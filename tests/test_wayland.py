"""Wayland portal tests without requiring Wayland compositor in CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jarvis.wayland import desktop_info, screenshot, _source_path, WaylandError
from jarvis.tools import Toolkit

class WaylandTests(unittest.TestCase):
    def test_session_detection(self):
        with patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland", "XDG_CURRENT_DESKTOP":"GNOME"}, clear=True):
            value = desktop_info()
        self.assertEqual(value["session"], "wayland")
        self.assertEqual(value["desktop"], "GNOME")

    def test_no_screenshot_without_confirmation(self):
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland"}):
            with patch("jarvis.wayland._request_screenshot", side_effect=AssertionError("must not call")):
                self.assertEqual(screenshot(Path(td), lambda _: False)["status"], "rejected")

    def test_reject_non_wayland(self):
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ", {"XDG_SESSION_TYPE":"x11"}):
            with self.assertRaises(WaylandError):
                screenshot(Path(td), lambda _: True)

    def test_reject_nonfile_screenshot_uri(self):
        with self.assertRaises(WaylandError):
            _source_path("https://example.com/a.png")

    def test_screenshot_copy_with_mocked_portal(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td)/"original.png"
            image.write_bytes(b"fake-image")
            workspace = Path(td)/"workspace"
            async def fake_portal(timeout=60):
                return image.as_uri()
            with patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland"}), patch("jarvis.wayland._request_screenshot", fake_portal):
                value=screenshot(workspace, lambda _: True)
            self.assertEqual(value["status"], "saved")
            self.assertEqual((workspace/"jarvis_desktop_screenshot.png").read_bytes(), b"fake-image")

    def test_tool_registry(self):
        with tempfile.TemporaryDirectory() as td:
            tool = Toolkit(Path(td), approve=lambda _: False)
            value=tool.execute("desktop_screenshot", {})
            with patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland"}):
                value=tool.execute("desktop_screenshot", {})
            self.assertEqual(value["result"]["status"], "rejected")

if __name__ == "__main__":
    unittest.main()
