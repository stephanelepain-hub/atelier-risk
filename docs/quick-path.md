# Quick path (`atelier_engine.quick`, web app `/quick/...`)

The quick path is a "known risks list": four screens, a public catalogue of typical risks, and a result with two
risk maps (now, after extra measures). It produces a normal `atelier-study` (docs/study-format.md), which the engine
checks and exports like any other study.

Rules that the ANSSI guide does not print are "Atelier rules, beyond the guide" (docs/rules.md, rule 5). All of them
are in `engine/atelier_engine/quick.py`; the web app never computes a level.

## The four screens (routes)

| Screen | Route | What the person does | Saved as |
|---|---|---|---|
| Home | `GET /` | Reads the honesty statement and presses Start (`/quick/new`). The list of saved studies is at `/studies` (reopen, delete). | nothing |
| 1 About you | `/quick/new`, `/quick/<study>/about` | 6 questions (name, what the organisation does, what matters most, what is used, how soon a stop hurts, how sensitive the information is). Each has an example and "Not sure". | `quick.profile` |
| 2 Risks | `/quick/<study>/risks` | Keeps or discards the proposed risks, adds risks in their own words. An always-assessed risk needs a reason to be discarded. | `quick.risks[]` |
| 3 Now and after | `/quick/<study>/now` | One compact row per kept risk: severity (proposed, with an override and a reason) and likelihood (plain question). Then each measure of the kept risks **once**, for the whole business, under a few plain headings: later, already in place, add to my plan. | `quick.risks[]` (severity, likelihood), `quick.measures` (the measure answers) |
| 4 Results | `/quick/<study>/results` | A positive summary line, the top actions, before and after maps with a numbered list of the risks, "See all your risks" and "Already in place" (collapsed), confidence, honesty statement, assumptions, Excel download, study-file download. | nothing |

Every POST saves and rebuilds the study from the quick answers (`quick.build_study`), so the study file is always a
valid study. Screen 2 pre-ticks only the short list (`quick.shortlist`, see "Short list" below); the other risks that
apply are listed under a collapsed "More risks you can add (N)" section, unticked, and are stored as `discard` until
ticked. Saving screen 1 again re-suggests the risks: earlier keep/discard decisions are kept, a new risk is ticked
when it is in the short list and unticked otherwise, and a catalogue risk that no longer applies to the new answers is
dropped with its ratings. Language: `?lang=en|fr` (kept in the `atelier_lang` cookie); the forms carry it and it is stored in
`quick.lang`, which is also the language of the generated study text.

**Measures are answered once.** A measure (for example "Turn on a second sign-in step") is the same sentence in every
risk that lists it, so the person is asked about it once: it is *in place*, *planned* (add to my plan) or open
(later), for the whole business. `quick.measures` holds the answers; each kept risk takes the answer for the measures
in its own list (`quick.org_measures`, `quick.measure_list`). A measure is therefore never "in place" for one risk and
"planned" for another, and the results list it in one place only. The levels after (`likelihood_target`) still count,
per risk, the planned measures of that risk's own list.

**Documents.** The public screens do not ask about documents. A study saved earlier may still carry
`profile.document`; the engine keeps reading that flag for the confidence ceiling, and nothing else.

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
    "sensitivity": {"answer": "confidential"}
  },
  "measures": {"in_place": ["updates"], "extra": ["backup_offline", "mfa"], "assessed": true},
  "risks": [
    {"id": "D01", "decision": "keep",
     "severity": {"value": 3, "reason": "we have a paper fallback"},
     "likelihood": {"answer": "likely"}},
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
| `profile.document` | `{"provided": bool}` | Not asked on the public screens any more; read only from studies saved earlier (they may also carry `status` or a `kind`). Nothing is read from a document. |
| `risks[].id` | catalogue id, or `C<n>` for the person's own | Order is the order of the suggestions. |
| `risks[].decision` | `keep`, `discard` | A discarded always-assessed risk needs a non-empty `reason`. |
| `risks[].severity` | `{"value": 1..4, "reason": text}` | Absent = keep the proposal. A value different from the proposal needs a `reason`. |
| `risks[].likelihood.answer` | deliberate: `unlikely`, `possible`, `likely`, `very_likely`; accidental: `never`, `once`, `sometimes`, `often`; or `dont_know` | Absent or `dont_know` = the typical value of the catalogue is used, as `default`. |
| `measures.in_place`, `measures.extra` | measure ids of the catalogue | The answers of the whole business. A measure in both lists is only "in place". An id that no kept risk lists is ignored (it stays stored, in case the risk is kept again). |
| `measures.assessed` | bool | Screen 3 was saved (the measures were reviewed). Without it the assumptions list says "Measures already in place: none assumed yet." |
| `risks[].in_place`, `.extra`, `.assessed` | old shape, read only | Studies saved before round 3 answered per risk. The engine reads them as below and `quick.migrate` (called by the app when a study is opened) moves them to `measures` and removes them. |
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
  `0.8 + 0.2 x` the share of the five About-you questions answered, rounded to a whole percent. From answers alone
  (the public screens read no document) the result tops out at 75 (`NO_DOCUMENT_CEILING`). No kept risk: 0. Bands: high 80 and up,
  medium 50-79, low under 50. The page says it in one line: "Confidence grows as you answer more questions yourself."
  A document flag in a study saved earlier does not raise the figure by itself (nothing in the study comes from it).
- **Top actions**: each extra measure's priority is the sum, over the kept risks that list it, of
  (100 x levels the risk gains + severity x likelihood now), shared among that risk's extra measures. At most 5.
  The summary line counts all the planned measures ("With 5 actions, 4 of your 7 risks move to Low or Moderate.").
- **Evidence ("Based on")**: the person's note on a changed severity; else the tool they ticked that brings the risk
  (not office IT, which is too broad), how sensitive their information is (for a risk that hits confidentiality), how
  soon a stop hurts (for availability); else the catalogue's `why` for the risk. The likelihood answer is never quoted.
  Each top-action card takes the first of its risks that an earlier card has not shown.
- **Effort figures** (`labels.EFFORT`, "Rough guide"): short ranges and plain words only (`labels.FIGURES`: "under an hour",
  "a day or two", "small monthly fee", ...), no precise price. A test refuses digits and currency signs.
- **Assumptions**: every About-you question not answered, every severity or likelihood that is a `default`, every
  proposed severity kept as is (`catalogue`), and, once, the measures in place when none were reviewed. About-you
  first, then by risk level, highest first. Their texts carry no risk code (the Excel sheet has a Risk column).

## Mapping to the study format

| Quick | Study |
|---|---|
| `profile.name`, `activity` | `study.name`, `study.scope` (`study.path` = `quick`) |
| `profile.values` | `business_values` (`BV1..`); with none, one default "Day-to-day operations" |
| `profile.tools` | `supporting_assets` (`SA1..`), linked to every business value |
| each kept risk `X` | `feared_events` `FE-X` (on the first business value) and `risks` `X` (`likelihood`, `likelihood_target`, `treatment: reduce` when it has extra measures) |
| a deliberate risk | also `risk_origins` `RO-X` (origin and objective from the catalogue, decision selected), `strategic_scenarios` `SS-X` and `operational_scenarios` `OS-X` carrying the likelihood |
| `measures.in_place` | `baseline` `BL-<measure>`, status applied (one per measure, shared by risks) |
| `measures.extra` | `measures` `M-<measure>`, status planned, `risks` = the kept risks that list it (no owner or date: the checks warn) |

An accidental risk has no risk origin or scenario, so the engine's checks list a warning for each feared event of
severity 3 or 4 ("no scenario targets it"). These are warnings, not errors; the study validates.

Saving a quick screen rebuilds the study from the quick answers, and the previous file is kept as `.bak`.

## Honesty statement

`quick.HONESTY` (EN and FR) is the only place the statement is written: "These results come only from your answers.
They are a first view, as good as the answers you gave." The home page (once), every results page (once) and the
header of the Excel export (first rows of the first sheet, with a line of counts: answers, assumptions, confidence and
its ceiling, `quick.CONFIDENCE_LINE`) read it from there.

## Public catalogue

`catalogues/quick-risks.json`, described in `catalogues/README.md`. `quick.load_catalogue()` reads and checks it;
`quick.suggest(profile)` returns the ids for the packs the profile implies (every risk that applies),
always-assessed risks first. With no answer for "what you use", the packs are `all` and `office-it`.

Packs: `all`, `office-it`, `cloud-service`, `cloud-infra` (servers, apps or data on a public cloud; tool `cloud_infra`),
`website-shop`, `industrial`. A risk may list several packs; `refs` (optional, required for a risk that belongs to
`cloud-infra` only) lists the numbers of the recommendations of the cited CERT-FR cloud report that it relates to. The engine
does not use `refs`; `check_catalogue` checks their shape.

### Short list and `audience`

`quick.shortlist(profile, catalogue=None, limit=10)` returns the ids pre-ticked on screen 2: the always-assessed risks
that apply (catalogue order, never cut: if there are more than `limit` all are kept), then the other applicable risks
ranked by `typical_severity * typical_likelihood` (highest first; ties in catalogue order), up to `limit` ids in total.

Each risk has one `audience` field: `all` (the default when absent) or `sensitive`. A `sensitive` risk is one that
only makes sense for a large or sensitive organisation (state-backed or targeted espionage, a competitor stealing
know-how). It is left out of the short list unless the profile's sensitivity answer is the highest one (`critical`,
"Secrets, health or legal data") or the industrial tool is ticked. It stays in `suggest` and in the "More risks"
section. An always-assessed risk cannot be `sensitive` (the catalogue check refuses it).

### English labels of a calibration

A calibration may carry optional English texts: `severity[].label_en`, `likelihood[].label_en`, `levels[].name_en`
(and `levels[].acceptability_en`, `action_en`, my translations, only used in the quick Excel export). The French
originals (`label`, `name`, ...) stay the reference and the level `name` stays the key; `calibration.check` accepts the
new keys (a non-empty text when present) and a calibration without them falls back to the original text.
`calibration.label(cal, axis, n, lang)` and `calibration.level_name(cal, name, lang)` give the text for `lang="en"`;
any other language, or none, gives the original. The quick-path screens, result maps and table and the quick Excel
export follow the page language. In the Excel export the object sheets keep their raw
column names.

### Brand logo

If `app/static/brand/logo.svg` exists, the page header shows it (30 px high, alt text set in `views.logo_html`) to the
left of the app name, and `/static/brand/logo.svg` serves it. Without the file nothing extra is shown. No logo file is shipped.

## Not done

- Reading documents (the public screens do not ask about them).
- French text beyond the quick-path screens and the honesty statement (the study list and the login page stay English).
- Several users or accounts.
