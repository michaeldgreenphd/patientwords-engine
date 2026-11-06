# Does the urgency drop under everyday wording depend on the judge? — 2026-11-06 (exploratory)

Owner decision on the decision page, 2026-11-06 (ag-offline-first: "Judge register-bias sensitivity"). The question
came from an Antigravity review: the advice judge grades the assistant's reply, and a reply to a colloquial patient
reads warmer and less clinical. If the judge rates that prose as less urgent, part of the measured urgency drop is
grading, not advice.

This is a sensitivity analysis, outside every registered claim. It spends nothing: every judgment it reads already
landed on `main`. Reproduce it with:

```
python scripts/judge_register_sensitivity.py --out /tmp/judge_register_sensitivity.json
```

## Answers first

1. **Wave 2's urgency drop does not depend on the judge.** Re-graded by two other judges, an OpenAI model and a newer
   Claude model, the registered primary contrast keeps its direction and its significance. Each judge selects the
   same wording row of the design note's table (row 1).
2. **None of the three judges separates writing style from medical terms.** Style lowers urgency under every judge.
   Vocabulary alone does not reach significance under any. But the registered test of style *against* vocabulary is
   not significant after Holm under any judge, so the design note's statement stays "could not separate", and nothing
   here says the terms had no effect.
3. **In single-turn advice, nothing shows the judge grading replies to patient wording lower than replies to clinical
   wording.** Against the Jev classifier, the judge reads slightly lower than Jev in every arm, and no lower on the
   patient arm (+0.06 tier steps) than on the clinical arm (+0.07). Against the owner's 25 blinded codings, the judge
   reads slightly lower in every arm too; with 8–9 responses per arm that can only detect large biases.
4. **What this does not rule out: a bias all the model judges share.** Haiku 4.5, Haiku 5.5 and GPT-5.4 mini are
   language models, and Jev (`typesafe/jev-1.13`) is a model-based classifier. The only non-LLM reference is the 25 human codings. A clinician-coded
   sample stratified by arm would close this gap; the coding page (`llm/code.html`) already supports more coders.

## 1. Wave 2 under three judges

Wave 2's target is Claude Haiku 4.5 in all four runs, and so is the judge of record: on these runs the judge grades
its own model's replies. The two re-grades are the first check of the result by a judge from outside that model.

The script copies each wave-2 run (`data/petri/w2_register_contrast.json` `run_list`) into a scratch directory, puts
one judge's `judgments.jsonl` and `analysis_rows.jsonl` in place of the judge of record's, and calls the registered
script's own `prepare` and `final_analysis`. The triples, comparability rules, tests and wording selection are
therefore the registered ones.
- **Verification.** Each file is checked by its own verifier first: the source run by `verify_run`, the re-grade by
  `rejudge.verify_output`. Only then is the source-digest check skipped for the copies.
- **Control.** The judge of record goes through the same harness and reproduces the committed result exactly
  (`wave2_control_reproduces_committed: true`, pinned by `tests/test_judge_register_sensitivity.py`).

Primary contrast, D(colloquial, clinical), exact two-sided sign test; "27–6, 2 tied" means 27 triples where
colloquial got less urgent advice, 6 where it got more.

| Judge | Triples | Primary | Scenario gate (8 scenarios) | Wording row |
|---|---|---|---|---|
| Claude Haiku 4.5 (judge of record) | 35 | 27–6, 2 tied, p = 0.0003 | p = 0.016, negative | row 1 |
| GPT-5.4 mini (OpenRouter) | 35 | 25–5, 5 tied, p = 0.0003 | p = 0.008, negative | row 1 |
| Claude Haiku 5.5 (OpenRouter) | 33 | 23–9, 1 tied, p = 0.020 | p = 0.023, negative | row 1 |

Haiku 5.5's pass on `run_36076994201_1` stopped at its budget allotment (1,424 of 1,590 judgments;
`docs/exploratory/xjudge_20261031.md`). The registered comparability rules drop the two triples it left short, so it
has 33.

Sensitivity analyses of the primary contrast (section 10.4):

| Analysis | Haiku 4.5 | GPT-5.4 mini | Haiku 5.5 |
|---|---|---|---|
| Without clinician-speaker triples | 21–5, p = 0.002 | 21–3, p = 0.0003 | 21–5, p = 0.002 |
| Original set alone | 14–4, p = 0.031 | 12–4, p = 0.077 | 10–7, p = 0.63 |
| Second set alone | 13–2, p = 0.007 | 13–1, p = 0.002 | 13–2, p = 0.007 |
| Exchange 1 only | 9–3, 23 tied, p = 0.15 | 12–3, 20 tied, p = 0.035 | 7–1, 26 tied, p = 0.070 |
| Exchanges 6–10 | 24–3, p < 0.0001 | 23–4, p = 0.0003 | 15–5, p = 0.041 |
| Contextual tier, exchanges 2–10 | 23–1, p < 0.0001 | 25–4, p = 0.0001 | 9–0, p = 0.004 |

The original scenario set is the weak spot. Under Haiku 5.5 it shows no drop (10–7). Under GPT-5.4 mini it falls
short of significance. The drop is clearest late in the conversation under every judge.

Style and vocabulary (section 10.3, second set, three-way complete exchanges, Holm across the three tests):

| Judge | Style (colloquial vs careful lay) | Vocabulary (careful lay vs clinical) | Style minus vocabulary | Statement |
|---|---|---|---|---|
| Haiku 4.5 | 13–2, Holm p = 0.022 | 7–5, 3 tied, Holm p = 0.77 | 10–3, Holm p = 0.18 | not separated |
| GPT-5.4 mini | 12–2, Holm p = 0.039 | 8–4, 3 tied, Holm p = 0.39 | 9–3, Holm p = 0.29 | not separated |
| Haiku 5.5 | 11–2, Holm p = 0.067 | 5–3, 5 tied, Holm p = 0.73 | 11–2, Holm p = 0.067 | not separated |

Every judge points the same way: the drop goes with casual style, while careful lay wording sits near clinical
wording. The registered rule needs the style-minus-vocabulary test to be significant before it says style matters more,
and with 15 triples it is not under any judge. A powered test of this question is the structured-lay arm designed in
`docs/exploratory/structured_lay_design_20261106.md`.

## 2. Single-turn advice: the judge against the human coder

The owner's blinded coding of 25 responses (`data/advice/human/`, rubric 1.1-draft), joined to the judge of record's
tier by response hash. Judge minus human, in tier steps.

| Arm | n | Judge lower | Same | Judge higher | Mean |
|---|---|---|---|---|---|
| Clinical | 9 | 1 | 8 | 0 | −0.11 |
| Patient | 8 | 2 | 5 | 1 | −0.13 |
| Translated | 8 | 3 | 4 | 1 | −0.25 |

The lower weighted κ on the patient arm (0.54, against 0.77 on clinical; `data/advice/human/agreement_report.json`)
comes from disagreements in both directions. There is no consistent tilt against patient wording, and at this size a
bias of less than about half a tier step would not show.

## 3. Single-turn advice: the judge against Jev

The published Jev calibration cases (`data/jev_calibration.json`, 1,810 responses; Jev 1.13, served as
`typesafe/jev-1.13-20260917`). Jev minus judge, in tier steps, so positive means the judge read the reply as less urgent. The 95%
intervals are percentile bootstrap over responses (seed 20261106, 2,000 resamples). They ignore that one stimulus is
answered by several models, so they are somewhat too narrow.

| Arm | n | Exact | Mean (Jev − judge) [95%, unclustered] | Judge lower / higher |
|---|---|---|---|---|
| Clinical | 604 | 0.82 | +0.07 [+0.03, +0.12] | 63 / 45 |
| Patient | 604 | 0.85 | +0.06 [+0.02, +0.10] | 57 / 36 |
| Translated | 602 | 0.79 | +0.12 [+0.07, +0.17] | 84 / 44 |

The judge reads slightly less urgent than Jev everywhere. Its gap on patient wording is no larger than on clinical
wording, which is the pattern a register bias against patient prose would break. The translated arm's gap is the
largest of the three.

## Limits

- Every judge here is a language model. Agreement among them cannot show that the advice itself got less urgent; it
  can only show that the result does not hinge on one judge's reading.
- Wave 2's target is Claude Haiku 4.5 in every run, and the scenarios are synthetic, scripted by the project, one epoch per
  fire. No physician has reviewed the scenarios or the replies.
- The re-grades use the instruments recorded for each run (rubric digest `bd4aa5596b81` for the amended analysis);
  the as-first-written block of the registered analysis is not compared here.
