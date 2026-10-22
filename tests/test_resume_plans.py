"""Recuperação supervisionada de tarefas sem repetição automática."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jarvis.plan_store import PlanStore
from jarvis.planner import TaskPlanner
from jarvis.plan_view import format_plan


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PlanStore(Path(self.tmp.name) / "plans.db")
        self.client = Mock()
        self.client.active_model = "openai/test"
        self.client.responses.return_value = {
            "output_text": '{"steps":["Listar arquivos","Inspecionar código","Resumir o projeto"]}'
        }
        self.agent = Mock()
        self.agent.model = "openai/test"
        self.agent.last_metrics = {}
        self.agent.ask.side_effect = ["Listados", "Inspecionados", "Resumo"]
        self.planner = TaskPlanner(self.client, self.agent, self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def interrupted_plan(self):
        plan = self.planner.prepare("Analisar repositório")
        self.planner.plan["status"] = "running"
        self.planner.plan["steps"][0]["status"] = "reported_unverified"
        self.planner.plan["steps"][0]["result"] = "Listados anteriormente"
        self.planner.plan["steps"][1]["status"] = "running"
        self.planner._save()
        return plan["id"]

    def test_select_historical_plan(self):
        first = self.planner.prepare("Analisar repositório")
        self.planner.prepare("Outra tarefa")
        selected = self.planner.select(first["id"])
        self.assertEqual(selected["id"], first["id"])
        self.assertEqual(selected["goal"], "Analisar repositório")
        with self.assertRaises(ValueError):
            self.planner.select(999999)
        with self.assertRaises(ValueError):
            self.planner.select(-3)

    def test_uncertain_step_needs_explicit_resolution(self):
        self.interrupted_plan()
        reloaded = TaskPlanner(self.client, self.agent, self.store)
        self.assertEqual(reloaded.plan["status"], "interrupted")
        with self.assertRaises(ValueError):
            reloaded.ready_to_resume()
        with self.assertRaises(ValueError):
            reloaded.execute(lambda _: True)
        self.agent.ask.assert_not_called()

    def test_skip_does_not_repeat_previous_action(self):
        self.interrupted_plan()
        recovered = TaskPlanner(self.client, self.agent, self.store)
        recovered.resolve_step("skip")
        panel = format_plan(recovered.snapshot())
        self.assertIn("Ignorada manualmente", panel)
        recovered.ready_to_resume()
        result = recovered.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "completed_unverified")
        self.assertEqual(result["steps"][0]["status"], "reported_unverified")
        self.assertEqual(result["steps"][1]["status"], "skipped_unverified")
        self.assertEqual(result["steps"][2]["status"], "reported_unverified")
        self.assertEqual(self.agent.ask.call_count, 1)
        self.assertEqual(self.agent.ask.call_args.args[0], "Resumir o projeto")

    def test_retry_requeues_only_uncertain_step(self):
        self.interrupted_plan()
        recovered = TaskPlanner(self.client, self.agent, self.store)
        recovered.resolve_step("retry")
        recovered.ready_to_resume()
        result = recovered.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "completed_unverified")
        self.assertEqual(self.agent.ask.call_count, 2)
        self.assertEqual(self.agent.ask.call_args_list[0].args[0], "Inspecionar código")
        self.assertEqual(self.agent.ask.call_args_list[1].args[0], "Resumir o projeto")

    def test_retry_must_not_be_automatic(self):
        self.interrupted_plan()
        recovered = TaskPlanner(self.client, self.agent, self.store)
        recovered.resolve_step("retry")
        self.assertEqual(recovered.snapshot()["status"], "stopped")
        self.agent.ask.assert_not_called()
        with self.assertRaises(ValueError):
            recovered.execute(lambda _: True)

if __name__ == "__main__":
    unittest.main()
