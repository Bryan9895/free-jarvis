"""Wayland portal tests without requiring Wayland compositor in CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jarvis.wayland import desktop_info, screenshot, _source_path, WaylandError, open_app
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

    def test_app_launch_requires_allowlist(self):
        with patch.dict("os.environ", {"JARVIS_ALLOWED_APPS":"org.gnome.Nautilus"}, clear=True):
            with self.assertRaises(WaylandError):
                open_app("org.gnome.Terminal", lambda _: True)

    def test_app_launch_needs_approval(self):
        with patch.dict("os.environ", {"JARVIS_ALLOWED_APPS":"org.gnome.Nautilus"}, clear=True), patch("jarvis.wayland.shutil.which", return_value="/usr/bin/gtk-launch"):
            with patch("jarvis.wayland.subprocess.Popen", side_effect=AssertionError("Should not launch")):
                self.assertEqual(open_app("org.gnome.Nautilus", lambda _: False)["status"], "rejected")

    def test_app_launch_approved(self):
        from unittest.mock import Mock
        with patch.dict("os.environ", {"JARVIS_ALLOWED_APPS":"org.gnome.Nautilus"}, clear=True), patch("jarvis.wayland.shutil.which", return_value="/usr/bin/gtk-launch"), patch("jarvis.wayland.subprocess.Popen", return_value=Mock(pid=1234)) as run:
            result = open_app("org.gnome.Nautilus", lambda _: True)
            self.assertEqual(result["status"], "launched_unverified")
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], ["/usr/bin/gtk-launch", "org.gnome.Nautilus"])

    def test_tool_registry(self):
        with tempfile.TemporaryDirectory() as td:
            tool = Toolkit(Path(td), approve=lambda _: False)
            value=tool.execute("desktop_screenshot", {})
            with patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland"}):
                value=tool.execute("desktop_screenshot", {})
            self.assertEqual(value["result"]["status"], "rejected")

if __name__ == "__main__":
    unittest.main()
