# Comma test on 18 hand-authored pairs: analysis plan (exploratory)

Written 2026-11-09, before any trace of `data/simulated/agscen_commas_20261109.json` exists. The owner asked whether
commas matter after excluding 18 scale-round pairs for "perfect comma grammar" alongside misspellings ("I feel like
people are more likely to not have commas at all in terms of how they type").

## Stimuli

`data/simulated/agscen_commas_20261109.json`: the 18 owner-excluded scale-round pairs
(`drafts/antigravity_scenarios_20261107/scale_20261108/candidates_v2.json` at `765459e3`), each twice.

- `<id>-comma`: as written. Every pair has 3 commas on each side.
- `<id>-nocomma`: every comma deleted, nothing else changed. The builder asserts the same words in the same order.

The round-5 rewrites (`data/simulated/agscen_r5_20261108.json`, `<id>-r5`, already traced) removed the commas and
also replaced one of them with "and" or "with"; sc-029-r5 also changed "eighty-one" to "81" and "outward-turned leg"
to "leg turned out". So `-comma` against `-r5` mixes punctuation and wording, which is why this file exists.

## Measures

Seven models, as for the earlier agscen rounds: hosted gemma-2-2b (2panel traces) and six logits models
(gemma-3-4b-it, qwen3-1.7b, qwen3-4b, llama-3.2-3b, olmo-2-1b, gemma-2-2b-it). Per pair and model:

- `penalty`: the engine's `language_penalty`, the clinical target's probability on the everyday side minus on the
  clinical side;
- `p_clinical`: the clinical target's probability on the clinical side;
- `class`: downgrade, upgrade, lateral or uninformative, by the tier rules in the agscen measured files
  (`data/urgency_tiers.draft.json`).

A model's row counts only when both variants of the pair have a numeric value for that measure.

## Units: 13 clinical sentences, not 18 pairs

Five dose groups share one clinical sentence and target between two pairs (one and three misspellings on the
everyday side): sc-039/sc-049, sc-040/sc-050, sc-042/sc-052, sc-043/sc-053 and sc-044/sc-054. Their clinical-side
measurements are the same prompt measured twice, so the two pairs of a group are not independent. Every test below
therefore uses one unit per distinct (clinical sentence, target): 13 units. A unit's value is the mean of its pairs'
values (one pair for 8 units, two for 5).

## Contrasts

1. **Commas (primary).** For each pair, the mean over models of penalty(comma) − penalty(nocomma); then the unit
   mean. Two-sided exact sign test over the 13 units; ties (a mean of exactly 0) are dropped and counted. The 18
   pair values are also reported, without a test.
2. **Commas on the clinical baseline.** p_clinical(comma) − p_clinical(nocomma), once per unit (the clinical prompt
   is identical within a group), with the same sign test over the 13 units.
3. **Commas on the class.** Pairs and model rows that downgrade, comma against nocomma. Descriptive only.
4. **Connective wording (secondary).** Contrasts 1 and 3 for `-nocomma` against `-r5`, on the 13 pairs whose
   rewrite differs from the comma-free original only in connectives: an "and" or "with" where a comma stood,
   and in sc-035, sc-039 and sc-049 also the final "and" changed to "with". Five pairs are left
   out of the test and reported on their own, because their rewrite also changed hyphens: sc-029 ("eighty-one" to
   "81", "outward-turned leg" to "leg turned out"), sc-040 and sc-050 ("full-body" to "full body"), and sc-042 and
   sc-052 ("blood-streaked" to "blood streaked"). The 13 kept pairs form 10 units (sc-039/sc-049, sc-043/sc-053 and
   sc-044/sc-054 share a clinical sentence); the sign test runs over those 10. Sensitivity: the same test without
   sc-035, sc-039 and sc-049, whose rewrites also change an existing "and" to "with" (10 pairs, 8 units), so that
   what remains is only a connective inserted where a comma stood.

No correction across contrasts; nothing here is confirmatory. The wording for a null result is "no difference was
detected on these 13 clinical sentences", not "commas have no effect". One sample per pair and model; small models
only.

Amended 2026-11-09, still before any trace, after review (engine #158): units by shared clinical sentence, and the
four further hyphen-changing rewrites left out of contrast 4.

## Reproduce

The comparison script is written after the traces land and committed with the results; it reads only
`trace_out/agscen_commas_20261109*/` and `trace_out/agscen_r5_20261108*/`. These parts are exploratory and
publication_hold refuses them by stem.
