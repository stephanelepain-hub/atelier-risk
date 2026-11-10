# Importing a filled-in risk analysis (review mode)

`atelier_engine.importer` reads an existing risk analysis kept in a spreadsheet (.xlsx) and turns it into a study,
so the engine can recompute its levels, check it and list what does not hold together. It reads; it never guesses.
Anything it cannot read is an error or a note in the report, and every value taken from a cell colour or mapped
from free text is listed.

```bash
cd engine
python3 -m atelier_engine layouts
python3 -m atelier_engine import filled.xlsx --cal anssi-v1.5 [--layout risk-register] [--out study.json]
```

From Python (this is what the web app calls):

```python
from atelier_engine import calibration, importer, study
cal = calibration.load("anssi-v1.5")
res = importer.read_xlsx(path_or_file_object, cal, layout=None)   # None: try every layout, keep the best read
res["study"]    # an atelier-study document (mode "review"): risks and measures
res["report"]   # {"layout", "calibration", "read": {...}, "errors": [...], "notes": [...], "findings": [...]}
study.validate(res["study"], cal)      # the usual checks, e.g. measures with no owner or due date
study.register(res["study"], cal)      # levels recomputed from the calibration's grid
```

`importer.SpreadsheetError` means the file cannot be read at all (not an xlsx, no layout matches, no risk rows).
Needs openpyxl. Installing defusedxml as well is recommended: openpyxl then uses it to parse the workbook XML.

## Report

- `errors`: the import is incomplete. Examples: a value that is not on the calibration's scale, a risk with no
  severity or likelihood anywhere, a risk listed twice, a risk placed twice on the same map.
- `notes`: how something was read. Examples: levels known only from cell colours (colour is lost in most exports),
  a free-text measure status counted as planned, no current likelihood so the initial one is used.
- `findings`: inconsistencies in the analysis itself, for the reviewer:
  - a level shown in the register (text or colour) that differs from the calibration's grid;
  - a risk map cell coloured differently from the grid;
  - a severity that differs between maps, or between the register and a map;
  - a risk missing from a map, or on a map but not in the register;
  - a likelihood in the register that differs from the map;
  - a measure linked from a risk but not described, or described but linked to no risk;
  - two measures with the same description (ignoring case, accents, plurals and note markers), and whether
    their statuses differ.

## Layouts

A layout (JSON) says where things are. Public ones ship in `layouts/`. Your own go in
`ATELIER_PRIVATE_DIR/layouts/` and win a name clash.

| Layout | Reads |
|---|---|
| `risk-register` | one row per risk with severity and likelihood columns (numbers, codes or labels); optional measures sheet |
| `register-with-maps` | a register whose levels are text or colours, with risk maps (initial, current, target) that give severity and likelihood; measures sheet |

```json
{
  "id": "my-layout",
  "risks": {
    "sheet": ["Risks"], "required": ["id"],
    "columns": {"id": ["Risk ID"], "label": ["Description"], "criterion": ["Criterion"],
                "severity": ["Severity"], "likelihood": ["Likelihood"], "likelihood_target": ["Target likelihood"],
                "likelihood_initial": ["Initial likelihood"],
                "level_initial": ["Initial risk"], "level_now": ["Current risk"], "level_target": ["Target risk"],
                "measures": ["Mitigation ID"], "owner": ["Owner"], "treatment": ["Treatment"]}
  },
  "measures": {"sheet": ["Measures"], "columns": {"id": ["Measure ID"], "label": ["Measure"], "status": ["Status"],
                                                  "owner": ["Owner"], "due": ["Due"], "details": ["Details"]},
               "status_rules": [["^ok\\b", "done"], ["in progress", "in progress"]]},
  "pictures": [{"sheet": ["Risk maps"], "title_contains": ["current"], "stage": "now"}],
  "criterion_codes": {"C": "confidentiality"}
}
```

- Headers are matched without case, accents or punctuation: an exact match first, then a header that starts
  with the name ("Current risk (2026-09)" matches "Current risk"). The header row is searched in the first 15 rows.
- A risk may span several rows (merged cells, or blank id cells below it). The rows below it add measure ids.
- Cell values for severity and likelihood: an integer 1-4, or a code or label from the calibration's scales.
- Levels: the level name as text, or only the fill colour, matched to the calibration's `colour` (and optional
  `colours` list) for each level.
- Risk maps: the importer finds the four severity labels side by side on one row, the four likelihood labels in
  a column just to their left, and the risk ids in the grid cells (separated by commas, semicolons, slashes or
  new lines). Merged cells are handled. The map's title (the nearest text above it) picks the stage.
- Measure status rules are regular expressions, tried in order on the normalised text. When none matches, the
  status counts as planned and the original text is kept in `status_text`.
