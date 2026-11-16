# Round 11 Batch 05 Self-Check (`batch_05` / `r11_b05`)

> **Draft status disclaimer:** All families in `families.json` are outcome-blind synthetic test drafts awaiting an owner's read, a clinician's review, and a patient-language review. Care-level and parity audit verdicts record model readings, not clinical validation.

## 1. Batch Outcome Summary

- **Planned slots in `batch_05`:** `24`
- **Passed all 8 gates (`G1`–`G8`):** `24`
- **Returned once and revised during audit:** `5` (`r11-111`, `r11-112`, `r11-113`, `r11-116`, `r11-118`)
- **Dropped:** `0` (none)

### Passed Families by Group and Care Level

| Group | Care Level (`right_care`) | Passed Count |
|---|---:|---:|
| `plain_register` | `4` | `6` |
| `plain_register` | `3` | `6` |
| `plain_register` | `2` | `6` |
| `dialect` | `4` | `2` |
| `dialect` | `3` | `1` |
| `dialect` | `2` | `1` |
| `self_care` | `1` | `2` |

## 2. Gate Verification (`G1`–`G8`)

- **G1 (`tools/assemble_batch.py` / `tools/validate_family.py`):** `PASS` — 0 structural/writing-rule errors, byte-for-byte deterministic rebuild verified.
- **G2 (`check_candidate_pairs.py` -> `check_report.json`):** `PASS` — `60` candidate pairs checked, `with_errors: 0`, `with_warnings: 14`.
- **G3 (`scripts.experiments.cli intake` -> `intake_summary.json`):** `PASS` — `status: "intake"`, `software_validation.errors: 0`, `software_validation.warnings: 25` (duplicate check verified against Round 9, Round 10, and all prior Round 11 batches).
- **G4 (`@facts` -> `audit/*.facts.json`):** `PASS` on all `24` assembled families (blind fact extraction matches atomic `reference_facts`; `changed_fact` alters only declared `fact_id`).
- **G5 (`@language` -> `audit/*.language.json`):** `PASS` on all `24` assembled families (`0` stated negatives, limit <= 3).
- **G6 (`@level` -> `audit/*.level.json`):** `PASS` on all `24` assembled families (model reading; explicit non-clinician disclaimer present in every file).
- **G7 (`@sources` -> `sources/*.json`):** `PASS` on all `24` assembled families (every cited record opened, title matched, verbatim single-sentence evidence verified).
- **G8 (`@adversary` on `claude-opus-4-6-thinking` -> `audit/*.adversarial.json`):** `PASS` on all `24` assembled families (cross-model check found no divergent register reading or multi-change control).

## 3. Explanation of Every G2 Pair-Checker Warning (`check_report.json`)

- `r11-097-cf` (`changed_fact_control`): `number: the everyday span drops ['20']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"suddenly her speech became slurred at breakfast 20 minutes ago"` -> `"she has forgotten scheduled appointment dates more often over 9 months"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-097-cf` (`changed_fact_control`): `number: the everyday span adds ['9']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"suddenly her speech became slurred at breakfast 20 minutes ago"` -> `"she has forgotten scheduled appointment dates more often over 9 months"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-099-cf` (`changed_fact_control`): `number: the everyday span drops ['103']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"103 F"` -> `"98 F"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-099-cf` (`changed_fact_control`): `number: the everyday span adds ['98']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"103 F"` -> `"98 F"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-100-cf` (`changed_fact_control`): `number: the everyday span drops ['3', '6']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have thrown up 6 times in 3 hours this morning"` -> `"have gained 12 pounds around my waist over 4 months"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-100-cf` (`changed_fact_control`): `number: the everyday span adds ['12', '4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have thrown up 6 times in 3 hours this morning"` -> `"have gained 12 pounds around my waist over 4 months"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-101-cf` (`changed_fact_control`): `number: the everyday span drops ['18']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have been unable to pee at all for 18 hours"` -> `"noticed my pee stream has been slower than usual"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-105-cf` (`changed_fact_control`): `number: the everyday span drops ['108']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"108"` -> `"192"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-105-cf` (`changed_fact_control`): `number: the everyday span adds ['192']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"108"` -> `"192"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-106-cf` (`changed_fact_control`): `number: the everyday span drops ['4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"gotten stuck in checking routines at the mirror over my nose for 4 hours daily keeping me home from work"` -> `"glanced at my nose in the mirror for 2 minutes each morning before heading to work"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-106-cf` (`changed_fact_control`): `number: the everyday span adds ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"gotten stuck in checking routines at the mirror over my nose for 4 hours daily keeping me home from work"` -> `"glanced at my nose in the mirror for 2 minutes each morning before heading to work"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-107-cf` (`changed_fact_control`): `number: the everyday span drops ['5']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"every night for 5 months"` -> `"on the past 2 nights"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-107-cf` (`changed_fact_control`): `number: the everyday span adds ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"every night for 5 months"` -> `"on the past 2 nights"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-108-cf` (`changed_fact_control`): `number: the everyday span drops ['7']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"7 months ago"` -> `"29 days ago"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-108-cf` (`changed_fact_control`): `number: the everyday span adds ['29']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"7 months ago"` -> `"29 days ago"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-110-cf` (`changed_fact_control`): `number: the everyday span drops ['3']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have had sharp pain along the thumb side of my right wrist for 3 weeks when picking up my baby"` -> `"felt a quick twinge along the thumb side of my right wrist that faded right away when picking up my baby once"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-112-cf` (`changed_fact_control`): `number: the everyday span drops ['6']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"solid meat has been getting stuck behind my breastbone at every dinner for 6 weeks"` -> `"a hurried bite of steamed rice paused behind my breastbone for 3 seconds once last month"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-112-cf` (`changed_fact_control`): `number: the everyday span adds ['3']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"solid meat has been getting stuck behind my breastbone at every dinner for 6 weeks"` -> `"a hurried bite of steamed rice paused behind my breastbone for 3 seconds once last month"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-113-cf` (`changed_fact_control`): `number: the everyday span drops ['3', '4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have woken up 4 times every night for 3 months soaked from hot flushes and night sweats"` -> `"woke up feeling mildly warm from a single hot flush 2 weeks ago"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-113-cf` (`changed_fact_control`): `number: the everyday span adds ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have woken up 4 times every night for 3 months soaked from hot flushes and night sweats"` -> `"woke up feeling mildly warm from a single hot flush 2 weeks ago"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-114-cf` (`changed_fact_control`): `number: the everyday span adds ['15']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have an itchy red patch of oozing blisters on my left wrist where the clasp sat"` -> `"saw a light clasp dent on my left wrist that smoothed out in 15 minutes"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-116-cf` (`changed_fact_control`): `number: the everyday span drops ['105']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"is 105 F"` -> `"is 97 F"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-116-cf` (`changed_fact_control`): `number: the everyday span adds ['97']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"is 105 F"` -> `"is 97 F"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-120-cf` (`changed_fact_control`): `number: the everyday span drops ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"for the past 2 nights"` -> `"every night for 6 weeks"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-120-cf` (`changed_fact_control`): `number: the everyday span adds ['6']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"for the past 2 nights"` -> `"every night for 6 weeks"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.

## 4. Source Fit and Unsourced Expressions

- **Cited expressions (`source_fit.json`):** `18` total — `same`: `11` (`61.1%`), `adjacent`: `7`, `different`: `0` (target `>= 50%` `same`: `MET`).
- **Unsourced expressions/attributions (`"source": "none"`):** `47` items across `24` families (full table in `sources.md`).

## 5. Stated Negatives (`<= 3` per batch)

- `0` families in this batch use a stated negative.

## 6. Self-Reported Concerns (`concerns_selfreported.json`)

- **Total non-blocking auditor notes recorded for human reviewers:** `7` (`control_level_disputed`: 3, `level_disputed`: 4)
- All concerns remain open (`pending_clinical_review`, `pending_patient_language_review`, or `open`) for human disposition.
