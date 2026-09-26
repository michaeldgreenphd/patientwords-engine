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

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .framework import (
    FRAMING_REGISTRY,
    OUTCOME_REGISTRY,
    ROOT,
    SEED_FILE,
    canonical_json,
    load_json,
    sha256_text,
    validate,
)

QUERY_PLACEHOLDER = "<query>"
# The speaker-identity manipulation check's vocabulary: identity clause patterns and waivers, data never Python
# (AGENTS.md hard conventions; owner decision 2026-09-22).
IDENTITY_MARKERS = ROOT / "data" / "petri" / "speaker_identity_markers.draft.json"


def load_identity_markers(path: Path | str = IDENTITY_MARKERS) -> dict:
    """The identity clause patterns and waivers `seed_problems` checks arm texts against."""
    return load_json(path)


def _identity_clauses(text: str, markers: dict) -> set[str]:
    """The identities with at least one clause pattern matching `text`, before the default is dropped."""
    return {identity for identity, spec in markers["identities"].items()
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in spec["patterns"])}


def _without_unmarked_default(found: set[str]) -> set[str]:
    """First-person reference is the unmarked default in English and a clinician or a carer uses it too ('I expect
    this is simply the result of their standing all day'), so `patient` is dropped whenever a clinician or caregiver
    clause is present. Applied to one text, or to the union over an arm's turns: one speaker per arm."""
    return found - {"patient"} if found & {"clinician", "caregiver"} else set(found)


def marked_identities(text: str, markers: dict) -> set[str]:
    """The identities whose clauses `text` carries, per the markers file, with the unmarked default dropped."""
    return _without_unmarked_default(_identity_clauses(text, markers))


def _speaker_identity_text_problems(seed: dict, arms: dict[str, dict], texts: dict[str, dict], policy: str,
                                    by_register: dict[str, str], expected: set[str] | None,
                                    markers: dict | None = None) -> list[str]:
    """The manipulation check on speaker identity (owner decision 2026-09-22, docs/petri_wave2_design.md section 8
    decision 5). `user_is` never reaches the target - the identity cue is whatever the text says - so a declaration
    the wording does not realise is a label, and a declaration the wording contradicts is wave 1's h3-tools
    confound: both arms declared `unknown` while one wrote as a clinician about someone else and the other as the
    patient, and the validator compared only the declarations. Three rules, all on an arm's OWN turn texts (branch
    turns are declared once per seed and carry no identity of their own): an arm declaring a specific identity
    carries no other identity's clause; under the factor policy an arm's text carries the identity it declares; and
    whatever the arms declare, every identity the texts carry appears in every register of the contrast (and of its
    decomposition registers), so identity is crossed with register in the wording, never nested inside it. A waiver
    in the markers file skips one landed seed by name, with its reason."""
    markers = markers if markers is not None else load_identity_markers()
    waived = {w["seed_id"]: w for w in markers.get("waivers", [])}
    if seed["seed_id"] in waived:
        if not waived[seed["seed_id"]].get("reason"):
            return [f"speaker-identity check waived for {seed['seed_id']!r} without a reason"]
        return []
    problems: list[str] = []
    carried: dict[str, set[str]] = {}
    for arm, spec in arms.items():
        clauses: set[str] = set()
        for turn in spec["turns"]:
            entry = texts.get(turn["text_ref"])
            if entry is not None:
                clauses |= _identity_clauses(entry["text"], markers)
        found = _without_unmarked_default(clauses)       # one speaker per arm: a later 'I' is the clinician's
        carried[arm] = found
        declared = spec["user_is"]
        if declared != "unknown" and found - {declared}:
            problems.append(f"arm {arm!r} declares user_is {declared!r} but its text carries "
                            f"{sorted(found - {declared})} identity clauses: the wording contradicts the declaration")
        if policy == "factor" and declared not in found:
            problems.append(f"arm {arm!r} declares user_is {declared!r} as a level of the speaker-identity factor but "
                            f"no turn of its text carries a {declared} clause: a declared identity the wording does "
                            f"not realise is a label the target never sees")
    if expected is not None:
        registers_of: dict[frozenset[str], set[str]] = {}
        for arm, found in carried.items():
            if arm in by_register:
                registers_of.setdefault(frozenset(found), set()).add(by_register[arm])
        for found, regs in sorted(registers_of.items(), key=lambda kv: sorted(kv[0])):
            if regs != expected:
                label = sorted(found) or "no identity clause"
                problems.append(f"the texts carrying {label} appear only in register(s) {sorted(regs)}, not "
                                f"{sorted(expected)}: identity is nested inside register in the wording, whatever "
                                f"the arms declare (the wave-1 h3-tools confound)")
    return problems


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
    by_register: dict[str, str] = {}              # arm id -> its turn-1 register, for the identity check below
    if dim is None:
        problems.append(f"framing dimension {seed['framing']['dimension_id']!r} not in the registry")
    else:
        contrast = next((c for c in dim["counterfactual"]["contrasts"] if c["id"] == seed["framing"]["contrast_id"]), None)
        if contrast is None:
            problems.append(f"contrast {seed['framing']['contrast_id']!r} not declared for {dim['id']!r}")
        else:
            poles = {contrast["from"], contrast["to"]}
            # A decomposition register (owner decision 2026-09-22; docs/petri_wave2_design.md section 3) is an extra
            # arm beside the contrast pair - lay terminology in careful orthography - so that a register effect can
            # be split into terminology and orthography. It must be a value of the same dimension and never a pole
            # of the contrast (an arm repeating a pole is a duplicate, not a decomposition). The registered estimand
            # stays the contrast pair; every check below that asked the arms for the poles now asks for the poles
            # and the decomposition registers together, so a declared third arm that is missing is refused.
            decomposition = list(seed["framing"].get("decomposition_registers") or [])
            if len(decomposition) != len(set(decomposition)):
                problems.append("duplicate decomposition registers")
            for reg in decomposition:
                if reg not in dim["values"]:
                    problems.append(f"decomposition register {reg!r} is not a value of dimension {dim['id']!r}")
                elif reg in poles:
                    problems.append(f"decomposition register {reg!r} is a pole of contrast {contrast['id']!r}, not a "
                                    f"decomposition of it")
            expected = poles | {reg for reg in decomposition if reg in dim["values"] and reg not in poles}
            realised = f" with decomposition registers {sorted(set(decomposition))}" if decomposition else ""
            first_turn_registers = set()
            by_speaker: dict[str, set[str]] = {}
            for arm, spec in arms.items():
                entry = ref(spec["turns"][0]["text_ref"], f"arm {arm!r} turn 1")
                if entry is not None:
                    first_turn_registers.add(entry["register"])
                    by_register[arm] = entry["register"]
                    by_speaker.setdefault(spec["user_is"], set()).add(entry["register"])
            if first_turn_registers != expected:
                problems.append(f"arm turn-1 registers {sorted(first_turn_registers)} do not realise the contrast "
                                f"{sorted(poles)}{realised}")
            if policy == "factor":
                # A declared factor is not a licence to confound. `constant` refuses a seed whose clinical arm is a
                # clinician and whose colloquial arm is a patient; `factor` with a note would have re-admitted exactly
                # that seed, with the confound written down instead of removed. Crossing is what makes both contrasts
                # estimable: every identity must appear in every register of the contrast, decomposition included.
                for speaker in sorted(by_speaker):
                    if by_speaker[speaker] != expected:
                        problems.append(f"speaker_identity is a declared factor but user_is {speaker!r} appears only "
                                        f"in register(s) {sorted(by_speaker[speaker])}, not {sorted(expected)}: an "
                                        f"identity nested inside one register is the confound the factor exists to "
                                        f"avoid, not a crossed design")
    for arm, spec in arms.items():
        for i, turn in enumerate(spec["turns"], 1):
            ref(turn["text_ref"], f"arm {arm!r} turn {i}")
    problems.extend(_speaker_identity_text_problems(seed, arms, texts, policy, by_register, expected))

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
    for i, grounding in enumerate(seed["scenario"].get("grounded_in") or []):
        # provenance as data (owner decision 4, 2026-09-22): an in-repository file must exist; a sibling-checkout
        # path (../patientwords/...) is recorded and not checked, because the workflow checks out this repository alone
        if not grounding["file"].startswith("../") and not (ROOT / grounding["file"]).is_file():
            problems.append(f"scenario.grounded_in[{i}]: file {grounding['file']!r} not found in the repository")
    if "assertion_handling" in judged and "assertion_handling" not in supplied:
        problems.append("assertion_handling is judged but no proposition is supplied as context")
    # A dimension the planner gates on a marked context role measures nothing in a trajectory that marks none.
    # Three things can go wrong and they are different (Codex rounds 2-4 on PR #29):
    #   * the seed marks the role NOWHERE - every reply is not_applicable, so the run clears preflight, spends the
    #     target budget and finishes with no measurement for its declared outcome;
    #   * the arms are not parallel - one arm marks it in a branch and its counterpart does not, so one side of the
    #     register contrast has rows and the other has none;
    #   * the arms mark it at DIFFERENT POSITIONS - both sides have rows, but at different exchanges, so the
    #     cross-arm comparison pairs replies to different stimuli. Presence alone does not catch this.
    # Requiring every trajectory to mark it is wrong: pw-petri-example-h4-persistence marks `pressure` on its
    # pressure branch and deliberately not on its neutral control, which is the design.
    from .judge_runner import CONTEXT_ROLE_GATED

    gated = {d: role for d, (role, _shape) in CONTEXT_ROLE_GATED.items() if d in judged}
    if gated:
        by_branch: dict[str, dict[str, list[dict]]] = {ROOT_BRANCH: {a["id"]: a["turns"] for a in proto["arms"]}}
        if anchor is not None:
            for branch in proto["branches"]:
                by_branch[branch["id"]] = {
                    arm: spec["turns"][: anchor["after_arm_turn"]] + branch["turns"] for arm, spec in arms.items()}
        for dim_id, role in sorted(gated.items()):
            # the 1-based positions of the marked turns in each trajectory, which is what the planner keys on
            positions = {branch: {arm: tuple(i for i, t in enumerate(turns, 1) if t.get("context_role") == role)
                                  for arm, turns in per_arm.items()}
                         for branch, per_arm in by_branch.items()}
            if not any(any(p) for per_arm in positions.values() for p in per_arm.values()):
                problems.append(f"{dim_id} is judged but no turn anywhere in the seed is marked context_role "
                                f"{role!r}: every reply would be recorded not_applicable, so the run would spend "
                                f"the target budget and measure nothing for that dimension")
                continue
            # An immediate gate judges the reply that ANSWERS the marked turn, against the reply before it. Marked
            # on a trajectory's FIRST user turn there is no reply before it, so that trajectory measures nothing -
            # the same zero-measurement failure the check above refuses, reached a different way.
            if CONTEXT_ROLE_GATED[dim_id][1] == "immediate":
                for branch, per_arm in sorted(positions.items()):
                    barren = sorted(arm for arm, p in per_arm.items() if p and set(p) == {1})
                    if barren:
                        problems.append(f"{dim_id} is judged and branch {branch!r} marks context_role {role!r} only "
                                        f"on the first user turn of {barren}: an immediate gate compares the reply "
                                        f"answering that turn against the reply before it, and there is none, so "
                                        f"those arms would measure nothing for that dimension")
            # An after gate judges every reply that FOLLOWS the baseline exchange against that exchange's reply, so
            # the mark has two shape requirements the other gates do not: one baseline per trajectory (two marks
            # would leave the planner to pick one, while the prompt describes a single named reply), and not on the
            # trajectory's last user turn, after which nothing follows to be compared.
            if CONTEXT_ROLE_GATED[dim_id][1] == "after":
                for branch, per_arm in sorted(positions.items()):
                    lengths_here = {arm: len(turns) for arm, turns in by_branch[branch].items()}
                    for arm, p in sorted(per_arm.items()):
                        if len(p) > 1:
                            problems.append(f"{dim_id} is judged and branch {branch!r} marks context_role {role!r} "
                                            f"on {len(p)} user turns of arm {arm!r} ({list(p)}): a baseline is one "
                                            f"reply, so exactly one turn per trajectory is marked")
                    barren = sorted(arm for arm, p in per_arm.items() if p and max(p) == lengths_here[arm])
                    if barren:
                        problems.append(f"{dim_id} is judged and branch {branch!r} marks context_role {role!r} on "
                                        f"the last user turn of {barren}: an after gate compares the replies that "
                                        f"follow the baseline exchange with its reply, and none follow, so those "
                                        f"arms would measure nothing for that dimension")
            for branch, per_arm in sorted(positions.items()):
                distinct = sorted({p for p in per_arm.values()})
                if len(distinct) == 1:
                    continue                                  # every arm marks it in the same places, or none does
                bare = sorted(arm for arm, p in per_arm.items() if not p)
                if bare:
                    problems.append(f"{dim_id} is judged and branch {branch!r} marks context_role {role!r} on "
                                    f"{sorted(arm for arm, p in per_arm.items() if p)} but not on {bare}: the arms "
                                    f"are not parallel, so one side of the contrast would carry rows the other "
                                    f"cannot")
                else:
                    problems.append(f"{dim_id} is judged and branch {branch!r} marks context_role {role!r} at "
                                    f"different user turns per arm ({dict(sorted(per_arm.items()))}): the planner "
                                    f"keys eligibility on position, so the arms would be judged at different "
                                    f"exchanges and the comparison would pair different stimuli")
    if seed["judge"]["advice_tier"]["contextual"] and exposure == "single_turn":
        problems.append("the contextual tier instrument applies to turns after the first; a single_turn seed has none")
    if seed["mode"] == "autonomous":
        if seed["claim_grade_eligible"]:
            problems.append("an autonomous (LLM-auditor) seed is exploratory and cannot be claim-grade eligible")
        if not seed.get("auditor_instruction"):
            problems.append("autonomous mode needs an auditor_instruction")
        # the adaptive controller (docs/petri_adaptive_design.md) writes turns 2..N, so nothing after the first turn
        # is a declared text: outcome dimensions gate on declared turns, branches anchor on a scripted reply, and a
        # system prompt would be a second manipulation the auditor cannot see
        if seed["judge"]["outcome_dimensions"] or seed["judge"]["supplied_contexts"]:
            problems.append("an autonomous seed judges the advice tier and the register check only; outcome "
                            "dimensions and supplied contexts need scripted turns")
        if seed["protocol"]["branches"] or seed["protocol"]["branch_anchor"]:
            problems.append("an autonomous seed declares no branches: the auditor's turns are not a shared prefix")
        if seed["system_prompt"]["policy"] != "none":
            problems.append("an autonomous seed stages no system prompt")
    else:
        if seed.get("auditor_instruction"):
            problems.append("a scripted seed carries no auditor instruction: nothing but data reaches the target")
    return problems
