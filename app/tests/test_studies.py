import io
import json
import re
import subprocess
import sys
import unittest

from app.tests import helpers
from app.tests.helpers import Client, make_app
from atelier_app import engine, views

XSS = '"><script>alert(1)</script><img src=x onerror=alert(2)>'


def rows_level(html_text):
    """id -> first level span (level now) of each row of the register table."""
    out = {}
    for m in re.finditer(r'<tr id="el-([^"]+)">(.*?)</tr>', html_text, re.S):
        lv = re.search(r'<span class="lvl [^"]*">([^<]+)</span>', m.group(2))
        if lv:
            out[m.group(1)] = lv.group(1)
    return out


class StudyFlowTest(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)
        self.c.login()

    def tearDown(self):
        helpers.cleanup(self.dir)

    def page(self, path):
        r = self.c.get(path)
        self.assertEqual(r.status, 200, path)
        return self.c.text(r)

    # --- list, create, rename, duplicate, delete ---

    def test_create_rename_duplicate_delete(self):
        r = self.c.post_csrf("/new", {"name": "Pilot", "scope": "One site", "calibration": "anssi-v1.5"})
        self.assertEqual(r.status, 303)
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        st = self.app.store.load(sid)
        self.assertEqual(st["format"], "atelier-study")
        self.assertEqual(st["study"], {"name": "Pilot", "scope": "One site", "calibration": "anssi-v1.5"})
        t = self.page("/")
        self.assertIn("Pilot", t)
        self.assertIn("anssi-v1.5", t)
        self.assertIn('badge ok">valid', t)
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/rename", {"name": "Pilot 2", "scope": "Two sites"}).status, 303)
        self.assertEqual(self.app.store.load(sid)["study"]["name"], "Pilot 2")
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/duplicate").status, 303)
        names = sorted(s["study"]["name"] for _, s, _ in self.app.store.list())
        self.assertEqual(names, ["Pilot 2", "Pilot 2 (copy)"])
        self.assertIn("Delete this study?", self.page(f"/s/{sid}/delete"))
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/delete").status, 303)
        self.assertEqual(len(self.app.store.list()), 1)

    def test_unknown_calibration_refused(self):
        r = self.c.post_csrf("/new", {"name": "x", "calibration": "../../etc/passwd"})
        self.assertEqual(r.status, 400)

    def test_calibration_picker_lists_engine_calibrations(self):
        t = self.page("/")
        for cal in engine.calibrations():
            self.assertIn(f'<option value="{cal}"', t)

    # --- import ---

    def test_import_guide_example_validates(self):
        r = self.c.import_bytes(helpers.EXAMPLE.read_bytes(), "anssi-guide-vaccine-example.json")
        self.assertEqual(r.status, 303)
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        st = self.app.store.load(sid)
        self.assertEqual(st, helpers.example_json())
        chk = engine.check(st)
        self.assertEqual(chk["errors"], [])
        self.assertEqual(chk["warnings"], [])
        t = self.page(f"/s/{sid}")
        self.assertIn("No error, no warning.", t)
        out = subprocess.run([sys.executable, "-m", "atelier_engine", "validate", str(self.app.store.dir / f"{sid}.json")],
                             cwd=helpers.ENGINE, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json.loads(out.stdout)["errors"], [])

    def test_import_refusals(self):
        cases = [(b"not json", "s.json", "not valid JSON"), (b"[1,2]", "s.json", "not a JSON object"),
                 (b'{"format": "other"}', "s.json", "format must be"),
                 (b'{"format": "atelier-study", "study": {"calibration": "nope"}}', "s.json", "unknown calibration"),
                 (b'{"format": "atelier-study", "risks": "x"}', "s.json", "must be a list"),
                 (b'{"format": "atelier-study", "x": NaN}', "s.json", "not valid JSON"),
                 (b"{}", "s.xlsx", "only .json")]
        for data, fn, msg in cases:
            r = self.c.import_bytes(data, fn)
            self.assertEqual(r.status, 400, data)
            self.assertIn(msg, self.c.text(r), data)
        self.assertEqual(self.app.store.list(), [])

    def test_import_with_errors_kept_and_errors_linked(self):
        st = helpers.example_json()
        st["feared_events"][0]["business_value"] = "BV9"
        r = self.c.import_bytes(json.dumps(st).encode())
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        t = self.page(f"/s/{sid}/w1")
        self.assertIn("FE1: unknown business value BV9", t)
        self.assertIn(f'href="/s/{sid}/el/FE1"', t)
        loc = self.c.get(f"/s/{sid}/el/FE1")
        self.assertEqual(loc.status, 303)
        self.assertEqual(loc.get("Location"), f"/s/{sid}/w1#el-FE1")
        self.assertIn('id="el-FE1"', t)
        self.assertIn("badge bad", self.page("/"))
        self.assertIn("only for a study without errors", self.page(f"/s/{sid}/register"))
        self.assertEqual(self.c.get(f"/s/{sid}/export.xlsx").status, 409)

    def test_workshops_2_to_5_show_every_element(self):
        sid = self.c.load_example()
        st = self.app.store.load(sid)
        for n, (_, keys) in views.WORKSHOPS.items():
            t = self.page(f"/s/{sid}/w{n}")
            for k in keys:
                for x in st.get(k) or []:
                    self.assertIn(f'id="el-{x["id"]}"', t, (n, x["id"]))
                    if k == "strategic_scenarios":
                        for p in x.get("paths") or []:
                            self.assertIn(f'id="el-{p["id"]}"', t)

    # --- W1 editor and live checks ---

    def test_w1_add_feared_event_updates_checks(self):
        sid = self.c.load_example()
        t = self.page(f"/s/{sid}/w1")
        self.assertIn("No error, no warning.", t)
        cal = engine.load_cal("anssi-v1.5")
        picker = re.search(r'<select name="severity" required>(.*?)</select>', t, re.S).group(1)
        self.assertEqual(re.findall(r'<option value="(\d)">([^<]+)</option>', picker),
                         [(str(x["n"]), f'{x["code"]} {x["label"]}') for x in cal["severity"]])
        r = self.c.post_csrf(f"/s/{sid}/w1/fe/add", {"business_value": "BV2", "label": "Batch records altered",
                                                     "criterion": "integrity", "severity": "3"}, page=f"/s/{sid}/w1")
        self.assertEqual(r.status, 303)
        st = self.app.store.load(sid)
        fe = st["feared_events"][-1]
        self.assertEqual(fe, {"id": "FE4", "business_value": "BV2", "label": "Batch records altered",
                              "criterion": "integrity", "severity": 3})
        t = self.page(r.get("Location").split("#")[0])
        self.assertIn("FE4: severity 3 but no scenario targets it (blind spot, guide p.73)", t)
        self.assertIn("1 warning", t)
        self.assertTrue((self.app.store.dir / f"{sid}.json.bak").exists())

    def test_w1_links_only_to_existing_ids(self):
        sid = self.c.load_example()
        before = self.app.store.load(sid)
        bad = [("fe", {"business_value": "BV999", "label": "x", "severity": "2"}),
               ("fe", {"business_value": "BV1", "label": "x", "severity": "7"}),
               ("fe", {"business_value": "BV1", "label": "", "severity": "2"}),
               ("sa", {"label": "Server", "business_values": ["BV1", "FE1"]}),
               ("bv", {"label": "x", "nature": "other"}),
               ("bl", {"reference": "x", "status": "maybe"})]
        for slug, form in bad:
            r = self.c.post_csrf(f"/s/{sid}/w1/{slug}/add", form, page=f"/s/{sid}/w1")
            self.assertEqual(r.status, 400, form)
        self.assertEqual(self.app.store.load(sid), before)

    def test_w1_full_cycle(self):
        r = self.c.post_csrf("/new", {"name": "W1"})
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        p = f"/s/{sid}/w1"
        self.assertEqual(self.c.post_csrf(f"{p}/bv/add", {"label": "Payroll", "nature": "process", "owner": "HR"}, page=p).status, 303)
        self.assertEqual(self.c.post_csrf(f"{p}/sa/add", {"label": "Payroll server", "business_values": ["BV1"]}, page=p).status, 303)
        self.assertEqual(self.c.post_csrf(f"{p}/fe/add", {"business_value": "BV1", "label": "Pay late", "severity": "2"}, page=p).status, 303)
        self.assertEqual(self.c.post_csrf(f"{p}/bl/add", {"reference": "Password policy", "status": "partial", "gap": "no MFA"}, page=p).status, 303)
        st = self.app.store.load(sid)
        self.assertEqual([x["id"] for x in st["business_values"]], ["BV1"])
        self.assertEqual(st["supporting_assets"], [{"id": "SA1", "label": "Payroll server", "business_values": ["BV1"]}])
        self.assertEqual(st["baseline"], [{"id": "BL1", "reference": "Password policy", "status": "partial", "gap": "no MFA"}])
        self.assertIn("Edit feared event FE1", self.page(f"{p}/fe/FE1"))
        r = self.c.post_csrf(f"{p}/fe/FE1", {"business_value": "BV1", "label": "Pay late", "severity": "4"}, page=f"{p}/fe/FE1")
        self.assertEqual(r.status, 303)
        self.assertEqual(self.app.store.load(sid)["feared_events"][0]["severity"], 4)
        self.assertEqual(engine.check(self.app.store.load(sid))["errors"], [])
        # deleting the business value leaves dangling links, which the engine reports
        self.assertEqual(self.c.post_csrf(f"{p}/bv/BV1/delete", page=p).status, 303)
        chk = engine.check(self.app.store.load(sid))
        self.assertIn("SA1: unknown business value BV1", chk["errors"])
        self.assertIn("FE1: unknown business value BV1", chk["errors"])
        self.assertIn("SA1: unknown business value BV1", self.page(p))
        self.assertEqual(self.c.get(f"{p}/fe/NOPE").status, 404)

    # --- escaping ---

    def test_xss_payload_is_escaped(self):
        r = self.c.post_csrf("/new", {"name": XSS, "scope": XSS})
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        p = f"/s/{sid}/w1"
        self.c.post_csrf(f"{p}/bv/add", {"label": XSS, "owner": XSS}, page=p)
        self.c.post_csrf(f"{p}/fe/add", {"business_value": "BV1", "label": XSS, "criterion": XSS, "severity": "1"}, page=p)
        st = self.app.store.load(sid)
        self.assertEqual(st["business_values"][0]["label"], XSS)
        escaped = "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x onerror=alert(2)&gt;"
        for path in ("/", f"/s/{sid}", p, f"{p}/fe/FE1", f"{p}/bv/BV1", f"/s/{sid}/register", f"/s/{sid}/delete"):
            t = self.page(path)
            self.assertNotIn("<script>alert", t, path)
            self.assertNotIn("<img src=x", t, path)
            self.assertIn(escaped, t, path)

    def test_xss_in_imported_ids_and_risks(self):
        st = helpers.example_json()
        st["risks"][0]["label"] = XSS
        st["business_values"][0]["owner"] = XSS
        r = self.c.import_bytes(json.dumps(st).encode())
        sid = helpers.SID_RE.search(r.get("Location")).group(1)
        for path in (f"/s/{sid}/register", f"/s/{sid}/w1", f"/s/{sid}/w5"):
            t = self.page(path)
            self.assertNotIn("<script>alert", t, path)
            self.assertNotIn("<img src=x", t, path)

    # --- register and grid ---

    def test_register_levels_equal_engine_cli(self):
        sid = self.c.load_example()
        st = self.app.store.load(sid)
        st["risks"][0]["likelihood_target"] = 1
        st["measures"] = [{"id": "M1", "label": "Egress filtering", "risks": ["R1"], "owner": "IT", "due": "2027-01",
                           "status": "planned"}]
        self.app.store.save(sid, st)
        out = subprocess.run([sys.executable, "-m", "atelier_engine", "register", str(self.app.store.dir / f"{sid}.json")],
                             cwd=helpers.ENGINE, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        cli = json.loads(out.stdout)
        t = self.page(f"/s/{sid}/register")
        shown = rows_level(t)
        expected = {r["id"]: r["level"] for r in cli["risks"]}
        self.assertEqual(len(expected), 5)
        self.assertEqual(shown, expected)
        r1 = next(r for r in cli["risks"] if r["id"] == "R1")
        self.assertEqual(r1["level_target"], "Faible")
        self.assertIn("At target", t)
        # the per-level counts shown are the engine summary
        for name, n in cli["summary"]["now"].items():
            self.assertRegex(t, rf'<span class="lvl [^"]*">{name}</span> {n}')
        # grid: every cell coloured by the calibration's level, each risk in its (severity, likelihood) cell
        cal = engine.load_cal("anssi-v1.5")
        cls = views.level_classes(cal)
        now_grid = t.split("<figcaption>Now</figcaption>")[1].split("</figure>")[0]
        cells = re.findall(r"<tr><th scope=\"row\">(G\d).*?</th>(.*?)</tr>", now_grid, re.S)
        self.assertEqual([c[0] for c in cells], ["G4", "G3", "G2", "G1"])
        for code, tds in cells:
            s = int(code[1])
            tdl = re.findall(r'<td class="([^"]+)">(.*?)</td>', tds, re.S)
            self.assertEqual(len(tdl), 4, code)
            for v, td in enumerate(tdl, start=1):
                self.assertEqual(td[0], cls[cal["grid_by_severity"][str(s)][v - 1]], (s, v))
                placed = set(re.findall(r'class="chip"[^>]*>([^<]+)</a>', td[1]))
                want = {r["id"] for r in cli["risks"] if r["severity"] == s and r["likelihood"] == v}
                self.assertEqual(placed, want, (s, v))

    def test_calibration_css_uses_level_colours(self):
        css = self.c.text(self.c.get("/cal/anssi-v1.5.css"))
        cal = engine.load_cal("anssi-v1.5")
        for l in cal["levels"]:
            self.assertIn(f"background:#{l['colour']}", css)
        self.assertEqual(self.c.get("/cal/nope.css").status, 404)

    # --- exports ---

    def test_export_json_and_xlsx(self):
        sid = self.c.load_example()
        r = self.c.get(f"/s/{sid}/export.json")
        self.assertEqual(r.status, 200)
        self.assertIn("attachment", r.get("Content-Disposition"))
        self.assertEqual(json.loads(r.body), helpers.example_json())
        r = self.c.get(f"/s/{sid}/export.xlsx")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.body.startswith(b"PK"))
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(r.body))
        self.assertIn("Risk register", wb.sheetnames)
        self.assertIn("Feared events", wb.sheetnames)
        self.assertIn("About", wb.sheetnames)
        ws = wb["Risk register"]
        self.assertEqual(ws.max_row, 6)
        self.assertEqual(list(self.app.tmp_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
