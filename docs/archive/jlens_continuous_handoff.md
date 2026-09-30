# Jacobian-lens transport figure — continuous wiring handoff

**Status (2026-07-20):** the frontend transport figure ("Where in the sentence",
`patientwords/technical/index.html`) is **live on `patientwords/main`** and now reads
richer, load-bearing fields (per answer row: the clinical target's rank grid, the layer
where it "forms", the model's actual top token + prob + on-target flag, and the per-layer
open-vocab readout). The **data it reads is pinned to a one-time `$0` fire** done by hand
on the experiment branch — nothing regenerates it on the nightly cycle. This doc is the
checklist to wire it into the continuous cycle so it refreshes as coverage grows.

See also: `docs/jlens_evaluation.md` (the evaluation + probe results, §5b/§6), and the
`FRONTEND_CONTRACT` dict + nightly-invocation docstring in
`scripts/export_jlens_transport.py` (the authoritative field + command reference).

## Current state (all branch-only on `claude/jacobian-lens-patientwords-r47tkt`)

None of the following is on engine `main`, and `main`'s
`docs/routine_standing_prompt.md` has **zero** jlens content:

- trigger `.github/trigger/jlens-readout.json`, workflow `.github/workflows/jlens_readout.yml`
- scripts `jlens_readout.py`, `jlens_steer.py`, `jlens_position_scan.py`,
  `jlens_insights.py`, and the three site exporters
  `export_jlens_{transport,depth,loglens}.py` (+ their `tests/`)

**The gap:** `jlens_readout.yml` produces **raw readouts only** — it does not run the site
exporters or write to `../patientwords/data/`. The publish step (below) was done by hand
this session and is the missing continuous link.

## Tasks

### 1. Promote the jlens machinery so the nightly Routine can reach it
Land the files above on `main` (or otherwise make them reachable from whatever the cycle
runs), tests included.

> ⚠️ **Trigger-on-merge:** landing `.github/trigger/jlens-readout.json` on `main` **fires**
> `jlens_readout.yml` (the repo's merge/copy danger rule). jlens is `$0`, so there's no
> spend risk — but respect queue discipline (one running + one pending per group). Land it
> deliberately; if you don't want the fire on the merge commit, restore the trigger file to
> `main`'s version in that commit.

### 2. Add the PUBLISH step to the cycle (the missing link)
After raw readouts land under `trace_out/*__jlens_gemma-2-2b/jlens_raw/`, regenerate and
republish the site data. All three site exporters **REFUSE** (return `None`, leave the good
file untouched) when raw coverage is missing, so a partial cycle cannot corrupt the live
figure — safe to run every cycle.

```bash
# transport (pinned exemplars keep the figure stable across regens):
python scripts/export_jlens_transport.py --model gemma-2-2b \
    --census-batch pairs_20260711T051145Z \
    --exemplar-pins pairs_20260712T163501Z:22,pairs_20260712T163501Z:7,pairs_20260712T163501Z:11,pairs_20260712T163501Z:83,pairs_20260712T163501Z:87 \
    --out data/jlens_transport.json --site ../patientwords

# logit-lens robustness companion:
python scripts/export_jlens_loglens.py --model gemma-2-2b \
    --out data/jlens_loglens.json --site ../patientwords

# technical-page insights strip:
python scripts/jlens_insights.py --site ../patientwords

# depth ladder (needs a jlens_steer / jsteer_ run; exemplar-specific args —
# canonical --units-batch/--exemplar-stem/--exemplar-index spec is in the
# export_jlens_depth.py docstring):
python scripts/export_jlens_depth.py --units-batch pairs_20260711T051145Z \
    --exemplar-stem <stem> --exemplar-index <idx> \
    --out data/jlens_depth.json --site ../patientwords
```

### 3. Register jlens in the nightly cycle
Add to `main`'s `docs/routine_standing_prompt.md`: fire `jlens-readout` on the sentinel
batch in idle slots, then run the step-2 publish after readouts land. The branch copy
already has the fire wording (step 3c) — port it **and** add the publish step.

## Contract (do not break — the live figure depends on it)

Source of truth is the `FRONTEND_CONTRACT` dict in `export_jlens_transport.py`. It codifies:

```
exemplars[].{target, layers, sides.<side>, render?}
sides.<side>.{tokens[].token, grid, answer_position,
              answer.{token, prob, on_target, trace_url},
              readout[].{layer, final, tokens}}
census.<side>.{n, reaches_answer, transport_gap, never_readable}
```

Assert these paths after each regen before committing the site copy. The frontend figure
degrades gracefully (pending/em-dash) if a field is absent, but a silent schema change
would quietly blank the annotations.

## Cleanup

`data/jlens_transport.json` currently carries a `pos_readout` field that **no engine script
emits** (hand-added) and the frontend now **ignores** (the per-position marginalia was
function-word noise that crowded the answer rows, so it was suppressed). Either drop
`pos_readout` from the payload, or — if a per-position view is wanted later — have the
exporter emit it and coordinate re-enabling a de-noised version on the frontend.

## Guardrails (unchanged)

`$0` triggers only via `scripts/fire_trigger.py`; one-running + one-pending per group;
`ops/dashboard.json` is Routine-only; medical vocabulary stays in JSON data files, never
Python; both repos public — no secrets anywhere. The lens is correlational (a readout, not
an intervention) — keep the EXPLORATORY framing; causal claims stay with activation
patching.
