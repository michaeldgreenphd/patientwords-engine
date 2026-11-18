#!/usr/bin/env python3
"""Build a read-only per-case multi-instrument record from landed trace_out summaries.

Reads summary parts across the eight mechanistic and next-token lanes under
``trace_out/`` without loading any model or tokenizer, without choosing a winner
among duplicate parts, and without computing any cross-instrument agreement
statistic, threshold, or composite quantity. Sealed Tier B holdout pairs are
excluded via ``scripts.tierb_split.sealed_pair``. Output JSON holds identifiers,
SHA-256 hashes, numbers, and flags only — never prompt or token text — and may
only be written outside every Git checkout and outside protected roots.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from scripts.experiments.common import (  # noqa: E402
    Refusal,
    atomic_write_json,
    check_output_path,
    digest,
    integer,
    prompt_digest,
    require,
    sha256_file,
    text,
)
from scripts.frontend_contract_schema import check_schema_subset  # noqa: E402
from scripts.sparse_guard import hidden_tracked  # noqa: E402
from scripts.tierb_split import (  # noqa: E402
    SealError,
    is_tierb_batch,
    seal_config_error,
    sealed_pair,
    tierb_start_stamp,
)

SCHEMA_VERSION = "patientwords.multi-instrument-case/1"
SCHEMA_PATH = ENGINE_ROOT / "schemas" / "multi_instrument_case.v1.schema.json"

INSTRUMENT_ORDER: tuple[str, ...] = (
    "hosted_graph",
    "cpu_logits",
    "activation_patching",
    "jacobian_lens",
    "logit_lens",
    "lens_steering",
    "depth_probe",
    "float32_verify",
)

HOSTED_GRAPH_MODES = frozenset({"2panel", "4quadrant", "dialect", "translation"})
NON_SUMMARY_SUFFIXES = (".report.json", "_probe.json")
PART_NUM_RE = re.compile(r"\.part_(\d+)\.json\Z")
DEPTH_PREFIX_RE = re.compile(r"^depth_(?:k\d+_)?")
OUTPUT_WRAPPER_RE = re.compile(r'Output "(.*)"\Z', flags=re.DOTALL)

CHECK_FLAG_NAMES: tuple[str, ...] = (
    "prompt_sha256_match",
    "prompt_missing_on_instrument",
    "target_label_match",
    "target_label_raw_match",
    "target_label_missing_on_instrument",
    "hosted_target_read_recorded",
    "revision_recorded",
    "any_revision_recorded",
    "revisions_match",
    "duplicate_parts_present",
    "duplicate_value_conflict",
)

EXIT_OK = 0
EXIT_REFUSED = 1


def classify_instrument(summary: Mapping[str, Any], *, where: str = "<summary>") -> str:
    """Identify one of the eight instruments from the summary's backend, mode, and lens_type."""
    backend = summary.get("backend")
    mode = summary.get("mode")
    lens_type = summary.get("lens_type")
    if backend == "hosted" and mode in HOSTED_GRAPH_MODES and lens_type is None:
        return "hosted_graph"
    if backend == "logits" and mode == "2panel" and lens_type is None:
        return "cpu_logits"
    if backend == "activation_patch" and mode == "2panel" and lens_type is None:
        return "activation_patching"
    if backend == "jlens-hosted" and mode == "jlens" and lens_type == "JACOBIAN_LENS":
        return "jacobian_lens"
    if backend == "jlens-hosted" and mode == "jlens" and lens_type == "LOGIT_LENS":
        return "logit_lens"
    if backend == "jlens-hosted" and mode == "jsteer" and lens_type is None:
        return "lens_steering"
    if backend == "interp-engine-eager" and mode == "depth_probe" and lens_type is None:
        return "depth_probe"
    if backend == "interp-engine" and mode == "2panel" and lens_type is None:
        return "float32_verify"
    raise Refusal(
        "unknown_instrument",
        f"{where}: unsupported (backend={backend!r}, mode={mode!r}, lens_type={lens_type!r})",
    )


def parse_stem(run_dir_name: str, model: str, instrument: str) -> str:
    """Derive the stimulus-set stem from a run directory name and summary metadata.

    Preserves stimulus-arm suffixes such as ``__context`` and ``__lenspairs`` while
    stripping lane/model suffixes and ``verify_`` / ``depth_`` / ``depth_k<N>_`` prefixes.
    """
    stem = run_dir_name
    suffixes = (
        f"__jlens_{model}",
        f"__loglens_{model}",
        f"__jsteer_{model}",
        f"__patch_{model}",
        "__patch",
        f"__{model}",
    )
    for suffix in suffixes:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            stem = stem[: -len(suffix)]
            break
    if instrument == "float32_verify" and stem.startswith("verify_"):
        stem = stem[len("verify_") :]
    elif instrument == "depth_probe":
        stem = DEPTH_PREFIX_RE.sub("", stem)
    require(text(stem), "invalid_stem", f"empty stem derived from run directory {run_dir_name!r}")
    return stem


def unwrap_output_label(label: str) -> tuple[str, bool]:
    """Strip only the literal ``Output "<token>"`` wrapper, keeping inner whitespace and case."""
    match = OUTPUT_WRAPPER_RE.fullmatch(label)
    if match is not None:
        return match.group(1), True
    return label, False


def _part_sort_key(run_dir: str, filename: str) -> tuple[str, int, int, str]:
    match = PART_NUM_RE.search(filename)
    if match is not None:
        return (run_dir, 0, int(match.group(1)), filename)
    return (run_dir, 1, 0, filename)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_num(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _optional_int(value: Any) -> int | None:
    return value if type(value) is int else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _hash_optional_str(value: Any) -> str | None:
    return prompt_digest(value) if isinstance(value, str) else None


def _extract_prompt_hashes(
    row: Mapping[str, Any],
    instrument: str,
    summary_mode: str,
    *,
    where: str,
) -> tuple[dict[str, str] | None, str | None]:
    """Return ``(prompt_sha256_map, clinical_prompt_for_seal)`` without retaining prompt text."""
    if instrument == "lens_steering":
        return None, None
    if summary_mode == "dialect":
        baseline = row.get("baseline_prompt")
        require(isinstance(baseline, str) and bool(baseline), "missing_prompt", f"{where}: missing baseline_prompt")
        hashes: dict[str, str] = {"baseline": prompt_digest(baseline)}
        variants = row.get("variants")
        if isinstance(variants, list):
            for idx, entry in enumerate(variants, start=1):
                if isinstance(entry, dict) and isinstance(entry.get("prompt"), str):
                    hashes[f"variant_{idx}"] = prompt_digest(entry["prompt"])
        return hashes, baseline
    prompts = row.get("prompts")
    require(isinstance(prompts, dict) and bool(prompts), "missing_prompt", f"{where}: missing prompts object")
    out: dict[str, str] = {}
    for key, val in sorted(prompts.items()):
        require(isinstance(val, str), "invalid_prompt", f"{where}: prompts[{key!r}] is not a string")
        out[key] = prompt_digest(val)
    if summary_mode == "4quadrant":
        clin = prompts.get("A")
        require(isinstance(clin, str) and bool(clin), "missing_prompt", f"{where}: 4quadrant row lacks prompts['A']")
        return out, clin
    clin = prompts.get("clinical")
    require(
        isinstance(clin, str) and bool(clin),
        "missing_prompt",
        f"{where}: paired row lacks non-empty prompts['clinical']",
    )
    return out, clin


def _extract_provenance(
    summary: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    part_rel: str,
    part_sha256: str,
    run_dir: str,
    prompt_hashes: dict[str, str] | None,
) -> dict[str, Any]:
    inference = summary.get("inference") if isinstance(summary.get("inference"), dict) else {}
    raw_target = row.get("target_token")
    if isinstance(raw_target, str):
        unwrapped, wrapped = unwrap_output_label(raw_target)
        target_recorded = True
        raw_sha = prompt_digest(raw_target)
        inner_sha = prompt_digest(unwrapped)
        has_wrapper: bool | None = wrapped
    else:
        target_recorded = False
        raw_sha = None
        inner_sha = None
        has_wrapper = None
    return {
        "part_path": part_rel,
        "part_sha256": part_sha256,
        "run_dir": run_dir,
        "backend": str(summary.get("backend")),
        "mode": str(summary.get("mode")),
        "lens_type": _optional_str(summary.get("lens_type")),
        "revision": _optional_str(inference.get("revision")),
        "dtype": _optional_str(inference.get("dtype")),
        "device": _optional_str(inference.get("device")),
        "environment": _optional_str(inference.get("environment")),
        "prompt_sha256": prompt_hashes,
        "target_label_recorded": target_recorded,
        "target_label_raw_sha256": raw_sha,
        "target_label_sha256": inner_sha,
        "target_has_output_wrapper": has_wrapper,
    }


def _extract_spread_summary(row: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, str | None], dict[str, float | int | None]]:
    spread = row.get("predictive_spread") if isinstance(row.get("predictive_spread"), dict) else {}
    counts: dict[str, int] = {}
    top1_sha: dict[str, str | None] = {}
    top1_prob: dict[str, float | int | None] = {}
    for side in ("clinical", "patient"):
        items = spread.get(side)
        if isinstance(items, list):
            counts[side] = len(items)
            if items and isinstance(items[0], (list, tuple)) and len(items[0]) == 2 and isinstance(items[0][0], str):
                inner, _ = unwrap_output_label(items[0][0])
                top1_sha[side] = prompt_digest(inner)
                top1_prob[side] = _optional_num(items[0][1])
            else:
                top1_sha[side] = None
                top1_prob[side] = None
        else:
            counts[side] = 0
            top1_sha[side] = None
            top1_prob[side] = None
    return counts, top1_sha, top1_prob


def _extract_hosted_graph_values(summary: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    row_mode = _optional_str(row.get("mode")) or _optional_str(summary.get("mode"))
    probs_raw = row.get("probabilities")
    probs: dict[str, float | int | None] | None = None
    if isinstance(probs_raw, dict):
        probs = {k: _optional_num(v) for k, v in sorted(probs_raw.items())}
    elif row_mode == "dialect" and "baseline_probability" in row:
        probs = {"baseline": _optional_num(row.get("baseline_probability"))}

    dialect_variants: list[dict[str, Any]] | None = None
    if isinstance(row.get("variants"), list):
        dialect_variants = [
            {
                "dialect": str(entry.get("dialect", "")),
                "probability": _optional_num(entry.get("probability")),
                "delta_vs_baseline": _optional_num(entry.get("delta_vs_baseline")),
            }
            for entry in row["variants"]
            if isinstance(entry, dict)
        ]

    cm_raw = row.get("clinical_mass")
    clinical_mass = {k: _optional_num(v) for k, v in sorted(cm_raw.items())} if isinstance(cm_raw, dict) else None
    es_raw = row.get("error_share")
    error_share = {k: _optional_num(v) for k, v in sorted(es_raw.items())} if isinstance(es_raw, dict) else None
    cd_raw = row.get("circuit_diff")
    circuit_diff = {k: _optional_num(v) for k, v in sorted(cd_raw.items())} if isinstance(cd_raw, dict) else None

    tp_raw = row.get("top_path")
    top_path_sha256: dict[str, str | None] | None = None
    if isinstance(tp_raw, dict):
        top_path_sha256 = {k: _hash_optional_str(v) for k, v in sorted(tp_raw.items())}

    screening = row.get("screening") if isinstance(row.get("screening"), dict) else None
    tr_raw = row.get("target_read")
    target_read_recorded = isinstance(tr_raw, dict)
    target_read: dict[str, Any] | None = None
    if isinstance(tr_raw, dict):
        target_read = {
            "rule": _optional_str(tr_raw.get("rule")),
            "match": _optional_str(tr_raw.get("match")),
            "substituted": _optional_bool(tr_raw.get("substituted")),
            "reference_side": _optional_str(tr_raw.get("reference_side")),
            "intended_target_sha256": _hash_optional_str(tr_raw.get("intended_target")),
            "measured_token_sha256": _hash_optional_str(tr_raw.get("measured_token")),
        }

    return {
        "row_mode": row_mode,
        "source_set": _optional_str(summary.get("source_set")),
        "probabilities": probs,
        "dialect_variants": dialect_variants,
        "language_penalty": _optional_num(row.get("language_penalty")),
        "flipped": _optional_bool(row.get("flipped")),
        "clinical_mass": clinical_mass,
        "error_share": error_share,
        "circuit_diff": circuit_diff,
        "top_path_sha256": top_path_sha256,
        "screening_status": _optional_str(screening.get("status")) if screening else None,
        "anchor_fallback": _optional_bool(row.get("anchor_fallback")),
        "target_read_recorded": target_read_recorded,
        "target_read": target_read,
        "has_feature_steering": bool(row.get("steering") or row.get("steering_boost")),
        "mitigation_recovery": _optional_num(row.get("mitigation_recovery")),
    }


def _extract_logits_values(row: Mapping[str, Any], *, include_parity: bool) -> dict[str, Any]:
    probs_raw = row.get("probabilities") if isinstance(row.get("probabilities"), dict) else {}
    probs = {
        "clinical": _optional_num(probs_raw.get("clinical")),
        "patient": _optional_num(probs_raw.get("patient")),
    }
    spread_counts, top1_sha, top1_prob = _extract_spread_summary(row)
    parity_raw = row.get("token_parity") if include_parity and isinstance(row.get("token_parity"), dict) else None
    token_parity = {k: _optional_bool(v) for k, v in sorted(parity_raw.items())} if parity_raw is not None else None
    return {
        "probabilities": probs,
        "language_penalty": _optional_num(row.get("language_penalty")),
        "flipped": _optional_bool(row.get("flipped")),
        "anchor_fallback": _optional_bool(row.get("anchor_fallback")),
        "spread_counts": spread_counts,
        "top1_token_sha256": top1_sha,
        "top1_prob": top1_prob,
        "token_parity": token_parity,
    }


def _extract_patch_values(row: Mapping[str, Any], *, where: str) -> dict[str, Any]:
    patching = row.get("patching")
    require(isinstance(patching, dict), "malformed_patch", f"{where}: missing patching object")
    probs_raw = row.get("probabilities") if isinstance(row.get("probabilities"), dict) else {}
    probs = {
        "clinical": _optional_num(probs_raw.get("clinical")),
        "patient": _optional_num(probs_raw.get("patient")),
    }
    layers_raw = patching.get("layers")
    require(isinstance(layers_raw, list) and all(integer(x) for x in layers_raw), "malformed_patch", f"{where}: layers")
    pos_raw = patching.get("positions")
    require(isinstance(pos_raw, list), "malformed_patch", f"{where}: positions")
    positions: list[dict[str, Any]] = []
    for entry in pos_raw:
        if isinstance(entry, dict) and integer(entry.get("index")):
            positions.append(
                {
                    "index": entry["index"],
                    "aligned_clean_index": _optional_int(entry.get("aligned_clean_index")),
                    "token_sha256": _hash_optional_str(entry.get("token")),
                }
            )
    recovery_raw = patching.get("recovery")
    patched_raw = patching.get("patched_prob")
    require(isinstance(recovery_raw, list) and isinstance(patched_raw, list), "malformed_patch", f"{where}: grids")
    recovery = [[_optional_num(cell) for cell in layer_row] for layer_row in recovery_raw if isinstance(layer_row, list)]
    patched_prob = [
        [_optional_num(cell) for cell in layer_row] for layer_row in patched_raw if isinstance(layer_row, list)
    ]
    return {
        "probabilities": probs,
        "language_penalty": _optional_num(row.get("language_penalty")),
        "hook_point": _optional_str(patching.get("hook_point")),
        "metric": _optional_str(patching.get("metric")),
        "placeholder": bool(patching.get("placeholder", False)),
        "align": _optional_str(patching.get("align")),
        "clean_prob": _optional_num(patching.get("clean_prob")),
        "corrupt_prob": _optional_num(patching.get("corrupt_prob")),
        "layers": list(layers_raw),
        "positions": positions,
        "recovery": recovery,
        "patched_prob": patched_prob,
    }


def _extract_lens_values(summary: Mapping[str, Any], row: Mapping[str, Any], *, where: str) -> dict[str, Any]:
    depth_raw = row.get("depth")
    require(isinstance(depth_raw, dict), "malformed_lens", f"{where}: missing depth object")
    depth: dict[str, list[dict[str, Any]]] = {}
    for side, entries in sorted(depth_raw.items()):
        require(isinstance(entries, list), "malformed_lens", f"{where}: depth[{side!r}] is not a list")
        side_rows: list[dict[str, Any]] = []
        for item in entries:
            require(isinstance(item, dict) and integer(item.get("layer")), "malformed_lens", f"{where}: layer entry")
            side_rows.append(
                {
                    "layer": item["layer"],
                    "target_rank": _optional_int(item.get("target_rank")),
                    "match": _optional_str(item.get("match")),
                    "top1_sha256": _hash_optional_str(item.get("top1")),
                }
            )
        depth[side] = side_rows
    ps_raw = row.get("parse_status") if isinstance(row.get("parse_status"), dict) else {}
    fl_raw = row.get("first_layer") if isinstance(row.get("first_layer"), dict) else {}
    lr_raw = row.get("last_layer_rank") if isinstance(row.get("last_layer_rank"), dict) else {}
    return {
        "top_n": _optional_int(summary.get("top_n")),
        "parse_status": {k: _optional_str(v) for k, v in sorted(ps_raw.items())},
        "first_layer": {k: _optional_int(v) for k, v in sorted(fl_raw.items())},
        "last_layer_rank": {k: _optional_int(v) for k, v in sorted(lr_raw.items())},
        "patient_depth_class": _optional_str(row.get("patient_depth_class")),
        "depth": depth,
    }


def _extract_steer_values(summary: Mapping[str, Any], row: Mapping[str, Any], *, where: str) -> dict[str, Any]:
    calls_raw = row.get("calls")
    require(isinstance(calls_raw, dict), "malformed_steer", f"{where}: missing calls object")
    calls: dict[str, dict[str, Any]] = {}
    for call_key, call_val in sorted(calls_raw.items()):
        require(isinstance(call_val, dict), "malformed_steer", f"{where}: calls[{call_key!r}] is not an object")
        calls[call_key] = {
            "first_layer": _optional_int(call_val.get("first_layer")),
            "final_rank": _optional_int(call_val.get("final_rank")),
            "parse_status": _optional_str(call_val.get("parse_status")),
            "completion_sha256": _hash_optional_str(call_val.get("completion")),
        }
    layers_raw = summary.get("layers") if isinstance(summary.get("layers"), list) else []
    strengths_raw = summary.get("strengths") if isinstance(summary.get("strengths"), list) else []
    return {
        "spec": _optional_str(summary.get("spec")),
        "spec_row_index": _optional_int(row.get("index")),
        "trajectory_class": _optional_str(row.get("class")),
        "layers": [x for x in layers_raw if integer(x)],
        "strengths": [float(x) for x in strengths_raw if isinstance(x, (int, float)) and not isinstance(x, bool)],
        "top_n": _optional_int(summary.get("top_n")),
        "winner_label_sha256": _hash_optional_str(row.get("winner_token")),
        "calls": calls,
    }


def _extract_depth_probe_values(summary: Mapping[str, Any], row: Mapping[str, Any], *, topk: int, where: str) -> dict[str, Any]:
    inst_meta = summary.get("instrument") if isinstance(summary.get("instrument"), dict) else {}
    curves_raw = row.get("curves")
    require(isinstance(curves_raw, dict), "malformed_depth_probe", f"{where}: missing curves object")
    curves: dict[str, list[dict[str, Any]]] = {}
    for side, entries in sorted(curves_raw.items()):
        require(isinstance(entries, list), "malformed_depth_probe", f"{where}: curves[{side!r}] is not a list")
        side_rows: list[dict[str, Any]] = []
        for item in entries:
            require(
                isinstance(item, dict) and integer(item.get("layer")),
                "malformed_depth_probe",
                f"{where}: depth curve entry lacks integer layer",
            )
            side_rows.append(
                {
                    "layer": item["layer"],
                    "expected_tier": _optional_num(item.get("expected_tier")),
                    "coverage": _optional_num(item.get("coverage")),
                    "top_sha256": _hash_optional_str(item.get("top")),
                }
            )
        curves[side] = side_rows
    gap_raw = row.get("gap")
    require(isinstance(gap_raw, list), "malformed_depth_probe", f"{where}: missing gap list")
    return {
        "topk": topk,
        "min_coverage": _optional_num(inst_meta.get("min_coverage")),
        "divergence_threshold": _optional_num(inst_meta.get("divergence_threshold")),
        "first_divergence_layer": _optional_int(row.get("first_divergence_layer")),
        "final_gap": _optional_num(row.get("final_gap")),
        "max_abs_gap": _optional_num(row.get("max_abs_gap")),
        "layers_informative": _optional_int(row.get("layers_informative")),
        "layers_measured": _optional_int(row.get("layers_measured")),
        "gap": [_optional_num(x) for x in gap_raw],
        "curves": curves,
    }


def _candidate_fingerprint(candidate: Mapping[str, Any]) -> str:
    prov = candidate["provenance"]
    return digest(
        {
            "values": candidate["values"],
            "prompt_sha256": prov["prompt_sha256"],
            "target_label_raw_sha256": prov["target_label_raw_sha256"],
        }
    )


def _build_candidate_block(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        candidates,
        key=lambda c: _part_sort_key(c["provenance"]["run_dir"], Path(c["provenance"]["part_path"]).name),
    )
    duplicate_parts = len(ordered) > 1
    value_conflict = len({_candidate_fingerprint(c) for c in ordered}) > 1
    return {
        "duplicate_parts": duplicate_parts,
        "value_conflict": value_conflict,
        "candidates": ordered,
    }


def _load_derivation_links(
    data_dirs: Iterable[Path],
) -> dict[tuple[str, int], tuple[dict[str, Any] | None, dict[str, Any] | None]]:
    """Scan stimulus batch JSON files for per-item ``derived_from`` and ``downgrade_source`` links."""
    links: dict[tuple[str, int], tuple[dict[str, Any] | None, dict[str, Any] | None]] = {}
    seen_stems: set[str] = set()
    for directory in data_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            lower_name = path.name.lower()
            if "holdout" in lower_name or "sealed" in lower_name:
                continue
            if path.name.endswith((".report.json", ".meta.json", ".build.json")):
                continue
            if path.stem in seen_stems:
                continue
            try:
                items = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(items, list) or not items or not isinstance(items[0], dict):
                continue
            seen_stems.add(path.stem)
            for idx, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                gen = item.get("generation") if isinstance(item.get("generation"), dict) else {}
                raw_df = gen.get("derived_from") if "derived_from" in gen else item.get("derived_from")
                raw_ds = gen.get("downgrade_source") if "downgrade_source" in gen else item.get("downgrade_source")
                df_link: dict[str, Any] | None = None
                ds_link: dict[str, Any] | None = None
                if isinstance(raw_df, dict) and text(raw_df.get("batch")) and integer(raw_df.get("index"), 1):
                    raw_batch = str(raw_df["batch"])
                    df_link = {
                        "batch": raw_batch.removesuffix(".json"),
                        "raw_batch": raw_batch,
                        "index": raw_df["index"],
                        "variant": _optional_int(raw_df.get("variant")),
                        "quadrant": _optional_str(raw_df.get("quadrant")),
                    }
                if isinstance(raw_ds, dict) and text(raw_ds.get("batch")) and integer(raw_ds.get("index"), 1):
                    raw_batch = str(raw_ds["batch"])
                    models_raw = raw_ds.get("models")
                    models = [str(m) for m in models_raw if isinstance(m, str)] if isinstance(models_raw, list) else None
                    ds_link = {
                        "batch": raw_batch.removesuffix(".json"),
                        "raw_batch": raw_batch,
                        "index": raw_ds["index"],
                        "models": models,
                    }
                if df_link is not None or ds_link is not None:
                    links[(path.stem, idx)] = (df_link, ds_link)
    return links


def _iter_case_candidates(instruments_block: Mapping[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for inst_name in INSTRUMENT_ORDER:
        block = instruments_block.get(inst_name)
        if block is None:
            continue
        if inst_name == "depth_probe":
            for topk_key in sorted(block["by_topk"], key=int):
                for cand in block["by_topk"][topk_key]["candidates"]:
                    yield inst_name, cand
        else:
            for cand in block["candidates"]:
                yield inst_name, cand


def _comparable_prompt_tuple(prompt_hashes: Mapping[str, str]) -> tuple[Any, ...]:
    if "clinical" in prompt_hashes and "patient" in prompt_hashes:
        return ("paired", prompt_hashes["clinical"], prompt_hashes["patient"])
    if all(k in prompt_hashes for k in ("A", "B", "C", "D")):
        return ("4quadrant", prompt_hashes["A"], prompt_hashes["B"], prompt_hashes["C"], prompt_hashes["D"])
    return ("other", tuple(sorted(prompt_hashes.items())))


def compute_case_checks(instruments_block: Mapping[str, Any]) -> dict[str, bool | None]:
    """Compute per-case check flags from recorded strings and metadata only."""
    prompt_tuples_by_inst: dict[str, set[tuple[Any, ...]]] = defaultdict(set)
    prompt_missing = False

    target_sha_by_inst: dict[str, set[str]] = defaultdict(set)
    target_raw_sha_by_inst: dict[str, set[str]] = defaultdict(set)
    target_missing = False

    revisions_present: list[str] = []
    all_have_revision = True
    any_candidate = False

    for inst_name, cand in _iter_case_candidates(instruments_block):
        any_candidate = True
        prov = cand["provenance"]
        p_hashes = prov["prompt_sha256"]
        if p_hashes is None:
            prompt_missing = True
        else:
            prompt_tuples_by_inst[inst_name].add(_comparable_prompt_tuple(p_hashes))

        if inst_name != "depth_probe":
            if prov["target_label_recorded"] and prov["target_label_sha256"] is not None:
                target_sha_by_inst[inst_name].add(prov["target_label_sha256"])
                target_raw_sha_by_inst[inst_name].add(prov["target_label_raw_sha256"])
            else:
                target_missing = True

        rev = prov["revision"]
        if isinstance(rev, str) and rev:
            revisions_present.append(rev)
        else:
            all_have_revision = False

    if len(prompt_tuples_by_inst) < 2:
        prompt_match: bool | None = None
    else:
        merged_prompts = set().union(*prompt_tuples_by_inst.values())
        prompt_match = len(merged_prompts) == 1

    if len(target_sha_by_inst) < 2:
        target_match: bool | None = None
        target_raw_match: bool | None = None
    else:
        target_match = len(set().union(*target_sha_by_inst.values())) == 1
        target_raw_match = len(set().union(*target_raw_sha_by_inst.values())) == 1

    hosted_block = instruments_block.get("hosted_graph")
    if hosted_block is None:
        hosted_target_read: bool | None = None
    else:
        hosted_target_read = all(c["values"]["target_read_recorded"] for c in hosted_block["candidates"])

    revision_recorded = bool(any_candidate and all_have_revision)
    any_revision = bool(revisions_present)
    if len(revisions_present) < 2:
        revisions_match: bool | None = None
    else:
        revisions_match = len(set(revisions_present)) == 1

    dup_present = any(block["duplicate_parts"] for block in instruments_block.values())
    dup_conflict = any(block["value_conflict"] for block in instruments_block.values())

    return {
        "prompt_sha256_match": prompt_match,
        "prompt_missing_on_instrument": prompt_missing,
        "target_label_match": target_match,
        "target_label_raw_match": target_raw_match,
        "target_label_missing_on_instrument": target_missing,
        "hosted_target_read_recorded": hosted_target_read,
        "revision_recorded": revision_recorded,
        "any_revision_recorded": any_revision,
        "revisions_match": revisions_match,
        "duplicate_parts_present": dup_present,
        "duplicate_value_conflict": dup_conflict,
    }


def engine_head_commit(engine_root: Path) -> str | None:
    """Return ``git rev-parse HEAD`` when ``engine_root`` is inside a Git repository, else None."""
    if not (engine_root / ".git").exists():
        return None
    try:
        return subprocess.check_output(
            ["git", "-C", str(engine_root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def validate_output_document(doc: Mapping[str, Any], schema_path: Path = SCHEMA_PATH) -> None:
    """Validate ``doc`` against ``schemas/multi_instrument_case.v1.schema.json``."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    check_schema_subset(
        lambda _artifact, where, why: errors.append(f"{where}: {why}"),
        "multi_instrument_case",
        doc,
        schema,
    )
    require(
        not errors,
        "schema_violation",
        "multi_instrument_case schema errors: "
        + "; ".join(errors[:5])
        + (f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""),
    )


def build_multi_instrument_records(
    *,
    trace_root: Path,
    data_dirs: Iterable[Path] = (),
    dashboard_path: Path | None = None,
    simulated_dir: Path | None = None,
    engine_root: Path | None = None,
) -> dict[str, Any]:
    """Read landed summary parts under ``trace_root`` and assemble unsealed per-case records.

    Raises ``SealError`` if the Tier B holdout seal cannot be evaluated, and
    ``Refusal`` if ``trace_root`` is missing, sparse, or contains malformed summaries.
    """
    resolved_trace = trace_root.resolve()
    require(resolved_trace.is_dir(), "missing_trace_root", f"{resolved_trace} is not a directory")

    if engine_root is not None and (engine_root / ".git").exists():
        hidden = [
            p
            for p in hidden_tracked(engine_root, "trace_out")
            if p.count("/") == 2 and p.endswith(".json") and not p.endswith(NON_SUMMARY_SUFFIXES)
        ]
        if hidden:
            raise Refusal(
                "sparse_checkout",
                f"engine checkout hides {len(hidden)} tracked summary file(s) under trace_out/, e.g. {hidden[0]}",
            )

    dash = Path(dashboard_path) if dashboard_path is not None else (ENGINE_ROOT / "ops" / "dashboard.json")
    sim = Path(simulated_dir) if simulated_dir is not None else (ENGINE_ROOT / "data" / "simulated")
    # Force eager seal-context validation even when trace_root holds zero rows.
    sealed_pair(None, None, "placeholder_probe_string", dashboard_path=dash, simulated_dir=sim)
    tierb_start = tierb_start_stamp(str(dash))

    search_data_dirs = list(data_dirs) if data_dirs else [
        sim,
        ENGINE_ROOT / "data" / "measured",
        ENGINE_ROOT / "data" / "pab",
    ]
    derivation_links = _load_derivation_links(search_data_dirs)

    part_files_read = 0
    non_summary_skipped = 0

    # (stem, index, model) -> instrument -> list[candidate] (or {topk: list[candidate]} for depth_probe)
    grouped: dict[tuple[str, int, str], dict[str, Any]] = defaultdict(dict)
    sealed_pairs: set[tuple[str, int]] = set()
    # Keep clinical prompts seen per (stem, index) so source-pair Tier B checks have a prompt string.
    pair_clinical_prompts: dict[tuple[str, int], str] = {}

    for run_dir in sorted(p for p in resolved_trace.iterdir() if p.is_dir()):
        lower_dir = run_dir.name.lower()
        require(
            "holdout" not in lower_dir and "sealed" not in lower_dir,
            "restricted_directory_name",
            f"refusing to open directory naming holdout or sealed: {run_dir.name}",
        )
        for part_file in sorted(run_dir.glob("*.json")):
            lower_file = part_file.name.lower()
            require(
                "holdout" not in lower_file and "sealed" not in lower_file,
                "restricted_file_name",
                f"refusing to open file naming holdout or sealed: {run_dir.name}/{part_file.name}",
            )
            if part_file.name.endswith(NON_SUMMARY_SUFFIXES):
                non_summary_skipped += 1
                continue

            part_rel = f"{run_dir.name}/{part_file.name}"
            try:
                summary = json.loads(part_file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise Refusal("unreadable_summary", f"{part_rel}: {type(exc).__name__}: {exc}") from exc
            require(
                isinstance(summary, dict) and isinstance(summary.get("results"), list),
                "malformed_summary",
                f"{part_rel}: expected JSON object with a 'results' list",
            )

            instrument = classify_instrument(summary, where=part_rel)
            model = summary.get("graph_model")
            require(text(model), "missing_model", f"{part_rel}: summary lacks non-empty 'graph_model'")
            model_str = str(model)

            topk_val: int | None = None
            if instrument == "depth_probe":
                inst_meta = summary.get("instrument")
                topk_raw = inst_meta.get("topk") if isinstance(inst_meta, dict) else None
                require(integer(topk_raw, 1), "missing_topk", f"{part_rel}: depth_probe lacks integer instrument.topk")
                topk_val = int(topk_raw)

            dir_stem: str | None = None
            if instrument != "lens_steering":
                dir_stem = parse_stem(run_dir.name, model_str, instrument)

            part_hash = sha256_file(part_file)
            part_files_read += 1

            for row_pos, row in enumerate(summary["results"]):
                where = f"{part_rel}[results[{row_pos}]]"
                require(isinstance(row, dict), "malformed_row", f"{where}: row is not an object")

                if instrument == "lens_steering":
                    raw_ds = row.get("dataset")
                    spec_idx = row.get("spec_index")
                    require(
                        text(raw_ds) and integer(spec_idx, 1),
                        "malformed_steer_key",
                        f"{where}: lens_steering requires non-empty 'dataset' and 1-based 'spec_index'",
                    )
                    stem = str(raw_ds).removesuffix(".json")
                    idx = int(spec_idx)
                else:
                    assert dir_stem is not None
                    raw_idx = row.get("index")
                    require(integer(raw_idx, 1), "malformed_index", f"{where}: row 'index' must be a 1-based integer")
                    stem = dir_stem
                    idx = int(raw_idx)

                prompt_hashes, clin_for_seal = _extract_prompt_hashes(
                    row, instrument, str(summary.get("mode")), where=where
                )
                if clin_for_seal is not None and (stem, idx) not in pair_clinical_prompts:
                    pair_clinical_prompts[(stem, idx)] = clin_for_seal

                if sealed_pair(stem, idx, clin_for_seal, dashboard_path=dash, simulated_dir=sim):
                    sealed_pairs.add((stem, idx))

                prov = _extract_provenance(
                    summary,
                    row,
                    part_rel=part_rel,
                    part_sha256=part_hash,
                    run_dir=run_dir.name,
                    prompt_hashes=prompt_hashes,
                )

                if instrument == "hosted_graph":
                    values = _extract_hosted_graph_values(summary, row)
                elif instrument == "cpu_logits":
                    values = _extract_logits_values(row, include_parity=False)
                elif instrument == "float32_verify":
                    values = _extract_logits_values(row, include_parity=True)
                elif instrument == "activation_patching":
                    values = _extract_patch_values(row, where=where)
                elif instrument in ("jacobian_lens", "logit_lens"):
                    values = _extract_lens_values(summary, row, where=where)
                elif instrument == "lens_steering":
                    values = _extract_steer_values(summary, row, where=where)
                elif instrument == "depth_probe":
                    assert topk_val is not None
                    values = _extract_depth_probe_values(summary, row, topk=topk_val, where=where)
                else:  # pragma: no cover
                    raise AssertionError(f"unhandled instrument {instrument!r}")

                candidate = {"provenance": prov, "values": values}
                case_map = grouped[(stem, idx, model_str)]
                if instrument == "depth_probe":
                    assert topk_val is not None
                    topk_map = case_map.setdefault("depth_probe", defaultdict(list))
                    topk_map[topk_val].append(candidate)
                else:
                    case_map.setdefault(instrument, []).append(candidate)

    # Propagate pair-level seal to derived pairs whose source pair is sealed.
    for (stem, idx, _model) in list(grouped):
        if (stem, idx) in sealed_pairs:
            continue
        df_link, ds_link = derivation_links.get((stem, idx), (None, None))
        clin = pair_clinical_prompts.get((stem, idx))
        for link in (df_link, ds_link):
            if link is None:
                continue
            src_pair = (link["batch"], link["index"])
            if src_pair in sealed_pairs:
                sealed_pairs.add((stem, idx))
                break
            if is_tierb_batch(src_pair[0], tierb_start) and sealed_pair(
                src_pair[0], src_pair[1], clin, dashboard_path=dash, simulated_dir=sim
            ):
                sealed_pairs.add(src_pair)
                sealed_pairs.add((stem, idx))
                break

    cases: list[dict[str, Any]] = []
    sealed_cases_excluded = 0
    sealed_pairs_with_cases: set[tuple[str, int]] = set()
    derived_cases_count = 0

    by_inst_count: Counter[int] = Counter()
    by_instrument: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    by_stem: Counter[str] = Counter()
    flag_tallies: dict[str, dict[str, int]] = {
        flag: {"true": 0, "false": 0, "null": 0} for flag in CHECK_FLAG_NAMES
    }

    for stem, idx, model_str in sorted(grouped):
        if (stem, idx) in sealed_pairs:
            sealed_cases_excluded += 1
            sealed_pairs_with_cases.add((stem, idx))
            continue

        raw_inst_map = grouped[(stem, idx, model_str)]
        instruments_block: dict[str, Any] = {}
        present_list: list[str] = []

        for inst_name in INSTRUMENT_ORDER:
            if inst_name not in raw_inst_map:
                continue
            present_list.append(inst_name)
            by_instrument[inst_name] += 1
            if inst_name == "depth_probe":
                topk_raw_map: dict[int, list[dict[str, Any]]] = raw_inst_map["depth_probe"]
                by_topk_block: dict[str, Any] = {}
                for topk_int in sorted(topk_raw_map):
                    slot = _build_candidate_block(topk_raw_map[topk_int])
                    by_topk_block[str(topk_int)] = {
                        "topk": topk_int,
                        "duplicate_parts": slot["duplicate_parts"],
                        "value_conflict": slot["value_conflict"],
                        "candidates": slot["candidates"],
                    }
                instruments_block["depth_probe"] = {
                    "duplicate_parts": any(s["duplicate_parts"] for s in by_topk_block.values()),
                    "value_conflict": any(s["value_conflict"] for s in by_topk_block.values()),
                    "by_topk": by_topk_block,
                }
            else:
                instruments_block[inst_name] = _build_candidate_block(raw_inst_map[inst_name])

        df_link, ds_link = derivation_links.get((stem, idx), (None, None))
        source_key: dict[str, Any] | None = None
        if df_link is not None:
            source_key = {
                "stem": df_link["batch"],
                "index": df_link["index"],
                "model": model_str,
                "via": "derived_from",
            }
        elif ds_link is not None:
            source_key = {
                "stem": ds_link["batch"],
                "index": ds_link["index"],
                "model": model_str,
                "via": "downgrade_source",
            }
        if source_key is not None:
            derived_cases_count += 1

        checks = compute_case_checks(instruments_block)
        for flag_name in CHECK_FLAG_NAMES:
            val = checks[flag_name]
            bucket = "null" if val is None else ("true" if val else "false")
            flag_tallies[flag_name][bucket] += 1

        inst_count = len(present_list)
        by_inst_count[inst_count] += 1
        by_model[model_str] += 1
        by_stem[stem] += 1

        cases.append(
            {
                "key": {"stem": stem, "index": idx, "model": model_str},
                "source_key": source_key,
                "derived_from": df_link,
                "downgrade_source": ds_link,
                "instrument_count": inst_count,
                "instruments_present": present_list,
                "checks": checks,
                "instruments": instruments_block,
            }
        )

    commit_root = engine_root if engine_root is not None else ENGINE_ROOT
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine_commit": engine_head_commit(commit_root),
        "counts": {
            "part_files_read": part_files_read,
            "non_summary_json_skipped": non_summary_skipped,
            "sealed_pairs_excluded": len(sealed_pairs_with_cases),
            "sealed_cases_excluded": sealed_cases_excluded,
            "case_count": len(cases),
            "derived_cases_with_source_key": derived_cases_count,
            "by_instrument_count": {str(k): by_inst_count[k] for k in sorted(by_inst_count)},
            "by_instrument": {name: by_instrument[name] for name in INSTRUMENT_ORDER if by_instrument[name]},
            "by_model": {m: by_model[m] for m in sorted(by_model)},
            "by_stem": {s: by_stem[s] for s in sorted(by_stem)},
            "flags": flag_tallies,
        },
        "cases": cases,
    }
    validate_output_document(doc)
    return doc


def write_records(path: Path | str, doc: Mapping[str, Any], *, allow_roots: Iterable[Path | str] = ()) -> Path:
    """Validate output path outside Git checkouts and protected roots, validate schema, and write atomically."""
    resolved = check_output_path(path, allow_roots)
    validate_output_document(doc)
    atomic_write_json(resolved, doc)
    return resolved


def format_terminal_summary(doc: Mapping[str, Any]) -> str:
    """Render a plain-text summary of counts by instrument count, model, stem, and check flags."""
    counts = doc["counts"]
    lines: list[str] = [
        f"schema_version: {doc['schema_version']}",
        f"engine_commit: {doc['engine_commit']}",
        f"part_files_read: {counts['part_files_read']}",
        f"non_summary_json_skipped: {counts['non_summary_json_skipped']}",
        f"sealed_pairs_excluded: {counts['sealed_pairs_excluded']}",
        f"sealed_cases_excluded: {counts['sealed_cases_excluded']}",
        f"case_count: {counts['case_count']}",
        f"derived_cases_with_source_key: {counts['derived_cases_with_source_key']}",
        "",
        "Cases by number of instruments:",
    ]
    for k_str in sorted(counts["by_instrument_count"], key=int):
        lines.append(f"  {k_str}: {counts['by_instrument_count'][k_str]}")

    lines.append("")
    lines.append("Cases by instrument:")
    for inst_name in INSTRUMENT_ORDER:
        if inst_name in counts["by_instrument"]:
            lines.append(f"  {inst_name}: {counts['by_instrument'][inst_name]}")

    lines.append("")
    lines.append("Cases by model:")
    for model_name, n_cases in sorted(counts["by_model"].items()):
        lines.append(f"  {model_name}: {n_cases}")

    lines.append("")
    lines.append("Check flags (true / false / null):")
    for flag_name in CHECK_FLAG_NAMES:
        tally = counts["flags"][flag_name]
        lines.append(f"  {flag_name}: true={tally['true']} false={tally['false']} null={tally['null']}")

    # Compute per-stem instrument-count breakdown from cases for clear multi-instrument visibility.
    stem_breakdown: dict[str, Counter[int]] = defaultdict(Counter)
    for case in doc["cases"]:
        stem_breakdown[case["key"]["stem"]][case["instrument_count"]] += 1

    lines.append("")
    lines.append(f"Cases by stem ({len(counts['by_stem'])} stems):")
    for stem_name, n_cases in sorted(counts["by_stem"].items()):
        bd = stem_breakdown[stem_name]
        detail = ", ".join(f"{k}-inst={bd[k]}" for k in sorted(bd))
        lines.append(f"  {stem_name}: {n_cases} ({detail})")

    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace-root",
        type=Path,
        default=ENGINE_ROOT / "trace_out",
        help="Directory holding landed summary subdirectories (default: <engine>/trace_out).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON path (must be outside every Git checkout and outside protected roots).",
    )
    parser.add_argument(
        "--dashboard",
        type=Path,
        default=None,
        help="Optional override for ops/dashboard.json used by sealed_pair.",
    )
    parser.add_argument(
        "--simulated-dir",
        type=Path,
        default=None,
        help="Optional override for data/simulated directory used by sealed_pair.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        action="append",
        default=[],
        help="Optional stimulus batch directory to scan for derived_from / downgrade_source (repeatable).",
    )
    parser.add_argument(
        "--allow-root",
        type=Path,
        action="append",
        default=[],
        help="Lift the Git-checkout output guard under this directory (never lifts protected-root names).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: validate output path first, build records, write JSON, and print summary."""
    args = build_arg_parser().parse_args(argv)
    try:
        check_output_path(args.out, args.allow_root)
        engine_root = ENGINE_ROOT if args.trace_root.resolve() == (ENGINE_ROOT / "trace_out").resolve() else None
        doc = build_multi_instrument_records(
            trace_root=args.trace_root,
            data_dirs=args.data_dir,
            dashboard_path=args.dashboard,
            simulated_dir=args.simulated_dir,
            engine_root=engine_root,
        )
        write_records(args.out, doc, allow_roots=args.allow_root)
    except SealError as exc:
        return seal_config_error(exc, stream=sys.stderr)
    except Refusal as exc:
        print(f"REFUSED [{exc.code}]: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    print(format_terminal_summary(doc))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
