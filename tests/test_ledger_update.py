"""Tests for scripts/ledger_update.py — the daily spend-accounting step.

All trees live under tmp_path and --date is injected, so runs are
deterministic and offline. Idempotency is asserted on file hashes.
"""
import hashlib
import importlib.util
import json
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
    assert dash["tierb"]["batches"] == [
        {"file": "pairs_tierb.report.json", "accepted": 50, "cost_usd": 0.0985, "status": "landed"}]
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
