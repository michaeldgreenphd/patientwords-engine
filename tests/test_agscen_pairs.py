"""The exploratory hand-authored pairs file (data/simulated/agscen_20261108.json, 2026-11-08).

Pins what the two $0 lanes and the publication rule need from it: the 2panel pair shape the circuit-trace
and logits-eval lanes read, the owner's verdicts (3 excluded, 4 re-levelled with tier_should recorded),
a stem that scripts/publication_hold.py refuses and that no ``pairs_*`` glob (Tier B split, exporter,
archive, convergence) can match, and no prompt that is a Tier B holdout phrase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_20261108"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def test_the_file_is_a_2panel_batch_the_lanes_can_read():
    pairs = _pairs()
    assert isinstance(pairs, list) and len(pairs) == 62
    for pair in pairs:
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"]
        assert pair["target_clinical_token"].startswith(" ")
        gen = pair["generation"]
        assert gen["status"] == ("exploratory: hand-authored by Antigravity, owner-read 2026-11-08, "
                                 "not a study batch")
        assert gen["source"]["candidates_commit"].startswith("f3be9e8a")
        assert gen["source"]["verdicts_commit"].startswith("6492b3ab")
    ids = [p["generation"]["id"] for p in pairs]
    assert len(set(ids)) == len(ids)


def test_owner_verdicts_are_applied_and_recorded():
    by_id = {p["generation"]["id"]: p["generation"] for p in _pairs()}
    assert not {"ag-017", "ag-045", "ag-046"} & set(by_id)
    assert {i: (g["tier_given"], g["tier_should"]) for i, g in by_id.items() if g["owner_verdict"] == "retier"} == {
        "ag-021": (3, 4), "ag-027": (2, 3), "ag-031": (2, 3), "ag-034": (2, 3)}
    assert all(g["owner_verdict"] == "right" and g["tier_should"] == g["tier_given"]
               for i, g in by_id.items() if i not in {"ag-021", "ag-027", "ag-031", "ag-034"})
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["pairs"] == 62 and report["source_pairs"] == 65 and report["cost_usd"] == 0.0
    assert "run_timestamp" not in report     # study_timeline.py lists no generation event for it


def test_the_stem_is_refused_by_the_publication_rule_and_matches_no_study_glob():
    hold = _load("publication_hold")
    assert hold.is_exploratory_run_dir(STEM) and "__" not in STEM
    assert not PAIRS.match("pairs_*.json")


def test_no_prompt_is_a_tier_b_holdout_phrase():
    split = _load("tierb_split")
    prompts = [p[side] for p in _pairs() for side in ("top_prompt", "bottom_prompt") if p[side]]
    assert len(prompts) == 124
    assert not [i for i, text in enumerate(prompts) if split.sealed_pair(None, None, text)]
