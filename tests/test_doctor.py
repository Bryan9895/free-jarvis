from pathlib import Path
import json
import subprocess
from unittest import TestCase
from unittest.mock import Mock, patch

from jarvis.config import Config
from jarvis.doctor import active, collect, human, safe_url


class DoctorTests(TestCase):
    def config(self):
        return Config('https://user:secret@example.org/api?token=secret', '', 'secret', Path('/tmp'), Path('/tmp/db'))

    def test_basic_is_read_only_redacts_credentials_and_keeps_legacy_json(self):
        with patch('subprocess.Popen', side_effect=AssertionError('Must not spawn')), \
                patch('socket.socket', side_effect=AssertionError('Must not connect')):
            result = collect(self.config())
        self.assertEqual(result['fcc_url'], 'https://example.org')
        self.assertIn('voice_package_installed', result)
        self.assertEqual(next(c['state'] for c in result['checks'] if c['id'] == 'inference'), 'Não testado')
        self.assertNotIn('secret', json.dumps(result))
        self.assertIn('Físico', human(result))
        self.assertEqual(safe_url('http://[::1]:11434/private'), 'http://[::1]:11434')

    def test_active_timeout_kills_group_and_does_not_pass_secrets_in_argv(self):
        process = Mock(pid=998, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired('probe', 1)
        with patch('subprocess.Popen', return_value=process) as spawn, patch('os.killpg') as kill:
            event = active(self.config(), 'inference', timeout=1)
        self.assertEqual(event['reason'], 'timeout')
        self.assertNotIn('secret', str(spawn.call_args))
        self.assertIn('secret', process.communicate.call_args.args[0].decode())
        self.assertEqual(kill.call_count, 2)
        process.wait.assert_called_once()

    def test_invalid_scope_does_not_start_process(self):
        with patch('subprocess.Popen') as spawn:
            for args in ({'kind': 'stt'}, {'kind': 'tts', 'timeout': 301}, {'kind': 'microphone', 'output': '/tmp/forbidden.wav'}):
                with self.assertRaises(ValueError): active(self.config(), **args)
        spawn.assert_not_called()

    def test_active_report_does_not_claim_audible_sound(self):
        report = collect(self.config())
        report['active_tests'] = [{'id': 'tts', 'state': 'OK'}]
        rendered = human(report)
        self.assertIn('Teste ativo · tts: OK', rendered)
        self.assertIn('audible: Não testado', rendered)
