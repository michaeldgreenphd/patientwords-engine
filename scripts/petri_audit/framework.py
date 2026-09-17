"""Framework contracts shared by the transcript importer, the Petri adapter, the
judge runner and the tests: the minimal JSON Schema validator the framework
files are written against, canonical JSON and digests, and the one prompt
rendering implementation (docs/framework_design.md sections 3.2 to 3.4;
docs/petri_integration_design.md section 8).

These helpers lived in tests/test_framework_schemas.py until 2026-09-16; they
moved here so an adapter can import them without importing a test file, which
is how a second rendering implementation would otherwise start. The test
modules import them from here.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_DIR = ROOT / "docs" / "framework"
TRANSCRIPT_SCHEMA = FRAMEWORK_DIR / "transcript.schema.json"
FRAMING_REGISTRY = FRAMEWORK_DIR / "framing_dimensions.draft.json"
OUTCOME_REGISTRY = FRAMEWORK_DIR / "outcome_dimensions.draft.json"
SEED_FILE = FRAMEWORK_DIR / "petri_seeds.draft.json"
MANIFEST_SCHEMA = FRAMEWORK_DIR / "petri_run_manifest.schema.json"
ENV_LOCK = FRAMEWORK_DIR / "petri_environment.lock.json"
ADVICE_RUBRIC = ROOT / "data" / "advice_rubric.draft.json"
ADVICE_RUBRIC_REF = ADVICE_RUBRIC.relative_to(ROOT).as_posix()      # the repository-relative form provenance records

_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


# ------------------------------------------------------------------ digests


def canonical_json(obj: Any) -> str:
    """The elicit chain's canonical form (scripts/advice_eval.py canonical_json):
    sorted keys, no whitespace, UTF-8 preserved."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path | str, obj: Any) -> None:
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- validator


def validate(instance: Any, schema: dict | bool, path: str = "$") -> list[str]:
    """Problems found in `instance` against `schema`, for the keywords the
    framework schemas use: type, enum, const, required, properties,
    additionalProperties, items, minItems, minLength, minimum, maximum,
    pattern, if/then/else, and the boolean schemas (`false` under properties
    forbids a key). Deliberately small: every keyword it does not know is a
    keyword the schemas must not rely on."""
    if schema is True:
        return []
    if schema is False:
        return [f"{path}: not allowed here"]
    problems: list[str] = []
    if "const" in schema and instance != schema["const"]:
        return [f"{path}: {instance!r} is not {schema['const']!r}"]
    types = schema.get("type")
    if types is not None:
        allowed = [types] if isinstance(types, str) else types
        ok = any(isinstance(instance, _TYPES[t]) and not (t in ("integer", "number") and isinstance(instance, bool))
                 for t in allowed)
        if not ok:
            return [f"{path}: expected {allowed}, got {type(instance).__name__}"]
    if "enum" in schema and instance not in schema["enum"]:
        problems.append(f"{path}: {instance!r} not in {schema['enum']}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            problems.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            problems.append(f"{path}: {instance!r} does not match {schema['pattern']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            problems.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            problems.append(f"{path}: above {schema['maximum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                problems.append(f"{path}: missing {key!r}")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                problems.extend(validate(value, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                problems.append(f"{path}: unexpected key {key!r}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            problems.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(instance):
                problems.extend(validate(item, schema["items"], f"{path}[{i}]"))
    if "if" in schema:
        if not validate(instance, schema["if"], path):
            if "then" in schema:
                problems.extend(f"{p} (required when {schema['if']})" for p in validate(instance, schema["then"], path))
        elif "else" in schema:
            problems.extend(f"{p} (unless {schema['if']})" for p in validate(instance, schema["else"], path))
    return problems


def inline_refs(schema: Any, root: Any = None) -> Any:
    """Resolve local `#/$defs/...` references by inlining, so the validator
    (which knows no $ref) checks the referenced sub-schemas instead of silently
    passing them. Descriptions beside a $ref are kept; `examples` are not
    schemas and are left alone."""
    root = schema if root is None else root
    if isinstance(schema, dict):
        if "$ref" in schema:
            target = root
            for part in schema["$ref"].lstrip("#/").split("/"):
                target = target[part]
            return {**inline_refs(target, root), **{k: v for k, v in schema.items() if k != "$ref"}}
        return {k: (inline_refs(v, root) if k != "examples" else v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [inline_refs(x, root) for x in schema]
    return schema


def validate_with_refs(instance: Any, schema: dict) -> list[str]:
    return validate(instance, inline_refs(schema))


# ------------------------------------------------------------ prompt rendering

# The placeholders a prompt file may declare: the register prompt's five plus the
# three context placeholders for scopes that show the judge a prior turn or a
# data-supplied context string. One left-to-right pass, so text inserted by one
# placeholder is never re-scanned for another.
_PLACEHOLDER = re.compile(r"\{(values|not_applicable|open|close|turn_text|context_open|context_close|context_text)\}")


def render_prompt(prompt: dict, turn_text: str, context_text: str | None = None) -> str:
    """The canonical rendering a prompt file declares in its `rendering` block:
    value lines in file order, every declared delimiter escaped inside the
    turn and the context, nothing else touched. A file that declares no
    context delimiters renders no context; a file that declares them refuses
    to render without one (the context is never defaulted)."""
    open_, close = prompt["turn_delimiters"]["open"], prompt["turn_delimiters"]["close"]
    delimiters = [open_, close]
    ctx = prompt.get("context_delimiters")
    if ctx:
        delimiters += [ctx["open"], ctx["close"]]

    def escape(text: str) -> str:
        for d in delimiters:
            text = text.replace(d, "\\" + d)
        return text

    fills = {"values": "\n".join(f"{k}: {v}" for k, v in prompt["values"].items()),
             "not_applicable": prompt["not_applicable"]["definition"],
             "open": open_, "close": close, "turn_text": escape(turn_text)}
    if ctx:
        if context_text is None:
            raise ValueError(f"{prompt['dimension_id']}: this prompt requires a context string")
        fills.update({"context_open": ctx["open"], "context_close": ctx["close"], "context_text": escape(context_text)})
    return _PLACEHOLDER.sub(lambda m: fills[m.group(1)], prompt["instructions"])


def render_judge_prompt(prompt: dict, turn_text: str) -> str:
    """The register prompt's rendering: a prompt with no context block."""
    return render_prompt(prompt, turn_text)


def prompt_canonical(prompt: dict) -> str:
    """The prompt file's order-preserving canonical form: its own key order
    with whitespace removed. Not `canonical_json`, which sorts keys: the order
    of `values` is what the judge is sent, so reordering them must change the
    digest."""
    return json.dumps(prompt, sort_keys=False, ensure_ascii=False, separators=(",", ":"))


def load_prompt(ref: str) -> dict:
    return load_json(ROOT / ref)


def prompt_digest(ref: str) -> str:
    """The provenance digest a judge annotation must carry: sha256 of the
    order-preserving canonical form of the dimension's judge_prompt_ref file,
    first 12 hex."""
    return hashlib.sha256(prompt_canonical(load_prompt(ref)).encode("utf-8")).hexdigest()[:12]


def rendered_digest(ref: str, turn_text: str, context_text: str | None = None) -> str:
    """sha256 of the canonical rendering of the referenced prompt over one turn
    (and its context, when the prompt declares one): what a judge annotation's
    rendered_sha256 must equal, recomputed at import."""
    return sha256_text(render_prompt(load_prompt(ref), turn_text, context_text))


# --------------------------------------------------------- transcript checks


def tool_call_problems(record: dict) -> list[str]:
    """The import-time checks for the transcript 0.2 tool fields: every tool
    turn answers a call on an earlier assistant turn, no call is answered
    twice, and call ids are unique within the record."""
    problems: list[str] = []
    calls: dict[str, int] = {}
    for t in record["turns"]:
        for call in t.get("tool_calls") or []:
            if call["call_id"] in calls:
                problems.append(f"turn {t['turn_id']}: duplicate call_id {call['call_id']!r}")
            calls[call["call_id"]] = t["turn_id"]
    answered: set[str] = set()
    order = {t["turn_id"]: i for i, t in enumerate(record["turns"])}
    for t in record["turns"]:
        if t["role"] != "tool":
            continue
        cid = t.get("tool_call_id")
        if cid not in calls:
            problems.append(f"turn {t['turn_id']}: tool_call_id {cid!r} names no tool call in this record")
        elif order[calls[cid]] >= order[t["turn_id"]]:
            problems.append(f"turn {t['turn_id']}: tool_call_id {cid!r} is answered before it is made")
        elif cid in answered:
            problems.append(f"turn {t['turn_id']}: tool_call_id {cid!r} answered twice")
        answered.add(cid)
    return problems
