"""Findings in three short lines, for the results page and the Excel export: To strengthen / Based on / Next step.

Each line is one short sentence of at most 15 words. Nothing here computes a level: levels, ranks, answers and the
extra measures come from the engine's rows (engine.quick_compute) and the person's own answers.
"""
from . import labels
from .views_quick import tr

MAX_WORDS = 15
LABEL_KEYS = ("gap_lbl", "evid_lbl", "fix_lbl")

TXT = {
    "en": {
        "more": "{t} (+{n} more)",
        "gap_open": "{k} of {m} helpful measures are still to add.",
        "gap_done": "All {m} helpful measures are in place.",
        "ev_lik_deliberate": "You said “{x}” for how likely it is.",
        "ev_lik_accidental": "You said “{x}” when asked if it happened.",
        "ev_sev": "You rated it “{x}”, noting: {why}",
        "ev_sens": "You said your information is “{x}”.",
        "ev_down": "You said a stop would matter “{x}”.",
        "ev_tools": "You said you use: {x}.",
        "ev_typical": "A typical value for businesses like yours.",
        "fix_done": "Review your measures yearly: an hour, a manager.",
        "close_land": "With your {m} planned actions, {k} of your {n} risks move to {lv}.",
        "close_land_1": "With your planned action, {k} of your {n} risks move to {lv}.",
        "close_better": "With your {m} planned actions, {k} of your {n} risks improve by a level.",
        "close_start": "Your {m} planned actions are a first step on {n} risks.",
        "close_now": "{k} of your {n} risks are already at {lv}.",
        "close_map": "You have mapped {n} risks: a solid start for choosing your first actions.",
        "or": " or ", "more_tools": "{a} and {n} more",
    },
    "fr": {
        "more": "{t} (+{n} autres)",
        "gap_open": "{k} mesures utiles sur {m} restent à ajouter.",
        "gap_done": "Les {m} mesures utiles sont en place.",
        "ev_lik_deliberate": "Vous avez répondu « {x} » pour la probabilité.",
        "ev_lik_accidental": "Vous avez répondu « {x} » : est-ce arrivé ?",
        "ev_sev": "Vous l'avez noté « {x} », avec cette remarque : {why}",
        "ev_sens": "Selon vous, vos informations sont « {x} ».",
        "ev_down": "Selon vous, un arrêt compterait « {x} ».",
        "ev_tools": "Vous avez dit utiliser : {x}.",
        "ev_typical": "Une valeur typique pour des entreprises comme la vôtre.",
        "fix_done": "Revoir vos mesures chaque année : une heure, un responsable.",
        "close_land": "Avec vos {m} actions prévues, {k} de vos {n} risques passent à {lv}.",
        "close_land_1": "Avec votre action prévue, {k} de vos {n} risques passent à {lv}.",
        "close_better": "Avec vos {m} actions prévues, {k} de vos {n} risques gagnent un niveau.",
        "close_start": "Vos {m} actions prévues sont un premier pas sur {n} risques.",
        "close_now": "{k} de vos {n} risques sont déjà à {lv}.",
        "close_map": "Vous avez cartographié {n} risques : un bon départ pour choisir vos premières actions.",
        "or": " ou ", "more_tools": "{a} et {n} autres",
    },
}


def wc(text):
    """Words in a line: whitespace-separated tokens that hold a letter or a digit (a lone ":" is no word)."""
    return len([w for w in str(text).split() if any(c.isalnum() for c in w)])


def _pick(d, lang):
    return d.get(lang) or d.get("en") or ""


def _cut(text, n):
    """The first `n` words of a text, with an ellipsis when something was cut."""
    w = str(text).split()
    return " ".join(w) if len(w) <= n else " ".join(w[:n]).rstrip(",;:.") + "…"


def _t(lang):
    return TXT[lang]


def risk_title(r, lang, n=12):
    return _cut(_pick(r["def"]["title"], lang), n)


def evidence(r, quick, cat, lang):
    """Which of the person's own answers led to this risk's rating, quoted; a typical value when none applies."""
    t = _t(lang)
    fam = r["def"]["family"]
    if r["likelihood_source"] == "answer" and r.get("likelihood_answer"):
        x = tr(lang, "lik_" + r["likelihood_answer"])
        return t["ev_lik_" + fam].format(x=_cut(x.split(":")[0].strip(), 5))
    if r["severity_source"] == "answer" and r["severity_reason"]:
        x = labels.SEVERITY_LABEL[lang][r["severity"]]
        return t["ev_sev"].format(x=x, why="“" + _cut(r["severity_reason"], 7) + "”")
    prof = quick.get("profile") or {}
    crit = r["def"].get("criteria") or []
    sens = (prof.get("sensitivity") or {}).get("answer")
    if sens and sens != "dont_know" and "confidentiality" in crit:
        return t["ev_sens"].format(x=_cut(tr(lang, "sens_" + sens).split(":")[0].strip(), 6))
    down = (prof.get("downtime") or {}).get("answer")
    if down and down != "dont_know" and "availability" in crit:
        return t["ev_down"].format(x=_cut(tr(lang, "downtime_" + down), 5))
    tool_ids = (prof.get("tools") or {}).get("value") or []
    names = [_pick(x, lang) for x in cat["tools"] if x["id"] in tool_ids]
    if names:
        a = _cut(names[0], 5)
        x = a if len(names) == 1 else t["more_tools"].format(a=a, n=len(names) - 1)
        return t["ev_tools"].format(x=x)
    return t["ev_typical"]


def fix(measure_id, texts, lang):
    """"Short action: how long or how much, who." for one measure (texts: {id: catalogue measure})."""
    short = labels.short_action(measure_id, lang)
    how = labels.effort_line(measure_id, lang)
    if short and how:
        return f"{short}{' : ' if lang == 'fr' else ': '}{how}."
    return _cut(_pick(texts[measure_id], lang), 12) + "."


def _next_measure(r):
    """The measure to do first for a risk: one the person chose to add, else the first one not yet in place."""
    if r["extra"]:
        return r["extra"][0]
    for m in r["def"]["measures"]:
        if m["id"] not in r["in_place"]:
            return m["id"]
    return None


def risk_item(r, quick, cat, lang):
    t = _t(lang)
    ms = r["def"]["measures"]
    missing = [m for m in ms if m["id"] not in r["in_place"]]
    gap = t["gap_open"].format(k=len(missing), m=len(ms)) if missing else t["gap_done"].format(m=len(ms))
    mid = _next_measure(r)
    texts = {m["id"]: m for m in ms}
    return {"id": r["id"], "title": risk_title(r, lang, 14), "gap": gap, "evidence": evidence(r, quick, cat, lang),
            "fix": fix(mid, texts, lang) if mid else t["fix_done"]}


def action_item(a, by_id, quick, cat, lang):
    t = _t(lang)
    r0 = by_id[a["risks"][0]]
    title = risk_title(r0, lang, 11)
    gap = title if len(a["risks"]) == 1 else t["more"].format(t=title, n=len(a["risks"]) - 1)
    texts = {m["id"]: m for m in r0["def"]["measures"]}
    texts.setdefault(a["id"], a)
    return {"id": a["id"], "risks": a["risks"], "gap": gap, "evidence": evidence(r0, quick, cat, lang),
            "fix": fix(a["id"], texts, lang)}


def closing(rows, cal, lang):
    """One encouraging line from the real before/after levels of the kept risks ("" with no kept risk)."""
    t = _t(lang)
    n = len(rows)
    if not n:
        return ""
    ranked = sorted(cal["levels"], key=lambda l: l["rank"])
    top = ranked[-1]["rank"]
    low = t["or"].join(labels.level_label(cal, l["name"], lang) for l in ranked if l["rank"] < top)
    m = len({x for r in rows for x in r["extra"]})
    better = [r for r in rows if r["rank_target"] < r["rank"]]
    land = [r for r in better if r["rank_target"] < top]
    if land:
        return t["close_land_1" if m == 1 else "close_land"].format(m=m, k=len(land), n=n, lv=low)
    if better:
        return t["close_better"].format(m=m, k=len(better), n=n)
    if m:
        return t["close_start"].format(m=m, n=n)
    done = [r for r in rows if r["rank"] < top]
    if done:
        return t["close_now"].format(k=len(done), n=n, lv=low)
    return t["close_map"].format(n=n)


def build(quick, cat, cal, rows, actions, lang):
    by_id = {r["id"]: r for r in rows}
    return {"actions": [action_item(a, by_id, quick, cat, lang) for a in actions],
            "risks": [risk_item(r, quick, cat, lang) for r in rows],
            "closing": closing(rows, cal, lang)}
