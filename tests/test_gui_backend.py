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
