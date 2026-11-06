import os
import socket
import subprocess
import sys
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.local_server import OllamaSession


class LocalServerTests(TestCase):
    def test_external_server_is_reused_and_never_signaled(self):
        server = OllamaSession()
        with patch('jarvis.local_server._version', return_value='1.2.3'), \
                patch('subprocess.Popen') as spawn, patch('os.killpg') as kill:
            result = server.start('http://127.0.0.1:11434')
            self.assertFalse(result['managed'])
            self.assertFalse(server.close())
        spawn.assert_not_called()
        kill.assert_not_called()

    def test_owned_server_reuse_environment_and_group_cleanup(self):
        server = OllamaSession()
        child = Mock(pid=998)
        child.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'JARVIS_OLLAMA_DIR': directory, 'FCC_TOKEN': 'secret', 'https_proxy': 'http://private'}), \
                patch('jarvis.local_server._version', side_effect=['', '1.2.3', '1.2.3']), \
                patch('jarvis.ollama_setup.binary', return_value='/fixture/ollama'), \
                patch('jarvis.project_services.owns_health_port', return_value=True), \
                patch('subprocess.Popen', return_value=child) as spawn, patch('os.killpg') as kill:
            self.assertFalse(server.start('http://127.0.0.1:11434')['reused'])
            self.assertTrue(server.start('http://127.0.0.1:11434')['reused'])
            self.assertTrue(server.close())
            self.assertFalse(server.close())
            env = spawn.call_args.kwargs['env']
            self.assertEqual(env['OLLAMA_NO_CLOUD'], '1')
            self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '-1')
            self.assertEqual(env['OLLAMA_MAX_LOADED_MODELS'], '1')
            self.assertNotIn('FCC_TOKEN', env)
            self.assertNotIn('https_proxy', env)
            self.assertEqual(kill.call_count, 2)
        spawn.assert_called_once()
        child.wait.assert_called()

    def test_cancel_during_readiness_cleans_owned_process_and_allows_retry(self):
        server, token = OllamaSession(), CancellationToken()
        child = Mock(pid=998)
        child.poll.return_value = None
        def not_ready(*args):
            token.cancel()
            return False
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JARVIS_OLLAMA_DIR': directory}), \
                patch('jarvis.local_server._version', return_value=''), \
                patch('jarvis.ollama_setup.binary', return_value='/fixture/ollama'), \
                patch('jarvis.project_services.owns_health_port', side_effect=not_ready), \
                patch('subprocess.Popen', return_value=child), patch('os.killpg') as kill:
            with self.assertRaises(CancelledError): server.start('http://127.0.0.1:11434', token=token)
            self.assertEqual(kill.call_count, 2)
            self.assertFalse(server.close())
        with patch('jarvis.local_server._version', return_value='1.2.3'):
            self.assertTrue(server.start('http://127.0.0.1:11434')['reused'])

    def test_bad_host_and_already_cancelled_request_do_not_connect_or_spawn(self):
        token = CancellationToken()
        token.cancel()
        with patch('jarvis.local_server._version') as connect, patch('subprocess.Popen') as spawn:
            with self.assertRaises(ValueError): OllamaSession().start('http://example.com:80')
            with self.assertRaises(CancelledError): OllamaSession().start('http://127.0.0.1:11434', token=token)
        connect.assert_not_called()
        spawn.assert_not_called()

    def test_real_controlled_http_process_has_owned_port_and_is_reaped(self):
        if sys.platform != 'linux': self.skipTest('Linux process identity')
        from jarvis.project_services import identity
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        script = '''from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'{"version":"controlled"}')
 def log_message(self,*args): pass
HTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
'''.replace('PORT', str(port))
        real_popen = subprocess.Popen
        children = []
        def spawn(command, **kwargs):
            child = real_popen([sys.executable, '-I', '-c', script], **kwargs)
            children.append(child)
            return child
        session = OllamaSession()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JARVIS_OLLAMA_DIR': directory}), \
                patch('jarvis.ollama_setup.binary', return_value=sys.executable), \
                patch('jarvis.local_server.subprocess.Popen', side_effect=spawn):
            try:
                result = session.start(f'http://127.0.0.1:{port}')
                self.assertTrue(result['managed'])
                self.assertEqual(result['version'], 'controlled')
                self.assertIsNotNone(identity(children[0].pid))
            finally:
                session.close()
            self.assertIsNone(identity(children[0].pid))
            self.assertIsNotNone(children[0].poll())
