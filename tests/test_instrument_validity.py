"""Offline checks of the instrument-validity scorer against a synthetic bundle; no model, service or study data.

Every expected number below was worked out by hand from the design of
tests/fixtures/instrument_validity/synthetic_bundle.v1.json, which is:

* Six families, two per split: family_1 and family_2 discovery, family_3 and family_4 validation, family_5 and
  family_6 fresh_test. Each has four reference facts, so a fact-recovery rate is a multiple of 1/4 (1/8 with the
  partial credit of 0.5).
* Fact-recovery rates (medical, everyday) per stage:
    activation  f1 1, 1      f2 1, 1/2      f3 3/4, 3/4  f4 1, 3/4      f5 1, 1/2    f6 1/2, 3/4
    readout     f1 1, 1      f2 3/4, 3/4    f3 1, 1      f4 1/2, 1/2    f5 1, 1      f6 3/4, 1/2
    label       f1 3/4, 3/4  f2 7/8, 3/4    f3 1, 1      f4 3/4, 3/4    f5 1/2, 1/2  f6 1, (row absent)
    score       every family 1, 1
  family_2's label rates use one "partially" (3 + 0.5 = 3.5 of 4) and one "contradicted" (3 of 4).
* Behaviour (medical, everyday), threshold 0.125: f1 0.75, 0.75; f2 0.75, 0.6875; f3 0.875, 0.5; f4 0.625, 0.625;
  f5 0.625, 0.25; f6 0.75, 0.75. Changed (difference above 0.125): family_3 and family_5 only.
* Representation value (medical, everyday), threshold 0.25:
    activation  f1 1, 1  f2 1, 0.25  f3 0.5, 0.375  f4 0.875, 0.25  f5 1.25, 0.125  f6 0.5, 0.5
    readout     f1 0.5, 0.5  f2 0.625, 0.5  f3 0.875, 0.25  f4 0.25, 0.25  f5 0.75, 0.125  f6 0.5, 0.5
  The label and score stages declare no representation threshold.
* Held artifact (score stage): medical-description score minus everyday-description score is 0.25 for five
  artifacts; family_5 has two artifacts, 0.375 and 0.125, which average to 0.25.
* Margins: 0.2 for the fact-recovery difference, 0.125 for the held-artifact difference. 2,000 resamples at 0.95,
  so the percentile index is k = 0.025 * 2000 = 50. Seed 7.
"""
from __future__ import annotations

import copy
import json
import math
import random
from pathlib import Path

import pytest

from scripts import instrument_validity as iv

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "instrument_validity" / "synthetic_bundle.v1.json"
RUBRIC = ROOT / "data" / "protocols" / "instrument_validity_rubric.draft.json"
FAMILIES = [f"family_{n}" for n in range(1, 7)]
Z95 = 1.959963984540054


@pytest.fixture
def bundle() -> dict:
    return iv.load_bundle(FIXTURE)


@pytest.fixture(scope="module")
def report() -> dict:
    return iv.score_bundle(iv.load_bundle(FIXTURE))


def recovery(report: dict, stage: str, name: str = "all") -> dict:
    return report["stages"][stage]["fact_recovery"]["analysis_sets"][name]


def differences(report: dict, stage: str) -> dict:
    return {row["family_id"]: row["difference"] for row in report["stages"][stage]["fact_recovery"]["per_family"]}


def independent_interval(values: list[float], seed_label: str, resamples: int = 2000, k: int = 50) -> list[float]:
    """The documented bootstrap, written again here so the scorer's interval is checked against a second copy."""
    rng = random.Random(seed_label)
    means = []
    for _ in range(resamples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        means.append(math.fsum(draw) / len(draw))
    means.sort()
    return [means[k], means[resamples - 1 - k]]


def refusal_code(bundle: dict) -> str:
    with pytest.raises(iv.Refusal) as caught:
        iv.score_bundle(bundle)
    return caught.value.code


def observation(bundle: dict, stage: str, variant_id: str) -> dict:
    return next(row for row in bundle["stages"][stage]["observations"] if row["variant_id"] == variant_id)


# --------------------------------------------------------------------------------------- labels and structure

def test_fixture_validates_and_the_report_never_calls_itself_a_measurement(bundle: dict, report: dict) -> None:
    record = iv.validate_bundle(bundle)
    assert record["status"] == "validated"
    assert record["families_by_split"] == {"discovery": FAMILIES[:2], "validation": FAMILIES[2:4],
                                           "fresh_test": FAMILIES[4:]}
    assert record["stages_supplied"] == ["activation", "readout", "label", "score"]
    assert report["synthetic"] is True
    assert report["execution_status"] == "synthetic"
    assert report["evidence_label"] == "synthetic software fixture - not a research result"
    assert report["benchmark_status"] == ("proposed PatientWords contribution; "
                                          "no register bias has been measured with it")
    assert "synthetic_not_measurement" in report["limitations"]
    assert '"measurement"' not in json.dumps(report)
    assert report["bundle_sha256"] == record["bundle_sha256"]


def test_schema_file_stays_inside_the_stdlib_subset_and_rejects_unknown_keys(bundle: dict) -> None:
    errors: list[str] = []
    iv.check_schema_subset(lambda *args: errors.append(args[1]), "bundle", bundle, iv.load_schema())
    assert errors == []
    bundle["families"][0]["outcome_note"] = "not in the contract"
    assert refusal_code(bundle) == "schema"


def test_rubric_values_match_the_scorer() -> None:
    rubric = json.loads(RUBRIC.read_text(encoding="utf-8"))
    assert rubric["schema"] == "patientwords.instrument-validity-rubric/1"
    assert rubric["status"] == "draft - not validated; no human calibration has been run"
    items = rubric["items"]
    assert tuple(v["value"] for v in items["fact_recovery"]["values"]) == iv.FACT_STATUSES
    assert items["fact_recovery"]["missing_value"]["recorded_as"] is None
    assert {v["value"] for v in items["changed_fact_sensitivity"]["derived_outcomes"]} == {
        "detected", "not_detected", "base_not_recovered", "undetermined"}
    assert set(iv.PAIRED_REGISTERS) <= {v["value"] for v in items["description_register"]["values"]}
    assert set(items) == {"fact_recovery", "unsupported_inferred_facts", "changed_fact_sensitivity",
                          "description_register"}
    assert rubric["annotator_blinding"]["fields"] and rubric["disagreement"]["rules"]
    instructions = " ".join(rubric["general_instructions"])
    assert "Clinical wording is not the answer key" in instructions
    assert "A fluent medical label is not credit by itself" in instructions


# ------------------------------------------------------------------------------- fact recovery, by hand

def test_paired_differences_and_means_match_the_hand_computation(report: dict) -> None:
    assert differences(report, "activation") == {"family_1": 0.0, "family_2": 0.5, "family_3": 0.0,
                                                 "family_4": 0.25, "family_5": 0.5, "family_6": -0.25}
    assert differences(report, "readout") == {**dict.fromkeys(FAMILIES[:5], 0.0), "family_6": 0.25}
    assert differences(report, "label") == {"family_1": 0.0, "family_2": 0.125, "family_3": 0.0, "family_4": 0.0,
                                            "family_5": 0.0, "family_6": None}
    assert differences(report, "score") == dict.fromkeys(FAMILIES, 0.0)
    # activation: (0 + 0.5 + 0 + 0.25 + 0.5 - 0.25) / 6 = 1/6; readout: 0.25 / 6; label: 0.125 / 5; score: 0
    assert recovery(report, "activation")["mean_difference"] == pytest.approx(1 / 6)
    assert recovery(report, "readout")["mean_difference"] == pytest.approx(0.25 / 6)
    assert recovery(report, "label")["mean_difference"] == pytest.approx(0.025)
    assert recovery(report, "score")["mean_difference"] == 0.0
    # by set, activation: discovery (0 + 0.5) / 2; held out (0 + 0.25 + 0.5 - 0.25) / 4;
    # comparable behaviour = families 1, 2, 4, 6: (0 + 0.5 + 0.25 - 0.25) / 4
    assert recovery(report, "activation", "discovery")["mean_difference"] == 0.25
    assert recovery(report, "activation", "held_out")["mean_difference"] == 0.125
    assert recovery(report, "activation", "comparable_behaviour")["mean_difference"] == 0.125
    assert report["analysis_sets"]["comparable_behaviour"]["family_ids"] == ["family_1", "family_2", "family_4",
                                                                             "family_6"]
    assert report["analysis_sets"]["held_out"] == {"family_ids": FAMILIES[2:], "contains_discovery_families": False}
    assert report["analysis_sets"]["all"]["contains_discovery_families"] is True


def test_partial_credit_and_contradiction_are_scored_as_declared(report: dict) -> None:
    row = next(r for r in report["stages"]["label"]["fact_recovery"]["per_family"] if r["family_id"] == "family_2")
    assert row["medical_rate"] == 0.875     # recovered, recovered, recovered, partially: (3 + 0.5) / 4
    assert row["everyday_rate"] == 0.75     # recovered, recovered, recovered, contradicted: 3 / 4


def test_missing_observation_is_excluded_with_its_reason_and_never_scored_as_zero(report: dict) -> None:
    label = recovery(report, "label")
    assert (label["n_families"], label["n_included"]) == (6, 5)
    assert label["excluded"] == [{"family_id": "family_6", "reason": "missing_observation:everyday"}]
    row = report["stages"]["label"]["fact_recovery"]["per_family"][5]
    assert (row["medical_rate"], row["everyday_rate"], row["difference"]) == (1.0, None, None)
    assert report["stages"]["label"]["unsupported_facts"]["by_register"]["everyday"]["n_absent_rows"] == 1
    # had the absent row been read as zero recovery, family_6 would add 1.0 and the mean would be 1.125 / 6
    assert label["mean_difference"] != pytest.approx(1.125 / 6)


def test_unassessed_fact_and_missing_count_are_recorded_as_missing(bundle: dict) -> None:
    row = observation(bundle, "activation", "f2_medical")
    row["fact_recovery"]["fact_c"] = None
    row["unsupported_facts"] = None
    del observation(bundle, "activation", "f4_everyday")["fact_recovery"]["fact_d"]
    result = iv.score_bundle(bundle)
    activation = recovery(result, "activation")
    assert activation["excluded"] == [{"family_id": "family_2", "reason": "missing_fact_recovery:medical"},
                                      {"family_id": "family_4", "reason": "missing_fact_recovery:everyday"}]
    assert activation["mean_difference"] == pytest.approx((0 + 0 + 0.5 - 0.25) / 4)   # families 1, 3, 5, 6
    counts = result["stages"]["activation"]["unsupported_facts"]
    assert counts["by_register"]["medical"]["n_missing_count"] == 1
    assert counts["by_register"]["medical"]["mean_per_description"] == pytest.approx(2 / 5)
    assert counts["paired_medical_minus_everyday"]["all"]["excluded"] == [
        {"family_id": "family_2", "reason": "missing_unsupported_count:medical"}]


# ------------------------------------------------------------------------------------ verdicts and intervals

def test_three_verdict_outcomes_and_no_equivalence_from_non_significance() -> None:
    assert iv.equivalence_verdict([-0.05, 0.1], 0.2) == "equivalent_within_margin"
    assert iv.equivalence_verdict([0.25, 0.4], 0.2) == "different_beyond_margin"
    assert iv.equivalence_verdict([-0.6, -0.3], 0.2) == "different_beyond_margin"
    # wide intervals that include zero are "not significant"; they are inconclusive, never equivalent
    assert iv.equivalence_verdict([-0.5, 0.5], 0.2) == "inconclusive"
    assert iv.equivalence_verdict([-0.1, 0.3], 0.2) == "inconclusive"
    # excludes zero but straddles the margin: still inconclusive
    assert iv.equivalence_verdict([0.1, 0.3], 0.2) == "inconclusive"
    # the margin itself is outside the equivalence region
    assert iv.equivalence_verdict([-0.2, 0.2], 0.2) == "inconclusive"


def test_fixture_verdicts(report: dict) -> None:
    activation = recovery(report, "activation")
    # mean 1/6, family values spread from -0.25 to 0.5: the interval crosses the 0.2 margin and stays above -0.2
    assert activation["verdict"] == "inconclusive"
    assert -0.2 < activation["interval"][0] < 0.2 < activation["interval"][1]
    assert activation["interval_excludes_zero"] is False
    # label: every resampled mean lies in [0, 0.125 / 5 * 5] = [0, 0.125], inside the 0.2 margin whatever the seed
    label = recovery(report, "label")
    assert label["verdict"] == "equivalent_within_margin"
    assert 0.0 <= label["interval"][0] <= label["interval"][1] <= 0.125
    assert recovery(report, "readout")["verdict"] == "equivalent_within_margin"
    # score: all six differences are 0, so every resampled mean is 0
    score = recovery(report, "score")
    assert (score["interval"], score["verdict"]) == ([0.0, 0.0], "equivalent_within_margin")
    assert report["verdict_rule"].endswith("A non-significant difference is never reported as equivalence.")


def test_interval_matches_an_independent_bootstrap(report: dict) -> None:
    activation = recovery(report, "activation")
    assert activation["seed_label"] == "7:activation:fact_recovery_rate_difference:all"
    assert activation["interval"] == independent_interval([0.0, 0.5, 0.0, 0.25, 0.5, -0.25],
                                                          "7:activation:fact_recovery_rate_difference:all")
    held_out = recovery(report, "activation", "held_out")
    assert held_out["interval"] == independent_interval([0.0, 0.25, 0.5, -0.25],
                                                        "7:activation:fact_recovery_rate_difference:held_out")
    label = recovery(report, "label")      # family_6 is excluded, so five values are resampled
    assert label["interval"] == independent_interval([0.0, 0.125, 0.0, 0.0, 0.0],
                                                     "7:label:fact_recovery_rate_difference:all")
    assert report["randomness"] == {"generator": "random.Random",
                                    "seed_rule": "'<seed>:<stage>:<endpoint>:<analysis set>'",
                                    "interval": "family-clustered percentile bootstrap of the mean",
                                    "bootstrap_resamples": 2000, "confidence_level": 0.95}


def test_sets_below_the_minimum_family_count_get_no_interval_and_no_equivalence(report: dict) -> None:
    for stage in ("activation", "readout", "label", "score"):
        for name in ("discovery", "validation", "fresh_test"):       # two families each; the plan's minimum is 3
            summary = recovery(report, stage, name)
            assert summary["interval"] is None
            assert summary["verdict"] == "inconclusive"
            assert summary["interval_status"] == "not_computed_fewer_than_minimum_families"
    # score/discovery has two identical zero differences; it is still not called equivalent
    assert recovery(report, "score", "discovery")["mean_difference"] == 0.0


def test_same_seed_reproduces_and_a_different_seed_is_recorded_differently(bundle: dict, report: dict) -> None:
    again = iv.score_bundle(copy.deepcopy(bundle))
    assert again == report
    bundle["seed"] = 8
    other = iv.score_bundle(bundle)
    assert (report["seed"], other["seed"]) == (7, 8)
    assert recovery(other, "activation")["seed_label"] == "8:activation:fact_recovery_rate_difference:all"
    assert other["bundle_sha256"] != report["bundle_sha256"]
    assert recovery(other, "activation")["interval"] == independent_interval(
        [0.0, 0.5, 0.0, 0.25, 0.5, -0.25], "8:activation:fact_recovery_rate_difference:all")
    # the point estimates do not depend on the seed
    assert recovery(other, "activation")["mean_difference"] == recovery(report, "activation")["mean_difference"]


def test_primary_results_use_the_declared_held_out_set(report: dict) -> None:
    primary = report["primary_results"]
    assert primary["analysis_set"] == "held_out"
    activation = primary["fact_recovery_rate_difference"]["activation"]
    assert (activation["n_families"], activation["n_included"], activation["mean_difference"]) == (4, 4, 0.125)
    # label, held out: families 3, 4, 5 are all 0 and family_6 is excluded
    label = primary["fact_recovery_rate_difference"]["label"]
    assert (label["n_included"], label["interval"], label["verdict"]) == (3, [0.0, 0.0], "equivalent_within_margin")
    assert primary["held_artifact_score_difference"]["label"] == {"status": "not_supplied"}
    assert primary["held_artifact_score_difference"]["score"]["verdict"] == "different_beyond_margin"


# ----------------------------------------------------------------------------------------- secondary endpoints

def test_changed_fact_sensitivity(report: dict) -> None:
    activation = report["stages"]["activation"]["changed_fact_sensitivity"]
    medical, everyday = activation["by_base_register"]["medical"], activation["by_base_register"]["everyday"]
    # six controls derived from the medical variant; families 3 and 6 still report the changed fact as recovered
    assert (medical["n_controls"], medical["n_assessed"], medical["detected"]["count"]) == (6, 6, 4)
    assert medical["detected"]["share"] == pytest.approx(4 / 6)
    assert medical["detected"]["wilson_interval"] == pytest.approx([0.3000, 0.9032], abs=5e-4)
    # three controls derived from the everyday variant (families 1 to 3); only family_1 is detected
    assert (everyday["n_controls"], everyday["detected"]["count"]) == (3, 1)
    assert everyday["detected"]["wilson_interval"] == pytest.approx([0.0615, 0.7923], abs=5e-4)
    missed = sorted(c["variant_id"] for c in activation["per_control"] if c["outcome"] == "not_detected")
    assert missed == ["f2_changed_everyday", "f3_changed_everyday", "f3_changed_medical", "f6_changed_medical"]
    readout = report["stages"]["readout"]["changed_fact_sensitivity"]["by_base_register"]
    # 6 of 6 and 3 of 3: the Wilson lower bound for k = n is n / (n + z^2)
    assert readout["medical"]["detected"]["wilson_interval"] == pytest.approx([6 / (6 + Z95 ** 2), 1.0])
    assert readout["everyday"]["detected"]["wilson_interval"] == pytest.approx([3 / (3 + Z95 ** 2), 1.0])


def test_changed_fact_control_with_an_unrecovered_base_is_counted_apart(bundle: dict) -> None:
    observation(bundle, "activation", "f1_medical")["fact_recovery"]["fact_a"] = "not_recovered"
    observation(bundle, "activation", "f2_changed_medical")["fact_recovery"]["fact_a"] = None
    medical = iv.score_bundle(bundle)["stages"]["activation"]["changed_fact_sensitivity"]["by_base_register"]["medical"]
    assert (medical["n_controls"], medical["n_base_not_recovered"], medical["n_undetermined"]) == (6, 1, 1)
    assert (medical["n_assessed"], medical["detected"]["count"]) == (4, 2)      # families 4 and 5 remain detected


def test_unsupported_fact_rates_by_register(report: dict) -> None:
    counts = report["stages"]["activation"]["unsupported_facts"]
    by_register = counts["by_register"]
    assert (by_register["medical"]["total"], by_register["medical"]["n_counted"]) == (2, 6)       # families 3, 6
    assert by_register["medical"]["mean_per_description"] == pytest.approx(2 / 6)
    assert by_register["everyday"]["mean_per_description"] == pytest.approx(3 / 6)                # 1 + 2
    assert by_register["within_register_paraphrase"]["mean_per_description"] == 0.0               # 8 paraphrases
    assert (by_register["changed_fact"]["n_counted"], by_register["changed_fact"]["total"]) == (9, 1)
    paired = counts["paired_medical_minus_everyday"]["all"]
    assert paired["mean_difference"] == pytest.approx((0 - 1 + 1 + 0 - 2 + 1) / 6)
    assert paired["verdict"] == "no_margin_declared"                 # the fixture fixes no margin for this endpoint


def test_paraphrase_consistency(report: dict) -> None:
    by_base = report["stages"]["activation"]["paraphrase_consistency"]["by_base_register"]
    # medical: five paraphrases agree on 4 of 4 facts, family_2's on 3 of 4 with a rate difference of -0.25
    assert by_base["medical"]["n_paraphrases"] == 6
    assert by_base["medical"]["mean_agreement_share"] == pytest.approx((5 + 0.75) / 6)
    assert by_base["medical"]["mean_absolute_rate_difference"] == pytest.approx(0.25 / 6)
    # everyday: family_1 agrees fully, family_4 on 3 of 4
    assert by_base["everyday"] == {"n_paraphrases": 2, "n_scored": 2, "n_undetermined": 0,
                                   "mean_agreement_share": 0.875, "mean_absolute_rate_difference": 0.125}
    assert report["stages"]["score"]["paraphrase_consistency"]["by_base_register"]["medical"][
        "mean_agreement_share"] == 1.0


def test_exact_token_ranks_are_lexical_and_a_window_miss_is_not_an_absence(report: dict) -> None:
    ranks = report["stages"]["readout"]["exact_token_ranks"]
    assert ranks["endpoint_kind"] == "lexical"
    medical, everyday = ranks["by_register"]["medical"], ranks["by_register"]["everyday"]
    # medical raw ranks 1, 2, 1, 3, 1, 4 -> median of (1, 1, 1, 2, 3, 4) = 1.5; filtered 1, 1, 1, 2, 1, 3 -> 1
    assert (medical["n_observed"], medical["median_raw_rank"], medical["median_filtered_rank"]) == (6, 1.5, 1.0)
    # everyday: family_5 was not observed in the window; the other five are 5, 2, 9, 3, 4 -> 4; filtered -> 3
    assert (everyday["n_observed"], everyday["n_not_observed_in_window"]) == (5, 1)
    assert (everyday["median_raw_rank"], everyday["median_filtered_rank"]) == (4, 3)
    paired = ranks["paired_raw_rank_medical_minus_everyday"]
    assert paired == {"n_families_both_observed": 5, "family_ids_without_both_ranks": ["family_5"], "median": 0}
    not_recorded = report["stages"]["activation"]["exact_token_ranks"]["by_register"]["medical"]
    assert (not_recorded["n_not_recorded"], not_recorded["median_raw_rank"]) == (6, None)


def test_rank_fields_must_agree_with_rank_status(bundle: dict) -> None:
    observation(bundle, "readout", "f5_everyday")["raw_rank"] = 40
    assert refusal_code(bundle) == "rank_status"


# ------------------------------------------------------------------------- behaviour by representation table

def test_four_cell_table_counts_and_wilson_intervals(report: dict) -> None:
    table = report["stages"]["activation"]["behaviour_by_representation"]
    assert (table["status"], table["n_determined"]) == ("determined", 6)
    cells = {name: cell["family_ids"] for name, cell in table["cells"].items()}
    assert cells == {"behaviour_changed__representation_changed": ["family_5"],
                     "behaviour_changed__representation_unchanged": ["family_3"],
                     "behaviour_unchanged__representation_changed": ["family_2", "family_4"],
                     "behaviour_unchanged__representation_unchanged": ["family_1", "family_6"]}
    one, two = (table["cells"]["behaviour_changed__representation_changed"],
                table["cells"]["behaviour_unchanged__representation_changed"])
    assert one["wilson_interval"] == pytest.approx([0.0301, 0.5635], abs=5e-4)      # 1 of 6
    assert two["wilson_interval"] == pytest.approx([0.0968, 0.7000], abs=5e-4)      # 2 of 6
    readout = report["stages"]["readout"]["behaviour_by_representation"]["cells"]
    assert readout["behaviour_changed__representation_changed"]["family_ids"] == ["family_3", "family_5"]
    assert readout["behaviour_unchanged__representation_unchanged"]["count"] == 4
    empty = readout["behaviour_changed__representation_unchanged"]
    assert (empty["count"], empty["share"]) == (0, 0.0)
    assert empty["wilson_interval"] == pytest.approx([0.0, Z95 ** 2 / (6 + Z95 ** 2)])     # 0 of 6


def test_table_is_undetermined_without_a_threshold_or_with_missing_inputs(bundle: dict, report: dict) -> None:
    for stage in ("label", "score"):
        assert report["stages"][stage]["behaviour_by_representation"] == {
            "status": "undetermined", "reason": "no_representation_threshold_declared_for_stage"}
    observation(bundle, "activation", "f2_everyday")["representation_value"] = None
    for stage in ("activation", "readout", "label", "score"):
        observation(bundle, stage, "f6_medical")["behaviour_value"] = None
    result = iv.score_bundle(bundle)
    table = result["stages"]["activation"]["behaviour_by_representation"]
    assert (table["status"], table["n_determined"]) == ("partly_undetermined", 4)
    assert table["undetermined"] == {"count": 2, "families": [
        {"family_id": "family_2", "missing": ["representation_value:everyday"]},
        {"family_id": "family_6", "missing": ["behaviour_value:medical"]}]}
    assert table["cells"]["behaviour_unchanged__representation_unchanged"]["family_ids"] == ["family_1"]
    comparable = result["analysis_sets"]["comparable_behaviour"]
    assert comparable["family_ids"] == ["family_1", "family_2", "family_4"]
    assert comparable["undetermined_family_ids"] == ["family_6"]
    assert result["model_behaviour"]["per_family"][5]["changed"] is None


def test_behaviour_is_model_evidence_and_must_agree_across_stages(bundle: dict, report: dict) -> None:
    behaviour = report["model_behaviour"]
    assert behaviour["evidence_about"] == "the model's output, not the instrument"
    assert [row["changed"] for row in behaviour["per_family"]] == [False, False, True, False, True, False]
    assert behaviour["per_family"][1]["difference"] == 0.0625
    assert report["stages"]["activation"]["evidence_about"] == "the instrument's output at this stage"
    observation(bundle, "readout", "f1_medical")["behaviour_value"] = 0.5
    assert refusal_code(bundle) == "behaviour_inconsistent"


def test_null_and_discordant_families_are_listed_by_id(report: dict) -> None:
    activation = recovery(report, "activation")
    assert activation["null_family_ids"] == ["family_1", "family_3"]
    assert activation["direction_discordant_family_ids"] == ["family_6"]       # -0.25 against a mean of +1/6
    assert recovery(report, "score")["direction_discordant_family_ids"] == []
    # family_1: zero difference in all four stages, unchanged behaviour, no representation change.
    # family_3 also has zero differences, but its behaviour changed, so it is not a null family.
    assert report["null_family_ids"] == ["family_1"]
    # family_6: -0.25 at the activation stage and +0.25 at the readout stage
    assert report["cross_stage_sign_discordant_family_ids"] == ["family_6"]


# ----------------------------------------------------------------------------------------------- held artifact

def test_instrument_effect_appears_only_in_the_held_artifact_manipulation(report: dict) -> None:
    for stage in ("activation", "readout", "label", "score"):
        assert recovery(report, stage)["verdict"] != "different_beyond_margin"
    held = report["held_artifact"]
    assert held["label"] == {"status": "not_supplied"}
    score = held["score"]
    assert (score["n_artifacts"], score["n_artifacts_included"], score["families_without_records"]) == (7, 7, [])
    by_artifact = {a["artifact_id"]: a["difference"] for a in score["per_artifact"]}
    assert (by_artifact["artifact_5a"], by_artifact["artifact_5b"]) == (0.375, 0.125)
    assert [row["difference"] for row in score["per_family"]] == [0.25] * 6        # family_5: (0.375 + 0.125) / 2
    everything = score["analysis_sets"]["all"]
    # six identical family values: every resampled mean is 0.25, above the 0.125 margin
    assert (everything["mean_difference"], everything["interval"]) == (0.25, [0.25, 0.25])
    assert everything["verdict"] == "different_beyond_margin"
    assert recovery(report, "score")["verdict"] == "equivalent_within_margin"


def test_held_artifact_exclusions_and_fixed_artifact_rule(bundle: dict) -> None:
    records = bundle["held_artifact"]
    removed = next(r for r in records if r["artifact_id"] == "artifact_1" and r["description_register"] == "everyday")
    records.remove(removed)
    next(r for r in records if r["artifact_id"] == "artifact_2" and r["description_register"] == "medical")[
        "score"] = None
    score = iv.score_bundle(bundle)["held_artifact"]["score"]
    reasons = {a["artifact_id"]: a["excluded_reason"] for a in score["per_artifact"] if a["excluded_reason"]}
    assert reasons == {"artifact_1": "unpaired_description:everyday", "artifact_2": "missing_score:medical"}
    summary = score["analysis_sets"]["all"]
    assert (summary["n_families"], summary["n_included"], summary["mean_difference"]) == (6, 4, 0.25)
    assert summary["excluded"] == [{"family_id": "family_1", "reason": "unpaired_description:everyday"},
                                   {"family_id": "family_2", "reason": "missing_score:medical"}]
    next(r for r in records if r["artifact_id"] == "artifact_3")["artifact_sha256"] = "another-digest"
    assert refusal_code(bundle) == "artifact_not_held_fixed"


# ----------------------------------------------------------------------------------------------------- refusals

def _drop(key: str):
    def mutate(bundle: dict) -> None:
        del bundle[key]
    return mutate


def _set(path: tuple, value: object):
    def mutate(bundle: dict) -> None:
        target = bundle
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
    return mutate


def _two_splits(bundle: dict) -> None:
    clone = copy.deepcopy(bundle["families"][0])
    clone["split"] = "fresh_test"
    bundle["families"].append(clone)


def _listed_twice(bundle: dict) -> None:
    bundle["families"].append(copy.deepcopy(bundle["families"][0]))


def _same_text_in_two_splits(bundle: dict) -> None:
    bundle["families"][4]["variants"][0]["text"] = bundle["families"][0]["variants"][0]["text"]


def _remove_register(register: str):
    def mutate(bundle: dict) -> None:
        family = bundle["families"][2]
        gone = {v["variant_id"] for v in family["variants"] if v["register"] == register}
        family["variants"] = [v for v in family["variants"] if v["variant_id"] not in gone]
        for stage in bundle["stages"].values():
            stage["observations"] = [row for row in stage["observations"] if row["variant_id"] not in gone]
    return mutate


def _unknown_stage(bundle: dict) -> None:
    bundle["stages"]["attribution"] = copy.deepcopy(bundle["stages"]["score"])


def _nan_value(bundle: dict) -> None:
    bundle["held_artifact"][0]["score"] = float("nan")


def _infinite_value(bundle: dict) -> None:
    bundle["stages"]["activation"]["observations"][0]["representation_value"] = float("inf")


def _drop_endpoint_margin(bundle: dict) -> None:
    del bundle["equivalence_margins"]["endpoints"]["held_artifact_score_difference"]


@pytest.mark.parametrize(("mutate", "code"), [
    (_drop("equivalence_margins"), "missing_margins"),
    (_drop_endpoint_margin, "missing_margins"),
    (_set(("equivalence_margins", "prespecified"), False), "margins_not_prespecified"),
    (_set(("equivalence_margins", "endpoints", "fact_recovery_rate_difference"), 0), "invalid_margin"),
    (_two_splits, "split_leakage"),
    (_listed_twice, "duplicate_family"),
    (_same_text_in_two_splits, "split_leakage"),
    (_set(("thresholds", "behaviour_change", "selected_on_split"), "validation"), "threshold_split"),
    (_set(("thresholds", "representation_change", "readout", "selected_on_split"), "fresh_test"),
     "threshold_split"),
    (_set(("development", "label_development_split"), "validation"), "development_split"),
    (_set(("development", "scorer_calibration_split"), "fresh_test"), "development_split"),
    (_remove_register("everyday"), "missing_register"),
    (_remove_register("medical"), "missing_register"),
    (_remove_register("changed_fact"), "missing_changed_fact_control"),
    (_nan_value, "non_finite_value"),
    (_infinite_value, "non_finite_value"),
    (_unknown_stage, "unknown_stage"),
    (_set(("stages",), {}), "no_stages"),
    (_set(("execution_status",), "measurement"), "synthetic_claims_measurement"),
    (_set(("synthetic",), False), "real_bundle_not_admitted"),
    (_drop("seed"), "missing_seed"),
    (_set(("seed",), True), "missing_seed"),
    (_set(("seed",), 7.0), "missing_seed"),
    (_set(("schema_version",), "patientwords.exploratory/1"), "schema_version"),
    (_set(("analysis_plan", "primary_analysis_set"), "all"), "primary_analysis_set"),
    (_set(("analysis_plan", "primary_analysis_set"), "discovery"), "primary_analysis_set"),
    (_set(("analysis_plan", "minimum_families_for_verdict"), 1), "analysis_plan"),
    (_set(("analysis_plan", "confidence_level"), 1), "analysis_plan"),
    (_set(("analysis_plan", "prespecified_subsets"), ["families_with_a_clear_effect"]), "analysis_plan"),
    (_set(("identities", "model_revision"), " "), "missing_identity"),
    (_set(("families", 0, "split"), "holdout"), "split"),
    (_set(("families", 0, "variants", 4, "changed_fact_id"), "fact_z"), "changed_fact"),
    (_set(("stages", "label", "observations", 0, "fact_recovery", "fact_a"), "mostly"), "fact_status"),
    (_set(("stages", "label", "observations", 0, "fact_recovery", "fact_z"), "recovered"), "unknown_fact"),
    (_set(("stages", "label", "observations", 0, "variant_id"), "f9_medical"), "unknown_variant"),
    (_set(("stages", "label", "observations", 1, "variant_id"), "f1_medical"), "duplicate_observation"),
    (_set(("stages", "label", "observations", 0, "unsupported_facts"), -1), "invalid_count"),
    (_set(("stages", "label", "observations", 0, "unsupported_facts"), "none"), "schema"),
    (_set(("held_artifact", 0, "stage"), "activation"), "held_artifact_stage"),
    (_set(("held_artifact", 1, "description_register"), "medical"), "duplicate_description"),
])
def test_named_refusals(bundle: dict, mutate, code: str) -> None:
    mutate(bundle)
    assert refusal_code(bundle) == code
    with pytest.raises(iv.Refusal) as caught:
        iv.validate_bundle(bundle)
    assert caught.value.code == code


def test_a_non_object_bundle_refuses_by_name() -> None:
    assert refusal_code([]) == "invalid_input"


# ---------------------------------------------------------------------------------------------------------- CLI

def test_cli_prints_the_report_and_refuses_with_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert iv.main(["--bundle", str(FIXTURE)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert (printed["status"], printed["execution_status"], printed["seed"]) == ("scored", "synthetic", 7)
    bad = tmp_path / "bundle.json"
    bad.write_text(FIXTURE.read_text(encoding="utf-8").replace('"score": 0.75', '"score": NaN', 1), encoding="utf-8")
    assert iv.main(["--bundle", str(bad)]) == 2
    refused = json.loads(capsys.readouterr().out)
    assert (refused["status"], refused["code"]) == ("refused", "non_finite_value")
    assert iv.main(["--bundle", str(tmp_path / "absent.json")]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "invalid_input"


def test_cli_out_is_exclusive_namespaced_and_outside_every_checkout(tmp_path: Path,
                                                                    capsys: pytest.CaptureFixture) -> None:
    out = tmp_path / "instrument_validity" / "instrument_validity_report.synthetic.json"
    assert iv.main(["--bundle", str(FIXTURE), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["evidence_label"].startswith("synthetic software fixture")
    capsys.readouterr()
    refused = [out,                                                             # exists: never overwritten
               tmp_path / "instrument_validity" / "batch_summary.json",         # a collector's file name
               tmp_path / "elsewhere" / "instrument_validity_report.a.json",    # wrong directory name
               tmp_path / "data" / "instrument_validity" / "instrument_validity_report.a.json",
               ROOT / "tests" / "fixtures" / "instrument_validity" / "instrument_validity_report.a.json"]
    for path in refused:
        assert iv.main(["--bundle", str(FIXTURE), "--out", str(path)]) == 2
        body = json.loads(capsys.readouterr().out)
        assert body["status"] == "refused"
        assert body["code"] == ("invalid_input" if path == out else "output_namespace")
    assert not (ROOT / "tests" / "fixtures" / "instrument_validity" / "instrument_validity_report.a.json").exists()
    assert sorted(p.name for p in (tmp_path / "instrument_validity").iterdir()) == [out.name]
