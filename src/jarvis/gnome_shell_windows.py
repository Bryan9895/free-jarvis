"""GNOME Shell window inventory through optional Window Calls Extended D-Bus API.

Read-only client. Never calls org.gnome.Shell.Eval or changes Shell settings.
Requires user-installed GNOME extension (not bundled or auto-installed).
"""
import ast
import json
import os
import shutil
import subprocess

DEST = "org.gnome.Shell"
OBJECT = "/org/gnome/Shell/Extensions/WindowsExt"
METHOD = "org.gnome.Shell.Extensions.WindowsExt.List"
MAX_BYTES = 100_000
MAX_WINDOWS = 150


def parse_gdbus_reply(raw):
    """Parse gdbus textual tuple with a JSON-string result, no code execution."""
    if not isinstance(raw, str) or len(raw) > MAX_BYTES:
        raise ValueError("Resposta D-Bus muito grande")
    outer = ast.literal_eval(raw.strip())
    if not isinstance(outer, tuple) or len(outer) != 1 or not isinstance(outer[0], str):
        raise ValueError("Resposta D-Bus inesperada")
    items = json.loads(outer[0])
    if not isinstance(items, list) or len(items) > MAX_WINDOWS:
        raise ValueError("Lista de janelas inválida")
    output = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Janela inválida")
        name = item.get("class") or ""
        title = item.get("title") or ""
        if not isinstance(name, str) or not isinstance(title, str):
            raise ValueError("Nome/título inválido")
        window = {"app": name[:120], "title": title[:240],
                  "source": "gnome_shell_extension"}
        if isinstance(item.get("focus"), bool):
            window["focused"] = item["focus"]
        if type(item.get("pid")) is int and item["pid"] > 0:
            window["pid"] = item["pid"]
        output.append(window)
    return output


def shell_windows():
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return {"status": "unavailable", "reason": "GNOME Wayland não detectado"}
    launcher = shutil.which("gdbus")
    if not launcher:
        return {"status": "unavailable", "reason": "gdbus indisponível"}
    try:
        proc = subprocess.run(
            [launcher, "call", "--session", "--dest", DEST,
             "--object-path", OBJECT, "--method", METHOD],
            capture_output=True, text=True, timeout=4, check=False,
        )
        if proc.returncode:
            return {"status": "unavailable",
                    "reason": "Extensão Window Calls Extended ausente/inativa ou sem resposta"}
        windows = parse_gdbus_reply(proc.stdout)
        return {"status": "observed", "source": "gnome_shell_extension",
                "complete": False, "windows": windows,
                "note": "Janelas gerenciadas pelo GNOME Shell; não inclui todas as superfícies possíveis."}
    except (OSError, ValueError, SyntaxError, MemoryError,
            subprocess.TimeoutExpired):
        return {"status": "unavailable", "reason": "Consulta D-Bus não pôde ser interpretada"}
