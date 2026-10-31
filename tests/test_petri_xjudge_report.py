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


def test_a_trailing_row_a_truncated_rejudge_never_wrote_counts_as_ungraded():
    """Codex review of PR #139: a re-grade cut short before the last exchange left that row absent, so the range
    ended at the last surviving row and the conversation read as held. The judge of record's rows give the length."""
    ranks = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}
    pairs_spec = {"pivot_turn": 8, "pairs": [{"equity": "e", "control": "c"}]}
    full = [row(seed_id="e", exchange_index=e, value="emergency") for e in (8, 9, 10)]
    record = xj.JudgeSet("run_1", "a", "judge_of_record", "x", Path("a"), full)
    truncated = xj.JudgeSet("run_1", "b", "rejudge", "y", Path("b"), full[:2])
    expected = xj.expected_last_exchange([record, truncated])
    assert expected[("run_1", "e", "clinical")] == 10
    [out] = xj.equity_contrast(truncated, pairs_spec, ranks, expected)
    assert out["equity"]["missing_from_pivot"] == 1 and out["equity"]["later_tiers"] == {9: "emergency", 10: None}
    assert out["equity"]["held_after_pivot"] is None and out["equity"]["emergency_share_from_pivot"] is None
    [complete] = xj.equity_contrast(record, pairs_spec, ranks, expected)
    assert complete["equity"]["held_after_pivot"] is True


def test_a_register_a_truncated_rejudge_never_reached_is_reported_ungraded():
    """Codex review of PR #139: a register missing from the re-grade's rows was dropped from its summary, so held read
    1/1 with nothing ungraded while the run had two conversations per side."""
    ranks = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}
    pairs_spec = {"pivot_turn": 8, "pairs": [{"equity": "e", "control": "c"}]}
    full = [row(seed_id=seed, condition_id=arm, tree_id=f"{seed}::{arm}#1", exchange_index=e, value="emergency")
            for seed in ("e", "c") for arm in ("clinical", "colloquial") for e in (8, 9, 10)]
    record = xj.JudgeSet("run_1", "a", "judge_of_record", "x", Path("a"), full)
    truncated = xj.JudgeSet("run_1", "b", "rejudge", "y", Path("b"),
                            [r for r in full if r["condition_id"] == "clinical"])
    expected = xj.expected_last_exchange([record, truncated])
    rows = xj.equity_contrast(truncated, pairs_spec, ranks, expected)
    assert sorted(r["register"] for r in rows) == ["clinical", "colloquial"]
    casual = next(r for r in rows if r["register"] == "colloquial")
    assert casual["equity"]["held_after_pivot"] is None and casual["equity"]["missing_from_pivot"] == 3
    [summary] = xj.summarize_equity(rows, ranks)
    assert summary["conversations_per_side"] == 2
    assert summary["equity"]["held"] == 1 and summary["equity"]["held_unknown"] == 1


def test_a_rejudge_with_no_equity_rows_still_enters_an_equity_run(tmp_path):
    full = [row(seed_id="pw-petri-equity-v2-scd-acute-chest", exchange_index=e, value="emergency") for e in (8, 9, 10)]
    paths = {}
    for name, rows in (("a", full), ("b", [row(seed_id="something-else")])):
        paths[name] = tmp_path / f"{name}.jsonl"
        paths[name].write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    record = xj.JudgeSet("run_1", "a", "judge_of_record", "x", paths["a"], full)
    other = xj.JudgeSet("run_1", "b", "rejudge", "y", paths["b"], [row(seed_id="something-else")])
    report = xj.build_report([record, other], seed=1, reps=0)
    by_judge = {r["judge"]: r for r in report["equity_contrast"]}
    assert set(by_judge) == {"a", "b"}
    assert by_judge["a"]["equity"]["held_after_pivot"] is True
    assert by_judge["b"]["equity"]["held_after_pivot"] is None and by_judge["b"]["equity"]["missing_from_pivot"] == 3


def test_rows_written_before_the_exchange_fields_existed_still_pair():
    """The wave-1 pilot's judge-of-record rows carry null exchange_index and null final_in_exchange; they were left
    out of every comparison until 2026-10-31, while the re-grades of the same run carry both fields."""
    old = xj.JudgeSet("run_1", "a", "judge_of_record", "x", Path("a"),
                      [row(exchange_index=None, final_in_exchange=None, value="urgent")])
    new = xj.JudgeSet("run_1", "b", "rejudge", "y", Path("b"), [row(exchange_index=1, value="emergency")])
    p = xj.pair_judges(old, new)
    assert len(p["paired"]) == 1 and p["only_first"] == 0 and p["only_second"] == 0
    assert xj.is_final({"final_in_exchange": None}) and xj.is_final({})
    assert not xj.is_final({"final_in_exchange": False})
