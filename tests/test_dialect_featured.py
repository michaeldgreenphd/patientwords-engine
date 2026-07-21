"""Dialect featured picks (scripts/export_dialect_matrix.py, audit M3 tail).

Pins the home specimen's exact selection semantics — stem() with the page's
`String(t||'')` guard, (cross_flips, flips, spread) descending with stable
file-order ties, the 2/1/0 variant weighting with |delta| tiebreak, top-4 —
and the featured-term pick (pins-pattern substring, items[0] fallback).
Synthetic terms only — no medical vocabulary in this file.
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_dialect_matrix", _ROOT / "scripts" / "export_dialect_matrix.py")
dm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dm)


def v(dial, top, flip, delta):
    return {"dialect": dial, "top_token": top, "flip": flip, "delta": delta}


def item(term, target, variants):
    return {"term": term, "target_token": target, "variants": variants}


def test_stem_has_the_missing_token_guard():
    assert dm.stem(None) == "" and dm.stem("") == ""
    assert dm.stem("  ALPha ") == "alp"
    assert dm.stem("ab") == "ab"


def test_specimen_pick_stats_and_variant_order():
    items = [
        item("t1", "alpha", [v("d1", "alpha", False, 0.5)]),
        item("t2", "alpha", [v("d1", "beta", True, 0.1),     # cross flip
                             v("d2", "alp-x", True, 0.2),    # flip, same stem
                             v("d3", "betb", True, 0.3),     # cross flip
                             v("d4", "gamma", False, 0.9),   # no flip
                             v("d5", "delta", True, 0.05)]), # cross flip
    ]
    spec = dm.featured_specimen(items)
    assert spec["item"] == 1
    assert spec["stats"] == {"cross_flips": 3, "flips_total": 4, "spread": 0.9}
    # weight 2 (cross) by |delta| desc, then weight 1, then weight 0; top 4
    assert spec["show_variants"] == ["d3", "d1", "d5", "d2"]


def test_specimen_ties_break_by_file_order_and_empty_is_none():
    a = item("t1", "x", [v("d1", "yy", True, 0.2)])
    b = item("t2", "x", [v("d1", "zz", True, 0.2)])
    assert dm.featured_specimen([a, b])["item"] == 0
    assert dm.featured_specimen([]) is None


def test_featured_term_pattern_substring_and_fallback():
    items = [item("aaa", "x", []), item("zz-needle-zz", "x", [])]
    assert dm.featured_term(items, "NEEDLE") == {"item": 1, "term": "zz-needle-zz"}
    assert dm.featured_term(items, "absent")["item"] == 0
    assert dm.featured_term(items, None)["item"] == 0
    assert dm.featured_term([], "x") is None


def test_function_word_classification_and_headline_counts(tmp_path):
    import json
    vocab = tmp_path / "display_vocab.json"
    vocab.write_text(json.dumps(
        {"function_word_targets": {"tokens": ["My", "the"]}}))
    fw = dm.function_word_set(str(vocab))
    assert fw == {"my", "the"}
    items = [
        item("t1", " My ", [v("d1", "x", True, 0.1), v("d2", "y", False, 0.2)]),
        item("t2", "alpha", [v("d1", "x", True, 0.1), v("d2", "y", True, 0.2),
                             v("d3", "z", False, 0.3)]),
    ]
    dm.classify_function_targets(items, fw)
    assert items[0]["target_is_function"] is True
    assert items[1]["target_is_function"] is False
    assert dm.headline_counts(items) == {"cells": 5, "flips": 2, "func_flips": 1}


def test_function_word_set_missing_file_is_none(tmp_path):
    assert dm.function_word_set(str(tmp_path / "nope.json")) is None
