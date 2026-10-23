import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from jarvis.voice import VoiceError
from jarvis.voice_diagnostics import VoiceDiagnostics, signal_metrics, compare_transcript


class VoiceDiagnosticTests(unittest.TestCase):
    def wav(self, path, samples):
        with wave.open(str(path), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(array('h', samples).tobytes())

    def test_signal_distinguishes_silence_and_clipping(self):
        silence = signal_metrics(array('h', [0]*160).tobytes())
        self.assertEqual(silence['dbfs'], -96)
        self.assertEqual(silence['peak'], 0)
        loud = signal_metrics(array('h', [-32768,32767]*80).tobytes())
        self.assertEqual(loud['clipping_percent'],100)
        self.assertGreater(loud['rms'], .99)

    def test_comparison_ignores_case_accents_and_punctuation(self):
        exact = compare_transcript('Olá, JARVIS!', 'ola jarvis')
        self.assertEqual(exact['similarity_percent'], 100)
        self.assertEqual(compare_transcript('abra o firefox','abra firefox')['word_edits'], 1)
        self.assertEqual(compare_transcript('teste','')['similarity_percent'], 0)
        self.assertIsNone(compare_transcript('', 'palavra'))

    def test_probe_resolves_input_and_warns_about_virtual_source(self):
        backend = SimpleNamespace(query_devices=Mock(return_value={'name':'Loopback'}),
                                  check_input_settings=Mock())
        with patch.dict(sys.modules, {'sounddevice':backend}), patch.dict('os.environ', {'PULSE_SOURCE':''}):
            result = VoiceDiagnostics().probe('Loopback')
        backend.query_devices.assert_called_once_with('Loopback', kind='input')
        self.assertTrue(result['warnings'])
        self.assertEqual(result['status'], 'available')

    def test_probe_fails_for_disconnected_device(self):
        backend = SimpleNamespace(query_devices=Mock(side_effect=ValueError('disconnected')))
        with patch.dict(sys.modules, {'sounddevice':backend}):
            with self.assertRaisesRegex(VoiceError, 'Entrada indisponível'):
                VoiceDiagnostics().probe('Bluetooth')

    def test_capture_keeps_silence_for_replay_and_cleans_old_sample(self):
        with tempfile.TemporaryDirectory() as td:
            old, new = Path(td)/'old.wav', Path(td)/'new.wav'
            old.write_bytes(b'old')
            self.wav(new, [0]*16000)
            test = VoiceDiagnostics()
            test.recording = old
            test.probe = Mock(return_value={'device':'Bluetooth','sample_rate':16000,'pulse_source':'default'})
            with patch('jarvis.voice_diagnostics.VoiceIO') as voice:
                voice.return_value.silence_rms = 150
                voice.return_value.record.return_value = new
                result = test.capture('Bluetooth')
                self.assertTrue(voice.return_value.record.call_args.kwargs['allow_silence'])
            self.assertEqual(result['signal'], 'baixo_ou_silencio')
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            test.close()
            self.assertFalse(new.exists())

    def test_transcription_compares_same_file_and_reuses_model(self):
        with tempfile.TemporaryDirectory() as td:
            recording = Path(td)/'test.wav'
            recording.write_bytes(b'fixture')
            test = VoiceDiagnostics()
            test.recording = recording
            with patch('jarvis.voice_diagnostics.VoiceIO') as voice:
                voice.return_value.transcribe.return_value = 'ola jarvis'
                first = test.transcribe('base','Olá Jarvis')
                test.transcribe('base','Olá Jarvis')
                self.assertEqual(voice.call_count,1)
                test.transcribe('small','Olá Jarvis')
                self.assertEqual(voice.call_count,2)
                voice.return_value.transcribe.assert_called_with(recording)
            self.assertEqual(first['comparison']['similarity_percent'],100)
            self.assertTrue(recording.exists())
            test.close()

    def test_replay_checks_exit_status_and_needs_recording(self):
        test = VoiceDiagnostics()
        with self.assertRaises(VoiceError):
            test.replay()
        with tempfile.TemporaryDirectory() as td:
            test.recording = Path(td)/'test.wav'
            test.recording.write_bytes(b'fixture')
            with patch('jarvis.voice_diagnostics.shutil.which', return_value='/bin/paplay'), patch(
                    'jarvis.voice_diagnostics.subprocess.run', return_value=Mock(returncode=1)):
                with self.assertRaisesRegex(VoiceError, 'reproduzir'):
                    test.replay()
            test.close()
