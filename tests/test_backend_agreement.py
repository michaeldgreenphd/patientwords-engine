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
