"""A refused form comes back with what the user typed and the message next to the field (all W1-W5 forms).

Each case posts one form with one refused value and several typed values, then checks: status 400, the study file
unchanged, every typed value back in the form, the refusal inside the label (or fieldset) of its field.
"""
import html as htmlmod
import re
import unittest

from app.tests import helpers
from app.tests.helpers import Client, make_app


def form_of(page, action):
    i = page.index(f'action="{action}"')
    start = page.rfind("<form", 0, i)
    return page[start:page.index("</form>", i) + 7]


def msg_next_to(form, name):
    """The field-error text inside the label (or fieldset) that holds the field `name`, or None."""
    i = form.index(f'name="{name}"')
    fs_start, lab_start = form.rfind("<fieldset", 0, i), form.rfind("<label", 0, i)
    if fs_start > form.rfind("</fieldset>", 0, i) and form.find('class="check"', lab_start, i) != -1:
        seg = form[fs_start:form.index("</fieldset>", i)]  # a checkbox list: the message sits under the legend
    else:
        seg = form[i:form.index("</label>", i)]
    m = re.search(r'<span class="field-error" role="alert">([^<]*)</span>', seg)
    return htmlmod.unescape(m.group(1)) if m else None


def selected(form, name):
    m = re.search(rf'<select name="{name}"[^>]*>(.*?)</select>', form, re.S)
    return re.findall(r'<option value="([^"]*)" selected>', m.group(1)) if m else None


def value_of(form, name):
    m = re.search(rf'name="{name}"[^>]*? value="([^"]*)"', form)
    return htmlmod.unescape(m.group(1)) if m else None


def checked(form, name):
    return re.findall(rf'<input type="checkbox" name="{name}" value="([^"]*)" checked>', form)


class StickyFormsTest(unittest.TestCase):
    def setUp(self):
        self.app, self.d = make_app()
        self.c = Client(self.app)
        self.c.login()
        self.sid = self.c.load_example()
        self.csrf = self.c.csrf()

    def tearDown(self):
        helpers.cleanup(self.d)

    def file_bytes(self):
        return (self.app.store.dir / f"{self.sid}.json").read_bytes()

    def refused(self, path, form, action=None):
        before = self.file_bytes()
        r = self.c.post(path, dict(form, csrf=self.csrf))
        self.assertEqual(r.status, 400, path)
        self.assertEqual(self.file_bytes(), before, "the study file changed after a refusal")
        page = self.c.text(r)
        self.assertIn("Not saved.", page)
        return form_of(page, action or path)

    # ---------- W1 ----------

    def test_w1_business_value_add(self):
        f = self.refused(f"/s/{self.sid}/w1/bv/add", {"label": "", "nature": "process", "owner": "Typed owner <b>"})
        self.assertEqual(msg_next_to(f, "label"), "label is required")
        self.assertEqual(value_of(f, "owner"), "Typed owner <b>")
        self.assertIn("Typed owner &lt;b&gt;", f)
        self.assertEqual(selected(f, "nature"), ["process"])

    def test_w1_supporting_asset_add(self):
        f = self.refused(f"/s/{self.sid}/w1/sa/add", {"label": "Typed asset", "business_values": ["BV1", "BV99"]})
        self.assertEqual(msg_next_to(f, "business_values"), "pick business values from the list")
        self.assertEqual(value_of(f, "label"), "Typed asset")
        self.assertEqual(checked(f, "business_values"), ["BV1"])

    def test_w1_feared_event_add_out_of_scale_severity(self):
        f = self.refused(f"/s/{self.sid}/w1/fe/add", {"business_value": "BV2", "label": "Typed event",
                                                      "criterion": "integrity", "severity": "7"})
        self.assertEqual(msg_next_to(f, "severity"), "pick a severity from the calibration's scale")
        self.assertEqual(selected(f, "severity"), ["7"])
        self.assertIn("7 (not in the scale)", f)
        self.assertEqual(selected(f, "business_value"), ["BV2"])
        self.assertEqual((value_of(f, "label"), value_of(f, "criterion")), ("Typed event", "integrity"))
        self.assertIsNone(msg_next_to(f, "label"))

    def test_w1_baseline_add(self):
        f = self.refused(f"/s/{self.sid}/w1/bl/add", {"reference": "Typed reference", "status": "bogus",
                                                      "gap": "Typed gap"})
        self.assertEqual(msg_next_to(f, "status"), "unknown status")
        self.assertEqual(selected(f, "status"), ["bogus"])
        self.assertEqual((value_of(f, "reference"), value_of(f, "gap")), ("Typed reference", "Typed gap"))

    def test_w1_feared_event_edit(self):
        f = self.refused(f"/s/{self.sid}/w1/fe/FE1", {"business_value": "BV9", "label": "Edited label",
                                                      "criterion": "availability", "severity": "2"})
        self.assertEqual(msg_next_to(f, "business_value"), "pick the business value from the list")
        self.assertEqual(selected(f, "severity"), ["2"])
        self.assertEqual(selected(f, "business_value"), ["BV9"])
        self.assertEqual(value_of(f, "label"), "Edited label")

    # ---------- W2 ----------

    def ro2(self, **kw):
        ro = next(x for x in helpers.example_json()["risk_origins"] if x["id"] == "RO2")
        form = {"origin": "Edited origin", "objective": "Edited objective", "motivation": "3", "resources": "4",
                "decision": "monitoring", "feared_events": ro["feared_events"][:1]}
        form.update(kw)
        return form

    def test_w2_engine_refusal_keeps_input(self):
        f = self.refused(f"/s/{self.sid}/w2/ro/RO2", self.ro2(motivation="5"))
        self.assertEqual(msg_next_to(f, "motivation"),
                         "The engine refused the value: RO2: motivation 5 out of scale 1-4")
        self.assertEqual(selected(f, "motivation"), ["5"])
        self.assertIn("5 (not in the scale)", f)
        self.assertEqual(selected(f, "resources"), ["4"])
        self.assertEqual(selected(f, "decision"), ["monitoring"])
        self.assertEqual((value_of(f, "origin"), value_of(f, "objective")), ("Edited origin", "Edited objective"))
        self.assertEqual(checked(f, "feared_events"), self.ro2()["feared_events"])
        self.assertIsNone(msg_next_to(f, "resources"))

    def test_w2_add_engine_refusal(self):
        f = self.refused(f"/s/{self.sid}/w2/ro/add", self.ro2(resources="9", origin="New origin"))
        self.assertEqual(msg_next_to(f, "resources"), "The engine refused the value: RO3: resources 9 out of scale 1-4")
        self.assertEqual(value_of(f, "origin"), "New origin")
        self.assertEqual(selected(f, "resources"), ["9"])

    def test_w2_app_refusal_missing_decision(self):
        f = self.refused(f"/s/{self.sid}/w2/ro/RO2", self.ro2(decision=""))
        self.assertEqual(msg_next_to(f, "decision"), "pick a decision")
        self.assertEqual(value_of(f, "origin"), "Edited origin")

    # ---------- W3 ----------

    def test_w3_stakeholder_add_engine_refusal(self):
        f = self.refused(f"/s/{self.sid}/w3/sh/add", {"name": "Typed partner", "category": "Typed category",
                                                      "dependence": "0", "penetration": "2", "maturity": "3",
                                                      "trust": "1", "critical": "yes"})
        self.assertEqual(msg_next_to(f, "dependence"), "The engine refused the value: SH4: dependence 0 out of scale 1-4")
        self.assertEqual(value_of(f, "name"), "Typed partner")
        self.assertEqual((selected(f, "penetration"), selected(f, "maturity"), selected(f, "trust")),
                         (["2"], ["3"], ["1"]))
        self.assertIn('name="critical" value="yes" checked', f)

    def test_w3_strategic_scenario_edit_keeps_paths(self):
        ss = next(x for x in helpers.example_json()["strategic_scenarios"] if x["id"] == "SS1")
        pids = [p["id"] for p in ss["paths"]]
        labels = [f"Typed label {i}" for i in range(len(pids))]
        shs = [p.get("stakeholder", "") for p in ss["paths"]]
        f = self.refused(f"/s/{self.sid}/w3/ss/SS1", {
            "risk_origin": "RO2", "feared_events": ["FE2"], "path_id": pids, "path_label": labels,
            "path_stakeholder": shs, "path_remove": [pids[0]], "new_path_label": "",
            "new_path_stakeholder": shs[-1] or "SH1"})
        m = re.search(r'<legend>Attack paths</legend><span class="field-error" role="alert">([^<]*)</span>', f)
        self.assertEqual(m.group(1) if m else None, "the new path needs a label")
        self.assertEqual(re.findall(r'name="path_label" value="([^"]*)"', f), labels)
        self.assertIn(f'name="path_remove" value="{pids[0]}" checked', f)
        self.assertEqual(selected(f, "risk_origin"), ["RO2"])
        self.assertEqual(checked(f, "feared_events"), ["FE2"])
        self.assertEqual(selected(f, "new_path_stakeholder"), [shs[-1] or "SH1"])

    # ---------- W4 ----------

    def test_w4_operational_scenario_add_engine_refusal(self):
        f = self.refused(f"/s/{self.sid}/w4/os/add", {"target": "SS1::SS1-P3", "likelihood": "6",
                                                      "description": "Typed description\nline two"})
        self.assertEqual(msg_next_to(f, "likelihood"), "The engine refused the value: OS1: likelihood 6 out of scale 1-4")
        self.assertEqual(selected(f, "target"), ["SS1::SS1-P3"])
        self.assertEqual(selected(f, "likelihood"), ["6"])
        self.assertIn(">Typed description\nline two</textarea>", f)

    def test_w4_operational_scenario_app_refusal_on_target(self):
        f = self.refused(f"/s/{self.sid}/w4/os/add", {"target": "SS9::", "likelihood": "2", "description": "Kept"})
        self.assertEqual(msg_next_to(f, "target"), "pick a strategic scenario path from the list")
        self.assertIn('<option value="SS9::" selected>SS9:: (not in the list)</option>', f)
        self.assertEqual(selected(f, "likelihood"), ["2"])

    # ---------- W5 ----------

    def test_w5_risk_edit_engine_refusal_on_target(self):
        f = self.refused(f"/s/{self.sid}/w5/rk/R3", {"scenario": "ss::SS3", "label": "Edited risk label",
                                                     "likelihood": "3", "likelihood_target": "8",
                                                     "treatment": "transfer", "owner": "Typed owner"})
        self.assertEqual(msg_next_to(f, "likelihood_target"),
                         "The engine refused the value: R3: target likelihood 8 out of scale 1-4")
        self.assertIsNone(msg_next_to(f, "likelihood"))
        self.assertEqual(selected(f, "likelihood_target"), ["8"])
        self.assertEqual(selected(f, "likelihood"), ["3"])
        self.assertEqual(selected(f, "treatment"), ["transfer"])
        self.assertIn('<option value="ss::SS3" selected>', f)
        self.assertEqual((value_of(f, "label"), value_of(f, "owner")), ("Edited risk label", "Typed owner"))

    def test_w5_measure_add_bad_date(self):
        f = self.refused(f"/s/{self.sid}/w5/ms/add", {"label": "Typed measure", "risks": ["R1", "R2"],
                                                      "owner": "Typed owner", "due": "2027-13-45",
                                                      "status": "in progress"})
        self.assertEqual(msg_next_to(f, "due"), "due date must be a date (YYYY-MM-DD)")
        self.assertEqual(value_of(f, "due"), "2027-13-45")
        self.assertEqual(checked(f, "risks"), ["R1", "R2"])
        self.assertEqual(selected(f, "status"), ["in progress"])

    def test_refused_add_form_is_open(self):
        page = self.c.text(self.c.post(f"/s/{self.sid}/w5/ms/add", {"csrf": self.csrf, "label": "", "status": "done"}))
        sec = page.split('id="sec-ms"', 1)[1].split("</section>", 1)[0]
        self.assertIn('<details class="add" open>', sec)

    def test_xss_in_kept_input_is_escaped(self):
        payload = '"><script>alert(1)</script>'
        f = self.refused(f"/s/{self.sid}/w2/ro/RO2", self.ro2(motivation="5", origin=payload))
        self.assertNotIn("<script>alert(1)", f)
        self.assertIn("&quot;&gt;&lt;script&gt;", f)


if __name__ == "__main__":
    unittest.main()
