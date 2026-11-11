"""The app adapter around the engine maps: placement on a synthetic 4-level calibration, both orientations, and the
neutralised colour attribute. No live calls."""
import copy
import unittest
from xml.etree import ElementTree as ET

from atelier_app import engine

# An invented calibration with 4 risk levels (the published one has 3), to check the placement in a 4x4 grid.
SYNTH_LEVELS = [("Calm", "7FB77E"), ("Watch", "F2D06B"), ("Alert", "F28C38"), ("Stop", "8E1B10")]
SYNTH_CAL = {
    "id": "synthetic-4level",
    "name": "Synthetic test calibration (invented, 4 levels)",
    "source": "invented for the app tests",
    "severity": [{"n": 1, "code": "S1", "label": "Slight"}, {"n": 2, "code": "S2", "label": "Notable"},
                 {"n": 3, "code": "S3", "label": "Heavy"}, {"n": 4, "code": "S4", "label": "Extreme"}],
    "likelihood": [{"n": 1, "code": "L1", "label": "Remote"}, {"n": 2, "code": "L2", "label": "Possible"},
                   {"n": 3, "code": "L3", "label": "Likely"}, {"n": 4, "code": "L4", "label": "Expected"}],
    "levels": [{"name": n, "rank": i + 1, "colour": c, "acceptability": f"{n} (invented acceptance class)",
                "action": "invented"} for i, (n, c) in enumerate(SYNTH_LEVELS)],
    "grid_by_severity": {
        "4": ["Watch", "Alert", "Stop", "Stop"],
        "3": ["Watch", "Watch", "Alert", "Stop"],
        "2": ["Calm", "Watch", "Watch", "Alert"],
        "1": ["Calm", "Calm", "Watch", "Watch"],
    },
}


class MapsTest(unittest.TestCase):
    def test_synthetic_four_levels_and_both_orientations_place_risk_in_correct_cell(self):
        cal = copy.deepcopy(SYNTH_CAL)
        rows = [{'id': 'R-check', 'severity': 4, 'likelihood': 3, 'likelihood_target': 1}]
        ns = {'s': 'http://www.w3.org/2000/svg'}
        for orientation in ('severity-rows', 'likelihood-rows'):
            cal['map_orientation'] = orientation
            for stage, likelihood in (('now', 3), ('target', 1)):
                root = ET.fromstring(engine.risk_map(rows, cal, stage, stage))
                chip = next(x for x in root.findall('s:text', ns) if x.text == 'R-check')
                row = 4 if orientation == 'severity-rows' else likelihood
                col = likelihood if orientation == 'severity-rows' else 4
                self.assertEqual(float(chip.attrib['x']), 150 + (col - 1) * 150 + 75)
                self.assertEqual(float(chip.attrib['y']), 70 + (4 - row) * 90 + 22)
                rects = root.findall('s:rect', ns)
                self.assertEqual(len(rects), 16)
                self.assertEqual(len(set(x.attrib['fill'] for x in rects)), 4)


    def test_colour_attribute_injection_is_neutralised_without_changing_calibration(self):
        cal = copy.deepcopy(SYNTH_CAL)
        bad = 'FFFFFF" onload="alert(1)'
        cal['levels'][0]['colour'] = bad
        root = ET.fromstring(engine.risk_map([], cal, 'now', 'Synthetic'))
        svg = ET.tostring(root, encoding='unicode')
        self.assertNotIn('onload', svg)
        self.assertNotIn('alert(1)', svg)
        self.assertIn('#BBBBBB', svg)
        self.assertEqual(cal['levels'][0]['colour'], bad)


if __name__ == '__main__':
    unittest.main()
