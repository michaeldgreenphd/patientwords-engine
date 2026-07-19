"""backfill_planner: depth-aware coverage + next-fire priority (offline, fixture-based)."""

import importlib.util
import json
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_planner.py"
    spec = importlib.util.spec_from_file_location("backfill_planner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bp = _load()


def _summary(indices):
    return {"results": [{"index": i} for i in indices]}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "ENGINE", tmp_path)
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_A.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}] * 3))
    (sim / "pairs_B.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}] * 4))
    tr = tmp_path / "trace_out"
    # A: gemma trace complete (3/3); B: trace absent
    (tr / "pairs_A").mkdir(parents=True)
    (tr / "pairs_A" / "batch_summary.part_01.json").write_text(json.dumps(_summary([1, 2, 3])))
    # A: lens partial (2/3 pairs of save_raw), B: none
    lens = tr / "pairs_A__jlens_gemma-2-2b"
    (lens / "jlens_raw").mkdir(parents=True)
    (lens / "jlens_summary.part_01.json").write_text(json.dumps(_summary([1, 2])))
    for p in (1, 2):
        for side in ("clinical", "patient"):
            (lens / "jlens_raw" / f"pair_{p:03d}_{side}.json.gz").write_bytes(b"x")
    return tr, sim


def test_depth_coverage_and_resume(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cov = bp.coverage()
    assert cov["pairs_A"]["n"] == 3 and cov["pairs_B"]["n"] == 4
    assert cov["pairs_A"]["trace"] == 3          # complete
    assert cov["pairs_B"]["trace"] == 0          # absent
    assert cov["pairs_A"]["lens"] == 2           # 2/3 save_raw pairs -> partial
    # trace lane resumes the incomplete batch (B, from offset 0)
    tr = bp._next_trace(cov)
    assert tr["params"]["pairs_file"].endswith("pairs_B.json")
    assert tr["params"]["offsets"] == "0"
    # lens lane resumes A at offset 2 (pairs 3/3), since A is the oldest incomplete
    ln = bp._next_lens(cov)
    assert ln["params"]["pairs_file"].endswith("pairs_A.json")
    assert ln["params"]["offset"] == "2" and ln["params"]["limit"] == "1"
    assert ln["params"]["save_raw"] == "true" and ln["params"]["lens_type"] == "JACOBIAN_LENS"


def test_logits_priority_medical_first(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cov = bp.coverage()
    step = bp._next_logits(cov)
    # no model has any logits here, so a MEDICAL model must be chosen first
    assert step["params"]["models"] in bp.MEDICAL
    # 8B medical models use the small chunk
    if step["params"]["models"] in bp.BIG:
        assert int(step["params"]["limit"]) <= bp.LOGITS_CHUNK_BIG


def test_complete_batch_yields_no_fire(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "ENGINE", tmp_path)
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_A.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}]))
    tr = tmp_path / "trace_out"
    # fully cover the single-pair batch on every axis
    (tr / "pairs_A").mkdir(parents=True)
    (tr / "pairs_A" / "batch_summary.json").write_text(json.dumps(_summary([1])))
    lens = tr / "pairs_A__jlens_gemma-2-2b"
    (lens / "jlens_raw").mkdir(parents=True)
    (lens / "jlens_summary.json").write_text(json.dumps(_summary([1])))
    for side in ("clinical", "patient"):
        (lens / "jlens_raw" / f"pair_001_{side}.json.gz").write_bytes(b"x")
    for m in bp.MODELS:
        (tr / f"pairs_A__{m}").mkdir(parents=True)
        (tr / f"pairs_A__{m}" / "batch_summary.json").write_text(json.dumps(_summary([1])))
    cov = bp.coverage()
    steps = bp.plan(cov)
    assert steps["circuit-trace"] is None
    assert steps["jlens-readout"] is None
    assert steps["logits-eval"] is None
