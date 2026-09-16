"""Transcript 0.2 records from a branch's messages (docs/framework/transcript.schema.json;
design memo section 9). The adapter hands this module plain message dicts so the
record construction, the digests and the checks are testable without Inspect.

A message dict carries: role (user, assistant, system, tool), text, id (the
harness message id or None), tool_calls (assistant only: a list of
{call_id, name, arguments, parse_error}) and tool_call_id (tool only).
"""
from __future__ import annotations

import hashlib
from typing import Any

from .framework import TRANSCRIPT_SCHEMA, canonical_json, load_json, sha256_text, tool_call_problems, validate

SCHEMA_VERSION = "0.2"
ROLES = ("user", "assistant", "system", "tool")


def conversation_id(eval_id: str, sample_uuid: str, branch_id: str) -> str:
    """sha256 of "<eval_id>:<sample_uuid>:<branch_id>": opaque, stable, unique per
    trajectory node, never derived from a person."""
    return sha256_text(f"{eval_id}:{sample_uuid}:{branch_id}")


def turns_digest(turns: list[dict]) -> str:
    return hashlib.sha256(canonical_json(turns).encode("utf-8")).hexdigest()


def build_turns(messages: list[dict]) -> list[dict]:
    """Numbered turns from messages, in order. Assistant turns answer the
    nearest preceding user turn (`reply_to`); tool calls and tool-call ids ride
    on the turns that made or answered them. An unknown role is an error, never
    a silent skip."""
    turns: list[dict] = []
    last_user: int | None = None
    for i, m in enumerate(messages, 1):
        role = m["role"]
        if role not in ROLES:
            raise ValueError(f"message {i}: unknown role {role!r}")
        turn: dict[str, Any] = {"turn_id": i, "role": role, "text": m.get("text") or "",
                                "timestamp_utc": m.get("timestamp_utc"), "attachments_omitted": int(m.get("attachments_omitted") or 0)}
        if role == "user":
            last_user = i
        if role == "assistant":
            if last_user is not None:
                turn["reply_to"] = last_user
            calls = m.get("tool_calls") or []
            if calls:
                turn["tool_calls"] = [{"call_id": c["call_id"], "name": c["name"], "arguments": dict(c.get("arguments") or {}),
                                       "parse_error": c.get("parse_error")} for c in calls]
        if role == "tool":
            turn["tool_call_id"] = m.get("tool_call_id")
        turns.append(turn)
    return turns


def build_record(messages: list[dict], *, conversation_id: str, source_system: str, source_model: str | None,
                 model_version: str | None, captured_utc: str, user_is: str, import_utc: str, importer_sha: str | None,
                 run_manifest_sha256: str | None, run_manifest_ref: str | None, topic: str | None = None) -> dict:
    """One transcript record for one trajectory node: root-to-node path with the
    replayed prefix included. Synthetic by construction (no person's words),
    captured from an API log, with the run manifest referenced by digest."""
    turns = build_turns(messages)
    record = {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "source": {"system": source_system, "product": None, "model": source_model, "model_version": model_version,
                   "capture_method": "api_log", "captured_utc": captured_utc},
        "deidentification": {"status": "synthetic", "method": None, "reviewed_by": None, "reviewed_utc": None},
        "consent": {"basis": None, "reference": None},
        "speaker_roles": {"user_is": user_is},
        "turns": turns,
        "annotations": {"topic": topic, "framing": []},
        "provenance": {"import_utc": import_utc, "importer_sha": importer_sha, "text_sha256": turns_digest(turns),
                       "run_manifest": ({"sha256": run_manifest_sha256, "ref": run_manifest_ref}
                                        if run_manifest_sha256 else None)},
    }
    return record


def bind_manifest(record: dict, manifest_sha256: str, ref: str | None) -> dict:
    """Return the record with its run-manifest reference set (the manifest digest
    exists only after the records do, so the adapter binds in a second pass)."""
    out = dict(record)
    out["provenance"] = {**record["provenance"], "run_manifest": {"sha256": manifest_sha256, "ref": ref}}
    return out


_SCHEMA_CACHE: dict | None = None


def transcript_schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = load_json(TRANSCRIPT_SCHEMA)
    return _SCHEMA_CACHE


def record_problems(record: dict) -> list[str]:
    """Schema problems plus the tool-call pairing checks plus the digest check.
    Empty when the record may be written."""
    problems = validate(record, transcript_schema())
    problems += tool_call_problems(record)
    if record["provenance"]["text_sha256"] != turns_digest(record["turns"]):
        problems.append("text_sha256 does not match the canonical turns")
    for t in record["turns"]:
        if isinstance(t.get("text"), str) and t["text"].startswith("attachment://"):
            problems.append(f"turn {t['turn_id']}: text is an unresolved attachment reference")
    return problems


def assistant_turns(record: dict) -> list[dict]:
    return [t for t in record["turns"] if t["role"] == "assistant"]
