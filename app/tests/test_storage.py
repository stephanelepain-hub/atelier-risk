import json
import os
import stat
import tempfile
import shutil
import unittest
from unittest import mock

from app.tests import helpers  # noqa: F401
from atelier_app import storage
from atelier_app.storage import NotFound, Store


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="atelier-store-")
        self.store = Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def files(self):
        return sorted(os.listdir(self.store.dir))

    def test_save_keeps_bak_of_previous_version(self):
        sid = self.store.create({"format": "atelier-study", "v": 1})
        p = self.store.dir / f"{sid}.json"
        self.assertFalse((self.store.dir / f"{sid}.json.bak").exists())
        self.store.save(sid, {"format": "atelier-study", "v": 2})
        self.assertEqual(json.loads(p.read_text())["v"], 2)
        self.assertEqual(json.loads((self.store.dir / f"{sid}.json.bak").read_text())["v"], 1)
        self.store.save(sid, {"format": "atelier-study", "v": 3})
        self.assertEqual(json.loads((self.store.dir / f"{sid}.json.bak").read_text())["v"], 2)
        self.assertEqual(self.files(), sorted([f"{sid}.json", f"{sid}.json.bak", "trash"]))
        for f in (p, self.store.dir / f"{sid}.json.bak"):
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.store.dir.stat().st_mode), 0o700)

    def test_failed_write_leaves_previous_file_intact(self):
        sid = self.store.create({"format": "atelier-study", "v": 1})
        p = self.store.dir / f"{sid}.json"
        before = p.read_bytes()
        real_replace = os.replace

        def boom(src, dst):
            if str(dst) == str(p):
                raise OSError("disk full (simulated)")
            return real_replace(src, dst)
        with mock.patch.object(storage.os, "replace", side_effect=boom):
            with self.assertRaises(OSError):
                self.store.save(sid, {"format": "atelier-study", "v": 2})
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual([f for f in self.files() if f.startswith(".tmp-")], [])

    def test_unserialisable_study_does_not_touch_file(self):
        sid = self.store.create({"format": "atelier-study", "v": 1})
        before = (self.store.dir / f"{sid}.json").read_bytes()
        with self.assertRaises(TypeError):
            self.store.save(sid, {"bad": object()})
        self.assertEqual((self.store.dir / f"{sid}.json").read_bytes(), before)

    def test_ids_are_generated_slugs(self):
        sid = self.store.new_id()
        self.assertRegex(sid, r"^s-[0-9]{8}-[0-9a-f]{8}$")
        with self.assertRaises(NotFound):
            self.store.save("../escape", {})
        self.assertFalse(os.path.exists(os.path.join(self.dir, "escape.json")))

    def test_list_and_delete_to_trash(self):
        a = self.store.create({"format": "atelier-study", "study": {"name": "A"}})
        b = self.store.create({"format": "atelier-study", "study": {"name": "B"}})
        self.store.save(a, {"format": "atelier-study", "study": {"name": "A2"}})
        self.assertEqual({x[0] for x in self.store.list()}, {a, b})
        self.store.delete(a)
        self.assertEqual([x[0] for x in self.store.list()], [b])
        trashed = os.listdir(self.store.trash)
        self.assertEqual(len(trashed), 2)
        self.assertTrue(any(t.endswith(".json.bak") for t in trashed))
        with self.assertRaises(NotFound):
            self.store.load(a)


if __name__ == "__main__":
    unittest.main()
