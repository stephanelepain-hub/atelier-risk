import http.client
import os
import socket
import stat
import threading
import unittest

from app.tests import helpers
from app.tests.helpers import Client, make_app, quick_study
from atelier_app import server
from atelier_app.app import App


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)

    def tearDown(self):
        helpers.cleanup(self.dir)

    def test_no_cookie_redirects_to_login(self):
        for p in ("/", "/studies", "/quick/new", "/s/s-20261110-0123abcd/delete", "/s/s-20261110-0123abcd/export.json",
                  "/s/s-20261110-0123abcd/export.xlsx", "/quick/s-20261110-0123abcd/results", "/cal/anssi-v1.5.css"):
            r = self.c.get(p)
            self.assertEqual(r.status, 303, p)
            self.assertEqual(r.get("Location"), "/login", p)

    def test_no_cookie_post_refused(self):
        for p in ("/quick/new", "/logout", "/s/s-20261110-0123abcd/delete", "/login/link"):
            r = self.c.post(p, {"name": "x"})
            self.assertEqual(r.status, 403, p)
        self.assertEqual(os.listdir(self.app.store.dir), ["trash"])

    def test_forged_session_cookie_refused(self):
        self.c.cookies["atelier_session"] = "forged-value"
        r = self.c.get("/")
        self.assertEqual(r.status, 303)
        self.assertEqual(r.get("Location"), "/login")

    def test_wrong_token_refused(self):
        pre = helpers.PRE_RE.search(self.c.text(self.c.get("/login"))).group(1)
        r = self.c.post("/login", {"pre": pre, "token": "not-the-token"})
        self.assertEqual(r.status, 403)
        self.assertNotIn("atelier_session", self.c.cookies)
        self.assertIn("Wrong token", self.c.text(r))
        self.assertEqual(self.c.get("/").status, 303)

    def test_lockout_after_repeated_failures(self):
        for _ in range(10):
            pre = helpers.PRE_RE.search(self.c.text(self.c.get("/login"))).group(1)
            self.c.post("/login", {"pre": pre, "token": "bad"})
        pre = helpers.PRE_RE.search(self.c.text(self.c.get("/login"))).group(1)
        r = self.c.post("/login", {"pre": pre, "token": self.app.auth.token})
        self.assertEqual(r.status, 429)
        self.assertNotIn("atelier_session", self.c.cookies)

    def test_login_without_form_nonce_refused(self):
        r = self.c.post("/login", {"token": self.app.auth.token})
        self.assertEqual(r.status, 403)
        self.assertNotIn("atelier_session", self.c.cookies)

    def test_login_sets_strict_httponly_cookie(self):
        pre = helpers.PRE_RE.search(self.c.text(self.c.get("/login"))).group(1)
        r = self.c.post("/login", {"pre": pre, "token": self.app.auth.token})
        self.assertEqual(r.status, 303)
        sc = [h for h in r.all("Set-Cookie") if h.startswith("atelier_session=")][0]
        self.assertIn("HttpOnly", sc)
        self.assertIn("SameSite=Strict", sc)
        self.assertIn("Path=/", sc)
        self.assertEqual(self.c.get("/").status, 200)

    def test_one_time_link_works_once(self):
        n = self.app.auth.mint_once("/")
        r = self.c.get(f"/login/once?n={n}")
        self.assertEqual(r.status, 303)
        self.assertIn("atelier_session", self.c.cookies)
        other = Client(self.app)
        r2 = other.get(f"/login/once?n={n}")
        self.assertEqual(r2.status, 403)
        self.assertNotIn("atelier_session", other.cookies)

    def test_login_link_refuses_external_next(self):
        self.c.login()
        for bad in ("//evil.example/", "http://evil.example/", "/x?y=1"):
            r = self.c.post_csrf("/login/link", {"next": bad})
            self.assertEqual(r.status, 400, bad)

    def test_csrf_missing_or_wrong(self):
        self.c.login()
        r = self.c.post("/quick/new", {"name": "x"})
        self.assertEqual(r.status, 403)
        r = self.c.post("/quick/new", {"name": "x", "csrf": "wrong"})
        self.assertEqual(r.status, 403)
        self.assertEqual(sorted(os.listdir(self.app.store.dir)), ["trash"])
        r = self.c.post_csrf("/quick/new", {"name": "x"}, page="/quick/new")
        self.assertEqual(r.status, 303)

    def test_multipart_bodies_are_not_accepted(self):
        self.c.login()
        body = (b'--b\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n' + self.c.csrf("/quick/new").encode()
                + b'\r\n--b\r\nContent-Disposition: form-data; name="name"\r\n\r\nx\r\n--b--\r\n')
        r = self.c.req("POST", "/quick/new", body=body, ctype="multipart/form-data; boundary=b")
        self.assertEqual(r.status, 415)
        self.assertEqual(sorted(os.listdir(self.app.store.dir)), ["trash"])

    def test_logout(self):
        self.c.login()
        r = self.c.post_csrf("/logout")
        self.assertEqual(r.status, 303)
        self.assertEqual(self.c.get("/").status, 303)

    def test_bad_host_refused(self):
        self.c.login()
        for h in ("evil.example", "evil.example:8770", "127.0.0.1:9999", "127.0.0.1", "", "localhost.evil:8770"):
            r = self.c.get("/", host=h)
            self.assertEqual(r.status, 421, h)
        self.assertEqual(self.c.get("/", host=None).status, 421)
        self.assertEqual(self.c.get("/", host="localhost:8770").status, 200)
        self.assertEqual(self.c.get("/", host="127.0.0.1:8770").status, 200)

    def test_security_headers(self):
        for p in ("/login", "/static/app.css", "/nope"):
            r = self.c.get(p)
            csp = r.get("Content-Security-Policy")
            self.assertIn("script-src 'self'", csp)
            self.assertIn("default-src 'none'", csp)
            self.assertIn("frame-ancestors 'none'", csp)
            self.assertNotIn("unsafe", csp)
            self.assertEqual(r.get("X-Frame-Options"), "DENY")
            self.assertEqual(r.get("X-Content-Type-Options"), "nosniff")

    def test_no_inline_script_or_style(self):
        self.c.login()
        sid = quick_study(self.c)
        for p in ("/login", "/", "/studies", "/quick/new", f"/quick/{sid}/about", f"/quick/{sid}/risks",
                  f"/quick/{sid}/now", f"/quick/{sid}/results", f"/s/{sid}/delete"):
            t = self.c.text(self.c.get(p))
            self.assertNotRegex(t, r"<script(?![^>]*\bsrc=)", p)
            self.assertNotIn(" style=", t, p)
            self.assertNotIn("<style", t, p)
            self.assertNotRegex(t, r"\son[a-z]+=", p)

    def test_token_file_mode_and_reuse(self):
        mode = stat.S_IMODE(os.stat(self.app.token_path).st_mode)
        self.assertEqual(mode, 0o600)
        for d in (self.app.data_dir, self.app.store.dir, self.app.tmp_dir):
            self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700, d)
        again = App(self.dir, port=8770)
        self.assertEqual(again.auth.token, self.app.auth.token)
        self.assertFalse(again.token_created)
        self.assertGreaterEqual(len(self.app.auth.token), 40)


class TraversalTest(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)
        self.c.login()
        self.sid = quick_study(self.c)

    def tearDown(self):
        helpers.cleanup(self.dir)

    def test_traversal_refused(self):
        paths = [
            "/static/../atelier_app/auth.py", "/static/%2e%2e/serve.py", "/static/..%2fserve.py",
            "/static/", "/static", "/static/app.css/..", "/static/%2e%2e%2f%2e%2e%2fengine%2fatelier_engine%2fcli.py",
            "/s/../../etc/passwd", "/s/..%2f..%2fetc%2fpasswd", "/s/%2e%2e%2f%2e%2e%2fetc%2fpasswd/delete",
            "/s/s-20261110-0000000g", "/s/s-20261110-01234567", "/s/S-20261110-01234567",
            f"/s/{self.sid}/../token", f"/s/{self.sid}%2f..%2f..%2ftoken", f"/quick/{self.sid}/..%2f..%2ftoken",
            f"/quick/{self.sid}/about/../../token", "/quick/..%2f..%2ftoken",
            "/cal/..%2f..%2fetc%2fpasswd.css", "/cal/../token.css", "/token", "/studies/", "/tmp/",
        ]
        token = self.app.auth.token
        for p in paths:
            r = self.c.get(p)
            self.assertEqual(r.status, 404, p)
            self.assertNotIn(token.encode(), r.body, p)

    def test_store_refuses_bad_ids(self):
        from atelier_app.storage import NotFound
        for bad in ("../token", "..", "s-20261110-0123abcd/../../x", "/etc/passwd", "", None, "s-2026111-0123abcd"):
            with self.assertRaises(NotFound, msg=repr(bad)):
                self.app.store.load(bad)

    def test_static_whitelist(self):
        self.assertEqual(self.c.get("/static/app.css").status, 200)
        self.assertEqual(self.c.get("/static/app.js").status, 200)
        self.assertEqual(self.c.get("/static/other.js").status, 404)


class RequestCapTest(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app(max_upload=2000)
        self.c = Client(self.app)
        self.c.login()

    def tearDown(self):
        helpers.cleanup(self.dir)

    def test_body_over_cap_refused(self):
        r = self.c.post_csrf("/quick/new", {"name": "x", "activity": "y" * 5000}, page="/quick/new")
        self.assertEqual(r.status, 413)
        self.assertEqual(sorted(os.listdir(self.app.store.dir)), ["trash"])

    def test_default_cap_is_5_mb(self):
        from atelier_app.app import MAX_UPLOAD
        self.assertEqual(MAX_UPLOAD, 5 * 1024 * 1024)


class RealSocketTest(unittest.TestCase):
    """The same checks through a real HTTP server on an ephemeral loopback port."""

    def setUp(self):
        self.app, self.dir = make_app()
        self.srv = server.Server(("127.0.0.1", 0), server.Handler)
        self.srv.app = self.app
        self.port = self.srv.server_address[1]
        self.app.set_port(self.port)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        helpers.cleanup(self.dir)

    def raw(self, data):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(data)
        out = b""
        while True:
            b = s.recv(65536)
            if not b:
                break
            out += b
        s.close()
        return out

    def test_oversize_content_length_refused_without_reading(self):
        n = 6 * 1024 * 1024
        out = self.raw(f"POST /quick/new HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Length: {n}\r\n"
                       f"Content-Type: application/x-www-form-urlencoded\r\nConnection: close\r\n\r\n".encode())
        self.assertTrue(out.startswith(b"HTTP/1.0 413") or out.startswith(b"HTTP/1.1 413"), out[:40])

    def test_post_without_length_refused(self):
        out = self.raw(f"POST /quick/new HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nConnection: close\r\n\r\n".encode())
        self.assertIn(b" 411 ", out.split(b"\r\n")[0])

    def test_bad_host_over_http(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/", headers={"Host": "rebind.example"})
        self.assertEqual(c.getresponse().status, 421)
        c.close()
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/login")
        r = c.getresponse()
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("X-Frame-Options"), "DENY")
        c.close()

    def test_duplicate_host_refused(self):
        out = self.raw(f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nHost: evil.example\r\n"
                       f"Connection: close\r\n\r\n".encode())
        self.assertIn(b" 400 ", out.split(b"\r\n")[0])


class BindTest(unittest.TestCase):
    def test_loopback_detection(self):
        for h in ("127.0.0.1", "localhost", "::1", "127.0.0.2"):
            self.assertTrue(server.is_loopback(h), h)
        for h in ("0.0.0.0", "10.0.0.5", "::", "example.org", ""):
            self.assertFalse(server.is_loopback(h), h)

    def test_non_loopback_refused_without_flag(self):
        self.assertEqual(server.main(["--host", "0.0.0.0", "--port", "0"]), 2)
        self.assertEqual(server.main(["--host", "127.0.0.1", "--allowed-host", "x:1"]), 2)


if __name__ == "__main__":
    unittest.main()
