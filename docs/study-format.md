# Study format (`atelier-study` 0.1)

A study is one JSON document. Every element has an `id` that is unique across the whole study. Links between
elements use those ids. Severity and likelihood are integers from 1 to 4, interpreted by the study's
calibration.

| Key | Workshop | Fields |
|---|---|---|
| `study` | - | `name`, `scope`, `calibration` (id, default `anssi-v1.5`) |
| `business_values` | 1 | `id`, `label`, `nature` (`process` or `information`), `owner` |
| `supporting_assets` | 1 | `id`, `label`, `business_values` [ids] |
| `feared_events` | 1 | `id`, `business_value`, `label`, `criterion` (confidentiality, integrity, availability, ...), `severity` |
| `baseline` | 1 | `id`, `reference`, `status` (applied / partial / not applied), `gap` |
| `risk_origins` | 2 | `id`, `origin`, `objective`, `motivation`, `resources`, `decision` (selected / monitoring / discarded), `feared_events` [ids] |
| `stakeholders` | 3 | `id`, `name`, `category`, `dependence`, `penetration`, `maturity`, `trust`, `critical` |
| `strategic_scenarios` | 3 | `id`, `risk_origin`, `feared_events` [ids], `severity`, `paths` [{`id`, `label`, `stakeholder`}] |
| `operational_scenarios` | 4 | `id`, `strategic_scenario`, `path`, `likelihood`, `description` |
| `risks` | 5 | `id`, `strategic_scenario` or `operational_scenario`, `label`, `severity`, `likelihood`, `likelihood_target`, `treatment` (reduce / accept / transfer / avoid), `owner` |
| `measures` | 5 | `id`, `label`, `risks` [ids], `owner`, `due`, `status` (planned / in progress / done / dropped) |

Header: `"format": "atelier-study", "version": "0.1"`.

## Checks (`validate`)

Errors (the study is not usable until fixed):
- duplicate or missing ids; a link to an id that does not exist or has the wrong type;
- a value outside the 1-4 scale; an unknown decision, treatment or measure status;
- a strategic scenario whose severity is not the highest severity of its feared events (guide p.49);
- an operational scenario or a risk whose severity differs from its strategic scenario (guide p.62, p.65).

Warnings (to review):
- a strategic scenario built on a risk origin that is not selected;
- a feared event of severity 3 or 4 that no scenario targets: a blind spot (guide p.73);
- a target likelihood lower than today with no measure linked;
- a measure that is not done or dropped and has no owner or no due date.

The example in `examples/` is a valid study.
