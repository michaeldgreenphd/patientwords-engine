# Design note — a clinical-equivalence screen for future runs

Parked for the owner's return (2026-07-09). Not implemented; Tier B is
mid-flight on its pre-registered design. Motivated by the blind stimulus QC
(`docs/stimulus_qc_v1.json`): 15/20 sound, but all 3 flawed pairs fell in the
flip half — failure mode is **condition-equivalence drift on the patient
side** (the rewrite loses/changes clinical specificity), not register. The
owner is arranging a clinician-in-the-loop equivalence review; this note maps
where it fits.

## Framing: equivalence is a third, parallel gate

The pipeline already filters in layers. Equivalence is a distinct *kind* of
check — semantic/clinical — which is why the existing gates miss it:

- **Structural** — `medlang-generate` validators (single-span swap,
  probe-boundary ending, term-verbatim, dedupe). *Well-formed?*
- **Behavioral** — `--screen-targets 0.02` in `batch_eval`. *Does the
  clinical side actually predict the target?*
- **Equivalence (new)** — *Do both phrasings describe the same clinical
  situation?* A pair can pass the first two and still fail this.

## Four insertion points (with the code hook)

1. **Generation-time LLM triage** — in `medlang-generate`, a new validator
   that writes `equivalence: {score, verdict, judge_model}` per pair and
   rejects gross drift (new `rejection_reason`). NOT the screen (LLM judging
   LLM-written equivalence has correlated blind spots) — a cheap high-recall
   pre-filter that conserves clinician time.
2. **Clinician review as a joined data file** (highest value). Mirror the
   reviewed tier vocabulary exactly: `data/equivalence_review.json` keyed by
   pair id, produced by clinicians through a review app (the tap-through
   decks are the right UI), consumed by `urgency_shift.py`. Keeps human
   judgment out of the automated path, versioned as data.
3. **Screening stage, sibling to `--screen-targets`** — in `batch_eval`, the
   `screening` result object already has the "kept-but-skipped" shape; add
   `screening.equivalence_screened_out`. A pair passes only if measurable AND
   equivalence-confirmed. Nothing downstream changes.
4. **Analysis conditioning** — in `urgency_shift.py`, carry the equivalence
   label as a covariate and report the downgrade rate two ways:
   equivalence-confirmed (headline) and raw (sensitivity bound).

## Recommended placement: measurement-informed, blinded clinician review

Tracing is $0; clinicians are the constraint. So do NOT gate before
measurement — **trace everything, then route to clinicians only where
conclusions are made**: every confident downgrade (p ≥ 0.2) plus a blinded
random sample of non-flips as a control. Human judgment lands on the
load-bearing pairs; the control guards against reviewers being swayed by
knowing a pair flipped.

Defensibility requirements:
- **Blind reviewers to the measurement outcome** (as the QC deck did) so
  equivalence labels can't be reverse-fit to the effect.
- **Pre-register the criterion, threshold, and reviewer protocol before
  collecting labels.** Adding an equivalence filter to a pre-registered run
  must be a documented amendment, else it reads as post-hoc filtering.

## Bonus the clinician labels unlock

Once clinician labels exist, measure the LLM triage judge (point 1) *against*
them — agreement rate, like the hand-measured validity correlation already in
the study. Validates the cheap pre-filter and yields a second reportable
number.

## When the owner returns, ready to build

Draft the pre-registration amendment; add the `equivalence` field +
generation triage + `batch_eval` screen hook + collector conditioning; build
the blinded clinician review app. All four are small, isolated changes that
reuse existing patterns (validator chain, `--screen-targets` bookkeeping,
reviewed-vocabulary join, deck UI).
