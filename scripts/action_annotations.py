"""Offline preparation and evidence validation; never calls a provider.

The v1 rehearsal accepts synthetic sources only. Semantic labels remain unverified
even when quotes match. No existing score, collector or publication input changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.frontend_contract_schema import check_schema_subset

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/action_annotations"


class AnnotationRefusal(ValueError):
    """A named refusal rather than partial or silently repaired annotations."""


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AnnotationRefusal("duplicate_json_key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise AnnotationRefusal("nonfinite_json")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AnnotationRefusal("unreadable_json") from exc


def _keys(value: Any, keys: set[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise AnnotationRefusal(code)


def _text(value: Any, code: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AnnotationRefusal(code)
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise AnnotationRefusal("invalid_utf8") from exc


def sources(document: Any) -> list[dict[str, Any]]:
    """Require explicit synthetic origin, complete unique IDs and exact UTF-8 hashes."""
    _keys(document, {"schema_version", "artifact_kind", "items"}, "source_shape")
    if document["schema_version"] != "patientwords.action-sources/1":
        raise AnnotationRefusal("source_version")
    if document["artifact_kind"] != "synthetic_fixture":
        raise AnnotationRefusal("research_input_not_enabled")
    items = document["items"]
    if not isinstance(items, list) or not items:
        raise AnnotationRefusal("empty_sources")
    seen: set[str] = set()
    for item in items:
        _keys(item, {"source_id", "text", "source_sha256"}, "source_item_shape")
        _text(item["source_id"], "source_id")
        _text(item["text"], "source_text")
        if item["source_id"] in seen:
            raise AnnotationRefusal("duplicate_source_id")
        seen.add(item["source_id"])
        if item["source_sha256"] != digest(item["text"].encode("utf-8")):
            raise AnnotationRefusal("source_hash_mismatch")
    return items


def prepare(document: Any) -> dict[str, Any]:
    """Build blinded, deterministic request previews without answers or source labels."""
    items = sources(document)
    rubric_path = CONTRACT / "rubric.v1.json"
    schema_path = CONTRACT / "annotation.v1.schema.json"
    rubric, schema = read_json(rubric_path), read_json(schema_path)
    system = json.dumps(rubric, ensure_ascii=False, sort_keys=True)
    requests = []
    for item in items:
        payload = {"system": system, "user": json.dumps({"response": item["text"]}, ensure_ascii=False),
                   "response_schema": schema}
        requests.append({"source_id": item["source_id"], "source_sha256": item["source_sha256"],
                         "request_sha256": digest(encoded(payload)), "payload": payload})
    return {"schema_version": "patientwords.action-requests/1", "status": "offline_prepared",
            "artifact_kind": "synthetic_fixture", "sources_sha256": digest(encoded(document)),
            "rubric_sha256": digest(rubric_path.read_bytes()), "schema_sha256": digest(schema_path.read_bytes()),
            "implementation_sha256": digest(Path(__file__).read_bytes()), "requests": requests}


def _span(span: dict[str, Any], text: str) -> None:
    start, end, quote = span["start"], span["end"], span["quote"]
    # Offsets are Unicode code points, zero-based half-open; no normalization.
    if not (0 <= start < end <= len(text)) or text[start:end] != quote or not quote.strip():
        raise AnnotationRefusal("evidence_span_mismatch")


def validate_annotation(annotation: Any, text: str) -> None:
    """Check structure first, then rubric values and literal evidence (not meaning)."""
    schema = read_json(CONTRACT / "annotation.v1.schema.json")
    errors: list[str] = []
    check_schema_subset(lambda artifact, path, message: errors.append(f"{path}: {message}"),
                        "annotation", annotation, schema)
    if errors:
        raise AnnotationRefusal("annotation_schema: " + "; ".join(errors))
    rubric = read_json(CONTRACT / "rubric.v1.json")
    status, actions, reason = annotation["status"], annotation["actions"], annotation["reason"]
    if status not in rubric["status"]:
        raise AnnotationRefusal("unknown_status")
    if status == "annotated":
        if not actions or reason is not None:
            raise AnnotationRefusal("annotated_state")
    elif actions:
        raise AnnotationRefusal("nonannotated_actions")
    elif status == "uncertain":
        _text(reason, "uncertainty_reason_required")
    elif reason is not None:
        raise AnnotationRefusal("no_actions_reason_must_be_null")
    seen: set[bytes] = set()
    for action in actions:
        for field in ("category", "stance", "actor"):
            if action[field] not in rubric[field]:
                raise AnnotationRefusal(f"unknown_{field}")
        _span(action["evidence"], text)
        for field in ("timing", "condition"):
            if action[field] is not None:
                _span(action[field], text)
                if not (action["evidence"]["start"] <= action[field]["start"]
                        < action[field]["end"] <= action["evidence"]["end"]):
                    raise AnnotationRefusal(f"{field}_outside_evidence")
        if action["stance"] == "conditional" and action["condition"] is None:
            raise AnnotationRefusal("conditional_without_condition")
        identity = encoded(action)
        if identity in seen:
            raise AnnotationRefusal("duplicate_action")
        seen.add(identity)


def validate(document: Any, responses: Any) -> dict[str, Any]:
    """Validate the whole packet before producing anything; no dropped source rows."""
    request = prepare(document)
    _keys(responses, {"schema_version", "artifact_kind", "items"}, "response_shape")
    if responses["schema_version"] != "patientwords.action-responses/1":
        raise AnnotationRefusal("response_version")
    if responses["artifact_kind"] != "synthetic_fixture":
        raise AnnotationRefusal("research_response_not_enabled")
    rows = responses["items"]
    if not isinstance(rows, list):
        raise AnnotationRefusal("response_items")
    by_id: dict[str, Any] = {}
    for row in rows:
        _keys(row, {"source_id", "source_sha256", "request_sha256", "annotation"}, "response_item_shape")
        _text(row["source_id"], "response_source_id")
        if row["source_id"] in by_id:
            raise AnnotationRefusal("duplicate_response_id")
        by_id[row["source_id"]] = row
    if set(by_id) != {item["source_id"] for item in request["requests"]}:
        raise AnnotationRefusal("response_coverage_mismatch")
    ordered = []
    for item, req in zip(document["items"], request["requests"]):
        row = by_id[item["source_id"]]
        for field in ("source_sha256", "request_sha256"):
            if row[field] != req[field]:
                raise AnnotationRefusal(f"{field}_mismatch")
        validate_annotation(row["annotation"], item["text"])
        ordered.append(row)
    return {"schema_version": "patientwords.action-validation/1", "artifact_kind": "synthetic_fixture",
            "status": "structurally_valid_semantics_unverified", "model_calls": 0,
            "request_packet": request, "responses_sha256": digest(encoded(responses)), "items": ordered}


def score(document: Any, responses: Any, key: Any) -> dict[str, Any]:
    """Compare a complete packet with a separately supplied synthetic key.

    Exact action matching includes spans, qualifiers and all labels, ignores array
    order, and is deliberately stricter than semantic equivalence. Empty cases and
    uncertain cases remain explicit; this is not a validity or accuracy estimate.
    """
    result = validate(document, responses)
    expected = validate(document, key)
    comparisons = []
    for row, gold in zip(result["items"], expected["items"]):
        actual_actions = {encoded(a) for a in row["annotation"]["actions"]}
        gold_actions = {encoded(a) for a in gold["annotation"]["actions"]}
        same_status = row["annotation"]["status"] == gold["annotation"]["status"]
        comparisons.append({"source_id": row["source_id"], "status_matches": same_status,
                            "observed_status": row["annotation"]["status"],
                            "expected_status": gold["annotation"]["status"],
                            "matched_actions": len(actual_actions & gold_actions),
                            "extra_actions": len(actual_actions - gold_actions),
                            "missing_actions": len(gold_actions - actual_actions),
                            "exact_case_match": same_status and actual_actions == gold_actions})
    result["key_comparison"] = {"status": "synthetic_exact_match_only", "key_sha256": digest(encoded(key)),
                                "cases": comparisons,
                                "exact_case_matches": sum(c["exact_case_match"] for c in comparisons),
                                "total_cases": len(comparisons)}
    return result


def write_new(path: Path, result: dict[str, Any]) -> None:
    """Exclusive creation outside Git; refuse paths usable by measurement collectors."""
    path = path.resolve()
    if path.name not in {"action_requests.json", "action_annotations.json"}:
        raise AnnotationRefusal("output_filename")
    if any((parent / ".git").exists() for parent in path.parents):
        raise AnnotationRefusal("output_inside_repository")
    body = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(body)
    except FileExistsError as exc:
        raise AnnotationRefusal("output_exists") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "validate", "score"])
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--key", type=Path, help="Separately specified synthetic reference packet; score mode only")
    parser.add_argument("--out", type=Path, required=True, help="New named JSON file in an existing directory outside Git")
    args = parser.parse_args(argv)
    if (args.mode != "prepare") != (args.responses is not None):
        parser.error("validate/score require --responses; prepare forbids it")
    if (args.mode == "score") != (args.key is not None):
        parser.error("score requires --key; other modes forbid it")
    try:
        document = read_json(args.sources)
        if args.mode == "prepare":
            result = prepare(document)
        elif args.mode == "score":
            result = score(document, read_json(args.responses), read_json(args.key))
        else:
            result = validate(document, read_json(args.responses))
        write_new(args.out, result)
    except (AnnotationRefusal, OSError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": result["status"], "output": str(args.out), "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
