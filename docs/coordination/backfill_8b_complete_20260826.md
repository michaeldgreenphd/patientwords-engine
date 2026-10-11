# 8B-medical logits backfill — COMPLETE (2026-08-26)

Both 8B models now have full next-token coverage across every generation batch:

- **meditron3-8b**: 39/39 batch dirs, 2,343 measured rows, every row with `language_penalty`
- **apertus-8b-meditronfo**: 39/39 batch dirs, 2,343 measured rows, every row with `language_penalty`
- Row counts are identical per batch across the two models (exact parity).

With this, all six claim-grade models (gemma-2-2b, gemma-3-4b-it, qwen3-1.7b,
qwen3-4b, meditron3-8b, apertus-8b-meditronfo) have full-parity coverage.
The babysitter loop that drove the backfill (owner-directed 2026-08-07,
`INTERIM babysitter` fires in `ops/trigger_journal.jsonl`) is now closed and
will not re-arm.

## Coverage inventory (parts / rows, identical for both models)

Batches at 100 pairs carry 4 chunk parts (offsets 0/25/50/75). Smaller and
older batches carry their historical part layout. Full table recomputed from
`trace_out/*__{model}/batch_summary.part_*.json` on 2026-08-26; the two
Tier B batches (0809: 69 rows, 0811: 68 rows) cover every non-withheld pair —
sealed holdout rows are excluded upstream by design, not missing.

Final legs landed this cycle: `pairs_20260806T135728Z` closers
(meditron run 32977600958, apertus run 32983756556, both completed/success,
part_76 verified idx 76..100, 25/25 penalties).

## Incident record (2026-08-26, tick 164)

The daily Routine's cycle (~14:00Z) resolved the babysitter's terminal 51-75
journal entries and fired the meditron 0806 closer itself. The babysitter's
subsequent `resolve --trigger logits-eval --all` then swept that **in-flight**
entry from the journal. Recovery: the run was GitHub-verified in_progress, it
was NOT re-fired, and the apertus closer was chained with the accounting
recorded in its fire note (commit 156cd52c). Queue discipline
(one running + one pending) held throughout; no run was duplicated or evicted.
**Lesson, now standing practice:** check each active entry's terminality
individually before any `resolve --all` — another writer may have swapped the
queue since the last look.

## Next steps

- The nightly Routine's stats refresh (`urgency_shift` → `paired_stats` →
  site publish) picks up the new parts automatically; no manual fire needed.
- Residual haiku null-tier gaps (advice archives 153329Z ×4, 003502Z ×1,
  235403Z ×5, 194624Z ×2) fold into future judging passes only — no dedicated
  slot (owner rule 15cbcf03).
- Open owner decisions at time of writing: round-4 verdict on the 56-pair
  scale batch; ox-branch merge to main (keep main's trigger files unchanged
  when merging); site `model_provenance.json` hand-sync; Neuronpedia hosted
  graph generation outage (no output since 08-21, j-lens control healthy).

## Correction (2026-10-09)

The sentence "With this, all six claim-grade models (gemma-2-2b, gemma-3-4b-it, qwen3-1.7b, qwen3-4b,
meditron3-8b, apertus-8b-meditronfo) have full-parity coverage" was not true, and this record keeps it as
written. Counted on 2026-10-09 against the committed `trace_out/` parts of the same 39 batches (2,343 pairs,
meditron3-8b's coverage as the reference): `gemma-2-2b` was complete through its hosted traces, and the two 8B
models as stated above; `gemma-3-4b-it` missed 702 pairs (24/39 batches complete), `qwen3-1.7b` 764 (24/39),
`qwen3-4b` 947 (21/39). Of the other original models, `llama-3.2-3b` missed 975, `olmo-2-1b` 985 and
`gemma-2-2b-it` 1,140. The site's published `data/urgency_shift.json` agrees (rows for gemma-3-4b-it on 25
batches, qwen3-1.7b 24, qwen3-4b 23). The 2026-08-28 brief's "262 of 390 batch-legs" was right; the
2026-08-29 maintenance rewrite of the Routine prompt repeated the claim above. The owner approved filling
the gaps on 2026-10-09 (`docs/model_matrix.md`, "Running the campaign"); the filled values publish only when
the owner releases them (`scripts/publication_release.py`).
