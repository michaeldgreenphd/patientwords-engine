"""Synthetic contract checks; no model weights, services, or source data."""
import copy
import json
from pathlib import Path

import pytest

from scripts import exploratory_methods as methods

FIXTURES = Path(__file__).parent / "fixtures" / "exploratory"


@pytest.fixture
def spec() -> dict:
    return json.loads((FIXTURES / "synthetic_spec.json").read_text())


@pytest.fixture
def packet() -> dict:
    return json.loads((FIXTURES / "synthetic_packet.json").read_text())


def test_complete_report_keeps_three_kinds_separate(spec: dict, packet: dict) -> None:
    result = methods.build_report(spec, packet)
    assert len(result["readouts"]) == 36
    assert len(result["model_outputs"]) == 3
    assert len(result["interventions"]) == 10
    assert result["execution_status"] == "synthetic"
    assert result["model_outputs"][0]["scores"] != result["readouts"][0]["scores"]
    assert result["provenance"] == spec
    assert result["filter_audit"][0]["decoded"] == "%"


@pytest.mark.parametrize("mutation,code", [
    ("missing_plan", "intervention_plan"), ("empty_plan", "intervention_plan"),
    ("missing_filter", "filter_metadata")])
def test_standalone_validation_refuses_incomplete_contracts(
        spec: dict, tmp_path: Path, capsys: pytest.CaptureFixture, mutation: str, code: str) -> None:
    if mutation == "missing_plan":
        del spec["intervention_plan"]
    elif mutation == "empty_plan":
        spec["intervention_plan"] = []
    else:
        del spec["vocabulary_filter"]
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == code
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(spec))
    assert methods.main(["--spec", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "refused" and result["code"] == code


def test_real_spec_with_pending_plan_remains_blocked(spec: dict) -> None:
    spec["synthetic"] = False
    spec["intervention_plan"] = []
    spec["methods"]["jpp"]["model_revision"] = None
    result = methods.validate_spec(spec)
    assert result["status"] == "blocked"
    assert result["blockers"] == ["ci_execution_adapter_not_wired", "intervention_plan_pending",
                                   "jpp:unknown_model_revision",
                                   "real_model_baseline_parity_unrun"]


@pytest.mark.parametrize("field", [
    "id", "case_id", "donor", "recipient", "kind", "component", "layer", "positions", "channels", "control", "seed"])
def test_standalone_plan_requires_complete_entries(spec: dict, field: str) -> None:
    del spec["intervention_plan"][0][field]
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "intervention_plan"


@pytest.mark.parametrize("value", [None, "", 0, True, []])
def test_standalone_plan_requires_nonempty_string_ids(spec: dict, value: object) -> None:
    spec["intervention_plan"][0]["id"] = value
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "intervention_plan"


def test_standalone_plan_refuses_duplicate_ids(spec: dict) -> None:
    spec["intervention_plan"][1]["id"] = spec["intervention_plan"][0]["id"]
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "intervention_plan"


@pytest.mark.parametrize("value", ["missing", None, "", 0])
def test_standalone_random_plan_requires_a_comparator_reference(spec: dict, value: object) -> None:
    row = next(p for p in spec["intervention_plan"] if p["control"] == "random")
    if value == "missing":
        del row["matched_to"]
    else:
        row["matched_to"] = value
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "intervention_plan"


@pytest.mark.parametrize("value", [
    None, {}, {"id": "fixture"}, {"id": False, "excluded": []},
    {"id": "fixture", "excluded": {}}, {"id": "fixture", "excluded": [None]},
    {"id": "fixture", "excluded": [{"token_id": False, "reason": "fixture"}]},
    {"id": "fixture", "excluded": [{"token_id": -1, "reason": "fixture"}]},
    {"id": "fixture", "excluded": [{"token_id": 1.0, "reason": "fixture"}]},
    {"id": "fixture", "excluded": [{"token_id": 0, "reason": ""}]},
    {"id": "fixture", "excluded": [{"token_id": 0, "reason": 7}]}])
def test_standalone_filter_validation_requires_explicit_shapes(spec: dict, value: object) -> None:
    spec["vocabulary_filter"] = value
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "filter_metadata"


def test_filter_vocabulary_bounds_remain_packet_dependent(spec: dict, packet: dict) -> None:
    spec["vocabulary_filter"]["excluded"][0]["token_id"] = len(packet["vocabulary"])
    packet["spec_sha256"] = methods.digest(spec)
    assert methods.validate_spec(spec)["status"] == "validated"
    with pytest.raises(methods.Refusal) as err:
        methods.build_report(spec, packet)
    assert err.value.code == "filter_metadata"


def test_packet_execution_seed_is_required(spec: dict, packet: dict) -> None:
    del packet["environment"]["seed"]
    with pytest.raises(methods.Refusal) as err:
        methods.build_report(spec, packet)
    assert err.value.code == "execution_seed"


def test_packet_execution_seed_must_match_spec(spec: dict, packet: dict) -> None:
    packet["environment"]["seed"] = spec["seed"] + 1
    with pytest.raises(methods.Refusal) as err:
        methods.build_report(spec, packet)
    assert err.value.code == "execution_seed"


@pytest.mark.parametrize("seed", [None, -1, 7.0, "7", True, False])
def test_packet_execution_seed_requires_a_nonnegative_strict_integer(spec: dict, packet: dict, seed: object) -> None:
    if type(seed) is bool:
        spec["seed"] = int(seed)
        packet["spec_sha256"] = methods.digest(spec)
    packet["environment"]["seed"] = seed
    with pytest.raises(methods.Refusal) as err:
        methods.build_report(spec, packet)
    assert err.value.code == "execution_seed"


@pytest.mark.parametrize("seed", [0, 7, 19])
def test_packet_execution_seed_is_preserved_when_it_matches(spec: dict, packet: dict, seed: int) -> None:
    spec["seed"] = seed
    packet["spec_sha256"] = methods.digest(spec)
    packet["environment"]["seed"] = seed
    result = methods.build_report(spec, packet)
    assert result["environment"]["seed"] == result["provenance"]["seed"] == seed
    assert type(result["environment"]["seed"]) is int


@pytest.mark.parametrize("field", ["method", "source_layers", "transport_target"])
def test_lens_metadata_is_required(spec: dict, field: str) -> None:
    del spec["methods"]["jpp"][field]
    with pytest.raises(methods.Refusal):
        methods.validate_spec(spec)


@pytest.mark.parametrize("field", ["model_id", "model_revision", "tokenizer_revision"])
def test_wrong_model_is_not_compatible(spec: dict, field: str) -> None:
    spec["methods"]["jpp"][field] = "wrong"
    with pytest.raises(methods.Refusal, match="jpp"):
        methods.validate_spec(spec)


def test_unknown_fit_revision_stays_unknown(spec: dict) -> None:
    spec["methods"]["jpp"]["model_revision"] = None
    result = methods.validate_spec(spec)
    assert result["status"] == "blocked"
    assert "jpp:unknown_model_revision" in result["blockers"]


@pytest.mark.parametrize("field", ["family_id", "template_family"])
def test_family_splits_cannot_leak(spec: dict, field: str) -> None:
    other = copy.deepcopy(spec["cases"][0])
    other.update(id="other", split="fresh_test", family_id="family-z", template_family="template-z")
    other[field] = spec["cases"][0][field]
    spec["cases"].append(other)
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "split_leakage"


def test_sealed_or_unknown_case_refuses(spec: dict) -> None:
    spec["cases"][0]["holdout_status"] = "unknown"
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "holdout_refusal"


def test_raw_probability_is_not_renormalized_by_filter() -> None:
    target = {"id": "x", "role": "answer", "token_ids": [1]}
    raw = methods.rank_target([3., 2., 1.], target, set(), [1, 2])
    filtered = methods.rank_target([3., 2., 1.], target, {0}, [1, 2])
    assert raw["raw_rank"] == filtered["raw_rank"] == 2
    assert filtered["filtered_rank"] == 1
    assert filtered["full_vocab_probability"] == raw["full_vocab_probability"]
    assert raw["top_k"]["1"] == "not_observed_in_window"
    excluded = methods.rank_target([3., 2., 1.], target, {1}, [1, 2])
    assert excluded["filtered_rank"] is None and excluded["excluded_candidate"]


def test_multitoken_target_is_retained_as_proxy() -> None:
    result = methods.rank_target([3., 2., 1.], {"id": "x", "role": "answer", "token_ids": [1, 2]}, set(), [1, 2])
    assert result["matching"] == "first_wordpiece_proxy"
    assert result["sequence_status"] == "not_scored"
    assert result["exact_sequence_score"] is None


def test_exact_prefix_and_first_piece_are_separate() -> None:
    assert methods.token_match("alpha", "alpha", [1], 1) == "exact"
    assert methods.token_match("alpha", "alpha tail", [1, 2], 1) == "first_wordpiece_proxy"
    assert methods.token_match("alp", "alpha", [1], 3) == "text_prefix_proxy"
    assert methods.token_match("ALPHA", "alpha", [1], 3) is None


def test_token_id_suffix_and_character_span_alignment() -> None:
    assert methods.suffix_alignment([1, 2, 3], [4, 5, 2, 3]) == [[2, 1], [3, 2]]
    assert methods.suffix_alignment([1, 2], [3, 4]) == []
    assert methods.span_positions([[0, 0], [0, 3], [3, 7], [8, 9]], [2, 6]) == [1, 2]
    with pytest.raises(methods.Refusal):
        methods.span_positions([[0, 0]], [2, 6])


def test_seeded_controls_preserve_layer_and_size() -> None:
    groups = methods.seeded_groups(20, 4, [7, 11, 13], 2)
    assert groups == methods.seeded_groups(20, 4, [7, 11, 13], 2)
    assert all(len(g["channels"]) == 4 and g["layer"] == 2 for g in groups)
    assert len({tuple(g["channels"]) for g in groups}) == 3


def test_zero_and_negative_gaps_do_not_produce_recovery() -> None:
    for source in [0.1, 0.2, 0.20000001]:
        result = methods.patch_effect(source, 0.2, 0.3, 1e-6)
        assert result["normalized_recovery"] is None
        assert result["raw_probability_delta"] == pytest.approx(0.1)
    assert methods.patch_effect(0.4, 0.2, 0.1, 1e-6)["normalized_recovery"] == pytest.approx(-0.5)


@pytest.mark.parametrize("mutation,code", [
    ("missing_grid", "incomplete_readouts"), ("missing_output", "missing_model_outputs"),
    ("missing_interventions", "missing_interventions"), ("unknown_layer", "readout_grid"),
    ("unknown_method", "readout_grid"), ("wrong_model", "model_mismatch"),
    ("bad_prompt_identity", "packet_identity"), ("inferred_output", "output_extraction"),
    ("partial_logits", "vocabulary_size"), ("edited_plan", "intervention_plan")])
def test_packet_refusals(spec: dict, packet: dict, mutation: str, code: str) -> None:
    if mutation == "missing_grid":
        packet["readouts"].pop()
    elif mutation == "missing_output":
        packet["model_outputs"].pop()
    elif mutation == "missing_interventions":
        packet["interventions"] = []
    elif mutation == "unknown_layer":
        del packet["readouts"][0]["layer"]
    elif mutation == "unknown_method":
        packet["readouts"][0]["method"] = "fallback"
    elif mutation == "wrong_model":
        packet["model"]["revision"] = "0" * 40
    elif mutation == "bad_prompt_identity":
        packet["spec_sha256"] = "0" * 64
    elif mutation == "inferred_output":
        packet["model_outputs"][0]["extraction"] = "last_lens_layer"
    elif mutation == "partial_logits":
        packet["readouts"][0]["logits"] = [1., 2.]
    elif mutation == "edited_plan":
        packet["interventions"][0]["layer"] = 0
    with pytest.raises(methods.Refusal) as err:
        methods.build_report(spec, packet)
    assert err.value.code == code


def test_self_patch_checks_unrelated_logits_too(spec: dict, packet: dict) -> None:
    row = next(x for x in packet["interventions"] if x["control"] == "self")
    row["logits"][2], row["logits"][5] = row["logits"][5], row["logits"][2]
    with pytest.raises(methods.Refusal) as err:
        methods.build_report(spec, packet)
    assert err.value.code == "self_patch_identity"


def test_hosted_never_relabels_another_method_or_infers_layers() -> None:
    response = {"meta": {"layers_by_type": {"JPP_LENS": [0, 2]}}, "tokens": [
        {"results": [{"type": "JPP_LENS", "top_tokens": [["a"], ["b"]]}]}]}
    assert methods.strict_hosted_metadata(response, "jpp") == [0, 2]
    with pytest.raises(methods.Refusal):
        methods.strict_hosted_metadata(response, "j_lens")
    response["meta"]["layers_by_type"] = {}
    with pytest.raises(methods.Refusal):
        methods.strict_hosted_metadata(response, "jpp")


def test_exploratory_results_are_outside_legacy_collectors(tmp_path: Path) -> None:
    report = tmp_path / "exploratory_methods" / "exploratory_report.synthetic.json"
    report.parent.mkdir()
    report.write_text("{}")
    for pattern in ("**/batch_summary*.json", "**/verify_summary*.json", "trace_out/*/*.json"):
        assert not list(tmp_path.glob(pattern))


def test_cli_immutable_output_and_structured_invalid_input(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    args = ["--spec", str(FIXTURES / "synthetic_spec.json"), "--packet", str(FIXTURES / "synthetic_packet.json")]
    target = tmp_path / "exploratory_methods" / "exploratory_report.synthetic.json"
    assert methods.main(args + ["--out", str(target)]) == 0
    original = target.read_bytes()
    assert methods.main(args + ["--out", str(target)]) == 2
    assert target.read_bytes() == original
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
    assert methods.main(args + ["--out", str(tmp_path / "batch_summary.json")]) == 2


@pytest.mark.parametrize("value", [None, [], "not_an_object", 7])
def test_cli_malformed_top_level_has_named_refusal(
        tmp_path: Path, capsys: pytest.CaptureFixture, value: object) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(value))
    assert methods.main(["--spec", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "refused" and result["code"] == "invalid_input"


@pytest.mark.parametrize("field,value", [("model", None), ("methods", None), ("cases", [None])])
def test_cli_malformed_nested_objects_have_named_refusal(
        spec: dict, tmp_path: Path, capsys: pytest.CaptureFixture, field: str, value: object) -> None:
    spec[field] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(spec))
    assert methods.main(["--spec", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "refused" and result["code"] == "invalid_input"


@pytest.mark.parametrize("protected", [
    "trace_out", "data", "pilot", ".github", "ops", ".claude/hooks", ".githooks", ".git", "modes"])
def test_cli_protected_ancestors_never_get_written(
        tmp_path: Path, capsys: pytest.CaptureFixture, protected: str) -> None:
    destination = tmp_path / protected / "exploratory_methods" / "exploratory_report.synthetic.json"
    args = ["--spec", str(FIXTURES / "synthetic_spec.json"), "--out", str(destination)]
    assert methods.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "output_namespace"
    assert not destination.parent.exists()


def test_cli_output_requires_the_declared_namespace(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    destination = tmp_path / "elsewhere" / "exploratory_report.synthetic.json"
    assert methods.main(["--spec", str(FIXTURES / "synthetic_spec.json"), "--out", str(destination)]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "output_namespace"
    assert not destination.parent.exists()


def test_cli_symlink_cannot_hide_a_protected_output_root(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    protected = tmp_path / "data" / "exploratory_methods"
    protected.mkdir(parents=True)
    alias = tmp_path / "exploratory_methods"
    alias.symlink_to(protected, target_is_directory=True)
    destination = alias / "exploratory_report.synthetic.json"
    assert methods.main(["--spec", str(FIXTURES / "synthetic_spec.json"), "--out", str(destination)]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "output_namespace"
    assert not destination.exists()


def test_tied_rank_and_k_windows_follow_token_id_order() -> None:
    first = methods.rank_target([1., 1., 0.], {"id": "x", "role": "answer", "token_ids": [0]}, set(), [1, 2])
    second = methods.rank_target([1., 1., 0.], {"id": "y", "role": "answer", "token_ids": [1]}, {0}, [1, 2])
    assert first["raw_rank"] == 1 and second["raw_rank"] == 2
    assert second["filtered_rank"] == 1
    assert second["top_k"] == {"1": "not_observed_in_window", "2": "observed"}
    assert first["full_vocab_probability"] == second["full_vocab_probability"]


def test_tied_output_does_not_mark_a_later_id_as_top1(spec: dict, packet: dict) -> None:
    row = next(row for row in packet["model_outputs"] if row["variant"] == "source")
    row["logits"] = [3., 3., 1., 0., 0., -1.]
    result = methods.build_report(spec, packet)
    output = next(row for row in result["model_outputs"] if row["variant"] == "source")
    assert output["unpatched_answer_stratum"] == "not_top1"
    assert result["rank_tie_rule"] == "descending_logit_then_ascending_token_id"


@pytest.mark.parametrize("values", [[1, 1], [1, True], [2]])
def test_k_sensitivity_requires_distinct_valid_windows(spec: dict, values: list) -> None:
    spec["top_k"] = values
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "top_k"


@pytest.mark.parametrize("values", [[False], [True], [-1], [0.0]])
def test_fixed_layers_require_nonnegative_integer_indices(spec: dict, values: list) -> None:
    spec["fixed_layers"] = values
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "fixed_layers"


def test_different_transport_targets_refuse_a_paired_comparison(spec: dict) -> None:
    spec["model"]["n_layers"] = 4
    spec["methods"]["jpp"]["transport_target"] = 3
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "transport_mismatch"


@pytest.mark.parametrize("method", ["logit_lens", "j_lens", "jpp"])
@pytest.mark.parametrize("field,value", [("capture_site", "block_input"), ("final_norm", "none")])
def test_each_method_must_share_capture_and_norm_conventions(
        spec: dict, method: str, field: str, value: str) -> None:
    spec["methods"][method][field] = value
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "capture_mismatch"


def test_input_tokens_must_fit_the_complete_packet_vocabulary(spec: dict, packet: dict) -> None:
    variant = spec["cases"][0]["variants"]["source"]
    variant["token_ids"][0] = len(packet["vocabulary"])
    variant["token_sha256"] = methods.digest(variant["token_ids"])
    packet["spec_sha256"] = methods.digest(spec)
    with pytest.raises(methods.Refusal) as err:
        methods.build_report(spec, packet)
    assert err.value.code == "input_outside_vocab"


@pytest.mark.parametrize("invalid_id", [None, "", 0, False])
def test_target_annotation_ids_are_nonempty_strings(spec: dict, invalid_id: object) -> None:
    spec["cases"][0]["targets"][0]["id"] = invalid_id
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "target_ids"


def test_join_keeps_study_id_separate_from_repository_id(spec: dict) -> None:
    spec["model"]["study_id"] = "synthetic-short-id"
    spec["cases"][0]["join"]["model"] = "synthetic-short-id"
    assert methods.validate_spec(spec)["status"] == "validated"
    spec["cases"][0]["join"]["model"] = spec["model"]["id"]
    with pytest.raises(methods.Refusal) as err:
        methods.validate_spec(spec)
    assert err.value.code == "missing_join"


def test_character_offsets_cannot_reorder_the_input() -> None:
    with pytest.raises(methods.Refusal) as err:
        methods.span_positions([[0, 0], [3, 7], [0, 3]], [2, 6])
    assert err.value.code == "invalid_offsets"


def test_actual_legacy_reader_excludes_exploratory_files(tmp_path: Path) -> None:
    from scripts import backend_agreement

    report = tmp_path / "exploratory_report.synthetic.json"
    report.write_text(json.dumps({"results": [{"index": 99}]}))
    with pytest.raises(SystemExit, match="no batch_summary"):
        backend_agreement.load_run(str(tmp_path))
    legacy = tmp_path / "batch_summary.part_01.json"
    legacy.write_text(json.dumps({"backend": "hosted", "results": [{"index": 1}]}))
    rows, metadata = backend_agreement.load_run(str(tmp_path))
    assert set(rows) == {1}
    assert metadata["parts"] == metadata["n_results"] == 1


@pytest.mark.parametrize("field", ["layer", "position"])
@pytest.mark.parametrize("value", [False, 0.0])
def test_packet_indices_are_integers(spec: dict, packet: dict, field: str, value: object) -> None:
    packet["readouts"][0][field] = value
    with pytest.raises(methods.Refusal) as error:
        methods.build_report(spec, packet)
    assert error.value.code == "readout_grid"


def test_boolean_index_base_refuses(spec: dict) -> None:
    spec["layer_index_base"] = False
    with pytest.raises(methods.Refusal) as error:
        methods.validate_spec(spec)
    assert error.value.code == "capture_mismatch"


def test_fixture_retains_failed_and_already_top1_cases(spec: dict, packet: dict) -> None:
    report = methods.build_report(spec, packet)
    assert {x["unpatched_answer_stratum"] for x in report["model_outputs"]} == {"top1", "not_top1"}


@pytest.mark.parametrize("same_source", [True, False])
def test_relabelled_families_cannot_reuse_source_or_prompt_across_splits(spec: dict, same_source: bool) -> None:
    other = copy.deepcopy(spec["cases"][0])
    other.update(id="case-b", family_id="family-b", template_family="template-b", split="fresh_test")
    if same_source:
        for entry in other["variants"].values():
            entry["prompt"] += " extra"
            entry["prompt_sha256"] = methods.prompt_digest(entry["prompt"])
    else:
        other["join"]["index"] += 1
    spec["cases"].append(other)
    with pytest.raises(methods.Refusal) as error:
        methods.validate_spec(spec)
    assert error.value.code == "split_leakage"


@pytest.mark.parametrize("target_index,text", [(0, "different"), (0, "alphabet"), (1, "different tail")])
def test_target_matching_uses_actual_vocabulary_text(spec: dict, packet: dict, target_index: int, text: str) -> None:
    spec["cases"][0]["targets"][target_index]["text"] = text
    packet["spec_sha256"] = methods.digest(spec)
    with pytest.raises(methods.Refusal) as error:
        methods.build_report(spec, packet)
    assert error.value.code == "target_text_token_mismatch"


def test_unrelated_decoded_token_is_not_a_first_piece_proxy() -> None:
    assert methods.token_match("alpha", "different tail", [0, 1], 0) is None


@pytest.mark.parametrize("mutation", ["missing_reference", "wrong_reference", "size", "layer", "positions"])
def test_seeded_controls_must_match_their_declared_comparator(spec: dict, packet: dict, mutation: str) -> None:
    for collection in (spec["intervention_plan"], packet["interventions"]):
        row = next(item for item in collection if item["control"] == "random")
        if mutation == "missing_reference":
            row.pop("matched_to")
        elif mutation == "wrong_reference":
            row["matched_to"] = "rescue"
        elif mutation == "size":
            row["channels"] = methods.seeded_groups(4, 2, [row["seed"]], row["layer"])[0]["channels"]
        elif mutation == "layer":
            row["layer"] = 0
        else:
            row["positions"] = [[1, 1], [1, 1]]
    packet["spec_sha256"] = methods.digest(spec)
    with pytest.raises(methods.Refusal) as error:
        methods.build_report(spec, packet)
    expected_code = "intervention_plan" if mutation == "missing_reference" else "random_control_match"
    assert error.value.code == expected_code


def test_valid_random_control_link_survives_reporting(spec: dict, packet: dict) -> None:
    report = methods.build_report(spec, packet)
    random = [row for row in report["interventions"] if row["control"] == "random"]
    assert len(random) == 3 and all(row["matched_to"] == "channels" for row in random)
