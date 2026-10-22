"""Movimento verificado de uma janela entre monitores GNOME Wayland."""
import time

from .desktop_spaces import _monitors
from .window_layout import _identity_ok, _select
from .window_manage import _inventory, EXTENSION_URL
from .workspace_control import _sent


def _topology(monitors):
    """Campos que identificam o destino sem depender do dock/área útil."""
    return sorted((item["index"], item["x"], item["y"], item["width"],
                   item["height"], item["scale"], item["connector"])
                  for item in monitors)


def move_window_to_monitor(app, approve, monitor_number=None, title="", *,
                           retries=4, delay=0.2):
    """Move uma janela inequívoca e confirma monitor_index no inventário."""
    if (not isinstance(app, str) or not 2 <= len(app) <= 100
            or any(c in app for c in ("\n", "\r", "\x00"))
            or not isinstance(title, str) or len(title) > 200
            or any(c in title for c in ("\n", "\r", "\x00"))):
        raise ValueError("Nome ou título de janela inválido")
    if monitor_number is not None and (type(monitor_number) is not int
                                       or not 1 <= monitor_number <= 65):
        raise ValueError("Número do monitor deve ser inteiro entre 1 e 65")
    before = _inventory()
    monitors = _monitors()
    if before is None or monitors is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    chosen, error = _select(before, app, title)
    if error:
        return {"status": error}
    source = chosen.get("monitor")
    indices = {item["index"] for item in monitors}
    if type(source) is not int or source not in indices:
        return {"status": "unavailable", "reason": "Monitor atual da janela desconhecido"}
    if monitor_number is None:
        others = indices - {source}
        if len(others) == 0:
            return {"status": "not_found", "reason": "Outro monitor não está conectado"}
        if len(others) != 1:
            return {"status": "ambiguous", "reason": "Informe o número do monitor de destino"}
        target = next(iter(others))
        monitor_number = target + 1
    else:
        target = monitor_number - 1
        if target not in indices:
            return {"status": "not_found", "reason": "Monitor de destino não encontrado"}
    if source == target:
        return {"status": "already_in_state", "app": chosen["app"],
                "title": chosen["title"], "monitor_number": monitor_number}
    if not approve(f"MOVER JANELA {chosen['app']} — {chosen['title']} "
                   f"PARA MONITOR {monitor_number}?"):
        return {"status": "rejected"}
    current = _inventory()
    current_monitors = _monitors()
    if current_monitors is None or _topology(current_monitors) != _topology(monitors):
        return {"status": "changed", "reason": "Monitores mudaram durante a autorização"}
    if current is None:
        return {"status": "unavailable", "reason": "Inventário de janelas indisponível"}
    again, error = _select(current, app, title)
    if error or not _identity_ok(chosen, again) or again.get("monitor") != source:
        return {"status": "changed", "reason": "Janela mudou antes da operação"}
    sent = _sent("MoveToMonitor", chosen["id"], target)
    if sent != "sent":
        return {"status": sent}
    for attempt in range(max(1, min(retries, 6))):
        if attempt:
            time.sleep(delay)
        after = _inventory()
        after_monitors = _monitors()
        if after is None or after_monitors is None:
            continue
        if _topology(after_monitors) != _topology(monitors):
            return {"status": "window_monitor_unverified", "monitor_number": monitor_number,
                    "reason": "Disposição dos monitores mudou após a solicitação"}
        matches = [row for row in after if _identity_ok(chosen, row)]
        if len(matches) == 1 and matches[0].get("monitor") == target:
            return {"status": "window_monitor_verified", "app": chosen["app"],
                    "title": chosen["title"], "monitor_number": monitor_number}
    return {"status": "window_monitor_unverified", "monitor_number": monitor_number,
            "reason": "Movimento enviado, mas o monitor da janela não foi confirmado"}
