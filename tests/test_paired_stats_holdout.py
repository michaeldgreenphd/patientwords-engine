"""scripts/paired_stats.py excludes Tier B holdout phrases from its unified-set statistics.

docs/preregistration_tierB.md, Amendment 1: interim analyses use the exploration split only. The exclusion is
phrase-keyed (scripts/tierb_split.drop_holdout_phrase_rows, the rule paired_stats_rigor.load_rows applies): a phrase
flagged holdout on any row is excluded on every row. Until 2026-11-10 this script built its unified set from every
row of the row file. Phrases are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("m1", "m2")
BATCH = "pairs_20260101T000000Z"


def pair_rows(index: int, phrase: str, penalties: tuple[float, float], *, split: str | None = None,
              batch: str = BATCH) -> list[dict[str, Any]]:
    """One phrase measured on both models: one row per model."""
    rows = []
    for model, penalty in zip(MODELS, penalties):
        row: dict[str, Any] = {"batch": batch, "index": index, "model": model, "clinical_prompt": phrase,
                               "language_penalty": penalty, "tier_shift": -1.0 if penalty < -0.2 else 0.0,
                               "flipped": penalty < -0.2, "prompt_words": [5, 7]}
        if split is not None:
            row["tierb_split"] = split
        rows.append(row)
    return rows


def run(tmp_path: Path, name: str, rows: list[dict[str, Any]]) -> tuple[dict[str, Any], str, str]:
    """Run the script on a synthetic row file; return (output document, stdout, stderr)."""
    (tmp_path / f"{name}.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    done = subprocess.run([sys.executable, str(ROOT / "scripts/paired_stats.py"), "--rows", f"{name}.json",
                           "--hand-pairs", "absent.json", "--out", f"{name}_out.json", "--models", *MODELS,
                           "--boot", "50", "--seed", "7"], cwd=tmp_path, check=True, capture_output=True, text=True)
    return json.loads((tmp_path / f"{name}_out.json").read_text(encoding="utf-8")), done.stdout, done.stderr


EXPLORE = (pair_rows(1, "PHRASE-K1", (-0.1, -0.3), split="explore")
           + pair_rows(2, "PHRASE-K2", (-0.2, -0.1), split="explore")
           + pair_rows(3, "PHRASE-K3", (0.05, -0.25)))  # a batch with no split flag
HOLDOUT = (pair_rows(4, "PHRASE-H", (-0.9, -0.8), split="holdout")
           # the same phrase re-run in a batch that carries no split flag: excluded by phrase, not by flag
           + pair_rows(1, "PHRASE-H", (-0.9, -0.8), batch="repeatability_r1"))


def test_a_holdout_phrase_does_not_change_the_statistics(tmp_path):
    without, _, _ = run(tmp_path, "explore", EXPLORE)
    doc, stdout, stderr = run(tmp_path, "all", EXPLORE + HOLDOUT)
    for key in ("unified_set", "per_model", "paired_differences", "length_confound"):
        assert doc[key] == without[key], key
    assert doc["unified_set"]["phrases"] == 3
    excl = doc["holdout_exclusion"]
    assert {k: excl[k] for k in ("rows_read", "rows_with_split_flag", "rows_excluded",
                                 "phrases_excluded", "rows_analyzed")} == {
        "rows_read": 10, "rows_with_split_flag": 6, "rows_excluded": 4, "phrases_excluded": 1, "rows_analyzed": 6}
    assert "excluded 4 rows across 1 holdout phrases" in stderr
    assert json.loads(stdout) == doc  # stdout stays the output JSON; the count line goes to stderr
    # counts only: the phrase itself is never written or printed
    assert "PHRASE-H" not in stdout and "PHRASE-H" not in stderr


def test_a_row_without_a_phrase_key_is_refused(tmp_path):
    rows = EXPLORE + [{"batch": BATCH, "index": 9, "model": "m1", "language_penalty": -0.5, "flipped": True}]
    (tmp_path / "unkeyed.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    done = subprocess.run([sys.executable, str(ROOT / "scripts/paired_stats.py"), "--rows", "unkeyed.json",
                           "--hand-pairs", "absent.json", "--out", "unkeyed_out.json", "--models", *MODELS,
                           "--boot", "50"], cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode != 0
    assert "1 of 7 rows carry no clinical_prompt" in done.stderr
    assert not (tmp_path / "unkeyed_out.json").exists()
