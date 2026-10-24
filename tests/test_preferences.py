from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from jarvis.preferences import Preferences, PreferenceStore


class PreferenceTests(unittest.TestCase):
    def test_followup_recovery_roundtrip_and_old_file_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            store = PreferenceStore(Path(td) / 'preferences.json')
            store.path.write_text('{"version": 1, "stt_model": "small"}')
            self.assertEqual(store.load().followup_seconds, 20)
            preferences = replace(store.load(), followup_seconds=60, start_timeout_seconds=10, reconnect_attempts=0)
            store.save(preferences)
            self.assertEqual(store.load(), preferences)
            for changes in ({'followup_seconds': 0}, {'start_timeout_seconds': 2}, {'reconnect_attempts': 6}):
                with self.assertRaises(ValueError):
                    replace(preferences, **changes).validate()
        with patch.dict(os.environ, {'JARVIS_FOLLOWUP_SECONDS': '30', 'JARVIS_START_TIMEOUT_SECONDS': '12', 'JARVIS_AUDIO_RETRIES': '4'}):
            effective = Preferences().effective()
            self.assertEqual((effective.followup_seconds, effective.start_timeout_seconds, effective.reconnect_attempts), (30, 12, 4))

    def test_roundtrip_atomic_private_file_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            store = PreferenceStore(Path(td) / 'preferences.json')
            saved = replace(store.load(), piper_model='/tmp/voz.onnx', conversation_model='modelo')
            store.save(saved)
            self.assertEqual(store.load(), saved)
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(td).iterdir()), [store.path])
            self.assertNotIn('token', store.path.read_text())

    def test_invalid_config_recovers_visibly_without_overwriting_file(self):
        with tempfile.TemporaryDirectory() as td:
            store = PreferenceStore(Path(td) / 'preferences.json')
            for value in ('{', '{"version": 99}', '{"silence_ms": 400}', '{"FCC_TOKEN":"secret"}'):
                store.path.write_text(value)
                self.assertEqual(store.load(), Preferences())
                self.assertIsNotNone(store.error)
                self.assertEqual(store.path.read_text(), value)

    def test_environment_overrides_saved_values(self):
        saved = Preferences(piper_model='/saved', conversation_model='saved', silence_ms=800)
        with patch.dict(os.environ, {'JARVIS_PIPER_MODEL': '/explicit', 'FCC_MODEL': 'explicit',
                                     'JARVIS_SILENCE_MS': '1200'}):
            effective = saved.effective()
        self.assertEqual(effective.piper_model, '/explicit')
        self.assertEqual(effective.conversation_model, 'explicit')
        self.assertEqual(effective.silence_ms, 1200)
        self.assertEqual(saved.piper_model, '/saved')

    def test_failed_replace_preserves_previous_preferences(self):
        with tempfile.TemporaryDirectory() as td:
            store = PreferenceStore(Path(td) / 'preferences.json')
            store.save(Preferences())
            with patch('jarvis.preferences.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    store.save(Preferences(silence_ms=1800))
            self.assertEqual(store.load().silence_ms, 1000)
            self.assertEqual(list(Path(td).iterdir()), [store.path])
