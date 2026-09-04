"""Offline tests for the negative-control statistics script.

Synthetic penalties only; the seams under test are the ones an independent
reviewer found the hand-computed write-up got wrong or could not regenerate.
"""

import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ncs = _load("negative_control_stats")


def row(index, clin, pat, n_clin=10, n_pat=14, top_c="a", top_p="a"):
    return {"index": index,
            "prompts": {"clinical": f"c{index}", "patient": f"p{index}"},
            "probabilities": {"clinical": clin, "patient": pat},
            "token_parity": {"clinical": {"n_engine": n_clin, "match": True},
                             "patient": {"n_engine": n_pat, "match": True}},
            "predictive_spread": {"clinical": [[top_c, 0.5]], "patient": [[top_p, 0.5]]}}


def test_same_seed_regenerates_identical_numbers():
    """The rule the first write-up broke: a seed that exists only in a shell
    one-liner is not reproducible. Two runs, one seed, byte-identical stats."""
    rows = {i: row(i, 0.5, 0.5 - 0.01 * i) for i in range(1, 21)}
    a = ncs.arm_stats(rows, random.Random(7), 500)
    b = ncs.arm_stats(rows, random.Random(7), 500)
    a.pop("penalties_by_index")
    b.pop("penalties_by_index")
    assert a == b


def test_token_delta_comes_from_the_run_not_from_word_counts():
    """The model sees tokens; the control matched in words but overshot in
    tokens (+5.60 vs +4.14). The stat must read token_parity.n_engine."""
    rows = {1: row(1, 0.5, 0.4, n_clin=10, n_pat=17), 2: row(2, 0.5, 0.4, n_clin=10, n_pat=13)}
    s = ncs.arm_stats(rows, random.Random(1), 100)
    assert s["token_delta_mean"] == 5.0
    assert s["token_delta_range"] == [3, 7]


def test_drop_k_reports_the_share_and_whether_zero_is_still_excluded():
    """Three pairs carried 45% of the real effect; dropping them put zero back
    inside the interval. The sensitivity must surface exactly that."""
    pens = {i: -0.01 for i in range(1, 48)}
    pens.update({48: -0.4, 49: -0.45, 50: -0.5})   # three outliers
    sens = ncs.drop_k_sensitivity(pens, random.Random(3), 2000, ks=(3,))
    s = sens[0]
    assert s["dropped_indices"] == [50, 49, 48]
    assert 0.7 < s["dropped_share_of_total"] < 0.8
    assert s["mean"] == -0.01


def test_redirects_count_top1_changes_between_sides():
    rows = {1: row(1, .5, .4, top_c="a", top_p="b"), 2: row(2, .5, .4, top_c="a", top_p="a")}
    assert ncs.arm_stats(rows, random.Random(1), 100)["top1_redirects"] == 1


def test_sd_ratio_and_variance_ratio_are_both_reported():
    """'33% of the variance' reads as an sd ratio and understates noise; the
    artifact carries both so the write-up cannot quote the flattering one alone."""
    out = json.loads((ROOT / "ops" / "negative_control_20260904.json").read_text())
    r = out["spread_ratio"]
    assert abs(r["sd_ratio_control_over_treatment"] ** 2 - r["variance_ratio_control_over_treatment"]) < 0.002
    assert out["seed"] == 7 and out["n_boot"] == 10000
