"""Test helpers: an in-process client that calls App.handle() directly, keeping cookies like a browser."""
import json
import pathlib
import re
import shutil
import sys
import tempfile
import urllib.parse

APP_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO = APP_DIR.parent
ENGINE = REPO / "engine"
EXAMPLE = REPO / "examples" / "anssi-guide-vaccine-example.json"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from atelier_app.app import App  # noqa: E402
from atelier_app.web import Request  # noqa: E402

HOST = "127.0.0.1:8770"
CSRF_RE = re.compile(r'name="csrf" value="([^"]+)"')
PRE_RE = re.compile(r'name="pre" value="([^"]+)"')
SID_RE = re.compile(r"/s/(s-[0-9]{8}-[0-9a-f]{8})")


def make_app(**kw):
    """An app on a fresh temp data dir. The private dir is always a temp one too (never the user's real one, even
    when ATELIER_PRIVATE_DIR is set in the environment), and drafting is off unless the test passes settings."""
    d = tempfile.mkdtemp(prefix="atelier-test-")
    kw.setdefault("private_dir", pathlib.Path(d) / "private")
    kw.setdefault("drafting_settings", {"backend": "off"})
    return App(d, port=8770, **kw), d


def cleanup(d):
    shutil.rmtree(d, ignore_errors=True)


def multipart(fields, files):
    b = "----atelierTestBoundary7d1"
    out = []
    for k, v in fields.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (fn, data) in files.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                   f'Content-Type: application/json\r\n\r\n'.encode() + data + b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"


class Client:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def req(self, method, path, form=None, body=b"", ctype=None, host=HOST, headers=None):
        h = {"Host": host} if host is not None else {}
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if form is not None:
            body = urllib.parse.urlencode(form, doseq=True).encode()
            ctype = "application/x-www-form-urlencoded"
        if ctype:
            h["Content-Type"] = ctype
        h.update(headers or {})
        resp = self.app.handle(Request(method, path, h, body))
        for sc in resp.all("Set-Cookie"):
            kv = sc.split(";")[0]
            k, _, v = kv.partition("=")
            if "Max-Age=0" in sc or not v:
                self.cookies.pop(k, None)
            else:
                self.cookies[k] = v
        return resp

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, form=None, **kw):
        return self.req("POST", path, form=form, **kw)

    def text(self, resp):
        return resp.body.decode("utf-8")

    def login(self):
        pre = PRE_RE.search(self.text(self.get("/login"))).group(1)
        r = self.post("/login", {"pre": pre, "token": self.app.auth.token})
        assert r.status == 303, r.status
        return r

    def csrf(self, path="/"):
        return CSRF_RE.search(self.text(self.get(path))).group(1)

    def post_csrf(self, path, form=None, page="/"):
        form = dict(form or {})
        form["csrf"] = self.csrf(page)
        return self.post(path, form)

    def load_example(self):
        r = self.post_csrf("/example")
        assert r.status == 303, r.status
        return SID_RE.search(r.get("Location")).group(1)

    def import_bytes(self, data, filename="study.json"):
        body, ctype = multipart({"csrf": self.csrf()}, {"file": (filename, data)})
        return self.req("POST", "/import", body=body, ctype=ctype)


def example_json():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


try:
    import openpyxl  # noqa: F401
    HAVE_OPENPYXL = True
except ImportError:
    HAVE_OPENPYXL = False

# An invented private calibration: 4 risk levels, invented labels. It stands in for an organisation's own
# calibration, which never enters the repository. Grid never decreasing along either axis, as the engine requires.
SYNTH_ID = "synthetic-4level"
SYNTH_LEVELS = [("Calm", "7FB77E"), ("Watch", "F2D06B"), ("Alert", "F28C38"), ("Stop", "8E1B10")]
SYNTH_CAL = {
    "id": SYNTH_ID,
    "name": "Synthetic test calibration (invented, 4 levels)",
    "source": "invented for the app tests",
    "severity": [{"n": 1, "code": "S1", "label": "Slight"}, {"n": 2, "code": "S2", "label": "Notable"},
                 {"n": 3, "code": "S3", "label": "Heavy"}, {"n": 4, "code": "S4", "label": "Extreme"}],
    "likelihood": [{"n": 1, "code": "L1", "label": "Remote"}, {"n": 2, "code": "L2", "label": "Possible"},
                   {"n": 3, "code": "L3", "label": "Likely"}, {"n": 4, "code": "L4", "label": "Expected"}],
    "levels": [{"name": n, "rank": i + 1, "colour": c, "acceptability": f"{n} (invented acceptance class)",
                "action": "invented"} for i, (n, c) in enumerate(SYNTH_LEVELS)],
    "grid_by_severity": {
        "4": ["Watch", "Alert", "Stop", "Stop"],
        "3": ["Watch", "Watch", "Alert", "Stop"],
        "2": ["Calm", "Watch", "Watch", "Alert"],
        "1": ["Calm", "Calm", "Watch", "Watch"],
    },
}


def make_private_dir(extra=None):
    """A temp private directory holding the synthetic calibration (and `extra` {filename: text})."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="atelier-private-"))
    d.chmod(0o700)
    (d / f"{SYNTH_ID}.json").write_text(json.dumps(SYNTH_CAL, indent=1), encoding="utf-8")
    for name, text in (extra or {}).items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def small_study(cal_id, name="Small study"):
    """A complete little study (W1-W5) on any calibration: one risk at severity 4, likelihood 3, target 1."""
    return {
        "format": "atelier-study", "version": "0.1",
        "study": {"name": name, "scope": "invented", "calibration": cal_id},
        "business_values": [{"id": "BV1", "label": "Order handling", "nature": "process"}],
        "supporting_assets": [{"id": "SA1", "label": "Order server", "business_values": ["BV1"]}],
        "feared_events": [{"id": "FE1", "business_value": "BV1", "label": "Orders stopped", "criterion": "availability",
                           "severity": 4}],
        "baseline": [],
        "risk_origins": [{"id": "RO1", "origin": "Organised crime", "objective": "Ransom", "motivation": 3,
                          "resources": 3, "decision": "selected", "feared_events": ["FE1"]}],
        "stakeholders": [],
        "strategic_scenarios": [{"id": "SS1", "risk_origin": "RO1", "feared_events": ["FE1"], "severity": 4,
                                 "paths": [{"id": "SS1-P1", "label": "Direct intrusion"}]}],
        "operational_scenarios": [],
        "risks": [{"id": "R1", "strategic_scenario": "SS1", "label": "Orders stopped by ransomware", "severity": 4,
                   "likelihood": 3, "likelihood_target": 1, "treatment": "reduce"}],
        "measures": [{"id": "M1", "label": "Offline backups", "risks": ["R1"], "owner": "IT", "due": "2027-06-30",
                      "status": "planned"}],
    }
