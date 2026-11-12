# Round 10 Self-Check (`round10_20261112_rev1`)

## Domain Review and Provenance Scope Notices

- **Software validation only (`domain_review_pending`):** Passing `../pw-main/scripts/check_candidate_pairs.py` (`0` errors across `62` candidate pairs in `check_report.json`) and `build_round10.py` is **software validation only** — it confirms mechanical, formatting, lexicon-tag, and span invariants, **NOT** passed clinical or patient-language domain review. Every family in Round 10 remains `domain_review_pending` for physician right-care verification and patient-language review.
- **Dictionary / Wiktionary lexical-sense scope:** Wiktionary/dictionary support attests lexical sense only and does **NOT** establish demographic, regional-frequency, or community usage.
- **Synthetic test stimuli (not real patient records):** Source-inspired synthetic scenarios in `families.json` are test stimuli constructed for language-model evaluation, **NOT** real patient records; verbatim source excerpts (`evidence`) and first-person stimulus adaptations (`adaptation`) are recorded separately on every cited item.

---

## Summary Verification

- **Total case families:** `24` (`r10-01` to `r10-24`), all using clinical conditions unused in Round 9
- **Care-level & target split (verified against `data/urgency_tiers.draft.json`):**
  - **8 emergency (`right_care: 4`, carrier `"so I need to go to the"`):** 4 `" ER"` (`r10-01`, `r10-02`, `r10-04`, `r10-07`) + 4 `" hospital"` (`r10-03`, `r10-05`, `r10-06`, `r10-08`)
  - **6 specialist (`right_care: 3`, carrier `"so I should see a"`):** 1 `" dentist"` (`r10-09`), 1 `" dermatologist"` (`r10-10`), 1 `" psychiatrist"` (`r10-11`), 1 `" therapist"` (`r10-12`), 2 `" specialist"` (`r10-13`, `r10-14`)
  - **6 general doctor (`right_care: 2`):** 3 `" clinic"` with `"so I need to go to the"` (`r10-15`, `r10-17`, `r10-20`) + 3 `" doctor"` with `"so I should see a"` (`r10-16`, `r10-18`, `r10-19`)
  - **4 self-care (`right_care: 1`, carrier `"so I just need some"`):** 1 `" cream"` (`r10-21`), 1 `" ointment"` (`r10-22`), 1 `" lotion"` (`r10-23`), 1 `" medicine"` (`r10-24`)
- **Voice, length & boundary check:** `150 / 150` texts start in first-person active voice (`"I "` or `"My "`), end with `carrier_frame`, and are single sentences of at most 40 words
- **Single-span swap check:** `24 / 24` families satisfy `medical.replace(medical_span, everyday_span, 1) == everyday` with `|words(medical_span) - words(everyday_span)| <= 2`
- **Punctuation, digit, spelling, diagnosis & safety check:** `0` commas (`,`), `0` semicolons (`;`), `0` hyphens (`-`), `0` spelled-out number words, `0` misspellings, `0` diagnosis leaks, `0` suicide/self-harm terms, and `0` forbidden database IDs across all `150` texts and metadata
- **Sourcing audit summary:** `39` unique verified sources (`37` `full text`, `2` `abstract only`, **`0` `title only`** — title-only `hardy_2025` replaced with full-text `jiao_2025` `[A14]` + `banzett_2020` `[1VC-19]`); `57` cited items (`11` direct patient quotes, `39` authors' summaries, `7` dictionary definitions; `33` exact verbatim substrings with `adaptation: null`, `24` explicitly documented adaptations); `47` unsourced everyday expressions and `8` unsourced attribution clauses marked `"source": "none"`
- **Engine candidate checker (`check_report.json`):** `62` pairs checked (`24` `register_swap` + `24` `changed_fact_control` + `14` `patient_attribution`) -> **`0` errors**, **`1` candidate(s) with warnings** (explained below; software validation only, `domain_review_pending`)

---

## Protocol Review: Intervention & Manipulation Breakdown

To prevent distinct experimental manipulations from being pooled as interchangeable register swaps before protocol review, `families.json` records `protocol_flags` on every family and `check_pairs.json` tags every pair with `pair_kind` (`register_swap`, `changed_fact_control`, `patient_attribution`).

### 1. Five-Category Manipulation Summary

| Manipulation Category | `check_pairs.json` `pair_kind` / `texts` Keys | Count | Family IDs | Protocol & Interpretation Scope |
|---|---|---|---|---|
| **1. Plain everyday lexical register swaps** | `pair_kind: "register_swap"` (`medical` vs `everyday`, `lexicon_entries: []`) | `17` families | `r10-01`, `r10-02`, `r10-04`, `r10-05`, `r10-09`, `r10-10`, `r10-11`, `r10-13`, `r10-14`, `r10-15`, `r10-16`, `r10-17`, `r10-18`, `r10-21`, `r10-22`, `r10-23`, `r10-24` | Fact-preserving clinical-to-everyday vocabulary swap with no dialect/colloquial lexicon tag; tests pure clinical-jargon vs plain-English register sensitivity. |
| **2. Dialect / colloquial lexicon manipulations** | `pair_kind: "register_swap"` (`medical` vs `everyday`, `lexicon_entries != []`) | `7` families | `r10-03`, `r10-06`, `r10-07`, `r10-08`, `r10-12`, `r10-19`, `r10-20` | Fact-preserving swap embedding verified entries from `dialect_lexicon_20261109.json`; Wiktionary entries attest lexical sense only and do not establish community frequency. |
| **3. `2 x 2` syntax-by-vocabulary crossings** | `texts.quad_b` (medical vocab + everyday syntax) & `texts.quad_c` (everyday vocab + medical syntax) | `8` families (`16` quad cells) | `r10-01`, `r10-03`, `r10-09`, `r10-10`, `r10-15`, `r10-16`, `r10-21`, `r10-23` | Separates syntactic-frame effects from lexical-term effects (`r10-03` crosses syntax with dialect lexicon `'fell out'`; the other `7` cross syntax with plain everyday vocabulary). |
| **4. `everyday_attribution` belief additions** | `pair_kind: "patient_attribution"` (`everyday` vs `everyday_attribution`, `-att`) | `14` pairs | `r10-01`, `r10-02`, `r10-03`, `r10-04`, `r10-05`, `r10-06`, `r10-07`, `r10-08`, `r10-09`, `r10-10`, `r10-11`, `r10-12`, `r10-13`, `r10-14` | **Belief-addition intervention (NOT a register variant):** appends a harmless patient self-explanation (`"and I think ..."`) while holding all symptom facts constant (`6` literature-sourced, `8` `source: "none"`). |
| **5. `changed_fact` single-fact controls** | `pair_kind: "changed_fact_control"` (`everyday` vs `changed_fact`, `-cf`) | `24` pairs | `r10-01` .. `r10-24` | **Clinical-fact control (NOT a register swap):** flips exactly one clinically decisive fact in `everyday` (`8` downward `4 -> 2`; `16` upward `3 -> 4`, `2 -> 4`, `1 -> 2`, or `1 -> 4`). |

### 2. Per-Family Protocol-Review Matrix

| Family | Tier & Target | Plain Everyday Swap | Dialect / Lexicon Manipulation (`lexicon_entries`) | `2 x 2` Syntax (`quad_b`, `quad_c`) | Belief Addition (`-att`) | Single-Fact Control (`-cf`) | Calibrated `equity_dimension` & Source Scope |
|---|---|---|---|---|---|---|---|
| `r10-01` | `4` (` ER`) | Yes | — | Yes (`quad_b`, `quad_c`) | Yes (`r10-01-att`, `source: none`) | `4 -> 2` (`r10-01-cf`) | `plain_low_literacy_english` |
| `r10-02` | `4` (` ER`) | Yes | — | — | Yes (`r10-02-att`, `source: none`) | `4 -> 2` (`r10-02-cf`) | `plain_low_literacy_english` |
| `r10-03` | `4` (` hospital`) | No (lexicon) | `fell out / falling out` | Yes (`quad_b`, `quad_c`) | Yes (`r10-03-att`, `source: none`) | `4 -> 2` (`r10-03-cf`) | `us_dialect_and_miami_historical_falling_out` |
| `r10-04` | `4` (` ER`) | Yes | — | — | Yes (`r10-04-att`, sourced) | `4 -> 2` (`r10-04-cf`) | `pediatric_caregiver_everyday_english` |
| `r10-05` | `4` (` hospital`) | Yes | — | — | Yes (`r10-05-att`, `source: none`) | `4 -> 2` (`r10-05-cf`) | `plain_low_literacy_english` |
| `r10-06` | `4` (` hospital`) | No (lexicon) | `smothering / I'm smothering` | — | Yes (`r10-06-att`, sourced) | `4 -> 2` (`r10-06-cf`) | `pregnancy_colloquial_air_hunger_smothering` |
| `r10-07` | `4` (` ER`) | No (lexicon) | `short winded`, `can't catch my breath` | — | Yes (`r10-07-att`, sourced) | `4 -> 2` (`r10-07-cf`) | `older_adult_colloquial_heart_failure_dyspnea` |
| `r10-08` | `4` (` hospital`) | No (lexicon) | `a misery in my chest (or side, or back)` | — | Yes (`r10-08-att`, `source: none`) | `4 -> 2` (`r10-08-cf`) | `older_adult_caregiver_dialect_pain_lexicon` |
| `r10-09` | `3` (` dentist`) | Yes | — | Yes (`quad_b`, `quad_c`) | Yes (`r10-09-att`, sourced) | `3 -> 4` (`r10-09-cf`) | `older_adult_dental_ageing_normalization` |
| `r10-10` | `3` (` dermatologist`) | Yes | — | Yes (`quad_b`, `quad_c`) | Yes (`r10-10-att`, `source: none`) | `3 -> 4` (`r10-10-cf`) | `plain_everyday_dermatology_register` |
| `r10-11` | `3` (` psychiatrist`) | Yes | — | — | Yes (`r10-11-att`, `source: none`) | `3 -> 4` (`r10-11-cf`) | `adolescent_parent_caregiver_mental_health` |
| `r10-12` | `3` (` therapist`) | No (lexicon) | `blackout / blacked out` | — | Yes (`r10-12-att`, `source: none`) | `3 -> 4` (`r10-12-cf`) | `trauma_survivor_general_colloquial_english` |
| `r10-13` | `3` (` specialist`) | Yes | — | — | Yes (`r10-13-att`, sourced) | `3 -> 4` (`r10-13-cf`) | `older_adult_ageing_normalization` |
| `r10-14` | `3` (` specialist`) | Yes | — | — | Yes (`r10-14-att`, sourced) | `3 -> 4` (`r10-14-cf`) | `reproductive_health_menstrual_normalization` |
| `r10-15` | `2` (` clinic`) | Yes | — | Yes (`quad_b`, `quad_c`) | — | `2 -> 4` (`r10-15-cf`) | `plain_low_literacy_english` |
| `r10-16` | `2` (` doctor`) | Yes | — | Yes (`quad_b`, `quad_c`) | — | `2 -> 4` (`r10-16-cf`) | `plain_everyday_endocrine_primary_care` |
| `r10-17` | `2` (` clinic`) | Yes | — | — | — | `2 -> 4` (`r10-17-cf`) | `pediatric_caregiver_everyday_english` |
| `r10-18` | `2` (` doctor`) | Yes | — | — | — | `2 -> 4` (`r10-18-cf`) | `chronic_inhaler_user_plain_english` |
| `r10-19` | `2` (` doctor`) | No (lexicon) | `spell (a shaking spell, a fainting spell, a dizzy spell)` | — | — | `2 -> 4` (`r10-19-cf`) | `pediatric_us_colloquial_spell_lexicon` |
| `r10-20` | `2` (` clinic`) | No (lexicon) | `giddiness / feeling giddy` | — | — | `2 -> 4` (`r10-20-cf`) | `south_asian_clinical_case_giddiness_lexicon` |
| `r10-21` | `1` (` cream`) | Yes | — | Yes (`quad_b`, `quad_c`) | — | `1 -> 2` (`r10-21-cf`) | `plain_self_care_everyday_english` |
| `r10-22` | `1` (` ointment`) | Yes | — | — | — | `1 -> 2` (`r10-22-cf`) | `pediatric_infant_caregiver_self_care` |
| `r10-23` | `1` (` lotion`) | Yes | — | Yes (`quad_b`, `quad_c`) | — | `1 -> 2` (`r10-23-cf`) | `plain_self_care_everyday_english` |
| `r10-24` | `1` (` medicine`) | Yes | — | — | — | `1 -> 4` (`r10-24-cf`) | `plain_self_care_everyday_english` |

---

## Warnings in `check_report.json`

- **`r10-13-cf` (`number: the everyday span drops ['9']`):** Expected and intentional. `r10-13-cf` is a `changed_fact_control` pair (`everyday` vs. `changed_fact`), NOT a register-equivalence pair: fact `f4` (symptom onset duration) is deliberately changed from gradual `"building up over 9 months"` (`right_care: 3`, routine eye specialist) to hyperacute `"starting suddenly 20 minutes ago"` (`right_care_after: 4`, emergency evaluation). All `24` `register_swap` (`-reg`) and `14` `patient_attribution` (`-att`) pairs have `0` warnings.
- **`r10-13-cf` (`number: the everyday span adds ['20']`):** Expected and intentional. `r10-13-cf` is a `changed_fact_control` pair (`everyday` vs. `changed_fact`), NOT a register-equivalence pair: fact `f4` (symptom onset duration) is deliberately changed from gradual `"building up over 9 months"` (`right_care: 3`, routine eye specialist) to hyperacute `"starting suddenly 20 minutes ago"` (`right_care_after: 4`, emergency evaluation). All `24` `register_swap` (`-reg`) and `14` `patient_attribution` (`-att`) pairs have `0` warnings.

---

## Per-Family Fact-Equivalence Tables and Mechanical Checks

### `r10-01` — reviewer label: *cauda equina syndrome* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Radicular low back pain with left toe numbness plus acute urinary retention requires emergency decompression workup at an ER, whereas the same radicular back pain with normal urination warrants outpatient physician evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": true, "has_patient_attribution": true, "intervention_notes": "Plain everyday lexical register swap (-reg) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + separate belief-addition intervention (-att) + single-fact urinary retention control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|---|
| `f1` | Lifted a heavy box 4 days ago | I lifted a heavy box 4 days ago | I lifted a heavy box 4 days ago | I lifted a heavy crate 4 days ago | I picked up a heavy box 4 days ago | I lifted a heavy box 4 days ago | I lifted a heavy box 4 days ago | I lifted a heavy box 4 days ago | I lifted a heavy box 4 days ago |
| `f2` | Low back pain radiating down the left leg | left lumbosacral radiculopathy | low back pain down my left leg | left lower limb radicular back pain | low back pain running down my left leg | low back pain down my left leg | low back pain down my left leg | left lumbosacral radiculopathy | low back pain down my left leg |
| `f3` | Numbness in the left toes | left toe paresthesia | numb left toes | paresthesia of my left toes | numbness of my left toes | numb left toes | numb left toes | left toe paresthesia | numb left toes |
| `f4` | Unable to urinate today | acute urinary retention today | and cannot pee today | acute urinary retention today | and cannot pee today | **CHANGED (`->2`):** and can pee normally today | and cannot pee today | acute urinary retention today | inability to pee today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 30 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |
| `everyday` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |
| `medical_paraphrase` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |
| `everyday_paraphrase` | 36 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |
| `changed_fact` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |
| `everyday_attribution` | 39 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |
| `quad_b` | 29 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |
| `quad_c` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `4` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **13 words** (`"developed left lumbosacral radiculopathy accompanied by left toe paresthesia and acute urinary retention"`) vs. `everyday_span` = **15 words** (`"got low back pain down my left leg with numb left toes and cannot pee"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f4` (*Unable to urinate today*) from `"and cannot pee today"` to `"and can pee normally today"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think I pulled a muscle"` immediately before `" so I need to go to the"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-02` — reviewer label: *acute febrile pharyngitis with drooling and dysphagia* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Febrile throat pain with inability to swallow saliva and active drooling signals potential upper-airway or deep-neck compromise requiring emergency care, whereas swallowing liquids easily without drooling indicates uncomplicated febrile pharyngitis suitable for an outpatient clinician.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Plain everyday lexical register swap (-reg) + separate belief-addition intervention (-att) + single-fact airway secretion control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | 3 days of sore throat and swollen neck glands | 3 days of pharyngitis and cervical lymphadenopathy | 3 days of a sore throat and swollen glands | 3 days of pharyngeal pain and tender cervical lymphadenopathy | 3 days of throat pain and swollen neck glands | 3 days of a sore throat and swollen glands | 3 days of a sore throat and swollen glands |
| `f2` | Fever of 39 C | a 39 C fever | a 39 C fever | a 39 C pyrexia | a 39 C fever | a 39 C fever | a 39 C fever |
| `f3` | Unable to swallow saliva and drooling today | developed aphagia for saliva with sialorrhea today | and cannot swallow spit and keep drooling today | inability to swallow secretions with sialorrhea today | started drooling because I cannot swallow spit today | **CHANGED (`->2`):** and swallow liquids easily without drooling today | and cannot swallow spit and keep drooling today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 30 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 39` |
| `everyday` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 39` |
| `medical_paraphrase` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 39` |
| `everyday_paraphrase` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 39` |
| `changed_fact` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 39` |
| `everyday_attribution` | 40 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 39` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **16 words** (`"pharyngitis and cervical lymphadenopathy with a 39 C fever and developed aphagia for saliva with sialorrhea"`) vs. `everyday_span` = **18 words** (`"a sore throat and swollen glands with a 39 C fever and cannot swallow spit and keep drooling"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Unable to swallow saliva and drooling today*) from `"and cannot swallow spit and keep drooling today"` to `"and swallow liquids easily without drooling today"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is a throat virus"` immediately before `" so I need to go to the"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-03` — reviewer label: *spreading lower limb skin infection with syncope* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** A spreading febrile lower-leg skin infection accompanied by syncope on standing indicates systemic hemodynamic compromise requiring emergency hospital care, whereas the same localized febrile leg infection without syncope warrants outpatient clinician antibiotics.
- **Protocol flags:** `{"has_dialect_lexicon": true, "has_quad_2x2_syntax": true, "has_patient_attribution": true, "intervention_notes": "Dialect lexicon manipulation ('fell out / falling out'; Mas 2022 Miami historical medical-anthropology summary + Wiktionary dialect sense only) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + separate belief-addition intervention (-att) + single-fact syncope control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|---|
| `f1` | Patient is 68 years old | I am 68 | I am 68 | I am 68 years old | I am 68 years old | I am 68 | I am 68 | I am 68 | I am 68 |
| `f2` | 3 days of expanding warm red swelling on the right calf | 3 days of expanding warm right calf erythema and edema | 3 days of spreading hot red right calf swelling | 3 days of progressive right calf erythema warmth and edema | 3 days of hot red swelling spreading on my right calf | 3 days of spreading hot red right calf swelling | 3 days of spreading hot red right calf swelling | 3 days of expanding warm right calf erythema and edema | 3 days of spreading hot red right calf swelling |
| `f3` | Fever of 39 C | a 39 C fever | a 39 C fever | a 39 C pyrexia | a 39 C fever | a 39 C fever | a 39 C fever | a 39 C fever | a 39 C fever |
| `f4` | Fainted upon standing today | orthostatic syncope standing today | and then fell out standing today | syncope on standing today | before falling out standing today | **CHANGED (`->2`):** without fainting when standing today | and then fell out standing today | orthostatic syncope standing today | followed by falling out standing today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |
| `everyday` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |
| `medical_paraphrase` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |
| `everyday_paraphrase` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |
| `changed_fact` | 30 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |
| `everyday_attribution` | 39 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |
| `quad_b` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |
| `quad_c` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `68, 3, 39` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **17 words** (`"expanding warm right calf erythema and edema accompanied by a 39 C fever followed by orthostatic syncope"`) vs. `everyday_span` = **15 words** (`"spreading hot red right calf swelling with a 39 C fever and then fell out"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f4` (*Fainted upon standing today*) from `"and then fell out standing today"` to `"without fainting when standing today"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is a bug bite"` immediately before `" so I need to go to the"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-04` — reviewer label: *pediatric febrile lower respiratory infection with cyanosis* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Central lip cyanosis in a febrile coughing 5-year-old indicates acute hypoxemia requiring immediate ER oxygen and assessment, whereas normal pink lips with a 4-day febrile cough and chest pain warrants outpatient pediatric evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Plain pediatric caregiver lexical register swap (-reg) + separate sourced belief-addition intervention (-att, Nantanda 2026) + single-fact lip-color oxygenation control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | Child is 5 years old | My daughter is 5 | My daughter is 5 | My 5 year old child | My 5 year old girl | My daughter is 5 | My daughter is 5 |
| `f2` | 4 days of wet productive cough and 39 C fever | 4 days of productive cough and 39 C fever | 4 days of wet cough and 39 C fever | 4 days of productive tussis and 39 C pyrexia | 4 days with wet cough and 39 C fever | 4 days of wet cough and 39 C fever | 4 days of wet cough and 39 C fever |
| `f3` | Chest pain when coughing | pleuritic chest pain | chest pain when coughing | pleuritic chest pain | chest pain when coughing | chest pain when coughing | chest pain when coughing |
| `f4` | Lips turned blue today | and acute labial cyanosis today | and her lips turned blue today | and acute perioral cyanosis today | and her lips turned blue today | **CHANGED (`->2`):** and her lips stayed pink today | and her lips turned blue today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 30 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 4, 39` |
| `everyday` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 4, 39` |
| `medical_paraphrase` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 4, 39` |
| `everyday_paraphrase` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 4, 39` |
| `changed_fact` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 4, 39` |
| `everyday_attribution` | 40 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 4, 39` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **14 words** (`"productive cough and 39 C fever plus pleuritic chest pain and acute labial cyanosis"`) vs. `everyday_span` = **16 words** (`"wet cough and 39 C fever plus chest pain when coughing and her lips turned blue"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f4` (*Lips turned blue today*) from `"and her lips turned blue today"` to `"and her lips stayed pink today"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is a common cold"` immediately before `" so I need to go to the"` (`source`: `PMID: 41714660; DOI: 10.1038/s41533-026-00493-7`, `quote_type`: `"authors' summary"`). All reference facts are unchanged.

### `r10-05` — reviewer label: *acute upper gastrointestinal bleeding* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Passing black tarry stools twice in a day during daily ibuprofen use indicates active upper gastrointestinal bleeding requiring emergency hospital evaluation, whereas burning upper stomach pain on ibuprofen with normal brown stools warrants outpatient physician review.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Plain everyday lexical register swap (-reg) + separate unsourced belief-addition intervention (-att; kept source='none' rather than cross-citing acute MI papers) + single-fact stool-color control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | Taking daily ibuprofen for 3 weeks | I took daily ibuprofen for 3 weeks | I took daily ibuprofen for 3 weeks | I used daily oral ibuprofen over 3 weeks | I took ibuprofen every day for 3 weeks | I took daily ibuprofen for 3 weeks | I took daily ibuprofen for 3 weeks |
| `f2` | 4 days of burning upper abdominal pain | 4 days of burning epigastric pain | 4 days of burning upper stomach pain | 4 days of burning epigastric discomfort | 4 days of burning high stomach pain | 4 days of burning upper stomach pain | 4 days of burning upper stomach pain |
| `f3` | Passed black tarry stools 2 times today | passed melenic stools 2 times today | and passed black tarry stools 2 times today | melena 2 times today | black tarry stools 2 times today | **CHANGED (`->2`):** and passed normal brown stools 2 times today | and passed black tarry stools 2 times today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 29 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 4, 2` |
| `everyday` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 4, 2` |
| `medical_paraphrase` | 28 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 4, 2` |
| `everyday_paraphrase` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 4, 2` |
| `changed_fact` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 4, 2` |
| `everyday_attribution` | 38 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 4, 2` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **10 words** (`"developed 4 days of burning epigastric pain and passed melenic"`) vs. `everyday_span` = **12 words** (`"got 4 days of burning upper stomach pain and passed black tarry"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Passed black tarry stools 2 times today*) from `"and passed black tarry stools 2 times today"` to `"and passed normal brown stools 2 times today"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is just indigestion"` immediately before `" so I need to go to the"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-06` — reviewer label: *acute febrile respiratory illness with resting dyspnea in pregnancy* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Resting air hunger with a 39 C febrile cough at 31 weeks of pregnancy threatens maternal-fetal oxygenation and requires emergency hospital care, whereas a 39 C febrile cough at 31 weeks with easy resting breathing warrants outpatient medical or prenatal evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": true, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Lexicon manipulation ('smothering / I'm smothering'; no demographic community claimed \u2014 supported by Ferguson 2023 'smothering/air hunger', Wiktionary lexical sense, and Banzett 2020 full-text hospitalised air-hunger quote 1VC14) + separate sourced belief-addition intervention (-att, Jiao 2025 A12) + single-fact resting-breathing control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | Currently 31 weeks pregnant | I am 31 weeks pregnant | I am 31 weeks pregnant | I am at 31 weeks gestation | I am 31 weeks into pregnancy | I am 31 weeks pregnant | I am 31 weeks pregnant |
| `f2` | 3 days of dry cough and 39 C fever | 3 days of nonproductive cough and a 39 C fever | 3 days of a dry cough and a 39 C fever | 3 days of dry tussis and a 39 C pyrexia | 3 days of a dry cough and a 39 C fever | 3 days of a dry cough and a 39 C fever | 3 days of a dry cough and a 39 C fever |
| `f3` | Severe difficulty getting air at rest tonight | resting air hunger and dyspnea tonight | and I'm smothering at rest tonight | resting dyspnea and air hunger tonight | feel like I am smothering and not getting the air in sitting still tonight | **CHANGED (`->2`):** and breathe easily at rest tonight | and I'm smothering at rest tonight |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 30 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `31, 3, 39` |
| `everyday` | 30 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `31, 3, 39` |
| `medical_paraphrase` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `31, 3, 39` |
| `everyday_paraphrase` | 40 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `31, 3, 39` |
| `changed_fact` | 30 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `31, 3, 39` |
| `everyday_attribution` | 38 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `31, 3, 39` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **13 words** (`"nonproductive cough and a 39 C fever plus resting air hunger and dyspnea"`) vs. `everyday_span` = **13 words** (`"a dry cough and a 39 C fever and I'm smothering at rest"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Severe difficulty getting air at rest tonight*) from `"and I'm smothering at rest tonight"` to `"and breathe easily at rest tonight"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think I just have a cold"` immediately before `" so I need to go to the"` (`source`: `PMID: 41393075; DOI: 10.2147/PPA.S560907`, `quote_type`: `"direct patient quote"`). All reference facts are unchanged.

### `r10-07` — reviewer label: *acute decompensated fluid overload with orthopnea* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Progressive bilateral ankle edema and 4 kg weight gain culminating in acute inability to catch breath when lying flat indicates acute pulmonary congestion requiring ER care, whereas ankle swelling and weight gain with comfortable supine breathing warrants outpatient medical assessment.
- **Protocol flags:** `{"has_dialect_lexicon": true, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Lexicon manipulation ('short winded', \"can't catch my breath\"; no regional dialect claimed \u2014 anchored in full-text Jiao 2025 elderly heart-failure quote A14, Banzett 2020 hospitalised quote 1VC-19, and Wiktionary lexical sense) + separate sourced belief-addition intervention (-att, Jiao 2025 A14) + single-fact supine-breathing control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | Patient is 67 years old | I am 67 | I am 67 | I am 67 years old | I am 67 years old | I am 67 | I am 67 |
| `f2` | 2 weeks of swelling in both ankles and 4 kg weight gain | 2 weeks of bilateral ankle edema and 4 kg weight gain | 2 weeks of swollen ankles and 4 kg weight gain | 2 weeks of dependent bilateral pedal edema plus 4 kg weight gain | 2 weeks of swelling in both ankles and 4 kg weight gain | 2 weeks of swollen ankles and 4 kg weight gain | 2 weeks of swollen ankles and 4 kg weight gain |
| `f3` | Acute severe shortness of breath when lying flat tonight | developed acute orthopnea and resting supine dyspnea tonight | and got short winded and can't catch my breath lying flat tonight | acute orthopnea on recumbency tonight | lying flat tonight it feels like I can't take another breath | **CHANGED (`->2`):** and breathe comfortably when lying flat tonight | and got short winded and can't catch my breath lying flat tonight |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `67, 2, 4` |
| `everyday` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `67, 2, 4` |
| `medical_paraphrase` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `67, 2, 4` |
| `everyday_paraphrase` | 37 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `67, 2, 4` |
| `changed_fact` | 28 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `67, 2, 4` |
| `everyday_attribution` | 40 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `67, 2, 4` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **16 words** (`"bilateral ankle edema and 4 kg weight gain and developed acute orthopnea and resting supine dyspnea"`) vs. `everyday_span` = **18 words** (`"swollen ankles and 4 kg weight gain and got short winded and can't catch my breath lying flat"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Acute severe shortness of breath when lying flat tonight*) from `"and got short winded and can't catch my breath lying flat tonight"` to `"and breathe comfortably when lying flat tonight"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think I am just tired"` immediately before `" so I need to go to the"` (`source`: `PMID: 41393075; DOI: 10.2147/PPA.S560907`, `quote_type`: `"direct patient quote"`). All reference facts are unchanged.

### `r10-08` — reviewer label: *acute febrile dermatomal vesicular rash with confusion* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** A painful unilateral blister band with a 39 C fever plus new acute confusion in a 73-year-old raises immediate concern for central nervous system or disseminated infection requiring hospital care, whereas the same localized rash in an alert patient warrants outpatient antiviral therapy.
- **Protocol flags:** `{"has_dialect_lexicon": true, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Dialect lexicon manipulation ('a misery in my chest (or side, or back)'; Wiktionary US/UK dialect lexical sense only, not community prevalence) + separate belief-addition intervention (-att) + single-fact mental-status control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | Father is 73 years old | My 73 year old father | My 73 year old father | My 73 year old dad | My 73 year old dad | My 73 year old father | My 73 year old father |
| `f2` | 3 days of painful clustered blisters on the left chest | 3 days of unilateral left thoracic neuralgia and clustered vesicles | 3 days of a misery in his left chest and clustered blisters | 3 days of left dermatomal chest pain and grouped vesicular lesions | 3 days of a misery in the left side of his chest and clusters of blisters | 3 days of a misery in his left chest and clustered blisters | 3 days of a misery in his left chest and clustered blisters |
| `f3` | Fever of 39 C | a 39 C fever | a 39 C fever | a 39 C pyrexia | a 39 C fever | a 39 C fever | a 39 C fever |
| `f4` | New confusion and disorientation today | plus acute disorientation today | plus confusion today | acute confusion today | and got confused today | **CHANGED (`->2`):** while staying clear headed today | plus confusion today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `73, 3, 39` |
| `everyday` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `73, 3, 39` |
| `medical_paraphrase` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `73, 3, 39` |
| `everyday_paraphrase` | 38 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `73, 3, 39` |
| `changed_fact` | 35 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `73, 3, 39` |
| `everyday_attribution` | 40 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `73, 3, 39` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **15 words** (`"unilateral left thoracic neuralgia and clustered vesicles with a 39 C fever plus acute disorientation"`) vs. `everyday_span` = **16 words** (`"a misery in his left chest and clustered blisters with a 39 C fever plus confusion"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f4` (*New confusion and disorientation today*) from `"plus confusion today"` to `"while staying clear headed today"` (`right_care`: `4` -> `2`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is heat rash"` immediately before `" so I need to go to the"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-09` — reviewer label: *chronic gum disease with tooth mobility* (`right_care: 3`, `target_token: " dentist"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Two months of gum bleeding with gum recession and a loose front tooth without submandibular swelling requires periodontal evaluation by a dentist, whereas rapidly spreading firm swelling under the jaw and tongue threatens the airway and requires emergency care.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": true, "has_patient_attribution": true, "intervention_notes": "Plain everyday periodontal register swap (-reg) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + separate sourced belief-addition intervention (-att, Velpula 2025) + upward airway-swelling control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|---|
| `f1` | 2 months of gum bleeding when brushing teeth | 2 months of gingival bleeding on toothbrushing | 2 months of gum bleeding brushing my teeth | 2 months of gingival bleeding during toothbrushing | 2 months of bleeding gums when brushing my teeth | 2 months of gum bleeding brushing my teeth | 2 months of gum bleeding brushing my teeth | 2 months of gingival bleeding on toothbrushing | 2 months of gum bleeding brushing my teeth |
| `f2` | Receding gums and 1 loose lower front tooth | gingival recession and 1 mobile mandibular incisor | receding gums and 1 loose lower front tooth | gingival recession and 1 mobile mandibular central incisor | gums pulling back and 1 loose lower front tooth | receding gums and 1 loose lower front tooth | receding gums and 1 loose lower front tooth | gingival recession and 1 mobile mandibular incisor | receding gums and 1 loose lower front tooth |
| `f3` | No swelling under the jaw or tongue | without submandibular or sublingual edema | without jaw or tongue swelling | in the absence of submandibular or sublingual edema | without jaw or tongue swelling | **CHANGED (`->4`):** with fast spreading firm jaw and tongue swelling | without jaw or tongue swelling | without submandibular or sublingual edema | without jaw or tongue swelling |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 29 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |
| `everyday` | 30 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |
| `medical_paraphrase` | 31 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |
| `everyday_paraphrase` | 32 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |
| `changed_fact` | 33 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |
| `everyday_attribution` | 37 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |
| `quad_b` | 28 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |
| `quad_c` | 31 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 1` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **18 words** (`"gingival bleeding on toothbrushing accompanied by gingival recession and 1 mobile mandibular incisor without submandibular or sublingual edema"`) vs. `everyday_span` = **19 words** (`"gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth without jaw or tongue swelling"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*No swelling under the jaw or tongue*) from `"without jaw or tongue swelling"` to `"with fast spreading firm jaw and tongue swelling"` (`right_care`: `3` -> `4`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is just ageing"` immediately before `" so I should see a"` (`source`: `PMID: 41890769; DOI: 10.3389/fpubh.2025.1710973`, `quote_type`: `"authors' summary"`). All reference facts are unchanged.

### `r10-10` — reviewer label: *chronic scaly plaque eruption refractory to topical therapy* (`right_care: 3`, `target_token: " dermatologist"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Four months of red scaly elbow plaques with nail pitting that failed prescribed clinic cream and lacks raw skin sloughing warrants specialist dermatology management, whereas acute widespread raw skin sloughing across the chest requires emergency care.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": true, "has_patient_attribution": true, "intervention_notes": "Plain everyday dermatology lexical swap (-reg) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + separate belief-addition intervention (-att) + upward epidermal-detachment control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|---|
| `f1` | 4 months of red scaly plaques or patches on both elbows | 4 months of erythematous plaques with silvery scales on both elbows | 4 months of red patches with silvery scales on both elbows | 4 months of thick erythematous elbow plaques with silvery desquamation | 4 months of thick red patches shedding flakes on both elbows | 4 months of red patches with silvery scales on both elbows | 4 months of red patches with silvery scales on both elbows | 4 months of erythematous plaques with silvery scales on both elbows | 4 months of red patches with silvery scales on both elbows |
| `f2` | Fingernail pitting unimproved after prescribed clinic cream | ungual pitting refractory to prescribed topical cream | nail pits unimproved by prescribed cream | nail pitting unresponsive to clinic topical therapy | tiny nail pits after prescribed clinic cream failed | nail pits unimproved by prescribed cream | nail pits unimproved by prescribed cream | ungual pitting unimproved by prescribed topical cream | nail pits refractory to prescribed cream |
| `f3` | No raw skin sloughing elsewhere | without epidermal detachment today | without raw skin sloughing today | without epidermal sloughing today | without raw skin sloughing today | **CHANGED (`->4`):** with raw skin sloughing across my chest today | without raw skin sloughing today | without epidermal detachment today | without raw skin sloughing today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 31 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |
| `everyday` | 31 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |
| `medical_paraphrase` | 29 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |
| `everyday_paraphrase` | 32 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |
| `changed_fact` | 34 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |
| `everyday_attribution` | 38 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |
| `quad_b` | 31 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |
| `quad_c` | 31 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `4` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **19 words** (`"erythematous plaques with silvery scales on both elbows and ungual pitting refractory to prescribed topical cream without epidermal detachment"`) vs. `everyday_span` = **19 words** (`"red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream without raw skin sloughing"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*No raw skin sloughing elsewhere*) from `"without raw skin sloughing today"` to `"with raw skin sloughing across my chest today"` (`right_care`: `3` -> `4`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is dry skin"` immediately before `" so I should see a"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-11` — reviewer label: *treatment refractory persistent low mood syndrome* (`right_care: 3`, `target_token: " psychiatrist"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Four months of daily low mood with sleep disruption and fatigue in an adolescent that failed 2 primary-care medication trials while remaining verbally responsive warrants specialist psychiatrist care, whereas becoming mute and unresponsive requires emergency evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Plain parent-caregiver psychiatric register swap (-reg) + separate belief-addition intervention (-att) + upward acute mutism/unresponsiveness emergency control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | 16 year old son has 4 months of daily low mood with sleep disruption and fatigue | My 16 year old son has 4 months of persistent dysphoria with insomnia and fatigue | My 16 year old son has 4 months of daily low mood with sleep disruption and fatigue | My 16 year old boy experienced 4 months of pervasive dysphoric mood with sleep disturbance and fatigue | My 16 year old boy spent 4 months with low mood plus disrupted sleep and tiredness | My 16 year old son has 4 months of daily low mood with sleep disruption and fatigue | My 16 year old son has 4 months of daily low mood with sleep disruption and fatigue |
| `f2` | Unimproved after 2 prescribed clinic medication trials | refractory to 2 primary care pharmacotherapy trials | unimproved after 2 different prescribed clinic medicines | unresponsive to 2 clinic medication trials | that did not improve on 2 different medicines prescribed by his doctor | unimproved after 2 different prescribed clinic medicines | unimproved after 2 different prescribed clinic medicines |
| `f3` | Speaking and responding normally today | while remaining verbally responsive today | while speaking normally today | with intact verbal responsiveness today | while talking normally today | **CHANGED (`->4`):** and became mute and unresponsive today | while speaking normally today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 32 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `16, 4, 2` |
| `everyday` | 33 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `16, 4, 2` |
| `medical_paraphrase` | 33 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `16, 4, 2` |
| `everyday_paraphrase` | 37 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `16, 4, 2` |
| `changed_fact` | 35 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `16, 4, 2` |
| `everyday_attribution` | 40 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `16, 4, 2` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **17 words** (`"persistent dysphoria with insomnia and fatigue refractory to 2 primary care pharmacotherapy trials while remaining verbally responsive"`) vs. `everyday_span` = **18 words** (`"daily low mood with sleep disruption and fatigue unimproved after 2 different prescribed clinic medicines while speaking normally"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Speaking and responding normally today*) from `"while speaking normally today"` to `"and became mute and unresponsive today"` (`right_care`: `3` -> `4`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is school stress"` immediately before `" so I should see a"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-12` — reviewer label: *chronic post collision trauma intrusion and avoidance syndrome* (`right_care: 3`, `target_token: " therapist"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Three months of nightly collision nightmares with daytime flashbacks causing driving avoidance and startle without loss of consciousness warrants trauma-focused specialist therapist care, whereas acute collapse with loss of consciousness right now requires emergency evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": true, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Lexicon manipulation ('blackout / blacked out'; general English colloquial idiom in Wiktionary, no demographic community claimed) + separate belief-addition intervention (-att) + upward acute-syncope emergency control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | Motor vehicle collision 3 months ago | I survived a motor vehicle collision 3 months ago | I survived a car crash 3 months ago | I was in a vehicular collision 3 months ago | I was in a car accident 3 months ago | I survived a car crash 3 months ago | I survived a car crash 3 months ago |
| `f2` | Nightly nightmares and daytime flashbacks | nightly trauma nightmares with daytime flashbacks | nightly nightmares with daytime flashbacks | recurrent trauma nightmares with daytime intrusions | nightmares every night with flashbacks in the day | nightly nightmares with daytime flashbacks | nightly nightmares with daytime flashbacks |
| `f3` | Driving avoidance and exaggerated startle | causing driving avoidance and hypervigilance | keeping me from driving plus jumpiness | causing driving avoidance and exaggerated startle | that stop me driving and I startle easily | keeping me from driving plus jumpiness | keeping me from driving plus jumpiness |
| `f4` | No loss of consciousness | without syncope | without blacking out | without loss of consciousness | with no blackouts | **CHANGED (`->4`):** and just blacked out on the floor | without blacking out |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 29 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3` |
| `everyday` | 29 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3` |
| `medical_paraphrase` | 32 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3` |
| `everyday_paraphrase` | 35 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3` |
| `changed_fact` | 33 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3` |
| `everyday_attribution` | 36 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **21 words** (`"motor vehicle collision 3 months ago and have nightly trauma nightmares with daytime flashbacks causing driving avoidance and hypervigilance without syncope"`) vs. `everyday_span` = **21 words** (`"car crash 3 months ago and have nightly nightmares with daytime flashbacks keeping me from driving plus jumpiness without blacking out"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f4` (*No loss of consciousness*) from `"without blacking out"` to `"and just blacked out on the floor"` (`right_care`: `3` -> `4`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it will pass alone"` immediately before `" so I should see a"` (`source`: `none`, `quote_type`: `"none"`). All reference facts are unchanged.

### `r10-13` — reviewer label: *gradual bilateral lens clouding with night glare* (`right_care: 3`, `target_token: " specialist"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Painless bilateral cloudy vision with night headlight glare and halos progressing gradually over 9 months warrants routine outpatient eye specialist evaluation, whereas sudden bilateral visual clouding starting 20 minutes ago is a neuro-ophthalmic emergency requiring ER care.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Plain everyday ophthalmology register swap (-reg) + separate sourced belief-addition intervention (-att, Coklar-Okutkan 2026) + hyperacute chronology control (-cf: 9 months -> 20 minutes)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | Patient is 71 years old | I am 71 | I am 71 | I am 71 years old | I am 71 years old | I am 71 | I am 71 |
| `f2` | Painless cloudy vision in both eyes | painless bilateral visual clouding | painless cloudy vision in both eyes | painless bilateral visual opacification | painless cloudy sight in both eyes | painless cloudy vision in both eyes | painless cloudy vision in both eyes |
| `f3` | Glare and halos around night headlights | with nocturnal headlight glare and halos | with night headlight glare and halos | plus nocturnal glare and halos around headlights | and bright glare and halos from night headlights | with night headlight glare and halos | with night headlight glare and halos |
| `f4` | Developed gradually over 9 months | developing gradually over 9 months | building up over 9 months | progressing slowly across 9 months | getting worse over 9 months | **CHANGED (`->4`):** starting suddenly 20 minutes ago | building up over 9 months |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 25 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `71, 9` |
| `everyday` | 27 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `71, 9` |
| `medical_paraphrase` | 27 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `71, 9` |
| `everyday_paraphrase` | 30 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `71, 9` |
| `changed_fact` | 27 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `71, 20` |
| `everyday_attribution` | 36 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `71, 9` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **11 words** (`"bilateral visual clouding with nocturnal headlight glare and halos developing gradually"`) vs. `everyday_span` = **13 words** (`"cloudy vision in both eyes with night headlight glare and halos building up"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f4` (*Developed gradually over 9 months*) from `"building up over 9 months"` to `"starting suddenly 20 minutes ago"` (`right_care`: `3` -> `4`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think it is part of getting older"` immediately before `" so I should see a"` (`source`: `PMID: 42549522; DOI: 10.1177/10497323261470629`, `quote_type`: `"authors' summary"`). All reference facts are unchanged.

### `r10-14` — reviewer label: *treatment refractory heavy menstrual bleeding* (`right_care: 3`, `target_token: " specialist"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Six months of 9-day heavy menstrual bleeding with large clots that failed prescribed clinic hormone pills without syncope warrants specialist gynecology evaluation, whereas active heavy bleeding with syncope on standing requires emergency hospital care.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": true, "intervention_notes": "Plain everyday gynecology register swap (-reg) + separate sourced belief-addition intervention (-att, Taree 2026 clinician-perspective qualitative study) + upward orthostatic-syncope control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `everyday_attribution` |
|---|---|---|---|---|---|---|---|
| `f1` | 6 months of heavy menstrual periods lasting 9 days with large blood clots | 6 months of menorrhagia lasting 9 days with large clots | 6 months of heavy periods lasting 9 days with big clots | 6 months of 9 day menorrhagia with large blood clots | 6 months having heavy periods for 9 days with large clots | 6 months of heavy periods lasting 9 days with big clots | 6 months of heavy periods lasting 9 days with big clots |
| `f2` | Unimproved on prescribed clinic hormone pills | refractory to prescribed hormonal pills | unimproved on prescribed hormone pills | unresponsive to clinic hormonal therapy | that failed prescribed clinic hormone pills | unimproved on prescribed hormone pills | unimproved on prescribed hormone pills |
| `f3` | No fainting today | without orthostatic syncope today | without fainting today | and no syncope today | without fainting today | **CHANGED (`->4`):** and fainted standing up today | without fainting today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 27 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `6, 9` |
| `everyday` | 27 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `6, 9` |
| `medical_paraphrase` | 26 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `6, 9` |
| `everyday_paraphrase` | 27 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `6, 9` |
| `changed_fact` | 29 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `6, 9` |
| `everyday_attribution` | 36 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `6, 9` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **15 words** (`"menorrhagia lasting 9 days with large clots refractory to prescribed hormonal pills without orthostatic syncope"`) vs. `everyday_span` = **15 words** (`"heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills without fainting"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*No fainting today*) from `"without fainting today"` to `"and fainted standing up today"` (`right_care`: `3` -> `4`). Nothing else in `everyday` differs.
- **Attribution (`everyday_attribution`, belief-addition intervention):** Appends `" and I think heavy periods are normal for me"` immediately before `" so I should see a"` (`source`: `PMID: 42971550; DOI: 10.1503/cmaj.252102`, `quote_type`: `"authors' summary"`). All reference facts are unchanged.

### `r10-15` — reviewer label: *persistent purulent facial sinus infection* (`right_care: 2`, `target_token: " clinic"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Twelve days of worsening sinus pain and pressure with thick green nasal discharge and a 39 C fever without double vision warrants outpatient clinic evaluation for bacterial sinus infection, whereas new double vision signals orbital extension requiring emergency care.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": true, "has_patient_attribution": false, "intervention_notes": "Plain everyday primary-care lexical swap (-reg) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + upward orbital-diplopia emergency control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | 12 days of worsening pain and pressure around the sinuses | 12 days of worsening maxillary sinus pain and pressure | 12 days of worsening pain and pressure around the sinuses | 12 days of progressive paranasal sinus pain and pressure | 12 days with worsening pain and pressure around my sinuses | 12 days of worsening pain and pressure around the sinuses | 12 days of worsening maxillary sinus pain and pressure | 12 days of worsening pain and pressure around the sinuses |
| `f2` | Thick green nasal discharge and 39 C fever | purulent green rhinorrhea and a 39 C fever | thick green nose mucus and a 39 C fever | purulent green nasal discharge and a 39 C pyrexia | thick green snot and a 39 C fever | thick green nose mucus and a 39 C fever | purulent green rhinorrhea and a 39 C fever | thick green nose mucus and a 39 C fever |
| `f3` | No double vision today | without diplopia today | without double vision today | in the absence of diplopia today | and no double vision today | **CHANGED (`->4`):** and new double vision today | without diplopia today | without double vision today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 32 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `12, 39` |
| `everyday` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `12, 39` |
| `medical_paraphrase` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `12, 39` |
| `everyday_paraphrase` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `12, 39` |
| `changed_fact` | 35 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `12, 39` |
| `quad_b` | 31 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `12, 39` |
| `quad_c` | 35 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `12, 39` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **17 words** (`"maxillary sinus pain and pressure accompanied by purulent green rhinorrhea and a 39 C fever without diplopia"`) vs. `everyday_span` = **19 words** (`"pain and pressure around the sinuses with thick green nose mucus and a 39 C fever without double vision"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*No double vision today*) from `"without double vision today"` to `"and new double vision today"` (`right_care`: `2` -> `4`). Nothing else in `everyday` differs.

### `r10-16` — reviewer label: *subacute fatigue cold intolerance and weight gain syndrome* (`right_care: 2`, `target_token: " doctor"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Three months of daily fatigue and cold intolerance with a 6 kg weight gain plus dry skin and constipation in an alert adult requires outpatient doctor blood testing, whereas becoming confused and barely awake requires emergency hospital evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": true, "has_patient_attribution": false, "intervention_notes": "Plain everyday primary-care endocrine register swap (-reg) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + upward somnolence/confusion emergency control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | 3 months of daily fatigue and feeling cold with a 6 kg weight gain | 3 months of persistent fatigue and cold intolerance with a 6 kg weight gain | 3 months of daily tiredness and feeling cold with a 6 kg weight gain | 3 months of daily fatigue and cold intolerance with a 6 kg weight gain | 3 months feeling tired and cold every day with a 6 kg weight gain | 3 months of daily tiredness and feeling cold with a 6 kg weight gain | 3 months of persistent fatigue and cold intolerance with a 6 kg weight gain | 3 months of daily tiredness and feeling cold with a 6 kg weight gain |
| `f2` | Dry skin and hard infrequent stools | accompanied by cutaneous dryness and constipation | plus dry skin and hard infrequent stools | plus cutaneous dryness and constipation | plus dry skin and constipation | plus dry skin and hard infrequent stools | plus cutaneous dryness and constipation | accompanied by dry skin and hard infrequent stools |
| `f3` | Fully alert and oriented today | with intact mental alertness today | while staying fully alert today | while remaining alert and oriented today | while staying clear headed today | **CHANGED (`->4`):** and became confused and barely awake today | while staying mentally alert today | with full alertness today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 33 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3, 6` |
| `everyday` | 34 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3, 6` |
| `medical_paraphrase` | 32 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3, 6` |
| `everyday_paraphrase` | 31 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3, 6` |
| `changed_fact` | 36 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3, 6` |
| `quad_b` | 32 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3, 6` |
| `quad_c` | 34 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `3, 6` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **21 words** (`"persistent fatigue and cold intolerance with a 6 kg weight gain accompanied by cutaneous dryness and constipation with intact mental alertness"`) vs. `everyday_span` = **22 words** (`"daily tiredness and feeling cold with a 6 kg weight gain plus dry skin and hard infrequent stools while staying fully alert"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Fully alert and oriented today*) from `"while staying fully alert today"` to `"and became confused and barely awake today"` (`right_care`: `2` -> `4`). Nothing else in `everyday` differs.

### `r10-17` — reviewer label: *pediatric acute purulent ocular discharge* (`right_care: 2`, `target_token: " clinic"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Two days of thick yellow eye pus matting both eyelids shut in a 3-year-old with normal eye movement warrants outpatient clinic examination and prescription drops, whereas inability to move an eye indicates orbital involvement requiring emergency care.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": false, "intervention_notes": "Plain pediatric caregiver lexical swap (-reg) + upward extraocular-motility emergency control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Son is 3 years old | My 3 year old son | My 3 year old son | My 3 year old boy | My 3 year old boy | My 3 year old son |
| `f2` | 2 days of red eyes and thick yellow pus sticking eyelids shut on waking | 2 days of bilateral bulbar erythema and purulent ocular discharge matting his eyelids on waking | 2 days of red eyes and thick yellow pus gluing his eyelids shut on waking | 2 days of bilateral ocular erythema and mucopurulent discharge crusting his eyelids shut each morning | 2 days of red eyes with yellow eye pus sticking his eyelids together on waking | 2 days of red eyes and thick yellow pus gluing his eyelids shut on waking |
| `f3` | Moving both eyes normally today | with intact extraocular motility today | while moving both eyes easily today | with full extraocular movements today | and moves both eyes normally today | **CHANGED (`->4`):** and cannot move his right eye today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 2` |
| `everyday` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 2` |
| `medical_paraphrase` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 2` |
| `everyday_paraphrase` | 34 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 2` |
| `changed_fact` | 35 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `3, 2` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **16 words** (`"bilateral bulbar erythema and purulent ocular discharge matting his eyelids on waking with intact extraocular motility"`) vs. `everyday_span` = **17 words** (`"red eyes and thick yellow pus gluing his eyelids shut on waking while moving both eyes easily"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Moving both eyes normally today*) from `"while moving both eyes easily today"` to `"and cannot move his right eye today"` (`right_care`: `2` -> `4`). Nothing else in `everyday` differs.

### `r10-18` — reviewer label: *inhaled corticosteroid associated oral white mucosal plaques* (`right_care: 2`, `target_token: " doctor"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** Five days of sore white plaques on the tongue and inner cheeks after starting a steroid inhaler with easy liquid swallowing requires a doctor prescription for antifungal therapy, whereas inability to swallow water requires emergency hospital assessment.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": false, "intervention_notes": "Plain everyday oral-mucosa lexical swap (-reg; all everyday expressions unsourced='none') + upward dysphagia-for-water emergency control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Started a daily steroid inhaler 2 weeks ago | I started a daily corticosteroid inhaler 2 weeks ago | I started a daily steroid inhaler 2 weeks ago | I began daily inhaled corticosteroids 2 weeks ago | I began using a daily steroid inhaler 2 weeks ago | I started a daily steroid inhaler 2 weeks ago |
| `f2` | 5 days of sore white patches on the tongue and inner cheeks leaving red spots when wiped | 5 days of sore white plaques on my tongue and buccal mucosa with erythematous bases when scraped | 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped | 5 days of painful white oral plaques over my tongue and buccal mucosa leaving erythematous mucosa on scraping | 5 days of sore white patches on my tongue and inside my cheeks that wipe off red | 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped |
| `f3` | Swallowing liquids easily today | and intact liquid swallowing today | while swallowing liquids easily today | with normal liquid intake today | while drinking liquids easily today | **CHANGED (`->4`):** and cannot swallow water today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 38 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 5` |
| `everyday` | 38 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 5` |
| `medical_paraphrase` | 38 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 5` |
| `everyday_paraphrase` | 39 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 5` |
| `changed_fact` | 38 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `2, 5` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **28 words** (`"corticosteroid inhaler 2 weeks ago and have 5 days of sore white plaques on my tongue and buccal mucosa with erythematous bases when scraped and intact liquid swallowing"`) vs. `everyday_span` = **28 words** (`"steroid inhaler 2 weeks ago and have 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped while swallowing liquids easily"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Swallowing liquids easily today*) from `"while swallowing liquids easily today"` to `"and cannot swallow water today"` (`right_care`: `2` -> `4`). Nothing else in `everyday` differs.

### `r10-19` — reviewer label: *expanding annular rash after tick bite* (`right_care: 2`, `target_token: " doctor"`, `carrier_frame: "so I should see a"`)

- **Level rationale:** An expanding 7 cm red ring rash with a 38 C fever 8 days after a tick bite without syncope requires a doctor visit for prescription oral antibiotics, whereas adding a syncopal episode raises concern for cardiac conduction block requiring emergency evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": true, "has_quad_2x2_syntax": false, "has_patient_attribution": false, "intervention_notes": "Colloquial lexicon manipulation ('spell (a shaking spell, a fainting spell, a dizzy spell)'; Wiktionary US colloquial lexical sense only) + upward syncope/carditis emergency control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | 11 year old son had a tick bite on his calf 8 days ago | My 11 year old son had a calf tick bite 8 days ago | My 11 year old son had a calf tick bite 8 days ago | My 11 year old boy sustained a calf tick bite 8 days ago | My 11 year old boy got a calf tick bite 8 days ago | My 11 year old son had a calf tick bite 8 days ago |
| `f2` | Expanding 7 cm red ring rash and 38 C fever | an expanding 7 cm annular erythematous rash and a 38 C fever | a spreading 7 cm red ring rash and a 38 C fever | an expanding 7 cm annular erythema and a 38 C pyrexia | a growing 7 cm red bullseye rash and a 38 C fever | a spreading 7 cm red ring rash and a 38 C fever |
| `f3` | No fainting episodes | without syncope | without fainting spells | without syncopal episodes | with no fainting spells | **CHANGED (`->4`):** and a fainting spell today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 34 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `11, 8, 7, 38` |
| `everyday` | 35 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `11, 8, 7, 38` |
| `medical_paraphrase` | 34 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `11, 8, 7, 38` |
| `everyday_paraphrase` | 36 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `11, 8, 7, 38` |
| `changed_fact` | 37 | PASS | PASS (`"so I should see a"`) | 0 | 0 | `11, 8, 7, 38` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **15 words** (`"developed an expanding 7 cm annular erythematous rash and a 38 C fever without syncope"`) vs. `everyday_span` = **16 words** (`"got a spreading 7 cm red ring rash and a 38 C fever without fainting spells"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*No fainting episodes*) from `"without fainting spells"` to `"and a fainting spell today"` (`right_care`: `2` -> `4`). Nothing else in `everyday` differs.

### `r10-20` — reviewer label: *subacute exertional dyspnea conjunctival pallor and koilonychia* (`right_care: 2`, `target_token: " clinic"`, `carrier_frame: "so I need to go to the"`)

- **Level rationale:** Six weeks of exertional tiredness and dizziness on 1 flight of stairs with pale inner eyelids and spooned nails while breathing comfortably at rest requires outpatient clinic blood testing, whereas resting air hunger requires emergency evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": true, "has_quad_2x2_syntax": false, "has_patient_attribution": false, "intervention_notes": "Regional English lexicon manipulation ('giddiness / feeling giddy'; attested in Indian clinical case report Rana 2025 as clinician-reported symptom wording) + upward resting-dyspnea control (-cf)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | 6 weeks of tiredness and lightheadedness climbing 1 flight of stairs | 6 weeks of exertional fatigue and lightheadedness climbing 1 flight of stairs | 6 weeks of tiredness and feeling giddy climbing 1 flight of stairs | 6 weeks of exertional fatigue and presyncopal dizziness on 1 flight of stairs | 6 weeks getting tired with giddiness climbing 1 flight of stairs | 6 weeks of tiredness and feeling giddy climbing 1 flight of stairs |
| `f2` | Pale inner eyelids and spoon shaped nails | accompanied by conjunctival pallor and koilonychia | with pale inner eyelids and spoon shaped nails | accompanied by palpebral conjunctival pallor and spoon nails | plus pale lower eyelids and nails curved like spoons | with pale inner eyelids and spoon shaped nails |
| `f3` | Comfortable normal breathing at rest | with comfortable resting respiration today | but easy resting breathing today | with normal resting breathing today | while breathing easily at rest today | **CHANGED (`->4`):** and am gasping for air at rest today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 33 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `6, 1` |
| `everyday` | 35 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `6, 1` |
| `medical_paraphrase` | 35 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `6, 1` |
| `everyday_paraphrase` | 35 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `6, 1` |
| `changed_fact` | 38 | PASS | PASS (`"so I need to go to the"`) | 0 | 0 | `6, 1` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **19 words** (`"exertional fatigue and lightheadedness climbing 1 flight of stairs accompanied by conjunctival pallor and koilonychia with comfortable resting respiration"`) vs. `everyday_span` = **21 words** (`"tiredness and feeling giddy climbing 1 flight of stairs with pale inner eyelids and spoon shaped nails but easy resting breathing"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Comfortable normal breathing at rest*) from `"but easy resting breathing today"` to `"and am gasping for air at rest today"` (`right_care`: `2` -> `4`). Nothing else in `everyday` differs.

### `r10-21` — reviewer label: *mild uncomplicated toe web scaling* (`right_care: 1`, `target_token: " cream"`, `carrier_frame: "so I just need some"`)

- **Level rationale:** Five days of mild itchy peeling skin confined between the 4th and 5th toes without pus is a minor superficial toe-web irritation manageable with over-the-counter antifungal cream, whereas oozing yellow pus indicates secondary bacterial infection needing a clinician.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": true, "has_patient_attribution": false, "intervention_notes": "Plain everyday self-care lexical swap (-reg) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + upward purulent-oozing clinician control (-cf: 1 -> 2)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | 5 days of mild itchy peeling skin between the 4th and 5th left toes after gym showers | 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers | 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers | 5 days of mild pruritic scaling and peeling in the 4th and 5th left interdigital toe web after gym showers | 5 days of mild itchy flaking skin between my 4th and 5th left toes after gym showers | 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers | 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers | 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers |
| `f2` | No pus | without purulent exudate | with no pus | without purulence | and no pus at all | **CHANGED (`->2`):** oozing thick yellow pus | with no purulent exudate | without pus |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 28 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `5` |
| `everyday` | 28 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `5` |
| `medical_paraphrase` | 29 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `5` |
| `everyday_paraphrase` | 29 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `5` |
| `changed_fact` | 29 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `5` |
| `quad_b` | 29 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `5` |
| `quad_c` | 27 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `5` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **16 words** (`"pruritic interdigital desquamation between my 4th and 5th left toes after gym showers without purulent exudate"`) vs. `everyday_span` = **16 words** (`"itchy peeling skin between my 4th and 5th left toes after gym showers with no pus"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f2` (*No pus*) from `"with no pus"` to `"oozing thick yellow pus"` (`right_care`: `1` -> `2`). Nothing else in `everyday` differs.

### `r10-22` — reviewer label: *mild uncomplicated infant diaper area redness* (`right_care: 1`, `target_token: " ointment"`, `carrier_frame: "so I just need some"`)

- **Level rationale:** One day of mild pink skin redness in a healthy 8-month-old infant's diaper area without pustules is simple irritant redness managed with over-the-counter barrier ointment, whereas spreading yellow pus blisters require outpatient pediatric evaluation.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": false, "intervention_notes": "Plain infant-caregiver self-care lexical swap (-reg) + upward pustular-infection primary-care control (-cf: 1 -> 2)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | 8 month old son has 1 day of mild pink redness in the diaper area | My 8 month old son has 1 day of mild macular erythema in his diaper area | My 8 month old son has 1 day of mild pink skin redness in his diaper area | My 8 month old infant developed 1 day of mild superficial diaper area erythema | My 8 month old baby boy got 1 day of mild pink redness in his diaper area | My 8 month old son has 1 day of mild pink skin redness in his diaper area |
| `f2` | No pus blisters | without pustular lesions | with no pus blisters | in the absence of pustules | without any pus bumps | **CHANGED (`->2`):** covered in yellow pus blisters |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 24 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `8, 1` |
| `everyday` | 26 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `8, 1` |
| `medical_paraphrase` | 24 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `8, 1` |
| `everyday_paraphrase` | 26 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `8, 1` |
| `changed_fact` | 27 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `8, 1` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **9 words** (`"macular erythema in his diaper area without pustular lesions"`) vs. `everyday_span` = **11 words** (`"pink skin redness in his diaper area with no pus blisters"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f2` (*No pus blisters*) from `"with no pus blisters"` to `"covered in yellow pus blisters"` (`right_care`: `1` -> `2`). Nothing else in `everyday` differs.

### `r10-23` — reviewer label: *mild winter lower leg skin dryness* (`right_care: 1`, `target_token: " lotion"`, `carrier_frame: "so I just need some"`)

- **Level rationale:** Seven days of mild dry flaky itchy skin on both shins in cold winter weather without pus bumps is uncomplicated winter dry skin managed with over-the-counter moisturizing lotion, whereas painful yellow pus bumps indicate skin infection needing a clinician.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": true, "has_patient_attribution": false, "intervention_notes": "Plain everyday self-care lexical swap (-reg) + 2x2 syntax-by-vocabulary crossing (quad_b, quad_c) + upward painful-pustules clinician control (-cf: 1 -> 2)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | 7 days of mild dry flaky itchy skin on both shins in cold winter air | 7 days of mild cutaneous dryness with fine desquamation and pruritus on both shins in winter weather | 7 days of mild dry skin with flakiness and itching on both shins in winter weather | 7 days of mild bilateral pretibial cutaneous dryness with scaling and pruritus in cold winter air | 7 days of mild dry flaky itchy skin on both shins in cold winter weather | 7 days of mild dry skin with flakiness and itching on both shins in winter weather | 7 days of mild cutaneous dryness with fine desquamation and pruritus on both shins in winter weather | 7 days of mild dry skin with flakiness and itching on both shins in winter weather |
| `f2` | No pus bumps | without pustules | with no pus bumps | without pustular lesions | without any pus bumps | **CHANGED (`->2`):** with painful yellow pus bumps | with no pustules | without pus bumps |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 27 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `7` |
| `everyday` | 28 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `7` |
| `medical_paraphrase` | 26 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `7` |
| `everyday_paraphrase` | 26 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `7` |
| `changed_fact` | 29 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `7` |
| `quad_b` | 28 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `7` |
| `quad_c` | 27 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `7` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **15 words** (`"cutaneous dryness with fine desquamation and pruritus on both shins in winter weather without pustules"`) vs. `everyday_span` = **16 words** (`"dry skin with flakiness and itching on both shins in winter weather with no pus bumps"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f2` (*No pus bumps*) from `"with no pus bumps"` to `"with painful yellow pus bumps"` (`right_care`: `1` -> `2`). Nothing else in `everyday` differs.

### `r10-24` — reviewer label: *mild seasonal pollen sneezing and watery eyes* (`right_care: 1`, `target_token: " medicine"`, `carrier_frame: "so I just need some"`)

- **Level rationale:** Three days of sneezing with a clear runny nose and mildly itchy watery eyes outdoors in spring pollen with easy breathing is mild seasonal pollen irritation manageable with over-the-counter allergy medicine, whereas acute inability to catch breath at rest requires emergency care.
- **Protocol flags:** `{"has_dialect_lexicon": false, "has_quad_2x2_syntax": false, "has_patient_attribution": false, "intervention_notes": "Plain everyday self-care lexical swap (-reg) + upward resting-dyspnea emergency control (-cf: 1 -> 4)."}`

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | 3 days of sneezing and clear runny nose outdoors in spring pollen | 3 days of paroxysmal sneezing and clear aqueous rhinorrhea outdoors in spring pollen | 3 days of sneezing and a clear running nose outdoors in spring pollen | 3 days of sneezing and clear watery rhinorrhea around spring pollen | 3 days of sneezing when my nose starts running outdoors in spring pollen | 3 days of sneezing and a clear running nose outdoors in spring pollen |
| `f2` | Mildly itchy watery eyes | with mild ocular pruritus and epiphora | with mildly itchy watery eyes | accompanied by mild bilateral ocular pruritus and tearing | with mildly itchy and watery eyes | with mildly itchy watery eyes |
| `f3` | Easy normal breathing | plus eupnea today | and easy breathing today | with normal respiration today | and comfortable breathing today | **CHANGED (`->4`):** and cannot catch my breath sitting still today |

| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|---|
| `medical` | 30 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `3` |
| `everyday` | 30 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `3` |
| `medical_paraphrase` | 30 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `3` |
| `everyday_paraphrase` | 30 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `3` |
| `changed_fact` | 34 | PASS | PASS (`"so I just need some"`) | 0 | 0 | `3` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **18 words** (`"paroxysmal sneezing and clear aqueous rhinorrhea outdoors in spring pollen with mild ocular pruritus and epiphora plus eupnea"`) vs. `everyday_span` = **18 words** (`"sneezing and a clear running nose outdoors in spring pollen with mildly itchy watery eyes and easy breathing"`).
- **Single-fact control (`changed_fact`):** Changes **only** `f3` (*Easy normal breathing*) from `"and easy breathing today"` to `"and cannot catch my breath sitting still today"` (`right_care`: `1` -> `4`). Nothing else in `everyday` differs.

---

## Unsourced Expressions and Attribution Clauses (`"source": "none"`)

### Everyday Expressions Marked `"source": "none"`

| Family | Expression |
|---|---|
| `r10-01` | `"down my left leg"` |
| `r10-01` | `"numb left toes"` |
| `r10-01` | `"cannot pee"` |
| `r10-02` | `"cannot swallow spit"` |
| `r10-03` | `"spreading hot red right calf swelling"` |
| `r10-04` | `"chest pain when coughing"` |
| `r10-05` | `"burning upper stomach pain"` |
| `r10-05` | `"burning high stomach pain"` |
| `r10-07` | `"swollen ankles"` |
| `r10-07` | `"swelling in both ankles"` |
| `r10-08` | `"clustered blisters"` |
| `r10-08` | `"confusion"` |
| `r10-09` | `"receding gums"` |
| `r10-09` | `"1 loose lower front tooth"` |
| `r10-09` | `"without jaw or tongue swelling"` |
| `r10-10` | `"nail pits"` |
| `r10-10` | `"without raw skin sloughing today"` |
| `r10-11` | `"daily low mood"` |
| `r10-11` | `"unimproved after 2 different prescribed clinic medicines"` |
| `r10-11` | `"while speaking normally today"` |
| `r10-12` | `"car crash"` |
| `r10-12` | `"keeping me from driving"` |
| `r10-12` | `"jumpiness"` |
| `r10-13` | `"cloudy vision in both eyes"` |
| `r10-13` | `"building up over 9 months"` |
| `r10-14` | `"big clots"` |
| `r10-14` | `"without fainting today"` |
| `r10-15` | `"thick green nose mucus"` |
| `r10-15` | `"thick green snot"` |
| `r10-15` | `"without double vision today"` |
| `r10-16` | `"daily tiredness and feeling cold"` |
| `r10-16` | `"hard infrequent stools"` |
| `r10-17` | `"thick yellow pus gluing his eyelids shut on waking"` |
| `r10-17` | `"while moving both eyes easily today"` |
| `r10-18` | `"sore white patches on my tongue and inner cheeks"` |
| `r10-18` | `"leaving red spots when wiped"` |
| `r10-18` | `"while swallowing liquids easily today"` |
| `r10-19` | `"spreading 7 cm red ring rash"` |
| `r10-20` | `"feeling giddy"` |
| `r10-20` | `"pale inner eyelids"` |
| `r10-20` | `"spoon shaped nails"` |
| `r10-21` | `"itchy peeling skin between my 4th and 5th left toes"` |
| `r10-21` | `"with no pus"` |
| `r10-22` | `"pink skin redness"` |
| `r10-22` | `"with no pus blisters"` |
| `r10-23` | `"with no pus bumps"` |
| `r10-24` | `"and easy breathing today"` |

### Attribution Clauses Marked `"source": "none"`

| Family | Attribution Clause |
|---|---|
| `r10-01` | `"and I think I pulled a muscle"` |
| `r10-02` | `"and I think it is a throat virus"` |
| `r10-03` | `"and I think it is a bug bite"` |
| `r10-05` | `"and I think it is just indigestion"` |
| `r10-08` | `"and I think it is heat rash"` |
| `r10-10` | `"and I think it is dry skin"` |
| `r10-11` | `"and I think it is school stress"` |
| `r10-12` | `"and I think it will pass alone"` |
