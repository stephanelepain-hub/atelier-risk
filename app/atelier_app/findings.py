"""Findings in three short lines, for the results page and the Excel export: To strengthen / Based on / Next step.

Each line is one short sentence of at most 15 words. Nothing here computes a level: levels, ranks, answers and the
extra measures come from the engine's rows (engine.quick_compute) and the person's own answers.
"""
from . import labels

MAX_WORDS = 15
LABEL_KEYS = ("gap_lbl", "evid_lbl", "fix_lbl")

TXT = {
    "en": {
        "more": "{t} (+{n} more)",
        "gap_open": "{k} of {m} helpful measures are still to add.",
        "gap_done": "All {m} helpful measures are in place.",
        "ev_sev": "You rated it “{x}”, noting: {why}",
        "ev_sens": {"internal": "Your information is for internal use.", "confidential": "Customer data is confidential for you.",
                    "critical": "Your information is highly sensitive."},
        "ev_down": {"hours": "A stop would hurt within hours.",
                    "day": "A stop would hurt within a day or two."},
        "ev_tool": {"remote": "Some of you work away from the office.", "cloud": "You keep files or email online.",
                    "provider": "An outside company looks after your IT.", "website": "You have a website.",
                    "shop": "You use an online shop.", "industrial": "Your machines run on computers.",
                    "cloud_infra": "You run servers, apps or data in the cloud."},
        "fix_done": "Review your measures yearly: an hour, a manager.",
        "close_land": "With {m} actions, {k} of your {n} {risks} {move} to {lv}.",
        "close_land_1": "With 1 action, {k} of your {n} {risks} {move} to {lv}.",
        "close_better": "With {m} actions, {k} of your {n} {risks} {improve} by a level.",
        "close_better_1": "With 1 action, {k} of your {n} {risks} {improve} by a level.",
        "close_start": "Your {m} actions are a first step on {n} {risks}.",
        "close_start_1": "Your action is a first step on {n} {risks}.",
        "close_now": "{k} of your {n} {risks} {are} already at {lv}.",
        "verbs": {"move": ("move", "moves"), "improve": ("improve", "improves"), "are": ("are", "is")}, "risk": ("risks", "risk"),
        "close_map": "You have mapped {n} {risks}: a solid start for choosing your first actions.",
        "or": " or ",
    },
    "fr": {
        "more": "{t} (+{n} autres)",
        "gap_open": "{k} mesures utiles sur {m} restent à ajouter.",
        "gap_done": "Les {m} mesures utiles sont en place.",
        "ev_sev": "Vous l'avez noté « {x} », avec cette remarque : {why}",
        "ev_sens": {"internal": "Vos informations sont à usage interne.", "confidential": "Les données clients sont confidentielles chez vous.",
                    "critical": "Vos informations sont très sensibles."},
        "ev_down": {"hours": "Un arrêt ferait mal en quelques heures.",
                    "day": "Un arrêt ferait mal en un jour ou deux."},
        "ev_tool": {"remote": "Une partie de l'équipe travaille hors du bureau.", "cloud": "Vous gardez fichiers ou messagerie en ligne.",
                    "provider": "Une entreprise extérieure s'occupe de votre informatique.", "website": "Vous avez un site web.",
                    "shop": "Vous utilisez une boutique en ligne.", "industrial": "Vos machines fonctionnent par ordinateur.",
                    "cloud_infra": "Vous faites tourner serveurs, applications ou données dans le cloud."},
        "fix_done": "Revoir vos mesures chaque année : une heure, un responsable.",
        "close_land": "Avec {m} actions, {k} de vos {n} {risks} {move} à {lv}.",
        "close_land_1": "Avec 1 action, {k} de vos {n} {risks} {move} à {lv}.",
        "close_better": "Avec {m} actions, {k} de vos {n} {risks} {improve} un niveau.",
        "close_better_1": "Avec 1 action, {k} de vos {n} {risks} {improve} un niveau.",
        "close_start": "Vos {m} actions sont un premier pas sur {n} {risks}.",
        "close_start_1": "Votre action est un premier pas sur {n} {risks}.",
        "close_now": "{k} de vos {n} {risks} {are} déjà à {lv}.",
        "verbs": {"move": ("passent", "passe"), "improve": ("gagnent", "gagne"), "are": ("sont", "est")}, "risk": ("risques", "risque"),
        "close_map": "Vous avez cartographié {n} {risks} : un bon départ pour choisir vos premières actions.",
        "or": " ou ",
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
    """Why this risk is on the list, in the business's own terms: the person's note on the severity when there is
    one, then what the About-you answers say (a tool used, how sensitive the information is, how soon a stop hurts),
    then the catalogue's own reason for the risk. The likelihood answer is never quoted: it is how the likelihood is
    rated, so quoting it would explain nothing."""
    t = _t(lang)
    d = r["def"]
    if r["severity_source"] == "answer" and r["severity_reason"]:
        x = labels.SEVERITY_LABEL[lang][r["severity"]]
        return t["ev_sev"].format(x=x, why="“" + _cut(r["severity_reason"], 7) + "”")
    prof = quick.get("profile") or {}
    tool_ids = (prof.get("tools") or {}).get("value") or []
    packs = set(d.get("packs") or [])
    if not d.get("custom") and "all" not in packs:
        for tool in cat["tools"]:            # a tool the person ticked that brings this risk (office IT is too broad to quote)
            tp = set(tool.get("packs") or [])
            if tool["id"] in tool_ids and tool["id"] in t["ev_tool"] and tp & packs:
                return t["ev_tool"][tool["id"]]
    crit = d.get("criteria") or []
    sens = (prof.get("sensitivity") or {}).get("answer")
    if sens in t["ev_sens"] and "confidentiality" in crit:
        return t["ev_sens"][sens]
    down = (prof.get("downtime") or {}).get("answer")
    if down in t["ev_down"] and "availability" in crit:
        return t["ev_down"][down]
    why = (d.get("why") or {})
    if why.get(lang) or why.get("en"):
        return _pick(why, lang)
    return _cut(_pick(d.get("description") or {}, lang), MAX_WORDS)


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


def risk_item(r, quick, cat, lang, n=None):
    t = _t(lang)
    ms = r["def"]["measures"]
    missing = [m for m in ms if m["id"] not in r["in_place"]]
    gap = t["gap_open"].format(k=len(missing), m=len(ms)) if missing else t["gap_done"].format(m=len(ms))
    mid = _next_measure(r)
    texts = {m["id"]: m for m in ms}
    return {"id": r["id"], "n": n, "title": risk_title(r, lang, 14), "gap": gap, "evidence": evidence(r, quick, cat, lang),
            "fix": fix(mid, texts, lang) if mid else t["fix_done"]}


def action_item(a, by_id, quick, cat, lang, used=None):
    """One top action in three lines. The first two lines (the risk it helps, and why that risk is on the list) come
    from the first of the action's risks that an earlier action has not shown yet (`used`), so that the cards do not
    repeat one sentence."""
    t = _t(lang)
    rid0 = next((rid for rid in a["risks"] if used is None or rid not in used), a["risks"][0])
    if used is not None:
        used.add(rid0)
    r0 = by_id[rid0]
    title = risk_title(r0, lang, 7)
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
    ranked = sorted(cal["levels"], key=lambda l: l["rank"])[:2]   # the two lowest levels: Low or Moderate
    top = ranked[-1]["rank"] + 1                                   # a risk "lands" when its level after is below this
    low = t["or"].join(labels.level_label(cal, l["name"], lang) for l in ranked)
    m = len({x for r in rows for x in r["extra"]})
    better = [r for r in rows if r["rank_target"] < r["rank"]]
    land = [r for r in better if r["rank_target"] < top]
    v = t["verbs"]

    def verb(key, k):
        return v[key][0 if k != 1 else 1]
    if land:
        k = len(land)
        return t["close_land_1" if m == 1 else "close_land"].format(m=m, k=k, n=n, lv=low, move=verb("move", k), risks=t["risk"][n == 1])
    if better:
        k = len(better)
        return t["close_better_1" if m == 1 else "close_better"].format(m=m, k=k, n=n, improve=verb("improve", k), risks=t["risk"][n == 1])
    if m:
        return t["close_start_1" if m == 1 else "close_start"].format(m=m, n=n, risks=t["risk"][n == 1])
    done = [r for r in rows if r["rank"] < top]
    if done:
        return t["close_now"].format(k=len(done), n=n, lv=low, are=verb("are", len(done)), risks=t["risk"][n == 1])
    return t["close_map"].format(n=n, risks=t["risk"][n == 1])


def build(quick, cat, cal, rows, actions, lang):
    by_id = {r["id"]: r for r in rows}
    used = set()
    return {"actions": [action_item(a, by_id, quick, cat, lang, used) for a in actions],
            "risks": [risk_item(r, quick, cat, lang, i) for i, r in enumerate(rows, 1)],
            "closing": closing(rows, cal, lang)}
