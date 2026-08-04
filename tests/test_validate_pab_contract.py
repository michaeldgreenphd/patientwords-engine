"""Tests for scripts/validate_pab_contract.py - the Layer-2 transcript gate.

scripts/ is not a package, so the module loads via importlib from its file path
(same pattern as test_validate_frontend_contract.py). The clean run lives in
tests/fixtures/pab_run/ and is committed; each test copies it to tmp_path, seeds
one contract break, and asserts the validator names it. Abstract vocabulary
only - no medical terms, and nothing here imports PatientAgentBench.
"""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "scripts" / "validate_pab_contract.py"
_SPEC = importlib.util.spec_from_file_location("validate_pab_contract", _MODULE_PATH)
vpc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vpc)

FIXTURE = _ROOT / "tests" / "fixtures" / "pab_run"
CONTRACT = _ROOT / "data" / "pab_transcript_contract.json"
EXP = "0_0"


@pytest.fixture
def run(tmp_path):
    """A writable copy of the committed clean run."""
    dest = tmp_path / "run"
    shutil.copytree(FIXTURE, dest)
    return dest


def read(run: Path, name: str, exp: str = EXP):
    path = run / exp / name if exp else run / name
    return json.loads(path.read_text(encoding="utf-8"))


def write(run: Path, name: str, data, exp: str = EXP):
    path = run / exp / name if exp else run / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def check(run: Path, strict: bool = False):
    return vpc.validate(run, CONTRACT, strict=strict)


def messages(rep):
    return " | ".join(rep.errors + rep.warnings)


class TestCleanRun:
    def test_committed_fixture_passes(self, run):
        rep, summary = check(run)
        assert rep.errors == []
        assert rep.warnings == []
        exp = summary["experiments"][EXP]
        assert exp["n_conversations"] == 6
        assert exp["n_scored"] == 6
        assert exp["n_pairs"] == 2
        assert exp["complete_pairs"] == 2
        assert exp["varying_traits"] == ["health_literacy"]
        assert exp["identified"] is True

    def test_cli_exits_zero(self, run, capsys):
        assert vpc.main(["--run", str(run)]) == 0
        assert "0 error(s), 0 warning(s)" in capsys.readouterr().out

    def test_cli_json_mode(self, run, capsys):
        assert vpc.main(["--run", str(run), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["errors"] == []
        assert payload["summary"]["experiments"][EXP]["identified"] is True

    def test_missing_run_directory_exits_two(self, tmp_path):
        assert vpc.main(["--run", str(tmp_path / "nope")]) == 2


class TestShape:
    def test_missing_required_conversation_key(self, run):
        data = read(run, "conversations.json")
        del data[0]["num_turns"]
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("num_turns" in e and "missing required key" in e for e in rep.errors)

    def test_wrong_type_on_a_conversation_key(self, run):
        data = read(run, "conversations.json")
        data[0]["num_turns"] = "two"
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("num_turns" in e and "wrong type" in e for e in rep.errors)

    def test_duplicate_case_id(self, run):
        data = read(run, "conversations.json")
        data[1]["case_id"] = data[0]["case_id"]
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("duplicate case_id" in e for e in rep.errors)

    def test_unknown_message_type(self, run):
        data = read(run, "conversations.json")
        data[0]["conversation"][0]["type"] = "narrator"
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("unknown message type" in e for e in rep.errors)

    def test_message_without_content(self, run):
        data = read(run, "conversations.json")
        del data[0]["conversation"][1]["content"]
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("content" in e and "missing" in e for e in rep.errors)

    def test_conversation_with_no_patient_turn_warns(self, run):
        data = read(run, "conversations.json")
        data[0]["conversation"] = [
            m for m in data[0]["conversation"] if m["type"] != "human"
        ]
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("no patient turn" in w for w in rep.warnings)

    def test_null_slots_warn_as_incomplete(self, run):
        """A resumable run legitimately carries empty slots in both files. The
        positional join must stay aligned on the file's own indices, not on the
        filtered records - otherwise every slot after the first gap reports a
        spurious case_id mismatch."""
        data = read(run, "conversations.json")
        data[0] = None
        evals = read(run, "evaluations.json")
        evals[0] = {}
        write(run, "conversations.json", data)
        write(run, "evaluations.json", evals)
        rep, summary = check(run)
        assert not any("does not match conversations" in e for e in rep.errors)
        assert not any("slot-for-slot join broken" in e for e in rep.errors)
        assert any("run incomplete" in w for w in rep.warnings)
        assert any("not yet evaluated" in w for w in rep.warnings)
        assert summary["experiments"][EXP]["n_conversations"] == 5
        # The gap does leave one case short of an arm, and that is reported --
        # the point is that it is reported once, not once per following slot.
        assert [e for e in rep.errors if "absent from arm" in e] == rep.errors

    def test_failed_conversation_does_not_shift_the_evaluation_join(self, run):
        data = read(run, "conversations.json")
        data[1]["error"] = "assistant agent failed"
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert not any("does not match conversations" in e for e in rep.errors)
        assert not any("slot-for-slot join broken" in e for e in rep.errors)
        assert any("excluded" in w for w in rep.warnings)

    def test_empty_conversations_file(self, run):
        write(run, "conversations.json", [])
        rep, _ = check(run)
        assert any("empty" in e for e in rep.errors)

    def test_no_experiment_directory(self, run):
        shutil.rmtree(run / EXP)
        rep, _ = check(run)
        assert any("no experiment subdirectory" in e for e in rep.errors)


class TestEvaluationJoin:
    def test_length_mismatch_breaks_the_slot_join(self, run):
        data = read(run, "evaluations.json")
        write(run, "evaluations.json", data[:-1])
        rep, _ = check(run)
        assert any("slot-for-slot join broken" in e for e in rep.errors)

    def test_case_id_mismatch_at_a_slot(self, run):
        data = read(run, "evaluations.json")
        data[2]["case_id"] = "case-elsewhere"
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert any("does not match conversations[2]" in e for e in rep.errors)

    def test_missing_evaluation_block(self, run):
        data = read(run, "evaluations.json")
        del data[0]["evaluation"]
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert any("evaluation" in e and "missing required key" in e for e in rep.errors)

    def test_score_outside_the_scale(self, run):
        data = read(run, "evaluations.json")
        data[0]["evaluation"]["rubric_scores"]["triage_quality"] = 7
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert any("outside the 1-5 scale" in e for e in rep.errors)

    def test_non_numeric_score(self, run):
        data = read(run, "evaluations.json")
        data[0]["evaluation"]["rubric_scores"]["triage_quality"] = "good"
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert any("non-numeric score" in e for e in rep.errors)

    def test_missing_required_rubric_is_an_error(self, run):
        data = read(run, "evaluations.json")
        del data[0]["evaluation"]["rubric_scores"]["triage_quality"]
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert any("missing required rubric" in e for e in rep.errors)

    def test_missing_secondary_rubric_is_a_warning(self, run):
        data = read(run, "evaluations.json")
        del data[0]["evaluation"]["rubric_scores"]["conversational_quality"]
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert rep.errors == []
        assert any("missing rubric" in w for w in rep.warnings)

    def test_failed_evaluation_is_excluded_with_a_warning(self, run):
        data = read(run, "evaluations.json")
        data[0]["evaluation"] = {"error": "All evaluators failed"}
        write(run, "evaluations.json", data)
        rep, summary = check(run)
        assert rep.errors == []
        assert any("excluded" in w for w in rep.warnings)
        assert summary["experiments"][EXP]["n_scored"] == 5

    def test_single_evaluator_warns_about_the_jury(self, run):
        data = read(run, "evaluations.json")
        for entry in data:
            del entry["evaluation_1"]
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert any("single evaluator" in w for w in rep.warnings)

    def test_pending_slots_warn(self, run):
        data = read(run, "evaluations.json")
        data[0] = {}
        write(run, "evaluations.json", data)
        rep, _ = check(run)
        assert any("not yet evaluated" in w for w in rep.warnings)


class TestArmLabels:
    def test_unparseable_arm_label(self, run):
        data = read(run, "conversations.json")
        data[0]["personality"] = "pw:health_literacy"
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("unparseable arm label" in e for e in rep.errors)

    def test_preset_labels_parse_but_are_not_decomposable(self):
        spec = json.loads(CONTRACT.read_text(encoding="utf-8"))["arm_spec"]
        base, overrides = vpc.parse_arm("confused", spec)
        assert base == "confused"
        assert overrides is None

    def test_free_trait_label_decomposes(self):
        spec = json.loads(CONTRACT.read_text(encoding="utf-8"))["arm_spec"]
        base, overrides = vpc.parse_arm("pw:base=confused;clarity=high", spec)
        assert base == "confused"
        assert overrides == {"clarity": "high"}

    def test_absent_trait_takes_the_neutral_level(self):
        """An arm that does not name a trait inherits the base level, so
        `pw:clarity=high` and `pw:clarity=high;health_literacy=medium` must not
        register as differing on health_literacy."""
        spec = json.loads(CONTRACT.read_text(encoding="utf-8"))["arm_spec"]
        arms = [vpc.parse_arm(label, spec) for label in
                ("pw:clarity=high", "pw:clarity=high;health_literacy=medium")]
        assert vpc.varying_traits(arms, spec) == []

    def test_preset_run_skips_the_identification_check(self, run):
        data = read(run, "conversations.json")
        for i, entry in enumerate(data):
            entry["personality"] = ["confused", "skeptical", "stoic"][i % 3]
        write(run, "conversations.json", data)
        evals = read(run, "evaluations.json")
        for i, entry in enumerate(evals):
            entry["personality"] = data[i]["personality"]
        write(run, "evaluations.json", evals)
        rep, summary = check(run)
        assert rep.errors == []
        assert any("not checkable from preset labels" in w for w in rep.warnings)
        assert summary["experiments"][EXP]["identified"] is None


class TestDesignIntegrity:
    def test_two_traits_varying_is_not_identified(self, run):
        """The check the whole layer exists for: a second trait moving with the
        swept one makes the contrast uninterpretable, and nothing downstream
        would notice."""
        data = read(run, "conversations.json")
        for entry in data:
            if entry["personality"] == "pw:health_literacy=low":
                entry["personality"] = "pw:health_literacy=low;clarity=low"
        write(run, "conversations.json", data)
        rep, summary = check(run)
        assert any("not identified" in e for e in rep.errors)
        assert summary["experiments"][EXP]["identified"] is False
        assert sorted(summary["experiments"][EXP]["varying_traits"]) == [
            "clarity", "health_literacy"
        ]

    def test_mixed_bases_are_rejected(self, run):
        data = read(run, "conversations.json")
        for entry in data:
            if entry["personality"] == "pw:health_literacy=high":
                entry["personality"] = "pw:base=confused;health_literacy=high"
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("different bases" in e for e in rep.errors)

    def test_empty_manipulation_is_rejected(self, run):
        """Two arm labels that differ as strings but resolve to the same traits
        - a config that looks like a sweep and measures nothing."""
        data = read(run, "conversations.json")
        for i, entry in enumerate(data):
            entry["personality"] = (
                "pw:health_literacy=low" if i % 2
                else "pw:base=neutral;health_literacy=low"
            )
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("manipulation is empty" in e for e in rep.errors)

    def test_case_missing_from_an_arm_breaks_the_pairing(self, run):
        data = read(run, "conversations.json")
        dropped = data.pop(0)
        write(run, "conversations.json", data)
        evals = [e for e in read(run, "evaluations.json") if e["case_id"] != dropped["case_id"]]
        write(run, "evaluations.json", evals)
        rep, summary = check(run)
        assert any("absent from arm" in e for e in rep.errors)
        assert summary["experiments"][EXP]["complete_pairs"] == 1

    def test_duplicate_arm_within_a_pair(self, run):
        data = read(run, "conversations.json")
        extra = dict(data[0])
        extra["case_id"] = "case-alpha-0-repeat"
        data.append(extra)
        write(run, "conversations.json", data)
        evals = read(run, "evaluations.json")
        evals.append({**evals[0], "case_id": extra["case_id"]})
        write(run, "evaluations.json", evals)
        rep, _ = check(run)
        assert any("more than once in arm" in e for e in rep.errors)

    def test_stimulus_attribute_differing_across_arms_is_a_confound(self, run):
        cases = read(run, "benchmark_cases.json", exp="")
        cases[0]["severity_level"] = "severe"
        write(run, "benchmark_cases.json", cases, exp="")
        rep, _ = check(run)
        assert any("severity_level" in e and "not the same clinical case" in e
                   for e in rep.errors)

    def test_absent_benchmark_cases_warns_that_the_check_is_skipped(self, run):
        (run / "benchmark_cases.json").unlink()
        rep, _ = check(run)
        assert rep.errors == []
        assert any("stimulus attributes not checked" in w for w in rep.warnings)

    def test_single_arm_run_has_no_contrast(self, run):
        data = read(run, "conversations.json")
        for entry in data:
            entry["personality"] = "pw:health_literacy=low"
        write(run, "conversations.json", data)
        rep, _ = check(run)
        assert any("no contrast to identify" in w for w in rep.warnings)


class TestMultiExperiment:
    def test_case_sets_must_match_across_experiments(self, run):
        second = run / "0_1"
        shutil.copytree(run / EXP, second)
        data = read(run, "conversations.json", exp="0_1")
        data = data[:-1]
        write(run, "conversations.json", data, exp="0_1")
        evals = read(run, "evaluations.json", exp="0_1")[:-1]
        write(run, "evaluations.json", evals, exp="0_1")
        rep, summary = check(run)
        assert any("case set differs" in w for w in rep.warnings)
        assert set(summary["experiments"]) == {"0_0", "0_1"}

    def test_identical_experiments_are_clean(self, run):
        shutil.copytree(run / EXP, run / "0_1")
        rep, summary = check(run)
        assert rep.errors == []
        assert set(summary["experiments"]) == {"0_0", "0_1"}


class TestStrictMode:
    def test_strict_promotes_warnings_to_errors(self, run):
        (run / "benchmark_cases.json").unlink()
        rep, _ = check(run, strict=True)
        assert rep.warnings == []
        assert any("stimulus attributes not checked" in e for e in rep.errors)


class TestPairKey:
    def test_pair_key_ignores_the_arm_label(self):
        fields = ["scenario", "user_profile"]
        a = {"scenario": "S", "user_profile": "P", "personality": "pw:x=low"}
        b = {"scenario": "S", "user_profile": "P", "personality": "pw:x=high"}
        assert vpc.pair_key(a, fields) == vpc.pair_key(b, fields)

    def test_pair_key_separates_different_cases(self):
        fields = ["scenario", "user_profile"]
        a = {"scenario": "S1", "user_profile": "P"}
        b = {"scenario": "S2", "user_profile": "P"}
        assert vpc.pair_key(a, fields) != vpc.pair_key(b, fields)

    def test_pair_key_does_not_leak_case_text(self):
        key = vpc.pair_key({"scenario": "sensitive text", "user_profile": ""},
                           ["scenario", "user_profile"])
        assert "sensitive" not in key
        assert len(key) == 12
