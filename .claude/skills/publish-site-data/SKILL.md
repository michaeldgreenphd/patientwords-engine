---
name: publish-site-data
description: Use when new engine results need publishing to the patientwords site ("publish the data", "republish site data", section 5 of the daily cycle): runs the sanctioned exporter/collector/gate chain in order and pushes data files only — never page text.
---

# publish-site-data

Republish the public site's data payloads after new measurement results land. This is
section 5 of the daily ops cycle ("Publish data, never text"). You publish **data files
only** — the owner edits site text personally; any text edit from this chain collides
with theirs.

## Preconditions

1. Run from the engine repo root. The site must exist as the sibling checkout
   `../patientwords`. If it is missing, stop — do not clone or improvise paths.
2. `git pull --rebase origin main` in both repos first (everything lands on `main`
   since 2026-09-04).
3. The site must be a full checkout: `git -C ../patientwords sparse-checkout disable`
   before step 1 (a no-op on a full checkout). The cloud containers clone the site
   with `modes/` excluded (`docs/fresh_session_bootstrap.md`). Over that checkout the
   exporter's render prune and the seal gate cannot see the renders, so both refuse:
   the exporter stops with `refusing: the site checkout ... tracks N render(s) ...
   that are not on disk`, and `seal_check.py` exits 2. A sparse pattern that keeps
   `modes/` but hides any page or payload the exporter scans for render references
   refuses too (`... tracks N file(s) that the render-reference scan reads ...`): a
   render named only there would otherwise be pruned. The engine side needs its
   `trace_out/*/*.html` renders on disk: over a checkout that restored only the
   summaries, the exporter refuses (`... render(s) this export would publish are not
   on disk in the engine checkout ...`) rather than prune the site's copies.
4. Only run if new results actually landed (new `trace_out/*/batch_summary.part_*.json`,
   new lens parts, new txcorpus runs). No new results → no republish this cycle.
   When the only new results are parts outside the default analysis membership (a
   backfill leg, a 2026-10-09 model, a hand-authored set: `docs/open_results_policy.md`),
   run the *Catalogue-only publish* below instead of the whole chain: steps 1 to 6
   would rewrite their files unchanged.

## The chain (run in this exact order)

**1. Exporter.**
```
python scripts/export_frontend_simulated.py --frontend ../patientwords \
    --stamps <comma-list of batch stamps> \
    --archive-url https://github.com/michaeldgreenphd/patientwords-engine/releases
```
- `--archive-url` is mandatory — it keeps `payload.archive` populated so data-only rows
  link the full render sets on GitHub Releases.
- Do NOT pass `--max-renders` or `--with-pngs`. The current defaults ARE the policy
  (2026-07-21): cap 200 most consequential renders, HTML-only (`--with-pngs` would
  restore rasters — owner-instruction only).
- `--stamps`: every stamp already in `../patientwords/data/simulated_scenarios.json`
  plus newly landed ones. Omitting a published stamp silently drops its scenarios —
  never shrink the list. Since 2026-09-23 it would also delete their renders: the
  exporter prunes every `modes/simulated/pairs_*/index_NN.*` render that neither the
  new payload nor any other site file lists, and prints the count. Run it once with
  `--dry-run` first (writes and deletes nothing, lists what would go) when the count
  could surprise you; the first publish after 2026-09-23 prunes about 235 orphans.
  A `refusing:` line means nothing was written. Fix the cause it names (for a
  sparse checkout, precondition 3) and re-run; it is not success-with-no-change.

**2. Urgency collector.**
```
python scripts/urgency_shift.py --publish ../patientwords
```
Writes the site's `data/urgency_shift.json`. Until the tier vocabulary
(`data/urgency_tiers.draft.json`) passes domain review, the site's urgency-tier
content carries a label that says so. The label is data, not a fixed
string: it is the vocabulary file's `status`, published as `vocabulary_status` (in
`urgency_shift.json` and in the payload's `urgency_meta`); read it there rather than
quoting it from memory. It stays exactly as the data sets it until the vocabulary is
approved (`docs/tier_review_checklist.md`), and `claim_check.py` (step 8) ties the
pages' pending-review wording to that field through `data/claims_manifest.json`.

**3. Wired exporters — these seven ONLY, in this order** (five j-lens exporters, then
the tag-mass and J-space exporters).
```
python scripts/jlens_insights.py --site ../patientwords
python scripts/export_jlens_depth.py --block ... --exemplar-stem ... --exemplar-index ... --site ../patientwords
python scripts/export_jlens_transport.py --site ../patientwords
python scripts/export_jlens_loglens.py --site ../patientwords
python scripts/export_pair_swaps.py --site ../patientwords --depth ../patientwords/data/jlens_depth.json
python scripts/export_tag_mass.py --site ../patientwords
python scripts/export_jspace.py --site ../patientwords
```
- For `export_jlens_depth.py`, reuse the pins of the committed
  `../patientwords/data/jlens_depth.json` (same `--block` stems, same exemplar
  stem/index). Pins change only on explicit owner instruction — an ad-hoc pin change
  silently churns the published figure and breaks manifest-guarded prose.
- Exit 3 from `export_jlens_depth.py` = degenerate-exemplar refusal; the good file is
  untouched. Treat any exporter refusal as success-with-no-change. Never hand-patch a
  payload past a refusal. Exit 2 (`CONFIG ERROR`) from any exporter in this chain is
  not a refusal: stop the publish, as for `seal_check.py` exit 2.
- `export_pair_swaps.py` runs AFTER depth/insights so its `<batch>#<index>` join is
  current; new batches show target-only until it re-runs. That is expected. It
  withholds Tier B holdout rows (count in the payload's `holdout_withheld`), and exits
  2 (`CONFIG ERROR`) when the sealed set computes empty (wrong branch), or when it
  cannot read the trace-time prompts in full: no `trace_out/`; git unable to list the
  `batch_summary` parts HEAD tracks there; a part HEAD tracks for a Tier B batch that
  is not on disk (a partial or sparse checkout: restore the parts as
  `docs/fresh_session_bootstrap.md` shows, then re-run); or an unreadable part.
  Either is a config error, not a refusal — stop, as for `seal_check.py` exit 2: the
  holdout rule could not be applied. A Tier B batch with no part at HEAD and none on
  disk has not been traced on this branch, and only its accepted prompt applies.
- **Transport and loglens wired 2026-07-23 (owner option 1).** The census batch's
  25/25 `save_raw` JACOBIAN_LENS runs and its `__loglens_` LOGIT_LENS runs both landed
  on this branch, and each exporter's regen reproduced its committed site file
  byte-identically except `generated_utc` (identical census numbers, exemplars, and
  agreement counts). Both have run in the cycle since.
- **Tag mass and J-space joined 2026-07-29 (owner directive)**, after
  `export_pair_swaps.py`. Both are $0 and offline. `export_jspace.py` refuses (exit 3,
  site file untouched) when a source raw is missing: success-with-no-change, as above.

**3b. Page joins — mandatory after every export.**
```
python scripts/embed_scenario_joins.py --site ../patientwords
```
Step 1's exporter rebuilds `data/simulated_scenarios.json` from scratch and drops what
this pass adds: each scenario's `urgency` and `depth_class`, and the payload's
`urgency_meta`, `depth_model` and `featured` (the home demo, the start-here care
ladder, the redirect gallery). It joins them back from the site's
`data/urgency_shift.json` (step 2) and `data/jlens_depth.json` (step 3's depth
exporter), so it runs after both; it is idempotent. Report the `embedded:` line it
prints. 0 urgency joins or 0 depth classes means that input was absent, unreadable, or
joined nothing, which the script does not treat as an error: find out why before
pushing. Exit 3 (`refused: no payload ...`) means step 1 wrote no payload: stop. The
contract gate (step 7) allows these keys but does not require them, so it passes a
payload this step never touched while the pages fall back to their own in-page picks.

**4. Trace-URL restamp.** `python scripts/export_traces_site.py --stamp-only`
Re-stamps every scenario's `trace_url` in the payload for the self-building
patientwords-traces Pages repo (its own Action mirrors nightly at 15:00 UTC).
Stamp-only needs no traces-repo checkout.

**5. Translation at scale — only when txcorpus logits or lens readouts landed.**
`python scripts/translation_scale.py --site ../patientwords`
**Scale-framing gate (owner, 2026-07-15):** the at-scale TABLE auto-updates from data —
sanctioned. Any framing SENTENCE about the scale result is NOT: draft it, put it in the
digest and `decisions_pending`, and wait for owner approval. Never deploy it yourself.

**6. Coverage.** `python scripts/coverage_gaps.py`
Its `steer_topics` block feeds the `topics` param of the next generation fire — corpus
balance is a sampling decision, not an afterthought.

**6b. Results catalogue (added 2026-11-10; open-results policy).**
`python scripts/export_results_catalogue.py --site ../patientwords --record`
Rewrites the site's `data/results_catalogue/` (index, per-run row files, per-set
stimulus files, two CSVs) from every run under `trace_out/`, and appends the sha256 of
each part it reads for the first time to the engine's
`data/results_policy/part_ledger.v1.json`. This is how a newly landed part becomes
public: nobody approves it individually. It lists every run whatever its effect,
including partial runs and parts no analysis includes, and it never writes a row the
Tier B seal covers. Exit 2 is a config error (the seal could not be evaluated, a sparse
engine checkout, an unreadable policy): stop the publish, as for `seal_check.py` exit
2. Report its totals line. A nonzero `differ from their recorded hash` count means a
committed part changed after it was recorded: put it in `blockers`; the part is
listed as `changed_since_recorded` and its rows are withheld until it is restored.
It runs before the gates so that steps 7 and 8b check what it wrote.

**7. Contract gate.** `python scripts/validate_frontend_contract.py --site ../patientwords`
Exit 0 = holds; 1 = violations; 2 = payload missing/unreadable. Report mode (no
`--strict`) only until the next urgency publish writes `unjoinable_rows` into the site's
`data/urgency_shift.json` (step 2 writes it; until then the orphan-row warning is
expected). After that publish, including step 7 of that same run, add `--strict`, so
any warning fails the gate. New ERRORS mean an export broke the
page contract: fix the export and re-run before pushing the site. Never push over errors.

**8. Claim gate.** `python scripts/claim_check.py`
Exit 1 = refreshed data invalidated a hardcoded sentence on the site. Do NOT edit the
prose. Put the exact FAIL line in the digest headline and in `decisions_pending`; the
owner (or the orchestrating session, which holds text-edit sanction) rewrites it. A
`warn:` line means prose was edited and the manifest needs updating — flag it the same
way, do not fix it here.

**8b. Holdout-seal gate (mandatory — also before any ad-hoc export push).**
`python scripts/seal_check.py --site ../patientwords` — exit 0 required to proceed.
Exit 1: ABORT the publish, follow the holdout-seal-check skill's breach protocol.
Exit 2: a config error, never a pass. The printed line names the cause: an empty
sealed set (wrong branch), a malformed `data/seal_allowlist.json` (fix the entry;
never delete the file to get past it), or a sparse site checkout (precondition 3).

**9. Release: commit locally, snapshot, check, then push.**
Nothing is pushed before step 9e passes. The site push (9g) is the publication: GitHub
Pages serves the site's `main`. The order below keeps a published statistic from
existing without its version record. *Recovery* (below) says what each failure leaves
and how to continue.

**9a. Engine commit, local.** Commit the chain's engine-side outputs (`ops/*.json`,
`data/jlens_*.json`, and `data/results_policy/part_ledger.v1.json` when step 6b recorded
new hashes). Do not push.

**9b. Site commit, local.** `git -C ../patientwords status` first. Only `data/*.json`,
the catalogue's files under `data/results_catalogue/`, and exporter-written
`modes/simulated/` render files may have changed (added, modified, or deleted by the
prune or the catalogue export). Anything else changed → abort, revert, investigate.
Stage render deletions too (`git -C ../patientwords add -A data modes/simulated`), or
the pruned files stay published. Commit. Do not push. The contract, claim and seal
gates above are the last check of the content; steps 9c to 9e check that the release
is recorded.

**9c. Snapshot — required whenever ANY published statistics file changes.**
The published statistics set is `STATISTICS_FILES` in `scripts/results_snapshot.py`,
the one definition. It holds every site data file that carries a measured or computed
number: the gallery payload `data/simulated_scenarios.json` (its `summary.penalty`
block is a published statistic, and it can change when `data/urgency_shift.json` does
not), `data/urgency_shift.json`, `data/model_stats.json`, the lens and J-space files
of step 3, `data/translation_scale.json`, and the owner-run advice, Petri and Jev
payloads. A run of the whole chain normally changes at least the payload, so it
normally needs a snapshot. When unsure, go to 9e: it names every changed statistics
file the current snapshot does not cover.
After a re-export that removes a row declared in
`data/results_policy/legacy_payload_rows.v1.json`, set that entry's state to
`"retired"` with `retired_by` naming the new snapshot, in the same engine commit as the
snapshot; `tests/test_legacy_payload_rows.py` fails until then.
```
python scripts/results_snapshot.py create --id study-interim-<UTC date> \
    --supersedes <the id `results_snapshot.py list` marks current> --site ../patientwords \
    --change "<one sentence: what landed or changed since the previous snapshot>"
```
It writes a new immutable file under `data/analysis_snapshots/` and changes no
published number. It records the sha256 of every file of the statistics set as
committed in the site, which of them changed since the superseded snapshot, and the
payload's `summary.penalty` block at both site commits, read from git. It refuses
(exit 2, `refused, nothing written`) inputs that are not committed (untracked parts
included), site statistics files that differ from the site's HEAD, an existing id
(a second snapshot on one date takes a letter suffix), an id that does not supersede
the current snapshot of its membership, and a directory holding a file the index does
not list. It reads the committed policy whatever `PW_RESULTS_POLICY` says. It does not
recompute the statistics (`--recomputed-statistics` records a comparison when the
owner has recomputed `model_stats.json`). Never edit or delete a landed snapshot.

**9d. Snapshot commit, local.** Commit the new snapshot file and
`data/analysis_snapshots/index.json` in a second engine commit. Do not push.

**9e. Release check.**
```
git -C ../patientwords fetch origin main
python scripts/results_snapshot.py check-release --site ../patientwords
```
Exit 0 is required before any push. It reads both repositories and pushes nothing.
It refuses (exit 1, one `REFUSED:` line per problem) unless: the engine tree is clean
under the snapshot's inputs; the snapshot file and the index are committed; the
snapshot is the current one of its membership and verifies; the engine commit it
records is an ancestor of the engine HEAD; the site has no uncommitted change under
`data/` or `modes/simulated/`; every file the snapshot records has the recorded sha256
in the site's HEAD commit; every published statistics file this release changes
(relative to the fetched `origin/main`) is recorded by the snapshot; and no changed
data file is unclassified. An unclassified file is one that is in neither
`STATISTICS_FILES` nor the commented lists of files a snapshot does not version; do
not classify it yourself: put the `REFUSED:` line in `blockers` and stop. Report the
manifest it prints (engine commit, site commit, snapshot id, each output's sha256) in
the digest. `--json` prints the same manifest as JSON.

**9f. Engine push.** `git push origin main`. If it is rejected, bring the remote in
with a merge, `git pull --no-rebase origin main` (keep the target's trigger files, as
the fire-trigger-safe skill says for any merge), never with a rebase: the snapshot
records the engine commit it was created at, and a rebase replaces that commit. Then
run 9e again and push.

**9g. Site push — the publication.** `git -C ../patientwords push origin main`. If it
is rejected, `git -C ../patientwords pull --rebase origin main`, run 9e again, then
push. The rebase changes the site commit's id; the snapshot's recorded sha256 values
bind the release, and 9e compares them at the new HEAD.

**9h. Post-publication check.**
```
python scripts/results_snapshot.py check-release --site ../patientwords --published --record
```
It fetches both remotes and exits 1 unless the remote site branch holds every recorded
file with the recorded sha256 and the remote engine branch holds the snapshot. On
success `--record` appends a publication record (snapshot id, published site commit,
time) to `data/analysis_snapshots/index.json`; commit that file and push the engine.
The snapshot file is not edited. A snapshot with no publication record was created
and not published: `results_snapshot.py list` shows `(no publication recorded)`.
Exit 1 goes in `blockers` with its `REFUSED:` lines.

## Catalogue-only publish

For a cycle whose only new results are parts outside the default analysis membership
(precondition 4). Run, in order: step 6b, step 7, step 8, step 8b, then steps 9a, 9b,
9e, 9f, 9g and 9h without `--record`. Nothing else. It needs no new snapshot: the
statistics files do not change in such a cycle, because the collectors behind them
read under `study-interim/1`, and the results catalogue is not versioned by a
snapshot. Step 9e passes against the current snapshot and prints
`published statistics files this release changes: 0`; step 9h confirms that the
published statistics files still have the bytes the current snapshot records. If
step 9b's `git status` shows a change outside `data/results_catalogue/`, abort and
investigate.

## Recovery

A snapshot is never edited or deleted to recover. A release that did not complete is
continued, or its snapshot is superseded by the next one and keeps no publication
record.

| What failed | State it leaves | Continue | Undo |
|---|---|---|---|
| A gate stops the publish (step 7 errors, step 8b exit 1 or 2, an exporter's exit 2) | Nothing committed. The site working tree holds the chain's writes. | Fix the cause in the engine and run the chain again from step 1. | `git -C ../patientwords checkout -- data modes/simulated`, then `git -C ../patientwords clean -fd data modes/simulated` for new files. Leave the engine's ledger additions: they are true whether or not the publish completes. |
| 9c `create` refuses (exit 2) | Commits 9a and 9b are local. No snapshot file was written. | Fix the cause the message names and run 9c again. | `git -C ../patientwords reset --hard origin/main` drops the local site commit. Nothing was published. |
| 9c `create` is interrupted | Possibly a snapshot file the index does not list; `results_snapshot.py list` prints `NOT INDEXED`. | Remove that one file, then run 9c again. | The same removal. |
| 9e `check-release` exits 1 | Everything is local. Nothing was pushed. | Fix what each `REFUSED:` line names and run 9e again. A recorded file with another sha256, or a changed statistics file the snapshot does not record: run 9c with `--supersedes <the snapshot just created>`, then 9d. | None needed. The unpublished snapshot stays in the index with no publication record. |
| 9f succeeds, 9g fails | The engine remote holds a snapshot whose bytes are not published. `list` shows `(no publication recorded)`; `check-release --published` exits 1 and names the files. | Run 9g again (its rejected-push steps), then 9h. | If the publish is abandoned: `git -C ../patientwords reset --hard origin/main`, then 9c with `--supersedes <the unpublished snapshot>` and a change sentence saying the release was abandoned, 9d, 9e, 9f. The current snapshot then describes the published site again. |
| 9g is rejected because the remote moved | The local site commit must be rebased, and its id changes. | `git -C ../patientwords pull --rebase origin main`, 9e, 9g. The recorded sha256 values bind the release; the publication record of 9h stores the published commit id. | As the row above. |
| Another publish changed a recorded file | Before the pull 9e says `origin/main changed the published statistics file ...`; after it, `... at the site HEAD has sha256 ...`. | Supersede: 9c with `--supersedes <the snapshot just created>`, 9d, 9e, then push. If the rebase stops on a conflict in an engine-written file, `git -C ../patientwords rebase --abort`, `git -C ../patientwords reset --hard origin/main`, and run the chain again from step 1; never resolve such a conflict by hand. | None. |
| The engine merge of 9f conflicts in `data/analysis_snapshots/index.json` | Two sessions created snapshots at once. | `git merge --abort`, stop, and put it in `blockers`: the owner decides which release stands. | None from this chain. |
| 9h exits 1 after both pushes | The published bytes differ from the snapshot (another publish landed after 9g). | `git pull` in both repositories, then 9c (superseding) to 9h on the published state. | None. |

`results_snapshot.py verify` (exit 1) means a recorded part changed or went missing,
the current snapshot no longer describes the checkout (the pin, the tiers file or the
membership rule changed without a superseding snapshot), or a snapshot file is not
indexed: put it in `blockers`. In a shallow engine checkout whose history ends before
the snapshot's commit, 9e says so and names the remedy (`git fetch --deepen=<n>`).

## Never

- Never edit page HTML, page text, figures, or labels — data files only, without exception.
- Never publish a scale-framing sentence, or any new prose, without explicit owner approval.
- Never remove or soften the urgency-tier review label. It comes from
  `vocabulary_status` in the data (step 2), and only the vocabulary's approval changes it.
- Never hand-edit an exported payload, invent a number, or patch past an exporter refusal.
- Never change depth-exporter pins or render-cap/PNG defaults without owner instruction.
- Never let holdout phrase text reach any output or committed file.
- Never run `scripts/publication_release.py --release` from this chain while
  `analysis_pin.auto_advance` is false in `data/results_policy/policy.v1.json`, never
  set `PW_RESULTS_POLICY`, and never edit the policy file, the ledger or a snapshot by hand.
