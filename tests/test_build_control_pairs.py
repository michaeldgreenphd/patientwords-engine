"""Offline tests for the negative-control pair builder.

No model, no network. Abstract placeholders only — the real prompts come from
the measured batch at runtime, and the qualifier clauses from a data file.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bcp = _load("build_control_pairs")

PAIR = {
    "top_prompt": "I have alpha, so I need to take my",
    "bottom_prompt": "My bravo keeps happening, so I need to take my",
    "target_clinical_token": " charlie",
    "generation": {"clinical_term": "alpha", "patient_term": "bravo", "topic": "delta"},
}
QUALIFIERS = ["noted in my chart", "confirmed on examination"]


def test_identity_arm_is_the_clinical_prompt_against_itself():
    """The penalty must be exactly 0; anything else means the measurement path
    carries state between the two forward passes."""
    out = bcp.build_pair(PAIR, "identity", None)
    assert out["bottom_prompt"] == out["top_prompt"] == PAIR["top_prompt"]
    assert out["generation"]["word_delta"] == 0


def test_qualified_arm_inserts_before_the_so_clause():
    out = bcp.build_pair(PAIR, "qualified", "noted in my chart")
    assert out["bottom_prompt"] == "I have alpha, noted in my chart, so I need to take my"
    # the continuation and therefore the target position is untouched
    assert out["bottom_prompt"].endswith(", so I need to take my")


def test_insertion_uses_the_last_so_clause():
    """A setup clause carrying its own ', so ' must not move the insertion point
    away from the continuation the target follows."""
    prompt = "It started, so it seemed, after alpha, so I need to take my"
    assert bcp.qualify(prompt, "noted in my chart") == (
        "It started, so it seemed, after alpha, noted in my chart, so I need to take my")


def test_a_prompt_with_no_so_clause_raises_rather_than_guessing():
    with pytest.raises(ValueError):
        bcp.qualify("I have alpha and need my", "noted in my chart")


def test_word_delta_is_recorded_so_the_match_to_the_treatment_is_checkable():
    """The control exists to reproduce the treatment's length difference; a run
    that did not must be visible in its own output, not recomputed later."""
    out = bcp.build_pair(PAIR, "qualified", "noted in my chart")
    assert out["generation"]["word_delta"] == 4


def test_patient_term_is_nulled_because_both_sides_are_clinical():
    """Downstream readers key off patient_term. Carrying the source pair's value
    would label a clinical prompt as the colloquial one."""
    out = bcp.build_pair(PAIR, "qualified", "noted in my chart")
    assert out["generation"]["patient_term"] is None
    assert out["generation"]["control_arm"] == "qualified"
    assert out["generation"]["source_bottom_prompt"] == PAIR["bottom_prompt"]


def test_qualifiers_are_assigned_round_robin_across_the_batch():
    built, skipped = bcp.build([PAIR] * 5, "qualified", QUALIFIERS)
    assert skipped == []
    used = [p["generation"]["control_qualifier"] for p in built]
    assert used == [QUALIFIERS[i % 2] for i in range(5)]


def test_unusable_rows_are_recorded_not_dropped():
    """A control missing rows is a different control, so the skip is reported."""
    bad = dict(PAIR, top_prompt="I have alpha and need my")
    built, skipped = bcp.build([PAIR, bad, {}], "qualified", QUALIFIERS)
    assert len(built) == 1
    assert [s["index"] for s in skipped] == [2, 3]
    assert "no top_prompt" in skipped[1]["reason"]


def test_source_index_preserves_the_join_key_back_to_the_batch():
    built, _ = bcp.build([PAIR, PAIR], "identity", QUALIFIERS)
    assert [p["generation"]["source_index"] for p in built] == [1, 2]


def test_shipped_qualifier_file_is_well_formed_and_sized_to_the_confound():
    """The qualifiers must bracket the treatment's +4.02-word difference; a
    control that is systematically shorter is an easier test."""
    doc = json.loads((ROOT / "data" / "control_qualifiers.draft.json").read_text())
    quals = doc["qualifiers"]
    assert quals, "no qualifiers shipped"
    for q in quals:
        assert q["words"] == len(q["text"].split()), q
    mean = sum(q["words"] for q in quals) / len(quals)
    assert abs(mean - doc["target_word_delta"]) < 1.0, f"mean {mean} vs target"
    assert doc["status"] == "draft pending domain review"
