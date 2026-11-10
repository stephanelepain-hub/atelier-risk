# Web app (`app/`, iteration 5)

A local, single-user web interface over the engine. It runs on your own machine and listens on the loopback
address only. Levels, checks, registers and the Excel export all come from the engine. The app never computes
or sets a level itself.

## Run it

The launcher starts the server in the background and prints the one-time login link. It opens nothing else.

```bash
python3 app/atelier.py start      # prints http://127.0.0.1:8770/ and the one-time login link
python3 app/atelier.py status     # running or not, where, and the drafting route (exit 0 running, 3 not)
python3 app/atelier.py stop
python3 app/atelier.py token --new  # a new login token (mode 0600); restart for it to take effect
```

`start` takes `--port` and `--private-dir`; every command takes `--data-dir` before the command name. The server
log goes to `<data-dir>/server.log` (mode 0600); the login link is never written there. `stop` signals only the
process the launcher started (it checks the process runs this checkout's `serve.py`).

In the foreground, without the launcher: `python3 app/serve.py`.

Python 3.12 or later, standard-library server. Study Excel export and review workbook import/export need
openpyxl, like the engine. Without it the app still runs: study Excel download answers "needs openpyxl"
(HTTP 501), review import reports the missing dependency, and other study features work.
The server prints its address (`http://127.0.0.1:8770/`) and a one-time login link. Open the link in your browser.

Options: `--port`, `--data-dir`, `--private-dir`, `--url-file`. `python3 app/serve.py --help` lists them.

### README snippet

```markdown
## Web app
python3 app/atelier.py start   # then open the one-time link it prints
python3 app/atelier.py stop
Drafting is off until you pick a route in Settings. See docs/app.md.
```

The same lines are in `app/README.md`.

### systemd user unit (template, not installed)

To start it with your session, adapt the path and save it as `~/.config/systemd/user/atelier.service`, then
`systemctl --user daemon-reload && systemctl --user start atelier`. The one-time link lands in
`$XDG_RUNTIME_DIR/atelier-login-url` (mode 0600); read it once, or log in with the token file.

```ini
[Unit]
Description=Atelier (local EBIOS Risk Manager workbench)

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/path/to/atelier-risk/app/serve.py --port 8770 --url-file %t/atelier-login-url
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

## Where data lives

| Path | Content |
|---|---|
| `~/.local/share/atelier/` | data directory (mode 0700); override with `--data-dir` or `ATELIER_DATA_DIR` |
| `studies/<id>.json` | one study per file, in the engine's `atelier-study` format; the engine CLI reads it as is |
| `studies/<id>.json.bak` | the previous version, rewritten on every save |
| `studies/trash/` | deleted studies (delete moves the file here, it does not erase it) |
| `drafts/<id>.json` | pending draft items of a study (see Drafting), never inside the study file |
| `documents/<id>/` | a study's source documents (mode 0700): the file as uploaded, its extracted text, its metadata (each 0600) |
| `private/` | private calibrations, passed to the engine as `ATELIER_PRIVATE_DIR` (mode 0700) |
| `reviews/<id>/` | review upload and atomic state snapshot; private directory (0700), files (0600) |
| `settings.json` | drafting route and limits (mode 0600; absent means drafting is off); override with `ATELIER_SETTINGS`. The iteration 3 `drafting.json` is still read when there is no `settings.json` |
| `drafting-log.jsonl` | one line per drafting request (mode 0600), without any document text |
| `server.log`, `run/` | the launcher's server log and pid file |
| `token` | the login token (mode 0600) |

Saves are atomic: the app writes a temporary file in the same directory, then renames it over the old one.

## What it does

- Home page (`/`) with the honesty statement and three ways in: start from scratch, start with a document, or import
  an existing risk analysis (Reviews). The **quick path** (`/quick/new`, then four screens: About you, Risks, Now and
  after, Results) is described in docs/quick-path.md. It saves at each step and builds a normal study that opens in
  the screens below ("expert mode").
- Study list (`/studies`) with calibration, last change and a check badge; new, open, rename, duplicate, delete.
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
- Risk register and grids: the engine's register and inline SVG maps now and at target, side by side. The
  engine renders both maps with the calibration's `map_orientation` (severity rows by default, or likelihood
  rows). Expand "Tabular risk grids" for the accessible table alternative (severity rows). A study with errors
  gets no register, as with the engine CLI. Malformed colour values use a neutral fallback before inline rendering.
- Downloads: the study JSON, and the engine's Excel export.
- A refused form comes back with what you typed. The message (the app's, or the engine's refusal of a value
  outside 1-4) sits next to the field it is about, and the study file is not changed.

## Calibrations, public and private

- The calibration picker of a new study lists every calibration the engine knows: the public ones of the
  repository and the private ones of `ATELIER_PRIVATE_DIR`, each with a `public` or `private` badge, its name
  and its number of risk levels. A calibration the engine refuses to load is listed, disabled, with the reason.
- The study list, the study header and the overview show which calibration a study uses, and the overview says
  whether the study is private.
- Grid, legend, counts and colours follow the levels the calibration declares (3 for `anssi-v1.5`, 4 or more
  for a calibration that declares them). Colours come from the calibration file.
- A study's calibration is never switched in place: that would change every level without notice. The overview
  offers "Duplicate with calibration X" for each other calibration; the engine then checks the copy against X.
- A study is private when its calibration is private, when you mark it confidential (overview), or when its
  calibration is not available. The copy of a private study is marked confidential, so duplicating it on a public
  calibration does not make it public.

## Documents

- Each study has a Documents tab: upload `.txt`, `.md`, `.docx` or `.pdf` files of 20 MB at most. The list shows
  name, type, size, upload date and the number of characters extracted; a document can be deleted.
- Text is extracted on this machine. `.docx`: the standard library reads `word/document.xml` (paragraphs, tabs,
  line breaks, table rows); a document type declaration, an oversized or an over-compressed archive is refused.
  `.pdf`: `pdftotext` (poppler) if it is on `PATH`, run without a shell and with a time limit; without it PDFs
  are refused with a message saying so. The app installs nothing. A scanned PDF without a text layer is refused.
- Deleting a study moves its documents folder to `studies/trash/` with it.
- Documents never leave the machine except as drafting requests, which follow the route policy below: the
  documents of a private study only go to the local route.

## Drafting (workshops 1 to 5)

Rule of trust: the model drafts, the engine computes and checks, you validate. A draft never sets a level.

- Every workshop tab has a drafting panel. It shows the active route, the model and the endpoint, the limits,
  and (local route) the ssh command you set as a hint. Tick the documents to draft from (all are ticked by
  default) and, if you like, paste text. The model's proposals are listed, marked `draft`, outside the study.
  Each one has its own form, pre-filled with the drafted text: edit it and accept it, or reject it.
- What a draft may propose, per workshop. Everything else in the model's answer is dropped:

  | Workshop | Proposals | Never drafted: you pick it, or the engine computes it |
  |---|---|---|
  | W1 | business values (label, nature), supporting assets (label, business values), feared events (label, business value, criterion) | severity, owner |
  | W2 | risk origins with their target objective and feared events | decision, motivation, resources |
  | W3 | stakeholders (name, category); strategic scenarios (risk origin, feared events, attack paths with their stakeholder) | dependence, penetration, maturity, trust, critical; the scenario's severity (engine, guide p.49) |
  | W4 | operational scenario descriptions on a strategic scenario path | likelihood |
  | W5 | measure proposals and the risks they treat | status, owner, due date, treatment |

- In each accept form the fields above start empty ("you pick the decision" and so on), so nothing is
  pre-selected for you. The form goes through the same checks as the workshop's own add form.
- "Accept all" exists only for proposals made of text alone: business values, supporting assets and
  stakeholders. Everything else is accepted one by one.
- A new draft does not repeat proposals already in the study or already pending. A rejected proposal may come
  back in a later draft.
- Prompts: one file per workshop in `app/prompts/` (`w1.md` to `w5.md`), written in our own words from the ANSSI
  guide v1.5 with its printed page numbers, and an example of the expected JSON. The prompt goes as the system
  message; a short summary of the study so far (ids and labels the model may refer to, never a level) and the
  source text go as the user message.
- Model answers: the app reads the JSON even when the model wraps it in prose, code fences or a thinking block,
  checks it against the workshop's schema and keeps only the allowed fields. When nothing usable remains, the
  panel says "The model's answer could not be used" and nothing is stored. Raw answers are never stored.

### Routes (Settings page, or `settings.json`)

```json
{"route": "local",
 "local": {"port": 11434, "path": "/v1", "model": "<model name>", "key_file": "",
           "ssh_hint": "ssh -N -L 11434:127.0.0.1:11434 <user>@<model host>"},
 "remote": {"base_url": "https://<provider>/v1", "model": "<model name>", "key_file": "~/.config/atelier/model.key"},
 "limits": {"requests_per_minute": 6, "max_output_tokens": 2048, "context_tokens": 8192, "max_chunks": 4}}
```

- `off` (default): nothing is sent anywhere.
- `local`: an OpenAI-compatible endpoint on `http://127.0.0.1:<port><path>`, typically the local end of an
  `ssh -L` forward to a model on your own network. You open the forward yourself; the app shows `ssh_hint` as
  text and never runs ssh or any other command for drafting.
- `remote`: any OpenAI-compatible URL. Refused for private studies, in code, before anything is sent.
- `key_file` (optional) names a file holding the API key on one line, mode 0600; a file readable by others is
  refused. The key is sent only in the `Authorization` header; it is never logged, stored or shown.
- Requests ignore proxy settings and do not follow redirects, so an endpoint cannot redirect a request.
- Local requests use `reasoning_effort: "none"`, a maximum of 4096 output tokens and a timeout of at least
  360 seconds (up to 600 when configured). They run one at a time across studies and settings changes.
  The submit button says "Drafting..." and a status message stays visible while waiting; keep the page open.
  Open the loopback forward yourself while using the app and close it afterwards.
- The Settings page writes the file atomically with mode 0600 and warns when its mode is looser.

### Limits and log

- Per study, enforced in code: at most `requests_per_minute` requests a minute (a draft that would pass it is
  refused, nothing sent); `max_output_tokens` sent as `max_tokens` on every request. Hard ceilings: 60 requests
  a minute, 8192 output tokens.
- The source text is cut into chunks that fit `context_tokens` minus the output tokens, the prompt and the study
  summary, at 4 characters a token (an estimate: there is no tokenizer in the standard library). At most
  `max_chunks` requests are sent per draft; when the text needs more, the panel says how much was sent.
  If the prompt, summary and output allowance already exhaust the configured context, the request is refused
  before sending anything; raise the context limit or lower the output limit.
- `drafting-log.jsonl` gets one line per request and per refused attempt: time, study id, workshop, route,
  model, endpoint, outcome, request number, source size in characters, number of documents, max output tokens,
  prompt and completion tokens (from the endpoint, or estimated and marked so), items read, latency. Never
  document text, never the model's answer, never the key.

## Security model

- Binds `127.0.0.1:8770` by default. A non-loopback address is refused unless `--allow-remote` is given.
- Requests whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` are refused (DNS rebinding).
- Every page except the login needs the session cookie. Every form carries a CSRF token, checked on each POST.
- Wrong tokens are refused; ten failures within a minute lock the login for that minute.
- Strict Content-Security-Policy (`default-src 'none'`, scripts and styles from the app only, no inline code),
  `X-Frame-Options: DENY`, `nosniff`, no referrer, no caching.
- Static files come from a fixed list; there is no directory listing. Study ids are generated slugs checked
  against a fixed pattern before any path is built.
- All study, document and draft text is HTML-escaped. Study imports are JSON only, capped at 5 MB. Document
  uploads are capped at 20 MB, typed by extension, and the uploaded file name is only displayed, never used in
  a path (document ids are generated). Review workbook uploads also have a 20 MB cap and a bounded multipart envelope.
- The server log never records query strings, so one-time login links do not end up in it.

## Review mode

Open **Reviews**, then **New review**. Upload an existing `.xlsx` risk analysis (20 MB maximum), pick a public
or private calibration, and optionally choose a layout. Auto detection is the default. The engine importer
interprets the workbook; expanded archives are limited to 100 MB and 3,000 entries before parsing.

The import report shows the detected layout, risks and measures read, stages, columns, pictures, errors, notes
and findings. Errors block ratings and exports: correct the source and import again. Notes and findings are
shown without blocking. The risk register and available now, target and initial maps come from the engine.

With the optional `atelier_private.review` plugin installed under `ATELIER_PRIVATE_DIR/plugins`, **Rate criteria**
shows its criteria grouped by axis and workshop, its machine proposals and explanations, and its status vocabulary.
Selections are prefilled from proposals. Saving confirms selected statuses as reviewer ratings. A blank selection
removes an explicit reviewer rating and leaves the plugin's automatic decision, if any. Applicability is handled
by the plugin, including its not-applicable statuses. Notes are optional. A refused status returns the form with
your input and the plugin error; it changes nothing on disk. Repeating an identical save changes nothing.

**Result & export** shows a score and confidence only when the plugin returns a score. Otherwise it lists the
unrated criteria with links back to their rows. Findings, measures and criterion sources distinguish automatic
ratings from reviewer decisions. Download the study JSON or the plugin's short Excel review. No score, level
or severity is calculated by the web app. Without the plugin, the interface explicitly says scoring and the short
Excel export are unavailable; import, checks, register, maps and study JSON remain usable.

Every review has its own `reviews/r-.../` directory under the data directory (0700), holding `upload.xlsx` and
one atomic `state.json` snapshot (0600). Original filenames are discarded. An imported private calibration or
private layout marks the study confidential. Review mode is local and offers no remote drafting route; the
exported study carries the confidential mark and the study-mode route policy still applies if it is imported there.
**Delete review** permanently removes the review directory and upload. Review exports use a private temporary
file in that directory and delete it after the download is prepared. Two tabs editing the same criterion: last save wins.

## Code layout

| Module | Role |
|---|---|
| `app/serve.py` | entry point |
| `app/atelier.py` | launcher: start, stop, status, token --new |
| `app/prompts/` | one drafting prompt per workshop |
| `app/atelier_app/documents.py` | document upload, local text extraction, storage |
| `app/atelier_app/drafts.py` | draft items: workshop, pre-filled form values, study summary sent to the model |
| `app/atelier_app/views_draft.py` | drafting panels, documents page, settings page |
| `app/atelier_app/config.py` | settings and their defaults (environment, then the user's home) |
| `app/atelier_app/engine.py` | the only module that calls the engine |
| `app/atelier_app/calibrations.py` | calibration lookup, the picker's catalogue, whether a study is private |
| `app/atelier_app/drafting.py` | the drafting adapter (`draft(task, context)`): routes and their policy, schemas, answer parsing, chunks, rate limit, request log |
| `app/atelier_app/storage.py` | study files |
| `app/atelier_app/reviews.py`, `review_store.py`, `views_review.py` | review handlers, private snapshots/uploads and review pages |
| `app/atelier_app/auth.py` | token, one-time links, sessions, CSRF |
| `app/atelier_app/editors.py` | workshop 2 to 5 forms: fields, link checks, ids |
| `app/atelier_app/quick_routes.py`, `views_quick.py` | quick-path handlers and pages (home, four screens, EN and FR text) |
| `app/atelier_app/app.py`, `views.py`, `views_ws.py`, `web.py`, `server.py` | routes and handlers, HTML (workshop 2 to 5 editors in `views_ws.py`), HTTP plumbing, the server |
| `app/static/` | the CSS and JS files the pages load |
| `app/tests/` | unit tests (`python3 -m unittest discover -s app/tests -t .`), `no_openpyxl.py` (the same tests as if openpyxl were missing: the Excel tests skip), `stub_model.py` (a local stand-in for an OpenAI-compatible API, answering per workshop) and `e2e.py` (end-to-end run) |

## Limits of this iteration

- Atelier is a single-user local app today. Sessions carry a user name and handlers get their study store
  through one function (`App.store_for`), so several users can be added later without changing URLs.
- No HTTPS: it relies on staying on the loopback address.
- The engine has no function that returns a derived severity; the app gets it by asking the engine's own check
  which of 1 to 4 it accepts (`engine.derived_severity`). When the engine gains such a function, only that
  function changes.
- No relevance aid for risk origins and no stakeholder threat level: the engine does not compute them yet.
- Two browser tabs editing the same study: the last save wins (the `.bak` keeps the version before it).
- Automated tests use a local OpenAI-compatible stub. A separate smoke test exercises one W1 draft with a
  public guide example on a local model; it does not establish the quality of drafts for other workshops or
  private documents. Token counts for chunking are estimates (4 characters a token).
- The rate limit lives in memory: a restart resets it.
- A drafted strategic scenario brings its first attack path into the form; its other proposed paths are listed
  so you can add them with Edit after accepting.
- No OCR: a PDF without a text layer is refused.
- Review scoring and the short review Excel export require the optional private plugin. Without it, imports,
  engine checks, register, maps and study JSON still work. Review mode does not call a language model.
- Drafts are kept per study, in a file beside the studies; two tabs drafting at once both add their items.
