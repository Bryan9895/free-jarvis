"""Serviço compartilhado e cancelamento da sessão."""
import threading
import os
from time import monotonic
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from jarvis.approval import ApprovalPolicy
from jarvis.cancellation import CancelledError
from jarvis.service import JarvisService


class ServiceTests(unittest.TestCase):
    def test_cancel_before_service_registers_token_never_starts_action(self):
        from jarvis.conversation import ConversationController
        class DelayedService(JarvisService):
            def ask_stream(self, message, **kwargs):
                controller.cancel()
                return super().ask_stream(message, **kwargs)
        service = DelayedService(Mock(), Mock(), Mock(), Mock(), Mock(), ApprovalPolicy(), report=lambda _: None)
        controller = ConversationController(service)
        with self.assertRaises(CancelledError):
            controller.run('execute uma ação')
        service.agent.ask.assert_not_called()
        self.assertFalse(service._lock.locked())
    def test_invalid_deadline_never_leaves_service_locked_and_can_recover(self):
        service = self.service(Mock())
        for value in ('invalid', 'nan', 'inf', '0', '-1', '3601'):
            with self.subTest(value=value), patch.dict(os.environ, {'JARVIS_TURN_TIMEOUT': value}):
                with self.assertRaises(ValueError):
                    service.ask('pergunta')
                with self.assertRaises(ValueError):
                    service.plan_action('prepare', 'objetivo')
                self.assertFalse(service._lock.locked())
        with patch.dict(os.environ, {'JARVIS_TURN_TIMEOUT': '120'}):
            service.agent.ask.return_value = 'recuperado'
            self.assertEqual(service.ask('pergunta'), 'recuperado')

    def test_queue_time_consumes_deadline_without_executing_stale_intent(self):
        from jarvis.latency import TurnTrace, tracing
        service = self.service(Mock())
        trace = TurnTrace()
        trace.mark('intent_enqueued', at=monotonic() - 121)
        with patch.dict(os.environ, {'JARVIS_TURN_TIMEOUT': '120'}), tracing(trace):
            with self.assertRaises(TimeoutError):
                service.ask('pergunta')
        service.agent.ask.assert_not_called()
        self.assertFalse(service._lock.locked())
    def service(self, planner, approval=None):
        return JarvisService(Mock(), Mock(), Mock(), Mock(), planner,
                             approval or ApprovalPolicy(auto=True), report=lambda _: None)

    def test_plan_execute_uses_cancel_token_and_releases_lock(self):
        planner = Mock()
        planner.execute.return_value = {"status":"completed_verified"}
        service = self.service(planner)
        result = service.plan_action("execute")
        self.assertEqual(result["status"], "completed_verified")
        self.assertIsNotNone(planner.execute.call_args.kwargs["cancel_token"])
        self.assertFalse(service._lock.locked())
        self.assertFalse(service.cancel_current())

    def test_resolving_uncertain_step_requires_specific_confirmation(self):
        planner = Mock()
        snapshot = {"status":"interrupted", "steps":[
            {"id":1,"description":"Criar arquivo","status":"interrupted"}]}
        planner.snapshot.return_value = snapshot
        approval = ApprovalPolicy(auto=True, manual_callback=lambda _: False)
        service = self.service(planner, approval)
        self.assertEqual(service.plan_action("resolve", "retry"), snapshot)
        planner.resolve_step.assert_not_called()
        self.assertFalse(service._lock.locked())

    def test_plan_action_cannot_overlap_chat(self):
        service = self.service(Mock())
        service._lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, "execução"):
                service.plan_action("prepare", "Objetivo")
        finally:
            service._lock.release()

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
