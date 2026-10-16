# Manual baseline CI preparation — blocked, not run

This draft wires only the lens-independent preflight in
[baseline_preflight.md](baseline_preflight.md). The owner explicitly authorized
preparing a manual-only route for review, superseding the earlier assumption that
this check had to add a push-to-run lane. That exception does not change any
production trigger, parked default, budget gate or queue tool. No workflow has
been dispatched, no Qwen weights downloaded, and no real-model output produced.

## Execution remains blocked

`data/exploratory/baseline_ci_readiness.v1.json` deliberately contains no approved
runner, runner budget, execution-ready status, Causalab execution commit, Linux
runtime approval, or current seal attestation. The helper reports each missing
prerequisite. Setting the dispatch's `execute=true` cannot override them.

Runner evidence checked on 2026-10-16 UTC:

- The owner engine repository's Actions runner inventory returned
  `total_count=0`: no registered self-hosted runner.
- Historical engine job `115307894442` in run `38399607622`, labelled
  `ubuntu-latest`, reported 15 GiB physical RAM / 14 GiB available at
  2026-10-13T12:55:57Z. Its 14 GiB swap does not count as RAM.
- No existing runner with the required 64 GiB RAM, 8 CPUs and 40 GiB free disk,
  current availability, and a verified zero incremental charge has been
  established. Do not infer this from public-repository status or rent capacity.

The proposed model job requires an already registered Linux x86_64 self-hosted
runner with a unique label and its exact recorded runner name. A different runner
class would require a reviewed readiness/helper change. Nothing provisions,
registers, pays for, or changes permissions on a runner. Effective capacity is
checked before dependency/model downloads: physical RAM intersected with every
enclosing cgroup memory limit, at least 32 GiB currently available, CPU affinity
intersected with CPU quotas, and actual free disk. Swap is excluded. Unknown
cgroup layout refuses. These are conservative predeclared requirements, not a
measured Qwen resource claim.

## Trust and default-branch prerequisites

`.github/workflows/exploratory_baseline_preflight.yml` has only
`workflow_dispatch`; there is no push, PR, schedule, workflow-call or privileged
PR event. Permissions are `contents: read`, checkouts do not persist credentials,
no repository secret is referenced, and concurrency has cancellation disabled.
Only the repository owner may dispatch or rerun this owner-repository workflow
from `main`; both the original actor and triggering actor must be the owner.
The model job cannot start until the lightweight readiness job succeeds. The
three reused action commits (checkout, setup-python and upload-artifact) were
verified against their official repository commit APIs during this preparation.

The workflow must be owner-merged onto the engine default branch before manual
dispatch is available. A draft PR does not meet that prerequisite. After review,
an owner-merged readiness update must identify an exact Causalab commit already
on the owner fork's `main`. Public GitHub metadata must confirm that exact commit
is an ancestor of that default branch; failure/rate-limit errors refuse. There
are no dispatch inputs for arbitrary repositories, refs, commands or model IDs.
The engine uses the exact default-branch dispatch commit. Both worker captures
verify clean checked-out commits against the generated execution record.

Default-branch ancestry relies on the owner's merge/review process; it does not
claim that GitHub cryptographically certifies a human review. The prepared fork
PR heads are cross-repository review dependencies until that process completes.
J++ is neither checked out nor installed and its fit provenance is not a gate.

The readiness seal attestation must identify the unchanged source-spec hash, a
clean current seal-check artifact hash and review reference, with a UTC time no
more than 24 hours old. No seal content is embedded in the record. Preparing this
workflow does not read any sealed holdout. Refreshing that attestation belongs to
the separately authorized execution preparation, not an automatic discovery task.

## Bounded runtime and artifacts

The prospective original-output comparison retains the plan's model/tokenizer
revision `1cfa9a7208912126459214e8b04321603b3df60c`, exact prompts, tokenization,
mask/position checks, six sequential forwards, CPU bfloat16, SDPA, seed 7, and all
predeclared numerical gates. Passing top-1 alone cannot pass the comparator.
Missing or mismatched data fails; no lens, hook intervention or generated answer
is involved.

The draft workflow uses separate fresh Python 3.12.14 virtual environments under
`RUNNER_TEMP`; it does not modify the checked-in environment constraints or the
owner's local environment. Engine core packages retain `constraints.txt` pins,
with the exact Linux distribution build `torch==2.13.0+cpu` now explicit in both
the plan/readiness record and install command. Before model metadata/downloads,
each independent interpreter checks its installed distribution versions and
Python version and writes a plan-bound receipt. Missing, mismatched or stripped
build suffixes refuse; staging requires both matching receipts.

The official [CPU wheel index](https://download.pytorch.org/whl/cpu/torch/) and
[PEP 658 metadata](https://download-r2.pytorch.org/whl/cpu/torch-2.13.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl.metadata)
were read without downloading or installing the wheel. The metadata reports
`Version: 2.13.0+cpu`; its 37,906 bytes hash to
`b3c7f4b3f77d06f86a42aab7d0facef7b661ca3c22967bfcc396917d935dd335`,
matching the index. The advertised wheel digest is recorded as advertised in the
plan, not claimed as a locally verified wheel hash.

Causalab uses `requirements.lock.txt --require-hashes`, its existing pinned Rust
toolchain, `Cargo.lock --locked`, and an editable compiled source installation.
A missing Rust prerequisite fails rather than installing a system toolchain.
The Linux setup has **not** run. Engine constraints and the upstream maturin build
range are not full transitive/build locks; the runtime-review readiness field
remains false until that reproducibility limitation is reviewed or resolved.
Do not describe this draft as two fully hash-locked Linux installations.

Model staging first reads only the immutable Hub metadata, refuses unknown sizes,
requires weight SHA-256 metadata, and caps the selected safe-format files at
10,000,000,000 bytes. It downloads only safetensors and required JSON/tokenizer
files, verifies actual lengths/hashes, and stores a per-file receipt. Pickle
weights, model code and unrelated repository files are excluded. Both captures
then run with Hub/Transformers offline mode against that shared cache.

The weight estimate is **8,044,936,192 bytes**, derived from the pinned geometry
and bfloat16 storage, not an observed transfer. Headers/tokenizer/config and two
runtime installations add disk use; the latter's total download size is still
unmeasured. The 40 GiB minimum is a **remaining reserve**, checked again before each capture
after dependencies and weights exist. Before staging, the helper requires free
disk for that reserve **plus** the previewed safe-file download. Thus an initially
40 GiB-free runner is insufficient; the owner must establish additional space for
the roughly 8.04 GB model plus both environments and build/cache files. A model job is capped at 60 minutes including setup and
staging, each capture at 900 seconds, dependency setup at 20 minutes and staging
at 15 minutes. The separate lightweight readiness job is capped at 5 minutes.
Provider budget and incremental runner budget are $0; zero runner cost still
needs evidence and owner approval.

Outputs live only under the runner's external
`exploratory_methods/baseline_preflight/` directory and a 14-day CI artifact:
execution record, readiness/capacity receipts, model inventory/hashes, dependency
freezes/input hashes, full-vocabulary captures, comparator output, bounded worker
logs and job status. They do not match existing collector names. Failure keeps
partial receipts; a vanished runner or hard timeout can prevent artifact upload
and is itself a failed preflight, never an agreement result. Nothing commits,
publishes or changes established measurements.

## Later commands, not authorization

Safe local readiness validation (no network or runtime imports):

```bash
python scripts/exploratory_ci_preflight.py
python -m pytest -q tests/test_exploratory_ci_preflight.py
```

After the workflow reaches the default branch, this manual call still only lists
readiness blockers and must be separately authorized if CI billing is uncertain:

```bash
gh workflow run exploratory_baseline_preflight.yml \
  --repo michaeldgreenphd/patientwords-engine --ref main -f execute=false
```

Only after owner review/merge, all readiness prerequisites, and a new explicit
execution authorization would the one-case model job be dispatched with:

```bash
gh workflow run exploratory_baseline_preflight.yml \
  --repo michaeldgreenphd/patientwords-engine --ref main -f execute=true
```

Inspect the existing concurrency group first: at most one running and one pending;
do not enqueue another request that would evict a pending job. The command has
not been run in this work. Its inputs cannot activate today's blocked readiness
record. Next smallest step is identifying suitable **existing** capacity and its
cost, not lowering the resource threshold or provisioning a runner.


## Workflow validation correction

The first draft-branch push produced a workflow-validation failure
([run 38836042869](https://github.com/michaeldgreenphd/patientwords-engine/actions/runs/38836042869))
with **zero jobs**. It did not launch the manual readiness or model job. The draft
had used five `runner.temp` expressions in job-level `env`, where GitHub does not
allow the `runner` context. YAML parsing alone had missed this platform rule.

Those paths now initialize in the first allocated-runner step through
`GITHUB_ENV`; failure-artifact paths use the context only at step scope. The
regression checks the documented
[context-availability boundary](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability).
The official actionlint 1.7.12 structural checker reproduced all five errors on
the pushed version and reports no errors on the correction. Its temporary
2,164,202-byte arm64 archive was verified against the release SHA-256
`aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f`;
no environment package was installed. The workflow remains manual-only and the
readiness record remains blocked. Neither a manual dispatch nor a model run was
performed to validate this fix.
