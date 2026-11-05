from unittest import TestCase
from unittest.mock import patch
from pathlib import Path
import tempfile
import json
import hashlib
from jarvis.model_comparison import main
from jarvis.model_comparison import select
from jarvis.benchmark import run


class ModelComparisonTests(TestCase):
    def test_requires_quality_critical_cases_and_complete_ram_before_selection(self):
        row = {'state': 'passed', 'wrong_effect': False, 'duplicate_effect': False}
        def model(latency, pss):
            return {'completed': True, 'runs': [{'phase': 'warm', 'scenario': 'case',
                'turns': [row.copy()], 'memory': {'peak_tree_pss_kib': pss, 'pss_complete': True, 'missing_root_pids': []},
                'scenarios': {'case': {'first_visual_s': {'p95': latency}}}}]}
        results = {'slow': model(2, 100), 'large': model(1, 300), 'small': model(1, 200)}
        review = {'quality_rate': .95, 'critical_rate': 1, 'reviewed_turns': 1,
                  'oom': 0, 'wrong_effects': 0, 'duplicate_effects': 0}
        reviews = {name: review.copy() for name in results}
        self.assertIsNone(select(results, {}))
        self.assertEqual(select(results, reviews), 'small')
        reviews['small']['critical_rate'] = .99
        self.assertEqual(select(results, reviews), 'large')
        results['large']['runs'][0]['memory']['missing_root_pids'] = [123]
        self.assertEqual(select(results, reviews), 'slow')
        results['slow']['runs'][0]['turns'][0]['duplicate_effect'] = True
        self.assertIsNone(select(results, reviews))

    def test_controlled_negation_has_no_effect_and_numbers_preserved(self):
        result = run(9)
        negative = next(row for row in result['turns'] if row['scenario'] == 'negation')
        numbers = next(row for row in result['turns'] if row['scenario'] == 'number_action')
        self.assertEqual(negative['tools_executed'], 0)
        self.assertTrue(negative['effect_verified'])
        self.assertTrue(numbers['effect_verified'])
        self.assertFalse(numbers['duplicate_effect'])

    def test_quality_review_reads_existing_report_without_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'measurements.json'
            report.write_text(json.dumps({'kind': 'local_cold_warm_comparison', 'models': {}}))
            review = root / 'review.json'
            review.write_text(json.dumps({'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(), 'models': {}}))
            output = root / 'selection.json'
            argv = ['compare', '--results', str(report), '--quality-review', str(review), '--output', str(output)]
            with patch('sys.argv', argv), patch('jarvis.model_comparison.compare', side_effect=AssertionError('Must not infer')), patch('builtins.print'):
                main()
            self.assertIsNone(json.loads(output.read_text())['selected_model'])
