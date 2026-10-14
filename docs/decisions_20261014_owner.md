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
- **D3**: engine #110 (the jev-audit lane) and #111 (the exporter combines several runs); no fire until the owner approves.
- **D4**: the script was deleted and the stale worktree entries pruned on the owner's machine on 2026-10-14. Neither was
  in git. The dashboard entry is the Routine's to close (above).

## Second round (October Owner Queue 2)

The owner's reply, verbatim:

> October Owner Queue 2: 1. B, 2. A, 3. A, 4. A, 5. A, 6. A, 7. A
> PRs: merge #109 first, then #110, #111, #108 once their reviews are clean. No fires beyond what I picked above.

And, in the same message: "For all the scripts that have haiku 4.5 as a judge, i would like to rerun them with the
newest haiku (5.5). From here forward use both since i started with one. Also if you see any old opus update those to
5.5 as well."

| # | Decision | Chosen |
|---|---|---|
| Q1 | Firing the equity v2 seeds (#108; 12 conversations, about $1.30) | One fire, with a dated $4 raise in `ops/budget_overrides.json` for that UTC day, after #108 merges. |
| Q2 | The foot pair's turn 4 ("cannot keep my feet dry or change socks") | Keep it: it is part of the housing manipulation. |
| Q3 | Jev after #110 and #111 merge | Park the lane on `main` ($0). Open a follow-up PR so a fire can skip the advice phase. After it merges, fire one Petri-only audit per run (the three other wave-2 runs and eq02, $0.05 ceiling each). Then a combined export, and a site PR that names every run. |
| Q4 | eq02's analysis rows carry hypothesis H2 | Record the correction below; landed data is not edited. |
| Q5 | Wave-3 judge route | The Anthropic route, `claude-haiku-4-5`, as in wave 2. Under the instruction above, Claude Haiku 5.5 judges alongside it. |
| Q6 | Wave-3 prerequisites | Write both, as PRs: the analysis script, and a guard against judge specs priced at the fallback rate. |
| Q7 | Widening and tidying | Draft three more equity pairs after the v2 pilot reads cleanly (language barrier, rural distance, medication cost). Remove the worktrees whose branches are merged or closed, after listing them for the owner. |
| Q8 | Judges and Opus models | Every result judged by Claude Haiku 4.5 is judged again by Claude Haiku 5.5 (`claude-haiku-5-5`), and from now on both judge. Configured defaults that name an Opus model older than Claude Opus 5.5 move to `claude-opus-5-5`. |

### Correction: eq02's hypothesis label (Q4)

The original equity seeds (`docs/framework/petri_seeds_equity.draft.json`, engine #104) declare hypotheses H1 and H2.
They measure H1 and H4: the outcome dimensions they judge are the safety-netting set (H4) and
`recommendation_specificity` (H1), and they have no assertion turn, which H2 (asymmetric sycophancy, judged on
`assertion_handling`) requires. eq02's analysis rows (`data/petri/runs/run_38434195912_1/analysis_rows.jsonl`) copy
the seeds' list, so they read H1/H2. **Any analysis that groups rows by hypothesis reads eq02's H2 as H4.** The rows
and seeds stay as they are, because eq02's recorded seed digests bind them. The v2 seeds (#108) declare H1/H4, and a
test holds a seed's hypotheses equal to those of the dimensions it judges.

### Judging with both Haiku models (Q8): what it takes

Claude Haiku 5.5 is not a drop-in replacement for Haiku 4.5 as a judge:
- it rejects a non-default `temperature`;
- it thinks by default, and the thinking counts against the judge's small `max_tokens`;
- it rejects an assistant prefill.

The judge clients therefore need a change first. It is a pull request; its run settings are recorded in the
judgments, so the two judges' rows can be told apart. Then come the re-judge fires: Petri `mode: rejudge` over each
landed run, and the advice lane's judge-only re-run. Those are paid fires, and they wait for the owner's approval of
their cost. Haiku 5.5 costs $0.10 / $0.50 per million tokens against Haiku 4.5's $1 / $5. The Opus move changes the
generator or target of future runs only; landed batches are not regenerated.
