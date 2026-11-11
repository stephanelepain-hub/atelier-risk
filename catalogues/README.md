# Public catalogue of typical risks

`quick-risks.json` is the list of typical risks behind the quick path of the web app (docs/quick-path.md). It is
written for Atelier in plain words, in English and French. It is public: no private material, no company names (the one exception: the label of the `cloud_infra` tool names the three cloud providers it covers)
and no text copied from another catalogue.

## What is in it

- 41 risks in two families.
  - **Deliberate** (20): someone attacks you. Each has a risk origin and a target objective from the ANSSI EBIOS
    Risk Manager typology.
  - **Accidental** (21): staff error, process or change error, failure of a network, hardware, software, supplier or
    building service, loss or theft of equipment, natural events.
- Per risk: `id`, `family`, `title`, `description` and `why` (EN and FR; `why` is one short sentence on why the risk applies to a business like yours, shown under "Based on" when no answer says more), `criteria` (which of confidentiality, integrity,
  availability it hits), `packs`, `always_assessed`, `audience` (`all` or `sensitive`, see docs/quick-path.md), 3 to 6 `measures` (id, EN, FR), two typical levels, and, for the risks of the `cloud-infra` pack, `refs` (see Sources).
- Top level: `packs`, the `tools` tick-list of the first screen (each tool implies packs), `origins`, `objectives`,
  `generic_measures` (offered for a risk the person adds), and `sources`.
- Packs: `office-it`, `cloud-service`, `cloud-infra`, `website-shop`, `industrial`, and `all` (every organisation).
  The pack `cloud-infra` (servers, apps or data on a public cloud: tool `cloud_infra`) has the same shape as the others: 9 risks of its own
  (D16 to D20, A18 to A21) and five existing ones that also list it (D07, D11, D13, A05, A09). Risk and measure texts name no provider.
  `always_assessed` risks are always put to the person for their pack; they cannot be discarded without a reason.
- The same measure has the same id and text in every risk that lists it. The quick path asks about each measure once, for the whole business (docs/quick-path.md). The measure `key_tasks` was called `documentation` before: answers saved under the old id still count.

## Sources

| Used for | Source | Licence |
|---|---|---|
| Deliberate risks: risk origins (state-backed group, activist, competitor, cybercriminal, staff member) and target objectives (make money, steal information, spread a message, take revenge, disrupt or create a crisis) | ANSSI, guide EBIOS Risk Manager v1.5, September 2024: the glossary entries "risk origin" and "target objective", and the workshop 2 example | Licence Ouverte / Open Licence (Etalab) |
| Accidental risks: the four families of threat sources (accidental, structural, environmental, and adversarial for theft) and their subtypes (user, privileged user, IT equipment, software, environmental controls, natural or man-made disaster, infrastructure failure) | NIST SP 800-30 Revision 1, Appendix D, Table D-2 "Taxonomy of threat sources" | US government work, no copyright |
| Cloud infrastructure risks (pack `cloud-infra`): `refs` on each risk lists the numbers of the recommendations for cloud customers (R1 to R17, sections 7.1 and 8) that the risk relates to. The report is cited by number only; its sentences are not copied | ANSSI / CERT-FR, "Cloud computing, état de la menace informatique", CERTFR-2025-CTI-001, version 1.0, 19 February 2025 (cert.cyber.gouv.fr) | cited, not copied; check the publication's terms |

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
