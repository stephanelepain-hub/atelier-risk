"""Quick-path handlers: the home page and the four screens. Levels, confidence and the study come from the engine."""
import copy
import json

from . import calibrations, engine, findings, views_public, views_quick
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
        if getattr(self, "public", False):
            router.add("POST", r"/quick/open", self.quick_open)

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
        # A copy in the current shape: answers saved per risk become answers for the whole business. The stored study
        # keeps its old shape until the next save rebuilds it.
        return st, engine.quick_migrate(copy.deepcopy(quick))

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
        keys = list(engine.COLLECTIONS)
        if not isinstance((st.get("quick") or {}).get("measures"), dict):
            # saved before the measures were answered once: its measures, baseline and risk rows were built per risk
            # and differ from a fresh build without any expert edit, so only the other collections are compared
            keys = [k for k in keys if k not in ("baseline", "measures", "risks")]
        return any(st.get(k) != fresh.get(k) for k in keys)

    def _save(self, req, sid, old, quick, cal):
        """Rebuild the study from the quick answers and save it (the store keeps the previous file as .bak)."""
        st = self._quick_build(quick, cal)
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
        if self.store_for(req.session).full():   # the study limit of a public workspace: say so before the form is filled in
            return Response(views_public.limit_page(lang, req.session), 409)
        resp = Response(views_quick.about(req.session, None, lang, self.quick_catalogue(), {}))
        return self._remember(req, resp, lang)

    def _parse_about(self, req, cat):
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
        prof = {"name": name,
                "activity": {"value": activity, "dont_know": bool(req.field("activity_dk"))},
                "values": {"value": values[:engine.MAX_VALUES] if "values" not in errors else values, "dont_know": bool(req.field("values_dk"))},
                "tools": {"value": tools, "dont_know": bool(req.field("tools_dk"))},
                "downtime": plain("downtime", engine.DOWNTIME_KEYS),
                "sensitivity": plain("sensitivity", engine.SENSITIVITY_KEYS)}
        return prof, errors

    def quick_new(self, req):
        lang = self._lang(req)
        cat = self.quick_catalogue()
        prof, errors = self._parse_about(req, cat)
        if errors:
            return Response(views_quick.about(req.session, None, lang, cat, prof, errors), 400)
        cal = calibrations.load(calibrations.DEFAULT)
        quick = dict(QUICK_FORMAT, lang=lang, step="risks", profile=dict(prof), risks=[])
        self._sync_risks(quick)
        sid = self.store_for(req.session).create(self._quick_build(quick, cal))
        return redirect(f"/quick/{sid}/risks")

    def quick_open(self, req):
        """Public mode: continue from a study file saved with "Download the study file". The file is read by the page's
        script and posted as the form field `study`. Only a valid quick-path study is taken in: its answers are checked and
        the study is built again from them, so the stored copy has the engine's own shape. It gets a new id."""
        lang = self._lang(req)
        raw = req.field("study")
        if len(raw.encode("utf-8")) > views_public.OPEN_MAX:
            return Response(views_public.open_error_page(lang, "open_big", req.session), 413)
        saved = self._saved_quick(raw)
        if saved is None:
            return Response(views_public.open_error_page(lang, "open_bad", req.session), 400)
        cal_id, quick = saved
        try:
            built = engine.quick_build(quick, calibrations.load(cal_id), self.quick_catalogue())
            ok = not engine.check(built)["errors"]
        except Exception:   # a file from outside: any shape that the engine cannot use is simply not accepted
            ok = False
        if not ok:
            return Response(views_public.open_error_page(lang, "open_bad", req.session), 400)
        sid = self.store_for(req.session).create(built)   # StudyLimit is answered by App.handle
        step = quick.get("step")
        return redirect(f"/quick/{sid}/{step if step in ORDER else 'about'}")

    @staticmethod
    def _saved_quick(raw):
        """(calibration id, quick answers in the current shape) from the text of a saved study file, or None when it
        is not a study made with the quick path."""
        try:
            st = json.loads(raw)
        except (ValueError, RecursionError):
            return None
        if not isinstance(st, dict) or st.get("format") != "atelier-study":
            return None
        quick = st.get("quick")
        if not isinstance(quick, dict) or quick.get("format") != QUICK_FORMAT["format"]:
            return None
        if not isinstance(quick.get("profile"), dict) or not isinstance(quick.get("risks"), list):
            return None
        cal_id = calibrations.of_study(st)
        if not calibrations.exists(cal_id):
            return None
        try:
            return cal_id, engine.quick_migrate(copy.deepcopy(quick))
        except Exception:
            return None

    def quick_about(self, req, sid):
        st, quick = self._quick_study(req, sid)
        cal = self._cal(st)
        lang = self._lang(req, quick)
        cat = self.quick_catalogue()
        prof = dict(quick.get("profile") or {})
        resp = Response(views_quick.about(req.session, sid, lang, cat, prof, edited=self._edited_in_expert_mode(st, quick, cal),
                                           flash=req.arg("f")))
        return self._remember(req, resp, lang)

    def quick_about_save(self, req, sid):
        with self.edit_lock:
            st, quick = self._quick_study(req, sid)
            cal = self._cal(st)
            lang = self._lang(req, quick)
            cat = self.quick_catalogue()
            prof, errors = self._parse_about(req, cat)
            if errors:
                return Response(views_quick.about(req.session, sid, lang, cat, prof, errors,
                                                  edited=self._edited_in_expert_mode(st, quick, cal)), 400)
            quick["lang"] = lang
            quick["profile"] = prof
            self._sync_risks(quick)
            self._advance(quick, "about")
            self._save(req, sid, st, quick, cal)
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
            listed = [m["id"] for m in engine.quick_measure_list(quick, cat)]    # each measure once, for the whole business
            answers = {m: req.field(f"m_{m}") for m in listed}
            answers = {m: (a if a in ("in", "extra") else "") for m, a in answers.items()}
            state = {"sev": {}, "sevreason": {}, "lik": {}, "m": {}}
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
                state["sev"][rid], state["sevreason"][rid], state["lik"][rid] = sev, reason, lik
                parsed[rid] = (sev, reason, lik)
                if sev is not None and not reason:
                    errors[rid] = views_quick.tr(lang, "err_sev_reason")
            state["m"] = answers
            if errors:
                return Response(views_quick.now(req.session, sid, lang, cat, quick, cal, rows, state, errors,
                                                edited=self._edited_in_expert_mode(st, quick, cal)), 400)
            for rid, (sev, reason, lik) in parsed.items():
                e = entries[rid]
                if sev is None:
                    e.pop("severity", None)
                else:
                    e["severity"] = {"value": sev, "reason": reason}
                if lik:
                    e["likelihood"] = {"answer": lik}
                else:
                    e.pop("likelihood", None)
            old = engine.quick_org_measures(quick)       # answers for measures not shown now (a risk set aside) stay
            quick["measures"] = {"in_place": [m for m in old["in_place"] if m not in answers] + [m for m in listed if answers[m] == "in"],
                                 "extra": [m for m in old["extra"] if m not in answers] + [m for m in listed if answers[m] == "extra"],
                                 "assessed": True}
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
            findings.build(quick, cat, cal, rows, engine.quick_actions(quick, cal, cat, 5), lang),
            edited=self._edited_in_expert_mode(st, quick, cal), can_xlsx=engine.have_xlsx()))
        return self._remember(req, resp, lang)
