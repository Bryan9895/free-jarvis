"""Testes locais de voz sem hardware nem downloads."""
import tempfile
import sys
from array import array
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from jarvis.voice import VoiceIO, VoiceError, WakeWordConversation

class VoiceTests(unittest.TestCase):
    def test_record_duration_bounds(self):
        voice = VoiceIO()
        for seconds in (0, -1, 16, 999):
            with self.subTest(seconds=seconds), self.assertRaises(VoiceError):
                voice.record(seconds)

    def test_silence_is_rejected_and_device_is_selected(self):
        recorded = []
        fake_sd = SimpleNamespace(
            rec=lambda *args, **kwargs: recorded.append(kwargs) or
                SimpleNamespace(tobytes=lambda: array("h", [0] * 160).tobytes()),
            wait=lambda: None,
            query_devices=lambda: [{"name": "Microfone USB", "max_input_channels": 1},
                                   {"name": "Saída", "max_input_channels": 0}],
        )
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            self.assertEqual(VoiceIO.input_devices(), [(0, "Microfone USB")])
            with self.assertRaisesRegex(VoiceError, "Nenhuma fala"):
                VoiceIO(device=0).record(1)
        self.assertEqual(recorded[0]["device"], 0)

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

    def test_wake_word_variants_are_removed_before_submission(self):
        examples = (("Jarvis, abra o Firefox", "abra o Firefox"),
                    ("Hey Jarvis: organize as janelas", "organize as janelas"),
                    ("Jarves feche o terminal", "feche o terminal"),
                    ("Djarvis, abra o projeto", "abra o projeto"),
                    ("Davies, abra o Firefox", "abra o Firefox"),
                    ("De avis: abra o Firefox", "abra o Firefox"))
        for transcript, expected in examples:
            with self.subTest(transcript=transcript):
                self.assertEqual(WakeWordConversation.remove_wake_word(transcript), expected)

    def test_wake_word_only_becomes_empty_command(self):
        self.assertEqual(WakeWordConversation.remove_wake_word("Hey Jarvis!"), "")

    def test_wake_command_must_start_with_wake_word(self):
        self.assertEqual(WakeWordConversation.extract_wake_command("Jarves, abra Firefox"),
                         (True, "abra Firefox"))
        self.assertEqual(WakeWordConversation.extract_wake_command("Hey Jarvis"),
                         (True, ""))
        self.assertEqual(WakeWordConversation.extract_wake_command("Davies."),
                         (True, ""))
        self.assertEqual(WakeWordConversation.extract_wake_command("Abra Firefox"),
                         (False, "Abra Firefox"))

    def test_voice_activity_capture_keeps_leading_speech_and_stops_at_silence(self):
        import numpy as np
        from types import SimpleNamespace
        blocks = ([np.zeros((1280, 1), dtype=np.int16) for _ in range(4)] +
                  [np.full((1280, 1), 600, dtype=np.int16) for _ in range(8)] +
                  [np.zeros((1280, 1), dtype=np.int16) for _ in range(8)])

        class InputStream:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]
            def __enter__(self):
                for block in blocks:
                    self.callback(block, len(block), None, None)
                return self
            def __exit__(self, *_args):
                return False

        listener = WakeWordConversation(VoiceIO(silence_rms=150), lambda _text: None,
                                        silence_seconds=0.24)
        samples = listener._listen_for_command(SimpleNamespace(InputStream=InputStream), np)
        self.assertIsNotNone(samples)
        self.assertGreater(int(samples.max()), 500)
        self.assertEqual(len(samples), (4 + 8 + 3) * 1280)

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
