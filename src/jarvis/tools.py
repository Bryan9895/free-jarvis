"""Ferramentas explicitamente autorizadas, limitadas ao workspace."""
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
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.approve = approve or (lambda action: False)
        self.browser = None

    def path(self, requested: str) -> Path:
        path = (self.workspace / requested).resolve()
        if not path.is_relative_to(self.workspace):
            raise ToolError("Acesso fora do workspace bloqueado")
        return path

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
        if len(content.encode()) > MAX_FILE_BYTES:
            raise ToolError("Arquivo muito grande")
        if not self.approve(f"ESCREVER {p} ({len(content)} caracteres)"):
            return {"status": "rejected"}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"status": "written", "path": str(p)}

    def run_command(self, command, cwd="."):
        """Executa somente comandos de inspeção sem shell; demais comandos são recusados."""
        args = shlex.split(command)
        if not args:
            raise ToolError("Comando vazio")
        allowed = {
            "pwd": set(), "ls": {"-l", "-la", "-a", "-h"},
            "git": {"status", "log", "diff", "branch", "remote"},
            "gh": {"repo", "auth"},
        }
        binary = args[0]
        if binary not in allowed:
            raise ToolError("Comando não permitido na versão inicial")
        if binary == "git" and (len(args) < 2 or args[1] not in allowed[binary]):
            raise ToolError("Subcomando git não permitido")
        if binary == "gh" and (len(args) < 3 or args[1:] not in (["auth", "status"], ["repo", "list"])):
            raise ToolError("Apenas 'gh auth status' e 'gh repo list' estão disponíveis")
        if binary == "ls" and any(a.startswith("-") and a not in allowed[binary] for a in args[1:]):
            raise ToolError("Opção ls não permitida")
        # Restringe argumento de caminho potencial; comandos git somente no diretório definido.
        if binary == "git" and len(args) > 2:
            if args[1] == "log" and args[2:] in (["-1"], ["--oneline"]):
                pass
            elif args[1] == "status" and args[2:] == ["--short"]:
                pass
            else:
                raise ToolError("Argumentos git não permitidos")
        if binary == "ls" and any(not a.startswith("-") and self.path(a) is None for a in args[1:]):
            raise ToolError("Caminho não permitido")
        run = subprocess.run(args, cwd=self.path(cwd), capture_output=True, text=True, timeout=15, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS":"0"})
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

    def execute(self, name, arguments):
        operations = {
            "list_files": self.list_files, "read_file": self.read_file,
            "write_file": self.write_file, "run_command": self.run_command,
            "browser_open": self.browser_open,
        }
        if name not in operations:
            return {"error": "Ferramenta desconhecida"}
        try:
            return {"result": operations[name](**arguments)}
        except (ToolError, OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            return {"error": str(exc)}

TOOL_SPECS = [
    {"type":"function","name":"list_files","description":"Lista arquivos e pastas dentro do workspace autorizado.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"additionalProperties":False}},
    {"type":"function","name":"read_file","description":"Lê arquivo de texto até 100 KB no workspace autorizado.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"write_file","description":"Escreve arquivo de texto dentro do workspace, após confirmação humana.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"],"additionalProperties":False}},
    {"type":"function","name":"run_command","description":"Comandos de inspeção limitados: pwd, ls, git status/log/diff/branch/remote, gh auth status, gh repo list.","parameters":{"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"}},"required":["command"],"additionalProperties":False}},
    {"type":"function","name":"browser_open","description":"Abre URL HTTP/HTTPS no navegador padrão após autorização. Não interage com a página.","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"],"additionalProperties":False}},
]
