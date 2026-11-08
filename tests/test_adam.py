"""Testes de ADAM sem ElevenLabs real, FCC, microfone ou rede externa."""
from array import array
from io import BytesIO
import os
from pathlib import Path
from threading import Event
import tempfile
from unittest import TestCase
from unittest.mock import patch
import wave

from jarvis.elevenlabs_tts import synthesize
from jarvis.personality import personality_instructions
from jarvis.voice import WakeWordConversation
from jarvis.preferences import Preferences


class AdamCoreTests(TestCase):
    def test_default_personality_and_user_customization(self):
        with patch.dict(os.environ, {"ADAM_PERSONA_FILE": ""}):
            self.assertIn("ADAM", personality_instructions())
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "persona.md"
            file.write_text("Fale de forma breve e inclua um lembrete sobre o café.", encoding="utf-8")
            with patch.dict(os.environ, {"ADAM_PERSONA_FILE": str(file)}):
                txt = personality_instructions()
                self.assertIn("café", txt)
                self.assertIn("ADAM", txt)

    def test_adam_primary_activation_word(self):
        for phrase in ("Adam, abra o Firefox", "Ei Adam! iniciar", "ADAM organize janelas"):
            self.assertTrue(WakeWordConversation.extract_wake_command(phrase)[0], phrase)
        self.assertEqual(WakeWordConversation.extract_wake_command("Adam, abra o Firefox"),
                         (True, "abra o Firefox"))
        self.assertEqual(WakeWordConversation.extract_wake_command("Abra o Firefox"),
                         (False, "Abra o Firefox"))

    def test_elevenlabs_is_default_backend(self):
        self.assertEqual(Preferences().tts_backend, "elevenlabs")

    def test_no_credentials_never_sends_request(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}), \
             patch("jarvis.elevenlabs_tts.urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "ELEVENLABS_API_KEY"):
                synthesize("Olá", Path(folder) / "spoken.wav", Event())
            request.assert_not_called()

    def test_pcm_stream_makes_valid_wav_without_leaking_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spoken.wav"
            data = array("h", [0, 300, -300, 150] * 200)
            with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "private_example_key"}), \
                 patch("jarvis.elevenlabs_tts.urlopen", return_value=BytesIO(data.tobytes())) as mock:
                synthesize("Olá", path, Event())
                self.assertEqual(mock.call_count, 1)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getnframes(), len(data))
            self.assertFalse((Path(folder) / "spoken.wav.incomplete").exists())

    def test_full_tts_pipeline_plays_mocked_elevenlabs_pcm(self):
        from jarvis.voice import VoiceIO
        samples = array("h", [250, -250] * 400)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "ELEVENLABS_API_KEY": "fake",
            "JARVIS_PREFERENCES": str(Path(folder) / "preferences.json"),
        }), patch("jarvis.elevenlabs_tts.urlopen", return_value=BytesIO(samples.tobytes())), \
             patch("jarvis.voice.shutil.which", return_value="/usr/bin/paplay"), \
             patch("jarvis.audio_output.shutil.which", return_value="/usr/bin/paplay"):
            voice = VoiceIO()
            self.assertEqual(voice.tts_backend, "elevenlabs")
            with patch.object(voice, "_run_audio") as play:
                self.assertEqual(voice.speak("Olá, teste."), "spoken")
                self.assertEqual(play.call_count, 1)
                self.assertEqual(play.call_args.args[0][0], "paplay")

    def test_cancel_avoids_network_call_and_output_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake"}), \
             patch("jarvis.elevenlabs_tts.urlopen") as request:
            cancel = Event()
            cancel.set()
            with self.assertRaisesRegex(Exception, "cancelada"):
                synthesize("teste", Path(folder) / "spoken.wav", cancel)
            request.assert_not_called()


if __name__ == "__main__":
    import unittest
    unittest.main()
