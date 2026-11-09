"""The comma-test pairs file (data/simulated/agscen_commas_20261109.json, 2026-11-09).

The 18 scale-round pairs the owner excluded for their commas, each as written and with every comma deleted. Pins
what the comparison and the publication rule need: 36 2panel pairs in twin order, twins that differ only by commas,
a stem that scripts/publication_hold.py refuses and no ``pairs_*`` glob can match, and no Tier B holdout phrase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_commas_20261109"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"
SCALE_IDS = [
    "sc-025", "sc-027", "sc-029", "sc-031", "sc-033", "sc-035", "sc-039", "sc-040", "sc-042",
    "sc-043", "sc-044", "sc-047", "sc-048", "sc-049", "sc-050", "sc-052", "sc-053", "sc-054",
]


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen_commas", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def test_the_file_is_36_2panel_pairs_in_twin_order() -> None:
    pairs = _pairs()
    assert len(pairs) == 36
    for pair in pairs:
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"] and pair["target_clinical_token"].startswith(" ")
        assert pair["generation"]["source"]["candidates_commit"].startswith("765459e3")
        assert pair["generation"]["source"]["verdicts_commit"].startswith("8d8afd1d")
    ids = [p["generation"]["id"] for p in pairs]
    assert ids == [f"{i}-{v}" for i in SCALE_IDS for v in ("comma", "nocomma")]
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["pairs"] == 36 and report["scale_ids"] == SCALE_IDS and report["cost_usd"] == 0.0
    assert "run_timestamp" not in report


def test_twins_differ_only_by_commas() -> None:
    pairs = _pairs()
    for comma, nocomma in zip(pairs[0::2], pairs[1::2]):
        assert comma["generation"]["scale_id"] == nocomma["generation"]["scale_id"]
        assert comma["target_clinical_token"] == nocomma["target_clinical_token"]
        for side in ("top_prompt", "bottom_prompt"):
            assert comma[side].count(",") == 3
            assert "," not in nocomma[side]
            assert comma[side].replace(",", "").split() == nocomma[side].split()
            assert "  " not in nocomma[side]


def test_these_are_the_owners_excluded_pairs() -> None:
    gens = [p["generation"] for p in _pairs()]
    assert all(g["owner_verdict"] == "excluded" and g["owner_note"] for g in gens)
    assert all(g["status"].startswith("exploratory: comma test") for g in gens)


def test_the_stem_is_refused_by_the_publication_rule_and_matches_no_study_glob() -> None:
    hold = _load("publication_hold")
    assert hold.is_exploratory_run_dir(STEM) and "__" not in STEM
    assert hold.is_exploratory_run_dir(STEM + "__qwen3-4b")
    assert not PAIRS.match("pairs_*.json")


def test_no_prompt_is_a_tier_b_holdout_phrase() -> None:
    split = _load("tierb_split")
    prompts = [p[side] for p in _pairs() for side in ("top_prompt", "bottom_prompt")]
    assert len(prompts) == 72
    assert not [i for i, text in enumerate(prompts) if split.sealed_pair(None, None, text)]
