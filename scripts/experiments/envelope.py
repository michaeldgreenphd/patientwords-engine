"""The run envelope (``patientwords.experiment-envelope/1``): one small outer record per task attempt.

The envelope says what was asked, on what input, with which model and method identity, how the attempt ended and
where the typed payload is. It holds no result number. A lens readout, an ICA score table, a next-token output
and a reference to a transcript or graph are different payload kinds with their own shapes; the envelope only
points at one by kind, SHA-256 and path.

Missing provenance is explicit. A provenance field may be null only when its JSON pointer is listed in
``not_recorded``. A field that does not apply to a method carries the string ``"not_applicable"``, which is a
recorded statement and is not null. No historical value is filled in.
"""
from __future__ import annotations

import math
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from scripts.experiments.common import (
    ENVELOPE_SCHEMA, EXECUTION_STATES, FITTED_METHODS, HEX64, LAYERED_METHODS, METHOD_IDS, METHOD_PAYLOAD_KINDS,
    METHOD_REPRESENTATION, NOT_APPLICABLE, PAYLOAD_KINDS, REPRESENTATION_TYPES, UNCERTAIN, VARIANTS, VISIBILITIES,
    Refusal, integer, require, require_structure, sha256_file, text,
)

# Blocks whose null leaves must be listed in not_recorded.
PROVENANCE_BLOCKS = ("protocol", "source", "input", "model", "environment", "method")
NUMERIC_RESOURCES = ("runtime_seconds", "peak_memory_bytes", "storage_bytes", "cost_usd")
EVIDENCE_KEYS = ("evidence_class", "clinical_review", "visibility", "restriction_reasons", "analysis_memberships",
                 "synthetic")
SYNTHETIC_CLASS = "synthetic_fixture"
SYNTHETIC_VISIBILITY = "not_published"
# States in which nothing was executed for the task: such an envelope accepts no unit and measures no resource.
NOT_EXECUTED_STATES = ("not_run", "unsupported", "unavailable")


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def null_pointers(value: Any, prefix: str = "") -> list[str]:
    """JSON pointers (RFC 6901) of every null leaf under ``value``."""
    if value is None:
        return [prefix]
    if isinstance(value, dict):
        return [p for key in sorted(value) for p in null_pointers(value[key], f"{prefix}/{_escape(key)}")]
    if isinstance(value, list):
        return [p for index, item in enumerate(value) for p in null_pointers(item, f"{prefix}/{index}")]
    return []


def provenance_nulls(envelope: Mapping[str, Any]) -> list[str]:
    """Pointers of every null leaf in the provenance blocks of an envelope."""
    return [p for block in PROVENANCE_BLOCKS for p in null_pointers(envelope.get(block), f"/{block}")]


def method_block(method: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The envelope's ``method`` block for a protocol method block.

    Fields that do not apply to the method are ``"not_applicable"``. Fields that apply and are unknown stay null,
    for example the fit revisions of a lens artifact whose fit identity is not recorded; the caller lists their
    pointers in ``not_recorded``. ``payload`` may supply ``output_head`` when the method block does not.
    """
    name = method["id"]
    layered = name in LAYERED_METHODS or "layers" in method
    artifact, basis = method.get("artifact"), method.get("basis")
    if isinstance(basis, dict):
        fitted = {"sha256": basis.get("manifest_sha256"),
                  "fit_provenance": {k: v for k, v in sorted(basis.items()) if k != "manifest_sha256"}}
    elif isinstance(artifact, dict):
        fitted = {"sha256": artifact.get("sha256"),
                  "fit_provenance": {k: v for k, v in sorted(artifact.items()) if k != "sha256"}}
    elif name in FITTED_METHODS:
        # The method reads through a fitted artifact and the protocol names none: unknown, not inapplicable.
        fitted = {"sha256": None, "fit_provenance": None}
    else:
        fitted = {"sha256": NOT_APPLICABLE, "fit_provenance": NOT_APPLICABLE}
    output_head = method.get("output_head") or (payload or {}).get("output_head")
    if output_head is None and name == "behavior_next_token":
        output_head = "model_lm_head_next_token"
    return {
        "id": name,
        "representation_type": METHOD_REPRESENTATION[name],
        "capture_site": method.get("capture_site") if layered else NOT_APPLICABLE,
        "layer_index_base": method.get("layer_index_base", 0),
        "layers": list(method.get("layers", [])),
        "positions": method.get("positions") or ("last" if name == "behavior_next_token"
                                                 else "all" if layered else NOT_APPLICABLE),
        "preprocessing": method.get("preprocessing") or (basis or {}).get("preprocessing") or NOT_APPLICABLE,
        "fitted_artifact": fitted,
        "output_head": output_head,
    }


def declared_memberships() -> frozenset[str]:
    """Membership names the committed results policy declares (``data/results_policy/policy.v1.json``), read
    through ``scripts/results_policy.py``. The committed file is named explicitly, so ``$PW_RESULTS_POLICY``
    does not change what an experiment document may state. A policy that cannot be read raises
    ``PolicyError``: a configuration error, not a refusal."""
    from scripts import results_policy

    policy = results_policy.load_policy(results_policy.ENGINE / results_policy.POLICY_PATH)
    return frozenset(policy.doc["memberships"])


def check_evidence_labels(evidence: Mapping[str, Any], synthetic: bool) -> None:
    """The open-results vocabulary rules for an evidence block (``docs/open_results_policy.md``).

    Visibility is one of ``VISIBILITIES``. ``restricted`` needs at least one named reason and ``public`` needs
    none. Every analysis membership must be a name the committed policy declares. A synthetic document is
    ``not_published`` and joins no membership. Absent keys read as a synthetic document's defaults.

    Naming a declared membership is checked as a label only: whether a membership rule would admit the result
    is decided by ``scripts/results_policy.py`` on a landed part, never here.
    """
    visibility = evidence.get("visibility", SYNTHETIC_VISIBILITY if synthetic else None)
    reasons = evidence.get("restriction_reasons", [])
    memberships = evidence.get("analysis_memberships", [])
    require(visibility in VISIBILITIES, "evidence_fields",
            f"evidence.visibility must be one of {list(VISIBILITIES)}; got {visibility!r}"
            + ("" if synthetic else " (a non-synthetic protocol must state it)"))
    require(isinstance(reasons, list) and all(text(r) for r in reasons) and isinstance(memberships, list)
            and all(text(m) for m in memberships), "evidence_fields",
            "evidence.restriction_reasons and evidence.analysis_memberships must be lists of non-empty strings")
    require(not synthetic or visibility == SYNTHETIC_VISIBILITY, "synthetic_label",
            "A synthetic document must have visibility 'not_published'")
    require(not synthetic or not memberships, "synthetic_label",
            "A synthetic document joins no analysis membership")
    require(visibility != "restricted" or bool(reasons), "evidence_fields",
            "visibility 'restricted' needs at least one named reason in evidence.restriction_reasons")
    require(visibility != "public" or not reasons, "evidence_fields",
            f"visibility 'public' cannot carry restriction reasons {reasons}")
    if memberships:
        unknown = sorted(set(memberships) - declared_memberships())
        require(not unknown, "evidence_fields",
                f"evidence.analysis_memberships names {unknown}, which the committed results policy does not "
                "declare")


def evidence_block(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Open-results policy fields for an envelope. A synthetic protocol is never published and joins no
    analysis; a non-synthetic protocol must state its own visibility."""
    evidence, synthetic = protocol["evidence"], protocol["synthetic"]
    require(synthetic or text(evidence.get("visibility")), "evidence_fields",
            "A non-synthetic protocol must state evidence.visibility")
    return {
        "evidence_class": evidence["evidence_class"],
        "clinical_review": evidence["clinical_review"],
        "visibility": evidence.get("visibility", SYNTHETIC_VISIBILITY),
        "restriction_reasons": list(evidence.get("restriction_reasons", [])),
        "analysis_memberships": list(evidence.get("analysis_memberships", [])),
        "synthetic": synthetic,
    }


def build_envelope(*, run_id: str, task: Mapping[str, Any], protocol: Mapping[str, Any], attempt: int,
                   attempt_history: list[dict[str, Any]], execution: str, reason: str | None,
                   payload: Mapping[str, Any] | None, counts: Mapping[str, Any], resources: Mapping[str, Any],
                   environment: Mapping[str, Any], provider: str, route: str, alignment: str,
                   not_recorded: Iterable[str], output_head: str | None = None,
                   payload_root: Path | None = None) -> dict[str, Any]:
    """Assemble and validate one envelope for ``task``.

    ``not_recorded`` is the explicit list of provenance pointers the caller knows to be null. The builder does
    not compute it: an unlisted null refuses with ``silent_missing_provenance``.
    """
    spec = task["spec"]
    family = next(f for f in protocol["case_families"] if f["family_id"] == spec["family_id"])
    variant = family["variants"][spec["variant"]]
    model, settings = spec["model"], spec["settings"]
    method = method_block(spec["method"], {"output_head": output_head} if output_head else None)
    envelope = {
        "schema_version": ENVELOPE_SCHEMA,
        "run_id": run_id,
        "task_id": task["task_id"],
        "spec_sha256": task["spec_sha256"],
        "replicate": task["replicate"],
        "attempt": attempt,
        "attempt_history": attempt_history,
        "protocol": {"id": protocol["protocol_id"], "version": protocol["version"],
                     "sha256": spec["protocol_sha256"]},
        "source": {
            "experiment_id": protocol["protocol_id"], "family_id": spec["family_id"], "variant": spec["variant"],
            "register": variant.get("register", spec["variant"]),
            # Single-prompt tasks have no conversation role, turn or branch.
            "role": NOT_APPLICABLE, "turn": NOT_APPLICABLE, "branch": NOT_APPLICABLE,
            "legacy_join": family["legacy_join"],
        },
        "evidence": evidence_block(protocol),
        "input": {
            "prompt_sha256": spec["input"]["prompt_sha256"], "token_sha256": spec["input"]["token_sha256"],
            "n_tokens": len(variant["token_ids"]),
            "tokenizer": {"id": model["tokenizer_id"], "revision": model["tokenizer_revision"]},
            "chat_template": settings["chat_template"] if settings["chat_template"] is not None
            else "not_applied_raw_prompt",
            "special_tokens": {"add_special_tokens": settings["add_special_tokens"]},
            "truncation": settings["truncation"],
            "alignment": alignment,
        },
        "model": {
            "study_id": model["study_id"], "hf_id": model["hf_id"], "revision": model["revision"],
            "hidden_size": model["hidden_size"], "n_layers": model["n_layers"],
            "provider": provider, "route": route, "hosted_timestamp_utc": NOT_APPLICABLE,
        },
        "environment": dict(environment),
        "method": method,
        "counts": dict(counts),
        "resources": dict(resources),
        "status": {"execution": execution, "reason": reason},
        "payload": dict(payload) if payload is not None else None,
        "not_recorded": sorted(set(not_recorded)),
    }
    validate_envelope(envelope, payload_root=payload_root)
    return envelope


def _resolves_to_null(doc: Any, pointer: str) -> bool:
    if not pointer.startswith("/"):
        return False
    node = doc
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and key in node:
            node = node[key]
        elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
            node = node[int(key)]
        else:
            return False
    return node is None


def _validate(doc: Any, payload_root: Path | None) -> dict[str, Any]:
    require(isinstance(doc, dict), "invalid_input", "An envelope must be a JSON object")
    require(doc.get("schema_version") == ENVELOPE_SCHEMA, "schema_version", f"Expected {ENVELOPE_SCHEMA}")
    require_structure(doc, "envelope")

    require(bool(HEX64.fullmatch(doc["spec_sha256"])) and doc["task_id"] == doc["spec_sha256"][:16]
            and bool(HEX64.fullmatch(doc["protocol"]["sha256"])), "plan_identity",
            "task_id must be the first 16 hex digits of spec_sha256; protocol.sha256 must be 64 hex")
    require(integer(doc["replicate"]) and text(doc["run_id"]), "invalid_input", "replicate and run_id")

    execution, reason = doc["status"]["execution"], doc["status"]["reason"]
    require(execution in EXECUTION_STATES, "execution_state",
            f"status.execution must be one of {list(EXECUTION_STATES)}; got {execution!r}")
    require(execution == "completed" or text(reason), "status_reason",
            f"An envelope in state {execution} must say why")

    history = doc["attempt_history"]
    require(integer(doc["attempt"], 1) and bool(history)
            and all(integer(h["attempt"], 1) and h["state"] in EXECUTION_STATES + (UNCERTAIN,) for h in history)
            and [h["attempt"] for h in history] == sorted({h["attempt"] for h in history})
            and history[-1]["attempt"] == doc["attempt"] and history[-1]["state"] == execution,
            "attempt_history",
            "attempt is 1-based; the history lists attempts in increasing order and ends with this attempt's state")

    nulls, listed = provenance_nulls(doc), list(doc["not_recorded"])
    silent = sorted(set(nulls) - set(listed))
    require(not silent, "silent_missing_provenance",
            f"null provenance fields are not listed in not_recorded: {silent}")
    stale = sorted(p for p in listed if not _resolves_to_null(doc, p))
    require(not stale, "not_recorded_pointer", f"not_recorded lists pointers that are not null fields: {stale}")

    evidence = doc["evidence"]
    require(all(key in evidence for key in EVIDENCE_KEYS) and text(evidence["evidence_class"])
            and text(evidence["clinical_review"]) and text(evidence["visibility"]), "evidence_fields",
            f"evidence needs {list(EVIDENCE_KEYS)}")
    require(evidence["synthetic"] == (evidence["evidence_class"] == SYNTHETIC_CLASS), "synthetic_label",
            "evidence.synthetic must be true exactly when evidence_class is 'synthetic_fixture'")
    check_evidence_labels(evidence, evidence["synthetic"])

    variant = doc["source"]["variant"]
    require(variant is None or variant in VARIANTS, "unknown_variant",
            f"source.variant must be one of {list(VARIANTS)}; got {variant!r}")
    identity = doc["environment"].get("input_identity_sha256")
    require(identity is None or bool(HEX64.fullmatch(str(identity))), "input_identity",
            "environment.input_identity_sha256 must be 64 hex digits or null")

    method, model = doc["method"], doc["model"]
    require(method["id"] in METHOD_IDS, "unknown_method", f"{method['id']!r}")
    require(method["representation_type"] in REPRESENTATION_TYPES + (NOT_APPLICABLE,), "representation_type",
            f"{method['representation_type']!r}")
    require(method["representation_type"] == METHOD_REPRESENTATION[method["id"]], "representation_type",
            f"method {method['id']} reads {METHOD_REPRESENTATION[method['id']]!r}, not "
            f"{method['representation_type']!r}")
    layers = method["layers"]
    require(integer(method["layer_index_base"]) and method["layer_index_base"] == 0, "layer_metadata",
            "layer_index_base must be 0")
    require(integer(model["n_layers"], 1) and all(integer(x) and x < model["n_layers"] for x in layers)
            and len(set(layers)) == len(layers), "layer_metadata",
            "method.layers must be distinct zero-based integers inside the model")
    require(integer(doc["input"]["n_tokens"], 1), "invalid_input", "input.n_tokens")

    counts = doc["counts"]
    require(all(integer(counts[key]) for key in ("requested", "accepted", "completed", "failed"))
            and all(text(x["reason"]) and integer(x["n"]) for x in counts["exclusions"]), "counts_arithmetic",
            "counts must be non-negative integers and each exclusion needs a reason and n")
    excluded = sum(x["n"] for x in counts["exclusions"])
    require(counts["accepted"] <= counts["requested"]
            and counts["completed"] + counts["failed"] + excluded == counts["accepted"], "counts_arithmetic",
            f"completed {counts['completed']} + failed {counts['failed']} + excluded {excluded} must equal "
            f"accepted {counts['accepted']}, and accepted may not exceed requested {counts['requested']}")
    require(execution != "completed" or counts["completed"] >= 1, "counts_arithmetic",
            "A completed envelope must count at least one completed unit")
    require(execution != "failed" or counts["failed"] >= 1, "counts_arithmetic",
            "A failed envelope must count at least one failed unit")
    require(execution not in NOT_EXECUTED_STATES or counts["accepted"] == 0, "counts_arithmetic",
            f"An envelope in state {execution} executed nothing, so it accepts no unit")
    require(execution == "completed" or counts["requested"] != 1 or counts["completed"] == 0, "counts_arithmetic",
            f"A single-task envelope in state {execution} cannot count a completed unit")

    resources = doc["resources"]
    require(execution not in NOT_EXECUTED_STATES or resources["measured"] is False, "resources_rule",
            f"An envelope in state {execution} executed nothing, so it measures no resource")
    for key in NUMERIC_RESOURCES:
        value = resources[key]
        require(value is None or (type(value) in (int, float) and math.isfinite(value) and value >= 0),
                "resources_rule", f"resources.{key} must be a non-negative finite number or null")
    if resources["measured"]:
        require(resources["runtime_seconds"] is not None, "resources_rule",
                "measured resources need a numeric runtime_seconds")
    else:
        require(all(resources[key] is None for key in NUMERIC_RESOURCES) and resources["usage"] is None,
                "resources_rule", "Unmeasured resources must all be null: an envelope stores no estimate")

    payload, verified = doc["payload"], False
    if execution != "completed":
        require(payload is None, "payload_state", f"payload must be null in state {execution}")
    else:
        require(isinstance(payload, dict), "payload_state", "A completed envelope needs a payload reference")
        require(payload["kind"] in PAYLOAD_KINDS and payload["kind"] in METHOD_PAYLOAD_KINDS[method["id"]],
                "method_payload_mismatch",
                f"method {method['id']} files {list(METHOD_PAYLOAD_KINDS[method['id']])}, not {payload['kind']!r}")
        require(bool(HEX64.fullmatch(payload["sha256"]))
                and PurePosixPath(payload["path"]) == PurePosixPath("payloads") / f"{payload['sha256']}.json",
                "payload_path", "payload.path must be payloads/<sha256>.json")
        if payload_root is not None:
            file = Path(payload_root) / payload["path"]
            require(file.is_file(), "payload_hash", f"payload file {payload['path']} is missing")
            actual = sha256_file(file)
            require(actual == payload["sha256"], "payload_hash",
                    f"payload file {payload['path']} has SHA-256 {actual}, not the recorded value")
            verified = True
    return {"status": "validated", "execution": execution, "payload_verified": verified}


def validate_envelope(doc: Any, *, payload_root: Path | str | None = None) -> dict[str, Any]:
    """Validate an envelope; raise ``Refusal`` with a named code on the first violated rule.

    With ``payload_root`` (the run directory) the payload file of a completed envelope is read and its SHA-256
    compared (``payload_hash``). Without it the file is not read and the result says ``payload_verified: false``.
    """
    try:
        return _validate(doc, Path(payload_root) if payload_root is not None else None)
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", f"{type(exc).__name__}: {exc}") from exc
