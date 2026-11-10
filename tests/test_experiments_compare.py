"""Experiment comparison blocks, preview bundle and command line.

Offline, synthetic fixtures only. Expected differences are fractions worked out by hand from the integer
weights in tests/fixtures/experiments/build_fixtures.py (logit = ln(weight), so a probability is
weight / sum of weights). Agreement here shows the arithmetic and the bookkeeping on toy inputs; it says nothing
about any model.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.experiments import bundle as bundle_module
from scripts.experiments import capabilities, cli, common, compare, planner
from scripts.experiments.adapters import readout_exploratory
from scripts.experiments.common import Refusal
from scripts.experiments.store import RunStore

ENGINE = Path(__file__).resolve().parents[1]
FIXTURES = ENGINE / "tests" / "fixtures" / "experiments"
PROTOCOL = FIXTURES / "protocol_synthetic.json"
PLACEHOLDER_TEXT = ("alpha tail", "beta tail", "gamma tail", "alpha beta tail", "delta alpha tail", "omega")
MERGING_WORDS = ("understanding", "overall", "combined_score", "composite", "merged", "aggregate", "total_score")


@pytest.fixture
def protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


@pytest.fixture
def finished(protocol: dict, tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path / "run")
    store.run_fixture(planner.build_plan(protocol, capabilities.load_matrix()), "w0", fixtures_dir=FIXTURES,
                      protocol=protocol)
    store.collect()
    return store


def entry(comparison: dict, family: str, comparison_id: str, replicate: int = 0) -> dict:
    block = next(f for f in comparison["families"] if f["family_id"] == family)
    return next(e for e in block["comparisons"] if (e["comparison_id"], e["replicate"]) == (comparison_id, replicate))


def keys_of(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_of(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_of(v)}
    return set()


# ----------------------------------------------------------------------------------------------- compare

# (family, comparison) -> hand-computed t1 probabilities (a, b) as exact fractions of the weight sums.
T1_EXPECTED = {
    ("fam-1", "clinical_vs_colloquial"): (4 / 12, 2 / 12),      # +1/6
    ("fam-1", "colloquial_vs_normalized"): (2 / 12, 3 / 12),    # -1/12
    ("fam-2", "clinical_vs_colloquial"): (8 / 16, 2 / 16),      # +3/8
    ("fam-2", "colloquial_vs_normalized"): (2 / 16, 4 / 16),    # -1/8
    ("fam-3", "clinical_vs_colloquial"): (3 / 10, 3 / 10),      # 0
    ("fam-3", "colloquial_vs_normalized"): (3 / 10, 1 / 10),    # +1/5
}


def test_behaviour_block_is_the_signed_probability_difference(finished: RunStore) -> None:
    comparison = compare.compare_run(finished.run_dir)
    for (family, comparison_id), (a, b) in T1_EXPECTED.items():
        block = entry(comparison, family, comparison_id)["behavior"]
        t1 = block["targets"][0]
        assert block["status"] == "computed" and block["payload_kind"] == "behavior_next_token/1"
        assert (t1["target_id"], t1["token_id"]) == ("t1", 5)
        assert t1["a"] == pytest.approx(a, abs=1e-12) and t1["b"] == pytest.approx(b, abs=1e-12)
        assert t1["difference_a_minus_b"] == pytest.approx(a - b, abs=1e-12)
    assert entry(comparison, "fam-1", "clinical_vs_colloquial")["behavior"]["targets"][0][
        "difference_a_minus_b"] == pytest.approx(1 / 6, abs=1e-12)
    negative = entry(comparison, "fam-1", "colloquial_vs_normalized")["behavior"]["targets"][0]
    assert negative["difference_a_minus_b"] == pytest.approx(-1 / 12, abs=1e-12) and negative["difference_a_minus_b"] < 0
    # Identical logits on both sides: the difference is exactly zero and the block is still computed.
    zero = entry(comparison, "fam-3", "clinical_vs_colloquial")["behavior"]
    assert zero["status"] == "computed" and zero["targets"][0]["difference_a_minus_b"] == 0.0
    assert comparison["sign_convention"].startswith("difference_a_minus_b is the value for variant a minus")
    assert comparison["statistics"]["computed"] is False and comparison["seed"] == 7


def test_readout_block_keeps_raw_and_filtered_ranks_apart(finished: RunStore) -> None:
    comparison = compare.compare_run(finished.run_dir)
    block = entry(comparison, "fam-1", "clinical_vs_colloquial")["readout"]["logit_lens"]
    assert block["status"] == "computed" and block["payload_kind"] == "lens_readout_report/1"
    assert block["filter"]["excluded_token_ids"] == [6, 7] and (block["position_a"], block["position_b"]) == (1, 1)
    layer_1 = next(layer for layer in block["layers"] if layer["layer"] == 1)
    t1 = next(target for target in layer_1["targets"] if target["target_id"] == "t1")
    # a: logits [0,1,2,3,4,5,7,6] -> token 5 is third raw, first once tokens 6 and 7 are filtered out.
    assert (t1["a"]["raw_rank"], t1["a"]["filtered_rank"]) == (3, 1)
    assert t1["a"]["top_k"] == {"1": "not_observed_in_window", "2": "not_observed_in_window", "4": "observed"}
    # b: logits [5,4,3,2,1,0,7,6] -> token 5 is last of eight raw, sixth of six filtered: a top-k miss everywhere.
    assert (t1["b"]["raw_rank"], t1["b"]["filtered_rank"]) == (8, 6)
    assert set(t1["b"]["top_k"].values()) == {"not_observed_in_window"}
    c1 = next(target for target in layer_1["targets"] if target["target_id"] == "c1")
    # Token 3. a: beaten by tokens 4,5,6,7 raw (rank 5), by 4,5 filtered (rank 3). b: 5 raw winners, 3 filtered.
    assert (c1["a"]["raw_rank"], c1["a"]["filtered_rank"], c1["b"]["raw_rank"], c1["b"]["filtered_rank"]) == (5, 3, 6, 4)
    assert set(t1["a"]) == {"raw_rank", "filtered_rank", "excluded_candidate", "top_k"}
    # Each target row says which token its ranks are for, as the behaviour block does.
    assert (t1["token_id"], c1["token_id"]) == (5, 3)
    behaviour = entry(comparison, "fam-1", "clinical_vs_colloquial")["behavior"]["targets"]
    assert [(t["target_id"], t["token_id"]) for t in behaviour] == [
        (t["target_id"], t["token_id"]) for t in layer_1["targets"]]
    assert layer_1["targets_only_in_a"] == [] and layer_1["targets_only_in_b"] == []
    assert [layer["layer"] for layer in block["layers"]] == [0, 1]
    assert not {"rank_difference", "difference_a_minus_b", "mean_rank"} & keys_of(block)


def test_methods_that_did_not_run_are_listed_with_states_and_reasons(finished: RunStore) -> None:
    comparison = compare.compare_run(finished.run_dir)
    summary = {row["method"]: row for row in comparison["methods_not_run"]}
    assert set(summary) == {"j_lens", "jpp"}
    assert summary["j_lens"]["states"] == {"unsupported": 9} and summary["jpp"]["states"] == {"unavailable": 9}
    assert summary["jpp"]["reasons"][0].startswith("artifact identity unknown")
    one = entry(comparison, "fam-2", "clinical_vs_colloquial")
    assert [(row["method"], row["states"]) for row in one["methods_not_run"]] == [
        ("j_lens", {"a": "unsupported", "b": "unsupported"}), ("jpp", {"a": "unavailable", "b": "unavailable"})]
    assert all(row["reasons"]["a"] and row["reasons"]["b"] for row in one["methods_not_run"])
    for method in ("j_lens", "jpp"):
        assert one["readout"][method]["status"] == "not_computed" and "layers" not in one["readout"][method]


def test_no_block_is_merged_into_one_number(finished: RunStore) -> None:
    comparison = compare.compare_run(finished.run_dir)
    for family in comparison["families"]:
        for item in family["comparisons"]:
            assert set(item) == {"comparison_id", "a", "b", "replicate", "behavior", "readout", "references",
                                 "methods_not_run"}
            assert not [k for k, v in item.items() if isinstance(v, (int, float)) and k != "replicate"]
    names = keys_of(comparison) | keys_of(bundle_module.build_bundle(finished.run_dir))
    assert not [name for name in names if any(word in name.lower() for word in MERGING_WORDS)]
    assert "No block is combined with another" in comparison["block_rule"]


def test_a_missing_side_is_not_computed_and_never_zero(protocol: dict, tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run")
    plan = planner.build_plan(protocol, capabilities.load_matrix())
    # Plan order runs fam-1 clinical first: behaviour, j_lens (state only), jpp (state only), logit_lens.
    store.run_fixture(plan, "w0", fixtures_dir=FIXTURES, protocol=protocol, stop_after=2)
    store.collect()
    comparison = compare.compare_run(store.run_dir)
    block = entry(comparison, "fam-1", "clinical_vs_colloquial")["behavior"]
    assert block == {"status": "not_computed", "states": {"a": "completed", "b": "not_run"},
                     "reasons": {"a": None, "b": "planned task has no envelope in the collected run"}}
    assert "difference_a_minus_b" not in keys_of(comparison)
    assert {row["method"]: row["states"] for row in comparison["methods_not_run"]}["behavior_next_token"] == {
        "not_run": 8}


def test_replicates_are_reported_side_by_side(protocol: dict, tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run")
    plan = planner.build_plan(protocol, capabilities.load_matrix(), replicates=2)
    store.run_fixture(plan, "w0", fixtures_dir=FIXTURES, protocol=protocol)
    store.collect()
    comparison = compare.compare_run(store.run_dir)
    family = comparison["families"][0]
    assert [(e["comparison_id"], e["replicate"]) for e in family["comparisons"]] == [
        ("clinical_vs_colloquial", 0), ("clinical_vs_colloquial", 1),
        ("colloquial_vs_normalized", 0), ("colloquial_vs_normalized", 1)]
    first, second = (entry(comparison, "fam-1", "clinical_vs_colloquial", r)["behavior"] for r in (0, 1))
    assert first == second and "mean" not in keys_of(comparison)


def ica_payload(basis: str, scores: dict[int, float], complete: bool = True, position: int = 2) -> dict:
    return {"kind": "ica_scores/1", "basis": {"manifest_sha256": basis}, "components_complete": complete,
            "scores": [{"layer": 1, "position": position, "component": c, "score": s} for c, s in scores.items()]}


def test_ica_block_gives_signed_differences_and_labelled_energy_shares() -> None:
    block = compare.ica_block(ica_payload("a" * 64, {0: 3.0, 1: 4.0}), ica_payload("a" * 64, {0: -1.0, 1: 0.0}, position=1))
    assert block["energy_share_label"] == "squared-coordinate share, not a probability"
    layer = block["layers"][0]
    assert (layer["layer"], layer["position_a"], layer["position_b"]) == (1, 2, 1)
    zero, one = layer["components"]
    # 3 - (-1) = 4 and 4 - 0 = 4. Shares for a: 9/25 and 16/25. For b: 1/1 and 0/1.
    assert (zero["difference_a_minus_b"], one["difference_a_minus_b"]) == (4.0, 4.0)
    assert (zero["energy_share_a"], one["energy_share_a"]) == pytest.approx((9 / 25, 16 / 25))
    assert (zero["energy_share_b"], one["energy_share_b"]) == (1.0, 0.0)
    opposite = compare.ica_block(ica_payload("a" * 64, {0: -2.0}), ica_payload("a" * 64, {0: 0.5}))
    assert opposite["layers"][0]["components"][0]["difference_a_minus_b"] == -2.5


def test_ica_block_refuses_two_bases_and_keeps_missing_values_missing() -> None:
    with pytest.raises(Refusal) as caught:
        compare.ica_block(ica_payload("a" * 64, {0: 1.0}), ica_payload("b" * 64, {0: 1.0}))
    assert caught.value.code == "basis_mismatch"
    with pytest.raises(Refusal) as caught:
        compare.ica_block(ica_payload("a" * 64, {0: 1.0}), ica_payload("not-a-hash", {0: 1.0}))
    assert caught.value.code == "basis_identity"
    partial = compare.ica_block(ica_payload("a" * 64, {0: 1.0, 1: 2.0}, complete=False), ica_payload("a" * 64, {0: 1.0}))
    components = partial["layers"][0]["components"]
    assert components[1]["score_b"] is None and components[1]["difference_a_minus_b"] is None
    assert components[0]["energy_share_a"] is None
    assert partial["layers"][0]["energy_share_status_a"] == "not_computed_component_list_incomplete"
    silent = compare.ica_block(ica_payload("a" * 64, {0: 0.0}), ica_payload("a" * 64, {0: 0.0}))
    assert silent["layers"][0]["components"][0]["energy_share_a"] is None
    assert silent["layers"][0]["energy_share_status_a"] == "not_computed_zero_or_non_finite_energy"


def test_a_block_reads_only_its_own_payload_kind(finished: RunStore) -> None:
    rows = finished.read_collected()["assembly"]["tasks"]
    lens = finished.read_payload(next(r["payload"] for r in rows if r["method"] == "logit_lens"))
    behaviour = finished.read_payload(next(r["payload"] for r in rows if r["method"] == "behavior_next_token"))
    for builder, a, b in ((compare.behavior_block, lens, lens), (compare.readout_block, behaviour, behaviour),
                          (compare.ica_block, lens, behaviour)):
        with pytest.raises(Refusal) as caught:
            builder(a, b)
        assert caught.value.code == "payload_kind"
    other_filter = copy.deepcopy(lens)
    other_filter["filter"]["excluded_token_ids"] = [7]
    with pytest.raises(Refusal) as caught:
        compare.readout_block(lens, other_filter)
    assert caught.value.code == "filter_mismatch"


def test_readout_block_refuses_two_tokens_under_one_target_id_and_lists_one_sided_targets(finished: RunStore) -> None:
    # Regression: the block carried no token_id, did not compare tokens between a and b, and dropped a target
    # present on one side only.
    rows = finished.read_collected()["assembly"]["tasks"]
    a = finished.read_payload(next(r["payload"] for r in rows if (r["method"], r["family_id"], r["variant"]) == (
        "logit_lens", "fam-1", "clinical")))
    b = finished.read_payload(next(r["payload"] for r in rows if (r["method"], r["family_id"], r["variant"]) == (
        "logit_lens", "fam-1", "colloquial")))
    other_token = copy.deepcopy(b)
    for row in other_token["readouts"]:
        row["scores"][0]["token_id"] = 2
    with pytest.raises(Refusal) as caught:
        compare.readout_block(a, other_token)
    assert caught.value.code == "payload_mismatch" and "token 5" in str(caught.value) and "token 2" in str(caught.value)
    one_sided = copy.deepcopy(b)
    for row in one_sided["readouts"]:
        row["scores"] = [score for score in row["scores"] if score["target_id"] != "c1"]
    block = compare.readout_block(a, one_sided)
    for layer in block["layers"]:
        assert [t["target_id"] for t in layer["targets"]] == ["t1"]
        assert (layer["targets_only_in_a"], layer["targets_only_in_b"]) == (["c1"], [])


def test_a_readout_fixture_that_scores_another_token_does_not_complete(protocol: dict, tmp_path: Path) -> None:
    # Regression: the protocol declared t1 as token 2 while readout_spec.json (outside the protocol and its
    # digest) scores t1 on token 5; all 18 tasks completed and the comparison showed two tokens under one id.
    for family in protocol["case_families"]:
        for target in family["targets"]:
            if target["id"] == "t1":
                target["token_ids"] = [2]
    store = RunStore(tmp_path / "run")
    summary = store.run_fixture(planner.build_plan(protocol, capabilities.load_matrix()), "w0", fixtures_dir=FIXTURES,
                                protocol=protocol)
    assert summary["by_state"]["completed"] == 9 and summary["by_state"]["invalid"] == 9
    reasons = {common.read_json(p)["status"]["reason"].split(":")[0] for p in store.envelope_files()
               if common.read_json(p)["status"]["execution"] == "invalid"}
    assert reasons == {"missing_targets"}
    store.collect()
    comparison = compare.compare_run(store.run_dir)
    block = entry(comparison, "fam-1", "clinical_vs_colloquial")
    assert block["readout"]["logit_lens"]["status"] == "not_computed"
    assert block["behavior"]["status"] == "computed" and block["behavior"]["targets"][0]["token_id"] == 2
    # Renamed target ids: the readout rows name ids the protocol does not contain, so they do not complete either.
    renamed = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    for family in renamed["case_families"]:
        for target in family["targets"]:
            target["id"] = "renamed_" + target["id"]
    renamed["primary_endpoint"]["target"] = "renamed_t1"
    other = RunStore(tmp_path / "renamed")
    summary = other.run_fixture(planner.build_plan(renamed, capabilities.load_matrix()), "w0", fixtures_dir=FIXTURES,
                                protocol=renamed)
    assert summary["by_state"]["completed"] == 9 and summary["by_state"]["invalid"] == 9


# ------------------------------------------------------------------------------------------------ bundle

def test_bundle_is_schema_valid_deterministic_and_labelled(finished: RunStore) -> None:
    first, second = bundle_module.build_bundle(finished.run_dir), bundle_module.build_bundle(finished.run_dir)
    assert common.json_bytes(first) == common.json_bytes(second)
    assert common.structural_errors(first, "bundle") == []
    assert first["schema_version"] == "patientwords.experiment-bundle/1"
    assert first["limitations"][0] == "synthetic_not_measurement"
    assert first["evidence"] == {"evidence_class": "synthetic_fixture", "clinical_review": "not_applicable_synthetic",
                                 "visibility": "not_published", "restriction_reasons": [], "analysis_memberships": [],
                                 "synthetic": True}
    assert first["execution"]["by_state"] == {"not_run": 0, "unsupported": 9, "unavailable": 9, "invalid": 0,
                                              "failed": 0, "completed": 18}
    assert first["plan_totals"]["by_planned_state"] == {"ready": 18, "unsupported": 9, "unavailable": 9}
    assert first["plan_totals"]["runtime_seconds_estimate"] is None
    rows = {(r["method"], r["planned_state"]): r for r in first["capability_rows"]}
    assert set(rows) == {("behavior_next_token", "ready"), ("logit_lens", "ready"), ("j_lens", "unsupported"),
                         ("jpp", "unavailable")}
    assert all(row["tasks"] == 9 and row["evidence"] for row in rows.values())
    # Every capability row says whether the matrix row names the protocol's model revision.
    assert {row["revision_match"] for row in rows.values()} == {"exact"}
    assert first["execution"]["ready_complete"] is True and first["execution"]["attempt_outcomes_differ"] == []
    assert first["execution"]["ended_line_missing"] == []
    assert len(first["provenance"]["payloads"]) == 18
    assert first["provenance"]["protocol_sha256"] == first["protocol"]["sha256"]
    assert first["provenance"]["comparison_sha256"] == common.digest(compare.compare_run(finished.run_dir))
    assert "scripts/exploratory_methods.py" in first["provenance"]["source_files_sha256"]
    assert "generated_utc" not in keys_of(first)


def test_bundle_copies_no_prompt_or_target_text(finished: RunStore) -> None:
    text = json.dumps(bundle_module.build_bundle(finished.run_dir))
    assert not [phrase for phrase in PLACEHOLDER_TEXT if phrase in text]
    for path in finished.envelope_files():
        assert not [phrase for phrase in PLACEHOLDER_TEXT if phrase in path.read_text(encoding="utf-8")]


def test_bundle_of_an_incomplete_run_says_so(protocol: dict, tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run")
    store.run_fixture(planner.build_plan(protocol, capabilities.load_matrix()), "w0", fixtures_dir=FIXTURES,
                      protocol=protocol, stop_after=1)
    store.collect()
    built = bundle_module.build_bundle(store.run_dir)
    assert "incomplete_run_some_planned_tasks_have_no_envelope" in built["limitations"]
    assert built["execution"]["complete"] is False and built["execution"]["by_state"]["not_run"] > 0


# --------------------------------------------------------------------------------------------------- CLI

def invoke(capsys: pytest.CaptureFixture, *argv: object) -> tuple[int, dict]:
    code = cli.main([str(a) for a in argv])
    return code, json.loads(capsys.readouterr().out)


def test_cli_full_slice_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    plan_path, run_dir = tmp_path / "plan.json", tmp_path / "runs" / "synthetic-slice-1"
    code, out = invoke(capsys, "validate", "--protocol", PROTOCOL)
    assert (code, out["status"]) == (0, "validated")
    code, out = invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", plan_path)
    assert (code, out["status"], out["totals"]["tasks"]) == (0, "planned", 36)
    first_bytes = plan_path.read_bytes()
    assert invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", plan_path)[0] == 0
    assert plan_path.read_bytes() == first_bytes

    code, out = invoke(capsys, "compare", "--run-dir", run_dir, "--out", tmp_path / "comparison.json")
    assert (code, out["status"], out["code"]) == (2, "refused", "not_collected")
    code, out = invoke(capsys, "run-fixture", "--plan", plan_path, "--fixtures", FIXTURES, "--run-dir", run_dir,
                       "--stop-after", 2)
    assert (code, out["executed"], out["reused"], out["stopped_early"]) == (0, 2, 0, True)
    code, out = invoke(capsys, "collect", "--run-dir", run_dir, "--require-complete")
    assert (code, out["complete"]) == (1, False) and len(out["missing"]) == 32
    code, out = invoke(capsys, "run-fixture", "--plan", plan_path, "--fixtures", FIXTURES, "--run-dir", run_dir)
    assert (code, out["executed"], out["reused"], out["remaining_ready"]) == (0, 16, 2, 0)
    code, out = invoke(capsys, "collect", "--run-dir", run_dir, "--require-complete")
    assert (code, out["complete"], out["by_state"]["completed"], out["reused_events"]) == (0, True, 18, 2)
    code, out = invoke(capsys, "compare", "--run-dir", run_dir, "--out", tmp_path / "comparison.json")
    assert (code, out["behavior_blocks_computed"], out["readout_blocks_computed"], out["ica_blocks_computed"]) == (
        0, 6, 6, 0)
    code, out = invoke(capsys, "bundle", "--run-dir", run_dir, "--out", tmp_path / "bundle.json")
    assert (code, out["status"], out["families"]) == (0, "bundled", 3)
    assert common.structural_errors(common.read_json(tmp_path / "bundle.json"), "bundle") == []


def test_cli_refusals_print_json_and_exit_two(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    broken = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    del broken["seed"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(broken), encoding="utf-8")
    code, out = invoke(capsys, "validate", "--protocol", bad)
    assert code == 2 and set(out) == {"status", "code", "detail"}
    assert (out["status"], out["code"]) == ("refused", "missing_seed")
    assert invoke(capsys, "validate", "--protocol", tmp_path / "absent.json") == (
        2, {"status": "refused", "code": "unreadable_input",
            "detail": f"protocol {tmp_path / 'absent.json'}: No such file or directory"})
    bad.write_text("{not json", encoding="utf-8")
    assert invoke(capsys, "validate", "--protocol", bad)[1]["code"] == "invalid_input"
    code, out = invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", tmp_path / "trace_out" / "plan.json")
    assert (code, out["code"]) == (2, "protected_root")
    code, out = invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", ENGINE / "plan.json")
    assert (code, out["code"]) == (2, "git_checkout") and not (ENGINE / "plan.json").exists()
    code, out = invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", tmp_path / "plan.json", "--replicates", 0)
    assert (code, out["code"]) == (2, "replicates")
    code, out = invoke(capsys, "collect", "--run-dir", tmp_path / "empty")
    assert (code, out["code"]) == (2, "no_plan")


def test_cli_allow_root_admits_a_checkout_directory_but_not_a_protected_one(tmp_path: Path,
                                                                           capsys: pytest.CaptureFixture) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    allowed = checkout / "experiment_runs"
    code, out = invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", allowed / "plan.json")
    assert (code, out["code"]) == (2, "git_checkout")
    code, out = invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", allowed / "plan.json", "--allow-root", allowed)
    assert code == 0
    code, out = invoke(capsys, "run-fixture", "--plan", allowed / "plan.json", "--fixtures", FIXTURES, "--run-dir",
                       allowed / "run")
    assert (code, out["code"]) == (2, "git_checkout")
    code, out = invoke(capsys, "run-fixture", "--plan", allowed / "plan.json", "--fixtures", FIXTURES, "--run-dir",
                       allowed / "run", "--allow-root", allowed)
    assert (code, out["executed"]) == (0, 18)
    code, out = invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", checkout / "data" / "plan.json",
                       "--allow-root", checkout)
    assert (code, out["code"]) == (2, "protected_root")


def test_cli_run_fixture_exits_one_when_an_attempt_fails(tmp_path: Path, capsys: pytest.CaptureFixture,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    plan_path = tmp_path / "plan.json"
    invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", plan_path)
    monkeypatch.setattr(readout_exploratory.ADAPTER, "execute_fixture",
                        lambda task, context: (_ for _ in ()).throw(RuntimeError("placeholder failure")))
    code, out = invoke(capsys, "run-fixture", "--plan", plan_path, "--fixtures", FIXTURES, "--run-dir", tmp_path / "run")
    assert code == 1 and out["by_state"]["failed"] == 9 and out["by_state"]["completed"] == 9


def test_cli_incompatible_resume_and_new_run_dir(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    plan_path, run_dir = tmp_path / "plan.json", tmp_path / "run"
    invoke(capsys, "plan", "--protocol", PROTOCOL, "--out", plan_path)
    invoke(capsys, "run-fixture", "--plan", plan_path, "--fixtures", FIXTURES, "--run-dir", run_dir, "--stop-after", 1)
    changed = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    changed["seed"] = 11
    changed_path, changed_plan = tmp_path / "changed.json", tmp_path / "changed_plan.json"
    changed_path.write_text(json.dumps(changed), encoding="utf-8")
    invoke(capsys, "plan", "--protocol", changed_path, "--out", changed_plan)
    args = ("run-fixture", "--plan", changed_plan, "--fixtures", FIXTURES, "--protocol", changed_path, "--run-dir",
            run_dir)
    code, out = invoke(capsys, *args)
    assert (code, out["code"]) == (2, "incompatible_resume")
    code, out = invoke(capsys, *args, "--new-run-dir")
    new_dir = Path(out["run_dir"])
    assert code == 0 and out["executed"] == 18 and new_dir != run_dir and new_dir.parent == run_dir.parent
    assert new_dir.name == f"run__{common.digest(changed)[:12]}"
    # The first directory is untouched: one execution, one plan of the first protocol.
    assert common.read_json(run_dir / "plan.json")["seed"] == 7
    code, out = invoke(capsys, "run-fixture", "--plan", changed_plan, "--fixtures", FIXTURES, "--run-dir", tmp_path / "r3")
    assert (code, out["code"]) == (2, "protocol_not_found")


def test_cli_unevaluable_seal_is_exit_three_not_a_refusal(tmp_path: Path, capsys: pytest.CaptureFixture,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import results_policy

    def broken(_doc: object) -> dict:
        raise results_policy.SealError("placeholder: seal inputs unreadable")

    monkeypatch.setattr(cli, "validate_protocol", broken)
    code, out = invoke(capsys, "validate", "--protocol", PROTOCOL)
    assert (code, out["status"], out["code"]) == (3, "config_error", "SealError")


def test_cli_capabilities_prints_matrix_rows(capsys: pytest.CaptureFixture) -> None:
    code, out = invoke(capsys, "capabilities", "--model", "qwen3-4b")
    assert code == 0 and out["schema_version"] == "patientwords.capability-matrix/1"
    assert sorted((row["method"], row["backend"]) for row in out["rows"]) == [
        ("attribution_graph", "hosted_neuronpedia"), ("behavior_next_token", "cpu_transformers"),
        ("j_lens", "cpu_transformers"), ("jpp", "cpu_transformers")]
    assert all(row["model"]["hf_id"] == "Qwen/Qwen3-4B" for row in out["rows"])
    code, everything = invoke(capsys, "capabilities")
    assert code == 0 and len(everything["rows"]) == len(capabilities.load_matrix()["rows"])


def test_module_entry_point_runs_as_documented(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, "-m", "scripts.experiments.cli", "plan", "--protocol", str(PROTOCOL),
                           "--out", str(tmp_path / "plan.json")], cwd=ENGINE, capture_output=True, text=True,
                          check=False, env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["totals"]["by_planned_state"] == {"ready": 18, "unsupported": 9, "unavailable": 9}
    refused = subprocess.run([sys.executable, "-m", "scripts.experiments.cli", "collect", "--run-dir",
                              str(tmp_path / "none")], cwd=ENGINE, capture_output=True, text=True, check=False,
                             env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
    assert refused.returncode == 2 and json.loads(refused.stdout)["status"] == "refused"
