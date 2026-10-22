"""Processos lançadores e abertura supervisionada de projetos."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.process_manager import ProcessManager
from jarvis.tools import Toolkit, TOOL_SPECS


class ProcessesTests(unittest.TestCase):
    def test_launch_and_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manager = ProcessManager()
            mock_process = Mock(pid=4321)
            mock_process.poll.side_effect = [None, 0]
            with patch("jarvis.process_manager.shutil.which", return_value="/usr/bin/code"), patch(
                "jarvis.process_manager.subprocess.Popen", return_value=mock_process
            ) as launch:
                result = manager.open_project(root, "vscode", lambda _: True)
                self.assertEqual(result["status"], "launched_unverified")
                self.assertEqual(launch.call_args.args[0],
                                 ["/usr/bin/code", "--new-window", str(root)])
            self.assertEqual(manager.list_launches()[0]["launcher_status"], "running")
            self.assertEqual(manager.list_launches()[0]["launcher_status"], "exited")
            self.assertEqual(manager.list_launches()[0]["window_status"], "unknown")
            manager.close()

    def test_denied_or_unknown_editor_never_starts_process(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "jarvis.process_manager.shutil.which", return_value="/usr/bin/code"
        ), patch("jarvis.process_manager.subprocess.Popen", side_effect=AssertionError("launch")):
            manager = ProcessManager()
            self.assertEqual(
                manager.open_project(Path(td), "vscode", lambda _: False)["status"],
                "rejected")
            with self.assertRaises(ValueError):
                manager.open_project(Path(td), "bash", lambda _: True)

    def test_toolkit_project_path_scoped_and_registered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            root.mkdir()
            folder = root / "demo"
            folder.mkdir()
            toolkit = Toolkit(root, approve=lambda _: False)
            with patch("jarvis.process_manager.shutil.which", return_value="/usr/bin/code"):
                result = toolkit.execute("open_project", {"path": "demo"})
                self.assertEqual(result["result"]["status"], "rejected")
            self.assertIn("error", toolkit.execute("open_project", {"path": "../outside"}))
            self.assertEqual(toolkit.execute("managed_processes", {})["result"], [])
            self.assertTrue({"open_project","managed_processes"} <=
                            {t["name"] for t in TOOL_SPECS})
            toolkit.close()

    def test_create_python_project_and_open_later(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            toolkit=Toolkit(root, approve=lambda _: True)
            result=toolkit.execute("create_python_project", {"path":"demo"})
            self.assertEqual(result["result"]["status"], "created")
            project=root/"demo"
            self.assertTrue((project/"main.py").exists())
            self.assertTrue((project/"README.md").exists())
            self.assertTrue((project/".gitignore").exists())
            self.assertIn("error", toolkit.execute("create_python_project", {"path":"demo"}))
            toolkit.close()

    def test_no_project_creation_when_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            toolkit=Toolkit(root, approve=lambda _: False)
            result=toolkit.execute("create_python_project", {"path":"demo"})
            self.assertEqual(result["result"]["status"], "rejected")
            self.assertFalse((root/"demo").exists())
            toolkit.close()

    def test_project_requires_existing_directory(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                ProcessManager().open_project(Path(td)/"missing", "vscode", lambda _: True)


if __name__ == "__main__":
    unittest.main()
