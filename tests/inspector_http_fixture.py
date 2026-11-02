"""Loopback-only fake Tagger. Not an AI inference test."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread


# {
#   責務: [TaggerFixture: local HTTP tagger server that records requests and returns configured responses]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     requests: captured HTTP requests for assertions,
#     code: HTTP response body written by the handler,
#     payload: HTTP request/response payload captured by the fixture,
#     models: model records returned by the local service fixture,
#     redirect: redirect fixture state used by the test cases,
#     server: local HTTP server fixture,
#     thread: worker thread owned by the fixture,
#     url: url fixture state used by the test cases,
#   ],
#   引数: []
# }
class TaggerFixture:
    # {
    #   責務: [__init__: initializes the fields and controlled behavior of TaggerFixture]
    #   処理: [1: initialize deterministic request/response fields, 2: bind and start the loopback server thread]
    #   引数: []
    #   戻り値: [None: initialize instance state without returning a value]
    #   副作用: [test専用のloopback HTTP fixture serverを起動・停止する]
    # }
    def __init__(self):
        self.requests = []
        self.code = 200
        self.payload = {
            "general": {"landscape": 0.95, "sky": 0.7, "low_score": 0.1},
            "character": {"fixture_character": 0.9},
            "rating": {"safe": 0.9, "questionable": 0.1},
            "caption": "fixture caption",
            "style": {"must_not_be_content": 0.99},
        }
        self.models = {"models": ["fixture-model"]}
        self.redirect = None
        fixture = self

        # {
        #   責務: [Handler: local HTTP request handler that records requests and emits JSON fixture responses]
        #   処理: [1: provide the configured fields and methods used by the surrounding cases]
        #   フィールド: []
        #   引数: []
        # }
        class Handler(BaseHTTPRequestHandler):
            # {
            #   責務: [log_message: suppresses default request logging from the local fixture server]
            #   処理: [1: suppress the HTTP server's default request log output]
            #   引数: [*args: positional HTTP handler arguments forwarded to the base class (unspecified)]
            #   戻り値: [None: test helper returns no value]
            # }
            def log_message(self, *args):
                pass

            # {
            #   責務: [do_GET: records a local fixture GET request and returns its response]
            #   処理: [1: record the request method and path, 2: send the configured model-list response]
            #   引数: []
            #   戻り値: [None: test helper returns no value]
            # }
            def do_GET(self):
                fixture.requests.append(("GET", self.path, None))
                self.respond(fixture.models)

            # {
            #   責務: [do_POST: records a local fixture POST request and returns its response]
            #   処理: [
            #     1: read and decode the posted JSON body,
            #     2: record the request and send the configured response payload,
            #   ],
            #   引数: []
            #   戻り値: [None: test helper returns no value]
            # }
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.requests.append(("POST", self.path, data))
                self.respond(fixture.payload)

            # {
            #   責務: [respond: serializes the fixture payload and writes an HTTP response]
            #   処理: [1: encode the payload as JSON, 2: write status and content headers followed by the response body]
            #   引数: [payload: JSON request/response payload (unspecified)]
            #   戻り値: [None: test helper returns no value]
            # }
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

    # {
    #   責務: [close: stops the loopback server, closes its socket, and joins its serving thread]
    #   処理: [1: stop owned workers/servers and release temporary files or UI resources]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
