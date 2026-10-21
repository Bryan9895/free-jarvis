"""Wayland: diagnósticos e captura via portal XDG com diálogo de consentimento.

Não utiliza xdotool, /dev/uinput ou bypass do compositor.
"""
from __future__ import annotations
import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"

class WaylandError(RuntimeError):
    pass

def desktop_info():
    session = os.getenv("XDG_SESSION_TYPE", "").lower()
    desktop = os.getenv("XDG_CURRENT_DESKTOP", "desconhecido")
    available = bool(shutil.which("gdbus"))
    status = {"session": session or "desconhecida", "desktop": desktop,
              "gdbus_installed": available, "portal_detected": False}
    if available and os.getenv("DBUS_SESSION_BUS_ADDRESS"):
        try:
            res = subprocess.run(
                ["gdbus", "introspect", "--session", "--dest", PORTAL_NAME, "--object-path", PORTAL_PATH],
                capture_output=True, text=True, timeout=4, check=False)
            status["portal_detected"] = res.returncode == 0
            status["screenshot_available"] = "org.freedesktop.portal.Screenshot" in res.stdout
            status["remote_desktop_available"] = "org.freedesktop.portal.RemoteDesktop" in res.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    if session != "wayland":
        status["note"] = "A etapa 5 foi projetada para Wayland."
    else:
        status["note"] = "Capturas dependem da confirmação na janela do portal. Controle do mouse/teclado ainda não ativado."
    return status

def _source_path(uri):
    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        raise WaylandError("O portal não retornou um arquivo local")
    path = Path(unquote(parsed.path)).resolve()
    if not path.is_file():
        raise WaylandError("Arquivo retornado pelo portal não existe")
    return path

async def _request_screenshot(timeout=60):
    try:
        from dbus_next.aio import MessageBus
        from dbus_next import Variant
    except ImportError as exc:
        raise WaylandError("Instale: pip install -e '.[desktop]'") from exc
    bus = await MessageBus().connect()
    try:
        node = await bus.introspect(PORTAL_NAME, PORTAL_PATH)
        obj = bus.get_proxy_object(PORTAL_NAME, PORTAL_PATH, node)
        interface = obj.get_interface("org.freedesktop.portal.Screenshot")
        # Subscribe as soon as request handle exists. A future signal is awaited
        # through DBus instead of reading the terminal or scraping screen pixels.
        handle = await interface.call_screenshot("", {"interactive": Variant("b", True)})
        request_node = await bus.introspect(PORTAL_NAME, handle)
        request_obj = bus.get_proxy_object(PORTAL_NAME, handle, request_node)
        request = request_obj.get_interface("org.freedesktop.portal.Request")
        loop = asyncio.get_running_loop()
        response = loop.create_future()
        def callback(code, results):
            if not response.done():
                response.set_result((code, results))
        request.on_response(callback)
        try:
            code, results = await asyncio.wait_for(response, timeout=timeout)
        finally:
            request.off_response(callback)
        if code != 0:
            raise WaylandError("Captura cancelada ou negada pelo usuário")
        uri = results.get("uri")
        if uri is None:
            raise WaylandError("O portal não retornou imagem")
        return uri.value
    finally:
        bus.disconnect()

def screenshot(workspace: Path, approve, timeout=60):
    if os.getenv("XDG_SESSION_TYPE", "").lower() != "wayland":
        raise WaylandError("A sessão atual não é Wayland")
    if not approve("CAPTURAR A TELA via diálogo do portal Wayland? A imagem pode conter dados privados."):
        return {"status": "rejected"}
    uri = asyncio.run(_request_screenshot(timeout=timeout))
    src = _source_path(uri)
    root = workspace.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    dest = root / "jarvis_desktop_screenshot.png"
    if src != dest:
        shutil.copyfile(src, dest)
    return {"status": "saved", "path": str(dest), "requires_user_portal_consent": True}
