"""Mean attribution-mass exporter (scripts/export_tag_mass.py) - offline.

Pins the three-way partition math, the featured-model + holdout gating in collect,
the sum-to-100 rounding, and the empty-input placeholder guard. No network.
"""

import functools
import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_tag_mass", _ROOT / "scripts" / "export_tag_mass.py")
ext = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ext)


def test_three_way_partition_sums_to_one():
    clin, off, struct = ext.three_way(0.3157, 0.0936)
    assert abs((clin + off + struct) - 1.0) < 1e-9
    assert struct == 0.0936                                   # error share passes through
    assert clin < off                                         # non-clinical features dominate here


def test_mean_shares_percentages_sum_to_100():
    m = ext.mean_shares([(0.29, 0.61, 0.10), (0.23, 0.66, 0.11)])
    assert m["clin"] + m["off"] + m["struct"] == 100.0        # struct absorbs rounding
    assert ext.mean_shares([]) is None


def _summary(root, batch, source_set, results):
    d = root / batch
    d.mkdir(parents=True)
    (d / "batch_summary.part_01.json").write_text(json.dumps(
        {"graph_model": "gemma-2-2b", "source_set": source_set, "results": results}),
        encoding="utf-8")


# Synthetic seal fixture (tests/test_tierb_split.py pins these hashes): symptom 4 and 13
# hash holdout, symptom 0 and 1 explore. The Tier B batch registers symptom 4.
HOLD_A, HOLD_B = "The patient reports symptom 4.", "The patient reports symptom 13."
EXPLORE_A, EXPLORE_B = "The patient reports symptom 0.", "The patient reports symptom 1."
TIERB = "pairs_20260711T000000Z"
FEATURED = "gemmascope-transcoder-16k"


def _seal_paths(tmp_path, start="2026-07-10T01:14:38Z"):
    dash = tmp_path / "dashboard.json"
    dash.write_text(json.dumps({"tierb": {"start_utc": start}}), encoding="utf-8")
    sim = tmp_path / "simulated"
    sim.mkdir()
    (sim / f"{TIERB}.json").write_text(json.dumps(
        [{"top_prompt": HOLD_A}, {"top_prompt": EXPLORE_A}]), encoding="utf-8")
    return {"dashboard_path": dash, "simulated_dir": sim}


def _row(index, clinical_prompt, mass=0.30):
    return {"index": index, "prompts": {"clinical": clinical_prompt, "patient": "PT"},
            "clinical_mass": {"clinical": mass, "patient": mass - 0.06},
            "error_share": {"clinical": 0.10, "patient": 0.10}}


def test_collect_gates_featured_and_holdout(tmp_path, monkeypatch):
    # the real seal (tierb_split.sealed_pair) over a synthetic dashboard and batch directory
    monkeypatch.setattr(ext, "sealed_pair", functools.partial(ext.sealed_pair, **_seal_paths(tmp_path)))
    root = tmp_path / "trace_out"
    # featured gemma pair (source_set set) with both phrasings -> counted
    _summary(root, "pairs_F", FEATURED, [_row(1, EXPLORE_B)])
    # non-featured model (source_set null) -> its mass is a NullFetcher artifact, excluded
    _summary(root, "pairs_F__qwen3-4b", None, [
        {"index": 1, "clinical_mass": {"clinical": 0.99, "patient": 0.99},
         "error_share": {"clinical": 0.0, "patient": 0.0}}])
    # Amendment 3: a registered phrase on a re-run stem is sealed (the old copy missed it)
    _summary(root, "repeatability_r1", FEATURED, [_row(1, HOLD_A, mass=0.9)])
    # Tier B: accepted prompt hashes holdout (pair 1), or trace-time prompt does (pair 2)
    _summary(root, TIERB, FEATURED, [_row(1, EXPLORE_B, mass=0.9), _row(2, HOLD_B, mass=0.9)])
    # a row with no value to add is never put to the seal (it has no prompt to check)
    _summary(root, "dialects_X", FEATURED, [{"index": 1, "variants": []}])
    acc = ext.collect(str(root))
    assert len(acc["clinical"]) == 1 and len(acc["patient"]) == 1   # only the featured pair
    payload = ext.build_payload(acc)
    assert payload["empirical"] is True
    assert payload["clinical"]["clin"] > payload["patient"]["clin"]  # clinical share falls
    # no featured/measured pair anywhere -> placeholder preserved (None)
    assert ext.build_payload({"clinical": [], "patient": []}) is None


def test_main_refuses_when_seal_cannot_be_evaluated(tmp_path, monkeypatch, capsys):
    # a dashboard with no Tier B start: the seal raises and nothing is written (exit 2)
    monkeypatch.setattr(ext, "sealed_pair",
                        functools.partial(ext.sealed_pair, **_seal_paths(tmp_path, start=None)))
    root = tmp_path / "trace_out"
    _summary(root, "pairs_F", FEATURED, [_row(1, EXPLORE_B)])
    out = tmp_path / "tag_mass.json"
    rc = ext.main(["--trace-root", str(root), "--out", str(out), "--site", ""])
    assert rc == 2
    assert "CONFIG ERROR" in capsys.readouterr().out
    assert not out.exists()
