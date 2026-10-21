"""Testes locais de voz sem hardware nem downloads."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from jarvis.voice import VoiceIO, VoiceError

class VoiceTests(unittest.TestCase):
    def test_record_duration_bounds(self):
        voice = VoiceIO()
        for seconds in (0, -1, 16, 999):
            with self.subTest(seconds=seconds), self.assertRaises(VoiceError):
                voice.record(seconds)

    def test_transcribe_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(VoiceError):
                VoiceIO().transcribe(Path(td) / "missing.wav")

    def test_transcribe_mock_model(self):
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "record.wav"
            audio.write_bytes(b"test")
            voice = VoiceIO()
            voice._stt = Mock()
            voice._stt.transcribe.return_value = ([SimpleNamespace(text=" Olá "), SimpleNamespace(text=" JARVIS ")], None)
            self.assertEqual(voice.transcribe(audio), "Olá JARVIS")

    def test_disabled_tts_no_cloud(self):
        self.assertEqual(VoiceIO().speak("Olá"), "disabled")
        self.assertEqual(VoiceIO().speak(" "), "empty")

    def test_missing_piper_model(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(VoiceError):
                VoiceIO(piper_model=str(Path(td) / "missing.onnx")).speak("Olá")

    def test_audio_file_is_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "mic.wav"
            audio.write_bytes(b"mock")
            voice = VoiceIO()
            voice.record = Mock(return_value=audio)
            voice.transcribe = Mock(return_value="Tudo bem")
            self.assertEqual(voice.listen_once(3), "Tudo bem")
            self.assertFalse(audio.exists())

    def test_piper_exec_and_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            model = Path(td) / "voice.onnx"
            model.write_bytes(b"mock")
            voice = VoiceIO(piper_model=str(model))
            with patch("jarvis.voice.shutil.which", return_value="/bin/true"), patch("jarvis.voice.subprocess.run", return_value=Mock(returncode=0, stderr="")) as run:
                self.assertEqual(voice.speak("Olá"), "spoken")
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args_list[0].args[0][0], "piper")
                self.assertEqual(run.call_args_list[1].args[0][0], "aplay")

if __name__ == "__main__":
    unittest.main()
