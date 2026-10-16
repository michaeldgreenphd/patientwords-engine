# Exploratory method integration — audit and bounded design

Audit date: 2026-10-15. This work compares competing explanations; it does not
validate existing mechanistic interpretations or change a published endpoint.

The bounded local preparation continuation is recorded in
[local_preparation_20261015.md](local_preparation_20261015.md). It supersedes the
initial download/runtime status below, and separates baseline parity from lens-fit
provenance. The original one-case stimulus specification remains unchanged. The later
[review-preparation handoff](review_preparation_20261016.md) records final code
review, draft PRs and the separately authorized manual-only CI preparation.

## Chosen slice

Keep study selection, scoring and JSON reports in the engine. Add small, separate
adapters in the method forks. The first executable slice validates a one-family
specification and joins explicitly identified, full-vocabulary readouts and
controlled patch results using synthetic offline fixtures. It refuses real-model
execution until revision compatibility and baseline parity are established.
Existing collectors, hosted parsers, measurement files and frontend payloads stay
unchanged. No fitting, mask training, production trigger wiring or display work.

## Audit anchors

- Engine base: `31ee9268` (full commit recorded in the source manifest).
- Site: `cbc6d25bf5c02068d51bd0e197ef5df05b07e00c`; presentation only.
- Causalab fork/upstream: `8e8d5d1f8f9ca8f42bfce7c6b5eef194f012660e`.
- J++ fork/upstream: `93f02cd6c27db765abb127f20eff656bb5d27340`.
- Released lens repo: `e166deb5ad540932100ef803c8c9bcc2a5453694`.
  The advertised J++ artifact SHA256 is
  `893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d`.
  Initially only metadata and a bounded archive header were inspected. The local
  preparation continuation downloaded the complete file, verified this digest and
  safely inspected all tensors and authoritative embedded provenance; the JSON
  inspection receipt is `data/exploratory/jpp_artifact_inspection.v1.json`.

The PatientWords pin is `Qwen/Qwen3-4B` at
`1cfa9a7208912126459214e8b04321603b3df60c` for model and tokenizer.
The release describes width 2560, block outputs 0–34, transport target 35,
FP16 maps, 96 fitting prompts and no stream reduction. Its authoritative pickle
metadata agrees on those fields (absolute target 35 is explicit in the YAML;
embedded `relative_end_transport_layer=-1` is consistent with it). Full safe
inspection confirms that neither it nor the adjacent configuration names
the model/tokenizer revision used for fitting. Compatibility remains **unknown**.
A matching name and width cannot resolve that gap. No Gemma artifact is substituted.

`jlens_readout.py` falls back to the first response method and inferred layer
indices; `export_jlens_transport.py` treats the last fitted layer as an output
readout. Those historical paths remain intact. The new contract rejects missing
method/layer metadata and requires actual model output separately.

`activation_patch.py` uses block-output residuals and shared-suffix alignment, but
writes `batch_summary*` and clamps its recovery denominator. The new path reuses
only the alignment rule on token IDs; it records raw deltas and marks recovery
not computable for nonpositive or near-zero baseline gaps.

Causalab's initial registry lacked exact `Qwen/Qwen3-4B`; its tree resolver places
`mlp_neuron_output` at the down-projection input, distinct from gate activation.
A synthetic architecture check cannot establish real-model baseline parity.
Causalab requires Transformers >=5.16, while the engine pins 5.14.1; J++ pins
Accelerate 1.12.0 versus engine 1.14.0. Keep independent environments and locks.

Further file-specific findings, protocol commands, acceptance results and staged
PR boundaries are recorded below as implementation is verified.

## File-specific compatibility findings

| Source | Verified behavior and consequence |
|---|---|
| Engine `scripts/logits_eval.py:131`, `:251`, `:295` | The model and tokenizer share the exact study pin; raw strings, special tokens, no chat template and no truncation. Read `.logits[0,-1]` separately. The legacy target is the first encoded target token; keep that endpoint. |
| Engine `scripts/backend_agreement.py`, `docs/model_matrix.md` | Existing scalar agreement checks are useful references, but do not establish full-logit Qwen parity. Gemma precision findings are not a Qwen tolerance. |
| Engine `scripts/jlens_readout.py:156`, `jlens_position_scan.py:47` | Legacy method/layer fallbacks and best-layer/last-position summaries are unsuitable for the new comparison. New ingestion requires explicit method and complete common-layer × position rows. |
| Engine `scripts/export_jlens_transport.py:167`, other `export_jlens_*.py` | Last fitted-layer readout is not model output. Late-quarter display sampling is not an experiment design. These exporters and their payloads are unchanged. |
| Engine `scripts/activation_patch.py:57`, `:108`, `:282`, `:386` | Residual block outputs, unprocessed TransformerLens basis and common suffix are the baseline conventions. The new alignment compares token IDs, not decoded strings; no clamped normalized recovery denominator is reused. |
| Engine `scripts/feature_models.py`, `publication_hold.py` | Existing feature calibration and publication release gates remain authoritative. Readability in a lens is not a native neuron, calibrated concept, or clinical correctness claim. |
| Causalab `protocol/registry/families.py`, `registry/models.py`, `neural/shared/sites.py` | Exact Qwen3-4B was absent from the initial static rows. Its verified config supplies a new explicit row. The resolved down-projection input is the native gated-MLP product. Architecture tests do not certify real checkpoint support. |
| Causalab `demos/papers/arithmetic_neurons.md`, referenced protocols, `demos/methods/protocols/minimal_cpu.json` | Arithmetic counterfactual training objectives use different answers. They are not copied into same-answer wording pairs. The v4 compiler is callable; an unregistered model can trigger config discovery in the general CLI, so the new adapter requires registered identity and prepared weights. |
| J++ `scripts/quickstart.py`, `scripts/jpp_cli.py`, `workspace_lens/utils.py` | The quickstart model is not this pilot. The legacy loader can leave tokenizer revision unpinned and default to CUDA. New interop never loads a model or tokenizer. |
| J++ `workspace_lens/lenses/base_lens.py`, `jacobian_lens.py` | Configured `parameters.jacobians` and released `J` dictionaries represent the same linear algebra, not necessarily the same method. Safe loading requires a verified hash, explicit method evidence and model/fit identity. Preserve original metadata; transport is `h @ J.T`, then native final norm and LM head once. |
| J++ `lens_evals/readout_evals/readout_eval_items.py` | Upstream correctness filtering would remove study failures. New comparisons retain wrong-answer cases and distinguish first-wordpiece scores from whole-answer correctness. |
| J++ `lens_evals/causal_evals/probe_swap.py`, `runner.py` | Existing swaps normally cover every nonsink position, use normalized pre-final-norm directions, pseudoinverse swaps and a scale sweep. Best evaluated scale selection and dropping unpatched failures are not adopted. Probe swaps remain a separate optional intervention. |
| Site `AGENTS.md`, `technical/index.html`, existing JSON contracts | Presentation only. No generated figures, existing payloads, pending states or published numbers are changed. |

Root instruction files were read in engine and site; no nested AGENTS files were
found there. Neither method fork contained an AGENTS file. Fork and upstream
heads were identical at the audit; the local adapter branches introduce the
only fork differences. The full commit, release-file metadata and configuration
hashes are in `data/exploratory/method_sources.v1.json`. The Causalab checkout has
no root repository license file (the Rust workspace declares Apache-2.0); resolve Python distribution terms before distributing its
code. J++ and the released lens are Apache-2.0; attribution stays in the fork and
source manifest. No upstream implementation is copied into the engine.

The official Neuronpedia source at `bd0f54796a957f0bf64e3080e43580a57d122b1e`
exposes `JPP_LENS` alongside `LOGIT_LENS` and `JACOBIAN_LENS` in
`apps/inference/openapi.json`. The web route limits `topN` to 8. That establishes
a schema, not deployed Qwen support or a returned revision. No hosted inference
was called. Its top-k interface cannot supply the full-vocabulary rank comparison
or k=16/32; use local full-logit adapters in an authorized CI execution instead.

## Implemented boundary and data dictionary

`schema_version=patientwords.exploratory/1` is new. The companion schemas are
`schemas/exploratory/spec.v1.schema.json` and `packet.v1.schema.json`;
`scripts/exploratory_methods.py` enforces the cross-field rules. Its first version
accepts **synthetic packets only**. Real ingestion remains blocked pending the
paired-readout/CI follow-up, rather than treating missing provenance as a waiver.

- **Specification:** exact model/tokenizer identities, study short model ID,
  dimensions, precision/backend, capture/norm convention, fork base commits and adapter source hashes, per-method
  artifact identities and fitted layers, explicit input settings, seed, family
  splits, original source joins, raw prompt and token hashes, separate intermediate
  and answer annotations, vocabulary exclusions, fixed layers, k values and the
  complete intervention plan. Null token IDs in a real plan mean pending, not an
  empty prompt. Original pilot source/run joins stay visible.
- **Packet:** exact specification digest and model metadata; complete vocabulary;
  each readout identifies case/variant/method/layer/position; actual model outputs
  identify their independent extraction; interventions repeat the prespecified
  identities and include the full output vector and measured edit norm. Missing
  grid cells or interventions refuse, as do duplicate identities.
- **Report:** keeps readouts, original-model behavior and intervention effects in
  separate arrays. Full-vocabulary softmax always retains its full denominator.
  Filtered rank is null for an excluded candidate; the exclusion audit retains its
  decoded symbol and reason. Ties break by ascending token ID. A top-k miss is
  `not_observed_in_window`. Multi-token targets retain a first-wordpiece proxy and
  a not-scored exact sequence status. Raw probability delta is primary; normalized
  recovery is null for a nonpositive or ≤1e-6 baseline gap.
- **Execution:** every report says synthetic/exploratory, carries both input hashes,
  environment and seed. Runtime and peak memory are null when unmeasured. No output
  filename matches `batch_summary*`, `verify_summary*` or a lens publication file.
  The writer creates `exploratory_methods/exploratory_report.<id>.json` exclusively,
  refuses existing files, protected trees and symlink escapes, and never publishes.

The synthetic packet deliberately includes failed and top-1 first-token baselines,
self replacement, both directions, separate zero ablation, full-component,
same-register, unrelated-coordinate and seeded random controls. These are abstract
fixtures; they establish software behavior, not biological or semantic controls.
Actual unrelated-concept and collateral-prompt selection remains a discovery-only,
reviewed prerequisite for the real experiment.

## One-case protocol and exact commands

`data/exploratory/qwen3_4b_one_case.v1.json` is the executable validation
specification. It selects the first kept, owner-reviewed, unsealed pilot item
`vt_216a7dd64eee` / `pilot_v2_20261002` / `r001`, without selecting on model outcome.
Its source bundle, review, display and original pair hashes are retained. The
intermediate lexical annotation comes directly from that review; the next-word
answer remains the existing target. This is a brand/generic contrast, not a slang
contrast, and remains a pilot source. No approved normalized variant is available.
No new wording was generated. The dated source seal is not substituted for a new
pre-execution seal check.

From the engine checkout, these commands are offline and do not fire anything:

```bash
python scripts/exploratory_methods.py \
  --spec data/exploratory/qwen3_4b_one_case.v1.json
# Expected exit 2: named blockers, including unknown lens fit revisions.

python scripts/exploratory_methods.py \
  --spec tests/fixtures/exploratory/synthetic_spec.json \
  --packet tests/fixtures/exploratory/synthetic_packet.json \
  --out /tmp/exploratory_methods/exploratory_report.synthetic.json
# Expected exit 0; choose a new filename if it already exists.

python -m pytest -q
ruff check .
python scripts/validate_frontend_contract.py --site ../patientwords
```

In the J++ fork, using its independent environment:

```bash
PYTHONPATH=src python -m lens_interop \
  --manifest examples/interop/qwen3-4b-jpp-unknown-fit.json
# Expected exit 2: unknown fit identity; no weights loaded.
PYTHONPATH=src python -m pytest -q src/lens_interop/tests src/jlens/tests/test_hf_layout.py
```

In the Causalab fork, the following validates a synthetic protocol without a model
or the Rust-backed runtime:

```bash
python -m causalab.analysis.paired_intervention \
  tests/analysis/fixtures/synthetic_pair.json \
  --protocol-out /tmp/synthetic_pair.protocol.json
python -m causalab.cli validate /tmp/synthetic_pair.protocol.json --engine pytorch_hooks
```

Use the Causalab commands and public `build_pair_protocol`, `validate_pair` and
`run_pair` interfaces in that fork's `docs/paired_intervention_adapter.md`. Its synthetic
protocol is executable by the actual v4 compiler. The model/tokenizer caller
must already have the pinned weights; the adapter never downloads them.
`temporary_pair_patch` and `capture_qwen_dense_product` are bounded native probes
using Causalab's public site resolver. They do not replace the protocol runner.

Environment preparation is separate. The engine keeps `constraints.txt` unchanged.
For a future authorized clean Linux CI environment, resolve each fork with its own
`uv sync --locked` and documented CPU extra (J++ `--extra cpu`), preserving its
lock. Causalab additionally needs its declared Rust toolchain and compiled
`fastersafetensors._core`. Do not claim the lightweight local test environments
are full locked installs. Their tested package versions are recorded in the fork
notes. No fitting or mask optimization is part of these commands.

**There is no honest production trigger command for this adapter yet.** Existing
`jlens-readout` keys do not admit these manifests and its hosted top-k path cannot
provide full ranks. Existing `activation-patching` would write a collector-visible
measurement. A follow-up PR must first add reviewed CI wiring, keys, parked defaults,
provenance and tests. Only after that merges and the owner authorizes execution may
an actual command be prepared with `scripts/fire_trigger.py`, the current budget
ceiling, one-running/one-pending queue discipline and subsequent parked state.
No imaginary trigger key or local research-model run is provided as a shortcut.
The subsequent owner authorization permits a narrow, manual-only baseline route;
[baseline_ci.md](baseline_ci.md) documents its review and default-branch gates.
This exception does not change any production trigger or authorize execution.

The first CI baseline check is **lens-independent**: unknown historical lens-fit
revisions do not block its preparation or an otherwise authorized baseline run.
The continuation in [baseline_preflight.md](baseline_preflight.md) replaces the
initial two-forward/120-second sketch with explicit settings, capacity, timeouts
and prospective failure gates. It compares the legacy HF call, an explicitly
aligned HF call and Causalab on the same two approved prompts, with no lens or
intervention. The current seal, exact code/weight/tokenizer revisions and reviewed
execution wiring remain prerequisites. TransformerLens parity remains a later
separate check before residual-patching comparisons.

Lens readouts additionally require authoritative fit model/tokenizer revisions
(or another genuinely compatible release), frozen filters and targets, final-norm
parity and actual-output extraction. Artifact integrity alone does not satisfy
those gates; the continuation does not weaken them.

Local hardware audit: 16 GiB RAM, 10 CPUs, arm64, CUDA unavailable, MPS available.
A CPU-only synthetic 8×2560 identity transport took 0.0141 s with process max RSS
220,348,416 bytes. This is **not** a Qwen model-runtime or fitting-capacity estimate.
No 4B weights were downloaded. The continuation inspected the complete lens file.
Full-model CPU/GPU memory,
mask training and Jacobian fitting remain unmeasured and unauthorized.

## Staged pull-request plan

1. **Compatibility/contracts:** this local engine branch, the small Causalab adapter
   branch and J++ interop branch. Review provenance refusals, safe formats, synthetic
   tests, exact-model registry row and original contract compatibility. No production
   measurement or site changes.
2. **Paired readouts:** once artifact provenance is sufficient, pin independent CI
   environments, verify baseline/final-norm parity, capture residuals once where
   parity permits, and emit complete common-layer/position comparisons with actual
   logits kept separate. Freeze candidates/filter before fresh cases.
3. **Controlled patches:** reproduce residual baseline first, then discovery-nominated
   native channels, reverse direction, ablation, matched seeded controls and collateral
   prompts. Add protocol-runner CI execution only after its Rust-backed path passes.
   Full-continuation scores or independent answer review are separately labeled
   measures; no upstream correctness filter or best-layer/scale selection.
4. **Optional presentation:** a new exploratory payload/view after useful results,
   preserving existing payloads and pending states. Provenance and observational
   versus interventional evidence are visible. No patient-facing safety meter.

No PR was opened, pushed or merged. These are local reviewable changes only.

## Optional extensions, ranked

| Priority | Extension | Scientific value | Cost/support and decision |
|---|---|---|---|
| 1 | Same-model lens disagreement | Tests whether depth stories depend on readout method before revising them | Released Qwen artifacts exist; exact fit provenance and full-logit parity are blockers. First follow-on. |
| 2 | Syntax × terminology and approved normalization rescue | Separates wording factors and tests observed gaps with existing 2×2 stimuli | Moderate inference cost, no new generator. Requires reviewed unsealed families and actual approved normalized text. |
| 3 | J++ lens-coordinate probe swap | Useful alternative intervention baseline to native coordinates | Machinery exists; predeclare position scope, direction normalization, final norm, token exclusions and scales. No test-set best-scale choice. |
| 4 | Sparse native masks versus distributed subspaces | Tests whether sparse neurons are sufficient rather than presuming it | Substantial optimization/validation cost; defer until residual/native controls work. Family-level discovery/validation/fresh-test separation. |
| 5 | New model-specific J++ fitting | Useful only if no matching released artifact can be established | High compute/memory and provenance burden. Never fit on evaluation families. Do not fit a substitute Gemma lens merely to fill a missing slot. |
| 6 | Drift-inspired multi-turn research view | Potentially links independently reviewed behaviors to within-model changes | Deferred: no specified validated clinical construct or artifact. A projection is neither causal evidence nor harm probability. Blog user-study score prediction would not establish clinical validation. API-only transcripts have no hidden states; surrogate internals must never be attributed to their source assistants. |

A later cohort of 12–20 families is feasibility scope, not a power calculation.
Allocate discovery/validation/fresh confirmation by both case and template family;
use family-level uncertainty, not token/layer counts. Retain failures, zero effects
and negative effects. No individual rescue establishes a unique circuit or a safety
improvement.


## Acceptance and artifact inventory

Initial implementation checks, before the local preparation continuation:

| Check | Actual result |
|---|---|
| Engine full `python -m pytest -q -rs` | **5,057 passed, 9 skipped**, 251.54 s. |
| New engine contract tests | **79 passed**; included in the full suite. |
| Engine `ruff check .` | Clean. |
| Existing site contract validator | **0 errors, 1 existing warning**: 1,728/13,652 urgency rows have no published-scenario join. No payload was edited. |
| Causalab selected new + registry/capability tests | **205 passed, 1 skipped**, 3 existing offline-cache warnings, 1.89 s. Pinned Ruff 0.14.5 clean. |
| J++ interop + existing HF-layout tests | **43 passed**, 1.01 s; one warning for absent NumPy in the minimal test environment. Ruff clean. |
| Synthetic cross-repository bridge | Both tensor serialization formats safely loaded, paired readouts scored by the engine: **36 readout rows, 3 independently extracted outputs, 10 toy interventions**. Exact self-patch identity, both first-token baseline strata, no real model execution. |
| Holdout sweep | **CLEAN: 183 sealed phrases, no new hits**. The existing owner allowlist remains unchanged. |

The first engine run found the missing new-script index row (fixed) and sandbox
localhost fixture errors. The successful full run allowed localhost sockets and
used the existing sibling site. Engine skips are two absent inspect_petri modules,
three absent Playwright browser checks, two absent inspect_ai checks, a not-landed
PAB workflow and the scheduled workflow's inapplicable push guard. They are not
passes. Causalab's skipped module contains full public-runtime tests requiring the
unbuilt Rust extension. Its entire upstream suite and released-weight parity were
not run. The J++ full workspace suite could not collect without Transformers in
the minimal environment; its entire locked upstream suite remains unrun.

The durable portable bridge is `tests/manual/exploratory_bridge.py`. From this
engine checkout, with the isolated Torch test interpreter selected:

```bash
PYTHONPATH=../patient-words-jpp_lens/src:. python tests/manual/exploratory_bridge.py \
  --jpp-root ../patient-words-jpp_lens \
  --out /tmp/patientwords-new-demo/exploratory_methods
```

The directory must be new. This writes two tiny synthetic lens tensors, their
manifests, a matching spec/packet and `exploratory_report.adapter_bridge.json`.
The arithmetic toy has three blocks and signed gated products. It is not Qwen,
not Causalab's protocol execution and not study evidence. The actual Causalab
native-hook tests instead use a separate random tiny Qwen3 architecture.

Actual audited artifacts are source commits/configuration metadata, the pinned
release's advertised hashes, bounded pickle-opcode headers and the already-reviewed
pilot item's source references. Synthetic artifacts are all fixture logits,
matrices, toy activations, patch effects and bridge outputs. There are **no new
real-model measurements**. The continuation verifies the full J++ checkpoint hash; the J-Lens file remains
unverified locally. No model benchmark, native-neuron identity, fitting result or
safety claim is reported. In the initial pass, no trigger, workflow, landed data, dependency pin or frontend
file changed, and no network inference, push, merge, publication or deployment
occurred. The review continuation adds inactive manual workflow wiring and pushes
review branches only; its handoff records the exact scope.

The next smallest experiment is the lens-independent one-case CI baseline-logit
parity preflight, after separate owner authorization and reviewed execution wiring.
Historical lens-fit provenance can be resolved in parallel. Paired readouts follow
only after both compatibility and parity gates pass; native-channel comparisons
follow a working residual baseline with complete controls.

### Contract hardening during review preparation

Synthetic evidence validation also rejects reuse of a source join or exact prompt
across discovery/validation/fresh-test splits, even when family IDs are relabeled.
Target text must agree with its vocabulary token identity before a score is
labeled exact or first-wordpiece proxy. Every random channel control now declares
`matched_to`, the nominated intervention ID, and must match its case, direction,
kind, component, layer, positions and group size as well as its own recorded seed.
The two structural schemas declare that required random-control reference; the
semantic validator enforces the cross-record comparison.

This tightens the new, unpublished exploratory v1 synthetic contract only. Old
synthetic packets without `matched_to` must be regenerated with explicit links;
they refuse rather than silently acquire a comparator. The repository's supplied
synthetic fixtures are updated. Existing measurement/frontend schemas and the
reviewed real-case specification remain unchanged.
