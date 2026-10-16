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
| Engine | `codex/exploratory-methods-contracts`, continued from `e816cd123b926e2e35c27c31b0cd64da7250bf08`; executable source at `b6b7b10abe05ee9ab852e049f3357038b8adeed4`; final documentation head is in its draft PR | [Owner draft PR #121](https://github.com/michaeldgreenphd/patientwords-engine/pull/121) against `main`; communication `70ac359f`, preparation `73bb882f`, manual CI `faf315d0` |
| J++ | `codex/lens-interop-contracts` at `1b0c3ffcfa152d3b0697ad852838183ffeac56ba` | [Owner draft PR #1](https://github.com/michaeldgreenphd/patient-words-jpp_lens/pull/1) |
| Causalab | `codex/paired-intervention-adapter` at `91291aa75aa19918e56f3d15ff87e9dbbe165afa` | [Owner branch](https://github.com/michaeldgreenphd/patient-words-causalab/tree/91291aa75aa19918e56f3d15ff87e9dbbe165afa); PR opening blocked as below |

The released lens is unchanged outside Git. Its SHA-256 is
`893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d`;
config SHA-256 is `6cf51651e2dfaab696cf86ce9e183738b53c9d6f4e3e7add428b6b20c451f957`.
Full embedded provenance was inspected. Historical fit-model and fit-tokenizer
revisions remain unknown. The [publisher question](lens_fit_provenance_question.md)
remains unsent. No lens compatibility gate was weakened.

## Push and pull-request safety audit

At the initial push audit all remotes pointed only to the owner's repositories,
all defaults were `main`, and all three proposed remote branches were absent.
The finalization audit rechecked the existing pushed branches and live workflows
on 2026-10-16; its current recommendations are below. Relevant local
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
  A future merge also starts the full suite through `push: branches: [main]`;
  marking the PR ready additionally invokes the credential-backed Claude review.
  The owner must first approve a safe review route or land a narrowly reviewed
  base-workflow correction. That correction should retain test coverage while
  separating bounded read-only checks from explicitly authorized heavy tests.

Workflow states and exact final review heads are reported in the draft PR bodies
and final handoff. Scheduled runs unrelated to these branches are not evidence
that this work launched them. Review is requested once per changed head; a quota
response stops further requests until the reset rather than causing retries.

## Code-only merge recommendations and order

- **Engine draft #121:** ready as inactive infrastructure after review of the
  final dispatch-assertion update and the owner's normal draft/merge decision.
  No production trigger, collector, measurement or frontend contract is changed.
  A merge makes the manual workflow available on `main` but does not dispatch it.
  Its readiness remains blocked; merging is not execution authorization.
- **J++ draft #1:** ready for the owner's code-only merge decision at exact head
  `1b0c3ffcfa152d3b0697ad852838183ffeac56ba`; the completed head-specific Codex
  review has no findings and all nine fixed threads are resolved. Neither main
  nor the branch defines an Actions workflow, so merging launches no repository
  workflow. Unknown fit revisions block transport, not this inactive adapter.
- **Causalab branch:** no draft exists because base
  [test.yml](https://github.com/michaeldgreenphd/patient-words-causalab/blob/8e8d5d1f8f9ca8f42bfce7c6b5eef194f012660e/.github/workflows/test.yml)
  starts heavy/privileged work on draft creation and full tests on main push.
  This is a review/merge-route blocker under the current authorization, not a
  failed adapter test. The owner must approve a safe base-workflow review route
  or separately authorize those effects. A head-only edit cannot guard the
  base's opening event. No protections or settings were changed to work around it.

Engine and J++ have no merge-order dependency; either can merge first. Causalab
need not merge before inactive engine infrastructure. Baseline execution later
requires the engine route, a reviewed readiness update and the exact reviewed
Causalab code on their owner default branches; J++ is not a baseline dependency.
The [post-merge verification procedure](baseline_ci.md#verify-final-integration-commits)
reconciles tested source bytes with new merge/squash SHAs before authorizing them.
No future merge SHA is invented or substituted for a tested source commit.

The live audit observed engine main at
`974ec914eb430f8a2f47278714fe17398f903e14`: the advance from the original base
changed only the scheduled backfill's operational journal. Existing workflow
blobs still match, and no trigger path is in this PR. The owner must preserve
main's current journal and trigger files during a merge. Its independent backfill
schedule continues unchanged; a later scheduled run is not an integration fire.
Both drafts reported clean/mergeable, with no current Actions check entries.
Those facts are not a substitute for independent review or owner approval.

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

## Verification of the review heads

| Check | Result and scope |
|---|---|
| Engine complete offline suite | **5,204 passed, 10 skipped in 254.97 s** at executable-source `4664014e5cf1e4de3af516615b5e1dc5215aea8e`; the later receipt/handoff commit changes documentation only. |
| Engine baseline worker | 71 targeted tests; original full-forward synthetic smoke and hook cleanup passed. |
| Engine contracts | 102 targeted tests, including missing/mismatched/non-integer execution-seed refusals. |
| Manual-CI helper and trigger docs | 68 targeted tests; invalid output paths return named JSON/exit 2 without a traceback or retry. |
| J++ final adapter/HF-layout selection | 129 passed, zero skips, 1.84 s at `1b0c3ff`; Codex review clean and all nine fixed threads resolved. |
| Causalab final edited-source selection | 62 passed, zero skips at `91291aa`; three unrelated offline-cache warnings. Earlier unchanged-runtime selection: 208 passed. |
| Final synthetic cross-repository bridge | 36 readout rows, 3 outputs, 10 interventions, zero real-model executions. |
| Ruff, actionlint, diff checks | Passed. Source receipt hashes match their declared commits. |
| Live frontend contract | 0 errors, 1 existing warning: 1,728/13,652 urgency rows have no published-scenario join. Existing stale vendor-pack notices remain. No site data changed. |

The ten full-suite skips are two unavailable `inspect_petri` checks, three
unavailable Playwright checks, two unavailable `inspect_ai` checks, one
not-yet-landed PAB workflow and two creation-guard tests inapplicable to workflows
without push events. Unrun checks remain explicit: full upstream fork suites,
CUDA, Linux runtime installation, released Qwen baseline, compatible real lens
readouts, residual/native-channel experiments, and comprehension review.
Software tests do not validate a clinical interpretation.

Commands actually run from the exploratory engine checkout, using the unchanged
engine environment:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/patientwords-review-final/fresh-bytecode \
  /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  -m pytest -q -rs -p no:cacheprovider
/Users/michaelgreen/patientwords-engine/.venv/bin/ruff check --no-cache .
/private/tmp/pw-actionlint-1.7.12/actionlint -shellcheck= -pyflakes= \
  .github/workflows/exploratory_baseline_preflight.yml
git diff --check
PYTHONDONTWRITEBYTECODE=1 /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  scripts/validate_frontend_contract.py --site ../patientwords
PYTHONDONTWRITEBYTECODE=1 /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  scripts/exploratory_baseline_preflight.py
PYTHONDONTWRITEBYTECODE=1 /Users/michaelgreen/patientwords-engine/.venv/bin/python \
  scripts/exploratory_ci_preflight.py
```

The baseline validation returns `prepared_not_executed`, with plan digest
`689062d03358a41fb665a87f91ff8b4e01001419a1f0daaa266314af565ac9cd`.
Readiness returns `blocked` with all six prerequisites unresolved: execution
approval, reviewed Causalab commit, suitable existing runner, verified zero-cost
allocation, reviewed Linux setup and current seal attestation. These dry checks
import no model runtime and perform no downloads or inference. Final suite log:
`/private/tmp/patientwords-review-approved-route-tests.log`.

## Verified corrections and artifact receipts

The engine worker captures actual aligned masks, positions and output indices,
verifies the offline tokenizer snapshot, and preserves the native whole-sequence
forward before selecting the final-token endpoint. Its synthetic runtime smoke
compared both complete `[1,2,16]` output matrices exactly with aligned direct
forwards and checked hook cleanup. The historical external installation receipt
is `/private/tmp/pw-review-installation-check/installation_checks/full_native_forward_v1/installation_check.json`;
it records worker SHA-256
`208d0e9de28e4deda7b0bb4e41daa8c5fab8ce666a46a10189ddeec1690a569b`.
Later path/Git refusal changes are covered by unit regressions; installation was
not repeated. The two Linux environments must verify exact package versions
before staging weights, including engine Torch `2.13.0+cpu`; only CPU wheel
metadata was inspected, not the wheel installed or downloaded.

The first engine push produced an unexpected workflow-validation failure:
[run 38836042869](https://github.com/michaeldgreenphd/patientwords-engine/actions/runs/38836042869),
with **zero jobs**. Five job-level `runner.temp` expressions were invalid in
GitHub's context. Commit `7c7f3b9091522ed341d60143052d9a6483879732` moves path
initialization to an allocated-runner step. Actionlint reproduced the original
errors and passes the correction. No dispatch or model run was used to test it.
The current manual workflow remains inactive on ordinary pushes/PRs; actual
post-push states and review status are recorded on draft #121.

The three engine review findings are addressed separately:

- `76e2ede0053d440e8d2bc3ae7df88cd43da83ba4` records the owner's existing narrow
  manual-route preparation authorization in canonical `AGENTS.md`. It grants no
  execution authority and leaves production triggers/budgets unchanged. Follow-up
  `4664014e5cf1e4de3af516615b5e1dc5215aea8e` keeps the rule within the unchanged
  30 KiB instruction budget; only adjacent wording was condensed, preserving
  every other rule. The full-suite size failure was corrected before pushing.
- `7408b7f59fe58d6430aac02e783fc0facf481578` preserves JSON refusals/exit 2 when
  receipt paths fail, without retrying an invalid primary output; an unavailable
  secondary failure receipt is reported separately from the original error.
- `cca937824b1ad1b208639b55f7cfe865b02ff73b` requires the packet's executed seed to
  be a strict nonnegative integer equal to the spec seed. Schema and synthetic
  fixture are explicit; missing data receives `execution_seed`, not a default.

J++ corrections preserve method, target, recipe and tokenizer identity; resolve
configured layer notation using the fitter's rules; and hash/deserialise the
same immutable byte snapshot. Transport is deliberately limited to the exact
independently audited Qwen model/revision/geometry tuple and the explicit
synthetic fixture. That topology audit does not establish historical fit
compatibility. Inspection remains available for unsupported artifacts. Snapshot
loading adds temporary memory for the serialized bytes; initial artifact timing
and peak-RSS receipts remain historical, not benchmarks of this newer loader.

The final bridge uses the same explicit `synthetic/toy` identity in both repos
and declares its fixture recipe. Its pre-fix run correctly refused the old
unaudited toy label; no real-case or released-artifact identity was changed.
The final seed-aware report is external at
`/private/tmp/pw-review-seed-contract/exploratory_methods/exploratory_report.adapter_bridge.json`,
SHA-256 `e11724b77f91474334a6e08f1372b2624a48bd76068331ae03e2a4af7acca030`.
The minimal Torch environment still warns that NumPy is absent; direct tensor
checks pass, and no dependency was installed to suppress the warning. These
counts describe software fixtures, not study samples or scientific findings.

## Finalization follow-up checks

This continuation preserved all three actual branches and clean starting trees:
engine `c62f9b0bd2aeb22c4e7927feafb0d87dba431380`, Causalab
`91291aa75aa19918e56f3d15ff87e9dbbe165afa`, and J++
`1b0c3ffcfa152d3b0697ad852838183ffeac56ba`. Neither method fork has an applicable
AGENTS.md; current engine instructions and both preparation handoffs were read.
No successful installation or download was repeated and no environment upgraded.
The runner inventory was rechecked read-only and still returned zero registered
self-hosted runners; no suitable capacity or budget was established.

Newly repeated checks on the unchanged fork heads: J++ **129 passed**, zero skips
(2.22 s), and Causalab **62 passed**, zero skips (3.66 s; three existing offline-cache
warnings). Causalab explicitly imported the checkout's edited adapter, exposing
only the prebuilt extension through a temporary package-path overlay; it did not
test the stale installed source. Both selected Ruff checks passed. At entry, all 30 source
receipt hashes matched the working trees and their declared commits. Both cached
lens files were rehashed successfully and remain read-only outside Git.

The baseline-plan dry run still reports `prepared_not_executed` with the unchanged
plan digest above. The live-site contract again reports 0 errors and the same
existing warning. Communication review found no missing requirements: 19 local
links, original prompt hashes, artifact mappings and the independent status
fields were checked; no formatter or extra endpoint was added.

Commit `b6b7b10abe05ee9ab852e049f3357038b8adeed4` addresses immutable execution
selection and attempt bounds: the manual input asserts the expected engine commit against `GITHUB_SHA`
without selecting code, and reruns refuse. The helper/worker/workflow-guard selection passed **150 tests, 2 skipped**;
Ruff and actionlint passed. Exact final commits and fresh full-suite verification
are recorded in draft #121's finalization summary. The preceding test table is the earlier source check,
not silently relabeled as a test of this update. Source hashes are refreshed to
the new executable-source commit in the companion receipt.

The first invalid-workflow run above remains historical and had zero jobs. No
baseline dispatch, research-weight download, new real-model finding, merge,
publication or recruitment occurred. Linux transport retry behavior, runtime
installation, runner cost/capacity and the other readiness blockers remain
explicit; they do not justify adding optional features to this preparation pass.
