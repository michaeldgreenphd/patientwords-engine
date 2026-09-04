"""payload.summary builder (scripts/payload_summary.py) — offline (audit M1).

Pins the phrase-dedupe (rigor semantics with the collector's batch#index
fallback), the screened/measured/flip totals the home strip needs, the
holdout-adjusted public denominator, and CI determinism.
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "payload_summary", _ROOT / "scripts" / "payload_summary.py")
ps = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ps)


def scen(batch, idx, phrase, pen, flipped=False, screened=False):
    s = {"batch": batch, "batch_index": idx,
         "prompts": {"clinical": phrase} if phrase else {},
         "language_penalty": pen, "flipped": flipped}
    if screened:
        s["screening"] = {"status": "screened_out"}
    return s


def test_phrase_dedupe_and_fallback_key():
    rows = [scen("b", 1, "same phrase", -0.4),
            scen("b", 2, "same phrase", -0.2),      # re-trace: averaged, not double-counted
            scen("b", 3, None, -0.1),               # missing prompt -> batch#index fallback
            scen("b", 4, None, -0.3)]               # distinct fallback keys stay distinct
    out = ps.build_summary(rows, accepted=10, holdout_withheld=2, n_boot=50)
    pen = out["penalty"]
    assert pen["n_phrases"] == 3 and pen["n_scored_rows"] == 4
    assert pen["mean_phrase_deduped"] == round((-0.3 + -0.1 + -0.3) / 3, 4)
    assert pen["mean_rows_raw"] == round((-0.4 - 0.2 - 0.1 - 0.3) / 4, 4)
    assert pen["population"] == "public_payload"


def test_totals_screening_flips_and_public_denominator():
    rows = [scen("b", 1, "p1", -0.2, flipped=True),
            scen("b", 2, "p2", None, screened=True),   # screened: null penalty, not measured
            scen("b", 3, "p3", 0.1)]
    out = ps.build_summary(rows, accepted=100, holdout_withheld=9, n_boot=50)
    t = out["totals"]
    assert t == {"accepted": 100, "accepted_public": 91, "holdout_withheld": 9,
                 "measured": 2, "screened_out": 1, "flipped_base": 1,
                 "steered_measured": 0, "steered_flipped_base": 0, "steered_batches": []}


def test_steered_scenarios_are_counted_but_never_pooled():
    """Steered batches publish, and stay out of every headline figure.

    Owner decision 2026-08-15: they were generated at topics already known to
    flip, so pooling them would let the selection inflate the site's share.
    """
    plain = [scen("b", 1, "p1", -0.2, flipped=True), scen("b", 2, "p2", -0.2)]
    steered = [dict(scen("s", 1, "s1", -0.9, flipped=True), steered=True),
               dict(scen("s", 2, "s2", -0.9, flipped=True), steered=True, batch="s")]
    for row in steered:
        row["batch"] = "s"
    out = ps.build_summary(plain + steered, accepted=10, holdout_withheld=0, n_boot=50)
    t = out["totals"]
    assert t["measured"] == 2 and t["flipped_base"] == 1          # steered excluded
    assert t["steered_measured"] == 2 and t["steered_flipped_base"] == 2
    assert t["steered_batches"] == ["s"]
    # the -0.9 steered penalties must not drag the published mean
    assert out["penalty"]["n_scored_rows"] == 2
    assert out["penalty"]["mean_rows_raw"] == round(-0.2, 4)


def test_ci_deterministic_and_none_under_three_phrases():
    rows = [scen("b", i, f"p{i}", -0.1 * i) for i in range(1, 6)]
    a = ps.build_summary(rows, 5, 0, n_boot=200)["penalty"]["ci95"]
    b = ps.build_summary(rows, 5, 0, n_boot=200)["penalty"]["ci95"]
    assert a == b and a[0] <= a[1]
    tiny = [scen("b", 1, "p1", -0.1), scen("b", 2, "p2", -0.2)]
    assert ps.build_summary(tiny, 2, 0, n_boot=50)["penalty"]["ci95"] is None


def test_bool_penalty_never_counts_as_number():
    rows = [scen("b", 1, "p1", True), scen("b", 2, "p2", -0.2)]
    out = ps.build_summary(rows, 2, 0, n_boot=50)
    assert out["penalty"]["n_scored_rows"] == 1
