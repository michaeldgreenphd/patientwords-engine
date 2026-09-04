"""Amendment 1 holdout split (scripts/tierb_split.py) - the pre-registered
90/10 exploration/holdout assignment for Tier B pairs.

The split must be deterministic and stable across sessions: a pair's split
membership is part of the pre-registration, so an algorithm drift (different
hash, different modulus, different encoding) would silently unblind the
holdout. The pinned examples below fail loudly on any such drift.
"""

import importlib.util
import json
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tierb_split.py"
_SPEC = importlib.util.spec_from_file_location("tierb_split", _MODULE_PATH)
tierb_split = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tierb_split)

_RIGOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "paired_stats_rigor.py"
_RSPEC = importlib.util.spec_from_file_location("paired_stats_rigor", _RIGOR_PATH)
rigor = importlib.util.module_from_spec(_RSPEC)
_RSPEC.loader.exec_module(rigor)


def test_holdout_membership_is_pinned():
    # Values computed once at implementation time (2026-07-10). If any of
    # these flip, the assignment algorithm changed and the pre-registered
    # split is broken - do NOT update the expectations without flagging a
    # pre-registration amendment.
    assert tierb_split.is_holdout("The patient reports symptom 4.")
    assert tierb_split.is_holdout("The patient reports symptom 13.")
    assert not tierb_split.is_holdout("The patient reports symptom 0.")
    assert not tierb_split.is_holdout("The patient reports symptom 1.")


def test_holdout_rate_near_ten_percent():
    n = sum(tierb_split.is_holdout(f"phrase {i}") for i in range(10000))
    assert 0.08 <= n / 10000 <= 0.12


def test_empty_prompt_stays_explore():
    assert not tierb_split.is_holdout(None)
    assert not tierb_split.is_holdout("")


def test_batch_gating_by_start_stamp():
    start = "20260710T011438Z"
    assert tierb_split.is_tierb_batch("pairs_20260710T011743Z", start)      # after start
    assert not tierb_split.is_tierb_batch("pairs_20260707T025842Z", start)  # Tier A
    assert not tierb_split.is_tierb_batch("dialects_20260708T215356Z", start)
    assert not tierb_split.is_tierb_batch("downgrades_txhaiku", start)
    assert not tierb_split.is_tierb_batch("pairs_20260710T011743Z", None)   # pre-start


def test_stamp_rows_flags_only_tierb(tmp_path):
    dash = tmp_path / "dashboard.json"
    dash.write_text(json.dumps({"tierb": {"start_utc": "2026-07-10T01:14:38Z"}}))
    rows = [
        {"batch": "pairs_20260710T011743Z", "clinical_prompt": "The patient reports symptom 4."},
        {"batch": "pairs_20260710T011743Z", "clinical_prompt": "The patient reports symptom 0."},
        {"batch": "pairs_20260707T025842Z", "clinical_prompt": "The patient reports symptom 4."},
    ]
    n = tierb_split.stamp_rows(rows, dashboard_path=str(dash))
    assert n == 1
    assert rows[0]["tierb_split"] == "holdout"
    assert rows[1]["tierb_split"] == "explore"
    assert "tierb_split" not in rows[2]  # Tier A rows carry no flag


def test_stamp_rows_noop_before_tierb_start(tmp_path):
    dash = tmp_path / "dashboard.json"
    dash.write_text(json.dumps({"tierb": {"start_utc": None}}))
    rows = [{"batch": "pairs_20260710T011743Z", "clinical_prompt": "x"}]
    assert tierb_split.stamp_rows(rows, dashboard_path=str(dash)) == 0
    assert "tierb_split" not in rows[0]


def test_rigor_loader_excludes_holdout_rows_phrase_keyed(tmp_path):
    # 2026-07-14: exclusion is phrase-keyed - a phrase flagged holdout anywhere
    # is excluded everywhere, including split-less re-run rows of that phrase.
    bundle = tmp_path / "rows.json"
    bundle.write_text(json.dumps({"rows": [
        {"model": "m", "clinical_prompt": "PH", "tierb_split": "holdout"},
        {"model": "m", "clinical_prompt": "PH"},                       # leak row
        {"model": "m", "clinical_prompt": "PE", "tierb_split": "explore"},
        {"model": "m", "clinical_prompt": "PA"},
    ]}))
    kept = rigor.load_rows(str(bundle))
    assert {r["clinical_prompt"] for r in kept} == {"PE", "PA"}


def test_collector_stamps_and_aggregates_on_exploration_split():
    # urgency_shift.py runs argparse at import, so tripwire on source: the
    # stamping call must exist and aggregates must run on the filtered rows.
    src = (Path(__file__).resolve().parents[1] / "scripts" / "urgency_shift.py").read_text(
        encoding="utf-8")
    assert "stamp_rows(rows)" in src
    assert 'arows = [r for r in rows if r.get("tierb_split") != "holdout"]' in src
    assert '"measurements": len(arows)' in src


def test_publish_paths_withhold_holdout():
    # 2026-07-14 owner decision: every public export withholds confirmatory-
    # holdout phrases. The three publishers run argparse at import (or write on
    # import), so tripwire on source: each must gate on is_tierb_batch +
    # is_holdout before emitting a pair/row.
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name in ("export_frontend_simulated.py", "export_archive.py"):
        src = (scripts / name).read_text(encoding="utf-8")
        assert "is_holdout" in src, f"{name} lost its holdout gate"
        assert "withheld_holdout += 1" in src, f"{name} lost its withheld counter"
    # the collector gates on stamped rows (phrase-keyed) rather than re-hashing
    collector_src = (scripts / "urgency_shift.py").read_text(encoding="utf-8")
    assert "_holdout_phrases" in collector_src
    assert 'r["clinical_prompt"] not in _holdout_phrases' in collector_src


def test_screen_sensitivity_scope_matches_confirmatory():
    # the sweep must mirror the rigor population: observational pairs_* only,
    # logits backend only, holdout excluded (referee worklist item 12)
    src = (Path(__file__).resolve().parents[1] / "scripts" / "screen_sensitivity.py").read_text(
        encoding="utf-8")
    assert 'r"pairs_\\d{8}T\\d{6}Z"' in src
    assert '"logits"' in src
    assert "is_holdout" in src


def test_site_copy_floors_probe_models():
    # 3-pair probe models must not reach the public comparison page until a
    # real measurement set lands (owner: incorporate models "when results land")
    src = _RIGOR_PATH.read_text(encoding="utf-8")
    assert "MIN_SITE_PHRASES = 30" in src
    assert 'v["penalty"]["n_phrases"] >= MIN_SITE_PHRASES' in src
