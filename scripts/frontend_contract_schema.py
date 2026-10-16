"""Small stdlib schema adapter used by the frontend export gate.

Artifact fields live exclusively in the JSON schema supplied by the caller.
This module handles structural validation only; joins, mirrors, provenance and
other scientific semantics remain with their existing validators.
"""
from __future__ import annotations

from typing import Callable


def _is(value: object, kinds: type | tuple[type, ...]) -> bool:
    """Keep bool out of numeric kinds and preserve the gate's lexical integers."""
    if kinds is bool:
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    return isinstance(value, kinds)


def check_schema_subset(report_error: Callable[[str, str, str], None], artifact: str,
                        value: object, schema: dict,
                        *, export_gate: bool = False) -> None:
    """Validate the deliberately small schema dialect used by the export gate.

    Supports local $ref, type, required, properties, items (single schema), and
    additionalProperties (boolean or schema). x-export-required is an annotation
    that tightens only the existing export gate, preserving legacy HTTP readers.
    All other assertion keywords fail closed, including in unused definitions;
    this is not a general JSON Schema implementation. The HTTP harness uses a
    full draft-07 validator against the same authority and fetched JSON bytes.
    As before, the export gate requires integer JSON tokens: Python float 1.0
    is rejected for integer fields even though draft-07 treats it as an integer.
    """
    allowed = {"$schema", "$id", "title", "description", "definitions", "$ref", "type",
               "required", "properties", "items", "additionalProperties", "x-export-required"}
    types = {"object": dict, "array": list, "string": str, "integer": int,
             "number": (int, float), "boolean": bool, "null": type(None)}

    def audit(node: dict) -> None:
        unsupported = set(node) - allowed
        if unsupported:
            raise ValueError(f"unsupported schema keywords: {sorted(unsupported)}")
        if "$ref" in node and set(node) != {"$ref"}:
            raise ValueError("$ref siblings are not supported by the export-gate adapter")
        kinds = node.get("type", [])
        for kind in kinds if isinstance(kinds, list) else [kinds]:
            if kind not in types:
                raise ValueError(f"unsupported schema type: {kind}")
        for group in ("definitions", "properties"):
            for child in node.get(group, {}).values():
                audit(child)
        if isinstance(node.get("items"), bool):
            raise ValueError("items must be a single object schema")
        for key in ("items", "additionalProperties"):
            if key in node and not isinstance(node[key], bool):
                if not isinstance(node[key], dict):
                    raise ValueError(f"{key} must be a single schema")
                audit(node[key])
        if "$ref" in node and not node["$ref"].startswith("#/"):
            raise ValueError("only local JSON Pointer references are supported")

    def visit(obj: object, node: dict, path: str) -> None:
        if "$ref" in node:
            target = schema
            for part in node["$ref"][2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            visit(obj, target, path)
            return
        kinds = node.get("type", [])
        kinds = kinds if isinstance(kinds, list) else [kinds]
        if kinds and not any(_is(obj, types[kind]) for kind in kinds):
            report_error(artifact, path, f"wrong type {type(obj).__name__}; expected {' or '.join(kinds)}")
            return
        if isinstance(obj, dict):
            required = node.get("required", []) + (node.get("x-export-required", []) if export_gate else [])
            for key in required:
                if key not in obj:
                    report_error(artifact, f"{path}.{key}", "missing required key")
            props = node.get("properties", {})
            extra = node.get("additionalProperties", True)
            for key, child in obj.items():
                if key in props:
                    visit(child, props[key], f"{path}.{key}")
                elif isinstance(extra, dict):
                    visit(child, extra, f"{path}[{key}]")
                elif extra is False:
                    report_error(artifact, f"{path}.{key}", "additional property is not allowed")
        if isinstance(obj, list) and "items" in node:
            for i, child in enumerate(obj):
                visit(child, node["items"], f"{path}[{i}]")

    audit(schema)
    visit(value, schema, "$")

