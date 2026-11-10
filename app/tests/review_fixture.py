"""Invented workbook and optional plugin. No real analysis or quality-grid text is used."""
import io
import json
import pathlib

STUB_PLUGIN = '''"""Synthetic review plugin for HTTP/UI tests only. Scores are fixed test values."""
from atelier_engine import study as study_mod
STATUSES = ("S", "P", "N", "NV", "NA")

def criteria():
    return {"grid": "synthetic-grid", "criteria": [
        {"id": f"C{i:02}", "axis": f"Axis {(i-1)//22+1}", "workshop": f"Workshop {(i-1)//11+1}",
         "text": f"Invented criterion {i}: confirm the evidence for the fictional organisation.",
         "appl": "all", "mode": "extract", "level": "test", "sentinel": False}
        for i in range(1, 67)]}

def propose(study, report, cal, kind="extract"):
    return {f"C{i:02}": {"status": "S", "why": "Synthetic evidence <example> & explanation"} for i in range(1,13)}

def review(study, report, cal, ratings=None, kind="extract", notes=None):
    ratings = ratings or {}
    for cid, status in ratings.items():
        if status not in STATUSES:
            raise ValueError("invalid status: " + status)
    proposed = propose(study, report, cal, kind)
    effective = {cid: p["status"] for cid, p in proposed.items()}
    effective.update(ratings)
    grid = criteria()
    unrated = [c["id"] for c in grid["criteria"] if c["id"] not in effective]
    rows = study_mod.register(study, cal) if not report["errors"] else []
    return {**grid, "register": rows, "summary": study_mod.summary(rows, cal),
            "check": study_mod.validate(study, cal), "measures": study.get("measures", []),
            "proposed": proposed, "ratings": effective, "notes": notes or {}, "unrated": unrated,
            "sources": {cid: "reviewer" if cid in ratings else "machine" for cid in effective},
            "score": None if unrated else {"final_score": 72, "confidence": 81,
                       "findings": {"major": ["Invented major finding"], "minor": ["Invented minor finding"]}}}

def to_xlsx(result, path, title):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name in ("Summary", "Findings", "Risk levels", "Measures", "Not checked"):
        ws = wb.create_sheet(name)
        ws.append([title])
    wb["Summary"].append(["Score", result["score"]["final_score"] if result["score"] else None])
    wb.save(path)
'''


def install_stub(private_dir):
    p = pathlib.Path(private_dir) / 'plugins' / 'atelier_private'
    p.mkdir(parents=True)
    (p / '__init__.py').write_text('')
    (p / 'review.py').write_text(STUB_PLUGIN)
    layouts = pathlib.Path(private_dir) / 'layouts'
    layouts.mkdir(exist_ok=True)
    # Extend a public layout only inside the throwaway fixture directory.
    source = pathlib.Path(__file__).resolve().parents[2] / 'layouts' / 'risk-register.json'
    layout = json.loads(source.read_text())
    layout['id'] = 'synthetic-register'
    layout['risks']['columns']['likelihood_initial'] = ['Initial likelihood']
    (layouts / 'synthetic-register.json').write_text(json.dumps(layout))


def workbook():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Risks'
    ws.append(['Risk ID', 'Description', 'Severity', 'Likelihood', 'Target likelihood', 'Initial likelihood', 'Measures', 'Owner', 'Treatment'])
    ws.append(['R1', 'Fictional workshop loses its invented orders <script>alert(1)</script>', 4, 3, 1, 4, 'M1', 'Operations', 'reduce'])
    ms = wb.create_sheet('Measures')
    ms.append(['Measure ID', 'Measure', 'Status', 'Owner', 'Due', 'Details'])
    ms.append(['M1', 'Synthetic daily recovery drill', 'planned', 'Operations', '2027-06-30', 'Invented evidence'])
    b = io.BytesIO()
    wb.save(b)
    wb.close()
    return b.getvalue()
