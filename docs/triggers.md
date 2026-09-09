# Push-to-run trigger files (`.github/trigger/`)

Every workflow in this repository that spends money, calls a hosted service, or
runs CPU inference starts when its file under `.github/trigger/` changes on a
pushed branch (the workflows' `on.push.paths` filters name these files). The
push path exists for automation that has contents-write access but no
actions-write scope, which is every Claude Code session working through the
GitHub App.

This page lives under `docs/` rather than beside the files because the guard
hooks refuse every session write under `.github/trigger/`, the README there
included; `.github/trigger/README.md` is a July 2026 runbook that predates the
ops system and is superseded by this page.

**Never edit the trigger files by hand.** `scripts/fire_trigger.py` is the only
sanctioned writer: it validates the keys against the table below (CI silently
ignores an unknown key, so a typo means a run with defaults), journals the fire
in `ops/trigger_journal.jsonl`, enforces one running + one pending run per
lane, refuses paid fires that would breach the daily ceiling, and pushes under a
one-shot token that `.githooks/pre-push` and the Claude Code guard hooks require
for any push carrying a change there. Procedure: `docs/operators_handbook.md`;
rules: `AGENTS.md` (*Execution model*).

Three facts about the mechanism that have cost real money or real runs:

- **A trigger file appearing on a ref for the first time counts as a change**,
  so a merge, rebase, cherry-pick or branch creation can fire a lane. Every
  workflow skips the push that creates a ref (`if: ${{ !github.event.created }}`),
  which means the first push to a brand-new branch fires nothing; fire from an
  existing branch. A merge must keep the target branch's trigger files unchanged.
- **The committed content of each file is a loaded default** (the resting-state
  rule): it should always be the lane's cheapest no-op, and `fire_trigger.py
  park` restores it after a real fire. The exception is `pab-probe`, which is not
  parked on `main` because its workflow lives on the PAB branch.
- **Each workflow's concurrency group holds one running + one pending run**, and a
  third push evicts the pending run silently. Chain fires; never stack.

## Lanes

The key column is the exact set the workflow's push path reads
(`KNOWN_KEYS` in `scripts/fire_trigger.py`); any other key is refused. Keys
beginning with `_` (`_nonce`, `_parked`) are the script's own and are never sent
to a workflow. `tests/test_trigger_docs.py` fails when this table, the table in
`AGENTS.md`, and the script's `TRIGGERS`, `PAID_TRIGGERS`, `PARK_DEFAULTS` or
`KNOWN_KEYS` disagree, or when a row names a workflow that does not read its file.

| Trigger file | Workflow | What it does, and what it costs | Park default | Keys |
|---|---|---|---|---|
| `circuit-trace.json` | `circuit_trace_evaluation.yml` | hosted attribution graphs on Neuronpedia (matrix: `graph_models` × `offsets`); $0, except `show_mitigation: true`, which makes Anthropic translation calls (a flat $0.15 imputed per fire) | yes | `commit_outputs`, `desired_logit_prob`, `edge_threshold`, `generate_explanations`, `graph_model`, `graph_models`, `max_feature_nodes`, `max_n_logits`, `mode`, `node_threshold`, `offsets`, `pairs_file`, `sample_size`, `screen_targets`, `show_mitigation`, `steer_boost`, `steer_boost_strength`, `steer_placebo`, `steer_rank_offset`, `steer_strength`, `steer_validate`, `translation_model`, `translation_placebo` |
| `logits-eval.json` | `logits_evaluation.yml` | CPU next-token measurement for models Neuronpedia cannot trace; `mode: verify` re-measures through interp-engine; $0 | yes | `commit_outputs`, `dtype`, `layers`, `limit`, `mode`, `models`, `offset`, `pairs_file`, `topk` |
| `activation-patching.json` | `activation_patching.yml` | CPU residual-stream patching grid; $0 | yes | `commit_outputs`, `layers`, `limit`, `model`, `offsets`, `pairs_file`, `positions` |
| `jlens-readout.json` | `jlens_readout.yml` | hosted Jacobian-lens depth readouts; $0 | yes | `commit_outputs`, `lens_type`, `limit`, `models`, `offset`, `pairs_file`, `save_raw`, `steer_spec`, `topn` |
| `scenario-generation.json` | `scenario_generation.yml` | Claude-authored pair batches, appended under `data/simulated/` with a `.report.json` cost sidecar; **paid**, `max_spend` ceiling | yes | `anthropic_model`, `dialects`, `feedback`, `graph_models`, `max_spend`, `num`, `num_baselines`, `phrase`, `seed_pairs`, `target_token`, `task`, `term`, `topics`, `trace_sample_size` |
| `model-evaluation.json` | `model_evaluation.yml` | Claude concept-extraction eval before/after translation; **paid**, `max_spend` ceiling | yes | `max_spend`, `model_selection`, `pairs_file`, `sample_size`, `scenario` |
| `archive-renders.json` | `archive_renders.yml` | zips run renders to a GitHub Release, optionally pruning the PNGs from the branch (`prune`), or pruning only what a Release already holds (`prune_only`); a bundle that would shrink an existing Release is refused unless `allow_shrink`; $0 | yes | `allow_shrink`, `no_pngs`, `prune`, `prune_only`, `runs`, `tag` |
| `advice-eval.json` | `advice_evaluation.yml` | deployed-assistant advice elicitation and judging; **paid**, `max_spend` and `judge_max_spend` ceilings | yes | `arms`, `commit_outputs`, `gen_config`, `judge`, `judge_max_spend`, `judge_max_tokens`, `judge_model`, `limit`, `max_spend`, `max_tokens`, `models`, `offset`, `restore_artifact_run_id`, `restore_merge_fork`, `rubric`, `samples`, `stimuli_file`, `temperature`, `translator_model` |
| `pab-probe.json` | `pab_probe.yml` | patient/assistant/sandbox probe legs; **paid** (prepaid OpenRouter key, Anthropic for the evaluate stage); its workflow exists only on the PAB branch, so on `main` a fire is refused (exit 7) | no (branch-local lane) | `artifact_run_id`, `artifact_run_id_2`, `assistant`, `cases_file`, `catalog_require`, `catalog_search`, `commit_sidecar`, `config_file`, `fork_ref`, `generate_timeout_minutes`, `max_spend`, `run_dir`, `stage`, `turns` |

Each run reads the file at the pushed commit, so the parameters are versioned
with the run they started. The journal entry's note and the commit message
(`Fire <trigger>: <note>`) say why.
