"""Private per-review directories. Upload bytes and one atomic state snapshot per review."""
import datetime
import json
import os
import pathlib
import re
import secrets
import shutil

from .storage import NotFound, atomic_write

ID_PATTERN = r"r-[0-9]{8}-[0-9a-f]{16}"
ID_RE = re.compile(ID_PATTERN)


class ReviewStore:
    def __init__(self, root):
        self.root = pathlib.Path(root) / "reviews"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def directory(self, rid):
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
            raise NotFound(rid)
        p = self.root / rid
        if p.is_symlink():
            raise NotFound(rid)
        return p

    def load(self, rid):
        try:
            return json.loads((self.directory(rid) / "state.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise NotFound(rid)

    def save(self, rid, state):
        p = self.directory(rid)
        if not p.is_dir():
            raise NotFound(rid)
        atomic_write(p / "state.json", (json.dumps(state, ensure_ascii=False, indent=1) + "\n").encode())

    def create(self, upload, state):
        while True:
            rid = f"r-{datetime.date.today():%Y%m%d}-{secrets.token_hex(8)}"
            p = self.directory(rid)
            try:
                p.mkdir(mode=0o700)
                break
            except FileExistsError:
                continue
        try:
            atomic_write(p / "upload.xlsx", upload)
            self.save(rid, state)
        except BaseException:
            shutil.rmtree(p)
            raise
        return rid

    def list(self):
        rows = []
        for p in self.root.iterdir():
            if not ID_RE.fullmatch(p.name) or not p.is_dir() or p.is_symlink():
                continue
            # Do not silently hide unreadable reviews.
            rows.append((p.name, self.load(p.name), (p / "state.json").stat().st_mtime))
        return sorted(rows, key=lambda row: -row[2])

    def delete(self, rid):
        p = self.directory(rid)
        if not p.is_dir():
            raise NotFound(rid)
        shutil.rmtree(p)
