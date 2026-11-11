"""Study files: one JSON file per study, atomic writes, a .bak of the previous version on every save.

The file holds the study exactly in the engine's `atelier-study` format, so the engine CLI can read it as is.
Study ids are generated here (s-YYYYMMDD-xxxxxxxx); any other id is refused before a path is built.
"""
import datetime
import json
import os
import pathlib
import re
import secrets
import shutil
import tempfile
import threading

ID_RE = re.compile(r"s-[0-9]{8}-[0-9a-f]{8}")


class NotFound(Exception):
    pass


def _fsync_dir(d):
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path, data):
    """Write bytes to path through a temp file in the same directory and an atomic rename."""
    path = pathlib.Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    _fsync_dir(path.parent)


class Store:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.dir = self.root / "studies"
        self.trash = self.dir / "trash"
        for d in (self.root, self.dir, self.trash):
            d.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(d, 0o700)
        self.lock = threading.Lock()

    def new_id(self):
        while True:
            sid = f"s-{datetime.date.today():%Y%m%d}-{secrets.token_hex(4)}"
            if not self._path(sid).exists():
                return sid

    def _path(self, sid):
        if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
            raise NotFound(sid)
        p = self.dir / f"{sid}.json"
        if p.parent != self.dir:  # cannot happen with ID_RE, kept as a second guard
            raise NotFound(sid)
        return p

    def exists(self, sid):
        try:
            return self._path(sid).is_file()
        except NotFound:
            return False

    def load(self, sid):
        p = self._path(sid)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise NotFound(sid)

    def mtime(self, sid):
        return self._path(sid).stat().st_mtime

    def list(self):
        out = []
        for p in sorted(self.dir.glob("s-*.json")):
            sid = p.stem
            if not ID_RE.fullmatch(sid):
                continue
            try:
                st = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                st = None
            out.append((sid, st, p.stat().st_mtime))
        out.sort(key=lambda x: -x[2])
        return out

    def save(self, sid, study):
        p = self._path(sid)
        data = (json.dumps(study, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        with self.lock:
            if p.exists():
                atomic_write(p.with_name(p.name + ".bak"), p.read_bytes())
            atomic_write(p, data)

    def create(self, study):
        sid = self.new_id()
        self.save(sid, study)
        return sid

    def delete(self, sid):
        """Move the study (and its .bak) to studies/trash/; nothing is unlinked."""
        p = self._path(sid)
        with self.lock:
            if not p.exists():
                raise NotFound(sid)
            stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            shutil.move(str(p), str(self.trash / f"{sid}.{stamp}.json"))
            bak = p.with_name(p.name + ".bak")
            if bak.exists():
                shutil.move(str(bak), str(self.trash / f"{sid}.{stamp}.json.bak"))
