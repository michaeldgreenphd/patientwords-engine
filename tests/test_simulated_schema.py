"""Offline checks for the shared artifact schema and its limited stdlib adapter.

These tests use no site checkout, model runtime, browser, or network. The separate
HTTP boundary suite applies a full JSON Schema validator to the same authority.
"""
from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_frontend_contract.py"
SPEC = importlib.util.spec_from_file_location("simulated_contract_gate", SCRIPT)
vfc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vfc)


def legacy_payload() -> dict:
    return {
        "batches": [{"batch": "pairs_example", "generated": {}}],
        "traced": {},
        "scenarios": [{"index": 1, "batch": "pairs_example", "batch_index": 1,
                       "clinical_prompt": "alpha", "patient_prompt": "beta", "intended_target": "gamma"}],
    }


def structure(value: object, schema: dict | None = None, *, export: bool = False) -> list[str]:
    rep = vfc.Report()
    vfc.check_schema_subset(rep, "test.json", value,
                            vfc.SIMULATED_SCHEMA if schema is None else schema, export_gate=export)
    return rep.errors


def test_legacy_read_shape_remains_valid_but_is_not_a_new_export() -> None:
    payload = legacy_payload()
    assert structure(payload) == []
    errors = structure(payload, export=True)
    assert len(errors) == 2
    assert any("$.models_meta :: missing required key" in error for error in errors)
    assert any("$.scenarios[0].models :: missing required key" in error for error in errors)


def test_additive_properties_remain_valid() -> None:
    payload = legacy_payload()
    payload["future_key"] = {"value": [1, 2, 3]}
    payload["scenarios"][0]["future_field"] = True
    assert structure(payload) == []


@pytest.mark.parametrize("value", [None, [], "wrong", False])
def test_nonobject_row_is_a_reported_error_not_a_crash(value: object, tmp_path: Path) -> None:
    payload = legacy_payload()
    payload["models_meta"] = []
    payload["scenarios"] = [value]
    rep = vfc.Report()
    vfc.check_simulated(rep, tmp_path, payload)
    assert any("$.scenarios[0] :: wrong type" in error for error in rep.errors)


@pytest.mark.parametrize("field,value", [
    ("index", True), ("index", 1.0), ("batch", None),
    ("clinical_prompt", 1), ("models", []), ("html", False),
])
def test_declared_scenario_types_are_enforced(field: str, value: object) -> None:
    payload = legacy_payload()
    payload["scenarios"][0][field] = value
    assert any(f"$.scenarios[0].{field} :: wrong type" in error for error in structure(payload))


def test_nullable_zero_and_missing_model_number_are_distinct() -> None:
    model_schema = {
        "$ref": "#/definitions/model",
    }
    # Validate a model through a real authority reference, not copied field definitions.
    schema = deepcopy(vfc.SIMULATED_SCHEMA)
    schema["properties"]["probe"] = model_schema
    required = schema["definitions"]["model"]["required"]
    model = dict.fromkeys(required)
    model.update(flipped=False, anchor_fallback=False, spread_clinical=[], spread_patient=[])
    payload = legacy_payload()
    payload["probe"] = model
    assert structure(payload, schema) == []
    model["prob_patient"] = 0
    assert structure(payload, schema) == []
    model["prob_patient"] = False
    assert any("probe.prob_patient :: wrong type" in error for error in structure(payload, schema))
    del model["prob_patient"]
    assert any("probe.prob_patient :: missing required key" in error for error in structure(payload, schema))


def test_model_dictionary_values_follow_references() -> None:
    payload = legacy_payload()
    payload["scenarios"][0]["models"] = {"model-x": []}
    assert any("models[model-x] :: wrong type" in error for error in structure(payload))


@pytest.mark.parametrize("mutation", [
    {"minimum": 0}, {"anyOf": [{"type": "string"}]},
    {"items": [{"type": "string"}]}, {"items": True},
    {"$ref": "other.json"}, {"type": "mystery"},
    {"$ref": "#/definitions/model", "type": "object"},
])
def test_unsupported_schema_features_fail_closed_even_if_unused(mutation: dict) -> None:
    schema = deepcopy(vfc.SIMULATED_SCHEMA)
    schema["definitions"]["unused"] = mutation
    with pytest.raises(ValueError):
        structure(legacy_payload(), schema)


def test_additional_properties_false_is_enforced() -> None:
    assert structure({"extra": 1}, {"type": "object", "additionalProperties": False})


def test_openapi_refers_to_the_authority_without_a_second_shape() -> None:
    path = SCRIPT.parent / "contracts" / "simulated_scenarios.openapi.json"
    api = json.loads(path.read_text(encoding="utf-8"))
    assert api["openapi"] == "3.1.0"
    assert api["jsonSchemaDialect"] == vfc.SIMULATED_SCHEMA["$schema"]
    assert list(api["paths"]) == ["/data/simulated_scenarios.json"]
    resource = api["paths"]["/data/simulated_scenarios.json"]
    assert list(resource) == ["get"]
    response = resource["get"]["responses"]["200"]["content"]["application/json"]
    assert response["schema"] == {"$ref": "./simulated_scenarios.v1.schema.json"}
    assert (path.parent / response["schema"]["$ref"]).resolve() == vfc.SIMULATED_SCHEMA_PATH


def test_shape_errors_preserve_usable_join_keys_without_accepting_malformed_keys(tmp_path: Path) -> None:
    payload = {
        "batches": [{"batch": "pairs_example"}, None, {"batch": []}],
        "scenarios": [{"batch": "pairs_example", "batch_index": 1}, None,
                      {"batch": "pairs_example", "batch_index": True},
                      {"batch": [], "batch_index": 2}],
        "models_meta": [{"id": "model-x"}, None, {"id": []}],
    }
    rep = vfc.Report()
    joins = vfc.check_simulated(rep, tmp_path, payload)
    assert rep.errors
    assert joins == {"scenario_keys": {("pairs_example", 1)},
                     "batch_stems": {"pairs_example"}, "meta_ids": {"model-x"}}
