"""Import a filled-in risk analysis spreadsheet (xlsx) into a study, for review.

Spreadsheets differ, so a *layout* (JSON) says where things are. The importer reads, never guesses: whatever it
cannot read is reported, and every value it read from a colour or mapped from free text is listed too.

What a layout can describe (all parts optional except the risk sheet):
  risks     one sheet, a header row, one risk per row (or a risk spread over merged rows, e.g. one row per
            linked measure). Columns are found by header text. Severity and likelihood may be numbers 1-4,
            scale codes or labels of the calibration. Levels may be text or only the cell's fill colour.
  measures  one sheet, a header row, one measure per row, status as free text mapped by rules.
  pictures  risk maps: grids with the severity labels across, the likelihood labels down and risk ids in the
            cells. Each picture is tied to a stage (initial, now, target) by text found in its title.

Layouts ship in <repo>/layouts/; private ones in ATELIER_PRIVATE_DIR/layouts/ win a name clash.
"""
import json
import pathlib
import re
import unicodedata

from . import calibration as cal_mod

PUBLIC_LAYOUTS = pathlib.Path(__file__).resolve().parents[2] / "layouts"
STAGES = ("initial", "now", "target")
DEFAULT_STATUS_RULES = [
    ["^(not started|to do|todo|planned|open)\\b", "planned"],
    ["^(ok|done|implemented|closed|complete[d]?)\\b", "done"],
    ["in progress|ongoing|on-going|partial", "in progress"],
    ["dropped|cancel|abandon|rejected|not applicable", "dropped"],
]
AXIS_WORDS = {"impact", "impacts", "severity", "gravite", "likelihood", "vraisemblance"}
FOOTNOTE = re.compile(r"\(\s*\d+\s*\)|\[\s*\d+\s*\]")  # "(1)", "(2)(4)", "[3]" note markers
ID_SPLIT = re.compile(r"[,;\n/]+")


class SpreadsheetError(ValueError):
    """The file cannot be read with this layout (wrong sheet, no header row, not an xlsx)."""


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ---------------------------------------------------------------- layouts

def _layout_dirs():
    p = cal_mod.private_dir()
    return ([p / "layouts"] if p else []) + [PUBLIC_LAYOUTS]


def layouts():
    out = {}
    for d in reversed(_layout_dirs()):
        if d.is_dir():
            for f in sorted(d.glob("*.json")):
                out[f.stem] = "private" if d != PUBLIC_LAYOUTS else "public"
    return out


def load_layout(layout_id):
    for d in _layout_dirs():
        f = d / f"{layout_id}.json"
        if f.is_file():
            lay = json.loads(f.read_text(encoding="utf-8"))
            lay.setdefault("id", layout_id)
            if "risks" not in lay or "columns" not in lay["risks"] or "id" not in lay["risks"]["columns"]:
                raise SpreadsheetError(f"layout {layout_id}: needs risks.columns.id")
            return lay
    raise SpreadsheetError(f"unknown layout '{layout_id}' (available: {', '.join(layouts()) or 'none'})")


# ---------------------------------------------------------------- workbook helpers

class _Sheet:
    """Cell access that sees merged cells: a merged range answers with its top-left value and fill."""

    def __init__(self, ws):
        self.ws = ws
        self.anchor = {}
        self.span = {}
        for rng in ws.merged_cells.ranges:
            top = (rng.min_row, rng.min_col)
            self.span[top] = (rng.min_row, rng.max_row, rng.min_col, rng.max_col)
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    self.anchor[(r, c)] = top

    def top(self, r, c):
        return self.anchor.get((r, c), (r, c))

    def value(self, r, c):
        v = self.ws.cell(*self.top(r, c)).value
        return None if v is None or (isinstance(v, str) and not v.strip()) else v

    def own_value(self, r, c):
        """Value only if (r, c) is not hidden inside someone else's merged range."""
        if self.top(r, c) != (r, c):
            return None
        return self.value(r, c)

    def fill(self, r, c):
        cell = self.ws.cell(*self.top(r, c))
        f = cell.fill
        if not f or f.fill_type != "solid":
            return None
        rgb = getattr(f.fgColor, "rgb", None)
        if not isinstance(rgb, str) or len(rgb) < 6 or getattr(f.fgColor, "type", "rgb") != "rgb":
            return None
        return rgb[-6:].upper()

    def rows_of(self, r, c):
        t = self.top(r, c)
        s = self.span.get(t)
        return (s[0], s[1]) if s else (r, r)

    def cols_of(self, r, c):
        t = self.top(r, c)
        s = self.span.get(t)
        return (s[2], s[3]) if s else (c, c)


def _find_sheet(wb, spec, what):
    names = spec.get("sheet")
    names = [names] if isinstance(names, str) else (names or [])
    for n in names:
        for ws in wb.worksheets:
            if _norm(ws.title) == _norm(n):
                return ws
    for n in names:
        for ws in wb.worksheets:
            if _norm(n) in _norm(ws.title):
                return ws
    raise SpreadsheetError(f"{what}: no sheet named {' or '.join(names) or '?'} (sheets: {', '.join(ws.title for ws in wb.worksheets)})")


def _header(sh, spec, what, max_scan=15):
    """Find the header row: the first row (within max_scan) where every required column header is found."""
    cols = spec["columns"]
    required = spec.get("required", ["id"])
    for r in range(1, min(sh.ws.max_row, max_scan) + 1):
        texts = {c: _norm(sh.own_value(r, c) or "") for c in range(1, sh.ws.max_column + 1)}
        found, used = {}, set()
        for exact in (True, False):
            for key, heads in cols.items():
                if key in found:
                    continue
                for h in [heads] if isinstance(heads, str) else heads:
                    hn = _norm(h)
                    hit = next((c for c, t in texts.items() if t and c not in used and
                                (t == hn if exact else t.startswith(hn + " "))), None)
                    if hit:
                        found[key] = hit
                        used.add(hit)
                        break
        if all(k in found for k in required):
            return r, found
    raise SpreadsheetError(f"{what}: header row not found (looked for {', '.join(str(cols[k]) for k in required)})")


# ---------------------------------------------------------------- value readers

class _Scales:
    def __init__(self, cal):
        self.cal = cal
        self.axis = {}
        for axis in ("severity", "likelihood"):
            m = {}
            for x in cal[axis]:
                for k in (x["n"], x.get("code"), x.get("label")):
                    if k is not None:
                        m[_norm(k)] = x["n"]
            self.axis[axis] = m
        self.level_by_name = {_norm(l["name"]): l["name"] for l in cal["levels"]}
        self.level_by_colour = {}
        for l in cal["levels"]:
            for col in [l.get("colour")] + list(l.get("colours", [])):
                if col:
                    self.level_by_colour[col.upper()[-6:]] = l["name"]

    def scale(self, axis, v):
        if v is None:
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer() and 1 <= v <= 4:
            return int(v)
        return self.axis[axis].get(_norm(v))

    def level(self, v, fill):
        """(level name, how) from cell text, else from the fill colour; (None, None) if neither reads."""
        if v is not None and not isinstance(v, (int, float)):
            n = self.level_by_name.get(_norm(v))
            if n:
                return n, "text"
        if fill and fill in self.level_by_colour:
            return self.level_by_colour[fill], "colour"
        return None, None


def _label_key(label):
    """Comparison key for two descriptions: no note markers, no case, accents or punctuation, no plural s."""
    words = _norm(FOOTNOTE.sub(" ", label or "")).split()
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words)


def _ids(v):
    if v is None:
        return []
    return [x.strip() for x in ID_SPLIT.split(str(v)) if x.strip()]


def _text(v):
    if v is None:
        return None
    if not isinstance(v, (str, int, float)):
        return None  # e.g. an array formula object with no cached value
    s = str(v).strip()
    return s or None


# ---------------------------------------------------------------- readers per part

def _read_risks(wb, lay, sc, rep):
    spec = lay["risks"]
    sh = _Sheet(_find_sheet(wb, spec, "risks"))
    hr, col = _header(sh, spec, "risks")
    rep["read"]["risks_sheet"] = sh.ws.title
    rep["read"]["risks_columns"] = sorted(col)
    risks, order, cur = {}, [], None
    blank_run = 0
    for r in range(hr + 1, sh.ws.max_row + 1):
        rid = _text(sh.own_value(r, col["id"])) if "id" in col else None
        in_merge = sh.top(r, col["id"]) != (r, col["id"])
        if rid:
            blank_run = 0
            if rid in risks:
                rep["errors"].append(f"risk {rid} appears twice in the register (row {r})")
                cur = None
                continue
            cur = {"id": rid, "_row": r}
            risks[rid] = cur
            order.append(rid)
            for key in ("label", "criterion", "owner", "treatment", "scenario"):
                if key in col:
                    t = _text(sh.value(r, col[key]))
                    if t:
                        cur[key] = t
            for key, axis in (("severity", "severity"), ("likelihood", "likelihood"),
                              ("likelihood_target", "likelihood"), ("likelihood_initial", "likelihood")):
                if key in col:
                    raw = sh.value(r, col[key])
                    v = sc.scale(axis, raw)
                    if v:
                        cur[key] = v
                    elif raw is not None:
                        rep["errors"].append(f"{rid}: {key} '{raw}' is not on the calibration's scale")
            for key, stage in (("level_initial", "initial"), ("level_now", "now"), ("level_target", "target")):
                if key in col:
                    raw, fill = sh.value(r, col[key]), sh.fill(r, col[key])
                    name, how = sc.level(raw, fill)
                    if name:
                        cur.setdefault("_shown", {})[stage] = (name, how)
                        if how == "colour":
                            rep["_colour_only"].add(key)
                    elif raw is not None or fill:
                        rep["notes"].append(f"{rid}: {key} cell not readable as a level (text {raw!r}, colour {fill})")
        elif cur is not None and (in_merge or any(sh.own_value(r, c) is not None for c in col.values())):
            blank_run = 0
        else:
            cur = None
            blank_run += 1
            if blank_run > 20:
                break
            continue
        if cur is not None and "measures" in col:
            for mid in _ids(_text(sh.own_value(r, col["measures"]))):
                cur.setdefault("_measures", [])
                if mid not in cur["_measures"]:
                    cur["_measures"].append(mid)
    return [risks[i] for i in order]


def _map_status(text, rules):
    t = _norm(text or "")
    for pat, status in rules:
        if re.search(pat, t):
            return status
    return None


def _read_measures(wb, lay, rep):
    spec = lay.get("measures")
    if not spec:
        return None
    try:
        sh = _Sheet(_find_sheet(wb, spec, "measures"))
        hr, col = _header(sh, spec, "measures")
    except SpreadsheetError as e:
        rep["notes"].append(f"{e}; measures read from the risk sheet only")
        return None
    rep["read"]["measures_sheet"] = sh.ws.title
    rules = spec.get("status_rules", DEFAULT_STATUS_RULES)
    out, blank_run = [], 0
    for r in range(hr + 1, sh.ws.max_row + 1):
        mid = _text(sh.own_value(r, col["id"]))
        if not mid:
            blank_run += 1
            if blank_run > 20:
                break
            continue
        blank_run = 0
        m = {"id": mid}
        for key in ("label", "owner", "due", "details"):
            if key in col:
                t = _text(sh.value(r, col[key]))
                if t:
                    m[key] = t
        raw = _text(sh.value(r, col["status"])) if "status" in col else None
        st = _map_status(raw, rules) if raw else None
        m["status"] = st or "planned"
        if raw:
            m["status_text"] = raw
        if raw and not st:
            rep["notes"].append(f"{mid}: status '{raw}' kept as text, counted as planned")
        out.append(m)
    return out


def _read_pictures(wb, lay, sc, rep):
    """{stage: {risk id: (severity, likelihood, cell colour)}} from every risk map the layout names."""
    specs = lay.get("pictures") or []
    out = {}
    if not specs:
        return out
    sheets = {}
    for spec in specs:
        try:
            ws = _find_sheet(wb, spec, "pictures")
        except SpreadsheetError as e:
            rep["notes"].append(str(e))
            continue
        sheets.setdefault(ws.title, (ws, []))[1].append(spec)
    for title, (ws, sp) in sheets.items():
        sh = _Sheet(ws)
        for grid in _grids(sh, sc):
            name = _norm(grid["title"] or "")
            stage = next((s["stage"] for s in sp if any(_norm(k) in name for k in
                          ([s["title_contains"]] if isinstance(s["title_contains"], str) else s["title_contains"]))), None)
            if stage is None:
                rep["notes"].append(f"risk map '{grid['title']}' on sheet {title}: no stage matches its title, skipped")
                continue
            if stage in out:
                rep["errors"].append(f"two risk maps for stage {stage}")
                continue
            cells = {}
            for (r, c), (sev, lik) in grid["cells"].items():
                for rid in _ids(_text(sh.own_value(r, c))):
                    if rid in cells:
                        rep["errors"].append(f"{rid} placed twice on the {stage} risk map")
                    cells[rid] = (sev, lik, sh.fill(r, c))
            out[stage] = cells
            rep["read"].setdefault("pictures", []).append({"stage": stage, "title": grid["title"], "risks": len(cells)})
    return out


def _grids(sh, sc):
    """Find risk maps: 4 severity labels on one row, the likelihood labels in a column to their left."""
    ws = sh.ws
    sev_axis, lik_axis = sc.axis["severity"], sc.axis["likelihood"]
    found = []
    for r in range(1, ws.max_row + 1):
        hits = []
        for c in range(1, ws.max_column + 1):
            v = sh.own_value(r, c)
            if v is not None and not isinstance(v, (int, float)) and _norm(v) in sev_axis:
                hits.append((c, sev_axis[_norm(v)]))
        run = []
        for c, n in hits:
            if run and n == run[-1][1] + 1 and c == sh.cols_of(r, run[-1][0])[1] + 1:
                run.append((c, n))
            else:
                if [x[1] for x in run] == [1, 2, 3, 4]:
                    found.append((r, run))
                run = [(c, n)]
        if [x[1] for x in run] == [1, 2, 3, 4]:
            found.append((r, run))
    grids = []
    for r, run in found:
        c0, c1 = run[0][0], sh.cols_of(r, run[-1][0])[1]
        colsev = {}
        for c, n in run:
            a, b = sh.cols_of(r, c)
            for x in range(a, b + 1):
                colsev[x] = n
        lik_rows, lik_col = {}, None
        for c in range(c0 - 1, max(0, c0 - 4), -1):
            rows = {}
            for rr in range(r + 1, min(ws.max_row, r + 60) + 1):
                v = sh.own_value(rr, c)
                if v is not None and not isinstance(v, (int, float)) and _norm(v) in lik_axis:
                    a, b = sh.rows_of(rr, c)
                    for x in range(a, b + 1):
                        rows[x] = lik_axis[_norm(v)]
            if len(set(rows.values())) == 4:
                lik_rows, lik_col = rows, c
                break
        if not lik_rows:
            continue
        title = None
        for rr in range(r - 1, 0, -1):
            for c in range(c0, c1 + 1):
                v = sh.value(rr, c)
                if isinstance(v, str) and _norm(v) not in sev_axis and len(_norm(v)) > 3 and _norm(v) not in AXIS_WORDS:
                    title = v.strip()
                    break
            if title:
                break
        cells = {}
        for rr, lik in lik_rows.items():
            for c, sev in colsev.items():
                if sh.top(rr, c) == (rr, c):
                    cells[(rr, c)] = (sev, lik)
        grids.append({"title": title, "header_row": r, "cells": cells})
    return grids


# ---------------------------------------------------------------- assembly

def read_xlsx(path, cal, layout=None, name=None):
    """Read a filled-in risk analysis. Returns {"study", "report"}; raises SpreadsheetError if it cannot be read.

    layout: a layout id, a layout dict, or None to try every available layout and keep the first that reads.
    """
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError("spreadsheet import needs openpyxl (pip install openpyxl)") from e
    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception as e:  # zip/xml errors of every kind: not a readable xlsx
        raise SpreadsheetError(f"not a readable .xlsx file ({type(e).__name__})") from e
    if layout is None:
        tried, best = [], None
        for lid in layouts():
            try:
                res = _assemble(wb, cal, load_layout(lid), path, name)
            except SpreadsheetError as e:
                tried.append(f"{lid}: {e}")
                continue
            rank = (len(res["report"]["errors"]), -len(res["report"]["read"].get("risks_columns", [])),
                    -len(res["report"]["read"].get("stages", [])))
            if best is None or rank < best[0]:
                best = (rank, res)
        if best is None:
            raise SpreadsheetError("no layout reads this file. " + " | ".join(tried))
        return best[1]
    lay = layout if isinstance(layout, dict) else load_layout(layout)
    return _assemble(wb, cal, lay, path, name)


def _assemble(wb, cal, lay, path, name):
    sc = _Scales(cal)
    rep = {"layout": lay.get("id"), "calibration": cal["id"], "read": {}, "errors": [], "notes": [],
           "findings": [], "_colour_only": set()}
    risks = _read_risks(wb, lay, sc, rep)
    if not risks:
        raise SpreadsheetError(f"layout {lay.get('id')}: header found but no risk rows")
    measures = _read_measures(wb, lay, rep)
    pics = _read_pictures(wb, lay, sc, rep)
    codes = {_norm(k): v for k, v in (lay.get("criterion_codes") or {}).items()}

    ids = {r["id"] for r in risks}
    for stage, cells in pics.items():
        for rid in sorted(set(cells) - ids):
            rep["findings"].append(f"{rid} is on the {stage} risk map but not in the register")

    out_risks = []
    for r in risks:
        rid = r["id"]
        row = {"id": rid}
        for k in ("label", "owner", "treatment"):
            if r.get(k):
                row[k] = r[k]
        if r.get("criterion"):
            row["criterion"] = codes.get(_norm(r["criterion"]), r["criterion"])
        sev_seen = {}
        for stage in STAGES:
            if rid in pics.get(stage, {}):
                sev, lik, fill = pics[stage][rid]
                sev_seen[stage] = sev
                key = {"initial": "likelihood_initial", "now": "likelihood", "target": "likelihood_target"}[stage]
                if r.get(key) and r[key] != lik:
                    rep["findings"].append(f"{rid}: {key.replace('_', ' ')} {r[key]} in the register, {lik} on the {stage} risk map")
                r.setdefault(key, lik)
                lvl = cal_mod.level(cal, sev, lik)
                shown, how = sc.level(None, fill)
                if fill and shown and shown != lvl:
                    rep["findings"].append(f"{rid}: {stage} risk map cell coloured {shown}, the grid gives {lvl}")
            elif pics.get(stage):
                rep["findings"].append(f"{rid} is missing from the {stage} risk map")
        if r.get("severity"):
            sev_seen["register"] = r["severity"]
        if len(set(sev_seen.values())) > 1:
            rep["findings"].append(f"{rid}: severity differs between " + ", ".join(f"{k} {v}" for k, v in sev_seen.items()))
        sev = r.get("severity") or sev_seen.get("now") or sev_seen.get("initial") or sev_seen.get("target")
        lik_now = r.get("likelihood") or r.get("likelihood_initial")
        if lik_now and not r.get("likelihood"):
            rep["notes"].append(f"{rid}: no current likelihood, the initial one is used")
        if sev:
            row["severity"] = sev
        else:
            rep["errors"].append(f"{rid}: severity not found (no column, no risk map)")
        if lik_now:
            row["likelihood"] = lik_now
        else:
            rep["errors"].append(f"{rid}: likelihood not found (no column, no risk map)")
        for k in ("likelihood_target", "likelihood_initial"):
            if r.get(k):
                row[k] = r[k]
        # levels shown in the register vs the grid
        for stage, (shown, how) in (r.get("_shown") or {}).items():
            lik = {"initial": row.get("likelihood_initial"), "now": row.get("likelihood"), "target": row.get("likelihood_target")}[stage]
            if sev and lik:
                lvl = cal_mod.level(cal, sev, lik)
                if shown != lvl:
                    rep["findings"].append(f"{rid}: {stage} level shown as {shown} ({how}), the grid gives {lvl}")
            elif stage == "target" and not row.get("likelihood_target"):
                row["level_target_shown"] = shown
        if r.get("_measures"):
            row["_measures"] = r["_measures"]
        out_risks.append(row)

    # measures: from the measures sheet, else from ids found on the risk sheet
    linked = {}
    for row in out_risks:
        for mid in row.pop("_measures", []):
            linked.setdefault(mid, []).append(row["id"])
    if measures is None:
        measures = [{"id": mid, "status": "planned"} for mid in linked]
        if linked:
            rep["notes"].append("no measures sheet: measures listed from the risk sheet, status unknown (planned)")
    by_id = {}
    for m in measures:
        if m["id"] in by_id:
            rep["errors"].append(f"measure {m['id']} appears twice")
            continue
        by_id[m["id"]] = m
        m["risks"] = linked.get(m["id"], [])
    for mid in sorted(set(linked) - set(by_id)):
        rep["findings"].append(f"{mid} is linked from {', '.join(linked[mid])} but not described on the measures sheet")
        by_id[mid] = {"id": mid, "status": "planned", "risks": linked[mid]}
    for m in by_id.values():
        if not m["risks"]:
            rep["findings"].append(f"{m['id']} is linked to no risk")
    seen = {}
    for m in by_id.values():
        key = _label_key(m.get("label"))
        if key and key in seen:
            o = seen[key]
            diff = f" with different status ({o.get('status_text') or o['status']} / {m.get('status_text') or m['status']})" \
                if (o.get("status_text") or o["status"]) != (m.get("status_text") or m["status"]) else ""
            rep["findings"].append(f"{o['id']} and {m['id']} have the same description{diff}")
        else:
            seen[key] = m

    colour_only = sorted(rep.pop("_colour_only"))
    if colour_only:
        rep["notes"].append("levels read from cell colour only (" + ", ".join(colour_only) + "): colour is lost in most exports")
    rep["read"].update({"risks": len(out_risks), "measures": len(by_id),
                        "stages": sorted(pics, key=STAGES.index)})
    nm = name or (pathlib.Path(str(path)).stem if not hasattr(path, "read") else "imported analysis")
    study = {"format": "atelier-study", "version": "0.1",
             "study": {"name": nm, "calibration": cal["id"], "source": f"imported from a spreadsheet (layout {lay.get('id')})",
                       "mode": "review"},
             "risks": out_risks, "measures": list(by_id.values())}
    return {"study": study, "report": rep}
