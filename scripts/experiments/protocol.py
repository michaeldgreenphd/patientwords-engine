"""Validate an experiment protocol (``patientwords.experiment-protocol/1``).

A protocol names one model, a list of case families with register variants, the methods to apply, the
comparisons to derive and the number of replicates. Validation is offline: it reads the protocol and, for
every family of a non-synthetic protocol, asks ``scripts/results_policy.row_restriction`` whether the legacy
row or any variant prompt is sealed. A family needs no ``legacy_join`` for that check. It loads no model and
tokenizes nothing; token ids are supplied by the protocol and checked only against their own hash.

Every rule that can fail has a named refusal code. ``validate_protocol`` raises
``scripts.exploratory_methods.Refusal``; a seal that cannot be evaluated raises ``SealError`` from
``scripts/tierb_split.py``, which is a configuration error and is not converted into a refusal.
"""
from __future__ import annotations

from typing import Any, Callable

from scripts.experiments.common import (
    DTYPE_BYTES, FIXTURE_BACKEND, HEX40, HEX64, LAYERED_METHODS, METHOD_IDS, PROTOCOL_SCHEMA, SPLITS, VARIANTS,
    Refusal, digest, integer, prompt_digest, require, require_structure, text,
)
from scripts.experiments.envelope import check_evidence_labels

RowRestriction = Callable[[str | None, int | None, str | None], str | None]
SYNTHETIC_CLASS = "synthetic_fixture"
POSITION_WORDS = ("all", "last")
TARGET_ROLES = ("answer", "intermediate")
# Keys of an ICA basis block that may list the families used at each stage.
BASIS_FAMILY_KEYS = ("fit_families", "profile_families", "selection_families")


def _default_row_restriction() -> RowRestriction:
    from scripts import results_policy

    return results_policy.row_restriction


def _check_model(model: dict[str, Any]) -> None:
    for key in ("study_id", "hf_id", "tokenizer_id", "backend"):
        require(text(model.get(key)), "missing_model_metadata", key)
    for key in ("hidden_size", "n_layers"):
        require(integer(model.get(key), 1), "missing_dimensions", key)
    require(model.get("dtype") in DTYPE_BYTES, "unknown_dtype",
            f"dtype must be one of {sorted(DTYPE_BYTES)}; got {model.get('dtype')!r}")
    for key in ("revision", "tokenizer_revision"):
        value = model.get(key)
        require(text(value), "missing_revision", f"model.{key} must be a non-empty string")
        if model["backend"] != FIXTURE_BACKEND:
            require(bool(HEX40.fullmatch(value)), "missing_revision",
                    f"model.{key} must be a full 40-hex commit for backend {model['backend']!r}")


def _check_variant(family_id: str, name: str, entry: dict[str, Any]) -> None:
    where = f"{family_id}:{name}"
    require(name in VARIANTS, "unknown_variant", f"{where}: variant must be one of {list(VARIANTS)}")
    require(isinstance(entry.get("prompt"), str), "missing_prompt", where)
    require(entry.get("prompt_sha256") == prompt_digest(entry["prompt"]), "prompt_hash",
            f"{where}: prompt_sha256 is not the SHA-256 of the prompt's UTF-8 bytes")
    token_ids = entry.get("token_ids")
    require(isinstance(token_ids, list) and bool(token_ids) and all(integer(t) for t in token_ids),
            "invalid_token_ids", f"{where}: token_ids must be a non-empty list of non-negative integers")
    require(entry.get("token_sha256") == digest(token_ids), "token_hash",
            f"{where}: token_sha256 is not exploratory_methods.digest(token_ids)")


def _check_method(method: dict[str, Any], n_layers: int, discovery: set[str], families: set[str]) -> None:
    name = method["id"]
    layered = name in LAYERED_METHODS
    if layered or "layers" in method:
        require(text(method.get("capture_site")), "layer_metadata", f"{name}: capture_site is required")
        require("layer_index_base" in method and integer(method["layer_index_base"])
                and method["layer_index_base"] == 0, "layer_metadata",
                f"{name}: layer_index_base must be present and equal to 0")
        layers = method.get("layers")
        require(isinstance(layers, list) and bool(layers) and all(integer(x) for x in layers), "layer_metadata",
                f"{name}: layers must be a non-empty list of zero-based integers")
        require(len(set(layers)) == len(layers), "layer_metadata", f"{name}: duplicate layer")
        require(max(layers) < n_layers, "layer_metadata",
                f"{name}: layer {max(layers)} is outside a model with {n_layers} layers")
    positions = method.get("positions")
    require(positions is None or positions in POSITION_WORDS, "position_metadata",
            f"{name}: positions must be one of {list(POSITION_WORDS)} when present")
    if name == "ica_lens":
        basis = method.get("basis")
        require(isinstance(basis, dict) and bool(HEX64.fullmatch(str(basis.get("manifest_sha256", ""))))
                and text(basis.get("preprocessing")) and text(basis.get("fit_split")), "method_metadata",
                "ica_lens: basis needs manifest_sha256 (64 hex), fit_split and preprocessing")
        require(basis["fit_split"] == "discovery", "ica_basis_split",
                f"ica_lens: the basis must be fit on the discovery split, not {basis['fit_split']!r}")
        for key in BASIS_FAMILY_KEYS:
            listed = basis.get(key, [])
            require(isinstance(listed, list) and all(text(x) for x in listed), "method_metadata",
                    f"ica_lens: basis.{key} must be a list of family ids")
            unknown = sorted(set(listed) - families)
            require(not unknown, "method_metadata", f"ica_lens: basis.{key} names unknown families {unknown}")
            outside = sorted(set(listed) - discovery)
            require(not outside, "ica_basis_split",
                    f"ica_lens: basis.{key} uses families outside the discovery split: {outside}")


def _check_seal(family_id: str, variants: dict[str, Any], join: dict[str, Any] | None,
                check: RowRestriction) -> None:
    """Refuse ``holdout_refusal`` when the seal covers the family's legacy row or any of its variant prompts.

    With a ``legacy_join`` the clinical prompt is checked as that row (batch and 1-based index), which applies
    every rule of ``tierb_split.sealed_pair``. Every other prompt, and the clinical prompt of a family without
    a join, is checked with batch and index None: that asks whether the text is a registered holdout phrase,
    which is sealed wherever it occurs and needs no batch. The row rules are not applied to a non-clinical
    variant, because holdout membership of a row is defined on its clinical prompt.

    A synthetic protocol is not checked: it cannot declare a ``legacy_join`` (``synthetic_label``), its text
    is placeholders, and it must validate without the seal's inputs.

    The refusal names the family, the variant and the row. It never repeats prompt text.
    """
    if join is not None:
        restriction = check(join["batch"], join["batch_index"], variants.get("clinical", {}).get("prompt"))
        require(restriction is None, "holdout_refusal",
                f"{family_id}: legacy row ({join['batch']}, {join['batch_index']}) is restricted: {restriction}")
    for name in sorted(variants):
        prompt = variants[name]["prompt"]
        if not prompt or (join is not None and name == "clinical"):
            continue  # an empty prompt is no phrase; the joined clinical prompt was checked as its row above
        restriction = check(None, None, prompt)
        require(restriction is None, "holdout_refusal",
                f"{family_id}:{name}: the variant's prompt is restricted: {restriction}")


def _validate(doc: dict[str, Any], row_restriction: RowRestriction | None) -> dict[str, Any]:
    require(isinstance(doc, dict), "invalid_input", "A protocol must be a JSON object")
    require(doc.get("schema_version") == PROTOCOL_SCHEMA, "schema_version",
            f"Expected {PROTOCOL_SCHEMA}; got {doc.get('schema_version')!r}")
    require(integer(doc.get("seed")), "missing_seed", "An explicit non-negative integer seed is required")
    model = doc.get("model")
    require(isinstance(model, dict), "invalid_input", "model must be an object")
    for key in ("revision", "tokenizer_revision"):
        require(key in model, "missing_revision", f"model.{key} must be present, also for a fixture backend")
    require_structure(doc, "protocol")
    require(text(doc["protocol_id"]) and text(doc["version"]), "invalid_input", "protocol_id and version")
    _check_model(model)

    evidence = doc["evidence"]
    synthetic = doc["synthetic"]
    require(text(evidence.get("evidence_class")) and text(evidence.get("clinical_review")), "invalid_input",
            "evidence.evidence_class and evidence.clinical_review are required")
    require(synthetic == (evidence["evidence_class"] == SYNTHETIC_CLASS), "synthetic_label",
            "synthetic must be true exactly when evidence_class is 'synthetic_fixture'")
    require(model["backend"] != FIXTURE_BACKEND or synthetic, "synthetic_label",
            "The fixture backend produces no measurement, so its protocol must be synthetic")
    check_evidence_labels(evidence, synthetic)

    families = doc["case_families"]
    require(bool(families), "missing_cases", "At least one case family is required")
    family_split: dict[str, str] = {}
    prompt_split: dict[str, str] = {}
    join_split: dict[tuple[str, int, str], str] = {}
    for family in families:
        family_id, split = family["family_id"], family["split"]
        require(text(family_id), "invalid_input", "family_id must be a non-empty string")
        require(split in SPLITS, "split", f"{family_id}: split must be one of {list(SPLITS)}")
        if family_id in family_split:
            require(family_split[family_id] == split, "split_leakage",
                    f"family {family_id} occurs in splits {family_split[family_id]} and {split}")
            raise Refusal("duplicate_family", f"family {family_id} occurs twice")
        family_split[family_id] = split
        require(text(family.get("review_status")), "invalid_input", f"{family_id}: review_status is required")
        variants = family["variants"]
        require(bool(variants), "variant_missing", f"{family_id}: no variants")
        for name in sorted(variants):
            _check_variant(family_id, name, variants[name])
            prompt_hash = variants[name]["prompt_sha256"]
            require(prompt_split.setdefault(prompt_hash, split) == split, "split_leakage",
                    f"{family_id}:{name}: the same prompt hash occurs in splits {prompt_split[prompt_hash]} "
                    f"and {split}")
        targets = family["targets"]
        require(bool(targets), "target_ids", f"{family_id}: at least one target is required")
        require(len({t.get("id") for t in targets}) == len(targets), "target_ids", f"{family_id}: duplicate target")
        for target in targets:
            require(text(target.get("id")) and text(target.get("text")), "target_ids",
                    f"{family_id}: target id and text are required")
            ids = target.get("token_ids")
            require(isinstance(ids, list) and bool(ids) and all(integer(t) for t in ids), "target_token_ids",
                    f"{family_id}:{target['id']}")
            require(target.get("role", "answer") in TARGET_ROLES, "target_roles", f"{family_id}:{target['id']}")
        join = family.get("legacy_join")
        if join is not None:
            require(not synthetic, "synthetic_label",
                    f"{family_id}: a synthetic protocol may not join a real legacy row")
            require(text(join.get("batch")) and integer(join.get("batch_index"), 1) and text(join.get("model")),
                    "missing_join", f"{family_id}: legacy_join needs batch, 1-based batch_index and model")
            key = (join["batch"], join["batch_index"], join["model"])
            require(join_split.setdefault(key, split) == split, "split_leakage",
                    f"{family_id}: legacy join {key} occurs in splits {join_split[key]} and {split}")
        if not synthetic:
            _check_seal(family_id, variants, join, row_restriction or _default_row_restriction())

    methods = doc["methods"]
    require(bool(methods), "method_metadata", "At least one method is required")
    discovery = {f for f, s in family_split.items() if s == "discovery"}
    seen_methods: set[str] = set()
    for method in methods:
        require(method["id"] in METHOD_IDS, "unknown_method",
                f"{method['id']!r} is not one of {list(METHOD_IDS)}")
        require(method["id"] not in seen_methods, "method_metadata", f"method {method['id']} is listed twice")
        seen_methods.add(method["id"])
        _check_method(method, model["n_layers"], discovery, set(family_split))

    seen_comparisons: set[str] = set()
    for comparison in doc["comparisons"]:
        cid, a, b = comparison["id"], comparison["a"], comparison["b"]
        require(text(cid) and cid not in seen_comparisons, "comparison_metadata", f"comparison id {cid!r}")
        seen_comparisons.add(cid)
        require(a in VARIANTS and b in VARIANTS and a != b, "unknown_variant",
                f"comparison {cid}: a and b must be two different variants from {list(VARIANTS)}")
        for family in families:
            lacking = sorted({a, b} - set(family["variants"]))
            require(not lacking, "variant_missing",
                    f"comparison {cid} names {lacking}, which family {family['family_id']} lacks")

    require(integer(doc["replicates"], 1), "replicates", "replicates must be an integer of at least 1")
    endpoint = doc["primary_endpoint"]
    require(endpoint.get("method") in seen_methods and text(endpoint.get("metric")), "primary_endpoint",
            "primary_endpoint.method must be a listed method and metric must be named")
    for family in families:
        require(endpoint.get("target") in {t["id"] for t in family["targets"]}, "primary_endpoint",
                f"family {family['family_id']} has no target {endpoint.get('target')!r}")
    excluded: set[str] = set()
    for row in doc["exclusions"]:
        require(row.get("family_id") in family_split and text(row.get("reason"))
                and row["family_id"] not in excluded, "exclusions",
                "each exclusion names one known family once and gives a reason")
        excluded.add(row["family_id"])

    by_split = {split: sum(1 for s in family_split.values() if s == split) for split in SPLITS}
    return {"schema_version": PROTOCOL_SCHEMA, "status": "validated", "protocol_id": doc["protocol_id"],
            "version": doc["version"], "protocol_sha256": digest(doc), "synthetic": synthetic,
            "seed": doc["seed"], "families": len(families), "families_by_split": by_split,
            "excluded_families": sorted(excluded), "methods": [m["id"] for m in methods],
            "comparisons": [c["id"] for c in doc["comparisons"]], "replicates": doc["replicates"],
            "digest_convention": "scripts.exploratory_methods.digest"}


def validate_protocol(doc: Any, *, row_restriction: RowRestriction | None = None) -> dict[str, Any]:
    """Validate ``doc`` and return a summary that includes ``protocol_sha256``.

    ``row_restriction`` is the seal check applied to every family of a non-synthetic protocol: to the legacy
    row when ``legacy_join`` is declared, and to each variant prompt with batch and index None otherwise. It
    defaults to ``scripts.results_policy.row_restriction``. Tests pass a stub so that no sealed text is read.
    Malformed shapes refuse with ``invalid_input`` and never escape as ``KeyError`` or ``TypeError``.
    """
    try:
        return _validate(doc, row_restriction)
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", f"{type(exc).__name__}: {exc}") from exc
