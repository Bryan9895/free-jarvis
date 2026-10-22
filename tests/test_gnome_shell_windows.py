"""GNOME Shell bridge: safe response parsing and AT-SPI fallback."""
import json
import unittest
from unittest.mock import Mock, patch

from jarvis.gnome_shell_windows import parse_gdbus_reply, shell_windows
from jarvis.desktop_windows import desktop_windows, verify_app_window


class ShellWindowsTests(unittest.TestCase):
    def test_parse_valid_extension_response(self):
        raw = repr((json.dumps([
            {"class": "code", "title": "main.py - Visual Studio Code", "pid": 88, "focus": True},
            {"class": "firefox", "title": "Mozilla Firefox", "pid": 89, "focus": False}
        ]),))
        found = parse_gdbus_reply(raw)
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0]["app"], "code")
        self.assertEqual(found[0]["pid"], 88)
        self.assertTrue(found[0]["focused"])

    def test_rejects_malformed_or_oversize_reply(self):
        for raw in ("hello", "(123,)", "('{}',)", "('[]', 'extra')",
                    "('not json',)", "(" + "x" * 100002 + ")"):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises((SyntaxError, ValueError)):
                    parse_gdbus_reply(raw)

    def test_bridge_observed_with_dbus(self):
        payload = repr((json.dumps([{"class":"firefox","title":"Firefox","focus":True}]),))
        with patch.dict("os.environ", {"XDG_SESSION_TYPE":"wayland"}), patch(
            "jarvis.gnome_shell_windows.shutil.which", return_value="/usr/bin/gdbus"
        ), patch("jarvis.gnome_shell_windows.subprocess.run",
                 return_value=Mock(returncode=0, stdout=payload)) as run:
            data = shell_windows()
            self.assertEqual(data["source"], "gnome_shell_extension")
            self.assertFalse(data["complete"])
            self.assertEqual(run.call_args.args[0][-1],
                             "org.gnome.Shell.Extensions.WindowsExt.List")

    def test_fallback_and_positive_window_check(self):
        primary = {"status":"unavailable","reason":"Extensão ausente"}
        fallback = {"status":"observed","complete":False,"windows":[
            {"app":"ptyxis","title":"Terminal"}],"source":"atspi_accessibility_partial"}
        with patch("jarvis.gnome_shell_windows.shell_windows", return_value=primary), patch(
            "jarvis.desktop_windows._atspi_windows", return_value=fallback
        ):
            data = desktop_windows()
            self.assertEqual(data["fallback_reason"], "Extensão ausente")
            self.assertEqual(verify_app_window("ptyxis")["status"], "window_observed")

    def test_bridge_preferred_over_accessibility(self):
        primary = {"status":"observed","source":"gnome_shell_extension",
                   "complete":False,"windows":[{"app":"code","title":"main.py"}]}
        with patch("jarvis.gnome_shell_windows.shell_windows", return_value=primary), patch(
            "jarvis.desktop_windows._atspi_windows"
        ) as fallback:
            self.assertEqual(desktop_windows(), primary)
            self.assertEqual(verify_app_window("code", "main.py")["source"],
                             "gnome_shell_extension")
            fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
