"""Run the reserved Haiku 5.5 pass as ordinary, separately verified re-grades.

The original judge's manifest and rows remain unchanged. Reusing the rejudge
format makes these exploratory rows readable by existing secondary analyses.
A small status record accounts for skipped/no-call passes; only per-source
*.report.json files enter the spend ledger.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Any

from scripts.fire_trigger import fire_commitment, fire_lane, secondary_judge_reservation

from . import rejudge
from .framework import load_json, write_json as _write_json
from .manifest import verify_chain
from .reconcile import read_journal


def default_client(spec: str, plans: list) -> Any:
    """Disable unmetered SDK retries; the existing outer attempt gate accounts for every retry."""
    from .judge_runner import RegistryJudge

    return RegistryJudge(spec, sdk_max_retries=0)


def write_json(path: Path, value: dict) -> None:
    """Atomically checkpoint this fire without exposing a partial JSON record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    _write_json(temporary, value)
    temporary.replace(path)


def status_path(root: Path, workflow_id: str) -> Path:
    """A fire-specific status filename; these records are never cost sidecars."""
    if not workflow_id.isascii() or not workflow_id.isdigit():
        raise ValueError("secondary_invalid_workflow_id: ASCII digits required")
    return root / f"fire_{workflow_id}.json"


def require_reservation(params: dict, reservation: dict, journal: list[dict], workflow_id: str) -> None:
    """Refuse local calls, retries, and an absent/mismatched single-fire reservation."""
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "push"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1" or os.environ.get("GITHUB_RUN_ID") != workflow_id):
        raise ValueError("secondary_ci_only: first-attempt push-to-run CI required")
    nonce = params.get("_nonce")
    matches = [e for e in journal if e.get("trigger") == "petri-audit" and e.get("nonce") == nonce]
    commitment, problem = fire_commitment(params)
    if (not isinstance(nonce, str) or not nonce or len(matches) != 1 or problem
            or matches[0].get("evicted") or matches[0].get("resolved")
            or matches[0].get("lane") != fire_lane("petri-audit", params)
            or matches[0].get("secondary_judge") != reservation
            or matches[0].get("max_spend") != commitment):
        raise ValueError("secondary_unreserved: nonce must bind the full, un-evicted dual-judge reservation")


def finalize(root: Path, workflow_id: str, scratch: Path) -> None:
    """Use the existing rejudge imputation for any call interrupted without its sidecar."""
    path = status_path(root, workflow_id)
    if not path.exists():
        return
    state = load_json(path)
    plan_path = scratch / "plan.json"
    if state["status"] == "running" and plan_path.exists():
        plan = load_json(plan_path)
        rejudge.impute_missing_reports(plan, scratch / "started")
        state.update(status="aborted", reason="secondary_process_interrupted")
        write_json(path, state)


def verify(root: Path, workflow_id: str, runs_dir: Path, scratch: Path) -> list[Path]:
    """Verify and list only completed re-grades and this pass's sidecars for staging."""
    scratch.mkdir(parents=True, exist_ok=True)
    plan_path = scratch / "plan.json"
    staged: list[Path] = []
    path = status_path(root, workflow_id)
    if path.exists():
        staged.append(path)
    if plan_path.exists():
        plan = load_json(plan_path)
        directories, sidecars = rejudge.fire_outputs(plan)
        ok, message = verify_chain(runs_dir)
        if not ok:
            raise ValueError(f"secondary_source_chain_invalid: {message}")
        for directory in directories:
            problems = rejudge.verify_output(directory, runs_dir)
            if problems:
                raise ValueError("secondary_output_invalid: " + "; ".join(problems))
        staged += directories + [p for p in sidecars if p.parent not in directories]
        for directory in directories:
            destination = scratch / "exports" / directory.parent.name / directory.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(directory, destination, dirs_exist_ok=True)
        write_json(scratch / "outputs.json", {"directories": [str(p) for p in directories],
                                             "sidecars": [str(p) for p in sidecars]})
    (scratch / "stage.txt").write_text("".join(f"{p}\n" for p in staged), encoding="utf-8")
    return staged


def execute(params: dict, *, source_runs: list[str], root: Path, runs_dir: Path, scratch: Path,
            workflow_id: str, primary_status: str, journal: list[dict],
            client_factory: Any = default_client) -> dict:
    """Apply the existing rejudge planner/executor using the second pass's reserved ceiling."""
    reservation = secondary_judge_reservation(params)
    require_reservation(params, reservation, journal, workflow_id)
    path = status_path(root, workflow_id)
    if path.exists():
        raise ValueError("secondary_already_started: one workflow attempt cannot spend twice")
    scratch.mkdir(parents=True, exist_ok=True)
    state = {"journal_nonce": params["_nonce"], "workflow_run_id": workflow_id,
             "judge_model": reservation["judge_model"], "reservation": reservation,
             "source_runs": source_runs, "status": "not_started", "reason": "primary_pass_failed",
             "transport_retry_policy": "no_sdk_retries; outer_attempts_metered"}
    write_json(path, state)
    if not reservation["max_spend_usd"] or primary_status != "success":
        state["reason"] = reservation.get("reason", "primary_pass_failed")
        write_json(path, state)
        return state
    try:
        pending = []
        reused = []
        for stem in source_runs:
            destination = rejudge.output_dir(runs_dir.parent / "rejudge", reservation["judge_model"], stem)
            source = rejudge.source_record(runs_dir, stem)
            if rejudge.same_judge(source["judge_of_record"]["judge_model"], reservation["judge_model"]):
                reused.append({"run_stem": stem, "reason": "source_judge_is_secondary", "source": source})
            elif (destination / rejudge.MANIFEST_NAME).exists():
                problems = rejudge.verify_output(destination, runs_dir)
                if problems:
                    raise ValueError("secondary_existing_output_invalid: " + "; ".join(problems))
                reused.append({"run_stem": stem, "reason": "verified_existing_regrade", "path": str(destination)})
            else:
                pending.append(stem)
        state["reused_sources"] = reused
        if not pending:
            state.update(status="not_started", reason="already_judged")
            write_json(path, state)
            return state
        second_params = {**params, "mode": "rejudge", "source_runs": pending,
                         "judge_model": reservation["judge_model"],
                         "judge_max_spend": reservation["max_spend_usd"]}
        plan = rejudge.make_plan(params=second_params, runs_dir=runs_dir,
                                rejudge_root=runs_dir.parent / "rejudge", journal_entries=journal,
                                workflow_run_id=workflow_id, workflow_run_attempt="1", commit=os.environ["GITHUB_SHA"],
                                instrument=params.get("instrument") or "current")
        plan["judge_role"] = "secondary"
        write_json(scratch / "plan.json", plan)
        problem = rejudge.judge_key_problem(plan["judge_model"])
        if problem:
            raise ValueError(problem)
        state.update(status="running", reason=None)
        write_json(path, state)
        outcome = rejudge.execute(plan, started_dir=scratch / "started", client_factory=client_factory)
        incomplete = any(item["status"] != "complete" for item in outcome["results"])
        state.update(status="aborted" if outcome["aborted"] else "truncated" if incomplete else "complete", outcome=outcome)
        write_json(path, state)
        verify(root, workflow_id, runs_dir, scratch)
        if incomplete:
            raise ValueError("secondary_judge_incomplete: completed re-grades and all costs retained")
    except Exception as exc:
        finalize(root, workflow_id, scratch)
        state = load_json(path)
        state["reason"] = "secondary_failed:" + type(exc).__name__
        write_json(path, state)
        raise
    return state


def main() -> None:
    """The CI entry point; finalization and verification make no provider call."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "finalize", "verify"))
    parser.add_argument("--params-file")
    parser.add_argument("--source-runs", nargs="*")
    parser.add_argument("--root", type=Path, default=Path("data/petri/secondary"))
    parser.add_argument("--runs-dir", type=Path, default=Path("data/petri/runs"))
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--journal", type=Path, default=Path("ops/trigger_journal.jsonl"))
    parser.add_argument("--workflow-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--primary-status", default="success")
    args = parser.parse_args()
    if args.command == "finalize":
        finalize(args.root, args.workflow_id, args.scratch)
    elif args.command == "verify":
        verify(args.root, args.workflow_id, args.runs_dir, args.scratch)
    else:
        params = load_json(args.params_file)
        stems = args.source_runs or rejudge.parse_source_runs(params.get("source_runs"))
        execute(params, source_runs=stems, root=args.root, runs_dir=args.runs_dir, scratch=args.scratch,
                workflow_id=args.workflow_id, primary_status=args.primary_status, journal=read_journal(args.journal))


if __name__ == "__main__":
    main()
