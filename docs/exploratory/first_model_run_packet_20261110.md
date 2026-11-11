# First model-backed run packet — pending, not run

Written 2026-11-10; completed the same day (sections 3 to 11 and 14). This is a request for
decisions, listed in section 14. Nothing in it has been fired, dispatched, downloaded or
measured. Writing or merging this document authorizes nothing. Paths are relative to the
engine root.

**Answer first.** The recommended first model-backed milestone uses `gemma-2-2b` on the
existing `logits-eval` lane, in two $0 fires on standard runners: a fresh float32 parity
measurement through interp-engine at the pinned revision (stage A), and the legacy
first-token read of the one reviewed case under the pilot root (stage B). Stage A is an
instrument check and stage B is a pipeline check on one case; neither is a study
measurement. The packet adds no lane, no key and no runner. It cannot start today: of the
prerequisites in section 12, six are met, eleven are not, and one can only be checked at
fire time.

Three things changed when the packet was completed, and each limits what it can show:

1. **Stage A can be compared with the hosted route on 9 sides, not 19.** On 5 of the 10
   rows of the parity batch the landed hosted part recorded the probability of another
   token than the one the CPU lane read (section 6). The parity criteria now name the 9
   comparable sides in advance.
2. **A complete interface protocol cannot be written offline.** The protocol validator
   needs token ids for every prompt and every target, and no tokenizer file is available in
   a development container. A valid protocol is committed for the 3 of 10 rows whose ids
   are all on a landed record (section 5). It plans 6 tasks, all `unavailable`. The other 7
   rows and the stage B case have no protocol.
3. **The two behaviour checks do not exercise the ICA integration.** Section 11 describes
   the smallest step that would, and what stays unverifiable from here.

The shared experiment interface (`scripts/experiments/`) has run only on synthetic
fixtures. Those runs establish neither real-model parity nor clinical validity, and this
packet does not change that.

## 1. The decision

| If approved | If declined |
|---|---|
| Three preparation pull requests (section 8, items 1, 3 and 4), then two chained `logits-eval` fires and one park (section 9), each on its own first attempt, with the criteria of section 6 fixed as written or as the owner amends them before the first fire. | Nothing changes. No fire, no file under `pilot/`, no capability row moves. The Qwen3-4B manual baseline route stays as blocked as it is in `docs/exploratory/baseline_ci.md`. |

Total proposed provider spend: $0. Total proposed runner time: about 21 runner minutes by
the estimate in section 7 (17.7 for stage A, 3.0 for stage B), inside one 240-minute job
ceiling per fire. The individual questions are in section 14.

## 2. Candidate comparison

Status words are the capability matrix's (`data/experiments/capability_matrix.v1.json`,
`as_of` 2026-11-10; its file SHA-256 is in the generated block of section 5), read with
`python -m scripts.experiments.cli capabilities --model gemma-2-2b` and
`--model qwen3.5-2b-base` (run for this document; offline; 6 rows and 2 rows).

| | `gemma-2-2b` | `qwen3-4b` | `qwen3.5-2b-base` |
|---|---|---|---|
| Pinned revision | `c5ebcd40d208330abc697524c919956e692655cf` | `1cfa9a7208912126459214e8b04321603b3df60c` | `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` |
| CPU first-token lane | `artifact_available`; 20 landed parts, 1,219 results | `artifact_available`; 46 parts, 1,957 results | `artifact_available`; 39 parts, 2,343 results; post-registration exploratory cohort |
| Second implementation | interp-engine 1.5.1 eager float32, compared with hosted probabilities on one 50-pair batch (2026-09-04): 71 of 100 side-measurements, mean absolute difference 0.00062, maximum 0.0273. The capability row is `artifact_available_identity_unknown`, not `parity_passed`: the records state no pass criterion and no verdict, and the audited summary records `inference.revision` null. No other record in the project was cited as a parity audit. | None has run. A two-stack comparison with Causalab is prepared for one case and blocked (below). | None. `scripts/depth_probe.py` support is unverified (`docs/model_matrix.md`). |
| Third route | Hosted attribution graphs, calibrated source set `gemmascope-transcoder-16k`: `artifact_available_identity_unknown` (no model revision, artifact revision or artifact hash is recorded). Hosted server commit not attested. Activation patching supports it (32 landed parts). | Hosted graphs: a two-pair probe landed; source set `transcoder-hp` is not calibrated, so `clinical_mass` stays null. | Not in `medlang_circuits/graph_client.py` `MODEL_REGISTRY`. Not in `scripts/activation_patch.py` `HF_IDS`. |
| Lens artifacts | Hosted J-Lens and logit lens: `artifact_available_identity_unknown`; no lens revision is recorded and the host changed its readouts twice. | Released J++ file: SHA-256 verified locally, fit model and tokenizer revisions unknown, `transport_authorized: false`. Released J-Lens file: advertised hash only. | None recorded. |
| ICA basis | Two names, both `identity unknown`: `sida/icalens-gemma-2-2b-pile10k` in the ICA fork (the matrix row), and `neuronpedia/icalens-gemma-2-2b` in the hosting service's record of 2026-11-10 (26 layers; not in the matrix). No manifest was read (huggingface.co is blocked from development containers). | No basis named. | `neuronpedia/icalens-qwen3.5-2b-pt` in the service's record (6 layers); `artifact_available_identity_unknown`. The service id `qwen3.5-2b-pt` is an unverified alias; hosted inference is off for it. |
| Geometry recorded locally | 26 layers, width 2,304, vocabulary 256,000 (sources in section 4) | 36 layers, width 2,560, vocabulary 151,936 (`data/exploratory/method_sources.v1.json`) | Not recorded, except a 248,320-entry tokenizer |
| Reviewed one-case protocol | None written for this model. The reviewed case's wording is model-independent. | `data/exploratory/qwen3_4b_one_case.v1.json`, `planned_experiment.status: blocked_before_model_execution` | None |
| Runner need | Standard hosted runner. Both lane modes have run on it for this model. | The prepared baseline requires an existing self-hosted Linux runner with 64 GiB RAM, 8 CPUs and 40 GiB free disk. Registered self-hosted runners: 0 (`data/exploratory/baseline_ci_readiness.v1.json`, checked 2026-10-16). | Standard runner; first-probe rate about 60 s per pair on 3 pairs. |
| Other blockers | None beyond section 12. | Causalab execution commit null; Linux runtime unreviewed; no current seal attestation; Causalab's Python licence unresolved; the checkpoint is post-trained and thinking-enabled, not a base model. | Hybrid Gated-DeltaNet and attention architecture: hook-site meaning unverified for any internal method. |

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
fix: for `gemma-2-2b` every lens artifact has unknown identity and no ICA basis manifest
was read, so the milestone is behaviour and parity only.

`qwen3.5-2b-base` is not chosen: no second implementation, no verified internal-method
support, no recorded width, and its ICA link is an unverified alias.

## 3. Exact inputs

No prompt text is quoted in this document. Rows are identified by `(batch, batch_index)` and
by the SHA-256 of the prompt's UTF-8 bytes.

### 3.1 Stage A: 10 rows of one exploration-period batch

`data/simulated/pairs_20260706T175614Z.json`, 10 pairs, file SHA-256
`67b74e6e1e40e39f8c4c79d4cf2599a021fffcfbe712e714d1c25e3899f2b832`. The 20 prompt hashes are
in the table of section 5.

**Split rule and why no row is a Tier B holdout row.** `scripts/tierb_split.py` is the one
implementation. A batch is Tier B when it is a `pairs_<stamp>` batch whose stamp is at or
after `tierb.start_utc` in `ops/dashboard.json`; inside Tier B a pair is holdout when
`sha1(clinical prompt) mod 10 == 0` (Amendment 1). A row of any batch is also sealed when
its clinical prompt is a registered holdout phrase (Amendment 3). This batch's stamp,
`20260706T175614Z`, is before the start stamp `20260710T011438Z`, so the hash rule does not
apply to it; the phrase rule was evaluated for all 10 rows and seals none
(`tierb_split.sealed_pair`, run for this document through the test below; counts only).

**The seal check through the protocol validator.** `validate_protocol` asks
`results_policy.row_restriction` about every family of a non-synthetic protocol. For the
committed protocol (3 of these rows, section 5) the check ran with the real seal and passed:
3 legacy rows checked as rows and 3 colloquial prompts checked as phrases.
`tests/test_first_run_packet.py::test_protocol_validates_and_the_seal_check_runs_on_every_family`
counts those six calls and shows that the same protocol is refused (`holdout_refusal`, with
no prompt text in the message) when a stub reports one row sealed.
`::test_no_family_is_a_tier_b_row` evaluates `sealed_pair` on all 10 rows.

**Review status.** Stimulus class `study_batch`, clinical review `domain_review_pending`,
visibility `public` (`data/results_policy/policy.v1.json`). This is an unsealed
exploration-period batch, not a reviewed set. It is numeric input to an instrument check.
No clinical reading is taken from it and its review status does not change.

Landed inputs the comparison reads:

- hosted: `trace_out/pairs_20260706T175614Z/batch_summary.part_01.json`, 10 results, 1 null
  patient-side value, SHA-256 `66925c49e7e6223193a2c095653c94d794727968a4dd99fa937531bb23b5a552`;
- CPU bfloat16: `trace_out/pairs_20260706T175614Z__gemma-2-2b/batch_summary.part_01.json`,
  10 results, `inference.revision` equal to the pin, SHA-256
  `3f21f073769e27d9ca4c927a624580222c568ea2fcbefe41035c9807151cd105`.

Both parts' prompts are byte-identical to the batch file on all 20 sides (checked by the
test file when it builds the row list).

### 3.2 Stage B: the one reviewed case

| Field | Value |
|---|---|
| Case id | `pw_exploratory_candidate_r001` |
| Family id | `A__cardiology__medication__L14` (review id `r001`, bundle item `vt_216a7dd64eee`) |
| Source | `pilot/runs/pilot_v2_20261002/trace/trace_pairs.json`, index 1 of 40; file SHA-256 `4a6ebb2215d79a41efb92643ebd9fa27cb1e882b2ffc26a98ed384407687c82a` (recomputed for this document) |
| Prompt SHA-256 | source variant `d56a6d92b2937b5cb9b3d9a33a8f7008363b26bf65574c66ee6b258fc4d6ae34`; recipient variant `9d156d56a62cb27cc71f6e122a9edac89ad59dad56ad7b296072ff52f911558d` |
| Split | `discovery`; the file is a pilot source, not a `pairs_<stamp>` batch, so the Tier B hash rule does not apply. A current seal run over it is prerequisite 9. |
| Holdout status | `unsealed_reviewed` |
| Review record | owner review recorded 2026-10-04T03:02:06Z; checker verdict `yes`; `pilot/codebook/review_export_pilot_v2_20261002.json`, sample `r001` |
| Review scope, as recorded | an owner-reviewed brand and generic substitution, not a slang contrast; the source stays a pilot source, not a main-study measurement |
| Seal record | `clean`, recorded 2026-10-04T04:29:45Z, and labelled `stored_bundle_attestation_only_not_a_new_seal_run` |
| Variants | `source` and `recipient`. `normalized_variant.status` is `unavailable`: no approved normalized wording exists in the source bundle. |
| Spec that carries all of this | `data/exploratory/qwen3_4b_one_case.v1.json`, SHA-256 `0d8014ec7395160409bf5afd04d7ef1d4db9cef2ce468cc62173ed89963d9f0d`. It is written for Qwen3-4B. Its case block is reused by identifier; its model block and tolerances are not. |

No prompt text of this case may be copied into a protocol outside the reviewed source files.

### 3.3 Is there a larger adequately reviewed set? No

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

## 4. Model revisions and artifact identities

"Pin file" means a value read from a committed file that the lane reads at run time.
"Landed record" means a value a committed run output records about itself. "Not recorded"
means no file in the two repositories holds the value; the last column says what would.

| Identity | Value | Read from | If not recorded: what would record it |
|---|---|---|---|
| Model repository | `google/gemma-2-2b` | pin file: `scripts/logits_eval.py` `HF_IDS` | — |
| Model revision | `c5ebcd40d208330abc697524c919956e692655cf` | pin file: `scripts/logits_eval.py` `HF_REVISIONS`; landed record: 14 of the 20 landed `trace_out/*__gemma-2-2b` parts record it and 6 record null (counted for this document); the stage A reference part records it | — |
| Tokenizer repository and revision | the same repository and commit | code, not a landed record: both paths call `load_pinned_tokenizer(hf_id, pinned)` (`scripts/logits_eval.py`; `scripts/verify_probs.py` passes that tokenizer to interp-engine). No landed part has a tokenizer field. | a `tokenizer` block in the summary's `inference` record (section 8, item 1) |
| Tokenizer file hashes | not recorded | — | the SHA-256 of `tokenizer.json`, written by the lane at load |
| Weight file hashes | not recorded. The commit pins the repository's content; no local file states a hash of the safetensors files. | — | the repository's file list with LFS SHA-256 at the pinned commit, read once in CI |
| Stage A dtype and backend | float32; interp-engine 1.5.1, eager backend, CPU | fire parameter `dtype`; pin file `constraints.txt` (`interp-engine==1.5.1`); landed record: the four `verify_*` summaries record `interp_engine: 1.5.1` | — |
| Stage B dtype and backend | bfloat16; transformers 5.14.1, CPU | code: `torch_dtype=torch.bfloat16` in `scripts/logits_eval.py`; pin file `constraints.txt`; landed record: the reference part records `transformers: 5.14.1` | — |
| torch, accelerate, numpy | 2.13.0, 1.14.0, 2.4.6 | pin file `constraints.txt`; landed record: `torch: 2.13.0+cpu`, `accelerate: 1.14.0` in the reference part | — |
| Package hashes | not recorded. `constraints.txt` pins versions without hashes. A landed summary records `interp_engine.__version__` only, which does not distinguish a PyPI wheel from a fork commit with the same version (`data/ecosystem/repositories.v1.json`, `patientwords-interp-engine`). | — | hash-checked requirements (`--require-hashes`), or `pip freeze` with wheel hashes written into the summary's environment block |
| Python and runner | Python 3.11 on `ubuntu-24.04` | pin file: header of `constraints.txt`; landed record: `python: 3.11.16` and `runner_image` in the reference part | the run's own values are recorded by the lane at run time |
| Engine commit of the run | not known before the fire | — | the lane records `inference.environment.engine_sha` |
| Layers, width, vocabulary | 26; 2,304; 256,000 | 26 and 256,000: landed record, every hosted-lens record of this model (`meta.layers_by_type`, `done.vocab_size`); 26 also in `docs/activation_patching_design.md:69`. 2,304: the hosting service's ICA release page, record `docs.research-releases.ica-lens` in `data/experiments/neuronpedia_evidence/20261110/index.v1.json`, and the ICA fork's result file (`docs/scaling_plan_20261110.md`, section 3.2). No landed engine run records the width. | a `config` block (hidden size, layer count) in the summary's `inference` record |
| Parameter count | "2.6B", rounded | `docs/model_matrix.md`. The exact count is not recorded. | the same `config` block |
| Hosted reference route (stage A comparator) | service model id `gemma-2-2b`, source set `gemmascope-transcoder-16k`, generation parameters in the part | landed record: the hosted part | — |
| Hosted model revision and dtype | not recorded | — | only the service could attest them; no landed field and no service record read on 2026-11-10 reports a commit (capability matrix, hosted rows) |
| Token ids of the protocol | see section 5 | landed record: hosted-lens records, service model id `gemma-2-2b`. The service records no tokenizer revision. | section 8, item 1 |
| Stage B pairs file | SHA-256 `4a6ebb22…7c82a` | recomputed from the committed file | — |
| Stage B hosted reference | `pilot/traces/trace_pairs/batch_summary.part_01.json`, SHA-256 `3a78536a539b70eecdd1357dbd773560f6418ab40a5abd983ea8c6ba48ac35d2`, `graph_model: gemma-2-2b` | landed record under the pilot root | — |
| Fitted artifacts used by stages A and B | none. Neither stage reads a lens, a basis or a transcoder. The hosted comparator's probabilities are read from the hosted part's `probabilities` field. | — | — |
| ICA basis (section 11 only) | `neuronpedia/icalens-gemma-2-2b` (service record) and `sida/icalens-gemma-2-2b-pile10k` (fork). Repository commit, file hashes, fit model revision, fit tokenizer, preprocessing mode and layer-indexing label: not recorded. | names only: `data/experiments/neuronpedia_evidence/20261110/` and the fork at `aa3b95c9e755e4374f8c9645a064e3f51d96066e` | a read of the basis repository from a machine that reaches huggingface.co (section 11, step S0) |

## 5. Protocol and reproducible preview

### 5.1 What is committed, and what is not

`data/experiments/protocols/first_run_stage_a.protocol.v1.json` is a
`patientwords.experiment-protocol/1` document for stage A: model `gemma-2-2b` at the pin,
backend `cpu_interp_engine`, dtype float32, method `behavior_next_token`, comparison
`clinical` against `colloquial` (the batch's `patient` side), evidence class `unclassified`
(the output is a verify summary, which no policy entry classifies), in no analysis
membership. It passes `cli validate` and plans with `cli plan`.

It covers **3 of the 10 stage A rows**. The validator requires token ids for every prompt
(checked against their own hash) and at least one token id for every target, and it has no
state for a protocol whose ids are pending. No tokenizer file is available offline, so ids
were taken only from landed records:

- **Prompt ids**: the hosted lens service's record for that exact prompt, one
  `pair_NNN_<side>.json.gz` file per prompt under
  `trace_out/pairs_20260706T175614Z__jlens_gemma-2-2b/jlens_raw/`.
  Each record lists one `id` per token; its token strings concatenate to the prompt on all
  20 prompts, and each begins with the BOS id 2 (`prepend_bos: true`). All 20 prompts have
  such a record.
- **Target ids**: no landed artifact records a target's token ids. A target is included
  only when (a) the landed CPU part's label, which is the decoded first token of the
  target, equals the target text, so the target is one token, and (b) a landed hosted-lens
  record of an exploration-period study batch holds a prompt token with exactly that
  string; the id recorded there is used. This joins two records on a token string. It is a
  derivation, not a tokenizer call. In the 982 records read (the hosted-lens records of the
  12 study batches before the Tier B start stamp; 1,172 distinct token strings) no string
  has two ids and no id two strings. No record of a Tier B batch or of a restricted-text
  set was opened.

Rows left out: 6 whose target is more than one token (its full tokenization is on no
record), and 1 whose one-token target has an id on no record. The table below names each.

**What is not verified:** that the hosted service's tokenizer for model id `gemma-2-2b` is
the tokenizer at the pinned revision. The service records no tokenizer revision. The
protocol states the pinned revision as `tokenizer_revision` because that is the tokenizer
the run would load. Section 6.2, precondition 6, says what is done when the ids a run
records differ from the protocol's.

**Not committed, and why:**

- A protocol for all 10 stage A rows. It cannot be completed offline, and the validator has
  no incomplete state, so no partial file for the other 7 rows is committed. The steps that
  complete it are section 8, items 1 and 2.
- A protocol for the stage B case. Three reasons: its prompt text may not be copied outside
  the reviewed pilot source; no landed artifact records token ids for it; and its variants
  are `source` and `recipient`, which are not in the interface's variant vocabulary
  (`clinical`, `colloquial`, `normalized`, `within_register_paraphrase`,
  `changed_fact_control`). Writing it as `clinical` against `colloquial` would mislabel a
  brand and generic substitution.

The protocol file holds the prompt text of its 3 rows, because the validator requires the
text; it is byte-identical to the batch file, which is already public. No family carries the
marker `publication:prompt_text_approved`, so `cli bundle` exports no prompt text from it.

### 5.2 Preview, pinned by `tests/test_first_run_packet.py`

The block below is generated from `data/experiments/protocols/first_run_stage_a.preview.v1.json`
by `python tests/test_first_run_packet.py --write`. The test file rebuilds the protocol and
the preview from the batch file, the landed parts, the hosted-lens records and the
capability matrix, and fails when a committed file or this block differs. The plan hash
depends on the capability matrix: after a reviewed change to the matrix, run the `--write`
command in the same change.

<!-- preview:begin (generated by tests/test_first_run_packet.py --write; do not edit by hand) -->

| Item | Value |
|---|---|
| Protocol file | `data/experiments/protocols/first_run_stage_a.protocol.v1.json` |
| Protocol file SHA-256 | `6ca17d979628c7ac9ced050fe8bcaf1fddc6fa73743f7d73c2b1ec17e1e7571e` |
| Protocol canonical digest (`protocol_sha256`) | `23d1e4cbdf1444e13bf5f915085b85c8456bbaea5ae0cca260a79ae61be91e78` |
| Rows of the batch in the protocol | 3 of 10 |
| Capability matrix file SHA-256 | `55b17316577227d591b2d0e62c0c79aaa5d05505ba6651874179cc3dd934cbfe` |
| Planned tasks | 6 |
| Tasks by planned state | `ready` 0, `unsupported` 0, `unavailable` 6 |
| Plan file SHA-256 | `7ca3ca7e4153a281059c8d5d2206d9f169757212fdf9b53464499cf80e2fd3a6` |
| Plan canonical digest | `38d24b6bb1cfc5fb30837cab64a177f860967f71404f1bfb0cec7a671be8f9b3` |
| Planner token estimate (all tasks; ready tasks) | 125; 0 |
| Planner activation bytes (all tasks) | 0 |
| Planner runtime estimate | null |
| Stage A runner seconds (estimate) | 1062.0 |
| Stage B runner seconds (estimate) | 177.0 |

Reasons the planner gives, with task counts:

- 6 x unavailable: artifact identity unknown: Lowered from parity_passed on 2026-11-10, first to artifact_available and the same day to artifact_available_identity_unknown. The route exists and one run landed; the cited records state no pass criterion and no verdict for this comparison, and the audited summary records no model revision (last sentences of this note), so the row records neither a model revision nor an artifact revision or hash and cannot hold artifact_available. ops/backend_agreement_interp_vs_hosted_20260904.json compares interp-engine 1.5.1 eager CPU float32 with the hosted next-token probabilities on one batch (pairs_20260710T011743Z, 50 pairs, one model). It covers 71 of 100 side-measurements: the hosted route reported no value for 8 clinical and 21 patient sides. Over those 71 the absolute probability difference has mean 0.00062, median 0.0002 and maximum 0.0273, with 1 of 71 above each of the report's thresholds (near 0.01, far 0.02). Over the 29 pairs with a penalty on both sides the maximum penalty difference is 0.027, with 1 of 29 above each threshold. The report has no pass or verdict field. docs/backend_agreement_20260903.md wrote its thresholds before the run for the maximum per-pair penalty difference between interp-engine float32 and the local bfloat16 path (at or below 0.0315, under 0.005, above 0.0315) and calls none of them a pass. Its statement that interp-engine and the hosted values agree to 0.0005, the rounding limit of the hosted three-decimal values, holds for 70 measurements once one row is left out (index 20, patient side, where the hosted path recorded another token's probability); that row was left out after the run. Tokenization parity held on all 100 prompts. The hosted reference route carries the target-read limitation recorded in AGENTS.md. The audited summary (trace_out/verify_pairs_20260710T011743Z__gemma-2-2b) records inference.revision null, so model.revision is null in this row: the run predates enforced pinning. That it loaded the commit pinned later is inferred, not recorded.

Rows by `(batch, batch_index)` and prompt SHA-256 (clinical side; colloquial side):

| Row | In protocol | Reason | Prompt SHA-256 | Tokens |
|---|---|---|---|---|
| `(pairs_20260706T175614Z, 1)` | yes | `every_token_id_on_a_landed_record` | `db5db31fd44fdeec0bba38c840d13d39b781b459dea8fe86a3d1021c9258bd32`; `c3fc29a227ee80439a8f40ffc88b9878d58ac98fd7d6dfed46a36c9a0c443e63` | 19; 19 |
| `(pairs_20260706T175614Z, 2)` | no | `target_is_more_than_one_token_and_its_tokenization_is_on_no_landed_record` | `469500729c0b55053800f5c32e76f2628935c719744bed1e055963dee65952c1`; `d5fb9ed2cf516093f519e156565902785733dee84d869ca2faf80b678fe9158e` | 15; 15 |
| `(pairs_20260706T175614Z, 3)` | no | `target_is_more_than_one_token_and_its_tokenization_is_on_no_landed_record` | `d833183cd913cfb0a0ec8a4f4576e58d95df5b6012b37c5a7d2ae45c32e99cb3`; `b44c8e9607bb1e21094be217a130f3c7ff440502a37e73bdae99c8e385b72927` | 16; 19 |
| `(pairs_20260706T175614Z, 4)` | no | `target_is_more_than_one_token_and_its_tokenization_is_on_no_landed_record` | `d12a56ef23573d111ee10c1a24ddf6f1fa34d890360e1df378a0a38cdd5fff49`; `fb278c3b7a58ad0672aee9ef5bc1cba7d76407ce4bfabec93918ccd894804572` | 20; 22 |
| `(pairs_20260706T175614Z, 5)` | no | `target_is_more_than_one_token_and_its_tokenization_is_on_no_landed_record` | `c08d7e866bea75698215b39fe476832fd6b4dbc5e829a2d2a1d412a0fb52d4e4`; `990f16422e89aab0fe7b17a1d8cde5671e0602cf81f7cab1ad6b54303c07b440` | 18; 20 |
| `(pairs_20260706T175614Z, 6)` | yes | `every_token_id_on_a_landed_record` | `7ecd3989ac2688d06e337cfa7d86498f339fd2cfeafc462675bbd203a61558d3`; `009002365df97266558ed57fbb2d117385fbdaddce4b82ae67706d4e153efdf9` | 22; 22 |
| `(pairs_20260706T175614Z, 7)` | no | `target_is_more_than_one_token_and_its_tokenization_is_on_no_landed_record` | `2e22678d22cea051f1a68997bdec95fb183c5319bff9f3071ba28556920fe552`; `82ec6817a146508211bc868a3a885d682c5ebb8972a4385c8d43043ac6f1843c` | 23; 22 |
| `(pairs_20260706T175614Z, 8)` | no | `target_is_more_than_one_token_and_its_tokenization_is_on_no_landed_record` | `b9b1ca207bad5fb39a09e2844115fd771cfc2ceaea8ed9bc0139fc5ee79ded12`; `0adb722bfbfb48760e7f018ac42224b8be8cb7633726f8784dc638b47b9ea1d5` | 18; 19 |
| `(pairs_20260706T175614Z, 9)` | no | `target_is_one_token_and_its_id_is_on_no_landed_record` | `7a9968a1498092913a683b55ff5df86a55d29a1250fe3263bc3b8f0aa0f34ed1`; `30a3403a841703f90bd60612989b1a42b64982cd6ec31c8872288ffc39c84964` | 21; 21 |
| `(pairs_20260706T175614Z, 10)` | yes | `every_token_id_on_a_landed_record` | `51bd1b1930a7b89e6f5ab9a4c9d4b2e5e64501565124054c2e1b01292ff82b7a`; `6bcdbd8a6837645b8b4eaac6d2b080c8aa72bf36c34bdcbeed0d6b0e27a100a8` | 21; 22 |

Stage A sides compared with the hosted part (`batch_index` side): 2 clinical, 4 clinical, 4 patient, 6 clinical, 6 patient, 7 clinical, 7 patient, 8 clinical, 8 patient. Count: 9 of 20.

Landed hosted part against landed CPU bfloat16 part, absolute difference per side (not a result of the proposed run): 9 comparable sides, maximum 0.0124, mean 0.00476; 10 sides where the hosted part read another token, minimum 0.0109, maximum 0.436, 9 above 0.06.

Hosted-lens records read for token ids: 982 files of 12 batches, 1172 distinct token strings, 0 strings with more than one id, 0 ids with more than one string. Recorded tokens: 394 over the 20 prompts of the batch, at most 23 per prompt; 125 over the 6 prompts of the protocol.

<!-- preview:end -->

The planner's reason is the capability row's own note: the interp-engine route for this
model records no model revision, so its identity is unknown. Every task is therefore
`unavailable`; none is `ready` and none was executed. The planner estimates no runtime
because no measured rate with a sample size exists, and no activation bytes because the
method captures none.

Commands (run for this document; all offline):

```bash
python -m scripts.experiments.cli validate --protocol data/experiments/protocols/first_run_stage_a.protocol.v1.json   # exit 0, status validated, 3 families
python -m scripts.experiments.cli plan --protocol data/experiments/protocols/first_run_stage_a.protocol.v1.json \
  --out /path/outside/the/checkout/plan.json                                                                           # exit 0, 6 tasks
sha256sum /path/outside/the/checkout/plan.json                                                                         # the plan file SHA-256 above
python -m pytest -q -p no:cacheprovider tests/test_first_run_packet.py
```

## 6. Parity criteria, written before any run

The earlier audit (`docs/backend_agreement_20260903.md`,
`ops/backend_agreement_interp_vs_hosted_20260904.json`) recorded thresholds as reading aids
and no pass criterion, and one row was left out after the run. The criteria below name the
comparison sets, the metric, the tolerance and its source, and the three verdicts, before
any run. They are proposals; the owner fixes or amends them when approving, and they are not
changed afterwards. The same sets and thresholds are in the preview file
(`parity_criteria`), so they are part of the pinned record.

### 6.1 A finding that changes the hosted comparison

On 5 of the 10 rows (batch indices 1, 3, 5, 9 and 10) the landed hosted part's recorded
target label differs from the landed CPU part's label. On those rows the hosted
`probabilities` are another token's: the absolute difference between the two landed parts is
between 0.0109 and 0.436 on those 10 sides (9 of them above 0.06), against at most 0.0124 on
the 9 comparable sides. This is
consistent with the hosted-path limitation recorded in `AGENTS.md` for traces before
2026-10-07. The compact audit file `data/audits/target_reads_20261007.json` lists no row of
this batch in `published_rows`; this document did not determine why.
`scripts/backend_agreement.py` joins on index and prompt and does not compare labels, so run
unchanged it would count those sides as disagreements between implementations.

### 6.2 Stage A

Candidate: `trace_out/verify_pairs_20260706T175614Z__gemma-2-2b/verify_summary.part_01.json`.

**Preconditions.** A verdict is given only when all hold; otherwise the verdict is
**inconclusive** and the reason is recorded:

1. Identity: the summary records `inference.revision` and `revision_pinned` equal to
   `c5ebcd40d208330abc697524c919956e692655cf`, dtype float32, `interp_engine` 1.5.1,
   `completed: true` and 10 results with indices 1 to 10.
2. Tokenization: `token_parity.match` is true on all 20 prompts.
3. Same token read: the candidate's target label equals the landed CPU part's label on
   every row.
4. Values: every candidate probability is finite and present on all 20 sides.
5. Fixed references: both reference files have the SHA-256 of section 3.1.
6. Protocol token ids (only if section 8, item 1 is merged before the fire): the token ids
   the run records for the 6 prompts and 3 targets of the protocol equal the protocol's. If
   they differ, the hosted-lens records are not this tokenizer's, the protocol is withdrawn
   and rebuilt from the run's record, and the verdicts below are still given, because they
   do not depend on the protocol.

**Comparison with the hosted part (the parity verdict).**

- Set: the 9 sides on which the hosted part reports a value for the token the CPU part
  read: index 2 clinical, and both sides of indices 4, 6, 7 and 8. The 11 other sides are
  excluded before the run: 10 because the hosted part read another token, 1 because it
  reports no value.
- Metric: absolute difference of the two recorded probabilities, per side.
- Tolerance and its source: recording precision. The hosted part keeps 3 decimals
  (half-width 0.0005) and a verify summary 4 (half-width 0.00005). Two routes that compute
  the same probability therefore differ by at most 0.00055 as recorded, which is 0.0005 on
  the 0.0001 grid such differences fall on. A recorded difference above 0.0010 needs a true
  difference above 0.00045. For orientation only: on 2026-09-04, on another batch and at an
  unrecorded revision, 70 of 71 sides were within 0.0005.
- **Pass:** every one of the 9 sides is at or below 0.0005.
- **Fail:** any of the 9 sides is above 0.0010.
- **Inconclusive:** a side is above 0.0005 and none is above 0.0010. A true difference
  smaller than the hosted record's resolution cannot be excluded or confirmed with a
  3-decimal reference.

**Comparison with the CPU bfloat16 part (secondary; it cannot pass the instrument).**

- Set: all 20 sides. Metric: absolute difference per side; mean and maximum reported.
- Tolerance and its source: observed values, not a derivation. 0.0311 is the largest of
  100 side differences between interp-engine float32 and CPU bfloat16 on
  `pairs_20260710T011743Z` (`ops/backend_agreement_interp_vs_local_20260904.json`; mean
  0.0043). If the 20 new sides and those 100 are exchangeable, the chance that the new
  maximum exceeds the old one is 20 / 120, about 17%, so exceeding 0.0311 alone is weak
  evidence. 0.0630 is twice 0.0315, the largest side difference any earlier comparison of
  the bfloat16 lane recorded; the factor 2 is a choice.
- **Consistent with the earlier audit:** maximum at or below 0.0311.
- **Fail:** any side above 0.0630. Both CPU routes record the same pinned commit, so a
  difference of that size is treated as a defect in one route, not as rounding.
- **Inconclusive:** a side above 0.0311 and none above 0.0630; reported by index and side.

Baseline already on disk, computed for this document from the two landed reference parts
(hosted against CPU bfloat16, the 9 comparable sides): maximum 0.0124, mean 0.0048. It
measures the bfloat16 lane against the hosted route. It is not a result of the proposed run.

**What stage A can and cannot show.** With 9 sides it can confirm or contradict agreement
with the hosted route on this batch at the hosted record's precision. It cannot estimate
agreement in general. It does not separate implementation from precision: the comparison at
equal dtype is not in this packet, because a second verify fire on the same batch and offset
writes the same file name. A pass would support one sentence: at the recorded revision,
interp-engine float32 reproduced the hosted values on 9 sides of one batch to their recorded
precision.

### 6.3 Stage B

Candidate:
`pilot/logits/pilot_v2_20261002/pilot_v2_20261002_trace_pairs__gemma-2-2b/batch_summary.part_01.json`.
Reference: the landed hosted pilot record of the same case,
`pilot/traces/trace_pairs/batch_summary.part_01.json`, index 1 (SHA-256 in section 4). Read
for this document: its prompts equal the pairs-file row, it reports a value on both sides,
and its target label equals the target text, so its read is the target token. Its values are
not quoted here: nothing under the pilot roots is cited as a number.

- Preconditions: the part is `completed` and its single result has index 1; the pairs file
  at the fired commit has SHA-256 `4a6ebb22…7c82a`; the candidate's target label equals the
  reference's; the reference file has its recorded SHA-256. Otherwise: **inconclusive**.
- Metric: absolute difference of the two recorded probabilities, per side (2 sides).
- Tolerance and its source: 0.0315, the largest of 71 side differences between the hosted
  route and CPU bfloat16 on `pairs_20260710T011743Z` (`docs/backend_agreement_20260903.md`).
  Observed, not derived. If the 2 new sides are exchangeable with those 71 and with the 9
  of section 6.2, the chance that either exceeds the earlier maximum is 2 / 82, about 2%.
- **Pass:** both sides at or below 0.0315. **Fail:** a side above 0.0315; no further
  pilot-root fire is proposed until the difference is explained.
- The size and sign of the difference between the two variants is the endpoint, not a parity
  quantity: any value is a completed result (section 6.4).

### 6.4 Stage B endpoint and controls

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

| Control | Status |
|---|---|
| Token parity across implementations | stage A precondition 2 |
| Same token read by both routes | stage A precondition 3 and the fixed comparison set |
| Fixed comparison inputs | the reference parts are named by SHA-256; a different hash at comparison time makes the verdict inconclusive |
| Normalized rewrite | `unavailable`: no approved wording |
| Within-register paraphrase, changed-fact control | `unavailable`: none exists in reviewed material; the one-case spec lists the paraphrase as pending |
| Second seed or replicate | not planned: the read is deterministic on one runner; a replicate would be its own fire and its own approval |

## 7. Resource estimate

Labels are those of `docs/scaling_plan_20261110.md`: [M] measured, [D] derived from
measured, [A] assumption. The time figures are the output of
`scripts/experiments/estimate.py` for the arguments shown; the preview file records the
complete output and the test compares it with a fresh call.

```bash
python -m scripts.experiments.estimate --families 10 --rate gemma-2-2b=88.5 --failed-attempt-fraction 0.15   # stage A: 1,062 runner seconds, 1 leg
python -m scripts.experiments.estimate --families 1  --rate gemma-2-2b=88.5 --failed-attempt-fraction 0.15   # stage B: 177 runner seconds, 1 leg
```

| Item | Stage A (10 pairs, float32, interp-engine) | Stage B (1 pair, bfloat16, transformers) |
|---|---|---|
| Seconds per pair | No rate is recorded for `gemma-2-2b` on the CPU lane, in either mode. [A] proxy: `gemma-2-2b-it`, slowest recorded 88.5 s per pair on the legacy bfloat16 endpoint, model load included ([M], `scripts/backfill_planner.py` `SECONDS_PER_PAIR`; sample size not recorded). Float32 through another implementation may differ in either direction. | same proxy |
| Failed-attempt allowance | 0.15 [A]. The packet proposes one attempt per fire, so this is headroom inside one job, not a retry plan. | same |
| Runner seconds | attempted pairs = ceil(10 x 1.15) = 12; 12 x 88.5 = 1,062 s = 17.7 min [D under A] | ceil(1 x 1.15) = 2; 2 x 88.5 = 177 s [D under A] |
| Input tokens | 394 over the 20 prompts, at most 23 per prompt, BOS included [M], read from the landed hosted-lens records | not recorded (no token record exists for the case) |
| Weights in memory | about 10.4 GB at float32, from the rounded "2.6B" parameter count [D] | about 5.2 GB at bfloat16 [D] |
| Runner | hosted `ubuntu-latest`: 15 GiB physical ([M], one job) plus the workflow's 12 GB swap file. Four float32 verify runs of this model have landed, so the load fits; its peak memory was not recorded. | same runner; 20 logits parts have landed |
| Output size | about 18 kB: the landed 50-pair verify summary is 90,398 bytes, 1,808 per result [D] | about 2.6 kB: the landed 10-result reference part is 25,979 bytes [D] |
| Activations, full-vocabulary logits | none stored; the lane keeps four-decimal probabilities and a top-k list | none stored |
| Planner estimate for the committed protocol | 125 tokens over 6 tasks, 0 activation bytes, runtime null (section 5.2) | no protocol |
| Job ceiling | 240 minutes, `max-parallel` 2 | same |
| Provider budget | $0 | $0 |

One weak timing record exists for stage A's shape: the 2026-09-04 verify fire of 50 pairs was
resolved in the journal 7.2 minutes after it was fired. Whether that resolve followed the
landing is not recorded, so it is not used as a rate.

Not measured, and what would measure it: model load time, peak resident memory and
seconds per pair for this model in each mode. The lane records none of them. Section 8,
item 1 adds the timing fields; peak memory needs one more line there.

## 8. Implementation changes needed before the run

Each item is a reviewed pull request. Sizes are estimates made by reading the files they
touch; item 3 was written on 2026-11-11 and the others were not. Item 3 lets stage A's
verdict be computed by code. Items 1 and 2 are needed for the protocol to be completed and
for load and measurement seconds to be recorded; stage A's verdict does not depend on them. Item 4 is needed for stage B. Items 5 and 6 are
needed only to bring a landed result into the experiment interface and are not needed for
the two fires.

| # | Change | Files | Size (estimate) | Without it |
|---|---|---|---|---|
| 1 | The verify and logits paths record, per side, the prompt's token ids, and per result the target's full token ids; the summary's `inference` block records the tokenizer repository and revision, the SHA-256 of `tokenizer.json`, the model's layer count and hidden size, and wall seconds for load and for measurement. Fields are added; no existing field changes. | `scripts/verify_probs.py`, `scripts/logits_eval.py`, `tests/test_verify_probs.py`, a new test file for the logits path | about 40 lines of code, 80 of tests | The protocol's token ids cannot be checked against the pinned tokenizer, the 7 remaining rows cannot be added to the protocol, and no rate is recorded. Stage A's hosted verdict can still be given. |
| 2 | The completion step: after stage A lands, `python tests/test_first_run_packet.py --write` reads token ids from the landed verify summary in place of the hosted-lens records, and the protocol then covers all 10 rows. A new protocol version, a new plan hash. | `tests/test_first_run_packet.py` (the builder), `data/experiments/protocols/` | about 40 lines | The protocol stays at 3 rows with ids from the hosted service's tokenizer. |
| 3 | **Done 2026-11-11.** The comparison sets aside a side whose two target labels differ, takes the comparison set and thresholds from the preview file, and writes a `verdict` block (`pass` or `consistent`, `fail`, `inconclusive`) with every precondition and its outcome. A precondition that fails or cannot be checked gives `inconclusive`. | `scripts/backend_agreement.py` (`--criteria`, `--comparison`), `tests/test_backend_agreement.py` | 150 lines of code, 120 of tests | Not applicable. Checked without a model: on the two landed reference parts, with a candidate assembled from the landed CPU rows, the script reproduces the baseline of section 6.2 (9 sides, maximum 0.0124, mean 0.00476) and returns `fail` for it, as the criteria require of a bfloat16 candidate. |
| 4 | The run-named copy of run 2's pairs file (`pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json`), written by `pilot/analysis/trace_pairs.py`, and a current seal run over it. | one new file under `pilot/`; no code | 1 file | The lane refuses the stage B fire: run 2's legacy file name is not accepted under the pilot root. |
| 5 | A route by which the interface accepts a result that was measured elsewhere. Today the planner marks every task on a non-fixture backend `unavailable`, and `collect` refuses a completed envelope for a task that is not planned `ready` (`plan_state_conflict`). Needed: a planned state or backend class for "import from a landed part", a `run-import` command, and an adapter that reads a landed `verify_summary` or `batch_summary` part by path and SHA-256 into a `behavior_next_token/1` payload. A legacy part records a 4-decimal probability and a top-k list, not a full-vocabulary rank, so the payload kind must allow `raw_rank` null with a `not_recorded` entry, or a second payload version is needed. | `scripts/experiments/planner.py`, `scripts/experiments/cli.py`, `scripts/experiments/store.py`, a new `scripts/experiments/adapters/behavior_landed_part.py`, `scripts/experiments/adapters/__init__.py` (one line), `schemas/experiments/`, tests | about 400 lines of code, 400 of tests | A landed stage A result stays a `verify_summary` file. It has no envelope, no comparison block and no bundle, and the site's experiments page lists nothing. A test of this adapter on a mocked part would not be evidence of real-model agreement. |
| 6 | After stage A lands: a capability row for `gemma-2-2b` at the pin, `behavior_next_token`, `cpu_interp_engine`, float32, citing the landed file by path and SHA-256 and the verdict under section 6. The status is `artifact_available` if the revision is recorded, and `parity_passed` only on a pass. | `data/experiments/capability_matrix.v1.json`; then the `--write` command of section 5.2 | about 25 lines | The plan keeps saying `artifact identity unknown` for this route. |

**What the lane writes, and where.**

| Output | Path | Read by a measurement collector? | Results catalogue at the next publish |
|---|---|---|---|
| Stage A | `trace_out/verify_pairs_20260706T175614Z__gemma-2-2b/verify_summary.part_01.json` | No. Collectors and the catalogue's row export read `batch_summary*.json` only (`AGENTS.md`, research invariants; `scripts/export_results_catalogue.py`). No statistic can move. | One new run entry with no rows and no numbers, as the two landed `verify_pairs_*` directories are listed today in the site's `data/results_catalogue/index.json`: `n_parts` 0, `other_artifacts.verify_summary` 1, stimulus class and evidence class `unclassified`, visibility `public`, 0 parts in each of the three memberships. |
| Stage B | `pilot/logits/pilot_v2_20261002/pilot_v2_20261002_trace_pairs__gemma-2-2b/batch_summary.part_01.json` | No. No collector reads `pilot/`. | Not listed: the catalogue reads `trace_out/` only. `pilot/logits/` has no landed run, so this would be the first use of that root. |
| Comparison reports (section 9.3) | a directory outside the repository | No | Not listed |
| Interface plan, run directory, bundle | a directory outside every checkout; the interface's writers refuse `trace_out`, `data`, `pilot`, `ops` and any path inside a checkout (`docs/experiment_interface/README.md`, *Where output may go*) | No | Not listed. The site's experiment index lists a bundle only after a reviewed exporter writes it into the site's `data/`; that exporter does not exist (`docs/experiment_interface/preview.md`). |

The lane has no other output location for `mode: verify`: under the pilot root it refuses
every mode except `logits` (`docs/triggers.md`). The catalogue entry for stage A is therefore
a consequence of the fire and is decision 3 in section 14.

## 9. Execution route, approvals and proposed commands

**Route.** The existing `logits-eval` lane, fired through `scripts/fire_trigger.py`. The
manual route of pull request 121 is not used: it is `exploratory_baseline_preflight.yml`,
prepared for the Qwen3-4B one-case baseline with Causalab, it needs a registered self-hosted
runner (0 exist), and its exception covers preparing that route, not dispatching it and not
another model.

**What existing approvals cover.**

| Record | Covers | Does it cover these fires? |
|---|---|---|
| `docs/routine_standing_prompt.md`, step 3e (owner-approved 2026-10-09) | One `logits-eval` backfill leg per cycle, as printed by `scripts/backfill_planner.py --campaign`; `mode: logits`, default root; "nothing else" | No. A `mode: verify` fire and a pilot-root fire are not legs the planner prints. |
| `AGENTS.md`, *Execution model*, owner exception (pull request 121) | Preparing the one-case manual route of `docs/exploratory/baseline_ci.md` | No. Preparation only, another workflow, another model. |
| `docs/decisions_20261014_owner.md`, three rounds | Named Jev, Petri, equity and re-judge work; "no fires until I approve"; "No fires beyond what I picked above" | No. None names a `logits-eval` fire for this purpose. |
| `docs/open_results_policy.md` (2026-11-10) | What is shared and what joins a statistic | No. It is not an execution approval. |

**What new approval is needed.** The questions are in section 14: two fires (decisions 1
and 2), each $0 of provider spend and one job of at most 240 minutes, each one first
attempt; the criteria of section 6 (decision 4); the catalogue consequence (decision 3).

None of the commands in 9.1 to 9.3 has been run. `scripts/fire_trigger.py` was not executed
in any form while this packet was written, including `--dry-run`. The fire parameters were
checked by reading `KNOWN_KEYS` for `logits-eval`, the workflow's params job and
`docs/triggers.md`; they were not validated by the script. The first command to run after
approval is each fire command with `--dry-run` added.

### 9.1 Preparation, by reviewed pull request — NOT RUN

```bash
# NOT RUN. Writes the run-named copy of run 2's pairs file, byte-identical by the 2026-10-05 check.
python pilot/analysis/trace_pairs.py --run-dir pilot/runs/pilot_v2_20261002 --review-sample
sha256sum pilot/runs/pilot_v2_20261002/trace/trace_pairs.json \
          pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json

# NOT RUN. Holdout seal: the default sweep plus the run's trace directory (--extra replaces the default list).
python scripts/seal_check.py --site ../patientwords \
  --extra docs,ops,data/verification,pilot/runs/pilot_v2_20261002/trace
```

Items 1 and 3 of section 8 are their own pull requests with tests; they have no command
here because they are not written.

### 9.2 Execution, only after approval, on `main`, lane idle — NOT RUN

```bash
# NOT RUN. Stage A: fresh float32 parity at the pinned revision. $0.
python scripts/fire_trigger.py fire --trigger logits-eval \
  --params '{"models": "gemma-2-2b", "pairs_file": "data/simulated/pairs_20260706T175614Z.json", "mode": "verify", "dtype": "float32", "limit": "10", "offset": "0", "commit_outputs": "true"}' \
  --note "Stage A of docs/exploratory/first_model_run_packet_20261110.md: gemma-2-2b interp-engine float32 parity at the pinned revision"

# NOT RUN. After stage A has landed, been resolved, and not failed under section 10. Stage B: the reviewed case. $0.
python scripts/fire_trigger.py resolve --trigger logits-eval
python scripts/fire_trigger.py fire --trigger logits-eval \
  --params '{"models": "gemma-2-2b", "pairs_file": "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json", "mode": "logits", "output_root": "pilot/logits", "limit": "1", "offset": "0", "commit_outputs": "true"}' \
  --note "Stage B of docs/exploratory/first_model_run_packet_20261110.md: reviewed case r001 on the legacy endpoint, pilot root"

# NOT RUN. After stage B has landed: resolve, then restore the lane's no-op default.
python scripts/fire_trigger.py resolve --trigger logits-eval
python scripts/fire_trigger.py park --trigger logits-eval
```

Expected landing paths, both absent today (checked with `ls`, and by the test file):

- `trace_out/verify_pairs_20260706T175614Z__gemma-2-2b/verify_summary.part_01.json`
- `pilot/logits/pilot_v2_20261002/pilot_v2_20261002_trace_pairs__gemma-2-2b/batch_summary.part_01.json`

The fires are chained, never stacked: the lane holds one running and one pending run, and a
third push evicts the pending one silently. The scheduled backfill uses the same concurrency
group every 12 hours without the journal's queue guard, so the lane must be idle and the
fire placed outside a cron slot. Follow the repository's `fire-trigger-safe` and
`harvest-resolve` procedures.

### 9.3 After landing, offline — NOT RUN

```bash
# NOT RUN. interp-engine float32 against hosted, then against CPU bfloat16.
# Each --out is a new file in a directory outside the repository.
python scripts/backend_agreement.py \
  --reference trace_out/pairs_20260706T175614Z \
  --candidate trace_out/verify_pairs_20260706T175614Z__gemma-2-2b \
  --criteria data/experiments/protocols/first_run_stage_a.preview.v1.json --comparison hosted \
  --out /path/outside/the/repository/interp_fp32_vs_hosted.json
python scripts/backend_agreement.py \
  --reference trace_out/pairs_20260706T175614Z__gemma-2-2b \
  --candidate trace_out/verify_pairs_20260706T175614Z__gemma-2-2b \
  --criteria data/experiments/protocols/first_run_stage_a.preview.v1.json --comparison cpu_bfloat16 \
  --out /path/outside/the/repository/interp_fp32_vs_local_bf16.json
```

Each report's `verdict` block is the verdict of section 6.2: the 9 named sides for the
hosted comparison, all 20 for the bfloat16 comparison, with the preconditions listed and
their outcomes (item 3 of section 8, done 2026-11-11). The report's older summary fields
still count every joined side and are not the verdict. The parity
record that follows states both environments, the batch by stem and index, the dtype, each
precondition, the per-side differences on the named set, the verdict, and what was not
compared (`docs/upgrade_checklist.md` section 6). `verify_summary` files stay outside the
measurement collectors by design, so no published statistic moves.

### 9.4 Run for this document (offline, read-only)

```bash
python -m scripts.experiments.cli capabilities --model gemma-2-2b          # exit 0; 6 rows
python -m scripts.experiments.cli capabilities --model qwen3.5-2b-base     # exit 0; 2 rows
python tests/test_first_run_packet.py --write                              # wrote the protocol, the preview and the block of section 5.2
python -m pytest -q -p no:cacheprovider tests/test_first_run_packet.py     # result in the completion report of this change
```

## 10. What would count as failure

Execution outcomes are kept apart from parity verdicts.

Stage A **did not execute**, and stage B is not fired, if the job does not finish, the model
does not load, or the loader's revision check refuses.

Stage A **fails**, and stage B is not fired, if the hosted comparison of section 6.2 fails,
or the bfloat16 comparison fails.

Stage A is **inconclusive** if a precondition of section 6.2 does not hold or either
comparison is inconclusive. Stage B may then be fired only if the owner says so after
reading the record; the approval of decision 2 does not cover that case.

Stage B **fails** if any of these holds:

- the cell's fail-closed seal check is not clean (the cell then commits nothing);
- no part lands, the part is not `completed`, or its single result is not index 1;
- the pairs file's SHA-256 at the fired commit is not `4a6ebb22…7c82a`;
- the comparison of section 6.3 fails.

Not a failure: any size or sign of the stage B difference between variants.

A failure or an inconclusive verdict is recorded with its artifacts and reported. It is not
re-fired to look for a pass. Each approval covers one first attempt per fire, the rule the
manual baseline route already uses (`docs/exploratory/baseline_ci.md`, retry limits). A new
attempt needs a new approval.

## 11. Smallest next step that exercises a real activation capture and a fitted basis through the viewer

**The two behaviour checks do not demonstrate the ICA integration.** Stages A and B read
next-token probabilities. They capture no activation, load no basis and produce no
`ica_scores/1` payload. The ICA adapter (`scripts/experiments/adapters/ica.py`) has scored
only toy activations of width 8 under a hand-written basis
(`docs/experiment_interface/ica_adapter.md`). Nothing in this section is proposed for
approval now; it describes the smallest step and what it would and would not establish.

### 11.1 Model and basis

**Model: `gemma-2-2b`**, the same model and pin as stages A and B.

| | `gemma-2-2b` | `qwen3.5-2b-base` |
|---|---|---|
| Hosted ICA source set (service record of 2026-11-10) | `icalens-res`, 26 layers (0 to 25), hook `blocks.{layer}.hook_resid_post`, basis repository `neuronpedia/icalens-gemma-2-2b`, hosted inference on | `icalens-res` under the service id `qwen3.5-2b-pt`, 6 layers (0, 4, 8, 12, 16, 20), basis repository `neuronpedia/icalens-qwen3.5-2b-pt`, hosted inference off |
| Basis named by the ICA fork | `sida/icalens-gemma-2-2b-pile10k` | none (the fork names bases for Qwen3.5-9B-Base and for the instruct checkpoint `Qwen/Qwen3.5-2B`) |
| Width recorded | 2,304 | 2,048, in the service's release page only |
| Capture route in the engine | none written; the model loads in the CPU lane today and its block structure is the standard one the fork's format describes | none written; hybrid architecture, hook-site meaning unverified (`docs/model_matrix.md`) |
| Policy cohort | registered cohort | post-registration exploratory |
| Token ids on record for study prompts | yes, 3 complete families (section 5) | none |

`gemma-2-2b` needs one new thing, a capture, where `qwen3.5-2b-base` needs a capture, a
check of what `resid_post` means in a hybrid block, a width record and a verified checkpoint
behind the service alias. A hosted cross-check is possible in principle only for
`gemma-2-2b`, because hosted inference is off for the other.

**Basis: the layer-12 basis of the repository the hosting service names,
`neuronpedia/icalens-gemma-2-2b`** (folder `blocks.12.hook_resid_post`), or the same layer
of `sida/icalens-gemma-2-2b-pile10k` if step S0 shows the two hold the same tensors. One
layer, fixed here before any read so that it is not chosen on results. Layer 12 is a choice
without evidence behind it: both sources list every layer from 0 to 25.

### 11.2 What identity is verified, and what is not

Verified from committed records (`data/experiments/neuronpedia_evidence/20261110/`, read on
2026-11-10 by another task of this change set; this document re-read the records, not the
service):

- the service lists source set `icalens-res` for model id `gemma-2-2b`, 26 sources, each
  naming repository `neuronpedia/icalens-gemma-2-2b` and a folder per layer, with the
  dashboard dataset `monology/pile-uncopyrighted`;
- its model record names `google/gemma-2-2b`;
- its release page states 26 layers and 2,304 directions per layer;
- no record read reports a model commit, a basis repository commit or a hash.

Verified from the ICA fork at `aa3b95c9e755e4374f8c9645a064e3f51d96066e` (checkout read for
this document):

- `experiments/reconstruction/official/results/gemma2/run.json` records, for a
  reconstruction evaluation with lens `sida/icalens-gemma-2-2b-pile10k`, `model_id`
  `google/gemma-2-2b` and `model_revision` `c5ebcd40d208330abc697524c919956e692655cf`, which
  is the study pin, and all 26 layers. That is the model commit the evaluation loaded. It is
  not a record of the commit the basis was fitted on.
- `notes/artifact-format.md` says a saved artifact records the fitted checkpoint revision.
  Whether the published artifact does was not read.

Not verified, and not obtainable from a development container (huggingface.co is refused by
the proxy; `data/experiments/representation_registry.v1.json`, `sources_not_read`):

- the commit of either basis repository, its file list and the SHA-256 of each tensor file;
- whether `neuronpedia/icalens-gemma-2-2b` and `sida/icalens-gemma-2-2b-pile10k` hold the
  same tensors;
- the content of `icalens.json`: the fit model revision, the preprocessing mode, the
  layer-indexing label (the fork uses two: `hidden_states` and
  `hidden_states_without_initial_embedding_state`), the number of components, the fit
  settings and seed;
- the tokenizer the fit used (the artifact format has no tokenizer field) and the model-load
  precision of the fit;
- the licence of the weights and of the fit corpus.

If the artifact records no model revision, or the string `unknown`, the adapter gives no
score by design: the task ends `unavailable` with a reason that starts `unknown_identity`.
That outcome is a completed answer to the identity question, not a defect.

### 11.3 The steps

| Step | What | Where it runs | Cost |
|---|---|---|---|
| S0 | Read the basis repository's commit, file list with sizes and LFS SHA-256, and `icalens.json`, for both repository names. No model is loaded and no tensor is downloaded. Commit the result as an evidence record in the form of `data/experiments/neuronpedia_evidence/`. | a machine that reaches huggingface.co: the owner's, or a CI step. No existing lane has such a step. | $0; seconds |
| S1 | Capture the residual stream after block 12 (`resid_post`), all positions, for the 6 prompts of the committed protocol (125 tokens), at the pinned model and tokenizer, into an ActivationDataset v1 with the PatientWords row provenance and file pins. | CI, CPU, standard runner; a new script and a lane step, both by reviewed pull request | $0; about the cost of stage B plus one model load |
| S2 | Download the layer-12 basis files at the commit S0 recorded, build the basis manifest (`patientwords.ica-basis-manifest/1`), and score the 6 prompts with the existing ICA adapter. | CI for the download; the scoring is offline arithmetic on files | $0 |
| S3 | Collect, compare, bundle, and open the bundle in the experiments page through `scripts/check_experiment_preview.py`'s temporary site copy, or through a reviewed exporter if the owner wants it on the site. | offline | $0 |

Sizes, derived from recorded counts ([D]): the capture is 125 x 2,304 x 4 bytes = 1.15 MB at
float32 for one layer (29.95 MB for all 26). One layer of a full-width basis is two
2,304 x 2,304 float32 matrices and a center vector, about 42.5 MB, if the published basis has
2,304 components as the service's page states. The fit workspace formula does not apply:
nothing is fitted.

The capture needed, exactly: format `ActivationDataset v1` as written by
`scripts/experiments/activation_dataset.py`; `activation_site` and `layer_indexing` equal,
as strings, to the basis artifact's own values (known only after S0); one row per token
position of each of the 6 prompts; `samples.safetensors` with `document_index`, `position`
and `token_id`; `provenance.patientwords` with the tokenizer id and 40-hex revision, the
position policy `all`, and one document entry per prompt with role `protocol_variant`, split
`discovery`, family, variant, token count and token hash; file pins
(`patientwords_files`). The fork's own `icalens capture` command cannot produce it in CI: it
requires a CUDA device (`src/icalens/cli/capture.py`).

### 11.4 Checks that would have to pass

1. `activation_dataset.validate_activation_dataset`: complete, dimensions, finite values,
   file pins `verified`, and every row's token id equal to the protocol's token id at that
   position. This also tests the protocol's hosted-lens token ids against the pinned
   tokenizer.
2. Identity `recorded` on both sides: model id, 40-hex model revision, tokenizer id and
   40-hex tokenizer revision in the dataset and in the basis manifest, and a model revision
   in the artifact itself equal to the pin.
3. Capture site and layer-indexing label equal to the artifact's (`layer_metadata`).
4. Preprocessing mode equal in the artifact, the manifest and the protocol
   (`preprocessing_mismatch` otherwise).
5. Every basis file's SHA-256 equal to the manifest's (`artifact_hash`).
6. The split-leakage report, with its words stated as they come out. For a published basis
   fitted on an external corpus the expected words are `not_listed_in_manifest` and
   `fit_dataset_not_supplied`, not `checked`.
7. A capture-indexing check that the engine does not have yet: the captured vector of the
   last block (layer 25), passed through the model's final normalization and unembedding,
   reproduces the same run's next-token logits. This shows that "layer k" means the output
   of block k at the top of the stack. It does not show it for layer 12.
8. The numpy path and the `icalens` path agree within 1e-9 where `icalens` is installed;
   where it is not, the payload records that only the numpy path ran.
9. The planner route of section 8, item 5, in the form the ICA method needs: today a task on
   a non-fixture backend is planned `unavailable`, so `run-fixture` would not score a real
   capture. The scoring is offline arithmetic, but the plan has no state that says so.
10. The bundle validates and the page renders it with its labels: not synthetic, the
    identity status, the hypothesis status of any component label.

### 11.5 What the step would and would not establish

It would establish that a real capture and a published basis pass through the dataset
validator, the identity checks, the adapter, the store, the bundle and the page, with every
identity field either recorded or listed as missing.

It would not establish:

- **that the capture is the activation the basis was fitted on.** With 2,304 components at
  width 2,304 the reconstruction error is near zero for any vector, so it cannot show that
  the site, the layer or the preprocessing is right. Check 7 covers the top layer only.
- **agreement with the fork's own capture path.** That path needs CUDA and was not run. The
  fork loads the model in bfloat16 on CUDA and in default precision on CPU, and a lens stores
  neither fact (`docs/experiment_interface/ica_adapter.md`).
- **agreement with the hosting service.** Hosted inference is on for this source set, but no
  record read says whether the service's activation value is the signed ICA score under the
  artifact's preprocessing. A comparison would first need that definition.
- **any meaning of a component, or any clinical statement.** Three study rows, one layer, no
  profile, no label, no test.

Approvals it would need, none requested now: S0 if it runs in CI; a reviewed pull request for
the capture script and its lane step; one $0 fire for S1 and S2 with a runner-time ceiling of
one 240-minute job.

## 12. Prerequisites

| # | Prerequisite | Status | Evidence | Rule or missing authorization |
|---|---|---|---|---|
| 1 | Model and tokenizer pinned to one commit | met | `scripts/logits_eval.py` `HF_REVISIONS`; `docs/model_matrix.md`, pinned revisions; section 4 | — |
| 2 | Both lane modes have run for this model on a standard runner | met | 20 logits parts; four float32 `verify_*` summaries (read for this document) | — |
| 3 | The chosen parity batch is outside the Tier B seal | met | stamp before `20260710T011438Z`; 0 sealed rows by `tierb_split.sealed_pair`; the validator's seal check passes on the committed protocol (section 3.1) | `AGENTS.md`, research invariants: preserve holdout seals |
| 4 | No landed artifact would be overwritten | met | neither landing path exists; the earlier audit's batch is not reused because a new verify fire there would replace `trace_out/verify_pairs_20260710T011743Z__gemma-2-2b/verify_summary.part_01.json` | `AGENTS.md`: landed `trace_out/` summaries are measurements, not caches |
| 5 | The lane and its keys exist; no new lane or secret is needed | met | `docs/triggers.md`, `logits-eval` row: `mode`, `dtype`, `output_root` | A new lane or key set would need its own reviewed pull request (`docs/agent_reference.md`, execution and operations). |
| 6 | One reviewed, unsealed case | met for one case | section 3.2; owner review of 2026-10-04 | Its seal record is a stored attestation, not a new seal run (row 9) |
| 7 | Execution approval that names these fires | **not met** | Section 9: no existing record covers them | `AGENTS.md`, *Execution model*: fire only through `scripts/fire_trigger.py`, never merely to test docs. `docs/agent_reference.md`: operational preparation is not new authorization to spend or publish. |
| 8 | Parity criteria fixed before the run | **not met** | Section 6 holds proposals, pinned in the preview file as `proposed_before_any_run_not_approved` | Owner decision 4 |
| 9 | A current holdout seal check over the inputs | **not met** | The case's seal record is `stored_bundle_attestation_only_not_a_new_seal_run`, dated 2026-10-04. For the stage A batch the seal was evaluated for this document (section 3.1). | `AGENTS.md`: preserve holdout seals; the pilot cell also runs a fail-closed seal check before it commits |
| 10 | The run-named pilot pairs file | **not met** | `pilot/runs/pilot_v2_20261002/trace/` holds `trace_pairs.json` and its meta file only | `docs/triggers.md` and `docs/pilot_runs.md`: under the pilot root the file must be `pilot/runs/<run_id>/trace/<run_id>_<name>.json`; run 2's legacy name is refused |
| 11 | A complete `patientwords.experiment-protocol/1` document for both checks | **not met**; partly met for stage A | 3 of 10 stage A rows are committed and validate (section 5). The other 7 and the stage B case have none. | `AGENTS.md`, *Execution model*: the sandbox proxy blocks huggingface.co; section 8, items 1 and 2 |
| 12 | A route from a landed legacy part to a typed envelope | **not met** | `scripts/experiments/planner.py` marks every non-fixture task `unavailable` by design; `scripts/experiments/adapters/` holds fixture, readout-report and ICA adapters | Section 8, item 5. Not needed for the two fires. |
| 13 | The pinned interp-engine load path has run against the real package | **not met** | All landed interp-engine summaries record `revision` null; the only tests replace the package with a fake | Not a rule. A risk: stage A is the first real execution and may fail at load. |
| 14 | A fresh parity result at a recorded revision | **not met** | Capability matrix, `cpu_interp_engine` row | This is what stage A produces |
| 15 | A reviewed set larger than one case | **not met** | Section 3.3 | `AGENTS.md`, known limitations: do not base a study claim on one pair's penalty or flip label. Not needed for this packet; needed for the next. |
| 16 | A comparison that reads target labels and writes the verdict | **not met** | `scripts/backend_agreement.py` joins on index and prompt only (section 6.1) | Section 8, item 3. Without it the verdict is taken by hand from the named sides. |
| 17 | The run records token ids, tokenizer identity and timing | **not met** | No landed summary has those fields (section 4) | Section 8, item 1 |
| 18 | The lane is idle and no cron leg is pending | to check at fire time | The scheduled backfill shares the concurrency group | `docs/triggers.md`: one running and one pending; chain, never stack |

Lens, ICA and J++ identity are not prerequisites of this packet. They stay `unavailable`
until their publishers' records or a manifest read settle them
(`docs/exploratory/lens_fit_provenance_question.md`; section 11, step S0).

## 13. What this packet did not verify

- No model was loaded. Every resource figure is an estimate with a proxy rate.
- No tokenizer was run. The protocol's token ids are the hosted service's records and one
  string join; their equality with the pinned tokenizer's ids is not established.
- The fire parameters were read against the lane's key set and params job, not validated by
  `scripts/fire_trigger.py`.
- That `pilot/analysis/trace_pairs.py` still writes a byte-identical run-named file was not
  re-run; the 2026-10-05 check is the record.
- `pilot/logits/` has no landed run, so stage B would be the first use of that output root.
- Why the hosted part read another token on 5 rows was not traced to a rule of the hosted
  path; the finding is the label difference and the size of the value difference.
- The catalogue's treatment of a verify directory was read from the two existing entries in
  the site's committed index, not by running the exporter on a new directory.
- The capability matrix was read at one moment; the preview's plan hash is tied to that
  file's content and the test fails when it changes.
- No basis repository, no `icalens.json` and no tensor was read. The hosting service was not
  queried for this document; its committed records of 2026-11-10 were read.
- Whether hosted runners remain free of charge for this repository is the project's dated
  record (`docs/model_matrix.md`, cost truth), not a fresh account check.
- The size estimates of section 8 were made by reading the files; no item was implemented.

## 14. Decisions that need the owner

**The one request that starts anything (2026-11-11).** Approve one first attempt of the
stage A fire, with the criteria of section 6.2 fixed as written.

| | |
|---|---|
| Workload | one `logits-eval` job, `mode: verify`, 10 public rows (20 prompts) of `data/simulated/pairs_20260706T175614Z.json` |
| Measured endpoint | full-vocabulary probability of the first target token, float32, interp-engine 1.5.1, CPU |
| Model and inputs | `google/gemma-2-2b` at `c5ebcd40d208330abc697524c919956e692655cf`, tokenizer from the same commit; batch file and both reference parts at the SHA-256 values of section 3.1 |
| Budget basis | $0 provider spend; one job of at most 240 runner minutes; estimate 17.7 minutes from a proxy rate on another model (an assumption, section 7) |
| Acceptance | `scripts/backend_agreement.py --criteria ... --comparison hosted`: `pass` when all 9 named sides are at or below 0.0005, `fail` when any is above 0.0010, `inconclusive` otherwise or when a precondition does not hold |
| Consequence you accept with it | the results catalogue lists the stage A directory at the next publish, with no rows and no numbers (decision 3) |

It demonstrates that the pinned model, the lane and the comparison work on real weights. It
cannot demonstrate the ICA hypothesis, clinical validity or throughput at scale. Decisions 1,
3 and 4 below are this request. Decisions 2, 5, 6 and 7 do not block it and can wait for its
result. The experiment it prepares is `docs/protocols/instrument_register_experiment_20261111.md`.

Each is a yes or no. Declining all of them changes nothing in either repository.

1. **Do you approve one first attempt of the stage A fire as written in section 9.2?**
   `logits-eval`, `mode: verify`, `gemma-2-2b`, float32, the 10 rows of
   `pairs_20260706T175614Z`. Section 8 item 3 is done; item 1 is not, so the run records no
   load or measurement seconds and precondition 6 of section 6.2 is not evaluated. Cost ceiling: $0 of provider spend; one
   job of at most 240 runner minutes (estimate 17.7).
2. **Do you approve one first attempt of the stage B fire as written in section 9.2,
   conditional on stage A not failing and not being inconclusive under section 10?**
   `logits-eval`, `mode: logits`, pilot root, the one reviewed case, after the run-named
   pairs file and a current seal run (section 8, item 4). Cost ceiling: $0 of provider
   spend; one job of at most 240 runner minutes (estimate 3.0).
3. **Do you accept that the public results catalogue lists the stage A directory at the next
   publish, with no rows and no numbers?** If no, stage A cannot use the existing lane, and a
   reviewed change to the lane's output location is needed first. Cost ceiling: none; no
   spend either way.
4. **Do you fix the parity criteria of section 6 as written?** The hosted set of 9 named
   sides with pass at or below 0.0005, fail above 0.0010 and inconclusive between; the
   bfloat16 comparison with 0.0311 and 0.0630; the stage B comparison with 0.0315. If you
   amend a number, it is changed in `tests/test_first_run_packet.py` and the preview is
   regenerated before the first fire. Cost ceiling: none.
5. **Do you accept a protocol that holds the prompt text of 3 public study rows under
   `data/experiments/protocols/`, with token ids taken from hosted-lens records and one
   string join?** If no, the protocol and preview files are removed, the generated block of
   section 5.2 goes with them, and the packet has no interface protocol until a run records
   token ids. Cost ceiling: none.
6. **Should section 8, item 5 (the import route into the experiment interface) be built
   before the fires?** It is not needed for them. If yes, the fires wait for about 800 lines
   of reviewed code and tests; if no, a landed result stays a `verify_summary` file and the
   experiments page lists nothing. Cost ceiling: none.
7. **Should step S0 of section 11 be done now?** A read of the two ICA basis repositories'
   commit, file hashes and `icalens.json` from a machine that reaches huggingface.co, yours
   or a CI step, committed as an evidence record. Nothing is loaded or fitted. It settles
   whether the ICA step of section 11 can produce a score at all. Cost ceiling: $0; if run
   in CI, one job of a few minutes on a workflow step that does not exist yet.
