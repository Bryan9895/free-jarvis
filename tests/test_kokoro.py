from contextlib import nullcontext
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Timer
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.kokoro_assets import install_assets, verify_assets
from jarvis.kokoro_engine import KokoroSynthesizer
from jarvis.kokoro_setup import install_runtime, runtime_python, inspect_runtime, TORCH
from jarvis.kokoro_worker import phoneme_units, deny_network, KokoroVoice
from jarvis.preferences import Preferences, PreferenceStore
from jarvis.voice import VoiceIO


class FixtureAssets:
    data = {'kokoro-v1_0.pth': b'model', 'pf_dora.pt': b'voice',
            'config.json': b'{"n_token":178,"style_dim":128}', 'MODEL_CARD.md': b'---\nlicense: apache-2.0\n---'}

    def recipe(self):
        from jarvis.kokoro_assets import MODEL_REVISION
        return {name: (MODEL_REVISION, name, hashlib.sha256(data).hexdigest(), len(data) + 10)
                for name, data in self.data.items()}

    def response(self, url, **_):
        data = self.data[url.rsplit('/', 1)[-1]]
        response = io.BytesIO(data)
        response.headers = {'Content-Length': str(len(data))}
        return response

    def install(self, root):
        with patch('jarvis.kokoro_assets.FILES', self.recipe()), \
                patch('jarvis.kokoro_assets.urlopen', side_effect=self.response):
            return install_assets(root=root, cancel=Event())


class KokoroAssetsTests(FixtureAssets, unittest.TestCase):
    def test_verified_install_records_license_and_reuses_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.install(Path(directory) / 'assets')
            with patch('jarvis.kokoro_assets.FILES', self.recipe()), patch('jarvis.kokoro_assets.urlopen') as network:
                self.assertEqual(install_assets(root=root, cancel=Event()), root)
                manifest = verify_assets(root)
                network.assert_not_called()
            self.assertEqual(manifest['license'], 'Apache-2.0')
            self.assertEqual(manifest['voice'], 'pf_dora')
            self.assertTrue(all(len(value) == 64 for value in manifest['sha256'].values()))

    def test_hash_failure_never_publishes_or_leaves_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'assets'
            recipe = self.recipe()
            recipe['kokoro-v1_0.pth'] = (*recipe['kokoro-v1_0.pth'][:2], '0' * 64, 100)
            with patch('jarvis.kokoro_assets.FILES', recipe), \
                    patch('jarvis.kokoro_assets.urlopen', side_effect=self.response):
                with self.assertRaisesRegex(ValueError, 'Hash'):
                    install_assets(root=root, cancel=Event())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cancellation_and_corruption_leave_prior_files_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.install(Path(directory) / 'assets')
            (root / 'pf_dora.pt').write_bytes(b'bad')
            with patch('jarvis.kokoro_assets.FILES', self.recipe()):
                with self.assertRaises(ValueError):
                    verify_assets(root)
            cancel = Event()
            cancel.set()
            with self.assertRaises(CancelledError):
                install_assets(root=Path(directory) / 'second', cancel=cancel)
            self.assertEqual((root / 'pf_dora.pt').read_bytes(), b'bad')
            self.assertFalse((Path(directory) / 'second').exists())


class KokoroRuntimeTests(unittest.TestCase):
    info = {'kokoro_version': '0.9.4', 'torch_version': TORCH, 'language': 'pt-br'}

    def test_runtime_inspection_rejects_wrong_cpu_language_or_python_contract(self):
        valid = {**self.info, 'espeak': 'OK', 'python_version': [3, 12, 0]}
        with patch('jarvis.kokoro_setup._run', return_value=json.dumps({'ok': True, 'runtime': valid})):
            self.assertEqual(inspect_runtime('/python')['language'], 'pt-br')
        for change in ({'torch_version': '2.8.0+cu128'}, {'language': 'en'},
                       {'kokoro_version': 'different'}, {'python_version': [3, 14, 0]}, {'espeak': 'missing'}):
            with self.subTest(change=change), patch('jarvis.kokoro_setup._run', return_value=json.dumps(
                    {'ok': True, 'runtime': {**valid, **change}})):
                with self.assertRaises(ValueError):
                    inspect_runtime('/python')

    def command(self, calls, fail=False):
        def run(command, *, stage, **kwargs):
            calls.append(command)
            if 'Verificar Python' in stage:
                return '3.12'
            if stage == 'Criar runtime Kokoro':
                python = Path(command[-1]) / 'bin/python'
                python.parent.mkdir(parents=True)
                python.write_text('#!/bin/sh\nexit 0\n')
                python.chmod(0o755)
            if stage == 'Instalar Kokoro' and fail:
                raise RuntimeError('injected failure')
            return ''
        return run

    def test_runtime_installs_cpu_only_and_reuses_verified_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            with patch('jarvis.kokoro_setup.shutil.which', return_value='/uv'), \
                    patch('jarvis.kokoro_setup._run', side_effect=self.command(calls)), \
                    patch('jarvis.kokoro_setup.inspect_runtime', return_value=self.info):
                first = install_runtime(root=directory, python='/python3.12', offline=True, progress=lambda _: None)
                count = len(calls)
                second = install_runtime(root=directory, python='/python3.12', offline=True, progress=lambda _: None)
            self.assertEqual(first['python'], runtime_python(directory))
            self.assertTrue(second['reused'])
            self.assertEqual(len(calls), count)
            torch = next(call for call in calls if 'torch==' + TORCH in call)
            self.assertIn('https://download.pytorch.org/whl/cpu', torch)
            self.assertIn('--offline', torch)

    def test_failed_runtime_keeps_previous_manifest_and_removes_only_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / 'runtime.json'
            previous.write_text('{"version":99}')
            with patch('jarvis.kokoro_setup.shutil.which', return_value='/uv'), \
                    patch('jarvis.kokoro_setup._run', side_effect=self.command([], fail=True)):
                with self.assertRaises(RuntimeError):
                    install_runtime(root=directory, python='/python3.12', progress=lambda _: None)
            self.assertEqual(previous.read_text(), '{"version":99}')
            self.assertEqual(list((root / 'versions').iterdir()), [])


FAKE_WORKER = '''import sys,json,wave
for line in sys.stdin:
 request=json.loads(line)
 with wave.open(request['filename'],'wb') as wav:
  wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(b'\\0\\0'*240)
 print('{"ok":true}',flush=True)
'''


class KokoroProcessTests(FixtureAssets, unittest.TestCase):
    def spawner(self, script, children):
        popen = subprocess.Popen
        def start(command, **kwargs):
            self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
            self.assertEqual(kwargs['env']['CUDA_VISIBLE_DEVICES'], '')
            self.assertNotIn('HF_TOKEN', kwargs['env'])
            child = popen([sys.executable, '-I', '-c', script], **kwargs)
            children.append(child)
            return child
        return start

    def test_resident_process_reused_and_wav_validated_without_player(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.install(Path(directory) / 'assets')
            children, engine = [], KokoroSynthesizer()
            try:
                with patch('jarvis.kokoro_engine.subprocess.Popen', side_effect=self.spawner(FAKE_WORKER, children)):
                    engine.synthesize(root, 'Uma frase.', Path(directory) / 'one.wav', Event(), python=sys.executable)
                    engine.synthesize(root, 'Outra frase.', Path(directory) / 'two.wav', Event(), python=sys.executable)
                self.assertEqual(len(children), 1)
                with wave.open(str(Path(directory) / 'two.wav')) as output:
                    self.assertEqual(output.getframerate(), 24000)
                    self.assertEqual(output.getnframes(), 240)
            finally:
                engine.close()
            self.assertTrue(all(child.poll() is not None for child in children))

    def test_cancel_and_timeout_reap_worker_and_next_attempt_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.install(Path(directory) / 'assets')
            children, engine = [], KokoroSynthesizer()
            cancel = Event()
            timer = Timer(.15, cancel.set)
            timer.start()
            try:
                with patch('jarvis.kokoro_engine.subprocess.Popen', side_effect=self.spawner(
                        'import sys,time; sys.stdin.readline(); time.sleep(30)', children)):
                    with self.assertRaises(CancelledError):
                        engine.synthesize(root, 'frase', Path(directory) / 'cancel.wav', cancel, python=sys.executable)
                    with self.assertRaises(TimeoutError):
                        engine.synthesize(root, 'frase', Path(directory) / 'timeout.wav', Event(), python=sys.executable, timeout=0)
                self.assertTrue(all(child.poll() is not None for child in children))
                with patch('jarvis.kokoro_engine.subprocess.Popen', side_effect=self.spawner(FAKE_WORKER, children)):
                    engine.synthesize(root, 'nova frase', Path(directory) / 'recovered.wav', Event(), python=sys.executable)
            finally:
                timer.join()
                engine.close()

    def test_worker_ack_without_audio_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.install(Path(directory) / 'assets')
            children, engine = [], KokoroSynthesizer()
            with patch('jarvis.kokoro_engine.subprocess.Popen', side_effect=self.spawner(
                    'import sys; sys.stdin.readline(); print(\'{"ok":true}\',flush=True)', children)):
                with self.assertRaises((OSError, ValueError)):
                    engine.synthesize(root, 'frase', Path(directory) / 'missing.wav', Event(), python=sys.executable)
            self.assertIsNone(engine._process)
            self.assertTrue(all(child.poll() is not None for child in children))


class KokoroSpeechTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv('JARVIS_TEST_KOKORO_WAV') == '1', 'Síntese Kokoro real exige provisionamento e teste explícito')
    def test_real_kokoro_produces_local_wav_without_playback(self):
        from jarvis.kokoro_assets import assets_directory
        from jarvis.kokoro_setup import runtime_python
        engine = KokoroSynthesizer()
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'sample.wav'
                engine.synthesize(assets_directory(), 'Esta é uma amostra em português brasileiro.',
                                  output, Event(), python=runtime_python())
                with wave.open(str(output)) as wav:
                    self.assertEqual(wav.getframerate(), 24000)
                    self.assertGreater(wav.getnframes(), 24000)
        finally:
            engine.close()

    def test_wav_contains_all_generated_segments_in_order(self):
        import numpy as np
        received = []
        class Audio:
            def detach(self): return self
            def cpu(self): return self
            def numpy(self): return np.ones(24, dtype=np.float32) * .25
        def generate(phonemes, **kwargs):
            received.append(phonemes)
            yield SimpleNamespace(audio=Audio())
        voice = KokoroVoice.__new__(KokoroVoice)
        voice.torch = SimpleNamespace(inference_mode=nullcontext)
        voice.pipeline = SimpleNamespace(g2p=lambda text: (text, None), generate_from_tokens=generate)
        voice.voice = '/local/pf_dora.pt'
        text = 'Uma resposta inteira sem cortes. ' * 100
        with tempfile.TemporaryDirectory() as directory:
            filename = str(Path(directory) / 'proof.wav')
            voice.synthesize(text, filename)
            with wave.open(filename) as output:
                self.assertEqual((output.getframerate(), output.getnchannels(), output.getsampwidth()), (24000, 1, 2))
                self.assertEqual(output.getnframes(), len(received) * 24)
        self.assertEqual(''.join(received), text)
        self.assertTrue(all(len(part) <= 500 for part in received))

    def test_kpipeline_receives_local_model_paths_cpu_and_portuguese(self):
        torch = SimpleNamespace(set_num_threads=Mock(), set_num_interop_threads=Mock())
        model = Mock()
        model.to.return_value = model
        model.eval.return_value = model
        constructor = Mock(return_value=model)
        pipeline = Mock()
        with patch.dict(sys.modules, {'torch': torch, 'kokoro': SimpleNamespace(KModel=constructor, KPipeline=pipeline)}), \
                patch('jarvis.kokoro_worker.verified_runtime'), patch('jarvis.kokoro_assets.verify_assets'):
            voice = KokoroVoice('/local/weights')
        self.assertEqual(constructor.call_args.kwargs['model'], '/local/weights/kokoro-v1_0.pth')
        self.assertEqual(constructor.call_args.kwargs['config'], '/local/weights/config.json')
        model.to.assert_called_once_with('cpu')
        self.assertEqual(pipeline.call_args.kwargs['lang_code'], 'p')
        self.assertEqual(pipeline.call_args.kwargs['device'], 'cpu')
        pipeline.return_value.load_voice.assert_called_once_with('/local/weights/pf_dora.pt')

    def test_long_phonemes_are_split_without_loss_or_truncation(self):
        text = ('Olá, mundo! ' * 200) + ('abc' * 500)
        parts = list(phoneme_units(text, lambda segment: (segment, None)))
        self.assertEqual(''.join(parts), text)
        self.assertTrue(all(len(part) <= 500 for part in parts))

    def test_worker_rejects_network_calls(self):
        for event in ('socket.connect', 'socket.getaddrinfo'):
            with self.assertRaises(RuntimeError):
                deny_network(event, ())
        deny_network('open', ())

    def test_pipeline_selection_and_warmup_preserve_player_and_cancel_contract(self):
        from jarvis.voice import VoiceIO
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            preferences = Preferences(tts_backend='kokoro', kokoro_directory=directory, kokoro_python='/python')
            spoken, paths = [], []
            def synthesize(root, text, filename, cancel, **_):
                self.assertEqual(root, Path(directory))
                paths.append(Path(filename))
                Path(filename).write_text(text)
            def play(command):
                spoken.append(Path(command[-1]).read_text())
            with patch('jarvis.preferences.PreferenceStore.load', return_value=preferences), \
                    patch('jarvis.kokoro_engine.kokoro_synthesizer.synthesize', side_effect=synthesize) as synthesis, \
                    patch('jarvis.tts_engine.synthesizer.synthesize') as piper, \
                    patch('jarvis.voice.shutil.which', return_value='/bin/true'):
                voice = VoiceIO()
                with patch.object(voice, '_run_audio', side_effect=play) as player:
                    voice.warmup()
                    player.assert_not_called()
                    self.assertEqual(voice.speak('Primeira frase. Segunda frase sem ponto'), 'spoken')
                piper.assert_not_called()
            self.assertEqual(spoken, ['Primeira frase.', 'Segunda frase sem ponto'])
            self.assertEqual(synthesis.call_count, 3)
            self.assertTrue(all(not path.exists() for path in paths))

    def test_preferences_legacy_default_and_explicit_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PreferenceStore(Path(directory) / 'prefs.json')
            store.path.write_text('{"version":1,"piper_model":"old.onnx"}')
            self.assertEqual(store.load().tts_backend, 'elevenlabs')
            saved = replace(store.load(), tts_backend='kokoro', kokoro_directory='/weights', kokoro_python='/python3.12')
            store.save(saved)
            self.assertEqual(store.load(), saved)
            with patch.dict(os.environ, {'JARVIS_TTS_BACKEND': 'piper', 'JARVIS_KOKORO_DIRECTORY': '/explicit'}):
                self.assertEqual(saved.effective().tts_backend, 'piper')
                self.assertEqual(saved.effective().kokoro_directory, '/explicit')
            with self.assertRaises(ValueError):
                replace(saved, tts_backend='cloud').validate()

    def test_token_can_share_existing_stop_event(self):
        event = Event()
        token = CancellationToken(event=event)
        event.set()
        with self.assertRaises(CancelledError):
            token.check()
