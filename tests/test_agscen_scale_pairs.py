"""The second exploratory hand-authored pairs file (data/simulated/agscen_scale_20261108.json, 2026-11-08).

The scale round that Antigravity wrote from the owner-confirmed agscen_20261108 pairs. Pins what the two $0
lanes and the publication rule need from it, as tests/test_agscen_pairs.py does for the first file: the 2panel
pair shape, only the owner's 34 "right" pairs (22 excluded, none re-levelled), a stem that
scripts/publication_hold.py refuses and that no ``pairs_*`` glob can match, and no Tier B holdout phrase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_scale_20261108"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"
EXCLUDED = {
    "sc-010", "sc-025", "sc-026", "sc-027", "sc-029", "sc-030", "sc-031", "sc-032", "sc-033", "sc-035",
    "sc-039", "sc-040", "sc-042", "sc-043", "sc-044", "sc-047", "sc-048", "sc-049", "sc-050", "sc-052", "sc-053", "sc-054",
}


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen_scale", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def test_the_file_is_a_2panel_batch_the_lanes_can_read() -> None:
    pairs = _pairs()
    assert isinstance(pairs, list) and len(pairs) == 34
    for pair in pairs:
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"]
        assert pair["target_clinical_token"].startswith(" ")
        gen = pair["generation"]
        assert gen["status"] == ("exploratory: hand-authored by Antigravity, owner-read 2026-11-08, "
                                 "not a study batch")
        assert gen["source"]["candidates_commit"].startswith("765459e3")
        assert gen["source"]["verdicts_commit"].startswith("8d8afd1d")
    ids = [p["generation"]["id"] for p in pairs]
    assert len(set(ids)) == len(ids)


def test_only_the_owners_right_pairs_are_kept() -> None:
    by_id = {p["generation"]["id"]: p["generation"] for p in _pairs()}
    assert not EXCLUDED & set(by_id)
    assert len(by_id) + len(EXCLUDED) == 56
    assert all(g["owner_verdict"] == "right" and g["tier_should"] == g["tier_given"] for g in by_id.values())
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["pairs"] == 34 and report["source_pairs"] == 56 and report["cost_usd"] == 0.0
    assert set(report["excluded_by_owner"]) == EXCLUDED and report["retiered_by_owner"] == {}
    assert "run_timestamp" not in report     # study_timeline.py lists no generation event for it


def test_the_stem_is_refused_by_the_publication_rule_and_matches_no_study_glob() -> None:
    hold = _load("publication_hold")
    assert hold.is_exploratory_run_dir(STEM) and "__" not in STEM
    assert hold.is_exploratory_run_dir(STEM + "__qwen3-4b")
    assert not PAIRS.match("pairs_*.json")


def test_no_prompt_is_a_tier_b_holdout_phrase() -> None:
    split = _load("tierb_split")
    prompts = [p[side] for p in _pairs() for side in ("top_prompt", "bottom_prompt") if p[side]]
    assert len(prompts) == 68
    assert not [i for i, text in enumerate(prompts) if split.sealed_pair(None, None, text)]
