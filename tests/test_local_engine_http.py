"""Optional installed-engine integration against controlled HTTP, never real inference."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import tempfile
import unittest

from jarvis.config import Config
from jarvis.conversation import ConversationController
from jarvis.local_setup import managed_python
from jarvis.service import JarvisService


@unittest.skipUnless(managed_python(), 'Pinned local runtime not provisioned')
class InstalledEngineHTTPTests(unittest.TestCase):
    def test_installed_engine_stream_and_structured_tool_reach_shared_controller(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_):
                pass

            def reply(self, data):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()

            def do_GET(self):
                calls.append((self.path, None))
                self.reply(json.dumps({'models': [{'name': 'qwen3:1.7b'}]}).encode())

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, payload))
                if self.path == '/api/show':
                    self.reply(json.dumps({'capabilities': ['completion', 'tools']}).encode())
                    return
                if any(item['role'] == 'tool' for item in payload['messages']):
                    chunk = {'message': {'content': 'Arquivo criado e verificado.'}}
                else:
                    chunk = {'message': {'tool_calls': [{'id': 'engine-call-id', 'function': {
                        'name': 'write_file', 'arguments': {'path': 'proof.txt', 'content': 'local'}}}]}}
                terminal = {'done': True, 'eval_count': 5, 'prompt_eval_count': 10}
                self.reply(('\n'.join(json.dumps(item) for item in (chunk, terminal)) + '\n').encode())

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = Config('http://127.0.0.1:1', '', '', root, root / 'memory.db',
                    profile='local', local_model='qwen3:1.7b',
                    ollama_host=f'http://127.0.0.1:{server.server_port}', openjarvis_python=managed_python())
                service = JarvisService.from_config(config, report=lambda _: None)
                try:
                    answer = ConversationController(service).run('Crie o arquivo proof.txt com o conteúdo local.')
                    self.assertEqual((root / 'proof.txt').read_text(), 'local')
                    self.assertTrue(answer)
                    self.assertTrue(service.toolkit.offline)
                    tool_calls = [entry for entry in service.toolkit.operation_log if entry['tool'] == 'write_file']
                    self.assertEqual(len(tool_calls), 1)
                finally:
                    service.close()
            requests = [payload for path, payload in calls if path == '/api/chat']
            self.assertGreaterEqual(len(requests), 1)
            self.assertTrue(all(payload['model'] == 'qwen3:1.7b' for payload in requests))
            self.assertTrue(all(payload['think'] is False for payload in requests))
            if len(requests) > 1:
                replay = [item for item in requests[-1]['messages'] if item['role'] == 'tool']
                self.assertEqual(replay[-1]['tool_call_id'], 'engine-call-id')
            self.assertTrue(all(path in ('/api/tags', '/api/show', '/api/chat') for path, _ in calls))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
