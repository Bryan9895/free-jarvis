"""FCC simulated API tests: catalog view, request auth and automated failover."""
import io
import os
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from jarvis.fcc import FCCClient, FCCError, AutoModelClient, may_fallback
from jarvis.config import Config

class HTTPResponse:
    def __init__(self, payload):
        self.buf = io.BytesIO(json.dumps(payload).encode())
    def __enter__(self): return self.buf
    def __exit__(self, *_): return False

class FakeClient:
    def __init__(self, statuses=None):
        self.statuses = list(statuses or [])
        self.seen = []
    def models(self):
        return {"default_model_id":"first", "data":[{"id":"first"},{"id":"second"}]}
    def responses(self, payload):
        self.seen.append(payload["model"])
        if self.statuses:
            code = self.statuses.pop(0)
            if code:
                raise FCCError("test failure", code)
        return {"output":[{"type":"message","content":[{"type":"output_text","text":"OK"}]}]}

class FCCTests(unittest.TestCase):
    def test_documentation_placeholder_uses_default_model(self):
        with patch.dict(os.environ, {"FCC_MODEL": "ID_DO_MODELO"}):
            self.assertEqual(Config.from_env().model, "")
        with patch.dict(os.environ, {"FCC_MODEL": "my-real-model"}):
            self.assertEqual(Config.from_env().model, "my-real-model")

    def test_responses_view_not_claude_aliases(self):
        c=FCCClient("http://127.0.0.1:8082", token="fake")
        with patch("jarvis.fcc.urlopen", return_value=HTTPResponse({"data":[{"id":"first"}]})) as mock:
            self.assertEqual(c.models()["data"][0]["id"], "first")
        req = mock.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/v1/models?view=responses"))
        self.assertEqual(req.get_header("Authorization"), "Bearer fake")

    def test_explicit_local_model_stays_local(self):
        class MixedCatalog(FakeClient):
            def models(self):
                return {"default_model_id":"nvidia_nim/super", "data":[
                    {"id":"gemini/preview"},{"id":"ollama/qwen3.5:2b"},
                    {"id":"nvidia_nim/super"},{"id":"ollama/qwen3.5:4b"}]}
        model=AutoModelClient(MixedCatalog(), preferred="ollama/qwen3.5:2b")
        model.initialize()
        self.assertEqual(model.candidates, ["ollama/qwen3.5:2b"])

    def test_auto_uses_same_provider_but_not_others(self):
        class MixedCatalog(FakeClient):
            def models(self):
                return {"default_model_id":"ollama/a", "data":[
                    {"id":"gemini/preview"},{"id":"ollama/a"},{"id":"ollama/b"}]}
        model=AutoModelClient(MixedCatalog())
        model.initialize()
        self.assertEqual(model.candidates, ["ollama/a", "ollama/b"])
        opted=AutoModelClient(MixedCatalog(), preferred="ollama/a", backups=["gemini/preview"])
        opted.initialize()
        self.assertEqual(opted.candidates, ["ollama/a", "gemini/preview"])

    def test_explicit_local_timeout_no_cross_provider(self):
        class BrokenCatalog(FakeClient):
            def models(self):
                return {"default_model_id":"gemini/preview", "data":[
                    {"id":"gemini/preview"},{"id":"ollama/qwen3.5:2b"}]}
        backend=BrokenCatalog([None])
        def fail(payload):
            backend.seen.append(payload["model"])
            raise FCCError("timed out")
        backend.responses=fail
        model=AutoModelClient(backend, preferred="ollama/qwen3.5:2b")
        model.initialize()
        with self.assertRaises(FCCError):
            model.responses({"input":"hi"})
        self.assertEqual(backend.seen, ["ollama/qwen3.5:2b"])

    def test_diagnostic_reduces_reasoning_and_increases_budget(self):
        backend = FakeClient()
        auto = AutoModelClient(backend)
        auto.diagnostic()
        # FakeClient records only model IDs: add a capturing variant for payload.
        class Capture(FakeClient):
            def responses(self, payload):
                self.last_payload = payload
                return super().responses(payload)
        capture = Capture()
        AutoModelClient(capture).diagnostic()
        self.assertEqual(capture.last_payload["reasoning"], {"effort": "none"})
        self.assertGreaterEqual(capture.last_payload["max_output_tokens"], 512)
        self.assertTrue(capture.last_payload["stream"])

    def test_switch_to_any_listed_fcc_model(self):
        backend = FakeClient()
        auto = AutoModelClient(backend, preferred="first")
        auto.initialize()
        self.assertEqual(auto.available_models(), ["first", "second"])
        self.assertEqual(auto.select_model("second"), "second")
        self.assertEqual(auto.candidates, ["second"])
        auto.responses({"input":"teste"})
        self.assertEqual(backend.seen[-1], "second")

    def test_unknown_model_cannot_be_selected(self):
        auto = AutoModelClient(FakeClient())
        auto.initialize()
        with self.assertRaises(FCCError):
            auto.select_model("not-announced")
        self.assertEqual(auto.active_model, "first")

    def test_all_models_in_catalog_can_be_fallbacks(self):
        auto = AutoModelClient(FakeClient([503]))
        auto.initialize()
        self.assertEqual(auto.use_all_models(), ["first", "second"])
        auto.responses({"input":"teste"})
        self.assertEqual(auto.active_model, "second")

    def test_tool_calls_do_not_implicitly_switch_to_unverified_model(self):
        fake = FakeClient([503])
        client = AutoModelClient(fake)
        client.initialize()
        with self.assertRaises(FCCError):
            client.responses({"input": "lista de janelas", "tools": [{"name": "desktop_windows"}]})
        self.assertEqual(fake.seen, ["first"])

    def test_tool_calls_can_use_explicit_backup(self):
        fake = FakeClient([503, None])
        client = AutoModelClient(fake, backups=["second"])
        client.initialize()
        answer = client.responses({"input": "lista de janelas",
                                   "tools": [{"name": "desktop_windows"}]})
        self.assertTrue(answer["output"])
        self.assertEqual(fake.seen, ["first", "second"])

    def test_default_model_automatic(self):
        a=AutoModelClient(FakeClient())
        self.assertEqual(a.initialize(), "first")
        self.assertEqual(a.diagnostic()["status"], "ok")

    def test_transient_switches_model(self):
        fake = FakeClient([429])
        swaps=[]
        a=AutoModelClient(fake, on_switch=swaps.append)
        a.initialize()
        a.responses({"input":"hello"})
        self.assertEqual(fake.seen, ["first","second"])
        self.assertEqual(a.active_model, "second")
        self.assertEqual(swaps, ["second"])

    def test_upstream_nim_404_triggers_switch(self):
        class UpstreamFailureClient(FakeClient):
            def responses(self, payload):
                self.seen.append(payload["model"])
                if payload["model"] == "first":
                    raise FCCError(
                        'HTTP 404 em /v1/responses: Upstream provider NIM returned HTTP 404. '
                        'Category: upstream. Provider API request failed.', 404)
                return {"output":[{"type":"message","content":[{"type":"output_text","text":"OK"}]}]}
        backend = UpstreamFailureClient()
        client = AutoModelClient(backend)
        self.assertEqual(client.diagnostic()["model"], "second")
        self.assertEqual(backend.seen, ["first", "second"])

    def test_normal_404_not_switched(self):
        client = AutoModelClient(FakeClient([404]))
        client.initialize()
        with self.assertRaises(FCCError):
            client.responses({"input":"olá"})
        self.assertFalse(may_fallback(FCCError("404 não encontrado", 404)))

    def test_gemini_interactions_only_switches(self):
        class GeminiOnlyClient(FakeClient):
            def responses(self, payload):
                self.seen.append(payload["model"])
                if payload["model"] == "first":
                    raise FCCError(
                        'HTTP 400 em /v1/responses: Upstream provider GEMINI returned HTTP 400. '
                        'Category: invalid_request. This model only supports Interactions API.', 400)
                return {"output":[{"type":"message","content":[{"type":"output_text","text":"OK"}]}]}
        fake = GeminiOnlyClient()
        a = AutoModelClient(fake)
        self.assertEqual(a.diagnostic()["model"], "second")
        self.assertEqual(fake.seen, ["first", "second"])

    def test_generic_400_remains_failure(self):
        a = AutoModelClient(FakeClient([400]))
        a.initialize()
        with self.assertRaises(FCCError):
            a.responses({"input": "teste"})
        self.assertFalse(may_fallback(FCCError("invalid JSON arguments", 400)))

    def test_permanent_auth_failure_no_fallback(self):
        fake=FakeClient([401])
        a=AutoModelClient(fake)
        a.initialize()
        with self.assertRaises(FCCError):
            a.responses({"input":"hello"})
        self.assertEqual(fake.seen, ["first"])

    def test_reject_unknown_preferred_model(self):
        a=AutoModelClient(FakeClient(), preferred="not-here")
        with self.assertRaises(FCCError): a.initialize()

    def test_retry_exhaustion(self):
        a=AutoModelClient(FakeClient([503,503]))
        a.initialize()
        with self.assertRaises(FCCError): a.responses({"input":"hello"})

    def test_http_error_status(self):
        err=HTTPError("http://127.0.0.1:8082/v1/responses",429,"Too Many Requests",None,io.BytesIO(b"rate limit"))
        with patch("jarvis.fcc.urlopen", side_effect=err):
            with self.assertRaises(FCCError) as cm:
                FCCClient("http://127.0.0.1:8082").responses({"model":"x","input":"hi"})
        self.assertEqual(cm.exception.status,429)

if __name__ == "__main__":
    unittest.main()
