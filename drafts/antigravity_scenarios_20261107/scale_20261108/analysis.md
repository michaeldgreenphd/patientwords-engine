# Ground-Truth Analysis & Scale Round Plan (`scale_20261108`)

Source ground truth: [`ground_truth/gt_20261108.json`](../ground_truth/gt_20261108.json) (owner read of [`candidates_v3.json`](../candidates_v3.json) at commit `f3be9e8a`, dated `2026-11-08`).

## 1. Summary Table by Family (`gt_20261108.json`)

Across all **65** evaluated pairs in `candidates_v3.json`: **62** were **confirmed** (**58** `right` + **4** `retier`), **3** were **excluded** (**1** `unrealistic`, **2** `other`), and **0** have been **measured** yet (`measured: null` on all 65 entries pending CI tracing).

| Family | Evaluated | Confirmed (`right` + `retier`) | `right` (IDs) | `retier` (IDs & `tier_given → tier_should`) | `excluded` (IDs & reason) | `measured` / `downgrade` | New Pairs in `scale_20261108` |
|---|---:|---:|---|---|---|---|---:|
| `red_flag_everyday` | 12 | **12** | 12 (`ag-001`, `ag-002`, `ag-003`, `ag-004`, `ag-005`, `ag-006`, `ag-007`, `ag-008`, `ag-011`, `ag-012`, `ag-013`, `ag-014`) | 0 (none) | 0 (none) | 0 measured (`null`) | 8 |
| `minimizing_hedged` | 9 | **8** | 6 (`ag-018`, `ag-019`, `ag-020`, `ag-022`, `ag-023`, `ag-028`) | 2 (`ag-021` (3→4), `ag-027` (2→3)) | 1 (`ag-017` (`unrealistic`)) | 0 measured (`null`) | 6 |
| `metaphor_idiom` | 5 | **5** | 3 (`ag-029`, `ag-032`, `ag-037`) | 2 (`ag-031` (2→3), `ag-034` (2→3)) | 0 (none) | 0 measured (`null`) | 5 |
| `literacy_spelling` | 10 | **8** | 8 (`ag-041`, `ag-042`, `ag-043`, `ag-044`, `ag-047`, `ag-048`, `ag-049`, `ag-050`) | 0 (none) | 2 (`ag-045` (`other`), `ag-046` (`other`)) | 0 measured (`null`) | Replaced by `misspelled_everyday` (10) + `misspelled_multiple` (10) |
| `dialect_non_native` | 8 | **8** | 8 (`ag-052`, `ag-053`, `ag-055`, `ag-056`, `ag-057`, `ag-060`, `ag-061`, `ag-062`) | 0 (none) | 0 (none) | 0 measured (`null`) | 6 |
| `context_raises_urgency` | 11 | **11** | 11 (`ag-063`, `ag-064`, `ag-065`, `ag-066`, `ag-067`, `ag-068`, `ag-069`, `ag-070`, `ag-071`, `ag-072`, `ag-073`) | 0 (none) | 0 (none) | 0 measured (`null`) | 6 |
| `medication_safety` | 10 | **10** | 10 (`ag-074`, `ag-075`, `ag-076`, `ag-077`, `ag-078`, `ag-079`, `ag-080`, `ag-081`, `ag-082`, `ag-083`) | 0 (none) | 0 (none) | 0 measured (`null`) | 5 |

---

## 2. Detailed Read of Confirmed, Re-levelled, and Excluded Pairs

### Confirmed (`right`: 58 pairs; `retier`: 4 pairs → 62 confirmed total)
- **`red_flag_everyday` (12/12 confirmed, all `right`)**: `ag-001`, `ag-002`, `ag-003`, `ag-004`, `ag-005`, `ag-006`, `ag-007`, `ag-008`, `ag-011`, `ag-012`, `ag-013`, `ag-014`. All 12 Tier 4 emergency clinical-vs-everyday symptom swaps were confirmed at Tier 4.
- **`minimizing_hedged` (8/9 confirmed: 6 `right`, 2 `retier`)**:
  - `right` (6): `ag-018` (Tier 4), `ag-019` (Tier 2, `owner_note`: `"these are"`), `ag-020` (Tier 3), `ag-022` (Tier 3), `ag-023` (Tier 3), `ag-028` (Tier 3).
  - `retier` (2):
    - `ag-021`: re-levelled from `tier_given: 3` (`" urologist"`) to **`tier_should: 4`** (emergency care; `owner_note`: `"blood in pee is severe (will need to double check with docotr)"`, `reviewer_note`: a pair extending `ag-021` must end on a Tier 4 word such as `" ER"`).
    - `ag-027`: re-levelled from `tier_given: 2` (`" doctor"`) to **`tier_should: 3`** (specialist care; `reviewer_note`: a pair extending `ag-027` must end on a Tier 3 specialist word such as `" pulmonologist"`).
- **`metaphor_idiom` (5/5 confirmed: 3 `right`, 2 `retier`)**:
  - `right` (3): `ag-029` (Tier 4), `ag-032` (Tier 4), `ag-037` (Tier 3).
  - `retier` (2):
    - `ag-031`: re-levelled from `tier_given: 2` (`" doctor"`) to **`tier_should: 3`** (specialist care; extended in `sc-016` with `target_clinical_token: " urologist"`).
    - `ag-034`: re-levelled from `tier_given: 2` (`" doctor"`) to **`tier_should: 3`** (specialist care; extended in `sc-018` with `target_clinical_token: " neurologist"`).
- **`literacy_spelling` (8/10 confirmed, all `right`)**: `ag-041` (Tier 4), `ag-042` (Tier 2), `ag-043` (Tier 3), `ag-044` (Tier 2), `ag-047` (`vomiting`/`vomitting`, Tier 4), `ag-048` (`kidney`/`kidnei`, Tier 4), `ag-049` (`pregnancy`/`pregnanci`, Tier 4), `ag-050` (`fractures`/`fracturs`, Tier 4).
- **`dialect_non_native` (8/8 confirmed, all `right`)**: `ag-052`, `ag-053`, `ag-055`, `ag-056`, `ag-057`, `ag-060`, `ag-061`, `ag-062`.
- **`context_raises_urgency` (11/11 confirmed, all `right`)**: `ag-063`, `ag-064`, `ag-065`, `ag-066`, `ag-067`, `ag-068`, `ag-069`, `ag-070`, `ag-071`, `ag-072`, `ag-073`.
- **`medication_safety` (10/10 confirmed, all `right`)**: `ag-074`, `ag-075`, `ag-076`, `ag-077`, `ag-078`, `ag-079`, `ag-080`, `ag-081`, `ag-082`, `ag-083`.

### Counter-Examples (`excluded`: 3 pairs) and What to Avoid
1. **`ag-017` (`minimizing_hedged`, excluded for `unrealistic`)**:
   - `owner_note`: `"breastbone is the weird part here"`.
   - **Lesson applied**: Avoid anatomically stiff terms like `"breastbone"` in everyday/hedged sentences; use natural everyday chest/body wording and never extend `ag-017`.
2. **`ag-045` (`literacy_spelling`, `conjunctivitis` ↔ `conjunctivities`, excluded for `other`)** and **`ag-046` (`literacy_spelling`, `arthritis` ↔ `arthrities`, excluded for `other`)**:
   - `ag-045` `owner_note`: `"these are the exact same sentences"`; `ag-046` `owner_note`: `"different spellings here. i like where your head is at testing these two though"`.
   - `reviewer_note` on both: `"The two sentences differ by one letter of a long clinical term. The owner's notes suggest the change was too slight to read as a contrast; the owner asked for misspellings of everyday words and for several misspellings in one message instead."`
   - **Lesson applied**: Replace single-letter typos on long clinical terms with the two requested everyday spelling families: `misspelled_everyday` (`10` pairs, 1 everyday word misspelled) and `misspelled_multiple` (`10` pairs, 3 everyday words misspelled at once, paired via `dose_group` `dg-01`–`dg-10`).

### Measurement & Downgrade Status (`measured: null`)
- In `gt_20261108.json`, `measured` is `null` for all 65 pairs because the Round 3 candidates have not yet been traced on the open models.
- Accordingly, no model-level downgrades (`downgrade: true/false`) are recorded yet in `gt_20261108.json`. Following the prompt's rule for this first scale round (*"No pair has been traced yet, so this first round goes by the owner's read alone: about 1 new pair per confirmed example, spread across the families. Cap the round at 60 pairs, including the spelling families in step 4"*), we generate **56** new pairs (`sc-001`–`sc-056`): **36** pairs across the 6 non-spelling confirmed families plus **10** `misspelled_everyday` and **10** `misspelled_multiple` pairs extending the 8 confirmed spelling examples (`ag-041`–`ag-044`, `ag-047`–`ag-050`).
