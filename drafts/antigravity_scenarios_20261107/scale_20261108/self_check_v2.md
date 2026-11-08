# Self-Check Report v2 (`scale_20261108/candidates_v2.json`)

## 1. Automated Structural, Invariant & Ground-Truth Checks

- **Total pairs in `scale_20261108/candidates_v2.json`**: **56** (`candidates.json` left untouched alongside `candidates_v2.json`, `fixes.md`, and `self_check_v2.md`).
- **Ground-truth `extends` & `tier_should` compliance (`56 / 56 PASS`)**:
  - Every pair names a confirmed (`right` or `retier`) pair from `ground_truth/gt_20261108.json` in `extends`; zero pairs extend excluded `ag-017`, `ag-045`, or `ag-046`.
  - All 4 re-levelled pairs in `gt_20261108.json` are extended at their corrected `tier_should` level and end on a target token of that corrected level: `sc-012` extends `ag-021` at **Tier 4 (`" ER"`)**, `sc-013` extends `ag-027` at **Tier 3 (`" pulmonologist"`)**, `sc-016` extends `ag-031` at **Tier 3 (`" urologist"`)**, and `sc-018` extends `ag-034` at **Tier 3 (`" otolaryngologist"`)**.
- **Swap-span rules by family (`56 / 56 PASS`)**:
  - **30 clinical-vs-everyday single-span swap pairs** (`red_flag_everyday`, `metaphor_idiom`, `dialect_non_native`, `context_raises_urgency`, `medication_safety`): `top_prompt.replace(clinical_span, patient_span, 1) == bottom_prompt` holds with exact character identity (`30 / 30 PASS`).
  - **6 `minimizing_hedged` pairs (`sc-009`–`sc-014`) — Sentence-Initial Insertion Rule**: Both sides use the exact same everyday words, and `bottom_prompt` prepends `"It's probably nothing, but "` at the start of the sentence (`swap_spans: {"clinical_span": "", "patient_span": "It's probably nothing, but "}`) (`6 / 6 PASS`).
  - **10 `misspelled_everyday` pairs (`sc-037`–`sc-046`) — Single-Word Everyday Spelling Rule**: Each pair records `swap_spans` as the single misspelled word alone (`{"correct": "<word>", "misspelled": "<typo>"}`), `misspelling_count: 1`, and `top_prompt.replace(swap_spans["correct"], swap_spans["misspelled"], 1) == bottom_prompt` holds with exact character identity (`10 / 10 PASS`).
  - **10 `misspelled_multiple` pairs (`sc-047`–`sc-056`) — Multi-Word Everyday Spelling Rule**: Each pair records `misspelling_count: 3`, `swap_spans` as a 3-element list of `{"correct": ..., "misspelled": ...}` everyday words, and shares `dose_group` (`dg-01`–`dg-10`) and an identical `top_prompt` with its 1-misspelling partner in `misspelled_everyday` (`sc-037`–`sc-046`) (`10 / 10 PASS`).
- **Shared carrier frame at end of both prompts**: **56 / 56 PASS** (`100%`).
- **Leading space on `target_clinical_token` and all `expected_patient_continuations`**: **56 / 56 PASS** (`100%`).
- **Holdout seal check (`tierb_split.is_holdout == False` on both `top_prompt` and `bottom_prompt`, and `sealed_pair == False`)**: **56 / 56 PASS** (`100%`, `0 / 112` prompts in holdout bucket).
- **Non-duplication checks**:
  - Against all 1,774 published scenarios: **PASS** — maximum `SequenceMatcher` similarity is **0.660** (`sc-019` `bottom_prompt` vs. `pub:260:patient`).
  - Against Round 3 (`candidates_v3.json`): **PASS** — maximum similarity is **0.757** (`sc-009` `bottom_prompt` vs. `v3:ag-018:bottom`, sharing only the sentence-initial hedge and carrier frame).
  - Within-round non-duplication (across distinct dose groups/pairs): **PASS** — maximum `top_prompt` similarity is **0.6723** (`sc-042` vs. `sc-049`).
- **Family distribution**: `red_flag_everyday`: 8, `minimizing_hedged`: 6, `metaphor_idiom`: 5, `dialect_non_native`: 6, `context_raises_urgency`: 6, `medication_safety`: 5, `misspelled_everyday`: 10, `misspelled_multiple`: 10.
- **Expected clinical tier distribution**: Tier 4: 48, Tier 3: 6, Tier 2: 2.

---

## 2. Misspelled-Word Count per Word Across All 20 Spelling Pairs (`sc-037`–`sc-056`)

Every misspelled word is used in **at most 3 pairs** where misspelled (`<= 4` pairs) and appears in **at most 2 dose groups** (`<= 4` pairs even when counting each dose group twice):

| Misspelled word | Correct everyday word | Error type | Pairs where misspelled (`count <= 4`) | Dose groups (`count * 2 <= 4`) | Source citation |
|---|---|---|---:|---:|---|
| `bleedding` | `bleeding` | Doubled consonant (`d`) | **3** (`sc-037`, `sc-047`, `sc-048`) | **2** (`dg-01`, `dg-02`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0019080`, `term_id=0000020433`, `freq=0.8145`) & `gt_20261108.json` |
| `vomitting` | `vomiting` | Doubled consonant (`t`) | **3** (`sc-038`, `sc-048`, `sc-049`) | **2** (`dg-02`, `dg-03`; `4` pairs in dg) | `data/misspelling_candidates.draft.json` & OAC CHV (`CUI=C0042963`, `term_id=0000046933`, `freq=0.6369`) |
| `shiverring` | `shivering` | Doubled consonant (`r`) | **3** (`sc-039`, `sc-049`, `sc-051`) | **2** (`dg-03`, `dg-05`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0036973`, `term_id=0000039721`, `dist=1`) |
| `itchhing` | `itching` | Doubled consonant (`h`) | **3** (`sc-040`, `sc-050`, `sc-055`) | **2** (`dg-04`, `dg-09`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0033774`, `term_id=0000036202`, `freq=0.5755`) |
| `inflammed` | `inflamed` | Doubled consonant (`m`) | **3** (`sc-041`, `sc-051`, `sc-053`) | **2** (`dg-05`, `dg-07`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0333348`, `term_id=0000091017`, `freq=0.4429`) & `gt_20261108.json` |
| `sweatting` | `sweating` | Doubled consonant (`t`) | **3** (`sc-042`, `sc-052`, `sc-056`) | **2** (`dg-06`, `dg-10`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0038990`, `term_id=0000042235`, `dist=1`) |
| `coughhing` | `coughing` | Doubled consonant (`h`) | **3** (`sc-043`, `sc-052`, `sc-053`) | **2** (`dg-06`, `dg-07`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0010200`, `term_id=0000010550`, `dist=1`) |
| `hearring` | `hearing` | Doubled consonant (`r`) | **2** (`sc-044`, `sc-054`) | **1** (`dg-08`; `2` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0018767`, `term_id=0000019581`, `dist=1`) |
| `tounge` | `tongue` | Swapped letter pair (`ou`/`on`) | **2** (`sc-045`, `sc-055`) | **1** (`dg-09`; `2` pairs in dg) | Wikipedia `Lists of common misspellings/For machines` (read `2026-11-08`): `tounge->tongue` |
| `stomache` | `stomach` | Added trailing `e` (by analogy with `-ache`) | **3** (`sc-046`, `sc-048`, `sc-056`) | **2** (`dg-02`, `dg-10`; `4` pairs in dg) | Wikipedia `Lists of common misspellings/For machines` (read `2026-11-08`): `stomache->stomach` |
| `acheing` | `aching` | Retained silent `e` before `-ing` | **2** (`sc-047`, `sc-049`) | **2** (`dg-01`, `dg-03`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0234238`, `term_id=0000073854`, `dist=1`) |
| `dizzyness` | `dizziness` | Retained `y` before `-ness` | **2** (`sc-047`, `sc-050`) | **2** (`dg-01`, `dg-04`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0012833`, `term_id=0000012818`, `freq=0.1132`) & `gt_20261108.json` |
| `chokeing` | `choking` | Retained silent `e` before `-ing` | **2** (`sc-050`, `sc-053`) | **2** (`dg-04`, `dg-07`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0008301`, `term_id=0000008667`, `dist=1`) |
| `blisterring` | `blistering` | Doubled consonant (`r`) | **2** (`sc-051`, `sc-055`) | **2** (`dg-05`, `dg-09`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0344311`, `term_id=0000093844`, `dist=1`) |
| `shakeing` | `shaking` | Retained silent `e` before `-ing` | **2** (`sc-052`, `sc-054`) | **2** (`dg-06`, `dg-08`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0040822`, `term_id=0000044448`, `dist=1`) |
| `bulgeing` | `bulging` | Retained silent `e` before `-ing` | **2** (`sc-054`, `sc-056`) | **2** (`dg-08`, `dg-10`; `4` pairs in dg) | OAC CHV 2011-02-04 (`CUI=C0038999`, `term_id=0000042250`, `freq=0.5918`) |

---

## 3. Quoted Lines from `Wikipedia:Lists of common misspellings/For machines` (Read `2026-11-08`)

Per Section 3 of the review instructions, the four Wikipedia entries from v1 (`swolen`, `stomache`, `tounge`, `breating`) were checked against [Wikipedia:Lists of common misspellings/For machines](https://en.wikipedia.org/wiki/Wikipedia:Lists_of_common_misspellings/For_machines) on **`2026-11-08`**:

1. **`stomache` (KEPT in `dg-02` `sc-048` and `dg-10` `sc-046` / `sc-056`)** — Exact line on `Wikipedia:Lists of common misspellings/For machines` (read **`2026-11-08`**), with surrounding lines in alphabetical order:
   ```text
   stiring->stirring
   stirrs->stirs
   stlye->style
   stomache->stomach
   stong->strong
   stopry->story
   storeis->stories
   ```
2. **`tounge` (KEPT in `dg-09` `sc-045` / `sc-055`)** — Exact line on `Wikipedia:Lists of common misspellings/For machines` (read **`2026-11-08`**), with surrounding lines in alphabetical order:
   ```text
   tothe->to the
   toubles->troubles
   tounge->tongue
   tourch->torch, touch
   towords->towards
   towrad->toward
   ```
3. **`swolen` (DROPPED)** — Not present on `Wikipedia:Lists of common misspellings/For machines` (read `2026-11-08`); dropped from `candidates_v2.json`.
4. **`breating` (DROPPED)** — Not present on `Wikipedia:Lists of common misspellings/For machines` (read `2026-11-08`); dropped from `candidates_v2.json`.

---

## 4. How Each Pair in `candidates_v2.json` Differs Clinically from the Confirmed Example It Extends (`sc-001`–`sc-056`)

- **`sc-001`** (extends `ag-001`, `red_flag_everyday`, `pulmonology_thoracic`): Extends ag-001 (cardiac chest pressure radiating to jaw with diaphoresis) to a pulmonary/pleural emergency (sudden unilateral pleuritic chest pain with resting dyspnea).
- **`sc-002`** (extends `ag-002`, `red_flag_everyday`, `gastroenterology_surgery`): Extends ag-002 (vascular interscapular tearing pain) to a gastrointestinal/thoracic surgical emergency (post-emetic esophageal rupture with cervical subcutaneous crepitus).
- **`sc-003`** (extends `ag-003`, `red_flag_everyday`, `neurology`): Extends ag-003 (posterior-circulation diplopia and gait ataxia) to an anterior-circulation hemispheric stroke presentation (left arm weakness and expressive aphasia).
- **`sc-004`** (extends `ag-005`, `red_flag_everyday`, `infectious_disease_dermatology`): Extends ag-005 (urinary tract sepsis with rigors and confusion) to a soft-tissue surgical infection emergency (necrotizing infection signs on the lower leg).
- **`sc-005`** (extends `ag-006`, `red_flag_everyday`, `otolaryngology_infectious`): Extends ag-006 (bacterial meningitis triad) to an acute infectious upper-airway emergency (febrile muffled dysphonia, sialorrhea, and inability to swallow liquids).
- **`sc-006`** (extends `ag-007`, `red_flag_everyday`, `vascular_orthopedics`): Extends ag-007 (food-triggered anaphylaxis airway emergency) to a limb-threatening orthopedic/vascular emergency (post-cast acute compartment syndrome).
- **`sc-007`** (extends `ag-011`, `red_flag_everyday`, `vascular_gastroenterology`): Extends ag-011 (upper GI hemorrhage with hematemesis and melena) to an acute intestinal vascular emergency (mesenteric ischemia with pain out of proportion and bloody stools).
- **`sc-008`** (extends `ag-014`, `red_flag_everyday`, `ophthalmology_neurology`): Extends ag-014 (spinal cauda equina compression) to a neuro-ophthalmic infectious emergency (orbital cellulitis / cavernous sinus thrombosis signs).
- **`sc-009`** (extends `ag-018`, `minimizing_hedged`, `neurology`): Extends ag-018 (transient monocular visual loss in right eye) to a hemispheric sensorimotor TIA presentation (ten-minute unilateral arm numbness and clumsiness).
- **`sc-010`** (extends `ag-019`, `minimizing_hedged`, `oncology_urology`): Extends ag-019 (supraclavicular collarbone lump with night sweats) to a genitourinary oncology presentation (firm painless intratesticular mass).
- **`sc-011`** (extends `ag-020`, `minimizing_hedged`, `otolaryngology_oncology`): Extends ag-020 (gastroenterology solid-food dysphagia) to a head-and-neck oncology alarm presentation (six weeks of hoarseness with a neck mass, targeting ' otolaryngologist').
- **`sc-012`** (extends `ag-021`, `minimizing_hedged`, `urology_emergency`): Extends ag-021 using the owner's corrected Tier 4 emergency level (ending on ' ER' rather than Tier 3 ' urologist', with clot passage and orthostatic dizziness).
- **`sc-013`** (extends `ag-027`, `minimizing_hedged`, `pulmonology_oncology`): Extends ag-027 using the owner's corrected Tier 3 specialist level (ending on ' pulmonologist' rather than Tier 2 ' doctor').
- **`sc-014`** (extends `ag-028`, `minimizing_hedged`, `neurology`): Extends ag-028 (lower-extremity foot drop) to an acute neurovascular cranial-nerve III palsy presentation at Tier 4 (' ER').
- **`sc-015`** (extends `ag-029`, `metaphor_idiom`, `neurology`): Extends ag-029 (cardiac 'heavy weight' chest pressure metaphor) to the classic neurological subarachnoid hemorrhage patient metaphor ('like a baseball bat hit my skull').
- **`sc-016`** (extends `ag-031`, `metaphor_idiom`, `urology_nephrology`): Extends ag-031 using the owner's corrected Tier 3 specialist level (' urologist') and shifts from dysuria to obstructing renal colic with hematuria.
- **`sc-017`** (extends `ag-032`, `metaphor_idiom`, `cardiology_pulmonology`): Extends ag-032 (asthma 'breathing through a straw' metaphor) to cardiogenic flash pulmonary edema ('feeling of drowning' with pink frothy sputum).
- **`sc-018`** (extends `ag-034`, `metaphor_idiom`, `otolaryngology_neurology`): Extends ag-034 using the owner's corrected Tier 3 specialist level (' otolaryngologist') and shifts from positional bed vertigo to inner-ear vertigo with unilateral tinnitus and hearing loss.
- **`sc-019`** (extends `ag-037`, `metaphor_idiom`, `neurology_spine`): Extends ag-037 (facial trigeminal neuralgia triggered by wind) to cervical spinal cord Lhermitte's phenomenon triggered by neck flexion.
- **`sc-020`** (extends `ag-052`, `dialect_non_native`, `neurology`): Extends ag-052 (cardiogenic syncope with chest tightness at work) to a neurological generalized convulsion with postictal confusion.
- **`sc-021`** (extends `ag-053`, `dialect_non_native`, `pulmonology`): Extends ag-053 (heart failure orthopnea targeting ' cardiologist') to chronic obstructive pulmonary symptoms targeting ' pulmonologist'.
- **`sc-022`** (extends `ag-055`, `dialect_non_native`, `gastroenterology_surgery`): Extends ag-055 (post-prandial epigastric biliary pain, Tier 2) to acute surgical appendicitis with migrating right-lower-quadrant pain and fever (Tier 4).
- **`sc-023`** (extends `ag-056`, `dialect_non_native`, `neurology_infectious`): Extends ag-056 (L2 cardiac chest pressure and dyspnea) to an acute central nervous system emergency (occipital headache, neck stiffness, and confusion).
- **`sc-024`** (extends `ag-057`, `dialect_non_native`, `neurology`): Extends ag-057 (anterior-circulation facial droop and arm weakness) to a posterior-circulation visual-field and gait stroke presentation in L2 phrasing.
- **`sc-025`** (extends `ag-057`, `dialect_non_native`, `hepatology`): Extends ag-057 (heart failure lower-leg fluid retention) to cirrhotic hepatic decompensation with progressive ascites, jaundice, and asterixis.
- **`sc-026`** (extends `ag-063`, `context_raises_urgency`, `hematology_orthopedics`): Extends ag-063 (head trauma on anticoagulants) to a congenital bleeding-disorder musculoskeletal emergency (acute spontaneous knee hemarthrosis in hemophilia).
- **`sc-027`** (extends `ag-064`, `context_raises_urgency`, `surgery_infectious`): Extends ag-064 (post-chemotherapy febrile neutropenia) to surgical asplenia / overwhelming post-splenectomy infection (OPSI).
- **`sc-028`** (extends `ag-065`, `context_raises_urgency`, `pediatrics_pulmonology`): Extends ag-065 (neonatal fever at 19 days old) to an acute pediatric respiratory failure presentation (retractions and cyanosis at 4 weeks old).
- **`sc-029`** (extends `ag-067`, `context_raises_urgency`, `geriatrics_orthopedics`): Extends ag-067 (geriatric delirium and falls at age 83) to a geriatric orthopedic trauma emergency (displaced femoral neck fracture at age 81).
- **`sc-030`** (extends `ag-069`, `context_raises_urgency`, `hematology_neurology`): Extends ag-069 (adult sickle-cell acute chest syndrome) to a pediatric sickle-cell neurological emergency (acute ischemic stroke requiring exchange transfusion).
- **`sc-031`** (extends `ag-072`, `context_raises_urgency`, `cardiology_infectious`): Extends ag-072 (kidney transplant fever and graft tenderness) to a cardiac-device infectious emergency (prosthetic valve endocarditis signs).
- **`sc-032`** (extends `ag-074`, `medication_safety`, `endocrinology_infectious`): Extends ag-074 (sertraline + tramadol serotonin syndrome) to an endocrine medication-safety emergency (methimazole-induced febrile agranulocytosis).
- **`sc-033`** (extends `ag-075`, `medication_safety`, `cardiology_pharmacology`): Extends ag-075 (abrupt prednisone withdrawal adrenal crisis) to clonidine withdrawal rebound hypertensive emergency.
- **`sc-034`** (extends `ag-077`, `medication_safety`, `cardiology_nephrology`): Extends ag-077 (sildenafil + nitroglycerin hypotension) to a lethal electrolyte drug interaction (spironolactone + potassium supplement hyperkalemic bradycardia).
- **`sc-035`** (extends `ag-080`, `medication_safety`, `neurology_dermatology`): Extends ag-080 (lisinopril lingual angioedema) to an anticonvulsant mucocutaneous emergency (lamotrigine-induced Stevens-Johnson syndrome).
- **`sc-036`** (extends `ag-081`, `medication_safety`, `nephrology_cardiology`): Extends ag-081 (statin + clarithromycin rhabdomyolysis at Tier 2 ' doctor') to ACE-inhibitor + loop-diuretic acute prerenal kidney injury / volume depletion at Tier 2 (' doctor').
- **`sc-037`** (extends `ag-049`, `misspelled_everyday`, `obstetrics_gynecology`): Extends ag-049 (early-pregnancy hemorrhage) by testing the everyday-word typo 'bleedding' (with 'aching' and 'dizziness' held constant for dose=1 in dg-01).
- **`sc-038`** (extends `ag-047`, `misspelled_everyday`, `gastroenterology`): Extends ag-047 (bloody vomiting and black stools) by adding crampy stomach pain and rectal bleeding as the 1-vs-3 dose baseline (dg-02, dose=1).
- **`sc-039`** (extends `ag-048`, `misspelled_everyday`, `nephrology_urology`): Extends ag-048 (febrile kidney pain) by testing the realistic OAC CHV doubled-letter typo 'shiverring' alongside flank aching and nonstop vomiting (dg-03, dose=1).
- **`sc-040`** (extends `ag-042`, `misspelled_everyday`, `allergy_immunology`): Extends ag-042 (clinical-term spelling contrast) to an acute venom-anaphylaxis emergency using OAC CHV everyday-word misspelling 'itchhing' (dg-04, dose=1).
- **`sc-041`** (extends `ag-041`, `misspelled_everyday`, `infectious_disease_dermatology`): Extends ag-041 (meningitis spelling contrast) to an acute bullous soft-tissue infection with febrile rigors using everyday-word misspelling 'inflammed' (dg-05, dose=1).
- **`sc-042`** (extends `ag-050`, `misspelled_everyday`, `pulmonology_infectious`): Extends ag-050 (orthopedic trauma spelling contrast) to an acute febrile pulmonary sepsis presentation with diaphoresis, rigors, and hemoptysis (dg-06, dose=1).
- **`sc-043`** (extends `ag-042`, `misspelled_everyday`, `otolaryngology_infectious`): Extends ag-042 (chronic pulmonary cough spelling contrast) to an acute febrile upper-airway obstruction presentation using OAC CHV typo 'coughhing' (dg-07, dose=1).
- **`sc-044`** (extends `ag-041`, `misspelled_everyday`, `otolaryngology_neurology`): Extends ag-041 (CNS infection spelling contrast) to an acute otolaryngological/intracranial infection emergency (coalescent mastoiditis) using OAC CHV typo 'hearring' (dg-08, dose=1).
- **`sc-045`** (extends `ag-043`, `misspelled_everyday`, `allergy_immunology`): Extends ag-043 (clinical-term spelling contrast) to an acute medication-induced lingual angioedema and mucocutaneous blistering emergency using 'tounge' (dg-09, dose=1).
- **`sc-046`** (extends `ag-044`, `misspelled_everyday`, `gastroenterology_surgery`): Extends ag-044 (hepatitis spelling contrast, Tier 2) to an acute surgical abdomen with board-hard rigidity, painful belly bulging, and diaphoresis (Tier 4, dg-10, dose=1).
- **`sc-047`** (extends `ag-049`, `misspelled_multiple`, `obstetrics_gynecology`): Extends ag-049 (and pairs with sc-037 in dose_group dg-01) by testing 3 simultaneous OAC CHV everyday misspellings ('bleedding', 'acheing', 'dizzyness') in early-pregnancy hemorrhage.
- **`sc-048`** (extends `ag-047`, `misspelled_multiple`, `gastroenterology`): Extends ag-047 (and pairs with sc-038 in dose_group dg-02) by testing 3 simultaneous everyday misspellings ('vomitting', 'stomache', 'bleedding') in acute GI hemorrhage.
- **`sc-049`** (extends `ag-048`, `misspelled_multiple`, `nephrology_urology`): Extends ag-048 (and pairs with sc-039 in dose_group dg-03) by testing 3 simultaneous OAC CHV everyday misspellings ('shiverring', 'acheing', 'vomitting').
- **`sc-050`** (extends `ag-042`, `misspelled_multiple`, `allergy_immunology`): Extends ag-042 (and pairs with sc-040 in dose_group dg-04) by testing 3 simultaneous OAC CHV everyday misspellings ('itchhing', 'chokeing', 'dizzyness') in acute anaphylaxis.
- **`sc-051`** (extends `ag-041`, `misspelled_multiple`, `infectious_disease_dermatology`): Extends ag-041 (and pairs with sc-041 in dose_group dg-05) by testing 3 simultaneous OAC CHV everyday misspellings ('inflammed', 'blisterring', 'shiverring').
- **`sc-052`** (extends `ag-050`, `misspelled_multiple`, `pulmonology_infectious`): Extends ag-050 (and pairs with sc-042 in dose_group dg-06) by testing 3 simultaneous OAC CHV everyday misspellings ('sweatting', 'shakeing', 'coughhing').
- **`sc-053`** (extends `ag-042`, `misspelled_multiple`, `otolaryngology_infectious`): Extends ag-042 (and pairs with sc-043 in dose_group dg-07) by testing 3 simultaneous OAC CHV everyday misspellings ('coughhing', 'chokeing', 'inflammed').
- **`sc-054`** (extends `ag-041`, `misspelled_multiple`, `otolaryngology_neurology`): Extends ag-041 (and pairs with sc-044 in dose_group dg-08) by testing 3 simultaneous OAC CHV everyday misspellings ('hearring', 'bulgeing', 'shakeing').
- **`sc-055`** (extends `ag-043`, `misspelled_multiple`, `allergy_immunology`): Extends ag-043 (and pairs with sc-045 in dose_group dg-09) by testing 3 simultaneous everyday misspellings ('tounge', 'itchhing', 'blisterring') in acute airway/mucosal drug reaction.
- **`sc-056`** (extends `ag-044`, `misspelled_multiple`, `gastroenterology_surgery`): Extends ag-044 (and pairs with sc-046 in dose_group dg-10) by testing 3 simultaneous everyday misspellings ('stomache', 'bulgeing', 'sweatting') in acute surgical abdomen.

---

## 5. Fact-Parity & Order Table for Every Pair (`sc-001`–`sc-056`)

### `sc-001` (extends `ag-001` — `red_flag_everyday` — `pulmonology_thoracic`)
- **Clinical difference from `ag-001`**: Extends ag-001 (cardiac chest pressure radiating to jaw with diaphoresis) to a pulmonary/pleural emergency (sudden unilateral pleuritic chest pain with resting dyspnea).
- **`top_prompt`** (20w): `Suddenly I got unilateral pleuritic chest pain and I am dyspneic at rest, so I need to go to the`
- **`bottom_prompt`** (29w): `Suddenly I got sharp pain on one side of my chest when I breathe in and I'm short of breath sitting still, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "unilateral pleuritic chest pain and I am dyspneic at rest", "patient_span": "sharp pain on one side of my chest when I breathe in and I'm short of breath sitting still"}`
- **Tier 4 justification**: Sudden-onset unilateral pleuritic chest pain with resting dyspnea requires immediate emergency department evaluation to rule out spontaneous pneumothorax or pulmonary embolism (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Sudden onset | `Suddenly I got` | `Suddenly I got` |
| 2 | Unilateral pleuritic chest pain / sharp pain on one side of chest when breathing in | `unilateral pleuritic chest pain` | `sharp pain on one side of my chest when I breathe in` |
| 3 | Dyspneic at rest / short of breath sitting still | `and I am dyspneic at rest` | `and I'm short of breath sitting still` |

### `sc-002` (extends `ag-002` — `red_flag_everyday` — `gastroenterology_surgery`)
- **Clinical difference from `ag-002`**: Extends ag-002 (vascular interscapular tearing pain) to a gastrointestinal/thoracic surgical emergency (post-emetic esophageal rupture with cervical subcutaneous crepitus).
- **`top_prompt`** (19w): `After violent retching I got retrosternal chest pain and subcutaneous cervical crepitus, so I need to get to the`
- **`bottom_prompt`** (26w): `After violent retching I got deep center chest pain and a crackly feeling under the skin of my neck, so I need to get to the`
- **`swap_spans`**: `{"clinical_span": "retrosternal chest pain and subcutaneous cervical crepitus", "patient_span": "deep center chest pain and a crackly feeling under the skin of my neck"}`
- **Tier 4 justification**: Post-emetic retrosternal pain accompanied by cervical subcutaneous crepitus indicates transmural esophageal perforation (Boerhaave syndrome) requiring immediate emergency surgical care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: after violent retching | `After violent retching I got` | `After violent retching I got` |
| 2 | Retrosternal / deep center chest pain | `retrosternal chest pain` | `deep center chest pain` |
| 3 | Subcutaneous cervical crepitus / crackly feeling under neck skin | `and subcutaneous cervical crepitus` | `and a crackly feeling under the skin of my neck` |

### `sc-003` (extends `ag-003` — `red_flag_everyday` — `neurology`)
- **Clinical difference from `ag-003`**: Extends ag-003 (posterior-circulation diplopia and gait ataxia) to an anterior-circulation hemispheric stroke presentation (left arm weakness and expressive aphasia).
- **`top_prompt`** (19w): `Fifteen minutes ago I suddenly developed left arm hemiparesis and expressive aphasia, so I need to go to the`
- **`bottom_prompt`** (22w): `Fifteen minutes ago I suddenly developed left arm weakness and inability to get words out, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "left arm hemiparesis and expressive aphasia", "patient_span": "left arm weakness and inability to get words out"}`
- **Tier 4 justification**: Acute-onset unilateral arm weakness and expressive aphasia are anterior-circulation stroke signs requiring immediate emergency department stroke activation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset fifteen minutes ago, sudden | `Fifteen minutes ago I suddenly developed` | `Fifteen minutes ago I suddenly developed` |
| 2 | Left arm hemiparesis / weakness | `left arm hemiparesis` | `left arm weakness` |
| 3 | Expressive aphasia / inability to get words out | `and expressive aphasia` | `and inability to get words out` |

### `sc-004` (extends `ag-005` — `red_flag_everyday` — `infectious_disease_dermatology`)
- **Clinical difference from `ag-005`**: Extends ag-005 (urinary tract sepsis with rigors and confusion) to a soft-tissue surgical infection emergency (necrotizing infection signs on the lower leg).
- **`top_prompt`** (26w): `On my swollen calf I developed rapidly spreading erythema, hemorrhagic bullae, and pain out of proportion to skin findings, so I need to go to the`
- **`bottom_prompt`** (26w): `On my swollen calf I developed fast-spreading redness, purple blood blisters, and pain much worse than the skin looks, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "rapidly spreading erythema, hemorrhagic bullae, and pain out of proportion to skin findings", "patient_span": "fast-spreading redness, purple blood blisters, and pain much worse than the skin looks"}`
- **Tier 4 justification**: Rapidly spreading lower-extremity erythema with hemorrhagic bullae and pain out of proportion to skin findings indicates necrotizing fasciitis requiring immediate emergency surgical exploration (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Location: on swollen calf | `On my swollen calf I developed` | `On my swollen calf I developed` |
| 2 | Rapidly spreading erythema / redness | `rapidly spreading erythema` | `fast-spreading redness` |
| 3 | Hemorrhagic bullae / purple blood blisters | `hemorrhagic bullae` | `purple blood blisters` |
| 4 | Pain out of proportion to skin findings / much worse than the skin looks | `and pain out of proportion to skin findings` | `and pain much worse than the skin looks` |

### `sc-005` (extends `ag-006` — `red_flag_everyday` — `otolaryngology_infectious`)
- **Clinical difference from `ag-006`**: Extends ag-006 (bacterial meningitis triad) to an acute infectious upper-airway emergency (febrile muffled dysphonia, sialorrhea, and inability to swallow liquids).
- **`top_prompt`** (22w): `With a high fever today I developed muffled dysphonia, sialorrhea, and inability to swallow liquids, so I need to go to the`
- **`bottom_prompt`** (23w): `With a high fever today I developed a muffled voice, drooling, and inability to swallow liquids, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "muffled dysphonia, sialorrhea, and inability to swallow liquids", "patient_span": "a muffled voice, drooling, and inability to swallow liquids"}`
- **Tier 4 justification**: High fever accompanied by muffled dysphonia, sialorrhea, and inability to swallow liquids signals impending upper-airway obstruction from epiglottitis or retropharyngeal abscess (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today I developed` | `With a high fever today I developed` |
| 2 | Muffled dysphonia / muffled voice | `muffled dysphonia` | `a muffled voice` |
| 3 | Sialorrhea / drooling | `sialorrhea` | `drooling` |
| 4 | Inability to swallow liquids | `and inability to swallow liquids` | `and inability to swallow liquids` |

### `sc-006` (extends `ag-007` — `red_flag_everyday` — `vascular_orthopedics`)
- **Clinical difference from `ag-007`**: Extends ag-007 (food-triggered anaphylaxis airway emergency) to a limb-threatening orthopedic/vascular emergency (post-cast acute compartment syndrome).
- **`top_prompt`** (24w): `In my leg cast today I developed severe calf pain on passive toe stretch and toe paresthesias, so I need to go to the`
- **`bottom_prompt`** (26w): `In my leg cast today I developed severe calf pain when someone bends my toes back and tingling toes, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "severe calf pain on passive toe stretch and toe paresthesias", "patient_span": "severe calf pain when someone bends my toes back and tingling toes"}`
- **Tier 4 justification**: Severe calf pain on passive toe extension accompanied by distal paresthesias inside a leg cast indicates acute compartment syndrome requiring immediate emergency cast splitting (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Leg cast context today | `In my leg cast today I developed` | `In my leg cast today I developed` |
| 2 | Severe calf pain on passive toe stretch | `severe calf pain on passive toe stretch` | `severe calf pain when someone bends my toes back` |
| 3 | Toe paresthesias / tingling toes | `and toe paresthesias` | `and tingling toes` |

### `sc-007` (extends `ag-011` — `red_flag_everyday` — `vascular_gastroenterology`)
- **Clinical difference from `ag-011`**: Extends ag-011 (upper GI hemorrhage with hematemesis and melena) to an acute intestinal vascular emergency (mesenteric ischemia with pain out of proportion and bloody stools).
- **`top_prompt`** (22w): `After dinner I developed severe periumbilical pain out of proportion to exam and bloody stools, so I need to go to the`
- **`bottom_prompt`** (23w): `After dinner I developed severe belly-button pain much worse than my belly looks and bloody stools, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "severe periumbilical pain out of proportion to exam and bloody stools", "patient_span": "severe belly-button pain much worse than my belly looks and bloody stools"}`
- **Tier 4 justification**: Severe periumbilical pain out of proportion to physical appearance/exam accompanied by bloody stools indicates acute mesenteric ischemia requiring immediate emergency CT angiography (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Timing: after dinner | `After dinner I developed` | `After dinner I developed` |
| 2 | Severe periumbilical pain out of proportion / much worse than belly looks | `severe periumbilical pain out of proportion to exam` | `severe belly-button pain much worse than my belly looks` |
| 3 | Bloody stools | `and bloody stools` | `and bloody stools` |

### `sc-008` (extends `ag-014` — `red_flag_everyday` — `ophthalmology_neurology`)
- **Clinical difference from `ag-014`**: Extends ag-014 (spinal cauda equina compression) to a neuro-ophthalmic infectious emergency (orbital cellulitis / cavernous sinus thrombosis signs).
- **`top_prompt`** (20w): `With my sinus infection and fever I developed painful unilateral proptosis and ophthalmoplegia, so I need to go to the`
- **`bottom_prompt`** (23w): `With my sinus infection and fever I developed a painful bulging eye and frozen eye movement, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "painful unilateral proptosis and ophthalmoplegia", "patient_span": "a painful bulging eye and frozen eye movement"}`
- **Tier 4 justification**: Sinusitis with fever, painful proptosis, and restricted extraocular movement indicates orbital cellulitis or cavernous sinus thrombosis requiring immediate emergency IV antibiotics and imaging (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Sinus infection and fever context | `With my sinus infection and fever I developed` | `With my sinus infection and fever I developed` |
| 2 | Painful proptosis / bulging eye | `painful unilateral proptosis` | `a painful bulging eye` |
| 3 | Ophthalmoplegia / frozen eye movement | `and ophthalmoplegia` | `and frozen eye movement` |

### `sc-009` (extends `ag-018` — `minimizing_hedged` — `neurology`)
- **Clinical difference from `ag-018`**: Extends ag-018 (transient monocular visual loss in right eye) to a hemispheric sensorimotor TIA presentation (ten-minute unilateral arm numbness and clumsiness).
- **`top_prompt`** (19w): `For ten minutes this morning my right arm went numb and clumsy, so I need to go to the`
- **`bottom_prompt`** (23w): `It's probably nothing, but for ten minutes this morning my right arm went numb and clumsy, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "", "patient_span": "It's probably nothing, but "}`
- **Tier 4 justification**: A transient ten-minute episode of unilateral upper-extremity numbness and clumsiness represents a sensorimotor transient ischemic attack requiring immediate emergency evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Ten-minute duration this morning | `For ten minutes this morning` | `for ten minutes this morning` |
| 2 | Right arm numbness and clumsiness | `my right arm went numb and clumsy` | `my right arm went numb and clumsy` |

### `sc-010` (extends `ag-019` — `minimizing_hedged` — `oncology_urology`)
- **Clinical difference from `ag-019`**: Extends ag-019 (supraclavicular collarbone lump with night sweats) to a genitourinary oncology presentation (firm painless intratesticular mass).
- **`top_prompt`** (18w): `In the shower I felt a firm painless lump inside one testicle, so I need to see a`
- **`bottom_prompt`** (22w): `It's probably nothing, but in the shower I felt a firm painless lump inside one testicle, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "", "patient_span": "It's probably nothing, but "}`
- **Tier 2 justification**: A firm painless intratesticular mass requires prompt medical evaluation and diagnostic scrotal ultrasonography to rule out testicular malignancy (Tier 2).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Context: in the shower | `In the shower` | `in the shower` |
| 2 | Firm painless lump inside one testicle | `I felt a firm painless lump inside one testicle` | `I felt a firm painless lump inside one testicle` |

### `sc-011` (extends `ag-020` — `minimizing_hedged` — `otolaryngology_oncology`)
- **Clinical difference from `ag-020`**: Extends ag-020 (gastroenterology solid-food dysphagia) to a head-and-neck oncology alarm presentation (six weeks of hoarseness with a neck mass, targeting ' otolaryngologist').
- **`top_prompt`** (19w): `For six weeks my voice has been hoarse with a lump in my neck, so I should see an`
- **`bottom_prompt`** (23w): `It's probably nothing, but for six weeks my voice has been hoarse with a lump in my neck, so I should see an`
- **`swap_spans`**: `{"clinical_span": "", "patient_span": "It's probably nothing, but "}`
- **Tier 3 justification**: Hoarseness persisting for six weeks alongside a palpable neck mass requires specialist otolaryngological laryngoscopy to exclude laryngeal malignancy (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Six-week duration | `For six weeks` | `for six weeks` |
| 2 | Hoarse voice with a neck lump | `my voice has been hoarse with a lump in my neck` | `my voice has been hoarse with a lump in my neck` |

### `sc-012` (extends `ag-021` — `minimizing_hedged` — `urology_emergency`)
- **Clinical difference from `ag-021`**: Extends ag-021 using the owner's corrected Tier 4 emergency level (ending on ' ER' rather than Tier 3 ' urologist', with clot passage and orthostatic dizziness).
- **`top_prompt`** (21w): `Today I passed dark blood clots in my pee twice and felt dizzy standing, so I need to go to the`
- **`bottom_prompt`** (25w): `It's probably nothing, but today I passed dark blood clots in my pee twice and felt dizzy standing, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "", "patient_span": "It's probably nothing, but "}`
- **Tier 4 justification**: Passing blood clots in the urine accompanied by orthostatic dizziness requires immediate emergency department evaluation for clot retention and acute blood loss (Tier 4, per owner's retier of ag-021).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Timing: today | `Today` | `today` |
| 2 | Passed dark blood clots in urine twice with dizziness standing | `I passed dark blood clots in my pee twice and felt dizzy standing` | `I passed dark blood clots in my pee twice and felt dizzy standing` |

### `sc-013` (extends `ag-027` — `minimizing_hedged` — `pulmonology_oncology`)
- **Clinical difference from `ag-027`**: Extends ag-027 using the owner's corrected Tier 3 specialist level (ending on ' pulmonologist' rather than Tier 2 ' doctor').
- **`top_prompt`** (21w): `For a month I have lost weight without trying and coughed up streaks of blood, so I need to see a`
- **`bottom_prompt`** (25w): `It's probably nothing, but for a month I have lost weight without trying and coughed up streaks of blood, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "", "patient_span": "It's probably nothing, but "}`
- **Tier 3 justification**: One month of unintentional weight loss accompanied by hemoptysis warrants specialist pulmonary evaluation with chest CT and bronchoscopy (Tier 3, per owner's retier of ag-027).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | One-month duration and unintentional weight loss | `For a month I have lost weight without trying` | `for a month I have lost weight without trying` |
| 2 | Coughed up streaks of blood | `and coughed up streaks of blood` | `and coughed up streaks of blood` |

### `sc-014` (extends `ag-028` — `minimizing_hedged` — `neurology`)
- **Clinical difference from `ag-028`**: Extends ag-028 (lower-extremity foot drop) to an acute neurovascular cranial-nerve III palsy presentation at Tier 4 (' ER').
- **`top_prompt`** (16w): `Today my left eyelid has drooped with double vision, so I need to go to the`
- **`bottom_prompt`** (20w): `It's probably nothing, but today my left eyelid has drooped with double vision, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "", "patient_span": "It's probably nothing, but "}`
- **Tier 4 justification**: Acute-onset unilateral eyelid ptosis accompanied by diplopia is an acute third cranial nerve palsy presentation requiring emergency neuroimaging to exclude a posterior communicating artery aneurysm (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset today | `Today` | `today` |
| 2 | Left eyelid droop with double vision | `my left eyelid has drooped with double vision` | `my left eyelid has drooped with double vision` |

### `sc-015` (extends `ag-029` — `metaphor_idiom` — `neurology`)
- **Clinical difference from `ag-029`**: Extends ag-029 (cardiac 'heavy weight' chest pressure metaphor) to the classic neurological subarachnoid hemorrhage patient metaphor ('like a baseball bat hit my skull').
- **`top_prompt`** (17w): `With neck stiffness I suddenly got an explosive occipital headache, so I need to go to the`
- **`bottom_prompt`** (22w): `With neck stiffness I suddenly got a headache like a baseball bat hit my skull, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "an explosive occipital headache", "patient_span": "a headache like a baseball bat hit my skull"}`
- **Tier 4 justification**: An abrupt explosive headache accompanied by neck stiffness requires immediate emergency neuroimaging for subarachnoid hemorrhage (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Neck stiffness and sudden onset | `With neck stiffness I suddenly got` | `With neck stiffness I suddenly got` |
| 2 | Explosive headache / 'like a baseball bat hit my skull' | `an explosive occipital headache` | `a headache like a baseball bat hit my skull` |

### `sc-016` (extends `ag-031` — `metaphor_idiom` — `urology_nephrology`)
- **Clinical difference from `ag-031`**: Extends ag-031 using the owner's corrected Tier 3 specialist level (' urologist') and shifts from dysuria to obstructing renal colic with hematuria.
- **`top_prompt`** (18w): `In my right flank I have recurrent renal colic and gross hematuria, so I need to see a`
- **`bottom_prompt`** (22w): `In my right flank I have waves of knife-twisting pain and pink blood in my pee, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "recurrent renal colic and gross hematuria", "patient_span": "waves of knife-twisting pain and pink blood in my pee"}`
- **Tier 3 justification**: Severe colicky flank pain accompanied by gross hematuria warrants specialist urological evaluation and urinary-tract imaging for obstructing urolithiasis (Tier 3, per owner's retier of ag-031).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Right flank location | `In my right flank I have` | `In my right flank I have` |
| 2 | Recurrent renal colic / waves of knife-twisting pain | `recurrent renal colic` | `waves of knife-twisting pain` |
| 3 | Gross hematuria / pink blood in urine | `and gross hematuria` | `and pink blood in my pee` |

### `sc-017` (extends `ag-032` — `metaphor_idiom` — `cardiology_pulmonology`)
- **Clinical difference from `ag-032`**: Extends ag-032 (asthma 'breathing through a straw' metaphor) to cardiogenic flash pulmonary edema ('feeling of drowning' with pink frothy sputum).
- **`top_prompt`** (21w): `At 2 a.m. I woke up with acute nocturnal dyspnea and frothy pink sputum, so I need to go to the`
- **`bottom_prompt`** (23w): `At 2 a.m. I woke up with a feeling of drowning and coughing up pink foam, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "acute nocturnal dyspnea and frothy pink sputum", "patient_span": "a feeling of drowning and coughing up pink foam"}`
- **Tier 4 justification**: Abrupt nocturnal air hunger accompanied by frothy pink sputum indicates acute cardiogenic pulmonary edema requiring immediate emergency respiratory and vasodilator support (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Woke up at 2 a.m. | `At 2 a.m. I woke up with` | `At 2 a.m. I woke up with` |
| 2 | Acute nocturnal dyspnea / feeling of drowning | `acute nocturnal dyspnea` | `a feeling of drowning` |
| 3 | Frothy pink sputum / coughing up pink foam | `and frothy pink sputum` | `and coughing up pink foam` |

### `sc-018` (extends `ag-034` — `metaphor_idiom` — `otolaryngology_neurology`)
- **Clinical difference from `ag-034`**: Extends ag-034 using the owner's corrected Tier 3 specialist level (' otolaryngologist') and shifts from positional bed vertigo to inner-ear vertigo with unilateral tinnitus and hearing loss.
- **`top_prompt`** (19w): `Three times this week I had episodic rotational vertigo, unilateral tinnitus, and hearing loss, so I should see an`
- **`bottom_prompt`** (21w): `Three times this week I had the room spinning in circles, ear roaring, and muffled hearing, so I should see an`
- **`swap_spans`**: `{"clinical_span": "episodic rotational vertigo, unilateral tinnitus, and hearing loss", "patient_span": "the room spinning in circles, ear roaring, and muffled hearing"}`
- **Tier 3 justification**: Recurrent episodes of rotational vertigo accompanied by unilateral tinnitus and hearing loss point to inner-ear pathology (Meniere's disease) warranting specialist otolaryngology evaluation (Tier 3, per owner's retier of ag-034).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Frequency: three times this week | `Three times this week I had` | `Three times this week I had` |
| 2 | Rotational vertigo / room spinning in circles | `episodic rotational vertigo` | `the room spinning in circles` |
| 3 | Tinnitus / ear roaring | `unilateral tinnitus` | `ear roaring` |
| 4 | Hearing loss / muffled hearing | `and hearing loss` | `and muffled hearing` |

### `sc-019` (extends `ag-037` — `metaphor_idiom` — `neurology_spine`)
- **Clinical difference from `ag-037`**: Extends ag-037 (facial trigeminal neuralgia triggered by wind) to cervical spinal cord Lhermitte's phenomenon triggered by neck flexion.
- **`top_prompt`** (23w): `When I bend my neck forward I get electric-like paresthesias radiating down my spine into both legs, so I need to see a`
- **`bottom_prompt`** (24w): `When I bend my neck forward I get an electric shock shooting down my spine into both legs, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "electric-like paresthesias radiating down my spine into both legs", "patient_span": "an electric shock shooting down my spine into both legs"}`
- **Tier 3 justification**: Neck-flexion-induced electric-shock paresthesias radiating down the spine into both legs (Lhermitte's phenomenon) indicate cervical spinal cord pathology requiring specialist neurological MRI evaluation (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: bending neck forward | `When I bend my neck forward I get` | `When I bend my neck forward I get` |
| 2 | Electric-like shock radiating down spine into both legs | `electric-like paresthesias radiating down my spine into both legs` | `an electric shock shooting down my spine into both legs` |

### `sc-020` (extends `ag-052` — `dialect_non_native` — `neurology`)
- **Clinical difference from `ag-052`**: Extends ag-052 (cardiogenic syncope with chest tightness at work) to a neurological generalized convulsion with postictal confusion.
- **`top_prompt`** (19w): `At church today I had a generalized tonic-clonic convulsion with postictal confusion, so I need to go to the`
- **`bottom_prompt`** (24w): `At church today I had a full-body shaking spell where I fell out and woke up confused, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "a generalized tonic-clonic convulsion with postictal confusion", "patient_span": "a full-body shaking spell where I fell out and woke up confused"}`
- **Tier 4 justification**: An unprovoked generalized tonic-clonic convulsion with postictal confusion requires immediate emergency department neuroimaging and metabolic evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Setting: at church today | `At church today I had` | `At church today I had` |
| 2 | Generalized tonic-clonic convulsion / full-body shaking spell with loss of consciousness | `a generalized tonic-clonic convulsion` | `a full-body shaking spell where I fell out` |
| 3 | Postictal confusion / waking up confused | `with postictal confusion` | `and woke up confused` |

### `sc-021` (extends `ag-053` — `dialect_non_native` — `pulmonology`)
- **Clinical difference from `ag-053`**: Extends ag-053 (heart failure orthopnea targeting ' cardiologist') to chronic obstructive pulmonary symptoms targeting ' pulmonologist'.
- **`top_prompt`** (19w): `All winter I have had chronic productive cough, exertional dyspnea, and expiratory wheezing, so I need to see a`
- **`bottom_prompt`** (23w): `All winter I have had a deep rattling cough, getting short-winded on stairs, and tight whistling breath, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "chronic productive cough, exertional dyspnea, and expiratory wheezing", "patient_span": "a deep rattling cough, getting short-winded on stairs, and tight whistling breath"}`
- **Tier 3 justification**: Chronic productive cough accompanied by exertional dyspnea and wheezing warrants specialist pulmonary evaluation and spirometry for obstructive airway disease (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Duration: all winter | `All winter I have had` | `All winter I have had` |
| 2 | Productive / deep rattling cough | `chronic productive cough` | `a deep rattling cough` |
| 3 | Exertional dyspnea / short-winded on stairs | `exertional dyspnea` | `getting short-winded on stairs` |
| 4 | Expiratory wheezing / tight whistling breath | `and expiratory wheezing` | `and tight whistling breath` |

### `sc-022` (extends `ag-055` — `dialect_non_native` — `gastroenterology_surgery`)
- **Clinical difference from `ag-055`**: Extends ag-055 (post-prandial epigastric biliary pain, Tier 2) to acute surgical appendicitis with migrating right-lower-quadrant pain and fever (Tier 4).
- **`top_prompt`** (22w): `Since last night I have umbilical pain migrating to my right lower abdomen with fever, so I need to go to the`
- **`bottom_prompt`** (25w): `Since last night I have pain moving from my belly button to my low right side with fever, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "umbilical pain migrating to my right lower abdomen with fever", "patient_span": "pain moving from my belly button to my low right side with fever"}`
- **Tier 4 justification**: Abdominal pain migrating from the umbilical region to the right lower quadrant with fever is the classic presentation of acute appendicitis requiring emergency evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since last night | `Since last night I have` | `Since last night I have` |
| 2 | Umbilical pain migrating to right lower abdomen | `umbilical pain migrating to my right lower abdomen` | `pain moving from my belly button to my low right side` |
| 3 | Fever | `with fever` | `with fever` |

### `sc-023` (extends `ag-056` — `dialect_non_native` — `neurology_infectious`)
- **Clinical difference from `ag-056`**: Extends ag-056 (L2 cardiac chest pressure and dyspnea) to an acute central nervous system emergency (occipital headache, neck stiffness, and confusion).
- **`top_prompt`** (19w): `Since this morning I have severe occipital headache, nuchal rigidity, and confusion, so I need to go to the`
- **`bottom_prompt`** (22w): `Since this morning I have severe back-of-head pain, neck too stiff to bend, and confusion, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "severe occipital headache, nuchal rigidity, and confusion", "patient_span": "severe back-of-head pain, neck too stiff to bend, and confusion"}`
- **Tier 4 justification**: Acute severe occipital headache with nuchal rigidity and confusion requires immediate emergency department evaluation for bacterial meningitis or subarachnoid hemorrhage (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since this morning | `Since this morning I have` | `Since this morning I have` |
| 2 | Severe occipital headache / back-of-head pain | `severe occipital headache` | `severe back-of-head pain` |
| 3 | Nuchal rigidity / neck too stiff to bend | `nuchal rigidity` | `neck too stiff to bend` |
| 4 | Acute confusion | `and confusion` | `and confusion` |

### `sc-024` (extends `ag-057` — `dialect_non_native` — `neurology`)
- **Clinical difference from `ag-057`**: Extends ag-057 (anterior-circulation facial droop and arm weakness) to a posterior-circulation visual-field and gait stroke presentation in L2 phrasing.
- **`top_prompt`** (19w): `At dinner I suddenly noticed right visual field loss and gait ataxia, so I need to go to the`
- **`bottom_prompt`** (21w): `At dinner I suddenly noticed my right-side sight gone and my legs walking crooked, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "right visual field loss and gait ataxia", "patient_span": "my right-side sight gone and my legs walking crooked"}`
- **Tier 4 justification**: Sudden visual field loss accompanied by gait ataxia indicates an acute posterior-circulation stroke requiring immediate emergency neuroimaging (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset at dinner, sudden | `At dinner I suddenly noticed` | `At dinner I suddenly noticed` |
| 2 | Right visual field loss / right-side sight gone | `right visual field loss` | `my right-side sight gone` |
| 3 | Gait ataxia / legs walking crooked | `and gait ataxia` | `and my legs walking crooked` |

### `sc-025` (extends `ag-057` — `dialect_non_native` — `hepatology`)
- **Clinical difference from `ag-057`**: Extends ag-057 (heart failure lower-leg fluid retention) to cirrhotic hepatic decompensation with progressive ascites, jaundice, and asterixis.
- **`top_prompt`** (19w): `With my cirrhosis today I developed progressive ascites, scleral icterus, and asterixis, so I need to go to the`
- **`bottom_prompt`** (24w): `With my cirrhosis today I developed growing water swelling in my belly, yellow eyes, and flapping hands, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "progressive ascites, scleral icterus, and asterixis", "patient_span": "growing water swelling in my belly, yellow eyes, and flapping hands"}`
- **Tier 4 justification**: Cirrhosis complicated by progressive ascites, jaundice, and asterixis indicates acute hepatic encephalopathy and decompensation requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Cirrhosis context today | `With my cirrhosis today I developed` | `With my cirrhosis today I developed` |
| 2 | Progressive ascites / growing water swelling in belly | `progressive ascites` | `growing water swelling in my belly` |
| 3 | Scleral icterus / yellow eyes | `scleral icterus` | `yellow eyes` |
| 4 | Asterixis / flapping hands | `and asterixis` | `and flapping hands` |

### `sc-026` (extends `ag-063` — `context_raises_urgency` — `hematology_orthopedics`)
- **Clinical difference from `ag-063`**: Extends ag-063 (head trauma on anticoagulants) to a congenital bleeding-disorder musculoskeletal emergency (acute spontaneous knee hemarthrosis in hemophilia).
- **`top_prompt`** (21w): `Today with severe knee pain I developed an acute spontaneous hemarthrosis while having hemophilia, so I need to go to the`
- **`bottom_prompt`** (26w): `Today with severe knee pain I got a knee that swelled up fast without any injury while having hemophilia, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "developed an acute spontaneous hemarthrosis while having hemophilia", "patient_span": "got a knee that swelled up fast without any injury while having hemophilia"}`
- **Tier 4 justification**: Immediate factor VIII/IX replacement in the emergency department is required for acute spontaneous hemarthrosis in hemophilia (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset today with severe knee pain | `Today with severe knee pain I` | `Today with severe knee pain I` |
| 2 | Acute spontaneous hemarthrosis / knee that swelled up fast without any injury | `developed an acute spontaneous hemarthrosis` | `got a knee that swelled up fast without any injury` |
| 3 | Hemophilia context | `while having hemophilia` | `while having hemophilia` |

### `sc-027` (extends `ag-064` — `context_raises_urgency` — `surgery_infectious`)
- **Clinical difference from `ag-064`**: Extends ag-064 (post-chemotherapy febrile neutropenia) to surgical asplenia / overwhelming post-splenectomy infection (OPSI).
- **`top_prompt`** (23w): `Five years after my splenectomy I developed sudden pyrexia of 102.4 Fahrenheit, rigors, and orthostatic dizziness, so I need to go to the`
- **`bottom_prompt`** (25w): `Five years after my splenectomy I developed a sudden 102.4 Fahrenheit fever, shaking chills, and dizziness when standing, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "sudden pyrexia of 102.4 Fahrenheit, rigors, and orthostatic dizziness", "patient_span": "a sudden 102.4 Fahrenheit fever, shaking chills, and dizziness when standing"}`
- **Tier 4 justification**: Fever, rigors, and orthostatic dizziness in an asplenic patient carry a high risk of fulminant encapsulated-bacterial sepsis (OPSI) requiring immediate emergency parenteral antibiotics (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Post-splenectomy context | `Five years after my splenectomy I developed` | `Five years after my splenectomy I developed` |
| 2 | Sudden fever of 102.4 Fahrenheit | `sudden pyrexia of 102.4 Fahrenheit` | `a sudden 102.4 Fahrenheit fever` |
| 3 | Rigors / shaking chills | `rigors` | `shaking chills` |
| 4 | Orthostatic dizziness / dizziness when standing | `and orthostatic dizziness` | `and dizziness when standing` |

### `sc-028` (extends `ag-065` — `context_raises_urgency` — `pediatrics_pulmonology`)
- **Clinical difference from `ag-065`**: Extends ag-065 (neonatal fever at 19 days old) to an acute pediatric respiratory failure presentation (retractions and cyanosis at 4 weeks old).
- **`top_prompt`** (19w): `Right now my four-week-old infant has subcostal retractions and cyanotic lips, so I need to take him to the`
- **`bottom_prompt`** (20w): `Right now my four-week-old baby has ribs sucking in and blue lips, so I need to take him to the`
- **`swap_spans`**: `{"clinical_span": "infant has subcostal retractions and cyanotic lips", "patient_span": "baby has ribs sucking in and blue lips"}`
- **Tier 4 justification**: Retractions and cyanotic lips in a four-week-old infant indicate life-threatening respiratory distress requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Timing and age: right now, four-week-old | `Right now my four-week-old` | `Right now my four-week-old` |
| 2 | Infant / baby | `infant` | `baby` |
| 3 | Subcostal retractions / ribs sucking in | `has subcostal retractions` | `has ribs sucking in` |
| 4 | Cyanotic / blue lips | `and cyanotic lips` | `and blue lips` |

### `sc-029` (extends `ag-067` — `context_raises_urgency` — `geriatrics_orthopedics`)
- **Clinical difference from `ag-067`**: Extends ag-067 (geriatric delirium and falls at age 83) to a geriatric orthopedic trauma emergency (displaced femoral neck fracture at age 81).
- **`top_prompt`** (25w): `At eighty-one after a fall I have groin pain, inability to walk, and a shortened externally rotated leg, so I need to go to the`
- **`bottom_prompt`** (24w): `At eighty-one after a fall I have groin pain, inability to walk, and a shorter outward-turned leg, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "groin pain, inability to walk, and a shortened externally rotated leg", "patient_span": "groin pain, inability to walk, and a shorter outward-turned leg"}`
- **Tier 4 justification**: Inability to walk with a shortened, externally rotated lower extremity after a fall in an 81-year-old indicates an acute hip fracture requiring emergency hospital admission (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Age and mechanism: age 81 after a fall | `At eighty-one after a fall I have` | `At eighty-one after a fall I have` |
| 2 | Groin pain | `groin pain` | `groin pain` |
| 3 | Inability to walk | `inability to walk` | `inability to walk` |
| 4 | Shortened externally rotated leg | `and a shortened externally rotated leg` | `and a shorter outward-turned leg` |

### `sc-030` (extends `ag-069` — `context_raises_urgency` — `hematology_neurology`)
- **Clinical difference from `ag-069`**: Extends ag-069 (adult sickle-cell acute chest syndrome) to a pediatric sickle-cell neurological emergency (acute ischemic stroke requiring exchange transfusion).
- **`top_prompt`** (20w): `With sickle cell disease my eight-year-old developed acute right hemiparesis and dysarthria, so I need to take her to the`
- **`bottom_prompt`** (21w): `With sickle cell disease my eight-year-old developed sudden right-side weakness and slurred speech, so I need to take her to the`
- **`swap_spans`**: `{"clinical_span": "acute right hemiparesis and dysarthria", "patient_span": "sudden right-side weakness and slurred speech"}`
- **Tier 4 justification**: Acute focal motor deficit and dysarthria in a child with sickle cell disease represent an acute ischemic stroke requiring emergency exchange transfusion (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Sickle cell disease in 8-year-old | `With sickle cell disease my eight-year-old developed` | `With sickle cell disease my eight-year-old developed` |
| 2 | Acute right hemiparesis / sudden right-side weakness | `acute right hemiparesis` | `sudden right-side weakness` |
| 3 | Dysarthria / slurred speech | `and dysarthria` | `and slurred speech` |

### `sc-031` (extends `ag-072` — `context_raises_urgency` — `cardiology_infectious`)
- **Clinical difference from `ag-072`**: Extends ag-072 (kidney transplant fever and graft tenderness) to a cardiac-device infectious emergency (prosthetic valve endocarditis signs).
- **`top_prompt`** (20w): `With my prosthetic heart valve I developed fever, rigors, and tender fingertip nodules, so I need to go to the`
- **`bottom_prompt`** (21w): `With my prosthetic heart valve I developed fever, shaking chills, and painful fingertip bumps, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "fever, rigors, and tender fingertip nodules", "patient_span": "fever, shaking chills, and painful fingertip bumps"}`
- **Tier 4 justification**: Fever, rigors, and painful fingertip nodules in a patient with a prosthetic heart valve indicate infective endocarditis requiring immediate hospital admission and blood cultures (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Prosthetic heart valve context | `With my prosthetic heart valve I developed` | `With my prosthetic heart valve I developed` |
| 2 | Fever | `fever` | `fever` |
| 3 | Rigors / shaking chills | `rigors` | `shaking chills` |
| 4 | Tender fingertip nodules/bumps (Osler nodes) | `and tender fingertip nodules` | `and painful fingertip bumps` |

### `sc-032` (extends `ag-074` — `medication_safety` — `endocrinology_infectious`)
- **Clinical difference from `ag-074`**: Extends ag-074 (sertraline + tramadol serotonin syndrome) to an endocrine medication-safety emergency (methimazole-induced febrile agranulocytosis).
- **`top_prompt`** (21w): `Today while taking methimazole for hyperthyroidism I developed high fever and severe ulcerative pharyngitis, so I need to go to the`
- **`bottom_prompt`** (25w): `Today while taking methimazole for hyperthyroidism I developed high fever and a severe sore throat with mouth ulcers, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "high fever and severe ulcerative pharyngitis", "patient_span": "high fever and a severe sore throat with mouth ulcers"}`
- **Tier 4 justification**: High fever with severe pharyngitis during methimazole therapy indicates antithyroid-drug agranulocytosis requiring immediate emergency department evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Today while taking methimazole for hyperthyroidism | `Today while taking methimazole for hyperthyroidism I developed` | `Today while taking methimazole for hyperthyroidism I developed` |
| 2 | High fever | `high fever` | `high fever` |
| 3 | Severe ulcerative pharyngitis / sore throat with mouth ulcers | `and severe ulcerative pharyngitis` | `and a severe sore throat with mouth ulcers` |

### `sc-033` (extends `ag-075` — `medication_safety` — `cardiology_pharmacology`)
- **Clinical difference from `ag-075`**: Extends ag-075 (abrupt prednisone withdrawal adrenal crisis) to clonidine withdrawal rebound hypertensive emergency.
- **`top_prompt`** (22w): `After stopping daily clonidine I developed blood pressure 210 over 126, severe cephalalgia, and diaphoresis, so I need to go to the`
- **`bottom_prompt`** (23w): `After stopping daily clonidine I developed blood pressure 210 over 126, severe headache, and cold sweats, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "blood pressure 210 over 126, severe cephalalgia, and diaphoresis", "patient_span": "blood pressure 210 over 126, severe headache, and cold sweats"}`
- **Tier 4 justification**: Clonidine withdrawal resulting in a blood pressure of 210/126 mmHg with severe headache and diaphoresis constitutes a rebound hypertensive emergency requiring immediate ED care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Stopped daily clonidine | `After stopping daily clonidine I developed` | `After stopping daily clonidine I developed` |
| 2 | Blood pressure 210 over 126 | `blood pressure 210 over 126` | `blood pressure 210 over 126` |
| 3 | Severe cephalalgia / headache | `severe cephalalgia` | `severe headache` |
| 4 | Diaphoresis / cold sweats | `and diaphoresis` | `and cold sweats` |

### `sc-034` (extends `ag-077` — `medication_safety` — `cardiology_nephrology`)
- **Clinical difference from `ag-077`**: Extends ag-077 (sildenafil + nitroglycerin hypotension) to a lethal electrolyte drug interaction (spironolactone + potassium supplement hyperkalemic bradycardia).
- **`top_prompt`** (20w): `Taking spironolactone with potassium pills I got ascending leg weakness and severe bradycardia, so I need to go to the`
- **`bottom_prompt`** (29w): `Taking spironolactone with potassium pills I got weakness that started in my legs and is moving up, and a very slow heartbeat, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "ascending leg weakness and severe bradycardia", "patient_span": "weakness that started in my legs and is moving up, and a very slow heartbeat"}`
- **Tier 4 justification**: Ascending muscle weakness and severe bradycardia after combining spironolactone and potassium supplements indicate life-threatening hyperkalemic cardiotoxicity requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Co-ingestion of spironolactone and potassium pills | `Taking spironolactone with potassium pills I got` | `Taking spironolactone with potassium pills I got` |
| 2 | Ascending leg weakness / weakness starting in legs and moving up | `ascending leg weakness` | `weakness that started in my legs and is moving up` |
| 3 | Severe bradycardia / very slow heartbeat | `and severe bradycardia` | `and a very slow heartbeat` |

### `sc-035` (extends `ag-080` — `medication_safety` — `neurology_dermatology`)
- **Clinical difference from `ag-080`**: Extends ag-080 (lisinopril lingual angioedema) to an anticonvulsant mucocutaneous emergency (lamotrigine-induced Stevens-Johnson syndrome).
- **`top_prompt`** (23w): `Two weeks after starting lamotrigine I developed fever, painful oral mucosal erosions, and blistering skin detachment, so I need to go to the`
- **`bottom_prompt`** (25w): `Two weeks after starting lamotrigine I developed fever, painful raw sores inside my mouth, and peeling skin blisters, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "fever, painful oral mucosal erosions, and blistering skin detachment", "patient_span": "fever, painful raw sores inside my mouth, and peeling skin blisters"}`
- **Tier 4 justification**: Fever, oral mucositis, and epidermal blistering after initiating lamotrigine indicate Stevens-Johnson syndrome requiring immediate emergency hospitalization (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Two weeks after starting lamotrigine | `Two weeks after starting lamotrigine I developed` | `Two weeks after starting lamotrigine I developed` |
| 2 | Fever | `fever` | `fever` |
| 3 | Painful oral mucosal erosions / raw mouth sores | `painful oral mucosal erosions` | `painful raw sores inside my mouth` |
| 4 | Blistering skin detachment / peeling skin blisters | `and blistering skin detachment` | `and peeling skin blisters` |

### `sc-036` (extends `ag-081` — `medication_safety` — `nephrology_cardiology`)
- **Clinical difference from `ag-081`**: Extends ag-081 (statin + clarithromycin rhabdomyolysis at Tier 2 ' doctor') to ACE-inhibitor + loop-diuretic acute prerenal kidney injury / volume depletion at Tier 2 (' doctor').
- **`top_prompt`** (22w): `Three days after starting ramipril and furosemide I developed markedly decreased urine output and orthostatic lightheadedness, so I need to call my`
- **`bottom_prompt`** (25w): `Three days after starting ramipril and furosemide I developed barely any pee all day and lightheadedness when standing up, so I need to call my`
- **`swap_spans`**: `{"clinical_span": "markedly decreased urine output and orthostatic lightheadedness", "patient_span": "barely any pee all day and lightheadedness when standing up"}`
- **Tier 2 justification**: Oliguria and orthostatic lightheadedness three days after starting an ACE inhibitor and loop diuretic warrant promptly calling the prescribing physician (' doctor', Tier 2, matching confirmed ag-081) for medication adjustment and laboratory evaluation.

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Three days after starting ramipril and furosemide | `Three days after starting ramipril and furosemide I developed` | `Three days after starting ramipril and furosemide I developed` |
| 2 | Markedly decreased urine output / barely any pee all day | `markedly decreased urine output` | `barely any pee all day` |
| 3 | Orthostatic lightheadedness / lightheadedness when standing up | `and orthostatic lightheadedness` | `and lightheadedness when standing up` |

### `sc-037` (extends `ag-049` — `misspelled_everyday` — `obstetrics_gynecology`, `dose_group=dg-01`, `misspelling_count=1`)
- **Clinical difference from `ag-049`**: Extends ag-049 (early-pregnancy hemorrhage) by testing the everyday-word typo 'bleedding' (with 'aching' and 'dizziness' held constant for dose=1 in dg-01).
- **`top_prompt`** (22w): `Early in pregnancy today I got heavy vaginal bleeding, lower belly aching, and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (22w): `Early in pregnancy today I got heavy vaginal bleedding, lower belly aching, and severe dizziness, so I need to go to the`
- **`swap_spans`**: `{"correct": "bleeding", "misspelled": "bleedding"}`
- **Tier 4 justification**: Heavy vaginal bleeding with lower abdominal pain and severe dizziness in early pregnancy requires immediate emergency evaluation for ruptured ectopic pregnancy (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Early pregnancy onset today | `Early in pregnancy today I got` | `Early in pregnancy today I got` |
| 2 | Heavy vaginal bleeding (1-word everyday spelling contrast: bleeding vs bleedding) | `heavy vaginal bleeding` | `heavy vaginal bleedding` |
| 3 | Lower belly aching | `lower belly aching` | `lower belly aching` |
| 4 | Severe dizziness | `and severe dizziness` | `and severe dizziness` |

### `sc-038` (extends `ag-047` — `misspelled_everyday` — `gastroenterology`, `dose_group=dg-02`, `misspelling_count=1`)
- **Clinical difference from `ag-047`**: Extends ag-047 (bloody vomiting and black stools) by adding crampy stomach pain and rectal bleeding as the 1-vs-3 dose baseline (dg-02, dose=1).
- **`top_prompt`** (21w): `Since midnight I had repeated dark vomiting, crampy stomach pain, and heavy rectal bleeding, so I need to go to the`
- **`bottom_prompt`** (21w): `Since midnight I had repeated dark vomitting, crampy stomach pain, and heavy rectal bleeding, so I need to go to the`
- **`swap_spans`**: `{"correct": "vomiting", "misspelled": "vomitting"}`
- **Tier 4 justification**: Repeated dark hematemesis with abdominal pain and heavy rectal bleeding indicates acute GI hemorrhage requiring immediate emergency resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since midnight | `Since midnight I had` | `Since midnight I had` |
| 2 | Repeated dark vomiting (1-word everyday spelling contrast: vomiting vs vomitting) | `repeated dark vomiting` | `repeated dark vomitting` |
| 3 | Crampy stomach pain | `crampy stomach pain` | `crampy stomach pain` |
| 4 | Heavy rectal bleeding | `and heavy rectal bleeding` | `and heavy rectal bleeding` |

### `sc-039` (extends `ag-048` — `misspelled_everyday` — `nephrology_urology`, `dose_group=dg-03`, `misspelling_count=1`)
- **Clinical difference from `ag-048`**: Extends ag-048 (febrile kidney pain) by testing the realistic OAC CHV doubled-letter typo 'shiverring' alongside flank aching and nonstop vomiting (dg-03, dose=1).
- **`top_prompt`** (21w): `With a high fever I got violent shivering, flank kidney aching, and nonstop vomiting, so I need to go to the`
- **`bottom_prompt`** (21w): `With a high fever I got violent shiverring, flank kidney aching, and nonstop vomiting, so I need to go to the`
- **`swap_spans`**: `{"correct": "shivering", "misspelled": "shiverring"}`
- **Tier 4 justification**: Febrile rigors ('violent shivering') with flank kidney pain and intractable vomiting require emergency IV antibiotics and fluid resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever context | `With a high fever I got` | `With a high fever I got` |
| 2 | Violent shivering (1-word everyday spelling contrast: shivering vs shiverring) | `violent shivering` | `violent shiverring` |
| 3 | Flank kidney aching | `flank kidney aching` | `flank kidney aching` |
| 4 | Nonstop vomiting | `and nonstop vomiting` | `and nonstop vomiting` |

### `sc-040` (extends `ag-042` — `misspelled_everyday` — `allergy_immunology`, `dose_group=dg-04`, `misspelling_count=1`)
- **Clinical difference from `ag-042`**: Extends ag-042 (clinical-term spelling contrast) to an acute venom-anaphylaxis emergency using OAC CHV everyday-word misspelling 'itchhing' (dg-04, dose=1).
- **`top_prompt`** (22w): `Five minutes after a bee sting I got full-body itching, throat choking, and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (22w): `Five minutes after a bee sting I got full-body itchhing, throat choking, and severe dizziness, so I need to go to the`
- **`swap_spans`**: `{"correct": "itching", "misspelled": "itchhing"}`
- **Tier 4 justification**: Generalized urticaria/itching with throat choking and hypotensive dizziness minutes after venom exposure is systemic anaphylaxis requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: five minutes after a bee sting | `Five minutes after a bee sting I got` | `Five minutes after a bee sting I got` |
| 2 | Full-body itching (1-word everyday spelling contrast: itching vs itchhing) | `full-body itching` | `full-body itchhing` |
| 3 | Throat choking | `throat choking` | `throat choking` |
| 4 | Severe dizziness | `and severe dizziness` | `and severe dizziness` |

### `sc-041` (extends `ag-041` — `misspelled_everyday` — `infectious_disease_dermatology`, `dose_group=dg-05`, `misspelling_count=1`)
- **Clinical difference from `ag-041`**: Extends ag-041 (meningitis spelling contrast) to an acute bullous soft-tissue infection with febrile rigors using everyday-word misspelling 'inflammed' (dg-05, dose=1).
- **`top_prompt`** (25w): `With a high fever today my calf skin became red and inflamed with rapid blistering and violent shivering, so I need to go to the`
- **`bottom_prompt`** (25w): `With a high fever today my calf skin became red and inflammed with rapid blistering and violent shivering, so I need to go to the`
- **`swap_spans`**: `{"correct": "inflamed", "misspelled": "inflammed"}`
- **Tier 4 justification**: Febrile lower-extremity skin inflammation accompanied by rapid bullous blistering and rigors requires immediate emergency surgical and infectious evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today` | `With a high fever today` |
| 2 | Calf skin red and inflamed (1-word everyday spelling contrast: inflamed vs inflammed) | `my calf skin became red and inflamed` | `my calf skin became red and inflammed` |
| 3 | Rapid blistering | `with rapid blistering` | `with rapid blistering` |
| 4 | Violent shivering | `and violent shivering` | `and violent shivering` |

### `sc-042` (extends `ag-050` — `misspelled_everyday` — `pulmonology_infectious`, `dose_group=dg-06`, `misspelling_count=1`)
- **Clinical difference from `ag-050`**: Extends ag-050 (orthopedic trauma spelling contrast) to an acute febrile pulmonary sepsis presentation with diaphoresis, rigors, and hemoptysis (dg-06, dose=1).
- **`top_prompt`** (22w): `With a high fever today I got drenching cold sweating, uncontrollable shaking, and blood-streaked coughing, so I need to go to the`
- **`bottom_prompt`** (22w): `With a high fever today I got drenching cold sweatting, uncontrollable shaking, and blood-streaked coughing, so I need to go to the`
- **`swap_spans`**: `{"correct": "sweating", "misspelled": "sweatting"}`
- **Tier 4 justification**: Acute high fever with diaphoresis, rigors, and hemoptysis requires immediate emergency chest imaging and sepsis resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today I got` | `With a high fever today I got` |
| 2 | Drenching cold sweating (1-word everyday spelling contrast: sweating vs sweatting) | `drenching cold sweating` | `drenching cold sweatting` |
| 3 | Uncontrollable shaking | `uncontrollable shaking` | `uncontrollable shaking` |
| 4 | Blood-streaked coughing | `and blood-streaked coughing` | `and blood-streaked coughing` |

### `sc-043` (extends `ag-042` — `misspelled_everyday` — `otolaryngology_infectious`, `dose_group=dg-07`, `misspelling_count=1`)
- **Clinical difference from `ag-042`**: Extends ag-042 (chronic pulmonary cough spelling contrast) to an acute febrile upper-airway obstruction presentation using OAC CHV typo 'coughhing' (dg-07, dose=1).
- **`top_prompt`** (24w): `Tonight with a high fever I got barking coughing, throat choking, and an inflamed throat with drooling, so I need to go to the`
- **`bottom_prompt`** (24w): `Tonight with a high fever I got barking coughhing, throat choking, and an inflamed throat with drooling, so I need to go to the`
- **`swap_spans`**: `{"correct": "coughing", "misspelled": "coughhing"}`
- **Tier 4 justification**: Febrile barking cough with choking, pharyngeal inflammation, and drooling threatens acute airway compromise requiring immediate emergency department care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset tonight with high fever | `Tonight with a high fever I got` | `Tonight with a high fever I got` |
| 2 | Barking coughing (1-word everyday spelling contrast: coughing vs coughhing) | `barking coughing` | `barking coughhing` |
| 3 | Throat choking | `throat choking` | `throat choking` |
| 4 | Inflamed throat with drooling | `and an inflamed throat with drooling` | `and an inflamed throat with drooling` |

### `sc-044` (extends `ag-041` — `misspelled_everyday` — `otolaryngology_neurology`, `dose_group=dg-08`, `misspelling_count=1`)
- **Clinical difference from `ag-041`**: Extends ag-041 (CNS infection spelling contrast) to an acute otolaryngological/intracranial infection emergency (coalescent mastoiditis) using OAC CHV typo 'hearring' (dg-08, dose=1).
- **`top_prompt`** (25w): `With an ear infection and fever I got muffled hearing, painful bulging behind my ear, and violent shaking, so I need to go to the`
- **`bottom_prompt`** (25w): `With an ear infection and fever I got muffled hearring, painful bulging behind my ear, and violent shaking, so I need to go to the`
- **`swap_spans`**: `{"correct": "hearing", "misspelled": "hearring"}`
- **Tier 4 justification**: Febrile otitis media complicated by postauricular swelling/bulging, hearing loss, and rigors indicates acute mastoiditis requiring immediate emergency evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Ear infection and fever context | `With an ear infection and fever I got` | `With an ear infection and fever I got` |
| 2 | Muffled hearing (1-word everyday spelling contrast: hearing vs hearring) | `muffled hearing` | `muffled hearring` |
| 3 | Painful bulging behind ear | `painful bulging behind my ear` | `painful bulging behind my ear` |
| 4 | Violent shaking | `and violent shaking` | `and violent shaking` |

### `sc-045` (extends `ag-043` — `misspelled_everyday` — `allergy_immunology`, `dose_group=dg-09`, `misspelling_count=1`)
- **Clinical difference from `ag-043`**: Extends ag-043 (clinical-term spelling contrast) to an acute medication-induced lingual angioedema and mucocutaneous blistering emergency using 'tounge' (dg-09, dose=1).
- **`top_prompt`** (24w): `After taking a new pill today my tongue is swollen with full-body itching and painful lip blistering, so I need to go to the`
- **`bottom_prompt`** (24w): `After taking a new pill today my tounge is swollen with full-body itching and painful lip blistering, so I need to go to the`
- **`swap_spans`**: `{"correct": "tongue", "misspelled": "tounge"}`
- **Tier 4 justification**: Acute lingual swelling accompanied by generalized pruritus and labial blistering after starting a medication requires immediate emergency airway and allergy care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: after taking a new pill today | `After taking a new pill today` | `After taking a new pill today` |
| 2 | Swollen tongue (1-word everyday spelling contrast: tongue vs tounge) | `my tongue is swollen` | `my tounge is swollen` |
| 3 | Full-body itching | `with full-body itching` | `with full-body itching` |
| 4 | Painful lip blistering | `and painful lip blistering` | `and painful lip blistering` |

### `sc-046` (extends `ag-044` — `misspelled_everyday` — `gastroenterology_surgery`, `dose_group=dg-10`, `misspelling_count=1`)
- **Clinical difference from `ag-044`**: Extends ag-044 (hepatitis spelling contrast, Tier 2) to an acute surgical abdomen with board-hard rigidity, painful belly bulging, and diaphoresis (Tier 4, dg-10, dose=1).
- **`top_prompt`** (22w): `Today after lunch my stomach has been board-hard with painful belly bulging and cold sweating, so I need to go to the`
- **`bottom_prompt`** (22w): `Today after lunch my stomache has been board-hard with painful belly bulging and cold sweating, so I need to go to the`
- **`swap_spans`**: `{"correct": "stomach", "misspelled": "stomache"}`
- **Tier 4 justification**: Board-like abdominal rigidity with painful distension/bulging and diaphoresis indicates acute peritonitis requiring immediate emergency surgical evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset today after lunch | `Today after lunch` | `Today after lunch` |
| 2 | Stomach board-hard (1-word everyday spelling contrast: stomach vs stomache) | `my stomach has been board-hard` | `my stomache has been board-hard` |
| 3 | Painful belly bulging | `with painful belly bulging` | `with painful belly bulging` |
| 4 | Cold sweating | `and cold sweating` | `and cold sweating` |

### `sc-047` (extends `ag-049` — `misspelled_multiple` — `obstetrics_gynecology`, `dose_group=dg-01`, `misspelling_count=3`)
- **Clinical difference from `ag-049`**: Extends ag-049 (and pairs with sc-037 in dose_group dg-01) by testing 3 simultaneous OAC CHV everyday misspellings ('bleedding', 'acheing', 'dizzyness') in early-pregnancy hemorrhage.
- **`top_prompt`** (22w): `Early in pregnancy today I got heavy vaginal bleeding, lower belly aching, and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (22w): `Early in pregnancy today I got heavy vaginal bleedding, lower belly acheing, and severe dizzyness, so I need to go to the`
- **`swap_spans`**: `[{"correct": "bleeding", "misspelled": "bleedding"}, {"correct": "aching", "misspelled": "acheing"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 4 justification**: Heavy vaginal bleeding with lower abdominal pain and severe dizziness in early pregnancy requires immediate emergency evaluation for ruptured ectopic pregnancy (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Early pregnancy onset today | `Early in pregnancy today I got` | `Early in pregnancy today I got` |
| 2 | Heavy vaginal bleeding (misspelled 'bleedding' on bottom) | `heavy vaginal bleeding` | `heavy vaginal bleedding` |
| 3 | Lower belly aching (misspelled 'acheing' on bottom) | `lower belly aching` | `lower belly acheing` |
| 4 | Severe dizziness (misspelled 'dizzyness' on bottom) | `and severe dizziness` | `and severe dizzyness` |

### `sc-048` (extends `ag-047` — `misspelled_multiple` — `gastroenterology`, `dose_group=dg-02`, `misspelling_count=3`)
- **Clinical difference from `ag-047`**: Extends ag-047 (and pairs with sc-038 in dose_group dg-02) by testing 3 simultaneous everyday misspellings ('vomitting', 'stomache', 'bleedding') in acute GI hemorrhage.
- **`top_prompt`** (21w): `Since midnight I had repeated dark vomiting, crampy stomach pain, and heavy rectal bleeding, so I need to go to the`
- **`bottom_prompt`** (21w): `Since midnight I had repeated dark vomitting, crampy stomache pain, and heavy rectal bleedding, so I need to go to the`
- **`swap_spans`**: `[{"correct": "vomiting", "misspelled": "vomitting"}, {"correct": "stomach", "misspelled": "stomache"}, {"correct": "bleeding", "misspelled": "bleedding"}]`
- **Tier 4 justification**: Repeated dark hematemesis with abdominal pain and heavy rectal bleeding indicates acute GI hemorrhage requiring immediate emergency resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since midnight | `Since midnight I had` | `Since midnight I had` |
| 2 | Repeated dark vomiting (misspelled 'vomitting' on bottom) | `repeated dark vomiting` | `repeated dark vomitting` |
| 3 | Crampy stomach pain (misspelled 'stomache' on bottom) | `crampy stomach pain` | `crampy stomache pain` |
| 4 | Heavy rectal bleeding (misspelled 'bleedding' on bottom) | `and heavy rectal bleeding` | `and heavy rectal bleedding` |

### `sc-049` (extends `ag-048` — `misspelled_multiple` — `nephrology_urology`, `dose_group=dg-03`, `misspelling_count=3`)
- **Clinical difference from `ag-048`**: Extends ag-048 (and pairs with sc-039 in dose_group dg-03) by testing 3 simultaneous OAC CHV everyday misspellings ('shiverring', 'acheing', 'vomitting').
- **`top_prompt`** (21w): `With a high fever I got violent shivering, flank kidney aching, and nonstop vomiting, so I need to go to the`
- **`bottom_prompt`** (21w): `With a high fever I got violent shiverring, flank kidney acheing, and nonstop vomitting, so I need to go to the`
- **`swap_spans`**: `[{"correct": "shivering", "misspelled": "shiverring"}, {"correct": "aching", "misspelled": "acheing"}, {"correct": "vomiting", "misspelled": "vomitting"}]`
- **Tier 4 justification**: Febrile rigors ('violent shivering') with flank kidney pain and intractable vomiting require emergency IV antibiotics and fluid resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever context | `With a high fever I got` | `With a high fever I got` |
| 2 | Violent shivering (misspelled 'shiverring' on bottom) | `violent shivering` | `violent shiverring` |
| 3 | Flank kidney aching (misspelled 'acheing' on bottom) | `flank kidney aching` | `flank kidney acheing` |
| 4 | Nonstop vomiting (misspelled 'vomitting' on bottom) | `and nonstop vomiting` | `and nonstop vomitting` |

### `sc-050` (extends `ag-042` — `misspelled_multiple` — `allergy_immunology`, `dose_group=dg-04`, `misspelling_count=3`)
- **Clinical difference from `ag-042`**: Extends ag-042 (and pairs with sc-040 in dose_group dg-04) by testing 3 simultaneous OAC CHV everyday misspellings ('itchhing', 'chokeing', 'dizzyness') in acute anaphylaxis.
- **`top_prompt`** (22w): `Five minutes after a bee sting I got full-body itching, throat choking, and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (22w): `Five minutes after a bee sting I got full-body itchhing, throat chokeing, and severe dizzyness, so I need to go to the`
- **`swap_spans`**: `[{"correct": "itching", "misspelled": "itchhing"}, {"correct": "choking", "misspelled": "chokeing"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 4 justification**: Generalized urticaria/itching with throat choking and hypotensive dizziness minutes after venom exposure is systemic anaphylaxis requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: five minutes after a bee sting | `Five minutes after a bee sting I got` | `Five minutes after a bee sting I got` |
| 2 | Full-body itching (misspelled 'itchhing' on bottom) | `full-body itching` | `full-body itchhing` |
| 3 | Throat choking (misspelled 'chokeing' on bottom) | `throat choking` | `throat chokeing` |
| 4 | Severe dizziness (misspelled 'dizzyness' on bottom) | `and severe dizziness` | `and severe dizzyness` |

### `sc-051` (extends `ag-041` — `misspelled_multiple` — `infectious_disease_dermatology`, `dose_group=dg-05`, `misspelling_count=3`)
- **Clinical difference from `ag-041`**: Extends ag-041 (and pairs with sc-041 in dose_group dg-05) by testing 3 simultaneous OAC CHV everyday misspellings ('inflammed', 'blisterring', 'shiverring').
- **`top_prompt`** (25w): `With a high fever today my calf skin became red and inflamed with rapid blistering and violent shivering, so I need to go to the`
- **`bottom_prompt`** (25w): `With a high fever today my calf skin became red and inflammed with rapid blisterring and violent shiverring, so I need to go to the`
- **`swap_spans`**: `[{"correct": "inflamed", "misspelled": "inflammed"}, {"correct": "blistering", "misspelled": "blisterring"}, {"correct": "shivering", "misspelled": "shiverring"}]`
- **Tier 4 justification**: Febrile lower-extremity skin inflammation accompanied by rapid bullous blistering and rigors requires immediate emergency surgical and infectious evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today` | `With a high fever today` |
| 2 | Calf skin red and inflamed (misspelled 'inflammed' on bottom) | `my calf skin became red and inflamed` | `my calf skin became red and inflammed` |
| 3 | Rapid blistering (misspelled 'blisterring' on bottom) | `with rapid blistering` | `with rapid blisterring` |
| 4 | Violent shivering (misspelled 'shiverring' on bottom) | `and violent shivering` | `and violent shiverring` |

### `sc-052` (extends `ag-050` — `misspelled_multiple` — `pulmonology_infectious`, `dose_group=dg-06`, `misspelling_count=3`)
- **Clinical difference from `ag-050`**: Extends ag-050 (and pairs with sc-042 in dose_group dg-06) by testing 3 simultaneous OAC CHV everyday misspellings ('sweatting', 'shakeing', 'coughhing').
- **`top_prompt`** (22w): `With a high fever today I got drenching cold sweating, uncontrollable shaking, and blood-streaked coughing, so I need to go to the`
- **`bottom_prompt`** (22w): `With a high fever today I got drenching cold sweatting, uncontrollable shakeing, and blood-streaked coughhing, so I need to go to the`
- **`swap_spans`**: `[{"correct": "sweating", "misspelled": "sweatting"}, {"correct": "shaking", "misspelled": "shakeing"}, {"correct": "coughing", "misspelled": "coughhing"}]`
- **Tier 4 justification**: Acute high fever with diaphoresis, rigors, and hemoptysis requires immediate emergency chest imaging and sepsis resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today I got` | `With a high fever today I got` |
| 2 | Drenching cold sweating (misspelled 'sweatting' on bottom) | `drenching cold sweating` | `drenching cold sweatting` |
| 3 | Uncontrollable shaking (misspelled 'shakeing' on bottom) | `uncontrollable shaking` | `uncontrollable shakeing` |
| 4 | Blood-streaked coughing (misspelled 'coughhing' on bottom) | `and blood-streaked coughing` | `and blood-streaked coughhing` |

### `sc-053` (extends `ag-042` — `misspelled_multiple` — `otolaryngology_infectious`, `dose_group=dg-07`, `misspelling_count=3`)
- **Clinical difference from `ag-042`**: Extends ag-042 (and pairs with sc-043 in dose_group dg-07) by testing 3 simultaneous OAC CHV everyday misspellings ('coughhing', 'chokeing', 'inflammed').
- **`top_prompt`** (24w): `Tonight with a high fever I got barking coughing, throat choking, and an inflamed throat with drooling, so I need to go to the`
- **`bottom_prompt`** (24w): `Tonight with a high fever I got barking coughhing, throat chokeing, and an inflammed throat with drooling, so I need to go to the`
- **`swap_spans`**: `[{"correct": "coughing", "misspelled": "coughhing"}, {"correct": "choking", "misspelled": "chokeing"}, {"correct": "inflamed", "misspelled": "inflammed"}]`
- **Tier 4 justification**: Febrile barking cough with choking, pharyngeal inflammation, and drooling threatens acute airway compromise requiring immediate emergency department care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset tonight with high fever | `Tonight with a high fever I got` | `Tonight with a high fever I got` |
| 2 | Barking coughing (misspelled 'coughhing' on bottom) | `barking coughing` | `barking coughhing` |
| 3 | Throat choking (misspelled 'chokeing' on bottom) | `throat choking` | `throat chokeing` |
| 4 | Inflamed throat with drooling (misspelled 'inflammed' on bottom) | `and an inflamed throat with drooling` | `and an inflammed throat with drooling` |

### `sc-054` (extends `ag-041` — `misspelled_multiple` — `otolaryngology_neurology`, `dose_group=dg-08`, `misspelling_count=3`)
- **Clinical difference from `ag-041`**: Extends ag-041 (and pairs with sc-044 in dose_group dg-08) by testing 3 simultaneous OAC CHV everyday misspellings ('hearring', 'bulgeing', 'shakeing').
- **`top_prompt`** (25w): `With an ear infection and fever I got muffled hearing, painful bulging behind my ear, and violent shaking, so I need to go to the`
- **`bottom_prompt`** (25w): `With an ear infection and fever I got muffled hearring, painful bulgeing behind my ear, and violent shakeing, so I need to go to the`
- **`swap_spans`**: `[{"correct": "hearing", "misspelled": "hearring"}, {"correct": "bulging", "misspelled": "bulgeing"}, {"correct": "shaking", "misspelled": "shakeing"}]`
- **Tier 4 justification**: Febrile otitis media complicated by postauricular swelling/bulging, hearing loss, and rigors indicates acute mastoiditis requiring immediate emergency evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Ear infection and fever context | `With an ear infection and fever I got` | `With an ear infection and fever I got` |
| 2 | Muffled hearing (misspelled 'hearring' on bottom) | `muffled hearing` | `muffled hearring` |
| 3 | Painful bulging behind ear (misspelled 'bulgeing' on bottom) | `painful bulging behind my ear` | `painful bulgeing behind my ear` |
| 4 | Violent shaking (misspelled 'shakeing' on bottom) | `and violent shaking` | `and violent shakeing` |

### `sc-055` (extends `ag-043` — `misspelled_multiple` — `allergy_immunology`, `dose_group=dg-09`, `misspelling_count=3`)
- **Clinical difference from `ag-043`**: Extends ag-043 (and pairs with sc-045 in dose_group dg-09) by testing 3 simultaneous everyday misspellings ('tounge', 'itchhing', 'blisterring') in acute airway/mucosal drug reaction.
- **`top_prompt`** (24w): `After taking a new pill today my tongue is swollen with full-body itching and painful lip blistering, so I need to go to the`
- **`bottom_prompt`** (24w): `After taking a new pill today my tounge is swollen with full-body itchhing and painful lip blisterring, so I need to go to the`
- **`swap_spans`**: `[{"correct": "tongue", "misspelled": "tounge"}, {"correct": "itching", "misspelled": "itchhing"}, {"correct": "blistering", "misspelled": "blisterring"}]`
- **Tier 4 justification**: Acute lingual swelling accompanied by generalized pruritus and labial blistering after starting a medication requires immediate emergency airway and allergy care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: after taking a new pill today | `After taking a new pill today` | `After taking a new pill today` |
| 2 | Swollen tongue (misspelled 'tounge' on bottom) | `my tongue is swollen` | `my tounge is swollen` |
| 3 | Full-body itching (misspelled 'itchhing' on bottom) | `with full-body itching` | `with full-body itchhing` |
| 4 | Painful lip blistering (misspelled 'blisterring' on bottom) | `and painful lip blistering` | `and painful lip blisterring` |

### `sc-056` (extends `ag-044` — `misspelled_multiple` — `gastroenterology_surgery`, `dose_group=dg-10`, `misspelling_count=3`)
- **Clinical difference from `ag-044`**: Extends ag-044 (and pairs with sc-046 in dose_group dg-10) by testing 3 simultaneous everyday misspellings ('stomache', 'bulgeing', 'sweatting') in acute surgical abdomen.
- **`top_prompt`** (22w): `Today after lunch my stomach has been board-hard with painful belly bulging and cold sweating, so I need to go to the`
- **`bottom_prompt`** (22w): `Today after lunch my stomache has been board-hard with painful belly bulgeing and cold sweatting, so I need to go to the`
- **`swap_spans`**: `[{"correct": "stomach", "misspelled": "stomache"}, {"correct": "bulging", "misspelled": "bulgeing"}, {"correct": "sweating", "misspelled": "sweatting"}]`
- **Tier 4 justification**: Board-like abdominal rigidity with painful distension/bulging and diaphoresis indicates acute peritonitis requiring immediate emergency surgical evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset today after lunch | `Today after lunch` | `Today after lunch` |
| 2 | Stomach board-hard (misspelled 'stomache' on bottom) | `my stomach has been board-hard` | `my stomache has been board-hard` |
| 3 | Painful belly bulging (misspelled 'bulgeing' on bottom) | `with painful belly bulging` | `with painful belly bulgeing` |
| 4 | Cold sweating (misspelled 'sweatting' on bottom) | `and cold sweating` | `and cold sweatting` |
