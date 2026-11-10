# Quick path (`atelier_engine.quick`, web app `/quick/...`)

The quick path is the "known risks list" shape of docs/design/guided-path.md section 17: four screens, a public
catalogue of typical risks, and a result with two risk maps (now, after extra measures). It produces a normal
`atelier-study` (docs/study-format.md), so the existing workshop screens ("expert mode") open the same study.

Rules that the ANSSI guide does not print are "Atelier rules, beyond the guide" (docs/rules.md, rule 5). All of them
are in `engine/atelier_engine/quick.py`; the web app never computes a level.

## The four screens (routes)

| Screen | Route | What the person does | Saved as |
|---|---|---|---|
| Home | `GET /` | Reads the honesty statement, picks a way in: scratch (`/quick/new`), with a document (`/quick/new?doc=1`), or an existing risk analysis (`/reviews`). The study list is at `/studies`. | nothing |
| 1 About you | `/quick/new`, `/quick/<study>/about` | 7 questions (name, what the organisation does, what matters most, what is used, how soon a stop hurts, how sensitive the information is, optional document). Each has an example and "I don't know". | `quick.profile` |
| 2 Risks | `/quick/<study>/risks` | Keeps or discards the proposed risks, adds risks in their own words. An always-assessed risk needs a reason to be discarded. | `quick.risks[]` |
| 3 Now and after | `/quick/<study>/now` | Per kept risk: severity (proposed, with an override and a reason), likelihood (plain question), measures in place, extra measures. | `quick.risks[]` |
| 4 Results | `/quick/<study>/results` | Before and after maps, top 5 actions, assumptions, confidence, honesty statement, Excel download, link to expert mode. | nothing |

Every POST saves and rebuilds the study from the quick answers (`quick.build_study`), so the study file is always a
valid study. Saving screen 1 again re-suggests the risks: earlier keep/discard decisions are kept, new suggestions are
added as kept, and a catalogue risk that no longer applies to the new answers is dropped with its ratings. Language: `?lang=en|fr` (kept in the `atelier_lang` cookie); the forms carry it and it is stored in
`quick.lang`, which is also the language of the generated study text.

Documents: a file sent with screen 1 is stored in the study's documents (same store and limits as the Documents tab)
and flagged as provided, with its type. It is **not read**: no answer or element comes from it, so it does not change
any level. The results page says so. (Document reading is out of scope of this first draft.)

## Quick answers (JSON)

Stored in the study file under the key `quick` (the engine's checks ignore it), and accepted by `build_study`.

```json
{
  "format": "atelier-quick", "version": "0.1",
  "lang": "en",
  "step": "risks",
  "profile": {
    "name": "Bakery review",
    "activity":    {"value": "We run three bakeries.", "dont_know": false},
    "values":      {"value": ["Taking orders", "Customer list"], "dont_know": false},
    "tools":       {"value": ["office", "shop"], "dont_know": false},
    "downtime":    {"answer": "day"},
    "sensitivity": {"answer": "confidential"},
    "document":    {"provided": true, "doc_id": "d0123456789ab", "filename": "notes.txt", "kind": "architecture", "status": "stored, not read"}
  },
  "risks": [
    {"id": "D01", "decision": "keep",
     "severity": {"value": 3, "reason": "we have a paper fallback"},
     "likelihood": {"answer": "likely"},
     "in_place": ["updates"], "extra": ["backup_offline", "mfa"], "assessed": true},
    {"id": "A02", "decision": "discard", "reason": "we keep no data"},
    {"id": "C1", "decision": "keep",
     "custom": {"title": "Our van breaks down", "family": "accidental", "criteria": ["availability"]}}
  ]
}
```

| Field | Values | Notes |
|---|---|---|
| `lang` | `en`, `fr` | Language of the generated study text. |
| `step` | `about`, `risks`, `now`, `results` | The next screen to do (where "pick up where you left off" goes). |
| `profile.name` | text | Study name. Required in the web form. |
| `profile.activity`, `.values`, `.tools` | `{"value": ..., "dont_know": bool}` | `values`: at most 5 labels, most important first. `tools`: ids of the catalogue's `tools`. |
| `profile.downtime` | `hours`, `day`, `days`, `week`, `dont_know` | How soon a stop of the main tools really hurts: levels 4, 3, 2, 1. |
| `profile.sensitivity` | `public`, `internal`, `confidential`, `critical`, `dont_know` | Levels 1, 2, 3, 4. |
| `profile.document` | `{"provided": bool, "kind": "architecture"\|"business-impact"\|"security-baseline"\|"other", ...}` | Flag only. |
| `risks[].id` | catalogue id, or `C<n>` for the person's own | Order is the order of the suggestions. |
| `risks[].decision` | `keep`, `discard` | A discarded always-assessed risk needs a non-empty `reason`. |
| `risks[].severity` | `{"value": 1..4, "reason": text}` | Absent = keep the proposal. A value different from the proposal needs a `reason`. |
| `risks[].likelihood.answer` | deliberate: `unlikely`, `possible`, `likely`, `very_likely`; accidental: `never`, `once`, `sometimes`, `often`; or `dont_know` | Absent or `dont_know` = the typical value of the catalogue is used, as `default`. |
| `risks[].in_place`, `.extra` | measure ids from the risk's own measures | A measure in both is only "in place". |
| `risks[].assessed` | bool | Screen 3 was saved for this row (measures in place were reviewed). |
| `risks[].custom` | `{"title", "family", "criteria"}` | A risk in the person's words. `family`: `deliberate`, `accidental`. |

## Sources

Every element of the built study has `source`, one of:

| Source | Meaning |
|---|---|
| `document` | Taken from a document. Reserved: nothing is read from documents yet, so it never appears today. |
| `answer` | The person gave it (an answer, a chosen severity, a ticked measure, a risk of their own). |
| `catalogue` | A typical value of the public catalogue, shown to the person and kept (the proposed severity). |
| `default` | Skipped or "I don't know": a default was used. |

Risks also carry `sources` (`{"severity": ..., "likelihood": ...}`). "I don't know" is a `default` source and is told
apart in the assumptions list.

## Rules (Atelier rules, beyond the guide)

- **Proposed severity** = the catalogue's typical severity, averaged (half up) with the level the person's answers give
  to the criteria the risk hits: availability = `downtime`, confidentiality = `sensitivity`, integrity = the higher of
  the two; the highest of the criteria hit is used. An unknown answer counts as level 3 (cautious) and makes the
  proposal a `default`. A risk the person added has no typical severity: the proposal is the answers' level.
- **Likelihood now**: the plain answer maps to 1-4 as above. Without an answer the catalogue's `typical_likelihood`
  is used (2 for a risk of the person's own), as `default`.
- **Likelihood after**: 1 or 2 extra measures lower it by one level, 3 or more by two, never below 1. The study's
  `likelihood` is the one now, `likelihood_target` the one after; `study.register` therefore gives `level` and
  `level_target`.
- **Levels** are `calibration.level(severity, likelihood)`. A chosen severity must be 1-4 or the engine refuses it.
- **Confidence** (0-100): weight by source: document 1.0, answer 0.75, catalogue 0.5, default 0. Risk confidence =
  0.5 x severity weight + 0.5 x likelihood weight; study confidence = the mean of the risks', times
  `0.8 + 0.2 x` the share of the five About-you questions answered, rounded to a whole percent. With no document
  provided the result never exceeds 75. No kept risk: 0. Bands: high 80 and up, medium 50-79, low under 50.
  A document that is stored but not read does not raise it (nothing in the study comes from it).
- **Top actions**: each extra measure's priority is the sum, over the risks it is ticked on, of
  (100 x levels the risk gains + severity x likelihood now), shared among that risk's extra measures. At most 5.
- **Facts line**: "Assumptions to confirm" counts every entry of the assumptions list, typical values kept included.
- **Assumptions**: every About-you question not answered, every severity or likelihood that is a `default`, every
  proposed severity kept as is (`catalogue`), and every risk whose measures in place were not reviewed. About-you
  first, then by risk level, highest first.

## Mapping to the study format

| Quick | Study |
|---|---|
| `profile.name`, `activity` | `study.name`, `study.scope` (`study.path` = `quick`) |
| `profile.values` | `business_values` (`BV1..`); with none, one default "Day-to-day operations" |
| `profile.tools` | `supporting_assets` (`SA1..`), linked to every business value |
| each kept risk `X` | `feared_events` `FE-X` (on the first business value) and `risks` `X` (`likelihood`, `likelihood_target`, `treatment: reduce` when it has extra measures) |
| a deliberate risk | also `risk_origins` `RO-X` (origin and objective from the catalogue, decision selected), `strategic_scenarios` `SS-X` and `operational_scenarios` `OS-X` carrying the likelihood |
| `in_place` | `baseline` `BL-<measure>`, status applied (one per measure, shared by risks) |
| `extra` | `measures` `M-<measure>`, status planned, `risks` = the risks it is ticked on (no owner or date: the checks warn) |

An accidental risk has no risk origin or scenario (design s.17), so the expert checks list a warning for each
feared event of severity 3 or 4 ("no scenario targets it"). These are warnings, not errors; the study validates.

## Expert mode

"Open in expert mode" links to `/s/<study>`. Changes made there are not carried back: saving a quick screen rebuilds
the study from the quick answers, and the previous file is kept as `.bak`. The quick screens show a notice when the
stored study differs from what the quick answers build.

## Honesty statement

`quick.HONESTY` (EN and FR) is the only place the statement is written. The home page, every results page and the
header of the Excel export (first rows of the first sheet, with a line of facts: documents, answers, assumptions,
confidence) read it from there.

## Public catalogue

`catalogues/quick-risks.json`, described in `catalogues/README.md`. `quick.load_catalogue()` reads and checks it;
`quick.suggest(profile)` returns the ids for the packs the profile implies, always-assessed risks first. With no
answer for "what you use", the packs are `all` and `office-it`.

## Not done in this draft

- Reading documents (the upload is stored and flagged only).
- French text beyond the quick-path screens and the honesty statement (other pages stay English).
- Level names are the calibration's own (`anssi-v1.5` names them in French).
- Several users or accounts.
