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
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig, get_model
from inspect_petri.target import ResponseOutput, controller

from .adaptive import auditor_answer, auditor_text_key, render_conversation, render_system, render_turn_request
from .checks import MAX_TOOL_ROUNDS_PER_TURN, ROOT_BRANCH
from .framework import sha256_text
from .seeds import SeedSet, conditions, seed_digest, text_of, tool_result_for

INFO_SOURCE = "patientwords"
AUDITOR_ROLE = "auditor"
__all__ = ["AUDITOR_ROLE", "INFO_SOURCE", "ROOT_BRANCH", "adaptive_auditor", "scripted_auditor"]


def _info(data: dict[str, Any]) -> None:
    transcript().info(data, source=INFO_SOURCE)


async def _stage_user_and_resume(seed: dict, turn: dict, *, branch_id: str, condition_id: str, turn_index: int,
                                 counters: dict[str, int], text: str | None = None, source: str = "seed",
                                 replies: list[str] | None = None) -> tuple[Any, bool]:
    """Stage one user turn, resume the target, answer every tool call from the
    seed's results table, and return the final output of the exchange (a text
    reply without pending calls) plus whether the exchange was truncated: after
    MAX_TOOL_ROUNDS_PER_TURN rounds of tool calls the controller stops
    resuming, records the limit, and leaves the last calls unanswered, so a
    target that keeps calling tools can never run to the token or cost limit
    as if it had followed the protocol (Codex round 3). The text is the seed's
    (`turn["text_ref"]`) unless the adaptive controller passes the auditor's,
    recorded with `source: auditor`; `replies`, when given, collects the
    assistant's visible text of every message in the exchange, interim ones
    included, in order."""
    c = controller()
    if text is None:
        text = text_of(seed, turn["text_ref"])
    anchor = await c.stage_user(text)
    _info({"pw": "staged", "kind": "user", "text_ref": turn["text_ref"], "sha256": sha256_text(text),
           "anchor": anchor, "branch_id": branch_id, "condition_id": condition_id, "turn_index": turn_index,
           "context_role": turn.get("context_role"), "source": source})
    resp = await c.resume(expected=ResponseOutput)
    counters["generates"] += 1
    rounds = 0
    while resp.output.message.tool_calls:
        if replies is not None and (resp.output.message.text or "").strip():
            replies.append(resp.output.message.text)
        if rounds >= MAX_TOOL_ROUNDS_PER_TURN:
            _info({"pw": "limit", "kind": "tool_rounds", "limit": MAX_TOOL_ROUNDS_PER_TURN, "branch_id": branch_id,
                   "condition_id": condition_id, "turn_index": turn_index})
            counters["limits"] += 1
            return resp.output, True
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
        rounds += 1
    if replies is not None and (resp.output.message.text or "").strip():
        replies.append(resp.output.message.text)
    return resp.output, False


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
        counters = {"generates": 0, "tool_calls": 0, "parse_errors": 0, "unknown_tools": 0, "limits": 0}
        max_turns = seed["protocol"]["max_target_turns"]
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
        truncated = False
        exchanges = 0
        for i, turn in enumerate(cond["turns"], 1):
            if exchanges >= max_turns:
                _info({"pw": "limit", "kind": "target_turns", "limit": max_turns, "branch_id": ROOT_BRANCH,
                       "condition_id": cond["condition_id"], "turn_index": i})
                counters["limits"] += 1
                truncated = True
                break
            output, truncated = await _stage_user_and_resume(seed, turn, branch_id=ROOT_BRANCH,
                                                             condition_id=cond["condition_id"], turn_index=i,
                                                             counters=counters)
            exchanges += 1
            if truncated:
                break
            if anchor_spec and i == anchor_spec["after_arm_turn"]:
                anchor_message_id = output.message.id
                anchor_short = c.short_id(anchor_message_id)
                _info({"pw": "anchor", "condition_id": cond["condition_id"], "after_arm_turn": i,
                       "anchor_message_id": anchor_message_id, "anchor_short": anchor_short,
                       "reply_sha256": sha256_text(output.message.text or "")})
        for branch in seed["protocol"]["branches"]:
            if anchor_short is None:
                # the root was truncated before its anchor: the branches have no prefix to replay and are
                # recorded as unrealised rather than staged on a broken trajectory
                _info({"pw": "limit", "kind": "branch_unrealised", "branch_id": branch["id"],
                       "condition_id": cond["condition_id"], "reason": "root truncated before the branch anchor"})
                counters["limits"] += 1
                continue
            await c.rollback(anchor_short)
            _info({"pw": "branch", "branch_id": branch["id"], "condition_id": cond["condition_id"],
                   "parent_branch_id": ROOT_BRANCH, "anchor_message_id": anchor_message_id, "anchor_short": anchor_short})
            exchanges = anchor_spec["after_arm_turn"]
            for i, turn in enumerate(branch["turns"], 1):
                if exchanges >= max_turns:
                    _info({"pw": "limit", "kind": "target_turns", "limit": max_turns, "branch_id": branch["id"],
                           "condition_id": cond["condition_id"], "turn_index": i})
                    counters["limits"] += 1
                    break
                _output, cut = await _stage_user_and_resume(seed, turn, branch_id=branch["id"],
                                                            condition_id=cond["condition_id"], turn_index=i,
                                                            counters=counters)
                exchanges += 1
                if cut:
                    break
        _info({"pw": "done", "condition_id": cond["condition_id"], **counters})
        return state

    return execute


@agent(name="patientwords_adaptive_controller")
def adaptive_auditor(seed_set: SeedSet, prompt: dict) -> Agent:
    """Executes an autonomous seed (docs/petri_adaptive_design.md): turn 1 is
    the arm's own stimulus, staged from the seed exactly as the scripted
    controller stages it; each later user turn is written by the model bound
    to the `auditor` role from the rendered instructions (adaptive.render_system)
    and the conversation the person has seen so far, then staged verbatim
    under `auditor_turn_text`. Tool calls are answered from the seed's results
    table, never by the auditor. An empty answer, or one that did not end on
    its own (max_tokens, a filter), stops the conversation with a recorded
    limit, which the adapter refuses as a truncated trajectory rather than
    stage a turn the auditor did not finish. No branches: the seed validator
    admits none for this lane (adaptive.adaptive_seed)."""

    async def execute(state: AgentState) -> AgentState:
        c = controller()
        meta = c.state.metadata
        seed = seed_set.seeds[meta["seed_id"]]
        cond = next(x for x in conditions(seed) if x["condition_id"] == meta["condition_id"])
        counters = {"generates": 0, "tool_calls": 0, "parse_errors": 0, "unknown_tools": 0, "limits": 0,
                    "auditor_calls": 0}
        total = min(seed["protocol"]["max_target_turns"], len(cond["turns"]))
        system_text = render_system(prompt, seed, cond)
        _info({"pw": "condition", "seed_id": seed["seed_id"], "seed_sha256": seed_digest(seed),
               "condition_id": cond["condition_id"], "arm_id": cond["arm_id"], "variant_id": cond["variant_id"],
               "register_exposure": seed["protocol"]["register_exposure"], "user_is": cond["user_is"],
               "mode": "autonomous", "auditor_system_sha256": sha256_text(system_text)})
        if cond["system_text_ref"]:
            text = text_of(seed, cond["system_text_ref"])
            anchor = await c.stage_system(text)
            _info({"pw": "staged", "kind": "system", "text_ref": cond["system_text_ref"], "sha256": sha256_text(text),
                   "anchor": anchor, "branch_id": ROOT_BRANCH, "condition_id": cond["condition_id"], "turn_index": 0})
        auditor = get_model(role=AUDITOR_ROLE)
        gen = prompt["generation"]
        config = GenerateConfig(max_tokens=int(gen["max_tokens"]), temperature=float(gen["temperature"]))
        visible: list[tuple[str, str]] = []
        for i in range(1, total + 1):
            if i == 1:
                turn, text, source = cond["turns"][0], None, "seed"
            else:
                request = render_turn_request(prompt, render_conversation(prompt, visible), i, total)
                out = await auditor.generate([ChatMessageSystem(content=system_text), ChatMessageUser(content=request)],
                                             config=config)
                counters["auditor_calls"] += 1
                text = auditor_answer(out)
                if text is None:
                    _info({"pw": "limit", "kind": "auditor_turn", "limit": gen["max_tokens"],
                           "reason": f"auditor answer empty or not finished (stop_reason {out.stop_reason!r})",
                           "branch_id": ROOT_BRANCH, "condition_id": cond["condition_id"], "turn_index": i})
                    counters["limits"] += 1
                    break
                turn, source = {"role": "user", "text_ref": auditor_text_key(i)}, "auditor"
            replies: list[str] = []
            output, truncated = await _stage_user_and_resume(seed, turn, branch_id=ROOT_BRANCH,
                                                             condition_id=cond["condition_id"], turn_index=i,
                                                             counters=counters, text=text, source=source,
                                                             replies=replies)
            visible.append(("user", text if text is not None else text_of(seed, turn["text_ref"])))
            visible.extend(("assistant", r) for r in replies)
            if truncated:
                break
        _info({"pw": "done", "condition_id": cond["condition_id"], **counters})
        return state

    return execute
