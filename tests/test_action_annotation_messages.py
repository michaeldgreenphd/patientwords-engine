"""Offline synthetic provider-envelope replay; no SDK, credentials or archive reads."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from scripts import action_annotations as aa
from scripts import action_annotation_messages as am

FIXTURES = Path(__file__).parent / "fixtures/action_annotations"


@pytest.fixture
def inputs() -> tuple[dict, dict, dict]:
    return tuple(aa.read_json(FIXTURES / f) for f in
                 ("sources.json", "messages_settings.json", "messages_attempts.json"))


def body_change(attempts: dict, key: str, value: Any) -> None:
    body = json.loads(attempts["items"][0]["body"])
    body[key] = value
    attempts["items"][0]["body"] = json.dumps(body)


def test_literal_fixture_replay_joins_existing_validator_and_key(inputs: tuple[dict, dict, dict]) -> None:
    sources, settings, attempts = inputs
    result = am.replay(*inputs)
    assert result["model_calls"] == 0
    assert result["status"] == "complete_semantics_unverified"
    assert result["status_counts"] == {"validated_semantics_unverified": 10}
    assert result["cost"] == {"status": "not_priced", "usd": None}
    key = aa.read_json(FIXTURES / "responses.json")
    scored = aa.score(sources, result["response_packet"], key)
    assert scored["key_comparison"]["exact_case_matches"] == 10
    assert result["response_packet"] == key
    for actual, original in zip(result["items"], attempts["items"]):
        assert actual["attempt"] == original
        assert actual["raw_body_sha256"] == aa.digest(original["body"].encode("utf-8"))
    assert result == am.replay(*copy.deepcopy(inputs))


def test_request_is_blinded_and_settings_version_are_hash_bound(inputs: tuple[dict, dict, dict]) -> None:
    sources, settings, _ = inputs
    preview = aa.prepare(sources)
    packet = am.prepare(sources, settings)
    request = packet["requests"][0]
    wire = request["request"]
    assert wire["api_version"] == "2026-10-21"
    assert wire["method"] == "POST" and wire["path"] == "/v1/messages"
    assert set(wire["body"]) == {"model", "max_tokens", "stream", "system", "messages"}
    assert wire["body"]["stream"] is False
    assert wire["body"]["messages"] == [{"role": "user", "content": [
        {"type": "text", "text": preview["requests"][0]["payload"]["user"]}]}]
    assert request["preview_request_sha256"] == preview["requests"][0]["request_sha256"]
    assert request["request_sha256"] == aa.digest(aa.encoded(wire))
    assert request["request_sha256"] != request["preview_request_sha256"]
    settings["max_tokens"] += 1
    assert request["request_sha256"] != am.prepare(sources, settings)["requests"][0]["request_sha256"]


@pytest.mark.parametrize("key,value", [("max_tokens", True), ("max_tokens", 0), ("max_tokens", 8193),
                                        ("max_tokens", 1.0), ("model", " "), ("model", None)])
def test_invalid_settings_refuse(inputs: tuple[dict, dict, dict], key: str, value: Any) -> None:
    sources, settings, _ = inputs
    settings[key] = value
    with pytest.raises(aa.AnnotationRefusal):
        am.prepare(sources, settings)


@pytest.mark.parametrize("extra", ["temperature", "tools", "api_key"])
def test_unsupported_request_settings_refuse(inputs: tuple[dict, dict, dict], extra: str) -> None:
    sources, settings, _ = inputs
    settings[extra] = "fixture"
    with pytest.raises(aa.AnnotationRefusal, match="settings_shape"):
        am.prepare(sources, settings)


@pytest.mark.parametrize("key,value,status", [
    ("model", "other", "model_mismatch"), ("role", "user", "invalid_response_shape"),
    ("id", None, "missing_message_id"), ("stop_reason", "max_tokens", "truncated"),
    ("stop_reason", "refusal", "provider_refusal"), ("stop_reason", "tool_use", "unsupported_stop_reason"),
    ("stop_reason", "pause_turn", "unsupported_stop_reason"), ("stop_reason", None, "unsupported_stop_reason"),
    ("stop_reason", "new_value", "unsupported_stop_reason"), ("stop_sequence", "x", "unexpected_stop_sequence"),
    ("usage", None, "invalid_or_missing_usage"), ("usage", {}, "invalid_or_missing_usage"),
    ("usage", {"input_tokens": True, "output_tokens": 1}, "invalid_or_missing_usage"),
    ("usage", {"input_tokens": 1, "output_tokens": -1}, "invalid_or_missing_usage"),
    ("usage", {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": "0"},
     "invalid_or_missing_usage"),
    ("content", [], "unsupported_content"),
    ("content", [{"type": "thinking", "thinking": "fixture"}], "unsupported_content"),
    ("content", [{"type": "text", "text": "{}", "citations": [1]}], "unsupported_content"),
    ("content", [{"type": "text", "text": "{}"}] * 2, "unsupported_content"),
    ("content", [{"type": "text", "text": '```json\n{}\n```'}], "invalid_annotation"),
    ("content", [{"type": "text", "text": '{"status":"no_actions","actions":[]}'}], "invalid_annotation"),
])
def test_bad_provider_outcomes_are_visible_not_dropped(
    inputs: tuple[dict, dict, dict], key: str, value: Any, status: str,
) -> None:
    body_change(inputs[2], key, value)
    result = am.replay(*inputs)
    assert len(result["items"]) == 10
    assert result["items"][0]["status"] == status
    assert result["items"][0]["annotation"] is None
    assert result["status_counts"] == {status: 1, "validated_semantics_unverified": 9}
    assert result["response_packet"] is None
    assert result["status"] == "incomplete_attempts_preserved"


@pytest.mark.parametrize("body", ['', '[]', '{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}',
                                   '{"a":"\\ud800"}'])
def test_malformed_raw_response_preserved(inputs: tuple[dict, dict, dict], body: str) -> None:
    inputs[2]["items"][0]["body"] = body
    result = am.replay(*inputs)
    assert result["items"][0]["status"] in {"invalid_response_json", "invalid_response_shape"}
    assert result["items"][0]["attempt"]["body"] == body
    aa.encoded(result)


def test_http_and_transport_errors_are_never_zero_cost_success(inputs: tuple[dict, dict, dict]) -> None:
    _, _, attempts = inputs
    attempts["items"][0].update(http_status=429, body='{"type":"error","error":{"type":"rate_limit_error"}}')
    attempts["items"][1].update(http_status=502, request_id=None, body="gateway unavailable")
    attempts["items"][2].update(http_status=None, request_id=None, body=None, transport_error="timeout")
    result = am.replay(*inputs)
    assert [r["status"] for r in result["items"][:3]] == ["http_error", "http_error", "transport_error"]
    assert all(r["usage"] is None for r in result["items"][:3])
    assert result["cost"]["usd"] is None and result["response_packet"] is None


def test_additive_usage_is_preserved_not_priced(inputs: tuple[dict, dict, dict]) -> None:
    usage = {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 30,
             "cache_creation_input_tokens": 40, "cache_creation": {"ephemeral_1h_input_tokens": 40},
             "new_provider_field": {"units": 12}}
    body_change(inputs[2], "usage", usage)
    result = am.replay(*inputs)
    assert result["items"][0]["usage"] == usage
    assert result["cost"]["status"] == "not_priced"


@pytest.mark.parametrize("mode", ["missing", "duplicate", "extra", "stale", "research", "source_research"])
def test_bad_packet_coverage_or_provenance_refuses(inputs: tuple[dict, dict, dict], mode: str) -> None:
    sources, _, attempts = inputs
    if mode == "missing":
        attempts["items"].pop()
    elif mode == "duplicate":
        attempts["items"].append(copy.deepcopy(attempts["items"][0]))
    elif mode == "extra":
        attempts["items"][0]["source_id"] = "extra"
    elif mode == "stale":
        attempts["items"][0]["request_sha256"] = "0" * 64
    elif mode == "research":
        attempts["artifact_kind"] = "recorded"
    else:
        sources["artifact_kind"] = "recorded"
    with pytest.raises(aa.AnnotationRefusal):
        am.replay(*inputs)


@pytest.mark.parametrize("key,value", [("started_utc", "2026-10-24T00:00:02Z"),
    ("started_utc", "2026-10-24T00:00:00"), ("finished_utc", "bad"), ("http_status", True),
    ("transport_error", "timeout"), ("transport_error", []), ("transport_error", {}), ("body", None)])
def test_malformed_transport_receipts_refuse(inputs: tuple[dict, dict, dict], key: str, value: Any) -> None:
    inputs[2]["items"][0][key] = value
    with pytest.raises(aa.AnnotationRefusal):
        am.replay(*inputs)


def test_wrong_semantics_can_pass_structure_but_fail_key(inputs: tuple[dict, dict, dict]) -> None:
    body = json.loads(inputs[2]["items"][0]["body"])
    annotation = json.loads(body["content"][0]["text"])
    annotation["actions"][0]["stance"] = "recommended"
    body["content"][0]["text"] = json.dumps(annotation)
    inputs[2]["items"][0]["body"] = json.dumps(body)
    result = am.replay(*inputs)
    assert result["status"] == "complete_semantics_unverified"
    scored = aa.score(inputs[0], result["response_packet"], aa.read_json(FIXTURES / "responses.json"))
    assert scored["key_comparison"]["exact_case_matches"] == 9


def test_cli_writes_failure_receipt_exclusively_and_refuses_live_mode(tmp_path: Path,
                                                                  inputs: tuple[dict, dict, dict]) -> None:
    attempts = tmp_path / "attempts.json"
    body_change(inputs[2], "stop_reason", "max_tokens")
    attempts.write_text(json.dumps(inputs[2]))
    out = tmp_path / "action_annotations.json"
    command = [sys.executable, "-m", "scripts.action_annotation_messages", "replay", "--sources",
               str(FIXTURES / "sources.json"), "--settings", str(FIXTURES / "messages_settings.json"),
               "--attempts", str(attempts), "--out", str(out)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 1, first.stdout + first.stderr
    original = out.read_bytes()
    assert json.loads(original)["status_counts"]["truncated"] == 1
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert out.read_bytes() == original
    assert subprocess.run(command + ["--live"], capture_output=True).returncode == 2
    command[-1] = str(tmp_path / "batch_summary.json")
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert not (tmp_path / "batch_summary.json").exists()
