"""Calibration lookup for the app: the public edition uses the published calibration (anssi-v1.5) only.

The engine adapter (engine.py) does the actual reading; this module is the one place the app asks about
calibrations.
"""
from . import engine

DEFAULT = engine.DEFAULT_CAL
CalibrationError = engine.CalibrationError


def available():
    """{id: "public"}: the calibrations shipped in calibrations/."""
    return engine.calibrations()


def exists(cal_id):
    return isinstance(cal_id, str) and cal_id in available()


def load(cal_id):
    if not exists(cal_id):
        raise CalibrationError(f"unknown calibration '{cal_id}'")
    return engine.load_cal(cal_id)


def of_study(st):
    return engine.study_cal_id(st)
