"""The framework's data contracts (docs/framework_design.md): the transcript
import schema, its synthetic example, and the framing-dimensions registry stay
consistent with each other. A minimal validator for the JSON Schema subset the
schema uses, so the suite needs no jsonschema dependency."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
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
    order = {t["turn_id"]: i for i, t in enumerate(record["turns"])}
    for t in record["turns"]:
        if t.get("reply_to") is not None:
            if t["role"] != "assistant":
                problems.append(f"turn {t['turn_id']}: reply_to on a non-assistant turn")
            elif roles.get(t["reply_to"]) != "user" or order.get(t["reply_to"], 10**9) >= order[t["turn_id"]]:
                problems.append(f"turn {t['turn_id']}: reply_to {t['reply_to']} is not an earlier user turn")
    seen_keys = set()
    for ann in record.get("annotations", {}).get("framing", []):
        key = (ann["turn_id"], ann["dimension_id"])
        if key in seen_keys:
            problems.append(f"duplicate annotation for turn {key[0]} on dimension {key[1]!r}")
        seen_keys.add(key)
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
    stamps = [("source.captured_utc", record["source"].get("captured_utc")),
              ("deidentification.reviewed_utc", record["deidentification"].get("reviewed_utc")),
              ("provenance.import_utc", record["provenance"].get("import_utc"))]
    stamps += [(f"turns[{i}].timestamp_utc", t.get("timestamp_utc")) for i, t in enumerate(record["turns"])]
    for name, stamp in stamps:
        if stamp is None:
            continue
        try:
            datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            problems.append(f"{name}: {stamp!r} is not a real UTC instant")
    return problems


def reply_pairs(record: dict) -> tuple[list[tuple[int, int]], list[int]]:
    """(user turn, assistant turn) pairs and the assistant turns that cannot be
    paired: an explicit reply_to wins; otherwise the immediately preceding turn,
    only if it is a user turn (docs/framework_design.md section 3.3)."""
    turns = record["turns"]
    pairs, unpaired = [], []
    for i, t in enumerate(turns):
        if t["role"] != "assistant":
            continue
        if t.get("reply_to") is not None:
            pairs.append((t["reply_to"], t["turn_id"]))
        elif i > 0 and turns[i - 1]["role"] == "user":
            pairs.append((turns[i - 1]["turn_id"], t["turn_id"]))
        else:
            unpaired.append(t["turn_id"])
    return pairs, unpaired


def counterfactual_ineligibility(record: dict, assistant_turn_id: int | None = None) -> str | None:
    """Why a record, or one assistant turn of it, may not enter the counterfactual
    step (docs/framework_design.md sections 3.1 and 3.3), or None when it may.
    The observational path is unaffected."""
    if not record["source"].get("model"):
        return "model_unidentified: source.model is null, so re-eliciting from the same model is impossible"
    if assistant_turn_id is None:
        return None
    pairs, unpaired = reply_pairs(record)
    if assistant_turn_id in unpaired:
        return f"unpaired_reply: assistant turn {assistant_turn_id} answers no identifiable user turn"
    by_id = {t["turn_id"]: t for t in record["turns"]}
    user_id = dict((a, u) for u, a in pairs)[assistant_turn_id]
    if by_id[user_id]["attachments_omitted"] > 0:
        return f"attachments_omitted: user turn {user_id} had non-text content the rewrite cannot reproduce"
    if by_id[assistant_turn_id]["attachments_omitted"] > 0:
        return f"incomplete_reply: assistant turn {assistant_turn_id} had non-text content the judge does not see"
    return None


def file_problems(records: list[dict]) -> list[str]:
    """Across one input file: a repeated conversation_id with the same digest is
    an idempotent duplicate (reported), with a different digest a conflict
    (refused). The importer runs the same check against its existing store."""
    seen: dict[str, str] = {}
    problems = []
    for r in records:
        cid, digest = r["conversation_id"], r["provenance"]["text_sha256"]
        if cid in seen:
            kind = "idempotent duplicate" if seen[cid] == digest else "conflict: same conversation_id, different text"
            problems.append(f"{cid}: {kind}")
        seen.setdefault(cid, digest)
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
    broken = json.loads(json.dumps(base))
    broken["annotations"]["framing"].append(dict(broken["annotations"]["framing"][0], value="clinical"))
    assert any("duplicate annotation" in p for p in semantic_problems(broken, dimensions))
    broken = json.loads(json.dumps(base))
    broken["source"]["captured_utc"] = "2026-99-99T99:99:99Z"           # shape-valid, not an instant
    assert any("not a real UTC instant" in p for p in semantic_problems(broken, dimensions))


def test_schema_requires_the_attachment_count_on_every_turn(schema):
    assert "attachments_omitted" in schema["properties"]["turns"]["items"]["required"]
    base = _examples()[0]
    broken = json.loads(json.dumps(base))
    del broken["turns"][0]["attachments_omitted"]
    assert any("missing 'attachments_omitted'" in p for p in validate(broken, schema))


def test_counterfactual_eligibility_needs_a_model_identity():
    base = _examples()[0]
    assert counterfactual_ineligibility(base) is None
    anonymous = json.loads(json.dumps(base))
    anonymous["source"]["model"] = None
    assert (counterfactual_ineligibility(anonymous) or "").startswith("model_unidentified")


def test_reply_pairing_and_the_per_turn_ineligibility_cases():
    base = _examples()[0]
    assert reply_pairs(base) == ([(1, 2)], [])
    assert counterfactual_ineligibility(base, 2) is None
    # adjacency rule without reply_to
    adjacent = json.loads(json.dumps(base))
    del adjacent["turns"][1]["reply_to"]
    assert reply_pairs(adjacent) == ([(1, 2)], [])
    # two consecutive assistant turns: the second answers no identifiable user turn
    orphan = json.loads(json.dumps(base))
    orphan["turns"].append({"turn_id": 3, "role": "assistant", "text": "<follow-up>", "attachments_omitted": 0})
    assert reply_pairs(orphan) == ([(1, 2)], [3])
    assert (counterfactual_ineligibility(orphan, 3) or "").startswith("unpaired_reply")
    # attachments on either side
    with_att = json.loads(json.dumps(base))
    with_att["turns"][0]["attachments_omitted"] = 1
    assert (counterfactual_ineligibility(with_att, 2) or "").startswith("attachments_omitted")
    with_att = json.loads(json.dumps(base))
    with_att["turns"][1]["attachments_omitted"] = 2
    assert (counterfactual_ineligibility(with_att, 2) or "").startswith("incomplete_reply")


def test_reply_to_must_name_an_earlier_user_turn(dimensions):
    base = _examples()[0]
    broken = json.loads(json.dumps(base))
    broken["turns"][1]["reply_to"] = 2                                 # itself
    assert any("not an earlier user turn" in p for p in semantic_problems(broken, dimensions))
    broken = json.loads(json.dumps(base))
    broken["turns"][0]["reply_to"] = 1                                 # on a user turn
    assert any("non-assistant" in p for p in semantic_problems(broken, dimensions))


def test_conversation_ids_are_unique_across_a_file():
    base = _examples()[0]
    assert file_problems([base]) == []
    twice = [base, json.loads(json.dumps(base))]
    assert file_problems(twice) == [f"{base['conversation_id']}: idempotent duplicate"]
    changed = json.loads(json.dumps(base))
    changed["provenance"]["text_sha256"] = "1" * 64
    assert any("conflict" in p for p in file_problems([base, changed]))


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
        contrast_sources = {c["from"] for c in cf["contrasts"]}
        no_contrast = set(cf.get("no_contrast", []))
        assert not (contrast_sources & no_contrast), f"{d['id']}: a value cannot both have a contrast and none"
        assert contrast_sources | no_contrast == set(d["values"]), \
            f"{d['id']}: every value needs a contrast or a no_contrast entry"
        unknown = set(d["probes"]) - set(probe_ids)
        assert not unknown, f"dimension {d['id']!r} names unknown probes {sorted(unknown)}"
    inputs = set(dimensions["inputs_levels"])
    for p in probes:
        for key in ("id", "name", "requires", "implementation", "output", "status", "inputs"):
            assert key in p, f"probe {p.get('id')!r} lacks {key!r}"
        assert p["requires"] in levels, f"probe {p['id']!r} requires unknown level {p['requires']!r}"
        assert p["inputs"] and set(p["inputs"]) <= inputs, f"probe {p['id']!r} lists unknown inputs {p['inputs']}"


def test_example_annotations_use_declared_dimensions(dimensions):
    by_id = {d["id"]: d for d in dimensions["dimensions"]}
    for record in _examples():
        for ann in record.get("annotations", {}).get("framing", []):
            assert ann["dimension_id"] in by_id, ann
            assert ann["value"] in by_id[ann["dimension_id"]]["values"], ann
            turn_ids = {t["turn_id"] for t in record["turns"]}
            assert ann["turn_id"] in turn_ids, ann
