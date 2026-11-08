"""Tests for scripts/casual_orthography.py (owner feedback 2026-11-08: digits, no hyphenated ages, no dashes)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("casual_orthography", ROOT / "scripts" / "casual_orthography.py")
co = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(co)


def test_number_words_become_digits():
    assert co.to_casual("for the past two weeks about thirty seconds") == "for the past 2 weeks about 30 seconds"
    assert co.to_casual("about forty five minutes and forty-five more") == "about 45 minutes and 45 more"
    assert co.to_casual("ten to fifteen seconds, nineteen days") == "10 to 15 seconds, 19 days"


def test_words_people_keep_are_kept():
    for s in ("an hour or two with my mind going", "the other one is bad", "each one ends",
              "101 and a half", "a couple of months", "often tired", "nineteenth"):
        assert co.to_casual(s) == s, s


def test_hyphenated_ages_and_dashes():
    assert co.to_casual("my 78-year-old mom") == "my 78 year old mom"
    assert co.to_casual("my seven-year-old son") == "my 7 year old son"
    assert co.to_casual("a two-week-old baby") == "a 2 week old baby"
    assert co.to_casual("to the kitchen—and she eats") == "to the kitchen and she eats"
    assert co.to_casual("tired – really tired - all day") == "tired really tired all day"
    assert co.to_casual("purple-red dots") == "purple-red dots"  # a hyphenated word, not a dash, stays


def test_transform_batch_records_the_text_before_and_keeps_every_field():
    pairs = [{"top_prompt": "T", "bottom_prompt": "for two days", "generation": {"x": 1}},
             {"top_prompt": "T2", "bottom_prompt": "fine", "generation": {}}]
    out = co.transform_batch(pairs, "src.json", "abc")
    assert out[0]["bottom_prompt"] == "for 2 days" and out[0]["top_prompt"] == "T"
    assert out[0]["generation"]["x"] == 1
    assert out[0]["generation"]["postprocess"] == {"rules": co.RULES_VERSION, "source_batch": "src.json",
                                                   "source_sha256": "abc", "before": "for two days",
                                                   "changed": True}
    assert out[1]["generation"]["postprocess"]["changed"] is False
    assert pairs[0]["bottom_prompt"] == "for two days"  # the input is not modified


def test_committed_v3_batch_is_the_pass_applied_to_v2():
    v2_path = ROOT / "data/advice/rewrite_colloquial_v2_20261107T231002Z.json"
    v3 = sorted((ROOT / "data/advice").glob("rewrite_colloquial_v3_*.json"))
    v3 = [p for p in v3 if not p.name.endswith(".report.json")]
    assert len(v3) == 1
    got = json.loads(v3[0].read_text(encoding="utf-8"))
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    assert [p["generation"]["postprocess"]["before"] for p in got] == [p["bottom_prompt"] for p in v2]
    assert [p["bottom_prompt"] for p in got] == [co.to_casual(p["bottom_prompt"]) for p in v2]
    assert [p["top_prompt"] for p in got] == [p["top_prompt"] for p in v2]
