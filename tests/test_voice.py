"""Testes locais de voz sem hardware nem downloads."""
import tempfile
import os
import sys
from array import array
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from jarvis.voice import VoiceIO, VoiceError, WakeWordConversation

class VoiceTests(unittest.TestCase):
    def setUp(self):
        preferences = tempfile.TemporaryDirectory()
        self.addCleanup(preferences.cleanup)
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for key in ('JARVIS_PIPER_MODEL', 'JARVIS_AUDIO_DEVICE', 'JARVIS_AUDIO_OUTPUT',
                    'JARVIS_WHISPER_MODEL', 'JARVIS_SILENCE_MS', 'JARVIS_VAD_THRESHOLD', 'JARVIS_VOICE_MODE',
                    'JARVIS_FOLLOWUP_SECONDS', 'JARVIS_START_TIMEOUT_SECONDS', 'JARVIS_AUDIO_RETRIES'):
            os.environ.pop(key, None)
        os.environ['JARVIS_PREFERENCES'] = str(Path(preferences.name) / 'preferences.json')
        # Estes testes verificam captura/lifecycle, não a precisão do classificador.
        activity = patch('jarvis.audio_activity.SileroActivity', side_effect=lambda **_:
            SimpleNamespace(active=lambda pcm: bool(abs(pcm).max() >= 180)))
        activity.start()
        self.addCleanup(activity.stop)

    def test_record_duration_bounds(self):
        voice = VoiceIO()
        for seconds in (0, -1, 16, 999):
            with self.subTest(seconds=seconds), self.assertRaises(VoiceError):
                voice.record(seconds)

    def _capture_backend(self, samples):
        stream = Mock()
        backend = SimpleNamespace(InputStream=Mock(return_value=stream),
                                  CallbackStop=type("CallbackStop", (Exception,), {}))
        def start():
            callback = backend.InputStream.call_args.kwargs["callback"]
            try:
                callback(samples, len(samples), None, None)
            except backend.CallbackStop:
                pass
        stream.start.side_effect = start
        return backend, stream

    def test_silence_is_rejected_and_device_is_selected(self):
        backend, stream = self._capture_backend(array("h", [0] * 16000))
        with patch.dict(sys.modules, {"sounddevice": backend}):
            with self.assertRaisesRegex(VoiceError, "Nenhuma fala"):
                VoiceIO(device="pulse").record(1)
        self.assertEqual(backend.InputStream.call_args.kwargs["device"], "pulse")
        stream.abort.assert_called_once()
        stream.close.assert_called_once()

    def test_capture_without_callbacks_times_out_and_releases_device(self):
        backend, stream = self._capture_backend(array("h"))
        stream.start.side_effect = None
        with patch.dict(sys.modules, {"sounddevice": backend}), patch(
                "jarvis.voice.threading.Event") as event:
            event.return_value.wait.return_value = False
            with self.assertRaisesRegex(VoiceError, "Tempo limite de captura"):
                VoiceIO().record(6)
            event.return_value.wait.assert_called_once_with(9)
        stream.abort.assert_called_once()
        stream.close.assert_called_once()

    def test_capture_writes_exact_duration_and_closes_stream(self):
        import wave
        backend, stream = self._capture_backend(array("h", [600] * 17000))
        with patch.dict(sys.modules, {"sounddevice": backend}):
            recording = VoiceIO().record(1)
        try:
            with wave.open(str(recording)) as wav:
                self.assertEqual(wav.getnframes(), 16000)
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getsampwidth(), 2)
        finally:
            recording.unlink()
        stream.close.assert_called_once()

    def test_capture_start_failure_releases_device(self):
        backend, stream = self._capture_backend(array("h"))
        stream.start.side_effect = RuntimeError("disconnected")
        with patch.dict(sys.modules, {"sounddevice": backend}):
            with self.assertRaisesRegex(VoiceError, "Microfone indisponível"):
                VoiceIO().record(1)
        stream.close.assert_called_once()

    def test_continuous_listener_inherits_voice_device(self):
        voice = VoiceIO(device="Bluetooth microphone")
        self.assertEqual(WakeWordConversation(voice, lambda _: None).device, voice.device)
        self.assertEqual(WakeWordConversation(voice, lambda _: None, device=0).device, 0)

    def test_diagnostic_record_accepts_silence_and_reports_levels(self):
        backend, stream = self._capture_backend(array("h", [0]*16000))
        updates = []
        with patch.dict(sys.modules, {"sounddevice": backend}):
            recording = VoiceIO().record(1, allow_silence=True, on_level=updates.append)
        try:
            self.assertEqual(updates[-1]["dbfs"], -96)
            self.assertEqual(updates[-1]["elapsed"], 1)
        finally:
            recording.unlink()

    def test_paused_listener_does_not_open_microphone(self):
        import numpy as np
        backend = Mock()
        listener = WakeWordConversation(VoiceIO(), lambda _: None)
        self.assertTrue(listener.pause(timeout=0))
        self.assertIsNone(listener._listen_for_command(backend, np))
        backend.InputStream.assert_not_called()

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
            self.assertEqual(voice._stt.transcribe.call_args.kwargs['beam_size'], 5)
            self.assertFalse(voice._stt.transcribe.call_args.kwargs['condition_on_previous_text'])

    def test_uncertain_stt_discards_whole_turn_without_blacklisting_valid_words(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'sample.wav'
            path.write_bytes(b'fixture')
            voice = VoiceIO()
            voice._stt = Mock()
            voice._stt.transcribe.return_value = ([SimpleNamespace(text='abra Firefox', no_speech_prob=.9, avg_logprob=-2)], None)
            with self.assertRaisesRegex(VoiceError, 'incerta'):
                voice.transcribe(path)
            voice._stt.transcribe.return_value = ([SimpleNamespace(text='obrigado', no_speech_prob=.1, avg_logprob=-.2)], None)
            self.assertEqual(voice.transcribe(path), 'obrigado')

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

    def test_continuous_listener_recovers_after_transcription_error(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            files = [Path(td) / "first.wav", Path(td) / "second.wav"]
            for path in files:
                path.write_bytes(b"audio")
            voice = VoiceIO()
            voice.transcribe = Mock(side_effect=[VoiceError("silêncio"), "Jarvis, olá"])
            commands, statuses = [], []
            listener = WakeWordConversation(voice, lambda text: (
                commands.append(text), listener._stop.set()), statuses.append)
            listener._listen_for_command = Mock(return_value=np.array([600], dtype=np.int16))
            listener._write_recording = Mock(side_effect=files)
            with patch.dict(sys.modules, {"sounddevice": SimpleNamespace()}):
                listener._run()
            self.assertEqual(commands, ["olá"])
            self.assertTrue(any("Aguardando Jarvis novamente" in x for x in statuses))
            self.assertTrue(all(not path.exists() for path in files))

    def test_continuous_capture_without_frames_has_deadline(self):
        import numpy as np
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        backend = SimpleNamespace(InputStream=Mock(return_value=stream))
        listener = WakeWordConversation(VoiceIO(), lambda _: None)
        with patch("jarvis.voice.time.monotonic", side_effect=[0, 4]), patch(
                "jarvis.voice.queue.Queue") as frames:
            frames.return_value.get.side_effect = __import__("queue").Empty
            with self.assertRaisesRegex(VoiceError, "sem entregar áudio"):
                listener._listen_for_command(backend, np)
        stream.__exit__.assert_called_once()

    def test_rejected_voice_request_resumes_and_reports_missing_wake_word(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            voice = VoiceIO()
            voice.transcribe = Mock(side_effect=["Olá mundo", "Jarvis, olá"])
            statuses = []
            submitted = Mock(return_value=False)
            listener = WakeWordConversation(voice, submitted, statuses.append)
            # O worker retoma a escuta quando termina a tarefa que bloqueou o envio.
            submitted.side_effect = lambda _text: (listener.resume(), False)[1]
            def capture(*_args, **_kwargs):
                if voice.transcribe.call_count == 2:
                    listener._stop.set()
                    return None
                return np.array([600], dtype=np.int16)
            def recording(_samples):
                path = Path(td) / 'sample.wav'
                path.write_bytes(b'audio')
                return path
            listener._listen_for_command = capture
            listener._write_recording = recording
            with patch.dict(sys.modules, {"sounddevice": SimpleNamespace()}):
                listener._run()
            submitted.assert_called_once_with("olá")
            self.assertTrue(listener._resume.is_set())
            self.assertTrue(any("sem ativação" in text for text in statuses))
            self.assertTrue(any("não enviado" in text for text in statuses))
            self.assertFalse((Path(td) / 'sample.wav').exists())

    def test_piper_exec_and_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            model = Path(td) / "voice.onnx"
            model.write_bytes(b"mock")
            voice = VoiceIO(piper_model=str(model))
            with patch("jarvis.voice.shutil.which", return_value="/bin/true"), patch.object(voice, '_run_audio') as run, patch('jarvis.tts_engine.synthesizer.synthesize') as synthesize:
                self.assertEqual(voice.speak("Olá"), "spoken")
                self.assertEqual(run.call_count, 1)
                synthesize.assert_called_once()
                self.assertEqual(synthesize.call_args.args[1], 'Olá')
                self.assertEqual(run.call_args_list[0].args[0][0], "aplay")

    def test_overflow_invalidates_turn_instead_of_transcribing_missing_audio(self):
        import numpy as np
        class Stream:
            def __init__(self, **kwargs): self.callback = kwargs['callback']
            def __enter__(self):
                for _ in range(65):
                    self.callback(np.full((1280, 1), 600, dtype=np.int16), 1280, None, None)
                return self
            def __exit__(self, *_): pass
        listener = WakeWordConversation(VoiceIO(), lambda _: self.fail('não enviar'))
        with self.assertRaisesRegex(VoiceError, 'overflow'):
            listener._listen_for_command(SimpleNamespace(InputStream=Stream), np)
        self.assertTrue(listener._capture_idle.is_set())

    def test_capture_exclusion_between_diagnostic_and_listener(self):
        from jarvis.voice import _capture_owner
        _capture_owner.acquire()
        try:
            with self.assertRaisesRegex(VoiceError, 'ocupado'):
                VoiceIO().record(1)
        finally:
            _capture_owner.release()

    def test_disconnected_listener_has_bounded_retries(self):
        listener = WakeWordConversation(VoiceIO(), lambda _: self.fail('não enviar'))
        listener._listen_for_command = Mock(side_effect=VoiceError('desconectado'))
        listener._stop.wait = Mock(return_value=False)
        statuses = []
        listener.on_status = statuses.append
        with patch.dict(sys.modules, {'sounddevice': SimpleNamespace()}):
            listener._run()
        self.assertEqual(listener._listen_for_command.call_count, 3)
        self.assertEqual([call.args[0] for call in listener._stop.wait.call_args_list], [0.5, 1.0])
        self.assertIn('Escuta contínua indisponível:', statuses[-1])

    def test_zero_retries_stops_after_first_capture_failure(self):
        voice = VoiceIO()
        voice.reconnect_attempts = 0
        listener = WakeWordConversation(voice, lambda _: self.fail('não enviar'))
        listener._listen_for_command = Mock(side_effect=VoiceError('desconectado'))
        listener._stop.wait = Mock()
        with patch.dict(sys.modules, {'sounddevice': SimpleNamespace()}):
            listener._run()
        listener._listen_for_command.assert_called_once()
        listener._stop.wait.assert_not_called()

    def test_manual_capture_uses_configured_start_timeout(self):
        import numpy as np
        voice = VoiceIO()
        voice.start_timeout_seconds = 12
        with patch('jarvis.voice.WakeWordConversation') as listener, patch.dict(sys.modules, {'sounddevice': SimpleNamespace()}):
            listener.return_value._listen_for_command.return_value = np.array([600], dtype=np.int16)
            voice.record_turn()
        self.assertEqual(listener.return_value._listen_for_command.call_args.kwargs['idle_timeout'], 12)

    def test_followup_uses_configured_window_after_answer(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            voice = VoiceIO()
            voice.followup_seconds = 7
            path = Path(td) / 'sample.wav'
            path.write_bytes(b'controlled')
            listener = WakeWordConversation(voice, lambda _: listener.resume())
            voice.transcribe = Mock(return_value='Jarvis, olá')
            calls = []
            def capture(*_args, **kwargs):
                calls.append(kwargs['idle_timeout'])
                if len(calls) == 2:
                    listener._stop.set()
                    return None
                return np.array([600], dtype=np.int16)
            listener._listen_for_command = capture
            listener._write_recording = Mock(return_value=path)
            with patch.dict(sys.modules, {'sounddevice': SimpleNamespace()}):
                listener._run()
            self.assertEqual(calls, [None, 7])

    def test_followup_deadline_never_expires_after_speech_starts(self):
        import numpy as np
        class Stream:
            def __init__(self, **kwargs): self.callback = kwargs['callback']
            def __enter__(self):
                for value in [600] * 5 + [0] * 13:
                    self.callback(np.full((1280, 1), value, dtype=np.int16), 1280, None, None)
                return self
            def __exit__(self, *_): pass
        listener = WakeWordConversation(VoiceIO(), lambda _: None)
        # Tempo de parede salta além da janela enquanto há fala.
        with patch('jarvis.voice.time.monotonic', side_effect=range(0, 10000, 30)):
            samples = listener._listen_for_command(SimpleNamespace(InputStream=Stream), np, idle_timeout=20)
        self.assertEqual(len(samples), 18 * 1280)

    def test_stopping_during_stt_never_submits_late_command(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'sample.wav'
            path.write_bytes(b'mock')
            voice, command = VoiceIO(), Mock()
            listener = WakeWordConversation(voice, command)
            listener._listen_for_command = Mock(return_value=np.array([600], dtype=np.int16))
            listener._write_recording = Mock(return_value=path)
            voice.transcribe = Mock(side_effect=lambda _: (listener.stop(timeout=0), 'Jarvis abra Firefox')[1])
            with patch.dict(sys.modules, {'sounddevice': SimpleNamespace()}):
                listener._run()
            command.assert_not_called()
            self.assertFalse(path.exists())

    def test_cancelled_player_is_terminated_and_reaped(self):
        from jarvis.cancellation import CancelledError
        voice = VoiceIO()
        process = Mock()
        process.poll.return_value = None
        def wait(**_):
            voice.cancel_speech()
            raise __import__('subprocess').TimeoutExpired('aplay', 0.1)
        process.communicate.side_effect = [wait, ('', '')]
        # Mock side_effect não invoca funções dentro de lista.
        calls = 0
        def communicate(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return wait(**kwargs)
            return '', ''
        process.communicate.side_effect = communicate
        with patch('jarvis.voice.subprocess.Popen', return_value=process):
            with self.assertRaises(CancelledError):
                voice._run_audio(['aplay', 'mock.wav'])
        process.terminate.assert_called_once()
        self.assertEqual(calls, 2)

    def test_long_tts_never_truncates_at_3000_characters(self):
        with tempfile.TemporaryDirectory() as td:
            model = Path(td) / 'voice.onnx'
            model.write_bytes(b'mock')
            voice = VoiceIO(piper_model=str(model))
            text = ' '.join('Frase completa.' for _ in range(300))
            with patch('jarvis.voice.shutil.which', return_value='/bin/true'), patch.object(voice, '_run_audio'), patch('jarvis.tts_engine.synthesizer.synthesize') as run:
                self.assertEqual(voice.speak(text), 'spoken')
            spoken = ' '.join(call.args[1] for call in run.call_args_list)
            self.assertEqual(spoken, text)

if __name__ == "__main__":
    unittest.main()
