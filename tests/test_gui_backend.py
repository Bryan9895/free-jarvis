"""GUI mantém operações no worker, sem depender de servidor X ou FCC real."""
import queue
import threading
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
            self.assertIn(("voice_status", "Whisper small: Aguardando Jarvis"), list(backend.events.queue))

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
        self.assertIn(("voice_status", "spoken"), events)
        self.assertTrue(backend._voice_listener.resumed)


if __name__ == "__main__":
    unittest.main()
