import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from jarvis.plan_store import PlanStore
from jarvis.planner import TaskPlanner
from jarvis.project_checkpoint import inspect_project
from jarvis.tools import Toolkit
from jarvis.agent import Agent
from jarvis.memory import Memory


class ProjectCheckpointTests(TestCase):
    def fixture(self, root):
        def git(*args):
            return subprocess.check_output(['/usr/bin/git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
        git('init', '-q')
        (root / 'app.py').write_text('print("fixture")\n')
        git('add', 'app.py')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.org', 'commit', '-qm', 'Fixture')
        git('remote', 'add', 'origin', 'https://user:secret@example.org/demo/repo.git?token=secret')
        venv = root / '.venv'
        (venv / 'bin').mkdir(parents=True)
        (venv / 'bin/python').touch()
        (venv / 'pyvenv.cfg').write_text('version = fixture\n')
        metadata = venv / 'lib/python3.13/site-packages/fixture-1.0.dist-info/METADATA'
        metadata.parent.mkdir(parents=True)
        metadata.write_text('Name: fixture\nVersion: 1.0\n')
        return git('rev-parse', 'HEAD'), metadata

    def test_observed_revision_dependency_identity_and_sanitized_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha, metadata = self.fixture(root)
            toolkit = Toolkit(root)
            checkpoint = toolkit.project_checkpoint(expected_revision=sha, distributions=['fixture'])
            self.assertTrue(checkpoint['effect_verified'])
            self.assertEqual(checkpoint['source_url'], 'https://example.org/demo/repo.git')
            self.assertNotIn('secret', json.dumps(checkpoint))
            self.assertEqual(toolkit.project_checkpoint(distributions=['missing'])['status'], 'failed')

    def test_durable_plan_revalidation_blocks_changed_environment_before_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, metadata = self.fixture(root)
            toolkit = Toolkit(root)
            checkpoint = inspect_project(root)
            store = PlanStore(root / 'plans.sqlite')
            plan = {'status': 'ready', 'goal': 'fixture', 'steps': [
                {'id': 1, 'description': 'Inspecionar projeto', 'status': 'verified', 'artifacts': [
                    {'tool': 'project_checkpoint', 'result': checkpoint, 'arguments': {}}]},
                {'id': 2, 'description': 'Continuar projeto', 'status': 'pending', 'depends_on': [1]}]}
            store.save(plan)
            agent = SimpleNamespace(toolkit=toolkit, ask=Mock())
            planner = TaskPlanner(Mock(), agent, store)
            metadata.write_text('Name: fixture\nVersion: 2.0\n')
            result = planner.execute(lambda _: True, report=lambda _: None)
            self.assertEqual(result['status'], 'stopped')
            self.assertEqual(result['steps'][0]['status'], 'blocked')
            agent.ask.assert_not_called()
            self.assertEqual(store.get(plan['id'])['steps'][1]['status'], 'pending')
            store.close()

    def test_structured_checkpoint_flows_through_agent_into_sqlite_plan(self):
        class Provider:
            active_model = 'fixture'
            calls = 0
            def responses(self, payload):
                self.calls += 1
                if self.calls == 1:
                    return {'output': [{'type': 'function_call', 'name': 'project_checkpoint',
                        'call_id': 'checkpoint', 'arguments': '{"path":"."}'}]}
                return {'output': [{'type': 'message', 'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': 'Projeto inspecionado.'}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revision, _ = self.fixture(root)
            toolkit = Toolkit(root)
            memory = Memory(root / 'state.sqlite')
            store = PlanStore(root / 'state.sqlite')
            provider = Provider()
            agent = Agent(provider, toolkit, memory, 'fixture')
            planner = TaskPlanner(provider, agent, store)
            planner.plan = {'status': 'ready', 'goal': 'Inspecionar projeto', 'steps': [
                {'id': 1, 'description': 'Inspecione projeto e dependências instaladas', 'status': 'pending'}]}
            try:
                result = planner.execute(lambda _: True, report=lambda _: None)
                self.assertEqual(result['status'], 'completed_verified', json.dumps(result))
                artifact = store.latest()['steps'][0]['artifacts'][0]
                self.assertEqual(artifact['result']['revision'], revision)
                self.assertNotIn('secret', json.dumps(artifact))
            finally:
                toolkit.close()
                memory.close()
                store.close()
