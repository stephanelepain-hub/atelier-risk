"""The quick path through the in-process client: home, the four screens, saving, the result page and the export."""
import html as html_mod
import io
import json
import pathlib
import re
import unittest
from html.parser import HTMLParser

from app.tests import helpers
from app.tests.helpers import HAVE_OPENPYXL, Client, make_app
from atelier_app import calibrations, engine

XSS = '"><script>alert(1)</script><img src=x onerror=alert(2)>'
STATIC = helpers.APP_DIR / "static"
SID = helpers.SID_RE


def sid_of(resp):
    return re.search(r"s-[0-9]{8}-[0-9a-f]{8}", resp.get("Location")).group(0)


class Base(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)
        self.c.login()
        self.cal = calibrations.load("anssi-v1.5")
        self.cat = engine.quick_catalogue()

    def tearDown(self):
        helpers.cleanup(self.dir)

    def page(self, path, status=200):
        r = self.c.get(path)
        self.assertEqual(r.status, status, path)
        return self.c.text(r)

    def start(self, **over):
        form = {"name": "Bakery review", "activity": "We run three bakeries.", "values": "Taking orders\nCustomer list",
                "tools": ["office", "shop"], "downtime": "day", "sensitivity": "confidential", "lang": "en"}
        form.update(over)
        r = self.c.post_csrf("/quick/new", form, page="/quick/new")
        self.assertEqual(r.status, 303, self.c.text(r)[:300])
        return sid_of(r)

    def study(self, sid):
        return self.app.store.load(sid)

    def post(self, path, form):
        return self.c.post_csrf(path, form, page=path)

    def keep_all(self, sid, **extra):
        ids = re.findall(r'name="keep" value="([^"]+)"', self.page(f"/quick/{sid}/risks"))
        form = {"keep": ids, "lang": "en"}
        form.update(extra)
        r = self.post(f"/quick/{sid}/risks", form)
        self.assertEqual(r.status, 303, self.c.text(r)[:300])
        return ids

    def rate_all(self, sid, go="next", per_risk=None, lang="en"):
        html = self.page(f"/quick/{sid}/now")
        ids = re.findall(r'id="risk-([^"]+)"', html)
        form = {"lang": lang, "go": go}
        for i, rid in enumerate(ids):
            form[f"lik_{rid}"] = (["likely", "possible", "very_likely"] if rid.startswith("D") else ["sometimes", "once", "often", "never"])[i % 3]
            ms = re.findall(rf'name="m_{rid}_([^"]+)" value="extra"', html)
            if i % 2 == 0:
                for m in ms[:3]:
                    form[f"m_{rid}_{m}"] = "extra"
            elif i % 3 == 1:
                form[f"m_{rid}_{ms[0]}"] = "in"
        for rid, over in (per_risk or {}).items():
            form.update(over)
        return self.post(f"/quick/{sid}/now", form), ids


class HomeTest(Base):
    def test_home_has_the_honesty_statement_and_three_ways_in(self):
        t = self.page("/")
        self.assertIn(engine.HONESTY["en"], t)
        self.assertIn('href="/quick/new?lang=en"', t)
        self.assertRegex(t, r'href="/quick/new\?doc=1&(amp;)?lang=en"')
        self.assertIn('href="/reviews?lang=en"', t)
        self.assertIn('href="/studies"', t)
        self.assertIn("Start from scratch", t)
        self.assertIn("I have documents", t)
        self.assertIn("I already have a risk analysis", t)

    def test_french_home(self):
        t = self.page("/?lang=fr")
        self.assertIn(engine.HONESTY["fr"], t)
        self.assertIn('<html lang="fr">', t)
        self.assertIn("Partir de zéro", t)

    def test_language_choice_is_remembered_by_cookie(self):
        self.page("/?lang=fr")
        self.assertEqual(self.c.cookies.get("atelier_lang"), "fr")
        t = self.page("/")
        self.assertIn(engine.HONESTY["fr"], t)

    def test_existing_study_list_stays_reachable(self):
        sid = helpers_load_example(self.c)
        t = self.page("/studies")
        self.assertIn(f'href="/s/{sid}"', t)
        self.assertIn("<h1>Studies</h1>", t)
        self.assertIn('href="/studies"', self.page("/"))

    def test_login_still_required(self):
        anon = Client(self.app)
        for p in ("/", "/quick/new", "/quick/s-20261110-0123abcd/results"):
            self.assertEqual(anon.get(p).status, 303, p)
        self.assertEqual(anon.post("/quick/new", {"name": "x"}).status, 403)

    def test_post_needs_the_csrf_token(self):
        r = self.c.post("/quick/new", {"name": "x", "csrf": "wrong"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.app.store.list(), [])

    def test_recent_quick_studies_listed_on_the_home_page(self):
        t = self.page("/")
        self.assertIn("Nothing here yet", t)
        sid = self.start(name=XSS)
        t = self.page("/")
        self.assertIn(f'href="/quick/{sid}/risks?lang=en"', t)   # next screen to do
        self.assertNotIn("<script>alert", t)
        self.assertIn("&quot;&gt;&lt;script&gt;alert(1)", t)


def helpers_load_example(c):
    return c.load_example()


class WalkTest(Base):
    def test_the_whole_path(self):
        # screen 1: the form, then save
        t = self.page("/quick/new")
        self.assertIn("Step 1 of 4", t)
        self.assertIn('name="activity"', t)
        sid = self.start()
        st = self.study(sid)
        self.assertEqual(st["quick"]["step"], "risks")
        self.assertEqual(st["quick"]["profile"]["name"], "Bakery review")
        self.assertEqual(st["study"]["name"], "Bakery review")
        self.assertEqual(engine.check(st)["errors"], [])
        # screen 2
        t = self.page(f"/quick/{sid}/risks")
        self.assertIn("Step 2 of 4", t)
        suggested = engine.quick_suggest(st["quick"]["profile"], self.cat)
        ids = re.findall(r'name="keep" value="([^"]+)"', t)
        self.assertEqual(sorted(ids), sorted(suggested))
        self.assertIn("Someone attacks you", t)
        self.assertIn("Things go wrong", t)
        discard = ids[-1]
        kept = [i for i in ids if i != discard]
        r = self.post(f"/quick/{sid}/risks", {"keep": kept, "lang": "en", "new_title_1": "Our delivery van breaks down",
                                              "new_family_1": "accidental", "new_crit_1": ["availability"]})
        self.assertEqual((r.status, r.get("Location")), (303, f"/quick/{sid}/now"))
        st = self.study(sid)
        by = {e["id"]: e for e in st["quick"]["risks"]}
        self.assertEqual(by[discard]["decision"], "discard")
        self.assertEqual(by["C1"]["custom"]["title"], "Our delivery van breaks down")
        # screen 3
        t = self.page(f"/quick/{sid}/now")
        self.assertIn("Step 3 of 4", t)
        self.assertIn("Our delivery van breaks down", t)
        self.assertNotIn(f'id="risk-{discard}"', t)
        r, rated = self.rate_all(sid)
        self.assertEqual((r.status, r.get("Location")), (303, f"/quick/{sid}/results"))
        self.assertEqual(sorted(rated), sorted(kept + ["C1"]))
        # screen 4
        st = self.study(sid)
        self.assertEqual(st["quick"]["step"], "results")
        t = self.page(f"/quick/{sid}/results")
        self.assertIn("Step 4 of 4", t)
        self.assertEqual(t.count(engine.HONESTY["en"]), 1)
        self.assertEqual(t.count("<svg"), 2)                                   # before and after maps
        self.assertNotIn("EBIOS", t)                                          # method names stay in expert mode
        self.assertNotIn("EBIOS", self.page(f"/quick/{sid}/now"))
        self.assertIn("Now</figcaption>", t)
        self.assertIn("After your extra measures</figcaption>", t)
        self.assertIn("Your top actions", t)
        self.assertIn("What we assumed", t)
        self.assertIn(f'href="/s/{sid}"', t)                                   # open in expert mode
        self.assertIn("Open in expert mode", t)
        if HAVE_OPENPYXL:
            self.assertIn(f'href="/s/{sid}/export.xlsx"', t)
        else:
            self.assertNotIn("export.xlsx", t)
            self.assertIn("needs the openpyxl package", t)
        conf = engine.quick_confidence(st["quick"], self.cat)
        self.assertLessEqual(conf, 75)
        self.assertIn(f'<span class="big-n">{conf}%</span>', t)
        self.assertIn("Without a document, confidence never goes above 75%.", t)
        actions = re.findall(r'<span class="a-n">(\d)</span>', t)
        self.assertEqual(actions, [str(i) for i in range(1, len(actions) + 1)])
        self.assertTrue(1 <= len(actions) <= 5)
        # the page's levels are the engine's
        rows = engine.quick_compute(st["quick"], self.cal, self.cat)
        reg, _ = engine.register(st, self.cal)
        self.assertEqual([r["id"] for r in reg], [r["id"] for r in rows])
        for r in rows:
            m = re.search(rf'<th scope="row">{r["id"]}</th><td>.*?</td><td><span class="lvl [^"]*">([^<]+)</span></td><td><span class="lvl [^"]*">([^<]+)</span></td>', t)
            self.assertIsNotNone(m, r["id"])
            self.assertEqual((m.group(1), m.group(2)), (r["level"], r["level_target"]))
        # facts line
        self.assertIn("Not provided: architecture document, business impact analysis, security baseline.", t)

    def test_the_stored_study_is_a_normal_valid_study_one_row_per_kept_risk(self):
        sid = self.start()
        ids = self.keep_all(sid)
        self.rate_all(sid)
        st = self.study(sid)
        chk = engine.check(st)
        self.assertEqual(chk["errors"], [])
        rows, summary = engine.register(st, chk["cal"])
        self.assertEqual(sorted(r["id"] for r in rows), sorted(ids))
        self.assertEqual([r["id"] for r in rows], [e["id"] for e in st["quick"]["risks"] if e["decision"] == "keep"])
        for r in rows:
            self.assertTrue(r["level"] and r["level_target"])
        self.assertTrue(summary["now"] and summary["target"])
        # same data in the JSON download
        j = json.loads(self.c.get(f"/s/{sid}/export.json").body)
        self.assertEqual(j["format"], "atelier-study")
        self.assertEqual(len(j["risks"]), len(ids))
        for key in engine.COLLECTIONS:
            for x in st[key]:
                self.assertIn(x["source"], ("document", "answer", "catalogue", "default"), (key, x["id"]))

    def test_saving_at_each_step(self):
        sid = self.start()
        self.assertEqual(self.study(sid)["quick"]["step"], "risks")
        self.keep_all(sid)
        self.assertEqual(self.study(sid)["quick"]["step"], "now")
        r, _ = self.rate_all(sid, go="stay")
        self.assertEqual(r.get("Location"), f"/quick/{sid}/now?f=saved")
        self.assertEqual(self.study(sid)["quick"]["step"], "now")
        self.assertIn("Saved.", self.page(f"/quick/{sid}/now?f=saved"))
        self.assertTrue(all(e.get("assessed") for e in self.study(sid)["quick"]["risks"] if e["decision"] == "keep"))
        self.rate_all(sid, go="next")
        self.assertEqual(self.study(sid)["quick"]["step"], "results")

    def test_coming_back_keeps_the_answers(self):
        sid = self.start(activity="We make chairs", tools=["industrial"], downtime="hours", sensitivity="critical")
        t = self.page(f"/quick/{sid}/about")
        self.assertIn("We make chairs", t)
        self.assertRegex(t, r'name="tools" value="industrial" checked')
        self.assertRegex(t, r'name="downtime" value="hours" checked')
        self.assertRegex(t, r'name="sensitivity" value="critical" checked')
        self.assertIn("Taking orders\nCustomer list", t)

    def test_changing_the_tools_changes_the_suggestions_and_keeps_decisions(self):
        sid = self.start(tools=["office"])
        before = [e["id"] for e in self.study(sid)["quick"]["risks"]]
        self.assertNotIn("D14", before)
        form = {"name": "Bakery review", "activity": "x", "values": "a", "tools": ["office", "industrial"], "downtime": "day",
                "sensitivity": "internal", "lang": "en"}
        r = self.post(f"/quick/{sid}/about", form)
        self.assertEqual(r.status, 303)
        after = [e["id"] for e in self.study(sid)["quick"]["risks"]]
        self.assertIn("D14", after)
        self.assertTrue(set(before) <= set(after))

    def test_calibration_levels_of_the_study_come_from_the_engine(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        st = self.study(sid)
        for r in st["risks"]:
            from atelier_engine import calibration
            self.assertEqual(r["severity"], max(f["severity"] for f in st["feared_events"] if f["id"] == "FE-" + r["id"]))
            self.assertIn(r["likelihood_target"], (1, 2, 3, 4))
            self.assertLessEqual(r["likelihood_target"], r["likelihood"])
            self.assertEqual(calibration.level(self.cal, r["severity"], r["likelihood"]),
                             next(x["level"] for x in engine.register(st, self.cal)[0] if x["id"] == r["id"]))


class ValidationTest(Base):
    def first_always(self, sid):
        t = self.page(f"/quick/{sid}/risks")
        ids = re.findall(r'name="keep" value="([^"]+)"', t)
        always = [r["id"] for r in self.cat["risks"] if r["always_assessed"] and r["id"] in ids]
        self.assertTrue(always)
        return ids, always[0]

    def test_an_always_assessed_risk_needs_a_reason_to_be_discarded(self):
        sid = self.start()
        ids, always = self.first_always(sid)
        before = self.study(sid)
        r = self.post(f"/quick/{sid}/risks", {"keep": [i for i in ids if i != always], "lang": "en"})
        self.assertEqual(r.status, 400)
        t = self.c.text(r)
        self.assertIn("Tell us why you discard this risk.", t)
        self.assertIn('class="reason needed"', t)
        self.assertEqual(self.study(sid), before)                       # nothing saved
        self.assertIn("We always check this one", t)
        # what was typed is kept: the other risks stay ticked
        self.assertEqual(len(re.findall(r'name="keep" value="[^"]+" checked', t)), len(ids) - 1)
        r = self.post(f"/quick/{sid}/risks", {"keep": [i for i in ids if i != always], "lang": "en",
                                              f"reason_{always}": "we have no computers"})
        self.assertEqual(r.status, 303)
        e = next(x for x in self.study(sid)["quick"]["risks"] if x["id"] == always)
        self.assertEqual((e["decision"], e["reason"]), ("discard", "we have no computers"))
        self.assertNotIn(f"FE-{always}", [f["id"] for f in self.study(sid)["feared_events"]])

    def test_discarding_an_ordinary_risk_needs_no_reason(self):
        sid = self.start()
        ids = re.findall(r'name="keep" value="([^"]+)"', self.page(f"/quick/{sid}/risks"))
        ordinary = [r["id"] for r in self.cat["risks"] if not r["always_assessed"] and r["id"] in ids][0]
        r = self.post(f"/quick/{sid}/risks", {"keep": [i for i in ids if i != ordinary], "lang": "en"})
        self.assertEqual(r.status, 303)

    def test_a_severity_other_than_the_proposed_needs_a_reason(self):
        sid = self.start()
        self.keep_all(sid)
        html = self.page(f"/quick/{sid}/now")
        rid = re.findall(r'id="risk-([^"]+)"', html)[0]
        prop = engine.quick_compute(self.study(sid)["quick"], self.cal, self.cat)[0]["severity_proposed"]
        other = 1 if prop != 1 else 2
        r = self.post(f"/quick/{sid}/now", {"lang": "en", "go": "next", f"sev_{rid}": str(other)})
        self.assertEqual(r.status, 400)
        self.assertIn("Tell us why you chose another level.", self.c.text(r))
        self.assertNotIn("severity", next(e for e in self.study(sid)["quick"]["risks"] if e["id"] == rid))
        r = self.post(f"/quick/{sid}/now", {"lang": "en", "go": "next", f"sev_{rid}": str(other), f"sevreason_{rid}": "we have a paper fallback"})
        self.assertEqual(r.status, 303)
        st = self.study(sid)
        risk = next(x for x in st["risks"] if x["id"] == rid)
        self.assertEqual(risk["severity"], other)                      # the engine's calibration accepts it
        self.assertEqual(risk["severity_reason"], "we have a paper fallback")
        self.assertEqual(risk["severity_proposed"], prop)
        self.assertEqual(risk["sources"]["severity"], "answer")
        self.assertEqual(engine.check(st)["errors"], [])
        # choosing the proposed level again clears the override
        self.post(f"/quick/{sid}/now", {"lang": "en", "go": "stay", f"sev_{rid}": str(prop)})
        self.assertNotIn("severity", next(e for e in self.study(sid)["quick"]["risks"] if e["id"] == rid))

    def test_a_level_outside_the_scale_is_ignored_never_stored(self):
        sid = self.start()
        self.keep_all(sid)
        rid = re.findall(r'id="risk-([^"]+)"', self.page(f"/quick/{sid}/now"))[0]
        r = self.post(f"/quick/{sid}/now", {"lang": "en", "go": "stay", f"sev_{rid}": "9", f"sevreason_{rid}": "x", f"lik_{rid}": "certain"})
        self.assertEqual(r.status, 303)
        e = next(e for e in self.study(sid)["quick"]["risks"] if e["id"] == rid)
        self.assertNotIn("severity", e)
        self.assertNotIn("likelihood", e)

    def test_a_measure_not_in_the_risk_list_is_dropped(self):
        sid = self.start()
        self.keep_all(sid)
        rid = re.findall(r'id="risk-([^"]+)"', self.page(f"/quick/{sid}/now"))[0]
        mine = [m["id"] for r in self.cat["risks"] if r["id"] == rid for m in r["measures"]]
        self.post(f"/quick/{sid}/now", {"lang": "en", "go": "stay", f"m_{rid}_not-a-measure": "extra", f"m_{rid}_{mine[0]}": "in",
                                        f"m_{rid}_{mine[1]}": "extra", f"m_{rid}_{mine[2]}": "bogus"})
        e = next(e for e in self.study(sid)["quick"]["risks"] if e["id"] == rid)
        self.assertEqual((e["in_place"], e["extra"]), ([mine[0]], [mine[1]]))     # unknown measures and values are dropped

    def test_name_is_required_and_the_form_keeps_what_was_typed(self):
        form = {"name": " ", "activity": "We bake", "values": "a\nb\nc\nd\ne\nf", "tools": ["office"], "lang": "en"}
        r = self.c.post_csrf("/quick/new", form, page="/quick/new")
        self.assertEqual(r.status, 400)
        t = self.c.text(r)
        self.assertIn("Give the analysis a name", t)
        self.assertIn("Up to 5 things", t)
        self.assertIn("We bake", t)
        self.assertEqual(self.app.store.list(), [])

    def test_unknown_study_and_non_quick_study(self):
        self.assertEqual(self.c.get("/quick/s-20261110-0123abcd/results").status, 404)
        sid = helpers_load_example(self.c)
        for step in ("about", "risks", "now", "results"):
            self.assertEqual(self.c.get(f"/quick/{sid}/{step}").status, 404, step)

    def test_xss_in_risk_title_name_and_text(self):
        sid = self.start(name=XSS, activity=XSS, values=XSS)
        self.keep_all(sid, new_title_1=XSS, new_family_1="deliberate")
        self.rate_all(sid)
        escaped = "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
        for p in ("about", "risks", "now", "results"):
            t = self.page(f"/quick/{sid}/{p}")
            self.assertNotIn("<script>alert", t, p)
            self.assertNotIn("<img src=x", t, p)
        self.assertIn(escaped, self.page(f"/quick/{sid}/risks"))
        self.assertIn(escaped, self.page(f"/quick/{sid}/results"))


class EmptyTest(Base):
    def test_no_risk_kept_gives_friendly_empty_states_and_a_valid_study(self):
        sid = self.start()
        ids = re.findall(r'name="keep" value="([^"]+)"', self.page(f"/quick/{sid}/risks"))
        form = {"keep": [], "lang": "en"}
        for r in self.cat["risks"]:
            form[f"reason_{r['id']}"] = "not relevant"
        r = self.post(f"/quick/{sid}/risks", form)
        self.assertEqual(r.status, 303)
        t = self.page(f"/quick/{sid}/now")
        self.assertIn("You have not kept any risk yet.", t)
        self.assertIn(f'href="/quick/{sid}/risks"', t)
        self.assertNotIn("<form method=\"post\" action=\"/quick/", t.split("</nav>", 2)[-1])
        t = self.page(f"/quick/{sid}/results")
        self.assertIn("You have not kept any risk yet.", t)
        self.assertIn("No action yet.", t)
        self.assertIn('<span class="big-n">0%</span>', t)
        st = self.study(sid)
        self.assertEqual(engine.check(st)["errors"], [])
        self.assertEqual(engine.register(st, self.cal)[0], [])
        self.assertEqual(len(ids), len([e for e in st["quick"]["risks"] if e["decision"] == "discard"]))


class ConfidenceAndAssumptionsTest(Base):
    def conf(self, sid):
        return engine.quick_confidence(self.study(sid)["quick"], self.cat)

    def test_dont_know_lowers_confidence_and_is_listed(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        c0 = self.conf(sid)
        t0 = self.page(f"/quick/{sid}/results")
        form = {"name": "Bakery review", "activity": "", "activity_dk": "1", "values": "", "values_dk": "1", "tools": ["office", "shop"],
                "downtime": "dont_know", "sensitivity": "dont_know", "lang": "en"}
        self.post(f"/quick/{sid}/about", form)
        c1 = self.conf(sid)
        self.assertLess(c1, c0)
        t1 = self.page(f"/quick/{sid}/results")
        self.assertIn("You did not know", t1)
        self.assertIn(f'<span class="big-n">{c1}%</span>', t1)
        self.assertNotIn("You did not know", t0)
        self.assertEqual(engine.check(self.study(sid))["errors"], [])

    def test_skipped_rows_are_default_and_in_the_assumptions(self):
        sid = self.start()
        self.keep_all(sid)
        t = self.page(f"/quick/{sid}/results")
        self.assertIn("Not answered", t)
        self.assertIn("measures already in place were not reviewed", t)
        risks = self.study(sid)["risks"]
        self.assertTrue(all(r["sources"]["likelihood"] == "default" for r in risks))

    def test_confidence_never_above_75_without_a_document(self):
        sid = self.start()
        self.keep_all(sid)
        rated, ids = self.rate_all(sid)
        form = {"lang": "en", "go": "next"}
        for rid in ids:
            form[f"sev_{rid}"] = "1"
            form[f"sevreason_{rid}"] = "our own judgement"
            form[f"lik_{rid}"] = "possible" if rid.startswith("D") else "once"
        self.post(f"/quick/{sid}/now", form)
        self.assertLessEqual(self.conf(sid), 75)


class DocumentTest(Base):
    def upload_start(self, name="notes.txt", data=b"Our network has one server and a router.", kind="architecture"):
        form = {"csrf": self.c.csrf("/quick/new"), "name": "With document", "activity": "x", "values": "a", "tools": ["office"],
                "downtime": "day", "sensitivity": "internal", "lang": "en", "doc_kind": kind}
        body, ctype = helpers.multipart(form, {"document": (name, data)})
        return self.c.req("POST", "/quick/new", body=body, ctype=ctype)

    def test_a_document_is_stored_and_flagged_not_read(self):
        r = self.upload_start()
        self.assertEqual(r.status, 303)
        sid = sid_of(r)
        doc = self.study(sid)["quick"]["profile"]["document"]
        self.assertTrue(doc["provided"])
        self.assertEqual((doc["kind"], doc["filename"]), ("architecture", "notes.txt"))
        listed = self.app.docs.list(sid)
        self.assertEqual([d["id"] for d in listed], [doc["doc_id"]])
        self.keep_all(sid)
        self.rate_all(sid)
        t = self.page(f"/quick/{sid}/results")
        self.assertIn("Documents: architecture document.", t)
        self.assertIn("Not provided: business impact analysis, security baseline.", t)
        self.assertIn("stored but has not been read yet", t)
        self.assertNotIn("Without a document, confidence never goes above", t)
        # nothing was drawn from the document: no element carries source "document"
        st = self.study(sid)
        for key in engine.COLLECTIONS:
            for x in st[key]:
                self.assertNotEqual(x["source"], "document")
        self.assertEqual(self.page(f"/s/{sid}/docs").count("notes.txt"), 1)

    def test_the_second_way_in_opens_the_document_section(self):
        t = self.page("/quick/new?doc=1")
        self.assertRegex(t, r'<details class="q doc" open>')
        self.assertNotRegex(self.page("/quick/new"), r'<details class="q doc" open>')

    def test_refused_document_keeps_the_form_and_says_why(self):
        r = self.upload_start(name="malware.exe", data=b"MZ")
        self.assertEqual(r.status, 400)
        t = self.c.text(r)
        self.assertIn("The document was not accepted", t)
        self.assertIn("only .txt, .md, .docx and .pdf files are accepted", t)
        self.assertRegex(t, r'action="/quick/s-[0-9]{8}-[0-9a-f]{8}/about"')   # resubmitting does not create a second study
        self.assertEqual(len(self.app.store.list()), 1)
        self.assertEqual(self.app.docs.list(sid_of_form(t)), [])

    def test_replacing_the_document(self):
        sid = sid_of(self.upload_start())
        old = self.study(sid)["quick"]["profile"]["document"]["doc_id"]
        form = {"csrf": self.c.csrf(f"/quick/{sid}/about"), "name": "With document", "activity": "x", "values": "a",
                "tools": ["office"], "downtime": "day", "sensitivity": "internal", "lang": "en", "doc_kind": "other"}
        body, ctype = helpers.multipart(form, {"document": ("second.txt", b"Second document text")})
        r = self.c.req("POST", f"/quick/{sid}/about", body=body, ctype=ctype)
        self.assertEqual(r.status, 303)
        new = self.study(sid)["quick"]["profile"]["document"]
        self.assertNotEqual(new["doc_id"], old)
        self.assertEqual([d["id"] for d in self.app.docs.list(sid)], [new["doc_id"]])
        self.assertEqual(new["kind"], "other")

    def test_upload_limit_for_the_quick_forms_matches_documents(self):
        for p in ("/quick/new", f"/quick/s-20261110-0123abcd/about"):
            self.assertEqual(self.app.body_limit(p), self.app.body_limit("/s/s-20261110-0123abcd/docs"))
        self.assertLess(self.app.body_limit("/quick/s-20261110-0123abcd/risks"), self.app.body_limit("/quick/new"))


def sid_of_form(t):
    return re.search(r'/quick/(s-[0-9]{8}-[0-9a-f]{8})/about', t).group(1)


class ExpertModeTest(Base):
    def walk(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        return sid

    def test_the_quick_study_opens_in_the_existing_screens(self):
        sid = self.walk()
        for p in ("", "/w1", "/w2", "/w3", "/w4", "/w5", "/register", "/docs"):
            self.assertEqual(self.c.get(f"/s/{sid}{p}").status, 200, p)
        t = self.page(f"/s/{sid}/w5")
        self.assertIn("Ransomware locks your files and systems", t)
        self.assertIn(f'href="/quick/{sid}/results"', self.page(f"/s/{sid}"))
        reg = self.page(f"/s/{sid}/register")
        self.assertIn("Risk grid, now and at target", reg)
        self.assertEqual(reg.count("<svg"), 2)

    def test_an_expert_edit_shows_a_notice_on_the_quick_screens(self):
        sid = self.walk()
        self.assertNotIn("changed in expert mode", self.page(f"/quick/{sid}/results"))
        r = self.c.post_csrf(f"/s/{sid}/w1/bv/add", {"label": "Added in expert mode", "owner": "me"}, page=f"/s/{sid}/w1")
        self.assertEqual(r.status, 303)
        for step in ("about", "risks", "now", "results"):
            self.assertIn("This study was changed in expert mode", self.page(f"/quick/{sid}/{step}"), step)
        # saving a quick screen rebuilds the study and keeps the previous version as .bak
        self.post(f"/quick/{sid}/risks", {"keep": [e["id"] for e in self.study(sid)["quick"]["risks"]], "lang": "en"})
        self.assertNotIn("Added in expert mode", json.dumps(self.study(sid)))
        self.assertIn("Added in expert mode", (self.app.store.dir / f"{sid}.json.bak").read_text(encoding="utf-8"))

    def test_the_confidential_mark_survives_a_rebuild(self):
        sid = self.walk()
        self.c.post_csrf(f"/s/{sid}/confidential", {"confidential": "yes"}, page=f"/s/{sid}")
        self.assertTrue(self.study(sid)["study"]["confidential"])
        self.rate_all(sid, go="stay")
        self.assertTrue(self.study(sid)["study"]["confidential"])


@unittest.skipUnless(HAVE_OPENPYXL, "openpyxl is not installed")
class ExportTest(Base):
    def test_excel_export_has_the_honesty_header_maps_and_assumptions(self):
        import openpyxl
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        r = self.c.get(f"/s/{sid}/export.xlsx")
        self.assertEqual(r.status, 200)
        self.assertIn("spreadsheetml", r.get("Content-Type"))
        wb = openpyxl.load_workbook(io.BytesIO(r.body))
        first = wb.worksheets[0]
        self.assertEqual(first["A1"].value, engine.HONESTY["en"])
        self.assertTrue(first["A2"].value.startswith("Documents: none. Not provided: architecture, business-impact, security-baseline."))
        self.assertIn("Confidence:", first["A2"].value)
        header_row = next(i for i, row in enumerate(first.iter_rows(values_only=True), 1) if row[0] == "id")
        self.assertEqual([c.value for c in first[header_row]][:5], ["id", "label", "severity", "likelihood", "level"])
        st = self.study(sid)
        ids = [first.cell(i, 1).value for i in range(header_row + 1, first.max_row + 1)]
        self.assertEqual(ids, [r["id"] for r in st["risks"]])
        self.assertIn("Map now", wb.sheetnames)
        self.assertIn("Map target", wb.sheetnames)
        self.assertIn("Assumptions", wb.sheetnames)
        self.assertIn("Top actions", wb.sheetnames)

    def test_french_export_uses_the_french_statement(self):
        import openpyxl
        sid = self.start(lang="fr")
        self.page(f"/quick/{sid}/risks?lang=fr")
        self.keep_all(sid, lang="fr")
        self.rate_all(sid, lang="fr")
        wb = openpyxl.load_workbook(io.BytesIO(self.c.get(f"/s/{sid}/export.xlsx").body))
        self.assertEqual(wb.worksheets[0]["A1"].value, engine.HONESTY["fr"])

    def test_plain_studies_export_without_a_header(self):
        import openpyxl
        sid = helpers_load_example(self.c)
        wb = openpyxl.load_workbook(io.BytesIO(self.c.get(f"/s/{sid}/export.xlsx").body))
        self.assertEqual(wb.worksheets[0]["A1"].value, "id")


class FrenchTest(Base):
    def test_french_walk_builds_a_french_study(self):
        self.page("/?lang=fr")
        sid = self.start(lang="fr", name="Boulangerie")
        t = self.page(f"/quick/{sid}/risks")
        self.assertIn("Étape 2 sur 4", t)
        self.assertIn("Quelqu&#x27;un vous attaque", t)
        self.keep_all(sid, lang="fr")
        self.rate_all(sid, lang="fr")
        t = self.page(f"/quick/{sid}/results")
        self.assertIn(engine.HONESTY["fr"], t)
        self.assertIn("Vos actions prioritaires", t)
        st = self.study(sid)
        self.assertEqual(st["quick"]["lang"], "fr")
        self.assertEqual(next(r for r in st["risks"] if r["id"] == "D01")["label"], "Un rançongiciel bloque vos fichiers et vos systèmes")
        self.assertEqual(engine.check(st)["errors"], [])

    def test_every_english_key_has_a_french_text(self):
        from atelier_app import views_quick
        self.assertEqual(set(views_quick.T["en"]), set(views_quick.T["fr"]))
        for k, v in views_quick.T["fr"].items():
            self.assertTrue(v.strip(), k)


class ExistingFeaturesTest(Base):
    def test_the_guide_example_still_loads_and_gives_the_same_levels(self):
        sid = helpers_load_example(self.c)
        st = self.study(sid)
        chk = engine.check(st)
        self.assertEqual(chk["errors"], [])
        rows, _ = engine.register(st, chk["cal"])
        self.assertEqual([(r["id"], r["severity"], r["likelihood"], r["level"]) for r in rows],
                         [("R1", 3, 3, "Élevé"), ("R2", 3, 2, "Moyen"), ("R3", 3, 4, "Élevé"), ("R4", 4, 2, "Moyen"), ("R5", 4, 1, "Moyen")])
        self.assertNotIn("Quick path results", self.page(f"/s/{sid}"))

    def test_review_import_page_is_reachable_from_the_home_page(self):
        self.assertIn('href="/reviews?lang=en"', self.page("/"))
        self.assertEqual(self.c.get("/reviews").status, 200)


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.fors, self.controls, self.in_label, self.html_lang, self.viewport = set(), set(), [], 0, None, False
        self.scripts, self.styles, self.urls, self.stack, self.headings = [], [], [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.html_lang = a.get("lang")
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = True
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "label":
            self.in_label += 1
            if "for" in a:
                self.fors.add(a["for"])
        if tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit", "button"):
            self.controls.append((tag, a, self.in_label > 0))
        if tag == "script":
            self.scripts.append(a)
        if "style" in a:
            self.styles.append(tag)
        for k in ("href", "src", "action"):
            if str(a.get(k, "")).startswith(("http://", "https://", "//")):
                self.urls.append((tag, a[k]))
        if tag in ("h1", "h2"):
            self.headings.append(tag)

    def handle_endtag(self, tag):
        if tag == "label":
            self.in_label -= 1


class MarkupTest(Base):
    def pages(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        return [("/", self.page("/")), ("/quick/new", self.page("/quick/new")), ("/quick/new?doc=1", self.page("/quick/new?doc=1"))] + [
            (f"/quick/{sid}/{s}", self.page(f"/quick/{sid}/{s}")) for s in ("about", "risks", "now", "results")]

    def test_every_control_has_a_label_and_the_page_is_self_contained(self):
        for path, t in self.pages():
            p = Parser()
            p.feed(t)
            self.assertEqual(p.html_lang, "en", path)
            self.assertTrue(p.viewport, path)
            for tag, a, inside in p.controls:
                labelled = inside or a.get("id") in p.fors or a.get("aria-label")
                self.assertTrue(labelled, (path, tag, a))
            self.assertEqual([s for s in p.scripts if not s.get("src")], [], path)       # no inline script (CSP)
            self.assertEqual(p.styles, [], path)                                          # no inline style (CSP)
            self.assertEqual(p.urls, [], path)                                            # nothing external
            self.assertEqual(p.headings.count("h1"), 1, path)

    def test_css_and_js_are_self_contained(self):
        css = (STATIC / "app.css").read_text(encoding="utf-8")
        self.assertNotRegex(css, r"https?://|@import|url\(")
        self.assertEqual(css.count("{"), css.count("}"))
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotRegex(js, r"https?://|import\(|XMLHttpRequest|fetch\(")

    def test_a_system_font_stack_only(self):
        css = (STATIC / "app.css").read_text(encoding="utf-8")
        self.assertIn("system-ui", css)
        self.assertNotIn("@font-face", css)

    def test_responsive_rules_exist_for_a_tablet_width(self):
        css = (STATIC / "app.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media \(max-width: 820px\)")
        self.assertIn("grid-template-columns: minmax(0, 1fr)", css)

    def test_security_headers_on_the_quick_pages(self):
        for p in ("/", "/quick/new"):
            r = self.c.get(p)
            self.assertIn("default-src 'none'", r.get("Content-Security-Policy"))
            self.assertEqual(r.get("X-Frame-Options"), "DENY")


def _lum(hexcol):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class ContrastTest(unittest.TestCase):
    """WCAG AA: 4.5:1 for normal text (3:1 for large text and focus indicators), computed from the stylesheet's own colours."""

    def vars(self):
        css = (STATIC / "app.css").read_text(encoding="utf-8")
        return dict(re.findall(r"--([a-z-]+): (#[0-9a-fA-F]{6})", css)), css

    def test_text_pairs_reach_aa(self):
        v, _ = self.vars()
        pairs = [("ink", "bg"), ("ink", "card"), ("muted", "bg"), ("muted", "card"), ("accent", "card"), ("accent", "bg"),
                 ("accent-dark", "accent-soft"), ("accent", "accent-soft"), ("bad", "card"), ("warn", "card"), ("ok", "card"),
                 ("muted", "accent-soft")]
        for fg, bg in pairs:
            self.assertGreaterEqual(contrast(v[fg], v[bg]), 4.5, (fg, bg, contrast(v[fg], v[bg])))

    def test_buttons_and_header(self):
        v, _ = self.vars()
        for bg in ("accent", "accent-dark", "bad"):
            self.assertGreaterEqual(contrast("#ffffff", v[bg]), 4.5, bg)
        self.assertGreaterEqual(contrast("#ffffff", "#1a2b63"), 4.5)
        self.assertGreaterEqual(contrast("#dbe4ff", "#27458f"), 4.5)       # the header's sub-title on the lighter end

    def test_badges_and_bands(self):
        pairs = [("#5a3d00", "#fff1cc"), ("#8c1d16", "#fde2e0"), ("#14502b", "#dff1e5"), ("#14502b", "#e6f4ea"), ("#5a3d00", "#fff6dd"),
                 ("#1d2a55", "#e8eefc")]
        for fg, bg in pairs:
            self.assertGreaterEqual(contrast(fg, bg), 4.5, (fg, bg))

    def test_legacy_badge_pairs_reach_aa(self):
        v, css = self.vars()
        for sel, fg, bg in ((".badge.ok", "ok", "#dff1e5"), (".badge.warn", "warn", "#fdeccc"), (".badge.bad", "bad", "#fadad7")):
            self.assertIn(f"{sel} {{ background: {bg}; color: var(--{fg}); }}", css)
            self.assertGreaterEqual(contrast(v[fg], bg), 4.5, sel)

    def test_focus_ring_is_visible(self):
        v, _ = self.vars()
        self.assertGreaterEqual(contrast(v["focus"], "#ffffff"), 3.0)
        self.assertGreaterEqual(contrast(v["focus"], v["bg"]), 3.0)

    def test_input_borders_reach_3_to_1(self):
        v, css = self.vars()
        self.assertIn("border: 1px solid var(--field)", css)
        self.assertGreaterEqual(contrast(v["field"], "#ffffff"), 3.0)

    def test_calibration_level_chips_are_readable(self):
        cal = json.loads((helpers.REPO / "calibrations" / "anssi-v1.5.json").read_text(encoding="utf-8"))
        from atelier_app import views
        for l in cal["levels"]:
            css = views.cal_css({"levels": [l]})
            fg = re.search(r"color:(#[0-9a-f]{3})", css).group(1)
            fg = "#" + "".join(ch * 2 for ch in fg[1:])
            self.assertGreaterEqual(contrast(fg, "#" + l["colour"]), 4.5, l["name"])


if __name__ == "__main__":
    unittest.main()
