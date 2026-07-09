"""Tests for scripts/ledger_update.py — the daily spend-accounting step.

All trees live under tmp_path and --date is injected, so runs are
deterministic and offline. Idempotency is asserted on file hashes.
"""
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ledger_update.py"
_SPEC = importlib.util.spec_from_file_location("ledger_update", _SCRIPT)
ledger_update = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ledger_update)

TODAY = "2026-07-09"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_sidecar(sim_dir, name, **fields):
    (sim_dir / name).write_text(json.dumps(fields), encoding="utf-8")


@pytest.fixture
def tree(tmp_path):
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    ledger = docs / "overnight_ledger_20260708.md"
    ledger.write_text("# Overnight session ledger\n\nProse the script must not touch.\n", encoding="utf-8")
    return {"sim": sim, "dash": tmp_path / "ops" / "dashboard.json", "ledger": ledger}


def run(tree, *extra):
    argv = ["--simulated-dir", str(tree["sim"]), "--dashboard", str(tree["dash"]),
            "--ledger", str(tree["ledger"]), "--date", TODAY, *extra]
    return ledger_update.main(argv)


def load_dash(tree):
    return json.loads(tree["dash"].read_text(encoding="utf-8"))


def seed_dash(tree, dash):
    tree["dash"].parent.mkdir(parents=True, exist_ok=True)
    tree["dash"].write_text(json.dumps(dash), encoding="utf-8")


def test_fresh_scan_counts_paid_sidecar_and_zero_cost_alias(tree, capsys):
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-08T02:38:37.713618+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, rejected=16, cost_usd=0.098501)
    write_sidecar(tree["sim"], "zz_alias.report.json",
                  alias_of="pairs_a.json", cost_usd=0.0, task="alias")
    seed_dash(tree, {"schema_version": 1, "spend": {"lifetime_generation_usd": 9.56}})

    assert run(tree) == 0

    spend = load_dash(tree)["spend"]
    assert spend["entries_seen"] == ["pairs_a.report.json", "zz_alias.report.json"]
    assert spend["lifetime_generation_usd"] == pytest.approx(9.6585)
    assert spend["by_day"]["2026-07-08"] == pytest.approx(0.0985)
    # alias has no run_timestamp: its $0 lands on the injected --date
    assert spend["by_day"][TODAY] == 0.0
    assert spend["today"] == {"date": TODAY, "spent_usd": 0.0}
    assert "last_scan_utc" in spend

    text = tree["ledger"].read_text(encoding="utf-8")
    assert text.count("## Spend log (auto)") == 1
    assert "- pairs_a.report.json · $0.0985 · claude-haiku-4-5 · accepted 50 · 2026-07-08T02:38:37.713618+00:00" in text
    assert "- zz_alias.report.json · $0.0000 · alias · accepted — · —" in text
    assert "2 new sidecars" in capsys.readouterr().out


def test_second_run_is_idempotent_file_hashes_identical(tree, capsys):
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-08T02:38:37+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)
    write_sidecar(tree["sim"], "zz_alias.report.json", alias_of="pairs_a.json", cost_usd=0.0, task="alias")

    run(tree)
    dash_hash, ledger_hash = sha(tree["dash"]), sha(tree["ledger"])
    assert run(tree) == 0
    assert sha(tree["dash"]) == dash_hash
    assert sha(tree["ledger"]) == ledger_hash
    assert "0 new sidecars" in capsys.readouterr().out
    assert len(load_dash(tree)["spend"]["entries_seen"]) == 2


def test_tierb_gate_start_time_and_model(tree):
    seed_dash(tree, {"schema_version": 1, "tierb": {
        "target_pairs": 1600, "generator": "claude-haiku-4-5",
        "start_utc": "2026-07-09T00:00:00Z", "accepted_pairs": 0, "batches": []}})
    write_sidecar(tree["sim"], "pairs_early.report.json",
                  run_timestamp="2026-07-08T23:59:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=40, cost_usd=0.08)
    write_sidecar(tree["sim"], "pairs_other_model.report.json",
                  run_timestamp="2026-07-09T01:00:00+00:00", task="pairs",
                  model="claude-sonnet-5", accepted=30, cost_usd=0.41)
    write_sidecar(tree["sim"], "pairs_tierb.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)

    run(tree)

    dash = load_dash(tree)
    assert dash["tierb"]["accepted_pairs"] == 50
    # rows key on the batch archive name (<batch>.json), not the sidecar name
    assert dash["tierb"]["batches"] == [
        {"file": "pairs_tierb.json", "accepted": 50, "cost_usd": 0.0985, "status": "landed"}]
    assert dash["spend"]["generation_spent_usd"] == pytest.approx(0.0985)
    # all three still count toward lifetime spend
    assert dash["spend"]["lifetime_generation_usd"] == pytest.approx(0.5885)


def test_tierb_not_attributed_when_start_utc_null(tree):
    seed_dash(tree, {"schema_version": 1, "tierb": {
        "generator": "claude-haiku-4-5", "start_utc": None, "accepted_pairs": 0, "batches": []}})
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)

    run(tree)

    dash = load_dash(tree)
    assert dash["tierb"]["accepted_pairs"] == 0
    assert dash["tierb"]["batches"] == []
    assert dash["spend"].get("generation_spent_usd") is None


def test_ledger_heading_created_once_then_appended(tree):
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-08T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)
    run(tree)
    write_sidecar(tree["sim"], "pairs_b.report.json",
                  run_timestamp="2026-07-09T03:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=48, cost_usd=0.0996)
    run(tree)

    text = tree["ledger"].read_text(encoding="utf-8")
    assert text.startswith("# Overnight session ledger")
    assert text.count("## Spend log (auto)") == 1
    assert text.index("- pairs_a.report.json") < text.index("- pairs_b.report.json")


def test_ceiling_alerts_fire_dedup_and_exit_zero(tree, capsys):
    seed_dash(tree, {"schema_version": 1,
                     "spend": {"generation_ceiling_usd": 0.05, "daily_ceiling_usd": 0.05},
                     "tierb": {"generator": "claude-haiku-4-5",
                               "start_utc": "2026-07-09T00:00:00Z"}})
    write_sidecar(tree["sim"], "pairs_big.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.10)

    assert run(tree) == 0
    out = capsys.readouterr().out
    assert "WARNING" in out
    alerts = load_dash(tree)["spend"]["alerts"]
    assert len(alerts) == 2  # run ceiling + daily ceiling
    assert any("daily ceiling" in a for a in alerts)

    # a further breach on the same day does not duplicate the sentences
    write_sidecar(tree["sim"], "pairs_more.report.json",
                  run_timestamp="2026-07-09T03:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.10)
    assert run(tree) == 0
    assert load_dash(tree)["spend"]["alerts"] == alerts


def test_unknown_dashboard_fields_preserved_round_trip(tree):
    seed_dash(tree, {"schema_version": 1,
                     "verdicts": ["haiku >= opus at 1/8 cost"],
                     "future_widget": {"nested": [1, 2, {"deep": True}]},
                     "spend": {"mystery_subfield": "keep-me", "lifetime_generation_usd": 1.0},
                     "notes": ["hand-written note"]})
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)

    run(tree)

    dash = load_dash(tree)
    assert dash["verdicts"] == ["haiku >= opus at 1/8 cost"]
    assert dash["future_widget"] == {"nested": [1, 2, {"deep": True}]}
    assert dash["spend"]["mystery_subfield"] == "keep-me"
    assert dash["notes"] == ["hand-written note"]
    assert dash["spend"]["lifetime_generation_usd"] == pytest.approx(1.0985)


def test_missing_dashboard_bootstraps_skeleton(tree, capsys):
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)
    assert not tree["dash"].exists()

    assert run(tree) == 0

    dash = load_dash(tree)
    assert dash["schema_version"] == 1
    assert dash["spend"]["entries_seen"] == ["pairs_a.report.json"]
    assert dash["spend"]["lifetime_generation_usd"] == pytest.approx(0.0985)
    assert dash["spend"]["today"] == {"date": TODAY, "spent_usd": pytest.approx(0.0985)}
    # written with a trailing newline, per the data contract
    assert tree["dash"].read_text(encoding="utf-8").endswith("}\n")
    assert "1 new sidecars" in capsys.readouterr().out


def test_dry_run_writes_nothing(tree, capsys):
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)
    ledger_before = tree["ledger"].read_text(encoding="utf-8")

    assert run(tree, "--dry-run") == 0

    assert not tree["dash"].exists()
    assert tree["ledger"].read_text(encoding="utf-8") == ledger_before
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "pairs_a.report.json" in out


# --- Finding 9: bullets are never lost - ledger before entries_seen ---

def test_no_ledger_file_creates_default_spend_ledger(tmp_path, monkeypatch):
    # Previously: WARNING, bullets skipped, entries_seen committed anyway -
    # the bullets were gone forever.
    monkeypatch.chdir(tmp_path)
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    write_sidecar(sim, "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)
    dash = tmp_path / "ops" / "dashboard.json"

    assert ledger_update.main(["--simulated-dir", str(sim), "--dashboard", str(dash),
                               "--date", TODAY]) == 0

    ledger = tmp_path / "docs" / "spend_ledger.md"
    assert ledger.exists()
    text = ledger.read_text(encoding="utf-8")
    assert text.startswith("# Spend ledger\n")
    assert text.count("## Spend log (auto)") == 1
    assert "- pairs_a.report.json" in text
    assert json.loads(dash.read_text())["spend"]["entries_seen"] == ["pairs_a.report.json"]


def test_failed_ledger_append_aborts_before_entries_seen_commit(tree):
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)
    bad_ledger = tree["ledger"].parent / "broken_ledger_dir.md"
    bad_ledger.mkdir()  # reading a directory raises OSError inside append_ledger

    with pytest.raises(OSError):
        ledger_update.main(["--simulated-dir", str(tree["sim"]), "--dashboard", str(tree["dash"]),
                            "--ledger", str(bad_ledger), "--date", TODAY])

    # entries_seen never committed: the dashboard write must not have happened
    assert not tree["dash"].exists()
    # so a later run with a working ledger recovers the same bullet
    assert run(tree) == 0
    assert "- pairs_a.report.json" in tree["ledger"].read_text(encoding="utf-8")
    assert load_dash(tree)["spend"]["entries_seen"] == ["pairs_a.report.json"]


# --- Finding 10: tierb rows key on the batch .json name and upsert ---

def test_tierb_upsert_updates_preregistered_row_no_duplicates(tree):
    seed_dash(tree, {"schema_version": 1, "tierb": {
        "target_pairs": 1600, "generator": "claude-haiku-4-5",
        "start_utc": "2026-07-09T00:00:00Z", "accepted_pairs": 40,
        "batches": [
            {"file": "pairs_done.json", "accepted": 40, "cost_usd": 0.08, "status": "traced"},
            {"file": "pairs_tierb.json", "accepted": 0, "cost_usd": 0.0, "status": "generating"},
        ]}})
    write_sidecar(tree["sim"], "pairs_tierb.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)

    run(tree)

    dash = load_dash(tree)
    # the pre-registered row was updated in place - no duplicate, joinable name
    assert dash["tierb"]["batches"] == [
        {"file": "pairs_done.json", "accepted": 40, "cost_usd": 0.08, "status": "traced"},
        {"file": "pairs_tierb.json", "accepted": 50, "cost_usd": 0.0985, "status": "landed"},
    ]
    assert dash["tierb"]["accepted_pairs"] == 90
    assert dash["spend"]["generation_spent_usd"] == pytest.approx(0.0985)


def test_batch_file_name_strips_report_suffix():
    assert ledger_update.batch_file_name("batch_x.report.json") == "batch_x.json"
    assert ledger_update.batch_file_name("odd_name.json") == "odd_name.json"


# --- Finding 11: by_day buckets by parsed UTC date, not string prefix ---

def test_by_day_buckets_by_utc_date_not_string_prefix(tree):
    write_sidecar(tree["sim"], "pairs_offset.report.json",
                  run_timestamp="2026-07-08T23:30:00-05:00",  # = 2026-07-09T04:30Z
                  task="pairs", model="claude-haiku-4-5", accepted=10, cost_usd=0.05)
    write_sidecar(tree["sim"], "pairs_garbage_stamp.report.json",
                  run_timestamp="2026-99-99T00:00:00Z",  # unparseable -> falls back to --date
                  task="pairs", model="claude-haiku-4-5", accepted=10, cost_usd=0.03)

    run(tree)

    spend = load_dash(tree)["spend"]
    assert "2026-07-08" not in spend["by_day"]  # offset stamp books to its UTC day
    assert "2026-99-99" not in spend["by_day"]  # garbage never becomes a key
    assert spend["by_day"][TODAY] == pytest.approx(0.08)
    # Finding 13: spend.today still mirrors by_day for --date on a writing run
    assert spend["today"] == {"date": TODAY, "spent_usd": pytest.approx(0.08)}


# --- Finding 12: updated_utc stamped on writes; updated_by preserved ---

def test_updated_utc_stamped_and_existing_updated_by_preserved(tree):
    seed_dash(tree, {"schema_version": 1, "updated_utc": "2026-07-01T00:00:00Z",
                     "updated_by": "routine"})
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)

    run(tree)

    dash = load_dash(tree)
    assert dash["updated_utc"] != "2026-07-01T00:00:00Z"
    datetime.strptime(dash["updated_utc"], "%Y-%m-%dT%H:%M:%SZ")  # contract format
    assert dash["updated_by"] == "routine"  # existing writer label preserved


def test_updated_by_defaults_to_session_only_when_absent(tree):
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-09T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.0985)

    run(tree)

    dash = load_dash(tree)
    assert dash["updated_by"] == "session"
    assert "updated_utc" in dash


# --- Finding 13: spend.today refreshed on every writing run ---

def test_stale_spend_today_replaced_on_next_writing_run(tree):
    seed_dash(tree, {"schema_version": 1,
                     "spend": {"today": {"date": "2026-07-08", "spent_usd": 1.5},
                               "by_day": {"2026-07-08": 1.5}}})
    write_sidecar(tree["sim"], "pairs_a.report.json",
                  run_timestamp="2026-07-08T02:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=50, cost_usd=0.10)

    run(tree)

    spend = load_dash(tree)["spend"]
    assert spend["by_day"]["2026-07-08"] == pytest.approx(1.6)
    assert spend["today"] == {"date": TODAY, "spent_usd": 0.0}  # nothing landed on --date itself


# --- Finding 16: the sample dashboard's arithmetic is internally consistent ---

def test_sample_dashboard_arithmetic_consistent():
    sample_path = Path(__file__).resolve().parents[1] / "ops" / "dashboard.sample.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    spend, tierb = sample["spend"], sample["tierb"]
    batches = tierb["batches"]
    # rows key on batch archive names, never on cost sidecars
    assert all(b["file"].endswith(".json") and not b["file"].endswith(".report.json")
               for b in batches)
    # tierb attribution sums exactly
    assert round(sum(b["cost_usd"] for b in batches), 4) == spend["generation_spent_usd"]
    assert sum(b["accepted"] for b in batches) == tierb["accepted_pairs"]
    # each by_day bucket equals the batch costs booked to that UTC day
    # (batch file names carry their run day)
    for day, total in spend["by_day"].items():
        assert round(sum(b["cost_usd"] for b in batches if day in b["file"]), 4) == total, day
    # spend.today mirrors by_day for its date
    assert spend["by_day"][spend["today"]["date"]] == spend["today"]["spent_usd"]
    # every landed batch's sidecar is in entries_seen; unlanded ones are not
    landed_sidecars = {b["file"][:-len(".json")] + ".report.json"
                       for b in batches if b["status"] != "generating"}
    assert landed_sidecars == set(spend["entries_seen"])
