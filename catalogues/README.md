# Public catalogue of typical risks

`quick-risks.json` is the list of typical risks behind the quick path of the web app (docs/quick-path.md). It is
written for Atelier in plain words, in English and French. It is public: no private material, no vendor names, no
company names and no text copied from another catalogue.

## What is in it

- 32 risks in two families.
  - **Deliberate** (15): someone attacks you. Each has a risk origin and a target objective from the ANSSI EBIOS
    Risk Manager typology.
  - **Accidental** (17): staff error, process or change error, failure of a network, hardware, software, supplier or
    building service, loss or theft of equipment, natural events.
- Per risk: `id`, `family`, `title` and `description` (EN and FR), `criteria` (which of confidentiality, integrity,
  availability it hits), `packs`, `always_assessed`, 3 to 6 `measures` (id, EN, FR), and two typical levels.
- Top level: `packs`, the `tools` tick-list of the first screen (each tool implies packs), `origins`, `objectives`,
  `generic_measures` (offered for a risk the person adds), and `sources`.
- Packs: `office-it`, `cloud-service`, `website-shop`, `industrial`, and `all` (every organisation).
  `always_assessed` risks are always put to the person for their pack; they cannot be discarded without a reason.
- The same measure has the same id and text in every risk that lists it.

## Sources

| Used for | Source | Licence |
|---|---|---|
| Deliberate risks: risk origins (state-backed group, activist, competitor, cybercriminal, staff member) and target objectives (make money, steal information, spread a message, take revenge, disrupt or create a crisis) | ANSSI, guide EBIOS Risk Manager v1.5, September 2024: the glossary entries "risk origin" and "target objective", and the workshop 2 example | Licence Ouverte / Open Licence (Etalab) |
| Accidental risks: the four families of threat sources (accidental, structural, environmental, and adversarial for theft) and their subtypes (user, privileged user, IT equipment, software, environmental controls, natural or man-made disaster, infrastructure failure) | NIST SP 800-30 Revision 1, Appendix D, Table D-2 "Taxonomy of threat sources" | US government work, no copyright |

The guide's typology is short; the five origins and five objectives used here are the ones its glossary and its
workshop 2 example name. Each accidental risk carries its Table D-2 family in `nist_source`. Theft of equipment is
adversarial in Table D-2; it is listed with the accidental family because, from the person's point of view, it is a loss of equipment.

## What the figures mean

`typical_severity` and `typical_likelihood` (1 to 4, the levels of the calibration) are the author's judgement of a
typical small organisation. They are not statistics and not taken from either source. The quick path shows them as
proposals, blends them with the person's answers, and lists every one that was kept as an assumption to confirm
(rules: docs/quick-path.md). Change them in this file if your own experience differs.

## Editing

Keep the file valid with `atelier_engine.quick.check_catalogue` (the engine tests run it). Keep every text in plain
words, EN and FR together, and keep each measure id tied to one text.
