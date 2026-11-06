import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.config import Config
from jarvis.local_setup import check, pull_model, install_stt


class LocalPreparationTests(TestCase):
    def config(self, root):
        return Config('http://127.0.0.1:1', '', '', root, root / 'db',
                      local_model='fixture:1', openjarvis_python='/fixture/python')

    def test_check_passes_token_to_preflight_and_generation_and_rejects_tool_calls(self):
        token = CancellationToken()
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(Path(directory))
            for tool in (False, True):
                response = {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'teste'}]}]}
                if tool: response['output'].append({'type': 'function_call', 'name': 'forbidden'})
                with self.subTest(tool=tool), patch('jarvis.local_setup.OpenJarvisProvider') as factory:
                    provider = factory.return_value
                    provider._exchange.side_effect = [['fixture:1'], True]
                    provider.active_model = 'fixture:1'
                    provider.stream_responses.return_value = response
                    if tool:
                        with self.assertRaises(ValueError): check(config, token=token)
                    else:
                        result = check(config, token=token)
                        self.assertEqual(result['inference'], 'verified')
                        self.assertEqual(result['physical_audio'], 'Não testado')
                    self.assertTrue(all(call.kwargs['cancel_token'] is token for call in provider._exchange.call_args_list))
                    self.assertIs(provider.stream_responses.call_args.kwargs['cancel_token'], token)
                    provider.close.assert_called_once()

    def test_pull_records_identity_only_after_download_and_cancel_keeps_previous_pins(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JARVIS_OLLAMA_DIR': directory}):
            root = Path(directory)
            config = self.config(root)
            pins = root / 'model-pins.json'
            pins.write_text('{"previous": {"model": "previous"}}')
            with patch('jarvis.ollama_setup.binary', return_value='/fixture/ollama'), \
                    patch('jarvis.local_setup._run'), patch('jarvis.local_setup.OpenJarvisProvider') as factory:
                provider = factory.return_value
                provider._exchange.return_value = {'model': 'fixture:1', 'digest': 'fixture-digest'}
                pull_model(config, 'fixture:1', progress=lambda _: None)
                self.assertIn('fixture:1', json.loads(pins.read_text()))
                before = pins.read_bytes()
                token = CancellationToken()
                def identity(*args, **kwargs):
                    token.cancel()
                    return {'model': 'other:1', 'digest': 'other-digest'}
                provider._exchange.side_effect = identity
                with self.assertRaises(CancelledError):
                    pull_model(config, 'other:1', token=token, progress=lambda _: None)
                self.assertEqual(pins.read_bytes(), before)

    def test_stt_validates_before_spawn_and_forwards_cancel_token(self):
        token = CancellationToken()
        with patch('jarvis.local_setup._run') as run:
            with self.assertRaises(ValueError): install_stt('not-a-model', token=token)
            run.assert_not_called()
            result = install_stt('small', token=token, progress=lambda _: None)
        self.assertIs(run.call_args.kwargs['token'], token)
        self.assertEqual(result['inference'], 'Não testado')
