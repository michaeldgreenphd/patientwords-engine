# HANDOFF — ops-infrastructure build, 2026-07-09

Living document for model/session handoff (owner may transition this
session from Fable to Claude Opus 4.8 at the 3:00 PM or Friday checkpoint).
A successor session should be able to take over from this file plus the
repo. **No secrets live here or anywhere in the repo — API keys exist only
as GitHub Actions secrets. Keep it that way.**

## The assignment (owner directive, 2026-07-09 midday)

Owner leaves Friday for one week. Primary objective while away: **pure data
generation** — the pre-registered Tier B run (`docs/preregistration_tierB.md`,
1,600 haiku-generated pairs, ≤$8 generation, $2/day operational ceiling)
runs autonomously. This session builds the infrastructure to manage that
without daily owner intervention.

**Out of scope (owner is doing these personally in their own session — do
NOT touch):** all public-site salience and reduction work: plain-language
abstract, "why this matters" paragraph, glossary unification, concrete-case
lead, activation patching, folding model-evaluations into methods,
re-rendering dialect tiles, translation flow chart, any site text/HTML/figure
edit. Engine-side **data publishing** (exporter, urgency collector, data
payload commits) stays in scope.

## Checkpoints (owner-mandated)

- **Checkpoint 1 — today 3:00 PM** (assumed America/New_York → 19:00 UTC):
  deliver `site_text.Rmd`, infra status, this file's draft, blockers.
- **Checkpoint 2 — Friday morning:** dashboard rendering in a browser with
  simulated + empty data, zero console errors; all script regression tests
  passing; dry-run of the Routine digest push; final HANDOFF.md.

## Architecture decided (build in flight)

Single data contract: **`ops/dashboard.json`** (schema_version 1) — written
exclusively by the daily Routine session via the ops scripts; read by the
dashboard HTML and the brief generator. Every consumer tolerates missing
fields.

| Piece | Path | State |
|---|---|---|
| Mission-control UI | `ops/dashboard.html` (+ `ops/dashboard.sample.json`, `ops/README.md`) | building (workflow `wf_44d8afae-d7b`) |
| Trigger guard + fire wrapper | `scripts/fire_trigger.py`, journal `ops/trigger_journal.jsonl`, `tests/test_fire_trigger.py` | building |
| Spend accounting | `scripts/ledger_update.py`, `tests/test_ledger_update.py` | building |
| 3-section brief + digest | `scripts/daily_brief.py`, `tests/test_daily_brief.py` | building |
| Site text extraction (.Rmd) | `scripts/extract_site_text.py` → `../patientwords/docs/site_text.Rmd` | building — due at Checkpoint 1 |
| Routine standing prompt | `docs/routine_standing_prompt.md` | **committed** |
| This file | `HANDOFF.md` | committed, keep current |

Key design decisions and why:

1. **Queue guard is a wrapper, not a hook.** Dev containers can't query the
   GitHub Actions API reliably, so `fire_trigger.py` keeps a committed
   journal (`ops/trigger_journal.jsonl`) of fires; ≥2 unresolved entries for
   a trigger blocks the third fire (the CI concurrency group holds one
   running + one pending; a third push silently evicts). Entries expire
   after 8h (jobs cap at ~6h) and are resolved at harvest. The standing
   prompt makes the wrapper the only sanctioned firing path.
2. **$2/day enforcement lives in the guard**: paid triggers must carry
   `max_spend`, and the guard refuses when `max_spend + today's spend`
   would breach `spend.daily_ceiling_usd` in `ops/dashboard.json`.
3. **Tier B attribution rule**: a sidecar counts toward Tier B iff
   `task=="pairs"`, model == `tierb.generator` (claude-haiku-4-5), and
   `run_timestamp >= tierb.start_utc`. `start_utc` is null until tonight's
   first Tier B fire sets it.
4. **Brief = render of dashboard.json** (three sections: Delta, Verdicts,
   Blocked-on-owner; `--digest` emits the ≤450-char push line). One JSON,
   three consumers, no drift.
5. **Rmd is strict extraction** — block IDs as HTML comments
   (`<!-- id: <page>.b<NNN> -->`) so the owner's edits map back to
   page+position mechanically. No rewording by us, ever.

## Current live state (update at every handoff)

- Branch (both repos): `claude/gemma-clinical-colloquial-interp-mavx04`.
  Site deploys from `main` (sanctioned: push branch, then branch:main).
- Runs in flight: circuit-trace run 64 = haiku-translator arm on the
  20-downgrade set (compare vs opus 8/20 recovery); run 65 pending = trace
  of second haiku batch (equivalence n). Logits run 14 = gemma-3-4b-it
  stem 3/4 (final unified column). Harvest check-in armed 13:45 UTC
  (trigger `trig_018p7kMkVW3c7E6pUyppX7nc`).
- Tonight: fire Tier B start per the pre-registration if the haiku
  translation arm and equivalence recheck hold (owner: "based on feedback
  and findings trigger the week long evaluation").
- Spend to date: $9.56 lifetime generation by sidecars (~$10.4 remaining of
  the $20 envelope); Tier B budget $8 sits inside that.
- Haiku evidence (basis of generator choice): validator yield 76% vs opus
  60%; screen-in 55% vs 48%; penalty −0.046 [−0.084, −0.012] (n=27) vs
  opus −0.036 [−0.080, +0.006]; $0.002/accepted pair vs $0.0164.

## Remaining work (ordered)

1. Integrate workflow output: fix review findings, run full pytest + ruff,
   finalize KNOWN_KEYS for logits-eval/model-evaluation/archive-renders
   against their workflow YAML defaults, seed `ops/dashboard.json` with the
   real live state above, commit everything.
2. Add ops rules to `CLAUDE.md` (fire only via `fire_trigger.py`; dashboard
   single-writer rule).
3. Checkpoint 1 (19:00 UTC): send `site_text.Rmd` + status + this file.
4. 13:45 UTC wake: harvest runs 64/65/14; haiku translation verdict feeds
   tonight's Tier B go/no-go; then unified gemma-3 recompute + data publish.
5. Tonight: fire Tier B batch 1 via `fire_trigger.py` (sets
   `tierb.start_utc`), begin chaining.
6. Thursday: create the daily Routine (fresh-session cron, prompt =
   `docs/routine_standing_prompt.md` body, notifications {push:true});
   dry-run one firing; verify digest push arrives.
7. Friday morning: Checkpoint 2 package.

## Gotchas a successor must not relearn

- Push-to-run CI: ANY push that changes a trigger file fires its workflow —
  including merges. One running + one pending per group; third push evicts
  silently. Chain, never stack.
- Generation archives commit to **main**; trace outputs to **the dispatched
  branch**. `git pull --rebase` before pushing; copy batch files from main
  to the branch before referencing them in a trace trigger.
- A trace re-run on the same batch stem clobbers `batch_summary.part_NN`
  files — use an alias batch file (copy + `alias_of` sidecar, cost 0) for
  re-traces, e.g. `data/simulated/downgrades_txhaiku.json`.
- Workflow params heredocs: the push-path `defaults` dict must contain every
  trigger key; unknown keys are silently ignored by CI (hence the guard's
  strict key validation).
- Only gemma-2-2b produces hosted graphs; other models' `clinical_mass`
  ≈ 0.0 is an artifact (NullFetcher), not a finding.
- `medlang-batch-eval` mid-batch failures truncate `results` with no
  per-pair error records — reconcile counts against the batch file via
  `results[i]["index"]`.
- Owner's timezone assumption: America/New_York (3:00 PM = 19:00 UTC).
  Unconfirmed — flagged at Checkpoint 1.
