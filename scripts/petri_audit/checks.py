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

from .framework import sha256_text
from .seeds import SeedSet, conditions, text_of

ROOT_BRANCH = "root"
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


def claim_grade_eligible(contract_checks: dict[str, dict], refused: int) -> bool:
    """Every check passed or had nothing to examine, and no record was refused."""
    return all(c["status"] in ELIGIBLE_STATUSES for c in contract_checks.values()) and refused == 0
