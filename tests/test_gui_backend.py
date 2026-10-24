"""GUI mantém operações no worker, sem depender de servidor X ou FCC real."""
import queue
import threading
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from jarvis.gui import GuiBackend


class FakeService:
    def __init__(self):
        self.client = SimpleNamespace(active_model="fake")
        self.approval = SimpleNamespace(mode="auto")
        self.toolkit = SimpleNamespace(capabilities=SimpleNamespace(enabled={"filesystem.read"}))
        self.planner = SimpleNamespace(snapshot=lambda: {"status": "no_plan"})
        self.agent = SimpleNamespace(last_metrics={"tools_executed": 0})
        self.called_in = None
        self.closed = False
        self.cancelled = False

    def ask(self, message):
        self.called_in = threading.current_thread().name
        return "Resposta: " + message

    def cancel_current(self):
        self.cancelled = True
        return True

    def close(self):
        self.closed = True


class GuiBackendTests(unittest.TestCase):
    def test_save_restarts_active_listener_with_new_microphone_and_model(self):
        from jarvis.preferences import PreferenceStore
        with tempfile.TemporaryDirectory() as td:
            backend = GuiBackend(None)
            backend.preference_store = PreferenceStore(Path(td) / 'preferences.json')
            old = Mock()
            old.stop.return_value = True
            backend._voice_listener = old
            backend._voice = SimpleNamespace(model_name='small', device='old mic')
            with patch('jarvis.voice.VoiceIO') as voice, patch('jarvis.voice.WakeWordConversation') as listener:
                backend._dispatch('voice_configure', {'audio_device': '14: new mic', 'stt_model': 'base', 'voice_mode': 'continuous'})
            old.stop.assert_called_once()
            self.assertEqual(voice.call_args.kwargs['model'], 'base')
            self.assertEqual(voice.call_args.kwargs['device'], 'new mic')
            listener.return_value.start.assert_called_once()
            self.assertEqual(backend.preference_store.load().audio_device, '14: new mic')

    def test_local_save_and_install_do_not_wait_for_fcc_initialization(self):
        from jarvis.preferences import PreferenceStore
        entered, release = threading.Event(), threading.Event()
        service = FakeService()
        def connect(*_args, **_kwargs):
            entered.set()
            release.wait(10)
            return service
        with tempfile.TemporaryDirectory() as td:
            backend = GuiBackend(None, service_factory=connect)
            backend.preference_store = PreferenceStore(Path(td) / 'preferences.json')
            backend.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(backend.submit('voice_configure', {'voice_mode': 'manual', 'piper_model': '/tmp/selected.onnx'}))
                events = []
                while ('busy', False) not in events:
                    events.append(backend.events.get(timeout=2))
                self.assertEqual(backend.preference_store.load().piper_model, '/tmp/selected.onnx')
                installed = Path(td) / 'installed.onnx'
                with patch('jarvis.voice_setup.install_faber', return_value=installed):
                    self.assertTrue(backend.submit('voice_install'))
                    events = []
                    while ('busy', False) not in events:
                        events.append(backend.events.get(timeout=2))
                self.assertIn(('voice_installed', str(installed)), events)
                self.assertEqual(backend.preference_store.load().piper_model, str(installed))
                self.assertIsNone(backend.service)
                self.assertFalse(release.is_set())
            finally:
                backend.close()
                release.set()
                backend._thread.join(2)
                backend._local_thread.join(2)
            self.assertFalse(backend._local_thread.is_alive())
            self.assertTrue(service.closed)

    def test_button_audio_to_verified_effect_and_visual_reply_journey(self):
        import sys
        import numpy as np
        from jarvis.voice import VoiceIO
        class Stream:
            def __init__(self, **kwargs): self.callback = kwargs['callback']
            def __enter__(self):
                for level in [600] * 38 + [0] * 13:
                    self.callback(np.full((1280, 1), level, dtype=np.int16), 1280, None, None)
                return self
            def __exit__(self, *_): pass
        backend = GuiBackend(None)
        backend.service = FakeService()
        voice = VoiceIO(model='small', piper_model='')
        voice.piper_model = None
        voice._stt = Mock()
        voice._stt.transcribe.return_value = ([SimpleNamespace(text='adicione revisar relatório às tarefas')], None)
        effects = []
        def execute(message):
            effects.append(message)
            return 'Tarefa adicionada e verificada.'
        backend.service.ask = execute
        with patch.dict(sys.modules, {'sounddevice': SimpleNamespace(InputStream=Stream)}), patch('jarvis.voice.VoiceIO', return_value=voice), patch('jarvis.audio_activity.SileroActivity', side_effect=lambda **_: SimpleNamespace(active=lambda pcm: bool(abs(pcm).max() >= 180))):
            backend._dispatch('voice_push_to_talk', {'model': 'small'})
        self.assertEqual(effects, ['adicione revisar relatório às tarefas'])
        self.assertIn(('answer', 'Tarefa adicionada e verificada.'), list(backend.events.queue))
        recording = Path(voice._stt.transcribe.call_args.args[0])
        self.assertFalse(recording.exists())

    def test_voice_preferences_save_and_reload_without_fcc(self):
        from jarvis.preferences import PreferenceStore
        with tempfile.TemporaryDirectory() as td:
            backend = GuiBackend(None)
            backend.preference_store = PreferenceStore(Path(td) / 'preferences.json')
            backend._dispatch('voice_configure', {'piper_model': '/tmp/voz.onnx',
                'output_device': 'bluez_output.test', 'silence_ms': 1200, 'voice_mode': 'manual'})
            saved = backend.preference_store.load()
            self.assertEqual(saved.output_device, 'bluez_output.test')
            self.assertEqual(saved.silence_ms, 1200)
            self.assertIsNone(backend.service)

    def test_push_to_talk_transcribes_sends_and_removes_wav(self):
        backend = GuiBackend(None)
        backend.service = FakeService()
        with tempfile.TemporaryDirectory() as td, patch('jarvis.voice.VoiceIO') as factory:
            recording = Path(td) / 'sample.wav'
            recording.write_bytes(b'audio')
            voice = factory.return_value
            voice.record_turn.return_value = recording
            voice.transcribe.return_value = 'Quanto é dois mais dois?'
            voice.piper_model = None
            voice.model_name = 'small'
            voice.device = 'Bluetooth mic'
            backend._dispatch('voice_push_to_talk', {'device':'14: Bluetooth mic', 'model':'small'})
            self.assertEqual(factory.call_args.kwargs['device'], 'Bluetooth mic')
            self.assertEqual(factory.call_args.kwargs['model'], 'small')
            self.assertFalse(recording.exists())
            events = list(backend.events.queue)
            self.assertIn(('voice_transcript', 'Quanto é dois mais dois?'), events)
            self.assertIn(('answer', 'Resposta: Quanto é dois mais dois?'), events)
            recording.write_bytes(b'second audio')
            backend._dispatch('voice_push_to_talk', {'device':'14: Bluetooth mic', 'model':'small'})
            factory.assert_called_once()
            self.assertFalse(recording.exists())

    def test_push_to_talk_does_not_send_failed_transcription(self):
        backend = GuiBackend(None)
        backend.service = FakeService()
        with tempfile.TemporaryDirectory() as td, patch('jarvis.voice.VoiceIO') as factory:
            recording = Path(td) / 'sample.wav'
            recording.write_bytes(b'audio')
            factory.return_value.record_turn.return_value = recording
            factory.return_value.transcribe.side_effect = RuntimeError('sem fala')
            with self.assertRaisesRegex(RuntimeError, 'sem fala'):
                backend._dispatch('voice_push_to_talk', {'model':'small'})
            self.assertFalse(recording.exists())
            self.assertIsNone(backend.service.called_in)

    def test_message_runs_on_worker_and_returns_plan_and_metrics(self):
        service = FakeService()
        backend = GuiBackend(None, service_factory=lambda *_a, **_kw: service)
        backend.start()
        self.assertEqual(backend.events.get(timeout=2)[0], "connected")
        backend.submit("ask", "Olá")
        received = {}
        while "busy_done" not in received:
            kind, value = backend.events.get(timeout=2)
            received["busy_done" if kind == "busy" and value is False else kind] = value
        self.assertEqual(received["answer"], "Resposta: Olá")
        self.assertEqual(received["plan"]["status"], "no_plan")
        self.assertEqual(service.called_in, "jarvis-gui-worker")
        self.assertTrue(backend.cancel())
        backend.close()
        backend._thread.join(timeout=2)
        self.assertTrue(service.closed)

    def test_repeated_submit_is_rejected_and_pending_cancel_prevents_execution(self):
        service = FakeService()
        backend = GuiBackend(None, service_factory=lambda *_a, **_kw: service)
        self.assertTrue(backend.submit("ask", "primeiro"))
        self.assertFalse(backend.submit("ask", "duplicado"))
        self.assertEqual(backend.commands.qsize(), 1)
        self.assertTrue(backend.cancel())
        backend.start()
        while True:
            event = backend.events.get(timeout=2)
            if event == ("busy", False):
                break
        self.assertIsNone(service.called_in)
        self.assertFalse(backend._action_pending.is_set())
        backend.close()
        backend._thread.join(2)

    def test_reconnect_refreshes_existing_service_without_discarding_it(self):
        backend = GuiBackend(None)
        service = FakeService()
        service.client = Mock(active_model="selected")
        service.client.available_models.return_value = ["selected", "other"]
        backend.service = service
        backend._reconnect()
        self.assertIs(backend.service, service)
        service.client.available_models.assert_called_once()
        self.assertEqual(backend.events.get_nowait(), ("models", ["selected", "other"]))
        self.assertEqual(backend.events.get_nowait(), ("reconnected", "selected"))

    def test_plan_controls_use_shared_service(self):
        backend = GuiBackend(None)
        service = FakeService()
        service.plan_action = Mock(return_value={"status":"ready"})
        backend.service = service
        backend._dispatch("plan_action", ("prepare", "Organizar janelas"))
        service.plan_action.assert_called_once_with("prepare", "Organizar janelas")
        self.assertEqual(backend.events.get_nowait(), ("plan", {"status":"ready"}))

    def test_voice_diagnostic_works_without_fcc_and_cleans_recording(self):
        backend = GuiBackend(None, service_factory=Mock(side_effect=RuntimeError("FCC offline")))
        with patch("jarvis.voice_diagnostics.VoiceDiagnostics") as diagnostic:
            diagnostic.return_value.probe.return_value = {"status":"available", "device":"Bluetooth"}
            backend.start()
            self.assertEqual(backend.events.get(timeout=2)[0], "connection_error")
            self.assertTrue(backend.submit("voice_test_probe", "14: Bluetooth"))
            while True:
                kind, value = backend.events.get(timeout=2)
                if kind == "voice_test_probe":
                    self.assertEqual(value["device"], "Bluetooth")
                    break
            diagnostic.return_value.probe.assert_called_once_with("Bluetooth")
            backend.close()
            backend._thread.join(2)
            diagnostic.return_value.close.assert_called_once()

    def test_diagnostic_capture_only_emits_local_events(self):
        backend = GuiBackend(None)
        backend._voice_test = Mock()
        backend._voice_test.capture.return_value = {"signal":"sinal_detectado"}
        backend._dispatch("voice_test_capture", "9: Bluetooth")
        backend._voice_test.capture.assert_called_once()
        callback = backend._voice_test.capture.call_args.kwargs["on_level"]
        callback({"dbfs":-20,"elapsed":1})
        events = []
        while not backend.events.empty():
            events.append(backend.events.get_nowait()[0])
        self.assertIn("voice_test_capture", events)
        self.assertIn("voice_test_level", events)
        self.assertNotIn("voice_transcript", events)

    def test_diagnostic_aborts_if_continuous_capture_does_not_release_device(self):
        backend = GuiBackend(None, service_factory=Mock(side_effect=RuntimeError("offline")))
        backend._voice_listener = Mock()
        backend._voice_listener.pause.return_value = False
        backend._voice_test = Mock()
        backend.start()
        backend.submit("voice_test_capture", "Bluetooth")
        events = []
        while True:
            event = backend.events.get(timeout=2)
            events.append(event)
            if event == ("busy", False):
                break
        backend._voice_listener.pause.assert_called_once_with(timeout=2)
        backend._voice_test.capture.assert_not_called()
        self.assertTrue(any(kind == "voice_test_error" for kind, _ in events))
        backend._voice_listener.resume.assert_called_once()
        backend.close()
        backend._thread.join(2)

    def test_text_turn_pauses_and_resumes_voice_listener(self):
        backend = GuiBackend(None)
        backend.service = FakeService()
        backend._voice_listener = Mock()
        backend._dispatch("ask", "Olá")
        backend._voice_listener.pause.assert_called_once()
        backend._voice_listener.resume.assert_called_once()

    def test_task_panel_uses_toolkit_and_refreshes(self):
        backend = GuiBackend(None)
        service = FakeService()
        service.toolkit = Mock()
        service.toolkit.execute.side_effect = [
            {"result": {"status": "state_verified", "task_id": 1}},
            {"result": {"status": "listed", "tasks": [{"id": 1}]}}]
        backend.service = service
        backend._dispatch("tool_action", ("task_add", {"title": "Estudar"}))
        self.assertEqual(service.toolkit.execute.call_args_list[0].args,
                         ("task_add", {"title": "Estudar"}))
        events = [backend.events.get_nowait(), backend.events.get_nowait()]
        self.assertEqual(events[1][0], "task_board")

    def test_tool_panel_does_not_hide_permission_error(self):
        backend = GuiBackend(None)
        backend.service = FakeService()
        backend.service.toolkit = Mock()
        backend.service.toolkit.execute.return_value = {"error": "Capacidade não autorizada"}
        with self.assertRaisesRegex(RuntimeError, "Capacidade"):
            backend._dispatch("tool_action", ("browser_tabs", {}))
        with self.assertRaises(ValueError):
            backend._dispatch("tool_action", ("run_command", {}))

    def test_record_selection_uses_name_and_configured_model(self):
        backend = GuiBackend(None)
        backend.service = FakeService()
        with patch("jarvis.voice.VoiceIO") as voice, patch.dict(
                "os.environ", {"JARVIS_WHISPER_MODEL": "small", "JARVIS_LANGUAGE": "pt"}):
            backend._dispatch("voice_record", "14: Bluetooth mic")
            self.assertEqual(voice.call_args.kwargs,
                             {"model": "small", "language": "pt", "device": "Bluetooth mic"})

    def test_continuous_voice_uses_applied_model_and_device(self):
        backend = GuiBackend(None)
        backend.service = FakeService()
        with patch("jarvis.voice.VoiceIO") as voice, patch("jarvis.voice.WakeWordConversation") as listener:
            backend._dispatch("voice_listen_start", {"device":"14: Bluetooth mic", "model":"small"})
            self.assertEqual(voice.call_args.kwargs["model"], "small")
            self.assertEqual(voice.call_args.kwargs["device"], "Bluetooth mic")
            listener.return_value.start.assert_called_once()
            listener.call_args.kwargs["on_status"]("Aguardando Jarvis")
            listener.call_args.kwargs["on_transcript"]("Olá mundo")
            self.assertIn(("voice_heard", "Olá mundo"), list(backend.events.queue))
            self.assertIn(("voice_status", "Whisper small: Aguardando Jarvis"), list(backend.events.queue))

    def test_explicit_audio_environment_matches_announced_effective_settings(self):
        backend = GuiBackend(None)
        with patch.dict('os.environ', {'JARVIS_WHISPER_MODEL': 'base', 'JARVIS_AUDIO_DEVICE': 'explicit mic'}), patch('jarvis.voice.VoiceIO') as voice, patch('jarvis.voice.WakeWordConversation') as listener:
            backend._dispatch('voice_listen_start', {'device': 'selected mic', 'model': 'small'})
            self.assertEqual(voice.call_args.kwargs['model'], 'base')
            self.assertEqual(voice.call_args.kwargs['device'], 'explicit mic')
            self.assertEqual(listener.call_args.kwargs['device'], 'explicit mic')
            listener.call_args.kwargs['on_status']('Ouvindo')
            self.assertIn(('voice_status', 'Whisper base: Ouvindo'), list(backend.events.queue))

    def test_model_change_waits_for_old_listener_to_stop(self):
        backend = GuiBackend(None)
        backend._voice_listener = Mock()
        backend._voice_listener.stop.return_value = False
        with patch("jarvis.voice.VoiceIO") as voice:
            with self.assertRaisesRegex(RuntimeError, "ainda está encerrando"):
                backend._dispatch("voice_listen_start", {"model":"small"})
            voice.assert_not_called()

    def test_voice_turn_uses_service_and_resumes_listener(self):
        service = FakeService()
        backend = GuiBackend(None, service_factory=lambda *_a, **_kw: service)
        class Listener:
            resumed = False
            def resume(self):
                self.resumed = True
        class Voice:
            piper_model = object()
            def prepare_speech(self): pass
            def speak(self, text):
                return "spoken"
        backend.service = service
        backend._voice = Voice()
        backend._voice_listener = Listener()
        backend._dispatch("voice_ask", "abra o Firefox")
        events = []
        while not backend.events.empty():
            events.append(backend.events.get_nowait())
        self.assertIn(("voice_transcript", "abra o Firefox"), events)
        self.assertIn(("answer", "Resposta: abra o Firefox"), events)
        self.assertTrue(any(kind == 'conversation_event' and value.state == 'aguardando_seguimento'
                            for kind, value in events))
        self.assertTrue(backend._voice_listener.resumed)


if __name__ == "__main__":
    unittest.main()
