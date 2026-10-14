"""Tests for the equity study, version 2 (docs/framework/petri_seeds_equity_v2.draft.json; owner decision 2026-10-14).

Each equity seed has a matched control: the same clinical course without the housing, insurance and stigma details.
The pairing, the shared turns and the warning-sign turn are data (data/petri/equity_v2_pairs.draft.json), and every
seed id is read from there, so no scenario vocabulary is written in this file (AGENTS.md hard conventions)."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.petri_audit import cli, seeds, token_budget
from scripts.petri_audit.framework import load_json, sha256_text

ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = ROOT / "docs" / "framework" / "petri_seeds_equity_v2.draft.json"
SWAPS_FILE = ROOT / "data" / "petri" / "lay_careful_swaps_equity_v2.draft.json"
PAIRS_FILE = ROOT / "data" / "petri" / "equity_v2_pairs.draft.json"
ARMS = ("clinical", "colloquial", "lay_careful")
TURNS = 10


@pytest.fixture(scope="module")
def doc() -> dict:
    return load_json(SEED_FILE)


@pytest.fixture(scope="module")
def by_id(doc: dict) -> dict:
    return {s["seed_id"]: s for s in doc["seeds"]}


@pytest.fixture(scope="module")
def pairs() -> dict:
    return load_json(PAIRS_FILE)


def _texts(seed: dict) -> dict[str, str]:
    return {t["key"]: t["text"] for t in seed["texts"]}


def _roles(seed: dict, arm: str) -> list:
    return [t["context_role"] for t in next(a for a in seed["protocol"]["arms"] if a["id"] == arm)["turns"]]


def test_pairs_name_every_seed_once(doc, pairs):
    named = [p[k] for p in pairs["pairs"] for k in ("equity", "control")]
    assert sorted(named) == sorted(s["seed_id"] for s in doc["seeds"])
    assert len(set(named)) == len(named)
    assert pairs["seed_file"] == str(SEED_FILE.relative_to(ROOT))


def test_every_seed_validates(doc):
    seed_set = seeds.load_seed_file(SEED_FILE)
    for seed_id, seed in seed_set.seeds.items():
        assert seeds.validate_seed(seed, seed_set) == [], seed_id


def test_validate_seeds_cli_accepts_the_file(doc, capsys):
    assert cli.main(["validate-seeds", "--seeds", str(SEED_FILE)]) == 0
    out = capsys.readouterr().out
    assert all(f"{s['seed_id']}: ok" in out for s in doc["seeds"])


def test_every_text_digest_matches_its_text(doc):
    for seed in doc["seeds"]:
        for t in seed["texts"]:
            assert t["sha256"] == sha256_text(t["text"]), (seed["seed_id"], t["key"])


def test_structure_is_the_same_in_every_seed(doc):
    """Exploratory study: not claim-grade. Ten scripted turns in three patient arms, sustained exposure, and one
    sequence of context roles shared by every arm of every seed, so a pair differs only in its texts."""
    role_sequences = set()
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


def test_the_warning_sign_arrives_only_at_the_pivot_turn(doc, pairs):
    """The only turn marked evidence is pivot_turn, so turns before it carry no warning sign (eq02, 2026-10-13: the
    first equity seeds put warning signs at turns 4, 5 and 7, and every wording reached the top tier by turn 4)."""
    pivot = pairs["pivot_turn"]
    for seed in doc["seeds"]:
        roles = _roles(seed, "clinical")
        assert [i for i, r in enumerate(roles, 1) if r == "evidence"] == [pivot], seed["seed_id"]


def test_matched_pairs_share_the_clinical_course(by_id, pairs):
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


def test_lay_careful_is_the_clinical_text_with_its_swaps(doc):
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


def test_colloquial_turns_are_lower_case(doc):
    """The framing registry's colloquial register: casual orthography, lower case."""
    for seed in doc["seeds"]:
        for key, text in _texts(seed).items():
            if key.endswith("_colloquial"):
                assert text == text.lower(), (seed["seed_id"], key)


def test_every_conversation_fits_the_token_limit_ten_turn_runs_use():
    """The pre-flight projection (scripts/petri_audit/token_budget.py) clears every condition at 40,000 tokens."""
    seed_set = seeds.load_seed_file(SEED_FILE)
    problems, _ = token_budget.token_limit_report(list(seed_set.seeds.values()), token_limit=40000)
    assert problems == []
