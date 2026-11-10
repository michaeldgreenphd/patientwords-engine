# Correction record: `summary.penalty` in the gallery payload, and what a re-export changes with it

Dated 2026-11-10. Nothing in this record was published. No model was called and no
measurement was made. The numbers come from one regeneration of the site's data in a
disposable copy, from the landed summaries, with the producers at engine `95bf61cc5424`
and the site at `13ece51` (published payload sha256 `5bcd3eac…`). The machine-readable
record is `ops/payload_reexport_accounting_20261110.json`. No stimulus text appears here
or there; rows are named by `(batch, batch_index)`.

## 1. Answer

The exporter cannot publish the summary correction alone. `scripts/export_frontend_simulated.py`
has no option that rewrites `summary` and keeps the rows: every export reads the current
parts through the analysis membership. A full re-export today therefore publishes three
kinds of change together. They are kept apart below, each with its own table and its own
treatment.

The correction is published alone through a second producer-side tool, added the same
day for this purpose: `scripts/restamp_payload_summary.py`. It applies the corrected
`payload_summary.build_summary` to the scenarios already in the published file, refuses
unless the result differs from the published summary in `n_phrases`,
`mean_phrase_deduped` and `ci95` only, and writes the file in the exporter's own
serialization, so every byte outside the summary block is unchanged
(`tests/test_restamp_payload_summary.py`). On the published payload it gives exactly the
values of section 3 (sha256 `5bcd3eac…` → `b7573599…`).

| Kind | What changes | Authorised today |
|---|---|---|
| Bug correction | `summary.penalty`: `n_phrases` 1163 → 1124 and two derived fields | Yes, as a correction published with a superseding snapshot (section 3) |
| Changed inputs | 13 `qwen3-4b` rows of one batch; through them `qwen3-4b` in `data/model_stats.json` and in the urgency files; one metadata flag | Partly. The 11-row removal is an open owner decision (section 4) |
| Expanded population | Advancing the pin or switching membership | No. Not part of a re-export; a separate owner decision (section 5) |

Release content (section 7): the bug correction alone, through the restamp tool, with
one superseding snapshot. The changed inputs are not in it: they need the owner
decisions of section 8, and a full re-export follows those decisions as its own release.
No pin advance and no membership switch in either.

## 2. What was regenerated, and every difference

Procedure: the temporary-regeneration block of `verify.md`, with the copy under a
scratch directory. The site working tree was copied once without `.git`, `modes/`
included, so the exporter's render checks and its prune ran as they would in a publish.
Then the real exporter (dry run, then a write), `scripts/urgency_shift.py --publish`,
`scripts/embed_scenario_joins.py` and `scripts/export_traces_site.py --stamp-only`, with
the 27 published stamps and the 4 published models. On the copy,
`validate_frontend_contract.py --strict` gave 0 errors and 0 warnings, `claim_check.py`
verified all claims and `seal_check.py` was clean (183 sealed phrases, 1,217 files).
`check_pages.py` was not run. The copy was deleted.

The regenerated `data/simulated_scenarios.json` differs from the published file in 42
JSON paths. Scenario order, identities and display indices are unchanged (1,774
scenarios). Every path is in one of these classes; none is left over.

| Class | Paths | Cause |
|---|---|---|
| Summary correction: `summary.penalty.n_phrases`, `.mean_phrase_deduped`, `.ci95[0]`, `.ci95[1]` | 4 | section 3 |
| Row objects removed: `models.qwen3-4b` at `(pairs_20260706T201750Z, 3…13)` | 11 | section 4.2 |
| Row values changed: `models.qwen3-4b` at `(pairs_20260706T201750Z, 1)` (9 paths) and `(…, 2)` (10 paths) | 19 | section 4.1 |
| `models_meta`: `qwen3-4b.graphs` false → true, `qwen3-4b.n_traced` 1261 → 1250 | 2 | section 4.4 |
| `traced_by_model`: `qwen3-4b.backend` "logits" → "hosted" | 1 | section 4.4 |
| `urgency_meta.per_model_deduped.qwen3-4b`: `n_phrases` 1255 → 1244, `flips` 548 → 541, `mean_penalty` -0.0401 → -0.0405 | 3 | the 11 rows; copied from the urgency file by the join step |
| `traces_site._provenance`: `engine_sha`, `generated_utc` | 2 | run stamp of the stamp step; every scenario's `trace_url` is unchanged |
| Anything else | 0 | |

A full chain also changes files outside the payload:

| File | Change | Cause |
|---|---|---|
| site `data/urgency_shift.json` | rows 13,692 → 13,684; 40 summary paths | 10 of the 11 `qwen3-4b` rows leave the trimmed row file (row 5 carries no tier information and was never in it); 2 `gemma-2-2b` rows of `drift_sentinel_20261106` enter, from a hosted part that landed after the file was last published on 2026-11-06 |
| site `modes/simulated/` | 235 tracked files deleted (193 HTML, 42 PNG); none added or changed | the render prune (`scripts/render_prune.py`, owner ruling 2 of 2026-09-23). The published payload lists none of them. The publish skill expects about 235 at the first export after that date |
| site `data/model_stats.json` | unchanged by the chain | `scripts/paired_stats_rigor.py` is not a chain step (section 4.3) |

## 3. Bug correction: the summary dedupe

`scripts/payload_summary.py` grouped scored rows on a nested `prompts.clinical`. The
exporter's rows hold the text as top-level `clinical_prompt`. Every row took the
`batch#batch_index` fallback, so nothing was deduplicated. The wrong key is in the
module's first commit (`5c7ab9954`, 2026-07-21; read through the GitHub API, the local
clone is shallow). It was corrected in `c46db48f0` on 2026-11-10. The block is a
base-model (`gemma-2-2b`) figure, so the 13 `qwen3-4b` rows do not enter it.

| `summary.penalty` | Published | After re-export |
|---|---|---|
| `n_phrases` | 1163 | 1124 |
| `mean_phrase_deduped` | -0.0387 | -0.0367 |
| `ci95` | [-0.0477, -0.0291] | [-0.046, -0.0267] |
| `n_scored_rows` | 1163 | 1163 |
| `mean_rows_raw` | -0.0387 | -0.0387 |
| `population` | `public_payload` | `public_payload` |

Where it shows: `index.html` (two sentences) and `wording-differences/index.html` (one
sentence) print `n_phrases` and the mean rounded to whole points. The visible change is
1163 → 1124 distinct phrases. The printed mean stays at 4 (3.87 and 3.67 both round to
4). No page reads `ci95`. The page rendering was checked in the pull request that made
the code change and was not repeated here. `data/claims_manifest.json` has no entry for
these numbers.

Authorisation: yes. `verify.md` (the notes under its paired baseline) names the remedy:
re-export with the corrected producer and publish the result. The contract gate accepts the legacy form
through 2026-12-15 UTC and fails it from 2026-12-16. `docs/open_results_policy.md` says a
published statistic changes only through a versioned snapshot and that a correction is a
new snapshot id that says what changed. The payload is in the published statistics set
(`STATISTICS_FILES` in `scripts/results_snapshot.py`).

Recommended treatment: publish it as a correction, in a superseding snapshot whose change
sentence names it as a bug correction. It is not a change of endpoint: neither registered
endpoint is computed from this block. The registration's analysis rule "dedupe by phrase
before any pooled count" was not met by this one descriptive block while the defect
stood; `docs/prereg_divergence_log.md` has the row.

## 4. Changed inputs

All 13 rows are `qwen3-4b` rows of `pairs_20260706T201750Z`, the first stamp of the
payload. One file explains them. Commit dates are from the GitHub commits API.

| Date (UTC) | Engine commit | `trace_out/pairs_20260706T201750Z__qwen3-4b/` |
|---|---|---|
| 2026-07-07 15:01 | `1162e9215` | `batch_summary.part_01.json` lands: CPU logits, pairs 1–13 (sha256 `198192f9…`) |
| 2026-08-29 | | last full export of the site payload; it holds those 13 rows |
| 2026-09-02 12:15 | `d0e478849` | the same file name is rewritten by a hosted trace of pairs 1–2 (the re-probe in `docs/cross-model.md`). The 13-result logits summary is no longer on the branch |
| 2026-10-09 | | the pin is written (409 parts). It has no entry for this directory: the only part there is hosted |
| 2026-10-31 05:18 | `b4451bed4` | `batch_summary.part_03.json` lands: CPU logits, pairs 3–13, a gap-fill run (sha256 `9e214489…`). It is outside the pin |

Verified: the file at `1162e9215` was read through the GitHub contents API. All 13 of its
results equal the published rows in target token, both probabilities, the penalty and
both spreads. So each published value was correct for the part that existed when it was
exported. The measured fields of the 13 rows (everything except the `urgency` join that
a later step writes) are identical in every site commit this clone holds, 2026-08-27 to
today.

### 4.1 Two rows take the hosted values

| Row | Field | Published (logits, 2026-07-07) | Regenerated (hosted, 2026-09-02) |
|---|---|---|---|
| `(…, 1)` | `prob_clinical` / `prob_patient` | 0.0118 / 0.0063 | 0.037 / 0.058 |
| | `language_penalty` | -0.0055 | 0.021 |
| | `flipped` | false | false |
| `(…, 2)` | `prob_clinical` / `prob_patient` | 0.4239 / 0.1804 | 0.218 / 0.103 |
| | `language_penalty` | -0.2435 | -0.115 |
| | `flipped` | false | true |

Also changed on both rows: `circuit_diff` (null → an object), both spreads (9 or 10
entries → 5), the top-token probabilities; on row 1 the measured target token; on row 2
the patient-side top token.

The hosted part is inside the membership: `study-interim/1` reads hosted parts as they
are, without a pin, and snapshot `study-interim-20261110` records this part's sha256
(`390e116a…`). The collector has read the hosted values since 2026-09-02. The published
payload already holds one trace of that: since site `70f1229` (2026-11-06) row 2 carries
`flipped: false` beside an urgency join computed from the hosted values.

Row 1 is not a second reading of the same token. The published row measured the whole
intended target (8 characters). The hosted part measured a 5-character leading piece of
it and has no `target_read` field; it predates the exact-read change of 2026-10-07
(`AGENTS.md`, *Known measurement limitations*).

Authorisation: the membership rule already reads this part. Publishing the changed rows
needs the superseding snapshot, nothing else. The row-1 token difference should be stated
in the snapshot's change sentence.

### 4.2 Eleven rows leave the payload and the statistics

The collector takes these 11 rows from the published payload today, although the part
now at their keys (`part_03`) is outside the pin. That is question (B) of
`docs/open_results_migration_20261110.md`, section 6. The rows are declared one by one
in `data/results_policy/legacy_payload_rows.v1.json`, and
`tests/test_legacy_payload_rows.py` fails when the collector takes a row the record does
not declare, or stops taking one it declares.

Two facts were not known when that section was written:

1. The published values of these rows cannot be reproduced from any part on the branch.
   They come from the 2026-07-07 file, which was replaced on 2026-09-02.
2. `part_03` is a different measurement of the same 11 pairs (2026-10-31). Its penalties
   differ from the published ones on 10 of 11 rows, by at most 0.0219.

A re-export removes the 11 model objects, because the exporter applies the membership
and the membership does not read `part_03`. The collector then has nothing to take. So a
re-export under the present pin decides question (B) as "drop".

Authorisation: not yet. The migration record reserves it: "Decision for the owner: drop
them in a new snapshot, or pin the parts they come from." Decision D1 in section 8.

### 4.3 `data/model_stats.json` (question A)

Answer: the ten differing fields come from the two rows of 4.1 and from nothing else.

The collector reads engine parts before the payload. On 2026-08-29 it read the logits
values of rows 1 and 2; since 2026-09-02 it reads the hosted values. Penalty sum over
1,121 phrases moves by 0.0265 + 0.1285 = 0.155, which is +0.00014 on the mean (-0.0466 →
-0.0465). Row 2 becomes a flip (497 → 498).

Verified two ways. (1) The 2026-08-29 payload (site `48fae78`) against today's collector
rows, all four payload models, 5,638 rows: exactly these 2 rows differ. (2) Today's
collector rows with these 2 rows set back to their 2026-08-29 values, then
`scripts/paired_stats_rigor.py` (seed 7, 5,000 resamples): the result equals the
published `data/model_stats.json` in every field except `_provenance` and `source`.
The second check also covers the six models that are not in the payload.
`data/audits/target_reads_20261007.json` already counted `published_stale: 2`; that these
are the same two rows is inferred from the count.

`qwen3-4b` in three states. The other nine models are identical in all three.

| Field | Published (2026-08-29) | Recomputed today, payload unchanged | After full re-export, pin unchanged |
|---|---|---|---|
| rows / unique phrases | 1152 / 1121 | 1152 / 1121 | 1141 / 1110 |
| mean penalty | -0.0466 | -0.0465 | -0.0470 |
| 95% interval | [-0.0595, -0.0334] | [-0.0594, -0.0333] | [-0.0605, -0.0340] |
| simultaneous interval | [-0.0661, -0.0280] | [-0.0660, -0.0279] | [-0.0660, -0.0287] |
| flips | 497 | 498 | 491 |
| downgrades / upgrades | 65 / 14 | 65 / 14 | 65 / 14 |
| downgrade rate | 0.1308 [0.1024, 0.1636] | 0.1305 [0.1022, 0.1633] | 0.1324 [0.1037, 0.1656] |
| sign test p, raw / BH | 5.19e-09 / 2.08e-08 | same | same |
| Tier A mean (phrases) | -0.0771 (235) | -0.0764 (235) | -0.0806 (224) |

The first two columns differ by the two rows of 4.1. The third also drops the 11 rows of
4.2. Direction, the downgrade and upgrade counts and the sign test are the same in all
three. These are interim, exploration-split numbers on a first-token lexical endpoint;
the caveats in `docs/agent_reference.md` (*Known measurement limitations*) apply.

Authorisation: not yet. `scripts/paired_stats_rigor.py --site` is not a step the publish
chain documents, and the migration record says "Regenerating the file is a publish the
owner decides." Decision D2. The file also copies `models_meta` from the payload, so a
regeneration takes the two `models_meta` changes of section 2 as well.

### 4.4 The `graphs` flag

`traced_by_model[model]` is the metadata of the first stamp in which the model has
results, and within that directory the last part read that states each key.
`models_meta[model].graphs` is true unless that backend is "logits". The first stamp is
this batch. On 2026-08-29 its `qwen3-4b` directory held one logits part. Now the
exporter reads the hosted probe part there and does not read `part_03`. So the flag
turns to true.

After a re-export the payload holds 1,250 `qwen3-4b` rows: 2 from the hosted part and
1,248 from 21 pinned logits parts. Three pages read the flag (`technical/index.html`,
`simulated-scenarios/index.html`, `simulated-scenarios/scenario.html`). They would
describe `qwen3-4b` as a model with hosted attribution graphs and stop marking it
"next-token only".

Authorisation: none applies; this is a side effect, and the result misdescribes 1,248
rows. Decision D3. It is not caused by the summary correction.

## 5. Expanded analysis population

Not part of a re-export. It happens only through
`scripts/publication_release.py --release` (optionally `--models`) or an edit of
`default_membership`, each with its own snapshot (`docs/open_results_policy.md`, *What
did not change on 2026-11-10*; `analysis_pin.auto_advance` is false).

The numbers are in `docs/open_results_migration_20261110.md`, section 5, and are not
recomputed here. Its `qwen3-4b` row gives 1,121 → 1,377 unique phrases, mean -0.0465 →
-0.0459, downgrades / upgrades 65 / 14 → 80 / 20. That table is for
`exploratory-open/1`. A scoped pin advance for `qwen3-4b` alone would read the same
`qwen3-4b` parts (15 parts outside the pin, 317 result rows, counted today), with the
Benjamini-Hochberg families left at 4 and 6 tests, so its adjusted values and intervals
would differ from that table. That variant was not computed.

`--models` selects by model. There is no option to pin one part. Pinning `part_03` to
keep the 11 rows therefore means pinning all 15 `qwen3-4b` parts, and the 11 rows would
then hold the 2026-10-31 values, not the published ones.

Recommended treatment: keep it out of this release. Decide it separately, with its own
snapshot and its own divergence-log entry.

## 6. What a full re-export includes beyond the bug correction

Stated once, as a list:

1. `qwen3-4b` rows `(pairs_20260706T201750Z, 1)` and `(…, 2)` change to hosted values;
   row 1's value is for a different token.
2. `qwen3-4b` is removed from rows `(pairs_20260706T201750Z, 3…13)`. `n_traced` 1261 → 1250.
3. Through 2, the published statistics lose 11 rows: `qwen3-4b` 1,121 → 1,110 unique
   phrases once `data/model_stats.json` is regenerated; `urgency_meta` and site
   `data/urgency_shift.json` change at once.
4. `qwen3-4b` is labelled as a graph model (`graphs: true`, backend "hosted").
5. Site `data/urgency_shift.json` also gains the `drift_sentinel_20261106` rows.
6. 235 unlisted render files are deleted from the site.
7. A new run stamp in `traces_site._provenance`.

The exporter's options are `--stamps`, `--steered-stamps`, `--models`,
`--preview-models`, `--no-pngs` / `--with-pngs`, `--max-renders`, `--archive-url` and
`--dry-run`. None limits a run to the summary or keeps the published row values.
`--models` without `qwen3-4b` would remove the model from all 1,261 rows. Editing the
payload by hand is forbidden (`AGENTS.md` of the site, *Invariants*). The exporter
therefore cannot publish item 0, the summary correction, without items 1 to 7;
`scripts/restamp_payload_summary.py` can (section 1).

## 7. Release content: two releases, kept apart

**This release: the bug correction alone.**

- `python scripts/restamp_payload_summary.py --site ../patientwords` rewrites
  `summary.penalty` in the site's `data/simulated_scenarios.json` from the file's own
  1,774 scenarios: `n_phrases` 1163 → 1124, `mean_phrase_deduped` -0.0387 → -0.0367,
  `ci95` [-0.0477, -0.0291] → [-0.046, -0.0267]. `n_scored_rows`, `mean_rows_raw`, the
  totals and every scenario are unchanged. No other site file changes.
- One superseding snapshot records the payload's new sha256 and `summary.penalty` at
  both site commits (section 9).
- The contract gate then reports no legacy note for the payload
  (`LEGACY_SUMMARY_ACCEPTED_THROUGH`, 2026-12-15, stops mattering once this is published).

Reason for keeping it alone: it is the one change that is a correction of a calculation
on unchanged inputs. It is authorised as a correction; the other changes are not
corrections and each has a numerical consequence the owner has not yet decided.

**A later release, after the owner decides: the full re-export.** One full re-export
under `study-interim/1` with the pin unchanged would contain:

- the 13 rows as the membership reads them today: 2 at hosted values, 11 without
  `qwen3-4b` (decision D1 = drop);
- site `data/urgency_shift.json` from the same collector run;
- site `data/model_stats.json` regenerated from the same collector output (decision D2);
- the render prune;
- `qwen3-4b` still described as "next-token only", through an exporter change made and
  reviewed before the export (decision D3);
- its own superseding snapshot, created after the local commits and before any push, as
  the publish skill's step 9 orders.

Not in it: any pin advance, any membership switch.

Reasons for the recommended treatment of the later release. Dropping the 11 rows is the
rule the membership already states, and the alternative does not keep the published
values either (section 5). The effect of the drop on `qwen3-4b` is small and leaves
direction, counts of downgrades and upgrades and the sign test unchanged (section 4.3).
Regenerating `data/model_stats.json` in the same release keeps the three statistics
files consistent with one collector output; left alone it would state 1,121 phrases
computed partly from rows no input holds.

**A risk that exists today, whatever is decided.** The publish chain runs the full
exporter. A routine full-chain publish before the owner decides D1 to D4 makes the
changes of section 6 by default, without a decision. Until the decisions are recorded,
a cycle that would publish site data should stop at the exporter's dry run and put the
section 6 list in `decisions_pending`.

## 8. Owner decisions

| | Decision | Exact change | Consequence |
|---|---|---|---|
| D1 | Drop the 11 legacy `qwen3-4b` rows | Run the re-export; set the 11 entries of `data/results_policy/legacy_payload_rows.v1.json` to `"state": "retired"` with `retired_by` naming the new snapshot | `qwen3-4b`: rows 1,152 → 1,141, unique phrases 1,121 → 1,110, mean penalty -0.0466 → -0.0470, flips 497 → 491, downgrade rate 0.1308 → 0.1324; downgrades / upgrades 65 / 14 and the sign test unchanged; payload `n_traced` 1261 → 1250. Alternative: `scripts/publication_release.py --release --models qwen3-4b` (15 parts, 317 rows; section 5), which is an expanded population and replaces the 11 values with the 2026-10-31 ones |
| D2 | Regenerate site `data/model_stats.json` in the same release | After the collector step: `python scripts/paired_stats_rigor.py --rows urgency_shift.json --site ../patientwords` (seed 7, 5,000 resamples, the defaults) | The file states the third column of the table in 4.3 and a new provenance stamp; the command also rewrites the engine's `paired_stats_rigor.json`. Without it the file keeps the 2026-08-29 values and the next snapshot's comparison lists the differences |
| D3 | Keep `qwen3-4b` described as next-token only | A reviewed change to `scripts/export_frontend_simulated.py` before the export: set a model's `traced_by_model` backend, and with it `graphs`, from all parts read for the model over the exported stamps, "logits" when any of them is a logits part, instead of from the first stamp's directory. A regression test with a first-stamp directory that holds a hosted part and an unread logits part | `models_meta.qwen3-4b.graphs` stays false and `traced_by_model.qwen3-4b.backend` stays "logits"; the payload diff of section 2 loses 2 paths. The rule gives the published `graphs` value for all four payload models (checked against the parts on disk: `gemma-2-2b` 269 hosted parts; `gemma-3-4b-it` 25 and `qwen3-1.7b` 22 logits parts; `qwen3-4b` 1 hosted and 21 logits). Without it three pages describe `qwen3-4b` as having hosted graphs |
| D4 | Accept row `(pairs_20260706T201750Z, 1)` at its hosted value | None; state it in the snapshot's change sentence | The public row shows a probability read on a leading piece of the target where it showed the whole target. A re-trace with the exact read is a new measurement and a separate owner decision |

## 9. The superseding snapshot

`study-interim-20261110` stays as it is. It records the files as they stood and says the
published `data/model_stats.json` does not reproduce.

For this release (the bug correction alone) the superseding snapshot records
`--supersedes study-interim-20261110`, `--site`, and a change sentence saying that only
`summary.penalty` of the gallery payload changed, by a correction of the phrase dedupe,
and that no input, pin, membership or other statistics file changed.
`outputs.changed_since_superseded` then holds the payload's two sha256 values and
`summary.penalty` at both site commits. `data/model_stats.json` is untouched, so the
snapshot repeats the earlier finding that it does not reproduce from the inputs.

For the later full re-export, the snapshot that supersedes that one must record:

- `--supersedes` naming the snapshot then current, and a change sentence that names
  the input change (13
  `qwen3-4b` rows of `pairs_20260706T201750Z`: 2 now read from the hosted part of
  2026-09-02, 11 no longer taken from the payload); and that the pin and the membership
  did not change;
- `--site`, so every file of the statistics set is hashed and
  `outputs.changed_since_superseded` holds `summary.penalty` at both site commits and
  the changed files (the payload, `data/urgency_shift.json`, `data/model_stats.json`);
- `--recomputed-statistics` with a file recomputed in the same run, so the record says
  whether the published `data/model_stats.json` now reproduces from the inputs. With D1
  and D2 taken it should;
- `inputs.site_payload` for the new payload, from which the collector takes no row at an
  unread key. The legacy-rows record then has 11 retired entries and the test passes
  with an empty active set.

`results_snapshot.py check-release` must pass before the pushes, and
`check-release --published --record` after them.

## 10. Found and not changed

- A hosted run rewrote a landed 13-result summary with a 2-result summary at the same
  file name on 2026-09-02. Eleven measurements left the branch (they are in git history
  at `1162e9215`). The engine rule is that landed summaries are measurements, not
  caches. Whether a hosted run can still overwrite another backend's part was not
  examined.
- `traced_by_model` and `graphs` depend on the first stamp's directory (section 4.4).
- The published payload is internally inconsistent on row `(pairs_20260706T201750Z, 2)`
  since 2026-11-06 (section 4.1). The re-export removes it.
- The local engine clone is shallow (history from `09d726eb`). Part history was read
  through the GitHub API. The date the `summary` block first reached the site could not
  be read from the site clone, whose history starts on 2026-08-27 with the block present.

## 11. Reproduce

From the engine root, with the sibling site checkout and about 1 GB free for the copy:
run the temporary-regeneration block of `verify.md`, keep the payload after each step,
and diff it against the site's file. The collector identity check is

```bash
python scripts/urgency_shift.py --frontend ../patientwords --out /tmp/u.json \
  --fallback-keys-out /tmp/keys.json
sha256sum /tmp/u.json   # 8b3068a5ffdeb1f8c9885a5e04674a1cd1fe7b5528bfa892418a158e93a42d70
```

against the published payload `5bcd3eac…` and the parts of 2026-11-10. `/tmp/keys.json`
then lists the 11 keys of section 4.2.
