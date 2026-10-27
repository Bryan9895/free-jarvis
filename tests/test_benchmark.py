import unittest
from unittest.mock import patch
from jarvis.benchmark import ControlledProvider
from jarvis.fcc import FCCError
from jarvis.benchmark import run
from jarvis.stt_evaluation import word_errors, critical_match


class BenchmarkTests(unittest.TestCase):
    def test_quota_stops_benchmark_without_repeating_generation(self):
        class QuotaProvider(ControlledProvider):
            calls = 0
            def stream_responses(self, *args, **kwargs):
                self.calls += 1
                raise FCCError('usage_limit_reached', 429)
        provider = QuotaProvider()
        with patch('jarvis.benchmark.ControlledProvider', return_value=provider):
            result = run(30)
        self.assertEqual(provider.calls, 1)
        self.assertFalse(result['completed'])
        self.assertEqual(result['samples'], 1)
        self.assertEqual(result['turns'][0]['error_category'], 'quota_exhausted')
    def test_complete_controlled_journeys_include_actions_failures_and_cancel(self):
        result = run(7)
        self.assertEqual(result['samples'], 7)
        self.assertEqual(result['scenarios']['network_failure']['failures'], 1)
        self.assertEqual(result['scenarios']['voice_failure']['failures'], 1)
        self.assertEqual(result['scenarios']['cancel']['cancelled'], 1)
        compound = next(row for row in result['turns'] if row['scenario'] == 'compound_action')
        self.assertEqual(compound['tools_executed'], 2)
        self.assertNotIn('revisar relatório', str(result))
        self.assertNotIn('Resposta controlada', str(result))
        self.assertEqual(result['physical_audio'], 'pending')

    def test_stt_metrics_detect_negation_and_number_changes(self):
        self.assertEqual(word_errors('não apague os 3 arquivos', 'apague os 4 arquivos'), (2, 5))
        self.assertFalse(critical_match('não apague os 3 arquivos', 'apague os 3 arquivos'))
        self.assertFalse(critical_match('abra 2 abas', 'abra 3 abas'))
        self.assertTrue(critical_match('Não apague 3 arquivos.', 'não apague 3 arquivos'))
