"""Server-rendered HTML shared by every page: the shell, login, study list, delete confirmation. Every piece of
study or user text goes through esc(). No inline script or style."""
import datetime
import html
import pathlib
import re
import urllib.parse

FLASH = {
    "removed": "Study moved to the trash folder.",
}
def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def q(x):
    return urllib.parse.quote(str(x), safe="")


def when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def level_classes(cal):
    """Level name -> CSS class (by rank order). The colours themselves come from /cal/<id>.css."""
    if not cal:
        return {}
    return {l["name"]: f"lvl-i{i}" for i, l in enumerate(sorted(cal["levels"], key=lambda l: l["rank"]))}


def csrf_input(session):
    return f'<input type="hidden" name="csrf" value="{esc(session.csrf)}">' if session else ""


NAV = {"en": {"home": "Home", "list": "Studies", "logout": "Log out",
              "sub": "Risk analysis, step by step", "skip": "Skip to the content"},
       "fr": {"home": "Accueil", "list": "Études", "logout": "Se déconnecter",
              "sub": "L'analyse de risques, pas à pas", "skip": "Aller au contenu"}}


def logo_path():
    """Where the brand logo goes, `app/static/brand/logo.svg`. It is supplied later; the file may not exist."""
    import atelier_app
    return pathlib.Path(atelier_app.STATIC_DIR) / "brand" / "logo.svg"


def logo_html():
    """The header logo (alt text CPLT, 30 px high) when the logo file exists, else nothing."""
    if not logo_path().is_file():
        return ""
    return '<img class="logo" src="/static/brand/logo.svg" alt="CPLT" height="30">'


def page(title, body, session=None, cal_id=None, flash="", lang="en", lang_path=None):
    """The shared page shell. `lang` ("en" or "fr") sets the language of the shell and of <html lang>; `lang_path`
    (a local path) adds the EN / FR switch, which links to that path with ?lang=."""
    n = NAV.get(lang, NAV["en"])
    cal_css = f'<link rel="stylesheet" href="/cal/{q(cal_id)}.css">' if cal_id else ""
    logout = ""
    if session:
        logout = (f'<form method="post" action="/logout" class="inline">{csrf_input(session)}'
                  f'<button class="link">{esc(n["logout"])}</button></form>')
    switch = ""
    if lang_path:
        on = ' aria-current="true" class="on"'
        switch = '<span class="lang" role="group" aria-label="Language">' + "".join(
            f'<a href="{esc(lang_path)}?lang={code}" lang="{code}" hreflang="{code}"{on if code == lang else ""}>'
            f'{code.upper()}</a>' for code in ("en", "fr")) + "</span>"
    note = f'<p class="flash" role="status">{esc(FLASH[flash])}</p>' if flash in FLASH else ""
    links = (f'<a href="/">{esc(n["home"])}</a><a href="/studies">{esc(n["list"])}</a>' if session else "")
    return f"""<!doctype html>
<html lang="{esc(lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} - Atelier</title>
<link rel="stylesheet" href="/static/app.css">
{cal_css}
<script src="/static/app.js" defer></script>
</head>
<body>
<a class="skip" href="#main">{esc(n["skip"])}</a>
<header class="top"><a class="brand" href="/">{logo_html()}Atelier</a><span class="sub">{esc(n["sub"])}</span>
<nav>{links}{switch}{logout}</nav></header>
<main id="main">
{note}
{body}
</main>
</body>
</html>
"""


def error_page(status, message, session=None):
    body = f'<h1>{status}</h1><p>{esc(message)}</p><p><a href="/">Back to the home page</a></p>'
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

STEP_LABEL = {"about": "About you", "risks": "Risks", "now": "Now and after", "results": "Results"}


def study_list(rows, session, flash=""):
    """rows: [(sid, st, mtime, step)]; step is the quick-path screen to reopen, or None when the file was not made
    with the quick path (it can only be deleted)."""
    trs = []
    for sid, st, mtime, step in rows:
        meta = (st or {}).get("study") if isinstance(st, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        name = meta.get("name") or "(no name)"
        if step:
            title = f'<a href="/quick/{sid}/{step}">{esc(name)}</a>'
            opener = f'<a href="/quick/{sid}/{step}">Open</a> '
        else:
            title, opener = esc(name), ""
        trs.append(f"""<tr>
<td>{title}</td>
<td>{esc(STEP_LABEL.get(step, "not a quick-path study"))}</td>
<td class="nowrap">{when(mtime)}</td>
<td class="actions">{opener}<a href="/s/{sid}/delete" class="danger">Delete</a></td>
</tr>""")
    table = ("<p class=\"empty\">No study yet. <a href=\"/quick/new\">Start one</a>.</p>" if not trs else
             "<table class=\"list\"><thead><tr><th>Name</th><th>Where you stopped</th><th>Last modified</th>"
             "<th>Actions</th></tr></thead><tbody>" + "".join(trs) + "</tbody></table>")
    body = f"""<h1>Studies</h1>
{table}
<p><a class="button" href="/quick/new">New study</a></p>"""
    return page("Studies", body, session, flash=flash)


def confirm_delete(sid, st, session):
    meta = st.get("study") if isinstance(st.get("study"), dict) else {}
    body = f"""<section class="card narrow"><h1>Delete this study?</h1>
<p><b>{esc(meta.get("name") or "(no name)")}</b></p>
<p>The file moves to the trash folder of the data directory; nothing else is removed.</p>
<form method="post" action="/s/{sid}/delete">{csrf_input(session)}<button class="danger">Delete</button>
<a href="/studies">Cancel</a></form></section>"""
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
