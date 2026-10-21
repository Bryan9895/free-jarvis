"""FCC simulated API tests: catalog view, request auth and automated failover."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from jarvis.fcc import FCCClient, FCCError, AutoModelClient

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
    def test_responses_view_not_claude_aliases(self):
        c=FCCClient("http://127.0.0.1:8082", token="fake")
        with patch("jarvis.fcc.urlopen", return_value=HTTPResponse({"data":[{"id":"first"}]})) as mock:
            self.assertEqual(c.models()["data"][0]["id"], "first")
        req = mock.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/v1/models?view=responses"))
        self.assertEqual(req.get_header("Authorization"), "Bearer fake")

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
