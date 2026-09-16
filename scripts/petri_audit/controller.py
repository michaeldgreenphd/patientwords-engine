"""The scripted controller: an engine-side Inspect Agent that drives Petri's
`controller()` from a seed and writes no text of its own (design memo
section 5). Python 3.12 only; imported by the run path, never by the engine's
3.11 suite.

Provenance channel: every staged message, anchor and branch is recorded as an
InfoEvent (`source="patientwords"`) with the text's sha256, so the adapter can
prove staged-text identity against the seed and map Petri's trajectory spans to
the seed's branch ids by creation order and anchor message id.

No approver runs for this agent (Petri wires the realism approver only into
its own LLM auditor loop), so the guarantee that nothing but seed data reaches
the target is this script plus the adapter's digest checks.
"""
from __future__ import annotations

from typing import Any

from inspect_ai.agent import Agent, AgentState, agent
from inspect_ai.log import transcript
from inspect_petri.target import ResponseOutput, controller

from .framework import sha256_text
from .seeds import SeedSet, conditions, seed_digest, text_of, tool_result_for

INFO_SOURCE = "patientwords"
ROOT_BRANCH = "root"


def _info(data: dict[str, Any]) -> None:
    transcript().info(data, source=INFO_SOURCE)


async def _stage_user_and_resume(seed: dict, turn: dict, *, branch_id: str, condition_id: str, turn_index: int,
                                 counters: dict[str, int]) -> Any:
    """Stage one user turn from the seed, resume the target, answer every tool
    call from the seed's results table, and return the final output of the
    exchange (a text reply without pending calls)."""
    c = controller()
    text = text_of(seed, turn["text_ref"])
    anchor = await c.stage_user(text)
    _info({"pw": "staged", "kind": "user", "text_ref": turn["text_ref"], "sha256": sha256_text(text),
           "anchor": anchor, "branch_id": branch_id, "condition_id": condition_id, "turn_index": turn_index,
           "context_role": turn.get("context_role")})
    resp = await c.resume(expected=ResponseOutput)
    counters["generates"] += 1
    while resp.output.message.tool_calls:
        for call in resp.output.message.tool_calls:
            counters["tool_calls"] += 1
            if call.parse_error:
                result = f"The tool call could not be parsed: {call.parse_error}"
                status, tool_ref, marker, query = "error", None, None, None
                counters["parse_errors"] += 1
            else:
                result, marker, query = tool_result_for(seed, call.function, dict(call.arguments or {}))
                if result is None:
                    result = f"Unknown tool: {call.function}"
                    status, tool_ref = "error", None
                    counters["unknown_tools"] += 1
                else:
                    status = "success"
                    tool_ref = next(r["text_ref"] for r in seed["tools"]["results"] if r["tool"] == call.function)
            anchor = await c.stage_tool_result(call.id, result, status=status)
            _info({"pw": "staged", "kind": "tool_result", "tool": call.function, "tool_call_id": call.id,
                   "text_ref": tool_ref, "sha256": sha256_text(result), "status": status, "anchor": anchor,
                   "substituted_query": query, "marker": marker, "branch_id": branch_id, "condition_id": condition_id,
                   "turn_index": turn_index, "parse_error": call.parse_error})
        resp = await c.resume(expected=ResponseOutput)
        counters["generates"] += 1
    return resp.output


@agent(name="patientwords_scripted_controller")
def scripted_auditor(seed_set: SeedSet) -> Agent:
    """Executes the seed named in the sample's metadata: system prompt (if
    any), the condition's arm turns, then for each declared branch a rollback
    to the anchored assistant reply followed by the branch's turns. It never
    reads a reply before staging the next branch, so nothing adaptive enters
    the tree."""

    async def execute(state: AgentState) -> AgentState:
        c = controller()
        meta = c.state.metadata
        seed = seed_set.seeds[meta["seed_id"]]
        cond = next(x for x in conditions(seed) if x["condition_id"] == meta["condition_id"])
        counters = {"generates": 0, "tool_calls": 0, "parse_errors": 0, "unknown_tools": 0}
        _info({"pw": "condition", "seed_id": seed["seed_id"], "seed_sha256": seed_digest(seed),
               "condition_id": cond["condition_id"], "arm_id": cond["arm_id"], "variant_id": cond["variant_id"],
               "register_exposure": seed["protocol"]["register_exposure"], "user_is": cond["user_is"]})
        if cond["system_text_ref"]:
            text = text_of(seed, cond["system_text_ref"])
            anchor = await c.stage_system(text)
            _info({"pw": "staged", "kind": "system", "text_ref": cond["system_text_ref"], "sha256": sha256_text(text),
                   "anchor": anchor, "branch_id": ROOT_BRANCH, "condition_id": cond["condition_id"], "turn_index": 0})
        anchor_spec = seed["protocol"]["branch_anchor"]
        anchor_message_id: str | None = None
        anchor_short: str | None = None
        for i, turn in enumerate(cond["turns"], 1):
            output = await _stage_user_and_resume(seed, turn, branch_id=ROOT_BRANCH, condition_id=cond["condition_id"],
                                                  turn_index=i, counters=counters)
            if anchor_spec and i == anchor_spec["after_arm_turn"]:
                anchor_message_id = output.message.id
                anchor_short = c.short_id(anchor_message_id)
                _info({"pw": "anchor", "condition_id": cond["condition_id"], "after_arm_turn": i,
                       "anchor_message_id": anchor_message_id, "anchor_short": anchor_short,
                       "reply_sha256": sha256_text(output.message.text or "")})
        for branch in seed["protocol"]["branches"]:
            assert anchor_short is not None, "branches declared without a realised anchor"
            await c.rollback(anchor_short)
            _info({"pw": "branch", "branch_id": branch["id"], "condition_id": cond["condition_id"],
                   "parent_branch_id": ROOT_BRANCH, "anchor_message_id": anchor_message_id, "anchor_short": anchor_short})
            for i, turn in enumerate(branch["turns"], 1):
                await _stage_user_and_resume(seed, turn, branch_id=branch["id"], condition_id=cond["condition_id"],
                                             turn_index=i, counters=counters)
        _info({"pw": "done", "condition_id": cond["condition_id"], **counters})
        return state

    return execute
