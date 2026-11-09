# Round 7b Self-Check and Verification Report (`round7b_20261109/candidates.json`, `n = 5`)

> **Research stimulus notice:** Every scenario in `round7b_20261109/candidates.json` is an unreviewed research stimulus replacing one of the five comma-excluded Round 7 variants (`r7-ag-052-a`, `r7-ag-052-b`, `r7-ag-057-a`, `r7-ag-057-b`, `r7-sc-023-a`). None of these materials are medical advice or findings.

---

## 1. Summary of Automated Checks (`5 / 5` Passed)

| Check | Result | Details |
|---|---|---|
| Exact string identity of `top_prompt` vs. original (`==`) | **PASS (`5 / 5`)** | Every pair satisfies `pair['top_prompt'] == original['top_prompt']` (including all 3 commas in each original clinical sentence) and `pair['original_bottom_prompt'] == original['bottom_prompt']`. |
| Zero commas on the everyday side (`bottom_prompt.count(',') == 0`) | **PASS (`5 / 5`)** | Every `bottom_prompt` has `0` commas (`bottom_prompt.count(',') == 0`), joining the three symptoms with `'with'` and `'and'` and ending with `' so I need to go to the'`. |
| Single-span swap reconstruction (`top_prompt.replace(clinical_span, patient_span, 1) == bottom_prompt`) | **PASS (`5 / 5`)** | Every pair reconstructs `bottom_prompt` from `top_prompt` via a single unique span replacement (`clinical_span` includes the trailing comma before `' so I need to go to the'`). |
| Hyphen, digit, and spelling check on new text (`patient_span`) | **PASS (`5 / 5`)** | `0` hyphens (`-`), `0` semicolons (`;`), `0` spelled-out number words (`1` written as a digit in `r7-ag-057-a-nc` and `r7-ag-057-b-nc`), and `0` misspellings. |
| Lexicon check (`lexicon/dialect_lexicon_20261109.json`) | **PASS (`5 / 5`)** | `r7-ag-052-a-nc` uses `'spell (a shaking spell, a fainting spell, a dizzy spell)'` from `core`; the other 4 pairs have `lexicon_entries: []`. |
| Sealed holdout check (`tierb_split.sealed_pair`) | **PASS (`5 / 5`)** | `tierb_split.sealed_pair('draft', 1, prompt)` returns `False` for all 10 prompts. |

---

## 2. `top_prompt` String Comparison (`==`), Zero-Comma Check on `bottom_prompt`, and Hyphen/Digit Check (`5 / 5`)

| Pair ID | `replaces` | `variant_of` | `top_prompt == original['top_prompt']` | `top_prompt` Commas | `bottom_prompt` Commas | Hyphens / Spelled-Out Numbers in `patient_span` | Digits in `patient_span` | Shared Content Words in Changed Span vs. Original Everyday Span | Status |
|---|---|---|---|---|---|---|---|---|---|
| `r7-ag-052-a-nc` | `r7-ag-052-a` | `ag-052` | `True` | `3` | **`0`** | `0` / `0` | `[]` | `['chest']` (`1`) | **PASS** |
| `r7-ag-052-b-nc` | `r7-ag-052-b` | `ag-052` | `True` | `3` | **`0`** | `0` / `0` | `[]` | `['chest']` (`1`) | **PASS** |
| `r7-ag-057-a-nc` | `r7-ag-057-a` | `ag-057` | `True` | `3` | **`0`** | `0` / `0` | `['1']` | `['arm', 'face']` (`2`) | **PASS** |
| `r7-ag-057-b-nc` | `r7-ag-057-b` | `ag-057` | `True` | `3` | **`0`** | `0` / `0` | `['1']` | `['arm', 'face']` (`2`) | **PASS** |
| `r7-sc-023-a-nc` | `r7-sc-023-a` | `sc-023` | `True` | `3` | **`0`** | `0` / `0` | `[]` | `['neck']` (`1`) | **PASS** |

### Full Sentences for All 5 Replacements

#### `r7-ag-052-a-nc` (replaces `r7-ag-052-a`, variant `a` of `ag-052`)
- **`top_prompt`** (`3` commas, `== original['top_prompt']`: `True`): `At work today I had diaphoresis, chest tightness, and brief syncope, so I need to go to the`
- **`original_bottom_prompt`**: `At work today I had cold sweats, a tight chest, and a brief blackout where I fell out, so I need to go to the`
- **`bottom_prompt`** (`0` commas): `At work today I had heavy sweating with squeezing in my chest and a short fainting spell so I need to go to the`
- **`lexicon_entries`**: `['spell (a shaking spell, a fainting spell, a dizzy spell)']`
- **Shared content words across full `bottom_prompt`**: `['chest', 'go', 'work']` (`3`)

#### `r7-ag-052-b-nc` (replaces `r7-ag-052-b`, variant `b` of `ag-052`)
- **`top_prompt`** (`3` commas, `== original['top_prompt']`: `True`): `At work today I had diaphoresis, chest tightness, and brief syncope, so I need to go to the`
- **`original_bottom_prompt`**: `At work today I had cold sweats, a tight chest, and a brief blackout where I fell out, so I need to go to the`
- **`bottom_prompt`** (`0` commas): `At work today I had pouring sweat with my chest feeling squeezed and passing out for a moment so I need to go to the`
- **`lexicon_entries`**: `[]`
- **Shared content words across full `bottom_prompt`**: `['chest', 'go', 'work']` (`3`)

#### `r7-ag-057-a-nc` (replaces `r7-ag-057-a`, variant `a` of `ag-057`)
- **`top_prompt`** (`3` commas, `== original['top_prompt']`: `True`): `In the mirror today I noticed unilateral facial droop, arm weakness, and dysarthria, so I need to go to the`
- **`original_bottom_prompt`**: `In the mirror today I noticed half my face gone crooked, my arm weak, and my words slurred, so I need to go to the`
- **`bottom_prompt`** (`0` commas): `In the mirror today I noticed 1 side of my face sagging with my arm losing strength and garbled speech so I need to go to the`
- **`lexicon_entries`**: `[]`
- **Shared content words across full `bottom_prompt`**: `['arm', 'face', 'go', 'mirror', 'noticed']` (`5`)

#### `r7-ag-057-b-nc` (replaces `r7-ag-057-b`, variant `b` of `ag-057`)
- **`top_prompt`** (`3` commas, `== original['top_prompt']`: `True`): `In the mirror today I noticed unilateral facial droop, arm weakness, and dysarthria, so I need to go to the`
- **`original_bottom_prompt`**: `In the mirror today I noticed half my face gone crooked, my arm weak, and my words slurred, so I need to go to the`
- **`bottom_prompt`** (`0` commas): `In the mirror today I noticed 1 side of my face hanging down with my arm hard to lift and trouble talking clear so I need to go to the`
- **`lexicon_entries`**: `[]`
- **Shared content words across full `bottom_prompt`**: `['arm', 'face', 'go', 'mirror', 'noticed']` (`5`)

#### `r7-sc-023-a-nc` (replaces `r7-sc-023-a`, variant `a` of `sc-023`)
- **`top_prompt`** (`3` commas, `== original['top_prompt']`: `True`): `Since this morning I have severe occipital headache, nuchal rigidity, and confusion, so I need to go to the`
- **`original_bottom_prompt`**: `Since this morning I have severe back-of-head pain, neck too stiff to bend, and confusion, so I need to go to the`
- **`bottom_prompt`** (`0` commas): `Since this morning I have a terrible headache at the base of my skull with a locked up neck and trouble thinking clearly so I need to go to the`
- **`lexicon_entries`**: `[]`
- **Shared content words across full `bottom_prompt`**: `['go', 'morning', 'neck', 'since']` (`4`)

---

## 3. Fact-Parity Table (`5 / 5` Pairs)

| Pair ID | `replaces` | `variant_of` (`variant`) | Target (`Tier`) | `clinical_span` | `patient_span` (`0` commas) | Ordered Fact-by-Fact Alignment (`facts`) |
|---|---|---|---|---|---|---|
| `r7-ag-052-a-nc` | `r7-ag-052-a` | `ag-052` (`a`) | `" ER"` (`4`) | `"diaphoresis, chest tightness, and brief syncope,"` | `"heavy sweating with squeezing in my chest and a short fainting spell"` | 1. Setting: at work today<br>2. Diaphoresis <-> heavy sweating<br>3. Chest tightness <-> squeezing in my chest<br>4. Brief syncope <-> a short fainting spell |
| `r7-ag-052-b-nc` | `r7-ag-052-b` | `ag-052` (`b`) | `" ER"` (`4`) | `"diaphoresis, chest tightness, and brief syncope,"` | `"pouring sweat with my chest feeling squeezed and passing out for a moment"` | 1. Setting: at work today<br>2. Diaphoresis <-> pouring sweat<br>3. Chest tightness <-> my chest feeling squeezed<br>4. Brief syncope <-> passing out for a moment |
| `r7-ag-057-a-nc` | `r7-ag-057-a` | `ag-057` (`a`) | `" ER"` (`4`) | `"unilateral facial droop, arm weakness, and dysarthria,"` | `"1 side of my face sagging with my arm losing strength and garbled speech"` | 1. Setting: in the mirror today<br>2. Unilateral facial droop <-> 1 side of my face sagging<br>3. Arm weakness <-> my arm losing strength<br>4. Dysarthria <-> garbled speech |
| `r7-ag-057-b-nc` | `r7-ag-057-b` | `ag-057` (`b`) | `" ER"` (`4`) | `"unilateral facial droop, arm weakness, and dysarthria,"` | `"1 side of my face hanging down with my arm hard to lift and trouble talking clear"` | 1. Setting: in the mirror today<br>2. Unilateral facial droop <-> 1 side of my face hanging down<br>3. Arm weakness <-> my arm hard to lift<br>4. Dysarthria <-> trouble talking clear |
| `r7-sc-023-a-nc` | `r7-sc-023-a` | `sc-023` (`a`) | `" ER"` (`4`) | `"severe occipital headache, nuchal rigidity, and confusion,"` | `"a terrible headache at the base of my skull with a locked up neck and trouble thinking clearly"` | 1. Onset: since this morning<br>2. Severe occipital headache <-> a terrible headache at the base of my skull<br>3. Nuchal rigidity <-> a locked up neck<br>4. Confusion <-> trouble thinking clearly |
