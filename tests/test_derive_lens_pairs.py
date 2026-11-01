"""scripts/derive_lens_pairs.py: dialect and quadrant records become J-lens reader pairs.

The reader (`scripts/jlens_readout.py`) takes `top_prompt` as the clinical side and
`bottom_prompt` as the patient side. These tests pin the comparisons the owner chose
on 2026-10-31 (baseline vs each dialect variant; quadrant A vs B, C and D), the
quadrant strings matching the circuit traces' own composition, and that every
committed `__lenspairs.json` is exactly what the script derives from its source.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from medlang_circuits.batch_eval import _quadrant_prompts

ROOT = Path(__file__).resolve().parents[1]
SIMULATED = ROOT / "data" / "simulated"
spec = importlib.util.spec_from_file_location("derive_lens_pairs", ROOT / "scripts" / "derive_lens_pairs.py")
dlp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dlp)

DIALECT = {
    "baseline_prompt": "I have clinical depression, so I need to talk to a",
    "variants": [
        {"dialect": "Southern US English", "prompt": "I reckon I've got clinical depression, so I need a"},
        {"dialect": "texting/informal register", "prompt": "ngl i got clinical depression so i gotta talk to a"},
    ],
    "held_fixed": "clinical",
    "term": "clinical depression",
    "target_clinical_token": " therapist",
}
QUADRANT_FRAMES = {
    "frames": {"standard": "I've had{term}, so I'll call", "nonstandard": "I been having{term}, so I'ma call"},
    "terms": {"medical": " insomnia", "patient": " trouble sleeping"},
    "target_clinical_token": " my doctor",
    "force_target_tokens": [{"token": " my"}],
}
QUADRANT_EXPLICIT = {
    "quadrants": {"A": "a prompt", "B": "b prompt", "C": "c prompt", "D": "d prompt"},
    "target_clinical_token": " doctor",
}


def test_dialect_record_gives_baseline_vs_each_variant():
    pairs = dlp.derive_record(DIALECT, "dialects_x.json", 3)
    assert [p["bottom_prompt"] for p in pairs] == [v["prompt"] for v in DIALECT["variants"]]
    assert all(p["top_prompt"] == DIALECT["baseline_prompt"] for p in pairs)
    assert all(p["target_clinical_token"] == " therapist" for p in pairs)
    assert [p["generation"]["derived_from"] for p in pairs] == [
        {"batch": "dialects_x.json", "index": 3, "variant": 1},
        {"batch": "dialects_x.json", "index": 3, "variant": 2},
    ]
    assert pairs[1]["generation"]["lens_comparison"]["compared"] == "texting/informal register"


def test_quadrant_record_gives_a_vs_b_c_d_with_the_traces_strings():
    pairs = dlp.derive_record(QUADRANT_FRAMES, "quadrants_x.json", 1)
    prompts = _quadrant_prompts(QUADRANT_FRAMES)
    assert [p["generation"]["lens_comparison"]["compared"] for p in pairs] == ["B", "C", "D"]
    assert all(p["top_prompt"] == prompts["A"] == "I've had insomnia, so I'll call" for p in pairs)
    assert [p["bottom_prompt"] for p in pairs] == [prompts["B"], prompts["C"], prompts["D"]]
    assert all(p["force_target_tokens"] == [{"token": " my"}] for p in pairs)


def test_explicit_quadrants_are_used_verbatim():
    pairs = dlp.derive_record(QUADRANT_EXPLICIT, "q.json", 2)
    assert [(p["top_prompt"], p["bottom_prompt"]) for p in pairs] == [
        ("a prompt", "b prompt"), ("a prompt", "c prompt"), ("a prompt", "d prompt")]
    assert "force_target_tokens" not in pairs[0]


def test_unknown_record_shape_is_refused():
    with pytest.raises(ValueError, match="neither a dialect record"):
        dlp.derive_record({"top_prompt": "x", "bottom_prompt": "y"}, "pairs.json", 1)


def test_dialect_variant_without_prompt_is_refused():
    bad = dict(DIALECT, variants=[{"dialect": "British English"}])
    with pytest.raises(ValueError, match="needs 'dialect' and 'prompt'"):
        dlp.derive_record(bad, "dialects_x.json", 1)


def test_derive_batch_keeps_records_together_and_writes_a_report(tmp_path):
    src = tmp_path / "dialects_t.json"
    src.write_text(json.dumps([DIALECT, DIALECT]), encoding="utf-8")
    out, report, n = dlp.derive_batch(src)
    assert out.name == "dialects_t__lenspairs.json" and n == 4
    indices = [p["generation"]["derived_from"]["index"] for p in json.loads(out.read_text())]
    assert indices == [1, 1, 2, 2]
    rep = json.loads(report.read_text())
    assert rep["pairs"] == 4 and rep["source_records"] == 2 and rep["cost_usd"] == 0.0


COMMITTED = sorted(SIMULATED.glob("*__lenspairs.json"))


@pytest.mark.parametrize("derived", COMMITTED, ids=lambda p: p.name)
def test_committed_lens_pairs_match_their_source(derived, tmp_path):
    source = SIMULATED / derived.name.replace("__lenspairs.json", ".json")
    out, _, _ = dlp.derive_batch(source, tmp_path)
    assert json.loads(out.read_text()) == json.loads(derived.read_text())
    for pair in json.loads(derived.read_text()):
        assert pair["top_prompt"] and pair["bottom_prompt"] and pair["top_prompt"] != pair["bottom_prompt"]


def test_lens_pair_files_exist_for_every_traced_set():
    assert len(COMMITTED) == 15
