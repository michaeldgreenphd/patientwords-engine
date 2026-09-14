"""The framework's data contracts (docs/framework_design.md): the transcript
import schema, its synthetic example, and the framing-dimensions registry stay
consistent with each other. A minimal validator for the JSON Schema subset the
schema uses, so the suite needs no jsonschema dependency."""
from __future__ import annotations

import hashlib
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
    transcript schema uses: type, enum, const, required, properties,
    additionalProperties, items, minItems, minLength, minimum, maximum, pattern,
    and if/then."""
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
    if "if" in schema and "then" in schema and not validate(instance, schema["if"], path):
        problems.extend(f"{p} (required when {schema['if']})" for p in validate(instance, schema["then"], path))
    return problems


def canonical_json(obj) -> str:
    """The elicit chain's canonical form (scripts/advice_eval.py canonical_json)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def semantic_problems(record: dict, dimensions: dict) -> list[str]:
    """The import-time checks the schema cannot express (docs/framework_design.md
    section 3.3): turn ids unique, every annotation on exactly one user turn
    with a declared dimension and value, and the provenance digest matching
    the turns. What a real importer must refuse a record for."""
    problems = []
    ids = [t["turn_id"] for t in record["turns"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate turn_id")
    roles = {t["turn_id"]: t["role"] for t in record["turns"]}
    by_id = {d["id"]: d for d in dimensions["dimensions"]}
    for ann in record.get("annotations", {}).get("framing", []):
        dim = by_id.get(ann["dimension_id"])
        if dim is None:
            problems.append(f"annotation names unknown dimension {ann['dimension_id']!r}")
        elif ann["value"] not in dim["values"]:
            problems.append(f"annotation value {ann['value']!r} not declared for {ann['dimension_id']!r}")
        if roles.get(ann["turn_id"]) != "user":
            problems.append(f"annotation turn {ann['turn_id']} is not a single user turn")
    digest = hashlib.sha256(canonical_json(record["turns"]).encode("utf-8")).hexdigest()
    if record["provenance"]["text_sha256"] != digest:
        problems.append("text_sha256 does not match the canonical turns")
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
    broken = json.loads(json.dumps(base))
    broken["deidentification"]["status"] = "deidentified"              # if/then: review metadata required
    assert any("method" in p and "required when" in p for p in validate(broken, schema))
    assert any("reviewed_by" in p for p in validate(broken, schema))
    broken["deidentification"].update({"method": "tool-x", "reviewed_by": "privacy officer",
                                       "reviewed_utc": "2026-09-14T00:00:00Z"})
    assert validate(broken, schema) == []


def test_identified_material_cannot_validate(schema):
    status = schema["properties"]["deidentification"]["properties"]["status"]
    assert "identified" not in status["enum"]
    assert set(status["enum"]) == {"deidentified", "synthetic"}


def test_example_passes_the_import_time_semantic_checks(dimensions):
    for record in _examples():
        assert semantic_problems(record, dimensions) == []


def test_semantic_checks_refuse_each_case(dimensions):
    base = _examples()[0]
    broken = json.loads(json.dumps(base))
    broken["turns"].append(dict(broken["turns"][0]))                    # duplicate turn_id
    assert any("duplicate turn_id" in p for p in semantic_problems(broken, dimensions))
    broken = json.loads(json.dumps(base))
    broken["annotations"]["framing"][0]["turn_id"] = 2                  # the assistant turn
    assert any("not a single user turn" in p for p in semantic_problems(broken, dimensions))
    broken = json.loads(json.dumps(base))
    broken["annotations"]["framing"][0]["dimension_id"] = "nope"
    assert any("unknown dimension" in p for p in semantic_problems(broken, dimensions))
    broken = json.loads(json.dumps(base))
    broken["annotations"]["framing"][0]["value"] = "nope"
    assert any("not declared" in p for p in semantic_problems(broken, dimensions))
    broken = json.loads(json.dumps(base))
    broken["turns"][0]["text"] = "edited after import"
    assert any("text_sha256" in p for p in semantic_problems(broken, dimensions))


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
        cf = d["counterfactual"]
        contrast_ids = [c["id"] for c in cf["contrasts"]]
        assert len(contrast_ids) == len(set(contrast_ids)), f"{d['id']}: contrast ids must be unique"
        for c in cf["contrasts"]:
            assert c["from"] in d["values"] and c["to"] in d["values"] and c["from"] != c["to"], (d["id"], c)
        assert set(cf.get("no_contrast", [])) <= set(d["values"]), d["id"]
        sources = {c["from"] for c in cf["contrasts"]} | set(cf.get("no_contrast", []))
        assert sources == set(d["values"]), f"{d['id']}: every value needs a contrast or a no_contrast entry"
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
