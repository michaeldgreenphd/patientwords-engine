"""Test-retest consistency: grouping and comparison of repeated traces."""
import json
from pathlib import Path

from scripts.retrace_consistency import collect, compare


def write_run(root: Path, run: str, prompts, probs, tops):
    d = root / run
    d.mkdir(parents=True)
    (d / "batch_summary.part_01.json").write_text(json.dumps({
        "backend": "hosted", "graph_model": "gemma-2-2b",
        "results": [{"prompts": {"clinical": prompts[0], "patient": prompts[1]},
                     "probabilities": {"clinical": probs[0], "patient": probs[1]},
                     "outputs": {"clinical": [tops[0]], "patient": [tops[1]]}}]}),
        encoding="utf-8")


def test_identical_retrace_zero_spread(tmp_path):
    for run in ("run_a", "run_b"):
        write_run(tmp_path, run, ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    rows = compare(collect(tmp_path))
    assert len(rows) == 1
    assert rows[0]["spread_p_clinical"] == 0.0
    assert rows[0]["top_clinical_stable"] and rows[0]["top_patient_stable"]
    assert rows[0]["spread_lists_identical"]
    assert rows[0]["cmass_param_variants"] <= 1


def test_moved_retrace_reports_spread_and_instability(tmp_path):
    write_run(tmp_path, "run_a", ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    write_run(tmp_path, "run_b", ("clin A", "pat A"), (0.4, 0.2), ("z", "y"))
    rows = compare(collect(tmp_path))
    assert rows[0]["spread_p_clinical"] == 0.1
    assert not rows[0]["top_clinical_stable"]
    assert rows[0]["top_patient_stable"]


def test_single_trace_pairs_excluded(tmp_path):
    write_run(tmp_path, "run_a", ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    assert compare(collect(tmp_path)) == []
