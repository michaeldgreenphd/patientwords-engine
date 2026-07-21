"""Convergence dataset (scripts/convergence_tracker.py) — offline.

Pins the phrase-dedupe unit, the least-alarming tie-break, the cumulative
prefix growth, and main()'s holdout/supplementary exclusions. No network.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "convergence_tracker", _ROOT / "scripts" / "convergence_tracker.py")
ct = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ct)


def row(batch, index, model="gemma-2-2b", phrase="p", pen=-0.2, flipped=False,
        flip_class=None, split=None):
    r = {"batch": batch, "index": index, "model": model, "clinical_prompt": phrase,
         "language_penalty": pen, "flipped": flipped, "flip_class": flip_class}
    if split:
        r["tierb_split"] = split
    return r


def test_phrase_groups_key_and_orphan_fallback():
    rows = [row("pairs_A", 1, phrase="x"), row("pairs_A", 2, phrase="x"),
            row("pairs_B", 3, phrase=None)]
    groups = ct.phrase_groups(rows)
    assert set(groups) == {"x", "pairs_B#3"}
    assert len(groups["x"]) == 2


def test_phrase_label_majority_and_least_alarming_tiebreak():
    dn = row("b", 1, flipped=True, flip_class="downgrade")
    up = row("b", 2, flipped=True, flip_class="upgrade")
    non = row("b", 3)
    assert ct.phrase_label([dn, dn, up]) == "downgrade"        # majority
    assert ct.phrase_label([dn, non]) == "none"                # tie -> least alarming
    assert ct.phrase_label([dn, up]) == "upgrade"              # tie among flips


def test_boot_ci_needs_three_and_is_deterministic():
    assert ct.boot_ci([-0.1, -0.2], seed=7, n_boot=100) == (None, None)
    a = ct.boot_ci([-0.1, -0.2, -0.3, -0.4], seed=7, n_boot=200)
    b = ct.boot_ci([-0.1, -0.2, -0.3, -0.4], seed=7, n_boot=200)
    assert a == b and a[0] <= a[1]


def test_cumulative_points_grow_by_stamp_and_dedupe_phrases():
    s1, s2 = "20260710T000000Z", "20260711T000000Z"
    rows = [row(f"pairs_{s1}", 1, phrase="a", pen=-0.4),
            row(f"pairs_{s1}", 2, phrase="a", pen=-0.2),   # same phrase -> averaged
            row(f"pairs_{s2}", 3, phrase="b", pen=-0.1),
            row("dialects_x", 4, phrase="c", pen=-0.9)]     # non-pairs batch excluded
    pts = ct.cumulative_points(rows, [s1, s2], seed=7, n_boot=50)
    assert [p["n_phrases"] for p in pts] == [1, 2]
    assert pts[0]["mean_penalty"] == -0.3                   # (-0.4 + -0.2)/2, one phrase
    assert pts[1]["through_batch"] == f"pairs_{s2}"


def test_main_excludes_holdout_phrases_and_writes_payload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s1 = "20260710T000000Z"
    bundle = {"rows": [
        row(f"pairs_{s1}", 1, phrase="kept1", pen=-0.2),
        row(f"pairs_{s1}", 2, phrase="kept2", pen=-0.3),
        row(f"pairs_{s1}", 3, phrase="kept3", pen=-0.1),
        row(f"pairs_{s1}", 4, phrase="sealed", pen=-0.9, split="holdout"),
        # the same sealed phrase appearing WITHOUT the flag must still drop
        row(f"pairs_{s1}", 5, phrase="sealed", pen=-0.8),
    ]}
    (tmp_path / "rows.json").write_text(json.dumps(bundle), encoding="utf-8")
    rc = ct.main(["--rows", "rows.json", "--out", "out.json", "--site", "",
                  "--boot", "50", "--seed", "7"])
    assert rc == 0
    payload = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    pts = payload["models"]["gemma-2-2b"]["points"]
    assert pts[-1]["n_phrases"] == 3                        # sealed phrase fully excluded
    assert "Amendment 1" in payload["scope"]
