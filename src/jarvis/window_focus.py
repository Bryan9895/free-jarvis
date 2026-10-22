"""Ativação supervisionada de uma única janela GNOME Wayland.

Requer Window Calls Extended para inventário e Activate Window By Title
para solicitar foco. Nunca usa org.gnome.Shell.Eval, comandos livres ou X11.
"""
import shutil
import subprocess
import time

from .gnome_shell_windows import shell_windows

DBUS_DEST = "org.gnome.Shell"
ACTIVATE_PATH = "/de/lucaswerkmeister/ActivateWindowByTitle"
ACTIVATE_METHOD = "de.lucaswerkmeister.ActivateWindowByTitle.activateByTitle"


def _visible_windows():
    inventory = shell_windows()
    if inventory.get("status") != "observed" or inventory.get("source") != "gnome_shell_extension":
        return None
    return inventory.get("windows", [])


def _match(windows, app, title):
    a = app.casefold().strip()
    t = title.casefold().strip()
    return [w for w in windows
            if isinstance(w, dict)
            and a in str(w.get("app", "")).casefold()
            and (not t or t in str(w.get("title", "")).casefold())]


def focus_window(app, title, approve, *, retries=3, delay=0.25):
    """Seleciona apenas títulos únicos, confirma e verifica foco por inventário."""
    if not isinstance(app, str) or not 2 <= len(app) <= 100 or any(
            x in app for x in ("\n", "\r", "\x00")):
        raise ValueError("Nome de aplicativo inválido")
    if not isinstance(title, str) or len(title) > 200 or any(
            x in title for x in ("\n", "\r", "\x00")):
        raise ValueError("Título inválido")
    before = _visible_windows()
    if before is None:
        return {"status": "unavailable", "reason": "Extensão Window Calls Extended não responde"}
    candidates = _match(before, app, title)
    if not candidates:
        return {"status": "not_observed", "reason": "Nenhuma janela correspondente foi identificada"}
    if len(candidates) != 1:
        return {"status": "ambiguous", "matches": len(candidates),
                "reason": "Há várias janelas correspondentes; informe mais detalhes do título"}
    chosen = candidates[0]
    exact_title = chosen.get("title")
    if not isinstance(exact_title, str) or not exact_title:
        return {"status": "ambiguous", "reason": "Janela sem título identificável"}
    # A API de ativação escolhe a primeira janela com título exato.
    if sum(1 for w in before if w.get("title") == exact_title) != 1:
        return {"status": "ambiguous", "reason": "Título idêntico em mais de uma janela"}
    if chosen.get("focused") is True:
        return {"status": "already_focused", "app": chosen.get("app"),
                "title": exact_title, "pid": chosen.get("pid")}
    executable = shutil.which("gdbus")
    if not executable:
        return {"status": "unavailable", "reason": "gdbus não instalado"}
    if not approve("COLOCAR JANELA EM PRIMEIRO PLANO: "
                   + str(chosen.get("app")) + " — " + exact_title + "?"):
        return {"status": "rejected"}
    # Revalidação depois da aprovação: janela e título podem ter mudado.
    current = _visible_windows()
    if current is None:
        return {"status": "unavailable", "reason": "Inventário indisponível após autorização"}
    if _match(current, app, title) != candidates or sum(
            1 for w in current if w.get("title") == exact_title) != 1:
        return {"status": "changed", "reason": "O conjunto de janelas mudou; repita a operação"}
    try:
        result = subprocess.run(
            [executable, "call", "--session", "--dest", DBUS_DEST,
             "--object-path", ACTIVATE_PATH, "--method", ACTIVATE_METHOD,
             exact_title],
            capture_output=True, text=True, timeout=4, check=False)
        if result.returncode:
            return {"status": "unavailable",
                    "reason": "Activate Window By Title ausente, desabilitada ou sem resposta"}
        reply = result.stdout.strip().lower()
        if reply not in ("(true,)", "(false,)"):
            return {"status": "unverified", "reason": "Resposta inesperada da extensão"}
        if reply == "(false,)":
            return {"status": "not_activated", "reason": "Extensão não encontrou a janela"}
    except (OSError, ValueError, SyntaxError, MemoryError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "reason": "Falha ao consultar a extensão de ativação"}
    for attempt in range(max(1, min(retries, 5))):
        if attempt:
            time.sleep(delay)
        after = _visible_windows()
        if after is None:
            continue
        matching = [w for w in after if w.get("title") == exact_title
                    and w.get("app") == chosen.get("app")
                    and w.get("pid") == chosen.get("pid")]
        if len(matching) == 1 and matching[0].get("focused") is True:
            return {"status": "focused_verified", "app": chosen.get("app"),
                    "title": exact_title, "pid": chosen.get("pid")}
    return {"status": "focus_unverified",
            "reason": "Comando aceito, mas foco não confirmado no GNOME Shell"}
