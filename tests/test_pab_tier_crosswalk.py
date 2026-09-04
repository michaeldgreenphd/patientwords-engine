"""Tests for the tier-crosswalk analysis (docs/pab_crosswalk_spec_20260804.md).

Abstract vocabularies only — no medical terms in test code (repo hard
convention). The committed pab_run fixture provides the run-directory shape.
"""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pab_tier_crosswalk",
    Path(__file__).resolve().parent.parent / "scripts" / "pab_tier_crosswalk.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pab_run"


def _write_vocab(tmp_path, tokens):
    p = tmp_path / "vocab.json"
    p.write_text(json.dumps({"tokens": {t: {"tier": tier} for t, tier in tokens.items()}}))
    return p


def _write_map(tmp_path, floors, tasks):
    p = tmp_path / "map.json"
    p.write_text(json.dumps({
        "floors": floors,
        "perturbations": {"shift": {k: v + 1 for k, v in floors.items()}},
        "clinical_task_types": tasks,
    }))
    return p


def test_spearman_known_values():
    assert abs(mod.spearman([1, 2, 3, 4], [1, 2, 3, 4]) - 1.0) < 1e-9
    assert abs(mod.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-9
    assert mod.spearman([1, 2], [2, 1]) is None  # n < 3


def test_lexicon_signal_and_exclusion():
    tiers = {"alpha": 3, "beta": 1}
    sig = mod.lexicon_signal("Alpha beta beta gamma.", tiers)
    assert sig["tier_token_occurrences"] == 3
    assert sig["max_tier"] == 3
    assert abs(sig["mean_tier"] - (3 + 1 + 1) / 3) < 1e-3  # signal rounds to 4dp
    assert mod.lexicon_signal("gamma delta only.", tiers) is None


def test_fixture_run_end_to_end(tmp_path):
    vocab = _write_vocab(tmp_path, {"clarifying": 3, "care": 2, "option": 1})
    smap = _write_map(tmp_path, {"mild": 1, "moderate": 2},
                      ["task-one", "task-two"])
    out = tmp_path / "report.json"
    rc = mod.main(["--run", str(FIXTURE), "--tiers", str(vocab),
                   "--map", str(smap), "--out", str(out)])
    assert rc == 0
    rep = json.loads(out.read_text())
    assert rep["n_rows"] > 0
    assert rep["endpoint1_direction"]["n"] == rep["n_rows"]
    assert "sensitivity_perturbed_map" in rep and "shift" in rep["sensitivity_perturbed_map"]
    # gap arithmetic: floor minus signal, clipped at zero
    # and the report must carry no transcript text or vocabulary terms
    text = out.read_text()
    convs = json.loads((FIXTURE / "0_0" / "conversations.json").read_text())
    for entry in convs:
        for msg in entry["conversation"]:
            assert msg["content"] not in text
    assert "clarifying" not in text


def test_non_clinical_tasks_are_excluded_not_dropped(tmp_path):
    vocab = _write_vocab(tmp_path, {"clarifying": 3})
    smap = _write_map(tmp_path, {"mild": 1, "moderate": 2}, ["task-one"])
    out = tmp_path / "r.json"
    mod.main(["--run", str(FIXTURE), "--tiers", str(vocab),
              "--map", str(smap), "--out", str(out)])
    rep = json.loads(out.read_text())
    assert rep["exclusions"]["non_clinical_task"] > 0


def test_gap_clipping():
    rows, _ = mod.build_rows([str(FIXTURE)], {"clarifying": 3, "care": 2, "option": 1},
                             {"mild": 1, "moderate": 2}, [])
    for r in rows:
        assert r["gap_mean"] >= 0.0
        assert r["gap_max"] >= 0.0


def test_exclusion_diagnostics_record_task_types_and_join_misses(tmp_path):
    """Run 31140382136 regression: an all-exclusions result must be
    attributable from the output alone — observed task_type labels and
    per-experiment join-miss counts, categorical only."""
    rows, excl = mod.build_rows(
        [str(FIXTURE)], {"clarifying": 3, "care": 2, "option": 1},
        {"mild": 1, "moderate": 2, "severe": 4}, ["some_other_task_type"])
    assert rows == []
    diag = excl["_diagnostics"]
    assert excl["non_clinical_task"] > 0
    assert sum(diag["task_types_seen"].values()) >= excl["non_clinical_task"]
    for label in diag["task_types_seen"]:
        assert isinstance(label, str)
