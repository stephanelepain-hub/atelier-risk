"""Seams kept on purpose: the engine behind one adapter, storage/auth/calibrations/config one module each."""
import os
import pathlib
import re
import unittest
from unittest import mock

from app.tests import helpers
from app.tests.helpers import Client, make_app
from atelier_app import config

SRC = helpers.APP_DIR / "atelier_app"


class StructureTest(unittest.TestCase):
    def test_engine_imported_only_by_the_adapter(self):
        users = sorted(p.name for p in SRC.glob("*.py") if re.search(r"\batelier_engine\b", p.read_text()))
        self.assertEqual(users, ["engine.py"])

    def test_no_host_specific_paths_in_code(self):
        for p in list(SRC.glob("*.py")) + [helpers.APP_DIR / "serve.py"]:
            t = p.read_text()
            self.assertNotRegex(t, r"/home/|/Users/|/root/|C:\\\\", p.name)

    def test_only_storage_builds_study_paths(self):
        for p in SRC.glob("*.py"):
            if p.name != "storage.py":
                self.assertNotIn('"studies"', p.read_text(), p.name)

    def test_config_defaults_follow_environment(self):
        with mock.patch.dict(os.environ, {"ATELIER_DATA_DIR": "/srv/x", "ATELIER_PRIVATE_DIR": ""}, clear=False):
            self.assertEqual(config.default_data_dir(), pathlib.Path("/srv/x"))
            self.assertEqual(config.default_private_dir("/srv/x"), pathlib.Path("/srv/x/private"))
        env = {k: v for k, v in os.environ.items() if k not in ("ATELIER_DATA_DIR", "XDG_DATA_HOME")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(config.default_data_dir(), pathlib.Path.home() / ".local" / "share" / "atelier")
        self.assertEqual((config.DEFAULT_HOST, config.DEFAULT_PORT), ("127.0.0.1", 8770))

    def test_sessions_carry_a_user_and_studies_come_from_store_for(self):
        app, d = make_app()
        try:
            c = Client(app)
            c.login()
            s = app.auth.get(c.cookies["atelier_session"])
            self.assertEqual(s.user, config.LOCAL_USER)
            self.assertIs(app.store_for(s), app.store)
        finally:
            helpers.cleanup(d)


if __name__ == "__main__":
    unittest.main()
