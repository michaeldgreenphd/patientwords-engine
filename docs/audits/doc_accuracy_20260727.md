# Doc-accuracy sweep — 2026-07-27 (Monday)

Checked: CLAUDE.md trigger table vs `.github/trigger/`; publish-site-data skill
exporter list vs `scripts/`; queue/lane claims vs journal behavior.

## Finding (LOW, real)

**`advice-eval` trigger is undocumented.** `.github/trigger/advice-eval.json`
exists and has been fired repeatedly (the 8-model advice arm, 1,842 calls), but
CLAUDE.md's "Execution model" trigger table lists only seven triggers and omits
it. A reader following CLAUDE.md would not know the lane exists, and the table is
the reference used when choosing a lane. Fix: add the row
(`advice-eval.json` | `advice_evaluation.yml` | cross-provider advice elicitation
+ blinded judge; paid, `max_spend` ceiling). Not done in this cycle — CLAUDE.md
is documentation the owner reads, and the standing rule for the daily cycle is
data-not-text; queued for the next engineering slot instead.

## Verified accurate

- All five j-lens exporters named in the publish skill exist in `scripts/` and
  the skill lists them in run order (transport + loglens wired 2026-07-23).
- Remaining seven trigger files all appear in the CLAUDE.md table.
- Queue discipline as documented (one running + one pending) matches observed
  `fire_trigger` refusals this weekend.
