"""The only place the app talks to the engine. Levels, checks and registers all come from here."""
import copy
import importlib
import io
import os
import pathlib
import re
import sys
import tempfile
import zipfile

from . import ENGINE_DIR  # noqa: F401  (puts the engine on sys.path)
from atelier_engine import calibration, importer as importer_mod, study as study_mod  # noqa: E402

COLLECTIONS = list(study_mod.COLLECTIONS)
DECISIONS = frozenset(study_mod.DECISIONS)
TREATMENTS = frozenset(x for x in study_mod.TREATMENTS if x is not None)
MEASURE_STATUS = frozenset(study_mod.MEASURE_STATUS)
DERIVED_SEVERITY = ("strategic_scenarios", "risks")  # the engine checks these against their sources
DEFAULT_CAL = "anssi-v1.5"
CalibrationError = calibration.CalibrationError
SpreadsheetError = importer_mod.SpreadsheetError


def calibrations():
    """{id: "public" | "private"} as the engine lists them (private dir taken from ATELIER_PRIVATE_DIR)."""
    return calibration.available()


def load_cal(cal_id):
    return calibration.load(cal_id)


def study_cal_id(st):
    return ((st or {}).get("study") or {}).get("calibration") or DEFAULT_CAL


def structure_errors(st):
    """Shape problems that would make the engine itself crash. The engine's own checks run after these."""
    if not isinstance(st, dict):
        return ["the file is not a JSON object"]
    errs = []
    if st.get("format") != "atelier-study":
        errs.append("header: format must be 'atelier-study'")
    if "study" in st and not isinstance(st["study"], dict):
        errs.append("study: must be an object")
    for key in COLLECTIONS:
        v = st.get(key)
        if v is None:
            continue
        if not isinstance(v, list):
            errs.append(f"{key}: must be a list")
        elif any(not isinstance(x, dict) for x in v):
            errs.append(f"{key}: every element must be an object")
    for ss in st.get("strategic_scenarios") or []:
        if isinstance(ss, dict) and ss.get("paths") is not None and (
                not isinstance(ss["paths"], list) or any(not isinstance(p, dict) for p in ss["paths"])):
            errs.append(f"{ss.get('id')}: paths must be a list of objects")
    return errs


def check(st):
    """Engine validation. Returns {"errors", "warnings", "calibration", "cal"}; never raises."""
    errs = structure_errors(st)
    cal_id = study_cal_id(st) if isinstance(st, dict) else DEFAULT_CAL
    if errs:
        return {"errors": errs, "warnings": [], "calibration": cal_id, "cal": None}
    try:
        cal = calibration.load(cal_id)
    except (CalibrationError, ValueError, OSError) as e:
        return {"errors": [f"calibration: {e}"], "warnings": [], "calibration": cal_id, "cal": None}
    try:
        r = study_mod.validate(st, cal)
    except Exception as e:  # the engine met a shape it does not expect: report, never crash the page
        return {"errors": [f"engine could not check the study: {type(e).__name__}: {e}"], "warnings": [],
                "calibration": cal_id, "cal": cal}
    return {"errors": r["errors"], "warnings": r["warnings"], "calibration": cal_id, "cal": cal}


def register(st, cal):
    """Engine risk register and per-level counts. Call only for a study without errors (as the CLI does)."""
    rows = study_mod.register(st, cal)
    return rows, study_mod.summary(rows, cal)


def risk_map(rows, cal, stage, title):
    """Inline SVG from the engine; orientation belongs to the calibration.

    Treat colours as data, not SVG markup: the engine currently interpolates them into attributes.
    Match the CSS fallback for malformed colours without changing any level or the original calibration.
    """
    from atelier_engine import maps
    safe = copy.deepcopy(cal)
    for level in safe["levels"]:
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", str(level.get("colour") or "")):
            level["colour"] = "BBBBBB"
    return maps.svg(rows, safe, stage=stage, title=title, orientation=cal.get("map_orientation"))


def level(cal, severity, likelihood):
    return calibration.level(cal, severity, likelihood)


def level_info(cal, name):
    return calibration.level_info(cal, name)


def have_xlsx():
    """True when openpyxl, which the engine's Excel export needs, can be imported."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return False
    return True


def to_xlsx_bytes(st, cal, tmp_dir):
    """Run the engine's Excel export into a private temp file and return the bytes."""
    from atelier_engine import export
    fd, path = tempfile.mkstemp(dir=tmp_dir, prefix=".export-", suffix=".xlsx")
    os.close(fd)
    try:
        export.to_xlsx(st, cal, path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


def review_layouts():
    from atelier_engine import importer
    return importer.layouts()


def import_review(data, cal, layout=None):
    """Bound expanded workbook size before openpyxl parses it. The engine alone interprets cells."""
    from atelier_engine import importer
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries = z.infolist()
            if len(entries) > 3000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                raise importer.SpreadsheetError("expanded workbook exceeds the safe import limit")
    except zipfile.BadZipFile:
        raise importer.SpreadsheetError("not an xlsx workbook") from None
    return importer.read_xlsx(io.BytesIO(data), cal, layout=layout)


def review_plugin(private_dir):
    """Load the optional installed plugin, never a package from an unrelated private directory."""
    directory = pathlib.Path(private_dir) / "plugins"
    cached = sys.modules.get("atelier_private")
    if cached and pathlib.Path(cached.__file__).resolve().parent.parent != directory.resolve():
        for name in list(sys.modules):
            if name == "atelier_private" or name.startswith("atelier_private."):
                del sys.modules[name]
    if not (directory / "atelier_private" / "review.py").is_file():
        return None
    sys.path.insert(0, str(directory))
    try:
        importlib.invalidate_caches()
        return importlib.import_module("atelier_private.review")
    finally:
        sys.path.remove(str(directory))


def review_result(state, cal, plugin):
    if state['report'].get('errors'):
        return {'register': [], 'summary': None, 'check': check(state['study']), 'score': None}
    if plugin is not None:
        return plugin.review(state["study"], state["report"], cal,
                             ratings=state.get("ratings", {}), notes=state.get("notes", {}), kind="extract")
    checked = check(state["study"])
    rows, totals = ([], None) if checked["errors"] else register(state["study"], cal)
    return {"register": rows, "summary": totals, "check": checked, "measures": state["study"].get("measures", []),
            "score": None, "criteria": [], "proposed": {}, "ratings": {}, "sources": {}, "unrated": []}


def review_xlsx(result, plugin, directory):
    fd, path = tempfile.mkstemp(dir=directory, prefix=".export-", suffix=".xlsx")
    os.close(fd)
    try:
        plugin.to_xlsx(result, path, "Risk analysis review")
        return pathlib.Path(path).read_bytes()
    finally:
        os.unlink(path)


def derived_severity(st, cal, key, eid):
    """The severity the engine's checks accept for strategic scenario or risk `eid`, or None if they leave it open.

    The engine checks that a strategic scenario's severity is the highest of its feared events (guide p.49) and that
    a risk's severity is its scenario's, but it has no function that returns that value. So the app asks the
    engine's own validate(): it tries 1 to 4 on a copy and keeps the single value that raises no severity error for
    this element. The rule itself is never coded in the app. If the engine gains a function for it, only this
    function changes.
    """
    if key not in DERIVED_SEVERITY or not cal or structure_errors(st):
        return None
    probe = copy.deepcopy(st)
    hits = [x for x in probe.get(key) or [] if isinstance(x, dict) and x.get("id") == eid]
    if len(hits) != 1:
        return None
    el, prefix, ok = hits[0], f"{eid}: severity ", []
    for k in (1, 2, 3, 4):
        el["severity"] = k
        try:
            errs = study_mod.validate(probe, cal)["errors"]
        except Exception:  # a shape the engine does not expect: no value
            return None
        if not any(e.startswith(prefix) for e in errs):
            ok.append(k)
    return ok[0] if len(ok) == 1 else None


def severity_errors(chk, eid):
    """The engine's severity errors for one element, as the engine words them."""
    return [e for e in chk.get("errors", []) if e.startswith(f"{eid}: severity ")]


def take_severities(st, cal, only=None):
    """Store the engine-accepted severity on strategic scenarios, then on risks (they follow their scenario).

    `only` limits the change to one element id. Returns [(id, old, new)] for the values that changed.
    """
    changed = []
    for key in DERIVED_SEVERITY:
        for x in st.get(key) or []:
            if not isinstance(x, dict) or (only is not None and x.get("id") != only):
                continue
            v = derived_severity(st, cal, key, x.get("id"))
            if v is not None and x.get("severity") != v:
                changed.append((x.get("id"), x.get("severity"), v))
                x["severity"] = v
    return changed
