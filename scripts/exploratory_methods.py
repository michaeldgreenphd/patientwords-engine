"""Offline contracts and scoring for isolated exploratory method comparisons.

This module does not load models, contact services, or publish measurements.
JSON inputs carry all domain annotations. Ranks use the complete vocabulary;
filtered ranks never change the softmax denominator. Synthetic fixtures are not
measurements. Runtime adapters remain in their respective method repositories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "patientwords.exploratory/1"
METHODS = {"logit_lens", "j_lens", "jpp"}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class Refusal(ValueError):
    """A named, serializable contract violation."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise Refusal(code, detail)


def digest(value: Any) -> str:
    """SHA256 of canonical UTF-8 JSON, also used for token arrays and specs."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def prompt_digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def integer(value: Any, lower: int = 0) -> bool:
    return type(value) is int and value >= lower


def finite_vector(values: Any) -> list[float]:
    require(isinstance(values, list) and bool(values), "missing_logits", "Full vocabulary logits are required")
    require(all(type(x) in (float, int) and math.isfinite(x) for x in values),
            "invalid_logits", "Logits must be finite numbers")
    return values


def suffix_alignment(donor: list[int], recipient: list[int]) -> list[list[int]]:
    """Return [recipient, donor] token-ID pairs under the legacy suffix rule."""
    require(all(integer(x) for x in donor + recipient), "invalid_token_ids", "Expected token IDs")
    count = 0
    while count < min(len(donor), len(recipient)) and donor[-count - 1] == recipient[-count - 1]:
        count += 1
    return [[len(recipient) - count + i, len(donor) - count + i] for i in range(count)]


def span_positions(offsets: list[list[int]], span: list[int]) -> list[int]:
    """Intersect a half-open character span with explicit tokenizer offsets.

    Special tokens with empty offsets are excluded. Boundary-crossing tokens
    are retained and are observable in the returned position list.
    """
    require(len(span) == 2 and all(integer(x) for x in span) and span[0] < span[1],
            "invalid_span", "Expected a nonempty half-open character span")
    require(all(len(x) == 2 and all(integer(v) for v in x) and x[0] <= x[1] for x in offsets),
            "invalid_offsets", "Expected ordered token offsets")
    nonempty = [x for x in offsets if x[0] < x[1]]
    require(nonempty == sorted(nonempty), "invalid_offsets", "Offsets must follow input order")
    positions = [i for i, (a, b) in enumerate(offsets) if a < b and a < span[1] and b > span[0]]
    require(bool(positions), "unaligned_span", "No token intersects the requested span")
    return positions


def seeded_groups(width: int, size: int, seeds: list[int], layer: int) -> list[dict[str, Any]]:
    require(integer(width, 1) and integer(size, 1) and size <= width and integer(layer),
            "invalid_control_size", "Random groups must match layer and channel count")
    require(bool(seeds) and len(set(seeds)) == len(seeds) and all(integer(s) for s in seeds),
            "invalid_seeds", "Distinct explicit random seeds are required")
    return [{"layer": layer, "seed": seed, "channels": sorted(random.Random(seed).sample(range(width), size))}
            for seed in seeds]


def token_match(token: str, target: str, encoded_target: list[int], token_id: int) -> str | None:
    """Exact ID matching and prefix proxies are deliberately different outputs."""
    if len(encoded_target) == 1 and encoded_target[0] == token_id and token == target:
        return "exact"
    if (len(encoded_target) > 1 and encoded_target[0] == token_id and token
            and target.startswith(token) and token != target):
        return "first_wordpiece_proxy"
    if token and target.startswith(token) and token != target:
        return "text_prefix_proxy"
    return None


def _validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    require(isinstance(spec, dict), "invalid_input", "Specification must be an object")
    require(spec.get("schema_version") == SCHEMA, "schema_version", "Unknown exploratory schema")
    require(type(spec.get("synthetic")) is bool, "missing_provenance", "synthetic flag is required")
    require(spec.get("publication") == "exploratory_only", "publication_gate", "Publication is not enabled")
    require(spec.get("output_namespace") == "exploratory_methods", "output_namespace", "Wrong output namespace")
    require(integer(spec.get("seed")), "missing_seed", "Explicit seed is required")
    plans = spec.get("intervention_plan")
    plan_fields = {"id", "case_id", "donor", "recipient", "kind", "component", "layer", "positions",
                   "channels", "control", "seed"}
    require(isinstance(plans, list) and (bool(plans) or not spec["synthetic"])
            and all(isinstance(p, dict) and plan_fields <= p.keys()
                    and isinstance(p["id"], str) and bool(p["id"])
                    and (p["control"] != "random"
                         or (isinstance(p.get("matched_to"), str) and bool(p["matched_to"]))) for p in plans)
            and len({p["id"] for p in plans}) == len(plans), "intervention_plan",
            "An explicit plan is required; validated synthetic plans need unique prespecified interventions")
    vocabulary_filter = spec.get("vocabulary_filter")
    require(isinstance(vocabulary_filter, dict) and isinstance(vocabulary_filter.get("id"), str)
            and bool(vocabulary_filter["id"]) and isinstance(vocabulary_filter.get("excluded"), list)
            and all(isinstance(x, dict) and integer(x.get("token_id"))
                    and isinstance(x.get("reason"), str) and bool(x["reason"])
                    for x in vocabulary_filter["excluded"]), "filter_metadata",
            "An explicit filter ID and exclusion list with token IDs and reasons are required")
    model = spec.get("model", {})
    require(isinstance(model, dict), "invalid_input", "Model must be an object")
    for key in ("id", "study_id", "tokenizer_id", "precision", "backend"):
        require(isinstance(model.get(key), str) and bool(model[key]), "missing_model_metadata", key)
    for key in ("revision", "tokenizer_revision"):
        require(bool(HEX40.fullmatch(str(model.get(key, "")))), "missing_revision", key)
    for key in ("hidden_size", "intermediate_size", "n_layers"):
        require(integer(model.get(key), 1), "missing_dimensions", key)
    require(type(spec.get("gap_threshold")) in (int, float) and math.isfinite(spec["gap_threshold"])
            and spec["gap_threshold"] > 0, "gap_threshold", "Positive, finite prespecified threshold required")
    settings = spec.get("input_settings", {})
    require(settings == {"chat_template": None, "thinking": "not_applied_raw_prompt", "add_special_tokens": True,
                         "truncation": False}, "input_settings", "Raw-prompt settings must be explicit")
    require(spec.get("capture_site") == "block_output" and integer(spec.get("layer_index_base"))
            and spec["layer_index_base"] == 0,
            "capture_mismatch", "Only zero-based block outputs are supported by this slice")
    require(spec.get("final_norm") == "model_final_norm_once_then_lm_head", "final_norm", "Unknown norm convention")
    methods = spec.get("methods", {})
    require(set(methods) == METHODS, "method_metadata", "Three explicitly named comparison methods are required")
    intersection: set[int] | None = None
    blockers = []
    for name, info in methods.items():
        layers = info.get("source_layers")
        require(isinstance(layers, list) and bool(layers) and all(integer(x) for x in layers)
                and len(layers) == len(set(layers)), "layer_metadata", name)
        require(info.get("method") == name, "method_metadata", name)
        require(info.get("capture_site") == spec["capture_site"] and info.get("final_norm") == spec["final_norm"],
                "capture_mismatch", name)
        require(max(layers) < model["n_layers"], "layer_metadata", "Layer outside model")
        intersection = set(layers) if intersection is None else intersection & set(layers)
        if name != "logit_lens":
            for key in ("artifact_sha256", "repository_revision"):
                pattern = HEX64 if key == "artifact_sha256" else HEX40
                require(bool(pattern.fullmatch(str(info.get(key, "")))), "lens_hash", name + ":" + key)
            require(integer(info.get("transport_target")), "layer_metadata", name + ":transport_target")
            require(info["transport_target"] < model["n_layers"], "layer_metadata", "Transport outside model")
            require(max(layers) < info["transport_target"], "layer_metadata", "Source must precede transport target")
            require(info.get("model_id") == model["id"], "model_mismatch", name)
            for key, model_key in (("model_revision", "revision"), ("tokenizer_revision", "tokenizer_revision")):
                if info.get(key) is None:
                    blockers.append(name + ":unknown_" + key)
                else:
                    require(info[key] == model[model_key], "model_mismatch", name + ":" + key)
    require(bool(intersection), "no_common_layers", "No intersecting fitted layers")
    require(isinstance(spec.get("fixed_layers"), list) and bool(spec["fixed_layers"])
            and all(integer(x) for x in spec["fixed_layers"]) and set(spec["fixed_layers"]) <= intersection,
            "fixed_layers", "Fixed layers must be prespecified in the intersection")
    require(methods["j_lens"]["transport_target"] == methods["jpp"]["transport_target"],
            "transport_mismatch", "Both fitted lenses must target the same block output")
    require(isinstance(spec.get("top_k"), list) and len(spec["top_k"]) >= 2
            and all(integer(k, 1) for k in spec["top_k"]) and len(set(spec["top_k"])) == len(spec["top_k"]),
            "top_k", "At least two distinct explicit k values required")
    families: dict[str, str] = {}
    templates: dict[str, str] = {}
    source_joins: dict[tuple[str, int, str], str] = {}
    prompts: dict[str, str] = {}
    cases = spec.get("cases")
    require(isinstance(cases, list) and bool(cases), "missing_cases", "At least one case is required")
    ids = set()
    for case in cases:
        require(case.get("id") and case["id"] not in ids, "duplicate_case", "Case IDs must be unique")
        ids.add(case["id"])
        split = case.get("split")
        require(split in {"discovery", "validation", "fresh_test"}, "split", "Unknown split")
        for key, seen in (("family_id", families), ("template_family", templates)):
            value = case.get(key)
            require(isinstance(value, str) and bool(value), "missing_family", key)
            require(value not in seen or seen[value] == split, "split_leakage", key + ":" + value)
            seen[value] = split
        require(case.get("holdout_status") == "unsealed_reviewed", "holdout_refusal", case["id"])
        require(case.get("join", {}).get("model") == model["study_id"]
                and integer(case.get("join", {}).get("index"), 1)
                and bool(case.get("join", {}).get("batch")), "missing_join", case["id"])
        source_join = (case["join"]["batch"], case["join"]["index"], case["join"]["model"])
        require(source_join not in source_joins or source_joins[source_join] == split,
                "split_leakage", "The same source join occurs in different splits")
        source_joins[source_join] = split
        targets = case.get("targets", [])
        require({x.get("role") for x in targets} == {"intermediate", "answer"},
                "target_roles", "Intermediate and final answer annotations must be distinct")
        require(len({t.get("id") for t in targets}) == len(targets), "target_ids", "Duplicate target ID")
        for target in targets:
            require(isinstance(target.get("id"), str) and bool(target["id"]), "target_ids", "Target ID required")
            require(isinstance(target.get("text"), str) and bool(target["text"]), "target_text", case["id"])
            token_ids = target.get("token_ids")
            if token_ids is None and not spec["synthetic"]:
                blockers.append(case["id"] + ":target_tokenization_pending")
            else:
                require(isinstance(token_ids, list) and bool(token_ids) and all(integer(t) for t in token_ids),
                        "target_token_ids", target["id"])
        variants = case.get("variants", {})
        require({"source", "recipient"} <= set(variants), "variants", "Both directions require original variants")
        for variant, entry in variants.items():
            require(isinstance(entry.get("prompt"), str), "missing_prompt", variant)
            require(entry.get("prompt_sha256") == prompt_digest(entry["prompt"]), "prompt_hash", variant)
            prompt_hash = entry["prompt_sha256"]
            require(prompt_hash not in prompts or prompts[prompt_hash] == split,
                    "split_leakage", "The same prompt occurs in different splits")
            prompts[prompt_hash] = split
            token_ids = entry.get("token_ids")
            if token_ids is None and not spec["synthetic"]:
                blockers.append(case["id"] + ":prompt_tokenization_pending")
                continue
            require(isinstance(token_ids, list) and bool(token_ids) and all(integer(t) for t in token_ids),
                    "invalid_token_ids", variant)
            require(entry.get("token_sha256") == digest(token_ids), "token_hash", variant)
            require(entry.get("positions") == list(range(len(token_ids))), "position_coverage",
                    "This bounded slice requires all input positions, including early ones")
    if not spec["synthetic"]:
        blockers.extend(["real_model_baseline_parity_unrun", "ci_execution_adapter_not_wired"])
        if not plans:
            blockers.append("intervention_plan_pending")
    return {"schema_version": SCHEMA, "status": "blocked" if blockers else "validated",
            "blockers": sorted(set(blockers)), "common_layers": sorted(intersection), "spec_sha256": digest(spec)}


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a specification, with named refusals for malformed JSON shapes."""
    try:
        return _validate_spec(spec)
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", str(exc)) from exc


def strict_hosted_metadata(response: dict[str, Any], method: str) -> list[int]:
    """Validate observed schema without issuing a network request or fallback."""
    allowed = {"logit_lens": "LOGIT_LENS", "j_lens": "JACOBIAN_LENS", "jpp": "JPP_LENS"}
    require(method in allowed, "unsupported_method", method)
    kind = allowed[method]
    layers = response.get("meta", {}).get("layers_by_type", {}).get(kind)
    require(isinstance(layers, list) and bool(layers) and all(integer(x) for x in layers)
            and len(set(layers)) == len(layers), "layer_metadata", "Missing actual returned layers")
    require(isinstance(response.get("tokens"), list) and bool(response["tokens"]), "missing_positions", "No tokens")
    for token in response["tokens"]:
        entries = [x for x in token.get("results", []) if x.get("type") == kind]
        require(len(entries) == 1, "method_metadata", "Requested method was not returned exactly once")
        require(len(entries[0].get("top_tokens", [])) == len(layers), "layer_metadata", "Layer count mismatch")
    return layers


def rank_target(logits: list[float], target: dict[str, Any], excluded: set[int], top_k: list[int]) -> dict[str, Any]:
    """Descending-logit ranks, ties by smaller token ID; denominator stays full."""
    logits = finite_vector(logits)
    token_ids = target["token_ids"]
    require(all(t < len(logits) for t in token_ids), "target_outside_vocab", target["id"])
    token_id = token_ids[0]
    def outranks(i: int, x: float) -> bool:
        return x > logits[token_id] or (x == logits[token_id] and i < token_id)
    rank = 1 + sum(outranks(i, x) for i, x in enumerate(logits))
    filtered = None if token_id in excluded else 1 + sum(
        outranks(i, x) for i, x in enumerate(logits) if i not in excluded)
    peak = max(logits)
    probability = math.exp(logits[token_id] - peak) / sum(math.exp(x - peak) for x in logits)
    return {"target_id": target["id"], "role": target["role"], "token_id": token_id,
            "matching": "exact_token" if len(token_ids) == 1 else "first_wordpiece_proxy",
            "exact_sequence_score": None, "sequence_status": "single_token" if len(token_ids) == 1 else "not_scored",
            "raw_rank": rank, "filtered_rank": filtered, "excluded_candidate": token_id in excluded,
            "full_vocab_probability": probability,
            "top_k": {str(k): "observed" if rank <= k else "not_observed_in_window" for k in top_k}}


def patch_effect(source: float, recipient: float, patched: float, epsilon: float) -> dict[str, Any]:
    require(all(math.isfinite(x) for x in (source, recipient, patched, epsilon)) and epsilon > 0,
            "invalid_effect", "Finite effects and positive gap threshold required")
    gap, delta = source - recipient, patched - recipient
    return {"baseline_gap": gap, "raw_probability_delta": delta,
            "normalized_recovery": delta / gap if gap > epsilon else None,
            "recovery_status": "computable" if gap > epsilon else "nonpositive_or_near_zero_gap",
            "gap_threshold": epsilon}


def _build_report(spec: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    validation = validate_spec(spec)
    require(validation["status"] == "validated", "execution_blocked", ",".join(validation["blockers"]))
    require(spec["synthetic"] and packet.get("execution_status") == "synthetic", "not_measurement",
            "This first slice accepts synthetic evidence only; real CI ingestion needs a reviewed follow-up")
    require(packet.get("schema_version") == SCHEMA and packet.get("spec_sha256") == digest(spec),
            "packet_identity", "Packet must identify the exact specification")
    require(packet.get("model") == spec["model"], "model_mismatch", "Packet model/tokenizer provenance differs")
    require(packet.get("environment", {}).get("kind") == "synthetic_fixture"
            and packet["environment"].get("model_execution") is False,
            "environment_metadata", "Synthetic execution identity must be explicit")
    executed_seed = packet["environment"].get("seed")
    require(integer(executed_seed) and executed_seed == spec["seed"], "execution_seed",
            "Execution seed must be an explicit nonnegative integer equal to the specification seed")
    vocab = packet.get("vocabulary")
    require(isinstance(vocab, list) and bool(vocab) and all(isinstance(x, str) for x in vocab),
            "missing_vocabulary", "Full vocabulary required")
    for case in spec["cases"]:
        for target in case["targets"]:
            token_ids = target["token_ids"]
            require(all(t < len(vocab) for t in token_ids), "target_outside_vocab", target["id"])
            observed = token_match(vocab[token_ids[0]], target["text"], token_ids, token_ids[0])
            expected_match = "exact" if len(token_ids) == 1 else "first_wordpiece_proxy"
            require(observed == expected_match, "target_text_token_mismatch", target["id"])
    require(all(t < len(vocab) for c in spec["cases"] for v in c["variants"].values() for t in v["token_ids"]),
            "input_outside_vocab", "Input token ID is outside the full vocabulary")
    exclusions = spec.get("vocabulary_filter", {}).get("excluded", [])
    require(spec.get("vocabulary_filter", {}).get("id") and all(
        integer(x.get("token_id")) and x["token_id"] < len(vocab) and bool(x.get("reason")) for x in exclusions),
        "filter_metadata", "Explicit excluded IDs and reasons are required")
    excluded = {x["token_id"] for x in exclusions}
    cases = {x["id"]: x for x in spec["cases"]}
    expected = {(c["id"], v, method, layer, position)
                for c in cases.values() for v, variant in c["variants"].items()
                for method in METHODS for layer in validation["common_layers"] for position in variant["positions"]}
    seen = set()
    readouts = []
    for row in packet.get("readouts", []):
        require(integer(row.get("layer")) and integer(row.get("position")),
                "readout_grid", "Explicit integer layer and position required")
        key = (row.get("case_id"), row.get("variant"), row.get("method"), row.get("layer"), row.get("position"))
        require(key in expected and key not in seen, "readout_grid", "Unknown, duplicate or unlabelled readout")
        seen.add(key)
        values = finite_vector(row.get("logits"))
        require(len(values) == len(vocab), "vocabulary_size", "Top-k vectors cannot supply full ranks")
        readouts.append({k: row[k] for k in ("case_id", "variant", "method", "layer", "position")} | {
            "scores": [rank_target(values, t, excluded, spec["top_k"]) for t in cases[key[0]]["targets"]],
            "probability_kind": "lens_readout_softmax"})
    require(seen == expected, "incomplete_readouts", "Every common layer and input position must be present")
    baselines = {}
    baseline_logits = {}
    baseline_rows = []
    for row in packet.get("model_outputs", []):
        key = (row.get("case_id"), row.get("variant"))
        require(key[0] in cases and key[1] in cases[key[0]]["variants"] and key not in baselines,
                "output_identity", "Unknown or duplicate output")
        require(row.get("extraction") == "model.logits[0,-1]", "output_extraction", "Actual model output required")
        values = finite_vector(row.get("logits"))
        require(len(values) == len(vocab), "vocabulary_size", "Output vocabulary mismatch")
        scores = [rank_target(values, t, excluded, spec["top_k"]) for t in cases[key[0]]["targets"]]
        baselines[key] = scores
        baseline_logits[key] = values
        baseline_rows.append({"case_id": key[0], "variant": key[1], "scores": scores,
                              "probability_kind": "original_model_softmax", "extraction": row["extraction"],
                              "unpatched_answer_stratum": "top1" if all(s["raw_rank"] == 1 for s in scores
                                                                         if s["role"] == "answer") else "not_top1"})
    require(set(baselines) == {(c["id"], v) for c in cases.values() for v in c["variants"]},
            "missing_model_outputs", "Last fitted layer cannot substitute for model outputs")
    effects = []
    intervention_ids = set()
    plans = spec.get("intervention_plan", [])
    require(isinstance(plans, list) and bool(plans) and all(isinstance(p, dict) and p.get("id") for p in plans)
            and len({p["id"] for p in plans}) == len(plans), "intervention_plan", "Unique prespecified interventions required")
    planned = {p["id"]: p for p in plans}
    for row in packet.get("interventions", []):
        require(row.get("id") and row["id"] not in intervention_ids, "intervention_identity", "Unique ID required")
        intervention_ids.add(row["id"])
        require(row["id"] in planned and {k: v for k, v in row.items() if k not in {"logits", "edit_l2"}}
                == planned[row["id"]], "intervention_plan", "Intervention differs from the prespecified plan")
        cid, donor, recipient = row.get("case_id"), row.get("donor"), row.get("recipient")
        require(cid in cases and (cid, donor) in baselines and (cid, recipient) in baselines,
                "intervention_identity", "Unknown input variant")
        require(row.get("kind") in {"observed_replacement", "zero_ablation"}
                and row.get("component") in {"block_output", "mlp_neuron_output"},
                "intervention_identity", "Explicit intervention and component required")
        require(integer(row.get("layer")) and row["layer"] in validation["common_layers"],
                "intervention_layer", "Layer outside prespecified comparison")
        allowed = suffix_alignment(cases[cid]["variants"][donor]["token_ids"],
                                   cases[cid]["variants"][recipient]["token_ids"])
        require(bool(row.get("positions")) and all(x in allowed for x in row["positions"]),
                "span_alignment", "Only token-ID-aligned suffix positions are patchable")
        require(type(row.get("edit_l2")) in (float, int) and math.isfinite(row["edit_l2"]) and row["edit_l2"] >= 0,
                "edit_magnitude", "Measured edit magnitude required")
        require(row.get("control") in {"self", "same_register", "random", "unrelated", "full_component", "nominated"},
                "control_identity", "Control class required")
        require(integer(row.get("seed")), "missing_seed", "Intervention seed required")
        channels = row.get("channels")
        width = spec["model"]["intermediate_size" if row["component"] == "mlp_neuron_output" else "hidden_size"]
        require(channels is None or (isinstance(channels, list) and bool(channels)
                and len(set(channels)) == len(channels) and all(integer(c) and c < width for c in channels)),
                "channel_identity", "Explicit unique in-range channels or null for full component required")
        if row["control"] == "random":
            require(channels is not None and channels == seeded_groups(width, len(channels), [row["seed"]],
                    row["layer"])[0]["channels"], "random_control", "Random channels do not match recorded seed")
            comparator = planned.get(row.get("matched_to"))
            require(isinstance(comparator, dict) and comparator.get("control") == "nominated",
                    "random_control_match", "Random controls must name their nominated comparator")
            require(all(row.get(key) == comparator.get(key) for key in
                        ("case_id", "kind", "component", "layer", "positions", "donor", "recipient"))
                    and isinstance(comparator.get("channels"), list)
                    and len(channels) == len(comparator["channels"]),
                    "random_control_match", "Random controls must match comparator scope, layer and size")
        if row["control"] == "nominated":
            require(row.get("nomination_split") == "discovery", "split_leakage", "Nominate from discovery only")
        values = finite_vector(row.get("logits"))
        require(len(values) == len(vocab), "vocabulary_size", "Patched vocabulary mismatch")
        scores = [rank_target(values, t, excluded, spec["top_k"]) for t in cases[cid]["targets"]]
        if row["control"] == "self":
            require(donor == recipient and row["kind"] == "observed_replacement" and row["edit_l2"] == 0
                    and values == baseline_logits[cid, recipient], "self_patch_identity", "Self patch changed output")
        effects.append({k: v for k, v in row.items() if k != "logits"} | {
            "effects": [{"target_id": t["id"], "role": t["role"], **patch_effect(
                baselines[cid, donor][i]["full_vocab_probability"],
                baselines[cid, recipient][i]["full_vocab_probability"], scores[i]["full_vocab_probability"],
                spec["gap_threshold"])} for i, t in enumerate(cases[cid]["targets"])]})
    require(intervention_ids == set(planned), "missing_interventions", "Every prespecified intervention must be returned")
    return {"schema_version": SCHEMA, "execution_status": "synthetic", "publication": "exploratory_only",
            "spec_sha256": digest(spec), "packet_sha256": digest(packet), "provenance": spec,
            "environment": packet["environment"],
            "rank_tie_rule": "descending_logit_then_ascending_token_id",
            "common_layers": validation["common_layers"], "fixed_layers": spec["fixed_layers"],
            "filter_audit": [{**x, "decoded": vocab[x["token_id"]]} for x in exclusions],
            "readouts": readouts, "model_outputs": baseline_rows, "interventions": effects,
            "runtime_seconds": packet.get("runtime_seconds"), "peak_memory_bytes": packet.get("peak_memory_bytes"),
            "limitations": ["synthetic_not_measurement", "no_sequence_scoring", "no_family_uncertainty_for_one_case"]}


def build_report(spec: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    """Join a synthetic packet without permitting malformed shapes to escape."""
    try:
        return _build_report(spec, packet)
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        result = (build_report(spec, json.loads(args.packet.read_text(encoding="utf-8")))
                  if args.packet else validate_spec(spec))
        if args.out:
            require(args.out.name.startswith("exploratory_report.") and args.out.suffix == ".json",
                    "output_namespace", "Use exploratory_report.<id>.json")
            resolved = args.out.resolve()
            require(resolved.parent.name == "exploratory_methods", "output_namespace", "Use exploratory_methods/ directory")
            forbidden = {"trace_out", "data", "pilot", ".github", "ops", ".claude", ".githooks", ".git", "modes"}
            require(not forbidden.intersection(resolved.parts), "output_namespace", "Protected output root")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
                handle.write("\n")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 2 if result.get("status") == "blocked" else 0
    except (Refusal, KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        print(json.dumps({"schema_version": SCHEMA, "status": "refused",
                          "code": exc.code if isinstance(exc, Refusal) else "invalid_input", "detail": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
