"""Cliente FCC com diagnóstico e failover de modelos retornados por /v1/models."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TRANSIENT = frozenset({429, 500, 502, 503, 504})

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
        return self.request("POST", "/v1/responses", payload)

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
            try:
                response = self.client.responses({**payload, "model": model})
                if index and self.on_switch:
                    self.on_switch(model)
                self.active_model = model
                return response
            except FCCError as exc:
                last_error = exc
                if exc.status not in TRANSIENT and exc.status is not None:
                    raise
                # Erros de transporte podem significar que o servidor está desligado,
                # mas tentar outro modelo não executa ações externas no computador.
        raise last_error or FCCError("Nenhum modelo disponível")

    def diagnostic(self):
        self.initialize()
        response = self.responses({
            "model": self.active_model, "input": "Responda somente: OK",
            "max_output_tokens": 48, "stream": False
        })
        output = response.get("output", [])
        text = response.get("output_text") or " ".join(
            p.get("text", "") for i in output if i.get("type") == "message"
            for p in i.get("content", []) if p.get("type") == "output_text"
        )
        if not str(text).strip():
            raise FCCError("FCC respondeu sem texto; verifique modelo e formato Responses")
        return {"status": "ok", "model": self.active_model, "reply": str(text).strip()[:200]}
