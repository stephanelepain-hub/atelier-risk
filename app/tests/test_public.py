"""Round 4: public mode. Anonymous private workspaces, the join screen and invite code, limits, clean-up, forget,
continuing from a saved file, the client address of the rate limit, and the wording of the new pages (EN and FR)."""
import hashlib
import html
import http.client
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from app.tests import helpers
from app.tests.helpers import Client as _Client, PRE_RE, SID_RE_ANY, make_app
from app.tests.test_tone import EN_NEGATIVE, FEAR, FR_NEGATIVE, words_read
from atelier_app import app as app_mod, server, views_public, workspaces
from atelier_app.web import Request

CODE = "bakers-2026"
SERVE = helpers.APP_DIR / "serve.py"
DAY = 86400


class Client(_Client):
    def text(self, resp):
        """The page text with HTML entities decoded (an apostrophe is written &#x27; in the page)."""
        return html.unescape(super().text(resp))


def make_public(code=CODE, **kw):
    d = tempfile.mkdtemp(prefix="atelier-public-test-")
    return app_mod.App(d, port=8770, public=True, invite_code=code, **kw), d


def join(client, code=CODE, **kw):
    """GET /join then POST it, like a person; returns the POST response."""
    page = client.text(client.get("/join", **kw))
    pre = PRE_RE.search(page).group(1)
    form = {"pre": pre}
    if code is not None:
        form["code"] = code
    return client.post("/join", form, **kw)


def new_study(client, name="Pilot"):
    form = {"name": name, "activity": "We run a shop.", "values": "Orders", "tools": ["office"], "downtime": "day",
            "sensitivity": "internal", "lang": "en"}
    return client.post_csrf("/quick/new", form, page="/quick/new")


def ws_folders(app):
    return sorted(p.name for p in (app.data_dir / "workspaces").iterdir())


class PublicBase(unittest.TestCase):
    code = CODE

    def setUp(self):
        self.app, self.dir = make_public(self.code)
        self.c = Client(self.app)

    def tearDown(self):
        helpers.cleanup(self.dir)

    def store_of(self, c):
        """The study store of the workspace a client's cookie names."""
        h = workspaces.hash_id(c.cookies[workspaces.COOKIE])
        return self.app.workspaces.store(h)

    def visitor(self):
        c = Client(self.app)
        r = join(c, self.code)
        self.assertEqual(r.status, 303)
        return c

    def joined(self):
        r = join(self.c, self.code)
        self.assertEqual(r.status, 303)
        return self.c


class LoginRoutesTest(PublicBase):
    def test_login_routes_answer_404_and_no_token_file_is_created(self):
        for method, path in (("GET", "/login"), ("POST", "/login"), ("GET", "/login/once"), ("POST", "/login/once"),
                             ("POST", "/login/link"), ("POST", "/logout")):
            self.assertEqual(self.c.req(method, path).status, 404, (method, path))
        self.assertFalse((self.app.data_dir / "token").exists())
        self.assertEqual(len([p for p in self.app.data_dir.rglob("token*")]), 0)

    def test_login_routes_are_404_also_with_a_workspace(self):
        c = self.joined()
        for path in ("/login", "/login/once"):
            self.assertEqual(c.get(path).status, 404, path)
        self.assertEqual(c.post_csrf("/login/link", {"next": "/"}).status, 404)

    def test_local_mode_is_unchanged(self):
        app, d = make_app()
        try:
            c = Client(app)
            self.assertTrue((pathlib.Path(d) / "token").is_file())
            self.assertEqual(c.get("/login").status, 200)
            self.assertEqual(c.get("/join").status, 404)
            self.assertEqual(c.get("/").status, 303)
            self.assertEqual(c.get("/").get("Location"), "/login")
            c.login()
            self.assertIn("Log out", c.text(c.get("/")))
            self.assertNotIn("Delete my data", c.text(c.get("/")))
            self.assertEqual(c.post_csrf("/forget", {}).status, 404)
            self.assertEqual(c.post_csrf("/quick/open", {"study": "{}"}).status, 404)
            self.assertNotIn("Open a saved file", c.text(c.get("/studies")))
        finally:
            helpers.cleanup(d)


class JoinTest(PublicBase):
    def test_join_with_a_code_shows_one_short_screen(self):
        r = self.c.get("/join")
        self.assertEqual(r.status, 200)
        t = self.c.text(r)
        self.assertIn("Atelier helps you see your main risks in about 15 minutes.", t)
        self.assertIn("These results come only from your answers.", t)        # the honesty line
        self.assertEqual(t.count('<button'), 1)
        self.assertIn("Start</button>", t)
        self.assertEqual(len(re.findall(r'name="code"', t)), 1)
        self.assertIn("Invite code", t)
        self.assertEqual(len(PRE_RE.findall(t)), 1)
        self.assertIn("atelier_pre=", r.get("Set-Cookie"))

    def test_join_without_a_code_has_no_code_field_and_starts(self):
        app, d = make_public(None)
        try:
            c = Client(app)
            t = c.text(c.get("/join"))
            self.assertNotIn('name="code"', t)
            self.assertNotIn("Invite code", t)
            r = join(c, None)
            self.assertEqual((r.status, r.get("Location")), (303, "/"))
            self.assertEqual(c.get("/").status, 200)
        finally:
            helpers.cleanup(d)

    def test_french_join_screen(self):
        t = self.c.text(self.c.get("/join?lang=fr"))
        self.assertIn("Code d'invitation", t)
        self.assertIn("Commencer</button>", t)
        self.assertIn("Atelier vous aide à voir vos principaux risques en 15 minutes environ.", t)
        self.assertIn("Ces résultats viennent uniquement de vos réponses.", t)

    def test_right_code_makes_a_workspace_and_redirects_home(self):
        r = join(self.c, CODE)
        self.assertEqual((r.status, r.get("Location")), (303, "/"))
        self.assertEqual(len(ws_folders(self.app)), 1)
        self.assertEqual(self.c.get("/").status, 200)

    def test_the_code_is_compared_in_constant_time(self):
        with mock.patch.object(app_mod.hmac, "compare_digest", wraps=app_mod.hmac.compare_digest) as cmp:
            join(self.c, "wrong-code")
        self.assertIn((b"wrong-code", CODE.encode()), [tuple(x.args) for x in cmp.call_args_list])

    def test_wrong_code_gives_403_a_kind_message_and_no_workspace(self):
        r = join(self.c, "nope")
        self.assertEqual(r.status, 403)
        t = self.c.text(r)
        self.assertIn("Check the invite code and try again.", t)
        self.assertEqual(ws_folders(self.app), [])
        self.assertNotIn(workspaces.COOKIE, self.c.cookies)
        self.assertEqual(join(self.c, "").status, 403)       # an empty code is a wrong code
        self.assertEqual(self.c.get("/").status, 303)

    def test_the_form_needs_its_anti_forgery_pair(self):
        self.c.get("/join")
        self.assertEqual(self.c.post("/join", {"pre": "forged", "code": CODE}).status, 403)
        self.assertEqual(self.c.post("/join", {"code": CODE}).status, 403)
        other = Client(self.app)                                  # a form from one browser, a cookie from none
        pre = PRE_RE.search(self.c.text(self.c.get("/join"))).group(1)
        self.assertEqual(other.post("/join", {"pre": pre, "code": CODE}).status, 403)
        self.assertEqual(ws_folders(self.app), [])

    def test_more_than_ten_wrong_codes_in_ten_minutes_gives_429(self):
        for i in range(10):
            self.assertEqual(join(self.c, f"bad{i}", peer="203.0.113.5").status, 403, i)
        r = join(self.c, f"bad-11", peer="203.0.113.5")
        self.assertEqual(r.status, 429)
        self.assertIn("Take a short break", self.c.text(r))
        self.assertEqual(join(self.c, CODE, peer="203.0.113.5").status, 429)    # locked, even with the right code
        self.assertEqual(ws_folders(self.app), [])
        self.assertEqual(join(Client(self.app), CODE, peer="203.0.113.6").status, 303)   # another client is free

    def test_the_lock_ends_after_ten_minutes(self):
        for i in range(10):
            join(self.c, "bad", peer="203.0.113.5")
        lim = self.app.join_limiter
        lim.failures["203.0.113.5"] = [t - 11 * 60 for t in lim.failures["203.0.113.5"]]
        self.assertEqual(join(self.c, CODE, peer="203.0.113.5").status, 303)

    def test_a_visitor_with_a_workspace_is_sent_home_from_join(self):
        c = self.joined()
        self.assertEqual((c.get("/join").status, c.get("/join").get("Location")), (303, "/"))
        n = len(ws_folders(self.app))
        pre = PRE_RE.search(c.text(Client(self.app).get("/join"))).group(1)
        self.assertEqual(c.post("/join", {"pre": pre, "code": CODE}).status, 303)
        self.assertEqual(len(ws_folders(self.app)), n)


class LimiterMemoryTest(unittest.TestCase):
    def test_the_list_of_remembered_addresses_stays_bounded(self):
        lim = workspaces.JoinLimiter()
        with mock.patch.object(workspaces, "JOIN_TRACKED", 50):
            for i in range(500):
                lim.fail(f"10.0.{i // 250}.{i % 250}")
        self.assertLessEqual(len(lim.failures), 50)
        self.assertFalse(lim.locked("10.9.9.9"))


class ClientAddressTest(PublicBase):
    def addr(self, app, headers, peer):
        return app.client_address(Request("GET", "/join", headers, b"", peer=peer))

    def test_without_behind_proxy_the_socket_address_counts(self):
        self.assertEqual(self.addr(self.app, {"X-Real-IP": "198.51.100.9"}, "127.0.0.1"), "127.0.0.1")
        for i in range(10):
            join(self.c, "bad", headers={"X-Real-IP": f"198.51.100.{i}"}, peer="127.0.0.1")
        self.assertEqual(join(self.c, "bad", headers={"X-Real-IP": "198.51.100.77"}, peer="127.0.0.1").status, 429)

    def test_behind_proxy_x_real_ip_counts(self):
        app, d = make_public(CODE, behind_proxy=True)
        try:
            self.assertEqual(self.addr(app, {"X-Real-IP": "198.51.100.9"}, "127.0.0.1"), "198.51.100.9")
            self.assertEqual(self.addr(app, {"X-Real-IP": "2001:db8::1"}, "127.0.0.1"), "2001:db8::1")
            self.assertEqual(self.addr(app, {"X-Real-IP": "not an address"}, "127.0.0.1"), "127.0.0.1")
            self.assertEqual(self.addr(app, {}, "127.0.0.1"), "127.0.0.1")
            c = Client(app)
            for i in range(10):
                join(c, "bad", headers={"X-Real-IP": "198.51.100.9"}, peer="127.0.0.1")
            self.assertEqual(join(c, "bad", headers={"X-Real-IP": "198.51.100.9"}, peer="127.0.0.1").status, 429)
            self.assertEqual(join(c, CODE, headers={"X-Real-IP": "198.51.100.10"}, peer="127.0.0.1").status, 303)
        finally:
            helpers.cleanup(d)


class WorkspaceTest(PublicBase):
    def test_every_page_but_join_redirects_to_join_without_a_workspace(self):
        sid = "s-20261111-0123abcd"
        for path in ("/", "/studies", "/quick/new", f"/quick/{sid}/about", f"/quick/{sid}/results", f"/s/{sid}",
                     f"/s/{sid}/export.json", f"/s/{sid}/delete", "/studies?f=removed"):
            r = self.c.get(path)
            self.assertEqual((r.status, r.get("Location")), (303, "/join"), path)
        for path in ("/quick/new", "/forget", "/expert", f"/s/{sid}/delete"):
            r = self.c.post(path, {})
            self.assertEqual((r.status, r.get("Location")), (303, "/join"), path)

    def test_a_cookie_that_names_no_workspace_is_the_same_as_none(self):
        for bad in ("x", "A" * 43, "../" * 20, workspaces.hash_id("A" * 43)):
            c = Client(self.app)
            c.cookies[workspaces.COOKIE] = bad
            r = c.get("/")
            self.assertEqual((r.status, r.get("Location")), (303, "/join"), bad)

    def test_the_cookie_flags_and_the_size_of_the_id(self):
        r = join(self.c, CODE)
        ck = [c for c in r.all("Set-Cookie") if c.startswith(workspaces.COOKIE + "=")]
        self.assertEqual(len(ck), 1)
        self.assertIn("; HttpOnly; Secure; SameSite=Lax; Path=/", ck[0])
        wid = ck[0].split(";")[0].split("=", 1)[1]
        self.assertGreaterEqual(len(wid) * 6, 128)                  # base64url: 6 bits per character
        self.assertRegex(wid, r"^[A-Za-z0-9_-]+$")
        self.assertEqual(join(Client(self.app), CODE).all("Set-Cookie")[0].split(";")[0].split("=")[1] == wid, False)

    def test_only_a_hash_of_the_id_names_the_folder(self):
        join(self.c, CODE)
        wid = self.c.cookies[workspaces.COOKIE]
        want = hashlib.sha256(wid.encode()).hexdigest()
        self.assertEqual(ws_folders(self.app), [want])
        self.assertTrue((self.app.data_dir / "workspaces" / want / "last_seen").is_file())
        for p in self.app.data_dir.rglob("*"):
            self.assertNotIn(wid, str(p))
            if p.is_file():
                self.assertNotIn(wid.encode(), p.read_bytes(), p)
        self.assertEqual(oct((self.app.data_dir / "workspaces" / want).stat().st_mode & 0o777), "0o700")

    def test_a_study_is_saved_in_the_workspace_folder(self):
        c = self.joined()
        sid = SID_RE_ANY.search(new_study(c).get("Location")).group(0)
        h = hashlib.sha256(c.cookies[workspaces.COOKIE].encode()).hexdigest()
        self.assertTrue((self.app.data_dir / "workspaces" / h / "studies" / f"{sid}.json").is_file())
        self.assertFalse((self.app.data_dir / "studies").exists())

    def test_two_visitors_see_only_their_own_studies(self):
        a, b = self.visitor(), self.visitor()
        sid = SID_RE_ANY.search(new_study(a, "Alice shop").get("Location")).group(0)
        self.assertIn("Alice shop", a.text(a.get("/studies")))
        self.assertNotIn("Alice shop", b.text(b.get("/studies")))
        self.assertNotIn("Alice shop", b.text(b.get("/")))
        for path in (f"/quick/{sid}/about", f"/quick/{sid}/risks", f"/quick/{sid}/now", f"/quick/{sid}/results",
                     f"/s/{sid}/export.json", f"/s/{sid}/export.xlsx", f"/s/{sid}/delete", f"/s/{sid}"):
            self.assertEqual(b.get(path).status, 404, path)
        self.assertEqual(b.post_csrf(f"/s/{sid}/delete", {}).status, 404)
        self.assertEqual(b.post_csrf(f"/quick/{sid}/about", {"name": "Hijack"}, page="/studies").status, 404)
        self.assertEqual(a.get(f"/quick/{sid}/about").status, 200)         # untouched
        self.assertIn("Alice shop", a.text(a.get("/studies")))

    def test_each_workspace_has_its_own_forms_token(self):
        a, b = self.visitor(), self.visitor()
        self.assertNotEqual(a.csrf("/studies"), b.csrf("/studies"))
        self.assertEqual(a.csrf("/studies"), a.csrf("/"))
        self.assertEqual(a.post("/quick/new", {"name": "x", "csrf": b.csrf("/studies")}).status, 403)
        self.assertEqual(a.post("/quick/new", {"name": "x"}).status, 403)

    def test_touching_a_page_updates_last_seen(self):
        c = self.joined()
        f = self.app.data_dir / "workspaces" / hashlib.sha256(c.cookies[workspaces.COOKIE].encode()).hexdigest() / "last_seen"
        old = time.time() - 5 * DAY
        os.utime(f, (old, old))
        for path in ("/studies", "/how", "/"):
            os.utime(f, (old, old))
            self.assertEqual(c.get(path).status, 200)
            self.assertGreater(f.stat().st_mtime, time.time() - 60, path)

    def test_session_survives_a_restart_of_the_app(self):
        c = self.joined()
        sid = SID_RE_ANY.search(new_study(c).get("Location")).group(0)
        csrf = c.csrf("/studies")
        again = app_mod.App(self.app.data_dir, port=8770, public=True, invite_code=CODE)
        c.app = again
        self.assertEqual(c.get(f"/quick/{sid}/about").status, 200)
        self.assertEqual(c.csrf("/studies"), csrf)

    def test_the_body_size_limit_stays(self):
        c = self.joined()
        r = c.req("POST", "/quick/new", body=b"x" * (5 * 1024 * 1024 + 1), ctype="application/x-www-form-urlencoded")
        self.assertEqual(r.status, 413)
        self.assertEqual(self.app.body_limit("/quick/new"), app_mod.MAX_UPLOAD)

    def test_delete_removes_the_study_for_good(self):
        c = self.joined()
        sid = SID_RE_ANY.search(new_study(c).get("Location")).group(0)
        r = c.post_csrf(f"/s/{sid}/delete", {})
        self.assertEqual(r.status, 303)
        self.assertEqual(list((self.app.data_dir / "workspaces").rglob("s-*")), [])
        self.assertEqual(list((self.app.data_dir / "workspaces").rglob("trash")), [])


class LimitsTest(PublicBase):
    def test_the_21st_study_gets_a_kind_page(self):
        c = self.joined()
        for i in range(20):
            self.assertEqual(new_study(c, f"S{i}").status, 303, i)
        r = new_study(c, "S21")
        self.assertEqual(r.status, 409)
        self.assertIn("You have 20 studies. Delete one to start a new one.", c.text(r))
        self.assertEqual(len(self.store_of(c)
                             .list()), 20)
        r = c.get("/quick/new")                                   # the form itself says so before it is filled in
        self.assertEqual(r.status, 409)
        self.assertIn("You have 20 studies.", c.text(r))
        self.assertEqual(c.get("/quick/new?lang=fr").status, 409)
        self.assertIn("Vous avez 20 études. Effacez-en une pour en commencer une nouvelle.", c.text(c.get("/quick/new?lang=fr")))
        sid = SID_RE_ANY.search(c.text(c.get("/studies"))).group(0)
        self.assertEqual(c.post_csrf(f"/s/{sid}/delete", {}).status, 303)
        self.assertEqual(new_study(c, "S22").status, 303)           # deleting one makes room

    def test_the_limit_is_per_workspace(self):
        a, b = self.visitor(), self.visitor()
        for i in range(20):
            new_study(a, f"S{i}")
        self.assertEqual(new_study(a).status, 409)
        self.assertEqual(new_study(b).status, 303)

    def test_the_5001st_workspace_gets_a_kind_page(self):
        self.app.workspaces.max_workspaces = 3
        for _ in range(3):
            self.assertEqual(join(Client(self.app), CODE).status, 303)
        c = Client(self.app)
        t = c.text(c.get("/join"))
        self.assertIn("We are full for now, please come back soon", t)
        self.assertNotIn('name="pre"', t)
        self.assertEqual(c.get("/join").status, 503)
        self.assertEqual(len(ws_folders(self.app)), 3)
        self.assertEqual(workspaces.MAX_WORKSPACES, 5000)
        self.assertEqual(workspaces.MAX_STUDIES, 20)
        self.assertIn("Nous sommes complets pour le moment", c.text(c.get("/join?lang=fr")))
        pre_page = Client(self.app)
        self.app.workspaces.max_workspaces = 4
        pre = PRE_RE.search(pre_page.text(pre_page.get("/join"))).group(1)
        self.app.workspaces.max_workspaces = 3                     # it fills up between the form and the click
        r = pre_page.post("/join", {"pre": pre, "code": CODE})
        self.assertIn("We are full for now", pre_page.text(r))
        self.assertEqual(len(ws_folders(self.app)), 3)

    def test_joins_that_arrive_together_cannot_pass_the_limit(self):
        self.app.workspaces.max_workspaces = 5
        results = []

        def go():
            c = Client(self.app)
            pre = PRE_RE.search(c.text(c.get("/join"))).group(1)
            results.append(c.post("/join", {"pre": pre, "code": CODE}).status)
        threads = [threading.Thread(target=go) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(len(ws_folders(self.app)), 5)
        self.assertEqual(sorted(results).count(303), 5)

    def test_a_visitor_with_a_workspace_still_works_when_full(self):
        c = self.joined()
        self.app.workspaces.max_workspaces = 1
        self.assertEqual(c.get("/studies").status, 200)


class PurgeTest(PublicBase):
    def age(self, c, days):
        h = hashlib.sha256(c.cookies[workspaces.COOKIE].encode()).hexdigest()
        f = self.app.data_dir / "workspaces" / h / "last_seen"
        t = time.time() - days * DAY
        os.utime(f, (t, t))
        return h

    def test_purge_idle_deletes_only_the_idle_workspaces(self):
        old, fresh = self.visitor(), self.visitor()
        new_study(old, "Old")
        h_old, h_fresh = self.age(old, 31), self.age(fresh, 29)
        self.assertEqual(self.app.purge_idle(days=30), 1)
        self.assertEqual(ws_folders(self.app), [h_fresh])
        self.assertEqual(old.get("/").get("Location"), "/join")      # the old cookie names nothing now
        self.assertEqual(fresh.get("/studies").status, 200)
        self.assertEqual(self.app.purge_idle(days=30), 0)

    def test_the_default_is_30_days_and_days_is_a_parameter(self):
        c = self.joined()
        h = self.age(c, 2)
        self.assertEqual(self.app.purge_idle(), 0)
        self.assertEqual(self.app.purge_idle(days=1), 1)
        self.assertEqual(ws_folders(self.app), [])
        self.assertFalse((self.app.data_dir / "workspaces" / h).exists())

    def test_what_is_not_a_workspace_is_left_alone(self):
        (self.app.data_dir / "workspaces" / "notes").mkdir()
        (self.app.data_dir / "workspaces" / "notes" / "last_seen").touch()
        t = time.time() - 90 * DAY
        os.utime(self.app.data_dir / "workspaces" / "notes" / "last_seen", (t, t))
        self.assertEqual(self.app.purge_idle(days=30), 0)
        self.assertTrue((self.app.data_dir / "workspaces" / "notes").is_dir())

    def test_a_workspace_without_last_seen_ages_by_its_folder(self):
        c = self.joined()
        h = self.age(c, 0)
        (self.app.data_dir / "workspaces" / h / "last_seen").unlink()
        t = time.time() - 40 * DAY
        os.utime(self.app.data_dir / "workspaces" / h, (t, t))
        self.assertEqual(self.app.purge_idle(days=30), 1)

    def test_local_mode_has_nothing_to_purge(self):
        app, d = make_app()
        try:
            self.assertEqual(app.purge_idle(days=30), 0)
        finally:
            helpers.cleanup(d)

    def test_the_server_runs_it_at_start_and_then_every_hour(self):
        c = self.joined()
        self.age(c, 40)
        stop = threading.Event()
        calls = []
        real = self.app.purge_idle
        self.app.purge_idle = lambda *a, **k: calls.append(1) or real(*a, **k)
        th = threading.Thread(target=server.purge_loop, args=(self.app, 0.05, stop), daemon=True)
        th.start()
        deadline = time.time() + 5
        while len(calls) < 3 and time.time() < deadline:
            time.sleep(0.01)
        stop.set()
        th.join(5)
        self.assertGreaterEqual(len(calls), 3)
        self.assertEqual(ws_folders(self.app), [])
        self.assertEqual(server.purge_loop.__defaults__[0], 3600)    # the default period is one hour

    def test_a_failing_clean_up_does_not_stop_the_loop(self):
        stop = threading.Event()
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise OSError("disk")
        self.app.purge_idle = boom
        th = threading.Thread(target=server.purge_loop, args=(self.app, 0.02, stop), daemon=True)
        with mock.patch("sys.stderr"):
            th.start()
            deadline = time.time() + 5
            while len(calls) < 2 and time.time() < deadline:
                time.sleep(0.01)
            stop.set()
            th.join(5)
        self.assertGreaterEqual(len(calls), 2)


class ForgetTest(PublicBase):
    def test_forget_deletes_the_workspace_clears_the_cookie_and_says_goodbye(self):
        c = self.joined()
        new_study(c)
        h = ws_folders(self.app)[0]
        r = c.post_csrf("/forget", {})
        self.assertEqual(r.status, 200)
        self.assertIn("Your data is deleted. Thank you for trying Atelier.", c.text(r))
        ck = [x for x in r.all("Set-Cookie") if x.startswith(workspaces.COOKIE + "=")]
        self.assertEqual(len(ck), 1)
        self.assertIn("Max-Age=0", ck[0])
        self.assertNotIn(workspaces.COOKIE, c.cookies)
        self.assertFalse((self.app.data_dir / "workspaces" / h).exists())
        self.assertEqual(c.get("/").get("Location"), "/join")

    def test_forget_needs_the_forms_token(self):
        c = self.joined()
        self.assertEqual(c.post("/forget", {}).status, 403)
        self.assertEqual(c.post("/forget", {"csrf": "wrong"}).status, 403)
        self.assertEqual(len(ws_folders(self.app)), 1)

    def test_forget_touches_only_the_visitors_own_workspace(self):
        a, b = self.visitor(), self.visitor()
        mine = ws_folders(self.app)
        a.post_csrf("/forget", {})
        self.assertEqual(len(ws_folders(self.app)), 1)
        self.assertEqual(b.get("/studies").status, 200)
        self.assertEqual(len(mine), 2)

    def test_the_goodbye_page_offers_a_new_start_and_french(self):
        c = self.joined()
        c.cookies["atelier_lang"] = "fr"
        r = c.post_csrf("/forget", {})
        self.assertIn("Vos données sont effacées. Merci d'avoir essayé Atelier.", c.text(r))
        self.assertIn('href="/join"', c.text(r))

    def test_the_header_says_delete_my_data_instead_of_log_out(self):
        c = self.joined()
        t = c.text(c.get("/"))
        self.assertIn("Delete my data", t)
        self.assertNotIn("Log out", t)
        self.assertIn('action="/forget"', t)
        self.assertIn("data-confirm=", t)
        fr = c.text(c.get("/?lang=fr"))
        self.assertIn("Effacer mes données", fr)
        self.assertNotIn("Se déconnecter", fr)
        for path in ("/studies?lang=en", "/how?lang=en", "/quick/new?lang=en"):
            self.assertIn("Delete my data", c.text(c.get(path)), path)

    def test_a_study_page_header_has_it_too(self):
        c = self.joined()
        sid = SID_RE_ANY.search(new_study(c).get("Location")).group(0)
        self.assertIn("Delete my data", c.text(c.get(f"/quick/{sid}/risks")))


def saved_file(c, name="Saved bakery"):
    sid = SID_RE_ANY.search(new_study(c, name).get("Location")).group(0)
    r = c.get(f"/s/{sid}/export.json")
    assert r.status == 200
    return sid, c.text(r)


class OpenFileTest(PublicBase):
    def open(self, c, text, page="/studies", **kw):
        return c.post_csrf("/quick/open", {"study": text}, page=page)

    def test_the_studies_page_offers_the_file_picker_and_a_small_same_origin_script(self):
        c = self.joined()
        r = c.get("/studies")
        t = c.text(r)
        self.assertIn("Open a saved file", t)
        self.assertIn('action="/quick/open"', t)
        self.assertIn('name="study"', t)
        self.assertIn('type="file"', t)
        self.assertIn('src="/static/app.js"', t)
        self.assertNotRegex(t, r"<script(?![^>]*\bsrc=)")           # no inline script
        csp = r.get("Content-Security-Policy")
        self.assertEqual(csp, app_mod.CSP)
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        js = c.text(c.get("/static/app.js"))
        for word in ("FileReader", "study", "512"):
            self.assertIn(word, js)
        self.assertIn("Ouvrir un fichier enregistré", c.text(c.get("/studies?lang=fr")))

    def test_a_valid_file_lands_in_the_workspace_with_a_new_id(self):
        c = self.joined()
        sid, text = saved_file(c)
        r = self.open(c, text)
        self.assertEqual(r.status, 303)
        new = SID_RE_ANY.search(r.get("Location")).group(0)
        self.assertNotEqual(new, sid)
        self.assertRegex(r.get("Location"), r"^/quick/s-[0-9]{8}-[0-9a-f]{8}/(about|risks|now|results)$")
        self.assertEqual(c.get(r.get("Location")).status, 200)
        names = c.text(c.get("/studies"))
        self.assertEqual(names.count("Saved bakery"), 2)
        self.assertEqual(self.store_of(c).load(new)["study"]["name"], "Saved bakery")

    def test_the_file_of_one_visitor_opens_in_another_workspace_only(self):
        a, b = self.visitor(), self.visitor()
        _, text = saved_file(a, "From A")
        r = self.open(b, text)
        self.assertEqual(r.status, 303)
        self.assertIn("From A", b.text(b.get("/studies")))
        self.assertEqual(a.text(a.get("/studies")).count("From A"), 1)

    def test_a_file_with_answers_at_every_step_is_kept(self):
        c = self.joined()
        sid = SID_RE_ANY.search(new_study(c, "Full").get("Location")).group(0)
        ids = re.findall(r'name="keep" value="([^"]+)"', c.text(c.get(f"/quick/{sid}/risks")))
        self.assertEqual(c.post_csrf(f"/quick/{sid}/risks", {"keep": ids, "lang": "en"}, page=f"/quick/{sid}/risks").status, 303)
        text = c.text(c.get(f"/s/{sid}/export.json"))
        r = self.open(c, text)
        self.assertEqual(r.status, 303)
        self.assertTrue(r.get("Location").endswith("/now"))
        self.assertEqual(c.get(r.get("Location")).status, 200)
        self.assertEqual(c.get(r.get("Location").replace("/now", "/results")).status, 200)

    def test_anything_else_gives_400_and_a_kind_message(self):
        c = self.joined()
        _, text = saved_file(c)
        good = json.loads(text)
        bad_cases = {
            "empty": "",
            "not json": "hello",
            "json but not an object": "[1, 2]",
            "null": "null",
            "an empty object": "{}",
            "no quick answers": json.dumps({k: v for k, v in good.items() if k != "quick"}),
            "the guide example": json.dumps(helpers.example_json()),
            "quick is a string": json.dumps(dict(good, quick="x")),
            "wrong study format": json.dumps(dict(good, format="other")),
            "wrong quick format": json.dumps(dict(good, quick=dict(good["quick"], format="x"))),
            "unknown risk": json.dumps(dict(good, quick=dict(good["quick"], risks=[{"id": "ZZ99", "decision": "keep"}]))),
            "bad decision": json.dumps(dict(good, quick=dict(good["quick"], risks=[dict(good["quick"]["risks"][0], decision="maybe")]))),
            "profile not an object": json.dumps(dict(good, quick=dict(good["quick"], profile=5))),
            "risks not a list": json.dumps(dict(good, quick=dict(good["quick"], risks=7))),
            "unknown calibration": json.dumps(dict(good, study=dict(good["study"], calibration="nope"))),
            "deep nesting": "[" * 100000,
        }
        self.assertGreaterEqual(len(good["quick"]["risks"]), 1)
        for label, body in bad_cases.items():
            r = self.open(c, body)
            self.assertEqual(r.status, 400, label)
            t = c.text(r)
            self.assertIn("Choose a study file saved with", t, label)
            self.assertIn("Download the study file", t, label)
            self.assertNotIn("Traceback", t)
        self.assertEqual(self.open(c, "{}", page="/studies").status, 400)
        self.assertEqual(len(c.text(c.get("/studies")).split('<tr>')) - 2, 1)       # only the original study exists (the first <tr> is the header)
        self.assertEqual(c.post_csrf("/quick/open", {}).status, 400)               # a missing field too

    def test_french_message(self):
        c = self.joined()
        c.cookies["atelier_lang"] = "fr"
        self.assertIn("Choisissez un fichier d'étude enregistré", c.text(self.open(c, "x")))

    def test_the_file_is_at_most_512_kb(self):
        c = self.joined()
        _, text = saved_file(c)
        pad = dict(json.loads(text))
        pad["pad"] = "x" * (512 * 1024)
        r = self.open(c, json.dumps(pad))
        self.assertEqual(r.status, 413)
        self.assertIn("512 KB at most", c.text(r))
        self.assertEqual(self.open(c, "x" * (600 * 1024)).status, 413)
        self.assertEqual(self.app.body_limit("/quick/open"), 3 * 512 * 1024 + 8192)
        self.assertEqual(self.app.body_limit("/quick/new"), app_mod.MAX_UPLOAD)
        r = c.req("POST", "/quick/open", body=b"s" * (4 * 1024 * 1024), ctype="application/x-www-form-urlencoded")
        self.assertEqual(r.status, 413)
        self.assertEqual(self.open(c, text).status, 303)                          # a normal file is far below

    def test_the_form_token_is_needed(self):
        c = self.joined()
        _, text = saved_file(c)
        self.assertEqual(c.post("/quick/open", {"study": text}).status, 403)
        self.assertEqual(c.post("/quick/open", {"study": text, "csrf": "no"}).status, 403)
        self.assertEqual(Client(self.app).post("/quick/open", {"study": text}).get("Location"), "/join")

    def test_the_study_limit_applies(self):
        c = self.joined()
        _, text = saved_file(c)
        for i in range(19):
            new_study(c, f"S{i}")
        r = self.open(c, text)
        self.assertEqual(r.status, 409)
        self.assertIn("You have 20 studies", c.text(r))

    def test_the_stored_study_is_built_again_from_the_answers(self):
        c = self.joined()
        _, text = saved_file(c)
        evil = json.loads(text)
        evil["unexpected"] = {"x": 1}
        evil["study"]["name"] = "Edited name"
        evil["feared_events"] = [{"id": "junk"}]
        r = self.open(c, json.dumps(evil))
        self.assertEqual(r.status, 303)
        new = SID_RE_ANY.search(r.get("Location")).group(0)
        stored = self.store_of(c).load(new)
        self.assertNotIn("unexpected", stored)
        self.assertNotEqual(stored["feared_events"], [{"id": "junk"}])
        self.assertEqual(stored["study"]["name"], json.loads(text)["study"]["name"])


@unittest.skipUnless(shutil.which("node"), "node is not installed; the script is checked only where it is")
class OpenFileScriptTest(unittest.TestCase):
    """app.js run against a small fake page (not a browser): the form shows, the file text goes into `study`."""

    def test_the_script_reads_the_file_into_the_study_field_and_submits(self):
        r = subprocess.run(["node", str(helpers.APP_DIR / "tests" / "open_file_script.js"),
                            str(helpers.APP_DIR / "static" / "app.js")], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["unhidden"])
        self.assertEqual((out["noFile"], out["submittedAfterNoFile"]), ("BAD", 0))      # no file: a message, no post
        self.assertEqual((out["big"], out["submittedAfterBig"]), ("BIG", 0))            # over 512 KB: a message, no post
        self.assertEqual((out["fieldValue"], out["submittedAfterOk"], out["msgAfterOk"]), ('{"a":"b"}', 1, ""))


class DataTextTest(PublicBase):
    def test_how_it_works_says_your_data_in_public_mode(self):
        c = self.joined()
        t = c.text(c.get("/how"))
        self.assertIn("Your answers stay in a private space that only your browser can open. It is cleared after 30 days "
                      "without a visit, and you can clear it yourself at any time with Delete my data. Download your results "
                      "or the study file to keep a copy.", t)
        self.assertNotIn("stays on the computer that runs Atelier", t)
        fr = c.text(c.get("/how?lang=fr"))
        self.assertIn("Vos réponses restent dans un espace privé que seul votre navigateur peut ouvrir. Il est effacé après "
                      "30 jours sans visite, et vous pouvez l'effacer vous-même à tout moment avec Effacer mes données. "
                      "Téléchargez vos résultats ou le fichier d'étude pour en garder une copie.", fr)

    def test_how_it_works_is_readable_before_joining(self):
        r = self.c.get("/how")
        self.assertEqual(r.status, 200)
        self.assertIn("Your answers stay in a private space", self.c.text(r))
        self.assertNotIn("Delete my data</button>", self.c.text(r))

    def test_local_mode_keeps_its_text(self):
        app, d = make_app()
        try:
            c = Client(app)
            c.login()
            self.assertIn("Your data stays on the computer that runs Atelier: your answers are saved there, and only there.",
                          c.text(c.get("/how")))
            self.assertIn("Vos données restent sur l'ordinateur qui fait tourner Atelier", c.text(c.get("/how?lang=fr")))
        finally:
            helpers.cleanup(d)


class WordingTest(PublicBase):
    """The new pages are plain, kind and positive, in English and French."""

    def pages(self, lang):
        c = Client(self.app)
        join(c, CODE)
        c.cookies["atelier_lang"] = lang
        out = {}
        out["join"] = Client(self.app).text(Client(self.app).get(f"/join?lang={lang}"))
        bad = Client(self.app)
        out["join-bad-code"] = bad.text(join(bad, "zzz", headers={}))
        out["studies"] = c.text(c.get(f"/studies?lang={lang}"))
        out["how"] = c.text(c.get(f"/how?lang={lang}"))
        v = self.visitor()
        v.cookies["atelier_lang"] = lang
        out["goodbye"] = v.text(v.post_csrf("/forget", {}))
        for key in ("open_bad", "open_big"):
            out[key] = views_public.open_error_page(lang, key, None)
        out["limit"] = views_public.limit_page(lang, None)
        out["full"] = views_public.full_page(lang)
        out["goodbye-fr"] = views_public.goodbye_page(lang)
        out["wait"] = views_public.join_page("p", lang, True, "wait")
        out["expired"] = views_public.join_page("p", lang, True, "expired")
        return out

    def test_no_negative_or_fear_words_in_english(self):
        for name, page in self.pages("en").items():
            t = words_read(page)
            self.assertIsNone(EN_NEGATIVE.search(t), (name, EN_NEGATIVE.search(t)))
            self.assertIsNone(FEAR.search(t), (name, FEAR.search(t)))

    def test_no_negative_or_fear_words_in_french(self):
        for name, page in self.pages("fr").items():
            t = words_read(page)
            self.assertIsNone(FR_NEGATIVE.search(t), (name, FR_NEGATIVE.search(t)))
            self.assertIsNone(FEAR.search(t), (name, FEAR.search(t)))

    def test_every_new_text_exists_in_both_languages(self):
        self.assertEqual(set(views_public.T["en"]), set(views_public.T["fr"]))


class LaunchTest(unittest.TestCase):
    """The command line: flags, the invite code file, a real server on a free port."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="atelier-public-cli-"))
        self.data = self.tmp / "data"
        self.f = self.tmp / "code"
        self.f.write_text(CODE + "\n")
        os.chmod(self.f, 0o600)

    def tearDown(self):
        helpers.cleanup(self.tmp)

    def test_flags_are_parsed(self):
        a = server.parse_args(["--public", "--invite-code-file", "x", "--behind-proxy"])
        self.assertEqual((a.public, a.invite_code_file, a.behind_proxy), (True, "x", True))
        a = server.parse_args([])
        self.assertEqual((a.public, a.invite_code_file, a.behind_proxy), (False, None, False))

    def test_the_code_is_the_first_line_of_the_file(self):
        self.assertEqual(server.read_invite_code(self.f), CODE)
        self.f.write_text("  spaced code  \nsecond line\n")
        self.assertEqual(server.read_invite_code(self.f), "spaced code")

    def test_a_file_readable_by_group_or_others_is_refused(self):
        for mode in (0o640, 0o604, 0o644, 0o660, 0o666, 0o604):
            os.chmod(self.f, mode)
            with self.assertRaises(server.InviteCodeError, msg=oct(mode)):
                server.read_invite_code(self.f)
        for mode in (0o600, 0o400):
            os.chmod(self.f, mode)
            self.assertEqual(server.read_invite_code(self.f), CODE)

    def test_a_missing_or_empty_file_is_refused(self):
        with self.assertRaises(server.InviteCodeError):
            server.read_invite_code(self.tmp / "nothing")
        self.f.write_text("\n")
        with self.assertRaises(server.InviteCodeError):
            server.read_invite_code(self.f)

    def test_main_refuses_to_start_with_a_readable_file(self):
        os.chmod(self.f, 0o644)
        with tempfile.TemporaryFile("w+") as err:
            with mock.patch("sys.stderr", err):
                rc = server.main(["--public", "--invite-code-file", str(self.f), "--data-dir", str(self.data), "--port", "0"])
            err.seek(0)
            self.assertEqual(rc, 2)
            self.assertIn("refusing to start", err.read())
        self.assertFalse(self.data.exists())                         # nothing was created

    def test_invite_code_file_needs_public(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(server.main(["--invite-code-file", str(self.f), "--data-dir", str(self.data), "--port", "0"]), 2)

    def run_server(self, *flags):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        out = open(self.tmp / "out.log", "w")
        proc = subprocess.Popen([sys.executable, str(SERVE), "--port", str(port), "--data-dir", str(self.data), *flags],
                                stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        self.addCleanup(lambda: (proc.terminate(), proc.wait(10), out.close()))
        deadline = time.time() + 15
        while time.time() < deadline:
            if proc.poll() is not None:
                self.fail("server exited: " + (self.tmp / "out.log").read_text())
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                return port
            except OSError:
                time.sleep(0.1)
        self.fail("server did not start")

    def http(self, port, method, path, form=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        body = None
        h = dict(headers or {})
        if form is not None:
            import urllib.parse
            body = urllib.parse.urlencode(form).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(method, path, body, h)
        r = conn.getresponse()
        data = r.read().decode("utf-8", "replace")
        out = (r.status, data, r.getheaders())
        conn.close()
        return out

    def join_attempt(self, port, code, real_ip=None):
        h = {}
        if real_ip:
            h["X-Real-IP"] = real_ip
        st, page, hdrs = self.http(port, "GET", "/join", headers=h)
        pre = PRE_RE.search(page).group(1)
        h["Cookie"] = f"atelier_pre={pre}"
        return self.http(port, "POST", "/join", {"pre": pre, "code": code}, h)

    def test_a_real_public_server(self):
        port = self.run_server("--public", "--invite-code-file", str(self.f))
        st, page, _ = self.http(port, "GET", "/login")
        self.assertEqual(st, 404)
        self.assertEqual(self.http(port, "GET", "/")[0:1], (303,))
        self.assertFalse((self.data / "token").exists())
        log = (self.tmp / "out.log").read_text()
        self.assertIn("Public mode", log)
        self.assertNotIn("login/once", log)
        st, _, hdrs = self.join_attempt(port, CODE)
        self.assertEqual(st, 303)
        cookies = [v for k, v in hdrs if k.lower() == "set-cookie"]
        self.assertTrue(any(c.startswith("atelier_session=") and "HttpOnly; Secure; SameSite=Lax; Path=/" in c for c in cookies))
        self.assertEqual(len(list((self.data / "workspaces").iterdir())), 1)

    def test_the_socket_address_is_used_without_behind_proxy(self):
        port = self.run_server("--public", "--invite-code-file", str(self.f))
        for i in range(10):
            self.assertEqual(self.join_attempt(port, "bad", real_ip=f"198.51.100.{i}")[0], 403)
        self.assertEqual(self.join_attempt(port, "bad", real_ip="198.51.100.99")[0], 429)     # X-Real-IP is ignored

    def test_behind_proxy_x_real_ip_is_used(self):
        port = self.run_server("--public", "--invite-code-file", str(self.f), "--behind-proxy")
        for i in range(10):
            self.assertEqual(self.join_attempt(port, "bad", real_ip="198.51.100.1")[0], 403)
        self.assertEqual(self.join_attempt(port, "bad", real_ip="198.51.100.1")[0], 429)
        self.assertEqual(self.join_attempt(port, CODE, real_ip="198.51.100.2")[0], 303)

    def test_old_workspaces_are_cleared_when_the_server_starts(self):
        old = self.data / "workspaces" / ("a" * 64)
        old.mkdir(parents=True)
        (old / "last_seen").touch()
        t = time.time() - 45 * DAY
        os.utime(old / "last_seen", (t, t))
        self.run_server("--public")
        deadline = time.time() + 10
        while old.exists() and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(old.exists())

    def test_local_mode_still_prints_its_login_link(self):
        self.run_server()
        log = (self.tmp / "out.log").read_text()
        self.assertIn("login/once?n=", log)
        self.assertTrue((self.data / "token").is_file())



class DiskBounds(unittest.TestCase):
    """Public mode keeps disk use bounded: a study file has a size cap, and joins wait when the disk runs low."""

    def test_study_size_cap(self):
        from atelier_app import storage, web
        d = tempfile.mkdtemp(prefix="atelier-test-")
        try:
            st = storage.Store(d, max_bytes=2000)
            sid = st.create({"x": "a" * 100})
            with self.assertRaises(web.HTTPError) as cm:
                st.save(sid, {"x": "a" * 5000})
            self.assertEqual(cm.exception.status, 413)
            self.assertIn("a" * 100, (pathlib.Path(d) / "studies" / (sid + ".json")).read_text())
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_low_disk_counts_as_full(self):
        from atelier_app import workspaces
        d = tempfile.mkdtemp(prefix="atelier-test-")
        try:
            ws = workspaces.Workspaces(d)
            self.assertFalse(ws.full())
            old = workspaces.MIN_FREE_BYTES
            workspaces.MIN_FREE_BYTES = 1 << 62
            try:
                self.assertTrue(ws.full())
            finally:
                workspaces.MIN_FREE_BYTES = old
        finally:
            shutil.rmtree(d, ignore_errors=True)


class PublisherFooter(unittest.TestCase):
    def _body(self, content, path="/how?lang=en"):
        d = tempfile.mkdtemp(prefix="atelier-test-")
        try:
            if content is not None:
                (pathlib.Path(d) / "publisher.json").write_text(content)
            from atelier_app.app import App
            c = helpers.Client(App(d, port=8770, public=True, invite_code=None))
            return c.text(c.get(path))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            from atelier_app import views
            views.PUBLISHER = None

    def test_footer_states_the_publisher_with_a_link(self):
        good = json.dumps({"name": "CPLT", "url": "https://cplt.tech", "feedback_url": "https://cplt.tech/contact"})
        for path in ("/how?lang=en", "/join?lang=en"):
            body = self._body(good, path)
            self.assertIn("Atelier is offered by <strong>CPLT</strong>", body)
            self.assertIn('href="https://cplt.tech"', body)
            self.assertIn('>cplt.tech</a>', body)
            self.assertIn('href="https://cplt.tech/contact"', body)
        fr = self._body(good, "/how?lang=fr")
        self.assertIn("Atelier est proposé par <strong>CPLT</strong>", fr)
        self.assertIn("Partagez-les", fr)

    def test_no_footer_without_a_valid_file(self):
        for content in (None, "not json", json.dumps({"name": "X", "url": "javascript:alert(1)"}),
                        json.dumps({"name": "X", "url": 'https://x"onmouseover=1'}),
                        json.dumps({"name": "X", "url": "https://x.org", "feedback_url": "http://plain"})):
            self.assertNotIn('class="publisher"', self._body(content), content)


class SearchEngines(unittest.TestCase):
    """Public mode asks search engines to leave the app out of results; local mode adds nothing."""

    def test_public_noindex_and_robots(self):
        app, d = helpers.make_app(public=True, invite_code=None)
        try:
            c = helpers.Client(app)
            r = c.get("/join")
            self.assertEqual(r.get("X-Robots-Tag"), "noindex, nofollow")
            self.assertIn('<meta name="robots" content="noindex, nofollow">', c.text(r))
            r = c.get("/robots.txt")
            self.assertEqual(r.status, 200)
            self.assertNotIn("Disallow", c.text(r))   # crawlers must be able to read the noindex signal
            self.assertEqual(c.get("/favicon.ico").status, 200)
        finally:
            helpers.cleanup(d)

    def test_local_mode_has_no_noindex(self):
        app, d = helpers.make_app()
        try:
            c = helpers.Client(app); c.login()
            r = c.get("/")
            self.assertIsNone(r.get("X-Robots-Tag"))
            self.assertNotIn('name="robots"', c.text(r))
        finally:
            helpers.cleanup(d)


if __name__ == "__main__":
    unittest.main()
