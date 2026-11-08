"""Smoke visual real do Canvas Tkinter em DISPLAY virtual (Xvfb)."""
import os
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jarvis.preferences import Preferences
from jarvis.gui import AdamWindow, ParticleSphere


@unittest.skipUnless(os.getenv("DISPLAY"), "Exige X11/Xvfb; teste físico GNOME separado")
class NativeTkTests(unittest.TestCase):
    def test_canvas_renders_particles_and_reacts_to_state_and_level(self):
        root = tk.Tk()
        root.withdraw()
        try:
            sphere = ParticleSphere(root, points=240, fps=30, width=600, height=450)
            sphere.pack()
            root.deiconify()
            root.update()
            self.assertEqual(len(sphere.items), 240)
            self.assertGreaterEqual(len(sphere.find_all()), 240)
            before = sphere.coords(sphere.items[33])
            sphere.set_state("ouvindo")
            sphere.set_level(0.7)
            root.after(90, root.quit)
            root.mainloop()
            after = sphere.coords(sphere.items[33])
            self.assertNotEqual(before, after)
        finally:
            root.destroy()

    def test_text_only_mode_disables_microphone_and_keeps_desktop(self):
        root = tk.Tk()
        try:
            with patch.dict(os.environ, {"JARVIS_GUI_VOICE": "0"}), patch(
                    "jarvis.preferences.PreferenceStore.load",
                    return_value=Preferences(voice_mode="continuous")):
                window = AdamWindow(root, SimpleNamespace(profile="fcc", model=""), auto=False)
            root.update()
            self.assertTrue(window.details)
            self.assertEqual(str(window.mic_button.cget("state")), "disabled")
            self.assertIsNone(window.listener)
            window.close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_desktop_window_starts_without_fcc_or_microphone(self):
        root = tk.Tk()
        try:
            with patch("jarvis.preferences.PreferenceStore.load",
                       return_value=Preferences(voice_mode="muted")):
                window = AdamWindow(root, SimpleNamespace(profile="fcc", model=""), auto=False)
            root.update()
            self.assertEqual(window.orb.state, "parado")
            self.assertFalse(window.listener is not None)
            window.close()
        finally:
            try:
                if root.winfo_exists():
                    root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
