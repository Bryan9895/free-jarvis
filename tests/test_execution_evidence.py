"""Regressões dos erros observados em testes reais: resposta sem efeito não conclui etapa."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.planner import TaskPlanner
from jarvis.tools import Toolkit


class ExecutionEvidenceTests(unittest.TestCase):
    def make_plan(self, description, metrics, answer):
        client = Mock()
        agent = Mock()
        agent.model = "openai/test"
        agent.ask.return_value = answer
        agent.last_metrics = metrics
        planner = TaskPlanner(client, agent)
        planner.plan = {"goal": description, "status": "ready", "steps": [
            {"id": 1, "description": description, "status": "pending", "result": ""},
            {"id": 2, "description": "Verificar resultado", "status": "pending", "result": ""},
        ]}
        return planner, agent

    def test_narrative_confirmation_does_not_complete_creation(self):
        planner, agent = self.make_plan(
            "Criar arquivo main.py na pasta testejarvis",
            {"tools_executed": 0, "tool_outcomes": [], "tool_problems": []},
            "Posso criar esse arquivo. Confirma a criação?",
        )
        result = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["steps"][0]["status"], "blocked")
        self.assertEqual(result["steps"][1]["status"], "pending")
        self.assertEqual(agent.ask.call_count, 1)

    def test_successful_write_file_is_counted(self):
        outcome = {"result": {"status": "written", "path": "/tmp/main.py"}}
        planner, agent = self.make_plan(
            "Criar main.py",
            {"tools_executed": 1, "tool_outcomes": [
                {"name": "write_file", "arguments": {"path": "main.py"}, "outcome": outcome}
            ], "tool_problems": []},
            "Arquivo gravado.",
        )
        result = planner.execute(lambda _: True, report=lambda _: None)
        self.assertEqual(result["status"], "completed_unverified")
        self.assertEqual(agent.ask.call_count, 2)

    def test_open_file_and_verify_content(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            file = folder / "main.py"
            file.write_text('print("hello world")\n', encoding="utf-8")
            tool = Toolkit(folder, approve=lambda _: True)
            self.assertEqual(
                tool.execute("verify_file", {"path": "main.py", "content": 'print("hello world")\n'})["result"]["status"],
                "verified",
            )
            self.assertEqual(
                tool.execute("verify_file", {"path": "main.py", "content": ""})["result"]["status"],
                "content_mismatch",
            )
            process = Mock(pid=17)
            with patch("jarvis.process_manager.shutil.which", return_value="/usr/bin/code"), patch(
                "jarvis.process_manager.subprocess.Popen", return_value=process
            ) as launch, patch("jarvis.window_tracking.snapshot", return_value=None), patch(
                "jarvis.window_tracking.observe_launch",
                side_effect=lambda launched, *_args: {**launched, "window_observation": {"status": "unavailable"}}
            ):
                result = tool.execute("open_file", {"path": "main.py"})
            self.assertEqual(result["result"]["status"], "launched_unverified")
            self.assertEqual(launch.call_args.args[0][-1], str(file))
            tool.close()

if __name__ == "__main__":
    unittest.main()
