"""Slang stress Wave A (data/simulated/agscen_slang_a_20261121.json): 48 exploratory next-token pairs.

Copied from the draft pack drafts/slang_stress_20261120/next_token/candidates.json at d9e66e8e (branch
draft/slang-stress-20261120): 4 tier-4, 3 tier-3, 3 tier-2 and 2 tier-1 pairs in each of four trap categories.
No owner, clinical or patient-language review has been recorded for them, so the file carries no verdicts. The
selection is outcome_informed, not outcome-blind. Pins the shape the two $0 lanes read, the id list and the
owner's ten exclusions, the single difference, the tier grid, the provenance, the stem rule (agscen_, never
pairs_) and the holdout seal.
"""
from __future__ import annotations

import collections
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_slang_a_20261121"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"
COMMIT = "d9e66e8e3605e92d6a1567746b45188ccea69423"
CANDIDATES_SHA256 = "95336dfda832a4801fbb3cd5a1743dc42a3e1d7912db6b8cb8b9ae81c8c29ec1"
STATUS = ("exploratory: hand-authored slang stress pair (draft pack slang_stress_20261120), awaiting owner, "
          "clinical and patient-language review, not a study batch")
IDS = [f"ss-nt-{n}" for n in (
    "002 003 005 006 019 023 026 031 033 034 043 044 051 052 054 055 071 074 075 081 084 085 093 094 "
    "101 102 103 105 121 122 124 132 133 134 145 146 152 153 154 155 169 170 171 182 183 187 194 195").split()]
EXCLUDED = [f"ss-nt-{n}" for n in "001 027 064 068 104 108 123 151 157 158".split()]
CATEGORIES = ("polysemous_slang", "casual_idiom_metaphor", "regional_dialect_idiom", "common_misattribution")
GRID = {4: 4, 3: 3, 2: 3, 1: 2}
REVIEW_KEYS = ("owner_verdict", "tier_should", "adjudicated_by", "verdicts")


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen_slang_a", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_the_file_is_a_2panel_batch_the_lanes_can_read() -> None:
    pairs = _pairs()
    assert isinstance(pairs, list) and len(pairs) == 48
    for pair in pairs:
        assert list(pair) == ["top_prompt", "bottom_prompt", "target_clinical_token", "generation"]
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"] and pair["target_clinical_token"].startswith(" ")
        gen = pair["generation"]
        for key in ("id", "trap_category", "condition", "carrier_frame", "slang_mechanism"):
            assert isinstance(gen[key], str) and gen[key].strip(), (gen.get("id"), key)
        assert isinstance(gen["expected_patient_continuations"], list) and gen["expected_patient_continuations"]
        assert isinstance(gen["source_evidence"], list) and gen["source_evidence"]
        assert gen["tokenization"] == "unverified"


def test_the_ids_are_the_owners_list_in_order_and_none_is_excluded() -> None:
    ids = [p["generation"]["id"] for p in _pairs()]
    assert ids == IDS and ids == sorted(ids) and len(set(ids)) == 48
    assert not set(ids) & set(EXCLUDED)


def test_each_pair_differs_only_by_its_one_declared_span() -> None:
    for pair in _pairs():
        gen, top, bottom = pair["generation"], pair["top_prompt"], pair["bottom_prompt"]
        spans = gen["swap_spans"]
        assert set(spans) == {"clinical_span", "patient_span"}, gen["id"]
        clin, pat = spans["clinical_span"], spans["patient_span"]
        assert clin and pat and clin != pat, gen["id"]
        assert top.count(clin) == 1 and top.replace(clin, pat) == bottom, gen["id"]
        for side in (top, bottom):
            assert not set(side) & set(",;-"), gen["id"]
            assert side.endswith(gen["carrier_frame"]), gen["id"]


def test_four_three_three_two_pairs_per_tier_in_each_trap_category() -> None:
    gens = [p["generation"] for p in _pairs()]
    assert all(g["tier_given"] == g["clinical_tier_expected"] for g in gens)
    grid = collections.Counter((g["trap_category"], g["tier_given"]) for g in gens)
    assert grid == {(cat, tier): n for cat in CATEGORIES for tier, n in GRID.items()}
    assert _report()["pairs_by_category_and_tier"] == {cat: {str(t): n for t, n in GRID.items()} for cat in CATEGORIES}


def test_status_selection_and_provenance_are_pinned_and_no_review_is_claimed() -> None:
    for pair in _pairs():
        gen = pair["generation"]
        assert gen["status"] == STATUS and gen["selection"] == "outcome_informed"
        assert gen["source"] == {"candidates": "drafts/slang_stress_20261120/next_token/candidates.json",
                                 "candidates_commit": COMMIT, "candidates_sha256": CANDIDATES_SHA256}
        assert not set(gen) & set(REVIEW_KEYS), gen["id"]


def test_sidecar() -> None:
    report = _report()
    assert report["status"] == STATUS and report["status"].startswith("exploratory:")
    assert report["cost_usd"] == 0.0 and "run_timestamp" not in report
    assert report["pairs"] == 48 and report["source_pairs"] == 200
    source = report["source"]
    assert source["candidates_commit"] == COMMIT and source["candidates_sha256"] == CANDIDATES_SHA256
    assert report["selection"].startswith("outcome_informed") and "not outcome-blind" in report["selection"]
    assert report["naming"].startswith("agscen_ only, never pairs_")
    assert report["excluded_by_owner"] == EXCLUDED and set(report["excluded_reasons"]) == set(EXCLUDED)
    assert report["retiered_by_owner"] == {}
    assert not set(report) & set(REVIEW_KEYS) and report["review"].startswith("pending")


def test_the_four_pairs_named_in_the_naming_note_are_the_ones_whose_clinical_prompt_hashes_holdout() -> None:
    """Under a pairs_ Tier B name these four rows would be sealed (Amendment 1); under agscen_ they are not."""
    split = _load("tierb_split")
    hashed = [p["generation"]["id"] for p in _pairs() if split.is_holdout(p["top_prompt"])]
    assert hashed == ["ss-nt-023", "ss-nt-043", "ss-nt-101", "ss-nt-153"]
    assert all(cid in _report()["naming"] for cid in hashed)


def test_the_stem_is_outside_every_analysis_membership_and_is_not_a_tier_b_batch() -> None:
    hold = _load("publication_hold")
    assert hold.is_exploratory_run_dir(STEM) and "__" not in STEM
    assert hold.is_exploratory_run_dir(STEM + "__qwen3-4b")
    assert not PAIRS.match("pairs_*.json")
    split = _load("tierb_split")
    start = split.tierb_start_stamp(str(ROOT / "ops" / "dashboard.json"))
    assert start and not split.is_tierb_batch(STEM, start)


def test_no_prompt_is_sealed_with_or_without_the_stem() -> None:
    split = _load("tierb_split")
    pairs = _pairs()
    prompts = [(i, p[side]) for i, p in enumerate(pairs, 1) for side in ("top_prompt", "bottom_prompt")]
    assert len(prompts) == 96
    assert not [i for i, text in prompts if split.sealed_pair(None, None, text)]
    assert not [i for i, text in prompts if split.sealed_pair(STEM, i, text)]


def test_the_shared_checker_finds_no_error_and_no_warning() -> None:
    checker = _load("check_candidate_pairs")
    report = checker.check(_pairs(), root=ROOT, exclude=PAIRS, forbid=",;-")
    assert list(report) == IDS
    assert not {cid: r["errors"] for cid, r in report.items() if r["errors"]}
    assert not {cid: r["warnings"] for cid, r in report.items() if r["warnings"]}
