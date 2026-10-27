import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from jarvis.audio_endpoint import AudioEndpoint, TurnLimitError
from jarvis.recording import PCMRecording
from jarvis.voice import VoiceIO, WakeWordConversation, PendingVoiceTurn


class RecordingSegmentsTests(unittest.TestCase):
    def test_segmented_pcm_roundtrip_sixty_seconds_without_losing_samples(self):
        import numpy as np
        recording = PCMRecording(1000)
        self.addCleanup(recording.close)
        endpoint = AudioEndpoint(1000, chunk_sink=recording.append)
        expected = bytearray()
        for index in range(600):
            block = np.full(100, index, dtype=np.int16)
            endpoint.feed(block, True)
            expected.extend(block.tobytes())
        for _ in range(10):
            block = np.zeros(100, dtype=np.int16)
            ended = endpoint.feed(block, False)
            expected.extend(block.tobytes())
        self.assertTrue(ended)
        self.assertTrue(recording.stream._rolled)
        self.assertEqual(endpoint.chunks, [])
        with self.assertRaises(ValueError): recording.write_to(None)
        recording.complete = True
        target = io.BytesIO()
        with wave.open(target, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(1000)
            recording.write_to(wav)
        target.seek(0)
        with wave.open(target) as wav:
            self.assertEqual(wav.readframes(wav.getnframes()), bytes(expected))

    def test_emergency_turn_remains_pending_until_explicit_continuation(self):
        import numpy as np
        class Stream:
            values = [600] * 25
            def __init__(self, **kwargs): self.callback = kwargs['callback']
            def __enter__(self):
                for value in self.values:
                    self.callback(np.full((1280, 1), value, dtype=np.int16), 1280, None, None)
                return self
            def __exit__(self, *_): pass
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'JARVIS_PREFERENCES': str(Path(td) / 'preferences.json')}):
            voice = VoiceIO()
            self.addCleanup(voice.discard_pending)
            listener = WakeWordConversation(voice, lambda _: self.fail('não executar'), max_command_seconds=2,
                activity_factory=lambda: SimpleNamespace(active=lambda pcm: bool(abs(pcm).max() >= 180)))
            backend = SimpleNamespace(InputStream=Stream)
            with self.assertRaises(PendingVoiceTurn): listener._listen_for_command(backend, np)
            pending = voice.pending_audio
            prefix_count = len(pending)
            self.assertFalse(pending.complete)
            with self.assertRaises(PendingVoiceTurn): listener._listen_for_command(backend, np)
            self.assertIs(voice.pending_audio, pending)
            voice._continue_pending = True
            Stream.values = [700] * 2 + [0] * 13
            completed = listener._listen_for_command(backend, np)
            self.assertIs(completed, pending)
            self.assertTrue(completed.complete)
            self.assertEqual(len(completed), prefix_count + 15 * 1280)
            self.assertIsNone(voice.pending_audio)
            completed.close()

    def test_acoustic_gate_preserves_preroll_without_endpoint_on_ambient_speech(self):
        import numpy as np
        class Engine:
            available = True
            calls = 0
            def reset(self): pass
            def process(self, pcm):
                self.calls += 1
                return self.calls == 20
        class Stream:
            def __init__(self, **kwargs): self.callback = kwargs['callback']
            def __enter__(self):
                for value in [600] * 23 + [0] * 13:
                    self.callback(np.full((1280, 1), value, dtype=np.int16), 1280, None, None)
                return self
            def __exit__(self, *_): pass
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'JARVIS_PREFERENCES': str(Path(td) / 'p.json')}):
            voice = VoiceIO()
            events = []
            engine = Engine()
            listener = WakeWordConversation(voice, lambda _: None, wake_engine=engine, on_event=events.append,
                activity_factory=lambda: SimpleNamespace(active=lambda pcm: bool(abs(pcm).max() >= 180)))
            listener._require_wake = True
            recording = listener._listen_for_command(SimpleNamespace(InputStream=Stream), np)
            self.addCleanup(recording.close)
            self.assertEqual(engine.calls, 20)
            self.assertTrue(listener._acoustically_activated)
            self.assertLess(len(recording), 36 * 1280)
            self.assertEqual(len({event.turn_id for event in events}), 1)
            self.assertTrue(any(event.state == 'ouvindo' for event in events))
