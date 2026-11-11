"""Small HTTP layer: request and response objects, a regex router, form parsing."""
import re
import urllib.parse
from http.cookies import SimpleCookie


class HTTPError(Exception):
    def __init__(self, status, message=""):
        super().__init__(message)
        self.status = status
        self.message = message


class Request:
    def __init__(self, method, target, headers=None, body=b""):
        self.method = method.upper()
        parts = urllib.parse.urlsplit(target)
        self.path = parts.path or "/"
        self.query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.body = body
        self.cookies = {}
        raw = self.headers.get("cookie")
        if raw:
            c = SimpleCookie()
            try:
                c.load(raw)
            except Exception:  # a malformed cookie header is treated as no cookie
                c = {}
            self.cookies = {k: m.value for k, m in c.items()}
        self.form = {}
        self.session = None

    def arg(self, name, default=""):
        v = self.query.get(name)
        return v[0] if v else default

    def field(self, name, default=""):
        v = self.form.get(name)
        return v[0] if v else default

    def fields(self, name):
        return list(self.form.get(name) or [])

    def parse_body(self):
        ctype = self.headers.get("content-type", "")
        main = ctype.split(";")[0].strip().lower()
        if not self.body:
            return
        if main == "application/x-www-form-urlencoded":
            try:
                text = self.body.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPError(400, "form is not UTF-8")
            self.form = urllib.parse.parse_qs(text, keep_blank_values=True)
        else:
            raise HTTPError(415, "unsupported content type")


class Response:
    def __init__(self, body=b"", status=200, ctype="text/html; charset=utf-8", headers=None):
        self.status = status
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.headers = [("Content-Type", ctype)] + list(headers or [])

    def header(self, name, value):
        self.headers.append((name, value))
        return self

    def get(self, name):
        for k, v in self.headers:
            if k.lower() == name.lower():
                return v
        return None

    def all(self, name):
        return [v for k, v in self.headers if k.lower() == name.lower()]


def redirect(location, status=303):
    return Response(b"", status, "text/plain; charset=utf-8", [("Location", location)])


class Router:
    """Routes are (method, regex) pairs matched against the raw (still percent-encoded) path.

    Captured groups are percent-decoded before they reach the handler, so a pattern such as [a-z0-9-]+
    can never match an encoded slash or dot sequence.
    """

    def __init__(self):
        self.routes = []

    def add(self, method, pattern, fn, public=False):
        self.routes.append((method.upper(), re.compile(pattern), fn, public))

    def match(self, method, path):
        """Return (fn, args, public) or raise HTTPError 404 / 405."""
        allowed = set()
        for m, rx, fn, public in self.routes:
            g = rx.fullmatch(path)
            if not g:
                continue
            if m != method and not (method == "HEAD" and m == "GET"):
                allowed.add(m)
                continue
            return fn, [urllib.parse.unquote(x) for x in g.groups()], public
        if allowed:
            raise HTTPError(405, "method not allowed")
        raise HTTPError(404, "not found")
