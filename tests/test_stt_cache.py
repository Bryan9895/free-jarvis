import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from jarvis import stt_cache


class ModelCacheTests(unittest.TestCase):
    def test_same_model_is_reused_and_different_model_replaces_it(self):
        factory = Mock(side_effect=[object(), object()])
        with patch.object(stt_cache, '_model', None), patch.object(stt_cache, '_name', None), patch.dict(
                sys.modules, {'faster_whisper': SimpleNamespace(WhisperModel=factory)}):
            with stt_cache.whisper_model('small') as first:
                pass
            with stt_cache.whisper_model('small') as reused:
                self.assertIs(reused, first)
            with stt_cache.whisper_model('base') as second:
                self.assertIsNot(second, first)
            self.assertEqual(factory.call_count, 2)
            factory.assert_called_with('base', device='cpu', compute_type='int8')

    def test_failed_load_releases_lock_and_does_not_keep_old_model(self):
        factory = Mock(side_effect=[RuntimeError('modelo ausente'), object()])
        with patch.object(stt_cache, '_model', object()), patch.object(stt_cache, '_name', 'old'), patch.dict(
                sys.modules, {'faster_whisper': SimpleNamespace(WhisperModel=factory)}):
            with self.assertRaises(RuntimeError):
                with stt_cache.whisper_model('small'):
                    pass
            self.assertIsNone(stt_cache._model)
            with stt_cache.whisper_model('small') as recovered:
                self.assertIsNotNone(recovered)
