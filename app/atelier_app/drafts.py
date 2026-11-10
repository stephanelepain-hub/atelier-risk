"""Draft items: which workshop and form each belongs to, how it pre-fills that form, and the study summary sent with
a drafting request. No HTML here (views_draft.py renders) and no storage (storage.Store keeps the draft file).

A draft item only pre-fills text and suggested links. Every value that is a judgement (severity, likelihood,
decision, status, owner, due date, ratings) is left empty, so the user picks it in the form; the form then goes
through the same checks as the workshop's own add form.
"""
from . import drafting, editors

W1_KINDS = {"business_value": "business_values", "supporting_asset": "supporting_assets",
            "feared_event": "feared_events"}
KIND_SLUG = {"risk_origin": "ro", "stakeholder": "sh", "strategic_scenario": "ss", "operational_scenario": "os",
             "measure": "ms"}
KIND_TITLE = {"business_value": "business value", "supporting_asset": "supporting asset",
              "feared_event": "feared event", "risk_origin": "risk origin and objective",
              "stakeholder": "stakeholder", "strategic_scenario": "strategic scenario",
              "operational_scenario": "operational scenario", "measure": "measure"}
KIND_ORDER = ["business_value", "supporting_asset", "feared_event", "risk_origin", "stakeholder",
              "strategic_scenario", "operational_scenario", "measure"]
WHAT = {1: "business values, supporting assets and feared events", 2: "risk origins and objectives",
        3: "stakeholders and strategic scenarios", 4: "operational scenario descriptions", 5: "measure proposals"}
LABEL_FIELDS = {"business_values": "label", "supporting_assets": "label", "feared_events": "label",
                "risk_origins": "origin", "stakeholders": "name", "strategic_scenarios": None,
                "operational_scenarios": "description", "risks": "label", "measures": "label"}


def item_ws(it):
    """The workshop of a draft item (from its kind; iteration 3 items carry no workshop)."""
    return drafting.KIND_WS.get(it.get("kind"), "w1")


def ws_number(it):
    return int(item_ws(it)[1])


def main_text(it):
    """The text that identifies a proposal or an element: its label, origin, name or description, or its paths."""
    for k in ("label", "origin", "name", "description"):
        if isinstance(it.get(k), str) and it[k].strip():
            return " ".join(it[k].split()).lower()
    return " / ".join(" ".join(str(p.get("label", "")).split()).lower() for p in it.get("paths") or []
                      if isinstance(p, dict))


def key(it):
    return (it.get("kind"), main_text(it))


def known_keys(st, pending):
    """(kind, main text) of every element already in the study and every pending draft item: a new draft does not
    propose them again. A rejected item is not remembered, so a later draft may propose it again."""
    out = {key(x) for x in pending if isinstance(x, dict)}
    for kind, coll in drafting.KIND_COLLECTION.items():
        for x in editors.items(st, coll):
            out.add((kind, main_text(x)))
    return out


def resolve(st, coll, ref):
    """The id of an existing element of `coll` named by `ref` (its id, or its label ignoring case), else None."""
    if not isinstance(ref, str) or not ref.strip():
        return None
    ref = ref.strip()
    els = editors.items(st, coll)
    for x in els:
        if x.get("id") == ref:
            return ref
    lf = LABEL_FIELDS.get(coll)
    if lf:
        low = ref.lower()
        for x in els:
            if isinstance(x.get(lf), str) and x[lf].strip().lower() == low and isinstance(x.get("id"), str):
                return x["id"]
    return None


def resolve_all(st, coll, refs):
    out = []
    for r in refs or []:
        i = resolve(st, coll, r)
        if i and i not in out:
            out.append(i)
    return out


def path_id(st, ssid, ref):
    """The id of a path of strategic scenario `ssid` named by `ref` (id or label), else None."""
    ss = editors.find(st, "strategic_scenarios", ssid) if ssid else None
    if not ss or not isinstance(ref, str):
        return None
    for p in ss.get("paths") or []:
        if isinstance(p, dict) and (p.get("id") == ref or str(p.get("label", "")).strip().lower() == ref.strip().lower()):
            return p.get("id")
    return None


def prefill(st, it):
    """The element-shaped dict that pre-fills the item's accept form. Judgement fields stay empty."""
    k = it.get("kind")
    if k == "business_value":
        return {"label": it.get("label", ""), "nature": it.get("nature")}
    if k == "supporting_asset":
        return {"label": it.get("label", ""), "business_values": resolve_all(st, "business_values", it.get("business_values"))}
    if k == "feared_event":
        return {"label": it.get("label", ""), "criterion": it.get("criterion", ""),
                "business_value": resolve(st, "business_values", it.get("business_value") or it.get("business_value_label"))}
    if k == "risk_origin":
        return {"origin": it.get("origin", ""), "objective": it.get("objective", ""),
                "feared_events": resolve_all(st, "feared_events", it.get("feared_events"))}
    if k == "stakeholder":
        return {"name": it.get("name", ""), "category": it.get("category", "")}
    if k == "strategic_scenario":
        paths = it.get("paths") or []
        first = paths[0] if paths else {}
        return {"risk_origin": resolve(st, "risk_origins", it.get("risk_origin")),
                "feared_events": resolve_all(st, "feared_events", it.get("feared_events")), "paths": [],
                "_new_label": first.get("label", ""), "_new_sh": resolve(st, "stakeholders", first.get("stakeholder"))}
    if k == "operational_scenario":
        ssid = resolve(st, "strategic_scenarios", it.get("strategic_scenario"))
        pid = path_id(st, ssid, it.get("path"))
        target = f"{ssid}::{pid or ''}" if ssid else ""
        return {"_target": target if target in editors.os_targets(st) else "", "description": it.get("description", "")}
    if k == "measure":
        return {"label": it.get("label", ""), "risks": resolve_all(st, "risks", it.get("risks"))}
    return {}


def as_form(st, it):
    """Form fields for "accept all" (text-only kinds only): {field: [values]}."""
    p = prefill(st, it)
    k = it.get("kind")
    if k == "business_value":
        return {"label": [p["label"]], "nature": [p.get("nature") or ""]}
    if k == "supporting_asset":
        return {"label": [p["label"]], "business_values": list(p["business_values"])}
    if k == "stakeholder":
        return {"name": [p["name"]], "category": [p.get("category") or ""]}
    raise KeyError(k)


class Form:
    """A stand-in for a submitted form (field/fields), used by "accept all"."""

    def __init__(self, data):
        self.form = data

    def field(self, name, default=""):
        v = self.form.get(name)
        return v[0] if v else default

    def fields(self, name):
        return list(self.form.get(name) or [])


def _line(x, *names):
    return " | ".join(f"{n}: {' '.join(str(x.get(n)).split())[:300]}" for n in names if x.get(n) not in (None, "", []))


def study_summary(st, ws):
    """Plain text: the study's name and scope and the elements a workshop's draft may refer to (ids and labels only,
    never a level). Sent with each drafting request, through the same route policy as the documents."""
    meta = st.get("study") if isinstance(st.get("study"), dict) else {}
    out = [f"Study: {meta.get('name') or '(no name)'}"]
    if meta.get("scope"):
        out.append(f"Scope: {' '.join(str(meta['scope']).split())[:1500]}")

    def block(title, coll, *names):
        rows = editors.items(st, coll)
        if rows:
            out.append(f"{title}:")
            out.extend(f"- {x.get('id')} | {_line(x, *names)}" for x in rows)
    n = int(str(ws).lstrip("w"))
    block("Business values", "business_values", "label", "nature")
    if n in (1, 4):
        block("Supporting assets", "supporting_assets", "label", "business_values")
    block("Feared events", "feared_events", "label", "business_value", "criterion")
    if n >= 2:
        block("Risk origins", "risk_origins", "origin", "objective", "feared_events")
    if n >= 3:
        block("Stakeholders", "stakeholders", "name", "category")
        rows = editors.items(st, "strategic_scenarios")
        if rows:
            out.append("Strategic scenarios:")
            for x in rows:
                out.append(f"- {x.get('id')} | {_line(x, 'risk_origin', 'feared_events')}")
                for p in x.get("paths") or []:
                    if isinstance(p, dict):
                        out.append(f"  - path {p.get('id')} | {_line(p, 'label', 'stakeholder')}")
    if n >= 4:
        block("Operational scenarios", "operational_scenarios", "strategic_scenario", "path", "description")
    if n >= 5:
        block("Risks", "risks", "label", "strategic_scenario", "operational_scenario")
        block("Measures", "measures", "label", "risks")
    return "\n".join(out)
