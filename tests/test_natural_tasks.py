"""Regressões do orquestrador de tarefas via linguagem natural."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jarvis.plan_store import PlanStore
from jarvis.planner import TaskPlanner
from jarvis.natural_tasks import NaturalTaskController
from jarvis.task_intent import classify, find_relevant


class NaturalTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PlanStore(Path(self.tmp.name) / "test.db")
        self.client = Mock()
        self.client.active_model = "openai/test"
        self.client.responses.return_value = {
            "output_text": '{"steps":["Listar arquivos do workspace","Explicar organização do código"]}'
        }
        self.agent = Mock()
        self.agent.model = "openai/test"
        self.agent.last_metrics = {}
        self.agent.ask.return_value = "Etapa processada"
        self.planner = TaskPlanner(self.client, self.agent, self.store)
        self.approvals = []
        def approve(message):
            self.approvals.append(message)
            return True
        self.controller = NaturalTaskController(
            self.planner, approve, report=lambda _: None
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_simple_questions_bypass_planner_and_extra_fcc_calls(self):
        for sentence in ("O que é Python?", "Explique inteligência artificial.",
                         "Bom dia", "Quanto é dois mais dois?"):
            self.assertIsNone(self.controller.handle(sentence))
        self.client.responses.assert_not_called()

    def test_multipart_local_task_plans_then_runs(self):
        result = self.controller.handle(
            "Liste os arquivos do workspace e depois explique sua organização"
        )
        self.assertIn("PLANO DE TAREFA", result)
        self.assertIn("Etapas processadas", result)
        self.assertEqual(self.client.responses.call_count, 1)
        self.assertEqual(self.agent.ask.call_count, 2)
        self.assertEqual(len(self.approvals), 1)

    def test_natural_plan_without_autoexecution(self):
        result = self.controller.handle(
            "Jarvis, planeje uma análise dos arquivos do meu projeto."
        )
        self.assertIn("Pronto para executar", result)
        self.assertEqual(self.agent.ask.call_count, 0)
        self.assertEqual(self.controller.handle("execute o plano").count("PLANO DE TAREFA"), 1)
        self.assertEqual(self.agent.ask.call_count, 2)

    def test_readable_natural_history_and_status(self):
        self.planner.prepare("Listar arquivos do workspace")
        history = self.controller.handle("Mostre o histórico das minhas tarefas")
        self.assertIn("HISTÓRICO DE PLANOS", history)
        status = self.controller.handle("Como está o andamento do meu plano?")
        self.assertIn("PLANO DE TAREFA", status)
        self.assertNotIn('"steps":', status)

    def test_resume_uncertain_does_not_retry_without_choice(self):
        self.planner.prepare("Analise os arquivos Python do projeto")
        plan = self.planner.plan
        plan["status"] = "interrupted"
        plan["steps"][0]["status"] = "interrupted"
        self.planner._save()
        answer = self.controller.handle("Continue a análise do meu projeto de onde parou")
        self.assertIn("resultado incerto", answer)
        self.agent.ask.assert_not_called()
        self.assertEqual(self.controller.handle("ignore a etapa interrompida").count("PLANO DE TAREFA"), 1)
        result = self.controller.handle("Continue de onde parou")
        self.assertIn("PLANO DE TAREFA", result)
        self.assertEqual(self.agent.ask.call_count, 1)
        self.assertEqual(self.planner.snapshot()["steps"][0]["status"], "skipped_unverified")

    def test_natural_retry_queues_but_does_not_execute(self):
        self.planner.prepare("Inspecionar projeto")
        self.planner.plan["status"] = "interrupted"
        self.planner.plan["steps"][0]["status"] = "interrupted"
        self.planner._save()
        self.controller.handle("repita a etapa interrompida")
        self.agent.ask.assert_not_called()
        self.assertEqual(self.planner.snapshot()["steps"][0]["status"], "pending")

    def test_ambiguous_recovery_does_not_pick_plan(self):
        self.planner.prepare("Revisar arquivos do laboratório")
        self.planner.prepare("Verificar arquivos do site")
        before = self.planner.snapshot()["id"]
        answer = self.controller.handle("Continue arquivos de onde parou")
        self.assertIn("várias tarefas", answer)
        self.assertEqual(self.planner.snapshot()["id"], before)
        self.agent.ask.assert_not_called()

    def test_cancel_and_denied_action(self):
        self.planner.prepare("Inspecionar projeto")
        self.assertIn("Cancelado", self.controller.handle("cancele o plano"))
        self.agent.ask.assert_not_called()

    def test_intents_remain_conservative(self):
        self.assertEqual(classify("O que é Python?"), "normal")
        self.assertEqual(classify("Abra o gerenciador de arquivos"), "normal")
        self.assertEqual(classify("Organize as janelas lado a lado"), "normal")
        self.assertEqual(classify("Coloque Firefox na metade direita"), "normal")
        self.assertEqual(classify("Jarvis, identifique a janela do Firefox e coloque-a em primeiro plano."), "normal")
        self.assertEqual(classify("Jarvis, coloque a janela do Firefox em primeiro plano."), "normal")
        self.assertEqual(classify("Liste arquivos e depois analise o projeto"), "plan_execute")
        self.assertEqual(classify("Continue de onde parou"), "resume")
        self.assertEqual(classify("Me mostre o histórico das tarefas"), "history")
        self.assertEqual(classify("ignore a etapa interrompida"), "resolve_skip")

if __name__ == "__main__":
    unittest.main()
