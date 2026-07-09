# Design note — feature-level experiments (B4): cross-pair transfer and vector-vs-feature

Owner-approved 2026-07-09 (`docs/fable_week_plan.md`, "B4 both"). Registered
before any B4 data collection; any later edit to the designs below is visible
in git history and must be flagged as an amendment in the analysis writeup.
Both experiments cost $0: Design A runs entirely on Neuronpedia's hosted
`/api/steer` path (`medlang_circuits/steering.py`); Design B adds one local
CPU arm that waits on the B1 patching dependency.

## Established baseline (what these designs extend)

All arms below ran on gemma-2-2b, `/api/steer` SIMPLE_ADDITIVE, temperature 0,
seed 16, greedy 8-token continuations, features from the
`gemmascope-transcoder-16k` source set. On the 5-pair boost-recovered subset
(`data/simulated/boostgrid_s5.json`; pairs referred to here as P1–P5):

- boost own top-5 clinical features at strength 5 → **5/5 recovered**;
- boost clinical ranks 6–10 (strength 10) → **3/4** (+ an identical
  independent replication) — near-parity with top-5;
- placebo, 5 seeded-random features at strength 10 → **0/5**;
- dose curve: **2.5 → 4/5, 5 → 5/5, 10 → 4/5, 20 → 1/4**. Strength 5 is the
  saturating dose and is therefore the fixed strength everywhere below.

(Sources: `../patientwords/data/provenance.json:steering_titration`;
`docs/findings_synthesis.md` §4; `trace_out/boostgrid_*`.)

## Shared pre-registration (both designs)

**Recovery criterion (mechanical, fixed here).** A cell *recovers* iff the
pair's `target_clinical_token` appears in the steered 8-token greedy
continuation (tolerant leading-wordpiece match, as `paired_stats.py` anchors
targets) and does not appear in the default continuation recorded in the same
response. Both continuations are stored verbatim in the batch summary
(`steering_boost.response.STEERED` / `.DEFAULT`), so classification is a
string operation on landed JSON, never a judgment call. Before any B4 cell
fires, this rule is validated by reprocessing the already-landed
`trace_out/boostgrid_*` summaries; if it fails to reproduce the published
classifications, the rule is corrected against that *old* data and the
correction documented here — the rule is never tuned on B4 outputs.

**Steering constants.** Strength 5.0, `n_tokens` 8, temperature 0, seed 16,
`steer_special_tokens` true, SIMPLE_ADDITIVE — the exact request
`steer_ablate` builds today. No code changes are needed for Design A.

**Remeasure rule (error-dependent, never outcome-dependent).** Hosted 5xx
failures are a known server flake (the strength-20 arm resolved three this
way). A cell whose steer call or trace fails server-side is refired at most
twice; a cell still failing is reported unmeasured and shrinks its
denominator, exactly as prior arms report "3/4 measured". No cell is ever
refired because of the answer it gave.

**Blind-to-outcome execution.** Stimulus files are constructed mechanically
from `boostgrid_s5.json` before anything fires; all cells of a grid fire in
one workflow run; no steered continuation is read until the full grid has
landed; classification then runs the pre-registered rule over every cell at
once. Fires go through `scripts/fire_trigger.py` only (journaled, queue-safe),
and the two Design A fires are chained, never stacked.

---

## Design A — cross-pair feature transfer

**Question.** The top-5 clinical features that causally recover a pair's
clinical continuation — are they a *shared clinical-register circuit* or five
pair-specific lexical handles? Boost pair *i*'s top-5 clinical features while
the model reads pair *j*'s patient wording and see whether *j*'s target
recovers.

**Hypotheses (fixed before data).**

- **H-shared:** the tagged clinical features implement a register-level
  circuit → off-diagonal cells recover at a rate comparable to the diagonal
  and well above placebo.
- **H-idiosyncratic:** the features are pair-bound → diagonal recovers
  (established), off-diagonal sits at the placebo rate.
- **H-topic (intermediate):** transfer only within topic → same-topic
  off-diagonal cells recover, cross-topic cells do not.

**Cells and n, stated up front.** Full 5×5 grid over P1–P5 = 25 cells
(20 off-diagonal transfer cells + 5 diagonal replications of the established
strength-5 arm), plus a 5-cell placebo row = **30 steer calls, 60 hosted
graphs, $0**. If any donor pair's clinical graph fails to trace after
remeasures, the grid shrinks to N×N over the pairs that traced (NxN stated in
the writeup); the grid is never extended beyond 5×5.

**Mechanics (zero code change).** The existing 2panel boost arm traces the
*clinical* prompt, takes that graph's top-5 clinical features, and boosts them
while completing the *patient* prompt (`_steer_boost` in
`medlang_circuits/batch_eval.py`). So a crossed pairs file executes the
transfer cell directly. Build `data/simulated/transfer_grid_5x5.json` with 25
entries in donor-major order; entry (i→j) is:

- `top_prompt` = P*i*'s clinical sentence (donor: its graph supplies the
  boosted features);
- `bottom_prompt` = P*j*'s patient sentence (recipient: the prompt being
  steered);
- `target_clinical_token` = P*j*'s target (recovery is judged on the
  recipient);
- `generation.transfer = {"donor": i, "recipient": j, "source":
  "boostgrid_s5.json"}` so every cell is auditable.

Diagonal entries (i = j) reproduce the `boostgrid_s5.json` prompts and
targets exactly (only the `transfer` audit field is added) — a free third
replication of the established arm (prediction: recoveries match
the landed 5/5). Each recipient's patient graph is re-traced once per column;
the five independent re-traces per patient prompt are kept as a free
graph-stability check, not an endpoint.

**Two cells are flagged in advance.** P1 and P3 share a target token and a
topic (see the pairs file). Cells 1→3 and 3→1 are a labeled subclass:
recovery there is compatible with token-level (not circuit-level) transfer
and is excluded from the primary cross-topic reading. Same-topic vs
cross-topic membership per cell is fixed by the `topic` field already in the
pairs file.

**Exact trigger parameters.** One workflow run covers the grid (offsets fan
out as parallel matrix jobs inside a single queue slot). `screen_targets`
must stay empty — the screen would compare donor prompts against recipient
targets and drop cells by design.

```bash
python scripts/fire_trigger.py fire --trigger circuit-trace --params '{
  "graph_models": "gemma-2-2b", "mode": "2panel",
  "pairs_file": "data/simulated/transfer_grid_5x5.json",
  "offsets": "0,5,10,15,20", "sample_size": "5",
  "steer_boost": "5", "steer_boost_strength": "5",
  "commit_outputs": "true", "_nonce": "b4a-transfer-r1"
}' --note "B4 design A: 5x5 cross-pair transfer grid, strength 5"
```

Placebo row (chained after the grid resolves, never stacked): the recipients'
own pairs file with the placebo arm at the *transfer* strength — the
established placebo (0/5) ran at strength 10, so the dose-matched control is
re-run at 5. `top_random_features` is seeded (seed 16), so the draw is the
same auditable 5 features per patient graph as the landed placebo arm.

```bash
python scripts/fire_trigger.py fire --trigger circuit-trace --params '{
  "graph_models": "gemma-2-2b", "mode": "2panel",
  "pairs_file": "data/simulated/boostgrid_s5.json",
  "offsets": "0", "sample_size": "5",
  "steer_placebo": "5", "steer_boost_strength": "5",
  "commit_outputs": "true", "_nonce": "b4a-placebo-s5"
}' --note "B4 design A: placebo row at the transfer strength"
```

`steer_rank_offset` stays empty in both fires (the low-rank arm is not part
of this design).

**Analysis plan (fixed before data).**

- **Primary endpoint:** off-diagonal transfer rate = recoveries / measured
  off-diagonal cells (max n = 20), with Clopper–Pearson 95% CI; compared to
  the placebo row (max n = 5) by two-sided Fisher's exact test.
- **Interpretation bands, pre-committed:** transfer CI excluding the placebo
  rate with point estimate ≥ 0.5 → H-shared; transfer ≤ 2/20 with the
  diagonal at ≥ 4/5 → H-idiosyncratic; anything between → report the
  same-topic vs cross-topic split (H-topic) rather than forcing a binary
  call. The flagged same-target cells (1→3, 3→1) are reported separately in
  every band.
- **Secondary (labeled exploratory):** transfer rate vs donor–recipient
  feature-set overlap, computed mechanically from the landed graphs (do
  donors whose top-5 literally intersect the recipient's own top-5 transfer
  more?); per-recipient transfer counts (is one recipient easy for every
  donor — a recipient effect, not a circuit effect?).

**Stopping rule.** One pass over the 30 cells plus the error-dependent
remeasure rule; the experiment ends when every cell is landed or declared
unmeasured. No second grid, no added pairs, no strength changes.

---

## Design B — steering vector vs SAE features

**Question.** Is the SAE feature basis doing real work, or would a plain
mean-difference direction in the residual stream steer just as well? This is
the standard "are features privileged?" control the steering results
currently lack.

**Arms (same 5 pairs, same recovery criterion, same dose logic).**

1. **SAE-feature arm (hosted, established path):** boost the pair's own top-5
   clinical features at strength 5 — the landed 5/5. To control for hosted
   drift, one fresh replication fires in the same week the vector arm runs
   (`pairs_file: "data/simulated/boostgrid_s5.json"`, `steer_boost: "5"`,
   `steer_boost_strength: "5"`, `_nonce: "b4b-sae-rerun"`; otherwise identical
   to the Design A diagonal).
2. **Vector arm (local CPU, new):** inject a mean-difference residual vector
   while greedily decoding 8 tokens from the same patient prompts,
   temperature 0.

**Vector definition (primary, fixed here).** For pair *i* and layer *l*:

```
v_i,l = resid_post_l(clinical prompt, last token)
      - resid_post_l(patient  prompt, last token)
```

computed from the pair's *own* prompts — matching the SAE arm, which uses the
pair's own graph. Injection sites are the layers of that pair's boosted top-5
features (recorded per pair in `trace_out/boostgrid_s5` request blocks), added
at every token position including generated ones, mirroring
`steer_special_tokens: true` on the hosted side.

**Matched strength (the sharp edge, fixed here).** The hosted arm adds
`5 × d_f` per feature, where `d_f` is the feature's transcoder decoder
direction. The matched vector arm scales `v_i,l` so its L2 norm equals the
norm of the summed SAE intervention at that layer:
`‖v̂_i,l‖ = ‖Σ_f 5·d_f‖` over that pair's boosted features at layer *l*
(decoder rows from the public Gemma Scope transcoder weights; CI has
`HF_TOKEN`). Primary comparison is at 1× matched norm only. A {0.5×, 2×}
ladder may run afterwards, labeled exploratory — it can never rescue the
primary comparison.

**Bridge check (gates interpretation).** Before comparing arms, the SAE boost
is reproduced *locally*: add the five decoder directions at strength 5 as an
additive hook and confirm the same recoveries as the hosted rerun. If hosted
and local disagree, the discrepancy is reported and the comparison stops —
otherwise a vector-vs-feature difference could just be a hosted-vs-local
implementation difference.

**Cells and n, stated up front.** 5 pairs × 2 primary arms (+ 5 local bridge
cells) = **15 primary cells**. No expansion; misses are misses.

**Outcome map (fixed before data).**

- **Vector ≈ SAE (parity) or vector > SAE:** the feature basis is not
  privileged for this behavior — a single clinical-minus-patient direction
  carries the register shift. The causal story survives, but its natural
  description becomes "a direction in the residual stream", and the
  distributed-rank result (6–10 ≈ top-5) is reinterpreted as the features
  jointly spanning that direction.
- **SAE > vector:** the feature-level handle is real — the top-5 features
  carry causal structure a mean-difference direction misses, and the
  feature-family language in the synthesis stands as written.
- **Both ~0:** contradicts the established hosted 5/5 — treated as an
  implementation failure (see bridge check), not a finding.

**Analysis plan.** Recovery rate per arm with Clopper–Pearson 95% CIs; the
per-pair paired outcomes reported as a discordance table (which pairs recover
under one arm only). At n = 5 this comparison is descriptive by design and is
reported as such — no significance claim, just the pre-committed outcome map.

**Sequencing.** The vector arm needs local residual read/write — the same
hooking dependency (transformer-lens) the activation-patching CI job brings
in (`docs/activation_patching_design.md`, B1). Design B therefore executes
**after B1 lands**, as a small extension of that CPU workflow emitting the
standard `batch_summary` schema (`backend: "steering_vector"`,
`source_set: null`). Design A has no such dependency and can fire first.
The hosted SAE rerun is timed to the vector arm's week, not to B1's landing.

---

## What would falsify the circuit story

The claim under test is that a specific, nameable clinical feature circuit —
not steering-as-such, not a lexical trick — causally carries the clinical
continuation. It fails if: the strength-5 placebo row recovers at a rate
comparable to the treatment cells (specificity was an artifact of dose);
transfer appears only in the same-target cells 1→3/3→1 while cross-topic
cells sit at placebo (the "circuit" is a token-copying handle); the local
reproduction of the SAE arm cannot match the hosted result (the causal
evidence is an API artifact); or the diagonal replication itself breaks
(the established 5/5 does not survive re-execution). Parity of the
mean-difference vector with the SAE arm does *not* falsify causality — it
demotes the description from "these features" to "this direction", and the
synthesis would be amended to say so.
