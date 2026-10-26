"""Synthetic single-attempt transport tests; no provider or credential access."""
from __future__ import annotations

import copy
import http.client
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from scripts import action_annotation_transport as at
from scripts import action_annotations as aa


@pytest.fixture
def wire() -> dict[str, Any]:
    return at.prepare_wire("Extract explicit actions as JSON.", "Move object A if condition B holds.")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "action_annotation_attempts"
    path.mkdir()
    return path


class Response:
    def __init__(self, body: bytes = b'{"usage":null}', status: int = 200,
                 fail: BaseException | None = None, declared_extra: int = 0) -> None:
        self.body = body
        self.status = status
        self.length = len(body) + declared_extra
        self.fail = fail

    def getheader(self, name: str) -> str | None:
        return "request_fixture" if name == "request-id" else None

    def read1(self, size: int) -> bytes:
        if not self.body and self.fail:
            raise self.fail
        part, self.body = self.body[:size], self.body[size:]
        self.length -= len(part)
        return part


class Connection:
    def __init__(self, response: Response | http.client.HTTPResponse, fail: BaseException | None = None) -> None:
        self.response = response
        self.fail = fail
        self.calls: list[tuple] = []
        self.closed = False

    def request(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))
        if self.fail:
            raise self.fail

    def getresponse(self) -> Response | http.client.HTTPResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def install(monkeypatch: pytest.MonkeyPatch, connection: Connection) -> list[tuple]:
    constructions: list[tuple] = []

    def factory(*args: Any, **kwargs: Any) -> Connection:
        constructions.append((args, kwargs))
        return connection

    monkeypatch.setattr(at.http.client, "HTTPSConnection", factory)
    return constructions


def capture(wire: dict, root: Path, send: Any) -> dict:
    return at.capture_attempt(wire, source_id="fixture-1", source_sha256=aa.digest(b"fixture"),
                              run_root=root, send=send)


def test_exact_profile_is_bound_and_old_or_extended_settings_refuse(wire: dict) -> None:
    assert wire["body"]["thinking"] == {"type": "disabled"}
    assert wire["body"]["output_config"] == {"effort": "medium"}
    assert wire["api_version"] == "2026-10-21"
    for key, value in [("max_tokens", 8192.0), ("stream", 0), ("model", "other"),
                       ("thinking", {"type": "adaptive"}), ("tools", []), ("temperature", 0),
                       ("output_config", {"effort": "high"}), ("messages", [])]:
        bad = copy.deepcopy(wire)
        bad["body"][key] = value
        with pytest.raises(aa.AnnotationRefusal, match="unsupported_request_profile"):
            at._wire_bytes(bad)
    for key, value in [("path", "https://example.invalid"), ("api_version", "other"), ("method", "GET")]:
        bad = copy.deepcopy(wire)
        bad[key] = value
        with pytest.raises(aa.AnnotationRefusal):
            at._wire_bytes(bad)
    del wire["body"]["thinking"]
    with pytest.raises(aa.AnnotationRefusal):
        at._wire_bytes(wire)


@pytest.mark.parametrize("text", ["", " ", None, "\ud800", "x" * at.MAX_REQUEST_BYTES])
def test_unusable_text_refuses_before_capture(text: Any) -> None:
    with pytest.raises(aa.AnnotationRefusal):
        at.prepare_wire("system", text)


@pytest.mark.parametrize("status", [200, 302, 401, 429, 500, 529])
def test_actual_transport_makes_one_post_never_redirects_or_retries(
    monkeypatch: pytest.MonkeyPatch, wire: dict, root: Path, status: int,
) -> None:
    raw = b'\xff{"duplicate":1,"duplicate":2,"usage":null}'
    conn = Connection(Response(raw, status))
    constructors = install(monkeypatch, conn)
    original = aa.encoded(wire)
    result = capture(wire, root, at.AnthropicTransport("fixture-placeholder"))
    assert constructors == [(("api.anthropic.com",), {"timeout": 120})]
    assert len(conn.calls) == 1 and conn.closed
    args, kwargs = conn.calls[0]
    assert args == ("POST", "/v1/messages")
    assert kwargs["body"] == aa.encoded(wire["body"])
    assert kwargs["headers"]["Authorization"] == "Bearer fixture-placeholder"
    assert kwargs["headers"]["anthropic-version"] == "2026-10-21"
    out = root / aa.digest(original)
    assert (out / "request.json").read_bytes() == original
    assert (out / "response.bin").read_bytes() == raw
    assert result["raw_body_sha256"] == aa.digest(raw)
    assert result["http_status"] == status
    assert result["status"] == "http_response_uninterpreted"
    assert result["cost_usd"] is None and result["reservation_release_allowed"] is False
    assert "fixture-placeholder" not in (out / "result.json").read_text()
    assert "fixture-placeholder" not in (out / "start.json").read_text()


@pytest.mark.parametrize("exc,code", [(TimeoutError("sensitive"), "timeout"),
    (OSError("sensitive"), "connection_error"), (http.client.HTTPException("sensitive"), "connection_error")])
def test_send_failure_preserves_unknown_charge_and_refuses_second_attempt(
    monkeypatch: pytest.MonkeyPatch, wire: dict, root: Path, exc: Exception, code: str,
) -> None:
    conn = Connection(Response(), exc)
    install(monkeypatch, conn)
    sender = at.AnthropicTransport("fixture-placeholder")
    result = capture(wire, root, sender)
    assert result["transport_error"] == code and not result["body_complete"]
    assert result["cost_usd"] is None
    assert "sensitive" not in json.dumps(result)
    with pytest.raises(aa.AnnotationRefusal, match="attempt_already_claimed_no_retry"):
        capture(wire, root, sender)
    assert len(conn.calls) == 1 and conn.closed


@pytest.mark.parametrize("failure,extra,code", [(TimeoutError(), 0, "timeout"),
    (http.client.IncompleteRead(b"tail"), 0, "incomplete_response"), (None, 7, "incomplete_response")])
def test_partial_read_preserves_prefix_and_cannot_become_success(
    monkeypatch: pytest.MonkeyPatch, wire: dict, root: Path, failure: Exception | None, extra: int, code: str,
) -> None:
    conn = Connection(Response(b"prefix", fail=failure, declared_extra=extra))
    install(monkeypatch, conn)
    result = capture(wire, root, at.AnthropicTransport("fixture-placeholder"))
    assert result["transport_error"] == code and result["status"] == "transport_incomplete"
    expected = b"prefixtail" if isinstance(failure, http.client.IncompleteRead) else b"prefix"
    assert (root / result["request_sha256"] / "response.bin").read_bytes() == expected
    assert conn.closed and len(conn.calls) == 1


@pytest.mark.parametrize("framing", ["length", "chunked", "close"])
@pytest.mark.parametrize("ending", ["timeout", "eof", "complete"])
def test_real_http_buffer_retains_received_body(
    monkeypatch: pytest.MonkeyPatch, wire: dict, root: Path, framing: str, ending: str,
) -> None:
    # Preload only a local socket pair: actual HTTPResponse buffering, no provider.
    prefix = b'{"partial":"evidence"}'
    size = len(prefix) if ending == "complete" else 100
    if framing == "length":
        header = f"Content-Length: {size}\r\n".encode()
        payload = prefix
    elif framing == "chunked":
        header = b"Transfer-Encoding: chunked\r\n"
        payload = f"{size:x}\r\n".encode() + prefix
        if ending == "complete":
            payload += b"\r\n0\r\n\r\n"
    else:
        header, payload = b"Connection: close\r\n", prefix
    reader, writer = socket.socketpair()
    with reader, writer:
        reader.settimeout(0.05)
        writer.sendall(b"HTTP/1.1 200 OK\r\nrequest-id: fixture\r\n" + header + b"\r\n" + payload)
        if ending != "timeout":
            writer.shutdown(socket.SHUT_WR)
        with http.client.HTTPResponse(reader) as response:
            response.begin()
            conn = Connection(response)
            install(monkeypatch, conn)
            result = capture(wire, root, at.AnthropicTransport("fixture-placeholder"))
        expected_error = "timeout" if ending == "timeout" else (
            "incomplete_response" if ending == "eof" and framing != "close" else None)
        assert result["transport_error"] == expected_error
        assert result["body_complete"] is (expected_error is None)
        assert (root / result["request_sha256"] / "response.bin").read_bytes() == prefix
        assert result["raw_body_sha256"] == aa.digest(prefix)
        assert result["raw_body_bytes"] == len(prefix)
        assert result["cost_usd"] is None and result["reservation_release_allowed"] is False
        assert conn.closed and len(conn.calls) == 1

def test_body_limit_is_explicit_and_prefix_retained(monkeypatch: pytest.MonkeyPatch, wire: dict, root: Path) -> None:
    monkeypatch.setattr(at, "MAX_BODY_BYTES", 20)
    conn = Connection(Response(b"a" * 21))
    install(monkeypatch, conn)
    result = capture(wire, root, at.AnthropicTransport("fixture-placeholder"))
    assert result["transport_error"] == "response_byte_limit" and result["raw_body_bytes"] == 20
    assert not result["body_complete"] and conn.closed


def test_write_ahead_and_exclusive_claim_stop_recursive_or_resumed_calls(wire: dict, root: Path) -> None:
    calls = []
    request_hash = aa.digest(aa.encoded(wire))

    def send(request: dict) -> at.Reply:
        calls.append(request)
        start = json.loads((root / request_hash / "start.json").read_text())
        assert start["status"] == "attempt_claimed_charge_unknown"
        assert (root / request_hash / "request.json").read_bytes() == aa.encoded(wire)
        with pytest.raises(aa.AnnotationRefusal, match="attempt_already_claimed_no_retry"):
            capture(wire, root, send)
        return at.Reply(200, "fixture", b"{}", True, None)

    capture(wire, root, send)
    assert len(calls) == 1


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), SystemExit(2), RuntimeError("sensitive")])
def test_interruption_leaves_start_no_result_and_no_retry(wire: dict, root: Path, exc: BaseException) -> None:
    calls = []

    def send(request: dict) -> at.Reply:
        calls.append(request)
        raise exc

    with pytest.raises(type(exc)):
        capture(wire, root, send)
    out = root / aa.digest(aa.encoded(wire))
    assert (out / "start.json").exists() and not (out / "result.json").exists()
    with pytest.raises(aa.AnnotationRefusal, match="attempt_already_claimed_no_retry"):
        capture(wire, root, send)
    assert len(calls) == 1


@pytest.mark.parametrize("fail_at", ["request.json", "start.json", "response.bin", "result.json"])
def test_storage_failure_prevents_or_preserves_call_without_retry(
    monkeypatch: pytest.MonkeyPatch, wire: dict, root: Path, fail_at: str,
) -> None:
    original = at._write
    calls = []

    def write(path: Path, raw: bytes) -> None:
        if path.name == fail_at:
            raise OSError("fixture failure")
        original(path, raw)

    def send(request: dict) -> at.Reply:
        calls.append(request)
        return at.Reply(200, "fixture", b"{}", True, None)

    monkeypatch.setattr(at, "_write", write)
    with pytest.raises(OSError):
        capture(wire, root, send)
    assert len(calls) == int(fail_at in {"response.bin", "result.json"})
    with pytest.raises(aa.AnnotationRefusal, match="attempt_already_claimed_no_retry"):
        capture(wire, root, send)


@pytest.mark.parametrize("root_kind", ["wrong_name", "trace_out", "pilot", "repository"])
def test_output_namespace_refusal(wire: dict, root: Path, root_kind: str) -> None:
    if root_kind == "repository":
        target = aa.ROOT
    elif root_kind == "wrong_name":
        target = root.parent
    else:
        target = root.parent / root_kind / "action_annotation_attempts"
        target.mkdir(parents=True)
    with pytest.raises(aa.AnnotationRefusal, match="attempt_root_not_allowed"):
        capture(wire, target, lambda request: pytest.fail("must not send"))


@pytest.mark.parametrize("reply", [None, at.Reply(True, None, b"", True, None),
    at.Reply(200, "", b"", True, None), at.Reply(200, None, "text", True, None),
    at.Reply(None, None, b"", True, None), at.Reply(200, None, b"", False, None),
    at.Reply(200, None, b"", True, "timeout")])
def test_bad_transport_result_never_reports_completion(wire: dict, root: Path, reply: Any) -> None:
    with pytest.raises(aa.AnnotationRefusal, match="invalid_transport_reply"):
        capture(wire, root, lambda request: reply)
    out = root / aa.digest(aa.encoded(wire))
    assert (out / "start.json").exists() and not (out / "result.json").exists()


def test_no_credential_or_network_side_effect_during_import_or_prepare(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("network construction during preparation")
    monkeypatch.setattr(at.http.client, "HTTPSConnection", forbidden)
    assert at.prepare_wire("system", "source")["body"]["stream"] is False
    for key in ("", "token\nheader", None):
        with pytest.raises(aa.AnnotationRefusal, match="invalid_credential"):
            at.AnthropicTransport(key)
