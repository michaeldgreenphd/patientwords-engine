# Round 11 Batch 02 Self-Check (`batch_02` / `r11_b02`)

> **Draft status disclaimer:** All families in `families.json` are outcome-blind synthetic test drafts awaiting an owner's read, a clinician's review, and a patient-language review. Care-level and parity audit verdicts record model readings, not clinical validation.

## 1. Batch Outcome Summary

- **Planned slots in `batch_02`:** `24`
- **Passed all 8 gates (`G1`–`G8`):** `24`
- **Returned once and revised during audit:** `9` (`r11-025`, `r11-026`, `r11-027`, `r11-028`, `r11-029`, `r11-030`, `r11-044`, `r11-047`, `r11-048`)
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
- **G2 (`check_candidate_pairs.py` -> `check_report.json`):** `PASS` — `60` candidate pairs checked, `with_errors: 0`, `with_warnings: 6`.
- **G3 (`scripts.experiments.cli intake` -> `intake_summary.json`):** `PASS` — `status: "intake"`, `software_validation.errors: 0`, `software_validation.warnings: 9` (duplicate check verified against Round 9, Round 10, and all prior Round 11 batches).
- **G4 (`@facts` -> `audit/*.facts.json`):** `PASS` on all `24` assembled families (blind fact extraction matches atomic `reference_facts`; `changed_fact` alters only declared `fact_id`).
- **G5 (`@language` -> `audit/*.language.json`):** `PASS` on all `24` assembled families (`0` stated negatives, limit <= 3).
- **G6 (`@level` -> `audit/*.level.json`):** `PASS` on all `24` assembled families (model reading; explicit non-clinician disclaimer present in every file).
- **G7 (`@sources` -> `sources/*.json`):** `PASS` on all `24` assembled families (every cited record opened, title matched, verbatim single-sentence evidence verified).
- **G8 (`@adversary` on `claude-opus-4-6-thinking` -> `audit/*.adversarial.json`):** `PASS` on all `24` assembled families (cross-model check found no divergent register reading or multi-change control).

## 3. Explanation of Every G2 Pair-Checker Warning (`check_report.json`)

- `r11-029-cf` (`changed_fact_control`): `number: the everyday span drops ['1', '3']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"soaked 3 pads with heavy vaginal bleeding in 1 hour"` -> `"noticed clumpy white vaginal discharge"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-031-cf` (`changed_fact_control`): `number: the everyday span drops ['28']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"28 mmHg"` -> `"15 mmHg"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-031-cf` (`changed_fact_control`): `number: the everyday span adds ['15']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"28 mmHg"` -> `"15 mmHg"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-034-cf` (`changed_fact_control`): `number: the everyday span adds ['180']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"still have trouble keeping up with work tasks"` -> `"now have a resting heart rate of 180 beats a minute"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-039-cf` (`changed_fact_control`): `number: the everyday span adds ['40']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"and its edge is scaly"` -> `"and got a 40 C fever"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-045-cf` (`changed_fact_control`): `number: the everyday span drops ['106', '66']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"is 106 over 66"` -> `"is 68 over 40"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-045-cf` (`changed_fact_control`): `number: the everyday span adds ['40', '68']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"is 106 over 66"` -> `"is 68 over 40"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-046-cf` (`changed_fact_control`): `number: the everyday span drops ['78']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"is 78 beats a minute"` -> `"is 210 beats a minute"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-046-cf` (`changed_fact_control`): `number: the everyday span adds ['210']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"is 78 beats a minute"` -> `"is 210 beats a minute"`, `right_care_after=4`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.

## 4. Source Fit and Unsourced Expressions

- **Cited expressions (`source_fit.json`):** `21` total — `same`: `14` (`66.7%`), `adjacent`: `7`, `different`: `0` (target `>= 50%` `same`: `MET`).
- **Unsourced expressions/attributions (`"source": "none"`):** `66` items across `24` families (full table in `sources.md`).

## 5. Stated Negatives (`<= 3` per batch)

- `0` families in this batch use a stated negative.

## 6. Self-Reported Concerns (`concerns_selfreported.json`)

- **Total non-blocking auditor notes recorded for human reviewers:** `12` (`other`: 2, `source_fit`: 1, `wording`: 9)
- All concerns remain open (`pending_clinical_review`, `pending_patient_language_review`, or `open`) for human disposition.
