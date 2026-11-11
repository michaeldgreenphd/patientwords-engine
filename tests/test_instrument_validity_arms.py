"""The input-only and control-artifact arms of the instrument-validity scorer, and the repeated-phrase refusal.

Synthetic software checks only; nothing here is a measurement. Every bundle is built from
tests/fixtures/instrument_validity/synthetic_bundle.v1.json (six families, two per split; four reference facts per
family; seed 7; 2,000 resamples at 0.95; minimum of three families for an interval; primary set held_out, which is
family_3 to family_6). The label stage is overwritten so that the hand-worked values are simple:

* Actual-artifact arm (the stage's own rows): every paired-register row recovers all four facts, rate 1.
* An arm row that recovers nothing has rate 0, so "actual minus arm" is 1 for that family; an arm row that recovers
  everything gives 0.
* With a difference of 1 in every held-out family the bootstrap interval is [1, 1]: above the margin of 0.125.
  With 0 in every family it is [0, 0]: at or below the margin. With 1, 1, 0, 0 the resampled mean is 0 with
  probability (1/2)^4 = 1/16 and 1 with probability 1/16, both above 2.5%, so the percentile interval is [0, 1],
  which contains the margin.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import instrument_validity as iv  # noqa: E402
from scripts.exploratory_methods import Refusal  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "instrument_validity" / "synthetic_bundle.v1.json"
STAGE = "label"
HELD_OUT = ("family_3", "family_4", "family_5", "family_6")
ALL, NONE = "recovered", "not_recovered"


def _base() -> dict:
    """The fixture with a complete label stage in which every paired-register row recovers every fact."""
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = bundle["stages"][STAGE]["observations"]
    paired = {(f["family_id"], v["variant_id"]) for f in bundle["families"] for v in f["variants"]
              if v["register"] in iv.PAIRED_REGISTERS}
    present = {(row["family_id"], row["variant_id"]) for row in rows}
    template = next(row for row in rows if (row["family_id"], row["variant_id"]) in paired)
    for fid, vid in sorted(paired - present):                       # the fixture omits one everyday row
        rows.append({**copy.deepcopy(template), "family_id": fid, "variant_id": vid, "behaviour_value": None,
                     "representation_value": None})
    facts = {f["family_id"]: [x["fact_id"] for x in f["reference_facts"]] for f in bundle["families"]}
    for row in rows:
        if (row["family_id"], row["variant_id"]) in paired:
            row["fact_recovery"] = dict.fromkeys(facts[row["family_id"]], ALL)
    return bundle


def _with_arms(input_only: dict[str, str] | str, control: dict[str, str] | str, bundle: dict | None = None) -> dict:
    """Add both arms. A string gives every family that status; a dict gives one per family (other families: NONE)."""
    bundle = bundle or _base()
    families = {f["family_id"]: f for f in bundle["families"]}
    mapping, _ = iv.seeded_derangement({fid: fid for fid in families}, f"{bundle['seed']}:control_artifact:{STAGE}")
    observations = []
    for fid, family in sorted(families.items()):
        facts = [x["fact_id"] for x in family["reference_facts"]]
        for variant in family["variants"]:
            if variant["register"] not in iv.PAIRED_REGISTERS:
                continue
            for arm, spec in (("input_only", input_only), ("control_artifact", control)):
                status = spec if isinstance(spec, str) else spec.get(fid, NONE)
                row = {"family_id": fid, "variant_id": variant["variant_id"], "arm": arm,
                       "fact_recovery": dict.fromkeys(facts, status)}
                if arm == "control_artifact":
                    row["control_family_id"] = mapping[fid]
                observations.append(row)
    bundle["verbalizer_arms"] = {
        "prespecified": True, "fixed_before_data": "synthetic fixture; written before the placeholder rows",
        "margins": {"artifact_minus_input_only": 0.125, "artifact_minus_control_artifact": 0.125},
        "stages": {STAGE: {"control_artifact_rule": "placeholder rule: same register, another family's artifact",
                           "observations": observations}}}
    return bundle


def _state(bundle: dict, analysis_set: str = "held_out") -> tuple[str, dict]:
    arms = iv.score_bundle(bundle)["stages"][STAGE]["verbalizer_arms"]
    return arms["state_by_analysis_set"][analysis_set], arms


def test_a_bundle_without_the_arms_reports_arms_not_run_and_changes_no_other_result() -> None:
    plain = iv.score_bundle(_base())
    arms = plain["stages"][STAGE]["verbalizer_arms"]
    assert arms["status"] == iv.ARMS_NOT_RUN and set(arms["state_by_analysis_set"].values()) == {iv.ARMS_NOT_RUN}
    assert plain["primary_results"]["fact_recovery_rate_difference"][STAGE]["artifact_arm_state"] == iv.ARMS_NOT_RUN
    assert "artifact_arm_state" not in plain["primary_results"]["fact_recovery_rate_difference"]["readout"]
    assert plain["arm_rule"] == iv.ARM_RULE
    with_arms = iv.score_bundle(_with_arms(NONE, NONE))
    for stage in iv.STAGES:                                # the arms add a block; every earlier result is unchanged
        before = {k: v for k, v in plain["stages"][stage].items() if k != "verbalizer_arms"}
        after = {k: v for k, v in with_arms["stages"][stage].items() if k != "verbalizer_arms"}
        assert before == after
    assert plain["held_artifact"] == with_arms["held_artifact"]


def test_artifact_contributes_only_when_both_arms_are_beaten_in_each_register() -> None:
    state, arms = _state(_with_arms(NONE, NONE))
    assert state == iv.ARTIFACT_CONTRIBUTES
    body = arms["analysis_sets"]["held_out"]
    for arm in iv.ARMS:
        for register in iv.PAIRED_REGISTERS:
            entry = body["comparisons"][arm][register]
            assert (entry["mean_difference"], entry["interval"], entry["outcome"]) == (1.0, [1.0, 1.0], iv.BEATEN)
            assert entry["n_included"] == 4 and entry["arm_margin"] == 0.125
            assert entry["seed_label"] == f"7:verbalizer_arms_label:artifact_minus_{arm}:{register}:held_out"
    assert body["failed_comparisons"] == []
    # Every arm has the same rate in both registers, so each register difference is 0, by hand.
    assert {arm: body["medical_minus_everyday_by_arm"][arm]["mean_difference"]
            for arm in ("artifact", *iv.ARMS)} == {"artifact": 0.0, "input_only": 0.0, "control_artifact": 0.0}
    assert body["register_difference_beyond_input_only"]["mean_difference"] == 0.0


def test_credit_earned_from_the_wording_alone_is_named_and_is_not_a_pass() -> None:
    state, arms = _state(_with_arms(ALL, NONE))
    assert state == iv.NO_ADVANTAGE_OVER_WORDING
    entry = arms["analysis_sets"]["held_out"]["comparisons"]["input_only"]["medical"]
    assert (entry["mean_difference"], entry["interval"], entry["outcome"]) == (0.0, [0.0, 0.0], iv.NOT_BEATEN)
    assert arms["analysis_sets"]["held_out"]["failed_comparisons"] == [
        "artifact_minus_input_only:medical", "artifact_minus_input_only:everyday"]


def test_a_control_artifact_that_scores_as_well_is_reported_first() -> None:
    # Both comparisons fail; the state names the control artifact, the first comparison in the order of the rule.
    assert _state(_with_arms(ALL, ALL))[0] == iv.NO_ADVANTAGE_OVER_CONTROL
    assert _state(_with_arms(NONE, ALL))[0] == iv.NO_ADVANTAGE_OVER_CONTROL


@pytest.mark.parametrize("input_only, control, expected", [
    (NONE, {"family_5": ALL, "family_6": ALL}, iv.SPECIFICITY_NOT_SHOWN),
    ({"family_5": ALL, "family_6": ALL}, NONE, iv.CONTRIBUTION_NOT_SHOWN),
])
def test_an_interval_that_contains_the_margin_is_not_shown(input_only, control, expected: str) -> None:
    state, arms = _state(_with_arms(input_only, control))
    assert state == expected
    arm = "control_artifact" if expected == iv.SPECIFICITY_NOT_SHOWN else "input_only"
    entry = arms["analysis_sets"]["held_out"]["comparisons"][arm]["medical"]
    assert (entry["mean_difference"], entry["interval"], entry["outcome"]) == (0.5, [0.0, 1.0], iv.NOT_SHOWN)


def test_zero_recovery_in_every_arm_is_no_demonstrated_advantage_and_says_nothing_about_the_cause() -> None:
    """Regression, 2026-11-11. With no fact recovered by the actual artifact, by the wording alone or by the
    control artifact, every difference is 0 - 0 = 0 and the interval [0, 0] is at or below the margin. The state
    was named system_does_not_read_artifact and the rule attributed the stage's result to the wording. Neither
    follows: nothing was recovered, so nothing can be said about where recovery comes from."""
    bundle = _with_arms(NONE, NONE)
    paired = {v["variant_id"] for f in bundle["families"] for v in f["variants"]
              if v["register"] in iv.PAIRED_REGISTERS}
    for row in bundle["stages"][STAGE]["observations"]:
        if row["variant_id"] in paired:
            row["fact_recovery"] = dict.fromkeys(row["fact_recovery"], NONE)
    report = iv.score_bundle(bundle)
    arms = report["stages"][STAGE]["verbalizer_arms"]
    body = arms["analysis_sets"]["held_out"]
    assert body["state"] == iv.NO_ADVANTAGE_OVER_CONTROL == "no_advantage_over_control_artifact"
    assert body["no_fact_recovered_in_any_arm"] is True
    assert body["mean_rates"]["artifact"] == body["mean_rates"]["input_only"] == body["mean_rates"][
        "control_artifact"] == {"medical": 0.0, "everyday": 0.0}
    for arm in iv.ARMS:                                        # the calculation is unchanged: 0 against 0.125
        for register in iv.PAIRED_REGISTERS:
            entry = body["comparisons"][arm][register]
            assert (entry["mean_difference"], entry["interval"], entry["outcome"]) == (0.0, [0.0, 0.0], iv.NOT_BEATEN)
    meaning = body["state_meaning"]
    assert "no demonstrated advantage" in meaning and iv.NOTHING_RECOVERED_NOTE in meaning
    # No state name, meaning or rule says the system does not read the artifact or that recovery came from wording.
    text = json.dumps({"states": iv.ARM_STATES, "meanings": iv.ARM_STATE_MEANING, "rule": iv.ARM_RULE, "arms": arms})
    for claim in ("does_not_read", "does not read", "recoverable_from_wording", "evidence about how the system reads"):
        assert claim not in text, claim
    assert "establishes nothing more" in iv.ARM_RULE and "is not evidence for either" in iv.ARM_RULE
    # A family that was not measured did not "recover nothing": with the arm rows of all but one held-out family
    # removed, the recorded family still scores zero everywhere, the state is arms_incomplete, and neither the
    # flag nor the note is set. (Review finding, 2026-11-11: the flag was computed from the families that had a
    # rate, so one recorded family set it for the whole set.)
    partial = _with_arms(NONE, NONE)
    for row in partial["stages"][STAGE]["observations"]:
        if row["variant_id"] in paired:
            row["fact_recovery"] = dict.fromkeys(row["fact_recovery"], NONE)
    stage_arms = partial["verbalizer_arms"]["stages"][STAGE]
    stage_arms["observations"] = [row for row in stage_arms["observations"] if row["family_id"] == "family_3"]
    some = iv.score_bundle(partial)["stages"][STAGE]["verbalizer_arms"]["analysis_sets"]["held_out"]
    entry = some["comparisons"]["input_only"]["medical"]
    assert some["state"] == iv.ARMS_INCOMPLETE and entry["n_included"] == 1 < entry["n_families"]
    assert some["mean_rates"]["input_only"] == {"medical": 0.0, "everyday": 0.0}      # the one recorded family
    assert some["no_fact_recovered_in_any_arm"] is False and iv.NOTHING_RECOVERED_NOTE not in some["state_meaning"]
    # A set with too few families has no interval: the state is a not_shown state and its meaning says so.
    assert "too few families for an interval" in iv.ARM_STATE_MEANING[iv.SPECIFICITY_NOT_SHOWN]
    assert "too few families for an interval" in iv.ARM_STATE_MEANING[iv.CONTRIBUTION_NOT_SHOWN]
    # A set where something was recovered does not carry the note.
    recovered = iv.score_bundle(_with_arms(ALL, NONE))["stages"][STAGE]["verbalizer_arms"]["analysis_sets"]["held_out"]
    assert recovered["no_fact_recovered_in_any_arm"] is False and iv.NOTHING_RECOVERED_NOTE not in recovered["state_meaning"]
    assert recovered["mean_rates"]["input_only"] == {"medical": 1.0, "everyday": 1.0}


def test_missing_arm_data_is_incomplete_or_not_run_and_never_a_pass() -> None:
    bundle = _with_arms(NONE, NONE)
    rows = bundle["verbalizer_arms"]["stages"][STAGE]["observations"]
    dropped = next(i for i, row in enumerate(rows) if row["family_id"] == "family_4" and row["arm"] == "input_only")
    removed = rows.pop(dropped)
    state, arms = _state(bundle)
    assert state == iv.ARMS_INCOMPLETE and arms["analysis_sets"]["held_out"]["arms_incomplete"] == ["input_only"]
    register = next(v["register"] for f in bundle["families"] if f["family_id"] == "family_4"
                    for v in f["variants"] if v["variant_id"] == removed["variant_id"])
    excluded = arms["analysis_sets"]["held_out"]["comparisons"]["input_only"][register]["excluded"]
    assert excluded == [{"family_id": "family_4", "reason": f"missing_arm:input_only:{register}"}]
    # An unassessed fact is a missing value, not a zero.
    bundle = _with_arms(NONE, NONE)
    row = next(r for r in bundle["verbalizer_arms"]["stages"][STAGE]["observations"]
               if r["family_id"] == "family_3" and r["arm"] == "control_artifact")
    row["fact_recovery"]["fact_a"] = None
    assert _state(bundle)[0] == iv.ARMS_INCOMPLETE
    # One arm absent altogether: not run.
    bundle = _with_arms(NONE, NONE)
    stage = bundle["verbalizer_arms"]["stages"][STAGE]
    stage["observations"] = [r for r in stage["observations"] if r["arm"] == "input_only"]
    state, arms = _state(bundle)
    assert state == iv.ARMS_NOT_RUN and arms["analysis_sets"]["held_out"]["arms_not_run"] == ["control_artifact"]
    # A missing actual-artifact row also leaves the comparison incomplete.
    bundle = _with_arms(NONE, NONE)
    stage_rows = bundle["stages"][STAGE]["observations"]
    stage_rows.remove(next(r for r in stage_rows if r["variant_id"] == "f5_medical"))
    assert _state(bundle)[0] == iv.ARMS_INCOMPLETE


def test_a_register_difference_that_the_wording_alone_also_shows_is_reported_beside_the_artifact_arm() -> None:
    # Artifact arm and input-only arm alike: the medical variant recovers all four facts (rate 1) and the everyday
    # variant recovers two of four (rate 1/2), in every family. The control artifact recovers nothing.
    bundle = _with_arms(NONE, NONE)
    everyday = {v["variant_id"] for f in bundle["families"] for v in f["variants"] if v["register"] == "everyday"}

    def half(row: dict) -> dict:
        facts = sorted(row["fact_recovery"])
        return {fact: (ALL if i < len(facts) // 2 else NONE) for i, fact in enumerate(facts)}

    for row in bundle["stages"][STAGE]["observations"]:
        if row["variant_id"] in everyday:
            row["fact_recovery"] = half(row)
    for row in bundle["verbalizer_arms"]["stages"][STAGE]["observations"]:
        if row["arm"] == "input_only":
            row["fact_recovery"] = half(row) if row["variant_id"] in everyday else dict.fromkeys(
                row["fact_recovery"], ALL)
    report = iv.score_bundle(bundle)
    body = report["stages"][STAGE]["verbalizer_arms"]["analysis_sets"]["held_out"]
    by_arm = body["medical_minus_everyday_by_arm"]
    assert by_arm["artifact"]["mean_difference"] == 0.5 and by_arm["input_only"]["mean_difference"] == 0.5
    assert by_arm["control_artifact"]["mean_difference"] == 0.0
    beyond = body["register_difference_beyond_input_only"]
    assert (beyond["mean_difference"], beyond["interval"]) == (0.0, [0.0, 0.0])
    # The control artifact is beaten in both registers (1 - 0 and 1/2 - 0); the wording alone is not (0 and 0).
    assert body["comparisons"]["control_artifact"]["everyday"]["mean_difference"] == 0.5
    assert body["failed_comparisons"] == ["artifact_minus_input_only:medical", "artifact_minus_input_only:everyday"]
    # The stage's own fact-recovery verdict still says "different" (1/2 against a margin of 0.2); the arm state
    # says the artifact showed no advantage over the wording alone at the margin. It names no cause.
    primary = report["primary_results"]["fact_recovery_rate_difference"][STAGE]
    assert primary["verdict"] == iv.DIFFERENT and primary["artifact_arm_state"] == iv.NO_ADVANTAGE_OVER_WORDING


def _unknown_arm(b: dict) -> None:
    b["verbalizer_arms"]["stages"][STAGE]["observations"][0]["arm"] = "activation_only"


def _wrong_control(b: dict) -> None:
    row = next(r for r in b["verbalizer_arms"]["stages"][STAGE]["observations"] if r["arm"] == "control_artifact")
    row["control_family_id"] = row["family_id"]


def _paraphrase_row(b: dict) -> None:
    b["verbalizer_arms"]["stages"][STAGE]["observations"][0]["variant_id"] = "f1_paraphrase_medical"


def _duplicate(b: dict) -> None:
    rows = b["verbalizer_arms"]["stages"][STAGE]["observations"]
    rows.append(copy.deepcopy(rows[0]))


def _readout_stage(b: dict) -> None:
    b["verbalizer_arms"]["stages"]["readout"] = b["verbalizer_arms"]["stages"].pop(STAGE)


def _input_only_with_control(b: dict) -> None:
    row = next(r for r in b["verbalizer_arms"]["stages"][STAGE]["observations"] if r["arm"] == "input_only")
    row["control_family_id"] = "family_2"


@pytest.mark.parametrize("mutate, code", [
    (lambda b: b["verbalizer_arms"].update(prespecified=False), "arm_margins_not_prespecified"),
    (lambda b: b["verbalizer_arms"].update(fixed_before_data=" "), "arm_margins_not_prespecified"),
    (lambda b: b["verbalizer_arms"]["margins"].pop("artifact_minus_input_only"), "missing_arm_margins"),
    (lambda b: b["verbalizer_arms"]["margins"].update(artifact_minus_control_artifact=-0.5), "invalid_margin"),
    (lambda b: b["verbalizer_arms"]["stages"][STAGE].update(control_artifact_rule=""), "control_artifact_rule"),
    (_unknown_arm, "unknown_arm"),
    (_wrong_control, "control_artifact_mapping_not_reproducible"),
    (_paraphrase_row, "arm_variant"),
    (_input_only_with_control, "arm_variant"),
    (_duplicate, "duplicate_observation"),
    (_readout_stage, "unknown_stage"),
    (lambda b: b["verbalizer_arms"]["stages"][STAGE]["observations"][0]["fact_recovery"].update(fact_zz=ALL),
     "unknown_fact"),
    (lambda b: b["verbalizer_arms"]["stages"][STAGE]["observations"][0].update(note="x"), "schema"),
])
def test_named_arm_refusals(mutate, code: str) -> None:
    bundle = _with_arms(NONE, NONE)
    mutate(bundle)
    with pytest.raises(Refusal) as refused:
        iv.score_bundle(bundle)
    assert refused.value.code == code


def test_the_control_artifact_assignment_is_seeded_and_never_a_familys_own() -> None:
    bundle = _with_arms(NONE, NONE)
    arms = iv.score_bundle(bundle)["stages"][STAGE]["verbalizer_arms"]
    mapping = arms["control_artifact_mapping"]
    assert sorted(mapping) == sorted(mapping.values()) == sorted(f["family_id"] for f in bundle["families"])
    assert all(source != fid for fid, source in mapping.items())
    again, _ = iv.seeded_derangement({fid: fid for fid in mapping}, "7:control_artifact:label")
    assert again == mapping


def test_the_same_phrase_in_two_families_is_refused_as_one_unit() -> None:
    bundle = _base()
    first, second = bundle["families"][0], bundle["families"][1]            # both discovery
    assert first["split"] == second["split"]
    source = next(v for v in first["variants"] if v["register"] == "medical")
    target = next(v for v in second["variants"] if v["register"] == "medical")
    target["text"] = source["text"]
    with pytest.raises(Refusal) as refused:
        iv.score_bundle(bundle)
    assert refused.value.code == "repeated_phrase" and first["family_id"] in str(refused.value)
    assert source["text"] not in str(refused.value)                          # a refusal never repeats text


def test_no_state_but_artifact_contributes_is_described_as_reading_the_artifact() -> None:
    assert iv.ARM_STATES[0] == iv.ARTIFACT_CONTRIBUTES and len(set(iv.ARM_STATES)) == 7
    assert set(iv.ARM_STATE_MEANING) == set(iv.ARM_STATES)
    text = (ROOT / "docs" / "protocols" / "instrument_validity_benchmark.md").read_text(encoding="utf-8")
    for state in iv.ARM_STATES:
        assert f"`{state}`" in text, state
    for arm in iv.ARMS:
        assert f"`{arm}`" in text, arm


# ------------------------------------------------------------------------------------------ calibration record

def _discovery_only() -> dict:
    """family_1 and family_2 of the fixture (both discovery), with representation values on the paraphrase rows.

    Activation stage, by hand. The fixture's base values are 1 (f1 medical), 1 (f1 everyday), 1 (f2 medical).
    Paraphrase rows are set to 1.25 (f1 medical paraphrase), 0.75 (f1 everyday paraphrase) and 0.5 (f2 medical
    paraphrase). Absolute differences: family_1 0.25 and 0.25, mean 0.25; family_2 0.5. Over the two families:
    median (0.25 + 0.5) / 2 = 0.375; nearest-rank quantile 0.9 is item ceil(0.9 * 2) = 2, so 0.5; quantile 0.5 is
    item 1, so 0.25; maximum 0.5.
    """
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    keep = {"family_1", "family_2"}
    bundle["families"] = [f for f in bundle["families"] if f["family_id"] in keep]
    for stage in bundle["stages"].values():
        stage["observations"] = [row for row in stage["observations"] if row["family_id"] in keep]
    bundle["held_artifact"] = [row for row in bundle["held_artifact"] if row["family_id"] in keep]
    bundle.pop("description_controls", None)
    bundle.pop("evaluation_items", None)
    values = {"f1_paraphrase_medical": 1.25, "f1_paraphrase_everyday": 0.75, "f2_paraphrase_medical": 0.5}
    for row in bundle["stages"]["activation"]["observations"]:
        if row["variant_id"] in values:
            row["representation_value"] = values[row["variant_id"]]
    return bundle


def test_calibration_record_reports_within_register_variation_of_discovery_families() -> None:
    bundle = _discovery_only()
    bases = {row["variant_id"]: row["representation_value"] for row in bundle["stages"]["activation"]["observations"]}
    assert (bases["f1_medical"], bases["f1_everyday"], bases["f2_medical"]) == (1, 1, 1)      # the hand values above
    record = iv.calibration_record(bundle, 0.9)
    assert record["schema_version"] == iv.CALIBRATION_SCHEMA and record["synthetic"] is True
    assert record["families"] == ["family_1", "family_2"] and record["split"] == "discovery"
    measured = record["stages"]["activation"]["within_register_paraphrase"]
    assert measured["representation_value_abs_difference"] == {
        "n_families": 2, "median": 0.375, "quantile": 0.5, "maximum": 0.5}
    assert [row["representation_value_abs_difference"] for row in measured["per_family"]] == [0.25, 0.5]
    assert iv.calibration_record(bundle, 0.5)["stages"]["activation"]["within_register_paraphrase"][
        "representation_value_abs_difference"]["quantile"] == 0.25
    # A stage whose paraphrase rows carry no representation value reports nulls, never zero.
    assert record["stages"]["label"]["within_register_paraphrase"]["representation_value_abs_difference"] == {
        "n_families": 0, "median": None, "quantile": None, "maximum": None}
    assert "margin" not in json.dumps(record["stages"])                       # the record computes no margin


def test_calibration_refuses_any_family_outside_discovery_and_any_missing_quantile(tmp_path: Path, capsys) -> None:
    with pytest.raises(Refusal) as refused:
        iv.calibration_record(json.loads(FIXTURE.read_text(encoding="utf-8")), 0.9)
    assert refused.value.code == "calibration_reads_held_out" and "4 of 6" in str(refused.value)
    for quantile in (0.0, 1.0, 1):
        with pytest.raises(Refusal) as refused:
            iv.calibration_record(_discovery_only(), quantile)
        assert refused.value.code == "calibration_quantile"
    path = tmp_path / "calibration_bundle.json"
    path.write_text(json.dumps(_discovery_only()), encoding="utf-8")
    assert iv.main(["--bundle", str(path), "--calibrate"]) == 2               # no quantile is assumed
    assert json.loads(capsys.readouterr().out)["code"] == "calibration_quantile"
    assert iv.main(["--bundle", str(path), "--quantile", "0.9"]) == 2         # a quantile without --calibrate
    capsys.readouterr()
    assert iv.main(["--bundle", str(path), "--calibrate", "--quantile", "0.9"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "calibrated"
    assert iv.main(["--bundle", str(FIXTURE), "--calibrate", "--quantile", "0.9"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "calibration_reads_held_out"
