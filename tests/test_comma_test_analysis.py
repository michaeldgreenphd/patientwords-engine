"""scripts/comma_test_analysis.py: the comma test's fixed analysis (docs/exploratory/comma_test_plan_20261109.md)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("comma_test_analysis", ROOT / "scripts" / "comma_test_analysis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sign_test_is_exact_and_two_sided() -> None:
    m = _mod()
    assert m.sign_test(0, 0) == 1.0
    assert m.sign_test(10, 3) == m.sign_test(3, 10)
    assert abs(m.sign_test(10, 3) - 0.09228515625) < 1e-12      # 2 * P(X <= 3), X ~ Bin(13, 1/2)
    assert m.sign_test(4, 4) == 1.0


def test_units_merge_pairs_that_share_a_clinical_sentence() -> None:
    m = _mod()
    diffs = {"a": {"x": 1.0, "y": 3.0}, "b": {"x": -1.0}, "c": {"x": 0.5}, "d": {}}
    unit_of = {"a": "u1", "b": "u1", "c": "u2", "d": "u3"}
    res = m.contrast(diffs, unit_of)
    assert res["pairs"] == {"a": 2.0, "b": -1.0, "c": 0.5}          # a pair with no model is left out
    assert res["units"] == 2 and res["up"] == 2 and res["down"] == 0   # u1 = mean(2.0, -1.0) = 0.5
    assert res["models_per_pair"] == {"a": 2, "b": 1, "c": 1, "d": 0}


def test_a_model_counts_only_when_both_variants_have_a_number() -> None:
    m = _mod()
    a = {"x": {"penalty": -0.2}, "y": {"penalty": None}, "z": {"penalty": -0.1}}
    b = {"x": {"penalty": -0.3}, "y": {"penalty": -0.1}}
    assert m.paired(a, b, "penalty") == {"x": -0.2 - -0.3}


def test_the_committed_files_give_the_planned_units() -> None:
    m = _mod()
    pairs = json.loads((ROOT / "data" / "simulated" / f"{m.COMMAS}.json").read_text(encoding="utf-8"))
    units = {p["top_prompt"] + p["target_clinical_token"] for p in pairs if p["generation"]["variant"] == "nocomma"}
    assert len(units) == 13
    ids = sorted({p["generation"]["scale_id"] for p in pairs})
    kept = [i for i in ids if i not in m.HYPHEN_REWRITES]
    unit_of = {p["generation"]["scale_id"]: p["top_prompt"] for p in pairs if p["generation"]["variant"] == "nocomma"}
    assert len(kept) == 13 and len({unit_of[i] for i in kept}) == 10
    narrow = [i for i in kept if i not in m.AND_TO_WITH]
    assert len(narrow) == 10 and len({unit_of[i] for i in narrow}) == 8


def test_the_committed_traces_give_the_reported_numbers() -> None:
    """Pins docs/exploratory/comma_test_results_20261109.md to the committed trace parts."""
    m = _mod()
    res = m.analyse(ROOT)
    assert res["distinct_clinical_units"] == 13 and res["missing_model_rows"] == {}
    c1 = res["1_commas_penalty"]
    assert (c1["units"], c1["up"], c1["down"], c1["zero"], c1["p"], c1["mean_unit"]) == (13, 10, 3, 0, 0.0923, 0.0101)
    c2 = res["2_commas_baseline"]
    assert (c2["up"], c2["down"], c2["p"]) == (8, 5, 0.5811)
    assert res["3_commas_class"]["comma"]["downgrade_rows"] == 10
    assert res["3_commas_class"]["nocomma"]["downgrade_rows"] == 6
    assert res["3_commas_class"]["comma"]["downgrade_pairs"] == res["3_commas_class"]["nocomma"]["downgrade_pairs"] == 5
    c4 = res["4_connective_penalty"]
    assert (c4["units"], c4["up"], c4["down"], c4["p"]) == (10, 6, 4, 0.7539)
    c4s = res["4s_connective_penalty_insert_only"]
    assert (c4s["units"], c4s["up"], c4s["down"], c4s["p"]) == (8, 4, 4, 1.0)
