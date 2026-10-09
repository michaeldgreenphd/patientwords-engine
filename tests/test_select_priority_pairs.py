"""scripts/select_priority_pairs.py: the deterministic medgemma-1.5-4b-it priority selection (offline, synthetic).

Identifiers only: no prompt text is read into the selection, and the placeholders here are never study stimuli.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("select_priority_pairs", ROOT / "scripts" / "select_priority_pairs.py")
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

A, B = "pairs_20990101T000000Z", "pairs_20990102T000000Z"


def _bundle():
    item = lambda iid, sid, rank, subset="main_study", fam="tracing_pair": {  # noqa: E731
        "item_id": iid, "family": fam, "display": {"text": "never read"},
        "provenance": {"subset": subset, "source_id": sid, "rank": rank}}
    return {"items": [item("t2", f"{B}#4", 2), item("t1", f"{A}#9", 1),
                      item("p1", "pilot#1", 1, subset="pilot_run2"), item("a1", f"{A}#1", 1, fam="advice")]}


def _rows():
    rows = []
    for m in ("m1", "m2", "m3"):
        rows.append({"model": m, "batch": A, "index": 2, "flip_class": "downgrade"})     # 3 models
        rows.append({"model": m, "batch": A, "index": 9, "flip_class": "upgrade"})       # 3 models, also task set
    rows.append({"model": "m1", "batch": B, "index": 1, "flip_class": "downgrade"})      # 2 models
    rows.append({"model": "m2", "batch": B, "index": 1, "flip_class": "upgrade"})
    rows.append({"model": "m3", "batch": B, "index": 1, "flip_class": "lateral"})        # not directional
    rows.append({"model": "gemma-4-e2b", "batch": B, "index": 3, "flip_class": "downgrade"})  # held: not counted
    return rows


def test_task_set_is_main_study_tracing_pairs_in_rank_order():
    assert sp.task_set_pairs(_bundle()) == [(A, 9), (B, 4)]


def test_consensus_counts_directional_flips_of_the_counted_models_only():
    counts = sp.consensus_counts(_rows(), {"m1", "m2", "m3"})
    assert counts == {(A, 2): 3, (A, 9): 3, (B, 1): 2}


def test_selection_order_dedupe_seal_and_cap():
    sizes = {A: 10, B: 5}
    sealed = lambda b, i: (b, i) == (B, 4)  # noqa: E731
    counts = sp.consensus_counts(_rows(), {"m1", "m2", "m3"})
    pairs, stats = sp.select(sp.task_set_pairs(_bundle()), counts, 2, 10, sizes, sealed)
    assert [(p["batch"], p["index"]) for p in pairs] == [(A, 9), (A, 2), (B, 1)]
    assert pairs[0]["reasons"] == ["task_set", "tier_flip_in_3_models"]
    assert stats["excluded_sealed"] == 1 and stats["duplicates_merged"] == 1 and stats["kept"] == 3
    capped, cstats = sp.select(sp.task_set_pairs(_bundle()), counts, 3, 1, sizes, sealed)
    assert [(p["batch"], p["index"]) for p in capped] == [(A, 9)] and cstats["dropped_by_cap"] == 1
    # deterministic: the same inputs give the same selection
    again, _ = sp.select(sp.task_set_pairs(_bundle()), counts, 2, 10, sizes, sealed)
    assert again == pairs


def test_a_pair_outside_the_committed_batches_is_dropped_by_name():
    pairs, stats = sp.select([(A, 11), ("pilot", 1)], {}, 5, 10, {A: 10}, lambda b, i: False)
    assert pairs == [] and stats["excluded_not_a_batch_pair"] == 2


def test_the_committed_proposal_is_identifiers_only_and_consistent():
    """The proposal committed beside this script names only (batch, index) pairs that exist, none sealed."""
    path = ROOT / "data" / "selections" / "medgemma15_priority_20261009.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["schema"] == sp.SCHEMA and doc["randomness"].startswith("none")
    assert doc["counts"]["kept"] == len(doc["pairs"]) <= doc["criteria"]["cap"]
    for p in doc["pairs"]:
        assert set(p) == {"batch", "index", "reasons", "tier_flip_models"}
        n = len(json.loads((ROOT / "data" / "simulated" / f"{p['batch']}.json").read_text(encoding="utf-8")))
        assert 1 <= p["index"] <= n
        assert not sp.sealed_pair(p["batch"], p["index"], None)
