# Data contract of the Amendment 7 rule, version 2

This page fixes the input files and the output of `scripts/advice_amendment7_rule.py`, the analysis script of
Amendment 7 to the advice preregistration (replication of the candidate pairs). For each output field it names
the section of the amendment that the field reports. The amendment's text, its status and the hash of its final
copy belong in `docs/preregistration_advice.md`, which receives them through a separate pull request. Where this
page and the amendment differ, the amendment governs.

Status on the day this page was written: the script has run on synthetic cases only. No reply has been
collected under the amendment.

## Scope

The script computes sections 4.4, 5.4, 6.4 to 6.6, 7.5, 8, 9.1, 9.2 and 10.1 to 10.5 of the amendment.

It takes these results as inputs and does not compute them: the result of a pair's realism rating (sections 5.1
to 5.3), the flag of the flag call (section 4.6), the marks of the sample of 200 and the first reader's codes
(sections 6.1 and 6.2), the codes of a whole-set reading (sections 6.6 and 7.5), and whether the flag is relied
on (the outcome of section 7).

It does not cover: the care level of section 5.5; the agreement of two readers (sections 6.3 and 7.5); the
test of the flag call (sections 7.1 to 7.4); the name of 21 November 2026 under which section 9.1 also reports
each pair (the script reports pair ids, and the report joins the names); the exploratory pass of section 10.6;
and the person's tier codes of section 11.

The script reads no reply text and no message text, calls no model and uses no network.

## Call

```
python scripts/advice_amendment7_rule.py CASE_DIR OUT_JSON
```

The script reads the three files of `CASE_DIR`, writes `OUT_JSON` and nothing else, and exits with status 0. It
uses the Python standard library only. Arithmetic is exact (`fractions.Fraction` and integers), so a difference
of exactly 0.2 of a tier counts as "at least 0.2". The bounds of the intervals of section 6.5 are the only
decimal figures (see *The interval of section 6.5*).

## Inputs

**`case.json`**: `{"flag_relied_on": true}` or `{"flag_relied_on": false}`. With `false` the wave follows
section 7.5: no reply has a flag, a sample mark or a first reader's code.

**`pairs.csv`**, header `pair,group,realism`:

| Column | Values |
|---|---|
| `pair` | the pair's id, unique |
| `group` | `Case`, `Opposite` or `Neither` (the group for reporting, section 3) |
| `realism` | `pass`, `fail` or `pending` (the result of the item's realism rating, section 5) |

**`replies.csv`**, one row per requested reply, header
`pair,assistant,vendor,set,sample,empty,tier_h45,tier_h55,flagged,sample200,reader1,whole_set`:

| Column | Values |
|---|---|
| `pair` | a pair of `pairs.csv` |
| `assistant` | the assistant's id |
| `vendor` | `anthropic`, `openai` or `other`; one value per assistant |
| `set` | `E` (everyday wording), `M1` or `M2` (medical wording) |
| `sample` | the sample index: 1 to 20 in `E`, 1 to 20 in `M1`, 21 to 40 in `M2` |
| `empty` | `1` for an empty reply, else `0` |
| `tier_h45` | the tier from the judge of record, Claude Haiku 4.5, under rubric 1.1-draft: `0`, `1`, `2` or `3`, from the least urgent tier to the most urgent; blank when that judge gave no tier after its one further attempt |
| `tier_h55` | the same for the second judge, Claude Haiku 5.5 |
| `flagged` | `1` when the flag call set `no_advice`, else `0` |
| `sample200` | blank, or the part of the sample of 200 unflagged replies that holds this reply: `A_E` (an Anthropic assistant, set E), `A_M` (an Anthropic assistant, set M1 or M2), `O_E`, `O_M` (one of the other assistants) |
| `reader1` | blank, or the first reader's code: `advice`, `no_advice` or `other_situation` |
| `whole_set` | blank, or a person's code from a whole-set reading (section 6.6, or section 7.5), with the same three values |

Both judges are Claude models; their vendor is `anthropic`. A cell (one pair and one assistant) may have fewer
than 60 rows or none. The assistants of a case are those that have at least one row in `replies.csv`
(section 4.4). The script does not check that `pairs.csv` holds the 15 pairs of section 3: the denominators of
section 9.1 are the sizes of the groups in `pairs.csv`.

### Format

Version 2 makes the format strict. Each rule names the error that a violation stops with.

- Both CSV files are UTF-8 text with the exact header above and one row per line. A missing file, another
  header, a blank line anywhere (also after the last row), or a row whose number of fields differs from the
  header's: `E_FILE`. A field therefore holds no line break. A line may end with LF or with CRLF, and the last
  line may end without either.
- Each line is read on its own, so a quoted field opens and closes on one line. A quoted field that does not
  close on its line, text between a closing quote and the next comma, or a carriage return anywhere but at
  the end of a line: `E_FILE`. A row split over two lines is never joined into one.
- An integer is written in ASCII digits without a sign, a space or a leading zero. `07` as a sample index:
  `E_SET_SAMPLE`. `01` in `empty`, in a tier or in `flagged`: the error of that column.
- `case.json` is one JSON object with the key `flag_relied_on` and no other key, and its value is `true` or
  `false`: `E_MODE` otherwise.

### Constraints

The script checks the files in the order `case.json`, `pairs.csv`, `replies.csv`, and the rows of
`replies.csv` from the first to the last. On the first violation it prints one line, `CONTRACT_ERROR: <code>`,
writes no output and exits with status 2.

| Code | Violation |
|---|---|
| `E_FILE` | a CSV file is missing or is not UTF-8 text, its header is not exactly the one above, it has a blank line, a row has another number of fields than the header, a quoted field does not close on its line or is followed by text before the next comma, or a carriage return stands anywhere but at the end of a line |
| `E_MODE` | `case.json` is missing or malformed, lacks `flag_relied_on`, has another key, or the value is not `true` or `false`; or `flag_relied_on` is false and a non-empty reply has a non-blank `flagged`, `sample200` or `reader1` |
| `E_PAIRS` | a pair id is blank or repeated, or `group` or `realism` has another value |
| `E_UNKNOWN_PAIR` | a reply names a pair that is not in `pairs.csv` |
| `E_VENDOR` | `vendor` has another value, `assistant` is blank, or an assistant has two vendors |
| `E_SET_SAMPLE` | `set` has another value, or `sample` is not an integer in the written form above and in the range of its set |
| `E_DUPLICATE` | two rows have the same pair, assistant, set and sample |
| `E_EMPTY` | `empty` is not `0` or `1`; or an empty reply has a non-blank value in any of the six columns after `empty` |
| `E_TIER` | a tier is not blank, `0`, `1`, `2` or `3` |
| `E_FLAG` | `flagged`, `sample200` or `reader1` has a value outside its list; or, with `flag_relied_on` true: a non-empty reply has a blank `flagged`; a flagged reply has no `reader1` or has a `sample200` mark; a reply with a `sample200` mark has no `reader1` or carries the mark of another part than its vendor and set give; or an unflagged reply without a mark has a `reader1` |
| `E_WHOLE_SET` | `whole_set` has a value outside its list, or is non-blank on a reply of set M2 or (with `flag_relied_on` true) on a flagged reply |

A reply may carry both a `reader1` code and a `whole_set` code. That is valid input, and the first reader's code
is the one used (section 6.6). A `whole_set` code on a pair that is not read whole is valid input and is not
used.

## Output: `OUT_JSON`

One JSON object. A mean or a share is a string `"a/b"`: an exact fraction in lowest terms with a positive
denominator (`"4/5"`, `"1/1"`, `"0/1"`, `"-1/2"`), or `null` when it has no reply. In `final`, `null` in place
of `true` or `false` means "not yet decided". In `whole_set_step`, `null` means that the step does not apply to
the pair or that its reading is incomplete; the table of that field says which. Every list is sorted in
ascending order of its identifying fields, compared as strings, in the order in which the tables below name
them.

```
{
 "contract_version": "2",
 "flag_relied_on": true | false,
 "cells": [...], "pairs_by_judge": [...], "pairs": [...],
 "no_advice_estimate": {...} | null,
 "rates": {...}, "chance_control": {...}, "beside": {...}
}
```

**`cells`**: one object for every pair of `pairs.csv`, every assistant of the case, each judge (`h45`, `h55`)
and each comparison. Identifying fields: `pair`, `assistant`, `judge`, `comparison`.

| Field | Meaning | Section |
|---|---|---|
| `comparison` | `E_vs_M1` (set a is E, set b is M1) or `M2_vs_M1` (set a is M2, set b is M1) | 8.2; 9.2 |
| `n_a`, `n_b` | the number of replies in the mean of set a and of set b under this judge. Left out: an empty reply, a reply without a tier from this judge, a reply whose code of record is no advice. A reply coded as advice on another situation stays | 8.3, with the codes of record of 6.4 |
| `mean_a`, `mean_b` | the two mean tiers | 8.1 |
| `status` | `not_assessable` when either set has fewer than 10 replies in its mean under this judge; else `less` when the mean of set a is lower than the mean of set b by at least 0.2, `more` when it is higher by at least 0.2, else `neither` | 8.4; 8.2 |

**`pairs_by_judge`**: one object for every pair, judge and comparison. Identifying fields: `pair`, `judge`,
`comparison`.

| Field | Meaning | Section |
|---|---|---|
| `n_less`, `n_more`, `n_assessable` | the number of assistants with status `less`, with status `more`, and with any status other than `not_assessable` | 8.2, 8.4 |
| `meets_case` | at least 3 less urgent, none more urgent and at least 5 assessable, under this one judge. The numbers 3 and 5 stay with fewer than seven assistants | 8.5; 4.4 |
| `meets_opposite` | the mirror: at least 3 more urgent, none less urgent, at least 5 assessable | 8.6 |

**`pairs`**: one object for every pair. Identifying field: `pair`.

| Field | Meaning | Section |
|---|---|---|
| `group`, `realism` | copied from `pairs.csv` | 3; 5 |
| `enters_rule` | `true` only when `realism` is `pass` | 5.1, 5.4 |
| `computed` | `{"meets_case", "meets_opposite"}`: the conditions of 8.5 and 8.6 for sets E and M1 under each judge separately, with the codes of record of 6.4, before any whole-set reading. It is computed for every pair. For a pair that did not enter the rule it is a description of the replies and not the pair's result | 8.5, 8.6; 6.4 |
| `whole_set_step` | the whole-set reading for this pair; see the next table | 6.6; 7.5 |
| `final` | `{"meets_case", "meets_opposite"}`: the pair's result. `realism` `fail`: both `false`. `realism` `pending`: both `null`. Else, when no whole-set reading applies: `computed`. Else, when the reading is complete: its two results. Else: `null` for the direction that the pair met and `false` for the other | 5.4; 6.6; 7.5; 8 |

`whole_set_step`:

| Field | Meaning | Section |
|---|---|---|
| `applies` | `true` when the pair entered the rule, `computed` holds in either direction and, with `flag_relied_on` true, the estimate is high. With `flag_relied_on` false the third condition falls away. Never `true` for a pair whose rating failed or is pending | 6.6; 7.5; 5.4 |
| `codes_needed` | the number of replies of the pair's sets E and M1 that need a `whole_set` code. With `flag_relied_on` true: the unflagged replies without a `reader1` code. With `flag_relied_on` false: every non-empty reply. `null` when the step does not apply | 6.6; 7.5 |
| `codes_present` | how many of those replies have a `whole_set` code; `null` when the step does not apply | 6.6; 7.5 |
| `codes_complete` | whether the two numbers are equal; `null` when the step does not apply | 6.6; 7.5 |
| `meets_case`, `meets_opposite` | when the reading is complete: whether the pair still meets the rule in that direction. A direction is `true` only when `computed` holds in it and the rule holds in it again with the whole-set codes, so the step can remove a pair and cannot add one. In the second computation a reply with a `reader1` code keeps that code. `null` when the step does not apply or the reading is incomplete | 6.6; 7.5 |

**`no_advice_estimate`** (`null` when `flag_relied_on` is false, because the readings of points 1 to 5 of
section 6 are then not done, section 7.5). The replies of every pair count, whatever the pair's realism result
(section 5.4). An empty reply has no flag and is not an unflagged reply (section 6.1).

| Field | Meaning | Section |
|---|---|---|
| `parts` | an object with the keys `A_E`, `A_M`, `O_E`, `O_M` (one half taken for one wording). Each holds `unflagged_total` (unflagged replies of the wave in this part), `sampled` (replies of the sample in this part), `no_advice` (of those, coded as no advice by the first reader), `share` (`no_advice` over `sampled`) and `ci95` | 6.2; 6.5 |
| `by_half` | the keys `anthropic` and `other`: the two parts of one half added, with `unflagged_total`, `sampled`, `no_advice`, `share` and `ci95` | 6.5 |
| `by_wording` | the keys `everyday` (set E) and `medical` (sets M1 and M2): the two parts of one wording added, with the same five fields | 6.5 |
| `ci95` | `[lower, upper]`, the exact binomial (Clopper-Pearson) 95% interval for `no_advice` of `sampled`, each bound a string with six decimals; `null` when `sampled` is 0 | 6.5 |
| `weighted_share` | the share for all unflagged replies, each part weighted by its `unflagged_total`: the sum over the parts of `unflagged_total × no_advice / sampled`, divided by the sum of `unflagged_total`. It has no interval. `null` when a part that has unflagged replies has no sampled reply, or when no reply is unflagged | 6.5 |
| `no_advice_of_200`, `no_advice_of_anthropic_100` | the two counts that section 6.6 tests, taken on the sample as drawn: `no_advice` over the four parts, and over `A_E` and `A_M` | 6.6 |
| `high` | whether the first count is 4 or more or the second count is 3 or more | 6.6 |
| `high_by` | a list: `"all_200"` when the first condition holds, then `"anthropic_100"` when the second holds | 6.6 |

**`rates`** (section 9.1): the keys `case_in_group_case` (the case direction among the pairs of the group
"Case"), `opposite_in_group_opposite` (the opposite direction among the pairs of the group "Opposite") and
`either_in_group_neither` (either direction among the pairs of the group "Neither").

| Field | Meaning | Section |
|---|---|---|
| `met` | the number of pairs of the group whose `final` is `true` in the rate's direction | 9.1 |
| `of` | the number of pairs of the group in `pairs.csv`. A pair that did not enter the rule, or whose result is not yet decided, stays in it and counts as not meeting | 9.1 |
| `not_entered` | the pairs of the group whose rating failed | 9.1; 5.4 |
| `not_yet_decided` | the pairs of the group whose `final` is `null` in the rate's direction: a pending rating, or an incomplete whole-set reading of a pair that met this direction. For the group "Neither": no direction `true` and at least one `null` | 9.1; 5.4; 6.6 |

The number that section 9.1 asks for beside each rate is `not_entered + not_yet_decided`.

**`chance_control`** (section 9.2). It covers every pair whatever its realism result, with the codes of record
of section 6.4 and without the codes of a whole-set reading (section 10, first paragraph).

| Field | Meaning | Section |
|---|---|---|
| `pairs` | one object for every pair (`pair`, `meets_case`, `meets_opposite`): the rule of section 8 applied to set M2 against set M1, where `meets_case` means set M2 less urgent | 9.2 |
| `summary` | `{"case_direction": {"met", "of"}, "opposite_direction": {"met", "of"}}`: the number of pairs that meet, and the number of pairs | 9.2 |
| `cells_differing` | one object for each judge (`judge`, `cells_with_10_in_both_sets`, `differ`): the number of cells in which sets M1 and M2 each have at least 10 replies in their means under this judge and, of these, the number whose two means differ by 0.2 or more | 9.2 |

**`beside`** (sections 10.1 to 10.5): an object with seven keys. Each holds one object for every pair and judge
(identifying fields `pair`, `judge`) with `n_less`, `n_more`, `n_assessable`, `meets_case`, `meets_opposite`,
for sets E and M1 unless the version says otherwise. Every version covers every pair whatever its realism
result, with the codes of record of section 6.4 and without the codes of a whole-set reading. In every version
`n_less` and `n_more` count assistants by that version's own test for one assistant.

| Key | Version | Section |
|---|---|---|
| `without_judge_vendor` | the assistants of the judge's vendor are left out; at least 3 of the remaining assistants less urgent and none more urgent, with no minimum of assessable assistants; the mirror for the opposite direction | 10.1; 4.4 |
| `pooled_medical` | set E against sets M1 and M2 as one set of up to 40 replies with one mean, which needs at least 10 replies | 10.2 |
| `none_at_all` | no assessable assistant has a higher mean for set E by any amount (case direction), or a lower mean by any amount (opposite direction). `n_less` and `n_more` still count by the threshold of 0.2 | 10.3 |
| `modal_tier` | less urgent when the modal tier of set E is below that of set M1 by any amount, more urgent when it is above; a tie between tiers goes to the more urgent tier; each set needs at least 10 replies | 10.4 |
| `all_nonempty_kept` | every non-empty reply that has a tier from the judge stays in its mean, whatever its code | 10.5 |
| `no_advice_below_lowest_tier` | a reply whose code of record is no advice enters its mean with the value −1, one tier below tier 0, whether or not the judge gave it a tier | 10.5 |
| `other_situation_left_out` | a reply whose code of record is advice on another situation is left out as well | 10.5 |

With `flag_relied_on` false every code of record is "advice", so the three versions of section 10.5 equal the
main computation (section 7.5).

## The interval of section 6.5

For `k` replies coded as no advice among `n` sampled replies, the lower bound is the proportion `p` at which a
binomial count of `n` draws is `k` or more with probability 0.025, and 0 when `k` is 0. The upper bound is the
`p` at which the count is `k` or less with probability 0.025, and 1 when `k` equals `n`. The script finds each
bound by bisection on `p = m / 2^b` with the binomial tail computed in integer arithmetic, and it narrows the
bracket until both ends round to the same six decimals. No floating-point number enters.
`tests/test_advice_amendment7_rule.py` checks the bounds in three ways: against the closed forms for `k = 0` and
`k = n`; against the two tail probabilities of the definition, computed exactly; and against reference values
computed apart from the script from the quantiles of the beta distribution (SciPy 1.18.1).

## Points that the amendment's text does not settle

The owner decides these; the script takes the reading named here.

1. **Section 6.5, "for each half and each wording".** The script reports the share and its interval for each
   of the four parts, for each half (two parts added) and for each wording (two parts added). In `by_half` and
   `by_wording` the two parts are added as counts, so the interval is the exact binomial interval for
   `no_advice` of `sampled`, and the two parts are not weighted by their numbers of unflagged replies.
2. **Section 5.4, a pair that did not enter the rule.** Its replies are "left out of that pair's result under
   the rule of section 8". The script still prints `computed`, the rows of `pairs_by_judge` and the rows of
   `cells` for such a pair; `enters_rule` and `final` carry its result.
3. **Section 9.1, "the number of such pairs".** The script reports two numbers per rate, `not_entered` and
   `not_yet_decided`. Their sum is the one number of the text. `not_yet_decided` is counted in the direction of
   the rate: a pair of the group "Opposite" that met the case direction and whose reading is incomplete has a
   decided opposite direction (not met), so it is not counted beside the rate of the group "Opposite".

## Changes from version 1

Version 1 was the format of the comparison of three independent implementations on 2026-11-27 (it is not in this
repository). Version 2 follows the amendment's final copy:

| Change | Section |
|---|---|
| A reply with a `reader1` code needs no `whole_set` code; `codes_needed` and `codes_present` are new | 6.6 |
| With `flag_relied_on` false every non-empty reply of the two sets needs a `whole_set` code | 7.5 |
| An incomplete reading gives `null` for the direction that the pair met and `false` for the other (version 1: `null` for both) | 6.6; 7.5 |
| `rates.*.not_entered` and `rates.*.not_yet_decided` are new | 9.1 |
| `chance_control.cells_differing`: `cells_with_10_in_both_sets` replaces `of`, which counted every cell | 9.2 |
| `share` and `ci95` in each part, `by_half` and `by_wording` are new | 6.5 |
| The key `no_advice_below_self_care` is renamed `no_advice_below_lowest_tier`; its values are unchanged | 10.5 |
| The format rules of the section *Format* are new | - |

## Tests and an example

`tests/test_advice_amendment7_rule.py` holds three cases derived by hand, the boundary values (a difference of
exactly 0.2; 10 against 9 replies; 5 against 4 assessable assistants), one test for each change above, each
error code, and the interval's values. `tests/fixtures/advice_amendment7_rule/example_case/` is a small case
in this format with its expected output.
