# ops/ — mission control

Private operator surface for the autonomous daily cycle. One page
(`dashboard.html`), one data file (`dashboard.json`), one writer (the daily
Routine session). Nothing in this directory is published; the public site
lives in the sibling `patientwords` repo.

## Layout

What `ops/` holds, grouped by how each file is used (`git ls-files ops`,
2026-09-30). A file a script names as its default path must stay where it is;
the writer column says which script that is.

**Live state and operating files.** Current; the tooling or the operator
reads each of them. None of these is archived.

| Path | What it is | Written by |
|---|---|---|
| `dashboard.json` | the dashboard's data (contract below) | the Routine only (single-writer rule below) |
| `trigger_journal.jsonl` | one row per fire, parks included; `resolve` marks a row resolved in place, and rows are never deleted | `scripts/fire_trigger.py` |
| `budget_overrides.json` | owner-authorized ceiling raises, each for one UTC day, with the authorization quoted | by hand, on the owner's words; read by `scripts/fire_trigger.py` |
| `disclosure_log.jsonl` | append-only log of every vendor reproducibility pack version | `scripts/advice_eval.py repro-pack`, `scripts/petri_audit/repro_pack.py` |
| `dashboard.html` | the dashboard page | hand edits |
| `dashboard.sample.json` | a fully populated example of the contract; `tests/test_ledger_update.py` reads it | hand edits |
| `routines.md` | registry of every scheduled automation and its standing prompt's hash | the session that changes a schedule or standing prompt, in the same commit |
| `environment_setup.sh` | the reviewed copy of the cloud environments' setup script; each environment's setup script is a pasted copy of it | by hand |

**Reading the journal.** A row is in flight only while it is unresolved,
not evicted, and younger than the expiry window (8 hours,
`DEFAULT_EXPIRE_HOURS` in `scripts/fire_trigger.py`, overridable with
`MEDLANG_TRIGGER_EXPIRE_HOURS`). An unresolved row older than that is
**expired and unharvested**, not in flight: it no longer holds a queue slot,
`fire_trigger.py resolve` declines it (resolve acts only on in-flight rows),
and a paid row's `max_spend` still counts against the ceiling until its UTC day
ends. Whether its run landed is answered by the run's outputs on `main` or its
GitHub run, not by the row. On 2026-09-30, 150 of the journal's 935 rows were
unresolved, all of them past the window; the Routine's archive-renders sweep
(`docs/routine_standing_prompt.md` §3d, "harvest and re-park it the next
cycle") adds one each time it fires, because the next cycle always comes after
the window. The journal is not rewritten to resolve them.

**Analysis outputs.** Regenerable from committed data by the script named.
Where the site's `data/` holds a file of the same name, **the site copy is the
published one** and the file here is the engine-side output.

| Path | Written by | Site copy |
|---|---|---|
| `drift_series.json` | `scripts/drift_sentinel.py` (Routine §3) | `data/drift_series.json`, identical |
| `jlens_insights.json` | `scripts/jlens_insights.py` (publish chain) | `data/jlens_insights.json`, identical |
| `translation_scale.json` | `scripts/translation_scale.py` (publish chain) | `data/translation_scale.json`, identical |
| `retrace_consistency.json` | `scripts/retrace_consistency.py` | `data/retrace_consistency.json`, **differs**: the site copy (2026-08-20, 87 pairs) is newer than this one (2026-07-17, 72 pairs) |
| `specialty_breakdown.json` | `scripts/specialty_breakdown.py` | `data/specialty_breakdown.json`, **differs**: this copy (2026-07-16) is newer than the site's (2026-07-14) |
| `coverage_gaps.json` | `scripts/coverage_gaps.py` (publish chain) | none |
| `lens_sentinel_series.json` | `scripts/lens_sentinel_check.py` | none |
| `jlens_position_scan.json` | `scripts/jlens_position_scan.py` | none |
| `screen_sensitivity.json` | `scripts/screen_sensitivity.py` | none |
| `tier_sensitivity.json` | `scripts/tier_sensitivity.py` | none |
| `pab_tier_scenario.json` | `scripts/pab_tier_scenario.py` | none |
| `negative_control_20260904.json` | `scripts/negative_control_stats.py`; `docs/negative_control_20260904.md` cites it and `tests/test_negative_control_stats.py` reads it | none |
| `backend_agreement_20260903.json`, `backend_agreement_interp_vs_{hosted,local}_20260904.json` | `scripts/backend_agreement.py`; `docs/backend_agreement_20260903.md` cites them | none |
| `site_text_outline.Rmd` | `scripts/extract_site_text.py` (its default output) | none |

The engine's root `urgency_shift.json` is not a copy of the site's
`data/urgency_shift.json` and is not meant to match it: the root file is the
collector's row file (`scripts/urgency_shift.py`, keys `summary` and `rows`),
and the site file is the `--publish` format, which adds `tiers`,
`tier_examples`, `vocabulary_status` and `render_min_n`. The difference is by
design.

**Subdirectories.**

| Path | What it is |
|---|---|
| `decks/` | owner decision decks and demo notes, 2026-07-11..08-29; `docs/` and the holdout-seal-check skill cite them by path, and `scripts/seal_check.py` sweeps them with the rest of `ops/` |
| `referee/` | the 2026-07-14 referee panel's reports and verdicts (`docs/referee_panel_20260714.md`) |
| `replication/` | the 2026-07-14 cross-model replication outputs and `comparison_20260714.md` |
| `pab_ci/` | a staged, not live, copy of the PAB branch's `pab_probe.yml` workflow (its README says what landing it takes); `tests/test_pab_ci_staged.py` reads it |
| `prototypes/` | a 2026-07-11 j-lens page prototype |
| `archive/` | dated one-off snapshots that nothing reads (below) |

**`archive/`.** Moved here on 2026-09-30 after a search of both repositories,
their workflows, skills, tests and docs found no reference to any of them:
`display_rankings_20260716.json` (a snapshot for the 2026-07-17 deck),
`neuronpedia_issue_prefill.txt` (2026-07-12 issue text for Neuronpedia),
`site_text_outline_20260717.md` and `site_text_outline_full_20260717.md`
(dated site-text outlines; the current one is `site_text_outline.Rmd`), and
`evidence_power_audit_20260728.Rmd` (the owner's decision copy of
`docs/audits/evidence_power_audit_20260728.md`). `git log --follow` on the new
path shows each file's history.

## Opening the dashboard

From the repo root:

```bash
python3 -m http.server 8900
# then open http://127.0.0.1:8900/ops/dashboard.html
```

Opening `ops/dashboard.html` directly as `file://` also works, with one caveat:
Chrome blocks `fetch()` on `file://` pages, so the page shows a paste pane
instead of loading `dashboard.json` itself. Paste the contents of
`ops/dashboard.json` into the textarea and press **Load**; rendering is
identical either way.

`dashboard.sample.json` is a fully populated example of the contract, kept for
development and for eyeballing the layout. The page reads only
`dashboard.json`; to preview with sample data, copy the sample over
`dashboard.json` locally and do not commit the copy.

## Data contract — `ops/dashboard.json` (schema_version 1)

A single committed JSON object. Every consumer must tolerate **any** field
being absent — the dashboard renders an em-dash or a pending state for missing
data, and a bare `{}` must render every panel without error. Do not add fields
casually; bump `schema_version` on breaking shape changes.

Top-level fields, and which step of the Routine's cycle writes them:

| Field | Meaning | Written by |
|---|---|---|
| `schema_version` | contract version, currently `1` | fixed |
| `updated_utc` | UTC timestamp of the last write; the page shows a STALE chip when this is older than 26 h (the Routine has failed) | every Routine write, incl. every `ledger_update.py` dashboard write |
| `updated_by` | `"routine"` or `"session"`; `ledger_update.py` sets `"session"` only when the field is absent and otherwise preserves the existing value | every Routine write |
| `queue` | per-concurrency-group running/pending slots (`circuit-trace`, `logits-eval`, `activation-patching`, `jlens-readout`, `scenario-generation`, `model-evaluation`, `archive-renders`), each `{fired_utc, commit, note}` or `null` (the Routine's mirror may write a free-text summary string instead - both shapes are valid to readers) | `scripts/fire_trigger.py` (fire/resolve), mirrored by the Routine |
| `runs_recent` | compact log of recent workflow runs `{workflow, fired_utc, status, note}` | the Routine's own edits |
| `spend` | generation-run and daily ceilings vs. spend, lifetime total, per-day map, per-channel map (`by_day_by_channel`, CHANNEL-SPLIT 2026-08-04: `today` also carries `anthropic_usd`/`openrouter_usd`; the $2/day guard counts the Anthropic channel only, falling back to the pooled figure on dashboards without the split), sidecar filenames already counted (`entries_seen`), `last_scan_utc`, ceiling `alerts` (alerts stay pooled) | `scripts/ledger_update.py` (idempotent sidecar scan) |
| `tierb` | overnight campaign progress: `target_pairs`, `generator`, `start_utc`, `accepted_pairs`, `traced_pairs`, `screened_in_pairs`, `batches[]` | `scripts/ledger_update.py` (costs) + the Routine's own edits (counts, statuses) |
| `verdicts` | current one-line scientific verdicts | the Routine's own edits |
| `findings_delta` | dated list of what changed, newest first on the page | the Routine's own edits |
| `decisions_pending` | `{id, title, context}` items awaiting the owner | the Routine's own edits |
| `blockers` | plain strings describing what is stuck | the Routine's own edits |
| `notes` | standing operational notes (footer) | the Routine's own edits |
| `decisions_log` | resolved owner decisions, newest first — the audit trail behind `decisions_pending` | the Routine's own edits |
| `queued_next` | the fire queue: what goes into each lane as it frees, in order | the Routine's own edits |
| `endpoint_protocol` | the standing rule that Tier B holdout unsealing runs **only** on an explicit owner instruction, never on a schedule | owner decision, transcribed once; do not edit without one |
| `critic` | `{last_pass, report}` pointer to the newest `docs/critic/critic_*.md` | the Routine's own edits, Mon/Wed/Fri |

Two `tierb` counters have **no automated writer** and drift silently:
`traced_pairs` and `screened_in_pairs`. Recount before quoting either
(`traced_pairs` = distinct `(batch stem, results[].index)` across
`trace_out/<Tier B stem>*/batch_summary*.json`; the method is recorded in
`tierb.traced_pairs_method`). The value carried here read 2049 until the
2026-08-03 recount put it at 1080.

## Spend accounting

`scripts/ledger_update.py` folds new cost sidecars into `spend` and appends one
bullet per sidecar to the human ledger — the lexicographically newest
`docs/*ledger*.md`, or `docs/spend_ledger.md` (created with a one-line header)
when no ledger file exists. The ledger append happens **before** the dashboard
write, so a failed append aborts the run without committing `entries_seen` and
the next run re-scans the same sidecars — bullets are never lost. `spend.by_day`
buckets each sidecar by its `run_timestamp` parsed to a UTC date (unparseable
stamps fall back to the run's `--date`), and every writing run refreshes
`spend.today` to `{date: <--date>, spent_usd: by_day[<--date>]}`. Tier B rows in
`tierb.batches` key on the batch archive name (`<batch>.json`) and are upserted,
never duplicated.

The $2/day ceiling enforced by `scripts/fire_trigger.py` counts **committed**
spend: landed spend from `spend.today` **plus** the `max_spend` held by
every paid trigger-journal entry (`PAID_TRIGGERS` in the script, and
mitigation circuit-trace fires at their imputed commitment) fired on the same
UTC day and not evicted. Paid journal entries record their `max_spend` at
fire time, and the hold lasts the whole UTC day: `resolve` frees the queue
slot, not the hold (since 2026-09-23 — releasing it on resolve let a
resolved run's cost drop out of the day before the sidecar scan counted it).
Once the scan folds a run's sidecar into `spend.today`, that run counts
twice for the rest of its day, which fails closed.
`--override-budget` can bypass only a ceiling refusal — a missing or invalid
`max_spend` (non-numeric, boolean, non-finite, or not > 0) always refuses.

## Single-writer rule

`ops/dashboard.json` is written **only by the daily Routine's session** (a
fresh session per firing since the 2026-08-04 cutover; the Routine is
configured in the claude.ai Routines UI, and what each firing does is set by
`docs/routine_standing_prompt.md`, registered in `ops/routines.md`;
2026-07-10..08-03 it was the orchestrator session the old Routine fired
into), through exactly three paths: `scripts/fire_trigger.py` (queue slots
and the trigger journal), `scripts/ledger_update.py` (spend accounting from
cost sidecars), and the Routine's own direct edits (verdicts, findings,
decisions, blockers, notes, Tier B counts). Every other session and every consumer treats the file
as read-only. This keeps a frequently-committed file free of merge conflicts
and keeps `updated_utc` meaningful: staleness on the dashboard means the
Routine failed, not that someone else forgot to touch a field. If an
interactive session finds something worth recording, it hands the item to the
Routine (or leaves it in a handoff doc) rather than editing the file itself.
Owner-authorized interim (2026-08-04, INTERIM-CYCLE): when a fresh-session
Routine firing fails, the takeover session may run that day's single cycle
inline and holds the writer role for it, through the same three paths.
