"""Mean attribution-mass exporter (scripts/export_tag_mass.py) - offline.

Pins the three-way partition math, the featured-model + holdout gating in collect,
the sum-to-100 rounding, and the empty-input placeholder guard. No network.
"""

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


def test_collect_gates_featured_and_holdout(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "ENGINE", tmp_path)
    root = tmp_path / "trace_out"
    # featured gemma pair (source_set set) with both phrasings -> counted
    _summary(root, "pairs_F", "gemmascope-transcoder-16k", [
        {"index": 1, "clinical_mass": {"clinical": 0.30, "patient": 0.24},
         "error_share": {"clinical": 0.10, "patient": 0.10}}])
    # non-featured model (source_set null) -> its mass is a NullFetcher artifact, excluded
    _summary(root, "pairs_F__qwen3-4b", None, [
        {"index": 1, "clinical_mass": {"clinical": 0.99, "patient": 0.99},
         "error_share": {"clinical": 0.0, "patient": 0.0}}])
    acc = ext.collect(str(root))
    assert len(acc["clinical"]) == 1 and len(acc["patient"]) == 1   # only the featured pair
    payload = ext.build_payload(acc)
    assert payload["empirical"] is True
    assert payload["clinical"]["clin"] > payload["patient"]["clin"]  # clinical share falls
    # no featured/measured pair anywhere -> placeholder preserved (None)
    assert ext.build_payload({"clinical": [], "patient": []}) is None
