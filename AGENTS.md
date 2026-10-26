# AGENTS.md

Canonical repository instructions for Codex and the root `CLAUDE.md` import.
Read applicable ancestor and nested `AGENTS.md` / `AGENTS.override.md` instructions
(including case variants present in the checkout) before editing. An override may
replace this file; it must still route agents to [verify.md](verify.md).

## Start here

This is the Python research engine for PatientWords: it generates paired stimuli,
measures next-token behavior and assistant responses, analyzes the results, and
exports artifacts to the public frontend, normally `../patientwords`. These are
measurements of language-model behavior, not medical advice or a clinical tool.
The frontend renders exported JSON and HTML; it does not call a live engine API.

- [verify.md](verify.md) is the canonical setup and verification guide. Read the
  relevant change-type and boundary sections when planning and again before completion.
- [docs/agent_reference.md](docs/agent_reference.md) contains binding project decisions
  moved out of this entry point. Read its architecture and research-limitations
  sections for engine/data changes, its operational sections before any run or push,
  and its PR/review sections before commits, PRs or reviews.
- [README.md](README.md) introduces the package and CLI; [docs/README.md](docs/README.md)
  indexes designs, preregistrations and decision records. Dated reports are historical
  evidence, not proof that today's checkout passes.
- `medlang_circuits/`: `cli.py` and `pipeline.py` (comparison), `graph_client.py`
  (hosted graph contract), `batch_eval.py` (batch summaries), `scenario_gen.py`
  (stimulus generation). Console commands are defined in `pyproject.toml`.
- [docs/exploratory/frontend_boundary.md](docs/exploratory/frontend_boundary.md)
  documents the existing synthetic exporter-to-HTTP-to-browser slice. Its structural
  authority is `scripts/contracts/simulated_scenarios.v1.schema.json`; OpenAPI
  describes the same static GET resource. Read it for contract/client/index changes.
- `scripts/` supplies analysis/export/operations tools; [scripts/README.md](scripts/README.md)
  records each tool's status, writer and consumers. `tests/` and `.github/workflows/`
  define executable checks and measurement jobs respectively.
- Source data: `data/`, packaged vocabulary in `medlang_circuits/data/`, immutable
  measured summaries in `trace_out/`. `pilot/` holds separately labeled pilot records.

## Working procedure

1. Inspect branch/status and applicable instructions; preserve unrelated and concurrent edits.
2. Define observable success and read the relevant sections of `verify.md` and the
   mandatory reference above. Identify consumers and whether the companion checkout is needed.
3. Make one focused change. Preserve established decisions; justify corrections with code/configuration evidence.
4. Run the quick path and the additional checks selected by change type. Every bug fix
   gets a regression test. Record actual passes, failures, skips and blocked checks;
   investigate baselines before attributing failures to the change.
5. Re-read applicable instructions and verification requirements, inspect the final
   diff and run `git diff --check`. Report exact commands, outcomes, counterpart
   revisions/artifacts and limits. Keep session output in the completion report.

## Research and compatibility invariants

- Medical vocabulary belongs in JSON data, never Python. Preserve intentional stimulus
  misspellings. Generated `data/simulated/` batches and their `.report.json` cost
  sidecars are append-only; landed `trace_out/` summaries are measurements, not caches.
- Hosted and logits producers share `batch_summary*.json`. A result's `index` is
  the global 1-based source-pair index; the exported join is `(batch, batch_index, model)`.
  Exported display `index` also supports public `?sim=` links: preserve batch ordering.
  `verify_summary*.json` intentionally stays outside measurement collectors.
- Preserve base-model compatibility mirrors, `models_meta`, null/missing-data meaning,
  holdout seals, publication-release hashes, source-set calibration and sampling labels.
  Do not hand-edit generated payloads or release held data to make a check pass.
- Record random seeds in statistical outputs; document methods, transforms and assumptions.
  Record absent/unreadable data explicitly; never silently turn it into zero or drop rows.
- The engine computes; the frontend presents. Public explanations must retain provenance,
  simulated/pilot/exploratory labels and domain-review status. Research-output changes
  require the paired contract/claim/seal checks and communication review in `verify.md`.
- Pilot traces/logits remain under `pilot/traces/` and `pilot/logits/`, never study collectors.
  Changes to `pilot/scripts/` require recomputing and re-finalizing every recorded run
  on the manifest's side of Python 3.12; see [docs/pilot_runs.md](docs/pilot_runs.md).
- `.claude/settings.json`, `.claude/hooks/` and `.githooks/` are owner-only. Preserve
  the operational single-writer, queue and cost rules in the reference. Both repos
  are public: never write secrets. Add type hints to new modules/public functions.
- For model defaults, judging, equity/Petri or Jev changes, read
  [docs/decisions_20261014_owner.md](docs/decisions_20261014_owner.md): preserve the
  separate judges, historical-instrument safeguards and scope of execution approvals.

## Execution model: nothing paid or networked runs locally

API keys exist **only as GitHub Actions secrets**, and the repository holds exactly five
(`gh secret list`, 2026-09-23): `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`,
`NEURONPEDIA_API_KEY` and optional `HF_TOKEN`. The models the study traces and measures are
reached through Neuronpedia (`NEURONPEDIA_API_KEY`) or loaded from Hugging Face for CPU
inference (`HF_TOKEN`). Every non-Anthropic model called through a chat API (the advice and
Petri lanes) goes through OpenRouter on `OPENROUTER_API_KEY`
(routing: `data/advice_providers.json`), except the
registry's direct `google:` entry, which uses `GEMINI_API_KEY`. There is no `OPENAI_API_KEY`,
`XAI_API_KEY`, `DEEPSEEK_API_KEY` or `MOONSHOT_API_KEY`: the workflows' references to them
resolve to empty strings. A Petri target in `mode: run` or `mode: readapt` must be
`anthropic/<model>` or `openrouter/<vendor>/<model>`; `mockllm/model`, the lane's park
default, calls nothing and is refused in both (`docs/triggers.md` has the full rule).
Dev containers have
none of these keys, and the sandbox egress proxy blocks huggingface.co and most model
hosts. Generation, tracing and CPU inference use **push-to-run CI**: a push changing
`.github/trigger/` fires its workflow. Owner exception (PR #121): prepare the
one-case manual route in `docs/exploratory/baseline_ci.md`; execution needs
separate owner approval. A machine that *can* run inference locally (yours, with a
GPU) still commits no locally produced measurement: every committed summary records
`inference.environment`, and only CI-produced summaries are measurements.

The secret inventory above is a dated project record, not a fresh account audit.
No credentials or model services are required for the offline verification path.
The pilot exception and exact execution/queue/spend rules remain in the mandatory
[agent reference](docs/agent_reference.md#execution-and-operations).

| Trigger file | Workflow | What it does |
|---|---|---|
| `circuit-trace.json` | `circuit_trace_evaluation.yml` | hosted attribution graphs |
| `logits-eval.json` | `logits_evaluation.yml` | CPU next-token measurement for models Neuronpedia can't trace |
| `scenario-generation.json` | `scenario_generation.yml` | Claude-authored pair batches (paid; `max_spend` ceiling) |
| `model-evaluation.json` | `model_evaluation.yml` | Claude concept-extraction eval before/after translation (paid) |
| `archive-renders.json` | `archive_renders.yml` | zips run renders to a GitHub Release |
| `activation-patching.json` | `activation_patching.yml` | CPU residual-stream patching grid ($0) |
| `jlens-readout.json` | `jlens_readout.yml` | hosted Jacobian-lens depth readouts ($0) |
| `advice-eval.json` | `advice_evaluation.yml` | deployed-assistant advice elicitation + judging (paid) |
| `petri-audit.json` | `petri_audit.yml` | Petri-hosted multi-turn register experiments (paid modes: *Cost discipline*; `rejudge` re-grades landed runs with another judge into `data/petri/rejudge/`) |
| `jev-audit.json` | `jev_pilot.yml` | Jev decisions classifier scored against landed advice and Petri outputs (paid when `live: true`, on OpenRouter) |
| `action-annotate.json` | `action_annotation.yml` | One fixed assisted action-label pass; paid only in run mode, $1 reservation |

11 lanes. `scripts/fire_trigger.py` is the source of truth; read
[docs/triggers.md](docs/triggers.md) and the reference before changing any workflow
or trigger. Paid Petri `mode: rejudge` writes `data/petri/rejudge/`. Fire only through
`scripts/fire_trigger.py`; never hand-edit trigger files or fire jobs merely to test docs.
Live Jev audits write cost records under `data/jev/runs/`; `live: true` is paid.
The generated site file `data/urgency_shift.json` belongs to the companion repository.

## Figure style

Follow the [figure-style decision](docs/agent_reference.md#figure-style-standing-preference):
Tufte, minimal structure, direct labels, readable at thumbnail size.

## Dual-AI PR Review Architecture

- **Codex** audits hunk-level diff logic, local edge cases and isolated code correctness.
- **Gemini CLI ([GEMINI.md](GEMINI.md))** audits whole-repo blast radius, untouched
  downstream callers, data provenance and `patientwords-engine` ↔ `patientwords`
  contract sync. It reports only cross-file findings with both changed and untouched
  evidence; it never duplicates Codex's local syntax, type or isolated logic checks.

## Code Review Rules

Codex applies these requirements during each review:

* Flag changes that could corrupt, silently alter, or irreversibly delete stored data.
* Flag backward-incompatible API, database, configuration, or schema changes that lack a documented migration or compatibility path.
* For authentication and authorization changes, verify every relevant entry point—not only the primary request path.
* Prioritize concrete correctness, security, data-loss, and regression risks over stylistic preferences.
* Confirm that behavior-changing code has appropriate tests, or identify the specific untested behavior and resulting risk.
* Do not report formatting or lint issues that should be handled deterministically by CI.
* Include the affected scenario and evidence when reporting a finding; do not report speculative issues without a plausible failure path.

### Repository-specific review requirements

Read [docs/agent_reference.md](docs/agent_reference.md#repository-specific-review-requirements)
for the data, pilot, spend, schema, single-writer, site-CI and traces-site rules.
Read its PR workflow and response rules before opening or responding to a review.
Agents do not merge; the owner merges. This task's request determines whether to
leave a local diff or create a PR.

## Known measurement limitations

Read the [research limitations](docs/agent_reference.md#known-measurement-limitations)
before changing measurement paths or quoting results. Historical audits constrain
claims; they do not establish a new run's accuracy. The evidence-linked paragraph
below remains here because `tests/test_target_reads_evidence.py` checks it directly.

* **The hosted path read some targets off another token.** Until 2026-10-07 its
  case-blind prefix match kept the likeliest logit related to the target in
  either direction: `" ant"` read as `" anti"` (index 20 of
  `pairs_20260710T011743Z`: 0.068 recorded, 0.041 correct) and `" antibiotic"`
  as its first part `" anti"`. `scripts/audit_target_reads.py` (2026-10-07,
  last part per index; rows in `data/audits/target_reads_20261007.json`): 63
  hosted results carry another token's value, 40 in a published field; 23
  measured a leading piece of a word the vocabulary holds whole (16
  published). Of 262 published substituted rows, 251 are the unscreened
  top-logit fallback, 8 the prefix match itself (6 extensions, 2 case
  variants; 4 screened) and 3 the logits lane's bare-space first token;
  `anchor_fallback` misses 9. Pilot traces are clean. New traces read exactly
  and record `target_read`. Re-measuring and republishing is the owner's
  decision.
* **Other limitations and publication decisions.** The reference preserves the bfloat16
  agreement audit, negative-control evidence and prohibition on silently remeasuring
  or republishing historical values. Do not base a study claim on one pair's penalty
  or flip label.
