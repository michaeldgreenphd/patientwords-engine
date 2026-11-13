"""The first bounded experiment's protocol draft is pinned to the code and records it names.

Nothing here runs a model. The checks keep the protocol's fixed statements, its control and state names, its
review form and its one runnable step in agreement with the scorer, the rubric and the run packet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import instrument_validity as iv  # noqa: E402
from scripts.experiments import bundle as bundle_module  # noqa: E402
from scripts.experiments.common import OPTIONAL_VARIANTS  # noqa: E402

PROTOCOL = ROOT / "docs" / "protocols" / "instrument_register_experiment_20261111.md"
RUBRIC = ROOT / "data" / "protocols" / "instrument_validity_rubric.draft.json"
PACKET = ROOT / "docs" / "exploratory" / "first_model_run_packet_20261110.md"
STAGE_A = ROOT / "data" / "experiments" / "protocols" / "first_run_stage_a.protocol.v1.json"


def _text() -> str:
    return " ".join(PROTOCOL.read_text(encoding="utf-8").split())


def test_the_protocol_is_an_unsigned_draft_that_reports_no_result() -> None:
    text = _text()
    assert "**Status: draft, not signed. Nothing in it has been run on a model." in text
    assert "None of these has a value yet." in text
    assert "a recommendation is not a value, and the table changes only by the owner's decision" in text
    assert "None. Nothing has been run under this protocol." in text
    # Section 14 holds no number: every margin and threshold is "not fixed". Section 14.1 recommends and fixes nothing.
    section = PROTOCOL.read_text(encoding="utf-8").split("\n## 14. ")[1].split("\n## 15. ")[0]
    table, recommendations = section.split("### 14.1")
    rows = [line for line in table.splitlines() if line.startswith("| ") and "Field" not in line and "---" not in line]
    assert len(rows) == 5 and all(row.split("|")[2].strip() == "not fixed" for row in rows)
    assert recommendations.startswith(" Recommendations awaiting the owner's decision")
    assert "No outcome-blind family has been measured" in recommendations


def test_the_pilot_on_authored_families_is_a_proposal_on_discovery_families_only() -> None:
    text = _text()
    assert "**The smallest pilot on authored families: proposed, not approved, not fired (2026-11-12).**" in text
    assert "no validation or fresh-test family is measured" in text
    for stratum in ("`patient_explanation`", "`syntax_crossing`", "`register_with_dialect`", "`new_carrier`"):
        assert stratum in text, stratum
    assert "Care tiers are not compared with each other" in text


def test_the_four_parts_stay_separate_and_name_their_level_of_evidence() -> None:
    text = _text()
    for part, level in (("| A |", "a change in a defined probability"),
                        ("| B |", "a difference in an instrument's readout"),
                        ("| C |", "a difference in an internal representation, and an association with behaviour"),
                        ("| D |", "none: D is a plan")):
        assert part in text and level in text, part
    for sentence in ("never adds their answers into one number",
                     "The endpoint of A is the probability of one token, the first token of the target.",
                     "C is an association across families.",
                     "No part of this experiment is such an intervention, and no result of A to C is described as causal.",
                     "Equity motivates the question. These data cannot show an effect on people.",
                     "A difference that is not significant is never reported as equivalence.",
                     "Everyday wording is not treated as defective medical wording"):
        assert sentence in text, sentence


def test_every_control_state_and_refusal_the_protocol_names_exists_in_the_scorer() -> None:
    text = _text()
    for arm in iv.ARMS:
        assert f"`{arm}`" in text
    assert f"`{iv.ARTIFACT_CONTRIBUTES}`" in text and iv.ARTIFACT_CONTRIBUTES in iv.ARM_STATES
    for outcome in (iv.EQUIVALENT, iv.DIFFERENT, iv.INCONCLUSIVE):
        assert f"`{outcome}`" in text
    source = (ROOT / "scripts" / "instrument_validity.py").read_text(encoding="utf-8")
    for code in ("repeated_phrase", "split_leakage", "calibration_reads_held_out", "real_bundle_not_admitted"):
        assert f"`{code}`" in text and f'"{code}"' in source, code
    assert "--calibrate --quantile <Q>" in text and "The command has no default" not in text
    assert "the command has no default" in text
    # The optional variants the runner's protocol accepts are the two controls the protocol requires.
    assert OPTIONAL_VARIANTS == ("within_register_paraphrase", "changed_fact_control")
    assert "Within-register paraphrase" in text and "Changed-fact control" in text


def test_the_review_form_has_the_six_dimensions_and_both_reviewer_roles() -> None:
    form = json.loads(RUBRIC.read_text(encoding="utf-8"))["pair_equivalence_review"]
    dimensions = [entry["dimension"] for entry in form["dimensions"]]
    assert dimensions == ["clinical_facts", "negation", "timing", "uncertainty", "severity", "urgency"]
    assert [reviewer["role"] for reviewer in form["reviewers"]] == ["clinician", "patient_language_reviewer"]
    assert form["reviewers"][0]["reviews"] == dimensions
    assert form["missing_value"]["recorded_as"] is None and "language model" in form["not_a_review"]
    text = _text()
    assert "clinical facts, negation, timing, uncertainty, severity, urgency" in text
    assert "A model's statement that two wordings are equivalent is not a review" in text


def test_the_runnable_step_matches_the_run_packet_and_the_committed_stage_a_protocol() -> None:
    text, packet = _text(), PACKET.read_text(encoding="utf-8")
    stage_a = json.loads(STAGE_A.read_text(encoding="utf-8"))
    revision = stage_a["model"]["revision"]
    assert revision in text and revision in packet
    assert stage_a["primary_endpoint"] == {"method": "behavior_next_token", "metric": "full_vocab_probability",
                                           "target": "t_answer"}
    assert "data/simulated/pairs_20260706T175614Z.json" in text and "pairs_20260706T175614Z.json" in packet
    for figure in ("240 runner minutes", "17.7", "88.5"):
        assert figure in text and figure in packet, figure
    for limit in ("the ICA hypothesis", "clinical validity", "throughput at scale"):
        assert limit in text, limit
    assert "It is fired only through `scripts/fire_trigger.py`." in text
    assert "are not measurements of a model run and are never reported as throughput" in text
    # The bundle's two text markers are separate approvals; the protocol relies on neither for stage A.
    assert bundle_module.PROMPT_TEXT_MARKER != bundle_module.TARGET_TEXT_MARKER
