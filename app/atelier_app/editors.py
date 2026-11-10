"""Workshops 2 to 5: what each editor accepts, and how a submitted form becomes study fields.

No HTML here (views_ws.py renders) and no method rule: links are checked against the study's ids, scale values
are handed to the engine, which refuses anything outside 1-4, and severities of strategic scenarios and risks
come from the engine (engine.derived_severity), never from the form.
"""
import copy
import datetime
import re

from . import engine

# slug -> (collection, workshop, id prefix)
SPECS = {
    "ro": ("risk_origins", 2, "RO"),
    "sh": ("stakeholders", 3, "SH"),
    "ss": ("strategic_scenarios", 3, "SS"),
    "os": ("operational_scenarios", 4, "OS"),
    "rk": ("risks", 5, "R"),
    "ms": ("measures", 5, "M"),
}
SLUG_OF = {v[0]: k for k, v in SPECS.items()}
SLUG_RE = "(" + "|".join(SPECS) + ")"
# Display order of the engine's value sets (the sets themselves come from the engine; a test checks they match).
DECISIONS = ["selected", "monitoring", "discarded"]
TREATMENTS = ["reduce", "accept", "transfer", "avoid"]
MEASURE_STATUS = ["planned", "in progress", "done", "dropped"]
SH_SCALES = ["dependence", "penetration", "maturity", "trust"]
RO_SCALES = ["motivation", "resources"]
INT_RE = re.compile(r"[+-]?[0-9]{1,6}")


class FormError(Exception):
    """A value the app cannot store. `field` names the form field it is about (None: the form as a whole)."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def items(st, key):
    return [x for x in st.get(key) or [] if isinstance(x, dict)]


def ids(st, key):
    return [x["id"] for x in items(st, key) if isinstance(x.get("id"), str)]


def find(st, key, eid):
    for x in items(st, key):
        if str(x.get("id")) == eid:
            return x
    return None


def os_targets(st):
    """Picker for an operational scenario: value -> (strategic scenario id, path id or None, label, group)."""
    out = {}
    for ss in items(st, "strategic_scenarios"):
        sid = ss.get("id")
        if not isinstance(sid, str):
            continue
        out[f"{sid}::"] = (sid, None, f"{sid}: whole scenario", sid)
        for p in ss.get("paths") or []:
            if isinstance(p, dict) and isinstance(p.get("id"), str):
                out[f"{sid}::{p['id']}"] = (sid, p["id"], f"{p['id']} {p.get('label', '')}".strip(), sid)
    return out


def risk_targets(st):
    """Picker for a risk: value -> (field, scenario id, label, group)."""
    out = {}
    for x in items(st, "strategic_scenarios"):
        if isinstance(x.get("id"), str):
            out[f"ss::{x['id']}"] = ("strategic_scenario", x["id"], x["id"], "Strategic scenarios")
    for x in items(st, "operational_scenarios"):
        if isinstance(x.get("id"), str):
            lab = f"{x['id']} ({x.get('strategic_scenario', '')}{'/' + x['path'] if x.get('path') else ''})"
            out[f"os::{x['id']}"] = ("operational_scenario", x["id"], lab, "Operational scenarios")
    return out


def risk_target_value(el):
    if el.get("operational_scenario"):
        return f"os::{el['operational_scenario']}"
    if el.get("strategic_scenario"):
        return f"ss::{el['strategic_scenario']}"
    return ""


def os_target_value(el):
    if not el.get("strategic_scenario"):
        return ""
    return f"{el['strategic_scenario']}::{el.get('path') or ''}"


def next_id(st, prefix):
    used = set()
    for k in engine.COLLECTIONS:
        for x in items(st, k):
            used.add(str(x.get("id")))
            if k == "strategic_scenarios":
                used.update(str(p.get("id")) for p in x.get("paths") or [] if isinstance(p, dict))
    nums = [int(m.group(1)) for u in used if (m := re.fullmatch(re.escape(prefix) + r"(\d+)", u))]
    n = max(nums, default=0) + 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def next_path_id(st, ssid, taken=()):
    used = set(taken)
    for k in engine.COLLECTIONS:
        for x in items(st, k):
            used.add(str(x.get("id")))
            if k == "strategic_scenarios":
                used.update(str(p.get("id")) for p in x.get("paths") or [] if isinstance(p, dict))
    n = 1
    while f"{ssid}-P{n}" in used:
        n += 1
    return f"{ssid}-P{n}"


class Form:
    """Reads one submitted form against the study. Every method returns the stored value or raises FormError."""

    def __init__(self, req, st):
        self.req, self.st = req, st

    def text(self, name, required=False, limit=500, label=None):
        v = self.req.field(name).strip()
        if required and not v:
            raise FormError(f"{label or name} is required", name)
        return v[:limit] if v else None

    def scale(self, name, required=False, label=None):
        """A whole number. Its range is the engine's business: it refuses values outside 1-4."""
        v = self.req.field(name).strip()
        if not v:
            if required:
                raise FormError(f"pick a {label or name}", name)
            return None
        if not INT_RE.fullmatch(v):
            raise FormError(f"{label or name} must be a whole number", name)
        return int(v)

    def choice(self, name, options, required=False, label=None):
        v = self.req.field(name)
        if not v:
            if required:
                raise FormError(f"pick a {label or name}", name)
            return None
        if v not in options:
            raise FormError(f"{label or name} must be one of: {', '.join(options)}", name)
        return v

    def ref(self, name, key, required=False, label=None):
        v = self.req.field(name)
        if not v:
            if required:
                raise FormError(f"pick the {label or name} from the list", name)
            return None
        if v not in ids(self.st, key):
            raise FormError(f"{label or name}: pick an existing id from the list", name)
        return v

    def refs(self, name, key, label=None):
        picked = list(dict.fromkeys(self.req.fields(name)))
        valid = set(ids(self.st, key))
        if any(x not in valid for x in picked):
            raise FormError(f"{label or name}: pick existing ids from the list", name)
        return picked

    def date(self, name, label=None):
        v = self.req.field(name).strip()
        if not v:
            return None
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise FormError(f"{label or name} must be a date (YYYY-MM-DD)", name)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise FormError(f"{label or name} must be a date (YYYY-MM-DD)", name)
        return v


def parse(slug, req, st, el=None):
    """Submitted fields -> {field: value}. None means "remove the field". Paths are handled by parse_paths."""
    f = Form(req, st)
    out = {}
    if slug == "ro":
        out["origin"] = f.text("origin", True, label="risk origin")
        out["objective"] = f.text("objective", limit=1000, label="target objective")
        for k in RO_SCALES:
            out[k] = f.scale(k)
        out["decision"] = f.choice("decision", DECISIONS, True)
        out["feared_events"] = f.refs("feared_events", "feared_events", "feared events") or None
    elif slug == "sh":
        out["name"] = f.text("name", True, limit=300)
        out["category"] = f.text("category", limit=100)
        for k in SH_SCALES:
            out[k] = f.scale(k)
        out["critical"] = req.field("critical") == "yes"
    elif slug == "ss":
        out["risk_origin"] = f.ref("risk_origin", "risk_origins", True, "risk origin")
        fes = f.refs("feared_events", "feared_events", "feared events")
        if not fes:
            raise FormError("pick at least one feared event: the scenario's severity comes from them", "feared_events")
        out["feared_events"] = fes
    elif slug == "os":
        t = os_targets(st).get(req.field("target"))
        if not t:
            raise FormError("pick a strategic scenario path from the list", "target")
        out["strategic_scenario"], out["path"] = t[0], t[1]
        out["likelihood"] = f.scale("likelihood", True)
        out["description"] = f.text("description", limit=4000)
    elif slug == "rk":
        t = risk_targets(st).get(req.field("scenario"))
        if not t:
            raise FormError("pick the strategic or operational scenario from the list", "scenario")
        out["strategic_scenario"] = t[1] if t[0] == "strategic_scenario" else None
        out["operational_scenario"] = t[1] if t[0] == "operational_scenario" else None
        out["label"] = f.text("label", True, limit=1000)
        out["likelihood"] = f.scale("likelihood", True)
        out["likelihood_target"] = f.scale("likelihood_target", label="target likelihood")
        out["treatment"] = f.choice("treatment", TREATMENTS)
        out["owner"] = f.text("owner", limit=200)
    elif slug == "ms":
        out["label"] = f.text("label", True, limit=1000)
        out["risks"] = f.refs("risks", "risks")
        out["owner"] = f.text("owner", limit=200)
        out["due"] = f.date("due", "due date")
        out["status"] = f.choice("status", MEASURE_STATUS, True)
    else:
        raise KeyError(slug)
    return out


def parse_paths(req, st, el):
    """Attack paths of a strategic scenario from its form: kept, relabelled, removed or added."""
    old = [p for p in (el or {}).get("paths") or [] if isinstance(p, dict)]
    by_id = {p.get("id"): p for p in old}
    pids, labels, shs = req.fields("path_id"), req.fields("path_label"), req.fields("path_stakeholder")
    if not (len(pids) == len(labels) == len(shs)):
        raise FormError("the path rows of the form are incomplete; reload the page", "paths")
    remove = set(req.fields("path_remove"))
    valid_sh = set(ids(st, "stakeholders"))
    used = {}
    for o in items(st, "operational_scenarios"):
        if o.get("path"):
            used.setdefault(o["path"], []).append(str(o.get("id")))
    out, seen = [], set()
    for pid, lab, sh in zip(pids, labels, shs):
        if pid not in by_id or pid in seen:
            raise FormError("unknown path in the form; reload the page", "paths")
        seen.add(pid)
        if pid in remove:
            if used.get(pid):
                raise FormError(f"{pid} is used by {', '.join(used[pid])}; link those operational scenarios to "
                                "another path first", "paths")
            continue
        if sh and sh not in valid_sh:
            raise FormError(f"{pid}: pick the stakeholder from the list", "paths")
        if not lab.strip():
            raise FormError(f"{pid}: the path needs a label (or tick remove)", "paths")
        p = copy.deepcopy(by_id[pid])
        p["label"] = lab.strip()[:1000]
        if sh:
            p["stakeholder"] = sh
        else:
            p.pop("stakeholder", None)
        out.append(p)
    missing = [p.get("id") for p in old if p.get("id") not in seen]
    if missing:  # a row the form did not send back: keep the path as it was
        out.extend(copy.deepcopy(p) for p in old if p.get("id") in missing)
    new_lab = req.field("new_path_label").strip()
    new_sh = req.field("new_path_stakeholder")
    if new_sh and not new_lab:
        raise FormError("the new path needs a label", "paths")
    if new_lab:
        if new_sh and new_sh not in valid_sh:
            raise FormError("new path: pick the stakeholder from the list", "paths")
        p = {"id": None, "label": new_lab[:1000]}
        if new_sh:
            p["stakeholder"] = new_sh
        out.append(p)
    return out


def apply(el, fields):
    for k, v in fields.items():
        if v is None or v == "" or v == []:
            el.pop(k, None)
        else:
            el[k] = v
    return el


# The form fields each editor sends back, so a refused form can be shown again with what was typed.
TEXT_FIELDS = {
    "ro": ["origin", "objective", *RO_SCALES, "decision"],
    "sh": ["name", "category", *SH_SCALES],
    "ss": ["risk_origin"],
    "os": ["likelihood", "description"],
    "rk": ["label", "likelihood", "likelihood_target", "treatment", "owner"],
    "ms": ["label", "owner", "due", "status"],
}
LIST_FIELDS = {"ro": ["feared_events"], "ss": ["feared_events"], "ms": ["risks"]}
# How the engine names a field in its messages, when that differs from the form field.
ENGINE_NAMES = {"target likelihood": "likelihood_target"}


def echo(slug, req, el=None):
    """The submitted form as an element-shaped dict, for showing a refused form again with the user's input.

    Nothing here is stored. Values stay as typed (strings); the form renderer marks a value that is not one of
    its options. Ids and severities still come from the stored element.
    """
    e = {"id": el.get("id")} if el else {}
    for k in TEXT_FIELDS[slug]:
        e[k] = req.field(k)
    for k in LIST_FIELDS.get(slug, []):
        e[k] = req.fields(k)
    if slug == "sh":
        e["critical"] = req.field("critical") == "yes"
    elif slug == "os":
        e["_target"] = req.field("target")
    elif slug == "rk":
        e["_scenario"] = req.field("scenario")
    elif slug == "ss":
        known = {p.get("id"): p for p in (el or {}).get("paths") or [] if isinstance(p, dict)}
        rows = zip(req.fields("path_id"), req.fields("path_label"), req.fields("path_stakeholder"))
        e["paths"] = [{"id": pid, "label": lab, "stakeholder": sh} for pid, lab, sh in rows if pid in known]
        e["_remove"] = set(req.fields("path_remove"))
        e["_new_label"] = req.field("new_path_label")
        e["_new_sh"] = req.field("new_path_stakeholder")
    return e


def refusal_fields(slug, messages):
    """{form field: engine message} for the engine refusals that name one field of this editor's form."""
    names = set(TEXT_FIELDS[slug])
    out = {}
    for m in messages:
        rest = m.split(": ", 1)[1] if ": " in m else m
        hit = None
        for word, field in sorted(ENGINE_NAMES.items(), key=lambda x: -len(x[0])):
            if rest.startswith(word + " ") and field in names:
                hit = field
                break
        if hit is None:
            first = rest.split(" ", 1)[0]
            hit = first if first in names else None
        if hit is not None:
            out.setdefault(hit, m)
    return out


def scale_refusals(before, after, eid):
    """New engine errors about this element's 1-4 values: the engine's refusal, in its own words."""
    old = set(before.get("errors", []))
    return [e for e in after.get("errors", []) if e not in old and "out of scale" in e
            and (e.startswith(f"{eid}:") or e.startswith(f"{eid}/"))]
