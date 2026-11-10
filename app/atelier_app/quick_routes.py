"""Quick-path handlers: the home page and the four screens. Levels, confidence and the study come from the engine."""
from . import calibrations, documents, engine, views_quick
from .storage import NotFound
from .web import HTTPError, Response, redirect

LANGS = ("en", "fr")
LANG_COOKIE = "atelier_lang"
SID = r"(s-[0-9]{8}-[0-9a-f]{8})"
NEXT_STEP = {"about": "risks", "risks": "now", "now": "results", "results": "results"}
ORDER = ("about", "risks", "now", "results")
QUICK_FORMAT = {"format": "atelier-quick", "version": "0.1"}


def _lines(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and line not in out:
            out.append(line)
    return out


class QuickRoutes:
    catalogue_cache = None

    def add_quick_routes(self, router):
        router.add("GET", r"/", self.home)
        router.add("GET", r"/quick/new", self.quick_new_form)
        router.add("POST", r"/quick/new", self.quick_new)
        router.add("GET", rf"/quick/{SID}/about", self.quick_about)
        router.add("POST", rf"/quick/{SID}/about", self.quick_about_save)
        router.add("GET", rf"/quick/{SID}/risks", self.quick_risks)
        router.add("POST", rf"/quick/{SID}/risks", self.quick_risks_save)
        router.add("GET", rf"/quick/{SID}/now", self.quick_now)
        router.add("POST", rf"/quick/{SID}/now", self.quick_now_save)
        router.add("GET", rf"/quick/{SID}/results", self.quick_results)

    # ---------- shared ----------

    def quick_catalogue(self):
        if QuickRoutes.catalogue_cache is None:
            try:
                QuickRoutes.catalogue_cache = engine.quick_catalogue()
            except engine.QuickError as e:
                raise HTTPError(500, f"the risk catalogue cannot be read: {e}")
        return QuickRoutes.catalogue_cache

    @staticmethod
    def _lang(req, quick=None):
        for cand in (req.arg("lang"), req.field("lang")):
            if cand in LANGS:
                return cand
        c = req.cookies.get(LANG_COOKIE)
        if c in LANGS:
            return c
        if quick and quick.get("lang") in LANGS:
            return quick["lang"]
        return "en"

    @staticmethod
    def _remember(req, resp, lang):
        if req.arg("lang") in LANGS:
            resp.header("Set-Cookie", f"{LANG_COOKIE}={lang}; Path=/; SameSite=Strict; Max-Age=31536000")
        return resp

    def _quick_study(self, req, sid):
        st = self._load(req, sid)
        quick = st.get("quick")
        if not isinstance(quick, dict):
            raise HTTPError(404, "this study was not made with the quick path")
        return st, quick

    def _cal(self, st):
        cal_id = calibrations.of_study(st)
        try:
            return calibrations.load(cal_id)
        except (calibrations.CalibrationError, ValueError, OSError) as e:
            raise HTTPError(409, f"the calibration of this study cannot be loaded: {e}")

    def _quick_build(self, quick, cal):
        try:
            return engine.quick_build(quick, cal, self.quick_catalogue())
        except engine.QuickError as e:
            raise HTTPError(400, str(e))

    def _edited_in_expert_mode(self, st, quick, cal):
        """True when the stored study differs from what the quick answers build (it was changed in expert mode)."""
        try:
            fresh = engine.quick_build(quick, cal, self.quick_catalogue())
        except engine.QuickError:
            return False
        return any(st.get(k) != fresh.get(k) for k in engine.COLLECTIONS)

    def _save(self, req, sid, old, quick, cal):
        """Rebuild the study from the quick answers and save it (the store keeps the previous file as .bak)."""
        st = self._quick_build(quick, cal)
        if isinstance((old or {}).get("study"), dict) and old["study"].get("confidential") is True:
            st["study"]["confidential"] = True
        self.store_for(req.session).save(sid, st)
        return st

    def _advance(self, quick, done):
        cur = ORDER.index(quick.get("step") or "about")
        quick["step"] = ORDER[max(cur, ORDER.index(NEXT_STEP[done]))]

    def _sync_risks(self, quick):
        """Risks that apply to the profile: keep earlier decisions; a new one is ticked (kept) when it is in the short
        list and unticked (discard, shown under "More risks you can add") otherwise; drop catalogue risks that no
        longer apply; keep the person's own."""
        cat = self.quick_catalogue()
        old = {e["id"]: e for e in quick.get("risks") or []}
        short = set(engine.quick_shortlist(quick["profile"], cat))
        out = [old.get(rid) or {"id": rid, "decision": "keep" if rid in short else "discard"}
               for rid in engine.quick_suggest(quick["profile"], cat)]
        out += [e for e in old.values() if e.get("custom")]
        quick["risks"] = out

    # ---------- home ----------

    def home(self, req):
        lang = self._lang(req)
        recent = []
        for sid, st, mtime in self.store_for(req.session).list():
            qk = st.get("quick") if isinstance(st, dict) else None
            if isinstance(qk, dict):
                meta = st.get("study") if isinstance(st.get("study"), dict) else {}
                recent.append((sid, meta.get("name") or "(no name)", mtime, qk.get("step") if qk.get("step") in ORDER else "about"))
        resp = Response(views_quick.home(req.session, lang, recent[:6], req.arg("f")))
        return self._remember(req, resp, lang)

    # ---------- screen 1: about you ----------

    def quick_new_form(self, req):
        lang = self._lang(req)
        resp = Response(views_quick.about(req.session, None, lang, self.quick_catalogue(), {}, doc_open=req.arg("doc") == "1"))
        return self._remember(req, resp, lang)

    def _parse_about(self, req, cat, doc_state=None):
        """(profile, errors) from the About-you form. Errors map a field to a message key already translated."""
        lang = self._lang(req)
        errors = {}
        name = req.field("name").strip()
        if not name or len(name) > 200:
            errors["name"] = views_quick.tr(lang, "err_name")
        activity = req.field("activity").strip()[:2000]
        values = _lines(req.field("values"))
        if len(values) > engine.MAX_VALUES or any(len(v) > 200 for v in values):
            errors["values"] = views_quick.tr(lang, "err_values")
        tool_ids = {t["id"] for t in cat["tools"]}
        tools = [t for t in dict.fromkeys(req.fields("tools")) if t in tool_ids]

        def plain(name_, keys):
            v = req.field(name_)
            if v == "dont_know":
                return {"answer": "dont_know", "dont_know": True}
            return {"answer": v} if v in keys else {}
        kind = req.field("doc_kind")
        prof = {"name": name,
                "activity": {"value": activity, "dont_know": bool(req.field("activity_dk"))},
                "values": {"value": values[:engine.MAX_VALUES] if "values" not in errors else values, "dont_know": bool(req.field("values_dk"))},
                "tools": {"value": tools, "dont_know": bool(req.field("tools_dk"))},
                "downtime": plain("downtime", engine.DOWNTIME_KEYS),
                "sensitivity": plain("sensitivity", engine.SENSITIVITY_KEYS),
                "doc_kind": kind if kind in engine.DOCUMENT_KINDS else "other"}
        return prof, errors

    def _apply_document(self, sid, prof, req, quick):
        """Store an uploaded document (flagged, not read). Returns an error text or None; updates prof["document"]."""
        lang = self._lang(req)
        prev = (quick or {}).get("profile", {}).get("document") or {}
        doc = dict(prev) if prev.get("provided") else {"provided": False}
        f = req.files.get("document")
        if f and f[1]:
            try:
                meta = self.docs.add(sid, f[0], f[1])
            except documents.DocumentError as e:
                prof["document"] = doc
                return views_quick.tr(lang, "err_doc", why=str(e))
            if prev.get("doc_id"):
                try:
                    self.docs.delete(sid, prev["doc_id"])
                except NotFound:
                    pass
            doc = {"provided": True, "doc_id": meta["id"], "filename": meta["name"], "kind": prof["doc_kind"],
                   "status": "stored, not read"}
        elif doc.get("provided"):
            doc["kind"] = prof["doc_kind"]
        prof["document"] = doc
        return None

    def _about_response(self, req, sid, lang, prof, errors, status, edited=False):
        doc = (prof.get("document") or {})
        return Response(views_quick.about(req.session, sid, lang, self.quick_catalogue(), prof, errors, edited=edited, doc=doc), status)

    def quick_new(self, req):
        lang = self._lang(req)
        cat = self.quick_catalogue()
        prof, errors = self._parse_about(req, cat)
        if errors:
            return Response(views_quick.about(req.session, None, lang, cat, prof, errors), 400)
        cal = calibrations.load(calibrations.DEFAULT)
        quick = dict(QUICK_FORMAT, lang=lang, step="risks", profile=dict(prof), risks=[])
        quick["profile"].pop("doc_kind")
        quick["profile"]["document"] = {"provided": False}
        self._sync_risks(quick)
        sid = self.store_for(req.session).create(self._quick_build(quick, cal))
        f = req.files.get("document")
        if f and f[1]:
            err = self._apply_document(sid, prof, req, quick)
            if err:
                quick["step"] = "about"
                self._save(req, sid, None, quick, cal)
                return self._about_response(req, sid, lang, prof, {"doc": err}, 400)
            quick["profile"]["document"] = prof["document"]
            self._save(req, sid, None, quick, cal)
        return redirect(f"/quick/{sid}/risks")

    def quick_about(self, req, sid):
        st, quick = self._quick_study(req, sid)
        cal = self._cal(st)
        lang = self._lang(req, quick)
        cat = self.quick_catalogue()
        prof = dict(quick.get("profile") or {})
        resp = Response(views_quick.about(req.session, sid, lang, cat, prof, doc=prof.get("document") or {},
                                          edited=self._edited_in_expert_mode(st, quick, cal), flash=req.arg("f")))
        return self._remember(req, resp, lang)

    def quick_about_save(self, req, sid):
        with self.edit_lock:
            st, quick = self._quick_study(req, sid)
            cal = self._cal(st)
            lang = self._lang(req, quick)
            cat = self.quick_catalogue()
            prof, errors = self._parse_about(req, cat)
            if errors:
                prof["document"] = (quick.get("profile") or {}).get("document") or {}
                return self._about_response(req, sid, lang, prof, errors, 400,
                                            edited=self._edited_in_expert_mode(st, quick, cal))
            err = self._apply_document(sid, prof, req, quick)
            kind = prof.pop("doc_kind")
            quick["lang"] = lang
            quick["profile"] = prof
            self._sync_risks(quick)
            self._advance(quick, "about")
            self._save(req, sid, st, quick, cal)
            if err:
                prof["doc_kind"] = kind
                return self._about_response(req, sid, lang, prof, {"doc": err}, 400)
        return redirect(f"/quick/{sid}/risks")

    # ---------- screen 2: risks ----------

    def quick_risks(self, req, sid):
        st, quick = self._quick_study(req, sid)
        cal = self._cal(st)
        lang = self._lang(req, quick)
        cat = self.quick_catalogue()
        resp = Response(views_quick.risks(req.session, sid, lang, cat, quick, edited=self._edited_in_expert_mode(st, quick, cal),
                                          flash=req.arg("f"), shortlist=engine.quick_shortlist(quick["profile"], cat)))
        return self._remember(req, resp, lang)

    def quick_risks_save(self, req, sid):
        with self.edit_lock:
            st, quick = self._quick_study(req, sid)
            cal = self._cal(st)
            lang = self._lang(req, quick)
            cat = self.quick_catalogue()
            by_id = {r["id"]: r for r in cat["risks"]}
            kept = set(req.fields("keep"))
            errors, state = {}, {"keep": {}, "reasons": {}, "new": []}
            for e in quick["risks"]:
                rid = e["id"]
                state["keep"][rid] = rid in kept
                state["reasons"][rid] = req.field(f"reason_{rid}").strip()[:500]
                if rid not in kept and by_id.get(rid, {}).get("always_assessed") and not state["reasons"][rid]:
                    errors[rid] = views_quick.tr(lang, "err_reason")
            for i in (1, 2, 3):
                title = req.field(f"new_title_{i}").strip()
                fam = req.field(f"new_family_{i}")
                crit = [c for c in req.fields(f"new_crit_{i}") if c in ("confidentiality", "integrity", "availability")]
                state["new"].append({"title": title, "family": fam if fam in ("deliberate", "accidental") else "accidental", "criteria": crit})
                if len(title) > 200:
                    errors["new"] = views_quick.tr(lang, "err_values")
            if errors:
                return Response(views_quick.risks(req.session, sid, lang, cat, quick, state, errors,
                                                  edited=self._edited_in_expert_mode(st, quick, cal),
                                                  shortlist=engine.quick_shortlist(quick["profile"], cat)), 400)
            for e in quick["risks"]:
                e["decision"] = "keep" if e["id"] in kept else "discard"
                if state["reasons"][e["id"]]:
                    e["reason"] = state["reasons"][e["id"]]
                else:
                    e.pop("reason", None)
            used = {e["id"] for e in quick["risks"]}
            n = 1
            for row in state["new"]:
                if not row["title"]:
                    continue
                while f"C{n}" in used:
                    n += 1
                rid = f"C{n}"
                used.add(rid)
                quick["risks"].append({"id": rid, "decision": "keep", "custom": {
                    "title": row["title"], "family": row["family"],
                    "criteria": row["criteria"] or ["confidentiality", "integrity", "availability"]}})
            quick["lang"] = lang
            self._advance(quick, "risks")
            self._save(req, sid, st, quick, cal)
        return redirect(f"/quick/{sid}/now")

    # ---------- screen 3: now and after ----------

    def _rows(self, quick, cal):
        try:
            return engine.quick_compute(quick, cal, self.quick_catalogue())
        except engine.QuickError as e:
            raise HTTPError(400, str(e))

    def quick_now(self, req, sid):
        st, quick = self._quick_study(req, sid)
        cal = self._cal(st)
        lang = self._lang(req, quick)
        resp = Response(views_quick.now(req.session, sid, lang, self.quick_catalogue(), quick, cal, self._rows(quick, cal),
                                        edited=self._edited_in_expert_mode(st, quick, cal), flash=req.arg("f")))
        return self._remember(req, resp, lang)

    def quick_now_save(self, req, sid):
        with self.edit_lock:
            st, quick = self._quick_study(req, sid)
            cal = self._cal(st)
            lang = self._lang(req, quick)
            cat = self.quick_catalogue()
            rows = self._rows(quick, cal)
            entries = {e["id"]: e for e in quick["risks"]}
            errors = {}
            state = {"sev": {}, "sevreason": {}, "lik": {}, "in": {}, "extra": {}}
            parsed = {}
            for r in rows:
                rid = r["id"]
                sev_raw = req.field(f"sev_{rid}")
                reason = req.field(f"sevreason_{rid}").strip()[:500]
                sev = int(sev_raw) if sev_raw in ("1", "2", "3", "4") else None
                if sev is not None and sev == r["severity_proposed"]:
                    sev = None
                lik = req.field(f"lik_{rid}")
                if lik not in engine.LIKELIHOOD_KEYS[r["def"]["family"]] and lik != "dont_know":
                    lik = ""
                order = [m["id"] for m in r["def"]["measures"]]
                in_place = [m for m in order if req.field(f"m_{rid}_{m}") == "in"]
                extra = [m for m in order if req.field(f"m_{rid}_{m}") == "extra"]
                state["sev"][rid], state["sevreason"][rid], state["lik"][rid] = sev, reason, lik
                state["in"][rid], state["extra"][rid] = in_place, extra
                parsed[rid] = (sev, reason, lik, in_place, extra)
                if sev is not None and not reason:
                    errors[rid] = views_quick.tr(lang, "err_sev_reason")
            if errors:
                return Response(views_quick.now(req.session, sid, lang, cat, quick, cal, rows, state, errors,
                                                edited=self._edited_in_expert_mode(st, quick, cal)), 400)
            for rid, (sev, reason, lik, in_place, extra) in parsed.items():
                e = entries[rid]
                if sev is None:
                    e.pop("severity", None)
                else:
                    e["severity"] = {"value": sev, "reason": reason}
                if lik:
                    e["likelihood"] = {"answer": lik}
                else:
                    e.pop("likelihood", None)
                e["in_place"], e["extra"], e["assessed"] = in_place, extra, True
            quick["lang"] = lang
            go = req.field("go")
            if go == "next":
                self._advance(quick, "now")
            self._save(req, sid, st, quick, cal)
        return redirect(f"/quick/{sid}/results" if go == "next" else f"/quick/{sid}/now?f=saved")

    # ---------- screen 4: results ----------

    def quick_results(self, req, sid):
        st, quick = self._quick_study(req, sid)
        cal = self._cal(st)
        lang = self._lang(req, quick)
        cat = self.quick_catalogue()
        rows = self._rows(quick, cal)
        built = self._quick_build(quick, cal)
        chk = engine.check(built)
        if chk["errors"]:
            raise HTTPError(409, "the engine refuses the study built from these answers: " + "; ".join(chk["errors"][:3]))
        reg_rows, _ = engine.register(built, cal)
        resp = Response(views_quick.results(
            req.session, sid, lang, cat, quick, cal, rows, reg_rows, engine.quick_facts(quick, cal, cat),
            engine.quick_actions(quick, cal, cat, 5), engine.quick_assumptions(quick, cal, cat),
            edited=self._edited_in_expert_mode(st, quick, cal), can_xlsx=engine.have_xlsx()))
        return self._remember(req, resp, lang)
