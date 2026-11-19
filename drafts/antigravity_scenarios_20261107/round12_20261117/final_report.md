# Round 12 Final Report (`round12_20261117`)

> **Draft status notice:** All 48 case families produced in Round 12 (`r12-001` to `r12-048`) are outcome-blind synthetic drafts awaiting an owner's read, a clinician's review, and a patient-language review. None of these families are clinically reviewed or patient-language reviewed; all audit files (`G4`–`G8`) record model readings only.

## 1. Commits Pushed and Stop Rule Triggered

- **Branch:** `draft/antigravity-scenarios-20261107`
- **Batch 01 commit (`r12-001`..`r12-024`):** `15cf3222` (`Round 12 batch 01: 24 families, 0 dropped`)
- **Batch 02 commit (`r12-025`..`r12-048`):** `6c3ffe77` (`Round 12 batch 02: 24 families, 0 dropped`)
- **Post-push revisions (`revisions.json`):** `0` entries (`[]`; no pushed family was edited).
- **Inter-batch `reviewer_notes.md` check:** After pushing `batch_01` (`15cf3222`), `git pull` on `draft/antigravity-scenarios-20261107` and `git -C ../pw-main pull` (`e6618a02`) were run. `round12_20261117/reviewer_notes.md` (which, when present, holds corrections from a Claude review session — a model's review, not the owner's) was absent, so the run continued directly to `batch_02` per `SPEC.md` section 9.
- **Stop rule triggered:** **Stop Rule 5** (`SPEC.md` section 9: *"Batch 02 is pushed"*).
  - Stop Rule 1 (`< 16` families passing in a batch): did **not** trigger (`24` in `batch_01`, `24` in `batch_02`).
  - Stop Rule 2 (`> 6` families dropped at the same gate in a batch): did **not** trigger (`0` dropped in either batch).
  - Stop Rule 3 (non-existent citation or absent evidence sentence in a G7-passed family): did **not** trigger.
  - Stop Rule 4 (any agent opening a Hard Limit 2 measured-outcome or holdout path): did **not** trigger (`0` forbidden paths opened).

---

## 2. Families Planned, Passed, and Dropped by Care Level

Every slot in Round 12 is a plain register family (`lexicon_entries: []`, zero dialect lexicon forms, zero self-care families). Twelve reserve slots (`6` per batch in `plan.json`) were prepared before authoring and `0` were needed.

| Scope | Care Level (`right_care`) | Planned | Passed (`G1`–`G8`) | Returned Once & Revised | Dropped |
|---|---:|---:|---:|---:|---:|
| `batch_01` (`r12-001`..`r12-024`) | `4` (emergency) | `8` | `8` | `1` (`r12-002`) | `0` |
| `batch_01` (`r12-001`..`r12-024`) | `3` (specialist) | `8` | `8` | `0` | `0` |
| `batch_01` (`r12-001`..`r12-024`) | `2` (general doctor) | `8` | `8` | `5` (`r12-017`, `r12-019`, `r12-022`, `r12-023`, `r12-024`) | `0` |
| **`batch_01` subtotal** | **All (`2`–`4`)** | **`24`** | **`24`** | **`6`** | **`0`** |
| `batch_02` (`r12-025`..`r12-048`) | `4` (emergency) | `8` | `8` | `2` (`r12-025`, `r12-026`) | `0` |
| `batch_02` (`r12-025`..`r12-048`) | `3` (specialist) | `8` | `8` | `0` | `0` |
| `batch_02` (`r12-025`..`r12-048`) | `2` (general doctor) | `8` | `8` | `3` (`r12-044`, `r12-046`, `r12-048`) | `0` |
| **`batch_02` subtotal** | **All (`2`–`4`)** | **`24`** | **`24`** | **`5`** | **`0`** |
| **Round 12 total** | **`4` (emergency)** | **`16`** | **`16`** | **`3`** | **`0`** |
| **Round 12 total** | **`3` (specialist)** | **`16`** | **`16`** | **`0`** | **`0`** |
| **Round 12 total** | **`2` (general doctor)** | **`16`** | **`16`** | **`8`** | **`0`** |
| **Round 12 grand total** | **All (`2`–`4`)** | **`48`** | **`48`** | **`11`** | **`0`** |

---

## 3. Drops by Gate and Single-Return Audit Revisions

- **Drops by gate (`G1`–`G8`):** `0` families dropped in `batch_01`; `0` families dropped in `batch_02`; `0` total.
- **Single-return revisions (`returned_count = 1`, `0` repeat gate failures):**
  - **`batch_01` (`6` families):**
    - `r12-002` (`G5`): changed `'look'` to `'have looked'` with `'over 8 months'` in `texts.changed_fact`.
    - `r12-017` (`G5`): moved `'for 6 weeks'` directly after `'each night'` so relative clause `'that eases when walking'` attaches to the symptom.
    - `r12-019` (`G5` + `G7` Rule B): fixed singular `'edema'` vs plural `'them'` agreement, smoothed `'swelling in both my ankles'`, and replaced investigator survey question (`PMID: 19251582`) with verbatim patient quote in Carter et al. 2022 (`PMID: 35005435`).
    - `r12-022` (`G5`): replaced bare participial splice `'Im 39 using'` with `'Im 39 and use'` in `texts.everyday_paraphrase`.
    - `r12-023` (`G5`): replaced `'I delivered 3 weeks ago while breastfeeding'` with `'I delivered 3 weeks ago and breastfeed'` in `texts.medical_paraphrase`.
    - `r12-024` (`G5`): changed `'for 3 weeks I got'` to `'for 3 weeks I have had'` and reordered `'on my inner wrists and between my fingers'`.
  - **`batch_02` (`5` families):**
    - `r12-025` (`G5` + `G6` Rule A): fixed first-person subject agreement (`'Im 34 and had ... and I have had'`) and anchored the `changed_fact` control (`'felt mild tiredness in my legs for 1 hour the day that diarrhea ended'`) directly to the resolved diarrhea without adding an unstated jogging trigger.
    - `r12-026` (`G5`): changed `'5 days after birth'` to `'5 days after giving birth'` and unstacked `'my blood pressure on my home arm cuff'`.
    - `r12-044` (`G7` Rule B): narrowed `everyday_sources[0].expression` to attested `'swollen'` (`PMID: 37915422`) and marked unattested words `"source": "none"`.
    - `r12-046` (`G7` Rule B): narrowed `everyday_sources[0].expression` to attested `'yellow green'` (`PMID: 40349003`) and marked unattested words `"source": "none"`.
    - `r12-048` (`G7` verbatim quote + Rule B): replaced condensed sentence with exact verbatim abstract sentence (`PMID: 38395028`) and narrowed `expression` to `'discharge'`.

---

## 4. Citation Share, Dictionaries Cited, and Source Fit

- **Dictionaries actually cited in Round 12 (`SPEC.md` section 7):** **Wiktionary** (`3` rows in `batch_01`, `7` rows in `batch_02`; `10` total) and **Cambridge Dictionary** (`0` rows in `batch_01`, `1` row in `batch_02`; `1` total). No other dictionaries were cited.
- **Literature sources cited:** `22` PubMed records in `batch_01` and `15` PubMed records in `batch_02` (`37` PubMed rows total; `0` title-only records; `0` non-PMID/DOI database identifiers).

| Scope | Everyday Expressions Cited | Attribution Clauses Cited | Combined Rows Cited | `same` Fit | `adjacent` Fit | `different` Fit |
|---|---:|---:|---:|---:|---:|---:|
| `batch_01` | `22/59` (`37.3%`) | `3/16` (`18.8%`) | `25/75` (`33.3%`) | `19/25` (`76.0%`) | `6/25` (`24.0%`) | `0/25` (`0.0%`) |
| `batch_02` | `22/67` (`32.8%`) | `1/16` (`6.2%`) | `23/83` (`27.7%`) | `10/23` (`43.5%`) | `13/23` (`56.5%`) | `0/23` (`0.0%`) |
| **Round 12 total** | **`44/126` (`34.9%`)** | **`4/32` (`12.5%`)** | **`48/158` (`30.4%`)** | **`29/48` (`60.4%`)** | **`19/48` (`39.6%`)** | **`0/48` (`0.0%`)** |

*(Note on `batch_02` source fit: among the `15` PubMed citations in `batch_02`, `10/15` [`66.7%`] have `same` population fit and `5/15` have `adjacent` fit; all `8` dictionary lexical definitions [`7` Wiktionary, `1` Cambridge Dictionary] are conservatively recorded as `adjacent` because lexical entries do not specify clinical study populations, yielding `10/23` [`43.5%`] overall in `batch_02` and `29/48` [`60.4%`] across Round 12.)*

---

## 5. Unsourced Expressions and Attribution Clauses (`110` Total)

`batch_01` has `50` unsourced rows and `batch_02` has `60` unsourced rows (`110` total marked `"source": "none"`):

| Family | Kind | Unsourced Phrase |
|---|---|---|
| `r12-001` | everyday expression | `"my resting pulse is 32 beats a minute"` |
| `r12-002` | everyday expression | `"suddenly lost all sight in my right eye"` |
| `r12-002` | attribution clause | `"and I think it is tired eyes"` |
| `r12-003` | everyday expression | `"swallowed a coin sized lithium button battery from the TV remote"` |
| `r12-003` | everyday expression | `"1 soft ripe raspberry"` |
| `r12-003` | attribution clause | `"and I think it looked like candy"` |
| `r12-004` | attribution clause | `"and I think it is from cold air"` |
| `r12-006` | everyday expression | `"a sudden big gush of clear fluid from my vagina"` |
| `r12-006` | everyday expression | `"let out 3 drops of pee once when I laughed"` |
| `r12-006` | attribution clause | `"and I think it is bladder pressure"` |
| `r12-007` | everyday expression | `"very painful fast spreading purple gray blisters"` |
| `r12-007` | everyday expression | `"have had a 1 cm soft rubbery lump on my right thigh for 3 weeks"` |
| `r12-007` | attribution clause | `"and I think it is chafing"` |
| `r12-008` | everyday expression | `"woke up with mild muscle stiffness in the back of my neck this morning"` |
| `r12-008` | attribution clause | `"and I think I pulled something"` |
| `r12-009` | everyday expression | `"my front hairline has crept back with flaking around the roots"` |
| `r12-009` | everyday expression | `"my front hairline felt mildly tight for 1 hour after braiding"` |
| `r12-009` | attribution clause | `"and I think my braids were tight"` |
| `r12-010` | everyday expression | `"sharp pain has shot through my upper right back tooth when I let off my bite"` |
| `r12-010` | everyday expression | `"1 time yesterday I felt brief mild pressure in my upper right back tooth"` |
| `r12-010` | attribution clause | `"and I think I bit a hard kernel"` |
| `r12-011` | everyday expression | `"breathe through my mouth"` |
| `r12-011` | everyday expression | `"can barely speak 2 words per breath sitting still"` |
| `r12-011` | attribution clause | `"and I think it is dust"` |
| `r12-012` | everyday expression | `"my tongue keeps poking out on its own"` |
| `r12-012` | everyday expression | `"my tongue locked stiff in my mouth muffling my voice"` |
| `r12-012` | attribution clause | `"and I think it is dry mouth"` |
| `r12-013` | everyday expression | `"kept them sorted neatly inside 2 small boxes on my hallway shelf"` |
| `r12-013` | attribution clause | `"and I think it is sentimentality"` |
| `r12-014` | everyday expression | `"I have had a small flat skin callus in my right palm below my ring finger"` |
| `r12-015` | everyday expression | `"for 2 days mild ashy dryness has appeared"` |
| `r12-015` | attribution clause | `"and I think it is laundry soap"` |
| `r12-016` | everyday expression | `"15 second breathing stops"` |
| `r12-016` | everyday expression | `"heard soft quiet snoring on 2 nights last week"` |
| `r12-016` | attribution clause | `"and I think it is long work hours"` |
| `r12-017` | everyday expression | `"1 evening last month I felt a 10 second urge to stretch both calves that passed right away"` |
| `r12-018` | everyday expression | `"a rough red rash on his chest"` |
| `r12-018` | everyday expression | `"his throat swelled nearly shut with continuous drooling today"` |
| `r12-019` | everyday expression | `"leaving a thumb dent when I press them"` |
| `r12-019` | everyday expression | `"noticed slight puffiness around both ankles for 10 minutes on 1 afternoon last week"` |
| `r12-020` | everyday expression | `"a soft squishy 4 cm fluid pouch on the back tip of my left elbow"` |
| `r12-020` | everyday expression | `"had a small red leaning mark on the back tip of my left elbow yesterday that faded within 8 minutes"` |
| `r12-021` | everyday expression | `"the sole of my right foot turned ice cold and dusky slate gray today"` |
| `r12-022` | everyday expression | `"painful cracked sores at both corners of my mouth"` |
| `r12-022` | everyday expression | `"had mild dry chapping at both corners of my mouth for 1 day last week"` |
| `r12-023` | everyday expression | `"gave birth 3 weeks ago"` |
| `r12-023` | everyday expression | `"a warm tender wedge shaped red patch on the outer side of my left breast"` |
| `r12-023` | everyday expression | `"my left breast felt slightly full before a feeding and softened right after nursing"` |
| `r12-024` | everyday expression | `"tiny wavy lines on my wrists and between my fingers"` |
| `r12-024` | everyday expression | `"hot swelling locked my fingers bent today"` |
| `r12-025` | everyday expression | `"felt mild tiredness in my legs for 1 hour the day that diarrhea ended"` |
| `r12-025` | attribution clause | `"and I think it is dehydration"` |
| `r12-026` | everyday expression | `"after giving birth"` |
| `r12-026` | everyday expression | `"my blood pressure on my home arm cuff is 178 over 114 at rest"` |
| `r12-026` | attribution clause | `"and I think it is stress"` |
| `r12-027` | everyday expression | `"all around my right hand and fingers making big tight blisters"` |
| `r12-027` | everyday expression | `"got 1 tiny pink drop mark on my right hand from warm soup that stopped stinging in 1 minute"` |
| `r12-027` | attribution clause | `"and I think it is steam"` |
| `r12-028` | everyday expression | `"felt warm to the touch"` |
| `r12-028` | everyday expression | `"a temperature of 39 degrees Celsius in his bottom"` |
| `r12-028` | attribution clause | `"and I think it is his blanket"` |
| `r12-029` | everyday expression | `"saliva started pouring nonstop from my mouth"` |
| `r12-029` | everyday expression | `"my mouth felt mildly dry for 10 minutes this afternoon"` |
| `r12-029` | attribution clause | `"and I think it is the heat"` |
| `r12-030` | everyday expression | `"got suddenly confused about where he is and what year it is"` |
| `r12-030` | everyday expression | `"forgot 1 grocery item off our list once"` |
| `r12-030` | attribution clause | `"and I think he is overtired"` |
| `r12-032` | attribution clause | `"and I think it is low iron"` |
| `r12-033` | everyday expression | `"a lengthwise brown black stripe has widened to 5 mm"` |
| `r12-033` | everyday expression | `"a tiny 1 mm white speck has grown halfway out toward the tip over 5 weeks"` |
| `r12-033` | attribution clause | `"and I think I pinched it"` |
| `r12-034` | everyday expression | `"draining pus has kept coming back over 3 weeks"` |
| `r12-034` | everyday expression | `"I felt mild tenderness for 5 minutes yesterday evening"` |
| `r12-034` | attribution clause | `"and I think food scratched it"` |
| `r12-035` | everyday expression | `"have felt mild outer vaginal dryness for 2 days"` |
| `r12-035` | attribution clause | `"and I think it is late hormones"` |
| `r12-036` | everyday expression | `"felt emotionally numb"` |
| `r12-036` | everyday expression | `"felt mildly teary for 10 minutes 1 afternoon last week"` |
| `r12-036` | attribution clause | `"and I think it is tiredness"` |
| `r12-037` | everyday expression | `"gotten stuck on words"` |
| `r12-037` | everyday expression | `"repeated 1 short word 2 times once yesterday"` |
| `r12-037` | attribution clause | `"and I think he talks fast"` |
| `r12-038` | everyday expression | `"passed dark red pee"` |
| `r12-038` | everyday expression | `"1 time yesterday morning my first pee looked medium yellow"` |
| `r12-038` | attribution clause | `"and I think it is beets"` |
| `r12-039` | everyday expression | `"I have had mild dry skin flaking for 2 days"` |
| `r12-039` | attribution clause | `"and I think glasses rubbed it"` |
| `r12-040` | everyday expression | `"1 day last week my upper eyelids felt mildly heavy for 15 minutes"` |
| `r12-040` | attribution clause | `"and I think it is eye strain"` |
| `r12-041` | everyday expression | `"a smooth firm 1 cm lump on the back of my right wrist"` |
| `r12-041` | everyday expression | `"yesterday I felt mild stiffness on the back of my right wrist for 10 minutes right after carrying trays"` |
| `r12-042` | everyday expression | `"bit the back of my right hand and left 2 deep tooth puncture marks"` |
| `r12-042` | everyday expression | `"mild redness and soreness right around them"` |
| `r12-042` | everyday expression | `"yesterday its claw left a tiny 3 mm shallow surface scratch on the back of my right hand that felt mildly tender for 1 minute"` |
| `r12-043` | everyday expression | `"lost 5 kg without trying"` |
| `r12-043` | everyday expression | `"tonight I have a 104 F fever with violent shaking chills and cannot stand up"` |
| `r12-044` | everyday expression | `"side edge of his right big toenail has dug into painful red"` |
| `r12-044` | everyday expression | `"skin oozing a little clear fluid"` |
| `r12-044` | everyday expression | `"felt mild pressure on the tip of his right big toe for 15 minutes yesterday afternoon"` |
| `r12-045` | everyday expression | `"learned to stay dry all night at age 5"` |
| `r12-045` | everyday expression | `"woke up 1 time last Saturday night and walked to the bathroom to pee"` |
| `r12-046` | everyday expression | `"smelly thick"` |
| `r12-046` | everyday expression | `"mucus coming out of only her right nostril"` |
| `r12-046` | everyday expression | `"has had a little thin watery mucus from both nostrils for 1 day"` |
| `r12-047` | everyday expression | `"hunger ache in my upper middle stomach that eases briefly with crackers or milk"` |
| `r12-047` | everyday expression | `"1 evening last week my upper middle stomach rumbled mildly with hunger right before dinner"` |
| `r12-048` | everyday expression | `"thick yellow"` |
| `r12-048` | everyday expression | `"from my penis staining my underwear"` |
| `r12-048` | everyday expression | `"burning when I pee"` |
| `r12-048` | everyday expression | `"today tight swelling trapped my foreskin behind the head of my penis turning the tip dark purple"` |

---

## 6. Stated Negatives and Bleeding Emergency Controls

- **Stated negatives (`<= 3` per batch):** `0` in `batch_01`, `0` in `batch_02`, `0` overall (no justifications required).
- **Emergency controls moving to Level 4 via bleeding (`<= 1` per batch, Rule D):** `0` in `batch_01`, `0` in `batch_02`, `0` overall.

---

## 7. Level Concerns Recorded (`14` Total)

Following the `SPEC.md` section 8 standard, `@level` recorded `7` non-blocking level concerns in `batch_01/concerns_selfreported.json` and `7` in `batch_02/concerns_selfreported.json` (`14` total; `0` withdrawn; all `pending_clinical_review`):

| Concern ID | Family | Kind | Applies To | Summary |
|---|---|---|---|---|
| `r12-002-c1` | `r12-002` | `control_level_disputed` | `chg` | Eight months of gradually blurry near print in the right eye of a 71-year-old woman is clearly non-emergent, though clinicians may route initial assessment either to a primary-care physician visit (level 2) or directly to an outpatient optometrist or ophthalmologist (level 3). |
| `r12-007-c1` | `r12-007` | `control_level_disputed` | `chg` | A 3-week 1 cm soft rubbery thigh lump at a daily insulin injection site fits non-emergent insulin lipohypertrophy evaluation at a primary-care physician visit (level 2), though patients managed in a diabetes or endocrinology clinic may have injection sites and insulin dosing reviewed directly by their specialist (level 3). |
| `r12-013-c1` | `r12-013` | `level_disputed` | `family` | Two years of floor clutter blocking the hallway and kitchen in a 67-year-old woman warrants structured cognitive behavioral therapy with an outpatient therapist (level 3), though clinicians also commonly begin with a primary-care physician visit to screen for late-life cognitive or medical contributors and coordinate home safety (level 2). |
| `r12-016-c1` | `r12-016` | `level_disputed` | `family` | Six months of nightly loud snoring with witnessed 15-second breathing pauses in a 51-year-old man warrants diagnostic sleep testing via an outpatient sleep specialist (level 3), though without prior workup a primary-care physician visit to assess cardiovascular risk and order home sleep apnea testing first is equally standard (level 2). |
| `r12-018-c1` | `r12-018` | `level_disputed` | `family` | Uncomplicated febrile pharyngitis (102 F for 2 days) developing a rough red chest rash and strawberry tongue in a 7-year-old boy is appropriately managed at a same-day outpatient clinic with rapid streptococcal testing and oral antibiotics (level 2), though some clinicians triage acute febrile pediatric rash with mucosal tongue changes to urgent emergency evaluation if same-day clinic testing is unavailable (level 4). |
| `r12-020-c1` | `r12-020` | `level_disputed` | `family` | A 10-day soft 4 cm posterior elbow fluid pouch in a plumber who leans on his elbows warrants an outpatient clinic examination to confirm aseptic olecranon bursitis and exclude low-grade infection (level 2), though when non-tender and afebrile some clinicians advise trialing elbow padding and pressure offloading at home first (level 1). |
| `r12-023-c1` | `r12-023` | `level_disputed` | `family` | An acute warm tender wedge-shaped erythematous breast patch with a 101 F fever at 3 weeks postpartum is managed as uncomplicated lactational mastitis at a same-day outpatient physician visit (level 2), though febrile postpartum breast infection sits near the urgent triage boundary where clinicians evaluate in the emergency department if same-day assessment is unavailable or systemic sepsis must be excluded (level 4). |
| `r12-028-c1` | `r12-028` | `control_level_disputed` | `chg` | A normal 37 degrees Celsius rectal temperature in a 21-day-old newborn who felt subjectively warm to the touch tonight supports unbundling and home observation (level 1), though some pediatricians advise an outpatient clinic check or nurse triage review whenever a neonate under 28 days is reported as feeling warm (level 2). |
| `r12-032-c1` | `r12-032` | `level_disputed` | `family` | Fatigue after missing 6 days of thrice-weekly hemodialysis warrants immediate hospital serum potassium and electrocardiogram screening with emergent dialysis (level 4), though when cardiopulmonary red flags are absent some nephrology teams arrange an urgent same-day add-on session at the patient's outpatient dialysis center (level 3). |
| `r12-035-c1` | `r12-035` | `level_disputed` | `family` | Three weeks of postmenopausal vaginal blood spotting 6 years after menopause requires transvaginal ultrasound and endometrial assessment via an outpatient gynecologist (level 3), though in primary-care-first systems initial pelvic examination and fast-track ultrasound ordering by a general practitioner is also standard (level 2). |
| `r12-038-c1` | `r12-038` | `level_disputed` | `family` | Recurrent dark red gross hematuria with small blood clots in a 64-year-old former dye-factory worker requires urology specialist cystoscopy and CT urography (level 3), though in gatekeeper systems initial urgent primary-care urinalysis, renal function check, and fast-track urology referral is also standard (level 2). |
| `r12-040-c1` | `r12-040` | `level_disputed` | `family` | Six weeks of fatigable evening bilateral ptosis and diplopia fits outpatient neurology or neuro-ophthalmology specialist evaluation for ocular myasthenia gravis (level 3), though when new binocular diplopia with ptosis has not yet undergone neuroimaging or bulbar screening some clinicians recommend urgent emergency assessment first (level 4). |
| `r12-042-c1` | `r12-042` | `level_disputed` | `family` | Deep cat-tooth puncture wounds on the dorsum of the hand with early mild local redness at 8 hours are managed at a same-day outpatient clinic with wound irrigation and oral amoxicillin-clavulanate (level 2), though given the risk of rapid Pasteurella deep-space hand infection some clinicians route deep cat bites on the hand directly to the emergency department (level 4). |
| `r12-046-c1` | `r12-046` | `level_disputed` | `family` | Six days of unilateral foul-smelling purulent nasal discharge in a 3-year-old toddler warrants prompt outpatient clinic anterior rhinoscopy for suspected nasal foreign body (level 2), though practices without pediatric suction or extraction instruments commonly refer directly to otolaryngology or emergency removal (level 3). |

---

## 8. Verified vs Assumed and Remaining Uncertainties

### Verified
- **Target token tiers:** Verified every target word's `tier` (`4`: `" ER"`, `" hospital"`; `3`: `" specialist"`, `" dentist"`, `" dermatologist"`, `" psychiatrist"`, `" therapist"`; `2`: `" doctor"`, `" clinic"`) directly against `origin/main:data/urgency_tiers.draft.json` (`3b255672` before `batch_01`, `e6618a02` before `batch_02`).
- **No repeats and no holdout leakage (`G1`–`G3`):** Verified `0` errors from `scripts/check_candidate_pairs.py` (`64` pairs in `batch_01`, `64` pairs in `batch_02`; all `G2` warnings are numeric changes in `-cf` controls explained in `self_check.md`) and `status: "intake"`, `software_validation.errors: 0` from `python -m scripts.experiments.cli intake --no-write` against `r9`, `r10`, `r11_b01`..`r11_b06` (and `r12_b01` for `batch_02`), plus `--concerns` check (`0` errors).
- **Writing and Rule D constraints (`G1`, `G5`, `G8`):** Deterministically and independently verified `<= 40` words per prompt, `<= 2`-word `swap_spans` difference, `0` forbidden characters (`,;-`), `0` apostrophe contractions (`"Im"` or `"I am"` and expanded forms throughout, possessives preserved), `0` dialect or folk lexicon forms, `0` banned diagnosis names, and `0` repeated `changed_fact.to` values against all `144` Round 11 controls and earlier Round 12 controls.
- **Citations (`G7`):** Opened and verified every cited PubMed abstract/full-text page (`37` rows) and every cited Wiktionary (`10` rows) and Cambridge Dictionary (`1` row) entry via `search_web`, confirming exact title match, word-for-word `evidence` sentence presence, and Rule B compliance.
- **Outcome-blindness and scope (`SPEC.md` section 1):** Verified `git status` and commits touch only `drafts/antigravity_scenarios_20261107/round12_20261117/` (`SPEC.md` and earlier round folders untouched; `0` measured-result, holdout, or companion-site paths read).

### Assumed and Uncertain
- **Clinical triage levels and Rule A case fit:** Care levels (`right_care` and `right_care_after`), absence of residual red flags, and clinical naturalness of controls rest on model readings (`@level`, `@facts`, `@adversary`), not a clinician's judgement. Fourteen boundary cases (`3` `control_level_disputed`, `11` `level_disputed`) where emergency vs urgent clinic or primary care vs specialist routing could reasonably differ are recorded in `concerns_selfreported.json`.
- **Naturalness of unsourced everyday phrasing:** The `110` rows marked `"source": "none"` (chiefly numeric/measured Rule A control phrases, plain household descriptions, and first-person causal attribution clauses without verbatim qualitative interview matches) rely on model judgement (`@language`) rather than attested patient quotes and await human patient-language review.
- **Batch 02 `same` source-fit share (`43.5%`):** While Round 12 overall reached `60.4%` `same` fit (`76.0%` in `batch_01`) and `batch_02` PubMed rows reached `66.7%` `same` (`10/15`), `batch_02`'s overall `same` share across all `23` cited rows was `43.5%` (`10/23`), below the `>= 50%` per-batch aim because `8` cited rows in `batch_02` used lexical dictionary definitions (`adjacent`).
- **Tokenization alignment:** In accordance with Hard Limit 3, no study model or tokenizer was run; subword alignment classes remain `not_recorded` until offline tokenization records are supplied outside authoring.

---

## 9. Where the Run Stalled or Needed Extra Steps and Specification Improvements

1. **Unsandboxed `curl` vs built-in `search_web` in `@sources`:** During the `r12-001` rehearsal, `@sources` initially attempted an unsandboxed `curl` to NCBI E-utilities, triggering a 60-second host approval timeout in an unattended session. Switching `@sources` and all authors strictly to the built-in `search_web` tool eliminated network-approval stalls for the rest of the run. *Spec change:* State in section 7/9 that source lookups should use the built-in web search tool rather than shell `curl`.
2. **Subagent sandbox inheritance for `.venv/bin/python` (`G2`/`G3`):** Session command approvals granted in the coordinator conversation did not automatically transfer to `@builder`'s separate worker conversation for `.venv/bin/python` (`BypassSandbox: true`). Having `@builder` run deterministic `assemble_batch.py` (`G1`) in sandbox (`BypassSandbox: false`) while the coordinator executed `--run-gates` (`G2`/`G3`) directly avoided worker approval timeouts, though changes to exact command-argument prefixes between `check_candidate_pairs.py` and `assemble_batch.py` still required host approval when first invoked. *Spec change:* Specify one fixed coordinator wrapper script path in section 9 ("Permissions") to warm once before the run so every batch's `G2`/`G3` invocation shares an identical command prefix.
3. **Intermittent HTTP `503` model capacity errors on `gemini-4-carbon-high`:** Even with `2`–`3` staggered workers, peak server load produced transient `503 UNAVAILABLE` errors that interrupted multi-family turns when files were buffered in memory until turn end. Instructing workers to write each `<family_id>.json` / audit file incrementally to disk as soon as it was finished, dispatching `gemini-4-carbon-high` auditors one at a time in `8`–`12` family chunks, and switching the three authors to `gemini-4-carbon-medium` (while keeping all Carbon auditors on `gemini-4-carbon-high` and `@adversary` on `gemini-4-hydrogen-xhigh`) prevented lost work. *Spec change:* Require per-family incremental disk writes in section 9 so any mid-turn `503` resumes from the remaining families without redoing completed ones.
