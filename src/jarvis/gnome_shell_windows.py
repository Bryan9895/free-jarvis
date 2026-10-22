"""GNOME Shell window inventory through optional Window Calls Extended D-Bus API.

Read-only client. Never calls org.gnome.Shell.Eval or changes Shell settings.
Requires user-installed GNOME extension (not bundled or auto-installed).
"""
import ast
import json
import os
import shutil
import subprocess
from pathlib import Path

DEST = "org.gnome.Shell"
OBJECT = "/org/gnome/Shell/Extensions/WindowsExt"
METHOD = "org.gnome.Shell.Extensions.WindowsExt.List"
MAX_BYTES = 100_000
MAX_WINDOWS = 150
EXT_UUID = "window-calls-extended@hseliger.eu"


def extension_diagnostic():
    """Read-only diagnostic of GNOME extension installation and activation."""
    folder = Path.home() / ".local/share/gnome-shell/extensions" / EXT_UUID
    status = {"uuid": EXT_UUID, "directory_exists": folder.is_dir(),
              "metadata_exists": (folder / "metadata.json").is_file()}
    cli = shutil.which("gnome-extensions")
    if cli:
        try:
            result = subprocess.run([cli, "info", EXT_UUID], capture_output=True,
                                    text=True, timeout=3, check=False)
            status["gnome_extensions_recognizes_it"] = result.returncode == 0
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip().lower().startswith("state:"):
                        status["state"] = line.split(":", 1)[1].strip()[:80]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return status



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
                    "reason": "Interface D-Bus da extensão não responde",
                    "extension": extension_diagnostic()}
        windows = parse_gdbus_reply(proc.stdout)
        return {"status": "observed", "source": "gnome_shell_extension",
                "complete": False, "windows": windows,
                "note": "Janelas gerenciadas pelo GNOME Shell; não inclui todas as superfícies possíveis."}
    except (OSError, ValueError, SyntaxError, MemoryError,
            subprocess.TimeoutExpired):
        return {"status": "unavailable", "reason": "Consulta D-Bus não pôde ser interpretada"}
