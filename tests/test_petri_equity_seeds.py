"""Tests for the equity-focused Petri seeds (docs/framework/petri_seeds_equity.draft.json)."""

from __future__ import annotations

from pathlib import Path
import pytest

from scripts.petri_audit import cli, seeds
from scripts.petri_audit.framework import load_json, sha256_text

ROOT = Path(__file__).resolve().parents[1]
EQUITY_FILE = ROOT / "docs" / "framework" / "petri_seeds_equity.draft.json"
EQUITY_SWAPS = ROOT / "data" / "petri" / "lay_careful_swaps_equity.draft.json"
ARMS = ("clinical", "colloquial", "lay_careful")
TURNS = 10


@pytest.fixture(scope="module")
def equity_set() -> seeds.SeedSet:
    return seeds.load_seed_file(EQUITY_FILE)


@pytest.fixture(scope="module")
def equity_doc() -> dict:
    return load_json(EQUITY_FILE)


@pytest.fixture(scope="module")
def swaps_doc() -> dict:
    return load_json(EQUITY_SWAPS)


def _roles(seed: dict, arm: str = "clinical") -> list[str | None]:
    return [t["context_role"] for t in next(a for a in seed["protocol"]["arms"] if a["id"] == arm)["turns"]]


def test_every_equity_seed_validates_through_seed_module(equity_set):
    assert len(equity_set.seeds) == 2
    for seed_id, seed in equity_set.seeds.items():
        problems = seeds.validate_seed(seed, equity_set)
        assert problems == [], f"{seed_id} has validation problems: {problems}"


def test_validate_seeds_cli_accepts_equity_file(capsys):
    ret = cli.main(["validate-seeds", "--seeds", str(EQUITY_FILE)])
    assert ret == 0
    out = capsys.readouterr().out
    assert "pw-petri-equity-scd-acute-chest: ok" in out
    assert "pw-petri-equity-diabetic-ulcer-sepsis: ok" in out


def test_every_text_digest_matches_its_text(equity_doc):
    for seed in equity_doc["seeds"]:
        for t in seed["texts"]:
            assert t["sha256"] == sha256_text(t["text"]), (seed["seed_id"], t["key"])


def test_seed_structure_and_invariants(equity_doc):
    for seed in equity_doc["seeds"]:
        sid = seed["seed_id"]
        assert seed["mode"] == "scripted", sid
        assert seed["claim_grade_eligible"] is True, sid
        assert seed["pilot_wave"] == 3, sid
        assert seed["speaker_identity"]["policy"] == "constant", sid
        assert seed["framing"] == {
            "dimension_id": "register",
            "contrast_id": "clinical_to_colloquial",
            "decomposition_registers": ["lay_careful"],
        }, sid
        proto = seed["protocol"]
        assert proto["register_exposure"] == "sustained", sid
        assert proto["max_target_turns"] == TURNS, sid
        assert [a["id"] for a in proto["arms"]] == list(ARMS), sid
        assert {a["user_is"] for a in proto["arms"]} == {"patient"}, sid
        assert {len(a["turns"]) for a in proto["arms"]} == {TURNS}, sid

        roles = {tuple(_roles(seed, arm)) for arm in ARMS}
        assert len(roles) == 1, f"{sid}: every arm marks the same context roles at the same exchanges"


def test_lay_careful_replacements_transform_clinical_to_lay_careful(equity_doc, swaps_doc):
    for seed in equity_doc["seeds"]:
        sid = seed["seed_id"]
        seed_swaps = swaps_doc["seeds"][sid]
        texts_by_key = {t["key"]: t["text"] for t in seed["texts"]}

        for turn_idx in range(1, TURNS + 1):
            t_key = f"t{turn_idx:02d}"
            clin_text = texts_by_key[f"{t_key}_clinical"]
            lay_text = texts_by_key[f"{t_key}_lay_careful"]
            colloq_text = texts_by_key[f"{t_key}_colloquial"]

            replacements = seed_swaps[f"{t_key}_lay_careful"]
            transformed = clin_text
            for clin_span, lay_span in replacements:
                assert clin_span in transformed, f"{sid} {t_key}: '{clin_span}' not in '{transformed}'"
                transformed = transformed.replace(clin_span, lay_span, 1)
                # Lay span must also be present in colloquial arm (case-insensitive)
                assert lay_span.lower() in colloq_text.lower(), (
                    f"{sid} {t_key}: lay span '{lay_span}' not in colloquial '{colloq_text}'"
                )

            assert transformed == lay_text, f"{sid} {t_key}: transformed text does not match lay_careful text"
