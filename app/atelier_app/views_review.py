"""Review-mode pages. All imported and plugin text is escaped, including field ids."""
from itertools import groupby

from . import calibrations, engine, views
from .views import esc, q, csrf_input, page


def details(value):
    if isinstance(value, dict):
        return '<dl class="review-details">' + ''.join(
            f'<dt>{esc(k)}</dt><dd>{details(v)}</dd>' for k, v in value.items()) + '</dl>'
    if isinstance(value, (list, tuple)):
        return '<ul>' + ''.join(f'<li>{details(v)}</li>' for v in value) + '</ul>' if value else '<p>None</p>'
    return esc(value)


def listing(rows, cats, layouts, session, error=""):
    table = '<p>No reviews yet.</p>'
    if rows:
        table = '<div class="table-wrap"><table><thead><tr><th>Review</th><th>Calibration</th><th>Updated</th></tr></thead><tbody>'
        for rid, state, mtime in rows:
            meta = state['study']['study']
            table += (f'<tr><td><a href="/r/{rid}">{esc(meta.get("name") or "Review")}</a></td>'
                      f'<td>{esc(meta.get("calibration"))}{views.cal_badge(calibrations.kind(meta.get("calibration")))}</td>'
                      f'<td>{views.when(mtime)}</td></tr>')
        table += '</tbody></table></div>'
    options = '<option value="">Auto detect</option>' + ''.join(
        f'<option value="{esc(k)}">{esc(k)} ({esc(v)})</option>' for k, v in layouts.items())
    body = (f'<h1>Reviews</h1>{table}<section class="card" id="new-review"><h2>New review</h2>'
            '<p>Import an existing risk analysis. The engine checks it; you decide the ratings.</p>'
            + (f'<p class="error" role="alert">{esc(error)}</p>' if error else '')
            + f'<form action="/reviews" method="post" enctype="multipart/form-data">{csrf_input(session)}'
            '<label>Review name <input name="name" maxlength="200" placeholder="Risk analysis review"></label>'
            '<label>Workbook (.xlsx, at most 20 MB) <input name="file" type="file" accept=".xlsx" required></label>'
            + views.cal_picker(cats)
            + f'<label>Layout <select name="layout">{options}</select></label><button>Import workbook</button></form></section>')
    return page('Reviews', body, session)


def shell(rid, state, body, session, title):
    meta = state['study']['study']
    private, why = calibrations.study_privacy(state['study'])
    intro = (f'<p><a href="/reviews">Reviews</a></p><h1>{esc(meta.get("name") or "Review")}</h1>'
             f'<p>{esc(meta.get("calibration"))}{views.cal_badge(calibrations.kind(meta.get("calibration")))}'
             + (f' · Confidential: {esc(why)}. Local review only.' if private else ' · Local review only.') + '</p>'
             f'<nav class="tabs"><a href="/r/{rid}">Import report</a><a href="/r/{rid}/ratings">Rate criteria</a>'
             f'<a href="/r/{rid}/result">Result &amp; export</a></nav>')
    return page(title, intro + body, session, cal_id=meta.get('calibration'))


def import_page(rid, state, result, cal, session, plugin):
    report = state['report']
    read = report.get('read', {})
    pictures = read.get('pictures', [])  # the importer omits this key when no pictures were read
    body = ('<h2>Import report</h2><section class="card"><h3>Layout detected: '
            + esc(report.get('layout')) + '</h3><div class="import-counts">')
    for label, value in (('risks', read.get('risks')), ('measures', read.get('measures')),
                         ('stages', len(read.get('stages', []))), ('pictures', len(pictures))):
        body += f'<p><strong>{esc(value)}</strong> {esc(label)}</p>'
    body += ('</div><details><summary>Columns, stages and picture details</summary>'
             + details(read) + '</details></section>')
    for key in ('errors', 'notes', 'findings'):
        body += f'<section class="card"><h3>Import {esc(key)} ({len(report.get(key, []))})</h3>{details(report.get(key, []))}</section>'
    body += '<h3>Engine checks</h3>' + details(result.get('check', {}))
    if report.get('errors'):
        body += '<p class="error">Import errors block ratings, register, maps and export. Correct the workbook and import again.</p>'
    else:
        body += register(result.get('register', []), cal)
        body += f'<p><a class="button" href="/r/{rid}/ratings">Rate criteria</a></p>' if plugin else no_plugin()
    body += (f'<form action="/r/{rid}/delete" method="post">{csrf_input(session)}'
             '<p>Delete removes this review and its uploaded workbook permanently.</p><button class="danger">Delete review</button></form>')
    return shell(rid, state, body, session, 'Import report')


def no_plugin():
    return '<p class="notice">Review plugin unavailable. Import, engine checks, register and maps work; scoring and review Excel export are unavailable.</p>'


def register(rows, cal):
    if not rows:
        return '<h3>Risk register</h3><p>No register available. Check the engine errors.</p>'
    body = '<h3>Risk register</h3><div class="table-wrap"><table><thead><tr>'
    keys = ('id', 'label', 'severity', 'likelihood', 'level', 'level_target', 'level_initial', 'measures')
    body += ''.join(f'<th>{esc(k.replace("_", " "))}</th>' for k in keys) + '</tr></thead><tbody>'
    for row in rows:
        body += '<tr>' + ''.join(f'<td>{details(row.get(k))}</td>' for k in keys) + '</tr>'
    body += '</tbody></table></div><div class="review-maps">'
    for stage, key in (('now', 'level'), ('target', 'level_target'), ('initial', 'level_initial')):
        if any(row.get(key) is not None for row in rows):
            title = f'Risk map: {stage}'
            body += f'<figure class="risk-map"><figcaption>{esc(title)}</figcaption>{engine.risk_map(rows, cal, stage, title)}</figure>'
    return body + '</div>'


def measure_table(rows):
    if not rows:
        return '<p>None</p>'
    keys = ('id', 'label', 'owner', 'due', 'status', 'risks', 'details')
    body = '<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th>{esc(k)}</th>' for k in keys) + '</tr></thead><tbody>'
    for row in rows:
        body += '<tr>' + ''.join(f'<td>{details(row.get(k))}</td>' for k in keys) + '</tr>'
    return body + '</tbody></table></div>'


def rating_page(rid, state, result, statuses, session, error='', sticky=None):
    body = '<h2>Rate criteria</h2><p>Machine proposals are prefilled. Saving confirms each selected status as your reviewer rating. Blank leaves it to the machine. Notes are optional.</p>'
    if error:
        body += f'<p class="error" role="alert">{esc(error)}</p>'
    body += f'<form method="post" action="/r/{rid}/ratings">{csrf_input(session)}'
    criteria = sorted(result['criteria'], key=lambda c: (str(c.get('axis', '')), str(c.get('workshop', ''))))
    for (axis, workshop), items in groupby(criteria, key=lambda c: (str(c.get('axis', '')), str(c.get('workshop', '')))):
        body += f'<section class="card"><h3>{esc(axis)} · {esc(workshop)}</h3>'
        for c in items:
            cid = c['id']
            proposal = result.get('proposed', {}).get(cid, {})
            value = state.get('ratings', {}).get(cid, proposal.get('status', result.get('ratings', {}).get(cid, '')))
            note = state.get('notes', {}).get(cid, '')
            if sticky is not None:
                value, note = sticky.get('status_' + cid, value), sticky.get('note_' + cid, note)
            picks = [''] + list(statuses)
            if value not in picks:
                picks.append(value)  # keep a refused value visible, never save it
            options = ''.join(f'<option value="{esc(s)}"{" selected" if s == value else ""}>{esc(s) if s else "Unrated / machine"}</option>' for s in picks)
            body += (f'<article class="rating-row" id="criterion-{q(cid)}"><h4>{esc(cid)} · {esc(c["text"])}</h4>'
                     f'<p class="muted">Applicability: {esc(c.get("appl"))} · Mode: {esc(c.get("mode"))} · Level: {esc(c.get("level"))}</p>'
                     f'<p>Machine proposal: <strong>{esc(proposal.get("status") or "None")}</strong> {esc(proposal.get("why", ""))}</p>'
                     f'<div class="rating-fields"><label>Status <select name="status_{esc(cid)}">{options}</select></label>'
                     f'<label>Reviewer note <textarea name="note_{esc(cid)}" rows="2" maxlength="4000">{esc(note)}</textarea></label></div></article>')
        body += '</section>'
    body += '<div class="review-save"><button>Save reviewer ratings</button></div></form>'
    return shell(rid, state, body, session, 'Rate criteria')


def result_page(rid, state, result, cal, session, plugin):
    body = '<h2>Review result</h2>'
    if not plugin:
        body += no_plugin()
    elif result.get('score') is not None:
        score = result['score']
        confidence = (f'<p>Confidence: {esc(score["confidence"])}%</p>' if score.get('confidence') is not None else '')
        body += (f'<section class="card review-score"><h3>Score: {esc(score.get("final_score"))}</h3>'
                 + confidence + '</section><h3>Findings</h3>' + details(score.get('findings', {})))
    else:
        unrated = result.get('unrated', [])
        body += f'<p class="notice">Unrated: {len(unrated)}. Score and confidence await completed ratings.</p><ul>'
        body += ''.join(f'<li><a href="/r/{rid}/ratings#criterion-{q(cid)}">{esc(cid)}</a></li>' for cid in unrated) + '</ul>'
    body += '<h3>Import findings</h3>' + details(state['report'].get('findings', []))
    body += '<h3>Measures</h3>' + measure_table(result.get('measures', []))
    if plugin:
        body += '<h3>Criterion sources</h3><div class="table-wrap"><table><thead><tr><th>Criterion</th><th>Status</th><th>Source</th><th>Note</th></tr></thead><tbody>'
        for c in result.get('criteria', []):
            cid = c['id']
            body += (f'<tr><td><a href="/r/{rid}/ratings#criterion-{q(cid)}">{esc(cid)}</a></td>'
                     f'<td>{esc(result.get("ratings", {}).get(cid, "Unrated"))}</td><td>{esc(result.get("sources", {}).get(cid, "unrated"))}</td>'
                     f'<td>{esc(result.get("notes", {}).get(cid, ""))}</td></tr>')
        body += '</tbody></table></div>'
    body += register(result.get('register', []), cal)
    body += f'<p><a class="button" href="/r/{rid}/export.json">Download study JSON</a> '
    if plugin:
        body += f'<a class="button" href="/r/{rid}/export.xlsx">Download review Excel</a>'
    body += '</p>'
    return shell(rid, state, body, session, 'Review result')
