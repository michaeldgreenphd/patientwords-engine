# Round 11 Batch 06 Self-Check (`batch_06` / `r11_b06`)

> **Draft status disclaimer:** All families in `families.json` are outcome-blind synthetic test drafts awaiting an owner's read, a clinician's review, and a patient-language review. Care-level and parity audit verdicts record model readings, not clinical validation.

## 1. Batch Outcome Summary

- **Planned slots in `batch_06`:** `24`
- **Passed all 8 gates (`G1`–`G8`):** `24`
- **Returned once and revised during audit:** `8` (`r11-121`, `r11-124`, `r11-125`, `r11-126`, `r11-128`, `r11-129`, `r11-130`, `r11-141`)
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
- **G2 (`check_candidate_pairs.py` -> `check_report.json`):** `PASS` — `60` candidate pairs checked, `with_errors: 0`, `with_warnings: 11`.
- **G3 (`scripts.experiments.cli intake` -> `intake_summary.json`):** `PASS` — `status: "intake"`, `software_validation.errors: 0`, `software_validation.warnings: 19` (duplicate check verified against Round 9, Round 10, and all prior Round 11 batches).
- **G4 (`@facts` -> `audit/*.facts.json`):** `PASS` on all `24` assembled families (blind fact extraction matches atomic `reference_facts`; `changed_fact` alters only declared `fact_id`).
- **G5 (`@language` -> `audit/*.language.json`):** `PASS` on all `24` assembled families (`0` stated negatives, limit <= 3).
- **G6 (`@level` -> `audit/*.level.json`):** `PASS` on all `24` assembled families (model reading; explicit non-clinician disclaimer present in every file).
- **G7 (`@sources` -> `sources/*.json`):** `PASS` on all `24` assembled families (every cited record opened, title matched, verbatim single-sentence evidence verified).
- **G8 (`@adversary` on `claude-opus-4-6-thinking` -> `audit/*.adversarial.json`):** `PASS` on all `24` assembled families (cross-model check found no divergent register reading or multi-change control).

## 3. Explanation of Every G2 Pair-Checker Warning (`check_report.json`)

- `r11-121-cf` (`changed_fact_control`): `number: the everyday span drops ['1']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"got sudden severe pain all across my belly 1 hour ago"` -> `"have passed hard dry stools 2 times over the past 7 days"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-121-cf` (`changed_fact_control`): `number: the everyday span adds ['2', '7']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"got sudden severe pain all across my belly 1 hour ago"` -> `"have passed hard dry stools 2 times over the past 7 days"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-124-cf` (`changed_fact_control`): `number: the everyday span drops ['15']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"got a fast moving steel sliver stuck in my right eye 15 minutes ago"` -> `"felt mild dryness in my right eye at quitting time"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-127-cf` (`changed_fact_control`): `number: the everyday span adds ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"developed firm scarred bumps joining together on the back of my neck"` -> `"got 2 tiny superficial pimples on the back of my neck"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-135-cf` (`changed_fact_control`): `number: the everyday span drops ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"developed painful sores inside his mouth and tiny blisters on his palms and feet over the past 2 days"` -> `"had 1 tiny flat pink dot on his palm this morning that faded by noon"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-135-cf` (`changed_fact_control`): `number: the everyday span adds ['1']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"developed painful sores inside his mouth and tiny blisters on his palms and feet over the past 2 days"` -> `"had 1 tiny flat pink dot on his palm this morning that faded by noon"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-136-cf` (`changed_fact_control`): `number: the everyday span drops ['3', '5', '5']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have had nosebleeds from my right nostril 5 times a week for 3 weeks stopping after 5 minutes of pinching my nose"` -> `"had 1 brief nosebleed from my right nostril that stopped within 1 minute of pinching my nose"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-136-cf` (`changed_fact_control`): `number: the everyday span adds ['1', '1']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have had nosebleeds from my right nostril 5 times a week for 3 weeks stopping after 5 minutes of pinching my nose"` -> `"had 1 brief nosebleed from my right nostril that stopped within 1 minute of pinching my nose"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-137-cf` (`changed_fact_control`): `number: the everyday span drops ['4', '5']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have 4 rough spots on my scalp that have stayed scaly and red for 5 months"` -> `"had mild warmth on my scalp yesterday evening that subsided overnight"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-138-cf` (`changed_fact_control`): `number: the everyday span drops ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have woken from sleep 3 nights a week for 2 months with painful leg cramps in both calves"` -> `"woke from sleep 1 time 3 weeks ago with a 20 second cramp in both calves"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-138-cf` (`changed_fact_control`): `number: the everyday span adds ['1', '20']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f3` (`"have woken from sleep 3 nights a week for 2 months with painful leg cramps in both calves"` -> `"woke from sleep 1 time 3 weeks ago with a 20 second cramp in both calves"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-139-cf` (`changed_fact_control`): `number: the everyday span drops ['15']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"15 minutes ago I had a sudden blackout"` -> `"that cuff read 156 over 94 this morning"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-139-cf` (`changed_fact_control`): `number: the everyday span adds ['156', '94']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"15 minutes ago I had a sudden blackout"` -> `"that cuff read 156 over 94 this morning"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-142-cf` (`changed_fact_control`): `number: the everyday span drops ['14', '4']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"4 times every day for 14 days"` -> `"2 times today"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-142-cf` (`changed_fact_control`): `number: the everyday span adds ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"4 times every day for 14 days"` -> `"2 times today"`, `right_care_after=1`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-143-cf` (`changed_fact_control`): `number: the everyday span drops ['3']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"in a mild 3 cm red streak"` -> `"with large fluid blisters wrapping 15 cm around it"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-143-cf` (`changed_fact_control`): `number: the everyday span adds ['15']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"in a mild 3 cm red streak"` -> `"with large fluid blisters wrapping 15 cm around it"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-144-cf` (`changed_fact_control`): `number: the everyday span drops ['2']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"for the past 2 hours today"` -> `"every workday afternoon for 8 weeks"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.
- `r11-144-cf` (`changed_fact_control`): `number: the everyday span adds ['8']` — Expected single-fact control difference (`SPEC.md` §2 & §5.5): `changed_fact` replaces `f4` (`"for the past 2 hours today"` -> `"every workday afternoon for 8 weeks"`, `right_care_after=2`); unlike `register_swap`, the 2-word length rule applies only to `medical` vs `everyday`.

## 4. Source Fit and Unsourced Expressions

- **Cited expressions (`source_fit.json`):** `27` total — `same`: `16` (`59.3%`), `adjacent`: `11`, `different`: `0` (target `>= 50%` `same`: `MET`).
- **Unsourced expressions/attributions (`"source": "none"`):** `41` items across `24` families (full table in `sources.md`).

## 5. Stated Negatives (`<= 3` per batch)

- `0` families in this batch use a stated negative.

## 6. Self-Reported Concerns (`concerns_selfreported.json`)

- **Total non-blocking auditor notes recorded for human reviewers:** `7` (`control_level_disputed`: 3, `level_disputed`: 4)
- All concerns remain open (`pending_clinical_review`, `pending_patient_language_review`, or `open`) for human disposition.
