# ops/ — mission control

Private operator surface for the autonomous daily cycle. One page
(`dashboard.html`), one data file (`dashboard.json`), one writer (the daily
Routine session). Nothing in this directory is published; the public site
lives in the sibling `patientwords` repo.

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
| `spend` | generation-run and daily ceilings vs. spend, lifetime total, per-day map, sidecar filenames already counted (`entries_seen`), `last_scan_utc`, ceiling `alerts` | `scripts/ledger_update.py` (idempotent sidecar scan) |
| `tierb` | overnight campaign progress: `target_pairs`, `generator`, `start_utc`, `accepted_pairs`, `traced_pairs`, `screened_in_pairs`, `batches[]` | `scripts/ledger_update.py` (costs) + the Routine's own edits (counts, statuses) |
| `verdicts` | current one-line scientific verdicts | the Routine's own edits |
| `findings_delta` | dated list of what changed, newest first on the page | the Routine's own edits |
| `decisions_pending` | `{id, title, context}` items awaiting the owner | the Routine's own edits |
| `blockers` | plain strings describing what is stuck | the Routine's own edits |
| `notes` | standing operational notes (footer) | the Routine's own edits |

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
spend: landed spend from `spend.today` **plus** the in-flight `max_spend` of
every ACTIVE trigger-journal entry for either paid trigger
(`scenario-generation`, `model-evaluation`) fired on the same UTC day. Paid
journal entries record their `max_spend` at fire time; `resolve` releases the
in-flight hold once the run's real cost lands via the sidecar scan.
`--override-budget` can bypass only a ceiling refusal — a missing or invalid
`max_spend` (non-numeric, boolean, non-finite, or not > 0) always refuses.

## Single-writer rule

`ops/dashboard.json` is written **only by the orchestrator session** (the daily
Routine fires into it since the 2026-07-10 rebind), through
exactly three paths: `scripts/fire_trigger.py` (queue slots and the trigger
journal), `scripts/ledger_update.py` (spend accounting from cost sidecars), and
the Routine's own direct edits (verdicts, findings, decisions, blockers,
notes, Tier B counts). Every other session and every consumer treats the file
as read-only. This keeps a frequently-committed file free of merge conflicts
and keeps `updated_utc` meaningful: staleness on the dashboard means the
Routine failed, not that someone else forgot to touch a field. If an
interactive session finds something worth recording, it hands the item to the
Routine (or leaves it in a handoff doc) rather than editing the file itself.
