"""Workshop 2 to 5 editors: round trips, links, engine refusals, engine severities, CSRF, escaping, navigation."""
import json
import re
import subprocess
import sys
import unittest
from unittest import mock

from app.tests import helpers
from app.tests.helpers import Client, make_app
from atelier_app import editors, engine, views

XSS = '"><script>alert(1)</script><img src=x onerror=alert(2)>'
ESCAPED = "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x onerror=alert(2)&gt;"

# one valid form per editor (against the guide example plus the objects added before it in this order)
VALID = {
    "ro": {"origin": "Insider", "objective": "Sell R&D data", "motivation": "3", "resources": "2",
           "decision": "selected", "feared_events": ["FE1"]},
    "sh": {"name": "Cloud host", "category": "supplier", "dependence": "3", "penetration": "2", "maturity": "2",
           "trust": "3", "critical": "yes"},
    "ss": {"risk_origin": "RO1", "feared_events": ["FE1", "FE2"], "new_path_label": "Through the cloud host",
           "new_path_stakeholder": "SH1"},
    "os": {"target": "SS1::SS1-P1", "likelihood": "3", "description": "Phishing, then exfiltration"},
    "rk": {"scenario": "ss::SS1", "label": "New risk", "likelihood": "3", "likelihood_target": "1",
           "treatment": "reduce", "owner": "CISO"},
    "ms": {"label": "Egress filtering", "risks": ["R1"], "owner": "IT", "due": "2027-01-31", "status": "planned"},
}
WS = {slug: spec[1] for slug, spec in editors.SPECS.items()}


class EditorTest(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)
        self.c.login()
        self.sid = self.c.load_example()

    def tearDown(self):
        helpers.cleanup(self.dir)

    def page(self, path):
        r = self.c.get(path)
        self.assertEqual(r.status, 200, path)
        return self.c.text(r)

    def st(self):
        return self.app.store.load(self.sid)

    def raw(self):
        return (self.app.store.dir / f"{self.sid}.json").read_bytes()

    def post(self, slug, form, eid="add"):
        p = f"/s/{self.sid}/w{WS[slug]}"
        return self.c.post_csrf(f"{p}/{slug}/{eid}", form, page=p)

    def add(self, slug, form):
        r = self.post(slug, form)
        self.assertEqual(r.status, 303, self.c.text(r)[:3000])
        m = re.search(r"hl=([^#&]+)", r.get("Location"))
        return m.group(1)

    def assert_refused(self, slug, form, eid="add", contains=None):
        before = self.raw()
        r = self.post(slug, form, eid)
        self.assertEqual(r.status, 400, (slug, form))
        if contains:
            self.assertIn(contains, self.c.text(r))
        self.assertEqual(self.raw(), before, "the file must not change on a refused form")
        return self.c.text(r)

    def find(self, key, eid):
        return next(x for x in self.st()[key] if x["id"] == eid)

    # --- round trips ---

    def test_risk_origin_round_trip(self):
        eid = self.add("ro", VALID["ro"])
        self.assertEqual(self.find("risk_origins", eid), {"id": "RO3", "origin": "Insider", "objective": "Sell R&D data",
                                                          "motivation": 3, "resources": 2, "decision": "selected",
                                                          "feared_events": ["FE1"]})
        self.assertIn('id="el-RO3" class="hl"', self.page(f"/s/{self.sid}/w2?hl=RO3"))
        self.assertEqual(self.page(f"/s/{self.sid}/w2/ro/RO3").count('value="FE1" checked'), 1)
        r = self.post("ro", {"origin": "Insider", "decision": "discarded", "feared_events": ["FE2", "FE3"]}, "RO3")
        self.assertEqual(r.status, 303)
        self.assertEqual(self.find("risk_origins", "RO3"),
                         {"id": "RO3", "origin": "Insider", "decision": "discarded", "feared_events": ["FE2", "FE3"]})
        r = self.post("ro", {}, "RO3/delete")
        self.assertEqual(r.status, 303)
        self.assertNotIn("RO3", [x["id"] for x in self.st()["risk_origins"]])

    def test_stakeholder_round_trip(self):
        eid = self.add("sh", VALID["sh"])
        self.assertEqual(self.find("stakeholders", eid),
                         {"id": "SH4", "name": "Cloud host", "category": "supplier", "dependence": 3, "penetration": 2,
                          "maturity": 2, "trust": 3, "critical": True})
        t = self.page(f"/s/{self.sid}/w3/sh/SH4")
        self.assertIn('name="critical" value="yes" checked', t)
        self.assertIn('<option value="supplier">', t)  # category suggestions come from the study itself
        self.assertEqual(self.post("sh", {"name": "Cloud host 2", "trust": "4"}, "SH4").status, 303)
        self.assertEqual(self.find("stakeholders", "SH4"),
                         {"id": "SH4", "name": "Cloud host 2", "trust": 4, "critical": False})
        self.assertEqual(self.post("sh", {}, "SH4/delete").status, 303)
        self.assertNotIn("SH4", [x["id"] for x in self.st()["stakeholders"]])

    def test_strategic_scenario_round_trip_with_paths(self):
        eid = self.add("ss", VALID["ss"])
        ss = self.find("strategic_scenarios", eid)
        self.assertEqual(ss, {"id": "SS4", "risk_origin": "RO1", "feared_events": ["FE1", "FE2"], "severity": 4,
                              "paths": [{"id": "SS4-P1", "label": "Through the cloud host", "stakeholder": "SH1"}]})
        # relabel P1 and drop its stakeholder, add P2
        r = self.post("ss", {"risk_origin": "RO2", "feared_events": ["FE1"], "path_id": ["SS4-P1"],
                             "path_label": ["Direct"], "path_stakeholder": [""], "new_path_label": "Via the lab",
                             "new_path_stakeholder": "SH2"}, "SS4")
        self.assertEqual(r.status, 303, self.c.text(r)[:2000])
        ss = self.find("strategic_scenarios", "SS4")
        self.assertEqual(ss["paths"], [{"id": "SS4-P1", "label": "Direct"},
                                       {"id": "SS4-P2", "label": "Via the lab", "stakeholder": "SH2"}])
        self.assertEqual((ss["risk_origin"], ss["feared_events"], ss["severity"]), ("RO2", ["FE1"], 3))
        # remove P1
        r = self.post("ss", {"risk_origin": "RO2", "feared_events": ["FE1"], "path_id": ["SS4-P1", "SS4-P2"],
                             "path_label": ["Direct", "Via the lab"], "path_stakeholder": ["", "SH2"],
                             "path_remove": ["SS4-P1"]}, "SS4")
        self.assertEqual(r.status, 303)
        self.assertEqual([p["id"] for p in self.find("strategic_scenarios", "SS4")["paths"]], ["SS4-P2"])
        self.assertEqual(self.post("ss", {}, "SS4/delete").status, 303)
        self.assertNotIn("SS4", [x["id"] for x in self.st()["strategic_scenarios"]])

    def test_path_used_by_an_operational_scenario_cannot_be_removed(self):
        self.add("os", VALID["os"])
        ss = self.find("strategic_scenarios", "SS1")
        form = {"risk_origin": "RO1", "feared_events": ["FE1"], "path_id": [p["id"] for p in ss["paths"]],
                "path_label": [p["label"] for p in ss["paths"]], "path_stakeholder": [p.get("stakeholder", "") for p in ss["paths"]],
                "path_remove": ["SS1-P1"]}
        self.assert_refused("ss", form, "SS1", "SS1-P1 is used by OS1")

    def test_operational_scenario_round_trip(self):
        t = self.page(f"/s/{self.sid}/w4")
        cal = engine.load_cal("anssi-v1.5")
        picker = re.search(r'<select name="likelihood" required>(.*?)</select>', t, re.S).group(1)
        self.assertEqual(re.findall(r'<option value="(\d)">([^<]+)</option>', picker),
                         [(str(x["n"]), f'{x["code"]} {x["label"]}') for x in cal["likelihood"]])
        eid = self.add("os", VALID["os"])
        self.assertEqual(self.find("operational_scenarios", eid),
                         {"id": "OS1", "strategic_scenario": "SS1", "path": "SS1-P1", "likelihood": 3,
                          "description": "Phishing, then exfiltration"})
        t = self.page(f"/s/{self.sid}/w4")
        self.assertIn(f"{cal['likelihood'][2]['code']} {cal['likelihood'][2]['label']}", t)
        self.assertEqual(self.post("os", {"target": "SS2::", "likelihood": "2"}, "OS1").status, 303)
        self.assertEqual(self.find("operational_scenarios", "OS1"),
                         {"id": "OS1", "strategic_scenario": "SS2", "likelihood": 2})
        self.assertEqual(self.post("os", {}, "OS1/delete").status, 303)
        self.assertEqual(self.st().get("operational_scenarios"), [])

    def test_risk_round_trip(self):
        eid = self.add("rk", VALID["rk"])
        self.assertEqual(self.find("risks", eid),
                         {"id": "R6", "strategic_scenario": "SS1", "label": "New risk", "likelihood": 3,
                          "likelihood_target": 1, "treatment": "reduce", "owner": "CISO", "severity": 3})
        self.add("os", {"target": "SS2::SS2-P1", "likelihood": "2"})
        r = self.post("rk", {"scenario": "os::OS1", "label": "New risk, operational", "likelihood": "2"}, "R6")
        self.assertEqual(r.status, 303)
        self.assertEqual(self.find("risks", "R6"),
                         {"id": "R6", "operational_scenario": "OS1", "label": "New risk, operational", "likelihood": 2,
                          "severity": 4})
        self.assertEqual(self.post("rk", {}, "R6/delete").status, 303)
        self.assertNotIn("R6", [x["id"] for x in self.st()["risks"]])

    def test_measure_round_trip(self):
        eid = self.add("ms", VALID["ms"])
        self.assertEqual(self.find("measures", eid), {"id": "M1", "label": "Egress filtering", "risks": ["R1"],
                                                     "owner": "IT", "due": "2027-01-31", "status": "planned"})
        t = self.page(f"/s/{self.sid}/w5/ms/M1")
        self.assertIn('type="date" name="due" value="2027-01-31"', t)
        self.assertEqual(self.post("ms", {"label": "Egress filtering", "risks": ["R1", "R2"], "status": "done"}, "M1").status, 303)
        self.assertEqual(self.find("measures", "M1"), {"id": "M1", "label": "Egress filtering", "risks": ["R1", "R2"],
                                                      "status": "done"})
        self.assertEqual(self.post("ms", {}, "M1/delete").status, 303)
        self.assertEqual(self.st()["measures"], [])
        self.assert_refused("ms", dict(VALID["ms"], due="31/01/2027"), contains="due date must be a date")
        self.assert_refused("ms", dict(VALID["ms"], status="finished"), contains="status must be one of")

    def test_unknown_fields_survive_an_edit(self):
        st = self.st()
        st["risk_origins"][0]["note"] = "kept"
        st["strategic_scenarios"][0]["paths"][0]["note"] = "kept too"
        self.app.store.save(self.sid, st)
        self.assertEqual(self.post("ro", {"origin": "Competitor", "decision": "selected", "feared_events": ["FE1"]}, "RO1").status, 303)
        self.assertEqual(self.find("risk_origins", "RO1")["note"], "kept")
        ss = self.find("strategic_scenarios", "SS1")
        form = {"risk_origin": "RO1", "feared_events": ["FE1"], "path_id": [p["id"] for p in ss["paths"]],
                "path_label": [p["label"] for p in ss["paths"]], "path_stakeholder": [p.get("stakeholder", "") for p in ss["paths"]]}
        self.assertEqual(self.post("ss", form, "SS1").status, 303)
        self.assertEqual(self.find("strategic_scenarios", "SS1")["paths"][0]["note"], "kept too")
        self.assertIn("kept", self.page(f"/s/{self.sid}/w2"))

    def test_slug_must_match_its_workshop(self):
        p = f"/s/{self.sid}/w2"
        self.assertEqual(self.c.post_csrf(f"/s/{self.sid}/w2/ss/add", VALID["ss"], page=p).status, 404)
        self.assertEqual(self.c.get(f"/s/{self.sid}/w4/rk/R1").status, 404)
        self.assertEqual(self.c.get(f"/s/{self.sid}/w5/rk/NOPE").status, 404)
        self.assertEqual(self.c.get(f"/s/{self.sid}/w5/xx/R1").status, 404)

    # --- links only to existing ids of the right type ---

    def test_links_only_to_existing_ids_of_the_right_type(self):
        self.add("os", VALID["os"])
        bad = [
            ("ro", dict(VALID["ro"], feared_events=["BV1"])), ("ro", dict(VALID["ro"], feared_events=["FE9"])),
            ("ss", dict(VALID["ss"], risk_origin="FE1")), ("ss", dict(VALID["ss"], risk_origin="RO9")),
            ("ss", dict(VALID["ss"], feared_events=["RO1"])), ("ss", dict(VALID["ss"], feared_events=[])),
            ("ss", dict(VALID["ss"], new_path_stakeholder="RO1")), ("ss", dict(VALID["ss"], new_path_stakeholder="SH9")),
            ("os", dict(VALID["os"], target="SS1::SS2-P1")), ("os", dict(VALID["os"], target="SS9::")),
            ("os", dict(VALID["os"], target="RO1::")), ("os", dict(VALID["os"], target="")),
            ("rk", dict(VALID["rk"], scenario="ss::OS1")), ("rk", dict(VALID["rk"], scenario="os::SS1")),
            ("rk", dict(VALID["rk"], scenario="ss::SS9")), ("rk", dict(VALID["rk"], scenario="")),
            ("ms", dict(VALID["ms"], risks=["SS1"])), ("ms", dict(VALID["ms"], risks=["R9"])),
        ]
        for slug, form in bad:
            with self.subTest(slug=slug, form=form):
                self.assert_refused(slug, form)
        # an existing path id from the edit form must belong to the scenario being edited
        self.assert_refused("ss", {"risk_origin": "RO1", "feared_events": ["FE1"], "path_id": ["SS2-P1"],
                                   "path_label": ["x"], "path_stakeholder": [""]}, "SS1", "unknown path")
        # pickers offer only ids of the right type
        t = self.page(f"/s/{self.sid}/w5")
        picker = re.search(r'<select name="scenario" required>(.*?)</select>', t, re.S).group(1)
        self.assertEqual(re.findall(r'<option value="([^"]*)"', picker),
                         ["", "ss::SS1", "ss::SS2", "ss::SS3", "os::OS1"])

    # --- 1-4 scale: the engine refuses, the UI shows it ---

    def test_value_outside_1_to_4_refused_by_the_engine(self):
        self.add("os", VALID["os"])
        cases = [("ro", "motivation", "add"), ("ro", "resources", "RO1"), ("sh", "dependence", "add"),
                 ("sh", "penetration", "SH1"), ("sh", "maturity", "add"), ("sh", "trust", "add"),
                 ("os", "likelihood", "add"), ("os", "likelihood", "OS1"), ("rk", "likelihood", "add"),
                 ("rk", "likelihood_target", "R1")]
        engine_words = {"likelihood_target": "target likelihood"}
        for slug, field, eid in cases:
            for v in ("0", "5", "-1", "44"):
                with self.subTest(slug=slug, field=field, eid=eid, v=v):
                    form = dict(VALID[slug])
                    if eid == "R1":
                        form["scenario"] = "ss::SS1"
                    form[field] = v
                    t = self.assert_refused(slug, form, eid, "The engine refused the value:")
                    self.assertIn(f"{engine_words.get(field, field)} {int(v)} out of scale 1-4", t)
        # not a number at all: the form refuses before the engine is asked
        self.assert_refused("ro", dict(VALID["ro"], motivation="high"), contains="motivation must be a whole number")

    def test_scale_refusal_comes_from_the_engine(self):
        """With the engine's check silenced, the app itself lets 7 through: the refusal is the engine's."""
        real = engine.study_mod.validate

        def lenient(st, cal):
            r = real(st, cal)
            return {"errors": [e for e in r["errors"] if "out of scale" not in e], "warnings": r["warnings"]}
        with mock.patch.object(engine.study_mod, "validate", lenient):
            self.assertEqual(self.post("ro", dict(VALID["ro"], motivation="7")).status, 303)
        self.assertEqual(self.find("risk_origins", "RO3")["motivation"], 7)

    # --- severities come from the engine ---

    def test_scenario_and_risk_severity_from_the_engine_not_the_form(self):
        eid = self.add("ss", dict(VALID["ss"], severity="1"))
        self.assertEqual(self.find("strategic_scenarios", eid)["severity"], 4)
        r = self.post("ss", {"risk_origin": "RO1", "feared_events": ["FE1"], "severity": "4", "path_id": ["SS4-P1"],
                             "path_label": ["x"], "path_stakeholder": [""]}, "SS4")
        self.assertEqual(r.status, 303)
        self.assertEqual(self.find("strategic_scenarios", "SS4")["severity"], 3)
        rid = self.add("rk", dict(VALID["rk"], scenario="ss::SS2", severity="1"))
        self.assertEqual(self.find("risks", rid)["severity"], 4)
        self.assertEqual(self.post("rk", dict(VALID["rk"], scenario="ss::SS4", severity="4"), rid).status, 303)
        self.assertEqual(self.find("risks", rid)["severity"], 3)
        # no severity input in either form
        for path in (f"/s/{self.sid}/w3", f"/s/{self.sid}/w3/ss/SS4", f"/s/{self.sid}/w5", f"/s/{self.sid}/w5/rk/{rid}"):
            self.assertNotIn('name="severity"', self.page(path), path)
        # the engine CLI agrees: the stored study validates without errors
        out = subprocess.run([sys.executable, "-m", "atelier_engine", "validate", str(self.app.store.dir / f"{self.sid}.json")],
                             cwd=helpers.ENGINE, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertEqual(json.loads(out.stdout)["errors"], [])

    def test_severity_is_whatever_the_engine_accepts(self):
        """Swap in an engine whose check accepts only severity 2: the app stores 2. The app has no rule of its own."""
        real = engine.study_mod.validate

        def only_two(st, cal):
            r = real(st, cal)
            errs = [e for e in r["errors"] if not re.match(r"(SS|R)\d+: severity ", e)]
            for key in ("strategic_scenarios", "risks"):
                for x in st.get(key) or []:
                    if x.get("severity") != 2:
                        errs.append(f"{x['id']}: severity {x.get('severity')} is not 2")
            return {"errors": errs, "warnings": r["warnings"]}
        with mock.patch.object(engine.study_mod, "validate", only_two):
            sid_ss = self.add("ss", VALID["ss"])
            sid_rk = self.add("rk", VALID["rk"])
        self.assertEqual(self.find("strategic_scenarios", sid_ss)["severity"], 2)
        self.assertEqual(self.find("risks", sid_rk)["severity"], 2)

    def test_stale_severity_shows_the_engine_check_and_can_be_taken_from_the_engine(self):
        p1 = f"/s/{self.sid}/w1"
        r = self.c.post_csrf(f"{p1}/fe/FE1", {"business_value": "BV1", "label": "R&D information stolen",
                                              "criterion": "confidentiality", "severity": "4"}, page=p1)
        self.assertEqual(r.status, 303)
        chk = engine.check(self.st())
        want = "SS1: severity 3 but its feared events reach 4 (severity comes from the feared events, guide p.49)"
        self.assertIn(want, chk["errors"])
        t = self.page(f"/s/{self.sid}/w3")
        row = re.search(r'<tr id="el-SS1">(.*?)</tr>', t, re.S).group(1)
        self.assertIn('<span class="sev">G4 ', row)  # the engine's value
        self.assertIn(views.esc(want), row)  # and its check result
        self.assertIn("stored: G3 ", row)
        self.assertIn("Take the severities from the engine", t)
        r = self.c.post_csrf(f"/s/{self.sid}/severities", {"back": "w3"}, page=f"/s/{self.sid}/w3")
        self.assertEqual(r.get("Location"), f"/s/{self.sid}/w3?f=synced")
        st = self.st()
        self.assertEqual(self.find("strategic_scenarios", "SS1")["severity"], 4)
        self.assertEqual([x["severity"] for x in st["risks"] if x.get("strategic_scenario") == "SS1"], [4, 4, 4])
        self.assertEqual(engine.check(st)["errors"], [])
        self.assertIn("engine check passed", self.page(f"/s/{self.sid}/w3"))
        r = self.c.post_csrf(f"/s/{self.sid}/severities", {"back": "w5"}, page=f"/s/{self.sid}/w5")
        self.assertEqual(r.get("Location"), f"/s/{self.sid}/w5?f=unchanged")
        self.assertEqual(self.c.post_csrf(f"/s/{self.sid}/severities", {"back": "//evil"}).status, 400)

    def test_engine_value_sets_match_the_pickers(self):
        self.assertEqual(set(editors.DECISIONS), engine.DECISIONS)
        self.assertEqual(set(editors.TREATMENTS), engine.TREATMENTS)
        self.assertEqual(set(editors.MEASURE_STATUS), engine.MEASURE_STATUS)

    # --- CSRF and escaping on every new form ---

    def test_csrf_on_every_new_form(self):
        self.add("os", VALID["os"])
        self.add("ms", VALID["ms"])
        ids = {"ro": "RO1", "sh": "SH1", "ss": "SS1", "os": "OS1", "rk": "R1", "ms": "M1"}
        posts = [(f"/s/{self.sid}/severities", {"back": "w3"})]
        for slug, eid in ids.items():
            base = f"/s/{self.sid}/w{WS[slug]}/{slug}"
            posts += [(f"{base}/add", VALID[slug]), (f"{base}/{eid}", VALID[slug]), (f"{base}/{eid}/delete", {})]
        for path, form in posts:
            for token in (None, "wrong"):
                with self.subTest(path=path, token=token):
                    before = self.raw()
                    f = dict(form)
                    if token:
                        f["csrf"] = token
                    r = self.c.post(path, f)
                    self.assertEqual(r.status, 403, path)
                    self.assertEqual(self.raw(), before)
        self.assertEqual(len(posts), 19)

    def test_xss_escaped_on_every_new_form(self):
        self.add("ro", {"origin": XSS, "objective": XSS, "decision": "selected"})
        self.add("sh", {"name": XSS, "category": XSS})
        self.add("ss", {"risk_origin": "RO1", "feared_events": ["FE1"], "new_path_label": XSS})
        self.add("os", {"target": "SS1::SS1-P1", "likelihood": "2", "description": XSS})
        self.add("rk", {"scenario": "ss::SS1", "label": XSS, "likelihood": "2", "owner": XSS})
        self.add("ms", {"label": XSS, "owner": XSS, "status": "planned", "risks": ["R6"]})
        st = self.st()
        self.assertEqual(self.find("stakeholders", "SH4")["name"], XSS)
        pages = [f"/s/{self.sid}/w{n}" for n in (2, 3, 4, 5)] + [
            f"/s/{self.sid}/w2/ro/RO3", f"/s/{self.sid}/w3/sh/SH4", f"/s/{self.sid}/w3/ss/SS4",
            f"/s/{self.sid}/w4/os/OS1", f"/s/{self.sid}/w5/rk/R6", f"/s/{self.sid}/w5/ms/M1", f"/s/{self.sid}/register"]
        for path in pages + [f"/s/{self.sid}"]:  # the overview shows no labels, so only the negative check there
            with self.subTest(path=path):
                t = self.page(path)
                self.assertNotIn("<script>alert", t)
                self.assertNotIn("<img src=x", t)
                if path in pages:
                    self.assertIn(ESCAPED, t)
        self.assertEqual(st["strategic_scenarios"][-1]["paths"][0]["label"], XSS)

    def test_no_inline_script_or_style_on_new_pages(self):
        self.add("os", VALID["os"])
        self.add("ms", VALID["ms"])
        for p in [f"/s/{self.sid}/w{n}" for n in (2, 3, 4, 5)] + [
                f"/s/{self.sid}/w2/ro/RO1", f"/s/{self.sid}/w3/sh/SH1", f"/s/{self.sid}/w3/ss/SS1",
                f"/s/{self.sid}/w4/os/OS1", f"/s/{self.sid}/w5/rk/R1", f"/s/{self.sid}/w5/ms/M1"]:
            t = self.page(p)
            self.assertNotRegex(t, r"<script(?![^>]*\bsrc=)", p)
            self.assertNotIn(" style=", t, p)
            self.assertNotRegex(t, r"\son[a-z]+=", p)

    # --- W5 grids: now and at target, from the engine's register ---

    def test_w5_grids_now_and_target_from_the_engine_register(self):
        st = self.st()
        st["risks"][0]["likelihood_target"] = 1
        st["risks"][3]["likelihood_target"] = 1
        st["measures"] = [{"id": "M1", "label": "x", "risks": ["R1", "R4"], "owner": "IT", "due": "2027-01-31",
                           "status": "planned"}]
        self.app.store.save(self.sid, st)
        out = subprocess.run([sys.executable, "-m", "atelier_engine", "register", str(self.app.store.dir / f"{self.sid}.json")],
                             cwd=helpers.ENGINE, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)
        cli = json.loads(out.stdout)["risks"]
        cal = engine.load_cal("anssi-v1.5")
        cls = views.level_classes(cal)
        for path in (f"/s/{self.sid}/w5", f"/s/{self.sid}/register"):
            t = self.page(path)
            self.assertLess(t.index("<figcaption>Now</figcaption>"), t.index("<figcaption>At target</figcaption>"))
            for cap, lk, lvl in (("Now", "likelihood", "level"), ("At target", "likelihood_target", "level_target")):
                grid = t.split(f"<figcaption>{cap}</figcaption>")[1].split("</figure>")[0]
                placed = {}
                for code, tds in re.findall(r'<tr><th scope="row">(G\d).*?</th>(.*?)</tr>', grid, re.S):
                    for v, (klass, td) in enumerate(re.findall(r'<td class="([^"]+)">(.*?)</td>', tds, re.S), start=1):
                        for rid in re.findall(r'class="chip"[^>]*>([^<]+)</a>', td):
                            placed[rid] = (int(code[1]), v, klass)
                want = {r["id"]: (r["severity"], r[lk], cls[r[lvl]]) for r in cli if r.get(lk)}
                self.assertEqual(placed, want, (path, cap))
            self.assertIn("No target likelihood yet for R2, R3, R5", t)

    def test_w5_grid_waits_for_a_study_without_errors(self):
        st = self.st()
        st["risks"][0]["likelihood"] = 9
        self.app.store.save(self.sid, st)
        t = self.page(f"/s/{self.sid}/w5")
        self.assertIn("The engine draws the grid only for a study without errors", t)
        self.assertNotIn("<figcaption>Now</figcaption>", t)


class NavigationTest(unittest.TestCase):
    """Every engine error and warning links to its row, in the right workshop tab, highlighted."""

    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)
        self.c.login()
        st = helpers.example_json()
        st["risk_origins"][0]["feared_events"] = ["FE9"]              # W2 error
        st["risk_origins"][1]["decision"] = "monitoring"              # W3 warning (SS2, SS3 built on it)
        st["stakeholders"][0]["dependence"] = 6                       # W3 error
        st["strategic_scenarios"][0]["severity"] = 2                  # W3 error
        st["strategic_scenarios"][0]["paths"][1]["stakeholder"] = "SH9"  # W3 path error
        st["operational_scenarios"] = [{"id": "OS1", "strategic_scenario": "SS9", "likelihood": 2}]  # W4 error
        st["risks"][4]["likelihood_target"] = 0                       # W5 error
        st["measures"] = [{"id": "M1", "label": "x", "risks": ["R9"], "status": "planned"}]  # W5 error and warning
        st["feared_events"].append({"id": "FE4", "business_value": "BV1", "label": "y", "severity": 4})  # W1 warning
        st["risks"].append({"label": "no id", "severity": 1, "likelihood": 1})  # collection-level error
        self.sid = self.app.store.create(st)
        self.st = self.app.store.load(self.sid)
        self.chk = engine.check(self.st)

    def tearDown(self):
        helpers.cleanup(self.dir)

    def test_every_message_links_to_its_row_highlighted(self):
        msgs = self.chk["errors"] + self.chk["warnings"]
        self.assertGreaterEqual(len(msgs), 10, msgs)
        idx = views.element_index(self.st)
        panel = self.c.text(self.c.get(f"/s/{self.sid}"))
        seen_ws = set()
        for m in msgs:
            with self.subTest(m=m):
                t, n = views.message_target(m, idx)
                self.assertIsNotNone(n, m)
                seen_ws.add(n)
                li = re.search(r'<li class="(?:err|wrn)">' + re.escape(views.esc(m)) + r' <a class="goto" href="([^"]+)">', panel)
                self.assertIsNotNone(li, m)
                href = li.group(1)
                if t is None:  # message about a whole collection: its workshop tab
                    self.assertEqual(href, f"/s/{self.sid}/w{n}")
                    continue
                self.assertEqual(href, f"/s/{self.sid}/el/{views.q(t)}")
                r = self.c.get(href)
                self.assertEqual(r.status, 303)
                loc = r.get("Location")
                self.assertEqual(loc, f"/s/{self.sid}/w{n}?hl={views.q(t)}#el-{views.q(t)}")
                key = idx[t][0]
                self.assertEqual(n, views.WORKSHOP_OF[key])
                page = self.c.text(self.c.get(loc))
                self.assertRegex(page, rf'<(tr|li) id="el-{re.escape(views.q(t))}" class="hl">')
                self.assertEqual(page.count('class="hl"'), 1)
        self.assertEqual(seen_ws, {1, 2, 3, 4, 5})

    def test_progress_strip_counts_the_engine_messages(self):
        t = self.c.text(self.c.get(f"/s/{self.sid}"))
        strip = re.search(r'<ol class="progress" id="progress">(.*?)</ol>', t, re.S).group(1)
        cells = re.findall(r'<b>W(\d)</b><span class="ps-n">(\d+) objects?</span><span class="ps-c">(\d+) errors?, '
                           r'(\d+) warnings?</span>', strip)
        self.assertEqual([c[0] for c in cells], ["1", "2", "3", "4", "5"])
        prog = views.progress(self.st, self.chk, views.element_index(self.st))
        for n, objs, e, w in cells:
            keys = views.WORKSHOPS[int(n)][1]
            self.assertEqual(int(objs), sum(len(self.st.get(k) or []) for k in keys))
            self.assertEqual((int(e), int(w)), (prog[int(n)]["errors"], prog[int(n)]["warnings"]))
        self.assertEqual(sum(int(c[2]) for c in cells) + prog["other"]["errors"], len(self.chk["errors"]))
        self.assertEqual(sum(int(c[3]) for c in cells) + prog["other"]["warnings"], len(self.chk["warnings"]))
        self.assertEqual(prog["other"], {"objects": 0, "errors": 0, "warnings": 0})
        w3 = next(c for c in cells if c[0] == "3")
        # W3: errors SH1 dependence, SS1 severity, SS1/SS1-P2 stakeholder; warnings SS2 and SS3 on RO2
        self.assertEqual((w3[2], w3[3]), ("3", "2"))
        self.assertIn('class="ps-bad"', strip)


if __name__ == "__main__":
    unittest.main()
