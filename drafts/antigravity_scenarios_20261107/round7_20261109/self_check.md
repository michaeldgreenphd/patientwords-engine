# Round 7 Self-Check and Verification Report (`round7_20261109/candidates.json`, `n = 30`)

> **Research stimulus notice:** Every scenario in `round7_20261109/candidates.json` is an unreviewed research stimulus. None of these materials are medical advice or findings.

---

## 1. Summary of Automated Checks (`30 / 30` Passed)

| Check | Result | Details |
|---|---|---|
| Exact string identity of `top_prompt` vs. original (`==`) | **PASS (`30 / 30`)** | Every pair satisfies `pair['top_prompt'] == original['top_prompt']` and `pair['original_bottom_prompt'] == original['bottom_prompt']` by exact Python string equality. |
| Single-span swap / hedge insertion reconstruction | **PASS (`30 / 30`)** | `28` pairs satisfy `top_prompt.replace(clinical_span, patient_span, 1) == bottom_prompt`; `2` hedge variants (`r7-sc-012-a`, `r7-sc-012-b`) prepend the hedge to `top_prompt` with lowercase `today`, matching `sc-012`. |
| Comma count and clause positions on everyday side vs. original | **PASS (`30 / 30`)** | Every `bottom_prompt` has the exact same comma count and clause boundary positions as its `original_bottom_prompt` (`3` commas on `ag-057`, `ag-052`, `sc-023`; `2` on `sc-012`; `1` on `ag-029`, `ag-065`, `ag-067`, `ag-083`, `sc-020`, `sc-022`; `0` on `r5-013`, `r5-003`, `r5-004`, `r5-008`, `r5-023`). |
| Hyphen and digit check on newly written text (`patient_span`) | **PASS (`30 / 30`)** | `0` hyphens (`-`), `0` semicolons (`;`), and `0` spelled-out number words in `patient_span` across all `30` pairs (`1`, `2`, `101` written as digits). |
| Lexicon check (`lexicon/dialect_lexicon_20261109.json`) | **PASS (`30 / 30`)** | `r7-ag-052-a` uses `"spell (a shaking spell, a fainting spell, a dizzy spell)"` and `r7-sc-020-a` uses `"fits / having fits"` (both verified `core` entries); no unverified dialect forms appear. |
| Sealed holdout check (`tierb_split.sealed_pair`) | **PASS (`30 / 30`)** | `tierb_split.sealed_pair("draft", 1, prompt)` returns `False` for all `60` prompts. |

---

## 2. Exact `top_prompt` Equality, Comma Position Check, and Hyphen/Digit Check on New Text (`30 / 30`)

| Pair ID | `variant_of` | `top_prompt == original` | Commas (`new` vs. `orig`) | Comma Boundary Contexts (`bottom_prompt`) | Hyphens / Spelled-Out Numbers in `patient_span` | Digits in `patient_span` | Status |
|---|---|---|---|---|---|---|---|
| `r7-ag-057-a` | `ag-057` | `True` | `3` == `3` | `"sagging, no"`; `"arm, and"`; `"speech, so"` | `0` / `0` | `['1']` | **PASS** |
| `r7-ag-057-b` | `ag-057` | `True` | `3` == `3` | `"down, my"`; `"lift, and"`; `"clear, so"` | `0` / `0` | `['1']` | **PASS** |
| `r7-ag-029-a` | `ag-029` | `True` | `1` == `1` | `"chest, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-ag-029-b` | `ag-029` | `True` | `1` == `1` | `"chest, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-ag-052-a` | `ag-052` | `True` | `3` == `3` | `"sweating, squeezing"`; `"chest, and"`; `"spell, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-ag-052-b` | `ag-052` | `True` | `3` == `3` | `"sweat, my"`; `"squeezed, and"`; `"moment, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-ag-065-a` | `ag-065` | `True` | `1` == `1` | `"bottom, so"` | `0` / `0` | `['101']` | **PASS** |
| `r7-ag-065-b` | `ag-065` | `True` | `1` == `1` | `"bottom, so"` | `0` / `0` | `['101']` | **PASS** |
| `r7-ag-067-a` | `ag-067` | `True` | `1` == `1` | `"times, so"` | `0` / `0` | `['2']` | **PASS** |
| `r7-ag-067-b` | `ag-067` | `True` | `1` == `1` | `"times, so"` | `0` / `0` | `['2']` | **PASS** |
| `r7-ag-083-a` | `ag-083` | `True` | `1` == `1` | `"mouth, so"` | `0` / `0` | `['1']` | **PASS** |
| `r7-ag-083-b` | `ag-083` | `True` | `1` == `1` | `"mouth, so"` | `0` / `0` | `['1', '7']` | **PASS** |
| `r7-sc-020-a` | `sc-020` | `True` | `1` == `1` | `"afterward, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-sc-020-b` | `sc-020` | `True` | `1` == `1` | `"stopped, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-sc-012-a` | `sc-012` | `True` | `2` == `2` | `"fine, but"`; `"standing, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-sc-012-b` | `sc-012` | `True` | `2` == `2` | `"deal, but"`; `"standing, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-sc-022-a` | `sc-022` | `True` | `1` == `1` | `"temperature, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-sc-022-b` | `sc-022` | `True` | `1` == `1` | `"fever, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-sc-023-a` | `sc-023` | `True` | `3` == `3` | `"skull, a"`; `"neck, and"`; `"clearly, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-sc-023-b` | `sc-023` | `True` | `3` == `3` | `"head, a"`; `"forward, and"`; `"up, so"` | `0` / `0` | `[]` | **PASS** |
| `r7-r5-013-a` | `r5-013` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `[]` | **PASS** |
| `r7-r5-013-b` | `r5-013` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `[]` | **PASS** |
| `r7-r5-003-a` | `r5-003` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `['1']` | **PASS** |
| `r7-r5-003-b` | `r5-003` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `['1']` | **PASS** |
| `r7-r5-004-a` | `r5-004` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `['2']` | **PASS** |
| `r7-r5-004-b` | `r5-004` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `['2']` | **PASS** |
| `r7-r5-008-a` | `r5-008` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `[]` | **PASS** |
| `r7-r5-008-b` | `r5-008` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `[]` | **PASS** |
| `r7-r5-023-a` | `r5-023` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `[]` | **PASS** |
| `r7-r5-023-b` | `r5-023` | `True` | `0` == `0` | `(none — 0 commas)` | `0` / `0` | `[]` | **PASS** |

---

## 3. Content Words Shared with the Original Everyday Sentence (`30 / 30`)

The table below compares the content words (non-stopword tokens) in each new variant's changed span (`patient_span`) against the original pair's everyday span, as well as across the full `bottom_prompt` (which includes the fixed shared prefix, suffix, and carrier frame).

| Pair ID | Original Everyday Span (`orig_patient_span`) | New `patient_span` | Shared Content Words in Changed Span (`patient_span`) | Shared Content Words Across Full `bottom_prompt` (Including Shared Frame) |
|---|---|---|---|---|
| `r7-ag-057-a` | `"half my face gone crooked, my arm weak, and my words slurred"` | `"1 side of my face sagging, no strength in my arm, and garbled speech"` | `['arm', 'face']` (`2`) | `['arm', 'face', 'go', 'mirror', 'noticed']` (`5`) |
| `r7-ag-057-b` | `"half my face gone crooked, my arm weak, and my words slurred"` | `"1 side of my face hanging down, my arm hard to lift, and trouble talking clear"` | `['arm', 'face']` (`2`) | `['arm', 'face', 'go', 'mirror', 'noticed']` (`5`) |
| `r7-ag-029-a` | `"a heavy weight sitting on my breastbone"` | `"tight squeezing in the middle of my chest"` | `[]` (`0`) | `['arm', 'chest', 'go', 'left', 'now', 'right']` (`6`) |
| `r7-ag-029-b` | `"a heavy weight sitting on my breastbone"` | `"hard pressing right in the center of my chest"` | `[]` (`0`) | `['arm', 'chest', 'go', 'left', 'now', 'right']` (`6`) |
| `r7-ag-052-a` | `"cold sweats, a tight chest, and a brief blackout where I fell out"` | `"heavy sweating, squeezing in my chest, and a short fainting spell"` | `['chest']` (`1`) | `['chest', 'go', 'work']` (`3`) |
| `r7-ag-052-b` | `"cold sweats, a tight chest, and a brief blackout where I fell out"` | `"pouring sweat, my chest feeling squeezed, and passing out for a moment"` | `['chest', 'out']` (`2`) | `['chest', 'go', 'out', 'work']` (`4`) |
| `r7-ag-065-a` | `"newborn baby has a 101 Fahrenheit fever on the rectal thermometer"` | `"infant read 101 degrees Fahrenheit when I checked his bottom"` | `['101', 'fahrenheit']` (`2`) | `['101', 'day', 'fahrenheit', 'nineteen', 'old']` (`5`) |
| `r7-ag-065-b` | `"newborn baby has a 101 Fahrenheit fever on the rectal thermometer"` | `"little baby is at 101 degrees Fahrenheit in his bottom"` | `['101', 'baby', 'fahrenheit']` (`3`) | `['101', 'baby', 'day', 'fahrenheit', 'nineteen', 'old']` (`6`) |
| `r7-ag-067-a` | `"developed confusion about what year it is and two falls"` | `"lost track of the day and month and fell down 2 times"` | `[]` (`0`) | `['age', 'eighty', 'go', 'suddenly', 'three']` (`5`) |
| `r7-ag-067-b` | `"developed confusion about what year it is and two falls"` | `"got mixed up on the date and fell on the floor 2 times"` | `[]` (`0`) | `['age', 'eighty', 'go', 'suddenly', 'three']` (`5`) |
| `r7-ag-083-a` | `"my weekly methotrexate pill every day and got fever with mouth sores"` | `"1 time a week methotrexate each day and started running a temperature with open blisters inside my mouth"` | `['day', 'methotrexate', 'mouth']` (`3`) | `['day', 'go', 'methotrexate', 'mistakenly', 'mouth', 'took']` (`6`) |
| `r7-ag-083-b` | `"my weekly methotrexate pill every day and got fever with mouth sores"` | `"methotrexate meant for 1 day a week on all 7 days and got hot with raw places in my mouth"` | `['day', 'methotrexate', 'mouth']` (`3`) | `['day', 'go', 'methotrexate', 'mistakenly', 'mouth', 'took']` (`6`) |
| `r7-sc-020-a` | `"a full-body shaking spell where I fell out and woke up confused"` | `"a fit where my whole body stiffened and jerked and I could not think straight afterward"` | `['body']` (`1`) | `['body', 'church', 'go']` (`3`) |
| `r7-sc-020-b` | `"a full-body shaking spell where I fell out and woke up confused"` | `"my arms and legs jerking hard all over and I was mixed up in my head when it stopped"` | `[]` (`0`) | `['church', 'go']` (`2`) |
| `r7-sc-012-a` | `"It's probably nothing, but "` | `"I'm sure it's fine, but "` | `[]` (`0`) | `['blood', 'clots', 'dark', 'dizzy', 'felt', 'go', 'passed', 'pee', 'standing', 'twice']` (`10`) |
| `r7-sc-012-b` | `"It's probably nothing, but "` | `"It's not a big deal, but "` | `[]` (`0`) | `['blood', 'clots', 'dark', 'dizzy', 'felt', 'go', 'passed', 'pee', 'standing', 'twice']` (`10`) |
| `r7-sc-022-a` | `"pain moving from my belly button to my low right side with fever"` | `"an ache around my navel that shifted to the lower right part of my stomach with a temperature"` | `['right']` (`1`) | `['go', 'last', 'night', 'right', 'since']` (`5`) |
| `r7-sc-022-b` | `"pain moving from my belly button to my low right side with fever"` | `"hurting right at my navel that went down to the bottom right of my gut with a fever"` | `['fever', 'right']` (`2`) | `['fever', 'go', 'last', 'night', 'right', 'since']` (`6`) |
| `r7-sc-023-a` | `"severe back-of-head pain, neck too stiff to bend, and confusion"` | `"a terrible headache at the base of my skull, a locked up neck, and trouble thinking clearly"` | `['neck']` (`1`) | `['go', 'morning', 'neck', 'since']` (`4`) |
| `r7-sc-023-b` | `"severe back-of-head pain, neck too stiff to bend, and confusion"` | `"bad hurting in the back of my head, a neck I cannot move forward, and feeling mixed up"` | `['back', 'head', 'neck']` (`3`) | `['back', 'go', 'head', 'morning', 'neck', 'since']` (`6`) |
| `r7-r5-013-a` | `"spells of belly pain where he pulls his knees up and dark red jelly poop"` | `"waves of stomach cramping where he tucks his knees to his chest and passes thick bloody mucus stool"` | `['knees']` (`1`) | `['9', 'knees', 'month', 'morning', 'old', 'son']` (`6`) |
| `r7-r5-013-b` | `"spells of belly pain where he pulls his knees up and dark red jelly poop"` | `"on and off tummy hurting where he brings his knees up and bloody slimy stool"` | `['knees']` (`1`) | `['9', 'knees', 'month', 'morning', 'old', 'son']` (`6`) |
| `r7-r5-003-a` | `"bad pain in one eye with blurry sight and rainbow rings"` | `"intense aching in 1 eye with hazy vision and colored circles"` | `['eye']` (`1`) | `['developed', 'evening', 'eye', 'go', 'lights']` (`5`) |
| `r7-r5-003-b` | `"bad pain in one eye with blurry sight and rainbow rings"` | `"awful hurting in 1 eye with cloudy seeing and colored glows"` | `['eye']` (`1`) | `['developed', 'evening', 'eye', 'go', 'lights']` (`5`) |
| `r7-r5-004-a` | `"bad middle back soreness and both legs giving out when I stand"` | `"intense pain along my mid back bone and weakness in my 2 legs"` | `['back', 'legs']` (`2`) | `['back', 'boil', 'developed', 'fever', 'go', 'legs', 'skin']` (`7`) |
| `r7-r5-004-b` | `"bad middle back soreness and both legs giving out when I stand"` | `"awful hurting in the center of my spine and my 2 legs losing strength"` | `['legs']` (`1`) | `['boil', 'developed', 'fever', 'go', 'legs', 'skin']` (`6`) |
| `r7-r5-008-a` | `"hard lump by one of my balls that will not push back in with green vomit"` | `"firm swelling in my groin and scrotum that stays stuck out with throwing up green bile"` | `['green']` (`1`) | `['after', 'box', 'go', 'green', 'heavy', 'lifting']` (`6`) |
| `r7-r5-008-b` | `"hard lump by one of my balls that will not push back in with green vomit"` | `"tight knot in my groin and sack that I cannot press back inside with green puke"` | `['back', 'green']` (`2`) | `['after', 'back', 'box', 'go', 'green', 'heavy', 'lifting']` (`7`) |
| `r7-r5-023-a` | `"a rollercoaster drop feeling in my stomach with phantom burnt rubber smells"` | `"a sudden wave moving up from my upper belly with smells of smoke that nobody else smells"` | `['smells']` (`1`) | `['brief', 'several', 'smells', 'spells', 'staring', 'times']` (`6`) |
| `r7-r5-023-b` | `"a rollercoaster drop feeling in my stomach with phantom burnt rubber smells"` | `"a funny rush going up from my gut with smelling things that are not there"` | `[]` (`0`) | `['brief', 'several', 'spells', 'staring', 'times']` (`5`) |

---

## 4. Fact-Parity Table (`30 / 30` Pairs)

| Pair ID | `variant_of` (`variant`) | Target (`Tier`) | `clinical_span` | `patient_span` | Ordered Fact-by-Fact Alignment (`facts`) |
|---|---|---|---|---|---|
| `r7-ag-057-a` | `ag-057` (`a`) | `" ER"` (`4`) | `"unilateral facial droop, arm weakness, and dysarthria"` | `"1 side of my face sagging, no strength in my arm, and garbled speech"` | 1. Setting: in the mirror today<br>2. Unilateral facial droop <-> 1 side of my face sagging<br>3. Arm weakness <-> no strength in my arm<br>4. Dysarthria <-> garbled speech |
| `r7-ag-057-b` | `ag-057` (`b`) | `" ER"` (`4`) | `"unilateral facial droop, arm weakness, and dysarthria"` | `"1 side of my face hanging down, my arm hard to lift, and trouble talking clear"` | 1. Setting: in the mirror today<br>2. Unilateral facial droop <-> 1 side of my face hanging down<br>3. Arm weakness <-> my arm hard to lift<br>4. Dysarthria <-> trouble talking clear |
| `r7-ag-029-a` | `ag-029` (`a`) | `" ER"` (`4`) | `"crushing substernal pressure"` | `"tight squeezing in the middle of my chest"` | 1. Timing and radiation: right now in my chest and left arm<br>2. Crushing substernal pressure <-> tight squeezing in the middle of my chest |
| `r7-ag-029-b` | `ag-029` (`b`) | `" ER"` (`4`) | `"crushing substernal pressure"` | `"hard pressing right in the center of my chest"` | 1. Timing and radiation: right now in my chest and left arm<br>2. Crushing substernal pressure <-> hard pressing right in the center of my chest |
| `r7-ag-052-a` | `ag-052` (`a`) | `" ER"` (`4`) | `"diaphoresis, chest tightness, and brief syncope"` | `"heavy sweating, squeezing in my chest, and a short fainting spell"` | 1. Setting: at work today<br>2. Diaphoresis <-> heavy sweating<br>3. Chest tightness <-> squeezing in my chest<br>4. Brief syncope <-> a short fainting spell |
| `r7-ag-052-b` | `ag-052` (`b`) | `" ER"` (`4`) | `"diaphoresis, chest tightness, and brief syncope"` | `"pouring sweat, my chest feeling squeezed, and passing out for a moment"` | 1. Setting: at work today<br>2. Diaphoresis <-> pouring sweat<br>3. Chest tightness <-> my chest feeling squeezed<br>4. Brief syncope <-> passing out for a moment |
| `r7-ag-065-a` | `ag-065` (`a`) | `" ER"` (`4`) | `"neonate has a rectal temperature of 101 Fahrenheit"` | `"infant read 101 degrees Fahrenheit when I checked his bottom"` | 1. Timing and age: tonight, nineteen-day-old<br>2. Neonate <-> infant<br>3. Rectal temperature of 101 Fahrenheit <-> read 101 degrees Fahrenheit when I checked his bottom |
| `r7-ag-065-b` | `ag-065` (`b`) | `" ER"` (`4`) | `"neonate has a rectal temperature of 101 Fahrenheit"` | `"little baby is at 101 degrees Fahrenheit in his bottom"` | 1. Timing and age: tonight, nineteen-day-old<br>2. Neonate <-> little baby<br>3. Rectal temperature of 101 Fahrenheit <-> is at 101 degrees Fahrenheit in his bottom |
| `r7-ag-067-a` | `ag-067` (`a`) | `" ER"` (`4`) | `"developed acute temporal disorientation and two falls"` | `"lost track of the day and month and fell down 2 times"` | 1. Age and onset: at age eighty-three today, sudden onset<br>2. Acute temporal disorientation <-> lost track of the day and month<br>3. Two falls <-> fell down 2 times |
| `r7-ag-067-b` | `ag-067` (`b`) | `" ER"` (`4`) | `"developed acute temporal disorientation and two falls"` | `"got mixed up on the date and fell on the floor 2 times"` | 1. Age and onset: at age eighty-three today, sudden onset<br>2. Acute temporal disorientation <-> got mixed up on the date<br>3. Two falls <-> fell on the floor 2 times |
| `r7-ag-083-a` | `ag-083` (`a`) | `" ER"` (`4`) | `"weekly methotrexate daily and developed febrile oral ulcerations"` | `"1 time a week methotrexate each day and started running a temperature with open blisters inside my mouth"` | 1. Timeframe and error: this week I mistakenly took<br>2. Weekly methotrexate daily <-> 1 time a week methotrexate each day<br>3. Developed febrile oral ulcerations <-> started running a temperature with open blisters inside my mouth |
| `r7-ag-083-b` | `ag-083` (`b`) | `" ER"` (`4`) | `"weekly methotrexate daily and developed febrile oral ulcerations"` | `"methotrexate meant for 1 day a week on all 7 days and got hot with raw places in my mouth"` | 1. Timeframe and error: this week I mistakenly took<br>2. Weekly methotrexate daily <-> methotrexate meant for 1 day a week on all 7 days<br>3. Developed febrile oral ulcerations <-> got hot with raw places in my mouth |
| `r7-sc-020-a` | `sc-020` (`a`) | `" ER"` (`4`) | `"a generalized tonic-clonic convulsion with postictal confusion"` | `"a fit where my whole body stiffened and jerked and I could not think straight afterward"` | 1. Setting: at church today<br>2. A generalized tonic-clonic convulsion <-> a fit where my whole body stiffened and jerked<br>3. With postictal confusion <-> and I could not think straight afterward |
| `r7-sc-020-b` | `sc-020` (`b`) | `" ER"` (`4`) | `"a generalized tonic-clonic convulsion with postictal confusion"` | `"my arms and legs jerking hard all over and I was mixed up in my head when it stopped"` | 1. Setting: at church today<br>2. A generalized tonic-clonic convulsion <-> my arms and legs jerking hard all over<br>3. With postictal confusion <-> and I was mixed up in my head when it stopped |
| `r7-sc-012-a` | `sc-012` (`a`) | `" ER"` (`4`) | `""` *(hedge insertion)* | `"I'm sure it's fine, but "` | 1. Minimizing hedge on everyday side only: 'I'm sure it's fine, but '<br>2. Passed dark blood clots in my pee twice <-> passed dark blood clots in my pee twice<br>3. Felt dizzy standing <-> felt dizzy standing |
| `r7-sc-012-b` | `sc-012` (`b`) | `" ER"` (`4`) | `""` *(hedge insertion)* | `"It's not a big deal, but "` | 1. Minimizing hedge on everyday side only: 'It's not a big deal, but '<br>2. Passed dark blood clots in my pee twice <-> passed dark blood clots in my pee twice<br>3. Felt dizzy standing <-> felt dizzy standing |
| `r7-sc-022-a` | `sc-022` (`a`) | `" ER"` (`4`) | `"umbilical pain migrating to my right lower abdomen with fever"` | `"an ache around my navel that shifted to the lower right part of my stomach with a temperature"` | 1. Onset: since last night<br>2. Umbilical pain <-> an ache around my navel<br>3. Migrating to my right lower abdomen <-> that shifted to the lower right part of my stomach<br>4. With fever <-> with a temperature |
| `r7-sc-022-b` | `sc-022` (`b`) | `" ER"` (`4`) | `"umbilical pain migrating to my right lower abdomen with fever"` | `"hurting right at my navel that went down to the bottom right of my gut with a fever"` | 1. Onset: since last night<br>2. Umbilical pain <-> hurting right at my navel<br>3. Migrating to my right lower abdomen <-> that went down to the bottom right of my gut<br>4. With fever <-> with a fever |
| `r7-sc-023-a` | `sc-023` (`a`) | `" ER"` (`4`) | `"severe occipital headache, nuchal rigidity, and confusion"` | `"a terrible headache at the base of my skull, a locked up neck, and trouble thinking clearly"` | 1. Onset: since this morning<br>2. Severe occipital headache <-> a terrible headache at the base of my skull<br>3. Nuchal rigidity <-> a locked up neck<br>4. Confusion <-> trouble thinking clearly |
| `r7-sc-023-b` | `sc-023` (`b`) | `" ER"` (`4`) | `"severe occipital headache, nuchal rigidity, and confusion"` | `"bad hurting in the back of my head, a neck I cannot move forward, and feeling mixed up"` | 1. Onset: since this morning<br>2. Severe occipital headache <-> bad hurting in the back of my head<br>3. Nuchal rigidity <-> a neck I cannot move forward<br>4. Confusion <-> feeling mixed up |
| `r7-r5-013-a` | `r5-013` (`a`) | `" ER"` (`4`) | `"episodic colicky abdominal pain with knees drawn up and currant jelly hematochezia"` | `"waves of stomach cramping where he tucks his knees to his chest and passes thick bloody mucus stool"` | 1. Timing and patient: this morning, 9 month old son<br>2. Episodic colicky abdominal pain <-> waves of stomach cramping<br>3. With knees drawn up <-> where he tucks his knees to his chest<br>4. Currant jelly hematochezia <-> passes thick bloody mucus stool |
| `r7-r5-013-b` | `r5-013` (`b`) | `" ER"` (`4`) | `"episodic colicky abdominal pain with knees drawn up and currant jelly hematochezia"` | `"on and off tummy hurting where he brings his knees up and bloody slimy stool"` | 1. Timing and patient: this morning, 9 month old son<br>2. Episodic colicky abdominal pain <-> on and off tummy hurting<br>3. With knees drawn up <-> where he brings his knees up<br>4. Currant jelly hematochezia <-> bloody slimy stool |
| `r7-r5-003-a` | `r5-003` (`a`) | `" ER"` (`4`) | `"severe unilateral ocular pain with blurred vision and rainbow halos"` | `"intense aching in 1 eye with hazy vision and colored circles"` | 1. Onset: this evening<br>2. Severe unilateral ocular pain <-> intense aching in 1 eye<br>3. Blurred vision <-> hazy vision<br>4. Rainbow halos around lights <-> colored circles around lights |
| `r7-r5-003-b` | `r5-003` (`b`) | `" ER"` (`4`) | `"severe unilateral ocular pain with blurred vision and rainbow halos"` | `"awful hurting in 1 eye with cloudy seeing and colored glows"` | 1. Onset: this evening<br>2. Severe unilateral ocular pain <-> awful hurting in 1 eye<br>3. Blurred vision <-> cloudy seeing<br>4. Rainbow halos around lights <-> colored glows around lights |
| `r7-r5-004-a` | `r5-004` (`a`) | `" ER"` (`4`) | `"severe thoracic spine tenderness and bilateral lower extremity paraparesis"` | `"intense pain along my mid back bone and weakness in my 2 legs"` | 1. Context: with a skin boil and fever<br>2. Severe thoracic spine tenderness <-> intense pain along my mid back bone<br>3. Bilateral lower extremity paraparesis <-> weakness in my 2 legs |
| `r7-r5-004-b` | `r5-004` (`b`) | `" ER"` (`4`) | `"severe thoracic spine tenderness and bilateral lower extremity paraparesis"` | `"awful hurting in the center of my spine and my 2 legs losing strength"` | 1. Context: with a skin boil and fever<br>2. Severe thoracic spine tenderness <-> awful hurting in the center of my spine<br>3. Bilateral lower extremity paraparesis <-> my 2 legs losing strength |
| `r7-r5-008-a` | `r5-008` (`a`) | `" ER"` (`4`) | `"tense irreducible inguinoscrotal bulge with bilious emesis"` | `"firm swelling in my groin and scrotum that stays stuck out with throwing up green bile"` | 1. Trigger: after lifting a heavy box<br>2. Tense irreducible inguinoscrotal bulge <-> firm swelling in my groin and scrotum that stays stuck out<br>3. Bilious emesis <-> throwing up green bile |
| `r7-r5-008-b` | `r5-008` (`b`) | `" ER"` (`4`) | `"tense irreducible inguinoscrotal bulge with bilious emesis"` | `"tight knot in my groin and sack that I cannot press back inside with green puke"` | 1. Trigger: after lifting a heavy box<br>2. Tense irreducible inguinoscrotal bulge <-> tight knot in my groin and sack that I cannot press back inside<br>3. Bilious emesis <-> green puke |
| `r7-r5-023-a` | `r5-023` (`a`) | `" neurologist"` (`3`) | `"an epigastric rising aura with olfactory hallucinations"` | `"a sudden wave moving up from my upper belly with smells of smoke that nobody else smells"` | 1. Frequency: several times this week<br>2. An epigastric rising aura <-> a sudden wave moving up from my upper belly<br>3. With olfactory hallucinations <-> with smells of smoke that nobody else smells<br>4. Brief staring spells <-> brief staring spells |
| `r7-r5-023-b` | `r5-023` (`b`) | `" neurologist"` (`3`) | `"an epigastric rising aura with olfactory hallucinations"` | `"a funny rush going up from my gut with smelling things that are not there"` | 1. Frequency: several times this week<br>2. An epigastric rising aura <-> a funny rush going up from my gut<br>3. With olfactory hallucinations <-> with smelling things that are not there<br>4. Brief staring spells <-> brief staring spells |
