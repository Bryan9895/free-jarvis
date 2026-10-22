"""Ferramentas locais com permissões explícitas, sem shell e workspace restrito."""
import os
from pathlib import Path
import shlex
import subprocess
import uuid
import shutil
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
        roots = []
        for value in os.getenv("JARVIS_ALLOWED_DIRS", "").split(os.pathsep):
            if value.strip():
                root = Path(value.strip()).expanduser().resolve()
                if root.is_dir() and root != Path.home().resolve() and root != Path("/"):
                    roots.append(root)
        self.allowed_roots = [self.workspace] + [p for p in roots if p != self.workspace]

    def path(self, requested: str) -> Path:
        if not isinstance(requested, str):
            raise ToolError("Caminho inválido")
        p = (self.workspace / requested).resolve()
        if not any(p.is_relative_to(root) for root in self.allowed_roots):
            raise ToolError("Acesso fora dos diretórios autorizados bloqueado")
        return p

    def _safe_mutation_path(self, requested):
        if not isinstance(requested, str):
            raise ToolError("Caminho inválido")
        raw = Path(requested).expanduser()
        if not raw.is_absolute():
            raw = self.workspace / raw
        raw = Path(os.path.abspath(raw))
        for root in self.allowed_roots:
            if raw.is_relative_to(root):
                candidate = raw
                while candidate != root:
                    if candidate.is_symlink():
                        raise ToolError("Links simbólicos não são aceitos em alterações")
                    candidate = candidate.parent
                return self.path(requested)
        raise ToolError("Acesso fora dos diretórios autorizados bloqueado")

    def _is_root(self, path):
        return path in self.allowed_roots

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

    def make_directory(self, path):
        destination = self._safe_mutation_path(path)
        if self._is_root(destination):
            raise ToolError("Escolha uma subpasta do workspace")
        if destination.exists():
            raise ToolError("O caminho já existe")
        if not self.approve(f"CRIAR PASTA {destination}"):
            return {"status": "rejected"}
        # Revalidar após a confirmação.
        destination = self._safe_mutation_path(path)
        destination.mkdir(parents=True, exist_ok=False)
        return {"status": "created", "path": str(destination)}

    def move_path(self, source, destination):
        src, dst = self._safe_mutation_path(source), self._safe_mutation_path(destination)
        if self._is_root(src) or self._is_root(dst) or src == self.workspace / ".jarvis-trash":
            raise ToolError("Não é permitido mover a raiz do workspace nem a lixeira")
        if src == dst or not src.exists() or dst.exists():
            raise ToolError("Origem ausente, destino existente ou caminhos idênticos")
        if src.is_symlink() or dst.is_symlink():
            raise ToolError("Links simbólicos não são aceitos nesta operação")
        if src.is_dir() and dst.is_relative_to(src):
            raise ToolError("Não é possível mover uma pasta para dentro dela mesma")
        if not dst.parent.is_dir():
            raise ToolError("A pasta de destino precisa existir")
        if not self.approve(f"MOVER {src} PARA {dst}"):
            return {"status": "rejected"}
        src, dst = self._safe_mutation_path(source), self._safe_mutation_path(destination)
        if not src.exists() or dst.exists():
            raise ToolError("Os caminhos mudaram; operação cancelada")
        moved = shutil.move(str(src), str(dst))
        return {"status": "moved", "path": moved}

    def delete_path(self, path):
        """Move para a lixeira interna do workspace, sem excluir definitivamente."""
        target = self._safe_mutation_path(path)
        trash = self.workspace / ".jarvis-trash"
        if self._is_root(target) or target == trash or target.is_relative_to(trash):
            raise ToolError("Não é permitido remover a raiz ou a lixeira")
        if target.is_symlink() or not target.exists():
            raise ToolError("Caminho inexistente ou link simbólico não permitido")
        if not self.approve(f"MOVER PARA LIXEIRA INTERNA {target}"):
            return {"status": "rejected"}
        target = self._safe_mutation_path(path)
        if not target.exists() or target.is_symlink():
            raise ToolError("Caminho alterado desde a autorização")
        trash.mkdir(exist_ok=True)
        destination = trash / (uuid.uuid4().hex + "-" + target.name)
        shutil.move(str(target), str(destination))
        return {"status": "trashed", "previous_path": str(target), "trash_path": str(destination)}

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

    def list_installed_apps(self, query="", limit=40):
        from .apps import installed_applications
        return installed_applications(limit=limit, query=query)

    def launch_installed_app(self, app_id):
        from .apps import launch_installed_app
        return launch_installed_app(app_id, self.approve)

    def authorized_directories(self):
        return [{"path": str(root), "default": root == self.workspace}
                for root in self.allowed_roots]

    def desktop_info(self):
        from .wayland import desktop_info
        return desktop_info()

    def desktop_screenshot(self):
        from .wayland import screenshot
        return screenshot(self.workspace, self.approve)

    def desktop_open_app(self, app_id):
        from .wayland import open_app
        return open_app(app_id, self.approve)

    def desktop_input(self, action, dx=0, dy=0, text=""):
        from .remote_desktop import agent_step
        return agent_step(self.approve, action, dx=dx, dy=dy, text=text)

    def execute(self, name, arguments):
        operations = {
            "list_files": self.list_files, "read_file": self.read_file,
            "write_file": self.write_file, "make_directory": self.make_directory,
            "move_path": self.move_path, "delete_path": self.delete_path,
            "run_command": self.run_command,
            "browser_open": self.browser_open,
            "browser_navigate": self.browser_navigate, "browser_inspect": self.browser_inspect,
            "browser_click": self.browser_click, "browser_fill": self.browser_fill,
            "browser_screenshot": self.browser_screenshot,
            "desktop_info": self.desktop_info, "desktop_screenshot": self.desktop_screenshot,
            "desktop_open_app": self.desktop_open_app,
            "list_installed_apps": self.list_installed_apps,
            "launch_installed_app": self.launch_installed_app,
            "authorized_directories": self.authorized_directories,
            "desktop_input": self.desktop_input,
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
    {"type":"function","name":"list_installed_apps","description":"Pesquisa aplicativos gráficos instalados visíveis no menu Ubuntu/GNOME. Informe query por nome ou ID antes de abrir. Não executa programas.","parameters":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":120}},"additionalProperties":False}},
    {"type":"function","name":"launch_installed_app","description":"Inicia um programa gráfico instalado pelo ID obtido em list_installed_apps, com autorização. Não executa comandos arbitrários nem confirma janela aberta.","parameters":{"type":"object","properties":{"app_id":{"type":"string"}},"required":["app_id"],"additionalProperties":False}},
    {"type":"function","name":"authorized_directories","description":"Lista as raízes de diretórios locais autorizados por JARVIS_ALLOWED_DIRS.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"make_directory","description":"Cria pasta dentro do workspace após confirmação.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"move_path","description":"Renomeia ou move arquivo/pasta dentro do workspace; destino não deve existir. Exige confirmação.","parameters":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"],"additionalProperties":False}},
    {"type":"function","name":"delete_path","description":"Remove arquivo ou pasta dentro do workspace movendo-o para .jarvis-trash, para permitir recuperação manual. Exige confirmação. Nunca faz exclusão permanente.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"desktop_input","description":"EXPERIMENTAL, desativado por padrão: executa UMA ação gráfica autorizada por sessão GNOME/Wayland: move o cursor no máximo 50px por eixo, um clique esquerdo na posição atual, ou digita até 40 caracteres minúsculos/dígitos/espaço. Não percebe a tela nem sabe onde está o foco. Requer JARVIS_ENABLE_DESKTOP_INPUT=1, aprovação do usuário e diálogo RemoteDesktop do GNOME. Não usar para compras, senhas, terminais ou operações irreversíveis.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["move","click","type"]},"dx":{"type":"number"},"dy":{"type":"number"},"text":{"type":"string"}},"required":["action"],"additionalProperties":False}},
    {"type":"function","name":"desktop_open_app","description":"Abre aplicativo Linux pelo ID do arquivo .desktop, apenas se permitido em JARVIS_ALLOWED_APPS e confirmado pelo usuário. Não promete foco de janela.","parameters":{"type":"object","properties":{"app_id":{"type":"string"}},"required":["app_id"],"additionalProperties":False}},
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
