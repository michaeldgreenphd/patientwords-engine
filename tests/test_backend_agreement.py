"""Cross-backend agreement: joining, censoring, and the prompt-identity guard."""
import json
from pathlib import Path

import pytest

from scripts.backend_agreement import compare, join, load_run


def write_run(root: Path, name: str, backend: str, results, part="01"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"batch_summary.part_{part}.json").write_text(json.dumps({
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
