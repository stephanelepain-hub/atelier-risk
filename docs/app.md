# Atelier web app (public edition)

A local, single-user web interface that gives a plain-language first view of your main cyber risks, following the
ANSSI EBIOS Risk Manager method. It runs on your own machine and listens on the loopback address only. Levels,
checks, registers, maps and the Excel export all come from the engine (`engine/atelier_engine/`). The app never
computes or sets a level itself.

## Honesty statement

The text below is written once, in `engine/atelier_engine/quick.py` (`HONESTY`, English and French). The home page,
every results page and the top of the Excel export show it.

> These results come only from your answers. They are a first view, as good as the answers you gave.

French: « Ces résultats viennent uniquement de vos réponses. C'est une première vue, aussi juste que vos réponses. »
It is shown once on the home page and once on the results page. A test pins the English text by its hash.

## Run it

The launcher starts the server in the background and prints the one-time login link. It opens nothing else.

```bash
python3 app/atelier.py start      # prints http://127.0.0.1:8770/ and the one-time login link
python3 app/atelier.py status     # running or not, and where (exit 0 running, 3 not)
python3 app/atelier.py stop
python3 app/atelier.py token --new  # a new login token (mode 0600); restart for it to take effect
```

`start` takes `--port`; every command takes `--data-dir` before the command name. The server log goes to
`<data-dir>/server.log` (mode 0600); the login link is never written there. `stop` signals only the process the
launcher started (it checks the process runs this checkout's `serve.py`).

In the foreground, without the launcher: `python3 app/serve.py` (options: `--port`, `--data-dir`, `--url-file`;
`--help` lists them). The server prints its address (`http://127.0.0.1:8770/`) and a one-time login link. Open the
link in your browser.

Python 3.12 or later, standard-library server. The Excel download needs `openpyxl`, like the engine. Without it the
app still runs: the Excel download answers "needs openpyxl" (HTTP 501) and the study-file download works.

### systemd user unit (template, not installed)

To start it with your session, adapt the path and save it as `~/.config/systemd/user/atelier.service`, then
`systemctl --user daemon-reload && systemctl --user start atelier`. The one-time link lands in
`$XDG_RUNTIME_DIR/atelier-login-url` (mode 0600); read it once, or log in with the token file.

```ini
[Unit]
Description=Atelier (local EBIOS Risk Manager first view)

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/path/to/atelier/app/serve.py --port 8770 --url-file %t/atelier-login-url
Restart=on-failure
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=%h/.local/share/atelier %t
UMask=0077

[Install]
WantedBy=default.target
```

## Log in

- On first start the app creates a random login token in `<data-dir>/token` (mode 0600).
- Each start prints a one-time login link. It works once, within 10 minutes.
- Without the link, open `/login` and paste the token from the file.
- Logging in sets a session cookie (`HttpOnly`, `SameSite=Strict`). Sessions live in memory: a restart logs you
  out. A session expires after 12 hours without use.

## Public mode

An optional mode for an internet server (for example for beta testers). The default, local mode is unchanged.
It is meant to sit behind a reverse proxy that serves HTTPS (the cookies are `Secure`) and passes requests to the
app on the loopback address.

```bash
python3 app/serve.py --public [--invite-code-file PATH] [--behind-proxy] [--data-dir DIR] [--port 8770]
```

| Flag | Meaning |
|---|---|
| `--public` | public mode: no token login, an anonymous private workspace for each visitor |
| `--invite-code-file PATH` | a file with the invite code on its first line. The server starts only when the file is readable by its owner alone (for example `chmod 600`). Without this flag no code is asked. Needs `--public` |
| `--behind-proxy` | take the client address for the join rate limit from `X-Real-IP`, set by the local reverse proxy; an absent or invalid header falls back to the socket address. Without the flag the socket address is used |

In code: `App(data_dir, port=..., public=True, invite_code="...", behind_proxy=False)`; `invite_code=None` asks for no code.
The `Host` header must be one the app accepts: have the proxy pass `Host: 127.0.0.1:<port>`, or add the public name
with `--allow-remote --allowed-host name` (the bind address stays on loopback).

**Join.** A visitor without a workspace sees `/join`: one line about Atelier, the honesty statement, a Start button and,
when a code is set, an Invite code field. The form carries the same anti-forgery pair as the local login form (hidden
field `pre` and a matching cookie). A right code (compared in constant time) creates a workspace, sets the session
cookie and redirects to `/`. A wrong code gives 403 and a kind message; more than 10 wrong codes from one client address
within 10 minutes give 429 for that client. Every other page redirects to `/join` (303) while there is no valid
workspace; `/how` and the static files stay open. `/login`, `/login/once`, `/login/link` and `/logout` answer 404, and
no token file is created.

**What is stored.** Each workspace is a random 256-bit id kept in the cookie `atelier_session`
(`HttpOnly; Secure; SameSite=Lax; Path=/`, plus `Max-Age` of 30 days so a visit the next day finds the workspace). On disk only its SHA-256 names the folder:

| Path | Content |
|---|---|
| `<data>/workspaces/<sha256 hex>/` | one workspace (mode 0700) |
| `.../last_seen` | empty file; its modification time is the last visit (any page updates it) |
| `.../studies/<id>.json`, `.json.bak` | the visitor's studies, same format as local mode |

The form token (CSRF) is derived from the cookie value, so it needs no server memory and survives a restart. A study
URL of another workspace answers 404. In public mode, Delete removes a study and its `.bak` for good (there is no
trash folder).

**Clean-up.** `App.purge_idle(days=30)` deletes every workspace whose `last_seen` is older than `days`; the server runs
it at start and then every hour. `POST /forget` (with the form token) deletes the visitor's workspace at once, clears
the cookie and shows a goodbye page. The header shows "Delete my data" (FR "Effacer mes données") in place of "Log out".

**Limits.** 20 studies per workspace (the 21st shows a kind page and the New study form shows it too, HTTP 409);
5000 workspaces in total (`/join` shows a kind "We are full for now" page, HTTP 503). Request bodies stay capped at 5 MB.

**Continue from a saved file.** The studies page has "Open a saved file". A small script (`app/static/app.js`, same
origin, the Content-Security-Policy is unchanged) reads the chosen file and posts its text as the urlencoded field
`study` to `POST /quick/open` (with the form token; the route exists in public mode only). The file is at most 512 KB
(larger: 413). Only a study made with the quick path is taken in, as written by "Download the study file": the app checks the answers
and builds the study again from them, so what is stored has the engine's own shape. Anything else gives 400 and a
kind message. The study lands in the visitor's workspace with a new id and opens at the screen where it was saved.

**Send my study to CPLT.** When `publisher.json` has an `email`, the results page ends with one card, "Want a deeper
look?": a form `POST /quick/<id>/share` (with the form token) with `email` (required, checked), `message` (optional, at
most 500 characters) and a `consent` box that starts unticked. A missing consent or a bad email gives a kind 400 page and
stores nothing. The copy goes outside the workspace:

| Path | Content |
|---|---|
| `<data>/shared/` | mode 0700 |
| `.../<UTC date>-<16 random hex>/` | one share (mode 0700) |
| `.../study.json` | the quick study, the same text as "Download the study file" (mode 0600) |
| `.../contact.json` | `email`, `message`, `lang`, `created` (ISO UTC), `study_name` (mode 0600) |

The app sends no email and makes no outbound call: the publisher reads the folders and replies from their own mailbox.
Limits: 3 shares per workspace per UTC day (the 4th gets a kind 429 page; the dates are kept in the file `shares` of the
workspace) and 2000 shared folders in total (then a kind "full for now, write to <email>" page, HTTP 503). The thank-you
page says what happens next and the 12 months. `App.purge_shared(days=365)` deletes the shared folders older than that
(by the date in the name, or by the folder's own time when older); the server runs it at start and every hour, next to
`purge_idle`. Delete my data keeps the shared copies (they were sent on purpose): the privacy page says to write to the
publisher address to remove one. Without an `email` in `publisher.json`, or in local mode, the card is absent and
the route answers 404.

**Anonymous counts.** One JSON line per event is appended to `<data>/stats/<YYYY-MM>.jsonl` (folder 0700, file 0600):
`{"day": "YYYY-MM-DD", "event": ...}` plus only catalogue ids and short answer words.

| Event | Fields |
|---|---|
| `visit` | `source`: `linkedin`, `x`, `github`, `cplt`, `search`, `other` or `direct` (the kind of site in the Referer; the address itself is never kept). Written when a new visitor opens the start page; link previews, crawlers and scripts (by user agent, never stored) are not counted |
| `joined` | `source` (carried from the start page in a hidden field), when a workspace is created with the invite code |
| `study_started` | `tools` (tool ids), `sensitivity`, `downtime` (answer words, `dont_know` or `unanswered`) |
| `step_reached` | `step` (`about`, `risks`, `now`, `results`; each counted once per study, when it is first reached) |
| `risk_discarded` | `risk` (a catalogue id, when a ticked risk is unticked) |
| `risk_added` | none (the text is never kept) |
| `measures` | `measures`: measure id to `in`, `extra` or `none`, once, on reaching the results |
| `download` | `kind`: `xlsx` or `study` (`maps` is allowed in the file format; the app has no separate maps download yet, so it writes none) |
| `shared`, `forget` | none |

`stats.clean` builds each line from this list, so a line holds no workspace id or hash, no study id, no IP address, no
browser name, no time finer than the day, no typed text and no email. Writing a count never stops a page. Read the counts
with `cd app && python3 -m atelier_app.stats <data_dir> [--month YYYY-MM] [--since YYYY-MM-DD]`: it prints start-page visits and
invite codes entered by source, studies started, studies that reached
each step, the most discarded risks, the most chosen measures, downloads and shares (all months without `--month`). Local
mode writes no counts.

**How it works.** In public mode the "Your data" section says that the answers stay in a private space that only the
browser can open, cleared after 30 days without a visit or at any time with Delete my data.

### Cloud infrastructure

The first screen has a tool "Servers, apps or data on AWS, Google Cloud or Microsoft Azure" (id `cloud_infra`). It
implies the pack `cloud-infra`, which has the same structure as the other packs: it is catalogue content only, with no new
engine path, scale, screen, origin or objective (catalogues/README.md lists the risks, their `refs` to the CERT-FR report
CERTFR-2025-CTI-001, and the licence note). The three provider names appear only in the tool's label and example, and here.

## Where data lives

| Path | Content |
|---|---|
| `~/.local/share/atelier/` | data directory (mode 0700); override with `--data-dir` or `ATELIER_DATA_DIR` |
| `studies/<id>.json` | one study per file, in the engine's `atelier-study` format (docs/study-format.md); the quick answers are under its `quick` key |
| `studies/<id>.json.bak` | the previous version, rewritten on every save |
| `shared/`, `stats/` | public mode only: studies sent to the publisher, anonymous counts (see Public mode) |
| `studies/trash/` | deleted studies (delete moves the file here, it does not erase it) |
| `tmp/` | private temporary files of the Excel export, removed right after each download |
| `server.log`, `run/` | the launcher's server log and pid file |
| `token` | the login token (mode 0600) |
| `workspaces/` | public mode only, see Public mode |

Saves are atomic: the app writes a temporary file in the same directory, then renames it over the old one.

## What it does

- **Home** (`/`): one title (about 15 minutes), one line, one Start button and the honesty statement.
  Below, the studies to pick up again, and a link to all saved studies.
- **The four screens** (`/quick/new`, then `/quick/<study>/about|risks|now|results`), described in
  docs/quick-path.md: About you, Risks, Now and after, Results. Each saves what you entered and builds a normal
  study that the engine checks.
- **Now and after**: one compact row per kept risk (severity and likelihood), then each measure once for the whole
  business, under a few plain headings (`labels.MEASURE_GROUP`), with three choices: Later, Already in place, Add to
  my plan. The answer counts for every risk that lists the measure.
- **Results**, in this order: one positive summary line ("With 5 actions, 4 of your 7 risks move to Low or
  Moderate."), your top actions in three short lines (To strengthen / Based on / Next step, `findings.py`; the
  "Rough guide" label above them says the time and who are estimates), the two risk maps with a numbered list of
  the risks (plain numbers 1..n; the codes stay in Expert mode and in Excel), then two collapsed sections ("See all
  your risks", "Already in place (n)"), the confidence with one plain line, the honesty statement, the assumptions
  (collapsed), the downloads, and the summary line again at the very end. At most 350 visible words above the
  collapsed sections for a typical study (a test checks it). "Based on" quotes the business (a tool used, how
  sensitive the information is, how soon a stop hurts), then the catalogue's own reason for the risk; it never
  quotes the likelihood. Levels and severities appear in plain words (`labels.py`: Low / Moderate / High;
  Minor / Noticeable / Serious / Very serious). The engine and the calibration keep the ANSSI terms; the mapping
  lives in the app and changes no number.
- **How it works** (`/how`, EN and FR, linked from every page): the method, the screens and the workshops, where
  the numbers come from, the confidence figure, the honesty statement, your data, the independence notice.
- **Expert switch** (page header, off by default): `POST /expert` (CSRF token, field `on` = `1` or `0`, optional
  `next`) sets the cookie `expert` (path `/`, HttpOnly, SameSite=Lax) and redirects back. On: an "Expert mode on"
  badge, "Open in expert view" on the results page and a link to the overview in the studies list. Off: no link to
  the expert screens anywhere. The expert screens themselves (`/s/<study>`, `/s/<study>/w1` to `w5`, `/register`,
  `/el/<id>`, `/severities`, rename, duplicate) answer either way, and a quick study changed there shows a note on
  the quick screens.
- **Saved studies** (`/studies`): reopen a study where you stopped, or delete it (it moves to the trash folder).
- **English and French**: `?lang=en|fr`, kept in a cookie; the quick-path pages and the Excel workbook follow it.
- **Calibration**: the published `anssi-v1.5` only (`calibrations/anssi-v1.5.json`). Grid, legend and colours follow
  the levels it declares. The app reads no other calibration.

## Security model

- Binds `127.0.0.1:8770` by default. A non-loopback address is refused unless `--allow-remote` is given.
- Requests whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` are refused (DNS rebinding).
- Every page except the login and `/how` needs the session cookie. Every form carries a CSRF token, checked on each POST.
- Wrong tokens are refused; ten failures within a minute lock the login for that minute.
- Strict Content-Security-Policy (`default-src 'none'`, scripts and styles from the app only, no inline code),
  `X-Frame-Options: DENY`, `nosniff`, no referrer, no caching.
- Static files come from a fixed list; there is no directory listing. Study ids are generated slugs checked
  against a fixed pattern before any path is built.
- All study and user text is HTML-escaped. Request bodies are capped at 5 MB and must be URL-encoded forms: there is
  no file upload.
- The server log never records query strings, so one-time login links do not end up in it.

## Code layout

| Module | Role |
|---|---|
| `app/serve.py` | entry point |
| `app/atelier.py` | launcher: start, stop, status, token --new |
| `app/atelier_app/app.py` | routes, login and CSRF gates, security headers, study list, downloads |
| `app/atelier_app/quick_routes.py`, `views_quick.py` | quick-path handlers and pages (home, four screens, EN and FR text) |
| `app/atelier_app/views.py` | shared page shell (header with the Expert switch), login page, study list, delete confirmation, the expert study pages |
| `app/atelier_app/expert_routes.py`, `editors.py`, `views_ws.py` | expert mode: study overview, workshops 1 to 5, register, severities, locate, rename, duplicate |
| `app/atelier_app/views_how.py` | the "How it works" page |
| `app/atelier_app/labels.py`, `findings.py` | plain names for severities and levels, one-line "how long, who" per measure, the three-line findings and the closing line |
| `app/atelier_app/engine.py` | the only module that calls the engine |
| `app/atelier_app/calibrations.py` | calibration lookup: the published calibration only |
| `app/atelier_app/storage.py` | study files |
| `app/atelier_app/auth.py` | token, one-time links, sessions, CSRF |
| `app/atelier_app/workspaces.py`, `views_public.py` | public mode: workspaces, join limit, clean-up; join, goodbye, limit pages and the saved-file form |
| `app/atelier_app/shares.py`, `views_share.py`, `stats.py` | public mode: studies sent to the publisher (folders, limits, purge) and their card and pages; anonymous counts and `python3 -m atelier_app.stats` |
| `app/atelier_app/config.py`, `web.py`, `server.py` | settings, HTTP plumbing, the server |
| `app/static/` | the CSS and JS files the pages load |
| `app/tests/` | unit tests (`python3 -m unittest discover -s app/tests -t .`); `no_openpyxl.py` runs the same tests as if openpyxl were missing (the Excel tests skip) |

## Limits

- A single-user local app. Sessions carry a user name and handlers get their study store through one function
  (`App.store_for`), so several users could be added later without changing URLs.
- No HTTPS: it relies on staying on the loopback address.
- It is a first view built from your answers and a public list of typical risks. It is not an audit.
- Two browser tabs editing the same study: the last save wins (the `.bak` keeps the version before it).
- In local mode the study list and the login page are in English only (in public mode the study list and the new pages follow the language).


### Publisher footer

If `<data_dir>/publisher.json` exists and is valid, every page ends with one line saying who offers this instance,
with a link, and an optional feedback link:

```json
{"name": "CPLT", "url": "https://cplt.tech", "feedback_url": "https://cplt.tech/contact", "email": "hello@cplt.tech"}
```

Both URLs must be https; `email` (optional) is shown as a mail link and turns on "Send my study to CPLT" in public mode. A
missing or invalid file shows no footer. The footer reads "Atelier is offered by NAME, site · email." then, when set, the
feedback line and the privacy link joined by a middle dot (the privacy link exists in public mode).
