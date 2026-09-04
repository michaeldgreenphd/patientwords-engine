# Operator's handbook — PatientWords ops

Written 2026-08-29, at the close of the active-measurement phase, as the
institutional memory of the long-running ops sessions. Audience: any future
session or human maintaining this repo. `CLAUDE.md` states the conventions;
this book is the *procedures and case law* — what actually breaks and the
exact drills that fix it. When this book and observed reality disagree,
trust reality, then fix the book.

## 1 · The system in one paragraph

Two public repos: `patientwords-engine` (measurement + ops) and
`patientwords` (presentation-only site), sibling checkouts, both worked on
branch `claude/gemma-clinical-colloquial-interp-mavx04` (the ops branch;
site `main` is the live GitHub Pages). Nothing paid or networked runs
locally — every job goes through push-to-run CI: changing a file under
`.github/trigger/` on any pushed branch fires its workflow. All firing goes
through `scripts/fire_trigger.py`, which journals to
`ops/trigger_journal.jsonl` and enforces queue + budget discipline. A
scheduled Routine ("Patient words operation cycle") runs maintenance
cycles per `docs/routine_standing_prompt.md` (MAINTENANCE MODE since
2026-08-29, with a self-throttling cadence gate).

## 2 · State as of 2026-08-29

- Every measurement axis is COMPLETE: six claim-grade models at 39/39
  batches (`docs/coordination/backfill_8b_complete_20260826.md`); gemma
  trace and j-lens axes done; Tier B generation done (endpoint pending
  owner sign-off).
- **All eight trigger lanes are PARKED** (`fire_trigger.py park`): each
  trigger file's resting content is a cheap no-op, so merges, rebases, and
  branch creations that touch them re-run pennies, not the last expensive
  fire. Keep it that way: after any real fire lands, re-park that lane.
- Paid programs closed: Ox Alpha done ($0.53 total), backfill done, the
  56-pair terminology batch elicited + judged ($0.30 total).
- Open owner items: clinician review (`docs/review_packet_clinician.md`),
  pre-registration signature, confirmatory Tier B holdout run (one-shot —
  only on explicit owner instruction), full-grid elicitation of the 56.

## 3 · Standard operating procedures

**Fire.** `python scripts/fire_trigger.py fire --trigger <t> --params
'<json>' --note '<why, with settle-bypass evidence if used>'`. Params must
match the workflow's key set exactly (the tool hard-errors on unknown
keys); `commit_outputs` must be stated wherever supported. Paid fires
(scenario-generation, model-evaluation, advice-eval) happen ONLY on the
owner's explicit words in a live chat, with `max_spend` matching the quote.

**Queue.** One running + one pending per lane; a third push silently
evicts the pending run. Chain fires, never stack. After a `resolve`, a
same-lane fire inside the 15-min settle window is refused; pass
`--ignore-settle` only with GitHub-confirmed terminality named in the note.

**Harvest → verify → resolve.** Pull; verify each landed output
substantively (part index ranges, counts, penalties/tiers present, sidecar
cost); confirm the run terminal on GitHub
(`mcp github actions_list` on the workflow yml) or via committed outputs;
then `resolve --trigger <t>` (oldest first). **Never `resolve --all`
without checking each active entry individually** — see §5, the
2026-08-26 mis-resolve.

**Re-park.** After a lane's real work lands and resolves:
`python scripts/fire_trigger.py park --trigger <t> --ignore-settle`
(terminality just confirmed). `park --all` exists for cold starts.

**Publish site data.** Only the sanctioned exporter chain (site
CLAUDE.md's data-contract table names every writer); then
`python scripts/validate_frontend_contract.py --site ../patientwords`
(0 errors required) and `python scripts/seal_check.py --site
../patientwords --extra docs,ops` (CLEAN required) before pushing. Data
payloads only — never page text. Merges to site `main` publish live.

**Merging branches.** Any push that changes a trigger file fires its
workflow — merges included, and "changes" includes a file appearing on a
ref for the first time. Restore the TARGET branch's trigger files before
committing any merge. Parks make the blast radius pennies, not dollars,
but the rule stands.

## 4 · Degradation drills (verbatim)

**Git pull hangs** (chronic in remote containers, ~50% of attempts in
2026-08): run `timeout 110 git pull --rebase origin <branch>` with a
process timeout; on kill, check `.git/rebase-merge`/`.git/rebase-apply`
for a stuck rebase (none = the kill was clean), confirm the cwd is the
repo (a killed compound command resets the shell cwd), and retry ONCE.
Still failing → verify remote state through the GitHub API instead and
retry the pull next pass. Never stack retries in a loop.

**"fire written locally but git publish failed" (exit 1):** the trigger
file, journal entry, and commit already exist locally. NEVER re-fire —
`git pull --rebase`, resolve any conflicts per the rules below, `git push`.
The fire then publishes and the workflow runs once.

**Journal conflict** (`ops/trigger_journal.jsonl`): ORDERED UNION — take
both sides (`git show :2:` / `:3:` during a rebase), dedupe on
`(fired_utc, trigger)` preferring the REMOTE copy, sort by `fired_utc`,
verify every line parses as JSON, write, `git add`, continue. THEN RECHECK
the merged journal for revived-but-terminal entries (the remote's
pre-resolve copy can resurrect an entry you already resolved — observed
live once) and re-resolve them.

**Dashboard conflict** (`ops/dashboard.json`): keep the Routine's side
wholesale — it is the single writer. After any manual op, run
`git checkout -- ops/dashboard.json` so stray local queue-view edits never
enter a commit.

**Verification fallback:** when git is degraded, GitHub API run listings
(status/conclusion) plus `get_file_contents` substitute for local pulls;
say in any record which evidence was used.

## 5 · Incident case law (read before repeating history)

- **2026-07-09 queue eviction:** resolving on partial landing let a new
  fire silently supersede a pending run → the settle window exists.
- **2026-07-12 batch-7 failures:** generation archives land on `main`,
  measurement checks out the branch — copy pairs files across
  (`git checkout origin/main -- data/simulated/<batch>*.json`) before any
  measurement fire.
- **2026-08-23 anthropic SDK `temperature` removal:** two $0 failed runs;
  fixed at the `_send` seam in `scripts/advice_eval.py` with
  retry-without + regression test. Pattern: SDK breakage fails fast and
  cheap; fix the seam, add the test, re-fire.
- **2026-08-22→25 Neuronpedia graph outage:** endpoint-specific 500s, four
  permanent sentinel holes; the j-lens control on the same host/key proved
  it upstream. Rule: no same-day retries; a hole is a record, not a bug to
  fix. Recovery question for the vendor: did the backend change (baseline
  annotation), not just "is it up".
- **2026-08-26 mis-resolve:** a `resolve --all` swept an IN-FLIGHT entry
  another session (the Routine) had fired between reads of the journal.
  Recovery: GitHub-verify the run, do NOT re-fire, account for the
  orphaned run manually in the next fire's note. Rule: per-entry
  terminality check before any `--all`.
- **2026-08-29 park rollout:** parking is 8 cheap fires; the batch stops at
  the first guard refusal by design — finish lanes individually after
  fixing the cause.
- **2026-09-04 new-ref fan-out:** pushing a merge branch created from `main`
  fired all eight lanes at once — a ref creation has no `before` commit, so
  every trigger file on it counts as changed, whatever the parent. The five
  live runs were cancelled in time ($0); the cancelled logits run's `always()`
  commit step still pushed a 1-result partial over a complete summary
  (reverted by hand). Fix: every push-to-run job now skips on
  `github.event.created`. Still open: the partial-over-complete overwrite.

## 6 · Money, seals, and boundaries (absolute)

- $2/day Anthropic operational ceiling, enforced by `fire_trigger.py`
  counting landed + in-flight `max_spend`. Every paid run writes a
  `.report.json` sidecar with its cost. `scripts/ledger_update.py` is the
  only spend writer.
- No paid fire without the owner's explicit words. No `--override-budget`,
  no `--force-evict`, ever. Ox Alpha never fires again (registry entry
  removed; post-window calls would bill catch-all).
- Both repos are PUBLIC: no secrets, keys, or tokens in any file, note, or
  commit message.
- The Tier B holdout stays sealed: 186 rows withheld; sealed labels
  pairs_20260809T172338Z #12 #27 #35 #45 #57 #62 and
  pairs_20260811T190638Z #10 #23 #33 #54. `seal_check` before quoting any
  new material anywhere; hits are reported as path + batch#index only.
- `data/simulated/` is append-only; intentional misspellings are stimuli;
  medical vocabulary lives in JSON data files only.

## 7 · Where things live

| Thing | Path |
|---|---|
| Fire/park/resolve/status | `scripts/fire_trigger.py` |
| Fire history | `ops/trigger_journal.jsonl` |
| Operational state (Routine-written) | `ops/dashboard.json` |
| Routine authority | `docs/routine_standing_prompt.md` |
| Fresh-container bootstrap | `docs/fresh_session_bootstrap.md` |
| Site data contract + validator | site `CLAUDE.md` + `scripts/validate_frontend_contract.py` |
| Holdout seal check | `scripts/seal_check.py` |
| Advice pipeline (elicit/judge/analyze) | `scripts/advice_eval.py` |
| Judge agreement exporter | `scripts/export_judge_agreement.py` |
| Backfill completion record | `docs/coordination/backfill_8b_complete_20260826.md` |
| Clinician review packet | `docs/review_packet_clinician.md` |
| Owner decision log | `docs/decisions_20260821_owner.md` (+ dated addenda) |
