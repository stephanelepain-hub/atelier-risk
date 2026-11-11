# Atelier (public edition)

Atelier gives a person with no security background a plain-language first view of their main cyber risks. You
answer a few simple questions, keep the risks that apply to you, say what you already do and what you could add,
and get two risk maps (now, and after your extra measures), your top 5 actions, the assumptions made, and a
confidence figure. The method behind it is the EBIOS Risk Manager method published by ANSSI, the French national
cybersecurity agency; ANSSI states that EBIOS Risk Manager conforms with ISO/IEC 27005:2022. The levels come from
the published `anssi-v1.5` calibration and are computed by the engine, never typed in and never guessed by the app.

Status: early (v0.1), for beta testers.

## Honesty statement

The app shows this text on the home page, on every results page and at the top of the Excel export:

> This analysis reflects only the answers you gave and the documents you provided. It is only as good as that
> information. Without source documents (architecture, business impact, security baseline) treat it as a first view.

## How to use it

1. **Home.** Start from scratch, or say that you have a document.
2. **About you.** Seven questions: a name, what the organisation does, what matters most, what you use, how soon a
   stop would hurt, how sensitive your information is, and whether you have a document. Each has an example and
   "I don't know". Atelier does not read documents: a "yes" is only listed in the results as "document mentioned,
   not read".
3. **Risks.** Keep the typical risks that fit, discard the others, add your own.
4. **Now and after.** For each kept risk: how bad, how likely, what you already do, what you could add.
5. **Results.** What is already in place, the top 5 actions and each risk in three short lines, two maps, the
   confidence, the honesty statement, the assumptions, and a closing line. Download the Excel workbook or the study
   file. Saved studies are listed under "Studies": reopen or delete.

"How it works" (in the header) explains the method and where the numbers come from. The **Expert** switch in the
header (off by default) shows the full method on the same study: overview, workshops 1 to 5, register.

English and French are both available (the EN / FR switch in the header). Everything is saved after each step.

## Run it

```bash
python3 app/atelier.py start     # prints http://127.0.0.1:8770/ and a one-time login link
python3 app/atelier.py status
python3 app/atelier.py stop
python3 app/atelier.py token --new   # a new login token
```

Open the link it prints. The app listens on the loopback address only and asks for a login token (kept in
`<data dir>/token`, readable by your user only). Without the launcher: `python3 app/serve.py`. Your studies are
kept in `~/.local/share/atelier/` (or `ATELIER_DATA_DIR`). More in `docs/app.md`.

Python 3.12 or later. The standard library is enough, except for the Excel download, which needs `openpyxl`
(`pip install openpyxl`); without it the app runs and the study-file download still works.

## Tests

```bash
cd engine && python3 -m unittest discover -s tests
cd .. && python3 -m unittest discover -s app/tests -t .
```

## Limits

- It is a first view. It reflects your answers and a public list of typical risks, not an audit of your systems.
- Documents are not read. A "yes" to the document question does not change any level.
- One calibration only (`anssi-v1.5`). One user, on your own machine, no HTTPS (loopback only).
- Where you do not know an answer, a typical value is used and listed under "What we assumed".
- The confidence figure is an Atelier rule, not part of the ANSSI method (see `docs/quick-path.md`).

## Layout

| Path | Content |
|---|---|
| `app/` | the web app (`atelier.py` launcher, `serve.py` server, `atelier_app/` code, `static/`, `tests/`) |
| `engine/atelier_engine/` | calibration, study checks, risk register, risk maps, Excel export, the quick-path rules |
| `catalogues/` | the public catalogue of typical risks, EN and FR |
| `calibrations/` | the published calibration `anssi-v1.5` |
| `examples/` | the worked example of the ANSSI guide, as a study file |
| `layouts/` | spreadsheet layouts read by the engine's own tests |
| `docs/` | `app.md`, `quick-path.md`, `study-format.md`, `rules.md` |

## Licence and credits

Code: Apache License 2.0 (`LICENSE`).
The `anssi-v1.5` calibration and the example study reproduce material from the ANSSI guide *EBIOS Risk Manager*,
version 1.5 (2024), published under the Licence Ouverte / Open Licence (Etalab V1). See `NOTICE`.
EBIOS is a registered trademark of the Secrétariat général de la défense et de la sécurité nationale (SGDSN).
Atelier is an independent project. It is not affiliated with, endorsed by or labelled by ANSSI, SGDSN or the
Club EBIOS.
