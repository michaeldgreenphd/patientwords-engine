# Self-Check Report (`scale_20261108/candidates.json`)

## 1. Automated Structural, Invariant & Ground-Truth Checks

- **Total new pairs in `scale_20261108/candidates.json`**: **56** (within the 60-pair cap).
- **Ground-truth `extends` & `tier_should` compliance (`56 / 56 PASS`)**:
  - Every pair names a confirmed (`right` or `retier`) pair from `ground_truth/gt_20261108.json` in `extends`; zero pairs extend excluded `ag-017`, `ag-045`, or `ag-046`.
  - All 4 re-levelled pairs in `gt_20261108.json` are extended at their corrected `tier_should` level and end on a target token of that corrected level: `sc-012` extends `ag-021` at **Tier 4 (`" ER"`)**, `sc-013` extends `ag-027` at **Tier 3 (`" pulmonologist"`)**, `sc-016` extends `ag-031` at **Tier 3 (`" urologist"`)**, and `sc-018` extends `ag-034` at **Tier 3 (`" neurologist"`)**.
- **Swap-span rules by family (`56 / 56 PASS`)**:
  - **40 single-span swap pairs** (`red_flag_everyday`, `metaphor_idiom`, `dialect_non_native`, `context_raises_urgency`, `medication_safety`, and `misspelled_everyday`): `top_prompt.replace(clinical_span, patient_span, 1) == bottom_prompt` holds with exact character identity (`40 / 40 PASS`).
  - **6 `minimizing_hedged` pairs (`sc-009`–`sc-014`) — Sentence-Initial Insertion Rule**: Both sides use the exact same everyday words, and `bottom_prompt` prepends `"It's probably nothing, but "` at the start of the sentence (`swap_spans: {"clinical_span": "", "patient_span": "It's probably nothing, but "}`), with zero severity words (`"a little"`) added (`6 / 6 PASS`).
  - **10 `misspelled_multiple` pairs (`sc-047`–`sc-056`) — Multi-Word Everyday Spelling Rule**: Each pair records `misspelling_count: 3`, `swap_spans` as a 3-element list of `{"correct": ..., "misspelled": ...}` everyday words, and shares `dose_group` (`dg-01`–`dg-10`) and an identical `top_prompt` with its 1-misspelling partner in `misspelled_everyday` (`sc-037`–`sc-046`) (`10 / 10 PASS`).
- **Shared carrier frame at end of both prompts**: **56 / 56 PASS** (`100%`).
- **Word count ceiling (`<= 25` whitespace-delimited words on both prompts)**: **56 / 56 PASS** (max `top_prompt` = **25** words; max `bottom_prompt` = **25** words).
- **Leading space on `target_clinical_token` and all `expected_patient_continuations`**: **56 / 56 PASS** (`100%`).
- **Holdout seal check (`tierb_split.is_holdout == False` on both `top_prompt` and `bottom_prompt`, and `sealed_pair == False`)**: **56 / 56 PASS** (`100%`).
- **Non-duplication against all 1,774 published scenarios**: **PASS** — maximum `SequenceMatcher` similarity is **0.660** (`sc-019` `bottom_prompt` vs. `pub:260:patient`). Maximum similarity against Round 3 (`candidates_v3.json`) is **0.757** (`sc-009` `bottom_prompt` vs. `v3:ag-018:bottom`, sharing only the sentence-initial hedge and carrier frame).
- **Family distribution**: `red_flag_everyday`: 8, `minimizing_hedged`: 6, `metaphor_idiom`: 5, `dialect_non_native`: 6, `context_raises_urgency`: 6, `medication_safety`: 5, `misspelled_everyday`: 10, `misspelled_multiple`: 10.
- **Expected clinical tier distribution**: Tier 4: 40, Tier 3: 14, Tier 2: 2.

---

## 2. How Each New Pair Differs Clinically from the Confirmed Example It Extends (`sc-001`–`sc-056`)

- **`sc-001`** (extends `ag-001`, `red_flag_everyday`, `pulmonology_thoracic`): Extends ag-001 (cardiac chest pressure radiating to jaw with diaphoresis) to a pulmonary/pleural emergency (sudden unilateral pleuritic chest pain with resting dyspnea).
- **`sc-002`** (extends `ag-002`, `red_flag_everyday`, `gastroenterology_surgery`): Extends ag-002 (vascular interscapular tearing pain) to a gastrointestinal/thoracic surgical emergency (post-emetic esophageal rupture with cervical subcutaneous crepitus).
- **`sc-003`** (extends `ag-003`, `red_flag_everyday`, `neurology`): Extends ag-003 (posterior-circulation diplopia and gait ataxia) to an anterior-circulation hemispheric stroke presentation (left arm weakness and expressive aphasia).
- **`sc-004`** (extends `ag-005`, `red_flag_everyday`, `infectious_disease_dermatology`): Extends ag-005 (urinary tract sepsis with rigors and confusion) to a soft-tissue surgical infection emergency (necrotizing infection signs on the lower leg).
- **`sc-005`** (extends `ag-006`, `red_flag_everyday`, `otolaryngology_infectious`): Extends ag-006 (bacterial meningitis triad) to an acute infectious upper-airway emergency (febrile drooling, muffled voice, and inability to swallow liquids).
- **`sc-006`** (extends `ag-007`, `red_flag_everyday`, `vascular_orthopedics`): Extends ag-007 (food-triggered anaphylaxis airway emergency) to a limb-threatening orthopedic/vascular emergency (post-cast acute compartment syndrome).
- **`sc-007`** (extends `ag-011`, `red_flag_everyday`, `vascular_gastroenterology`): Extends ag-011 (upper GI hemorrhage with hematemesis and melena) to an acute intestinal vascular emergency (mesenteric ischemia with pain out of proportion and bloody stools).
- **`sc-008`** (extends `ag-014`, `red_flag_everyday`, `ophthalmology_neurology`): Extends ag-014 (spinal cauda equina compression) to a neuro-ophthalmic infectious emergency (orbital cellulitis / cavernous sinus thrombosis signs).
- **`sc-009`** (extends `ag-018`, `minimizing_hedged`, `neurology`): Extends ag-018 (transient monocular visual loss in right eye) to a hemispheric sensorimotor TIA presentation (ten-minute unilateral arm numbness and clumsiness).
- **`sc-010`** (extends `ag-019`, `minimizing_hedged`, `oncology_urology`): Extends ag-019 (supraclavicular collarbone lump with night sweats) to a genitourinary oncology presentation (firm painless intratesticular mass).
- **`sc-011`** (extends `ag-020`, `minimizing_hedged`, `otolaryngology_oncology`): Extends ag-020 (gastroenterology solid-food dysphagia) to a head-and-neck oncology alarm presentation (six weeks of hoarseness with a neck mass, targeting ' otolaryngologist').
- **`sc-012`** (extends `ag-021`, `minimizing_hedged`, `urology_emergency`): Extends ag-021 using the owner's corrected Tier 4 emergency level (ending on ' ER' rather than Tier 3 ' urologist', with clot passage and orthostatic dizziness).
- **`sc-013`** (extends `ag-027`, `minimizing_hedged`, `pulmonology_oncology`): Extends ag-027 using the owner's corrected Tier 3 specialist level (ending on ' pulmonologist' rather than Tier 2 ' doctor').
- **`sc-014`** (extends `ag-028`, `minimizing_hedged`, `neurology`): Extends ag-028 (lower-extremity foot drop) to a cranial-nerve oculomotor deficit (acute unilateral eyelid ptosis with double vision).
- **`sc-015`** (extends `ag-029`, `metaphor_idiom`, `neurology`): Extends ag-029 (cardiac 'heavy weight' chest pressure metaphor) to the classic neurological subarachnoid hemorrhage patient metaphor ('like a baseball bat hit my skull').
- **`sc-016`** (extends `ag-031`, `metaphor_idiom`, `urology_nephrology`): Extends ag-031 using the owner's corrected Tier 3 specialist level (' urologist') and shifts from dysuria to obstructing renal colic with hematuria.
- **`sc-017`** (extends `ag-032`, `metaphor_idiom`, `cardiology_pulmonology`): Extends ag-032 (asthma 'breathing through a straw' metaphor) to cardiogenic flash pulmonary edema ('feeling of drowning' with pink frothy sputum).
- **`sc-018`** (extends `ag-034`, `metaphor_idiom`, `otolaryngology_neurology`): Extends ag-034 using the owner's corrected Tier 3 specialist level (' neurologist') and shifts from positional bed vertigo to episodic vertigo with tinnitus and hearing loss.
- **`sc-019`** (extends `ag-037`, `metaphor_idiom`, `neurology_spine`): Extends ag-037 (facial trigeminal neuralgia triggered by wind) to cervical spinal cord Lhermitte's phenomenon triggered by neck flexion.
- **`sc-020`** (extends `ag-052`, `dialect_non_native`, `neurology`): Extends ag-052 (cardiogenic syncope with chest tightness at work) to a neurological generalized convulsion with postictal confusion.
- **`sc-021`** (extends `ag-053`, `dialect_non_native`, `pulmonology`): Extends ag-053 (heart failure orthopnea targeting ' cardiologist') to chronic obstructive pulmonary symptoms targeting ' pulmonologist'.
- **`sc-022`** (extends `ag-055`, `dialect_non_native`, `gastroenterology_surgery`): Extends ag-055 (post-prandial epigastric biliary pain, Tier 2) to acute surgical appendicitis with migrating right-lower-quadrant pain and fever (Tier 4).
- **`sc-023`** (extends `ag-056`, `dialect_non_native`, `neurology_infectious`): Extends ag-056 (L2 cardiac chest pressure and dyspnea) to an acute central nervous system emergency (occipital headache, neck stiffness, and confusion).
- **`sc-024`** (extends `ag-057`, `dialect_non_native`, `neurology`): Extends ag-057 (anterior-circulation facial droop and arm weakness) to a posterior-circulation visual-field and gait stroke presentation in L2 phrasing.
- **`sc-025`** (extends `ag-060`, `dialect_non_native`, `hepatology_gastroenterology`): Extends ag-060 (renal/cardiac ankle edema and oliguria) to a hepatobiliary presentation (abdominal ascites and scleral icterus).
- **`sc-026`** (extends `ag-063`, `context_raises_urgency`, `hematology_orthopedics`): Extends ag-063 (head trauma on anticoagulants) to a congenital bleeding-disorder musculoskeletal emergency (acute knee hemarthrosis in hemophilia).
- **`sc-027`** (extends `ag-064`, `context_raises_urgency`, `surgery_infectious`): Extends ag-064 (post-chemotherapy febrile neutropenia) to surgical asplenia / overwhelming post-splenectomy infection (OPSI).
- **`sc-028`** (extends `ag-065`, `context_raises_urgency`, `pediatrics_pulmonology`): Extends ag-065 (neonatal fever at 19 days old) to an acute pediatric respiratory failure presentation (retractions and cyanosis at 4 weeks old).
- **`sc-029`** (extends `ag-067`, `context_raises_urgency`, `geriatrics_orthopedics`): Extends ag-067 (geriatric delirium and falls at age 83) to a geriatric orthopedic trauma emergency (displaced femoral neck fracture at age 81).
- **`sc-030`** (extends `ag-069`, `context_raises_urgency`, `hematology_neurology`): Extends ag-069 (adult sickle-cell acute chest syndrome) to a pediatric sickle-cell neurological emergency (acute ischemic stroke requiring exchange transfusion).
- **`sc-031`** (extends `ag-072`, `context_raises_urgency`, `cardiology_infectious`): Extends ag-072 (kidney transplant fever and graft tenderness) to a cardiac-device infectious emergency (prosthetic valve endocarditis signs).
- **`sc-032`** (extends `ag-074`, `medication_safety`, `endocrinology_infectious`): Extends ag-074 (sertraline + tramadol serotonin syndrome) to an endocrine medication-safety emergency (methimazole-induced febrile agranulocytosis).
- **`sc-033`** (extends `ag-075`, `medication_safety`, `cardiology_pharmacology`): Extends ag-075 (abrupt prednisone withdrawal adrenal crisis) to clonidine withdrawal rebound hypertensive emergency.
- **`sc-034`** (extends `ag-077`, `medication_safety`, `cardiology_nephrology`): Extends ag-077 (sildenafil + nitroglycerin hypotension) to a lethal electrolyte drug interaction (spironolactone + potassium supplement hyperkalemic bradycardia).
- **`sc-035`** (extends `ag-080`, `medication_safety`, `neurology_dermatology`): Extends ag-080 (lisinopril lingual angioedema) to an anticonvulsant mucocutaneous emergency (lamotrigine-induced Stevens-Johnson syndrome).
- **`sc-036`** (extends `ag-081`, `medication_safety`, `nephrology_cardiology`): Extends ag-081 (post-stent antiplatelet cessation calling ' cardiologist') to an antihypertensive/diuretic acute kidney injury scenario calling ' nephrologist'.
- **`sc-037`** (extends `ag-049`, `misspelled_everyday`, `obstetrics_gynecology`): Extends ag-049 (pregnancy misspelling) to a pure everyday symptom-word misspelling ('bleeding' -> 'bleedding') in early pregnancy with severe dizziness (dose_group dg-01, dose=1).
- **`sc-038`** (extends `ag-047`, `misspelled_everyday`, `gastroenterology`): Extends ag-047 (upper abdominal pain with vomiting) to combined dark vomiting, rectal bleeding, and misspelled 'dizzyness' (dose_group dg-02, dose=1).
- **`sc-039`** (extends `ag-048`, `misspelled_everyday`, `nephrology_urology`): Extends ag-048 (febrile kidney pain with chills) by adding intractable vomiting ('vomitting') and dizziness as a 1-vs-3 dose baseline (dose_group dg-03, dose=1).
- **`sc-040`** (extends `ag-042`, `misspelled_everyday`, `hematology_oncology`): Extends ag-042 (infectious tuberculosis spelling contrast) to a hematology pancytopenia presentation using everyday-word misspelling 'fatigu' (dose_group dg-04, dose=1).
- **`sc-041`** (extends `ag-041`, `misspelled_everyday`, `orthopedics_infectious`): Extends ag-041 (meningitis spelling contrast) to an acute septic arthritis emergency using everyday-word misspelling 'inflammed' (dose_group dg-05, dose=1).
- **`sc-042`** (extends `ag-050`, `misspelled_everyday`, `orthopedics_trauma`): Extends ag-050 (ladder fall leg fracture) to a motorcycle crash with open wrist fractures, heavy bleeding, and dizziness (dose_group dg-06, dose=1).
- **`sc-043`** (extends `ag-049`, `misspelled_everyday`, `obstetrics_gynecology`): Extends ag-049 (ectopic/hemorrhagic pregnancy emergency, Tier 4) to first-trimester hyperemesis gravidarum targeting ' obstetrician' (Tier 3, dose_group dg-07, dose=1).
- **`sc-044`** (extends `ag-048`, `misspelled_everyday`, `nephrology`): Extends ag-048 (acute febrile kidney infection, Tier 4) to subacute hematuria and renal pain targeting ' nephrologist' (Tier 3, dose_group dg-08, dose=1).
- **`sc-045`** (extends `ag-043`, `misspelled_everyday`, `allergy_immunology`): Extends ag-043 (neurological MS spelling contrast) to an acute drug-induced airway swelling emergency using everyday body/symptom words (dose_group dg-09, dose=1).
- **`sc-046`** (extends `ag-044`, `misspelled_everyday`, `gastroenterology_surgery`): Extends ag-044 (hepatitis spelling contrast, Tier 2) to an acute surgical abdomen with abdominal rigidity and vomiting (Tier 4, dose_group dg-10, dose=1).
- **`sc-047`** (extends `ag-049`, `misspelled_multiple`, `obstetrics_gynecology`): Extends ag-049 (and pairs with sc-037 in dose_group dg-01) by testing 3 simultaneous OAC CHV everyday misspellings ('pregnanci', 'bleedding', 'dizzyness') in early-pregnancy hemorrhage.
- **`sc-048`** (extends `ag-047`, `misspelled_multiple`, `gastroenterology`): Extends ag-047 (and pairs with sc-038 in dose_group dg-02) by testing 3 simultaneous OAC CHV everyday misspellings ('vomitting', 'bleedding', 'dizzyness') in acute GI hemorrhage.
- **`sc-049`** (extends `ag-048`, `misspelled_multiple`, `nephrology_urology`): Extends ag-048 (and pairs with sc-039 in dose_group dg-03) by testing 3 simultaneous OAC CHV everyday misspellings ('kidnei', 'vomitting', 'dizzyness').
- **`sc-050`** (extends `ag-042`, `misspelled_multiple`, `hematology_oncology`): Extends ag-042 (and pairs with sc-040 in dose_group dg-04) by testing 3 simultaneous OAC CHV everyday misspellings ('bleedding', 'fatigu', 'dizzyness') in hematologic pancytopenia.
- **`sc-051`** (extends `ag-041`, `misspelled_multiple`, `orthopedics_infectious`): Extends ag-041 (and pairs with sc-041 in dose_group dg-05) by testing 3 simultaneous OAC CHV everyday misspellings ('inflammed', 'vomitting', 'dizzyness') in septic arthritis.
- **`sc-052`** (extends `ag-050`, `misspelled_multiple`, `orthopedics_trauma`): Extends ag-050 (and pairs with sc-042 in dose_group dg-06) by testing 3 simultaneous OAC CHV everyday misspellings ('fracturs', 'bleedding', 'dizzyness').
- **`sc-053`** (extends `ag-049`, `misspelled_multiple`, `obstetrics_gynecology`): Extends ag-049 (and pairs with sc-043 in dose_group dg-07) by testing 3 simultaneous OAC CHV everyday misspellings ('pregnanci', 'vomitting', 'fatigu').
- **`sc-054`** (extends `ag-048`, `misspelled_multiple`, `nephrology`): Extends ag-048 (and pairs with sc-044 in dose_group dg-08) by testing 3 simultaneous OAC CHV everyday misspellings ('kidnei', 'bleedding', 'fatigu').
- **`sc-055`** (extends `ag-043`, `misspelled_multiple`, `allergy_immunology`): Extends ag-043 (and pairs with sc-045 in dose_group dg-09) by testing 3 simultaneous everyday misspellings ('tounge', 'swolen', 'breating') in acute airway swelling.
- **`sc-056`** (extends `ag-044`, `misspelled_multiple`, `gastroenterology_surgery`): Extends ag-044 (and pairs with sc-046 in dose_group dg-10) by testing 3 simultaneous everyday misspellings ('stomache', 'inflammed', 'vomitting') in acute peritonitis.

---

## 3. Fact-Parity & Order Table for Every Pair (`sc-001`–`sc-056`)

### `sc-001` (extends `ag-001` — `red_flag_everyday` — `pulmonology_thoracic`)
- **Clinical difference from `ag-001`**: Extends ag-001 (cardiac chest pressure radiating to jaw with diaphoresis) to a pulmonary/pleural emergency (sudden unilateral pleuritic chest pain with resting dyspnea).
- **`top_prompt`** (20w): `An hour ago I suddenly got unilateral pleuritic chest pain and resting dyspnea, so I need to go to the`
- **`bottom_prompt`** (23w): `An hour ago I suddenly got one-sided sharp chest pain breathing in and resting short breath, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "unilateral pleuritic chest pain and resting dyspnea", "patient_span": "one-sided sharp chest pain breathing in and resting short breath"}`
- **Tier 4 justification**: Sudden-onset unilateral pleuritic chest pain with resting dyspnea requires immediate emergency department evaluation to rule out spontaneous pneumothorax or pulmonary embolism (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset one hour ago, sudden | `An hour ago I suddenly got` | `An hour ago I suddenly got` |
| 2 | Unilateral pleuritic chest pain | `unilateral pleuritic chest pain` | `one-sided sharp chest pain breathing in` |
| 3 | Resting dyspnea / short breath | `and resting dyspnea` | `and resting short breath` |

### `sc-002` (extends `ag-002` — `red_flag_everyday` — `gastroenterology_surgery`)
- **Clinical difference from `ag-002`**: Extends ag-002 (vascular interscapular tearing pain) to a gastrointestinal/thoracic surgical emergency (post-emetic esophageal rupture with cervical subcutaneous crepitus).
- **`top_prompt`** (20w): `After violent retching I suddenly got retrosternal chest pain and subcutaneous cervical crepitus, so I need to get to the`
- **`bottom_prompt`** (25w): `After violent retching I suddenly got deep center chest pain and crackling air bubbles under my neck skin, so I need to get to the`
- **`swap_spans`**: `{"clinical_span": "retrosternal chest pain and subcutaneous cervical crepitus", "patient_span": "deep center chest pain and crackling air bubbles under my neck skin"}`
- **Tier 4 justification**: Post-emetic retrosternal pain accompanied by cervical subcutaneous emphysema indicates transmural esophageal perforation (Boerhaave syndrome) requiring immediate emergency surgical care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: after violent retching, sudden onset | `After violent retching I suddenly got` | `After violent retching I suddenly got` |
| 2 | Retrosternal / deep center chest pain | `retrosternal chest pain` | `deep center chest pain` |
| 3 | Subcutaneous cervical crepitus / crackling air under neck skin | `and subcutaneous cervical crepitus` | `and crackling air bubbles under my neck skin` |

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
- **`top_prompt`** (24w): `On my swollen calf I developed rapidly spreading erythema, hemorrhagic bullae, and severe pain out of proportion, so I need to go to the`
- **`bottom_prompt`** (24w): `On my swollen calf I developed fast-spreading redness, purple blood blisters, and extreme pain beyond the rash, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "rapidly spreading erythema, hemorrhagic bullae, and severe pain out of proportion", "patient_span": "fast-spreading redness, purple blood blisters, and extreme pain beyond the rash"}`
- **Tier 4 justification**: Rapidly spreading lower-extremity erythema with hemorrhagic bullae and severe pain out of proportion indicates necrotizing fasciitis requiring immediate emergency surgical exploration (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Location: on swollen calf | `On my swollen calf I developed` | `On my swollen calf I developed` |
| 2 | Rapidly spreading erythema / redness | `rapidly spreading erythema` | `fast-spreading redness` |
| 3 | Hemorrhagic bullae / purple blood blisters | `hemorrhagic bullae` | `purple blood blisters` |
| 4 | Severe pain out of proportion / beyond the rash | `and severe pain out of proportion` | `and extreme pain beyond the rash` |

### `sc-005` (extends `ag-006` — `red_flag_everyday` — `otolaryngology_infectious`)
- **Clinical difference from `ag-006`**: Extends ag-006 (bacterial meningitis triad) to an acute infectious upper-airway emergency (febrile drooling, muffled voice, and inability to swallow liquids).
- **`top_prompt`** (22w): `With a high fever today I developed muffled voice, drooling, and inability to swallow liquids, so I need to go to the`
- **`bottom_prompt`** (24w): `With a high fever today I developed a hot-potato muffled voice, drooling, and inability to swallow water, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "muffled voice, drooling, and inability to swallow liquids", "patient_span": "a hot-potato muffled voice, drooling, and inability to swallow water"}`
- **Tier 4 justification**: High fever accompanied by a muffled voice, drooling, and inability to swallow liquids signals impending upper-airway obstruction from epiglottitis or retropharyngeal abscess (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today I developed` | `With a high fever today I developed` |
| 2 | Muffled ('hot-potato') voice | `muffled voice` | `a hot-potato muffled voice` |
| 3 | Drooling | `drooling` | `drooling` |
| 4 | Inability to swallow liquids/water | `and inability to swallow liquids` | `and inability to swallow water` |

### `sc-006` (extends `ag-007` — `red_flag_everyday` — `vascular_orthopedics`)
- **Clinical difference from `ag-007`**: Extends ag-007 (food-triggered anaphylaxis airway emergency) to a limb-threatening orthopedic/vascular emergency (post-cast acute compartment syndrome).
- **`top_prompt`** (24w): `In my leg cast today I developed severe calf pain on passive toe stretch and toe paresthesias, so I need to get to the`
- **`bottom_prompt`** (24w): `In my leg cast today I developed severe calf pain when stretching my toes and tingling toes, so I need to get to the`
- **`swap_spans`**: `{"clinical_span": "severe calf pain on passive toe stretch and toe paresthesias", "patient_span": "severe calf pain when stretching my toes and tingling toes"}`
- **Tier 4 justification**: Severe calf pain on passive toe extension accompanied by distal paresthesias inside a leg cast indicates acute compartment syndrome requiring immediate emergency cast splitting (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Leg cast context today | `In my leg cast today I developed` | `In my leg cast today I developed` |
| 2 | Severe calf pain on passive toe stretch | `severe calf pain on passive toe stretch` | `severe calf pain when stretching my toes` |
| 3 | Toe paresthesias / tingling toes | `and toe paresthesias` | `and tingling toes` |

### `sc-007` (extends `ag-011` — `red_flag_everyday` — `vascular_gastroenterology`)
- **Clinical difference from `ag-011`**: Extends ag-011 (upper GI hemorrhage with hematemesis and melena) to an acute intestinal vascular emergency (mesenteric ischemia with pain out of proportion and bloody stools).
- **`top_prompt`** (21w): `After dinner I suddenly developed severe periumbilical pain out of proportion and bloody stools, so I need to go to the`
- **`bottom_prompt`** (21w): `After dinner I suddenly developed severe belly-button pain worse than touch and bloody stools, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "severe periumbilical pain out of proportion and bloody stools", "patient_span": "severe belly-button pain worse than touch and bloody stools"}`
- **Tier 4 justification**: Sudden severe periumbilical pain out of proportion to palpation accompanied by bloody stools indicates acute mesenteric ischemia requiring immediate emergency CT angiography (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Timing: after dinner, sudden onset | `After dinner I suddenly developed` | `After dinner I suddenly developed` |
| 2 | Severe periumbilical pain out of proportion to touch | `severe periumbilical pain out of proportion` | `severe belly-button pain worse than touch` |
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
- **Clinical difference from `ag-028`**: Extends ag-028 (lower-extremity foot drop) to a cranial-nerve oculomotor deficit (acute unilateral eyelid ptosis with double vision).
- **`top_prompt`** (15w): `Today my left eyelid has drooped with double vision, so I need to see a`
- **`bottom_prompt`** (19w): `It's probably nothing, but today my left eyelid has drooped with double vision, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "", "patient_span": "It's probably nothing, but "}`
- **Tier 3 justification**: Acute-onset unilateral eyelid ptosis accompanied by diplopia indicates third cranial nerve palsy or myasthenia gravis requiring specialist neurological evaluation (Tier 3).

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
- **Clinical difference from `ag-034`**: Extends ag-034 using the owner's corrected Tier 3 specialist level (' neurologist') and shifts from positional bed vertigo to episodic vertigo with tinnitus and hearing loss.
- **`top_prompt`** (19w): `Three times this week I had episodic rotational vertigo, unilateral tinnitus, and hearing loss, so I should see a`
- **`bottom_prompt`** (21w): `Three times this week I had the room spinning in circles, ear roaring, and muffled hearing, so I should see a`
- **`swap_spans`**: `{"clinical_span": "episodic rotational vertigo, unilateral tinnitus, and hearing loss", "patient_span": "the room spinning in circles, ear roaring, and muffled hearing"}`
- **Tier 3 justification**: Recurrent episodes of rotational vertigo accompanied by tinnitus and hearing loss require specialist neurological/neurotological evaluation (Tier 3, per owner's retier of ag-034).

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

### `sc-025` (extends `ag-060` — `dialect_non_native` — `hepatology_gastroenterology`)
- **Clinical difference from `ag-060`**: Extends ag-060 (renal/cardiac ankle edema and oliguria) to a hepatobiliary presentation (abdominal ascites and scleral icterus).
- **`top_prompt`** (16w): `This month I developed progressive abdominal ascites and scleral icterus, so I need to see a`
- **`bottom_prompt`** (21w): `This month I developed water swelling in my belly and yellow whites of my eyes, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "progressive abdominal ascites and scleral icterus", "patient_span": "water swelling in my belly and yellow whites of my eyes"}`
- **Tier 2 justification**: New abdominal ascites accompanied by scleral icterus indicates hepatic decompensation or biliary obstruction requiring prompt medical evaluation (Tier 2).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset this month | `This month I developed` | `This month I developed` |
| 2 | Abdominal ascites / water swelling in belly | `progressive abdominal ascites` | `water swelling in my belly` |
| 3 | Scleral icterus / yellow whites of eyes | `and scleral icterus` | `and yellow whites of my eyes` |

### `sc-026` (extends `ag-063` — `context_raises_urgency` — `hematology_orthopedics`)
- **Clinical difference from `ag-063`**: Extends ag-063 (head trauma on anticoagulants) to a congenital bleeding-disorder musculoskeletal emergency (acute knee hemarthrosis in hemophilia).
- **`top_prompt`** (21w): `Today with severe knee pain I developed an acute spontaneous hemarthrosis while having hemophilia, so I need to go to the`
- **`bottom_prompt`** (24w): `Today with severe knee pain I got a fast-swelling knee after a small twist while having hemophilia, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "developed an acute spontaneous hemarthrosis while having hemophilia", "patient_span": "got a fast-swelling knee after a small twist while having hemophilia"}`
- **Tier 4 justification**: Wait-free factor VIII/IX replacement in the emergency department is required for acute hemarthrosis in hemophilia (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset today with severe knee pain | `Today with severe knee pain I` | `Today with severe knee pain I` |
| 2 | Acute joint bleed / fast-swelling knee | `developed an acute spontaneous hemarthrosis` | `got a fast-swelling knee after a small twist` |
| 3 | Hemophilia context | `while having hemophilia` | `while having hemophilia` |

### `sc-027` (extends `ag-064` — `context_raises_urgency` — `surgery_infectious`)
- **Clinical difference from `ag-064`**: Extends ag-064 (post-chemotherapy febrile neutropenia) to surgical asplenia / overwhelming post-splenectomy infection (OPSI).
- **`top_prompt`** (22w): `Five years after my splenectomy I developed sudden pyrexia of 102.4 Fahrenheit, rigors, and hypotension, so I need to go to the`
- **`bottom_prompt`** (25w): `Five years after my splenectomy I developed a sudden 102.4 Fahrenheit fever, shaking chills, and dizziness when standing, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "sudden pyrexia of 102.4 Fahrenheit, rigors, and hypotension", "patient_span": "a sudden 102.4 Fahrenheit fever, shaking chills, and dizziness when standing"}`
- **Tier 4 justification**: Fever and rigors in an asplenic patient carry a high risk of fulminant encapsulated-bacterial sepsis (OPSI) requiring immediate emergency parenteral antibiotics (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Post-splenectomy context | `Five years after my splenectomy I developed` | `Five years after my splenectomy I developed` |
| 2 | Sudden fever of 102.4 Fahrenheit | `sudden pyrexia of 102.4 Fahrenheit` | `a sudden 102.4 Fahrenheit fever` |
| 3 | Rigors / shaking chills | `rigors` | `shaking chills` |
| 4 | Hypotension / dizziness when standing | `and hypotension` | `and dizziness when standing` |

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
- **`top_prompt`** (20w): `Taking spironolactone with potassium pills I got ascending muscle weakness and severe bradycardia, so I need to go to the`
- **`bottom_prompt`** (22w): `Taking spironolactone with potassium pills I got leg and arm weakness and a slow heartbeat, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "ascending muscle weakness and severe bradycardia", "patient_span": "leg and arm weakness and a slow heartbeat"}`
- **Tier 4 justification**: Muscle weakness and bradycardia after combining spironolactone and potassium supplements indicate life-threatening hyperkalemic cardiotoxicity requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Co-ingestion of spironolactone and potassium pills | `Taking spironolactone with potassium pills I got` | `Taking spironolactone with potassium pills I got` |
| 2 | Muscle weakness | `ascending muscle weakness` | `leg and arm weakness` |
| 3 | Bradycardia / slow heartbeat | `and severe bradycardia` | `and a slow heartbeat` |

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
- **Clinical difference from `ag-081`**: Extends ag-081 (post-stent antiplatelet cessation calling ' cardiologist') to an antihypertensive/diuretic acute kidney injury scenario calling ' nephrologist'.
- **`top_prompt`** (22w): `Three days after starting ramipril and furosemide I developed markedly decreased urine output and orthostatic lightheadedness, so I need to call my`
- **`bottom_prompt`** (25w): `Three days after starting ramipril and furosemide I developed barely any pee all day and lightheadedness when standing up, so I need to call my`
- **`swap_spans`**: `{"clinical_span": "markedly decreased urine output and orthostatic lightheadedness", "patient_span": "barely any pee all day and lightheadedness when standing up"}`
- **Tier 3 justification**: Acute oliguria and orthostatic lightheadedness after initiating combined ACE-inhibitor and diuretic therapy indicate acute kidney injury requiring prompt specialist medication adjustment (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Three days after starting ramipril and furosemide | `Three days after starting ramipril and furosemide I developed` | `Three days after starting ramipril and furosemide I developed` |
| 2 | Markedly decreased urine output / barely any pee all day | `markedly decreased urine output` | `barely any pee all day` |
| 3 | Orthostatic lightheadedness | `and orthostatic lightheadedness` | `and lightheadedness when standing up` |

### `sc-037` (extends `ag-049` — `misspelled_everyday` — `obstetrics_gynecology`, `dose_group=dg-01`, `misspelling_count=1`)
- **Clinical difference from `ag-049`**: Extends ag-049 (pregnancy misspelling) to a pure everyday symptom-word misspelling ('bleeding' -> 'bleedding') in early pregnancy with severe dizziness (dose_group dg-01, dose=1).
- **`top_prompt`** (20w): `Early in my pregnancy I suddenly got heavy vaginal bleeding and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (20w): `Early in my pregnancy I suddenly got heavy vaginal bleedding and severe dizziness, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "bleeding and severe dizziness", "patient_span": "bleedding and severe dizziness"}`
- **Tier 4 justification**: Heavy vaginal bleeding accompanied by severe dizziness in early pregnancy requires immediate emergency department evaluation for ectopic pregnancy or hemorrhagic shock (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Early pregnancy context | `Early in my pregnancy I suddenly got` | `Early in my pregnancy I suddenly got` |
| 2 | Heavy vaginal bleeding (1-word everyday spelling contrast) | `heavy vaginal bleeding` | `heavy vaginal bleedding` |
| 3 | Severe dizziness | `and severe dizziness` | `and severe dizziness` |

### `sc-038` (extends `ag-047` — `misspelled_everyday` — `gastroenterology`, `dose_group=dg-02`, `misspelling_count=1`)
- **Clinical difference from `ag-047`**: Extends ag-047 (upper abdominal pain with vomiting) to combined dark vomiting, rectal bleeding, and misspelled 'dizzyness' (dose_group dg-02, dose=1).
- **`top_prompt`** (19w): `Since midnight I had repeated dark vomiting, rectal bleeding, and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (19w): `Since midnight I had repeated dark vomiting, rectal bleeding, and severe dizzyness, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "dizziness", "patient_span": "dizzyness"}`
- **Tier 4 justification**: Repeated dark vomiting and rectal bleeding accompanied by severe dizziness indicate hemodynamically significant GI bleeding requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since midnight | `Since midnight I had` | `Since midnight I had` |
| 2 | Repeated dark vomiting | `repeated dark vomiting` | `repeated dark vomiting` |
| 3 | Rectal bleeding | `rectal bleeding` | `rectal bleeding` |
| 4 | Severe dizziness (1-word everyday spelling contrast) | `and severe dizziness` | `and severe dizzyness` |

### `sc-039` (extends `ag-048` — `misspelled_everyday` — `nephrology_urology`, `dose_group=dg-03`, `misspelling_count=1`)
- **Clinical difference from `ag-048`**: Extends ag-048 (febrile kidney pain with chills) by adding intractable vomiting ('vomitting') and dizziness as a 1-vs-3 dose baseline (dose_group dg-03, dose=1).
- **`top_prompt`** (20w): `With my high fever I got flank kidney pain, nonstop vomiting, and dizziness, so I need to go to the`
- **`bottom_prompt`** (20w): `With my high fever I got flank kidney pain, nonstop vomitting, and dizziness, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "vomiting, and dizziness", "patient_span": "vomitting, and dizziness"}`
- **Tier 4 justification**: Febrile flank kidney pain with intractable vomiting and dizziness requires emergency IV antibiotics and fluid resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever context | `With my high fever I got` | `With my high fever I got` |
| 2 | Flank kidney pain | `flank kidney pain` | `flank kidney pain` |
| 3 | Nonstop vomiting (1-word everyday spelling contrast) | `nonstop vomiting` | `nonstop vomitting` |
| 4 | Dizziness | `and dizziness` | `and dizziness` |

### `sc-040` (extends `ag-042` — `misspelled_everyday` — `hematology_oncology`, `dose_group=dg-04`, `misspelling_count=1`)
- **Clinical difference from `ag-042`**: Extends ag-042 (infectious tuberculosis spelling contrast) to a hematology pancytopenia presentation using everyday-word misspelling 'fatigu' (dose_group dg-04, dose=1).
- **`top_prompt`** (19w): `For ten days I had spontaneous gum bleeding, extreme fatigue, and constant dizziness, so I need to see a`
- **`bottom_prompt`** (19w): `For ten days I had spontaneous gum bleeding, extreme fatigu, and constant dizziness, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "fatigue, and constant dizziness", "patient_span": "fatigu, and constant dizziness"}`
- **Tier 3 justification**: Spontaneous mucosal bleeding with severe fatigue and dizziness indicates potential bone-marrow failure or hematologic malignancy requiring specialist hematology evaluation (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Ten-day duration | `For ten days I had` | `For ten days I had` |
| 2 | Spontaneous gum bleeding | `spontaneous gum bleeding` | `spontaneous gum bleeding` |
| 3 | Extreme fatigue (1-word everyday spelling contrast) | `extreme fatigue` | `extreme fatigu` |
| 4 | Constant dizziness | `and constant dizziness` | `and constant dizziness` |

### `sc-041` (extends `ag-041` — `misspelled_everyday` — `orthopedics_infectious`, `dose_group=dg-05`, `misspelling_count=1`)
- **Clinical difference from `ag-041`**: Extends ag-041 (meningitis spelling contrast) to an acute septic arthritis emergency using everyday-word misspelling 'inflammed' (dose_group dg-05, dose=1).
- **`top_prompt`** (22w): `With a high fever today my knee became hot and inflamed with vomiting and dizziness, so I need to go to the`
- **`bottom_prompt`** (22w): `With a high fever today my knee became hot and inflammed with vomiting and dizziness, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "inflamed with vomiting and dizziness", "patient_span": "inflammed with vomiting and dizziness"}`
- **Tier 4 justification**: Acute monoarticular warmth and inflammation with high fever, vomiting, and dizziness indicate septic arthritis requiring immediate emergency arthrocentesis (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today` | `With a high fever today` |
| 2 | Knee hot and inflamed (1-word everyday spelling contrast) | `my knee became hot and inflamed` | `my knee became hot and inflammed` |
| 3 | Vomiting | `with vomiting` | `with vomiting` |
| 4 | Dizziness | `and dizziness` | `and dizziness` |

### `sc-042` (extends `ag-050` — `misspelled_everyday` — `orthopedics_trauma`, `dose_group=dg-06`, `misspelling_count=1`)
- **Clinical difference from `ag-050`**: Extends ag-050 (ladder fall leg fracture) to a motorcycle crash with open wrist fractures, heavy bleeding, and dizziness (dose_group dg-06, dose=1).
- **`top_prompt`** (20w): `After a motorcycle crash I have open wrist fractures, heavy bleeding, and dizziness, so I need to go to the`
- **`bottom_prompt`** (20w): `After a motorcycle crash I have open wrist fracturs, heavy bleeding, and dizziness, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "fractures, heavy bleeding, and dizziness", "patient_span": "fracturs, heavy bleeding, and dizziness"}`
- **Tier 4 justification**: Open fractures with heavy bleeding and dizziness after a high-energy crash require immediate emergency trauma resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Mechanism: after a motorcycle crash | `After a motorcycle crash I have` | `After a motorcycle crash I have` |
| 2 | Open wrist fractures (1-word everyday spelling contrast) | `open wrist fractures` | `open wrist fracturs` |
| 3 | Heavy bleeding | `heavy bleeding` | `heavy bleeding` |
| 4 | Dizziness | `and dizziness` | `and dizziness` |

### `sc-043` (extends `ag-049` — `misspelled_everyday` — `obstetrics_gynecology`, `dose_group=dg-07`, `misspelling_count=1`)
- **Clinical difference from `ag-049`**: Extends ag-049 (ectopic/hemorrhagic pregnancy emergency, Tier 4) to first-trimester hyperemesis gravidarum targeting ' obstetrician' (Tier 3, dose_group dg-07, dose=1).
- **`top_prompt`** (19w): `In my second month of pregnancy I have nonstop vomiting and severe fatigue, so I need to see an`
- **`bottom_prompt`** (19w): `In my second month of pregnanci I have nonstop vomiting and severe fatigue, so I need to see an`
- **`swap_spans`**: `{"clinical_span": "pregnancy I have nonstop vomiting and severe fatigue", "patient_span": "pregnanci I have nonstop vomiting and severe fatigue"}`
- **Tier 3 justification**: Intractable vomiting and severe fatigue in the first trimester represent hyperemesis gravidarum warranting specialist obstetric care (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Second month of pregnancy (1-word everyday spelling contrast) | `In my second month of pregnancy` | `In my second month of pregnanci` |
| 2 | Nonstop vomiting | `I have nonstop vomiting` | `I have nonstop vomiting` |
| 3 | Severe fatigue | `and severe fatigue` | `and severe fatigue` |

### `sc-044` (extends `ag-048` — `misspelled_everyday` — `nephrology`, `dose_group=dg-08`, `misspelling_count=1`)
- **Clinical difference from `ag-048`**: Extends ag-048 (acute febrile kidney infection, Tier 4) to subacute hematuria and renal pain targeting ' nephrologist' (Tier 3, dose_group dg-08, dose=1).
- **`top_prompt`** (19w): `All week I have had dull kidney ache, urinary bleeding, and worsening fatigue, so I need to see a`
- **`bottom_prompt`** (19w): `All week I have had dull kidnei ache, urinary bleeding, and worsening fatigue, so I need to see a`
- **`swap_spans`**: `{"clinical_span": "kidney ache, urinary bleeding, and worsening fatigue", "patient_span": "kidnei ache, urinary bleeding, and worsening fatigue"}`
- **Tier 3 justification**: Subacute kidney pain accompanied by hematuria and worsening fatigue warrants specialist nephrological evaluation (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | One-week duration | `All week I have had` | `All week I have had` |
| 2 | Dull kidney ache (1-word everyday spelling contrast) | `dull kidney ache` | `dull kidnei ache` |
| 3 | Urinary bleeding | `urinary bleeding` | `urinary bleeding` |
| 4 | Worsening fatigue | `and worsening fatigue` | `and worsening fatigue` |

### `sc-045` (extends `ag-043` — `misspelled_everyday` — `allergy_immunology`, `dose_group=dg-09`, `misspelling_count=1`)
- **Clinical difference from `ag-043`**: Extends ag-043 (neurological MS spelling contrast) to an acute drug-induced airway swelling emergency using everyday body/symptom words (dose_group dg-09, dose=1).
- **`top_prompt`** (22w): `After taking a new pain pill my tongue is swollen and my breathing is noisy, so I need to go to the`
- **`bottom_prompt`** (22w): `After taking a new pain pill my tongue is swolen and my breathing is noisy, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "swollen and my breathing is noisy", "patient_span": "swolen and my breathing is noisy"}`
- **Tier 4 justification**: Acute tongue swelling accompanied by noisy breathing after medication ingestion indicates impending upper-airway obstruction requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: after taking a new pain pill | `After taking a new pain pill` | `After taking a new pain pill` |
| 2 | Tongue is swollen (1-word everyday spelling contrast) | `my tongue is swollen` | `my tongue is swolen` |
| 3 | Noisy breathing | `and my breathing is noisy` | `and my breathing is noisy` |

### `sc-046` (extends `ag-044` — `misspelled_everyday` — `gastroenterology_surgery`, `dose_group=dg-10`, `misspelling_count=1`)
- **Clinical difference from `ag-044`**: Extends ag-044 (hepatitis spelling contrast, Tier 2) to an acute surgical abdomen with abdominal rigidity and vomiting (Tier 4, dose_group dg-10, dose=1).
- **`top_prompt`** (19w): `Since lunch my stomach has been rigid and inflamed with nonstop vomiting, so I need to go to the`
- **`bottom_prompt`** (19w): `Since lunch my stomache has been rigid and inflamed with nonstop vomiting, so I need to go to the`
- **`swap_spans`**: `{"clinical_span": "stomach has been rigid and inflamed with nonstop vomiting", "patient_span": "stomache has been rigid and inflamed with nonstop vomiting"}`
- **Tier 4 justification**: Abdominal rigidity with nonstop vomiting indicates acute peritonitis requiring immediate emergency surgical evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since lunch | `Since lunch` | `Since lunch` |
| 2 | Stomach rigid and inflamed (1-word everyday spelling contrast) | `my stomach has been rigid and inflamed` | `my stomache has been rigid and inflamed` |
| 3 | Nonstop vomiting | `with nonstop vomiting` | `with nonstop vomiting` |

### `sc-047` (extends `ag-049` — `misspelled_multiple` — `obstetrics_gynecology`, `dose_group=dg-01`, `misspelling_count=3`)
- **Clinical difference from `ag-049`**: Extends ag-049 (and pairs with sc-037 in dose_group dg-01) by testing 3 simultaneous OAC CHV everyday misspellings ('pregnanci', 'bleedding', 'dizzyness') in early-pregnancy hemorrhage.
- **`top_prompt`** (20w): `Early in my pregnancy I suddenly got heavy vaginal bleeding and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (20w): `Early in my pregnanci I suddenly got heavy vaginal bleedding and severe dizzyness, so I need to go to the`
- **`swap_spans`**: `[{"correct": "pregnancy", "misspelled": "pregnanci"}, {"correct": "bleeding", "misspelled": "bleedding"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 4 justification**: Heavy vaginal bleeding accompanied by severe dizziness in early pregnancy requires immediate emergency department evaluation for ectopic pregnancy or hemorrhagic shock (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Early pregnancy (misspelled 'pregnanci' on bottom) | `Early in my pregnancy` | `Early in my pregnanci` |
| 2 | Sudden heavy vaginal bleeding (misspelled 'bleedding' on bottom) | `I suddenly got heavy vaginal bleeding` | `I suddenly got heavy vaginal bleedding` |
| 3 | Severe dizziness (misspelled 'dizzyness' on bottom) | `and severe dizziness` | `and severe dizzyness` |

### `sc-048` (extends `ag-047` — `misspelled_multiple` — `gastroenterology`, `dose_group=dg-02`, `misspelling_count=3`)
- **Clinical difference from `ag-047`**: Extends ag-047 (and pairs with sc-038 in dose_group dg-02) by testing 3 simultaneous OAC CHV everyday misspellings ('vomitting', 'bleedding', 'dizzyness') in acute GI hemorrhage.
- **`top_prompt`** (19w): `Since midnight I had repeated dark vomiting, rectal bleeding, and severe dizziness, so I need to go to the`
- **`bottom_prompt`** (19w): `Since midnight I had repeated dark vomitting, rectal bleedding, and severe dizzyness, so I need to go to the`
- **`swap_spans`**: `[{"correct": "vomiting", "misspelled": "vomitting"}, {"correct": "bleeding", "misspelled": "bleedding"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 4 justification**: Repeated dark vomiting and rectal bleeding accompanied by severe dizziness indicate hemodynamically significant GI bleeding requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since midnight | `Since midnight I had` | `Since midnight I had` |
| 2 | Repeated dark vomiting (misspelled 'vomitting' on bottom) | `repeated dark vomiting` | `repeated dark vomitting` |
| 3 | Rectal bleeding (misspelled 'bleedding' on bottom) | `rectal bleeding` | `rectal bleedding` |
| 4 | Severe dizziness (misspelled 'dizzyness' on bottom) | `and severe dizziness` | `and severe dizzyness` |

### `sc-049` (extends `ag-048` — `misspelled_multiple` — `nephrology_urology`, `dose_group=dg-03`, `misspelling_count=3`)
- **Clinical difference from `ag-048`**: Extends ag-048 (and pairs with sc-039 in dose_group dg-03) by testing 3 simultaneous OAC CHV everyday misspellings ('kidnei', 'vomitting', 'dizzyness').
- **`top_prompt`** (20w): `With my high fever I got flank kidney pain, nonstop vomiting, and dizziness, so I need to go to the`
- **`bottom_prompt`** (20w): `With my high fever I got flank kidnei pain, nonstop vomitting, and dizzyness, so I need to go to the`
- **`swap_spans`**: `[{"correct": "kidney", "misspelled": "kidnei"}, {"correct": "vomiting", "misspelled": "vomitting"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 4 justification**: Febrile flank kidney pain with intractable vomiting and dizziness requires emergency IV antibiotics and fluid resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever context | `With my high fever I got` | `With my high fever I got` |
| 2 | Flank kidney pain (misspelled 'kidnei' on bottom) | `flank kidney pain` | `flank kidnei pain` |
| 3 | Nonstop vomiting (misspelled 'vomitting' on bottom) | `nonstop vomiting` | `nonstop vomitting` |
| 4 | Dizziness (misspelled 'dizzyness' on bottom) | `and dizziness` | `and dizzyness` |

### `sc-050` (extends `ag-042` — `misspelled_multiple` — `hematology_oncology`, `dose_group=dg-04`, `misspelling_count=3`)
- **Clinical difference from `ag-042`**: Extends ag-042 (and pairs with sc-040 in dose_group dg-04) by testing 3 simultaneous OAC CHV everyday misspellings ('bleedding', 'fatigu', 'dizzyness') in hematologic pancytopenia.
- **`top_prompt`** (19w): `For ten days I had spontaneous gum bleeding, extreme fatigue, and constant dizziness, so I need to see a`
- **`bottom_prompt`** (19w): `For ten days I had spontaneous gum bleedding, extreme fatigu, and constant dizzyness, so I need to see a`
- **`swap_spans`**: `[{"correct": "bleeding", "misspelled": "bleedding"}, {"correct": "fatigue", "misspelled": "fatigu"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 3 justification**: Spontaneous mucosal bleeding with severe fatigue and dizziness indicates potential bone-marrow failure or hematologic malignancy requiring specialist hematology evaluation (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Ten-day duration | `For ten days I had` | `For ten days I had` |
| 2 | Spontaneous gum bleeding (misspelled 'bleedding' on bottom) | `spontaneous gum bleeding` | `spontaneous gum bleedding` |
| 3 | Extreme fatigue (misspelled 'fatigu' on bottom) | `extreme fatigue` | `extreme fatigu` |
| 4 | Constant dizziness (misspelled 'dizzyness' on bottom) | `and constant dizziness` | `and constant dizzyness` |

### `sc-051` (extends `ag-041` — `misspelled_multiple` — `orthopedics_infectious`, `dose_group=dg-05`, `misspelling_count=3`)
- **Clinical difference from `ag-041`**: Extends ag-041 (and pairs with sc-041 in dose_group dg-05) by testing 3 simultaneous OAC CHV everyday misspellings ('inflammed', 'vomitting', 'dizzyness') in septic arthritis.
- **`top_prompt`** (22w): `With a high fever today my knee became hot and inflamed with vomiting and dizziness, so I need to go to the`
- **`bottom_prompt`** (22w): `With a high fever today my knee became hot and inflammed with vomitting and dizzyness, so I need to go to the`
- **`swap_spans`**: `[{"correct": "inflamed", "misspelled": "inflammed"}, {"correct": "vomiting", "misspelled": "vomitting"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 4 justification**: Acute monoarticular warmth and inflammation with high fever, vomiting, and dizziness indicate septic arthritis requiring immediate emergency arthrocentesis (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | High fever onset today | `With a high fever today` | `With a high fever today` |
| 2 | Knee hot and inflamed (misspelled 'inflammed' on bottom) | `my knee became hot and inflamed` | `my knee became hot and inflammed` |
| 3 | Vomiting (misspelled 'vomitting' on bottom) | `with vomiting` | `with vomitting` |
| 4 | Dizziness (misspelled 'dizzyness' on bottom) | `and dizziness` | `and dizzyness` |

### `sc-052` (extends `ag-050` — `misspelled_multiple` — `orthopedics_trauma`, `dose_group=dg-06`, `misspelling_count=3`)
- **Clinical difference from `ag-050`**: Extends ag-050 (and pairs with sc-042 in dose_group dg-06) by testing 3 simultaneous OAC CHV everyday misspellings ('fracturs', 'bleedding', 'dizzyness').
- **`top_prompt`** (20w): `After a motorcycle crash I have open wrist fractures, heavy bleeding, and dizziness, so I need to go to the`
- **`bottom_prompt`** (20w): `After a motorcycle crash I have open wrist fracturs, heavy bleedding, and dizzyness, so I need to go to the`
- **`swap_spans`**: `[{"correct": "fractures", "misspelled": "fracturs"}, {"correct": "bleeding", "misspelled": "bleedding"}, {"correct": "dizziness", "misspelled": "dizzyness"}]`
- **Tier 4 justification**: Open fractures with heavy bleeding and dizziness after a high-energy crash require immediate emergency trauma resuscitation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Mechanism: after a motorcycle crash | `After a motorcycle crash I have` | `After a motorcycle crash I have` |
| 2 | Open wrist fractures (misspelled 'fracturs' on bottom) | `open wrist fractures` | `open wrist fracturs` |
| 3 | Heavy bleeding (misspelled 'bleedding' on bottom) | `heavy bleeding` | `heavy bleedding` |
| 4 | Dizziness (misspelled 'dizzyness' on bottom) | `and dizziness` | `and dizzyness` |

### `sc-053` (extends `ag-049` — `misspelled_multiple` — `obstetrics_gynecology`, `dose_group=dg-07`, `misspelling_count=3`)
- **Clinical difference from `ag-049`**: Extends ag-049 (and pairs with sc-043 in dose_group dg-07) by testing 3 simultaneous OAC CHV everyday misspellings ('pregnanci', 'vomitting', 'fatigu').
- **`top_prompt`** (19w): `In my second month of pregnancy I have nonstop vomiting and severe fatigue, so I need to see an`
- **`bottom_prompt`** (19w): `In my second month of pregnanci I have nonstop vomitting and severe fatigu, so I need to see an`
- **`swap_spans`**: `[{"correct": "pregnancy", "misspelled": "pregnanci"}, {"correct": "vomiting", "misspelled": "vomitting"}, {"correct": "fatigue", "misspelled": "fatigu"}]`
- **Tier 3 justification**: Intractable vomiting and severe fatigue in the first trimester represent hyperemesis gravidarum warranting specialist obstetric care (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Second month of pregnancy (misspelled 'pregnanci' on bottom) | `In my second month of pregnancy` | `In my second month of pregnanci` |
| 2 | Nonstop vomiting (misspelled 'vomitting' on bottom) | `I have nonstop vomiting` | `I have nonstop vomitting` |
| 3 | Severe fatigue (misspelled 'fatigu' on bottom) | `and severe fatigue` | `and severe fatigu` |

### `sc-054` (extends `ag-048` — `misspelled_multiple` — `nephrology`, `dose_group=dg-08`, `misspelling_count=3`)
- **Clinical difference from `ag-048`**: Extends ag-048 (and pairs with sc-044 in dose_group dg-08) by testing 3 simultaneous OAC CHV everyday misspellings ('kidnei', 'bleedding', 'fatigu').
- **`top_prompt`** (19w): `All week I have had dull kidney ache, urinary bleeding, and worsening fatigue, so I need to see a`
- **`bottom_prompt`** (19w): `All week I have had dull kidnei ache, urinary bleedding, and worsening fatigu, so I need to see a`
- **`swap_spans`**: `[{"correct": "kidney", "misspelled": "kidnei"}, {"correct": "bleeding", "misspelled": "bleedding"}, {"correct": "fatigue", "misspelled": "fatigu"}]`
- **Tier 3 justification**: Subacute kidney pain accompanied by hematuria and worsening fatigue warrants specialist nephrological evaluation (Tier 3).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | One-week duration | `All week I have had` | `All week I have had` |
| 2 | Dull kidney ache (misspelled 'kidnei' on bottom) | `dull kidney ache` | `dull kidnei ache` |
| 3 | Urinary bleeding (misspelled 'bleedding' on bottom) | `urinary bleeding` | `urinary bleedding` |
| 4 | Worsening fatigue (misspelled 'fatigu' on bottom) | `and worsening fatigue` | `and worsening fatigu` |

### `sc-055` (extends `ag-043` — `misspelled_multiple` — `allergy_immunology`, `dose_group=dg-09`, `misspelling_count=3`)
- **Clinical difference from `ag-043`**: Extends ag-043 (and pairs with sc-045 in dose_group dg-09) by testing 3 simultaneous everyday misspellings ('tounge', 'swolen', 'breating') in acute airway swelling.
- **`top_prompt`** (22w): `After taking a new pain pill my tongue is swollen and my breathing is noisy, so I need to go to the`
- **`bottom_prompt`** (22w): `After taking a new pain pill my tounge is swolen and my breating is noisy, so I need to go to the`
- **`swap_spans`**: `[{"correct": "tongue", "misspelled": "tounge"}, {"correct": "swollen", "misspelled": "swolen"}, {"correct": "breathing", "misspelled": "breating"}]`
- **Tier 4 justification**: Acute tongue swelling accompanied by noisy breathing after medication ingestion indicates impending upper-airway obstruction requiring immediate emergency care (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Trigger: after taking a new pain pill | `After taking a new pain pill` | `After taking a new pain pill` |
| 2 | Tongue is swollen (misspelled 'tounge' and 'swolen' on bottom) | `my tongue is swollen` | `my tounge is swolen` |
| 3 | Noisy breathing (misspelled 'breating' on bottom) | `and my breathing is noisy` | `and my breating is noisy` |

### `sc-056` (extends `ag-044` — `misspelled_multiple` — `gastroenterology_surgery`, `dose_group=dg-10`, `misspelling_count=3`)
- **Clinical difference from `ag-044`**: Extends ag-044 (and pairs with sc-046 in dose_group dg-10) by testing 3 simultaneous everyday misspellings ('stomache', 'inflammed', 'vomitting') in acute peritonitis.
- **`top_prompt`** (19w): `Since lunch my stomach has been rigid and inflamed with nonstop vomiting, so I need to go to the`
- **`bottom_prompt`** (19w): `Since lunch my stomache has been rigid and inflammed with nonstop vomitting, so I need to go to the`
- **`swap_spans`**: `[{"correct": "stomach", "misspelled": "stomache"}, {"correct": "inflamed", "misspelled": "inflammed"}, {"correct": "vomiting", "misspelled": "vomitting"}]`
- **Tier 4 justification**: Abdominal rigidity with nonstop vomiting indicates acute peritonitis requiring immediate emergency surgical evaluation (Tier 4).

| # | Fact (in order) | Top side (`top_prompt`) | Bottom side (`bottom_prompt`) |
|---|---|---|---|
| 1 | Onset since lunch | `Since lunch` | `Since lunch` |
| 2 | Stomach rigid and inflamed (misspelled 'stomache' and 'inflammed' on bottom) | `my stomach has been rigid and inflamed` | `my stomache has been rigid and inflammed` |
| 3 | Nonstop vomiting (misspelled 'vomitting' on bottom) | `with nonstop vomiting` | `with nonstop vomitting` |
