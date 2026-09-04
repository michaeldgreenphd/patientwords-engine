"""Tier-vocabulary sensitivity bounds (scripts/tier_sensitivity.py).

Synthetic vocabulary and rows only - no medical vocabulary in this file.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "tier_sensitivity", _ROOT / "scripts" / "tier_sensitivity.py")
ts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ts)

VOCAB = {"alpha": {"tier": 3}, "beta": {"tier": 1}, "gamma": {"tier": 2}}
SPEC = {"deciders": ["gamma"], "blockers": [], "advice_tier_collapses": {"merge": [["t2", "t3"]]}}


def row(model, top_c, top_p):
    return {"model": model, "flipped": True, "top_clinical": top_c, "top_patient": top_p}


def test_scenarios_bracket_the_flagged_token():
    rows = [
        row("m1", "alpha", "beta"),   # 3 -> 1: downgrade under every scenario
        row("m1", "alpha", "gamma"),  # 3 -> 2 baseline; excluded when gamma dropped;
                                      # 3 -> 0 floor (down); 3 -> 4 ceiling (UP)
    ]
    nt = ts.next_token_scenarios(rows, VOCAB, SPEC)
    assert nt["baseline"]["m1"] == {"downgrades": 2, "upgrades": 0, "sign_p": 0.5}
    assert nt["exclude"]["m1"]["downgrades"] == 1  # the gamma call went uninformative
    assert nt["floor"]["m1"]["downgrades"] == 2
    assert nt["ceiling"]["m1"] == {"downgrades": 1, "upgrades": 1, "sign_p": 1.0}
    v = ts.verdicts(nt)
    assert v["m1"]["asymmetry_all_scenarios"] is False  # the ceiling tie breaks it


def test_advice_collapse_merges_adjacent_tiers():
    payload = {
        "tier_order": ["t1", "t2", "t3", "t4"],
        "scenarios": [{"tier_summary": [
            {"clinical": "t3", "patient": "t2"},   # down; merged away under merge
            {"clinical": "t1", "patient": "t4"},   # up in both ladders
        ]}],
    }
    out = ts.advice_scenarios(payload, SPEC)
    assert out["baseline"] == {"down": 1, "up": 1, "unchanged": 0, "sign_p": 1.0}
    assert out["merge"] == {"down": 0, "up": 1, "unchanged": 1, "sign_p": 1.0}


def test_output_file_shape(tmp_path):
    rows_file = tmp_path / "rows.json"
    rows_file.write_text(json.dumps({"rows": [row("m1", "alpha", "beta")]}), encoding="utf-8")
    tiers = tmp_path / "tiers.json"
    tiers.write_text(json.dumps({"tokens": VOCAB}), encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    out = tmp_path / "out.json"
    ts.main(["--rows", str(rows_file), "--tiers", str(tiers), "--spec", str(spec),
             "--advice", str(tmp_path / "absent.json"), "--out", str(out)])
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["next_token"]) == {"baseline", "exclude", "floor", "ceiling"}
    assert doc["next_token_verdicts"]["m1"]["asymmetry_all_scenarios"] is True
