"""Testes do planejador: sem FCC real nem ações no desktop."""
import unittest
from unittest.mock import Mock

from jarvis.planner import TaskPlanner, _extract_plan


class PlannerTests(unittest.TestCase):
    def test_accepts_json_and_fenced_explanation(self):
        plan = _extract_plan('Plano:\n```json\n{"steps":["Listar arquivos","Ler documento"]}\n```')
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["status"], "pending")
        self.assertEqual(plan[1]["depends_on"], [])

    def test_validates_explicit_step_dependencies(self):
        plan = _extract_plan('{"steps":[{"description":"Criar arquivo","depends_on":[]},'
                             '{"description":"Abrir arquivo","depends_on":[1]}]}')
        self.assertEqual(plan[1]["depends_on"], [1])
        for invalid in (
            '{"steps":[{"description":"Criar arquivo","depends_on":[1]}]}',
            '{"steps":["Etapa um",{"description":"Etapa dois","depends_on":[2]}]}',
            '{"steps":["Etapa um",{"description":"Etapa dois","depends_on":[1,1]}]}',
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                _extract_plan(invalid)

    def test_rejects_malformed_or_oversized_plans(self):
        bad = [
            "Olá", '{"steps":[]}', '{"steps":["a"]}',
            '{"steps":["Etapa 1","Etapa 2","Etapa 3","Etapa 4","Etapa 5","Etapa 6"]}',
            '{"steps":["Ler arquivo"]} outro {"steps":["Ler arquivo"]}',
            '{"steps":[42]}',
        ]
        for response in bad:
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    _extract_plan(response)

    def make_planner(self, model_response=None):
        client = Mock()
        client.active_model = "ollama/qwen3.5:2b"
        client.responses.return_value = {"output_text": model_response or
            '{"steps":["Listar arquivos do workspace","Descrever a estrutura"]}'}
        agent = Mock()
        agent.model = "ollama/qwen3.5:2b"
        agent.ask.side_effect = ["Arquivos listados", "Estrutura descrita"]
        return TaskPlanner(client, agent), client, agent

    def test_plan_only_never_calls_tools(self):
        planner, client, agent = self.make_planner()
        result = planner.prepare("Analise meu projeto")
        self.assertEqual(result["status"], "ready")
        payload = client.responses.call_args.args[0]
        self.assertEqual(payload["tools"], [])
        self.assertEqual(payload["reasoning"], {"effort": "none"})
        self.assertEqual(len(result["steps"]), 2)
        agent.ask.assert_not_called()

    def test_explicit_approval_required(self):
        planner, _, agent = self.make_planner()
        planner.prepare("Analise meu projeto")
        result = planner.execute(lambda _: False, report=lambda _: None)
        self.assertEqual(result["status"], "cancelled")
        agent.ask.assert_not_called()

    def test_executes_steps_one_by_one_without_claiming_verification(self):
        planner, _, agent = self.make_planner()
        planner.prepare("Analise meu projeto")
        result = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "completed_unverified")
        self.assertEqual([s["status"] for s in result["steps"]],
                         ["reported_unverified", "reported_unverified"])
        self.assertEqual(agent.ask.call_count, 2)
        self.assertEqual(agent.ask.call_args_list[0].kwargs["mode"], "tools")

    def test_failure_stops_following_steps(self):
        planner, _, agent = self.make_planner()
        agent.ask.side_effect = ValueError("FCC não disponível")
        planner.prepare("Analise meu projeto")
        result = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["steps"][0]["status"], "failed")
        self.assertEqual(result["steps"][1]["status"], "pending")
        self.assertEqual(agent.ask.call_count, 1)

    def test_unverified_dependency_blocks_dependent_step(self):
        planner, client, agent = self.make_planner(
            '{"steps":[{"description":"Inspecionar projeto","depends_on":[]},'
            '{"description":"Editar arquivo encontrado","depends_on":[1]}]}')
        agent.last_metrics = {"tool_problems": [], "tool_outcomes": [], "tools_executed": 0}
        planner.prepare("Inspecionar e editar projeto")
        result = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual([s["status"] for s in result["steps"]],
                         ["reported_unverified", "blocked"])
        self.assertEqual(agent.ask.call_count, 1)

    def test_tool_rejection_stops_following_steps(self):
        planner, _, agent = self.make_planner()
        agent.last_metrics = {"tool_problems": [{"tool": "write_file", "reason": "rejected"}]}
        planner.prepare("Analise meu projeto")
        result = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["steps"][0]["status"], "blocked")
        self.assertEqual(result["steps"][1]["status"], "pending")
        self.assertEqual(agent.ask.call_count, 1)

    def test_cancel_invalidates_plan_and_new_plan_replaces_old(self):
        planner, _, agent = self.make_planner()
        planner.prepare("Tarefa antiga")
        planner.cancel()
        with self.assertRaises(ValueError):
            planner.execute(lambda _: True, report=lambda _: None)
        planner.prepare("Tarefa nova")
        self.assertEqual(planner.snapshot()["goal"], "Tarefa nova")
        agent.ask.assert_not_called()

    def test_focus_plan_does_not_accept_model_claim_without_tool_evidence(self):
        planner, client, agent = self.make_planner(
            '{"steps":["Colocar a janela do Firefox em primeiro plano",'
            '"Ativar a janela do Firefox novamente"]}')
        agent.ask.return_value = "O foco foi confirmado pelo GNOME."
        agent.ask.side_effect = None
        agent.last_metrics = {"tool_problems": [], "tool_outcomes": [],
                              "tools_executed": 0}
        planner.prepare("Focar Firefox")
        state = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(state["status"], "stopped")
        self.assertEqual(state["steps"][0]["status"], "blocked")
        self.assertEqual(state["steps"][1]["status"], "pending")
        self.assertEqual(agent.ask.call_count, 1)

    def test_focus_plan_verified_only_from_tool_status(self):
        planner, _, agent = self.make_planner(
            '{"steps":["Colocar a janela do Firefox em primeiro plano"]}')
        agent.ask.side_effect = None
        agent.ask.return_value = "Firefox em primeiro plano."
        agent.last_metrics = {"tool_problems": [], "tools_executed": 1,
                              "tool_outcomes": [{"name": "focus_window",
                                  "outcome": {"result": {"status": "focused_verified"}}}]}
        planner.prepare("Focar Firefox")
        state = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(state["status"], "completed_verified")
        self.assertEqual(state["steps"][0]["status"], "verified")

    def test_focus_plan_unavailable_blocks_remaining_steps(self):
        planner, _, agent = self.make_planner(
            '{"steps":["Ativar a janela do Firefox", "Listar arquivos do workspace"]}')
        agent.ask.side_effect = None
        agent.ask.return_value = "Não consegui ativar."
        agent.last_metrics = {"tool_problems": [], "tools_executed": 1,
                              "tool_outcomes": [{"name": "focus_window",
                                  "outcome": {"result": {"status": "not_observed"}}}]}
        planner.prepare("Focar Firefox")
        state = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(state["status"], "stopped")
        self.assertEqual(state["steps"][0]["status"], "blocked")
        self.assertEqual(state["steps"][1]["status"], "pending")

    def test_remote_model_omits_ollama_reasoning(self):
        planner, client, _ = self.make_planner()
        client.active_model = "openai/example"
        planner.agent.model = "openai/example"
        planner.prepare("Preparar tarefas")
        self.assertNotIn("reasoning", client.responses.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
