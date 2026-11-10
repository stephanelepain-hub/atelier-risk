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


def to_xlsx(study, cal, path, orientation=None, notice=None, extra_sheets=None):
    """Write the study to an Excel workbook. `notice` (a list of text lines) is written at the top of the first
    sheet, above the register, as a header; `extra_sheets` is [(title, [rows])] appended before the About sheet."""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
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
    for line in notice or []:
        ws.append([line])
        ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=len(cols))
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[ws.max_row].height = 18 * (1 + len(line) // 150)
    if notice:
        ws.append([None])
    ws.append(cols)
    header_row = ws.max_row
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
    for title, table in extra_sheets or []:
        sh = wb.create_sheet(title[:31])
        for row in table:
            sh.append(list(row))
    for sh in wb.worksheets:
        if sh.title.startswith("Map "):
            continue
        top = header_row if sh is ws else 1
        for c in sh[top]:
            c.fill = head
            c.font = Font(bold=True, color="FFFFFF")
        for col in sh.columns:
            cells = [c for c in col if c.row >= top]
            width = min(60, max(10, *(len(str(c.value or "")) for c in cells)))
            sh.column_dimensions[get_column_letter(col[0].column)].width = width
            for c in cells[1:]:
                c.alignment = wrap
        sh.freeze_panes = f"A{top + 1}"
    info = wb.create_sheet("About")
    info.append(["Study", (study.get("study") or {}).get("name", "")])
    info.append(["Calibration", cal["id"]])
    info.append(["Calibration source", cal.get("source", "")])
    for l in sorted(cal["levels"], key=lambda l: -l["rank"]):
        info.append([l["name"], l.get("acceptability", ""), l.get("action", "")])
    wb.save(path)
    return path
