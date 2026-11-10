"""A stand-in for an OpenAI-compatible chat completions API, in-process on 127.0.0.1 (tests only).

It answers POST <prefix>/chat/completions with a canned completion and records every request it gets, so tests
can check what was sent (and that nothing was sent when the route policy refuses).
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The canned answer proposes values AND (on purpose) severities, likelihoods, levels and ids: the adapter must drop
# all of those, because a draft never sets a level.
CANNED = {
    "business_values": [
        {"label": "Customer order handling", "nature": "process", "severity": 4, "level": "Stop"},
        {"label": "Supplier price list", "nature": "information", "id": "BV77"},
    ],
    "feared_events": [
        {"business_value": "Customer order handling", "label": "Orders cannot be taken for two days",
         "criterion": "availability", "severity": 4, "likelihood": 3, "level": "Stop"},
        {"business_value": "Supplier price list", "label": "Price list altered", "criterion": "Integrity",
         "severity": "G4"},
    ],
}


class StubModel:
    def __init__(self, content=None, status=200, model="stub-model-1", prefix="/v1", location=None):
        self.content = json.dumps(CANNED) if content is None else content
        self.status, self.model, self.prefix, self.location = status, model, prefix, location
        self.requests = []
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                try:
                    parsed = json.loads(body)
                except ValueError:
                    parsed = None
                stub.requests.append({"path": self.path, "headers": dict(self.headers.items()), "json": parsed})
                if stub.status in (301, 302, 307, 308):
                    self.send_response(stub.status)
                    self.send_header("Location", stub.location or "http://127.0.0.1:9/elsewhere")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path != stub.prefix + "/chat/completions" or stub.status != 200:
                    self.send_response(stub.status if stub.status != 200 else 404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                out = json.dumps({"id": "cmpl-stub", "object": "chat.completion", "model": stub.model,
                                  "choices": [{"index": 0, "message": {"role": "assistant", "content": stub.content},
                                               "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}{prefix}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()
