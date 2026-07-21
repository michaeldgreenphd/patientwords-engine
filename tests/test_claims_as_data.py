"""M7 claim emissions: threshold-classification sentences become data fields.

The four generators are script-style or emit inside main(), so these pins
read the source per the repo pattern: each derived claim sentence on the
technical/translation pages has a generator-side verdict field with the
page's exact semantics, and the pages keep their inline checks as fallback.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1] / "scripts"


def src(name):
    return (_ROOT / name).read_text(encoding="utf-8")


def test_convergence_all_secondary_end_below_zero():
    s = src("convergence_tracker.py")
    assert '"ends_below_zero": ends_below' in s
    assert '"all_secondary_end_below_zero":' in s
    assert 'if len(mids) > 1 else None' in s


def test_translation_minority_lift_with_recorded_threshold():
    s = src("translation_scale.py")
    assert '"median_near_zero_threshold": 0.01' in s
    assert '"instruction_tuned_minority_lift":' in s
    assert 'abs(s["median_recovery"]) < 0.01' in s
    assert 'if it_models else None' in s


def test_model_stats_zero_crossers():
    s = src("paired_stats_rigor.py")
    assert '"zero_crossers_per_model":' in s
    assert '"zero_crossers_simultaneous":' in s
    assert 'isinstance(ci[1], (int, float)) and ci[1] >= 0' in s


def test_jlens_window_holds_and_dominant_class():
    s = src("jlens_insights.py")
    assert '"window_capture_exceeds_hijack_at_every_k":' in s
    assert 'all(ws[k]["capture"] > ws[k]["hijack"] for k in ws_keys)' in s
    assert '"dominant_failure_class":' in s
