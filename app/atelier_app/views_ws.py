"""Workshop 2 to 5 editors: tables with edit and delete, add forms, edit pages, the W5 grids.

Same rules as views.py: every piece of study or user text goes through esc(); no inline script or style.
Severities of strategic scenarios and risks, and every level, are the engine's (engine.derived_severity,
engine.register, engine.level); this module only displays them.
"""
from . import editors, engine
from .views import (TITLES, WORKSHOPS, anchor, csrf_input, esc, grids_block, q, scale_text, study_shell, _select)

SINGULAR = {"risk_origins": "risk origin", "stakeholders": "stakeholder", "strategic_scenarios": "strategic scenario",
            "operational_scenarios": "operational scenario", "risks": "risk", "measures": "measure"}
SCALE_OPTS = [(n, str(n)) for n in (1, 2, 3, 4)]


def _ref(sid, v, idx):
    if isinstance(v, str) and v in idx:
        return f'<a href="/s/{sid}/el/{q(v)}">{esc(v)}</a>'
    return esc(v)


def _refs(sid, vs, idx):
    if not isinstance(vs, list):
        return esc(vs)
    return ", ".join(_ref(sid, v, idx) for v in vs)


def _scale_cell(cal, axis, v):
    if v is None:
        return ""
    if axis:
        return scale_text(cal, axis, v)
    return esc(v)


def severity_cell(st, chk, key, x):
    """Stored severity, the engine's value and the engine's check result for one scenario or risk."""
    cal = chk.get("cal")
    eid = x.get("id")
    stored = x.get("severity")
    derived = engine.derived_severity(st, cal, key, eid)
    errs = engine.severity_errors(chk, eid)
    shown = derived if derived is not None else stored
    val = scale_text(cal, "severity", shown) if shown is not None else "not determined"
    if errs:
        note = "".join(f'<span class="chk bad">{esc(e)}</span>' for e in errs)
        if derived is not None and derived != stored:
            note += f'<span class="chk">stored: {scale_text(cal, "severity", stored) if stored is not None else "none"}</span>'
        return f'<span class="sev">{val}</span>{note}'
    if derived is None:
        return f'<span class="sev">{val}</span><span class="chk">the engine cannot determine it yet</span>'
    return f'<span class="sev">{val}</span><span class="chk ok">engine check passed</span>'


def _paths_cell(sid, x, idx, hl):
    lis = []
    for p in x.get("paths") or []:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        sh = p.get("stakeholder")
        via = f' <span class="via">via {_ref(sid, sh, idx)}</span>' if sh else ""
        cls = ' class="hl"' if hl is not None and pid == hl else ""
        lis.append(f'<li id="{anchor(pid)}"{cls}><b>{esc(pid)}</b> {esc(p.get("label", ""))}{via}</li>')
    return f'<ul class="paths">{"".join(lis)}</ul>' if lis else ""


def columns(key, sid, st, chk, idx, hl):
    cal = chk.get("cal")
    paths = {p.get("id"): p for ss in editors.items(st, "strategic_scenarios") for p in ss.get("paths") or []
             if isinstance(p, dict)}
    if key == "risk_origins":
        return [("origin", "Risk origin", lambda x: esc(x.get("origin"))),
                ("objective", "Target objective", lambda x: esc(x.get("objective"))),
                ("motivation", "Motivation", lambda x: _scale_cell(cal, None, x.get("motivation"))),
                ("resources", "Resources", lambda x: _scale_cell(cal, None, x.get("resources"))),
                ("decision", "Decision", lambda x: f'<span class="dec dec-{esc(x.get("decision"))}">'
                                                    f'{esc(x.get("decision"))}</span>' if x.get("decision") else ""),
                ("feared_events", "Feared events", lambda x: _refs(sid, x.get("feared_events") or [], idx))]
    if key == "stakeholders":
        cols = [("name", "Name", lambda x: esc(x.get("name"))), ("category", "Category", lambda x: esc(x.get("category")))]
        cols += [(k, k.capitalize(), lambda x, k=k: _scale_cell(cal, None, x.get(k))) for k in editors.SH_SCALES]
        cols.append(("critical", "Critical", lambda x: "yes" if x.get("critical") is True else (
            "no" if x.get("critical") is False else esc(x.get("critical")))))
        return cols
    if key == "strategic_scenarios":
        return [("risk_origin", "Risk origin", lambda x: _ref(sid, x.get("risk_origin"), idx)),
                ("feared_events", "Feared events", lambda x: _refs(sid, x.get("feared_events") or [], idx)),
                ("severity", "Severity (engine)", lambda x: severity_cell(st, chk, key, x)),
                ("paths", "Attack paths", lambda x: _paths_cell(sid, x, idx, hl))]
    if key == "operational_scenarios":
        def path_text(x):
            p = paths.get(x.get("path"))
            if not x.get("path"):
                return '<span class="hint">whole scenario</span>'
            lab = f' {esc(p.get("label", ""))}' if p else ' <span class="chk bad">no such path</span>'
            return f'{_ref(sid, x.get("path"), idx)}{lab}'
        return [("strategic_scenario", "Strategic scenario", lambda x: _ref(sid, x.get("strategic_scenario"), idx)),
                ("path", "Path", path_text),
                ("likelihood", "Likelihood", lambda x: _scale_cell(cal, "likelihood", x.get("likelihood"))),
                ("description", "Description", lambda x: f'<span class="pre">{esc(x.get("description"))}</span>')]
    if key == "risks":
        return [("scenario", "Scenario", lambda x: _ref(sid, x.get("operational_scenario") or x.get("strategic_scenario"), idx)),
                ("label", "Risk", lambda x: esc(x.get("label"))),
                ("severity", "Severity (engine)", lambda x: severity_cell(st, chk, key, x)),
                ("likelihood", "Likelihood", lambda x: _scale_cell(cal, "likelihood", x.get("likelihood"))),
                ("likelihood_target", "Target", lambda x: _scale_cell(cal, "likelihood", x.get("likelihood_target"))),
                ("treatment", "Treatment", lambda x: esc(x.get("treatment") or "")),
                ("owner", "Owner", lambda x: esc(x.get("owner") or ""))]
    if key == "measures":
        return [("label", "Measure", lambda x: esc(x.get("label"))),
                ("risks", "Risks", lambda x: _refs(sid, x.get("risks") or [], idx)),
                ("owner", "Owner", lambda x: esc(x.get("owner") or "")),
                ("due", "Due", lambda x: esc(x.get("due") or "")),
                ("status", "Status", lambda x: esc(x.get("status") or ""))]
    raise KeyError(key)


KNOWN = {"risk_origins": {"origin", "objective", "motivation", "resources", "decision", "feared_events"},
         "stakeholders": {"name", "category", "critical", *editors.SH_SCALES},
         "strategic_scenarios": {"risk_origin", "feared_events", "severity", "paths"},
         "operational_scenarios": {"strategic_scenario", "path", "likelihood", "description"},
         "risks": {"strategic_scenario", "operational_scenario", "label", "severity", "likelihood", "likelihood_target",
                   "treatment", "owner"},
         "measures": {"label", "risks", "owner", "due", "status"}}


def table(sid, st, chk, key, idx, session, hl=None):
    slug = editors.SLUG_OF[key]
    n = editors.SPECS[slug][1]
    rows = editors.items(st, key)
    if not rows:
        return '<p class="empty">None yet.</p>'
    cols = columns(key, sid, st, chk, idx, hl)
    extra = [k for k in dict.fromkeys(k for x in rows for k in x) if k != "id" and k not in KNOWN[key]]
    cols += [(k, k.replace("_", " "), lambda x, k=k: esc(x.get(k)) if not isinstance(x.get(k), (list, dict))
              else esc(str(x.get(k)))) for k in extra]
    head = "<th>Id</th>" + "".join(f"<th>{esc(t)}</th>" for _, t, _ in cols) + "<th></th>"
    trs = []
    for x in rows:
        eid = x.get("id", "")
        cls = ' class="hl"' if hl is not None and eid == hl else ""
        act = (f'<a href="/s/{sid}/w{n}/{slug}/{q(eid)}">Edit</a>'
               f'<form method="post" action="/s/{sid}/w{n}/{slug}/{q(eid)}/delete" class="inline">{csrf_input(session)}'
               f'<button class="link danger" data-confirm="Delete {esc(eid)}? Links to it will show up in the checks.">'
               f'Delete</button></form>')
        tds = "".join(f'<td class="c-{k}">{fn(x)}</td>' for k, _, fn in cols)
        trs.append(f'<tr id="{anchor(eid)}"{cls}><td class="c-id"><b>{esc(eid)}</b></td>{tds}'
                   f'<td class="actions">{act}</td></tr>')
    return (f'<div class="scroll"><table class="list ed-{slug}"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


# ---------- forms ----------

def _boxes(name, options, current, empty_hint):
    cur = set(current or [])
    boxes = "".join(f'<label class="check"><input type="checkbox" name="{name}" value="{esc(i)}"'
                    f'{" checked" if i in cur else ""}> {esc(lab)}</label>' for i, lab in options)
    return boxes or f'<span class="hint">{esc(empty_hint)}</span>'


def _grouped(name, targets, current, required=True, blank="(pick one)"):
    groups = {}
    for value, t in targets.items():
        groups.setdefault(t[3], []).append((value, t[2]))
    opts = [f'<option value="">{esc(blank)}</option>']
    for g, vals in groups.items():
        inner = "".join(f'<option value="{esc(v)}"{" selected" if v == current else ""}>{esc(lab)}</option>'
                        for v, lab in vals)
        opts.append(f'<optgroup label="{esc(g)}">{inner}</optgroup>')
    return f'<select name="{name}"{" required" if required else ""}>{"".join(opts)}</select>'


def _cal_scale(cal, axis):
    return [(x["n"], f'{x.get("code", x["n"])} {x.get("label", "")}') for x in (cal or {}).get(axis, [])]


def form_fields(slug, el, st, chk):
    el = el or {}
    cal = chk.get("cal")
    fes = [(i, f'{i} {(editors.find(st, "feared_events", i) or {}).get("label", "")}') for i in editors.ids(st, "feared_events")]
    if slug == "ro":
        scales = "".join(f'<label>{k.capitalize()} {_select(k, SCALE_OPTS, el.get(k))}</label>' for k in editors.RO_SCALES)
        return f"""<label>Risk origin <input name="origin" value="{esc(el.get("origin", ""))}" required maxlength="500"></label>
<label>Target objective <input name="objective" value="{esc(el.get("objective", ""))}" maxlength="1000"></label>
{scales}
<label>Decision {_select("decision", [(d, d) for d in editors.DECISIONS], el.get("decision"), required=True)}</label>
<fieldset><legend>Feared events it aims at</legend>{_boxes("feared_events", fes, el.get("feared_events"), "No feared event yet (workshop 1).")}</fieldset>"""
    if slug == "sh":
        cats = sorted({str(x.get("category")) for x in editors.items(st, "stakeholders") if x.get("category")})
        dl = "".join(f'<option value="{esc(c)}">' for c in cats)
        scales = "".join(f'<label>{k.capitalize()} {_select(k, SCALE_OPTS, el.get(k))}</label>' for k in editors.SH_SCALES)
        return f"""<label>Name <input name="name" value="{esc(el.get("name", ""))}" required maxlength="300"></label>
<label>Category <input name="category" list="sh-categories" value="{esc(el.get("category", ""))}" maxlength="100"></label>
<datalist id="sh-categories">{dl}</datalist>
{scales}
<label class="check"><input type="checkbox" name="critical" value="yes"{" checked" if el.get("critical") is True else ""}> Critical stakeholder</label>"""
    if slug == "ss":
        ros = [(i, f'{i} {(editors.find(st, "risk_origins", i) or {}).get("origin", "")}') for i in editors.ids(st, "risk_origins")]
        shs = [(i, f'{i} {(editors.find(st, "stakeholders", i) or {}).get("name", "")}') for i in editors.ids(st, "stakeholders")]
        rows = []
        for p in el.get("paths") or []:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            rows.append(f"""<tr><td><input type="hidden" name="path_id" value="{esc(pid)}"><b>{esc(pid)}</b></td>
<td><input name="path_label" value="{esc(p.get("label", ""))}" maxlength="1000" aria-label="label of {esc(pid)}"></td>
<td>{_select("path_stakeholder", shs, p.get("stakeholder"), blank="(direct, no stakeholder)")}</td>
<td><label class="check"><input type="checkbox" name="path_remove" value="{esc(pid)}"> remove</label></td></tr>""")
        rows.append(f"""<tr><td><i>new</i></td><td><input name="new_path_label" maxlength="1000" placeholder="label of a new path" aria-label="label of a new path"></td>
<td>{_select("new_path_stakeholder", shs, None, blank="(direct, no stakeholder)")}</td><td></td></tr>""")
        sev = ""
        if el.get("id"):
            sev = f'<p class="derived">Severity: {severity_cell(st, chk, "strategic_scenarios", el)}</p>'
        return f"""<label>Risk origin {_select("risk_origin", ros, el.get("risk_origin"), required=True)}</label>
<fieldset><legend>Feared events it leads to</legend>{_boxes("feared_events", fes, el.get("feared_events"), "No feared event yet (workshop 1).")}</fieldset>
<p class="hint wide">Severity is not typed here: the engine takes it from the feared events (guide p.49) when you save.</p>{sev}
<fieldset><legend>Attack paths</legend><div class="scroll"><table class="paths-form"><thead><tr><th>Id</th><th>Label</th><th>Stakeholder</th><th></th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></fieldset>"""
    if slug == "os":
        return f"""<label>Strategic scenario path {_grouped("target", editors.os_targets(st), editors.os_target_value(el))}</label>
<label>Likelihood {_select("likelihood", _cal_scale(cal, "likelihood"), el.get("likelihood"), required=True)}</label>
<label class="wide">Description <textarea name="description" rows="3" maxlength="4000">{esc(el.get("description", ""))}</textarea></label>"""
    if slug == "rk":
        lk = _cal_scale(cal, "likelihood")
        sev = ""
        if el.get("id"):
            sev = f'<p class="derived">Severity: {severity_cell(st, chk, "risks", el)}</p>'
        return f"""<label>Scenario {_grouped("scenario", editors.risk_targets(st), editors.risk_target_value(el))}</label>
<label class="wide">Label <input name="label" value="{esc(el.get("label", ""))}" required maxlength="1000"></label>
<label>Likelihood now {_select("likelihood", lk, el.get("likelihood"), required=True)}</label>
<label>Target likelihood {_select("likelihood_target", lk, el.get("likelihood_target"), blank="(no target)")}</label>
<label>Treatment {_select("treatment", [(t, t) for t in editors.TREATMENTS], el.get("treatment"))}</label>
<label>Owner <input name="owner" value="{esc(el.get("owner", ""))}" maxlength="200"></label>
<p class="hint wide">Severity is not typed here: the engine takes it from the scenario (guide p.62, p.65) when you save.</p>{sev}"""
    if slug == "ms":
        rks = [(i, f'{i} {(editors.find(st, "risks", i) or {}).get("label", "")}') for i in editors.ids(st, "risks")]
        return f"""<label class="wide">Label <input name="label" value="{esc(el.get("label", ""))}" required maxlength="1000"></label>
<label>Owner <input name="owner" value="{esc(el.get("owner", ""))}" maxlength="200"></label>
<label>Due date <input type="date" name="due" value="{esc(el.get("due", ""))}"></label>
<label>Status {_select("status", [(s, s) for s in editors.MEASURE_STATUS], el.get("status"), required=True)}</label>
<fieldset><legend>Risks it treats</legend>{_boxes("risks", rks, el.get("risks"), "No risk yet.")}</fieldset>"""
    raise KeyError(slug)


def _needs(slug, st):
    """Why the add form cannot be used yet, or ''."""
    if slug == "ss" and not editors.ids(st, "risk_origins"):
        return "Add a risk origin (workshop 2) first."
    if slug == "ss" and not editors.ids(st, "feared_events"):
        return "Add a feared event (workshop 1) first."
    if slug == "os" and not editors.ids(st, "strategic_scenarios"):
        return "Add a strategic scenario (workshop 3) first."
    if slug == "rk" and not (editors.ids(st, "strategic_scenarios") or editors.ids(st, "operational_scenarios")):
        return "Add a strategic or operational scenario first."
    return ""


def workshop_page(sid, st, chk, n, session, flash="", hl=None, form_error=None, register=None):
    from .views import element_index
    title, keys = WORKSHOPS[n]
    idx = element_index(st)
    parts = [f'<h2 class="ws">{esc(title)}</h2>']
    for key in keys:
        slug = editors.SLUG_OF[key]
        err = f'<p class="error">{esc(form_error[1])}</p>' if form_error and form_error[0] == slug else ""
        need = _needs(slug, st)
        add = (f'<p class="hint">{esc(need)}</p>' if need else
               f"""<details class="add"{" open" if err or not editors.items(st, key) else ""}><summary>Add {esc(SINGULAR[key])}</summary>
<form method="post" action="/s/{sid}/w{n}/{slug}/add" class="grid-form">{csrf_input(session)}
{form_fields(slug, None, st, chk)}<button>Add</button></form></details>""")
        sync = ""
        if key in engine.DERIVED_SEVERITY and any(engine.severity_errors(chk, x.get("id")) for x in editors.items(st, key)):
            sync = (f'<form method="post" action="/s/{sid}/severities" class="sync">{csrf_input(session)}'
                    f'<input type="hidden" name="back" value="w{n}">'
                    '<button>Take the severities from the engine</button></form>')
        parts.append(f'<section class="card" id="sec-{slug}"><h2>{esc(TITLES[key])} '
                     f'<span class="count">{len(editors.items(st, key))}</span></h2>{err}{sync}'
                     f'{table(sid, st, chk, key, idx, session, hl)}{add}</section>')
    if n == 5:
        parts.append(grid_section(sid, chk, register))
    return study_shell(sid, st, chk, f"w{n}", "".join(parts), session, flash)


def grid_section(sid, chk, register):
    if register is None:
        return ('<section class="card" id="sec-grid"><h2>Risk grid, now and at target</h2>'
                '<p class="hint">The engine draws the grid only for a study without errors. Fix the errors in the '
                'checks panel first.</p></section>')
    rows, summary = register
    return (f'<section class="card" id="sec-grid"><h2>Risk grid, now and at target</h2>'
            f'{grids_block(chk["cal"], rows, summary, sid)}</section>')


def edit_page(sid, st, chk, slug, el, session, error=""):
    key, n, _ = editors.SPECS[slug]
    err = f'<p class="error">{esc(error)}</p>' if error else ""
    content = f"""<section class="card"><h2>Edit {esc(SINGULAR[key])} {esc(el.get("id"))}</h2>{err}
<form method="post" action="/s/{sid}/w{n}/{slug}/{q(el.get("id"))}" class="grid-form">{csrf_input(session)}
{form_fields(slug, el, st, chk)}
<div class="form-actions"><button>Save</button> <a href="/s/{sid}/w{n}?hl={q(el.get("id"))}#{anchor(el.get("id"))}">Cancel</a></div></form></section>"""
    return study_shell(sid, st, chk, f"w{n}", content, session)
