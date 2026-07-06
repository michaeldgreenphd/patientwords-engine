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
