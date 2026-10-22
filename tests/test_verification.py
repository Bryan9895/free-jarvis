"""Verificação independente do filesystem e estados do planejador."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jarvis.tools import Toolkit
from jarvis.planner import TaskPlanner
from jarvis.verification import verify_step
from jarvis.plan_view import format_plan


def record(name, result, content=None):
    entry = {"name": name, "outcome": {"result": result, "error": None}}
    if content is not None:
        entry["expected_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    return entry


class VerificationTests(unittest.TestCase):
    def test_created_folder_verified_and_absent_folder_fails(self):
        with tempfile.TemporaryDirectory() as td:
            toolkit = Toolkit(Path(td), approve=lambda _: True)
            folder = Path(td) / "demo"
            folder.mkdir()
            evidence = [record("make_directory", {"status": "created", "path": str(folder)})]
            self.assertEqual(verify_step(toolkit, evidence)[0], "verified")
            folder.rmdir()
            self.assertEqual(verify_step(toolkit, evidence)[0], "failed")
            toolkit.close()

    def test_written_contents_compared_without_exposing_text(self):
        with tempfile.TemporaryDirectory() as td:
            toolkit = Toolkit(Path(td), approve=lambda _: True)
            path = Path(td) / "main.py"
            path.write_text('print("hello world")\n', encoding="utf8")
            evidence = [record("write_file",
                               {"status": "written", "path": str(path)},
                               'print("hello world")\n')]
            self.assertEqual(verify_step(toolkit, evidence)[0], "verified")
            path.write_text("changed", encoding="utf8")
            self.assertEqual(verify_step(toolkit, evidence)[0], "failed")
            self.assertNotIn("hello world", str(evidence))
            toolkit.close()

    def test_gui_launch_never_claimed_verified(self):
        with tempfile.TemporaryDirectory() as td:
            toolkit = Toolkit(Path(td))
            state, evidence = verify_step(toolkit, [
                record("open_file", {"status": "launched_unverified"})])
            self.assertEqual(state, "unverified")
            self.assertEqual(evidence[0]["status"], "unverified")
            toolkit.close()

    def test_planner_verified_steps_and_stops_on_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"main.py"
            path.write_text("hello", encoding="utf8")
            toolkit = Toolkit(Path(td))
            agent = Mock()
            agent.model = "openai/test"
            agent.toolkit = toolkit
            agent.ask.return_value = "Gravado"
            agent.last_metrics = {"tool_problems": [], "tools_executed": 1,
                                  "tool_outcomes": [record(
                                      "write_file", {"status": "written", "path": str(path)}, "hello")]}
            planner = TaskPlanner(Mock(), agent)
            planner.plan = {"status": "ready", "goal": "Criar arquivo", "steps": [
                {"id": 1, "description": "Criar main.py", "status": "pending", "result": ""}]}
            response = planner.execute(lambda _: True, report=lambda _: None)
            self.assertEqual(response["status"], "completed_verified")
            self.assertEqual(response["steps"][0]["status"], "verified")
            self.assertIn("Verificada", format_plan(response))
            path.write_text("bad", encoding="utf8")
            planner.plan["status"] = "ready"
            planner.plan["steps"][0]["status"] = "pending"
            response = planner.execute(lambda _: True, report=lambda _: None)
            self.assertEqual(response["status"], "stopped")
            self.assertEqual(response["steps"][0]["status"], "blocked")
            toolkit.close()


if __name__ == "__main__":
    unittest.main()
