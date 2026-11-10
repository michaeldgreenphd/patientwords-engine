# Contributing a method

Written 2026-11-10. This is the path for adding an interpretability or behavioural method
to the shared experiment interface: a lens, a decomposition, an attribution method, a
behavioural readout or a conversation audit. Paths are relative to the engine root.

The interface is the package `scripts/experiments/` with schemas under `schemas/experiments/`.
It extends the exploratory contract in `scripts/exploratory_methods.py`
(`patientwords.exploratory/1`) and does not replace it. The package, its schemas under
`schemas/experiments/`, its fixtures under `tests/fixtures/experiments/` and its tests
`tests/test_experiments_*.py` were added with the 2026-11-10 change set. Check the code for
the exact field lists; where this page and the code disagree, the code governs.

A contribution is offline by default. It loads no model weights, calls no provider and
writes nothing under `trace_out/`, `data/`, `pilot/`, `ops/` or the site's data directory.
Real-model execution is a separate, approved step ([start_here.md](start_here.md#procedure-b-model-execution)).

## 1. Required metadata: the run envelope

Every result is one envelope, schema `patientwords.experiment-envelope/1`, around one typed
payload. The envelope records, for each task:

- identity: `run_id`, `task_id`, `spec_sha256`, `replicate`, `attempt`, `attempt_history`;
- `protocol` (id, version, sha256) and `source` (family, variant, register, role, turn, branch, legacy join);
- `evidence`: the open-results policy fields plus `synthetic`;
- `input`: prompt and token hashes, token count, tokenizer id and revision, chat template,
  special tokens, truncation, alignment;
- `model`: study id, repository id, revision, provider, route, hosted timestamp;
- `environment`: source commits, packages, lock hash, backend, device, dtype, quantization,
  attention implementation, sampling;
- `method`: id, representation type, capture site, layer index base (0), layers, positions,
  preprocessing, fitted artifact hash with its fit provenance, output head;
- `counts`, `resources`, `status` (execution state and reason), `payload` and `not_recorded`.

Three rules decide most reviews:

1. A provenance field may be null only when its JSON pointer is listed in `not_recorded`.
   A historical value is never invented to fill a field.
2. Execution state uses the fixed vocabulary `not_run`, `unsupported`, `unavailable`,
   `invalid`, `failed`, `completed`. A zero or opposite-direction effect is `completed`.
3. A resource number is stored only when it was measured. An estimate belongs in the plan.

## 2. Result type: a typed payload, never a generic score

Declare a new payload kind, `<name>/<version>`, with its own schema file under
`schemas/experiments/`. Existing kinds: `behavior_next_token/1`, `lens_readout_report/1`,
`ica_scores/1`, `conversation_ref/1`, `attribution_graph_ref/1`.

- Write the schema in the keyword subset `scripts/frontend_contract_schema.py` accepts
  (`$schema`, `$id`, `title`, `description`, `definitions`, `$ref`, `type`, `required`,
  `properties`, `items`, `additionalProperties`). Enforce vocabularies in code.
- The adapter declares which payload kinds its method may file. A payload of another kind is
  refused, so a lens readout cannot be stored as an ICA score.
- Do not add a field that reduces different methods to one number. A lens rank, a component
  score and a next-token probability have different units. The comparison step keeps them in
  separate blocks.
- State units and denominators in the schema descriptions. A share of squared coordinates is
  not a probability and must not be labelled as one.

## 3. Capability declarations

Add rows to `data/experiments/capability_matrix.v1.json`, one per model revision, method,
backend and artifact. Each row carries `evidence` (a file path or URL, with a date) and a
`status_note`. The statuses, weakest first:

`unsupported`, `architecture_supported`, `artifact_available_identity_unknown`,
`artifact_available`, `runtime_verified_offline_fixture`, `parity_passed`.

These are different facts. Architecture support says the code path exists. Artifact
availability says a fitted lens or basis can be fetched; with `identity_unknown`, its fit
revision or provenance is not recorded. `parity_passed` says a recorded audit compared this
exact combination against a reference, and the row cites the record. A passing fixture test
is `runtime_verified_offline_fixture` and nothing stronger; it is not evidence of parity.

A combination the matrix marks `unsupported` stays in the plan as `unsupported` with its
reason. It is counted, not skipped.

## 4. Example fixture

Add a synthetic fixture under `tests/fixtures/experiments/`:

- abstract placeholder phrases only. No text from `data/simulated/` or `trace_out/` (the
  Tier B holdout seal), and no medical vocabulary in Python source;
- `synthetic: true`, `evidence_class: "synthetic_fixture"`, `visibility: "not_published"`,
  `analysis_memberships: []`;
- expected values that were derived independently of the adapter under test, so the test can
  fail;
- a recorded seed for anything random.

## 5. Verification an addition must pass

| Check | Command or test |
|---|---|
| The adapter's own tests: payload validation, each named refusal, the unsupported path | a new `tests/test_experiments_<method>.py` |
| The shared interface still holds | `python -m pytest -q -ra tests/test_experiments_*.py` |
| The exploratory contract is unchanged | `tests/test_exploratory_methods.py` |
| Documentation gates and lint | the quick path in [verify.md](../verify.md#quick-path) |
| A new top-level script has its index row | `tests/test_scripts_readme.py` (packages under `scripts/` need no row) |
| Everything else | the full suite in [verify.md](../verify.md#broader-local-gates-and-ci-limits) |

Each statistical routine takes a seed and writes it into its output. Missing data is
recorded as missing, never as zero. Report every skip; a skipped test is not a pass.

## 6. Publication eligibility

[docs/open_results_policy.md](open_results_policy.md) governs. A result is shared when its
artifact is intact and no named restriction applies, whatever its direction or size.
Analysis membership is a separate decision: a result enters a statistic only through a
named membership recorded in a versioned snapshot. A new method's real outputs start visible,
labelled with evidence class and review status, and in no analysis membership until one is
declared. Fixture output is never published.

## 7. Dependencies: optional and isolated

- The method's runtime (for example a GPU stack or a lens library) lives in its own
  environment with its own lock file. `docs/framework/petri_environment.lock.json` is the
  existing example of a lane with its own lock.
- `constraints.txt` pins the measurement CI stack. It is not changed to make a method
  install. A bump there is a deliberate, single-purpose change with its own review.
- The offline interface imports the standard library and numpy only. An adapter must
  import without the method's runtime present, and report `unavailable` when it is absent.

## 8. Attribution, licence and local patches

- No upstream implementation is copied into the engine
  (`docs/exploratory/methods_integration.md` records the rule). The adapter calls the method
  in its own repository or reads an artifact that repository wrote.
- Cite the upstream project, authors and licence in the capability row's evidence and in the
  method's documentation. Where an upstream ships a `NOTICE` or third-party notices file,
  redistribution of its code or of a derived artifact must carry it; read the licence before
  an artifact derived from upstream code is published.
- A local change to an upstream method is committed in the project's fork of that
  repository, as added files where possible, so that upstream merges stay clean and the delta
  can be listed. Record the fork ref the adapter was verified against in the ecosystem
  manifest, `data/ecosystem/repositories.v1.json`.
- Licences of model weights and of released fitted artifacts are their publishers' own.
  Record what the publisher states; record "not stated" when it is not.

## 9. Out of scope

These are refused in review, whatever the result looks like:

- Fitting, profiling or selecting anything on evaluation families. A basis or lens is fitted
  on the `discovery` split only.
- Choosing the best layer, scale, component or threshold on evaluation data. Such choices are
  fixed in the protocol before the evaluation data is opened.
- Relaxing unknown-fit identity. An artifact whose fit revision is unknown stays
  `artifact_available_identity_unknown`, and its tasks stay `unavailable`, until the identity
  is recorded.
- A generic "understanding" or "bias" score across methods.
- Presenting a fixture or mocked run as a measurement, or as evidence of parity with a real model.
- Unsealing holdout rows, rewriting a recorded hash, or editing landed measurements.
- Firing a lane. That goes through `scripts/fire_trigger.py` with owner approval.
