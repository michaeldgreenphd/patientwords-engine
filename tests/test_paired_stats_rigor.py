"""Tests for scripts/paired_stats_rigor.py — the pre-registered rigor step.

Offline and deterministic: a synthetic rows fixture (no medical vocabulary, no
network, no keys) exercises phrase dedupe, the exact downgrade-rate interval,
Benjamini-Hochberg multiplicity control, and seed determinism. Abstract phrase
strings stand in for the real clinical_prompt values, which live only in the
collector output.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "paired_stats_rigor.py"
_SPEC = importlib.util.spec_from_file_location("paired_stats_rigor", _SCRIPT)
psr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(psr)


def _row(model, phrase, flipped, flip_class, penalty):
    return {
        "model": model,
        "batch": "synthetic",
        "index": 0,
        "clinical_prompt": phrase,
        "top_clinical": "x",
        "top_patient": "y",
        "flipped": flipped,
        "flip_class": flip_class,
        "tier_top_clinical": 1,
        "tier_top_patient": 0,
        "tier_shift": -0.5 if flipped else 0.0,
        "language_penalty": penalty,
    }


@pytest.fixture
def rows():
    """One model 'm1' built for dedupe, one 'm2' built for BH/significance.

    m1 (11 rows -> 7 phrases):
      P1  x3 downgrade, penalties -0.2/-0.3/-0.4 (mean -0.3)  -> dedupe + mean
      P2  x1 downgrade, penalty  -0.2
      P3  x2 upgrade,   penalty  -0.1 (both)
      P4  x1 non-flip,  penalty  +0.05
      P5  x1 lateral,   penalty  -0.15
      P6  x1 uninformative flip, penalty None (flip w/o numeric penalty)
      P7  x2 CONFLICT: one non-flip, one uninformative -> tie -> conservative none
    m2 (11 rows -> 11 phrases): 10 downgrade + 1 upgrade, all penalty -0.2
    """
    r = []
    for pen in (-0.2, -0.3, -0.4):
        r.append(_row("m1", "P1", True, "downgrade", pen))
    r.append(_row("m1", "P2", True, "downgrade", -0.2))
    r.append(_row("m1", "P3", True, "upgrade", -0.1))
    r.append(_row("m1", "P3", True, "upgrade", -0.1))
    r.append(_row("m1", "P4", False, None, 0.05))
    r.append(_row("m1", "P5", True, "lateral", -0.15))
    r.append(_row("m1", "P6", True, "uninformative", None))
    r.append(_row("m1", "P7", False, None, None))
    r.append(_row("m1", "P7", True, "uninformative", None))
    for i in range(10):
        r.append(_row("m2", f"Q{i}", True, "downgrade", -0.2))
    r.append(_row("m2", "Qup", True, "upgrade", -0.2))
    return r


def test_dedupe_reduces_n_and_averages_penalty(rows):
    bundle = psr.analyze(rows, boot=200, seed=7)
    m1 = bundle["per_model"]["m1"]
    assert m1["n_rows"] == 11
    assert m1["n_unique_phrases"] == 7
    assert m1["pseudoreplication_gap"] == 4
    # P1's three differing penalties collapse to their mean before pooling.
    pen = m1["penalty"]
    assert pen["n_rows_with_penalty"] == 8      # P1x3 + P2 + P3x2 + P4 + P5
    assert pen["n_phrases_with_penalty"] == 5   # P6, P7 carry no numeric penalty
    # phrase means: -0.3, -0.2, -0.1, +0.05, -0.15  ->  grand mean -0.14
    assert pen["mean"] == pytest.approx(-0.14)


def test_conflicting_duplicate_resolves_conservatively(rows):
    records = {rec["phrase"]: rec for rec in psr.dedupe_by_phrase(
        [r for r in rows if r["model"] == "m1"])}
    # P7 ties non-flip vs uninformative -> tie-break never manufactures a flip.
    assert records["P7"]["label"] == "none"
    # P1's mean penalty is the average of its three rows.
    assert records["P1"]["penalty"] == pytest.approx(-0.3)


def test_flip_and_downgrade_counts_are_phrase_level(rows):
    m1 = psr.analyze(rows, boot=200, seed=7)["per_model"]["m1"]["flips"]
    # flips: P1(dg) P2(dg) P3(up) P5(lat) P6(uninf) = 5; P7 resolved to non-flip.
    assert m1["n_flips"] == 5
    assert m1["downgrades"] == 2
    assert m1["upgrades"] == 1
    assert m1["downgrade_rate"] == pytest.approx(2 / 5)


def test_clopper_pearson_brackets_and_bounds():
    for k, n in [(0, 5), (2, 5), (5, 5), (1, 20), (18, 40), (3, 3)]:
        lo, hi = psr.clopper_pearson(k, n)
        assert 0.0 <= lo <= hi <= 1.0
        assert lo <= k / n <= hi
    assert psr.clopper_pearson(0, 5)[0] == 0.0    # left tail pinned
    assert psr.clopper_pearson(5, 5)[1] == 1.0    # right tail pinned
    assert psr.clopper_pearson(0, 0) is None      # undefined on no flips


def test_downgrade_rate_ci_brackets_point_estimate(rows):
    fl = psr.analyze(rows, boot=200, seed=7)["per_model"]["m1"]["flips"]
    lo, hi = fl["downgrade_rate_ci95"]
    assert 0.0 <= lo <= fl["downgrade_rate"] <= hi <= 1.0


def test_penalty_ci_brackets_mean(rows):
    pen = psr.analyze(rows, boot=2000, seed=7)["per_model"]["m1"]["penalty"]
    lo, hi = pen["ci95"]
    assert lo <= pen["mean"] <= hi


def test_bh_is_monotone_and_at_least_raw():
    # ascending raw p -> adjusted must be non-decreasing and never below raw.
    raw = {"a": 0.001, "b": 0.02, "c": 0.04, "d": 0.5}
    adj = psr.benjamini_hochberg(raw)
    for k in raw:
        assert adj[k] >= raw[k] - 1e-9
    ordered = sorted(raw, key=lambda k: raw[k])
    seq = [adj[k] for k in ordered]
    assert seq == sorted(seq)                       # monotone in raw ranking
    assert all(0.0 <= v <= 1.0 for v in seq)


def test_bh_passes_through_undefined_pvalues():
    adj = psr.benjamini_hochberg({"a": 0.01, "b": None})
    assert adj["b"] is None
    assert adj["a"] == pytest.approx(0.01)          # single defined test: q == raw


def test_bh_applied_across_models(rows):
    bundle = psr.analyze(rows, boot=200, seed=7)
    assert bundle["benjamini_hochberg"]["n_tests"] == 2
    for m in ("m1", "m2"):
        st = bundle["per_model"][m]["sign_test"]
        assert st["p_bh"] >= st["p_raw"] - 1e-9
    # m2 (10 vs 1) is the stronger asymmetry, so its adjusted p is the smaller.
    assert (bundle["per_model"]["m2"]["sign_test"]["p_bh"]
            <= bundle["per_model"]["m1"]["sign_test"]["p_bh"])


def test_deterministic_on_fixed_seed(rows):
    a = psr.analyze(rows, boot=1000, seed=7)
    b = psr.analyze(rows, boot=1000, seed=7)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_main_writes_bundle_and_summary(rows, tmp_path, capsys):
    rows_path = tmp_path / "urgency_shift.json"
    rows_path.write_text(json.dumps({"summary": {}, "rows": rows}), encoding="utf-8")
    out_path = tmp_path / "rigor.json"
    rc = psr.main(["--rows", str(rows_path), "--out", str(out_path),
                   "--boot", "300", "--seed", "7"])
    assert rc == 0
    bundle = json.loads(out_path.read_text(encoding="utf-8"))
    assert bundle["source"] == str(rows_path)
    assert set(bundle["models"]) == {"m1", "m2"}
    out = capsys.readouterr().out
    assert "paired-stats rigor" in out
    assert "pseudoreplication gap" in out
