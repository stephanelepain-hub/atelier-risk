"""Command line. Every command prints JSON on stdout and exits 1 on error.

  python3 -m atelier_engine calibrations
  python3 -m atelier_engine grid     --cal anssi-v1.5
  python3 -m atelier_engine level    --cal anssi-v1.5 --severity 3 --likelihood 2
  python3 -m atelier_engine levels   --cal anssi-v1.5 risks.json    # [{id, severity, likelihood, likelihood_target?}]
  python3 -m atelier_engine validate study.json [--cal ID]           # calibration defaults to study.calibration
  python3 -m atelier_engine register study.json [--cal ID]
  python3 -m atelier_engine export   study.json out.xlsx [--cal ID]
  python3 -m atelier_engine map      study.json out.svg [--stage now|target|initial] [--cal ID] [--orientation O]
  python3 -m atelier_engine layouts
  python3 -m atelier_engine import   filled.xlsx --cal ID [--layout ID] [--out study.json]

Extra commands can be added by a plugin, if ATELIER_PRIVATE_DIR/plugins holds one.
"""
import argparse
import importlib
import json
import pathlib
import sys

from . import calibration, study as study_mod
from .importer import SpreadsheetError


def out(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    return code


def _plugin():
    d = calibration.private_dir()
    if not d or not (d / "plugins").is_dir():
        return None
    sys.path.insert(0, str(d / "plugins"))
    try:
        mod = importlib.import_module("atelier_private.cli")
    except ImportError:
        return None
    return mod if hasattr(mod, "register") and hasattr(mod, "run") else None


def _read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="atelier_engine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("calibrations")
    p = sp.add_parser("grid"); p.add_argument("--cal", required=True)
    p = sp.add_parser("level"); p.add_argument("--cal", required=True)
    p.add_argument("--severity", type=int, required=True); p.add_argument("--likelihood", type=int, required=True)
    p = sp.add_parser("levels"); p.add_argument("--cal", required=True); p.add_argument("file")
    for name in ("validate", "register"):
        p = sp.add_parser(name); p.add_argument("file"); p.add_argument("--cal")
    p = sp.add_parser("export"); p.add_argument("file"); p.add_argument("out"); p.add_argument("--cal")
    sp.add_parser("layouts")
    p = sp.add_parser("map"); p.add_argument("file"); p.add_argument("out"); p.add_argument("--cal")
    p.add_argument("--stage", default="now", choices=("now", "target", "initial"))
    p.add_argument("--orientation", choices=("severity-rows", "likelihood-rows"))
    p = sp.add_parser("import"); p.add_argument("file"); p.add_argument("--cal", required=True)
    p.add_argument("--layout"); p.add_argument("--out")
    plugin = _plugin()
    if plugin:
        plugin.register(sp)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "calibrations":
            return out(calibration.available())
        if a.cmd == "layouts":
            from . import importer
            return out(importer.layouts())
        if a.cmd == "import":
            from . import importer
            cal = calibration.load(a.cal)
            res = importer.read_xlsx(a.file, cal, a.layout)
            res["check"] = study_mod.validate(res["study"], cal)
            ok = not res["report"]["errors"] and not res["check"]["errors"]
            if ok:
                rows = study_mod.register(res["study"], cal)
                res["summary"] = study_mod.summary(rows, cal)
            if a.out:
                pathlib.Path(a.out).write_text(json.dumps(res["study"], ensure_ascii=False, indent=1), encoding="utf-8")
                res["written"] = a.out
                res.pop("study")
            return out(res, 0 if ok else 1)
        if plugin and a.cmd in getattr(plugin, "COMMANDS", ()):
            obj, code = plugin.run(a)
            return out(obj, code)
        if a.cmd in ("grid", "level", "levels"):
            cal = calibration.load(a.cal)
            if a.cmd == "grid":
                return out({"calibration": cal["id"], "levels": cal["levels"], "grid_by_severity": cal["grid_by_severity"]})
            if a.cmd == "level":
                n = calibration.level(cal, a.severity, a.likelihood)
                return out({"calibration": cal["id"], "severity": a.severity, "likelihood": a.likelihood, "level": n,
                            "acceptability": calibration.level_info(cal, n).get("acceptability", "")})
            rows = []
            for r in _read(a.file):
                row = dict(r, level=calibration.level(cal, r["severity"], r["likelihood"]))
                if r.get("likelihood_target") is not None:
                    row["level_target"] = calibration.level(cal, r["severity"], r["likelihood_target"])
                rows.append(row)
            return out({"calibration": cal["id"], "risks": rows, "summary": study_mod.summary(rows, cal)})
        st = _read(a.file)
        cal = calibration.load(a.cal or (st.get("study") or {}).get("calibration") or "anssi-v1.5")
        if a.cmd == "validate":
            r = study_mod.validate(st, cal)
            return out(dict(r, calibration=cal["id"]), 1 if r["errors"] else 0)
        check = study_mod.validate(st, cal)
        if check["errors"]:
            return out(dict(check, calibration=cal["id"]), 1)
        if a.cmd == "register":
            rows = study_mod.register(st, cal)
            return out({"calibration": cal["id"], "risks": rows, "summary": study_mod.summary(rows, cal), "warnings": check["warnings"]})
        if a.cmd == "map":
            from . import maps
            rows = study_mod.register(st, cal)
            pathlib.Path(a.out).write_text(maps.svg(rows, cal, a.stage, orientation=a.orientation), encoding="utf-8")
            return out({"written": a.out, "stage": a.stage, "placed": sum(len(v) for v in maps.placements(rows, a.stage).values()),
                        "calibration": cal["id"]})
        if a.cmd == "export":
            from . import export
            return out({"written": export.to_xlsx(st, cal, a.out), "calibration": cal["id"], "warnings": check["warnings"]})
    except (calibration.CalibrationError, SpreadsheetError, KeyError, TypeError, ValueError, FileNotFoundError, RuntimeError) as e:
        return out({"error": f"{type(e).__name__}: {e}"}, 1)


if __name__ == "__main__":
    sys.exit(main())
