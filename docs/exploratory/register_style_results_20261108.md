# Style-vs-vocabulary sub-study: results (exploratory)

Registered in `docs/preregistration_advice_register_style.md` (signed 2026-11-08). Files A
(`stimuli_20261108T014809Z`) and B (`stimuli_20261108T014810Z`), seven models, K = 1, elicited 2026-11-08 UTC.
Judge of record `claude-haiku-4-5`; second judge `anthropic:claude-haiku-5-5`. Deviations and analysis choices were
written before any contrast was computed and are recorded in `docs/prereg_divergence_log.md` (2026-11-08 entry).

Reproduce: `python scripts/register_style_analysis.py` (reads only committed archives under `data/advice/`;
`--out <file>` writes every number below as JSON).

Positive differences mean the first-named wording got the *more* urgent advice (tier order self-care < routine <
urgent < emergency).

## Registered result

All 56 situations joined one to one across the files; 7 models measured. Units missing for an
unparsed judge tier: 9 (vocabulary), 16 (style).

| Contrast | Situations up | down | tied | p | p (Holm) | mean unit difference |
|---|---:|---:|---:|---:|---:|---:|
| 1. Style: D(colloquial, careful lay) | 20 | 10 | 26 | 0.099 | 0.296 | +0.035 |
| 2. Vocabulary: D(careful lay, clinical) | 12 | 14 | 30 | 0.845 | 0.845 | +0.010 |
| 3. Style minus vocabulary | 18 | 11 | 27 | 0.265 | 0.530 | +0.027 |

No pooled test is significant after Holm (α = 0.05). The prereg's statement for this outcome is: **"No difference
in recommended urgency was detected between these wordings."** It is not "the wording has no effect", and the null
vocabulary test does not license "medical terms had no effect".

## Sensitivity analyses

**1. Second judge.** Under the second judge the two arms of a file differ in 20.4% (A) and 20.1% (B) of units.

| Contrast | Situations up | down | tied | p | p (Holm) | mean unit difference |
|---|---:|---:|---:|---:|---:|---:|
| 1. Style: D(colloquial, careful lay) | 21 | 15 | 20 | 0.405 | 1.000 | +0.021 |
| 2. Vocabulary: D(careful lay, clinical) | 13 | 15 | 28 | 0.851 | 1.000 | +0.016 |
| 3. Style minus vocabulary | 21 | 15 | 20 | 0.405 | 1.000 | +0.008 |

**2. Each model alone** (exact sign test over situations; up/down/tied, p; not corrected for multiplicity). One of
the 21 tests has p below 0.05 (GPT-5.5, style: 8 situations more urgent, 1 less); with 21 tests, one such result is
what chance alone would often give.

| Model | Style | Vocabulary | Style minus vocabulary |
|---|---|---|---|
| claude-haiku-4-5 | 2/5/49, p 0.453 | 2/3/51, p 1.000 | 5/5/46, p 1.000 |
| claude-sonnet-5 | 7/4/45, p 0.549 | 4/3/49, p 1.000 | 8/6/42, p 0.791 |
| deepseek/deepseek-v4-flash | 7/5/36, p 0.774 | 7/4/42, p 0.549 | 8/9/31, p 1.000 |
| moonshotai/kimi-k2.5 | 8/5/36, p 0.581 | 5/8/37, p 0.581 | 10/6/33, p 0.454 |
| openai/gpt-5.4-mini | 8/5/43, p 0.581 | 6/4/46, p 0.754 | 9/7/40, p 0.804 |
| openai/gpt-5.5 | 8/1/47, p 0.039 | 3/0/53, p 0.250 | 8/3/45, p 0.227 |
| x-ai/grok-4.3 | 6/5/44, p 1.000 | 4/6/46, p 0.754 | 6/6/43, p 1.000 |

**3. Clinical test-retest.** The identical clinical message was answered once in each file. Of 382 model ×
situation pairs, 87.4% got the same tier (linear-weighted κ 0.81, quadratic 0.84);
file A's reply was higher in 28 and file B's in 20. Within a file, the two arms got different tiers in
15.4% (A) and 16.7% (B) of units, so at K = 1 most arm differences are of the same size as resampling noise.

**4. Situations flagged in review but kept.** None: no file-B rewrite carries a `rewrite_checks` flag, so this
analysis equals the registered one.

## Added analysis (not registered): truncated and empty replies removed

Every unit involving a reply stopped for length or empty was dropped (97 file-A and 87 file-B unit removals,
174 of the 184 from DeepSeek V4 Flash and Kimi K2.5; the rest Claude Sonnet 5 7, GPT-5.5 2, Grok 4.3 1).

| Contrast | Situations up | down | tied | p | p (Holm) | mean unit difference |
|---|---:|---:|---:|---:|---:|---:|
| 1. Style: D(colloquial, careful lay) | 16 | 8 | 32 | 0.152 | 0.455 | +0.029 |
| 2. Vocabulary: D(careful lay, clinical) | 11 | 10 | 35 | 1.000 | 1.000 | +0.014 |
| 3. Style minus vocabulary | 14 | 9 | 33 | 0.405 | 0.810 | +0.018 |

## Limits

- K = 1 per cell; the test-retest disagreement shows how much one resample moves a tier.
- Claude Haiku 4.5 and Claude Sonnet 5 were sampled at the API default temperature (divergence log item 1).
- DeepSeek V4 Flash and Kimi K2.5 often hit the 1024-token limit; the added analysis above removes those units.
- 56 situations from one generated source; exploratory relative to the advice arm's registered endpoints.
