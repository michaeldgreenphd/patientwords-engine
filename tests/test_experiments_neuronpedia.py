"""Neuronpedia identity and link boundary: registry, links, fallback, snapshots, records, explanations.

Offline. The fixture registry is synthetic: an invented toy model, invented ids and a host under the reserved
``.invalid`` domain. Label texts are abstract placeholders. These tests show that the registry rules and the
link rules behave as written. They contact nothing. What the real registry says about the service rests on
responses fetched on 2026-11-10, outside the module, with plain GET requests; their hashes, sizes, retrieval
times and the fields read are in ``data/experiments/neuronpedia_evidence/20261110/index.v1.json``, with the
small JSON bodies beside it. The tests compare the registry with those saved records. They are therefore
evidence about what the service answered on that date, not about what it answers today, and nothing here shows
that a hosted checkpoint equals a study pin: no record that was read names a revision.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import inspect
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from medlang_circuits import graph_client, neuronpedia_features
from scripts import feature_models, jlens_readout, logits_eval
from scripts.experiments import capabilities, common
from scripts.experiments import neuronpedia as nps
from scripts.experiments.common import Refusal
from scripts.frontend_contract_schema import check_schema_subset

ENGINE = Path(__file__).resolve().parents[1]
FX = ENGINE / "tests" / "fixtures" / "experiments" / "neuronpedia"
MODULE = ENGINE / "scripts" / "experiments" / "neuronpedia.py"

EVIDENCE = ENGINE / "data" / "experiments" / "neuronpedia_evidence" / "20261110"
EVIDENCE_INDEX = "data/experiments/neuronpedia_evidence/20261110/index.v1.json"
EVIDENCE_DAY = "2026-11-10"
# A response key that would name a revision, a commit or a content hash.
REVISION_KEY = re.compile(r"revision|commit|checkpoint|sha256|sha1|hash", re.I)
CITED_RECORD = re.compile(r"\(records? ([a-z0-9.-]+)(?: and ([a-z0-9.-]+))? in " + re.escape(EVIDENCE_INDEX) + r"\)")

ALIAS = "qwen3.5-2b-base.ica-component.neuronpedia-alias"
HOSTED_LENSES = ("gemma-2-2b.workspace-readout.hosted-jlens", "gemma-2-2b-it.workspace-readout.hosted-jlens")
# The bases the ICA fork names, with the Neuronpedia model id and the repository the service's records name.
FORK_BASES = {
    "gemma-2-2b.ica-component.sida-icalens-gemma-2-2b-pile10k": ("gemma-2-2b", "neuronpedia/icalens-gemma-2-2b"),
    "gpt2.ica-component.sida-icalens-gpt2-small-pile10k": ("gpt2-small", "neuronpedia/icalens-gpt2-small"),
    "qwen3.5-9b-base.ica-component.sida-icalens-qwen3.5-9b-base-pile10k": ("qwen3.5-9b-pt",
                                                                         "neuronpedia/icalens-qwen3.5-9b-pt"),
}
INSTRUCT_BASIS = "qwen3.5-2b-instruct.ica-component.sida-icalens-qwen3.5-2b-ultrachat-1m"
# The fourteen pages listed as not read when the registry was written. All were read on 2026-11-10.
FORMERLY_UNREAD = (
    "https://www.neuronpedia.org/blog/neurons-ica", "https://www.neuronpedia.org/blog",
    "https://arxiv.org/abs/2606.11722v2", "https://docs.neuronpedia.org/api-and-data/api",
    "https://docs.neuronpedia.org/sparse-autoencoders/auto-interp", "https://www.neuronpedia.org/graph/validator",
    "https://www.neuronpedia.org/blog/circuit-tracer", "https://www.neuronpedia.org/blog/interp-engine",
    "https://www.neuronpedia.org/blog/headvis", "https://www.neuronpedia.org/blog/nlas",
    "https://www.neuronpedia.org/blog/assistant-axis", "https://www.neuronpedia.org/blog/jpp-drift-ui",
    "https://www.neuronpedia.org/blog/interp-explorer", "https://www.neuronpedia.org/blog/fall-update",
)
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


@pytest.fixture(scope="module")
def evidence() -> dict[str, dict]:
    """The records fetched on 2026-11-10, by id."""
    index = json.loads((EVIDENCE / "index.v1.json").read_text(encoding="utf-8"))
    assert index["schema_version"] == "patientwords.neuronpedia-evidence/1"
    assert index["retrieved_utc_date"] == EVIDENCE_DAY
    by_id = {record["id"]: record for record in index["records"]}
    assert len(by_id) == len(index["records"]) == 62
    return by_id


def body_of(record: dict) -> Any:
    """The saved response body of a record that keeps one: a JSON document, or the first row of a JSONL export."""
    raw = (EVIDENCE / record["body"]).read_text(encoding="utf-8")
    return json.loads(raw) if record["kind"] == "api_json" else json.loads(raw.splitlines()[0])


def keys_in(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {key for value in node.values() for key in keys_in(value)}
    if isinstance(node, list):
        return {key for value in node for key in keys_in(value)}
    return set()


def cited_records(text: str) -> list[str]:
    return [name for found in CITED_RECORD.findall(text) for name in found if name]


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
    # What is still unread after 2026-11-10: Hugging Face (the host was refused) and two POST routes that were
    # not requested, one of them because it runs a model.
    assert [item["url"] for item in real["sources_not_read"]] == [
        "https://huggingface.co/api/models/neuronpedia/icalens-qwen3.5-2b-pt",
        "https://www.neuronpedia.org/api/model/lookup",
        "https://www.neuronpedia.org/api/lens/prompt",
    ]
    assert all(item["attempted_utc_date"] == EVIDENCE_DAY for item in real["sources_not_read"])
    blocked, lookup, lens = (item["result"] for item in real["sources_not_read"])
    assert blocked.startswith("not read:") and "403" in blocked
    assert lookup.startswith("not requested:") and "POST" in lookup
    assert lens.startswith("not requested:") and "runs a model" in lens


def test_the_pages_once_listed_as_not_read_are_recorded_as_read(real: dict, evidence: dict[str, dict]) -> None:
    read = {record["snapshot"]["source_url"]: record for record in evidence.values()}
    still_unread = {item["url"] for item in real["sources_not_read"]}
    for url in FORMERLY_UNREAD:
        assert url not in still_unread, url
        assert read[url]["http_status"] == 200 and read[url]["snapshot"]["bytes"] > 0, url
        assert read[url]["snapshot"]["retrieved_utc"].startswith(EVIDENCE_DAY), url


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
    assert statuses == {
        GEMMA_SET: "hosted_identity_unknown", QWEN_SET: "hosted_identity_unknown",
        HOSTED_LENSES[0]: "hosted_identity_unknown", HOSTED_LENSES[1]: "hosted_identity_unknown",
        ALIAS: "alias_unverified_checkpoint",
        **{registry_id: "unverified" for registry_id in (*FORK_BASES, INSTRUCT_BASIS)},
    }
    # The service's records were read on 2026-11-10 and none names a revision (the tests below), so nothing is
    # verified_exact and no hosted revision is recorded. The documentation gives a feature page form; it is
    # not entered as a URL pattern. An entry may change only together with its evidence.
    for item in real["entries"]:
        assert item["verification"]["status"] != "verified_exact", item["registry_id"]
        assert item["links_enabled"] is False
        assert item["verification"]["hosted_checkpoint_revision"] is None
        assert "/verification/hosted_checkpoint_revision" in item["not_recorded"]
        assert item["url_pattern"] is None and "/url_pattern" in item["not_recorded"]
        assert item["verification"]["evidence"]
        assert item["verification"]["checked_utc_date"] == EVIDENCE_DAY


def test_every_evidence_record_is_hashed_dated_and_sourced(evidence: dict[str, dict]) -> None:
    """One record per response: SHA-256, size, URL and retrieval time, made by ``record_snapshot``. A body that
    was kept still has the recorded hash and size; a request record validates and repeats the response hash."""
    kept = 0
    for record_id, record in evidence.items():
        snapshot = record["snapshot"]
        assert snapshot["schema_version"] == nps.SNAPSHOT_SCHEMA and snapshot["not_recorded"] == [], record_id
        assert nps.HEX64.fullmatch(snapshot["sha256"]) and snapshot["bytes"] > 0, record_id
        assert nps.PLAIN_URL.fullmatch(snapshot["source_url"]), record_id
        assert re.fullmatch(EVIDENCE_DAY + r"T\d{2}:\d{2}:\d{2}Z", snapshot["retrieved_utc"]), record_id
        assert record["kind"] in ("api_json", "export_jsonl", "html_page") and record["fields_read"], record_id
        if record["body"] is None:
            assert record["body_omitted_reason"], record_id
        else:
            kept += 1
            assert record["body_omitted_reason"] is None and record["kind"] != "html_page", record_id
            assert nps.verify_snapshot(EVIDENCE / record["body"], snapshot) == {
                "status": "verified", "sha256": snapshot["sha256"], "bytes": snapshot["bytes"],
                "provenance_complete": True, "not_recorded": []}, record_id
        if "request" in record:
            request = nps.validate_request_record(record["request"])
            assert request["endpoint"]["method"] == "GET"
            assert snapshot["source_url"] == f"https://{request['endpoint']['host']}{request['endpoint']['path']}"
            assert request["response_sha256"] == snapshot["sha256"]
            assert request["retrieved_utc"] == snapshot["retrieved_utc"]
            assert request["effective_request_settings"] == {}
    assert kept == 24 and sorted(p.name for p in (EVIDENCE / "bodies").iterdir()) == sorted(
        Path(record["body"]).name for record in evidence.values() if record["body"])
    # Feature records hold dataset text and user names, and pages are large: neither body is in the repository.
    assert all(record["body"] is None for record_id, record in evidence.items()
               if record["kind"] == "html_page" or record_id.startswith("api.feature."))
    assert all("@" not in (EVIDENCE / record["body"]).read_text(encoding="utf-8")
               for record in evidence.values() if record["body"])
    # Every request was a GET of a plain URL. The only non-200 answer is the probe of a route that does not exist.
    assert {record_id for record_id, record in evidence.items() if record["http_status"] != 200} == {
        "probe.api.source.qwen3.5-2b-pt.0-icalens-res"}


def test_no_record_of_the_service_names_a_revision(evidence: dict[str, dict]) -> None:
    """The reason no entry is verified_exact, checked on the saved bytes and on the fields read.

    ``sae_lens_training_version`` (null in every record) is a library version and is not a revision of a model
    or of a dictionary. A request record lists its three revision fields as not recorded."""
    for record_id, record in evidence.items():
        if record["body"] is not None:
            named = {key for key in keys_in(body_of(record)) if REVISION_KEY.search(key)}
            assert named == set(), (record_id, named)
        if "keys_naming_a_revision_commit_or_hash" in record["fields_read"]:
            assert record["fields_read"]["keys_naming_a_revision_commit_or_hash"] == [], record_id
        if "request" in record:
            identity = record["request"]["service_identity"]
            assert identity["service"] == "www.neuronpedia.org"
            assert (identity["model_revision"], identity["dictionary_revision"], identity["instrument_revision"]) \
                == (None, None, None)
            assert record["request"]["not_recorded"] == ["/service_identity/dictionary_revision",
                                                         "/service_identity/instrument_revision",
                                                         "/service_identity/model_revision"]
    with_request = {record_id for record_id, record in evidence.items() if "request" in record}
    assert len(with_request) == 11 and all(record_id.startswith(("api.source-set.", "api.feature."))
                                           for record_id in with_request)
    # The documentation agrees for the two routes that were not called.
    reference = evidence["page.api-doc"]["fields_read"]
    assert not any(REVISION_KEY.search(field) for field in reference["model_lookup_response_fields"])
    assert not any(REVISION_KEY.search(key) for key in reference["lens_prompt_meta_example_keys"])
    assert reference["operations_under_model_source_or_source_set"] == ["POST /api/model/lookup",
                                                                         "POST /api/model/new"]
    assert evidence["page.available-resources"]["fields_read"]["keys_naming_a_revision_commit_or_hash"] == []


def test_registry_evidence_about_the_service_cites_a_recorded_response(real: dict,
                                                                       evidence: dict[str, dict]) -> None:
    """An evidence item whose source is a URL names the record that holds its hash, and the URL is the one that
    record was fetched from. A hosted entry's id_source cites such a record too."""
    for item in real["entries"]:
        from_service = [e for e in item["verification"]["evidence"] if e["source"].startswith("https://")]
        for cited in from_service:
            url = cited["source"].split(" ", 1)[0]
            names = cited_records(cited["source"])
            assert len(names) == 1, cited["source"]
            assert evidence[names[0]]["snapshot"]["source_url"] == url, cited["source"]
            assert cited["date"] == evidence[names[0]]["snapshot"]["retrieved_utc"][:10] == EVIDENCE_DAY
        # Every real entry has at least one dated, hashed record of the service behind its status.
        assert from_service, item["registry_id"]
        if item["neuronpedia"] is not None:
            url = item["neuronpedia"]["id_source"].split(",", 1)[0]
            names = cited_records(item["neuronpedia"]["id_source"])
            assert names and evidence[names[0]]["snapshot"]["source_url"] == url, item["registry_id"]
            assert "read on 2026-11-10" in item["neuronpedia"]["id_source"]
    for text in (real["description"], *(e["notes"] for e in real["entries"])):
        assert "service reports no" not in text  # say which record was read, not what the service does in general


def test_hosted_ids_layers_and_repositories_are_the_ones_in_the_saved_records(real: dict,
                                                                             evidence: dict[str, dict]) -> None:
    for registry_id in (GEMMA_SET, QWEN_SET, ALIAS):
        item = entry(real, registry_id)
        hosted = item["neuronpedia"]
        body = body_of(evidence[f"api.source-set.{hosted['model_id']}.{hosted['source_set']}"])
        assert (body["modelId"], body["name"]) == (hosted["model_id"], hosted["source_set"])
        # The service names the repository the engine pins. It names no commit, so the pin is not compared.
        assert body["model"]["hfRepoId"] == item["model"]["hf_id"] == logits_eval.HF_IDS[item["model"]["study_id"]]
        layers = sorted(int(source["id"].split("-", 1)[0]) for source in body["sources"])
        assert all(source["id"] == f"{layer}-{hosted['source_set']}" for source, layer in zip(
            sorted(body["sources"], key=lambda s: int(s["id"].split("-", 1)[0])), layers))
        assert item["site"]["layers"] == layers and item["site"]["layer_index_base"] == 0
        assert hosted["source_id"] == "not_applicable"
        feature = evidence[f"api.feature.{hosted['model_id']}.0-{hosted['source_set']}.0"]["fields_read"]
        assert feature["model"]["hfRepoId"] == item["model"]["hf_id"]
        assert feature["source"]["setName"] == hosted["source_set"]
    assert entry(real, GEMMA_SET)["site"]["layers"] == list(range(26))
    assert entry(real, QWEN_SET)["site"]["layers"] == list(range(36))

    # qwen3-4b: the API record and the export name one weights repository, and the registry records it.
    qwen_repositories = {source["hfRepoId"] for source in body_of(
        evidence["api.source-set.qwen3-4b.transcoder-hp"])["sources"]}
    qwen_export = body_of(evidence["export.qwen3-4b.0-transcoder-hp.source"])["hfRepoId"]
    assert qwen_repositories == {qwen_export} == {entry(real, QWEN_SET)["artifact"]["repository"]}
    # gemma-2-2b: the API record and the export disagree, so the registry records no repository and says so.
    gemma = entry(real, GEMMA_SET)
    gemma_api = {source["hfRepoId"] for source in body_of(
        evidence["api.source-set.gemma-2-2b.gemmascope-transcoder-16k"])["sources"]}
    gemma_export = body_of(evidence["export.gemma-2-2b.0-gemmascope-transcoder-16k.source"])["hfRepoId"]
    assert gemma_api == {"google/gemma-scope-2b-pt-transcoders"} and gemma_export == "google/gemma-scope"
    assert gemma["artifact"]["repository"] is None and "/artifact/repository" in gemma["not_recorded"]
    assert "(google/gemma-scope-2b-pt-transcoders; google/gemma-scope)" in gemma["notes"]

    # The hosted lens: a page per model id, with no lens identity in it.
    for registry_id in HOSTED_LENSES:
        item = entry(real, registry_id)
        page = evidence[f"page.jlens.{item['neuronpedia']['model_id']}"]["fields_read"]
        assert page["page_component_properties"] == {"modelId": item["neuronpedia"]["model_id"], "share": None,
                                                     "inferenceAvailable": True}
        listed = evidence["page.available-resources"]["fields_read"]["models"][item["neuronpedia"]["model_id"]]
        assert listed["hfRepoId"] == item["model"]["hf_id"]
        assert item["artifact"]["repository"] is None and item["site"]["layers"] is None


def test_alias_entry_records_the_pin_and_what_the_service_reported(real: dict, evidence: dict[str, dict]) -> None:
    alias = entry(real, ALIAS)
    assert alias["model"] == {"study_id": "qwen3.5-2b-base", "hf_id": "Qwen/Qwen3.5-2B-Base",
                              "revision": logits_eval.HF_REVISIONS["qwen3.5-2b-base"]}
    assert alias["neuronpedia"]["model_id"] == "qwen3.5-2b-pt" and alias["neuronpedia"]["source_set"] == "icalens-res"
    body = body_of(evidence["api.source-set.qwen3.5-2b-pt.icalens-res"])
    # The id exists and names the engine's repository; the basis repository and the hook are the service's.
    assert body["model"]["id"] == "qwen3.5-2b-pt" and body["model"]["hfRepoId"] == "Qwen/Qwen3.5-2B-Base"
    assert {source["hfRepoId"] for source in body["sources"]} == {alias["artifact"]["repository"]} \
        == {"neuronpedia/icalens-qwen3.5-2b-pt"}
    assert {source["hfFolderId"] for source in body["sources"]} == {
        f"blocks.{layer}.hook_resid_post" for layer in alias["site"]["layers"]}
    assert alias["site"] == {"capture_site": "resid_post", "layer_index_base": 0, "layers": [0, 4, 8, 12, 16, 20]}
    # No commit: not of the model, not of the basis. The entry stays an alias with an unverified checkpoint.
    assert alias["artifact"]["revision"] is None and alias["artifact"]["fit_model_revision"] is None
    assert {"/artifact/revision", "/artifact/fit_model_revision", "/verification/hosted_checkpoint_revision"} \
        <= set(alias["not_recorded"])
    assert alias["verification"]["status"] == "alias_unverified_checkpoint" and alias["links_enabled"] is False
    sources = " ".join(e["source"] + " " + e["states"] for e in alias["verification"]["evidence"])
    assert "scripts/logits_eval.py" in sources and "owner's task brief of 2026-11-10" in sources
    assert "Not read" not in sources and "No key in the response names a model revision" in sources
    assert "status stays alias_unverified_checkpoint" in alias["notes"]
    # The export of the same model record has no repository id at all; the entry says where the two differ.
    assert "hfRepoId" not in body_of(evidence["export.qwen3.5-2b-pt.0-icalens-res.model"])
    assert "has no hfRepoId key" in sources


def test_bases_named_in_the_ica_fork_keep_no_mapping_and_say_why(real: dict, evidence: dict[str, dict]) -> None:
    """The service hosts an ICA set for three of the four models, from a repository under neuronpedia/. The
    registry's entries are for repositories under sida/. Nothing read ties one to the other, so no mapping is
    entered and the status is left at unverified, with the reason."""
    for registry_id, (model_id, hosted_repository) in FORK_BASES.items():
        item = entry(real, registry_id)
        body = body_of(evidence[f"api.source-set.{model_id}.icalens-res"])
        assert body["model"]["hfRepoId"] == item["model"]["hf_id"]
        assert {source["hfRepoId"] for source in body["sources"]} == {hosted_repository}
        assert item["artifact"]["repository"].startswith("sida/") and hosted_repository != item["artifact"]["repository"]
        assert item["neuronpedia"] is None and "/neuronpedia" in item["not_recorded"]
        assert hosted_repository in item["notes"] and "left at unverified" in item["notes"]
    instruct = entry(real, INSTRUCT_BASIS)
    listing = evidence["page.available-resources"]["fields_read"]
    assert instruct["model"]["hf_id"] == "Qwen/Qwen3.5-2B"
    assert listing["model_ids_with_hfRepoId_Qwen/Qwen3.5-2B"] == [] and listing["model_record_count"] == 43
    assert evidence["page.model.qwen3.5-2b"]["fields_read"]["page_components"] == []
    assert instruct["neuronpedia"] is None and "left at unverified" in instruct["notes"]


def test_the_registry_the_matrix_and_the_doc_say_the_same_about_what_was_read(real: dict) -> None:
    """Wording rules, checked on the committed files.

    Hosted identity: the vocabulary sentence says where to look, and each entry's evidence says which records
    were read. The alias id qwen3.5-2b-pt: its id_source is the service's record; the owner's task brief of
    2026-11-10 is kept as where the id first came from; none of the three files still says that the service
    was not read, and none points at a design note, a repository text or a search result."""
    sourced = ("The entry's evidence names the records of the service that were read and says that none of them "
               "carries a revision, or says that none was read")
    doc = " ".join((ENGINE / "docs" / "experiment_interface" / "neuronpedia.md").read_text(encoding="utf-8").split())
    fixture = nps.load_registry(FX / "representation_registry.fixture.json")
    for registry in (real, fixture):
        assert sourced in registry["verification_meaning"]["hosted_identity_unknown"]
        assert "whether the service reports one was not read" not in json.dumps(registry)
    assert sourced in doc and "whether the service reports one was not read" not in doc
    # verified_exact keeps its definition, in the registry and in the doc.
    assert real["verification_meaning"]["verified_exact"] == fixture["verification_meaning"]["verified_exact"] == (
        "The Neuronpedia ids were read in a primary source and the hosted checkpoint revision is recorded and "
        "equals the study revision. The only status that permits a link.")

    origin, stale = "owner's task brief of 2026-11-10", (
        "design note", "repository text", "web-search", "search result", "are reported to name",
        "blocked by this environment's network policy", "unverified against the service", "Not read:",
        "no Neuronpedia page was read")
    alias = entry(real, ALIAS)
    assert alias["neuronpedia"]["id_source"].startswith(
        "https://www.neuronpedia.org/api/source-set/qwen3.5-2b-pt/icalens-res, read on 2026-11-10")
    assert origin in alias["neuronpedia"]["id_source"]
    assert all(phrase not in json.dumps(alias) for phrase in stale)
    assert [e["source"] for e in alias["verification"]["evidence"] if origin in e["source"]]
    # The two prose lines of the matrix that name the id: the not_verified item and the row's status note.
    matrix_lines = [line for line in (ENGINE / "data" / "experiments" / "capability_matrix.v1.json").read_text(
        encoding="utf-8").splitlines() if "qwen3.5-2b-pt" in line
        and not line.lstrip().startswith(('"id"', '"repository"', '"source"'))]
    assert len(matrix_lines) == 2
    for line in matrix_lines:
        assert "its model record names Qwen/Qwen3.5-2B-Base" in line and "2026-11-10" in line
        assert "unverified" in line and all(phrase not in line for phrase in stale), line
    paragraph = doc[doc.index("**`qwen3.5-2b-base` and `qwen3.5-2b-pt`.**"):doc.index(
        "**`sida/icalens-gemma-2-2b-pile10k`.**")]
    assert origin in paragraph and "Qwen/Qwen3.5-2B-Base" in paragraph and "reports no commit" in paragraph
    assert all(phrase not in paragraph for phrase in stale)
    assert EVIDENCE_INDEX in doc and EVIDENCE_INDEX in real["description"]


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


@pytest.mark.parametrize("study_id", [None, "", 0, False, ["gemma-2-2b"], b"gemma-2-2b"])
def test_resolve_refuses_a_study_id_that_is_not_a_non_empty_string(real: dict, study_id: Any) -> None:
    """Three real entries have study_id null because the engine does not run those models. ``None`` used to
    match them: resolve(None, "ica_component", artifact_id=...) returned status "mapped"."""
    no_study_id = [e for e in real["entries"] if e["model"]["study_id"] is None]
    assert len(no_study_id) == 3 and all(e["representation_type"] == "ica_component" for e in no_study_id)
    assert code_of(lambda: nps.resolve(study_id, "ica_component", registry=real)) == "invalid_input"
    assert code_of(lambda: nps.resolve(study_id, "ica_component", artifact_id=no_study_id[0]["artifact"]["id"],
                                       registry=real)) == "invalid_input"


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
    # The hosted lens entries record no layer list: a live lens response was not read.
    found = nps.resolve("gemma-2-2b", "workspace_readout", 7, registry=real)
    assert found.mapped and found.layer_coverage == "not_recorded"
    # The transcoder set's layers are the service's source ids, read on 2026-11-10.
    covered = nps.resolve("qwen3-4b", "transcoder_feature", 7, registry=real)
    assert covered.mapped and covered.layer_coverage == "recorded"
    assert nps.resolve("qwen3-4b", "transcoder_feature", 36, registry=real).status == "no_mapping"
    # The hosted ICA set of qwen3.5-2b-pt has every fourth layer.
    assert nps.resolve("qwen3.5-2b-base", "ica_component", 4, registry=real).mapped
    assert nps.resolve("qwen3.5-2b-base", "ica_component", 1, registry=real).status == "no_mapping"


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


def test_the_integers_of_a_url_are_bounded_so_a_hash_written_as_an_integer_is_refused(
        real: dict, fixture_registry: dict) -> None:
    """``build_link(entry, int("a" * 64, 16), layer=1)`` used to return a URL that ended in 77 digits."""
    verified, alias = entry(fixture_registry, FX_VERIFIED), entry(fixture_registry, FX_ALIAS)
    as_integer = int("a" * 64, 16)
    assert verified["component_id"]["count"] == 4096 and "count" not in alias["component_id"]
    assert (nps.MAX_COMPONENT_ID, nps.MAX_LAYER) == (2 ** 20, 4096)
    for target, layer in ((verified, 1), (alias, 2)):
        for component in (as_integer, 10 ** 80, 2 ** 32, 2 ** 20):
            with pytest.raises(Refusal) as caught:
                nps.build_link(target, component, layer=layer)
            assert caught.value.code == "free_text_in_url"
            assert component == 2 ** 20 or str(component) not in str(caught.value)     # the bound itself is named
            assert code_of(lambda: nps.link_or_fallback(target, component, layer=layer)) == "free_text_in_url"
        for big_layer in (4096, as_integer):
            assert code_of(lambda: nps.build_link(target, 3, layer=big_layer)) == "free_text_in_url"
            assert code_of(lambda: nps.link_or_fallback(target, 3, layer=big_layer)) == "free_text_in_url"
    # Below the entry's recorded component count when it records one; below 2**20 otherwise.
    assert nps.build_link(verified, 4095, layer=1).url.endswith("/4095")
    assert code_of(lambda: nps.build_link(verified, 4096, layer=1)) == "free_text_in_url"
    assert code_of(lambda: nps.build_link(verified, 2 ** 20 - 1, layer=1)) == "free_text_in_url"
    assert nps.build_link(alias, 2 ** 20 - 1, layer=2).reason == nps.REASON_NOT_VERIFIED     # in range, no link
    unmapped = nps.resolve("gemma-2-2b", "neuron", registry=real)
    assert nps.link_or_fallback(unmapped, 2 ** 20 - 1, layer=4095)["link"] is None
    assert code_of(lambda: nps.link_or_fallback(unmapped, 2 ** 20, layer=1)) == "free_text_in_url"
    assert code_of(lambda: nps.link_or_fallback(unmapped, 3, layer=4096)) == "free_text_in_url"
    # A recorded count is itself a bounded positive integer.
    for count in (0, -1, 2 ** 20 + 1, "4096", 4096.0, True, None):
        doc = mutated(fixture_registry, FX_VERIFIED, lambda e: e["component_id"].update(count=count))
        assert code_of(lambda: nps.validate_registry(doc)) in ("registry_entry", "invalid_input"), count
    # The committed registry records no count and still yields no link, for any entry and any in-range integers.
    assert all(nps._component_count(item) is None for item in real["entries"])
    for item in real["entries"]:
        for layer in (None, 0, 1, 12, 4095):
            for component in (0, 3, 99999, 2 ** 20 - 1):
                assert nps.build_link(item, component, layer=layer).url is None, item["registry_id"]
                assert nps.link_or_fallback(item, component, layer=layer)["link"] is None


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
    result = nps.link_or_fallback(nps.resolve("qwen3.5-2b-base", "ica_component", 4, registry=real), 3, layer=4,
                                  record=record)
    assert result["link"] is None and result["reason"] == "mapping not verified"
    local = result["local"]
    assert local["registry_id"] == ALIAS and local["component_id"] == 3 and local["layer"] == 4
    assert local["representation_type"] == "ica_component" and local["method"] == "ica_lens"
    assert local["model"]["revision"] == logits_eval.HF_REVISIONS["qwen3.5-2b-base"]
    assert local["verification"] == {"status": "alias_unverified_checkpoint", "checked_utc_date": "2026-11-10"}
    assert local["record"] == record and local["inspectable_offline"] is True
    assert local["neuronpedia"]["source_set"] == "icalens-res"
    assert "/verification/hosted_checkpoint_revision" in local["not_recorded"]
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


def public_functions(module: Any) -> set[str]:
    """Names of the functions a module defines itself whose names do not start with an underscore."""
    return {name for name, value in vars(module).items()
            if inspect.isfunction(value) and value.__module__ == module.__name__ and not name.startswith("_")}


def test_importing_and_using_the_module_opens_no_socket(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every public function of the module is called here, with the three socket entry points replaced.

    The last assertion compares the functions called with the functions the module defines, so the sentence in
    the module docstring ("calls every public function") cannot go stale when a function is added."""
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
    called: set[str] = set()

    def use(function: str) -> Callable[..., Any]:
        called.add(function)
        return getattr(fresh, function)

    real = use("load_registry")()
    toy = use("load_registry")(FX / "representation_registry.fixture.json")
    assert use("validate_registry")(copy.deepcopy(toy)) == toy
    verified, alias = use("entry_by_id")(toy, FX_VERIFIED), use("entry_by_id")(real, ALIAS)
    assert use("resolve")("gemma-2-2b", "transcoder_feature", registry=real).mapped
    assert use("build_link")(verified, 3, layer=1).url == EXPECTED_FIXTURE_URL
    assert use("link_or_fallback")(alias, 3, layer=1)["link"] is None
    assert use("local_record")(alias, 3, 1, {"signed_score": 1.5})["inspectable_offline"] is True
    export = tmp_path / "export.jsonl"
    export.write_bytes(b"alpha\n")
    snapshot = use("record_snapshot")(export, "https://exports.invalid/v1/toy.jsonl", "2026-11-10T00:00:00Z")
    assert use("verify_snapshot")(export, snapshot)["status"] == "verified"
    explanations = use("validate_feature_explanations")(read("feature_explanations.fixture.json"))
    label = use("token_list_label")("label-t", ["alpha", "beta"], source=explanations["labels"][0]["source"],
                                    scorer=None)
    assert len(use("add_label")(explanations, label, ["/labels/3/scorer"])["labels"]) == 4
    assert use("collect_quantity")("lens_token_rank", explanations["quantities"]["lens_token_rank"])
    assert use("validate_graph_reference")(read("graph_reference.fixture.json"), toy)["status"] == "validated"
    document = request_document()
    assert use("validate_request_record")(document)
    assert use("request_record")(**{key: document[key] for key in (
        "endpoint", "effective_request_settings", "service_identity", "response_sha256", "retrieved_utc",
        "not_recorded")}) == document
    assert called == public_functions(fresh) and len(called) == 16


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
        "service_identity": {"service": "fixture-service", "model_id": "toy-model-hosted",
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


REPOSITORY_SECRET_NAMES = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "NEURONPEDIA_API_KEY",
                           "HF_TOKEN")
OTHER_CREDENTIAL_KEYS = ("x-api-key", "X_API_KEY", "api-key", "apiKey", "access_token", "refreshToken", "bearer",
                         "cookie", "Set-Cookie", "auth", "Authorization", "credentials", "key", "keys", "secret",
                         "client_secret", "password", "session_id", "signature", "headers", "jwt")
TEXT_KEY_NAMES = ("prompt", "prompts", "prompt_text", "promptText", "user_prompt", "system_prompt", "text",
                  "input", "inputs", "input_text", "content", "contents", "message", "messages", "query", "body",
                  "slug", "completion", "transcript")


@pytest.mark.parametrize("block", ["effective_request_settings", "service_identity"])
@pytest.mark.parametrize("key", REPOSITORY_SECRET_NAMES + OTHER_CREDENTIAL_KEYS)
def test_a_credential_key_name_is_refused_under_any_spelling_and_at_any_depth(block: str, key: str) -> None:
    """Key names only. Every value here is the dummy "x" or a number; no credential appears in this file."""
    for value in ("x", 1, None, {"nested": 1}):
        top = request_document()
        top[block][key] = value
        assert code_of(lambda: nps.validate_request_record(top)) == "secret_in_record", (key, value)
    nested = request_document()
    nested[block]["options"] = {"more": [{key: "x"}]}
    assert code_of(lambda: nps.validate_request_record(nested)) == "secret_in_record"
    with pytest.raises(Refusal) as caught:
        nps.request_record(**{**{k: v for k, v in request_document().items() if k != "schema_version"},
                              block: {**request_document()[block], key: "x"}})
    assert caught.value.code == "secret_in_record" and "'x'" not in str(caught.value)   # the value is not echoed


@pytest.mark.parametrize("key", TEXT_KEY_NAMES)
def test_prompt_text_is_refused_under_alternative_key_names(key: str) -> None:
    """Abstract placeholders only: no prompt and no holdout text appears in this file."""
    for value in ("alpha beta tail", "alpha", ["alpha", "beta"], {"role": "user"}, 0):
        doc = request_document()
        doc["effective_request_settings"][key] = value
        assert code_of(lambda: nps.validate_request_record(doc)) == "prompt_text_in_record", (key, value)
    nested = request_document()
    nested["effective_request_settings"]["options"] = [{"deeper": {key: "alpha beta tail"}}]
    assert code_of(lambda: nps.validate_request_record(nested)) == "prompt_text_in_record"


@pytest.mark.parametrize("change", [
    lambda s: s.update(notes="alpha beta tail"),                    # a sentence under a key no rule names
    lambda s: s.update(model_id="alpha beta tail"),                 # a sentence under an id key
    lambda s: s.update(modelId="alpha beta tail"),
    lambda s: s.update(label="alpha"),                              # one id-shaped word under an unknown key
    lambda s: s.update(extra=["alpha beta", "tail"]),               # strings inside a list
    lambda s: s.update(extra=[[1, "alpha"]]),
    lambda s: s.update(options={"deeper": {"note": "alpha"}}),
    lambda s: s.update(type=["JACOBIAN_LENS", "alpha beta"]),       # one list item is not an id
    lambda s: s.update(type=[]),
    lambda s: s.update(prompt_sha256="alpha beta tail"),            # a hash key must hold a hash
    lambda s: s.update(prompt_sha256="6" * 63),
    lambda s: s.update(numCompletionTokens="alpha"),                # a counted setting must hold a count
    lambda s: s.update(top_n=float("inf")),
    lambda s: s.update({"alpha beta tail": 1}),                     # the key itself is the text
    lambda s: s.update({"a" * 49: 1}),
    lambda s: s.update({7: 1}),
])
def test_a_string_value_is_accepted_only_as_an_id_under_a_known_key(change: Callable[[dict], None]) -> None:
    for block in ("effective_request_settings", "service_identity"):
        doc = request_document()
        change(doc[block])
        with pytest.raises(Refusal) as caught:
            nps.validate_request_record(doc)
        assert caught.value.code == "free_text_in_record"
        assert "alpha beta tail" not in str(caught.value)            # neither a value nor a text key is echoed


WORDS = ["PLACEHOLDER", "WORDS", "STANDING", "IN", "FOR", "A", "PRIVATE", "SENTENCE", "OF"]      # nine constants


@pytest.mark.parametrize("key", ["type", "lens", "lens_type", "model_id", "modelId", "source_set", "sourceSetName",
                                 "sourceId", "dtype", "instrument_revision", "model_revision"])
def test_a_list_of_strings_is_accepted_only_as_a_short_list_of_constants_under_type(key: str) -> None:
    """A sentence stored one word per item used to validate under every id key, at any length."""
    def code(value: Any, block: str = "effective_request_settings") -> str | None:
        doc = request_document()
        doc[block][key] = value
        try:
            nps.validate_request_record(doc)
        except Refusal as refusal:
            assert not any(str(word) in str(refusal) for word in value if isinstance(word, str) and len(word) > 2)
            return refusal.code
        return None

    lower = [word.lower() for word in WORDS[:4]]
    for block in ("effective_request_settings", "service_identity"):
        assert code(lower, block) == "free_text_in_record"                  # id-shaped words, not constants
        assert code(WORDS, block) == "free_text_in_record"                  # nine items: one over the cap
        assert code(WORDS * 60, block) == "free_text_in_record"
        assert code(["JACOBIAN_LENS", "JACOBIAN_LENS"], block) == "free_text_in_record"     # an item twice
        assert code(["JACOBIAN_LENS", 3], block) == "free_text_in_record"
        assert code(["JACOBIAN_LENS", ["LOGIT_LENS"]], block) == "free_text_in_record"
        assert code(["org/JACOBIAN_LENS"], block) == "free_text_in_record"
        assert code(["A" * 33], block) == "free_text_in_record"
        assert code([], block) == "free_text_in_record"
    # The engine's own shape, and the longest list the rule accepts: under "type" only.
    allowed = None if key == "type" else "free_text_in_record"
    assert code(["JACOBIAN_LENS"]) == code(["JACOBIAN_LENS", "LOGIT_LENS"]) == code(WORDS[:8]) == allowed
    assert nps.LIST_VALUE_KEYS == {"type"} and nps.MAX_LIST_ITEMS == 8
    assert all(nps.LIST_ITEM.fullmatch(name) for name in jlens_readout.LENS_TYPES)


# Dummies: an issuer prefix followed by filler. None of these strings is or was a credential.
FILLER = "x" * 34
PREFIXED = ["sk-placeholder", "hf_placeholder", "AIzaPlaceholder", "ghp_placeholder", "hf_" + FILLER,
            "AIza" + FILLER, "sk-" + FILLER, "gho_" + FILLER, "github_pat_" + FILLER, "xoxb-" + FILLER]


@pytest.mark.parametrize("value", PREFIXED)
def test_a_string_with_a_credential_prefix_is_refused_wherever_it_sits(value: str) -> None:
    """The prefix test used to read the first characters of an id value only: ``org/<value>``, a key name, a
    path segment and a host label all validated."""
    def refused(change: Callable[[dict], None]) -> str:
        doc = request_document()
        change(doc)
        with pytest.raises(Refusal) as caught:
            nps.validate_request_record(doc)
        assert caught.value.code == "secret_in_record"
        assert value not in str(caught.value) and value.lower() not in str(caught.value).lower()
        return str(caught.value)

    def settings(**update: Any) -> Callable[[dict], None]:
        return lambda doc: doc["effective_request_settings"].update(update)

    refused(settings(model_id=value))
    refused(settings(model_id=value.upper()))
    refused(settings(model_id="org/" + value))                      # the part after the slash
    refused(settings(modelId=value + "/name"))
    refused(lambda doc: doc["service_identity"].update(type=["TOY_LENS", value]))
    refused(settings(type=["org/" + value]))
    refused(settings(notes=value))                                  # under a key that takes no string
    refused(settings(extra=[1, [value]]))                           # inside a nested list
    host_form = value.replace("_", "-")                             # a host holds no underscore
    refused(lambda doc: doc["endpoint"].update(path="/api/" + value))
    refused(lambda doc: doc["endpoint"].update(path="/api/toy/" + value + "/readout"))
    refused(lambda doc: doc["endpoint"].update(host=host_form + ".invalid"))
    refused(lambda doc: doc["endpoint"].update(host="api." + host_form + ".invalid"))
    # As a key name, with a number, with a string (key and value swapped) and nested: refused by position.
    for change in (settings(**{value: 1}), settings(**{value: "y"}), settings(bounds={value: [1, 2]}),
                   settings(options=[{"deeper": {value: None}}]),
                   lambda doc: doc["service_identity"].update({value: 1})):
        assert "key number" in refused(change)


def test_an_id_value_shaped_like_a_token_is_refused_and_a_commit_id_under_a_revision_key_is_not() -> None:
    """Filler strings built here from repeated letters and digits; none is a credential."""
    mixed = "Ab3" * 9                                  # 27 characters, three classes, no separator
    assert len(mixed) == 27 and nps.TOKEN_RUN_LENGTH == 24

    def code(key: str, value: str, block: str = "effective_request_settings") -> str | None:
        doc = request_document()
        doc[block][key] = value
        try:
            nps.validate_request_record(doc)
        except Refusal as refusal:
            assert value not in str(refusal)
            return refusal.code
        return None

    for key in ("model_id", "modelId", "source_set", "sourceId", "service", "type", "lens", "dtype",
                "instrument_revision", "model_revision", "dictionary_revision"):
        assert code(key, mixed) == "secret_in_record", key
        assert code(key, "org/" + mixed) == "secret_in_record", key
        assert code(key, "v1." + mixed + "-x") == "secret_in_record", key      # a run between separators
        assert code(key, "ab" * 13) is None, key                               # one class: not token-shaped
        assert code(key, "a1" * 12) is None, key                               # 24 characters: at the limit
        assert code(key, "a1" * 13) == "secret_in_record", key                 # 26: lower-case and digits
        assert code(key, "0123456789abcdef" * 2) == "secret_in_record", key    # 32 hex: not a commit id
    # 40 or 64 lower-case hex digits are a commit id or a content hash under a revision key, and only there.
    for digits in ("0123456789abcdef0123" * 2, "0123456789abcdef" * 4):
        for key in ("model_revision", "instrument_revision", "dictionary_revision"):
            assert code(key, digits) is None, key
            assert code(key, digits.upper()) == "secret_in_record", key
            assert code(key, "org/" + digits) == "secret_in_record", key
        for key in ("model_id", "source_set", "service", "type"):
            assert code(key, digits) == "secret_in_record", key
    recorded = request_document()
    recorded["service_identity"]["instrument_revision"], recorded["not_recorded"] = "0123456789abcdef0123" * 2, []
    assert nps.validate_request_record(recorded)
    assert code("prompt_sha256", "6" * 64) is None                              # a hash key keeps its own rule
    # Ids the registry and the engine use pass.
    for value in ("gemma-2-2b", "google/gemma-2-2b", "gemmascope-transcoder-16k", "qwen3.5-2b-pt",
                  "sida/icalens-qwen3.5-2b-ultrachat-1m", "JACOBIAN_LENS", "float32"):
        assert code("model_id", value) is None, value


SENTINEL = "ZZSENTINEL"


@pytest.mark.parametrize("entry_value", [
    SENTINEL + " words here", SENTINEL, "hf_" + FILLER, "/" + SENTINEL, "/notes/" + SENTINEL,
    "/effective_request_settings/" + SENTINEL + " words", "/effective_request_settings/" + "a" * 49,
    "/effective_request_settings/hf_" + FILLER, "/endpoint/host", "/schema_version", "/not_recorded/0",
    "effective_request_settings/top_n", "/effective_request_settings/", "", 7, None, [SENTINEL], {SENTINEL: 1},
    # Well-formed pointers under a known root that point at no null field of the record.
    "/effective_request_settings/" + SENTINEL, "/service_identity/model_id", "/response_sha256",
    "/effective_request_settings/bounds/top_n/0", "/effective_request_settings/bounds/top_n/7",
])
def test_a_not_recorded_entry_is_checked_as_a_pointer_and_never_repeated(entry_value: Any) -> None:
    """The refusal used to print every entry that pointed at no null field, so a sentence or a credential
    appended to ``not_recorded`` came back in the message."""
    doc = request_document()
    doc["not_recorded"].append(entry_value)
    with pytest.raises(Refusal) as caught:
        nps.validate_request_record(doc)
    message = str(caught.value)
    assert caught.value.code == "not_recorded_pointer"
    assert SENTINEL not in message and FILLER not in message and "a" * 49 not in message
    assert "position(s) [1]" in message and "1 of the 2" in message
    # The builder passes the list on and gives the same refusal, also for entries it cannot sort.
    with pytest.raises(Refusal) as built:
        nps.request_record(**{**{k: v for k, v in request_document().items() if k != "schema_version"},
                              "not_recorded": doc["not_recorded"]})
    assert built.value.code == "not_recorded_pointer" and SENTINEL not in str(built.value)


def test_not_recorded_must_be_a_list_of_distinct_pointers() -> None:
    for value in (None, "/service_identity/instrument_revision", {"/service_identity/instrument_revision": 1}, 3):
        doc = {**request_document(), "not_recorded": value}
        assert code_of(lambda: nps.validate_request_record(doc)) == "not_recorded_pointer"
    twice = request_document()
    twice["not_recorded"] = twice["not_recorded"] * 2
    assert code_of(lambda: nps.validate_request_record(twice)) == "not_recorded_pointer"
    many = {**request_document(), "not_recorded": ["/service_identity/instrument_revision"] * 300}
    assert code_of(lambda: nps.validate_request_record(many)) == "not_recorded_pointer"
    # The pointer check runs before the settings are read: a record with both faults reports this one.
    both = request_document()
    both["not_recorded"].append(SENTINEL)
    both["effective_request_settings"]["api_key"] = "x"
    assert code_of(lambda: nps.validate_request_record(both)) == "not_recorded_pointer"


def request_refusal(change: Callable[[dict], None]) -> Refusal:
    doc = request_document()
    change(doc)
    with pytest.raises(Refusal) as caught:
        nps.validate_request_record(doc)
    return caught.value


@pytest.mark.parametrize("change", [
    lambda d: d["effective_request_settings"].update(note=SENTINEL),
    lambda d: d["effective_request_settings"].update(model_id=SENTINEL + " a b"),
    lambda d: d["effective_request_settings"].update(api_key=SENTINEL),
    lambda d: d["effective_request_settings"].update({SENTINEL + " a b": 1}),
    lambda d: d["effective_request_settings"].update(type=[SENTINEL, "a b"]),
    lambda d: d["effective_request_settings"].update(prompt_sha256=SENTINEL),
    lambda d: d["effective_request_settings"].update(max_tokens=SENTINEL),
    lambda d: d["service_identity"].update(service=[SENTINEL]),
    lambda d: d["service_identity"].update(service=SENTINEL + " a"),
    lambda d: d.update(response_sha256=SENTINEL + " a"),
    lambda d: d.update(retrieved_utc=SENTINEL + " a"),
    lambda d: d["endpoint"].update(path="/" + SENTINEL + " a"),
    lambda d: d["endpoint"].update(path="/api/" + SENTINEL + "?prompt=" + SENTINEL),
    lambda d: d["endpoint"].update(host=SENTINEL + " a"),
    lambda d: d["endpoint"].update(method=SENTINEL),
    lambda d: d["endpoint"].update({SENTINEL: 1}),
    lambda d: d.update(schema_version=SENTINEL),
    lambda d: d.update({SENTINEL: SENTINEL}),
    lambda d: d.update(effective_request_settings=SENTINEL),
    lambda d: d.update(service_identity=[SENTINEL]),
    lambda d: d.update(endpoint=SENTINEL),
    lambda d: d.update(not_recorded=[{SENTINEL: 1}]),
    lambda d: d.update(not_recorded=SENTINEL),
])
def test_no_refusal_of_a_request_record_repeats_a_value(change: Callable[[dict], None]) -> None:
    """docs/experiment_interface/neuronpedia.md says a refusal never repeats a value; this holds it to that."""
    assert SENTINEL not in str(request_refusal(change))


def test_a_record_nested_beyond_the_recursion_limit_is_a_refusal() -> None:
    node: Any = 1
    for _ in range(sys.getrecursionlimit() + 100):
        node = {"a": node}
    deep = request_document()
    deep["effective_request_settings"]["bounds"] = node
    assert code_of(lambda: nps.validate_request_record(deep)) == "invalid_input"


def test_the_endpoint_host_and_path_are_bounded() -> None:
    assert request_refusal(lambda d: d["endpoint"].update(path="/a" * 9)).code == "request_record"
    assert nps.validate_request_record({**request_document(), "endpoint": {
        "method": "GET", "host": "www.service.invalid", "path": "/a" * 8}})
    for host in ("a" * 64 + ".invalid", ".".join(["a"] * 9), "service..invalid", ".invalid", "service.invalid.",
                 "under_score.invalid", 5):
        assert request_refusal(lambda d: d["endpoint"].update(host=host)).code == "request_record", host
    # A host label that begins hf- is refused as well: an over-refusal the doc states.
    assert request_refusal(lambda d: d["endpoint"].update(host="hf-mirror.invalid")).code == "secret_in_record"


def test_a_token_shaped_path_segment_or_host_label_is_refused() -> None:
    """Regression (Codex, PR 167): the endpoint got the issuer-prefix screen only, so a long mixed run of
    letters and digits, refused as an id value, validated as a path segment and as a host label."""
    filler = "Ab3" * 9                                          # 27 characters, three character classes
    assert request_refusal(lambda d: d["effective_request_settings"].update(model_id=filler)).code == \
        "secret_in_record"                                      # the rule an id value already had
    for change in ({"path": f"/api/{filler}"}, {"path": f"/{filler}/graph"}, {"host": f"{filler.lower()}.invalid"},
                   {"host": f"www.{filler.lower()}.invalid"}, {"path": "/api/" + "a1" * 20}):
        caught = request_refusal(lambda d, change=change: d["endpoint"].update(change))
        assert caught.code == "secret_in_record", change
        assert filler not in str(caught) and filler.lower() not in str(caught)
    # Short segments, words and a 24-character run still validate.
    for path in ("/api/graph/new", "/api/lens/gemma-2-2b/12", "/" + "Ab3" * 8):
        assert nps.validate_request_record({**request_document(), "endpoint": {
            "method": "GET", "host": "www.service.invalid", "path": path}})


def test_refusals_of_the_other_records_repeat_no_value_that_failed_its_check(
        real: dict, fixture_registry: dict, explanations: dict, graph_ref: dict, tmp_path: Path) -> None:
    """Each case puts the sentinel where a value or a key fails a check, and reads the message."""
    def message(call: Callable[[], Any], code: str) -> str:
        with pytest.raises(Refusal) as caught:
            call()
        assert caught.value.code == code and SENTINEL not in str(caught.value), str(caught.value)
        return str(caught.value)

    text_key = SENTINEL + " a b"
    # Registry.
    message(lambda: nps.validate_registry(mutated(fixture_registry, FX_VERIFIED, lambda e: e.update(
        method=SENTINEL))), "unknown_method")
    message(lambda: nps.validate_registry(mutated(fixture_registry, FX_VERIFIED, lambda e: e["verification"].update(
        status=SENTINEL))), "verification_status")
    message(lambda: nps.validate_registry(mutated(fixture_registry, FX_VERIFIED, lambda e: e["not_recorded"].append(
        SENTINEL + " words"))), "not_recorded_pointer")
    # A superscript two passes str.isdigit and fails int(): it used to come back inside a ValueError text.
    message(lambda: nps.validate_registry(mutated(fixture_registry, FX_VERIFIED, lambda e: e["not_recorded"].append(
        "/site/layers/\u00b2"))), "not_recorded_pointer")
    unread = copy.deepcopy(real)
    unread["sources_not_read"] = [{"url": "https://exports.invalid/v1?X-Amz-Signature=" + SENTINEL,
                                   "attempted_utc_date": "2026-11-10", "result": "not read"}]
    assert "sources_not_read[0]" in message(lambda: nps.validate_registry(unread), "registry_entry")
    named = copy.deepcopy(entry(fixture_registry, FX_VERIFIED))
    named["registry_id"] = SENTINEL + " words"
    message(lambda: nps.build_link(named, 3, layer=1), "registry_entry")
    # resolve: the argument is reported by type.
    assert "got list" in message(lambda: nps.resolve([SENTINEL], "ica_component", registry=real), "invalid_input")
    message(lambda: nps.resolve("toy-model", SENTINEL, registry=real), "representation_type")
    # Explanation records.
    def explained(change: Callable[[dict], None]) -> Callable[[], Any]:
        doc = copy.deepcopy(explanations)
        change(doc)
        return lambda: nps.validate_feature_explanations(doc)
    counted = message(explained(lambda d: d["labels"][0].update({text_key: 1})), "explanation_record")
    assert "1 name(s) that are not short identifiers" in counted
    message(explained(lambda d: d["labels"][0].update({text_key + " score": 1})), "merged_score")
    message(explained(lambda d: d["labels"][0]["source"].update({text_key: "x"})), "explanation_record")
    message(explained(lambda d: d["quantities"].update({text_key: []})), "merged_score")
    message(explained(lambda d: d["quantities"]["lens_token_rank"][0].update(kind=SENTINEL)), "score_kind_mismatch")
    message(explained(lambda d: d["quantities"]["lens_token_rank"][0].update({text_key: 1})), "quantity_fields")
    message(explained(lambda d: d["not_recorded"].append(SENTINEL)), "not_recorded_pointer")
    message(lambda: nps.collect_quantity(SENTINEL, []), "score_kind_merge")
    message(lambda: nps.collect_quantity("lens_token_rank", [{"kind": SENTINEL}]), "score_kind_merge")
    # A key that is a short identifier is still named, so the message stays usable.
    assert "'confidence'" in str(code_and_text(explained(lambda d: d["labels"][0].update(confidence=0.9))))
    # Graph references and snapshot records.
    def referenced(change: Callable[[dict], None]) -> Callable[[], Any]:
        doc = copy.deepcopy(graph_ref)
        change(doc)
        return lambda: nps.validate_graph_reference(doc)
    message(referenced(lambda r: r.update({text_key: 1})), "graph_ref_keys")
    message(referenced(lambda r: r["graph"].update({text_key: SENTINEL})), "graph_ref_keys")
    message(referenced(lambda r: r["model"].update(hf_id=SENTINEL + " a")), "free_text_in_reference")
    message(referenced(lambda r: r.update(not_recorded=[SENTINEL])), "not_recorded_pointer")
    export = tmp_path / "export.jsonl"
    export.write_bytes(b"alpha\n")
    record = nps.record_snapshot(export, None, None)
    message(lambda: nps.verify_snapshot(export, {**record, "not_recorded": record["not_recorded"] + [SENTINEL]}),
            "not_recorded_pointer")
    message(lambda: nps.verify_snapshot(export, {**record, "source_url": "https://x.invalid/?k=" + SENTINEL}),
            "snapshot_url")


def code_and_text(call: Callable[[], Any]) -> Refusal:
    with pytest.raises(Refusal) as caught:
        call()
    return caught.value


def test_the_engines_own_request_settings_validate_once_the_prompt_is_named_by_hash() -> None:
    """The lens request body the engine sends (scripts/jlens_readout.py) and the graph request's field names
    (medlang_circuits/graph_client.py:304-321), with the prompt and the slug replaced by hashes."""
    body = jlens_readout.lens_request_body("toy-model-hosted", "alpha", 8)
    assert set(body) == {"modelId", "prompt", "type", "topN", "temperature", "numCompletionTokens",
                         "filterNonWordTokens", "stream"}
    sent = request_document()
    sent["effective_request_settings"] = body
    assert code_of(lambda: nps.validate_request_record(sent)) == "prompt_text_in_record"    # as sent: refused
    body.pop("prompt")
    lens = request_document()
    lens["effective_request_settings"] = {**body, "prompt_sha256": "6" * 64}
    assert nps.validate_request_record(lens)["effective_request_settings"]["type"] == ["JACOBIAN_LENS"]
    graph = request_document()
    graph["effective_request_settings"] = {
        "modelId": "toy-model-hosted", "sourceSetName": "toy-transcoder-set", "prompt_sha256": "6" * 64,
        "slug_sha256": "5" * 64, "token_sha256": None, "maxNLogits": 10, "desiredLogitProb": 0.95,
        "nodeThreshold": 0.8, "edgeThreshold": 0.85, "maxFeatureNodes": 5000, "qkTopFraction": 0.5, "qkTopk": 4,
        "bounds": {"maxNLogits": [5, 15]}}
    graph["not_recorded"] = sorted(graph["not_recorded"] + ["/effective_request_settings/token_sha256"])
    assert nps.validate_request_record(graph)
    with_slug = copy.deepcopy(graph)
    with_slug["effective_request_settings"]["slug"] = "alpha-beta-tail-1"
    assert code_of(lambda: nps.validate_request_record(with_slug)) == "prompt_text_in_record"
    # The path is an id-only character class with a length cap per segment; the doc states what that leaves open.
    long_path = request_document()
    long_path["endpoint"]["path"] = "/api/toy/" + "a" * 65
    assert code_of(lambda: nps.validate_request_record(long_path)) == "request_record"


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


@pytest.mark.parametrize("change,code", [
    # A number, a rank or a selection marker inside a label.
    (lambda d: d["labels"][0].update(confidence=0.9), "explanation_record"),
    (lambda d: d["labels"][0].update(interpretability=0.93), "explanation_record"),
    (lambda d: d["labels"][0].update(clinical_outcome=0.4), "explanation_record"),
    (lambda d: d["labels"][0].update(rank=1, primary=True), "explanation_record"),
    (lambda d: d["labels"][0].update(selected=True), "explanation_record"),
    (lambda d: d["labels"][0].update(best=True), "explanation_record"),
    (lambda d: d["labels"][0].update(is_best_label=True), "explanation_record"),
    (lambda d: d["labels"][0].update(total_score=1.4), "merged_score"),
    (lambda d: d["labels"][0].update(feature_interpretability_score=0.5), "merged_score"),
    (lambda d: d["labels"][0].pop("flags"), "explanation_record"),
    # The same inside a label's source or scorer, and inside the scorer of a quantity record.
    (lambda d: d["labels"][0]["scorer"].update(score=0.91), "merged_score"),
    (lambda d: d["labels"][0]["scorer"].update(combined_score=0.91), "merged_score"),
    (lambda d: d["labels"][0]["scorer"].update(weight=0.91), "explanation_record"),
    (lambda d: d["labels"][0]["scorer"].update(version=0.91), "explanation_record"),
    (lambda d: d["labels"][0]["source"].update(overall_score=0.91), "merged_score"),
    (lambda d: d["labels"][0]["source"].update(rank=1), "explanation_record"),
    (lambda d: d["labels"][0]["source"].update(version=0.91), "explanation_record"),
    (lambda d: d["labels"][0]["source"].pop("explanation_type"), "explanation_record"),
    (lambda d: d["quantities"]["feature_interpretability_score"][0]["scorer"].update(score=0.5), "merged_score"),
    (lambda d: d["quantities"]["feature_interpretability_score"][0]["scorer"].update(combined=0.9),
     "quantity_fields"),
    (lambda d: d["quantities"]["label_prediction_score"][0]["scorer"].update(version=0.9), "quantity_fields"),
    # A flag is one of the known flags: a flag cannot promote a label or select it.
    (lambda d: d["labels"][0].update(flags=["verified_clinical_concept"]), "explanation_record"),
    (lambda d: d["labels"][0].update(flags=["selected"]), "explanation_record"),
    # A label that carries its token list needs the flag, whatever basis it declares.
    (lambda d: d["labels"][2].update(basis="human_written", flags=[]), "token_list_label"),
    (lambda d: d["labels"][2].update(basis="activation_examples", flags=[]), "token_list_label"),
    (lambda d: d["labels"][2].update(tokens=[]), "token_list_label"),
    (lambda d: d["labels"][2].update(tokens=["alpha", 0.9]), "token_list_label"),
])
def test_label_source_and_scorer_key_sets_are_closed(explanations: dict, change: Callable[[dict], None],
                                                     code: str) -> None:
    assert nps.validate_feature_explanations(copy.deepcopy(explanations))
    change(explanations)
    assert code_of(lambda: nps.validate_feature_explanations(explanations)) == code


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
                                                      "registry_checked": False, "model_revision_compared": False}
    assert nps.validate_graph_reference(graph_ref, fixture_registry) == {
        "status": "validated", "native_retained": True, "registry_checked": True, "model_revision_compared": True}
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
    # The entry pins revision 1111...1. A graph traced on another commit of the same model is another graph.
    (lambda r: r["model"].update(revision="9" * 40), "graph_ref_identity"),
])
def test_graph_reference_is_checked_against_the_registry_entry(graph_ref: dict, fixture_registry: dict,
                                                               change: Callable[[dict], None], code: str) -> None:
    change(graph_ref)
    assert code_of(lambda: nps.validate_graph_reference(graph_ref, fixture_registry)) == code


def test_a_graph_reference_without_a_revision_says_the_revision_was_not_compared(graph_ref: dict,
                                                                                fixture_registry: dict) -> None:
    assert entry(fixture_registry, FX_TRANSCODER)["model"]["revision"] == "1" * 40 == graph_ref["model"]["revision"]
    graph_ref["model"]["revision"] = None
    # A null revision must be listed; unlisted, it is refused before the registry is consulted.
    assert code_of(lambda: nps.validate_graph_reference(graph_ref, fixture_registry)) == "silent_missing_provenance"
    graph_ref["not_recorded"] = ["/model/revision"]
    assert nps.validate_graph_reference(graph_ref, fixture_registry) == {
        "status": "validated", "native_retained": True, "registry_checked": True, "model_revision_compared": False}
    # A revision the entry does not pin cannot be confirmed by it either.
    unpinned = mutated(fixture_registry, FX_TRANSCODER, lambda e: (
        e["model"].update(revision=None), e["verification"].update(status="unverified"),
        e.update(links_enabled=False), e["not_recorded"].append("/model/revision")))
    graph_ref["model"]["revision"], graph_ref["not_recorded"] = "1" * 40, []
    assert code_of(lambda: nps.validate_graph_reference(graph_ref, unpinned)) == "graph_ref_identity"
