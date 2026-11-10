"""Calibration lookup for the app: which calibrations exist, loading one, and the study's choice.

The engine adapter (engine.py) does the actual reading; this module is the one place the app asks about
calibrations, so another source (for example per-organisation calibrations) can be added here later.
"""
import os

from . import engine

DEFAULT = engine.DEFAULT_CAL
CalibrationError = engine.CalibrationError


def use_private_dir(path):
    """Point the engine at the private calibration directory (it reads ATELIER_PRIVATE_DIR at every call)."""
    os.environ["ATELIER_PRIVATE_DIR"] = str(path)


def available():
    """{id: "public" | "private"}."""
    return engine.calibrations()


def exists(cal_id):
    return isinstance(cal_id, str) and cal_id in available()


def load(cal_id):
    return engine.load_cal(cal_id)


def of_study(st):
    return engine.study_cal_id(st)


def kind(cal_id):
    """"public", "private", or None for a calibration the engine does not list."""
    return available().get(cal_id)


def catalogue():
    """Every calibration the engine lists, for the picker: [(id, kind, info)], public ones first.

    info = {"name", "levels" (count), "error"}; a calibration the engine refuses to load keeps its error.
    """
    out = []
    for cal_id, k in available().items():
        try:
            cal = load(cal_id)
            info = {"name": cal.get("name") or cal_id, "levels": len(cal.get("levels") or []), "error": None}
        except (CalibrationError, ValueError, OSError) as e:
            info = {"name": cal_id, "levels": 0, "error": str(e)}
        out.append((cal_id, k, info))
    out.sort(key=lambda x: (x[1] != "public", x[0]))
    return out


def study_privacy(st):
    """(private?, reason). A study is private when its calibration is a private one, when the user flagged it
    confidential, or when its calibration is not listed at all (fail safe: treated as private)."""
    meta = (st or {}).get("study") if isinstance(st, dict) else None
    meta = meta if isinstance(meta, dict) else {}
    k = kind(of_study(st))
    if k == "private":
        return True, "it uses a private calibration"
    if meta.get("confidential") is True:
        return True, "it is marked confidential"
    if k is None:
        return True, "its calibration is not available, so it is treated as private"
    return False, "public calibration, not marked confidential"
