import unittest

from jarvis.loop_guard import LoopGuard


class LoopGuardTests(unittest.TestCase):
    def test_alternating_cycle_is_detected(self):
        guard = LoopGuard()
        values = [guard.observe(name) for name in ("a", "b", "a", "b", "a", "b")]
        self.assertEqual(values, [False, False, False, False, False, True])

    def test_distinct_calls_are_allowed(self):
        guard = LoopGuard()
        self.assertFalse(any(guard.observe(name) for name in ("a", "b", "c", "d")))


if __name__ == "__main__":
    unittest.main()
