"""Cross-backend agreement: joining, censoring, and the prompt-identity guard."""
import json
from pathlib import Path

import pytest

from scripts.backend_agreement import SUMMARY_PATTERNS, compare, join, load_run


def write_run(root: Path, name: str, backend: str, results, part="01",
              family="batch_summary"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{family}.part_{part}.json").write_text(json.dumps({
        "backend": backend, "graph_model": "model-x", "results": results}),
        encoding="utf-8")
    return d


def result(index, prompts, probs, penalty=None):
    return {"index": index,
            "prompts": {"clinical": prompts[0], "patient": prompts[1]},
            "probabilities": {"clinical": probs[0], "patient": probs[1]},
            "language_penalty": penalty}


def test_identical_runs_agree_exactly(tmp_path):
    rows = [result(1, ("c1", "p1"), (0.5, 0.4), -0.1)]
    a = write_run(tmp_path, "ref", "hosted", rows)
    b = write_run(tmp_path, "cand", "logits", rows)
    joined, mismatched = join(load_run(a)[0], load_run(b)[0])
    report = compare(joined)
    assert mismatched == []
    assert report["probability"]["max"] == 0.0
    assert report["penalty"]["mean_reference"] == report["penalty"]["mean_candidate"]


def test_disagreement_is_measured_and_ranked(tmp_path):
    a = write_run(tmp_path, "ref", "hosted",
                  [result(1, ("c1", "p1"), (0.50, 0.40), 0.10),
                   result(2, ("c2", "p2"), (0.20, 0.20), 0.00)])
    b = write_run(tmp_path, "cand", "logits",
                  [result(1, ("c1", "p1"), (0.53, 0.40), 0.13),
                   result(2, ("c2", "p2"), (0.20, 0.20), 0.00)])
    joined, _ = join(load_run(a)[0], load_run(b)[0])
    report = compare(joined, near=0.01, far=0.02)
    assert report["probability"]["n"] == 4
    assert report["probability"]["max"] == pytest.approx(0.03)
    assert report["probability"]["over_near"] == 1
    assert report["probability"]["over_far"] == 1
    # The worst row names the pair and the side, not just the magnitude.
    assert report["worst"][0]["index"] == 1
    assert report["worst"][0]["side"] == "clinical"


def test_prompt_mismatch_is_refused_not_averaged(tmp_path):
    """The one failure that would look like a small disagreement instead of a
    joined-wrong dataset, so it must drop the row and name the index."""
    a = write_run(tmp_path, "ref", "hosted", [result(1, ("c1", "p1"), (0.5, 0.4))])
    b = write_run(tmp_path, "cand", "logits", [result(1, ("c1", "DIFFERENT"), (0.5, 0.4))])
    joined, mismatched = join(load_run(a)[0], load_run(b)[0])
    assert joined == []
    assert mismatched == [1]


def test_censoring_counted_per_side(tmp_path):
    """A reference null against a measured candidate is censoring, not a
    disagreement, and it is reported per side because it is not symmetric."""
    a = write_run(tmp_path, "ref", "hosted",
                  [result(1, ("c1", "p1"), (0.5, None)),
                   result(2, ("c2", "p2"), (0.3, None))])
    b = write_run(tmp_path, "cand", "logits",
                  [result(1, ("c1", "p1"), (0.5, 0.01)),
                   result(2, ("c2", "p2"), (0.3, 0.02))])
    joined, _ = join(load_run(a)[0], load_run(b)[0])
    report = compare(joined)
    assert report["censoring"]["patient"]["reference_null_candidate_measured"] == 2
    assert report["censoring"]["patient"]["rate"] == 1.0
    assert report["censoring"]["clinical"]["reference_null_candidate_measured"] == 0
    # A censored side contributes no delta, so it cannot flatter the agreement.
    assert report["probability"]["n"] == 2


def test_chunked_run_is_the_union_of_its_parts(tmp_path):
    d = write_run(tmp_path, "ref", "hosted", [result(1, ("c1", "p1"), (0.5, 0.4))], part="01")
    write_run(tmp_path, "ref", "hosted", [result(2, ("c2", "p2"), (0.3, 0.2))], part="04")
    results, meta = load_run(d)
    assert sorted(results) == [1, 2]
    assert meta["parts"] == 2 and meta["n_results"] == 2


def test_missing_summary_is_an_error_not_an_empty_report(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit):
        load_run(tmp_path / "empty")



def test_load_run_infers_the_verification_family_when_that_is_what_is_there(tmp_path):
    """A verify run dir holds no batch_summary; reading it must not need a flag."""
    rows = [result(1, ("c1", "p1"), (0.4, 0.3), -0.1)]
    d = write_run(tmp_path, "verify", "interp-engine", rows, family="verify_summary")
    results, meta = load_run(d)
    assert meta["backend"] == "interp-engine"
    assert list(results) == [1]


def test_load_run_refuses_a_dir_holding_both_families(tmp_path):
    """Silently picking one would compare something other than what was asked."""
    d = write_run(tmp_path, "both", "logits", [])
    write_run(tmp_path, "both", "interp-engine", [], family="verify_summary")
    with pytest.raises(SystemExit) as exc:
        load_run(d)
    assert "more than one summary family" in str(exc.value)


def test_load_run_honors_an_explicit_pattern_over_inference(tmp_path):
    d = write_run(tmp_path, "both", "logits", [])
    write_run(tmp_path, "both", "interp-engine", [], family="verify_summary")
    assert load_run(d, "verify_summary*.json")[1]["backend"] == "interp-engine"


def test_missing_summaries_name_every_family_it_looked_for(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit) as exc:
        load_run(empty)
    for pattern in SUMMARY_PATTERNS:
        assert pattern in str(exc.value)


def test_parts_are_ordered_numerically_so_later_part_wins_past_99(tmp_path):
    """String order puts part_100 between part_10 and part_11. With an index
    present in both part_10 and part_100, the documented policy says part_100
    wins; a string sort would let part_10 win. Three batches already reach
    part_100+, so this is one fill-in chunk away from a wrong number."""
    old = result(5, ("c5", "p5"), (0.1, 0.1), 0.0)
    new = result(5, ("c5", "p5"), (0.9, 0.9), 0.0)
    d = write_run(tmp_path, "run", "logits", [old], part="10")
    write_run(tmp_path, "run", "logits", [new], part="100")
    write_run(tmp_path, "run", "logits", [], part="09")
    results, meta = load_run(d)
    assert meta["parts"] == 3
    assert results[5]["probabilities"]["clinical"] == 0.9


def test_part_ordering_helper_is_numeric_and_stable():
    from scripts.backend_agreement import _part_sorted
    names = ["batch_summary.part_11.json", "batch_summary.part_100.json",
             "batch_summary.part_09.json", "batch_summary.part_351.json",
             "batch_summary.part_36.json", "batch_summary.json"]
    got = [n.split("/")[-1] for n in _part_sorted(names)]
    assert got == ["batch_summary.json", "batch_summary.part_09.json", "batch_summary.part_11.json",
                   "batch_summary.part_36.json", "batch_summary.part_100.json", "batch_summary.part_351.json"]


# ------------------------------------------------------------------ verdict from criteria written before a run

import copy  # noqa: E402

from scripts import backend_agreement as ba  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "data" / "experiments" / "protocols" / "first_run_stage_a.preview.v1.json"
HELD = [{"name": "placeholder precondition", "holds": True, "detail": ""}]


def labelled(index, probs, label='Output " tok"'):
    return {**result(index, (f"c{index}", f"p{index}"), probs), "target_token": label}


def joined(reference, candidate):
    rows, mismatched = join({r["index"]: r for r in reference}, {r["index"]: r for r in candidate})
    assert mismatched == []
    return rows


def test_verdict_passes_fails_and_stays_inconclusive_by_the_declared_thresholds():
    criteria = {"pass_max": 0.0005, "fail_above": 0.001,
                "comparable_sides": [{"batch_index": 1, "side": "clinical"}, {"batch_index": 1, "side": "patient"}]}
    reference = [labelled(1, (0.123, 0.456))]
    # 0.1235 - 0.123 is 0.0005000000000000004 in binary; it is on the grid at exactly the pass threshold.
    passing = ba.stage_verdict(joined(reference, [labelled(1, (0.1235, 0.4558))]), criteria, HELD)
    assert (passing["verdict"], passing["sides_compared"], passing["max_abs_delta"]) == ("pass", 2, 0.0005)
    between = ba.stage_verdict(joined(reference, [labelled(1, (0.1238, 0.456))]), criteria, HELD)
    assert between["verdict"] == "inconclusive" and "above 0.0005 and none above 0.001" in between["reason"]
    failing = ba.stage_verdict(joined(reference, [labelled(1, (0.1241, 0.456))]), criteria, HELD)
    assert failing["verdict"] == "fail" and failing["reason"] == "1 side(s) above 0.001"
    assert failing["outcomes"] == ["pass", "fail", "inconclusive"]


def test_a_side_read_on_another_token_is_set_aside_and_never_counted_as_a_disagreement():
    criteria = {"pass_max": 0.0005, "fail_above": 0.001}                       # no list: every side of every row
    reference = [labelled(1, (0.5, 0.4)), labelled(2, (0.5, 0.4), label='Output " other"')]
    candidate = [labelled(1, (0.5, 0.4)), labelled(2, (0.9, 0.1))]
    verdict = ba.stage_verdict(joined(reference, candidate), criteria, HELD)
    assert verdict["verdict"] == "inconclusive" and verdict["sides_compared"] == 2 and verdict["max_abs_delta"] == 0.0
    assert verdict["set_aside"] == [{"index": 2, "side": side, "reason": "target_labels_differ"} for side in ba.SIDES]
    # With row 2 outside the declared set, the same data give a verdict, and the 0.4 difference is not in it.
    declared = {**criteria, "comparable_sides": [{"batch_index": 1, "side": side} for side in ba.SIDES]}
    assert ba.stage_verdict(joined(reference, candidate), declared, HELD)["verdict"] == "pass"


def test_a_failed_an_unchecked_or_a_missing_precondition_gives_inconclusive_whatever_the_values():
    criteria = {"consistent_max": 0.0311, "fail_above": 0.063}
    rows = joined([labelled(1, (0.5, 0.4))], [labelled(1, (0.9, 0.4))])        # 0.4 apart: a fail on values alone
    assert ba.stage_verdict(rows, criteria, HELD)["verdict"] == "fail"
    for holds, phrase in ((False, "does not hold"), (None, "was not checked")):
        verdict = ba.stage_verdict(rows, criteria, [{"name": "identity", "holds": holds, "detail": ""}])
        assert verdict["verdict"] == "inconclusive" and phrase in verdict["reason"]
    missing = joined([labelled(1, (0.5, None))], [labelled(1, (0.5, 0.4))])
    verdict = ba.stage_verdict(missing, criteria, HELD)
    assert verdict["verdict"] == "inconclusive" and verdict["set_aside"][0]["reason"] == "value_missing_or_not_finite"
    assert ba.stage_verdict(joined([labelled(1, (0.5, 0.4))], [labelled(1, (0.5, 0.4))]), criteria, HELD)[
        "verdict"] == "consistent"


def _constructed_candidate(tmp_path, source_part, overrides=None, **inference):
    """A verify summary assembled from a landed part's rows. It is constructed for this test and measures nothing."""
    preview = json.loads(PREVIEW.read_text(encoding="utf-8"))
    model = json.loads((ROOT / preview["protocol"]["path"]).read_text(encoding="utf-8"))["model"]
    results = copy.deepcopy(json.loads((ROOT / source_part).read_text(encoding="utf-8"))["results"])
    for row in results:
        row["token_parity"] = {side: {"match": True} for side in ba.SIDES}
        for side, value in (overrides or {}).get(row["index"], {}).items():
            row["probabilities"][side] = value
    block = {"dtype": model["dtype"], "revision": model["revision"], "revision_pinned": model["revision"],
             "environment": {"interp_engine": ba.criteria_engine_version(ROOT)}, **inference}
    directory = tmp_path / "verify_constructed"
    directory.mkdir()
    (directory / "verify_summary.part_01.json").write_text(
        json.dumps({"backend": "interp-engine", "completed": True, "inference": block, "results": results}),
        encoding="utf-8")
    return directory, preview


def _run(tmp_path, candidate, comparison, reference_part, capsys):
    out = tmp_path / f"{comparison}.json"
    ba.main(["--reference", str((ROOT / reference_part).parent), "--candidate", str(candidate),
             "--criteria", str(PREVIEW), "--comparison", comparison, "--out", str(out)])
    capsys.readouterr()
    return json.loads(out.read_text(encoding="utf-8"))["verdict"]


def test_the_stage_a_criteria_run_on_the_landed_references_with_a_constructed_candidate(tmp_path, capsys):
    """Real reference parts, read-only; the candidate is the landed CPU part's rows relabelled as a verify run.
    The expected numbers are the baseline the run packet records for those two landed parts (section 6.2)."""
    preview = json.loads(PREVIEW.read_text(encoding="utf-8"))
    hosted, cpu = (preview["inputs"][name]["path"] for name in ("landed_hosted_part", "landed_cpu_part"))
    if not (ROOT / hosted).is_file() or not (ROOT / cpu).is_file():
        pytest.skip("the landed reference parts are not in this checkout")
    baseline = preview["parity_criteria"]["stage_a"]["landed_baseline_hosted_vs_cpu_bfloat16"]
    candidate, _ = _constructed_candidate(tmp_path, cpu)
    verdict = _run(tmp_path, candidate, "hosted", hosted, capsys)
    assert all(item["holds"] is True for item in verdict["preconditions"]), verdict["preconditions"]
    assert (verdict["sides_declared"], verdict["sides_compared"]) == (9, baseline["sides"])
    assert verdict["max_abs_delta"] == baseline["max"] and round(verdict["mean_abs_delta"], 5) == baseline["mean"]
    assert verdict["verdict"] == "fail"                    # bfloat16 against a 3-decimal reference: 0.0124 > 0.001
    assert verdict["criteria_status"] == "proposed_before_any_run_not_approved"
    # Against the CPU part itself the same candidate is identical on all 20 sides.
    same = _run(tmp_path, candidate, "cpu_bfloat16", cpu, capsys)
    assert (same["verdict"], same["sides_compared"], same["max_abs_delta"]) == ("consistent", 20, 0.0)


def test_a_constructed_candidate_without_the_pinned_identity_gets_no_verdict(tmp_path, capsys):
    preview = json.loads(PREVIEW.read_text(encoding="utf-8"))
    hosted, cpu = (preview["inputs"][name]["path"] for name in ("landed_hosted_part", "landed_cpu_part"))
    if not (ROOT / hosted).is_file() or not (ROOT / cpu).is_file():
        pytest.skip("the landed reference parts are not in this checkout")
    candidate, _ = _constructed_candidate(tmp_path, cpu, revision=None)       # as the older landed verify parts
    verdict = _run(tmp_path, candidate, "hosted", hosted, capsys)
    assert verdict["verdict"] == "inconclusive" and "pinned revision" in verdict["reason"]
    held = {item["name"]: item["holds"] for item in verdict["preconditions"]}
    assert held["the candidate records the pinned revision as loaded and as pinned"] is False
    assert held["landed_hosted_part has the recorded SHA-256"] is True
    with pytest.raises(SystemExit):
        ba.main(["--reference", str((ROOT / hosted).parent), "--candidate", str(candidate), "--criteria", str(PREVIEW)])
