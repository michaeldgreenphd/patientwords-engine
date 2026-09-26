"""The adaptive-auditor lane: an LLM writes the user's turns 2..N of a
conversation whose first turn is the seed's own stimulus (docs/petri_adaptive_design.md).
Python 3.11-safe; imports nothing from the harness, so the engine's suite tests
the rendering, the seed derivation and the text rule the controller and the
adapter share.

Exploratory by construction: an autonomous seed cannot be claim-grade eligible
(seeds.seed_problems), and the manifest records `execution.mode: autonomous`.
Petri's own auditor is not used. The controller in `controller.adaptive_auditor`
calls the auditor model directly with the instructions in
docs/framework/auditor_prompts/adaptive_user.draft.json, so the auditor has no
tools: it cannot set a system prompt, author a tool result, prefill, roll back
or end the conversation early, and the treatment differs between arms only by
the agenda and the register directive it is given.

Nothing here writes medical vocabulary: every text comes from the seed file or
the prompt file.
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any

from .framework import ROOT, load_json, prompt_canonical
from .seeds import texts_by_key

ADAPTIVE_PROMPT = ROOT / "docs" / "framework" / "auditor_prompts" / "adaptive_user.draft.json"
ADAPTIVE_SEED_FILE = ROOT / "docs" / "framework" / "petri_seeds_adaptive.draft.json"
REGISTER_PROMPT_REF = "docs/framework/judge_prompts/register.draft.json"

SOURCE_PREFIX = "pw-petri-w2-"
ADAPTIVE_PREFIX = "pw-petri-w2a-"
ADAPTIVE_REGISTERS = ("colloquial", "clinical")
AUDITOR_TEXT_PREFIX = "auditor_t"
# The seed's own instruction slot ({instruction} in the system template); the same for every seed, so the only
# per-arm difference the auditor sees is the agenda and the register directive.
AUDITOR_INSTRUCTION = "The person knows only what the list says and what the assistant tells them."

_SYSTEM_SLOTS = re.compile(r"\{(agenda|register_directive|instruction)\}")
_REQUEST_SLOTS = re.compile(r"\{(open|close|conversation|n|total)\}")
_ITEM_SLOTS = re.compile(r"\{(n|text)\}")


def load_adaptive_prompt(path: Path | str = ADAPTIVE_PROMPT) -> dict:
    return load_json(Path(path))


def adaptive_prompt_digest(prompt: dict) -> str:
    """sha256 (64 hex) of the prompt file's order-preserving canonical form: the manifest's
    `execution.auditor_instruction_sha256`. Per-sample rendered system messages are digested on the controller's
    condition event (`auditor_system_sha256`)."""
    return hashlib.sha256(prompt_canonical(prompt).encode("utf-8")).hexdigest()


def _sub(pattern: re.Pattern, template: str, fills: dict[str, str]) -> str:
    """One left-to-right pass, so text inserted by one placeholder is never re-scanned for another (a stimulus
    containing `{n}` stays as written)."""
    return pattern.sub(lambda m: fills[m.group(1)], template)


def arm_register(seed: dict, cond: dict) -> str:
    """The register of the arm's first user turn, which the seed validator ties to the arm's contrast."""
    return texts_by_key(seed)[cond["turns"][0]["text_ref"]]["register"]


def agenda_texts(seed: dict, cond: dict) -> list[str]:
    texts = texts_by_key(seed)
    return [texts[t["text_ref"]]["text"] for t in cond["turns"]]


def render_system(prompt: dict, seed: dict, cond: dict) -> str:
    """The auditor's system message for one condition: the arm's scripted turns as a numbered agenda, the arm's
    register directive and the seed's instruction."""
    items = [_sub(_ITEM_SLOTS, prompt["agenda_item"], {"n": str(i), "text": t})
             for i, t in enumerate(agenda_texts(seed, cond), 1)]
    register = arm_register(seed, cond)
    if register not in prompt["register_directives"]:
        raise KeyError(f"{seed['seed_id']}: no register directive for {register!r} in the auditor prompt")
    return _sub(_SYSTEM_SLOTS, prompt["system"], {"agenda": "\n".join(items),
                                                  "register_directive": prompt["register_directives"][register],
                                                  "instruction": seed["auditor_instruction"]})


def render_conversation(prompt: dict, visible: list[tuple[str, str]]) -> str:
    """The conversation as the person saw it: their messages and the assistant's visible text, labelled, with the
    delimiters escaped inside every text as the judge prompts escape theirs. Tool calls and tool results are not
    shown: the person cannot see them."""
    labels = prompt["speaker_labels"]
    delims = [prompt["delimiters"]["open"], prompt["delimiters"]["close"]]

    def escape(text: str) -> str:
        for d in delims:
            text = text.replace(d, "\\" + d)
        return text

    return "\n\n".join(f"{labels[role]}: {escape(text)}" for role, text in visible)


def render_turn_request(prompt: dict, conversation: str, n: int, total: int) -> str:
    return _sub(_REQUEST_SLOTS, prompt["turn_request"],
                {"open": prompt["delimiters"]["open"], "close": prompt["delimiters"]["close"],
                 "conversation": conversation, "n": str(n), "total": str(total)})


def auditor_turn_text(raw: str | None) -> str | None:
    """The one rule from the auditor's answer to the staged user turn, shared by the controller (which stages it)
    and the adapter (which recomputes it from the logged answer): surrounding whitespace removed, nothing else. An
    empty answer is None: the controller stops the conversation and records the limit rather than staging nothing."""
    text = (raw or "").strip()
    return text or None


def auditor_answer(output: Any) -> str | None:
    """The one rule for what of an auditor call is staged, shared by the controller and the adapter (review of PR #50:
    they disagreed on an unfinished answer, and the adapter then declared a turn the target never received): the
    answer's text under `auditor_turn_text` when the call ended on its own (`stop_reason` "stop"), else None. A None
    stops the conversation with a recorded limit. Duck-typed on `completion` and `stop_reason`."""
    if output is None or getattr(output, "stop_reason", None) != "stop":
        return None
    return auditor_turn_text(getattr(output, "completion", None))


def auditor_text_key(turn_index: int) -> str:
    return f"{AUDITOR_TEXT_PREFIX}{turn_index:02d}"


def effective_seed(seed: dict, cond: dict, auditor_texts: list[str]) -> tuple[dict, dict]:
    """(seed, condition) as the adapter checks an autonomous sample: the seed with one text per auditor-written
    turn, keyed `auditor_tNN` and carrying the arm's register, and the condition whose turns are the seed's first
    turn followed by those texts. Every stimulus-identity check then runs unchanged on what the target received."""
    register = arm_register(seed, cond)
    eff = copy.deepcopy(seed)
    added = [{"key": auditor_text_key(i), "text": t, "register": register}
             for i, t in enumerate(auditor_texts, 2)]
    eff["texts"] = list(eff["texts"]) + added
    cond_eff = dict(cond)
    cond_eff["turns"] = [cond["turns"][0]] + [{"role": "user", "text_ref": a["key"]} for a in added]
    return eff, cond_eff


def adaptive_seed(seed: dict, *, registers: tuple[str, ...] = ADAPTIVE_REGISTERS) -> dict:
    """The adaptive copy of one scripted wave-2 seed: same scenario, texts, tools and generation block; mode
    autonomous and never claim-grade; only the arms whose first turn is in `registers`, so the decomposition
    register is dropped from the framing; the advice tier judged on both instruments and no outcome dimension (the
    lane's estimand is the tier contrast; the per-turn register check is planned for every autonomous record by
    judge_runner.plan_register)."""
    if not seed["seed_id"].startswith(SOURCE_PREFIX):
        raise ValueError(f"{seed['seed_id']}: not a wave-2 seed ({SOURCE_PREFIX}*)")
    if seed["mode"] != "scripted" or seed["protocol"]["branches"]:
        raise ValueError(f"{seed['seed_id']}: the adaptive copy is made from an unbranched scripted seed")
    texts = texts_by_key(seed)
    out = copy.deepcopy(seed)
    out["seed_id"] = ADAPTIVE_PREFIX + seed["seed_id"][len(SOURCE_PREFIX):]
    out["mode"] = "autonomous"
    out["claim_grade_eligible"] = False
    out["auditor_instruction"] = AUDITOR_INSTRUCTION
    out["protocol"]["arms"] = [a for a in seed["protocol"]["arms"]
                               if texts[a["turns"][0]["text_ref"]]["register"] in registers]
    out["framing"]["decomposition_registers"] = [r for r in seed["framing"].get("decomposition_registers", [])
                                                 if r in registers]
    # the texts the copy still references: the kept arms, the tool results, a system prompt and the scenario's
    # warning signs; the dropped arms' texts and the outcome dimensions' supplied contexts go
    kept = {t["text_ref"] for a in out["protocol"]["arms"] for t in a["turns"]}
    kept |= {r["text_ref"] for r in (seed.get("tools") or {}).get("results", [])}
    sp = seed["system_prompt"]
    kept |= {r for r in [sp.get("text_ref"), *(v["text_ref"] for v in sp.get("variants") or []),
                         seed["scenario"]["reference"].get("warning_signs_text_ref")] if r}
    out["texts"] = [t for t in seed["texts"] if t["key"] in kept]
    out["judge"] = {"advice_tier": {"response_only": True, "contextual": True}, "outcome_dimensions": [],
                    "supplied_contexts": []}
    out["notes"] = (f"EXPLORATORY adaptive-auditor copy of {seed['seed_id']} (owner-authorized 2026-09-25, "
                    "docs/petri_adaptive_design.md): turn 1 is the arm's own stimulus; turns 2..N are written by the "
                    "auditor model from the arm's scripted turns as an agenda.")
    return out


def adaptive_seed_file(source: dict, *, wave: int = 2) -> dict:
    """The adaptive seed file derived from a scripted seed file: its schema unchanged, one adaptive seed per
    unbranched scripted seed of `wave`, in file order."""
    seeds = [adaptive_seed(s) for s in source["seeds"]
             if s["pilot_wave"] == wave and s["seed_id"].startswith(SOURCE_PREFIX) and s["mode"] == "scripted"
             and not s["protocol"]["branches"]]
    if not seeds:
        raise ValueError(f"no unbranched scripted wave-{wave} seed to derive from")
    return {"schema_version": source["schema_version"], "status": source["status"],
            "_readme": ("EXPLORATORY adaptive-auditor seeds, derived by `python -m scripts.petri_audit.cli "
                        "build-adaptive-seeds` from docs/framework/petri_seeds.draft.json (docs/petri_adaptive_design.md). "
                        "Never claim-grade; never edit by hand: rebuild and diff."),
            "seed_schema": source["seed_schema"], "seeds": seeds}


def visible_turns(turns: list[dict]) -> list[tuple[str, str]]:
    """What the person saw of a transcript: their own turns and the assistant's non-empty text, in order; tool calls
    and tool results are not shown. The controller builds the same list as the conversation runs."""
    return [(t["role"], t.get("text") or "") for t in turns
            if t["role"] == "user" or (t["role"] == "assistant" and (t.get("text") or "").strip())]


def expected_auditor_requests(prompt: dict, turns: list[dict], total: int) -> list[str]:
    """The request each auditor call must have been sent, recomputed from a transcript record: for every user turn n
    from 2 on, the conversation the person had seen before it, rendered under `render_turn_request(.., n, total)`."""
    out: list[str] = []
    seen: list[tuple[str, str]] = []
    n = 0
    for role, text in visible_turns(turns):
        if role == "user":
            n += 1
            if n >= 2:
                out.append(render_turn_request(prompt, render_conversation(prompt, seen), n, total))
        seen.append((role, text))
    return out


def auditor_request_problems(prompt: dict, turns: list[dict], events: list[Any], total: int, *, where: str) -> list[str]:
    """Each way the auditor calls of a sample differ from what the controller must have sent them, recomputed from the
    record (Codex review of PR #50: only the system message was checked, so a stale or malformed request could stand
    behind a passing stimulus check): one call per auditor-written turn, each sent exactly the rendered request, plus
    at most one further call whose answer was not staged (the conversation then stops at a recorded limit and the
    tree is refused). Duck-typed on `input` (messages with `role` and `text`)."""
    import hashlib as _h

    def digest(text: str | None) -> str | None:
        return None if text is None else _h.sha256(text.encode("utf-8")).hexdigest()

    expected = expected_auditor_requests(prompt, turns, total)
    sent = [next((m.text for m in getattr(e, "input", []) or [] if getattr(m, "role", None) == "user"), None)
            for e in events]
    if len(sent) < len(expected):
        return [f"{where}: {len(expected)} auditor-written turn(s) but {len(sent)} auditor call(s)"]
    if len(sent) > len(expected) + 1:
        return [f"{where}: {len(sent)} auditor calls for {len(expected)} auditor-written turn(s)"]
    for n, (want, got) in enumerate(zip(expected, sent), 2):
        if digest(got) != digest(want):
            return [f"{where}: the auditor call for user turn {n} was not sent the conversation the person had seen"]
    return []


def auditor_texts_from_events(events: list[Any]) -> list[str | None]:
    """The auditor's answers in call order, from a sample's model events (duck-typed: `role`, `output`), each under
    `auditor_answer`, so an unfinished answer is None exactly where the controller stopped."""
    return [auditor_answer(getattr(e, "output", None)) for e in events if getattr(e, "role", None) == "auditor"]
