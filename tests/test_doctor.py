from pathlib import Path
import json
import subprocess
from unittest import TestCase
from unittest.mock import Mock, patch
from dataclasses import asdict
import os
import tempfile
import wave
import sys
import signal

from jarvis.config import Config
from jarvis.doctor import active, collect, human, safe_url, merge_active, _probe
from jarvis.preferences import Preferences
from jarvis.stt_corpus import fingerprint


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

    def test_kokoro_manifest_without_runtime_is_not_configured_as_ok(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch('jarvis.preferences.PreferenceStore.load', return_value=Preferences(tts_backend='kokoro')), \
                patch('jarvis.kokoro_setup.status', return_value={'assets': 'Presentes', 'runtime': 'Falta'}):
            report = collect(self.config())
        self.assertEqual(next(row['state'] for row in report['checks'] if row['id'] == 'tts'), 'Falta')

    def test_tts_functional_result_does_not_replace_configuration_state(self):
        report = {'checks': [
            {'id': 'tts', 'category': 'configuration', 'state': 'Falta'},
            {'id': 'tts_synthesis', 'category': 'functional', 'state': 'Não testado'}]}
        merge_active(report, {'id': 'tts', 'state': 'OK'})
        self.assertEqual([row['state'] for row in report['checks']], ['Falta', 'OK'])

    def test_legacy_nonempty_transcription_is_explicitly_not_an_accuracy_check(self):
        payload = {'config': asdict(self.config()), 'kind': 'stt', 'sample': '/not/read.wav'}
        with patch('jarvis.voice.VoiceIO') as factory:
            factory.return_value.transcribe.return_value = 'private speech secret'
            event = _probe(payload)
        self.assertEqual(event['state'], 'OK')
        self.assertEqual(event['reference_check'], 'Não testado')
        self.assertNotIn('secret', json.dumps(event))
        report = collect(self.config())
        merge_active(report, event)
        self.assertIn('acurácia não testada', human(report))

    def test_corpus_reference_failure_and_exact_success_stay_separate_from_physical_acceptance(self):
        for matched in (False, True):
            with self.subTest(matched=matched), tempfile.TemporaryDirectory() as directory:
                corpus = Path(directory) / 'corpus.json'
                corpus.write_text('[]')
                sha = fingerprint(corpus)
                result = {'corpus_sha256': sha, 'model': 'small', 'samples': [{}], 'human_coverage': {'state': 'pending'},
                    'reference': 'private secret', 'profiles': {5: {'failures': 0, 'wer': 0 if matched else .5,
                    'critical_status': 'passed' if matched else 'failed', 'critical_match_rate': 1 if matched else 0}}}
                payload = {'config': asdict(self.config()), 'kind': 'stt', 'corpus': str(corpus), 'corpus_sha256': sha}
                with patch('jarvis.stt_corpus.evaluate', return_value=result): event = _probe(payload)
                self.assertEqual(event['state'], 'OK' if matched else 'Falhou')
                self.assertEqual(event['physical_audio'], 'Não testado')
                self.assertEqual(event['human_coverage'], 'pending')
                self.assertNotIn('secret', json.dumps(event))
                self.assertNotIn(directory, json.dumps(event))

    def test_corpus_requires_explicit_stt_scope_and_cannot_mix_with_sample(self):
        with patch('subprocess.Popen') as spawn:
            for kind, sample in (('tts', None), ('stt', '/some.wav')):
                with self.assertRaises(ValueError): active(self.config(), kind, corpus='/some.json', sample=sample)
        spawn.assert_not_called()

    def test_changed_reference_is_rejected_before_transcription(self):
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / 'corpus.json'
            corpus.write_text('[]')
            payload = {'config': asdict(self.config()), 'kind': 'stt', 'corpus': str(corpus), 'corpus_sha256': '0' * 64}
            with patch('jarvis.stt_corpus.evaluate') as evaluate, self.assertRaises(ValueError): _probe(payload)
            evaluate.assert_not_called()

    def test_timeout_removes_probe_audio_and_unpublished_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'out.wav'
            owned = []
            def communicate(data, **kwargs):
                payload = json.loads(data)
                root, stage = Path(payload['temporary_directory']), Path(payload['output_stage'])
                (root / 'private-microphone.wav').write_bytes(b'controlled audio')
                stage.write_bytes(b'partial output')
                owned.extend([root, stage])
                raise subprocess.TimeoutExpired('doctor', 1)
            process = Mock(pid=998)
            process.communicate.side_effect = communicate
            with patch('subprocess.Popen', return_value=process), patch('os.killpg'):
                event = active(self.config(), 'tts', output=target, timeout=1)
            self.assertEqual(event['reason'], 'timeout')
            self.assertFalse(target.exists())
            self.assertTrue(all(not path.exists() for path in owned))

    def test_output_publication_is_complete_and_does_not_overwrite_a_concurrent_file(self):
        for concurrent in (False, True):
            with self.subTest(concurrent=concurrent), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'out.wav'
                def communicate(data, **kwargs):
                    payload = json.loads(data)
                    with wave.open(payload['output_stage'], 'wb') as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(22050)
                        wav.writeframes(b'\0\0' * 200)
                    if concurrent: target.write_bytes(b'concurrent file')
                    return json.dumps({'id': 'tts', 'state': 'OK'}).encode(), None
                process = Mock(pid=998, returncode=0)
                process.communicate.side_effect = communicate
                with patch('subprocess.Popen', return_value=process), patch('os.killpg'):
                    event = active(self.config(), 'tts', output=target)
                if concurrent:
                    self.assertEqual(event['state'], 'Falhou')
                    self.assertEqual(target.read_bytes(), b'concurrent file')
                else:
                    self.assertEqual(event['state'], 'OK')
                    with wave.open(str(target)) as wav: self.assertEqual(wav.getnframes(), 200)
                self.assertFalse(list(Path(directory).glob('.jarvis-doctor-*')))

    def test_timeout_reaps_probe_and_its_inherited_synthesis_worker(self):
        if sys.platform != 'linux': self.skipTest('Linux process groups')
        from jarvis.project_services import identity
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'worker.json'
            worker = ('import os,json,time;from pathlib import Path;'
                      f'Path({str(marker)!r}).write_text(json.dumps([os.getpid(),os.getpgrp()]));time.sleep(30)')
            code = '''import json,sys,subprocess
from pathlib import Path
from threading import Event
from jarvis.kokoro_engine import KokoroSynthesizer
from jarvis.kokoro_assets import FILES
payload=json.loads(sys.stdin.read())
root=Path(payload['temporary_directory'])
for name in (*FILES,'SOURCE.json'): (root/name).write_bytes(b'fixture')
original=subprocess.Popen
def start(command,**kwargs):
 return original([sys.executable,'-I','-c',WORKER],**kwargs)
subprocess.Popen=start
engine=KokoroSynthesizer(own_session=False)
engine.synthesize(root,'directed test',root/'out.wav',Event(),python=sys.executable)
'''.replace('WORKER', repr(worker))
            popen = subprocess.Popen
            children = []
            def spawn(command, **kwargs):
                child = popen([sys.executable, '-c', code], **kwargs)
                children.append(child)
                return child
            try:
                with patch('subprocess.Popen', side_effect=spawn):
                    event = active(self.config(), 'tts', timeout=1)
                self.assertEqual(event['reason'], 'timeout')
                self.assertTrue(marker.exists())
                pid, group = json.loads(marker.read_text())
                self.assertEqual(group, children[0].pid)
                self.assertIsNone(identity(pid))
                self.assertIsNotNone(children[0].poll())
            finally:
                for child in children:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
