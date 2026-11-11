"""Pins the first real-model run packet to the committed inputs it describes.

The packet is ``docs/exploratory/first_model_run_packet_20261110.md``. Nothing in it has been run against a
model. This file checks three things, all offline:

* the protocol under ``data/experiments/protocols/`` is rebuilt from landed records and equals the committed
  file byte for byte, so no token id in it was typed by hand;
* the preview file beside it (plan counts, reasons, plan SHA-256, resource estimates, the parity comparison
  set) is recomputed from the protocol, the capability matrix and the landed parts and equals the committed
  file, so the preview cannot drift from its inputs;
* the packet's generated block quotes the preview's values.

No stimulus text appears in this file. Rows are named by ``(batch, batch_index)`` and by SHA-256.

Where the token ids come from. The protocol validator requires token ids for every variant prompt and for
every target. No tokenizer file is available offline. The ids are therefore read from landed hosted-lens
records (``trace_out/<batch>__jlens_gemma-2-2b/jlens_raw/pair_NNN_<side>.json.gz``), which record one
``id`` per prompt token. A family is in the protocol only when every id it needs is on such a record:

* the prompt ids are the record for that exact prompt (the recorded token strings concatenate to the prompt);
* the target is one token in the landed CPU part (the part's recorded label, the decoded first token, equals
  the target text), and a landed lens record holds a prompt token with that exact string, whose id is taken.

The second step joins two records on a token string. It is a derivation, not a tokenizer call, and the
preview says so for each target. Families that fail either test are left out and listed with the reason.
Only hosted-lens records of study batches dated before the Tier B start stamp are opened. That the hosted
service's tokenizer is the tokenizer at the pinned revision is not verified by anything in this file.

Regenerate after a deliberate change to an input (for example the capability matrix)::

    python tests/test_first_run_packet.py --write

That rewrites the protocol, the preview and the generated block of the packet, and prints what changed.
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

ENGINE = Path(__file__).resolve().parents[1]
if str(ENGINE) not in sys.path:  # run as a script: ``python tests/test_first_run_packet.py --write``
    sys.path.insert(0, str(ENGINE))

import pytest  # noqa: E402

from scripts import results_policy, tierb_split  # noqa: E402
from scripts.experiments import capabilities as caps  # noqa: E402
from scripts.experiments import cli, estimate  # noqa: E402
from scripts.experiments.common import Refusal, digest, json_bytes, prompt_digest, sha256_bytes  # noqa: E402
from scripts.experiments.planner import build_plan, estimate_activation_bytes  # noqa: E402
from scripts.experiments.protocol import validate_protocol  # noqa: E402

PROTOCOL_DIR = ENGINE / "data" / "experiments" / "protocols"
PROTOCOL_REL = "data/experiments/protocols/first_run_stage_a.protocol.v1.json"
PREVIEW_REL = "data/experiments/protocols/first_run_stage_a.preview.v1.json"
PACKET_REL = "docs/exploratory/first_model_run_packet_20261110.md"
PREVIEW_SCHEMA = "patientwords.first-run-preview/1"

BATCH = "pairs_20260706T175614Z"
MODEL_ID = "gemma-2-2b"
HF_ID = "google/gemma-2-2b"
PIN = "c5ebcd40d208330abc697524c919956e692655cf"
BATCH_REL = f"data/simulated/{BATCH}.json"
CPU_PART_REL = f"trace_out/{BATCH}__{MODEL_ID}/batch_summary.part_01.json"
HOSTED_PART_REL = f"trace_out/{BATCH}/batch_summary.part_01.json"
LENS_DIR_REL = f"trace_out/{BATCH}__jlens_{MODEL_ID}/jlens_raw"
# Token-id records are read only from the hosted-lens records of study batches dated before the Tier B start
# stamp (the exploration period). No record of a Tier B batch or of a restricted-text set is opened.
LENS_SCOPE = (f"trace_out/pairs_<stamp>__jlens_{MODEL_ID}/jlens_raw/*.json.gz with <stamp> before the Tier B "
              "start stamp")
_LENS_DIR = re.compile(rf"pairs_(\d{{8}}T\d{{6}}Z)__jlens_{re.escape(MODEL_ID)}\Z")
MATRIX_REL = "data/experiments/capability_matrix.v1.json"
PILOT_PAIRS_REL = "pilot/runs/pilot_v2_20261002/trace/trace_pairs.json"
PILOT_HOSTED_REL = "pilot/traces/trace_pairs/batch_summary.part_01.json"
STAGE_A_LANDING = f"trace_out/verify_{BATCH}__{MODEL_ID}/verify_summary.part_01.json"
STAGE_B_LANDING = ("pilot/logits/pilot_v2_20261002/pilot_v2_20261002_trace_pairs__gemma-2-2b/"
                   "batch_summary.part_01.json")

# Model geometry. Sources are cited in the packet (section 4): 26 layers and a 256,000-entry vocabulary are in
# every landed hosted-lens record of this model; width 2,304 is in the service's ICA release page record.
N_LAYERS = 26
HIDDEN_SIZE = 2304
VOCAB_SIZE = 256000
BOS_ID = 2

# The batch's two sides and the protocol's variant names for them.
SIDES = (("clinical", "top_prompt", "clinical"), ("patient", "bottom_prompt", "colloquial"))

# Proxy rate for the resource estimate: no rate is recorded for gemma-2-2b on the CPU lane. The value is the
# slowest recorded rate of gemma-2-2b-it (scripts/backfill_planner.py SECONDS_PER_PAIR), an assumption.
PROXY_RATE_MODEL = "gemma-2-2b-it"
FAILED_ATTEMPT_FRACTION = 0.15
# Rounded parameter count from docs/model_matrix.md ("2.6B"). The exact count is not recorded.
PARAMETERS_ROUNDED = 2_600_000_000

# Parity thresholds, proposed in the packet (section 6) before any run. Changing one here changes the preview
# file and the packet block, which is the point: the criteria are part of the pinned record.
HOSTED_PASS_MAX = 0.0005
HOSTED_FAIL_ABOVE = 0.0010
BF16_EARLIER_MAX_INTERP = 0.0311
BF16_EARLIER_MAX_HOSTED = 0.0315
BF16_FAIL_ABOVE = 0.0630

BLOCK_BEGIN = "<!-- preview:begin (generated by tests/test_first_run_packet.py --write; do not edit by hand) -->"
BLOCK_END = "<!-- preview:end -->"

_LABEL = re.compile(r'Output "(.*)"\Z', re.S)


def _read_json(rel: str) -> Any:
    return json.loads((ENGINE / rel).read_text(encoding="utf-8"))


def _file_sha(rel: str) -> str:
    return hashlib.sha256((ENGINE / rel).read_bytes()).hexdigest()


def _label(value: Any) -> str | None:
    """The decoded token inside a summary's ``Output "<token>"`` label, or None."""
    match = _LABEL.match(value) if isinstance(value, str) else None
    return match.group(1) if match else None


def _lens_rel(index: int, side: str) -> str:
    return f"{LENS_DIR_REL}/pair_{index:03d}_{side}.json.gz"


def _lens_prompt_tokens(rel: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``(meta, prompt tokens)`` of one landed hosted-lens record. Generated tokens are left out."""
    with gzip.open(ENGINE / rel, "rt", encoding="utf-8") as handle:
        doc = json.load(handle)
    return doc["meta"], [token for token in doc["tokens"] if not token.get("is_generated")]


def _prompt_ids(rel: str, prompt: str) -> list[int]:
    """Token ids the hosted lens recorded for exactly this prompt.

    Refuses (AssertionError) a record of another model, a record without a leading BOS, a record whose length
    differs from its own ``prompt_len`` and a record whose token strings do not concatenate to the prompt.
    """
    meta, tokens = _lens_prompt_tokens(rel)
    assert meta["model"] == MODEL_ID and meta["prepend_bos"] is True, rel
    assert len(tokens) == meta["prompt_len"] and [t["position"] for t in tokens] == list(range(len(tokens))), rel
    assert tokens[0]["id"] == BOS_ID, rel
    assert "".join(t["token"] for t in tokens[1:]) == prompt, f"{rel}: recorded tokens are not this prompt"
    ids = [t["id"] for t in tokens]
    assert all(type(i) is int and 0 <= i < VOCAB_SIZE for i in ids), rel
    return ids


def _lens_files() -> list[Path]:
    """Hosted-lens record files of this model for study batches dated before the Tier B start stamp."""
    start = tierb_split.tierb_start_stamp(str(tierb_split.DASHBOARD_PATH))
    assert start, "no Tier B start stamp: the exploration period cannot be told from Tier B"
    files: list[Path] = []
    for directory in sorted((ENGINE / "trace_out").glob(f"pairs_*__jlens_{MODEL_ID}")):
        match = _LENS_DIR.match(directory.name)
        if match and match.group(1) < start:
            files.extend(sorted((directory / "jlens_raw").glob("*.json.gz")))
    return files


def scan_token_records() -> dict[str, Any]:
    """Every (token string, id) pair in the in-scope hosted-lens records, with the first place it occurs.

    Reads under a thousand small gzip files (about 1 s). Used by ``--write`` to find where a target's id is
    recorded, and by one test that checks the string-to-id relation is one to one in those records.
    """
    by_string: dict[str, set[int]] = {}
    by_id: dict[int, set[str]] = {}
    first: dict[str, dict[str, Any]] = {}
    files = _lens_files()
    for path in files:
        rel = path.relative_to(ENGINE).as_posix()
        _meta, tokens = _lens_prompt_tokens(rel)
        for token in tokens:
            by_string.setdefault(token["token"], set()).add(token["id"])
            by_id.setdefault(token["id"], set()).add(token["token"])
            first.setdefault(token["token"], {"file": rel, "position": token["position"]})
    return {"files": len(files), "batches": len({path.parent.parent.name for path in files}),
            "by_string": by_string, "by_id": by_id, "first": first}


def _rows() -> list[dict[str, Any]]:
    """One record per row of the batch: hashes, landed labels and values. No text is returned except the
    prompts and the target, which stay inside this process and go only into the protocol file."""
    pairs = _read_json(BATCH_REL)
    cpu = {r["index"]: r for r in _read_json(CPU_PART_REL)["results"]}
    hosted = {r["index"]: r for r in _read_json(HOSTED_PART_REL)["results"]}
    rows = []
    for index, pair in enumerate(pairs, 1):
        for side, key, _variant in SIDES:
            assert cpu[index]["prompts"][side] == pair[key] and hosted[index]["prompts"][side] == pair[key], \
                f"({BATCH}, {index}) {side}: a landed part was measured on another prompt"
        cpu_label, hosted_label = _label(cpu[index]["target_token"]), _label(hosted[index]["target_token"])
        rows.append({
            "index": index, "pair": pair, "target": pair["target_clinical_token"],
            "cpu_label": cpu_label, "hosted_label": hosted_label,
            "single_token": cpu_label == pair["target_clinical_token"],
            "hosted": hosted[index]["probabilities"], "cpu": cpu[index]["probabilities"],
        })
    return rows


def _target_id(source: dict[str, Any], target: str) -> int:
    """The id at the cited place, after checking that the token recorded there is exactly the target."""
    _meta, tokens = _lens_prompt_tokens(source["file"])
    token = tokens[source["position"]]
    assert token["position"] == source["position"] and token["token"] == target, \
        f"{source['file']} position {source['position']} does not record the target's token"
    return token["id"]


def build_protocol(target_sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The stage A protocol, from the batch file and landed records. ``target_sources`` maps a batch index
    (as a string) to the lens record and position that hold the target's token; only those rows are built."""
    families = []
    for row in _rows():
        source = target_sources.get(str(row["index"]))
        if source is None:
            continue
        assert row["single_token"], f"({BATCH}, {row['index']}): the target is not one token in the landed part"
        variants = {}
        for side, key, variant in SIDES:
            prompt = row["pair"][key]
            ids = _prompt_ids(_lens_rel(row["index"], side), prompt)
            variants[variant] = {"prompt": prompt, "prompt_sha256": prompt_digest(prompt), "token_ids": ids,
                                 "token_sha256": digest(ids), "register": side}
        families.append({
            "family_id": f"{BATCH}_i{row['index']:02d}", "split": "discovery",
            "review_status": "domain_review_pending",
            "legacy_join": {"batch": BATCH, "batch_index": row["index"], "model": MODEL_ID},
            "facts": [], "variants": variants,
            "targets": [{"id": "t_answer", "role": "answer", "text": row["target"],
                         "token_ids": [_target_id(source, row["target"])]}],
        })
    return {
        "schema_version": "patientwords.experiment-protocol/1",
        "protocol_id": "first-run-stage-a-gemma-2-2b-recorded-subset", "version": "1",
        "synthetic": False, "seed": 0,
        "notes": ("Stage A of docs/exploratory/first_model_run_packet_20261110.md, restricted to the rows of "
                  f"{BATCH} whose token ids are all on a landed record. NOT RUN. Prompt token ids are the hosted "
                  "lens service's record for each prompt (model id gemma-2-2b; the service records no tokenizer "
                  "revision). Each target id is the id a landed lens record holds for a token with the target's "
                  "exact string; the target is one token in the landed CPU part. Equality with the tokenizer at "
                  "model.tokenizer_revision is not verified offline: the run must reproduce every token_sha256 "
                  "from the pinned tokenizer before a model loads, or stop. The seed is recorded because the "
                  "schema requires one; the read draws no random number. No family carries the prompt-text "
                  "publication marker."),
        "evidence": {"evidence_class": "unclassified", "clinical_review": "domain_review_pending",
                     "visibility": "public", "restriction_reasons": [], "analysis_memberships": []},
        "model": {"study_id": MODEL_ID, "hf_id": HF_ID, "revision": PIN, "tokenizer_id": HF_ID,
                  "tokenizer_revision": PIN, "hidden_size": HIDDEN_SIZE, "n_layers": N_LAYERS,
                  "dtype": "float32", "backend": "cpu_interp_engine"},
        "input_settings": {"chat_template": None, "add_special_tokens": True, "truncation": False},
        "case_families": families,
        "methods": [{"id": "behavior_next_token"}],
        "comparisons": [{"id": "clinical_vs_colloquial", "a": "clinical", "b": "colloquial"}],
        "replicates": 1,
        "primary_endpoint": {"method": "behavior_next_token", "metric": "full_vocab_probability",
                             "target": "t_answer"},
        "exclusions": [],
    }


def _selection(target_sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """All ten rows of the batch: included or not, why, and the hashes that identify them. No text."""
    out = []
    for row in _rows():
        included = str(row["index"]) in target_sources
        if included:
            reason = "every_token_id_on_a_landed_record"
        elif not row["single_token"]:
            reason = "target_is_more_than_one_token_and_its_tokenization_is_on_no_landed_record"
        else:
            reason = "target_is_one_token_and_its_id_is_on_no_landed_record"
        entry: dict[str, Any] = {"batch": BATCH, "batch_index": row["index"], "in_protocol": included,
                                 "reason": reason,
                                 "target_tokens_in_landed_cpu_part": "one" if row["single_token"] else "more_than_one",
                                 "variants": {}}
        for side, key, variant in SIDES:
            rel = _lens_rel(row["index"], side)
            ids = _prompt_ids(rel, row["pair"][key])
            entry["variants"][variant] = {
                "batch_side": side, "prompt_sha256": prompt_digest(row["pair"][key]), "token_count": len(ids),
                "token_sha256": digest(ids), "token_id_record": {"file": rel, "sha256": _file_sha(rel)}}
        if included:
            source = target_sources[str(row["index"])]
            entry["target_id_record"] = {**source, "sha256": _file_sha(source["file"]),
                                         "join": "token string equal to the target text; id read at that position"}
        out.append(entry)
    return out


def _parity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The comparison sets and thresholds of the packet's section 6, fixed from landed files before any run."""
    comparable, excluded, baseline, misread = [], [], [], []
    for row in rows:
        for side, _key, _variant in SIDES:
            where = {"batch_index": row["index"], "side": side}
            if row["hosted_label"] != row["cpu_label"]:
                excluded.append({**where, "reason": "hosted_part_read_another_token_than_the_cpu_part"})
                if row["hosted"][side] is not None:
                    misread.append(round(abs(row["hosted"][side] - row["cpu"][side]), 4))
            elif row["hosted"][side] is None:
                excluded.append({**where, "reason": "hosted_part_reports_no_value"})
            else:
                comparable.append(where)
                baseline.append(round(abs(row["hosted"][side] - row["cpu"][side]), 4))
    pilot = [r for r in _read_json(PILOT_HOSTED_REL)["results"] if r["index"] == 1][0]
    pilot_pair = _read_json(PILOT_PAIRS_REL)[0]
    return {
        "status": "proposed_before_any_run_not_approved",
        "stage_a": {
            "candidate": STAGE_A_LANDING,
            "preconditions": [
                "the candidate records inference.revision and revision_pinned equal to the pin, dtype float32, "
                "interp_engine 1.5.1, completed true and results with indices 1 to 10",
                "token_parity.match is true on all 20 prompts",
                "every candidate target label equals the landed CPU part's label for that row",
                "every candidate probability is finite and present on all 20 sides",
                "both reference files have the SHA-256 recorded here",
            ],
            "hosted": {
                "reference": {"path": HOSTED_PART_REL, "sha256": _file_sha(HOSTED_PART_REL)},
                "metric": "absolute difference of the two recorded probabilities, per side",
                "comparable_sides": comparable, "excluded_sides": excluded,
                "pass": f"every comparable side at or below {HOSTED_PASS_MAX}",
                "fail": f"any comparable side above {HOSTED_FAIL_ABOVE}",
                "inconclusive": (f"otherwise (a side above {HOSTED_PASS_MAX} and none above {HOSTED_FAIL_ABOVE}), "
                                 "or a precondition does not hold"),
                "pass_max": HOSTED_PASS_MAX, "fail_above": HOSTED_FAIL_ABOVE,
                "tolerance_source": ("recording precision: the hosted part keeps 3 decimals (half-width 0.0005) "
                                     "and a verify summary 4 (half-width 0.00005), so two routes that compute "
                                     "the same probability differ by at most 0.00055 as recorded, which is "
                                     "0.0005 on the 0.0001 grid of such differences; a recorded difference "
                                     "above 0.0010 needs a true difference above 0.00045"),
            },
            "cpu_bfloat16": {
                "reference": {"path": CPU_PART_REL, "sha256": _file_sha(CPU_PART_REL)},
                "metric": "absolute difference of the two recorded probabilities, per side; mean and maximum",
                "sides": 2 * len(rows),
                "consistent": f"maximum at or below {BF16_EARLIER_MAX_INTERP}",
                "fail": f"any side above {BF16_FAIL_ABOVE}",
                "inconclusive": (f"otherwise (a side above {BF16_EARLIER_MAX_INTERP} and none above "
                                 f"{BF16_FAIL_ABOVE}), or a precondition does not hold"),
                "consistent_max": BF16_EARLIER_MAX_INTERP, "fail_above": BF16_FAIL_ABOVE,
                "tolerance_source": ("observed, not derived: 0.0311 is the largest of 100 side differences "
                                     "between interp-engine float32 and CPU bfloat16 on pairs_20260710T011743Z "
                                     "(ops/backend_agreement_interp_vs_local_20260904.json); 0.0630 is twice "
                                     "0.0315, the largest side difference any earlier comparison of the "
                                     "bfloat16 lane recorded (docs/backend_agreement_20260903.md). The factor "
                                     "2 is a choice, not a derivation"),
            },
            "landed_baseline_hosted_vs_cpu_bfloat16": {
                "statement": ("computed from the two landed reference parts for this document; it measures the "
                              "bfloat16 lane against the hosted route on the comparable sides and is not a "
                              "result of the proposed run"),
                "sides": len(baseline), "max": max(baseline), "mean": round(sum(baseline) / len(baseline), 5),
                "sides_where_the_hosted_part_read_another_token": {
                    "sides": len(misread), "min": min(misread), "max": max(misread),
                    "above_0.06": sum(1 for value in misread if value > 0.06)}},
        },
        "stage_b": {
            "candidate": STAGE_B_LANDING,
            "reference": {"path": PILOT_HOSTED_REL, "sha256": _file_sha(PILOT_HOSTED_REL), "index": 1,
                          "pairs_file": PILOT_PAIRS_REL, "pairs_file_sha256": _file_sha(PILOT_PAIRS_REL)},
            "reference_checks": {
                "prompts_equal_the_pairs_file_row": (pilot["prompts"]["clinical"] == pilot_pair["top_prompt"]
                                                     and pilot["prompts"]["patient"] == pilot_pair["bottom_prompt"]),
                "label_equals_the_target_text": _label(pilot["target_token"]) == pilot_pair["target_clinical_token"],
                "both_sides_reported": all(pilot["probabilities"][side] is not None
                                           for side in ("clinical", "patient")),
                "graph_model": _read_json(PILOT_HOSTED_REL)["graph_model"],
            },
            "prompt_sha256": {"source": prompt_digest(pilot_pair["top_prompt"]),
                              "recipient": prompt_digest(pilot_pair["bottom_prompt"])},
            "metric": "absolute difference of the two recorded probabilities, per side (2 sides)",
            "preconditions": [
                "the part is completed and its single result has index 1",
                "the pairs file at the fired commit has the SHA-256 recorded here",
                "the candidate's target label equals the reference's label",
                "the reference file has the SHA-256 recorded here",
            ],
            "pass": f"both sides at or below {BF16_EARLIER_MAX_HOSTED}",
            "fail": f"a side above {BF16_EARLIER_MAX_HOSTED}",
            "inconclusive": "a precondition does not hold",
            "pass_max": BF16_EARLIER_MAX_HOSTED,
            "tolerance_source": ("observed, not derived: 0.0315 is the largest of 71 side differences between "
                                 "the hosted route and CPU bfloat16 on pairs_20260710T011743Z "
                                 "(docs/backend_agreement_20260903.md)"),
        },
    }


def _estimate_cli(argv: list[str]) -> dict[str, Any]:
    """Run ``python -m scripts.experiments.estimate`` in process and return its JSON output."""
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = estimate.main(argv)
    assert code == 0, stream.getvalue()
    return json.loads(stream.getvalue())


def build_preview(protocol: dict[str, Any], target_sources: dict[str, dict[str, Any]],
                  token_records: dict[str, Any]) -> dict[str, Any]:
    """Everything the packet quotes about the protocol and its plan. Deterministic: no clock, no random number."""
    rows = _rows()
    summary = validate_protocol(protocol)
    matrix = caps.load_matrix()
    plan = build_plan(protocol, matrix)
    reasons: dict[str, int] = {}
    for task in plan["tasks"]:
        key = f"{task['planned_state']}: {task['reason']}"
        reasons[key] = reasons.get(key, 0) + 1
    selection = _selection(target_sources)
    rate = estimate.recorded_slowest_rates()["seconds_per_pair"][PROXY_RATE_MODEL]
    max_tokens = max(v["token_count"] for row in selection for v in row["variants"].values())
    stage_a_argv = ["--families", "10", "--rate", f"{MODEL_ID}={rate}", "--failed-attempt-fraction",
                    str(FAILED_ATTEMPT_FRACTION)]
    stage_b_argv = ["--families", "1", "--rate", f"{MODEL_ID}={rate}", "--failed-attempt-fraction",
                    str(FAILED_ATTEMPT_FRACTION)]
    protocol_tokens = sum(v["token_count"] for row in selection if row["in_protocol"]
                          for v in row["variants"].values())
    return {
        "schema_version": PREVIEW_SCHEMA,
        "status": "preview_not_run",
        "statement": ("Nothing here was measured on a model. The plan below marks every task unavailable; no "
                      "task is ready and none was executed. Counts, hashes and estimates are computed offline "
                      "from committed files."),
        "protocol": {"path": PROTOCOL_REL, "file_sha256": sha256_bytes(json_bytes(protocol)),
                     "protocol_sha256": summary["protocol_sha256"], "validation": summary},
        "inputs": {
            "batch": {"path": BATCH_REL, "sha256": _file_sha(BATCH_REL), "rows": len(rows)},
            "landed_cpu_part": {"path": CPU_PART_REL, "sha256": _file_sha(CPU_PART_REL)},
            "landed_hosted_part": {"path": HOSTED_PART_REL, "sha256": _file_sha(HOSTED_PART_REL)},
            "capability_matrix": {"path": MATRIX_REL, "file_sha256": _file_sha(MATRIX_REL),
                                  "digest": digest(dict(matrix)), "as_of": matrix.get("as_of")},
            "tier_b_start_stamp": tierb_split.tierb_start_stamp(str(tierb_split.DASHBOARD_PATH)),
        },
        "selection": {
            "rule": ("a row is in the protocol when (1) the landed hosted-lens record of each of its two prompts "
                     "reproduces the prompt from its token strings, (2) the landed CPU part's target label "
                     "equals the target text, so the target is one token, and (3) a landed hosted-lens record "
                     "of this model, from a study batch dated before the Tier B start stamp, holds a prompt "
                     "token with exactly that string"),
            "rows_in_batch": len(rows), "rows_in_protocol": sum(1 for row in selection if row["in_protocol"]),
            "rows": selection,
        },
        "token_records": {
            "scope": LENS_SCOPE, "files_read": token_records["files"], "batches_read": token_records["batches"],
            "distinct_token_strings": len(token_records["by_string"]),
            "distinct_token_ids": len(token_records["by_id"]),
            "strings_recorded_with_more_than_one_id": sum(1 for v in token_records["by_string"].values() if len(v) > 1),
            "ids_recorded_with_more_than_one_string": sum(1 for v in token_records["by_id"].values() if len(v) > 1),
            "not_verified": ("that the hosted service's tokenizer for model id gemma-2-2b is the tokenizer at "
                             "the pinned revision; the service records no tokenizer revision"),
        },
        "commands": [
            f"python -m scripts.experiments.cli validate --protocol {PROTOCOL_REL}",
            f"python -m scripts.experiments.cli plan --protocol {PROTOCOL_REL} --out <directory outside the "
            "checkout>/plan.json",
            "sha256sum <directory outside the checkout>/plan.json",
            "python -m scripts.experiments.estimate " + " ".join(stage_a_argv),
            "python -m scripts.experiments.estimate " + " ".join(stage_b_argv),
        ],
        "plan": {
            "file_sha256": sha256_bytes(json_bytes(plan)), "plan_digest": digest(plan),
            "tasks": plan["totals"]["tasks"], "by_planned_state": plan["totals"]["by_planned_state"],
            "by_method": plan["totals"]["by_method"], "reasons": reasons, "adapters": plan["adapters"],
            "capability": sorted({json.dumps({"status": t["capability"]["status"],
                                              "revision_match": t["capability"]["revision_match"],
                                              "matched": t["capability"]["matched"]}, sort_keys=True)
                                  for t in plan["tasks"]}),
            "estimates": plan["totals"]["estimates"],
            "runtime_seconds_estimate": plan["totals"]["runtime_seconds_estimate"],
            "estimate_notes": plan["estimate_notes"],
        },
        "resource_estimate": {
            "statement": "Arithmetic on stated inputs. No number in this block is a measurement of this model.",
            "rate": {"seconds_per_pair": rate, "of_model": PROXY_RATE_MODEL,
                     "label": "assumption: a proxy; no rate is recorded for gemma-2-2b on the CPU lane",
                     "source": estimate.recorded_slowest_rates()["source"]},
            "failed_attempt_fraction": {"value": FAILED_ATTEMPT_FRACTION, "label": "assumption, a stated allowance"},
            "stage_a": {"argv": stage_a_argv, "output": _estimate_cli(stage_a_argv)},
            "stage_b": {"argv": stage_b_argv, "output": _estimate_cli(stage_b_argv)},
            "weights": {
                "parameters": PARAMETERS_ROUNDED,
                "label": ("derived from the rounded count '2.6B' in docs/model_matrix.md; the exact count is "
                          "not recorded"),
                "float32_bytes": estimate.estimate_weight_bytes(PARAMETERS_ROUNDED, "float32"),
                "bfloat16_bytes": estimate.estimate_weight_bytes(PARAMETERS_ROUNDED, "bfloat16")},
            "recorded_token_counts": {
                "label": "measured: read from the landed hosted-lens records, BOS included",
                "batch_prompts": 2 * len(rows),
                "batch_tokens": sum(v["token_count"] for row in selection for v in row["variants"].values()),
                "max_tokens_per_prompt": max_tokens, "protocol_prompts": 2 * len(protocol["case_families"]),
                "protocol_tokens": protocol_tokens},
            "activation_capture_if_one_were_added": {
                "label": ("derived from the recorded token counts; the two behaviour checks capture no "
                          "activation, so this is the size of the smallest capture section 11 describes"),
                "float32_bytes_all_positions_one_layer": estimate_activation_bytes(
                    protocol_tokens, 1, HIDDEN_SIZE, "float32"),
                "float32_bytes_all_positions_all_layers": estimate_activation_bytes(
                    protocol_tokens, N_LAYERS, HIDDEN_SIZE, "float32")},
        },
        "parity_criteria": _parity(rows),
        # Whether these exist is not recorded here: a landed run must not change this file's expected bytes.
        "landing_paths": {"stage_a": STAGE_A_LANDING, "stage_b": STAGE_B_LANDING},
    }


def render_block(preview: dict[str, Any]) -> str:
    """The generated block of the packet: the values a reader checks against the two committed files."""
    plan, sel, est = preview["plan"], preview["selection"], preview["resource_estimate"]
    lines = [BLOCK_BEGIN, "",
             "| Item | Value |", "|---|---|",
             f"| Protocol file | `{preview['protocol']['path']}` |",
             f"| Protocol file SHA-256 | `{preview['protocol']['file_sha256']}` |",
             f"| Protocol canonical digest (`protocol_sha256`) | `{preview['protocol']['protocol_sha256']}` |",
             f"| Rows of the batch in the protocol | {sel['rows_in_protocol']} of {sel['rows_in_batch']} |",
             f"| Capability matrix file SHA-256 | `{preview['inputs']['capability_matrix']['file_sha256']}` |",
             f"| Planned tasks | {plan['tasks']} |",
             "| Tasks by planned state | " + ", ".join(f"`{state}` {plan['by_planned_state'][state]}"
                                                       for state in ("ready", "unsupported", "unavailable")) + " |",
             f"| Plan file SHA-256 | `{plan['file_sha256']}` |",
             f"| Plan canonical digest | `{plan['plan_digest']}` |",
             f"| Planner token estimate (all tasks; ready tasks) | {plan['estimates']['tokens']}; "
             f"{plan['estimates']['ready_tokens']} |",
             f"| Planner activation bytes (all tasks) | {plan['estimates']['activation_bytes']} |",
             "| Planner runtime estimate | "
             + ("null" if plan["runtime_seconds_estimate"] is None else str(plan["runtime_seconds_estimate"])) + " |",
             f"| Stage A runner seconds (estimate) | {est['stage_a']['output']['time']['runner_seconds']} |",
             f"| Stage B runner seconds (estimate) | {est['stage_b']['output']['time']['runner_seconds']} |",
             "", "Reasons the planner gives, with task counts:", ""]
    lines += [f"- {count} x {reason}" for reason, count in sorted(plan["reasons"].items())]
    lines += ["", "Rows by `(batch, batch_index)` and prompt SHA-256 (clinical side; colloquial side):", "",
              "| Row | In protocol | Reason | Prompt SHA-256 | Tokens |", "|---|---|---|---|---|"]
    for row in sel["rows"]:
        clinical, colloquial = row["variants"]["clinical"], row["variants"]["colloquial"]
        lines.append(f"| `({row['batch']}, {row['batch_index']})` | {'yes' if row['in_protocol'] else 'no'} | "
                     f"`{row['reason']}` | `{clinical['prompt_sha256']}`; `{colloquial['prompt_sha256']}` | "
                     f"{clinical['token_count']}; {colloquial['token_count']} |")
    hosted = preview["parity_criteria"]["stage_a"]["hosted"]
    landed = preview["parity_criteria"]["stage_a"]["landed_baseline_hosted_vs_cpu_bfloat16"]
    misread = landed["sides_where_the_hosted_part_read_another_token"]
    records, counts = preview["token_records"], est["recorded_token_counts"]
    lines += ["", "Stage A sides compared with the hosted part (`batch_index` side): "
              + ", ".join(f"{s['batch_index']} {s['side']}" for s in hosted["comparable_sides"])
              + f". Count: {len(hosted['comparable_sides'])} of {2 * sel['rows_in_batch']}.", "",
              "Landed hosted part against landed CPU bfloat16 part, absolute difference per side (not a result "
              f"of the proposed run): {landed['sides']} comparable sides, maximum {landed['max']}, mean "
              f"{landed['mean']}; {misread['sides']} sides where the hosted part read another token, minimum "
              f"{misread['min']}, maximum {misread['max']}, {misread['above_0.06']} above 0.06.", "",
              f"Hosted-lens records read for token ids: {records['files_read']} files of "
              f"{records['batches_read']} batches, "
              f"{records['distinct_token_strings']} distinct token strings, "
              f"{records['strings_recorded_with_more_than_one_id']} strings with more than one id, "
              f"{records['ids_recorded_with_more_than_one_string']} ids with more than one string. Recorded "
              f"tokens: {counts['batch_tokens']} over the {counts['batch_prompts']} prompts of the batch, at most "
              f"{counts['max_tokens_per_prompt']} per prompt; {counts['protocol_tokens']} over the "
              f"{counts['protocol_prompts']} prompts of the protocol.", "", BLOCK_END]
    return "\n".join(lines)


def _committed_preview() -> dict[str, Any]:
    return _read_json(PREVIEW_REL)


def _target_sources(preview: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["batch_index"]): {"file": row["target_id_record"]["file"],
                                      "position": row["target_id_record"]["position"]}
            for row in preview["selection"]["rows"] if row["in_protocol"]}


def _find_target_sources(token_records: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """For ``--write``: the first landed record (in sorted path order) of each one-token target's string."""
    sources = {}
    for row in _rows():
        if row["single_token"] and row["target"] in token_records["first"]:
            sources[str(row["index"])] = dict(token_records["first"][row["target"]])
    return sources


# ------------------------------------------------------------------------------------------------ tests

@pytest.fixture(scope="module")
def preview() -> dict[str, Any]:
    return _committed_preview()


@pytest.fixture(scope="module")
def protocol() -> dict[str, Any]:
    return _read_json(PROTOCOL_REL)


@pytest.fixture(scope="module")
def token_records() -> dict[str, Any]:
    return scan_token_records()


def test_protocol_is_rebuilt_from_landed_records(preview, protocol):
    """Every prompt, hash and token id of the committed protocol comes out of the batch file and the landed
    records again. A hand-edited token id, prompt or target fails here."""
    rebuilt = build_protocol(_target_sources(preview))
    assert rebuilt == protocol
    assert (ENGINE / PROTOCOL_REL).read_bytes() == json_bytes(rebuilt)


def test_protocol_validates_and_the_seal_check_runs_on_every_family(protocol, monkeypatch):
    """The real validator passes with the real holdout seal, and the seal is asked about each legacy row and
    each colloquial prompt. A stub that reports one row sealed makes the same protocol refuse."""
    calls: list[tuple[Any, Any]] = []
    real = results_policy.row_restriction

    def counting(batch, index, prompt, **kwargs):
        calls.append((batch, index))
        return real(batch, index, prompt, **kwargs)

    monkeypatch.setattr(results_policy, "row_restriction", counting)
    summary = validate_protocol(protocol)
    families = protocol["case_families"]
    assert summary["status"] == "validated" and summary["synthetic"] is False
    assert summary["families_by_split"] == {"discovery": len(families), "validation": 0, "fresh_test": 0}
    joins = sorted((f["legacy_join"]["batch"], f["legacy_join"]["batch_index"]) for f in families)
    assert sorted(c for c in calls if c[0] is not None) == joins
    assert len([c for c in calls if c == (None, None)]) == len(families)

    sealed_index = families[0]["legacy_join"]["batch_index"]
    with pytest.raises(Refusal) as refused:
        validate_protocol(protocol, row_restriction=lambda batch, index, prompt:
                          "sealed_holdout" if index == sealed_index else None)
    assert refused.value.code == "holdout_refusal"
    assert all(v["prompt"] not in str(refused.value) for f in families for v in f["variants"].values())


def test_no_family_is_a_tier_b_row(protocol, preview):
    """The batch predates the Tier B start stamp, so the split rule assigns none of its rows to the holdout,
    and no row is sealed under the phrase rule either."""
    start = tierb_split.tierb_start_stamp(str(tierb_split.DASHBOARD_PATH))
    assert start == preview["inputs"]["tier_b_start_stamp"]
    assert tierb_split.is_tierb_batch(BATCH, start) is False
    for index, pair in enumerate(_read_json(BATCH_REL), 1):
        assert tierb_split.sealed_pair(BATCH, index, pair["top_prompt"]) is False, (BATCH, index)
    assert {f["split"] for f in protocol["case_families"]} == {"discovery"}


def test_model_identity_is_the_recorded_pin(protocol):
    """The protocol names the commit the lane pins and a landed part recorded, and no other."""
    source = (ENGINE / "scripts" / "logits_eval.py").read_text(encoding="utf-8")
    assert f'"{MODEL_ID}": "{PIN}"' in source
    assert _read_json(CPU_PART_REL)["inference"]["revision"] == PIN
    model = protocol["model"]
    assert (model["revision"], model["tokenizer_revision"], model["hf_id"]) == (PIN, PIN, HF_ID)
    assert (model["n_layers"], model["hidden_size"]) == (N_LAYERS, HIDDEN_SIZE)
    meta, _tokens = _lens_prompt_tokens(_lens_rel(1, "clinical"))
    assert len(meta["layers_by_type"]["JACOBIAN_LENS"]) == N_LAYERS


def test_selection_follows_the_rule_and_cites_its_records(preview, protocol):
    """A row is in the protocol exactly when the rule admits it; each cited record has the recorded hash and
    holds the id the protocol uses. No row with a multi-token target is in the protocol."""
    rows = {row["index"]: row for row in _rows()}
    selection = preview["selection"]["rows"]
    assert [row["batch_index"] for row in selection] == list(range(1, len(rows) + 1))
    included = [row for row in selection if row["in_protocol"]]
    assert [f["legacy_join"]["batch_index"] for f in protocol["case_families"]] == \
        [row["batch_index"] for row in included]
    by_index = {f["legacy_join"]["batch_index"]: f for f in protocol["case_families"]}
    for row in selection:
        landed = rows[row["batch_index"]]
        assert (row["target_tokens_in_landed_cpu_part"] == "one") == landed["single_token"]
        for variant in row["variants"].values():
            assert _file_sha(variant["token_id_record"]["file"]) == variant["token_id_record"]["sha256"]
        if row["in_protocol"]:
            assert landed["single_token"]
            record = row["target_id_record"]
            assert _file_sha(record["file"]) == record["sha256"]
            family = by_index[row["batch_index"]]
            assert family["targets"][0]["token_ids"] == [_target_id(record, landed["target"])]
            for name, variant in family["variants"].items():
                assert variant["prompt_sha256"] == row["variants"][name]["prompt_sha256"]
                assert variant["token_sha256"] == row["variants"][name]["token_sha256"]
                assert variant["token_ids"][0] == BOS_ID
        else:
            assert "target_id_record" not in row


def test_landed_token_records_are_one_to_one_and_selection_is_complete(preview, token_records):
    """In the landed hosted-lens records of this model no token string has two ids and no id two strings, and
    every row the rule admits is in the protocol (none was left out by hand)."""
    assert all(len(ids) == 1 for ids in token_records["by_string"].values())
    assert all(len(strings) == 1 for strings in token_records["by_id"].values())
    recorded = preview["token_records"]
    assert recorded["files_read"] == token_records["files"]
    assert recorded["distinct_token_strings"] == len(token_records["by_string"])
    assert recorded["strings_recorded_with_more_than_one_id"] == 0
    assert _find_target_sources(token_records) == _target_sources(preview)


def test_preview_file_is_current(preview, protocol, token_records):
    """The committed preview equals the preview recomputed from the protocol, the capability matrix and the
    landed parts. After a deliberate change to one of those, regenerate with ``--write``."""
    rebuilt = build_preview(protocol, _target_sources(preview), token_records)
    assert rebuilt == preview, ("the preview differs from its inputs; if the change is deliberate run "
                                "`python tests/test_first_run_packet.py --write`")
    assert (ENGINE / PREVIEW_REL).read_bytes() == json_bytes(rebuilt)


def test_cli_validate_and_plan_reproduce_the_preview(preview, tmp_path, capsys):
    """The two documented commands give the recorded protocol digest, task counts, reasons and plan hash."""
    assert cli.main(["validate", "--protocol", str(ENGINE / PROTOCOL_REL)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated == preview["protocol"]["validation"]

    out = tmp_path / "plan.json"
    assert cli.main(["plan", "--protocol", str(ENGINE / PROTOCOL_REL), "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    plan = json.loads(out.read_text(encoding="utf-8"))
    recorded = preview["plan"]
    assert hashlib.sha256(out.read_bytes()).hexdigest() == recorded["file_sha256"]
    assert printed["totals"]["by_planned_state"] == recorded["by_planned_state"]
    assert recorded["by_planned_state"]["ready"] == 0, "no task of a real-model protocol may be planned ready"
    assert recorded["tasks"] == 2 * preview["selection"]["rows_in_protocol"] == len(plan["tasks"])
    assert all(task["planned_state"] == "unavailable" and task["reason"] for task in plan["tasks"])
    assert sum(recorded["reasons"].values()) == recorded["tasks"]
    assert plan["totals"]["runtime_seconds_estimate"] is None and plan["totals"]["estimates"]["measured"] is False
    # No prompt text and no target text reaches the plan.
    text = out.read_text(encoding="utf-8")
    for family in _read_json(PROTOCOL_REL)["case_families"]:
        assert all(variant["prompt"] not in text for variant in family["variants"].values())


def test_resource_estimate_is_the_estimator_output(preview):
    """Each estimate in the preview is what ``scripts/experiments/estimate.py`` prints for the recorded
    arguments, the rate is the recorded proxy, and every block says it is not a measurement."""
    est = preview["resource_estimate"]
    for stage in ("stage_a", "stage_b"):
        assert _estimate_cli(est[stage]["argv"]) == est[stage]["output"]
        assert est[stage]["output"]["time"]["measured"] is False
    assert est["rate"]["seconds_per_pair"] == estimate.recorded_slowest_rates()["seconds_per_pair"][PROXY_RATE_MODEL]
    assert MODEL_ID not in estimate.recorded_slowest_rates()["seconds_per_pair"], \
        "a rate for gemma-2-2b is now recorded: use it and drop the proxy"
    assert est["stage_a"]["output"]["time"]["runner_seconds"] == pytest.approx(12 * 88.5)
    assert est["stage_b"]["output"]["time"]["runner_seconds"] == pytest.approx(2 * 88.5)
    assert est["weights"]["float32_bytes"] == 4 * PARAMETERS_ROUNDED


def test_parity_sets_are_fixed_from_landed_files(preview):
    """The sides compared with the hosted part are exactly those where the hosted part reports a value for
    the token the CPU part read. The thresholds are present and ordered, and the references are pinned."""
    parity = preview["parity_criteria"]
    assert parity["status"] == "proposed_before_any_run_not_approved"
    hosted = parity["stage_a"]["hosted"]
    expected = [{"batch_index": row["index"], "side": side} for row in _rows() for side, _k, _v in SIDES
                if row["hosted_label"] == row["cpu_label"] and row["hosted"][side] is not None]
    assert hosted["comparable_sides"] == expected
    assert len(hosted["comparable_sides"]) + len(hosted["excluded_sides"]) == 20
    assert 0 < hosted["pass_max"] < hosted["fail_above"]
    bf16 = parity["stage_a"]["cpu_bfloat16"]
    assert 0 < bf16["consistent_max"] < bf16["fail_above"] and bf16["sides"] == 20
    for block in (hosted, bf16):
        assert _file_sha(block["reference"]["path"]) == block["reference"]["sha256"]
        assert block["pass" if "pass" in block else "consistent"] and block["fail"] and block["inconclusive"]
        assert block["tolerance_source"]
    stage_b = parity["stage_b"]
    assert _file_sha(stage_b["reference"]["path"]) == stage_b["reference"]["sha256"]
    assert _file_sha(stage_b["reference"]["pairs_file"]) == stage_b["reference"]["pairs_file_sha256"]
    assert stage_b["reference_checks"] == {"prompts_equal_the_pairs_file_row": True,
                                           "label_equals_the_target_text": True,
                                           "both_sides_reported": True, "graph_model": MODEL_ID}
    assert stage_b["pass"] and stage_b["fail"] and stage_b["inconclusive"] and stage_b["tolerance_source"]
    # The earlier audit's figures the thresholds cite are still what the landed reports say.
    interp_local = _read_json("ops/backend_agreement_interp_vs_local_20260904.json")["probability"]
    assert (interp_local["n"], interp_local["max"]) == (100, BF16_EARLIER_MAX_INTERP)
    assert _read_json("ops/backend_agreement_20260903.json")["probability"]["max"] == BF16_EARLIER_MAX_HOSTED


def test_packet_quotes_the_preview_and_holds_no_stimulus_text(preview, protocol):
    """The packet's generated block is the rendering of the committed preview, and neither the packet, the
    preview nor this file holds a prompt of the batch or of the reviewed pilot case."""
    packet = (ENGINE / PACKET_REL).read_text(encoding="utf-8")
    assert packet.count(BLOCK_BEGIN) == 1 and packet.count(BLOCK_END) == 1
    block = packet[packet.index(BLOCK_BEGIN):packet.index(BLOCK_END) + len(BLOCK_END)]
    assert block == render_block(preview), ("the packet's generated block is stale; run "
                                            "`python tests/test_first_run_packet.py --write`")
    prompts = [pair[key] for pair in _read_json(BATCH_REL) for key in ("top_prompt", "bottom_prompt")]
    pilot = _read_json(PILOT_PAIRS_REL)[0]
    prompts += [pilot["top_prompt"], pilot["bottom_prompt"]]
    assert len(prompts) == 22 and all(len(p) > 20 for p in prompts)
    for rel in (PACKET_REL, PREVIEW_REL, "tests/test_first_run_packet.py",
                "data/experiments/protocols/README.md"):
        text = (ENGINE / rel).read_text(encoding="utf-8")
        assert not [i for i, prompt in enumerate(prompts) if prompt in text], rel
    # The protocol is the one file that holds prompt text, and only for the rows it covers.
    held = (ENGINE / PROTOCOL_REL).read_text(encoding="utf-8")
    assert pilot["top_prompt"] not in held and pilot["bottom_prompt"] not in held
    assert all("publication:prompt_text_approved" not in family["facts"] for family in protocol["case_families"])


def test_packet_prose_repeats_the_preview_numbers(preview):
    """Numbers the packet states in prose, outside the generated block, are the preview's. A regenerated
    preview with other counts fails here until the prose is corrected."""
    packet = (ENGINE / PACKET_REL).read_text(encoding="utf-8")
    prose = packet[:packet.index(BLOCK_BEGIN)] + packet[packet.index(BLOCK_END):]
    parity = preview["parity_criteria"]["stage_a"]
    landed = parity["landed_baseline_hosted_vs_cpu_bfloat16"]
    misread = landed["sides_where_the_hosted_part_read_another_token"]
    records, est, sel = preview["token_records"], preview["resource_estimate"], preview["selection"]
    counts = est["recorded_token_counts"]
    mismatched_rows = sorted({s["batch_index"] for s in parity["hosted"]["excluded_sides"]
                              if s["reason"] == "hosted_part_read_another_token_than_the_cpu_part"})
    expected = [
        f"**{sel['rows_in_protocol']} of the {sel['rows_in_batch']} stage A rows**",
        f"plans {preview['plan']['tasks']} tasks, all `unavailable`",
        f"compared with the hosted route on {len(parity['hosted']['comparable_sides'])} sides",
        "batch indices " + ", ".join(str(i) for i in mismatched_rows[:-1]) + f" and {mismatched_rows[-1]}",
        f"between {misread['min']} and {misread['max']} on those {misread['sides']} sides "
        f"({misread['above_0.06']} of them above 0.06)",
        f"maximum {landed['max']}, mean {landed['mean']:.4f}",
        f"In the {records['files_read']} records read",
        f"{records['batches_read']} study batches before the Tier B start stamp",
        f"{records['distinct_token_strings']:,} distinct token strings",
        f"{counts['batch_tokens']} over the {counts['batch_prompts']} prompts, at most "
        f"{counts['max_tokens_per_prompt']} per prompt",
        f"{counts['protocol_tokens']} tokens over {preview['plan']['tasks']} tasks",
        f"{est['stage_a']['output']['time']['runner_seconds']:,.0f} runner seconds",
        f"{est['stage_b']['output']['time']['runner_seconds']:,.0f} runner seconds",
        f"pass at or below {parity['hosted']['pass_max']}, fail above {parity['hosted']['fail_above']:.4f}",
        f"at or below {parity['cpu_bfloat16']['consistent_max']}",
        f"above {parity['cpu_bfloat16']['fail_above']:.4f}",
        f"at or below {preview['parity_criteria']['stage_b']['pass_max']}",
        preview["inputs"]["batch"]["sha256"], preview["inputs"]["landed_cpu_part"]["sha256"],
        preview["inputs"]["landed_hosted_part"]["sha256"],
        preview["parity_criteria"]["stage_b"]["reference"]["sha256"],
        preview["parity_criteria"]["stage_b"]["reference"]["pairs_file_sha256"],
        preview["parity_criteria"]["stage_b"]["prompt_sha256"]["source"],
        preview["parity_criteria"]["stage_b"]["prompt_sha256"]["recipient"],
        preview["inputs"]["tier_b_start_stamp"],
    ]
    flat = " ".join(prose.split())
    missing = [text for text in expected if text not in flat]
    assert not missing, missing


# Paths the packet names that do not exist, each on purpose. A path that starts to exist (a landed stage, a
# written adapter) does not fail the test; a path missing for any other reason does.
EXPECTED_ABSENT = {
    STAGE_A_LANDING: "stage A's landing path; nothing has been fired",
    f"trace_out/verify_{BATCH}__{MODEL_ID}": "stage A's landing directory",
    STAGE_B_LANDING: "stage B's landing path; nothing has been fired",
    "pilot/logits": "the pilot logits root has no landed run",
    "pilot/logits/": "the pilot logits root has no landed run",
    "pilot/runs/pilot_v2_20261002/trace/pilot_v2_20261002_trace_pairs.json": "prerequisite 10, not written",
    "scripts/experiments/adapters/behavior_landed_part.py": "section 8, item 5: a proposed file",
    "data/results_catalogue/index.json": "a path in the site repository",
}


def test_packet_paths_exist_or_are_declared_absent():
    """Every repository path the packet names exists, except the ones listed above with their reason. Uses
    the path reader of tests/test_doc_paths.py (inline code spans and fenced blocks)."""
    import test_doc_paths as doc_paths

    repo = doc_paths.make_repo(doc_paths._listed_paths())
    packet = (ENGINE / PACKET_REL).read_text(encoding="utf-8")
    missing = set(doc_paths.missing_paths(packet, repo))
    assert missing <= set(EXPECTED_ABSENT), sorted(missing - set(EXPECTED_ABSENT))
    readme = (PROTOCOL_DIR / "README.md").read_text(encoding="utf-8")
    assert doc_paths.missing_paths(readme, repo) == []


def test_packet_ends_with_owner_decisions_and_has_the_next_step_section():
    """The two sections the packet must keep: the separate smallest-next-step section, and the closing list
    of decisions for the owner, each worded as a yes or no question with a cost ceiling."""
    packet = (ENGINE / PACKET_REL).read_text(encoding="utf-8")
    headings = [line for line in packet.splitlines() if line.startswith("## ")]
    assert any("Smallest next step that exercises a real activation capture and a fitted basis through the viewer"
               in heading for heading in headings)
    assert "Decisions that need the owner" in headings[-1]
    closing = packet[packet.index(headings[-1]):]
    decisions = re.findall(r"^\d+\. \*\*(.+?)\*\*", closing, re.M | re.S)
    assert len(decisions) >= 4 and all(question.rstrip().endswith("?") for question in decisions)
    assert "Cost ceiling" in closing


# --------------------------------------------------------------------------------------------- generator

def _write() -> int:
    """Regenerate the protocol, the preview and the packet's generated block. Prints each file's status."""
    token_records = scan_token_records()
    sources = _find_target_sources(token_records)
    protocol = build_protocol(sources)
    preview = build_preview(protocol, sources, token_records)
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    for rel, obj in ((PROTOCOL_REL, protocol), (PREVIEW_REL, preview)):
        path, data = ENGINE / rel, json_bytes(obj)
        changed = not path.exists() or path.read_bytes() != data
        if changed:
            path.write_bytes(data)
        print(f"{'wrote' if changed else 'unchanged'} {rel} sha256 {sha256_bytes(data)}")
    packet_path = ENGINE / PACKET_REL
    packet = packet_path.read_text(encoding="utf-8")
    if packet.count(BLOCK_BEGIN) != 1 or packet.count(BLOCK_END) != 1:
        print(f"{PACKET_REL}: the generated block markers are missing; the packet was not changed")
        return 1
    start, end = packet.index(BLOCK_BEGIN), packet.index(BLOCK_END) + len(BLOCK_END)
    updated = packet[:start] + render_block(preview) + packet[end:]
    if updated != packet:
        packet_path.write_text(updated, encoding="utf-8")
    print(f"{'wrote' if updated != packet else 'unchanged'} {PACKET_REL} (generated block)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", required=True,
                        help="regenerate the protocol, the preview and the packet's generated block")
    parser.parse_args()
    raise SystemExit(_write())
