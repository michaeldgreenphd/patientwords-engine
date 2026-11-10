# Upgrade checklist: forks, runtime pins and the manifest

Use this when a fork is synced with its upstream, or when a runtime pin (`constraints.txt`, the Petri lock) is a
candidate for change. The two are different events and this procedure keeps them apart.

**State on 2026-11-10.** The owner synced the five method forks with their upstreams. That was a source sync. It
was not a runtime migration: no runtime test was run against the new source, no package was upgraded, and neither
`constraints.txt` nor `docs/framework/petri_environment.lock.json` changed. The engine still executes
`interp-engine==1.5.1` from PyPI and `inspect_petri` at commit `e199ec1a`. Every landed measurement and every
landed Petri run was produced by those pins. The map is [ecosystem.md](ecosystem.md); the machine-readable record
is `data/ecosystem/repositories.v1.json`.

What this checklist rests on. The interp-engine and Petri checks below come from reading both versions of each
package on 2026-11-10. None of them was executed: the dev container has no model weights, no torch and no Inspect
package. Treat each check as a thing to run, not as a result.

## 1. Record the state first

1. Run `python scripts/ecosystem_status.py --root <directory holding the clones>` and keep the output with the
   work. It reads; it never clones, fetches, pulls, installs or writes. Exit 0 means every compared value matches
   the manifest, 1 means a recorded value differs, 2 means the manifest is malformed.
2. Add `--remote` to compare remote tips. It compares tips only and cannot count commits ahead or behind.
3. A dirty working tree in a fork is printed. Find out what the uncommitted change is before going on; add
   `--fail-on-dirty` to make it an error.
4. If the manifest and the disk disagree before the work starts, correct the manifest in its own commit, with the
   evidence, before changing anything else.

## 2. Sync a fork without losing local patches

1. Never reset a fork to its upstream. `patient-words-jpp_lens` carries five owner commits (`src/lens_interop/`
   and its documents); a reset deletes them.
2. Merge the upstream's default branch into the fork's `main`. Keep the local commits. Do not rebase commits that
   a dated engine receipt names by hash (`data/exploratory/*.v1.json` record fork commits and file hashes).
3. Re-run the fork's own tests after the merge, in the fork's own environment, and record the command and the
   counts. On 2026-11-10 none of the five suites could run in the dev container.
4. If a merge conflicts in a file the owner changed, stop and report the conflict with both versions. Do not
   choose one side to make the merge pass.
5. Update `recorded_head` and `upstream_relation` for that fork in the manifest, in the same change as any engine
   file that cites the new head. Say in `basis` what was verified and how. Leave `head_vs_pin` alone: a new source
   head does not move the tested pin.
6. The dated receipts under `data/exploratory/` are byte-pinned and stay as they are. A new audit is a new file.

## 3. Evaluate a candidate runtime in isolation

1. Never edit `constraints.txt` or `docs/framework/petri_environment.lock.json` in place as the first step. Both
   are read by literal path in the workflows, so an in-place edit changes the next real measurement.
2. Write the candidate as a new file (a candidate constraints file, a candidate lock) and build a separate
   environment from it. `python -m scripts.petri_audit.cli verify-lock --lock <candidate>` already accepts another
   lock. The measurement workflows do not accept another constraints or lock path; a CI evaluation of a candidate
   therefore needs a reviewed workflow change or a separate workflow. That is a workflow change under
   [triggers.md](triggers.md), and firing it needs the owner's approval like any other fire.
3. Keep every output of a candidate run outside `trace_out/`, `data/`, `pilot/` and `ops/`. A candidate run is
   not a measurement.
4. A newer version is not evidence of compatibility
   (`docs/exploratory/method_readiness_20261024.md`). Do not recalculate historical scores in place.

## 4. interp-engine: checks before the pin moves

The engine pins 1.5.1; the fork source declares 1.14.3 and equals the PyPI 1.14.3 wheel for the package directory
(checked on 2026-11-10 with `diff -rq`). All seven call sites still accept the engine's arguments at 1.14.3, by
reading both sources. The differences are in behaviour.

1. **Install source.** Decide PyPI or a git install of the fork, and record it. Both scripts record only
   `interp_engine.__version__` (`scripts/depth_probe.py:66-70`, `scripts/verify_probs.py:79-83`), which cannot
   tell the two apart. Add the wheel hash or the commit to the recorded environment block before switching.
2. **Call signatures the engine uses.** Confirm each against the candidate:
   `load_model(hf_id, backend="eager", device="cpu", dtype=..., trust_remote_code=False, tokenizer=..., model_kwargs={"revision": ...})`;
   `sync_model(model)` with `.warmup()` and `.shutdown()`; `layer_logits(model, tokens, {"logit_lens": layers})`
   returning `out["logit_lens"][layer]` whose last row the engine reads; `generate_stream(model, tokens, max_tokens=1, n_logprobs=k)`
   whose first step's `.logits` the engine reads; `model.to_tokens`, `model.to_string`, `model.n_layers`,
   `model.tokenizer`, `model.hf_model.config`.
3. **Sampling defaults and inherited generation config.** In 1.5.1 `generate_stream` has `temperature=1.0`. At
   1.14.3 the default is `None`, resolved from the checkpoint's `generation_config.json`, read with no revision.
   The engine records raw `step.logits`, taken before sampling arithmetic in both versions, so the recorded
   probabilities are not expected to change; that expectation is from reading, not from a run. Pass `temperature`
   explicitly in `scripts/verify_probs.py` so the call does not depend on a file outside the pin, and confirm in
   the candidate that `.logits` is still the raw last-position vector.
4. **Reads outside the model pin.** At 1.14.3 an eager load calls `AutoConfig.from_pretrained` twice with no
   revision, and the first generation reads `generation_config.json` with no revision. For a model whose default
   branch has moved since its pin, these read another commit than the weights. Either hand in a pre-loaded
   `hf_model=` and `tokenizer=`, or record that these three reads are unpinned.
5. **Padded-position semantics.** The engine sends one unpadded prompt per call today. If batching is introduced:
   with an attention mask and no position ids, each row's positions count from 0 at its first unmasked token, and
   values at masked positions are not meaningful (computed from pad tokens on the eager backend, zeros on vLLM).
   Never read a masked position.
6. **Returned token positions.** Confirm that `to_tokens` returns `[1, seq]` with the same BOS handling, that
   `layer_logits` returns one row per prompt position in order, and that the row the engine reads is the final
   prompt token. Compare token ids between the two versions for every prompt in the parity set.
7. **Request isolation under batching, padding and prefix caching.** The eager backend has no prefix cache. The
   vLLM backends enable prefix caching and give each capturing request a unique salt; the fork's tests for this
   are GPU-only and were not read or run. Before any use of a batched or vLLM path, measure the same prompt alone
   and inside a batch and require equal logits within the stated tolerance.
8. **dtype.** Pass dtype explicitly and record it. Compare at float32 first: the recorded audit
   ([backend_agreement_20260903.md](backend_agreement_20260903.md)) found bfloat16 to be the largest per-pair
   error term, so a bfloat16 comparison cannot separate a version effect from a precision effect.
9. **Final normalization.** For one model per family, confirm that the last-layer `logit_lens` readout equals
   the model's raw output logits for the same prompt within tolerance, in both versions. On the eager backend
   the decode applies the model's own softcap and logit multiplier by default; a change there changes every
   depth curve.
10. **Parity run.** Re-run the same prompts on both versions before promoting. The instrument exists: `mode: verify`
    at float32 plus `scripts/backend_agreement.py`, with `trace_out/verify_pairs_20260710T011743Z__gemma-2-2b`
    as the 1.5.1 reference, and `mode: depth` on one model per family that has landed depth artifacts. The landed
    interp-engine artifacts record `inference.revision: null`, so the reference cannot be tied to a checkpoint
    commit; say so in the parity record.
    Do not re-fire `mode: verify` on that same batch with `commit_outputs: true`: the run would write
    `verify_summary.part_01.json` at the same path and replace the landed 1.5.1 reference, and the workflow
    uploads no artifact, so `commit_outputs: false` keeps only the job-summary text. Run the candidate on a
    batch with no landed verify directory
    ([first_model_run_packet_20261110.md](exploratory/first_model_run_packet_20261110.md) names one).
11. **Pins around it.** The fork's CI tests transformers 4.57.1 (configuration only) and the resolver's latest;
    the engine's 5.14.1 lies between them, untested by the fork. Python must be `>=3.11`.
12. **Offline doubles are not evidence.** `tests/test_model_pins.py` and `tests/test_depth_probe.py` replace
    `interp_engine` with a fake module and pass under any version.
13. **What the upgrade does not give.** There is still no activation-replacement spec, and the package applies
    Jacobian matrices it is handed but ships and fits none.

## 5. Petri and Inspect: checks before the lock moves

The lock holds inspect-ai 0.3.237 and inspect-scout 0.4.39. The fork head requires `>=0.3.276` and `>=0.5.3`, so
the lock cannot host the head. The engine's import surface (`audit_solver`, `target_agent`, `select_timeline`,
the target controller) still exists at the head, by reading. The Inspect and Scout side is unverified.

1. **Inputs to obtain.** A fork clone with history, or a fetch of `e199ec1a`, to diff the pin against the head;
   a Python 3.12 environment with the candidate packages; one raw `.eval` log written under the locked
   environment. Raw logs of landed runs are CI artifacts with 90-day retention
   (`.github/workflows/petri_audit.yml:730`). Secure one before it expires.
2. **Candidate lock as a new file.** It carries `python.version`, `harness.commit` (40 hex), every package with an
   exact version, `pins_of_record`, `offline_tests` with each failure listed and classified, and `lock_sha256`
   computed by `scripts/petri_audit/envlock.py`. Record the fork's own suite (`uv run pytest`) at the candidate
   commit in `offline_tests`, as the current lock does for the pin.
3. **Transcript adaptation.** Adapt the same raw `.eval` in the locked and the candidate environment, with output
   outside `data/petri/runs/`, and compare `transcripts.jsonl`, `rule_outcomes.jsonl`, and the manifest's `trees`,
   target stop reasons and contract checks. `sanitised_log.json` and the `harness` block are expected to differ.
   Answer separately whether the candidate Inspect reads a log written by 0.3.237 at all.
4. **Run `verify-lock` before `adapt`.** `cli adapt` writes the lock digest into the manifest without comparing
   the environment with the lock. In CI the `verify-lock` step precedes it; outside CI nothing does.
5. **Engine code that cites 0.3.237 behaviour.** Re-verify each under the candidate: the private import
   `inspect_ai.log._resolve.rebind_sample_timelines` (`scripts/petri_audit/adapter.py:33`); the per-provider
   seed-forwarding table; the stop-reason sets and the sample-limit refusal in `scripts/petri_audit/checks.py`;
   usage and cache accounting in `spend.py`; the sanitiser allowlist `data/petri/sanitizer_allowlist.json`, which
   drops any event type or key a newer Inspect adds.
6. **Branch naming.** The adapter reads creation order from span names matching `^branch (\d+)$`
   (`scripts/petri_audit/adapter.py:101`) and treats the largest index as the survivor. The head can name a span
   `branch (incomplete)`. Confirm such a span is not exported as the surviving trajectory.
7. **Historical rejudge rehearsal.** Run
   `python -m scripts.petri_audit.cli rejudge-rehearse --source-run <stem> --out-root <directory outside the repository>`
   for every landed run, adding `--instrument historical` for the runs whose prompt files have changed since. It
   costs nothing and uses a mock judge. A rehearsal that passed under the lock must pass under the candidate.
8. **Realism role.** At the head the `realism` model role is required only when the realism filter is on, and
   the filter is off by default. The engine passes its own agent, so no approver runs and no landed run has an
   auditor model. Confirm that a scripted candidate run still starts without a `realism` role, and that nothing
   in the candidate turns the filter on by default.
9. **Judge isolation.** The judge of record and the second judge run in the same job and environment as the
   harness. A candidate lock that raises the `anthropic` SDK changes the judge's SDK too, and judgment rows
   record no SDK version. Either keep the judge step in the locked environment, or judge one fixed plan under
   both and compare rows.
10. **Preserve the original instrument in landed records.** Never re-adapt or re-judge a landed run in place.
    Landed manifests keep `harness.commit` and `harness.environment_lock_sha256` of the run; a re-grade goes to
    `data/petri/rejudge/<judge>/<run>/` and never into `data/petri/runs/`. `python -m scripts.petri_audit.cli verify-chain --data-dir data/petri/runs`
    must print the same chain head before and after the evaluation.
11. **Harness tests.** `tests/petri/` needs the harness and skips in the ordinary environment; no CI job runs it.
    Run it in the candidate environment. Several of its tests pass the old harness commit as a literal, so read
    their labels before trusting a pass.
12. **Read first.** [decisions_20261014_owner.md](decisions_20261014_owner.md) for the separate judges and the
    historical-instrument safeguards; [petri_integration_design.md](petri_integration_design.md) section 11 for
    the lock rule ("Moving any pin is a new lock, a new digest and a pull request").

## 6. Record parity, then change one pin

1. Write the parity result before the pin changes: the two environments (versions, hashes or commits), the
   prompts or log compared (by batch stem and index, never by text), dtype, the tolerance, the counts that
   agreed and disagreed, and what was not compared. A zero difference and a non-zero difference are both
   results; record either.
2. If parity fails, the pin does not move. Record the failure and stop.
3. One pin change per commit, with a note in the ledger. That is the policy written in `constraints.txt`. A lock
   change is a new lock file, a new digest and a pull request.
4. In that same change, update the manifest: the pin value under `consumed_by_engine`, `head_vs_pin`, and
   `as_of`. `tests/test_ecosystem_manifest.py` fails while the manifest and the pointer file disagree.
5. Update the documents that describe the old pin: [interp_engine_assessment.md](interp_engine_assessment.md)
   for interp-engine, the lock's own note and [petri_integration_design.md](petri_integration_design.md) for
   Petri, and the capability matrix `data/experiments/capability_matrix.v1.json` where a row cites the version.
6. Measurements made after the change are a new instrument state. Do not pool them with earlier ones without a
   label, and do not re-measure or republish historical values; that is the owner's decision
   ([agent_reference.md](agent_reference.md), research limitations).

## 7. The other forks

- **ICA Lens.** Nothing is pinned today. Before any run that imports `icalens`, pin its version and record it in
  the manifest. Always pass the preprocessing mode explicitly: the Python constructor and the fit CLI have
  different defaults. Its exact `transformers==5.14.1` pin equals the engine's; a transformers bump on either
  side breaks that.
- **J++ Lens.** The released Qwen3-4B artifact has an unknown fit identity and `lens_interop` refuses to load it
  for transport. An upgrade does not change that; the publisher's answer does.
- **J-Lens reference.** Frozen upstream and not executed. Nothing to upgrade.
- **Causalab.** Not pinned and never run. Resolve the Python licence and set one execution commit before the
  first authorized run.
