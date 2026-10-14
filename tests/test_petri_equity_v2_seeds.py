"""Tests for the equity study, version 2 (docs/framework/petri_seeds_equity_v2.draft.json; owner decision 2026-10-14).

Each equity seed has a matched control: the same clinical course without the housing, insurance and stigma details.
The pairing, the shared turns, the warning-sign turn and the warning-sign terms are data
(data/petri/equity_v2_pairs.draft.json), and every seed id is read from there, so no scenario vocabulary is written in
this file (AGENTS.md hard conventions)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from scripts.petri_audit import cli, seeds, token_budget
from scripts.petri_audit.framework import load_json, sha256_text

ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = ROOT / "docs" / "framework" / "petri_seeds_equity_v2.draft.json"
SWAPS_FILE = ROOT / "data" / "petri" / "lay_careful_swaps_equity_v2.draft.json"
PAIRS_FILE = ROOT / "data" / "petri" / "equity_v2_pairs.draft.json"
ARMS = ("clinical", "colloquial", "lay_careful")
TURNS = 10

Seed = dict[str, Any]


@pytest.fixture(scope="module")
def doc() -> dict[str, Any]:
    return load_json(SEED_FILE)


@pytest.fixture(scope="module")
def by_id(doc: dict[str, Any]) -> dict[str, Seed]:
    return {s["seed_id"]: s for s in doc["seeds"]}


@pytest.fixture(scope="module")
def pairs() -> dict[str, Any]:
    return load_json(PAIRS_FILE)


def _texts(seed: Seed) -> dict[str, str]:
    return {t["key"]: t["text"] for t in seed["texts"]}


def _roles(seed: Seed, arm: str) -> list[str | None]:
    return [t["context_role"] for t in next(a for a in seed["protocol"]["arms"] if a["id"] == arm)["turns"]]


def test_pairs_name_every_seed_once(doc: dict[str, Any], pairs: dict[str, Any]) -> None:
    named = [p[k] for p in pairs["pairs"] for k in ("equity", "control")]
    assert sorted(named) == sorted(s["seed_id"] for s in doc["seeds"])
    assert len(set(named)) == len(named)
    assert pairs["seed_file"] == str(SEED_FILE.relative_to(ROOT))


def test_every_seed_validates(doc: dict[str, Any]) -> None:
    seed_set = seeds.load_seed_file(SEED_FILE)
    for seed_id, seed in seed_set.seeds.items():
        assert seeds.validate_seed(seed, seed_set) == [], seed_id


def test_validate_seeds_cli_accepts_the_file(doc: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate-seeds", "--seeds", str(SEED_FILE)]) == 0
    out = capsys.readouterr().out
    assert all(f"{s['seed_id']}: ok" in out for s in doc["seeds"])


def test_every_text_digest_matches_its_text(doc: dict[str, Any]) -> None:
    for seed in doc["seeds"]:
        for t in seed["texts"]:
            assert t["sha256"] == sha256_text(t["text"]), (seed["seed_id"], t["key"])


def test_structure_is_the_same_in_every_seed(doc: dict[str, Any]) -> None:
    """Exploratory study: not claim-grade. Ten scripted turns in three patient arms, sustained exposure, and one
    sequence of context roles shared by every arm of every seed, so a pair differs only in its texts."""
    role_sequences: set[tuple[str | None, ...]] = set()
    for seed in doc["seeds"]:
        sid, proto = seed["seed_id"], seed["protocol"]
        assert seed["mode"] == "scripted" and seed["claim_grade_eligible"] is False, sid
        assert seed["speaker_identity"]["policy"] == "constant", sid
        assert proto["register_exposure"] == "sustained" and proto["max_target_turns"] == TURNS, sid
        assert [a["id"] for a in proto["arms"]] == list(ARMS), sid
        assert {a["user_is"] for a in proto["arms"]} == {"patient"}, sid
        assert {len(a["turns"]) for a in proto["arms"]} == {TURNS}, sid
        role_sequences |= {tuple(_roles(seed, arm)) for arm in ARMS}
    assert len(role_sequences) == 1


def test_the_evidence_role_is_only_at_the_pivot_turn(doc: dict[str, Any], pairs: dict[str, Any]) -> None:
    """The only turn marked evidence is pivot_turn. The role is a label; the text it labels is checked below."""
    pivot = pairs["pivot_turn"]
    for seed in doc["seeds"]:
        roles = _roles(seed, "clinical")
        assert [i for i, r in enumerate(roles, 1) if r == "evidence"] == [pivot], seed["seed_id"]


def _affirmed(text: str, terms: list[str], cues: list[str]) -> list[str]:
    """The terms `text` affirms: each occurrence whose sentence has no negation cue before it ("no fever" is a
    negated mention; "a fever of" an affirmed one)."""
    found = []
    for sentence in re.split(r"[.?!]\s", text.lower()):
        for term in terms:
            for m in re.finditer(re.escape(term.lower()), sentence):
                before = sentence[:m.start()]
                if not any(re.search(rf"\b{re.escape(c)}\b", before) for c in cues):
                    found.append(term)
    return found


def test_the_warning_signs_are_affirmed_only_at_the_pivot_turn(by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """The scripted texts, not only the role label (Codex review of PR #108): in every arm of every seed, the
    scenario's warning-sign terms are affirmed at pivot_turn and nowhere else; earlier turns may only deny them. eq02
    (2026-10-13) put warning signs at turns 4, 5 and 7 of the first equity seeds, and every wording reached the top
    tier by turn 4."""
    pivot, cues = pairs["pivot_turn"], pairs["negation_cues"]
    for pair in pairs["pairs"]:
        assert pair["warning_signs"]
        for seed_id in (pair["equity"], pair["control"]):
            texts = _texts(by_id[seed_id])
            for n in range(1, TURNS + 1):
                for arm in ARMS:
                    affirmed = _affirmed(texts[f"t{n:02d}_{arm}"], pair["warning_signs"], cues)
                    if n == pivot:
                        assert affirmed, (seed_id, n, arm)
                    else:
                        assert affirmed == [], (seed_id, n, arm, affirmed)


def test_the_affirmation_check_tells_a_denial_from_a_sign() -> None:
    assert _affirmed("Today I have no fever.", ["fever"], ["no"]) == []
    assert _affirmed("Today I have a fever of 39.", ["fever"], ["no"]) == ["fever"]
    assert _affirmed("No rash. Tonight a fever started.", ["fever"], ["no"]) == ["fever"]


def test_matched_pairs_share_the_clinical_course(by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """Shared turns are byte-identical in every arm of the equity seed and its control; every other turn differs in
    every arm, where the equity seed carries its housing, insurance and stigma details."""
    for pair in pairs["pairs"]:
        eq, ctl = _texts(by_id[pair["equity"]]), _texts(by_id[pair["control"]])
        shared = set(pair["shared_turns"])
        assert pairs["pivot_turn"] in shared
        for n in range(1, TURNS + 1):
            for arm in ARMS:
                key = f"t{n:02d}_{arm}"
                if n in shared:
                    assert eq[key] == ctl[key], (pair["equity"], key)
                else:
                    assert eq[key] != ctl[key], (pair["equity"], key)


def _one_span_deleted(longer: str, shorter: str) -> bool:
    """True when `shorter` is `longer` with exactly one non-empty contiguous span removed."""
    if len(shorter) >= len(longer):
        return False
    head = next((i for i, (a, b) in enumerate(zip(longer, shorter)) if a != b), len(shorter))
    return any(longer[:i] + longer[i + len(longer) - len(shorter):] == shorter for i in range(head + 1))


def test_clause_removed_turns_change_only_the_equity_clause(by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """On the turns the pairs file names, the control is the equity text with one span (the equity clause) deleted, so
    the clinical exposure the turn describes is the same in both (Codex review of PR #108: the foot control had
    changed the footwear exposure as well)."""
    for pair in pairs["pairs"]:
        eq, ctl = _texts(by_id[pair["equity"]]), _texts(by_id[pair["control"]])
        assert pair["clause_removed_turns"] and not set(pair["clause_removed_turns"]) & set(pair["shared_turns"])
        for n in pair["clause_removed_turns"]:
            for arm in ARMS:
                key = f"t{n:02d}_{arm}"
                assert _one_span_deleted(eq[key], ctl[key]), (pair["control"], key)


def test_declared_hypotheses_are_those_of_the_judged_outcomes(doc: dict[str, Any]) -> None:
    """A seed's hypotheses are copied onto every analysis row (judge_runner.analysis_rows), so they must be exactly the
    hypotheses of the outcome dimensions it judges (Codex review of PR #108: H2 was declared, which these seeds do not
    measure, and H4 was missing)."""
    registry = {d["id"]: set(d.get("hypotheses") or [])
                for d in load_json(ROOT / "docs" / "framework" / "outcome_dimensions.draft.json")["dimensions"]}
    for seed in doc["seeds"]:
        judged: set[str] = set().union(*(registry[d] for d in seed["judge"]["outcome_dimensions"]))
        assert set(seed["hypotheses"]) == judged, (seed["seed_id"], seed["hypotheses"], sorted(judged))


def test_lay_careful_is_the_clinical_text_with_its_swaps(doc: dict[str, Any]) -> None:
    swaps = load_json(SWAPS_FILE)
    assert swaps["seed_file"] == str(SEED_FILE.relative_to(ROOT))
    for seed in doc["seeds"]:
        sid, texts = seed["seed_id"], _texts(seed)
        for n in range(1, TURNS + 1):
            t = f"t{n:02d}"
            out = texts[f"{t}_clinical"]
            for clinical_span, lay_span in swaps["seeds"][sid][f"{t}_lay_careful"]:
                assert clinical_span in out, (sid, t, clinical_span)
                out = out.replace(clinical_span, lay_span, 1)
                assert lay_span.lower() in texts[f"{t}_colloquial"].lower(), (sid, t, lay_span)
            assert out == texts[f"{t}_lay_careful"], (sid, t)


def test_colloquial_turns_are_lower_case(doc: dict[str, Any]) -> None:
    """The framing registry's colloquial register: casual orthography, lower case."""
    for seed in doc["seeds"]:
        for key, text in _texts(seed).items():
            if key.endswith("_colloquial"):
                assert text == text.lower(), (seed["seed_id"], key)


def test_every_conversation_fits_the_token_limit_ten_turn_runs_use() -> None:
    """The pre-flight projection (scripts/petri_audit/token_budget.py) clears every condition at 40,000 tokens."""
    seed_set = seeds.load_seed_file(SEED_FILE)
    problems, _ = token_budget.token_limit_report(list(seed_set.seeds.values()), token_limit=40000)
    assert problems == []
