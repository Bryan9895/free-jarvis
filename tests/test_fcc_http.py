"""Testa socket HTTP real usando uma simulação local do FCC, sem credenciais."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from jarvis.fcc import FCCClient, AutoModelClient

class Handler(BaseHTTPRequestHandler):
    calls = []
    def log_message(self, *_): pass
    def reply(self, status, item):
        data = json.dumps(item).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"status":"healthy"})
        if self.path == "/v1/models?view=responses":
            return self.reply(200, {"object":"list", "default_model_id":"primary",
                                    "data":[{"id":"primary"},{"id":"backup"}]})
        self.reply(404, {"error":"unknown"})

    def do_POST(self):
        if self.path != "/v1/responses":
            return self.reply(404, {"error":"unknown"})
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        type(self).calls.append({"model":payload["model"], "stream":payload.get("stream"), "authorization":self.headers.get("Authorization")})
        if payload["model"] == "primary":
            return self.reply(503, {"error":"temporarily unavailable"})
        data = {"type":"response.completed","response":{"output":[{"type":"message","content":[{"type":"output_text","text":"OK"}]}]}}
        output = ("event: response.created\\ndata: " + json.dumps({"type":"response.created","response":{"output":[]}}) + "\\n\\n"
                  + "event: response.completed\\ndata: " + json.dumps(data) + "\\n\\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(output)))
        self.end_headers()
        self.wfile.write(output)

class HTTPIntegrationTests(unittest.TestCase):
    def test_socket_catalog_and_automatic_switch(self):
        Handler.calls = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = FCCClient(f"http://127.0.0.1:{server.server_port}", "example-token")
            self.assertEqual(client.health()["status"],"healthy")
            auto = AutoModelClient(client)
            self.assertEqual(auto.diagnostic()["model"], "backup")
            self.assertEqual([entry["model"] for entry in Handler.calls], ["primary","backup"])
            self.assertTrue(all(entry["authorization"] == "Bearer example-token" for entry in Handler.calls))
            self.assertTrue(all(entry["stream"] is True for entry in Handler.calls))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

if __name__ == "__main__":
    unittest.main()
