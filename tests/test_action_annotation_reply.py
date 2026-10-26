"""Raw synthetic replies through the annotation parser; no network or archive reads."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import action_annotation_messages as am
from scripts import action_annotation_transport as at
from scripts import action_annotations as aa

FIXTURES = Path(__file__).parent / "fixtures/action_annotations"


@pytest.fixture
def example() -> tuple[dict[str, Any], at.Reply, str]:
    source = aa.read_json(FIXTURES / "sources.json")["items"][0]
    attempt = aa.read_json(FIXTURES / "messages_attempts.json")["items"][0]
    model = aa.read_json(FIXTURES / "messages_settings.json")["model"]
    return source, at.Reply(200, attempt["request_id"], attempt["body"].encode(), True, None), model


def interpret(example: tuple[dict[str, Any], at.Reply, str], reply: at.Reply | None = None) -> dict[str, Any]:
    source, original, model = example
    return am.interpret_reply(original if reply is None else reply, expected_model=model, source_text=source["text"])


def test_raw_reply_matches_existing_replay_without_promoting_evidence() -> None:
    sources, settings, attempts = [aa.read_json(FIXTURES / name) for name in
                                  ("sources.json", "messages_settings.json", "messages_attempts.json")]
    legacy = am.replay(sources, settings, attempts)
    for source, attempt, old in zip(sources["items"], attempts["items"], legacy["items"]):
        raw = attempt["body"].encode("utf-8")
        result = am.interpret_reply(at.Reply(200, attempt["request_id"], raw, True, None),
                                    expected_model=settings["model"], source_text=source["text"])
        assert result["schema_version"] == "patientwords.action-reply-interpretation/1"
        for key in ("annotation", "status", "usage", "usage_status", "message_id", "reported_model", "stop_reason"):
            assert result[key] == old[key]
        assert result["raw_body_sha256"] == aa.digest(raw)
        assert result["raw_body_bytes"] == len(raw)
        assert result["source_sha256"] == source["source_sha256"]
        assert result["source_binding"] == "caller_asserted_not_admitted"
        assert result["cost_usd"] is None and result["reservation_release_allowed"] is False
        aa.encoded(result)


@pytest.mark.parametrize("error", ["timeout", "connection_error", "incomplete_response", "response_byte_limit"])
def test_complete_looking_partial_body_is_never_accepted(example: tuple, error: str) -> None:
    result = interpret(example, replace(example[1], complete=False, error=error))
    assert result["status"] == "transport_incomplete"
    assert result["annotation"] is None and result["usage"] is None
    assert result["transport_error"] == error and result["body_complete"] is False
    assert result["raw_body_sha256"] == aa.digest(example[1].body)
    assert result["cost_usd"] is None and result["reservation_release_allowed"] is False


@pytest.mark.parametrize("raw,status", [(b"\xff\xfe", "invalid_response_encoding"),
                                       (b'{"x":1,"x":2}', "invalid_response_json"),
                                       (b'{"x":NaN}', "invalid_response_json"),
                                       (b'{"x":1e999}', "invalid_response_json"),
                                       (b'{"x":"\\ud800"}', "invalid_response_json"),
                                       (b"", "invalid_response_json")])
def test_invalid_bytes_remain_identifiable(example: tuple, raw: bytes, status: str) -> None:
    result = interpret(example, replace(example[1], body=raw))
    assert result["status"] == status and result["annotation"] is None
    assert result["raw_body_sha256"] == aa.digest(raw)
    assert result["cost_usd"] is None


@pytest.mark.parametrize("field,value,status", [
    ("model", "other", "model_mismatch"), ("stop_reason", "max_tokens", "truncated"),
    ("stop_reason", "refusal", "provider_refusal"), ("stop_reason", "new", "unsupported_stop_reason"),
    ("usage", None, "invalid_or_missing_usage"),
    ("usage", {"input_tokens": True, "output_tokens": 1}, "invalid_or_missing_usage"),
    ("content", [{"type": "thinking", "thinking": "fixture"}], "unsupported_content"),
    ("content", [{"type": "text", "text": "{}"}], "invalid_annotation"),
])
def test_provider_failures_remain_outcomes(example: tuple, field: str, value: Any, status: str) -> None:
    body = json.loads(example[1].body)
    body[field] = value
    result = interpret(example, replace(example[1], body=aa.encoded(body)))
    assert result["status"] == status and result["annotation"] is None


def test_source_spans_use_supplied_text_and_model_is_exact(example: tuple) -> None:
    _, reply, model = example
    wrong_text = am.interpret_reply(reply, expected_model=model, source_text="Different source.")
    assert wrong_text["status"] == "invalid_annotation"
    wrong_model = am.interpret_reply(reply, expected_model="other", source_text=example[0]["text"])
    assert wrong_model["status"] == "model_mismatch"


def test_additional_usage_is_preserved_but_not_priced(example: tuple) -> None:
    body = json.loads(example[1].body)
    body["usage"].update(cache_read_input_tokens=9, cache_creation={"unknown_unit": 3})
    result = interpret(example, replace(example[1], body=aa.encoded(body)))
    assert result["usage"] == body["usage"]
    assert result["usage_status"] == "base_counts_present_not_priced"
    assert result["cost_usd"] is None and result["reservation_release_allowed"] is False


@pytest.mark.parametrize("kwargs", [
    {"http_status": True}, {"http_status": 0}, {"http_status": None}, {"body": "not bytes"},
    {"complete": 1}, {"complete": False}, {"error": "timeout"}, {"error": []},
    {"request_id": " "}, {"request_id": "\ud800"}, {"body": b"x" * (at.MAX_BODY_BYTES + 1)},
])
def test_invalid_transport_contract_refuses(example: tuple, kwargs: dict[str, Any]) -> None:
    with pytest.raises(aa.AnnotationRefusal, match="invalid_transport_reply"):
        interpret(example, replace(example[1], **kwargs))


@pytest.mark.parametrize("field,value", [("expected_model", None), ("expected_model", ""),
                                         ("source_text", ""), ("source_text", "\ud800")])
def test_invalid_context_refuses(example: tuple, field: str, value: Any) -> None:
    args = {"expected_model": example[2], "source_text": example[0]["text"]}
    args[field] = value
    with pytest.raises(aa.AnnotationRefusal):
        am.interpret_reply(example[1], **args)


def test_capture_and_parse_fixed_profile_without_calling_provider(example: tuple, tmp_path: Path) -> None:
    source, reply, _ = example
    wire = at.prepare_wire("Extract explicit actions as JSON.", source["text"])
    body = json.loads(reply.body)
    body["model"] = wire["body"]["model"]
    supplied = replace(reply, body=aa.encoded(body))
    original = copy.deepcopy(supplied)
    root = tmp_path / "action_annotation_attempts"
    root.mkdir()
    receipt = at.capture_attempt(wire, source_id=source["source_id"], source_sha256=source["source_sha256"],
                                 run_root=root, send=lambda _: supplied)
    raw = (root / receipt["request_sha256"] / "response.bin").read_bytes()
    result = am.interpret_reply(at.Reply(receipt["http_status"], receipt["request_id"], raw,
                                         receipt["body_complete"], receipt["transport_error"]),
                                expected_model=wire["body"]["model"], source_text=source["text"])
    assert result["status"] == "validated_semantics_unverified"
    assert result["raw_body_sha256"] == receipt["raw_body_sha256"]
    assert supplied == original
    assert receipt["status"] == "http_response_uninterpreted"
    assert (root / receipt["request_sha256"] / "result.json").read_bytes() == aa.encoded(receipt)


def test_http_error_missing_id_and_empty_transport_failure(example: tuple) -> None:
    assert interpret(example, replace(example[1], http_status=429))["status"] == "http_error"
    assert interpret(example, replace(example[1], request_id=None))["status"] == "missing_request_id"
    failed = interpret(example, at.Reply(None, None, b"", False, "connection_error"))
    assert failed["status"] == "transport_incomplete" and failed["cost_usd"] is None

