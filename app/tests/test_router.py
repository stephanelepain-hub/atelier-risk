import unittest

from app.tests import helpers  # noqa: F401  (sets sys.path)
from atelier_app.web import HTTPError, Request, Router


class RouterTest(unittest.TestCase):
    def setUp(self):
        self.r = Router()
        self.r.add("GET", r"/", lambda req: "index")
        self.r.add("GET", r"/s/([a-z0-9-]+)", lambda req, sid: sid)
        self.r.add("POST", r"/s/([a-z0-9-]+)", lambda req, sid: "post " + sid)
        self.r.add("GET", r"/el/([^/]+)", lambda req, eid: eid, public=True)

    def test_match_and_groups(self):
        fn, args, public = self.r.match("GET", "/s/abc-1")
        self.assertEqual(fn(None, *args), "abc-1")
        self.assertFalse(public)
        fn, args, _ = self.r.match("POST", "/s/abc-1")
        self.assertEqual(fn(None, *args), "post abc-1")

    def test_groups_are_percent_decoded(self):
        fn, args, public = self.r.match("GET", "/el/SS1%2FP1")
        self.assertEqual(args, ["SS1/P1"])
        self.assertTrue(public)

    def test_full_match_only(self):
        for p in ("/s/abc/extra", "/s/", "/s/ABC", "/s/..%2f..", "//", "/s/abc%2f..", "/x"):
            with self.assertRaises(HTTPError) as c:
                self.r.match("GET", p)
            self.assertEqual(c.exception.status, 404, p)

    def test_method_not_allowed(self):
        with self.assertRaises(HTTPError) as c:
            self.r.match("POST", "/")
        self.assertEqual(c.exception.status, 405)

    def test_head_uses_get(self):
        fn, args, _ = self.r.match("HEAD", "/")
        self.assertEqual(fn(None), "index")

    def test_request_parsing(self):
        req = Request("get", "/s/x?f=saved&n=1", {"Cookie": "a=1; b=2", "Host": "h"})
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.path, "/s/x")
        self.assertEqual(req.arg("f"), "saved")
        self.assertEqual(req.cookies, {"a": "1", "b": "2"})
        self.assertEqual(req.headers["host"], "h")

    def test_unsupported_body_type(self):
        req = Request("POST", "/", {"Content-Type": "application/json"}, b"{}")
        with self.assertRaises(HTTPError) as c:
            req.parse_body()
        self.assertEqual(c.exception.status, 415)


if __name__ == "__main__":
    unittest.main()
