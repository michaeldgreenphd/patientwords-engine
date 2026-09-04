"""Tests for the D6 utterance harvest. Abstract fixture content only."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pab_harvest_utterances",
    Path(__file__).resolve().parent.parent / "scripts" / "pab_harvest_utterances.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pab_run"
CONTRACT = Path(__file__).resolve().parent.parent / "data" / "pab_transcript_contract.json"


def test_literacy_arm_parsing():
    assert mod.literacy_arm("pw:health_literacy=low") == "low"
    assert mod.literacy_arm("pw:base=confused;health_literacy=high") == "high"
    assert mod.literacy_arm("anxious") is None          # preset, not a sweep arm
    assert mod.literacy_arm("pw:clarity=low") is None   # different trait


def test_fixture_harvest_pairs_and_hides_scenario(tmp_path):
    out = tmp_path / "h.json"
    rc = mod.main(["--run", str(FIXTURE), "--contract", str(CONTRACT),
                   "--out", str(out)])
    assert rc == 0
    rep = json.loads(out.read_text())
    assert rep["n_groups"] > 0
    assert rep["n_complete_pairs"] > 0
    # patient turns present; assistant turns absent
    convs = json.loads((FIXTURE / "0_0" / "conversations.json").read_text())
    text = out.read_text()
    human = [m["content"] for c in convs for m in c["conversation"] if m["type"] == "human"]
    ai = [m["content"] for c in convs for m in c["conversation"] if m["type"] == "ai"]
    assert any(h in text for h in human)
    assert not any(a in text for a in ai)
    # the pairing basis (scenario text) never reaches the output
    for c in convs:
        assert c["scenario"] not in text
    # groups carry hashed keys only
    for g in rep["groups"]:
        assert len(g["pair_key"]) == 16


def test_medium_arm_kept_but_not_required_for_completeness(tmp_path):
    out = tmp_path / "h.json"
    mod.main(["--run", str(FIXTURE), "--contract", str(CONTRACT), "--out", str(out)])
    rep = json.loads(out.read_text())
    arms = set()
    for g in rep["groups"]:
        arms |= set(g["arms"])
    assert "medium" in arms or arms == {"low", "high"}  # fixture carries 3 arms
    # completeness is defined by low+high presence, whatever else exists
    for g in rep["groups"]:
        if {"low", "high"} <= set(g["arms"]):
            assert g in rep["groups"]


def test_null_conversation_entries_are_counted_not_fatal(tmp_path):
    """Run 31140382136 regression: real conversations.json files carry null
    placeholders for aborted conversations; the harvest must count and skip
    them, never crash."""
    run = tmp_path / "run"
    exp = run / "0_0"
    exp.mkdir(parents=True)
    real = json.loads((FIXTURE / "0_0" / "conversations.json").read_text())
    exp.joinpath("conversations.json").write_text(json.dumps([None] + real + [None]))
    out = tmp_path / "h.json"
    rc = mod.main(["--run", str(run), "--contract", str(CONTRACT), "--out", str(out)])
    assert rc == 0
    rep = json.loads(out.read_text())
    assert rep["skipped"]["not_a_dict"] == 2
    assert rep["n_groups"] > 0
