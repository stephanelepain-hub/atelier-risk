#!/usr/bin/env python3
"""Run the app tests as if openpyxl were not installed: the Excel tests skip, every other test runs.

  python3 app/tests/no_openpyxl.py        (from the repository root)
"""
import pathlib
import sys
import unittest

sys.modules["openpyxl"] = None  # any `import openpyxl` now raises ImportError
REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(REPO / "app" / "tests"), top_level_dir=str(REPO))
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    print(f"ran {res.testsRun}, skipped {len(res.skipped)}, failures {len(res.failures)}, errors {len(res.errors)}")
    for t, why in res.skipped:
        print(f"skipped: {t.id()}: {why}")
    sys.exit(0 if res.wasSuccessful() else 1)
