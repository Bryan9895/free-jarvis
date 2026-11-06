from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import sys
import wave
import numpy as np

from jarvis.voice import VoiceIO, WakeWordConversation


class ClapConversationTests(TestCase):
    def test_split_clap_preserves_command_start_and_arms_only_one_turn(self):
        voice = VoiceIO()
        voice.clap_enabled = True
        signal = np.zeros(1280 * 6, dtype=np.int16)
        signal[1280 * 3 - 20:1280 * 3 + 20:2] = 30000
        signal[1280 * 3 - 19:1280 * 3 + 20:2] = -30000
        speech = (600 + np.arange(1280 * 4, dtype=np.int16) % 500).astype(np.int16)
        signal = np.concatenate((signal, speech, np.zeros(1280 * 4, dtype=np.int16)))
        commands, activated, decoded, paths, statuses = [], [], [], [], []
        construction, opened, maximum = [], [], []
        def transcribe(path):
            paths.append(Path(path))
            with wave.open(str(path)) as audio: decoded.append(audio.readframes(audio.getnframes()))
            return 'crie um arquivo de teste'
        voice.transcribe = transcribe
        def command(text):
            commands.append(str(text))
            listener.resume()
        listener = WakeWordConversation(voice, command, on_status=statuses.append, silence_seconds=.16,
            on_activation=activated.append,
            activity_factory=lambda: SimpleNamespace(active=lambda pcm: bool(np.max(np.abs(pcm)) > 300)))
        class Stream:
            def __init__(self, **kwargs):
                self.callback = kwargs['callback']
                construction.append(self)
            def __enter__(self):
                opened.append(self)
                maximum.append(len(opened))
                if len(construction) == 1:
                    for start in range(0, len(signal), 1280):
                        block = signal[start:start + 1280].reshape(-1, 1)
                        self.callback(block, len(block), None, None)
                else:
                    self.assert_waiting()
                    listener._stop.set()
                return self
            def assert_waiting(self):
                if not listener._waiting_activation:
                    raise AssertionError('Clap unexpectedly opened a followup session')
            def __exit__(self, *_): opened.remove(self)
        backend = SimpleNamespace(InputStream=Stream,
            query_devices=lambda *_, **__: {'name': 'Controlled PCM', 'max_input_channels': 1, 'default_samplerate': 16000},
            check_input_settings=lambda **_: None)
        with patch.dict(sys.modules, {'sounddevice': backend}):
            listener._run()
        self.assertEqual(commands, ['crie um arquivo de teste'], statuses)
        self.assertEqual(activated, ['clap'])
        self.assertFalse(any('conversação por voz ativa' in status for status in statuses))
        self.assertEqual(max(maximum), 1)
        self.assertIn(speech.tobytes(), decoded[0])
        self.assertLess(np.max(np.frombuffer(decoded[0], dtype=np.int16)), 2000)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_fallback_speech_start_is_preserved_and_pause_discards_finished_capture(self):
        speech = (600 + np.arange(1280 * 4, dtype=np.int16) % 500).astype(np.int16)
        signal = np.concatenate((speech, np.zeros(1280 * 3, dtype=np.int16)))
        for paused in (False, True):
            with self.subTest(paused=paused):
                voice = VoiceIO()
                voice.clap_enabled = True
                listener = WakeWordConversation(voice, lambda _: None, silence_seconds=.16,
                    activity_factory=lambda: SimpleNamespace(active=lambda pcm: bool(np.max(np.abs(pcm)) > 300)))
                listener._waiting_activation = True
                class Stream:
                    def __init__(self, **kwargs): self.callback = kwargs['callback']
                    def __enter__(self):
                        for start in range(0, len(signal), 1280):
                            block = signal[start:start + 1280].reshape(-1, 1)
                            self.callback(block, len(block), None, None)
                        return self
                    def __exit__(self, *_):
                        if paused: listener.pause()
                result = listener._listen_for_command(SimpleNamespace(InputStream=Stream), np)
                if paused:
                    self.assertIsNone(result)
                else:
                    path = listener._write_recording(result)
                    try:
                        with wave.open(str(path)) as audio: data = audio.readframes(audio.getnframes())
                        self.assertTrue(data.startswith(speech.tobytes()))
                        self.assertFalse(listener._clap_activated)
                    finally:
                        path.unlink(missing_ok=True)
