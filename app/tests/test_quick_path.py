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
from atelier_app import calibrations, engine, labels

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
        ms = re.findall(r'name="m_([^"]+)" value="extra"', html)     # each measure is answered once, for the whole business
        for i, m in enumerate(ms):
            if i % 3 == 0:
                form[f"m_{m}"] = "extra"
            elif i % 7 == 1:
                form[f"m_{m}"] = "in"
        for rid, over in (per_risk or {}).items():
            form.update(over)
        return self.post(f"/quick/{sid}/now", form), ids


class HomeTest(Base):
    def test_home_has_the_honesty_statement_and_one_clear_start(self):
        t = self.page("/")
        self.assertEqual(t.count(engine.HONESTY["en"]), 1)
        self.assertIn('href="/quick/new?lang=en"', t)
        self.assertNotIn("doc=1", t)
        self.assertIn('href="/studies"', t)
        self.assertEqual(len(re.findall(r'<a class="button primary big"', t)), 1)
        self.assertIn(">Start <", t)
        self.assertNotIn('<a class="way', t)
        for gone in ("I have a document", "Start from scratch", "I already have a risk analysis", "/reviews", "workshop"):
            self.assertNotIn(gone, t, gone)

    def test_home_says_15_minutes_once_and_the_subtitle_is_one_line(self):
        for lang, phrase in (("en", "15 minutes"), ("fr", "15 minutes")):
            t = self.page(f"/?lang={lang}")
            self.assertEqual(t.count(phrase), 1, lang)
            self.assertNotIn("30 minutes", t)
            self.assertEqual(len(re.findall(r'<p class="lead">', t)), 1)
            lead = re.search(r'<p class="lead">(.*?)</p>', t).group(1)
            self.assertLessEqual(len(lead.split()), 16, lead)          # one line of the page
            self.assertEqual(re.findall(r"[.!?]", lead.rstrip(".")), [], lead)  # one sentence

    def test_french_home(self):
        t = self.page("/?lang=fr")
        self.assertIn(engine.HONESTY["fr"], t)
        self.assertIn('<html lang="fr">', t)
        self.assertIn("Commencer", t)
        self.assertNotIn("J'ai un document", t)

    def test_language_choice_is_remembered_by_cookie(self):
        self.page("/?lang=fr")
        self.assertEqual(self.c.cookies.get("atelier_lang"), "fr")
        t = self.page("/")
        self.assertIn(engine.HONESTY["fr"], t)

    def test_study_list_reopens_and_deletes(self):
        sid = self.start()
        t = self.page("/studies")
        self.assertIn(f'href="/quick/{sid}/risks"', t)                 # reopen at the screen where the person stopped
        self.assertIn(f'href="/s/{sid}/delete"', t)
        self.assertIn("<h1>Studies</h1>", t)
        self.assertIn('href="/studies"', self.page("/"))
        self.assertNotIn("Duplicate", t)
        self.assertNotIn("Import a study file", t)

    def test_a_file_that_is_not_a_quick_study_can_only_be_deleted(self):
        sid = helpers.store_example(self.c)
        t = self.page("/studies")
        self.assertIn("not a quick-path study", t)
        self.assertNotIn(f'href="/quick/{sid}/', t)
        self.assertIn(f'href="/s/{sid}/delete"', t)

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
        self.assertIn("Your analyses will appear here", t)
        sid = self.start(name=XSS)
        t = self.page("/")
        self.assertIn(f'href="/quick/{sid}/risks?lang=en"', t)   # next screen to do
        self.assertNotIn("<script>alert", t)
        self.assertIn("&quot;&gt;&lt;script&gt;alert(1)", t)


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
        self.assertIn("Someone does it on purpose", t)
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
        self.assertNotIn("EBIOS", t)                                          # plain words only, no method names
        self.assertNotIn("EBIOS", self.page(f"/quick/{sid}/now"))
        self.assertIn("Now</figcaption>", t)
        self.assertIn("After your extra measures</figcaption>", t)
        self.assertIn("Your top actions", t)
        self.assertIn("What we assumed", t)
        for gone in ("Open in expert view", "workshop", "Workshop"):
            self.assertNotIn(gone, t, gone)
        self.assertNotIn(f'href="/s/{sid}"', t)
        self.assertIn(f'href="/s/{sid}/export.json"', t)
        if HAVE_OPENPYXL:
            self.assertIn(f'href="/s/{sid}/export.xlsx"', t)
        else:
            self.assertNotIn("export.xlsx", t)
            self.assertIn("Add the openpyxl package to enable the Excel download", t)
        conf = engine.quick_confidence(st["quick"], self.cat)
        self.assertLessEqual(conf, 75)
        self.assertIn(f'<span class="big-n">{conf}%</span>', t)
        self.assertIn("Confidence grows as you answer more questions yourself.", t)
        self.assertIn("up to 75%", t)
        actions = re.findall(r'<span class="a-n">(\d)</span>', t)
        self.assertEqual(actions, [str(i) for i in range(1, len(actions) + 1)])
        self.assertTrue(1 <= len(actions) <= 5)
        # the page's levels are the engine's
        rows = engine.quick_compute(st["quick"], self.cal, self.cat)
        reg, _ = engine.register(st, self.cal)
        self.assertEqual([r["id"] for r in reg], [r["id"] for r in rows])
        listing = t.split('<details class="see-all">')[1].split("</details>")[0]
        for i, r in enumerate(rows, 1):
            m = re.search(rf'<span class="rid">{i}</span> .*?<span class="lvl [^"]*">([^<]+)</span> <span aria-hidden="true">&rarr;</span> '
                          rf'<span class="lvl [^"]*">([^<]+)</span></h3>', listing)
            self.assertIsNotNone(m, r["id"])
            # the engine's level, shown under its plain name (Low / Moderate / High) on this English page
            self.assertEqual((m.group(1), m.group(2)), (labels.level_label(self.cal, r["level"], "en"),
                                                        labels.level_label(self.cal, r["level_target"], "en")))
        self.assertNotIn("Documents", t)

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
        q = self.study(sid)["quick"]
        self.assertTrue(q["measures"]["assessed"])
        for e in q["risks"]:     # the answers belong to the whole business, not to one risk
            for k in ("in_place", "extra", "assessed"):
                self.assertNotIn(k, e)
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
        self.assertIn("Tell us why you set this risk aside.", t)
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

    def test_a_measure_not_in_the_list_is_dropped(self):
        sid = self.start()
        self.keep_all(sid)
        mine = re.findall(r'name="m_([^"]+)" value="extra"', self.page(f"/quick/{sid}/now"))
        self.post(f"/quick/{sid}/now", {"lang": "en", "go": "stay", "m_not-a-measure": "extra", f"m_{mine[0]}": "in",
                                        f"m_{mine[1]}": "extra", f"m_{mine[2]}": "bogus"})
        measures = self.study(sid)["quick"]["measures"]
        self.assertEqual((measures["in_place"], measures["extra"]), ([mine[0]], [mine[1]]))     # unknown measures and values are dropped

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
        sid = helpers.store_example(self.c)
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
        self.assertIn("Choose your risks first, then come back here.", t)
        self.assertIn(f'href="/quick/{sid}/risks"', t)
        self.assertNotIn("<form method=\"post\" action=\"/quick/", t.split("</nav>", 2)[-1])
        t = self.page(f"/quick/{sid}/results")
        self.assertIn("Choose your risks first, then come back here.", t)
        self.assertIn("Tick the measures you would add", t)
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
        self.assertIn("Not sure", t1)
        self.assertIn(f'<span class="big-n">{c1}%</span>', t1)
        self.assertNotIn("Not sure", t0)
        self.assertEqual(engine.check(self.study(sid))["errors"], [])

    def test_skipped_rows_are_default_and_in_the_assumptions(self):
        sid = self.start()
        self.keep_all(sid)
        t = self.page(f"/quick/{sid}/results")
        self.assertIn("Left open", t)
        self.assertIn("Measures already in place: none assumed yet.", t)
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


class NoDocumentTalkTest(Base):
    """Small businesses have no architecture document, impact analysis or security baseline: the public screens
    do not ask for one, and the answers of an older form that did are ignored."""
    WORDS = ("document", "architecture", "impact analysis", "security baseline", "business impact", "socle de sécurité",
             "analyse d'impact", "d'architecture", "mentioned, not read", "mentionné")

    def start_doc(self, answer):
        form = {"csrf": self.c.csrf("/quick/new"), "name": "With document", "activity": "x", "values": "a", "tools": ["office"],
                "downtime": "day", "sensitivity": "internal", "lang": "en"}
        if answer is not None:
            form["has_doc"] = answer
        return self.c.post("/quick/new", form)

    def test_the_about_form_has_no_document_question(self):
        for path in ("/quick/new", "/quick/new?doc=1"):
            t = self.page(path)
            self.assertNotIn("has_doc", t, path)
            self.assertNotIn("Do you have a document", t, path)
            self.assertNotIn('type="file"', t, path)
            self.assertNotIn("multipart", t, path)

    def test_an_old_form_answer_is_ignored(self):
        for answer in ("yes", "no", None, "maybe"):
            sid = sid_of(self.start_doc(answer))
            self.assertNotIn("document", self.study(sid)["quick"]["profile"], answer)
        self.keep_all(sid)
        self.rate_all(sid)
        t = self.page(f"/quick/{sid}/results")
        self.assertIn("Confidence grows as you answer more questions yourself.", t)
        st = self.study(sid)
        for key in engine.COLLECTIONS:
            for x in st[key]:
                self.assertNotEqual(x["source"], "document")
        self.assertEqual(engine.check(st)["errors"], [])

    def test_no_public_screen_talks_about_documents_in_either_language(self):
        for lang in ("en", "fr"):
            sid = self.start(lang=lang)
            self.keep_all(sid, lang=lang)
            self.rate_all(sid, lang=lang)
            paths = ["/", "/quick/new", f"/quick/{sid}/about", f"/quick/{sid}/risks", f"/quick/{sid}/now",
                     f"/quick/{sid}/results", "/how", "/studies"]
            for path in paths:
                t = self.page(path + ("&" if "?" in path else "?") + f"lang={lang}").split("<main", 1)[1].lower()
                for w in self.WORDS:
                    self.assertNotIn(w, t, (lang, path, w))

    @unittest.skipUnless(HAVE_OPENPYXL, "openpyxl is not installed")
    def test_the_excel_export_has_no_document_talk(self):
        import openpyxl
        for lang in ("en", "fr"):
            sid = self.start(lang=lang)
            self.keep_all(sid, lang=lang)
            self.rate_all(sid, lang=lang)
            wb = openpyxl.load_workbook(io.BytesIO(self.c.get(f"/s/{sid}/export.xlsx?lang={lang}").body))
            blob = " ".join(str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None).lower()
            for w in self.WORDS:
                self.assertNotIn(w, blob, (lang, w))

    def test_the_document_routes_and_storage_are_gone(self):
        sid = sid_of(self.start_doc("yes"))
        self.assertEqual(self.c.get(f"/s/{sid}/docs").status, 404)
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/docs", {}, page="/").status, 404)
        self.assertFalse(hasattr(self.app, "docs"))
        self.assertFalse((self.app.data_dir / "documents").exists())

    def test_the_request_limit_is_the_same_for_every_form(self):
        for p in ("/quick/new", "/quick/s-20261110-0123abcd/about", "/quick/s-20261110-0123abcd/risks"):
            self.assertEqual(self.app.body_limit(p), self.app.max_upload)


class RemovedExpertFeaturesTest(Base):
    """Review mode, AI drafting, document upload, private calibrations and import stay out of the public edition."""

    def walk(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        return sid

    def test_the_removed_pages_answer_404(self):
        sid = self.walk()
        for p in ("/docs", "/confidential", "/draft", "/draft/clear", "/draft/accept-all"):
            self.assertEqual(self.c.get(f"/s/{sid}{p}").status, 404, p)
            self.assertEqual(self.c.post_csrf(f"/s/{sid}{p}", {}, page="/").status, 404, p)
        for p in ("/reviews", "/reviews/r-20261110-0123abcd", "/settings", "/new", "/import", "/example"):
            self.assertEqual(self.c.get(p).status, 404, p)
            self.assertEqual(self.c.post_csrf(p, {}, page="/").status, 404, p)

    def test_the_quick_study_still_downloads_and_deletes(self):
        sid = self.walk()
        self.assertEqual(self.c.get(f"/s/{sid}/export.json").status, 200)
        self.assertEqual(self.c.get(f"/s/{sid}/delete").status, 200)
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/delete", {}, page=f"/s/{sid}/delete").status, 303)
        self.assertEqual(self.c.get(f"/quick/{sid}/results").status, 404)

    def test_no_page_mentions_the_removed_features(self):
        sid = self.walk()
        for path in ("/", "/studies", "/quick/new", f"/quick/{sid}/about", f"/quick/{sid}/risks",
                     f"/quick/{sid}/now", f"/quick/{sid}/results"):
            for lang in ("en", "fr"):
                t = self.page(f"{path}{'&' if '?' in path else '?'}lang={lang}").lower()
                for word in ("workshop", "atelier 1", "reviews", "revues", "/settings", "calibration", "/docs", "/draft"):
                    self.assertNotIn(word, t, (path, lang, word))

    def test_only_the_published_calibration_is_known(self):
        self.assertEqual(calibrations.available(), {"anssi-v1.5": "public"})
        self.assertTrue(calibrations.exists("anssi-v1.5"))
        self.assertFalse(calibrations.exists("my-org-2026"))
        self.assertEqual(self.c.get("/cal/anssi-v1.5.css").status, 200)
        self.assertEqual(self.c.get("/cal/my-org-2026.css").status, 404)

    def test_a_private_directory_in_the_environment_is_ignored(self):
        import os
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            clash = pathlib.Path(d) / "anssi-v1.5.json"                      # would win a name clash in the engine
            clash.write_text('{"id": "anssi-v1.5", "name": "NOT THE PUBLISHED ONE"}', encoding="utf-8")
            (pathlib.Path(d) / "my-org-2026.json").write_text("{}", encoding="utf-8")
            with mock.patch.dict(os.environ, {"ATELIER_PRIVATE_DIR": d}):
                self.assertEqual(calibrations.available(), {"anssi-v1.5": "public"})
                self.assertNotEqual(calibrations.load("anssi-v1.5").get("name"), "NOT THE PUBLISHED ONE")
                self.assertFalse(calibrations.exists("my-org-2026"))
                self.assertEqual(engine.check({"format": "atelier-study", "study": {"calibration": "my-org-2026"}})["cal"], None)
                sid = self.start()                                            # a whole walk uses the published one
                self.assertEqual(self.study(sid)["study"]["calibration"], "anssi-v1.5")

    def test_the_removed_modules_are_not_importable(self):
        import importlib
        for name in ("reviews", "views_review", "review_store", "drafting", "drafts", "views_draft", "documents"):
            with self.assertRaises(ImportError, msg=name):
                importlib.import_module(f"atelier_app.{name}")

    def test_the_app_has_no_private_dir_option(self):
        import inspect
        from atelier_app import server
        self.assertNotIn("private", inspect.signature(type(self.app).__init__).parameters)
        with self.assertRaises(SystemExit):
            server.parse_args(["--private-dir", "/tmp/x"])


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
        self.assertNotIn("Documents", first["A2"].value)
        self.assertIn("Confidence:", first["A2"].value)
        self.assertIn("Confidence grows as you answer more questions yourself.", first["A2"].value)
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
        sid = helpers.store_example(self.c)
        wb = openpyxl.load_workbook(io.BytesIO(self.c.get(f"/s/{sid}/export.xlsx").body))
        self.assertEqual(wb.worksheets[0]["A1"].value, "id")


class FrenchTest(Base):
    def test_french_walk_builds_a_french_study(self):
        self.page("/?lang=fr")
        sid = self.start(lang="fr", name="Boulangerie")
        t = self.page(f"/quick/{sid}/risks")
        self.assertIn("Étape 2 sur 4", t)
        self.assertIn("Quelqu&#x27;un le fait exprès", t)
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
    def test_the_guide_example_still_gives_the_same_levels(self):
        st = helpers.example_json()
        chk = engine.check(st)
        self.assertEqual(chk["errors"], [])
        rows, _ = engine.register(st, chk["cal"])
        self.assertEqual([(r["id"], r["severity"], r["likelihood"], r["level"]) for r in rows],
                         [("R1", 3, 3, "Élevé"), ("R2", 3, 2, "Moyen"), ("R3", 3, 4, "Élevé"), ("R4", 4, 2, "Moyen"), ("R5", 4, 1, "Moyen")])


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
        return [("/", self.page("/")), ("/quick/new", self.page("/quick/new")), ("/quick/new?doc=1", self.page("/quick/new?doc=1")),
                ("/studies", self.page("/studies"))] + [
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
        pairs = [("#5a3d00", "#fff1cc"), ("#14502b", "#dff1e5"), ("#14502b", "#e6f4ea"), ("#5a3d00", "#fff6dd"),
                 ("#1d2a55", "#e8eefc")]
        for fg, bg in pairs:
            self.assertGreaterEqual(contrast(fg, bg), 4.5, (fg, bg))

    def test_the_soft_palette_has_no_red_alert_colours_and_the_pairs_stay_readable(self):
        v, css = self.vars()
        self.assertIn(".band.b-low { background: #fff1cc; color: #5a3d00; }", css)       # low confidence: soft amber, not red
        self.assertIn(".band.b-medium { background: var(--accent-soft); color: var(--accent-dark); }", css)
        self.assertIn("button.danger, a.button.danger { background: #fff; border-color: var(--bad); color: var(--bad); }", css)
        for sel, fg, bg in ((".badge.ok", "ok", "#dff1e5"), (".badge.warn", "warn", "#fdeccc"), (".badge.bad", "bad", "#fdeccc")):
            self.assertIn(f"{sel} {{ background: {bg}; color: var(--{fg}); }}", css)
            self.assertGreaterEqual(contrast(v[fg], bg), 4.5, sel)
        r, g, b = (int(v["bad"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertLess(r - max(g, b), 100, v["bad"])                                    # not a strong red

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


class RoundTwoShortlistTest(Base):
    """F1: the Risks screen pre-ticks only the short list; the rest sits under a collapsed section, unticked."""

    def small(self, **over):
        form = {"tools": ["office", "cloud", "provider", "shop"], "downtime": "day", "sensitivity": "confidential"}
        form.update(over)
        return self.start(**form)

    def test_at_most_ten_are_pre_ticked_and_the_others_are_offered_unticked(self):
        sid = self.small()
        html = self.page(f"/quick/{sid}/risks")
        boxes = re.findall(r'<input class="keep-box" type="checkbox" name="keep" value="([A-Z0-9]+)"( checked)?>', html)
        self.assertEqual(len(boxes), 29)
        ticked = [b for b, c in boxes if c]
        self.assertEqual(len(ticked), 10)
        self.assertEqual(sorted(ticked), sorted(engine.quick_shortlist({"tools": {"value": ["office", "cloud", "provider", "shop"]},
                                                         "downtime": {"answer": "day"}, "sensitivity": {"answer": "confidential"}}, self.cat)))
        self.assertIn("10 of 10 risks kept", html)
        self.assertRegex(html, r'<details class="q more-risks"><summary><span class="q-t">More risks you can add \(19\)</span></summary>')
        self.assertNotIn("more-risks\" open", html)  # collapsed
        main, more = html.split('<details class="q more-risks">')
        self.assertEqual(len(re.findall(r'name="keep"', main)), 10)
        self.assertEqual(len(re.findall(r'name="keep"', more.split("</details>")[0])), 19)
        self.assertNotIn(" checked>", more.split("</details>")[0].split("add-row")[0])

    def test_a_risk_ticked_from_the_more_section_is_kept(self):
        sid = self.small()
        html = self.page(f"/quick/{sid}/risks")
        first = re.findall(r'name="keep" value="([A-Z0-9]+)"', html.split('<details class="q more-risks">')[1])[0]
        ids = re.findall(r'<input class="keep-box" type="checkbox" name="keep" value="([A-Z0-9]+)" checked>', html) + [first]
        r = self.post(f"/quick/{sid}/risks", {"keep": ids, "lang": "en"})
        self.assertEqual(r.status, 303)
        kept = [e["id"] for e in self.study(sid)["quick"]["risks"] if e["decision"] == "keep"]
        self.assertEqual(len(kept), 11)
        self.assertIn(first, kept)
        self.assertEqual(len(self.study(sid)["quick"]["risks"]), 29)
        self.assertEqual(len(self.study(sid)["risks"]), 11)
        # the ticked one now shows in the main list
        html2 = self.page(f"/quick/{sid}/risks")
        self.assertIn(f'name="keep" value="{first}" checked>', html2.split('<details class="q more-risks">')[0])

    def test_now_and_after_and_results_cover_only_the_ticked_ones(self):
        sid = self.small()
        self.keep_all_ticked(sid)
        now = self.page(f"/quick/{sid}/now")
        self.assertEqual(len(re.findall(r'<article class="risk-row', now)), 10)
        res = self.page(f"/quick/{sid}/results")
        self.assertEqual(res.count('<article class="risk-finding">'), 10)
        self.assertEqual(len(re.findall(r'<li value="\d+">', res)), 10)
        self.assertEqual(len(self.study(sid)["risks"]), 10)

    def keep_all_ticked(self, sid):
        html = self.page(f"/quick/{sid}/risks")
        ids = re.findall(r'<input class="keep-box" type="checkbox" name="keep" value="([A-Z0-9]+)" checked>', html)
        r = self.post(f"/quick/{sid}/risks", {"keep": ids, "lang": "en"})
        self.assertEqual(r.status, 303)
        return ids

    def test_state_level_risk_only_for_the_highest_sensitivity_or_industrial(self):
        sid = self.small()
        self.assertNotIn("D10", re.findall(r'name="keep" value="([A-Z0-9]+)" checked>', self.page(f"/quick/{sid}/risks")))
        top = self.small(sensitivity="critical")
        d10 = re.search(r'name="keep" value="D10"( checked)?>', self.page(f"/quick/{top}/risks"))
        self.assertIsNotNone(d10)  # offered (main list or "More")
        short = engine.quick_shortlist({"tools": {"value": ["office"]}, "sensitivity": {"answer": "critical"}}, self.cat, limit=99)
        self.assertIn("D10", short)

    def test_changing_the_answers_keeps_earlier_decisions(self):
        sid = self.small()
        ids = self.keep_all_ticked(sid)
        discard = ids[-1]
        self.post(f"/quick/{sid}/risks", {"keep": [i for i in ids if i != discard], "lang": "en"})
        form = {"name": "Bakery review", "activity": "x", "values": "a", "tools": ["office", "cloud", "provider", "shop"],
                "downtime": "day", "sensitivity": "confidential", "lang": "en"}
        self.assertEqual(self.post(f"/quick/{sid}/about", form).status, 303)
        decisions = {e["id"]: e["decision"] for e in self.study(sid)["quick"]["risks"]}
        self.assertEqual(decisions[discard], "discard")
        self.assertEqual(sum(1 for v in decisions.values() if v == "keep"), 9)


class MapWordsMatchTheQuestion(Base):
    def test_map_axis_uses_the_likelihood_question_words(self):
        from atelier_app import labels
        for lang in ("en", "fr"):
            sid = self.start(lang=lang)
            self.keep_all(sid, lang=lang)
            self.rate_all(sid, lang=lang)
            now = self.page(f"/quick/{sid}/now?lang={lang}")
            res = self.page(f"/quick/{sid}/results?lang={lang}")
            for n in (1, 2, 3, 4):
                w = labels.LIKELIHOOD_LABEL[lang][n]
                self.assertIn(w, res, (lang, n))
                self.assertIn(w, now, (lang, n))


class RoundTwoLanguageTest(Base):
    """F2: English pages carry English level and axis names; French pages French; the quick xlsx follows."""

    FRENCH_LEVELS = ("Élevé", "Modéré", "Faible", "Peu probable", "Très probable", "Probable", "Très sérieux", "Mineur", "Notable")
    ENGLISH_LEVELS = ("Low", "Moderate", "High", "Unlikely", "Very likely", "Very serious", "Minor")

    def walk(self, lang):
        sid = self.start(lang=lang)
        self.keep_all(sid, lang=lang)
        self.rate_all(sid, lang=lang)
        return sid

    def test_english_pages_have_no_french_level_or_axis_names(self):
        sid = self.walk("en")
        for path in ("now", "results"):
            t = self.page(f"/quick/{sid}/{path}?lang=en")
            body = t.split("<main", 1)[1]
            for w in self.FRENCH_LEVELS:
                self.assertNotIn(w, body, (path, w))
        res = self.page(f"/quick/{sid}/results?lang=en")
        for w in ("Very serious", "Unlikely", "Very likely", "Likelihood", "Severity"):
            self.assertIn(w, res)
        self.assertNotIn("Almost certain", res)   # the map uses the words of the likelihood question
        self.assertRegex(res, r'<span class="lvl lvl-i\d">(High|Moderate|Low)</span>')

    def test_french_pages_keep_the_french_names_and_french_axes(self):
        sid = self.walk("fr")
        res = self.page(f"/quick/{sid}/results?lang=fr")
        body = res.split("<main", 1)[1]
        for w in ("Très sérieux", "Peu probable", "Très probable", "Gravité", "Vraisemblance"):
            self.assertIn(w, body)
        for w in ("Very serious", "Unlikely", "Very likely", "Quasi certain", ">Severity<", ">Likelihood<"):
            self.assertNotIn(w, body)
        self.assertRegex(res, r'<span class="lvl lvl-i\d">(Élevé|Modéré|Faible)</span>')

    def test_no_code_in_brackets_on_the_suggestion_line(self):
        sid = self.walk("en")
        for lang in ("en", "fr"):
            t = self.page(f"/quick/{sid}/now?lang={lang}")
            self.assertNotRegex(t, r"\(G[1-4]\b")
            self.assertNotIn("G4 Critique", t)
            self.assertIn("Keep our suggestion (", t) if lang == "en" else self.assertIn("Garder notre proposition (", t)

    def test_severity_words_agree_with_the_map_labels(self):
        self.assertEqual([engine.SEVERITY_WORDS["en"][n].split(":")[0] for n in (1, 2, 3, 4)],
                         [x["label_en"] for x in self.cal["severity"]])

    @unittest.skipUnless(HAVE_OPENPYXL, "openpyxl not installed")
    def test_the_xlsx_follows_the_page_language(self):
        import openpyxl
        for lang, expect, absent in (("en", "High", "Élevé"), ("fr", "Élevé", "High")):
            sid = self.walk(lang)
            self.page(f"/quick/{sid}/results?lang={lang}")  # sets the language cookie as the page does
            r = self.c.get(f"/s/{sid}/export.xlsx")
            self.assertEqual(r.status, 200)
            wb = openpyxl.load_workbook(io.BytesIO(r.body))
            cells = [str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None]
            self.assertIn(expect, cells, lang)
            self.assertNotIn(absent, cells, lang)
            self.assertIn(engine.HONESTY[lang], cells)
            if lang == "fr":
                self.assertIn("Registre des risques", wb.sheetnames)
                self.assertIn("Carte maintenant", wb.sheetnames)
            else:
                self.assertIn("Map now", wb.sheetnames)


class RoundTwoLayoutTest(Base):
    """F3: markup and style rules behind the layout fixes. (The real rendering was checked in headless Chrome.)"""

    def css(self):
        return (STATIC / "app.css").read_text(encoding="utf-8")

    def test_map_title_is_shown_once(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        t = self.page(f"/quick/{sid}/results")
        self.assertEqual(t.count("After your extra measures"), 1)
        self.assertEqual(t.count('<figcaption id="map-now">Now</figcaption>'), 1)
        self.assertEqual(len(re.findall(r"<svg[^>]*aria-labelledby=\"map-(now|after)\"", t)), 2)
        self.assertNotIn("<title>Now", t)
        self.assertNotRegex(t, r"<text[^>]*>(Now|After your extra measures)</text>")

    def test_legend_choice_summary_and_row_grid_rules_exist(self):
        css = self.css()
        self.assertRegex(css, r"fieldset\.q > legend \{[^}]*float: left;[^}]*width: 100%")
        self.assertRegex(css, r"fieldset\.q > legend \+ \* \{[^}]*clear: both")
        self.assertRegex(css, r"\.q label\.choice \{[^}]*display: grid;[^}]*grid-template-columns: auto minmax\(0, 1fr\)")
        self.assertRegex(css, r"\.choice \.c-t, \.choice \.c-d \{[^}]*grid-column: 2")
        self.assertRegex(css, r"details\.q > summary \.q-t[^{]*\{[^}]*display: inline")
        self.assertRegex(css, r"\.row-card \.blk\.sev \{[^}]*white-space: normal")  # the old nowrap `.sev` rule no longer leaks in
        self.assertRegex(css, r"@media \(max-width: 900px\) \{ \.row-grid \{ grid-template-columns: minmax\(0, 1fr\); \} \}")



class RoundTwoLogoTest(Base):
    """F4: a logo slot. app/static/brand/logo.svg is shown when it exists; nothing extra otherwise."""

    def test_no_logo_file_shows_nothing_extra(self):
        self.assertFalse((STATIC / "brand" / "logo.svg").exists())  # no logo file is created by this change
        for path in ("/", "/studies", "/quick/new"):
            t = self.page(path)
            self.assertNotIn("<img", t.split("</header>")[0])
            self.assertNotIn("logo.svg", t)
        self.assertEqual(self.c.get("/static/brand/logo.svg").status, 404)
        self.assertIn('<a class="brand" href="/">Atelier</a>', self.page("/"))

    def test_logo_file_is_shown_left_of_the_app_name(self):
        import atelier_app
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "brand").mkdir()
            svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
            (pathlib.Path(d) / "brand" / "logo.svg").write_bytes(svg)
            with mock.patch.object(atelier_app, "STATIC_DIR", pathlib.Path(d)):
                for path in ("/", "/studies", "/quick/new"):
                    head = self.page(path).split("</header>")[0]
                    m = re.search(r'<img class="logo" src="/static/brand/logo.svg" alt="CPLT" height="30">', head)
                    self.assertIsNotNone(m, path)
                    self.assertLess(m.start(), head.index("Atelier</a>"))
                r = self.c.get("/static/brand/logo.svg")
                self.assertEqual((r.status, r.get("Content-Type")), (200, "image/svg+xml"))
                self.assertEqual(r.body, svg)
                self.assertIn("/static/brand/logo.svg", self.c.text(Client(self.app).get("/login")))  # public pages too
        self.assertNotIn("<img", self.page("/").split("</header>")[0])  # and gone again when the file is gone

    def test_logo_css_height_is_28_to_32_px(self):
        css = (STATIC / "app.css").read_text(encoding="utf-8")
        m = re.search(r"header\.top \.brand img\.logo \{[^}]*height: (\d+)px", css)
        self.assertIsNotNone(m)
        self.assertTrue(28 <= int(m.group(1)) <= 32)


if __name__ == "__main__":
    unittest.main()
