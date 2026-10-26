"""Cliente FCC com diagnóstico e failover de modelos retornados por /v1/models."""
import json
import sys
import os
from time import monotonic
from uuid import uuid4
from .latency import mark
from .transport import ReadBudget
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TRANSIENT = frozenset({429, 500, 502, 503, 504})

def may_fallback(error):
    """404 só autoriza fallback se vier de erro explicitamente atribuído ao provedor."""
    if error.category in ("invalid_response", "deadline", "partial_stream"):
        return False
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
    def __init__(self, message, status=None, category=None):
        super().__init__(message)
        self.status = status
        self.category = category or self._category(status, message)

    @staticmethod
    def _category(status, message):
        if status in (401, 403):
            return "authentication"
        if status == 429:
            return "rate_limit"
        if status in (500, 502, 503, 504) or status is None and "indisponível" in message.lower():
            return "unavailable"
        if "inválid" in message.lower() or "sem evento response.completed" in message.lower():
            return "invalid_response"
        return "request"

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
            try:
                detail = exc.read(700).decode(errors="replace")
            finally:
                exc.close()
            raise FCCError(f"HTTP {exc.code} em {path}: {detail}", exc.code) from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise FCCError(f"FCC indisponível: {exc}") from exc
        except ValueError as exc:
            raise FCCError("Resposta JSON inválida do FCC", category="invalid_response") from exc

    def health(self):
        return self.request("GET", "/health")

    def models(self):
        # A visão padrão contém aliases Claude. Responses anuncia IDs roteáveis;
        # a listagem não comprova disponibilidade de inferência ou function calling.
        return self.request("GET", "/v1/models?view=responses")

    def responses(self, payload):
        return self.stream_responses(payload)

    def stream_responses(self, payload, *, on_event=None, cancel_token=None, deadline=None):
        """SSE incremental; o evento terminal libera o socket sem esperar EOF."""
        deadline = deadline or monotonic() + self.timeout
        if cancel_token is not None:
            cancel_token.check()
            if cancel_token.deadline is not None:
                deadline = min(deadline, cancel_token.deadline)
        if monotonic() >= deadline:
            raise FCCError('Prazo total da requisição excedido', category='deadline')
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = json.dumps({**payload, "stream": True}).encode()
        req = Request(self.base_url + "/v1/responses", data=body, headers=headers, method="POST")
        request_id = uuid4().hex
        mark('provider_start', request_id=request_id)
        try:
            connect = min(float(os.getenv('FCC_CONNECT_TIMEOUT', '5')), deadline - monotonic())
            with urlopen(req, timeout=max(.001, connect)) as response:
                # O watchdog aplica os prazos após headers, inclusive se vierem
                # heartbeats. O deadline absoluto não reinicia a cada evento.
                sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                if sock is not None:
                    sock.settimeout(max(.001, deadline - monotonic()))
                with ReadBudget(response, token=cancel_token, deadline=deadline,
                        first=float(os.getenv('FCC_FIRST_EVENT_TIMEOUT', '30')),
                        idle=float(os.getenv('FCC_IDLE_TIMEOUT', '20'))) as budget:
                    event, lines, size = '', [], 0
                    first_event = True
                    first_text = True

                    def process():
                        nonlocal first_event, first_text
                        if not lines:
                            return None
                        try:
                            data = json.loads('\n'.join(lines))
                        except ValueError as exc:
                            raise FCCError('Evento SSE inválido do FCC', category='invalid_response') from exc
                        if not isinstance(data, dict):
                            raise FCCError('Evento SSE inválido do FCC', category='invalid_response')
                        kind = data.get('type', event)
                        if first_event:
                            mark('provider_first_event', request_id=request_id)
                            first_event = False
                        if kind in ('response.failed', 'response.incomplete', 'error'):
                            result = data.get('response') or {}
                            reason = (result.get('incomplete_details') or {}).get('reason', 'não informado') if isinstance(result, dict) else 'não informado'
                            raise FCCError('FCC retornou ' + str(kind) + ' (motivo: ' + str(reason)[:100] + ')', category='invalid_response')
                        if kind == 'response.completed':
                            final = data.get('response')
                            if not isinstance(final, dict) or not isinstance(final.get('output'), list):
                                raise FCCError('Evento response.completed inválido', category='invalid_response')
                            mark('provider_final', request_id=request_id)
                            return final
                        # Apenas texto público. Não encaminhar raciocínio ou
                        # argumentos parciais às interfaces.
                        if kind == 'response.output_text.delta' and isinstance(data.get('delta'), str):
                            if first_text and data['delta'].strip():
                                mark('provider_first_text', request_id=request_id)
                                first_text = False
                            if on_event is not None:
                                on_event({'type': kind, 'delta': data['delta']})
                        return None

                    while True:
                        budget.check()
                        raw = response.readline(1024 * 1024 + 1)
                        budget.check()
                        if not raw:
                            final = process()
                            if final is not None:
                                return final
                            break
                        if len(raw) > 1024 * 1024:
                            raise FCCError('Evento SSE excedeu limite', category='invalid_response')
                        line = raw.decode('utf-8', errors='strict').rstrip('\r\n')
                        if not line:
                            if lines:
                                budget.touch()
                            final = process()
                            event, lines, size = '', [], 0
                            if final is not None:
                                return final
                        elif line.startswith('event:'):
                            event = line[6:].strip()
                        elif line.startswith('data:'):
                            value = line[5:].removeprefix(' ')
                            if value.strip() == '[DONE]':
                                final = process()
                                if final is not None:
                                    return final
                                break
                            lines.append(value)
                            size += len(raw)
                            if size > 1024 * 1024:
                                raise FCCError('Evento SSE excedeu limite', category='invalid_response')
                    raise FCCError('Streaming encerrado sem evento response.completed válido', category='invalid_response')
        except HTTPError as exc:
            try:
                detail = exc.read(700).decode(errors='replace')
            finally:
                exc.close()
            raise FCCError(f'HTTP {exc.code} em /v1/responses: {detail}', exc.code) from exc
        except (URLError, TimeoutError, ConnectionError, OSError) as exc:
            if cancel_token is not None:
                cancel_token.check()
            category = 'deadline' if isinstance(exc, TimeoutError) or monotonic() >= deadline else 'unavailable'
            raise FCCError('Conexão FCC interrompida: ' + str(exc), category=category) from exc
        except UnicodeError as exc:
            raise FCCError('UTF-8 inválido no SSE', category='invalid_response') from exc

class AutoModelClient:
    """Seleciona modelo inicial e tenta outro para falhas transitórias.
    
    Não marca todas as entradas do catálogo como saudáveis: somente uma geração real
    comprova disponibilidade. Não reenvia operações locais, somente requisições ao FCC.
    """
    def __init__(self, client, preferred="", backups=(), on_switch=None, allow_cross_provider=False):
        self.client = client
        self.preferred = preferred
        self.backups = tuple(backups)
        self.allow_cross_provider = allow_cross_provider
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
        primary = self.preferred or (default if default in available else available[0])
        provider = primary.split("/", 1)[0] if "/" in primary else ""
        same_provider = [m for m in available if (m.split("/", 1)[0] if "/" in m else "") == provider]
        # Modelo explicitamente selecionado jamais migra de provedor sem um
        # fallback igualmente explícito, exceto se usuário habilitar a opção.
        implicit = [] if self.preferred else same_provider
        if self.allow_cross_provider:
            implicit = available
        self.candidates = list(dict.fromkeys([primary, *self.backups, *implicit]))
        self.active_model = self.candidates[0]
        return self.active_model

    def available_models(self):
        if not self.candidates:
            self.initialize()
        catalog = self.client.models()
        return [m["id"] for m in catalog.get("data", [])
                if isinstance(m, dict) and isinstance(m.get("id"), str)]

    def select_model(self, name):
        if not isinstance(name, str) or name not in self.available_models():
            raise FCCError("Modelo não encontrado no catálogo Responses")
        self.active_model = name
        self.candidates = [name]
        return name

    def use_all_models(self):
        """Inclui todos os IDs Responses como alternativas, preservando a ordem FCC."""
        models = self.available_models()
        if not models:
            raise FCCError("Nenhum modelo Responses anunciado.")
        current = self.active_model if self.active_model in models else models[0]
        self.candidates = [current] + [m for m in models if m != current]
        self.active_model = current
        return list(self.candidates)

    def responses(self, payload):
        return self.stream_responses(payload)

    def stream_responses(self, payload, *, on_event=None, cancel_token=None, deadline=None):
        deadline = deadline or monotonic() + getattr(self.client, 'timeout', 100)
        emitted = False
        def forward(event):
            nonlocal emitted
            if on_event is not None:
                emitted = True
                on_event(event)
        if not self.candidates:
            self.initialize()
        candidates = [self.active_model] + [m for m in self.candidates if m != self.active_model]
        # Um catálogo Responses não garante suporte a function calling. Em pedidos
        # com ferramentas, não migrar automaticamente para modelos incompatíveis
        # (por exemplo, de geração especializada) só porque são do mesmo provedor.
        # Backups expressamente configurados pelo usuário continuam permitidos.
        if payload.get("tools"):
            candidates = [self.active_model] + [
                model for model in candidates[1:] if model in self.backups
            ]
        last_error = None
        for index, model in enumerate(candidates[:max(1, int(os.getenv("FCC_MAX_ATTEMPTS", "3")))]):
            if cancel_token is not None:
                cancel_token.check()
            if monotonic() >= deadline:
                raise FCCError("Prazo total da requisição excedido", category="deadline")
            mark("provider_attempt", attempt=index + 1)
            if getattr(self, "_diagnosing", False):
                print(f"FCC: testando {model} ...", file=sys.stderr, flush=True)
            try:
                if callable(getattr(type(self.client), 'stream_responses', None)):
                    response = self.client.stream_responses({**payload, 'model': model},
                        on_event=forward, cancel_token=cancel_token, deadline=deadline)
                else:
                    response = self.client.responses({**payload, 'model': model})
                if index and self.on_switch:
                    self.on_switch(model)
                self.active_model = model
                return response
            except FCCError as exc:
                last_error = exc
                if getattr(self, "_diagnosing", False):
                    print(f"FCC: modelo {model} falhou: {str(exc)[:160]}", file=sys.stderr, flush=True)
                if emitted or not may_fallback(exc):
                    raise
                # Erros de transporte podem significar que o servidor está desligado,
                # mas tentar outro modelo não executa ações externas no computador.
        raise last_error or FCCError("Nenhum modelo disponível")

    def diagnostic(self):
        self.initialize()
        # Diagnóstico intencionalmente curto; não varrer todo o catálogo de provedores.
        saved_candidates = self.candidates
        self.candidates = self.candidates[:3]
        previous_timeout = getattr(self.client, "timeout", None)
        if previous_timeout is not None:
            default_timeout = 120 if self.active_model.startswith('ollama/') else 30
            self.client.timeout = max(1, int(os.getenv('FCC_DIAGNOSTIC_TIMEOUT', default_timeout)))
        previous_switch = self.on_switch
        def report_switch(model):
            if previous_switch:
                previous_switch(model)
        self.on_switch = report_switch
        self._diagnosing = True
        try:
            print("Diagnóstico: modelos candidatos: " + ", ".join(self.candidates), file=sys.stderr, flush=True)
            response = self.responses({
            "model": self.active_model,
            "input": [{"role": "user", "content": "Responda somente: OK"}],
            "max_output_tokens": 768, "reasoning": {"effort": "none"}, "stream": True
            })
        finally:
            self._diagnosing = False
            self.candidates = saved_candidates
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
