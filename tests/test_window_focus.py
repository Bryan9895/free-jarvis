"""Regressões de ativação supervisionada no GNOME; não altera desktop do CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.window_focus import focus_window
from jarvis.tools import Toolkit, TOOL_SPECS


def w(app, title, focused=False, pid=55):
    return {"app": app, "title": title, "focused": focused, "pid": pid}


class FocusTests(unittest.TestCase):
    def test_unique_focus_is_verified_after_approval(self):
        first = [w("firefox_firefox", "Mozilla Firefox")]
        second = [w("firefox_firefox", "Mozilla Firefox", True)]
        seen = []
        with patch("jarvis.window_focus._visible_windows",
                   side_effect=[first, first, second]), patch(
            "jarvis.window_focus.shutil.which", return_value="/usr/bin/gdbus"
        ), patch("jarvis.window_focus.subprocess.run",
                 return_value=Mock(returncode=0, stdout="(true,)")) as run:
            result = focus_window("firefox", "", lambda value: seen.append(value) or True)
        self.assertEqual(result["status"], "focused_verified")
        self.assertEqual(len(seen), 1)
        self.assertEqual(run.call_args.args[0][-1], "Mozilla Firefox")
        self.assertIn("activateByTitle", run.call_args.args[0][-2])

    def test_multiple_matches_rejected_without_side_effects(self):
        before = [w("firefox", "A"), w("firefox", "B")]
        with patch("jarvis.window_focus._visible_windows", return_value=before), patch(
            "jarvis.window_focus.subprocess.run"
        ) as run:
            self.assertEqual(focus_window("firefox", "", lambda _: True)["status"], "ambiguous")
            run.assert_not_called()

    def test_shared_titles_rejected_even_with_unique_app(self):
        before = [w("firefox", "Hello"), w("code", "Hello")]
        with patch("jarvis.window_focus._visible_windows", return_value=before), patch(
            "jarvis.window_focus.subprocess.run"
        ) as run:
            self.assertEqual(focus_window("firefox", "", lambda _: True)["status"], "ambiguous")
            run.assert_not_called()

    def test_denied_does_not_call_dbus(self):
        before = [w("code", "main.py - Code")]
        with patch("jarvis.window_focus._visible_windows", return_value=before), patch(
            "jarvis.window_focus.shutil.which", return_value="/usr/bin/gdbus"
        ), patch("jarvis.window_focus.subprocess.run") as run:
            self.assertEqual(focus_window("code", "", lambda _: False)["status"], "rejected")
            run.assert_not_called()

    def test_preapproved_title_change_blocks_request(self):
        before = [w("code", "main.py - Code")]
        after = [w("code", "README.md - Code")]
        with patch("jarvis.window_focus._visible_windows", side_effect=[before, after]), patch(
            "jarvis.window_focus.shutil.which", return_value="/usr/bin/gdbus"
        ), patch("jarvis.window_focus.subprocess.run") as run:
            self.assertEqual(focus_window("code", "", lambda _: True)["status"], "changed")
            run.assert_not_called()

    def test_extension_failure_is_not_success(self):
        before = [w("code", "main.py - Code")]
        with patch("jarvis.window_focus._visible_windows", side_effect=[before, before]), patch(
            "jarvis.window_focus.shutil.which", return_value="/usr/bin/gdbus"
        ), patch("jarvis.window_focus.subprocess.run",
                 return_value=Mock(returncode=1, stdout="", stderr="error")):
            result = focus_window("code", "", lambda _: True)
        self.assertEqual(result["status"], "unavailable")

    def test_no_focus_after_accepted_command_is_unverified(self):
        before = [w("code", "main.py - Code")]
        with patch("jarvis.window_focus._visible_windows", return_value=before), patch(
            "jarvis.window_focus.shutil.which", return_value="/usr/bin/gdbus"
        ), patch("jarvis.window_focus.subprocess.run",
                 return_value=Mock(returncode=0, stdout="(true,)")):
            result = focus_window("code", "", lambda _: True, retries=1)
        self.assertEqual(result["status"], "focus_unverified")

    def test_already_focused_is_noop(self):
        with patch("jarvis.window_focus._visible_windows",
                   return_value=[w("code", "Code", True)]), patch(
            "jarvis.window_focus.subprocess.run"
        ) as run:
            self.assertEqual(focus_window("code", "", lambda _: True)["status"], "already_focused")
            run.assert_not_called()

    def test_toolkit_registers_focus_tool(self):
        with tempfile.TemporaryDirectory() as td:
            toolkit = Toolkit(Path(td), approve=lambda _: False)
            self.assertIn("focus_window", {spec["name"] for spec in TOOL_SPECS})
            with patch("jarvis.window_focus._visible_windows", return_value=None):
                self.assertEqual(toolkit.execute("focus_window", {"app": "firefox"})[
                    "result"]["status"], "unavailable")
            toolkit.close()


if __name__ == "__main__":
    unittest.main()
