# Pilot runs: how the pilot scripts select, guard and re-seal a run directory

The rules are in `AGENTS.md`: the pilot exception and its four conditions under
*Execution model*, and the reviewer's reading of files under `pilot/` under *Code
Review Rules* (*What those rules mean in this repository*). This page holds the
mechanics those rules rely on. It was moved out of `AGENTS.md` on 2026-10-02 to
keep that file under its byte budget (`tests/test_agents_md_budget.py`); nothing
here changes a rule. The step-by-step procedure for a run is in the first run's
`pilot/HANDOFF.md` (*First three things to do on your laptop*) and, for the
version-2 kit, `pilot/prompts_v2/README.md` (*How a run uses it*). The version-3
kit, `pilot/prompts_v3/`, runs on the same harness version and follows the same
procedure; its README lists what it changes.

## Why the exception exists

The owner granted it on 2026-09-30 on PR #52, after Codex read the execution-model
rule (nothing paid or networked runs locally) as excluding a pilot run as Claude
Code subagents in the owner's own session. The pilot had been executed that way,
through the Workflow tool, and `pilot/HANDOFF.md` (*Owner decision on the
recorded run (2026-09-30)*) records the decision.

## Run directories

- `pilot/` is the first recorded run; each later run is committed as
  `pilot/runs/<run_id>/`. Each run directory holds its own protocol, handoff and
  manifest (`pilot/PROTOCOL.md`, `pilot/HANDOFF.md` and `pilot/manifest.json`; the
  same three in `pilot/runs/<run_id>/`), which state the execution path
  (condition 1).
- The pilot scripts work on one run directory at a time: the one the `PILOT_DIR`
  environment variable names, or `pilot/` when it is unset
  (`pilot/scripts/common.py`, `PILOT`). Set `PILOT_DIR` for every call of a new
  run.
- A run's blind review is recorded outside its sealed directory, in
  `pilot/codebook/`: the review export and, for a version-2 run, the owner's
  answers compared with the checker's (`pilot/analysis/review_agreement.py`).
  `pilot/codebook/README.md` lists those files and keeps a dated entry per
  review.
- Pilot traces are a separate tree: a circuit-trace fire with
  `output_root: pilot/traces` writes `pilot/traces/<pairs-stem>[__<model>]/`,
  which no collector reads. `docs/triggers.md` (the `circuit-trace` row) has every
  rule that lane applies to a pilot fire.

## A finalized run is not written into without `--replace`

- The planning, batching, rendering, review-draw and request-body scripts
  (`plan_calls.py`, `build_checker_set.py`, `make_workflow_scripts.py`,
  `make_review_sheet.py`, `build_api_requests.py`) refuse to write into a run
  directory whose `manifest.json` is finalized (`finalized_utc` set) unless
  `--replace` is passed (`common.finalized_run_guard`). A manifest that is not
  JSON is refused too, never read as unfinalized. With `--replace` the write goes
  ahead, and the next `write_manifest.py` clears the finalization if any hashed
  output changed.
- `compute_summary.py` and `write_manifest.py` have no such guard: run with
  `PILOT_DIR` unset, they rewrite the recorded run's summary, results block and
  manifest in `pilot/`. If that happens, restore those files from git
  (`pilot/prompts_v2/README.md`, *How a run uses it*, has the command).
- The parsers, the journal extractor and the run recorder (`parse_generation.py`,
  `parse_checker.py`, `extract_workflow_journal.py`, `record_run.py`) refuse to
  write over an earlier output of their own unless `--replace` is passed.

## Script hashes: why a script change re-seals every recorded run

- `compute_summary.py` records the SHA-256 of every `pilot/scripts/*.py`, by file
  name (`common.script_hashes`), in `summary.json`, and `write_manifest.py`
  records them in `manifest.json`. `write_manifest.py finalize` refuses a summary
  computed under other scripts, and refuses a bundle whose files do not agree
  with each other: it recomputes the summary, re-derives the plans, re-renders
  the workflow scripts and compares them with the files on disk.
- So a pull request that changes any pilot script must recompute and re-finalize
  every recorded run (`AGENTS.md`, *Code Review Rules*).
  `tests/test_pilot_recorded_runs.py` fails when it did not: it compares every
  hash a run records with the file it names, then runs finalize on a copy of the
  run in a temporary directory.

## The Python 3.12 line

- Python 3.12 made `sum()` over floats compensated (Neumaier summation), so the
  summary's float sums (estimands 3 and 5) can differ in the last bit between an
  interpreter before 3.12 and one from 3.12 on. Within either side the values
  agree.
- So a recorded run is re-finalized under an interpreter on the same side of 3.12
  as the one its manifest's `python` field records. `compute_summary.py` and
  `write_manifest.py` (except with `--reset`) refuse a finalized run sealed on the
  other side (`common.sealed_interpreter_guard`); a finalized manifest that
  records no readable interpreter version is refused too. Without the refusal,
  re-sealing under alternating interpreters would flip the recorded float sums on
  every pull request that touches a pilot script.
- Both recorded runs, `pilot/` and `pilot/runs/pilot_v2_20261002/`, are sealed
  under Python 3.13.4, so re-finalizing them needs 3.12 or later.
  `tests/test_pilot_recorded_runs.py` skips only its finalize step, with the
  reason, on the other side of the line; its hash step runs on every
  interpreter.

## No script sends a request

`pilot/scripts/build_api_requests.py` writes the exact Messages API request
bodies for the planned generation calls or checker batches
(`api_requests_generation.json`, `api_requests_checker.json`), with the retry
rule and the result-file shape the parsers consume, and sends nothing. It exists
for a pilot push-to-run lane, which does not exist yet; until one does, the
Claude Code Workflow tool (`workflows/*.workflow.js` in each run directory) is
the only way the pilot has been executed. No script in this repository calls a
paid provider API for a pilot (condition 3).
