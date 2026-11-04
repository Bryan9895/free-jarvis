"""Offline profile boundaries and subprocess lifecycle; no microphone/model downloads."""
import asyncio
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.config import Config
from jarvis.fcc import FCCError
from jarvis.local_provider import OpenJarvisProvider, local_host, local_model, OPENJARVIS_REVISION
from jarvis.openjarvis_worker import check_model, generate, verify_revision
from jarvis.preferences import Preferences, PreferenceStore
from jarvis.provider_factory import create_provider, profile_registry
from jarvis.tools import Toolkit, DEFAULT_REGISTRY


class LocalProfileTests(unittest.TestCase):
    def test_legacy_config_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'JARVIS_PREFERENCES': directory + '/preferences.json'}, clear=True):
            store = PreferenceStore()
            self.assertEqual(Config.from_env().profile, 'fcc')
            store.save(replace(Preferences(), inference_profile='local', local_model='qwen3:1.7b',
                               conversation_model='ollama/legacy'))
            config = Config.from_env()
            self.assertEqual((config.profile, config.local_model, config.model),
                             ('local', 'qwen3:1.7b', 'ollama/legacy'))
            with patch.dict(os.environ, {'JARVIS_PROFILE': 'fcc', 'FCC_MODEL': 'explicit'}):
                self.assertEqual(Config.from_env().profile, 'fcc')
                self.assertEqual(Config.from_env().model, 'explicit')
            self.assertEqual(store.load().inference_profile, 'local')

    def test_remote_endpoints_and_cloud_models_rejected(self):
        for host in ('https://127.0.0.1:11434', 'http://example.com:11434',
                'http://127.0.0.1.evil:80', 'http://localhost:11434',
                'http://user:secret@127.0.0.1:11434', 'http://127.0.0.1:11434/path',
                'http://127.0.0.1:11434?target=cloud'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                local_host(host)
        for model in ('ollama/qwen3:1.7b', 'gemini/test', 'qwen:cloud', '', 'bad name'):
            with self.subTest(model=model), self.assertRaises(FCCError):
                local_model(model)
        self.assertEqual(local_host('http://[::1]:11434/'), 'http://[::1]:11434')

    def test_local_factory_never_constructs_fcc_or_loads_plugins(self):
        config = SimpleNamespace(profile='local', local_model='gemma4:e2b',
            ollama_host='http://127.0.0.1:11434', openjarvis_python=sys.executable)
        with patch('jarvis.provider_factory.FCCClient') as fcc, patch('jarvis.plugins.load_plugins') as plugins:
            provider = create_provider(config, initialize=False)
            registry = profile_registry(config)
        fcc.assert_not_called()
        plugins.assert_not_called()
        self.assertIsInstance(provider, OpenJarvisProvider)
        self.assertIsNotNone(registry.get('write_file'))
        self.assertIsNone(registry.get('browser_navigate'))
        self.assertIsNone(registry.get('execute_process'))

    def test_toolkit_blocks_network_even_with_capabilities_reenabled(self):
        with tempfile.TemporaryDirectory() as directory:
            toolkit = Toolkit(Path(directory), approve=lambda _: True, offline=True)
            try:
                with patch.object(toolkit, 'browser_navigate') as navigate:
                    self.assertIn('offline', toolkit.execute('browser_navigate', {'url': 'https://example.com'})['error'])
                    navigate.assert_not_called()
                result = toolkit.execute('write_file', {'path': 'proof.txt', 'content': 'local'})
                self.assertNotIn('error', result)
                self.assertEqual((Path(directory) / 'proof.txt').read_text(), 'local')
                registry = DEFAULT_REGISTRY.copy()
                registry.register({'type': 'function', 'name': 'external', 'parameters': {'type': 'object'}},
                                  'filesystem.read', lambda _: None)
                toolkit.registry = registry
                self.assertIn('offline', toolkit.execute('external', {})['error'])
            finally:
                toolkit.close()

    def test_cloud_metadata_and_missing_tool_support_fail_closed(self):
        engine = Mock()
        for metadata in ({'remote_host': 'https://ollama.com'}, {'remote_model': 'qwen'},
                         {'modelfile': 'FROM qwen:cloud'}, {'capabilities': ['completion']}):
            engine._client.post.return_value.json.return_value = metadata
            with self.assertRaises(ValueError):
                check_model(engine, 'qwen3:1.7b', tools=True)
        engine._client.post.return_value.json.return_value = {'capabilities': ['tools']}
        check_model(engine, 'qwen3:1.7b', tools=True)

    def test_dependency_revision_is_verified(self):
        distribution = Mock()
        with patch('importlib.metadata.distribution', return_value=distribution):
            distribution.read_text.return_value = '{}'
            with self.assertRaises(ValueError):
                verify_revision(OPENJARVIS_REVISION)
            distribution.read_text.return_value = json.dumps({'url': 'https://github.com/open-jarvis/OpenJarvis.git',
                'vcs_info': {'commit_id': OPENJARVIS_REVISION}})
            verify_revision(OPENJARVIS_REVISION)

    def test_local_selection_has_no_automatic_fallback(self):
        provider = OpenJarvisProvider()
        with patch.object(provider, '_exchange', side_effect=[['gemma4:e2b', 'qwen:cloud'], True]):
            self.assertEqual(provider.initialize(), 'gemma4:e2b')
        self.assertEqual(provider.known_models, ('gemma4:e2b',))
        with self.assertRaises(FCCError):
            provider.use_all_models()

    def test_shared_service_executes_local_structured_action_through_toolkit(self):
        from jarvis.conversation import ConversationController
        from jarvis.service import JarvisService
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Config('http://127.0.0.1:1', '', '', root, root / 'memory.db', profile='local')
            provider = OpenJarvisProvider()
            requests = []
            def exchange(request, **kwargs):
                requests.append(request)
                payload = request['payload']
                if any(item.get('type') == 'function_call_output' for item in payload['input']):
                    return {'output': [{'type': 'message', 'content': [
                        {'type': 'output_text', 'text': 'Arquivo criado e verificado.'}]}]}
                return {'output': [{'type': 'function_call', 'call_id': 'structured-id',
                    'name': 'write_file', 'arguments': '{"path":"proof.txt","content":"local"}'}]}
            with patch('jarvis.provider_factory.create_provider', return_value=provider), \
                    patch.object(provider, '_exchange', side_effect=exchange), \
                    patch('jarvis.service.FCCClient') as fcc:
                service = JarvisService.from_config(config, report=lambda _: None)
                try:
                    answer = ConversationController(service).run('Crie o arquivo proof.txt com o conteúdo local.')
                    self.assertEqual((root / 'proof.txt').read_text(), 'local')
                    self.assertTrue(any(item['tool'] == 'write_file' for item in service.toolkit.operation_log))
                    self.assertTrue(answer)
                    self.assertTrue(service.toolkit.offline)
                    fcc.assert_not_called()
                finally:
                    service.close()

    def test_worker_consolidates_complete_structured_calls_before_execution(self):
        chunks = [SimpleNamespace(content='Resposta sem ponto', tool_calls=None, usage=None, finish_reason=None),
                  SimpleNamespace(content='', tool_calls=[{'id': 'original-id', 'function': {
                      'name': 'write_file', 'arguments': '{"path":"proof.txt","content":"ok"}'}}],
                      usage={'total_tokens': 12}, finish_reason='tool_calls')]
        class Engine:
            async def stream_full(self, *args, **kwargs):
                self.options = kwargs
                for chunk in chunks:
                    yield chunk
        engine = Engine()
        emitted = []
        with patch('jarvis.openjarvis_worker.check_model'), patch('jarvis.openjarvis_worker.messages_from_payload', return_value=[]), \
                patch('jarvis.openjarvis_worker.emit', side_effect=emitted.append):
            asyncio.run(generate(engine, {'model': 'gemma4:e2b', 'payload': {}}))
        self.assertEqual(emitted[0], {'delta': 'Resposta sem ponto'})
        result = emitted[-1]['result']
        self.assertEqual(result['output'][-1]['call_id'], 'original-id')
        self.assertEqual(json.loads(result['output'][-1]['arguments'])['path'], 'proof.txt')
        self.assertFalse(engine.options['think'])
        self.assertEqual(engine.options['num_ctx'], 4096)
        chunks[-1].finish_reason = 'length'
        with patch('jarvis.openjarvis_worker.check_model'), patch('jarvis.openjarvis_worker.messages_from_payload', return_value=[]), \
                patch('jarvis.openjarvis_worker.emit') as emit:
            with self.assertRaisesRegex(ValueError, 'incompleta'):
                asyncio.run(generate(engine, {'model': 'gemma4:e2b', 'payload': {}}))
            self.assertFalse(any('result' in c.args[0] for c in emit.call_args_list))


class LocalProcessTests(unittest.TestCase):
    def exchange(self, script, **kwargs):
        provider = OpenJarvisProvider()
        real_popen = subprocess.Popen
        children = []
        def spawn(_command, **options):
            child = real_popen([sys.executable, '-I', '-c', script], **options)
            children.append(child)
            return child
        try:
            with patch('jarvis.local_provider.subprocess.Popen', side_effect=spawn):
                return provider._exchange({'operation': 'generate'}, **kwargs)
        finally:
            self.assertTrue(all(child.poll() is not None for child in children))

    def test_deltas_arrive_before_terminal_without_waiting_for_eof(self):
        seen = []
        start = monotonic()
        result = self.exchange('import sys,time; sys.stdin.readline(); '
            'print(\'{"delta":"Olá."}\',flush=True); time.sleep(.1); '
            'print(\'{"result":{"output":[]}}\',flush=True); time.sleep(10)', on_event=seen.append)
        self.assertEqual(result, {'output': []})
        self.assertEqual(seen[0]['delta'], 'Olá.')
        self.assertLess(monotonic() - start, 3)

    def test_cancel_and_deadline_reap_blocked_child(self):
        token = CancellationToken()
        timer = threading.Timer(.1, token.cancel)
        timer.start()
        try:
            with self.assertRaises(CancelledError):
                self.exchange('import sys,time; sys.stdin.readline(); time.sleep(30)', cancel_token=token)
        finally:
            timer.join()
        with self.assertRaises(TimeoutError):
            self.exchange('import sys,time; sys.stdin.readline(); time.sleep(30)', deadline=monotonic() + .1)

    def test_partial_failure_does_not_retry(self):
        seen = []
        with self.assertRaises(FCCError):
            self.exchange('import sys; sys.stdin.readline(); print(\'{"delta":"parcial"}\',flush=True)', on_event=seen.append)
        self.assertEqual(len(seen), 1)
