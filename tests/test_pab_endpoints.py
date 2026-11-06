"""scripts/pab_endpoints.py: the PAB frame spec's preregistered endpoints, reported with counts and hashes only.

The harvested utterances are CC-BY-NC-4.0-derived and must never leave the engine as text; these tests pin that the
report carries none, that every entry is accounted for, and that pairs (not entries) are the unit.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("pab_endpoints", _SCRIPTS / "pab_endpoints.py")
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)


def test_every_entry_is_accounted_for_and_reads_are_exact():
    recs = pe.entries()
    assert len(recs) == 52
    with_pen = [r for r in recs if r["penalty"] is not None]
    assert all(r["read_exact"] is True for r in with_pen)
    assert all(r.get("missing_reason") for r in recs if r["penalty"] is None)


def test_pairs_are_the_unit():
    out = pe.endpoint_penalty(pe.entries())
    assert out["pairs_total"] == 13
    assert out["pairs_negative"] + out["pairs_positive"] + out["pairs_zero"] == out["pairs_with_a_penalty"]


def test_the_report_carries_no_harvested_text(tmp_path):
    out = tmp_path / "pab.json"
    assert pe.main(["--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    batch = json.loads(pe.BATCH.read_text(encoding="utf-8"))
    for e in batch:
        for span in e["generation"]["spans"].values():
            assert span[:30] not in text
