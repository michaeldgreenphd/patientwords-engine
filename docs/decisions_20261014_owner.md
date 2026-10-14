# Owner decisions — 2026-10-14 (October Owner Queue)

After the Jev calibration work landed on the site (engine #103 and #107; site #14, #16 and #17), the owner answered
the four decisions of the October Owner Queue page in a Claude Code session on 2026-10-14. The reply, verbatim:

> 1. A, 2. A, but youre also welcome to look at a spread of stimuli 3. Bring the Jev workflow under fire_trigger
> (journal, daily ceiling, ledger) and let export_jev_calibration combine several runs. PR only; no fires until I
> approve. 4. Delete scripts/run_export_and_verify.py and run git worktree prune. When the next daily cycle runs,
> have it close PETRI-EQ01-EMPTY-OUTPUTS as resolved by eq02 (run 38434195912).

## The decisions and their option A

| # | Decision | Chosen |
|---|---|---|
| D1 | Wave 3 (`data/petri/w3_register_contrast_plan.json`, still DRAFT) | Check the plan against the lessons of 2026-10-12/13 and report what needs amending before approval. No fires. |
| D2 | The equity seeds | Redraft as an exploratory study under new seed ids: turns 1-7 below the warning sign, and a matched control for each without the housing, insurance and stigma details. A wider spread of stimuli is also welcome. No fires. |
| D3 | Jev | Bring `.github/workflows/jev_pilot.yml` under `scripts/fire_trigger.py` (journal, daily ceiling, ledger) and let `scripts/export_jev_calibration.py` combine several runs. Pull requests only; no fires until the owner approves. |
| D4 | Tidy-ups | Delete the untracked `scripts/run_export_and_verify.py`; `git worktree prune`; the next daily cycle closes `PETRI-EQ01-EMPTY-OUTPUTS`. |

## For the daily Routine

**Close `PETRI-EQ01-EMPTY-OUTPUTS-20261013` in `ops/dashboard.json:decisions_pending` as resolved.** The equity run
eq01 (`run_38311055562_1`, 2026-10-12) committed no transcripts because every sample hit Inspect's 20,000-token limit.
It was re-fired as eq02 (`run_38434195912_1`, 2026-10-13) at `token_limit` 40,000 with judge `claude-haiku-4-5`:
6 of 6 samples adapted, 300 judgments plus 54 not applicable, $0.65. The guard that refuses a token limit a scripted
sample cannot finish under is engine #105.

## Implementation

- **D1**: report given in the session (no repository change). In short, nothing in the plan's design needs amending for
  these lessons. The two late-red-flag seeds keep turns 1-6 below their warning sign at turn 7, unlike the eq01/eq02
  seeds. The plan's token limits (40,000 for the anchor, 65,000 for the comparison targets) fit the pre-flight
  projection. Things to settle at approval:
  - the judge route (`judge.judge_model`);
  - fires only after the physician realism gate (round 1 closes 2026-10-31) is applied;
  - the analysis script, still unwritten;
  - a guard against a judge spec that prices at the fallback rate (eq01's `anthropic/claude-haiku-4-5`).
- **D2**: engine #108, `docs/framework/petri_seeds_equity_v2.draft.json` with its swap and pairing files and tests.
- **D3**: engine pull requests to follow (the lane and the exporter); no fire until the owner approves.
- **D4**: the script was deleted and the stale worktree entries pruned on the owner's machine on 2026-10-14. Neither was
  in git. The dashboard entry is the Routine's to close (above).
