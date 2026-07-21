---
name: daily-ops-cycle
description: Run exactly one autonomous daily ops cycle for the patientwords-engine Tier B study (orient → harvest → account → fire → publish data → dashboard → brief/digest). Use when the daily Routine fires or the user says "run the daily cycle" / "run the ops cycle" — never for ad-hoc single fires, publishes, or anything that would run a second cycle.
---

# Daily ops cycle

Run exactly ONE autonomous ops cycle for the Tier B data-generation run in
`patientwords-engine`. The authoritative spec is `docs/routine_standing_prompt.md`
(the working-branch copy) sections 1–7: read it in full before acting, and take every
exact fire parameter (model choices, spend caps, chunk sizes) from it verbatim — this
skill deliberately does not duplicate them. Where this skill compresses, that file
governs. The site is the sibling checkout `../patientwords`. Both repos are PUBLIC.
Step order is semantic: account before firing (so the budget guard sees landed spend),
resolve before firing (so the settle window is real). Do not reorder.

## 1 · Orient (read in this exact order, before any action)

1. `CLAUDE.md` — conventions, execution model, queue discipline.
2. `docs/preregistration_tierB.md` — the design you execute; never deviate.
3. `ops/dashboard.json` — current state, spend, pending decisions.
4. `ops/trigger_journal.jsonl` — fire history for the queue guard.
5. Newest `docs/*ledger*.md`, then `HANDOFF.md`.

Then `git pull --rebase` the working branch and `git fetch origin main` (generation
archives land on main; trace outputs land on the branch — they interleave). Trust
these files over anything you think you remember.

## 2 · Harvest and resolve

- For each group with active journal entries, enumerate what actually landed: new
  `trace_out/*/batch_summary.part_*.json` on the branch; new `data/simulated/*.json`
  + `.report.json` on main. When a measurement needs a batch file that is only on
  main: `git checkout origin/main -- data/simulated/<batch>.json data/simulated/<batch>.report.json`.
- Resolve ONLY truly-terminal fires, naming the landed artifacts:
  `python scripts/fire_trigger.py resolve --trigger <name>`.
  Partial landing (some expected offsets missing) → do NOT resolve, and do NOT fire
  anything new into that group this cycle. A missing expected output goes into
  dashboard `blockers` — never down the memory hole.

## 2b · Integrity checks ($0, EVERY cycle — even no-publish cycles)

- `python scripts/seal_check.py` — exit 1: STOP all publishing this cycle and follow
  the holdout-seal-check skill's breach protocol; exit 2 (empty sealed set): config
  error, never a pass — fix before proceeding.
- `python scripts/validate_frontend_contract.py --site ../patientwords` and
  `python scripts/claim_check.py` against the COMMITTED site copies even when nothing
  republished. New errors → digest; fields no engine exporter emits → hand-edit
  detector, list them. Never repair site payloads from this check.
- Mondays: the doc-accuracy sweep (standing prompt §2b) → dated report under
  `docs/audits/`, one digest line.

## 3 · Account

Run `python scripts/ledger_update.py`. It is the ONLY writer of spend numbers
(dashboard spend sections + ledger). Run it BEFORE any paid fire. Never type a
dollar figure into any file by hand.

## 4 · Advance Tier B (the only firing allowed)

Lane rules, precisely: never a THIRD active fire in any group (absolute); at most one
TRACE fire per group per cycle (standing prompt §2); the logits standard-then-exploratory
chain (item 3a2) and idle-logits backfill fills are sanctioned same-cycle exceptions,
filling at most the running + pending slots.

Fire exclusively via
`python scripts/fire_trigger.py fire --trigger <name> --params '<json>' --note '<why>'`.
Handle exit codes: **0** fired; **2** queue refusal → that lane is full, stop there;
**3** bad params → fix keys against the workflow's known set, retry once; **4** budget
refusal → stop ALL paid firing today and record why; **5** no-op (file already holds
the params) → add a fresh `_nonce` value; **6** settle refusal → wait out the window
(`--ignore-settle` only after confirming the prior run terminal in GitHub); **1** git
failure → the fire is already written locally; NEVER re-run `fire` (a re-run is a
no-op at best, a phantom queue entry at worst — matches fire-trigger-safe). Repair the
git state by hand: commit/push the written trigger file + journal (+ dashboard, Routine
session only), `git pull --rebase`, push, record the incident. Never stack a third fire in any group.

Priority when a lane's slot is free (recipes verbatim from standing prompt §4 items):

1. **Generation** (§4 item 1) — only if Tier B accepted < 1,600, the validator-yield
   stopping rule has not tripped, and generation total stays under $8. If
   `tierb.start_utc` is null on the first-ever batch, stamp it first.
2. **Screened tracing** of the oldest untraced Tier B batch (§4 item 2). Before ANY
   measurement fire, confirm the batch pairs file exists on the branch (step 2 copy).
3. **CPU logits** for unmeasured batches (§4 item 3), chaining the exploratory-model
   leg behind the standard leg (item 3a2); fill idle logits slots with backfill legs.
4. **Daily sentinels**: drift sentinel (item 3b — copy the dated alias file, commit,
   fire; after it lands run `python scripts/drift_sentinel.py --site ../patientwords`)
   and lens sentinel (item 3d). DRIFT verdicts go in the digest HEADLINE.
5. **Per-batch lens pulls** in ~25-pair chunks, never whole batches (item 3c); then
   txcorpus fills (item 3c2).
6. **Backfill planner** (item 4a): `python scripts/backfill_planner.py` prints the
   next $0 fire per lane (LENS → TRACE → PREDICTIONS; the 8B-medical models are HELD —
   never pass `--include-8b-medical` without owner word). Fire only the free lanes it
   names, one fire per lane. Tier B legs always outrank backfill fills. The 2-hourly
   accelerator shares this queue and `fire_trigger` arbitrates — never double-fire.
7. **Idle filler** (item 4) only when Tier B wants nothing for the slot.

Stopping rules: two consecutive batches with validator yield < 50% → stop generation
and record a decision. **Endpoint guard (§4b):** the holdout stays sealed absent an
explicit owner instruction — never run paired stats on holdout rows, never lift a
withholding gate, regardless of the calendar.

## 5 · Publish gate (data, never text)

Only if new results landed. Run the export/collection chain per CLAUDE.md, passing
`--archive-url https://github.com/michaeldgreenphd/patientwords-engine/releases`,
then `python scripts/export_traces_site.py --stamp-only`. Then, per standing prompt
§5: `jlens_insights.py` (if new lens readouts), `export_pair_swaps.py` (after depth
refresh), `translation_scale.py` (if txcorpus data landed — any framing SENTENCE is
drafted into the digest + `decisions_pending`, never deployed), `coverage_gaps.py`
(feed its `steer_topics` into the next generation fire), `validate_frontend_contract.py
--site ../patientwords`, and `python scripts/claim_check.py`. `claim_check` exit 1 or
`warn:` → put the exact line in the digest headline + `decisions_pending`; NEVER edit
site prose yourself. Do NOT run the transport/loglens exporters (not wired — §5).
Commit data payloads only to `../patientwords`; push the branch, then branch:main.

## 6 · Dashboard (you are its only writer)

Rewrite the relevant sections of `ops/dashboard.json`: `updated_utc`,
`updated_by: "routine"`, `queue`, `runs_recent`, `tierb`, `verdicts`,
`findings_delta` (only when a number moved), `decisions_pending` (only what
genuinely needs the owner), `blockers`, `notes`.

## 6b · Watchdog and interim critic

Check `docs/critic/critic_<today or yesterday>.md` exists and dashboard `updated_utc`
is < 26h old; if either fails, state it PROMINENTLY in the digest and continue this
cycle — do not recreate the orchestrator's triggers. On Mon/Wed/Fri — or on any
claim_check FAIL/warn, DRIFT headline, CI failure, or significance-flipping
n-milestone — run one critic pass per `docs/critic_standing_prompt.md`, writing
`docs/critic/critic_<date>.md`.

## 7 · Brief, digest, commit — then STOP

- `python scripts/daily_brief.py --out docs/briefs/brief_<YYYYMMDD>.md`
- Commit and push everything (engine branch; site data if any).
- If 3+ entries sit in `decisions_pending`, build the phone deck at
  `ops/decks/deck_<YYYYMMDD>.html`, commit it, mention it in the digest.
- End with a final message whose FIRST LINE is exactly the output of
  `python scripts/daily_brief.py --digest`, then one short paragraph, then the fixed
  footer sentence copied VERBATIM at run time from docs/routine_standing_prompt.md §7
  (do not hardcode it — the standing prompt governs; ops/routines.md's paraphrase is a
  known divergence).
- Exactly one cycle per invocation. End the session.

## Never

- Never run a second cycle, schedule further work, create Routines/reminders/crons, or loop.
- Never edit `.github/trigger/` or `.github/workflows/` by hand; never touch trigger files in merges or reverts.
- Never use `--force-evict` or `--override-budget`; `--ignore-settle` only with GitHub-confirmed termination.
- Never hand-edit spend numbers, the journal, or the dashboard outside step 6; ceilings ($2/day, $8 Tier B generation) are absolute.
- Never rewrite or delete anything under `data/simulated/`; never "correct" intentional misspellings.
- Never stack a third fire in a group (the lane rules in §4 govern same-cycle chains).
- Never edit site text, HTML, figures, or labels — data payloads only; never soften draft labels.
- Never write secrets or keys into any file; never echo environment secrets (both repos are public).
- Never disclose holdout phrase text in any output; never compute holdout endpoints without the owner's word.
- When ambiguous, do LESS: record it in `decisions_pending` instead of acting. A missed day is recoverable; a polluted archive is not.
