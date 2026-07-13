# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Backend engine for a mechanistic-interpretability study of how language models shift
next-token predictions between colloquial patient phrasing and clinical terminology.
It generates stress-test sentence pairs with Claude, traces them as attribution graphs
through Neuronpedia's hosted circuit-tracer, measures next-token behavior, and exports
results to the public frontend repo (`patientwords`, expected as a sibling checkout at
`../patientwords`). The study measures language-model probabilities only — nothing here
generates or evaluates medical advice.

## Hard conventions (deliberate — do not "fix")

- **Medical vocabulary lives only in JSON data files, never in Python source.** Code uses
  abstract placeholders and loads terms from `data/` or `medlang_circuits/data/`. This
  includes analysis vocabularies (e.g. `data/urgency_tiers.draft.json`); scripts that need
  them load them as data.
- **Intentional misspellings in phrase datasets are stress-test stimuli** (e.g. `ihal` for
  inhaler in `data/measured/imported_pairs.json`). Never correct them.
- Generated batches are append-only archives under `data/simulated/` with a
  `<batch>.report.json` cost sidecar. Never rewrite a landed batch.

## Commands

```bash
pip install -e ".[llm]"                 # dev install (poetry-core backend; [llm] adds anthropic)
python -m pytest                        # full suite (fast, offline; must stay green)
python -m pytest tests/test_graph_client.py -k retries   # single file / test
ruff check .                            # lint (line-length 120)
```

Console entry points (see `[tool.poetry.scripts]`): `medlang-compare`, `medlang-batch-eval`,
`medlang-evaluate`, `medlang-generate`.

## Execution model: nothing paid or networked runs locally

API keys (`ANTHROPIC_API_KEY`, `NEURONPEDIA_API_KEY`, optional `HF_TOKEN`) exist **only as
GitHub Actions secrets** — dev containers have none, and the sandbox egress proxy blocks
huggingface.co and most model hosts. All generation, tracing, and CPU inference therefore
runs through **push-to-run CI**: each workflow fires when its file under `.github/trigger/`
changes on any pushed branch.

| Trigger file | Workflow | What it does |
|---|---|---|
| `circuit-trace.json` | `circuit_trace_evaluation.yml` | hosted attribution graphs (matrix: `graph_models` × `offsets`) |
| `logits-eval.json` | `logits_evaluation.yml` | CPU next-token measurement for models Neuronpedia can't trace |
| `scenario-generation.json` | `scenario_generation.yml` | Claude-authored pair batches (paid; `max_spend` ceiling) |
| `model-evaluation.json` | `model_evaluation.yml` | Claude concept-extraction eval before/after translation (paid) |
| `archive-renders.json` | `archive_renders.yml` | zips run renders to a GitHub Release |
| `activation-patching.json` | `activation_patching.yml` | CPU residual-stream patching grid ($0) |
| `jlens-readout.json` | `jlens_readout.yml` | hosted Jacobian-lens depth readouts ($0) |

**Queue discipline (the sharpest tool in the repo):** every workflow has a per-branch
concurrency group with `cancel-in-progress: false`, which means **one running + one
pending run**. Pushing a third trigger change *evicts the pending run silently*. Never
stack two pending runs in the same group; chain fires instead.

**Merge/copy danger:** any push that changes a trigger file fires its workflow — including
merges to `main`. When merging branches, keep the target branch's trigger files unchanged
(restore them before committing the merge) or you will re-fire runs and double-spend.

**Cost discipline:** Neuronpedia tracing, Qwen logits, and all analysis are $0. Only
`medlang-generate`, `medlang-evaluate`, and 2panel's `--show-mitigation` translation
panel spend Anthropic credits (~$0.015/pair on opus, ~$0.002 on haiku; mitigation
fires are budget-guarded via an imputed commitment in `fire_trigger.py`); every paid
run writes a `.report.json` (or `.mitigation.report.json`) sidecar with its cost. Session
ledgers live in `docs/` when an overnight run is active.

**Ops tooling (required path):** fire triggers ONLY via `scripts/fire_trigger.py` — it
journals every fire (`ops/trigger_journal.jsonl`), mechanically enforces the
one-running + one-pending discipline, hard-errors on unknown trigger keys (CI silently
ignores them), and refuses paid fires that would breach the $2/day operational ceiling
counting landed **and in-flight** `max_spend`. `scripts/ledger_update.py` is the only
writer of spend numbers (`ops/dashboard.json` + the ledger); `scripts/daily_brief.py`
renders the 3-section brief and the push digest. `ops/dashboard.json` has one writer —
the daily Routine session (`ops/README.md`, `docs/routine_standing_prompt.md`). Both
repos are public: never write secrets anywhere.

## Architecture

**Tracing (`graph_client.py` → `batch_eval.py`).** `MODEL_REGISTRY` lists four Neuronpedia
model ids, but **only `gemma-2-2b` actually produces hosted graphs** (verified 2026-07-07;
the others 400/500 server-side — see `docs/cross-model.md`). Hosted requests retry on
{429,500,502,503,504} with fresh slugs; a 400 aborts the batch immediately, and `run_batch`
has no per-pair error records — a mid-batch failure just truncates `results`.
`medlang-batch-eval` has four modes (`2panel`, `4quadrant`, `dialect`, `translation`) with
different result schemas; `2panel` supports `--screen-targets` (clinical side traced first;
unmeasurable pairs recorded as `screening.screened_out`, patient trace skipped) and
`--show-mitigation` (third, LLM-translated panel — the only Anthropic call in 2panel).

**Feature tagging.** Only gemma-2-2b has a transcoder source set
(`neuronpedia_features.MODEL_SOURCE_SETS`); other models auto-degrade to `NullFetcher`:
tracing and probabilities still work, but every feature is untagged, so their
`clinical_mass` comes out ~0.0 — an artifact, not a finding. Anything consuming
per-model results must null clinical-mass for models whose `source_set` is null
(the frontend exporter does this via its `FEATURED` set).

**Behavior without graphs (`scripts/logits_eval.py`).** Models Neuronpedia can't trace are
measured by direct CPU inference in CI, emitting **the same `batch_summary` schema** so
everything downstream merges unchanged (`backend: "logits"`, `source_set: null`, plus a
`continuations` map from greedy multi-token decoding that disambiguates wordpiece tops).

**Output layout & checkpointing.** Each run writes `trace_out/<pairs-stem>/`; non-default
models get `trace_out/<stem>__<model>/`. CI renames each chunk's summary to
`batch_summary.part_NN.json` (NN = 1-based start offset) so chunks never clobber — all
consumers must glob `batch_summary*.json`, and `results[i]["index"]` is the global 1-based
join key back into the batch file. Generation archives commit to **main**; trace outputs
commit to **the dispatched branch** — expect the two to interleave, and `git pull --rebase`
before pushing.

**Analysis chain.** `scripts/urgency_shift.py` is the collector (reads site payload +
every `trace_out/*/batch_summary.part_*`, scores care-urgency tiers from the reviewed
vocabulary data file, classifies flips downgrade/upgrade/lateral, handles the translated
third panel as `urgency_recovery`, `--publish` writes the site's `data/urgency_shift.json`);
`scripts/paired_stats.py` consumes its row file (unified same-phrase set across models,
bootstrap CIs, hand-measured validity correlation). `scripts/export_archive.py` writes the
flat per-(pair × model) collaborator CSV.

**Publishing (`scripts/export_frontend_simulated.py`).** Merges every model's trace dir per
batch stamp into `scenario.models[<id>]`, mirrors the gemma base to the top level for
backward compatibility, emits `models_meta` (the frontend model-selector's source of
truth), and caps public interactive renders at the 25 most consequential (`--max-renders`;
flips first, then |language penalty|). Full render sets go to GitHub Releases via
`scripts/archive_run.py` + the archive workflow (`docs/archiving.md`); pass the Release URL
back with `--archive-url`.

## Figure style (standing preference)

Figures follow Tufte: simple and readable, maximum data-ink. Concretely for the renderer
(`compare_viz.py`) and any new figure code: no decorative chrome, hairline structure only,
direct labels on the data instead of legends where possible, muted structural elements so
the clinical/off-target contrast carries the story, serif/mono typography per the site
palette, and every mark must survive gallery-thumbnail scale. When in doubt, remove ink.

## Tests

Offline and fast (`tests/`, `conftest.py` provides fixtures; no network, no keys). Every
bug fix gets a regression test. CI-side behavior (workflow YAML, hosted API quirks) can't
be tested here — validate YAML with `yaml.safe_load` and verify wiring by reading the
params heredoc, which has its own pitfalls (push-path `defaults` dict must contain every
trigger key; JSON lists must be normalized to CSV before `str()`).
