"""Cancelamento impede novas ações e preserva estado incerto para retomada."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jarvis.agent import Agent
from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.memory import Memory
from jarvis.planner import TaskPlanner
from jarvis.tools import Toolkit


class CancellingClient:
    def __init__(self, token):
        self.token = token

    def responses(self, _payload):
        self.token.cancel()
        return {"output": [{"type": "function_call", "name": "write_file",
                            "call_id": "one", "arguments": '{"path":"danger","content":"x"}'}]}


class CancellationTests(unittest.TestCase):
    def test_direct_tool_call_is_blocked_before_side_effect(self):
        token = CancellationToken()
        token.cancel()
        with tempfile.TemporaryDirectory() as temp:
            kit = Toolkit(Path(temp), approve=lambda _: True)
            with self.assertRaises(CancelledError):
                kit.execute("write_file", {"path": "danger", "content": "x"},
                            cancel_token=token)
            self.assertFalse((Path(temp) / "danger").exists())
            kit.close()

    def test_agent_drops_tool_call_after_cancel_during_model_response(self):
        token = CancellationToken()
        with tempfile.TemporaryDirectory() as temp:
            kit = Toolkit(Path(temp), approve=lambda _: True)
            memory = Memory(Path(temp) / "memory.db")
            agent = Agent(CancellingClient(token), kit, memory, "fake")
            with self.assertRaises(CancelledError):
                agent.ask("Escreva danger", cancel_token=token)
            self.assertFalse((Path(temp) / "danger").exists())
            self.assertTrue(agent.last_metrics["cancelled"])
            kit.close()
            memory.close()

    def test_plan_keeps_later_steps_pending_after_cancel(self):
        token = CancellationToken()
        agent = Mock()
        agent.ask.side_effect = lambda *_args, **_kwargs: token.cancel() or "Concluído"
        planner = TaskPlanner(Mock(), agent)
        planner.plan = {"goal": "teste", "status": "ready", "steps": [
            {"id": 1, "description": "Escrever arquivo", "status": "pending", "result": ""},
            {"id": 2, "description": "Abrir projeto", "status": "pending", "result": ""},
        ]}
        state = planner.execute(lambda _: True, report=lambda _: None, cancel_token=token)
        self.assertEqual(state["status"], "interrupted")
        self.assertEqual(state["steps"][0]["status"], "interrupted")
        self.assertEqual(state["steps"][1]["status"], "pending")
        self.assertEqual(agent.ask.call_count, 1)


if __name__ == "__main__":
    unittest.main()
