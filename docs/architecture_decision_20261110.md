# Architecture decision, 2026-11-10: a coordinated multi-repository workspace

Status: proposed with the 2026-11-10 change set; in force when the owner merges it.
Paths in backticks are relative to the engine root unless they begin `../patientwords/`
(the site checkout) or name another repository.

## Decision

The project stays a coordinated workspace of separate repositories.

- **The engine owns the scientific workflow**: stimuli, protocols, planning, measurement
  records, statistics, the open-results policy, provenance and every export.
- **The site presents exports.** It computes nothing that the engine has not written or that
  a page cannot derive at runtime from committed data.
- **Method forks supply narrow adapters.** A lens or decomposition library stays in its own
  repository with its own environment. The engine reads typed artifacts through the experiment
  interface (`scripts/experiments/`) and copies no upstream implementation.
- **One manifest records the workspace**: each repository, its upstream, the ref the engine
  was verified against, and the runtime pins the engine consumes. It lives under
  `data/ecosystem/` and is checked against the pin files by `tests/test_ecosystem_manifest.py`.

## Context

Each fact below was read in the working trees on 2026-11-10 unless marked otherwise.

1. **Site CI checks out four engine directories only.**
   `../patientwords/.github/workflows/site_checks.yml:98-109` checks out the engine with
   `filter: blob:none` and a sparse list of `scripts`, `data`, `ops` and `docs`, then runs
   `scripts/validate_frontend_contract.py` and `scripts/check_pages.py` from it. Anything those
   two scripts import or read must be inside those four directories.
2. **The site has no Python and no build step, by decision.** `../patientwords/AGENTS.md:13-15`.
3. **The engine computes; the frontend presents.** `AGENTS.md:70`. The site's invariants forbid
   patching engine-written data there (`../patientwords/AGENTS.md`, *Invariants*).
4. **The engine consumes a published package, not the fork's source.** `constraints.txt:24`
   pins `interp-engine==1.5.1` from PyPI. The local fork checkout
   `michaeldgreenphd/patientwords-interp-engine` is at version 1.14.3 (line 3 of the fork's own
   `pyproject.toml`, head `2afe000`). No engine code or pin file names the fork, so no check compares the two.
   `docs/exploratory/method_readiness_20261024.md:20` recorded the same gap against 1.14.2.
5. **The Petri lane has its own lock.** `docs/framework/petri_environment.lock.json` pins
   Python 3.12.3, the package set and the harness commit `e199ec1a` in
   `michaeldgreenphd/patientwords-inspect_petri`; `.github/workflows/petri_audit.yml:426-438`
   installs from it.
6. **Forks track their upstreams with small local deltas.** From the 2026-11-10 mapping pass
   (comparisons against upstream remotes; not repeated for this record): the ICA lens fork
   equals its upstream head `aa3b95c`; the J-Lens reference fork is the single upstream
   commit `581d398`; the J++ fork adds 9 files (1,639 lines) and modifies no upstream file.
   The interp-engine fork's delta against its upstream was not measured.
7. **A third repository mirrors renders.** `docs/agent_reference.md:310-314` records that
   `patientwords-traces` serves the traces the site does not ship and that its nightly build
   copies `trace_out/<batch>/index_NN.html` from engine `main`. Its workflow is in that
   repository (`docs/README.md`, *Elsewhere*) and was not read for this record.
8. **Visibility differs.** The engine and the site are public (`AGENTS.md:77-78`,
   `../patientwords/AGENTS.md:74`). The physician rating app
   `michaeldgreenphd/patientwords-verify` is private (`docs/README.md`, *Physician verification* row).
9. **Licences differ.** Engine and site code is MIT (`LICENSE`); data terms are in
   `DATA_LICENSE.md`. Of the five local fork checkouts, three are Apache-2.0 (interp-engine,
   J-Lens, J++; J++ carries a `NOTICE`) and two are MIT (ICA lens, with third-party notices;
   Petri harness).

## Alternatives considered

**A monorepo.** Not chosen now. Each reason below names its cost:

- It would bring the forks' upstream histories and their licence and notice obligations into
  one tree. Every upstream merge would become a merge into the study's repository.
- It would put Python and a build next to the site's pages, against fact 2, or require an
  exception that every site review would then have to check.
- It would remove the repository boundary that today enforces analysis versus presentation
  (fact 3). The rule would remain only as a convention.
- Site CI's sparse checkout (fact 1) and the traces mirror (fact 7) both address the engine
  by path. Both would need rewriting, and published trace links depend on the second.
- A private app (fact 8) cannot share a public tree.

**Git submodules.** Not chosen now. Consumed versions are already pinned where they are
consumed: `constraints.txt` for the measurement stack and the Petri lock for that lane. A
submodule would add a second pin for the same dependency, and fact 4 shows the two would
disagree on the first day: the submodule would point at 1.14.3 source while CI installs
1.5.1. The manifest records refs without making Git a second source of truth for installs.

**A live backend or a database.** Not chosen. The site is static by decision, and nothing
measured needs a query service: results are immutable summaries, and the catalogue and
snapshots are generated files. A service would add an availability and security surface with
no research function.

## Consequences

- A cross-repository change is two pull requests. The paired gates in `verify.md` are the
  only check of the contract between them before merge; there is no automated cross-file
  reviewer (`AGENTS.md`, *PR review*).
- A schema that site CI must read lives under `scripts/contracts/`, not `schemas/`, because
  of fact 1. `scripts/contracts/results_catalogue.v1.schema.json` is placed there for that
  reason. Schemas that only engine code reads may live under `schemas/`.
- The manifest is a record, not an enforcement. A fork can move ahead of the recorded ref and
  no check fails. The cost is a stale record until someone re-verifies and updates it.
- An adapter is verified against a recorded fork ref and a recorded artifact hash. Parity with
  a real model is a separate, cited status in the capability matrix.
- Contributors need one route into several repositories. [start_here.md](start_here.md) is it.

## When to revisit

Revisit this decision when any of the following is observed. The numbers are proposals, not
measurements; none has a baseline yet, and the first step is to start counting.

| Signal | Proposed threshold | Where it would be counted |
|---|---|---|
| Engine-to-site contract breaks found only after merge | more than 2 in a calendar quarter | site CI failures on the site's `main` |
| An adapter needs code from two forks imported in one process | 1 occurrence | the adapter's pull request |
| Site CI needs an engine path outside `scripts`, `data`, `ops`, `docs` | 1 occurrence | a change to `site_checks.yml`'s sparse list |
| A recorded fork ref differs from the ref an adapter was actually run against | 1 occurrence in a landed record | envelope `environment.source_commits` against the manifest |
| The same pin is maintained by hand in more than two files | 1 occurrence | review of `constraints.txt`, locks and the manifest |
| Paired pull requests wait on each other | median more than 3 days over a quarter | pull-request timestamps |

A single occurrence of the second or third signal is enough to reopen the question, because
each removes a premise of this record.

## What this decision does not change

- No file, dataset or summary is moved or renamed
  ([migration record](migration_record_20261110.md)).
- No pin changes: `constraints.txt`, the Petri lock and the model revisions are as they were.
- The execution model: nothing paid or networked runs locally; lanes start only through
  `scripts/fire_trigger.py`.
- The site's deployment at `/patientwords/`, its static design and its data ownership table.
- The holdout seal, the open-results policy and every preregistration.
- Who merges: the owner.
