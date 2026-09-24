"""The petri-audit lane's `mode: readapt` (2026-09-24) on the fire path and in
the workflow: the params validation, the commitment (judge_max_spend alone),
the match against the parameters the source fire journaled, the idle-lane
rule, and the workflow's step conditions and download wiring, read from the
YAML as tests/test_petri_audit_workflow.py reads it. Nothing here fires: the
fire path runs `--dry-run --no-git` in a temporary repository."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "petri_audit.yml"
TRIGGER = "petri-audit"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("fire_trigger")


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(workflow: dict) -> list[dict]:
    return workflow["jobs"]["audit"]["steps"]


def _step(workflow: dict, prefix: str) -> dict:
    for step in _steps(workflow):
        if step.get("name", "").startswith(prefix):
            return step
    raise AssertionError(f"no step named {prefix!r}")


def _runs(expr, **outputs) -> bool:
    """Whether a step's `if:` admits it for the given params outputs, `always()` read as true (a success path).
    Evaluated by translating the expression to Python: the step conditions use only ==, !=, &&, ||, parentheses
    and needs.params.outputs.<key>."""
    if expr is None:
        return True
    body = str(expr).strip()
    assert body.startswith("${{") and body.endswith("}}"), body
    body = body[3:-2].replace("always()", "True")
    body = re.sub(r"needs\.params\.outputs\.(\w+)", lambda m: repr(outputs[m.group(1)]), body)
    body = body.replace("!=", " __NE__ ").replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    return bool(eval(body.replace("__NE__", "!="), {"__builtins__": {}}, {}))  # noqa: S307 - a literal expression


# ------------------------------------------------------------ the workflow


def test_readapt_skips_the_run_step_downloads_the_source_log_and_otherwise_runs_as_mode_run(workflow):
    """Mode readapt makes no target call: the run step is gated off, the plan and download steps run in its place,
    and every step after them runs exactly when it runs for mode run."""
    steps = _steps(workflow)
    names = [s.get("name", s.get("uses", "")) for s in steps]

    def admitted(mode: str) -> set[str]:
        outs = {"mode": mode, "judge": "true", "commit_outputs": "true"}
        return {n for n, s in zip(names, steps) if _runs(s.get("if"), **outs)}

    readapt, run, dry, pre = admitted("readapt"), admitted("run"), admitted("dry_run"), admitted("preflight")
    plan = "Plan the readapt (mode readapt; locate the source run's raw-eval artifact; no model call)"
    download = "Download the source run's raw .eval (mode readapt; outside the checkout)"
    run_step = "Run (mode dry_run or run; the raw .eval is written OUTSIDE the checkout)"
    assert run_step not in readapt and run_step in run and run_step in dry
    assert {plan, download} <= readapt and not ({plan, download} & (run | dry | pre))
    assert readapt - {plan, download} == run - {run_step}, "once the source log is in place, readapt is mode run"
    assert names.index(plan) < names.index(download) < names.index(
        "Adapt (sanitised export, transcripts 0.2, rule outcomes, manifest, cost sidecar)")
    judge = _step(workflow, "Judge of record")
    assert _runs(judge["if"], mode="readapt", judge="true") and not _runs(judge["if"], mode="readapt", judge="false")
    sidecars = _step(workflow, "Commit cost sidecars")
    assert _runs(sidecars["if"], mode="readapt") and not _runs(sidecars["if"], mode="dry_run")
    commit = _step(workflow, "Commit sanitised outputs")
    assert _runs(commit["if"], mode="readapt", commit_outputs="true")
    assert not _runs(commit["if"], mode="readapt", commit_outputs="false")
    # the run directory: the source run's under readapt, one per attempt otherwise
    stem = workflow["jobs"]["audit"]["env"]["RUN_STEM"]
    assert "format('run_{0}_1', needs.params.outputs.source_run_id)" in stem
    assert "format('run_{0}_{1}', github.run_id, github.run_attempt)" in stem


def test_readapt_downloads_the_named_artifact_with_a_pinned_action_and_the_existing_token_scope(workflow):
    plan = _step(workflow, "Plan the readapt")
    assert plan["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert plan["env"]["SOURCE_RUN_ID"] == "${{ needs.params.outputs.source_run_id }}"
    assert 'gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN_ID/artifacts?per_page=100"' in plan["run"]
    assert "readapt-plan" in plan["run"] and '--out "$RUNNER_TEMP/petri-readapt/plan.json"' in plan["run"]
    for flag in ('--readapt-run-id "$GITHUB_RUN_ID"', '--readapt-run-attempt "$GITHUB_RUN_ATTEMPT"',
                 '--readapt-commit "$GITHUB_SHA"', "--runs-dir data/petri/runs"):
        assert flag in plan["run"], flag
    download = _step(workflow, "Download the source run's raw .eval")
    action, _, sha = str(download["uses"]).partition("@")
    assert action == "actions/download-artifact" and re.fullmatch(r"[0-9a-f]{40}", sha), download["uses"]
    assert download["with"] == {"name": "petri-audit-raw-eval-${{ needs.params.outputs.source_run_id }}-1",
                                "run-id": "${{ needs.params.outputs.source_run_id }}",
                                "github-token": "${{ github.token }}",
                                "path": "${{ runner.temp }}/petri-run/logs"}
    # the cross-run listing and download need actions: read, which the workflow already held; nothing was added
    assert workflow["permissions"] == {"contents": "write", "actions": "read"}
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
    adapt = _step(workflow, "Adapt")
    assert 'SOURCE=(--readapt "$RUNNER_TEMP/petri-readapt/plan.json")' in adapt["run"] and '"${SOURCE[@]}"' in adapt["run"]
    assert adapt["env"]["MODE"] == "${{ needs.params.outputs.mode }}"
    spend = _step(workflow, "Spend report for an attempted run")
    assert 'if [ "$MODE" = "readapt" ]; then' in spend["run"], "a readapt imputes no target spend"
    assert spend["run"].index('"$MODE" = "readapt"') < spend["run"].index("spend-report --out")
    params = workflow["jobs"]["params"]
    assert params["outputs"]["source_run_id"] == "${{ steps.params.outputs.source_run_id }}"


# ------------------------------------------------------------ the fire path


def test_mode_readapt_is_a_paid_fire_whose_commitment_is_the_judge_ceiling_alone():
    base = dict(ft.PARK_DEFAULTS[TRIGGER], mode="readapt", source_run_id="35937014168",
                target="anthropic/claude-haiku-4-5", max_spend="6.10", judge="true", judge_model="claude-haiku-4-5",
                judge_max_spend="2.50", commit_outputs="true", _nonce="w2e3r")
    assert "source_run_id" in ft.KNOWN_KEYS[TRIGGER] and "source_run_id" not in ft.PARK_DEFAULTS[TRIGGER]
    assert ft.PARK_DEFAULTS[TRIGGER]["mode"] == "preflight", "the park is unchanged"
    assert ft.is_paid_fire(TRIGGER, base) is True
    assert ft.fire_commitment(base) == (2.5, None), "the target ceiling is the source fire's, already reserved"
    assert ft.fire_commitment(dict(base, mode="run")) == (pytest.approx(8.6), None), "mode run is unchanged"
    assert ft.fire_lane(TRIGGER, base) == "anthropic"
    ft.validate_params(TRIGGER, base)
    commitment, error = ft.fire_commitment(dict(base, judge="false"))
    assert commitment is None and "judge=true" in error
    for bad, needle in (({"source_run_id": ""}, "needs source_run_id"), ({"source_run_id": "12a"}, "needs source_run_id"),
                        ({"source_run_id": True}, "needs source_run_id"), ({"judge": "false"}, "must run the judge of record"),
                        ({"_nonce": ""}, "mode readapt must carry a non-empty _nonce"),
                        ({"target": "mockllm/model"}, "mode readapt must not target the test sentinel"),
                        ({"sourcerunid": "1"}, "unknown petri-audit key")):
        with pytest.raises(ValueError, match=needle):
            ft.validate_params(TRIGGER, dict(base, **bad))
    # the key is refused outside the mode that reads it
    with pytest.raises(ValueError, match="read by mode readapt only"):
        ft.validate_params(TRIGGER, dict(base, mode="run"))
    ft.validate_params(TRIGGER, dict(base, mode="run", source_run_id=""))
    # the in-flight reservation a CI gate checks is the same judge-only figure
    entry = {"trigger": TRIGGER, "fired_utc": ft.iso_utc(ft.utc_now()), "resolved": False, "evicted": False,
             "nonce": "w2e3r", "max_spend": 2.5, "lane": "anthropic", "params_sha256": "d" * 64}
    assert ft.journal_reservation_problems(TRIGGER, base, [entry], digest="d" * 64) == []


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *argv],
                   check=True, capture_output=True, text=True)


SOURCE_PARAMS = {"mode": "run", "target": "anthropic/claude-haiku-4-5",
                 "seed_ids": "pw-petri-w2-tool-clarify pw-petri-w2-referral-specificity", "epochs": "1",
                 "token_limit": "40000", "max_spend": "6.10", "judge": "true", "judge_model": "claude-haiku-4-5",
                 "judge_max_spend": "1.50", "commit_outputs": "true", "_nonce": "w2e3", "_note": "the source fire"}


def _readapt_repo(tmp_path: Path) -> tuple[Path, dict]:
    """A branch that carries a source fire (its trigger file and journal entry, committed together as
    fire_trigger commits them), the park after it, and the source run's landed fallback sidecar; and readapt
    params that match the source."""
    repo = tmp_path / "repo"
    trigger_dir = repo / ".github" / "trigger"
    trigger_dir.mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "ops").mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    (repo / ".github" / "workflows" / "petri_audit.yml").write_text(
        "on:\n  push:\n    paths:\n      - \".github/trigger/petri-audit.json\"\n", encoding="utf-8")
    trigger = trigger_dir / f"{TRIGGER}.json"
    content = json.dumps(SOURCE_PARAMS, separators=(",", ":")) + "\n"
    trigger.write_text(content, encoding="utf-8")
    entry = {"trigger": TRIGGER, "fired_utc": "2026-09-20T00:08:16Z", "commit": "", "note": "source", "resolved": True,
             "resolved_utc": "2026-09-20T00:13:10Z", "evicted": False, "nonce": "w2e3",
             "params_sha256": ft.params_digest(content), "ref": "main", "max_spend": 7.6, "lane": "anthropic"}
    (repo / "ops" / "trigger_journal.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fire the source run")
    trigger.write_text(json.dumps(dict(ft.PARK_DEFAULTS[TRIGGER], _parked="true"), separators=(",", ":")) + "\n",
                       encoding="utf-8")
    run_dir = repo / "data" / "petri" / "runs" / "run_4242_1"
    run_dir.mkdir(parents=True)
    (run_dir / "run_4242_1.report.json").write_text(json.dumps(
        {"run_id": "run_4242_1", "eval_id": "E1", "journal_nonce": "w2e3", "eval_log": "x.eval", "run_status": "success",
         "spend_report_reason": "run attempted; no adapted report exists (run or adaptation failed)"}), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "park, and the source run's sidecar")
    readapt = {k: v for k, v in SOURCE_PARAMS.items() if not k.startswith("_")}
    readapt.update(mode="readapt", source_run_id="4242", max_spend="6.1", _nonce="w2e3r")
    return repo, readapt


def test_a_readapt_must_state_the_parameters_its_source_fire_ran_under(tmp_path):
    """The source fire's journal entry records the digest of the trigger file it wrote; that content is recovered
    from the branch's history, and every parameter the log and the judge ran under must match it."""
    repo, readapt = _readapt_repo(tmp_path)
    assert ft.petri_readapt_source_problems(repo, TRIGGER, readapt) == []
    # the workflow's own resolution: 6.1 is 6.10, a list of ids is the space-joined string, a JSON boolean is "true"
    assert ft.petri_readapt_source_problems(repo, TRIGGER, dict(readapt, seed_ids=SOURCE_PARAMS["seed_ids"].split(),
                                                                judge=True)) == []
    for key, value in (("target", "anthropic/claude-sonnet-4-5"), ("judge_max_spend", "2.50"), ("epochs", "2"),
                       ("seed_ids", "pw-petri-w2-tool-clarify"), ("judge_model", "openai:gpt-5.4-mini"),
                       ("token_limit", "20000"), ("judge_max_tokens", "500"), ("seeds_file", "other.json"),
                       ("log_model_api", "false"), ("wave", "2"), ("max_spend", "5")):
        problems = ft.petri_readapt_source_problems(repo, TRIGGER, dict(readapt, **{key: value}))
        assert len(problems) == 1 and f"{key} " in problems[0] and "the parameters differ" in problems[0], (key, problems)
    assert ft.petri_readapt_source_problems(repo, TRIGGER, dict(readapt, mode="run")) == [], "other modes: nothing"
    assert ft.petri_readapt_source_problems(repo, "advice-eval", readapt) == []
    runs = repo / "data" / "petri" / "runs"
    assert "holds no landed target sidecar" in ft.petri_readapt_source_problems(
        repo, TRIGGER, dict(readapt, source_run_id="7"))[0]
    (runs / "run_4242_1" / "manifest.json").write_text("{}", encoding="utf-8")
    assert "already holds adapted outputs" in ft.petri_readapt_source_problems(repo, TRIGGER, readapt)[0]
    (runs / "run_4242_1" / "manifest.json").unlink()
    # a journal entry naming content the history does not hold: the parameters cannot be recovered, so refused
    journal = repo / "ops" / "trigger_journal.jsonl"
    entry = json.loads(journal.read_text(encoding="utf-8"))
    journal.write_text(json.dumps(dict(entry, params_sha256="f" * 64)) + "\n", encoding="utf-8")
    assert "is not in this branch's history" in ft.petri_readapt_source_problems(repo, TRIGGER, readapt)[0]
    journal.write_text("", encoding="utf-8")
    assert "0 journal entries carry the source nonce" in ft.petri_readapt_source_problems(repo, TRIGGER, readapt)[0]


def test_the_source_fire_is_found_through_a_merge_that_kept_the_other_sides_trigger_file(tmp_path):
    """The hand merge of a firing branch into main restores main's trigger files (AGENTS.md, merge danger), so the
    merge commit's trigger file is main's and git's default path simplification drops the fired side: the source
    fire's commit is an ancestor of main, but `git log -- <trigger file>` did not list it, and a readapt fired from
    main was refused as unrecoverable. The search follows full history; the digest still binds the content."""
    repo = tmp_path / "repo"
    trigger_dir = repo / ".github" / "trigger"
    trigger_dir.mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "ops").mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    (repo / ".github" / "workflows" / "petri_audit.yml").write_text(
        "on:\n  push:\n    paths:\n      - \".github/trigger/petri-audit.json\"\n", encoding="utf-8")
    trigger = trigger_dir / f"{TRIGGER}.json"
    trigger.write_text(json.dumps(dict(ft.PARK_DEFAULTS[TRIGGER], _parked="true"), separators=(",", ":")) + "\n",
                       encoding="utf-8")
    journal = repo / "ops" / "trigger_journal.jsonl"
    journal.write_text("", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main, parked")
    _git(repo, "switch", "-q", "-c", "side")
    content = json.dumps(SOURCE_PARAMS, separators=(",", ":")) + "\n"
    trigger.write_text(content, encoding="utf-8")
    journal.write_text(json.dumps({"trigger": TRIGGER, "fired_utc": "2026-09-20T00:08:16Z", "commit": "",
                                   "note": "source", "resolved": True, "evicted": False, "nonce": "w2e3",
                                   "params_sha256": ft.params_digest(content), "ref": "side", "max_spend": 7.6,
                                   "lane": "anthropic"}) + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fire the source run")
    fire_commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True,
                                 text=True).stdout.strip()
    trigger.write_text(json.dumps(dict(ft.PARK_DEFAULTS[TRIGGER], _parked="true", _nonce="side-park"),
                                  separators=(",", ":")) + "\n", encoding="utf-8")
    run_dir = repo / "data" / "petri" / "runs" / "run_4242_1"
    run_dir.mkdir(parents=True)
    (run_dir / "run_4242_1.report.json").write_text(json.dumps(
        {"run_id": "run_4242_1", "eval_id": "E1", "journal_nonce": "w2e3", "eval_log": "x.eval", "run_status": "success",
         "spend_report_reason": "run attempted; no adapted report exists (run or adaptation failed)"}), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "park, and the source run's sidecar")
    # the hand merge: main's copy of every trigger file is restored before the merge is committed
    _git(repo, "switch", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    _git(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", ".github/trigger/")
    _git(repo, "commit", "-q", "-m", "merge side, keeping main's trigger files")

    def git_out(*argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *argv], capture_output=True, text=True)

    assert git_out("merge-base", "--is-ancestor", fire_commit, "HEAD").returncode == 0
    assert fire_commit not in git_out("log", "--format=%H", "--", f".github/trigger/{TRIGGER}.json").stdout, \
        "the case under test: default simplification hides the fired side's versions of the file"
    readapt = {k: v for k, v in SOURCE_PARAMS.items() if not k.startswith("_")}
    readapt.update(mode="readapt", source_run_id="4242", max_spend="6.1", _nonce="w2e3r")
    assert ft.petri_readapt_source_problems(repo, TRIGGER, readapt) == []
    problems = ft.petri_readapt_source_problems(repo, TRIGGER, dict(readapt, epochs="2"))
    assert len(problems) == 1 and f"its trigger file at {fire_commit[:12]}" in problems[0], problems


def test_a_readapt_of_a_run_whose_eval_did_not_complete_is_refused_at_the_fire_and_the_gate(tmp_path, capsys):
    """The fallback sidecar is written for an error or cancelled run too, and records the eval's status; mode run
    adapts only a `success` run, so the fire path refuses any other before it journals a reservation, and the
    budget gate refuses it again before the audit job starts."""
    repo, readapt = _readapt_repo(tmp_path)
    sidecar = repo / "data" / "petri" / "runs" / "run_4242_1" / "run_4242_1.report.json"
    report = json.loads(sidecar.read_text(encoding="utf-8"))
    params_file = tmp_path / "gate_params.json"
    params_file.write_text(json.dumps(readapt), encoding="utf-8")
    args = type("Args", (), {"repo": str(repo), "trigger": TRIGGER, "params_file": str(params_file)})()
    fire = ["fire", "--repo", str(repo), "--trigger", TRIGGER, "--note", "readapt", "--dry-run", "--no-git",
            "--params", json.dumps(readapt)]
    for status in ("error", "cancelled", None):
        sidecar.write_text(json.dumps(dict(report, run_status=status)), encoding="utf-8")
        problems = ft.petri_readapt_source_problems(repo, TRIGGER, readapt)
        assert len(problems) == 1 and f"records run_status {status!r}, not 'success'" in problems[0], problems
        assert ft.cmd_budget_gate(args) == 6
        assert "a readapt recovers only a run whose eval completed" in capsys.readouterr().err
        assert ft.main(fire) == 3
        assert f"records run_status {status!r}" in capsys.readouterr().err
    sidecar.write_text(json.dumps(report), encoding="utf-8")
    assert ft.petri_readapt_source_problems(repo, TRIGGER, readapt) == []
    assert ft.main(fire) == 0, "the same fire with the success sidecar reaches the dry run"
    capsys.readouterr()


def test_the_budget_gate_and_the_fire_path_refuse_a_readapt_that_is_not_its_source(tmp_path, capsys):
    repo, readapt = _readapt_repo(tmp_path)
    params_file = tmp_path / "gate_params.json"
    params_file.write_text(json.dumps(dict(readapt, target="anthropic/claude-sonnet-4-5")), encoding="utf-8")
    args = type("Args", (), {"repo": str(repo), "trigger": TRIGGER, "params_file": str(params_file)})()
    assert ft.cmd_budget_gate(args) == 6
    assert "the parameters differ from those the source fire 'w2e3' ran under" in capsys.readouterr().err
    fire = ["fire", "--repo", str(repo), "--trigger", TRIGGER, "--note", "readapt", "--dry-run", "--no-git"]
    assert ft.main(fire + ["--params", json.dumps(dict(readapt, target="anthropic/claude-sonnet-4-5"))]) == 3
    assert "the parameters differ" in capsys.readouterr().err
    # the matching readapt reaches the dry run with the judge ceiling as its whole commitment
    assert ft.main(fire + ["--params", json.dumps(readapt)]) == 0
    out = capsys.readouterr().out
    assert '"nonce": "w2e3r"' in out and '"max_spend": 1.5' in out and '"lane": "anthropic"' in out, out
    # ...and only into an idle lane: a queued readapt would adapt against outputs older than the running fire's
    journal = repo / "ops" / "trigger_journal.jsonl"
    active = {"trigger": TRIGGER, "fired_utc": ft.iso_utc(ft.utc_now()), "commit": "", "note": "running",
              "resolved": False, "evicted": False, "nonce": "w2e4", "max_spend": 0.1, "lane": "anthropic"}
    journal.write_text(journal.read_text(encoding="utf-8") + json.dumps(active) + "\n", encoding="utf-8")
    assert ft.main(fire + ["--params", json.dumps(readapt)]) == 2
    assert "a readapt fires only when the lane is idle" in capsys.readouterr().err


def test_no_fire_of_any_mode_enters_the_lane_behind_an_active_readapt(tmp_path, capsys):
    """Codex, PR #29: the idle-lane rule refused a readapt behind an active fire but admitted a mode-run fire behind
    an active readapt. That run checks out its own trigger commit, whose manifest chain predates the readapt's
    appended head, so its outputs could not commit after its target and judge had spent. Every mode is refused now,
    the park included; the active entry's mode is read from the trigger content its digest names."""
    repo, readapt = _readapt_repo(tmp_path)
    trigger = repo / ".github" / "trigger" / f"{TRIGGER}.json"
    journal = repo / "ops" / "trigger_journal.jsonl"
    source_journal = journal.read_text(encoding="utf-8")
    readapt_content = json.dumps(readapt, separators=(",", ":")) + "\n"
    active = {"trigger": TRIGGER, "fired_utc": ft.iso_utc(ft.utc_now()), "commit": "", "note": "w2e3r running",
              "resolved": False, "evicted": False, "nonce": "w2e3r", "max_spend": 2.5, "lane": "anthropic",
              "params_sha256": ft.params_digest(readapt_content), "ref": "main"}
    trigger.write_text(readapt_content, encoding="utf-8")
    journal.write_text(source_journal + json.dumps(active) + "\n", encoding="utf-8")
    run = dict(SOURCE_PARAMS, _nonce="w2e4")
    fire = ["fire", "--repo", str(repo), "--trigger", TRIGGER, "--note", "next", "--dry-run", "--no-git"]
    for params in (run, dict(run, mode="preflight", judge="false", commit_outputs="false"),
                   dict(run, mode="dry_run", target="mockllm/model", judge="false", commit_outputs="false")):
        assert ft.main(fire + ["--params", json.dumps(params)]) == 2, params["mode"]
        err = capsys.readouterr().err
        assert "is a readapt (source_run_id '4242')" in err and "No petri-audit fire of any mode" in err, err
    park = ["park", "--repo", str(repo), "--trigger", TRIGGER, "--dry-run", "--no-git"]
    assert ft.main(park) == 2
    assert "is a readapt" in capsys.readouterr().err
    # the readapt's trigger commit is in the history rather than on disk (a later edit replaced the file): still found
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fire the readapt")
    trigger.write_text(json.dumps(dict(ft.PARK_DEFAULTS[TRIGGER], _parked="true", _nonce="later")) + "\n",
                       encoding="utf-8")
    assert ft.petri_active_readapt_problems(repo, TRIGGER, [active]) == [
        f"the active {TRIGGER} entry fired {active['fired_utc']} (nonce 'w2e3r') is a readapt (source_run_id '4242')"]
    # an active entry whose content cannot be recovered cannot be shown not to be a readapt: refused, by name
    for broken, needle in (({"params_sha256": None}, "records no params_sha256"),
                           ({"params_sha256": "f" * 64}, "neither on disk nor in this branch's history")):
        problems = ft.petri_active_readapt_problems(repo, TRIGGER, [dict(active, **broken)])
        assert len(problems) == 1 and needle in problems[0], problems
    # an active mode-run entry is not a readapt: the ordinary one-running + one-pending queue applies
    run_content = json.dumps(dict(SOURCE_PARAMS, _nonce="w2e4"), separators=(",", ":")) + "\n"
    trigger.write_text(run_content, encoding="utf-8")
    running = dict(active, nonce="w2e4", params_sha256=ft.params_digest(run_content), max_spend=8.6)
    journal.write_text(source_journal + json.dumps(running) + "\n", encoding="utf-8")
    assert ft.petri_active_readapt_problems(repo, TRIGGER, [running]) == []
    assert ft.main(fire + ["--params", json.dumps(dict(ft.PARK_DEFAULTS[TRIGGER], _nonce="p"))]) == 0
    capsys.readouterr()
    assert ft.petri_active_readapt_problems(repo, "advice-eval", [active]) == []
