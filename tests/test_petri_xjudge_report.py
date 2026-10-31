"""Tests for scripts/petri_xjudge_report.py (exploratory cross-vendor judging report)."""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("petri_xjudge_report", ROOT / "scripts" / "petri_xjudge_report.py")
xj = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = xj      # dataclasses resolve their module through sys.modules
spec.loader.exec_module(xj)


def row(**kw):
    base = {"tree_id": "s::clinical#1", "branch_id": "root", "turn_id": 2, "exchange_index": 1, "kind": "tier",
            "key": "response_only", "value": "urgent", "final_in_exchange": True, "rendered_sha256": "d1",
            "conversation_id": "c1", "seed_id": "s", "condition_id": "clinical", "judge_model": "j"}
    base.update(kw)
    return base


def test_cohen_kappa_matches_hand_computation():
    # 2x2 table: a/a 20, a/b 5, b/a 10, b/b 15 -> po 0.7, pe 0.5*0.6 + 0.5*0.4 = 0.5, kappa 0.4
    pairs = [("a", "a")] * 20 + [("a", "b")] * 5 + [("b", "a")] * 10 + [("b", "b")] * 15
    assert xj.cohen_kappa(pairs) == pytest.approx(0.4)


def test_kappa_undefined_when_both_judges_use_one_value():
    assert xj.cohen_kappa([("specific", "specific")] * 5) is None
    assert xj.cohen_kappa([]) is None


def test_weighted_kappa_perfect_and_one_step_off():
    assert xj.weighted_kappa([(0, 0), (1, 1), (2, 2), (3, 3)], 4) == pytest.approx(1.0)
    off = xj.weighted_kappa([(0, 1), (1, 2), (2, 3), (3, 3)], 4)
    assert off is not None and 0 < off < 1


def test_pairing_drops_rows_whose_prompt_digests_differ():
    first = xj.JudgeSet("run_1", "a", "judge_of_record", "x", Path("a"),
                        [row(), row(turn_id=4, exchange_index=2)])
    second = xj.JudgeSet("run_1", "b", "rejudge", "y", Path("b"),
                         [row(), row(turn_id=4, exchange_index=2, rendered_sha256="other")])
    p = xj.pair_judges(first, second)
    assert p["digest_mismatch"] == 1 and len(p["paired"]) == 1


def test_pairing_ignores_rows_not_final_in_exchange():
    first = xj.JudgeSet("run_1", "a", "judge_of_record", "x", Path("a"), [row(final_in_exchange=False)])
    second = xj.JudgeSet("run_1", "b", "rejudge", "y", Path("b"), [row(final_in_exchange=False)])
    assert xj.pair_judges(first, second)["paired"] == []


def test_agreement_table_leaves_out_null_and_not_applicable():
    ranks = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}
    paired = [(row(value="urgent"), row(value="emergency")),
              (row(turn_id=4, value=None), row(turn_id=4, value="urgent")),
              (row(turn_id=6, value="not_applicable"), row(turn_id=6, value="not_applicable"))]
    [entry] = xj.agreement_table(paired, ranks, reps=0, rng=random.Random(1))
    assert entry["paired_usable"] == 1 and entry["null_under_either"] == 1
    assert entry["mean_step_second_minus_first"] == pytest.approx(1.0)
    assert entry["second_higher"] == 1 and entry["second_lower"] == 0


def test_bootstrap_is_reproducible_with_the_seed():
    clusters = {f"c{i}": [("a", "a"), ("a", "b") if i % 2 else ("b", "b")] for i in range(10)}
    one = xj.bootstrap_ci(clusters, xj.cohen_kappa, 200, random.Random(7))
    two = xj.bootstrap_ci(clusters, xj.cohen_kappa, 200, random.Random(7))
    assert one == two and one is not None


def test_equity_contrast_marks_a_drop_after_the_pivot_as_not_held():
    ranks = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}
    pairs_spec = {"pivot_turn": 8, "pairs": [{"equity": "e", "control": "c"}]}
    rows = []
    for seed, later in (("e", ["urgent", "emergency"]), ("c", ["emergency", "emergency"])):
        rows.append(row(seed_id=seed, exchange_index=8, value="emergency"))
        rows += [row(seed_id=seed, exchange_index=9 + i, value=v) for i, v in enumerate(later)]
    js = xj.JudgeSet("run_1", "j", "judge_of_record", "x", Path("a"), rows)
    [out] = xj.equity_contrast(js, pairs_spec, ranks)
    assert out["equity"]["held_after_pivot"] is False
    assert out["control"]["held_after_pivot"] is True
    assert out["equity"]["emergency_share_from_pivot"] == pytest.approx(2 / 3)
    [summary] = xj.summarize_equity([out], ranks)
    assert summary["equity"]["held"] == 0 and summary["control"]["held"] == 1


def test_tier_order_is_read_from_the_rubric():
    rubric = json.loads(xj.RUBRIC.read_text(encoding="utf-8"))
    assert list(xj.tier_rank()) == [t["id"] for t in rubric["tiers"]]


def test_report_on_landed_runs_pairs_nothing_without_a_rejudge(tmp_path):
    runs = ROOT / "data" / "petri" / "runs"
    if not any(runs.glob("run_*/judgments.jsonl")):
        pytest.skip("no landed Petri runs in this checkout")
    empty = tmp_path / "rejudge"
    empty.mkdir()
    code = xj.main(["--runs-dir", str(runs), "--rejudge-dir", str(empty), "--bootstrap", "0",
                    "--out-dir", str(tmp_path / "out")])
    assert code == 0
    report = json.loads((tmp_path / "out" / "xjudge_report.json").read_text(encoding="utf-8"))
    assert report["agreement"] == [] and report["bootstrap_seed"] == xj.DEFAULT_SEED


def test_judge_family_ignores_the_route():
    assert xj.judge_family("claude-haiku-4-5") == xj.judge_family("openrouter:anthropic/claude-haiku-4.5")
    assert xj.judge_family("anthropic:claude-haiku-5-5") == xj.judge_family("openrouter:anthropic/claude-haiku-5.5")
    assert xj.judge_family("openrouter:openai/gpt-5.4-mini") == "gpt-5-4-mini"


def test_shift_by_target_reports_the_difference_between_targets():
    a = {"run": "r1", "target": "t1", "first": "claude-haiku-4-5", "second": "openrouter:openai/gpt-5.4-mini",
         "clusters": {"c1": [(2, 2), (2, 3)], "c2": [(3, 3)]}}
    b = {"run": "r2", "target": "t2", "first": "openrouter:anthropic/claude-haiku-4.5",
         "second": "openrouter:openai/gpt-5.4-mini", "clusters": {"c3": [(1, 3)], "c4": [(2, 3)]}}
    [group] = xj.shift_by_target([a, b], reps=200, rng=random.Random(3))
    assert [r["mean_step"] for r in group["runs"]] == [pytest.approx(1 / 3), pytest.approx(1.5)]
    [d] = group["differences"]
    assert d["difference_b_minus_a"] == pytest.approx(1.5 - 1 / 3)
    assert d["ci95"] is not None and d["ci95"][0] <= d["difference_b_minus_a"] <= d["ci95"][1]


def test_shift_by_target_skips_runs_with_the_same_target():
    a = {"run": "r1", "target": "t", "first": "a", "second": "b", "clusters": {"c1": [(1, 2)]}}
    b = {"run": "r2", "target": "t", "first": "a", "second": "b", "clusters": {"c2": [(1, 1)]}}
    [group] = xj.shift_by_target([a, b], reps=10, rng=random.Random(1))
    assert group["differences"] == []


def test_a_missing_grade_after_the_pivot_is_not_read_as_held():
    """Codex review of PR #139: emergency, null, emergency at exchanges 8-10 read as held with an emergency share of
    1.0, because the null row was dropped before the check."""
    ranks = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}
    pairs_spec = {"pivot_turn": 8, "pairs": [{"equity": "e", "control": "c"}]}
    rows = []
    for seed, values in (("e", ["emergency", None, "emergency"]), ("c", ["emergency", "not_applicable", "emergency"])):
        rows += [row(seed_id=seed, exchange_index=8 + i, value=v) for i, v in enumerate(values)]
    js = xj.JudgeSet("run_1", "j", "rejudge", "x", Path("a"), rows)
    [out] = xj.equity_contrast(js, pairs_spec, ranks)
    for side in ("equity", "control"):
        assert out[side]["held_after_pivot"] is None
        assert out[side]["emergency_share_from_pivot"] is None
        assert out[side]["missing_from_pivot"] == 1
        assert out[side]["later_tiers"] == {9: None, 10: "emergency"}
    [summary] = xj.summarize_equity([out], ranks)
    assert summary["equity"] == {"held": 0, "held_of": 0, "held_unknown": 1, "mean_emergency_share_from_pivot": None,
                                 "mean_pre_pivot_rank": None, "pre_pivot_rows": 0}


def test_a_missing_pivot_grade_leaves_held_unknown():
    ranks = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}
    pairs_spec = {"pivot_turn": 8, "pairs": [{"equity": "e", "control": "c"}]}
    rows = [row(seed_id="e", exchange_index=8, value=None), row(seed_id="e", exchange_index=9, value="emergency")]
    js = xj.JudgeSet("run_1", "j", "rejudge", "x", Path("a"), rows)
    [out] = xj.equity_contrast(js, pairs_spec, ranks)
    assert out["equity"]["held_after_pivot"] is None and out["equity"]["missing_from_pivot"] == 1
