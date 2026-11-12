# Start here: one route into the project

Written 2026-11-10. This page routes a reader to the document that owns each instruction.
It restates none of them. Where this page and a linked document disagree, the linked
document governs and this page is wrong.

Paths in backticks are relative to the engine repository root. A path that begins
`../patientwords/` is in the site checkout, normally the sibling directory.

The project measures how language models respond to the same clinical situation written
in clinical and in everyday wording. It is not a clinical tool and gives no medical advice
([README.md](../README.md)).

A reader who arrives from the site or from a method fork: the
[ecosystem map](ecosystem.md#1-repositories-at-a-glance) says what each repository is
for. Both procedures below are run from an engine checkout.

## Reading paths

Each path is the shortest set of documents for one kind of work. Read them in order.

### New researcher

1. [README.md](../README.md): what the engine measures and the question the study asks.
2. [Protocol template, section 1](protocols/protocol_template.md#1-research-question-and-claim-type):
   the four separate claims (wording sensitivity, clinical relevance, mechanism, equity
   relevance), because evidence for one is not evidence for another.
3. [Known measurement limitations](agent_reference.md#known-measurement-limitations):
   read before quoting any number.
4. [Open-results policy](open_results_policy.md): what is shared, what stays restricted,
   and why sharing a result and counting it in a statistic are separate decisions.
5. The results catalogue: written by `scripts/export_results_catalogue.py` into the site's
   `../patientwords/data/results_catalogue/`, shown by `../patientwords/results/index.html`.
   It lists every run, including null and opposite-direction results.
6. [Protocol template](protocols/protocol_template.md): copy it and fill every field
   before collecting or opening data for a new study.

### Frontend contributor

1. `../patientwords/AGENTS.md`: the site's invariants; the site holds no Python and no build step.
2. `../patientwords/verify.md`: the checks each kind of site change needs.
3. [Scenario payload schema](../scripts/contracts/simulated_scenarios.v1.schema.json) and
   [results catalogue schema](../scripts/contracts/results_catalogue.v1.schema.json): the
   structural contracts the pages read.
4. [Boundary procedure](exploratory/frontend_boundary.md), with the site's
   `../patientwords/docs/boundary-check.md`: the synthetic exporter-to-browser check and its limits.
5. [Paired gates](../verify.md#paired-gates-on-existing-artifacts): how to run
   `scripts/validate_frontend_contract.py` and `scripts/check_pages.py`, which the site's CI
   also runs from an engine checkout.

### Method developer

1. [Contributing a method](contributing_a_method.md): the contribution path and what is out of scope.
2. The experiment interface: package `scripts/experiments/` with schemas under
   `schemas/experiments/`. One run envelope carries one typed payload.
3. The capability matrix, `data/experiments/capability_matrix.v1.json`: what each model,
   method and backend combination can do, with the evidence for each status.
4. [Ecosystem map](ecosystem.md), with its manifest `data/ecosystem/repositories.v1.json`:
   repositories, forks, refs and consumed pins. `python scripts/ecosystem_status.py` compares
   the manifest with the checkouts and pin files on disk and writes nothing.
5. [Methods integration record](exploratory/methods_integration.md): the audited
   compatibility of the existing method forks and the staged plan.
6. [Architecture decision](architecture_decision_20261110.md): why adapters stay in
   their forks and the engine owns the workflow.


### Operator

1. [AGENTS.md, execution model](../AGENTS.md#execution-model-nothing-paid-or-networked-runs-locally):
   nothing paid or networked runs locally; the lane table.
2. [docs/triggers.md](triggers.md): every lane, its trigger keys and what it spends.
3. [Operators handbook](operators_handbook.md): procedures, degradation drills and incident
   records.
4. [fire-trigger-safe skill](../.claude/skills/fire-trigger-safe/SKILL.md): the queue,
   settle-window and budget checks before any fire.
5. [publish-site-data skill](../.claude/skills/publish-site-data/SKILL.md): the publication
   chain in order.
6. [Execution and operations](agent_reference.md#execution-and-operations): the
   single-writer, queue and spend rules.

## Case lifecycle

Two units are in use, and they are not the same thing. A **comparison pair** is two wordings of one
clinical situation measured against each other: in a study batch, one row `(batch, batch_index)` with a
clinical wording and an everyday wording. The gallery lists pairs, and each row of a catalogue run is one
pair. A **case family** is the unit of an experiment protocol: one clinical situation with a fixed set of
reference facts and all of its wordings (`variants`). A protocol names the pairs of variants it compares
(`comparisons`). A family taken from an existing study row joins that row through `legacy_join`, which is
optional. The family is the independent unit of every analysis
([protocol template, section 3](protocols/protocol_template.md#3-population-and-independent-unit)).

Each row links the documents that govern its step, and a quoted command is written as its
source writes it. [Trace A](ecosystem.md#3-trace-a-one-real-result-from-stimulus-to-page)
follows one real result from stimulus to page.

| Step | Where | Command | Who runs it | Governing document |
|---|---|---|---|---|
| Authored: generated batch | The `scenario-generation` lane, in CI, appends a batch and its `.report.json` cost sidecar under `data/simulated/`. Batches are append-only | `python scripts/fire_trigger.py fire --trigger <t> --params '<json>' --note '<why, with settle-bypass evidence if used>'`, with `scenario-generation` as `<t>` | A session that fires, through the script. The lane is paid: only on the owner's explicit words in a live chat | [Operators handbook, section 3](operators_handbook.md#3--standard-operating-procedures); [lanes](triggers.md#lanes); [invariants](../AGENTS.md#research-and-compatibility-invariants); [the generator](../README.md#generating-stress-test-scenarios) |
| Authored: hand-written set | Candidates and the owner's verdicts are files on a draft branch. The committed set is `data/simulated/agscen_*.json`; its `.report.json` sidecar names those files and their commits. These sets are in no analysis membership | `python scripts/check_candidate_pairs.py CANDIDATES.json`; the options are in the script's docstring | A session, before each hand-authored round | [Script index](../scripts/README.md#analysis-and-checks); [memberships](open_results_policy.md#memberships) |
| Reviewed: each case | Per case family, as its protocol declares. The register experiment requires two reviews of the pair. A clinician decides whether the two wordings state the same clinical facts, and sets the reference facts. A patient-language reviewer decides whether the everyday wording is language a patient would plausibly use and carries the same meaning for a lay reader. The result is recorded per family, in the form `pair_equivalence_review`; a family without both reviews keeps `review_status: domain_review_pending`. A model's statement that two wordings are equivalent is not a review. For a hand-written set, the owner's reading is recorded per candidate in the sidecar (`excluded_by_owner`, `retiered_by_owner`); it is neither of the two reviews | None. Reviewers fill the form | A clinician and a patient-language reviewer; physicians, in a private rating app (draft protocol); the owner reads hand-written candidates | [Register experiment, section 4](protocols/instrument_register_experiment_20261111.md#4-clinical-facts-held-equal-and-who-reviews-what); [protocol template, section 4](protocols/protocol_template.md#4-clinical-facts-held-equal); [review index](review/README.md); [physician protocol](verification_protocol.md) |
| Reviewed: the catalogue's label | One label for a whole stimulus class: `clinical_review` in `data/results_policy/policy.v1.json`, which the results catalogue prints on every run of the class. It states the status of the class. It does not record that any case was reviewed | None. A class gets its label with its `stimulus_classes` entry in that file | The owner, in a reviewed pull request | [Open-results policy](open_results_policy.md#the-rule), with [adding a family](open_results_policy.md#adding-things) |
| Measured | CI lanes. Trace and logits summaries land under `trace_out/`. A locally produced value is not a measurement | `python scripts/fire_trigger.py status`, then the fire command above with the lane's trigger; when the run is terminal and every expected output has landed, `python scripts/fire_trigger.py resolve --trigger <name>` | Every session that fires, and the Routine. A paid fire only on the owner's explicit words | [Procedure B](#procedure-b-model-execution); [fire-trigger-safe skill](../.claude/skills/fire-trigger-safe/SKILL.md); [harvest-resolve skill](../.claude/skills/harvest-resolve/SKILL.md); [script index](../scripts/README.md#ops-tooling-and-the-routine) |
| Published | The chain writes `../patientwords/data/` and `../patientwords/modes/simulated/`. The site push is the publication: GitHub Pages serves the site's `main` | The chain, in the skill's order. `python scripts/results_snapshot.py check-release --site ../patientwords` must exit 0 before any push | The Routine, when new results land; by hand under the same skill. Data files only, never page text | [publish-site-data skill](../.claude/skills/publish-site-data/SKILL.md); [script index](../scripts/README.md#publish-chain); the site's `../patientwords/verify.md` |

## Procedure A: offline quickstart

This procedure calls no model, needs no API key, no GPU stack and no method fork.

Prerequisites:

- Python 3.12 or later, as [verify.md](../verify.md#setup-and-sources-of-truth) states and explains.
- Package-index access for the install, unless the dependencies are cached.
- A Git checkout of the engine. `tests/test_doc_paths.py` resolves paths with
  `git ls-files` and skips, visibly, in a tree without Git metadata.
- Optional: the site checkout. The shared-conventions tests skip visibly without it.
  The paired gates and the page check need it.
- Optional: Chromium with Playwright, for `scripts/check_pages.py` and the browser tests only.
  The [environment table](../verify.md#environment-fixtures-and-services) has the install
  and the executable override.

Steps:

1. Run the setup block in [verify.md, Setup](../verify.md#setup-and-sources-of-truth), then
   activate the environment as that section says.
2. Run the block in [verify.md, Quick path](../verify.md#quick-path). Read the skip reasons
   that `-ra` prints. A skip is a check that did not run.
3. Run the offline experiment slice on the synthetic fixture:

   ```bash
   (
   set -euo pipefail
   # From the engine root, with the environment active.
   PW_SLICE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/patientwords-slice.XXXXXX")
   PW_SLICE_PROTOCOL=tests/fixtures/experiments/protocol_synthetic_ica.json
   python -m scripts.experiments.cli validate --protocol "$PW_SLICE_PROTOCOL"
   python -m scripts.experiments.cli plan --protocol "$PW_SLICE_PROTOCOL" --out "$PW_SLICE_DIR/plan.json"
   python -m scripts.experiments.cli run-fixture --plan "$PW_SLICE_DIR/plan.json" \
     --fixtures tests/fixtures/experiments --run-dir "$PW_SLICE_DIR/runs"
   python -m scripts.experiments.cli collect --run-dir "$PW_SLICE_DIR/runs"
   python -m scripts.experiments.cli compare --run-dir "$PW_SLICE_DIR/runs" --out "$PW_SLICE_DIR/compare.json"
   python -m scripts.experiments.cli bundle --run-dir "$PW_SLICE_DIR/runs" --out "$PW_SLICE_DIR/bundle.json"
   printf 'Slice output (remove when done): %s\n' "$PW_SLICE_DIR"
   )
   ```

   The run directory is outside the checkout on purpose: the run store refuses a path inside
   a Git checkout. It is created under `$TMPDIR`, or under `/tmp` when that is unset. A
   refusal prints a JSON object with `"status": "refused"` and exits 2.

Status on 2026-11-10: steps 1 and 2 were executed from a clean copy; the outcomes are in the
[migration record](migration_record_20261110.md#clean-copy-run). Step 3 was executed in the
working tree and is pinned by `tests/test_experiments_slice.py`: 45 planned tasks, of which
27 are ready, 9 unavailable and 9 unsupported, each with its reason; a second
`run-fixture` executes nothing and reuses all 27. To see an interruption and a resume, add
`--stop-after 5` to the first `run-fixture` and run it again without the flag.

Status on 2026-11-11: the three steps were run again as written, in the working tree, with
a new Python 3.12.3 environment kept outside the checkout (the one substitution: the
environment's path). The install resolved pytest 9.1.1, ruff 0.16.10 and PyYAML 6.0.3. The
quick path passed with no skip (125 tests; the site checkout was present). The slice gave
the counts above, and the second `run-fixture` reused all 27.

To see the bundle in a browser, run the preview check described in
[experiment_interface/preview.md](experiment_interface/preview.md). It needs the site checkout
and Chromium, builds the same synthetic bundle in a temporary copy of the site and checks the
viewer page `../patientwords/experiments/index.html` against it.

What this procedure shows: the developer install works, the documentation gates pass or
name their failures, and the slice code handles a synthetic fixture. It shows nothing about
a model. The fixture is synthetic, and its output is a software check, not a measurement.

## Procedure B: model execution

No command on this page starts a model job, and none should be run from a developer machine.
Generation, tracing, inference and judging run in CI lanes. A lane starts only through
`scripts/fire_trigger.py`. A locally produced value is not a measurement.

Read, in this order, before any fire:

1. [AGENTS.md, execution model](../AGENTS.md#execution-model-nothing-paid-or-networked-runs-locally):
   the policy and the lane table.
2. [Execution and operations](agent_reference.md#execution-and-operations): queue, single
   writer, spend ceilings and the scope of owner approvals.
3. [docs/triggers.md](triggers.md): the lane's keys, park defaults and cost.
4. [fire-trigger-safe skill](../.claude/skills/fire-trigger-safe/SKILL.md): the procedure itself.
5. [Protocol template, section 19](protocols/protocol_template.md#19-execution-route):
   what a study records about its route and approvals before it runs.

Preparing an offline plan or a fixture run is not authorization to spend or to publish.

## Known stale navigation

These documents disagree today. Each row names the canonical source. The documentation
change of 2026-11-11 fixed the three rows of 2026-11-10 that were in
`docs/operators_handbook.md` (the lane count, the site data contract, the latest owner
decision record) and the install sentence in `docs/fresh_session_bootstrap.md`, which now
points at `verify.md`. It did not edit the files below: the environment setup script and
the guard files are the owner's, and sessions cannot write under `.github/trigger/`. Line
numbers are those of the working tree on 2026-11-11 and move when the files change.

| Fact | Stale statement | Canonical source |
|---|---|---|
| Developer install command | `ops/environment_setup.sh:28` installs unpinned `pytest ruff pillow pyyaml`. | `verify.md:34`, whose ranges match `pyproject.toml`. `pillow` is declared in neither. |
| Where the dev install is documented | `.claude/hooks/README.md:53` and `ops/environment_setup.sh:21` cite `AGENTS.md` (*Commands*). `AGENTS.md` has no *Commands* section. | `verify.md:11` (*Setup and sources of truth*). The hooks README is owner-only. |
| Where a guard refusal points | `.claude/hooks/guard_paths.py:51,54`, `.claude/hooks/guard_git.py:96` and `.githooks/pre-commit:13` cite `AGENTS.md` (*Ops tooling*, *Single-writer*). `AGENTS.md` has neither paragraph. | `docs/agent_reference.md:70` (*Ops tooling*) and `:306` (*Single-writer invariants*). The guard files are owner-only. |
| Lanes described under the trigger directory | `.github/trigger/README.md:3` describes two lanes. Sessions cannot edit that directory. | `docs/triggers.md`, and the lane table in `AGENTS.md`, which `tests/test_trigger_docs.py` compares with the wired workflows. |

Cost of leaving these: a reader who follows the setup script installs unpinned tools,
not the ranges `verify.md` and `pyproject.toml` give, and a reader who
follows a refusal message or the hooks README looks for a section that does not exist. The
fix for each is a one-line edit in the stale file, made by whoever owns that file.
