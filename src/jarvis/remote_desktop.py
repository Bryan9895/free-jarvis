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


def _result_value(results, key):
    value = results.get(key)
    return value.value if hasattr(value, "value") else value


class RemoteDesktop:
    def __init__(self):
        self.bus = None
        self.session = None
        self.devices = 0

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
            options["types"] = Variant("u", POINTER)
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

    async def start(self):
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
            if not self.devices & POINTER:
                raise WaylandError("Permissão de ponteiro não foi concedida")
            return {"status": "authorized", "pointer": True}
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
        await desktop.start()
        return await desktop.move(25, 0)
    finally:
        await desktop.close()


def test_remote_pointer(approve):
    import os
    if os.getenv("XDG_SESSION_TYPE", "").lower() != "wayland":
        raise WaylandError("Teste disponível apenas em sessão Wayland")
    if not approve("ABRIR sessão RemoteDesktop e MOVER o ponteiro 25 pixels para a direita?"):
        return {"status": "rejected"}
    return asyncio.run(test_remote_pointer_async())
