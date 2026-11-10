"""Iteration 4 drafting: every workshop, documents as source, routes in settings, hard limits, the request log.

Every model call goes to stub_model.StubModel on 127.0.0.1 (in-process), which answers per workshop with JSON
wrapped in fences, prose or a thinking block and carrying, on purpose, fields a draft must never set. No real
provider is called: the tests that need a non-local endpoint replace the transport with a mock.
"""
import json
import os
import pathlib
import re
import stat
import tempfile
import unittest
from unittest import mock

from app.tests import helpers
from app.tests.helpers import SYNTH_ID, Client, make_app, make_docx, make_private_dir, upload
from app.tests.stub_model import CANNED_WS, StubModel
from atelier_app import config, drafting, drafts

REMOTE = "https://models.example.net/v1"  # never reached: the tests make sure nothing goes there
FORBIDDEN_NAMES = {"severity", "likelihood", "decision", "status", "level", "owner", "due", "motivation", "resources",
                   "dependence", "penetration", "maturity", "trust", "critical", "treatment", "likelihood_target"}


def local(stub, **limits):
    return {"route": "local", "local": {"port": stub.port, "path": "/v1", "model": "stub-model-1",
                                        "ssh_hint": "ssh -N -L 11434:127.0.0.1:11434 user@model-host"},
            "limits": limits}


def remote(**limits):
    return {"route": "remote", "remote": {"base_url": REMOTE, "model": "remote-m"}, "limits": limits}


class SchemaTest(unittest.TestCase):
    """The schemas, the prompt files and the extractor, without the web layer."""

    def test_no_schema_field_is_a_judgement(self):
        for ws, sch in drafting.SCHEMAS.items():
            for coll, (kind, fields) in sch.items():
                self.assertFalse(set(fields) & drafting.FORBIDDEN, (ws, coll))
                self.assertFalse(set(fields) & FORBIDDEN_NAMES, (ws, coll))
        self.assertLessEqual(FORBIDDEN_NAMES, drafting.FORBIDDEN)

    def test_every_prompt_file_exists_cites_the_guide_and_its_example_matches_the_schema(self):
        for ws in ("w1", "w2", "w3", "w4", "w5"):
            text = drafting.load_prompt(ws)
            self.assertTrue(text.startswith(f"# Workshop {ws[1]} draft"), ws)
            self.assertIn("ANSSI guide EBIOS Risk Manager v1.5", " ".join(text.split()))
            self.assertRegex(text, r"guide p\.\d+", ws)
            self.assertIn("Never give", text)
            example = drafting.prompt_example(ws)
            self.assertTrue(example, ws)
            data = json.loads(example)
            self.assertEqual(set(data), set(drafting.SCHEMAS[ws]), ws)
            for coll, rows in data.items():
                kind, fields = drafting.SCHEMAS[ws][coll]
                for row in rows:
                    self.assertLessEqual(set(row), set(fields), (ws, coll, row))
                    self.assertFalse(set(row) & drafting.FORBIDDEN, (ws, coll, row))
            items = drafting.parse_items(example, ws)
            self.assertEqual(len(items), sum(len(v) for v in data.values()), ws)
            for it in items:
                self.assertFalse(set(it) & drafting.FORBIDDEN, it)

    def test_forbidden_fields_are_dropped_in_every_workshop(self):
        for ws, sch in drafting.SCHEMAS.items():
            answer = {}
            for coll, (kind, fields) in sch.items():
                row = {name: ("x" if ft in (drafting.TEXT, drafting.TEXT_REQ, drafting.REF) else
                              ["x"] if ft == drafting.REFS else [{"label": "x"}] if ft == drafting.PATHS else ft[0])
                       for name, ft in fields.items()}
                row.update({k: 4 for k in drafting.FORBIDDEN})
                answer[coll] = [row]
            for it in drafting.parse_items(json.dumps(answer), ws):
                self.assertEqual(set(it) & drafting.FORBIDDEN, set(), (ws, it))
                self.assertEqual(set(it) - {"kind"}, set(sch[drafting.KIND_COLLECTION[it["kind"]]][1]), (ws, it))

    def test_stub_answers_parse_and_lose_their_judgements(self):
        for ws, content in CANNED_WS.items():
            items = drafting.parse_items(content, ws)
            self.assertTrue(items, ws)
            for it in items:
                self.assertEqual(set(it) & drafting.FORBIDDEN, set(), (ws, it))

    def test_extractor(self):
        good = {"risk_origins": [{"origin": "Crime group", "objective": "Ransom"}]}
        ok = [json.dumps(good),
              "```json\n" + json.dumps(good) + "\n```",
              "```\n" + json.dumps(good) + "\n```",
              "Sure, here it is: " + json.dumps(good) + " Anything else?",
              "<think>I should answer {maybe} in JSON</think>" + json.dumps(good),
              "Some {text} with braces, then " + json.dumps({"note": "x"}) + " and " + json.dumps(good),
              json.dumps({"risk_origins": [{"origin": "Crime {group}", "objective": "a \"quoted\" } brace"}]})]
        for content in ok:
            items = drafting.parse_items(content, "w2")
            self.assertEqual([it["kind"] for it in items], ["risk_origin"], content)
        bad = ["", "   ", "no json at all", "```json\n{\"risk_origins\": [{\"origin\": \"x\",}]}\n```",
               '{"risk_origins": [{"origin": "x"}', '{"other": [1, 2]}', '{"risk_origins": "not a list"}',
               '{"risk_origins": [{"objective": "no origin"}]}', "[1, 2, 3]", '{"risk_origins": [null, 3, "x"]}']
        for content in bad:
            with self.assertRaises(drafting.Unusable, msg=content) as cm:
                drafting.parse_items(content, "w2")
            self.assertTrue(str(cm.exception).startswith("The model's answer could not be used"), content)

    def test_chunks_respect_the_size_and_keep_the_text(self):
        text = "\n\n".join(f"Paragraph {i} " + "word " * 50 for i in range(40))
        parts = drafting.chunks(text, 1000)
        self.assertTrue(all(len(p) <= 1000 for p in parts))
        self.assertEqual(" ".join(" ".join(parts).split()), " ".join(text.split()))
        self.assertEqual(drafting.chunks("x" * 2500, 1000), ["x" * 1000, "x" * 1000, "x" * 500])

    def test_limits_are_clamped_to_hard_ceilings(self):
        s = drafting.normalise({"route": "off", "limits": {"requests_per_minute": 10 ** 6, "max_output_tokens": 10 ** 6,
                                                           "context_tokens": 0, "max_chunks": "x"}})
        self.assertEqual(s["limits"], {"requests_per_minute": 60, "max_output_tokens": 8192, "context_tokens": 1024,
                                       "max_chunks": drafting.DEFAULT_LIMITS["max_chunks"]})

    def test_routes(self):
        self.assertEqual(drafting.normalise(None)["route"], "off")
        self.assertEqual(drafting.normalise({"route": "local", "local": {"port": 11434, "model": "m"}})["base_url"],
                         "http://127.0.0.1:11434/v1")
        for bad in ({"route": "local", "local": {"port": 0, "model": "m"}},
                    {"route": "local", "local": {"port": 11434}},
                    {"route": "local", "local": {"base_url": "http://models.example.net/v1", "model": "m"}},
                    {"route": "remote", "remote": {"base_url": "ftp://x", "model": "m"}},
                    {"route": "elsewhere"}):
            s = drafting.normalise(bad)
            self.assertEqual(s["route"], "off", bad)
            self.assertTrue(s["problem"], bad)

    def test_remote_refused_for_private_before_any_request(self):
        d = drafting.Drafter(remote())
        with mock.patch.object(drafting, "_post") as post:
            with self.assertRaises(drafting.RouteRefused) as cm:
                d.draft("w3", {"text": "x", "private": True})
            post.assert_not_called()
        self.assertIn("Nothing was sent", str(cm.exception))

    def test_rate_limiter(self):
        rl = drafting.RateLimiter()
        rl.reserve("s", 2, 3, now=100.0)
        rl.reserve("s", 1, 3, now=110.0)
        with self.assertRaises(drafting.RateLimited) as cm:
            rl.reserve("s", 1, 3, now=120.0)
        self.assertIn("at most 3 drafting requests a minute", str(cm.exception))
        rl.reserve("other", 3, 3, now=120.0)  # per study
        rl.reserve("s", 2, 3, now=160.5)  # the first two are older than 60 s
        with self.assertRaises(drafting.RateLimited):
            rl.reserve("s", 4, 3, now=1000.0)  # one draft can never need more than the limit

    def test_no_subprocess_in_the_drafting_and_settings_code(self):
        """The app shows the ssh command as a hint and never runs it (or anything else) from these modules."""
        app_dir = pathlib.Path(drafting.__file__).parent
        for name in ("drafting.py", "drafts.py", "config.py", "views_draft.py"):
            src = (app_dir / name).read_text()
            for bad in (r"\bsubprocess\b", r"\bos\.system\b", r"\bos\.popen\b", r"\bos\.exec", r"\bimport pty\b",
                        r"\bos\.spawn"):
                self.assertNotRegex(src, bad, name)


class AppDraftingTest(unittest.TestCase):
    """The web layer, with the guide example (public) and the workshop-aware stub."""

    def setUp(self):
        self.stub = StubModel(by_workshop=True, usage={"prompt_tokens": 321, "completion_tokens": 45}).__enter__()
        self.priv = make_private_dir()
        self.make(local(self.stub))

    def make(self, settings):
        if getattr(self, "d", None):
            helpers.cleanup(self.d)
        self.app, self.d = make_app(drafting_settings=settings, private_dir=self.priv)
        self.c = Client(self.app)
        self.c.login()

    def tearDown(self):
        self.stub.__exit__()
        helpers.cleanup(self.d)
        helpers.cleanup(self.priv)

    def post(self, path, form=None, page="/"):
        return self.c.post_csrf(path, form, page)

    def study(self):
        return self.c.load_example()

    def stored(self, sid):
        return json.loads((self.app.store.dir / f"{sid}.json").read_text())

    def drafts(self, sid):
        return self.app.store.load_drafts(sid)

    def page(self, sid, n):
        r = self.c.get(f"/s/{sid}/w{n}")
        self.assertEqual(r.status, 200)
        return self.c.text(r)

    def panel(self, sid, n):
        return self.page(sid, n).split('id="draft"', 1)[1].split("</section>", 1)[0]

    def log(self):
        p = self.app.draft_log
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def item(self, sid, kind):
        return next(x for x in self.drafts(sid)["items"] if x["kind"] == kind)

    # --- every panel shows the route and the model ---

    def test_every_workshop_panel_shows_route_and_model(self):
        sid = self.study()
        for n in range(1, 6):
            p = self.panel(sid, n)
            self.assertIn("route: local (this machine)", p, n)
            self.assertIn("<b>stub-model-1</b>", p, n)
            self.assertIn(f"127.0.0.1:{self.stub.port}", p, n)
            self.assertIn("ssh -N -L 11434:127.0.0.1:11434 user@model-host", p, n)
            self.assertIn("The app never runs ssh", p, n)
            self.assertIn(f'name="ws" value="{n}"', p, n)

    # --- W1 from an uploaded docx, accept all only for text ---

    def test_w1_from_a_document_and_accept_all_only_takes_text_items(self):
        r = self.c.post_csrf("/new", {"name": "Fresh", "calibration": "anssi-v1.5"})
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        upload(self.c, sid, "shop.docx", make_docx(["We take customer orders and keep a supplier price list."]))
        did = self.app.docs.list(sid)[0]["id"]
        r = self.post(f"/s/{sid}/draft", {"ws": "1", "docs": did})
        self.assertEqual((r.status, r.get("Location")), (303, f"/s/{sid}/w1?f=drafted#draft"))
        user = self.stub.requests[-1]["json"]["messages"][1]["content"]
        self.assertIn("[Document: shop.docx]\nWe take customer orders and keep a supplier price list.", user)
        kinds = [x["kind"] for x in self.drafts(sid)["items"]]
        self.assertEqual(kinds, ["business_value", "business_value", "feared_event", "feared_event"])
        r = self.post(f"/s/{sid}/draft/accept-all", {"ws": "1"})
        self.assertEqual(r.status, 303)
        st = self.stored(sid)
        self.assertEqual([b["label"] for b in st["business_values"]], ["Customer order handling", "Supplier price list"])
        self.assertEqual(st["feared_events"], [])  # needs a severity: never accepted all at once
        self.assertEqual([x["kind"] for x in self.drafts(sid)["items"]], ["feared_event", "feared_event"])
        p = self.panel(sid, 1)
        self.assertNotIn("accept-all", p)  # nothing text-only left
        fe = p.split('id="draft-D3"', 1)[1].split("</form></li>", 1)[0]
        self.assertIn('<option value="BV1" selected>', fe)  # the business value it named, matched by label
        self.assertRegex(fe, r'<select name="severity" required><option value="">\(pick a severity\)</option>')
        self.assertNotRegex(fe.split('name="severity"', 1)[1].split("</select>", 1)[0], r"selected")

    # --- W2: decision never drafted, the user picks ---

    def test_w2_risk_origin_needs_the_users_decision(self):
        sid = self.study()
        r = self.post(f"/s/{sid}/draft", {"ws": "2", "text": "Criminals and competitors are a concern."})
        self.assertEqual((r.status, r.get("Location")), (303, f"/s/{sid}/w2?f=drafted#draft"))
        ro = self.item(sid, "risk_origin")
        self.assertEqual(ro["feared_events"], ["FE1", "not-an-id"])
        for k in ("decision", "motivation", "resources", "severity"):
            self.assertNotIn(k, ro)
        p = self.panel(sid, 2)
        form = p.split(f'id="draft-{ro["id"]}"', 1)[1].split("</form></li>", 1)[0]
        self.assertRegex(form, r'<select name="decision" required><option value="">\(you pick the decision\)</option>')
        self.assertNotRegex(form.split('name="decision"', 1)[1].split("</select>", 1)[0], r'<option [^>]*\bselected>')
        self.assertIn('value="FE1" checked', form)
        self.assertNotIn("not-an-id", form.split("<fieldset>", 1)[1])  # an unknown id is not offered
        self.assertNotIn("accept-all", p)
        before = (self.app.store.dir / f"{sid}.json").read_bytes()
        form = {"origin": ro["origin"], "objective": ro["objective"], "feared_events": "FE1", "decision": ""}
        r = self.post(f"/s/{sid}/draft/{ro['id']}/accept", form)
        self.assertEqual(r.status, 400)
        self.assertIn("pick a decision", self.c.text(r))
        self.assertEqual((self.app.store.dir / f"{sid}.json").read_bytes(), before)
        r = self.post(f"/s/{sid}/draft/{ro['id']}/accept", dict(form, decision="monitoring"))
        self.assertEqual(r.status, 303)
        new = self.stored(sid)["risk_origins"][-1]
        self.assertEqual((new["origin"], new["decision"], new["feared_events"]),
                         ("Organised crime group", "monitoring", ["FE1"]))
        self.assertNotIn("motivation", new)

    # --- W3: no ratings drafted; strategic scenario severity from the engine ---

    def test_w3_stakeholders_without_ratings_and_scenario_severity_from_the_engine(self):
        sid = self.study()
        r = self.post(f"/s/{sid}/draft", {"ws": "3", "text": "We rely on a hosting provider and a courier."})
        self.assertEqual(r.status, 303)
        shs = [x for x in self.drafts(sid)["items"] if x["kind"] == "stakeholder"]
        self.assertEqual([set(x) - {"id", "batch", "state"} for x in shs], [{"kind", "name", "category"}] * 2)
        p = self.panel(sid, 3)
        self.assertIn("Courier &lt;b&gt;company&lt;/b&gt;", p)  # escaped
        self.assertNotIn("<b>company</b>", p)
        n_before = len(self.stored(sid)["stakeholders"])
        self.assertEqual(self.post(f"/s/{sid}/draft/accept-all", {"ws": "3"}).status, 303)
        st = self.stored(sid)
        added = st["stakeholders"][n_before:]
        self.assertEqual([x["name"] for x in added], ["Hosting provider", "Courier <b>company</b>"])
        for x in added:
            for k in ("dependence", "penetration", "maturity", "trust"):
                self.assertNotIn(k, x)
            self.assertFalse(x.get("critical"))
        ss = self.item(sid, "strategic_scenario")
        self.assertNotIn("severity", ss)
        form = self.panel(sid, 3).split(f'id="draft-{ss["id"]}"', 1)[1].split("</form></li>", 1)[0]
        self.assertIn('<option value="RO1" selected>', form)
        self.assertIn('value="Through the hosting provider"', form)
        self.assertIn("Direct phishing of a lab employee", form)  # the other proposed path, as a hint
        r = self.post(f"/s/{sid}/draft/{ss['id']}/accept", {
            "risk_origin": "RO1", "feared_events": "FE1", "new_path_label": "Through the hosting provider",
            "new_path_stakeholder": added[0]["id"]})
        self.assertEqual(r.status, 303)
        new = self.stored(sid)["strategic_scenarios"][-1]
        fe1 = next(x for x in st["feared_events"] if x["id"] == "FE1")
        self.assertEqual(new["severity"], fe1["severity"])  # the engine's (from FE1), the stub said 1
        self.assertEqual(new["paths"][0]["stakeholder"], added[0]["id"])

    # --- W4: likelihood never drafted ---

    def test_w4_operational_scenario_needs_the_users_likelihood(self):
        sid = self.study()
        self.assertEqual(self.post(f"/s/{sid}/draft", {"ws": "4", "text": "Remote access is used by admins."}).status, 303)
        os_ = self.item(sid, "operational_scenario")
        self.assertNotIn("likelihood", os_)
        form = self.panel(sid, 4).split(f'id="draft-{os_["id"]}"', 1)[1].split("</form></li>", 1)[0]
        self.assertIn('<option value="SS1::SS1-P1" selected>', form)
        self.assertRegex(form, r'<select name="likelihood" required><option value="">\(you pick the likelihood\)</option>')
        r = self.post(f"/s/{sid}/draft/{os_['id']}/accept", {"target": "SS1::SS1-P1", "description": os_["description"]})
        self.assertEqual(r.status, 400)
        self.assertIn("pick a likelihood", self.c.text(r))
        r = self.post(f"/s/{sid}/draft/{os_['id']}/accept", {"target": "SS1::SS1-P1", "description": os_["description"],
                                                             "likelihood": "2"})
        self.assertEqual(r.status, 303)
        new = self.stored(sid)["operational_scenarios"][-1]
        self.assertEqual((new["likelihood"], new["strategic_scenario"], new["path"]), (2, "SS1", "SS1-P1"))

    # --- W5: status, owner and due never drafted ---

    def test_w5_measure_needs_the_users_status_and_has_no_owner_or_due(self):
        sid = self.study()
        self.assertEqual(self.post(f"/s/{sid}/draft", {"ws": "5", "text": "Backups exist but are online."}).status, 303)
        ms = [x for x in self.drafts(sid)["items"] if x["kind"] == "measure"]
        self.assertEqual(len(ms), 2)
        for x in ms:
            for k in ("status", "owner", "due", "treatment"):
                self.assertNotIn(k, x)
        form = self.panel(sid, 5).split(f'id="draft-{ms[1]["id"]}"', 1)[1].split("</form></li>", 1)[0]
        self.assertIn('value="R1" checked', form)
        self.assertNotIn("R99", form)
        self.assertRegex(form, r'<select name="status" required><option value="">\(you pick the status\)</option>')
        self.assertIn('name="owner" value=""', form)
        self.assertIn('name="due" value=""', form)
        r = self.post(f"/s/{sid}/draft/{ms[0]['id']}/accept", {"label": ms[0]["label"], "risks": "R1"})
        self.assertEqual(r.status, 400)
        r = self.post(f"/s/{sid}/draft/{ms[0]['id']}/accept", {"label": ms[0]["label"], "risks": "R1", "status": "planned"})
        self.assertEqual(r.status, 303)
        new = self.stored(sid)["measures"][-1]
        self.assertEqual(new, {"id": new["id"], "label": "Offline backups of the production servers", "risks": ["R1"],
                               "status": "planned"})
        self.assertEqual(self.post(f"/s/{sid}/draft/{ms[1]['id']}/reject").status, 303)
        self.assertEqual([x for x in self.drafts(sid)["items"] if x["kind"] == "measure"], [])

    def test_a_new_draft_does_not_repeat_pending_or_accepted_items(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"ws": "5", "text": "x"})
        first = [x["id"] for x in self.drafts(sid)["items"]]
        self.assertEqual(len(first), 2)
        r = self.post(f"/s/{sid}/draft", {"ws": "5", "text": "x"})
        self.assertEqual(r.get("Location"), f"/s/{sid}/w5?f=drafted-nothing-new#draft")
        self.assertEqual([x["id"] for x in self.drafts(sid)["items"]], first)
        ms = self.drafts(sid)["items"]
        self.post(f"/s/{sid}/draft/{ms[0]['id']}/accept", {"label": ms[0]["label"], "risks": "R1", "status": "planned"})
        self.post(f"/s/{sid}/draft/{ms[1]['id']}/reject")
        self.post(f"/s/{sid}/draft", {"ws": "5", "text": "x"})
        again = self.drafts(sid)["items"]  # the accepted one is in the study: not proposed again; the rejected one is
        self.assertEqual([x["label"] for x in again], [ms[1]["label"]])

    # --- the route policy with documents ---

    def test_private_study_with_documents_and_the_remote_route_is_refused(self):
        self.make(remote())
        r = self.c.post_csrf("/new", {"name": "Private", "calibration": SYNTH_ID})
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        marker = "INVENTED-PRIVATE-MARKER-" + os.urandom(4).hex()
        upload(self.c, sid, "private.txt", marker.encode())
        did = self.app.docs.list(sid)[0]["id"]
        self.assertIn("Refused: this study is private", self.panel(sid, 2))  # said before anything is sent
        with mock.patch.object(drafting, "_post") as post:
            r = self.post(f"/s/{sid}/draft", {"ws": "2", "docs": did})
            post.assert_not_called()
        self.assertEqual(r.status, 403)
        self.assertIn("Nothing was sent", self.c.text(r))
        self.assertEqual(self.drafts(sid)["items"], [])
        log = self.log()
        self.assertEqual([x["outcome"] for x in log], ["refused-route"])
        self.assertNotIn(marker, self.app.draft_log.read_text())
        # the same study through the local route works
        self.make(local(self.stub))

    def test_confidential_flag_also_refuses_the_remote_route(self):
        self.make(remote())
        sid = self.study()
        self.post(f"/s/{sid}/confidential", {"confidential": "yes"})
        with mock.patch.object(drafting, "_post") as post:
            self.assertEqual(self.post(f"/s/{sid}/draft", {"ws": "5", "text": "x"}).status, 403)
            post.assert_not_called()

    def test_public_study_may_use_the_remote_route(self):
        self.make(remote())
        sid = self.study()
        reply = json.dumps({"model": "remote-m", "choices": [{"message": {"content": CANNED_WS["w5"]}}]}).encode()
        with mock.patch.object(drafting, "_post", return_value=(200, reply)) as post:
            r = self.post(f"/s/{sid}/draft", {"ws": "5", "text": "x"})
        self.assertEqual(r.status, 303)
        self.assertEqual(post.call_args[0][0], REMOTE + "/chat/completions")
        self.assertEqual(self.drafts(sid)["batches"][-1]["route"], "remote")

    # --- hard limits ---

    def test_rate_limit_per_study(self):
        self.make(local(self.stub, requests_per_minute=2))
        sid = self.study()
        for _ in range(2):
            self.assertEqual(self.post(f"/s/{sid}/draft", {"ws": "2", "text": "x"}).status, 303)
        n = len(self.stub.requests)
        r = self.post(f"/s/{sid}/draft", {"ws": "2", "text": "x"})
        self.assertEqual(r.status, 429)
        self.assertIn("at most 2 drafting requests a minute", self.c.text(r))
        self.assertEqual(len(self.stub.requests), n)
        self.assertEqual(self.log()[-1]["outcome"], "rate-limited")
        other = self.study()  # another study has its own budget
        self.assertEqual(self.post(f"/s/{other}/draft", {"ws": "2", "text": "x"}).status, 303)

    def test_max_output_tokens_is_sent_and_capped(self):
        self.make(local(self.stub, max_output_tokens=10 ** 6))
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"ws": "2", "text": "x"})
        body = self.stub.requests[-1]["json"]
        self.assertEqual(body["max_tokens"], drafting.CEILINGS["max_output_tokens"])
        self.assertEqual((body["temperature"], body["stream"]), (0, False))
        self.make(local(self.stub, max_output_tokens=300))
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"ws": "2", "text": "x"})
        self.assertEqual(self.stub.requests[-1]["json"]["max_tokens"], 300)

    def test_chunks_and_the_per_draft_cap(self):
        self.make(local(self.stub, context_tokens=2048, max_output_tokens=256, max_chunks=3, requests_per_minute=20))
        r = self.c.post_csrf("/new", {"name": "Long", "calibration": "anssi-v1.5"})
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        long_text = "\n\n".join(f"Paragraph {i}: " + "invented words " * 40 for i in range(60))
        upload(self.c, sid, "long.md", long_text.encode())
        did = self.app.docs.list(sid)[0]["id"]
        n0 = len(self.stub.requests)
        self.assertEqual(self.post(f"/s/{sid}/draft", {"ws": "1", "docs": did}).status, 303)
        sent = self.stub.requests[n0:]
        self.assertEqual(len(sent), 3)
        budget = drafting.chunk_budget(self.app.drafter.settings["limits"],
                                       len(drafting.load_prompt("w1")) + len(drafts.study_summary(self.stored(sid), 1)))
        for i, req in enumerate(sent, 1):
            user = req["json"]["messages"][1]["content"]
            self.assertIn(f"Source text, part {i} of 3:", user)
            self.assertLessEqual(len(user.split(f"part {i} of 3:\n", 1)[1]), budget)
        b = self.drafts(sid)["batches"][-1]
        self.assertEqual(b["requests"], 3)
        self.assertLess(b["covered"], b["total"])
        self.assertIn("Only part of the selected text was sent", self.panel(sid, 1))
        # four chunk answers, the same four proposals: merged, not repeated
        self.assertEqual(len(self.drafts(sid)["items"]), 4)

    # --- the log ---

    def test_log_has_every_request_and_no_document_text(self):
        r = self.c.post_csrf("/new", {"name": "Logged", "calibration": "anssi-v1.5"})
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        marker = "UNIQUE-DOC-TEXT-" + os.urandom(6).hex()
        upload(self.c, sid, "src.txt", f"Line one {marker} line two.".encode())
        did = self.app.docs.list(sid)[0]["id"]
        self.post(f"/s/{sid}/draft", {"ws": "1", "docs": did, "text": "pasted " + marker})
        self.assertIn(marker, self.stub.requests[-1]["json"]["messages"][1]["content"])  # it was sent...
        raw = self.app.draft_log.read_text()
        self.assertNotIn(marker, raw)  # ...but never logged
        self.assertNotIn("Line one", raw)
        self.assertNotIn("Customer order handling", raw)  # nor the answer
        self.assertEqual(stat.S_IMODE(os.stat(self.app.draft_log).st_mode), 0o600)
        rec = self.log()[-1]
        self.assertEqual({k: rec[k] for k in ("study", "workshop", "route", "model", "outcome", "prompt_tokens",
                                              "completion_tokens", "tokens_from", "documents", "request", "of")},
                         {"study": sid, "workshop": "w1", "route": "local", "model": "stub-model-1", "outcome": "ok",
                          "prompt_tokens": 321, "completion_tokens": 45, "tokens_from": "endpoint", "documents": 1,
                          "request": 1, "of": 1})
        self.assertRegex(rec["time"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(set(rec) - set(drafting.DraftLog.FIELDS), set())

    # --- unusable answers ---

    def test_unusable_answer_says_so_and_stores_nothing(self):
        for content in ("I am sorry, I cannot help with that.", '```json\n{"business_values": [{"label": "x",}]}\n```'):
            stub = StubModel(content=content).__enter__()
            try:
                self.make(local(stub))
                sid = self.study()
                before = (self.app.store.dir / f"{sid}.json").read_bytes()
                r = self.post(f"/s/{sid}/draft", {"ws": "1", "text": "orders"})
                self.assertEqual(r.status, 502)
                self.assertIn("The model&#x27;s answer could not be used", self.c.text(r))
                self.assertFalse((self.app.store.drafts / f"{sid}.json").exists())
                self.assertEqual((self.app.store.dir / f"{sid}.json").read_bytes(), before)
                self.assertEqual(self.log()[-1]["outcome"], "unusable")
                self.assertNotIn("sorry", self.app.draft_log.read_text())
            finally:
                stub.__exit__()

    def test_raw_answers_are_not_stored(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"ws": "2", "text": "x"})
        raw = (self.app.store.drafts / f"{sid}.json").read_text()
        self.assertNotIn("Hope it helps", raw)
        self.assertNotIn("Here are the pairs", raw)

    # --- CSRF and escaping on the new forms ---

    def test_csrf_on_every_new_post_route(self):
        sid = self.study()
        self.post(f"/s/{sid}/draft", {"ws": "3", "text": "x"})
        did = self.drafts(sid)["items"][0]["id"]
        upload(self.c, sid, "a.txt", b"x")
        doc = self.app.docs.list(sid)[0]["id"]
        n = len(self.stub.requests)
        for path, form in (("/settings", {"route": "off"}), (f"/s/{sid}/draft", {"ws": "3", "text": "x"}),
                           (f"/s/{sid}/draft/accept-all", {"ws": "3"}), (f"/s/{sid}/draft/{did}/accept", {"name": "x"}),
                           (f"/s/{sid}/draft/clear", {"ws": "3"}), (f"/s/{sid}/docs/{doc}/delete", {})):
            for bad in (None, "wrong"):
                f = dict(form)
                if bad:
                    f["csrf"] = bad
                self.assertEqual(self.c.post(path, f).status, 403, (path, bad))
        self.assertEqual(len(self.stub.requests), n)
        self.assertEqual(len(self.app.docs.list(sid)), 1)
        self.assertFalse(config.settings_path(self.d).exists())

    def test_draft_text_and_hint_are_escaped(self):
        payload = '<script>alert("x")</script>'
        stub = StubModel(content=json.dumps({"measures": [{"label": payload, "risks": ["R1"]}]})).__enter__()
        try:
            s = local(stub)
            s["local"]["ssh_hint"] = 'ssh -L 1:2:3 "<img src=x onerror=alert(1)>"'
            self.make(s)
            sid = self.study()
            self.post(f"/s/{sid}/draft", {"ws": "5", "text": payload})
            p = self.page(sid, 5)
            self.assertNotIn("<script>alert", p)
            self.assertNotIn("<img src=x", p)
            self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", p)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", p)
        finally:
            stub.__exit__()


class SettingsPageTest(unittest.TestCase):
    def setUp(self):
        self.app, self.d = make_app()
        self.c = Client(self.app)
        self.c.login()
        self.keydir = pathlib.Path(tempfile.mkdtemp())
        self.key = self.keydir / "k"
        self.key.write_text("sk-test-" + os.urandom(8).hex())
        self.key.chmod(0o600)

    def tearDown(self):
        helpers.cleanup(self.d)
        helpers.cleanup(self.keydir)

    def form(self, **kw):
        f = {"route": "local", "local_port": "11434", "local_path": "/v1", "local_model": "qwen-test", "local_key_file": "",
             "local_ssh_hint": "ssh -N -L 11434:127.0.0.1:11434 user@model-host", "remote_base_url": "",
             "remote_model": "", "remote_key_file": "", "limits_requests_per_minute": "4",
             "limits_max_output_tokens": "1024", "limits_context_tokens": "16384", "limits_max_chunks": "2"}
        f.update(kw)
        return f

    def test_off_by_default_and_the_file_path_is_shown(self):
        page = self.c.text(self.c.get("/settings"))
        self.assertIn("route: off", page)
        self.assertIn(str(config.settings_path(self.d)), page)
        self.assertIn('value="off" checked', page)

    def test_save_writes_a_0600_file_and_reloads_the_route(self):
        r = self.c.post_csrf("/settings", self.form(), "/settings")
        self.assertEqual((r.status, r.get("Location")), (303, "/settings?f=settings-saved"))
        path = config.settings_path(self.d)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        data = json.loads(path.read_text())
        self.assertEqual(data["route"], "local")
        self.assertEqual(data["local"]["port"], 11434)
        self.assertEqual(data["limits"], {"requests_per_minute": 4, "max_output_tokens": 1024, "context_tokens": 16384,
                                          "max_chunks": 2})
        self.assertEqual(self.app.drafter.settings["base_url"], "http://127.0.0.1:11434/v1")
        sid = self.c.load_example()
        panel = self.c.text(self.c.get(f"/s/{sid}/w3"))
        self.assertIn("<b>qwen-test</b>", panel)
        self.assertIn("at most 4 requests a minute", panel)

    def test_refused_form_keeps_input_and_says_why(self):
        r = self.c.post_csrf("/settings", self.form(local_port="99999", local_model="kept-model"), "/settings")
        self.assertEqual(r.status, 400)
        t = self.c.text(r)
        self.assertIn('value="kept-model"', t)
        self.assertRegex(t, r'name="local_port" value="99999"[^>]*>\s*<span class="field-error" role="alert">between 1 and 65535')
        self.assertFalse(config.settings_path(self.d).exists())
        r = self.c.post_csrf("/settings", self.form(route="remote", remote_base_url="ftp://x", remote_model="m"), "/settings")
        self.assertEqual(r.status, 400)
        self.assertIn("an http:// or https:// URL", self.c.text(r))

    def test_key_file_must_be_0600_and_is_never_shown(self):
        self.key.chmod(0o644)
        r = self.c.post_csrf("/settings", self.form(route="remote", remote_base_url=REMOTE, remote_model="m",
                                                     remote_key_file=str(self.key)), "/settings")
        self.assertEqual(r.status, 400)
        self.assertIn("mode 600", self.c.text(r))
        self.key.chmod(0o600)
        r = self.c.post_csrf("/settings", self.form(route="remote", remote_base_url=REMOTE, remote_model="m",
                                                     remote_key_file=str(self.key)), "/settings")
        self.assertEqual(r.status, 303)
        secret = self.key.read_text()
        self.assertNotIn(secret, config.settings_path(self.d).read_text())
        self.assertNotIn(secret, self.c.text(self.c.get("/settings")))

    def test_loose_file_mode_is_flagged(self):
        self.c.post_csrf("/settings", self.form(), "/settings")
        config.settings_path(self.d).chmod(0o644)
        self.assertIn("it should be 600", self.c.text(self.c.get("/settings")))

    def test_ssh_hint_is_only_text(self):
        hint = "ssh -N -L 11434:127.0.0.1:11434 user@model-host; touch /tmp/should-never-exist"
        with mock.patch("subprocess.run") as run, mock.patch("subprocess.Popen") as popen, mock.patch("os.system") as sys_:
            self.c.post_csrf("/settings", self.form(local_ssh_hint=hint), "/settings")
            sid = self.c.load_example()
            self.c.get(f"/s/{sid}/w2")
            run.assert_not_called()
            popen.assert_not_called()
            sys_.assert_not_called()
        self.assertEqual(json.loads(config.settings_path(self.d).read_text())["local"]["ssh_hint"], hint)


if __name__ == "__main__":
    unittest.main()
