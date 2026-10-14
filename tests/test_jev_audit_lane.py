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

LIVE = {**ft.JEV_DEFAULTS, "live": "true", "max_spend": "0.20"}


def _report(billed=0.11, estimated=0.09, unbilled=0, **meta):
    return {"metadata": {"timestamp_utc": "2026-10-12T05:00:00Z", **meta},
            "metrics": {"total_cost_usd": billed, "total_estimated_cost_usd": estimated,
                        "unbilled_calls_count": unbilled},
            "cases": [{"id": "a"}, {"id": "b"}], "petri_cases": [{"turn_index": 1}]}


def _build(report, started=True):
    return sidecar.build_sidecar(report, report_sha256="ab" if report else None, model="typesafe/jev-1.13",
                                 max_spend=0.2, nonce="n1", started=started, run_utc="2026-10-14T00:00:00Z")


# --- the cost sidecar -------------------------------------------------------------------------------------------

def test_a_fully_billed_report_books_its_billed_cost_to_openrouter():
    sc = _build(_report())
    assert sc["cost_usd"] == pytest.approx(0.11) and sc["cost_basis"] == "provider_billed"
    assert sc["billing_channel"] == "openrouter" and sc["task"] == "jev-audit"
    assert sc["run_utc"] == "2026-10-12T05:00:00Z" and sc["calls"] == 3 and sc["journal_nonce"] == "n1"
    assert sc["interrupted"] is False


def test_unbilled_calls_book_the_estimate_when_it_is_larger():
    sc = _build(_report(billed=0.02, estimated=0.09, unbilled=4))
    assert sc["cost_usd"] == pytest.approx(0.09)
    assert sc["cost_basis"] == "billed_plus_estimate_for_unbilled_calls"


def test_a_started_run_without_a_report_books_the_whole_ceiling():
    sc = _build(None, started=True)
    assert sc["cost_usd"] == pytest.approx(0.2) and sc["cost_basis"] == "ceiling_imputed:report_missing"


def test_a_run_that_never_started_writes_no_sidecar():
    assert _build(None, started=False) is None


def test_an_interrupted_report_is_labelled():
    assert _build(_report(interrupted={"reason": "ceiling"}))["interrupted"] is True


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
    rc, out, err = _run(tmp_path, {**LIVE, "_nonce": "jev-1"})
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
