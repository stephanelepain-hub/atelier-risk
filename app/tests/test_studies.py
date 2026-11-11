"""The saved-studies list (reopen, delete) and the downloads of a study (study file, Excel)."""
import io
import json
import sys
import unittest
from unittest import mock

from app.tests import helpers
from app.tests.helpers import Client, make_app
from atelier_app import engine

XSS = '"><script>alert(1)</script><img src=x onerror=alert(2)>'
ESCAPED = "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x onerror=alert(2)&gt;"


class StudyListTest(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)
        self.c.login()

    def tearDown(self):
        helpers.cleanup(self.dir)

    def page(self, path, status=200):
        r = self.c.get(path)
        self.assertEqual(r.status, status, path)
        return self.c.text(r)

    def sid(self, name="Pilot"):
        return helpers.quick_study(self.c, name)

    def test_empty_list_points_to_the_quick_path(self):
        t = self.page("/studies")
        self.assertIn("No study yet", t)
        self.assertIn('href="/quick/new"', t)

    def test_list_reopen_and_delete(self):
        sid = self.sid("Pilot")
        t = self.page("/studies")
        self.assertIn("Pilot", t)
        self.assertIn(f'href="/quick/{sid}/risks"', t)
        self.assertIn("Delete this study?", self.page(f"/s/{sid}/delete"))
        self.assertEqual(self.c.post_csrf(f"/s/{sid}/delete").status, 303)
        self.assertEqual(self.app.store.list(), [])
        self.assertTrue(any(p.name.startswith(sid) for p in self.app.store.trash.iterdir()))   # moved, not erased
        self.assertIn("Study moved to the trash folder.", self.page("/studies?f=removed"))
        self.assertEqual(self.c.get(f"/quick/{sid}/about").status, 404)

    def test_delete_needs_a_login_and_the_csrf_token(self):
        sid = self.sid()
        anon = Client(self.app)
        self.assertEqual(anon.get(f"/s/{sid}/delete").status, 303)
        self.assertEqual(anon.post(f"/s/{sid}/delete", {"csrf": "x"}).status, 403)
        self.assertEqual(self.c.post(f"/s/{sid}/delete", {"csrf": "wrong"}).status, 403)
        self.assertEqual(len(self.app.store.list()), 1)

    def test_delete_of_an_unknown_study_is_404(self):
        self.assertEqual(self.c.get("/s/s-20261110-0123abcd/delete").status, 404)
        self.assertEqual(self.c.post_csrf("/s/s-20261110-0123abcd/delete").status, 404)

    def test_xss_in_a_study_name_is_escaped(self):
        sid = self.sid(XSS)
        for path in ("/", "/studies", f"/s/{sid}/delete"):
            t = self.page(path)
            self.assertNotIn("<script>alert", t, path)
            self.assertNotIn("<img src=x", t, path)
            self.assertIn(ESCAPED, t, path)

    def test_a_damaged_file_is_listed_and_can_be_deleted(self):
        sid = self.app.store.create({"format": "atelier-study"})
        (self.app.store.dir / f"{sid}.json").write_text("{not json", encoding="utf-8")
        t = self.page("/studies")
        self.assertIn(f'href="/s/{sid}/delete"', t)

    def test_calibration_css_uses_level_colours(self):
        css = self.c.text(self.c.get("/cal/anssi-v1.5.css"))
        cal = engine.load_cal("anssi-v1.5")
        for l in cal["levels"]:
            self.assertIn(f"background:#{l['colour']}", css)
        self.assertEqual(self.c.get("/cal/nope.css").status, 404)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.app, self.dir = make_app()
        self.c = Client(self.app)
        self.c.login()
        self.sid = helpers.store_example(self.c)

    def tearDown(self):
        helpers.cleanup(self.dir)

    def test_export_json(self):
        r = self.c.get(f"/s/{self.sid}/export.json")
        self.assertEqual(r.status, 200)
        self.assertIn("attachment", r.get("Content-Disposition"))
        self.assertEqual(json.loads(r.body), helpers.example_json())

    @unittest.skipUnless(helpers.HAVE_OPENPYXL, "openpyxl not installed: the Excel export is not tested")
    def test_export_xlsx(self):
        r = self.c.get(f"/s/{self.sid}/export.xlsx")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.body.startswith(b"PK"))
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(r.body))
        self.assertIn("Risk register", wb.sheetnames)
        self.assertIn("Feared events", wb.sheetnames)
        self.assertIn("About", wb.sheetnames)
        self.assertEqual(wb["Risk register"].max_row, 6)
        self.assertEqual(list(self.app.tmp_dir.iterdir()), [])

    def test_export_xlsx_without_openpyxl_says_so(self):
        with mock.patch.dict(sys.modules, {"openpyxl": None}):
            r = self.c.get(f"/s/{self.sid}/export.xlsx")
        self.assertEqual(r.status, 501)
        self.assertIn("needs openpyxl", self.c.text(r))
        self.assertEqual(list(self.app.tmp_dir.iterdir()), [])

    def test_downloads_need_a_login(self):
        anon = Client(self.app)
        for ext in ("json", "xlsx"):
            self.assertEqual(anon.get(f"/s/{self.sid}/export.{ext}").status, 303)


if __name__ == "__main__":
    unittest.main()
