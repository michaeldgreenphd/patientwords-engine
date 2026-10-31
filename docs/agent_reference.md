# Agent reference

Binding detail linked from [AGENTS.md](../AGENTS.md). Paths in code spans are
relative to the engine repository root. Read the sections required by AGENTS.md
before acting; [verify.md](../verify.md) defines setup, checks and evidence reporting.
This document preserves the project's operational and research decisions. Dated
inventories and measurements are historical records, not current verification results.

## Execution and operations

**One exception, for pilots of the generation loop** (owner decision of 2026-09-30 on
PR #52). A measurement-validity
pilot of the stimulus-generation loop may run as Claude Code subagents inside the
owner's own interactive Claude Code session (the Workflow tool, in a cloud session or
on the owner's machine), on that session's subscription and with no repository key, and
its artifacts may be committed under `pilot/`, on four conditions: the run directory's
protocol, handoff and manifest (`pilot/PROTOCOL.md`, `pilot/HANDOFF.md` and
`pilot/manifest.json` for the first recorded run; the same three in `pilot/runs/<run_id>/`
for later ones) state that execution path; nothing it produces is
written under `data/` or `trace_out/`, counted as a measurement, or published to the
site; no script in this repository calls a paid provider API for it; and the
holdout seal check is CLEAN over each run directory before the commit.
Subscription usage in the owner's session is not provider spend, so
`fire_trigger.py`'s journal and ceiling do not apply to it. A pilot run through a
push-to-run lane, once one exists, needs no exception. Mechanics: `docs/pilot_runs.md`.

11 lanes. `scripts/fire_trigger.py` also knows `pab-probe`, whose
workflow exists only on the PAB branch. The lane reference, with every lane's exact
key set, is `docs/triggers.md` (it says why `.github/trigger/README.md` is not);
`tests/test_trigger_docs.py` checks it and the `AGENTS.md` table against `TRIGGERS`,
`PAID_TRIGGERS`, `PARK_DEFAULTS`, `KNOWN_KEYS` and the workflows on the branch, so
adding a lane without updating both fails the suite.

**Queue discipline (the sharpest tool in the repo):** the push-to-run lanes have per-branch
concurrency groups with `cancel-in-progress: false`, which means **one running + one
pending run**. Pushing a third trigger change *evicts the pending run silently*. Never
stack two pending runs in the same group; chain fires instead.

**Merge/copy danger:** any push that changes a trigger file fires its workflow, merges
to `main` included. When merging branches, keep the target branch's trigger files
unchanged (restore them before committing the merge) or you will re-fire runs and
double-spend. Two corollaries (case law: `docs/operators_handbook.md` §5): **"changes"
includes a trigger file appearing on a ref for the first time** — branch creation,
cherry-picks and rebases all count, and on a *new* ref **every** trigger file on it
counts, not only those that differ from the parent. Every push-to-run job carries
`if: ${{ !github.event.created }}` (`tests/test_workflow_created_guard.py`), so the push
that creates a ref is skipped and `fire_trigger.py`'s first push to a brand-new branch
fires nothing — fire from an existing branch; cherry-picks and rebases onto an existing
branch still fire. And the **resting-state rule**: a trigger file at rest is a loaded
default any branch operation can pull, so its committed content should be the cheapest
stage that exists with `commit_outputs`/`commit_sidecar` false, never the last expensive
thing that ran. `scripts/fire_trigger.py park --trigger <t>` (or `--all`) fires each
lane's no-op default from `PARK_DEFAULTS`. All 11 lanes rest parked (`jev-audit` and `action-annotate` once
first parked on `main`) except
`archive-renders`, from the cycle that fires its $0 PNG sweep until the next re-parks it
(`docs/routine_standing_prompt.md` §3d); after any real fire lands, re-park that lane
(`docs/operators_handbook.md` §3).

**Cost discipline:** Neuronpedia tracing, CPU logits, and all analysis are $0. The lanes
in `fire_trigger.py`'s `PAID_TRIGGERS` (the source of truth) spend provider credits — on
`main`, `scenario-generation`, `model-evaluation`, `advice-eval`, and
`petri-audit` when `mode: run` (or `mode: readapt` or `mode: rejudge`, whose judge alone
spends) and `jev-audit` when `live: true` — and so does `circuit-trace` with `show_mitigation: true` or
`mode: translation`; `docs/triggers.md` has each lane's costs. Every paid
generation run writes `<batch>.report.json`; mitigation runs write
`mitigation.part_NN.report.json` under the trace dir; jev-audit, `data/jev/runs/`. The spend ledger is
`docs/overnight_ledger_20260708.md`; `scripts/ledger_update.py` appends to the newest
`docs/*ledger*.md`, so never add another (`docs/README.md`, naming rule).

**Ops tooling (required path):** fire triggers ONLY via `scripts/fire_trigger.py` — it
journals every fire (`ops/trigger_journal.jsonl`), mechanically enforces the
one-running + one-pending discipline, hard-errors on unknown trigger keys (CI silently
ignores them), and refuses paid fires that would breach the daily operational ceiling
($2 unless `ops/budget_overrides.json` holds a dated raise for that UTC day; $10 for a
fire billed only to OpenRouter), counting landed spend **and** the `max_spend` every
paid fire made that UTC day, resolved or expired alike, until eviction
(`entry_holds_spend`; hold rules, including a deliberate fail-closed double count:
`docs/operators_handbook.md` §6). A fire tagged `"_campaign": "<name>"` must also fit
that campaign's owner-approved limits in `ops/campaign_budgets.json` (a total per lane, a
monthly total, and optionally a higher daily ceiling for its own fires); the fire path and
the CI `budget-gate` both apply them, and they are never overridable.
`scripts/ledger_update.py` is the only writer of spend numbers
(`ops/dashboard.json` + the ledger). `ops/dashboard.json` is **committed**
only by the daily Routine session (`ops/README.md`, `docs/routine_standing_prompt.md`):
`fire_trigger.py` rewrites its `queue` block on every fire and resolve and restores the
file unless the Routine, and only it, passes `--keep-dashboard`; it never commits it.
Both repos are public: never write secrets anywhere.

**Enforced, not only stated.** `.claude/settings.json` installs PreToolUse hooks
(`.claude/hooks/`) that refuse, from any Claude Code session: hand edits under
`.github/trigger/`; a commit of `ops/dashboard.json` outside the Routine environment;
ref deletions and force pushes; and a `git push` from Bash that carries a trigger-file
change. `.githooks/pre-commit` and `pre-push` repeat the dashboard, trigger and deletion
checks inside git itself when installed as `core.hooksPath`. A copied checkout
does not prove hook installation; inspect the configuration before relying on it.
`.claude/hooks/README.md` has how each layer is installed, including user-level in the cloud containers. Paid lanes and
circuit-trace's two Anthropic paths are also ceiling-gated server-side in their own
workflows (`fire_trigger.py budget-gate`).

## Exploratory preparation and current owner decisions

The owner exception in [AGENTS.md](../AGENTS.md#execution-model-nothing-paid-or-networked-runs-locally)
(PR #121) authorizes preparing the one-case manual route, not dispatching or running it.
Read [exploratory/baseline_ci.md](exploratory/baseline_ci.md) before any work on that
route. The workflow has only `workflow_dispatch`, read-only permissions, owner/main
and first-attempt guards, an exact expected-engine-commit assertion and a reviewed
readiness gate before runtime setup, downloads or model capture. It has its own
concurrency group and is not one of the 11 push-to-run lanes. Separate execution
approval and the readiness requirements remain necessary; neither a documentation
change nor an offline test satisfies them. Historical receipts bind their recorded
commits and must not be presented as tests of a later merge SHA.

For model defaults, dual judging, Jev and equity/Petri work, read
[decisions_20261014_owner.md](decisions_20261014_owner.md), including its later rounds.
Keep judge-of-record and secondary judgments distinct, preserve landed instrument
hashes and hypothesis corrections, rehearse rejudging candidates as required, and
respect the named run, cost and attempt scope of each approval. Operational preparation
is not new authorization to spend or publish. The decision record is the authority;
this entry point is not a replacement inventory of current permissions.

## Architecture

**Tracing (`graph_client.py` → `batch_eval.py`).** `MODEL_REGISTRY` lists four Neuronpedia
model ids (`gemma-2-2b` and `qwen3-4b` have hosted graphs and labelled transcoders;
`docs/cross-model.md` has dated status). Hosted requests retry on {429,500,502,503,504};
a 400 aborts immediately, and mid-batch failure truncates `results`. Modes: `2panel`,
`4quadrant`, `dialect`, `translation` (`README.md`). `--screen-targets` marks unmeasurable
pairs `screened_out`; `--show-mitigation` is the only Anthropic call.

**Feature tagging.** `neuronpedia_features.MODEL_SOURCE_SETS` registers labelled source
sets for gemma-2-2b and qwen3-4b; other models use `NullFetcher` (~0.0 clinical mass artifact).
Labelled is not publishable: qwen3-4b's mass is exploratory pending calibration. Anything
publishing or aggregating clinical mass gates per row on `scripts/feature_models.py`'s
`clinical_mass_publishable` (today only gemma-2-2b with `gemmascope-transcoder-16k`); additions
require owner decision after `scripts/feature_label_calibration.py`.

**Behavior without graphs (`scripts/logits_eval.py`).** Models Neuronpedia can't trace are
measured by direct CPU inference in CI, emitting **the same `batch_summary` schema** so
everything downstream merges unchanged (`backend: "logits"`, `source_set: null`, plus a
`continuations` map of greedy completions that disambiguates wordpiece tops).

**Output layout & checkpointing.** Each run writes `trace_out/<pairs-stem>/`; non-default
models get `trace_out/<stem>__<model>/`. CI renames each chunk's summary to
`batch_summary.part_NN.json` (NN = the first 1-based index the part measures: `offset + 1`
for a range, the first listed index for a logits-eval `indices` fire) so chunks never clobber — all
consumers must glob `batch_summary*.json`, and `results[i]["index"]` is the global 1-based
join key back into the batch file. Generation archives and trace outputs both commit to
`main` (the dispatched branch); CI's commits interleave with
yours, so `git pull --rebase` before every push. Pilot traces and pilot logits
(`output_root`) go to `pilot/traces/` and `pilot/logits/`; no collector reads them.

**Analysis chain.** `scripts/urgency_shift.py` is the collector (reads the site payload and
every `trace_out/*/batch_summary.part_*`, scores urgency tiers and flip classes as its
docstring defines them and the translated panel as `urgency_recovery`; `--publish` writes
the site's `../patientwords/data/urgency_shift.json`);
`scripts/paired_stats.py` consumes its row file. `scripts/export_archive.py` writes the
flat per-(pair × model) collaborator CSV. `scripts/publication_hold.py`'s `HELD_MODELS`, and
logits parts missing from `data/publication_release/logits_parts.json`, stay out of every published
number: each collector that pools `trace_out/*` skips them with a count (its docstring lists them; a new
one must too). Only the owner releases (`scripts/publication_release.py --release`).

**Publishing (`scripts/export_frontend_simulated.py`).** Merges every model's trace dir per
batch stamp into `scenario.models[<id>]`, mirrors the gemma base to the top level for
backward compatibility, emits `models_meta` (the frontend model-selector's source of
truth), and caps public interactive renders at the 200 most consequential (`--max-renders`;
flips first, then |language penalty|; HTML-only unless `--with-pngs`).
Full render sets go to GitHub Releases via
`scripts/archive_run.py` + the archive workflow (`docs/archiving.md`); pass the Release URL
back with `--archive-url`. **PNG renders live in those Releases, not in git** (pruned
from `main` from 2026-09-08 so the repository stays clonable): `scripts/render_archive.py
fetch` brings any one back and `coverage` says which are archived where (`docs/archiving.md`).
The exporter also
**deletes** site renders under `modes/simulated/` that match its own naming but that
neither the new payload nor any other site file lists (`scripts/render_prune.py`; why,
in `docs/prereg_divergence_log.md`); `--dry-run` writes and deletes nothing and lists them.
Over a sparse site checkout (the cloud containers' clone) the exporter refuses, writing
nothing, and `scripts/seal_check.py` exits 2: `git -C ../patientwords sparse-checkout
disable` first (each refusal: `.claude/skills/publish-site-data/SKILL.md`, precondition 3).
The Multi-turn page's two files come from `scripts/export_petri_multiturn.py`, **owner-run
once** after the wave-2 section 10 analysis and never in the Routine's chain (its module
docstring has the usage and every refusal).

**Frontend boundary authority.** The existing
[exploratory/frontend_boundary.md](exploratory/frontend_boundary.md) documents the
synthetic exporter → HTTP → real index-page test. Its schema is
`scripts/contracts/simulated_scenarios.v1.schema.json`; the neighboring OpenAPI
file references that same schema for the static JSON GET resource. The stdlib
adapter in `scripts/frontend_contract_schema.py` enforces its supported subset and
rejects unsupported features; `scripts/validate_frontend_contract.py` retains its
public wrapper and semantic checks. `scripts/check_frontend_boundary.py` uses the
separately locked test client/browser environment, fixture
`tests/fixtures/frontend_boundary.json`, temporary exports and real HTTP/page JS.
It verifies declared synthetic outcomes and deliberate defects, not model inference,
aggregate research validity, deployment or every detail-page interaction. Preserve
its source/fixture/schema hashes and clearly label synthetic evidence. The boundary
document and [verify.md](../verify.md) distinguish that slice from whole-site smoke
checks and artifact regeneration.

## Figure style (standing preference)

Figures follow Tufte: simple and readable, maximum data-ink. Concretely for the renderer
(`compare_viz.py`) and any new figure code: no decorative chrome, hairline structure only,
direct labels on the data instead of legends where possible, muted structural elements so
the clinical/off-target contrast carries the story, serif/mono typography per the site
palette, and every mark must survive gallery-thumbnail scale. When in doubt, remove ink.

## Verification and data-review requirements

Follow [verify.md](../verify.md) for setup and selected checks. Establish a current
baseline before attributing a failure; historical green reports do not prove the
present checkout is clean. If new live topics outrun `data/specialty_map.draft.json`,
mapping them is an owner-review data task, not a reason to relax the coverage floor.
Every bug fix gets a regression test. Workflow tests and YAML parsing validate
local structure/wiring, not hosted execution: inspect parameter defaults and list
normalization, and use the applicable platform checker when changing workflow YAML.

## Pull request workflow — required

Every pull request in this repository is independently reviewed by Codex agents.
Write changes to be reviewable by one: keep each pull request focused on a single
concern, make behavior changes testable and tested, and include migration or
compatibility notes whenever a change alters an API, a data file's shape, a
configuration key, or anything another repository or a published page reads.

1. Branch from `main` and open a pull request against `main`. Never push to
   `main` directly unless the owner explicitly says to.
2. Immediately after opening the PR, post a comment containing exactly
   "@codex review". Do this for every PR, without being asked, and again
   after any push that changes the diff so the new head is reviewed.
3. Address every Codex finding before the PR is considered done: verify it
   against the diff, push a fix for anything real, and reply on the thread
   saying what changed. Resolve the threads you addressed.
4. Ask before disputing. When a finding is unclear or looks wrong, do not
   argue with it or ignore it — post a comment addressed to @codex with the
   specific question, then act on the answer: fix, or reply with the reason
   it should not be taken. Codex answers direct questions; it does not
   respond to ordinary thread replies.
5. One editor per branch. Never use "@codex address that feedback", or
   otherwise ask Codex to push commits, while an agent or session is working
   on the branch. Asking Codex questions is fine at any time.
6. Keep the PR title and description accurate as the branch changes.
7. Agents do not merge; the owner merges.

Item 1 has one standing exception the owner has already granted, and it is
narrow: the **operational commits** described under *Execution model* go to
`main` directly — `scripts/fire_trigger.py`'s trigger-file and journal
commits, the daily Routine's dashboard, brief and site-data publishes, and
CI's own output commits. Everything else — code, tests, workflow YAML, docs,
skills, data-file shapes — goes through a pull request. Creating the branch
fires nothing (see the `github.event.created` guard above), so there is no
cost to branching.

## Repository-specific review requirements

The generic categories in `AGENTS.md` have specific referents here. A reviewer who does not
know them will pass a change that is destructive in this repo's terms:

* **Stored data that must not be altered:** `data/simulated/` batches are append-only
  archives with a `.report.json` cost sidecar; a landed batch is never rewritten.
  `trace_out/` summaries are measurements, not caches — a change that regenerates
  them differently is new data, not a refresh.
* **Pilot artifacts are labeled pilot outputs, not measurements:** files under
  `pilot/` come from the exception in *Execution model* and say so in their protocol,
  handoff and manifest. They are stored data all the same: a change to any of them is
  a data change, the chain is re-run from the recorded result files and the summary
  compared. A pull request that changes any `pilot/scripts/*.py` also recomputes and
  re-finalizes every recorded run (`pilot/` and each `pilot/runs/<run_id>/`), under an
  interpreter on the same side of Python 3.12 as the one the manifest's `python`
  records (`docs/pilot_runs.md` has why). Their numbers are
  checks of the pipeline, never claims about the study's stimuli or its models.
* **Irreversible spend:** any change to a file under `.github/trigger/` fires its
  workflow on push, including a merge that carries one; *Cost discipline* lists what
  spends. A trigger file changed incidentally — by a merge, rebase, or
  branch creation — is a defect, not a formatting detail.
* **The compatibility path that matters most:** `batch_summary*.json` is a shared
  schema across the hosted and logits paths, and the frontend exporter and every
  collector glob it. Verification output is written as `verify_summary*.json` on
  purpose so those collectors never ingest it; the two families share field names
  but not a filename, and `backend_agreement.py` is the only reader of both. A field added, renamed, or given a new
  meaning needs the consumers named in the Architecture section checked.
* **Single-writer invariants:** `ops/dashboard.json` is committed only by the daily
  Routine session (`fire_trigger.py` restores it for every other caller; a
  `scripts/ledger_update.py` run outside the Routine is reverted, not committed);
  `scripts/ledger_update.py` is the only writer of spend numbers. A
  second committer is a data-loss bug even when each write looks correct.
* **Owner-only files:** `.claude/settings.json`, `.claude/hooks/` and `.githooks/` are
  edited only by the owner, by hand; an agent pull request that touches them is a finding.
* **The site's CI runs engine code:** site `site_checks.yml` runs
  `scripts/validate_frontend_contract.py` and `scripts/check_pages.py` from engine `main`
  (or a same-named branch). Changing them, their imports or the engine files they read
  changes site CI; moving either fails every site push.
* **`patientwords-traces`** (GitHub Pages) serves the traces the site does not ship:
  payload `trace_url` links (`scripts/export_traces_site.py`) point there, and its nightly
  build copies engine `main`'s `trace_out/<batch>/index_NN.html`. Both skip a missing
  render, so moving or pruning those renders drops links at the next publish; changing
  the URL scheme on one side breaks published links.

## Coding constraints

* **Statistical work must be reproducible from its own output.** Set the random
  seed explicitly, pass it rather than relying on a global, and **record it in
  the artifact the run writes** — a seed that only exists in the invocation is
  not reproducible by whoever reads the JSON later. `scripts/paired_stats_rigor.py`
  is the reference: `--seed` with a default, `random.Random(seed)`, and `seed` in
  the emitted bundle. Document the methodology, transformations, and assumptions
  inline; these numbers get published, so a reader must be able to reconstruct
  what was computed without reading the caller.
* **No silent failures in extraction or parsing.** Missing data, an absent field,
  or an unexpected format is recorded as such (a null, a named refusal, a
  reported count) — never defaulted to zero, silently skipped, or averaged over.
  A measurement that quietly drops rows produces a plausible wrong number, which
  is worse than a crash. `expected_tier`'s coverage floor and `verify_probs.py`'s
  `token_parity` are the pattern: measure it, report it, refuse rather than guess.
* **Type hints on new modules and new public functions.** Not a retrofit rule.
  Many older scripts carry none; most newer ones have them. Requiring hints everywhere
  would turn every pull request into a typing project and train everyone to dismiss
  the reviewer. New files
  and new entry points, yes; matching the surrounding style in an old file is not
  a finding.
* **Analysis is decoupled from presentation.** This repo computes and emits data;
  `../patientwords` renders it. A script that writes HTML meant for a page, or a
  page-layout concern appearing in an exporter, belongs on the other side of that
  line. The two repos are the enforcement mechanism — keep it that way.

## Responding to code review

Every pull request here is reviewed by Codex. Its findings are
**hypotheses, not defects**, and the disposition is yours to establish:

1. **Verify against the actual file before changing anything.** Read the lines
   the finding names. On the first reviewed pull request (`patientwords#4`,
   2026-09-04) four of five findings were real; the fifth misread how a trailing
   newline renders in a diff. A later fact-check of this file found 22 false or
   misleading assertions, half of them written that same day. Plan for both error
   rates.
2. **Give every finding a disposition on its own thread**: fixed, naming the
   commit; declined, naming the reason and the evidence; or not applicable, and
   why. Silence is not a disposition. A decline goes through the ask-first
   step first (**Pull request workflow — required**, item 4): put the specific
   question to @codex, and decline only on its answer.
3. **Resolve only threads you actually fixed.** Resolving one you dismissed makes
   the pull request look handled when it is not.
4. **Never apply a finding you have not checked.** Both directions cost: applying
   a wrong finding puts a defect in the file the reviewers grade against, and
   dismissing a right one ships the defect the review existed to catch. Both
   happened on that first pull request.

The reviewers are graded by the **Code Review Rules** in `AGENTS.md`; this section is the
other half of that loop. Keep the rules in one place — restating them in a skill
or in `CLAUDE.md` recreates the drift this file exists to prevent.

## Known measurement limitations

Read these before adding a model, changing a measurement path or quoting a per-pair
value. The dates identify the evidence being summarized; rerun applicable checks
and cite the actual counterpart/artifact before claiming current verification.

* **The logits lane runs bfloat16, and that is the dominant per-pair error term.**
  Measured 2026-09-04 (`docs/backend_agreement_20260903.md`): interp-engine
  float32 agrees with the hosted service to **0.0005 on 70 of 71 measurements** —
  the rounding floor of hosted's three-decimal numbers; the 71st is the misread
  token below (max 0.0273 with it). Both disagree with our local bfloat16 path by
  0.004–0.006 mean and up to **0.032** per pair, roughly half the study's mean
  language penalty. `scripts/logits_eval.py` and `scripts/depth_probe.py` both
  hardcode bfloat16. Only gemma-2-2b has a second implementation to check
  against; for the other nine models the error is present but unmeasured.
  `mode: verify` on the logits lane measures it for any model in `HF_IDS` at $0.
* **Historical hosted target reads.** The exact evidence-linked target-read audit
  paragraph remains in [AGENTS.md](../AGENTS.md#known-measurement-limitations), where
  `tests/test_target_reads_evidence.py` checks its figures against
  `data/audits/target_reads_20261007.json`.
* **Per-pair penalties and flip labels are not stable measurements.** The negative
  control of 2026-09-04 (`docs/negative_control_20260904.md`, numbers regenerable
  from `ops/negative_control_20260904.json`, seed 7) measured each clinical
  prompt against a longer *clinical* phrasing of itself (+5.6 tokens vs the
  treatment's +4.14). Control mean -0.0018, CI [-0.0259, 0.0234], includes
  zero; treatment -0.0603, CI [-0.1046, -0.0192], excludes it. **The direction is
  robust** (36/14 negative, sign test p = 0.0026); **the magnitude is
  not** — the three most-negative pairs carry 45% of the effect, and without
  them the CI is [-0.0702, 0.0002]. Cite the direction, not −0.06. The control's per-pair
  sd is **58% of the treatment's** (variance ratio 0.33), pairs reach
  -0.214/+0.277, and a neutral clause flips the top-1 prediction — a site
  "redirect" — in 14 of 50 pairs. **No claim may rest on a single pair's penalty
  or flip label**; the aggregate phrase-clustered estimate is the only defensible one.
* **Publication consequence.** These limitations are not permission to silently change
  historical published values. Changing a measurement implementation and remeasuring
  or republishing pairs are separate decisions; retain the existing owner review.

The fixed `action-annotate` lane is paid only in `mode: run` ($1 total, Anthropic).
Its harmless park calls nothing. [The runbook](exploratory/action_pilot.md) specifies
first-attempt/source/budget gates, unknown-charge handling and artifact recovery.
It does not change existing judges, historical measures or publication inputs.
