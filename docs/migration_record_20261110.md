# Migration record, 2026-11-10: paths and interfaces of the change set

Written 2026-11-10. This records which paths and interfaces the 2026-11-10 change set adds,
who consumes them, how to roll each back, and what was run to check that existing commands
and URLs still work. Paths are relative to the engine root unless they begin
`../patientwords/` (the site checkout).

Answer first: **no file was moved or renamed, and no dataset or summary was moved.** Every
change is an addition or an in-place edit. One defect was found while this record was
written (the contract check failed on the new results catalogue) and was fixed before the
change set was pushed; see [Found and closed](#found-and-closed).

The policy change itself, with its counts and the byte-identity check of the collector, is
in [open_results_migration_20261110.md](open_results_migration_20261110.md). This record
covers paths and interfaces only and repeats none of those numbers.

Base commit of the change set: `d8d0855d`. The policy commits are `9b338b01` and `7ad978bf`.
Two more commits landed while this record was written: `9ff59a6f` (catalogue) and `8f3319fe`
(protocol template and instrument-validity benchmark).
The working tree was still changing while the checks below ran, so each result carries its
time (UTC, 2026-11-10).

## Path and interface changes

The State column was written at 13:58 UTC, while other parts of the change set were still
being built. Every row marked "proposed" below was present, tested and committed by the end
of the day: `scripts/experiments/`, `data/experiments/`, `data/ecosystem/` and
`schemas/experiments/`.

| Change | Kind | State | Consumers | Rollback |
|---|---|---|---|---|
| `scripts/results_policy.py` | new module; holds the rule | present | every collector that pooled `trace_out/` through the hold (listed in the policy migration record, section 6); `tests/test_results_policy.py` | revert the commit. The default membership reproduces the previous rule, so reverting changes no published statistic |
| `scripts/publication_hold.py` | kept as the import path older callers use; holds no rule | present, edited in place | callers that import `Gate` and the names below; `tests/test_publication_hold.py` | revert the commit |
| `scripts/export_results_catalogue.py` | new script | present | publish chain step 6b (`.claude/skills/publish-site-data/SKILL.md`); the Routine through that skill; `tests/test_results_catalogue.py` | revert the commit and drop step 6b; delete the site's catalogue directory and page in the paired site change |
| `scripts/results_snapshot.py` | new script | present | the owner, when a statistic's inputs change | revert the commit; snapshots already written are records and stay |
| `scripts/open_results_migration.py` | new script | present | one-off comparison; reads through `PW_RESULTS_POLICY` | revert the commit |
| `scripts/experiments/` | new package, run as `python -m scripts.experiments.cli` | proposed | its own tests `tests/test_experiments_*.py`; nothing published | delete the package; nothing else imports it |
| `data/results_policy/` | new data directory (policy file; the part ledger is appended by step 6b) | present | `scripts/results_policy.py` | revert the commit |
| `data/analysis_snapshots/` | new data directory | present | `scripts/results_snapshot.py` | revert the commit that added the snapshot |
| `data/protocols/` | new data directory (annotation rubric) | present | annotators of the instrument-validity benchmark (`docs/protocols/`); `tests/test_instrument_validity.py`; `scripts/instrument_validity.py` reads the rubric's description-control definitions (added later the same day; before that no script read the directory) | delete; nothing published reads it |
| `data/experiments/`, `data/ecosystem/` | new data directories | proposed | the experiment package; documentation | delete; nothing published reads them |
| `schemas/protocols/` | new schema directory | present | `scripts/instrument_validity.py` | delete with that script |
| `schemas/experiments/` | new schema directory | proposed | the experiment package | delete with the package |
| `scripts/contracts/results_catalogue.v1.schema.json` | new schema, placed under `scripts/` | present | `scripts/validate_frontend_contract.py`, which site CI runs. Site CI checks out `scripts`, `data`, `ops` and `docs` of the engine and not `schemas`, so a schema that checker reads cannot live under `schemas/` | revert together with the checker's catalogue check |
| `scripts/validate_frontend_contract.py`, `scripts/check_pages.py` | edited in place (catalogue check; one more table id) | present | site CI; the paired gates in `verify.md` | revert the commit |
| `../patientwords/results/index.html` | new site page | present, untracked | readers; `scripts/check_pages.py` | delete the page in the site repository |
| `../patientwords/data/results_catalogue/` | new site data directory | present, untracked | the new page; the contract check | delete the directory in the site repository |
| `docs/protocols/`, `docs/start_here.md`, `docs/contributing_a_method.md`, `docs/architecture_decision_20261110.md`, this file | new documents | present | readers | delete |

Not changed: `trace_out/`, `render_archives/`, `pilot/`, `.github/`, `.githooks/`,
`.claude/hooks/`, `constraints.txt`, `pyproject.toml`, and every file under `data/simulated/`
except its `README.md` (text only).

## Checks that nothing moved

Run at 13:58 from the engine root.

- `git diff --name-status -M d8d0855d | grep -E '^(R|D)'`: 0 lines. No rename and no deletion
  between the base commit and the working tree.
- `git status --short` in both checkouts: 0 entries with status `D` or `R`. The site shows
  five edited documents and the two untracked additions named above; no existing page and
  no existing payload is modified.
- `git diff --stat d8d0855d -- trace_out data/simulated pilot render_archives .github .claude/hooks .githooks constraints.txt pyproject.toml`:
  one file, `data/simulated/README.md`.

## Affected consumers

**Site CI.** It runs the two checkers from a sparse engine checkout. Both gained code in this
change set. Simulated at 13:59: a directory holding only `scripts`, `data`, `ops` and `docs`
copied from the working tree, the site as its sibling, and
`python3.11 -S scripts/validate_frontend_contract.py --site ../patientwords --engine .`
(Python 3.11.18, site-packages disabled, so standard library only). The checker ran to its
summary line with no import error, so everything it imports and reads is inside the four
directories. It exited 1 at that time; see [Found and closed](#found-and-closed).
`python3.11 -S scripts/check_pages.py --help` exited 0 in the same layout.

**The Routine's publish chain.** One step was added (6b, the catalogue export) and a
catalogue-only route. No existing step was removed or reordered. Not executed here: the
chain writes site data and is run by the Routine or the owner.

**Tests.** `tests/test_publication_hold.py` and `tests/test_study_timeline.py` were edited;
`tests/test_results_policy.py` and `tests/test_results_catalogue.py` are new. This task ran
the quick-path files only (below). It did not run the full suite.

**patientwords-traces.** None of its paths changed. What was checked, at 13:57:

- `scripts/export_traces_site.py` is identical to the base commit (absent from
  `git diff --stat d8d0855d`). It still builds `<base-url>/t/<batch>/index_NN.html`
  (lines 57 and 69) with the default base URL at line 79.
- `grep -rn "patientwords-traces" scripts .github medlang_circuits ops` over `.py`, `.yml` and
  `.json` files: 5 hits, all in that one script.
- No entry under `trace_out/` or `render_archives/` in `git status`, so no render the nightly
  mirror copies was moved or pruned by this change set.
- `../patientwords/data/simulated_scenarios.json` is unmodified, and all 1,509 `trace_url`
  values in it match the scheme above.

Not checked: the traces repository itself is not checked out here, and its build workflow
was not read.

## Evidence that legacy commands and URLs still work

### Clean-copy run

The working tree was copied at 13:52:47 to a temporary directory outside any Git checkout,
excluding `.git`, `trace_out`, `render_archives`, `.venv`, `__pycache__`, `.pytest_cache`
and `.ruff_cache`. `rsync` is not installed in this container, so the copy was
`tar -cf - --exclude=... . | tar -xf -` with the same exclusions; 232 MB. The copy is a
snapshot of the change set in progress: it predates the two policy commits by under a
minute and does not contain `data/analysis_snapshots/`, the two files under
`docs/protocols/` or `tests/test_instrument_validity.py`.

| Step | Command | Outcome |
|---|---|---|
| Environment | `python3.12 -m venv .venv` | Python 3.12.3 |
| Install | the install line of `verify.md` (*Setup and sources of truth*) | exit 0. `medlang-circuits` 0.1.0 (editable), pytest 9.1.1, ruff 0.16.10, PyYAML 6.0.3, requests 2.34.2, matplotlib 3.11.2, networkx 3.7, anthropic 2.7.0 |
| Import | `python -c "import medlang_circuits; print(medlang_circuits.__file__)"` | exit 0; the path is inside the temporary copy |
| Console command | `medlang-compare --help` | exit 0 |
| Console command | `medlang-batch-eval --help` | exit 0 |
| Quick-path tests | `python -m pytest -q -ra` on the seven files of `verify.md` (*Quick path*), `PW_SITE_ROOT` unset | **1 failed, 59 passed, 26 skipped** in 12.2 s |
| Lint | `python -m ruff check .` | exit 0, "All checks passed!" |
| Legacy script | `python scripts/exploratory_methods.py --spec tests/fixtures/exploratory/synthetic_spec.json --packet tests/fixtures/exploratory/synthetic_packet.json` | exit 0; a 72,414-byte JSON report on stdout, `schema_version` `patientwords.exploratory/1`, `execution_status` `synthetic`; stderr empty |
| Legacy script | `python scripts/validate_frontend_contract.py --help` | exit 0 |
| Legacy script | `python scripts/check_pages.py --help` | exit 0 |
| Legacy script | `python scripts/publication_release.py --help` | exit 0 |
| Legacy script | `python scripts/urgency_shift.py --help` | exit 0 |
| Legacy import path | `from scripts.publication_hold import Gate, ReleaseError, HELD_MODELS, is_held, is_held_run_dir, is_exploratory_run_dir, EXPLORATORY_STEM_PREFIXES, load_manifest, sha256_file, RELEASE_MANIFEST, MANIFEST_SCHEMA` | exit 0; `MANIFEST_SCHEMA` is `logits_release/1` |

The quick-path result in detail:

- The one failure is `tests/test_scripts_readme.py::test_every_top_level_script_has_exactly_one_valid_row`:
  "no row for scripts/instrument_validity.py". Cause: a new script from another task of the
  change set had no row in `scripts/README.md` yet. It is not caused by the missing
  `trace_out/`. The row was added afterwards; see the live-tree run below.
- 24 skips are `tests/test_doc_paths.py`: "git ls-files unavailable". The copy has no `.git`,
  and that test resolves paths through Git. In a clone these tests run.
- 2 skips are `tests/test_shared_conventions.py`: no site checkout beside the temporary copy.
- No quick-path test failed or skipped because `trace_out/` was absent.
  `tests/test_target_reads_evidence.py` and `tests/test_trigger_docs.py` passed without it.

The `git diff --check` lines of the quick path were not run in the copy; it has no Git
metadata. The temporary directory was deleted after the run.

### Live working tree, after the clean-copy run

Run at 14:06 from the engine root with the developer environment (Python 3.12.3), the site
checkout present as the sibling:

- the same seven quick-path files: **86 passed**, 0 failed, 0 skipped in 9.6 s. The Git-based
  and cross-repository tests that skipped in the copy ran here.
- `python -m ruff check .`: "All checks passed!"
- `git diff --check`: exit 0.
- `python scripts/seal_check.py --site ../patientwords` (14:02): exit 0. Its sweep includes
  `docs/`, so it read the four documents added with this record.

### Script paths named by automation

A script checked that every script path named in the automation still exists in the working
tree (13:54). Files scanned: the 13 files of `.github/workflows/`, the 6 `SKILL.md` files
under `.claude/skills/`, `docs/routine_standing_prompt.md` and the site's
`../patientwords/.github/workflows/site_checks.yml`; 21 files. A path is any token that
starts with `scripts/`, `pilot/scripts/`, `ops/`, `.claude/hooks/` or `.githooks/` and ends
in `.py` or `.sh`, plus the two checker names in the site workflow's loop.

| Source | Distinct script paths |
|---|---|
| Engine workflows | 25 |
| Skills | 22 |
| Routine prompt | 13 |
| Site CI | 2 |
| All sources, distinct | 49 |
| Missing | **0** |

Limits of this check: it tests existence, not behaviour. It does not see a script named only
by a shell variable, and none of the scanned files invokes a script as `python -m scripts.<name>`.

### Pages

`python scripts/check_pages.py --site ../patientwords --port 8947 --browser <chromium>` at 13:54,
run from the working tree with Playwright 1.65.0 and a local Chromium: exit 0,
**22 pages checked, 0 failing**. The 21 existing pages load as before; the new
`results/index.html` loads with a non-empty table. This is a load check of local files over
loopback HTTP. It is not the deployed site.

Existing public URLs: no existing page file and no existing payload is modified in the site
working tree, and `../patientwords/data/simulated_scenarios.json`, which fixes the
`scenario.html?sim=N` order, is unmodified.

## Found and closed

Both items were open when this record was first written and were closed the same day.

1. Closed at 14:06: the quick-path failure on the missing `scripts/README.md` row.
2. Closed in commit `6d699d0f`: **the contract check exited 1**, in the working tree and in
   the simulated site-CI layout:
   "contract check: 2356 error(s), 0 warning(s)" at 13:59 and again at 14:06. Every error is
   in the new catalogue; none is in a payload that existed before.
   - 2,352 errors, in 42 files under `../patientwords/data/results_catalogue/rows/`:
     a row's `clinical_mass` is an object with keys `clinical` and `patient`, and
     `scripts/contracts/results_catalogue.v1.schema.json` declares it number or null.
     `scripts/export_results_catalogue.py:161` copies the summary's value unchanged. The
     schema and the exporter disagree. `tests/test_results_catalogue.py:56` builds its
     fixture row with a number, so the tests pass while landed summaries, which hold the
     object, fail.
   - 4 errors: `count_unit` is a required key missing from each entry of `restrictions` in
     the catalogue index. The exporter writes that key since its 13:56 edit, and the site's
     catalogue files date from 13:39. Inferred, not run: regenerating the catalogue removes
     these four.

   Failure path had it been merged: site CI's contract step would fail on every site push,
   because `check_results_catalogue` validates every catalogue file whenever the directory
   exists. Fix: the schema now declares the landed shape (an object per phrasing), the test
   fixture uses that shape, a regression test runs the gate over a calibrated part, and the
   catalogue was regenerated. Re-run after the fix:
   `python scripts/validate_frontend_contract.py --site ../patientwords --engine .` printed
   "contract check: 0 error(s), 0 warning(s)".

## Not checked

- Hosted CI was not run. No workflow was dispatched and no trigger was fired.
- The synthetic boundary procedure of `verify.md` was not run: it needs its own locked
  Python 3.13 environment with `jsonschema`, which was not installed here.
- The publish chain was not executed against the real site. Its steps, including the new
  step 6b, were run on a disposable copy of the site; the results are in
  [open_results_migration_20261110.md](open_results_migration_20261110.md), section 1.
- The full test suite and the offline experiment slice were run later the same day, outside
  this record's clean-copy pass; the change set's completion report has the counts.
- The deployed site and the traces site were not fetched.
- Site CI's own runner was not reproduced beyond the Python version and the four directories:
  its checkout uses `filter: blob:none` from a remote, and that was not simulated.
