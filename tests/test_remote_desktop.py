"""Tests for restricted Wayland RemoteDesktop operations."""
import asyncio
import unittest
from unittest.mock import patch
from jarvis.remote_desktop import RemoteDesktop, POINTER, test_remote_pointer as run_demo
from jarvis.wayland import WaylandError

class RemoteDesktopTests(unittest.TestCase):
    def test_refuses_without_wayland(self):
        with patch.dict("os.environ", {"XDG_SESSION_TYPE":"x11"}):
            with self.assertRaises(WaylandError):
                run_demo(lambda _: True)

    def test_no_connection_when_rejected(self):
        with patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland"}), patch("jarvis.remote_desktop.asyncio.run", side_effect=AssertionError("must not run")):
            self.assertEqual(run_demo(lambda _: False), {"status":"rejected"})

    def test_move_requires_granted_session(self):
        async def exercise():
            desktop=RemoteDesktop()
            with self.assertRaises(WaylandError):
                await desktop.move(1, 0)
        asyncio.run(exercise())

    def test_movement_bounded(self):
        async def exercise():
            desktop=RemoteDesktop()
            desktop.session="/org/freedesktop/portal/desktop/session/test"
            desktop.devices=POINTER
            with self.assertRaises(WaylandError):
                await desktop.move(51, 0)
            with self.assertRaises(WaylandError):
                await desktop.move(0, -90)
        asyncio.run(exercise())

    def test_notification_signature(self):
        async def exercise():
            desktop=RemoteDesktop()
            desktop.session="/org/freedesktop/portal/desktop/session/test"
            desktop.devices=POINTER
            calls=[]
            async def fake_call(interface, member, signature="", body=None, path=None):
                calls.append((interface,member,signature,body))
            desktop._call=fake_call
            self.assertEqual((await desktop.move(25,0))["status"], "sent_unverified")
            self.assertEqual(calls[0][2], "oa{sv}dd")
            self.assertEqual(calls[0][3][-2:], [25.0, 0.0])
        asyncio.run(exercise())

if __name__ == "__main__":
    unittest.main()
