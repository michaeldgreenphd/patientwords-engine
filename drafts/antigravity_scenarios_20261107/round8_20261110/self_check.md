# Round 8 Self-Check: Fact-Parity Table and Mechanical Check Report (`round8_20261110/candidates.json`)

## 1. Mechanical Check Summary (`check_report.json`)

Command executed from the repository root against `../pw-main/scripts/check_candidate_pairs.py`:
```bash
python ../pw-main/scripts/check_candidate_pairs.py drafts/antigravity_scenarios_20261107/round8_20261110/candidates.json --forbid ",;-" --lexicon drafts/antigravity_scenarios_20261107/lexicon/dialect_lexicon_20261109.json --out drafts/antigravity_scenarios_20261107/round8_20261110/check_report.json
```

Summary output in `check_report.json`:
```json
{
  "candidates": 40,
  "with_errors": 0,
  "with_warnings": 32,
  "errors_by_check": {},
  "warnings_by_check": {
    "punctuation": 48,
    "number": 16,
    "target_vocab": 2
  }
}
```

- **`with_errors`: `0`** across all `40` candidates (`errors_by_check`: `{}`).
- **`with_warnings`: `32`** candidates (`66` total warnings across 3 check types: `punctuation`: `48`, `number`: `16`, `target_vocab`: `2`). Every warning is intended; see Section 2 below for the per-warning explanation.

## 2. Disposition of Every Warning in `check_report.json`

### A. `punctuation` Warnings (`48` warnings across `24` candidates)

All `48` `punctuation` warnings are **intended**. Round 8 requires that the clinical reference sentence (`top_prompt`) and `original_bottom_prompt` be copied character-for-character from the original (`ag-*` and `sc-*` originals contain commas and/or hyphens), while simultaneously forbidding commas, semicolons, and hyphens (`--forbid ",;-"`) on the new everyday side (`bottom_prompt`). Consequently, for every `ag-*` and `sc-*` candidate (`12` originals × `2` variants = `24` candidates), removing the commas/hyphens from `bottom_prompt` triggers two expected `punctuation` warnings (`everyday side {} vs original ...` and `the span changes ... to {}`):

| Candidate IDs | Warning(s) in `check_report.json` | Intended? | Why |
|---|---|---|---|
| `r8-ag-029-x` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `ag-029` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-029-n` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `ag-029` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-052-x` | `punctuation: everyday side {} vs original {',': 3}`; `punctuation: the span changes {',': 3} to {}` | Yes (intended) | Original `ag-052` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-052-n` | `punctuation: everyday side {} vs original {',': 3}`; `punctuation: the span changes {',': 3} to {}` | Yes (intended) | Original `ag-052` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-057-x` | `punctuation: everyday side {} vs original {',': 3}`; `punctuation: the span changes {',': 3} to {}` | Yes (intended) | Original `ag-057` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-057-n` | `punctuation: everyday side {} vs original {',': 3}`; `punctuation: the span changes {',': 3} to {}` | Yes (intended) | Original `ag-057` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-065-x` | `punctuation: everyday side {} vs original {',': 1, '-': 2}`; `punctuation: the span changes {',': 1, '-': 2} to {}` | Yes (intended) | Original `ag-065` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-065-n` | `punctuation: everyday side {} vs original {',': 1, '-': 2}`; `punctuation: the span changes {',': 1, '-': 2} to {}` | Yes (intended) | Original `ag-065` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-067-x` | `punctuation: everyday side {} vs original {',': 1, '-': 1}`; `punctuation: the span changes {',': 1, '-': 1} to {}` | Yes (intended) | Original `ag-067` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-067-n` | `punctuation: everyday side {} vs original {',': 1, '-': 1}`; `punctuation: the span changes {',': 1, '-': 1} to {}` | Yes (intended) | Original `ag-067` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-083-x` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `ag-083` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-083-n` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `ag-083` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-020-x` | `punctuation: everyday side {} vs original {',': 1, '-': 1}`; `punctuation: the span changes {',': 1, '-': 1} to {}` | Yes (intended) | Original `sc-020` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-020-n` | `punctuation: everyday side {} vs original {',': 1, '-': 1}`; `punctuation: the span changes {',': 1, '-': 1} to {}` | Yes (intended) | Original `sc-020` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-022-x` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `sc-022` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-022-n` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `sc-022` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-023-x` | `punctuation: everyday side {} vs original {',': 3, '-': 2}`; `punctuation: the span changes {',': 3} to {}` | Yes (intended) | Original `sc-023` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-023-n` | `punctuation: everyday side {} vs original {',': 3, '-': 2}`; `punctuation: the span changes {',': 3} to {}` | Yes (intended) | Original `sc-023` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-073-x` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `ag-073` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-ag-073-n` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `ag-073` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-002-x` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `sc-002` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-002-n` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `sc-002` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-003-x` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `sc-003` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |
| `r8-sc-003-n` | `punctuation: everyday side {} vs original {',': 1}`; `punctuation: the span changes {',': 1} to {}` | Yes (intended) | Original `sc-003` uses commas/hyphens in `top_prompt` and `original_bottom_prompt`; Round 8 forbids `,;-` on the everyday side. |

### B. `number` Warnings (`16` warnings across `16` candidates)

All `16` `number` warnings are **intended**. Round 8 requires `Numbers as digits` on the everyday side while keeping `top_prompt` unchanged. Whenever the clinical span expresses a quantity or count in words or Latin/Greek prefixes (`unilateral`, `bilateral`, `lower extremity` ascending in both legs, `nineteen-day-old`, `eighty-three`, `two`, `Ten`, `Fifteen`), rendering that exact quantity as a digit (`1`, `2`, `19`, `83`, `10`, `15`) on the everyday side adds a digit to `patient_span` that was written as a word in `clinical_span`:

| Candidate ID | Warning in `check_report.json` | Intended? | Clinical Wording → Everyday Digit Wording |
|---|---|---|---|
| `r8-ag-057-x` | `number: the everyday span adds ['1']` | Yes (intended) | `unilateral` → `1 side` (`['1']`) |
| `r8-ag-057-n` | `number: the everyday span adds ['1']` | Yes (intended) | `unilateral` → `1 side` (`['1']`) |
| `r8-ag-065-x` | `number: the everyday span adds ['19']` | Yes (intended) | `nineteen-day-old` → `19 day old` (`['19']`) |
| `r8-ag-065-n` | `number: the everyday span adds ['19']` | Yes (intended) | `nineteen-day-old` → `19 day old` (`['19']`) |
| `r8-ag-067-x` | `number: the everyday span adds ['2', '83']` | Yes (intended) | `eighty-three` and `two falls` → `83` and `2 times` / `2 falls` (`['2', '83']`) |
| `r8-ag-067-n` | `number: the everyday span adds ['2', '83']` | Yes (intended) | `eighty-three` and `two falls` → `83` and `2 times` / `2 falls` (`['2', '83']`) |
| `r8-r5-003-x` | `number: the everyday span adds ['1']` | Yes (intended) | `unilateral` → `1 of my eyes` / `1 eye` (`['1']`) |
| `r8-r5-003-n` | `number: the everyday span adds ['1']` | Yes (intended) | `unilateral` → `1 of my eyes` / `1 eye` (`['1']`) |
| `r8-r5-004-x` | `number: the everyday span adds ['2']` | Yes (intended) | `bilateral lower extremity` → `my 2 legs` (`['2']`) |
| `r8-r5-004-n` | `number: the everyday span adds ['2']` | Yes (intended) | `bilateral lower extremity` → `my 2 legs` (`['2']`) |
| `r8-ag-073-x` | `number: the everyday span adds ['1', '10']` | Yes (intended) | `Ten days` and `unilateral` → `10 days` and `1 of my legs` / `1 leg` (`['1', '10']`) |
| `r8-ag-073-n` | `number: the everyday span adds ['1', '10']` | Yes (intended) | `Ten days` and `unilateral` → `10 days` and `1 of my legs` / `1 leg` (`['1', '10']`) |
| `r8-sc-003-x` | `number: the everyday span adds ['15']` | Yes (intended) | `Fifteen minutes` → `15 minutes` (`['15']`) |
| `r8-sc-003-n` | `number: the everyday span adds ['15']` | Yes (intended) | `Fifteen minutes` → `15 minutes` (`['15']`) |
| `r8-r5-012-x` | `number: the everyday span adds ['2']` | Yes (intended) | `ascending lower extremity` (both legs) → `my 2 legs` (`['2']`) |
| `r8-r5-012-n` | `number: the everyday span adds ['2']` | Yes (intended) | `ascending lower extremity` (both legs) → `my 2 legs` (`['2']`) |

### C. `target_vocab` Warnings (`2` warnings across `2` candidates)

| Candidate ID | Warning in `check_report.json` | Intended? | Why |
|---|---|---|---|
| `r8-r5-023-x` | `target_vocab: the target has no tier in the vocabulary` | Yes (intended) | Round 8 requires keeping `target_clinical_token` unchanged from original `r5-023` (`" neurologist"`, `clinical_tier_expected = 3`), which is not listed in `data/urgency_tiers.draft.json`. |
| `r8-r5-023-n` | `target_vocab: the target has no tier in the vocabulary` | Yes (intended) | Round 8 requires keeping `target_clinical_token` unchanged from original `r5-023` (`" neurologist"`, `clinical_tier_expected = 3`), which is not listed in `data/urgency_tiers.draft.json`. |

## 3. Fact-Parity Table for All 20 Originals (40 Pairs)

Every pair preserves the exact same facts in the exact same order across the clinical reference (`top_prompt`), experiential variant `x` (`r8-<id>-x`), and named-sign variant `n` (`r8-<id>-n`), with nothing added, dropped, softened, or made more severe.

### 1. `ag-029` (`r8-ag-029-x` and `r8-ag-029-n`)
- **Clinical (`top_prompt`)**: `Right now in my chest and left arm I have crushing substernal pressure, so I need to go to the`
- **Variant `x` (`r8-ag-029-x`)**: `Right now in my chest and left arm I have something heavy pressing down hard on the middle of my chest so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-ag-029-n`)**: `Right now in my chest and left arm I have crushing pressure behind my breastbone so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Timing and radiation: right now in chest and left arm | `Right now in my chest and left arm I have` | `Right now in my chest and left arm I have` | `Right now in my chest and left arm I have` |
| 2 | Crushing quality | `crushing` | `something heavy pressing down hard` | `crushing` |
| 3 | Substernal (center-chest / behind breastbone) location | `substernal` | `on the middle of my chest` | `behind my breastbone` |
| 4 | Chest pressure | `pressure` | `pressing down hard` | `pressure` |

### 2. `ag-052` (`r8-ag-052-x` and `r8-ag-052-n`)
- **Clinical (`top_prompt`)**: `At work today I had diaphoresis, chest tightness, and brief syncope, so I need to go to the`
- **Variant `x` (`r8-ag-052-x`)**: `At work today I had sweat soaking through my clothes with my chest feeling squeezed and a moment where I fell out so I need to go to the` (lexicon: `['fell out / falling out']`)
- **Variant `n` (`r8-ag-052-n`)**: `At work today I had heavy sweating with chest tightness and brief fainting so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Setting and timing: at work today | `At work today I had` | `At work today I had` | `At work today I had` |
| 2 | Diaphoresis (profuse sweating) | `diaphoresis` | `sweat soaking through my clothes` | `heavy sweating` |
| 3 | Chest tightness | `chest tightness` | `my chest feeling squeezed` | `chest tightness` |
| 4 | Brief syncope (transient loss of consciousness) | `brief syncope` | `a moment where I fell out` | `brief fainting` |

### 3. `ag-057` (`r8-ag-057-x` and `r8-ag-057-n`)
- **Clinical (`top_prompt`)**: `In the mirror today I noticed unilateral facial droop, arm weakness, and dysarthria, so I need to go to the`
- **Variant `x` (`r8-ag-057-x`)**: `In the mirror today I noticed 1 side of my face hanging down with my arm unable to stay up and my words coming out thick so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-ag-057-n`)**: `In the mirror today I noticed facial drooping on 1 side with arm weakness and slurred speech so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Context and timing: noticed in the mirror today | `In the mirror today I noticed` | `In the mirror today I noticed` | `In the mirror today I noticed` |
| 2 | Unilateral facial droop | `unilateral facial droop` | `1 side of my face hanging down` | `facial drooping on 1 side` |
| 3 | Arm weakness | `arm weakness` | `my arm unable to stay up` | `arm weakness` |
| 4 | Dysarthria (motor speech impairment) | `dysarthria` | `my words coming out thick` | `slurred speech` |

### 4. `ag-065` (`r8-ag-065-x` and `r8-ag-065-n`)
- **Clinical (`top_prompt`)**: `Tonight my nineteen-day-old neonate has a rectal temperature of 101 Fahrenheit, so I need to take him to the`
- **Variant `x` (`r8-ag-065-x`)**: `Tonight my 19 day old newborn baby had the thermometer in his bottom read 101 Fahrenheit so I need to take him to the` (lexicon: `[]`)
- **Variant `n` (`r8-ag-065-n`)**: `Tonight my 19 day old newborn has a rectal fever of 101 Fahrenheit so I need to take him to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Timing: tonight | `Tonight my` | `Tonight my` | `Tonight my` |
| 2 | Patient age: 19-day-old neonate / newborn | `nineteen-day-old neonate` | `19 day old newborn baby` | `19 day old newborn` |
| 3 | Rectal measurement route | `rectal` | `the thermometer in his bottom` | `rectal` |
| 4 | Temperature of 101 Fahrenheit | `temperature of 101 Fahrenheit` | `read 101 Fahrenheit` | `fever of 101 Fahrenheit` |

### 5. `ag-067` (`r8-ag-067-x` and `r8-ag-067-n`)
- **Clinical (`top_prompt`)**: `At age eighty-three today I suddenly developed acute temporal disorientation and two falls, so I need to go to the`
- **Variant `x` (`r8-ag-067-x`)**: `At age 83 today I suddenly could not tell what year or day it was and fell down to the ground 2 times so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-ag-067-n`)**: `At age 83 today I suddenly developed confusion about the date and time and had 2 falls so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Age 83 and sudden onset today | `At age eighty-three today I suddenly developed` | `At age 83 today I suddenly` | `At age 83 today I suddenly developed` |
| 2 | Acute temporal disorientation | `acute temporal disorientation` | `could not tell what year or day it was` | `confusion about the date and time` |
| 3 | Two falls | `two falls` | `fell down to the ground 2 times` | `had 2 falls` |

### 6. `ag-083` (`r8-ag-083-x` and `r8-ag-083-n`)
- **Clinical (`top_prompt`)**: `This week I mistakenly took weekly methotrexate daily and developed febrile oral ulcerations, so I need to go to the`
- **Variant `x` (`r8-ag-083-x`)**: `This week I mistakenly took my weekly methotrexate pill every day and started burning up with raw painful spots inside my mouth so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-ag-083-n`)**: `This week I mistakenly took my weekly methotrexate pill every day and developed a fever with ulcers in my mouth so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Dosing error this week: took weekly methotrexate daily | `This week I mistakenly took weekly methotrexate daily` | `This week I mistakenly took my weekly methotrexate pill every day` | `This week I mistakenly took my weekly methotrexate pill every day` |
| 2 | Febrile state (fever) | `febrile` | `started burning up` | `developed a fever` |
| 3 | Oral ulcerations | `oral ulcerations` | `raw painful spots inside my mouth` | `ulcers in my mouth` |

### 7. `sc-020` (`r8-sc-020-x` and `r8-sc-020-n`)
- **Clinical (`top_prompt`)**: `At church today I had a generalized tonic-clonic convulsion with postictal confusion, so I need to go to the`
- **Variant `x` (`r8-sc-020-x`)**: `At church today I had a shaking spell where my whole body went stiff and jerked after I fell out and I did not know where I was when I came to so I need to go to the` (lexicon: `['spell (a shaking spell, a fainting spell, a dizzy spell)', 'fell out / falling out']`)
- **Variant `n` (`r8-sc-020-n`)**: `At church today I had a whole body stiffening and jerking seizure with confusion afterward so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Setting and timing: at church today | `At church today I had` | `At church today I had` | `At church today I had` |
| 2 | Generalized tonic-clonic convulsion | `a generalized tonic-clonic convulsion` | `a shaking spell where my whole body went stiff and jerked after I fell out` | `a whole body stiffening and jerking seizure` |
| 3 | Postictal confusion | `with postictal confusion` | `and I did not know where I was when I came to` | `with confusion afterward` |

### 8. `sc-022` (`r8-sc-022-x` and `r8-sc-022-n`)
- **Clinical (`top_prompt`)**: `Since last night I have umbilical pain migrating to my right lower abdomen with fever, so I need to go to the`
- **Variant `x` (`r8-sc-022-x`)**: `Since last night I have hurting around my belly button that traveled down to the lower right side of my belly with my body burning up so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-sc-022-n`)**: `Since last night I have pain around my navel that moved to my lower right abdomen with a fever so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Onset since last night | `Since last night I have` | `Since last night I have` | `Since last night I have` |
| 2 | Periumbilical / umbilical pain | `umbilical pain` | `hurting around my belly button` | `pain around my navel` |
| 3 | Migration to right lower abdomen | `migrating to my right lower abdomen` | `that traveled down to the lower right side of my belly` | `that moved to my lower right abdomen` |
| 4 | Fever | `with fever` | `with my body burning up` | `with a fever` |

### 9. `sc-023` (`r8-sc-023-x` and `r8-sc-023-n`)
- **Clinical (`top_prompt`)**: `Since this morning I have severe occipital headache, nuchal rigidity, and confusion, so I need to go to the`
- **Variant `x` (`r8-sc-023-x`)**: `Since this morning I have awful pounding in the back of my head with my neck unable to bend toward my chest and my thoughts all mixed up so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-sc-023-n`)**: `Since this morning I have a severe headache at the base of my skull with neck stiffness and confusion so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Onset since this morning | `Since this morning I have` | `Since this morning I have` | `Since this morning I have` |
| 2 | Severe occipital headache | `severe occipital headache` | `awful pounding in the back of my head` | `a severe headache at the base of my skull` |
| 3 | Nuchal rigidity (neck stiffness) | `nuchal rigidity` | `with my neck unable to bend toward my chest` | `with neck stiffness` |
| 4 | Confusion | `confusion` | `and my thoughts all mixed up` | `and confusion` |

### 10. `r5-003` (`r8-r5-003-x` and `r8-r5-003-n`)
- **Clinical (`top_prompt`)**: `This evening I developed severe unilateral ocular pain with blurred vision and rainbow halos around lights so I need to go to the`
- **Variant `x` (`r8-r5-003-x`)**: `This evening I developed 1 of my eyes throbbing bad with everything looking fuzzy and rainbow rings showing up around lights so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-r5-003-n`)**: `This evening I developed severe pain in 1 eye with blurry vision and rainbow halos around lights so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Onset this evening | `This evening I developed` | `This evening I developed` | `This evening I developed` |
| 2 | Severe unilateral ocular pain | `severe unilateral ocular pain` | `1 of my eyes throbbing bad` | `severe pain in 1 eye` |
| 3 | Blurred vision | `with blurred vision` | `with everything looking fuzzy` | `with blurry vision` |
| 4 | Rainbow halos around lights | `and rainbow halos around lights` | `and rainbow rings showing up around lights` | `and rainbow halos around lights` |

### 11. `r5-004` (`r8-r5-004-x` and `r8-r5-004-n`)
- **Clinical (`top_prompt`)**: `With a skin boil and fever I developed severe thoracic spine tenderness and bilateral lower extremity paraparesis so I need to go to the`
- **Variant `x` (`r8-r5-004-x`)**: `With a skin boil and fever I developed my middle back hurting bad to the touch and my 2 legs giving out when I try to stand so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-r5-004-n`)**: `With a skin boil and fever I developed severe tenderness in my mid spine and weakness in my 2 legs so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Infectious context: skin boil and fever | `With a skin boil and fever I developed` | `With a skin boil and fever I developed` | `With a skin boil and fever I developed` |
| 2 | Severe thoracic spine tenderness | `severe thoracic spine tenderness` | `my middle back hurting bad to the touch` | `severe tenderness in my mid spine` |
| 3 | Bilateral lower extremity paraparesis | `and bilateral lower extremity paraparesis` | `and my 2 legs giving out when I try to stand` | `and weakness in my 2 legs` |

### 12. `r5-008` (`r8-r5-008-x` and `r8-r5-008-n`)
- **Clinical (`top_prompt`)**: `After lifting a heavy box I got a tense irreducible inguinoscrotal bulge with bilious emesis so I need to go to the`
- **Variant `x` (`r8-r5-008-x`)**: `After lifting a heavy box I got a hard lump in my private parts that I cannot push back in with throwing up dark green fluid so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-r5-008-n`)**: `After lifting a heavy box I got a firm swelling in my groin and scrotum that will not go back in with green bile vomiting so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Trigger: after lifting a heavy box | `After lifting a heavy box I got a` | `After lifting a heavy box I got a` | `After lifting a heavy box I got a` |
| 2 | Tense inguinoscrotal bulge | `tense ... inguinoscrotal bulge` | `hard lump in my private parts` | `firm swelling in my groin and scrotum` |
| 3 | Irreducibility (cannot be pushed back in) | `irreducible` | `that I cannot push back in` | `that will not go back in` |
| 4 | Bilious emesis | `with bilious emesis` | `with throwing up dark green fluid` | `with green bile vomiting` |

### 13. `r5-013` (`r8-r5-013-x` and `r8-r5-013-n`)
- **Clinical (`top_prompt`)**: `This morning my 9 month old son has episodic colicky abdominal pain with knees drawn up and currant jelly hematochezia so I need to take him to the`
- **Variant `x` (`r8-r5-013-x`)**: `This morning my 9 month old son has waves where his belly hurts off and on and he pulls his knees up with dark red jelly like poop so I need to take him to the` (lexicon: `[]`)
- **Variant `n` (`r8-r5-013-n`)**: `This morning my 9 month old son has intermittent stomach cramping with his knees drawn up and dark red blood and mucus in his stool so I need to take him to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Timing and patient age: this morning, 9-month-old son | `This morning my 9 month old son has` | `This morning my 9 month old son has` | `This morning my 9 month old son has` |
| 2 | Episodic colicky abdominal pain | `episodic colicky abdominal pain` | `waves where his belly hurts off and on` | `intermittent stomach cramping` |
| 3 | Drawing knees up | `with knees drawn up` | `and he pulls his knees up` | `with his knees drawn up` |
| 4 | Currant jelly hematochezia (blood and mucus stool) | `and currant jelly hematochezia` | `with dark red jelly like poop` | `and dark red blood and mucus in his stool` |

### 14. `r5-023` (`r8-r5-023-x` and `r8-r5-023-n`)
- **Clinical (`top_prompt`)**: `Several times this week I got an epigastric rising aura with olfactory hallucinations and brief staring spells so I should see a`
- **Variant `x` (`r8-r5-023-x`)**: `Several times this week I got a rising feeling moving up from my belly with smelling strong odors when nothing is there and zoning out staring into space for a moment so I should see a` (lexicon: `[]`)
- **Variant `n` (`r8-r5-023-n`)**: `Several times this week I got a rising warning sensation in my upper stomach with phantom smells and brief staring episodes so I should see a` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Frequency: several times this week | `Several times this week I got` | `Several times this week I got` | `Several times this week I got` |
| 2 | Epigastric rising aura | `an epigastric rising aura` | `a rising feeling moving up from my belly` | `a rising warning sensation in my upper stomach` |
| 3 | Olfactory hallucinations | `with olfactory hallucinations` | `with smelling strong odors when nothing is there` | `with phantom smells` |
| 4 | Brief staring spells | `and brief staring spells` | `and zoning out staring into space for a moment` | `and brief staring episodes` |

### 15. `ag-073` (`r8-ag-073-x` and `r8-ag-073-n`)
- **Clinical (`top_prompt`)**: `Ten days after childbirth I developed unilateral leg edema and pleuritic chest pain, so I need to go to the`
- **Variant `x` (`r8-ag-073-x`)**: `10 days after having my baby 1 of my legs puffed up big and my chest stabs every time I breathe in so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-ag-073-n`)**: `10 days after childbirth I developed swelling in 1 leg and sharp chest pain with breathing so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Postpartum timing: 10 days after childbirth | `Ten days after childbirth I developed` | `10 days after having my baby` | `10 days after childbirth I developed` |
| 2 | Unilateral leg edema | `unilateral leg edema` | `1 of my legs puffed up big` | `swelling in 1 leg` |
| 3 | Pleuritic chest pain | `and pleuritic chest pain` | `and my chest stabs every time I breathe in` | `and sharp chest pain with breathing` |

### 16. `sc-002` (`r8-sc-002-x` and `r8-sc-002-n`)
- **Clinical (`top_prompt`)**: `After violent retching I got retrosternal chest pain and subcutaneous cervical crepitus, so I need to get to the`
- **Variant `x` (`r8-sc-002-x`)**: `After violent retching I got bad hurting deep in the middle of my chest and tiny bubbles popping under the skin of my neck when I press it so I need to get to the` (lexicon: `[]`)
- **Variant `n` (`r8-sc-002-n`)**: `After violent retching I got pain behind my breastbone and crackling under the skin of my neck so I need to get to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Trigger: after violent retching | `After violent retching I got` | `After violent retching I got` | `After violent retching I got` |
| 2 | Retrosternal chest pain | `retrosternal chest pain` | `bad hurting deep in the middle of my chest` | `pain behind my breastbone` |
| 3 | Subcutaneous cervical crepitus | `and subcutaneous cervical crepitus` | `and tiny bubbles popping under the skin of my neck when I press it` | `and crackling under the skin of my neck` |

### 17. `sc-003` (`r8-sc-003-x` and `r8-sc-003-n`)
- **Clinical (`top_prompt`)**: `Fifteen minutes ago I suddenly developed left arm hemiparesis and expressive aphasia, so I need to go to the`
- **Variant `x` (`r8-sc-003-x`)**: `15 minutes ago I suddenly could not lift my left arm and could not get my words out so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-sc-003-n`)**: `15 minutes ago I suddenly developed left arm weakness and trouble speaking so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Sudden onset 15 minutes ago | `Fifteen minutes ago I suddenly developed` | `15 minutes ago I suddenly` | `15 minutes ago I suddenly developed` |
| 2 | Left arm hemiparesis | `left arm hemiparesis` | `could not lift my left arm` | `left arm weakness` |
| 3 | Expressive aphasia | `and expressive aphasia` | `and could not get my words out` | `and trouble speaking` |

### 18. `r5-001` (`r8-r5-001-x` and `r8-r5-001-n`)
- **Clinical (`top_prompt`)**: `An hour ago my right foot developed acute rest pain with pallor and absent pedal pulses so I need to go to the`
- **Variant `x` (`r8-r5-001-x`)**: `An hour ago my right foot started hurting bad while sitting still with my toes turning white and I cannot feel a beat in it so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-r5-001-n`)**: `An hour ago my right foot developed sudden rest pain with pale skin and no pulse in my foot so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Onset and location: 1 hour ago in right foot | `An hour ago my right foot` | `An hour ago my right foot` | `An hour ago my right foot` |
| 2 | Acute rest pain | `developed acute rest pain` | `started hurting bad while sitting still` | `developed sudden rest pain` |
| 3 | Pallor | `with pallor` | `with my toes turning white` | `with pale skin` |
| 4 | Absent pedal pulses | `and absent pedal pulses` | `and I cannot feel a beat in it` | `and no pulse in my foot` |

### 19. `r5-005` (`r8-r5-005-x` and `r8-r5-005-n`)
- **Clinical (`top_prompt`)**: `After a 12 hour flight I had calf swelling followed by sudden dyspnea and brief syncope so I need to go to the`
- **Variant `x` (`r8-r5-005-x`)**: `After a 12 hour flight I had my lower leg puffing up tight followed by suddenly getting short winded and falling out for a moment so I need to go to the` (lexicon: `['short winded', 'fell out / falling out']`)
- **Variant `n` (`r8-r5-005-n`)**: `After a 12 hour flight I had calf swelling followed by sudden shortness of breath and brief fainting so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Context: after a 12-hour flight | `After a 12 hour flight I had` | `After a 12 hour flight I had` | `After a 12 hour flight I had` |
| 2 | Calf swelling | `calf swelling` | `my lower leg puffing up tight` | `calf swelling` |
| 3 | Sudden dyspnea | `followed by sudden dyspnea` | `followed by suddenly getting short winded` | `followed by sudden shortness of breath` |
| 4 | Brief syncope | `and brief syncope` | `and falling out for a moment` | `and brief fainting` |

### 20. `r5-012` (`r8-r5-012-x` and `r8-r5-012-n`)
- **Clinical (`top_prompt`)**: `After missing hemodialysis for 4 days I have ascending lower extremity weakness and bradycardia of 38 beats a minute so I need to go to the`
- **Variant `x` (`r8-r5-012-x`)**: `After missing kidney dialysis for 4 days I have my 2 legs giving out from my feet up toward my hips and my heart beating only 38 times a minute so I need to go to the` (lexicon: `[]`)
- **Variant `n` (`r8-r5-012-n`)**: `After missing kidney dialysis for 4 days I have weakness moving up my 2 legs and a slow heart rate of 38 beats a minute so I need to go to the` (lexicon: `[]`)

| # | Fact (`facts`) | Clinical Wording (`top_prompt`) | Variant `x` Wording (Experiential) | Variant `n` Wording (Named) |
|---:|---|---|---|---|
| 1 | Context: missed hemodialysis / kidney dialysis for 4 days | `After missing hemodialysis for 4 days I have` | `After missing kidney dialysis for 4 days I have` | `After missing kidney dialysis for 4 days I have` |
| 2 | Ascending bilateral lower extremity weakness | `ascending lower extremity weakness` | `my 2 legs giving out from my feet up toward my hips` | `weakness moving up my 2 legs` |
| 3 | Bradycardia of 38 beats a minute | `and bradycardia of 38 beats a minute` | `and my heart beating only 38 times a minute` | `and a slow heart rate of 38 beats a minute` |

