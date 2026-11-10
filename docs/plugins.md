# Calibrations and private extensions

## Calibration file

```json
{
  "id": "my-org-2026",
  "name": "...", "source": "...",
  "severity":   [{"n": 1, "code": "G1", "label": "..."}, "... n = 1 to 4"],
  "likelihood": [{"n": 1, "code": "V1", "label": "..."}, "... n = 1 to 4"],
  "levels": [{"name": "Low", "rank": 1, "colour": "00B050", "acceptability": "...", "action": "..."}, "..."],
  "grid_by_severity": {"4": ["...", "...", "...", "..."], "3": [], "2": [], "1": []}
}
```

`grid_by_severity["s"][v-1]` is the level for severity `s` and likelihood `v`. The engine refuses a calibration
whose scales are not 1-4, whose grid uses an undeclared level, or whose level drops as severity or likelihood
rises.

## Private directory

`ATELIER_PRIVATE_DIR=/path/outside/the/repo`

- `*.json` in that directory are calibrations. They are listed as `private` and win a name clash with a public one.
- `plugins/atelier_private/cli.py`, if present, can add commands. It must define `COMMANDS` (a tuple of names),
  `register(subparsers)` and `run(args) -> (result_dict, exit_code)`.

Keep organisation-specific scales, documents and studies in that directory. The repository holds none.
