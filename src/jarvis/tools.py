"""Ferramentas locais com permissões explícitas, sem shell e workspace restrito."""
import os
import sqlite3
from pathlib import Path
import subprocess
import time
from collections import deque
from urllib.parse import urlparse
from .registry import CapabilityPolicy, ToolRegistry
from .schema_validation import validate_arguments
from .cancellation import CancelledError
from .filesystem_tools import FilesystemTools, ToolError, MAX_FILE_BYTES
from .command_execution import CommandTools

class Toolkit(FilesystemTools, CommandTools):
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
        self._execution_token = None
        roots = []
        for value in os.getenv("JARVIS_ALLOWED_DIRS", "").split(os.pathsep):
            if value.strip():
                root = Path(value.strip()).expanduser().resolve()
                if root.is_dir() and root != Path.home().resolve() and root != Path("/"):
                    roots.append(root)
        self._allowed_roots = [self.workspace] + [p for p in roots if p != self.workspace]

    @property
    def allowed_roots(self):
        roots = list(self._allowed_roots)
        store = getattr(self.approve, 'authorizations', None)
        if store is not None and self.approve.granted('files'):
            roots.extend(Path(p) for p in store.snapshot().roots)
        return list(dict.fromkeys(roots))

    @allowed_roots.setter
    def allowed_roots(self, roots):
        self._allowed_roots = list(roots)

    def task_list(self, status=None):
        from .task_board import TaskBoard
        return TaskBoard(self.layout_db).list(status)

    def task_add(self, title, priority=2):
        from .task_board import TaskBoard
        if not self.approve(f"ADICIONAR tarefa: {title}"):
            return {"status": "rejected"}
        return TaskBoard(self.layout_db).add(title, priority)

    def task_update(self, task_id, status):
        from .task_board import TaskBoard
        if not self.approve(f"ALTERAR tarefa #{task_id} para {status}"):
            return {"status": "rejected"}
        return TaskBoard(self.layout_db).update(task_id, status)

    def browser_tabs(self):
        return self._browser_client().perform("tabs")

    def browser_new_tab(self, url):
        from .browser_worker import validate_url
        validate_url(url)
        if not self.approve(f"ABRIR ABA no Chromium gerenciado: {url}"):
            return {"status": "rejected"}
        return self._browser_client().perform("new_tab", url=url)

    def browser_select_tab(self, tab_id):
        if not self.approve(f"SELECIONAR ABA #{tab_id} no Chromium gerenciado"):
            return {"status": "rejected"}
        return self._browser_client().perform("select_tab", tab_id=tab_id)

    def browser_close_tab(self, tab_id):
        confirmation = getattr(self.approve, "confirm_sensitive", self.approve)
        if not confirmation(f"FECHAR ABA #{tab_id}? Dados não salvos podem ser perdidos."):
            return {"status": "rejected"}
        return self._browser_client().perform("close_tab", tab_id=tab_id)

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

    def execute(self, name, arguments, cancel_token=None):
        from .latency import mark
        mark('tool_start')
        started = time.monotonic()
        def finish(outcome, capability=None):
            mark('tool_end')
            detail = outcome.get("result") if isinstance(outcome, dict) else None
            status = "error" if "error" in outcome else (
                detail.get("status", "ok") if isinstance(detail, dict) else "ok")
            self.operation_log.append({"tool": name, "capability": capability,
                                       "status": status,
                                       "duration_ms": round((time.monotonic() - started) * 1000, 2)})
            return outcome

        entry = self.registry.get(name)
        if cancel_token is not None:
            cancel_token.check()
        if entry is None:
            return finish({"error": "Ferramenta desconhecida"})
        if not self.capabilities.permits(entry):
            return finish({"error": "Capacidade não autorizada: " + entry.capability},
                          entry.capability)
        if name == "desktop_input" and os.getenv("JARVIS_ENABLE_DESKTOP_INPUT") != "1":
            return finish({"error": "Entrada gráfica desativada"}, entry.capability)
        if not isinstance(arguments, dict):
            return finish({"error": "Argumentos devem formar um objeto JSON"}, entry.capability)
        try:
            validate_arguments(entry.spec["parameters"], arguments)
        except ValueError as exc:
            return finish({"error": str(exc)}, entry.capability)
        if getattr(self.approve, "mode", None) == "revoked":
            outcome = {"result": {"status": "rejected", "reason": "Sessão revogada"}}
        else:
            try:
                if cancel_token is not None:
                    cancel_token.check()
                handler = getattr(self, entry.handler) if isinstance(entry.handler, str) else entry.handler
                previous_token, self._execution_token = self._execution_token, cancel_token
                try:
                    from .approval import action_category
                    with action_category(entry.capability):
                        outcome = {"result": handler(**arguments) if isinstance(entry.handler, str)
                                   else handler(self, **arguments)}
                finally:
                    self._execution_token = previous_token
            except CancelledError:
                raise
            except (TimeoutError, subprocess.TimeoutExpired) as exc:
                outcome = {'result': {'status': 'execution_uncertain', 'reason': str(exc)}}
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
    "tasks.read": {"task_list"},
    "tasks.write": {"task_add", "task_update"},
    "command.read": {"run_command"},
    "command.execute": {"execute_process"},
    "system.admin": {"manage_packages", "manage_service"},
    "browser.read": {"browser_inspect", "browser_tabs"},
    "browser.control": {"browser_open", "browser_navigate", "browser_click",
                        "browser_fill", "browser_screenshot", "browser_new_tab",
                        "browser_select_tab", "browser_close_tab"},
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
