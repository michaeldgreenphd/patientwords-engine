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
be evaluated). "Not clean" covers three cases: an attempt ended `failed` or `invalid`;
`run-fixture` was not stopped by `--stop-after` and left a ready task without a completed
result (absent or unreadable fixtures, for example); `collect --require-complete` found a
planned task without an envelope or a ready task without a completed result that counts (a
completed result set aside under `completed_under_superseded_inputs`, below, does not
count). An adapter error at preflight is recorded as a `failed` or `invalid` attempt, and
the run goes on to the next task.

The holdout seal is checked for every family of a non-synthetic protocol. A family with a
`legacy_join` has its clinical prompt checked as that row. Every other variant prompt, and
every prompt of a family without a join, is checked as a bare phrase with no batch and no
index. Any hit refuses `holdout_refusal`; the refusal names the family and variant and
never repeats prompt text.

## Batch intake: from an authored batch to a review packet and a manifest

Added 2026-11-12. `intake` reads one authored batch of case families (the `families.json`
of a draft round) and writes three files. It loads no model and reads no measurement.

```bash
python -m scripts.experiments.cli intake --batch tests/fixtures/experiments/intake_families_synthetic.json --batch-id synthetic --stem placeholder_stem --split-seed 7 --no-write
```

| Output | Holds |
|---|---|
| `review_packet.md` | per family, on one screen: reference facts, every wording, the changed fact, the patient's explanation where there is one, each everyday expression with its declared source and evidence sentence, and the software findings. No model output |
| `review_form.json` | one empty record per family and reviewer role, with the items of `pair_equivalence_review` in the draft rubric set to null. A null is "not reviewed" |
| `intake_manifest.json` | the proposed measurement manifest: family ids, SHA-256 of each family, of its texts and of each prompt, strata, splits, the mechanistic subset, review status, model and tokenizer pins, and estimated work. It holds no prompt text |

The rules it applies are data, in `data/experiments/intake_design.v1.json`. That file is a
draft the owner has not agreed; the packet and the manifest repeat its status line.

**Four layers of review, never merged.** Software validation (this command, extending
`scripts/check_candidate_pairs.py`) covers structure only. The owner's read is a keep or
exclude decision on a named version of the family. Clinician review and patient-language
review come only from `--reviews` records whose `reviewer_kind` is `human`; anything else
is refused (`not_a_review`). A family without both reviews is `domain_review_pending`.
Several reviews of one role are combined item by item and never by input order: any
`different` stands and removes the family, `same` needs every reviewer who recorded the
item to say `same`, and the manifest lists the items they disagree on.

**What a read or review is bound to.** The family's review basis
(`review_basis_sha256`): its texts, reference facts, care levels (`right_care` and
`right_care_after`), carrier, target and changed-fact declaration. When any of them
changes, with or without a change of prompt text, the owner's read and both reviews are
`stale` and the manifest names the part that changed. They are not carried over.

**Known concerns** (`--concerns`, schema `patientwords.intake-concerns/1`). A concern
about a family's content (a control that adds a fact, a disputed level, a stated negative,
source fit) is a record of its own, with a kind, the contrasts it applies to, who raised it
and a disposition. The owner keeping a family does not close a concern, and neither does a
review: only its recorded disposition does. `accepted_as_is` and `resolved_by_revision`
are a person's decisions and a model cannot record either (`not_a_disposition`); a revision
made to address a concern leaves it open as `revised_pending_reread` until a person
confirms it. `resolved_by_revision` names the review basis of the version that resolved
it; for any other version the concern is open again. An open concern on the family or its
register contrast blocks a confirmatory statement on the register pair. An open concern on
a control is listed on that control (`controls_with_open_concerns`) and does not block the
pair; neither does one on the reviewer-only label. The packet prints every
concern with its disposition; the review form lists the open ones.

**Source verification and source fit.** `--source-check` (schema
`patientwords.source-check/1`) records, per citation (an expression with one identifier),
that the cited record exists and contains the evidence sentence. A check of one citation
does not count for another citation of the same wording. That is verification. Whether patients in the family's
population use the expression is source fit, a judgement that verification never implies;
it is recorded as a concern of kind `source_fit`.

**Strata.** Each contrast belongs to one stratum and strata are never pooled:
`register` (medical against everyday), `patient_explanation` (everyday against everyday
plus the speaker's stated belief; the clause adds information, so it is not a register
contrast) and `syntax_crossing`. A family that uses a dialect form, or a carrier phrase
with no earlier measurement, has its register contrast reported in `register_with_dialect`
or `new_carrier`. Only an unflagged family's `register` contrast is a candidate for a
confirmatory statement, and only under a signed protocol. Care tiers are not compared:
families at different tiers end on different carrier phrases and target words.

**Two kinds of eligibility.** `eligibility.publication` follows
[open_results_policy.md](../open_results_policy.md): an admissible family's intact results
are shareable under `public-display/1` whatever their effect, with their labels.
`eligibility.confirmatory` lists what blocks a confirmatory statement
(`protocol_not_signed`, a missing review, a flag, an unassigned split, and
`calibration_split` for a discovery family: the protocol makes its primary contrast on
held-out families and uses discovery families for calibration only). Every blocker the
command can give is defined in the design file (`eligibility.confirmatory_blockers`),
which also says which criteria the protocol draft names and which this design adds: the
owner's keep, the open-concern rule and the named stem. A recorded clinician review with a
`cannot_judge` does not pass (`domain_review_not_passed`). The two are
separate fields because an exploratory or null result is shared, not hidden.

**Splits and the mechanistic subset.** A split is drawn per family (every wording of a
case together), per care level, from a recorded seed. A recorded split
(`--split-record`) is read and never redrawn; two records that disagree refuse
`split_conflict`. A split record is accepted, before or after measurement, only when it
carries a seed and its splits are exactly the draw that seed gives over this batch's
families and care levels (if it lists strata, they must be the batch's); a bare mapping or
a hand-placed assignment refuses `split_record_unbound`.
When `trace_out/` already holds a directory for `--stem`, nothing is drawn: a new split
refuses `split_after_measurement`. The command
cannot see when a record was written: the commit that added it is the evidence, and the
manifest says so (`records_timing`). A subset is restored only from `--previous-manifest`
when that file is an intake manifest of this batch and this stem, written while no run
directory of the stem existed, with the same seed and count, and every chosen family still has the review basis it had
then; otherwise `subset_after_measurement` or `subset_family_changed`. An earlier manifest
is a file the caller supplies, so these are consistency checks and not proof of when it
was written. A restored subset therefore has the status `restored_from_earlier_manifest`
and `outcome_selected: not_verified_by_this_command`, never `selected_before_outcomes`;
its `timing` field says that the commit which added the earlier manifest is the evidence.
A subset is not restored when one of its families is no longer an owner-kept, unflagged
discovery family (`subset_family_not_candidate`). For the same reason no family of a
measured batch is reported as eligible for a confirmatory statement
(`split_timing_not_verified`): eligibility is read from a manifest written before
measurement. A split or a subset is assigned only for a named `--stem` (`stem_required`),
and without a stem no family is reported as eligible (`stem_not_named`): the command has
not looked for measurements. The stem is the caller's statement of where the batch's
measurements land; the command does not check that statement. A protocol counts as signed
only when its status begins with the word `signed`. The manifest records the validation
parameters the caller set (`software_validation.parameters`). A concern is withdrawn only
by whoever raised it. The mechanistic
subset is a seeded draw from owner-kept, unflagged discovery families that no review has
removed, so it is not outcome-selected, and its estimate includes the three controls per
site. With `--pairs-file` every row of the lane's input is accounted for: a contrast is
`identical`, `differs`, `absent` or `duplicated`, rows with a repeated or missing id are
listed, and `lane_input.clean` is true only when no such row exists and no contrast
`differs`. Absent contrasts and rows of other batches are listed, not judged.

**Tokenization.** Alignment classes (`position_aligned`, `suffix_aligned`) are computed
only from `--tokenization` records of real token ids (every prompt and target value a
non-empty list of integers; anything else refuses `invalid_tokenization`). Without one the
manifest says `not_recorded`. No family is rewritten to reach a class.

**Repeated inputs.** Several inputs can be passed more than once, and the order of the
arguments never decides a result or a byte of the output. Owner reads: the read made at
the later instant applies (`owner_read_utc` is parsed as a time, offsets included); two
reads that cannot be ordered (the same instant, or a time missing from either) and differ
in any recorded field (decision, reasons, note, batch version, or whether a time was
recorded) refuse `conflicting_verdicts`.
Reviews of one role are combined item by item, and their reviewers are listed by name and
date. Source checks of one citation must agree (`conflicting_source_checks`). Tokenization
files of one tokenizer are merged, and one prompt with two different id lists refuses
`conflicting_tokenization`. Split records that disagree refuse `split_conflict`; the
manifest numbers the accepted records by seed, not by argument position. A
repeated concern id refuses `invalid_concerns`, and a family's concerns are listed by
concern id. Models are listed once each, by study id. A `--prior-batch` label names one
file; the same label twice refuses `invalid_input`. Earlier batches are compared in label
order, so a text held by two of them is reported against the same one each time.

**Reruns.** The same inputs give byte-identical outputs. An existing output with the same
bytes is `unchanged`; with other bytes the command refuses `output_differs` and writes
nothing. Output paths follow *Where output may go* below. Exit 1 means software
validation found an error; the three files are still written so the errors can be read.

## Three things kept apart

**Execution state** says what happened to a task: `not_run`, `unsupported`, `unavailable`,
`invalid`, `failed`, `completed`. A finished task with a zero or opposite-direction effect
is `completed`. `unsupported` means the capability matrix says the combination cannot run.
`unavailable` means it could in principle, and a required input is absent or its identity
is unknown.

**Evidence and visibility** come from the [open-results policy](../open_results_policy.md):
evidence class, clinical-review status, visibility, restriction reasons, analysis
memberships. A fixture run is `synthetic_fixture`, `not_published`, in no membership.
The protocol and envelope validators check these labels against the committed policy
(`data/results_policy/policy.v1.json`, read through `scripts/results_policy.py`):

- `evidence_class` is a class a model cohort or a stimulus class declares, or `unclassified`
  (what the policy assigns where no entry declares one). A synthetic document says
  `synthetic_fixture`.
- `clinical_review` is a review status a stimulus class declares. A synthetic document says
  `not_applicable_synthetic`; no other document may.
- visibility is `public`, `restricted` or `not_published`; `restricted` needs at least one
  reason and `public` needs none.
- each restriction reason is a restriction name the policy declares (`sealed_holdout`,
  `redistribution_limited_text`, `artifact_integrity`, `uncalibrated_clinical_mass` in policy
  version open-results/1), alone or followed by `:detail`.
- every analysis membership is a name the policy declares.

Visibility and analysis membership are not coupled, because the policy keeps them
independent: the restricted-text stimulus class is inside `study-interim/1` in policy
version open-results/1, so a `restricted` document may name a membership. These are checks
of labels only. Whether a membership rule admits a result, and which restriction applies to
it, is decided by `scripts/results_policy.py` on a landed part.

**Capability status** says what is known about a model revision, method, backend and
artifact, weakest to strongest: `unsupported`, `architecture_supported`,
`artifact_available_identity_unknown`, `artifact_available`,
`runtime_verified_offline_fixture`, `parity_passed`. Each row of
`data/experiments/capability_matrix.v1.json` cites its evidence. "The architecture is
supported" and "this combination passed parity" are different rows. On 2026-11-10 no row
is `parity_passed`. The one row that held that status (gemma-2-2b next-token behaviour
through interp-engine in float32 against the hosted service) was lowered the same day and
is `artifact_available_identity_unknown`: the cited records
(`docs/backend_agreement_20260903.md`, `ops/backend_agreement_interp_vs_hosted_20260904.json`)
state no pass criterion and no verdict for that comparison, cover 71 of 100
side-measurements, and record no checkpoint revision. The row's status note carries the
agreement numbers. The two hosted attribution-graph rows are
`artifact_available_identity_unknown` for the same reason: no model revision, artifact
revision or artifact hash is recorded for them.

`artifact_available` and every status above it need a recorded identity: the row records a
model revision, or an artifact revision or SHA-256. `validate_matrix` refuses a row that
holds such a status without one (`unpinned_status`). A row that records no model revision
answers a lookup for any revision, and never with a status above
`artifact_available_identity_unknown` when the lookup names a revision. The bundle's
capability rows carry `revision_match`, which says whether the row names the protocol's
revision (`exact`) or records none (`row_revision_not_recorded`).

## Identity, attempts and replicates

`spec_sha256` is the digest of what a task computes: protocol hash, family, variant, model
identity, the full method block, input hashes and settings. Attempt and replicate numbers
are not part of it. The store key for reuse is `(spec_sha256, replicate)`:

- a resumed run reuses a completed, hash-verified envelope and does not execute the task
  again, provided the inputs outside the spec are unchanged (next paragraph);
- a changed protocol input or setting changes `spec_sha256`, so nothing is reused, and the
  old run directory refuses the new plan (`incompatible_resume`);
- replicate 1 is executed even when replicate 0 is complete. A cached response is never
  counted as an independent repetition.

The fixture files and the adapter code are not part of the protocol, so they are not in
`spec_sha256`. Each envelope records them instead: `environment.source_files_sha256` (the
adapter module and `scripts/exploratory_methods.py`) and
`environment.input_identity_sha256`, a digest the adapter computes over the hashes of the
files a task reads (its optional `input_identity` hook). A completed envelope is reused
only when both still hold. When one differs, the task is executed again as a new attempt
and counted as executed. An adapter without the hook has a null identity recorded in
`not_recorded` and is reused on the payload hash and the source hashes alone.

What `collect` does with a task that was executed again under changed inputs:

| The new attempt | `collect` |
|---|---|
| completed with the same payload bytes | keeps one envelope and lists the other in `duplicate_identical` |
| completed with other payload bytes | refuses `duplicate_conflict` and says that the recorded inputs differ; the plan needs a new run directory |
| did not complete (failed, invalid, unavailable) | sets the earlier completed envelope aside: the task is collected in the new attempt's state, is not counted in `ready_completed`, and is listed in `completed_under_superseded_inputs`; `collect --require-complete` exits 1 and the bundle carries the limitation `completed_results_under_superseded_inputs_not_counted_see_execution` |

The third row applies when the later attempt's `started` journal line records that a
completed result was not reused, or when its envelope records other adapter source hashes or
another input identity than the completed envelope. A later failure under the same recorded
inputs (a second worker's transient error) does not set a completed result aside. A result
that was set aside counts again once a later attempt completes, or once a run that began
after the failed attempt had ended reuses it because the inputs it recorded are in place
again (in the journal, the reusing run's `run_started` line follows the attempt's `ended`
line). A `reused` line from a run that was already going while the attempt ran does not
count: two workers on one run directory can be given different fixture directories.

Across tasks, `collect` requires that the completed envelopes of one method can all be
taken from one recorded pair of adapter source hashes and input identity, and refuses
`mixed_input_identities` otherwise. A resume under unchanged inputs always satisfies this.
After an edit that leaves the payload bytes unchanged, a task may hold two completed
envelopes; the one recorded under the pair that covers every task is kept. An adapter's
`input_identity` therefore identifies the inputs of the method's whole task set in a
fixtures directory, not one task's rows. `compare` checks the two sides of each block
again and refuses with the same code, and the behaviour block refuses `payload_mismatch`
for two payloads that name different fixture files.

A completed envelope for a task the plan does not mark `ready` refuses
`plan_state_conflict`, at any attempt number. This happens when the plan was built again
under another capability matrix or adapter set than the one the envelope was written under,
or when an envelope was put in a shard by hand.

Run directories written before engine commit `66514e0d` are not collected by this version
when they hold an envelope of a ready task that ended `unavailable` at preflight: that
commit stopped recording a runtime for such an attempt, the validator now refuses the older
shape (`resources_rule`), and the envelope schema version did not change. No converter
exists. Run the plan again in a new run directory.

The journal records a line before a task starts and another when it ends. A start without
an end and without an envelope is listed as an uncertain attempt and is kept. A start
without an end whose envelope is on disk is listed as `ended_line_missing`: its outcome is
known. The store does not claim exactly-once execution; for a paid call, an uncertain
attempt and its reservation are what reconciliation needs.

Concurrent workers write separate shard directories. `collect` is the only assembler: it
sorts, verifies every payload hash, checks each envelope's family, variant, method and
input against the planned task, keeps one of identical duplicates, refuses two completed
envelopes that name different payloads, and lists planned tasks with no envelope. When two
workers' attempts of one number ended in different states (one failed, one completed), the
completed envelope is kept, the difference is listed in `attempt_outcomes_differ`, and the
bundle carries a limitation that names it. `complete` means every planned task has an
envelope; `ready_complete` means every ready task has a completed one that counts. The
bundle lists a limitation when ready tasks did not complete and another when no task
completed.

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
names it. Inside a run directory, `payloads/`, `shards/`, each shard directory and
`journal.jsonl` must be real entries: a symbolic link in their place refuses
`run_dir_symlink`. The paths are checked when the store is opened, before a run and before
every assembly. Each payload and envelope is then written through a descriptor of its
directory, opened one component at a time without following a link, so a link created
during a run takes no write; each journal line is appended through a descriptor opened the
same way. Two limits: a directory above the run directory that is replaced by a link after
the store resolved its path is not detected, and on a platform without directory
descriptors (Windows) the store checks the paths right before each write, which leaves an
interval between the check and the write. Fixture output therefore cannot reach a
measurement collector, the site's data or a historical manifest through a run directory on
the platforms the project runs on (Linux).

## What was verified, and what was not

| Statement | Evidence |
|---|---|
| The slice runs end to end on synthetic fixtures, with interruption, resume and reuse | `tests/test_experiments_slice.py`: 45 tasks; 5 executed, then 22 with 5 reused; a third run executes 0 |
| Each named refusal fires | `tests/test_experiments_core.py`, `tests/test_experiments_store.py`, `tests/test_experiments_compare.py` |
| The ICA adapter agrees with the `icalens` library on toy data | `tests/test_experiments_ica_icalens.py`, run in an isolated environment with torch 2.13.0 and icalens 0.4.0 |
| The existing exploratory contract is unchanged | `tests/test_exploratory_methods.py` passes; its fixtures are byte-identical |
| Batch intake keeps review layers, strata, splits and outputs as stated | `tests/test_experiments_intake.py`, on eight placeholder families |
| Any real model | not verified. No model was loaded. Fixture timings say nothing about a model run |
| Any measurement validity | not verified. Toy values are chosen by hand so that expected results are computable |

The next step that involves a model is described in
[first_model_run_packet_20261110.md](../exploratory/first_model_run_packet_20261110.md).
One non-synthetic protocol is committed,
`data/experiments/protocols/first_run_stage_a.protocol.v1.json`: 3 rows, 6 planned tasks, all
`unavailable`, none executed. It
needs a declared model, reviewed case families, verified artifact identity, a resource
plan, an admission route and a fresh parity result. None of those is supplied by this
package.

## Adding a method

[contributing_a_method.md](../contributing_a_method.md) is the procedure. In short: a new
payload kind with its own schema, an adapter module that exposes `ADAPTER`, one line in
`ADAPTER_MODULES` in `scripts/experiments/adapters/__init__.py`, capability rows with
evidence, a fixture with hand-computable expectations, and tests for each refusal.
