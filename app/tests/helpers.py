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
SID_RE_ANY = re.compile(r"s-[0-9]{8}-[0-9a-f]{8}")


def make_app(**kw):
    """An app on a fresh temp data dir."""
    d = tempfile.mkdtemp(prefix="atelier-test-")
    return App(d, port=8770, **kw), d


def cleanup(d):
    shutil.rmtree(d, ignore_errors=True)


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


def quick_study(client, name="Pilot"):
    """Start a quick-path study (screen 1 saved); returns its id."""
    form = {"name": name, "activity": "We run a shop.", "values": "Orders", "tools": ["office"], "downtime": "day",
            "sensitivity": "internal", "lang": "en"}
    r = client.post_csrf("/quick/new", form, page="/quick/new")
    assert r.status == 303, r.status
    return SID_RE_ANY.search(r.get("Location")).group(0)


def example_json():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def store_example(client):
    """Put the guide example in the study store as a file that was not made with the quick path (the public app
    has no way to import one); returns its id."""
    return client.app.store.create(example_json())


try:
    import openpyxl  # noqa: F401
    HAVE_OPENPYXL = True
except ImportError:
    HAVE_OPENPYXL = False
