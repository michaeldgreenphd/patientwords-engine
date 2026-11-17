"""Round 8 (data/simulated/agscen_r8_20261110.json, owner-read 2026-11-13): two wording types per measured scenario.

Twenty measured scenarios, each with two new everyday wordings: experiential (x), which describes what the person
notices or cannot do, and named (n), which names the body part and the sign in plain words. The owner kept all 40.
The scenarios were chosen after their originals were measured, so the set is exploratory and not outcome-blind.
Pins the shape, the verdicts, the original clinical sides, the single difference, the stem rule and the holdout seal.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_r8_20261110"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"
ORIGINAL_FILES = ("agscen_20261108", "agscen_scale_20261108", "agscen_r5_20261108")


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen_r8", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def _originals() -> dict[str, dict]:
    out = {}
    for stem in ORIGINAL_FILES:
        for p in json.loads((ROOT / "data" / "simulated" / f"{stem}.json").read_text(encoding="utf-8")):
            out[p["generation"]["id"]] = p
    return out


def test_the_file_is_a_2panel_batch_the_lanes_can_read() -> None:
    pairs = _pairs()
    assert isinstance(pairs, list) and len(pairs) == 40
    for pair in pairs:
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"] and pair["target_clinical_token"].startswith(" ")
        gen = pair["generation"]
        assert gen["status"] == "exploratory: hand-authored by Antigravity, owner-read 2026-11-13, not a study batch"
        assert gen["source"]["candidates_commit"].startswith("36f12d77")
        assert gen["source"]["verdicts_commit"].startswith("57f58309")
    ids = [p["generation"]["id"] for p in pairs]
    assert len(set(ids)) == 40


def test_each_scenario_has_one_experiential_and_one_named_wording() -> None:
    gens = [p["generation"] for p in _pairs()]
    assert Counter(g["wording_type"] for g in gens) == {"experiential": 20, "named": 20}
    by_scenario = Counter(g["variant_of"] for g in gens)
    assert len(by_scenario) == 20 and set(by_scenario.values()) == {2}
    assert all({"x": "experiential", "n": "named"}[g["variant"]] == g["wording_type"] for g in gens)


def test_owner_verdicts_and_sidecar() -> None:
    gens = [p["generation"] for p in _pairs()]
    assert all(g["owner_verdict"] == "right" and g["tier_should"] == g["tier_given"] for g in gens)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["pairs"] == 40 and report["source_pairs"] == 40
    assert report["excluded_by_owner"] == [] and report["retiered_by_owner"] == {}
    assert report["cost_usd"] == 0.0 and "run_timestamp" not in report
    assert "not outcome-blind" in report["selection"]


def test_each_clinical_side_is_its_originals_and_each_variant_differs_only_by_its_span() -> None:
    originals = _originals()
    for pair in _pairs():
        gen, top, bottom = pair["generation"], pair["top_prompt"], pair["bottom_prompt"]
        orig = originals[gen["variant_of"]]
        assert top == orig["top_prompt"] and pair["target_clinical_token"] == orig["target_clinical_token"]
        assert gen["original_bottom_prompt"] == orig["bottom_prompt"] and bottom != orig["bottom_prompt"]
        clin, pat = gen["swap_spans"]["clinical_span"], gen["swap_spans"]["patient_span"]
        assert top.count(clin) == 1 and top.replace(clin, pat) == bottom


def test_the_stem_is_refused_by_the_publication_rule_and_matches_no_study_glob() -> None:
    hold = _load("publication_hold")
    assert hold.is_exploratory_run_dir(STEM) and "__" not in STEM
    assert hold.is_exploratory_run_dir(STEM + "__qwen3-4b")
    assert not PAIRS.match("pairs_*.json")


def test_no_prompt_is_a_tier_b_holdout_phrase() -> None:
    split = _load("tierb_split")
    prompts = [p[side] for p in _pairs() for side in ("top_prompt", "bottom_prompt")]
    assert len(prompts) == 80
    assert not [i for i, text in enumerate(prompts) if split.sealed_pair(None, None, text)]
