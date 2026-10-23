"""Serviço compartilhado e cancelamento da sessão."""
import threading
import unittest
from types import SimpleNamespace

from jarvis.approval import ApprovalPolicy
from jarvis.cancellation import CancelledError
from jarvis.service import JarvisService


class ServiceTests(unittest.TestCase):
    def test_cancel_current_stops_new_work_and_returns_cancelled_result(self):
        started = threading.Event()
        release = threading.Event()
        errors = []

        class Agent:
            def ask(self, _message, cancel_token=None):
                started.set()
                release.wait(2)
                cancel_token.check()

        class Toolkit:
            def close(self):
                pass

        class Memory:
            def close(self):
                pass

        planner = SimpleNamespace(history=lambda _limit: [], snapshot=lambda: {"status": "no_plan"})
        service = JarvisService(None, Agent(), Toolkit(), Memory(), planner,
                                ApprovalPolicy(auto=True), report=lambda _message: None)

        def run():
            try:
                service.ask("Explique este conceito")
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(started.wait(2))
        self.assertTrue(service.cancel_current())
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], CancelledError)
        self.assertFalse(service.cancel_current())


if __name__ == "__main__":
    unittest.main()
