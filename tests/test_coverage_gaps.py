"""Coverage/steering report (scripts/coverage_gaps.py) — offline.

Pins the taxonomy flattening, the tier join scoped to the base model, thin
detection (Other never steers), and the steer_topics vocabulary. No network.
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "coverage_gaps", _ROOT / "scripts" / "coverage_gaps.py")
cg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cg)

MAP = {"specialties": {"Cardio": {"General": ["heart rhythm"]},
                       "Derm": {"General": ["skin rash", "itchy patch"]}}}


def test_topic_lookup_flattens_to_spec_sub():
    assert cg.topic_lookup(MAP)["skin rash"] == ("Derm", "General")


def test_build_counts_tiers_thin_and_steering():
    scenarios = [
        {"batch": "b", "batch_index": 1, "topic": "Heart Rhythm"},
        {"batch": "b", "batch_index": 2, "topic": "heart rhythm"},
        {"batch": "b", "batch_index": 3, "topic": "skin rash"},
        {"batch": "b", "batch_index": 4, "topic": "mystery"},        # -> Other
    ]
    urgency = [
        {"batch": "b", "index": 1, "model": "gemma-2-2b", "tier_top_clinical": 2},
        {"batch": "b", "index": 3, "model": "gemma-2-2b", "tier_top_clinical": 1},
        {"batch": "b", "index": 2, "model": "qwen3-4b", "tier_top_clinical": 3},  # wrong model
    ]
    out = cg.build(MAP, scenarios, urgency, "gemma-2-2b", steer_n=1, thin_threshold=2)
    assert out["per_specialty"] == {"Cardio": 2, "Derm": 1, "Other": 1}
    assert out["tier_matrix"]["Cardio"] == {"2": 1}                  # qwen row ignored
    assert out["tier_matrix"]["Derm"] == {"1": 1}
    # Derm (1 < 2) is thin; Other is never steered
    assert out["thin_specialties"] == ["Derm"]
    assert out["steer_topics"] == {"Derm": ["itchy patch", "skin rash"]}
    assert out["scenarios_total"] == 4
