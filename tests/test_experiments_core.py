"""Experiment core: protocol, capability matrix, adapters, planner, envelope.

Offline. Synthetic placeholders only: no model, no service, no measurement, no text from data/simulated or
trace_out. Expected numbers are worked out by hand in the comments beside them; none is produced by the code
under test. These tests show that the contract code does what it says on toy inputs. They are not evidence
that any real-model run agrees with it.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from scripts import exploratory_methods, logits_eval
from scripts.experiments import adapters, capabilities, common, envelope, planner
from scripts.experiments.adapters import behavior_fixture, readout_exploratory
from scripts.experiments.common import Refusal
from scripts.experiments.protocol import validate_protocol
from scripts.experiments.store import RunStore

ENGINE = Path(__file__).resolve().parents[1]
FIXTURES = ENGINE / "tests" / "fixtures" / "experiments"
ABSENT = {"ica_lens": "scripts.experiments.adapters.module_that_does_not_exist"}
PLACEHOLDER_PROMPTS = ("alpha tail", "beta tail", "gamma tail", "alpha beta tail", "delta alpha tail")


def canonical(value: object) -> str:
    """The canonical digest rule, restated with the stdlib so the tests do not lean on the package for it."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def protocol() -> dict:
    return load("protocol_synthetic.json")


@pytest.fixture(scope="module")
def matrix() -> dict:
    return capabilities.load_matrix()


def real_like(protocol: dict) -> dict:
    """The fixture protocol relabelled as non-synthetic with a legacy join per family. Still placeholders."""
    doc = copy.deepcopy(protocol)
    doc["synthetic"] = False
    doc["evidence"] = {"evidence_class": "exploratory_post_registration", "clinical_review": "domain_review_pending",
                       "visibility": "restricted", "restriction_reasons": ["placeholder_restriction"]}
    doc["model"]["backend"] = "cpu_transformers"
    for number, family in enumerate(doc["case_families"], start=1):
        family["legacy_join"] = {"batch": "placeholder_batch", "batch_index": number, "model": "toy-model"}
    return doc


def refusal(doc: object, **kwargs: object) -> str:
    with pytest.raises(Refusal) as caught:
        validate_protocol(doc, **kwargs)
    return caught.value.code


def set_variant(doc: dict, family: int, variant: str, token_ids: list[int], words: str) -> None:
    doc["case_families"][family]["variants"][variant] = {
        "prompt": words, "prompt_sha256": hashlib.sha256(words.encode()).hexdigest(),
        "token_ids": token_ids, "token_sha256": canonical(token_ids)}


# ------------------------------------------------------------------------------------------------ common

def test_common_reuses_the_exploratory_contract_by_import() -> None:
    assert common.Refusal is exploratory_methods.Refusal
    assert common.digest is exploratory_methods.digest
    assert common.prompt_digest is exploratory_methods.prompt_digest
    assert common.require is exploratory_methods.require


def test_digest_is_the_ensure_ascii_false_form() -> None:
    # '"é"' in UTF-8 is 22 c3 a9 22; the baseline module's digest would hash the six-byte escape instead.
    assert common.digest("é") == hashlib.sha256(b'"\xc3\xa9"').hexdigest()
    assert common.digest("é") != hashlib.sha256(json.dumps("é").encode()).hexdigest()


def test_committed_fixtures_are_what_the_generator_writes() -> None:
    spec = importlib.util.spec_from_file_location("pw_experiment_fixture_builder", FIXTURES / "build_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, document in module.build_all().items():
        assert (FIXTURES / name).read_text(encoding="utf-8") == module.render(document), name


def test_fixtures_hold_placeholders_only() -> None:
    vocabulary = {"alpha", "beta", "gamma", "delta", "tail", "omega", "%", "/"}
    for family in load("protocol_synthetic.json")["case_families"]:
        assert family["review_status"] == "synthetic_placeholder" and family["legacy_join"] is None
        for entry in family["variants"].values():
            assert set(entry["prompt"].split()) <= vocabulary


@pytest.mark.parametrize("name,schema_id", [
    ("protocol", "patientwords.experiment-protocol/1"), ("plan", "patientwords.experiment-plan/1"),
    ("envelope", "patientwords.experiment-envelope/1"), ("bundle", "patientwords.experiment-bundle/1"),
    ("capability_matrix", "patientwords.capability-matrix/1")])
def test_schemas_use_only_the_keywords_the_repository_validator_executes(name: str, schema_id: str) -> None:
    from scripts.frontend_contract_schema import check_schema_subset

    schema = common.load_schema(name)
    assert schema["$id"] == schema_id
    errors: list[tuple[str, str]] = []
    # The audit pass raises ValueError on any keyword outside the supported subset, before it visits the value.
    check_schema_subset(lambda _a, where, why: errors.append((where, why)), name, {}, schema)
    assert errors and all(why == "missing required key" for _where, why in errors)


# ---------------------------------------------------------------------------------------------- protocol

def test_fixture_protocol_validates(protocol: dict) -> None:
    result = validate_protocol(protocol)
    assert result["status"] == "validated"
    assert result["protocol_sha256"] == canonical(protocol)
    assert result["families_by_split"] == {"discovery": 1, "validation": 1, "fresh_test": 1}
    assert result["methods"] == ["behavior_next_token", "logit_lens", "j_lens", "jpp"]
    for family in protocol["case_families"]:
        assert {"clinical", "colloquial", "normalized"} <= set(family["variants"])


def test_optional_variants_are_accepted_and_unknown_ones_refused(protocol: dict) -> None:
    set_variant(protocol, 0, "within_register_paraphrase", [0, 0, 4], "alpha alpha tail")
    set_variant(protocol, 0, "changed_fact_control", [2, 2, 4], "gamma gamma tail")
    assert validate_protocol(protocol)["status"] == "validated"
    set_variant(protocol, 0, "slang", [1, 1, 4], "beta beta tail")
    assert refusal(protocol) == "unknown_variant"


def mutate_schema_version(doc: dict) -> None:
    doc["schema_version"] = "patientwords.exploratory/1"


def mutate_seed_absent(doc: dict) -> None:
    del doc["seed"]


def mutate_seed_bool(doc: dict) -> None:
    doc["seed"] = True


def mutate_prompt_hash(doc: dict) -> None:
    doc["case_families"][0]["variants"]["clinical"]["prompt"] = "alpha alpha tail"


def mutate_token_hash(doc: dict) -> None:
    doc["case_families"][0]["variants"]["clinical"]["token_ids"] = [0, 4, 4]


def mutate_revision_absent(doc: dict) -> None:
    del doc["model"]["revision"]


def mutate_revision_branch_name(doc: dict) -> None:
    doc.update(real_like(doc))
    doc["model"]["tokenizer_revision"] = "main"


def mutate_family_in_two_splits(doc: dict) -> None:
    doc["case_families"][1]["family_id"] = "fam-1"


def mutate_prompt_in_two_splits(doc: dict) -> None:
    set_variant(doc, 1, "clinical", [0, 4], "alpha tail")


def mutate_duplicate_family(doc: dict) -> None:
    doc["case_families"][1]["family_id"] = "fam-1"
    doc["case_families"][1]["split"] = "discovery"


def mutate_unknown_method(doc: dict) -> None:
    doc["methods"].append({"id": "understanding_score"})


def mutate_layer_outside_model(doc: dict) -> None:
    doc["methods"][1]["layers"] = [0, 3]


def mutate_layer_duplicate(doc: dict) -> None:
    doc["methods"][1]["layers"] = [1, 1]


def mutate_layer_base_absent(doc: dict) -> None:
    del doc["methods"][1]["layer_index_base"]


def mutate_layer_base_one(doc: dict) -> None:
    doc["methods"][1]["layer_index_base"] = 1


def mutate_variant_missing(doc: dict) -> None:
    del doc["case_families"][1]["variants"]["normalized"]


def ica_method(**basis: object) -> dict:
    return {"id": "ica_lens", "capture_site": "block_output", "layer_index_base": 0, "layers": [1],
            "positions": "last", "basis": {"manifest_sha256": "a" * 64, "fit_split": "discovery",
                                           "preprocessing": "none", **basis}}


def mutate_ica_fit_on_validation(doc: dict) -> None:
    doc["methods"].append(ica_method(fit_split="validation"))


def mutate_ica_selects_on_fresh_test(doc: dict) -> None:
    doc["methods"].append(ica_method(selection_families=["fam-1", "fam-3"]))


def mutate_ica_profiles_on_validation(doc: dict) -> None:
    doc["methods"].append(ica_method(profile_families=["fam-2"]))


def mutate_synthetic_with_measured_class(doc: dict) -> None:
    doc["evidence"]["evidence_class"] = "registered_cohort"


def mutate_measured_with_synthetic_class(doc: dict) -> None:
    doc["synthetic"] = False


def mutate_synthetic_with_legacy_join(doc: dict) -> None:
    doc["case_families"][0]["legacy_join"] = {"batch": "placeholder_batch", "batch_index": 1, "model": "toy-model"}


def mutate_not_an_object(doc: dict) -> None:
    doc["case_families"] = "fam-1"


def mutate_primary_endpoint(doc: dict) -> None:
    doc["primary_endpoint"]["target"] = "t9"


def mutate_replicates(doc: dict) -> None:
    doc["replicates"] = 0


@pytest.mark.parametrize("mutation,code", [
    (mutate_schema_version, "schema_version"),
    (mutate_seed_absent, "missing_seed"), (mutate_seed_bool, "missing_seed"),
    (mutate_prompt_hash, "prompt_hash"), (mutate_token_hash, "token_hash"),
    (mutate_revision_absent, "missing_revision"), (mutate_revision_branch_name, "missing_revision"),
    (mutate_family_in_two_splits, "split_leakage"), (mutate_prompt_in_two_splits, "split_leakage"),
    (mutate_duplicate_family, "duplicate_family"),
    (mutate_unknown_method, "unknown_method"),
    (mutate_layer_outside_model, "layer_metadata"), (mutate_layer_duplicate, "layer_metadata"),
    (mutate_layer_base_absent, "layer_metadata"), (mutate_layer_base_one, "layer_metadata"),
    (mutate_variant_missing, "variant_missing"),
    (mutate_ica_fit_on_validation, "ica_basis_split"), (mutate_ica_selects_on_fresh_test, "ica_basis_split"),
    (mutate_ica_profiles_on_validation, "ica_basis_split"),
    (mutate_synthetic_with_measured_class, "synthetic_label"),
    (mutate_measured_with_synthetic_class, "synthetic_label"),
    (mutate_synthetic_with_legacy_join, "synthetic_label"),
    (mutate_not_an_object, "invalid_input"),
    (mutate_primary_endpoint, "primary_endpoint"), (mutate_replicates, "replicates"),
])
def test_protocol_named_refusals(protocol: dict, mutation: object, code: str) -> None:
    mutation(protocol)
    assert refusal(protocol, row_restriction=lambda *_: None) == code


def test_ica_basis_fit_on_discovery_is_accepted(protocol: dict) -> None:
    protocol["methods"].append(ica_method(fit_families=["fam-1"], selection_families=["fam-1"]))
    assert "ica_lens" in validate_protocol(protocol)["methods"]


def test_fixture_backend_needs_the_revision_fields_but_not_forty_hex(protocol: dict) -> None:
    protocol["model"]["revision"] = "toy-revision"
    protocol["model"]["tokenizer_revision"] = "toy-revision"
    assert validate_protocol(protocol)["status"] == "validated"


def test_legacy_join_in_two_splits_is_leakage(protocol: dict) -> None:
    doc = real_like(protocol)
    doc["case_families"][1]["legacy_join"] = dict(doc["case_families"][0]["legacy_join"])
    assert refusal(doc, row_restriction=lambda *_: None) == "split_leakage"


def test_sealed_legacy_row_is_refused_without_repeating_the_prompt(protocol: dict) -> None:
    doc = real_like(protocol)
    seen = []

    def sealed_second_row(batch: str, index: int, prompt: str) -> str | None:
        seen.append((batch, index, prompt))
        return "sealed_holdout" if index == 2 else None

    with pytest.raises(Refusal) as caught:
        validate_protocol(doc, row_restriction=sealed_second_row)
    assert caught.value.code == "holdout_refusal"
    # The row check receives the clinical variant's prompt; the refusal names the row by batch and index only.
    assert seen[-1] == ("placeholder_batch", 2, "alpha beta tail")
    assert [call for call in seen if call[0] is not None] == [("placeholder_batch", 1, "alpha tail"),
                                                              ("placeholder_batch", 2, "alpha beta tail")]
    assert "alpha beta tail" not in str(caught.value) and "placeholder_batch, 2" in str(caught.value)
    assert validate_protocol(doc, row_restriction=lambda *_: None)["synthetic"] is False


def seal_stub(sealed_prompt: str, seen: list) -> object:
    """A seal checker that knows one placeholder string as sealed, wherever it occurs. No sealed text is read."""
    def check(batch: str | None, index: int | None, prompt: str | None) -> str | None:
        seen.append((batch, index, prompt))
        return "sealed_holdout" if prompt == sealed_prompt else None
    return check


def test_the_seal_is_checked_for_a_family_without_a_legacy_join(protocol: dict) -> None:
    # Regression: the check sat inside `if legacy_join is not None`, so a join-less family was never asked.
    doc = real_like(protocol)
    for family in doc["case_families"]:
        family["legacy_join"] = None
    seen: list = []
    assert refusal(doc, row_restriction=seal_stub("alpha tail", seen)) == "holdout_refusal"   # fam-1 clinical
    assert seen == [(None, None, "alpha tail")]
    seen.clear()
    assert validate_protocol(doc, row_restriction=seal_stub("no such prompt", seen))["status"] == "validated"
    # Every variant prompt of every family is asked once, with no batch and no index.
    prompts = sorted(entry["prompt"] for family in doc["case_families"] for entry in family["variants"].values())
    assert sorted(call[2] for call in seen) == prompts and len(prompts) == 9
    assert {call[:2] for call in seen} == {(None, None)}


@pytest.mark.parametrize("joined", [True, False])
@pytest.mark.parametrize("variant", ["colloquial", "normalized"])
def test_a_sealed_prompt_in_any_variant_is_refused_without_repeating_it(protocol: dict, joined: bool,
                                                                        variant: str) -> None:
    # Regression: only variants["clinical"] reached the checker, so a sealed phrase in another slot validated.
    doc = real_like(protocol)
    if not joined:
        for family in doc["case_families"]:
            family["legacy_join"] = None
    sealed_prompt = doc["case_families"][1]["variants"][variant]["prompt"]
    with pytest.raises(Refusal) as caught:
        validate_protocol(doc, row_restriction=seal_stub(sealed_prompt, []))
    assert caught.value.code == "holdout_refusal"
    assert sealed_prompt not in str(caught.value) and f"fam-2:{variant}" in str(caught.value)
    with pytest.raises(Refusal) as planned:
        planner.build_plan(doc, capabilities.load_matrix(), row_restriction=seal_stub(sealed_prompt, []))
    assert planned.value.code == "holdout_refusal"


def test_a_synthetic_protocol_never_reads_the_seal(protocol: dict) -> None:
    seen: list = []
    assert validate_protocol(protocol, row_restriction=seal_stub("alpha tail", seen))["synthetic"] is True
    assert seen == []


def test_a_synthetic_protocol_cannot_declare_a_legacy_join_so_skipping_its_seal_check_hides_no_row(protocol: dict) -> None:
    """The seal check is skipped for a synthetic protocol. That is sound only because such a protocol is
    refused before it can name a real row."""
    doc = copy.deepcopy(protocol)
    doc["case_families"][0]["legacy_join"] = {"batch": "placeholder_batch", "batch_index": 1, "model": "toy-model"}
    assert refusal(doc, row_restriction=seal_stub("no such placeholder", [])) == "synthetic_label"


def test_default_seal_check_is_results_policy_row_restriction(protocol: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import results_policy

    calls = []
    monkeypatch.setattr(results_policy, "row_restriction", lambda *args: calls.append(args))
    validate_protocol(real_like(protocol))
    # One row check per joined family, then the two other variants of that family as bare phrases.
    assert [call[:2] for call in calls if call[0] is not None] == [
        ("placeholder_batch", 1), ("placeholder_batch", 2), ("placeholder_batch", 3)]
    assert len([call for call in calls if call[:2] == (None, None)]) == 6 and len(calls) == 9


def test_unevaluable_seal_is_a_configuration_error_not_a_refusal(protocol: dict) -> None:
    from scripts import results_policy

    def broken(*_: object) -> None:
        raise results_policy.SealError("placeholder: seal inputs unreadable")

    with pytest.raises(results_policy.SealError):
        validate_protocol(real_like(protocol), row_restriction=broken)


def with_evidence(protocol: dict, **evidence: object) -> dict:
    doc = real_like(protocol)
    doc["evidence"] = {"evidence_class": "exploratory_post_registration", "clinical_review": "domain_review_pending",
                       **evidence}
    return doc


def test_protocol_evidence_labels_follow_the_open_results_vocabulary(protocol: dict) -> None:
    # Regression: any non-empty string was accepted, including "public" with a restriction reason.
    from scripts import results_policy

    no_seal = {"row_restriction": lambda *_: None}
    declared = sorted(results_policy.load_policy(results_policy.ENGINE / results_policy.POLICY_PATH).doc["memberships"])
    assert "study-interim/1" in declared
    accepted = [
        {"visibility": "public"},
        {"visibility": "public", "restriction_reasons": [], "analysis_memberships": declared},
        {"visibility": "restricted", "restriction_reasons": ["placeholder_restriction"]},
        {"visibility": "not_published"},
    ]
    for evidence in accepted:
        assert validate_protocol(with_evidence(protocol, **evidence), **no_seal)["status"] == "validated"
    refused = [
        {},                                                                           # visibility not stated
        {"visibility": "whatever"},
        {"visibility": "public", "restriction_reasons": ["placeholder_restriction"]},
        {"visibility": "restricted"},
        {"visibility": "restricted", "restriction_reasons": []},
        {"visibility": "restricted", "restriction_reasons": [""]},
        {"visibility": "public", "analysis_memberships": ["placeholder-membership/9"]},
    ]
    for evidence in refused:
        assert refusal(with_evidence(protocol, **evidence), **no_seal) == "evidence_fields", evidence


def test_a_synthetic_protocol_is_not_published_and_joins_no_membership(protocol: dict) -> None:
    protocol["evidence"]["visibility"] = "public"
    assert refusal(protocol) == "synthetic_label"
    protocol["evidence"]["visibility"] = "not_published"
    assert validate_protocol(protocol)["status"] == "validated"
    protocol["evidence"]["analysis_memberships"] = ["study-interim/1"]
    assert refusal(protocol) == "synthetic_label"


# ---------------------------------------------------------------------------------------- capability matrix

def find(matrix: dict, **want: object) -> list[dict]:
    def match(row: dict) -> bool:
        return all((row["model"].get(k[6:]) if k.startswith("model_") else row.get(k)) == v for k, v in want.items())
    return [row for row in matrix["rows"] if match(row)]


def test_matrix_statuses_are_six_ordered_words(matrix: dict) -> None:
    assert matrix["status_order"] == ["unsupported", "architecture_supported", "artifact_available_identity_unknown",
                                      "artifact_available", "runtime_verified_offline_fixture", "parity_passed"]
    assert capabilities.status_rank("architecture_supported") < capabilities.status_rank("parity_passed")
    assert {row["status"] for row in matrix["rows"]} <= set(matrix["status_order"])


def test_cpu_logits_rows_carry_the_registry_pins(matrix: dict) -> None:
    rows = {row["model"]["study_id"]: row for row in find(matrix, method="behavior_next_token",
                                                          backend="cpu_transformers")}
    assert set(rows) == set(logits_eval.HF_REVISIONS)
    for short, row in rows.items():
        assert row["model"] == {"study_id": short, "hf_id": logits_eval.HF_IDS[short],
                                "revision": logits_eval.HF_REVISIONS[short]}
        assert row["status"] == "artifact_available" and row["dtype"] == "bfloat16"


def test_no_row_claims_parity_and_the_interp_engine_row_states_the_agreement_numbers(matrix: dict) -> None:
    # Regression: this row was parity_passed on an audit that records no pass criterion and no verdict.
    assert find(matrix, status="parity_passed") == []
    assert "parity_passed" in matrix["status_order"]                     # the word stays in the vocabulary
    row, = find(matrix, model_study_id="gemma-2-2b", backend="cpu_interp_engine")
    assert (row["status"], row["dtype"], row["model"]["revision"]) == ("artifact_available", "float32", None)
    assert "parity_record" not in row
    report = json.loads((ENGINE / "ops" / "backend_agreement_interp_vs_hosted_20260904.json").read_text("utf-8"))
    assert not [key for key in report if "pass" in key or "verdict" in key]
    note = row["status_note"]
    # The numbers in the note are the report's own.
    assert (report["probability"]["n"], report["penalty"]["n"]) == (71, 29) and "71 of 100" in note
    for value in (report["probability"]["mean"], report["probability"]["median"], report["probability"]["max"],
                  report["penalty"]["max"], report["thresholds"]["near"], report["thresholds"]["far"]):
        assert str(value) in note, value
    censored = report["censoring"]
    assert (censored["clinical"]["reference_null_candidate_measured"],
            censored["patient"]["reference_null_candidate_measured"]) == (8, 21)
    assert "8 clinical and 21 patient" in note and "no pass criterion" in note
    assert {item["source"].split(" (")[0] for item in row["evidence"]} == {
        "docs/backend_agreement_20260903.md", "ops/backend_agreement_interp_vs_hosted_20260904.json"}
    # The bfloat16 lane of the same model has a recorded audit that did not pass per pair.
    assert find(matrix, model_study_id="gemma-2-2b", backend="cpu_transformers")[0]["status"] == "artifact_available"


def test_hosted_graph_rows_with_nothing_pinned_are_identity_unknown(matrix: dict) -> None:
    # Regression: both rows were artifact_available with model revision, artifact revision and hash all null.
    rows = find(matrix, method="attribution_graph", backend="hosted_neuronpedia")
    assert sorted(r["model"]["study_id"] for r in rows) == ["gemma-2-2b", "qwen3-4b"]
    for row in rows:
        assert row["model"]["revision"] is None and row["artifact"]["revision"] is None
        assert row["artifact"]["sha256"] is None
        assert row["status"] == "artifact_available_identity_unknown"
    # No row above identity_unknown is without a model revision, except the interp-engine row, whose note says so.
    unpinned = [r for r in matrix["rows"] if r["model"]["revision"] is None
                and capabilities.status_rank(r["status"]) > capabilities.status_rank("artifact_available_identity_unknown")]
    assert [(r["model"]["study_id"], r["backend"]) for r in unpinned] == [("gemma-2-2b", "cpu_interp_engine")]


def test_a_row_without_a_revision_never_answers_above_artifact_available_for_a_named_revision() -> None:
    # Regression: lookup returned parity_passed from a null-revision row for any revision asked.
    row = {"model": {"study_id": "toy-model", "hf_id": "fixture/toy-model", "revision": None},
           "method": "behavior_next_token", "backend": "cpu_interp_engine", "dtype": None, "artifact": None,
           "status": "parity_passed", "status_note": "placeholder note",
           "evidence": [{"source": "placeholder", "date": "2026-11-10"}],
           "parity_record": {"source": "placeholder", "date": "2026-11-10", "scope": "placeholder"}}
    asked = capabilities.lookup(f"fixture/toy-model@{'f' * 40}", "behavior_next_token", "cpu_interp_engine", rows=[row])
    assert (asked["status"], asked["row_status"], asked["status_capped"]) == ("artifact_available", "parity_passed", True)
    assert asked["revision_match"] == "row_revision_not_recorded" and asked["matched"] is True
    assert "records no model revision" in asked["status_note"] and "placeholder note" in asked["status_note"]
    # A question that names no revision gets the row as it is, and so does a row pinned to the asked revision.
    bare = capabilities.lookup("fixture/toy-model", "behavior_next_token", "cpu_interp_engine", rows=[row])
    assert (bare["status"], bare["status_capped"], bare["revision_match"]) == ("parity_passed", False, "exact")
    pinned = {**row, "model": {**row["model"], "revision": "f" * 40}}
    exact = capabilities.lookup(f"fixture/toy-model@{'f' * 40}", "behavior_next_token", "cpu_interp_engine",
                                rows=[pinned])
    assert (exact["status"], exact["status_capped"], exact["revision_match"]) == ("parity_passed", False, "exact")
    # A weaker status is not raised to the ceiling.
    weak = capabilities.lookup(f"fixture/toy-model@{'f' * 40}", "behavior_next_token", "cpu_interp_engine",
                               rows=[{**row, "status": "architecture_supported"}])
    assert (weak["status"], weak["status_capped"]) == ("architecture_supported", False)


def test_matrix_holds_the_rows_the_design_names(matrix: dict) -> None:
    graphs = {r["model"]["study_id"]: r for r in find(matrix, method="attribution_graph")}
    assert graphs["gemma-2-2b"]["artifact"]["id"] == "gemmascope-transcoder-16k"
    assert graphs["gemma-2-2b"]["artifact"]["calibration"] == "calibrated_reference"
    assert graphs["qwen3-4b"]["artifact"]["id"] == "transcoder-hp"
    assert graphs["qwen3-4b"]["artifact"]["calibration"] == "not_calibrated"
    # The released ICA basis is cited where the fork names its Hugging Face id, not at a local fit command.
    released = find(matrix, method="ica_lens")
    cited = [e["source"] for r in released if r["artifact"] and r["artifact"]["id"] == "sida/icalens-qwen3.5-2b-ultrachat-1m"
             for e in r["evidence"]]
    assert cited and all(source.endswith(": README.md:53") for source in cited)
    hosted_lens = find(matrix, method="j_lens", backend="hosted_neuronpedia")
    assert {r["model"]["study_id"] for r in hosted_lens} == {"gemma-2-2b", "gemma-2-2b-it"}
    assert all(r["status"] == "artifact_available_identity_unknown" and r["model"]["revision"] is None
               for r in hosted_lens)
    jpp = find(matrix, method="jpp", model_study_id="qwen3-4b")[0]
    assert jpp["status"] == "artifact_available_identity_unknown"
    assert jpp["artifact"]["fit_model_revision"] is None and jpp["artifact"]["fit_tokenizer_revision"] is None
    assert jpp["artifact"]["sha256"] == "893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d"
    ica = find(matrix, method="ica_lens", backend="cpu_transformers")
    assert {r["artifact"]["id"] for r in ica if r["artifact"]} >= {"sida/icalens-gemma-2-2b-pile10k"}
    assert all(r["status"] != "parity_passed" and r["status"] != "artifact_available" for r in ica)
    alias = find(matrix, method="ica_lens", model_study_id="qwen3.5-2b-base")[0]
    assert alias["aliases"] == [{"namespace": "neuronpedia", "id": "qwen3.5-2b-pt", "verified": False,
                                 "note": "alias only; the checkpoint behind the Neuronpedia id was not verified"}]
    assert alias["status"] == "architecture_supported"
    toy = {r["method"]: r["status"] for r in find(matrix, model_hf_id="fixture/toy-model")}
    # The ica_lens row was written before the ICA adapter existed; it may be raised once that adapter's own
    # tests pass, and never above the offline-fixture status.
    assert toy.pop("ica_lens") in ("architecture_supported", "runtime_verified_offline_fixture")
    assert toy == {"behavior_next_token": "runtime_verified_offline_fixture",
                   "logit_lens": "runtime_verified_offline_fixture", "j_lens": "unsupported",
                   "jpp": "artifact_available_identity_unknown"}


def test_every_row_cites_evidence_and_engine_paths_exist(matrix: dict) -> None:
    for row in matrix["rows"]:
        assert row["evidence"] and row["status_note"]
        for item in row["evidence"]:
            source = item["source"].split(" (")[0]
            if not source.startswith("michaeldgreenphd/"):
                assert (ENGINE / source).exists(), source


def test_lookup_reports_an_absent_combination_as_unsupported(matrix: dict) -> None:
    answer = capabilities.lookup(common.FIXTURE_MODEL, "attribution_graph", "fixture", matrix=matrix)
    assert answer["status"] == "unsupported" and answer["matched"] is False
    assert "no capability row" in answer["status_note"]
    with pytest.raises(Refusal) as caught:
        capabilities.lookup(common.FIXTURE_MODEL, "understanding_score", "fixture", matrix=matrix)
    assert caught.value.code == "unknown_method"


def test_lookup_uses_exact_revision_first_and_says_when_none_is_recorded(matrix: dict) -> None:
    pin = logits_eval.HF_REVISIONS["gemma-2-2b"]
    exact = capabilities.lookup(f"google/gemma-2-2b@{pin}", "behavior_next_token", "cpu_transformers",
                                dtype="bfloat16", matrix=matrix)
    assert (exact["status"], exact["revision_match"]) == ("artifact_available", "exact")
    hosted = capabilities.lookup({"hf_id": "google/gemma-2-2b", "revision": pin}, "j_lens", "hosted_neuronpedia",
                                 matrix=matrix)
    assert hosted["status"] == "artifact_available_identity_unknown"
    assert hosted["revision_match"] == "row_revision_not_recorded"
    other = capabilities.lookup(f"google/gemma-2-2b@{'9' * 40}", "behavior_next_token", "cpu_transformers",
                                matrix=matrix)
    assert other["status"] == "unsupported"


def test_lookup_answers_an_ambiguous_question_with_the_weakest_status() -> None:
    def row(status: str, artifact: str) -> dict:
        return {"model": dict(common.FIXTURE_MODEL), "method": "jpp", "backend": "fixture", "dtype": None,
                "artifact": {"id": artifact}, "status": status, "status_note": "placeholder",
                "evidence": [{"source": "placeholder", "date": "2026-11-10"}]}

    rows = [row("artifact_available", "lens-a"), row("artifact_available_identity_unknown", "lens-b")]
    assert capabilities.lookup(common.FIXTURE_MODEL, "jpp", "fixture", rows=rows)["status"] == \
        "artifact_available_identity_unknown"
    named = capabilities.lookup(common.FIXTURE_MODEL, "jpp", "fixture", "lens-a", rows=rows)
    assert (named["status"], named["ambiguous"]) == ("artifact_available", False)
    assert capabilities.lookup(common.FIXTURE_MODEL, "jpp", "fixture", "lens-c", rows=rows)["matched"] is False


def matrix_with(matrix: dict, **changes: object) -> dict:
    doc = copy.deepcopy(matrix)
    doc["rows"][0].update(changes)
    return doc


def test_matrix_refusals(matrix: dict) -> None:
    def code(doc: dict) -> str:
        with pytest.raises(Refusal) as caught:
            capabilities.validate_matrix(doc)
        return caught.value.code

    assert code(matrix_with(matrix, status="parity_passed")) == "parity_without_record"
    assert code(matrix_with(matrix, status="verified")) == "capability_status"
    assert code(matrix_with(matrix, evidence=[])) == "capability_evidence"
    assert code(matrix_with(matrix, evidence=[{"source": "x", "date": "November 2026"}])) == "capability_evidence"
    duplicated = copy.deepcopy(matrix)
    duplicated["rows"].append(copy.deepcopy(duplicated["rows"][0]))
    assert code(duplicated) == "duplicate_row"
    assert code({**matrix, "schema_version": "patientwords.capability-matrix/2"}) == "schema_version"


def test_an_adapter_may_declare_fixture_rows_only() -> None:
    base = behavior_fixture.ADAPTER.capabilities()[0]
    assert capabilities.check_adapter_rows([base], "m")[0]["declared_by"] == "m"
    for change in ({"status": "parity_passed", "parity_record": {"source": "s", "date": "2026-11-10", "scope": "x"}},
                   {"backend": "cpu_transformers"}):
        with pytest.raises(Refusal) as caught:
            capabilities.check_adapter_rows([{**base, **change}], "m")
        assert caught.value.code == "adapter_capability_scope"


# ---------------------------------------------------------------------------------------------- adapters

def test_registry_names_the_ica_module_and_loads_lazily() -> None:
    assert adapters.ADAPTER_MODULES["ica_lens"] == "scripts.experiments.adapters.ica"
    assert adapters.adapter_status("behavior_next_token") == ("present", None)
    assert adapters.adapter_status("logit_lens") == ("present", None)
    assert adapters.ADAPTERS["logit_lens"] is readout_exploratory.ADAPTER
    assert "understanding_score" not in adapters.ADAPTERS


def test_a_missing_adapter_module_is_a_state_not_an_import_error() -> None:
    state, reason = adapters.adapter_status("ica_lens", ABSENT)
    assert state == "absent" and reason == f"adapter module not present: {ABSENT['ica_lens']}"
    assert adapters.load_adapter("ica_lens", ABSENT) == (None, reason)
    for method in ("j_lens", "jpp", "attribution_graph", "conversation_audit"):
        assert adapters.adapter_status(method) == ("none", adapters.NO_ADAPTER_REASON)


def test_adapters_declare_only_the_payload_kinds_of_their_methods() -> None:
    for method in adapters.ADAPTERS:
        adapter = adapters.ADAPTERS[method]
        assert set(adapter.payload_kinds) <= set(common.METHOD_PAYLOAD_KINDS[method])
        assert isinstance(adapter, adapters.Adapter)
    assert behavior_fixture.ADAPTER.payload_kinds == ("behavior_next_token/1",)
    assert readout_exploratory.ADAPTER.payload_kinds == ("lens_readout_report/1",)
    assert readout_exploratory.ADAPTER.method_ids == ("logit_lens",)


def task_for(plan: dict, family: str, variant: str, method: str, replicate: int = 0) -> dict:
    return next(t for t in plan["tasks"] if (t["spec"]["family_id"], t["spec"]["variant"], t["spec"]["method"]["id"],
                                             t["replicate"]) == (family, variant, method, replicate))


def test_behaviour_payload_matches_hand_computed_probabilities(protocol: dict, matrix: dict) -> None:
    plan = planner.build_plan(protocol, matrix)
    context = {"fixtures_dir": FIXTURES, "protocol": protocol}
    adapter = behavior_fixture.ADAPTER
    # Weights [1,1,1,2,1,4,1,1], sum 12: t1 (token 5) = 4/12, rank 1; c1 (token 3) = 2/12, rank 2.
    task = task_for(plan, "fam-1", "clinical", "behavior_next_token")
    assert adapter.preflight(task, context) == ("ready", None)
    payload = adapter.execute_fixture(task, context)
    adapter.validate_payload(payload, task, context)
    t1, c1 = payload["targets"]
    assert (t1["target_id"], t1["token_id"], t1["raw_rank"]) == ("t1", 5, 1)
    assert t1["full_vocab_probability"] == pytest.approx(1 / 3, abs=1e-12)
    assert (c1["target_id"], c1["raw_rank"]) == ("c1", 2) and c1["full_vocab_probability"] == pytest.approx(1 / 6)
    # Weights [1,1,4,1,1,2,1,1]: t1 = 2/12, second after token 2; c1 = 1/12, tied at weight 1 with tokens
    # 0,1,3,4,6,7, so its rank is 1 + two larger (tokens 2 and 5) + two equal with a smaller id (0 and 1) = 5.
    payload = adapter.execute_fixture(task_for(plan, "fam-1", "colloquial", "behavior_next_token"), context)
    assert payload["targets"][0]["full_vocab_probability"] == pytest.approx(1 / 6, abs=1e-12)
    assert [row["raw_rank"] for row in payload["targets"]] == [2, 5]
    assert payload["synthetic"] is True and payload["kind"] == "behavior_next_token/1"
    assert payload["extraction"] == "fixture_supplied_next_token_logits"


def test_behaviour_adapter_reports_absent_fixtures_as_unavailable(protocol: dict, matrix: dict, tmp_path: Path) -> None:
    task = task_for(planner.build_plan(protocol, matrix), "fam-1", "clinical", "behavior_next_token")
    state, reason = behavior_fixture.ADAPTER.preflight(task, {"fixtures_dir": tmp_path, "protocol": protocol})
    assert state == "unavailable" and "behavior_logits.json" in reason
    state, reason = readout_exploratory.ADAPTER.preflight(
        task_for(planner.build_plan(protocol, matrix), "fam-1", "clinical", "logit_lens"),
        {"fixtures_dir": tmp_path, "protocol": protocol})
    assert state == "unavailable" and "readout_spec.json" in reason


def test_a_fixture_file_that_is_not_json_is_unavailable_and_has_an_identity(protocol: dict, matrix: dict,
                                                                            tmp_path: Path) -> None:
    # Regression: read_json raised JSONDecodeError out of preflight and the run stopped with a traceback.
    (tmp_path / "behavior_logits.json").write_text('{"rows": [', encoding="utf-8")
    task = task_for(planner.build_plan(protocol, matrix), "fam-1", "clinical", "behavior_next_token")
    context = {"fixtures_dir": tmp_path, "protocol": protocol}
    state, reason = behavior_fixture.ADAPTER.preflight(task, context)
    assert state == "unavailable" and "is not JSON" in reason
    assert len(behavior_fixture.ADAPTER.input_identity(task, context)) == 64
    (tmp_path / "behavior_logits.json").write_text("[1, 2]", encoding="utf-8")
    state, reason = behavior_fixture.ADAPTER.preflight(task, {"fixtures_dir": tmp_path, "protocol": protocol})
    assert state == "unavailable" and "not a JSON object" in reason


def test_input_identity_is_the_digest_of_the_fixture_file_hashes(protocol: dict, matrix: dict, tmp_path: Path) -> None:
    plan = planner.build_plan(protocol, matrix)
    context = {"fixtures_dir": FIXTURES, "protocol": protocol}

    def sha(name: str) -> str:
        return hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()

    behaviour = behavior_fixture.ADAPTER.input_identity(task_for(plan, "fam-1", "clinical", "behavior_next_token"), context)
    assert behaviour == canonical({"adapter_inputs": {"behavior_logits.json": sha("behavior_logits.json")}})
    lens = readout_exploratory.ADAPTER.input_identity(task_for(plan, "fam-1", "clinical", "logit_lens"), context)
    assert lens == canonical({"adapter_inputs": {"readout_packet.json": sha("readout_packet.json"),
                                                 "readout_spec.json": sha("readout_spec.json")}})
    absent = {"fixtures_dir": tmp_path, "protocol": protocol}
    assert behavior_fixture.ADAPTER.input_identity(plan["tasks"][0], absent) is None
    assert readout_exploratory.ADAPTER.input_identity(plan["tasks"][0], absent) is None
    # The registry helper: an adapter without the hook is "not implemented", and a bad return value refuses.
    assert adapters.input_identity(behavior_fixture.ADAPTER, plan["tasks"][0], context) == (True, behaviour)
    assert adapters.input_identity(object(), plan["tasks"][0], context) == (False, None)

    class Raises:
        def input_identity(self, task: dict, context: dict) -> str:
            raise OSError("placeholder: unreadable")

    class Wrong:
        def input_identity(self, task: dict, context: dict) -> str:
            return "not-a-digest"

    assert adapters.input_identity(Raises(), plan["tasks"][0], context) == (True, None)
    with pytest.raises(Refusal) as caught:
        adapters.input_identity(Wrong(), plan["tasks"][0], context)
    assert caught.value.code == "adapter_contract"


def test_readout_targets_must_be_the_protocols_targets(protocol: dict, matrix: dict) -> None:
    # Regression: readout_spec.json could score t1 on another token than the protocol declares and still validate.
    plan = planner.build_plan(protocol, matrix)
    context = {"fixtures_dir": FIXTURES, "protocol": protocol}
    adapter = readout_exploratory.ADAPTER
    task = task_for(plan, "fam-1", "clinical", "logit_lens")
    payload = adapter.execute_fixture(task, context)
    adapter.validate_payload(payload, task, context)
    assert [(s["target_id"], s["role"], s["token_id"]) for s in payload["readouts"][0]["scores"]] == [
        (t["id"], t.get("role", "answer"), t["token_ids"][0]) for t in protocol["case_families"][0]["targets"]]

    def code(changed_payload: dict, changed_protocol: dict = protocol) -> str:
        with pytest.raises(Refusal) as caught:
            adapter.validate_payload(changed_payload, task, {"fixtures_dir": FIXTURES, "protocol": changed_protocol})
        return caught.value.code

    other_token = copy.deepcopy(payload)
    other_token["readouts"][0]["scores"][0]["token_id"] = 2     # not an excluded token, so the rank rules still hold
    assert code(other_token) == "missing_targets"
    other_role = copy.deepcopy(payload)
    other_role["readouts"][1]["scores"][0]["role"] = "intermediate"
    assert code(other_role) == "missing_targets"
    dropped = copy.deepcopy(payload)
    del dropped["readouts"][2]["scores"][1]
    assert code(dropped) == "missing_targets"
    renamed = copy.deepcopy(protocol)
    renamed["case_families"][0]["targets"][0]["id"] = "renamed_t1"
    assert code(payload, renamed) == "missing_targets"
    retokened = copy.deepcopy(protocol)
    retokened["case_families"][0]["targets"][0]["token_ids"] = [2]
    assert code(payload, retokened) == "missing_targets"


def test_readout_payload_wraps_the_v1_report_without_its_prompt_text(protocol: dict, matrix: dict) -> None:
    plan = planner.build_plan(protocol, matrix)
    context = {"fixtures_dir": FIXTURES, "protocol": protocol}
    adapter = readout_exploratory.ADAPTER
    task = task_for(plan, "fam-1", "clinical", "logit_lens")
    payload = adapter.execute_fixture(task, context)
    adapter.validate_payload(payload, task, context)
    spec, packet = load("readout_spec.json"), load("readout_packet.json")
    report = exploratory_methods.build_report(spec, packet)
    assert payload["source_report"]["schema_version"] == "patientwords.exploratory/1"
    assert payload["source_report"]["spec_sha256"] == report["spec_sha256"] == canonical(spec)
    assert payload["source_report"]["packet_sha256"] == canonical(packet)
    # fam-1 clinical has two tokens: layers 0,1 x positions 0,1, logit_lens only.
    assert [(r["layer"], r["position"]) for r in payload["readouts"]] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert payload["method"] == "logit_lens" and (payload["v1_case_id"], payload["v1_variant"]) == ("fam-1", "source")
    text = json.dumps(payload)
    assert "provenance" not in payload and not any(prompt in text for prompt in PLACEHOLDER_PROMPTS)
    # Layer 1, last position, logits [0,1,2,3,4,5,7,6], tokens 6 and 7 excluded by the filter:
    # t1 (token 5) is beaten by tokens 6 and 7 -> raw rank 3; with them removed -> filtered rank 1.
    t1 = payload["readouts"][3]["scores"][0]
    assert (t1["target_id"], t1["raw_rank"], t1["filtered_rank"]) == ("t1", 3, 1)
    assert t1["top_k"] == {"1": "not_observed_in_window", "2": "not_observed_in_window", "4": "observed"}


def test_adapters_refuse_a_payload_that_is_not_the_planned_row(protocol: dict, matrix: dict) -> None:
    plan = planner.build_plan(protocol, matrix)
    context = {"fixtures_dir": FIXTURES, "protocol": protocol}
    clinical = task_for(plan, "fam-1", "clinical", "behavior_next_token")
    colloquial = task_for(plan, "fam-1", "colloquial", "behavior_next_token")
    payload = behavior_fixture.ADAPTER.execute_fixture(clinical, context)
    with pytest.raises(Refusal) as caught:
        behavior_fixture.ADAPTER.validate_payload(payload, colloquial, context)
    assert caught.value.code == "row_misalignment"
    lens = readout_exploratory.ADAPTER.execute_fixture(task_for(plan, "fam-1", "clinical", "logit_lens"), context)
    with pytest.raises(Refusal) as caught:
        behavior_fixture.ADAPTER.validate_payload(lens, clinical, context)
    assert caught.value.code == "payload_kind"
    del lens["readouts"][0]
    with pytest.raises(Refusal) as caught:
        readout_exploratory.ADAPTER.validate_payload(lens, task_for(plan, "fam-1", "clinical", "logit_lens"), context)
    assert caught.value.code == "readout_grid"


# ----------------------------------------------------------------------------------------------- planner

def test_plan_is_deterministic_and_task_ids_are_spec_digests(protocol: dict, matrix: dict) -> None:
    first, second = planner.build_plan(protocol, matrix), planner.build_plan(copy.deepcopy(protocol), matrix)
    assert common.json_bytes(first) == common.json_bytes(second)
    for task in first["tasks"]:
        assert task["spec_sha256"] == canonical(task["spec"]) and task["task_id"] == task["spec_sha256"][:16]
        assert task["spec"]["protocol_sha256"] == canonical(protocol)
        assert "replicate" not in task["spec"] and "attempt" not in task["spec"]
    order = [(t["spec"]["family_id"], t["spec"]["variant"], t["spec"]["method"]["id"]) for t in first["tasks"]]
    assert order == sorted(order) and len(set(order)) == 36
    planner.validate_plan(json.loads(common.json_bytes(first)))


def test_plan_counts_every_task_with_its_state_and_reason(protocol: dict, matrix: dict) -> None:
    plan = planner.build_plan(protocol, matrix)
    # 3 families x 3 variants x 4 methods x 1 replicate.
    assert plan["totals"]["tasks"] == 36
    assert plan["totals"]["by_planned_state"] == {"ready": 18, "unsupported": 9, "unavailable": 9}
    assert plan["totals"]["by_method"]["jpp"] == {"ready": 0, "unsupported": 0, "unavailable": 9, "total": 9}
    assert plan["totals"]["by_method"]["j_lens"] == {"ready": 0, "unsupported": 9, "unavailable": 0, "total": 9}
    jpp = task_for(plan, "fam-2", "normalized", "jpp")
    assert jpp["planned_state"] == "unavailable" and jpp["reason"].startswith("artifact identity unknown")
    assert jpp["capability"]["status"] == "artifact_available_identity_unknown"
    j_lens = task_for(plan, "fam-2", "normalized", "j_lens")
    assert j_lens["planned_state"] == "unsupported" and j_lens["reason"]
    assert all((t["planned_state"] == "ready") == (t["reason"] is None) for t in plan["tasks"])
    assert plan["adapters"]["jpp"].startswith("none: no executable adapter")


def test_a_method_with_no_capability_row_stays_in_the_plan_as_unsupported(protocol: dict, matrix: dict) -> None:
    protocol["methods"].append({"id": "attribution_graph"})
    plan = planner.build_plan(protocol, matrix)
    rows = [t for t in plan["tasks"] if t["spec"]["method"]["id"] == "attribution_graph"]
    assert len(rows) == 9 and {t["planned_state"] for t in rows} == {"unsupported"}
    assert all("no capability row" in t["reason"] and t["capability"]["matched"] is False for t in rows)


def test_released_jpp_artifact_is_unavailable_because_its_fit_identity_is_unknown(protocol: dict, matrix: dict) -> None:
    # A planning rehearsal with placeholder inputs against the real Qwen3-4B rows. Nothing can be ready.
    protocol["model"].update({"study_id": "qwen3-4b", "hf_id": "Qwen/Qwen3-4B", "backend": "cpu_transformers",
                              "revision": logits_eval.HF_REVISIONS["qwen3-4b"], "dtype": "bfloat16",
                              "tokenizer_revision": logits_eval.HF_REVISIONS["qwen3-4b"],
                              "hidden_size": 2560, "n_layers": 36})
    protocol["methods"] = [{"id": "behavior_next_token"},
                           {"id": "jpp", "capture_site": "block_output", "layer_index_base": 0, "layers": [17],
                            "artifact": {"sha256": "893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d"}}]
    plan = planner.build_plan(protocol, matrix)
    assert plan["totals"]["by_planned_state"] == {"ready": 0, "unsupported": 0, "unavailable": 18}
    jpp = task_for(plan, "fam-1", "clinical", "jpp")
    assert jpp["capability"]["status"] == "artifact_available_identity_unknown"
    assert jpp["reason"].startswith("artifact identity unknown") and "fit model revision" in jpp["reason"]
    behaviour = task_for(plan, "fam-1", "clinical", "behavior_next_token")
    assert behaviour["capability"]["status"] == "artifact_available"
    assert "offline fixtures only" in behaviour["reason"]
    # 2 tokens x 1 layer x 2560 wide x 2 bytes (bfloat16) = 10,240 bytes for the fam-1 clinical jpp task.
    assert jpp["estimate"]["activation_bytes"] == 10240


def test_a_missing_optional_adapter_is_planned_as_unavailable(protocol: dict, matrix: dict) -> None:
    protocol["methods"].append(ica_method())
    plan = planner.build_plan(protocol, matrix, registry={**adapters.ADAPTER_MODULES, **ABSENT})
    rows = [t for t in plan["tasks"] if t["spec"]["method"]["id"] == "ica_lens"]
    assert len(rows) == 9 and {t["planned_state"] for t in rows} == {"unavailable"}
    assert all(t["reason"] == f"adapter module not present: {ABSENT['ica_lens']}" for t in rows)
    assert plan["adapters"]["ica_lens"] == f"unavailable: adapter module not present: {ABSENT['ica_lens']}"
    assert plan["totals"]["by_planned_state"]["ready"] == 18


def test_replicates_share_a_spec_and_have_their_own_key(protocol: dict, matrix: dict) -> None:
    one, two = planner.build_plan(protocol, matrix), planner.build_plan(protocol, matrix, replicates=2)
    assert two["totals"]["tasks"] == 72 and two["replicates"] == 2
    assert {t["spec_sha256"] for t in two["tasks"]} == {t["spec_sha256"] for t in one["tasks"]}
    assert len({(t["spec_sha256"], t["replicate"]) for t in two["tasks"]}) == 72
    with pytest.raises(Refusal) as caught:
        planner.build_plan(protocol, matrix, replicates=0)
    assert caught.value.code == "replicates"


def test_changed_input_or_config_changes_every_spec_digest(protocol: dict, matrix: dict) -> None:
    base = {t["spec_sha256"] for t in planner.build_plan(protocol, matrix)["tasks"]}
    changed_input = copy.deepcopy(protocol)
    set_variant(changed_input, 0, "clinical", [0, 0, 4], "alpha alpha tail")
    changed_config = copy.deepcopy(protocol)
    changed_config["methods"][1]["layers"] = [0]
    changed_setting = copy.deepcopy(protocol)
    changed_setting["input_settings"]["add_special_tokens"] = False
    for doc in (changed_input, changed_config, changed_setting):
        assert not base & {t["spec_sha256"] for t in planner.build_plan(doc, matrix)["tasks"]}


def test_size_estimates_follow_the_stated_formulas(protocol: dict, matrix: dict) -> None:
    # 3 positions x 2 layers x 8 wide x 4 bytes.
    assert planner.estimate_activation_bytes(3, 2, 8, "float32") == 192
    assert planner.estimate_activation_bytes(3, 2, 8, "bfloat16") == 96
    # 8 bytes x (2 x 100 x 8 + 3 x 64) = 8 x 1792.
    assert planner.estimate_fit_bytes(100, 8, "float64") == 14336
    with pytest.raises(Refusal) as caught:
        planner.estimate_activation_bytes(3, 2, 8, "int8")
    assert caught.value.code == "unknown_dtype"
    plan = planner.build_plan(protocol, matrix)
    # Input lengths 2,2,2 / 3,3,3 / 3,3,3 = 24 tokens per method. logit_lens: 24 x 2 layers x 8 x 4 = 1536.
    # j_lens and jpp: 24 x 1 layer x 8 x 4 = 768 each. behaviour captures nothing.
    assert plan["totals"]["estimates"] == {"tokens": 96, "activation_bytes": 3072, "ready_tokens": 48,
                                           "ready_activation_bytes": 1536, "measured": False}
    behaviour = task_for(plan, "fam-1", "clinical", "behavior_next_token")
    assert behaviour["estimate"]["activation_bytes"] == 0 and behaviour["estimate"]["measured"] is False


def test_no_runtime_is_estimated_without_a_measured_rate(protocol: dict, matrix: dict) -> None:
    plan = planner.build_plan(protocol, matrix)
    assert plan["totals"]["runtime_seconds_estimate"] is None and plan["rates_used"] == []
    assert any("no measured rate was supplied" in note for note in plan["estimate_notes"])

    def rate(method: str, **extra: object) -> dict:
        return {"method": method, "backend": "fixture", "seconds_per_task": 2.0, "source": "placeholder run",
                "n_samples": 5, **extra}

    doc = {"schema_version": "patientwords.experiment-rates/1", "rates": [rate("behavior_next_token")]}
    assert planner.build_plan(protocol, matrix, rates=doc)["totals"]["runtime_seconds_estimate"] is None
    doc["rates"].append(rate("logit_lens", seconds_per_task=3.0))
    timed = planner.build_plan(protocol, matrix, rates=doc)
    # 9 ready behaviour tasks x 2.0 s + 9 ready logit_lens tasks x 3.0 s.
    assert timed["totals"]["runtime_seconds_estimate"] == pytest.approx(45.0)
    assert [(r["method"], r["source"], r["n_samples"]) for r in timed["rates_used"]] == [
        ("behavior_next_token", "placeholder run", 5), ("logit_lens", "placeholder run", 5)]
    doc["rates"][0].pop("source")
    with pytest.raises(Refusal) as caught:
        planner.build_plan(protocol, matrix, rates=doc)
    assert caught.value.code == "rates_source"


def rates_doc(*rows: dict) -> dict:
    return {"schema_version": "patientwords.experiment-rates/1", "rates": list(rows)}


def rate_row(method: str, backend: str, seconds: object = 80.0) -> dict:
    return {"method": method, "backend": backend, "seconds_per_task": seconds, "source": "placeholder run",
            "n_samples": 5}


def test_no_runtime_is_estimated_when_no_task_is_ready(protocol: dict, matrix: dict) -> None:
    # Regression: sum([]) gave runtime_seconds_estimate 0 for a plan whose every task needs a model run.
    protocol["model"].update({"study_id": "gemma-2-2b", "hf_id": "google/gemma-2-2b", "backend": "cpu_interp_engine",
                              "revision": "f" * 40, "tokenizer_revision": "f" * 40, "dtype": "float32",
                              "hidden_size": 2304, "n_layers": 26})
    protocol["methods"] = [{"id": "behavior_next_token"}]
    plan = planner.build_plan(protocol, matrix, rates=rates_doc(rate_row("behavior_next_token", "cpu_interp_engine")))
    assert plan["totals"]["by_planned_state"] == {"ready": 0, "unsupported": 0, "unavailable": 9}
    assert plan["totals"]["runtime_seconds_estimate"] is None and plan["rates_used"] == []
    assert any("no task is ready, so no runtime is estimated" in note for note in plan["estimate_notes"])
    # The row records no revision, so the plan carries the lowered answer and says which kind of match it was.
    capability = plan["tasks"][0]["capability"]
    assert (capability["status"], capability["revision_match"]) == ("artifact_available", "row_revision_not_recorded")


def test_a_rates_document_with_two_rows_for_one_method_and_backend_is_refused(protocol: dict, matrix: dict) -> None:
    # Regression: the dict comprehension kept the last of two rows without saying so.
    def code(doc: dict) -> str:
        with pytest.raises(Refusal) as caught:
            planner.build_plan(protocol, matrix, rates=doc)
        return caught.value.code

    assert code(rates_doc(rate_row("behavior_next_token", "fixture", 2.0),
                          rate_row("behavior_next_token", "fixture", 9.0))) == "duplicate_rate"
    assert code(rates_doc(rate_row("behavior_next_token", "fixture", float("inf")))) == "rates_source"
    assert code(rates_doc(rate_row("behavior_next_token", "fixture", float("nan")))) == "rates_source"
    # The same method on two backends is two rates, not a duplicate.
    two = rates_doc(rate_row("behavior_next_token", "fixture", 2.0), rate_row("logit_lens", "fixture", 3.0),
                    rate_row("behavior_next_token", "cpu_transformers", 50.0))
    assert planner.build_plan(protocol, matrix, rates=two)["totals"]["runtime_seconds_estimate"] == pytest.approx(45.0)


def test_an_excluded_family_is_listed_and_gets_no_task(protocol: dict, matrix: dict) -> None:
    protocol["exclusions"] = [{"family_id": "fam-2", "reason": "placeholder exclusion"}]
    plan = planner.build_plan(protocol, matrix)
    assert plan["excluded"] == [{"family_id": "fam-2", "reason": "placeholder exclusion"}]
    assert plan["totals"]["tasks"] == 24 and "fam-2" not in {t["spec"]["family_id"] for t in plan["tasks"]}


def test_a_plan_copies_no_prompt_or_target_text(protocol: dict, matrix: dict) -> None:
    text = json.dumps(planner.build_plan(protocol, matrix))
    assert not any(prompt in text for prompt in PLACEHOLDER_PROMPTS) and "omega" not in text


def test_a_tampered_plan_is_refused(protocol: dict, matrix: dict) -> None:
    plan = planner.build_plan(protocol, matrix)
    plan["tasks"][0]["spec"]["variant"] = "colloquial"
    with pytest.raises(Refusal) as caught:
        planner.validate_plan(plan)
    assert caught.value.code == "plan_identity"


# ---------------------------------------------------------------------------------------------- envelope

@pytest.fixture
def run(protocol: dict, matrix: dict, tmp_path: Path) -> tuple[RunStore, dict]:
    plan = planner.build_plan(protocol, matrix)
    store = RunStore(tmp_path / "run")
    store.run_fixture(plan, "w0", fixtures_dir=FIXTURES, protocol=protocol)
    return store, plan


def envelope_of(store: RunStore, plan: dict, family: str, variant: str, method: str) -> dict:
    task = task_for(plan, family, variant, method)
    return common.read_json(store.shards_dir / "w0" / f"{task['task_id']}.r0.a1.envelope.json")


def envelope_code(doc: dict, root: Path | None) -> str:
    with pytest.raises(Refusal) as caught:
        envelope.validate_envelope(doc, payload_root=root)
    return caught.value.code


def test_fixture_envelopes_validate_and_say_what_they_are(run: tuple[RunStore, dict]) -> None:
    store, plan = run
    done = envelope_of(store, plan, "fam-1", "clinical", "behavior_next_token")
    assert envelope.validate_envelope(done, payload_root=store.run_dir) == {
        "status": "validated", "execution": "completed", "payload_verified": True}
    assert envelope.validate_envelope(done)["payload_verified"] is False
    assert done["evidence"] == {"evidence_class": "synthetic_fixture", "clinical_review": "not_applicable_synthetic",
                                "visibility": "not_published", "restriction_reasons": [], "analysis_memberships": [],
                                "synthetic": True}
    assert done["counts"] == {"requested": 1, "accepted": 1, "completed": 1, "failed": 0, "exclusions": []}
    assert done["resources"]["measured"] is True and done["resources"]["runtime_seconds"] >= 0
    assert done["resources"]["cost_usd"] is None and done["resources"]["peak_memory_bytes"] is None
    assert done["payload"]["kind"] == "behavior_next_token/1"
    assert done["method"]["representation_type"] == "not_applicable" and done["method"]["layers"] == []
    assert done["environment"]["sampling"] == {"seed": 7, "sampled": False}
    assert set(done["not_recorded"]) >= {"/environment/lock_sha256", "/source/legacy_join"}
    assert set(done) == set(common.load_schema("envelope")["required"])


def test_states_that_did_not_run_carry_a_reason_and_no_payload(run: tuple[RunStore, dict]) -> None:
    store, plan = run
    jpp = envelope_of(store, plan, "fam-1", "clinical", "jpp")
    assert jpp["status"]["execution"] == "unavailable" and jpp["status"]["reason"].startswith("artifact identity")
    assert jpp["payload"] is None
    assert jpp["counts"] == {"requested": 1, "accepted": 0, "completed": 0, "failed": 0, "exclusions": []}
    assert jpp["resources"] == {"runtime_seconds": None, "peak_memory_bytes": None, "storage_bytes": None,
                                "usage": None, "cost_usd": None, "measured": False}
    # The lens's fit revisions are unknown. They stay null and are listed; no value is filled in.
    assert jpp["method"]["fitted_artifact"]["sha256"] == "4" * 64
    assert jpp["method"]["fitted_artifact"]["fit_provenance"]["fit_model_revision"] is None
    assert "/method/fitted_artifact/fit_provenance/fit_model_revision" in jpp["not_recorded"]
    assert jpp["method"]["representation_type"] == "workspace_readout"
    j_lens = envelope_of(store, plan, "fam-1", "clinical", "j_lens")
    assert j_lens["status"]["execution"] == "unsupported"
    assert {"/method/fitted_artifact/sha256", "/method/output_head"} <= set(j_lens["not_recorded"])


def test_silent_missing_provenance_is_refused(run: tuple[RunStore, dict]) -> None:
    store, plan = run
    base = envelope_of(store, plan, "fam-1", "clinical", "logit_lens")
    doc = copy.deepcopy(base)
    doc["model"]["revision"] = None
    assert envelope_code(doc, store.run_dir) == "silent_missing_provenance"
    doc["not_recorded"].append("/model/revision")
    assert envelope.validate_envelope(doc, payload_root=store.run_dir)["status"] == "validated"
    doc = copy.deepcopy(base)
    doc["not_recorded"].remove("/source/legacy_join")
    assert envelope_code(doc, store.run_dir) == "silent_missing_provenance"
    doc = copy.deepcopy(base)
    doc["not_recorded"].append("/model/hf_id")
    assert envelope_code(doc, store.run_dir) == "not_recorded_pointer"


def test_payload_hash_and_payload_kind_rules(run: tuple[RunStore, dict]) -> None:
    store, plan = run
    base = envelope_of(store, plan, "fam-1", "clinical", "logit_lens")
    doc = copy.deepcopy(base)
    doc["payload"]["kind"] = "ica_scores/1"
    assert envelope_code(doc, store.run_dir) == "method_payload_mismatch"
    doc["payload"]["kind"] = "behavior_next_token/1"
    assert envelope_code(doc, store.run_dir) == "method_payload_mismatch"
    doc = copy.deepcopy(base)
    doc["payload"]["path"] = "../elsewhere.json"
    assert envelope_code(doc, store.run_dir) == "payload_path"
    payload_file = store.run_dir / base["payload"]["path"]
    original = payload_file.read_bytes()
    payload_file.write_bytes(original.replace(b'"raw_rank": 3', b'"raw_rank": 1'))
    assert envelope_code(base, store.run_dir) == "payload_hash"
    payload_file.unlink()
    assert envelope_code(base, store.run_dir) == "payload_hash"
    payload_file.write_bytes(original)
    assert envelope.validate_envelope(base, payload_root=store.run_dir)["payload_verified"] is True


def change(doc: dict, path: str, value: object) -> dict:
    out = copy.deepcopy(doc)
    node = out
    keys = path.split("/")
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    return out


def test_envelope_rules(run: tuple[RunStore, dict]) -> None:
    store, plan = run
    done = envelope_of(store, plan, "fam-1", "clinical", "logit_lens")
    skipped = envelope_of(store, plan, "fam-1", "clinical", "jpp")
    root = store.run_dir
    cases = [
        (change(done, "counts/failed", 1), "counts_arithmetic"),           # 1 + 1 + 0 != 1 accepted
        (change(done, "counts/accepted", 2), "counts_arithmetic"),          # accepted 2 > requested 1
        (change(done, "counts/exclusions", [{"reason": "placeholder", "n": 1}]), "counts_arithmetic"),
        (change(done, "evidence/visibility", "public"), "synthetic_label"),
        (change(done, "evidence/evidence_class", "registered_cohort"), "synthetic_label"),
        (change(done, "evidence/analysis_memberships", ["study-interim/1"]), "synthetic_label"),
        (change(done, "resources/measured", False), "resources_rule"),      # runtime present, measured false
        (change(done, "resources/runtime_seconds", None), "resources_rule"),
        (change(skipped, "resources/runtime_seconds", 1.5), "resources_rule"),
        (change(done, "payload", None), "payload_state"),
        (change(skipped, "payload", done["payload"]), "payload_state"),
        (change(done, "method/layers", [0, 3]), "layer_metadata"),          # the toy model has layers 0..2
        (change(done, "method/layer_index_base", 1), "layer_metadata"),
        (change(done, "status/execution", "skipped"), "execution_state"),
        (change(skipped, "status/reason", None), "status_reason"),
        (change(done, "attempt", 2), "attempt_history"),
        (change(done, "task_id", "0" * 16), "plan_identity"),
        (change(done, "method/representation_type", "feature"), "representation_type"),
        (change(done, "schema_version", "patientwords.exploratory/1"), "schema_version"),
        ({**done, "understanding_score": 0.5}, "invalid_input"),            # the envelope has no result field
        ({k: v for k, v in done.items() if k != "not_recorded"}, "invalid_input"),
    ]
    for doc, code in cases:
        assert envelope_code(doc, root) == code, code
    excluded = change(change(done, "counts/completed", 0), "counts/exclusions", [{"reason": "placeholder", "n": 1}])
    assert envelope_code(excluded, root) == "counts_arithmetic"             # completed state needs a completed unit


def changes(doc: dict, **paths: object) -> dict:
    for path, value in paths.items():
        doc = change(doc, path.replace("__", "/"), value)
    return doc


def test_counts_and_resources_must_agree_with_the_execution_state(run: tuple[RunStore, dict]) -> None:
    # Regression: each of these envelopes validated.
    store, plan = run
    root = store.run_dir
    done = envelope_of(store, plan, "fam-1", "clinical", "logit_lens")
    skipped = envelope_of(store, plan, "fam-1", "clinical", "j_lens")
    assert skipped["status"]["execution"] == "unsupported"
    failed = changes(done, status={"execution": "failed", "reason": "placeholder failure"}, payload=None,
                     resources__storage_bytes=None)
    failed["attempt_history"][-1]["state"] = "failed"
    # (a) failed, yet it counts one completed unit and no failed unit.
    assert envelope_code(failed, root) == "counts_arithmetic"
    assert envelope.validate_envelope(changes(failed, counts__completed=0, counts__failed=1),
                                      payload_root=root)["execution"] == "failed"
    # (b) never ran, yet it accepts and completes a unit.
    assert envelope_code(changes(skipped, counts__accepted=1, counts__completed=1), root) == "counts_arithmetic"
    assert envelope_code(changes(skipped, counts__accepted=1, counts__failed=1), root) == "counts_arithmetic"
    # (c) never ran, yet it reports measured runtime and cost.
    measured = changes(skipped, resources__measured=True, resources__runtime_seconds=12.5, resources__cost_usd=3.0)
    assert envelope_code(measured, root) == "resources_rule"
    for state in ("unavailable", "not_run"):
        other = changes(measured, status={"execution": state, "reason": "placeholder"})
        other["attempt_history"][-1]["state"] = state
        assert envelope_code(other, root) == "resources_rule"
    # An invalid single-task envelope cannot count a completed unit either.
    invalid = changes(failed, status={"execution": "invalid", "reason": "placeholder"})
    invalid["attempt_history"][-1]["state"] = "invalid"
    assert envelope_code(invalid, root) == "counts_arithmetic"


def test_method_representation_and_variant_are_checked_on_read(run: tuple[RunStore, dict]) -> None:
    # Regression: behavior_next_token with representation_type ica_component validated, as did an unknown variant.
    store, plan = run
    root = store.run_dir
    behaviour = envelope_of(store, plan, "fam-1", "clinical", "behavior_next_token")
    assert envelope_code(change(behaviour, "method/representation_type", "ica_component"), root) == "representation_type"
    lens = envelope_of(store, plan, "fam-1", "clinical", "logit_lens")
    assert envelope_code(change(lens, "method/representation_type", "ica_component"), root) == "representation_type"
    assert envelope_code(change(lens, "source/variant", "no_such_variant"), root) == "unknown_variant"
    assert envelope_code(change(lens, "environment/input_identity_sha256", "abc"), root) == "input_identity"


def test_envelope_evidence_labels_follow_the_open_results_vocabulary(run: tuple[RunStore, dict]) -> None:
    # Regression: a non-synthetic envelope could say "public" with a restriction reason, or any visibility word.
    store, plan = run
    root = store.run_dir
    done = envelope_of(store, plan, "fam-1", "clinical", "logit_lens")

    def labelled(**evidence: object) -> dict:
        return change(done, "evidence", {"evidence_class": "exploratory_post_registration",
                                         "clinical_review": "domain_review_pending", "visibility": "public",
                                         "restriction_reasons": [], "analysis_memberships": [], "synthetic": False,
                                         **evidence})

    assert envelope.validate_envelope(labelled(), payload_root=root)["status"] == "validated"
    assert envelope.validate_envelope(labelled(analysis_memberships=["study-interim/1"]),
                                      payload_root=root)["status"] == "validated"
    assert envelope.validate_envelope(labelled(visibility="restricted", restriction_reasons=["placeholder_restriction"]),
                                      payload_root=root)["status"] == "validated"
    for evidence in ({"visibility": "whatever"},
                     {"visibility": "public", "restriction_reasons": ["placeholder_restriction"]},
                     {"visibility": "public", "restriction_reasons": ["placeholder_restriction"],
                      "analysis_memberships": ["study-interim/1"]},
                     {"visibility": "restricted"},
                     {"analysis_memberships": ["placeholder-membership/9"]}):
        assert envelope_code(labelled(**evidence), root) == "evidence_fields", evidence


def test_measured_resources_of_a_skipped_task_may_not_hold_an_estimate(run: tuple[RunStore, dict]) -> None:
    store, plan = run
    skipped = envelope_of(store, plan, "fam-1", "clinical", "j_lens")
    assert skipped["resources"]["measured"] is False
    for key in ("runtime_seconds", "peak_memory_bytes", "storage_bytes", "cost_usd"):
        assert envelope_code(change(skipped, f"resources/{key}", 0), store.run_dir) == "resources_rule"
    assert envelope_code(change(skipped, "resources/usage", {"tokens": 1}), store.run_dir) == "resources_rule"
