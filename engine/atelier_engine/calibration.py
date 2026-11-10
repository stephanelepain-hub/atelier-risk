"""Calibrations: the settings of a qualitative 4x4 risk matrix (scales, levels, grid, acceptance).

A calibration is a JSON file. Public ones ship in <repo>/calibrations/. Private ones (an organisation's own
scales) live outside the repository, in the directory named by ATELIER_PRIVATE_DIR, and win on a name clash.
"""
import json
import os
import pathlib

PUBLIC_DIR = pathlib.Path(__file__).resolve().parents[2] / "calibrations"


class CalibrationError(ValueError):
    pass


def private_dir():
    d = os.environ.get("ATELIER_PRIVATE_DIR")
    return pathlib.Path(d) if d else None


def _dirs():
    p = private_dir()
    return ([p] if p else []) + [PUBLIC_DIR]


def available():
    out = {}
    for d in reversed(_dirs()):
        if d.is_dir():
            for f in sorted(d.glob("*.json")):
                out[f.stem] = "private" if d != PUBLIC_DIR else "public"
    return out


def load(cal_id):
    for d in _dirs():
        f = d / f"{cal_id}.json"
        if f.is_file():
            cal = json.loads(f.read_text(encoding="utf-8"))
            check(cal)
            return cal
    raise CalibrationError(f"unknown calibration '{cal_id}' (available: {', '.join(available()) or 'none'})")


def check(cal):
    """Structural check: 1-4 scales, a 4x4 grid of declared levels, never decreasing along either axis."""
    cid = cal.get("id", "?")
    levels = cal.get("levels") or []
    rank = {l["name"]: l["rank"] for l in levels}
    if len(rank) != len(levels) or not levels:
        raise CalibrationError(f"{cid}: levels missing or duplicated")
    if cal.get("map_orientation") not in (None, "severity-rows", "likelihood-rows"):
        raise CalibrationError(f"{cid}: map_orientation must be severity-rows or likelihood-rows")
    for k in ("severity", "likelihood"):
        if [x.get("n") for x in cal.get(k, [])] != [1, 2, 3, 4]:
            raise CalibrationError(f"{cid}: {k} scale must be 1-4")
    grid = cal.get("grid_by_severity") or {}
    if sorted(grid) != ["1", "2", "3", "4"]:
        raise CalibrationError(f"{cid}: grid must have severity rows 1-4")
    for s in "1234":
        row = grid[s]
        if len(row) != 4 or any(c not in rank for c in row):
            raise CalibrationError(f"{cid}: row {s} must hold 4 declared levels")
        if any(rank[row[i]] > rank[row[i + 1]] for i in range(3)):
            raise CalibrationError(f"{cid}: row {s} decreases as likelihood grows")
    for v in range(4):
        col = [rank[grid[s][v]] for s in "1234"]
        if any(col[i] > col[i + 1] for i in range(3)):
            raise CalibrationError(f"{cid}: likelihood column {v + 1} decreases as severity grows")
    return True


def scale_value(x, what):
    if isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= 4:
        raise CalibrationError(f"{what} must be an integer from 1 to 4, got {x!r}")
    return x


def level(cal, severity, likelihood):
    """Risk level name for a severity (impact) and a likelihood, both 1-4."""
    s = scale_value(severity, "severity")
    v = scale_value(likelihood, "likelihood")
    return cal["grid_by_severity"][str(s)][v - 1]


def level_info(cal, name):
    for l in cal["levels"]:
        if l["name"] == name:
            return l
    raise CalibrationError(f"{cal.get('id')}: no level '{name}'")


def label(cal, axis, n):
    for x in cal[axis]:
        if x["n"] == n:
            return x["label"]
    raise CalibrationError(f"{axis} {n} not in scale")
