# Experiment interface

Added 2026-11-10. The package `scripts/experiments/` is a small orchestration layer for
method comparisons: one run envelope around typed payloads. It extends the exploratory
contract (`scripts/exploratory_methods.py`, `patientwords.exploratory/1`), which is
unchanged and still the authority for lens readout scoring. Everything in the package is
offline: no command loads a model, opens a network connection or fires a trigger.

This page says what exists and what was verified. The code governs where they differ.

## Why an envelope and not one schema

A lens readout, an ICA score table, the original model's next-token output, a conversation
transcript and an attribution graph are different measurements. Version 1 of the
exploratory contract could not represent a method that did not run, a fourth method or a
real run ([methods_integration.md](../exploratory/methods_integration.md)). The envelope
carries what every run shares (identity, provenance, state, counts) and points at one
typed payload by hash. Nothing in the package computes or stores a combined score.

| Payload kind | Method ids | Produced by | Status in this milestone |
|---|---|---|---|
| `behavior_next_token/1` | `behavior_next_token` | `scripts/experiments/adapters/behavior_fixture.py` | runs on independently supplied fixture logits |
| `lens_readout_report/1` | `logit_lens` | `scripts/experiments/adapters/readout_exploratory.py`, which wraps `exploratory_methods.build_report` | runs on the synthetic readout fixture |
| `ica_scores/1` | `ica_lens` | `scripts/experiments/adapters/ica.py` | runs on toy activations; [ica_adapter.md](ica_adapter.md) |
| `conversation_ref/1` | `conversation_audit` | none | reference only; the Petri lane keeps its own records |
| `attribution_graph_ref/1` | `attribution_graph` | none | reference only; [neuronpedia.md](neuronpedia.md) has the contract plan |
| none | `j_lens`, `jpp` | none | planned as `unsupported` or `unavailable` with the reason |

## The flow

```text
protocol (case families, variants, methods)      scripts/experiments/protocol.py
        | validate: hashes, splits, layers, seal
plan (deterministic tasks, estimates)            scripts/experiments/planner.py + capabilities.py
        | each task: ready | unsupported | unavailable, with the reason
run store (shards, journal, resume, reuse)       scripts/experiments/store.py
        | one envelope per task and attempt       scripts/experiments/envelope.py
collect (one deterministic assembler)            scripts/experiments/store.py
        |
compare (separate blocks per payload kind)       scripts/experiments/compare.py
        |
bundle (what a browser preview renders)          scripts/experiments/bundle.py
```

Commands, from the engine root (the offline quickstart in [start_here.md](../start_here.md)
has a runnable block):

```bash
python -m scripts.experiments.cli validate --protocol tests/fixtures/experiments/protocol_synthetic_ica.json
python -m scripts.experiments.cli capabilities --model gemma-2-2b
```

Exit codes: 0 success; 1 the command finished and the run is not clean; 2 a named refusal,
printed as JSON; 3 a configuration error (the holdout seal or the results policy could not
be evaluated).

## Three things kept apart

**Execution state** says what happened to a task: `not_run`, `unsupported`, `unavailable`,
`invalid`, `failed`, `completed`. A finished task with a zero or opposite-direction effect
is `completed`. `unsupported` means the capability matrix says the combination cannot run.
`unavailable` means it could in principle, and a required input is absent or its identity
is unknown.

**Evidence and visibility** come from the [open-results policy](../open_results_policy.md):
evidence class, clinical-review status, visibility, restriction reasons, analysis
memberships. A fixture run is `synthetic_fixture`, `not_published`, in no membership.

**Capability status** says what is known about a model revision, method, backend and
artifact, weakest to strongest: `unsupported`, `architecture_supported`,
`artifact_available_identity_unknown`, `artifact_available`,
`runtime_verified_offline_fixture`, `parity_passed`. Each row of
`data/experiments/capability_matrix.v1.json` cites its evidence. "The architecture is
supported" and "this combination passed parity" are different rows. On 2026-11-10 one row
is `parity_passed`: gemma-2-2b next-token behaviour through interp-engine in float32
against the hosted service (`docs/backend_agreement_20260903.md`), and that record has no
checkpoint revision.

## Identity, attempts and replicates

`spec_sha256` is the digest of what a task computes: protocol hash, family, variant, model
identity, the full method block, input hashes and settings. Attempt and replicate numbers
are not part of it. The store key for reuse is `(spec_sha256, replicate)`:

- a resumed run reuses a completed, hash-verified envelope and does not execute the task again;
- a changed input or setting changes `spec_sha256`, so nothing is reused, and the old run
  directory refuses the new plan (`incompatible_resume`);
- replicate 1 is executed even when replicate 0 is complete. A cached response is never
  counted as an independent repetition.

The journal records a line before a task starts and another when it ends. A start without
an end is listed as an uncertain attempt and is kept. The store does not claim exactly-once
execution; for a paid call, an uncertain attempt and its reservation are what
reconciliation needs.

Concurrent workers write separate shard directories. `collect` is the only assembler: it
sorts, verifies every payload hash, keeps one of identical duplicates, refuses conflicting
ones, and lists planned tasks with no envelope.

## Provenance that is missing stays missing

An envelope field that records provenance may be null only when its JSON pointer is listed
in `not_recorded`. The validator refuses a null that is not listed
(`silent_missing_provenance`). Historical runs lack fields (118 landed logits parts have no
`inference.environment`; the hosted lens records no instrument revision); the envelope says
so and never fills them in.

Resource fields follow the same rule: `resources.measured` false requires every numeric
field to be null. The plan carries estimates (activation bytes from tokens, layers, width
and bytes per value), each labelled as an estimate with its assumptions. No runtime is
estimated unless a measured rate with its source and sample size is supplied.

## Where output may go

Writers refuse a path under `trace_out`, `data`, `pilot`, `ops`, `modes`, `.github`,
`.claude`, `.githooks` or `.git`, and any path inside a Git checkout unless `--allow-root`
names it. Fixture output therefore cannot reach a measurement collector, the site's data or
a historical manifest.

## What was verified, and what was not

| Statement | Evidence |
|---|---|
| The slice runs end to end on synthetic fixtures, with interruption, resume and reuse | `tests/test_experiments_slice.py`: 45 tasks; 5 executed, then 22 with 5 reused; a third run executes 0 |
| Each named refusal fires | `tests/test_experiments_core.py`, `tests/test_experiments_store.py`, `tests/test_experiments_compare.py` |
| The ICA adapter agrees with the `icalens` library on toy data | `tests/test_experiments_ica_icalens.py`, run in an isolated environment with torch 2.13.0 and icalens 0.4.0 |
| The existing exploratory contract is unchanged | `tests/test_exploratory_methods.py` passes; its fixtures are byte-identical |
| Any real model | not verified. No model was loaded. Fixture timings say nothing about a model run |
| Any measurement validity | not verified. Toy values are chosen by hand so that expected results are computable |

The next step that involves a model is described in
[first_model_run_packet_20261110.md](../exploratory/first_model_run_packet_20261110.md). It
needs a declared model, reviewed case families, verified artifact identity, a resource
plan, an admission route and a fresh parity result. None of those is supplied by this
package.

## Adding a method

[contributing_a_method.md](../contributing_a_method.md) is the procedure. In short: a new
payload kind with its own schema, an adapter module that exposes `ADAPTER`, one line in
`ADAPTER_MODULES` in `scripts/experiments/adapters/__init__.py`, capability rows with
evidence, a fixture with hand-computable expectations, and tests for each refusal.
