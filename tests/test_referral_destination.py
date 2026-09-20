"""Tests for scripts/referral_destination.py.

The behaviours worth pinning are the ones that would otherwise produce a plausible wrong
number: a vocabulary that silently scores zero, a row dropped without being counted, an
out-of-scope row dragging the coverage rate down, and the tier-identical stratum failing to
actually hold the tier fixed.
"""

import json

import pytest

from scripts import referral_destination as rd


def _vocab_file(tmp_path, specialist=None, emergency=None):
    body = {
        "status": "test",
        "version": "test",
        "method_note": "test note",
        "specialist_services": specialist if specialist is not None else ["cardiolog", "specialist"],
        "emergency_services": emergency if emergency is not None else ["emergency room"],
    }
    path = tmp_path / "vocab.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


def _corpus(tmp_path, rows):
    """rows: (stimulus, model, arm, tier, text, judge). Writes the two JSONL families the
    script reads and returns the directory."""
    advice = tmp_path / "advice"
    advice.mkdir()
    responses, judgments = [], []
    for i, (stimulus, model, arm, tier, text, judge) in enumerate(rows):
        sha = f"sha{i:03d}"
        if text is not None:
            responses.append({"response_sha256": sha, "response_text": text})
        judgments.append({
            "response_sha256": sha, "stimulus_id": stimulus, "model": model,
            "arm": arm, "tier": tier, "judge_model": judge,
        })
    (advice / "responses_stimuli_x.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in responses), encoding="utf-8")
    (advice / "judgments_stimuli_x.jsonl").write_text(
        "".join(json.dumps(j) + "\n" for j in judgments), encoding="utf-8")
    return str(advice)


def test_an_empty_vocabulary_is_refused_rather_than_scoring_zero(tmp_path):
    """A term list that fails to load would make every reply score false and the difference
    come out at exactly zero — a clean-looking null that is really a missing file."""
    path = _vocab_file(tmp_path, specialist=[])
    with pytest.raises(ValueError, match="non-empty"):
        rd.load_vocab(path)


def test_rows_from_another_judge_do_not_count_against_coverage(tmp_path):
    """The secondary judge's rows are out of scope, not extraction failures. Folding them into
    the skip count would put coverage near 0.64 and hide a real problem behind the noise."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "secondary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "secondary"),
    ])
    bundle = rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))
    cov = bundle["coverage"]
    assert cov["rows_from_other_judges_out_of_scope"] == 2
    assert cov["judge_of_record_rows_considered"] == 2
    assert cov["coverage_rate"] == 1.0
    assert cov["unmeasurable_by_reason"] == {}


def test_a_judgment_with_no_response_record_is_counted_not_dropped(tmp_path):
    """AGENTS.md: missing data is recorded as such, never silently skipped."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s2", "m1", "clinical", "routine", None, "primary"),
    ])
    bundle = rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))
    reasons = bundle["coverage"]["unmeasurable_by_reason"]
    assert reasons.get("no_response_record_for_this_judgment") == 1
    assert bundle["coverage"]["judge_of_record_rows_considered"] == 3
    assert bundle["coverage"]["judge_of_record_rows_measured"] == 2


def test_an_unrecognised_tier_is_named_rather_than_ranked_as_zero(tmp_path):
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s2", "m1", "clinical", "not_applicable", "no advice", "primary"),
    ])
    bundle = rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))
    assert bundle["coverage"]["unmeasurable_by_reason"].get("tier_absent_or_unrecognised") == 1


def test_the_tier_identical_stratum_drops_cells_whose_arms_differ_on_tier(tmp_path):
    """The whole point of the stratum: a destination difference inside it cannot be a
    restatement of an urgency difference. One cell agrees on tier, one does not."""
    advice = _corpus(tmp_path, [
        ("same", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("same", "m1", "patient", "routine", "see your doctor", "primary"),
        ("diff", "m1", "clinical", "urgent", "see a cardiologist", "primary"),
        ("diff", "m1", "patient", "self_care", "see your doctor", "primary"),
    ])
    bundle = rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))
    spec = bundle["readouts"]["names_specialist_service"]
    assert spec["all_cells"]["cells"] == 2
    assert spec["tier_identical_cells"]["cells"] == 1


def test_the_specialist_difference_has_the_sign_the_construct_predicts(tmp_path):
    """Clinical names a specialist, patient does not, so patient-minus-clinical is negative."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    bundle = rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))
    assert bundle["readouts"]["names_specialist_service"]["all_cells"]["patient_minus_clinical"] == -1.0


def test_the_colloquial_arm_name_is_accepted_as_the_patient_side(tmp_path):
    """The petri lane calls it `colloquial`; the advice lane calls it `patient`. Both must
    pair against `clinical` or a whole family of rows silently contributes nothing."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "colloquial", "routine", "see your doctor", "primary"),
    ])
    bundle = rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))
    assert bundle["readouts"]["names_specialist_service"]["all_cells"]["cells"] == 1


def test_an_empty_comparable_set_refuses_rather_than_reporting_a_number(tmp_path):
    """Only a clinical arm exists, so nothing is comparable. Reporting 0.0 here would be a
    fabricated null."""
    advice = _corpus(tmp_path, [("s1", "m1", "clinical", "routine", "see a cardiologist", "primary")])
    with pytest.raises(ValueError, match="no comparable cells"):
        rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))


def test_the_seed_is_recorded_and_the_run_is_reproducible(tmp_path):
    """A seed that exists only in the invocation is not reproducible by whoever reads the
    JSON later (AGENTS.md, Coding constraints)."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s2", "m2", "clinical", "urgent", "see a specialist", "primary"),
        ("s2", "m2", "patient", "urgent", "rest at home", "primary"),
    ])
    vocab = _vocab_file(tmp_path)
    first = rd.analyze(advice, judge="primary", boot=200, seed=7, vocab_path=vocab)
    second = rd.analyze(advice, judge="primary", boot=200, seed=7, vocab_path=vocab)
    assert first["seed"] == 7
    assert first["readouts"] == second["readouts"]
    other = rd.analyze(advice, judge="primary", boot=200, seed=8, vocab_path=vocab)
    assert other["seed"] == 8


def test_the_vocabulary_status_rides_the_output(tmp_path):
    """The term list is draft; a bundle that does not say so invites its numbers being quoted
    as if the vocabulary were reviewed."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    bundle = rd.analyze(advice, judge="primary", boot=50, seed=7, vocab_path=_vocab_file(tmp_path))
    assert bundle["vocabulary"]["status"] == "test"
    assert bundle["limitation"] == "test note"
