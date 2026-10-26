"""Replay HTTP controlado; não mede microfone, FCC real ou som no fone.

PYTHONPATH=src .venv/bin/python tools/benchmark_transport.py --samples 30
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
from threading import Thread
from time import monotonic, sleep
from jarvis.fcc import FCCClient
from jarvis.latency import summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--baseline-ref', default='1702cd7')
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('samples deve ser positivo')
    source = subprocess.run(['git', 'show', args.baseline_ref + ':src/jarvis/fcc.py'],
                            check=True, capture_output=True, text=True).stdout
    baseline = {}
    exec(compile(source, '<baseline-fcc>', 'exec'), baseline)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            def send(value):
                try:
                    self.wfile.write(('data: ' + json.dumps(value) + '\n\n').encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError): pass
            sleep(.02)
            send({'type': 'response.output_text.delta', 'delta': 'Resposta controlada.'})
            sleep(.02)
            send({'type': 'response.completed', 'response': {'output': []}})
            sleep(.08)  # socket permanece aberto após o terminal
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    old, new, first = [], [], []
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        for index in range(args.samples):
            # Alternar a ordem para reduzir viés temporal.
            order = ('old', 'new') if index % 2 else ('new', 'old')
            for kind in order:
                start = monotonic()
                if kind == 'old':
                    baseline['FCCClient'](url).responses({})
                    old.append(monotonic() - start)
                else:
                    FCCClient(url).stream_responses({}, on_event=lambda _: first.append(monotonic() - start))
                    new.append(monotonic() - start)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
    print(json.dumps({'kind': 'controlled_http_replay', 'baseline_ref': args.baseline_ref,
        'samples_per_version': args.samples, 'server_delays_s': {'delta': .02, 'terminal': .04, 'eof': .12},
        'baseline_final_s': summary(old), 'current_final_s': summary(new),
        'current_first_delta_s': summary(first),
        'median_reduction_percent': round(100 * (1 - summary(new)['p50'] / summary(old)['p50']), 2),
        'physical_audio': 'pending', 'real_fcc': 'pending'}, indent=2))


if __name__ == '__main__': main()
