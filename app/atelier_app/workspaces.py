"""Public mode: anonymous private workspaces.

A visitor gets a random id (256 bits) in a cookie. On disk only its SHA-256 names the folder
`<data>/workspaces/<sha256 hex>/`, so the folder name cannot be turned back into the cookie. Each workspace has its own
study store and a `last_seen` file whose modification time says when the visitor last came; `purge_idle` removes the
workspaces nobody visited for a while.
"""
import hashlib
import hmac
import os
import pathlib
import re
import secrets
import shutil
import threading
import time

from . import auth
from .storage import Store

COOKIE = auth.SESSION_COOKIE                  # the same cookie name as the local session; here its value is the workspace id
ID_RE = re.compile(r"[A-Za-z0-9_-]{43}")        # secrets.token_urlsafe(32): 256 bits
HASH_RE = re.compile(r"[0-9a-f]{64}")
MAX_WORKSPACES = 5000
MAX_STUDIES = 20
IDLE_DAYS = 30
JOIN_WINDOW = 10 * 60
JOIN_MAX = 10
JOIN_TRACKED = 10000                            # most client addresses remembered at once


def hash_id(wid):
    return hashlib.sha256(wid.encode("ascii")).hexdigest()


def cookie_header(wid):
    return f"{COOKIE}={wid}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={IDLE_DAYS * 86400}"


def clear_cookie_header():
    return f"{COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0"


class WorkspacesFull(Exception):
    """The server already holds its maximum number of workspaces."""


class JoinLimiter:
    """Wrong invite codes per client address: more than JOIN_MAX in JOIN_WINDOW seconds locks that address."""

    def __init__(self):
        self.failures = {}
        self.lock = threading.Lock()

    def _recent(self, client, now):
        return [t for t in self.failures.get(client, ()) if now - t < JOIN_WINDOW]

    def locked(self, client):
        now = time.time()
        with self.lock:
            recent = self._recent(client, now)
            if recent:
                self.failures[client] = recent
            else:
                self.failures.pop(client, None)
            return len(recent) >= JOIN_MAX

    def fail(self, client):
        now = time.time()
        with self.lock:
            if len(self.failures) >= JOIN_TRACKED and client not in self.failures:
                self.failures = {c: r for c in list(self.failures) if (r := self._recent(c, now))}
                while len(self.failures) >= JOIN_TRACKED:      # still full of recent failures: forget the oldest address
                    del self.failures[next(iter(self.failures))]
            self.failures.setdefault(client, [])
            self.failures[client] = self._recent(client, now) + [now]


class Workspaces:
    def __init__(self, data_dir, max_workspaces=MAX_WORKSPACES, max_studies=MAX_STUDIES):
        self.root = pathlib.Path(data_dir) / "workspaces"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.max_workspaces = max_workspaces
        self.max_studies = max_studies
        self.stores = {}
        self.lock = threading.Lock()
        self.create_lock = threading.Lock()

    # ---------- lookup ----------

    def folder(self, h):
        return self.root / h

    def hashes(self):
        return [p.name for p in self.root.iterdir() if HASH_RE.fullmatch(p.name) and p.is_dir() and not p.is_symlink()]

    def full(self):
        return len(self.hashes()) >= self.max_workspaces

    def find(self, wid):
        """The hash of a cookie value naming an existing workspace, else None."""
        if not isinstance(wid, str) or not ID_RE.fullmatch(wid):
            return None
        h = hash_id(wid)
        return h if self.folder(h).is_dir() else None

    def touch(self, h):
        try:
            os.utime(self.folder(h) / "last_seen")
        except FileNotFoundError:
            (self.folder(h) / "last_seen").touch(mode=0o600)

    def store(self, h):
        with self.lock:
            st = self.stores.get(h)
            if st is None:
                st = self.stores[h] = Store(self.folder(h), max_studies=self.max_studies, keep_trash=False)
            return st

    def session(self, wid, h):
        """A session for the cookie value `wid`. The CSRF token is derived from the cookie value, so it needs no
        server memory and survives a restart; it does not reveal the cookie value or the folder name."""
        s = auth.Session(h)
        s.sid = h
        s.public = True
        s.csrf = hmac.new(wid.encode("ascii"), b"atelier-csrf", hashlib.sha256).hexdigest()
        return s

    # ---------- create and remove ----------

    def create(self):
        """A new workspace. Returns the cookie value. Raises WorkspacesFull at the limit (checked and created under one
        lock, so joins that arrive together cannot pass it)."""
        with self.create_lock:
            if self.full():
                raise WorkspacesFull(self.max_workspaces)
            while True:
                wid = secrets.token_urlsafe(32)
                h = hash_id(wid)
                try:
                    self.folder(h).mkdir(mode=0o700)
                except FileExistsError:
                    continue
                break
        self.touch(h)
        self.store(h)
        return wid

    def remove(self, h):
        with self.lock:
            self.stores.pop(h, None)
        folder = self.folder(h)
        if HASH_RE.fullmatch(h) and folder.is_dir() and not folder.is_symlink():
            shutil.rmtree(folder, ignore_errors=True)

    def purge_idle(self, days=IDLE_DAYS):
        """Delete every workspace whose `last_seen` is older than `days`. Returns how many were deleted."""
        cutoff = time.time() - days * 86400
        n = 0
        for h in self.hashes():
            f = self.folder(h)
            try:
                seen = (f / "last_seen").stat().st_mtime
            except FileNotFoundError:
                try:
                    seen = f.stat().st_mtime
                except FileNotFoundError:
                    continue
            if seen < cutoff:
                self.remove(h)
                n += 1
        return n
