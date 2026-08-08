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
    adv = tmp_path / "data" / "advice"
    adv.mkdir()
    pab = tmp_path / "data" / "pab"
    pab.mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()
    ledger = docs / "overnight_ledger_20260708.md"
    ledger.write_text("# Overnight session ledger\n\nProse the script must not touch.\n", encoding="utf-8")
    trace = tmp_path / "trace_out"
    trace.mkdir()
    return {"sim": sim, "adv": adv, "pab": pab, "trace": trace,
            "dash": tmp_path / "ops" / "dashboard.json", "ledger": ledger}


def run(tree, *extra):
    # --advice-dir and --pab-dir always pinned to the fixture so a real sidecar
    # landing in the repo's data/advice/ or data/pab/ can never leak into these
    # hermetic tests
    argv = ["--simulated-dir", str(tree["sim"]), "--advice-dir", str(tree["adv"]),
            "--pab-dir", str(tree["pab"]),
            "--trace-dir", str(tree["trace"]),
            "--dashboard", str(tree["dash"]),
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
    # today carries the pooled figure plus one <channel>_usd per booked channel
    # (CHANNEL-SPLIT, 2026-08-04); both sidecars here are Anthropic-billed
    assert spend["today"]["date"] == TODAY
    assert spend["today"]["spent_usd"] == 0.0
    assert spend["today"]["anthropic_usd"] == 0.0
    assert spend["by_day_by_channel"]["anthropic"]["2026-07-08"] == pytest.approx(0.0985)
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
    # run ceiling + pooled daily + anthropic-lane daily (per-lane reporting,
    # owner decision 2026-08-08: the lane sentence names WHICH account is over)
    assert len(alerts) == 3
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
    assert dash["spend"]["today"]["date"] == TODAY
    assert dash["spend"]["today"]["spent_usd"] == pytest.approx(0.0985)
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
    assert spend["today"]["date"] == TODAY
    assert spend["today"]["spent_usd"] == pytest.approx(0.08)


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
    assert spend["today"]["date"] == TODAY
    assert spend["today"]["spent_usd"] == 0.0  # nothing landed on --date itself


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


def test_advice_sidecars_fold_into_spend_totals(tree):
    # handoff rev 2 accounting gap: advice-arm sidecars must reach the same
    # totals the $2/day guard reads, or landed advice spend is invisible
    write_sidecar(tree["adv"], "responses_20260722T010101Z.report.json",
                  cost_usd=0.42, model="advice-elicit",
                  run_timestamp=f"{TODAY}T01:01:01Z")
    write_sidecar(tree["adv"], "judgments_20260722T020202Z.report.json",
                  cost_usd=0.11, model="claude-haiku-4-5",
                  run_timestamp=f"{TODAY}T02:02:02Z")
    write_sidecar(tree["sim"], "pairs_20260722T000000Z.report.json",
                  cost_usd=0.05, model="claude-haiku-4-5", accepted=5,
                  task="pairs", run_timestamp=f"{TODAY}T00:00:00Z")
    assert run(tree) == 0
    dash = load_dash(tree)
    spend = dash["spend"]
    assert spend["by_day"][TODAY] == pytest.approx(0.58)
    assert spend["today"]["date"] == TODAY
    assert spend["today"]["spent_usd"] == pytest.approx(0.58)
    assert spend["today"]["anthropic_usd"] == pytest.approx(0.58)
    seen = set(spend["entries_seen"])
    assert {"responses_20260722T010101Z.report.json",
            "judgments_20260722T020202Z.report.json",
            "pairs_20260722T000000Z.report.json"} <= seen
    # idempotent on re-run
    assert run(tree) == 0
    assert load_dash(tree)["spend"]["by_day"][TODAY] == pytest.approx(0.58)


def test_pab_sidecars_fold_into_spend_totals(tree):
    # PatientAgentBench probe spend is billed by the provider, not fired
    # through a CI trigger, so without this glob the $2/day guard never sees it
    # -- the same gap the advice arm hit in July.
    write_sidecar(tree["pab"], "toolcall_smoke_20260804T101010Z.report.json",
                  cost_usd=0.0123, model="openrouter:openai/gpt-5.4-mini",
                  task="pab-toolcall-smoke", max_spend_usd=0.10,
                  run_timestamp=f"{TODAY}T10:10:10Z")
    assert run(tree) == 0
    spend = load_dash(tree)["spend"]
    assert spend["by_day"][TODAY] == pytest.approx(0.0123)
    assert "toolcall_smoke_20260804T101010Z.report.json" in set(spend["entries_seen"])
    # idempotent on re-run
    assert run(tree) == 0
    assert load_dash(tree)["spend"]["by_day"][TODAY] == pytest.approx(0.0123)


def test_pab_sidecar_never_attributed_to_tier_b(tree):
    # attribute_tierb gates on task == "pairs"; a probe sidecar is background
    # spend and must not move the Tier B campaign counters.
    seed_dash(tree, {"tierb": {"start_utc": "2026-01-01T00:00:00Z",
                               "generator": "claude-opus-4-8",
                               "accepted_pairs": 7, "batches": []},
                     "spend": {}})
    write_sidecar(tree["pab"], "probe_20260804T111111Z.report.json",
                  cost_usd=0.5, model="claude-opus-4-8",
                  task="pab-toolcall-smoke",
                  run_timestamp=f"{TODAY}T11:11:11Z")
    assert run(tree) == 0
    dash = load_dash(tree)
    assert dash["tierb"]["accepted_pairs"] == 7
    assert dash["tierb"]["batches"] == []
    assert dash["spend"].get("generation_spent_usd") in (None, 0, 0.0)
    # still counted as background spend against the daily guard
    assert dash["spend"]["by_day"][TODAY] == pytest.approx(0.5)


def test_cumulative_sidecar_growth_folds_as_delta(tree, capsys):
    # critic HIGH closed 2026-07-29: the advice archive rewrites its
    # responses_*.report.json in place as the append-only archive grows; the
    # entries_seen filename gate must not hide that growth from the guard.
    write_sidecar(tree["adv"], "responses_stimuli_x.report.json", cost_usd=7.20)
    run(tree)
    write_sidecar(tree["adv"], "responses_stimuli_x.report.json", cost_usd=7.99)
    run(tree)
    dash = load_dash(tree)
    assert dash["spend"]["by_day"][TODAY] == pytest.approx(7.99)
    assert dash["spend"]["lifetime_generation_usd"] == pytest.approx(7.99)
    assert dash["spend"]["entries_folded"]["responses_stimuli_x.report.json"] == pytest.approx(7.99)
    text = tree["ledger"].read_text(encoding="utf-8")
    assert "· $0.7900 · delta (cumulative $7.9900" in text
    # idempotent: a third run folds nothing more
    before = sha(tree["dash"])
    run(tree)
    assert sha(tree["dash"]) == before


def test_delta_bootstrap_from_ledger_bullets(tree):
    # a sidecar folded BEFORE entries_folded existed has only its ledger
    # bullet as the record of what was booked; the delta pass reconstructs
    # the folded total from those bullets instead of double-counting
    write_sidecar(tree["adv"], "responses_stimuli_y.report.json", cost_usd=5.00)
    seed_dash(tree, {"spend": {"entries_seen": ["responses_stimuli_y.report.json"],
                               "by_day": {TODAY: 3.0}, "lifetime_generation_usd": 3.0}})
    tree["ledger"].write_text(
        "# Ledger\n\n## Spend log (auto)\n\n"
        "- responses_stimuli_y.report.json · $3.0000 · alias · accepted — · —\n",
        encoding="utf-8")
    run(tree)
    dash = load_dash(tree)
    assert dash["spend"]["by_day"][TODAY] == pytest.approx(5.0)
    assert dash["spend"]["entries_folded"]["responses_stimuli_y.report.json"] == pytest.approx(5.0)


def test_mitigation_sidecars_fold_from_trace_out(tree):
    """The translation panel is the only paid call in a trace run, and its cost
    booked as $0 for the study's whole history: nothing wrote the sidecar, and
    nothing scanned trace_out for one (owner decision D2, 2026-07-31)."""
    out = tree["trace"] / "pairs_x"
    out.mkdir(parents=True)
    (out / "mitigation.part_01.report.json").write_text(json.dumps({
        "kind": "mitigation", "cost_usd": 0.0421, "imputed": False,
        "run_utc": "2026-07-08T21:00:00Z", "calls": 20}), encoding="utf-8")
    assert run(tree) == 0
    spend = load_dash(tree)["spend"]
    # keyed by batch dir: the bare basename repeats under every stem
    assert "pairs_x/mitigation.part_01.report.json" in spend["entries_seen"]
    assert spend["by_day"]["2026-07-08"] == 0.0421
    # idempotent: a second scan books nothing more
    assert run(tree) == 0
    assert load_dash(tree)["spend"]["by_day"]["2026-07-08"] == 0.0421


def test_same_basename_under_two_stems_both_book(tree):
    """Every batch dir holds a mitigation.part_01.report.json; a basename-keyed
    ledger would silently drop all but the first."""
    for stem, cost in (("pairs_a", 0.02), ("pairs_b", 0.03)):
        d = tree["trace"] / stem
        d.mkdir(parents=True)
        (d / "mitigation.part_01.report.json").write_text(json.dumps({
            "kind": "mitigation", "cost_usd": cost,
            "run_utc": "2026-07-08T21:00:00Z"}), encoding="utf-8")
    assert run(tree) == 0
    assert load_dash(tree)["spend"]["by_day"]["2026-07-08"] == 0.05


def test_mitigation_sidecar_key_is_depth_independent():
    """Same key from a relative or absolute scan, so a re-run never double-books."""
    rel = Path("trace_out/pairs_x/mitigation.part_11.report.json")
    absolute = Path("/a/b/trace_out/pairs_x/mitigation.part_11.report.json")
    assert (ledger_update.sidecar_key(rel)
            == ledger_update.sidecar_key(absolute)
            == "pairs_x/mitigation.part_11.report.json")
    # flat sidecars keep the historical bare-filename identity
    assert ledger_update.sidecar_key(
        Path("/tmp/x/data/simulated/pairs_a.report.json")) == "pairs_a.report.json"


def test_channel_split_books_openrouter_separately(tree):
    """CHANNEL-SPLIT (owner 2026-08-04): OpenRouter-billed sidecars book to
    their own channel so the $2/day Anthropic guard never counts them."""
    write_sidecar(tree["sim"], "pairs_x.report.json",
                  run_timestamp=f"{TODAY}T01:00:00+00:00", task="pairs",
                  model="claude-haiku-4-5", accepted=10, cost_usd=0.25)
    # channel is DERIVED from model names at any depth (PAB-branch parity):
    # nested openrouter: names route to the OpenRouter account …
    write_sidecar(tree["pab"], "pab_generate_1.reconciled.report.json",
                  run_timestamp=f"{TODAY}T02:00:00+00:00", cost_usd=2.2,
                  per_model={"openrouter:vendor/model-a": {"cost_usd": 2.2}})
    write_sidecar(tree["pab"], "toolcall_x.report.json",
                  run_timestamp=f"{TODAY}T03:00:00+00:00",
                  model="openrouter:openai/gpt-5.4-mini", cost_usd=0.04)
    # … a jury sidecar naming only claude judges stays Anthropic even in
    # data/pab/, and an explicit field always wins
    write_sidecar(tree["pab"], "pab_evaluate_1.report.json",
                  run_timestamp=f"{TODAY}T05:00:00+00:00", cost_usd=0.0,
                  evaluators=["pw:claude-opus-4.8-api"])
    write_sidecar(tree["pab"], "explicit_field.report.json",
                  run_timestamp=f"{TODAY}T04:00:00+00:00",
                  billing_channel="anthropic", cost_usd=0.1)
    seed_dash(tree, {"schema_version": 1, "spend": {}})

    assert run(tree) == 0
    spend = load_dash(tree)["spend"]
    assert spend["by_day_by_channel"]["anthropic"][TODAY] == pytest.approx(0.35)
    assert spend["by_day_by_channel"]["openrouter"][TODAY] == pytest.approx(2.24)
    assert spend["today"]["spent_usd"] == pytest.approx(2.59)
    assert spend["today"]["anthropic_usd"] == pytest.approx(0.35)
    assert spend["today"]["openrouter_usd"] == pytest.approx(2.24)


def test_cumulative_first_sight_books_run_cost_to_day(tree, capsys):
    """OPENROUTER-LANE-UNCEILINGED (owner 2026-08-08): a first-sight sidecar
    with cost_basis='cumulative_from_records' books run_cost_usd to its day —
    not the whole campaign total — while lifetime carries the full cumulative
    and entries_folded keeps the cumulative baseline for the growth pass."""
    write_sidecar(tree["adv"], "responses_stimuli_x.report.json",
                  run_utc=f"{TODAY}T03:00:00Z", cost_usd=17.89,
                  cost_basis="cumulative_from_records", run_cost_usd=6.09,
                  model="openrouter:google/gemini-3.1-pro-preview")
    seed_dash(tree, {"schema_version": 1, "spend": {}})

    assert run(tree) == 0
    spend = load_dash(tree)["spend"]
    assert spend["by_day"][TODAY] == pytest.approx(6.09)
    assert spend["today"]["openrouter_usd"] == pytest.approx(6.09)
    assert spend["lifetime_generation_usd"] == pytest.approx(17.89)
    folded = spend["entries_folded"]
    key = next(k for k in folded if "responses_stimuli_x" in k)
    assert folded[key] == pytest.approx(17.89)


def test_check_ceilings_reports_per_lane(tree, capsys):
    """Per-lane alerts: OpenRouter over its $10/day ceiling warns by name even
    when the Anthropic lane is far under its own."""
    write_sidecar(tree["adv"], "responses_stimuli_y.report.json",
                  run_utc=f"{TODAY}T03:00:00Z", cost_usd=11.5,
                  model="openrouter:google/gemini-3.5-flash")
    seed_dash(tree, {"schema_version": 1,
                     "spend": {"daily_ceiling_usd": 2.0, "daily_ceiling_note": ""}})

    assert run(tree) == 0
    spend = load_dash(tree)["spend"]
    assert spend["openrouter_daily_ceiling_usd"] == pytest.approx(10.0)
    alerts = " | ".join(spend.get("alerts", []))
    assert "openrouter lane" in alerts and "$10 daily ceiling" in alerts
    # anthropic lane spent nothing today: no anthropic-lane alert
    assert "anthropic lane" not in alerts
