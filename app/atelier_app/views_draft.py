"""Drafting panels (one per workshop), the documents page and the settings page.

Same rules as views.py: every piece of study, document or user text goes through esc(); no inline script or style.
A draft item is not in the study: it becomes an element only when the user accepts it in its form, and every
judgement field (severity, likelihood, decision, status, owner, due date, ratings) starts empty for the user to pick.
"""
from . import drafting, drafts, views_ws
from .views import CRITERIA, NATURES, TITLES, _select, csrf_input, esc, ferr, form_note, page, q, study_shell

ROUTE_TEXT = {"off": "off", "local": "local (this machine)", "remote": "remote"}


def size_text(n):
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def route_line(info):
    """The active route and model, shown on every drafting panel and on the settings page."""
    r = info["route"]
    badge = f'<span class="badge route route-{esc(r)}">route: {esc(ROUTE_TEXT.get(r, r))}</span>'
    if r == "off":
        why = f" ({esc(info['problem'])})" if info.get("problem") else ""
        return (f'<p class="route-line">{badge} Drafting is off{why}. Nothing is sent anywhere. '
                f'<a href="/settings">Settings</a></p>')
    where = "on this machine" if r == "local" else "not on this machine"
    return (f'<p class="route-line">{badge} model <b>{esc(info["model"])}</b> &middot; endpoint '
            f'<b>{esc(info["endpoint"])}</b> ({where}) &middot; <a href="/settings">Settings</a></p>')


def limits_line(info):
    lim = info["limits"]
    return (f'<p class="hint">Limits for this study: at most {lim["requests_per_minute"]} requests a minute, '
            f'{lim["max_output_tokens"]} output tokens a request, and {lim["max_chunks"]} requests a draft. The source '
            f'text is cut to fit a {lim["context_tokens"]}-token context (about {info["budget"] // 1000}k characters a '
            f'request, at {drafting.CHARS_PER_TOKEN} characters a token). Every request is logged without any text.</p>')


def ssh_hint(info):
    if info.get("route") != "local" or not info.get("ssh_hint"):
        return ""
    return (f'<p class="hint">The local route expects a forward you open yourself, for example '
            f'<code>{esc(info["ssh_hint"])}</code>. The app never runs ssh.</p>')


# ---------- the drafting panel ----------

def _w1_fields(kind, cur, st, cal, errs):
    bvs = [(b["id"], f'{b["id"]} {b.get("label", "")}') for b in st.get("business_values") or []
           if isinstance(b, dict) and b.get("id")]
    if kind == "business_value":
        return f"""<label>Label <input name="label" value="{esc(cur.get("label", ""))}" required maxlength="500">{ferr(errs, "label")}</label>
<label>Nature {_select("nature", [(n, n) for n in NATURES], cur.get("nature"))}{ferr(errs, "nature")}</label>
<label>Owner (you fill it in) <input name="owner" value="{esc(cur.get("owner", ""))}" maxlength="200">{ferr(errs, "owner")}</label>"""
    if kind == "supporting_asset":
        sel = set(cur.get("business_values") or [])
        boxes = "".join(f'<label class="check"><input type="checkbox" name="business_values" value="{esc(i)}"'
                        f'{" checked" if i in sel else ""}> {esc(lab)}</label>' for i, lab in bvs)
        return f"""<label class="wide">Label <input name="label" value="{esc(cur.get("label", ""))}" required maxlength="500">{ferr(errs, "label")}</label>
<fieldset><legend>Business values it supports</legend>{ferr(errs, "business_values")}{boxes or '<span class="hint">No business value yet.</span>'}</fieldset>"""
    if kind == "feared_event":
        sev = [(x["n"], f'{x.get("code", x["n"])} {x.get("label", "")}') for x in (cal or {}).get("severity", [])]
        crit = "".join(f'<option value="{esc(c)}">' for c in CRITERIA)
        return f"""<label>Business value {_select("business_value", bvs, cur.get("business_value"), required=True, pick="(pick a business value)")}{ferr(errs, "business_value")}</label>
<label class="wide">Label <input name="label" value="{esc(cur.get("label", ""))}" required maxlength="500">{ferr(errs, "label")}</label>
<label>Criterion <input name="criterion" list="criteria-d" value="{esc(cur.get("criterion", ""))}" maxlength="100">{ferr(errs, "criterion")}</label>
<datalist id="criteria-d">{crit}</datalist>
<label>Severity (you pick it) {_select("severity", sev, cur.get("severity"), required=True, pick="(pick a severity)", unknown="not in the scale")}{ferr(errs, "severity")}</label>"""
    raise KeyError(kind)


def _needs(kind, st):
    if kind == "feared_event" and not st.get("business_values"):
        return "Accept or add a business value first."
    if kind == "strategic_scenario" and not (st.get("risk_origins") and st.get("feared_events")):
        return "The study needs a risk origin (W2) and a feared event (W1) first."
    if kind == "operational_scenario" and not st.get("strategic_scenarios"):
        return "The study needs a strategic scenario (W3) first."
    return ""


def _summary(it):
    """One line of what the draft proposes, for items whose form cannot be shown yet."""
    for k in ("label", "origin", "name", "description"):
        if it.get(k):
            return it[k]
    return " / ".join(p.get("label", "") for p in it.get("paths") or [])


def _a(word):
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


def _item(sid, st, chk, session, it, state):
    did = it.get("id")
    kind = it.get("kind")
    mine = state.get("item") == did
    errs = state.get("errs") if mine else None
    typed = state.get("sticky") if mine else None
    note = form_note(state.get("msg", ""), errs) if mine else ""
    head = (f'<span class="badge draft">draft</span> <b>{esc(did)}</b> '
            f'<span class="kind">{esc(drafts.KIND_TITLE.get(kind, kind))}</span>')
    reject_only = (f'<form method="post" action="/s/{sid}/draft/{q(did)}/reject" class="inline">{csrf_input(session)}'
                   f'<button class="link danger">Reject</button></form>')
    need = _needs(kind, st)
    if need:
        return (f'<li class="draft-item" id="draft-{q(did)}">{head} {esc(_summary(it))}'
                f'<p class="hint">{esc(need)}</p>{reject_only}</li>')
    cur = typed if typed is not None else drafts.prefill(st, it)
    if kind in drafts.W1_KINDS:
        if kind == "feared_event" and typed is None:
            cur = dict(cur, severity=None)
        fields = _w1_fields(kind, cur, st, chk.get("cal"), errs)
    else:
        fields = views_ws.form_fields(drafts.KIND_SLUG[kind], cur, st, chk, errs, draft=True)
    extra = ""
    if kind == "feared_event" and (it.get("business_value") or it.get("business_value_label")):
        extra = (f'<p class="hint">The draft puts it on the business value '
                 f'"{esc(it.get("business_value") or it.get("business_value_label"))}".</p>')
    if kind == "strategic_scenario" and len(it.get("paths") or []) > 1:
        more = "".join(f'<li>{esc(p.get("label"))}{" (via " + esc(p.get("stakeholder")) + ")" if p.get("stakeholder") else ""}</li>'
                       for p in it["paths"][1:])
        extra = (f'<p class="hint">The first proposed path is in the form. The draft also proposes these paths; '
                 f'add them with Edit after accepting:</p><ul class="more-paths">{more}</ul>')
    reject_btn = (f'<button class="link danger" formaction="/s/{sid}/draft/{q(did)}/reject" formnovalidate>'
                  f'Reject</button>')
    return f"""<li class="draft-item" id="draft-{q(did)}">{head}{extra}{note}
<form method="post" action="/s/{sid}/draft/{q(did)}/accept" class="grid-form">{csrf_input(session)}{fields}
<div class="form-actions"><button>Accept as {esc(_a(drafts.KIND_TITLE.get(kind, kind)))}</button> {reject_btn}</div></form></li>"""


def panel(sid, st, chk, session, ctx, n):
    """The drafting panel of workshop n: route and model, limits, document picker, pending items."""
    info, state = ctx["info"], ctx.get("state") or {}
    all_items = [x for x in (ctx.get("drafts") or {}).get("items") or [] if isinstance(x, dict)]
    items = [x for x in all_items if drafts.ws_number(x) == n]
    docs = ctx.get("docs") or []
    priv = (f'<p class="hint"><span class="badge private">private</span> This study is private ({esc(ctx["why"])}): '
            'its documents and drafts may only go to the local route.</p>' if ctx["private"] else
            '<p class="hint">This study is not private: the local or the remote route may be used.</p>')
    refused = f'<p class="error" role="alert">{esc(info["refused"])}</p>' if info.get("refused") else ""
    err = f'<p class="error" role="alert">{esc(state["error"])}</p>' if state.get("error") else ""
    # no draft asked yet on this page: every document is ticked (the usual case is "draft from all of them")
    picked = set(state["docs"]) if "docs" in state else {d["id"] for d in docs}
    if docs:
        boxes = "".join(
            f'<label class="check"><input type="checkbox" name="docs" value="{esc(d["id"])}"'
            f'{" checked" if d["id"] in picked else ""}> {esc(d["name"])} '
            f'<small>{esc(d["type"])}, {d["chars"]:,} characters</small></label>' for d in docs)
    else:
        boxes = f'<span class="hint">No document yet. <a href="/s/{sid}/docs">Upload one in Documents</a>.</span>'
    form = f"""<form method="post" action="/s/{sid}/draft" class="draft-form">{csrf_input(session)}
<input type="hidden" name="ws" value="{n}">
<fieldset class="doc-pick"><legend>Documents to draft from</legend>{boxes}</fieldset>
<details class="paste"{" open" if state.get("text") else ""}><summary>Or paste text (at most {drafting.MAX_TEXT:,} characters)</summary>
<textarea name="text" rows="5" maxlength="{drafting.MAX_TEXT}" aria-label="text to draft from">{esc(state.get("text", ""))}</textarea></details>
<button>Draft {esc(drafts.WHAT[n])}</button></form>"""
    lists = ""
    by_kind = {}
    for it in items:
        by_kind.setdefault(it.get("kind"), []).append(it)
    for kind in drafts.KIND_ORDER:
        rows = by_kind.get(kind)
        if rows:
            title = TITLES.get(drafting.KIND_COLLECTION.get(kind, ""), kind)
            lists += (f'<h3>Proposed {esc(title.lower())} <span class="count">{len(rows)}</span></h3><ul class="drafts">'
                      + "".join(_item(sid, st, chk, session, it, state) for it in rows) + "</ul>")
    if items:
        batches = [b for b in (ctx.get("drafts") or {}).get("batches") or [] if isinstance(b, dict)
                   and str(b.get("ws") or "w1") == f"w{n}"]
        b = batches[-1] if batches else {}
        cover = ""
        if b.get("total"):
            cover = (f', {b.get("requests", "?")} request(s), {b.get("covered", 0):,} of {b.get("total", 0):,} '
                     f'characters of source text sent')
        src = (f'<p class="hint">Last draft: model {esc(b.get("model") or "?")}, route {esc(b.get("route") or "?")}, '
               f'{esc(str(b.get("at") or "").replace("T", " "))}{cover}. A draft never sets a severity, likelihood, decision, status or '
               f'level: you pick them, the engine computes the rest.</p>')
        if b.get("total") and b.get("covered", 0) < b["total"]:
            src += ('<p class="error">Only part of the selected text was sent (the per-draft request limit). '
                    'Select fewer documents, or raise the limit in Settings, to cover the rest.</p>')
        text_only = [it for it in items if it.get("kind") in drafting.TEXT_ONLY_KINDS]
        actions = ""
        if text_only:
            actions += (f'<form method="post" action="/s/{sid}/draft/accept-all" class="inline">{csrf_input(session)}'
                        f'<input type="hidden" name="ws" value="{n}"><button>Accept all {len(text_only)} text-only '
                        f'item{"s" if len(text_only) != 1 else ""}</button></form> ')
        actions += (f'<form method="post" action="/s/{sid}/draft/clear" class="inline">{csrf_input(session)}'
                    f'<input type="hidden" name="ws" value="{n}"><button class="link danger">Reject all draft items '
                    f'of W{n}</button></form>')
        note = ('<p class="hint">"Accept all" takes only items made of text (business values, supporting assets, '
                'stakeholders). Items that need your pick are accepted one by one.</p>' if text_only else "")
        lists = src + f'<div class="draft-actions">{actions}</div>{note}' + lists
    elif (ctx.get("drafts") or {}).get("unreadable"):
        lists = '<p class="error">The draft file of this study cannot be read.</p>'
    open_ = " open" if items or state else ""
    title = "Draft from documents or text" if n == 1 else f"Draft W{n} from documents"
    return f"""<section class="card draft-panel" id="draft"><details{open_}><summary><h2>{esc(title)}</h2></summary>
{route_line(info)}{limits_line(info)}{ssh_hint(info)}{priv}{refused}{err}{form}{lists}</details></section>"""


# ---------- documents ----------

def documents_page(sid, st, chk, docs, session, flash="", error="", private=False, why="", pdf_tool=None):
    if pdf_tool:
        pdf = "PDF text is extracted with pdftotext on this machine."
    else:
        pdf = "pdftotext is not on this machine's PATH, so PDF files are refused (nothing is installed by the app)."
    priv = (f'<p class="hint"><span class="badge private">private</span> This study is private ({esc(why)}): its '
            'documents stay on this machine and are sent only to the local drafting route.</p>' if private else
            '<p class="hint">Documents stay on this machine. Drafting sends their text to the route you pick in '
            'Settings.</p>')
    err = f'<p class="error" role="alert">{esc(error)}</p>' if error else ""
    rows = []
    for d in docs:
        rows.append(f"""<tr><td>{esc(d.get("name"))}</td><td>{esc(d.get("type"))}</td><td class="num">{esc(size_text(int(d.get("size") or 0)))}</td>
<td>{esc(str(d.get("uploaded") or "")[:16].replace("T", " "))}</td><td class="num">{int(d.get("chars") or 0):,}{" (cut)" if d.get("truncated") else ""}</td>
<td><form method="post" action="/s/{sid}/docs/{q(d.get("id"))}/delete" class="inline">{csrf_input(session)}<button class="link danger" data-confirm="Delete this document?">Delete</button></form></td></tr>""")
    table = (f'<div class="scroll"><table class="docs"><thead><tr><th>Name</th><th>Type</th><th>Size</th><th>Uploaded</th>'
             f'<th>Characters</th><th></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>' if rows else
             '<p class="hint">No document yet.</p>')
    content = f"""<h2 class="ws">Source documents</h2>
<section class="card" id="docs"><h2>Documents <span class="count">{len(docs)}</span></h2>{priv}{err}
<form method="post" action="/s/{sid}/docs" enctype="multipart/form-data" class="upload">{csrf_input(session)}
<label>File (.txt, .md, .docx, .pdf; at most 20 MB) <input type="file" name="file" accept=".txt,.md,.docx,.pdf" required></label>
<button>Upload</button></form><p class="hint">{esc(pdf)} The text is used only for drafting; the drafting panel of each
workshop lets you pick the documents to send.</p>{table}</section>"""
    return study_shell(sid, st, chk, "documents", content, session, flash)


# ---------- settings ----------

def _v(sticky, raw, *path, default=""):
    if sticky is not None:
        return sticky.get("_".join(path), default)
    d = raw
    for p in path:
        d = d.get(p) if isinstance(d, dict) else None
    return default if d is None else d


def settings_page(info, raw, path, mode_problem, session, flash="", errs=None, sticky=None, saved_problem=None):
    errs = errs or {}
    route = _v(sticky, raw, "route", default=info["route"] if not raw else raw.get("route", "off"))
    radios = "".join(
        f'<label class="check"><input type="radio" name="route" value="{r}"{" checked" if route == r else ""}> '
        f'{esc(label)}</label>' for r, label in (("off", "off: nothing is sent (default)"),
                                                 ("local", "local: an endpoint on 127.0.0.1"),
                                                 ("remote", "remote: any OpenAI-compatible URL (refused for private studies)")))
    lim = {k: _v(sticky, raw, "limits", k, default=v) for k, v in drafting.DEFAULT_LIMITS.items()}

    def num(name, label, value, lo, hi):
        return (f'<label>{esc(label)} <input type="number" name="{name}" value="{esc(value)}" min="{lo}" max="{hi}" '
                f'required>{ferr(errs, name)}</label>')
    mode = f'<p class="error" role="alert">{esc(mode_problem)}</p>' if mode_problem else ""
    note = form_note("", errs) if errs else ""
    problem = f'<p class="error">{esc(saved_problem)}</p>' if saved_problem else ""
    body = f"""<h1>Settings</h1>
<section class="card"><h2>Drafting route</h2>{route_line(info)}{problem}{mode}
<p class="hint">Stored in <code>{esc(path)}</code> (mode 600, outside the repository). Keys are never stored here:
name a key file (mode 600) instead.</p>{note}
<form method="post" action="/settings" class="grid-form settings">{csrf_input(session)}
<fieldset><legend>Route</legend>{ferr(errs, "route")}{radios}</fieldset>
<fieldset><legend>Local route (an ssh -L forward or a model on this machine)</legend><div class="grid-form">
{num("local_port", "Port on 127.0.0.1", _v(sticky, raw, "local", "port", default=11434), 1, 65535)}
<label>Path <input name="local_path" value="{esc(_v(sticky, raw, "local", "path", default="/v1"))}" maxlength="100">{ferr(errs, "local_path")}</label>
<label>Model <input name="local_model" value="{esc(_v(sticky, raw, "local", "model"))}" maxlength="200">{ferr(errs, "local_model")}</label>
<label class="wide">Key file (optional) <input name="local_key_file" value="{esc(_v(sticky, raw, "local", "key_file"))}" maxlength="500">{ferr(errs, "local_key_file")}</label>
<label class="wide">ssh command to show as a hint (never run by the app) <input name="local_ssh_hint" value="{esc(_v(sticky, raw, "local", "ssh_hint"))}" maxlength="400" placeholder="ssh -N -L 11434:127.0.0.1:11434 user@model-host">{ferr(errs, "local_ssh_hint")}</label>
</div></fieldset>
<fieldset><legend>Remote route (public studies only)</legend><div class="grid-form">
<label class="wide">Base URL <input name="remote_base_url" value="{esc(_v(sticky, raw, "remote", "base_url"))}" maxlength="500" placeholder="https://api.example.net/v1">{ferr(errs, "remote_base_url")}</label>
<label>Model <input name="remote_model" value="{esc(_v(sticky, raw, "remote", "model"))}" maxlength="200">{ferr(errs, "remote_model")}</label>
<label class="wide">Key file <input name="remote_key_file" value="{esc(_v(sticky, raw, "remote", "key_file"))}" maxlength="500">{ferr(errs, "remote_key_file")}</label>
</div></fieldset>
<fieldset><legend>Hard limits, per study</legend><div class="grid-form">
{num("limits_requests_per_minute", "Requests a minute", lim["requests_per_minute"], 1, drafting.CEILINGS["requests_per_minute"])}
{num("limits_max_output_tokens", "Output tokens a request", lim["max_output_tokens"], drafting.FLOORS["max_output_tokens"], drafting.CEILINGS["max_output_tokens"])}
{num("limits_context_tokens", "Model context (tokens)", lim["context_tokens"], drafting.FLOORS["context_tokens"], drafting.CEILINGS["context_tokens"])}
{num("limits_max_chunks", "Requests a draft", lim["max_chunks"], 1, drafting.CEILINGS["max_chunks"])}
</div></fieldset>
<div class="form-actions"><button>Save settings</button></div></form></section>"""
    return page("Settings", body, session, flash=flash)
