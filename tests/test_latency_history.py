import unittest
from jarvis.latency_history import LatencyHistory


class HistoryTests(unittest.TestCase):
    def test_statistics_dont_contain_conversation(self):
        h = LatencyHistory(max_turns=3)
        for total, first in ((500, 100), (3000, 600), (750, 250), (900, None)):
            h.add(total, first)
        s = h.snapshot()
        self.assertEqual(s["turn"]["n"], 3)
        self.assertEqual(s["turn"]["p50"], 900)
        self.assertEqual(s["turn"]["p95"], 3000)
        self.assertEqual(s["first_text"]["p95"], 600)

    def test_invalid_metrics_fail_closed(self):
        h = LatencyHistory()
        for pair in ((10, 20), (-1, 0), (0, -1)):
            with self.assertRaises(ValueError):
                h.add(*pair)
