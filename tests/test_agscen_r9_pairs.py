"""Round 9 (data/simulated/agscen_r9_20261110.json): outcome-blind matched-information case families.

Sixteen case families were hand-authored by Antigravity without access to any measured result, in the design of
docs/protocols/instrument_validity_benchmark.md (reference facts, a medical and an everyday wording, a paraphrase
of each, one changed-fact control, and for some families the two mixed-register wordings). The owner read all
sixteen on 2026-11-11 and kept fifteen; the sixteenth is reworded and awaits a second read. Each kept family is
here as 2panel pairs. Pins the shape the two $0 lanes read, the pair kinds, that each pair's declared edit turns
its top side into its bottom side, the split assignment and its seed (made before any measurement), the stem rule
and the holdout seal.
"""
from __future__ import annotations

import collections
import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "agscen_r9_20261110"
PAIRS = ROOT / "data" / "simulated" / f"{STEM}.json"
REPORT = ROOT / "data" / "simulated" / f"{STEM}.report.json"
PENDING = {"r9-14"}
SPLITS = ("discovery", "validation", "fresh_test")
VARIANTS = {"register": {("medical", "everyday")},
            "within_register_paraphrase": {("medical", "medical_paraphrase"), ("everyday", "everyday_paraphrase")},
            "changed_fact": {("everyday", "changed_fact")},
            "syntax_only": {("medical", "quad_b")},
            "lexicon_only": {("medical", "quad_c")}}


def _load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"{name}_agscen_r9", ROOT / "scripts" / f"{name}.py")
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
    assert isinstance(pairs, list) and len(pairs) == 70
    for pair in pairs:
        for key in ("top_prompt", "bottom_prompt", "target_clinical_token"):
            assert isinstance(pair[key], str) and pair[key].strip(), key
        assert pair["top_prompt"] != pair["bottom_prompt"] and pair["target_clinical_token"].startswith(" ")
        gen = pair["generation"]
        assert gen["status"] == "exploratory: hand-authored by Antigravity, owner-read 2026-11-11, not a study batch"
        assert gen["source"]["families_commit"].startswith("d4b27148")
        assert gen["source"]["families_read_commit"].startswith("8f5f61c8")
        assert gen["source"]["verdicts_commit"].startswith("59084e78")
        assert gen["selection"] == "outcome_blind" and gen["owner_verdict"] == "right"
    ids = [p["generation"]["id"] for p in pairs]
    assert len(set(ids)) == 70


def test_families_and_pair_kinds() -> None:
    gens = [p["generation"] for p in _pairs()]
    families = collections.OrderedDict((g["family_id"], g) for g in gens)
    assert list(families) == [f"r9-{n:02d}" for n in range(1, 17) if f"r9-{n:02d}" not in PENDING]
    assert collections.Counter(g["tier_given"] for g in families.values()) == {4: 8, 3: 4, 2: 3}
    assert collections.Counter(g["pair_kind"] for g in gens) == {
        "register": 15, "within_register_paraphrase": 30, "changed_fact": 15, "syntax_only": 5, "lexicon_only": 5}
    for g in gens:
        assert (g["top_variant"], g["bottom_variant"]) in VARIANTS[g["pair_kind"]], g["id"]
        assert g["tier_should"] == g["tier_given"] and len(g["reference_facts"]) >= 3
    per_family = collections.Counter(g["family_id"] for g in gens)
    assert set(per_family.values()) == {4, 6} and sum(v == 6 for v in per_family.values()) == 5
    report = _report()
    assert report["pairs"] == 70 and report["source_families"] == 16
    assert report["families"] == list(families) and set(report["families_pending_reread"]) == PENDING
    assert report["pairs_by_kind"] == dict(collections.Counter(g["pair_kind"] for g in gens))
    assert report["excluded_by_owner"] == [] and report["cost_usd"] == 0.0 and "run_timestamp" not in report


def test_each_declared_edit_turns_the_top_side_into_the_bottom_side() -> None:
    for pair in _pairs():
        gen, top, bottom = pair["generation"], pair["top_prompt"], pair["bottom_prompt"]
        for side in (top, bottom):
            assert not set(side) & set(",;-"), (gen["id"], side)
            assert side.endswith(gen["carrier_frame"]), gen["id"]
        clin, pat = gen["swap_spans"]["clinical_span"], gen["swap_spans"]["patient_span"]
        assert clin and pat and top.count(clin) == 1 and top.replace(clin, pat) == bottom, gen["id"]
        if gen["pair_kind"] == "changed_fact":
            changed = gen["changed_fact"]
            assert (clin, pat) == (changed["from"], changed["to"]) and changed["right_care_after"] != gen["tier_given"]
            assert changed["fact_id"] in {f["fact_id"] for f in gen["reference_facts"]}
        else:
            assert "changed_fact" not in gen


def test_every_wording_of_a_family_is_the_same_text_wherever_it_appears() -> None:
    texts: dict[tuple[str, str], str] = {}
    for pair in _pairs():
        gen = pair["generation"]
        for variant, text in ((gen["top_variant"], pair["top_prompt"]), (gen["bottom_variant"], pair["bottom_prompt"])):
            assert texts.setdefault((gen["family_id"], variant), text) == text, (gen["id"], variant)
    targets = collections.defaultdict(set)
    for pair in _pairs():
        targets[pair["generation"]["family_id"]].add(pair["target_clinical_token"])
    assert all(len(t) == 1 for t in targets.values())


def test_the_split_is_the_seeded_assignment_recorded_before_measurement() -> None:
    """Recomputes the report's method from its seed; a family's split is the same on every one of its pairs."""
    record = _report()["split_assignment"]
    assert record["seed"] == 20261111 and record["unit"] == "case family"
    assert record["assigned_before_any_measurement"] is True
    gens = [p["generation"] for p in _pairs()]
    care = {g["family_id"]: g["tier_given"] for g in gens}
    care["r9-14"] = 2                                   # pending a second read; assigned with the others
    rng = random.Random(record["seed"])
    expected: dict[str, str] = {}
    for level in (4, 3, 2):
        ids = sorted(f for f, c in care.items() if c == level)
        rng.shuffle(ids)
        n = len(ids)
        for i, fid in enumerate(ids):
            expected[fid] = SPLITS[0] if i < n // 2 else SPLITS[1] if i < n // 2 + n // 4 else SPLITS[2]
    assert record["splits"] == expected
    assert collections.Counter(expected.values()) == {"discovery": 8, "validation": 4, "fresh_test": 4}
    assert all(g["split"] == expected[g["family_id"]] for g in gens)
    assert not {p.name for p in ROOT.glob(f"trace_out/{STEM}*")} or record["assigned_utc"] == "2026-11-11"


def test_the_shared_checker_finds_no_error() -> None:
    checker = _load("check_candidate_pairs")
    report = checker.check(_pairs(), root=ROOT, exclude=PAIRS, forbid=",;-")
    assert not {cid: r["errors"] for cid, r in report.items() if r["errors"]}
    kinds = {m.split(":", 1)[0] for r in report.values() for m in r["warnings"]}
    assert kinds <= {"number"}                          # number changes occur only inside changed-fact controls
    assert all(cid.endswith("-chg") for cid, r in report.items() if r["warnings"])


def test_the_stem_is_outside_every_analysis_membership_and_matches_no_study_glob() -> None:
    hold = _load("publication_hold")
    assert hold.is_exploratory_run_dir(STEM) and "__" not in STEM
    assert hold.is_exploratory_run_dir(STEM + "__qwen3-4b")
    assert not PAIRS.match("pairs_*.json")


def test_no_prompt_is_a_tier_b_holdout_phrase() -> None:
    split = _load("tierb_split")
    prompts = sorted({p[side] for p in _pairs() for side in ("top_prompt", "bottom_prompt")})
    assert len(prompts) == 85                           # 15 families x 5 wordings, plus 5 x 2 mixed wordings
    assert not [i for i, text in enumerate(prompts) if split.sealed_pair(None, None, text)]
