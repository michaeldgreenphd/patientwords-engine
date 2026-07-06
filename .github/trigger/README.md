# Push-to-run trigger files

The Scenario Generation and Circuit Trace Evaluation workflows can be
started two ways: `workflow_dispatch` from the Actions tab, or by pushing a
parameters file here. The push path exists for automation that has
contents-write access but no actions-write scope (so it cannot call the
workflow-dispatch API) - e.g. Claude Code sessions working through the
GitHub App.

- `scenario-generation.json` - starts **Scenario Generation** on the pushed
  branch. Keys mirror the workflow_dispatch inputs (`task`, `num`, `topics`,
  `seed_pairs`, `phrase`, `term`, `target_token`, `anthropic_model`,
  `max_spend`, `graph_models`, `trace_sample_size`); omitted keys use the
  dispatch defaults.
- `circuit-trace.json` - starts **Circuit Trace Evaluation** on the pushed
  branch. Keys mirror its dispatch inputs (`graph_model`, `mode`,
  `pairs_file`, `offset`, `commit_outputs`, `max_n_logits`,
  `desired_logit_prob`, `node_threshold`, `edge_threshold`,
  `max_feature_nodes`, `sample_size`). Chunked tracing over one batch =
  repeated pushes stepping `offset`, with `commit_outputs: true` so each
  chunk's `index_NN.html/png` + `batch_summary.part_NN.json` land back on
  the branch as checkpoints.

Each workflow run reads the file at the pushed commit, so the parameters
are versioned with the run they started.

## Runbook: the large screened run (~100+ measured pairs)

Everything is push-to-run; no session required. Costs: generation only
(Anthropic tokens; tracing is free with the Neuronpedia account key).

1. **Generate** — edit `scenario-generation.json` and push:
   `{"task": "pairs", "num": "150", "topics": "<comma-separated areas>",
     "seed_pairs": "data/simulated/seed_union_20260706.json",
     "feedback": "data/simulated/feedback_pairs_20260706T201750Z.json",
     "anthropic_model": "claude-opus-4-8", "max_spend": "10",
     "trace_sample_size": "0"}`
   The batch + cost sidecar land on main (13 candidates cost ~$0.19, so
   150 stays comfortably under a $10 ceiling).
2. **Screen + trace** — edit `circuit-trace.json` with the new stamp and push:
   `{"graph_model": "gemma-2-2b", "mode": "2panel",
     "pairs_file": "data/simulated/pairs_<STAMP>.json",
     "offsets": [0, 3, 6, ...], "sample_size": "3",
     "screen_targets": "0.02", "commit_outputs": true,
     "max_feature_nodes": "2500"}`
   One matrix job per offset, 3 in parallel; ~5 min per graph; screened-out
   candidates cost one graph, measured pairs two. Expect ~6-8 hours for 150
   candidates. `max_feature_nodes 2500` roughly halves render weight - use
   it for large series so the Pages repo stays light.
3. **Optional feedback round** — assemble the screened-out entries into a
   feedback JSON (see scripts in the repo history or ask the assistant),
   regenerate a top-up batch, trace it with the same settings.
4. **Publish** — in the frontend checkout:
   `python scripts/export_frontend_simulated.py --frontend ../patientwords \
      --stamps <STAMP>[,<TOPUP-STAMP>] --no-pngs`
   then review, commit, and push the frontend to main. The Simulated
   Scenarios page paginates 15 per page and each scenario has its own
   detail page, so 100+ scenarios stay navigable.
