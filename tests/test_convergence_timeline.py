"""P1/P2 generators: convergence tracker and study timeline (offline)."""

import importlib.util
import json
from pathlib import Path


def _load(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


conv = _load("convergence_tracker")
timeline = _load("study_timeline")


def test_phrase_label_majority_and_tie_break():
    down = {"flipped": True, "flip_class": "downgrade"}
    up = {"flipped": True, "flip_class": "upgrade"}
    none = {"flipped": False, "flip_class": None}
    assert conv.phrase_label([down, down, up]) == "downgrade"
    # ties break least-alarming-first so a tie can never manufacture asymmetry
    assert conv.phrase_label([down, up]) == "upgrade"
    assert conv.phrase_label([down, none]) == "none"


def test_cumulative_points_grow_and_dedupe():
    rows = []
    for stamp, phrases in [("20260706T000000Z", ["a", "b", "c"]),
                           ("20260707T000000Z", ["c", "d", "e", "f"])]:
        for ph in phrases:
            rows.append({"batch": f"pairs_{stamp}", "index": 1, "clinical_prompt": ph,
                         "language_penalty": -0.05, "flipped": False, "flip_class": None})
    pts = conv.cumulative_points(rows, ["20260706T000000Z", "20260707T000000Z"],
                                 seed=7, n_boot=200)
    assert [p["n_phrases"] for p in pts] == [3, 6]  # 'c' re-measured, counted once
    assert pts[1]["through_batch"] == "pairs_20260707T000000Z"
    assert pts[1]["mean_penalty"] == -0.05


def test_convergence_excludes_holdout_via_caller_contract():
    # main() filters tierb_split == "holdout" before cumulative_points; tripwire
    # on the source so the exclusion cannot silently disappear.
    src = (Path(__file__).resolve().parents[1] / "scripts" / "convergence_tracker.py").read_text(
        encoding="utf-8")
    assert 'r.get("tierb_split") != "holdout"' in src


def test_timeline_batches_from_sidecars(tmp_path, monkeypatch):
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_20260710T011743Z.report.json").write_text(json.dumps({
        "run_timestamp": "2026-07-10T01:23:00+00:00", "model": "claude-haiku-4-5",
        "accepted": 50, "cost_usd": 0.08}))
    (sim / "alias_set.report.json").write_text(json.dumps({"cost_usd": 0.0}))
    monkeypatch.chdir(tmp_path)
    entries = timeline.batch_entries()
    assert len(entries) == 1  # zero-cost alias sidecars are not generation events
    assert entries[0]["batch"] == "pairs_20260710T011743Z"
    assert entries[0]["accepted"] == 50


def test_new_models_join_convergence_automatically():
    # llama/biomistral etc. must appear the moment their rows land; the
    # tracker may not gate on a hardcoded model list (owner request 07-10)
    src = (Path(__file__).resolve().parents[1] / "scripts" / "convergence_tracker.py").read_text(
        encoding="utf-8")
    assert 'present = sorted({r["model"] for r in rows})' in src
    assert "PREFERRED_ORDER" in src
