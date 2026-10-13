"""Tests for the per-sample token projection (scripts/petri_audit/token_budget.py) and its preflight refusal.

Regression for fire eq01 (run 38311055562, 2026-10-12): two 10-turn equity seeds ran at token_limit 20000, Inspect
halted all six samples, the adapter refused all six, and the target was paid for zero transcripts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.petri_audit import cli, seeds, token_budget
from scripts.petri_audit.token_budget import BYTES_PER_TOKEN, MESSAGE_FRAMING_TOKENS

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "docs" / "framework"
EQUITY_FILE = FRAMEWORK / "petri_seeds_equity.draft.json"
W3_FILE = FRAMEWORK / "petri_seeds_w3.draft.json"
EQ01_LOG = ROOT / "data" / "petri" / "runs" / "run_38311055562_1" / "sanitised_log.json"


def _scripted(path: Path) -> list[dict]:
    return [s for s in seeds.load_seed_file(path).seeds.values() if s.get("mode") == "scripted"]


def _synthetic_seed(turn_bytes: list[int], *, max_turns: int, branches: list[list[int]] | None = None,
                    after_arm_turn: int | None = None) -> dict:
    texts = [{"key": f"u{i}", "text": "x" * n} for i, n in enumerate(turn_bytes)]
    branch_defs = []
    for b, lengths in enumerate(branches or []):
        keys = []
        for j, n in enumerate(lengths):
            texts.append({"key": f"b{b}_{j}", "text": "y" * n})
            keys.append({"role": "user", "text_ref": f"b{b}_{j}"})
        branch_defs.append({"id": f"b{b}", "turns": keys})
    return {
        "seed_id": "synthetic", "mode": "scripted", "texts": texts,
        "system_prompt": {"policy": "none", "text_ref": None, "variants": []},
        "generation": {"max_tokens": 1000},
        "protocol": {"arms": [{"id": "a", "user_is": "patient",
                               "turns": [{"role": "user", "text_ref": f"u{i}"} for i in range(len(turn_bytes))]}],
                     "max_target_turns": max_turns,
                     "branch_anchor": {"after_arm_turn": after_arm_turn, "anchor": "assistant"} if branches else None,
                     "branches": branch_defs},
    }


def _user(n_bytes: int) -> int:
    return -(-n_bytes // int(BYTES_PER_TOKEN)) + MESSAGE_FRAMING_TOKENS


def test_projection_matches_the_controller_call_order_by_hand():
    """Three turns of 30 bytes at a 100-token reply: call k sees k user turns and k-1 replies, and outputs one."""
    seed = _synthetic_seed([30, 30, 30], max_turns=10)
    cond = seeds.conditions(seed)[0]
    p = token_budget.project_condition(seed, cond, assumed_reply_tokens=100)
    u, r = _user(30), 100
    reply_ctx = r + MESSAGE_FRAMING_TOKENS
    expected = (u + r) + (2 * u + reply_ctx + r) + (3 * u + 2 * reply_ctx + r)
    assert (p.target_calls, p.projected_tokens) == (3, expected)
    assert p.worst_case_tokens > p.projected_tokens


def test_projection_stops_at_max_target_turns_and_replays_branches_from_the_anchor():
    """The root stops at max_target_turns; each branch restarts from the anchor reply's context with the exchange
    count reset to the anchor turn, so it too stops at max_target_turns (controller.py)."""
    seed = _synthetic_seed([30, 30, 30], max_turns=2, branches=[[30, 30], [30]], after_arm_turn=1)
    cond = seeds.conditions(seed)[0]
    p = token_budget.project_condition(seed, cond, assumed_reply_tokens=100)
    u, r = _user(30), 100
    reply_ctx = r + MESSAGE_FRAMING_TOKENS
    root = (u + r) + (2 * u + reply_ctx + r)                       # capped at 2 of 3 turns
    anchor_ctx = u + reply_ctx                                     # the history after arm turn 1's reply
    branch = anchor_ctx + u + r                                    # each branch makes one call before the cap
    assert (p.target_calls, p.projected_tokens) == (4, root + 2 * branch)


def test_projection_errs_high_against_every_eq01_sample():
    """Calibration: on the run that motivated the check, every sample's projection at the default reply
    assumption is above the tokens it actually used (input + output over its target calls), and above 20000."""
    log = json.loads(EQ01_LOG.read_text(encoding="utf-8"))
    by_id = {s["seed_id"]: s for s in _scripted(EQUITY_FILE)}
    checked = 0
    for sample in log["samples"]:
        seed_id, condition_id = sample["id"].split("::")
        actual = sum(e["output"]["usage"]["input_tokens"] + e["output"]["usage"]["output_tokens"]
                     for e in sample["events"] if e.get("event") == "model")
        cond = next(c for c in seeds.conditions(by_id[seed_id]) if c["condition_id"] == condition_id)
        p = token_budget.project_condition(by_id[seed_id], cond,
                                           assumed_reply_tokens=token_budget.DEFAULT_ASSUMED_REPLY_TOKENS)
        assert p.projected_tokens > actual > 20000
        checked += 1
    assert checked == 6


def test_equity_seeds_at_20000_are_refused_before_the_lock_or_seal(capsys):
    """The eq01 parameters: preflight refuses every one of the six conditions with exit 5 before any later check."""
    code = cli.main(["preflight", "--seeds", str(EQUITY_FILE), "--target", "anthropic/claude-haiku-4-5",
                     "--max-spend", "3", "--token-limit", "20000", "--no-harness-commit"])
    out = capsys.readouterr()
    assert code == 5
    assert out.err.count("pre-flight: REFUSED") == 6
    assert "holdout seal" not in out.out


@pytest.mark.parametrize("path", [EQUITY_FILE, W3_FILE], ids=["equity", "w3"])
def test_ten_turn_seeds_clear_at_the_limit_landed_runs_used(path):
    problems, notes = token_budget.token_limit_report(_scripted(path), token_limit=40000)
    assert problems == []
    assert any(n.startswith("largest projection") for n in notes)


def test_park_default_selection_still_clears_at_20000():
    """The lane's park default (wave 1 at 20000) is fired after every real run; the check must not refuse it even
    when its target is a real model."""
    wave1 = seeds.select_seeds(seeds.load_seed_file(FRAMEWORK / "petri_seeds.draft.json"), None, 1)
    problems, _ = token_budget.token_limit_report(wave1, token_limit=20000)
    assert problems == []


def test_mock_target_is_reported_not_projected(capsys):
    code = cli.main(["preflight", "--seeds", str(EQUITY_FILE), "--target", "mockllm/model",
                     "--max-spend", "0.01", "--token-limit", "20000", "--no-harness-commit"])
    out = capsys.readouterr()
    assert code != 5
    assert "token projection: not applied to mock target mockllm/model" in out.out
    assert "pre-flight: REFUSED" not in out.err


def test_autonomous_and_tool_seeds_are_named_not_passed_silently():
    base = _scripted(EQUITY_FILE)[0]
    autonomous = dict(copy.deepcopy(base), seed_id="auto", mode="autonomous")
    with_tools = dict(copy.deepcopy(base), seed_id="tools", tools={"definitions": [{"name": "lookup"}]})
    problems, notes = token_budget.token_limit_report([autonomous, with_tools], token_limit=40000)
    assert problems == []
    assert any(n.startswith("auto: not projected") for n in notes)
    assert any(n.startswith("tools::") and "lower bound" in n for n in notes)


def test_non_positive_reply_assumption_is_refused():
    with pytest.raises(ValueError):
        token_budget.token_limit_report(_scripted(EQUITY_FILE), token_limit=40000, assumed_reply_tokens=0)
