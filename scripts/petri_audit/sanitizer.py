"""Raw-log sanitiser: the allowlist projection of an Inspect `.eval` log that
may enter a public repository (docs/petri_integration_design.md section 9;
allowlist data in data/petri/sanitizer_allowlist.json).

The raw log holds every provider request and response body; Inspect redacts
only `api_key` and `aws_*` arguments, and request bodies, headers, base URLs
and provider extras are logged as sent. So the raw file is never committed:
this module projects it onto the allowlist, counts every key it drops, and
refuses its own output if any forbidden key survives anywhere in it.

Forbidden keys inside provider-filled values. Some values the projection keeps
whole are filled by the model provider's response, whose shape can change on
the server with no package change: a model event's `output` (apart from its
choices' messages, which are projected), every value a projected message
keeps, and a tool event's `arguments` and `internal`. Inside those values a
forbidden key at any depth is dropped and counted in the redaction report's
`forbidden_keys_dropped`, by path with list indices elided. The run that
required this: w2e3 (run 35937014168, 2026-09-24 00:09 UTC) failed at Adapt.
Every Anthropic response in it carried a top-level `diagnostics` field that
the non-beta `Message` type of anthropic 0.105.0 does not declare, and
inspect_ai 0.3.237 records undeclared response fields as
`output.metadata.extra_body`. A forbidden key anywhere else (a key the
allowlist itself keeps, or one in our own harness, seed or task data) still
refuses the whole output: that is a defect on our side, not a provider change.

Operates on the log's JSON form (an `EvalLog` dumped with `mode="json"`), so
it is 3.11-safe and testable without Inspect.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .framework import ROOT, load_json, sha256_text

ALLOWLIST_PATH = ROOT / "data" / "petri" / "sanitizer_allowlist.json"


@dataclass
class RedactionReport:
    fields_removed: int = 0
    fields_hashed: int = 0
    events_dropped_by_type: dict[str, int] = field(default_factory=dict)
    timeline_content_dropped_by_type: dict[str, int] = field(default_factory=dict)
    samples: int = 0
    events_kept: int = 0
    request_bodies_kept: bool = True
    headers_kept: bool = False
    base_urls_kept: bool = False
    # forbidden keys removed from inside provider-filled values, by index-free path; separate from fields_removed,
    # which counts only what the allowlist projection drops, so that count stays comparable across runs
    forbidden_keys_dropped: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """The whole report, as the manifest records it: an event type the
        allowlist does not name is dropped AND counted here by type, so a
        sanitised log with events missing always says which and how many.
        `forbidden_keys_dropped` is always present (empty when nothing was
        dropped), so a manifest that carries it was written by a sanitiser
        that drops rather than refuses inside provider-filled values."""
        return {"fields_removed": self.fields_removed, "fields_hashed": self.fields_hashed,
                "request_bodies_kept": self.request_bodies_kept, "headers_kept": self.headers_kept,
                "base_urls_kept": self.base_urls_kept,
                "events_dropped_by_type": dict(sorted(self.events_dropped_by_type.items())),
                "timeline_content_dropped_by_type": dict(sorted(self.timeline_content_dropped_by_type.items())),
                "samples": self.samples, "events_kept": self.events_kept,
                "forbidden_keys_dropped": dict(sorted(self.forbidden_keys_dropped.items()))}


class SanitiserError(RuntimeError):
    """The projection produced output that still carries a forbidden key."""


def load_allowlist(path: Path | str = ALLOWLIST_PATH) -> dict:
    return load_json(path)


def allowlist_digest(allowlist: dict) -> str:
    import json
    return sha256_text(json.dumps(allowlist, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _project(obj: dict, keys: list[str], report: RedactionReport) -> dict:
    kept = {k: obj[k] for k in keys if k in obj}
    report.fields_removed += len(obj) - len(kept)
    return kept


# Tool-event keys whose values the provider fills (the model's call arguments, a provider-specific payload); the
# model event's `output` and every projected message are the other provider-filled values (module docstring).
PROVIDER_TOOL_EVENT_KEYS = ("arguments", "internal")


def _forbidden(allowlist: dict) -> set[str]:
    return set(allowlist["forbidden_keys"])


def _drop_forbidden(key: str, where: str, report: RedactionReport) -> None:
    path = f"{where}.{key}"
    report.forbidden_keys_dropped[path] = report.forbidden_keys_dropped.get(path, 0) + 1


def _scrub(value: Any, forbidden: set[str], where: str, report: RedactionReport) -> Any:
    """A copy of a provider-filled `value` with every forbidden key removed at
    any depth, each removal counted under its path with list indices elided
    (`$.samples[].events[].output.metadata.extra_body`), so the report says
    where the key sat without growing with the log. Everything else is kept
    exactly, in its original order; the input is not mutated."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in forbidden:
                _drop_forbidden(k, where, report)
                continue
            out[k] = _scrub(v, forbidden, f"{where}.{k}", report)
        return out
    if isinstance(value, list):
        return [_scrub(v, forbidden, f"{where}[]", report) for v in value]
    return value


def _project_config(config: Any, allowlist: dict, report: RedactionReport) -> Any:
    if not isinstance(config, dict):
        return config
    return _project(config, allowlist["config_keys"], report)


def _project_message(message: Any, allowlist: dict, report: RedactionReport, where: str = "$.messages[]") -> Any:
    """A message onto the allowlist's message keys. A message is the unit a
    provider returns, so every value it keeps (content items, tool calls,
    metadata) is scrubbed of forbidden keys; a forbidden key the allowlist
    itself keeps stays, and the backstop refuses it."""
    if not isinstance(message, dict):
        return message
    kept = _project(message, allowlist["message"]["keys"], report)
    forbidden = _forbidden(allowlist)
    return {k: _scrub(v, forbidden, f"{where}.{k}", report) for k, v in kept.items()}


def _project_choice(choice: Any, allowlist: dict, report: RedactionReport, where: str) -> Any:
    """One choice of a model output: its message is projected, every other
    value (stop reason, stop details, logprobs) is provider-filled and
    scrubbed. The shape is the one the projection has always written: a dict
    choice always carries `message`, None when the choice had none."""
    forbidden = _forbidden(allowlist)
    if not isinstance(choice, dict):
        return _scrub(choice, forbidden, where, report)
    rest = {}
    for k, v in choice.items():
        if k in forbidden:
            _drop_forbidden(k, where, report)
        else:
            rest[k] = v if k == "message" else _scrub(v, forbidden, f"{where}.{k}", report)
    return {**rest, "message": _project_message(choice.get("message"), allowlist, report, f"{where}.message")}


def _project_output(output: Any, allowlist: dict, report: RedactionReport, where: str) -> Any:
    """A model event's `output`: Inspect's ModelOutput, which the provider
    module builds from the API response (`metadata` holds whatever response
    fields the SDK does not declare). The choices are projected; every other
    value, and any key the output itself carries, is provider-filled, so a
    forbidden key anywhere in it is dropped and counted rather than refused."""
    forbidden = _forbidden(allowlist)
    if not isinstance(output, dict):
        return _scrub(output, forbidden, where, report)
    out = {}
    for k, v in output.items():
        if k in forbidden:
            _drop_forbidden(k, where, report)
        elif k == "choices" and isinstance(v, list):
            out[k] = [_project_choice(c, allowlist, report, f"{where}.choices[]") for c in v]
        else:
            out[k] = _scrub(v, forbidden, f"{where}.{k}", report)
    return out


def _project_event(event: Any, allowlist: dict, report: RedactionReport, where: str = "$.events[]") -> dict | None:
    """One event onto its type's allowlist; None (and a count) for a type the
    allowlist does not name. Nested events (subtask, tool) recurse; message
    lists and configs recurse into their own projections; provider-filled
    values (a model event's output, a tool event's arguments) are scrubbed."""
    if not isinstance(event, dict):
        return None
    etype = event.get("event")
    if etype not in allowlist["events"]["types_kept"]:
        report.events_dropped_by_type[str(etype)] = report.events_dropped_by_type.get(str(etype), 0) + 1
        return None
    keys = list(allowlist["events"]["keys"]["*"]) + list(allowlist["events"]["keys"].get(etype, []))
    out = _project(event, keys, report)
    if "config" in out:
        out["config"] = _project_config(out["config"], allowlist, report)
    if "input" in out and isinstance(out["input"], list):
        out["input"] = [_project_message(m, allowlist, report, f"{where}.input[]") for m in out["input"]]
    if "output" in out:
        out["output"] = _project_output(out["output"], allowlist, report, f"{where}.output")
    if etype == "tool":
        for k in PROVIDER_TOOL_EVENT_KEYS:
            if k in out:
                out[k] = _scrub(out[k], _forbidden(allowlist), f"{where}.{k}", report)
    if "events" in out and isinstance(out["events"], list):
        out["events"] = [e for e in (_project_event(x, allowlist, report, f"{where}.events[]") for x in out["events"])
                         if e is not None]
    if etype == "anchor" and isinstance(out.get("message"), dict):
        out["message"] = _project_message(out["message"], allowlist, report, f"{where}.message")
    return out


def _project_timeline_node(node: Any, allowlist: dict, report: RedactionReport, where: str = "$.root") -> Any:
    """Timeline spans carry events inline as {type: event, event: {...}}. The
    span itself is projected onto the allowlist's `timeline.node_keys`, and a
    content item of a type the allowlist does not name is dropped and counted
    (Codex round 8: nodes used to be copied whole, so an unreviewed node
    field or content type reached the public export)."""
    if not isinstance(node, dict):
        return node
    out = _project(node, allowlist["timeline"]["node_keys"], report)
    kept_types = allowlist["timeline"]["content_types_kept"]
    if isinstance(out.get("content"), list):
        projected = []
        for item in out["content"]:
            itype = item.get("type") if isinstance(item, dict) else None
            if itype not in kept_types:
                report.timeline_content_dropped_by_type[str(itype)] = report.timeline_content_dropped_by_type.get(str(itype), 0) + 1
                continue
            if itype == "event":
                ev = _project_event(item.get("event"), allowlist, report, f"{where}.content[].event")
                if ev is not None:
                    projected.append({"type": "event", "event": ev})
                    report.fields_removed += len(item) - 2
            else:
                projected.append(_project_timeline_node(item, allowlist, report, f"{where}.content[]"))
        out["content"] = projected
    if isinstance(out.get("branches"), list):
        out["branches"] = [_project_timeline_node(b, allowlist, report, f"{where}.branches[]") for b in out["branches"]]
    return out


def _project_sample(sample: dict, allowlist: dict, report: RedactionReport, where: str = "$.samples[]") -> dict:
    out = _project(sample, allowlist["sample"]["keys"], report)
    if isinstance(out.get("messages"), list):
        out["messages"] = [_project_message(m, allowlist, report, f"{where}.messages[]") for m in out["messages"]]
    if isinstance(out.get("events"), list):
        kept = [e for e in (_project_event(x, allowlist, report, f"{where}.events[]") for x in out["events"])
                if e is not None]
        report.events_kept += len(kept)
        out["events"] = kept
    if isinstance(out.get("timelines"), list):
        out["timelines"] = [
            ({**t, "root": _project_timeline_node(t.get("root"), allowlist, report, f"{where}.timelines[].root")}
             if isinstance(t, dict) else t)
            for t in out["timelines"]]
    report.samples += 1
    return out


def _project_eval(spec: dict, allowlist: dict, report: RedactionReport) -> dict:
    out = _project(spec, allowlist["eval"]["keys"], report)
    roles = out.get("model_roles")
    if isinstance(roles, dict):
        out["model_roles"] = {
            role: (_project(cfg, allowlist["eval"]["model_roles_keys"], report) if isinstance(cfg, dict) else cfg)
            for role, cfg in roles.items()}
        for cfg in out["model_roles"].values():
            if isinstance(cfg, dict) and "config" in cfg:
                cfg["config"] = _project_config(cfg["config"], allowlist, report)
    if "model_generate_config" in out:
        out["model_generate_config"] = _project_config(out["model_generate_config"], allowlist, report)
    return out


def forbidden_key_paths(obj: Any, forbidden: set[str], path: str = "$") -> list[str]:
    """Every path at which a forbidden key occurs anywhere in `obj`."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in forbidden:
                hits.append(f"{path}.{k}")
            hits.extend(forbidden_key_paths(v, forbidden, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(forbidden_key_paths(v, forbidden, f"{path}[{i}]"))
    return hits


def sanitise_log(log_json: dict, allowlist: dict | None = None) -> tuple[dict, RedactionReport]:
    """The published projection of a raw log plus its redaction report. Raises
    SanitiserError when a forbidden key survives, so a defective allowlist can
    never publish. Forbidden keys inside provider-filled values were already
    dropped and counted during the projection (`forbidden_keys_dropped`); this
    check is the backstop for every other place, and it covers the whole
    output, scrubbed values included."""
    allowlist = allowlist or load_allowlist()
    report = RedactionReport()
    out: dict[str, Any] = {
        "sanitiser": {"version": allowlist["version"], "allowlist_sha256": allowlist_digest(allowlist)},
        "eval": _project_eval(log_json.get("eval") or {}, allowlist, report),
        "samples": [_project_sample(s, allowlist, report) for s in (log_json.get("samples") or [])],
        "stats": log_json.get("stats"),
        "status": log_json.get("status"),
    }
    hits = forbidden_key_paths(out, set(allowlist["forbidden_keys"]))
    if hits:
        raise SanitiserError(f"forbidden keys survived sanitisation: {hits[:10]}")
    return out, report
