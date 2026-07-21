"""P3 aggregator (scripts/patch_aggregate.py) - offline."""

import importlib.util
import json
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "patch_aggregate.py"
_SPEC = importlib.util.spec_from_file_location("patch_aggregate", _MODULE_PATH)
agg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(agg)


def _patching(clean, corrupt, grid):
    return {"clean_prob": clean, "corrupt_prob": corrupt, "recovery": grid}


def test_screen_rules():
    assert agg.screen(_patching(0.1, 0.4, [[0.5]])).startswith("inverted")
    assert agg.screen(_patching(0.4, 0.1, [[None], [None]])) == "all-null grid"
    assert agg.screen(_patching(0.4, 0.1, [[None, 0.2]])) is None


def test_aggregate_profile_and_term_site_split():
    pairs = {
        # best cell at the first aligned position (col 1)
        1: _patching(0.4, 0.1, [[None, 0.10, 0.05],
                                [None, 0.90, 0.40]]),
        # best cell downstream (col 2)
        2: _patching(0.3, 0.1, [[None, 0.20, 0.30],
                                [None, 0.10, 0.80]]),
        # inverted: screened out entirely
        3: _patching(0.1, 0.4, [[None, 0.9, 0.9]]),
    }
    out = agg.aggregate(pairs)
    assert out["pairs_used"] == [1, 2]
    assert list(out["pairs_screened"]) == ["3"]
    # layer 0: max per pair = 0.10 and 0.30 -> mean 0.2; layer 1: 0.9, 0.8 -> 0.85
    assert out["per_layer"] == [
        {"layer": 0, "mean_max_recovery": 0.2, "n": 2},
        {"layer": 1, "mean_max_recovery": 0.85, "n": 2},
    ]
    assert out["best_cell_site"] == {"term_adjacent": 1, "downstream": 1}
    pair1 = next(p for p in out["per_pair"] if p["index"] == 1)
    assert pair1["best"] == {"recovery": 0.9, "layer": 1, "position": 1,
                             "site": "term_adjacent"}
    assert pair1["term_adjacent_best"] == 0.9
    assert pair1["downstream_best"] == 0.4


def test_main_refuses_missing_stem(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert agg.main(["--stem", "nope"]) == 3


def test_main_writes_payload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "trace_out" / "s__patch"
    d.mkdir(parents=True)
    part = {"results": [{"index": 1, "patching": _patching(0.4, 0.1, [[None, 0.5]])}]}
    (d / "batch_summary.part_01.json").write_text(json.dumps(part))
    assert agg.main(["--stem", "s", "--out", "out.json"]) == 0
    payload = json.loads((tmp_path / "out.json").read_text())
    assert payload["pairs_used"] == [1]
    assert payload["term_adjacent_rule"].startswith("first aligned position")
