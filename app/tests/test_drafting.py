"""Drafting scaffold: adapter, route policy, accept/reject flow, no level from a draft, key never logged, CSRF.

Every model call goes to stub_model.StubModel on 127.0.0.1 (in-process). No real provider is called: the one test
that needs a non-local endpoint replaces the transport with a mock.
"""
import contextlib
import io
import json
import logging
import os
import pathlib
import re
import secrets
import shutil
import tempfile
import unittest
from unittest import mock

from app.tests import helpers
from app.tests.helpers import SYNTH_ID, Client, make_app, make_private_dir
from app.tests.stub_model import CANNED, StubModel
from atelier_app import config, drafting

REMOTE = "http://203.0.113.10:8080/v1"  # TEST-NET-3, never reached: the tests make sure no request goes there
ALLOWED_KEYS = {"id", "kind", "label", "nature", "criterion", "business_value", "batch", "state"}


def settings(base_url, key_file=""):
    return {"backend": "openai-compatible", "base_url": base_url, "model": "stub-model-1", "key_file": key_file}


class RoutePolicyTest(unittest.TestCase):
    """drafting.route_for and Drafter.draft, without the web layer."""

    def test_privacy_study_refused_on_a_non_local_endpoint_and_nothing_sent(self):
        for url in (REMOTE, "https://models.example.net/v1", "http://127.0.0.1.example.net/v1",
                    "http://127.0.0.1@models.example.net/v1", "http://[2001:db8::1]:8080/v1"):
            d = drafting.Drafter(settings(url))
            with mock.patch.object(drafting, "_post") as post:
                with self.assertRaises(drafting.RouteRefused) as cm:
                    d.draft("w1-values-events", {"text": "some text", "private": True})
                post.assert_not_called()
            self.assertIn("this study is private", str(cm.exception))
            self.assertIn("Nothing was sent", str(cm.exception))

    def test_public_study_may_use_a_non_local_endpoint(self):
        reply = json.dumps({"model": "m", "choices": [{"message": {"content": json.dumps(CANNED)}}]}).encode()
        d = drafting.Drafter(settings(REMOTE))
        with mock.patch.object(drafting, "_post", return_value=(200, reply)) as post:
            out = d.draft("w1-values-events", {"text": "some text", "private": False})
        post.assert_called_once()
        self.assertEqual(post.call_args[0][0], REMOTE + "/chat/completions")
        self.assertEqual(out["route"], "remote")

    def test_local_endpoints(self):
        for url in ("http://127.0.0.1:9/v1", "http://localhost:9/v1", "http://[::1]:9/v1"):
            self.assertTrue(drafting.is_local_endpoint(url), url)
            self.assertEqual(drafting.route_for(drafting.normalise(settings(url)), True), "local")
        self.assertFalse(drafting.is_local_endpoint("http://127.0.0.2/v1"))  # not one of the three names

    def test_unknown_privacy_is_treated_as_private(self):
        d = drafting.Drafter(settings(REMOTE))
        with mock.patch.object(drafting, "_post") as post:
            with self.assertRaises(drafting.RouteRefused):
                d.draft("w1-values-events", {"text": "x"})
            post.assert_not_called()

    def test_off_is_the_default_and_sends_nothing(self):
        for s in (None, {}, {"backend": "off"}, {"backend": "something-else"},
                  {"backend": "openai-compatible", "base_url": "ftp://x/", "model": "m"},
                  {"backend": "openai-compatible", "base_url": "http://127.0.0.1:9/v1"}):
            d = drafting.Drafter(s)
            self.assertEqual(d.settings["route"], "off", s)
            with mock.patch.object(drafting, "_post") as post:
                with self.assertRaises(drafting.DraftError) as cm:
                    d.draft("w1-values-events", {"text": "x", "private": False})
                post.assert_not_called()
            self.assertIn("drafting is off", str(cm.exception))

    def test_no_level_in_parsed_items(self):
        items = drafting.parse_items("Here you are:\n```json\n" + json.dumps(CANNED) + "\n```")
        self.assertEqual(len(items), 4)
        for it in items:
            self.assertLessEqual(set(it), ALLOWED_KEYS, it)
            for k in ("severity", "likelihood", "level", "id"):
                self.assertNotIn(k, it)
        self.assertEqual(items[3]["criterion"], "integrity")
        for bad in ("no json here", '{"business_values": "x"}'):  # nothing usable: refused, never an empty draft
            with self.assertRaises(drafting.Unusable):
                drafting.parse_items(bad)

    def test_settings_file(self):
        d = tempfile.mkdtemp()
        try:
            self.assertEqual(config.drafting_settings(d), {"route": "off"})
            pathlib.Path(d, "drafting.json").write_text("{bad")
            self.assertEqual(config.drafting_settings(d)["route"], "off")
            pathlib.Path(d, "drafting.json").write_text(json.dumps(settings("http://127.0.0.1:9/v1", "~/k")))
            s = config.drafting_settings(d)
            self.assertEqual(s["base_url"], "http://127.0.0.1:9/v1")
            self.assertFalse(s["key_file"].startswith("~"))
        finally:
            shutil.rmtree(d)

    def test_proxy_settings_ignored_and_redirects_refused(self):
        with StubModel() as stub, mock.patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:9", "HTTP_PROXY":
                                                               "http://127.0.0.1:9", "no_proxy": "", "NO_PROXY": ""}):
            out = drafting.Drafter(settings(stub.base_url)).draft("w1-values-events", {"text": "t", "private": True})
            self.assertEqual(len(out["items"]), 4)
        with StubModel() as target, StubModel(status=302) as stub:
            target_url = target.base_url + "/chat/completions"
            stub.location = target_url
            with self.assertRaises(drafting.EndpointError) as cm:
                drafting.Drafter(settings(stub.base_url)).draft("w1-values-events", {"text": "t", "private": True})
            self.assertIn("HTTP 302", str(cm.exception))
            self.assertEqual(len(stub.requests), 1)
            self.assertEqual(target.requests, [])


class DraftingAppTest(unittest.TestCase):
    """The W1 "Draft from text" box against the stub, through App.handle()."""

    def setUp(self):
        self.priv = make_private_dir()
        self.keydir = pathlib.Path(tempfile.mkdtemp(prefix="atelier-key-"))
        self.key = "sk-test-" + secrets.token_hex(16)
        self.keyfile = self.keydir / "model.key"
        self.keyfile.write_text(self.key + "\n")
        self.keyfile.chmod(0o600)
        self.stub = StubModel().__enter__()
        self.make(settings(self.stub.base_url, str(self.keyfile)))

    def make(self, s):
        if getattr(self, "d", None):
            helpers.cleanup(self.d)
        self.app, self.d = make_app(private_dir=self.priv, drafting_settings=s)
        self.c = Client(self.app)
        self.c.login()

    def tearDown(self):
        self.stub.__exit__()
        helpers.cleanup(self.d)
        shutil.rmtree(self.priv, ignore_errors=True)
        shutil.rmtree(self.keydir, ignore_errors=True)
        os.environ.pop("ATELIER_PRIVATE_DIR", None)

    def study(self, cal="anssi-v1.5", name="Draft study"):
        r = self.c.post_csrf("/new", {"name": name, "calibration": cal})
        return helpers.SID_RE.search(r.get("Location")).group(1)

    def drafts(self, sid):
        return self.app.store.load_drafts(sid)

    def post(self, path, form=None, page=None):
        return self.c.post_csrf(path, form or {}, page=page or "/")

    def w1(self, sid):
        r = self.c.get(f"/s/{sid}/w1")
        self.assertEqual(r.status, 200)
        return self.c.text(r)

    # --- happy path ---

    def test_draft_lists_items_marked_draft_and_changes_nothing_in_the_study(self):
        sid = self.study()
        before = (self.app.store.dir / f"{sid}.json").read_bytes()
        r = self.post(f"/s/{sid}/draft", {"text": "We take customer orders and buy from suppliers."})
        self.assertEqual((r.status, r.get("Location")), (303, f"/s/{sid}/w1?f=drafted#draft"))
        self.assertEqual((self.app.store.dir / f"{sid}.json").read_bytes(), before)
        self.assertEqual(len(self.stub.requests), 1)
        sent = self.stub.requests[0]
        self.assertEqual(sent["path"], "/v1/chat/completions")
        self.assertEqual(sent["headers"].get("Authorization"), "Bearer " + self.key)
        user = sent["json"]["messages"][1]["content"]  # the study summary, then the pasted text
        self.assertTrue(user.startswith("Study so far (ids you may refer to):\nStudy: "), user[:80])
        self.assertTrue(user.endswith("[Pasted text]\nWe take customer orders and buy from suppliers."), user[-80:])
        d = self.drafts(sid)
        self.assertEqual([x["id"] for x in d["items"]], ["D1", "D2", "D3", "D4"])
        self.assertEqual(d["batches"][0]["model"], "stub-model-1")
        self.assertEqual(d["batches"][0]["route"], "local")
        page = self.w1(sid)
        panel = page.split('id="draft"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(panel.count('<span class="badge draft">draft</span>'), 4)
        self.assertIn("Customer order handling", panel)
        self.assertIn("stub-model-1", panel)

    # --- no draft sets a level ---

    def test_no_draft_sets_a_level(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"text": "orders"})
        for it in self.drafts(sid)["items"]:
            self.assertLessEqual(set(it), ALLOWED_KEYS, it)
        # accept the business value, then look at the feared event's accept form: no severity pre-selected
        self.assertEqual(self.post(f"/s/{sid}/draft/D1/accept", {"label": "Customer order handling",
                                                                  "nature": "process"}).status, 303)
        page = self.w1(sid)
        form = page.split(f'action="/s/{sid}/draft/D3/accept"', 1)[1].split("</form>", 1)[0]
        sev = re.search(r'<select name="severity" required>(.*?)</select>', form, re.S).group(1)
        self.assertNotIn(" selected", sev)
        self.assertTrue(sev.startswith('<option value="">(pick a severity)</option>'))
        self.assertIn('<option value="BV1" selected>', form)  # the business value it proposed, matched by label
        # accepting without a severity is refused, with the input kept and the message next to the field
        before = (self.app.store.dir / f"{sid}.json").read_bytes()
        r = self.post(f"/s/{sid}/draft/D3/accept", {"business_value": "BV1", "label": "Orders stopped (edited)",
                                                     "criterion": "availability", "severity": ""})
        self.assertEqual(r.status, 400)
        self.assertEqual((self.app.store.dir / f"{sid}.json").read_bytes(), before)
        t = self.c.text(r)
        item = t.split('id="draft-D3"', 1)[1].split("</li>", 1)[0]
        self.assertIn('value="Orders stopped (edited)"', item)
        self.assertRegex(item, r'<select name="severity" required>.*?</select><span class="field-error" role="alert">'
                               r'pick a severity</span>')
        # the user's pick is what is stored: 2, while the stub's answer said 4
        r = self.post(f"/s/{sid}/draft/D3/accept", {"business_value": "BV1", "label": "Orders stopped (edited)",
                                                     "criterion": "availability", "severity": "2"})
        self.assertEqual(r.status, 303)
        st = self.app.store.load(sid)
        self.assertEqual(st["feared_events"], [{"id": "FE1", "business_value": "BV1", "label": "Orders stopped (edited)",
                                                "criterion": "availability", "severity": 2}])
        self.assertEqual(st["risks"], [])
        self.assertNotIn("level", json.dumps(st))

    # --- accept / reject flow ---

    def test_accept_reject_and_clear(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"text": "orders"})
        r = self.post(f"/s/{sid}/draft/D2/accept", {"label": "Supplier price list (edited)", "nature": "information",
                                                     "owner": "Purchasing"})
        self.assertEqual(r.status, 303)
        self.assertIn("f=draft-accepted&hl=BV1", r.get("Location"))
        st = self.app.store.load(sid)
        self.assertEqual(st["business_values"], [{"id": "BV1", "label": "Supplier price list (edited)",
                                                  "nature": "information", "owner": "Purchasing"}])
        self.assertEqual([x["id"] for x in self.drafts(sid)["items"]], ["D1", "D3", "D4"])
        r = self.post(f"/s/{sid}/draft/D1/reject")
        self.assertEqual(r.status, 303)
        self.assertEqual([x["id"] for x in self.drafts(sid)["items"]], ["D3", "D4"])
        self.assertEqual(self.app.store.load(sid), st)  # reject changes nothing in the study
        self.assertEqual(self.post(f"/s/{sid}/draft/D1/reject").status, 404)
        # the Reject button of an item's form posts the same form (with its CSRF field) to the reject route
        item = self.w1(sid).split('id="draft-D4"', 1)[1].split("</li>", 1)[0]
        self.assertIn(f'formaction="/s/{sid}/draft/D4/reject" formnovalidate>Reject</button>', item)
        self.assertIn('name="csrf"', item.split(f'formaction="/s/{sid}/draft/D4/reject"')[0])
        self.assertEqual(self.post(f"/s/{sid}/draft/D1/accept", {"label": "x"}).status, 404)
        self.assertEqual(self.post(f"/s/{sid}/draft/clear").status, 303)
        self.assertEqual(self.drafts(sid)["items"], [])
        self.assertFalse((self.app.store.drafts / f"{sid}.json").exists())
        # after "reject all" the draft file is gone, so numbering starts again
        self.post(f"/s/{sid}/draft", {"text": "again"})
        self.assertEqual(self.drafts(sid)["items"][0]["id"], "D1")

    def test_feared_event_draft_needs_a_business_value_first(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"text": "orders"})
        item = self.w1(sid).split('id="draft-D3"', 1)[1].split("</li>", 1)[0]
        self.assertIn("Accept or add a business value first.", item)
        self.assertNotIn("/accept", item)

    def test_drafts_are_kept_out_of_the_study_file_and_exports(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"text": "orders"})
        exp = self.c.get(f"/s/{sid}/export.json")
        self.assertNotIn("Customer order handling", exp.body.decode())
        self.assertNotIn("Customer order handling", (self.app.store.dir / f"{sid}.json").read_text())
        self.post(f"/s/{sid}/delete")
        self.assertFalse((self.app.store.drafts / f"{sid}.json").exists())

    # --- route policy through the app ---

    def test_privacy_study_with_a_non_local_endpoint_refused(self):
        self.make(settings(REMOTE))
        for sid in (self.study(SYNTH_ID, "Private by calibration"), self.study(name="Confidential")):
            if self.app.store.load(sid)["study"]["calibration"] != SYNTH_ID:
                self.post(f"/s/{sid}/confidential", {"confidential": "yes"})
            with mock.patch.object(drafting, "_post") as post:
                r = self.post(f"/s/{sid}/draft", {"text": "secret plans"})
                post.assert_not_called()
            self.assertEqual(r.status, 403)
            t = self.c.text(r)
            self.assertIn("Refused: this study is private", t)
            self.assertIn("secret plans</textarea>", t)  # the pasted text is kept
            self.assertEqual(self.drafts(sid)["items"], [])
            page = self.w1(sid)
            self.assertIn("Refused: this study is private", page)  # said before anyone pastes anything

    def test_privacy_study_with_the_local_stub_works(self):
        sid = self.study(SYNTH_ID)
        r = self.post(f"/s/{sid}/draft", {"text": "orders"})
        self.assertEqual(r.status, 303)
        self.assertEqual(self.drafts(sid)["batches"][0]["route"], "local")
        self.assertIn("its documents and drafts may only go to the local route", self.w1(sid))

    def test_public_study_with_a_non_local_endpoint_goes_through(self):
        self.make(settings(REMOTE))
        sid = self.study()
        reply = json.dumps({"model": "remote-m", "choices": [{"message": {"content": json.dumps(CANNED)}}]}).encode()
        with mock.patch.object(drafting, "_post", return_value=(200, reply)) as post:
            r = self.post(f"/s/{sid}/draft", {"text": "orders"})
        self.assertEqual(r.status, 303)
        self.assertEqual(post.call_args[0][0], REMOTE + "/chat/completions")
        self.assertEqual(self.drafts(sid)["batches"][0]["route"], "remote")

    def test_off_by_default(self):
        self.make({"backend": "off"})
        sid = self.study()
        self.assertIn("Drafting is off", self.w1(sid))
        with mock.patch.object(drafting, "_post") as post:
            r = self.post(f"/s/{sid}/draft", {"text": "orders"})
            post.assert_not_called()
        self.assertEqual(r.status, 400)
        self.assertIn("Drafting is off; set a route in Settings", self.c.text(r))

    # --- the key ---

    def test_key_file_never_logged_or_shown(self):
        sid = self.study()
        err, log = io.StringIO(), io.StringIO()
        handler = logging.StreamHandler(log)
        logging.getLogger().addHandler(handler)
        bodies = []
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
                bodies.append(self.c.text(self.post(f"/s/{sid}/draft", {"text": "ok"})))
                bodies.append(self.w1(sid))
                for status in (401, 500):
                    self.stub.status = status
                    r = self.post(f"/s/{sid}/draft", {"text": "fails"})
                    self.assertEqual(r.status, 502)
                    bodies.append(self.c.text(r))
                self.stub.status = 200
                self.stub.content = "not json at all"
                bodies.append(self.c.text(self.post(f"/s/{sid}/draft", {"text": "garbled"})))
                self.make(settings("http://127.0.0.1:9/v1", str(self.keyfile)))  # nothing listens on port 9
                sid2 = self.study()
                r = self.post(f"/s/{sid2}/draft", {"text": "unreachable"})
                self.assertEqual(r.status, 502)
                bodies.append(self.c.text(r))
                self.keyfile.chmod(0o644)
                n = len(self.stub.requests)
                self.make(settings(self.stub.base_url, str(self.keyfile)))
                sid3 = self.study()
                r = self.post(f"/s/{sid3}/draft", {"text": "loose key file"})
                self.assertEqual(r.status, 400)
                self.assertIn("chmod 600", self.c.text(r))
                self.assertEqual(len(self.stub.requests), n)  # a loose key file stops the call before it is made
                bodies.append(self.c.text(r))
        finally:
            logging.getLogger().removeHandler(handler)
        captured = err.getvalue() + log.getvalue()
        self.assertEqual(self.stub.requests[0]["headers"].get("Authorization"), "Bearer " + self.key)
        for b in bodies:
            self.assertNotIn(self.key, b)
            self.assertNotIn(str(self.keyfile), b)
        self.assertNotIn(self.key, captured)
        self.assertNotIn(str(self.keyfile), captured)
        for p in pathlib.Path(self.d).rglob("*"):
            if p.is_file():
                self.assertNotIn(self.key.encode(), p.read_bytes(), p.name)

    # --- CSRF and escaping ---

    def test_csrf_on_every_drafting_and_calibration_post(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"text": "orders"})
        n = len(self.stub.requests)
        before = ((self.app.store.dir / f"{sid}.json").read_bytes(), json.dumps(self.drafts(sid)))
        studies = len(self.app.store.list())
        for path, form in ((f"/s/{sid}/draft", {"text": "x"}), (f"/s/{sid}/draft/D1/accept", {"label": "x"}),
                           (f"/s/{sid}/draft/D1/reject", {}), (f"/s/{sid}/draft/clear", {}),
                           (f"/s/{sid}/confidential", {"confidential": "yes"}),
                           (f"/s/{sid}/duplicate", {"calibration": SYNTH_ID})):
            for bad in (None, "wrong-token"):
                f = dict(form)
                if bad:
                    f["csrf"] = bad
                r = self.c.post(path, f)
                self.assertEqual(r.status, 403, path)
        self.assertEqual(len(self.stub.requests), n)
        self.assertEqual(((self.app.store.dir / f"{sid}.json").read_bytes(), json.dumps(self.drafts(sid))), before)
        self.assertEqual(len(self.app.store.list()), studies)

    def test_drafted_text_is_escaped(self):
        self.stub.content = json.dumps({"business_values": [{"label": '<script>alert("x")</script>', "nature": "process"}],
                                        "feared_events": []})
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"text": "x"})
        page = self.w1(sid)
        self.assertNotIn('<script>alert("x")', page)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", page)


if __name__ == "__main__":
    unittest.main()
