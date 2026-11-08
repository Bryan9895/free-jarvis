"""Contratos da interface web; não usa rede externa, FCC real nem áudio físico."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from jarvis.web_ui import WEB, OrbHandler, OrbState


class OrbUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "JARVIS_ORB_SETTINGS": str(Path(self.tmp.name) / "prefs.json"),
            "ELEVENLABS_API_KEY": "",
            "JARVIS_TTS_BACKEND": "piper",
            "JARVIS_PIPER_MODEL": "",
        })
        self.env.start()
        self.app = OrbState(SimpleNamespace(profile="fcc"), start_worker=False)
        self.app._voice_available = lambda: False

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_original_orb_page_contains_2400_points_and_essential_shortcuts(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("const N = 2400", html)
        self.assertIn('id="esfera"', html)
        self.assertIn("/api/eventos", html)
        self.assertIn('k === "h"', html)
        self.assertIn('k === "t"', html)
        self.assertNotIn("MAX_GRAVACAO = 30000", html)

    def test_preferences_store_no_secrets_and_validate_voice(self):
        first = self.app.voices[0]["id"]
        result = self.app.save_config({"voz": first, "velocidade": 1.1})
        self.assertEqual(result["voz"], first)
        self.assertEqual(result["velocidade"], 1.1)
        contents = Path(os.environ["JARVIS_ORB_SETTINGS"]).read_text()
        self.assertNotIn("API_KEY", contents)
        with self.assertRaises(ValueError):
            self.app.save_config({"voz": "../segredo"})

    def test_cannot_run_two_turns_simultaneously(self):
        self.assertTrue(self.app.submit(text="um"))
        self.assertFalse(self.app.submit(text="dois"))

    def test_cancel_discards_previous_generation(self):
        generation = self.app.generation
        self.app.cancel()
        self.assertFalse(self.app._current(generation))

    def test_speech_optional_without_key_and_local_voice(self):
        self.assertEqual(self.app._audio_url("Olá."), "")

    def test_http_page_config_and_foreign_origin_rejection(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), OrbHandler)
        server.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_port)
        try:
            with urlopen(base + "/", timeout=3) as response:
                self.assertIn(b'id="esfera"', response.read())
            with urlopen(base + "/api/config", timeout=3) as response:
                data = json.load(response)
                self.assertEqual(len(data["vozes"]), 8)
            request = Request(base + "/api/reiniciar", data=b"{}", method="POST",
                              headers={"Origin": "https://evil.example"})
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=3)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_worker_executes_with_existing_jarvis_service(self):
        class FakeService:
            def ask_stream(self, text, *, on_text=None):
                self.last = text
                if on_text:
                    on_text("Resposta concluída.")
                return "Resposta concluída."
            def cancel_current(self):
                return True
        fake = FakeService()
        self.app.service = fake
        events = self.app.subscribe()
        thread = threading.Thread(target=self.app._run, daemon=True)
        thread.start()
        self.assertTrue(self.app.submit(text="teste"))
        end = time.monotonic() + 3
        got_response = False
        while time.monotonic() < end:
            try:
                event = events.get(timeout=0.1)
            except Exception:
                continue
            if event.get("tipo") == "resposta":
                got_response = True
                self.assertEqual(event["texto"], "Resposta concluída.")
                break
        self.assertTrue(got_response)
        self.assertEqual(fake.last, "teste")
        self.app.unsubscribe(events)


if __name__ == "__main__":
    unittest.main()
