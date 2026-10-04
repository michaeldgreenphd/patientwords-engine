# Handoff: pilot run 3 (version-3 prompts, harness version 2), 2026-10-04

This file describes the run in this directory as it proceeds. The protocol (`PROTOCOL.md`) was written and frozen before any generation call; deviations from it are recorded here.

## Execution path

Claude Code in VS Code on the owner's laptop, in the owner's interactive session, in which the owner asked on 2026-10-04 to generate run 3 now with the version-3 kit (`pilot/prompts_v3/`, merged in pull request #80, with the provisional brand cap of one concept per call, which the owner accepted by merging), as Workflow tool subagents, exactly as run 2 was executed. A subagent of that session created this run directory and ran the planning steps; the session itself launches the generation and checker workflows. The scripts are the pilot harness at version 2 as on engine main 0404b10c, the same `pilot/scripts/*.py` whose hashes run 2's manifest records, run from branch claude/pilot-run3 in a worktree in the session's scratchpad. No repository script calls a paid provider API for this run: subscription usage in the owner's session is not provider spend.

## Assumptions and notes, in order

1. Seeds: the 26 cases of runs 1 and 2, copied from run 2's `seeds.json`, byte-identical (sha256 095820fe...).
2. The run kit was copied from `pilot/prompts_v3/` unchanged, at engine main 0404b10c: `design.json` (harness_version 2, sha256 0c01bea7...), `prompts/generation_prompt.txt` (da04f920...) and `prompts/checker_prompt.txt` (ceb18c4b..., byte-identical to version 2's and to run 2's copy). The brand cap is the kit's one concept per call.
3. Model facts are in `manifest_model.json`, read at 2026-10-04T17:01Z. The model id (claude-opus-5-5[1m]) comes from the planning subagent's system prompt and the session's statement that it runs claude-opus-5-5. The Claude Code version, 2.1.287, is the binary of the process running this session (the VS Code extension's native binary, started 2026-10-02 with `--resume` of this session's id), found by walking the planning subagent's shell up to its parent; run 2's file could only give its version as most likely. If the session restarts under another version before generation, the next note records it. The effort level, the model at session creation and any model switch could not be verified (see the file's source field).
4. Planning: `plan_calls.py` and the plan-time `write_manifest.py` ran at 2026-10-04T17:04Z under Python 3.12.14 (the engine checkout's virtual environment): 18 calls, K = 8, harness_version 2, protocol sha256 6e27b80f... recorded as `protocol_sha256_at_write` (manifest created 2026-10-04T17:04:44Z, protocol unchanged). The seeds and the master seed are runs 1 and 2's, so every call drew exactly run 2's exemplar ids (compared call by call with run 2's `calls.json`); all 18 rendered prompts differ from run 2's because the rule text changed, and none carries an unrendered marker.
5. `make_workflow_scripts.py generation` wrote `workflows/generation.workflow.js` (18 items, 151,927 bytes, sha256 f391c1c7...). Outside its `PROTOCOL` and `CALLS` constants the script is byte-identical to run 2's generation script, which the Workflow tool ran; every entry of `CALLS` is the planned prompt with its hash, and the agent labels carry the frozen protocol's hash. It passed a JavaScript syntax check wrapped in an async function. As in run 2, the plan-time manifest was written before the script was rendered, so the manifest's `workflow_script_hashes` stays empty until the next `write_manifest.py`. The planning subagent did not launch it.
6. Checks before generation, on branch claude/pilot-run3: `pilot/scripts/selftest.py` passed; `tests/test_pilot_*.py` gave 68 passed and 1 failed, the failure being `tests/test_pilot_recorded_runs.py` on this directory, which requires every run directory with a `manifest.json` to be finalized and so fails until this run is finalized (runs 1 and 2 re-finalized there in temporary copies and passed); the holdout seal check over this directory and the site was CLEAN (exit 0).

## Results

<!-- results:begin -->
(written by `scripts/compute_summary.py` from `summary.json` after the run; empty until then)
<!-- results:end -->

## Deviations

None so far.
