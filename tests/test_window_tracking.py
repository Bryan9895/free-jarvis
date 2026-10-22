"""Correlacao conservadora de janelas do GNOME e processos iniciados."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.window_tracking import compare, observe_launch
from jarvis.tools import Toolkit
from jarvis.verification import verify_step


def windows(items):
    return {"source": "gnome_shell_extension", "windows": items}


class WindowTrackingTests(unittest.TestCase):
    def test_preexisting_firefox_is_not_claimed_as_new(self):
        existing = [{"app": "firefox_firefox", "title": "Mozilla Firefox", "pid": 41}]
        result = compare(windows(existing), windows(existing), "firefox")
        self.assertEqual(result["status"], "already_observed")

    def test_new_window_after_launch(self):
        before = windows([{"app": "org.gnome.Nautilus", "title": "Downloads"}])
        after = windows([{"app": "firefox_firefox", "title": "Mozilla Firefox", "pid": 42}])
        self.assertEqual(compare(before, after, "firefox")["status"], "appeared_after_request")

    def test_code_title_change_is_observation_not_verified_file(self):
        before = windows([{"app": "code", "title": "README.md - VS Code", "pid": 8}])
        after = windows([{"app": "code", "title": "main.py - VS Code", "pid": 8}])
        self.assertEqual(compare(before, after, "vscode")["status"], "window_changed_after_request")

    def test_unavailable_never_fails_launcher(self):
        self.assertEqual(compare(None, None, "vscode")["status"], "unavailable")
        with patch("jarvis.window_tracking.snapshot", return_value=None):
            result = observe_launch({"status": "launched_unverified"}, "vscode", None,
                                    attempts=1)
        self.assertEqual(result["status"], "launched_unverified")
        self.assertEqual(result["window_observation"]["status"], "unavailable")

    def test_verifier_keeps_gui_unverified_even_when_observed(self):
        with tempfile.TemporaryDirectory() as td:
            toolkit = Toolkit(Path(td))
            action = {"name": "open_project",
                      "outcome": {"result": {"status": "launched_unverified"}},
                      "window_observation": {"status": "appeared_after_request",
                                             "source": "gnome_shell_extension"}}
            state, evidence = verify_step(toolkit, [action])
            self.assertEqual(state, "unverified")
            self.assertEqual(evidence[0]["window_status"], "appeared_after_request")
            toolkit.close()

    def test_gtk_launch_compares_firefox_before_after(self):
        from jarvis.apps import launch_installed_app
        before = windows([])
        after = windows([{"app": "firefox_firefox", "title": "Firefox", "pid": 23}])
        with patch("jarvis.apps.installed_applications", return_value=[
            {"id": "firefox_firefox", "name": "Firefox"}]), patch(
            "jarvis.apps.shutil.which", return_value="/usr/bin/gtk-launch"
        ), patch("jarvis.apps.subprocess.Popen", return_value=Mock(pid=123)) as launched, patch(
            "jarvis.window_tracking.snapshot", side_effect=[before, after]
        ):
            result = launch_installed_app("firefox_firefox", lambda _: True)
        self.assertEqual(result["window_observation"]["status"], "appeared_after_request")
        self.assertEqual(result["status"], "launched_unverified")
        self.assertEqual(launched.call_args.args[0],
                         ["/usr/bin/gtk-launch", "firefox_firefox"])

    def test_project_launch_reports_observation_to_managed_processes(self):
        with tempfile.TemporaryDirectory() as td:
            toolkit = Toolkit(Path(td), approve=lambda _: True)
            mock_process = Mock(pid=99)
            mock_process.poll.return_value = None
            initial = windows([])
            new = windows([{"app": "code", "title": "demo - VS Code", "pid": 99}])
            with patch("jarvis.process_manager.shutil.which", return_value="/usr/bin/code"), patch(
                "jarvis.process_manager.subprocess.Popen", return_value=mock_process
            ), patch("jarvis.window_tracking.snapshot", side_effect=[initial, new]):
                result = toolkit.execute("open_project", {"path": "."})
            self.assertEqual(result["result"]["window_observation"]["status"],
                             "appeared_after_request")
            self.assertEqual(toolkit.managed_processes()[0]["window_status"],
                             "appeared_after_request")
            toolkit.close()


if __name__ == "__main__":
    unittest.main()
