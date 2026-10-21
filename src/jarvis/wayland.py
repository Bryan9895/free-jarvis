"""Wayland: diagnósticos e captura via portal XDG com diálogo de consentimento.

Não utiliza xdotool, /dev/uinput ou bypass do compositor.
"""
from __future__ import annotations
import asyncio
import os
import re
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
    """Portal Screenshot sem introspecção XML de outras interfaces do GNOME.

    GNOME pode anunciar propriedades fora do padrão aceito pelo parser
    dbus-next (por exemplo power-saver-enabled). Usamos chamadas D-Bus diretas.
    """
    try:
        from dbus_next.aio import MessageBus
        from dbus_next import Message, MessageType, Variant
    except ImportError as exc:
        raise WaylandError("Instale: pip install -e '.[desktop]'") from exc
    import secrets
    bus = await MessageBus().connect()
    loop = asyncio.get_running_loop()
    pending = loop.create_future()
    expected_path = None

    def on_message(message):
        if (message.message_type == MessageType.SIGNAL
                and message.interface == "org.freedesktop.portal.Request"
                and message.member == "Response"
                and len(message.body) == 2):
            if not pending.done():
                pending.set_result((message.path, message.body[0], message.body[1]))

    bus.add_message_handler(on_message)
    match_rule = "type='signal',interface='org.freedesktop.portal.Request',member='Response'"
    try:
        result = await bus.call(Message(
            destination="org.freedesktop.DBus",
            path="/org/freedesktop/DBus", interface="org.freedesktop.DBus",
            member="AddMatch", signature="s", body=[match_rule]))
        if result.message_type == MessageType.ERROR:
            raise WaylandError("Não foi possível acompanhar resposta do portal: " + str(result.body))
        token = "jarvis_" + secrets.token_hex(8)
        call = await bus.call(Message(
            destination=PORTAL_NAME, path=PORTAL_PATH,
            interface="org.freedesktop.portal.Screenshot", member="Screenshot",
            signature="sa{sv}", body=["", {"interactive": Variant("b", True),
                                          "handle_token": Variant("s", token)}]))
        if call.message_type == MessageType.ERROR:
            raise WaylandError("Falha ao solicitar captura: " + str(call.body))
        expected_path = call.body[0]
        try:
            path, code, result = await asyncio.wait_for(pending, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise WaylandError("Tempo limite aguardando autorização do GNOME") from exc
        if path != expected_path:
            raise WaylandError("Resposta do portal não corresponde à solicitação")
        if code != 0:
            raise WaylandError("Captura cancelada ou negada pelo usuário")
        uri = result.get("uri")
        if uri is None:
            raise WaylandError("O portal não retornou imagem")
        return uri.value
    finally:
        bus.remove_message_handler(on_message)
        try:
            await bus.call(Message(destination="org.freedesktop.DBus",
                                   path="/org/freedesktop/DBus", interface="org.freedesktop.DBus",
                                   member="RemoveMatch", signature="s", body=[match_rule]))
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

def open_app(app_id, approve):
    """Abre somente IDs .desktop explicitamente permitidos em JARVIS_ALLOWED_APPS."""
    allowed = {item.strip() for item in os.getenv("JARVIS_ALLOWED_APPS", "").split(",") if item.strip()}
    if not isinstance(app_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", app_id):
        raise WaylandError("Identificador de aplicativo inválido")
    if app_id not in allowed:
        raise WaylandError("Aplicativo não está em JARVIS_ALLOWED_APPS")
    launcher = shutil.which("gtk-launch")
    if not launcher:
        raise WaylandError("gtk-launch não está instalado (pacote libgtk-3-bin)")
    if not approve(f"ABRIR aplicativo gráfico autorizado: {app_id}"):
        return {"status": "rejected"}
    try:
        process = subprocess.Popen([launcher, app_id], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
    except OSError as exc:
        raise WaylandError(f"Falha ao abrir aplicativo: {exc}") from exc
    return {"status": "launched_unverified", "app_id": app_id, "pid": process.pid}
