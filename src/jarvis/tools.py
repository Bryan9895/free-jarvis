"""Ferramentas locais com permissões explícitas, sem shell e workspace restrito."""
import os
from pathlib import Path
import shlex
import subprocess
from urllib.parse import urlparse

MAX_FILE_BYTES = 100_000

class ToolError(ValueError):
    pass

class Toolkit:
    def __init__(self, workspace: Path, approve=None):
        self.workspace = workspace.expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.approve = approve or (lambda _action: False)
        self._browser = None

    def path(self, requested: str) -> Path:
        if not isinstance(requested, str):
            raise ToolError("Caminho inválido")
        p = (self.workspace / requested).resolve()
        if not p.is_relative_to(self.workspace):
            raise ToolError("Acesso fora do workspace bloqueado")
        return p

    def list_files(self, path="."):
        p = self.path(path)
        if not p.is_dir():
            raise ToolError("Diretório inexistente")
        return [{"name": x.name, "directory": x.is_dir()} for x in sorted(p.iterdir())[:120]]

    def read_file(self, path):
        p = self.path(path)
        if not p.is_file():
            raise ToolError("Arquivo inexistente")
        if p.stat().st_size > MAX_FILE_BYTES:
            raise ToolError("Arquivo muito grande (limite 100 KB)")
        return p.read_text(encoding="utf-8")

    def write_file(self, path, content):
        p = self.path(path)
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
            raise ToolError("Conteúdo inválido ou arquivo muito grande")
        if not self.approve(f"ESCREVER {p} ({len(content)} caracteres)"):
            return {"status": "rejected"}
        p = self.path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p = self.path(path)
        p.write_text(content, encoding="utf-8")
        return {"status": "written", "path": str(p)}

    def run_command(self, command, cwd="."):
        """Executa apenas comandos de inspeção exatos, sem shell."""
        try:
            args = shlex.split(command)
        except (TypeError, ValueError) as exc:
            raise ToolError("Comando inválido") from exc
        allowed = (
            ["pwd"], ["ls"], ["ls", "-la"], ["ls", "-l"], ["ls", "-a"],
            ["git", "status"], ["git", "status", "--short"],
            ["git", "diff"], ["git", "branch"], ["git", "remote"],
            ["git", "log", "-1"], ["git", "log", "--oneline"],
            ["gh", "auth", "status"], ["gh", "repo", "list"],
        )
        if args not in allowed:
            raise ToolError("Comando ou argumentos não permitidos nesta versão")
        run = subprocess.run(args, cwd=self.path(cwd), capture_output=True, text=True,
                             timeout=15, check=False,
                             env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_PAGER": "cat", "PAGER": "cat"})
        return {"exit_code": run.returncode, "stdout": run.stdout[:10000], "stderr": run.stderr[:1500]}

    def browser_open(self, url):
        u = urlparse(url)
        if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password:
            raise ToolError("URL inválida")
        if not self.approve(f"ABRIR URL {url} (pode acessar rede)"):
            return {"status": "rejected"}
        import webbrowser
        webbrowser.open(url)
        return {"status": "opened_unverified", "url": url}

    def _browser_client(self):
        if self._browser is None:
            from .browser import BrowserController
            self._browser = BrowserController(self.workspace)
        return self._browser

    def browser_navigate(self, url):
        from .browser_worker import validate_url
        validate_url(url)
        if not self.approve(f"NAVEGAR no navegador isolado para {url}"):
            return {"status": "rejected"}
        return self._browser_client().perform("navigate", url=url)

    def browser_inspect(self):
        return self._browser_client().perform("inspect")

    def browser_click(self, selector):
        if not self.approve(f"CLICAR no elemento {selector!r} (pode enviar formulários ou alterar dados)"):
            return {"status": "rejected"}
        return self._browser_client().perform("click", selector=selector)

    def browser_fill(self, selector, text):
        if not self.approve(f"PREENCHER elemento {selector!r} com {len(text)} caracteres (conteúdo pode ser sensível)"):
            return {"status": "rejected"}
        return self._browser_client().perform("fill", selector=selector, text=text)

    def browser_screenshot(self):
        if not self.approve("SALVAR captura de tela do navegador isolado no workspace"):
            return {"status": "rejected"}
        return self._browser_client().perform("screenshot")

    def close(self):
        if self._browser is not None:
            self._browser.close()
            self._browser = None

    def desktop_info(self):
        from .wayland import desktop_info
        return desktop_info()

    def desktop_screenshot(self):
        from .wayland import screenshot
        return screenshot(self.workspace, self.approve)

    def execute(self, name, arguments):
        operations = {
            "list_files": self.list_files, "read_file": self.read_file,
            "write_file": self.write_file, "run_command": self.run_command,
            "browser_open": self.browser_open,
            "browser_navigate": self.browser_navigate, "browser_inspect": self.browser_inspect,
            "browser_click": self.browser_click, "browser_fill": self.browser_fill,
            "browser_screenshot": self.browser_screenshot,
            "desktop_info": self.desktop_info, "desktop_screenshot": self.desktop_screenshot,
        }
        if name not in operations:
            return {"error": "Ferramenta desconhecida"}
        try:
            return {"result": operations[name](**arguments)}
        except (ToolError, OSError, UnicodeError, subprocess.TimeoutExpired, TypeError, ValueError) as exc:
            return {"error": str(exc)}
        except RuntimeError as exc:
            return {"error": str(exc)}

TOOL_SPECS = [
    {"type":"function","name":"desktop_info","description":"Diagnostica sessão Wayland, compositor, Screenshot e RemoteDesktop portals; não controla o computador.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"desktop_screenshot","description":"Solicita captura da área de trabalho via portal XDG, com dupla aprovação do usuário. Salva imagem no workspace. A imagem não é transmitida ao modelo automaticamente.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"browser_navigate","description":"Navega em endereço público HTTP/HTTPS com navegador Chromium isolado; exige aprovação.","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"],"additionalProperties":False}},
    {"type":"function","name":"browser_inspect","description":"Lê título, URL, texto e elementos interativos da página atual sem executar JavaScript fornecido pelo modelo.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"browser_click","description":"Clica exatamente em um elemento CSS, após aprovação; pode enviar formulário.","parameters":{"type":"object","properties":{"selector":{"type":"string"}},"required":["selector"],"additionalProperties":False}},
    {"type":"function","name":"browser_fill","description":"Preenche exatamente um campo por seletor CSS, após aprovação; não envia automaticamente.","parameters":{"type":"object","properties":{"selector":{"type":"string"},"text":{"type":"string"}},"required":["selector","text"],"additionalProperties":False}},
    {"type":"function","name":"browser_screenshot","description":"Salva screenshot do navegador isolado em jarvis_screenshot.png no workspace mediante aprovação.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"list_files","description":"Lista arquivos e pastas dentro do workspace autorizado.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"additionalProperties":False}},
    {"type":"function","name":"read_file","description":"Lê arquivo de texto até 100 KB no workspace autorizado.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"write_file","description":"Escreve arquivo de texto dentro do workspace, após confirmação humana.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"],"additionalProperties":False}},
    {"type":"function","name":"run_command","description":"Comandos de inspeção limitados, sem argumentos livres.","parameters":{"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"}},"required":["command"],"additionalProperties":False}},
    {"type":"function","name":"browser_open","description":"Abre URL HTTP/HTTPS no navegador padrão após autorização.","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"],"additionalProperties":False}},
]
