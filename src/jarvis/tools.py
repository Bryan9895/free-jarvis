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
import time
from collections import deque
from urllib.parse import urlparse
from .registry import CapabilityPolicy, ToolRegistry

MAX_FILE_BYTES = 100_000

class ToolError(ValueError):
    pass

class Toolkit:
    def __init__(self, workspace: Path, approve=None, layout_db=None, registry=None,
                 enabled_capabilities=None):
        self.workspace = workspace.expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.approve = approve or (lambda _action: False)
        self.layout_db = layout_db
        self.operation_log = deque(maxlen=100)
        self.registry = registry or DEFAULT_REGISTRY
        if enabled_capabilities is None:
            configured = os.getenv("JARVIS_ENABLED_CAPABILITIES")
            if configured is not None:
                enabled_capabilities = {item.strip() for item in configured.split(",") if item.strip()}
        self.capabilities = CapabilityPolicy(self.registry, enabled_capabilities)
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

    def desktop_spaces(self):
        from .desktop_spaces import desktop_spaces
        return desktop_spaces()

    def activate_workspace(self, workspace_number):
        from .workspace_control import activate_workspace
        return activate_workspace(workspace_number, self.approve)

    def move_window_to_workspace(self, app, workspace_number, title=""):
        from .workspace_control import move_window_to_workspace
        return move_window_to_workspace(app, workspace_number, self.approve, title)

    def move_window_to_monitor(self, app, monitor_number=None, title=""):
        from .monitor_control import move_window_to_monitor
        return move_window_to_monitor(app, self.approve, monitor_number, title)

    def save_desktop_profile(self, name, windows):
        from .desktop_profiles import save_desktop_profile
        return save_desktop_profile(self.layout_db, name, windows, self.approve)

    def list_desktop_profiles(self):
        from .desktop_profiles import list_desktop_profiles
        return list_desktop_profiles(self.layout_db)

    def restore_desktop_profile(self, name):
        from .desktop_profiles import restore_desktop_profile
        return restore_desktop_profile(self.layout_db, name, self.approve)

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
        started = time.monotonic()
        def finish(outcome, capability=None):
            detail = outcome.get("result") if isinstance(outcome, dict) else None
            status = "error" if "error" in outcome else (
                detail.get("status", "ok") if isinstance(detail, dict) else "ok")
            self.operation_log.append({"tool": name, "capability": capability,
                                       "status": status,
                                       "duration_ms": round((time.monotonic() - started) * 1000, 2)})
            return outcome

        entry = self.registry.get(name)
        if entry is None:
            return finish({"error": "Ferramenta desconhecida"})
        if not self.capabilities.permits(entry):
            return finish({"error": "Capacidade não autorizada: " + entry.capability},
                          entry.capability)
        if name == "desktop_input" and os.getenv("JARVIS_ENABLE_DESKTOP_INPUT") != "1":
            return finish({"error": "Entrada gráfica desativada"}, entry.capability)
        if not isinstance(arguments, dict):
            return finish({"error": "Argumentos devem formar um objeto JSON"}, entry.capability)
        if getattr(self.approve, "mode", None) == "revoked":
            outcome = {"result": {"status": "rejected", "reason": "Sessão revogada"}}
        else:
            try:
                handler = getattr(self, entry.handler) if isinstance(entry.handler, str) else entry.handler
                outcome = {"result": handler(**arguments) if isinstance(entry.handler, str)
                           else handler(self, **arguments)}
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
        return finish(outcome, entry.capability)

from .tool_specs import TOOL_SPECS  # Compatibilidade com importadores existentes.

# Cada ferramenta pertence a uma única capacidade. A política pode ocultar a
# capacidade no catálogo e também bloqueá-la no limite de execução.
_CAPABILITY_TOOLS = {
    "filesystem.read": {"list_files", "read_file", "verify_file", "authorized_directories"},
    "filesystem.write": {"write_file", "make_directory", "move_path", "delete_path",
                         "create_python_project"},
    "command.read": {"run_command"},
    "browser.read": {"browser_inspect"},
    "browser.control": {"browser_open", "browser_navigate", "browser_click",
                        "browser_fill", "browser_screenshot"},
    "desktop.read": {"desktop_info", "desktop_windows", "verify_app_window",
                     "focused_window", "desktop_spaces", "list_desktop_profiles",
                     "list_window_layouts", "window_action_history", "list_installed_apps",
                     "managed_processes"},
    "desktop.control": {"place_window", "close_window", "activate_workspace",
                        "move_window_to_workspace", "move_window_to_monitor",
                        "save_desktop_profile", "restore_desktop_profile", "arrange_windows",
                        "arrange_window_grid", "save_window_layout", "restore_window_layout",
                        "manage_window", "focus_window", "launch_installed_app_and_focus",
                        "open_project_and_focus", "open_file_and_focus", "open_file",
                        "open_project", "launch_installed_app", "desktop_open_app"},
    "desktop.capture": {"desktop_screenshot"},
    "desktop.input": {"desktop_input"},
}


def _build_default_registry():
    registry = ToolRegistry()
    capabilities = {}
    for capability, names in _CAPABILITY_TOOLS.items():
        for name in names:
            if name in capabilities:
                raise ValueError(f"Ferramenta em duas capacidades: {name}")
            capabilities[name] = capability
    for spec in TOOL_SPECS:
        name = spec["name"]
        if name not in capabilities:
            raise ValueError(f"Ferramenta sem capacidade: {name}")
        if not callable(getattr(Toolkit, name, None)):
            raise ValueError(f"Ferramenta sem executor: {name}")
        registry.register(spec, capabilities[name], name)
    missing = capabilities.keys() - {spec["name"] for spec in TOOL_SPECS}
    if missing:
        raise ValueError("Capacidades sem esquema: " + ", ".join(sorted(missing)))
    return registry


DEFAULT_REGISTRY = _build_default_registry()
