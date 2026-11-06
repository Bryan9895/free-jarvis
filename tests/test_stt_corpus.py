from array import array
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import wave

from jarvis.stt_corpus import load_corpus, evaluate, describe
from jarvis.stt_evaluation import critical_match, critical_values
from tools.evaluate_stt import main


class CriticalQuantityTests(TestCase):
    def test_spelled_numbers_decimals_negatives_and_large_quantities(self):
        for reference, actual in (
            ('abra duas abas', 'abra 2 abas'),
            ('não apague vinte e três arquivos', 'não apague 23 arquivos'),
            ('use dois mil e vinte e seis', 'use 2026'),
            ('limite de menos dois vírgula zero cinco', 'limite de -2,05'),
            ('não mude duzentos e trinta e sete', 'nao mude 237'),
            ('abra a terceira pasta', 'abra a 3ª pasta'),
        ):
            with self.subTest(reference=reference): self.assertTrue(critical_match(reference, actual))
        for reference, actual in (
            ('abra dois arquivos', 'abra três arquivos'),
            ('não apague dois arquivos', 'apague dois arquivos'),
            ('use -3', 'use 3'), ('código 003', 'código 3'),
            ('em segundo plano', 'em terceiro plano'),
            ('nenhuma pasta', 'pasta'), ('um milhão', 'um bilhão'),
            ('arquivos 1,2,3', 'arquivos 4,5,6'),
            ('não abra duas abas e abra três pastas', 'abra duas abas e não abra três pastas'),
            ('não abra firefox e abra chrome', 'abra firefox e não abra chrome'),
            ('use 123456789012345678901234567891', 'use 123456789012345678901234567892'),
        ):
            with self.subTest(reference=reference): self.assertFalse(critical_match(reference, actual))
        self.assertEqual(critical_values('duas e três')['numbers'], ('2', '3'))


class CorpusTests(TestCase):
    def wav(self, root, duration=3, pause=False):
        path = root / 'private-audio.wav'
        pcm = array('h', [1000]) * round(16000 * duration)
        if pause: pcm[16000:28800] = array('h', [0]) * 12800
        with wave.open(str(path), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(pcm.tobytes())
        return path

    def manifest(self, root, **extra):
        path = root / 'private-reference.json'
        path.write_text(json.dumps([{'audio': 'private-audio.wav', 'reference': 'Não apague dois arquivos. segredoX',
                                    'consent': True, **extra}]))
        return path

    def test_preflight_validates_pause_duration_and_does_not_load_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wav(root, pause=True)
            manifest = self.manifest(root, source_kind='human', duration_class=3, pause_ms=800)
            samples = load_corpus(manifest)
            self.assertTrue(samples[0]['internal_quiet_800ms'])
            self.assertEqual(describe(samples)['human_coverage']['missing_duration_classes'], [10, 25, 60])
            with patch('sys.argv', ['evaluate', str(manifest), '--preflight']), \
                    patch('jarvis.voice.VoiceIO', side_effect=AssertionError('No model')), patch('builtins.print') as printed:
                main()
            self.assertNotIn('segredoX', printed.call_args.args[0])
            self.assertNotIn('private-audio', printed.call_args.args[0])

    def test_invalid_consent_duration_and_pause_reject_whole_corpus_before_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wav(root)
            for extra in ({'consent': False}, {'duration_class': 60}, {'pause_ms': 800}, {'sha256': '0' * 64}):
                factory = Mock()
                manifest = self.manifest(root, **extra)
                with self.subTest(extra=extra), self.assertRaises(ValueError): evaluate(manifest, voice_factory=factory)
                factory.assert_not_called()

    def test_numeric_loss_and_transcription_failure_cannot_pass_critical_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wav(root)
            manifest = self.manifest(root, source_kind='synthetic')
            voice = SimpleNamespace(model_name='small', transcribe=Mock(side_effect=[
                'Não apague três arquivos. segredoX', RuntimeError('private error segredoX')]))
            result = evaluate(manifest, repetitions=2, voice_factory=lambda **_: voice)
            self.assertEqual(result['profiles'][5]['critical_match_rate'], 0)
            self.assertEqual(result['profiles'][5]['failures'], 1)
            self.assertEqual(result['human_coverage']['state'], 'pending')
            self.assertNotIn('segredoX', json.dumps(result))
            self.assertNotIn(str(root), json.dumps(result))

    def test_changed_sample_invalidates_report_and_output_cannot_overwrite_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = self.wav(root)
            manifest = self.manifest(root)
            def transcribe(*args, **kwargs):
                audio.write_bytes(b'changed')
                return 'Não apague dois arquivos.'
            voice = SimpleNamespace(model_name='small', transcribe=transcribe)
            with self.assertRaises(ValueError): evaluate(manifest, voice_factory=lambda **_: voice)
            self.wav(root)
            before = audio.read_bytes()
            with patch('sys.argv', ['evaluate', str(manifest), '--preflight', '--output', str(audio)]), self.assertRaises(SystemExit):
                main()
            self.assertEqual(audio.read_bytes(), before)

    def test_no_critical_reference_is_reported_as_unmeasured_not_perfect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wav(root)
            manifest = self.manifest(root, reference='Abra arquivos agora.')
            voice = SimpleNamespace(model_name='small', transcribe=lambda *a, **kw: 'Abra arquivos agora.')
            result = evaluate(manifest, voice_factory=lambda **_: voice)
            self.assertIsNone(result['profiles'][5]['critical_match_rate'])

    def test_actual_git_marker_is_rejected_before_loading_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.git/objects').mkdir(parents=True)
            (root / '.git/HEAD').write_text('ref: refs/heads/main\n')
            self.wav(root)
            manifest = self.manifest(root)
            factory = Mock()
            with self.assertRaises(ValueError): evaluate(manifest, voice_factory=factory)
            factory.assert_not_called()
