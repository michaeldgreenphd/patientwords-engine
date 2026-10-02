# data/advice/ — frontier-model advice archive (append-only)

Outputs of `scripts/advice_eval.py`. Elicitation against hosted frontier models is
inherently unrepeatable, so this archive is designed to be **auditable instead**:
nothing here is ever rewritten, and every response record is hash-chained.

## Files

| Pattern | Written by | Contents |
|---|---|---|
| `stimuli_<STAMP>.json` | `build-stimuli` | paired vignettes: clinical/patient bodies + assembled messages (identical ask suffix on both sides preserves the minimal pair), per-text sha256, source provenance, engine sha |
| `responses_<stem>.jsonl` | `elicit` | one record per API call, append-only, hash-chained (see below) |
| `responses_<stem>.report.json` | `elicit` | cost sidecar: spend vs `--max-spend`, per-model token usage, records appended, truncation reason, **chain_head** |
| `judgments_<stem>.jsonl` | `judge` | tier + flags per response, keyed by `response_sha256` + `rubric_sha256` + judge model — never mutates the response archive, re-runnable forever |
| `judgments_<stem>.report.json` | `judge` | judge cost sidecar |
| `analysis_<stem>.json` | `analyze` | offline paired stats: modal tiers, rank diffs, downgrade/upgrade classes, translation recovery, within-prompt variance, cluster bootstrap CIs |

## Re-running chosen items (`--source selection`)

To send items of earlier stimuli files to other models, list them in a selection
file and build a new stimuli file from it:

```bash
python scripts/advice_eval.py build-stimuli --source selection --selection <selection>.json
```

The selection file is JSON:

```json
{"rule": "how the items were chosen, in plain words (stated as post hoc if it was)",
 "items": [{"file": "data/advice/stimuli_<STAMP>.json", "id": "<item id>"}],
 "notes": "optional"}
```

`scripts/advice_rerun_select.py --report-out <report> --selection-out <selection>`
writes a selection in this shape together with its ranking report. Every metric
stays in the report, and the selection's `notes` name the report by path and
sha256 (`rerun_ranking_20261002.json` and `rerun_selection_20261002.json`).

- Each selected item is copied **verbatim**: bodies, assembled messages, sha256
  values, `source_ref`, `meta` and any other field. The build adds only
  `meta.rerun_of = {file, id, file_sha256}`; an item that already had a
  `rerun_of` keeps it under `rerun_of.prior`.
- Each copied message must still hash to its recorded `clinical_sha256` /
  `patient_sha256`; a mismatch is refused.
- A missing file, a missing id, an entry listed twice (also when the same file
  is named two ways, such as an absolute and a relative path), two entries
  that send the same two messages (one stimulus copied into two files), an
  unknown key, an empty `rule` and `--ask-suffix` are refused, and nothing is
  written.
- Items that name one source pair (`source_ref` batch and index) with
  different messages, such as one pair built with two ask suffixes, are kept,
  and `source.shared_source_pairs` lists their output ids. `analyze` treats
  each id as its own cluster, so read its bootstrap intervals with that list.
- Output ids stay unique. When an id was already taken by an earlier entry, the
  later item becomes `<id>~<file stem>`; `source.renamed_ids` lists each one,
  and `meta.rerun_of.id` keeps the original id.
- The holdout seal applies to every item: `tierb_split.sealed_pair`, the
  one-row form of the rule the collector stamps, which is wider than the
  `--source pairs` guard. An item is refused when its clinical body is a
  registered holdout phrase anywhere (Amendment 3: under an alias stem such as
  `pairs_<STAMP>_txopus`, a re-run stem, a non-Tier-B batch, or with no
  `source_ref` at all), or when it comes from a Tier B batch whose `top_prompt`
  or its own clinical body hashes holdout. When an item names a non-Tier-B
  batch whose file is in `--simulated-dir`, that batch's accepted prompt is
  checked too (a payload item completed with its target word has a body that
  differs from the registered prompt). When the seal cannot be evaluated (no
  `tierb.start_utc` in `--dashboard`, no Tier B batch files in
  `--simulated-dir`, a Tier B pair with no `top_prompt`, an index outside its
  batch) the build is refused. A sealed item is refused, not dropped, so the
  output never silently covers fewer items than the selection names.
- The output's `source` block records `kind: "selection"`, the selection file's
  `path` and `sha256`, the `rule`, each source file's sha256 (`files`), ask
  suffix (`ask_suffixes`) and own source kind and paths (`file_sources`),
  `renamed_ids`, `shared_source_pairs`, and the seal's counts: every item (`seal_items_checked`), the
  Tier B items (`tierb_items_checked`) and the items whose batch file's
  accepted prompt was checked as well (`accepted_prompt_items_checked`).
- `export_advice_scenarios.py` labels a selection file's family from
  `file_sources` (an `advnat_` batch behind a source file is the
  natural-question family), and refuses a selection that mixes the two
  families, because the label is per stimuli file: build one selection per
  family.
- `ask_suffix` is the selected files' common suffix. When they differ it is
  `null`, and `elicit` refuses the translated arm for that file, because that
  arm appends the file-level suffix to each translation. The clinical and
  patient arms send the copied messages unchanged.

## The audit chain

Each `responses_*.jsonl` record carries `prev_sha256` (the previous record's hash)
and `record_sha256` (sha256 of the record's canonical JSON including `prev_sha256`).
The final hash is committed as `chain_head` in the sidecar, in the same commit as
the data, on a public repo. You cannot re-run the model, but anyone can prove the
archive has not been altered since it landed:

```bash
python scripts/advice_eval.py verify-chain \
    --responses data/advice/responses_<stem>.jsonl \
    --sidecar   data/advice/responses_<stem>.report.json
```

Every record also stores the full request (message text verbatim, temperature,
max_tokens), the full raw provider response, the exact `model` version string the
API returned, send/receive UTC timestamps, latency, token usage, per-call cost,
and the engine git sha.

## Rules

- **Append-only.** Never rewrite, reorder, or delete a landed record or file; the
  chain makes any edit detectable, and `elicit` refuses to append to a broken chain.
- **Holdout seal.** Stimuli built from the published payload are holdout-safe by
  construction (the payload withholds sealed rows). The `--source pairs` path
  excludes holdout pairs via `tierb_split.py` and hard-errors when the holdout set
  cannot be computed (null `tierb.start_utc` — use the ops-truth dashboard copy).
  The `--source selection` path applies `tierb_split.sealed_pair` (Amendment 3,
  wider than the pairs guard) to each selected item and refuses a sealed one, or
  the whole build when the seal cannot be evaluated.
- **Judge blinding.** The judge sees response text only — never the prompt or arm.
- **Vocabulary is data.** Tier definitions and judge wording live in the rubric
  JSON (`data/advice_rubric.json`, domain-reviewed; `.example` is the skeleton).
- This arm **evaluates** model advice for measurement. It never dispenses advice.
