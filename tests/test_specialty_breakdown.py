"""Specialty penalty breakdown (scripts/specialty_breakdown.py) — offline.

Pins the topic->specialty join, the per-(model, phrase) dedupe (last wins),
missing-prob skipping, and the downgrade join. No network.
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "specialty_breakdown", _ROOT / "scripts" / "specialty_breakdown.py")
sb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sb)

MAP = {"specialties": {"Cardio": {"General": ["heart rhythm", "chest pressure"]},
                       "Derm": {"General": ["skin rash"]}}}


def scen(batch, idx, topic, phrase, pc, pp, models=None):
    s = {"batch": batch, "batch_index": idx, "topic": topic,
         "prompts": {"clinical": phrase},
         "prob_clinical": pc, "prob_patient": pp}
    if models:
        s["models"] = models
    return s


def test_join_dedupe_and_downgrades():
    scenarios = [
        scen("b1", 1, "Heart Rhythm", "ph-a", 0.6, 0.2),            # Cardio, pen -0.4
        scen("b1", 2, "heart rhythm", "ph-a", 0.6, 0.4),            # same phrase -> last wins
        scen("b1", 3, "skin rash", "ph-b", 0.5, 0.1,
             models={"qwen3-4b": {"prob_clinical": 0.3, "prob_patient": 0.4}}),
        scen("b1", 4, "unknown topic", "ph-c", 0.5, 0.5),           # -> Other
        scen("b1", 5, "skin rash", "ph-d", None, 0.2),              # missing prob -> skipped
    ]
    urgency = [{"batch": "b1", "index": 3, "model": "gemma-2-2b",
                "flip_class": "downgrade"}]
    table = sb.penalties_by_specialty(MAP, scenarios, urgency)

    cardio = table["Cardio"]["gemma-2-2b"]
    assert cardio["n_phrases"] == 1
    assert cardio["mean_penalty"] == -0.2                           # ph-a dedupe: last wins
    derm = table["Derm"]
    assert derm["gemma-2-2b"] == {"n_phrases": 1, "mean_penalty": -0.4, "downgrades": 1}
    assert derm["qwen3-4b"]["mean_penalty"] == 0.1                  # per-model submap read
    assert derm["qwen3-4b"]["downgrades"] == 0                      # downgrade is per-model
    assert table["Other"]["gemma-2-2b"]["n_phrases"] == 1
    assert derm["gemma-2-2b"]["n_phrases"] == 1                     # ph-d (missing prob) skipped
