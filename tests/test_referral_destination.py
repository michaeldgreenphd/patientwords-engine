"""Tests for scripts/referral_destination.py.

The behaviours worth pinning are the ones that would otherwise produce a plausible wrong
number: a vocabulary that silently scores zero, a row dropped without being counted, an
out-of-scope row dragging the coverage rate down, and the tier-identical stratum failing to
actually hold the modal tier fixed.
"""

import json

import pytest

from scripts import referral_destination as rd
from scripts.advice_eval import canonical_json, sha256_text


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


TEST_TIERS = ["self_care", "routine", "urgent", "emergency"]


def _rubric_file(tmp_path, tiers=None, name="rubric.json", version="test"):
    """A rubric file and its canonical digest, computed the way advice_eval's judge stamps it."""
    rubric = {"version": version, "tiers": [{"id": t} for t in (tiers or TEST_TIERS)]}
    path = tmp_path / name
    path.write_text(json.dumps(rubric), encoding="utf-8")
    return str(path), sha256_text(canonical_json(rubric))


def _corpus(tmp_path, rows):
    """rows: (stimulus, model, arm, tier, text, judge[, rubric digest]). Writes the two JSONL
    families the script reads and returns the directory. A row without a seventh member carries
    the digest of the default test rubric; a seventh member of None omits the field."""
    advice = tmp_path / "advice"
    advice.mkdir()
    _, default_digest = _rubric_file(tmp_path)
    responses, judgments = [], []
    for i, row in enumerate(rows):
        stimulus, model, arm, tier, text, judge = row[:6]
        digest = row[6] if len(row) > 6 else default_digest
        sha = f"sha{i:03d}"
        if text is not None:
            responses.append({"response_sha256": sha, "response_text": text})
        judgment = {
            "response_sha256": sha, "stimulus_id": stimulus, "model": model,
            "arm": arm, "tier": tier, "judge_model": judge,
        }
        if digest is not None:
            judgment["rubric_sha256"] = digest
        judgments.append(judgment)
    (advice / "responses_stimuli_x.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in responses), encoding="utf-8")
    (advice / "judgments_stimuli_x.jsonl").write_text(
        "".join(json.dumps(j) + "\n" for j in judgments), encoding="utf-8")
    return str(advice)


def _analyze(tmp_path, advice, **kwargs):
    kwargs.setdefault("judge", "primary")
    kwargs.setdefault("boot", 50)
    kwargs.setdefault("seed", 7)
    kwargs.setdefault("rubric_path", str(tmp_path / "rubric.json"))
    return rd.analyze(advice, **kwargs)


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
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
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
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    reasons = bundle["coverage"]["unmeasurable_by_reason"]
    assert reasons.get("no_response_record_for_this_judgment") == 1
    assert bundle["coverage"]["judge_of_record_rows_considered"] == 3
    assert bundle["coverage"]["judge_of_record_rows_measured"] == 2


def test_a_cell_missing_an_arm_is_listed_and_its_rows_accounted_for(tmp_path):
    """Codex, PR #29: a cell with one arm was dropped from every estimate by a bare `continue`
    while its rows still counted as measured (advnat_20260728T144020Z#27 with one model in the
    committed corpus). The cell is now named, and every measured row is either in the contrast
    or outside it under a reason, so the two counts add up to the rows measured."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s1", "m1", "translated", "routine", "see a cardiologist", "primary"),
        ("s2", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s2", "m1", "clinical", "urgent", "see a cardiologist", "primary"),
        ("s2", "m1", "translated", "routine", "see a cardiologist", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    cov = bundle["coverage"]
    assert cov["cells_with_both_arms"] == 1
    assert cov["cells_missing_an_arm"] == [
        {"stimulus_id": "s2", "model": "m1", "arms_present": ["clinical", "translated"], "rows": 3}]
    assert cov["measured_rows_outside_the_contrast"] == {
        "arm_not_compared:translated": 1, "cell_lacks_the_patient_or_clinical_arm": 3}
    assert cov["judge_of_record_rows_in_the_contrast"] == 2
    assert (cov["judge_of_record_rows_in_the_contrast"] + sum(cov["measured_rows_outside_the_contrast"].values())
            == cov["judge_of_record_rows_measured"] == 6)
    assert "cell missing an arm: s2 / m1" in rd.format_summary(bundle)


def test_an_unrecognised_tier_is_named_rather_than_ranked_as_zero(tmp_path):
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s2", "m1", "clinical", "not_applicable", "no advice", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    assert bundle["coverage"]["unmeasurable_by_reason"].get("tier_absent_or_unrecognised") == 1


def test_the_tier_identical_stratum_drops_cells_whose_arms_differ_on_tier(tmp_path):
    """The stratum holds the modal tier fixed, so a destination difference inside it is not a
    difference in modal tier. One cell agrees on tier, one does not."""
    advice = _corpus(tmp_path, [
        ("same", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("same", "m1", "patient", "routine", "see your doctor", "primary"),
        ("diff", "m1", "clinical", "urgent", "see a cardiologist", "primary"),
        ("diff", "m1", "patient", "self_care", "see your doctor", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    spec = bundle["readouts"]["names_specialist_service"]
    assert spec["all_cells"]["cells"] == 2
    assert spec["tier_identical_cells"]["cells"] == 1


def test_the_tier_identical_stratum_compares_modal_tiers_not_rounded_mean_ranks(tmp_path):
    """Codex, PR #29: a rounded mean held two arms equal whose modal tiers differ (18 such cells in
    the committed corpus). Here both arms have mean rank 1.33, which rounds to 1, but the patient
    arm's mode is routine and the clinical arm's three-way tie breaks to the most urgent, urgent.
    A second cell has a two-way tie on the patient side that breaks to the clinical side's tier,
    so it stays in."""
    advice = _corpus(tmp_path, [
        ("differ", "m1", "patient", "routine", "see your doctor", "primary"),
        ("differ", "m1", "patient", "routine", "see your doctor", "primary"),
        ("differ", "m1", "patient", "urgent", "see your doctor", "primary"),
        ("differ", "m1", "clinical", "self_care", "see a cardiologist", "primary"),
        ("differ", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("differ", "m1", "clinical", "emergency", "see a cardiologist", "primary"),
        ("tie", "m1", "patient", "routine", "see your doctor", "primary"),
        ("tie", "m1", "patient", "urgent", "see your doctor", "primary"),
        ("tie", "m1", "clinical", "urgent", "see a cardiologist", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    spec = bundle["readouts"]["names_specialist_service"]
    assert spec["all_cells"]["cells"] == 2
    assert spec["tier_identical_cells"]["cells"] == 1


def test_the_modal_stratum_reports_the_mean_rank_gaps_it_admits_and_a_stratum_without_them(tmp_path):
    """Codex, PR #29, and its re-review: the modal tier holds the registered summary fixed, not
    the mean tier rank (184 of the 693 modal-equal cells in the committed corpus differ in mean
    rank). `gap` shares mode routine (patient 1,1,2 against clinical 0,1,1) with means 2/3 of a rank
    apart, so it stays in the tier-identical stratum but leaves the sensitivity stratum; `same`
    has identical ranks and stays in both; `differ` leaves both. The bundle counts the gap and says
    in its method text what the modal stratum does not hold fixed."""
    advice = _corpus(tmp_path, [
        ("gap", "m1", "patient", "routine", "see your doctor", "primary"),
        ("gap", "m1", "patient", "routine", "see your doctor", "primary"),
        ("gap", "m1", "patient", "urgent", "see your doctor", "primary"),
        ("gap", "m1", "clinical", "self_care", "see a cardiologist", "primary"),
        ("gap", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("gap", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("same", "m1", "patient", "routine", "see a cardiologist", "primary"),
        ("same", "m1", "clinical", "routine", "see your doctor", "primary"),
        ("differ", "m1", "patient", "self_care", "see your doctor", "primary"),
        ("differ", "m1", "clinical", "urgent", "see a cardiologist", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    spec = bundle["readouts"]["names_specialist_service"]
    assert list(spec) == ["all_cells", "tier_identical_cells", "tier_and_mean_rank_identical_cells"]
    assert [spec[s]["cells"] for s in spec] == [3, 2, 1]
    assert spec["tier_and_mean_rank_identical_cells"]["patient_minus_clinical"] == 1.0
    assert bundle["tier_matching"] == {
        "modal_tier_equal_cells": 2,
        "of_which_mean_rank_unequal": 1,
        "of_which_mean_rank_gap_at_least_half_a_rank": 1,
        "largest_mean_rank_gap": 0.666667,
    }
    assert "not the mean tier rank" in bundle["method"]["tier_identical_stratum"]
    assert "sensitivity" in bundle["method"]["tier_and_mean_rank_identical_stratum"]
    summary = rd.format_summary(bundle)
    assert "2 cells share the modal tier; of those 1 differ in mean tier rank" in summary
    assert "tier_and_mean_rank_identical_cells" in summary


def test_an_empty_sensitivity_stratum_is_named_not_estimated_rather_than_refusing_the_run(tmp_path):
    """The only modal-equal cell has unequal mean ranks, so the sensitivity stratum is empty. The
    registered strata still have estimates, so the run records the empty stratum by name instead of
    refusing, and never reports a number for it."""
    advice = _corpus(tmp_path, [
        ("tie", "m1", "patient", "routine", "see your doctor", "primary"),
        ("tie", "m1", "patient", "urgent", "see your doctor", "primary"),
        ("tie", "m1", "clinical", "urgent", "see a cardiologist", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    spec = bundle["readouts"]["names_specialist_service"]
    assert spec["tier_identical_cells"]["cells"] == 1
    assert spec["tier_and_mean_rank_identical_cells"] == {
        "cells": 0, "stimuli": 0, "models": 0, "not_estimated": "no comparable cells in this stratum"}
    assert "tier_and_mean_rank_identical_cells" in rd.format_summary(bundle)
    with pytest.raises(ValueError, match="unknown stratum"):
        rd.in_stratum("rounded_mean", [1], [1])


def test_modal_rank_is_the_registered_per_cell_summary():
    """The stratum must use the advice arm's registered estimator, most-urgent tie-break included,
    so it is checked against advice_eval._modal_tier over every multiset of up to four tiers."""
    from itertools import combinations_with_replacement

    from scripts.advice_eval import _modal_tier

    for size in range(1, 5):
        for ranks in combinations_with_replacement(range(len(TEST_TIERS)), size):
            names = [TEST_TIERS[r] for r in ranks]
            rank = {tier: i for i, tier in enumerate(TEST_TIERS)}
            assert TEST_TIERS[rd.modal_rank(list(ranks))] == _modal_tier(names, rank)


def test_the_specialist_difference_has_the_sign_the_construct_predicts(tmp_path):
    """Clinical names a specialist, patient does not, so patient-minus-clinical is negative."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    assert bundle["readouts"]["names_specialist_service"]["all_cells"]["patient_minus_clinical"] == -1.0


def test_a_model_at_zero_is_tied_not_agreeing_even_through_float_noise(tmp_path):
    """Codex, PR #29: a Boolean sign test counted a model at exactly zero as agreeing with any
    non-negative estimate. `zero` has identical arms. `noise` has two cells that cancel exactly
    (-1/3 and +1/3) but whose float mean is +2.8e-17, the same artefact that put a model at
    -5.6e-18 in the committed corpus and counted it as negative. Only `pos` agrees."""
    advice = _corpus(tmp_path, [
        ("s1", "pos", "patient", "routine", "see a cardiologist", "primary"),
        ("s1", "pos", "clinical", "routine", "see your doctor", "primary"),
        ("s2", "zero", "patient", "routine", "see your doctor", "primary"),
        ("s2", "zero", "clinical", "routine", "see your doctor", "primary"),
        ("s3", "noise", "patient", "routine", "see your doctor", "primary"),
        ("s3", "noise", "clinical", "routine", "see a cardiologist", "primary"),
        ("s3", "noise", "clinical", "routine", "see your doctor", "primary"),
        ("s3", "noise", "clinical", "routine", "see your doctor", "primary"),
        ("s4", "noise", "patient", "routine", "see a cardiologist", "primary"),
        ("s4", "noise", "clinical", "routine", "see a cardiologist", "primary"),
        ("s4", "noise", "clinical", "routine", "see a cardiologist", "primary"),
        ("s4", "noise", "clinical", "routine", "see your doctor", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    res = bundle["readouts"]["names_specialist_service"]["all_cells"]
    assert res["patient_minus_clinical"] > 0
    assert res["models_agreeing_in_sign"] == 1
    assert res["models_opposing_sign"] == 0
    assert res["models_tied_at_zero"] == 2
    assert res["models_by_sign"] == {"negative": 0, "zero": 2, "positive": 1}
    assert res["per_model"]["noise"] == 0.0
    assert "1/1 non-tied models agree in sign (2 tied at zero)" in rd.format_summary(bundle)


def test_an_estimate_of_exactly_zero_has_no_direction_to_agree_with(tmp_path):
    advice = _corpus(tmp_path, [
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s1", "m1", "clinical", "routine", "see your doctor", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    res = bundle["readouts"]["names_specialist_service"]["all_cells"]
    assert res["models_agreeing_in_sign"] is None and res["models_opposing_sign"] is None
    assert res["models_tied_at_zero"] == 1


def test_the_colloquial_arm_name_is_accepted_as_the_patient_side(tmp_path):
    """The petri lane calls it `colloquial`; the advice lane calls it `patient`. Both must
    pair against `clinical` or a whole family of rows silently contributes nothing."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "colloquial", "routine", "see your doctor", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    assert bundle["readouts"]["names_specialist_service"]["all_cells"]["cells"] == 1


def test_an_empty_comparable_set_refuses_rather_than_reporting_a_number(tmp_path):
    """Only a clinical arm exists, so nothing is comparable. Reporting 0.0 here would be a
    fabricated null."""
    advice = _corpus(tmp_path, [("s1", "m1", "clinical", "routine", "see a cardiologist", "primary")])
    with pytest.raises(ValueError, match="no comparable cells"):
        _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))


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
    first = _analyze(tmp_path, advice, boot=200, seed=7, vocab_path=vocab)
    second = _analyze(tmp_path, advice, boot=200, seed=7, vocab_path=vocab)
    assert first["seed"] == 7
    assert first["readouts"] == second["readouts"]
    other = _analyze(tmp_path, advice, boot=200, seed=8, vocab_path=vocab)
    assert other["seed"] == 8


def test_the_vocabulary_status_rides_the_output(tmp_path):
    """The term list is draft; a bundle that does not say so invites its numbers being quoted
    as if the vocabulary were reviewed."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    assert bundle["vocabulary"]["status"] == "test"
    assert bundle["limitation"] == "test note"


def _two_rubric_corpus(tmp_path):
    """The same responses judged by the same judge under rubric A and again under rubric B, which
    is what a rubric revision followed by a re-judge leaves in the append-only archive. Rubric B
    splits s1's arms by two tiers; s2 agrees under both, so the tier-identical stratum is never
    empty."""
    _, digest_b = _rubric_file(tmp_path, name="rubric_b.json", version="b")
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s2", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s2", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s1", "m1", "clinical", "urgent", "see a cardiologist", "primary", digest_b),
        ("s1", "m1", "patient", "self_care", "see your doctor", "primary", digest_b),
        ("s2", "m1", "clinical", "routine", "see a cardiologist", "primary", digest_b),
        ("s2", "m1", "patient", "routine", "see your doctor", "primary", digest_b),
    ])
    return advice, digest_b


def test_two_rubric_digests_from_the_judge_of_record_are_refused_not_pooled(tmp_path):
    """Codex, PR #29: filtering on the judge alone pooled every rubric that judge was run under,
    mixing classifications and counting each re-judged response twice."""
    advice, _ = _two_rubric_corpus(tmp_path)
    with pytest.raises(ValueError, match=r"2 rubric digests .*\(4 rows\).*--rubric-digest"):
        _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))


def test_a_declared_rubric_digest_selects_its_rows_and_reports_the_rest(tmp_path):
    advice, digest_b = _two_rubric_corpus(tmp_path)
    _, digest_a = _rubric_file(tmp_path)
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path), rubric_digest=digest_a[:12])
    cov = bundle["coverage"]
    assert bundle["rubric"]["sha256"] == digest_a
    assert bundle["rubric"]["tier_order_least_to_most_urgent"] == TEST_TIERS
    assert cov["judge_of_record_rows_under_other_rubric_digests_out_of_scope"] == 4
    assert cov["judge_of_record_rows_considered"] == cov["judge_of_record_rows_measured"] == 4
    assert bundle["urgency_tier_for_comparison"]["all_cells"]["patient_minus_clinical_tier_ranks"] == 0.0

    rubric_b = str(tmp_path / "rubric_b.json")
    other = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path), rubric_digest=digest_b, rubric_path=rubric_b)
    assert other["urgency_tier_for_comparison"]["all_cells"]["patient_minus_clinical_tier_ranks"] == -1.0


def test_a_short_or_unmatched_rubric_digest_is_refused(tmp_path):
    advice, _ = _two_rubric_corpus(tmp_path)
    with pytest.raises(ValueError, match="at least 12"):
        _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path), rubric_digest="abc")
    with pytest.raises(ValueError, match="matches 0"):
        _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path), rubric_digest="0" * 12)


def test_a_judgment_without_a_rubric_digest_is_counted_not_pooled(tmp_path):
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
        ("s2", "m1", "clinical", "routine", "see a cardiologist", "primary", None),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    assert bundle["coverage"]["unmeasurable_by_reason"] == {"judgment_missing_rubric_sha256": 1}


def test_the_rubric_in_hand_must_be_the_one_the_judge_was_shown(tmp_path):
    """The tier order is read from the rubric whose canonical digest the judgments carry; a
    different rubric file is refused rather than used to rank the tiers."""
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    other_path, _ = _rubric_file(tmp_path, name="other.json", version="other")
    with pytest.raises(ValueError, match="canonical digest"):
        _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path), rubric_path=other_path)


def test_the_tier_order_comes_from_the_rubric_not_from_code(tmp_path):
    """A rubric listing the same tiers in the opposite order reverses the tier comparison: the
    ranking is data, read from the rubric the judge used."""
    reversed_path, reversed_digest = _rubric_file(tmp_path, tiers=TEST_TIERS[::-1], name="reversed.json")
    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "urgent", "see a cardiologist", "primary", reversed_digest),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary", reversed_digest),
        ("s2", "m1", "clinical", "routine", "see a cardiologist", "primary", reversed_digest),
        ("s2", "m1", "patient", "routine", "see your doctor", "primary", reversed_digest),
    ])
    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path), rubric_path=reversed_path)
    assert bundle["urgency_tier_for_comparison"]["all_cells"]["patient_minus_clinical_tier_ranks"] == 0.5


def test_the_bundle_records_every_input_archive_with_its_digest(tmp_path):
    """Codex, PR #29: the script globs growing append-only archives, so the recorded command and
    seed analyse a different corpus once another archive lands. The bundle names every file read
    with its sha256 and row count, and a newly landed archive shows up in it."""
    import hashlib
    from pathlib import Path

    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    vocab = _vocab_file(tmp_path)
    bundle = _analyze(tmp_path, advice, vocab_path=vocab)
    inputs = bundle["inputs"]
    assert inputs["advice_dir"] == advice
    for family, name in (("responses", "responses_stimuli_x.jsonl"), ("judgments", "judgments_stimuli_x.jsonl")):
        path = Path(advice) / name
        assert inputs[family] == [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                   "rows": 2}]
    assert bundle["vocabulary"]["sha256"] == hashlib.sha256(Path(vocab).read_bytes()).hexdigest()

    (Path(advice) / "judgments_stimuli_y.jsonl").write_text("", encoding="utf-8")
    later = _analyze(tmp_path, advice, vocab_path=vocab)
    assert [f["rows"] for f in later["inputs"]["judgments"]] == [2, 0]
    assert later["readouts"] == bundle["readouts"]


def test_a_reply_containing_a_unicode_line_separator_is_one_record(tmp_path):
    """advice_eval writes both archive families with ensure_ascii=False, which leaves U+2028,
    U+2029 and U+0085 raw inside a string. `str.splitlines` splits on all three, so the reader cut
    such a reply into pieces and failed with a JSONDecodeError. Records are split on "\\n" only."""
    from pathlib import Path

    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    responses = Path(advice) / "responses_stimuli_x.jsonl"
    rows = [json.loads(line) for line in responses.read_text(encoding="utf-8").split("\n") if line]
    rows[0]["response_text"] = "first see a cardiologist\u0085then rest"
    responses.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert " " in responses.read_text(encoding="utf-8")

    bundle = _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))
    assert bundle["inputs"]["responses"][0]["rows"] == 2
    assert bundle["coverage"]["judge_of_record_rows_measured"] == 2
    assert bundle["readouts"]["names_specialist_service"]["all_cells"]["patient_minus_clinical"] == -1.0


def test_a_corrupt_archive_line_is_refused_with_its_file_and_line(tmp_path):
    from pathlib import Path

    advice = _corpus(tmp_path, [
        ("s1", "m1", "clinical", "routine", "see a cardiologist", "primary"),
        ("s1", "m1", "patient", "routine", "see your doctor", "primary"),
    ])
    judgments = Path(advice) / "judgments_stimuli_x.jsonl"
    judgments.write_text(judgments.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"judgments_stimuli_x\.jsonl:3: corrupt JSONL line"):
        _analyze(tmp_path, advice, vocab_path=_vocab_file(tmp_path))


def test_a_null_judgment_retried_to_a_valid_one_is_history_not_an_unmeasurable_row(tmp_path):
    """Codex, PR #29: advice_eval's judge leaves a null judgment in the append-only archive and a later run retries
    it, appending a valid row for the same sample. The null was counted as unmeasurable while its retry was measured,
    so one sample sat on both sides of the coverage figure (four such rows in the committed primary-judge corpus:
    44 unmeasurable and coverage 0.993205 instead of 40 and 0.993819). The null is now reported on its own line,
    outside the coverage count. The key is the sample, not the response digest: two samples returning identical
    text share a digest, and both are measurements; a null with no later valid row stays unmeasurable."""
    _, digest = _rubric_file(tmp_path)
    advice = tmp_path / "advice"
    advice.mkdir()

    def judgment(sha, stimulus, arm, k, tier, judge="primary"):
        return {"response_sha256": sha, "rubric_sha256": digest, "judge_model": judge, "stimulus_id": stimulus,
                "model": "m1", "arm": arm, "sample_k": k, "tier": tier}

    responses = [{"response_sha256": "r1", "response_text": "reply naming term-a"},
                 {"response_sha256": "r2", "response_text": "reply without it"},
                 {"response_sha256": "r3", "response_text": "identical reply naming term-a"},
                 {"response_sha256": "r4", "response_text": "reply without it either"},
                 {"response_sha256": "r5", "response_text": "a reply the judge never tiered"}]
    judgments = [judgment("r1", "s1", "clinical", 1, "routine"),
                 judgment("r2", "s1", "patient", 1, None),            # failed ...
                 judgment("r2", "s1", "patient", 1, "routine"),       # ... and retried: the null is history
                 judgment("r3", "s2", "clinical", 1, "urgent"),       # two samples, identical text: both measured
                 judgment("r3", "s2", "clinical", 2, "urgent"),
                 judgment("r4", "s2", "patient", 1, "routine"),
                 judgment("r5", "s2", "patient", 2, None),            # never retried: unmeasurable
                 judgment("r5", "s2", "patient", 2, None)]            # retried and failed again: still unmeasurable
    (advice / "responses_stimuli_x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in responses), encoding="utf-8")
    (advice / "judgments_stimuli_x.jsonl").write_text("".join(json.dumps(j) + "\n" for j in judgments), encoding="utf-8")
    bundle = _analyze(tmp_path, str(advice), vocab_path=_vocab_file(tmp_path, specialist=["term-a"], emergency=["term-b"]))
    cov = bundle["coverage"]
    assert cov["judge_of_record_null_rows_superseded_by_a_later_valid_judgment"] == 1
    assert cov["unmeasurable_by_reason"] == {"tier_absent_or_unrecognised": 2}
    assert (cov["judge_of_record_rows_measured"], cov["judge_of_record_rows_considered"]) == (5, 7)
    assert cov["coverage_rate"] == round(5 / 7, 6)
    assert "retried       1  null judgments whose sample has a later valid judgment" in rd.format_summary(bundle)
    # the identical-text samples are two measurements, not a retry of one
    cells, _ = rd.build_cells(*rd.load_corpus(str(advice))[:2], rd.load_vocab(
        _vocab_file(tmp_path, specialist=["term-a"], emergency=["term-b"])), "primary", digest,
        {t: i for i, t in enumerate(TEST_TIERS)})
    assert len(cells[("s2", "m1")]["clinical"]) == 2
    # a valid row BEFORE a null (not what the judge writes) does not supersede it, and a row missing a key field
    # cannot be matched to a sample at all: both stay unmeasurable
    rows = [judgment("r2", "s1", "patient", 1, "routine"), judgment("r2", "s1", "patient", 1, None),
            dict(judgment("r2", "s1", "patient", None, None)), judgment("r2", "s1", "patient", 1, "routine")]
    superseded = rd.superseded_null_rows(rows, "primary", digest, {t: i for i, t in enumerate(TEST_TIERS)})
    assert superseded == {1}, "the null at index 1 has a later valid row; the keyless null at index 2 does not match"
    assert rd.superseded_null_rows(rows[:2], "primary", digest, {t: i for i, t in enumerate(TEST_TIERS)}) == set()
