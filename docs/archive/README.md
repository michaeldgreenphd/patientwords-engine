# docs/archive — superseded documents

The files here are kept for the record and describe the project at the date in
their names. None of them is a current instruction. `git log --follow <new path>`
shows each one's history from its original path.

Before each file moved (2026-09-30), both repositories were searched with
`git grep` for its path and its name. Nothing executable, no test, workflow,
skill, ops file, data file or site file cited any of them; the only citations
are the dated records named in the last column, which are left as written and
now point at the old path.

| Now | Was | Added | What it was, and what replaced it | Cited by (dated records, left as written) |
|---|---|---|---|---|
| `HANDOFF_20260709.md` | `HANDOFF.md` (repository root) | 2026-07-09 | `docs/HANDOFF_20260804.md`, itself superseded by `docs/operators_handbook.md` | `docs/HANDOFF_20260804.md`, `docs/audits/doc_accuracy_20260810.md`, `docs/audits/doc_accuracy_20260824.md` |
| `first_prompt_20260804.md` | `docs/first_prompt_20260804.md` | 2026-08-03 | A paste-in first prompt that sends a session to the ops branch retired on 2026-09-04. `docs/fresh_session_bootstrap.md`, `docs/operators_handbook.md` and `docs/routine_standing_prompt.md` do that job now. | none |
| `backfill_accel_prompt.md` | `docs/backfill_accel_prompt.md` | 2026-07-22 | Nothing: the Routine it was written for was never created (its own banner says so), and the backfill closed on 2026-08-26 (`docs/coordination/backfill_8b_complete_20260826.md`). | `docs/HANDOFF_20260804.md`, `docs/audits/timing_forensics_20260727.json` |
| `handoff_20260724_trace_pace.md` | `docs/handoff_20260724_trace_pace.md` | 2026-07-24 | Neuronpedia 429 pacing for a trace chain that has since completed (`docs/operators_handbook.md` §2). | `docs/audits/timing_forensics_20260727.json` |
| `handoff_20260730_dialect_small_multiples.md` | `docs/handoff_20260730_dialect_small_multiples.md` | 2026-07-29 | The request for dialect small-multiples renders. Delivered: see the next row. | none |
| `handoff_20260730_dialect_multiples.md` | `docs/handoff_20260730_dialect_multiples.md` | 2026-07-30 | The delivery note for that request; the renders are live on the site (`modes/dialect/sweep/multi_*`, 40 files). | none |
| `jlens_continuous_handoff.md` | `docs/jlens_continuous_handoff.md` | 2026-07-20 | A wiring checklist whose work landed: `scripts/export_jlens_transport.py`, run by the publish-site-data skill. | none |
| `prompt_context_20260709.md` | `docs/prompt_context_20260709.md` | 2026-07-09 | A one-off context pack for reviewing a draft prompt. | `docs/overnight_ledger_20260708.md` |
| `timeline_endnote_DRAFT.md` | `docs/timeline_endnote_DRAFT.md` | 2026-07-10 | A methods-endnote draft for the owner's voice. It says the nightly cycle keeps it fresh; that cycle ended with the 2026-08-29 maintenance rewrite. Its numbers come from `data/timeline.json` (`scripts/study_timeline.py`). | none |

Two other files left their old places in the same change:

- `docs/traces_site_build.yml` was deleted. It was an outdated copy of
  `.github/workflows/build.yml` in `michaeldgreenphd/patientwords-traces`, which
  is the file that runs; the copy still named the retired ops branch. Its last
  content is `git show 1fd9f4f8:docs/traces_site_build.yml`.
- `.claude/audit-patientwords-engine-2026-09-06.md` moved to
  `docs/audits/claude_config_audit_20260906.md`, beside the other audits and
  inside the holdout seal sweep, which reads `docs/` and `ops/` but not
  `.claude/`.

Never move a preregistration, amendment, divergence log, decision record or
ledger here, nor anything `docs/README.md` lists as read by code, records or
the site.
