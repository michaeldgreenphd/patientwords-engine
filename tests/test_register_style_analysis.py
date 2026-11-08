"""Tests for scripts/register_style_analysis.py (style-vs-vocabulary sub-study analysis)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import register_style_analysis as rsa  # noqa: E402


def test_sign_test_drops_and_counts_ties() -> None:
    r = rsa.sign_test([1, 2, -1, 0, 0])
    assert (r["pos"], r["neg"], r["ties"], r["n"]) == (2, 1, 2, 5)
    assert r["p"] == pytest.approx(1.0)


def test_binom_two_sided_known_values() -> None:
    assert rsa.binom_two_sided(0, 0) is None
    assert rsa.binom_two_sided(10, 30) == pytest.approx(0.098737146705389)  # 20 vs 10 of 30
    assert rsa.binom_two_sided(0, 5) == pytest.approx(2 / 32)
    assert rsa.binom_two_sided(8, 9) == pytest.approx(2 * (1 + 9) / 512)


def test_holm_step_down_and_monotone() -> None:
    adj = rsa.holm([0.01, 0.04, 0.03])
    assert adj == pytest.approx([0.03, 0.06, 0.06])
    assert rsa.holm([None, 0.2]) == [None, 0.2]


def test_weighted_kappa_perfect_and_chance() -> None:
    assert rsa.weighted_kappa([(0, 0), (1, 1), (2, 2), (3, 3)], "linear") == pytest.approx(1.0)
    assert rsa.weighted_kappa([], "linear") is None
    k = rsa.weighted_kappa([(0, 1), (1, 0), (2, 3), (3, 2)], "quadratic")
    assert k is not None and not math.isnan(k)


def test_join_rejects_bodies_repeated_on_either_side() -> None:
    """Codex review of #155: two A items sharing a body must not both join one B item."""
    a = {"a1": {"clinical_body": "x"}, "a2": {"clinical_body": "x"}, "a3": {"clinical_body": "y"},
         "a4": {"clinical_body": "z"}, "a5": {"clinical_body": "w"}}
    b = {"b1": {"clinical_body": "x"}, "b2": {"clinical_body": "y"},
         "b3": {"clinical_body": "z"}, "b4": {"clinical_body": "z"}}
    joins, unjoined = rsa.join_one_to_one(a, b)
    assert joins == {"a3": "b2"}
    assert sorted(unjoined) == ["a1", "a2", "a4", "a5"]


def test_registered_result_on_committed_archives() -> None:
    """The numbers quoted in docs/exploratory/register_style_results_20261108.md."""
    data = ROOT / "data" / "advice"
    if not (data / f"judgments_{rsa.FILE_B}.jsonl").exists():
        pytest.skip("style-run archives not present")
    main = rsa.analyse(data, rsa.PRIMARY)
    assert main["joined_situations"] == 56 and main["unjoined"] == [] and len(main["models"]) == 7
    got = {c: (main["pooled"][c]["pos"], main["pooled"][c]["neg"], main["pooled"][c]["ties"]) for c in rsa.CONTRASTS}
    assert got == {"style": (20, 10, 26), "vocab": (12, 14, 30), "smv": (18, 11, 27)}
    assert main["pooled"]["style"]["p_holm"] == pytest.approx(0.296211440116167)
    assert main["retest"]["n"] == 382 and main["retest"]["a_higher"] == 28 and main["retest"]["b_higher"] == 20
