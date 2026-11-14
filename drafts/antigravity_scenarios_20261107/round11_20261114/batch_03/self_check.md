# Round 11 Batch 03 Self-Check (`batch_03` / `r11_b03`)

> **Draft status disclaimer:** All families in `families.json` are outcome-blind synthetic test drafts awaiting an owner's read, a clinician's review, and a patient-language review. Care-level and parity audit verdicts record model readings, not clinical validation.

## 1. Batch Outcome Summary

- **Planned slots in `batch_03`:** `24`
- **Passed all 8 gates (`G1`–`G8`):** `24`
- **Returned once and revised during audit:** `5` (`r11-052`, `r11-055`, `r11-056`, `r11-061`, `r11-065`)
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
- **G2 (`check_candidate_pairs.py` -> `check_report.json`):** `PASS` — `60` candidate pairs checked, `with_errors: 0`, `with_warnings: 10`.
- **G3 (`scripts.experiments.cli intake` -> `intake_summary.json`):** `PASS` — `status: "intake"`, `software_validation.errors: 0`, `software_validation.warnings: 16` (duplicate check verified against Round 9, Round 10, and all prior Round 11 batches).
- **G4 (`@facts` -> `audit/*.facts.json`):** `PASS` on all `24` assembled families (blind fact extraction matches atomic `reference_facts`; `changed_fact` alters only declared `fact_id`).
- **G5 (`@language` -> `audit/*.language.json`):** `PASS` on all `24` assembled families (`0` stated negatives, limit <= 3).
- **G6 (`@level` -> `audit/*.level.json`):** `PASS` on all `24` assembled families (model reading; explicit non-clinician disclaimer present in every file).
- **G7 (`@sources` -> `sources/*.json`):** `PASS` on all `24` assembled families (every cited record opened, title matched, verbatim single-sentence evidence verified).
- **G8 (`@adversary` on `claude-opus-4-6-thinking` -> `audit/*.adversarial.json`):** `PASS` on all `24` assembled families (cross-model check found no divergent register reading or multi-change control).

## 3. Explanation of Every G2 Pair-Checker Warning (`check_report.json`)

- `r11-049-cf` (`changed_fact_control`): `number: the everyday span adds ['5']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"got sudden severe pain in my chest and ribs today"` -> `"had mild nausea after my morning pill for 5 days"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-052-cf` (`changed_fact_control`): `number: the everyday span drops ['39']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"39 C"` -> `"37 C"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-052-cf` (`changed_fact_control`): `number: the everyday span adds ['37']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"39 C"` -> `"37 C"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-058-cf` (`changed_fact_control`): `number: the everyday span drops ['30']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"feel driven to check my baby's breathing 30 times"` -> `"calmly check my baby's breathing once before bed"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-059-cf` (`changed_fact_control`): `number: the everyday span adds ['5']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"my vaginal muscles tighten in painful spasms that block the exam"` -> `"I feel brief mild pressure for 5 seconds during the exam"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-060-cf` (`changed_fact_control`): `number: the everyday span drops ['5']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"pass loose bloody stools 5 times a day"` -> `"passed large maroon blood clots into the toilet 4 times this hour"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-060-cf` (`changed_fact_control`): `number: the everyday span adds ['4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"pass loose bloody stools 5 times a day"` -> `"passed large maroon blood clots into the toilet 4 times this hour"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-062-cf` (`changed_fact_control`): `number: the everyday span drops ['4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"wake 4 times a night to pee"` -> `"have a painful full bladder passing only drops for 14 hours"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-062-cf` (`changed_fact_control`): `number: the everyday span adds ['14']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"wake 4 times a night to pee"` -> `"have a painful full bladder passing only drops for 14 hours"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-065-cf` (`changed_fact_control`): `number: the everyday span drops ['154', '96']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"154 over 96"` -> `"118 over 74"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-065-cf` (`changed_fact_control`): `number: the everyday span adds ['118', '74']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"154 over 96"` -> `"118 over 74"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-068-cf` (`changed_fact_control`): `number: the everyday span drops ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"blacked out for 2 minutes"` -> `"felt briefly lightheaded for 5 seconds"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-068-cf` (`changed_fact_control`): `number: the everyday span adds ['5']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"blacked out for 2 minutes"` -> `"felt briefly lightheaded for 5 seconds"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-069-cf` (`changed_fact_control`): `number: the everyday span drops ['95']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"reads 95 percent"` -> `"reads 79 percent"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-069-cf` (`changed_fact_control`): `number: the everyday span adds ['79']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"reads 95 percent"` -> `"reads 79 percent"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-070-cf` (`changed_fact_control`): `number: the everyday span adds ['10']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"mild nausea after breakfast today"` -> `"vomiting every sip of water for 10 hours"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.

## 4. Source Fit and Unsourced Expressions

- **Cited expressions (`source_fit.json`):** `21` total — `same`: `11` (`52.4%`), `adjacent`: `10`, `different`: `0` (target `>= 50%` `same`: `MET`).
- **Unsourced expressions/attributions (`"source": "none"`):** `59` items across `24` families (full table in `sources.md`).

## 5. Stated Negatives (`<= 3` per batch)

- `0` families in this batch use a stated negative.

## 6. Self-Reported Concerns (`concerns_selfreported.json`)

- **Total non-blocking auditor notes recorded for human reviewers:** `10` (`control_level_disputed`: 5, `level_disputed`: 1, `wording`: 4)
- All concerns remain open (`pending_clinical_review`, `pending_patient_language_review`, or `open`) for human disposition.
