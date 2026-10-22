"""Editor opening and supervised focusing are two separate approvals."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.tools import Toolkit, TOOL_SPECS


class EditorFocusTests(unittest.TestCase):
    def test_project_launch_then_focus_with_distinct_approvals(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "MyProject"
            folder.mkdir()
            approvals = []
            kit = Toolkit(Path(root), approve=lambda msg: approvals.append(msg) or True)
            with patch.object(kit._processes, "open_project",
                              return_value={"status": "launched_unverified"}) as opened, patch(
                "jarvis.window_focus.focus_window",
                return_value={"status": "focused_verified", "title": "MyProject"}) as focus:
                answer = kit.execute("open_project_and_focus", {"path": "MyProject"})
            self.assertEqual(answer["result"]["focus"]["status"], "focused_verified")
            self.assertEqual(opened.call_args.args[0], folder)
            self.assertEqual(focus.call_args.args[0][:2], ("code", "MyProject"))
            kit.close()

    def test_rejected_launch_never_attempts_focus(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "MyProject"
            folder.mkdir()
            kit = Toolkit(Path(root), approve=lambda _: False)
            with patch.object(kit._processes, "open_project",
                              return_value={"status": "rejected"}), patch(
                "jarvis.window_focus.focus_window") as focus:
                answer = kit.execute("open_project_and_focus", {"path": "MyProject"})
            self.assertEqual(answer["result"]["focus"]["status"], "not_attempted")
            focus.assert_not_called()
            kit.close()

    def test_file_focus_targets_filename_not_directory(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "main.py"
            path.write_text("print(1)", encoding="utf8")
            kit = Toolkit(Path(root))
            with patch.object(kit._processes, "open_file",
                              return_value={"status": "launched_unverified"}), patch(
                "jarvis.window_focus.focus_window",
                return_value={"status": "ambiguous"}) as focus:
                answer = kit.execute("open_file_and_focus", {"path": "main.py"})
            self.assertEqual(answer["result"]["focus"]["status"], "ambiguous")
            self.assertEqual(focus.call_args.args[0][:2], ("code", "main.py"))
            kit.close()

    def test_app_open_and_focus_separate_outcomes(self):
        with tempfile.TemporaryDirectory() as root:
            kit = Toolkit(Path(root))
            with patch("jarvis.apps.launch_installed_app",
                       return_value={"status": "launched_unverified"}) as launched, patch(
                "jarvis.window_focus.focus_window",
                return_value={"status": "focus_unverified"}) as focused:
                result = kit.execute("launch_installed_app_and_focus",
                                     {"app_id": "firefox_firefox"})
            self.assertEqual(result["result"]["launch"]["status"], "launched_unverified")
            self.assertEqual(result["result"]["focus"]["status"], "focus_unverified")
            launched.assert_called_once()
            self.assertEqual(focused.call_args.args[0][0], "firefox_firefox")
            kit.close()

    def test_rejected_app_never_focuses(self):
        with tempfile.TemporaryDirectory() as root:
            kit = Toolkit(Path(root))
            with patch("jarvis.apps.launch_installed_app",
                       return_value={"status": "rejected"}), patch(
                "jarvis.window_focus.focus_window") as focus:
                result = kit.execute("launch_installed_app_and_focus",
                                     {"app_id": "firefox_firefox"})
            self.assertEqual(result["result"]["focus"]["status"], "not_attempted")
            focus.assert_not_called()
            kit.close()

    def test_exposed_and_workspace_restricted(self):
        with tempfile.TemporaryDirectory() as root:
            kit = Toolkit(Path(root))
            self.assertIn("open_project_and_focus", {spec["name"] for spec in TOOL_SPECS})
            self.assertIn("open_file_and_focus", {spec["name"] for spec in TOOL_SPECS})
            self.assertIn("error", kit.execute("open_file_and_focus",
                                               {"path": "/etc/passwd"}))
            kit.close()


if __name__ == "__main__":
    unittest.main()
