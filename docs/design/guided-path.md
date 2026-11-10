# Guided path: design

Status: design proposal, not built. Applies to the web app (`app/`) and the engine (`engine/`).

Atelier follows the ANSSI EBIOS Risk Manager method (guide v1.5, September 2024). "EBIOS" is a trademark
registered by the SGDSN (guide p.2, footnote 1). Product text uses the phrase "follows the ANSSI EBIOS Risk Manager
method" and nothing that suggests endorsement or a label.

Page numbers are the guide's printed pages ("guide p.N").

## 1. Goal and principles

Let a person with no security background, and possibly no architecture document, no business impact analysis and
no security baseline, produce a risk analysis that follows the method, in about 30 minutes, then refine it later.

1. **Honesty first.** The result reflects the answers given and the documents provided, nothing more. The product
   says so plainly, shows where every input came from, and lists what was assumed (section 2).
2. **The method stays as published.** The guided path is a preliminary risk study, a use the guide describes
   (guide p.14-15): workshop 1 at reduced depth, workshops 2 and 3, a simple technique for likelihood, and a
   treatment plan. Nothing is added to the method; where Atelier needs a rule the guide does not print, the rule
   is public, versioned and marked "Atelier rule, beyond the guide" (rules.md, rule 5).
3. **Humans answer, the engine computes.** Severity comes from the person's answer on the calibration's scale.
   Likelihood, risk level, scenario severity, stakeholder threat, pertinence, confidence and the action ranking
   are computed by the engine. The AI and the UI never set any of them.
4. **Plain questions, method fields behind them.** Every question names the study-format fields it fills.
   The expert workshop screens stay, as "expert mode", over the same study file.
5. **Works with nothing.** No documents and drafting off: the full path still works. Documents and AI only
   pre-fill answers that a person confirms.

## 2. Honesty

### 2.1 The statement, in three places

The same statement, word for word, appears:

1. on the start screen, above the three ways in;
2. on every result screen and every risk map (results page, register, maps, expert-mode map), next to the
   confidence figure;
3. in the header of every report and export (HTML/PDF report, Excel first sheet).

EN:
> This analysis reflects only the answers you gave and the documents you provided. Atelier has not inspected your
> systems. Without an architecture document, a business impact analysis and a security baseline, the analysis is
> only as good as the answers given. Parts based on defaults or "I don't know" are marked and listed as
> assumptions to confirm.

FR:
> Cette analyse reflète uniquement vos réponses et les documents fournis. Atelier n'a pas examiné vos systèmes.
> Sans document d'architecture, analyse d'impact sur l'activité et socle de sécurité, l'analyse ne vaut que par
> les réponses données. Les éléments fondés sur des valeurs par défaut ou sur « Je ne sais pas » sont signalés
> et listés comme hypothèses à confirmer.

The result screens and the report header add one line of facts: documents provided (by type), documents not provided,
number of answers, number of assumptions, open conflicts, confidence figure. Example: "Documents: none. Not
provided: architecture document, business impact analysis, security baseline. Answers: 64. Assumptions to
confirm: 11. Conflicts: 0. Confidence: 58% (medium)."

### 2.2 Where each input came from

Every input slot (an answer to one question about one element) has one source:

| Source | Badge | Meaning |
|---|---|---|
| `document` | D | Taken from a document, with a reference (document, page or cell): confirmed by a person, or used because it disagrees with an answer (document wins, section 9) |
| `answer` | A | Picked or typed by a person in the interview or in expert mode |
| `catalogue` | C | A typical value from a public catalogue, shown to the person and kept |
| `default` | ? | Question skipped; the question's default was used |
| `dont_know` | ? | The person answered "I don't know"; the question's default was used |

- Every element on screen (business value, feared event, stakeholder, path, risk) shows its badges.
- Each risk on the results page has a "Based on" line: e.g. "Severity: answer. Likelihood: 2 answers, 1 catalogue
  value, 3 don't know."
- The report has a section "Where this comes from": per workshop, the count of D / A / C / ? inputs, and the list
  of documents used.
- A document-proposed value that nobody confirmed is not in the study (same rule as drafting today, docs/app.md),
  except when it disagrees with an answer: then the document value is used and the conflict is shown (section 9).
- A missing document is shown as such: the result screens and the report list the document types not provided
  and the parts of the analysis that rest on answers instead (section 9).

### 2.3 Confidence figure (Atelier rule, beyond the guide)

The guide has no confidence measure. The engine computes one from the sources, so it is reproducible.

- Weight per input: `document` 1.0, `answer` 0.75, `catalogue` 0.5, `default` and `dont_know` 0.
  A document with a reference weighs more than a recollection; this is how a missing document lowers confidence.
- Inputs of a risk: the severity of the feared event that sets its severity; the inputs of its likelihood
  (attacker motivation and resources, then either the 4 stakeholder criteria or the path's safeguards).
- Risk confidence = 0.5 x severity weight + 0.5 x mean weight of the likelihood inputs.
- Study confidence = mean of risk confidences, shown as a percentage and a band: high (80% or more), medium
  (50-79%), low (under 50%). With no documents the ceiling is 75%, and the screen says why.
- The weights live in the rules file (section 7) and are an open question (section 15).

### 2.4 Assumptions to confirm

The engine lists every input with source `default`, `dont_know` or `catalogue`: question, element, value used,
why, and who could confirm it (each question carries a "who would know" hint, e.g. "your IT provider"). The list
is ordered by effect: inputs of the highest-level risks first. It appears on the results page (count and link)
and as a report section. Confirming an assumption is one click back into that question.

## 3. Home screen

Above the three choices: the statement of 2.1. Below: "Continue a study" (list) and "See the worked example"
(the guide's example, read-only).

| Way in | EN label | FR label | What happens |
|---|---|---|---|
| 1 | Start from scratch: answer simple questions (about 30 minutes) | Partir de zéro : répondre à des questions simples (environ 30 minutes) | Guided interview, section 6 |
| 2 | I have documents (Word, PDF, Excel or pasted text) | J'ai des documents (Word, PDF, Excel ou texte collé) | Upload, say what each document is, AI pre-fills answers, the person confirms, the interview asks what is left |
| 3 | I already have a risk analysis | J'ai déjà une analyse de risque | Existing review mode (`.xlsx` import, docs/import.md), or study JSON import |

Ways 1 and 2 are one mechanism with zero, one or several documents (section 10). Way 3 can end with "Continue
in the guided path": the imported study opens in the interview, which asks only for what the import did not fill.

## 4. One mechanism

```
documents (0..n) --extract--> text --AI (optional)--> proposed answers --person confirms--+
interview ------------------------------------------> answers ---------------------------+--> answer slots
catalogues --------------------------------------------> typical values (kept or not) ----+        |
                                                                                                  v
                       engine: derive(answers, question bank, catalogues, rules, calibration) --> study
                                                                                                  |
                       engine: validate, register, maps, confidence, assumptions, top actions <---+
```

- An answer slot is (question id, element id). The study stores answers with their source (section 12).
- `derive` is deterministic: the same answers, bank version, catalogue version, rules version and calibration
  give the same study. Generated elements get stable ids from their slot, so re-deriving keeps links.
- An element edited in expert mode is pinned (`source: answer`, `pinned: true`) and is not regenerated; if a
  later answer conflicts with it, the conflict is listed, not overwritten.
- The interview skips a question whose slot is already filled by a confirmed document answer, and shows it in a
  "From your documents" summary instead, where it can be changed.

## 5. Quick path: flow and time budget

One question per card. Buttons: answer, "I don't know", Back. "Why we ask" opens one plain sentence and the guide
page. Autosave after each answer; resume later. Progress shows section and minutes left.

| Step | Workshop | Questions | Target time |
|---|---|---|---|
| About you | W1 scope (guide p.19-20) | Q-ORG-01 to 08 | 3 min |
| What matters most | W1 business values (p.20-21) | Q-BV-01 to 03, 3 to 5 values | 3 min |
| What supports it | W1 supporting assets (p.21-22) | Q-SA-01 to 03 | 4 min |
| If it stopped | W1 feared events, severity (p.24-27) | Q-FE-01 to 05, per value | 7 min |
| The basics | W1 baseline (p.28-31) | Q-BL-01 to 13 | 3 min |
| Who might attack | W2 (p.34-40) | Q-RO-01 to 05, up to 6 cards | 3 min |
| Who you work with | W3 stakeholders (p.44-47) | Q-SH-01 to 07, up to 5 parties | 4 min |
| How it could happen | W3 paths, W4 (p.48-49, p.60-65) | Q-SS-01, Q-OS-01 | 2 min |
| Results | W5 (p.70-77) | none before the results; Q-TR-01 to 02 after | 1 min |
| | | | **30 min** |

Caps in the quick path: 5 business values (guide p.21 suggests 5 to 10 for a full study; a preliminary study
keeps the main ones, p.15 note 2), 6 risk origin cards (3 to 6 pairs, p.38), 5 stakeholders, 3 paths per pair
(p.49). Refinement lifts the caps.

## 6. Question bank

### 6.1 Conventions

- Stored in `catalogues/questions/atelier-qb-1.json`: id, section, text `{en, fr}`, help `{en, fr}`, example,
  answer type, options with codes, `dont_know` value, `fills` (study-format paths), `doc` (document types that
  may pre-fill it), `ai` (`prefill`, `hint` or `none`), `who_knows` `{en, fr}`, guide pages.
- `ai: prefill`: the AI may pre-select a value from a document; a person confirms it. `ai: hint`: the AI may show
  the passage it found, nothing is pre-selected. `ai: none`: no AI involvement. Rating questions (severity,
  motivation, stakeholder criteria, decisions, treatment) are never `prefill`.
- "I don't know" (`dont_know`) is always offered. General rule: it never makes a risk look lower than a real
  answer could; where the catalogue has a typical value it uses it, otherwise the cautious end of the scale.
  Every use is flagged (section 2.4).
- Doc column codes: ARD architecture document, BIA business impact analysis, SRS security requirements
  specification, PSB project security baseline, BCA baseline compliance assessment (section 9; "BCA" is only a
  column code in this file, not a name used in the product). Any document type can be used if it contains the
  information; the column says where it is usually found.
- `[BV]` is replaced by the business value's label.

### 6.2 W1-A: about you (scope, guide p.19-20)

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-ORG-01 | What should we call this analysis? | Comment voulez-vous appeler cette analyse ? | "Risk review 2027 - Harbour dental clinics" | "My risk analysis"; not flagged (no effect on results) | `study.name` | any / prefill |
| Q-ORG-02 | In one or two sentences: what does your organisation do, and for whom? | En une ou deux phrases : que fait votre organisation, et pour qui ? | "We run four dental clinics and book about 300 appointments a week." | Required to continue; can be pre-filled | `study.mission` (new) | ARD, BIA / prefill |
| Q-ORG-03 | Which sector is closest to yours? (list) | Quel secteur est le plus proche du vôtre ? (liste) | "Health care" | "General"; flagged: suggestions are less specific | `study.sector` (new); picks catalogue packs | any / prefill |
| Q-ORG-04 | How many people work there? 1-9 / 10-49 / 50-249 / 250+ | Combien de personnes y travaillent ? 1-9 / 10-49 / 50-249 / 250+ | "10-49" | "10-49"; flagged | `study.size` (new); orders tick-lists | any / prefill |
| Q-ORG-05 | Should this analysis cover the whole organisation, or one activity or system? Which one? | Cette analyse couvre-t-elle toute l'organisation, ou une activité ou un système ? Lequel ? | "Only our online booking service" | "The whole organisation"; flagged | `study.scope` | ARD / prefill |
| Q-ORG-06 | Who will decide which risks are acceptable? (role) | Qui décidera des risques acceptables ? (fonction) | "The managing director" | "Not named yet"; flagged (the guide requires it, p.19) | `study.acceptance_owner` (new) | any / prefill |
| Q-ORG-07 | How often will you review this? | À quel rythme réviserez-vous cette analyse ? | "Attack paths every year, the whole analysis every 3 years" | 1 year / 3 years (the usual values, p.19); flagged | `study.cycles` (new) | SRS / prefill |
| Q-ORG-08 | Do rules or contracts require security measures from you? (tick: personal-data law, sector rules, customer contract requirements, a certification, none) | Des règles ou des contrats vous imposent-ils des mesures de sécurité ? (cocher) | "Personal-data law; customer contract requirements" | "Not identified"; flagged | `study.frameworks` (new); one `baseline` entry per ticked item, status asked in expert mode (p.28) | SRS, PSB / prefill |

### 6.3 W1-B: what matters most (business values, guide p.20-22)

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-BV-01 | Which of these could your organisation not do without? Tick 3 to 5, or add your own. (sector list: serving customers, producing or delivering, getting paid and paying, customer or patient records, know-how and designs, prices and bids, website or online service, accounting and legal records, quality and traceability records, payroll and HR) | Sans quoi votre organisation ne pourrait-elle pas fonctionner ? Cochez 3 à 5 éléments, ou ajoutez les vôtres. | "Booking appointments; Patient records; Getting paid" | The sector's 3 first items, each flagged "proposed by Atelier, not chosen by you" | `business_values[].id, label, nature` (nature from the catalogue item) | BIA, ARD / prefill |
| Q-BV-02 | Who is in charge of [BV]? (role) | Qui est responsable de [BV] ? (fonction) | "Head of reception" | Empty; flagged | `business_values[].owner` | BIA / prefill |
| Q-BV-03 | (own entries only) Is [BV] mostly something you do, or information you keep? | [BV] est-il surtout une activité, ou une information que vous conservez ? | "Information we keep" | `process`; flagged | `business_values[].nature` | BIA / prefill |

### 6.4 W1-C: what supports it (supporting assets, guide p.21-22, p.86, p.91)

A thing the organisation runs is a supporting asset; a thing run by an outside company is also a stakeholder,
because its security does not depend on the organisation (guide p.21 footnote 10, p.91 note).

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-SA-01 | Which of these do you use? Tick all. (email; office files and shared folders; cloud storage; accounting or invoicing software; main business application; website; online shop or payment terminal; laptops and desktops; phones and tablets; servers on your premises; office network and Wi-Fi; machines or equipment run by computers; backups; paper records; key people) | Lesquels de ces outils utilisez-vous ? Cochez tout ce qui s'applique. | "Email; office files; practice-management software; laptops; Wi-Fi; backups" | If none ticked: email, office files, laptops; flagged | `supporting_assets[].id, label` | ARD / prefill |
| Q-SA-02 | Who looks after [asset]? We do / An outside company (name it) | Qui s'occupe de [outil] ? Nous-mêmes / Une entreprise extérieure (laquelle ?) | "An outside company: BrightDesk IT" | An outside company, not named (a placeholder stakeholder); flagged | if outside: `stakeholders[].id, name, category: supplier`, `stakeholders[].supporting_assets` (new) | ARD, SRS / prefill |
| Q-SA-03 | Which of your important activities rely on each tool? (grid, pre-ticked from the catalogue; "pick the 1 to 3 that matter most", p.21) | Quelles activités importantes reposent sur chaque outil ? (grille pré-cochée) | "Patient records: practice software, backups" | Catalogue pre-ticks kept; flagged | `supporting_assets[].business_values` | ARD, BIA / prefill |

### 6.5 W1-D: if it stopped (feared events and severity, guide p.24-27)

The options are the calibration's severity levels in plain words. For `anssi-v1.5` they are written from the
guide's example scale (p.26); a private calibration supplies its own plain wording (section 12). The person
picks the consequence; the engine stores the level number. Option 0 "Not relevant to us" creates no feared event.

| Level | EN | FR |
|---|---|---|
| 1 | We would manage without much trouble, using our margins. No effect on our work or on anyone's safety. | Nous nous en sortirions sans trop de difficultés, en puisant dans nos marges. Aucun effet sur l'activité ni sur la sécurité des personnes. |
| 2 | Work would be degraded and we would have some difficulties. Nobody's safety at risk. | L'activité serait dégradée, avec quelques difficultés. Aucun risque pour la sécurité des personnes. |
| 3 | Work would be badly degraded; we would get through with serious difficulty; people or property could be harmed. | L'activité serait fortement dégradée ; nous nous en sortirions avec de sérieuses difficultés ; des personnes ou des biens pourraient être touchés. |
| 4 | We could not carry on all or part of our activity; people could be seriously harmed; the organisation might not survive. | Nous ne pourrions plus assurer tout ou partie de l'activité ; des personnes pourraient être gravement touchées ; la survie de l'organisation serait en jeu. |

"I don't know" on any severity question gives level 3, flagged. Reason: level 3 is the lowest level the engine
checks for blind spots (guide p.73), so an unknown impact is never dropped silently.

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-FE-01 | If [BV] stopped for a day, what would it mean? | Si [BV] s'arrêtait pendant une journée, qu'est-ce que cela signifierait ? | Level 2 | 3; flagged | `feared_events[]`: `business_value`, `criterion: availability`, `label` "[BV] unavailable for more than a day", `threshold` "1 day" (new; p.25 note), `severity` | BIA / hint |
| Q-FE-02 | (asked if Q-FE-01 < 4) And if it stopped for a week? | Et si l'arrêt durait une semaine ? | Level 4 | max(Q-FE-01 answer, 3); flagged | a second availability event "for more than a week" when higher than Q-FE-01; else Q-FE-01's label becomes "a day or more" | BIA / hint |
| Q-FE-03 | (information, and processes that hold information) If [BV] leaked to a competitor, criminals or the public, what would it mean? | Si [BV] était divulgué à un concurrent, à des criminels ou au public, qu'est-ce que cela signifierait ? | Level 3 | 3; flagged | `feared_events[]` with `criterion: confidentiality` | BIA / hint |
| Q-FE-04 | If [BV] were secretly changed or wrong, and nobody noticed at once, what would it mean? | Si [BV] était modifié à votre insu ou faux, sans que personne ne s'en aperçoive tout de suite, qu'est-ce que cela signifierait ? | Level 4 | 3; flagged | `feared_events[]` with `criterion: integrity` | BIA / hint |
| Q-FE-05 | (each event of level 3 or 4) What would be hit? Tick: our customers or mission; people's health or safety; money; reputation; legal or regulatory; how we are run | Qu'est-ce qui serait touché ? Cocher : clients ou missions ; santé ou sécurité des personnes ; finances ; image ; juridique ou réglementaire ; gouvernance | "Customers; money; legal" | Empty; flagged as "justification missing" (p.27 note) | `feared_events[].impacts` (new; impact types of p.25 and p.27) | BIA / hint |

Traceability (p.24) and finer availability thresholds (e.g. "more than 2 hours", p.25) are in refinement.

### 6.6 W1-E: the basics (security baseline, guide p.28-31)

Answers: Yes / Partly / No / I don't know, mapped to `baseline[].status` applied / partial / not applied (the
guide's green / orange / red, p.29). "I don't know" gives `not applied`, flagged. Each item fills `baseline[]`
with `reference` "atelier-baseline-1:BLnn", `status`, and an optional `gap` text ("What is missing?",
shown after Partly or No). Every item also feeds the safeguards of attack paths (section 7.4).

The wording is Atelier's own. Mapping items to the ANSSI IT hygiene guide (listed in the guide's bibliography,
p.84) is wanted but waits for its licence to be checked (section 15).

| ID | EN | FR | Example | Who would know |
|---|---|---|---|---|
| Q-BL-01 | Do email and remote access ask for a second step (a code or an app), not just a password? | La messagerie et les accès à distance demandent-ils une deuxième étape (code ou application), pas seulement un mot de passe ? | Partly: email yes, remote access no | IT provider |
| Q-BL-02 | Are security updates installed on computers, phones and servers within about a month? | Les mises à jour de sécurité sont-elles installées sur les ordinateurs, téléphones et serveurs en un mois environ ? | Yes | IT provider |
| Q-BL-03 | Are backups kept away from your network, and was a restore tried in the last year? | Les sauvegardes sont-elles conservées à l'écart de votre réseau, et une restauration a-t-elle été testée dans l'année ? | No | IT provider |
| Q-BL-04 | Does everyone have their own account (no shared logins), with administrator rights only for those who need them? | Chacun a-t-il son propre compte (pas d'identifiants partagés), avec des droits d'administrateur réservés à ceux qui en ont besoin ? | Partly | IT provider |
| Q-BL-05 | When someone leaves, are their accounts closed on their last day? | Quand quelqu'un part, ses comptes sont-ils fermés le dernier jour ? | Yes | HR, IT provider |
| Q-BL-06 | Have staff been shown in the last year how to spot a fake email or phone call? | Le personnel a-t-il appris dans l'année à repérer un faux courriel ou un faux appel ? | No | Manager |
| Q-BL-07 | Do all computers have up-to-date protection software (antivirus or similar)? | Tous les ordinateurs ont-ils un logiciel de protection à jour (antivirus ou équivalent) ? | Yes | IT provider |
| Q-BL-08 | Are important systems kept apart from the office network and guest Wi-Fi? | Les systèmes importants sont-ils séparés du réseau bureautique et du Wi-Fi invités ? | I don't know | IT provider |
| Q-BL-09 | Is administration done from dedicated accounts, never from one used for email and web browsing? | L'administration se fait-elle depuis des comptes dédiés, jamais depuis un compte utilisé pour la messagerie et la navigation ? | I don't know | IT provider |
| Q-BL-10 | Would someone notice unusual activity, such as large transfers of data out or logins at night? | Quelqu'un remarquerait-il une activité inhabituelle, comme de gros envois de données vers l'extérieur ou des connexions la nuit ? | No | IT provider |
| Q-BL-11 | Do you know which outside companies can access your systems, and can you cut their access quickly? | Savez-vous quelles entreprises extérieures accèdent à vos systèmes, et pouvez-vous couper ces accès rapidement ? | Partly | Manager, IT provider |
| Q-BL-12 | Are your most sensitive files limited to the people who need them, and protected (for example encrypted)? | Vos fichiers les plus sensibles sont-ils réservés à ceux qui en ont besoin, et protégés (par exemple chiffrés) ? | Partly | Manager |
| Q-BL-13 | If you were hacked tomorrow, do you know who to call and what to do first? | Si vous étiez piraté demain, savez-vous qui appeler et quoi faire en premier ? | No | Manager |

Doc / AI for all Q-BL: BCA, PSB / `prefill` when the document records a status for a measure mapped to the
item (a documented fact, not a judgement); SRS, ARD / `hint` otherwise (the passage is shown; the person picks).

If 7 or more items are No or I don't know, the results page says: "Basics first: the guide advises strengthening
the basics before studying targeted attacks (guide p.31). Your results below assume the gaps stay open." The study
continues, which is the guide's second option on the same page.

### 6.7 W2 light: who might attack (risk origins and target objectives, guide p.34-40)

Atelier shows up to 6 cards from the public catalogue `catalogues/risk-origins-1.json`, filtered by sector and by
the feared events found. Each card is one pair (risk origin, target objective) in plain words, with the feared
events it would aim at, pre-ticked by criterion (p.40 note: every pair links to feared events and back).

Catalogue (original wording; examples of origins in the guide: p.37, p.93):

| Card | Origin | Objective (plain) | Aims at | Resources (catalogue value, 1-4) |
|---|---|---|---|---|
| RO-C01 | Criminal group | Lock or steal your data and demand a ransom | availability, confidentiality | 3 |
| RO-C02 | Criminal group | Divert payments (fake invoice, changed bank details) | integrity of payments | 2 |
| RO-C03 | Criminal group | Steal personal data to sell it | confidentiality of personal data | 2 |
| RO-C04 | Competitor | Steal know-how, prices or bids to gain an edge | confidentiality of information | 3 |
| RO-C05 | Activist | Disrupt your activity to make a point | availability, integrity | 2 |
| RO-C06 | Activist | Expose your practices by leaking information | confidentiality | 2 |
| RO-C07 | Insider or former staff | Take revenge, or take data to a new job | integrity, confidentiality | 2 |
| RO-C08 | State-backed group (only offered for public bodies, essential services and sensitive research) | Spy on sensitive information, or prepare sabotage | confidentiality, availability | 4 |
| RO-C09 | Opportunist | Use your systems for other attacks, or show off | availability | 1 |

The resources values are Atelier catalogue values (the guide prints none) and count as `catalogue` inputs.

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-RO-01 | Could this happen to you? Keep / Not for us | Cela pourrait-il vous arriver ? Garder / Pas pour nous | Keep | The engine's suggestion from pertinence (7.1): high or medium → selected, low → monitoring; flagged | `risk_origins[].origin, objective, resources, decision`, `catalogue` (new) | none |
| Q-RO-02 | How much would this attacker gain by succeeding against you, compared with other targets? Little / Some / A lot / You would be a prime target | Que gagnerait cet attaquant à réussir contre vous, par rapport à d'autres cibles ? Peu / Un peu / Beaucoup / Vous seriez une cible de choix | A lot | The card's typical value; flagged | `risk_origins[].motivation` (1-4) | none |
| Q-RO-03 | Have you heard of this kind of attack? Not that I know / In other sectors / In our sector / Against us or our partners | Avez-vous entendu parler de ce type d'attaque ? Pas à ma connaissance / Dans d'autres secteurs / Dans notre secteur / Contre nous ou nos partenaires | In our sector | The card's typical value; flagged | `risk_origins[].activity` (new, 1-4; criterion of p.38) | any / hint |
| Q-RO-04 | Which of these would they aim at? (feared events, pre-ticked) | Que viseraient-ils ? (événements redoutés, pré-cochés) | "Patient records leaked" | Pre-ticks kept; flagged | `risk_origins[].feared_events` | none |
| Q-RO-05 | Anyone else who might want to harm you? (optional; then "Which card is it closest to?" for resources) | Quelqu'un d'autre pourrait-il vouloir vous nuire ? (facultatif) | "A former business partner in a dispute" | Not asked again; resources 3 if the closest card is unknown, flagged | a new `risk_origins[]` entry | any / prefill (text only) |

### 6.8 W3 light: who you work with (stakeholders, guide p.42-55)

Stakeholders come from Q-SA-02 and from a tick-list. The four criteria are those of the guide: exposure
(dependence, penetration) and cyber reliability (maturity, trust) (p.45). The plain wording of each level is
Atelier's own; v1.5 does not print level definitions.

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-SH-01 | Which of these outside parties work with you? (IT provider; software or cloud providers; accountant; maintenance contractor; cleaning or security company; customers or partners connected to your systems; partners who hold your data; logistics; bank or payment provider; parent or sister company) | Lesquels de ces partenaires extérieurs travaillent avec vous ? (liste) | "IT provider; accountant; lab partner" | Nothing added; flagged "ecosystem not reviewed" | `stakeholders[].id, name, category` (customer / partner / supplier, as p.46) | ARD, SRS / prefill |
| Q-SH-02 | If [party] stopped working with you tomorrow, how hard would it be? Easy to replace within days / Weeks, some trouble / Months, serious trouble / We could not work | Si [partenaire] cessait de travailler avec vous demain, ce serait difficile à quel point ? Remplaçable en quelques jours / Quelques semaines, avec des difficultés / Plusieurs mois, de sérieuses difficultés / Nous ne pourrions plus travailler | Months, serious trouble | Catalogue value for that kind of party; flagged | `stakeholders[].dependence` | BIA / hint |
| Q-SH-03 | What access does [party] have to your systems or data? None, or public information only / Limited: some data or a basic account / Broad: a lot of data or remote access / Full: administrator rights, or it runs your systems | Quel accès [partenaire] a-t-il à vos systèmes ou données ? Aucun, ou données publiques / Limité / Large : beaucoup de données ou accès à distance / Total : droits d'administrateur, ou il gère vos systèmes | Full | Catalogue value for that kind of party; flagged | `stakeholders[].penetration` | ARD, SRS / hint |
| Q-SH-04 | As far as you know, how well does [party] protect its own systems? Weakly (known problems) / Basic / Good (it can show its practices) / Strong (independent audit or certification) | À votre connaissance, [partenaire] protège-t-il bien ses propres systèmes ? Faiblement / De façon basique / Bien / Très bien (audit indépendant ou certification) | Basic | 1 (weakly); flagged | `stakeholders[].maturity` | SRS / hint |
| Q-SH-05 | Do your contract and your experience give you confidence in how [party] handles security? No security terms or bad experience / Some terms, never checked / Clear terms, followed / Clear terms, checked by audit or reports | Votre contrat et votre expérience vous donnent-ils confiance dans la sécurité chez [partenaire] ? | Some terms, never checked | 1; flagged | `stakeholders[].trust` | SRS / hint |
| Q-SH-06 | Which of your important activities does [party] touch? (pre-ticked from Q-SA-03) | Quelles activités importantes [partenaire] touche-t-il ? | "Patient records" | Pre-ticks kept; flagged | `stakeholders[].business_values` (new) | ARD, BIA / prefill |
| Q-SH-07 | Keep [party] in the analysis as a possible way in? (engine suggestion shown) | Garder [partenaire] dans l'analyse comme point d'entrée possible ? | Keep | The engine's suggestion (7.3); flagged | `stakeholders[].critical` | none |

In the quick path, parties with access (Q-SH-03 at "Broad" or "Full", or unknown) are asked first; the others
wait for refinement.

### 6.9 W3-W4 light: how it could happen (attack paths and operational scenarios, guide p.48-68)

For each kept pair, the engine proposes up to 3 paths (p.49) from `catalogues/attack-paths-1.json`: direct paths
matching the pair's criteria, and one path through each kept stakeholder that touches a targeted business value.
Each catalogue path carries a plain operating-mode text and its safeguards (baseline items or path-specific
questions).

| Path | Kind | Plain label | Safeguards |
|---|---|---|---|
| AP-D1 | direct | Get into your systems and copy information | BL-01, 02, 06, 08, 09, 10, 12 |
| AP-D2 | direct | Lock or wipe your systems (ransomware) | BL-01, 02, 03, 04, 06, 07, 09 |
| AP-D3 | direct | Alter data or outputs in a business application | SG-REL, SG-LOG |
| AP-D4 | direct | Stop machines or equipment run by computers | BL-08, BL-11, SG-MAINT |
| AP-D5 | direct | Trick staff into paying or sending data | BL-06, SG-PAY |
| AP-D6 | direct | Make your website or online service unreachable | SG-DOS, BL-13 |
| AP-D7 | direct | Through someone inside (bribed or unhappy staff or contractor) | BL-04, BL-05, BL-10, BL-12 |
| AP-S1 | stakeholder | Through [party], which has access to your systems or holds your data | the party's four criteria |
| AP-S2 | stakeholder | Through equipment or software that [party] supplies or maintains | the party's four criteria |

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-SS-01 | Could [origin] do it this way: [path]? Keep / Not possible here | [Source] pourrait-elle procéder ainsi : [chemin] ? Garder / Impossible ici | Keep | Keep; flagged | `strategic_scenarios[]` (one per pair and set of targeted feared events, p.72 footnote 36): `risk_origin`, `feared_events`, `paths[]` with `label`, `stakeholder`, `kind`, `catalogue` (new); `severity` by the engine (p.49) | ARD / hint |
| Q-OS-01 | (path-specific safeguards not covered by the basics) e.g. SG-REL "Are labels, orders or other outputs checked before they leave?"; SG-LOG "Are changes to important data recorded and reviewed?"; SG-MAINT "Do maintenance contractors only connect with equipment you control?"; SG-PAY "Is a change of bank details confirmed by phone?"; SG-DOS "Is your website protected against floods of traffic?" Yes / Partly / No | (garde-fous propres au chemin) ex. « Les étiquettes, commandes ou autres sorties sont-elles contrôlées avant de partir ? » ; « Les modifications de données importantes sont-elles tracées et revues ? » ; « Les prestataires de maintenance ne se connectent-ils qu'avec du matériel que vous maîtrisez ? » ; « Un changement de coordonnées bancaires est-il confirmé par téléphone ? » ; « Votre site est-il protégé contre un afflux de trafic ? » | Yes | Counted as a gap (No); flagged | `paths[].safeguards` (new) and their status; `operational_scenarios[]` (one per kept path, p.60): `strategic_scenario`, `path`, `description` from the catalogue, `likelihood` and `likelihood_basis` by the engine | PSB, SRS / hint |

The AI may reword a path label or a description to fit the organisation (`prefill`, text only), never the
structure or any value.

### 6.10 W5 light: after the results (guide p.70-79)

| ID | EN | FR | Example | Don't know → | Fills | Doc / AI |
|---|---|---|---|---|---|---|
| Q-TR-01 | What do you want to do about [risk]? Reduce / Accept / Share it (insurance, contract) / Stop the activity / Decide later | Que voulez-vous faire de [risque] ? Réduire / Accepter / Partager (assurance, contrat) / Arrêter l'activité / Décider plus tard | Reduce | "Decide later": `treatment` empty; the proposal from the level's acceptability class (p.74) is shown, not stored; flagged "decision pending" | `risks[].treatment` | none |
| Q-TR-02 | For [action]: who will do it, and by when? | Pour [action] : qui s'en charge, et pour quand ? | "IT provider, end of March" | Empty; the engine's existing warning applies (measure without owner or due date) | `measures[].owner, due`, `status: planned` | none |

Risks are created by the engine, one per kept path (a risk scenario is a path and its operational scenario,
p.10 figure 3): `risks[]` with `operational_scenario`, `label` "[origin] could [objective] [path]",
`severity` (from the scenario, p.62, p.65), `likelihood` (engine), `likelihood_target` (engine, 7.6).

## 7. What the engine computes

All rules below are in one public file, `rules/guided-1.json`, loaded by a new engine module
(`atelier_engine/guided.py`). A calibration may name another rules file; client-specific rules are private
plug-ins. Each rule is marked as from the guide or "Atelier rule, beyond the guide".

### 7.1 Pertinence of a pair (criteria from the guide p.38; scoring is an Atelier rule)

Sum of motivation, resources and activity (each 1-4): 3-5 low, 6-8 medium, 9-12 high. On the guide's four
example pairs (p.39) this gives the guide's column: competitor 4+3+4 = 11 high; activist sabotage 3+2+2 = 7
medium; activist leak 2+1+1 = 4 low; criminal 2+2+1 = 5 low (word scale read as 1 = faible, 2 = modérée,
3 = significative, 4 = importante). The pertinence only suggests the decision; the person decides (Q-RO-01).

### 7.2 Attacker strength (inputs from the guide p.65; formula is an Atelier rule)

A = ceil((motivation + resources) / 2), 1-4. The guide's likelihood estimate weighs the attacker's resources and
motivation against the baseline and the ecosystem's weaknesses (p.65, p.94).

### 7.3 Stakeholder threat (criteria from the guide p.45; formula inferred, Atelier rule)

T = (dependence x penetration) / (maturity x trust). v1.5 names the criteria and the exposure and reliability
axes (p.45, p.47) but does not print a formula. This one reproduces the guide's figures on p.54 (threat 2 to
1.3 when penetration goes from 3 to 2; 3 to 2 when maturity goes from 2 to 3; 2.25 to 1.5 when penetration goes
from 3 to 2). Zones from the thresholds on p.47: watch 0.2, control 0.9, danger 2.5. Suggested critical
(Q-SH-07): T of 0.9 or more.

### 7.4 Path ease (Atelier rule)

- Through a stakeholder: E = 1 if T < 0.9; 2 if 0.9 <= T < 2.5 (control zone); 4 if T >= 2.5 (danger zone: the
  "weak link" an attacker picks first, p.44).
- Direct: g = gaps / safeguards, where No and "I don't know" count 1, Partly 0.5, Yes 0. E = 1 if g = 0;
  2 if 0 < g < 0.5; 3 if g >= 0.5.

### 7.5 Likelihood (Atelier rule)

L = min(A, E): an attack is as likely as the weaker of the attacker's strength and the path's ease. With no
information about the path, L = A, which matches the guide's note that the pair's pertinence indicates the
likelihood when workshop 4 is not done (p.49). The engine writes `operational_scenarios[].likelihood`,
`risks[].likelihood` and `likelihood_basis` (rule version and inputs). Properties tested: L never drops when an
answer moves to "I don't know"; L rises or stays when any input worsens.

### 7.6 Target likelihood and top 5 actions

- Measures come from `catalogues/measures-1.json`; each closes one or more safeguards or improves a stakeholder
  criterion by one step (e.g. "Give maintenance contractors equipment you manage": penetration -1, as in the
  guide's example p.54). Baseline gaps also produce measures (p.18, p.76).
- Current likelihood counts only measures in place (p.60 note; for stakeholders, p.53 footnote 26). Target likelihood recomputes L with the
  planned measures applied.
- Ranking of candidate measures, deterministic: (1) number of risks whose level drops, highest levels first;
  (2) total drop in level ranks; (3) number of risks whose likelihood drops; (4) baseline gap closed; (5) effort
  (+, ++, +++ as in the plan of p.77); (6) id. The top 5 are shown with the reason, e.g. "Lowers R3 from High to
  Medium". The person adds owner and due date (Q-TR-02).
- Pending assumptions are not actions; they appear in their own list (2.4).

### 7.7 Checks added to `validate`

- Error: a stored likelihood whose basis is a rule but which differs from the rule's result.
- Warning: a selected pair with no kept path; a feared event linked to no pair (p.40 note); an expert-pinned
  element that conflicts with a later answer; more than 6 pairs or more than 3 paths per pair (p.38, p.49).

## 8. Results first

After the quick path the person sees, on one page:

1. The honesty statement (2.1), the fact line and the confidence figure.
2. The risk map now and at target (engine SVG, calibration orientation) and the tabular alternative.
3. Top 5 actions with their reason.
4. Risks in plain sentences, each with its level, its acceptability class (p.74) and its "Based on" line.
5. Assumptions to confirm (count, link), the "basics first" banner if it applies, blind spots in plain words
   (p.73).
6. Buttons: Improve this analysis, Expert mode, Download report, Download Excel, Study JSON.

"Improve this analysis" is a queue: assumptions first, then deeper questions (more business values, traceability,
availability thresholds, more stakeholders, elementary actions and residual risk sheets in expert mode, p.78).
Expert mode is the existing workshop screens; computed fields stay read-only there and show their basis.

## 9. Document-driven path (internal use)

Internal studies receive any combination of the documents below. The workflow is the same as section 4; this
section says what each document can fill, what is asked when it is missing, and the effect on confidence.

The person uploading says what each document is (a type picker); the app does not guess the type. Types:
architecture document (ARD), business impact analysis (BIA), security requirements specification (SRS),
project security baseline (PSB), baseline compliance assessment (when required), other. Internal studies are
private: drafting uses only a route approved for private data (today: local only, docs/app.md).

| Document | Can fill (when it contains it) | Asked in the interview when missing | Effect on confidence when missing |
|---|---|---|---|
| ARD: architecture document | `study.scope`; `supporting_assets[]` (applications, servers, networks, interfaces); `supporting_assets[].business_values` if flows are described; `stakeholders[]` (hosting, managed services, interconnections) and `stakeholders[].supporting_assets`; hints for penetration (Q-SH-03), network separation and admin access (Q-BL-08, 09), path keep/discard (Q-SS-01). The guide builds on the system's map: p.21, p.44, p.59 | Q-ORG-05, Q-SA-01 to 03, Q-SH-01, Q-SH-03, Q-SH-06, Q-BL-08, 09 | Those inputs come from answers (0.75) or defaults (0) instead of 1.0; stakeholder paths rest on recollection |
| BIA: business impact analysis | `study.mission`; `business_values[]` with `owner`; availability thresholds (`threshold`); hints for each severity question (Q-FE-01 to 04) and impacts (Q-FE-05); hints for dependence (Q-SH-02) | Q-ORG-02, Q-BV-01 to 03, Q-FE-01 to 05, Q-SH-02 | Severity inputs, half of each risk's confidence, come from answers or defaults |
| SRS: security requirements specification | `study.frameworks`; `baseline[]` entries for applicable requirements (p.28: third-party and internal rules); hints for supplier contract terms (Q-SH-04, 05), path safeguards (Q-OS-01), review cycles (Q-ORG-07) | Q-ORG-07, 08, Q-SH-04, 05 | Requirements default to the Atelier checklist; safeguard inputs come from answers or defaults |
| PSB: project security baseline | `baseline[]` entries: the measures that apply, with `reference` (the structure of the guide's table, p.29-30); status and gaps only if the document records them | The Atelier checklist (Q-BL-01 to 13) stands in for the list of measures | Baseline references are generic rather than the project's own |
| Baseline compliance assessment (when required): a graded check of compliance against the project security baseline | `baseline[].status` per measure (applied / partial / not applied, p.29) and `baseline[].gap`; through the mapping below, the answers to Q-BL-01 to 13 and to path safeguards (Q-OS-01) | Q-BL-01 to 13, Q-OS-01 | Every direct path's ease rests on answers or defaults |
| Other | Hints only, for any `hint` or `prefill` question | n/a | n/a |

Mapping baseline measures to the checklist: the PSB's measures and the assessment's grades keep their own
references in `baseline[]`. Path ease (7.4) uses the Atelier checklist items, so each document measure is
mapped to one or more checklist items. The AI may propose the mapping; a person confirms it. A checklist item
with no mapped measure is asked as usual.

Rules:

1. **The app never stops for a missing document.** It carries on with the plain questions for that part. Every
   result screen and the report show the missing document types, e.g. "Not provided: business impact analysis.
   Severities come from your answers." Next to the honesty statement (2.1).
2. **Skipping is allowed and flagged.** The plain questions for a part with no document are offered; a skipped
   question takes its default (source `default`), lowers confidence and appears in the assumptions list (2.4).
3. **A document wins over an answer.** When a document value (with a verified quote) disagrees with an answer,
   the engine uses the document value, and the conflict is shown on the element, on the results page and in the
   report, with both values, their sources and the quote. The person decides: keep the document value, or keep
   the answer with a reason (stored as `answer`, with the conflict and the reason recorded). Until decided the
   conflict stays open and listed.
4. A document fills nothing on its own otherwise. The AI proposes answers with a quote; the app keeps a proposal
   only if the quote is found verbatim in the extracted text; a person confirms each one (source `document`,
   with reference).
5. Rating questions get hints, never pre-selected values (6.1). A BIA's own impact scale is not translated into
   the calibration's levels automatically; the person picks the level with the quote in view. Baseline status
   from a compliance assessment is a documented fact and is pre-filled (6.6).
6. The report lists the documents received and the types missing, and per workshop which inputs came from which
   document.

## 10. Public path: the same mechanism

The public build runs section 4 with zero, one or several documents. With zero, every slot is an answer, a
catalogue value or a default; with documents, the confirmed document answers replace questions. Customers
often have no ARD, no BIA and no baseline; the type picker offers the same types with plain names ("a description
of your systems", "an analysis of what happens if activities stop", "security rules you must follow", "a list of
security measures in place", "a check of which of those measures are applied"), plus "other". Rules 1 to 6
of section 9 apply unchanged: nothing stops for a missing document, skips are flagged, a document wins over an
answer and the conflict is shown.

- Extraction: `.txt`, `.md`, `.docx`, `.pdf` as today; add `.xlsx` (cell text read from the archive, same limits
  as `.docx`) and keep pasted text. No OCR (as today).
- Drafting off: the documents path still works; the documents sit beside the interview for the person to read.
- Drafting tasks: `prefill.answers` (question ids, values for `prefill` questions, quotes for `hint` questions)
  and `rephrase.catalogue` (labels only). Both through the existing adapter `draft(task, context)`; the model's
  answer is checked against the bank's schema and unknown fields are dropped.

## 11. Forward-looking constraints

### 11.1 Languages

- EN and FR from the first increment. All UI text in `app/i18n/en.json` and `fr.json` (keys, no text in views);
  question bank, catalogues and plain calibration wording carry `{en, fr}`.
- Engine messages become codes with parameters (e.g. `scenario.severity_mismatch {id, expected}`); the app
  renders them in the user's language. The CLI keeps English output from the same codes.
- Study content stays in the language the person typed; the study records `language`.

### 11.2 Ready for accounts and separate customers (no cloud design here)

- Every stored object belongs to a workspace (one customer). Locally there is one workspace, `local`.
  `App.store_for(user)` becomes `store_for(user, workspace)`; paths and ids are scoped by workspace.
- The study file carries no personal data about users: answers may carry an opaque `by` id; names live outside
  the study file.
- Private overlays (calibrations, rules, catalogues, question packs, layouts, review plugin) are looked up per
  workspace, then in `ATELIER_PRIVATE_DIR`, then public.

### 11.3 AI route

- Route profiles in settings: `off`, `local`, `remote`, each with `private_data_allowed` (true only for local
  today). A later EU-hosted route is a `remote` profile the operator marks as allowed for private data after its
  own review; the code path does not change.
- The guided path never needs AI. The AI never sets a level, a severity, a rating, a decision or a treatment.

### 11.4 Public build and private material

| Public (repository) | Private (plug-ins, `ATELIER_PRIVATE_DIR`, per workspace later) |
|---|---|
| engine, app, question bank, catalogues and rules in Atelier's own words; `anssi-v1.5` calibration; the guide's worked example and its answers fixture; invented examples | client calibrations, client rules, client layouts, client catalogue overlays and question packs, the review plugin; all client studies and documents |

- The ANSSI guide v1.5 is under Licence Ouverte / Open Licence (Etalab V1), as printed on its back cover and
  credited in `NOTICE`. Any other source needs its licence checked before any text, numbering or list is copied
  (section 15, "To verify").
- Client data never enters the repository. Generic lessons may improve questions and catalogues: written fresh,
  with no client text or detail, reviewed by a second person, recorded in the changelog as "field feedback".
- Release check: a script refuses a public build that contains files from a private directory, a catalogue entry
  without a source and licence field, or the word "EBIOS" outside the approved phrases.

## 12. Study format additions (`atelier-study` 0.2)

All optional; a 0.1 study stays valid.

| Where | Addition |
|---|---|
| `study` | `mission`, `sector`, `size`, `acceptance_owner`, `cycles` {`strategic_years`, `operational_years`}, `frameworks` [], `language`, `workspace`, `path` (`guided` / `expert` / `review`), `question_bank`, `catalogues`, `rules` (versions), `documents` [{`id`, `type`, `name`}] |
| `answers` (new) | [{`q`, `about` (element id or null), `value`, `source` (document / answer / catalogue / default / dont_know), `ref` {`document`, `page` or `cell`, `quote`}, `by`, `at`, `conflict` {`other_value`, `other_source`, `decision`, `reason`}}] |
| `feared_events[]` | `threshold`, `impacts` [] |
| `risk_origins[]` | `activity`, `catalogue` |
| `stakeholders[]` | `supporting_assets` [], `business_values` [], `catalogue` |
| `strategic_scenarios[].paths[]` | `kind` (direct / stakeholder), `catalogue`, `safeguards` [{`id`, `status`}] |
| `operational_scenarios[]`, `risks[]` | `likelihood_basis` {`rule`, `inputs`}; `likelihood_target_basis` |
| `measures[]` | `catalogue`, `closes` [safeguard ids], `effort` |
| any element | `pinned` (edited in expert mode) |
| calibration file | optional `severity[].plain`, `likelihood[].plain`, `levels[].plain` {`en`, `fr`}; optional `rules` |

## 13. Acceptance tests

### 13.1 A non-security person, unaided, under 30 minutes

- Five participants with no security role, each given a one-page brief of an invented organisation (e.g. a
  group of dental clinics, a small online shop, a joinery workshop). No help during the run.
- Pass: at least 4 of 5 reach the results page in under 30 minutes, and each can say in their own words what
  the top action is and why. Every question where 2 or more hesitate for over 30 seconds, ask what a word
  means, or answer against the brief is rewritten before the next round.
- Automated companion: an end-to-end script answers the brief through the UI and checks the screen count and
  that the study validates with no errors.

### 13.2 The guide's worked example through the guided path

Fixture `examples/guided/anssi-vaccine-answers.json`: answers only from the question bank, each with the guide
page it rests on. The test derives the study, then compares with `examples/anssi-guide-vaccine-example.json`.

Pass: zero errors and zero warnings (as the example today); the same feared-event severities by business value
and criterion (3, 4, 4); the same strategic scenario severities (3, 4, 4); for R1-R5, the same severity,
likelihood and level. Labels may differ.

Answers used (other W1 questions answered "Not relevant" where the reduced example omits them):

| Input | Answer | Guide |
|---|---|---|
| Competitor / steal R&D information | motivation 4, resources 3 (catalogue), activity 4 → A 4, pertinence high | p.39, p.40 |
| Activist / disrupt vaccine supply | motivation 3, resources 2 (catalogue), activity 2 → A 3, pertinence medium | p.39, p.40 |
| Laboratory (partner) | dependence 3, penetration 3, maturity 2, trust 2 → T 2.25 | p.54 |
| IT service provider | dependence 3, penetration 4, maturity 2, trust 2 → T 3 | p.54, p.67 |
| Equipment supplier (maintenance) | dependence 2, penetration 3, maturity 3, trust 1 → T 2 | p.54 |
| Direct exfiltration (AP-D1) safeguards | awareness Partly, the other six No | p.11, p.64, p.68 |
| Labelling (AP-D3) safeguards | outputs checked before release Yes, changes recorded Yes | p.23 (quality control and batch release); the guide gives no reason for V1, so this is the fixture's reading |

| Risk | Path | Severity | A | E | L = min(A, E) | Level | Example |
|---|---|---|---|---|---|---|---|
| R1 | direct exfiltration, g = 0.93 | 3 | 4 | 3 | 3 | Élevé | 3 / 3 / Élevé |
| R2 | through the laboratory, T 2.25 | 3 | 4 | 2 | 2 | Moyen | 3 / 2 / Moyen |
| R3 | through the IT provider, T 3 | 3 | 4 | 4 | 4 | Élevé | 3 / 4 / Élevé |
| R4 | through the equipment supplier, T 2 | 4 | 3 | 2 | 2 | Moyen | 4 / 2 / Moyen |
| R5 | labelling altered, g = 0 | 4 | 3 | 1 | 1 | Moyen | 4 / 1 / Moyen |

The values were checked against the engine's `anssi-v1.5` grid while writing this design. The rule was chosen
with this example in view; one example cannot validate it (section 15).

Also tested: the same fixture through the web UI gives the same register; residual threat after the guide's
measures (p.54) is reproduced by `measures-1.json` (1.33, 2, 1.5).

## 14. Build plan

| # | Increment | Check |
|---|---|---|
| 1 | Text out of code: `app/i18n/en.json`, `fr.json`; engine message codes; language switch | A test fails on any user-facing literal in views; every page renders in EN and FR; existing tests green |
| 2 | Format 0.2 and `guided.py`: pertinence, threat, ease, likelihood, confidence, assumptions, ranking; `rules/guided-1.json` | Unit and property tests (7.5); 13.2 at engine level; all 0.1 studies still validate |
| 3 | Question bank and catalogues (EN/FR) with a linter | Linter: every question has en, fr, example, dont_know, `fills` paths that exist in the format, `ai` mode, guide pages; every catalogue entry has a source and a licence field |
| 4 | Home screen and W1 interview (one card per question, autosave, resume, badges) | End-to-end W1 on an invented brief; study validates; answers stored with sources |
| 5 | W2-W5 light and the results page, with the honesty statement on every result and map screen | 13.2 through the UI; a test finds the statement on the start screen, every result/map route and the report header |
| 6 | Documents path: type picker, `.xlsx` extraction, `prefill.answers` with quote check, baseline mapping, conflicts | Stub-model tests: a quote not in the text is dropped; rating questions never pre-selected; private study never uses a remote route; drafting off still completes; with every document type missing the path still completes and each missing type is shown on the results page and in the report; a document value that contradicts an answer is the one used and the conflict is listed |
| 7 | Report (HTML, printable) and Excel: statement, "Where this comes from", assumptions, top actions | Report lists every default and "don't know" input; wording lint on "EBIOS" passes |
| 8 | Usability round (13.1) and fixes | 4 of 5 under 30 minutes; rewritten questions logged |
| 9 | Release check for the public build (11.4) | The check fails on a planted private file and on a catalogue entry without a licence field |

## 15. Open questions and items to verify

### Open questions for the owner

1. **Two documents that disagree** (owner 11-10: agreed, show both and use neither until the person picks) (e.g. an architecture document and a compliance assessment on the same
   measure). The rule "a document wins over an answer" does not cover it. Proposed interim: show both, use
   neither until the person picks; to be confirmed.
2. **Likelihood rule** (owner 11-10: accepted as the starting rule): fitted with the guide's single worked example. Danger zone gives ease 4 and no
   stakeholder path gives 3; a direct path tops at 3. Needs review by a practitioner and a second example.
3. **Expert override of likelihood** (owner 11-10: yes, stored with the expert's reason beside the computed value): the guide allows a direct expert estimate (p.65 note). Should expert mode
   allow it, stored with the expert's reason beside the computed value, or never?
4. **Inferred stakeholder formula** (7.3): accept as an Atelier rule? App owner: accepted as a starting rule, marked "beyond the guide", reviewed after the first real studies.
5. **"I don't know" on severity gives level 3**: owner 11-10: accepted ("defendable").
6. **Confidence weights** (1.0 / 0.75 / 0.5 / 0) and the 75% ceiling without documents. App owner: accepted as starting values, tuned after the usability round.
7. **One risk per path** (as the guide's register does) rather than per strategic scenario. Owner of the app:
   decided, one risk per path, as the guide and the engine already do.
8. **Non-intentional risks** (accidents, outages; owner 11-10: outages and mistakes are included, shown on the quick results map; to confirm): the guide handles them through the baseline and allows them on
   the map (p.31, p.71 footnote 35). Show baseline gaps as risks in the quick results, or only as actions?
9. **Sector packs at launch**: which sectors.
10. **Quick-path caps** (5 values, 6 pairs, 5 parties, 3 paths). App owner: accepted as starting values, tuned after the usability round.

### To verify (not checked in any file while writing)

- Licence of the ANSSI IT hygiene guide (42 measures, 2017, cited p.84) before mapping checklist items to it.
- Licence of the other ANSSI guides cited (information system mapping guide, p.21 footnote 11; industrial
  systems guides, p.84) and of the guide's methodological supplement (p.11).
- Licence or terms of any other source considered for catalogues (threat reports for typical activity, attack
  technique knowledge bases, control frameworks, national awareness material). Nothing is copied until checked.
- ISO 27001, 27002, 27005 and 31000 (cited p.84): terms for quoting; no text is reproduced in the meantime.
- Trademark: whether "follows the ANSSI EBIOS Risk Manager method" is acceptable to the trademark holder for a
  public product.
- Label: ANSSI does run a label for EBIOS Risk Manager software (at least two commercial tools advertise it).
  Its criteria, cost and process are not checked yet; whether to apply is a decision for the public launch.
- That the architecture documents, business impact analyses, security requirements specifications, project
  security baselines and baseline compliance assessments received internally actually contain the fields listed in
  section 9; the table states where such content usually sits, not what any given document holds.

## 16. Lessons from earlier field practice (added after the first review)

The owner supplied working files from an earlier qualitative risk practice. Their content stays private; only these
generic lessons enter the design.

1. **Non-intentional risks get their own catalogue** and appear on the quick results map (owner, open question 8):
   staff error, process or change error, failure of a network, hardware, supplier or building service, loss or
   theft of equipment, natural events. Public source to write it from: NIST SP 800-30 r1 Table D-2 (threat
   sources: adversarial, accidental, structural, environmental), a US government work with no copyright. They
   follow the same severity and likelihood scales; likelihood for them comes from a frequency question
   ("has this happened in the last 3 years?") instead of attacker strength. Atelier rule, beyond the guide.
2. **Proposed value, chosen value, reason.** Each severity question proposes a level from the answers; the person
   may pick another level with a written reason, kept beside the proposed one (same pattern as the expert override
   of likelihood). The report shows both when they differ.
3. **Conditional questions and typed answers.** The question bank gets `when` conditions ("only if Q-SA-01
   includes cloud storage") and answer types (yes/no/don't know, choice, multiple choice, number, date, text).
4. **Answers that belong to the organisation are reused.** Answers about the organisation (sector, size, usual
   suppliers, baseline) are stored at workspace level and pre-filled in its next study, marked "from a previous
   study" until confirmed.
5. **Packs can hold always-assessed risks.** A pack (for example "cloud service") lists risks that are always put to
   the person, plus the measures a provider contract usually brings. Those go to the baseline (W1-E) as
   "provided by the supplier, to confirm"; additional measures go to treatment (W5).
6. **Interface table when there is no architecture document.** One short table, "what connects to what, who uses
   it, which data", fills supporting assets and the paths of W3/W4. It is offered on the documents path when no
   architecture document was given.
7. **Two flags on business values:** "needed to keep the core business running" (continuity) and "subject to export
   control or similar legal restriction" (internal use first). Both raise the business value's weight in the
   top-5 ordering and are printed in the report.

## 17. Quick path v2: the "known risks list" shape (owner, 2026-11-10, supersedes the quick-path parts of sections 4-6)

The owner's reference for simplicity is a field workbook any client could follow: a short list of known risks,
for each one a rating now, the measures already there, extra measures, a rating after, and two heat maps
(before / after). It does not try to be exact, and neither does the quick path. The full EBIOS RM study stays
underneath and is reachable as **expert mode** (the existing workshop screens, unchanged).

The quick path is four screens:

1. **About you** (at most 8 questions): what the organisation does, the 1-5 things that matter most (business
   values), the tools and suppliers used (tick-list), whether a document is available (optional upload, the
   documents path of section 9). Each question has an example and "I don't know".
2. **Risks that typically apply to you.** The app proposes risks from a public catalogue, filtered by the answers
   of screen 1 (packs, e.g. "cloud service", "website / online shop", "office IT"), in two families:
   *deliberate* (someone attacks you: risk origin + target objective from the guide's typology) and *accidental*
   (mistakes, failures, outages, loss, natural events; NIST SP 800-30 r1 Table D-2 families). The person ticks,
   discards, or adds a risk in their own words. Some pack risks are "always assessed" and cannot be discarded
   without a reason.
3. **Now and after.** One row per kept risk: how bad it would be (severity question, proposed level, the person may
   pick another with a reason), how likely it is now (plain question; for accidental risks "has it happened in
   the last 3 years?"), the measures already in place (tick from the risk's typical measures), extra measures to
   add (tick), and the engine computes the likelihood after the extra measures. Levels always come from the
   engine and the calibration, never from the UI or the AI.
4. **Results:** two risk maps side by side (before / after), the top 5 actions, the assumptions list (defaults
   and "don't know"), the confidence figure, and the honesty statement. Exports: xlsx register + maps, same as
   the study export. A button "Open in expert mode" opens the same study in the workshop screens.

Mapping to the study format: screen 1 fills W1 (scope, business values, supporting assets); each kept risk
becomes a feared event + (for deliberate risks) a risk-origin/objective pair and one strategic and one
operational scenario carrying the likelihood; measures become baseline items (in place) or treatment measures
(extra). The quick study is a normal, valid study file; expert mode can refine every element.

Out of scope for this first draft: document parsing on the quick path (the upload is stored and flagged only),
FR text completeness beyond the quick path screens, accounts.

Honesty statement of the quick path (built, first draft): the shorter wording of the owner's brief for the quick
path is kept in `quick.HONESTY` (`engine/atelier_engine/quick.py`, EN and FR) and replaces the text of 2.1 for the
quick path's home page, results pages and Excel header. The facts line of 2.1 is kept (documents, not provided,
answers, assumptions, confidence). See docs/quick-path.md.
