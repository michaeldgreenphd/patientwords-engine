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

Description controls of the same fixture (score stage). Each of the seven artifacts has eight evaluation items,
four positive (p1 to p4) and four negative (n1 to n4). A score is balanced accuracy, (share of positives given yes +
share of negatives given no) / 2, so it is a multiple of 1/8. The items given a yes verdict are:
    medical            p1 p2 p3 p4 -> (1 + 1) / 2 = 1        artifact_5b: p1 p2 p3 -> (3/4 + 1) / 2 = 0.875
    everyday           p1 p2 p3 n4 -> (3/4 + 3/4) / 2 = 0.75  artifact_5a: p1 p2 p3 n3 n4 -> (3/4 + 2/4) / 2 = 0.625
    shuffled_medical   p1 p2 n1 n2 -> 0.5     shuffled_everyday  p3 p4 n3 n4 -> 0.5     irrelevant  none -> 0.5
  So matched minus control is 0.5 (medical) and 0.25 (everyday) per artifact, except artifact_5a everyday 0.125 and
  artifact_5b medical 0.375; family_5 averages its two artifacts to 0.4375 (medical) and 0.1875 (everyday).
  Every item cue is balanced between the classes (two positives and two negatives per span_position and per
  span_marking value and per window_token_count value; the presentation order of the second discovery artifact
  is the label-mirror of the first), so every rule of the closed family scores 0.5 on the discovery items and the
  frozen baseline is the first rule of the list, always_positive.
  Description token counts are 8 and 8, except artifact_5a: medical 6, everyday 12. Formatting classes are
  plain_sentence, except the everyday description of artifact_6. No presentation_order is recorded for descriptions.
  Control margins are 0.125 each; shuffle seed 11; 2,000 permutations at alpha 0.05.

tests/fixtures/instrument_validity/synthetic_control_states.v1.json holds one cell per control state. Six families,
two per split (family_1, family_2 discovery; 3, 4 validation; 5, 6 fresh_test), one artifact per family and stage,
four items per artifact (p1, p2 positive; n1, n2 negative), so a score is a multiple of 1/4. The plan's minimum is
two families. The stages carry no observations. Yes verdicts: "reads" = p1 p2 (1.0); "one each" = p1 n1 (0.5);
"three" = p1 p2 n1 -> (1 + 1/2) / 2 = 0.75; "none" (0.5).
  score stage  span_position is centre for positives and edge for negatives on artifacts 1, 2, 5, 6, and centre for
               p1 n1, edge for p2 n2 on artifacts 3, 4. span_marking is not recorded. Windows are 16 tokens.
               artifacts 1, 2, 5, 6: matched "reads", shuffled "one each", irrelevant "none".
               artifacts 3, 4: all five conditions "three" (a scorer that ignores the description).
  label stage  window_token_count is 24 for p1 and 12 for p2, n1, n2; span_position and span_marking are balanced.
               artifact 1: medical "reads", everyday "one each"; tokens 8 and 16; everyday formatting differs.
               artifact 2: medical "reads", everyday "three"; tokens 8 and 12.
               artifacts 3 to 6: matched "reads"; tokens 8 and 8. Shuffled "one each" and irrelevant "none"
               everywhere, except that artifacts 3 and 4 have no shuffled verdicts at all.
               The medical description is scored first on artifacts 1, 3, 5 and second on 2, 4, 6.
"""
from __future__ import annotations

import copy
import json
import math
import random
import statistics
from pathlib import Path

import pytest

from scripts import instrument_validity as iv

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "instrument_validity" / "synthetic_bundle.v1.json"
STATES_FIXTURE = ROOT / "tests" / "fixtures" / "instrument_validity" / "synthetic_control_states.v1.json"
SPECIFICATION = ROOT / "docs" / "protocols" / "instrument_validity_benchmark.md"
RUBRIC = ROOT / "data" / "protocols" / "instrument_validity_rubric.draft.json"
FAMILIES = [f"family_{n}" for n in range(1, 7)]
Z95 = 1.959963984540054


@pytest.fixture
def bundle() -> dict:
    return iv.load_bundle(FIXTURE)


@pytest.fixture(scope="module")
def report() -> dict:
    return iv.score_bundle(iv.load_bundle(FIXTURE))


@pytest.fixture
def states_bundle() -> dict:
    return iv.load_bundle(STATES_FIXTURE)


@pytest.fixture(scope="module")
def states() -> dict:
    return iv.score_bundle(iv.load_bundle(STATES_FIXTURE))


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


# ------------------------------------------------------------------------- description controls and cue checks

THREE_OUTCOMES = ("equivalent_within_margin", "different_beyond_margin", "inconclusive")
USUAL_SCORES = {"medical": 1.0, "everyday": 0.75, "shuffled_medical": 0.5, "shuffled_everyday": 0.5, "irrelevant": 0.5}


def held(report: dict, stage: str = "score", name: str = "all") -> dict:
    return report["held_artifact"][stage]["analysis_sets"][name]


def controls(report: dict, stage: str = "score") -> dict:
    return report["held_artifact"][stage]["description_controls"]


def control_of(report: dict, stage: str = "score", name: str = "all") -> dict:
    return controls(report, stage)["analysis_sets"][name]


def scored_items(report: dict, stage: str = "score") -> dict:
    return {row["artifact_id"]: row for row in controls(report, stage)["per_artifact"]}


def independent_derangement(family_of: dict[str, str], seed_label: str) -> tuple[dict[str, str], int]:
    """The documented shuffle, written again here: sorted ids, redrawn until no artifact meets its own family."""
    ids = sorted(family_of)
    rng = random.Random(seed_label)
    attempts = 0
    while True:
        attempts += 1
        drawn = ids[:]
        rng.shuffle(drawn)
        if not any(family_of[own] == family_of[source] for own, source in zip(ids, drawn)):
            return dict(zip(ids, drawn)), attempts


def independent_association(xs: list[float], ys: list[float], permutations: int,
                            seed_label: str) -> tuple[float, float]:
    """The documented permutation test, written again here with the standard library's correlation."""
    observed = statistics.correlation(xs, ys)
    rng = random.Random(seed_label)
    drawn = list(xs)
    count = 0
    for _ in range(permutations):
        rng.shuffle(drawn)
        if abs(statistics.correlation(drawn, ys)) >= abs(observed) - 1e-12:
            count += 1
    return observed, (1 + count) / (1 + permutations)


def outcome_from(interval: list[float], margin: float) -> str:
    if interval[0] > margin:
        return "control_beaten"
    return "control_not_beaten" if interval[1] <= margin else "advantage_not_shown"


def test_rubric_control_names_match_the_scorer() -> None:
    rubric = json.loads(RUBRIC.read_text(encoding="utf-8"))["description_controls"]
    assert rubric["status"].startswith("draft - not validated")
    assert rubric["score_metric"] == iv.SCORE_METRIC == "balanced_accuracy"
    assert [c["condition"] for c in rubric["conditions"]] == ["matched", "shuffled", "irrelevant"]
    family = tuple(rule["rule"] for rule in rubric["explanation_free_baseline"]["rule_family"])
    assert family == iv.EXPLANATION_FREE_RULES == ("always_positive", "always_negative", "majority_class",
                                                   "span_position", "span_marking", "window_length",
                                                   "presentation_order")
    margins = rubric["margins"]
    assert set(margins) - {"note"} == set(iv.CONTROL_MARGINS.values()) == {
        "matched_minus_shuffled", "matched_minus_irrelevant", "matched_minus_explanation_free"}
    for name in iv.CONTROL_MARGINS.values():      # placeholders: the rubric names each margin and fixes no value
        assert (margins[name]["value"], margins[name]["status"]) == (None, "placeholder - not fixed")
    assert tuple(state["value"] for state in rubric["control_states"]) == iv.CONTROL_STATES
    assert tuple(state["value"] for state in rubric["comparison_outcomes"]) == iv.CONTROL_OUTCOMES
    assert tuple(state["value"] for state in rubric["cue_states"]) == iv.CUE_STATES
    assert tuple(state["value"] for state in rubric["association_states"]) == iv.ASSOCIATION_STATES
    fields = {**{cue: f"evaluation_items[].{field}" for cue, (field, _) in iv.CUE_RULES.items()},
              **{cue: f"held_artifact[].{field}" for cue, field in iv.DESCRIPTION_CUES.items()}}
    assert {check["cue"]: check["bundle_field"] for check in rubric["cue_checks"]} == fields
    not_exposed = next(state for state in rubric["cue_states"] if state["value"] == "not_exposed")
    assert "This is not a pass." in not_exposed["definition"]
    placeholder = rubric["irrelevant_description"]
    assert _text_of(FIXTURE)["description_controls"]["irrelevant_description"] == {
        "placeholder_id": placeholder["placeholder_id"], "text": placeholder["text"]}


def _text_of(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_description_condition_is_scored_on_the_artifacts_own_items(report: dict) -> None:
    assert iv.balanced_accuracy([True, True, False, False], [True, False, False, False]) == 0.75     # (1/2 + 1) / 2
    assert iv.balanced_accuracy([True, True, False, False], [True, True, True, True]) == 0.5         # (1 + 0) / 2
    assert iv.balanced_accuracy([True, True], [True, True]) is None          # no negative item: undefined, not 1
    assert iv.balanced_accuracy([], []) is None
    per = scored_items(report)
    assert len(per) == 7
    assert all((row["n_items"], row["n_positive_items"], row["missing"]) == (8, 4, {}) for row in per.values())
    for artifact_id in ("artifact_1", "artifact_2", "artifact_3", "artifact_4", "artifact_6"):
        assert per[artifact_id]["scores"] == USUAL_SCORES
    assert per["artifact_5a"]["scores"] == {**USUAL_SCORES, "everyday": 0.625}
    assert per["artifact_5b"]["scores"] == {**USUAL_SCORES, "medical": 0.875}
    # the matched scores are the ones the held-artifact records declare
    declared = {row["artifact_id"]: (row["medical_description_score"], row["everyday_description_score"])
                for row in report["held_artifact"]["score"]["per_artifact"]}
    assert declared == {artifact_id: (row["scores"]["medical"], row["scores"]["everyday"])
                        for artifact_id, row in per.items()}
    assert controls(report)["score_metric"] == "balanced_accuracy"


def test_shuffled_descriptions_come_from_a_seeded_derangement_across_families(bundle: dict, report: dict) -> None:
    family_of = {record["artifact_id"]: record["family_id"] for record in bundle["held_artifact"]}
    mapping, attempts = independent_derangement(family_of, "11:shuffle:score")
    assert bundle["description_controls"]["shuffle"]["mapping"]["score"] == mapping
    assert sorted(mapping) == sorted(mapping.values()) == sorted(family_of)        # a permutation of seven artifacts
    assert all(family_of[own] != family_of[source] for own, source in mapping.items())
    assert mapping["artifact_5a"] != "artifact_5b" and mapping["artifact_5b"] != "artifact_5a"     # one family
    shuffle = controls(report)["shuffle"]
    assert (shuffle["status"], shuffle["seed"], shuffle["seed_label"], shuffle["attempts"], shuffle["mapping"]) == (
        "reproduced", 11, "11:shuffle:score", attempts, mapping)
    assert iv.seeded_derangement(family_of, "11:shuffle:score") == (mapping, attempts)
    assert iv.seeded_derangement({"a": "one_family", "b": "one_family"}, "0:shuffle:score") is None
    swapped = copy.deepcopy(bundle)
    recorded = swapped["description_controls"]["shuffle"]["mapping"]["score"]
    recorded["artifact_1"], recorded["artifact_2"] = recorded["artifact_2"], recorded["artifact_1"]
    assert refusal_code(swapped) == "shuffle_mapping_not_reproducible"
    own = copy.deepcopy(bundle)
    own["description_controls"]["shuffle"]["mapping"]["score"]["artifact_1"] = "artifact_1"
    assert refusal_code(own) == "shuffle_mapping_not_reproducible"
    assert independent_derangement(family_of, "12:shuffle:score")[0] != mapping
    bundle["description_controls"]["shuffle"]["seed"] = 12            # the recorded mapping belongs to seed 11
    assert refusal_code(bundle) == "shuffle_mapping_not_reproducible"


def test_controls_pass_on_the_base_fixture_and_the_verdict_is_issued(report: dict) -> None:
    baseline = controls(report)["explanation_free"]
    assert baseline["candidate_rules"] == list(iv.EXPLANATION_FREE_RULES)
    assert baseline["discovery_scores"] == dict.fromkeys(iv.EXPLANATION_FREE_RULES, 0.5)
    assert (baseline["selected_rule"], baseline["selected_on_split"]) == ("always_positive", "discovery")
    for name in ("all", "held_out", "comparable_behaviour"):
        state = control_of(report, "score", name)
        assert (state["state"], state["failed_comparisons"], state["controls_not_run"]) == ("controls_passed", [], [])
        summary = held(report, "score", name)
        assert (summary["control_state"], summary["verdict_issued"], summary["verdict"]) == (
            "controls_passed", True, "different_beyond_margin")
    # held out = families 3, 4, 5, 6. Matched minus any control: medical 0.5, 0.5, (0.5 + 0.375) / 2, 0.5;
    # everyday 0.25, 0.25, (0.125 + 0.25) / 2, 0.25. Shuffled, irrelevant and the baseline all score 0.5.
    for control in iv.CONTROLS:
        medical, everyday = (control_of(report, "score", "held_out")["comparisons"][control][register]
                             for register in ("medical", "everyday"))
        assert medical["mean_difference"] == (0.5 + 0.5 + 0.4375 + 0.5) / 4
        assert everyday["mean_difference"] == (0.25 + 0.25 + 0.1875 + 0.25) / 4
        # no family value is below 0.4375 (0.1875), so no resampled mean is, whatever the seed: above the 0.125 margin
        assert 0.4375 <= medical["interval"][0] <= medical["interval"][1] <= 0.5
        assert 0.125 < 0.1875 <= everyday["interval"][0] <= everyday["interval"][1] <= 0.25
        assert (medical["outcome"], everyday["outcome"], medical["control_margin"]) == (
            "control_beaten", "control_beaten", 0.125)
        label = f"7:held_artifact_score:matched_minus_{control}:everyday:held_out"
        assert (everyday["seed_label"], everyday["interval"]) == (
            label, independent_interval([0.25, 0.25, 0.1875, 0.25], label))
    scores = control_of(report, "score", "held_out")["mean_scores"]
    assert scores["matched"] == {"medical": (1 + 1 + 0.9375 + 1) / 4, "everyday": (0.75 + 0.75 + 0.6875 + 0.75) / 4}
    assert (scores["shuffled"], scores["irrelevant"]) == ({"medical": 0.5, "everyday": 0.5}, 0.5)
    assert scores["explanation_free_baseline"] == {"rule": "always_positive", "score": 0.5}
    assert scores["explanation_free_rules"] == dict.fromkeys(iv.EXPLANATION_FREE_RULES, 0.5)


def test_a_set_below_the_minimum_family_count_gets_a_control_state_and_no_verdict(report: dict) -> None:
    for name in ("discovery", "validation", "fresh_test"):         # two families each; the plan's minimum is 3
        state = control_of(report, "score", name)
        assert state["state"] == "description_reading_not_shown"
        assert all(body["interval"] is None and body["outcome"] == "advantage_not_shown"
                   for registers in state["comparisons"].values() for body in registers.values())
        summary = held(report, "score", name)
        assert (summary["verdict"], summary["verdict_issued"]) == ("description_reading_not_shown", False)


def test_control_state_fixture_is_synthetic_and_scores(states_bundle: dict, states: dict,
                                                      capsys: pytest.CaptureFixture) -> None:
    assert (states_bundle["synthetic"], states_bundle["execution_status"]) == (True, "synthetic")
    record = iv.validate_bundle(states_bundle)
    assert record["families_by_split"] == {"discovery": FAMILIES[:2], "validation": FAMILIES[2:4],
                                           "fresh_test": FAMILIES[4:]}
    assert states["evidence_label"] == "synthetic software fixture - not a research result"
    assert '"measurement"' not in json.dumps(states)
    assert iv.main(["--bundle", str(STATES_FIXTURE)]) == 0
    assert json.loads(capsys.readouterr().out)["execution_status"] == "synthetic"
    # the stages carry no observations: nothing is scored for fact recovery, and nothing is read as a zero difference
    for stage in ("label", "score"):
        assert (recovery(states, stage)["n_included"], recovery(states, stage)["verdict"]) == (0, "inconclusive")
    usual = {**USUAL_SCORES, "everyday": 1.0}
    assert scored_items(states, "score")["score_artifact_1"]["scores"] == usual
    assert scored_items(states, "label")["label_artifact_5"]["scores"] == usual
    assert scored_items(states, "label")["label_artifact_1"]["scores"] == {**usual, "everyday": 0.5}
    assert scored_items(states, "label")["label_artifact_2"]["scores"] == {**usual, "everyday": 0.75}


def test_a_scorer_that_ignores_the_description_gets_no_equivalence_verdict(states: dict) -> None:
    for artifact_id in ("score_artifact_3", "score_artifact_4"):
        # p1, p2 and n1 get yes under every condition: (2/2 + 1/2) / 2 = 0.75
        assert scored_items(states)[artifact_id]["scores"] == dict.fromkeys(iv.VERDICT_CONDITIONS, 0.75)
    summary = held(states, "score", "validation")
    # both family differences are 0, so the interval is [0, 0], inside the 0.125 margin. The verdict rule alone
    # calls that equivalent; the scorer at the commit before this change returned exactly that.
    assert (summary["mean_difference"], summary["interval"], summary["margin"]) == (0.0, [0.0, 0.0], 0.125)
    assert iv.equivalence_verdict(summary["interval"], summary["margin"]) == "equivalent_within_margin"
    assert (summary["verdict"], summary["control_state"], summary["verdict_issued"]) == (
        "scorer_does_not_read_description", "scorer_does_not_read_description", False)
    state = control_of(states, "score", "validation")
    for control in ("shuffled", "irrelevant"):
        for register in ("medical", "everyday"):
            body = state["comparisons"][control][register]
            assert (body["mean_difference"], body["interval"], body["outcome"]) == (0.0, [0.0, 0.0],
                                                                                    "control_not_beaten")
    # the frozen baseline (span_position) says yes to p1 and n1 on these two artifacts: 0.5, and 0.75 - 0.5 = 0.25
    for register in ("medical", "everyday"):
        body = state["comparisons"]["explanation_free"][register]
        assert (body["mean_difference"], body["interval"], body["outcome"]) == (0.25, [0.25, 0.25], "control_beaten")
    assert state["failed_comparisons"] == ["matched_minus_shuffled:medical", "matched_minus_shuffled:everyday",
                                           "matched_minus_irrelevant:medical", "matched_minus_irrelevant:everyday"]
    assert states["stages"]["score"]["description_controls"]["state_by_analysis_set"]["validation"] == (
        "scorer_does_not_read_description")


def test_a_cue_only_rule_that_matches_the_real_score_blocks_the_verdict(states: dict) -> None:
    baseline = controls(states)["explanation_free"]
    candidates = [rule for rule in iv.EXPLANATION_FREE_RULES if rule != "span_marking"]
    assert baseline["candidate_rules"] == candidates
    # on the four discovery positives span_position is "centre", on the four negatives "edge"
    assert baseline["parameters"]["span_position"] == {"field": "span_position", "positive_values": ["centre"]}
    assert baseline["discovery_scores"] == {**dict.fromkeys(candidates, 0.5), "span_position": 1.0}
    assert baseline["selected_rule"] == "span_position"
    for artifact_id in ("score_artifact_5", "score_artifact_6"):
        row = scored_items(states)[artifact_id]
        assert (row["scores"]["medical"], row["scores"]["everyday"], row["rule_scores"]["span_position"]) == (1, 1, 1)
    state = control_of(states, "score", "fresh_test")
    for register in ("medical", "everyday"):
        for control in ("shuffled", "irrelevant"):                   # 1.0 - 0.5
            body = state["comparisons"][control][register]
            assert (body["mean_difference"], body["interval"], body["outcome"]) == (0.5, [0.5, 0.5], "control_beaten")
        body = state["comparisons"]["explanation_free"][register]     # 1.0 - 1.0
        assert (body["mean_difference"], body["interval"], body["outcome"]) == (0.0, [0.0, 0.0], "control_not_beaten")
    assert state["state"] == "baseline_not_beaten"
    assert state["mean_scores"]["matched"] == {"medical": 1.0, "everyday": 1.0}       # reported beside the baseline
    assert state["mean_scores"]["explanation_free_baseline"] == {"rule": "span_position", "score": 1.0}
    summary = held(states, "score", "fresh_test")
    assert iv.equivalence_verdict(summary["interval"], summary["margin"]) == "equivalent_within_margin"
    assert (summary["verdict"], summary["verdict_issued"]) == ("baseline_not_beaten", False)
    assert states["primary_results"]["held_artifact_score_difference"]["score"] == {
        "n_families": 2, "n_included": 2, "mean_difference": 0.0, "interval": [0.0, 0.0], "margin": 0.125,
        "verdict": "baseline_not_beaten", "control_state": "baseline_not_beaten"}


def test_the_baseline_is_fitted_and_selected_on_discovery_items_only(states_bundle: dict, states: dict) -> None:
    rows = [{"label": True, "window_token_count": 24}, {"label": True, "window_token_count": 12},
            {"label": False, "window_token_count": 12}, {"label": False, "window_token_count": 12}]
    # at least 12: yes to all, 0.5; at least 24: yes to the first positive only, (1/2 + 2/2) / 2 = 0.75;
    # at most 12: (1/2 + 0) / 2 = 0.25; at most 24: 0.5
    at_least_24 = {"field": "window_token_count", "direction": "at_least", "threshold": 24}
    assert iv.fit_explanation_free_rule("window_length", rows) == at_least_24
    assert [iv.apply_explanation_free_rule("window_length", at_least_24, row) for row in rows] == [True, False,
                                                                                                  False, False]
    flat = [{"label": True, "window_token_count": 16}, {"label": False, "window_token_count": 16}]
    assert iv.fit_explanation_free_rule("window_length", flat) == {**at_least_24, "threshold": 16}   # yes to all
    assert iv.fit_explanation_free_rule("majority_class", rows) == {"predicts": True}        # 2 of 4: a tie is yes
    assert iv.fit_explanation_free_rule("majority_class", rows[1:]) == {"predicts": False}   # 1 positive of 3
    assert iv.apply_explanation_free_rule("always_negative", {}, rows[0]) is False
    label = controls(states, "label")["explanation_free"]
    assert label["parameters"]["window_length"] == at_least_24
    assert label["discovery_scores"] == {**dict.fromkeys(iv.EXPLANATION_FREE_RULES, 0.5), "window_length": 0.75}
    assert (label["selected_rule"], label["fitted_on"]) == ("window_length", "pooled discovery items of this stage")
    # the cue of the fresh-test items changes: no fitted parameter and no selection moves
    moved = copy.deepcopy(states_bundle)
    for row in moved["evaluation_items"]:
        if row["artifact_id"] in ("score_artifact_5", "score_artifact_6"):
            row["span_position"] = "centre" if row["item_id"] in ("p1", "n1") else "edge"
    after = iv.score_bundle(moved)
    assert controls(after)["explanation_free"] == controls(states)["explanation_free"]
    # the frozen rule now says yes to p1 and n1 there: 0.5. The matched 1.0 beats it by 0.5 and the verdict is issued
    assert control_of(after, "score", "fresh_test")["comparisons"]["explanation_free"]["medical"]["mean_difference"] == 0.5
    assert (control_of(after, "score", "fresh_test")["state"], held(after, "score", "fresh_test")["verdict"]) == (
        "controls_passed", "equivalent_within_margin")
    # without discovery items no rule can be fitted: the baseline is missing, it is not 0.5 and not a pass
    bare = copy.deepcopy(states_bundle)
    bare["evaluation_items"] = [row for row in bare["evaluation_items"]
                                if row["artifact_id"] not in ("score_artifact_1", "score_artifact_2")]
    without = iv.score_bundle(bare)
    assert controls(without)["explanation_free"]["selected_rule"] is None
    assert controls(without)["explanation_free"]["selection_status"] == "no_discovery_items_with_both_classes"
    assert (control_of(without, "score", "fresh_test")["state"], control_of(without, "score", "fresh_test")["controls_not_run"]) == (
        "control_not_run", ["explanation_free"])
    states_bundle["description_controls"]["explanation_free_rules"].remove("span_position")
    assert refusal_code(states_bundle) == "explanation_free_rule_family"


def test_an_absent_control_is_recorded_as_missing_and_blocks_the_verdict(bundle: dict, states_bundle: dict,
                                                                       states: dict) -> None:
    row = scored_items(states, "label")["label_artifact_3"]
    assert (row["scores"]["shuffled_medical"], row["scores"]["shuffled_everyday"]) == (None, None)     # not 0
    assert row["missing"] == {"shuffled_medical": "missing_item_verdict", "shuffled_everyday": "missing_item_verdict"}
    state = control_of(states, "label", "validation")
    assert (state["state"], state["controls_not_run"], state["controls_incomplete"]) == ("control_not_run",
                                                                                         ["shuffled"], [])
    for register in ("medical", "everyday"):
        body = state["comparisons"]["shuffled"][register]
        assert (body["n_families"], body["n_included"], body["mean_difference"], body["interval"]) == (2, 0, None,
                                                                                                       None)
        assert body["excluded"] == [{"family_id": "family_3", "reason": "missing_control_score:shuffled"},
                                    {"family_id": "family_4", "reason": "missing_control_score:shuffled"}]
        # the two controls that were run are beaten (1.0 - 0.5 and 1.0 - 0.75); one absent control still blocks
        assert state["comparisons"]["irrelevant"][register]["mean_difference"] == 0.5
        assert state["comparisons"]["explanation_free"][register]["mean_difference"] == 0.25
        assert state["comparisons"]["explanation_free"][register]["outcome"] == "control_beaten"
    summary = held(states, "label", "validation")
    assert iv.equivalence_verdict(summary["interval"], summary["margin"]) == "equivalent_within_margin"
    assert (summary["verdict"], summary["verdict_issued"]) == ("control_not_run", False)
    # held out = families 3 to 6; the shuffled control exists for 5 and 6 only
    assert (control_of(states, "label", "held_out")["state"], control_of(states, "label", "held_out")["controls_incomplete"]) == (
        "control_incomplete", ["shuffled"])
    assert held(states, "label", "held_out")["verdict"] == "control_incomplete"

    # one null verdict is a missing score. Read as "no" it would have left the irrelevant score at 0.5 and the set
    # in the state controls_passed.
    one = copy.deepcopy(states_bundle)
    next(item for item in one["evaluation_items"] if (item["artifact_id"], item["item_id"]) == (
        "label_artifact_5", "p1"))["verdicts"]["irrelevant"] = None
    result = iv.score_bundle(one)
    assert scored_items(result, "label")["label_artifact_5"]["scores"]["irrelevant"] is None
    assert (control_of(result, "label", "fresh_test")["state"], control_of(result, "label", "fresh_test")["controls_incomplete"]) == (
        "control_incomplete", ["irrelevant"])
    assert control_of(states, "label", "fresh_test")["state"] == "controls_passed"

    no_mapping = copy.deepcopy(bundle)
    del no_mapping["description_controls"]["shuffle"]["mapping"]["score"]
    result = iv.score_bundle(no_mapping)
    assert scored_items(result)["artifact_1"]["missing"] == {"shuffled_medical": "no_shuffle_mapping",
                                                            "shuffled_everyday": "no_shuffle_mapping"}
    assert (control_of(result)["state"], control_of(result)["controls_not_run"]) == ("control_not_run", ["shuffled"])
    assert controls(result)["shuffle"] == {"status": "control_not_run", "reason": "no_shuffle_mapping", "seed": 11}

    no_items = copy.deepcopy(bundle)
    del no_items["evaluation_items"]
    result = iv.score_bundle(no_items)
    assert control_of(result) == {"state": "control_not_run", "reason": "no_evaluation_items"}
    summary = held(result)
    # the difference and its interval are still reported; only the verdict is withheld
    assert (summary["mean_difference"], summary["interval"], summary["verdict"]) == (0.25, [0.25, 0.25],
                                                                                   "control_not_run")


def test_controls_passed_with_a_fitted_baseline_issues_the_equivalence_verdict(states: dict) -> None:
    state = control_of(states, "label", "fresh_test")
    for register in ("medical", "everyday"):
        # matched 1.0; shuffled 0.5; irrelevant 0.5; the frozen window_length rule says yes to p1 only: 0.75
        for control, difference in (("shuffled", 0.5), ("irrelevant", 0.5), ("explanation_free", 0.25)):
            body = state["comparisons"][control][register]
            assert (body["mean_difference"], body["interval"], body["outcome"]) == (
                difference, [difference, difference], "control_beaten")
    assert (state["state"], state["failed_comparisons"], state["item_cues_not_exposed"]) == ("controls_passed", [], [])
    assert state["mean_scores"]["explanation_free_baseline"] == {"rule": "window_length", "score": 0.75}
    assert states["primary_results"]["analysis_set"] == "fresh_test"
    assert states["primary_results"]["held_artifact_score_difference"]["label"] == {
        "n_families": 2, "n_included": 2, "mean_difference": 0.0, "interval": [0.0, 0.0], "margin": 0.125,
        "verdict": "equivalent_within_margin", "control_state": "controls_passed"}
    assert held(states, "label", "fresh_test")["verdict_issued"] is True


def test_an_advantage_that_the_interval_does_not_settle_is_not_shown(states: dict) -> None:
    # held out: families 3, 4 ignore the description (0 over shuffled and irrelevant, 0.25 over the baseline);
    # families 5, 6 read it and match the baseline (0.5, 0.5, 0)
    expected = {"shuffled": [0.0, 0.0, 0.5, 0.5], "irrelevant": [0.0, 0.0, 0.5, 0.5],
                "explanation_free": [0.25, 0.25, 0.0, 0.0]}
    state = control_of(states, "score", "held_out")
    for control, values in expected.items():
        for register in ("medical", "everyday"):
            body = state["comparisons"][control][register]
            label = f"7:held_artifact_score:matched_minus_{control}:{register}:held_out"
            interval = independent_interval(values, label)
            assert (body["mean_difference"], body["interval"], body["seed_label"]) == (sum(values) / 4, interval, label)
            assert interval[0] <= 0.125 < interval[1]                 # the margin lies inside the interval
            assert body["outcome"] == outcome_from(interval, 0.125) == "advantage_not_shown"
    assert state["state"] == "description_reading_not_shown"
    assert held(states, "score", "held_out")["verdict"] == "description_reading_not_shown"
    # all six families: 0.5, 0.5, 0, 0, 0.5, 0.5 over shuffled and irrelevant; 0, 0, 0.25, 0.25, 0, 0 over the baseline
    everything = control_of(states, "score", "all")
    derived = set()
    for control, values in (("shuffled", [0.5, 0.5, 0.0, 0.0, 0.5, 0.5]), ("irrelevant", [0.5, 0.5, 0.0, 0.0, 0.5, 0.5]),
                            ("explanation_free", [0.0, 0.0, 0.25, 0.25, 0.0, 0.0])):
        for register in ("medical", "everyday"):
            label = f"7:held_artifact_score:matched_minus_{control}:{register}:all"
            outcome = outcome_from(independent_interval(values, label), 0.125)
            assert everything["comparisons"][control][register]["outcome"] == outcome
            derived.add((control, outcome))
    assert derived == {("shuffled", "control_beaten"), ("irrelevant", "control_beaten"),
                       ("explanation_free", "advantage_not_shown")}
    assert everything["state"] == "baseline_advantage_not_shown"
    assert held(states, "score", "all")["verdict"] == "baseline_advantage_not_shown"
    # the rule on the boundary: an interval that ends on the margin is not above it
    assert (outcome_from([0.125, 0.25], 0.125), outcome_from([0.0, 0.125], 0.125)) == ("advantage_not_shown",
                                                                                      "control_not_beaten")


def test_a_cue_that_is_not_exposed_is_reported_and_is_never_a_pass(report: dict, states: dict) -> None:
    cues = controls(states)["item_cues"]
    assert {cue: body["state"] for cue, body in cues.items()} == {
        "span_position": "exposed", "span_marking": "not_exposed", "window_length": "exposed",
        "presentation_order": "exposed"}
    assert (cues["span_marking"]["n_items"], cues["span_marking"]["n_items_recorded"]) == (24, 0)
    assert cues["span_marking"]["bundle_field"] == "evaluation_items[].span_marking"
    assert "span_marking" not in controls(states)["explanation_free"]["parameters"]
    for name in states["analysis_sets"]:
        assert control_of(states, "score", name)["item_cues_not_exposed"] == ["span_marking"]
    assert {body["state"] for body in controls(states, "label")["item_cues"].values()} == {"exposed"}
    # no description order is recorded in the base fixture or at the score stage of the control-state fixture
    for scored in (report, states):
        order = held(scored)["description_cues"]["description_order"]
        assert (order["state"], order["n_pairs_recorded"], order["association_with_score_difference"]) == (
            "not_exposed", 0, {"state": "not_exposed"})
    # the base controls passed with that cue unexposed; the cue's own state stays not_exposed and is reported beside it
    assert held(report)["control_state"] == "controls_passed"
    assert not any("pass" in name for name in iv.CUE_STATES + iv.ASSOCIATION_STATES)
    assert "a cue reported as not_exposed was not checked; it is not a pass" in report["limitations"]


def test_a_cue_recorded_for_some_items_only_is_missing_data(states_bundle: dict) -> None:
    partial = copy.deepcopy(states_bundle)
    del next(item for item in partial["evaluation_items"] if item["artifact_id"] == "label_artifact_5")["span_position"]
    result = iv.score_bundle(partial)
    cue = controls(result, "label")["item_cues"]["span_position"]
    assert (cue["state"], cue["n_items"], cue["n_items_recorded"]) == ("partly_recorded", 24, 23)
    assert "span_position" not in controls(result, "label")["explanation_free"]["candidate_rules"]
    state = control_of(result, "label", "fresh_test")
    assert (state["state"], state["item_cues_partly_recorded"]) == ("control_incomplete", ["span_position"])
    assert held(result, "label", "fresh_test")["verdict"] == "control_incomplete"

    del next(record for record in states_bundle["held_artifact"] if record["artifact_id"] == "label_artifact_6"
             and record["description_register"] == "everyday")["description_token_count"]
    result = iv.score_bundle(states_bundle)
    length = held(result, "label", "fresh_test")["description_cues"]["description_length"]
    assert (length["state"], length["n_pairs"], length["n_pairs_recorded"]) == ("partly_recorded", 2, 1)
    assert length["association_with_score_difference"] == {"state": "partly_recorded", "n_families": 2,
                                                           "n_families_recorded": 1}
    pair = next(row for row in result["held_artifact"]["label"]["per_artifact"]
                if row["artifact_id"] == "label_artifact_6")
    assert (pair["token_count_difference"], pair["length_confounded"]) == (None, None)       # unknown, not "equal"


def test_a_length_confounded_pair_is_flagged_beside_every_difference(report: dict, states: dict) -> None:
    pairs = {row["artifact_id"]: row for row in report["held_artifact"]["score"]["per_artifact"]}
    unequal = pairs["artifact_5a"]
    assert (unequal["medical_description_token_count"], unequal["everyday_description_token_count"],
            unequal["token_count_difference"], unequal["length_confounded"]) == (6, 12, -6, True)
    assert [artifact_id for artifact_id, row in pairs.items() if row["length_confounded"]] == ["artifact_5a"]
    assert [artifact_id for artifact_id, row in pairs.items() if row["formatting_differs"]] == ["artifact_6"]
    assert all(row["medical_presented_first"] is None for row in pairs.values())
    for name in report["analysis_sets"]:                    # reported with every medical-minus-everyday difference
        assert set(held(report, "score", name)["description_cues"]) == set(iv.DESCRIPTION_CUES)
    length = held(report)["description_cues"]["description_length"]
    assert (length["state"], length["n_pairs"], length["n_pairs_recorded"]) == ("exposed", 7, 7)
    assert length["length_confounded_artifact_ids"] == ["artifact_5a"]
    assert length["mean_token_count_difference"] == pytest.approx(-6 / 7)
    # six pairs of equal length: five differences of 0.25 and artifact_5b's 0.125. The unequal pair: 0.375
    assert length["score_difference_by_length_match"] == {
        "length_matched": {"n_artifacts": 6, "mean_score_difference": pytest.approx((5 * 0.25 + 0.125) / 6)},
        "length_differs": {"n_artifacts": 1, "mean_score_difference": 0.375}}
    # the six family differences are all 0.25: no association can be computed. That is not "no association".
    association = length["association_with_score_difference"]
    assert (association["state"], association["reason"], association["p_value"]) == ("not_computable",
                                                                                    "score_constant", None)
    held_out = held(report, "score", "held_out")["description_cues"]
    assert held_out["description_length"]["mean_token_count_difference"] == pytest.approx(-6 / 5)
    assert held_out["description_formatting"]["formatting_differs_artifact_ids"] == ["artifact_6"]
    validation = held(report, "score", "validation")["description_cues"]["description_length"]
    assert (validation["length_confounded_artifact_ids"], validation["mean_token_count_difference"]) == ([], 0.0)
    label = {row["artifact_id"]: row for row in states["held_artifact"]["label"]["per_artifact"]}
    assert (label["label_artifact_1"]["token_count_difference"], label["label_artifact_1"]["length_confounded"],
            label["label_artifact_1"]["formatting_differs"]) == (-8, True, True)
    assert (label["label_artifact_2"]["token_count_difference"], label["label_artifact_2"]["length_confounded"],
            label["label_artifact_2"]["formatting_differs"]) == (-4, True, False)
    assert held(states, "label", "discovery")["description_cues"]["description_length"][
        "length_confounded_artifact_ids"] == ["label_artifact_1", "label_artifact_2"]


def test_cue_association_is_a_seeded_permutation_test(states: dict) -> None:
    # five families with the cue and the score in the same order: r = 1. Of the 120 orderings of the cue only the
    # identity (r = 1) and the reversal (r = -1) reach |r| = 1, so the exact p-value is 2 / 120.
    xs, ys = [1.0, 2.0, 3.0, 4.0, 5.0], [0.125, 0.25, 0.375, 0.5, 0.625]
    result = iv.permutation_association(xs, ys, 2000, 0.05, "7:cue:hand")
    r, p = independent_association(xs, ys, 2000, "7:cue:hand")
    assert result["pearson_r"] == pytest.approx(1.0) and r == pytest.approx(1.0)
    assert result["p_value"] == p and abs(p - 2 / 120) < 0.012
    assert (result["state"], result["n_families"], result["permutations"], result["alpha"], result["seed_label"]) == (
        "association_detected", 5, 2000, 0.05, "7:cue:hand")
    assert iv.permutation_association(xs, ys, 2000, 0.05, "7:cue:hand") == result             # same seed, same result
    assert iv.permutation_association(xs, ys, 2000, 0.001, "7:cue:hand")["state"] == "association_not_detected"
    for cue, score, reason in (([1.0, 2.0], [0.5, 0.25], "fewer_than_three_families"),
                               ([8.0, 8.0, 8.0], [0.5, 0.25, 0.0], "cue_constant"),
                               ([8.0, 4.0, 0.0], [0.25, 0.25, 0.25], "score_constant")):
        missing = iv.permutation_association(cue, score, 2000, 0.05, "7:cue:hand")
        assert (missing["state"], missing["reason"], missing["pearson_r"], missing["p_value"]) == (
            "not_computable", reason, None, None)

    # label stage, all six families. Token difference (medical - everyday): -8, -4, 0, 0, 0, 0. Score difference:
    # 0.5, 0.25, 0, 0, 0, 0, which is the token difference times -1/16, so r = -1. An ordering reaches |r| = 1 only
    # with -8 on family_1 and -4 on family_2: 1 of the 6 * 5 = 30 placements of those two values, so p is 1 / 30.
    length = held(states, "label", "all")["description_cues"]["description_length"]
    association = length["association_with_score_difference"]
    label = "7:cue:label:description_length:all"
    r, p = independent_association([-8.0, -4.0, 0.0, 0.0, 0.0, 0.0], [0.5, 0.25, 0.0, 0.0, 0.0, 0.0], 2000, label)
    assert association["pearson_r"] == pytest.approx(-1.0) and r == pytest.approx(-1.0)
    assert (association["p_value"], association["seed_label"], association["n_families"]) == (p, label, 6)
    assert abs(p - 1 / 30) < 0.012 and association["state"] == "association_detected"
    assert length["mean_token_count_difference"] == -2.0                    # (-8 - 4) / 6
    # the control state of that set is control_incomplete; the association is reported whatever the control state
    assert held(states, "label", "all")["control_state"] == "control_incomplete"

    # description order: the medical description is first on families 1, 3, 5. With x - 0.5 = +-0.5 and
    # y - 0.125 = 0.375, 0.125, -0.125 (four times): sum of products = 0.5 * 0.375 - 0.5 * 0.125 = 0.125,
    # sum of squares 6 * 0.25 = 1.5 and 0.140625 + 5 * 0.015625 = 0.21875.
    order = held(states, "label", "all")["description_cues"]["description_order"]
    assert (order["state"], order["n_pairs"], order["n_pairs_medical_first"]) == ("exposed", 6, 3)
    association = order["association_with_score_difference"]
    assert association["pearson_r"] == pytest.approx(0.125 / math.sqrt(1.5 * 0.21875))
    # the sum of products of any ordering is +-0.375 or +-0.125, so every ordering reaches the observed |r|: p = 1
    assert (association["p_value"], association["state"]) == (1.0, "association_not_detected")
    assert "an association that was not detected is not evidence that the cue has no effect" in states["limitations"]


def test_window_length_is_checked_against_the_matched_score_over_families(bundle: dict, report: dict) -> None:
    for register in ("medical", "everyday"):        # every artifact's windows average (12 + 16) / 2 = 14 tokens
        association = control_of(report)["window_length_association"][register]
        assert (association["state"], association["reason"]) == ("not_computable", "cue_constant")
    for item in bundle["evaluation_items"]:
        if item["artifact_id"] == "artifact_3":
            item["window_token_count"] += 8
    result = iv.score_bundle(bundle)
    association = control_of(result)["window_length_association"]["everyday"]
    # cue: 14 for five families, 22 for family_3. Score: 0.75 for five families, 0.6875 for family_5. Two
    # one-family departures on different families of six correlate at -1/5 when both go the same way; one is
    # upward and one downward, so r = +1/5. Any ordering puts the long windows on family_5 (r = -1) or
    # elsewhere (|r| = 1/5), so every ordering reaches the observed |r| and p = 1.
    assert association["pearson_r"] == pytest.approx(0.2)
    assert (association["p_value"], association["state"], association["seed_label"]) == (
        1.0, "association_not_detected", "7:cue:score:window_length:everyday:all")
    # artifact_3 is a validation artifact: the rules fitted on discovery items did not move
    assert controls(result)["explanation_free"]["parameters"] == controls(report)["explanation_free"]["parameters"]


def test_label_and_score_stages_carry_the_control_state_and_no_pass_verdict(report: dict, states: dict) -> None:
    # the base fixture has no held-artifact record at the label stage, so no control was run there
    label = report["stages"]["label"]["description_controls"]
    assert label["state_by_analysis_set"] == dict.fromkeys(report["analysis_sets"], "control_not_run")
    primary = report["primary_results"]["fact_recovery_rate_difference"]
    assert (primary["label"]["verdict"], primary["label"]["description_control_state"]) == (
        "equivalent_within_margin", "control_not_run")
    assert (primary["score"]["verdict"], primary["score"]["description_control_state"]) == (
        "equivalent_within_margin", "controls_passed")
    for stage in ("activation", "readout"):
        assert "description_control_state" not in primary[stage]
        assert "description_controls" not in report["stages"][stage]
    assert report["control_rule"].endswith("The report holds no verdict that a stage passes.")
    assert report["held_artifact"]["control_rule"] == report["control_rule"]
    # in both reports a held-artifact verdict is one of the three outcomes exactly where the controls passed
    seen = set()
    for scored in (report, states):
        for stage in ("label", "score"):
            for summary in scored["held_artifact"][stage].get("analysis_sets", {}).values():
                seen.add(summary["control_state"])
                assert summary["control_state"] in iv.CONTROL_STATES
                if summary["control_state"] == "controls_passed":
                    assert summary["verdict"] in THREE_OUTCOMES and summary["verdict_issued"] is True
                else:
                    assert summary["verdict"] == summary["control_state"] and summary["verdict_issued"] is False
    assert seen == set(iv.CONTROL_STATES)                        # the two fixtures reach every named state


def test_every_random_step_of_the_controls_records_its_seed(bundle: dict, report: dict) -> None:
    randomness = report["control_randomness"]
    assert randomness["generator"] == "random.Random"
    assert randomness["shuffle_seed_rule"] == "'<description_controls.shuffle.seed>:shuffle:<stage>'"
    assert randomness["description_controls"]["shuffle"]["seed"] == 11
    assert randomness["description_controls"]["cue_association"] == {"permutations": 2000, "alpha": 0.05}
    body = control_of(report)["comparisons"]["shuffled"]["medical"]
    assert body["seed_label"] == "7:held_artifact_score:matched_minus_shuffled:medical:all"
    bundle["seed"] = 8
    other = iv.score_bundle(bundle)
    assert control_of(other)["comparisons"]["shuffled"]["medical"]["seed_label"] == (
        "8:held_artifact_score:matched_minus_shuffled:medical:all")
    assert controls(other)["shuffle"]["seed_label"] == "11:shuffle:score"       # the shuffle has its own seed
    assert control_of(other)["comparisons"]["shuffled"]["medical"]["mean_difference"] == body["mean_difference"]


def test_a_bundle_in_the_earlier_shape_stays_valid_and_gets_no_held_artifact_verdict(bundle: dict,
                                                                                    report: dict) -> None:
    del bundle["description_controls"], bundle["evaluation_items"]
    for record in bundle["held_artifact"]:
        for field in iv.DESCRIPTION_CUES.values():
            record.pop(field, None)
    assert iv.validate_bundle(bundle)["status"] == "validated"
    result = iv.score_bundle(bundle)
    summary = held(result)
    assert (summary["mean_difference"], summary["interval"]) == (0.25, [0.25, 0.25])
    assert (summary["verdict"], summary["control_state"], summary["verdict_issued"]) == ("control_not_run",
                                                                                       "control_not_run", False)
    assert control_of(result) == {"state": "control_not_run", "reason": "no_description_controls_plan"}
    assert result["primary_results"]["held_artifact_score_difference"]["score"]["verdict"] == "control_not_run"
    length = summary["description_cues"]["description_length"]
    assert (length["state"], length["length_confounded_artifact_ids"], length["mean_token_count_difference"]) == (
        "not_exposed", [], None)
    assert [row["length_confounded"] for row in result["held_artifact"]["score"]["per_artifact"]] == [None] * 7
    for stage in ("activation", "readout", "label", "score"):       # the stage endpoints do not use the controls
        for key in ("fact_recovery", "changed_fact_sensitivity", "behaviour_by_representation"):
            assert result["stages"][stage][key] == report["stages"][stage][key]


def _swap_shuffle_sources(bundle: dict) -> None:
    mapping = bundle["description_controls"]["shuffle"]["mapping"]["score"]
    mapping["artifact_3"], mapping["artifact_4"] = mapping["artifact_4"], mapping["artifact_3"]


def _shuffled_description_with_its_own_text(bundle: dict) -> None:
    source = bundle["description_controls"]["shuffle"]["mapping"]["score"]["artifact_1"]
    text = next(r["description_text"] for r in bundle["held_artifact"]
                if r["artifact_id"] == source and r["description_register"] == "medical")
    bundle["held_artifact"][0]["description_text"] = text


def _both_descriptions_first(bundle: dict) -> None:
    bundle["held_artifact"][0]["presentation_order"] = bundle["held_artifact"][1]["presentation_order"] = 1


def _drop_control(key: str):
    def mutate(bundle: dict) -> None:
        del bundle["description_controls"][key]
    return mutate


@pytest.mark.parametrize(("mutate", "code"), [
    (_set(("description_controls", "prespecified"), False), "control_margins_not_prespecified"),
    (_set(("description_controls", "fixed_before_data"), " "), "control_margins_not_prespecified"),
    (_set(("description_controls", "score_metric"), "pooled_correlation"), "score_metric"),
    (_set(("description_controls", "margins"), {"matched_minus_shuffled": 0.125}), "missing_control_margins"),
    (_set(("description_controls", "margins", "matched_minus_blank"), 0.125), "unknown_control_margin"),
    (_set(("description_controls", "margins", "matched_minus_explanation_free"), 0), "invalid_margin"),
    (_set(("description_controls", "explanation_free_rules"), ["always_positive"]), "explanation_free_rule_family"),
    (_set(("description_controls", "irrelevant_description", "text"), "another placeholder"),
     "irrelevant_description"),
    (_set(("description_controls", "shuffle", "seed"), -1), "missing_seed"),
    (_set(("description_controls", "shuffle", "mapping", "readout"), {}), "unknown_stage"),
    (_swap_shuffle_sources, "shuffle_mapping_not_reproducible"),
    (_shuffled_description_with_its_own_text, "shuffle_identical_description"),
    (_set(("description_controls", "cue_association", "alpha"), 1), "analysis_plan"),
    (_set(("description_controls", "cue_association", "permutations"), 0), "analysis_plan"),
    (_drop_control("cue_association"), "schema"),
    (_drop_control("shuffle"), "schema"),
    (_set(("evaluation_items", 0, "artifact_id"), "artifact_9"), "unknown_artifact"),
    (_set(("evaluation_items", 1, "item_id"), "p1"), "duplicate_item"),
    (_set(("evaluation_items", 0, "verdicts", "reversed"), True), "verdict_condition"),
    (_set(("evaluation_items", 0, "window_token_count"), 0), "invalid_cue_value"),
    (_set(("evaluation_items", 1, "presentation_index"), 1), "invalid_cue_value"),
    (_set(("evaluation_items", 0, "span_position"), " "), "invalid_cue_value"),
    (_set(("evaluation_items", 0, "label"), "yes"), "schema"),
    (_set(("evaluation_items", 0, "verdicts", "medical"), "yes"), "schema"),
    (_set(("held_artifact", 0, "description_token_count"), 0), "invalid_cue_value"),
    (_set(("held_artifact", 0, "presentation_order"), 3), "invalid_cue_value"),
    (_both_descriptions_first, "invalid_cue_value"),
    (_set(("held_artifact", 0, "score"), 0.875), "score_not_reproduced_from_items"),
])
def test_named_control_refusals(bundle: dict, mutate, code: str) -> None:
    mutate(bundle)
    assert refusal_code(bundle) == code
    with pytest.raises(iv.Refusal) as caught:
        iv.validate_bundle(bundle)
    assert caught.value.code == code


def test_no_failed_or_missing_control_ends_in_an_equivalence_verdict(states: dict) -> None:
    # every set below has a zero difference in each family: interval [0, 0], inside the 0.125 margin, which the
    # verdict rule alone calls equivalent_within_margin
    withheld = {("score", "validation"): "scorer_does_not_read_description",
                ("score", "fresh_test"): "baseline_not_beaten",
                ("score", "held_out"): "description_reading_not_shown",
                ("score", "all"): "baseline_advantage_not_shown",
                ("label", "validation"): "control_not_run",
                ("label", "held_out"): "control_incomplete"}
    for (stage, name), state in withheld.items():
        summary = held(states, stage, name)
        assert (summary["mean_difference"], summary["interval"], summary["margin"]) == (0.0, [0.0, 0.0], 0.125)
        assert summary["verdict"] == state
    passed = held(states, "label", "fresh_test")              # the same numbers, with every control beaten
    assert (passed["mean_difference"], passed["interval"], passed["verdict"]) == (0.0, [0.0, 0.0],
                                                                                 "equivalent_within_margin")


def test_specification_keeps_the_fixed_statements_and_defines_every_state() -> None:
    text = " ".join(SPECIFICATION.read_text(encoding="utf-8").split())
    for sentence in (
            "**Status: proposed PatientWords contribution; no register bias has been measured with it.**",
            "Its reported result is a reason to test these controls in PatientWords, not evidence that PatientWords "
            "already has that failure.",
            "Equal behaviour on a measured endpoint does not imply identical hidden states, and it does not establish "
            "instrument bias.",
            "this file makes no novelty claim",
            "They are not results and describe no scorer.",
            "established independently of every interpretability instrument",
            "**Within-register paraphrases.**", "**Changed-fact controls.**", "**Split before development.**",
            "A practical equivalence margin is fixed for each endpoint that receives a verdict, before any data.",
            "Hold the underlying artifact fixed",
            "**The control margins are placeholders.**"):
        assert sentence in text, sentence
    names = (iv.CONTROL_STATES + iv.CONTROL_OUTCOMES + iv.CUE_STATES + iv.ASSOCIATION_STATES + iv.EXPLANATION_FREE_RULES
             + tuple(iv.CONTROL_MARGINS.values()) + iv.ARM_STATES + iv.ARMS + tuple(iv.ARM_MARGINS.values()))
    for name in names:
        assert f"`{name}`" in text, name
    for question in ("1. **Decided by the owner, 2026-11-10: yes.**", "2. **Partly decided by the owner, 2026-11-10.**",
                     # Question 3 was decided by the owner on 2026-11-11 (the input-only and control-artifact
                     # arms); question 4 stays open as a general rule and is fixed for the first experiment only.
                     "3. **Decided by the owner, 2026-11-11: yes.**",
                     "4. **Open as a general rule; fixed for the first experiment.**"):
        assert question in text, question
