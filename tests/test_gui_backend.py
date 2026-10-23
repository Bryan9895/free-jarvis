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
