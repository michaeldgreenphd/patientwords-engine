"""The jev-audit push-to-run lane (owner decision D3, 2026-10-14): the cost sidecar a live run commits
(scripts/jev_audit_sidecar.py), the fire guard's rules for the lane (scripts/fire_trigger.py), and the workflow's
params heredoc run as CI runs it (.github/workflows/jev_pilot.yml)."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "jev_pilot.yml"
TRIGGER_LITERAL = '".github/trigger/jev-audit.json"'


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sidecar = _load("jev_audit_sidecar")
ft = _load("fire_trigger")

LIVE = {**ft.JEV_DEFAULTS, "live": "true", "max_spend": "0.20", "_nonce": "jev-1"}


def _row(cost, estimate):
    return {"cost_usd": cost, "estimated_cost_usd": estimate}


def _report(rows=None, **meta):
    """A report whose metrics agree with its rows: two advice calls and one Petri call, all billed by default."""
    advice = rows[:2] if rows else [_row(0.05, 0.04), _row(0.05, 0.04)]
    petri = rows[2:] if rows else [_row(0.01, 0.01)]
    every = advice + petri
    return {"metadata": {"timestamp_utc": "2026-10-12T05:00:00Z", **meta},
            "metrics": {"total_cost_usd": sum(r["cost_usd"] or 0 for r in every),
                        "total_estimated_cost_usd": sum(r["estimated_cost_usd"] for r in every),
                        "unbilled_calls_count": sum(r["cost_usd"] is None for r in every)},
            "cases": advice, "petri_cases": petri}


def _build(report, started=True):
    return sidecar.build_sidecar(report, report_sha256="ab" if report else None, model="typesafe/jev-1.13",
                                 max_spend=0.2, nonce="n1", started=started, run_utc="2026-10-14T00:00:00Z")


# --- the cost sidecar -------------------------------------------------------------------------------------------

def test_a_fully_billed_report_books_its_billed_cost_to_openrouter():
    sc = _build(_report())
    assert sc["cost_usd"] == pytest.approx(0.11)
    assert sc["cost_usd"] == pytest.approx(0.11) and sc["cost_basis"] == "provider_billed"
    assert sc["billing_channel"] == "openrouter" and sc["task"] == "jev-audit"
    assert sc["run_utc"] == "2026-10-12T05:00:00Z" and sc["calls"] == 3 and sc["journal_nonce"] == "n1"
    assert sc["interrupted"] is False


def test_an_unbilled_call_adds_its_own_estimate_to_the_billed_spend():
    # Codex review of PR #110: a billed call of $0.10 estimated at $0.01 and an unbilled call estimated at $0.02 give
    # a $0.03 estimate over all calls; max(billed, estimate) booked $0.10 and lost the unbilled call
    sc = _build(_report([_row(0.10, 0.01), _row(None, 0.02), _row(0.0, 0.0)]))
    assert sc["cost_usd"] == pytest.approx(0.12)
    assert sc["cost_basis"] == "billed_plus_estimate_for_unbilled_calls" and sc["unbilled_calls_count"] == 1


def test_rows_that_disagree_with_the_unbilled_count_are_refused():
    report = _report([_row(0.10, 0.01), _row(None, 0.02), _row(0.0, 0.0)])
    report["metrics"]["unbilled_calls_count"] = 0
    with pytest.raises(ValueError, match="unbilled_calls_count"):
        _build(report)


def test_an_interrupted_report_books_at_least_the_ceiling():
    # Codex review of PR #110: the call that raised may have been billed and is in no row
    sc = _build(_report(interrupted={"reason": "classifier error"}))
    assert sc["cost_usd"] == pytest.approx(0.2) and sc["cost_basis"] == "ceiling_imputed:interrupted"
    assert sc["interrupted"] is True


def test_a_started_run_without_a_report_books_the_whole_ceiling():
    sc = _build(None, started=True)
    assert sc["cost_usd"] == pytest.approx(0.2) and sc["cost_basis"] == "ceiling_imputed:report_missing"


def test_a_run_that_never_started_writes_no_sidecar():
    assert _build(None, started=False) is None


def test_an_unbilled_call_with_no_estimate_is_refused():
    # Codex review of PR #110, round 2: the client defaults the estimate to zero when the response has no token counts
    with pytest.raises(ValueError, match="no positive estimate"):
        _build(_report([_row(0.10, 0.01), _row(None, 0.0), _row(0.0, 0.0)]))


def test_rows_that_disagree_with_the_billed_total_are_refused():
    report = _report()
    report["metrics"]["total_cost_usd"] = 0.5
    with pytest.raises(ValueError, match="total_cost_usd"):
        _build(report)


def _resumable_report() -> dict:
    report = _report([_row(0.05, 0.04), _row(None, 0.03), _row(0.01, 0.01)])
    report["cases"][0]["id"], report["cases"][1]["id"] = "a", "b"
    report["petri_cases"][0].update(conversation_id="c", turn_index=1)
    return report


def test_a_resumed_run_books_only_the_rows_it_scored():
    """The restored checkpoint's rows were booked by the earlier run's sidecar; the runner folds them, and their
    cost, into this report, so they are left out here."""
    checkpoint = {"advice_cases": [{"id": "a"}], "petri_cases": [{"conversation_id": "c", "turn_index": 1}]}
    sc = sidecar.build_sidecar(_resumable_report(), report_sha256="ab", model="typesafe/jev-1.13", max_spend=0.2,
                               nonce="n2", started=True, run_utc="2026-10-14T00:00:00Z", resumed=checkpoint,
                               resumed_run_id="123")
    assert sc["cost_usd"] == pytest.approx(0.03) and sc["calls"] == 1 and sc["resumed_rows"] == 2
    assert sc["resumed_from_run_id"] == "123" and sc["unbilled_calls_count"] == 1


def test_a_checkpoint_row_missing_from_the_report_is_refused():
    with pytest.raises(ValueError, match="checkpoint rows"):
        sidecar.build_sidecar(_resumable_report(), report_sha256="ab", model="typesafe/jev-1.13", max_spend=0.2,
                              nonce="n2", started=True, run_utc="2026-10-14T00:00:00Z",
                              resumed={"advice_cases": [{"id": "zzz"}], "petri_cases": []})


@pytest.mark.parametrize("metrics", [
    {},
    {"total_cost_usd": -1, "total_estimated_cost_usd": 0, "unbilled_calls_count": 0},
    {"total_cost_usd": 0.1, "total_estimated_cost_usd": 0.1, "unbilled_calls_count": True},
])
def test_malformed_metrics_are_refused(metrics):
    with pytest.raises(ValueError):
        _build({"metrics": metrics})


def test_the_cli_books_the_ceiling_for_an_unreadable_report(tmp_path):
    report = tmp_path / "r.json"
    report.write_text("{not json", encoding="utf-8")
    marker = tmp_path / "started"
    marker.write_text("")
    out = tmp_path / "data" / "x.report.json"
    rc = sidecar.main(["--report", str(report), "--out", str(out), "--model", "typesafe/jev-1.13",
                       "--max-spend", "0.2", "--started-marker", str(marker), "--run-utc", "2026-10-14T00:00:00Z"])
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["cost_usd"] == pytest.approx(0.2) and written["cost_basis"] == "ceiling_imputed:report_missing"


def test_the_cli_writes_nothing_when_nothing_started(tmp_path):
    out = tmp_path / "x.report.json"
    rc = sidecar.main(["--report", str(tmp_path / "missing.json"), "--out", str(out), "--model", "typesafe/jev-1.13",
                       "--max-spend", "0.2", "--started-marker", str(tmp_path / "none"),
                       "--run-utc", "2026-10-14T00:00:00Z"])
    assert rc == 0 and not out.exists()


# --- the fire guard ---------------------------------------------------------------------------------------------

def test_the_lane_is_registered_paid_and_parked():
    assert "jev-audit" in ft.TRIGGERS and "jev-audit" in ft.PAID_TRIGGERS
    assert ft.KNOWN_KEYS["jev-audit"] == frozenset(ft.JEV_DEFAULTS)
    park = ft.PARK_DEFAULTS["jev-audit"]
    assert park["live"] == "false" and park["commit_outputs"] == "false"
    assert ft.jev_params_problems(park) == []
    assert ft.is_paid_fire("jev-audit", park) is False


def test_triggers_stays_a_literal_tuple():
    # other readers take TRIGGERS with ast.literal_eval; a computed value would break them
    tree = ast.parse((ROOT / "scripts" / "fire_trigger.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "TRIGGERS")
    assert "jev-audit" in ast.literal_eval(node.value)


def test_only_a_live_run_is_paid_and_it_bills_openrouter():
    assert ft.is_paid_fire("jev-audit", LIVE) is True
    assert ft.is_paid_fire("jev-audit", {**LIVE, "live": "false"}) is False
    assert ft.is_paid_fire("jev-audit", {**LIVE, "live": True}) is True       # a JSON boolean, as the job reads it
    assert ft.fire_lane("jev-audit", LIVE) == "openrouter"


@pytest.mark.parametrize("change, fragment", [
    ({"live": "yes"}, "live"),
    ({"commit_outputs": "true"}, "needs live true"),
    ({"archive_samples": "-1"}, "archive_samples"),
    ({"petri_conversations": "three"}, "petri_conversations"),
    ({"max_spend": "0"}, "max_spend"),
    ({"model": "jev-1.13"}, "vendor/model"),
    ({"archive": "../outside.jsonl"}, "repo-relative"),
    ({"petri_transcripts": "data\\petri\\x.jsonl"}, "repo-relative"),
    ({"archive": "data/advice/no_such_archive.jsonl"}, "does not exist"),
    ({"live": "true", "_nonce": ""}, "_nonce"),
    ({"live": "true", "_nonce": " padded "}, "_nonce"),
    # Codex review of PR #110, round 2: what the params job refuses, the fire path refuses before journaling
    ({"archive_samples": "\u0661"}, "archive_samples"),                 # an Arabic-Indic one: isdigit() is True
    ({"petri_conversations": "\u00b2"}, "petri_conversations"),          # a superscript two
    ({"archive": "data/advice/../advice/responses_stimuli_20260721T235403Z.jsonl"}, "repo-relative"),
    ({"archive": "/" + ft.JEV_DEFAULTS["archive"]}, "repo-relative"),
    ({"resume_run_id": "abc"}, "resume_run_id"),
])
def test_bad_params_are_refused(change, fragment):
    problems = ft.jev_params_problems({**ft.JEV_DEFAULTS, **change})
    assert any(fragment in p for p in problems), problems


def test_a_live_committed_fire_is_accepted_and_the_lane_check_is_wired():
    assert ft.jev_params_problems({**LIVE, "commit_outputs": "true"}) == []
    assert ft.lane_params_problems("jev-audit", {**LIVE, "live": "maybe"})


# --- the workflow -----------------------------------------------------------------------------------------------

def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _heredoc() -> str:
    step = next(s for s in _workflow()["jobs"]["params"]["steps"] if s.get("name") == "Resolve parameters")
    m = re.search(r"python - <<'EOF'\n(.*?)\nEOF", step["run"], re.S)
    assert m, "the Resolve parameters step no longer carries its python heredoc"
    return m.group(1)


def _run(tmp_path: Path, cfg: dict, event: str = "push", attempt: str = "1"):
    """Run the heredoc from the repository root (it checks that its input files exist there), reading the trigger
    file from a temporary path instead of the checkout's."""
    trig = tmp_path / "jev-audit.json"
    trig.write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    code = _heredoc().replace(TRIGGER_LITERAL, repr(str(trig)))
    env = {**os.environ, "EVENT_NAME": event, "RUN_ATTEMPT": attempt, "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, "-"], input=code, cwd=ROOT, capture_output=True, text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


def test_the_heredoc_reads_the_trigger_file_and_its_defaults_match_the_fire_guard():
    code = _heredoc()
    assert TRIGGER_LITERAL in code
    m = re.search(r"defaults = (\{.*?\})\n", code, re.S)
    assert ast.literal_eval(m.group(1)) == ft.JEV_DEFAULTS


def test_a_live_fire_resolves_with_its_nonce(tmp_path):
    rc, out, err = _run(tmp_path, LIVE)
    assert rc == 0, err
    assert "live=true\n" in out and "max_spend=0.20\n" in out and "_nonce=jev-1\n" in out


def test_the_park_resolves_as_a_free_mock(tmp_path):
    rc, out, err = _run(tmp_path, ft.PARK_DEFAULTS["jev-audit"])
    assert rc == 0, err
    assert "live=false\n" in out and "commit_outputs=false\n" in out


def test_a_dispatch_never_reads_the_trigger_file_and_runs_mock(tmp_path):
    rc, out, err = _run(tmp_path, LIVE, event="workflow_dispatch")
    assert rc == 0, err
    assert "live=false\n" in out and "_nonce=\n" in out


@pytest.mark.parametrize("cfg, attempt, fragment", [
    (LIVE, "2", "cannot be re-run"),
    ({**LIVE, "live": "True "}, "1", "live must be true or false"),
    ({**LIVE, "live": "false", "commit_outputs": "true"}, "1", "not a measurement"),
    ({**LIVE, "_nonce": "x\nmax_spend=99"}, "1", "control character"),
    ({**LIVE, "archive": "../x.jsonl"}, "1", "repo-relative"),
    ({**LIVE, "model": "jev"}, "1", "vendor/model"),
    ({k: v for k, v in LIVE.items() if k != "_nonce"}, "1", "_nonce"),
    ({**LIVE, "resume_run_id": "12a"}, "1", "resume_run_id"),
    ({**LIVE, "archive_samples": "\u0661"}, "1", "archive_samples"),
])
def test_the_heredoc_refuses_before_any_output(tmp_path, cfg, attempt, fragment):
    rc, out, err = _run(tmp_path, cfg, attempt=attempt)
    assert rc != 0 and fragment in err, err
    assert out == "", "nothing may be written once a value is refused"


def test_every_job_skips_ref_creation_and_the_key_reaches_live_runs_only():
    wf = _workflow()
    for name, job in wf["jobs"].items():
        assert "!github.event.created" in str(job.get("if", "")), name
    run_step = next(s for s in wf["jobs"]["audit"]["steps"] if s.get("name", "").startswith("Run Jev audit"))
    assert "needs.params.outputs.live == 'true'" in run_step["env"]["OPENROUTER_API_KEY"]
    assert wf["concurrency"]["cancel-in-progress"] is False
    assert wf[True]["push"]["paths"] == [TRIGGER_LITERAL.strip('"')]   # yaml reads `on:` as True


# --- the server-side reservation (Codex review of PR #110) ------------------------------------------------------

def test_a_live_fire_with_no_journal_entry_is_refused_by_the_gate():
    """A live trigger that reached the branch without fire_trigger.py (a merge, a hand push) has no reservation, and
    budget-gate refuses it; a mock run needs none."""
    assert "jev-audit" in ft.NONCE_LANES
    problems = ft.journal_reservation_problems("jev-audit", LIVE, entries=[])
    assert problems and "no jev-audit journal entry carries _nonce" in problems[0]
    assert ft.reservation_entries("jev-audit", {**LIVE, "live": "false"}, []) is None


def test_the_reservation_must_be_on_the_ref_ci_runs():
    entry = {"trigger": "jev-audit", "nonce": "jev-1", "ref": "main", "max_spend": "0.20"}
    assert ft.ref_reservation_problems("jev-audit", LIVE, [entry], "main", True) == []
    assert ft.ref_reservation_problems("jev-audit", LIVE, [entry], "other", True)


def test_input_paths_are_checked_in_the_checkout_the_fire_targets(tmp_path):
    """fire --repo <checkout>: the paths must exist in that checkout, not in the one holding the script."""
    for key in ("archive", "petri_transcripts"):
        target = tmp_path / ft.JEV_DEFAULTS[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    elsewhere = {**ft.JEV_DEFAULTS, "archive": "data/only_in_target.jsonl"}
    (tmp_path / "data" / "only_in_target.jsonl").write_text("{}\n", encoding="utf-8")
    assert ft.lane_params_problems("jev-audit", elsewhere, repo=tmp_path) == []
    assert any("does not exist" in p for p in ft.lane_params_problems("jev-audit", elsewhere))
    with pytest.raises(ValueError, match="does not exist"):
        ft.validate_params("jev-audit", {**ft.PARK_DEFAULTS["jev-audit"]}, repo=tmp_path / "empty")


def test_every_run_keeps_a_checkpoint_and_a_resume_restores_it():
    """Codex review of PR #110, round 2: the checkpoint is written into the artifact on every run, and resume_run_id
    restores an earlier run's into a new fire (whose sidecar is told which rows were restored)."""
    steps = _workflow()["jobs"]["audit"]["steps"]
    run_step = next(s for s in steps if s.get("name", "").startswith("Run Jev audit"))
    assert '--checkpoint "artifacts/jev_pilot_checkpoint.json"' in run_step["run"]
    restore = next(s for s in steps if s.get("name") == "Restore the checkpoint of the run being resumed")
    assert restore["with"]["run-id"] == "${{ needs.params.outputs.resume_run_id }}"
    sidecar_step = next(s for s in steps if s.get("name", "").startswith("Write the cost sidecar"))
    assert "--resumed-checkpoint" in sidecar_step["run"]
    assert _workflow()["permissions"]["actions"] == "read"


def _cli_resume(tmp_path, source_sidecar):
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_resumable_report()), encoding="utf-8")
    checkpoint = tmp_path / "cp.json"
    checkpoint.write_text(json.dumps({"advice_cases": [{"id": "a"}],
                                      "petri_cases": [{"conversation_id": "c", "turn_index": 1}]}), encoding="utf-8")
    marker = tmp_path / "started"
    marker.write_text("")
    out = tmp_path / "out.report.json"
    args = ["--report", str(report), "--out", str(out), "--model", "typesafe/jev-1.13", "--max-spend", "0.2",
            "--started-marker", str(marker), "--run-utc", "2026-10-14T00:00:00Z",
            "--resumed-checkpoint", str(checkpoint), "--resumed-run-id", "123"]
    if source_sidecar is not None:
        args += ["--resumed-source-sidecar", str(source_sidecar)]
    assert sidecar.main(args) == 0
    return json.loads(out.read_text(encoding="utf-8"))


def test_restored_rows_are_left_out_only_when_the_source_sidecar_is_on_the_branch(tmp_path):
    """Codex review of PR #110, round 3: the restored rows were booked by the earlier run's sidecar only if that
    sidecar landed; when it is absent (its commit failed, or it is on another ref) they are booked here."""
    source = tmp_path / "jev_audit_123_1.report.json"
    source.write_text(json.dumps({"task": "jev-audit", "cost_usd": 0.06}), encoding="utf-8")
    left_out = _cli_resume(tmp_path, source)
    assert left_out["cost_usd"] == pytest.approx(0.03) and left_out["resumed_rows"] == 2
    booked_here = _cli_resume(tmp_path, tmp_path / "missing.report.json")
    assert booked_here["cost_usd"] == pytest.approx(0.09) and booked_here["resumed_rows"] == 0
    source.write_text(json.dumps({"task": "petri-audit"}), encoding="utf-8")
    assert _cli_resume(tmp_path, source)["resumed_rows"] == 0


def test_a_run_without_a_report_is_dated_by_its_start_marker(tmp_path):
    """Codex review of PR #110, round 4: a run that began before midnight UTC and left no report is booked to the day
    its marker records, not to the day the sidecar step ran."""
    marker = tmp_path / "started"
    marker.write_text("2026-10-14T23:58:00Z\n", encoding="utf-8")
    out = tmp_path / "x.report.json"
    assert sidecar.main(["--report", str(tmp_path / "missing.json"), "--out", str(out), "--model", "typesafe/jev-1.13",
                         "--max-spend", "0.2", "--started-marker", str(marker),
                         "--run-utc", "2026-10-15T00:20:00Z"]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["run_utc"] == "2026-10-14T23:58:00Z" and written["cost_basis"] == "ceiling_imputed:report_missing"


def test_inputs_must_be_committed_in_a_git_checkout(tmp_path):
    """Codex review of PR #110, round 4: CI checks out committed files only, so an untracked input is refused before
    the fire journals a reservation."""
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for key in ("archive", "petri_transcripts"):
        target = tmp_path / ft.JEV_DEFAULTS[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    problems = ft.jev_params_problems(dict(ft.JEV_DEFAULTS), repo=tmp_path)
    assert any("not committed at HEAD" in p for p in problems)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
                   check=True)
    assert ft.jev_params_problems(dict(ft.JEV_DEFAULTS), repo=tmp_path) == []


def test_the_audit_step_leaves_time_for_the_sidecar_steps():
    audit = _workflow()["jobs"]["audit"]
    run_step = next(s for s in audit["steps"] if s.get("name", "").startswith("Run Jev audit"))
    assert run_step["timeout-minutes"] < audit["timeout-minutes"]
