# Verification

Use this guide from the **patientwords-engine repository root** unless a command
says otherwise. Read [AGENTS.md](AGENTS.md), applicable nested/override instructions,
and the relevant sections here when planning and before declaring completion.
[docs/agent_reference.md](docs/agent_reference.md) preserves operational and research
rules; [docs/README.md](docs/README.md) indexes deeper sources. The separate
`docs/verification_protocol.md` is a physician-rating research protocol, not this
software-verification guide.

## Setup and sources of truth

`pyproject.toml` uses Poetry's build backend and supports Python `>=3.10,<4`.
Use Python 3.12 or later for normal development so recorded pilots sealed on that
side of 3.12 can re-finalize (float summation changed in 3.12; see
[docs/pilot_runs.md](docs/pilot_runs.md#the-python-312-line)). The main measurement
workflows use Python 3.11; the Petri lane pins 3.12.3; the Jev pilot uses 3.12.
These are distinct execution environments.

There is no general Poetry/uv/pip lockfile in this checkout. The dev ranges below
match `pyproject.toml`; installation resolves versions within those ranges, rather
than reproducing an exact environment. `constraints.txt` pins the measurement CI
stack, while `docs/framework/petri_environment.lock.json` governs the Petri lane.
The synthetic browser boundary has its own Python 3.13 environment and
`scripts/boundary_client/requirements.lock`; keep it separate from the dev ranges.
Do not silently change those pins to repair a local developer install.

```bash
(
set -euo pipefail
# From patientwords-engine; reuse a suitable existing .venv instead of replacing it.
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[llm]' 'pytest>=9.1,<9.2' 'ruff>=0.16,<0.17' 'pyyaml>=6,<7'
python --version
python -m pip show pytest ruff PyYAML requests matplotlib networkx anthropic
)
```

The setup block's activation ends with its subshell. Before the quick path or any
other developer command below, activate the chosen environment in your current
shell (repeat in each new shell; substitute its path if reusing another venv):

```bash
. .venv/bin/activate
```

Installation requires package-index access unless dependencies are already cached.
The `llm` extra installs Anthropic's client for imports/tests; it does not authorize
API calls. README usage examples demonstrate CLI capabilities and do not override
the CI-only measurement policy. `matplotlib` and `networkx` are base dependencies. Pip does not install
Poetry's dev group automatically. Optional spreadsheet imports need `.[sheets]`;
unit testing does not need the GPU/CPU model stack.

Before editing, record `git status --short`, `git branch --show-current` and
`git rev-parse HEAD`. Record the same for the frontend if paired checks use it.
Do not reset unrelated changes. Old test reports and the existence of a populated
`.pytest_cache/` are not a current baseline.

## Environment, fixtures and services

| Need | Source or setting | Scope |
|---|---|---|
| Offline unit tests | `tests/conftest.py` synthetic graphs and abstract keyword config; `tests/fixtures/`; committed `data/`, `trace_out/`, `pilot/` records | No API keys or model service |
| Companion site | Normally `../patientwords`; set `PW_SITE_ROOT` to an absolute path for the shared-conventions and specialty-coverage tests | A missing default sibling skips those checks visibly; an invalid explicit path fails |
| Developer browser checks | `python -m pip install playwright`, then `python -m playwright install chromium` | Installation needs network; execution serves local HTTP; Linux may additionally need Playwright's OS dependencies |
| Browser executable override | `python scripts/check_pages.py --site "$PW_SITE_ROOT" --browser /absolute/path/to/chromium` | Use an installed compatible Chromium when Playwright's managed browser is absent |
| Unit browser regression server | Port 8933 in `tests/test_check_pages_browser.py` | Playwright/Chromium absence skips browser cases; a skip is not exercised rendering |
| Local archive fixtures | Ephemeral loopback ports in `tests/test_render_archive.py` | Offline tests still need permission to bind localhost; no external service |
| Whole-site browser server | `check_pages.py --port 8901` (change to a free port if needed) | Script starts and terminates its own local server |
| Vocabulary override | Optional `MEDLANG_KEYWORD_CONFIG`; packaged default `medlang_circuits/data/keyword_config_default.json` | Keep vocabulary in JSON; no override needed for tests |
| Provider execution | `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `NEURONPEDIA_API_KEY`; optional `HF_TOKEN` | GitHub Actions secrets under the execution policy, not local test prerequisites |
| Legacy local graph backend | `GRAPH_SERVER_URL`, `GRAPH_SERVER_SECRET` and a Neuronpedia graph server | CLI capability, not a required local verification service; measurements follow the project's CI-only policy |

Optional model selectors include `MEDLANG_ANTHROPIC_MODEL`, `MEDLANG_GRAPH_MODEL`
and `NEURONPEDIA_BASE_URL`; see README for their CLI scope. Do not copy secrets into
commands, repository files or reports. No database or live PatientWords API is needed.

## Quick path

After setup, from the engine root:

```bash
(
set -euo pipefail
python -m pytest -q -ra \
  tests/test_agents_md_budget.py tests/test_agents_secrets.py \
  tests/test_trigger_docs.py tests/test_target_reads_evidence.py \
  tests/test_doc_paths.py tests/test_scripts_readme.py tests/test_shared_conventions.py
python -m ruff check .
git diff --check
)
```

This checks instruction size, evidence/secret/lane references, documented paths,
script inventory and shared instructions, then lint and whitespace. The shared
cross-repository checks require the frontend; `-ra` makes skip reasons visible.
It does **not** test all engine behavior, generate measurements, validate every
Markdown link, or render the site. Manually check new Markdown links and commands.
`test_doc_paths.py` covers the fixed operations list and both repositories'
`verify.md` and `docs/agent_reference.md`, including local Markdown file links and
explicit companion references. It does not validate heading anchors or external URLs.

## Choose additional checks

The quick path is the documentation baseline. Preserve the full-suite/lint gates
for code changes and add the checks below according to the affected behavior.

| Change type | Focused checks from engine root | Additional evidence required |
|---|---|---|
| Instructions / documentation only | Quick path; exact sections parsed by tests must remain compatible | Verify links, command help/source and cross-repo shared rules; no model job |
| Graph client / targets / batch logic | `python -m pytest -q -ra tests/test_graph_client.py tests/test_targets_and_batch.py tests/test_target_exact_read.py tests/test_target_keep_node_metrics.py` | Full suite + lint; hosted behavior still needs approved CI evidence |
| Generation / phrase handling | `python -m pytest -q -ra tests/test_scenario_gen.py tests/test_patient_lexicon.py tests/test_translate_and_keywords.py` | Full suite + lint; preserve stimuli and append-only archives |
| Exported schemas, collectors or model metadata | `python -m pytest -q -ra tests/test_export_frontend_defaults.py tests/test_validate_frontend_contract.py tests/test_simulated_schema.py tests/test_embed_scenario_joins.py tests/test_payload_summary.py tests/test_publication_hold.py tests/test_render_prune.py` | Full suite + paired contract/claim/seal gates; temporary export and consumer rendering when output changes |
| Frontend behavior or the engine checks used by site CI | `python -m pytest -q -ra tests/test_check_pages.py tests/test_check_pages_browser.py tests/test_validate_frontend_contract.py` | Companion's `verify.md`, paired structural gate, actual browser checks and relevant manual interaction |
| Workflow/configuration/dependencies | `python -m pytest -q -ra tests/test_trigger_docs.py tests/test_workflow_created_guard.py tests/test_model_pins.py tests/test_agents_secrets.py` plus affected lane tests | Full suite + lint; read push-path parameter handling; local tests do not dispatch or reproduce hosted jobs |
| Pilot scripts / recorded pilot artifacts | `python -m pytest -q -ra tests/test_pilot_recorded_runs.py tests/test_pilot_selftest.py` plus affected pilot tests | Recompute/re-finalize every recorded run under the compatible interpreter, compare summaries, and seal-check as `docs/pilot_runs.md` requires |
| Research analysis or public research claims | Tests for affected analysis plus `tests/test_claim_check.py`, `tests/test_seal_check.py`, `tests/test_provenance_stamp.py` | Record seed/method/source artifacts; paired publication gates; update claims and decision/disclosure documents with the proper owner review |

The file groups are starting points: inspect call sites and consumers to select
additional affected tests. A module-only pass is not a substitute for the full
suite when changing executable behavior.

## Broader local gates and CI limits

```bash
(
set -euo pipefail
python -m pytest -q -ra
python -m ruff check .
git diff --check
)
```

No provider calls are required by these tests. The full suite includes temporary
Git repositories, subprocesses, artifact integrity checks and pilot finalization;
it can take several minutes. Browser cases can skip when dependencies are absent;
record every skip and interpreter-dependent pilot skip. Tests must remain green;
if a failure exists before the change, report it and its evidence rather than
weakening an assertion or assuming a historical green run applies.

Run the suite in a writable checkout: the recorded-blob test briefly writes
`docs/framework/_blob_probe.tmp.json` and removes it afterward. A read-only checkout
or sandbox that denies loopback sockets prevents those checks from completing.
Use an authorized writable/local-server environment and report the initial blocker;
do not remove assertions or confuse local fixture HTTP with a live provider call.

This checkout's `.github/workflows/` runs measurement, generation, archive,
operational lanes and the separately approved exploratory preflight, not a generic
pytest/ruff pull-request workflow. The commands
above are the local regression gates; do not claim they reproduced all CI jobs.
The frontend's `site_checks.yml` independently runs this engine's contract and
browser scripts against the site, selecting engine `main` or a matching branch.
Record the actual engine revision when reproducing that boundary locally.

Live generation/tracing/inference needs external services, credentials and sometimes
large model downloads/compute. The existing policy routes it through
`scripts/fire_trigger.py`; read [docs/triggers.md](docs/triggers.md) and
[docs/operators_handbook.md](docs/operators_handbook.md) first. Never edit a trigger
or launch a paid job as an ordinary docs/test check. The pilot subscription exception
is limited to the documented, separately labeled generation pilot. The newer owner
exception permits preparing the one-case route in
[docs/exploratory/baseline_ci.md](docs/exploratory/baseline_ci.md); execution still
needs separate owner approval. Neither exception authorizes a verification run here.

## Artifact boundary

The public `patientwords` frontend consumes exported static JSON and generated HTML,
not a live engine API. The third `patientwords-traces` repository serves long-tail
render links; external trace availability is separate from local frontend loading.

1. Producers archive generated pairs and cost/provenance sidecars under
   `data/simulated/pairs_<STAMP>.json` and `.report.json`. Hosted tracing and CPU logits
   write the shared `trace_out/<batch>[__<model>]/batch_summary*.json` schema.
   Verification output deliberately uses `verify_summary*.json`.
2. `scripts/export_frontend_simulated.py` merges those summaries into the frontend's
   `data/simulated_scenarios.json`, copies capped HTML renders and prunes unreferenced
   matching renders. The base `gemma-2-2b` fields mirror `scenario.models[base]` for
   compatibility. `models_meta` controls available model choices.
3. Preserve the complete ordered stamp list, steering disclosure, source model/source
   set, report provenance, holdout counts, release hashes and archive link. The exporter
   withholds sealed rows and held/unreleased results; clinical mass is published only
   for calibrated model/source-set combinations. Missing measurements remain explicit.
4. The scenario-index flow uses exported global `scenario.index` for display and public
   `scenario.html?sim=N` links. Stable data joins use `(batch, batch_index, model)`;
   `batch_index` is the source summary's 1-based `index`. Reordering/removing batches
   can alter public links. There is no separate scenario-index build artifact here.
5. After relevant collectors/exporters, `scripts/embed_scenario_joins.py` embeds
   urgency/depth joins and featured editorial choices. The exporter rebuilds the payload
   and removes these additions, so joins must be restored after every export. Inspect
   the printed join counts: zero is not an automatic failure in the script. The contract
   validator permits these fields to be absent and cannot alone prove enrichment ran.
6. The frontend fetches the payload over HTTP, indexes/selects the requested scenario,
   renders model-dependent probabilities and labels, and links or embeds the available
   circuit render. Exercise this with the companion's own guide and manual checks for
   scenario links, switching models, data-only rows, disclosures and missing-data states.

The structural authority is
[scripts/contracts/simulated_scenarios.v1.schema.json](scripts/contracts/simulated_scenarios.v1.schema.json).
The [OpenAPI description](scripts/contracts/simulated_scenarios.openapi.json)
describes the existing static GET resource, not a live API. Semantic checks (joins,
calibration and base mirrors) remain in `scripts/validate_frontend_contract.py`.

The source of the complete publication chain is
[the existing publish-site-data skill](.claude/skills/publish-site-data/SKILL.md).
It includes specialized lens/translation exports, trace URL restamping and publication
rules. A documentation check does not require invoking that publishing workflow.

### Research explanations and records

When research outputs change, identify the companion pages and captions that use
them, including `methods.html` and `technical/index.html`; check labels for generated
stimuli, measured traces, pilot/exploratory findings, missing data and domain-review
status against the source artifacts. Update `data/claims_manifest.json` when its
registered quantities or prose snippets change. Preserve seeds, source/run hashes
and generation/cost sidecars so the public explanation remains traceable.

Review the applicable preregistration, amendment/deviation record, disclosure log
and vendor reproduction pack when methods or published findings change. Follow
the existing publication workflow's owner/orchestrator review requirement for new
page wording; a data-only publishing cycle does not authorize changing research
claims. The engine's `scripts/extract_site_text.py` can refresh its working prose
outline, but does not extract text generated by page JavaScript. Record paired
documentation follow-up explicitly when the consumer repository is unavailable.

## Paired gates on existing artifacts

Point to the actual frontend checkout; the default below is the normal sibling:

```bash
(
set -euo pipefail
PW_SITE_ROOT=$(cd ../patientwords && pwd)
export PW_SITE_ROOT
git rev-parse HEAD
git -C "$PW_SITE_ROOT" rev-parse HEAD
git status --short
git -C "$PW_SITE_ROOT" status --short
python -m pytest -q -ra tests/test_shared_conventions.py tests/test_specialty_map.py
python scripts/validate_frontend_contract.py --site "$PW_SITE_ROOT" --engine .
python scripts/claim_check.py --site "$PW_SITE_ROOT"
python scripts/seal_check.py --site "$PW_SITE_ROOT"
python scripts/check_pages.py --site "$PW_SITE_ROOT" --port 8901
)
```

- The structural validator checks required fields/types, compatibility mirrors,
  joins, render paths and cross-repo copies. Exit 0 is clean, 1 is violations and
  2 is missing/unreadable payload. The command above matches current frontend CI
  report mode: warnings do not fail it and must still be reported. The publication
  chain requires `--strict` once urgency regeneration has written `unjoinable_rows`;
  the temporary regeneration below uses that stronger gate. `--strict` makes every
  warning fail; do not remove it from a publication check to hide drift.
- `claim_check.py` compares public prose against `data/claims_manifest.json` and
  data expressions. Exit 1 means failed claims. **Warnings can exit 0**: a missing
  snippet still needs investigation/manifest coordination, not a clean report.
- `seal_check.py` must return 0; 1 means a disclosure hit, 2 means configuration or
  incomplete-checkout failure. Neither is a pass; never weaken the seal to publish.
- `check_pages.py` catches JavaScript/console errors, failed payload requests and
  empty visible tables. Hidden optional sections and legitimate pending cells can
  pass. Schema drift can degrade gracefully and evade this browser check, so run
  the structural gate first. It checks published pages, not every generated render
  or interaction; perform the scenario/model/manual checks above.

These checks exercise committed/current artifacts with a real consumer. They do not
prove the current exporter regenerated them, nor call a live model. Fixture-based
engine tests establish compatibility/refusal behavior on synthetic inputs; label
that evidence separately from this paired run and from the regeneration below.

## Synthetic exporter-to-browser boundary

For schema/exporter changes or changes to the scenario index consumer, use the
existing [boundary procedure](docs/exploratory/frontend_boundary.md) and its
independently specified `tests/fixtures/frontend_boundary.json`. From the engine
root, after installing that procedure's separate locked Python 3.13 environment:

```bash
(
set -euo pipefail
# Example venv location from the boundary procedure; use the environment you installed.
PW_BOUNDARY_PY=/tmp/pw-boundary-venv/bin/python
PW_SITE_ROOT=$(cd ../patientwords && pwd)
PW_BOUNDARY_RECEIPT=$(mktemp /tmp/patientwords-boundary-receipt.XXXXXX)
"$PW_BOUNDARY_PY" scripts/boundary_client/generate.py --check
"$PW_BOUNDARY_PY" scripts/check_frontend_boundary.py --site "$PW_SITE_ROOT" \
  --receipt "$PW_BOUNDARY_RECEIPT"
printf 'Retained boundary receipt: %s\n' "$PW_BOUNDARY_RECEIPT"
)
```

The runner uses a temporary sibling layout and the real exporter, local HTTP client
and frontend JS. It checks generated-client/schema consistency, independently known
probabilities and row identity, missing data and legacy fallback, plus deliberate
schema/semantic/HTTP failures followed by restored passes. Its receipt binds both
HEADs, tracked diffs, untracked files, fixture/tool hashes and browser results.
The source fixture is synthetic; ancillary payloads are fixture substitutes. This
is an exercised synthetic generation-to-consumer flow, not research regeneration,
live inference, the deployed site or every page. Review and then remove only the
printed receipt file when no longer needed. The site CI example remains inactive;
its activation and hosted evidence are separate work.

## Temporary regeneration and consumer check

Use this when exporter/collector behavior changes and both checkouts are available.
It exercises the current producer on landed source summaries and a disposable copy
of the current frontend; it does not generate new research measurements or publish.
Run from the engine root after the paired baseline. It needs a full frontend and
all source summaries/renders for the existing payload's batches, plus space for a
full site copy. A refusal caused by
missing data is a gap to report, not a reason to prune the stamp list.

```bash
(
set -euo pipefail
# From patientwords-engine; change only this sibling path if the site is elsewhere.
test -f scripts/export_frontend_simulated.py
PW_SITE_ROOT=$(cd ../patientwords && pwd)
PW_CHECK_ROOT=$(mktemp -d /tmp/patientwords-boundary.XXXXXX)
# Assign before export: export itself would hide a failed command substitution.
trap 'pw_status=$?; rm -rf -- "$PW_CHECK_ROOT"; exit "$pw_status"' EXIT
PW_CHECK_SITE="$PW_CHECK_ROOT/site"
export PW_SITE_ROOT PW_CHECK_ROOT PW_CHECK_SITE
python - <<'PY'
import hashlib, json, os, shutil, subprocess
from pathlib import Path
from scripts.sparse_guard import hidden_tracked
site = Path(os.environ['PW_SITE_ROOT']).resolve()
out = Path(os.environ['PW_CHECK_SITE'])
hidden = hidden_tracked(site)
if hidden:
    raise SystemExit(f'Source site has {len(hidden)} hidden tracked files; restore the checkout first')
payload_path = site / 'data/simulated_scenarios.json'
receipt = {
    'engine_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'site_revision': subprocess.check_output(['git', '-C', str(site), 'rev-parse', 'HEAD'], text=True).strip(),
    'source_payload_sha256': hashlib.sha256(payload_path.read_bytes()).hexdigest(),
    'engine_status': subprocess.check_output(['git', 'status', '--short'], text=True),
    'site_status': subprocess.check_output(['git', '-C', str(site), 'status', '--short'], text=True),
}
shutil.copytree(site, out, ignore=shutil.ignore_patterns(
    '.git', '.claude', '.agents', '.codex', '.vscode', '.venv', 'node_modules',
    '.DS_Store', '__pycache__', '.pytest_cache'))
(Path(os.environ['PW_CHECK_ROOT']) / 'source-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
PY
python - <<'PY'
import json, os, subprocess, sys
from pathlib import Path
site = Path(os.environ['PW_CHECK_SITE'])
payload = json.loads((site / 'data/simulated_scenarios.json').read_text())
stamps = [b['batch'].removeprefix('pairs_') for b in payload['batches']]
steered = sorted({s['batch'].removeprefix('pairs_') for s in payload['scenarios'] if s.get('steered')})
models = [model['id'] for model in payload['models_meta']]
archive = (payload.get('archive') or {}).get('release_url')
if not stamps or not models or not archive:
    raise SystemExit('Expected published stamps, model metadata and archive URL; inspect the source payload')
args = [sys.executable, 'scripts/export_frontend_simulated.py', '--engine', '.',
        '--frontend', str(site), '--stamps', ','.join(stamps),
        '--models', ','.join(models), '--steered-stamps', ','.join(steered), '--archive-url', archive]
subprocess.run(args + ['--dry-run'], check=True)
subprocess.run(args, check=True)
PY
python scripts/urgency_shift.py --frontend "$PW_CHECK_SITE" \
  --out "$PW_CHECK_ROOT/urgency_shift.json" --publish "$PW_CHECK_SITE"
python scripts/embed_scenario_joins.py --site "$PW_CHECK_SITE"
python scripts/export_traces_site.py --payload "$PW_CHECK_SITE/data/simulated_scenarios.json" --stamp-only
python scripts/validate_frontend_contract.py --site "$PW_CHECK_SITE" --engine . --strict
python scripts/claim_check.py --site "$PW_CHECK_SITE"
python scripts/seal_check.py --site "$PW_CHECK_SITE"
python scripts/check_pages.py --site "$PW_CHECK_SITE" --port 8901 --json "$PW_CHECK_ROOT/browser.json"
cat "$PW_CHECK_ROOT/browser.json"
)
```

Run the entire block in Bash as written; its subshell stops on any failed command
and removes only its freshly allocated temporary directory on exit, preserving the
failure status. Do not source it inside an `if`/`&&` condition, which can disable
Bash errexit. Save terminal output for the printed source receipt and browser report
before cleanup; keep failed-step evidence too. Investigate all warnings/refusals and
zero join counts. Python subprocess failures propagate via `check=True`. This bounded flow reuses the copied depth and other
specialized payloads. If their sources or producers changed, regenerate them using
the documented publication order and preserved pins before the joins. Record that
scope; do not describe it as the entire publication chain or a new live end-to-end
measurement. Compare changed values to the named source artifacts and examine the
rendered behavior; schema validity alone is not scientific validity.

## Cleanup and completion evidence

`check_pages.py` and browser test fixtures terminate their local servers in `finally`.
If interrupted, identify and stop only the process started for this check; do not kill
unrelated services on a shared port. A manual `python -m http.server` stops with Ctrl-C.
Pytest uses temporary directories and ignored `.pytest_cache/` / `__pycache__/` caches;
retain caches unless there is a task-specific reason to remove them.

The temporary regeneration block cleans its own directory on success or failure;
its variables are confined to the subshell. The synthetic boundary runner above
also owns and removes its temporary tree. Keep session receipts outside the repos
and inspect the final checkout rather than deleting broad caches:

```bash
(
set -euo pipefail
git status --short
git diff --stat
git diff --check
)
```

Report files changed; exact commands, runtime and observed results; failures/skips and
blocked/unrun checks with reasons; and paired engine/site revisions plus payload hash
or fixture identity. State whether evidence was synthetic fixtures, current exported
artifacts, temporary regeneration, or approved live execution. List larger code,
framework, dependency and CI work separately; keep session logs out of durable guidance.
