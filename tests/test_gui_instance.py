import os
from pathlib import Path
from threading import Event
import tempfile
from unittest import TestCase, skipUnless
from jarvis.gui_instance import GuiInstance


@skipUnless(__import__('sys').platform == 'linux', 'Linux session IPC')
class GuiInstanceTests(TestCase):
    def test_second_launch_shows_existing_without_another_gui_and_stale_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            first = GuiInstance(directory)
            second = GuiInstance(directory)
            third = GuiInstance(directory)
            requested = Event()
            try:
                self.assertTrue(first.acquire_or_show())
                self.assertEqual(first.path.stat().st_mode & 0o777, 0o600)
                first.serve(requested.set)
                self.assertFalse(second.acquire_or_show())
                self.assertTrue(requested.wait(1))
                first.close()
                third.path.touch()  # Stale entry after a terminated owner.
                self.assertTrue(third.acquire_or_show())
            finally:
                first.close()
                second.close()
                third.close()

    def test_rejects_shared_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o755)
            with self.assertRaises(PermissionError):
                GuiInstance(directory)
