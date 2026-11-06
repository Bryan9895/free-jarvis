from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
from jarvis_fixture_dep import VALUE


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == '/health' and VALUE == 17 else 404)
        self.end_headers()
        self.wfile.write(f'fixture:{VALUE}'.encode())

    def log_message(self, *args):
        pass


HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
