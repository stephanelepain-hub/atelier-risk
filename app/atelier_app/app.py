"""The application: routes, authentication and CSRF gates, security headers, study handlers."""
import hmac
import ipaddress
import json
import os
import pathlib
import re
import sys
import threading
import traceback
import urllib.parse

from . import STATIC_DIR, auth, calibrations, config, engine, findings, labels, views, views_how, views_public, views_quick, workspaces
from .expert_routes import ExpertRoutes
from .quick_routes import ORDER, QuickRoutes
from .storage import NotFound, Store, StudyLimit
from .web import HTTPError, Request, Response, Router, redirect

MAX_UPLOAD = config.MAX_UPLOAD
SID = r"(s-[0-9]{8}-[0-9a-f]{8})"
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
EXPERT_COOKIE = "expert"




def allowed_hosts_for(port, extra=()):
    return {f"127.0.0.1:{port}", f"localhost:{port}"} | {h.lower() for h in extra}


class App(ExpertRoutes, QuickRoutes):
    def __init__(self, data_dir, port=config.DEFAULT_PORT, extra_hosts=(), max_upload=MAX_UPLOAD,
                 public=False, invite_code=None, behind_proxy=False):
        """public=True is the internet edition: no token login; each visitor gets an anonymous private workspace
        (see workspaces.py). invite_code (a string, or None for none) is asked on the join screen. behind_proxy=True
        reads the client address from X-Real-IP (set by the local reverse proxy) instead of the socket address."""
        self.data_dir = pathlib.Path(data_dir)
        self.public = bool(public)
        self.invite_code = (invite_code.strip() or None) if isinstance(invite_code, str) else None
        self.behind_proxy = bool(behind_proxy)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.tmp_dir = self.data_dir / "tmp"
        self.tmp_dir.mkdir(exist_ok=True, mode=0o700)
        os.chmod(self.tmp_dir, 0o700)
        self.token_path = self.data_dir / "token"
        if self.public:   # no login token, no shared study store: every visitor has a workspace of their own
            self.store, self.token_created, self.auth = None, False, auth.Auth("")
            self.workspaces = workspaces.Workspaces(self.data_dir)
            self.join_limiter = workspaces.JoinLimiter()
        else:
            self.store = Store(self.data_dir)
            token, self.token_created = auth.load_or_create_token(self.token_path)
            self.auth = auth.Auth(token)
            self.workspaces = None
        self.max_upload = max_upload
        self.extra_hosts = tuple(extra_hosts)
        self.set_port(port)
        self.edit_lock = threading.Lock()
        self.router = self._routes()

    def body_limit(self, path):
        """Request body cap: max_upload for every request; the saved-file upload of public mode has its own cap
        (the file is at most OPEN_MAX bytes; the form encoding of a JSON file may need up to three times that)."""
        if self.public and path == "/quick/open":
            return min(self.max_upload, 3 * views_public.OPEN_MAX + 8192)
        return self.max_upload

    def store_for(self, session):
        """The study store of a session's user. A local install has one user and one store; in public mode each
        workspace has its own."""
        if self.public:
            return self.workspaces.store(session.user)
        return self.store

    def client_address(self, req):
        """The address the rate limit counts: X-Real-IP behind the local proxy (when it holds an address), else the
        socket address."""
        if self.behind_proxy:
            try:
                return str(ipaddress.ip_address(req.headers.get("x-real-ip", "").strip()))
            except ValueError:
                pass
        return req.peer or "unknown"

    def purge_idle(self, days=workspaces.IDLE_DAYS):
        """Public mode: delete every workspace not visited for `days` days. Returns how many were deleted."""
        return self.workspaces.purge_idle(days) if self.public else 0

    def set_port(self, port):
        self.port = port
        self.allowed_hosts = allowed_hosts_for(port, self.extra_hosts)

    # ---------- plumbing ----------

    def _routes(self):
        r = Router()
        self.add_quick_routes(r)
        self.add_expert_routes(r)
        r.add("GET", r"/how", self.how, public=True)
        r.add("POST", r"/expert", self.expert_switch)
        if self.public:
            r.add("GET", r"/join", self.join_form, public=True)
            r.add("POST", r"/join", self.join, public=True)
            r.add("POST", r"/forget", self.forget)
        else:
            r.add("GET", r"/login", self.login_form, public=True)
            r.add("POST", r"/login", self.login, public=True)
            r.add("GET", r"/login/once", self.login_once, public=True)
            r.add("POST", r"/logout", self.logout)
            r.add("POST", r"/login/link", self.login_link)
        r.add("GET", r"/static/([a-z]+\.(?:css|js))", self.static, public=True)
        r.add("GET", r"/static/brand/logo\.svg", self.brand_logo, public=True)
        r.add("GET", r"/studies", self.index)
        r.add("GET", r"/cal/([A-Za-z0-9._%-]+)\.css", self.cal_css)
        r.add("GET", rf"/s/{SID}/delete", self.delete_confirm)
        r.add("POST", rf"/s/{SID}/delete", self.delete)
        r.add("GET", rf"/s/{SID}/export\.json", self.export_json)
        r.add("GET", rf"/s/{SID}/export\.xlsx", self.export_xlsx)
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
            req.session = self._workspace_session(req) if self.public else self.auth.get(req.cookies.get(auth.SESSION_COOKIE))
            if req.session:
                req.session.expert = req.cookies.get(EXPERT_COOKIE) == "1"
                req.session.path = req.path if req.method == "GET" else ""
            if not public and not req.session:
                if self.public:   # no workspace (new visitor, or an expired one): the join screen
                    return self.secure(redirect("/join"))
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
        except StudyLimit:
            resp = Response(views_public.limit_page(self._lang(req), req.session), 409)
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

    # ---------- public mode: join, workspace, forget ----------

    def _workspace_session(self, req):
        """The session of the workspace named by the cookie, or None. Every page a visitor opens counts as a visit."""
        wid = req.cookies.get(workspaces.COOKIE)
        h = self.workspaces.find(wid)
        if h is None:
            return None
        if not req.path.startswith(("/static/", "/cal/")):
            self.workspaces.touch(h)
        return self.workspaces.session(wid, h)

    def join_form(self, req, message_key="", status=200):
        if req.session:
            return redirect("/")
        lang = self._lang(req)
        if self.workspaces.full():
            return self._remember(req, Response(views_public.full_page(lang), 503, headers=[("Retry-After", "3600")]), lang)
        pre = auth.secrets.token_urlsafe(24)
        resp = Response(views_public.join_page(pre, lang, self.invite_code is not None, message_key), status)
        resp.header("Set-Cookie", f"{auth.PRE_COOKIE}={pre}; HttpOnly; Secure; SameSite=Strict; Path=/join")
        return self._remember(req, resp, lang)

    def join(self, req):
        if req.session:
            return redirect("/")
        pre_c, pre_f = req.cookies.get(auth.PRE_COOKIE, ""), req.field("pre")
        if not pre_c or not pre_f or not hmac.compare_digest(pre_c.encode("utf-8"), pre_f.encode("utf-8")):
            return self.join_form(req, "expired", 403)
        client = self.client_address(req)
        if self.join_limiter.locked(client):
            return self.join_form(req, "wait", 429)
        if self.invite_code is not None and not hmac.compare_digest(req.field("code").strip().encode("utf-8"),
                                                                    self.invite_code.encode("utf-8")):
            self.join_limiter.fail(client)
            return self.join_form(req, "bad_code", 403)
        if self.workspaces.full():
            return self.join_form(req)
        wid = self.workspaces.create()
        resp = redirect("/")
        resp.header("Set-Cookie", workspaces.cookie_header(wid))
        resp.header("Set-Cookie", f"{auth.PRE_COOKIE}=; HttpOnly; Secure; SameSite=Strict; Path=/join; Max-Age=0")
        return resp

    def forget(self, req):
        """Delete the visitor's workspace at once, clear the cookie, say goodbye."""
        self.workspaces.remove(req.session.user)
        resp = Response(views_public.goodbye_page(self._lang(req)))
        resp.header("Set-Cookie", workspaces.clear_cookie_header())
        return resp

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
            return self.login_form(req, "Please wait a minute, then try the token again.", 429)
        if res != "ok":
            return self.login_form(req, "Check the token and try again.", 403)
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
            return self.login_form(req, "Ask for a fresh login link; each one works once.", 403)
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

    # ---------- Expert switch and "How it works" ----------

    def expert_switch(self, req):
        """Turn Expert mode on (`on`=1) or off (`on`=0) in a cookie, then go back to the page the switch was on."""
        on = req.field("on")
        if on not in ("0", "1"):
            raise HTTPError(400, "on must be 1 or 0")
        nxt = req.field("next") or urllib.parse.urlsplit(req.headers.get("referer", "")).path or "/"
        if not NEXT_RE.fullmatch(nxt) or nxt.startswith("//"):
            nxt = "/"
        resp = redirect(nxt)
        resp.header("Set-Cookie", f"{EXPERT_COOKIE}={on}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000")
        return resp

    def how(self, req):
        lang = self._lang(req)
        return self._remember(req, Response(views_how.how(req.session, lang, self.public)), lang)

    # ---------- static ----------

    def static(self, req, name):
        if name not in STATIC:
            raise HTTPError(404, "not found")
        return Response((STATIC_DIR / name).read_bytes(), 200, STATIC[name])

    def brand_logo(self, req):
        """The brand logo, only when the file exists (it is supplied later; nothing is drawn or created here)."""
        p = views.logo_path()
        if not p.is_file():
            raise HTTPError(404, "not found")
        return Response(p.read_bytes(), 200, "image/svg+xml")

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
            qk = st.get("quick") if isinstance(st, dict) else None
            step = (qk.get("step") if qk.get("step") in ORDER else "about") if isinstance(qk, dict) else None
            rows.append((sid, st, mtime, step))
        if not self.public:
            return Response(views.study_list(rows, req.session, req.arg("f")))
        lang = self._lang(req)
        return self._remember(req, Response(views.study_list(rows, req.session, req.arg("f"), lang,
                                                             views_public.open_form(req.session, lang), True)), lang)

    def delete_confirm(self, req, sid):
        return Response(views.confirm_delete(sid, self._load(req, sid), req.session))

    def delete(self, req, sid):
        store = self.store_for(req.session)
        store.delete(sid)
        return redirect("/studies?f=removed")

    def _filename(self, sid, st, ext):
        meta = st.get("study") if isinstance(st.get("study"), dict) else {}
        base = re.sub(r"[^A-Za-z0-9._-]+", "-", str(meta.get("name") or "")).strip("-.")[:60] or sid
        return f"{base}.{ext}"

    def export_json(self, req, sid):
        st = self._load(req, sid)
        data = (json.dumps(st, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        return Response(data, 200, "application/json; charset=utf-8",
                        [("Content-Disposition", f'attachment; filename="{self._filename(sid, st, "json")}"')])

    @staticmethod
    def _finding_sheets(base, fnd, lang):
        """The Excel sheets: the engine's assumptions, then each top action and each kept risk in three short lines
        (To strengthen / Based on / Next step), closing with one encouraging line."""
        lbl = [views_quick.tr(lang, k) for k in findings.LABEL_KEYS]
        head = ["Rank" if lang == "en" else "Rang", "", "Text" if lang == "en" else "Texte"]
        acts = [head] + [[i, lbl[k], f[key]] for i, f in enumerate(fnd["actions"], 1)
                         for k, key in enumerate(("gap", "evidence", "fix"))]
        risks = [["Risk" if lang == "en" else "Risque", "", head[2]]] + [
            [f'{f["id"]} {f["title"]}', lbl[k], f[key]] for f in fnd["risks"]
            for k, key in enumerate(("gap", "evidence", "fix"))]
        if fnd["closing"]:
            (risks if len(risks) > 1 else acts).append(["", "", fnd["closing"]])
        return [base[0], ("Top actions" if lang == "en" else "Actions", acts),
                (views_quick.tr(lang, "risks_h"), risks)]

    def export_xlsx(self, req, sid):
        st = self._load(req, sid)
        chk = engine.check(st)
        if chk["errors"] or not chk["cal"]:
            raise HTTPError(409, "the engine exports only a study without errors; fix the errors listed in the checks")
        if not engine.have_xlsx():
            raise HTTPError(501, "the Excel export needs openpyxl, which is not installed here; the JSON export works")
        notice = sheets = lang = None
        cal = chk["cal"]
        if isinstance(st.get("quick"), dict):  # a quick-path study: honesty header, assumptions and top actions
            try:
                cat = self.quick_catalogue()
                lang = self._lang(req, st["quick"])  # the quick workbook follows the page language
                quick = dict(st["quick"], lang=lang)
                if lang != st["quick"].get("lang") and not self._edited_in_expert_mode(st, st["quick"], chk["cal"]):
                    st = engine.quick_build(quick, chk["cal"], cat)  # same answers, texts in the page language
                notice = engine.quick_notice(quick, chk["cal"], cat)
                rows = engine.quick_compute(quick, chk["cal"], cat)
                fnd = findings.build(quick, cat, chk["cal"], rows, engine.quick_actions(quick, chk["cal"], cat, 5), lang)
                sheets = self._finding_sheets(engine.quick_sheets(quick, chk["cal"], cat), fnd, lang)
                if fnd["closing"]:
                    notice = notice + [fnd["closing"]]  # the summary at the top of the workbook closes on it
                cal = labels.display_cal(chk["cal"], lang)  # plain level and severity names, same numbers
            except engine.QuickError:
                notice = sheets = lang = None
        data = engine.to_xlsx_bytes(st, cal, self.tmp_dir, notice, sheets, lang)
        return Response(data, 200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        [("Content-Disposition", f'attachment; filename="{self._filename(sid, st, "xlsx")}"')])
