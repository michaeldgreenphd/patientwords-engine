"""Pure contract-check helpers for the adapter (design memo section 9), kept
free of Inspect imports so the engine's 3.11 suite can test every verdict the
3.12-only adapter records. Nothing here reads a log: the adapter extracts the
facts and these functions turn them into problems (an empty list is a pass).

Added after the first Codex review of the lane (PR #26, 2026-09-16): the
stimulus check compares each record with the exact text sequence its
condition and branch declare, never with the seed's whole text pool; the
coverage check compares the log against the seeds the task selected, so a
seed missing from a truncated log is refused rather than unseen; and the
eligibility rule accepts `not_applicable` beside `pass`, so a run whose
seeds declare no tools is not barred from claim grade by a check that had
nothing to examine.
"""
from __future__ import annotations

import re
from typing import Any

from .framework import sha256_text
from .seeds import ROOT_BRANCH, SeedSet, conditions, text_of  # noqa: F401 - ROOT_BRANCH re-exported

ELIGIBLE_STATUSES = ("pass", "not_applicable")


def _branch(seed: dict, branch_id: str) -> dict:
    branch = next((b for b in seed["protocol"]["branches"] if b["id"] == branch_id), None)
    if branch is None:
        raise KeyError(f"{seed['seed_id']}: branch {branch_id!r} is not declared")
    return branch


def expected_stimuli(seed: dict, cond: dict, branch_id: str) -> list[tuple[str, str]]:
    """The (role, text) sequence a record of this condition and branch must
    carry, in order: the condition's system text if any, then the arm's user
    turns (all of them on the root; up to the anchor on a branch), then the
    branch's own turns."""
    out: list[tuple[str, str]] = []
    if cond["system_text_ref"]:
        out.append(("system", text_of(seed, cond["system_text_ref"])))
    arm_turns = list(cond["turns"])
    if branch_id == ROOT_BRANCH:
        out.extend(("user", text_of(seed, t["text_ref"])) for t in arm_turns)
        return out
    anchor = seed["protocol"]["branch_anchor"]
    branch = _branch(seed, branch_id)
    if anchor is None:
        raise KeyError(f"{seed['seed_id']}: branch {branch_id!r} declared without a branch_anchor")
    out.extend(("user", text_of(seed, t["text_ref"])) for t in arm_turns[: anchor["after_arm_turn"]])
    out.extend(("user", text_of(seed, t["text_ref"])) for t in branch["turns"])
    return out


def branch_staged_texts(seed: dict, cond: dict, branch_id: str) -> list[tuple[str, str]]:
    """The part of `expected_stimuli` the controller stages under this branch
    id: the root stages the system text and the whole arm; a branch stages
    only its own turns (the prefix is Petri's replay, not a staging)."""
    if branch_id == ROOT_BRANCH:
        return expected_stimuli(seed, cond, ROOT_BRANCH)
    return [("user", text_of(seed, t["text_ref"])) for t in _branch(seed, branch_id)["turns"]]


def condition_text_pool(seed: dict, cond: dict) -> set[str]:
    """sha256 of every text this condition may legitimately send the target
    across all of its branches: the raw-request check is per sample, and a
    sample holds every branch of the tree, so the pool is the condition's,
    not the seed's."""
    shas: set[str] = set()
    if cond["system_text_ref"]:
        shas.add(sha256_text(text_of(seed, cond["system_text_ref"])))
    shas.update(sha256_text(text_of(seed, t["text_ref"])) for t in cond["turns"])
    for branch in seed["protocol"]["branches"]:
        shas.update(sha256_text(text_of(seed, t["text_ref"])) for t in branch["turns"])
    return shas


def stimulus_problems(expected: list[tuple[str, str]], turns: list[dict], *, where: str) -> list[str]:
    """The record's user and system turns, in order, against the declared
    sequence: count, role and text must all agree."""
    got = [(t["role"], t["text"]) for t in turns if t["role"] in ("user", "system")]
    problems: list[str] = []
    if len(got) != len(expected):
        problems.append(f"{where}: {len(got)} staged user/system turn(s) in the record, "
                        f"{len(expected)} declared for this condition and branch")
    for i, (exp, act) in enumerate(zip(expected, got), 1):
        if exp[0] != act[0]:
            problems.append(f"{where}: staged turn {i} is a {act[0]} message, expected {exp[0]}")
        elif exp[1] != act[1]:
            problems.append(f"{where}: staged {exp[0]} turn {i} is not the text declared for this condition and branch")
    return problems


def staging_problems(expected: list[tuple[str, str]], staged_shas: list[str], *, where: str) -> list[str]:
    """The controller's staging records for one branch (sha256 per staged
    user/system text, in order) against the texts it should have staged."""
    want = [sha256_text(text) for _role, text in expected]
    if staged_shas != want:
        return [f"{where}: the controller's staging records ({len(staged_shas)}) do not match the "
                f"{len(want)} text(s) declared for this branch"]
    return []


def coverage_problems(seed_set: SeedSet, selected_seed_ids: list[str] | None, seen_counts: dict[str, dict[str, int]],
                      epochs: int) -> list[str]:
    """Every seed the task selected must appear with every declared condition,
    each exactly `epochs` times; a seed the log carries but the task did not
    select is reported too. `selected_seed_ids` None means the log's task
    metadata names none, which is itself a problem: coverage cannot be
    established from the surviving samples alone."""
    problems: list[str] = []
    if selected_seed_ids is None:
        problems.append("the log's task metadata names no selected seed ids; coverage cannot be established")
        selected = sorted(seen_counts)
    else:
        selected = list(selected_seed_ids)
    for seed_id in selected:
        seed = seed_set.seeds.get(seed_id)
        if seed is None:
            problems.append(f"{seed_id}: selected by the task but not in the seed file")
            continue
        want = {c["condition_id"] for c in conditions(seed)}
        seen = seen_counts.get(seed_id, {})
        missing = sorted(want - set(seen))
        extra = sorted(set(seen) - want)
        if missing:
            problems.append(f"{seed_id}: condition(s) absent from the log: {missing}")
        if extra:
            problems.append(f"{seed_id}: condition(s) not declared by the seed: {extra}")
        short = {c: n for c, n in sorted(seen.items()) if c in want and n != epochs}
        if short:
            problems.append(f"{seed_id}: samples per condition {short} differ from epochs {epochs}")
    for seed_id in sorted(set(seen_counts) - set(selected)):
        problems.append(f"{seed_id}: present in the log but not among the seeds the task selected")
    return problems


def claim_grade_eligible(contract_checks: dict[str, dict], refused: int,
                         seeds_declared: list[bool] | None = None) -> bool:
    """Every check passed or had nothing to examine, no record was refused,
    and every seed the run used declares itself claim-grade eligible: a
    scripted seed marked exploratory by its author is never promoted by the
    runtime checks passing (Codex round 4)."""
    checks_ok = all(c["status"] in ELIGIBLE_STATUSES for c in contract_checks.values())
    seeds_ok = all(bool(x) for x in (seeds_declared if seeds_declared is not None else [True]))
    return checks_ok and refused == 0 and seeds_ok


# ------------------------------------------------- raw provider requests (Codex round 2)


def _block_text(content: Any) -> str | None:
    """Text of a message content value: a string, or the text blocks of a list
    (Inspect's ChatMessage dumps, Anthropic content blocks, OpenAI input_text
    parts, Google parts). None when the content carries no text at all (a
    tool-result-only user message), so the caller can skip it."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        saw_text = False
        for block in content:
            if not isinstance(block, dict):
                continue
            if isinstance(block.get("text"), str) and block.get("type") in (None, "text", "input_text", "output_text"):
                texts.append(block["text"])
                saw_text = True
        return "".join(texts) if saw_text else None
    return None


def request_stimuli(request: dict) -> list[tuple[str, str]] | None:
    """The (role, text) sequence of system and user text a raw provider request
    carries, in order, for the request shapes the lane can meet: Inspect's
    mockllm (`messages` of ChatMessage dumps), Anthropic (`system` plus
    `messages`), OpenAI-compatible (`messages` with system/developer/user
    roles) and Google (`contents` plus a system instruction). Tool-result-only
    user messages and every assistant/tool message are skipped: those are
    checked through the staging records. None when the shape is not one of
    these, so the caller records the request as unprovable rather than clean."""
    if not isinstance(request, dict):
        return None
    out: list[tuple[str, str]] = []
    if isinstance(request.get("messages"), list):
        system = request.get("system")
        if system is not None:
            text = _block_text(system)
            if text is None:
                return None
            out.append(("system", text))
        for m in request["messages"]:
            if not isinstance(m, dict):
                return None
            role = m.get("role")
            if role in ("system", "developer"):
                text = _block_text(m.get("content"))
                if text is None:
                    return None
                out.append(("system", text))
            elif role == "user":
                text = _block_text(m.get("content"))
                if text is not None:
                    out.append(("user", text))
            elif role in ("assistant", "tool"):
                continue
            else:
                return None
        return out
    if isinstance(request.get("contents"), list):
        instruction = request.get("system_instruction", request.get("systemInstruction"))
        if instruction is None and isinstance(request.get("config"), dict):
            instruction = request["config"].get("system_instruction", request["config"].get("systemInstruction"))
        if instruction is not None:
            text = instruction if isinstance(instruction, str) else _block_text(
                instruction.get("parts") if isinstance(instruction, dict) else instruction)
            if text is None:
                return None
            out.append(("system", text))
        for c in request["contents"]:
            if not isinstance(c, dict):
                return None
            role = c.get("role", "user")
            if role == "user":
                text = _block_text(c.get("parts"))
                if text is not None:
                    out.append(("user", text))
            elif role == "model":
                continue
            else:
                return None
        return out
    return None


def request_prefix_problems(sequence: list[tuple[str, str]] | None, seed: dict, cond: dict, *, where: str) -> list[str]:
    """A raw request's system/user sequence must be a non-empty prefix of the
    exact sequence some branch of this condition declares (the root, or any
    declared branch); duplicated, omitted, reordered, wrong-branch or foreign
    texts all fail, and an unrecognised request shape fails by name."""
    if sequence is None:
        return [f"{where}: a raw request has a shape the adapter cannot read; its stimuli are unprovable"]
    if not sequence:
        return [f"{where}: a raw request carries no system or user text"]
    branch_ids = [ROOT_BRANCH] + [b["id"] for b in seed["protocol"]["branches"]]
    for branch_id in branch_ids:
        expected = expected_stimuli(seed, cond, branch_id)
        if len(expected) >= len(sequence) and expected[: len(sequence)] == sequence:
            return []
    return [f"{where}: a raw request's {len(sequence)} system/user text(s) are not a prefix of any branch declared for "
            f"this condition"]


# ------------------------------------------------------- branches and seeds


def declared_branch_ids(seed: dict) -> list[str]:
    return [ROOT_BRANCH] + [b["id"] for b in seed["protocol"]["branches"]]


def missing_branch_refusals(seed: dict, exported_branch_ids: list[str], *, where: str) -> list[dict]:
    """Every branch the seed declares must have been exported from the tree;
    an absent one is a refusal entry (branch_id, reason), never a silently
    smaller tree."""
    exported = set(exported_branch_ids)
    return [{"branch_id": f"{where}:{bid}", "reason": "declared branch absent from the timeline"}
            for bid in declared_branch_ids(seed) if bid not in exported]


def seed_drift_problems(manifest_seeds: list[dict], seed_set: SeedSet) -> list[str]:
    """The seeds a manifest recorded (id and digest) against the seed file in
    hand: a seed that changed since the run must not be used to interpret,
    judge or analyse it."""
    from .seeds import seed_digest

    problems: list[str] = []
    for entry in manifest_seeds:
        seed = seed_set.seeds.get(entry["seed_id"])
        if seed is None:
            problems.append(f"{entry['seed_id']}: recorded by the run but absent from {seed_set.path.name}")
        elif seed_digest(seed) != entry["seed_sha256"]:
            problems.append(f"{entry['seed_id']}: the seed in {seed_set.path.name} differs from the one the run recorded "
                            f"({entry['seed_sha256'][:12]}); use the seed file of record")
    return problems


# ------------------------------------------------ generation settings and turn limits (Codex round 3)

MAX_TOOL_ROUNDS_PER_TURN = 4
"""Protocol constant: how many rounds of tool calls the controller answers
within one user exchange before it stops resuming the target. A trajectory
that hits it is truncated and refused; the value is recorded in every
manifest (`execution.max_tool_rounds_per_turn`)."""

_GENERATION_NAMES = {
    "temperature": ("temperature",),
    "max_tokens": ("max_tokens", "max_completion_tokens", "max_output_tokens", "maxOutputTokens"),
    "seed": ("seed",),
}


def request_generation(request: Any) -> dict[str, Any]:
    """The sampling settings a raw request carries, normalised across provider
    shapes: `temperature`, `max_tokens` (any of the provider spellings) and
    `seed`, read from the top level (Anthropic, OpenAI-compatible, mockllm) or
    from a nested Google `generation_config` / `generationConfig` / `config`
    block. None for a setting the request does not carry."""
    out: dict[str, Any] = {"temperature": None, "max_tokens": None, "seed": None}
    if not isinstance(request, dict):
        return out
    layers = [request] + [request[k] for k in ("generation_config", "generationConfig", "config")
                          if isinstance(request.get(k), dict)]
    for field, names in _GENERATION_NAMES.items():
        for layer in layers:
            found = next((layer[n] for n in names if layer.get(n) is not None), None)
            if found is not None:
                out[field] = found
                break
    return out


def generation_problems(expected: dict, request: Any, *, forwards_seed: bool | None) -> list[str]:
    """The seed's generation block against one raw request: temperature and
    max_tokens must be sent (and equal when the seed sets them); the requested
    seed must be sent and equal when the provider forwards seeds, while a
    provider that never forwards them is not asked (the manifest records
    `seed_forwarded_by_provider`)."""
    got = request_generation(request)
    problems: list[str] = []
    for field in ("temperature", "max_tokens"):
        want = expected.get(field)
        if got[field] is None:
            problems.append(f"{field}: not_sent")
        elif want is not None and got[field] != want:
            problems.append(f"{field}: sent {got[field]!r}, seed {want!r}")
    want_seed = expected.get("seed_requested")
    if want_seed is not None and forwards_seed:
        if got["seed"] is None:
            problems.append("seed: not_sent although the provider forwards seeds")
        elif got["seed"] != want_seed:
            problems.append(f"seed: sent {got['seed']!r}, seed {want_seed!r}")
    return problems


# ------------------------------------------------ how each target reply ended (2026-09-23)

TRUNCATING_STOP_REASONS = ("max_tokens", "model_length", "content_filter")
"""Inspect `StopReason` values (inspect_ai/model/_model_output.py in the locked 0.3.237) under which a reply is
not the model's whole answer: cut at the output cap (OpenAI-shaped `finish_reason: length` maps to max_tokens),
a prompt the provider rejected as longer than its context window (model_length: Inspect substitutes the
provider's error text for the reply, `handle_bad_request` in anthropic.py and openai_compatible.py), or withheld
by a provider filter. A reasoning model whose hidden reasoning counts against `max_tokens` ends here with little
or no visible text, which rules and the judge would otherwise score as its answer."""

CLEAN_STOP_REASONS = ("stop", "tool_calls")
"""The only endings under which a reply is admitted: the model ended its turn, or ended it on a tool call. Every
other value is refused, `unknown` included (2026-09-23 review: it was recorded and admitted, and a partial reply
was exported as a claim-grade answer). Inspect's `as_stop_reason` maps any finish_reason it does not know to
`unknown`, which covers OpenRouter's documented `error` (a generation that failed upstream, possibly after
partial text; OpenRouter's `on_response` raises only on a top-level error, and the openai SDK builds a response
without validating it) and a null finish_reason. The direct Anthropic provider maps
`model_context_window_exceeded`, a reply cut at the context window, to `unknown` too (`message_stop_reason`;
`pause_turn` is resumed by the provider and never returned). No landed run recorded one: the three Anthropic
runs' logs hold only stop and tool_calls."""


def reply_problems(turns: list[dict], stop_reasons: dict[int, str | None], *, where: str) -> list[str]:
    """Each assistant turn of a record against how the target call that
    produced it ended (`stop_reasons`: turn_id -> Inspect stop reason, None
    when no retained call produced that message). A turn with no recorded
    ending cannot be shown complete and is a problem, never assumed clean; so
    is any ending outside CLEAN_STOP_REASONS, a truncating one named as such
    and any other (`unknown`) as an ending Inspect could not map; so is a
    reply with neither text nor a tool call (a tool-call turn carries no text
    legitimately)."""
    problems: list[str] = []
    for t in turns:
        if t["role"] != "assistant":
            continue
        tid = t["turn_id"]
        reason = stop_reasons.get(tid)
        if reason is None:
            problems.append(f"{where}: assistant turn {tid} has no target call recording how it ended; the reply "
                            "cannot be shown to be complete")
        elif reason in TRUNCATING_STOP_REASONS:
            problems.append(f"{where}: assistant turn {tid} ended on stop_reason {reason!r}; a reply cut at a limit or "
                            "withheld by a filter is not the model's answer")
        elif reason not in CLEAN_STOP_REASONS:
            problems.append(f"{where}: assistant turn {tid} ended on stop_reason {reason!r}, an ending Inspect could not "
                            "map (OpenRouter's finish_reason error or null, Anthropic's context-window stop); the reply "
                            "cannot be shown to be complete")
        elif not (t.get("text") or "").strip() and not t.get("tool_calls"):
            problems.append(f"{where}: assistant turn {tid} is empty (no text and no tool call, stop_reason {reason!r})")
    return problems


def uncarried_ending_refusal(endings: list[tuple[str | None, str]], carried: set[str], *, where: str) -> dict | None:
    """The refusal for a tree in which a target call ended outside
    CLEAN_STOP_REASONS with a reply no branch of the tree carries (`endings`:
    one (id of the assistant message the call produced, or None when it
    produced none; stop reason) per call; `carried`: every message id on the
    tree's timeline). reply_problems refuses a branch that carries such a
    reply; one that no branch carries would be counted in
    models.target.stop_reasons and refuse nothing, so a claim-grade manifest
    could sit over it (2026-09-23 review). In the offline mock runs, tool
    loops and replayed prefixes included, every call's reply is on the
    timeline, so this guards an invariant of the controller rather than a
    case seen; the tree is refused as a whole, as a sample error is. None
    when no such call exists."""
    stray = [reason for mid, reason in endings if reason not in CLEAN_STOP_REASONS and (mid is None or mid not in carried)]
    if not stray:
        return None
    return {"branch_id": f"{where}:{ROOT_BRANCH}",
            "reason": f"{len(stray)} target call(s) ended on stop_reason {sorted(set(stray))} with a reply no branch of "
                      "the tree carries, so no branch can be checked against that ending"}


def sample_limit_refusal(limit: Any, *, where: str) -> dict | None:
    """The refusal for a sample Inspect halted at one of its own limits
    (`EvalSample.limit`, an `EvalSampleLimit` with `type` and `limit`, set by
    the run loop on `LimitExceededError` with no sample error: _eval/task/run.py
    in the locked 0.3.237). Every branch of such a tree may stop mid-exchange,
    so the tree is refused as a whole, as a sample error is; None when the
    sample ran to its end. Duck-typed so the 3.11 suite can test it."""
    if limit is None:
        return None
    kind = getattr(limit, "type", None) if not isinstance(limit, dict) else limit.get("type")
    value = getattr(limit, "limit", None) if not isinstance(limit, dict) else limit.get("limit")
    return {"branch_id": f"{where}:{ROOT_BRANCH}",
            "reason": f"sample halted by Inspect's {kind} limit ({value}); every branch of the tree may end mid-exchange"}


def tool_results_verdict(results_by_seed: dict[str, int]) -> tuple[str, str]:
    """The `tool_results_from_data` verdict from the number of tool-result
    turns the adapter examined per tool-declaring seed (seeds without tools
    absent). A tool seed whose target never called a tool leaves nothing to
    examine: whether the target calls a tool is the measured outcome
    (`tool_invoked`, design memo H3), not a contract requirement, so the check
    is not_applicable, with the seeds named, rather than a pass over zero
    results (2026-09-23: a target without native tool use passed it vacuously).
    A pass names how many results it examined and any tool seed that produced
    none. A failure the adapter recorded is never overwritten (the caller only
    fills a check still `not_run`)."""
    if not results_by_seed:
        return "not_applicable", "no tools declared by this run's seeds"
    total = sum(results_by_seed.values())
    if total == 0:
        return "not_applicable", (f"tools declared by {', '.join(sorted(results_by_seed))}, but no examined record carries a "
                                  "tool result (the target made no tool call): nothing to examine; tool_invoked records "
                                  "the behaviour")
    silent = sorted(s for s, n in results_by_seed.items() if n == 0)
    return "pass", (f"every tool result matches the seed's results table ({total} tool-result turn(s) examined across "
                    "records" + (f"; none from {', '.join(silent)})" if silent else ")"))


# ------------------------------------------------ OpenRouter's upstream host (2026-09-23)

_UPSTREAM_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()+/-]{0,63}$")


def upstream_provider_name(response: Any) -> str | None:
    """The upstream host OpenRouter names in a retained raw response (its
    top-level `provider` field: "OpenAI", "Azure", "DeepInfra", ...), or None
    when no response was retained or it carries no short plain name. OpenRouter
    routes one model slug to several hosts (the advice lane saw gpt-5.4-mini on
    OpenAI and on Azure), and the field survives only inside the raw ModelEvent
    `call`, which the sanitiser forbids in every published file. The adapter
    copies this one string out before sanitising; nothing else of the raw
    response leaves it, and a value that is not a plain name is not copied."""
    if not isinstance(response, dict):
        return None
    name = response.get("provider")
    if not isinstance(name, str):
        return None
    name = name.strip()
    return name if _UPSTREAM_NAME.match(name) else None


def exchange_limit_problems(seed: dict) -> list[str]:
    """Every root-to-leaf trajectory a seed declares must fit its
    `max_target_turns` (user exchanges: the arm's turns, or the anchored
    prefix plus a branch's turns)."""
    proto = seed["protocol"]
    limit = proto["max_target_turns"]
    problems: list[str] = []
    for arm in proto["arms"]:
        if len(arm["turns"]) > limit:
            problems.append(f"arm {arm['id']!r} declares {len(arm['turns'])} user turns, above max_target_turns {limit}")
    anchor = proto.get("branch_anchor")
    if anchor is not None:
        for branch in proto["branches"]:
            n = anchor["after_arm_turn"] + len(branch["turns"])
            if n > limit:
                problems.append(f"branch {branch['id']!r} reaches {n} user turns with its prefix, above max_target_turns {limit}")
    return problems


def exchange_problems(turns: list[dict], max_target_turns: int, max_tool_rounds: int = MAX_TOOL_ROUNDS_PER_TURN,
                      *, where: str) -> list[str]:
    """A record's realised trajectory against the protocol limits: assistant
    replies that close an exchange (no tool calls) must not exceed
    `max_target_turns`, and the tool-call replies inside any one exchange must
    not exceed `max_tool_rounds`."""
    problems: list[str] = []
    exchanges = 0
    rounds = 0
    for t in turns:
        if t["role"] == "user":
            rounds = 0
        elif t["role"] == "assistant":
            if t.get("tool_calls"):
                rounds += 1
                if rounds > max_tool_rounds:
                    problems.append(f"{where}: {rounds} tool-call rounds in one exchange, above the limit of {max_tool_rounds}")
                    break
            else:
                exchanges += 1
    if exchanges > max_target_turns:
        problems.append(f"{where}: {exchanges} target replies, above max_target_turns {max_target_turns}")
    return problems

