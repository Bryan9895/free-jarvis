import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import numpy as np
from jarvis.audio_activity import PCMNormalizer, SileroActivity


class ActivityTests(unittest.TestCase):
    def test_loud_noise_is_not_speech_when_classifier_rejects_it(self):
        model = Mock(return_value=np.full(3, .1))
        with patch.dict(sys.modules, {'faster_whisper.vad': SimpleNamespace(get_vad_model=lambda: model)}):
            activity = SileroActivity()
        self.assertFalse(activity.active(np.full(1280, 30000, dtype=np.int16)))
        self.assertTrue(np.all(abs(model.call_args.args[0]) <= 1))
        model.return_value = np.full(3, .9)
        self.assertTrue(activity.active(np.full(1280, 100, dtype=np.int16)))

    def test_classifier_context_is_bounded(self):
        model = Mock(return_value=np.zeros(16))
        with patch.dict(sys.modules, {'faster_whisper.vad': SimpleNamespace(get_vad_model=lambda: model)}):
            activity = SileroActivity()
        for _ in range(100):
            self.assertFalse(activity.active(np.zeros(1280, dtype=np.int16)))
        self.assertLessEqual(len(activity._recent), 8192)
        self.assertEqual(len(model.call_args.args[0]) % 512, 0)

    def test_native_rate_conversion_is_continuous_and_flushes_tail(self):
        normalizer = PCMNormalizer(48000)
        frames = []
        for _ in range(10):
            frames.append(normalizer.feed(np.full((4800, 2), 1000, dtype=np.int16)))
        frames.append(normalizer.flush())
        mono = np.concatenate(frames)
        self.assertEqual(len(mono), 16000)
        self.assertEqual(mono.ndim, 1)
        self.assertGreater(float(mono.mean()), 990)

    def test_target_rate_does_not_create_resampler(self):
        normalizer = PCMNormalizer(16000)
        pcm = np.ones(1280, dtype=np.int16)
        self.assertIs(normalizer.feed(pcm), pcm)
        self.assertIsNone(normalizer._resampler)
