"""The third exploratory hand-authored pairs file (data/simulated/agscen_r5_20261108.json, 2026-11-08).

Round 5 from Antigravity: 18 comma-free rewrites of scale-round pairs the owner excluded for their commas, and 30
new pairs extending measured round-3 pairs. Pins what the two $0 lanes and the publication rule need from it, as
tests/test_agscen_scale_pairs.py does for the second file: the 2panel pair shape, the owner's 48 "right" pairs, a
stem that scripts/publication_hold.py refuses and no ``pairs_*`` glob can match, no Tier B holdout phrase, and none
of the three CHV term ids Antigravity invented for tounge, inflammed and stomache.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_r5_20261108"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"
REWRITTEN = {
    "sc-025", "sc-027", "sc-029", "sc-031", "sc-033", "sc-035", "sc-039", "sc-040", "sc-042",
    "sc-043", "sc-044", "sc-047", "sc-048", "sc-049", "sc-050", "sc-052", "sc-053", "sc-054",
}
INVENTED_TERM_IDS = ("0000033827", "0000024600", "0000033821")


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen_r5", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def test_the_file_is_a_2panel_batch_the_lanes_can_read() -> None:
    pairs = _pairs()
    assert isinstance(pairs, list) and len(pairs) == 48
    for pair in pairs:
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"]
        assert pair["target_clinical_token"].startswith(" ")
        gen = pair["generation"]
        assert gen["status"] == ("exploratory: hand-authored by Antigravity, owner-read 2026-11-08, "
                                 "not a study batch")
        assert gen["source"]["candidates_commit"].startswith("6f65f5ba")
        assert gen["source"]["verdicts_commit"].startswith("e5400d0d")
    ids = [p["generation"]["id"] for p in pairs]
    assert len(set(ids)) == len(ids)


def test_the_rewrites_and_new_pairs_are_the_owners_right_pairs() -> None:
    gens = [p["generation"] for p in _pairs()]
    assert {g["rewrites"] for g in gens if "rewrites" in g} == REWRITTEN
    assert all(g["id"] == g["rewrites"] + "-r5" for g in gens if "rewrites" in g)
    assert sum("rewrites" not in g for g in gens) == 30
    assert all(g["owner_verdict"] == "right" and g["tier_should"] == g["tier_given"] for g in gens)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["pairs"] == 48 and report["source_pairs"] == 48 and report["cost_usd"] == 0.0
    assert report["excluded_by_owner"] == [] and report["retiered_by_owner"] == {}
    assert "run_timestamp" not in report     # study_timeline.py lists no generation event for it


def test_the_comma_rewrites_carry_no_comma_or_hyphen_on_either_side() -> None:
    for pair in _pairs():
        if "rewrites" in pair["generation"]:
            for side in ("top_prompt", "bottom_prompt"):
                assert "," not in pair[side] and "-" not in pair[side], (pair["generation"]["id"], side)


def test_no_invented_chv_citation_is_carried() -> None:
    text = PAIRS.read_text(encoding="utf-8")
    assert not [tid for tid in INVENTED_TERM_IDS if tid in text]
    sources = {p["generation"]["id"]: p["generation"].get("misspelling_source") for p in _pairs()}
    assert all(sources[i] for i in ("r5-024", "r5-025", "r5-026"))


def test_the_stem_is_refused_by_the_publication_rule_and_matches_no_study_glob() -> None:
    hold = _load("publication_hold")
    assert hold.is_exploratory_run_dir(STEM) and "__" not in STEM
    assert hold.is_exploratory_run_dir(STEM + "__qwen3-4b")
    assert not PAIRS.match("pairs_*.json")


def test_no_prompt_is_a_tier_b_holdout_phrase() -> None:
    split = _load("tierb_split")
    prompts = [p[side] for p in _pairs() for side in ("top_prompt", "bottom_prompt") if p[side]]
    assert len(prompts) == 96
    assert not [i for i, text in enumerate(prompts) if split.sealed_pair(None, None, text)]
