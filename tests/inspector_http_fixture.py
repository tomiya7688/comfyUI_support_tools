"""Loopback-only fake Tagger. Not an AI inference test."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread


class TaggerFixture:
    def __init__(self):
        self.requests = []
        self.code = 200
        self.payload = {"tag": {"landscape": 0.95, "sky": 0.7, "low_score": 0.1}}
        self.models = {"models": ["fixture-model"]}
        self.redirect = None
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                fixture.requests.append(("GET", self.path, None))
                self.respond(fixture.models)
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.requests.append(("POST", self.path, data))
                self.respond(fixture.payload)
            def respond(self, payload):
                self.send_response(fixture.code)
                if fixture.redirect:
                    self.send_header("Location", fixture.redirect)
                self.send_header("Content-Type", "application/json")
                data = json.dumps(payload).encode()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/pixai/v1/interrogate"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
