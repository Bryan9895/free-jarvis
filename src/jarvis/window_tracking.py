"""Compara snapshots de janelas antes/depois de iniciar um aplicativo.

Observação ≠ causalidade: uma janela preexistente não comprova um novo launch.
Nenhum método modifica o desktop nem interpreta títulos como instruções.
"""
from __future__ import annotations

import time

_APP_ALIASES = {
    "vscode": ("code", "visual studio code", "vscode"),
    "vscodium": ("codium", "vscodium"),
    "vscode-insiders": ("code - insiders", "code-insiders", "visual studio code"),
    "firefox": ("firefox",),
    "org.mozilla.firefox": ("firefox",),
    "org.gnome.nautilus": ("nautilus",),
}


def snapshot():
    from .gnome_shell_windows import shell_windows
    try:
        # Launch checks use compositor only: AT-SPI fallback may block for 6s
        # and cannot reliably match graphical application windows.
        data = shell_windows(timeout=1.5)
        if not isinstance(data, dict) or data.get("status") != "observed":
            return None
        entries = data.get("windows", [])
        if not isinstance(entries, list):
            return None
        return {"source": data.get("source", "unknown"),
                "windows": [w for w in entries if isinstance(w, dict)][:150]}
    except (OSError, RuntimeError, ValueError):
        return None


def _aliases(app):
    key = str(app).casefold().removesuffix(".desktop")
    if key in _APP_ALIASES:
        return _APP_ALIASES[key]
    # GNOME window class and desktop ID can differ; don't guess using general titles.
    tail = key.rsplit(".", 1)[-1]
    if len(tail) < 4:
        return (key,)
    return (key, tail)


def _matching(windows, app):
    names = _aliases(app)
    return [w for w in windows if any(
        token in str(w.get("app", "")).casefold() for token in names
    )]


def compare(before, after, app):
    if after is None:
        return {"status": "unavailable", "note": "Não foi possível consultar janelas após iniciar"}
    matches = _matching(after["windows"], app)
    if not matches:
        return {"status": "not_observed", "source": after["source"],
                "note": "Não observada; ausência não comprova falha da abertura"}
    if before is None:
        status = "observed_unknown_origin"
    else:
        earlier = _matching(before["windows"], app)
        fingerprints = {(w.get("app"), w.get("title"), w.get("pid")) for w in earlier}
        current = {(w.get("app"), w.get("title"), w.get("pid")) for w in matches}
        if not current - fingerprints:
            status = "already_observed"
        elif any(w.get("app") == old.get("app")
                 and w.get("pid") == old.get("pid") and w.get("pid") is not None
                 for w in matches for old in earlier):
            status = "window_changed_after_request"
        else:
            status = "appeared_after_request"
    return {"status": status, "source": after["source"],
            "windows_observed": len(matches),
            "focused": any(w.get("focused") is True for w in matches),
            "note": "Observação de janela não comprova que a solicitação criou nova instância "
                    "ou abriu o arquivo pretendido."}


def observe_launch(launch, app, before, *, attempts=2, interval=0.35):
    """Não converte falhas de observação em falhas de execução."""
    if not isinstance(launch, dict) or launch.get("status") != "launched_unverified":
        return launch
    after = snapshot()
    assessment = compare(before, after, app)
    for _ in range(max(0, attempts - 1)):
        if assessment["status"] != "not_observed":
            break
        time.sleep(interval)
        assessment = compare(before, snapshot(), app)
    return {**launch, "window_observation": assessment}
