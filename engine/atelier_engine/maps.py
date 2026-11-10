"""Risk maps: the calibration's 4x4 grid with each risk id placed in its cell, as SVG or as an Excel sheet.

The default orientation follows the ANSSI guide v1.5 figure (p.75): severity in rows (4 at the top),
likelihood in columns (1 on the left). A calibration may set "map_orientation"; an explicit argument wins.
orientation="likelihood-rows" swaps the axes (severity across, likelihood
down, 4 at the top), the shape many organisations' own risk pictures use.

`lang`: None (the default) keeps the calibration's own labels and the English axis names, as before. "en" uses the
calibration's optional English labels (`label_en`, `name_en`) when it has them; "fr" uses the original labels and
French axis names. The original labels stay the reference.
"""
from xml.sax.saxutils import escape

STAGES = {"initial": "likelihood_initial", "now": "likelihood", "target": "likelihood_target"}
ORIENTATIONS = ("severity-rows", "likelihood-rows")


def placements(rows, stage="now"):
    """{(severity, likelihood): [risk ids]} for one stage of a register (rows from study.register)."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    key = STAGES[stage]
    cells = {}
    for r in rows:
        s, v = r.get("severity"), r.get(key)
        if s and v:
            cells.setdefault((s, v), []).append(r["id"])
    return cells


AXIS_NAMES = {"en": ("Severity", "Likelihood"), "fr": ("Gravité", "Vraisemblance")}


def _layout(cal, orientation, lang=None):
    from . import calibration as cal_mod
    orientation = orientation or cal.get("map_orientation") or "severity-rows"
    if orientation not in ORIENTATIONS:
        raise ValueError(f"orientation must be one of {', '.join(ORIENTATIONS)}")
    sev = {x["n"]: cal_mod.label(cal, "severity", x["n"], lang) for x in cal["severity"]}
    lik = {x["n"]: cal_mod.label(cal, "likelihood", x["n"], lang) for x in cal["likelihood"]}
    sev_name, lik_name = AXIS_NAMES.get(lang, AXIS_NAMES["en"])
    if orientation == "severity-rows":
        return [(n, sev[n]) for n in (4, 3, 2, 1)], [(n, lik[n]) for n in (1, 2, 3, 4)], sev_name, lik_name, \
            (lambda row, col: (row, col))
    return [(n, lik[n]) for n in (4, 3, 2, 1)], [(n, sev[n]) for n in (1, 2, 3, 4)], lik_name, sev_name, \
        (lambda row, col: (col, row))


def _text_colour(rgb):
    r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
    return "000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "FFFFFF"


def svg(rows, cal, stage="now", title=None, orientation=None, lang=None, labelled_by=None):
    """Standalone SVG of the risk map for one stage. Text is escaped; no script, no external reference.
    `labelled_by`: id of an element of the page that already shows the map's title; the SVG then draws no title of
    its own (no visible title, no <title> element) and refers to that element with aria-labelledby."""
    from . import calibration as cal_mod
    cells = placements(rows, stage)
    row_axis, col_axis, row_name, col_name, to_sl = _layout(cal, orientation, lang)
    cw, ch, left, top = 150, 90, 150, (20 if labelled_by else 70)  # no title drawn: no room kept for it
    width, height = left + 4 * cw + 20, top + 4 * ch + 60
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'font-family="Helvetica, Arial, sans-serif" role="img"'
           + (f' aria-labelledby="{escape(labelled_by, {chr(34): "&quot;"})}"' if labelled_by else "") + '>']
    t = title or {"initial": "Initial risk map", "now": "Current risk map", "target": "Target risk map"}[stage]
    if not labelled_by:
        out.append(f'<title>{escape(t)}</title>')
        out.append(f'<text x="{left}" y="28" font-size="18" font-weight="bold">{escape(t)}</text>')
        out.append(f'<text x="{left}" y="50" font-size="12" fill="#555">{escape(cal.get("name", cal["id"]))}</text>')
    for i, (rn, rl) in enumerate(row_axis):
        y = top + i * ch
        out.append(f'<text x="{left - 8}" y="{y + ch / 2 + 4}" font-size="12" text-anchor="end">{escape(f"{rn} {rl}")}</text>')
        for j, (cn, _cl) in enumerate(col_axis):
            x = left + j * cw
            s, v = to_sl(rn, cn)
            level = cal_mod.level(cal, s, v)
            colour = (cal_mod.level_info(cal, level).get("colour") or "DDDDDD").upper()
            ids = cells.get((s, v), [])
            out.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="#{colour}" stroke="#FFFFFF" stroke-width="2">'
                       f'<title>{escape(f"{row_name} {rn}, {col_name} {cn}: {cal_mod.level_name(cal, level, lang)}")}</title></rect>')
            fg = _text_colour(colour)
            lines = [", ".join(ids[k:k + 3]) for k in range(0, len(ids), 3)]
            for k, line in enumerate(lines[:4]):
                out.append(f'<text x="{x + cw / 2}" y="{y + 22 + k * 16}" font-size="13" font-weight="bold" '
                           f'text-anchor="middle" fill="#{fg}">{escape(line)}</text>')
            if len(lines) > 4:
                out.append(f'<text x="{x + cw / 2}" y="{y + ch - 8}" font-size="11" text-anchor="middle" fill="#{fg}">'
                           f'+{len(ids) - 12} {"de plus" if lang == "fr" else "more"}</text>')
    for j, (cn, cl) in enumerate(col_axis):
        out.append(f'<text x="{left + j * cw + cw / 2}" y="{top + 4 * ch + 18}" font-size="12" text-anchor="middle">'
                   f'{escape(f"{cn} {cl}")}</text>')
    out.append(f'<text x="{left + 2 * cw}" y="{top + 4 * ch + 42}" font-size="13" text-anchor="middle" font-weight="bold">'
               f'{escape(col_name)}</text>')
    out.append(f'<text x="20" y="{top + 2 * ch}" font-size="13" font-weight="bold" '
               f'transform="rotate(-90 20 {top + 2 * ch})" text-anchor="middle">{escape(row_name)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def add_sheet(wb, rows, cal, stage="now", title=None, orientation=None, lang=None):
    """Add a risk-map worksheet (coloured cells, risk ids inside) to an openpyxl workbook. Returns the sheet."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from . import calibration as cal_mod
    cells = placements(rows, stage)
    row_axis, col_axis, row_name, col_name, to_sl = _layout(cal, orientation, lang)
    fr = lang == "fr"
    name = title or ({"initial": "Carte initiale", "now": "Carte maintenant", "target": "Carte après"} if fr else
                     {"initial": "Map initial", "now": "Map now", "target": "Map target"})[stage]
    ws = wb.create_sheet(name[:31])
    ws["A1"] = ({"initial": "Carte des risques initiale", "now": "Carte des risques actuelle", "target": "Carte des risques cible"} if fr else
                {"initial": "Initial risk map", "now": "Current risk map", "target": "Target risk map"})[stage]
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (f"{row_name} en lignes, {col_name} en colonnes. Calibration : {cal['id']}" if fr else
                f"{row_name} down, {col_name} across. Calibration: {cal['id']}")
    centre = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, (rn, rl) in enumerate(row_axis):
        r = 4 + i
        ws.cell(r, 1, f"{rn} {rl}").alignment = centre
        ws.row_dimensions[r].height = 60
        for j, (cn, _cl) in enumerate(col_axis):
            s, v = to_sl(rn, cn)
            level = cal_mod.level(cal, s, v)
            colour = (cal_mod.level_info(cal, level).get("colour") or "DDDDDD").upper()
            c = ws.cell(r, 2 + j, ", ".join(cells.get((s, v), [])) or None)
            c.fill = PatternFill("solid", fgColor=colour)
            c.alignment = centre
            c.font = Font(bold=True, color=_text_colour(colour))
    for j, (cn, cl) in enumerate(col_axis):
        ws.cell(8, 2 + j, f"{cn} {cl}").alignment = centre
    ws.cell(9, 2, col_name).font = Font(bold=True)
    ws.cell(3, 1, row_name).font = Font(bold=True)
    ws.column_dimensions["A"].width = 24
    for col in "BCDE":
        ws.column_dimensions[col].width = 22
    legend = 11
    ws.cell(legend, 1, "Niveaux" if fr else "Levels").font = Font(bold=True)
    for k, l in enumerate(sorted(cal["levels"], key=lambda l: -l["rank"])):
        c = ws.cell(legend + 1 + k, 1, cal_mod.level_name(cal, l["name"], lang))
        if l.get("colour"):
            c.fill = PatternFill("solid", fgColor=l["colour"])
            c.font = Font(color=_text_colour(l["colour"].upper()))
        ws.cell(legend + 1 + k, 2, cal_mod.level_text(cal, l["name"], "acceptability", lang))
    return ws
