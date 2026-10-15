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

**Close `PETRI-EQ01-EMPTY-OUTPUTS-20261013`:** remove it from `ops/dashboard.json:decisions_pending` and add its
resolution, citing this file, to the top of `decisions_log` (`docs/routine_standing_prompt.md` §6). The equity run
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
judgments, so the two judges' rows can be told apart. Then come the re-judge fires: Petri `mode: rejudge` and the
advice lane's judge-only re-run. Those are paid fires, and they wait for the owner's approval of their cost.

Not every landed Petri run can be re-graded as it stands. `rejudge.make_plan` refuses a run before any call when its
prompts or digests differ from the current ones. Wave 2's epoch-1 run is refused that way
(`tests/test_petri_audit_rejudge.py`): its baseline-persistence prompt predates the revision. A fire naming a
refused run alongside others is refused as a whole. So before any paid re-judge fire:
1. Rehearse every candidate run at $0 (`cli rejudge-rehearse` with `mockllm/judge`).
2. Report each refused run and why.
3. The owner chooses, per refused run, between a reconstruction path for the historical instrument and an
   exclusion recorded here.

The paid fires name only runs whose rehearsal was clean.

The advice lane's judge-only re-runs have two more prerequisites, both code changes made in a PR before any such fire:
- **The judge's spelling.** The second judge is spelled `anthropic:claude-haiku-5-5`. Analysis treats a spec
  containing `:` as a secondary judge and keeps it out of the judge-of-record cells. A bare `claude-haiku-5-5` would
  pool with Haiku 4.5 as if the two were replicate samples, so a bare second-judge spelling must be refused or kept
  separate in code, not just avoided by convention.
- **A spend record per fire.** `advice_eval.judge()` rewrites the stable `judgments_<stem>.report.json` with the
  latest pass's cost, and `scripts/ledger_update.py` books a seen sidecar's growth only. A cheaper Haiku 5.5 pass
  would therefore book nothing, and a dearer one only the difference. The judge must write a sidecar per fire, or one
  that is truly cumulative, before these fires.

Haiku 5.5 costs $0.10 / $0.50 per million tokens against Haiku 4.5's $1 / $5. The Opus move changes the generator or
target of future runs only; landed batches are not regenerated.

## Third round (October Owner Queue 3)

The owner's reply, verbatim:

> October Owner Queue 3: 1. A, 2. B, 3. A, 4. A, 5. A, 6. A, 7. B, 8. A, 9. A, 10. A

A $0 rehearsal (`cli rejudge-rehearse` with the mock judge, run locally on 2026-10-14) re-planned every landed Petri
run against today's prompts.
- **Clean (4):** `run_35812312136_1`, `run_35937014168_1`, `run_36076994201_1` and eq02 `run_38434195912_1`.
- **Refused (2):**
  - `run_35351739969_1`, the wave-1 pilot: 4 judgments whose rendered prompt differs;
  - `run_35801345137_1`, wave 2's epoch 1: 30 judgments, because the planner changed.
- **Nothing to re-judge:** eq01, `run_38311055562_1`.

| # | Decision | Chosen |
|---|---|---|
| R1 | Petri re-judge with Claude Haiku 5.5 | One `mode: rejudge` fire over the four clean runs, `judge_model: claude-haiku-5-5`, `judge_max_spend` $1.00 (about $0.53 expected), after #114 merges. |
| R2 | The two refused Petri runs | Rebuild their original judge instrument (the prompts and the planner as they ran), so each can be re-judged exactly. A pull request. |
| R3 | Advice re-judge | One judge-only advice-eval fire per archive (six), `judge_model: anthropic:claude-haiku-5-5`, $0.30 ceiling each, chained, after #114 merges. About $0.70 in all. |
| R4 | Both judges from now on | Automate it: each judged fire runs Claude Haiku 5.5 after the judge of record, inside the same reservation. A pull request after #114 merges. |
| R5 | The equity v2 fire's raise (Q1 of the second round) | The owner authorizes a $4.00 dated raise in `ops/budget_overrides.json` for the fire's UTC day, citing this record. The agent writes it in the fire's own commit and fires once #108 merges. |
| R6 | Circuit-trace translation | Stays on `claude-opus-4-8` (engine #112 pins it). |
| R7 | The PAB jury | Moves to `claude-opus-5-5`. The jury is re-validated before any PAB fire uses it (`docs/pab_first_probe_costing.md` calls the Opus 4.8 jury the validated instrument). |
| R8 | The scenario-generation spend check | Fixed: each call is admitted at the allowance it is sent. The park's `max_spend` rises from $0.01 to $0.03 so the park still produces its one-pair batch. |
| R9 | Petri-only Jev runs | A follow-up PR after #110 and #111 merge. |
| R10 | Wave-3 script readings and worktrees | The six readings in engine #113 are accepted. The eight clean worktrees of merged PRs were removed on 2026-10-14. The row-3 sentence below is the draft for approval with the plan. |

### Draft: the wave-3 statement for row 3 (R10)

The plan's §9.8 row 3 ("the reverse direction, under the rules of rows 1 and 2") has no sentence. This draft is for
the owner to approve with the plan, as a dated amendment; the plan file is not edited here.

- **Row 3, gate p < 0.05, same direction:** "In this pilot of eight new scripted scenarios, {target}'s replies to
  clinical wording were graded as less urgent than its replies to casual wording, and the difference held across the
  scenarios."
- **Row 3, gate p >= 0.05:** "In these eight scenarios, {target}'s replies to clinical wording were graded as less
  urgent than its replies to casual wording, but the difference was not consistent across scenarios." It also names
  the scenarios that carry it.
