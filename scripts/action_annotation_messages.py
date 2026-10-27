"""Synthetic-only Messages preparation/replay and offline raw-reply interpretation.

Keep failed attempts visible. A valid response shape is not verified semantics.
The transport record is a fixture assertion, not authenticated provider evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from scripts import action_annotations as aa
from scripts.action_annotation_transport import Reply, validate_reply

PROTOCOL = aa.CONTRACT / "messages_protocol.v1.json"


def _shape(value: Any, keys: set[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise aa.AnnotationRefusal(code)


def _text(value: Any, code: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise aa.AnnotationRefusal(code)
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise aa.AnnotationRefusal(code) from exc


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise aa.AnnotationRefusal("duplicate_json_key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise aa.AnnotationRefusal("nonfinite_json")


def _parse(text: str) -> Any:
    value = json.loads(text, object_pairs_hook=_unique, parse_constant=_nonfinite)
    aa.encoded(value)  # Reject overflowed floats and invalid escaped Unicode anywhere.
    return value


def prepare(document: Any, settings: Any) -> dict[str, Any]:
    """Bind a text-only nonstreaming request to the unchanged v1 preview and settings."""
    _shape(settings, {"model", "max_tokens"}, "settings_shape")
    _text(settings["model"], "model_required")
    if type(settings["max_tokens"]) is not int or not 1 <= settings["max_tokens"] <= 8192:
        raise aa.AnnotationRefusal("max_tokens_outside_rehearsal_bound")
    preview = aa.prepare(document)  # Preserves the existing synthetic-only gate.
    protocol = aa.read_json(PROTOCOL)
    requests = []
    for row in preview["requests"]:
        payload = row["payload"]
        body = {"model": settings["model"], "max_tokens": settings["max_tokens"], "stream": False,
                "system": payload["system"] + "\n" + protocol["format_instruction"] + "\n"
                + aa.encoded(payload["response_schema"]).decode("utf-8"),
                "messages": [{"role": "user", "content": [{"type": "text", "text": payload["user"]}]}]}
        wire = {"method": "POST", "path": "/v1/messages", "api_version": protocol["api_version"], "body": body}
        requests.append({"source_id": row["source_id"], "source_sha256": row["source_sha256"],
                         "preview_request_sha256": row["request_sha256"],
                         "request_sha256": aa.digest(aa.encoded(wire)), "request": wire})
    return {"schema_version": "patientwords.action-messages-requests/1", "artifact_kind": "synthetic_fixture",
            "status": "offline_only_model_support_unverified", "model_calls": 0,
            "preview": preview, "protocol_sha256": aa.digest(PROTOCOL.read_bytes()),
            "implementation_sha256": aa.digest(Path(__file__).read_bytes()), "requests": requests}


def _utc(value: Any) -> datetime:
    _text(value, "attempt_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise aa.AnnotationRefusal("attempt_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise aa.AnnotationRefusal("attempt_timestamp_not_utc")
    return parsed


def _attempt(row: Any, request: dict[str, Any]) -> None:
    _shape(row, {"source_id", "request_sha256", "started_utc", "finished_utc", "http_status",
                 "request_id", "body", "transport_error"}, "attempt_shape")
    if row["request_sha256"] != request["request_sha256"]:
        raise aa.AnnotationRefusal("wire_request_hash_mismatch")
    if _utc(row["finished_utc"]) < _utc(row["started_utc"]):
        raise aa.AnnotationRefusal("attempt_time_reversed")
    if row["request_id"] is not None:
        _text(row["request_id"], "request_id")
    if row["transport_error"] is not None:
        if not isinstance(row["transport_error"], str) or row["transport_error"] not in {"timeout", "connection_error"}:
            raise aa.AnnotationRefusal("unsupported_transport_error")
        if any(row[k] is not None for k in ("http_status", "request_id", "body")):
            raise aa.AnnotationRefusal("transport_response_conflict")
    else:
        if type(row["http_status"]) is not int or not 100 <= row["http_status"] <= 599:
            raise aa.AnnotationRefusal("http_status")
        # Empty/malformed response bodies remain recordable failures.
        if not isinstance(row["body"], str):
            raise aa.AnnotationRefusal("response_body_type")
        try:
            row["body"].encode("utf-8")
        except UnicodeError as exc:
            raise aa.AnnotationRefusal("response_body_encoding") from exc


def _interpret(row: dict[str, Any], request: dict[str, Any], text: str,
               response_format: str = 'patientwords.action-spans/1') -> dict[str, Any]:
    result: dict[str, Any] = {"status": "transport_error", "annotation": None, "refusal": None,
                              "usage": None, "usage_status": "unavailable", "message_id": None,
                              "reported_model": None, "stop_reason": None}
    if row["transport_error"] is not None:
        return result
    try:
        response = _parse(row["body"])
    except (ValueError, aa.AnnotationRefusal):
        result["status"] = "invalid_response_json" if row["http_status"] == 200 else "http_error"
        return result
    if not isinstance(response, dict):
        result["status"] = "invalid_response_shape" if row["http_status"] == 200 else "http_error"
        return result
    # Preserve the complete supplied usage, including future/cache-specific fields.
    # No token summation, price fallback, cost estimate or budget admission here.
    result.update(usage=response.get("usage"), message_id=response.get("id"),
                  reported_model=response.get("model"), stop_reason=response.get("stop_reason"))
    usage = result["usage"]
    if isinstance(usage, dict):
        fields = {"input_tokens", "output_tokens"}
        counts = fields | ({"cache_creation_input_tokens", "cache_read_input_tokens"} & usage.keys())
        result["usage_status"] = "base_counts_present_not_priced" if fields <= usage.keys() and all(
            type(usage[k]) is int and usage[k] >= 0 for k in counts) else "invalid_usage"
    elif usage is not None:
        result["usage_status"] = "invalid_usage"
    if row["http_status"] != 200:
        result["status"] = "http_error"
    elif response.get("type") != "message" or response.get("role") != "assistant":
        result["status"] = "invalid_response_shape"
    elif not isinstance(result["message_id"], str) or not result["message_id"].strip():
        result["status"] = "missing_message_id"
    elif row["request_id"] is None:
        result["status"] = "missing_request_id"
    elif result["reported_model"] != request["request"]["body"]["model"]:
        result["status"] = "model_mismatch"
    elif result["usage_status"] != "base_counts_present_not_priced":
        result["status"] = "invalid_or_missing_usage"
    elif result["stop_reason"] != "end_turn":
        result["status"] = {"max_tokens": "truncated", "refusal": "provider_refusal"}.get(
            str(result["stop_reason"]), "unsupported_stop_reason")
    elif response.get("stop_sequence") is not None:
        result["status"] = "unexpected_stop_sequence"
    else:
        content = response.get("content")
        if (not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict)
                or content[0].get("type") != "text" or not isinstance(content[0].get("text"), str)
                or content[0].get("citations")):
            result["status"] = "unsupported_content"
            return result
        try:
            annotation = _parse(content[0]["text"])
            if response_format == 'patientwords.action-quotes/1':
                from scripts.action_quote_annotations import normalize
                result['provider_annotation'] = annotation
                annotation = normalize(annotation, text)
            else:
                aa.validate_annotation(annotation, text)
        except (ValueError, TypeError, KeyError) as exc:
            result.update(status="invalid_annotation", refusal=str(exc))
        else:
            result.update(status="validated_semantics_unverified", annotation=annotation)
    return result


def interpret_reply(reply: Reply, *, expected_model: str, source_text: str,
                    response_format: str = 'patientwords.action-spans/1') -> dict[str, Any]:
    """Interpret captured bytes without sending, authenticating, admitting or pricing.

    The caller must bind source/model/request/receipt identities before using this
    result. Matching literal spans proves neither that the request used this source
    nor that the proposed labels are correct. Keep the original capture unchanged.
    """
    if response_format not in ('patientwords.action-spans/1', 'patientwords.action-quotes/1'):
        raise aa.AnnotationRefusal('unsupported_response_format')
    validate_reply(reply)
    _text(expected_model, "expected_model_required")
    _text(source_text, "source_text_required")
    outcome: dict[str, Any] = {
        "status": "transport_incomplete", "annotation": None, "refusal": None,
        "usage": None, "usage_status": "unavailable", "message_id": None,
        "reported_model": None, "stop_reason": None,
    }
    if reply.complete:
        try:
            body = reply.body.decode("utf-8")
        except UnicodeDecodeError:
            outcome["status"] = "invalid_response_encoding"
        else:
            outcome = _interpret(
                {"transport_error": None, "http_status": reply.http_status,
                 "request_id": reply.request_id, "body": body},
                {"request": {"body": {"model": expected_model}}}, source_text, response_format)
    # An incomplete body cannot supply trusted usage, even if its prefix parses.
    # Its exact bytes remain in response.bin; this derived record identifies them.
    result = {
        "schema_version": "patientwords.action-reply-interpretation/1",
        "source_binding": "caller_asserted_not_admitted",
        "source_sha256": aa.digest(source_text.encode("utf-8")), "expected_model": expected_model,
        "http_status": reply.http_status, "request_id": reply.request_id,
        "body_complete": reply.complete, "transport_error": reply.error,
        "raw_body_sha256": aa.digest(reply.body), "raw_body_bytes": len(reply.body),
        "cost_usd": None, "reservation_release_allowed": False, **outcome,
    }
    if response_format == 'patientwords.action-quotes/1':
        from scripts import action_quote_annotations as quotes
        result.update(schema_version='patientwords.action-reply-interpretation/2',
                      response_format=response_format,
                      normalization={'method': 'unique_literal_quotes_unicode_codepoints/1',
                                     'implementation_sha256': aa.digest(Path(quotes.__file__).read_bytes()),
                                     'provider_schema_sha256': aa.digest((aa.ROOT / quotes.SCHEMA).read_bytes()),
                                     'normalized_schema_sha256': aa.digest(
                                         (aa.CONTRACT / 'annotation.v1.schema.json').read_bytes())})
    return result


def replay(document: Any, settings: Any, attempts: Any) -> dict[str, Any]:
    """One fixture attempt per source; preserve every failure and refuse incomplete joins."""
    packet = prepare(document, settings)
    _shape(attempts, {"schema_version", "artifact_kind", "items"}, "attempts_shape")
    if attempts["schema_version"] != "patientwords.action-messages-attempts/1":
        raise aa.AnnotationRefusal("attempts_version")
    if attempts["artifact_kind"] != "synthetic_fixture":
        raise aa.AnnotationRefusal("research_attempts_not_enabled")
    if not isinstance(attempts["items"], list):
        raise aa.AnnotationRefusal("attempts_items")
    by_id = {}
    for row in attempts["items"]:
        if not isinstance(row, dict):
            raise aa.AnnotationRefusal("attempt_shape")
        _text(row.get("source_id"), "attempt_source_id")
        if row["source_id"] in by_id:
            raise aa.AnnotationRefusal("duplicate_attempt_source")
        by_id[row["source_id"]] = row
    if set(by_id) != {r["source_id"] for r in packet["requests"]}:
        raise aa.AnnotationRefusal("attempt_coverage_mismatch")
    results, normalized = [], []
    for source, req in zip(document["items"], packet["requests"]):
        attempt = by_id[source["source_id"]]
        _attempt(attempt, req)
        outcome = _interpret(attempt, req, source["text"])
        results.append({"source_id": source["source_id"], "source_sha256": source["source_sha256"],
                        "attempt": attempt, "attempt_sha256": aa.digest(aa.encoded(attempt)),
                        "raw_body_sha256": None if attempt["body"] is None else aa.digest(
                            attempt["body"].encode("utf-8")), **outcome})
        normalized.append({"source_id": source["source_id"], "source_sha256": source["source_sha256"],
                           "request_sha256": req["preview_request_sha256"], "annotation": outcome["annotation"]})
    complete = all(row["status"] == "validated_semantics_unverified" for row in results)
    response_packet = {"schema_version": "patientwords.action-responses/1", "artifact_kind": "synthetic_fixture",
                       "items": normalized} if complete else None
    if complete:
        aa.validate(document, response_packet)
    return {"schema_version": "patientwords.action-messages-replay/1", "artifact_kind": "synthetic_fixture",
            "status": "complete_semantics_unverified" if complete else "incomplete_attempts_preserved",
            "model_calls": 0, "cost": {"status": "not_priced", "usd": None},
            "request_packet": packet, "attempts_sha256": aa.digest(aa.encoded(attempts)),
            "status_counts": dict(sorted(Counter(r["status"] for r in results).items())),
            "items": results, "response_packet": response_packet}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "replay"])
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--attempts", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if (args.mode == "replay") != (args.attempts is not None):
        parser.error("replay requires --attempts; prepare forbids it")
    try:
        document, settings = aa.read_json(args.sources), aa.read_json(args.settings)
        result = prepare(document, settings) if args.mode == "prepare" else replay(
            document, settings, aa.read_json(args.attempts))
        aa.write_new(args.out, result)
    except (aa.AnnotationRefusal, OSError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    # A recorded failure is not a successful annotation campaign.
    return 1 if result["status"] == "incomplete_attempts_preserved" else 0


if __name__ == "__main__":
    raise SystemExit(main())
