"""Controlled PCM decisions; no microphone, player, Whisper or model download."""
from array import array
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch
import wave

from jarvis.endpoint_evaluation import evaluate, main


class LevelActivity:
    def active(self, pcm):
        return bool((abs(pcm.astype('int32')) > 1000).any())


class EndpointReplayTests(TestCase):
    def corpus(self, root, segments, *, rate=16000, channels=1):
        pcm = array('h')
        for seconds, active in segments:
            pcm.extend(array('h', [3000 if active else 0]) * round(seconds * rate * channels))
        audio = root / 'private-audio.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setnchannels(channels)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(pcm.tobytes())
        manifest = root / 'private-reference.json'
        manifest.write_text(json.dumps([{'audio': audio.name, 'reference': 'Não apague dois arquivos. segredoX',
                                        'consent': True, 'source_kind': 'synthetic'}]))
        return manifest

    def run_replay(self, manifest, **kwargs):
        return evaluate(manifest, activity_factory=LevelActivity, **kwargs)

    def test_long_speech_and_internal_pause_survive_with_no_raw_data_in_report(self):
        for seconds in (3, 10, 25, 60):
            with self.subTest(seconds=seconds), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = self.corpus(root, [(1, True), (.8, False), (seconds - 1, True), (1.3, False)])
                result = self.run_replay(manifest)
                row = result['measurements'][0]
                self.assertEqual(result['state'], 'passed')
                self.assertGreater(row['endpoint_audio_s'], seconds + .8)
                self.assertEqual(row['source_activity_blocks_after_endpoint'], 0)
                self.assertEqual(row['retained_samples'], round(row['endpoint_audio_s'] * 16000))
                self.assertFalse(row['retained_is_executable'])
                self.assertEqual(result['human_coverage']['state'], 'pending')
                self.assertNotIn('segredoX', json.dumps(result))
                self.assertNotIn(str(root), json.dumps(result))

    def test_speech_after_first_endpoint_is_reported_as_possible_cut(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.corpus(Path(directory), [(1, True), (1.3, False), (2, True), (1.3, False)])
            row = self.run_replay(manifest)['measurements'][0]
            self.assertEqual(row['state'], 'failed')
            self.assertEqual(row['reason'], 'activity_after_endpoint')
            self.assertGreater(row['last_source_activity_s'], row['endpoint_audio_s'])
            self.assertGreater(row['source_activity_blocks_after_endpoint'], 0)

    def test_eof_never_finalizes_and_padding_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.corpus(Path(directory), [(3, True)])
            row = self.run_replay(manifest)['measurements'][0]
            self.assertEqual(row['reason'], 'endpoint_not_reached')
            self.assertIsNone(row['endpoint_audio_s'])
            padded = self.run_replay(manifest, tail_silence_ms=1300)
            row = padded['measurements'][0]
            self.assertEqual(row['state'], 'passed')
            self.assertTrue(row['endpoint_in_padding'])
            self.assertEqual(padded['settings']['tail_silence_ms'], 1300)
            self.assertEqual(row['source_normalized_samples'], 48000)

    def test_silence_cannot_become_valid_turn_and_limit_stays_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.corpus(root, [(3, False)])
            row = self.run_replay(manifest, tail_silence_ms=1300)['measurements'][0]
            self.assertEqual(row['reason'], 'no_activity')
            self.assertEqual(row['retained_samples'], 0)
            manifest = self.corpus(root, [(3, True), (1.3, False)])
            row = self.run_replay(manifest, max_seconds=2)['measurements'][0]
            self.assertEqual(row['reason'], 'segment_limit')
            self.assertTrue(row['segment_pending'])
            self.assertFalse(row['retained_is_executable'])
            self.assertIsNone(row['endpoint_audio_s'])

    def test_real_resampler_accepts_stereo_and_flushes_without_sample_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.corpus(Path(directory), [(1, True), (1.3, False)], rate=44100, channels=2)
            row = self.run_replay(manifest)['measurements'][0]
            self.assertEqual(row['state'], 'passed')
            self.assertEqual(row['source_normalized_samples'], 36800)

    def test_invalid_corpus_is_rejected_before_detector_load(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.corpus(Path(directory), [(1, True)])
            rows = json.loads(manifest.read_text())
            rows[0]['consent'] = False
            manifest.write_text(json.dumps(rows))
            factory = Mock()
            with self.assertRaises(ValueError): evaluate(manifest, activity_factory=factory)
            factory.assert_not_called()

    def test_changed_audio_or_manifest_invalidates_replay(self):
        for target in ('private-audio.wav', 'private-reference.json'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = self.corpus(root, [(1, True), (1.3, False)])
                class ChangeActivity(LevelActivity):
                    def active(self, pcm):
                        (root / target).write_bytes(b'changed secret')
                        return super().active(pcm)
                with self.assertRaises((ValueError, wave.Error)):
                    evaluate(manifest, activity_factory=ChangeActivity)

    def test_bad_options_do_not_load_vad(self):
        for kwargs in ({'silence_ms': 0}, {'max_seconds': float('nan')}, {'max_seconds': 121},
                       {'max_seconds': True}, {'threshold': float('nan')}, {'tail_silence_ms': 5001}):
            factory = Mock()
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                evaluate('/not/opened.json', activity_factory=factory, **kwargs)
            factory.assert_not_called()

    def test_cli_preserves_existing_or_concurrent_destination_and_cleans_stage(self):
        for concurrent in (False, True):
            with self.subTest(concurrent=concurrent), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = self.corpus(root, [(1, True), (1.3, False)])
                target = root / 'result.json'
                if not concurrent: target.write_text('private file')
                def publish(*args):
                    target.write_text('private file')
                    raise FileExistsError()
                with patch('jarvis.endpoint_evaluation.evaluate', return_value={'state': 'passed'}) as run, \
                        patch('jarvis.endpoint_evaluation.os.link', side_effect=publish), self.assertRaises(SystemExit):
                    main([str(manifest), '--output', str(target)])
                if not concurrent: run.assert_not_called()
                self.assertEqual(target.read_text(), 'private file')
                self.assertFalse(list(root.glob('.endpoint-evaluation-*')))

    def test_cli_writes_complete_sanitized_report_and_failed_gate_returns_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'result.json'
            with patch('jarvis.endpoint_evaluation.evaluate', return_value={'state': 'failed', 'reason': 'no_activity'}), \
                    patch('builtins.print'), self.assertRaises(SystemExit) as exit:
                main([str(root / 'corpus.json'), '--output', str(target)])
            self.assertEqual(exit.exception.code, 1)
            self.assertEqual(json.loads(target.read_text())['state'], 'failed')
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertFalse(list(root.glob('.endpoint-evaluation-*')))
