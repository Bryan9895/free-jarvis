"""Controle verificado de áreas de trabalho GNOME via Window Control."""
import time

from .desktop_spaces import _workspaces
from .window_layout import _identity_ok, _select
from .window_manage import _dbus, _inventory, EXTENSION_URL


def _target(number, workspaces):
    if type(number) is not int or not 1 <= number <= 64:
        raise ValueError("Número da área deve ser inteiro entre 1 e 64")
    index = number - 1
    if workspaces is None:
        return None, {"status": "unavailable", "install_url": EXTENSION_URL}
    if index not in {row["index"] for row in workspaces}:
        return None, {"status": "not_found", "reason": "Área de trabalho inexistente"}
    return index, None


def _sent(method, *args):
    response = _dbus(method, *args)
    if response is None or response.returncode:
        return "unavailable"
    reply = response.stdout.strip().lower()
    if reply == "(true,)":
        return "sent"
    if reply == "(false,)":
        return "refused"
    return "unverified"


def activate_workspace(workspace_number, approve, *, retries=4, delay=0.2):
    """Alterna para área existente e confirma qual está ativa no compositor."""
    before = _workspaces()
    index, error = _target(workspace_number, before)
    if error:
        return error
    active = next(row["index"] for row in before if row["is_active"])
    if index == active:
        return {"status": "already_in_state", "workspace_number": workspace_number}
    if not approve(f"ATIVAR ÁREA DE TRABALHO {workspace_number}?"):
        return {"status": "rejected"}
    current = _workspaces()
    if (current is None or index not in {row["index"] for row in current}
            or next(row["index"] for row in current if row["is_active"]) != active):
        return {"status": "changed", "reason": "Áreas de trabalho mudaram durante a autorização"}
    sent = _sent("ActivateWorkspace", index)
    if sent != "sent":
        return {"status": sent}
    for attempt in range(max(1, min(retries, 6))):
        if attempt:
            time.sleep(delay)
        after = _workspaces()
        if after is not None and any(
                row["index"] == index and row["is_active"] for row in after):
            return {"status": "workspace_verified", "workspace_number": workspace_number}
    return {"status": "workspace_unverified", "workspace_number": workspace_number,
            "reason": "Alternância enviada, mas a área ativa não foi confirmada"}


def move_window_to_workspace(app, workspace_number, approve, title="", *,
                             retries=4, delay=0.2):
    """Move uma única janela identificada e confirma seu workspace_index."""
    if (not isinstance(app, str) or not 2 <= len(app) <= 100
            or any(c in app for c in ("\n", "\r", "\x00"))
            or not isinstance(title, str) or len(title) > 200
            or any(c in title for c in ("\n", "\r", "\x00"))):
        raise ValueError("Nome ou título de janela inválido")
    spaces = _workspaces()
    index, error = _target(workspace_number, spaces)
    if error:
        return error
    before = _inventory()
    if before is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    chosen, error = _select(before, app, title)
    if error:
        return {"status": error}
    if chosen.get("is_on_all_workspaces") is True:
        return {"status": "refused", "reason": "Janela fixa em todas as áreas de trabalho"}
    old_index = chosen.get("workspace_index")
    if type(old_index) is not int or old_index < 0:
        return {"status": "unavailable", "reason": "Área atual da janela desconhecida"}
    if old_index == index:
        return {"status": "already_in_state", "app": chosen["app"],
                "title": chosen["title"], "workspace_number": workspace_number}
    if not approve(f"MOVER JANELA {chosen['app']} — {chosen['title']} "
                   f"PARA ÁREA DE TRABALHO {workspace_number}?"):
        return {"status": "rejected"}
    current_spaces = _workspaces()
    current = _inventory()
    if current_spaces is None or index not in {row["index"] for row in current_spaces}:
        return {"status": "changed", "reason": "Área de destino mudou"}
    if current is None:
        return {"status": "unavailable", "reason": "Inventário de janelas indisponível"}
    again, error = _select(current, app, title)
    if (error or not _identity_ok(chosen, again)
            or again.get("workspace_index") != old_index
            or again.get("is_on_all_workspaces") is True):
        return {"status": "changed", "reason": "Janela mudou antes da operação"}
    sent = _sent("MoveToWorkspace", chosen["id"], index)
    if sent != "sent":
        return {"status": sent}
    for attempt in range(max(1, min(retries, 6))):
        if attempt:
            time.sleep(delay)
        rows = _inventory()
        if rows is None:
            continue
        matches = [row for row in rows if _identity_ok(chosen, row)]
        if (len(matches) == 1 and matches[0].get("workspace_index") == index
                and matches[0].get("is_on_all_workspaces") is not True):
            return {"status": "window_workspace_verified", "app": chosen["app"],
                    "title": chosen["title"], "workspace_number": workspace_number}
    return {"status": "window_workspace_unverified", "workspace_number": workspace_number,
            "reason": "Movimento enviado, mas a área da janela não foi confirmada"}
