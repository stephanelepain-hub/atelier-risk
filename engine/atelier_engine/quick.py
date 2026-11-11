"""Quick path: a short list of known risks, rated now and after extra measures, turned into a normal study.

The quick path is the "known risks list" shape of the method. A person gives a few
answers, ticks the risks of a public catalogue that apply, rates each one in plain words, and ticks measures. This
module turns those answers (the "quick answers", documented in docs/quick-path.md) into an `atelier-study`
that `study.validate` accepts and `study.register` can list, with a level before and after.

Rules here that the ANSSI guide does not print are "Atelier rules, beyond the guide" (docs/rules.md, rule 5):
  - the proposed severity (typical value of the catalogue blended with the person's answers),
  - the likelihood from a plain answer, and from "has it happened in the last 3 years?" for accidental risks,
  - the likelihood after extra measures,
  - the confidence figure and the ranking of actions.
Severity and likelihood are levels 1..4 of the calibration. Levels are computed here, never by a UI or a model.
"""
import copy
import json
import pathlib

from . import calibration as cal_mod

CATALOGUE_PATH = pathlib.Path(__file__).resolve().parents[2] / "catalogues" / "quick-risks.json"
SOURCES = ("document", "answer", "catalogue", "default")
SOURCE_WEIGHT = {"document": 1.0, "answer": 0.75, "catalogue": 0.5, "default": 0.0}
NO_DOCUMENT_CEILING = 75
FAMILIES = ("deliberate", "accidental")
AUDIENCES = ("all", "sensitive")
SHORTLIST_LIMIT = 10
HIGHEST_SENSITIVITY = "critical"        # "Secrets, health or legal data" on the About-you screen
SENSITIVE_TOOL = "industrial"
CRITERIA = ("confidentiality", "integrity", "availability")
MAX_VALUES = 5

# The honesty statement. This is the only place the text is written; pages and exports read these constants.
HONESTY = {
    "en": "This analysis reflects only the answers you gave and the documents you provided. It is only as good as "
          "that information. Without source documents (architecture, business impact, security baseline) treat it "
          "as a first view.",
    "fr": "Cette analyse reflète uniquement les réponses que vous avez données et les documents que vous avez "
          "fournis. Sa qualité dépend entièrement de ces informations. Sans documents sources (architecture, "
          "impacts métier, socle de sécurité), considérez-la comme une première vue.",
}

# Plain answers and the level the engine gives them (Atelier rule, beyond the guide).
DOWNTIME = {"hours": 4, "day": 3, "days": 2, "week": 1}          # how soon a stop of the main tools really hurts
SENSITIVITY = {"public": 1, "internal": 2, "confidential": 3, "critical": 4}
LIKELIHOOD_DELIBERATE = {"unlikely": 1, "possible": 2, "likely": 3, "very_likely": 4}
LIKELIHOOD_ACCIDENTAL = {"never": 1, "once": 2, "sometimes": 3, "often": 4}
UNKNOWN_LEVEL = 3          # severity input when the person does not know (cautious)
CUSTOM_LIKELIHOOD = 2      # likelihood of a risk added by the person, when they do not say
DOCUMENT_KINDS = ("architecture", "business-impact", "security-baseline", "other")
MISSING_DOCUMENTS = ("architecture", "business-impact", "security-baseline")

SEVERITY_WORDS = {
    "en": {1: "Minor: a nuisance", 2: "Significant: it hurts for a few days", 3: "Serious: lasting damage or a high cost",
           4: "Critical: it threatens the organisation"},
    "fr": {1: "Mineure : une gêne", 2: "Significative : cela fait mal pendant quelques jours",
           3: "Grave : dégâts durables ou coût élevé", 4: "Critique : cela menace l'organisation"},
}


class QuickError(ValueError):
    """The quick answers or the catalogue are malformed."""


# ---------------------------------------------------------------- catalogue

def load_catalogue(path=None):
    """The public risk catalogue (catalogues/quick-risks.json, or another file with the same shape), checked."""
    p = pathlib.Path(path) if path else CATALOGUE_PATH
    try:
        cat = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise QuickError(f"cannot read catalogue {p}: {e}") from e
    check_catalogue(cat)
    return cat


def check_catalogue(cat):
    """Structure check. Raises QuickError listing every problem found."""
    errs = []
    if not isinstance(cat, dict) or cat.get("format") != "atelier-quick-catalogue":
        raise QuickError("catalogue: format must be 'atelier-quick-catalogue'")
    packs = {p.get("id") for p in cat.get("packs") or []}
    if "all" not in packs:
        errs.append("packs: the pack 'all' is required")
    origins = {o.get("id") for o in cat.get("origins") or []}
    objectives = {o.get("id") for o in cat.get("objectives") or []}
    for t in cat.get("tools") or []:
        if not t.get("id") or not (t.get("en") and t.get("fr")):
            errs.append(f"tool {t.get('id')}: id, en and fr are required")
        for p in t.get("packs") or []:
            if p not in packs:
                errs.append(f"tool {t.get('id')}: unknown pack {p}")
    seen, measure_text = set(), {}
    for r in cat.get("risks") or []:
        rid = r.get("id")
        if not rid or rid in seen:
            errs.append(f"risk {rid}: id missing or duplicated")
        seen.add(rid)
        if r.get("family") not in FAMILIES:
            errs.append(f"risk {rid}: family must be one of {FAMILIES}")
        for k in ("title", "description"):
            if not all((r.get(k) or {}).get(lang) for lang in ("en", "fr")):
                errs.append(f"risk {rid}: {k} needs en and fr text")
        if not r.get("criteria") or any(c not in CRITERIA for c in r["criteria"]):
            errs.append(f"risk {rid}: criteria must be a non-empty subset of {CRITERIA}")
        if not r.get("packs") or any(p not in packs for p in r["packs"]):
            errs.append(f"risk {rid}: packs must be a non-empty list of known packs")
        if not isinstance(r.get("always_assessed"), bool):
            errs.append(f"risk {rid}: always_assessed must be true or false")
        if r.get("audience", "all") not in AUDIENCES:
            errs.append(f"risk {rid}: audience must be one of {AUDIENCES}")
        elif r.get("audience") == "sensitive" and r.get("always_assessed") is True:
            errs.append(f"risk {rid}: an always-assessed risk cannot have the audience 'sensitive'")
        for k in ("typical_severity", "typical_likelihood"):
            if not cal_mod_scale(r.get(k)):
                errs.append(f"risk {rid}: {k} must be 1 to 4")
        if r.get("family") == "deliberate":
            if r.get("origin") not in origins or r.get("objective") not in objectives:
                errs.append(f"risk {rid}: deliberate risks need a known origin and objective")
        ms = r.get("measures") or []
        if not 3 <= len(ms) <= 6:
            errs.append(f"risk {rid}: 3 to 6 measures are required, found {len(ms)}")
        for m in ms:
            if not (m.get("id") and m.get("en") and m.get("fr")):
                errs.append(f"risk {rid}: a measure needs id, en and fr")
            elif measure_text.setdefault(m["id"], (m["en"], m["fr"])) != (m["en"], m["fr"]):
                errs.append(f"measure {m['id']}: different texts in different risks")
    if errs:
        raise QuickError("catalogue: " + "; ".join(errs))
    return True


def cal_mod_scale(x):
    return isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 4


def _by_id(cat):
    return {r["id"]: r for r in cat["risks"]}


# ---------------------------------------------------------------- answers

def _slot(profile, key):
    s = (profile or {}).get(key)
    return s if isinstance(s, dict) else {}


def slot_source(slot):
    """Source of one answer slot: `document` if it carries a document reference, `answer` if the person gave a
    value, else `default` (skipped or "I don't know")."""
    if not slot:
        return "default"
    if slot.get("source") in SOURCES:
        return slot["source"]
    if slot.get("dont_know"):
        return "default"
    value = slot.get("value", slot.get("answer"))
    if value is None or value == "" or value == [] or value == "dont_know":
        return "default"
    return "answer"


def _profile_known(profile):
    return {k: slot_source(_slot(profile, k)) != "default" for k in ("activity", "values", "tools", "downtime", "sensitivity")}


def _profile(quick):
    p = quick.get("profile")
    return p if isinstance(p, dict) else {}


def _tools(profile, cat):
    known = {t["id"] for t in cat.get("tools") or []}
    return [t for t in (_slot(profile, "tools").get("value") or []) if t in known]


def packs_for(profile, catalogue=None):
    """Packs implied by the profile: `all`, plus the packs of the tools ticked. With no tool answer
    (skipped or "I don't know") the default is `all` + `office-it`."""
    cat = catalogue or load_catalogue()
    if isinstance(profile, dict) and "profile" in profile and isinstance(profile["profile"], dict):
        profile = profile["profile"]
    packs = ["all"]
    chosen = _tools(profile, cat)
    if slot_source(_slot(profile, "tools")) == "default" or not chosen:
        packs.append("office-it")
    for t in cat.get("tools") or []:
        if t["id"] in chosen:
            for p in t.get("packs") or []:
                if p not in packs:
                    packs.append(p)
    return packs


def suggest(profile, catalogue=None):
    """Risk ids of the catalogue that apply to the profile's packs: always-assessed first, then the others,
    each group in catalogue order. `profile` is the "profile" object of the quick answers (a whole quick-answers
    object is accepted too)."""
    cat = catalogue or load_catalogue()
    packs = set(packs_for(profile, cat))
    hits = [r for r in cat["risks"] if packs & set(r["packs"])]
    return [r["id"] for r in hits if r["always_assessed"]] + [r["id"] for r in hits if not r["always_assessed"]]


def shortlist(profile, catalogue=None, limit=SHORTLIST_LIMIT):
    """The short list pre-ticked on the Risks screen: at most `limit` risk ids of those that apply to the profile
    (`suggest`).

    1. The always-assessed risks that apply come first, in catalogue order. They are never cut: if there are more
       than `limit`, all of them are kept.
    2. Then the other applicable risks, ranked by `typical_severity * typical_likelihood` (highest first; ties in
       catalogue order), until `limit` ids are reached.
    A risk whose `audience` is "sensitive" (state-level or targeted attacks, and the like) is left out of step 2 unless
    the profile's sensitivity answer is the highest ("secrets, health or legal data") or the industrial tool is ticked.
    `profile` is the "profile" object of the quick answers (a whole quick-answers object is accepted too)."""
    cat = catalogue or load_catalogue()
    if isinstance(profile, dict) and isinstance(profile.get("profile"), dict):
        profile = profile["profile"]
    applicable = suggest(profile, cat)
    by_id = _by_id(cat)
    order = {rid: i for i, rid in enumerate(r["id"] for r in cat["risks"])}
    out = [rid for rid in applicable if by_id[rid]["always_assessed"]]
    wide = (_slot(profile, "sensitivity").get("answer") == HIGHEST_SENSITIVITY
            or SENSITIVE_TOOL in _tools(profile, cat))
    rest = [rid for rid in applicable if not by_id[rid]["always_assessed"]
            and (wide or by_id[rid].get("audience", "all") != "sensitive")]
    rest.sort(key=lambda rid: (-by_id[rid]["typical_severity"] * by_id[rid]["typical_likelihood"], order[rid]))
    return out + rest[:max(0, limit - len(out))]


def _norm_measures(ids, allowed):
    out = []
    for m in ids or []:
        if m in allowed and m not in out:
            out.append(m)
    return out


def _risk_def(entry, cat_by_id, cat):
    """The definition (catalogue risk, or the person's own) behind one entry of quick["risks"]."""
    if entry.get("custom"):
        c = entry["custom"]
        fam = c.get("family") if c.get("family") in FAMILIES else "accidental"
        crit = [x for x in (c.get("criteria") or []) if x in CRITERIA] or list(CRITERIA)
        title = str(c.get("title") or "").strip()
        if not title:
            raise QuickError(f"{entry.get('id')}: a risk of your own needs a title")
        return {"id": entry["id"], "family": fam, "title": {"en": title, "fr": title},
                "description": {"en": str(c.get("description") or ""), "fr": str(c.get("description") or "")},
                "criteria": crit, "typical_severity": None, "typical_likelihood": None, "always_assessed": False,
                "measures": cat.get("generic_measures") or [], "custom": True,
                "origin": None, "objective": None}
    r = cat_by_id.get(entry.get("id"))
    if r is None:
        raise QuickError(f"unknown risk {entry.get('id')!r}")
    return r


def validate_quick(quick, catalogue=None):
    """Raise QuickError for anything build_study could not use."""
    cat = catalogue or load_catalogue()
    if not isinstance(quick, dict):
        raise QuickError("quick answers must be an object")
    by_id = _by_id(cat)
    seen = set()
    for e in quick.get("risks") or []:
        if not isinstance(e, dict) or not e.get("id"):
            raise QuickError("every risk entry needs an id")
        if e["id"] in seen:
            raise QuickError(f"risk {e['id']} appears twice")
        seen.add(e["id"])
        if e.get("decision") not in ("keep", "discard"):
            raise QuickError(f"{e['id']}: decision must be keep or discard")
        d = _risk_def(e, by_id, cat)
        if e["decision"] == "discard" and d["always_assessed"] and not str(e.get("reason") or "").strip():
            raise QuickError(f"{e['id']}: an always-assessed risk needs a reason to be discarded")
        sv = (e.get("severity") or {}).get("value")
        if sv is not None:
            cal_mod.scale_value(sv, f"{e['id']} severity")
            if sv != propose_severity(d, quick.get("profile")) and not str((e.get("severity") or {}).get("reason") or "").strip():
                raise QuickError(f"{e['id']}: a severity different from the proposed one needs a reason")
        ans = (e.get("likelihood") or {}).get("answer")
        table = LIKELIHOOD_DELIBERATE if d["family"] == "deliberate" else LIKELIHOOD_ACCIDENTAL
        if ans not in (None, "", "dont_know") and ans not in table:
            raise QuickError(f"{e['id']}: likelihood answer {ans!r} is not one of {sorted(table)}")
    prof = _profile(quick)
    for key, table in (("downtime", DOWNTIME), ("sensitivity", SENSITIVITY)):
        a = _slot(prof, key).get("answer")
        if a not in (None, "", "dont_know") and a not in table:
            raise QuickError(f"profile {key}: {a!r} is not one of {sorted(table)}")
    vals = _slot(prof, "values").get("value") or []
    if len([v for v in vals if str(v).strip()]) > MAX_VALUES:
        raise QuickError(f"at most {MAX_VALUES} things that matter most")
    return True


# ---------------------------------------------------------------- levels

def _level_from(slot, table):
    """(level, known) for a plain profile answer."""
    a = slot.get("answer")
    if slot.get("dont_know") or a in (None, "", "dont_know") or a not in table:
        return UNKNOWN_LEVEL, False
    return table[a], True


def _profile_levels(profile):
    down, dk = _level_from(_slot(profile, "downtime"), DOWNTIME)
    sens, sk = _level_from(_slot(profile, "sensitivity"), SENSITIVITY)
    return {"availability": (down, dk), "confidentiality": (sens, sk),
            "integrity": (max(down, sens), dk and sk)}


def propose_severity(rdef, profile):
    """Proposed severity 1..4: the catalogue's typical severity blended (average, half up) with the level the
    person's answers give to the criteria the risk hits (availability: how soon a stop hurts; confidentiality:
    how sensitive the information is; integrity: the higher of the two). Atelier rule, beyond the guide."""
    return _severity(rdef, profile)[0]


def _severity(rdef, profile):
    lv = _profile_levels(profile)
    best = max(rdef["criteria"], key=lambda c: lv[c][0])
    plevel = lv[best][0]
    known = all(lv[c][1] for c in rdef["criteria"])
    t = rdef.get("typical_severity")
    level = plevel if t is None else (t + plevel + 1) // 2
    return max(1, min(4, level)), known


def likelihood_from_answer(family, answer):
    """Level 1..4 for a plain answer, or None for no answer / "I don't know"."""
    table = LIKELIHOOD_DELIBERATE if family == "deliberate" else LIKELIHOOD_ACCIDENTAL
    return table.get(answer)


def likelihood_after(now, n_extra):
    """Likelihood after extra measures (Atelier rule, beyond the guide): 1 or 2 extra measures lower it by one
    level, 3 or more by two, never below 1. A level of 1 stays 1."""
    cal_mod.scale_value(now, "likelihood")
    step = 0 if n_extra <= 0 else (1 if n_extra <= 2 else 2)
    return max(1, now - step)


def assess(quick, catalogue=None):
    """One dict per kept risk, without calibration levels: definition, severity (proposed, chosen, final, source),
    likelihood now and after (with sources), measures in place and extra. Raises QuickError on bad answers."""
    cat = catalogue or load_catalogue()
    validate_quick(quick, cat)
    by_id = _by_id(cat)
    profile = _profile(quick)
    rows = []
    for e in quick.get("risks") or []:
        if e["decision"] != "keep":
            continue
        d = _risk_def(e, by_id, cat)
        allowed = {m["id"] for m in d["measures"]}
        in_place = _norm_measures(e.get("in_place"), allowed)
        extra = [m for m in _norm_measures(e.get("extra"), allowed) if m not in in_place]
        proposed, known = _severity(d, profile)
        sev = e.get("severity") or {}
        if sev.get("value") is not None:
            final, sev_src, reason = sev["value"], "answer", str(sev.get("reason") or "").strip()
        else:
            final, reason = proposed, ""
            if d.get("custom"):
                sev_src = "answer" if known else "default"
            else:
                sev_src = "catalogue" if known else "default"
        lik = e.get("likelihood") or {}
        ans = lik.get("answer")
        now = likelihood_from_answer(d["family"], ans)
        if now is not None:
            lik_src, flag = "answer", None
        else:
            now = d["typical_likelihood"] if d.get("typical_likelihood") else CUSTOM_LIKELIHOOD
            lik_src = "default"
            flag = "dont_know" if ans == "dont_know" else "skipped"
        rows.append({"id": d["id"], "def": d, "severity_proposed": proposed, "severity": final, "severity_source": sev_src,
                     "severity_reason": reason, "severity_known": known,
                     "likelihood": now, "likelihood_source": lik_src, "likelihood_flag": flag,
                     "likelihood_answer": ans if lik_src == "answer" else None,
                     "likelihood_target": likelihood_after(now, len(extra)),
                     "in_place": in_place, "extra": extra,
                     "in_place_source": "answer" if e.get("assessed") else "default",
                     "source": "answer" if d.get("custom") else "catalogue"})
    return rows


def compute(quick, cal, catalogue=None):
    """assess() plus the levels the calibration gives: `level` now and `level_target` after the extra measures."""
    rows = assess(quick, catalogue)
    for r in rows:
        r["level"] = cal_mod.level(cal, r["severity"], r["likelihood"])
        r["level_target"] = cal_mod.level(cal, r["severity"], r["likelihood_target"])
        r["rank"] = cal_mod.level_info(cal, r["level"])["rank"]
        r["rank_target"] = cal_mod.level_info(cal, r["level_target"])["rank"]
    return rows


# ---------------------------------------------------------------- confidence, facts, assumptions, actions

def document_provided(quick):
    return bool(_slot(_profile(quick), "document").get("provided"))


def confidence(quick, catalogue=None):
    """Confidence figure 0..100 (Atelier rule, beyond the guide; design s.2.3).

    Weight of an input by source: document 1.0, answer 0.75, catalogue 0.5, default (skipped or "I don't know") 0.
    Risk confidence = 0.5 x severity weight + 0.5 x likelihood weight. Study confidence = mean of the risk
    confidences, scaled by 0.8 + 0.2 x (share of the five About-you questions answered), as a whole percentage.
    With no document provided the result never exceeds 75. With no kept risk it is 0."""
    rows = assess(quick, catalogue)
    if not rows:
        return 0
    mean = sum(0.5 * SOURCE_WEIGHT[r["severity_source"]] + 0.5 * SOURCE_WEIGHT[r["likelihood_source"]] for r in rows) / len(rows)
    known = _profile_known(_profile(quick))
    share = sum(known.values()) / len(known)
    value = int(round(100 * mean * (0.8 + 0.2 * share)))
    value = max(0, min(100, value))
    if not document_provided(quick):
        value = min(value, NO_DOCUMENT_CEILING)
    return value


def confidence_band(value):
    return "high" if value >= 80 else ("medium" if value >= 50 else "low")


def _t(en, fr):
    return {"en": en, "fr": fr}


def assumptions(quick, cal, catalogue=None):
    """Inputs the person did not give: defaults, "I don't know" and catalogue values kept as proposed.
    Each: {"kind", "scope", "risk", "what", "value", "text": {"en", "fr"}}. Ordered by effect: the About-you
    answers first, then the inputs of the highest-level risks."""
    cat = catalogue or load_catalogue()
    out = []
    prof = _profile(quick)
    questions = {"activity": _t("what the organisation does", "ce que fait l'organisation"),
                 "values": _t("what matters most", "ce qui compte le plus"),
                 "tools": _t("what you use", "ce que vous utilisez"),
                 "downtime": _t("how soon a stop of your main tools hurts", "au bout de combien de temps un arrêt de vos outils principaux fait mal"),
                 "sensitivity": _t("how sensitive your information is", "la sensibilité de vos informations")}
    used = {"activity": _t("no value used", "aucune valeur utilisée"),
            "values": _t("one general value, 'day-to-day operations'", "une valeur générale, « fonctionnement courant »"),
            "tools": _t("office IT and the general risks", "l'informatique de bureau et les risques généraux"),
            "downtime": _t(f"level {UNKNOWN_LEVEL} (serious), to be cautious", f"niveau {UNKNOWN_LEVEL} (sérieux), par prudence"),
            "sensitivity": _t(f"level {UNKNOWN_LEVEL} (serious), to be cautious", f"niveau {UNKNOWN_LEVEL} (sérieux), par prudence")}
    for key, q in questions.items():
        if slot_source(_slot(prof, key)) == "default":
            dk = bool(_slot(prof, key).get("dont_know"))
            out.append({"kind": "dont_know" if dk else "default", "scope": "profile", "risk": None, "what": key,
                        "value": used[key],
                        "text": _t(f"About you: {q['en']}: {'not sure' if dk else 'left open'}; used {used[key]['en']}.",
                                   f"Vous : {q['fr']} : {'pas sûr' if dk else 'laissé ouvert'} ; utilisé : {used[key]['fr']}.")})
    rows = sorted(compute(quick, cal, cat), key=lambda r: (-r["rank"], -r["severity"], -r["likelihood"], r["id"]))
    for r in rows:
        title = r["def"]["title"]
        if r["severity_source"] == "default":
            out.append({"kind": "default", "scope": "risk", "risk": r["id"], "what": "severity", "value": r["severity"],
                        "text": _t(f"{r['id']} {title['en']}: severity {r['severity']} proposed from a typical value and a cautious default.",
                                   f"{r['id']} {title['fr']} : gravité {r['severity']} proposée à partir d'une valeur typique et d'une valeur par défaut prudente.")})
        elif r["severity_source"] == "catalogue":
            out.append({"kind": "catalogue", "scope": "risk", "risk": r["id"], "what": "severity", "value": r["severity"],
                        "text": _t(f"{r['id']} {title['en']}: severity {r['severity']} is our proposal, kept as it is.",
                                   f"{r['id']} {title['fr']} : gravité {r['severity']} proposée, conservée telle quelle.")})
        if r["likelihood_source"] == "default":
            why = _t("not sure", "pas sûr") if r["likelihood_flag"] == "dont_know" else _t("left open", "laissé ouvert")
            out.append({"kind": "dont_know" if r["likelihood_flag"] == "dont_know" else "default", "scope": "risk", "risk": r["id"],
                        "what": "likelihood", "value": r["likelihood"],
                        "text": _t(f"{r['id']} {title['en']}: likelihood {r['likelihood']} is a typical value ({why['en']}).",
                                   f"{r['id']} {title['fr']} : vraisemblance {r['likelihood']} est une valeur typique ({why['fr']}).")})
        if r["in_place_source"] == "default":
            out.append({"kind": "default", "scope": "risk", "risk": r["id"], "what": "measures", "value": [],
                        "text": _t(f"{r['id']} {title['en']}: measures already in place, none assumed yet.",
                                   f"{r['id']} {title['fr']} : mesures déjà en place, aucune supposée pour l'instant.")})
    return out


def facts(quick, cal, catalogue=None):
    """The one-line facts of the results page and exports: documents, answers, assumptions, confidence."""
    doc = _slot(_profile(quick), "document")
    given = [doc.get("kind")] if doc.get("provided") and doc.get("kind") else []
    rows = assess(quick, catalogue)
    n_answers = sum(1 for k in ("activity", "values", "tools", "downtime", "sensitivity")
                    if slot_source(_slot(_profile(quick), k)) == "answer")
    n_answers += sum((r["severity_source"] == "answer") + (r["likelihood_source"] == "answer") for r in rows)
    ass = assumptions(quick, cal, catalogue)
    conf = confidence(quick, catalogue)
    return {"documents": given, "document_provided": bool(doc.get("provided")),
            "not_provided": [k for k in MISSING_DOCUMENTS if k not in given],
            "answers": n_answers, "assumptions": len(ass),
            "catalogue_values": len([a for a in ass if a["kind"] == "catalogue"]),
            "confidence": conf, "band": confidence_band(conf), "risks": len(rows)}


def top_actions(quick, cal, n=5, catalogue=None):
    """The `n` extra measures most worth doing: each measure's priority is the sum, over the risks it is ticked on,
    of (100 x levels gained by the risk's extra measures + severity x likelihood now) shared among that risk's extra
    measures. Ties: more risks first, then id. Each: {"id", "en", "fr", "risks", "priority"}."""
    rows = compute(quick, cal, catalogue)
    acts = {}
    for r in rows:
        if not r["extra"]:
            continue
        share = (100 * (r["rank"] - r["rank_target"]) + r["severity"] * r["likelihood"]) / len(r["extra"])
        texts = {m["id"]: m for m in r["def"]["measures"]}
        for m in r["extra"]:
            a = acts.setdefault(m, {"id": m, "en": texts[m]["en"], "fr": texts[m]["fr"], "risks": [], "priority": 0.0})
            a["risks"].append(r["id"])
            a["priority"] += share
    ranked = sorted(acts.values(), key=lambda a: (-a["priority"], -len(a["risks"]), a["id"]))
    for a in ranked:
        a["priority"] = round(a["priority"], 1)
    return ranked[:n]


# ---------------------------------------------------------------- the study

def build_study(quick, cal, catalogue=None):
    """A normal study (docs/study-format.md) from the quick answers. Every element carries `source` (document,
    answer, catalogue or default); risks also carry `sources` for severity and likelihood.

    Mapping (design s.17): About you fills `study`, business values and supporting assets; each kept risk becomes a
    feared event and a risk; a deliberate risk also becomes a risk origin with its target objective, one strategic
    scenario and one operational scenario carrying the likelihood; measures in place become baseline items,
    extra measures become measures. `likelihood` is the likelihood now, `likelihood_target` the one after the
    extra measures, so `study.register` gives a level before (`level`) and after (`level_target`).
    """
    cat = catalogue or load_catalogue()
    rows = compute(quick, cal, cat)
    lang = quick.get("lang") if quick.get("lang") in ("en", "fr") else "en"
    prof = _profile(quick)
    name = str(prof.get("name") or "").strip() or ("Quick analysis" if lang == "en" else "Analyse rapide")
    activity = str(_slot(prof, "activity").get("value") or "").strip()
    st = {"format": "atelier-study", "version": "0.1",
          "study": {"name": name, "scope": activity, "calibration": cal["id"], "path": "quick"}}
    vals = [str(v).strip() for v in (_slot(prof, "values").get("value") or []) if str(v).strip()][:MAX_VALUES]
    vsrc = slot_source(_slot(prof, "values"))
    if not vals:
        vals, vsrc = [("Day-to-day operations" if lang == "en" else "Fonctionnement courant")], "default"
    st["business_values"] = [{"id": f"BV{i}", "label": v, "source": vsrc} for i, v in enumerate(vals, 1)]
    bv_ids = [b["id"] for b in st["business_values"]]
    tools = {t["id"]: t for t in cat.get("tools") or []}
    st["supporting_assets"] = [{"id": f"SA{i}", "label": tools[t][lang], "business_values": list(bv_ids), "source": "answer"}
                               for i, t in enumerate(_tools(prof, cat), 1)]
    st.update({"feared_events": [], "baseline": [], "risk_origins": [], "stakeholders": [], "strategic_scenarios": [],
               "operational_scenarios": [], "risks": [], "measures": []})
    baseline, measures = {}, {}
    for r in rows:
        d, rid = r["def"], r["id"]
        title = d["title"][lang]
        st["feared_events"].append({"id": f"FE-{rid}", "business_value": bv_ids[0], "label": title,
                                    "criterion": ", ".join(d["criteria"]), "severity": r["severity"],
                                    "source": r["severity_source"]})
        risk = {"id": rid, "label": title, "severity": r["severity"], "likelihood": r["likelihood"],
                "likelihood_target": r["likelihood_target"], "source": r["source"],
                "sources": {"severity": r["severity_source"], "likelihood": r["likelihood_source"]}}
        if r["severity_reason"]:
            risk["severity_reason"] = r["severity_reason"]
            risk["severity_proposed"] = r["severity_proposed"]
        if r["extra"]:
            risk["treatment"] = "reduce"
        if d["family"] == "deliberate":
            if d.get("custom"):
                origin, objective = ("Other" if lang == "en" else "Autre"), title
            else:
                origin = _label(cat["origins"], d["origin"], lang)
                objective = _label(cat["objectives"], d["objective"], lang)
            st["risk_origins"].append({"id": f"RO-{rid}", "origin": origin, "objective": objective, "decision": "selected",
                                       "feared_events": [f"FE-{rid}"], "source": r["source"]})
            st["strategic_scenarios"].append({"id": f"SS-{rid}", "risk_origin": f"RO-{rid}", "feared_events": [f"FE-{rid}"],
                                              "severity": r["severity"], "paths": [{"id": f"SS-{rid}-P1", "label": title}],
                                              "source": r["source"]})
            st["operational_scenarios"].append({"id": f"OS-{rid}", "strategic_scenario": f"SS-{rid}", "path": f"SS-{rid}-P1",
                                                "likelihood": r["likelihood"], "description": d["description"][lang],
                                                "source": r["likelihood_source"]})
            risk["strategic_scenario"] = f"SS-{rid}"
        st["risks"].append(risk)
        texts = {m["id"]: m for m in d["measures"]}
        for m in r["in_place"]:
            baseline.setdefault(m, {"id": f"BL-{m}", "reference": texts[m][lang], "status": "applied", "gap": "",
                                    "source": "answer"})
        for m in r["extra"]:
            measures.setdefault(m, {"id": f"M-{m}", "label": texts[m][lang], "risks": [], "status": "planned",
                                    "source": "answer"})["risks"].append(rid)
    st["baseline"] = list(baseline.values())
    st["measures"] = list(measures.values())
    for k in ("baseline", "measures"):
        for x in st[k]:
            if x.get("gap") == "":
                x.pop("gap")
    st["quick"] = copy.deepcopy(quick)
    return st


def _label(items, key, lang):
    for i in items:
        if i["id"] == key:
            return i[lang]
    return key


# ---------------------------------------------------------------- exports

def xlsx_notice(quick, cal, catalogue=None):
    """Lines for the header of the Excel export: the honesty statement and the facts, in the study's language."""
    lang = quick.get("lang") if quick.get("lang") in ("en", "fr") else "en"
    f = facts(quick, cal, catalogue)
    names = {"architecture": ("architecture document", "document d'architecture"),
             "business-impact": ("business impact analysis", "analyse d'impact sur l'activité"),
             "security-baseline": ("security baseline", "socle de sécurité"),
             "other": ("other document", "autre document")}
    name = lambda k: names.get(k, (k, k))[0 if lang == "en" else 1]  # noqa: E731
    docs = ", ".join(name(k) for k in f["documents"]) or (
        ("mentioned, not read" if lang == "en" else "mentionné, non lu") if f["document_provided"]
        else ("none yet" if lang == "en" else "aucun pour l'instant"))
    missing = ", ".join(name(k) for k in f["not_provided"]) or ("none" if lang == "en" else "aucun")
    if lang == "fr":
        band = {"low": "faible", "medium": "moyenne", "high": "élevée"}[f["band"]]
        line = (f"Documents : {docs}. À ajouter : {missing}. Réponses : {f['answers']}. Hypothèses à confirmer : "
                f"{f['assumptions']}. Confiance : {f['confidence']} % ({band}).")
    else:
        line = (f"Documents: {docs}. To add: {missing}. Answers: {f['answers']}. Assumptions to confirm: "
                f"{f['assumptions']}. Confidence: {f['confidence']}% ({f['band']}).")
    return [HONESTY[lang], line]


def xlsx_sheets(quick, cal, catalogue=None):
    """Extra sheets for the Excel export: [(title, [rows])] with the assumptions and the top actions."""
    lang = quick.get("lang") if quick.get("lang") in ("en", "fr") else "en"
    head = ["Kind", "Risk", "Input", "Assumption"] if lang == "en" else ["Type", "Risque", "Élément", "Hypothèse"]
    kinds = ({"default": "laissé ouvert", "dont_know": "pas sûr", "catalogue": "valeur typique conservée"} if lang == "fr" else
             {"default": "left open", "dont_know": "not sure", "catalogue": "typical value kept"})
    whats = {"severity": "gravité", "likelihood": "vraisemblance", "measures": "mesures", "activity": "activité", "values": "valeurs",
             "tools": "outils", "downtime": "arrêt", "sensitivity": "sensibilité"} if lang == "fr" else {}
    ass = [head] + [[kinds.get(a["kind"], a["kind"]), a["risk"] or "", whats.get(a["what"], a["what"]), a["text"][lang]]
                    for a in assumptions(quick, cal, catalogue)]
    head2 = ["Rank", "Action", "Risks", "Priority"] if lang == "en" else ["Rang", "Action", "Risques", "Priorité"]
    acts = [head2] + [[i, a[lang], ", ".join(a["risks"]), a["priority"]] for i, a in enumerate(top_actions(quick, cal, 5, catalogue), 1)]
    return [("Assumptions" if lang == "en" else "Hypothèses", ass), ("Top actions" if lang == "en" else "Actions", acts)]
