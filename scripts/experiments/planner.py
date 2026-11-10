"""Expand a protocol and the capability matrix into a deterministic plan (``patientwords.experiment-plan/1``).

``build_plan`` reads no clock and draws no random number. Tasks are sorted by family, variant, method and
replicate, so the same protocol, matrix and adapter set give the same plan bytes.

A task's identity is ``spec_sha256 = exploratory_methods.digest(spec)``: what is computed. The replicate index
and the attempt number are not part of it. The store keys reuse on ``(spec_sha256, replicate)``, so replicate
1 is never satisfied by replicate 0's result.

Estimates are sizes derived from stated formulas. They are marked ``measured: false``. No throughput, price or
duration is invented: ``runtime_seconds_estimate`` stays null unless a rates file supplies measured rates with
their source and sample size, and null when no task is ready, because the sum is over ready tasks only.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from scripts.experiments import capabilities as caps
from scripts.experiments.adapters import adapter_status, load_adapter
from scripts.experiments.common import (
    CAPABILITY_SCHEMA, DTYPE_BYTES, FIXTURE_BACKEND, PLAN_SCHEMA, PLANNED_STATES, RATES_SCHEMA, Refusal, digest,
    integer, require, require_structure, text,
)
from scripts.experiments.protocol import RowRestriction, validate_protocol

ACTIVATION_BYTES_FORMULA = "activation_bytes = captured_positions * layers * hidden_size * bytes_per_value(dtype)"
FIT_BYTES_FORMULA = "fit_bytes = bytes_per_value(dtype) * (2 * n_samples * hidden_size + 3 * hidden_size ** 2)"
MODEL_IDENTITY_KEYS = ("study_id", "hf_id", "revision", "tokenizer_id", "tokenizer_revision", "hidden_size",
                       "n_layers")


def _bytes_per_value(dtype: str) -> int:
    require(dtype in DTYPE_BYTES, "unknown_dtype", f"dtype must be one of {sorted(DTYPE_BYTES)}; got {dtype!r}")
    return DTYPE_BYTES[dtype]


def estimate_activation_bytes(tokens: int, layers: int, hidden_size: int, dtype: str) -> int:
    """Bytes of one residual vector per captured token position and layer, uncompressed, no container overhead.

    ``tokens * layers * hidden_size * bytes_per_value(dtype)``. An estimate from a formula, not a measurement.
    """
    require(integer(tokens) and integer(layers) and integer(hidden_size, 1), "invalid_estimate_input",
            "tokens and layers must be non-negative integers and hidden_size a positive integer")
    return tokens * layers * hidden_size * _bytes_per_value(dtype)


def estimate_fit_bytes(n_samples: int, hidden_size: int, dtype: str) -> int:
    """Bytes of an ICA or whitening workspace held in memory at once.

    ``bytes_per_value(dtype) * (2 * n_samples * hidden_size + 3 * hidden_size ** 2)``: the sample matrix and
    one whitened copy of it, plus three square matrices (covariance, whitening, unmixing). An estimate from a
    formula. A real fit may hold more copies or fit in chunks; measure before relying on it.
    """
    require(integer(n_samples, 1) and integer(hidden_size, 1), "invalid_estimate_input",
            "n_samples and hidden_size must be positive integers")
    return _bytes_per_value(dtype) * (2 * n_samples * hidden_size + 3 * hidden_size ** 2)


def _method_artifact(method: Mapping[str, Any]) -> str | None:
    """The artifact a method block names: a lens artifact's hash or id, or an ICA basis manifest hash."""
    artifact = method.get("artifact")
    if isinstance(artifact, dict):
        return artifact.get("sha256") or artifact.get("id")
    basis = method.get("basis")
    if isinstance(basis, dict):
        return basis.get("manifest_sha256")
    return None


def _planned_state(method_id: str, backend: str, answer: Mapping[str, Any],
                   adapter: tuple[str, str | None]) -> tuple[str, str | None]:
    """``(planned_state, reason)`` from the capability answer and the adapter's presence.

    ``ready`` needs all of: a fixture backend, a status of at least ``runtime_verified_offline_fixture``, and an
    importable adapter. Everything else stays in the plan as ``unsupported`` or ``unavailable`` with the reason.
    """
    status = answer["status"]
    if status == "unsupported":
        return "unsupported", answer["status_note"]
    if status == "artifact_available_identity_unknown":
        return "unavailable", f"artifact identity unknown: {answer['status_note']}"
    state, reason = adapter
    if state != "present":
        return "unavailable", reason
    if backend != FIXTURE_BACKEND or caps.status_rank(status) < caps.status_rank(caps.FIXTURE_CEILING):
        return "unavailable", (f"capability status {status} on backend {backend}: this package runs offline "
                               "fixtures only; a real-model run needs its own approved execution route")
    return "ready", None


def load_rates(doc: Any) -> list[dict[str, Any]]:
    """Validate a rates document. Every rate must say where it was measured and on how many samples."""
    require(isinstance(doc, dict) and doc.get("schema_version") == RATES_SCHEMA and isinstance(doc.get("rates"), list),
            "rates_source", f"Expected a {RATES_SCHEMA} document with a 'rates' list")
    seen: set[tuple[str, str]] = set()
    for rate in doc["rates"]:
        require(isinstance(rate, dict) and text(rate.get("method")) and text(rate.get("backend"))
                and type(rate.get("seconds_per_task")) in (int, float) and math.isfinite(rate["seconds_per_task"])
                and rate["seconds_per_task"] >= 0
                and text(rate.get("source")) and integer(rate.get("n_samples"), 1), "rates_source",
                "Each rate needs method, backend, a finite non-negative seconds_per_task, source and n_samples "
                "(at least 1)")
        key = (rate["method"], rate["backend"])
        require(key not in seen, "duplicate_rate",
                f"the rates document has two rows for method {key[0]} on backend {key[1]}; one measured rate "
                "per method and backend is needed, and neither row is preferred")
        seen.add(key)
    return doc["rates"]


def _build(protocol: dict[str, Any], matrix: Mapping[str, Any], replicates: int | None,
           rates: Any, registry: Mapping[str, str] | None,
           row_restriction: RowRestriction | None) -> dict[str, Any]:
    summary = validate_protocol(protocol, row_restriction=row_restriction)
    caps.validate_matrix(dict(matrix))
    count = protocol["replicates"] if replicates is None else replicates
    require(integer(count, 1), "replicates", "replicates must be an integer of at least 1")
    model = protocol["model"]
    identity = {key: model[key] for key in MODEL_IDENTITY_KEYS}
    settings = {**protocol["input_settings"], "dtype": model["dtype"], "backend": model["backend"]}
    methods = sorted(protocol["methods"], key=lambda m: m["id"])

    adapters: dict[str, tuple[str, str | None]] = {}
    declared: list[dict[str, Any]] = []
    for method in methods:
        adapters[method["id"]] = adapter_status(method["id"], registry)
        if adapters[method["id"]][0] == "present":
            adapter, _ = load_adapter(method["id"], registry)
            module = type(adapter).__module__
            declared.extend(caps.check_adapter_rows(
                [row for row in adapter.capabilities() if row.get("method") == method["id"]], module))
    rows = caps.merge_rows(matrix, declared)

    excluded = {row["family_id"]: row["reason"] for row in protocol["exclusions"]}
    families = sorted(protocol["case_families"], key=lambda f: f["family_id"])
    tasks: list[dict[str, Any]] = []
    for family in families:
        if family["family_id"] in excluded:
            continue
        for variant in sorted(family["variants"]):
            entry = family["variants"][variant]
            for method in methods:
                spec = {
                    "protocol_sha256": summary["protocol_sha256"], "family_id": family["family_id"],
                    "variant": variant, "model": identity, "method": method,
                    "input": {"prompt_sha256": entry["prompt_sha256"], "token_sha256": entry["token_sha256"]},
                    "settings": settings,
                }
                spec_sha256 = digest(spec)
                answer = caps.lookup(identity, method["id"], model["backend"], _method_artifact(method),
                                     dtype=model["dtype"], rows=rows)
                state, reason = _planned_state(method["id"], model["backend"], answer, adapters[method["id"]])
                tokens = len(entry["token_ids"])
                layers = len(method.get("layers", []))
                captured = 0 if not layers else (1 if method.get("positions") == "last" else tokens)
                estimate = {
                    "tokens": tokens, "captured_positions": captured, "layers": layers,
                    "activation_bytes": estimate_activation_bytes(captured, layers, model["hidden_size"],
                                                                  model["dtype"]),
                    "assumptions": [ACTIVATION_BYTES_FORMULA,
                                    "positions 'last' captures one position; any other value captures every "
                                    "input position",
                                    "a method block without layers captures no activations"],
                    "measured": False,
                }
                for replicate in range(count):
                    tasks.append({
                        "task_id": spec_sha256[:16], "spec_sha256": spec_sha256, "spec": spec,
                        "replicate": replicate,
                        "capability": {"status": answer["status"], "evidence": answer["evidence_text"],
                                       "status_note": answer["status_note"], "matched": answer["matched"],
                                       "revision_match": answer["revision_match"],
                                       "declared_by": answer["declared_by"]},
                        "planned_state": state, "reason": reason, "estimate": estimate,
                    })
    require(len({(t["task_id"], t["replicate"]) for t in tasks}) == len(tasks), "task_id_collision",
            "Two tasks share the first 16 hex digits of spec_sha256 and a replicate index")

    by_state = {state: sum(1 for t in tasks if t["planned_state"] == state) for state in PLANNED_STATES}
    by_method = {
        method["id"]: {**{state: sum(1 for t in tasks if t["spec"]["method"]["id"] == method["id"]
                                    and t["planned_state"] == state) for state in PLANNED_STATES},
                       "total": sum(1 for t in tasks if t["spec"]["method"]["id"] == method["id"])}
        for method in methods}
    ready = [t for t in tasks if t["planned_state"] == "ready"]
    runtime, rates_used, notes = None, [], [
        ACTIVATION_BYTES_FORMULA + "; float16 and bfloat16 are 2 bytes, float32 4, float64 8.",
        "Sizes are for uncompressed arrays with no container overhead. They are estimates, not measurements.",
        "Estimates cover every planned task, including unsupported and unavailable ones; ready-only sums are "
        "given separately.",
        FIT_BYTES_FORMULA + " is exposed as estimate_fit_bytes for an ICA or whitening workspace; no fit is "
        "planned here, so no fit size is summed.",
    ]
    if rates is None:
        notes.append("runtime_seconds_estimate is null: no measured rate was supplied. Fixture timings would say "
                     "nothing about model runs, so none is used.")
    else:
        table = {(r["method"], r["backend"]): r for r in load_rates(rates)}
        missing = sorted({t["spec"]["method"]["id"] for t in ready} - {m for m, b in table if b == model["backend"]})
        if not ready:
            notes.append("runtime_seconds_estimate is null: no task is ready, so no runtime is estimated. The "
                         "estimate sums over ready tasks only and says nothing about the tasks planned as "
                         "unsupported or unavailable.")
        elif missing:
            notes.append(f"runtime_seconds_estimate is null: the rates file has no rate for {missing} on backend "
                         f"{model['backend']}.")
        else:
            runtime = sum(table[(t["spec"]["method"]["id"], model["backend"])]["seconds_per_task"] for t in ready)
            rates_used = [table[key] for key in sorted(table) if key[1] == model["backend"]
                          and key[0] in {t["spec"]["method"]["id"] for t in ready}]
            notes.append("runtime_seconds_estimate sums seconds_per_task over ready tasks from the supplied rates; "
                         "each rate's source and sample size are in rates_used.")

    return {
        "schema_version": PLAN_SCHEMA,
        "protocol": {"id": protocol["protocol_id"], "version": protocol["version"],
                     "sha256": summary["protocol_sha256"]},
        "digest_convention": "scripts.exploratory_methods.digest",
        "synthetic": protocol["synthetic"], "seed": protocol["seed"], "replicates": count,
        "evidence": protocol["evidence"],
        "protocol_summary": {
            "model": {**identity, "dtype": model["dtype"], "backend": model["backend"]},
            "input_settings": protocol["input_settings"],
            # No prompt text and no target text is copied into a plan: ids, hashes and token ids only.
            "families": [{"family_id": f["family_id"], "split": f["split"], "review_status": f["review_status"],
                          "legacy_join": f["legacy_join"], "variants": sorted(f["variants"]),
                          "targets": [{"id": t["id"], "role": t.get("role", "answer"), "token_ids": t["token_ids"]}
                                      for t in f["targets"]]} for f in families],
            "methods": [m["id"] for m in methods],
            "comparisons": protocol["comparisons"],
            "primary_endpoint": protocol["primary_endpoint"],
        },
        "excluded": [{"family_id": f, "reason": excluded[f]} for f in sorted(excluded)],
        "capability_matrix": {"schema_version": CAPABILITY_SCHEMA, "sha256": digest(dict(matrix)),
                              "as_of": matrix.get("as_of")},
        "adapters": {m: ("present" if s == "present" else f"unavailable: {r}" if s == "absent" else f"none: {r}")
                     for m, (s, r) in sorted(adapters.items())},
        "tasks": tasks,
        "totals": {
            "tasks": len(tasks), "by_planned_state": by_state, "by_method": by_method,
            "estimates": {
                "tokens": sum(t["estimate"]["tokens"] for t in tasks),
                "activation_bytes": sum(t["estimate"]["activation_bytes"] for t in tasks),
                "ready_tokens": sum(t["estimate"]["tokens"] for t in ready),
                "ready_activation_bytes": sum(t["estimate"]["activation_bytes"] for t in ready),
                "measured": False,
            },
            "runtime_seconds_estimate": runtime,
        },
        "rates_used": rates_used,
        "estimate_notes": notes,
    }


def build_plan(protocol: dict[str, Any], capabilities: Mapping[str, Any], *, replicates: int | None = None,
               rates: Any = None, registry: Mapping[str, str] | None = None,
               row_restriction: RowRestriction | None = None) -> dict[str, Any]:
    """The plan for ``protocol`` under the capability matrix ``capabilities``.

    ``replicates`` overrides the protocol's count. ``rates`` is a parsed rates document or None. ``registry``
    replaces the adapter module map (tests use it to plan against an absent adapter). ``row_restriction`` is
    passed to ``validate_protocol``. The result validates against ``schemas/experiments/plan.v1.schema.json``.
    """
    try:
        plan = _build(protocol, capabilities, replicates, rates, registry, row_restriction)
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", f"{type(exc).__name__}: {exc}") from exc
    require_structure(plan, "plan")
    return plan


def validate_plan(plan: Any) -> dict[str, Any]:
    """Check a plan read from disk: schema, state vocabulary and that every task id is its spec's digest."""
    require(isinstance(plan, dict) and plan.get("schema_version") == PLAN_SCHEMA, "schema_version",
            f"Expected {PLAN_SCHEMA}")
    require_structure(plan, "plan")
    for task in plan["tasks"]:
        require(task["planned_state"] in PLANNED_STATES, "plan_state", f"task {task['task_id']}")
        require(task["spec_sha256"] == digest(task["spec"]) and task["task_id"] == task["spec_sha256"][:16],
                "plan_identity", f"task {task['task_id']}: spec_sha256 is not the digest of its spec")
        require(task["spec"]["protocol_sha256"] == plan["protocol"]["sha256"], "plan_identity",
                f"task {task['task_id']} belongs to another protocol")
        require((task["planned_state"] == "ready") == (task["reason"] is None), "plan_state",
                f"task {task['task_id']}: a reason is required exactly when the task is not ready")
    return plan
