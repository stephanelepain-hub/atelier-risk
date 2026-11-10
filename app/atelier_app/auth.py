"""Login token, one-time login links, in-memory sessions and CSRF tokens."""
import hmac
import os
import pathlib
import secrets
import stat
import threading
import time

SESSION_COOKIE = "atelier_session"
PRE_COOKIE = "atelier_pre"
SESSION_IDLE = 12 * 3600
ONCE_TTL = 10 * 60
FAIL_WINDOW = 60
FAIL_MAX = 10


def load_or_create_token(path):
    """Read the login token, creating it (0600, parent dir 0700) on first start. Returns (token, created)."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32) + "\n")
        created = True
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        os.chmod(path, 0o600)
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 20:
        raise RuntimeError(f"login token in {path} is too short; delete the file to generate a new one")
    return token, created


class Session:
    __slots__ = ("sid", "csrf", "seen")

    def __init__(self):
        self.sid = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.seen = time.time()


class Auth:
    def __init__(self, token):
        self.token = token
        self.sessions = {}
        self.once = {}
        self.failures = []
        self.lock = threading.Lock()

    def check_token(self, candidate):
        now = time.time()
        with self.lock:
            self.failures = [t for t in self.failures if now - t < FAIL_WINDOW]
            if len(self.failures) >= FAIL_MAX:
                return "locked"
            ok = hmac.compare_digest(candidate.encode("utf-8"), self.token.encode("utf-8"))
            if not ok:
                self.failures.append(now)
            return "ok" if ok else "bad"

    def new_session(self):
        s = Session()
        with self.lock:
            self.sessions[s.sid] = s
        return s

    def get(self, sid):
        if not sid:
            return None
        now = time.time()
        with self.lock:
            s = self.sessions.get(sid)
            if s and now - s.seen > SESSION_IDLE:
                del self.sessions[sid]
                return None
            if s:
                s.seen = now
            return s

    def drop(self, sid):
        with self.lock:
            self.sessions.pop(sid, None)

    def mint_once(self, next_path="/"):
        n = secrets.token_urlsafe(32)
        with self.lock:
            now = time.time()
            self.once = {k: v for k, v in self.once.items() if v[0] > now}
            self.once[n] = (now + ONCE_TTL, next_path)
        return n

    def use_once(self, nonce):
        """Consume a one-time link. Returns its next path, or None if unknown, used or expired."""
        with self.lock:
            v = self.once.pop(nonce, None)
        if not v or v[0] < time.time():
            return None
        return v[1]

    @staticmethod
    def csrf_ok(session, candidate):
        return bool(session and candidate) and hmac.compare_digest(candidate.encode("utf-8"), session.csrf.encode("utf-8"))


def session_cookie(sid, max_age=None):
    c = f"{SESSION_COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/"
    if max_age is not None:
        c += f"; Max-Age={max_age}"
    return c
