"""Test-retest consistency: grouping and comparison of repeated traces."""
import json
from pathlib import Path

from scripts.retrace_consistency import collect, compare, main


def hosted_row(index: int, prompts, probs, tops) -> dict:
    """One 2panel result with the keys batch_eval.py writes for a hosted pair.

    `outputs` holds render file paths. The top word of each wording is the first
    entry of its `predictive_spread` list ([[token, probability], ...] best first);
    a `tops` entry of None leaves that wording's spread unrecorded.
    """
    roles = ("clinical", "patient")
    stem = f"index_{index:02d}"
    return {
        "index": index, "mode": "2panel",
        "prompts": dict(zip(roles, prompts)),
        "target_token": "x",
        "probabilities": dict(zip(roles, probs)),
        "language_penalty": probs[1] - probs[0],
        "clinical_mass": {"clinical": 0.0, "patient": 0.0},
        "error_share": {"clinical": 0.0, "patient": 0.0},
        "top_path": {"clinical": "", "patient": ""},
        "mitigation_recovery": None, "translation_method": None, "translation_model": None,
        "forced_targets": [],
        "predictive_spread": {role: None if top is None else [[top, prob], ["other", 0.01]]
                              for role, top, prob in zip(roles, tops, probs)},
        "target_read": {},
        "circuit_diff": {"shared_features": 0, "unique_to_a": 0, "unique_to_b": 0},
        "outputs": {"html": f"{stem}.html", "png": f"{stem}.png",
                    "diff_html": f"{stem}_diff.html", "diff_png": f"{stem}_diff.png"},
    }


def write_rows(root: Path, run: str, rows: list[dict]) -> None:
    d = root / run
    d.mkdir(parents=True)
    (d / "batch_summary.part_01.json").write_text(json.dumps({
        "backend": "hosted", "graph_model": "gemma-2-2b", "results": rows}), encoding="utf-8")


def write_run(root: Path, run: str, prompts, probs, tops) -> None:
    write_rows(root, run, [hosted_row(1, prompts, probs, tops)])


def run_main(tmp_path: Path, monkeypatch) -> dict:
    out = tmp_path / "out.json"
    monkeypatch.setattr("sys.argv", ["retrace_consistency.py", "--trace-root", str(tmp_path / "trace_out"),
                                     "--out", str(out)])
    main()
    return json.loads(out.read_text(encoding="utf-8"))


def test_identical_retrace_zero_spread(tmp_path):
    for run in ("run_a", "run_b"):
        write_run(tmp_path, run, ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    rows = compare(collect(tmp_path))
    assert len(rows) == 1
    assert rows[0]["spread_p_clinical"] == 0.0
    assert rows[0]["top_clinical_stable"] is True and rows[0]["top_patient_stable"] is True
    assert rows[0]["spread_lists_identical"]
    assert rows[0]["cmass_param_variants"] <= 1


def test_moved_retrace_reports_spread_and_instability(tmp_path):
    write_run(tmp_path, "run_a", ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    write_run(tmp_path, "run_b", ("clin A", "pat A"), (0.4, 0.2), ("z", "y"))
    rows = compare(collect(tmp_path))
    assert rows[0]["spread_p_clinical"] == 0.1
    assert rows[0]["top_clinical_stable"] is False
    assert rows[0]["top_patient_stable"] is True


def test_single_trace_pairs_excluded(tmp_path):
    write_run(tmp_path, "run_a", ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    assert compare(collect(tmp_path)) == []


def test_exploratory_set_never_enters_the_repeatability_rows(tmp_path):
    # an exploratory set (scripts/publication_hold.py rule 3) that shares a prompt pair with a study run
    write_run(tmp_path, "pairs_a", ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    write_run(tmp_path, "agscen_20990101", ("clin A", "pat A"), (0.4, 0.2), ("z", "y"))
    skipped: list[str] = []
    assert compare(collect(tmp_path, skipped)) == []
    assert [Path(p).parent.name for p in skipped] == ["agscen_20990101"]


def test_changed_top_word_lowers_the_stable_count(tmp_path, monkeypatch):
    # regression: the top word was read from `outputs` (render paths), so every pair counted as stable
    root = tmp_path / "trace_out"
    pairs = [("clin A", "pat A"), ("clin B", "pat B")]
    write_rows(root, "run_a", [hosted_row(i, p, (0.5, 0.2), ("x", "y")) for i, p in enumerate(pairs, 1)])
    write_rows(root, "run_b", [hosted_row(1, pairs[0], (0.5, 0.2), ("x", "y")),
                               hosted_row(2, pairs[1], (0.5, 0.2), ("x", "z"))])
    payload = run_main(tmp_path, monkeypatch)
    assert payload["pairs_retraced"] == 2
    assert payload["top_word_stable_pairs"] == 1
    assert payload["top_word_not_recorded_pairs"] == 0
    changed = [r for r in payload["rows"] if r["top_patient_stable"] is False]
    assert len(changed) == 1 and changed[0]["top_clinical_stable"] is True


def test_unrecorded_top_word_is_counted_apart_from_stable(tmp_path, monkeypatch):
    root = tmp_path / "trace_out"
    write_run(root, "run_a", ("clin A", "pat A"), (0.5, 0.2), ("x", "y"))
    write_run(root, "run_b", ("clin A", "pat A"), (0.5, 0.2), ("x", None))
    payload = run_main(tmp_path, monkeypatch)
    assert payload["pairs_retraced"] == 1
    assert payload["top_word_stable_pairs"] == 0
    assert payload["top_word_not_recorded_pairs"] == 1
    assert payload["rows"][0]["top_patient_stable"] is None
    assert payload["rows"][0]["top_clinical_stable"] is True
