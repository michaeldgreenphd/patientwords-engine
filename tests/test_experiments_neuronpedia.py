"""Neuronpedia identity and link boundary: registry, links, fallback, snapshots, records, explanations.

Offline. The fixture registry is synthetic: an invented toy model, invented ids and a host under the reserved
``.invalid`` domain. Label texts are abstract placeholders. These tests show that the registry rules and the
link rules behave as written. They are not evidence that any Neuronpedia page exists, that any id in the real
registry resolves on the site, or that a hosted checkpoint equals a study pin: no page was read and no request
was made (the hosts were unreachable on 2026-11-10, and this module sends nothing in any case).
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import inspect
import json
import socket
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from medlang_circuits import graph_client, neuronpedia_features
from scripts import feature_models, logits_eval
from scripts.experiments import capabilities, common
from scripts.experiments import neuronpedia as nps
from scripts.experiments.common import Refusal
from scripts.frontend_contract_schema import check_schema_subset

ENGINE = Path(__file__).resolve().parents[1]
FX = ENGINE / "tests" / "fixtures" / "experiments" / "neuronpedia"
MODULE = ENGINE / "scripts" / "experiments" / "neuronpedia.py"

ALIAS = "qwen3.5-2b-base.ica-component.neuronpedia-alias"
GEMMA_SET = "gemma-2-2b.transcoder-feature.gemmascope-transcoder-16k"
QWEN_SET = "qwen3-4b.transcoder-feature.transcoder-hp"
FX_VERIFIED = "toy-model.ica-component.fixture-verified"
FX_ALIAS = "toy-model.ica-component.fixture-alias"
FX_NO_PATTERN = "toy-model.workspace-readout.fixture-no-pattern"
FX_TRANSCODER = "toy-model.transcoder-feature.fixture-set"
# Written out here, not read from the fixture: template https://registry-fixture.invalid/{model_id}/
# {layer}-{source_set}/{component} with model_id toy-model-hosted, layer 1, source set toy-ica-set, component 3.
EXPECTED_FIXTURE_URL = "https://registry-fixture.invalid/toy-model-hosted/1-toy-ica-set/3"
PLACEHOLDER_WORDS = {"placeholder", "label", "alpha", "beta", "gamma", "|"}


def read(name: str) -> Any:
    return json.loads((FX / name).read_text(encoding="utf-8"))


def code_of(call: Callable[[], Any]) -> str:
    with pytest.raises(Refusal) as caught:
        call()
    return caught.value.code


@pytest.fixture(scope="module")
def real() -> dict:
    return nps.load_registry()


@pytest.fixture
def fixture_registry() -> dict:
    return nps.load_registry(FX / "representation_registry.fixture.json")


def entry(registry: dict, registry_id: str) -> dict:
    found = nps.entry_by_id(registry, registry_id)
    assert found is not None, registry_id
    return found


def mutated(registry: dict, registry_id: str, change: Callable[[dict], None]) -> dict:
    doc = copy.deepcopy(registry)
    change(entry(doc, registry_id))
    return doc


# ------------------------------------------------------------------------------------------------ registry

def test_schema_uses_only_the_keywords_the_repository_validator_executes() -> None:
    schema = common.load_schema("representation_registry")
    assert schema["$id"] == nps.REGISTRY_SCHEMA == "patientwords.representation-registry/1"
    errors: list[str] = []
    check_schema_subset(lambda _a, where, why: errors.append(f"{where}: {why}"), "representation_registry",
                        nps.load_registry(), schema)
    assert errors == []


def test_vocabularies_are_the_contract_strings() -> None:
    assert nps.VERIFICATION_STATUSES == ("verified_exact", "alias_unverified_checkpoint",
                                         "hosted_identity_unknown", "unverified")
    assert nps.GRAPH_REF_KIND in common.PAYLOAD_KINDS
    assert common.METHOD_PAYLOAD_KINDS["attribution_graph"] == (nps.GRAPH_REF_KIND,)
    assert nps.QUANTITY_KINDS == ("feature_interpretability_score", "label_prediction_score", "lens_token_rank",
                                  "clinical_outcome")


def test_real_registry_validates_and_states_what_was_not_read(real: dict) -> None:
    assert real["synthetic"] is False
    assert len({e["registry_id"] for e in real["entries"]}) == len(real["entries"]) == 9
    assert {e["representation_type"] for e in real["entries"]} == {"transcoder_feature", "workspace_readout",
                                                                  "ica_component"}
    # Every source page the registry could have been checked against is listed as not read, with the date.
    assert len(real["sources_not_read"]) == 14
    assert all(item["attempted_utc_date"] == "2026-11-10" for item in real["sources_not_read"])


def test_real_entries_agree_with_the_engine_tables(real: dict) -> None:
    for item in real["entries"]:
        study_id = item["model"]["study_id"]
        if study_id is None:
            assert "/model/study_id" in item["not_recorded"] and item["model"]["revision"] is None
            continue
        assert logits_eval.HF_IDS[study_id] == item["model"]["hf_id"], item["registry_id"]
        assert logits_eval.HF_REVISIONS[study_id] == item["model"]["revision"], item["registry_id"]
    for registry_id in (GEMMA_SET, QWEN_SET):
        hosted = entry(real, registry_id)["neuronpedia"]
        assert hosted["model_id"] in graph_client.MODEL_REGISTRY
        assert neuronpedia_features.MODEL_SOURCE_SETS[hosted["model_id"]] == hosted["source_set"]
    calibrated = {(e["neuronpedia"]["model_id"], e["neuronpedia"]["source_set"]) for e in real["entries"]
                  if e["calibration"] == "calibrated_reference"}
    assert calibrated == set(feature_models.CALIBRATED_FEATURE_SOURCES)
    assert entry(real, QWEN_SET)["calibration"] == "not_calibrated"
    assert entry(real, QWEN_SET)["use"] == "exploration_only"


def test_registry_artifact_ids_exist_in_the_capability_matrix(real: dict) -> None:
    matrix_ids = {(row["model"]["hf_id"], row["artifact"]["id"]) for row in capabilities.load_matrix()["rows"]
                  if row["artifact"] is not None}
    for item in real["entries"]:
        if item["artifact"] is not None:
            assert (item["model"]["hf_id"], item["artifact"]["id"]) in matrix_ids, item["registry_id"]


def test_real_statuses_are_the_ones_the_evidence_supports(real: dict) -> None:
    statuses = {e["registry_id"]: e["verification"]["status"] for e in real["entries"]}
    assert statuses[ALIAS] == "alias_unverified_checkpoint"
    assert statuses[GEMMA_SET] == statuses[QWEN_SET] == "hosted_identity_unknown"
    assert statuses["gemma-2-2b.workspace-readout.hosted-jlens"] == "hosted_identity_unknown"
    assert statuses["gemma-2-2b-it.workspace-readout.hosted-jlens"] == "hosted_identity_unknown"
    # No page was read on 2026-11-10, so nothing is verified_exact, no hosted revision is recorded and no URL
    # pattern is recorded. An entry may change only together with its evidence.
    for item in real["entries"]:
        assert item["verification"]["status"] != "verified_exact", item["registry_id"]
        assert item["links_enabled"] is False
        assert item["verification"]["hosted_checkpoint_revision"] is None
        assert item["url_pattern"] is None and "/url_pattern" in item["not_recorded"]
        assert item["verification"]["evidence"]


def test_alias_entry_records_the_pin_and_that_the_page_was_not_read(real: dict) -> None:
    alias = entry(real, ALIAS)
    assert alias["model"] == {"study_id": "qwen3.5-2b-base", "hf_id": "Qwen/Qwen3.5-2B-Base",
                              "revision": logits_eval.HF_REVISIONS["qwen3.5-2b-base"]}
    assert alias["neuronpedia"]["model_id"] == "qwen3.5-2b-pt"
    assert alias["neuronpedia"]["source_set"] is None and "/neuronpedia/source_set" in alias["not_recorded"]
    sources = " ".join(e["source"] + " " + e["states"] for e in alias["verification"]["evidence"])
    assert "scripts/logits_eval.py" in sources and "Not read" in sources


@pytest.mark.parametrize("change,code", [
    (lambda e: e.update(links_enabled=True), "links_without_verification"),
    (lambda e: e["verification"].update(status="verified_exact"), "verification_status"),
    (lambda e: e["verification"].update(status="verified"), "verification_status"),
    (lambda e: e["verification"].update(evidence=[]), "verification_evidence"),
    (lambda e: e.update(representation_type="feature"), "representation_type"),
    (lambda e: e.update(method="ica"), "unknown_method"),
    (lambda e: e["model"].update(revision="main"), "registry_entry"),
    (lambda e: e["neuronpedia"].update(model_id="two words"), "registry_entry"),
    (lambda e: e["not_recorded"].remove("/url_pattern"), "silent_missing_provenance"),
    (lambda e: e["not_recorded"].append("/model/hf_id"), "not_recorded_pointer"),
    (lambda e: e["model"].update(hf_id="fixture/toy-model"), "synthetic_label"),
])
def test_dishonest_or_malformed_entries_are_refused(real: dict, change: Callable[[dict], None], code: str) -> None:
    assert code_of(lambda: nps.validate_registry(mutated(real, ALIAS, change))) == code


def test_verified_exact_needs_the_hosted_revision_to_equal_the_study_pin(real: dict) -> None:
    def claim(revision: str) -> Callable[[dict], None]:
        def change(e: dict) -> None:
            e["verification"].update(status="verified_exact", hosted_checkpoint_revision=revision)
            e["not_recorded"].remove("/verification/hosted_checkpoint_revision")
        return change
    # Another commit behind the alias: refused. The same commit, recorded: accepted.
    assert code_of(lambda: nps.validate_registry(mutated(real, ALIAS, claim("a" * 40)))) == "verification_status"
    pin = logits_eval.HF_REVISIONS["qwen3.5-2b-base"]
    assert nps.validate_registry(mutated(real, ALIAS, claim(pin)))


def test_duplicate_ids_and_wrong_schema_are_refused(real: dict) -> None:
    doubled = copy.deepcopy(real)
    doubled["entries"].append(copy.deepcopy(doubled["entries"][0]))
    assert code_of(lambda: nps.validate_registry(doubled)) == "duplicate_entry"
    assert code_of(lambda: nps.validate_registry({**real, "schema_version": "patientwords.registry/0"})) \
        == "schema_version"
    assert code_of(lambda: nps.validate_registry({**real, "verification_statuses": ["verified_exact"]})) \
        == "verification_status"
    extra = mutated(real, ALIAS, lambda e: e.update(understanding_score=1.0))
    assert code_of(lambda: nps.validate_registry(extra)) == "invalid_input"


# ------------------------------------------------------------------------------------------------ resolve

def test_resolve_returns_the_entry_or_a_typed_no_mapping(real: dict) -> None:
    found = nps.resolve("gemma-2-2b", "transcoder_feature", registry=real)
    assert found.mapped and found.entry["registry_id"] == GEMMA_SET and not found.verified

    for query in (("gemma-2-2b", "sae_latent"), ("gemma-2-2b", "attention_head"), ("no-such-model", "neuron")):
        missing = nps.resolve(*query, registry=real)
        assert isinstance(missing, nps.Resolution)
        assert missing.status == "no_mapping" and missing.entry is None and not missing.mapped
        assert missing.reason.startswith(nps.REASON_NO_MAPPING)
    # A transcoder entry does not answer for another representation type of the same model.
    assert "not interchangeable" in nps.resolve("qwen3-4b", "sae_latent", registry=real).reason
    assert code_of(lambda: nps.resolve("gemma-2-2b", "feature", registry=real)) == "representation_type"


def test_alias_never_resolves_as_verified(real: dict) -> None:
    alias = nps.resolve("qwen3.5-2b-base", "ica_component", registry=real)
    assert alias.mapped and alias.entry["registry_id"] == ALIAS
    assert alias.verified is False
    strict = nps.resolve("qwen3.5-2b-base", "ica_component", require_verified=True, registry=real)
    assert strict.status == "no_mapping" and strict.entry is None
    assert "alias_unverified_checkpoint" in strict.reason and strict.candidates == (ALIAS,)
    # The Neuronpedia id is a field of the entry, not a second key.
    assert nps.resolve("qwen3.5-2b-pt", "ica_component", registry=real).status == "no_mapping"


def test_resolve_layers_and_ambiguity(fixture_registry: dict) -> None:
    both = nps.resolve("toy-model", "ica_component", registry=fixture_registry)
    assert both.status == "ambiguous" and both.entry is None
    assert both.candidates == (FX_ALIAS, FX_VERIFIED)
    at_one = nps.resolve("toy-model", "ica_component", 1, registry=fixture_registry)
    assert at_one.mapped and at_one.verified and at_one.entry["registry_id"] == FX_VERIFIED
    assert at_one.layer_coverage == "recorded"
    at_two = nps.resolve("toy-model", "ica_component", 2, registry=fixture_registry)
    assert at_two.mapped and not at_two.verified and at_two.entry["registry_id"] == FX_ALIAS
    assert nps.resolve("toy-model", "ica_component", 0, registry=fixture_registry).status == "no_mapping"
    by_set = nps.resolve("toy-model", "ica_component", source_set="toy-ica-alias-set", registry=fixture_registry)
    assert by_set.entry["registry_id"] == FX_ALIAS


def test_resolve_says_when_layer_coverage_is_not_recorded(real: dict) -> None:
    found = nps.resolve("qwen3-4b", "transcoder_feature", 7, registry=real)
    assert found.mapped and found.layer_coverage == "not_recorded"


# ------------------------------------------------------------------------------------------------ links

def test_fixture_mapping_links_and_the_real_alias_does_not(real: dict, fixture_registry: dict) -> None:
    built = nps.build_link(entry(fixture_registry, FX_VERIFIED), 3, layer=1)
    assert built.url == EXPECTED_FIXTURE_URL and built.reason == nps.LINK_BUILT

    withheld = nps.build_link(entry(real, ALIAS), 3, layer=1)
    assert withheld.url is None and withheld.reason == nps.REASON_NOT_VERIFIED == "mapping not verified"
    assert "alias_unverified_checkpoint" in withheld.detail


def test_the_two_withheld_reasons(fixture_registry: dict) -> None:
    # An alias with a recorded pattern: still no link.
    alias = nps.build_link(entry(fixture_registry, FX_ALIAS), 3, layer=2)
    assert (alias.url, alias.reason) == (None, "mapping not verified")
    # Verified, and the registry records no pattern.
    bare = nps.build_link(entry(fixture_registry, FX_NO_PATTERN), 3, layer=1)
    assert (bare.url, bare.reason) == (None, nps.REASON_NO_PATTERN)
    assert nps.REASON_NO_PATTERN == "no recorded URL pattern"


def test_no_real_entry_yields_a_link(real: dict) -> None:
    for item in real["entries"]:
        assert nps.build_link(item, 0, layer=0).url is None, item["registry_id"]


def test_link_functions_take_no_text_argument() -> None:
    assert list(inspect.signature(nps.build_link).parameters) == ["entry", "component_id", "layer"]
    assert list(inspect.signature(nps.link_or_fallback).parameters) == ["target", "component_id", "layer", "record"]


@pytest.mark.parametrize("component", ["alpha beta tail", "12", "C3", 3.0, True, -1, None, ["3"]])
def test_a_non_integer_component_id_never_reaches_a_url(fixture_registry: dict, component: Any) -> None:
    target = entry(fixture_registry, FX_VERIFIED)
    assert code_of(lambda: nps.build_link(target, component, layer=1)) == "free_text_in_url"
    assert code_of(lambda: nps.link_or_fallback(target, component, layer=1)) == "free_text_in_url"
    # The refusal comes before the status check, so an unverified entry does not hide a text argument.
    assert code_of(lambda: nps.build_link(entry(fixture_registry, FX_ALIAS), component, layer=2)) == "free_text_in_url"


def test_a_text_layer_is_refused(fixture_registry: dict) -> None:
    target = entry(fixture_registry, FX_VERIFIED)
    assert code_of(lambda: nps.build_link(target, 3, layer="alpha tail")) == "free_text_in_url"
    assert code_of(lambda: nps.build_link(target, 3)) == "link_arguments"
    assert code_of(lambda: nps.build_link(target, 3, layer=2)) == "layer_metadata"


@pytest.mark.parametrize("template", [
    "https://registry-fixture.invalid/{model_id}/lens?prompt={component}",
    "https://registry-fixture.invalid/{model_id}/{prompt}",
    "https://registry-fixture.invalid/{model_id}/a%20b/{component}",
    "https://registry-fixture.invalid/{model_id}/{component}#alpha",
    "https://registry-fixture.invalid/{model_id}/alpha beta/{component}",
    "http://registry-fixture.invalid/{model_id}/{component}",
    "https://{model_id}.invalid/{component}",
    "https://registry-fixture.invalid/{model_id}/{source_id}/{component}",
])
def test_a_template_that_could_carry_text_is_refused(fixture_registry: dict, template: str) -> None:
    doc = mutated(fixture_registry, FX_VERIFIED, lambda e: e["url_pattern"].update(template=template))
    assert code_of(lambda: nps.validate_registry(doc)) == "url_template"


def test_fixture_links_cannot_point_at_a_real_host_and_real_entries_cannot_use_the_fixture_host(
        real: dict, fixture_registry: dict) -> None:
    outside = mutated(fixture_registry, FX_VERIFIED, lambda e: e["url_pattern"].update(
        template="https://example.org/{model_id}/{layer}-{source_set}/{component}"))
    assert code_of(lambda: nps.validate_registry(outside)) == "synthetic_label"

    def borrow(e: dict) -> None:
        e["url_pattern"] = copy.deepcopy(entry(fixture_registry, FX_VERIFIED)["url_pattern"])
        e["not_recorded"].remove("/url_pattern")
    assert code_of(lambda: nps.validate_registry(mutated(real, GEMMA_SET, borrow))) == "synthetic_label"


def test_every_built_url_is_made_of_recorded_ids_and_integers(fixture_registry: dict) -> None:
    target = entry(fixture_registry, FX_VERIFIED)
    allowed = {target["neuronpedia"]["model_id"], target["neuronpedia"]["source_set"], "registry-fixture.invalid"}
    for component in (0, 3, 4095):
        url = nps.build_link(target, component, layer=1).url
        assert url is not None and "?" not in url and "#" not in url and "%" not in url and " " not in url
        host, model_id, layer_and_set, last = url[len("https://"):].split("/")
        layer, _, source_set = layer_and_set.partition("-")
        assert {host, model_id, source_set} <= allowed
        assert layer == "1" and last == str(component)


def test_a_hand_made_entry_cannot_switch_links_on(real: dict, fixture_registry: dict) -> None:
    forged = copy.deepcopy(entry(real, ALIAS))
    forged["links_enabled"] = True
    forged["url_pattern"] = copy.deepcopy(entry(fixture_registry, FX_VERIFIED)["url_pattern"])
    forged["not_recorded"].remove("/url_pattern")
    assert code_of(lambda: nps.build_link(forged, 3, layer=1)) == "links_without_verification"


# ------------------------------------------------------------------------------------------------ fallback

def test_fallback_record_is_present_when_the_link_is_none(real: dict) -> None:
    record = {"signed_score": -0.5, "note_id": "row-7"}
    result = nps.link_or_fallback(nps.resolve("qwen3.5-2b-base", "ica_component", registry=real), 3, layer=1,
                                  record=record)
    assert result["link"] is None and result["reason"] == "mapping not verified"
    local = result["local"]
    assert local["registry_id"] == ALIAS and local["component_id"] == 3 and local["layer"] == 1
    assert local["representation_type"] == "ica_component" and local["method"] == "ica_lens"
    assert local["model"]["revision"] == logits_eval.HF_REVISIONS["qwen3.5-2b-base"]
    assert local["verification"] == {"status": "alias_unverified_checkpoint", "checked_utc_date": "2026-11-10"}
    assert local["record"] == record and local["inspectable_offline"] is True
    assert "/neuronpedia/source_set" in local["not_recorded"]
    assert json.loads(json.dumps(result)) == result


def test_fallback_record_is_also_present_with_a_link_and_with_no_mapping(real: dict, fixture_registry: dict) -> None:
    linked = nps.link_or_fallback(entry(fixture_registry, FX_VERIFIED), 3, layer=1, record={"signed_score": 1.5})
    assert linked["link"] == EXPECTED_FIXTURE_URL and linked["reason"] == nps.LINK_BUILT
    assert linked["local"]["registry_id"] == FX_VERIFIED and linked["local"]["record"] == {"signed_score": 1.5}
    assert linked["local"]["fitted_artifact_sha256"] == "2" * 64

    unmapped = nps.link_or_fallback(nps.resolve("gemma-2-2b", "neuron", registry=real), 5, layer=2,
                                    record={"signed_score": 0.0})
    assert unmapped["link"] is None and unmapped["reason"] == "no mapping"
    assert unmapped["local"]["registry_id"] is None and unmapped["local"]["component_id"] == 5
    assert unmapped["local"]["query"]["study_model_id"] == "gemma-2-2b"
    assert unmapped["local"]["record"] == {"signed_score": 0.0}


# ------------------------------------------------------------------------------------------------ no network

def test_module_imports_no_network_or_process_library() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported == {"__future__", "functools", "math", "re", "dataclasses", "pathlib", "typing",
                        "scripts.experiments.common", "scripts.experiments.envelope"}
    assert "NO NETWORK REQUEST" in (ast.get_docstring(tree) or "")


def test_importing_and_using_the_module_opens_no_socket(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the Neuronpedia boundary module tried to open a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    name = "pw_neuronpedia_no_network"
    spec = importlib.util.spec_from_file_location(name, MODULE)
    fresh = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, fresh)
    spec.loader.exec_module(fresh)

    real = fresh.load_registry()
    toy = fresh.load_registry(FX / "representation_registry.fixture.json")
    assert fresh.resolve("gemma-2-2b", "transcoder_feature", registry=real).mapped
    assert fresh.build_link(fresh.entry_by_id(toy, FX_VERIFIED), 3, layer=1).url == EXPECTED_FIXTURE_URL
    assert fresh.link_or_fallback(fresh.entry_by_id(real, ALIAS), 3, layer=1)["link"] is None
    export = tmp_path / "export.jsonl"
    export.write_bytes(b"alpha\n")
    snapshot = fresh.record_snapshot(export, "https://exports.invalid/v1/toy.jsonl", "2026-11-10T00:00:00Z")
    assert fresh.verify_snapshot(export, snapshot)["status"] == "verified"
    assert fresh.validate_feature_explanations(read("feature_explanations.fixture.json"))
    assert fresh.validate_graph_reference(read("graph_reference.fixture.json"), toy)["status"] == "validated"
    assert fresh.validate_request_record(request_document())


# ------------------------------------------------------------------------------------------------ snapshots

def test_snapshot_records_hash_size_and_stated_provenance(tmp_path: Path) -> None:
    export = tmp_path / "export.jsonl"
    export.write_bytes(b"alpha beta\n")
    record = nps.record_snapshot(export, "https://exports.invalid/v1/toy.jsonl", "2026-11-10T12:00:00Z")
    # sha256 of the 11 bytes "alpha beta\n", computed with the stdlib outside the module.
    assert record == {"schema_version": "patientwords.export-snapshot/1",
                      "sha256": hashlib.sha256(b"alpha beta\n").hexdigest(), "bytes": 11,
                      "source_url": "https://exports.invalid/v1/toy.jsonl", "retrieved_utc": "2026-11-10T12:00:00Z",
                      "not_recorded": []}
    assert nps.verify_snapshot(export, record) == {"status": "verified", "sha256": record["sha256"], "bytes": 11,
                                                   "provenance_complete": True, "not_recorded": []}


def test_snapshot_verification_detects_altered_bytes(tmp_path: Path) -> None:
    export = tmp_path / "export.jsonl"
    export.write_bytes(b"alpha beta\n")
    record = nps.record_snapshot(export, "https://exports.invalid/v1/toy.jsonl", "2026-11-10")
    export.write_bytes(b"alpha bet4\n")  # same length, one byte changed
    assert code_of(lambda: nps.verify_snapshot(export, record)) == "snapshot_hash"
    export.write_bytes(b"alpha beta\nx")
    assert code_of(lambda: nps.verify_snapshot(export, record)) == "snapshot_size"
    export.unlink()
    assert code_of(lambda: nps.verify_snapshot(export, record)) == "snapshot_missing"
    assert code_of(lambda: nps.record_snapshot(export, None, None)) == "snapshot_missing"


def test_missing_snapshot_provenance_is_recorded_and_never_filled_in(tmp_path: Path) -> None:
    export = tmp_path / "export.jsonl"
    export.write_bytes(b"alpha\n")
    record = nps.record_snapshot(export, None, None)
    assert record["source_url"] is None and record["retrieved_utc"] is None
    assert record["not_recorded"] == ["/retrieved_utc", "/source_url"]
    checked = nps.verify_snapshot(export, record)
    assert checked["status"] == "verified" and checked["provenance_complete"] is False
    silent = {**record, "not_recorded": ["/source_url"]}
    assert code_of(lambda: nps.verify_snapshot(export, silent)) == "silent_missing_provenance"


@pytest.mark.parametrize("url", [
    "https://exports.invalid/v1/toy.jsonl?X-Amz-Signature=abc", "https://user@exports.invalid/v1/toy.jsonl",
    "http://exports.invalid/v1/toy.jsonl", "exports.invalid/v1/toy.jsonl"])
def test_a_snapshot_url_with_a_query_string_or_user_part_is_refused(tmp_path: Path, url: str) -> None:
    export = tmp_path / "export.jsonl"
    export.write_bytes(b"alpha\n")
    assert code_of(lambda: nps.record_snapshot(export, url, "2026-11-10")) == "snapshot_url"
    assert code_of(lambda: nps.record_snapshot(export, "https://exports.invalid/v1/toy.jsonl", "yesterday")) \
        == "snapshot_provenance"


# ------------------------------------------------------------------------------------------------ request record

def request_document() -> dict:
    return {
        "schema_version": "patientwords.api-request-record/1",
        "endpoint": {"method": "POST", "host": "service.invalid", "path": "/api/toy/readout"},
        "effective_request_settings": {"model_id": "toy-model-hosted", "top_n": 8, "prompt_sha256": "6" * 64,
                                       "bounds": {"top_n": [1, 16]}},
        "service_identity": {"service": "fixture service", "model_id": "toy-model-hosted",
                             "instrument_revision": None},
        "response_sha256": "9" * 64,
        "retrieved_utc": "2026-11-10T00:00:00Z",
        "not_recorded": ["/service_identity/instrument_revision"],
    }


def test_request_record_structure() -> None:
    doc = request_document()
    assert nps.validate_request_record(doc) == doc
    built = nps.request_record(
        endpoint=doc["endpoint"], effective_request_settings=doc["effective_request_settings"],
        service_identity=doc["service_identity"], response_sha256=doc["response_sha256"],
        retrieved_utc=doc["retrieved_utc"], not_recorded=doc["not_recorded"])
    assert built == doc
    assert set(doc) - {"schema_version", "not_recorded"} == {
        "endpoint", "effective_request_settings", "service_identity", "response_sha256", "retrieved_utc"}


@pytest.mark.parametrize("change,code", [
    (lambda d: d["effective_request_settings"].update(prompt="alpha beta tail"), "prompt_text_in_record"),
    (lambda d: d["effective_request_settings"].update(body={"messages": []}), "prompt_text_in_record"),
    (lambda d: d["effective_request_settings"].update(headers={"x-api-key": "k"}), "secret_in_record"),
    (lambda d: d["service_identity"].update(Authorization="k"), "secret_in_record"),
    (lambda d: d.update(not_recorded=[]), "silent_missing_provenance"),
    (lambda d: d.update(response_sha256=None), "silent_missing_provenance"),
    (lambda d: d["endpoint"].update(path="/api/toy/readout?prompt=alpha"), "request_record"),
    (lambda d: d["endpoint"].update(method="DELETE"), "request_record"),
    (lambda d: d.update(response_sha256="abc"), "request_record"),
    (lambda d: d.update(cost_usd=0.0), "request_record"),
    (lambda d: d["service_identity"].pop("instrument_revision"), "request_record"),
])
def test_request_record_refusals(change: Callable[[dict], None], code: str) -> None:
    doc = request_document()
    change(doc)
    assert code_of(lambda: nps.validate_request_record(doc)) == code


# ------------------------------------------------------------------------------------------------ explanations

@pytest.fixture
def explanations() -> dict:
    return read("feature_explanations.fixture.json")


def test_fixtures_hold_placeholders_only(explanations: dict, fixture_registry: dict) -> None:
    for label in explanations["labels"]:
        assert set(label["text"].split()) <= PLACEHOLDER_WORDS
    assert fixture_registry["synthetic"] is True
    assert all(e["model"]["hf_id"] == "fixture/toy-model" for e in fixture_registry["entries"])
    assert all("SYNTHETIC" in e["notes"] for e in fixture_registry["entries"])


def test_competing_labels_are_all_kept_with_source_and_scorer(explanations: dict) -> None:
    doc = nps.validate_feature_explanations(explanations)
    assert [label["label_id"] for label in doc["labels"]] == ["label-a", "label-b", "label-c"]
    assert {label["source"]["name"] for label in doc["labels"]} == {"fixture_labels", "fixture_labels_second"}
    assert all("scorer" in label and label["status"] == "hypothesis" for label in doc["labels"])
    # A missing scorer is null and listed. It is not dropped and not invented.
    assert doc["labels"][1]["scorer"] is None and "/labels/1/scorer" in doc["not_recorded"]

    fourth = {**copy.deepcopy(doc["labels"][0]), "label_id": "label-d", "text": "placeholder label gamma"}
    grown = nps.add_label(doc, fourth)
    assert [label["label_id"] for label in grown["labels"]] == ["label-a", "label-b", "label-c", "label-d"]
    assert len(doc["labels"]) == 3
    assert code_of(lambda: nps.add_label(doc, copy.deepcopy(doc["labels"][0]))) == "duplicate_label"
    assert code_of(lambda: nps.validate_feature_explanations({**doc, "label": "placeholder label alpha"})) \
        == "label_selection"
    silent = copy.deepcopy(doc)
    silent["not_recorded"].remove("/labels/1/scorer")
    assert code_of(lambda: nps.validate_feature_explanations(silent)) == "silent_missing_provenance"


def test_a_token_list_label_is_flagged_as_not_a_clinical_concept_name(explanations: dict) -> None:
    label = nps.token_list_label("label-t", ["alpha", "beta"], source=explanations["labels"][0]["source"],
                                 scorer={"name": "fixture_scorer", "version": "1"})
    assert label["basis"] == "token_list_only" and label["flags"] == ["not_a_clinical_concept_name"]
    assert nps.FLAG_TEXT["not_a_clinical_concept_name"] == "not a clinical concept name"
    assert label["tokens"] == ["alpha", "beta"] and label["status"] == "hypothesis"
    assert explanations["labels"][2]["basis"] == "token_list_only"

    unflagged = copy.deepcopy(explanations)
    unflagged["labels"][2]["flags"] = []
    assert code_of(lambda: nps.validate_feature_explanations(unflagged)) == "token_list_label"
    promoted = copy.deepcopy(explanations)
    promoted["labels"][2]["status"] = "verified"
    assert code_of(lambda: nps.validate_feature_explanations(promoted)) == "annotation_status"
    assert code_of(lambda: nps.token_list_label("label-e", [], source={}, scorer=None)) == "token_list_label"


def test_the_four_quantities_cannot_be_merged(explanations: dict) -> None:
    quantities = explanations["quantities"]
    assert set(quantities) == set(nps.QUANTITY_KINDS)

    # 1. A record moved to another field is refused, in every direction.
    for source in nps.QUANTITY_KINDS:
        for target in nps.QUANTITY_KINDS:
            if source == target:
                continue
            moved = copy.deepcopy(explanations)
            moved["quantities"][target].append(copy.deepcopy(quantities[source][0]))
            assert code_of(lambda: nps.validate_feature_explanations(moved)) == "score_kind_mismatch", (source, target)

    # 2. A generic score, at any level, and a fifth field are refused.
    for place in (lambda d: d, lambda d: d["labels"][0], lambda d: d["quantities"]["lens_token_rank"][0]):
        generic = copy.deepcopy(explanations)
        place(generic)["score"] = 0.5
        assert code_of(lambda: nps.validate_feature_explanations(generic)) == "merged_score"
    fifth = copy.deepcopy(explanations)
    fifth["quantities"]["understanding_score"] = [{"kind": "understanding_score", "value": 0.5}]
    assert code_of(lambda: nps.validate_feature_explanations(fifth)) == "merged_score"

    # 3. Gathering refuses mixed kinds, and gathering one kind changes nothing.
    mixed = [quantities["feature_interpretability_score"][0], quantities["label_prediction_score"][0]]
    assert code_of(lambda: nps.collect_quantity("feature_interpretability_score", mixed)) == "score_kind_merge"
    assert code_of(lambda: nps.collect_quantity("score", mixed)) == "score_kind_merge"
    assert nps.collect_quantity("label_prediction_score", quantities["label_prediction_score"]) \
        == quantities["label_prediction_score"]

    # 4. A field does not accept another kind's attributes under its own name.
    scored_rank = copy.deepcopy(explanations)
    scored_rank["quantities"]["lens_token_rank"][0]["scorer"] = {"name": "fixture_scorer", "version": "1"}
    assert code_of(lambda: nps.validate_feature_explanations(scored_rank)) == "quantity_fields"
    scored_outcome = copy.deepcopy(explanations)
    scored_outcome["quantities"]["clinical_outcome"][0]["scorer"] = {"name": "fixture_scorer", "version": "1"}
    assert code_of(lambda: nps.validate_feature_explanations(scored_outcome)) == "quantity_fields"


def test_quantity_values_keep_missing_apart_from_zero(explanations: dict) -> None:
    missing = explanations["quantities"]["label_prediction_score"][1]
    assert missing["value"] is None and missing["missing_reason"]
    silent = copy.deepcopy(explanations)
    del silent["quantities"]["label_prediction_score"][1]["missing_reason"]
    assert code_of(lambda: nps.validate_feature_explanations(silent)) == "missing_value"
    zero = copy.deepcopy(explanations)
    zero["quantities"]["label_prediction_score"][1]["value"] = 0.0
    assert code_of(lambda: nps.validate_feature_explanations(zero)) == "missing_value"  # a value with a reason
    del zero["quantities"]["label_prediction_score"][1]["missing_reason"]
    assert nps.validate_feature_explanations(zero)

    for change, code in [
        (lambda q: q["lens_token_rank"][0].update(value=1.5), "quantity_fields"),
        (lambda q: q["lens_token_rank"][0].update(value=0), "quantity_fields"),  # below rank_base 1
        (lambda q: q["lens_token_rank"][0].update(lens="attribution_graph"), "quantity_fields"),
        (lambda q: q["label_prediction_score"][0].update(label_id="label-z"), "quantity_fields"),
        (lambda q: q["clinical_outcome"][0].update(owner="neuronpedia"), "quantity_fields"),
        (lambda q: q["feature_interpretability_score"][0].update(value=float("nan")), "quantity_fields"),
        (lambda q: q["feature_interpretability_score"][0].pop("scorer"), "quantity_fields"),
    ]:
        doc = copy.deepcopy(explanations)
        change(doc["quantities"])
        assert code_of(lambda: nps.validate_feature_explanations(doc)) == code


# ------------------------------------------------------------------------------------------------ graph reference

@pytest.fixture
def graph_ref() -> dict:
    return read("graph_reference.fixture.json")


def test_graph_reference_validates_alone_and_against_the_registry(graph_ref: dict, fixture_registry: dict) -> None:
    assert nps.validate_graph_reference(graph_ref) == {"status": "validated", "native_retained": True,
                                                      "registry_checked": False}
    assert nps.validate_graph_reference(graph_ref, fixture_registry)["registry_checked"] is True
    assert entry(fixture_registry, FX_TRANSCODER)["representation_type"] == "transcoder_feature"


def test_graph_reference_for_a_real_entry_records_that_the_native_graph_was_not_kept(real: dict) -> None:
    # The engine stores a pruned and annotated graph, not the native one, so a reference to a landed trace has no
    # native hash. The fields are null and listed.
    hosted = entry(real, GEMMA_SET)
    ref = {
        "kind": "attribution_graph_ref/1", "registry_id": GEMMA_SET, "model": dict(hosted["model"]),
        "neuronpedia": {"model_id": "gemma-2-2b", "source_set": "gemmascope-transcoder-16k"},
        "graph": {"native_retained": False, "native_sha256": None, "native_bytes": None, "schema_version": None,
                  "slug_sha256": None, "n_nodes": None, "n_links": None},
        "input": {"prompt_sha256": "6" * 64, "token_sha256": None},
        "settings_sha256": None, "retrieved_utc": None,
        "not_recorded": ["/graph/native_bytes", "/graph/native_sha256", "/graph/n_links", "/graph/n_nodes",
                         "/graph/schema_version", "/graph/slug_sha256", "/input/token_sha256", "/retrieved_utc",
                         "/settings_sha256"],
    }
    assert nps.validate_graph_reference(ref, real)["native_retained"] is False
    wrong_set = copy.deepcopy(ref)
    wrong_set["neuronpedia"]["source_set"] = "transcoder-hp"
    assert code_of(lambda: nps.validate_graph_reference(wrong_set, real)) == "source_set_identity"
    assert nps.validate_graph_reference(wrong_set)["registry_checked"] is False  # only the registry can tell


@pytest.mark.parametrize("change,code", [
    (lambda r: r.update(kind="ica_scores/1"), "payload_kind"),
    (lambda r: r.update(prompt="alpha beta tail"), "graph_ref_keys"),
    (lambda r: r["graph"].update(slug="fixture-alpha-beta-tail-1"), "graph_ref_keys"),
    (lambda r: r["graph"].update(nodes=[]), "graph_ref_keys"),
    (lambda r: r["neuronpedia"].pop("source_set"), "graph_ref_keys"),
    (lambda r: r["model"].update(hf_id="alpha beta tail"), "free_text_in_reference"),
    (lambda r: r["neuronpedia"].update(source_set="toy transcoder set"), "free_text_in_reference"),
    (lambda r: r["graph"].update(native_sha256="4" * 63), "graph_ref_hash"),
    (lambda r: r["input"].update(prompt_sha256="abc"), "graph_ref_hash"),
    (lambda r: r["graph"].update(native_sha256=None), "graph_native_artifact"),
    (lambda r: r["graph"].update(native_retained=False), "graph_native_artifact"),
    (lambda r: r["graph"].update(n_nodes=-1), "graph_ref_identity"),
    (lambda r: r["model"].update(revision="main"), "graph_ref_identity"),
    (lambda r: r.update(settings_sha256=None), "silent_missing_provenance"),
    (lambda r: r.update(not_recorded=["/graph/n_nodes"]), "not_recorded_pointer"),
])
def test_graph_reference_refusals(graph_ref: dict, change: Callable[[dict], None], code: str) -> None:
    change(graph_ref)
    assert code_of(lambda: nps.validate_graph_reference(graph_ref)) == code


@pytest.mark.parametrize("change,code", [
    (lambda r: r.update(registry_id="toy-model.transcoder-feature.absent"), "unknown_registry_id"),
    (lambda r: r.update(registry_id=FX_VERIFIED), "representation_type"),
    (lambda r: r["neuronpedia"].update(source_set="toy-ica-set"), "source_set_identity"),
    (lambda r: r["neuronpedia"].update(model_id="toy-model-other-name"), "source_set_identity"),
    (lambda r: r["model"].update(study_id="toy-model-2"), "graph_ref_identity"),
])
def test_graph_reference_is_checked_against_the_registry_entry(graph_ref: dict, fixture_registry: dict,
                                                               change: Callable[[dict], None], code: str) -> None:
    change(graph_ref)
    assert code_of(lambda: nps.validate_graph_reference(graph_ref, fixture_registry)) == code
