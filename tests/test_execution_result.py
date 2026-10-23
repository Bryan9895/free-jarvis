"""Contrato de estados gerais; nenhum estado desconhecido confirma sucesso."""
import unittest

from jarvis.execution_result import ResultState, classify_tool_outcome


class ExecutionResultTests(unittest.TestCase):
    def test_specialized_statuses_keep_raw_evidence(self):
        cases = {
            "rejected": ResultState.REJECTED,
            "unavailable": ResultState.UNAVAILABLE,
            "not_observed": ResultState.NOT_FOUND,
            "ambiguous": ResultState.AMBIGUOUS,
            "close_unverified": ResultState.UNVERIFIED,
            "profile_partial": ResultState.PARTIAL,
            "layout_verified": ResultState.VERIFIED,
            "changed": ResultState.FAILED,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                result = classify_tool_outcome({"result": {"status": raw}})
                self.assertEqual(result.state, expected)
                self.assertEqual(result.raw_status, raw)

    def test_write_requires_independent_verification_and_is_not_safe_to_retry(self):
        result = classify_tool_outcome({"result": {"status": "written"}},
                                       capability="filesystem.write")
        self.assertEqual(result.state, ResultState.UNVERIFIED)
        self.assertTrue(result.effect_sent)
        self.assertFalse(result.retry_safe)

    def test_unknown_status_fails_closed_and_reads_can_be_observed(self):
        self.assertEqual(classify_tool_outcome(
            {"result": {"status": "mystery_success"}}).state, ResultState.UNVERIFIED)
        self.assertEqual(classify_tool_outcome(
            {"result": ["a"]}, capability="filesystem.read").state,
            ResultState.VERIFIED)
        self.assertEqual(classify_tool_outcome(
            {"result": {"exit_code": 1}}, capability="command.read").state,
            ResultState.FAILED)

    def test_transport_error_is_failure(self):
        self.assertEqual(classify_tool_outcome({"error": "boom"}).state,
                         ResultState.FAILED)


if __name__ == "__main__":
    unittest.main()
