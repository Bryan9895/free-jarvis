"""Cliente HTTP mínimo para a API OpenAI Responses do FCC."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class FCCError(RuntimeError):
    pass

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
            raise FCCError(f"HTTP {exc.code} em {path}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise FCCError(f"FCC indisponível: {exc}") from exc

    def models(self):
        return self.request("GET", "/v1/models")

    def responses(self, payload):
        return self.request("POST", "/v1/responses", payload)
