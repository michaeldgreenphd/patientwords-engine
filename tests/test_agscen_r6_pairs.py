"""The fourth exploratory hand-authored pairs file (data/simulated/agscen_r6_20261109.json, 2026-11-09).

Round 6 from Antigravity: 14 dialect pairs built from the verified expression list, 10 folk-meaning pairs (5 name
swaps, 5 with an added explanation) and 12 red-flag pairs, 14 of them below the ER. Pins what the two $0 lanes and
the publication rule need from it, as tests/test_agscen_r5_pairs.py does for round 5: the 2panel pair shape, the
owner's 36 "right" pairs, the typing style, that each pair differs only by its marked span or clause, a stem that
scripts/publication_hold.py refuses and no ``pairs_*`` glob can match, and no Tier B holdout phrase.
"""
from __future__ import annotations

import collections
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_r6_20261109"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen_r6", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def test_the_file_is_a_2panel_batch_the_lanes_can_read() -> None:
    pairs = _pairs()
    assert isinstance(pairs, list) and len(pairs) == 36
    for pair in pairs:
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"] and pair["target_clinical_token"].startswith(" ")
        gen = pair["generation"]
        assert gen["status"] == "exploratory: hand-authored by Antigravity, owner-read 2026-11-09, not a study batch"
        assert gen["source"]["candidates_commit"].startswith("7b538a6e")
        assert gen["source"]["verdicts_commit"].startswith("4909e28d")
        assert gen["source"]["lexicon_commit"].startswith("5fe0de67")
    ids = [p["generation"]["id"] for p in pairs]
    assert ids == [f"r6-{n:03d}" for n in range(1, 37)]


def test_families_levels_and_owner_verdicts() -> None:
    gens = [p["generation"] for p in _pairs()]
    assert collections.Counter(g["family"] for g in gens) == {
        "dialect_non_native": 14, "folk_meaning": 10, "red_flag_everyday": 12}
    assert collections.Counter(g["pair_kind"] for g in gens if g["family"] == "folk_meaning") == {
        "name_swap": 5, "added_explanation": 5}
    assert sum(g["tier_given"] < 4 for g in gens) == 14
    assert all(g["owner_verdict"] == "right" and g["tier_should"] == g["tier_given"] for g in gens)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["pairs"] == 36 and report["excluded_by_owner"] == [] and report["retiered_by_owner"] == {}
    assert report["cost_usd"] == 0.0 and "run_timestamp" not in report


def test_typing_style_and_single_difference() -> None:
    for pair in _pairs():
        gen, top, bottom = pair["generation"], pair["top_prompt"], pair["bottom_prompt"]
        for side in (top, bottom):
            assert not set(side) & set(",;-"), (gen["id"], side)
            assert side.endswith(gen["carrier_frame"])
        clin, pat = gen["swap_spans"]["clinical_span"], gen["swap_spans"]["patient_span"]
        if gen["pair_kind"] == "added_explanation":
            assert clin == "" and bottom.replace(pat, "", 1) == top
        else:
            assert top.count(clin) == 1 and top.replace(clin, pat) == bottom


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
