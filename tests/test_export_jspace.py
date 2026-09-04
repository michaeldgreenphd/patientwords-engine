"""Tests for scripts/export_jspace.py - the empirical J-space panel exporter."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "export_jspace", Path(__file__).resolve().parents[1] / "scripts" / "export_jspace.py")
ej = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ej)


def _resp(prompt_tokens, per_layer_tops):
    toks = [{"token": t, "is_generated": False} for t in prompt_tokens]
    toks[-1]["results"] = [{"type": "JACOBIAN_LENS", "top_tokens": per_layer_tops}]
    return {"meta": {}, "tokens": toks, "done": {}}


def test_concepts_filter_junk_and_require_persistence():
    tops = [["junk"]] * 12 + [
        ["RenderAtEndOf", " meds", "x"],       # CamelCase artifact dropped
        ["otomatig", " meds", " medication"],  # 'otomatig' flickers once -> dropped
        [" medication", " meds", "!"], [" medication", " meds", "q"],
        [" medication", " vitamins", "."],
        [" vitamins", " medication", "y"], [" vitamins", " z", "w"],
    ] + [["pad"]] * 9 + [[" medication"]]
    out = ej.concepts_of(tops, 12, len(tops) - 2, 4)
    assert "RenderAtEndOf" not in out and "otomatig" not in out
    assert "meds" in out and "medication" in out and "vitamins" in out


def test_panel_verifies_prompt_and_reads_output():
    tops = [[" a"]] * 25 + [[" medication", " x"]]
    r = _resp(["<bos>", "I have", " a thing"], tops)
    p = ej.panel(r, "I have a thing", "a thing", " medication")
    assert p["output"] == "medication" and p["on_target"] is True
    with pytest.raises(SystemExit) as exc:
        ej.panel(r, "some other sentence", "t", " medication")
    assert exc.value.code == 3


def test_diff_span_extracts_swap():
    a, b = ej.diff_span("I have cognitive impairment, so I should",
                        "I've been feeling foggy in my head, so I should")
    assert "cognitive" in a and "foggy" in b
