# Round 11 Batch 04 Self-Check (`batch_04` / `r11_b04`)

> **Draft status disclaimer:** All families in `families.json` are outcome-blind synthetic test drafts awaiting an owner's read, a clinician's review, and a patient-language review. Care-level and parity audit verdicts record model readings, not clinical validation.

## 1. Batch Outcome Summary

- **Planned slots in `batch_04`:** `24`
- **Passed all 8 gates (`G1`–`G8`):** `24`
- **Returned once and revised during audit:** `3` (`r11-088`, `r11-092`, `r11-096`)
- **Dropped:** `0` (none)

### Passed Families by Group and Care Level

| Group | Care Level (`right_care`) | Passed Count |
|---|---:|---:|
| `plain_register` | `4` | `6` |
| `plain_register` | `3` | `6` |
| `plain_register` | `2` | `6` |
| `dialect` | `4` | `1` |
| `dialect` | `3` | `1` |
| `dialect` | `2` | `2` |
| `self_care` | `1` | `2` |

## 2. Gate Verification (`G1`–`G8`)

- **G1 (`tools/assemble_batch.py` / `tools/validate_family.py`):** `PASS` — 0 structural/writing-rule errors, byte-for-byte deterministic rebuild verified.
- **G2 (`check_candidate_pairs.py` -> `check_report.json`):** `PASS` — `60` candidate pairs checked, `with_errors: 0`, `with_warnings: 12`.
- **G3 (`scripts.experiments.cli intake` -> `intake_summary.json`):** `PASS` — `status: "intake"`, `software_validation.errors: 0`, `software_validation.warnings: 19` (duplicate check verified against Round 9, Round 10, and all prior Round 11 batches).
- **G4 (`@facts` -> `audit/*.facts.json`):** `PASS` on all `24` assembled families (blind fact extraction matches atomic `reference_facts`; `changed_fact` alters only declared `fact_id`).
- **G5 (`@language` -> `audit/*.language.json`):** `PASS` on all `24` assembled families (`0` stated negatives, limit <= 3).
- **G6 (`@level` -> `audit/*.level.json`):** `PASS` on all `24` assembled families (model reading; explicit non-clinician disclaimer present in every file).
- **G7 (`@sources` -> `sources/*.json`):** `PASS` on all `24` assembled families (every cited record opened, title matched, verbatim single-sentence evidence verified).
- **G8 (`@adversary` on `claude-opus-4-6-thinking` -> `audit/*.adversarial.json`):** `PASS` on all `24` assembled families (cross-model check found no divergent register reading or multi-change control).

## 3. Explanation of Every G2 Pair-Checker Warning (`check_report.json`)

- `r11-075-cf` (`changed_fact_control`): `number: the everyday span drops ['580']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"580"` -> `"168"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-075-cf` (`changed_fact_control`): `number: the everyday span adds ['168']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"580"` -> `"168"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-076-cf` (`changed_fact_control`): `number: the everyday span adds ['20', '3']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"the whites of my eyes turned yellow today"` -> `"had 3 of those 20 minute aches this week"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-077-cf` (`changed_fact_control`): `number: the everyday span adds ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"got a deep gash on my right shin with bone sticking out"` -> `"got a shallow 2 cm road scrape on my right shin"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-078-cf` (`changed_fact_control`): `number: the everyday span adds ['3']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"started making a loud harsh squeak on every breath in while resting"` -> `"gave 3 brief dry coughs after lying down"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-084-cf` (`changed_fact_control`): `number: the everyday span drops ['18']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"for 18 months"` -> `"for 2 months"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-084-cf` (`changed_fact_control`): `number: the everyday span adds ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"for 18 months"` -> `"for 2 months"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-085-cf` (`changed_fact_control`): `number: the everyday span drops ['4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have had sharp pain on the outer side of my right elbow for 4 weeks when gripping tools"` -> `"felt slight soreness on the outer side of my right elbow for 10 minutes after gripping tools yesterday"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-085-cf` (`changed_fact_control`): `number: the everyday span adds ['10']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have had sharp pain on the outer side of my right elbow for 4 weeks when gripping tools"` -> `"felt slight soreness on the outer side of my right elbow for 10 minutes after gripping tools yesterday"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-088-cf` (`changed_fact_control`): `number: the everyday span adds ['20']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"seen drops of bright red blood on toilet paper when wiping"` -> `"heavy bright red blood has been pouring from my rectum for 20 minutes"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-089-cf` (`changed_fact_control`): `number: the everyday span adds ['18']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"while keeping daytime meals and water down"` -> `"and I have retched up bile 18 times since midnight"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-091-cf` (`changed_fact_control`): `number: the everyday span drops ['128', '224']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"reads 224 over 128"` -> `"reads 148 over 92"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-091-cf` (`changed_fact_control`): `number: the everyday span adds ['148', '92']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"reads 224 over 128"` -> `"reads 148 over 92"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-092-cf` (`changed_fact_control`): `number: the everyday span drops ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"happens 2 times a month"` -> `"happened 6 times this morning"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-092-cf` (`changed_fact_control`): `number: the everyday span adds ['6']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"happens 2 times a month"` -> `"happened 6 times this morning"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-093-cf` (`changed_fact_control`): `number: the everyday span drops ['4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"every day for 4 weeks"` -> `"1 time last night"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-093-cf` (`changed_fact_control`): `number: the everyday span adds ['1']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"every day for 4 weeks"` -> `"1 time last night"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-094-cf` (`changed_fact_control`): `number: the everyday span drops ['14']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"counted 14 breaths a minute"` -> `"counted 38 breaths a minute"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-094-cf` (`changed_fact_control`): `number: the everyday span adds ['38']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"counted 14 breaths a minute"` -> `"counted 38 breaths a minute"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.

## 4. Source Fit and Unsourced Expressions

- **Cited expressions (`source_fit.json`):** `14` total — `same`: `9` (`64.3%`), `adjacent`: `5`, `different`: `0` (target `>= 50%` `same`: `MET`).
- **Unsourced expressions/attributions (`"source": "none"`):** `55` items across `24` families (full table in `sources.md`).

## 5. Stated Negatives (`<= 3` per batch)

- `0` families in this batch use a stated negative.

## 6. Self-Reported Concerns (`concerns_selfreported.json`)

- **Total non-blocking auditor notes recorded for human reviewers:** `8` (`control_level_disputed`: 4, `level_disputed`: 3, `wording`: 1)
- All concerns remain open (`pending_clinical_review`, `pending_patient_language_review`, or `open`) for human disposition.
