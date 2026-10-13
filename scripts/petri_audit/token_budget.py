"""Per-sample token projection for scripted seeds, checked by `cli preflight`
and `cli run` before any model call (2026-10-13).

Why: Inspect's `token_limit` is per sample and counts every call's input and
output tokens, and a multi-turn conversation re-sends its whole history on
each call, so a sample's total grows with the square of its turn count. Fire
eq01 (run 38311055562, 2026-10-12) ran two 10-turn equity seeds at the
lane's park-default `token_limit` of 20000: every one of the six samples
reached 20.3k-22.8k tokens by its ninth or tenth call, Inspect halted all six,
the adapter refused all six (`integrity.records_refused`), and the run spent
$0.21 for zero transcripts. The bound in `spend.preflight_bound` caps what a
run can cost; this projection asks the other question, whether a sample can
finish under the limit at all.

Method, per condition (one Inspect sample), following the scripted
controller's call order (controller.py): the root trajectory stages each arm
turn and makes one target call, up to `max_target_turns`; each branch rolls
back to the anchor reply after `after_arm_turn` and replays from there with
the exchange count reset to the anchor's. Call k's input is the system prompt
and tool definitions, every user turn staged so far and every earlier reply;
its output is one reply. Inputs:

- user and system text: UTF-8 bytes / BYTES_PER_TOKEN, plus
  MESSAGE_FRAMING_TOKENS per message. Measured on the eq01 log: 3.84-4.14
  bytes per token across the six samples' user-turn deltas, and turn 1 cost
  about 7 tokens above its text. 3.0 and 8 overstate both.
- replies: `assumed_reply_tokens` per call (default 600). Measured on Haiku
  4.5's landed 10-turn runs: 294-296 output tokens per call on the four
  wave-2 runs, 368 on eq01, at most 454 for any one eq01 sample. A target
  that writes longer replies needs a larger value (`--assumed-reply-tokens`).

At the defaults the projection for eq01's longest sample is about 37k against
the 22.2k it used. It is an estimate meant to err high, not a bound: the
upper bound, every reply at `generation.max_tokens`, is printed beside it and
is far above any limit the lane uses. Two cases are reported rather than
projected, never passed silently: seeds with tools (tool rounds add calls
whose number the seed does not fix, so the figure is a lower bound for
them) and autonomous seeds (the auditor writes the user turns and its calls
count against the same limit).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .seeds import conditions, text_of

BYTES_PER_TOKEN = 3.0
MESSAGE_FRAMING_TOKENS = 8
DEFAULT_ASSUMED_REPLY_TOKENS = 600


@dataclass(frozen=True)
class SampleProjection:
    seed_id: str
    condition_id: str
    target_calls: int
    projected_tokens: int
    worst_case_tokens: int          # every reply at the seed's generation.max_tokens
    has_tools: bool


def _text_tokens(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / BYTES_PER_TOKEN) + MESSAGE_FRAMING_TOKENS


def _trajectory(seed: dict, turns: list[dict], *, context: int, exchanges: int, reply: int) -> tuple[int, int, int]:
    """Tokens spent and calls made by staging `turns` on `context` tokens of history, stopping at the seed's
    max_target_turns as the controller does. Returns (tokens, calls, context after the last reply)."""
    max_turns = seed["protocol"]["max_target_turns"]
    tokens = calls = 0
    for turn in turns:
        if exchanges >= max_turns:
            break
        context += _text_tokens(text_of(seed, turn["text_ref"]))
        tokens += context + reply
        context += reply + MESSAGE_FRAMING_TOKENS
        exchanges += 1
        calls += 1
    return tokens, calls, context


def project_condition(seed: dict, cond: dict, *, assumed_reply_tokens: int) -> SampleProjection:
    """The projected token total of one scripted condition (one Inspect sample)."""
    tool_defs = (seed.get("tools") or {}).get("definitions", [])
    fixed = 0
    if cond["system_text_ref"]:
        fixed += _text_tokens(text_of(seed, cond["system_text_ref"]))
    if tool_defs:
        fixed += math.ceil(len(json.dumps(tool_defs).encode("utf-8")) / BYTES_PER_TOKEN)
    max_reply = int(seed["generation"]["max_tokens"])

    def total(reply: int) -> tuple[int, int]:
        tokens, calls, _ = _trajectory(seed, cond["turns"], context=fixed, exchanges=0, reply=reply)
        anchor = seed["protocol"]["branch_anchor"]
        if anchor:
            after = anchor["after_arm_turn"]
            _, _, anchor_context = _trajectory(seed, cond["turns"][:after], context=fixed, exchanges=0, reply=reply)
            for branch in seed["protocol"]["branches"]:
                b_tokens, b_calls, _ = _trajectory(seed, branch["turns"], context=anchor_context, exchanges=after,
                                                   reply=reply)
                tokens, calls = tokens + b_tokens, calls + b_calls
        return tokens, calls

    projected, calls = total(assumed_reply_tokens)
    worst, _ = total(max_reply)
    return SampleProjection(seed_id=seed["seed_id"], condition_id=cond["condition_id"], target_calls=calls,
                            projected_tokens=projected, worst_case_tokens=worst, has_tools=bool(tool_defs))


def token_limit_report(seeds: list[dict], *, token_limit: int,
                       assumed_reply_tokens: int = DEFAULT_ASSUMED_REPLY_TOKENS) -> tuple[list[str], list[str]]:
    """(problems, notes) for the selected seeds at `token_limit`. A problem is a scripted condition whose projected
    total exceeds the limit: Inspect would halt it before its last call and the adapter would refuse it after the
    target had been paid. Notes name what is reported but not checked, and the largest projection."""
    if assumed_reply_tokens <= 0:
        raise ValueError(f"assumed_reply_tokens must be positive, got {assumed_reply_tokens}")
    problems: list[str] = []
    notes: list[str] = []
    projections: list[SampleProjection] = []
    for seed in seeds:
        if seed.get("mode") != "scripted":
            notes.append(f"{seed['seed_id']}: not projected (mode {seed.get('mode')!r}: the auditor writes the user "
                         "turns, and its calls count against the same per-sample limit)")
            continue
        for cond in conditions(seed):
            projections.append(project_condition(seed, cond, assumed_reply_tokens=assumed_reply_tokens))
    for p in projections:
        if p.has_tools:
            notes.append(f"{p.seed_id}::{p.condition_id}: declares tools; tool rounds add calls the seed does not fix, "
                         "so its projection is a lower bound")
        if p.projected_tokens > token_limit:
            problems.append(f"{p.seed_id}::{p.condition_id}: {p.target_calls} target call(s) project to "
                            f"~{p.projected_tokens} tokens at {assumed_reply_tokens} reply tokens per call, over "
                            f"token_limit {token_limit}; Inspect would halt the sample before its last call and the "
                            "adapter would refuse it after the target was paid")
    if projections:
        top = max(projections, key=lambda p: p.projected_tokens)
        notes.append(f"largest projection {top.projected_tokens} tokens ({top.seed_id}::{top.condition_id}, "
                     f"{top.target_calls} calls, {assumed_reply_tokens} reply tokens per call) against token_limit "
                     f"{token_limit}; every reply at max_tokens would be {top.worst_case_tokens}")
    return problems, notes
