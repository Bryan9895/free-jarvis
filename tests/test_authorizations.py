import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from jarvis.authorizations import AuthorizationStore, Grants
from jarvis.approval import ApprovalPolicy
from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.command_execution import limited_process
from jarvis.tools import Toolkit


class AuthorizationTests(unittest.TestCase):
    def setup_policy(self, root, categories=(), roots=()):
        store = AuthorizationStore(root / 'authorizations.json')
        store.save(Grants(frozenset(categories), tuple(str(p) for p in roots)))
        policy = ApprovalPolicy(auto=True, manual_callback=lambda _: False, authorizations=store, report=lambda _: None)
        return policy, store

    def test_persistence_atomic_failure_and_corruption_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy, store = self.setup_policy(root, ('terminal',))
            self.assertTrue(AuthorizationStore(store.path).permits('terminal'))
            with patch('jarvis.authorizations.os.replace', side_effect=OSError('disk')):
                with self.assertRaises(OSError): store.save(Grants(frozenset(('administration',))))
            self.assertTrue(store.permits('terminal'))
            self.assertTrue(AuthorizationStore(store.path).permits('terminal'))
            store.path.write_text('{bad')
            invalid = AuthorizationStore(store.path)
            self.assertFalse(invalid.permits('terminal'))
            self.assertTrue(invalid.error)
            self.assertEqual(list(root.glob('.authorizations-*')), [])

    def test_auto_never_grants_terminal_or_administration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy, _ = self.setup_policy(root)
            kit = Toolkit(root, approve=policy)
            with patch('jarvis.command_execution.limited_process') as run:
                self.assertEqual(kit.execute('execute_process', {'argv': ['true']})['result']['status'], 'rejected')
                self.assertEqual(kit.execute('manage_packages', {'action': 'install', 'packages': ['vlc']})['result']['status'], 'rejected')
                run.assert_not_called()

    def test_terminal_requires_explicit_account_data_permission(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy, store = self.setup_policy(root, ('terminal',))
            kit = Toolkit(root, approve=policy)
            with patch('jarvis.command_execution.limited_process') as run:
                self.assertEqual(kit.execute('execute_process', {'argv': ['true']})['result']['status'], 'rejected')
                run.assert_not_called()
            store.save(Grants(frozenset(('terminal', 'secrets'))))
            result = kit.execute('execute_process', {'argv': ['/usr/bin/true']})
            self.assertEqual(result['result']['exit_code'], 0)
            self.assertFalse(result['result']['effect_verified'])

    def test_granted_roots_and_symlink_escape_then_persistent_revocation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace, extra, outside = (root / name for name in ('work', 'extra', 'outside'))
            for path in (workspace, extra, outside): path.mkdir()
            (extra / 'ok.txt').write_text('ok')
            (outside / 'hidden.txt').write_text('hidden')
            (extra / 'escape').symlink_to(outside, target_is_directory=True)
            policy, store = self.setup_policy(root, ('files',), (extra,))
            kit = Toolkit(workspace, approve=policy)
            self.assertEqual(kit.read_file(str(extra / 'ok.txt')), 'ok')
            self.assertIn('error', kit.execute('read_file', {'path': str(extra / 'escape/hidden.txt')}))
            policy.revoke()
            self.assertEqual(AuthorizationStore(store.path).snapshot().categories, frozenset())
            self.assertEqual(kit.allowed_roots, [workspace])
            self.assertEqual(kit.execute('read_file', {'path': '.'})['result']['status'], 'rejected')

    def test_sensitive_file_is_separate_even_inside_authorized_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy, store = self.setup_policy(root)
            (root / '.env').write_text('fixture')
            kit = Toolkit(root, approve=policy)
            self.assertIn('error', kit.execute('read_file', {'path': '.env'}))
            store.save(Grants(frozenset(('secrets',))))
            self.assertEqual(kit.read_file('.env'), 'fixture')

    def test_administration_uses_fixed_program_and_observed_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy, _ = self.setup_policy(root, ('administration',))
            kit = Toolkit(root, approve=policy)
            with patch('jarvis.command_execution.shutil.which', return_value='/usr/bin/tool'), patch(
                    'jarvis.command_execution.limited_process', side_effect=[
                        {'status': 'executed', 'exit_code': 0},
                        {'stdout': 'install ok installed', 'exit_code': 0}]) as run:
                result = kit.execute('manage_packages', {'action': 'install', 'packages': ['vlc']})
            self.assertEqual(result['result']['status'], 'verified')
            self.assertEqual(run.call_args_list[0].args[0], ['/usr/bin/pkexec', '/usr/bin/apt-get', '-y', 'install', '--', 'vlc'])
            with patch('jarvis.command_execution.limited_process') as run:
                self.assertIn('error', kit.execute('manage_packages', {'action': 'install', 'packages': ['--evil']}))
                run.assert_not_called()

    def test_output_is_bounded_and_environment_does_not_inherit_tokens(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'FCC_TOKEN': 'fixture-secret'}):
            result = limited_process([sys.executable, '-c',
                'import os; print(os.getenv("FCC_TOKEN", "absent")); print("a"*100000)'], td)
        self.assertLessEqual(len(result['stdout'].encode()), 32768)
        self.assertTrue(result['output_truncated'])
        self.assertIn('absent', result['stdout'])
        self.assertNotIn('fixture-secret', result['stdout'])

    def test_cancel_reaps_process_and_descendant(self):
        with tempfile.TemporaryDirectory() as td:
            pidfile = Path(td) / 'child.pid'
            token, errors = CancellationToken(), []
            script = ('import subprocess,time,pathlib,sys; '
                      'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
                      'pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)')
            def run():
                try: limited_process([sys.executable, '-c', script, str(pidfile)], td, token=token)
                except Exception as exc: errors.append(exc)
            worker = threading.Thread(target=run)
            worker.start()
            deadline = time.monotonic() + 2
            while not pidfile.exists() and time.monotonic() < deadline: time.sleep(.01)
            self.assertTrue(pidfile.exists())
            token.cancel()
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertIsInstance(errors[0], CancelledError)
            pid = int(pidfile.read_text())
            stat = Path(f'/proc/{pid}/stat')
            self.assertTrue(not stat.exists() or stat.read_text().split()[2] == 'Z')

    def test_uncertain_process_stops_agent_before_more_effects(self):
        from jarvis.agent import Agent
        from jarvis.memory import Memory
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy, _ = self.setup_policy(root, ('terminal', 'secrets'))
            kit = Toolkit(root, approve=policy)
            memory = Memory(root / 'm.db')
            self.addCleanup(memory.close)
            client = Mock()
            client.responses.return_value = {'output': [
                {'type': 'function_call', 'name': 'execute_process', 'call_id': 'p',
                 'arguments': '{"argv":["fixture"]}'},
                {'type': 'function_call', 'name': 'write_file', 'call_id': 'w',
                 'arguments': '{"path":"should-not-exist","content":"x"}'}]}
            agent = Agent(client, kit, memory, 'fake')
            with patch('jarvis.command_execution.limited_process', side_effect=TimeoutError('timeout')):
                answer = agent.ask('Execute o processo e crie um arquivo', mode='tools')
            self.assertIn('Efeitos parciais', answer)
            self.assertFalse((root / 'should-not-exist').exists())
            client.responses.assert_called_once()
