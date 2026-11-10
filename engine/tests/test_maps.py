"""Risk map tests: placement, SVG well-formed and escaped, Excel sheets, orientation, negatives."""
import copy
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from atelier_engine import calibration, maps, study  # noqa: E402

EXAMPLE = json.loads((ROOT / "examples" / "anssi-guide-vaccine-example.json").read_text(encoding="utf-8"))
NS = "{http://www.w3.org/2000/svg}"


class Maps(unittest.TestCase):
    def setUp(self):
        self.cal = calibration.load("anssi-v1.5")
        self.rows = study.register(EXAMPLE, self.cal)

    def test_placements_follow_the_guide_figure(self):
        # guide p.75: R1 G3V3, R2 G3V2, R3 G3V4, R4 G4V2, R5 G4V1
        self.assertEqual(maps.placements(self.rows), {(3, 3): ["R1"], (3, 2): ["R2"], (3, 4): ["R3"], (4, 2): ["R4"], (4, 1): ["R5"]})
        self.assertEqual(maps.placements(self.rows, "target"), {})

    def test_svg_well_formed_with_16_cells_coloured_by_the_grid(self):
        doc = ET.fromstring(maps.svg(self.rows, self.cal))
        rects = doc.findall(f"{NS}rect")
        self.assertEqual(len(rects), 16)
        colours = {r.get("fill").lstrip("#") for r in rects}
        self.assertEqual(colours, {l["colour"].upper() for l in self.cal["levels"]})
        texts = [t.text for t in doc.iter(f"{NS}text")]
        for rid in ("R1", "R2", "R3", "R4", "R5"):
            self.assertIn(rid, texts)
        # top-left cell of the guide orientation is severity 4 x likelihood 1 = Moyen
        self.assertIn("Severity 4, Likelihood 1: Moyen", rects[0].find(f"{NS}title").text)

    def test_orientation_swaps_axes(self):
        doc = ET.fromstring(maps.svg(self.rows, self.cal, orientation="likelihood-rows"))
        first = doc.findall(f"{NS}rect")[0].find(f"{NS}title").text
        self.assertIn("Likelihood 4, Severity 1: Moyen", first)  # G1 x V4 = Moyen in the guide grid
        cal = copy.deepcopy(self.cal)
        cal["map_orientation"] = "likelihood-rows"
        self.assertEqual(maps.svg(self.rows, cal), maps.svg(self.rows, self.cal, orientation="likelihood-rows"))

    def test_hostile_ids_are_escaped(self):
        rows = [{"id": '<script>alert(1)</script>&"', "severity": 2, "likelihood": 2}]
        out = maps.svg(rows, self.cal)
        self.assertNotIn("<script>", out)
        ET.fromstring(out)  # still well-formed

    def test_crowded_cell(self):
        rows = [{"id": f"R{i}", "severity": 4, "likelihood": 4} for i in range(20)]
        doc = ET.fromstring(maps.svg(rows, self.cal))
        self.assertIn("+8 more", [t.text for t in doc.iter(f"{NS}text")])

    def test_negative(self):
        with self.assertRaises(ValueError):
            maps.placements(self.rows, "later")
        with self.assertRaises(ValueError):
            maps.svg(self.rows, self.cal, orientation="diagonal")
        bad = copy.deepcopy(self.cal)
        bad["map_orientation"] = "diagonal"
        with self.assertRaises(calibration.CalibrationError):
            calibration.check(bad)


class ExcelMaps(unittest.TestCase):
    def setUp(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl not installed")
        self.cal = calibration.load("anssi-v1.5")

    def test_export_has_map_sheets_only_for_stages_present(self):
        import openpyxl
        from atelier_engine import export
        st = copy.deepcopy(EXAMPLE)
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "a.xlsx"
            export.to_xlsx(st, self.cal, p)
            wb = openpyxl.load_workbook(p)
            self.assertEqual(wb.sheetnames[:2], ["Risk register", "Map now"])
            self.assertNotIn("Map target", wb.sheetnames)
            ws = wb["Map now"]
            # severity-rows: row 4 = G4, row 5 = G3; columns B..E = V1..V4
            self.assertEqual(ws["C5"].value, "R2")
            self.assertEqual(ws["D5"].value, "R1")
            self.assertEqual(ws["E5"].value, "R3")
            self.assertEqual(ws["B4"].value, "R5")
            self.assertEqual(ws["D5"].fill.fgColor.rgb[-6:], "F07178")  # Eleve red
            st["risks"][0]["likelihood_target"] = 1
            st["measures"] = [{"id": "M1", "label": "x", "risks": ["R1"], "status": "planned", "owner": "a", "due": "b"}]
            export.to_xlsx(st, self.cal, p)
            wb = openpyxl.load_workbook(p)
            self.assertEqual(wb.sheetnames[:3], ["Risk register", "Map now", "Map target"])
            self.assertEqual(wb["Map target"]["B5"].value, "R1")

    def test_cli_map(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "m.svg"
            env = dict(os.environ, PYTHONPATH=str(ROOT / "engine"))
            env.pop("ATELIER_PRIVATE_DIR", None)
            p = subprocess.run([sys.executable, "-m", "atelier_engine", "map", str(ROOT / "examples" / "anssi-guide-vaccine-example.json"),
                                str(out)], capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["placed"], 5)
            ET.parse(out)


if __name__ == "__main__":
    unittest.main()
