# First model-backed run packet — pending, not run

Written 2026-11-10. This is a request for one decision: approve or decline the packet as a
whole. Nothing in it has been fired, dispatched, downloaded or measured. Writing or merging
this document authorizes nothing. Paths are relative to the engine root.

**Answer first.** The recommended first model-backed milestone uses `gemma-2-2b` on the
existing `logits-eval` lane, in two $0 fires on standard runners: a fresh float32 parity
measurement through interp-engine at the pinned revision (stage A), and the legacy
first-token read of the one reviewed case under the pilot root (stage B). Stage A is an
instrument check and stage B is a pipeline check on one case; neither is a study
measurement. The packet adds no lane, no key and no runner. It cannot start today: of the prerequisites in section 9, six are met,
nine are not, and one can only be checked at fire time. The two that only the owner can
supply are an execution approval that names these fires and the parity gates fixed in
advance.

The packet does not include a lens, an ICA basis, an attribution graph or an intervention.
Each of those has an artifact whose identity is unknown or a route that has never run
(section 5). They stay in the plan as `unavailable` with the reason.

## 1. The decision

| If approved | If declined |
|---|---|
| Two preparation pull requests (section 8.1), then two chained `logits-eval` fires and one park (section 8.2), each on its own first attempt, with the gates of section 6 fixed as written or as the owner amends them before the first fire. | Nothing changes. No fire, no file under `pilot/`, no capability row moves. The Qwen3-4B manual baseline route stays as blocked as it is in `docs/exploratory/baseline_ci.md`. |

Total proposed provider spend: $0. Total proposed runner time: about 20 runner minutes by
the estimate in section 4, inside one 240-minute job ceiling per fire.

## 2. Candidate comparison

Status words are the capability matrix's (`data/experiments/capability_matrix.v1.json`,
`as_of` 2026-11-10, file sha256 `a2cdbf7b…a0458`), read with
`python -m scripts.experiments.cli capabilities --model gemma-2-2b` (run for this document;
offline). The matrix is being edited in the same change set, so re-read it before acting.

| | `gemma-2-2b` | `qwen3-4b` | `qwen3.5-2b-base` |
|---|---|---|---|
| Pinned revision | `c5ebcd40d208330abc697524c919956e692655cf` | `1cfa9a7208912126459214e8b04321603b3df60c` | `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` |
| CPU first-token lane | `artifact_available`; 20 landed parts, 1,219 results | `artifact_available`; 46 parts, 1,957 results | `artifact_available`; 39 parts, 2,343 results; post-registration exploratory cohort |
| Second implementation | interp-engine 1.5.1 eager float32: `parity_passed` against hosted probabilities on one 50-pair batch (2026-09-04). The audited summary records `inference.revision` null. The only recorded parity audit in the project. | None has run. A two-stack comparison with Causalab is prepared for one case and blocked (below). | None. `scripts/depth_probe.py` support is unverified (`docs/model_matrix.md`). |
| Third route | Hosted attribution graphs, calibrated source set `gemmascope-transcoder-16k`: `artifact_available`. Hosted server commit not attested. Activation patching supports it (32 landed parts). | Hosted graphs: a two-pair probe landed; source set `transcoder-hp` is not calibrated, so `clinical_mass` stays null. | Not in `medlang_circuits/graph_client.py` `MODEL_REGISTRY`. Not in `scripts/activation_patch.py` `HF_IDS`. |
| Lens artifacts | Hosted J-Lens and logit lens: `artifact_available_identity_unknown`; no lens revision is recorded and the host changed its readouts twice. | Released J++ file: SHA-256 verified locally, fit model and tokenizer revisions unknown, `transport_authorized: false`. Released J-Lens file: advertised hash only. | None recorded. |
| ICA basis | `sida/icalens-gemma-2-2b-pile10k` is named in the ICA fork: `artifact_available_identity_unknown`. Its manifest was not read (huggingface.co is blocked from development containers), so layers, hashes and fit revision are unknown. | No basis named. | The fork names no basis for it: `architecture_supported` only. The Neuronpedia id `qwen3.5-2b-pt` is recorded as an unverified alias; the checkpoint behind it was not verified. |
| Geometry recorded locally | 26 layers (`docs/activation_patching_design.md:69`); width 2,304 only in the ICA fork's result files | 36 layers, width 2,560, vocabulary 151,936 (`data/exploratory/method_sources.v1.json`) | Not recorded, except a 248,320-entry tokenizer |
| Reviewed one-case protocol | None written for this model. The reviewed case's wording is model-independent. | `data/exploratory/qwen3_4b_one_case.v1.json`, `planned_experiment.status: blocked_before_model_execution` | None |
| Runner need | Standard hosted runner. Both lane modes have run on it for this model. | The prepared baseline requires an existing self-hosted Linux runner with 64 GiB RAM, 8 CPUs and 40 GiB free disk. Registered self-hosted runners: 0 (`data/exploratory/baseline_ci_readiness.v1.json`, checked 2026-10-16). | Standard runner; first-probe rate about 60 s per pair on 3 pairs. |
| Other blockers | None beyond section 9. | Causalab execution commit null; Linux runtime unreviewed; no current seal attestation; Causalab's Python licence unresolved; the checkpoint is post-trained and thinking-enabled, not a base model. | Hybrid Gated-DeltaNet and attention architecture: hook-site meaning unverified for any internal method. |

**Choice: `gemma-2-2b`.** Reasons, each from a record:

1. It is the only model for which a second implementation has run and been audited. The
   milestone can repeat that audit at a recorded revision, which the first audit lacks.
2. Every runtime piece the milestone needs has already run in CI for this model on a
   standard runner: `mode: logits` (20 parts) and `mode: verify` at float32 (four landed
   `verify_*` summaries).
3. It needs no new lane, key, workflow or runner. The Qwen3-4B route needs a runner that does
   not exist and four readiness fields that are null.
4. A hosted route with a calibrated source set exists for a third comparison.

What the choice gives up: the prepared Causalab comparison, which is the only prepared route
to an intervention-capable second stack, and the released J++ artifact. Both are Qwen3-4B
only, and both are blocked for reasons this packet does not remove. What the choice does not
fix: for `gemma-2-2b` every lens artifact has unknown identity and the ICA basis manifest is
unread, so the milestone is behaviour and parity only.

`qwen3.5-2b-base` is not chosen: no second implementation, no verified internal-method
support, no recorded width, and its ICA link is an unverified alias.

## 3. Model, case families and their review records

**Declared model.** `google/gemma-2-2b` at `c5ebcd40d208330abc697524c919956e692655cf`,
tokenizer from the same repository and revision (`scripts/logits_eval.py` `HF_REVISIONS`;
the loader refuses any other resolved commit). Stage A: interp-engine 1.5.1, eager backend,
CPU, float32. Stage B: transformers 5.14.1, CPU, bfloat16. Both from `constraints.txt`.

**Stage B case family: the one reviewed case.**

| Field | Value |
|---|---|
| Case id | `pw_exploratory_candidate_r001` |
| Family id | `A__cardiology__medication__L14` (review id `r001`, bundle item `vt_216a7dd64eee`) |
| Source | `pilot/runs/pilot_v2_20261002/trace/trace_pairs.json`, index 1 of 40; file sha256 `4a6ebb2215d79a41efb92643ebd9fa27cb1e882b2ffc26a98ed384407687c82a` (recomputed for this document) |
| Split | `discovery` |
| Holdout status | `unsealed_reviewed` |
| Review record | owner review recorded 2026-10-04T03:02:06Z; checker verdict `yes`; `pilot/codebook/review_export_pilot_v2_20261002.json`, sample `r001` |
| Review scope, as recorded | an owner-reviewed brand and generic substitution, not a slang contrast; the source stays a pilot source, not a main-study measurement |
| Seal record | `clean`, recorded 2026-10-04T04:29:45Z, and labelled `stored_bundle_attestation_only_not_a_new_seal_run` |
| Variants | `source` and `recipient`. `normalized_variant.status` is `unavailable`: no approved normalized wording exists in the source bundle. |
| Spec that carries all of this | `data/exploratory/qwen3_4b_one_case.v1.json`, sha256 `0d8014ec7395160409bf5afd04d7ef1d4db9cef2ce468cc62173ed89963d9f0d`. It is written for Qwen3-4B. Its case block is reused by identifier; its model block and tolerances are not. |

No prompt text is quoted here, and none may be copied into a protocol outside the reviewed
source files.

**Stage A parity set: an unsealed exploration-split batch, not a reviewed set.**
`pairs_20260706T175614Z`: 10 pairs, dated before the Tier B start stamp `20260710T011438Z`
(`ops/dashboard.json`, read through `scripts/tierb_split.py`), 0 rows sealed by
`tierb_split.sealed_pair` (computed for this document; counts only). Policy fields: stimulus
class `study_batch`, clinical review `domain_review_pending`, visibility `public`. Landed
inputs the comparison reads:

- hosted: `trace_out/pairs_20260706T175614Z/batch_summary.part_01.json`, 10 results, 1 null
  patient-side value, sha256 `66925c49e7e6223193a2c095653c94d794727968a4dd99fa937531bb23b5a552`;
- CPU bfloat16: `trace_out/pairs_20260706T175614Z__gemma-2-2b/batch_summary.part_01.json`,
  10 results, `inference.revision` equal to the pin, sha256 `3f21f073769e27d9ca4c927a624580222c568ea2fcbefe41035c9807151cd105`.

This batch is used as numeric input to an instrument check. No clinical reading is taken
from it and its review status does not change.

**Is there a larger adequately reviewed set? No.** What exists:

- The owner's blind review of 40 rows of pilot run `pilot_v2_20261002`, of which the owner
  kept 27 (`pilot/codebook/agreement_pilot_v2_20261002.md`). These are owner-reviewed,
  pilot-sourced and not clinician-reviewed, and no selection from them is recorded as a
  protocol.
- The physician task bundle `vtasks_20261004T042945Z` (127 items, 80 tracing pairs). No
  rating has been imported: `data/verification/` holds only the questions file and the
  bundle.
- The one-case spec's follow-on scope is 12 to 20 families, labelled feasibility, not power.

A reviewed set larger than one case is a prerequisite for any milestone after this one. This
packet does not assemble one.

## 4. Resource plan

Formulas and labels are those of `docs/scaling_plan_20261110.md`: [M] measured, [D] derived
from measured, [A] assumption.

| Item | Stage A (10 pairs, float32, interp-engine) | Stage B (1 pair, bfloat16, transformers) |
|---|---|---|
| Seconds per pair | No rate is recorded for `gemma-2-2b` on the CPU lane, in either mode. [A] proxy: `gemma-2-2b-it`, slowest recorded 88.5 s per pair on the legacy bfloat16 endpoint ([M], `scripts/backfill_planner.py`). Float32 through another implementation may differ in either direction. | same proxy |
| Runner seconds | attempted pairs = ceil(10 x 1.15) = 12; 12 x 88.5 = 1,062 s = 17.7 min [D under A] | ceil(1 x 1.15) = 2; 2 x 88.5 = 177 s [D under A] |
| Weights in memory | about 10.4 GB at float32, from the rounded "2.6B" parameter count [D] | about 5.2 GB at bfloat16 [D] |
| Runner | hosted `ubuntu-latest`: 15 GiB physical ([M], one job) plus the workflow's 12 GB swap file. Four float32 verify runs of this model have landed, so the load fits; its peak memory was not recorded. | same runner; 20 logits parts have landed |
| Output size | about 18 kB: the landed 50-pair verify summary is 90,398 bytes, 1,808 per result [D] | about 2.6 kB: 2,579 bytes per logits result [D] |
| Activations, full-vocabulary logits | none stored; the lane keeps four-decimal probabilities and a top-k list | none stored |
| Job ceiling | 240 minutes, `max-parallel` 2 | same |
| Provider budget | $0 | $0 |

One weak timing record exists for stage A's shape: the 2026-09-04 verify fire of 50 pairs was
resolved in the journal 7.2 minutes after it was fired. Whether that resolve followed the
landing is not recorded, so it is not used as a rate.

The run is also the first opportunity to record what section 1 of the scaling plan lists as
not measured. That needs a change to the measurement scripts and is not part of this packet.

## 5. Artifact compatibility required, and its current status

Required for this milestone:

| Model revision x method x backend x artifact | Status today | Evidence | Enough? |
|---|---|---|---|
| `gemma-2-2b` @ `c5ebcd40…` x `behavior_next_token` x `cpu_transformers` x bfloat16 | `artifact_available` | `HF_REVISIONS`; 14 landed summaries record the pin (`docs/model_matrix.md`) | Yes for stage B. |
| `gemma-2-2b` @ revision null x `behavior_next_token` x `cpu_interp_engine` x float32 | `parity_passed`, scope: one batch, against hosted three-decimal values, revision not recorded | `docs/backend_agreement_20260903.md`, results of 2026-09-04 | No. The row cannot name a revision. Stage A exists to produce a record that can. |

Not required, and planned as `unavailable`:

| Method | Status today | Why it is out |
|---|---|---|
| `attribution_graph`, hosted | `artifact_available`, server commit not attested | A third comparison uses the landed hosted part; no new trace is asked for. |
| `j_lens`, `logit_lens`, hosted | `artifact_available_identity_unknown` | No lens revision recorded; three instrument eras in landed readouts. |
| `ica_lens` | `artifact_available_identity_unknown` | Basis manifest unread; fit revision, layers and hashes unknown. |
| `jpp` | no row for this model | The released artifact is for Qwen3-4B. |
| Interventions | no executable adapter | Out of scope for a first milestone. |

After stage A, a capability row may gain a parity record with a revision only through a
reviewed change to the matrix that cites the landed files by path and hash.

## 6. The parity result that must be fresh, and the prespecified endpoints

### Stage A: parity (an instrument check; it makes no behavioural claim)

Measured: the 10 pairs of `pairs_20260706T175614Z` through interp-engine 1.5.1 at float32, at
the pinned revision. Compared offline, with `scripts/backend_agreement.py`, against the two
landed parts named in section 3.

Why it must be fresh: the existing audit's summary records `inference.revision` null, and all
landed interp-engine summaries predate enforced pinning (the four `verify_*` summaries were
read for this document: `revision` null, `revision_pinned` absent, interp-engine 1.5.1). The
pinned load path through interp-engine has never run against the real package; its tests use
a fake module.

Gates. These are proposals. The owner fixes them when approving, and they are not changed
after the run. The project's existing tolerances are for Qwen3-4B, and the one-case spec
says no Gemma tolerance is imported.

| # | Check | Proposed gate |
|---|---|---|
| A1 | Identity | The summary records `inference.revision` equal to `c5ebcd40d208330abc697524c919956e692655cf`, `revision_pinned` equal to it, dtype float32, interp-engine 1.5.1, `completed: true`, 10 results with indices 1 to 10. |
| A2 | Tokenization | `token_parity` holds on all 20 prompts. |
| A3 | interp-engine float32 against hosted | Every side both routes report differs by at most 0.001 in probability. At most 19 sides are comparable (one hosted value is null). A side on which the hosted value disagrees with the hosted run's own recorded spread is listed by index and counted as a hosted read defect, not as a parity failure and not dropped. |
| A4 | interp-engine float32 against CPU bfloat16 | Descriptive only: mean, median and maximum absolute difference over 20 sides. No pass or fail. A maximum above 0.0311, the earlier audit's maximum over 100 sides, is reported as a finding to investigate. |
| A5 | Finite values | No non-finite probability; no side reported by the CPU routes is missing. |

Reference values for A3 and A4 are the 2026-09-04 audit's: 70 of 71 sides within 0.0005
against hosted, one at 0.0273 from a hosted prefix read; mean 0.00431 and maximum 0.0311
against bfloat16. With at most 19 and 20 sides, stage A can confirm or contradict agreement
on this batch. It cannot estimate agreement in general, and it does not separate
implementation from precision: the comparison at equal dtype is not in this packet, because a
second verify fire on the same batch and offset writes the same file name.

### Stage B: the reviewed case on the legacy endpoint

- **Primary endpoint.** `legacy_first_target_token_probability` for each of the two variants,
  and their signed difference, source minus recipient. This is the one-case spec's primary
  endpoint and the lane's existing read: the full-vocabulary softmax probability of the first
  token of the target, recorded to four decimals.
- **Secondary.** The recorded top-k continuation list for each variant.
- **No direction is predicted and no test is run.** n = 1. A zero or opposite-direction
  difference is a completed result.
- **Labels.** The contrast is a brand and generic substitution by the review record. It is
  not reported as a clinical-versus-colloquial register effect. The output is under
  `pilot/logits/` and is a pipeline check, never a study number
  (`docs/triggers.md`, `logits-eval` row).

### Controls

| Control | Status |
|---|---|
| Token parity across implementations | part of A2 |
| Fixed comparison inputs | the two landed parts are named by sha256 in section 3; a different hash at comparison time stops the comparison |
| Hosted self-consistency | part of A3 |
| Normalized rewrite | `unavailable`: no approved wording |
| Within-register paraphrase, changed-fact control | `unavailable`: none exists in reviewed material; the one-case spec lists the paraphrase as pending |
| Second seed or replicate | not planned: the read is deterministic on one runner; a replicate would be its own fire and its own approval |

## 7. What would count as failure

Stage A fails, and stage B is not fired, if any of these holds:

- the job does not finish, the model does not load, or the loader's revision check refuses;
- A1, A2 or A5 does not hold;
- A3 exceeds its gate on any side that is not a listed hosted read defect.

Stage B fails if any of these holds:

- the cell's fail-closed seal check is not clean (the cell then commits nothing);
- no part lands, the part is not `completed`, or its single result is not index 1;
- the pairs file's sha256 at the fired commit is not `4a6ebb22…7c82a`.

Not a failure: any size or sign of the stage B difference, and any A4 value.

A failure is recorded with its artifacts and reported. It is not re-fired to look for a pass.
Each approval covers one first attempt per fire, the rule the manual baseline route already
uses (`docs/exploratory/baseline_ci.md`, retry limits). A new attempt needs a new approval.

## 8. Proposed commands — NOT RUN

None of the commands in 8.1 to 8.3 has been run. `scripts/fire_trigger.py` was not executed
in any form while this packet was written, including `--dry-run`. The fire parameters were
checked by reading `KNOWN_KEYS` for `logits-eval`, the workflow's params job and
`docs/triggers.md`; they were not validated by the script. The first command to run after
approval is each fire command with `--dry-run` added.

### 8.1 Preparation, by reviewed pull request — NOT RUN

```bash
# NOT RUN. Writes the run-named copy of run 2's pairs file, byte-identical by the 2026-10-05 check.
python pilot/analysis/trace_pairs.py --run-dir pilot/runs/pilot_v2_20261002 --review-sample
sha256sum pilot/runs/pilot_v2_20261002/trace/trace_pairs.json \
          pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json

# NOT RUN. Holdout seal: the default sweep plus the run's trace directory (--extra replaces the default list).
python scripts/seal_check.py --site ../patientwords \
  --extra docs,ops,data/verification,pilot/runs/pilot_v2_20261002/trace
```

The second pull request adds an adapter that reads a landed `batch_summary` or
`verify_summary` part into a `behavior_next_token/1` payload and envelope, with every field
the legacy part does not record listed under `not_recorded`. No such adapter exists, so
there is no command for it yet.

### 8.2 Execution, only after approval, on `main`, lane idle — NOT RUN

```bash
# NOT RUN. Stage A: fresh float32 parity at the pinned revision. $0.
python scripts/fire_trigger.py fire --trigger logits-eval \
  --params '{"models": "gemma-2-2b", "pairs_file": "data/simulated/pairs_20260706T175614Z.json", "mode": "verify", "dtype": "float32", "limit": "10", "offset": "0", "commit_outputs": "true"}' \
  --note "Stage A of docs/exploratory/first_model_run_packet_20261110.md: gemma-2-2b interp-engine float32 parity at the pinned revision"

# NOT RUN. After stage A has landed, passed section 7 and been resolved. Stage B: the reviewed case. $0.
python scripts/fire_trigger.py resolve --trigger logits-eval
python scripts/fire_trigger.py fire --trigger logits-eval \
  --params '{"models": "gemma-2-2b", "pairs_file": "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json", "mode": "logits", "output_root": "pilot/logits", "limit": "1", "offset": "0", "commit_outputs": "true"}' \
  --note "Stage B of docs/exploratory/first_model_run_packet_20261110.md: reviewed case r001 on the legacy endpoint, pilot root"

# NOT RUN. After stage B has landed: resolve, then restore the lane's no-op default.
python scripts/fire_trigger.py resolve --trigger logits-eval
python scripts/fire_trigger.py park --trigger logits-eval
```

Expected landing paths, both absent today (checked with `ls`):

- `trace_out/verify_pairs_20260706T175614Z__gemma-2-2b/verify_summary.part_01.json`
- `pilot/logits/pilot_v2_20261002/pilot_v2_20261002_trace_pairs__gemma-2-2b/batch_summary.part_01.json`

The fires are chained, never stacked: the lane holds one running and one pending run, and a
third push evicts the pending one silently. The scheduled backfill uses the same concurrency
group every 12 hours without the journal's queue guard, so the lane must be idle and the
fire placed outside a cron slot. Follow the repository's `fire-trigger-safe` and
`harvest-resolve` procedures.

### 8.3 After landing, offline — NOT RUN

```bash
# NOT RUN. interp-engine float32 against hosted, then against CPU bfloat16.
# Each --out is a new file in a directory outside the repository.
python scripts/backend_agreement.py \
  --reference trace_out/pairs_20260706T175614Z \
  --candidate trace_out/verify_pairs_20260706T175614Z__gemma-2-2b \
  --out /path/outside/the/repository/interp_fp32_vs_hosted.json
python scripts/backend_agreement.py \
  --reference trace_out/pairs_20260706T175614Z__gemma-2-2b \
  --candidate trace_out/verify_pairs_20260706T175614Z__gemma-2-2b \
  --out /path/outside/the/repository/interp_fp32_vs_local_bf16.json
```

The parity record that follows states both environments, the batch by stem and index, the
dtype, each gate, the counts that agreed and disagreed, and what was not compared
(`docs/upgrade_checklist.md` section 6). `verify_summary` files stay outside the measurement
collectors by design, so no published statistic moves.

### 8.4 Run for this document (offline, read-only)

```bash
python -m scripts.experiments.cli capabilities --model gemma-2-2b          # exit 0; 6 rows
python -m scripts.experiments.estimate --families 10 --rate gemma-2-2b-it=88.5 \
       --failed-attempt-fraction 0.15                                      # exit 0; 1,062 runner seconds
```

## 9. Prerequisites

| # | Prerequisite | Status | Evidence | Rule or missing authorization |
|---|---|---|---|---|
| 1 | Model and tokenizer pinned to one commit | met | `scripts/logits_eval.py` `HF_REVISIONS`; `docs/model_matrix.md`, pinned revisions | — |
| 2 | Both lane modes have run for this model on a standard runner | met | 20 logits parts; four float32 `verify_*` summaries (read for this document) | — |
| 3 | The chosen parity batch is outside the Tier B seal | met | stamp before `20260710T011438Z`; 0 sealed rows by `tierb_split.sealed_pair` | `AGENTS.md`, research invariants: preserve holdout seals |
| 4 | No landed artifact would be overwritten | met | neither landing path exists; the earlier audit's batch is not reused because a new verify fire there would replace `trace_out/verify_pairs_20260710T011743Z__gemma-2-2b/verify_summary.part_01.json` | `AGENTS.md`: landed `trace_out/` summaries are measurements, not caches |
| 5 | The lane and its keys exist; no new lane or secret is needed | met | `docs/triggers.md`, `logits-eval` row: `mode`, `dtype`, `output_root` | A new lane or key set would need its own reviewed pull request (`docs/agent_reference.md`, execution and operations). The manual baseline route is not used: the owner exception in `AGENTS.md` (PR #121) covers preparing that route for Qwen3-4B, not running it and not another model. |
| 6 | One reviewed, unsealed case | met for one case | section 3; owner review of 2026-10-04 | Its seal record is a stored attestation, not a new seal run (row 9) |
| 7 | Execution approval that names these fires | **not met** | No owner record names a `logits-eval` fire for this purpose. `docs/decisions_20261014_owner.md`: first round, D3, "no fires until I approve"; second round, "No fires beyond what I picked above"; third round, R1 to R10 name re-judge, equity and tidy-up work only. | `AGENTS.md`, *Execution model*: fire only through `scripts/fire_trigger.py`, never merely to test docs. `docs/agent_reference.md`: operational preparation is not new authorization to spend or publish. |
| 8 | Parity gates fixed before the run | **not met** | Section 6 holds proposals. The one-case spec records that no Gemma tolerance is imported. | Owner decision |
| 9 | A current holdout seal check over the inputs | **not met** | The case's seal record is `stored_bundle_attestation_only_not_a_new_seal_run`, dated 2026-10-04 | `AGENTS.md`: preserve holdout seals; the pilot cell also runs a fail-closed seal check before it commits |
| 10 | The run-named pilot pairs file | **not met** | `pilot/runs/pilot_v2_20261002/trace/` holds `trace_pairs.json` and its meta file only | `docs/triggers.md` and `docs/pilot_runs.md`: under the pilot root the file must be `pilot/runs/<run_id>/trace/<run_id>_<name>.json`; run 2's legacy name is refused |
| 11 | A real `patientwords.experiment-protocol/1` document for this model | **not met** | The protocol needs token ids and their hash for each variant. No tokenizer is available in a development container. | `AGENTS.md`, *Execution model*: the sandbox proxy blocks huggingface.co; nothing networked runs locally |
| 12 | An adapter from a landed legacy part to a typed envelope | **not met** | `scripts/experiments/adapters/` holds fixture, readout-report and ICA adapters. `scripts/experiments/planner.py` marks every non-fixture task `unavailable` by design. | Needs a reviewed pull request with tests; a mocked test would not be evidence of real-model agreement |
| 13 | The pinned interp-engine load path has run against the real package | **not met** | All landed interp-engine summaries record `revision` null; the only tests replace the package with a fake | Not a rule. A risk: stage A is the first real execution and may fail at load. |
| 14 | A fresh parity result at a recorded revision | **not met** | Section 5, second row | This is what stage A produces |
| 15 | A reviewed set larger than one case | **not met** | Section 3 | `AGENTS.md`, known limitations: do not base a study claim on one pair's penalty or flip label. Not needed for this packet; needed for the next. |
| 16 | The lane is idle and no cron leg is pending | to check at fire time | The scheduled backfill shares the concurrency group | `docs/triggers.md`: one running and one pending; chain, never stack |

Lens, ICA and J++ identity are not prerequisites of this packet. They are recorded as
`unavailable` and stay that way until their publishers' records or a manifest read settle
them (`docs/exploratory/lens_fit_provenance_question.md`).

## 10. What this packet did not verify

- No model was loaded. Every resource figure is an estimate with a proxy rate.
- The fire parameters were read against the lane's key set and params job, not validated by
  `scripts/fire_trigger.py`.
- That `pilot/analysis/trace_pairs.py` still writes a byte-identical run-named file was not
  re-run; the 2026-10-05 check is the record.
- `pilot/logits/` has no landed run, so stage B would be the first use of that output root.
- The capability matrix was read at one moment of a working tree that other tasks were
  editing.
- Whether hosted runners remain free of charge for this repository is the project's dated
  record (`docs/model_matrix.md`, cost truth), not a fresh account check.
