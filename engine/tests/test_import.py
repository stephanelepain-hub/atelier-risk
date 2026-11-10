"""Spreadsheet import tests. Workbooks are built here with openpyxl (invented data), so no file is shipped."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from atelier_engine import calibration, importer, study  # noqa: E402

try:
    import openpyxl
    from openpyxl.styles import PatternFill
except ImportError:  # the import feature needs openpyxl; without it these tests skip
    openpyxl = None

RED, ORANGE, TEAL = "F07178", "FFC57A", "4FC3B5"  # anssi-v1.5 colours: Eleve, Moyen, Faible


def fill(cell, rgb):
    cell.fill = PatternFill("solid", fgColor="FF" + rgb)


def plain_register(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Risk register"
    ws.append(["Note: invented example"])
    ws.append(["Risk ID", "Description", "Severity", "Likelihood", "Target likelihood", "Risk level", "Measures"])
    ws.append(["R1", "Supplier compromise", "Grave", "V3", "Peu vraisemblable", "Élevé", "M1, M2"])
    ws.append(["R2", "Data theft", 4, 2, None, "Moyen", "M2"])
    ws.append(["R3", "Defacement", "G2", "Quasi certain", 3, "Faible", None])  # level shown wrong: grid says Eleve
    m = wb.create_sheet("Measures")
    m.append(["Measure ID", "Measure", "Status", "Owner", "Due"])
    m.append(["M1", "Supplier security clauses (1)", "Done", "Purchasing", "2026-12-01"])
    m.append(["M2", "Supplier security clause", "Not started", None, None])   # same as M1, other status
    m.append(["M3", "Unused measure", "Waiting for budget", "IT", "2027-01-01"])  # no risk, free-text status
    wb.save(path)


def mapped_register(path):
    """Levels only as colours, a risk spread over merged rows, and three risk maps with merged cells."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Risks"
    ws.append(["Risk ID", "Criterion", "Description", "Initial risk", "Mitigation ID", "Current risk", "Targeted risk"])
    ws.append(["R1", "C", "Theft through a partner", None, "M1", None, None])
    ws.append([None, None, None, None, "M2", None, None])
    ws.merge_cells("A2:A3"); ws.merge_cells("D2:D3"); ws.merge_cells("F2:F3"); ws.merge_cells("G2:G3")
    fill(ws["D2"], RED); fill(ws["F2"], RED); fill(ws["G2"], ORANGE)
    ws.append(["R2", "I", "Tampering", None, "M3", None, None])
    fill(ws["D4"], ORANGE); fill(ws["F4"], ORANGE); fill(ws["G4"], RED)  # target colour wrong: grid says Faible
    ws.append(["R3", "A", "Outage", None, "M9", None, None])  # M9 not on the measures sheet; R3 off the target map
    fill(ws["D5"], ORANGE); fill(ws["F5"], ORANGE)
    m = wb.create_sheet("Mitigations")
    m.append([])
    m.append(["Mitigation ID", "Description", "Status"])
    m.append(["M1", "MFA for partners", "OK"])
    m.append(["M2", "Partner audit", "In progress"])
    m.append(["M3", "Signed releases", "Not started"])
    p = wb.create_sheet("Risk maps")
    sev = ["Mineure", "Significative", "Grave", "Critique"]
    lik = ["Quasi certain", "Très vraisemblable", "Vraisemblable", "Peu vraisemblable"]
    places = {"initial": {("R1", 3, 4), ("R2", 2, 3), ("R3", 2, 4)},
              "now": {("R1", 3, 3), ("R2", 2, 3), ("R3", 2, 4)},
              "target": {("R1", 3, 2), ("R2", 2, 1)}}
    for k, (stage, title) in enumerate((("initial", "INITIAL RISK MAP"), ("now", "CURRENT RISK MAP 2026"), ("target", "TARGET RISK MAP"))):
        c0 = 1 + k * 7  # label column; grid columns c0+1 .. c0+4 (each grid cell 2 rows high)
        p.cell(1, c0 + 1, title)
        p.merge_cells(start_row=1, start_column=c0 + 1, end_row=1, end_column=c0 + 4)
        p.cell(2, c0 + 1, "Gravité")
        for i, s in enumerate(sev):
            p.cell(3, c0 + 1 + i, s)
        for j, v in enumerate(lik):
            r = 4 + 2 * j
            p.cell(r, c0, v)
            p.merge_cells(start_row=r, start_column=c0, end_row=r + 1, end_column=c0)
            for i in range(4):
                p.merge_cells(start_row=r, start_column=c0 + 1 + i, end_row=r + 1, end_column=c0 + 1 + i)
                ids = sorted(x[0] for x in places[stage] if x[1] == i + 1 and x[2] == 4 - j)
                if ids:
                    p.cell(r, c0 + 1 + i, ",\n".join(ids))
    wb.save(path)


@unittest.skipIf(openpyxl is None, "openpyxl not installed")
class Import(unittest.TestCase):
    def setUp(self):
        self.cal = calibration.load("anssi-v1.5")
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_register(self):
        f = self.dir / "plain.xlsx"
        plain_register(f)
        res = importer.read_xlsx(f, self.cal, "risk-register")
        rep, st = res["report"], res["study"]
        self.assertEqual(rep["errors"], [])
        got = {r["id"]: (r["severity"], r["likelihood"], r.get("likelihood_target")) for r in st["risks"]}
        self.assertEqual(got, {"R1": (3, 3, 1), "R2": (4, 2, None), "R3": (2, 4, 3)})
        self.assertIn("R3: now level shown as Faible (text), the grid gives Élevé", rep["findings"])
        self.assertTrue(any(x.startswith("M1 and M2 have the same description with different status") for x in rep["findings"]))
        self.assertIn("M3 is linked to no risk", rep["findings"])
        self.assertIn("M3: status 'Waiting for budget' kept as text, counted as planned", rep["notes"])
        ms = {m["id"]: (m["status"], m["risks"]) for m in st["measures"]}
        self.assertEqual(ms["M1"], ("done", ["R1"]))
        self.assertEqual(ms["M2"], ("planned", ["R1", "R2"]))
        self.assertEqual(study.validate(st, self.cal)["errors"], [])

    def test_maps_and_colours(self):
        f = self.dir / "maps.xlsx"
        mapped_register(f)
        res = importer.read_xlsx(f, self.cal, "register-with-maps")
        rep, st = res["report"], res["study"]
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["read"]["stages"], ["initial", "now", "target"])
        got = {r["id"]: (r["severity"], r.get("likelihood_initial"), r["likelihood"], r.get("likelihood_target")) for r in st["risks"]}
        self.assertEqual(got, {"R1": (3, 4, 3, 2), "R2": (2, 3, 3, 1), "R3": (2, 4, 4, None)})
        self.assertEqual({r["id"]: r.get("criterion") for r in st["risks"]},
                         {"R1": "confidentiality", "R2": "integrity", "R3": "availability"})
        self.assertIn("R2: target level shown as Élevé (colour), the grid gives Faible", rep["findings"])
        self.assertIn("R3 is missing from the target risk map", rep["findings"])
        self.assertIn("M9 is linked from R3 but not described on the measures sheet", rep["findings"])
        self.assertTrue(any("colour only" in n for n in rep["notes"]))
        self.assertEqual({m["id"]: m["risks"] for m in st["measures"]}["M2"], ["R1"])
        rows = study.register(st, self.cal)
        self.assertEqual(study.summary(rows, self.cal), {"now": {"Élevé": 2, "Moyen": 1}, "target": {"Moyen": 1, "Faible": 1}})
        # R3 is G2 x V4: the guide's grid gives Élevé; the sheet coloured it orange (Moyen)
        self.assertIn("R3: now level shown as Moyen (colour), the grid gives Élevé", rep["findings"])

    def test_autodetect_prefers_the_layout_that_reads(self):
        f = self.dir / "maps.xlsx"
        mapped_register(f)
        self.assertEqual(importer.read_xlsx(f, self.cal)["report"]["layout"], "register-with-maps")
        g = self.dir / "plain.xlsx"
        plain_register(g)
        self.assertEqual(importer.read_xlsx(g, self.cal)["report"]["layout"], "risk-register")

    def test_negative(self):
        bad = self.dir / "not.xlsx"
        bad.write_bytes(b"this is not a zip")
        with self.assertRaises(importer.SpreadsheetError):
            importer.read_xlsx(bad, self.cal, "risk-register")
        with self.assertRaises(importer.SpreadsheetError):
            importer.load_layout("nope")
        wb = openpyxl.Workbook()
        wb.active.title = "Other"
        wb.active.append(["nothing", "here"])
        empty = self.dir / "empty.xlsx"
        wb.save(empty)
        with self.assertRaises(importer.SpreadsheetError):
            importer.read_xlsx(empty, self.cal)
        # a value off the scale is an error, not a guess
        f = self.dir / "plain.xlsx"
        plain_register(f)
        wb = openpyxl.load_workbook(f)
        wb["Risk register"]["C3"] = "Catastrophic"
        wb.save(f)
        rep = importer.read_xlsx(f, self.cal, "risk-register")["report"]
        self.assertTrue(any("severity 'Catastrophic' is not on the calibration's scale" in e for e in rep["errors"]))

    def test_cli(self):
        f = self.dir / "maps.xlsx"
        mapped_register(f)
        out = self.dir / "study.json"
        env = dict(os.environ, PYTHONPATH=str(ROOT / "engine"))
        env.pop("ATELIER_PRIVATE_DIR", None)
        p = subprocess.run([sys.executable, "-m", "atelier_engine", "import", str(f), "--cal", "anssi-v1.5", "--out", str(out)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        r = json.loads(p.stdout)
        self.assertEqual(r["summary"]["now"], {"Élevé": 2, "Moyen": 1})
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["format"], "atelier-study")
        p = subprocess.run([sys.executable, "-m", "atelier_engine", "layouts"], capture_output=True, text=True, env=env)
        self.assertEqual(json.loads(p.stdout), {"register-with-maps": "public", "risk-register": "public"})


if __name__ == "__main__":
    unittest.main()
