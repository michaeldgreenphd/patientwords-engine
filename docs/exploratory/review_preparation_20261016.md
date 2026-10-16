# Review preparation — 2026-10-16 UTC

The software adapters and explanation plan are prepared for review. The next
scientific prerequisite is agreement between implementations of the unchanged
model. **No real-model PatientWords findings have been produced by this
integration. The Qwen baseline has not run.** No merge, deployment, publication,
paid job, runner provisioning, production trigger or publisher contact occurred.

## Scope and source identities

The existing three branches were continued without resetting or replacing them.
The [initial local receipt](local_preparation_20261015.md) preserves the actual
installation versions, commands, hashes and synthetic checks from that pass.
Its `local_preparation_sources.v1.json` is a historical source receipt, not a
current execution manifest. [The final source receipt](../../data/exploratory/review_preparation_sources.v1.json)
records the reviewed fork heads and exact executable-source hashes. Final execution will pin the reviewed engine dispatch
commit and the approved Causalab commit as described in [baseline_ci.md](baseline_ci.md).

| Repository | Review branch and commit | Review route |
|---|---|---|
| Engine | `codex/exploratory-methods-contracts`, continued from `e816cd123b926e2e35c27c31b0cd64da7250bf08`; executable source at `6265fc7cf029dc3144c4e1c611351ecc8fe8fd80`; final documentation head is in its draft PR | Draft against owner `main`; communication `70ac359f`, preparation `73bb882f`, manual CI `faf315d0` |
| J++ | `codex/lens-interop-contracts` at `28e75c5569a42ab9458c82b3d3f14f8d8567b7a4` | [Owner draft PR #1](https://github.com/michaeldgreenphd/patient-words-jpp_lens/pull/1) |
| Causalab | `codex/paired-intervention-adapter` at `91291aa75aa19918e56f3d15ff87e9dbbe165afa` | [Owner branch](https://github.com/michaeldgreenphd/patient-words-causalab/tree/91291aa75aa19918e56f3d15ff87e9dbbe165afa); PR opening blocked as below |

The released lens is unchanged outside Git. Its SHA-256 is
`893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d`;
config SHA-256 is `6cf51651e2dfaab696cf86ce9e183738b53c9d6f4e3e7add428b6b20c451f957`.
Full embedded provenance was inspected. Historical fit-model and fit-tokenizer
revisions remain unknown. The [publisher question](lens_fit_provenance_question.md)
remains unsent. No lens compatibility gate was weakened.

## Push and pull-request safety audit

At audit time all remotes pointed only to the owner's repositories, all defaults
were `main`, and all three proposed remote branches were absent. Relevant local
workflow blobs matched remote main. No indirect `workflow_run`, reusable workflow
or dispatch chain was found. Protected triggers, operational records, landed data,
owner hooks, dependency pins and frontend files are unchanged.

- Engine: existing measurement workflows are push-path gated and skip ref creation.
  Creating the branch can produce skipped run records but cannot run a measurement
  job. PR opening has no repository workflow listener. The new baseline workflow
  is manual-only, has read-only permissions and a blocked readiness record; it is
  inactive on pushes, PRs and schedules.
- J++: no repository workflow files; its push and draft PR launch no Actions jobs.
- Causalab: pushing this nondefault branch does not match its main-only push event.
  **Opening a main-target PR is unsafe in this scope**, including a draft. The base
  `.github/workflows/test.yml` uses `pull_request_target`, checks out the head,
  runs the heavyweight non-golden suite and can auto-push lint changes with a write
  token. A head-only workflow edit cannot protect the opening event. No PR was
  opened, no unrelated workflow disabled, and no repository permission changed.
  The owner must first approve a safe review route or land a narrowly reviewed
  base-workflow correction. That correction should retain test coverage while
  separating bounded read-only checks from explicitly authorized heavy tests.

Workflow states and exact final review heads are reported in the draft PR bodies
and final handoff. Scheduled runs unrelated to these branches are not evidence
that this work launched them. Review is requested once per changed head; a quota
response stops further requests until the reset rather than causing retries.

## Independent readiness states

| Dimension | Status |
|---|---|
| Local runtime | Causalab compiled extension and tiny synthetic installation checks passed. J++ inspection environment passed; full upstream J++ runtime is not installed. Engine environment unchanged. |
| Downloaded-artifact integrity | Complete pinned J++ file and adjacent config verified; originals unchanged outside Git. |
| Historical lens-fit provenance | Exact historical model/tokenizer revisions remain unknown after complete embedded inspection. |
| Study model/tokenizer compatibility | Unestablished; matching names, dimensions and hashes are insufficient. |
| Original-model baseline parity | Not run. Its preparation is independent of lens-fit provenance. |
| CI execution readiness | Blocked by review/default-branch prerequisites, Linux runtime review, suitable existing runner, cost confirmation and current seal attestation. |

No suitable existing runner was established. The repository has zero registered
self-hosted runners. Historical standard-runner evidence from
[run 38399607622](https://github.com/michaeldgreenphd/patientwords-engine/actions/runs/38399607622)
shows 15 GiB physical RAM and 14 GiB swap; swap does not meet the declared 64 GiB
physical-memory requirement. CPU count, free disk and current allocation/billing
were not established for a suitable runner. Do not infer free compute from the
zero model-provider budget or provision a runner to fill the gap.

## Prepared next check, not executed

Use only the unchanged reviewed, unsealed one-case specification. Model and
tokenizer are `Qwen/Qwen3-4B@1cfa9a7208912126459214e8b04321603b3df60c`.
Compare six forwards across two wordings: legacy engine, explicitly aligned
engine, and Causalab. No lens, intervention, generated continuation or new
clinical endpoint is included. The two environments retain their own pinned
Torch/Transformers/Accelerate versions. Engine constraints are not a complete
transitive hash lock; Linux runtime setup remains explicitly unreviewed.

Prospective gates apply to both wordings and both comparisons: maximum absolute
logit difference <= 0.125, RMS <= 0.02, maximum absolute probability difference
<= 0.001, target-token probability difference <= 0.0001, and equal top-1. These
are engineering acceptance criteria, not observed Qwen tolerances. Any missing
identity/input field, nonfinite vector, tolerance failure, timeout or OOM fails;
do not loosen limits after observing results.

Planned capacity: Linux x86_64, 8 logical CPUs, 64 GiB RAM and 40 GiB free disk.
Derived bf16 weight estimate: 8,044,936,192 bytes, excluding headers/tokenizer;
actual immutable file inventory must be previewed under a 10,000,000,000-byte
cap. Workers run sequentially with 900-second limits; whole model job 60 minutes.
Provider budget is $0. Runner/storage cost is unverified and execution refuses
until an existing nonbillable allocation and explicit zero-cost budget are
recorded. Artifacts stay outside Git and publication collectors under
`exploratory_methods/baseline_preflight/`, with partial failure receipts retained.

The exact later dispatch inputs and worker commands are in
[baseline_ci.md](baseline_ci.md) and [baseline_preflight.md](baseline_preflight.md).
The workflow must first be reviewed and owner-merged onto the default branch;
Causalab code must also be reviewed and on its owner's default branch. A subsequent
reviewed readiness change must pin approved code/capacity/budget and seal evidence.
Only then may the owner separately authorize execution. This task authorizes
preparation and draft review, **not that dispatch**.

## Communication foundation

The [communication plan](communication_plan.md), [existing-artifact mapping](case_report_mapping.md)
and [text storyboard](one_case_storyboard.md) are documentation only. The frozen
case keeps its Claude-generated pilot origin, brand/generic scope and limited
owner review; it is not a general literacy comparison or an actual patient quote.
All unrun stages remain visibly not run. No dashboard, audience recruitment,
formatter, new endpoint or patient-facing safety score was added.

## Review corrections and verification

The final worker observes actual aligned input masks, positions and output
indices instead of trusting copied settings. It verifies the tokenizer's offline
snapshot identity rather than relying on an init argument consumed by
Transformers. It uses Causalab's supported whole-sequence head read to preserve
the original complete forward, then retains the final-token endpoint. Git
identity failures and in-repository output paths receive named refusals.

The revised synthetic runtime smoke compared both complete `[1,2,16]` output
matrices exactly with direct aligned forwards and verified hook cleanup. Its
external installation receipt is
`/private/tmp/pw-review-installation-check/installation_checks/full_native_forward_v1/installation_check.json`.
It records worker SHA-256
`208d0e9de28e4deda7b0bb4e41daa8c5fab8ce666a46a10189ddeec1690a569b`;
the subsequent path/Git-refusal-only changes are covered by unit regressions.
The final baseline module passed 71 targeted tests. No installation was repeated.

The Causalab family restriction passed 62 final edited-source adapter/runtime
tests, zero skips; the earlier unchanged-runtime selection passed 208 tests.
Three warnings concerned unrelated offline fixture caches. The new Linux setup
records the exact verified CPU wheel version `2.13.0+cpu`, including its local
build suffix; both environments must pass exact-version checks before staging
weights. Only wheel metadata was inspected, not a wheel download or install.

Larger unrun checks remain explicit: full upstream fork suites, CUDA, Linux
installation, released Qwen baseline, compatible real lens transport, residual
and native-channel experiments, and independent comprehension review. Local
software checks do not validate a clinical interpretation.

J++ review fixes at `5a001cbfca8b69698a01908321a098aecce34876` reject ambiguous
matrix families, equal-target source layers, conflicting legacy estimator
metadata and tokenizer identities. All four findings received a fix-commit reply
and were resolved after verification. Final selection: **72 passed**, zero skips;
Ruff and diff checks passed. Re-review was requested once for the changed head.
Unknown historical fit identity still refuses transport; the explicit J++
method is not relabeled from its internal `rlens` recipe setting.

Second-round J++ fixes at `28e75c5569a42ab9458c82b3d3f14f8d8567b7a4` resolve
configured relative/duplicate/unsorted layer notation using the fitter's rules
and hash/load one immutable byte snapshot. Both new threads have fix replies
and are resolved; re-review was requested once for this head. **89 tests passed**,
zero skips. Snapshot loading requires additional temporary memory for the input
bytes; the earlier artifact-inspection timing and peak memory remain historical,
not a benchmark of this newer loader.

Engine contract hardening at `6265fc7cf029dc3144c4e1c611351ecc8fe8fd80` adds
source/prompt split checks, actual vocabulary/target matching, and explicit
`matched_to` random-control links with layer/size/scope agreement. Both schemas
declare the reference. Supplied synthetic fixtures are updated; no real case or
landed result changes. **91 targeted tests passed**. The external synthetic bridge
passed with 36 readouts, 3 outputs and 10 interventions, zero model executions:
`/private/tmp/pw-review-synthetic-contract-v2/exploratory_methods/`; report SHA-256
`29412585a2b990a3957a1f3c69b7821fad31697db9576f505f4de410747c2954`.
These counts describe software fixtures, not study sample sizes or findings.


## Final check inventory

At executable-source commit `6265fc7cf029dc3144c4e1c611351ecc8fe8fd80`, the complete
engine suite passed **5,188 tests with 10 skips in 253.84 seconds**. The later
handoff/index/source-receipt commit changes documentation only. Full-tree Ruff
and `git diff --check` passed. The live frontend contract returned **0 errors,
1 pre-existing warning**: 1,728 of 13,652 urgency rows have no published-scenario
join; it also reported existing stale vendor packs. No site data was changed.

The ten skips were two unavailable `inspect_petri` checks, three unavailable
Playwright checks, two unavailable `inspect_ai` checks, one not-yet-landed PAB
workflow and two creation-guard tests inapplicable to workflows without push
triggers. Full upstream fork suites and real-model tests remain unrun as above.

Commands run from the exploratory engine checkout (the interpreter and Ruff are
from the unchanged engine environment):

```bash
PYTHONPYCACHEPREFIX=/private/tmp/patientwords-review-final/fresh-bytecode \
  /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  -m pytest -q -rs -p no:cacheprovider
/Users/michaelgreen/patientwords-engine/.venv/bin/ruff check --no-cache .
git diff --check
PYTHONDONTWRITEBYTECODE=1 /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  scripts/validate_frontend_contract.py --site ../patientwords
PYTHONDONTWRITEBYTECODE=1 /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  scripts/exploratory_baseline_preflight.py
PYTHONDONTWRITEBYTECODE=1 /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  scripts/exploratory_ci_preflight.py
```

The baseline validation returned `prepared_not_executed`, with plan digest
`689062d03358a41fb665a87f91ff8b4e01001419a1f0daaa266314af565ac9cd`.
Readiness returned `blocked` with all six expected prerequisites unresolved:
execution approval, reviewed Causalab commit, suitable existing runner,
verified zero-cost allocation, reviewed Linux setup and current seal attestation.
These dry checks import no model runtime and perform no downloads or inference.
The full-suite log is external at
`/private/tmp/patientwords-review-complete-tests.log`.
