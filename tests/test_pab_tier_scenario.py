"""Regression tests for the PAB-anchored tier-ladder sensitivity scenario.

Synthetic vocabulary only — no medical terms in test code (repo hard
convention); abstract placeholder tokens stand in for the real lexicon.
"""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pab_tier_scenario",
    Path(__file__).resolve().parent.parent / "scripts" / "pab_tier_scenario.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _draft():
    return {
        "_": "draft header",
        "status": "owner-reviewed v1 · domain review pending",
        "tiers": {"4": "emergency", "3": "specialist", "2": "generalist",
                  "1": "self", "0": "none", "null": "excluded"},
        "tokens": {
            "tokA": {"tier": 3, "confidence": "reviewed-v1"},
            "tokB": {"tier": 4, "confidence": "reviewed-v1"},
            "tokC": {"tier": None, "confidence": "reviewed-v1"},
            "tokD": {"tier": 2, "confidence": "reviewed-v1"},
            "tokE": {"tier": 3, "confidence": "reviewed-v1"},
        },
    }


def test_collapse_moves_only_tier3():
    out = mod.build_anchored(_draft())
    toks = out["tokens"]
    assert toks["tokA"]["tier"] == 2 and "scenario_note" in toks["tokA"]
    assert toks["tokE"]["tier"] == 2
    assert toks["tokB"]["tier"] == 4 and "scenario_note" not in toks["tokB"]
    assert toks["tokC"]["tier"] is None
    assert toks["tokD"]["tier"] == 2 and "scenario_note" not in toks["tokD"]
    assert out["scenario_meta"]["tokens_moved"] == 2


def test_ladder_merges_and_labels():
    out = mod.build_anchored(_draft())
    assert "3" not in out["tiers"]
    assert "former tier 3" in out["tiers"]["2"]
    assert out["status"] == mod.STATUS
    assert "ENGINE-SIDE ONLY" in out["_"]
    # the draft file itself is untouched by the transform
    d = _draft()
    mod.build_anchored(d)
    assert d["tokens"]["tokA"]["tier"] == 3


def test_compare_reads_expected_summary_keys():
    base = {
        "flip_classes": {"downgrade": 10, "upgrade": 4, "lateral": 2, "uninformative": 1},
        "mean_tier_shift": -0.10, "flips": 17,
        "per_model": {"m1": {"downgrades": 7, "upgrades": 3, "mean_tier_shift": -0.5}},
        "per_model_deduped": {"m1": {"downgrades": 6, "upgrades": 3, "mean_tier_shift": -0.4}},
        "headline_downgrader": "m1",
    }
    scen = {
        "flip_classes": {"downgrade": 8, "upgrade": 4, "lateral": 4, "uninformative": 1},
        "mean_tier_shift": -0.06, "flips": 17,
        "per_model": {"m1": {"downgrades": 5, "upgrades": 3, "mean_tier_shift": -0.3}},
        "per_model_deduped": {"m1": {"downgrades": 4, "upgrades": 3, "mean_tier_shift": -0.2}},
        "headline_downgrader": "m1",
    }
    c = mod.compare(base, scen)
    assert c["totals"]["baseline"]["flip_classes"]["downgrade"] == 10
    assert c["totals"]["pab_anchored"]["flip_classes"]["downgrade"] == 8
    assert c["per_model_deduped"]["m1"]["baseline"]["downgrades"] == 6
    assert c["per_model_deduped"]["m1"]["pab_anchored"]["mean_tier_shift"] == -0.2
    assert c["per_model_raw"]["m1"]["baseline"]["downgrades"] == 7
    assert c["headline_downgrader"]["baseline"] == "m1"
