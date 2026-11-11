"""The only place the app talks to the engine. Levels, checks and registers all come from here."""
import copy
import json
import os
import re
import tempfile

from . import ENGINE_DIR  # noqa: F401  (puts the engine on sys.path)
from atelier_engine import calibration, quick as quick_mod, study as study_mod  # noqa: E402

COLLECTIONS = list(study_mod.COLLECTIONS)
DEFAULT_CAL = "anssi-v1.5"
CalibrationError = calibration.CalibrationError


def calibrations():
    """{id: "public"}: the calibrations shipped in the repository's calibrations/ folder, and no others."""
    return {f.stem: "public" for f in sorted(calibration.PUBLIC_DIR.glob("*.json"))}


def load_cal(cal_id):
    """Read and check one published calibration. Nothing outside calibrations/ is ever read."""
    if cal_id not in calibrations():
        raise CalibrationError(f"unknown calibration '{cal_id}' (available: {', '.join(calibrations())})")
    cal = json.loads((calibration.PUBLIC_DIR / f"{cal_id}.json").read_text(encoding="utf-8"))
    calibration.check(cal)
    return cal


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
        cal = load_cal(cal_id)
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


def risk_map(rows, cal, stage, title, plain=False, lang=None, labelled_by=None):
    """Inline SVG from the engine; orientation belongs to the calibration.

    Treat colours as data, not SVG markup: the engine currently interpolates them into attributes.
    Match the CSS fallback for malformed colours without changing any level or the original calibration.
    """
    from atelier_engine import maps
    safe = copy.deepcopy(cal)
    for level in safe["levels"]:
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", str(level.get("colour") or "")):
            level["colour"] = "BBBBBB"
    if plain:  # quick-path pages: no method or calibration name under the map title (plain words)
        safe["name"] = ""
    return maps.svg(rows, safe, stage=stage, title=title, orientation=cal.get("map_orientation"), lang=lang,
                    labelled_by=labelled_by)


def level_name(cal, name, lang=None):
    """Display name of a level in the page language (English names when the calibration has them)."""
    return calibration.level_name(cal, name, lang)


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


def to_xlsx_bytes(st, cal, tmp_dir, notice=None, extra_sheets=None, lang=None):
    """Run the engine's Excel export into a private temp file and return the bytes."""
    from atelier_engine import export
    fd, path = tempfile.mkstemp(dir=tmp_dir, prefix=".export-", suffix=".xlsx")
    os.close(fd)
    try:
        export.to_xlsx(st, cal, path, notice=notice, extra_sheets=extra_sheets, lang=lang)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


# ---------- quick path (the engine's quick module; levels, confidence and the honesty statement come from there) ----------

QuickError = quick_mod.QuickError
HONESTY = quick_mod.HONESTY
DOWNTIME_KEYS = list(quick_mod.DOWNTIME)
SENSITIVITY_KEYS = list(quick_mod.SENSITIVITY)
LIKELIHOOD_KEYS = {"deliberate": list(quick_mod.LIKELIHOOD_DELIBERATE), "accidental": list(quick_mod.LIKELIHOOD_ACCIDENTAL)}
SEVERITY_WORDS = quick_mod.SEVERITY_WORDS
MAX_VALUES = quick_mod.MAX_VALUES
DOCUMENT_KINDS = quick_mod.DOCUMENT_KINDS
NO_DOCUMENT_CEILING = quick_mod.NO_DOCUMENT_CEILING


def quick_catalogue():
    return quick_mod.load_catalogue()


def quick_suggest(profile, cat):
    return quick_mod.suggest(profile, cat)


def quick_shortlist(profile, cat, limit=quick_mod.SHORTLIST_LIMIT):
    return quick_mod.shortlist(profile, cat, limit)


def quick_assess(quick, cat):
    return quick_mod.assess(quick, cat)


def quick_compute(quick, cal, cat):
    return quick_mod.compute(quick, cal, cat)


def quick_build(quick, cal, cat):
    return quick_mod.build_study(quick, cal, cat)


def quick_confidence(quick, cat):
    return quick_mod.confidence(quick, cat)


def quick_band(value):
    return quick_mod.confidence_band(value)


def quick_facts(quick, cal, cat):
    return quick_mod.facts(quick, cal, cat)


def quick_assumptions(quick, cal, cat):
    return quick_mod.assumptions(quick, cal, cat)


def quick_actions(quick, cal, cat, n=5):
    return quick_mod.top_actions(quick, cal, n, cat)


def quick_notice(quick, cal, cat):
    return quick_mod.xlsx_notice(quick, cal, cat)


def quick_sheets(quick, cal, cat):
    return quick_mod.xlsx_sheets(quick, cal, cat)


def quick_proposed_severity(rdef, profile):
    return quick_mod.propose_severity(rdef, profile)

