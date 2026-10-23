"""Frames sintéticos: sem gravação ambiental e sem alegação de precisão VAD."""
import unittest
from jarvis.audio_endpoint import AudioEndpoint, TurnLimitError


class EndpointTests(unittest.TestCase):
    def test_long_turns_preserve_samples_and_short_internal_pause(self):
        for seconds in (3, 10, 25, 60):
            with self.subTest(seconds=seconds):
                endpoint = AudioEndpoint(1000)
                for _ in range(seconds * 10):
                    self.assertFalse(endpoint.feed(bytes(100), True))
                for _ in range(8):  # 800 ms não encerra com endpoint de 1 s
                    self.assertFalse(endpoint.feed(bytes(100), False))
                self.assertFalse(endpoint.feed(bytes(100), True))
                for _ in range(9):
                    self.assertFalse(endpoint.feed(bytes(100), False))
                self.assertTrue(endpoint.feed(bytes(100), False))
                self.assertEqual(sum(map(len, endpoint.chunks)), seconds * 1000 + 1900)

    def test_emergency_limit_cannot_return_partial_intention(self):
        endpoint = AudioEndpoint(1000, max_seconds=2)
        endpoint.feed(bytes(1000), True)
        with self.assertRaises(TurnLimitError):
            endpoint.feed(bytes(1000), True)
        self.assertEqual(endpoint.chunks, [])

    def test_silence_has_bounded_preroll_and_no_turn(self):
        endpoint = AudioEndpoint(1000)
        for _ in range(10000):
            self.assertFalse(endpoint.feed(bytes(100), False))
        self.assertFalse(endpoint.started)
        self.assertEqual(endpoint.chunks, [])
        self.assertLessEqual(endpoint.recent_samples, 800)

    def test_preroll_survives_start(self):
        endpoint = AudioEndpoint(1000)
        for _ in range(20):
            endpoint.feed(bytes(100), False)
        endpoint.feed(bytes(100), True)
        self.assertEqual(endpoint.samples, 800)
