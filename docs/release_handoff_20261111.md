# Release handoff, 2026-11-11

This is the one handoff record for the release candidate of 2026-11-10 and 2026-11-11. It says what is
in the two pull requests, in which order they are merged, what was checked, and what is left to the
owner. It is a record of its date. Later commits to either branch are in the pull request descriptions.

Answer first: both pull requests are release candidates and nothing in them is merged, published or
run on a model. The owner merges. Two decisions block further steps, and they are listed last.

## The two pull requests

| Repository | Pull request | Head when this was written | Base |
|---|---|---|---|
| `patientwords-engine` | 171 | `bf26567d` (this file is the next commit) | `main` at `b6af0e5c` |
| `patientwords` | 29 | `6c5ef90a` | `main` at `f1504ce` |

Engine pull request 167 is merged. Pull request 169 is redundant (its fix reached `main` through 167)
and pull request 170's two commits are in 171. Neither is merged on its own; both are closed after 171.

## Release order

1. Merge engine 171 **with a merge commit**. The snapshot `study-interim-20261110-r2` records engine
   commit `a40520d1`, which must stay an ancestor of `main`; a squash or rebase merge removes it and
   the published-release check then refuses. If such a merge happens, a replacement snapshot is
   created and checked before anything else (`.claude/skills/publish-site-data/SKILL.md`, *Recovery*).
2. Merge site 29. This publishes the corrected payload summary and the revised pages. The published
   check compares bytes, so any merge method works for the site.
3. Record the publication and commit the one-file index change:
   `python scripts/results_snapshot.py check-release --id study-interim-20261110-r2 --site ../patientwords --published --record`
4. Close 169 and 170.

Immediately before step 1, confirm the two heads in the pull requests and that
`python scripts/results_snapshot.py check-release --site ../patientwords` exits 0.

## What the candidate contains

Three kinds of thing, kept apart.

**Completed implementation (software and text; nothing measured).**

- The payload summary correction, published alone: four JSON values of `summary.penalty` change
  (1,163 to 1,124 distinct scored phrases; mean -0.0387 to -0.0367; interval [-0.0477, -0.0291] to
  [-0.0460, -0.0267]) and no scenario record changes.
- A check that refuses an export or a release that changes or removes a published measurement, or
  changes a capability label, without the owner's recorded disposition
  (`scripts/payload_dispositions.py`). It runs in the exporter before its first write, in
  `results_snapshot.py create` and in `check-release`. Catalogue-only publishes and new results are
  not held. The 13 undecided `qwen3-4b` row differences are recorded as `pending`.
- A capability-label rule for a model with rows from two backends (decision D3, prepared): the label
  follows the exported rows, so `qwen3-4b` stays "next-token only" as published.
- Revised public pages (homepage, Start here, Results, Compare methods) and a small primary
  navigation on every page, with two page checks that test reading order, labels, sign and states.
- The experiment bundle can export target text under a second marker and the existing seal checks.
- The instrument-validity scorer has the input-only and control-artifact arms, a calibration record
  that refuses held-out families, and a refusal of one phrase in two families.
- The stage A parity verdict is computed by code, and the verify path records load and measurement
  seconds.

**Observed model evidence.** None is new. No model was loaded and no lane was fired. The only changed
published numbers are the four summary values above, recomputed from rows that were already public.

**Proposed research.** `docs/protocols/instrument_register_experiment_20261111.md` is an unsigned
draft. It holds no margin, no threshold and no result. The comparison pages show a synthetic fixture
in development only; the public comparison index is empty.

## What was checked, and on what

Engine `bf26567d`, site `6c5ef90a`, Python 3.12.3 unless stated. Commands are in `verify.md`.

| Check | Result |
|---|---|
| Full engine suite, at `1ec0e05e` with the page-check edits that became `4884836a` on disk | 7,709 passed, 33 skipped, 0 failed; the two page-check test files were run separately: 81 passed |
| After the last two engine commits: the boundary, doc-path and claim tests | 77 passed |
| `ruff check .`, `git diff --check` in both repositories | clean |
| Boundary check, Python 3.13.18, Chromium 153 | exit 0, 21 checks. Its first run against the new homepage failed and found a page defect, fixed in site `6c5ef90a` |
| Results page check / comparison preview check | 69 of 69 / 56 of 56 (synthetic fixture) |
| Page load check | 23 pages, 0 failing |
| Contract gate `--strict`, claim check, seal check | 0 errors and 0 warnings; all claims verified; clean (183 sealed phrases, 1,414 files) |
| `check-release` | exit 0: one statistics file changes, the snapshot covers it, and 0 published measurements change |
| Real exporter, dry run, all published stamps | exit 1 as intended: the 13 `qwen3-4b` rows refused, no label difference, the site unchanged |

Skipped, with the reason each test gives: the ICA reference tests (no `icalens` or `torch` in this
environment; 14), the Petri tests that need `inspect_petri` or `inspect_ai` (4), tests that need
history a shallow clone lacks (4), two legacy-summary tests and one bundle test that no longer apply
to the corrected payload (3), three `barrier_help` tests the study does not judge, two permission
tests that cannot run as root, two workflow tests with no push trigger, one workflow not landed.
Not run in this pass: the ICA reference tests in their own environment (it was lost in a container
restart; no ICA code changed), and the temporary-regeneration block of `verify.md` (it needs a full
site copy).

Not checked by any automated job: the engine has no workflow on pull requests, and neither page check
runs in site CI.

## Decisions that block a next step

1. **The 13 `qwen3-4b` rows (D1, D2, D4).** Until they are decided, a full export is refused and the
   site keeps the published values. The decision record with numbers is
   `docs/corrections/payload_summary_dedupe_20261110.md`, section 8. Proposed: drop the 11 legacy rows
   (D1), regenerate `model_stats.json` in the same release (D2), show row 1 as not measured and
   accept row 2's hosted value (D4). A known misread is not proposed for publication. A re-trace of
   row 1 is a new measurement with its own approval, and today it would overwrite a landed part
   unless the part naming is changed first.
2. **The stage A operation check.** One `logits-eval` job, 10 public rows, `gemma-2-2b` at the pinned
   revision, $0 provider spend, at most 240 runner minutes, acceptance by
   `scripts/backend_agreement.py --criteria`. The request with its table is in
   `docs/exploratory/first_model_run_packet_20261110.md`, section 14. It answers none of the research
   questions and it is the only step that can run on a real model today.

## Found and not changed

- `scripts/audit_target_reads.py` refuses on today's tree: ten `agscen_` parts carry a `target_read`
  block with no record for the patient side.
- A hand `logits-eval` fire can overwrite a part of another backend at the same name.
- `README.md` in `.github/trigger/` still gives a hand export recipe. The exporter now refuses it. The
  file is under the trigger directory and was left alone.
- The reader label for the bundle variant `normalized` is "Rewritten wording"; no engine document
  defines the transformation.
- The homepage's share image and its alternative text carry the earlier headline.
- The twelve pages outside this pass keep their earlier type sizes and palette. Start here and Results
  are longer than before because their text is larger.
- The site's `docs/agent_reference.md` says 16 canonical tags; 18 authored pages carry one.
- The message of engine commit `bf26567d` misstates how far the site fix is from the snapshot's site
  commit. The fix is site commit `6c5ef90a`, three commits after `2bf3c1e`.

## Addendum, later on 2026-11-11: the restoration pass

The owner merged engine 171 at 03:10 UTC with a merge commit (`21ad6657`), so `a40520d1` is an
ancestor of `main`. 169 and 170 are closed as superseded. Steps 1 and 4 of *Release order* are done.

Two statements above are superseded.

- **Start here.** The owner rejected the redesign of that page listed under *Completed implementation*.
  Site 29 now restores the page from its design of 2026-10-27 (site `ac82473`), corrects specific claims
  in place, and adds a second drawing of each wide diagram for narrow screens. The standing preference
  (preserve the diagram-led narrative and its interactions; make small, justified edits) is recorded in
  the site's `docs/agent_reference.md`. The homepage, Results and Compare methods were shortened; no data
  file changed.
- **The instrument-validity scorer's state names.** `system_does_not_read_artifact` and
  `recoverable_from_wording_alone` named a cause the comparison cannot show. Engine 172 renames them
  (`no_advantage_over_control_artifact`, `no_advantage_over_wording_alone`) and corrects the rule. It
  makes the same correction to `scorer_does_not_read_description`, in a separate commit.

Remaining order:

1. Merge site 29. Any merge method works for the site.
2. Merge engine 172. It holds the claim entries and the browser test for the restored page, so between
   the two merges `tests/test_claim_check.py::test_live_manifest_verifies_against_live_site` reports
   warnings when engine `main` is paired with site `main`.
3. Record the publication with the command in step 3 of *Release order* and commit the one-file index
   change.

Checked at engine `b2c1951a` and site `60c2d8e`, Python 3.12.3 unless stated:

| Check | Result |
|---|---|
| Full engine suite | 7,799 passed, 33 skipped, 0 failed (the skips are the ones listed above) |
| Boundary check, Python 3.13.18, with `--browser` set to the installed Chromium | exit 0, 21 checks. Without `--browser` it stopped before any check: that environment's Playwright expects a browser build that is not installed |
| Results page check / comparison preview check | 69 of 69 / 56 of 56 (synthetic fixture) |
| Page load check, contract gate `--strict`, claim check, seal check | 23 pages, 0 failing; 0 errors and 0 warnings; all claims verified; clean (183 sealed phrases) |
| `check-release` | exit 0: one statistics file changes, the snapshot covers it, 0 published measurements change. No file under the site's `data/` or `modes/` changed after the snapshot's site commit `2bf3c1e` |
| Site CI at `60c2d8e` | both `checks` runs succeeded |

Found in this pass and not changed: the site's `data/provenance.json` gives the translation outcome
twice and the two do not agree. `translation_cases.summary` says 8 recovered of 20 downgrades (7
unrecovered, 5 unclassifiable). `translation_cases.all.cases` lists 18 cases: 8 recovered, 4 already
correct, 3 unrecovered, 3 worsened. The Translation page prints the first. The restored Start here page
prints neither count. An earlier review recorded the same disagreement (`docs/referee_panel_20260714.md`).
