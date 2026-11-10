"""A study (one EBIOS RM analysis) as a JSON document: checks and the risk register.

The format is described in docs/study-format.md. Rules implemented here come from the ANSSI guide
EBIOS Risk Manager v1.5 (page numbers are the guide's printed pages):
  - strategic scenario severity comes from the feared events it targets (p.49);
  - an operational scenario inherits the severity of its strategic scenario (workshop 4 notes, p.62 and p.65);
  - risk level = calibration grid(severity, likelihood) (p.74-75);
  - feared events of high severity left out of every scenario are a blind spot to review (p.73).
"""
from . import calibration as cal_mod

COLLECTIONS = ["business_values", "supporting_assets", "feared_events", "baseline", "risk_origins",
               "stakeholders", "strategic_scenarios", "operational_scenarios", "risks", "measures"]
DECISIONS = {"selected", "monitoring", "discarded"}
TREATMENTS = {"reduce", "accept", "transfer", "avoid", None}
MEASURE_STATUS = {"planned", "in progress", "done", "dropped"}


def _items(study, key):
    return study.get(key) or []


def _is_scale(x):
    return isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 4


def validate(study, cal):
    """Return {"errors": [...], "warnings": [...]}. Errors make the study unusable; warnings need a look."""
    err, warn = [], []
    if study.get("format") != "atelier-study":
        err.append("header: format must be 'atelier-study'")
    ids = {}
    for key in COLLECTIONS:
        for x in _items(study, key):
            i = x.get("id")
            if not i:
                err.append(f"{key}: element without id")
            elif i in ids:
                err.append(f"duplicate id {i} ({ids[i][0]} and {key})")
            else:
                ids[i] = (key, x)

    def ref(owner, value, key):
        if value is None:
            return None
        if value not in ids or ids[value][0] != key:
            err.append(f"{owner}: unknown {key[:-1].replace('_', ' ')} {value}")
            return None
        return ids[value][1]

    def scale(owner, x, what, required=True):
        if x is None:
            if required:
                err.append(f"{owner}: {what} missing")
            return None
        if not _is_scale(x):
            err.append(f"{owner}: {what} {x!r} out of scale 1-4")
            return None
        return x

    for sa in _items(study, "supporting_assets"):
        for bv in sa.get("business_values") or []:
            ref(sa.get("id"), bv, "business_values")
    for fe in _items(study, "feared_events"):
        ref(fe.get("id"), fe.get("business_value"), "business_values")
        scale(fe.get("id"), fe.get("severity"), "severity")
    for ro in _items(study, "risk_origins"):
        if ro.get("decision") not in DECISIONS:
            err.append(f"{ro.get('id')}: decision must be one of {sorted(DECISIONS)}")
        for k in ("motivation", "resources"):
            scale(ro.get("id"), ro.get(k), k, required=False)
        for fe in ro.get("feared_events") or []:
            ref(ro.get("id"), fe, "feared_events")
    for sh in _items(study, "stakeholders"):
        for k in ("dependence", "penetration", "maturity", "trust"):
            scale(sh.get("id"), sh.get(k), k, required=False)

    ss_severity = {}
    covered = set()
    for ss in _items(study, "strategic_scenarios"):
        sid = ss.get("id")
        ro = ref(sid, ss.get("risk_origin"), "risk_origins")
        if ro and ro.get("decision") != "selected":
            warn.append(f"{sid}: built on {ro.get('id')}, which is not selected")
        sevs = []
        for fe in ss.get("feared_events") or []:
            f = ref(sid, fe, "feared_events")
            covered.add(fe)
            if f and _is_scale(f.get("severity")):
                sevs.append(f["severity"])
        if not ss.get("feared_events"):
            err.append(f"{sid}: no feared event targeted")
        s = scale(sid, ss.get("severity"), "severity")
        if s and sevs and s != max(sevs):
            err.append(f"{sid}: severity {s} but its feared events reach {max(sevs)} (severity comes from the feared events, guide p.49)")
        ss_severity[sid] = s or (max(sevs) if sevs else None)
        for p in ss.get("paths") or []:
            if p.get("stakeholder"):
                ref(f"{sid}/{p.get('id')}", p["stakeholder"], "stakeholders")

    os_ss = {}
    for os_ in _items(study, "operational_scenarios"):
        oid = os_.get("id")
        ss = ref(oid, os_.get("strategic_scenario"), "strategic_scenarios")
        os_ss[oid] = ss.get("id") if ss else None
        scale(oid, os_.get("likelihood"), "likelihood")
        if os_.get("severity") is not None and ss and os_["severity"] != ss_severity.get(ss.get("id")):
            err.append(f"{oid}: severity {os_['severity']} differs from its strategic scenario (inherited, guide p.62, p.65)")

    for r in _items(study, "risks"):
        rid = r.get("id")
        ref(rid, r.get("strategic_scenario"), "strategic_scenarios")
        ref(rid, r.get("operational_scenario"), "operational_scenarios")
        s = scale(rid, r.get("severity"), "severity")
        scale(rid, r.get("likelihood"), "likelihood")
        scale(rid, r.get("likelihood_target"), "target likelihood", required=False)
        linked = r.get("strategic_scenario") or os_ss.get(r.get("operational_scenario"))
        if s and linked in ss_severity and ss_severity[linked] and s != ss_severity[linked]:
            err.append(f"{rid}: severity {s} differs from its scenario {linked} ({ss_severity[linked]})")
        if r.get("treatment") not in TREATMENTS:
            err.append(f"{rid}: treatment must be one of reduce/accept/transfer/avoid")
        if r.get("likelihood_target") and r.get("likelihood") and _is_scale(r["likelihood_target"]) and _is_scale(r["likelihood"]) \
                and r["likelihood_target"] < r["likelihood"] and not any(rid in (m.get("risks") or []) for m in _items(study, "measures")):
            warn.append(f"{rid}: target likelihood lower than today with no measure linked")

    for m in _items(study, "measures"):
        mid = m.get("id")
        for rid in m.get("risks") or []:
            ref(mid, rid, "risks")
        if m.get("status") not in MEASURE_STATUS:
            err.append(f"{mid}: status must be one of {sorted(MEASURE_STATUS)}")
        missing = [k for k in ("owner", "due") if not m.get(k)]
        if missing and m.get("status") not in ("done", "dropped"):
            warn.append(f"{mid}: no {' or '.join(missing)}")

    if _items(study, "strategic_scenarios"):
        for fe in _items(study, "feared_events"):
            if _is_scale(fe.get("severity")) and fe["severity"] >= 3 and fe.get("id") not in covered:
                warn.append(f"{fe.get('id')}: severity {fe['severity']} but no scenario targets it (blind spot, guide p.73)")
    return {"errors": err, "warnings": warn}


def register(study, cal):
    """Risk register: each risk with its level now and at target, acceptability and linked measures."""
    measures = _items(study, "measures")
    rows = []
    for r in _items(study, "risks"):
        row = {k: r.get(k) for k in ("id", "label", "severity", "likelihood", "likelihood_target", "treatment", "owner")}
        row["level"] = cal_mod.level(cal, r["severity"], r["likelihood"])
        row["acceptability"] = cal_mod.level_info(cal, row["level"]).get("acceptability", "")
        if r.get("likelihood_target"):
            row["level_target"] = cal_mod.level(cal, r["severity"], r["likelihood_target"])
        row["measures"] = [m["id"] for m in measures if r.get("id") in (m.get("risks") or [])]
        rows.append(row)
    return rows


def summary(rows, cal):
    order = [l["name"] for l in sorted(cal["levels"], key=lambda l: -l["rank"])]

    def count(key):
        return {n: c for n in order if (c := sum(1 for r in rows if r.get(key) == n))}
    return {"now": count("level"), "target": count("level_target")}
