import unittest
import numpy as np
from jarvis.clap import ClapDetector


class ClapTests(unittest.TestCase):
    def clap(self):
        frame = np.zeros(1280, dtype=np.int16)
        frame[400:440:2] = 30000
        frame[401:440:2] = -30000
        return frame

    def test_one_clap_debounce_and_disabled_gate(self):
        detector = ClapDetector()
        self.assertFalse(detector.process(self.clap(), enabled=False, now=0))
        self.assertTrue(detector.process(self.clap(), now=0))
        self.assertFalse(detector.process(self.clap(), now=1.49))
        self.assertTrue(detector.process(self.clap(), now=1.5))

    def test_silence_tone_and_sustained_noise_do_not_activate(self):
        detector = ClapDetector()
        tone = (np.sin(np.arange(1280) * .1) * 30000).astype(np.int16)
        noise = np.random.default_rng(12).integers(-30000, 30000, 1280, dtype=np.int16)
        for frame in (np.zeros(1280, dtype=np.int16), tone, noise):
            self.assertFalse(detector.process(frame))
