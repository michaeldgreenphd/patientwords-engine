"""Tier-vocabulary sensitivity bounds (scripts/tier_sensitivity.py).

Synthetic vocabulary and rows only - no medical vocabulary in this file.
Phrases are abstract placeholders (PHRASE-A, PHRASE-H), never study stimuli.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "tier_sensitivity", _ROOT / "scripts" / "tier_sensitivity.py")
ts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ts)

VOCAB = {"alpha": {"tier": 3}, "beta": {"tier": 1}, "gamma": {"tier": 2}}
SPEC = {"deciders": ["gamma"], "blockers": [], "advice_tier_collapses": {"merge": [["t2", "t3"]]}}


def row(model, top_c, top_p, phrase="PHRASE-A", split=None, batch="pairs_20260101T000000Z"):
    r = {"model": model, "batch": batch, "clinical_prompt": phrase, "flipped": True,
         "top_clinical": top_c, "top_patient": top_p}
    if split is not None:
        r["tierb_split"] = split
    return r


def run_main(tmp_path, rows, name, extra=()):
    """Run the script's main on a synthetic row file; return the path of its output."""
    rows_file = tmp_path / f"{name}_rows.json"
    rows_file.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    tiers = tmp_path / "tiers.json"
    tiers.write_text(json.dumps({"tokens": VOCAB}), encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    out = tmp_path / f"{name}_out.json"
    ts.main(["--rows", str(rows_file), "--tiers", str(tiers), "--spec", str(spec),
             "--advice", str(tmp_path / "absent.json"), "--out", str(out), *extra])
    return out


def test_scenarios_bracket_the_flagged_token():
    rows = [
        row("m1", "alpha", "beta"),   # 3 -> 1: downgrade under every scenario
        row("m1", "alpha", "gamma"),  # 3 -> 2 baseline; excluded when gamma dropped;
                                      # 3 -> 0 floor (down); 3 -> 4 ceiling (UP)
    ]
    nt = ts.next_token_scenarios(rows, VOCAB, SPEC)
    assert nt["baseline"]["m1"] == {"downgrades": 2, "upgrades": 0, "sign_p": 0.5}
    assert nt["exclude"]["m1"]["downgrades"] == 1  # the gamma call went uninformative
    assert nt["floor"]["m1"]["downgrades"] == 2
    assert nt["ceiling"]["m1"] == {"downgrades": 1, "upgrades": 1, "sign_p": 1.0}
    v = ts.verdicts(nt)
    assert v["m1"]["asymmetry_all_scenarios"] is False  # the ceiling tie breaks it


def test_advice_collapse_merges_adjacent_tiers():
    payload = {
        "tier_order": ["t1", "t2", "t3", "t4"],
        "scenarios": [{"tier_summary": [
            {"clinical": "t3", "patient": "t2"},   # down; merged away under merge
            {"clinical": "t1", "patient": "t4"},   # up in both ladders
        ]}],
    }
    out = ts.advice_scenarios(payload, SPEC)
    assert out["baseline"] == {"down": 1, "up": 1, "unchanged": 0, "sign_p": 1.0}
    assert out["merge"] == {"down": 0, "up": 1, "unchanged": 1, "sign_p": 1.0}


def test_output_file_shape(tmp_path):
    out = run_main(tmp_path, [row("m1", "alpha", "beta")], "shape")
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["next_token"]) == {"baseline", "exclude", "floor", "ceiling"}
    assert doc["next_token_verdicts"]["m1"]["asymmetry_all_scenarios"] is True


EXPLORE_ROWS = [
    row("m1", "alpha", "beta", phrase="PHRASE-K1", split="explore"),  # downgrade
    row("m1", "beta", "alpha", phrase="PHRASE-K2"),                   # upgrade, a batch with no split flag
]
HOLDOUT_ROWS = [
    row("m1", "alpha", "beta", phrase="PHRASE-H", split="holdout"),
    # the same phrase re-run in a batch that carries no split flag: excluded by phrase, not by flag
    row("m1", "alpha", "beta", phrase="PHRASE-H", batch="repeatability_r1"),
    # a model whose only flipped row is a holdout row must not appear at all
    row("m2", "alpha", "beta", phrase="PHRASE-H", split="holdout"),
]


def test_a_holdout_phrase_does_not_change_the_counts(tmp_path, capsys):
    """Amendment 1: an interim analysis counts the exploration split only.

    Until 2026-11-10 main counted every row of the row file, so the three rows
    of the holdout phrase added two downgrades to m1 and created m2."""
    without = json.loads(run_main(tmp_path, EXPLORE_ROWS, "explore").read_text(encoding="utf-8"))
    capsys.readouterr()
    out_path = run_main(tmp_path, EXPLORE_ROWS + HOLDOUT_ROWS, "all")
    printed = capsys.readouterr().out
    text = out_path.read_text(encoding="utf-8")
    doc = json.loads(text)

    assert doc["next_token"] == without["next_token"]
    assert doc["next_token_verdicts"] == without["next_token_verdicts"]
    assert doc["next_token"]["baseline"] == {"m1": {"downgrades": 1, "upgrades": 1, "sign_p": 1.0}}
    excl = doc["holdout_exclusion"]
    assert {k: excl[k] for k in ("rows_read", "rows_with_split_flag", "rows_excluded",
                                 "phrases_excluded", "rows_analyzed")} == {
        "rows_read": 5, "rows_with_split_flag": 3, "rows_excluded": 3, "phrases_excluded": 1, "rows_analyzed": 2}
    assert "excluded 3 rows across 1 holdout phrases" in printed
    # counts only: the phrase itself is never written or printed
    assert "PHRASE-H" not in text and "PHRASE-H" not in printed


def test_an_unstamped_row_file_is_reported_as_such(tmp_path, capsys):
    """No tierb_split flag anywhere: nothing was excluded because nothing could be,
    and the output and the printed note say so."""
    out_path = run_main(tmp_path, [row("m1", "alpha", "beta")], "unstamped")
    excl = json.loads(out_path.read_text(encoding="utf-8"))["holdout_exclusion"]
    assert (excl["rows_with_split_flag"], excl["rows_excluded"], excl["phrases_excluded"]) == (0, 0, 0)
    printed = capsys.readouterr().out
    assert "excluded 0 rows across 0 holdout phrases" in printed
    assert "no row carries a tierb_split flag" in printed


def test_a_row_without_a_phrase_key_is_refused(tmp_path):
    """A row that cannot be matched to a phrase cannot be checked against the holdout:
    the script stops before it writes anything."""
    unkeyed = {"model": "m1", "flipped": True, "top_clinical": "alpha", "top_patient": "beta"}
    with pytest.raises(RuntimeError, match="1 of 2 rows carry no clinical_prompt"):
        run_main(tmp_path, [row("m1", "alpha", "beta"), unkeyed], "unkeyed")
    assert not (tmp_path / "unkeyed_out.json").exists()


def test_the_output_records_its_inputs(tmp_path):
    """The file says what it was computed from: each input's path and sha256, a null
    sha256 for the absent advice payload, the generating script, and the caller's note."""
    out = run_main(tmp_path, EXPLORE_ROWS, "src", extra=("--note", "inputs read from commit abc1234"))
    doc = json.loads(out.read_text(encoding="utf-8"))
    rows_file = tmp_path / "src_rows.json"
    assert doc["sources"]["rows"] == {"path": str(rows_file),
                                      "sha256": hashlib.sha256(rows_file.read_bytes()).hexdigest()}
    for key, name in (("tiers", "tiers.json"), ("spec", "spec.json")):
        assert doc["sources"][key]["sha256"] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    assert doc["sources"]["advice"] == {"path": str(tmp_path / "absent.json"), "sha256": None}
    assert doc["advice_pooled"] == {}
    assert doc["note"] == "inputs read from commit abc1234"
    assert doc["_provenance"]["generator"] == "scripts/tier_sensitivity.py"
    assert set(doc["_provenance"]) == {"generator", "engine_sha", "generated_utc"}
    # without --note the field is present and null
    assert json.loads(run_main(tmp_path, EXPLORE_ROWS, "nonote").read_text(encoding="utf-8"))["note"] is None
