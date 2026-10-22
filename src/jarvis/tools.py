"""Ferramentas locais com permissões explícitas, sem shell e workspace restrito."""
import os
import hashlib
import difflib
import sqlite3
from pathlib import Path
import shlex
import subprocess
import tempfile
import uuid
import shutil
from urllib.parse import urlparse

MAX_FILE_BYTES = 100_000

class ToolError(ValueError):
    pass

class Toolkit:
    def __init__(self, workspace: Path, approve=None, layout_db=None):
        self.workspace = workspace.expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.approve = approve or (lambda _action: False)
        self.layout_db = layout_db
        self._browser = None
        from .process_manager import ProcessManager
        self._processes = ProcessManager()
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

    def write_file(self, path, content, expected_sha256=None):
        p = self._safe_mutation_path(path)
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
            raise ToolError("Conteúdo inválido ou arquivo muito grande")
        if p.exists() and not p.is_file():
            raise ToolError("O destino não é um arquivo regular")
        if p.exists() and p.stat().st_size > MAX_FILE_BYTES:
            raise ToolError("Arquivo existente muito grande para edição segura")
        before = p.read_bytes() if p.exists() else None
        before_hash = hashlib.sha256(before).hexdigest() if before is not None else None
        if expected_sha256 is not None and expected_sha256 != before_hash:
            raise ToolError("Arquivo mudou desde a leitura; conteúdo esperado não confere")
        try:
            previous = before.decode("utf-8") if before is not None else ""
        except UnicodeDecodeError as exc:
            raise ToolError("Arquivo existente não é texto UTF-8") from exc
        diff = "".join(difflib.unified_diff(
            previous.splitlines(keepends=True), content.splitlines(keepends=True),
            fromfile=str(p) if before is not None else "/dev/null", tofile=str(p),
        ))
        summary = diff[:4000] + ("\n[diff truncado]" if len(diff) > 4000 else "")
        if not self.approve(f"ESCREVER {p} ({len(content)} caracteres)\n{summary}"):
            return {"status": "rejected"}
        p = self._safe_mutation_path(path)
        if p.exists() and not p.is_file():
            raise ToolError("O destino mudou desde a autorização")
        current = p.read_bytes() if p.exists() else None
        if current != before:
            raise ToolError("O arquivo mudou durante a autorização; escrita cancelada")
        p.parent.mkdir(parents=True, exist_ok=True)
        p = self._safe_mutation_path(path)
        if (p.read_bytes() if p.exists() else None) != before:
            raise ToolError("O arquivo mudou antes da escrita; operação cancelada")
        fd, temporary = tempfile.mkstemp(prefix=".jarvis-write-", dir=p.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                if before is not None:
                    os.fchmod(output.fileno(), p.stat().st_mode & 0o777)
                output.write(content.encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
            p = self._safe_mutation_path(path)
            if (p.read_bytes() if p.exists() else None) != before:
                raise ToolError("O arquivo mudou antes da substituição; operação cancelada")
            os.replace(temporary, p)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {"status": "written", "path": str(p),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}

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

    def create_python_project(self, path):
        """Cria estrutura Python mínima sem instalar pacotes nem executar código."""
        folder = self._safe_mutation_path(path)
        if self._is_root(folder) or folder.exists():
            raise ToolError("Escolha uma nova subpasta de projeto")
        if not folder.parent.is_dir():
            raise ToolError("A pasta pai precisa existir")
        if not self.approve(f"CRIAR PROJETO PYTHON {folder} (main.py, README.md, .gitignore)?"):
            return {"status": "rejected"}
        folder = self._safe_mutation_path(path)
        if folder.exists() or not folder.parent.is_dir():
            raise ToolError("O destino mudou desde a autorização")
        folder.mkdir(exist_ok=False)
        (folder / "main.py").write_text(
            'def main():\n    print("Olá, mundo!")\n\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8")
        (folder / "README.md").write_text(
            f"# {folder.name}\n\nProjeto Python criado pela JARVIS.\n",
            encoding="utf-8")
        (folder / ".gitignore").write_text(
            "__pycache__/\n*.py[cod]\n.venv/\n",
            encoding="utf-8")
        return {"status": "created", "path": str(folder),
                "files": ["main.py", "README.md", ".gitignore"]}

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
        self._processes.close()
        if self._browser is not None:
            self._browser.close()
            self._browser = None

    def list_installed_apps(self, query="", limit=40):
        from .apps import installed_applications
        return installed_applications(limit=limit, query=query)

    def launch_installed_app(self, app_id):
        from .apps import launch_installed_app
        return launch_installed_app(app_id, self.approve)

    def open_project(self, path, editor="vscode"):
        folder = self.path(path)
        return self._processes.open_project(folder, editor, self.approve)

    def open_file(self, path, editor="vscode"):
        file_path = self.path(path)
        return self._processes.open_file(file_path, editor, self.approve)

    def launch_installed_app_and_focus(self, app_id):
        """Abre aplicativo XDG, depois pede aprovação para focar janela única."""
        from .apps import launch_installed_app
        launched = launch_installed_app(app_id, self.approve)
        if launched.get("status") != "launched_unverified":
            return {"launch": launched, "focus": {"status": "not_attempted"}}
        from .window_tracking import _aliases
        # Alias único e específico à classe, sem escolher uma janela por título.
        aliases = _aliases(app_id)
        app_class = aliases[-1] if len(aliases) > 1 else aliases[0]
        focused = self.focus_window(app_class)
        return {"launch": launched, "focus": focused}

    def open_project_and_focus(self, path, editor="vscode"):
        """Abre projeto e tenta focar somente janela com título do projeto."""
        directory = self.path(path)
        launched = self._processes.open_project(directory, editor, self.approve)
        if launched.get("status") != "launched_unverified":
            return {"launch": launched, "focus": {"status": "not_attempted"}}
        aliases = {"vscode": "code", "vscodium": "codium",
                   "vscode-insiders": "code"}
        focused = self.focus_window(aliases[editor], directory.name)
        return {"launch": launched, "focus": focused}

    def open_file_and_focus(self, path, editor="vscode"):
        """Abre arquivo e tenta focar somente janela com título do arquivo."""
        file_path = self.path(path)
        launched = self._processes.open_file(file_path, editor, self.approve)
        if launched.get("status") != "launched_unverified":
            return {"launch": launched, "focus": {"status": "not_attempted"}}
        aliases = {"vscode": "code", "vscodium": "codium",
                   "vscode-insiders": "code"}
        focused = self.focus_window(aliases[editor], file_path.name)
        return {"launch": launched, "focus": focused}

    def verify_file(self, path, content=None):
        file_path = self.path(path)
        if not file_path.is_file():
            return {"status": "not_found", "path": str(file_path)}
        if content is not None:
            if not isinstance(content, str):
                raise ToolError("Conteúdo esperado inválido")
            if file_path.stat().st_size > MAX_FILE_BYTES:
                raise ToolError("Arquivo grande demais para verificação textual")
            actual = file_path.read_text(encoding="utf-8")
            return {"status": "verified" if actual == content else "content_mismatch",
                    "path": str(file_path), "bytes": file_path.stat().st_size}
        return {"status": "verified", "path": str(file_path),
                "bytes": file_path.stat().st_size}

    def managed_processes(self):
        return self._processes.list_launches()

    def authorized_directories(self):
        return [{"path": str(root), "default": root == self.workspace}
                for root in self.allowed_roots]

    def desktop_windows(self):
        from .desktop_windows import desktop_windows
        return desktop_windows()

    def verify_app_window(self, app, title=""):
        from .desktop_windows import verify_app_window
        return verify_app_window(app, title)

    def focus_window(self, app, title=""):
        from .window_focus import focus_window
        return focus_window(app, title, self.approve)

    def manage_window(self, app, action, title=""):
        from .window_manage import manage_window
        return manage_window(app, title, action, self.approve)

    def place_window(self, app, position, title="", width_percent=None, height_percent=None,
                     x_px=None, y_px=None, width_px=None, height_px=None):
        from .window_layout import place_window
        return place_window(app, position, self.approve, title=title,
                            width_percent=width_percent, height_percent=height_percent,
                            x_px=x_px, y_px=y_px, width_px=width_px, height_px=height_px)

    def close_window(self, app, title=""):
        from .window_manage import close_window
        return close_window(app, title, self.approve)

    def focused_window(self):
        from .window_manage import focused_window
        return focused_window()

    def arrange_windows(self, left_app, right_app, left_title="", right_title=""):
        from .window_layout import arrange_windows
        return arrange_windows(left_app, right_app, self.approve,
                               left_title=left_title, right_title=right_title)

    def arrange_window_grid(self, windows):
        from .window_layout import arrange_window_grid
        return arrange_window_grid(windows, self.approve)

    def save_window_layout(self, name, windows):
        from .layout_profiles import save_window_layout
        return save_window_layout(self.layout_db, name, windows, self.approve)

    def restore_window_layout(self, name):
        from .layout_profiles import restore_window_layout
        return restore_window_layout(self.layout_db, name, self.approve)

    def list_window_layouts(self):
        from .layout_profiles import list_window_layouts
        return list_window_layouts(self.layout_db)

    def window_action_history(self, limit=20):
        from .window_history import window_action_history
        return window_action_history(self.layout_db, limit)

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
            "create_python_project": self.create_python_project,
            "move_path": self.move_path, "delete_path": self.delete_path,
            "run_command": self.run_command,
            "browser_open": self.browser_open,
            "browser_navigate": self.browser_navigate, "browser_inspect": self.browser_inspect,
            "browser_click": self.browser_click, "browser_fill": self.browser_fill,
            "browser_screenshot": self.browser_screenshot,
            "desktop_info": self.desktop_info,
            "desktop_windows": self.desktop_windows,
            "verify_app_window": self.verify_app_window,
            "focus_window": self.focus_window, "manage_window": self.manage_window,
            "close_window": self.close_window, "focused_window": self.focused_window,
            "place_window": self.place_window, "arrange_windows": self.arrange_windows,
            "arrange_window_grid": self.arrange_window_grid,
            "save_window_layout": self.save_window_layout,
            "restore_window_layout": self.restore_window_layout,
            "list_window_layouts": self.list_window_layouts,
            "window_action_history": self.window_action_history,
            "desktop_screenshot": self.desktop_screenshot,
            "desktop_open_app": self.desktop_open_app,
            "list_installed_apps": self.list_installed_apps,
            "launch_installed_app": self.launch_installed_app,
            "authorized_directories": self.authorized_directories,
            "open_project": self.open_project, "open_file": self.open_file,
            "launch_installed_app_and_focus": self.launch_installed_app_and_focus,
            "open_project_and_focus": self.open_project_and_focus,
            "open_file_and_focus": self.open_file_and_focus,
            "verify_file": self.verify_file, "managed_processes": self.managed_processes,
            "desktop_input": self.desktop_input,
        }
        if name not in operations:
            return {"error": "Ferramenta desconhecida"}
        if getattr(self.approve, "mode", None) == "revoked":
            outcome = {"result": {"status": "rejected", "reason": "Sessão revogada"}}
        else:
            try:
                outcome = {"result": operations[name](**arguments)}
            except (ToolError, OSError, UnicodeError, subprocess.TimeoutExpired, TypeError, ValueError) as exc:
                outcome = {"error": str(exc)}
            except RuntimeError as exc:
                outcome = {"error": str(exc)}
        from .window_history import WINDOW_MUTATIONS, record_window_action
        if name in WINDOW_MUTATIONS and self.layout_db is not None:
            try:
                outcome["audit_id"] = record_window_action(self.layout_db, name, arguments, outcome)
            except (OSError, sqlite3.Error):
                outcome["audit_error"] = "Histórico de janelas indisponível"
        return outcome

TOOL_SPECS = [
    {"type":"function","name":"place_window","description":"Posiciona UMA janela na área útil: left, right, center, bottom_right ou custom. Percentuais opcionais definem tamanho relativo (10 a 100). custom exige x_px, y_px, width_px, height_px em pixels relativos à área útil e dentro dela. Revalida ID e confirma geometria GNOME após MoveResize e Move.","parameters":{"type":"object","properties":{"app":{"type":"string"},"position":{"type":"string","enum":["left","right","center","bottom_right","custom"]},"title":{"type":"string"},"width_percent":{"type":"integer"},"height_percent":{"type":"integer"},"x_px":{"type":"integer"},"y_px":{"type":"integer"},"width_px":{"type":"integer"},"height_px":{"type":"integer"}},"required":["app","position"],"additionalProperties":False}},
    {"type":"function","name":"close_window","description":"Solicita fechamento educado de UMA janela GNOME identificada sem ambiguidade. Sempre exige confirmação específica por risco de dados não salvos; só declara sucesso quando o ID desaparece do inventário.","parameters":{"type":"object","properties":{"app":{"type":"string"},"title":{"type":"string"}},"required":["app"],"additionalProperties":False}},
    {"type":"function","name":"focused_window","description":"Consulta a janela atualmente em foco via Window Control GetFocused e confirma ID, classe e título no inventário GNOME. Somente leitura.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"arrange_windows","description":"Organiza DUAS janelas GNOME no mesmo monitor, uma à esquerda e outra à direita. Só prossegue se ambas forem inequívocas. Informe left_app e right_app e títulos opcionais. Retorna layout_verified apenas se ambas as posições forem observadas.","parameters":{"type":"object","properties":{"left_app":{"type":"string"},"right_app":{"type":"string"},"left_title":{"type":"string"},"right_title":{"type":"string"}},"required":["left_app","right_app"],"additionalProperties":False}},
    {"type":"function","name":"arrange_window_grid","description":"Organiza exatamente três ou quatro janelas já abertas no mesmo monitor. Informe windows em ordem de leitura, cada uma com app e título opcional. Três: metade esquerda e duas à direita; quatro: grade 2x2. Recusa ambiguidades e verifica geometria de cada janela.","parameters":{"type":"object","properties":{"windows":{"type":"array","minItems":3,"maxItems":4,"items":{"type":"object","properties":{"app":{"type":"string"},"title":{"type":"string"}},"required":["app"],"additionalProperties":False}}},"required":["windows"],"additionalProperties":False}},
    {"type":"function","name":"save_window_layout","description":"Salva um perfil nomeado com a geometria atual de duas a quatro janelas já abertas no mesmo monitor. Informe seletores de app e título opcional, sem IDs inventados. Persiste em SQLite local.","parameters":{"type":"object","properties":{"name":{"type":"string"},"windows":{"type":"array","minItems":2,"maxItems":4,"items":{"type":"object","properties":{"app":{"type":"string"},"title":{"type":"string"}},"required":["app"],"additionalProperties":False}}},"required":["name","windows"],"additionalProperties":False}},
    {"type":"function","name":"restore_window_layout","description":"Restaura um perfil salvo para janelas já abertas. Redimensiona proporcionalmente à área útil atual, revalida IDs e verifica geometria após cada ação. Não abre aplicativos ausentes.","parameters":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}},
    {"type":"function","name":"list_window_layouts","description":"Lista nomes dos perfis de janelas salvos em SQLite local. Não altera janelas.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"window_action_history","description":"Lista até 50 ações recentes sobre janelas com estado observado, sem títulos ou conteúdo sensível. Somente leitura.","parameters":{"type":"object","properties":{"limit":{"type":"integer"}},"additionalProperties":False}},
    {"type":"function","name":"manage_window","description":"Minimiza, restaura, maximiza ou desfaz maximização de UMA janela GNOME Wayland identificada unicamente por app e título opcional. Requer extensão opcional Window Control; utiliza ID obtido do compositor, revalida janela e estado após comando, sem Shell.Eval. Não fecha janelas.","parameters":{"type":"object","properties":{"app":{"type":"string"},"title":{"type":"string"},"action":{"type":"string","enum":["minimize","restore","maximize","unmaximize"]}},"required":["app","action"],"additionalProperties":False}},
    {"type":"function","name":"launch_installed_app_and_focus","description":"Abre aplicativo XDG com autorização e tenta focar UMA janela correspondente com segunda aprovação, somente quando identificação no GNOME é inequívoca. Use o app_id obtido no catálogo; estados separados para abertura e foco.","parameters":{"type":"object","properties":{"app_id":{"type":"string"}},"required":["app_id"],"additionalProperties":False}},
    {"type":"function","name":"open_project_and_focus","description":"Abre projeto existente no editor, depois tenta trazer a janela desse projeto ao primeiro plano. Duas aprovações separadas e verificações GNOME; não afirma sucesso quando título do projeto não é encontrado.","parameters":{"type":"object","properties":{"path":{"type":"string"},"editor":{"type":"string","enum":["vscode","vscodium","vscode-insiders"]}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"open_file_and_focus","description":"Abre arquivo existente no editor, depois tenta trazer a janela desse arquivo ao primeiro plano. Aprovações separadas, identificação por título e verificação via GNOME Shell; pode retornar not_observed.","parameters":{"type":"object","properties":{"path":{"type":"string"},"editor":{"type":"string","enum":["vscode","vscodium","vscode-insiders"]}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"focus_window","description":"Com autorização explícita, solicita foco de UMA janela do GNOME Wayland usando a extensão opcional Activate Window By Title. Requer Window Calls Extended para identificar janela por app e título único. Confere foco depois; recusa ambiguidades. Não fecha, move ou redimensiona.","parameters":{"type":"object","properties":{"app":{"type":"string"},"title":{"type":"string"}},"required":["app"],"additionalProperties":False}},
    {"type":"function","name":"desktop_windows","description":"Consulta somente nomes de aplicativos e títulos de janelas que expõem acessibilidade AT-SPI no GNOME Wayland. Leitura, sem clique. Lista pode ser incompleta.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
    {"type":"function","name":"verify_app_window","description":"Procura janela acessível de aplicativo por nome e título opcional no GNOME Wayland. window_observed atesta somente janela acessível, não foco ou arquivo aberto. not_observed não prova ausência.","parameters":{"type":"object","properties":{"app":{"type":"string"},"title":{"type":"string"}},"required":["app"],"additionalProperties":False}},
    {"type":"function","name":"open_file","description":"Abre um arquivo INDIVIDUAL existente e autorizado no VS Code, VSCodium ou VS Code Insiders. Não abre diretórios; use open_project para pastas. Exige autorização.","parameters":{"type":"object","properties":{"path":{"type":"string"},"editor":{"type":"string","enum":["vscode","vscodium","vscode-insiders"]}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"verify_file","description":"Confere se um arquivo de texto existe dentro de diretórios autorizados e opcionalmente se seu conteúdo é exatamente igual a content. Não altera arquivos.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"create_python_project","description":"Cria uma nova pasta com projeto Python básico (main.py, README.md, .gitignore), dentro de diretório autorizado. Não sobrescreve nem executa código. Use open_project depois para abrir no VS Code.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"open_project","description":"Abre pasta de projeto existente em VS Code, VSCodium ou VS Code Insiders instalado, após autorização. Use editor=vscode e path absoluto dentro de diretório autorizado ou relativo ao workspace. Início do lançador não garante janela aberta.","parameters":{"type":"object","properties":{"path":{"type":"string"},"editor":{"type":"string","enum":["vscode","vscodium","vscode-insiders"]}},"required":["path"],"additionalProperties":False}},
    {"type":"function","name":"managed_processes","description":"Lista os editores de projeto lançados pela JARVIS nesta sessão e o estado real do processo lançador. Não garante estado da janela.","parameters":{"type":"object","properties":{},"additionalProperties":False}},
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
    {"type":"function","name":"write_file","description":"Escreve texto atomicamente em diretório autorizado. Mostra diff na autorização e recusa se o arquivo mudar durante a operação. Para editar versão lida antes, informe expected_sha256 do conteúdo anterior.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"expected_sha256":{"type":"string"}},"required":["path","content"],"additionalProperties":False}},
    {"type":"function","name":"run_command","description":"Comandos de inspeção limitados, sem argumentos livres.","parameters":{"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"}},"required":["command"],"additionalProperties":False}},
    {"type":"function","name":"browser_open","description":"Abre URL HTTP/HTTPS no navegador padrão após autorização.","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"],"additionalProperties":False}},
]
