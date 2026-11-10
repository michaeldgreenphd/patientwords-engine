# Open-results migration record, 2026-11-10

A dated record of the move from the publication hold to the
[open-results policy](open_results_policy.md). It is a dry run: nothing in it was
published, and no measurement, manifest or site file was changed to produce it. The
numbers come from `scripts/open_results_migration.py`; the full output is
`ops/open_results_migration_20261110.json`. No stimulus text appears here or there.

Regenerate from the engine root (about 75 seconds; needs the sibling site checkout):

```bash
python scripts/open_results_migration.py --site ../patientwords \
  --baseline-ref d8d0855d --out /tmp/open_results_migration.json
```

Inputs: engine `trace_out/` at `d8d0855d976b62a1a98b8cceab24a407673d7610` with this
change applied; site payload at `b7da45303be3057c5993d1bb192219827d1acda9`.

## 1. The published statistics did not move

| Check | Result |
|---|---|
| `scripts/urgency_shift.py` as it was at `d8d0855d`, and the same script reading through `scripts/results_policy.py`, over identical inputs | byte-identical output, sha256 `8b3068a5ffdeb1f8c9885a5e04674a1cd1fe7b5528bfa892418a158e93a42d70` |
| `scripts/export_frontend_simulated.py` as it was at `d8d0855d` (run with only its own script directory importable, so it used the old hold) and the same script at this change, into two disposable site copies with the published 27 stamps and 4 models | byte-identical `data/simulated_scenarios.json`, sha256 `d949b5c6bb2dd9b522fde6a64c27b6b16dea1e888e9eaa9bf668ae35624caaa4`; identical render set (218 files) |
| Parts the default membership `study-interim/1` admits | 951 of 1,235, the same 951 the hold admitted |
| Parts it does not read, by reason | 93 logits parts outside the pin; 39 + 39 parts of `gemma-4-e2b` and `qwen3.5-2b-base`; 113 parts of hand-authored sets. The same 284 the hold skipped |
| Recomputed rows against the engine's committed `urgency_shift.json` | 18,208 against 18,205. The 3 extra rows are `gemma-2-2b` rows of `drift_sentinel_20261106`, a hosted part that landed after the committed file was written |

A fresh export differs from the site's committed payload (sha256 `5bcd3eac…`) for both
versions of the exporter alike: the committed file was last fully exported on 2026-08-29
and carries the joins that later steps embed. That difference predates this change.

After the export, the rest of the publish chain was run on the disposable copy, with the
catalogue step added: `urgency_shift.py --publish`, `embed_scenario_joins.py` (4,745
urgency joins, 421 depth classes), `export_traces_site.py --stamp-only` (1,509 stamped),
`export_results_catalogue.py`, then the gates. `validate_frontend_contract.py --strict`:
0 errors, 0 warnings. `claim_check.py`: all claims verified. `seal_check.py`: CLEAN, 183
sealed phrases, 1,207 files scanned. `check_pages.py`: 22 pages, 0 failing. This is a
regeneration from landed summaries on a copy; it is not a publish and not a new
measurement.

The last table row is not caused by this change, and it shows a gap the hold never covered:
hosted parts are read without a pin, so a statistics file moves when one lands. The
snapshots record hosted hashes for that reason.

## 2. What becomes visible

Parts the hold kept out of everything the publish chain wrote, now listed in the
results catalogue. Their rows are listed except those at sealed Tier B pairs, which are
counted and not written:

| Reason the study membership does not read them | Parts | Public rows |
|---|---|---|
| CPU-logits part outside the pin (gap-fill of six original models) | 93 | 1,889 |
| Model `gemma-4-e2b` (2026-10-09 cohort) | 39 | 2,056 |
| Model `qwen3.5-2b-base` (2026-10-09 cohort) | 39 | 2,056 |
| Hand-authored exploratory sets (`agscen_`, seven models) | 113 | 1,722 |
| **Total** | **284** | **7,723** |

`medgemma-1.5-4b-it` has no landed part. When its priority-selection parts land, the
catalogue labels those rows `outcome_selected_priority_subset`.

The catalogue also lists, per row, the 17,145 rows of parts that were already inside
the published statistics. Before this change the site's per-row values were the gallery
payload (four models), the trimmed urgency rows file, and a collaborator archive that
`scripts/README.md` dates to 2026-08-20.

## 3. What stays restricted

| Restriction | Count | Released by |
|---|---|---|
| Rows the Tier B seal covers | 2,054 rows at 187 sealed pairs, counted and never written (1,672 in parts inside the study membership, 382 in parts outside it) | the owner's explicit unseal instruction |
| Redistribution-limited text (`pabharvest_`) | 3 parts listed without rows | a recorded licence review |
| Artifact integrity failures | 0 parts | restoring the recorded bytes |

The seal is applied per pair. A pair that `sealed_pair` seals in any run is withheld in
every run, and its prompts are never written. Three Tier B pairs are sealed only because one
run traced them with a probe extension whose text hashes holdout
(`docs/prereg_divergence_log.md`, 2026-07-17); the gallery exporter already withholds them
whole. A first version of the catalogue exporter decided row by row and would have listed
those three pairs' prompts and 36 rows from other runs. A review found it before anything
was pushed; `tests/test_results_catalogue.py` has the regression test. The exporter also
applies the publish gate's own phrase matcher (`scripts/seal_check.py`), so it does not write
what that gate would then refuse.

Listed without rows for a scope reason, not a restriction: 225 parts of stimulus
families with no row-export entry in policy version `open-results/1`, and 40 parts of
instrument runs (32 activation-patching, 8 context) that have their own exporters.

`scripts/seal_check.py` over the exported catalogue: `CLEAN - 183 sealed phrases, no
hits`, with the one existing allowlisted containing field (ruling of 2026-09-23) in two
files.

## 4. Execution states of all 1,235 parts

| State | Parts |
|---|---|
| `completed` | 728 |
| `completion_not_recorded` (written before parts recorded completion) | 434 |
| `partial` | 73 |
| `empty`, `unreadable` | 0 |

## 5. What the statistics would become under `exploratory-open/1`

This is a separately declared analysis. It is reported so the change is known before
any switch; it replaces nothing. Each cell is `study-interim/1` → `exploratory-open/1`.
Collector rows 18,208 → 25,080; holdout rows excluded from aggregates 1,544 → 1,980.
`scripts/paired_stats_rigor.py`, seed 7, 5,000 resamples.

| Model | Unique phrases | Mean penalty | Downgrades / upgrades | Sign test, BH-adjusted |
|---|---|---|---|---|
| `gemma-2-2b` | 1712 → 1712 | -0.0320 → -0.0320 | 93 / 32 → 93 / 32 | 8.73e-08 → 8.73e-08 |
| `gemma-3-4b-it` | 1321 → 1577 | -0.0507 → -0.0489 | 72 / 23 → 82 / 27 | 6.34e-07 → 1.68e-07 |
| `qwen3-1.7b` | 1264 → 1520 | -0.0494 → -0.0490 | 66 / 29 → 80 / 32 | 1.86e-04 → 6.57e-06 |
| `qwen3-4b` | 1121 → 1377 | -0.0465 → -0.0459 | 65 / 14 → 80 / 20 | 2.08e-08 → 4.46e-09 |
| `apertus-8b-meditronfo` | 1864 → 1864 | -0.0293 → -0.0293 | 63 / 27 → 63 / 27 | 2.82e-04 → 2.50e-04 |
| `gemma-2-2b-it` | 1058 → 1438 | -0.0403 → -0.0461 | 55 / 25 → 77 / 37 | 1.05e-03 → 2.59e-04 |
| `llama-3.2-3b` | 1078 → 1438 | -0.0316 → -0.0320 | 51 / 22 → 65 / 35 | 1.05e-03 → 3.52e-03 |
| `medgemma-4b-it` | 1864 → 1864 | -0.0473 → -0.0473 | 88 / 26 → 88 / 26 | 2.75e-08 → 1.22e-08 |
| `meditron3-8b` | 1864 → 1864 | -0.0351 → -0.0351 | 80 / 27 → 80 / 27 | 5.75e-07 → 5.75e-07 |
| `olmo-2-1b` | 1068 → 1438 | -0.0435 → -0.0445 | 55 / 11 → 91 / 14 | 1.08e-07 → 4.26e-14 |
| `gemma-4-e2b` | not in → 1864 | not in → -0.0348 | not in → 89 / 35 | not in → 2.14e-06 |
| `qwen3.5-2b-base` | not in → 1864 | not in → -0.0533 | not in → 142 / 41 | not in → 1.22e-13 |

What changes and why:

- **The exploratory Benjamini-Hochberg family grows from 6 tests to 8.** Every adjusted
  value in that family is recomputed, including for models whose data did not change
  (`apertus-8b-meditronfo` 2.82e-04 → 2.50e-04, `medgemma-4b-it` 2.75e-08 → 1.22e-08).
  The registered family stays at 4 tests.
- **The three registered models with gap-fill parts change** because their data change:
  256, 256 and 256 more unique phrases for `gemma-3-4b-it`, `qwen3-1.7b` and `qwen3-4b`.
  This is the pin's effect, not a family effect, and it is why an advance of the pin
  needs its own snapshot.
- **The Bonferroni simultaneous interval is sized over 12 models instead of 10**
  (alpha 0.005 → 0.004167). At fixed data and fixed draws that widens an interval. In this
  comparison it is wider for 3 of the 10 shared models and narrower for 7
  (`penalty_ci95_simultaneous` widths in the JSON: for example `gemma-3-4b-it`
  0.0392 → 0.0339 and `medgemma-4b-it` 0.0250 → 0.0260), because six models gain rows and
  the shared bootstrap stream shifts for all of them. `meditron3-8b`, whose data are
  unchanged, moves 0.0185 → 0.0180 from the stream alone.
- **Intervals move even where data do not**, because the bootstrap consumes one random
  stream in sorted model order. `qwen3-4b`'s 95% interval is [-0.0594, -0.0333] in one
  run and [-0.0574, -0.0343] in the other; part of that is new data and part is the
  stream. Seed 7 identifies an interval only together with the exact model set.
- Direction is unchanged for every model: more downgrades than upgrades in both runs.
  The magnitude caveats in `docs/agent_reference.md` (*Known measurement limitations*)
  apply to both columns.

These are interim, exploration-split numbers on a first-token lexical endpoint with a
draft urgency vocabulary. They are not clinical findings and not the confirmatory
endpoint.

## 6. Callers

Every script that pooled `trace_out/` through the hold now reads through the policy
module with the default membership, unchanged in what it admits:

`urgency_shift.py`, `paired_stats_rigor.py`, `export_frontend_simulated.py`,
`export_archive.py`, `study_timeline.py`, `screen_sensitivity.py`,
`interp_analyses.py`, `translation_scale.py`, `audit_target_reads.py` (mirror),
`export_tag_mass.py`, `retrace_consistency.py`, `publication_release.py`.

One defect was found and fixed in the collector. `urgency_shift.py` filled rows from
the site payload without asking the gate, so a payload that displayed a model outside
the membership would have pooled it into every aggregate. It was unreachable only
because the exporter refused such models. The fill loop now applies the membership's
model rule; `tests/test_results_policy.py` has the regression test.

The same loop has a second gap that was left in place on purpose. The published site
payload carries 11 `qwen3-4b` rows at keys whose engine parts are outside the pin, and the
loop takes them, so they are in the published statistics today (`qwen3-4b`: 1,121 unique
phrases with them, 1,110 without). Dropping them is the consistent rule, and it would move
a published number, so it was not done here: a first version of the fix did drop them, the
byte-identity check failed, and the change was reverted. The collector now prints the count
(`note: rows taken from the site payload at keys whose engine part this membership did not
read ... qwen3-4b 11`). Decision for the owner: drop them in a new snapshot, or pin the
parts they come from. The loop does refuse two things it did not before, neither of which
occurs in today's payload: a scenario of an excluded stimulus class, and a model that no
cohort declares.

Two refusals were added to every analysis membership after review, and neither changes
what is read today (the old gate and the default gate agree on all 1,235 parts): a part
whose bytes differ from its ledger record, and a part whose own `graph_model` no cohort
declares. Before, a new model's hosted parts would have joined the statistics on landing.

Lens readers (`jlens_insights.py`, `export_jlens_loglens.py`,
`export_jlens_transport.py`, `jlens_position_scan.py`) read only `__jlens_` and
`__loglens_` directories and have no stimulus-class check. No hand-authored set has a
lens directory today. The skip must be added before any lens fire on such a set; this
is unchanged from before and still open.

## 7. Compatibility

- Public URLs and existing payloads are unchanged. The catalogue is a new directory,
  `data/results_catalogue/`, and a new page.
- `scripts/publication_hold.py` keeps every name older code imports (`Gate`,
  `ReleaseError`, `HELD_MODELS`, `is_held`, `is_held_run_dir`, `is_exploratory_run_dir`,
  `EXPLORATORY_STEM_PREFIXES`, `load_manifest`, `sha256_file`, `RELEASE_MANIFEST`,
  `MANIFEST_SCHEMA`).
- `data/publication_release/logits_parts.json` is unchanged and still `logits_release/1`.
- `scripts/publication_release.py --release` now refuses when a pinned or ledger-recorded
  part's committed bytes differ from the record. Before, it rewrote the hash. `--models`
  is new and only adds entries.
- Collector stdout changed: the skip line now names the membership and the reason
  (`membership study-interim/1 (scripts/results_policy.py), parts not read: ...`), and
  the collector and exporter print the membership in force. Nothing parses those lines
  except the tests, which were updated.
- The seven `agscen_*.report.json` sidecars say their outputs are kept out of every
  published aggregate. That is still true. Sidecars are append-only and were not edited.

## 8. Not done here

- No snapshot was advanced and no pin was changed.
- The site's gallery payload still carries four models. Adding a model there is a
  membership decision, because the joins and the statistics read that payload.
- `paired_stats_rigor.py --site` is not a step of the publish chain documents, although
  the 2026-08-15 owner decision automated it; `data/model_stats.json` on the site dates
  from 2026-08-29. Found during this work, not changed by it.
