"""The application: routes, authentication and CSRF gates, security headers, study handlers."""
import copy
import json
import os
import pathlib
import re
import sys
import threading
import traceback
import urllib.parse

import datetime

from . import (REPO_DIR, STATIC_DIR, auth, calibrations, config, documents, drafting, drafts, editors, engine, views,
               views_draft, views_ws)
from .storage import NotFound, Store
from .web import HTTPError, Request, Response, Router, redirect

MAX_UPLOAD = config.MAX_UPLOAD
EXAMPLE = REPO_DIR / "examples" / "anssi-guide-vaccine-example.json"
SID = r"(s-[0-9]{8}-[0-9a-f]{8})"
DOCS_RE = re.compile(r"/s/s-[0-9]{8}-[0-9a-f]{8}/docs")
W1SLUG = r"(bv|sa|fe|bl)"
STATIC = {"app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
       "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
SECURITY_HEADERS = [
    ("Content-Security-Policy", CSP),
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cache-Control", "no-store"),
]
NEXT_RE = re.compile(r"/[A-Za-z0-9/_.\-]*")


FormError = editors.FormError  # carries the form field it is about
W1_TEXT = {"business_values": ["label", "nature", "owner"], "supporting_assets": ["label"],
           "feared_events": ["business_value", "label", "criterion", "severity"],
           "baseline": ["reference", "status", "gap"]}


def allowed_hosts_for(port, extra=()):
    return {f"127.0.0.1:{port}", f"localhost:{port}"} | {h.lower() for h in extra}


class EngineRefused(Exception):
    """The engine refused a value of a W2-W5 form: (message above the form, {field: message})."""

    def __init__(self, message, errs):
        super().__init__(message)
        self.message, self.errs = message, errs


def _no_constants(x):
    raise ValueError(f"{x} is not valid JSON")


class App:
    def __init__(self, data_dir, private_dir=None, port=config.DEFAULT_PORT, extra_hosts=(), max_upload=MAX_UPLOAD,
                 drafting_settings=None):
        self.data_dir = pathlib.Path(data_dir)
        self.store = Store(self.data_dir)
        self.private_dir = pathlib.Path(private_dir) if private_dir else config.default_private_dir(self.data_dir)
        self.private_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.private_dir, 0o700)
        calibrations.use_private_dir(self.private_dir)
        self.tmp_dir = self.data_dir / "tmp"
        self.tmp_dir.mkdir(exist_ok=True, mode=0o700)
        os.chmod(self.tmp_dir, 0o700)
        self.token_path = self.data_dir / "token"
        token, self.token_created = auth.load_or_create_token(self.token_path)
        self.auth = auth.Auth(token)
        self.max_upload = max_upload
        self.extra_hosts = tuple(extra_hosts)
        self.set_port(port)
        self.edit_lock = threading.Lock()
        self.docs = documents.DocStore(self.data_dir)
        self.draft_log = self.data_dir / "drafting-log.jsonl"
        self.limiter = drafting.RateLimiter()
        self.load_drafter(drafting_settings)
        self.router = self._routes()

    def load_drafter(self, settings=None):
        """(Re)build the drafting adapter from the given settings, or from the settings file."""
        raw = settings if settings is not None else config.drafting_settings(self.data_dir)
        self.drafter = drafting.Drafter(raw, log_path=self.draft_log, limiter=self.limiter)

    def body_limit(self, path):
        """Request body cap: 20 MB (plus the multipart envelope) for a document upload, else max_upload."""
        if DOCS_RE.fullmatch(path or ""):
            return max(self.max_upload, config.MAX_DOCUMENT_BODY)
        return self.max_upload

    def store_for(self, session):
        """The study store of a session's user. A local install has one user and one store."""
        return self.store

    def set_port(self, port):
        self.port = port
        self.allowed_hosts = allowed_hosts_for(port, self.extra_hosts)

    # ---------- plumbing ----------

    def _routes(self):
        r = Router()
        r.add("GET", r"/login", self.login_form, public=True)
        r.add("POST", r"/login", self.login, public=True)
        r.add("GET", r"/login/once", self.login_once, public=True)
        r.add("GET", r"/static/([a-z]+\.(?:css|js))", self.static, public=True)
        r.add("POST", r"/logout", self.logout)
        r.add("POST", r"/login/link", self.login_link)
        r.add("GET", r"/", self.index)
        r.add("GET", r"/settings", self.settings_form)
        r.add("POST", r"/settings", self.settings_save)
        r.add("POST", r"/new", self.new_study)
        r.add("POST", r"/import", self.import_study)
        r.add("POST", r"/example", self.load_example)
        r.add("GET", r"/cal/([A-Za-z0-9._%-]+)\.css", self.cal_css)
        r.add("GET", rf"/s/{SID}", self.overview)
        r.add("POST", rf"/s/{SID}/rename", self.rename)
        r.add("POST", rf"/s/{SID}/duplicate", self.duplicate)
        r.add("POST", rf"/s/{SID}/confidential", self.set_confidential)
        r.add("GET", rf"/s/{SID}/delete", self.delete_confirm)
        r.add("POST", rf"/s/{SID}/delete", self.delete)
        r.add("GET", rf"/s/{SID}/w1", self.w1)
        r.add("GET", rf"/s/{SID}/w([2-5])", self.workshop)
        r.add("POST", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/add", self.ws_add)
        r.add("GET", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/([^/]+)", self.ws_edit_form)
        r.add("POST", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/([^/]+)/delete", self.ws_delete)
        r.add("POST", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/([^/]+)", self.ws_save)
        r.add("POST", rf"/s/{SID}/severities", self.take_severities)
        r.add("GET", rf"/s/{SID}/el/([^/]+)", self.locate)
        r.add("GET", rf"/s/{SID}/register", self.register)
        r.add("GET", rf"/s/{SID}/export\.json", self.export_json)
        r.add("GET", rf"/s/{SID}/export\.xlsx", self.export_xlsx)
        r.add("GET", rf"/s/{SID}/docs", self.documents)
        r.add("POST", rf"/s/{SID}/docs", self.document_upload)
        r.add("POST", rf"/s/{SID}/docs/(d[0-9a-f]{{12}})/delete", self.document_delete)
        r.add("POST", rf"/s/{SID}/draft", self.draft)
        r.add("POST", rf"/s/{SID}/draft/clear", self.draft_clear)
        r.add("POST", rf"/s/{SID}/draft/accept-all", self.draft_accept_all)
        r.add("POST", rf"/s/{SID}/draft/(D[0-9]{{1,6}})/accept", self.draft_accept)
        r.add("POST", rf"/s/{SID}/draft/(D[0-9]{{1,6}})/reject", self.draft_reject)
        r.add("POST", rf"/s/{SID}/w1/{W1SLUG}/add", self.w1_add)
        r.add("GET", rf"/s/{SID}/w1/{W1SLUG}/([^/]+)", self.w1_edit_form)
        r.add("POST", rf"/s/{SID}/w1/{W1SLUG}/([^/]+)/delete", self.w1_delete)
        r.add("POST", rf"/s/{SID}/w1/{W1SLUG}/([^/]+)", self.w1_save)
        return r

    def handle(self, req: Request) -> Response:
        try:
            host = req.headers.get("host", "").lower()
            if host not in self.allowed_hosts:
                raise HTTPError(421, "this server only answers to its own loopback address")
            limit = self.body_limit(req.path)
            if len(req.body) > limit:
                raise HTTPError(413, f"request body over {limit // (1024 * 1024)} MB")
            fn, args, public = self.router.match(req.method, req.path)
            req.session = self.auth.get(req.cookies.get(auth.SESSION_COOKIE))
            if not public and not req.session:
                if req.method in ("GET", "HEAD"):
                    return self.secure(redirect("/login"))
                raise HTTPError(403, "not logged in")
            if req.method == "POST":
                req.parse_body()
                if not public and not auth.Auth.csrf_ok(req.session, req.field("csrf")):
                    raise HTTPError(403, "CSRF token missing or wrong; reload the page and try again")
            resp = fn(req, *args)
        except HTTPError as e:
            resp = Response(views.error_page(e.status, e.message, req.session), e.status)
        except NotFound:
            resp = Response(views.error_page(404, "not found", req.session), 404)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            resp = Response(views.error_page(500, "internal error (details in the server log)", req.session), 500)
        return self.secure(resp)

    def too_large(self, path=""):
        limit = self.body_limit(path)
        return self.secure(Response(views.error_page(413, f"request body over {limit // (1024 * 1024)} MB"), 413))

    @staticmethod
    def secure(resp):
        for k, v in SECURITY_HEADERS:
            if resp.get(k) is None:
                resp.header(k, v)
        return resp

    def _load(self, req, sid):
        st = self.store_for(req.session).load(sid)
        if not isinstance(st, dict):
            raise HTTPError(500, "the study file is not a JSON object")
        return st

    # ---------- auth ----------

    def login_form(self, req, message="", status=200):
        pre = auth.secrets.token_urlsafe(24)
        resp = Response(views.login_page(pre, message), status)
        resp.header("Set-Cookie", f"{auth.PRE_COOKIE}={pre}; HttpOnly; SameSite=Strict; Path=/login")
        return resp

    def login(self, req):
        pre_c, pre_f = req.cookies.get(auth.PRE_COOKIE, ""), req.field("pre")
        if not pre_c or not pre_f or not auth.hmac.compare_digest(pre_c, pre_f):
            return self.login_form(req, "The login form expired. Paste the token again.", 403)
        res = self.auth.check_token(req.field("token").strip())
        if res == "locked":
            return self.login_form(req, "Too many wrong tokens. Wait a minute.", 429)
        if res != "ok":
            return self.login_form(req, "Wrong token.", 403)
        return self._start_session("/")

    def _start_session(self, next_path):
        s = self.auth.new_session(config.LOCAL_USER)
        resp = redirect(next_path)
        resp.header("Set-Cookie", auth.session_cookie(s.sid))
        resp.header("Set-Cookie", f"{auth.PRE_COOKIE}=; HttpOnly; SameSite=Strict; Path=/login; Max-Age=0")
        return resp

    def login_once(self, req):
        nxt = self.auth.use_once(req.arg("n"))
        if nxt is None:
            return self.login_form(req, "That login link was already used or has expired.", 403)
        return self._start_session(nxt)

    def logout(self, req):
        self.auth.drop(req.session.sid)
        resp = redirect("/login")
        resp.header("Set-Cookie", auth.session_cookie("", max_age=0))
        return resp

    def login_link(self, req):
        nxt = req.field("next", "/") or "/"
        if not NEXT_RE.fullmatch(nxt) or nxt.startswith("//"):
            raise HTTPError(400, "next must be a local path")
        n = self.auth.mint_once(nxt)
        url = f"http://{req.headers['host']}/login/once?n={n}"
        return Response(views.link_page(url, req.session))

    # ---------- static ----------

    def static(self, req, name):
        if name not in STATIC:
            raise HTTPError(404, "not found")
        return Response((STATIC_DIR / name).read_bytes(), 200, STATIC[name])

    def cal_css(self, req, cal_id):
        if cal_id not in calibrations.available():
            raise HTTPError(404, "unknown calibration")
        try:
            cal = calibrations.load(cal_id)
        except (calibrations.CalibrationError, ValueError, OSError) as e:
            raise HTTPError(404, str(e))
        return Response(views.cal_css(cal), 200, "text/css; charset=utf-8")

    # ---------- study list ----------

    def index(self, req):
        rows = []
        for sid, st, mtime in self.store_for(req.session).list():
            chk = engine.check(st) if st is not None else {"errors": ["file unreadable"], "warnings": [],
                                                            "calibration": "?", "cal": None}
            rows.append((sid, st, mtime, chk))
        return Response(views.study_list(rows, calibrations.catalogue(), req.session, req.arg("f")))

    def new_study(self, req):
        name = req.field("name").strip()
        if not name or len(name) > 200:
            raise HTTPError(400, "a name of 1 to 200 characters is required")
        cal = req.field("calibration") or calibrations.DEFAULT
        if cal not in calibrations.available():
            raise HTTPError(400, "unknown calibration")
        try:
            calibrations.load(cal)
        except (calibrations.CalibrationError, ValueError, OSError) as e:
            raise HTTPError(400, f"the engine refuses that calibration: {e}")
        st = {"format": "atelier-study", "version": "0.1",
              "study": {"name": name, "scope": req.field("scope").strip()[:4000], "calibration": cal}}
        for k in engine.COLLECTIONS:
            st[k] = []
        sid = self.store_for(req.session).create(st)
        return redirect(f"/s/{sid}/w1?f=created")

    def _accept_study(self, raw, filename):
        """Parse and screen an uploaded study. Returns (study, None) or (None, [reasons])."""
        try:
            st = json.loads(raw.decode("utf-8-sig"), parse_constant=_no_constants)
        except UnicodeDecodeError:
            return None, ["the file is not UTF-8 text"]
        except ValueError as e:
            return None, [f"not valid JSON: {e}"]
        errs = engine.structure_errors(st)
        if errs:
            return None, errs
        cal = calibrations.of_study(st)
        if cal not in calibrations.available():
            return None, [f"unknown calibration '{cal}' (available: {', '.join(sorted(calibrations.available()))})"]
        return st, None

    def import_study(self, req):
        f = req.files.get("file")
        if not f or not f[1]:
            raise HTTPError(400, "choose a study JSON file")
        filename, raw = f
        if not filename.lower().endswith(".json"):
            return Response(views.import_errors(filename, ["only .json study files are accepted"], req.session), 400)
        st, errs = self._accept_study(raw, filename)
        if errs:
            return Response(views.import_errors(filename, errs, req.session), 400)
        sid = self.store_for(req.session).create(st)
        return redirect(f"/s/{sid}?f=imported")

    def load_example(self, req):
        st, errs = self._accept_study(EXAMPLE.read_bytes(), EXAMPLE.name)
        if errs:
            raise HTTPError(500, "; ".join(errs))
        sid = self.store_for(req.session).create(st)
        return redirect(f"/s/{sid}?f=example")

    # ---------- one study ----------

    def overview(self, req, sid):
        st = self._load(req, sid)
        return Response(views.overview(sid, st, engine.check(st), self.store_for(req.session).mtime(sid), req.session,
                                       req.arg("f"), calibrations.catalogue()))

    def rename(self, req, sid):
        name = req.field("name").strip()
        if not name or len(name) > 200:
            raise HTTPError(400, "a name of 1 to 200 characters is required")
        with self.edit_lock:
            st = self._load(req, sid)
            meta = st.get("study") if isinstance(st.get("study"), dict) else {}
            meta["name"] = name
            meta["scope"] = req.field("scope").strip()[:4000]
            st["study"] = meta
            self.store_for(req.session).save(sid, st)
        return redirect(f"/s/{sid}?f=renamed")

    def duplicate(self, req, sid):
        """Copy a study, optionally with another calibration (the only way to change a study's calibration).

        The copy of a private study stays private: it is marked confidential, so a copy on a public calibration
        cannot be sent to a remote drafting endpoint.
        """
        st = self._load(req, sid)
        meta = st.get("study") if isinstance(st.get("study"), dict) else {}
        was_private, _ = calibrations.study_privacy(st)
        new_cal = req.field("calibration")
        if new_cal:
            if not calibrations.exists(new_cal):
                raise HTTPError(400, "unknown calibration")
            try:
                calibrations.load(new_cal)
            except (calibrations.CalibrationError, ValueError, OSError) as e:
                raise HTTPError(400, f"the engine refuses that calibration: {e}")
        old_cal = calibrations.of_study(st)
        if new_cal and new_cal != old_cal:
            meta["calibration"] = new_cal
            meta["name"] = (meta.get("name") or "study") + f" (copy, calibration {new_cal})"
        else:
            meta["name"] = (meta.get("name") or "study") + " (copy)"
        if was_private:
            meta["confidential"] = True
        st["study"] = meta
        new_sid = self.store_for(req.session).create(st)
        if new_cal and new_cal != old_cal:
            return redirect(f"/s/{new_sid}?f=duplicated-cal")
        return redirect("/?f=duplicated")

    def set_confidential(self, req, sid):
        v = req.field("confidential")
        if v not in ("yes", "no"):
            raise HTTPError(400, "confidential must be yes or no")
        with self.edit_lock:
            st = self._load(req, sid)
            meta = st.get("study") if isinstance(st.get("study"), dict) else {}
            if v == "yes":
                meta["confidential"] = True
            else:
                meta.pop("confidential", None)
            st["study"] = meta
            self.store_for(req.session).save(sid, st)
        return redirect(f"/s/{sid}?f={'confidential' if v == 'yes' else 'not-confidential'}#privacy")

    def delete_confirm(self, req, sid):
        return Response(views.confirm_delete(sid, self._load(req, sid), req.session))

    def delete(self, req, sid):
        store = self.store_for(req.session)
        store.delete(sid)
        stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.docs.move_to(sid, store.trash / f"{sid}.{stamp}.documents")
        return redirect("/?f=removed")

    def _draft_ctx(self, req, sid, st, state=None):
        private, why = calibrations.study_privacy(st)
        return {"info": self.drafter.describe(private), "private": private, "why": why,
                "drafts": self.store_for(req.session).load_drafts(sid), "state": state, "docs": self.docs.list(sid)}

    def _w1_page(self, req, sid, st, chk=None, flash="", form_error=None, draft_state=None, status=200):
        chk = chk or engine.check(st)
        return Response(views.w1_page(sid, st, chk, req.session, flash, form_error, req.arg("hl") or None,
                                      self._draft_ctx(req, sid, st, draft_state)), status)

    def w1(self, req, sid):
        return self._w1_page(req, sid, self._load(req, sid), flash=req.arg("f"))

    def _ws_page(self, req, sid, st, n, flash="", form_error=None, status=200, draft_state=None):
        chk = engine.check(st)
        reg = None
        if n == 5 and not chk["errors"] and chk["cal"]:
            reg = engine.register(st, chk["cal"])
        return Response(views_ws.workshop_page(sid, st, chk, n, req.session, flash, req.arg("hl") or None,
                                               form_error, reg, self._draft_ctx(req, sid, st, draft_state)), status)

    def _draft_page(self, req, sid, st, n, state, status):
        if n == 1:
            return self._w1_page(req, sid, st, draft_state=state, status=status)
        return self._ws_page(req, sid, st, n, draft_state=state, status=status)

    def workshop(self, req, sid, n):
        return self._ws_page(req, sid, self._load(req, sid), int(n), req.arg("f"))

    def locate(self, req, sid, eid):
        st = self._load(req, sid)
        idx = views.element_index(st)
        if eid not in idx:
            raise HTTPError(404, "no such element in this study")
        return redirect(views.locate_url(sid, eid, idx[eid][1]))

    def register(self, req, sid):
        st = self._load(req, sid)
        chk = engine.check(st)
        if chk["errors"] or not chk["cal"]:
            return Response(views.register_blocked(sid, st, chk, req.session))
        rows, summary = engine.register(st, chk["cal"])
        return Response(views.register_page(sid, st, chk, rows, summary, req.session))

    def _filename(self, sid, st, ext):
        meta = st.get("study") if isinstance(st.get("study"), dict) else {}
        base = re.sub(r"[^A-Za-z0-9._-]+", "-", str(meta.get("name") or "")).strip("-.")[:60] or sid
        return f"{base}.{ext}"

    def export_json(self, req, sid):
        st = self._load(req, sid)
        data = (json.dumps(st, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        return Response(data, 200, "application/json; charset=utf-8",
                        [("Content-Disposition", f'attachment; filename="{self._filename(sid, st, "json")}"')])

    def export_xlsx(self, req, sid):
        st = self._load(req, sid)
        chk = engine.check(st)
        if chk["errors"] or not chk["cal"]:
            raise HTTPError(409, "the engine exports only a study without errors; fix the errors listed in the checks")
        if not engine.have_xlsx():
            raise HTTPError(501, "the Excel export needs openpyxl, which is not installed here; the JSON export works")
        data = engine.to_xlsx_bytes(st, chk["cal"], self.tmp_dir)
        return Response(data, 200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        [("Content-Disposition", f'attachment; filename="{self._filename(sid, st, "xlsx")}"')])

    # ---------- workshop 1 editor ----------

    def _w1_fields(self, key, req, st, cal):
        """Read and check the submitted fields. Links must name existing ids of the right type."""
        out = {}

        def text(name, required=False, limit=500):
            v = req.field(name).strip()
            if required and not v:
                raise FormError(f"{name} is required", name)
            out[name] = v[:limit] if v else None

        bv_ids = {b.get("id") for b in st.get("business_values") or [] if isinstance(b, dict)}
        if key == "business_values":
            text("label", True)
            nat = req.field("nature")
            if nat and nat not in views.NATURES:
                raise FormError("nature must be process or information", "nature")
            out["nature"] = nat or None
            text("owner", limit=200)
        elif key == "supporting_assets":
            text("label", True)
            picked = list(dict.fromkeys(req.fields("business_values")))
            bad = [x for x in picked if x not in bv_ids]
            if bad:
                raise FormError("pick business values from the list", "business_values")
            out["business_values"] = picked
        elif key == "feared_events":
            bv = req.field("business_value")
            if bv not in bv_ids:
                raise FormError("pick the business value from the list", "business_value")
            out["business_value"] = bv
            text("label", True)
            text("criterion", limit=100)
            try:
                sev = int(req.field("severity"))
            except ValueError:
                raise FormError("pick a severity", "severity")
            if sev not in [x["n"] for x in (cal or {}).get("severity", [])]:
                raise FormError("pick a severity from the calibration's scale", "severity")
            out["severity"] = sev
        elif key == "baseline":
            text("reference", True)
            stt = req.field("status")
            if stt and stt not in views.BASELINE_STATUS:
                raise FormError("unknown status", "status")
            out["status"] = stt or None
            text("gap", limit=1000)
        return out

    @staticmethod
    def _w1_echo(key, req, el=None):
        """What the user typed in a W1 form, element-shaped, to show a refused form again. Never stored."""
        e = {"id": el.get("id")} if el else {}
        for name in W1_TEXT[key]:
            e[name] = req.field(name)
        if key == "supporting_assets":
            e["business_values"] = req.fields("business_values")
        return e

    @staticmethod
    def _refusal(e):
        """(message above the form, {field: message}) for a FormError."""
        return ("", {e.field: str(e)}) if e.field else (str(e), {})

    @staticmethod
    def _next_id(st, prefix):
        used = set()
        for k in engine.COLLECTIONS:
            for x in st.get(k) or []:
                if isinstance(x, dict):
                    used.add(str(x.get("id")))
                    for p in (x.get("paths") or []) if k == "strategic_scenarios" else []:
                        if isinstance(p, dict):
                            used.add(str(p.get("id")))
        nums = [int(m.group(1)) for u in used if (m := re.fullmatch(re.escape(prefix) + r"(\d+)", u))]
        n = max(nums, default=0) + 1
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    @staticmethod
    def _apply(el, fields):
        for k, v in fields.items():
            if v is None or v == "":
                el.pop(k, None)
            else:
                el[k] = v
        return el

    def w1_add(self, req, sid, slug):
        key = views.W1[slug]
        with self.edit_lock:
            st = self._load(req, sid)
            chk = engine.check(st)
            try:
                fields = self._w1_fields(key, req, st, chk.get("cal"))
            except FormError as e:
                msg, errs = self._refusal(e)
                return self._w1_page(req, sid, st, chk, form_error=(key, msg, errs, self._w1_echo(key, req)), status=400)
            el = self._apply({"id": self._next_id(st, views.W1_PREFIX[key])}, fields)
            if not isinstance(st.get(key), list):
                st[key] = []
            st[key].append(el)
            self.store_for(req.session).save(sid, st)
        return redirect(f"/s/{sid}/w1?f=added&hl={urllib.parse.quote(el['id'], safe='')}#{views.anchor(el['id'])}")

    def _find(self, st, key, eid):
        for x in st.get(key) or []:
            if isinstance(x, dict) and str(x.get("id")) == eid:
                return x
        raise HTTPError(404, "no such element")

    def w1_edit_form(self, req, sid, slug, eid):
        key = views.W1[slug]
        st = self._load(req, sid)
        return Response(views.w1_edit(sid, st, engine.check(st), key, self._find(st, key, eid), req.session))

    def w1_save(self, req, sid, slug, eid):
        key = views.W1[slug]
        with self.edit_lock:
            st = self._load(req, sid)
            el = self._find(st, key, eid)
            chk = engine.check(st)
            try:
                fields = self._w1_fields(key, req, st, chk.get("cal"))
            except FormError as e:
                msg, errs = self._refusal(e)
                return Response(views.w1_edit(sid, st, chk, key, el, req.session, msg, errs,
                                              self._w1_echo(key, req, el)), 400)
            self._apply(el, fields)
            self.store_for(req.session).save(sid, st)
        return redirect(f"/s/{sid}/w1?f=saved&hl={urllib.parse.quote(eid, safe='')}#{views.anchor(eid)}")

    def w1_delete(self, req, sid, slug, eid):
        key = views.W1[slug]
        with self.edit_lock:
            st = self._load(req, sid)
            el = self._find(st, key, eid)
            st[key] = [x for x in st[key] if x is not el]
            self.store_for(req.session).save(sid, st)
        return redirect(f"/s/{sid}/w1?f=deleted#sec-{urllib.parse.quote(slug)}")

    # ---------- workshop 2 to 5 editors ----------

    @staticmethod
    def _spec(n, slug):
        key, ws, prefix = editors.SPECS[slug]
        if ws != int(n):
            raise HTTPError(404, "not found")
        return key, ws, prefix

    def _build(self, st, n, slug, req, eid=None):
        """The study with one W2-W5 element added (eid None) or updated, as a copy: (candidate, element).

        Raises editors.FormError for a value the form refuses, EngineRefused for one the engine refuses. The
        severities of strategic scenarios and risks are the engine's (engine.take_severities), never the form's.
        """
        key, ws, prefix = self._spec(n, slug)
        before = engine.check(st)
        el = None if eid is None else self._find(st, key, eid)
        fields = editors.parse(slug, req, st, el)
        paths = editors.parse_paths(req, st, el) if slug == "ss" else None
        cand = copy.deepcopy(st)
        if not isinstance(cand.get(key), list):
            cand[key] = []
        if el is None:
            target = {"id": editors.next_id(cand, prefix)}
            cand[key].append(target)
        else:
            target = next(x for x in cand[key] if isinstance(x, dict) and str(x.get("id")) == eid)
        editors.apply(target, fields)
        if paths is not None:
            taken = {p.get("id") for p in paths if p.get("id")}
            for p in paths:
                if p.get("id") is None:
                    p["id"] = editors.next_path_id(cand, target["id"], taken)
                    taken.add(p["id"])
            if paths:
                target["paths"] = paths
            else:
                target.pop("paths", None)
        if key in engine.DERIVED_SEVERITY and before.get("cal"):
            engine.take_severities(cand, before["cal"], only=target["id"])
        refused = editors.scale_refusals(before, engine.check(cand), target["id"])
        if refused:
            by_field = editors.refusal_fields(slug, refused)
            rest = [m for m in refused if m not in by_field.values()]
            errs = {k: "The engine refused the value: " + m for k, m in by_field.items()}
            raise EngineRefused("The engine refused the value: " + "; ".join(rest) if rest else "", errs)
        return cand, target

    def _commit(self, req, sid, n, slug, eid=None):
        """Add (eid None) or update one element. Returns a Response. The file changes only on success."""
        key, ws, prefix = self._spec(n, slug)
        with self.edit_lock:
            st = self._load(req, sid)
            el = None if eid is None else self._find(st, key, eid)

            def refuse(msg, errs):
                """Show the form again with what was typed and each message next to its field; store nothing."""
                sticky = editors.echo(slug, req, el)
                if el is None:
                    return self._ws_page(req, sid, st, ws, form_error=(slug, msg, errs, sticky), status=400)
                return Response(views_ws.edit_page(sid, st, engine.check(st), slug, el, req.session, msg, errs,
                                                   sticky), 400)
            try:
                cand, target = self._build(st, n, slug, req, eid)
            except editors.FormError as e:
                return refuse(*self._refusal(e))
            except EngineRefused as e:
                return refuse(e.message, e.errs)
            self.store_for(req.session).save(sid, cand)
        flag = "added" if el is None else "saved"
        return redirect(f"/s/{sid}/w{ws}?f={flag}&hl={urllib.parse.quote(target['id'], safe='')}"
                        f"#{views.anchor(target['id'])}")

    def ws_add(self, req, sid, n, slug):
        return self._commit(req, sid, n, slug)

    def ws_save(self, req, sid, n, slug, eid):
        return self._commit(req, sid, n, slug, eid)

    def ws_edit_form(self, req, sid, n, slug, eid):
        key, _, _ = self._spec(n, slug)
        st = self._load(req, sid)
        return Response(views_ws.edit_page(sid, st, engine.check(st), slug, self._find(st, key, eid), req.session))

    def ws_delete(self, req, sid, n, slug, eid):
        key, ws, _ = self._spec(n, slug)
        with self.edit_lock:
            st = self._load(req, sid)
            el = self._find(st, key, eid)
            st[key] = [x for x in st[key] if x is not el]
            self.store_for(req.session).save(sid, st)
        return redirect(f"/s/{sid}/w{ws}?f=deleted#sec-{slug}")

    def take_severities(self, req, sid):
        back = req.field("back")
        if back not in ("w3", "w5"):
            raise HTTPError(400, "unknown return page")
        with self.edit_lock:
            st = self._load(req, sid)
            chk = engine.check(st)
            if not chk.get("cal"):
                raise HTTPError(409, "the study's calibration could not be loaded")
            changed = engine.take_severities(st, chk["cal"])
            if changed:
                self.store_for(req.session).save(sid, st)
        return redirect(f"/s/{sid}/{back}?f={'synced' if changed else 'unchanged'}")

    # ---------- settings ----------

    def _settings_raw(self):
        path = config.settings_path(self.data_dir)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        return (raw if isinstance(raw, dict) else {}), path

    def settings_form(self, req):
        raw, path = self._settings_raw()
        info = self.drafter.describe(False)
        return Response(views_draft.settings_page(info, raw, path, config.settings_mode_problem(path), req.session,
                                                  req.arg("f"), saved_problem=info.get("problem")))

    def settings_save(self, req):
        """Check and store the settings form (mode 0600, atomic). Refused: the form comes back with what was typed."""
        errs = {}
        route = req.field("route")
        if route not in drafting.ROUTES:
            errs["route"] = "pick off, local or remote"

        def number(name, lo, hi):
            v = req.field(name).strip()
            try:
                n = int(v)
            except ValueError:
                errs[name] = "a whole number is required"
                return None
            if not lo <= n <= hi:
                errs[name] = f"between {lo} and {hi}"
                return None
            return n

        def key_file(name):
            v = req.field(name).strip()[:500]
            if v:
                p = pathlib.Path(v).expanduser()
                try:
                    st_ = p.stat()
                except OSError:
                    errs[name] = "this file does not exist"
                    return v
                if not p.is_file() or st_.st_mode & 0o077:
                    errs[name] = "the key file must be a regular file with mode 600"
            return v
        port = number("local_port", 1, 65535)
        lpath = req.field("local_path").strip() or "/v1"
        if not re.fullmatch(r"/[A-Za-z0-9/_.\-]{0,99}", lpath):
            errs["local_path"] = "a path such as /v1"
        lmodel = req.field("local_model").strip()[:200]
        lkey = key_file("local_key_file")
        hint = " ".join(req.field("local_ssh_hint").split())[:400]
        rurl = req.field("remote_base_url").strip()[:500]
        rmodel = req.field("remote_model").strip()[:200]
        rkey = key_file("remote_key_file")
        if rurl:
            u = urllib.parse.urlsplit(rurl)
            if u.scheme not in ("http", "https") or not u.hostname:
                errs["remote_base_url"] = "an http:// or https:// URL"
        if route == "local" and not lmodel:
            errs["local_model"] = "the local route needs a model name"
        if route == "remote":
            if not rurl:
                errs["remote_base_url"] = "the remote route needs a base URL"
            if not rmodel:
                errs["remote_model"] = "the remote route needs a model name"
        lims = {k: number(f"limits_{k}", drafting.FLOORS[k], drafting.CEILINGS[k]) for k in drafting.DEFAULT_LIMITS}
        if errs:
            raw, path = self._settings_raw()
            sticky = {k: v[0] for k, v in req.form.items() if k != "csrf"}
            return Response(views_draft.settings_page(self.drafter.describe(False), raw, path,
                                                      config.settings_mode_problem(path), req.session, errs=errs,
                                                      sticky=sticky), 400)
        raw, _ = self._settings_raw()
        data = {"route": route,
                "local": {"port": port, "path": lpath, "model": lmodel, "key_file": lkey, "ssh_hint": hint},
                "remote": {"base_url": rurl, "model": rmodel, "key_file": rkey},
                "limits": lims, "timeout": raw.get("timeout", 120)}
        with self.edit_lock:
            config.save_settings(self.data_dir, data)
            self.load_drafter()
        return redirect("/settings?f=settings-saved")

    # ---------- documents ----------

    def _docs_page(self, req, sid, st, flash="", error="", status=200):
        private, why = calibrations.study_privacy(st)
        return Response(views_draft.documents_page(sid, st, engine.check(st), self.docs.list(sid), req.session, flash,
                                                   error, private, why, documents.pdftotext_path()), status)

    def documents(self, req, sid):
        return self._docs_page(req, sid, self._load(req, sid), req.arg("f"))

    def document_upload(self, req, sid):
        st = self._load(req, sid)
        f = req.files.get("file")
        if not f or not f[1]:
            return self._docs_page(req, sid, st, error="Choose a file to upload.", status=400)
        try:
            self.docs.add(sid, f[0], f[1])
        except documents.DocumentError as e:
            return self._docs_page(req, sid, st, error=f"Not uploaded: {e}.", status=400)
        return redirect(f"/s/{sid}/docs?f=uploaded")

    def document_delete(self, req, sid, did):
        self._load(req, sid)
        self.docs.delete(sid, did)
        return redirect(f"/s/{sid}/docs?f=doc-deleted")

    # ---------- drafting (workshops 1 to 5) ----------

    def draft(self, req, sid):
        """Ask the drafting adapter for proposals. They go to the study's draft file, not into the study."""
        st = self._load(req, sid)
        try:
            n = int(req.field("ws") or "1")
        except ValueError:
            n = 0
        if n not in range(1, 6):
            raise HTTPError(400, "unknown workshop")
        private, _ = calibrations.study_privacy(st)
        pasted = req.field("text").strip()
        known = {d["id"]: d for d in self.docs.list(sid)}
        picked = list(dict.fromkeys(req.fields("docs")))
        state = {"text": pasted[:drafting.MAX_TEXT], "docs": picked}
        if any(d not in known for d in picked):
            return self._draft_page(req, sid, st, n, dict(state, error="Pick documents from the list."), 400)
        if len(pasted) > drafting.MAX_TEXT:
            return self._draft_page(req, sid, st, n, dict(
                state, error=f"The pasted text is over {drafting.MAX_TEXT} characters; paste a shorter part."), 400)
        parts = [f"[Document: {known[d]['name']}]\n{self.docs.text(sid, d)}" for d in picked]
        if pasted:
            parts.append("[Pasted text]\n" + pasted)
        ctx = {"text": "\n\n".join(parts), "private": private, "study_id": sid, "documents": len(picked),
               "study": drafts.study_summary(st, n)}
        status = None
        try:
            out = self.drafter.draft(f"w{n}", ctx)
        except drafting.RouteRefused as e:
            status, msg = 403, str(e)
        except drafting.RateLimited as e:
            status, msg = 429, str(e)
        except (drafting.Unusable, drafting.EndpointError) as e:
            status, msg = 502, str(e)
        except drafting.DraftError as e:
            status, msg = 400, str(e)
        if status:
            if not msg.endswith("."):
                msg += "."
            return self._draft_page(req, sid, st, n, dict(state, error=msg[0].upper() + msg[1:]), status)
        with self.edit_lock:
            store = self.store_for(req.session)
            d = store.load_drafts(sid)
            d.pop("unreadable", None)
            known = drafts.known_keys(self._load(req, sid), d["items"])
            fresh = [it for it in out["items"] if drafts.key(it) not in known]
            if not fresh:
                return redirect(f"/s/{sid}/w{n}?f=drafted-nothing-new#draft")
            out["items"] = fresh
            k = int(d.get("next") or 1)
            b = len(d["batches"]) + 1
            d["batches"].append({"id": f"B{b}", "ws": f"w{n}", "at": datetime.datetime.now().isoformat(timespec="seconds"),
                                 "model": out["model"], "route": out["route"], "requests": out["requests"],
                                 "covered": out["covered"], "total": out["total"], "documents": len(picked)})
            for it in out["items"]:
                d["items"].append(dict(it, id=f"D{k}", batch=f"B{b}", state="draft"))
                k += 1
            d["next"] = k
            store.save_drafts(sid, d)
        return redirect(f"/s/{sid}/w{n}?f=drafted#draft")

    def _find_draft(self, d, did):
        it = next((x for x in d["items"] if isinstance(x, dict) and x.get("id") == did), None)
        if it is None:
            raise HTTPError(404, "no such draft item (already accepted or rejected?)")
        if it.get("kind") not in drafting.KIND_WS:
            raise HTTPError(400, "unknown draft item kind")
        return it

    def _add_w1(self, st, key, req):
        """Add one W1 element from a form (the same checks as the W1 add form). Raises FormError. Returns it."""
        fields = self._w1_fields(key, req, st, engine.check(st).get("cal"))
        el = self._apply({"id": self._next_id(st, views.W1_PREFIX[key])}, fields)
        if not isinstance(st.get(key), list):
            st[key] = []
        st[key].append(el)
        return el

    def draft_accept(self, req, sid, did):
        """Turn one draft item into a study element with the values the user confirmed in its form.

        The form goes through the same checks as the workshop's own add form. Severity, likelihood, decision and
        status are the user's picks (the draft item has none), and the engine computes scenario severities.
        """
        with self.edit_lock:
            store = self.store_for(req.session)
            st = self._load(req, sid)
            d = store.load_drafts(sid)
            it = self._find_draft(d, did)
            kind, n = it["kind"], drafts.ws_number(it)
            try:
                if kind in drafts.W1_KINDS:
                    cand = copy.deepcopy(st)
                    el = self._add_w1(cand, drafts.W1_KINDS[kind], req)
                else:
                    cand, el = self._build(st, n, drafts.KIND_SLUG[kind], req)
            except (FormError, editors.FormError, EngineRefused) as e:
                if isinstance(e, EngineRefused):
                    msg, errs = e.message, e.errs
                else:
                    msg, errs = self._refusal(e)
                sticky = (self._w1_echo(drafts.W1_KINDS[kind], req) if kind in drafts.W1_KINDS
                          else editors.echo(drafts.KIND_SLUG[kind], req))
                return self._draft_page(req, sid, st, n, {"item": did, "msg": msg, "errs": errs, "sticky": sticky}, 400)
            store.save(sid, cand)
            d["items"] = [x for x in d["items"] if x is not it]
            store.save_drafts(sid, d)
        return redirect(f"/s/{sid}/w{n}?f=draft-accepted&hl={urllib.parse.quote(el['id'], safe='')}#{views.anchor(el['id'])}")

    def draft_accept_all(self, req, sid):
        """Accept every pending text-only item of one workshop (business values, supporting assets, stakeholders).
        Items that need a pick of the user (severity, likelihood, decision, status, links) are never accepted here."""
        try:
            n = int(req.field("ws"))
        except ValueError:
            raise HTTPError(400, "unknown workshop")
        with self.edit_lock:
            store = self.store_for(req.session)
            st = self._load(req, sid)
            d = store.load_drafts(sid)
            order = {k: i for i, k in enumerate(drafts.KIND_ORDER)}
            pending = sorted((x for x in d["items"] if isinstance(x, dict) and drafts.ws_number(x) == n
                              and x.get("kind") in drafting.TEXT_ONLY_KINDS), key=lambda x: order[x["kind"]])
            cand, done = copy.deepcopy(st), []
            for it in pending:
                form = drafts.Form(drafts.as_form(cand, it))
                try:
                    if it["kind"] in drafts.W1_KINDS:
                        self._add_w1(cand, drafts.W1_KINDS[it["kind"]], form)
                    else:
                        cand, _ = self._build(cand, n, drafts.KIND_SLUG[it["kind"]], form)
                except (FormError, editors.FormError, EngineRefused):
                    continue  # stays in the list, to be accepted one by one
                done.append(it)
            if done:
                store.save(sid, cand)
                d["items"] = [x for x in d["items"] if not any(x is y for y in done)]
                store.save_drafts(sid, d)
        return redirect(f"/s/{sid}/w{n}?f=drafts-accepted-all#draft")

    def draft_reject(self, req, sid, did):
        with self.edit_lock:
            store = self.store_for(req.session)
            self._load(req, sid)
            d = store.load_drafts(sid)
            it = next((x for x in d["items"] if isinstance(x, dict) and x.get("id") == did), None)
            if it is None:
                raise HTTPError(404, "no such draft item (already accepted or rejected?)")
            d["items"] = [x for x in d["items"] if x is not it]
            store.save_drafts(sid, d)
        return redirect(f"/s/{sid}/w{drafts.ws_number(it)}?f=draft-rejected#draft")

    def draft_clear(self, req, sid):
        """Reject every pending draft item of one workshop (ws field), or of the whole study without it."""
        ws = req.field("ws")
        with self.edit_lock:
            store = self.store_for(req.session)
            self._load(req, sid)
            d = store.load_drafts(sid)
            if ws in ("1", "2", "3", "4", "5"):
                d["items"] = [x for x in d["items"] if not (isinstance(x, dict) and drafts.ws_number(x) == int(ws))]
            else:
                d = {"items": [], "batches": []}
            store.save_drafts(sid, d)
        return redirect(f"/s/{sid}/w{ws if ws in ('1', '2', '3', '4', '5') else '1'}?f=drafts-cleared#draft")
