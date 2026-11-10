"""Server-rendered HTML. Every piece of study or user text goes through esc(). No inline script or style."""
import datetime
import html
import re
import urllib.parse

from . import calibrations, engine

FIELDS = {
    "business_values": ["id", "label", "nature", "owner"],
    "supporting_assets": ["id", "label", "business_values"],
    "feared_events": ["id", "business_value", "label", "criterion", "severity"],
    "baseline": ["id", "reference", "status", "gap"],
    "risk_origins": ["id", "origin", "objective", "motivation", "resources", "decision", "feared_events"],
    "stakeholders": ["id", "name", "category", "dependence", "penetration", "maturity", "trust", "critical"],
    "strategic_scenarios": ["id", "risk_origin", "feared_events", "severity", "paths"],
    "operational_scenarios": ["id", "strategic_scenario", "path", "likelihood", "description"],
    "risks": ["id", "strategic_scenario", "operational_scenario", "label", "severity", "likelihood",
              "likelihood_target", "treatment", "owner"],
    "measures": ["id", "label", "risks", "owner", "due", "status"],
}
TITLES = {
    "business_values": "Business values", "supporting_assets": "Supporting assets",
    "feared_events": "Feared events", "baseline": "Security baseline", "risk_origins": "Risk origins and objectives",
    "stakeholders": "Ecosystem stakeholders", "strategic_scenarios": "Strategic scenarios",
    "operational_scenarios": "Operational scenarios", "risks": "Risks", "measures": "Security measures",
}
WORKSHOPS = {
    1: ("Workshop 1: scope and security baseline", ["business_values", "supporting_assets", "feared_events", "baseline"]),
    2: ("Workshop 2: risk origins", ["risk_origins"]),
    3: ("Workshop 3: strategic scenarios", ["stakeholders", "strategic_scenarios"]),
    4: ("Workshop 4: operational scenarios", ["operational_scenarios"]),
    5: ("Workshop 5: risk treatment", ["risks", "measures"]),
}
WORKSHOP_OF = {c: n for n, (_, cs) in WORKSHOPS.items() for c in cs}
FLASH = {
    "saved": "Saved. The checks below were recomputed by the engine.",
    "added": "Added. The checks below were recomputed by the engine.",
    "deleted": "Deleted. The checks below were recomputed by the engine.",
    "created": "Study created.",
    "imported": "Study imported and checked by the engine.",
    "example": "The guide example was loaded as a new study.",
    "renamed": "Saved.",
    "duplicated": "Duplicate created.",
    "removed": "Study moved to the trash folder.",
    "synced": "Severities taken from the engine. The checks below were recomputed.",
    "unchanged": "The engine's severities were already stored; nothing changed.",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-/]+")


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def q(x):
    return urllib.parse.quote(str(x), safe="")


def anchor(eid):
    return "el-" + q(eid)


def when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def level_classes(cal):
    """Level name -> CSS class (by rank order). The colours themselves come from /cal/<id>.css."""
    if not cal:
        return {}
    return {l["name"]: f"lvl-i{i}" for i, l in enumerate(sorted(cal["levels"], key=lambda l: l["rank"]))}


def scale_text(cal, axis, n, long=True):
    if not cal or isinstance(n, bool) or not isinstance(n, int):
        return esc(n)
    for x in cal.get(axis, []):
        if x.get("n") == n:
            return esc(f"{x.get('code', n)} {x.get('label', '')}" if long else x.get("code", n))
    return esc(n)


def csrf_input(session):
    return f'<input type="hidden" name="csrf" value="{esc(session.csrf)}">' if session else ""


def badge(chk):
    if chk["errors"]:
        n = len(chk["errors"])
        return f'<span class="badge bad">{n} error{"s" if n > 1 else ""}</span>'
    if chk["warnings"]:
        n = len(chk["warnings"])
        return f'<span class="badge warn">{n} warning{"s" if n > 1 else ""}</span>'
    return '<span class="badge ok">valid</span>'


def page(title, body, session=None, cal_id=None, flash=""):
    cal_css = f'<link rel="stylesheet" href="/cal/{q(cal_id)}.css">' if cal_id else ""
    logout = ""
    if session:
        logout = (f'<form method="post" action="/logout" class="inline">{csrf_input(session)}'
                  '<button class="link">Log out</button></form>')
    note = f'<p class="flash" role="status">{esc(FLASH[flash])}</p>' if flash in FLASH else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} - Atelier</title>
<link rel="stylesheet" href="/static/app.css">
{cal_css}
<script src="/static/app.js" defer></script>
</head>
<body>
<header class="top"><a class="brand" href="/">Atelier</a><span class="sub">EBIOS Risk Manager workbench</span>
<nav><a href="/">Studies</a>{logout}</nav></header>
<main>
{note}
{body}
</main>
</body>
</html>
"""


def error_page(status, message, session=None):
    body = f'<h1>{status}</h1><p>{esc(message)}</p><p><a href="/">Back to the studies</a></p>'
    return page(f"Error {status}", body, session)


def login_page(pre, message=""):
    msg = f'<p class="error">{esc(message)}</p>' if message else ""
    body = f"""<section class="card narrow">
<h1>Log in</h1>
{msg}
<p>Paste the login token. It is in the <code>token</code> file of the data directory, readable by your user only.</p>
<form method="post" action="/login">
<input type="hidden" name="pre" value="{esc(pre)}">
<label>Token <input type="password" name="token" autocomplete="current-password" required autofocus></label>
<button>Log in</button>
</form>
</section>"""
    return page("Log in", body)


# ---------- study list ----------

def study_list(rows, cals, session, flash=""):
    trs = []
    for sid, st, mtime, chk in rows:
        meta = (st or {}).get("study") if isinstance(st, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        name = meta.get("name") or "(no name)"
        trs.append(f"""<tr>
<td><a href="/s/{sid}">{esc(name)}</a></td>
<td>{esc(chk["calibration"])}</td>
<td class="nowrap">{when(mtime)}</td>
<td>{badge(chk)}</td>
<td class="actions"><a href="/s/{sid}">Open</a>
<form method="post" action="/s/{sid}/duplicate" class="inline">{csrf_input(session)}<button class="link">Duplicate</button></form>
<a href="/s/{sid}/delete" class="danger">Delete</a></td>
</tr>""")
    table = ("<p class=\"empty\">No study yet. Create one, import a study file or load the guide example.</p>" if not trs else
             "<table class=\"list\"><thead><tr><th>Name</th><th>Calibration</th><th>Last modified</th><th>Checks</th>"
             "<th>Actions</th></tr></thead><tbody>" + "".join(trs) + "</tbody></table>")
    opts = "".join(f'<option value="{esc(c)}"{" selected" if c == calibrations.DEFAULT else ""}>{esc(c)} ({esc(k)})</option>'
                   for c, k in sorted(cals.items()))
    body = f"""<h1>Studies</h1>
{table}
<div class="cards">
<section class="card">
<h2>New study</h2>
<form method="post" action="/new">{csrf_input(session)}
<label>Name <input name="name" required maxlength="200"></label>
<label>Scope <textarea name="scope" rows="3" maxlength="4000"></textarea></label>
<label>Calibration <select name="calibration">{opts}</select></label>
<button>Create</button>
</form>
</section>
<section class="card">
<h2>Import a study file</h2>
<form method="post" action="/import" enctype="multipart/form-data">{csrf_input(session)}
<label>Study JSON (atelier-study format, 5 MB at most) <input type="file" name="file" accept=".json,application/json" required></label>
<button>Import</button>
</form>
<h2>Guide example</h2>
<p>The worked example of the ANSSI guide v1.5 (risks R1-R5 of its initial risk map).</p>
<form method="post" action="/example">{csrf_input(session)}<button>Load example</button></form>
</section>
</div>"""
    return page("Studies", body, session, flash=flash)


def import_errors(name, errors, session):
    lis = "".join(f"<li>{esc(e)}</li>" for e in errors)
    body = f"""<h1>Import refused</h1><p>The file <code>{esc(name)}</code> was not imported.</p>
<ul class="checks">{lis}</ul><p><a href="/">Back to the studies</a></p>"""
    return page("Import refused", body, session)


# ---------- study pages ----------

def element_index(st):
    """id -> (collection, workshop) for every element and every attack path."""
    idx = {}
    for key in engine.COLLECTIONS:
        for x in st.get(key) or []:
            if isinstance(x, dict) and isinstance(x.get("id"), str):
                idx.setdefault(x["id"], (key, WORKSHOP_OF.get(key, 1)))
                if key == "strategic_scenarios":
                    for p in x.get("paths") or []:
                        if isinstance(p, dict) and isinstance(p.get("id"), str):
                            idx.setdefault(p["id"], (key, 3))
    return idx


def find_target(msg, idx):
    """The first study element a check message names (messages start with the element id)."""
    for tok in TOKEN_RE.findall(msg):
        for part in [tok] + tok.split("/")[::-1]:
            part = part.rstrip(".,")
            if part in idx:
                return part
    return None


def message_target(msg, idx):
    """(element id or None, workshop number or None) for one engine message.

    Messages name their element first ("SS1: ..."); a path is "SS1/SS1-P2: ...". Messages about a whole
    collection ("risks: element without id") point at its workshop; header messages at the overview (None).
    """
    t = find_target(msg, idx)
    if t:
        return t, idx[t][1]
    head = msg.split(":", 1)[0].strip()
    if head in WORKSHOP_OF:
        return None, WORKSHOP_OF[head]
    return None, None


def locate_url(sid, eid, n):
    if n is None:
        return f"/s/{sid}"
    if eid is None:
        return f"/s/{sid}/w{n}"
    return f"/s/{sid}/w{n}?hl={q(eid)}#{anchor(eid)}"


def progress(st, chk, idx):
    """Per workshop: number of objects, and the engine's errors and warnings that point into it."""
    out = {n: {"objects": sum(len([x for x in st.get(k) or [] if isinstance(x, dict)]) for k in keys),
               "errors": 0, "warnings": 0} for n, (_, keys) in WORKSHOPS.items()}
    out["other"] = {"objects": 0, "errors": 0, "warnings": 0}
    for kind, msgs in (("errors", chk["errors"]), ("warnings", chk["warnings"])):
        for m in msgs:
            _, n = message_target(m, idx)
            out[n if n in out else "other"][kind] += 1
    return out


def checks_panel(sid, chk, idx):
    def items(msgs, cls):
        out = []
        for m in msgs:
            t, n = message_target(m, idx)
            if t:
                link = f' <a class="goto" href="/s/{sid}/el/{q(t)}">{esc(t)} in W{n}</a>'
            elif n:
                link = f' <a class="goto" href="/s/{sid}/w{n}">W{n}</a>'
            else:
                link = f' <a class="goto" href="/s/{sid}">overview</a>'
            out.append(f'<li class="{cls}">{esc(m)}{link}</li>')
        return "".join(out)
    if not chk["errors"] and not chk["warnings"]:
        content = '<p class="ok">No error, no warning.</p>'
    else:
        content = f'<ul class="checks">{items(chk["errors"], "err")}{items(chk["warnings"], "wrn")}</ul>'
    return f"""<aside class="checks-panel" id="checks"><h2>Checks {badge(chk)}</h2>
<p class="hint">Computed by the engine after every save.</p>{content}</aside>"""


def study_shell(sid, st, chk, active, content, session, flash=""):
    meta = st.get("study") if isinstance(st.get("study"), dict) else {}
    tabs = [("overview", "Overview", f"/s/{sid}")] + [
        (f"w{n}", f"W{n}", f"/s/{sid}/w{n}") for n in WORKSHOPS] + [
        ("register", "Register and grid", f"/s/{sid}/register")]
    cur = ' class="active" aria-current="page"'
    nav = "".join(f'<a href="{href}"{cur if key == active else ""}>{esc(label)}</a>' for key, label, href in tabs)
    body = f"""<div class="study-head"><h1>{esc(meta.get("name") or "(no name)")}</h1>
<span class="cal">calibration {esc(chk["calibration"])}</span></div>
<nav class="tabs">{nav}</nav>
<div class="study-body"><div class="study-main">{content}</div>{checks_panel(sid, chk, element_index(st))}</div>"""
    return page(meta.get("name") or "Study", body, session, cal_id=chk["calibration"] if chk.get("cal") else None,
                flash=flash)


def overview(sid, st, chk, mtime, session, flash=""):
    meta = st.get("study") if isinstance(st.get("study"), dict) else {}
    counts = "".join(f"<tr><td>W{WORKSHOP_OF[k]}</td><td>{esc(TITLES[k])}</td><td>{len(st.get(k) or [])}</td></tr>"
                     for k in engine.COLLECTIONS)
    prog = progress(st, chk, element_index(st))
    cells = []
    for n in WORKSHOPS:
        p = prog[n]
        state = "bad" if p["errors"] else ("warn" if p["warnings"] else ("ok" if p["objects"] else "none"))
        cells.append(f'<li class="ps-{state}"><a href="/s/{sid}/w{n}"><b>W{n}</b>'
                     f'<span class="ps-n">{p["objects"]} object{"s" if p["objects"] != 1 else ""}</span>'
                     f'<span class="ps-c">{p["errors"]} error{"s" if p["errors"] != 1 else ""}, '
                     f'{p["warnings"]} warning{"s" if p["warnings"] != 1 else ""}</span></a></li>')
    o = prog["other"]
    other = (f'<p class="hint">Not tied to a workshop: {o["errors"]} error(s), {o["warnings"]} warning(s).</p>'
             if o["errors"] or o["warnings"] else "")
    strip = (f'<section class="card"><h2>Study progress</h2><ol class="progress" id="progress">{"".join(cells)}</ol>'
             f'{other}<p class="hint">Errors and warnings are the engine\'s checks, counted by the workshop of the '
             f'element they name.</p></section>')
    extra = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in meta.items()
                    if k not in ("name", "scope", "calibration"))
    content = f"""{strip}<section class="card">
<h2>Study</h2>
<table class="kv"><tr><th>Scope</th><td class="pre">{esc(meta.get("scope", ""))}</td></tr>
<tr><th>Calibration</th><td>{esc(chk["calibration"])}</td></tr>
<tr><th>Last modified</th><td>{when(mtime)}</td></tr>{extra}</table>
<form method="post" action="/s/{sid}/rename">{csrf_input(session)}
<label>Name <input name="name" value="{esc(meta.get("name", ""))}" required maxlength="200"></label>
<label>Scope <textarea name="scope" rows="3" maxlength="4000">{esc(meta.get("scope", ""))}</textarea></label>
<button>Save</button></form>
</section>
<section class="card">
<h2>Contents</h2>
<table class="list"><thead><tr><th>Workshop</th><th>Object</th><th>Count</th></tr></thead><tbody>{counts}</tbody></table>
</section>
<section class="card">
<h2>Export and manage</h2>
<p><a class="button" href="/s/{sid}/export.json">Download study JSON</a>
<a class="button" href="/s/{sid}/export.xlsx">Download Excel (engine export)</a></p>
<form method="post" action="/s/{sid}/duplicate" class="inline">{csrf_input(session)}<button>Duplicate</button></form>
<a class="button danger" href="/s/{sid}/delete">Delete</a>
</section>"""
    return study_shell(sid, st, chk, "overview", content, session, flash)


def cell(key, v, sid, idx, cal):
    if key in ("severity",) and isinstance(v, int):
        return scale_text(cal, "severity", v)
    if key in ("likelihood", "likelihood_target") and isinstance(v, int):
        return scale_text(cal, "likelihood", v)
    if isinstance(v, str) and v in idx and key != "id":
        return f'<a href="/s/{sid}/el/{q(v)}">{esc(v)}</a>'
    if isinstance(v, list):
        if all(isinstance(x, dict) for x in v):
            lis = []
            for p in v:
                pid = p.get("id")
                rest = ", ".join(f"{k}: {x}" for k, x in p.items() if k not in ("id", "label", "stakeholder"))
                sh = p.get("stakeholder")
                shl = f' <span class="via">via <a href="/s/{sid}/el/{q(sh)}">{esc(sh)}</a></span>' if sh in idx else (
                    f' <span class="via">via {esc(sh)}</span>' if sh else "")
                lis.append(f'<li id="{anchor(pid)}"><b>{esc(pid)}</b> {esc(p.get("label", ""))}{shl}'
                           f'{" <small>" + esc(rest) + "</small>" if rest else ""}</li>')
            return f'<ul class="paths">{"".join(lis)}</ul>'
        return ", ".join(cell(key, x, sid, idx, cal) for x in v)
    if isinstance(v, dict):
        return esc(", ".join(f"{k}: {x}" for k, x in v.items()))
    if isinstance(v, bool):
        return "yes" if v else "no"
    return esc(v)


def read_table(sid, st, key, cal, idx, actions=None, hl=None):
    items = [x for x in st.get(key) or [] if isinstance(x, dict)]
    if not items:
        return '<p class="empty">None.</p>'
    cols = list(FIELDS.get(key, [])) + [k for k in dict.fromkeys(k for x in items for k in x) if k not in FIELDS.get(key, [])]
    cols = [c for c in cols if any(c in x for x in items)] or ["id"]
    head = "".join(f"<th>{esc(c.replace('_', ' '))}</th>" for c in cols) + ("<th></th>" if actions else "")
    trs = []
    for x in items:
        tds = "".join(f"<td>{cell(c, x.get(c), sid, idx, cal)}</td>" for c in cols)
        act = f'<td class="actions">{actions(x)}</td>' if actions else ""
        cls = ' class="hl"' if hl is not None and x.get("id") == hl else ""
        trs.append(f'<tr id="{anchor(x.get("id", ""))}"{cls}>{tds}{act}</tr>')
    return f'<div class="scroll"><table class="list"><thead><tr>{head}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


# ---------- workshop 1 editor ----------

W1 = {"bv": "business_values", "sa": "supporting_assets", "fe": "feared_events", "bl": "baseline"}
W1_PREFIX = {"business_values": "BV", "supporting_assets": "SA", "feared_events": "FE", "baseline": "BL"}
NATURES = ["process", "information"]
BASELINE_STATUS = ["applied", "partial", "not applied"]
CRITERIA = ["confidentiality", "integrity", "availability"]


def _select(name, options, current, required=False, blank="(none)"):
    opts = [] if required else [f'<option value="">{esc(blank)}</option>']
    for value, label in options:
        sel = " selected" if str(value) == str(current if current is not None else "") else ""
        opts.append(f'<option value="{esc(value)}"{sel}>{esc(label)}</option>')
    req = " required" if required else ""
    return f'<select name="{name}"{req}>{"".join(opts)}</select>'


def w1_form_fields(key, el, st, cal):
    el = el or {}
    bvs = [(b["id"], f'{b["id"]} {b.get("label", "")}') for b in st.get("business_values") or []
           if isinstance(b, dict) and b.get("id")]
    if key == "business_values":
        return f"""<label>Label <input name="label" value="{esc(el.get("label", ""))}" required maxlength="500"></label>
<label>Nature {_select("nature", [(n, n) for n in NATURES], el.get("nature"))}</label>
<label>Owner <input name="owner" value="{esc(el.get("owner", ""))}" maxlength="200"></label>"""
    if key == "supporting_assets":
        cur = set(el.get("business_values") or [])
        boxes = "".join(f'<label class="check"><input type="checkbox" name="business_values" value="{esc(i)}"'
                        f'{" checked" if i in cur else ""}> {esc(lab)}</label>' for i, lab in bvs)
        boxes = boxes or '<span class="hint">Add a business value first.</span>'
        return f"""<label>Label <input name="label" value="{esc(el.get("label", ""))}" required maxlength="500"></label>
<fieldset><legend>Business values it supports</legend>{boxes}</fieldset>"""
    if key == "feared_events":
        sev = [(x["n"], f'{x.get("code", x["n"])} {x.get("label", "")}') for x in (cal or {}).get("severity", [])]
        crit = "".join(f'<option value="{esc(c)}">' for c in CRITERIA)
        return f"""<label>Business value {_select("business_value", bvs, el.get("business_value"), required=True)}</label>
<label>Label <input name="label" value="{esc(el.get("label", ""))}" required maxlength="500"></label>
<label>Criterion <input name="criterion" list="criteria" value="{esc(el.get("criterion", ""))}" maxlength="100"></label>
<datalist id="criteria">{crit}</datalist>
<label>Severity {_select("severity", sev, el.get("severity"), required=True)}</label>"""
    if key == "baseline":
        return f"""<label>Reference <input name="reference" value="{esc(el.get("reference", ""))}" required maxlength="500"></label>
<label>Status {_select("status", [(s, s) for s in BASELINE_STATUS], el.get("status"))}</label>
<label>Gap <input name="gap" value="{esc(el.get("gap", ""))}" maxlength="1000"></label>"""
    raise KeyError(key)


def w1_page(sid, st, chk, session, flash="", form_error=None, hl=None):
    idx = element_index(st)
    cal = chk.get("cal")
    rev = {v: k for k, v in W1.items()}
    parts = [f"<h2 class=\"ws\">{esc(WORKSHOPS[1][0])}</h2>"]
    for key in WORKSHOPS[1][1]:
        slug = rev[key]

        def actions(x, slug=slug):
            eid = x.get("id", "")
            return (f'<a href="/s/{sid}/w1/{slug}/{q(eid)}">Edit</a>'
                    f'<form method="post" action="/s/{sid}/w1/{slug}/{q(eid)}/delete" class="inline">{csrf_input(session)}'
                    f'<button class="link danger" data-confirm="Delete {esc(eid)}? Links to it will show up in the checks.">'
                    f'Delete</button></form>')
        err = ""
        if form_error and form_error[0] == key:
            err = f'<p class="error">{esc(form_error[1])}</p>'
        disabled = key in ("feared_events",) and not (st.get("business_values") or [])
        add = ('<p class="hint">Add a business value first.</p>' if disabled else
               f"""<details class="add"{" open" if err or not (st.get(key) or []) else ""}><summary>Add {esc(TITLES[key].lower().rstrip("s"))}</summary>
<form method="post" action="/s/{sid}/w1/{slug}/add" class="grid-form">{csrf_input(session)}
{w1_form_fields(key, None, st, cal)}<button>Add</button></form></details>""")
        parts.append(f'<section class="card" id="sec-{slug}"><h2>{esc(TITLES[key])} '
                     f'<span class="count">{len(st.get(key) or [])}</span></h2>{err}'
                     f'{read_table(sid, st, key, cal, idx, actions, hl)}{add}</section>')
    return study_shell(sid, st, chk, "w1", "".join(parts), session, flash)


def w1_edit(sid, st, chk, key, el, session, error=""):
    slug = {v: k for k, v in W1.items()}[key]
    err = f'<p class="error">{esc(error)}</p>' if error else ""
    content = f"""<section class="card"><h2>Edit {esc(TITLES[key].lower().rstrip("s"))} {esc(el.get("id"))}</h2>{err}
<form method="post" action="/s/{sid}/w1/{slug}/{q(el.get("id"))}" class="grid-form">{csrf_input(session)}
{w1_form_fields(key, el, st, chk.get("cal"))}
<button>Save</button> <a href="/s/{sid}/w1#{anchor(el.get("id"))}">Cancel</a></form></section>"""
    return study_shell(sid, st, chk, "w1", content, session)


# ---------- register and grid ----------

def grid_table(cal, rows, key_l, key_level, title, sid):
    cls = level_classes(cal)
    by_cell = {}
    for r in rows:
        lk = r.get(key_l)
        if isinstance(lk, int) and isinstance(r.get("severity"), int):
            by_cell.setdefault((r["severity"], lk), []).append(r)
    head = "".join(f'<th scope="col">{esc(x.get("code"))}<small>{esc(x.get("label"))}</small></th>'
                   for x in cal["likelihood"])
    trs = []
    for s in (4, 3, 2, 1):
        sv = next(x for x in cal["severity"] if x["n"] == s)
        tds = []
        for v in (1, 2, 3, 4):
            name = engine.level(cal, s, v)
            chips = "".join(f'<a class="chip" href="#{anchor(r.get("id"))}" '
                            f'title="{esc(r.get("label", ""))}">{esc(r.get("id"))}</a>' for r in by_cell.get((s, v), []))
            tds.append(f'<td class="{cls.get(name, "")}"><span class="lvl-name">{esc(name)}</span>{chips}</td>')
        trs.append(f'<tr><th scope="row">{esc(sv.get("code"))}<small>{esc(sv.get("label"))}</small></th>{"".join(tds)}</tr>')
    return f"""<figure class="grid-wrap"><figcaption>{esc(title)}</figcaption>
<div class="axis-y">Severity</div>
<table class="grid"><thead><tr><th class="corner"></th>{head}</tr></thead><tbody>{"".join(trs)}</tbody></table>
<div class="axis-x">Likelihood</div></figure>"""


def grids_block(cal, rows, summary, sid):
    """The engine's register on two grids side by side: now, and at target (risks with a target likelihood)."""
    cls = level_classes(cal)

    def lvl(name):
        return f'<span class="lvl {cls.get(name, "")}">{esc(name)}</span>' if name else ""

    def counts(d):
        return " ".join(f'{lvl(k)} {v}' for k, v in d.items()) or "none"
    with_target = [r for r in rows if r.get("likelihood_target")]
    without = [r.get("id") for r in rows if not r.get("likelihood_target")]
    grids = grid_table(cal, rows, "likelihood", "level", "Now", sid)
    grids += grid_table(cal, with_target, "likelihood_target", "level_target", "At target", sid)
    note = (f'<p class="hint">No target likelihood yet for {esc(", ".join(str(x) for x in without))}, so '
            f'{"it is" if len(without) == 1 else "they are"} not on the target grid.</p>') if without else ""
    legend = "".join(f'<li>{lvl(l["name"])} {esc(l.get("acceptability", ""))}</li>'
                     for l in sorted(cal["levels"], key=lambda l: -l["rank"]))
    return f"""<p class="hint">Levels, acceptability and counts are the engine's register for calibration {esc(cal["id"])}.</p>
<p>Now: {counts(summary.get("now", {}))}. At target: {counts(summary.get("target", {}))}.</p>
<div class="grids">{grids}</div>{note}
<ul class="legend">{legend}</ul>"""


def register_page(sid, st, chk, rows, summary, session):
    cal = chk["cal"]
    cls = level_classes(cal)

    def lvl(name):
        return f'<span class="lvl {cls.get(name, "")}">{esc(name)}</span>' if name else ""
    cols = [("id", "Id", lambda r: f'<b>{esc(r.get("id"))}</b>'),
            ("label", "Risk", lambda r: esc(r.get("label"))),
            ("severity", "Severity", lambda r: scale_text(cal, "severity", r.get("severity"))),
            ("likelihood", "Likelihood", lambda r: scale_text(cal, "likelihood", r.get("likelihood"))),
            ("level", "Level", lambda r: lvl(r.get("level"))),
            ("acceptability", "Acceptability", lambda r: esc(r.get("acceptability"))),
            ("likelihood_target", "Target likelihood",
             lambda r: scale_text(cal, "likelihood", r.get("likelihood_target")) if r.get("likelihood_target") is not None else ""),
            ("level_target", "Target level", lambda r: lvl(r.get("level_target"))),
            ("treatment", "Treatment", lambda r: esc(r.get("treatment") or "")),
            ("owner", "Owner", lambda r: esc(r.get("owner") or "")),
            ("measures", "Measures", lambda r: esc(", ".join(r.get("measures") or [])))]
    always = {"id", "label", "severity", "likelihood", "level", "acceptability"}
    cols = [c for c in cols if c[0] in always or any(r.get(c[0]) not in (None, "", []) for r in rows)]
    hidden = 11 - len(cols)
    trs = [f'<tr id="{anchor(r.get("id"))}">' + "".join(f'<td class="c-{k}">{fn(r)}</td>' for k, _, fn in cols) + "</tr>"
           for r in rows]
    note = (f'<p class="hint">{hidden} column{"s" if hidden > 1 else ""} with no value for any risk '
            f'(target, treatment, owner, measures) not shown.</p>') if hidden else ""
    table = ('<p class="empty">The study has no risk yet (risks are workshop 5).</p>' if not rows else
             '<div class="scroll"><table class="list register"><thead><tr>'
             + "".join(f"<th>{esc(t)}</th>" for _, t, _ in cols) + f'</tr></thead><tbody>{"".join(trs)}</tbody></table></div>{note}')
    content = f"""<section class="card"><h2>Risk grid, now and at target</h2>
{grids_block(cal, rows, summary, sid)}</section>
<section class="card"><h2>Risk register <span class="count">{len(rows)}</span></h2>
{table}</section>"""
    return study_shell(sid, st, chk, "register", content, session)


def register_blocked(sid, st, chk, session):
    content = """<section class="card"><h2>Risk register</h2>
<p class="error">The engine builds the register only for a study without errors. Fix the errors listed in the checks
panel, then come back.</p></section>"""
    return study_shell(sid, st, chk, "register", content, session)


def confirm_delete(sid, st, session):
    meta = st.get("study") if isinstance(st.get("study"), dict) else {}
    body = f"""<section class="card narrow"><h1>Delete this study?</h1>
<p><b>{esc(meta.get("name") or "(no name)")}</b></p>
<p>The file moves to the trash folder of the data directory; nothing else is removed.</p>
<form method="post" action="/s/{sid}/delete">{csrf_input(session)}<button class="danger">Delete</button>
<a href="/s/{sid}">Cancel</a></form></section>"""
    return page("Delete study", body, session)


def link_page(url, session):
    body = f"""<section class="card narrow"><h1>One-time login link</h1>
<p>Valid for one use within 10 minutes.</p><p><code id="once-link">{esc(url)}</code></p>
<p><a href="/">Back</a></p></section>"""
    return page("Login link", body, session)


def cal_css(cal):
    out = []
    for i, l in enumerate(sorted(cal["levels"], key=lambda l: l["rank"])):
        c = str(l.get("colour") or "")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", c):
            c = "BBBBBB"
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        fg = "#111" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#fff"
        out.append(f".lvl-i{i}{{background:#{c};color:{fg}}}")
    return "\n".join(out) + "\n"
