from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest import TestCase
from unittest.mock import Mock, patch

from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.config import Config
from jarvis.model_evaluation import evaluate, load, review, approved_model, responses_for_review
from jarvis.model_comparison import compare, select


def fixture_report():
    def model(name, latency):
        return {'completed': True, 'unloaded': True, 'identity': {'model': name, 'digest': name}, 'runs': [
            {'phase': 'warm', 'scenario': 'short_question', 'completed': True,
             'turns': [{'state': 'passed', 'wrong_effect': False, 'duplicate_effect': False}] * 2,
             'memory': {'pss_complete': True, 'peak_tree_pss_kib': 100, 'missing_root_pids': []},
             'scenarios': {'short_question': {'first_visual_s': {'p95': latency}}}}]}
    return {'kind': 'local_cold_warm_comparison', 'completed': True, 'state': 'completed',
            'selected_model': None, 'models': {name: model(name, latency) for name, latency in [('first:1', 1), ('second:1', 2)]}}


def fixture_compare(models, *, checkpoint, review_sink, **kwargs):
    report = fixture_report()
    for model in models:
        for index in range(2):
            review_sink({'model': model, 'request': 'directed request privateX', 'answer': 'directed answer privateX',
                         'phase': 'warm', 'scenario': 'short_question', 'index': index, 'state': 'passed'})
    checkpoint(report)
    return report


class EvaluationFilesTests(TestCase):
    def config(self, directory):
        return Config('http://127.0.0.1:1', '', '', directory, directory / 'db')

    def create(self, parent):
        with patch('jarvis.model_evaluation.verify_monitor'), patch('jarvis.model_evaluation.compare', side_effect=fixture_compare):
            return evaluate(self.config(parent), ['first:1', 'second:1'], directory=parent, monitor_pid=os.getpid())[0]

    def ratings(self):
        return {model: {'reviewed': 2, 'adequate': 2, 'critical_errors': 0, 'oom': 0} for model in ('first:1', 'second:1')}

    def test_private_files_review_and_pick_do_not_change_preferences(self):
        with tempfile.TemporaryDirectory() as directory, patch('jarvis.preferences.PreferenceStore.save') as save:
            root = self.create(Path(directory))
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / 'responses.jsonl').stat().st_mode & 0o777, 0o600)
            metrics = (root / 'metrics.json').read_text()
            self.assertNotIn('privateX', metrics)
            self.assertNotIn(str(root), metrics)
            self.assertEqual(len(responses_for_review(root)), 4)
            selected = review(root, self.ratings())
            self.assertEqual(selected['selected_model'], 'first:1')
            self.assertEqual(approved_model(root)[0], 'first:1')
            save.assert_not_called()

    def test_changed_replies_metrics_or_quality_invalidates_previous_selection(self):
        for filename in ('responses.jsonl', 'metrics.json', 'quality.json'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = self.create(Path(directory))
                review(root, self.ratings())
                with (root / filename).open('a') as stream: stream.write('\n')
                with self.assertRaises(ValueError): approved_model(root)

    def test_all_answers_and_critical_quality_and_oom_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.create(Path(directory))
            ratings = self.ratings()
            ratings['first:1']['reviewed'] = 1
            with self.assertRaises(ValueError): review(root, ratings)
            ratings = self.ratings()
            ratings['first:1']['critical_errors'] = 1
            ratings['second:1']['oom'] = 1
            self.assertIsNone(review(root, ratings)['selected_model'])
            with self.assertRaises(ValueError): approved_model(root)
            ratings = self.ratings()
            ratings['first:1']['adequate'] = True
            with self.assertRaises(ValueError): review(root, ratings)

    def test_cancelled_partial_run_and_failure_keep_artifacts_without_selection(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled), tempfile.TemporaryDirectory() as directory:
                def stop(models, *, review_sink, checkpoint, **kwargs):
                    report = fixture_report()
                    report.update(state='running', completed=False)
                    checkpoint(report)
                    raise CancelledError('privateX') if cancelled else RuntimeError('privateX')
                with patch('jarvis.model_evaluation.verify_monitor'), patch('jarvis.model_evaluation.compare', side_effect=stop):
                    root, report = evaluate(self.config(Path(directory)), ['first:1', 'second:1'],
                        directory=directory, monitor_pid=os.getpid())
                self.assertEqual(report['state'], 'cancelled' if cancelled else 'failed')
                self.assertIsNone(report['selected_model'])
                self.assertNotIn('privateX', (root / 'metrics.json').read_text())
                load(root)
                with self.assertRaises(ValueError): review(root, self.ratings())

    def test_repository_root_and_invalid_monitor_are_rejected_before_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.git/objects').mkdir(parents=True)
            (root / '.git/HEAD').write_text('ref: refs/heads/main\n')
            with patch('jarvis.model_evaluation.verify_monitor'), patch('jarvis.model_evaluation.compare') as infer:
                with self.assertRaises(ValueError): evaluate(self.config(root), ['first:1', 'second:1'], directory=root, monitor_pid=1)
            infer.assert_not_called()
            self.assertEqual(list(root.glob('jarvis-models-*')), [])


class ComparisonExecutionTests(TestCase):
    def test_models_use_explicit_config_and_cancel_unloads_with_separate_token(self):
        token = CancellationToken()
        reports, received, unloaded = [], [], []
        provider = Mock()
        provider._exchange.side_effect = lambda payload, **kwargs: (
            unloaded.append(kwargs['cancel_token']) or True if payload['operation'] == 'unload' else {'model': payload['model']})
        def measure(count, **kwargs):
            received.append(kwargs['config'].local_model)
            self.assertEqual(os.environ['JARVIS_LOCAL_MODEL'], 'unchanged:1')
            token.cancel()
            return {'completed': False, 'turns': [], 'memory': {}, 'scenarios': {}}
        config = Config('http://localhost', '', '', Path('/tmp'), Path('/tmp/db'))
        with patch.dict(os.environ, {'JARVIS_LOCAL_MODEL': 'unchanged:1'}), \
                patch('jarvis.model_comparison.verify_monitor', return_value={}), \
                patch('jarvis.model_comparison.OpenJarvisProvider', return_value=provider), \
                patch('jarvis.model_comparison.run', side_effect=measure), self.assertRaises(CancelledError):
            compare(['first:1', 'second:1'], config=config, monitor_pids=[1], cancel_token=token,
                    checkpoint=lambda value: reports.append(deepcopy(value)))
        self.assertEqual(received, ['first:1'])
        self.assertFalse(unloaded[-1].cancelled)
        self.assertEqual(reports[-1]['state'], 'cancelled')
        self.assertIsNone(reports[-1]['selected_model'])
        provider.close.assert_called_once()

    def test_nonfinite_timings_missing_ram_and_unload_failure_cannot_win(self):
        ratings = {name: {'quality_rate': 1, 'critical_rate': 1, 'reviewed_turns': 2,
                         'oom': 0, 'wrong_effects': 0, 'duplicate_effects': 0} for name in ('first:1', 'second:1')}
        report = fixture_report()
        report['models']['first:1']['runs'][0]['scenarios']['short_question']['first_visual_s']['p95'] = float('nan')
        report['models']['second:1']['unloaded'] = False
        self.assertIsNone(select(report['models'], ratings))

    def test_cold_warm_sequence_finishes_both_models_without_environment_changes(self):
        events, reviewed = [], []
        def provider(model, **kwargs):
            value = Mock()
            value.initialize.side_effect = lambda **kw: events.append(('initialize', model))
            def exchange(payload, **kw):
                events.append((payload['operation'], model))
                return {'model': model} if payload['operation'] == 'identity' else True
            value._exchange.side_effect = exchange
            return value
        def measure(count, *, config, review_sink, **kwargs):
            self.assertEqual(os.environ['JARVIS_LOCAL_MODEL'], 'unchanged:1')
            for index in range(count):
                review_sink({'request': 'directed', 'answer': 'directed', 'scenario': 'short_question', 'index': index})
            return {'completed': True, 'turns': [{'state': 'passed', 'trace': {'events': []}} for _ in range(count)],
                    'scenarios': {'short_question': {'first_visual_s': {'p95': 1}}},
                    'memory': {'pss_complete': True, 'peak_tree_pss_kib': 100, 'missing_root_pids': []}}
        config = Config('http://localhost', '', '', Path('/tmp'), Path('/tmp/db'))
        with patch.dict(os.environ, {'JARVIS_LOCAL_MODEL': 'unchanged:1'}), \
                patch('jarvis.model_comparison.verify_monitor', return_value={}), \
                patch('jarvis.model_comparison.OpenJarvisProvider', side_effect=provider), \
                patch('jarvis.model_comparison.SCENARIOS', [('short_question', 'directed')]), \
                patch('jarvis.model_comparison.run', side_effect=measure):
            report = compare(['first:1', 'second:1'], config=config, monitor_pids=[1], review_sink=reviewed.append)
        self.assertTrue(report['completed'])
        self.assertIsNone(report['selected_model'])
        self.assertEqual(len(reviewed), 66)
        for data in report['models'].values():
            self.assertEqual([entry['phase'] for entry in data['runs']], ['cold', 'cold', 'cold', 'warm'])
            self.assertTrue(data['unloaded'])
        second_start = events.index(('initialize', 'second:1'))
        self.assertEqual(events[second_start - 1], ('unload', 'first:1'))

    def test_parent_cancellation_interrupts_benchmark_and_child_deadline_is_independent(self):
        from jarvis.benchmark import run
        from jarvis.service import _turn_token
        from time import monotonic
        entered = threading.Event()
        token = CancellationToken(deadline=monotonic() + 3600)
        child = _turn_token(token.child())
        self.assertLess(child.deadline, token.deadline)
        class Provider:
            active_model = 'fixture:1'
            def initialize(self, **kwargs): pass
            def stream_responses(self, payload, *, cancel_token, **kwargs):
                entered.set()
                while not cancel_token.cancelled: threading.Event().wait(.01)
                cancel_token.check()
            def close(self): pass
        results, errors = [], []
        def execute():
            try: results.append(run(30, real_local=True, scenario='short_question', cancel_token=token))
            except Exception as exc: errors.append(exc)
        with patch('jarvis.provider_factory.create_provider', return_value=Provider()):
            thread = threading.Thread(target=execute)
            thread.start()
            try:
                self.assertTrue(entered.wait(2))
                token.cancel()
                thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertFalse(results[0]['completed'])
                self.assertEqual(results[0]['turns'][0]['state'], 'cancelled')
            finally:
                token.cancel()
                thread.join(2)
