import io
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.fcc import FCCClient, FCCError, AutoModelClient
from jarvis.conversation import ConversationController, TextMailbox
from jarvis.latency import TurnTrace, summary


def frame(kind, **data):
    return ('data: ' + json.dumps({'type': kind, **data}, ensure_ascii=False) + '\n\n').encode()


class StreamingTests(unittest.TestCase):
    def serve(self, behavior):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                try:
                    behavior(self)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return FCCClient(f'http://127.0.0.1:{server.server_port}')

    def test_terminal_returns_without_eof_and_delta_arrives_first(self):
        hold = threading.Event()
        self.addCleanup(hold.set)
        def behavior(handler):
            handler.wfile.write(frame('response.output_text.delta', delta='Olá.'))
            handler.wfile.write(frame('response.completed', response={'output': []}))
            handler.wfile.flush()
            hold.wait(2)
        client = self.serve(behavior)
        seen = []
        start = time.monotonic()
        result = client.stream_responses({}, on_event=seen.append)
        self.assertLess(time.monotonic() - start, .5)
        self.assertEqual(result, {'output': []})
        self.assertEqual(seen, [{'type': 'response.output_text.delta', 'delta': 'Olá.'}])

    def test_stop_interrupts_blocked_read(self):
        ready, hold = threading.Event(), threading.Event()
        self.addCleanup(hold.set)
        def behavior(handler):
            handler.wfile.write(b': ready\n\n')
            handler.wfile.flush()
            ready.set()
            hold.wait(2)
        client, token, errors = self.serve(behavior), CancellationToken(), []
        def run():
            try: client.stream_responses({}, cancel_token=token)
            except Exception as exc: errors.append(exc)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        self.assertTrue(ready.wait(1))
        start = time.monotonic()
        token.cancel()
        worker.join(.5)
        self.assertFalse(worker.is_alive())
        self.assertLess(time.monotonic() - start, .5)
        self.assertIsInstance(errors[0], CancelledError)

    def test_deadline_interrupts_stream_with_no_terminal(self):
        hold = threading.Event()
        self.addCleanup(hold.set)
        def behavior(handler):
            handler.wfile.write(b': heartbeat\n\n')
            handler.wfile.flush()
            hold.wait(2)
        client = self.serve(behavior)
        start = time.monotonic()
        with self.assertRaises(FCCError) as error:
            client.stream_responses({}, deadline=start + .15)
        self.assertEqual(error.exception.category, 'deadline')
        self.assertLess(time.monotonic() - start, .5)

    def test_sse_multiline_utf8_and_private_events(self):
        payload = (b'event: response.output_text.delta\r\n'
                   b'data: {"delta":\r\ndata: "Ol\xc3\xa1"}\r\n\r\n'
                   + frame('response.reasoning_text.delta', delta='segredo')
                   + frame('response.function_call_arguments.delta', delta='{"x":')
                   + frame('response.completed', response={'output': []}))
        response = io.BytesIO(payload)
        seen = []
        with patch('jarvis.fcc.urlopen', return_value=response):
            FCCClient('http://localhost').stream_responses({}, on_event=seen.append)
        self.assertEqual([item['delta'] for item in seen], ['Olá'])

    def test_invalid_or_incomplete_stream_is_never_a_result(self):
        for data in (frame('response.output_text.delta', delta='partial'),
                     frame('response.completed', response={'output': None}),
                     b'data: not-json\n\n'):
            with self.subTest(data=data), patch('jarvis.fcc.urlopen', return_value=io.BytesIO(data)):
                with self.assertRaises(FCCError):
                    FCCClient('http://localhost').responses({})

    def test_fallback_after_visible_delta_is_forbidden(self):
        class Backend:
            timeout = 1
            def models(self): return {'data': [{'id': 'one'}, {'id': 'two'}]}
            def stream_responses(self, payload, *, on_event, **_):
                self.calls += 1
                on_event({'type': 'response.output_text.delta', 'delta': 'partial'})
                raise FCCError('network')
        backend = Backend()
        backend.calls = 0
        client = AutoModelClient(backend)
        with self.assertRaises(FCCError):
            client.stream_responses({}, on_event=lambda _: None)
        self.assertEqual(backend.calls, 1)

    def test_mailbox_bounds_queue_and_keeps_text(self):
        events = []
        box = TextMailbox(events.append)
        for _ in range(10000): box.publish('a')
        self.assertEqual(events, [box])
        self.assertEqual(box.take(), 'a' * 10000)
        box.publish('b')
        self.assertEqual(len(events), 2)

    def test_controller_streams_before_final_and_traces_without_content(self):
        order = []
        class Service:
            def ask_stream(self, message, *, on_text):
                on_text('Olá.')
                order.append('provider_final')
                return 'Olá.'
        controller = ConversationController(Service())
        controller.run('private user text', on_text=lambda _: order.append('delta'),
                       display=lambda _: order.append('display'))
        self.assertEqual(order, ['delta', 'provider_final', 'display'])
        self.assertNotIn('private', str(controller.last_trace.snapshot()))
        self.assertEqual(summary([3, 1, 2])['p95'], 3)
