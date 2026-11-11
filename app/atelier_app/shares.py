"""Public mode: "Send my study to CPLT".

A visitor who agrees sends a copy of their study, with an email address and an optional message. The copy goes to
`<data>/shared/<UTC date>-<16 random hex>/` (outside the workspace, so Delete my data leaves it):

    study.json    the quick study, the same text as the study file download
    contact.json  email, message, lang, created (ISO UTC), study_name

Folders are 0700 and files 0600. The app sends no email and makes no outbound call: the publisher reads the folders.
`purge_shared` deletes the folders older than a year. A workspace may share 3 times per UTC day (the dates are kept
in the workspace itself, in `shares`), and the instance keeps at most 2000 shared folders.
"""
import datetime
import json
import os
import pathlib
import re
import secrets
import shutil
import threading
import time

MAX_PER_DAY = 3
MAX_SHARED = 2000
KEEP_DAYS = 365
MAX_MESSAGE = 500
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
FOLDER_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{16}")


class TooManyToday(Exception):
    """This workspace has already shared MAX_PER_DAY studies today."""


class SharedFull(Exception):
    """The instance already holds MAX_SHARED shared folders."""


def valid_email(x):
    return isinstance(x, str) and len(x) <= 254 and EMAIL_RE.fullmatch(x) is not None


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(path, 0o600)


class Shares:
    def __init__(self, data_dir, max_shared=MAX_SHARED, per_day=MAX_PER_DAY):
        self.root = pathlib.Path(data_dir) / "shared"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.max_shared = max_shared
        self.per_day = per_day
        self.lock = threading.Lock()

    def folders(self):
        return [p for p in self.root.iterdir() if p.is_dir() and not p.is_symlink()]

    def full(self):
        return len(self.folders()) >= self.max_shared

    # the dates this workspace shared on, kept inside the workspace (so a deleted workspace starts again at zero)
    @staticmethod
    def _days(ws_folder):
        try:
            d = json.loads((pathlib.Path(ws_folder) / "shares").read_text(encoding="utf-8"))
            return [x for x in d if isinstance(x, str)] if isinstance(d, list) else []
        except (OSError, ValueError):
            return []

    def create(self, ws_folder, study_bytes, email, message, lang, study_name):
        """Store one share. Raises TooManyToday or SharedFull; otherwise returns the folder name."""
        now = _utc_now()
        today = now.strftime("%Y-%m-%d")
        with self.lock:
            days = self._days(ws_folder)
            if days.count(today) >= self.per_day:
                raise TooManyToday()
            if self.full():
                raise SharedFull()
            while True:
                name = f"{today}-{secrets.token_hex(8)}"
                folder = self.root / name
                try:
                    folder.mkdir(mode=0o700)
                    break
                except FileExistsError:
                    continue
            try:
                os.chmod(folder, 0o700)
                _write(folder / "study.json", study_bytes)
                contact = {"email": email, "message": message, "lang": lang, "created": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "study_name": study_name}
                _write(folder / "contact.json", (json.dumps(contact, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
                keep = [d for d in days if d == today]          # older dates are of no use: the limit is per day
                _write_replace(pathlib.Path(ws_folder) / "shares", json.dumps(keep + [today]).encode("utf-8"))
            except Exception:
                shutil.rmtree(folder, ignore_errors=True)
                raise
            return name

    def purge(self, days=KEEP_DAYS):
        """Delete the shared folders older than `days` days: by the date in the folder name, or by the folder's own
        modification time when that is older. Returns how many were deleted."""
        cutoff_day = (_utc_now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        cutoff_ts = time.time() - days * 86400
        n = 0
        for p in self.folders():
            try:
                old = (FOLDER_RE.fullmatch(p.name) is not None and p.name[:10] < cutoff_day) or p.stat().st_mtime < cutoff_ts
            except FileNotFoundError:
                continue
            if old:
                shutil.rmtree(p, ignore_errors=True)
                n += 1
        return n


def _write_replace(path, data):
    tmp = pathlib.Path(str(path) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
