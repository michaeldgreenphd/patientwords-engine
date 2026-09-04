# Staged CI for the PatientAgentBench probe

`pab_probe.yml` is a candidate workflow. It is **not live**. It sits here rather
than in `.github/workflows/` because two separate acts make it real, and both are
the owner's:

1. **Landing it** — `cp ops/pab_ci/pab_probe.yml .github/workflows/`. From that
   commit on, the repository has a workflow that can spend money.
2. **Firing it** — `python scripts/fire_trigger.py pab-probe --params '...'`,
   which creates `.github/trigger/pab-probe.json` and pushes. That is what
   actually spends.

Nothing here has been done. `tests/test_pab_ci_staged.py` asserts the workflow is
absent from `.github/workflows/` and that no trigger file exists, so an accidental
landing shows up as a failing test rather than a surprise invoice.

## Why it exists

The OpenRouter key is a GitHub Actions secret. Secrets are injected into workflow
runners and nowhere else — no development container can read one — so CI is the
only way to run the probe, exactly as the advice arm does it
(`.github/workflows/advice_evaluation.yml`, which binds the same
`OPENROUTER_API_KEY`).

But the PatientAgentBench code is not in this repository. It is in the fork, under
CC-BY-NC-4.0, and this repository is MIT and imports none of it. So the workflow
clones the fork into `.pab-fork/`, runs there, and brings back **only the cost
sidecar** — numbers, no case content. Transcripts leave as a build artifact and
stay out of git until the licence boundary for derived artifacts is settled
(`docs/patientagentbench_integration_design.md` lists that as an open blocker).

## What landing it commits you to

| | |
|---|---|
| new workflow file under `.github/` | the directory whose whole property is that changes there fire paid jobs |
| a second repository cloned in CI | the fork, CC-BY-NC-4.0, by branch |
| `data/pab/*.report.json` committed by CI | already scanned by `ledger_update.py`, so spend reaches the $2/day guard |
| a new concurrency group `pab-probe-<ref>` | its own group, so a probe can never evict a pending trace, logits or lens run |

## Stages and what each costs

Figures from `scripts/pab_probe_cost.py`; see `docs/pab_first_probe_costing.md`.

| stage | what it does | keys used | est. cost |
|---|---|---|---|
| `smoke` | one conversation, asserts the tool trace is non-empty and well-formed | OpenRouter | **$0.025** |
| `generate` | 4 arms × 8 cases = 32 conversations, no scoring | OpenRouter | **$1.19** |
| `evaluate` | scores an existing run with the jury | OpenRouter + Anthropic | **$8.48** for 52 |

The default stage is `smoke` and the default `max_spend` is `$0.10`, so a trigger
fired with no parameters does the cheap thing.

## The order, if it goes ahead

```bash
# 1. land the workflow (one commit, no spend)
cp ops/pab_ci/pab_probe.yml .github/workflows/pab_probe.yml

# 2. tool-calling smoke test — the gate on everything else
python scripts/fire_trigger.py pab-probe --params '{"stage":"smoke","max_spend":"0.10"}'

# 3. read the sidecar it commits, then harvest
python scripts/ledger_update.py

# 4. only if the tool trace came back ok
python scripts/fire_trigger.py pab-probe --params \
  '{"stage":"generate","cases_file":"pw_pilot/sweep_health_literacy_n8.json","max_spend":"1.50"}'
```

`fire_trigger.py` is the required path: it journals the fire, enforces the
one-running-plus-one-pending discipline, and refuses a paid fire that would breach
the $2/day ceiling counting landed and in-flight `max_spend`.

## Before firing anything

- `pab-probe` must be added to `fire_trigger.py`'s known-trigger set, or the
  guard hard-errors on the key (by design — CI silently ignores unknown keys).
- The fork branch in `fork_ref` must be pushed and current.
- OpenRouter slugs and prices in the fork's `openrouter_specs.py` should be
  re-verified against OpenRouter's live model list; this sandbox cannot reach it.
- Three runs were unresolved in `ops/trigger_journal.jsonl` as of 2026-08-03
  (one logits-eval, two jlens-readout). Harvest before adding a fourth thing to
  reason about.
