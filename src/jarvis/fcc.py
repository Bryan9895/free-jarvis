"""Cliente FCC com diagnóstico e failover de modelos retornados por /v1/models."""
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TRANSIENT = frozenset({429, 500, 502, 503, 504})

def may_fallback(error):
    """404 só autoriza fallback se vier de erro explicitamente atribuído ao provedor."""
    if error.status in TRANSIENT or error.status is None:
        return True
    if error.status == 400:
        detail = str(error).lower()
        return ("upstream provider gemini returned http 400" in detail
                and "this model only supports interactions api" in detail)
    if error.status == 404:
        detail = str(error).lower()
        return ("upstream provider" in detail and "returned http 404" in detail
                and "category: upstream" in detail)
    return False

class FCCError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

class FCCClient:
    def __init__(self, base_url: str, token: str = "", timeout: int = 100):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            detail = exc.read(700).decode(errors="replace")
            raise FCCError(f"HTTP {exc.code} em {path}: {detail}", exc.code) from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise FCCError(f"FCC indisponível: {exc}") from exc

    def health(self):
        return self.request("GET", "/health")

    def models(self):
        # A visualização padrão do FCC contém aliases Claude; Responses usa IDs específicos.
        return self.request("GET", "/v1/models?view=responses")

    def responses(self, payload):
        """FCC exige stream=true; monta a resposta final do evento SSE response.completed."""
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = json.dumps({**payload, "stream": True}).encode()
        req = Request(self.base_url + "/v1/responses", data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                final = None
                failed = None
                event = ""
                lines = []
                def process():
                    nonlocal final, failed
                    if not lines:
                        return
                    try:
                        data = json.loads("\n".join(lines))
                    except ValueError as exc:
                        raise FCCError("Evento SSE inválido do FCC") from exc
                    kind = data.get("type", event) if isinstance(data, dict) else event
                    if kind == "response.completed":
                        final = data.get("response")
                    elif kind in ("response.failed", "response.incomplete", "error"):
                        failed = data
                for raw in response:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        process()
                        event, lines = "", []
                    elif line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        if line[5:].strip() == "[DONE]":
                            break
                        lines.append(line[5:].lstrip())
                process()
                if failed is not None:
                    detail = failed.get("response", {}).get("error") if isinstance(failed.get("response"), dict) else failed.get("error")
                    raise FCCError("FCC não concluiu a resposta: " + str(detail or failed)[:600])
                if not isinstance(final, dict) or not isinstance(final.get("output"), list):
                    raise FCCError("Streaming encerrado sem evento response.completed válido")
                return final
        except HTTPError as exc:
            detail = exc.read(700).decode(errors="replace")
            raise FCCError(f"HTTP {exc.code} em /v1/responses: {detail}", exc.code) from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise FCCError(f"Conexão FCC interrompida: {exc}") from exc

class AutoModelClient:
    """Seleciona modelo inicial e tenta outro para falhas transitórias.
    
    Não marca todas as entradas do catálogo como saudáveis: somente uma geração real
    comprova disponibilidade. Não reenvia operações locais, somente requisições ao FCC.
    """
    def __init__(self, client, preferred="", backups=(), on_switch=None):
        self.client = client
        self.preferred = preferred
        self.backups = tuple(backups)
        self.on_switch = on_switch
        self.candidates = []
        self.active_model = ""

    def initialize(self):
        inventory = self.client.models()
        data = inventory.get("data", [])
        available = [m.get("id") for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]
        if not available:
            raise FCCError("FCC não anunciou modelos compatíveis com Responses")
        default = inventory.get("default_model_id")
        if self.preferred and self.preferred not in available:
            raise FCCError(f"Modelo configurado não encontrado no FCC: {self.preferred}")
        for model in self.backups:
            if model not in available:
                raise FCCError(f"Modelo de fallback desconhecido: {model}")
        configured = [self.preferred, *self.backups] if self.preferred else [default, *self.backups]
        self.candidates = list(dict.fromkeys(m for m in [*configured, *available] if m in available))
        self.active_model = self.candidates[0]
        return self.active_model

    def responses(self, payload):
        if not self.candidates:
            self.initialize()
        candidates = [self.active_model] + [m for m in self.candidates if m != self.active_model]
        last_error = None
        for index, model in enumerate(candidates):
            if getattr(self, "_diagnosing", False):
                print(f"FCC: testando {model} ...", file=sys.stderr, flush=True)
            try:
                response = self.client.responses({**payload, "model": model})
                if index and self.on_switch:
                    self.on_switch(model)
                self.active_model = model
                return response
            except FCCError as exc:
                last_error = exc
                if getattr(self, "_diagnosing", False):
                    print(f"FCC: modelo {model} falhou: {str(exc)[:160]}", file=sys.stderr, flush=True)
                if not may_fallback(exc):
                    raise
                # Erros de transporte podem significar que o servidor está desligado,
                # mas tentar outro modelo não executa ações externas no computador.
        raise last_error or FCCError("Nenhum modelo disponível")

    def diagnostic(self):
        self.initialize()
        # Diagnóstico intencionalmente curto; não varrer todo o catálogo de provedores.
        self.candidates = self.candidates[:3]
        previous_timeout = getattr(self.client, "timeout", None)
        if previous_timeout is not None:
            self.client.timeout = min(previous_timeout, 15)
        previous_switch = self.on_switch
        def report_switch(model):
            if previous_switch:
                previous_switch(model)
        self.on_switch = report_switch
        self._diagnosing = True
        try:
            print("Diagnóstico: modelos candidatos: " + ", ".join(self.candidates), file=sys.stderr, flush=True)
            response = self.responses({
            "model": self.active_model, "input": "Responda somente: OK",
            "max_output_tokens": 48, "stream": True
            })
        finally:
            self._diagnosing = False
            self.on_switch = previous_switch
            if previous_timeout is not None:
                self.client.timeout = previous_timeout
        output = response.get("output", [])
        text = response.get("output_text") or " ".join(
            p.get("text", "") for i in output if i.get("type") == "message"
            for p in i.get("content", []) if p.get("type") == "output_text"
        )
        if not str(text).strip():
            raise FCCError("FCC respondeu sem texto; verifique modelo e formato Responses")
        return {"status": "ok", "model": self.active_model, "reply": str(text).strip()[:200]}
