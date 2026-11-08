import json
import unittest
from jarvis.engineering_team import EngineeringTeam, TeamError, review_report


class MockAgent:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.inputs = []
    def run(self, prompt):
        self.inputs.append(prompt)
        return next(self.outputs)


class TeamContractTests(unittest.TestCase):
    def test_complete_critical_revision_cycle(self):
        supervisor = MockAgent(["Plano seguro"])
        developer = MockAgent(["aplicado", "corrigido"])
        reviewer = MockAgent([
            json.dumps({"verdict": "changes_requested", "findings": ["Bug na GUI"]}),
            json.dumps({"verdict": "approve", "findings": []}),
        ])
        team = EngineeringTeam(supervisor, developer, reviewer, lambda: (True, "ok"))
        result = team.run("Ajustar esfera do Adam")
        self.assertEqual(result["log"], ["supervisor_ok", "developer_ran",
            "codex_changes_requested", "developer_ran", "codex_approve", "tests_passed"])
        self.assertTrue(result["approved"])
        self.assertIn("Bug na GUI", developer.inputs[-1])

    def test_critic_cannot_say_approve_with_findings_or_prose(self):
        for answer in ("Aprovado", "{}", "[]", '{"verdict":"approve","findings":["erro"]}',
                       '{"verdict":"changes_requested","findings":[]}'):
            with self.assertRaises(TeamError):
                review_report(answer)

    def test_tests_failure_prevents_publication(self):
        team = EngineeringTeam(MockAgent(["plano"]),
            MockAgent(["primeira", "segunda"]),
            MockAgent(['{"verdict":"approve","findings":[]}',
                       '{"verdict":"approve","findings":[]}']),
            lambda: (False, "regressão"), max_rounds=2)
        result = team.run("Teste")
        self.assertFalse(result["approved"])
        self.assertEqual(result["log"].count("tests_failed"), 2)

    def test_missing_rounds_rejected(self):
        with self.assertRaises(ValueError):
            EngineeringTeam(None, None, None, None, max_rounds=0)
