"""The petri-audit lane's `mode: rejudge` (2026-09-24) on the fire path, in the params job and in the workflow: the
params validation (unknown keys still refused), the commitment (judge_max_spend alone, on the judge's channel), the
source checks the fire path can see, the idle-lane rule, the park unchanged, the params heredoc run as CI runs it
and its parity with the fire guard, and the rejudge job's step conditions read from the YAML. Nothing here fires:
the fire path runs `--dry-run --no-git` in a temporary repository."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "petri_audit.yml"
TRIGGER = "petri-audit"
MOCK = "mockllm/judge"
PAID_JUDGE = "openrouter:openai/gpt-5.4-mini"
PAID_SLUG = "openrouter-openai-gpt-5.4-mini"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("fire_trigger")

REJUDGE = {"mode": "rejudge", "source_runs": "run_4242_1", "judge": "true", "judge_model": PAID_JUDGE,
           "judge_max_spend": "1.60", "judge_max_tokens": "300", "commit_outputs": "true", "_nonce": "rj-1"}


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(expr, steps: dict | None = None, **outputs) -> bool:
    """Whether a step's or job's `if:` admits it for the given params outputs and earlier steps' outcomes and
    outputs (`steps`: {id: {"outcome": ..., "outputs": {...}}}, default a success with no outputs), `always()` and
    the created guard read as on an existing ref. The conditions use only ==, !=, &&, ||, parentheses,
    needs.params.outputs.<key>, steps.<id>.outcome, steps.<id>.outputs.<key> and github.event.created. Values are
    compared exactly here; GitHub ignores case, which is why the steps gate on the params job's exact `rehearsal`."""
    if expr is None:
        return True
    steps = steps or {}
    body = str(expr).strip()
    assert body.startswith("${{") and body.endswith("}}"), body
    body = body[3:-2].replace("always()", "True").replace("github.event.created", "False")
    body = re.sub(r"needs\.params\.outputs\.(\w+)", lambda m: repr(outputs[m.group(1)]), body)
    body = re.sub(r"steps\.(\w+)\.outcome", lambda m: repr(steps.get(m.group(1), {}).get("outcome", "success")), body)
    body = re.sub(r"steps\.(\w+)\.outputs\.(\w+)",
                  lambda m: repr(steps.get(m.group(1), {}).get("outputs", {}).get(m.group(2), "")), body)
    body = body.replace("!=", " __NE__ ").replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    return bool(eval(body.replace("__NE__", "!="), {"__builtins__": {}}, {}))  # noqa: S307 - a literal expression


def _job_steps(workflow: dict, job: str) -> list[dict]:
    return workflow["jobs"][job]["steps"]


def _step(workflow: dict, job: str, prefix: str) -> dict:
    for step in _job_steps(workflow, job):
        if step.get("name", "").startswith(prefix):
            return step
    raise AssertionError(f"no step named {prefix!r} in job {job!r}")


# ------------------------------------------------------------ the fire path


def test_a_rejudge_is_paid_with_the_judge_ceiling_alone_on_the_judges_channel():
    ft.validate_params(TRIGGER, REJUDGE)
    assert "source_runs" in ft.KNOWN_KEYS[TRIGGER] and "source_runs" not in ft.PARK_DEFAULTS[TRIGGER]
    assert ft.PARK_DEFAULTS[TRIGGER]["mode"] == "preflight", "the park is unchanged"
    assert ft.is_paid_fire(TRIGGER, REJUDGE) is True
    assert ft.fire_commitment(REJUDGE) == (1.6, None), "no target call: the judge's ceiling is the commitment"
    assert ft.fire_commitment(dict(REJUDGE, max_spend="6.10")) == (1.6, None), "max_spend is not read"
    assert ft.fire_lane(TRIGGER, REJUDGE) == "openrouter"
    assert ft.fire_lane(TRIGGER, dict(REJUDGE, judge_model="x-ai/grok-4.3")) == "anthropic", \
        "a bare id is an Anthropic model to the registry, so it books the anthropic lane (fail closed)"
    assert ft.fire_lane(TRIGGER, dict(REJUDGE, judge_model="xai:x-ai/grok-4.3")) == "openrouter"
    commitment, error = ft.fire_commitment(dict(REJUDGE, judge="false"))
    assert commitment is None and "mode rejudge commits the judge's ceiling alone" in error
    # budget_check needs no max_spend for a rejudge (it reads none) and prices the judge's ceiling on its lane
    kind, reason = ft.budget_check(REJUDGE, {"spend": {}}, "2026-09-25", trigger=TRIGGER)
    assert kind == "ok" and "max_spend 1.60" in reason and "[openrouter lane]" in reason, reason
    # ...while a run without max_spend is still refused as before
    assert ft.budget_check(dict(REJUDGE, mode="run"), {}, "2026-09-25", trigger=TRIGGER)[0] == "invalid"
    # the target is not called, so an Anthropic target default does not make the OpenRouter judge a mixed fire
    ft.validate_params(TRIGGER, dict(REJUDGE, target="anthropic/claude-haiku-4-5"))


def test_the_rehearsal_is_free_needs_no_nonce_and_never_commits():
    rehearsal = dict(REJUDGE, judge_model=MOCK, commit_outputs="false", _nonce="")
    ft.validate_params(TRIGGER, rehearsal)
    assert ft.is_paid_fire(TRIGGER, rehearsal) is False
    with pytest.raises(ValueError, match="is never committed"):
        ft.validate_params(TRIGGER, dict(rehearsal, commit_outputs="true"))
    # a padded sentinel is not the rehearsal: it is refused, not read as a paid judge named "mockllm/judge "
    with pytest.raises(ValueError, match="judge_model spelled exactly"):
        ft.validate_params(TRIGGER, dict(rehearsal, judge_model=f"{MOCK} "))


@pytest.mark.parametrize("change, needle", [
    ({"source_runs": ""}, "needs source_runs"),
    ({"source_runs": "run_4242_1 run_4242_1"}, "names a source run twice"),
    ({"source_runs": "run_4242"}, "are not run stems"),
    ({"source_runs": "../run_4242_1"}, "are not run stems"),
    ({"judge": "false"}, "runs a judge (judge true)"),
    ({"judge_model": f" {PAID_JUDGE}"}, "spelled exactly"),
    ({"_nonce": ""}, "mode rejudge must carry a non-empty _nonce"),
    ({"judge_model": "google:gemini-3.5-flash"}, "bills GEMINI_API_KEY"),
    ({"mode": "REJUDGE"}, "mode must be exactly one of"),
    ({"sourceruns": "run_4242_1"}, "unknown petri-audit key"),
    ({"commit_outputs": "True"}, "must be true or false"),
])
def test_a_rejudge_the_workflow_cannot_run_is_refused_at_the_fire(change, needle):
    with pytest.raises(ValueError, match=re.escape(needle)):
        ft.validate_params(TRIGGER, dict(REJUDGE, **change))


def test_source_runs_is_refused_outside_mode_rejudge_and_a_list_is_read_as_the_job_reads_it():
    run = {"mode": "run", "target": "anthropic/claude-haiku-4-5", "judge": "false", "commit_outputs": "false",
           "_nonce": "n"}
    with pytest.raises(ValueError, match="source_runs is read by mode rejudge only"):
        ft.validate_params(TRIGGER, dict(run, source_runs="run_1_1"))
    ft.validate_params(TRIGGER, dict(run, source_runs=""))
    ft.validate_params(TRIGGER, dict(REJUDGE, source_runs=["run_4242_1", "run_4343_1"]))
    assert ft.petri_source_runs({"source_runs": ["run_1_1", "run_2_1"]}) == ["run_1_1", "run_2_1"]


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *argv],
                   check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    """A branch with the workflow wired, a parked trigger file, an empty journal, and one landed run whose judge of
    record is claude-haiku-4-5 under judge_max_tokens 300, named by the manifests chain."""
    repo = tmp_path / "repo"
    (repo / ".github" / "trigger").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "ops").mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    (repo / ".github" / "workflows" / "petri_audit.yml").write_text(
        "on:\n  push:\n    paths:\n      - \".github/trigger/petri-audit.json\"\n", encoding="utf-8")
    (repo / ".github" / "trigger" / f"{TRIGGER}.json").write_text(
        json.dumps(dict(ft.PARK_DEFAULTS[TRIGGER], _parked="true"), separators=(",", ":")) + "\n", encoding="utf-8")
    (repo / "ops" / "trigger_journal.jsonl").write_text("", encoding="utf-8")
    (repo / "data").mkdir()
    (repo / "data" / "advice_providers.json").write_bytes((ROOT / "data" / "advice_providers.json").read_bytes())
    runs = repo / "data" / "petri" / "runs"
    (runs / "run_4242_1").mkdir(parents=True)
    (runs / "run_4242_1" / "manifest.json").write_text(json.dumps(
        {"artifacts": {"judge_of_record": {"judge_model": "claude-haiku-4-5", "judge_max_tokens": 300}}}),
        encoding="utf-8")
    (runs / "manifests.chain").write_text("run_4242_1/manifest.json " + "e" * 64 + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "a landed run, the lane parked")
    return repo


def test_the_fire_path_refuses_what_it_can_see_before_the_reservation(tmp_path):
    repo = _repo(tmp_path)
    assert ft.petri_rejudge_source_problems(repo, TRIGGER, REJUDGE) == []
    assert ft.petri_rejudge_source_problems(repo, TRIGGER, dict(REJUDGE, mode="run")) == [], "other modes: nothing"
    for change, needle in (({"source_runs": "run_9_1"}, "holds no landed run"),
                           ({"judge_model": "claude-haiku-4-5"}, "is its judge of record"),
                           ({"judge_model": "anthropic:claude-haiku-4-5"}, "is its judge of record"),
                           ({"judge_max_tokens": "500"}, "ran with judge_max_tokens 300")):
        problems = ft.petri_rejudge_source_problems(repo, TRIGGER, dict(REJUDGE, **change))
        assert len(problems) == 1 and needle in problems[0], (change, problems)
    chain = repo / "data" / "petri" / "runs" / "manifests.chain"
    chain.write_text("", encoding="utf-8")
    assert "does not name it" in ft.petri_rejudge_source_problems(repo, TRIGGER, REJUDGE)[0]
    chain.write_text("run_4242_1/manifest.json " + "e" * 64 + "\n", encoding="utf-8")
    out = repo / "data" / "petri" / "rejudge" / PAID_SLUG / "run_4242_1"
    out.mkdir(parents=True)
    (out / "run_4242_1.rejudge_700.judge.report.json").write_text("{}", encoding="utf-8")
    assert ft.petri_rejudge_source_problems(repo, TRIGGER, REJUDGE) == [], "an earlier failed fire's sidecar alone"
    for name, needle in (("rejudge_manifest.json", "already holds a re-grade"),
                         ("judgments.jsonl", "already holds a re-grade"),
                         ("notes.txt", "holds files other than earlier rejudge fires' judge sidecars")):
        (out / name).write_text("x", encoding="utf-8")
        problems = ft.petri_rejudge_source_problems(repo, TRIGGER, REJUDGE)
        assert len(problems) == 1 and needle in problems[0], (name, problems)
        (out / name).unlink()


def test_the_dry_run_prints_the_judge_ceiling_on_the_openrouter_lane_and_the_lane_must_be_idle(tmp_path, capsys):
    repo = _repo(tmp_path)
    fire = ["fire", "--repo", str(repo), "--trigger", TRIGGER, "--note", "rejudge", "--dry-run", "--no-git"]
    assert ft.main(fire + ["--params", json.dumps(REJUDGE)]) == 0
    out = capsys.readouterr().out
    assert "max_spend 1.60 + today's committed 0.00" in out and "[openrouter lane]" in out, out
    assert '"max_spend": 1.6' in out and '"lane": "openrouter"' in out and '"nonce": "rj-1"' in out
    assert ft.main(fire + ["--params", json.dumps(dict(REJUDGE, judge_model="claude-haiku-4-5"))]) == 3
    assert "is its judge of record" in capsys.readouterr().err
    # only into an idle lane: a queued rejudge would find the output directory empty in its own checkout
    journal = repo / "ops" / "trigger_journal.jsonl"
    running = {"trigger": TRIGGER, "fired_utc": ft.iso_utc(ft.utc_now()), "commit": "", "note": "running",
               "resolved": False, "evicted": False, "nonce": "other", "max_spend": 0.5, "lane": "openrouter"}
    journal.write_text(json.dumps(running) + "\n", encoding="utf-8")
    assert ft.main(fire + ["--params", json.dumps(REJUDGE)]) == 2
    assert "a rejudge fires only when the lane is idle" in capsys.readouterr().err
    # ...and nothing enters behind an active rejudge, whatever its mode (its content is read by the digest it journaled)
    content = json.dumps(REJUDGE, separators=(",", ":")) + "\n"
    (repo / ".github" / "trigger" / f"{TRIGGER}.json").write_text(content, encoding="utf-8")
    active = dict(running, nonce="rj-1", params_sha256=ft.params_digest(content), max_spend=1.6)
    journal.write_text(json.dumps(active) + "\n", encoding="utf-8")
    assert ft.petri_active_readapt_problems(repo, TRIGGER, [active]) == [
        f"the active {TRIGGER} entry fired {active['fired_utc']} (nonce 'rj-1') is a rejudge (source_runs 'run_4242_1')"]
    park = dict(ft.PARK_DEFAULTS[TRIGGER], _nonce="p")
    assert ft.main(fire + ["--params", json.dumps(park)]) == 2
    assert "No petri-audit fire of any mode enters the lane while a readapt or a rejudge is active" in \
        capsys.readouterr().err


def test_the_budget_gate_refuses_the_same_rejudges_and_clears_the_rehearsal(tmp_path, capsys):
    repo = _repo(tmp_path)
    params_file = tmp_path / "gate_params.json"
    args = type("Args", (), {"repo": str(repo), "trigger": TRIGGER, "params_file": str(params_file)})()
    params_file.write_text(json.dumps(dict(REJUDGE, judge_model="claude-haiku-4-5")), encoding="utf-8")
    assert ft.cmd_budget_gate(args) == 6 and "is its judge of record" in capsys.readouterr().err
    params_file.write_text(json.dumps(dict(REJUDGE, judge_model=MOCK, commit_outputs="false", _nonce="")),
                           encoding="utf-8")
    assert ft.cmd_budget_gate(args) == 0 and "free fire" in capsys.readouterr().out


# ------------------------------------------------------------ the params job, run as CI runs it


def _resolve_step_python() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["params"]["steps"] if s.get("name") == "Resolve parameters")
    m = re.search(r"python - <<'EOF'\n(.*?)\nEOF", step["run"], re.S)
    assert m
    return m.group(1)


def _run_params_job(tmp_path: Path, cfg: dict, *, event: str = "push", attempt: str = "1") -> tuple[int, str, str]:
    trigger_dir = tmp_path / ".github" / "trigger"
    trigger_dir.mkdir(parents=True, exist_ok=True)
    (trigger_dir / f"{TRIGGER}.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "EVENT_NAME": event, "RUN_ATTEMPT": attempt, "GITHUB_OUTPUT": str(out)}
    if event != "push":
        env.update({f"IN_{k.upper()}": str(v) for k, v in cfg.items() if not k.startswith("_")})
    proc = subprocess.run([sys.executable, "-"], input=_resolve_step_python(), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    return proc.returncode, out.read_text(encoding="utf-8"), proc.stderr


def test_the_params_job_resolves_a_rejudge_and_joins_a_list_of_source_runs(tmp_path):
    rc, out, err = _run_params_job(tmp_path, dict(REJUDGE, source_runs=["run_4242_1", "run_4343_1"]))
    assert rc == 0, err
    assert "mode=rejudge\n" in out and "source_runs=run_4242_1 run_4343_1\n" in out and "_nonce=rj-1\n" in out
    assert f"judge_model={PAID_JUDGE}\n" in out and "judge_max_spend=1.60\n" in out
    # the park and every other mode resolve source_runs empty
    rc, out, err = _run_params_job(tmp_path, dict(ft.PARK_DEFAULTS[TRIGGER]))
    assert rc == 0 and "source_runs=\n" in out, err


@pytest.mark.parametrize("cfg, needle", [
    (dict(REJUDGE, source_runs=""), "mode rejudge needs source_runs"),
    (dict(REJUDGE, source_runs="run_1_1 run_1_1"), "mode rejudge needs source_runs"),
    (dict(REJUDGE, source_runs="run_１_1"), "mode rejudge needs source_runs"),
    (dict(REJUDGE, judge="false"), "mode rejudge runs a judge"),
    (dict(REJUDGE, judge_model=f"{PAID_JUDGE} "), "spelled exactly"),
    (dict(REJUDGE, judge_model=MOCK, commit_outputs="true"), "is never committed"),
    (dict(REJUDGE, mode="run", target="anthropic/claude-haiku-4-5"), "source_runs is read by mode rejudge only"),
])
def test_the_params_job_refuses_a_rejudge_it_cannot_run_before_any_output(tmp_path, cfg, needle):
    rc, out, err = _run_params_job(tmp_path, cfg)
    assert rc != 0 and needle in err, err
    assert out == ""


def test_a_paid_rejudge_is_admitted_from_a_first_attempt_push_only_and_the_rehearsal_from_anywhere(tmp_path):
    rc, out, err = _run_params_job(tmp_path, REJUDGE, attempt="2")
    assert rc != 0 and "a paid rejudge cannot be re-run from the Actions tab" in err and out == ""
    rc, out, err = _run_params_job(tmp_path, REJUDGE, event="workflow_dispatch")
    assert rc != 0 and "a paid rejudge is fired through scripts/fire_trigger.py only" in err and out == ""
    rehearsal = dict(REJUDGE, judge_model=MOCK, commit_outputs="false")
    for event, attempt in (("workflow_dispatch", "1"), ("push", "2")):
        rc, out, err = _run_params_job(tmp_path, rehearsal, event=event, attempt=attempt)
        assert rc == 0 and "mode=rejudge\n" in out and f"judge_model={MOCK}\n" in out, (event, attempt, err)


@pytest.mark.parametrize("change", [
    {}, {"judge_model": MOCK, "commit_outputs": "false"}, {"judge_model": MOCK, "commit_outputs": "true"},
    {"source_runs": ""}, {"source_runs": "run_1_1 run_1_1"}, {"source_runs": "run_1"}, {"source_runs": ["run_1_1"]},
    {"judge": "false"}, {"judge": True}, {"judge_model": f" {PAID_JUDGE}"}, {"judge_model": ""},
    {"mode": "Rejudge"}, {"mode": "rejudge "}, {"target": "anthropic/claude-haiku-4-5"},
    {"target": "openai/gpt-5.4-mini"}, {"source_run_id": "12"}, {"source_run_id": None}, {"source_runs": None},
    {"judge_model": "MockLLM/Judge"},
])
def test_the_fire_guard_refuses_exactly_the_rejudges_the_params_job_refuses(tmp_path, change):
    """The fire path journals a reservation before the params job runs, so a rejudge the job would refuse must be
    refused at the fire too. Same trigger file, both checks, same verdict (the nonce rule, the judge's key routing and
    the plan's judge-spec rules are the guard's own, stricter than the job, and are held constant here)."""
    cfg = dict(REJUDGE, **change)
    rc, _, err = _run_params_job(tmp_path, cfg)
    try:
        ft.validate_params(TRIGGER, cfg)
        admitted = True
    except ValueError as exc:
        admitted, why = False, str(exc)
    assert admitted == (rc == 0), (change, rc, err.strip(), None if admitted else why)


# ------------------------------------------------------------ the workflow


def test_mode_rejudge_runs_its_own_job_and_no_step_of_the_audit_job(workflow):
    audit, rejudge_job = workflow["jobs"]["audit"], workflow["jobs"]["rejudge"]
    assert rejudge_job["needs"] == "params" and "!github.event.created" in rejudge_job["if"]
    for mode in ("preflight", "dry_run", "run", "readapt"):
        assert _runs(audit["if"], mode=mode) and not _runs(rejudge_job["if"], mode=mode), mode
    assert not _runs(audit["if"], mode="rejudge") and _runs(rejudge_job["if"], mode="rejudge")
    names = [s.get("name", s.get("uses", "")) for s in rejudge_job["steps"]]
    assert not any(n.startswith(("Run (", "Adapt", "Download", "Plan the readapt", "Preflight", "Validate seeds"))
                   for n in names), "no target call and no adaptation"
    assert workflow["jobs"]["params"]["outputs"]["source_runs"] == "${{ steps.params.outputs.source_runs }}"
    on = workflow.get("on") or workflow.get(True)
    assert on["workflow_dispatch"]["inputs"]["source_runs"]["default"] == ""
    # the same pinned actions and interpreter as the audit job
    for step in rejudge_job["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
    setup = next(s for s in rejudge_job["steps"] if str(s.get("uses", "")).startswith("actions/setup-python"))
    assert setup["with"]["python-version"] == "3.12.3"
    assert names.index("Verify the environment lock (refuses any drift before a model call)") < names.index(
        "Plan the rejudge (verify the source runs and the instrument; no model call)") < names.index(
        "Rejudge (paid unless the judge is mockllm/judge; no target call)")


def test_the_rejudge_steps_run_plan_judge_verify_and_commit_in_order(workflow):
    plan = _step(workflow, "rejudge", "Plan the rejudge")
    assert plan["id"] == "plan" and plan["env"]["RESOLVED_PARAMS"] == "${{ toJSON(needs.params.outputs) }}"
    for flag in ("rejudge-plan", "--runs-dir data/petri/runs", "--rejudge-root data/petri/rejudge",
                 '--rejudge-run-id "$GITHUB_RUN_ID"', '--rejudge-run-attempt "$GITHUB_RUN_ATTEMPT"',
                 '--rejudge-commit "$GITHUB_SHA"', '--out "$RUNNER_TEMP/petri-rejudge/plan.json"'):
        assert flag in plan["run"], flag
    judge = _step(workflow, "rejudge", "Rejudge (paid")
    assert {"ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"} == set(judge["env"])
    assert '--started-dir "$RUNNER_TEMP/petri-rejudge/started"' in judge["run"]
    verify = _step(workflow, "rejudge", "Verify the re-grades and seal-check exactly what is staged")
    assert verify["id"] == "verify" and "verify-chain" in verify["run"]
    for flag in ('verify-rejudge --plan "$RUNNER_TEMP/petri-rejudge/plan.json"', "--copy-to",
                 '--verified-list "$RUNNER_TEMP/petri-rejudge/verified.txt"',
                 '--stage-list "$RUNNER_TEMP/petri-rejudge/stage.txt"', 'seal_check.py --site "$RUNNER_TEMP/no-site"',
                 '--extra "$EXTRA"', 'EXTRA="data/petri/runs"', 'echo "verified='):
        assert flag in verify["run"], flag
    # the seal check sweeps exactly the staged list (and the runs read), after the list is written
    body = verify["run"]
    assert body.index("--stage-list") < body.index('done < "$RUNNER_TEMP/petri-rejudge/stage.txt"') < body.index("seal_check.py")
    assert "data/petri/rejudge" not in body.split("seal_check.py", 1)[1].split("\n", 1)[0], "never the root wholesale"
    steps = _job_steps(workflow, "rejudge")
    names = [s.get("name", "") for s in steps]
    commit = _step(workflow, "rejudge", "Commit the re-grades")
    sidecars = _step(workflow, "rejudge", "Commit rejudge cost sidecars")
    upload = _step(workflow, "rejudge", "Upload the seal-cleared re-grades")
    rawlog = _step(workflow, "rejudge", "Refuse to publish a raw log")
    assert rawlog["id"] == "rawlog"
    assert names.index(verify["name"]) < names.index(rawlog["name"]) < names.index(upload["name"]) \
        < names.index(commit["name"]) < names.index(sidecars["name"])
    # the commit stages exactly the list verify-rejudge wrote; never the rejudge root wholesale
    assert 'while IFS= read -r path; do git add -f -- "$path"; done < "$RUNNER_TEMP/petri-rejudge/stage.txt"' in commit["run"]
    assert "git add -f data/petri/rejudge/" not in commit["run"] and "data/petri/runs" not in commit["run"]
    assert "continue-on-error" not in commit
    # the cost sidecars: every paid rejudge, whatever happened; never the rehearsal; only report files are staged
    assert _runs(sidecars["if"], rehearsal="false") and not _runs(sidecars["if"], rehearsal="true")
    assert "for f in data/petri/rejudge/*/*/*.report.json" in sidecars["run"]
    assert "data/petri/runs" not in sidecars["run"] and "git add -f data/petri/rejudge/ " not in sidecars["run"]
    spend = _step(workflow, "rejudge", "Spend report for a rejudge judge")
    assert _runs(spend["if"], rehearsal="false") and not _runs(spend["if"], rehearsal="true")
    assert "rejudge-spend-report" in spend["run"]
    # the recovery upload is non-blocking only where a commit follows it; the rehearsal's copy is its only one
    assert upload["continue-on-error"] == ("${{ needs.params.outputs.rehearsal != 'true' && "
                                           "needs.params.outputs.commit_outputs == 'true' }}")
    assert upload["with"]["path"] == "${{ runner.temp }}/petri-rejudge/exports/"
    assert upload["with"]["if-no-files-found"] == "error" and "petri-run/logs" not in upload["with"]["path"]
    summary = _step(workflow, "rejudge", "Job summary")
    assert "always()" in summary["if"] and "rejudge-summary" in summary["run"] and "--seal-scan" in summary["run"]
    for step in steps:
        assert "${{ secrets." not in (step.get("run") or ""), step.get("name")
        # no rejudge step reads the judge spec to decide paid or rehearsal: `!=` in an expression ignores case
        assert "outputs.judge_model !=" not in str(step.get("if", "")) + str(step.get("continue-on-error", "")), \
            step.get("name")


def test_a_later_runs_abort_does_not_skip_the_verification_upload_or_commit_of_an_earlier_one(workflow):
    """PR #41 review: when the judge aborted on a later source run, the Rejudge step failed and every step gated on
    success (verify, upload, commit) was skipped, so an earlier run's completed re-grade was discarded and its retry
    paid again. They now run whenever the plan succeeded, over what verify-rejudge verified."""
    verify = _step(workflow, "rejudge", "Verify the re-grades")
    upload = _step(workflow, "rejudge", "Upload the seal-cleared re-grades")
    commit = _step(workflow, "rejudge", "Commit the re-grades")
    aborted = {"plan": {"outcome": "success"}, "rejudge": {"outcome": "failure"},
               "verify": {"outcome": "success", "outputs": {"verified": "1"}}, "rawlog": {"outcome": "success"}}
    paid = {"rehearsal": "false", "commit_outputs": "true"}
    assert _runs(verify["if"], aborted, **paid) and _runs(upload["if"], aborted, **paid) and _runs(commit["if"], aborted, **paid)
    # nothing verified (the first run aborted): nothing to upload or commit; the sidecar step books the spend
    none_verified = dict(aborted, verify={"outcome": "success", "outputs": {"verified": "0"}})
    assert not _runs(upload["if"], none_verified, **paid) and not _runs(commit["if"], none_verified, **paid)
    # fail closed: a verification or seal failure, or a raw log in the checkout, stops the upload and the commit
    for broken in ({"verify": {"outcome": "failure", "outputs": {"verified": "1"}}}, {"rawlog": {"outcome": "failure"}}):
        state = {**aborted, **broken}
        assert not _runs(upload["if"], state, **paid) and not _runs(commit["if"], state, **paid), broken
    # the plan refused: nothing was judged, so nothing is verified
    assert not _runs(verify["if"], {"plan": {"outcome": "failure"}}, **paid)
    # the rehearsal uploads and never commits; a paid rejudge without commit_outputs uploads only
    assert _runs(upload["if"], aborted, rehearsal="true", commit_outputs="false")
    assert not _runs(commit["if"], aborted, rehearsal="true", commit_outputs="false")
    assert not _runs(commit["if"], aborted, rehearsal="false", commit_outputs="false")


def test_the_params_job_emits_the_rehearsal_flag_from_an_exact_comparison(tmp_path, workflow):
    assert workflow["jobs"]["params"]["outputs"]["rehearsal"] == "${{ steps.params.outputs.rehearsal }}"
    for cfg, flag in ((dict(REJUDGE, judge_model=MOCK, commit_outputs="false"), "true"), (REJUDGE, "false"),
                      (dict(ft.PARK_DEFAULTS[TRIGGER]), "false"),
                      (dict(ft.PARK_DEFAULTS[TRIGGER], judge_model=MOCK), "false")):
        rc, out, err = _run_params_job(tmp_path, cfg)
        assert rc == 0 and f"rehearsal={flag}\n" in out, (cfg, err)


@pytest.mark.parametrize("spec", ["MockLLM/Judge", "mockllm/JUDGE", "MOCKLLM/MODEL", "None/None"])
def test_a_sentinel_spelled_in_another_case_is_refused_by_the_guard_the_job_and_the_plan(tmp_path, spec):
    """GitHub's expression `!=` compares strings ignoring case: `MockLLM/Judge` gated the steps as the rehearsal while
    every Python check read it as a paid judge (PR #41 review). It is refused everywhere."""
    cfg = dict(REJUDGE, judge_model=spec)
    with pytest.raises(ValueError, match="differs from a test sentinel in case alone"):
        ft.validate_params(TRIGGER, cfg)
    rc, out, err = _run_params_job(tmp_path, cfg)
    assert rc != 0 and "differs from a test sentinel in case alone" in err and out == ""
    from scripts.petri_audit import rejudge

    assert "in case alone" in (rejudge.sentinel_case_problem(spec) or "")
    assert any("in case alone" in p for p in rejudge.judge_spec_refusals(spec)), "cli rejudge's own re-check too"
    assert rejudge.sentinel_case_problem("mockllm/judge") is None and rejudge.sentinel_case_problem(PAID_JUDGE) is None


def test_the_trigger_docs_name_the_mode_and_its_key():
    doc = (ROOT / "docs" / "triggers.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "`mode: rejudge`" in doc and "`source_runs`" in doc and "data/petri/rejudge/" in doc
    assert "`mode: rejudge`" in agents


# ------------------------------------------------------------ PR #41 review: what the fire guard admits and the job refuses


@pytest.mark.parametrize("base, change", [
    ({"mode": "run", "target": "anthropic/claude-haiku-4-5", "judge": "false", "commit_outputs": "false", "_nonce": "n"},
     {"source_runs": None}),
    ({"mode": "run", "target": "anthropic/claude-haiku-4-5", "judge": "false", "commit_outputs": "false", "_nonce": "n"},
     {"source_run_id": None}),
    ({"mode": "preflight", "commit_outputs": "false"}, {"source_runs": None}),
    ({"mode": "preflight", "commit_outputs": "false"}, {"source_run_id": None}),
    (REJUDGE, {"source_runs": None}),
    (REJUDGE, {"source_run_id": None}),
])
def test_a_json_null_the_job_reads_as_the_string_none_is_refused_at_the_fire_too(tmp_path, base, change):
    """The params job `str()`s every value, so a JSON null is "None": outside the mode that reads the key it is a
    value the job refuses, and the guard journaled a reservation for it (PR #41 review)."""
    cfg = dict(base, **change)
    rc, _, err = _run_params_job(tmp_path, cfg)
    assert rc != 0, err
    with pytest.raises(ValueError):
        ft.validate_params(TRIGGER, cfg)


def test_a_readapt_still_refuses_a_null_source_run_id_as_before():
    readapt = {"mode": "readapt", "source_run_id": None, "target": "anthropic/claude-haiku-4-5", "judge": "true",
               "judge_model": "claude-haiku-4-5", "judge_max_spend": "1.0", "commit_outputs": "true", "_nonce": "r"}
    with pytest.raises(ValueError, match="mode readapt needs source_run_id"):
        ft.validate_params(TRIGGER, readapt)


@pytest.mark.parametrize("spec", ["mockllm/model", "none/none", "foo:bar", "copilot", "copilot:x", "openrouter",
                                  "openrouter:", "openrouter:openai/gpt-5.5", "_readme:x"])
def test_the_fire_guard_refuses_the_judge_specs_the_plan_refuses(spec):
    """The plan refuses these before any call, but only after the fire's reservation held the day's ceiling; the
    guard now refuses them first (a mirror of judge_runner.judge_spec_problems and spend.openrouter_price_problems)."""
    with pytest.raises(ValueError):
        ft.validate_params(TRIGGER, dict(REJUDGE, judge_model=spec))


@pytest.mark.parametrize("spec", ["mockllm/model", "none/none", "foo:bar", "copilot", "copilot:x", "openrouter",
                                  "openrouter:", "openrouter:openai/gpt-5.5", "openrouter:openai/gpt-5.4-mini",
                                  "openrouter:x-ai/grok-4.3", "openrouter:google/gemini-3.5-flash", "xai",
                                  "xai:x-ai/grok-4.3", "openai", "openai:gpt-5.4-mini", "claude-sonnet-4-5",
                                  "anthropic:claude-haiku-4-5", "deepseek", "moonshot"])
def test_the_guards_judge_spec_rule_is_the_plans(spec):
    from scripts.petri_audit import rejudge

    guard = ft.petri_judge_spec_problems(spec)
    plan = rejudge.judge_spec_refusals(spec)
    # the plan's key-routing refusal (google:, GEMINI_API_KEY) is the guard's own separate rule; none of these bill it
    assert bool(guard) == bool(plan), (spec, guard, plan)
