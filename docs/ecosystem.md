# Ecosystem map

Current as of 2026-11-11. The five fork heads and every upstream tip were read on that date; the mapping pass is
of 2026-11-10. The machine-readable form is
[`data/ecosystem/repositories.v1.json`](../data/ecosystem/repositories.v1.json); `python scripts/ecosystem_status.py`
compares it with the checkouts and pin files on disk and writes nothing. Rules are not restated here: the
invariants are in [AGENTS.md](../AGENTS.md), the checks in [verify.md](../verify.md), sharing and membership in
[open_results_policy.md](open_results_policy.md), and the upgrade procedure in
[upgrade_checklist.md](upgrade_checklist.md).

**Where to start.** Work on PatientWords starts from an engine checkout.
[start_here.md](start_here.md) has the reading paths by role and the offline quickstart
([Procedure A](start_here.md#procedure-a-offline-quickstart)), which needs no fork checkout. The table in
section 1 gives each repository's role. Section 2 records what the engine consumes from each repository and which
of its tests have run here.

**The short answer.** The project is two core repositories, five method forks and three repositories whose identity
is resolved from engine source. The engine executes code from two of the forks only, and in both cases not from
the fork's current head: interp-engine as the PyPI distribution 1.5.1 (the fork source declares 1.14.3), and
inspect_petri at commit `e199ec1a` (the fork head is `5ee1f549` and needs newer Inspect packages than the lock
holds). The owner's fork sync of 2026-11-10 and README merges of 2026-11-11 changed source only. No pin moved and
no run used the new source.

How to read the status words. **VERIFIED (doc, read)**: the file was read at the cited line while writing this
document. **VERIFIED (doc, ran)**: a read-only command was run for this document. **VERIFIED (map, read)** or
**(map, ran)**: the mapping pass of 2026-11-10 did so and it was not repeated here. **CONCERN**: a reasoned
failure path that nobody has tested. Line numbers are for the working tree of 2026-11-10; other files of the same
change set were still being edited, so a number may be off by a few lines at merge. Function names are given
where they exist.

## 1. Repositories at a glance

| Repository | Role | What the engine consumes from it, and as what | Recorded head |
|---|---|---|---|
| `patientwords-engine` | generation, measurement, analysis, export | itself | `d8d0855d` (base of this change set) |
| `patientwords` | public static site | `generated_files`: its `data/*.json`, read back by later publish steps; `source_checkout`: page HTML for the checkers. No pin | `b7da4530` |
| `patientwords-ica-lens-paper` | ICA Lens paper (arXiv:2606.11722v2) and `icalens` library | `none` today. An optional offline adapter was added in this change set; fixtures only | `103aadab` |
| `patient-words-jpp_lens` | J++ Lens plus the owner's `lens_interop` contract | `fitted_artifact`: the released Qwen3-4B J++ file, sha256 `893f7da2…`, fit identity unknown, inspected and never used. `source_checkout`: `lens_interop` in one manual script, no pin | `2672473d` |
| `patientwords-interp-engine` | interpretability runtime | `installed_distribution`: `interp-engine==1.5.1` from PyPI (`constraints.txt`). Not the fork source | `758220c4` |
| `patientwords-inspect_petri` | conversation-audit harness | `source_checkout` at `e199ec1a`, installed from git under `docs/framework/petri_environment.lock.json` | `5ee1f549` |
| `jacobian-lens-patientwords` | original J-Lens reference | `none`: method description and credit strings | `29ff70ea` |
| `patientwords-traces` (outside the seven) | public render site | `none` read back. The engine copies renders into it and stamps its URLs | `96bd3cd6` (remote tip, not an owner anchor) |
| `patient-words-causalab` (outside the seven) | intervention library, staged | `source_checkout` at a commit that is not set (`causalab_commit: null`); never run | `1db3b8ce` (remote tip, not an owner anchor) |
| `patientwords-verify` (outside the seven) | private physician-rating app | `generated_files`: one ratings export, read from outside the checkout | not recorded (private) |

Two things reach the engine without being one of these repositories. The J-Lens and logit-lens readouts come from
the hosted Neuronpedia endpoint `POST /api/lens/prompt` (`scripts/jlens_readout.py:43-44`), type `hosted_service`,
with no lens artifact, lens revision or model revision recorded. Model weights come from Hugging Face at one
40-hex revision per model (`HF_REVISIONS`, `scripts/logits_eval.py:131`), type `model_weights`. The manifest
lists both under `external_services`.

Heads of the two core repositories were confirmed with `git rev-parse` on the local clones on 2026-11-10. The five
fork heads were confirmed on 2026-11-11, after the owner merged one README orientation note into each fork. Each
merge added two commits: the note and its merge commit. No hand-written code, dependency or pin changed.
`git ls-remote` on 2026-11-10 showed four forks at their upstream's tip (ICA, interp-engine, Petri, J-Lens). The
J++ fork was seven commits ahead of `safety-research/jpp_lens` and none behind, checked that day in a local clone
with full history. The two commits of 2026-11-11 raise the counts ahead to two and nine. On 2026-11-11
`git ls-remote` returned the same upstream tip for J++, interp-engine and J-Lens, so those three stay none behind.
It returned another tip for ICA (`9b7d1cbd`) and for Petri (`797c7c12` at 21:52 UTC, then `adf985b8` at 21:54
UTC). Those two were counted on 2026-11-12, after each new tip was fetched into the local clone: each tip descends
from the 2026-11-10 tip and is two commits past it, so each fork is two commits ahead of its upstream and two
behind, with diverged histories. Bringing either fork up to date is a merge and is the owner's decision. The
numbers of upstream commits the sync brought in (55 for interp-engine, 13 for Petri) are owner-reported: those
two clones are shallow, so they cannot be re-derived. The default branches of the two core repositories had moved past the recorded heads
by the time of the 2026-11-10 check (`61b33f96`, `f1504ce9`).

## 2. Each repository

Facts below were read in the engine or fork files for the manifest, or are marked (map, …). For the ICA fork, the formats, the upstream-pointing URLs and the commit history are (map, read) except where a line is cited in finding 20.

### patientwords-engine

- **Purpose and role.** Generates paired stimuli, measures model behaviour, analyses, exports. Runs in push-to-run CI; nothing paid or networked runs locally (AGENTS.md, *Execution model*).
- **Fork relationship.** Not a fork. README.md records an earlier port from a Neuronpedia fork branch; that is history.
- **Licence.** MIT for code (`LICENSE`); `DATA_LICENSE.md` for data.
- **Maintenance.** The owner. Agents open pull requests; the owner merges.
- **Entry points.** Four console commands (`pyproject.toml`); `scripts/*.py`, indexed in [scripts/README.md](../scripts/README.md); eleven trigger lanes fired through `scripts/fire_trigger.py`; `python -m scripts.petri_audit.cli`; `python -m scripts.experiments.cli`.
- **Formats.** In: `data/simulated/<stem>.json` batches (a JSON list of pairs, no id field). Out: `trace_out/<stem>[__<model>]/batch_summary.part_NN.json`, lens summaries, Petri run directories with a hash-chained manifest, site payloads.
- **Environment.** Python `^3.10` declared; measurement lanes run 3.11 under `constraints.txt`; the Petri lane runs 3.12.3 under its lock; the boundary check needs 3.13 and `scripts/boundary_client/requirements.lock`.
- **Tests and CI.** pytest under `tests/` and ruff. One pull-request workflow, `.github/workflows/pr_checks.yml`, runs both on every pull request: once on the engine alone and once beside a resolved site commit (`verify.md:152`, `verify.md:169`). The other 13 workflows are measurement and operations lanes.
- **Active versus historical.** `scripts/README.md` marks each script. `trace_out/` and `data/simulated/` are append-only. Dated documents describe their own revisions.
- **Writers and readers.** CI writes measurements; sessions write code and documents; the Routine writes `ops/dashboard.json`. Readers: the site (through exports), the traces site, the verify app.
- **Stable identifiers.** `(batch stem, 1-based index, model)` for a measurement; the repo-relative part path plus sha256 for a logits part; `(run stem, conversation_id, turn_id, kind, key, prompt_file_digest, judge_model)` for a Petri judgment.
- **Publication boundary.** Public repository. Sealed Tier B rows are present in `data/simulated/` and `trace_out/` by design; the seal withholds them from interim analysis and from derived published artifacts (`docs/prereg_amendment3_holdout.md`).
- **Depends on.** The site checkout for exports and paired checks; Neuronpedia, Hugging Face and PyPI in CI.

### patientwords

- **Purpose and role.** The public gallery, served by GitHub Pages at `/patientwords/`. Pages fetch committed JSON.
- **Fork relationship.** Not a fork.
- **Licence.** MIT for code; CC BY 4.0 for published data and renders (`DATA_LICENSE.md` there).
- **Maintenance.** The owner. The engine writes its data; two files are hand-maintained (site AGENTS.md, *Invariants*).
- **Entry points.** `index.html`, `methods.html`, section `index.html` pages, `simulated-scenarios/scenario.html?sim=<n>[&model=<id>]`.
- **Formats.** In: engine exports. Structural authority for the scenario payload: `scripts/contracts/simulated_scenarios.v1.schema.json` in the engine.
- **Environment.** No build system, no Python, no Node.
- **Tests and CI.** No tests of its own. `site_checks.yml` runs two engine checkers against a sparse engine checkout (finding 1).
- **Active versus historical.** `SITE_COPY_OUTLINE.md` is a historical working copy. `docs/boundary-check.yml.example` is inactive.
- **Writers and readers.** Writer table: the site's `docs/agent_reference.md`. Readers: the public; the engine reads the payload back in three publish steps.
- **Stable identifiers.** `(batch, batch_index)`; `scenario.index` is display order and the `?sim=` value, not a research id.
- **Publication boundary.** Everything here is public. Holdout rows are withheld by the exporters and swept by `scripts/seal_check.py`.
- **Depends on.** The engine for all data and for both CI checkers; the traces site for `trace_url` links.
- **Sibling path.** `../patientwords`. Scripts take `--site` (or `--frontend`); `PW_SITE_ROOT` is read by four test files and by no script.

### patientwords-ica-lens-paper

- **Purpose.** The ICA Lens paper repository around the installable library `icalens` 0.4.0. The paper is Sida Liu, Feijiang Han, Sarah Wiegreffe and Furong Huang, "Non-Gaussianity Reveals Interpretable Directions in Language Models", arXiv:2606.11722v2 (version 2 submitted 2026-10-19). VERIFIED (doc, ran): title, version, authors and date read on the arXiv abstract page on 2026-11-10 (record `arxiv.2606.11722v2` in `data/experiments/neuronpedia_evidence/20261110_reference_pages/index.v1.json`).
- **Fork relationship.** Fork of `liusida/ica-lens-paper`. On 2026-11-10 the fork and the upstream were at the same tip, `aa3b95c9`. On 2026-11-11 the fork is two commits ahead of that tip: one README orientation note and the owner's merge commit for it, both of 2026-11-11. They change `README.md` only. On 2026-11-11 `git ls-remote` returned another upstream tip, `9b7d1cbd`. It descends from `aa3b95c9` and is two commits past it, so the fork is two ahead and two behind (counted 2026-11-12 with `git rev-list --left-right --count`). Project URLs and the model-framing registry URL still point upstream.
- **Runtime role.** None in any engine lane. The adapter `scripts/experiments/adapters/ica.py` applies a saved basis with numpy and uses `icalens` only where it imports. It fits nothing.
- **Licence.** MIT. `THIRD_PARTY_NOTICES.md` carries the FastICA_torch notice for `_fastica.py`; copied code must carry both.
- **Maintenance.** Upstream authors; the upstream commit the fork holds (`aa3b95c9`) is dated 2026-11-10.
- **Entry points.** `icalens.ICALens` and `ActivationDataset`; the `icalens` CLI, whose fit and capture commands require CUDA.
- **Formats.** ActivationDataset: `activations.json`, `samples.safetensors`, `layer_NN.safetensors`. Lens artifact: `icalens.json` plus per-layer safetensors. Site `resid_post` only; zero-based layers.
- **Environment.** Python `>=3.10`; `transformers==5.14.1` exactly, equal to the engine's pin; `uv.lock`.
- **Tests and CI.** 28 test files on synthetic data; none run here (no torch). The only workflow publishes to PyPI on a release; nothing runs tests.
- **Active versus historical.** Commit `c4f3528` replaced the arXiv v1 implementation with v2. The README citation block is still the v1 title.
- **Stable identifiers.** Hugging Face lens ids `sida/icalens-*`; component `C<index>` within one basis. A component index means nothing across two bases.
- **Publication boundary.** Public upstream code. No PatientWords data is in it.
- **Depends on.** Hugging Face for published lenses (not read by the engine).

### patient-words-jpp_lens

- **Purpose.** J++ Lens fitting and evaluation, plus the owner's `src/lens_interop/`: verify a lens file by hash, check geometry, refuse transport when the fit identity is unknown.
- **Fork relationship.** Fork of `safety-research/jpp_lens`. It is nine commits ahead: five owner commits of 2026-10-15, two merges, and the README orientation note of 2026-11-11 with the owner's merge commit for it. It is none behind the upstream tip `d7efc0de`, read on 2026-11-10 and again on 2026-11-11. The whole delta is nine added files and one modified upstream file, `README.md` (`git diff --name-status` against `d7efc0de`, run 2026-11-11).
- **Runtime role.** None in a measurement. `tests/manual/exploratory_bridge.py` imports `lens_interop` on synthetic tensors and needs torch.
- **Licence.** Apache-2.0 with `NOTICE`: `src/jlens/` is vendored from `anthropics/jacobian-lens` at `581d3986`; the LRP rules are adapted from R-Lens.
- **Maintenance.** Upstream authors for the method; the owner for `lens_interop`.
- **Entry points.** `python -m lens_interop --manifest PATH` and `--inspect PATH --sha256 HEX`. No console command is installed.
- **Formats.** Interchange manifest: `schemas/lens-interop-v1.schema.json` there. Lens files are `torch.save` archives loaded with `weights_only=True`.
- **Environment.** Python `>=3.12`; every dependency pinned exactly, `transformers==5.14.1` among them.
- **Tests and CI.** Two test modules under `src/lens_interop/tests/`; one skips without torch. No CI: there is no `.github` directory.
- **Active versus historical.** `data/exploratory/method_sources.v1.json` records fork commit `93f02cd6` (2026-10-15), ten commits behind the head. It is a dated receipt and is not edited.
- **Stable identifiers.** Artifact sha256; Hugging Face repository revision `e166deb5`; model and tokenizer revision of the fit, which are unknown for the released Qwen3-4B file.
- **Publication boundary.** Nothing from it is published. The released artifact stays outside Git.
- **Depends on.** The J-Lens reference (vendored); Hugging Face for released lens files.

### patientwords-interp-engine

- **Purpose.** Standardized capture, steering, lens and generation over Hugging Face models, with eager and vLLM backends.
- **Fork relationship.** Fork of `decoderesearch/interp-engine`. It is two commits ahead of the upstream tip `2afe000d`, read on 2026-11-10 and again on 2026-11-11. The two commits are one README orientation note and the owner's merge commit for it, both of 2026-11-11. They change `README.md` and the generated `visualizer-web/knowledge/bundle.generated.ts` that embeds it. The package directory is byte-identical to the PyPI 1.14.3 wheel (map, ran `diff -rq` at `2afe000d`; the two later commits do not touch `interp_engine/`).
- **Runtime role.** The engine's `mode: depth` and `mode: verify` install `interp-engine==1.5.1` from PyPI on Python 3.11, eager backend on CPU (`.github/workflows/logits_evaluation.yml:303-306`). The fork is not installed anywhere.
- **Licence.** Apache-2.0; no NOTICE file.
- **Maintenance.** Upstream, active (v1.14.3, 2026-10-27).
- **Entry points the engine uses.** `load_model`, `sync_model`, `layer_logits`, `generate_stream` (`scripts/depth_probe.py:218-292`, `scripts/verify_probs.py:113-233`).
- **Formats.** Out of the engine's scripts: `depth_probe.part_NN.json`, `verify_summary.part_NN.json`, which stay outside measurement collectors.
- **Environment.** Python `>=3.11,<3.14`; the fork's `uv.lock` resolves transformers 5.16.1; the engine pins 5.14.1.
- **Tests and CI.** The fork has a CPU test workflow and GPU-marked tests; none run here.
- **Active versus historical.** `docs/interp_engine_assessment.md` assessed fork commit `74716092` (package 1.5.1). Its validator-coverage statements do not hold at the recorded head (finding 21).
- **Stable identifiers.** A landed summary records `interp_engine.__version__` only. That string cannot tell a PyPI wheel from a fork commit with the same version.
- **Publication boundary.** Depth results reach the site through `export_jlens_depth.py` and related exporters; verify summaries do not.
- **Depends on.** PyPI; Hugging Face weights at pinned revisions.

### patientwords-inspect_petri

- **Purpose.** Multi-turn audit harness on Inspect and Scout.
- **Fork relationship.** Fork of `meridianlabs-ai/inspect_petri`. On 2026-11-10 the fork and the upstream were at the same tip, `de5dad81`. On 2026-11-11 the fork is two commits ahead of that tip: one README orientation note and the owner's merge commit for it, both of 2026-11-11. They change `README.md` only. On 2026-11-11 `git ls-remote` returned another upstream tip: `797c7c12` at 21:52 UTC, then `adf985b8` at 21:54 UTC. Both descend from `de5dad81`: they are the two commits the upstream added, so the fork is two ahead and two behind (counted 2026-11-12 with `git rev-list --left-right --count`).
- **Runtime role.** The Petri lane installs every package in the lock with `==`, then the harness with `--no-deps` from git at the locked commit, then runs `verify-lock` (`.github/workflows/petri_audit.yml:426-443`). The engine supplies its own scripted controller and attaches no Petri scorer.
- **Licence.** MIT; no NOTICE file.
- **Maintenance.** Upstream, active (release 3.1.1).
- **Entry points the engine uses.** `audit_solver`, `target_agent`, `select_timeline`, `inspect_petri.target.controller` (`scripts/petri_audit/task.py`, `controller.py`, `adapter.py`).
- **Formats.** In: a raw Inspect `.eval` log. Out: transcript 0.2 records and a run manifest (`docs/framework/transcript.schema.json`, `petri_run_manifest.schema.json`).
- **Environment.** Lock of record: Python 3.12.3, inspect-ai 0.3.237, inspect-scout 0.4.39, anthropic 0.105.0, openai 2.40.0. Fork head requires inspect-ai `>=0.3.276` and inspect-scout `>=0.5.3`.
- **Tests and CI.** The lock records 737 passed and 1 failed for the fork's suite at the locked commit. The engine's `tests/petri/` needs the harness and skips without it.
- **Active versus historical.** Nine landed runs name harness `e199ec1a` and lock digest `4aecf38c…`. They are chained records and are not re-adapted in place.
- **Stable identifiers.** Run stem `run_<workflow run id>_<attempt>`; `chain.identity_sha256`; `conversation_id`; the judge's model string.
- **Publication boundary.** Sanitised logs and transcripts are committed; raw `.eval` logs are held as CI artifacts for 90 days and are not published.
- **Depends on.** PyPI at locked versions; model providers in paid modes.

### jacobian-lens-patientwords

- **Purpose.** Companion code for the Jacobian-lens paper. README: "Reference implementation. Not maintained and not accepting contributions."
- **Fork relationship.** Fork of `anthropics/jacobian-lens`, whose one commit is `581d3986` (read on 2026-11-10 and again on 2026-11-11). The fork is two commits ahead of it: one README orientation note and the owner's merge commit for it, both of 2026-11-11. They change `README.md` only.
- **Runtime role.** None. The engine never ran it. The commit string does not occur in the engine.
- **Licence.** Apache-2.0; no NOTICE file; `data/` is synthetic and under the same licence.
- **What the engine takes.** The method description and the authors' limitations (`docs/jlens_evaluation.md`) and the credit string in every lens summary (`scripts/jlens_readout.py:319-321`).
- **Environment, tests, CI.** Python `>=3.10`, unpinned dependencies; five test files; no CI.
- **Active versus historical.** Frozen. The engine's planned pinned-commit local route was never implemented; the hosted route replaced it.

### Outside the seven: identity resolved from engine source

- **patientwords-traces.** A GitHub Pages site for per-scenario trace renders. URL scheme `<base>/t/<batch>/index_<NN>.html` from `batch` and `batch_index` (`scripts/export_traces_site.py:38`, `:69`). Writers: that repository's own build workflow, which copies engine renders (stated in `docs/README.md:151` and `docs/agent_reference.md:310`; the workflow file was not read), and `export_traces_site.py` without `--stamp-only`, which copies into a local checkout at `--traces-repo` (default `../patientwords-traces`) and returns 3 when it is absent (`:91`). Readers: `scenario.html` and `technical/index.html` use `trace_url` as a link target. The engine has no liveness check for those links (finding 22). No local checkout existed; its licence and tests were not read.
- **patient-words-causalab.** Owner fork of `goodfire-ai/causalab`, named in `data/exploratory/method_sources.v1.json`. Planned as an independent second implementation in the one-case baseline preflight (`scripts/exploratory_baseline_preflight.py --backend causalab`). It has not run: `data/exploratory/baseline_ci_readiness.v1.json` has `status: blocked_not_authorized` and `causalab_commit: null`. The licence of the Python distribution is unresolved; the engine's record says the Rust workspace declares Apache-2.0 and no root licence file was found. On 2026-11-10 the fork tip (`1db3b8ce`) and the upstream tip (`07cf9b96`) differed; ahead and behind were not derived.
- **patientwords-verify.** The private physician-rating app (`docs/verification_protocol.md`). `scripts/export_verification_tasks.py` writes `data/verification/tasks_<stamp>.json` (schema `patientwords-verification-tasks/1`), which the owner uploads. `scripts/import_verification_ratings.py` reads one export (schema `patientwords-verification-ratings/1`) from a path outside the checkout, refuses a path inside it, and writes summaries without note text. No summary has been imported. Nothing else about that repository is recorded here.

## 3. Trace A: one real result, from stimulus to page

The row is `(pairs_20260707T171223Z, 5)`. It is not a Tier B row: the batch stamp precedes `tierb.start_utc` (map, read). It is named by stem and index only.

| Hop | What happens | Identifier at this hop | Where | Status |
|---|---|---|---|---|
| 1. Stimulus | The generation lane wrote `data/simulated/pairs_20260707T171223Z.json`, a list of 119 pairs, and its `.report.json` sidecar | file stem plus list position `[4]`; the row has no id field | `medlang_circuits/scenario_gen.py:1356-1377` (sidecar) | VERIFIED (doc, ran): 119 rows, four keys per row |
| 2. Measurement | The hosted lane wrote `trace_out/pairs_20260707T171223Z/batch_summary.part_05.json`; logits models write `trace_out/<stem>__<model>/batch_summary.part_NN.json` | directory stem, `results[].index` = 5 (1-based), summary `graph_model`, `source_set` | `medlang_circuits/batch_eval.py:1221` (`run_batch`), `:1294-1301`; `scripts/logits_eval.py:456` | VERIFIED (doc, ran): `backend: hosted`, `start_index` 5, indices 5 to 8 |
| 3. Admission | Each part passes the default-membership gate before any collector reads it | repo-relative part path plus sha256 for logits parts (`data/publication_release/logits_parts.json`) | `scripts/results_policy.py:513` (`Gate`), `:593` (`admit`); called at `scripts/export_frontend_simulated.py:271` | VERIFIED (doc, read) |
| 4. Analysis | The collector builds one row per `(model, batch, index)`, stamps Tier B rows, and the registered statistics collapse rows to one record per clinical phrase per model | `(model, batch, index)`, then the clinical phrase within a model; the row is not individually visible in `model_stats.json` | `scripts/urgency_shift.py:115`, `:176`, `:195`, `:255`; `scripts/paired_stats_rigor.py:96` (`load_rows`), `:357` (`analyze`) | VERIFIED (doc, ran): seven urgency rows exist for this `(batch, index)` |
| 5. Export | The exporter reads the pair by position, applies the holdout check, assigns the display index and builds the per-model objects and the base-model mirror | `(batch, batch_index)` = `(pairs_20260707T171223Z, 5)`; key of `scenario.models`; `scenario.index` = 41, display only | `scripts/export_frontend_simulated.py:371`, `:379-381`, `:384`, `:393-395`, `:117` (`COMPAT`), `:600` | VERIFIED (doc, ran): `$.scenarios[40]`, four models; the three base-model numbers equal the summary's |
| 6. Later joins | Urgency and depth class are embedded; the trace URL is stamped | `(batch, batch_index, model)`; `(batch, batch_index)`; `<base>/t/<stem>/index_05.html` | `scripts/embed_scenario_joins.py:65`, `:91`; `scripts/export_traces_site.py:69` | VERIFIED (doc, ran): the row carries `urgency`, `depth_class` and `trace_url` |
| 7. Render | The base model's render is copied for the 200 rows with the highest consequence score | `modes/simulated/<stem>/index_05.html` | exporter `_consequence` (`:449`), `ranked[:max_renders]` (`:455`) | VERIFIED (doc, ran): the file exists in both checkouts |
| 8. Page | The index page links each row; the detail page resolves `?sim=41` by equality on `scenario.index` and embeds the render | `scenario.html?sim=41[&model=<id>]` | site `simulated-scenarios/index.html:576`, `:948`, `:964`; `scenario.html:369`, `:375`, `:396`, `:515` | VERIFIED (doc, read); not rendered in a browser here |

The identifier changes four times: list position, 1-based result index, `(batch, batch_index)`, display index. Only `(batch, batch_index, model)` is stable. Three more models are measured for this row in the engine and are absent from the site payload, which was last rebuilt on 2026-08-29 with four models (map, read; finding 16).

## 4. Trace B: the synthetic exporter-to-browser boundary check

`scripts/check_frontend_boundary.py`, documented in [exploratory/frontend_boundary.md](exploratory/frontend_boundary.md).

1. Copies the engine's `scripts/` and the site (without `.git`) into a temporary sibling layout (`:106-107`). Identifier: none yet.
2. Runs five offline test modules inside it (`UNIT_TESTS`, `:35-38`, `:115`).
3. Writes the fixture's engine files and site substitutes (`:125-128`). Identifier: fixture stamp `20000101T000000Z`, three synthetic pairs by index.
4. Runs the real exporter CLI with `--models gemma-2-2b,qwen3-4b` (`:136`). Identifier: `(batch, batch_index)` and display `index`, as in Trace A hop 5.
5. Runs `check_simulated` on the export, in process and from the sparse layout (`:144`, `:151-153`), and `generate.py --check` (`:157`).
6. Serves the tree under `/patientwords` on loopback and fetches the payload with the handwritten client (`:160-168`). Identifier: the URL path `data/simulated_scenarios.json`.
7. Drives the real `simulated-scenarios/index.html` in Chromium with non-loopback requests blocked, then the negative controls (`:171-262`; eight, per the mapping pass). Identifier: displayed row text for the synthetic pairs.

Status: VERIFIED (doc, read) for the steps and line numbers. Not run here: the check needs Python 3.13 with `jsonschema` and the locked tools, which the project venv lacks (map, read). Its receipt, `docs/exploratory/frontend_boundary_receipt.json`, is dated 2026-10-16 and names engine `ef22c7b9` with `dirty: true`; it describes that tree, not today's. The check is not in site CI.

### Where the two traces share code, and where synthetic evidence stops

Shared: the exporter's module body (argument parsing, `read_trace_dir`, the row loop, the mirror, `models_meta`, the payload write); the hosted branch of the gate; `clinical_mass_publishable`; the schema through the stdlib adapter; `check_simulated`; the index page's JavaScript.

The synthetic check does not reach: the logits backend and the part-hash record (three of the four published models are logits-only); models outside the default membership; holdout withholding (the fixture's Tier B start is in 2099); render copy and the 200-row cap; more than one stamp; mixed backends or source sets per model; `urgency_shift.py`, `embed_scenario_joins.py` and `export_traces_site.py`; `scenario.html`; every other page that fetches the payload; real payload size; GitHub Pages itself. It is software evidence that one exporter path produces a payload one page renders for six synthetic measurements. It says nothing about a published value.

## 5. Test coverage

A path is listed as exercised only where a test runs it. Files existing is not evidence.

| Area | Exercised by | Not exercised |
|---|---|---|
| Exporter end to end | `tests/test_render_prune.py` (16 tests), `tests/test_qwen3_4b_source_set.py`, `tests/test_publication_hold.py` (27): the real exporter as a subprocess on small synthetic trees | a missing or unreadable dashboard (finding 3); the traced-prompt holdout clause; `models_meta.graphs` under mixed backends; the 200-row ranking |
| Payload structure and semantics | `tests/test_simulated_schema.py` (11), `tests/test_validate_frontend_contract.py` (90) on hand-built payloads | a payload produced by the real exporter, except inside the boundary runner |
| Payload summary | `tests/test_payload_summary.py` (5) | the row shape the exporter produces (finding 15) |
| Later joins | `tests/test_embed_scenario_joins.py` (6), `tests/test_export_traces_site.py` (4) | the collector's refill from the site payload; a non-root working directory |
| Pages | `tests/test_check_pages.py`, `tests/test_check_pages_browser.py` test the checker; the boundary runner asserts values on the index page | any value on a real page in CI; `scenario.html` has no test (map: searched test names and the boundary fixture) |
| Seal | `tests/test_tierb_split.py` (26), `tests/test_seal_check.py` (30) | the two lens exporters of findings 4 and 5; `tier_sensitivity.py` |
| interp-engine call sites | `tests/test_depth_probe.py` (26), `tests/test_model_pins.py` (27), with a fake `interp_engine` module | the real package at any version. The doubles pass regardless of what the package does |
| Petri lane | the harness-free suite: 1973 passed, 9 skipped (map, ran, 2026-11-10) | `tests/petri/` (two modules) skips without `inspect_petri` and runs in no CI job; nothing ran against the fork head |
| Forks' own suites | none run for this document | all of them: no interpreter here has torch, and no Inspect package is installed |
| Experiment interface and ICA adapter | `tests/test_experiments_*.py` on synthetic fixtures (not run for this document) | any real model, real activation capture or parity with `icalens` |
| This manifest | `tests/test_ecosystem_manifest.py`: schema, pin agreement with the pointer files, the status command on a synthetic git layout, the read-only guard | the remote mode against the network (a fake `ls-remote` is used); sibling checkouts, which CI does not have |
| Whole suite | local baseline at `d8d0855d`, 2026-11-10: 6506 passed, 4 failed, 20 skipped in 712 s (finding 2). First hosted run of `.github/workflows/pr_checks.yml`, 2026-11-11, engine `02ce6e8a`: standalone 7913 passed, 65 skipped; paired beside site `e13b7aa`: 7950 passed, 28 skipped | in both hosted jobs, 18 tests that need `icalens` and torch, `inspect_petri` or `inspect_ai` skip; a manual run of the workflow with a `site_ref` has not been made |

## 6. Findings

Ordered by consequence: seal and publication first, then statistics, provenance, runtime pins, documents. "This change set" is the work of 2026-11-10 on branch `claude/great-tesla-p33tvl`.

| # | Finding and evidence | Consequence | Proposed remedy | Verification | State |
|---|---|---|---|---|---|
| 1 | Site CI checks out the engine sparsely: `scripts`, `data`, `ops`, `docs` only (site `.github/workflows/site_checks.yml:105-109`), at the branch of the same name, else `main` | A checker that site CI runs cannot read `schemas/`, `tests/`, `medlang_circuits/` or `trace_out/`. A contract file placed under `schemas/` would be missing in site CI and the check would fail there while passing locally | Keep every file the two checkers read under `scripts/contracts/` or `data/`, as the results-catalogue schema is; or widen the sparse list in a site change | VERIFIED (doc, read). Site CI was not run here | Open constraint; respected by this change set |
| 2 | Four tests fail at the unmodified head on 2026-11-10, all in `tests/test_action_pilot.py`. Two return `action_plan_or_price_unavailable`: `data/action_annotations/price.v1.json` has `expires_utc: 2026-11-02` and `scripts/action_pilot_budget.py:29-33` compares it with today's date. Two fail on `git commit` exit 128 inside a temporary repository; this container sets `commit.gpgsign=true` with an ssh signing program | The quick path is red for reasons unrelated to a change. The first pair fails for everyone after the expiry date; the second pair depends on the machine's git configuration | Pass a fixed date into the tests that are not about expiry; create fixture commits with `-c commit.gpgsign=false` | VERIFIED (doc, read) for the expiry rule and the log; the baseline itself was run by the integrator; the signing cause was not reproduced separately | Open |
| 3 | The scenario exporter's holdout gate fails open: it uses `tierb_start_stamp` (`scripts/export_frontend_simulated.py:55`, `:336`), which returns `None` when `ops/dashboard.json` is missing or lacks `tierb.start_utc`; then nothing is withheld and no message is printed. `sealed_pair` (`scripts/tierb_split.py:238`) raises in that state and is not used here. `export_archive.py` and `urgency_shift.py` share the pattern (map, read) | On a wrong branch or a damaged dashboard, all holdout rows are written into the site working tree with `holdout_withheld: 0`. The backstop is `seal_check.py` exiting 2 at a later publish step, which is a procedure step and not CI | Move the three writers to `sealed_pair`, and add a test with a missing dashboard | VERIFIED (doc, read) for the exporter; (map, read) for the other two. The fail-open run is untested | Open |
| 4 | `scripts/export_jspace.py` has no seal check: it does not import `tierb_split`, reads `data/simulated/<stem>.json` directly (`:159`) and writes three full sentences into the site file (`:220-222`); `--stem` and `--index` are free arguments (`:203-207`) | A non-default invocation naming a sealed row publishes its text. The default pair is fixed, so this needs an operator to pass other arguments | Call `sealed_pair` before building, and add a seal test | VERIFIED (doc, read) | Open |
| 5 | `scripts/export_jlens_transport.py` applies the seal in `collect_pairs` (`:335`) but looks pinned exemplars up with `by_key.get` (`:473`) and builds them even when the pair was sealed out (`:474-476`) | A pin naming a sealed pair with committed raw output publishes that pair token by token | Refuse a pin that is absent from the sealed-filtered set | VERIFIED (doc, read). The combination is untested; whether a later gate catches it was not checked | Open |
| 6 | `scripts/tier_sensitivity.py` reads every row of the engine row file (`:157-158`) and contains no reference to `holdout`, `tierb_split` or `sealed` | An interim per-model aggregate pools the sealed split, against Amendment 1. That the committed `ops/tier_sensitivity.json` (2026-07-30) did so is inferred, not recounted | Filter with the stored `tierb_split` flag, and label or regenerate the committed file | VERIFIED (doc, ran `grep`) for the absence; CONCERN for the committed file's content | Open |
| 7 | A release could not be scoped: `publication_release.py --release` pinned every eligible part of every model | Admitting one new model also admitted backfill parts of the registered models, so registered numbers moved in the same step | `--models` on `--release` | VERIFIED (doc, read): `scripts/publication_release.py:91`; `tests/test_publication_hold.py:302` exercises it | Fixed in this change set |
| 8 | The statistics file's legacy block is described as a merged correction and is not one: `bh = {**bh_pre, **bh_post}` (`scripts/paired_stats_rigor.py:468-470`) places the two family-wise results side by side under `n_tests` of all models (`:482-485`). `docs/prereg_divergence_log.md:14` and site `technical/index.html:629` call it merged | Two public sentences describe a computation the file does not contain. A true ten-test correction differs in 8 of 10 values (map, ran). No page reads the block | Correct the two sentences, or compute the merged correction and say which is which | VERIFIED (doc, read) for code and prose; (map, ran) for the recomputation | Open |
| 9 | `paired_stats_rigor.py` is outside the publish chain: neither `.claude/skills/publish-site-data/SKILL.md` nor `docs/routine_standing_prompt.md` names it or `model_stats.json` | The chain can republish rows and the payload for a wider model set while `model_stats.json` stays at the earlier set, and `claim_check` keeps passing because the file it checks did not move | Decide the pending publish policy and add the step, or state on the page which model set the statistics cover | VERIFIED (doc, ran `grep` on both files) | Open |
| 10 | One bootstrap stream is shared across models in sorted order (`random.Random(seed)` once, `scripts/paired_stats_rigor.py:367`) | Adding a model that sorts earlier changes the intervals of unchanged models with unchanged data, and the file still says `seed: 7` (map, ran) | Derive one stream per model from the seed and the model id, and record the rule | VERIFIED (doc, read) for the code; (map, ran) for the effect | Open |
| 11 | AGENTS.md says every committed summary records `inference.environment` (`AGENTS.md:104`). 118 of 628 committed logits parts do not | A design that keys eligibility on that block silently treats 118 parts differently; the sentence is cited as a guarantee | Say "since `<date>`" in the sentence, and record the count in the reference | VERIFIED (doc, ran): counted over `trace_out/*/batch_summary*.json` | Open |
| 12 | Lens summaries record no instrument identity. The union of top-level keys over all 258 committed lens summaries is `mode, backend, graph_model, lens_type, top_n, start_index, endpoint, method_credit, results` plus `errors`, `partial`, `_partial`. The host changed its readouts on 2026-07-31 and 2026-08-14 (`scripts/export_jlens_depth.py:405-414`) | Summaries from three host states enter one census and no field separates them | Record the request date, base URL and response `meta` in every new summary; keep era labels in exports | VERIFIED (doc, ran) | Open |
| 13 | `data/jspace.json` contradicts its own note. The note says the pair was chosen because the final-layer readouts "carry the story at top-1" (`scripts/export_jspace.py:188-190`); the payload has `panels.clinical.on_target: false`. The engine and site copies are byte-identical | The methods page shows the clinical panel as off target beside a caption that says otherwise | Make the exporter check the selection criterion and refuse, then reselect or reword | VERIFIED (doc, ran). The cause (a re-measurement under a later host state) is inferred | Open |
| 14 | Two `digest` functions disagree on non-ASCII input: `scripts/exploratory_methods.py:39-42` uses `ensure_ascii=False`; `scripts/exploratory_baseline_preflight.py:36-38` leaves the default | The same value hashes differently depending on the module imported, for any prompt with a non-ASCII character | Name the two rules in every record that stores a digest; new code imports the first (the experiment package does) | VERIFIED (doc, read) | Open; documented in `docs/exploratory/case_report_mapping.md` |
| 15 | The exploratory report writer refuses protected directory names (`scripts/exploratory_methods.py:490-496`) but not a path inside the checkout. The baseline writer refuses any Git checkout (`scripts/exploratory_baseline_preflight.py:486-494`) | A report can be written to `<engine>/exploratory_methods/…`, where a later `git add` would pick it up | Add the checkout refusal to the older writer when its pinned hash can next change | VERIFIED (doc, read); the write was not attempted | Open for the older writer. The new run store refuses any checkout (`scripts/experiments/common.py:167-185`) |
| 16 | `payload.summary.penalty` is labelled phrase-deduped and is not: `phrase_key` reads `scenario["prompts"]["clinical"]` (`scripts/payload_summary.py:23`), and the exporter's rows carry `clinical_prompt` (`scripts/export_frontend_simulated.py:397`). Published: `n_phrases` 1163 = `n_scored_rows` 1163; no scenario has a `prompts` key | The home page prints the row count as "distinct phrases". Separately, the payload lists four models while the exporter's default list has seven, so a default republish would change `models_meta` (inferred; the exporter was not run) | Read `clinical_prompt`; add a test with the exporter's row shape. Decide `--models` explicitly at the next republish | VERIFIED (doc, ran) for the counts; CONCERN for the republish outcome | Open |
| 17 | interp-engine: pinned 1.5.1 from PyPI (`constraints.txt:24`); fork source 1.14.3 (fork `pyproject.toml:3`). Between them, `generate_stream` changed its default temperature to a value read from the checkpoint's `generation_config.json` with no revision, and an eager load reads `AutoConfig` twice with no revision (map, read). All 13 landed interp-engine artifacts record version 1.5.1 and `inference.revision: null` | A version bump is a new instrument, not a refresh. After it, three Hub reads would ignore the model pin. The 13 artifacts cannot be tied to a checkpoint commit | Follow [upgrade_checklist.md](upgrade_checklist.md); record the wheel hash or commit beside the version | VERIFIED (doc, ran) for versions and the null revisions; (map, read) for the API differences | Open by design: recorded in the manifest |
| 18 | Petri: the lock holds inspect-ai 0.3.237 and inspect-scout 0.4.39; the fork head requires `>=0.3.276` and `>=0.5.3` (fork `pyproject.toml:11-12`). CI installs the harness with `--no-deps` (`petri_audit.yml:438`), so pip would not report the violation; `verify-lock` would refuse on the commit. Engine checks cite inspect-ai 0.3.237 internals, including one private import (`scripts/petri_audit/adapter.py:33`) | The lock cannot host the head. A harness upgrade also changes the `anthropic` SDK under the judge, in the same job | Evaluate a candidate lock as a new file in an isolated environment; see the checklist | VERIFIED (doc, read) for versions and the flag; (map, read) for the internals list | Open by design: recorded in the manifest |
| 19 | Raw Petri `.eval` logs are held only as CI artifacts with 90-day retention (`petri_audit.yml:730`). The first landed run dates from 2026-09-18 (map, read) | After expiry no candidate harness can be compared on a real landed log, and `mode: readapt` has no input. Expiry dates near 2026-12-17 are inferred from the manifests' dates | Download and store the raw logs under owner custody before the first expiry | VERIFIED (doc, read) for the retention; CONCERN for the dates | Open |
| 20 | `icalens` at the fork head: the Python constructor defaults to L2 preprocessing (`src/icalens/lens.py:76`) while the fit CLI defaults to `none` (`cli/fit_activations.py:27`) and requires CUDA (`:39-40`); a fit runs a fixed number of iterations and saves no convergence flag; a missing model revision is stored as the string `unknown`; the lens holds no tokenizer identity or tensor hashes (map, read) | A basis fitted through one entry point is not comparable with one fitted through the other; scores can be computed against activations from another tokenizer or precision with no check that can fail | The adapter requires an explicit preprocessing mode and a basis manifest that pins every file by sha256 and records the identity the artifact lacks | VERIFIED (doc, read) for the three cited lines; (map, read) for the rest. The adapter's refusals were read in its docstring and its tests were not run here | Open upstream; guarded in the adapter |
| 21 | `docs/interp_engine_assessment.md` says the fork's validator covers the study's primary models. At the recorded head only one registered model has a results directory there (map, read) | A reader following the citation finds no supporting file; the assessed commit is not in the shallow clone | Mark the section as describing commit `74716092`, and rewrite it when the pin moves | VERIFIED (map, read) | Open |
| 22 | Stamped `trace_url` links have no liveness check: neither `validate_frontend_contract.py` nor `check_pages.py` fetches them (map, ran `grep`). The published stamp carries `engine_sha: 6884692f0a15+dirty` | A failed build in the traces repository yields 404 links on the public site with no failing check | A scheduled link check on a sample of links, in the traces repository or the Routine | VERIFIED (doc, ran) for the stamp; (map, ran) for the absence | Open |
| 23 | Causalab: four commit identifiers in four dated engine records, a fifth at the remote tip, `causalab_commit: null`, and an unresolved Python licence | A document can cite the wrong commit as the version used. Copying Causalab Python code has no recorded licence grant | Resolve the licence first; record one execution commit when the owner authorizes the run | VERIFIED (doc, ran) for the null pin and the remote tip; (map, read) for the four records | Open |
| 24 | Site `index.html:738` hard-codes the chart's `aria-label`: "In 9 of 10 measured models … one model ties". The data has ten models and all ten have more downgrades than upgrades | A screen-reader user hears a count the chart contradicts; it is wrong again whenever the model count changes | Build the label from `summary.per_model_deduped` at render time | VERIFIED (doc, ran) | Open |
| 25 | Site `docs/agent_reference.md` inaccuracies: `:43-44` says `data/timeline.json` drives a simulated-scenarios strip, removed 2026-07-30 (`simulated-scenarios/index.html:462`); `:109` lists five files with no page consumer and omits `timeline.json`; `:81` calls `specialties.json` the specialty filter, which is gated off (`TWO_LEVEL_SPECIALTY=false`, `index.html:1236`) | A reviewer treats `timeline.json` as page-consumed and misjudges what a data change can break | Correct the three statements in the site repository | VERIFIED (doc, read) | Open |
| 26 | Restriction and membership shared one boolean in the old gate: a caller could not tell "sealed" from "outside the registered set" | Lifting the hold for display risked lifting a restriction with it | Decide sharing, membership, integrity and restriction separately | VERIFIED (doc, read): `scripts/results_policy.py` (`classify_part`, `row_restriction`) | Fixed in this change set |

Lower-priority items with a concrete path, all (map, read) and open: the scheduled backfill shares the logits lane's concurrency group without its queue guard; a shorter re-run can replace a longer landed part; `activation_patch.py` writes nothing until a whole chunk is done; a Neuronpedia feature-fetch failure lowers `clinical_mass` without a count; one second-judge re-grade is truncated and its directory is closed; Haiku 5.5 coverage is split across two judge spellings that analyses compare as strings; `cli adapt` records a lock digest without verifying the environment against it outside CI.

## 7. What this document does not establish

- No fork's test suite was run, no model was loaded and no provider was called.
- Statements about the traces, Causalab and verify repositories come from engine source and `git ls-remote`, not from their files.
- "Public" for the forks rests on their answering `git ls-remote` through this environment's proxy; that does not prove anonymous access.
- The tested pins are what the engine has executed. They say nothing about whether the newer fork sources would give the same numbers.
