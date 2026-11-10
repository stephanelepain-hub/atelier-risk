# Web app (`app/`, iteration 2)

A local, single-user web interface over the engine. It runs on your own machine and listens on the loopback
address only. Levels, checks, registers and the Excel export all come from the engine. The app never computes
or sets a level itself.

## Run it

```bash
python3 app/serve.py
```

Python 3.12 or later, standard library only. The Excel export needs openpyxl, like the engine's.
The server prints its address (`http://127.0.0.1:8770/`) and a one-time login link. Open the link in your browser.

Options: `--port`, `--data-dir`, `--private-dir`. `python3 app/serve.py --help` lists them.

## Log in

- On first start the app creates a random login token in `<data-dir>/token` (mode 0600).
- Each start prints a one-time login link. It works once, within 10 minutes.
- Without the link, open `/login` and paste the token from the file.
- Logging in sets a session cookie (`HttpOnly`, `SameSite=Strict`). Sessions live in memory: a restart logs you
  out. A session expires after 12 hours without use.

## Where data lives

| Path | Content |
|---|---|
| `~/.local/share/atelier/` | data directory (mode 0700); override with `--data-dir` or `ATELIER_DATA_DIR` |
| `studies/<id>.json` | one study per file, in the engine's `atelier-study` format; the engine CLI reads it as is |
| `studies/<id>.json.bak` | the previous version, rewritten on every save |
| `studies/trash/` | deleted studies (delete moves the file here, it does not erase it) |
| `private/` | private calibrations, passed to the engine as `ATELIER_PRIVATE_DIR` (mode 0700) |
| `token` | the login token (mode 0600) |

Saves are atomic: the app writes a temporary file in the same directory, then renames it over the old one.

## What it does

- Study list with calibration, last change and a check badge; new, open, rename, duplicate, delete.
- Import a study JSON file (5 MB at most), or load the guide example. The engine checks the study on import.
- Workshop 1 editor: business values, supporting assets, feared events (severity picked from the calibration's
  scale), security baseline. Links are picked from existing elements; ids are generated.
- Workshop 2 editor: risk origins with their target objective, motivation and resources (1-4), decision
  (selected, monitoring, discarded) and the feared events they aim at.
- Workshop 3 editor: ecosystem stakeholders (category, dependence, penetration, maturity, trust, critical flag)
  and strategic scenarios (risk origin, feared events, attack paths with their stakeholder). The engine computes
  no stakeholder threat level, so the app shows none.
- Workshop 4 editor: operational scenarios on a strategic scenario path, likelihood picked from the calibration's
  scale, description.
- Workshop 5 editor: risks (linked to a strategic or an operational scenario, likelihood now and at target,
  treatment, owner) and security measures (risks, owner, due date, status), with the two grids below.
- Every link is picked from existing elements of the right type; ids are generated. A value outside 1-4 is
  refused by the engine's check and the form shows the engine's message; the file is not changed.
- Severity of strategic scenarios and risks is never typed. The engine checks it (the highest severity of the
  feared events, guide p.49; a risk takes its scenario's, p.62 and p.65), and the app stores the value that the
  engine's check accepts. A stale value (after a feared event changes) shows the engine's error next to the
  engine's value, and one button takes the values from the engine.
- Checks panel on every study page: the engine's errors and warnings after every save. Each one links to the
  row it names, in the right workshop tab, and that row is highlighted.
- Overview: a study progress strip with, per workshop, the number of objects and of the engine's open errors
  and warnings.
- Risk register and grids: the engine's register, and the calibration's severity x likelihood grid now and at
  target, side by side, each risk in its cell, coloured with the calibration's level colours. A study with
  errors gets no register, as with the engine CLI.
- Downloads: the study JSON, and the engine's Excel export.

## Security model

- Binds `127.0.0.1:8770` by default. A non-loopback address is refused unless `--allow-remote` is given.
- Requests whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` are refused (DNS rebinding).
- Every page except the login needs the session cookie. Every form carries a CSRF token, checked on each POST.
- Wrong tokens are refused; ten failures within a minute lock the login for that minute.
- Strict Content-Security-Policy (`default-src 'none'`, scripts and styles from the app only, no inline code),
  `X-Frame-Options: DENY`, `nosniff`, no referrer, no caching.
- Static files come from a fixed list; there is no directory listing. Study ids are generated slugs checked
  against a fixed pattern before any path is built.
- All study text is HTML-escaped. Uploads are JSON only, capped at 5 MB, and checked before they are stored.
- The server log never records query strings, so one-time login links do not end up in it.

## Code layout

| Module | Role |
|---|---|
| `app/serve.py` | entry point |
| `app/atelier_app/config.py` | settings and their defaults (environment, then the user's home) |
| `app/atelier_app/engine.py` | the only module that calls the engine |
| `app/atelier_app/calibrations.py` | calibration lookup |
| `app/atelier_app/storage.py` | study files |
| `app/atelier_app/auth.py` | token, one-time links, sessions, CSRF |
| `app/atelier_app/editors.py` | workshop 2 to 5 forms: fields, link checks, ids |
| `app/atelier_app/app.py`, `views.py`, `views_ws.py`, `web.py`, `server.py` | routes and handlers, HTML (workshop 2 to 5 editors in `views_ws.py`), HTTP plumbing, the server |
| `app/static/` | the CSS and JS files the pages load |
| `app/tests/` | unit tests (`python3 -m unittest discover -s app/tests -t .`) and `e2e.py` (end-to-end run) |

## Limits of this iteration

- Atelier is a single-user local app today. Sessions carry a user name and handlers get their study store
  through one function (`App.store_for`), so several users can be added later without changing URLs.
- No HTTPS: it relies on staying on the loopback address.
- The engine has no function that returns a derived severity; the app gets it by asking the engine's own check
  which of 1 to 4 it accepts (`engine.derived_severity`). When the engine gains such a function, only that
  function changes.
- No relevance aid for risk origins and no stakeholder threat level: the engine does not compute them yet.
- Two browser tabs editing the same study: the last save wins (the `.bak` keeps the version before it).
- No document upload and no drafting by a model yet.
