"""Seed loading and validation (docs/framework/petri_seeds.draft.json, design
memo section 5). A seed is data the scripted controller executes verbatim; this
module is the only place that interprets its structure, so the controller, the
adapter and the tests agree on what an arm, a branch, a tool result and a
supplied context are.

The semantic checks (`seed_problems`) lived in tests/test_petri_framework_data.py
until 2026-09-16 and moved here so the CLI's `validate-seeds` and the run's
pre-flight refuse the same seeds the tests refuse.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .framework import (
    FRAMING_REGISTRY,
    OUTCOME_REGISTRY,
    SEED_FILE,
    canonical_json,
    load_json,
    sha256_text,
    validate,
)

QUERY_PLACEHOLDER = "<query>"


@dataclass(frozen=True)
class SeedSet:
    """A loaded seed file: its schema, its seeds by id, and the registries the
    semantic checks need."""

    path: Path
    schema: dict
    seeds: dict[str, dict]
    framing: dict
    outcomes: dict
    file_sha256: str


def load_seed_file(path: Path | str = SEED_FILE, *, framing_path: Path | str = FRAMING_REGISTRY,
                   outcomes_path: Path | str = OUTCOME_REGISTRY) -> SeedSet:
    path = Path(path)
    doc = load_json(path)
    seeds = {s["seed_id"]: s for s in doc["seeds"]}
    if len(seeds) != len(doc["seeds"]):
        raise ValueError(f"{path}: duplicate seed ids")
    return SeedSet(path=path, schema=doc["seed_schema"], seeds=seeds, framing=load_json(framing_path),
                   outcomes=load_json(outcomes_path), file_sha256=sha256_text(path.read_text(encoding="utf-8")))


def seed_digest(seed: dict) -> str:
    """sha256 of the seed's canonical JSON: the identity the manifest records."""
    return sha256_text(canonical_json(seed))


def select_seeds(seed_set: SeedSet, seed_ids: list[str] | None = None, wave: int | None = None) -> list[dict]:
    """The seeds a run executes, in file order; an unknown id is an error, never
    silently skipped, and an empty selection is an error, never a clear
    pre-flight with zero samples."""
    if seed_ids:
        missing = [s for s in seed_ids if s not in seed_set.seeds]
        if missing:
            raise ValueError(f"unknown seed id(s) {missing}; known: {sorted(seed_set.seeds)}")
        chosen = [seed_set.seeds[s] for s in seed_ids]
    else:
        chosen = list(seed_set.seeds.values())
    if wave is not None:
        chosen = [s for s in chosen if s["pilot_wave"] == wave]
    if not chosen:
        selector = (f"seed ids {list(seed_ids)}" if seed_ids else "every seed") + (f" in wave {wave}" if wave is not None else "")
        raise ValueError(f"{selector} selects no seed from {seed_set.path.name}; an empty run is refused, not reported clear")
    return chosen


def texts_by_key(seed: dict) -> dict[str, dict]:
    return {t["key"]: t for t in seed["texts"]}


ROOT_BRANCH = "root"       # the adapter's reserved id for the root trajectory; a seed may not declare a branch with it


def _string_leaves(obj: Any) -> list[str]:
    """Every string in a JSON value: leaves and dictionary keys alike, since a
    JSON-schema property name is a key and reaches the target as text (Codex
    round 9)."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in ([k] if isinstance(k, str) else []) + _string_leaves(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _string_leaves(v)]
    return []


def target_visible_strings(seed: dict) -> list[str]:
    """Every string the target can receive from a seed: the texts, and every
    string leaf of the tool definitions (name, description, parameter schema),
    which the task forwards verbatim (Codex round 8: the holdout seal scan
    read the texts alone, so a sealed phrase in a tool description would have
    reached the target)."""
    out = [t["text"] for t in seed["texts"]]
    for d in (seed.get("tools") or {}).get("definitions", []):
        out.extend(_string_leaves(d))
    return out


def text_of(seed: dict, key: str) -> str:
    texts = texts_by_key(seed)
    if key not in texts:
        raise KeyError(f"{seed['seed_id']}: text_ref {key!r} does not resolve")
    return texts[key]["text"]


def conditions(seed: dict) -> list[dict]:
    """The root-level conditions a seed expands to: one per (arm, system-prompt
    variant), each a Sample in the run. `variant_id` is None when the seed has
    no variants."""
    out: list[dict] = []
    sp = seed["system_prompt"]
    variants: list[dict | None] = list(sp["variants"]) if sp["policy"] == "variants" else [None]
    for arm in seed["protocol"]["arms"]:
        for variant in variants:
            system_ref = sp["text_ref"] if sp["policy"] == "fixed" else (variant["text_ref"] if variant else None)
            out.append({
                "seed_id": seed["seed_id"],
                "arm_id": arm["id"],
                "variant_id": variant["id"] if variant else None,
                "condition_id": arm["id"] if variant is None else f"{arm['id']}__{variant['id']}",
                "user_is": arm["user_is"],
                "system_text_ref": system_ref,
                "turns": list(arm["turns"]),
            })
    return out


def tool_result_for(seed: dict, tool_name: str, arguments: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(result text, marker, substituted query) for a tool call, from the
    seed's results table only. The literal `<query>` in the template is
    replaced by the call's `query` argument when the call carries one, and the
    substitution is returned so the adapter can recompute the staged text from
    the template and the recorded arguments. None when the tool is not defined
    in the seed: the caller stages an error result and counts it."""
    tools = seed.get("tools")
    if not tools:
        return None, None, None
    entry = next((r for r in tools["results"] if r["tool"] == tool_name), None)
    if entry is None:
        return None, None, None
    template = text_of(seed, entry["text_ref"])
    query = arguments.get("query")
    if QUERY_PLACEHOLDER in template and isinstance(query, str):
        return template.replace(QUERY_PLACEHOLDER, query), entry.get("marker"), query
    return template, entry.get("marker"), None


def validate_seed(seed: dict, seed_set: SeedSet) -> list[str]:
    """Schema problems followed by semantic problems; empty when the seed may run."""
    problems = validate(seed, seed_set.schema)
    if problems:
        return problems
    return seed_problems(seed, seed_set.framing, seed_set.outcomes)


def seed_problems(seed: dict, framing: dict, outcomes: dict) -> list[str]:
    """The checks the schema cannot express, mirroring the transcript importer's
    semantic checks: every text reference resolves, every digest matches its
    text, the framing contrast and the outcome dimensions are declared in the
    registries, arm texts carry the registers the contrast declares, register
    exposure follows its declared protocol, speaker identity is constant unless
    declared a factor and crossed with register, branch structure is coherent,
    supplied contexts exist
    for the dimensions that need them, and a seed is claim-grade eligible only
    when scripted."""
    problems: list[str] = []
    keys = [t["key"] for t in seed["texts"]]
    if len(keys) != len(set(keys)):
        problems.append("duplicate text keys")
    texts = {t["key"]: t for t in seed["texts"]}
    for key, entry in texts.items():
        if entry["sha256"] != sha256_text(entry["text"]):
            problems.append(f"text {key!r}: sha256 does not match the text")

    def ref(name: str, where: str) -> dict | None:
        if name not in texts:
            problems.append(f"{where}: text_ref {name!r} does not resolve")
            return None
        return texts[name]

    proto = seed["protocol"]
    arm_ids = [a["id"] for a in proto["arms"]]
    if len(arm_ids) != len(set(arm_ids)):
        problems.append("duplicate arm ids")
    arms = {a["id"]: a for a in proto["arms"]}
    branch_ids = [b["id"] for b in proto["branches"]]
    if len(branch_ids) != len(set(branch_ids)):
        problems.append("duplicate branch ids")
    if ROOT_BRANCH in branch_ids:
        # the root and a branch named root would share a conversation id (Codex round 8)
        problems.append(f"branch id {ROOT_BRANCH!r} is reserved for the root trajectory")
    # the derived condition id joins arm and variant ids with '__', which is not injective when the ids themselves
    # carry '__'; two conditions with one id would share a sample id and be conflated after the target spent
    # (Codex round 9)
    cond_ids = [c["condition_id"] for c in conditions(seed)]
    for dup in sorted({c for c in cond_ids if cond_ids.count(c) > 1}):
        problems.append(f"derived condition id {dup!r} collides: arm and variant ids joined by '__' must stay distinct")
    branches = {b["id"]: b for b in proto["branches"]}

    speakers = {a["user_is"] for a in proto["arms"]}
    policy = seed["speaker_identity"]["policy"]
    if policy == "constant" and len(speakers) > 1:
        problems.append(f"speaker_identity is constant but arms declare user_is {sorted(speakers)}: register must not "
                        f"change who is speaking")
    if policy == "factor" and not seed["speaker_identity"].get("note"):
        problems.append("speaker_identity declared a factor without a note justifying it")
    if policy == "factor" and len(speakers) < 2:
        # a note plus one identity is a declaration with nothing behind it, and it reads downstream as a crossed
        # design that was never run
        problems.append(f"speaker_identity is declared a factor but every arm declares user_is {sorted(speakers)[0]!r}: "
                        f"a factor that does not vary is not a factor")

    dim = next((d for d in framing["dimensions"] if d["id"] == seed["framing"]["dimension_id"]), None)
    expected: set[str] | None = None
    if dim is None:
        problems.append(f"framing dimension {seed['framing']['dimension_id']!r} not in the registry")
    else:
        contrast = next((c for c in dim["counterfactual"]["contrasts"] if c["id"] == seed["framing"]["contrast_id"]), None)
        if contrast is None:
            problems.append(f"contrast {seed['framing']['contrast_id']!r} not declared for {dim['id']!r}")
        else:
            expected = {contrast["from"], contrast["to"]}
            first_turn_registers = set()
            by_speaker: dict[str, set[str]] = {}
            for arm, spec in arms.items():
                entry = ref(spec["turns"][0]["text_ref"], f"arm {arm!r} turn 1")
                if entry is not None:
                    first_turn_registers.add(entry["register"])
                    by_speaker.setdefault(spec["user_is"], set()).add(entry["register"])
            if first_turn_registers != expected:
                problems.append(f"arm turn-1 registers {sorted(first_turn_registers)} do not realise the contrast "
                                f"{sorted(expected)}")
            if policy == "factor":
                # A declared factor is not a licence to confound. `constant` refuses a seed whose clinical arm is a
                # clinician and whose colloquial arm is a patient; `factor` with a note would have re-admitted exactly
                # that seed, with the confound written down instead of removed. Crossing is what makes both contrasts
                # estimable: every identity must appear in every register of the contrast.
                for speaker in sorted(by_speaker):
                    if by_speaker[speaker] != expected:
                        problems.append(f"speaker_identity is a declared factor but user_is {speaker!r} appears only "
                                        f"in register(s) {sorted(by_speaker[speaker])}, not {sorted(expected)}: an "
                                        f"identity nested inside one register is the confound the factor exists to "
                                        f"avoid, not a crossed design")
    for arm, spec in arms.items():
        for i, turn in enumerate(spec["turns"], 1):
            ref(turn["text_ref"], f"arm {arm!r} turn {i}")

    exposure = proto["register_exposure"]
    lengths = {len(a["turns"]) for a in proto["arms"]}
    if exposure == "single_turn":
        if lengths != {1} or branches:
            problems.append("single_turn exposure needs exactly one user turn per arm and no branches")
    else:
        if len(lengths) != 1:
            problems.append(f"{exposure} exposure needs the same number of user turns in every arm, got {sorted(lengths)}")
        elif exposure == "initial_only":
            n = next(iter(lengths))
            for i in range(1, n):
                refs = {a["turns"][i]["text_ref"] for a in proto["arms"]}
                if len(refs) != 1:
                    problems.append(f"initial_only exposure: arm turn {i + 1} differs across arms ({sorted(refs)}); "
                                    f"every user turn after the first must be byte-identical")
        elif exposure == "sustained":
            if branches:
                problems.append("sustained exposure with branches is not expressible: branch turns are declared once "
                                "per seed, not per arm")
            n = next(iter(lengths))
            for i in range(1, n):
                regs = set()
                for arm, spec in arms.items():
                    first = texts.get(spec["turns"][0]["text_ref"])
                    later = texts.get(spec["turns"][i]["text_ref"])
                    if first is None or later is None:
                        continue
                    if later["register"] != first["register"]:
                        problems.append(f"sustained exposure: arm {arm!r} turn {i + 1} is {later['register']}, not the "
                                        f"arm's register {first['register']}")
                    regs.add(later["register"])
                if expected is not None and regs != expected:
                    problems.append(f"sustained exposure: arm turn {i + 1} registers {sorted(regs)} do not realise the "
                                    f"contrast {sorted(expected)}")
    anchor = proto["branch_anchor"]
    # every declared trajectory fits max_target_turns (checks.exchange_limit_problems; Codex round 3)
    from .checks import exchange_limit_problems

    problems.extend(exchange_limit_problems(seed))
    if anchor is None and branches:
        problems.append("branches declared without a branch_anchor")
    if anchor is not None and not branches:
        problems.append("branch_anchor declared without branches")
    if anchor is not None:
        for arm, spec in arms.items():
            if anchor["after_arm_turn"] > len(spec["turns"]):
                problems.append(f"branch_anchor after_arm_turn {anchor['after_arm_turn']} exceeds arm {arm!r} turns")
        for cond, spec in branches.items():
            for i, turn in enumerate(spec["turns"], 1):
                ref(turn["text_ref"], f"branch {cond!r} turn {i}")
    sp = seed["system_prompt"]
    if sp["policy"] == "none" and (sp.get("text_ref") or sp.get("variants")):
        problems.append("system_prompt policy none must carry no text")
    if sp["policy"] == "fixed" and not sp.get("text_ref"):
        problems.append("system_prompt policy fixed needs text_ref")
    if sp["policy"] == "variants" and not sp.get("variants"):
        problems.append("system_prompt policy variants needs variants")
    if sp.get("text_ref"):
        ref(sp["text_ref"], "system_prompt")
    variant_ids = [v["id"] for v in sp.get("variants") or []]
    if len(variant_ids) != len(set(variant_ids)):
        problems.append("duplicate system_prompt variant ids")
    for v in sp.get("variants") or []:
        ref(v["text_ref"], f"system_prompt variant {v['id']!r}")
    tools = seed.get("tools")
    if tools:
        names = [t["name"] for t in tools["definitions"]]
        if len(names) != len(set(names)):
            problems.append("duplicate tool names")
        result_names = [r["tool"] for r in tools["results"]]
        if len(result_names) != len(set(result_names)):
            problems.append("duplicate tool results")
        for r in tools["results"]:
            if r["tool"] not in names:
                problems.append(f"tool result for undefined tool {r['tool']!r}")
            ref(r["text_ref"], f"tool result {r['tool']!r}")
        for name in names:
            if name not in result_names:
                problems.append(f"tool {name!r} has no data-supplied result; results are never auditor-authored")
    outcome_ids = {d["id"] for d in outcomes["dimensions"]}
    judged = seed["judge"]["outcome_dimensions"]
    for od in judged:
        if od not in outcome_ids:
            problems.append(f"judge outcome dimension {od!r} not in the outcome registry")
    supplied = {c["dimension_id"]: c for c in seed["judge"]["supplied_contexts"]}
    supplied_ids = [c["dimension_id"] for c in seed["judge"]["supplied_contexts"]]
    for dup in sorted({d for d in supplied_ids if supplied_ids.count(d) > 1}):
        # the planner keys supplied contexts by dimension, so a repeated id would silently keep one entry (Codex round 6)
        problems.append(f"supplied context for {dup!r} is declared {supplied_ids.count(dup)} times; one per dimension")
    for c in seed["judge"]["supplied_contexts"]:
        if c["dimension_id"] not in judged:
            problems.append(f"supplied context for {c['dimension_id']!r}, which the seed does not judge")
        ref(c["text_ref"], f"supplied context {c['dimension_id']!r}")
    # the reference's warning-signs text is read eagerly when judging (Codex round 5: an unresolved reference passed
    # preflight, spent the target budget, and raised before any judgment)
    warning_ref = seed["scenario"]["reference"].get("warning_signs_text_ref")
    if warning_ref:
        ref(warning_ref, "scenario.reference.warning_signs_text_ref")
    if "assertion_handling" in judged and "assertion_handling" not in supplied:
        problems.append("assertion_handling is judged but no proposition is supplied as context")
    if "assertion_handling" in judged:
        # The planner gates the dimension on a preceding turn marked `assertion`, so a seed that judges it without
        # marking one produces nothing but not_applicable rows - a run that passes preflight, spends the target
        # budget and finishes with zero measurements for its declared outcome. Refuse it here, where it costs
        # nothing (Codex round 2 on PR #29).
        trajectories = [(f"arm {a['id']!r}", a["turns"]) for a in proto["arms"]]
        if anchor is not None:
            for arm, spec in arms.items():
                prefix = spec["turns"][: anchor["after_arm_turn"]]
                trajectories += [(f"arm {arm!r} branch {b['id']!r}", prefix + b["turns"]) for b in proto["branches"]]
        bare = [where for where, turns in trajectories
                if not any(t.get("context_role") == "assertion" for t in turns)]
        for where in bare:
            problems.append(f"assertion_handling is judged but {where} marks no turn context_role 'assertion': "
                            f"every reply in it would be recorded not_applicable, so the run would spend the target "
                            f"budget and measure nothing for that dimension")
    if seed["judge"]["advice_tier"]["contextual"] and exposure == "single_turn":
        problems.append("the contextual tier instrument applies to turns after the first; a single_turn seed has none")
    if seed["mode"] == "autonomous":
        if seed["claim_grade_eligible"]:
            problems.append("an autonomous (LLM-auditor) seed is exploratory and cannot be claim-grade eligible")
        if not seed.get("auditor_instruction"):
            problems.append("autonomous mode needs an auditor_instruction")
    else:
        if seed.get("auditor_instruction"):
            problems.append("a scripted seed carries no auditor instruction: nothing but data reaches the target")
    return problems
