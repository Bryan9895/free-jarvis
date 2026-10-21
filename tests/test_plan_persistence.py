"""Persistência SQLite e interface legível de tarefas."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jarvis.plan_store import PlanStore
from jarvis.planner import TaskPlanner
from jarvis.plan_view import format_plan, format_history


class PersistentPlansTests(unittest.TestCase):
    def _create(self, store):
        client = Mock()
        client.active_model = "openai/test"
        client.responses.return_value = {
            "output_text": '{"steps":["Listar arquivos","Inspecionar projeto"]}'
        }
        agent = Mock()
        agent.model = "openai/test"
        agent.last_metrics = {}
        agent.ask.side_effect = ["Arquivos vistos", "Projeto descrito"]
        return TaskPlanner(client, agent, store=store), agent

    def test_plan_persists_after_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tasks.sqlite3"
            store = PlanStore(path)
            planner, _ = self._create(store)
            created = planner.prepare("Analisar workspace")
            self.assertEqual(created["status"], "ready")
            self.assertIsInstance(created["id"], int)
            store.close()
            second = PlanStore(path)
            restored, _ = self._create(second)
            self.assertEqual(restored.snapshot()["id"], created["id"])
            self.assertEqual(restored.snapshot()["goal"], "Analisar workspace")
            second.close()

    def test_checkpoints_saved_at_each_step(self):
        with tempfile.TemporaryDirectory() as td:
            store = PlanStore(Path(td) / "tasks.sqlite3")
            planner, agent = self._create(store)
            planner.prepare("Analisar workspace")
            def inspect(_):
                # Checkpoints visible even during execution.
                self.assertEqual(store.latest()["status"], "running")
                return True
            result = planner.execute(inspect, report=lambda _: None)
            self.assertEqual(result["status"], "completed_unverified")
            self.assertEqual(store.latest()["steps"][0]["status"], "reported_unverified")
            self.assertEqual(agent.ask.call_count, 2)
            store.close()

    def test_running_state_recovers_as_interrupted_no_autoreplay(self):
        with tempfile.TemporaryDirectory() as td:
            store = PlanStore(Path(td) / "tasks.sqlite3")
            planner, agent = self._create(store)
            planner.prepare("Analisar workspace")
            planner.plan["status"] = "running"
            planner.plan["steps"][0]["status"] = "running"
            planner._save()
            restored, new_agent = self._create(store)
            self.assertEqual(restored.snapshot()["status"], "interrupted")
            self.assertEqual(restored.snapshot()["steps"][0]["status"], "interrupted")
            self.assertEqual(store.latest()["status"], "interrupted")
            with self.assertRaises(ValueError):
                restored.execute(lambda _: True)
            new_agent.ask.assert_not_called()
            store.close()

    def test_history_retains_old_plans(self):
        with tempfile.TemporaryDirectory() as td:
            store = PlanStore(Path(td) / "tasks.sqlite3")
            planner, _ = self._create(store)
            old = planner.prepare("Primeira tarefa")
            newer = planner.prepare("Segunda tarefa")
            self.assertNotEqual(old["id"], newer["id"])
            history = planner.history()
            self.assertEqual([p["goal"] for p in history], ["Segunda tarefa", "Primeira tarefa"])
            store.close()

    def test_view_has_no_raw_json_and_is_honest(self):
        with tempfile.TemporaryDirectory() as td:
            store = PlanStore(Path(td) / "tasks.sqlite3")
            planner, _ = self._create(store)
            planner.prepare("Analisar workspace")
            display = format_plan(planner.snapshot())
            self.assertIn("PLANO DE TAREFA", display)
            self.assertIn("Analisar workspace", display)
            self.assertIn("0/2 etapas", display)
            self.assertNotIn('"steps":', display)
            history = format_history(planner.history())
            self.assertIn("HISTÓRICO DE PLANOS", history)
            self.assertIn("Primeira", format_history([{"goal":"Primeira", "steps": [], "status":"ready"}]))
            store.close()

if __name__ == "__main__":
    unittest.main()
