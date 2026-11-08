"""Smoke visual real do Canvas Tkinter em DISPLAY virtual (Xvfb)."""
import os
import tkinter as tk
import tempfile
import time
import threading
from pathlib import Path
from jarvis.preferences import PreferenceStore
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

    def test_settings_saves_preference_without_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            root = tk.Tk()
            try:
                with patch.dict(os.environ, {
                    "JARVIS_GUI_VOICE": "0",
                    "JARVIS_PREFERENCES": str(Path(td) / "prefs.json"),
                    "ELEVENLABS_API_KEY": "",
                }):
                    window = AdamWindow(root, SimpleNamespace(profile="fcc", model=""), auto=False)
                    window.settings()
                    root.update()
                    dialog = window.dialog
                    self.assertTrue(dialog.winfo_exists())
                    panel = dialog.winfo_children()[0]
                    buttons = [widget for widget in panel.winfo_children()
                               if isinstance(widget, tk.Button)]
                    buttons[-1].invoke()
                    root.update()
                    settings = PreferenceStore().load()
                    self.assertEqual(settings.tts_backend, "elevenlabs")
                    self.assertFalse("ELEVENLABS_API_KEY" in settings.__dict__)
                    window.close()
            finally:
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_text_stream_reaches_tk_with_fake_fcc_service(self):
        class FakeService:
            supports_turn_cancellation = True
            agent = SimpleNamespace(last_metrics={})
            def ask_stream(self, message, on_text=None, cancel_token=None):
                self.message = message
                on_text("ADAM ")
                on_text("funcionou.")
                return "ADAM funcionou."
            def close(self):
                pass
            def cancel_current(self):
                pass
        fake = FakeService()
        root = tk.Tk()
        try:
            with patch.dict(os.environ, {"JARVIS_GUI_VOICE": "0"}), patch(
                    "jarvis.preferences.PreferenceStore.load",
                    return_value=Preferences(voice_mode="muted")), patch(
                    "jarvis.service.JarvisService.from_config", return_value=fake):
                window = AdamWindow(root, SimpleNamespace(profile="fcc", model=""), auto=False)
                self.assertTrue(window._enqueue("teste do FCC"))
                deadline = time.monotonic() + 2.
                while ((window.result.get() != "ADAM funcionou." or not window.metrics.get())
                       and time.monotonic() < deadline):
                    root.update()
                    time.sleep(.01)
                self.assertEqual(fake.message, "teste do FCC")
                self.assertEqual(window.result.get(), "ADAM funcionou.")
                self.assertTrue(window.metrics.get())
                window.close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_approval_request_is_presented_on_tk_main_thread(self):
        root = tk.Tk()
        try:
            with patch.dict(os.environ, {"JARVIS_GUI_VOICE": "0"}), patch(
                    "jarvis.preferences.PreferenceStore.load",
                    return_value=Preferences(voice_mode="muted")):
                window = AdamWindow(root, SimpleNamespace(profile="fcc", model=""), auto=False)
            result = []
            worker = threading.Thread(
                target=lambda: result.append(window._ask_approval("Abrir programa?")),
                daemon=True)
            with patch("jarvis.gui.messagebox.askyesno", return_value=True) as dialog:
                worker.start()
                deadline = time.monotonic() + 2.
                while worker.is_alive() and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                worker.join(timeout=.1)
                self.assertEqual(result, [True])
                dialog.assert_called_once()
            window.close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

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
