"""The only place the app talks to the engine. Levels, checks and registers all come from here."""
import os
import tempfile

from . import ENGINE_DIR  # noqa: F401  (puts the engine on sys.path)
from atelier_engine import calibration, study as study_mod  # noqa: E402

COLLECTIONS = list(study_mod.COLLECTIONS)
DEFAULT_CAL = "anssi-v1.5"
CalibrationError = calibration.CalibrationError


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


def level(cal, severity, likelihood):
    return calibration.level(cal, severity, likelihood)


def level_info(cal, name):
    return calibration.level_info(cal, name)


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
