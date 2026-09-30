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

import pytest

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


# --- sealed_pair: stamp_rows' rule for one row, failing closed (2026-09-30) ---------
# Synthetic prompts only. The pinned hashes above: symptom 4 and 13 hash holdout,
# symptom 0 and 1 hash explore.
HOLD_A = "The patient reports symptom 4."
HOLD_B = "The patient reports symptom 13."
EXPLORE_A = "The patient reports symptom 0."
EXPLORE_B = "The patient reports symptom 1."
TIERB = "pairs_20260711T000000Z"


def _seal_fixture(tmp_path, start="2026-07-10T01:14:38Z", batches=None):
    """A dashboard and a batch directory; the default Tier B batch registers HOLD_A
    (pair 1) and holds one explore pair (pair 2)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    dash = tmp_path / "dashboard.json"
    dash.write_text(json.dumps({"tierb": {"start_utc": start}}), encoding="utf-8")
    sim = tmp_path / "simulated"
    sim.mkdir()
    if batches is None:
        batches = {TIERB: [{"top_prompt": HOLD_A}, {"top_prompt": EXPLORE_A}]}
    for stem, content in batches.items():
        text = content if isinstance(content, str) else json.dumps(content)
        (sim / f"{stem}.json").write_text(text, encoding="utf-8")
    return {"dashboard_path": dash, "simulated_dir": sim}


def test_sealed_pair_phrase_clause_seals_any_stem(tmp_path):
    fx = _seal_fixture(tmp_path)
    # Amendment 3: a registered phrase is sealed on alias, re-run and Tier A stems too
    assert tierb_split.sealed_pair("repeatability_r1", 7, HOLD_A, **fx)
    assert tierb_split.sealed_pair(f"{TIERB}_txopus", 1, HOLD_A, **fx)
    assert tierb_split.sealed_pair("pairs_20260707T000000Z", 3, HOLD_A, **fx)
    # outside Tier B only the phrase clause applies: a holdout hash alone does not seal
    assert not tierb_split.sealed_pair("repeatability_r1", 7, HOLD_B, **fx)
    assert not tierb_split.sealed_pair("repeatability_r1", 7, EXPLORE_A, **fx)


def test_sealed_pair_accepted_hash_clause(tmp_path):
    fx = _seal_fixture(tmp_path)
    # a probe-extended trace-time prompt that hashes explore; the accepted one hashes holdout
    assert tierb_split.sealed_pair(TIERB, 1, EXPLORE_B, **fx)
    assert not tierb_split.sealed_pair(TIERB, 2, EXPLORE_B, **fx)


def test_sealed_pair_trace_time_clause_is_tier_b_only(tmp_path):
    fx = _seal_fixture(tmp_path)
    # accepted prompt of pair 2 hashes explore, but its trace-time prompt hashes holdout
    assert tierb_split.sealed_pair(TIERB, 2, HOLD_B, **fx)
    assert not tierb_split.sealed_pair(f"{TIERB}_txopus", 2, HOLD_B, **fx)


def test_sealed_pair_matches_stamp_rows(tmp_path):
    fx = _seal_fixture(tmp_path)
    rows = [{"batch": b, "index": i, "clinical_prompt": p} for b, i, p in (
        (TIERB, 1, EXPLORE_B), (TIERB, 2, HOLD_B), (TIERB, 2, EXPLORE_B),
        ("repeatability_r1", 5, HOLD_A), ("repeatability_r1", 5, HOLD_B),
        ("pairs_20260707T000000Z", 1, EXPLORE_A))]
    tierb_split.stamp_rows(rows, dashboard_path=str(fx["dashboard_path"]),
                           simulated_dir=str(fx["simulated_dir"]))
    for r in rows:
        assert tierb_split.sealed_pair(r["batch"], r["index"], r["clinical_prompt"], **fx) == (
            r.get("tierb_split") == "holdout")


def test_sealed_pair_promptless_row_uses_accepted_prompt(tmp_path):
    fx = _seal_fixture(tmp_path, batches={
        TIERB: [{"top_prompt": HOLD_A}, {"top_prompt": EXPLORE_A}],
        "steer_set": [{"top_prompt": EXPLORE_B}, {"top_prompt": HOLD_A}]})
    assert tierb_split.sealed_pair(TIERB, 1, None, **fx)
    assert not tierb_split.sealed_pair(TIERB, 2, "", **fx)
    assert tierb_split.sealed_pair("steer_set", 2, None, **fx)      # registered phrase, non-Tier-B file
    assert not tierb_split.sealed_pair("steer_set", 1, None, **fx)
    with pytest.raises(tierb_split.SealError):                      # no file to supply a prompt
        tierb_split.sealed_pair("no_such_set", 1, None, **fx)
    with pytest.raises(tierb_split.SealError):
        tierb_split.sealed_pair(None, 1, None, **fx)


def test_sealed_pair_refuses_without_start_stamp(tmp_path):
    fx = _seal_fixture(tmp_path, start=None)
    with pytest.raises(tierb_split.SealError, match="start_utc"):
        tierb_split.sealed_pair("repeatability_r1", 1, EXPLORE_A, **fx)
    missing = {"dashboard_path": tmp_path / "absent.json", "simulated_dir": fx["simulated_dir"]}
    with pytest.raises(tierb_split.SealError, match="start_utc"):
        tierb_split.sealed_pair("repeatability_r1", 1, EXPLORE_A, **missing)


def test_sealed_pair_refuses_empty_phrase_set(tmp_path):
    fx = _seal_fixture(tmp_path, batches={TIERB: [{"top_prompt": EXPLORE_A}]})
    with pytest.raises(tierb_split.SealError, match="empty"):
        tierb_split.sealed_pair("repeatability_r1", 1, EXPLORE_B, **fx)


def test_sealed_pair_refuses_unreadable_tier_b_batch(tmp_path):
    # any unreadable Tier B file refuses, even for a row of another batch: holdout_phrases
    # would skip it and the phrase set would be incomplete
    fx = _seal_fixture(tmp_path, batches={
        TIERB: [{"top_prompt": HOLD_A}], "pairs_20260712T000000Z": "{not json"})
    with pytest.raises(tierb_split.SealError, match="cannot read"):
        tierb_split.sealed_pair("repeatability_r1", 1, EXPLORE_A, **fx)
    fx2 = _seal_fixture(tmp_path / "b", batches={
        TIERB: [{"top_prompt": HOLD_A}], "pairs_20260712T000000Z": {"not": "a list"}})
    with pytest.raises(tierb_split.SealError, match="not a list"):
        tierb_split.sealed_pair("repeatability_r1", 1, EXPLORE_A, **fx2)


def test_sealed_pair_refuses_tier_b_row_without_batch_file(tmp_path):
    fx = _seal_fixture(tmp_path)
    with pytest.raises(tierb_split.SealError, match="no batch file"):
        tierb_split.sealed_pair("pairs_20260713T000000Z", 1, EXPLORE_A, **fx)


@pytest.mark.parametrize("index", [0, 3, -1, None, True, "1"])
def test_sealed_pair_refuses_index_outside_tier_b_batch(tmp_path, index):
    fx = _seal_fixture(tmp_path)
    with pytest.raises(tierb_split.SealError, match="index"):
        tierb_split.sealed_pair(TIERB, index, EXPLORE_A, **fx)


def test_sealed_pair_refuses_non_string_prompt(tmp_path):
    fx = _seal_fixture(tmp_path)
    with pytest.raises(tierb_split.SealError, match="not a string"):
        tierb_split.sealed_pair("repeatability_r1", 1, {"clinical": HOLD_A}, **fx)


def test_seal_error_is_not_a_value_error():
    # export_jlens_depth maps ValueError to exit 3, which the publish chain reads as
    # success with no change; an unevaluable seal must never take that path
    assert issubclass(tierb_split.SealError, RuntimeError)
    assert not issubclass(tierb_split.SealError, ValueError)


def test_seal_config_error_prints_the_stop_line_and_returns_2(capsys):
    # every exporter that calls sealed_pair returns this on SealError: the status
    # export_pair_swaps.py and seal_check.py return when the holdout rule cannot be
    # applied, never 3, the status the publish chain reads as a refusal (Codex, PR #62)
    rc = tierb_split.seal_config_error(tierb_split.SealError("no tierb.start_utc in x"))
    assert rc == tierb_split.SEAL_CONFIG_EXIT == 2
    out = capsys.readouterr().out
    assert out.startswith("CONFIG ERROR: no tierb.start_utc in x.")
    assert "not a refusal: stop the publish chain" in out and "nothing was written" in out


def test_publish_skill_reads_exit_2_from_any_exporter_as_a_stop():
    # the publish chain is run from this skill, which treats an exporter's refusal as
    # success with no change; exit 2 from the seal must be named as a stop for every
    # exporter in the chain, not for export_pair_swaps.py alone (Codex, PR #62)
    skill = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "publish-site-data" / "SKILL.md"
    text = " ".join(skill.read_text(encoding="utf-8").split())
    assert "Exit 2 (`CONFIG ERROR`) from any exporter in this chain is not a refusal: stop the publish" in text


def test_sealed_pair_defaults_are_repo_rooted_not_cwd(tmp_path, monkeypatch):
    root = Path(tierb_split.__file__).resolve().parents[1]
    assert tierb_split.DASHBOARD_PATH == root / "ops" / "dashboard.json"
    assert tierb_split.SIMULATED_DIR == root / "data" / "simulated"
    # with no path arguments the module paths are used whatever the working directory,
    # including one holding its own dashboard with no Tier B start
    fx = _seal_fixture(tmp_path / "repo")
    monkeypatch.setattr(tierb_split, "DASHBOARD_PATH", fx["dashboard_path"])
    monkeypatch.setattr(tierb_split, "SIMULATED_DIR", fx["simulated_dir"])
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "ops").mkdir(parents=True)
    (elsewhere / "ops" / "dashboard.json").write_text(json.dumps({"tierb": {"start_utc": None}}))
    monkeypatch.chdir(elsewhere)
    assert tierb_split.sealed_pair("repeatability_r1", 1, HOLD_A)
    assert tierb_split.sealed_pair(TIERB, 1, EXPLORE_B)
    assert not tierb_split.sealed_pair(TIERB, 2, EXPLORE_B)


def test_site_copy_floors_probe_models():
    # 3-pair probe models must not reach the public comparison page until a
    # real measurement set lands (owner: incorporate models "when results land")
    src = _RIGOR_PATH.read_text(encoding="utf-8")
    assert "MIN_SITE_PHRASES = 30" in src
    assert 'v["penalty"]["n_phrases"] >= MIN_SITE_PHRASES' in src
