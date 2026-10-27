"""Single-attempt Messages transport primitive; no CLI, campaign or budget admission.

Only a future reviewed CI caller may supply a real transport. Tests inject a fake
connection. Receipts never authorize a reservation release, even after HTTP 200.
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable

from scripts import action_annotations as aa

MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 120
STRUCTURED_FORMAT = 'patientwords.action-quotes-json-schema/1'
QUOTE_SCHEMA = aa.CONTRACT / 'annotation_quotes.v1.schema.json'
QUOTE_SCHEMA_SHA256 = '1dd60212f4c5d96349425090894270e2a8dc08430e6bf285226ca3012047ccc0'


@dataclass(frozen=True)
class Reply:
    """Raw bytes, including a bounded partial body when reading failed."""

    http_status: int | None
    request_id: str | None
    body: bytes
    complete: bool
    error: str | None


def validate_reply(reply: Reply) -> None:
    """Validate the bounded raw-reply contract without decoding or pricing it."""
    if not isinstance(reply, Reply) or type(reply.body) is not bytes:
        raise aa.AnnotationRefusal("invalid_transport_reply")
    if reply.http_status is not None and (type(reply.http_status) is not int or not 100 <= reply.http_status <= 599):
        raise aa.AnnotationRefusal("invalid_transport_reply")
    if reply.request_id is not None and (not isinstance(reply.request_id, str) or not reply.request_id.strip()):
        raise aa.AnnotationRefusal("invalid_transport_reply")
    if reply.request_id is not None:
        try:
            reply.request_id.encode("utf-8")
        except UnicodeError as exc:
            raise aa.AnnotationRefusal("invalid_transport_reply") from exc
    if type(reply.complete) is not bool or (reply.error is not None and (
            not isinstance(reply.error, str) or reply.error not in {
                "timeout", "connection_error", "response_byte_limit", "incomplete_response"})):
        raise aa.AnnotationRefusal("invalid_transport_reply")
    if reply.complete != (reply.error is None) or (reply.complete and reply.http_status is None):
        raise aa.AnnotationRefusal("invalid_transport_reply")
    if len(reply.body) > MAX_BODY_BYTES:
        raise aa.AnnotationRefusal("invalid_transport_reply")


def _structured_format() -> dict[str, Any]:
    """One reviewed schema, unchanged: no arbitrary schemas or lossy SDK rewriting."""
    raw = QUOTE_SCHEMA.read_bytes()
    if aa.digest(raw) != QUOTE_SCHEMA_SHA256:
        raise aa.AnnotationRefusal('structured_schema_hash_mismatch')
    return {'type': 'json_schema', 'schema': json.loads(raw)}


def prepare_wire(system: str, text: str, *, output_format: str | None = None) -> dict[str, Any]:
    """Build legacy or explicit structured-quote wire bytes; no execution admission."""
    if output_format not in (None, STRUCTURED_FORMAT):
        raise aa.AnnotationRefusal('unsupported_output_format')
    for value in (system, text):
        if not isinstance(value, str) or not value.strip():
            raise aa.AnnotationRefusal("request_text_required")
    wire = {"method": "POST", "path": "/v1/messages", "api_version": "2026-10-21",
            "body": {"model": "claude-haiku-5-5", "max_tokens": 8192, "stream": False,
                     "thinking": {"type": "disabled"}, "output_config": {"effort": "medium"},
                     "system": system, "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}]}}
    if output_format == STRUCTURED_FORMAT:
        wire['body']['output_config']['format'] = _structured_format()
    _wire_bytes(wire)
    return wire


def _wire_bytes(wire: Any) -> bytes:
    """Reject hidden tools, alternate destinations and unspecified model settings."""
    try:
        body = wire["body"]
        text = body["messages"][0]["content"][0]["text"]
        system = body["system"]
        expected = {"method": "POST", "path": "/v1/messages", "api_version": "2026-10-21",
                    "body": {"model": "claude-haiku-5-5", "max_tokens": 8192, "stream": False,
                             "thinking": {"type": "disabled"}, "output_config": {"effort": "medium"},
                             "system": system,
                             "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}]}}
        if 'format' in body.get('output_config', {}):
            expected['body']['output_config']['format'] = _structured_format()
        if not all(isinstance(v, str) and v.strip() for v in (text, system)):
            raise ValueError
        # Compare canonical bytes, not Python equality (False == 0, 8192 == 8192.0).
        if aa.encoded(wire) != aa.encoded(expected):
            raise ValueError
        payload = aa.encoded(body)
        if len(payload) > MAX_REQUEST_BYTES:
            raise aa.AnnotationRefusal("request_byte_limit")
        return payload
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError) as exc:
        raise aa.AnnotationRefusal("unsupported_request_profile") from exc


class AnthropicTransport:
    """Fixed HTTPS endpoint, one POST, no redirect or SDK retry mechanism.

    Construction/calling does NOT enforce study approval or budget admission.
    Never use locally; there is deliberately no CLI or environment-key lookup.
    Socket timeout is per operation; a future CI job must enforce a total deadline.
    """

    def __init__(self, api_key: str) -> None:
        if not isinstance(api_key, str) or not api_key or any(ord(c) < 33 or ord(c) > 126 for c in api_key):
            raise aa.AnnotationRefusal("invalid_credential")
        self._api_key = api_key

    def __call__(self, wire: dict[str, Any]) -> Reply:
        body = _wire_bytes(wire)
        return self._post("/v1/messages", wire["api_version"], body)

    def count(self, wire: dict[str, Any]) -> Reply:
        """One free count request for the same inputs; no generation or retries."""
        _wire_bytes(wire)
        body = {k: wire["body"][k] for k in ("model", "system", "messages", "thinking")}
        if 'format' in wire['body']['output_config']:
            # Count the very same format instructions as generation. A count error
            # is a failure, never permission to strip the schema and retry.
            body['output_config'] = wire['body']['output_config']
        return self._post("/v1/messages/count_tokens", wire["api_version"], aa.encoded(body))

    def _post(self, path: str, version: str, body: bytes) -> Reply:
        connection = http.client.HTTPSConnection("api.anthropic.com", timeout=TIMEOUT_SECONDS)
        status, request_id = None, None
        raw = b""
        try:
            connection.request("POST", path, body=body, headers={
                "Authorization": "Bearer " + self._api_key, "anthropic-version": version,
                "Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            status, request_id = response.status, response.getheader("request-id")
            # read1 returns buffered bytes before waiting for more. read(size) can
            # consume a prefix internally and lose it when that same read times out.
            while len(raw) <= MAX_BODY_BYTES:
                part = response.read1(min(65536, MAX_BODY_BYTES + 1 - len(raw)))
                if not part:
                    if response.length not in (None, 0):
                        return Reply(status, request_id, raw, False, "incomplete_response")
                    return Reply(status, request_id, raw, True, None)
                raw += part
            return Reply(status, request_id, raw[:MAX_BODY_BYTES], False, "response_byte_limit")
        except http.client.IncompleteRead as exc:
            raw = (raw + exc.partial)[:MAX_BODY_BYTES]
            return Reply(status, request_id, raw, False, "incomplete_response")
        except TimeoutError:
            return Reply(status, request_id, raw, False, "timeout")
        except (OSError, http.client.HTTPException):
            # Exception text can contain headers/credentials: never persist it.
            return Reply(status, request_id, raw, False, "connection_error")
        finally:
            with suppress(OSError):
                connection.close()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_dir(path.parent)


def capture_attempt(wire: dict[str, Any], *, source_id: str, source_sha256: str,
                    run_root: Path, send: Callable[[dict[str, Any]], Reply]) -> dict[str, Any]:
    """Capture one attempt per request hash in a new child directory of run_root.

    The caller owns the immutable campaign/root, admission, source/holdout checks,
    reservation and persistence beyond the runner. Reusing another root is NOT an
    idempotency mechanism. A start without a result is unknown charge, never retry.
    """
    _wire_bytes(wire)
    if not isinstance(source_id, str) or not source_id.strip():
        raise aa.AnnotationRefusal("source_id_required")
    if not isinstance(source_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
        raise aa.AnnotationRefusal("source_hash_required")
    request_bytes = aa.encoded(wire)
    request_hash = aa.digest(request_bytes)
    root = run_root.resolve(strict=True)
    if (not root.is_dir() or root.name != "action_annotation_attempts"
            or root.is_relative_to(aa.ROOT.resolve())
            or any(part in root.parts for part in ("trace_out", "pilot", ".git"))):
        raise aa.AnnotationRefusal("attempt_root_not_allowed")
    attempt_dir = root / request_hash
    # mkdir is the exclusive claim, including two processes and interrupted starts.
    try:
        attempt_dir.mkdir()
    except FileExistsError as exc:
        raise aa.AnnotationRefusal("attempt_already_claimed_no_retry") from exc
    _sync_dir(root)
    start = {"schema_version": "patientwords.action-attempt-start/1", "source_id": source_id,
             "source_sha256": source_sha256, "request_sha256": request_hash, "started_utc": _utc(),
             "status": "attempt_claimed_charge_unknown", "cost_usd": None, "reservation_release_allowed": False,
             "implementation_sha256": aa.digest(Path(__file__).read_bytes()),
             "request_file": "request.json", "raw_body_file": "response.bin"}
    # A write/sync failure here prevents the call; never overwrite or resume it.
    _write(attempt_dir / "request.json", request_bytes)
    _write(attempt_dir / "start.json", aa.encoded(start))
    before = time.monotonic()
    try:
        reply = send(json.loads(request_bytes))  # Caller mutation cannot change the recorded request.
        validate_reply(reply)
        _write(attempt_dir / "response.bin", reply.body)
        result = {**start, "schema_version": "patientwords.action-attempt-result/1",
                  "finished_utc": _utc(), "elapsed_seconds": time.monotonic() - before,
                  "status": "http_response_uninterpreted" if reply.complete else "transport_incomplete",
                  "http_status": reply.http_status, "request_id": reply.request_id,
                  "body_complete": reply.complete, "transport_error": reply.error,
                  "raw_body_sha256": aa.digest(reply.body), "raw_body_bytes": len(reply.body)}
        _write(attempt_dir / "result.json", aa.encoded(result))
        return result
    except BaseException:
        # No fallback or retry. An interrupted process may leave only the durable
        # start; the future reconciler must hold that reservation until reconciled.
        raise
