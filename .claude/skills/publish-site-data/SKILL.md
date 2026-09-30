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
  payload past a refusal.
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

**7. Contract gate.** `python scripts/validate_frontend_contract.py --site ../patientwords`
Exit 0 = holds; 1 = violations; 2 = payload missing/unreadable. Report mode (no
`--strict`) until F-M27's orphan-row trim lands. New ERRORS mean an export broke the
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

**9. Commit and push.**
- Site: `git -C ../patientwords status` first. Only `data/*.json` and exporter-written
  `modes/simulated/` render files may have changed (added, modified, or deleted by the
  prune). Anything else changed → abort, revert, investigate. Stage render deletions
  too (`git add -A data modes/simulated`), or the pruned files stay published. Commit
  and push `main`; GitHub Pages serves it, so this push is the publish — the contract,
  claim and seal gates above are the last check.
- Engine: commit the chain's engine-side outputs (`ops/*.json`, `data/jlens_*.json`)
  to `main`; `git pull --rebase` before pushing.

## Never

- Never edit page HTML, page text, figures, or labels — data files only, without exception.
- Never publish a scale-framing sentence, or any new prose, without explicit owner approval.
- Never remove or soften the urgency-tier review label. It comes from
  `vocabulary_status` in the data (step 2), and only the vocabulary's approval changes it.
- Never hand-edit an exported payload, invent a number, or patch past an exporter refusal.
- Never change depth-exporter pins or render-cap/PNG defaults without owner instruction.
- Never let holdout phrase text reach any output or committed file.
