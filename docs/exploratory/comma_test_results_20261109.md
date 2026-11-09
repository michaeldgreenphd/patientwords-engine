# Comma test on 18 hand-authored pairs: results (exploratory)

Plan: `docs/exploratory/comma_test_plan_20261109.md`, fixed before any trace (engine #158). Stimuli:
`data/simulated/agscen_commas_20261109.json`. Traces: hosted gemma-2-2b (runs 42633307499 and 42658888179) and six
logits models (run 42633312846). Run 42633307499 failed at index 27 on a Neuronpedia "Server busy" error, so the
two lost pairs (sc-049 with and without commas) were re-run alone as `part_27`; nothing landed was overwritten.
All 36 pairs are measured on all 7 models.

Reproduce: `python scripts/comma_test_analysis.py [--out results.json]`. It reads only the committed trace parts.
`tests/test_comma_test_analysis.py` pins every number below.

`penalty` is the clinical target's probability on the everyday side minus on the clinical side. It is usually
negative; a positive difference below means a smaller gap.

## Result

No difference was detected on these 13 clinical sentences.

| Contrast | Units | Up | Down | p (exact sign test) | Mean unit difference |
|---|---:|---:|---:|---:|---:|
| 1. Commas: penalty(comma) − penalty(nocomma) | 13 | 10 | 3 | 0.092 | +0.010 |
| 2. Clinical baseline: p_clinical(comma) − p_clinical(nocomma) | 13 | 8 | 5 | 0.581 | +0.004 |
| 4. Connective: penalty(nocomma) − penalty(r5) | 10 | 6 | 4 | 0.754 | +0.007 |
| 4, sensitivity: inserted connective only | 8 | 4 | 4 | 1.000 | +0.004 |

Contrast 3 (descriptive): downgrading pairs, 5 of 18 with commas and 5 of 18 without. Downgrading model rows, 10 of
125 with commas and 6 of 124 without, with 0 and 1 upgrades.

## Reading

- The differences are about one percentage point of the target's probability. The penalties these pairs carry are
  usually several points or more.
- The two measures point in opposite directions. Contrast 1 leans towards a slightly smaller gap with commas; the
  downgrade counts lean towards more downgrades with commas. Neither is significant. Neither supports the claim that
  removing commas changes what these models do.
- The connective added in the round-5 rewrites ("and", "with") also shows no difference.
- For comparisons across rounds, this suggests the comma-free rewrites in round 5 can be read alongside the comma
  pairs of earlier rounds. It does not show that punctuation never matters: 13 sentences, one sample each, seven
  small models.

The five rewrites left out of contrast 4 because they also changed hyphens, reported alone (penalty(nocomma) −
penalty(r5), mean over models): sc-029 +0.020, sc-040 +0.010, sc-042 +0.028, sc-050 −0.020, sc-052 +0.023.
