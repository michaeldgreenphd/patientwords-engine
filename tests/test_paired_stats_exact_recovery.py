"""scripts/paired_stats.py validity: a side the exact read recorded as missing is not recovered from a neighbour.

When a hand-measured pair's live penalty is null, the validity section recovers both sides from the stored spreads
with a tolerant match (case, and a fragment in either direction), which would hand a new trace's missing side a
neighbour's value. Results that carry a ``target_read`` block (written since 2026-10-07) are recovered exactly;
results written before keep the tolerant recovery, so the committed validity numbers are unchanged. Tokens are
abstract stand-ins.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def validity(tmp_path: Path, result: dict[str, Any]) -> dict[str, Any]:
    (tmp_path / "data/measured").mkdir(parents=True)
    (tmp_path / "trace_out/hp").mkdir(parents=True)
    (tmp_path / "rows.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    (tmp_path / "data/measured/hp.json").write_text(json.dumps([{
        "top_prompt": "c", "bottom_prompt": "p", "target_clinical_token": " xab",
        "provenance": {"patient": {"observed_prob": 0.1}, "clinical": {"observed_prob": 0.3}}}]), encoding="utf-8")
    (tmp_path / "trace_out/hp/batch_summary.part_01.json").write_text(json.dumps({"results": [result]}),
                                                                       encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts/paired_stats.py"), "--rows", "rows.json",
                    "--hand-pairs", "data/measured/hp.json", "--out", "out.json", "--models", "gemma-2-2b",
                    "--boot", "10"], cwd=tmp_path, check=True, capture_output=True)
    return json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))["validity"]


SPREADS = {"clinical": [['Output " xab"', 0.4]], "patient": [['Output " xabi"', 0.2]]}


def test_a_new_traces_missing_side_is_censored_not_recovered_from_a_neighbour(tmp_path):
    v = validity(tmp_path, {"index": 1, "language_penalty": None, "predictive_spread": SPREADS,
                            "target_read": {"rule": "exact_token/2026-10-07"}})
    assert v["matched"] == 0
    assert v["censored"] == [{"index": 1, "p_clinical": 0.4, "anchor": "exact", "patient_floor": 0.2,
                              "penalty_upper_bound": -0.2, "hand_penalty": -0.2}]


def test_an_older_result_keeps_the_tolerant_recovery(tmp_path):
    # the committed validity numbers were computed this way; changing it is the owner's decision
    v = validity(tmp_path, {"index": 1, "language_penalty": None, "predictive_spread": SPREADS})
    assert v["matched"] == 1 and "censored" not in v
