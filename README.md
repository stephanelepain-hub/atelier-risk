# Atelier

Atelier is an open-source workbench for qualitative cyber risk analysis. It follows the five workshops
("ateliers") of the EBIOS Risk Manager method published by ANSSI, the French national cybersecurity agency.
ANSSI states that EBIOS Risk Manager conforms with ISO/IEC 27005:2022. The method stays as published:
Atelier keeps the study in one structured file, does the arithmetic, checks consistency and produces the
deliverables.

Status: early (v0.1). The engine works. The web app is being built.

## What the engine does today

- **Calibrations.** A calibration is the settings of a 4x4 qualitative risk matrix: severity and likelihood
  scales, risk levels, the grid, and what each level means for acceptance. `anssi-v1.5` ships with the
  repository and reproduces the scales, acceptance classes and grid of the ANSSI guide v1.5. An organisation's
  own calibration is a JSON file of the same shape, kept outside the repository.
- **Study checks.** References between workshop objects resolve. Values stay on the 1-4 scales. A strategic
  scenario's severity follows its feared events, an operational scenario inherits it, and every risk matches its
  scenario. High-severity feared events left out of every scenario are flagged as blind spots.
- **Risk register.** Level now and at target, acceptability, linked measures, and counts per level.
- **Excel export.** A risk register with coloured levels, plus one sheet per workshop object.

## Quick start

```bash
cd engine
python3 -m atelier_engine calibrations
python3 -m atelier_engine level --cal anssi-v1.5 --severity 3 --likelihood 2
python3 -m atelier_engine validate ../examples/anssi-guide-vaccine-example.json
python3 -m atelier_engine register ../examples/anssi-guide-vaccine-example.json
pip install openpyxl   # only for the Excel export
python3 -m atelier_engine export ../examples/anssi-guide-vaccine-example.json risks.xlsx
python3 -m unittest    # tests
```

Python 3.8 or later. The standard library is enough, except for the Excel export, which needs openpyxl.

## Layout

| Path | Content |
|---|---|
| `engine/atelier_engine/` | calibrations, study checks, risk register, export, CLI |
| `calibrations/` | public calibrations (JSON) |
| `examples/` | the worked example of the ANSSI guide, as a study file |
| `docs/` | study format, calibration format, private extensions |
| `app/` | web app (in progress) |

## Your own scales and extensions

Set `ATELIER_PRIVATE_DIR` to a directory outside the repository. Calibration files placed there are picked up,
and a name clash resolves to your copy. An optional `plugins/atelier_private` package in that directory can add
CLI commands (see `docs/plugins.md`). Nothing in that directory is ever committed.

## Licence and credits

Code: Apache License 2.0 (`LICENSE`).
The `anssi-v1.5` calibration and the example study reproduce material from the ANSSI guide *EBIOS Risk Manager*,
version 1.5 (2024), published under the Licence Ouverte / Open Licence (Etalab V1). See `NOTICE`.
EBIOS is a registered trademark of the Secrétariat général de la défense et de la sécurité nationale (SGDSN).
Atelier is an independent project. It is not affiliated with, endorsed by or labelled by ANSSI, SGDSN or the
Club EBIOS.
