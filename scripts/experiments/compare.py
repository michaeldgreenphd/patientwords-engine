"""Derive the small per-family comparison from collected envelopes and their typed payloads.

For each family, comparison (variant a against variant b) and replicate, each method contributes its own block:

* ``behavior``: the difference in full-vocabulary probability of each target, a minus b, signed and raw, from
  ``behavior_next_token/1`` payloads only.
* ``readout``: per readout method and layer, the target's raw rank and filtered rank for a and for b, both kept,
  from ``lens_readout_report/1`` payloads. A top-k miss reads ``not_observed_in_window``.
* ``ica``: signed score differences per component under one basis hash, and energy shares labelled
  "squared-coordinate share, not a probability", from ``ica_scores/1`` payloads.

Blocks have different units and are never added, averaged or otherwise combined. A method whose two tasks did
not both complete is listed with each side's state and reason; its block says ``not_computed``. A missing value
is never written as zero.

No statistic is computed here: there is one value per family, variant and replicate, so there is no interval,
no test and no random draw. Replicates are reported side by side and are not pooled.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from scripts.experiments.common import COMPARISON_SCHEMA, HEX64, digest, require
from scripts.experiments.store import RunStore

SIGN_CONVENTION = "difference_a_minus_b is the value for variant a minus the value for variant b"
ENERGY_LABEL = "squared-coordinate share, not a probability"
BLOCK_RULE = ("Each block comes from one payload kind and keeps its own units. No block is combined with another "
              "into one number.")
READOUT_KIND, BEHAVIOR_KIND, ICA_KIND = "lens_readout_report/1", "behavior_next_token/1", "ica_scores/1"


def behavior_block(payload_a: Mapping[str, Any], payload_b: Mapping[str, Any]) -> dict[str, Any]:
    """Signed difference in full-vocabulary target probability, a minus b, for every target."""
    require(payload_a.get("kind") == BEHAVIOR_KIND and payload_b.get("kind") == BEHAVIOR_KIND, "payload_kind",
            f"the behaviour block reads {BEHAVIOR_KIND} payloads only")
    require(payload_a["model"] == payload_b["model"] and payload_a["vocabulary_size"] == payload_b["vocabulary_size"]
            and payload_a["probability_kind"] == payload_b["probability_kind"], "payload_mismatch",
            "The two behaviour payloads differ in model, vocabulary size or probability kind")
    b_rows = {row["target_id"]: row for row in payload_b["targets"]}
    targets = []
    for row in payload_a["targets"]:
        other = b_rows.get(row["target_id"])
        require(other is not None and other["token_id"] == row["token_id"], "payload_mismatch",
                f"target {row['target_id']} is absent from one payload or names another token")
        targets.append({
            "target_id": row["target_id"], "role": row["role"], "token_id": row["token_id"],
            "a": row["full_vocab_probability"], "b": other["full_vocab_probability"],
            "difference_a_minus_b": row["full_vocab_probability"] - other["full_vocab_probability"],
            "raw_rank_a": row["raw_rank"], "raw_rank_b": other["raw_rank"],
        })
    return {"status": "computed", "payload_kind": BEHAVIOR_KIND, "metric": "full_vocab_probability",
            "probability_kind": payload_a["probability_kind"], "sign_convention": SIGN_CONVENTION,
            "targets": targets}


def _last_scores(payload: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    """``{layer: {target_id: score row}}`` at the payload's last input position."""
    last = payload["last_position"]
    return {row["layer"]: {score["target_id"]: score for score in row["scores"]}
            for row in payload["readouts"] if row["position"] == last}


def readout_block(payload_a: Mapping[str, Any], payload_b: Mapping[str, Any]) -> dict[str, Any]:
    """Raw and filtered target ranks per layer for a and b, at each variant's last input position.

    The two ranks are separate fields. No rank difference and no summary across layers is computed.
    """
    require(payload_a.get("kind") == READOUT_KIND and payload_b.get("kind") == READOUT_KIND, "payload_kind",
            f"the readout block reads {READOUT_KIND} payloads only")
    require(payload_a["method"] == payload_b["method"], "payload_mismatch", "The payloads are from two methods")
    require(payload_a["filter"] == payload_b["filter"] and payload_a["top_k"] == payload_b["top_k"]
            and payload_a["rank_tie_rule"] == payload_b["rank_tie_rule"], "filter_mismatch",
            "The two readout payloads use different vocabulary filters, top-k windows or tie rules")
    scores_a, scores_b = _last_scores(payload_a), _last_scores(payload_b)
    keys = ("raw_rank", "filtered_rank", "excluded_candidate", "top_k")
    layers = []
    for layer in sorted(set(scores_a) & set(scores_b)):
        targets = [{"target_id": target, "role": scores_a[layer][target]["role"],
                    "a": {key: scores_a[layer][target][key] for key in keys},
                    "b": {key: scores_b[layer][target][key] for key in keys}}
                   for target in scores_a[layer] if target in scores_b[layer]]
        layers.append({"layer": layer, "targets": targets})
    return {"status": "computed", "payload_kind": READOUT_KIND, "method": payload_a["method"],
            "position": "last_input_position_of_each_variant",
            "position_a": payload_a["last_position"], "position_b": payload_b["last_position"],
            "filter": payload_a["filter"], "top_k_windows": payload_a["top_k"],
            "rank_tie_rule": payload_a["rank_tie_rule"],
            "rank_fields": "raw_rank and filtered_rank are separate; filtered_rank is null when the target token "
                           "is itself excluded",
            "layers_only_in_a": sorted(set(scores_a) - set(scores_b)),
            "layers_only_in_b": sorted(set(scores_b) - set(scores_a)),
            "layers": layers}


def _ica_rows(payload: Mapping[str, Any]) -> dict[int, tuple[int, dict[int, float]]]:
    """``{layer: (position, {component: score})}`` at the highest captured position of each layer."""
    by_layer: dict[int, dict[int, dict[int, float]]] = {}
    for row in payload["scores"]:
        by_layer.setdefault(row["layer"], {}).setdefault(row["position"], {})[row["component"]] = row["score"]
    return {layer: (max(positions), positions[max(positions)]) for layer, positions in by_layer.items()}


def _energy_shares(scores: Mapping[int, float], complete: bool) -> tuple[dict[int, float | None], str]:
    if not complete:
        return {k: None for k in scores}, "not_computed_component_list_incomplete"
    total = sum(v * v for v in scores.values())
    if not math.isfinite(total) or total <= 0.0:
        return {k: None for k in scores}, "not_computed_zero_or_non_finite_energy"
    return {k: (v * v) / total for k, v in scores.items()}, "computed"


def ica_block(payload_a: Mapping[str, Any], payload_b: Mapping[str, Any]) -> dict[str, Any]:
    """Signed score differences per component under one basis, with labelled energy shares.

    Fields read from an ``ica_scores/1`` payload: ``basis.manifest_sha256`` (64 hex), ``components_complete``
    (true when ``scores`` lists every component of the basis at each captured layer and position) and
    ``scores``: rows of ``{layer, position, component, score}``. Refuses ``basis_mismatch`` when the two payloads
    name different basis hashes: scores under two bases share no coordinate.
    A component present on one side only has a null difference; it is not treated as zero.
    """
    require(payload_a.get("kind") == ICA_KIND and payload_b.get("kind") == ICA_KIND, "payload_kind",
            f"the ICA block reads {ICA_KIND} payloads only")
    basis_a = payload_a.get("basis", {}).get("manifest_sha256")
    basis_b = payload_b.get("basis", {}).get("manifest_sha256")
    require(bool(HEX64.fullmatch(str(basis_a))) and bool(HEX64.fullmatch(str(basis_b))), "basis_identity",
            "Each ICA payload must name its basis by manifest SHA-256")
    require(basis_a == basis_b, "basis_mismatch",
            f"The two variants were scored under different bases ({basis_a[:12]} and {basis_b[:12]})")
    rows_a, rows_b = _ica_rows(payload_a), _ica_rows(payload_b)
    layers = []
    for layer in sorted(set(rows_a) & set(rows_b)):
        (position_a, scores_a), (position_b, scores_b) = rows_a[layer], rows_b[layer]
        shares_a, status_a = _energy_shares(scores_a, payload_a.get("components_complete") is True)
        shares_b, status_b = _energy_shares(scores_b, payload_b.get("components_complete") is True)
        components = []
        for component in sorted(set(scores_a) | set(scores_b)):
            a, b = scores_a.get(component), scores_b.get(component)
            components.append({
                "component": component, "score_a": a, "score_b": b,
                "difference_a_minus_b": a - b if a is not None and b is not None else None,
                "energy_share_a": shares_a.get(component), "energy_share_b": shares_b.get(component)})
        layers.append({"layer": layer, "position_a": position_a, "position_b": position_b,
                       "energy_share_status_a": status_a, "energy_share_status_b": status_b,
                       "components": components})
    return {"status": "computed", "payload_kind": ICA_KIND, "basis_manifest_sha256": basis_a,
            "sign_convention": SIGN_CONVENTION, "energy_share_label": ENERGY_LABEL,
            "position": "highest_captured_position_of_each_layer",
            "layers_only_in_a": sorted(set(rows_a) - set(rows_b)),
            "layers_only_in_b": sorted(set(rows_b) - set(rows_a)),
            "layers": layers}


BLOCK_BUILDERS = {BEHAVIOR_KIND: behavior_block, READOUT_KIND: readout_block, ICA_KIND: ica_block}


def _not_computed(sides: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {"status": "not_computed",
            "states": {side: sides[side]["execution"] for side in ("a", "b")},
            "reasons": {side: sides[side]["reason"] for side in ("a", "b")}}


def compare_run(run_dir: Any, *, allow_roots: Iterable[Any] = ()) -> dict[str, Any]:
    """The comparison document for a collected run directory. Reads only; the caller writes it.

    The same run directory gives the same document: no clock value and no random draw enter it.
    """
    store = RunStore(run_dir, allow_roots=allow_roots)
    collected, plan = store.read_collected(), store.read_plan()
    assembly, summary = collected["assembly"], plan["protocol_summary"]
    rows = {(r["family_id"], r["variant"], r["method"], r["replicate"]): r for r in assembly["tasks"]}
    planned = {(t["spec"]["family_id"], t["spec"]["variant"], t["spec"]["method"]["id"], t["replicate"]): t
               for t in plan["tasks"]}
    excluded = {row["family_id"] for row in plan["excluded"]}

    def side(family_id: str, variant: str, method: str, replicate: int) -> dict[str, Any]:
        key = (family_id, variant, method, replicate)
        if key in rows:
            row = rows[key]
            return {"execution": row["execution"], "reason": row["reason"], "payload": row["payload"]}
        if key in planned:
            return {"execution": "not_run", "reason": "planned task has no envelope in the collected run",
                    "payload": None}
        return {"execution": "not_run", "reason": "no task was planned for this family, variant and method",
                "payload": None}

    families = []
    for family in summary["families"]:
        if family["family_id"] in excluded:
            continue
        entries = []
        for comparison in summary["comparisons"]:
            for replicate in range(plan["replicates"]):
                entry: dict[str, Any] = {"comparison_id": comparison["id"], "a": comparison["a"],
                                         "b": comparison["b"], "replicate": replicate, "readout": {},
                                         "references": {}, "methods_not_run": []}
                for method in summary["methods"]:
                    sides = {name: side(family["family_id"], comparison[name], method, replicate)
                             for name in ("a", "b")}
                    done = all(sides[name]["execution"] == "completed" for name in ("a", "b"))
                    if not done:
                        entry["methods_not_run"].append({"method": method, **{
                            k: v for k, v in _not_computed(sides).items() if k != "status"}})
                        block: dict[str, Any] = _not_computed(sides)
                        kind = None
                    else:
                        payloads = {name: store.read_payload(sides[name]["payload"]) for name in ("a", "b")}
                        kind = sides["a"]["payload"]["kind"]
                        require(sides["b"]["payload"]["kind"] == kind, "payload_mismatch",
                                f"{method}: the two variants filed different payload kinds")
                        builder = BLOCK_BUILDERS.get(kind)
                        block = (builder(payloads["a"], payloads["b"]) if builder else
                                 {"status": "reference_only", "payload_kind": kind,
                                  "a": sides["a"]["payload"], "b": sides["b"]["payload"]})
                    if method == "behavior_next_token":
                        entry["behavior"] = block
                    elif method == "ica_lens":
                        entry["ica"] = block
                    elif kind == READOUT_KIND or method in ("logit_lens", "j_lens", "jpp"):
                        entry["readout"][method] = block
                    else:
                        entry["references"][method] = block
                entries.append(entry)
        families.append({"family_id": family["family_id"], "split": family["split"],
                         "review_status": family["review_status"], "comparisons": entries})

    not_run = []
    for method in summary["methods"]:
        states: dict[str, int] = {}
        reasons: set[str] = set()
        for key, task in planned.items():
            if key[2] != method:
                continue
            row = rows.get(key)
            state = row["execution"] if row else "not_run"
            if state == "completed":
                continue
            states[state] = states.get(state, 0) + 1
            reasons.add(row["reason"] if row else "planned task has no envelope in the collected run")
        if states:
            not_run.append({"method": method, "states": dict(sorted(states.items())), "reasons": sorted(reasons)})

    return {
        "schema_version": COMPARISON_SCHEMA,
        "protocol": plan["protocol"], "synthetic": plan["synthetic"], "seed": plan["seed"],
        "assembly_sha256": collected["assembly_sha256"], "plan_sha256": digest(plan),
        "digest_convention": "scripts.exploratory_methods.digest",
        "sign_convention": SIGN_CONVENTION, "block_rule": BLOCK_RULE,
        "statistics": {"computed": False,
                       "note": "One value per family, variant and replicate. No interval, test or resampling is "
                               "computed, so no random seed is drawn; the protocol seed is recorded above. "
                               "Replicates are listed side by side and are not pooled."},
        "primary_endpoint": summary["primary_endpoint"],
        "families": families,
        "methods_not_run": not_run,
    }
