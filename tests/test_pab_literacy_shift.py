"""Tests for the cross-model literacy-shift analysis (Layer 2, offline).

The measures here are the ones a finding would be built on, so the tests target
the ways a behavioural measure quietly lies: a term list that matches inside
other words, a pairing that silently drops half the design, an arm label parsed
wrong so every conversation lands in neither arm.

No network, no PatientAgentBench import.
"""

import json

import pytest

from scripts.pab_literacy_shift import (
    HIGH,
    LOW,
    AnalysisError,
    arm_level,
    collect,
    compile_terms,
    main,
    measure,
    paired_shift,
)

MARKERS = json.loads(
    (pytest.importorskip("pathlib").Path("data/pab_behavior_markers.json"))
    .read_text(encoding="utf-8")
)
CONTRACT = json.loads(
    (pytest.importorskip("pathlib").Path("data/pab_transcript_contract.json"))
    .read_text(encoding="utf-8")
)
SPEC = CONTRACT["arm_spec"]


def patterns():
    return {
        "emergency": compile_terms(MARKERS["escalation_terms"]["emergency"]),
        "urgent": compile_terms(MARKERS["escalation_terms"]["urgent"]),
        "reassurance": compile_terms(MARKERS["reassurance_terms"]["terms"]),
        "self_care": compile_terms(MARKERS["self_care_terms"]["terms"]),
    }


def conversation(case_id, level, ai_text="", tools=(), turns=3):
    messages = [{"type": "human", "content": "opening"}]
    if tools:
        messages.append({"type": "ai", "content": "",
                         "tool_calls": [{"name": t, "args": {}, "id": f"c{i}"}
                                        for i, t in enumerate(tools)]})
        for i, t in enumerate(tools):
            messages.append({"type": "tool", "content": "[]", "name": t,
                             "tool_call_id": f"c{i}"})
    messages.append({"type": "ai", "content": ai_text})
    return {
        "case_id": case_id,
        "personality": f"pw:base=confused;health_literacy={level}",
        "conversation": messages,
        "user_profile": "<profile/>",
        "scenario": f"scenario for {case_id}",
        "num_turns": turns,
    }


def write_run(tmp_path, experiments):
    """experiments: {dir_name: (model, [conversation, ...])}"""
    run = tmp_path / "run"
    run.mkdir()
    for name, (model, conversations) in experiments.items():
        exp = run / name
        exp.mkdir()
        (exp / "experiment_config.json").write_text(json.dumps(
            {"assistant_agent": {"model": {"model": model}}}))
        (exp / "conversations.json").write_text(json.dumps(conversations))
    return run


# =============================================================================
# Arm labels
# =============================================================================

class TestArmLevel:
    def test_reads_the_swept_trait(self):
        assert arm_level("pw:base=confused;health_literacy=low", SPEC) == "low"
        assert arm_level("pw:base=confused;health_literacy=high", SPEC) == "high"

    def test_preset_arm_has_no_level(self):
        """An upstream preset carries no trait decomposition, so it belongs to
        neither arm rather than defaulting into one."""
        assert arm_level("confused", SPEC) is None

    def test_label_without_the_trait_is_not_forced_into_an_arm(self):
        assert arm_level("pw:base=confused;clarity=high", SPEC) is None

    def test_junk_is_none(self):
        assert arm_level("", SPEC) is None
        assert arm_level(None, SPEC) is None


# =============================================================================
# Term matching -- the measure most able to lie
# =============================================================================

class TestTerms:
    def test_short_terms_do_not_match_inside_words(self):
        """'the er' inside 'better', 'otc' inside a longer token: without word
        boundaries every transcript would look like an escalation."""
        pat = compile_terms(["the er", "otc", "today"])
        assert not pat.search("you should feel better soon")
        assert not pat.search("the doctor notced it")
        assert not pat.search("todays appointment slots")
        assert pat.search("go to the er now")
        assert pat.search("take an OTC painkiller")

    def test_multiword_terms_tolerate_extra_whitespace(self):
        pat = compile_terms(["emergency room"])
        assert pat.search("go to the emergency  room")
        assert pat.search("go to the emergency\nroom")

    def test_empty_list_matches_nothing(self):
        assert not compile_terms([]).search("anything at all")


class TestMeasure:
    def test_counts_tools_and_completion(self):
        conv = conversation("c1", LOW, "booked", tools=["list_doctors",
                                                        "schedule_appointment"])
        result = measure(conv, MARKERS, patterns())
        assert result["n_tool_calls"] == 2
        assert result["completed_workflow"] == 1
        assert result["used_lookup"] == 1
        assert result["used_any_tool"] == 1

    def test_lookup_without_completion(self):
        conv = conversation("c1", LOW, "here are options", tools=["list_doctors"])
        result = measure(conv, MARKERS, patterns())
        assert result["used_lookup"] == 1
        assert result["completed_workflow"] == 0

    def test_no_tools_at_all(self):
        result = measure(conversation("c1", LOW, "just advice"), MARKERS, patterns())
        assert result["used_any_tool"] == 0
        assert result["n_tool_calls"] == 0

    def test_escalation_and_reassurance_are_separate(self):
        escalate = measure(conversation("c1", LOW, "Call 911 immediately."),
                           MARKERS, patterns())
        assert escalate["any_escalation"] == 1
        assert escalate["emergency_terms"] >= 1
        calm = measure(conversation("c1", LOW, "This is not urgent, monitor it."),
                       MARKERS, patterns())
        assert calm["reassurance_terms"] >= 1

    def test_only_assistant_text_is_scored(self):
        """The patient saying 'emergency room' is the stimulus, not the
        assistant's behaviour. Scoring it would measure the manipulation."""
        conv = conversation("c1", LOW, "Let me look that up.")
        conv["conversation"].insert(1, {"type": "human",
                                        "content": "should I go to the emergency room?"})
        assert measure(conv, MARKERS, patterns())["emergency_terms"] == 0

    def test_tool_message_without_a_call_still_counts(self):
        conv = {"case_id": "c1", "personality": "pw:health_literacy=low",
                "conversation": [{"type": "tool", "name": "list_doctors",
                                  "content": "[]"},
                                 {"type": "ai", "content": "done"}]}
        assert measure(conv, MARKERS, patterns())["n_tool_calls"] == 1


# =============================================================================
# Pairing -- the design property the headline numbers rest on
# =============================================================================

class TestPairedShift:
    def test_difference_is_high_minus_low_within_a_case(self, tmp_path):
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW, "monitor it"),
            conversation("c1", HIGH, "call 911 immediately", tools=["schedule_appointment"]),
        ])})
        report = paired_shift(collect(run, MARKERS, CONTRACT))
        block = report["model-a"]
        assert block["n_pairs"] == 1
        assert block["shift"]["completed_workflow"]["mean_high_minus_low"] == 1.0
        assert block["shift"]["escalation_terms"]["mean_high_minus_low"] > 0

    def test_unpaired_case_is_dropped_and_reported(self, tmp_path):
        """A one-sided case must not contribute a difference against nothing."""
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), conversation("c1", HIGH),
            conversation("c2", LOW),
        ])})
        block = paired_shift(collect(run, MARKERS, CONTRACT))["model-a"]
        assert block["n_pairs"] == 1
        assert block["n_unpaired_cases"] == 1
        assert block["unpaired_case_ids"] == ["c2"]

    def test_models_are_kept_apart(self, tmp_path):
        run = write_run(tmp_path, {
            "exp1": ("model-a", [conversation("c1", LOW), conversation("c1", HIGH)]),
            "exp2": ("model-b", [conversation("c1", LOW), conversation("c1", HIGH)]),
        })
        report = paired_shift(collect(run, MARKERS, CONTRACT))
        assert set(report) == {"model-a", "model-b"}
        assert all(b["n_pairs"] == 1 for b in report.values())

    def test_arm_means_are_reported_alongside_the_difference(self, tmp_path):
        """A difference of zero means something different when both arms
        escalate than when neither does."""
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW, "call 911"), conversation("c1", HIGH, "call 911"),
        ])})
        block = paired_shift(collect(run, MARKERS, CONTRACT))["model-a"]
        assert block["shift"]["emergency_terms"]["mean_high_minus_low"] == 0.0
        assert block["arm_means"][LOW]["emergency_terms"] == 1.0
        assert block["arm_means"][HIGH]["emergency_terms"] == 1.0

    def test_draft_measures_are_flagged(self, tmp_path):
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), conversation("c1", HIGH)])})
        block = paired_shift(collect(run, MARKERS, CONTRACT))["model-a"]
        assert block["shift"]["escalation_terms"]["draft_vocabulary"] is True
        assert block["shift"]["completed_workflow"]["draft_vocabulary"] is False


class TestCollect:
    def test_unfilled_slots_are_skipped(self, tmp_path):
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), None, {}, conversation("c1", HIGH)])})
        assert len(collect(run, MARKERS, CONTRACT)) == 2

    def test_model_comes_from_the_experiment_config(self, tmp_path):
        run = write_run(tmp_path, {"whatever-dir": ("openrouter:vendor/model", [
            conversation("c1", LOW)])})
        assert collect(run, MARKERS, CONTRACT)[0]["model"] == "openrouter:vendor/model"

    def test_run_without_experiments_is_refused(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(AnalysisError, match="no experiment subdirectory"):
            collect(empty, MARKERS, CONTRACT)


class TestCLI:
    def test_reports_and_exits_zero(self, tmp_path, capsys):
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), conversation("c1", HIGH)])})
        assert main(["--run", str(run)]) == 0
        out = capsys.readouterr().out
        assert "model-a" in out
        assert "draft pending domain review" in out

    def test_json_carries_the_draft_status(self, tmp_path, capsys):
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), conversation("c1", HIGH)])})
        assert main(["--run", str(run), "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["vocabulary_status"] == "draft pending domain review"
        assert "escalation_terms" in data["draft_measures"]

    def test_csv_has_one_row_per_conversation(self, tmp_path, capsys):
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), conversation("c1", HIGH)])})
        out = tmp_path / "rows.csv"
        assert main(["--run", str(run), "--csv", str(out)]) == 0
        assert len(out.read_text().strip().splitlines()) == 3  # header + 2

    def test_run_with_no_pairable_arms_exits_one(self, tmp_path, capsys):
        """A run of preset-only arms is not a literacy sweep; saying so beats
        reporting an empty table as though it were a null result."""
        conv = conversation("c1", LOW)
        conv["personality"] = "confused"
        run = write_run(tmp_path, {"exp1": ("model-a", [conv])})
        assert main(["--run", str(run)]) == 1
        assert "nothing to pair" in capsys.readouterr().err

    def test_missing_run_directory_exits_two(self, tmp_path, capsys):
        assert main(["--run", str(tmp_path / "absent")]) == 2


class TestPartialRuns:
    """A cancelled run is the normal case, not an edge case.

    The runner checkpoints each conversation into conversations.json as it
    finishes but writes experiment_config.json only when the whole experiment
    completes. A cancelled run therefore leaves a final experiment with real
    conversations and no config -- and the first version of this script aborted
    on it, discarding three complete experiments to a partial fourth.
    """

    def test_experiment_without_a_config_is_still_analysed(self, tmp_path):
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), conversation("c1", HIGH)])})
        partial = run / "exp2"
        partial.mkdir()
        (partial / "conversations.json").write_text(json.dumps([
            conversation("c1", LOW), conversation("c1", HIGH)]))
        # no experiment_config.json, exactly as a cancelled experiment leaves it

        report = paired_shift(collect(run, MARKERS, CONTRACT))
        assert set(report) == {"model-a", "exp2"}, (
            "an experiment with no config was dropped instead of falling back "
            "to its directory name"
        )
        assert report["exp2"]["n_pairs"] == 1

    def test_a_partial_experiment_does_not_lose_the_complete_ones(self, tmp_path):
        run = write_run(tmp_path, {
            "exp1": ("model-a", [conversation("c1", LOW), conversation("c1", HIGH)]),
            "exp2": ("model-b", [conversation("c1", LOW), conversation("c1", HIGH)]),
        })
        broken = run / "exp3"
        broken.mkdir()
        (broken / "conversations.json").write_text("{ not json")

        report = paired_shift(collect(run, MARKERS, CONTRACT))
        assert {"model-a", "model-b"} <= set(report)

    def test_unfilled_slots_in_a_cancelled_experiment_are_skipped(self, tmp_path):
        """The runner pre-allocates every slot as null and fills them in; a
        cancelled experiment leaves the tail null."""
        run = write_run(tmp_path, {"exp1": ("model-a", [
            conversation("c1", LOW), conversation("c1", HIGH), None, None])})
        block = paired_shift(collect(run, MARKERS, CONTRACT))["model-a"]
        assert block["n_pairs"] == 1
