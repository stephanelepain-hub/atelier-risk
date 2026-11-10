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

from . import REPO_DIR, STATIC_DIR, auth, calibrations, config, editors, engine, views, views_ws
from .storage import NotFound, Store
from .web import HTTPError, Request, Response, Router, redirect

MAX_UPLOAD = config.MAX_UPLOAD
EXAMPLE = REPO_DIR / "examples" / "anssi-guide-vaccine-example.json"
SID = r"(s-[0-9]{8}-[0-9a-f]{8})"
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


class FormError(Exception):
    pass


def allowed_hosts_for(port, extra=()):
    return {f"127.0.0.1:{port}", f"localhost:{port}"} | {h.lower() for h in extra}


def _no_constants(x):
    raise ValueError(f"{x} is not valid JSON")


class App:
    def __init__(self, data_dir, private_dir=None, port=config.DEFAULT_PORT, extra_hosts=(), max_upload=MAX_UPLOAD):
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
        self.router = self._routes()

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
        r.add("POST", r"/new", self.new_study)
        r.add("POST", r"/import", self.import_study)
        r.add("POST", r"/example", self.load_example)
        r.add("GET", r"/cal/([A-Za-z0-9._%-]+)\.css", self.cal_css)
        r.add("GET", rf"/s/{SID}", self.overview)
        r.add("POST", rf"/s/{SID}/rename", self.rename)
        r.add("POST", rf"/s/{SID}/duplicate", self.duplicate)
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
            if len(req.body) > self.max_upload:
                raise HTTPError(413, f"request body over {self.max_upload // (1024 * 1024)} MB")
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

    def too_large(self):
        return self.secure(Response(views.error_page(413, f"request body over {self.max_upload // (1024 * 1024)} MB"), 413))

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
        except calibrations.CalibrationError as e:
            raise HTTPError(404, str(e))
        return Response(views.cal_css(cal), 200, "text/css; charset=utf-8")

    # ---------- study list ----------

    def index(self, req):
        rows = []
        for sid, st, mtime in self.store_for(req.session).list():
            chk = engine.check(st) if st is not None else {"errors": ["file unreadable"], "warnings": [],
                                                            "calibration": "?", "cal": None}
            rows.append((sid, st, mtime, chk))
        return Response(views.study_list(rows, calibrations.available(), req.session, req.arg("f")))

    def new_study(self, req):
        name = req.field("name").strip()
        if not name or len(name) > 200:
            raise HTTPError(400, "a name of 1 to 200 characters is required")
        cal = req.field("calibration") or calibrations.DEFAULT
        if cal not in calibrations.available():
            raise HTTPError(400, "unknown calibration")
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
        return Response(views.overview(sid, st, engine.check(st), self.store_for(req.session).mtime(sid), req.session, req.arg("f")))

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
        st = self._load(req, sid)
        meta = st.get("study") if isinstance(st.get("study"), dict) else {}
        meta["name"] = (meta.get("name") or "study") + " (copy)"
        st["study"] = meta
        self.store_for(req.session).create(st)
        return redirect("/?f=duplicated")

    def delete_confirm(self, req, sid):
        return Response(views.confirm_delete(sid, self._load(req, sid), req.session))

    def delete(self, req, sid):
        self.store_for(req.session).delete(sid)
        return redirect("/?f=removed")

    def w1(self, req, sid):
        st = self._load(req, sid)
        return Response(views.w1_page(sid, st, engine.check(st), req.session, req.arg("f"), hl=req.arg("hl") or None))

    def _ws_page(self, req, sid, st, n, flash="", form_error=None, status=200):
        chk = engine.check(st)
        reg = None
        if n == 5 and not chk["errors"] and chk["cal"]:
            reg = engine.register(st, chk["cal"])
        return Response(views_ws.workshop_page(sid, st, chk, n, req.session, flash, req.arg("hl") or None,
                                               form_error, reg), status)

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
                raise FormError(f"{name} is required")
            out[name] = v[:limit] if v else None

        bv_ids = {b.get("id") for b in st.get("business_values") or [] if isinstance(b, dict)}
        if key == "business_values":
            text("label", True)
            nat = req.field("nature")
            if nat and nat not in views.NATURES:
                raise FormError("nature must be process or information")
            out["nature"] = nat or None
            text("owner", limit=200)
        elif key == "supporting_assets":
            text("label", True)
            picked = list(dict.fromkeys(req.fields("business_values")))
            bad = [x for x in picked if x not in bv_ids]
            if bad:
                raise FormError("pick business values from the list")
            out["business_values"] = picked
        elif key == "feared_events":
            bv = req.field("business_value")
            if bv not in bv_ids:
                raise FormError("pick the business value from the list")
            out["business_value"] = bv
            text("label", True)
            text("criterion", limit=100)
            try:
                sev = int(req.field("severity"))
            except ValueError:
                raise FormError("pick a severity")
            if sev not in [x["n"] for x in (cal or {}).get("severity", [])]:
                raise FormError("pick a severity from the calibration's scale")
            out["severity"] = sev
        elif key == "baseline":
            text("reference", True)
            stt = req.field("status")
            if stt and stt not in views.BASELINE_STATUS:
                raise FormError("unknown status")
            out["status"] = stt or None
            text("gap", limit=1000)
        return out

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
                return Response(views.w1_page(sid, st, chk, req.session, form_error=(key, str(e))), 400)
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
                return Response(views.w1_edit(sid, st, chk, key, el, req.session, str(e)), 400)
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

    def _commit(self, req, sid, n, slug, eid=None):
        """Add (eid None) or update one element. Returns a Response. The file changes only on success."""
        key, ws, prefix = self._spec(n, slug)
        with self.edit_lock:
            st = self._load(req, sid)
            before = engine.check(st)
            el = None if eid is None else self._find(st, key, eid)

            def refuse(msg):
                if el is None:
                    return self._ws_page(req, sid, st, ws, form_error=(slug, msg), status=400)
                return Response(views_ws.edit_page(sid, st, before, slug, el, req.session, msg), 400)
            try:
                fields = editors.parse(slug, req, st, el)
                paths = editors.parse_paths(req, st, el) if slug == "ss" else None
            except editors.FormError as e:
                return refuse(str(e))
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
                return refuse("The engine refused the value: " + "; ".join(refused))
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
