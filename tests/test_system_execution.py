"""Testes do gerenciador de apps XDG e diretórios adicionais, sem abrir GUI."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.apps import installed_applications, launch_installed_app
from jarvis.tools import Toolkit, TOOL_SPECS


class SystemExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.appdir = self.base / "share" / "applications"
        self.appdir.mkdir(parents=True)
        (self.appdir / "org.example.Editor.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Exemplo Editor\nExec=untrusted --arguments\n",
            encoding="utf-8",
        )
        (self.appdir / "org.example.Hidden.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Oculto\nNoDisplay=true\nExec=none\n",
            encoding="utf-8",
        )
        self.env = patch.dict(os.environ, {
            "XDG_DATA_HOME": str(self.base / "share"),
            "XDG_DATA_DIRS": str(self.base / "empty"),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_discovery_filters_hidden_and_returns_id(self):
        result = installed_applications(query="Editor")
        self.assertEqual(result, [{"id":"org.example.Editor","name":"Exemplo Editor"}])
        self.assertEqual(installed_applications(query="Oculto"), [])

    def test_launch_uses_gtk_launch_not_desktop_exec(self):
        with patch("jarvis.apps.shutil.which", return_value="/usr/bin/gtk-launch"), patch(
            "jarvis.apps.subprocess.Popen", return_value=Mock(pid=77)
        ) as run, patch("jarvis.window_tracking.snapshot", return_value=None), patch(
            "jarvis.window_tracking.observe_launch",
            side_effect=lambda launched, *_args: {**launched, "window_observation": {"status": "unavailable"}}
        ):
            result = launch_installed_app("org.example.Editor", lambda _: True)
        self.assertEqual(result["status"], "launched_unverified")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/gtk-launch", "org.example.Editor"])

    def test_launch_requires_approval_and_valid_id(self):
        with patch("jarvis.apps.shutil.which", return_value="/usr/bin/gtk-launch"), patch(
            "jarvis.apps.subprocess.Popen", side_effect=AssertionError("should not launch")
        ):
            self.assertEqual(
                launch_installed_app("org.example.Editor", lambda _: False)["status"],
                "rejected",
            )
            with self.assertRaises(ValueError):
                launch_installed_app("../unsafe", lambda _: True)

    def test_extra_roots_and_mutation_scope(self):
        workspace = self.base / "projects"
        documents = self.base / "Documents"
        downloads = self.base / "Downloads"
        for root in (workspace, documents, downloads):
            root.mkdir()
        with patch.dict(os.environ, {
            "JARVIS_ALLOWED_DIRS": str(documents) + os.pathsep + str(downloads)
        }):
            toolkit = Toolkit(workspace, approve=lambda _: True)
            self.assertEqual(len(toolkit.authorized_directories()), 3)
            result = toolkit.execute("make_directory", {"path": str(documents / "Teste")})
            self.assertEqual(result["result"]["status"], "created")
            self.assertTrue((documents / "Teste").is_dir())
            self.assertIn("error", toolkit.execute("make_directory", {"path": str(self.base / "other")}))
            self.assertIn("error", toolkit.execute("delete_path", {"path": str(documents)}))

    def test_mutation_rejects_symlink_escape(self):
        workspace = self.base / "projects"
        workspace.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        (workspace / "shortcut").symlink_to(outside, target_is_directory=True)
        toolkit = Toolkit(workspace, approve=lambda _: True)
        self.assertIn("error", toolkit.execute("make_directory", {"path": "shortcut/unsafe"}))
        self.assertFalse((outside / "unsafe").exists())

    def test_specs_exposed(self):
        names = {entry["name"] for entry in TOOL_SPECS}
        self.assertTrue({"list_installed_apps", "launch_installed_app",
                         "authorized_directories"} <= names)


if __name__ == "__main__":
    unittest.main()
