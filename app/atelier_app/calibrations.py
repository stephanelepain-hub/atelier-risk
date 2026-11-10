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
