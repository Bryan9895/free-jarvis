from dataclasses import replace
import os
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.gui import GuiBackend, JarvisWindow
from jarvis.preferences import Preferences, PreferenceStore


class KokoroBackendTests(unittest.TestCase):
    def test_install_failure_preserves_voice_then_retry_applies_verified_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'JARVIS_PREFERENCES': directory + '/prefs.json'}, clear=True):
            store = PreferenceStore()
            store.save(Preferences(piper_model='/previous.onnx'))
            backend = GuiBackend(SimpleNamespace())
            with patch('jarvis.kokoro_setup.install_runtime', side_effect=RuntimeError('network failed')):
                with self.assertRaises(RuntimeError):
                    backend._dispatch('voice_install_kokoro', None)
            self.assertEqual(store.load().piper_model, '/previous.onnx')
            self.assertEqual(store.load().tts_backend, 'piper')
            with patch('jarvis.kokoro_setup.install_runtime', return_value={'python': '/verified/python'}), \
                    patch('jarvis.kokoro_assets.install_assets', return_value=Path('/verified/weights')):
                backend._dispatch('voice_install_kokoro', None)
            saved = store.load()
            self.assertEqual((saved.tts_backend, saved.kokoro_python, saved.kokoro_directory),
                             ('kokoro', '/verified/python', '/verified/weights'))
            self.assertEqual(saved.piper_model, '/previous.onnx')
            self.assertIsNone(backend.service)


@unittest.skipUnless(os.getenv('DISPLAY'), 'Display gráfico indisponível')
class KokoroWindowTests(unittest.TestCase):
    def test_gui_persists_backend_and_busy_controls_without_automatic_install(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'JARVIS_PREFERENCES': directory + '/prefs.json', 'JARVIS_GUI_VOICE': '0'}):
            backend = Mock()
            backend.events = queue.Queue()
            root = tk.Tk()
            try:
                with patch('jarvis.kokoro_assets.install_assets') as install:
                    window = JarvisWindow(root, backend)
                    root.update_idletasks()
                    install.assert_not_called()
                window.voice_tts_backend.set('kokoro')
                window.voice_kokoro_directory.set('/weights')
                window.voice_kokoro_python.set('/python3.12')
                backend.reset_mock()
                window.voice_save_button.invoke()
                command, options = backend.submit.call_args.args
                self.assertEqual(command, 'voice_configure')
                self.assertEqual(options['tts_backend'], 'kokoro')
                self.assertEqual(options['kokoro_directory'], '/weights')
                window._handle('busy', True)
                self.assertEqual(str(window.voice_kokoro_install_button['state']), 'disabled')
                window._handle('busy', False)
                self.assertEqual(str(window.voice_kokoro_install_button['state']), 'normal')
                window._handle('voice_preferences', Preferences(tts_backend='kokoro', kokoro_directory='/saved'))
                self.assertEqual(window.voice_kokoro_directory.get(), '/saved')
            finally:
                root.destroy()
