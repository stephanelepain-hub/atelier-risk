"""Expert mode: the workshop screens (study overview, W1 to W5, register, locate, severities, rename, duplicate).

The routes always answer; the Expert switch in the page header only decides whether the quick screens link to them
(see expert.py). Levels, severities and checks are the engine's.
"""
import copy
import re
import urllib.parse

from . import editors, engine, views, views_ws
from .web import HTTPError, Response, redirect

FormError = editors.FormError  # carries the form field it is about
SID = r"(s-[0-9]{8}-[0-9a-f]{8})"
W1SLUG = r"(bv|sa|fe|bl)"
W1_TEXT = {"business_values": ["label", "nature", "owner"], "supporting_assets": ["label"],
           "feared_events": ["business_value", "label", "criterion", "severity"],
           "baseline": ["reference", "status", "gap"]}


class EngineRefused(Exception):
    """The engine refused a value of a W2-W5 form: (message above the form, {field: message})."""

    def __init__(self, message, errs):
        super().__init__(message)
        self.message, self.errs = message, errs


class ExpertRoutes:
    def add_expert_routes(self, r):
        r.add("GET", rf"/s/{SID}", self.overview)
        r.add("POST", rf"/s/{SID}/rename", self.rename)
        r.add("POST", rf"/s/{SID}/duplicate", self.duplicate)
        r.add("GET", rf"/s/{SID}/w1", self.w1)
        r.add("GET", rf"/s/{SID}/w([2-5])", self.workshop)
        r.add("POST", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/add", self.ws_add)
        r.add("GET", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/([^/]+)", self.ws_edit_form)
        r.add("POST", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/([^/]+)/delete", self.ws_delete)
        r.add("POST", rf"/s/{SID}/w([2-5])/{editors.SLUG_RE}/([^/]+)", self.ws_save)
        r.add("POST", rf"/s/{SID}/severities", self.take_severities)
        r.add("GET", rf"/s/{SID}/el/([^/]+)", self.locate)
        r.add("GET", rf"/s/{SID}/register", self.register)
        r.add("POST", rf"/s/{SID}/w1/{W1SLUG}/add", self.w1_add)
        r.add("GET", rf"/s/{SID}/w1/{W1SLUG}/([^/]+)", self.w1_edit_form)
        r.add("POST", rf"/s/{SID}/w1/{W1SLUG}/([^/]+)/delete", self.w1_delete)
        r.add("POST", rf"/s/{SID}/w1/{W1SLUG}/([^/]+)", self.w1_save)

    # ---------- one study (expert view) ----------

    def overview(self, req, sid):
        st = self._load(req, sid)
        return Response(views.overview(sid, st, engine.check(st), self.store_for(req.session).mtime(sid), req.session,
                                       req.arg("f")))

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
        """Copy a study (the copy gets its own id and " (copy)" after its name)."""
        st = self._load(req, sid)
        meta = st.get("study") if isinstance(st.get("study"), dict) else {}
        meta["name"] = (meta.get("name") or "study") + " (copy)"
        st["study"] = meta
        self.store_for(req.session).create(st)
        return redirect("/studies?f=duplicated")

    def _w1_page(self, req, sid, st, chk=None, flash="", form_error=None, status=200):
        chk = chk or engine.check(st)
        return Response(views.w1_page(sid, st, chk, req.session, flash, form_error, req.arg("hl") or None), status)

    def w1(self, req, sid):
        return self._w1_page(req, sid, self._load(req, sid), flash=req.arg("f"))

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
