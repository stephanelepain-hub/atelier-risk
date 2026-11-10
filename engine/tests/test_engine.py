"""Engine tests. Run from the repository root:  python3 -m unittest discover -s engine/tests -t engine   (or: cd engine && python3 -m unittest)"""
import copy
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from atelier_engine import calibration, study  # noqa: E402

EXAMPLE = json.loads((ROOT / "examples" / "anssi-guide-vaccine-example.json").read_text(encoding="utf-8"))


class AnssiCalibration(unittest.TestCase):
    """The grid must reproduce the guide's own figure (EBIOS RM v1.5 p.75), cell by cell."""

    # Transcribed independently from the p.75 figure: teal = Faible, orange = Moyen, red = Eleve (legend p.74).
    FIGURE_P75 = {4: "MMEE", 3: "FMEE", 2: "FFME", 1: "FFMM"}
    NAMES = {"F": "Faible", "M": "Moyen", "E": "Eleve"}

    def setUp(self):
        self.cal = calibration.load("anssi-v1.5")

    def test_grid_16_cells(self):
        for s, row in self.FIGURE_P75.items():
            for v, code in enumerate(row, 1):
                self.assertEqual(calibration.level(self.cal, s, v), self.NAMES[code], f"G{s} V{v}")

    def test_guide_example_risks(self):
        # p.75: R1 G3V3 red, R2 G3V2 orange, R3 G3V4 red, R4 G4V2 orange, R5 G4V1 orange
        rows = {r["id"]: r["level"] for r in study.register(EXAMPLE, self.cal)}
        self.assertEqual(rows, {"R1": "Eleve", "R2": "Moyen", "R3": "Eleve", "R4": "Moyen", "R5": "Moyen"})

    def test_acceptability_classes(self):
        self.assertEqual([calibration.level_info(self.cal, n)["acceptability"] for n in ("Faible", "Moyen", "Eleve")],
                         ["Acceptable en l'etat", "Tolerable sous controle", "Inacceptable"])


class CalibrationChecks(unittest.TestCase):
    def setUp(self):
        self.cal = calibration.load("anssi-v1.5")

    def test_out_of_scale_rejected(self):
        for bad in (0, 5, "3", 2.0, True, None):
            with self.assertRaises(calibration.CalibrationError):
                calibration.level(self.cal, bad, 2)

    def test_non_monotonic_grid_rejected(self):
        bad = copy.deepcopy(self.cal)
        bad["grid_by_severity"]["3"] = ["Eleve", "Moyen", "Eleve", "Eleve"]
        with self.assertRaises(calibration.CalibrationError):
            calibration.check(bad)

    def test_unknown_level_rejected(self):
        bad = copy.deepcopy(self.cal)
        bad["grid_by_severity"]["1"][0] = "Tiny"
        with self.assertRaises(calibration.CalibrationError):
            calibration.check(bad)

    def test_unknown_calibration(self):
        with self.assertRaises(calibration.CalibrationError):
            calibration.load("does-not-exist")


class StudyChecks(unittest.TestCase):
    def setUp(self):
        self.cal = calibration.load("anssi-v1.5")

    def check(self, st):
        return study.validate(st, self.cal)

    def test_example_is_clean(self):
        self.assertEqual(self.check(EXAMPLE)["errors"], [])

    def test_dangling_reference(self):
        st = copy.deepcopy(EXAMPLE)
        st["risks"][0]["strategic_scenario"] = "SS9"
        self.assertTrue(any("unknown strategic scenario SS9" in e for e in self.check(st)["errors"]))

    def test_duplicate_id(self):
        st = copy.deepcopy(EXAMPLE)
        st["risks"][1]["id"] = "R1"
        self.assertTrue(any("duplicate id R1" in e for e in self.check(st)["errors"]))

    def test_scenario_severity_must_follow_feared_events(self):
        st = copy.deepcopy(EXAMPLE)
        st["strategic_scenarios"][1]["severity"] = 3
        self.assertTrue(any("SS2: severity 3" in e for e in self.check(st)["errors"]))

    def test_risk_severity_must_follow_scenario(self):
        st = copy.deepcopy(EXAMPLE)
        st["risks"][3]["severity"] = 3
        self.assertTrue(any("R4: severity 3 differs" in e for e in self.check(st)["errors"]))

    def test_out_of_scale_in_study(self):
        st = copy.deepcopy(EXAMPLE)
        st["risks"][0]["likelihood"] = 5
        self.assertTrue(any("R1: likelihood 5 out of scale" in e for e in self.check(st)["errors"]))

    def test_blind_spot_warning(self):
        st = copy.deepcopy(EXAMPLE)
        st["feared_events"].append({"id": "FE4", "business_value": "BV2", "label": "x", "criterion": "integrity", "severity": 4})
        self.assertTrue(any(w.startswith("FE4:") for w in self.check(st)["warnings"]))

    def test_target_without_measure_warning(self):
        st = copy.deepcopy(EXAMPLE)
        st["risks"][0]["likelihood_target"] = 1
        self.assertTrue(any(w.startswith("R1: target") for w in self.check(st)["warnings"]))


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "engine"))
        env.pop("ATELIER_PRIVATE_DIR", None)
        p = subprocess.run([sys.executable, "-m", "atelier_engine", *args], capture_output=True, text=True, env=env)
        return p.returncode, json.loads(p.stdout)

    def test_register(self):
        code, r = self.run_cli("register", str(ROOT / "examples" / "anssi-guide-vaccine-example.json"))
        self.assertEqual(code, 0)
        self.assertEqual(r["summary"]["now"], {"Eleve": 2, "Moyen": 3})

    def test_bad_input_exit_1(self):
        code, r = self.run_cli("level", "--cal", "anssi-v1.5", "--severity", "5", "--likelihood", "1")
        self.assertEqual(code, 1)
        self.assertIn("error", r)

    def test_export_xlsx(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl not installed")
        with tempfile.TemporaryDirectory() as d:
            out = str(pathlib.Path(d) / "x.xlsx")
            code, r = self.run_cli("export", str(ROOT / "examples" / "anssi-guide-vaccine-example.json"), out)
            self.assertEqual(code, 0)
            wb = openpyxl.load_workbook(out)
            self.assertEqual(wb.sheetnames[0], "Risk register")
            self.assertEqual(wb["Risk register"].max_row, 6)


if __name__ == "__main__":
    unittest.main()
