# Round 12 Fix Round Report (`round12_20261117`)

> **Draft status:** All 48 Round 12 case families (`batch_01` and `batch_02`) are outcome-blind synthetic drafts awaiting an owner's read, a clinician's review, and a patient-language review. None of these families are clinically validated, and every care-level, fact-parity, language, and feasibility verdict below is a model's reading rather than a clinician's or human reviewer's judgment.

- **Draft branch base read before fix round:** `5193f9b2097ce8d00dfaad7c9ad0bd77c264adfe` (`draft/antigravity-scenarios-20261107`)
- **Engine `main` worktree (`../pw-main`) verified for G2 and G3:** `e6618a020`
- **Source of review notes:** `round12_20261117/reviewer_notes.md` lines 1–100 record a review by a Claude review session (a model's reading, not the owner's, containing no measured result). Lines 101–157 record the owner's decisions of `2026-11-19`, specifically card `r12-fixes` (*"Gemini fixes the 6 controls and 2 clauses"*).
- **Fix-round outcome:** **`2` families revised** (`r12-003` in `batch_01` and `r12-027` in `batch_02`, both explanation clauses); **`6` families left byte-for-byte unchanged as pushed** (`r12-011`, `r12-015`, `r12-021`, `r12-024` in `batch_01`; `r12-043`, `r12-048` in `batch_02`) under `reviewer_notes.md` line 154 (*"If no control that meets the rules exists for a case, say so in `fix_report.md` and leave that family unchanged"*); **`0` families dropped**.

---

## 1. Summary Table of the 8 Target Families

| Family ID | Batch | Level (`target_token`) | Target Field(s) | Author | Fix-Round Disposition | Audit Verdicts (`G1`–`G8`) |
|---|---|---:|---|---|---|---|
| `r12-003` | `batch_01` | `4` (`" ER"`) | `attribution`, `texts.everyday_attribution` | `@author-l4` | **Revised** (`0` returns) | `G1`–`G8` all `pass` (re-audited in fix round) |
| `r12-027` | `batch_02` | `4` (`" ER"`) | `attribution`, `texts.everyday_attribution` | `@author-l4` | **Revised** (`1` return on `G5`, passed on `rev1`) | `G1`–`G8` all `pass` (re-audited in fix round) |
| `r12-011` | `batch_01` | `3` (`" specialist"`) | Control (`changed_fact`, `texts.changed_fact`) | `@author-l3` | **Unchanged as pushed (`5193f9b2`)** — no compliant single-property control exists | Pushed `G1`–`G8` `pass` preserved; `G1`–`G3` re-verified; `@author-l3`, `@level`, `@adversary` confirmed no compliant control |
| `r12-015` | `batch_01` | `3` (`" dermatologist"`) | Control (`changed_fact`, `texts.changed_fact`) | `@author-l3` | **Unchanged as pushed (`5193f9b2`)** — no compliant single-property control exists | Pushed `G1`–`G8` `pass` preserved; `G1`–`G3` re-verified; `@author-l3`, `@level`, `@adversary` confirmed no compliant control |
| `r12-021` | `batch_01` | `2` (`" doctor"`) | Control (`changed_fact`, `texts.changed_fact`) | `@author-l2` | **Unchanged as pushed (`5193f9b2`)** — no compliant single-property control exists | Pushed `G1`–`G8` `pass` preserved; `G1`–`G3` re-verified; `@author-l2`, `@level`, `@adversary` confirmed no compliant control |
| `r12-024` | `batch_01` | `2` (`" clinic"`) | Control (`changed_fact`, `texts.changed_fact`) | `@author-l2` | **Unchanged as pushed (`5193f9b2`)** — no compliant single-property control exists | Pushed `G1`–`G8` `pass` preserved; `G1`–`G3` re-verified; `@author-l2`, `@level`, `@adversary` confirmed no compliant control |
| `r12-043` | `batch_02` | `2` (`" doctor"`) | Control (`changed_fact`, `texts.changed_fact`) | `@author-l2` | **Unchanged as pushed (`5193f9b2`)** — no compliant single-property control exists | Pushed `G1`–`G8` `pass` preserved; `G1`–`G3` re-verified; `@author-l2`, `@level`, `@adversary` confirmed no compliant control |
| `r12-048` | `batch_02` | `2` (`" clinic"`) | Control (`changed_fact`, `texts.changed_fact`) | `@author-l2` | **Unchanged as pushed (`5193f9b2`)** — no compliant single-property control exists | Pushed `G1`–`G8` `pass` preserved; `G1`–`G3` re-verified; `@author-l2`, `@level`, `@adversary` confirmed no compliant control |

---

## 2. The 2 Revised Families (Explanation Clauses)

Both changes are logged in `round12_20261117/revisions.json` with `reason: "Owner decision 2026-11-19, card r12-fixes"`. Only `attribution` (`clause` and `explains`; `source` remains `"none"` after PubMed searches under Rule B) and `texts.everyday_attribution` changed; every other field of `r12-003` and `r12-027` is byte-for-byte identical to `5193f9b2`.

### `r12-003` (`batch_01`, Level 4 `" ER"`, `@author-l4`)

- **Why rewritten:** `"and I think it looked like candy"` explained why the child swallowed the battery rather than what the speaker thinks is happening.
- **Old `attribution.clause`:** `"and I think it looked like candy"`
- **New `attribution.clause`:** `"and I think the battery is dead"`
- **Old `texts.everyday_attribution` (`39` words):**
  `"My 3 year old daughter was in the living room 20 minutes ago and swallowed a coin sized lithium button battery from the TV remote and I think it looked like candy so I need to go to the"`
- **New `texts.everyday_attribution` (`39` words):**
  `"My 3 year old daughter was in the living room 20 minutes ago and swallowed a coin sized lithium button battery from the TV remote and I think the battery is dead so I need to go to the"`
- **Rule B check & audit trail:** `@author-l4` and `@sources` searched PubMed (`search_web`) for parent/carer button-battery ingestion studies; survey and clinical papers describe the dead/flat lithium battery hazard clinically (or report survey rejection rates, e.g. Girardi et al. 2024) without quoting a carer stating this wording verbatim, so `attribution.source` remains `"none"` (`title_matches: null`, `evidence_found_verbatim: null` in `batch_01/sources/r12-003.json`). Passed `G4` (`@facts`), `G5` (`@language`), `G6` (`@level`), `G7` (`@sources`), and `G8` (`@adversary`) on the first pass (`0` returns).

### `r12-027` (`batch_02`, Level 4 `" ER"`, `@author-l4`)

- **Why rewritten:** `"and I think it is steam"` contradicted the stated `"splashed hot oil"`.
- **Old `attribution.clause`:** `"and I think it is steam"`
- **First fix-round attempt (`returned_count = 1` on `G5`):** `"and I think it stayed shallow"` — passed `G4`, `G6`, `G7`, and `G8`, and returned once by `@language` (`G5`) because singular `"it"` had no singular injury noun antecedent after `"splashed hot oil all around my right hand and fingers making big tight blisters"` and `"stayed shallow"` read awkwardly.
- **Final `attribution.clause` (`rev1`):** `"and I think they are superficial"`
- **Old `texts.everyday_attribution` (`39` words):**
  `"Im a 31 year old cook and 20 minutes ago in the kitchen splashed hot oil all around my right hand and fingers making big tight blisters and I think it is steam so I need to go to the"`
- **New `texts.everyday_attribution` (`40` words):**
  `"Im a 31 year old cook and 20 minutes ago in the kitchen splashed hot oil all around my right hand and fingers making big tight blisters and I think they are superficial so I need to go to the"`
- **Rule B check, audit trail & reviewer note:** `texts.everyday` is `34` words, leaving at most `6` words (`"and I think"` + `3` words) under the `40`-word ceiling without naming `"burn"` (`SPEC.md` §4). `@author-l4` and `@sources` searched PubMed (`search_web`) for adult burn/scald qualitative studies; `"superficial"` appears in clinical depth classifications rather than verbatim patient quotes, so `attribution.source` remains `"none"` (`title_matches: null`, `evidence_found_verbatim: null` in `batch_02/sources/r12-027.json`). Passed `G4` (`@facts`), `G5` (`@language`), `G6` (`@level`), `G7` (`@sources`), and `G8` (`@adversary`) on `rev1`, and `G2` (`check_candidate_pairs.py`) reported `0` errors and `0` warnings on `r12-027-att`. Note for the human patient-language reviewer: `"superficial"` is higher-register than everyday kitchen speech under the `6`-word clause ceiling.

---

## 3. Why the 6 Controls Remain Unchanged as Pushed (`reviewer_notes.md` line 154)

Under `reviewer_notes.md` lines 114 and 138–146, `texts.everyday` and `reference_facts` are frozen while a new control must simultaneously:
1. Change **exactly one property** (`onset`, `duration`, `frequency`, `severity`, `count`, `extent`, `side`, or `measured value`) of the named symptom, without changing it into a different symptom or condition (**Rule 1**);
2. Aim for `<= 5` differing words (**Rule 2**);
3. Not write a mild, brief version lasting minutes (**Rule 3**);
4. Move `right_care_after` to a **clear** different care level with **no red flag or higher/same-tier finding remaining** from the untouched facts in `texts.everyday` (**Rule 4** and `SPEC.md` §4 / Gate `G6`);
5. Repeat no Round 11 or Round 12 `changed_fact.to` value in any unit or wording, including no `40 C` / `104 F` fever and no limb changing colour or turning cold (**Rule 5**);
6. Use no dialect-lexicon or dictionary-variety-labelled word (**Rule 6**).

Each of the 6 families was independently evaluated by its author (`@author-l3` or `@author-l2`), `@level` (`gemini-4-carbon-high`), and `@adversary` (`gemini-4-hydrogen-xhigh`) across every candidate `right_care_after` in `{1, 2, 3, 4} \ {right_care}`. All three concluded that **none of the 6 admits a G6-clear single-property control** while `texts.everyday` and `reference_facts` remain frozen:

1. **`r12-011` (`batch_01`, Level 3 `" specialist"`):**
   - *Pushed `everyday` (unchanged):* `"Im a 41 year old woman with 7 months of pale growths in both nostrils and loss of smell despite steroid nose spray and I breathe through my mouth so I should see a"`
   - *Pushed `changed_fact` (unchanged):* `"Im a 41 year old woman with 7 months of pale growths in both nostrils and loss of smell despite steroid nose spray and I can barely speak 2 words per breath sitting still so I should see a"`
   - *Blocking conflict:* `texts.everyday` bundles three refractory bilateral polyposis findings (`f2`: `7 months of pale growths in both nostrils and loss of smell`; `f3`: `despite steroid nose spray`; `f4`: `breathe through my mouth`). Changing one property of any one nasal symptom downward or laterally leaves steroid-refractory intranasal growths/anosmia untouched at Level 3 ENT specialist (and unilateral intranasal growth increases neoplasm concern rather than lowering care to Level 1 or 2, **Rule 4**), whereas even complete bilateral nasal blockage in an adult causes mouth breathing rather than a Level 4 airway emergency unless a different symptom/condition (epistaxis, orbital/intracranial extension, or lower-airway dyspnea) is introduced (**Rule 1**).

2. **`r12-015` (`batch_01`, Level 3 `" dermatologist"`):**
   - *Pushed `everyday` (unchanged):* `"Im a 49 year old woman with dark brown skin and for 4 months intensely itchy flat topped dark violet bumps have clustered across both inner wrists so I should see a"`
   - *Pushed `changed_fact` (unchanged):* `"Im a 49 year old woman with dark brown skin and for 2 days mild ashy dryness has appeared across both inner wrists so I should see a"`
   - *Blocking conflict:* Keeping the lesion identity (`flat topped dark violet bumps` across `both inner wrists`, **Rule 1**) retains classic cutaneous lichen planus papule morphology under any single-property change to duration, itch severity, count, side, or extent: flat-topped dark violet wrist papules are never clear Level 1 self-care (**Rule 4**), Level 2 vs Level 3 is not G6-clear on duration/count/severity alone because `texts.everyday` contains no prior primary-care treatment failure (its Level 3 routing rests on the specialist morphology itself), and no single property of flat-topped bumps reaches Level 4 emergency care without changing into a different blistering/sloughing condition (**Rule 1** and Round 11 `r11-111` stock overlap).

3. **`r12-021` (`batch_01`, Level 2 `" doctor"`):**
   - *Pushed `everyday` (unchanged):* `"Im a 66 year old Black man on daily metformin and have had burning pain and pins and needles across the soles of both feet every night for 8 weeks so I should see a"`
   - *Pushed `changed_fact` (unchanged):* `"Im a 66 year old Black man on daily metformin and the sole of my right foot turned ice cold and dusky slate gray today so I should see a"`
   - *Blocking conflict:* Untouched `f1` + `f2` (`66 year old Black man on daily metformin`) combined with `"burning pain and pins and needles"` means any single-property downward change in frequency, duration, extent, or strength (`reviewer_notes.md` line 120) still describes plantar neuropathic dysesthesia/paresthesia in an older adult taking metformin, which warrants outpatient physician neuropathy/vitamin B12 screening (`Level 2`) rather than clear `Level 1` self-care (**Rule 4**, with mild-for-minutes rewrites barred by **Rules 1 & 3**). Moving to `Level 3` specialist is indistinct before initial primary-care workup, and moving to `Level 4` ER via a single sensory property (without introducing acute paralysis or limb coldness/colour change barred by **Rules 1 & 5**) leaves `"every night"` or isolated paresthesias non-emergent or G6-disputed.

4. **`r12-024` (`batch_01`, Level 2 `" clinic"`):**
   - *Pushed `everyday` (unchanged):* `"Im 22 and my roommate shares this rash and I have had tiny wavy lines on my wrists and between my fingers for 3 weeks and itching makes me lie awake at night so I need to go to the"`
   - *Pushed `changed_fact` (unchanged):* `"Im 22 and my roommate shares this rash and I have had tiny wavy lines on my wrists and between my fingers for 3 weeks and hot swelling locked my fingers bent today so I need to go to the"`
   - *Blocking conflict:* `texts.everyday` holds contagious household transmission (`f2`: `my roommate shares this rash`), interdigital/wrist burrows (`f3`: `tiny wavy lines on my wrists and between my fingers for 3 weeks`), and sleep-preventing nocturnal pruritus (`f4`: `itching makes me lie awake at night`) as separate clauses. Changing one property of the itch leaves contagious 3-week burrows shared with a roommate (`f2` + `f3`), which still requires Level 2 clinic prescription scabicidal therapy (**Rule 4**); changing one property of the wavy lines leaves a shared household rash with sleep-preventing nocturnal itch (`f2` + `f4`) at Level 2 (**Rule 4**); and no single property of itch or wavy lines reaches Level 3 or Level 4 without adding secondary bacterial infection or tenosynovitis (**Rule 1**).

5. **`r12-043` (`batch_02`, Level 2 `" doctor"`):**
   - *Pushed `everyday` (unchanged):* `"I am a 44 year old man and over 6 weeks I have lost 5 kg without trying and had drenching night sweats soaking my bedsheets 4 nights a week so I should see a"`
   - *Pushed `changed_fact` (unchanged):* `"I am a 44 year old man and over 6 weeks I have lost 5 kg without trying and tonight I have a 104 F fever with violent shaking chills and cannot stand up so I should see a"`
   - *Blocking conflict:* `texts.everyday` pairs two independent 6-week systemic B-symptoms (`f2`: `lost 5 kg without trying`; `f3`: `drenching night sweats soaking my bedsheets 4 nights a week`). Changing one property of the night sweats leaves unexplained `5 kg` unintentional weight loss over `6 weeks`, which alone requires a Level 2 physician workup (**Rule 4**); changing one property of the weight loss leaves `6 weeks` of bedsheet-soaking night sweats `4 nights a week`, which also requires a Level 2 physician workup (**Rule 4**); and with fever excluded (`reviewer_notes.md` line 121) and syncope/rigors barred by **Rule 1**, escalating one property of weight loss or night sweats over 6 weeks remains urgent outpatient physician evaluation (`Level 2`) rather than a G6-clear `Level 3` subspecialist or `Level 4` emergency resuscitation.

6. **`r12-048` (`batch_02`, Level 2 `" clinic"`):**
   - *Pushed `everyday` (unchanged):* `"Im 23 and had a new sexual partner 5 days ago and for 2 days I have had thick yellow discharge from my penis staining my underwear with burning when I pee so I need to go to the"`
   - *Pushed `changed_fact` (unchanged):* `"Im 23 and had a new sexual partner 5 days ago and today tight swelling trapped my foreskin behind the head of my penis turning the tip dark purple so I need to go to the"`
   - *Blocking conflict:* Untouched `f2` (`had a new sexual partner 5 days ago`) is paired in `f3` with both `thick yellow discharge from my penis staining my underwear` and `burning when I pee`. Changing one property of the discharge leaves penile discharge plus dysuria 5 days after a new sexual partner (`Level 2` STI clinic NAAT testing and antimicrobial treatment, **Rule 4**); changing one property of the burning leaves purulent yellow penile discharge 5 days after a new sexual partner (`Level 2` STI clinic, **Rule 4**); and no single property of discharge or burning urination reaches `Level 3` or `Level 4` without introducing urinary retention, testicular torsion, or paraphimosis (**Rule 1**).

---

## 4. Rebuilt Batch Verification (`G1`–`G3`) and Citation Totals

Both batches were rebuilt from per-family files via `tools/assemble_batch.py` (`batch_01` first, then `batch_02` so `batch_02`'s `G3` intake check hashes the updated `batch_01/families.json`):

- **`batch_01` (`r12-001`..`r12-024`, `24` families):**
  - **G1:** `pass` — deterministic rebuild verified (`families.json` SHA-256 `2925b68ae7733a20a0bee03639be51ad6cff2caf788de41425fc557f5d661d47`, `check_pairs.json` SHA-256 `c5cdd76d99afc02c783029c0fb8b4ad5a3382e5b6a7f951f30cbdb4614f0b586`, `sources.md` SHA-256 `11503dcbfd7b7bbb0a2eec1ed8448da5e57fcdd60f8f9e6a6fad37e3cc98f11e`, `source_fit.json` SHA-256 `efd61c5c179be09a19edef28302300af15d3c2e1776f96ae4c65a8dbd0f2d35d`).
  - **G2 (`check_candidate_pairs.py`):** `pass` — `64` pairs, `0` errors, `28` number warnings across `19` `-cf` pairs (all explained in `batch_01/self_check.md`).
  - **G3 (`scripts.experiments.cli intake`):** `pass` — `"status": "intake"`, `software_validation.errors: 0`, `software_validation.warnings: 28`; `concerns_selfreported.json` accepted with `0` errors (`7` open concerns).
  - **Citations & dictionaries:** `25/75` rows cited (`33.3%`: `22/59` everyday expressions + `3/16` attribution clauses), `50` unsourced rows; `source_fit.json`: `19/25` `same` (`76.0%`), `6` `adjacent`, `0` `different`; dictionary cited: `Wiktionary`.

- **`batch_02` (`r12-025`..`r12-048`, `24` families):**
  - **G1:** `pass` — deterministic rebuild verified (`families.json` SHA-256 `e8e152fb975b9fe3d13db0f368cc46a09cc6ee03a7177ef9d3af9fe4f6884651`, `check_pairs.json` SHA-256 `6e16657860e571c0e3a0c8efb631299a846d27488cca49597f0a479a2754c580`, `sources.md` SHA-256 `a05054f19affc8479e78ee2812ee733b4ecedef6c26b97a6ebdb4b651adf1441`, `source_fit.json` SHA-256 `ec7e3cb8d369e8df4409403a04ae87ba64af5795bee442277435c9634aaddeee`).
  - **G2 (`check_candidate_pairs.py`):** `pass` — `64` pairs, `0` errors, `44` number warnings across `24` `-cf` pairs (`0` warnings on `r12-027-att`; all `-cf` warnings explained in `batch_02/self_check.md`).
  - **G3 (`scripts.experiments.cli intake` with `--prior-batch r12_b01=...`):** `pass` — `"status": "intake"`, `software_validation.errors: 0`, `software_validation.warnings: 44`; `concerns_selfreported.json` accepted with `0` errors (`7` open concerns).
  - **Citations & dictionaries:** `23/83` rows cited (`27.7%`: `22/67` everyday expressions + `1/16` attribution clauses), `60` unsourced rows; `source_fit.json`: `10/23` `same` (`43.5%` overall, below the `50%` aim because `8` dictionary definitions are recorded as `adjacent`; `10/15` = `66.7%` on PubMed rows), `13` `adjacent`, `0` `different`; dictionaries cited: `Wiktionary`, `Cambridge`.

---

## 5. What Was Verified vs. What Was Assumed

### Verified
- **Surgical edit scope:** Verified programmatically against `5193f9b2` that `46` of `48` family draft files are byte-for-byte untouched, and that in `r12-003.json` and `r12-027.json` **only** `attribution` (`clause`, `explains`) and `texts.everyday_attribution` changed.
- **Protected paths untouched:** Verified via `git status` and `git diff` that `SPEC.md`, `reviewer_notes.md`, `final_report.md`, `ground_truth/*`, earlier rounds (`round9_*`, `round10_*`, `round11_*`), and all paths outside `drafts/antigravity_scenarios_20261107/round12_20261117/` are completely untouched, and that zero Hard-Limit-2 paths were opened.
- **Executable gates (`G1`, `G2`, `G3`):** Verified deterministic `G1` rebuilds and re-ran `G2` (`check_candidate_pairs.py`) and `G3` (`python -m scripts.experiments.cli intake` from `../pw-main` at `e6618a020`, with `batch_01` rebuilt before `batch_02`) with `0` errors on both batches.
- **Independent multi-agent audits (`G4`–`G8`):** Both revised families (`r12-003` and `r12-027`) were audited independently by `@facts` (`G4`), `@language` (`G5`), `@level` (`G6`), `@sources` (`G7`), and `@adversary` (`G8`, on `gemini-4-hydrogen-xhigh`). In updated `sources/r12-003.json` and `sources/r12-027.json`, `"source": "none"` rows now record `"title_matches": null` and `"evidence_found_verbatim": null` rather than `true` (`reviewer_notes.md` line 34).

### Assumed / Open for Human Review
- **Model care-level and feasibility judgments:** Both the care-level assignments (`right_care` and `right_care_after`) and the conclusion that `0/6` target controls admit a G6-clear single-property control while `texts.everyday` and `reference_facts` remain frozen reflect model clinical reasoning, not a clinician's review. If the owner decides to relax the single-property constraint or allow coordinated edits to `texts.everyday` / `reference_facts` on those 6 families, compliant controls can be constructed.
- **Patient-language naturalness:** Whether `"and I think the battery is dead"` (`r12-003`) and `"and I think they are superficial"` (`r12-027`, where `"superficial"` is relatively formal under the 6-word length limit) read as natural spoken caregiver/patient wording awaits human patient-language review.
- **Unchanged families outside this fix round:** All items outside the 8 named targets (including the two unverified SciELO full-text rows on `r12-004` noted in `reviewer_notes.md` line 20 and the linked-family split question in card `r12-split-links`) were outside this fix round's remit and remain as pushed at `5193f9b2`.
