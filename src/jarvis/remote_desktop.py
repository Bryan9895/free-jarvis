"""Experimental Wayland RemoteDesktop permissioned session.

Uses only XDG Desktop Portal direct D-Bus calls (no X11, uinput or privileged access).
No persistent permissions. The caller must explicitly consent before an input event.
"""
from __future__ import annotations

import asyncio
import secrets

from .wayland import PORTAL_NAME, PORTAL_PATH, WaylandError

INTERFACE = "org.freedesktop.portal.RemoteDesktop"
POINTER = 2
KEYBOARD = 1
LEFT_BUTTON = 0x110
RELEASED = 0
PRESSED = 1


def _result_value(results, key):
    value = results.get(key)
    return value.value if hasattr(value, "value") else value


class RemoteDesktop:
    def __init__(self):
        self.bus = None
        self.session = None
        self.devices = 0
        self.requested_types = POINTER

    async def connect(self):
        try:
            from dbus_next.aio import MessageBus
        except ImportError as exc:
            raise WaylandError("Instale a dependência desktop: pip install -e '.[desktop]'") from exc
        self.bus = await MessageBus().connect()
        return self

    async def _call(self, interface, member, signature="", body=None, path=PORTAL_PATH):
        from dbus_next import Message, MessageType
        message = await self.bus.call(Message(
            destination=PORTAL_NAME, path=path, interface=interface,
            member=member, signature=signature, body=body or []))
        if message is None or message.message_type == MessageType.ERROR:
            raise WaylandError("Falha no portal RemoteDesktop: " + str(getattr(message, "body", []))[:250])
        return message

    async def _request(self, member, signature, body, timeout=60):
        from dbus_next import Variant, MessageType
        token = "jarvis_" + secrets.token_hex(8)
        options = {"handle_token": Variant("s", token)}
        if member == "CreateSession":
            options["session_handle_token"] = Variant("s", "session_" + secrets.token_hex(8))
        if member == "SelectDevices":
            options["types"] = Variant("u", self.requested_types)
            options["persist_mode"] = Variant("u", 0)
        params = ([options] if member == "CreateSession" else [self.session, options]
                  if member == "SelectDevices" else [self.session, "", options])
        match = "type='signal',interface='org.freedesktop.portal.Request',member='Response'"
        loop = asyncio.get_running_loop()
        done = loop.create_future()
        expected = None
        def handler(message):
            if (message.message_type == MessageType.SIGNAL
                    and message.interface == "org.freedesktop.portal.Request"
                    and message.member == "Response" and len(message.body) == 2
                    and message.path is not None
                    and message.path.endswith("/" + token)
                    and not done.done()):
                done.set_result((message.path, message.body[0], message.body[1]))
        self.bus.add_message_handler(handler)
        try:
            from dbus_next import Message
            from dbus_next import MessageType as MT
            add = await self.bus.call(Message(destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus", interface="org.freedesktop.DBus",
                    member="AddMatch", signature="s", body=[match]))
            if add.message_type == MT.ERROR:
                raise WaylandError("Não foi possível assinar sinais de permissão")
            response = await self._call(INTERFACE, member, signature, params)
            expected = response.body[0]
            try:
                path, status, result = await asyncio.wait_for(done, timeout)
            except asyncio.TimeoutError as exc:
                raise WaylandError("Tempo limite ou diálogo do GNOME não respondido") from exc
            if path != expected or status != 0:
                raise WaylandError("Permissão RemoteDesktop negada ou cancelada")
            return result
        finally:
            self.bus.remove_message_handler(handler)
            from dbus_next import Message
            try:
                await self.bus.call(Message(destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus", interface="org.freedesktop.DBus",
                    member="RemoveMatch", signature="s", body=[match]))
            except Exception:
                pass

    async def start(self, requested_types=POINTER):
        if requested_types not in (POINTER, KEYBOARD):
            raise WaylandError("Tipo de dispositivo inválido")
        self.requested_types = requested_types
        if self.bus is None:
            await self.connect()
        try:
            created = await self._request("CreateSession", "a{sv}", [])
            self.session = _result_value(created, "session_handle")
            if not self.session:
                raise WaylandError("Portal não retornou identificador de sessão")
            await self._request("SelectDevices", "oa{sv}", [])
            result = await self._request("Start", "osa{sv}", [])
            self.devices = int(_result_value(result, "devices") or 0)
            if not self.devices & requested_types:
                raise WaylandError("Permissão do dispositivo não concedida")
            return {"status": "authorized", "pointer": bool(self.devices & POINTER), "keyboard": bool(self.devices & KEYBOARD)}
        except Exception:
            await self.close()
            raise

    async def move(self, dx: float, dy: float):
        if not self.session or not self.devices & POINTER:
            raise WaylandError("Sessão sem permissão de ponteiro")
        if abs(dx) > 50 or abs(dy) > 50:
            raise WaylandError("Movimento de teste limitado a 50 pixels por eixo")
        await self._call(INTERFACE, "NotifyPointerMotion", "oa{sv}dd",
                         [self.session, {}, float(dx), float(dy)])
        return {"status": "sent_unverified", "dx": dx, "dy": dy}

    async def click_left(self):
        """Um clique esquerdo no cursor atual, somente com permissão do portal."""
        if not self.session or not self.devices & POINTER:
            raise WaylandError("Sessão sem permissão de ponteiro")
        try:
            await self._call(INTERFACE, "NotifyPointerButton", "oa{sv}iu",
                             [self.session, {}, LEFT_BUTTON, PRESSED])
        finally:
            await self._call(INTERFACE, "NotifyPointerButton", "oa{sv}iu",
                             [self.session, {}, LEFT_BUTTON, RELEASED])
        return {"status": "sent_unverified", "action": "left_click"}

    async def type_test_letter(self):
        """Envia somente a tecla minúscula j, sem comandos arbitrários."""
        if not self.session or not self.devices & KEYBOARD:
            raise WaylandError("Sessão sem permissão de teclado")
        key = ord("j")
        try:
            await self._call(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu",
                             [self.session, {}, key, PRESSED])
        finally:
            await self._call(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu",
                             [self.session, {}, key, RELEASED])
        return {"status": "sent_unverified", "action": "type_letter_j"}

    async def type_safe_text(self, text):
        """Digita somente letras latinas minúsculas, dígitos e espaços.

        Não oferece teclas especiais, atalhos ou envio de comandos.
        """
        if not self.session or not self.devices & KEYBOARD:
            raise WaylandError("Sessão sem permissão de teclado")
        if not isinstance(text, str) or not (1 <= len(text) <= 40):
            raise WaylandError("Texto deve ter entre 1 e 40 caracteres")
        if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789 " for c in text):
            raise WaylandError("Somente letras minúsculas sem acentos, dígitos e espaço")
        for character in text:
            key = ord(character)
            try:
                await self._call(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu",
                                 [self.session, {}, key, PRESSED])
            finally:
                await self._call(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu",
                                 [self.session, {}, key, RELEASED])
            await asyncio.sleep(0.02)
        return {"status": "sent_unverified", "action": "type_text", "characters": len(text)}

    async def close(self):
        if self.bus is not None:
            try:
                if self.session:
                    await self._call("org.freedesktop.portal.Session", "Close",
                                     path=self.session)
            finally:
                self.session = None
                self.devices = 0
                self.bus.disconnect()
                self.bus = None


async def test_remote_pointer_async():
    desktop = RemoteDesktop()
    try:
        info = await desktop.start()
        # Dar tempo para o diálogo GNOME desaparecer e o desktop retomar o foco.
        await asyncio.sleep(1.5)
        movements = []
        for _ in range(3):
            movements.append(await desktop.move(25, 0))
            await asyncio.sleep(0.5)
        # Manter sessão autorizada ativa para o compositor processar os eventos.
        await asyncio.sleep(2)
        return {"status": "sent_unverified", "devices": desktop.devices,
                "pointer_authorized": info["pointer"], "events_sent": len(movements),
                "total_dx": 75, "total_dy": 0}
    finally:
        await desktop.close()


def test_remote_pointer(approve):
    import os
    if os.getenv("XDG_SESSION_TYPE", "").lower() != "wayland":
        raise WaylandError("Teste disponível apenas em sessão Wayland")
    if not approve("ABRIR sessão RemoteDesktop e MOVER o ponteiro 75 pixels à direita (3 eventos), encerrando em seguida?"):
        return {"status": "rejected"}
    return asyncio.run(test_remote_pointer_async())

async def _test_input_async(kind):
    desktop = RemoteDesktop()
    try:
        await desktop.start(KEYBOARD if kind == "keyboard" else POINTER)
        await asyncio.sleep(1.5)
        result = await (desktop.type_test_letter() if kind == "keyboard" else desktop.click_left())
        await asyncio.sleep(1.0)
        return result
    finally:
        await desktop.close()

def test_input(approve, kind):
    """Teste de CLI isolado; não registrado como ferramenta do agente."""
    import os
    if kind not in ("click", "keyboard"):
        raise WaylandError("Tipo de teste inválido")
    if os.getenv("XDG_SESSION_TYPE", "").lower() != "wayland":
        raise WaylandError("Exige sessão Wayland")
    description = ("UM clique esquerdo na posição atual (coloque o cursor numa área vazia)"
                   if kind == "click" else
                   "digitar somente a letra j num editor de texto vazio (não em terminal)")
    if not approve("AUTORIZAR " + description + "?"):
        return {"status": "rejected"}
    return asyncio.run(_test_input_async(kind))

async def _agent_step_async(action, dx=0, dy=0, text=""):
    desktop = RemoteDesktop()
    try:
        await desktop.start(KEYBOARD if action == "type" else POINTER)
        # Dar tempo ao GNOME para fechar o diálogo do portal.
        await asyncio.sleep(1.5)
        if action == "move":
            outcome = await desktop.move(dx, dy)
        elif action == "click":
            outcome = await desktop.click_left()
        else:
            outcome = await desktop.type_safe_text(text)
        await asyncio.sleep(0.7)
        return outcome
    finally:
        await desktop.close()


def agent_step(approve, action, dx=0, dy=0, text=""):
    """Uma ação de interface por autorização e por sessão portal transitória."""
    import os
    if os.getenv("JARVIS_ENABLE_DESKTOP_INPUT") != "1":
        raise WaylandError("Controle gráfico do agente desativado: defina JARVIS_ENABLE_DESKTOP_INPUT=1")
    if os.getenv("XDG_SESSION_TYPE", "").lower() != "wayland":
        raise WaylandError("Controle gráfico exige sessão Wayland")
    if action not in ("move", "click", "type"):
        raise WaylandError("Ação gráfica não permitida")
    if action == "move":
        if type(dx) not in (int, float) or type(dy) not in (int, float):
            raise WaylandError("Deslocamento inválido")
        if not (-50 <= dx <= 50 and -50 <= dy <= 50):
            raise WaylandError("Movimento limitado a 50 pixels por eixo")
        description = f"MOVER ponteiro em dx={dx}, dy={dy} pixels"
    elif action == "click":
        if dx != 0 or dy != 0 or text:
            raise WaylandError("Clique não admite texto ou deslocamento")
        description = "CLICAR com botão esquerdo na posição ATUAL do ponteiro; pode acionar comandos ou alterar dados"
    else:
        if dx != 0 or dy != 0 or not isinstance(text, str):
            raise WaylandError("Argumentos inválidos para digitação")
        if not (1 <= len(text) <= 40) or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789 " for c in text):
            raise WaylandError("Texto restrito a 40 caracteres minúsculos, dígitos ou espaço")
        description = f"DIGITAR no campo focado o texto EXATO {text!r}; não use em campos de senha"
    if not approve("AÇÃO GRÁFICA SOLICITADA PELA IA: " + description):
        return {"status": "rejected"}
    return asyncio.run(_agent_step_async(action, dx, dy, text))
