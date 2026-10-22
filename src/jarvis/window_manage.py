"""Controle de estado de janelas GNOME Wayland via Window Control opcional.

A extensão deve ser instalada pelo usuário. Seleção exata por ID, classe e
título; nenhuma chamada ao Shell.Eval nem fallback para atalhos cegos.
"""
import ast
import json
import os
import shutil
import subprocess
import time

from .window_focus import _match

DEST = "org.gnome.Shell"
OBJECT = "/org/gnome/Shell/Extensions/WindowControl"
METHOD = "org.gnome.Shell.Extensions.WindowControl"
EXTENSION_URL = "https://extensions.gnome.org/extension/10886/window-control/"
ACTIONS = {
    "minimize": ("Minimize", "is_minimized", True),
    "restore": ("Unminimize", "is_minimized", False),
    "maximize": ("Maximize", "is_maximized", True),
    "unmaximize": ("Unmaximize", "is_maximized", False),
}


def _dbus(method, *args, timeout=3):
    if os.getenv("XDG_SESSION_TYPE", "").casefold() != "wayland":
        return None
    executable = shutil.which("gdbus")
    if not executable:
        return None
    try:
        return subprocess.run(
            [executable, "call", "--session", "--dest", DEST,
             "--object-path", OBJECT, "--method", METHOD + "." + method,
             *[str(arg) for arg in args]],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _inventory():
    """Lista estados detalhados, com limites e validação da resposta D-Bus."""
    proc = _dbus("ListDetailed")
    if proc is None or proc.returncode:
        return None
    if len(proc.stdout) > 120_000:
        return None
    try:
        reply = ast.literal_eval(proc.stdout.strip())
        if not isinstance(reply, tuple) or len(reply) != 1 or not isinstance(reply[0], str):
            return None
        rows = json.loads(reply[0])
        if not isinstance(rows, list) or len(rows) > 150:
            return None
        result = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            ident = row.get("id")
            title = row.get("title")
            app = row.get("wm_class")
            if (type(ident) is not int or not 0 < ident < 2**64
                    or not isinstance(title, str) or not isinstance(app, str)
                    or len(title) > 240 or len(app) > 120):
                return None
            result.append({**row, "app": app, "title": title})
        return result
    except (ValueError, SyntaxError, TypeError, MemoryError):
        return None


def manage_window(app, title, action, approve, *, retries=3, delay=0.2):
    """Executa operação e confirma o estado pelo compositor.

    Não aceita IDs fornecidos pelo modelo. Deriva o ID do inventário, revalida
    após a aprovação e exige uma janela única.
    """
    if action not in ACTIONS:
        raise ValueError("Ação de janela inválida")
    if not isinstance(app, str) or not 2 <= len(app) <= 100 or any(
            c in app for c in ("\n", "\r", "\x00")):
        raise ValueError("Nome de aplicativo inválido")
    if not isinstance(title, str) or len(title) > 200 or any(
            c in title for c in ("\n", "\r", "\x00")):
        raise ValueError("Título inválido")
    before = _inventory()
    if before is None:
        return {"status": "unavailable", "reason": "Extensão Window Control indisponível",
                "install_url": EXTENSION_URL}
    selected = _match(before, app, title)
    if not selected:
        return {"status": "not_observed", "reason": "Nenhuma janela correspondente"}
    if len(selected) != 1:
        return {"status": "ambiguous", "matches": len(selected)}
    chosen = selected[0]
    method, flag, target = ACTIONS[action]
    if chosen.get(flag) is target:
        return {"status": "already_in_state", "action": action,
                "app": chosen["app"], "title": chosen["title"]}
    if not approve(f"{method.upper()} JANELA: {chosen['app']} — {chosen['title']}?"):
        return {"status": "rejected"}
    current = _inventory()
    if current is None:
        return {"status": "unavailable", "reason": "Inventário indisponível após autorização"}
    current_match = [w for w in current if w["id"] == chosen["id"]]
    if (len(current_match) != 1
            or current_match[0]["app"] != chosen["app"]
            or current_match[0]["title"] != chosen["title"]
            or current_match[0].get("pid") != chosen.get("pid")
            or len(_match(current, app, title)) != 1):
        return {"status": "changed", "reason": "Janela mudou antes da operação"}
    proc = _dbus(method, chosen["id"])
    if proc is None or proc.returncode:
        return {"status": "unavailable", "reason": "Controle D-Bus não respondeu"}
    reply = proc.stdout.strip().lower()
    if reply == "(false,)":
        return {"status": "not_activated", "action": action}
    if reply != "(true,)":
        return {"status": "unverified", "reason": "Resposta desconhecida da extensão"}
    for attempt in range(max(1, min(retries, 5))):
        if attempt:
            time.sleep(delay)
        after = _inventory()
        if after is None:
            continue
        same = [w for w in after if w["id"] == chosen["id"]
                and w["app"] == chosen["app"]
                and w.get("pid") == chosen.get("pid")]
        if len(same) == 1 and same[0].get(flag) is target:
            return {"status": "state_verified", "action": action,
                    "app": chosen["app"], "title": chosen["title"]}
    return {"status": "state_unverified", "action": action,
            "reason": "Operação solicitada, estado final não confirmado pelo GNOME"}
