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


# Answers per workshop, each wrapped the way real models often wrap JSON (fences, prose, a thinking block), and
# each carrying (on purpose) the fields a draft must never set: severity, likelihood, decision, status, owner, due,
# ratings. The adapter must drop them all.
CANNED_WS = {
    "w1": json.dumps(CANNED),
    "w2": "Here are the pairs I found:\n```json\n" + json.dumps({"risk_origins": [
        {"origin": "Organised crime group", "objective": "Extort a ransom by stopping vaccine production",
         "feared_events": ["FE1", "not-an-id"], "decision": "selected", "motivation": 4, "resources": 3,
         "severity": 4},
        {"origin": "Disgruntled former employee", "objective": "Leak research results to the press",
         "decision": "discarded"}]}) + "\n```\nHope it helps.",
    "w3": "<think>The user wants stakeholders. {not json}</think>\n" + json.dumps({
        "stakeholders": [{"name": "Hosting provider", "category": "service provider", "dependence": 4, "trust": 1,
                          "critical": True},
                         {"name": "Courier <b>company</b>", "category": "partner", "maturity": 2}],
        "strategic_scenarios": [{"risk_origin": "RO1", "feared_events": ["FE1"], "severity": 1, "likelihood": 4,
                                 "paths": [{"label": "Through the hosting provider", "stakeholder": "Hosting provider"},
                                           {"label": "Direct phishing of a lab employee"}]},
                                {"risk_origin": "RO2", "feared_events": ["FE2"],
                                 "paths": [{"label": "Sabotage through a maintenance contractor"}]}]}),
    "w4": "Sure! The operational scenario is: " + json.dumps({"operational_scenarios": [
        {"strategic_scenario": "SS1", "path": "SS1-P1", "likelihood": 4, "severity": 4,
         "description": "Phishing mail, theft of a remote access account, encryption of the production servers."},
        {"strategic_scenario": "SS2", "path": "SS2-P1", "likelihood": 3,
         "description": "Rogue update pushed through the supplier's portal, then altered labelling settings."}]})
        + " Let me know.",
    "w5": json.dumps({"measures": [
        {"label": "Offline backups of the production servers", "risks": ["R1"], "status": "done",
         "owner": "Somebody", "due": "2027-01-01", "treatment": "reduce"},
        {"label": "Multi-factor authentication for remote access", "risks": ["R1", "R99"]}]}),
}


def workshop_of(body):
    """The workshop a request is for, from the first line of its system prompt ("# Workshop N draft ...")."""
    try:
        first = body["messages"][0]["content"].split("\n", 1)[0]
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    for n in "12345":
        if first.startswith(f"# Workshop {n} draft"):
            return "w" + n
    return None


class StubModel:
    def __init__(self, content=None, status=200, model="stub-model-1", prefix="/v1", location=None, by_workshop=False,
                 usage=None):
        self.content = json.dumps(CANNED) if content is None else content
        self.by_workshop, self.usage = by_workshop, usage
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
                content = stub.content
                if stub.by_workshop:
                    content = CANNED_WS.get(workshop_of(parsed) or "", "no workshop found in the system prompt")
                ans = {"id": "cmpl-stub", "object": "chat.completion", "model": stub.model,
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                    "finish_reason": "stop"}]}
                if stub.usage:
                    ans["usage"] = stub.usage
                out = json.dumps(ans).encode()
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
