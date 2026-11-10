"""A private calibration in the UI, with an invented 4-level calibration in a temp ATELIER_PRIVATE_DIR."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from app.tests import helpers
from app.tests.helpers import SID_RE, SYNTH_CAL, SYNTH_ID, Client, make_app, make_private_dir, small_study
from atelier_app import calibrations, engine, views


class PrivateCalibrationTest(unittest.TestCase):
    def setUp(self):
        self.priv = make_private_dir()
        self.app, self.d = make_app(private_dir=self.priv)
        self.c = Client(self.app)
        self.c.login()

    def tearDown(self):
        helpers.cleanup(self.d)
        shutil.rmtree(self.priv, ignore_errors=True)
        os.environ.pop("ATELIER_PRIVATE_DIR", None)

    def page(self, path):
        r = self.c.get(path)
        self.assertEqual(r.status, 200, path)
        return self.c.text(r)

    def new_study(self, cal_id, name="Synthetic private study"):
        r = self.c.post_csrf("/new", {"name": name, "calibration": cal_id})
        self.assertEqual(r.status, 303)
        return SID_RE.search(r.get("Location")).group(1)

    def import_study(self, st):
        r = self.c.import_bytes(json.dumps(st).encode())
        self.assertEqual(r.status, 303, self.c.text(r)[:500])
        return SID_RE.search(r.get("Location")).group(1)

    def stored(self, sid):
        return self.app.store.load(sid)

    # --- picker and badges ---

    def test_engine_lists_the_synthetic_calibration_as_private(self):
        self.assertEqual(calibrations.available(), {"anssi-v1.5": "public", SYNTH_ID: "private"})

    def test_picker_shows_public_and_private_with_badges_and_level_counts(self):
        t = self.page("/")
        pick = t.split('<fieldset class="cal-pick">', 1)[1].split("</fieldset>", 1)[0]
        opts = re.findall(r'<label class="cal-opt">(.*?)</label>', pick, re.S)
        self.assertEqual(len(opts), 2)
        pub = next(o for o in opts if 'value="anssi-v1.5"' in o)
        prv = next(o for o in opts if f'value="{SYNTH_ID}"' in o)
        self.assertIn('<span class="badge public">public</span>', pub)
        self.assertIn('<span class="badge private"', prv)
        self.assertIn("4 risk levels", prv)
        self.assertIn("3 risk levels", pub)
        self.assertIn(" checked", pub)  # the public calibration stays the default
        self.assertNotIn(" checked", prv)

    def test_new_study_on_the_private_calibration(self):
        sid = self.new_study(SYNTH_ID)
        self.assertEqual(self.stored(sid)["study"]["calibration"], SYNTH_ID)
        t = self.page(f"/s/{sid}")
        self.assertIn(f'calibration {SYNTH_ID} <span class="badge private"', t)  # study head
        row = re.search(r"<tr><th>Calibration</th><td>(.*?)</td></tr>", t).group(1)
        self.assertIn('<span class="badge private"', row)
        self.assertIn("4 risk levels", row)
        priv = re.search(r'<td id="privacy">(.*?)</td>', t, re.S).group(1)
        self.assertIn("it uses a private calibration", priv)
        lst = self.page("/")
        rowl = re.search(rf'<a href="/s/{sid}">.*?</tr>', lst, re.S).group(0)
        self.assertIn('<span class="badge private"', rowl)

    def test_public_study_overview_says_not_private(self):
        sid = self.new_study("anssi-v1.5", "Public one")
        priv = re.search(r'<td id="privacy">(.*?)</td>', self.page(f"/s/{sid}"), re.S).group(1)
        self.assertIn("not private", priv)
        self.assertIn("Mark this study confidential", priv)

    # --- grid, legend, counts, colours for 4 levels ---

    def test_four_level_grid_legend_counts_and_colours(self):
        sid = self.import_study(small_study(SYNTH_ID))
        chk = engine.check(self.stored(sid))
        self.assertEqual((chk["errors"], chk["warnings"]), ([], []))
        t = self.page(f"/s/{sid}/register")
        grids = re.findall(r'<table class="grid">(.*?)</table>', t, re.S)
        self.assertEqual(len(grids), 2)  # now and at target
        cls = views.level_classes(SYNTH_CAL)
        self.assertEqual(sorted(cls.values()), ["lvl-i0", "lvl-i1", "lvl-i2", "lvl-i3"])
        for g in grids:
            cells = re.findall(r'<td class="([^"]*)"><span class="lvl-name">([^<]+)</span>', g)
            self.assertEqual(len(cells), 16)
            # every cell carries the class of the level the engine gives it
            expect = [(cls[engine.level(SYNTH_CAL, s, v)], engine.level(SYNTH_CAL, s, v)) for s in (4, 3, 2, 1)
                      for v in (1, 2, 3, 4)]
            self.assertEqual(cells, expect)
            self.assertEqual({n for _, n in cells}, {"Calm", "Watch", "Alert", "Stop"})
        legend = re.search(r'<ul class="legend">(.*?)</ul>', t, re.S).group(1)
        self.assertEqual(re.findall(r'<span class="lvl ([^"]+)">([^<]+)</span>', legend),
                         [("lvl-i3", "Stop"), ("lvl-i2", "Alert"), ("lvl-i1", "Watch"), ("lvl-i0", "Calm")])
        # register and counts are the engine's: R1 at S4/L3 is Stop now, S4/L1 is Watch at target
        rows, summary = engine.register(self.stored(sid), SYNTH_CAL)
        self.assertEqual((rows[0]["level"], rows[0]["level_target"]), ("Stop", "Watch"))
        self.assertIn(f'<span class="lvl lvl-i3">Stop</span> 1', t)
        self.assertIn(f'<span class="lvl lvl-i1">Watch</span> 1', t)
        self.assertEqual(summary["now"], {"Stop": 1})
        css = self.c.text(self.c.get(f"/cal/{SYNTH_ID}.css"))
        for i, (_, colour) in enumerate(helpers.SYNTH_LEVELS):
            self.assertIn(f".lvl-i{i}{{background:#{colour};", css)
        self.assertEqual(css.count("background:"), 4)

    def test_register_equals_the_engine_cli_with_the_private_dir(self):
        sid = self.import_study(small_study(SYNTH_ID))
        path = self.app.store.dir / f"{sid}.json"
        env = dict(os.environ, ATELIER_PRIVATE_DIR=str(self.priv))
        cli = subprocess.run([sys.executable, "-m", "atelier_engine", "register", str(path)], cwd=helpers.ENGINE,
                             capture_output=True, text=True, env=env)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        cli_levels = {r["id"]: (r["level"], r.get("level_target")) for r in json.loads(cli.stdout)["risks"]}
        t = self.page(f"/s/{sid}/register")
        app_levels = dict(re.findall(r'<tr id="el-(R\d)">.*?<span class="lvl [^"]*">([^<]+)</span>', t, re.S))
        self.assertEqual(app_levels, {k: v[0] for k, v in cli_levels.items()})
        self.assertEqual(cli_levels, {"R1": ("Stop", "Watch")})

    def test_w5_grids_and_xlsx_with_four_levels(self):
        sid = self.import_study(small_study(SYNTH_ID))
        t = self.page(f"/s/{sid}/w5")
        self.assertEqual(t.count('<span class="lvl-name">'), 32)
        if not helpers.HAVE_OPENPYXL:
            self.skipTest("openpyxl not installed")
        import io
        import openpyxl
        r = self.c.get(f"/s/{sid}/export.xlsx")
        self.assertEqual(r.status, 200)
        wb = openpyxl.load_workbook(io.BytesIO(r.body))
        ws = wb["Risk register"]
        head = [c.value for c in ws[1]]
        row = dict(zip(head, [c.value for c in ws[2]]))
        self.assertEqual((row["level"], row["level_target"]), ("Stop", "Watch"))

    # --- duplicate with another calibration, never switch in place ---

    def test_overview_offers_duplicate_with_each_other_calibration(self):
        sid = self.new_study("anssi-v1.5", "Public one")
        t = self.page(f"/s/{sid}")
        self.assertIn(f"Duplicate with calibration {SYNTH_ID}", t)
        self.assertNotIn("Duplicate with calibration anssi-v1.5", t)

    def test_rename_cannot_switch_the_calibration_in_place(self):
        sid = self.new_study("anssi-v1.5", "Public one")
        r = self.c.post_csrf(f"/s/{sid}/rename", {"name": "Renamed", "scope": "", "calibration": SYNTH_ID})
        self.assertEqual(r.status, 303)
        self.assertEqual(self.stored(sid)["study"]["calibration"], "anssi-v1.5")

    def test_duplicate_public_to_private_calibration(self):
        sid = self.import_study(small_study("anssi-v1.5", "Pub"))
        r = self.c.post_csrf(f"/s/{sid}/duplicate", {"calibration": SYNTH_ID})
        self.assertEqual(r.status, 303)
        nsid = SID_RE.search(r.get("Location")).group(1)
        self.assertNotEqual(nsid, sid)
        old, new = self.stored(sid), self.stored(nsid)
        self.assertEqual(old["study"]["calibration"], "anssi-v1.5")  # the original is untouched
        self.assertEqual(new["study"]["calibration"], SYNTH_ID)
        self.assertEqual(new["study"]["name"], f"Pub (copy, calibration {SYNTH_ID})")
        self.assertNotIn("confidential", new["study"])  # private through its calibration already
        self.assertEqual(calibrations.study_privacy(new), (True, "it uses a private calibration"))
        self.assertEqual({k: v for k, v in new.items() if k != "study"}, {k: v for k, v in old.items() if k != "study"})
        rows, _ = engine.register(new, engine.load_cal(SYNTH_ID))
        self.assertEqual(rows[0]["level"], "Stop")
        rows, _ = engine.register(old, engine.load_cal("anssi-v1.5"))
        self.assertEqual(rows[0]["level"], "Élevé")

    def test_duplicate_of_a_private_study_on_a_public_calibration_stays_private(self):
        sid = self.import_study(small_study(SYNTH_ID, "Priv"))
        r = self.c.post_csrf(f"/s/{sid}/duplicate", {"calibration": "anssi-v1.5"})
        nsid = SID_RE.search(r.get("Location")).group(1)
        new = self.stored(nsid)
        self.assertEqual(new["study"]["calibration"], "anssi-v1.5")
        self.assertIs(new["study"]["confidential"], True)
        self.assertEqual(calibrations.study_privacy(new), (True, "it is marked confidential"))
        t = self.page(f"/s/{nsid}")
        self.assertIn("it is marked confidential", t)
        self.assertIn("Remove the confidential mark", t)

    def test_duplicate_with_unknown_or_broken_calibration_refused(self):
        sid = self.new_study("anssi-v1.5", "Public one")
        n = len(self.app.store.list())
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/duplicate", {"calibration": "../x"}).status, 400)
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/duplicate", {"calibration": "nope"}).status, 400)
        self.assertEqual(len(self.app.store.list()), n)

    def test_plain_duplicate_still_works(self):
        sid = self.new_study("anssi-v1.5", "Public one")
        r = self.c.post_csrf(f"/s/{sid}/duplicate")
        self.assertEqual((r.status, r.get("Location")), (303, "/?f=duplicated"))
        names = sorted(st["study"]["name"] for _, st, _ in self.app.store.list())
        self.assertEqual(names, ["Public one", "Public one (copy)"])

    # --- confidential flag ---

    def test_confidential_flag_set_and_removed(self):
        sid = self.new_study("anssi-v1.5", "Public one")
        r = self.c.post_csrf(f"/s/{sid}/confidential", {"confidential": "yes"}, page=f"/s/{sid}")
        self.assertEqual(r.status, 303)
        self.assertIs(self.stored(sid)["study"]["confidential"], True)
        self.assertEqual(engine.check(self.stored(sid))["errors"], [])  # the engine ignores the flag
        self.c.post_csrf(f"/s/{sid}/confidential", {"confidential": "no"}, page=f"/s/{sid}")
        self.assertNotIn("confidential", self.stored(sid)["study"])
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/confidential", {"confidential": "maybe"}).status, 400)

    def test_unknown_calibration_counts_as_private(self):
        st = small_study("not-installed")
        self.assertEqual(calibrations.study_privacy(st)[0], True)


class BrokenPrivateCalibrationTest(unittest.TestCase):
    def test_broken_private_file_is_listed_disabled_and_refused(self):
        priv = make_private_dir({"broken-cal.json": "{not json", "bad-scale.json": json.dumps(
            dict(SYNTH_CAL, id="bad-scale", severity=SYNTH_CAL["severity"][:3]))})
        app, d = make_app(private_dir=priv)
        try:
            c = Client(app)
            c.login()
            t = c.text(c.get("/"))
            for cid in ("broken-cal", "bad-scale"):
                opt = re.search(rf'<label class="cal-opt"><input type="radio" name="calibration" value="{cid}"[^>]*>', t)
                self.assertIsNotNone(opt, cid)
                self.assertIn(" disabled", opt.group(0))
                r = c.post_csrf("/new", {"name": "x", "calibration": cid})
                self.assertEqual(r.status, 400, cid)
            self.assertIn("cannot be loaded", t)
            self.assertEqual(app.store.list(), [])
        finally:
            helpers.cleanup(d)
            shutil.rmtree(priv, ignore_errors=True)
            os.environ.pop("ATELIER_PRIVATE_DIR", None)


if __name__ == "__main__":
    unittest.main()
