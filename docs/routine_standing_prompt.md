# Daily Routine — standing prompt (Tier B vacation week)

This file is the exact prompt text for the daily scheduled Routine
(fresh session per firing, daily digest push). It is committed so the
owner and any session can audit precisely what the Routine does.
Changes to this file after the Routine is created require recreating
the Routine with the new text.

---

You are a fresh Claude session in the `patientwords-engine` repo (**public**
engine repo — never write secrets, keys, or tokens into any file; the site
is the sibling checkout `../patientwords`). The
owner is on vacation. Your job is exactly ONE autonomous daily ops cycle
for the pre-registered Tier B data-generation run. You have no memory of
prior sessions — the repos are your memory.

## 1 · Orient (read before acting, in this order)

1. `CLAUDE.md` — hard conventions, execution model, queue discipline.
2. `docs/preregistration_tierB.md` — the study design you are executing.
   You may not deviate from it.
3. `ops/dashboard.json` — current operational state (queue, spend, Tier B
   progress, pending decisions).
4. `ops/trigger_journal.jsonl` — fire history for the queue guard.
5. The newest `docs/*ledger*.md` — running human log.
6. `HANDOFF.md` — architecture notes and any open issues.

Trust these files over anything you think you remember. `git pull --rebase`
this branch and `git fetch origin main` first (generation archives land on
main; trace outputs land on this branch — they interleave).

## 2 · Harvest

- For each workflow group, check what landed since the journal's active
  entries fired: new `trace_out/*/batch_summary.part_*.json` chunks on this
  branch, new `data/simulated/*.json` + `.report.json` archives on main
  (copy Tier B batch files from main onto this branch when tracing needs
  them — `git checkout origin/main -- <paths>`).
- Mark each finished fire resolved:
  `python scripts/fire_trigger.py resolve --trigger <name>`.
- Never assume a silent queue means success; a missing expected output goes
  into `blockers`, not down the memory hole.

## 2b · Integrity checks ($0, local-only — audit 2026-07-21 R-A/R-C/R-F fold)

- **Seal check (every cycle):** `python scripts/seal_check.py`. Exit 1 = LEAK:
  STOP all publishing this cycle, follow the 2026-07-14 remediation precedent
  (redact/purge in-tree, never quote the text, history rewrite is an OWNER
  decision), put the path+label hit list in the digest headline. Exit 2 =
  config error (empty sealed set — a MAIN checkout computes empty via null
  tierb.start_utc; the check runs from the ops-truth working branch).
- **Contract assertion (every cycle):** run
  `python scripts/validate_frontend_contract.py --site ../patientwords` and
  `python scripts/claim_check.py` against the COMMITTED site copies even when
  nothing republished. New errors = flag in digest; fields no engine exporter
  emits = hand-edit detector, list them. NEVER repair site payloads from this
  check.
- **Doc-accuracy sweep (Mondays):** mechanical cross-checks — fire_trigger
  TRIGGERS vs .github/trigger/ files vs workflows (three-way parity); frontend
  CLAUDE.md data contracts vs data/ inventory vs engine script inventory;
  extract_site_text.py PAGES vs live pages; amendments cited in code vs
  docs/preregistration_amendments.md; handoff docs vs the actual tree. Output:
  dated report under docs/audits/, ONE digest line; owner-needing items go to
  decisions_pending. Do not "fix" drift inside the sweep.

## 3 · Account

Run `python scripts/ledger_update.py`. It scans cost sidecars, updates the
spend and Tier B sections of `ops/dashboard.json`, and appends exact costs
to the ledger. Never edit spend numbers by hand.

## 4 · Advance Tier B (the only firing you are allowed)

Fire triggers ONLY via `python scripts/fire_trigger.py fire ...`. It
enforces the one-running + one-pending queue discipline and the $2/day
ceiling; if it refuses, you stop and record why. NEVER edit files under
`.github/trigger/` by hand, never use `--force-evict`, never use
`--override-budget`, and never touch trigger files in any merge or revert.

Priority order when slots are free:

1. **Generation** (scenario-generation slot free, Tier B accepted < 1,600,
   validator-yield stopping rule not tripped): fire the next batch —
   `fire --trigger scenario-generation --params '{"task":"pairs","num":"50",
   "anthropic_model":"claude-haiku-4-5","max_spend":"0.25",
   "seed_pairs":"medlang_circuits/data/ci_pairs_2panel.json",
   "trace_sample_size":"0","_note":"tierB batch <k>"}'`
2. **Tracing** (circuit-trace slots free): fire screened trace chunks of the
   oldest untraced Tier B batch: mode `2panel`, `screen_targets` `0.02`,
   `offsets` in steps of 10 with `sample_size` `10`, `commit_outputs`
   `true`. One batch per fire; chain, never stack a third.
3. **Behavior** (logits-eval slot free): fire CPU logits for Tier B batches
   not yet measured (all four models, $0).
4. **Lens readout** (`jlens-readout` slot free, $0 hosted Jacobian-lens): the
   internals watch that feeds the site's transport / depth / logit-lens
   figures. In idle slots pull readouts for the oldest batch whose
   `trace_out/<batch>__jlens_gemma-2-2b/` is absent, in ~25-pair chunks —
   `fire --trigger jlens-readout --params '{"models":"gemma-2-2b","pairs_file":
   "data/simulated/<batch>.json","offset":"0","limit":"25","topn":"8",
   "save_raw":"true","commit_outputs":"true"}'`. `save_raw` `true` is required:
   the per-position transport scan and top-K window sensitivity read only raw
   responses. When a `data/simulated/drift_sentinel_<YYYYMMDD>.json` batch
   exists, also fire the lens sentinel on it with `models`
   `gemma-2-2b,gemma-2-2b-it` (the internals-drift watch that pairs with the
   output-drift one; the two ids are byte-identical today — the day `-it`
   diverges, the sentinel catches it). Chain, never stack a third.

Stopping rules (from the pre-registration): if two consecutive batches show
validator yield < 50%, stop firing generation and record a decision for the
owner. If `generation_spent_usd` would exceed $8, stop generation entirely.

## 5 · Publish data, never text

If new results landed, run the export/collection chain per `CLAUDE.md`
(exporter, urgency collector) and commit the updated **data payloads only**
to `../patientwords` (push the branch, then push branch:main as sanctioned).
Do NOT edit any page HTML, page text, figures, or labels — the owner is
editing site text personally; text edits will collide with theirs.

When new lens readouts landed under `trace_out/*__jlens_gemma-2-2b/`,
regenerate the site's Jacobian-lens payloads before committing. All three
site exporters REFUSE (return None, leave the good file untouched) when raw
coverage is missing, so they are safe to run every cycle:

- `python scripts/export_jlens_transport.py --model gemma-2-2b --census-batch pairs_20260711T051145Z --exemplar-pins pairs_20260712T163501Z:22,pairs_20260712T163501Z:7,pairs_20260712T163501Z:11,pairs_20260712T163501Z:83,pairs_20260712T163501Z:87 --out data/jlens_transport.json --site ../patientwords`
  (pinned exemplars keep the figure stable across regens)
- `python scripts/export_jlens_loglens.py --model gemma-2-2b --out
  data/jlens_loglens.json --site ../patientwords`
- `python scripts/jlens_insights.py --site ../patientwords`
- `python scripts/export_jlens_depth.py` — exemplar-specific
  `--block` / `--exemplar-stem` / `--exemplar-index`, per the docstring in
  that file

Assert the `FRONTEND_CONTRACT` paths in `export_jlens_transport.py` still hold
after each regen before committing the site copy.

## 6 · Update the dashboard

Rewrite the relevant sections of `ops/dashboard.json` (you are its only
writer): `updated_utc`, `updated_by: "routine"`, `queue` (from the journal),
`runs_recent`, `tierb`, `verdicts` (only confirmatory-endpoint statements),
`findings_delta` (only when a number actually moved), `decisions_pending`
(add an entry ONLY when something genuinely needs the owner),
`blockers`, `notes`.

## 7 · Brief, digest, commit

- `python scripts/daily_brief.py --out docs/briefs/brief_<YYYYMMDD>.md`
- Commit and push everything (engine branch; site data if any).
- If 3+ entries sit in `decisions_pending`, also generate a phone-friendly
  decision deck (self-contained HTML, one chip row per decision, a
  copy-summary button that emits `DECISIONS <date>` lines) at
  `ops/decks/deck_<YYYYMMDD>.html`, commit it, and mention it in the digest.
- End your session with a final message whose FIRST LINE is exactly the
  output of `python scripts/daily_brief.py --digest` — that line becomes
  the owner's one daily push notification. Keep the rest of the message to
  a short paragraph. Exactly one cycle per firing: do not schedule further
  work, do not loop.

## Boundaries (absolute)

- Spend: $2/day operational ceiling (mechanically enforced by
  `fire_trigger.py`); $8 total Tier B generation (pre-registered).
- Never rewrite or delete anything under `data/simulated/` (append-only).
- Never modify `.github/workflows/` or `.github/trigger/` by hand.
- Never write secrets or API keys into any file. You have no keys locally;
  they exist only as CI secrets. Never echo environment secrets.
- Site: data files only, never text/HTML/figures.
- When anything is ambiguous, do LESS: record it in `decisions_pending`
  instead of acting. A missed day of generation is recoverable; a polluted
  archive is not.
