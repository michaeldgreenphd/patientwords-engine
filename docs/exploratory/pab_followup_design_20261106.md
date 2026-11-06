# Design: the PatientAgentBench follow-up — 2026-11-06 (draft, nothing run)

Owner decision on the decision page, 2026-11-06 (ag-new-runs: "Design both"). The card proposed tracing the
PatientAgentBench (PAB) low- and high-literacy utterances. **That tracing already happened in August.** This design
covers what is left.

## What already exists

- **Harvest.** `data/pab/pab_harvest_20260807T021948Z.json` holds 13 complete low/high health-literacy pairs from PAB
  transcripts, under owner decision HARVEST-TRACE (`docs/decisions_20260804_pab.md`). The utterance text is derived
  from CC-BY-NC-4.0 runner output and stays engine-side; scenario text appears only as a hash.
- **Frames, preregistered before any were built.** `docs/pab_frame_spec_20260805.md` fixed the span extraction, the
  carrier frames, the target screening and two directional endpoints.
- **Build.** `scripts/pab_build_frames.py` turned the 13 pairs into 52 two-panel entries: 4 frames each, no
  exclusions (`data/pab/pabharvest_20260807T025446Z.build.json`). The batch lives in `data/pab/`, never
  `data/simulated/`.
- **Measurement, all on gemma-2-2b, $0.**
  - All 52 entries are circuit-traced (`trace_out/pabharvest_20260807T025446Z/`).
  - All 52 are read through the hosted Jacobian lens (`..._20260807T025446Z__jlens_gemma-2-2b/`).
  - 32 of the 52 carry a numeric language penalty.
  - The `pabharvest_` stem keeps them out of the confirmatory population by construction.

**What is missing.** No report tests the spec's two endpoints:
1. a negative mean language penalty for the low-literacy spans;
2. later or weaker formation depth for the low-literacy spans.

The entries appear only in two downgrade-screen review files (`docs/review/downgrade_screen_20260809.json`,
`downgrade_validated_seeds_20260809.json`).

## Step 1: report the preregistered endpoints (offline, $0)

- **Endpoint 1.** Per pair, the mean language penalty over its frames, then the mean and an exact sign test over the
  13 pairs. Pairs are the unit, not entries: the four frames of one pair share an utterance.
- **Endpoint 2.** First legible layer, first rank-1 layer and persistence per arm, from the lens readouts, plus the
  capture/hijack/unreadable class under the published taxonomy.
- **Check the lens era first.** These readouts landed on 2026-08-07, between the two known host-side lens changes
  (2026-07-31 and 2026-08-14). The 2026-10-31 re-measure covered July readouts only, so it did not include them.
  Before endpoint 2 is reported, a $0 re-read of a few pairs should show whether they still reproduce under today's
  host.
- **Report the 20 entries without a numeric penalty, with their reasons.** A missing value is never counted as zero.
- **Compare with the study's own pairs, on the same frames:** is the effect size on PAB phrasing inside the range
  seen on Claude-written stimuli? This answers the external-generator critique in `docs/critic/critic_20260821.md` as
  far as 13 pairs can.
- **Disclosures, as the spec fixed them:**
  - the simulator is an LLM;
  - the frames and targets are this study's instrument;
  - nothing publishes without a clean `seal_check` and an owner decision;
  - any output carries counts and hashes only, never utterance text.

Cost $0, about half a day of work. **This step should come first**, because steps 2 and 3 are only worth doing if
the endpoints show something.

## Step 2: other models (logits lane, $0)

Run the 52 entries on the CPU logits lane for the preregistered models without hosted graphs:
`gemma-3-4b-it`, `qwen3-1.7b` and `qwen3-4b`, the other three of `_PREREG_MODELS` in
`scripts/paired_stats_rigor.py`. The lane cost is
$0. Each fire must pass the publication-hold and release-manifest rules before its parts enter any collector
(`scripts/publication_hold.py`). The entries live under `data/pab/`, and `fire_trigger.py` takes the pairs file by
path; whether the logits workflow accepts a path outside `data/simulated/` must be checked with a $0 rehearsal first.

## Step 3: cumulative conversation context (new; needs a spec amendment)

Antigravity's new idea: trace turn 1, then turns 1–2, then 1–3, then 1–4 of each pair as growing context. This tests
whether more patient context rescues the clinical prediction or compounds the gap, as wave 2's late-exchange drop
suggests.
- **It changes the preregistered construction rules.** Spec rule 1 extracts one span per arm. So it needs an amendment
  committed before any build, recorded in `docs/prereg_divergence_log.md`.
- **Prompts get much longer.** Hosted attribution graphs and lens reads have prompt-length limits that a four-turn
  context may exceed. A $0 rehearsal on one pair settles that before any design work.

## Decisions needed

1. **Approve step 1**, the endpoint report. It is offline and $0, and I can start it immediately.
2. **Decide on step 2 only after step 1.**
3. **Decide on step 3 only after steps 1 and 2.** It needs a spec amendment and a length check.
