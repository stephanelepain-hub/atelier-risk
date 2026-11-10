"""Excel export of a study: the risk register (coloured levels), risk maps (now, target, initial when present),
then one sheet per workshop object."""
from . import calibration as cal_mod
from . import study as study_mod

SHEETS = [("Feared events", "feared_events"), ("Risk origins", "risk_origins"), ("Stakeholders", "stakeholders"),
          ("Strategic scenarios", "strategic_scenarios"), ("Operational scenarios", "operational_scenarios"),
          ("Measures", "measures"), ("Business values", "business_values"), ("Supporting assets", "supporting_assets"),
          ("Baseline", "baseline")]


def _cell(v):
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) if not isinstance(x, dict) else x.get("id", str(x)) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}: {x}" for k, x in v.items())
    return v


def to_xlsx(study, cal, path, orientation=None):
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as e:  # optional dependency
        raise RuntimeError("xlsx export needs openpyxl (pip install openpyxl)") from e
    head = PatternFill("solid", fgColor="1F3864")
    wrap = Alignment(wrap_text=True, vertical="top")
    colour = {l["name"]: l.get("colour") for l in cal["levels"]}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Risk register"
    rows = study_mod.register(study, cal)
    cols = ["id", "label", "severity", "likelihood", "level", "acceptability", "likelihood_target", "level_target", "treatment", "owner", "measures"]
    ws.append(cols)
    for r in rows:
        ws.append([_cell(r.get(c)) for c in cols])
        for c in ("level", "level_target"):
            name = r.get(c)
            if name and colour.get(name):
                ws.cell(ws.max_row, cols.index(c) + 1).fill = PatternFill("solid", fgColor=colour[name])
    from . import maps
    for stage, key in (("now", "level"), ("target", "level_target"), ("initial", "level_initial")):
        if any(r.get(key) for r in rows):
            maps.add_sheet(wb, rows, cal, stage, orientation=orientation)
    for key, title in SHEETS:
        items = study.get(title) or []
        if not items:
            continue
        sh = wb.create_sheet(key)
        fields = list(dict.fromkeys(k for x in items for k in x))
        sh.append(fields)
        for x in items:
            sh.append([_cell(x.get(f)) for f in fields])
    for sh in wb.worksheets:
        if sh.title.startswith("Map "):
            continue
        for c in sh[1]:
            c.fill = head
            c.font = Font(bold=True, color="FFFFFF")
        for col in sh.columns:
            width = min(60, max(10, *(len(str(c.value or "")) for c in col)))
            sh.column_dimensions[col[0].column_letter].width = width
            for c in col[1:]:
                c.alignment = wrap
        sh.freeze_panes = "A2"
    info = wb.create_sheet("About")
    info.append(["Study", (study.get("study") or {}).get("name", "")])
    info.append(["Calibration", cal["id"]])
    info.append(["Calibration source", cal.get("source", "")])
    for l in sorted(cal["levels"], key=lambda l: -l["rank"]):
        info.append([l["name"], l.get("acceptability", ""), l.get("action", "")])
    wb.save(path)
    return path
