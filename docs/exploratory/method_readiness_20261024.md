# Method readiness for the action-annotation pilot — 2026-10-24

This is a dated wiring and revision check, not a reanalysis of past experiments or
a certification that every past case has every method. The engine base inspected
is `94c0c047be44275b3aea9eef9abd3dc3b20d6ced`. No measurement, dependency pin,
fork branch, deployed service or existing execution-readiness record was changed.

Keeping research current means retaining the version that produced each result,
evaluating newer versions separately, and reporting missing coverage. It does not
mean overwriting past experiments to make them appear to use today's software.

## Current connection and next step

| Method | Verified connection / status | Next bounded step before new research use |
|---|---|---|
| Circuit tracing | `medlang_circuits/graph_client.py` and `batch_eval.py` use hosted Neuronpedia. Local source and pinned model identity do not attest the hosted server commit. Existing calibration/publication gates and historical target-read limitations remain. | Recheck the hosted schema and returned model/method metadata for the exact approved model; preserve raw provenance and explicit missing server identity. New sentinel/trace runs require their existing execution route and approval. Do not claim retrospective correction of affected target reads. |
| J-Lens / Logit Lens | `scripts/jlens_readout.py` exposes `JACOBIAN_LENS` and `LOGIT_LENS`; this does not establish a hosted J++ API. Existing readouts are separate from original output logits. | Before a new comparison, require same prompt bytes/tokens, capture/normalization conventions, shared layers, full-vocabulary versus filtered ranks and exact/prefix match identities. Preserve absent metadata as unknown; do not rename fallback data. |
| J++ | Owner PR #1 is merged at `19339c9617ca5907337ad912c42c2ea0777cb8f7`; reviewed head `1b0c3ffcfa152d3b0697ad852838183ffeac56ba`. The merged `uv.lock`, `pyproject.toml` and `src/lens_interop/artifact.py` hashes match that head. Upstream `d7efc0de372e20589e899188c0cfe8434acc63ec` adds one README-only commit above the incorporated upstream `93f02cd6c27db765abb127f20eff656bb5d27340`; no new runtime delta in that comparison. | Preserve the installed isolated environment and safe checkpoint loader. Historical released-lens fit model/tokenizer revisions remain unknown in the existing inspection receipt. That blocks a verified same-model lens comparison, not action annotation or the lens-independent baseline. No released-model lens comparison was run here. |
| Petri | Engine lock still pins owner harness `e199ec1abcd10267c60cd7eb03035a76567d9e52`, also owner fork main. Current upstream is `128f61d56776169e5030135eede930783ab7fcc3`, ten commits ahead. | Review a candidate harness/environment update separately, prioritizing synthetic-tool and resource boundary fixes. Inspect AI/Scout/SDK dependency changes cannot be promoted by changing the harness SHA alone. Preserve historical instruments and separate primary/secondary judges. Rehearse eligible historical rejudges before any separately authorized paid run. |
| interp-engine | `constraints.txt` pins PyPI `1.5.1`; `scripts/verify_probs.py` and `depth_probe.py` consume the package, not an automatically synchronized owner fork. Direct PyPI JSON metadata reports latest `1.14.2`; pinned `1.5.1` remains available and not yanked. Current upstream main is `c042cd3c21a54bfcbf14bf3a7e41d0a2f359dcd5`. | Prepare an isolated candidate against the current pin, check exact model/tokenizer, backend, positions, normalization and output parity before promotion. Newer package version is not evidence of compatibility. Do not upgrade the engine environment or recalculate historical scores in place. |
| Causalab interventions | Owner main remains `7efb9d3e88632f4e7f8eba353b487108885b451b`, with the corrected safe workflow. No open adapter PR was returned. Local refreshed adapter `e099b181b35529af60cbccba219b8b877aa97797` is clean and remains separate from the editable-install checkout. | The existing handoff identifies a format-only blocker in its test file. Complete that focused correction/review before an adapter PR; then obtain an approved execution pin. Mac installation and tiny synthetic hook tests are not original-model parity. |

The hosted Neuronpedia source repository currently has main
`1800b1984e01fb39890162370103d3baf325b482`. This is a GitHub source identity,
**not** the service's deployed revision. Synchronizing an owner fork would not
update or certify that service.

The previous Petri audit covered nine of the ten upstream commits. The newly added
`128f61d5` changes development/docs dependency grouping (`CONTRIBUTING.md`,
`pyproject.toml`, `uv.lock`). This metadata check did not install or test the newer
harness. The earlier tool-boundary and dependency changes still need a focused
candidate evaluation; their presence upstream is not proof that a particular
historical PatientWords run was affected.

## Keep past and ongoing experiments interpretable

For each future approved case-family protocol, name applicable methods and record
each as available, not run, incompatible, provenance unknown, or not applicable.
Use existing batch/index/model joins and exact source hashes. Record prompt/token
identity, method/version, model/tokenizer revision, capture site, positions/layers,
numeric settings and execution source. Do not replace a historical manifest or
infer missing historical identity from a current checkout.

Not every method applies to every experiment: Claude API responses support behavioral
and action analyses but do not expose the hidden states needed by circuit/lens or
native-component interventions. Do not attach a surrogate model's internals as if
they came from the API assistant. Model-generated wording remains labeled as such.

Priority order for the existing mechanistic path:

1. Finish the small Causalab adapter review route independently of this annotation PR.
2. Establish the actual Linux environment, runner allocation/cost, approved exact pins
   and seal attestation required by `baseline_ci_readiness.v1.json`. It still records
   `blocked_not_authorized`, null Causalab/runner/budget fields and unreviewed Linux
   runtime. Do not fill these from assumptions or Mac install receipts.
3. Separately authorize the existing one-case **original-output baseline parity**
   check, with its fixed tolerances and settings. No lens checkpoint is needed.
4. Only after parity, complete and validate the real-case intervention execution/report
   path using the existing controls and family split. Tiny-model adapter tests do not
   establish that this end-to-end research path works.
5. Compare lenses only when historical fit compatibility is established. Keep full
   output logits separate, retain wrong-answer and null-effect cases, and validate
   any future interp-engine/Petri update against its old pinned environment.

The annotation pilot can proceed through offline development while those steps and
physician realism ratings are pending. Its next API step still requires reviewed
CI/budget wiring and explicit execution authorization. No automatic update monitor,
new research schedule or retrospective run was enabled by this check.

## Sources and evidence limits

- Local authorities: `constraints.txt`, `docs/framework/petri_environment.lock.json`,
  `data/exploratory/jpp_artifact_inspection.v1.json`,
  `data/exploratory/baseline_ci_readiness.v1.json`, `docs/exploratory/baseline_ci.md`.
- [Merged J++ PR](https://github.com/michaeldgreenphd/patient-words-jpp_lens/pull/1),
  [J++ upstream delta](https://github.com/safety-research/jpp_lens/compare/93f02cd6c27db765abb127f20eff656bb5d27340...d7efc0de372e20589e899188c0cfe8434acc63ec).
- [Petri upstream delta](https://github.com/meridianlabs-ai/inspect_petri/compare/e199ec1abcd10267c60cd7eb03035a76567d9e52...128f61d56776169e5030135eede930783ab7fcc3).
- [PyPI current metadata](https://pypi.org/pypi/interp-engine/json) and
  [pinned release metadata](https://pypi.org/pypi/interp-engine/1.5.1/json).
  These are metadata observations; no wheel was downloaded or installed. The cached
  PyPI HTML page returned older information, so the current-version observation uses
  the direct JSON response. Package-to-source byte identity was not established.

The local October 16 runtime-identity and adapter-refresh receipts remain historical
evidence. This pass rechecked current refs and the three named J++ hashes; it did not
repeat installations, replay every historical run, inspect sealed stimuli or produce
new scientific results. Fresh offline test results belong in the task handoff.
