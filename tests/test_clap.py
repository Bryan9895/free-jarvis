import unittest
import numpy as np
from jarvis.clap import ClapDetector, ClapGate


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

    def test_every_sample_offset_including_split_impulses_activates_once(self):
        for offset in range(1280):
            detector = ClapDetector()
            signal = np.zeros(1280 * 4, dtype=np.int16)
            signal[1280 + offset:1280 + offset + 40:2] = 30000
            signal[1281 + offset:1280 + offset + 40:2] = -30000
            hits = sum(detector.process(signal[start:start + 1280], now=start / 16000)
                       for start in range(0, len(signal), 1280))
            self.assertEqual(hits, 1, offset)

    def test_disabled_gate_clears_partial_clap_history(self):
        detector = ClapDetector()
        first = np.zeros(1280, dtype=np.int16)
        first[-20:] = 30000
        self.assertFalse(detector.process(first, now=0))
        self.assertFalse(detector.process(np.zeros(1280, dtype=np.int16), enabled=False, now=.08))
        self.assertFalse(detector.process(np.zeros(1280, dtype=np.int16), now=.16))

    def test_holdback_flush_and_mode_transition_preserve_all_non_clap_samples(self):
        gate = ClapGate(ClapDetector())
        blocks = [np.arange(index * 1280, (index + 1) * 1280, dtype=np.int16) % 100
                  for index in range(4)]
        emitted = []
        for index, block in enumerate(blocks):
            decision = gate.feed(block, enabled=index < 2, defer=True, at=index, now=index * .08)
            self.assertFalse(decision.activated)
            if decision.pcm is not None: emitted.append(decision.pcm)
        final = gate.flush()
        if final.pcm is not None: emitted.append(final.pcm)
        np.testing.assert_array_equal(np.concatenate(emitted), np.concatenate(blocks))

    def test_flush_releases_last_frame_with_its_original_timestamp(self):
        gate = ClapGate(ClapDetector())
        frame = np.zeros(1280, dtype=np.int16)
        self.assertIsNone(gate.feed(frame, enabled=True, defer=True, at=12, now=0).pcm)
        result = gate.flush()
        self.assertEqual(result.at, 12)
        np.testing.assert_array_equal(result.pcm, frame)
        self.assertIsNone(gate.flush().pcm)
