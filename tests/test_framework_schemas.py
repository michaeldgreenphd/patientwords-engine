"""The framework's data contracts (docs/framework_design.md): the transcript
import schema, its synthetic example, and the framing-dimensions registry stay
consistent with each other. A minimal validator for the JSON Schema subset the
schema uses, so the suite needs no jsonschema dependency."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "docs" / "framework"
SCHEMA = FRAMEWORK / "transcript.schema.json"
EXAMPLE = FRAMEWORK / "example_transcript.jsonl"
DIMENSIONS = FRAMEWORK / "framing_dimensions.draft.json"

_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "null": type(None),
          "boolean": bool}


def validate(instance, schema: dict, path: str = "$") -> list[str]:
    """Problems found in `instance` against `schema`, for the keywords the
    transcript schema uses: type, enum, required, properties,
    additionalProperties, items, minItems, minLength, minimum, maximum, pattern."""
    problems: list[str] = []
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
    return problems


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dimensions() -> dict:
    return json.loads(DIMENSIONS.read_text(encoding="utf-8"))


def _examples() -> list[dict]:
    return [json.loads(line) for line in EXAMPLE.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_example_transcripts_validate(schema):
    examples = _examples()
    assert examples, "the example file must hold at least one record"
    for record in examples:
        assert validate(record, schema) == []


def test_validator_catches_each_keyword(schema):
    """The home-grown validator must refuse what the schema refuses, or the
    example test proves nothing."""
    base = _examples()[0]
    broken = json.loads(json.dumps(base))
    broken["deidentification"]["status"] = "identified"                 # not in the enum, by design
    assert any("not in" in p for p in validate(broken, schema))
    broken = json.loads(json.dumps(base))
    del broken["provenance"]["text_sha256"]                            # required
    assert any("missing 'text_sha256'" in p for p in validate(broken, schema))
    broken = json.loads(json.dumps(base))
    broken["patient_name"] = "x"                                       # additionalProperties false at the top
    assert any("unexpected key" in p for p in validate(broken, schema))
    broken = json.loads(json.dumps(base))
    broken["turns"] = []                                               # minItems
    assert any("fewer than" in p for p in validate(broken, schema))
    broken = json.loads(json.dumps(base))
    broken["turns"][0]["turn_id"] = "1"                                # type
    assert any("expected ['integer']" in p for p in validate(broken, schema))
    broken = json.loads(json.dumps(base))
    broken["provenance"]["text_sha256"] = "abc"                        # pattern
    assert any("does not match" in p for p in validate(broken, schema))
    broken = json.loads(json.dumps(base))
    broken["annotations"]["framing"][0]["confidence"] = 1.5            # maximum
    assert any("above 1" in p for p in validate(broken, schema))


def test_identified_material_cannot_validate(schema):
    status = schema["properties"]["deidentification"]["properties"]["status"]
    assert "identified" not in status["enum"]
    assert set(status["enum"]) == {"deidentified", "synthetic"}


def test_framing_dimensions_registry_is_consistent(dimensions):
    dims = dimensions["dimensions"]
    probes = dimensions["probes"]
    levels = set(dimensions["requires_levels"])
    dim_ids = [d["id"] for d in dims]
    probe_ids = [p["id"] for p in probes]
    assert len(dim_ids) == len(set(dim_ids)), "dimension ids must be unique"
    assert len(probe_ids) == len(set(probe_ids)), "probe ids must be unique"
    for d in dims:
        for key in ("id", "name", "definition", "values", "detection", "counterfactual", "probes", "status"):
            assert key in d, f"dimension {d.get('id')!r} lacks {key!r}"
        assert d["values"] and len(set(d["values"])) == len(d["values"]), d["id"]
        assert set(d["detection"]["methods"]) <= {"rule", "judge", "human"}, d["id"]
        assert set(d["counterfactual"]["rewrite_to"]) <= set(d["values"]), d["id"]
        unknown = set(d["probes"]) - set(probe_ids)
        assert not unknown, f"dimension {d['id']!r} names unknown probes {sorted(unknown)}"
    for p in probes:
        for key in ("id", "name", "requires", "implementation", "output", "status"):
            assert key in p, f"probe {p.get('id')!r} lacks {key!r}"
        assert p["requires"] in levels, f"probe {p['id']!r} requires unknown level {p['requires']!r}"


def test_example_annotations_use_declared_dimensions(dimensions):
    by_id = {d["id"]: d for d in dimensions["dimensions"]}
    for record in _examples():
        for ann in record.get("annotations", {}).get("framing", []):
            assert ann["dimension_id"] in by_id, ann
            assert ann["value"] in by_id[ann["dimension_id"]]["values"], ann
            turn_ids = {t["turn_id"] for t in record["turns"]}
            assert ann["turn_id"] in turn_ids, ann
