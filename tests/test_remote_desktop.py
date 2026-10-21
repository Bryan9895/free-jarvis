"""Tests for restricted Wayland RemoteDesktop operations."""
import asyncio
import unittest
from unittest.mock import patch
from jarvis.remote_desktop import RemoteDesktop, POINTER, KEYBOARD, LEFT_BUTTON, PRESSED, RELEASED, test_remote_pointer as run_demo, test_remote_pointer_async, test_input, agent_step
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

    def test_demo_keeps_session_open_for_motion(self):
        async def exercise():
            events=[]
            async def start(_):
                events.append("start")
                _.devices=POINTER
                return {"pointer": True}
            async def move(_, dx, dy):
                events.append("move")
                return {"status": "sent_unverified"}
            async def close(_):
                events.append("close")
            async def pause(duration):
                events.append("pause")
            with patch.object(RemoteDesktop,"start",start), patch.object(RemoteDesktop,"move",move), patch.object(RemoteDesktop,"close",close), patch("jarvis.remote_desktop.asyncio.sleep",side_effect=pause):
                result=await test_remote_pointer_async()
            self.assertEqual(result["total_dx"],75)
            self.assertEqual(result["events_sent"],3)
            self.assertEqual(events[-1],"close")
            self.assertEqual(events.count("move"),3)
            self.assertIn("pause",events)
        asyncio.run(exercise())

    def test_click_requires_pointer(self):
        async def run():
            d = RemoteDesktop()
            d.session = "/session/mock"
            d.devices = KEYBOARD
            with self.assertRaises(WaylandError):
                await d.click_left()
        asyncio.run(run())

    def test_keyboard_requires_keyboard(self):
        async def run():
            d = RemoteDesktop()
            d.session = "/session/mock"
            d.devices = POINTER
            with self.assertRaises(WaylandError):
                await d.type_test_letter()
        asyncio.run(run())

    def test_click_press_release_and_keyboard_keysym(self):
        async def run():
            d = RemoteDesktop()
            d.session = "/session/mock"
            d.devices = POINTER | KEYBOARD
            calls = []
            async def fake_call(interface, member, signature="", body=None, path=None):
                calls.append((member, signature, body))
            d._call = fake_call
            await d.click_left()
            await d.type_test_letter()
            self.assertEqual(calls[0][0:2], ("NotifyPointerButton", "oa{sv}iu"))
            self.assertEqual(calls[0][2][-2:], [LEFT_BUTTON, PRESSED])
            self.assertEqual(calls[1][2][-2:], [LEFT_BUTTON, RELEASED])
            self.assertEqual(calls[2][0:2], ("NotifyKeyboardKeysym", "oa{sv}iu"))
            self.assertEqual(calls[2][2][-2:], [ord("j"), PRESSED])
            self.assertEqual(calls[3][2][-2:], [ord("j"), RELEASED])
        asyncio.run(run())

    def test_click_and_keyboard_rejected_without_portal(self):
        with patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland"}), patch("jarvis.remote_desktop.asyncio.run", side_effect=AssertionError("never")):
            self.assertEqual(test_input(lambda _: False, "click")["status"], "rejected")
            self.assertEqual(test_input(lambda _: False, "keyboard")["status"], "rejected")

    def test_disallows_other_input_kinds(self):
        with self.assertRaises(WaylandError):
            test_input(lambda _: True, "arbitrary")

    def test_agent_step_disabled_by_default(self):
        import os
        with patch.dict(os.environ, {"XDG_SESSION_TYPE":"wayland"}, clear=True):
            with self.assertRaises(WaylandError):
                agent_step(lambda _: True, "move", dx=1)

    def test_agent_step_rejects_invalid_actions_before_approval(self):
        import os
        with patch.dict(os.environ, {"XDG_SESSION_TYPE":"wayland", "JARVIS_ENABLE_DESKTOP_INPUT":"1"}):
            for action, kwargs in (("delete", {}), ("move", {"dx":100}), ("type", {"text":"sudo rm -rf /"}), ("type", {"text":"Olá"}), ("click", {"dx":1})):
                with self.subTest(action=action, kwargs=kwargs):
                    with self.assertRaises(WaylandError):
                        agent_step(lambda _: True, action, **kwargs)

    def test_agent_step_rejects_without_starting_portal(self):
        import os
        with patch.dict(os.environ, {"XDG_SESSION_TYPE":"wayland", "JARVIS_ENABLE_DESKTOP_INPUT":"1"}), patch("jarvis.remote_desktop.asyncio.run", side_effect=AssertionError("must not run")):
            self.assertEqual(agent_step(lambda _: False, "move", dx=10)["status"], "rejected")
            self.assertEqual(agent_step(lambda _: False, "click")["status"], "rejected")
            self.assertEqual(agent_step(lambda _: False, "type", text="ola")["status"], "rejected")

    def test_safe_text_key_events(self):
        async def run():
            d=RemoteDesktop()
            d.session="/session/mock"
            d.devices=KEYBOARD
            calls=[]
            async def fake_call(interface, member, signature="", body=None, path=None):
                calls.append((member, body))
            async def fake_sleep(_): pass
            d._call=fake_call
            with patch("jarvis.remote_desktop.asyncio.sleep", side_effect=fake_sleep):
                result=await d.type_safe_text("ja 1")
            self.assertEqual(result["characters"], 4)
            self.assertEqual(len(calls), 8)
            self.assertEqual(calls[0][1][-2:], [ord("j"), PRESSED])
            self.assertEqual(calls[1][1][-2:], [ord("j"), RELEASED])
        asyncio.run(run())

    def test_safe_text_requires_keyboard_and_valid_chars(self):
        async def run():
            d=RemoteDesktop()
            d.session="/session/mock"
            d.devices=POINTER
            with self.assertRaises(WaylandError):
                await d.type_safe_text("ola")
            d.devices=KEYBOARD
            for text in ("", "A", "x"*41, "a\\nb", "á"):
                with self.assertRaises(WaylandError):
                    await d.type_safe_text(text)
        asyncio.run(run())

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
