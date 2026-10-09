#!/usr/bin/env python3
"""Run the 2026-10 logits backfill campaign unattended: plan, fire, wait, verify, resolve, repeat, then park.

Owner decisions, 2026-10-09: fill the exploratory sweep (gemma-4-e2b + qwen3.5-2b-base) and the six original
models' gaps in one chain, with medgemma-1.5-4b-it's priority selection and rest only when asked; republish only
when the owner says so (scripts/publication_hold.py holds every new part); and keep the chain runnable by any
agent, or by hand, with a single command and no Claude session. Every rule that keeps it safe is therefore
enforced here, in scripts/fire_trigger.py, or in the git hooks fire_trigger.py installs - never by a Claude hook.

    python scripts/backfill_chain.py                 # the campaign: sweep, then the original models' gaps
    python scripts/backfill_chain.py --dry-run       # print the plan and change nothing
    python scripts/backfill_chain.py --stop-after 4  # fire at most 4 legs, then drain, park and stop
    python scripts/backfill_chain.py --medgemma15-priority data/selections/<file>.json   # add phase 3
    python scripts/backfill_chain.py --include-medgemma15                                # add phase 4

Each round:
  1. reads ops/trigger_journal.jsonl: the logits-eval lane may hold only this chain's own legs (their notes end
     with CHAIN_TAG) and parks; anything else stops the chain;
  2. asks scripts/backfill_planner.py (campaign_plan) for the next leg, planned from what has landed plus the
     legs already in flight, and fires it through scripts/fire_trigger.py, keeping at most one running and one
     pending run in the lane;
  3. finds the leg's GitHub Actions run (gh), waits for it to finish, and requires conclusion success;
  4. verifies on origin/main that every expected trace_out/<stem>__<model>/batch_summary.part_NN.json landed,
     complete, with exactly the expected indices and model;
  5. fast-forwards main, resolves the journal entry (fire_trigger.py resolve), and commits and pushes the
     journal alone as an ops commit.
When the plan is empty, or --stop-after legs have been fired and have landed, it parks the lane, waits for the
park to land, resolves it, and exits 0. Re-running it resumes from what has landed and what is in flight.

It STOPS (exit 1, a plain-English reason and what to do next, on stdout and in the log) on: any nonzero
fire_trigger.py exit; a run that failed, was cancelled, or did not finish in --max-wait-hours; outputs missing,
partial, or not what was asked; an unexpected active entry in the lane; a dirty working tree (tracked files);
a checkout not on main, or main that cannot be fast-forwarded or rebased onto origin; gh missing or not
logged in; and a planned fire that is not a $0 logits-eval fire.

It never passes --force-evict, --override-budget or --keep-dashboard, never commits ops/dashboard.json, and
passes --ignore-settle only after GitHub Actions shows the previous run terminal and nothing of the workflow
queued on main (the fire-trigger-safe skill, section 4). It never releases anything for publication
(scripts/publication_release.py is the owner's command). Every action is logged to --log (default: a file in
the system temp directory, never committed).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

ENGINE = Path(__file__).resolve().parents[1]
LANE = "logits-eval"
WORKFLOW = "logits_evaluation.yml"
BRANCH = "main"
CHAIN_TAG = " [backfill_chain]"
JOURNAL = Path("ops") / "trigger_journal.jsonl"
FORBIDDEN_FLAGS = ("--force-evict", "--override-budget", "--keep-dashboard")
QUEUED_STATES = ("queued", "pending", "waiting", "requested")
NOTE_RE = re.compile(r"^backfill PREDICTIONS \([^)]*\): (?P<batch>\S+) pairs (?P<where>\S+)/\d+ x (?P<models>\S+)$")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_for_chain", Path(__file__).resolve().parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Stop(Exception):
    """The chain must stop: `reason` says what happened, `todo` what a person should do next."""

    def __init__(self, reason: str, todo: str) -> None:
        super().__init__(reason)
        self.reason, self.todo = reason, todo


def parse_note(note: str) -> tuple[str, list[int], list[str]]:
    """(batch, indices, models) of a planner leg note, with or without CHAIN_TAG. ValueError if not a leg note."""
    m = NOTE_RE.match(note.removesuffix(CHAIN_TAG))
    if not m:
        raise ValueError(f"not a backfill leg note: {note!r}")
    where = m.group("where")
    if "-" in where:
        a, b = (int(x) for x in where.split("-"))
        indices = list(range(a, b + 1))
    else:
        indices = [int(x) for x in where.split(",")]
    return m.group("batch"), indices, m.group("models").split("+")


class Chain:
    """One chain run. Every external effect goes through self.run (argv -> (rc, stdout, stderr)) and self.sleep,
    so the tests can drive it offline."""

    def __init__(self, repo: Path, args: argparse.Namespace, log_path: Path,
                 run: Callable[[list[str]], tuple[int, str, str]] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.repo, self.args, self.log_path = repo, args, log_path
        self._run = run or self._subprocess
        self.sleep, self.now = sleep, now
        self.ft = _load("fire_trigger")
        self.bp = _load("backfill_planner")
        self.bp.ENGINE = repo
        self.fired = 0
        self.selection = (self.bp.load_selection(args.medgemma15_priority)
                          if args.medgemma15_priority else None)

    # ------------------------------------------------------------------ plumbing
    def _subprocess(self, argv: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(argv, cwd=self.repo, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def log(self, msg: str) -> None:
        line = f"{self.now().strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
        print(line, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def run(self, argv: list[str]) -> tuple[int, str, str]:
        self.log("$ " + " ".join(argv))
        rc, out, err = self._run(argv)
        if rc:
            self.log(f"  exit {rc}: {(err or out).strip()[:2000]}")
        return rc, out, err

    def git(self, *argv: str) -> tuple[int, str, str]:
        return self.run(["git", "-C", str(self.repo), *argv])

    def gh(self, *argv: str) -> tuple[int, str, str]:
        return self.run([self.args.gh, *argv])

    def fire_trigger(self, *argv: str) -> None:
        bad = [a for a in argv if a in FORBIDDEN_FLAGS]
        if bad:   # a guard against this file's own future edits, not against the caller
            raise Stop(f"refusing to pass {bad} to fire_trigger.py", "this is a bug in backfill_chain.py; report it")
        rc, out, err = self.run([sys.executable, str(self.repo / "scripts" / "fire_trigger.py"), *argv])
        if rc:
            raise Stop(f"fire_trigger.py {argv[0]} exited {rc}: {(err or out).strip()[:600]}",
                       "read fire_trigger.py's message above. If it says the push was rejected, run "
                       "`python scripts/fire_trigger.py publish`; if it is a queue or settle refusal, wait for the "
                       "lane's runs to finish and rerun this chain. Do not retry with any override flag.")

    # ------------------------------------------------------------------ checks
    def preflight(self) -> None:
        rc, _, _ = self.gh("auth", "status")
        if rc:
            raise Stop("gh is not available or not logged in", "install gh and run `gh auth login`, then rerun")
        self.require_clean()
        rc, branch, _ = self.git("rev-parse", "--abbrev-ref", "HEAD")
        if rc or branch.strip() != BRANCH:
            raise Stop(f"the checkout is on {branch.strip() or '?'}, not {BRANCH}",
                       f"`git switch {BRANCH}` in a clean checkout, then rerun")
        self.sync()

    def require_clean(self, allow: tuple[str, ...] = ()) -> None:
        rc, out, _ = self.git("status", "--porcelain", "--untracked-files=no")
        dirty = [line[3:] for line in out.splitlines() if line.strip() and line[3:] not in allow]
        if rc or dirty:
            raise Stop(f"the working tree has uncommitted changes to tracked files: {dirty}",
                       "commit or restore them (never commit ops/dashboard.json from here), then rerun")

    def sync(self) -> None:
        rc, _, _ = self.git("pull", "--ff-only", "origin", BRANCH)
        if rc:
            raise Stop(f"local {BRANCH} cannot be fast-forwarded to origin/{BRANCH}",
                       f"inspect `git log origin/{BRANCH}..{BRANCH}`; publish or drop local commits, then rerun")

    def journal(self) -> list[dict]:
        return self.ft.load_journal(self.repo / JOURNAL)

    def active(self) -> list[dict]:
        return self.ft.active_entries(self.journal(), LANE, self.now(), self.ft.expire_hours_from_env())

    def classify(self) -> tuple[list[dict], list[dict]]:
        """(this chain's legs, parks) among the lane's active entries; anything else stops the chain."""
        legs, parks = [], []
        for e in self.active():
            note = e.get("note", "")
            if note.endswith(CHAIN_TAG):
                legs.append(e)
            elif note == self.ft.PARK_NOTE:
                parks.append(e)
            else:
                raise Stop(f"the {LANE} lane holds an active entry this chain did not fire: {note[:160]!r}",
                           "let that run land and resolve it (harvest-resolve), or ask the owner; then rerun")
        return legs, parks

    # ------------------------------------------------------------------ GitHub
    def fire_commit(self, entry: dict) -> str:
        """The commit fire_trigger.py made for this journal entry: the oldest commit on origin/main that changed
        the lane's trigger file and whose message names the entry's note, among those that added the entry's
        unique `_nonce` (every chain fire and every park carries one)."""
        nonce = entry.get("nonce")
        if not nonce:
            raise Stop(f"the entry {entry.get('note', '')[:120]!r} carries no nonce, so its run cannot be found",
                       "find its run in the Actions tab, resolve it by hand once terminal, then rerun")
        self.git("fetch", "origin", BRANCH)
        rc, out, _ = self.git("log", f"origin/{BRANCH}", "--format=%H", f"-S{nonce}", "--fixed-strings",
                              f"--grep=Fire {LANE}: {entry.get('note', '')}", "--",
                              f".github/trigger/{LANE}.json")
        shas = out.split()
        if rc or not shas:
            raise Stop(f"cannot find the fire commit of {entry.get('note', '')[:120]!r} on origin/{BRANCH}",
                       "check `git log origin/main` for it; if the fire never reached origin, run "
                       "`python scripts/fire_trigger.py publish`, then rerun")
        return shas[-1]

    def find_run(self, sha: str) -> dict:
        deadline = self.now() + timedelta(minutes=self.args.find_run_minutes)
        while True:
            rc, out, _ = self.gh("run", "list", "--workflow", WORKFLOW, "--branch", BRANCH, "--commit", sha,
                                 "--json", "databaseId,status,conclusion,event")
            if rc:
                raise Stop("gh run list failed", "check gh (`gh auth status`) and the network, then rerun")
            runs = [r for r in json.loads(out or "[]") if r.get("event") == "push"]
            if runs:
                return runs[0]
            if self.now() >= deadline:
                raise Stop(f"no {WORKFLOW} run appeared for commit {sha[:12]}",
                           "open the repository's Actions tab: if the run is missing, the trigger did not fire; "
                           "resolve the entry by hand and rerun")
            self.sleep(self.args.poll_seconds)

    def wait_run(self, run_id: int) -> None:
        deadline = self.now() + timedelta(hours=self.args.max_wait_hours)
        while True:
            rc, out, _ = self.gh("run", "view", str(run_id), "--json", "status,conclusion")
            if rc:
                raise Stop(f"gh run view {run_id} failed", "check gh and the network, then rerun (it resumes)")
            state = json.loads(out)
            if state.get("status") == "completed":
                if state.get("conclusion") != "success":
                    raise Stop(f"run {run_id} concluded {state.get('conclusion')!r}",
                               f"read the run's log (`gh run view {run_id} --log-failed`); fix the cause; resolve "
                               "its journal entry (fire_trigger.py resolve) only after confirming it is terminal; "
                               "then rerun - the planner re-plans whatever did not land")
                return
            if self.now() >= deadline:
                raise Stop(f"run {run_id} has not finished after {self.args.max_wait_hours} h",
                           "check it in the Actions tab; rerun this chain once it has finished (it resumes)")
            self.sleep(self.args.poll_seconds)

    def nothing_queued(self) -> bool:
        rc, out, _ = self.gh("run", "list", "--workflow", WORKFLOW, "--branch", BRANCH, "--limit", "20",
                             "--json", "databaseId,status")
        if rc:
            raise Stop("gh run list failed", "check gh and the network, then rerun")
        return not any(r.get("status") in QUEUED_STATES for r in json.loads(out or "[]"))

    def settle_flags(self) -> list[str]:
        """["--ignore-settle"] when a lane entry was resolved inside the settle window, which this chain does
        only after confirming its run terminal - and only once nothing of the workflow is queued on main."""
        recent = self.ft.recently_resolved(self.journal(), LANE, self.now(), self.ft.settle_minutes_from_env())
        if not recent:
            return []
        deadline = self.now() + timedelta(minutes=self.args.find_run_minutes)
        while not self.nothing_queued():
            if self.now() >= deadline:
                raise Stop(f"a {WORKFLOW} run is still queued on {BRANCH}",
                           "wait for the lane's queue to drain, then rerun")
            self.sleep(self.args.poll_seconds)
        return ["--ignore-settle"]

    # ------------------------------------------------------------------ outputs and journal
    def verify_outputs(self, note: str) -> None:
        batch, indices, models = parse_note(note)
        name = f"batch_summary.part_{indices[0]:02d}.json"
        self.git("fetch", "origin", BRANCH)
        for model in models:
            path = f"trace_out/{batch}__{model}/{name}"
            rc, out, _ = self.git("show", f"origin/{BRANCH}:{path}")
            if rc:
                raise Stop(f"{path} did not land on origin/{BRANCH}",
                           "the run succeeded without committing its output; check its commit step's log, then "
                           "resolve the entry by hand and rerun (the planner re-plans the pairs)")
            try:
                summary = json.loads(out)
            except ValueError:
                raise Stop(f"{path} is not valid JSON", "inspect the file; do not resolve until it is understood")
            got = [r.get("index") for r in summary.get("results", [])]
            problems = []
            if summary.get("graph_model") != model:
                problems.append(f"graph_model {summary.get('graph_model')!r}")
            if summary.get("backend") != "logits":
                problems.append(f"backend {summary.get('backend')!r}")
            if summary.get("completed") is not True:
                problems.append("completed is not true (a partial, crash-flushed part)")
            if got != indices:
                problems.append(f"indices {got[:8]}... ({len(got)}) instead of {indices[:8]}... ({len(indices)})")
            if problems:
                raise Stop(f"{path} landed but is not what was asked: " + "; ".join(problems),
                           "inspect the part; resolve the entry by hand once understood; rerun (the planner "
                           "re-plans any pair not measured)")
        self.log(f"verified {len(models)} part(s) {name} for {batch}: {len(indices)} pairs x {'+'.join(models)}")

    def resolve_oldest(self, entry: dict) -> None:
        oldest = self.active()[0]
        if (oldest.get("fired_utc"), oldest.get("note")) != (entry.get("fired_utc"), entry.get("note")):
            raise Stop("the oldest active entry is not the one that just landed",
                       "resolve entries by hand in landing order (harvest-resolve), then rerun")
        self.fire_trigger("resolve", "--trigger", LANE)
        self.require_clean(allow=(JOURNAL.as_posix(),))
        rc, staged, _ = self.git("status", "--porcelain", "--untracked-files=no")
        if rc or [line[3:] for line in staged.splitlines() if line.strip()] != [JOURNAL.as_posix()]:
            raise Stop("resolving changed something other than the journal", "inspect `git status`; rerun")
        for argv in (["add", JOURNAL.as_posix()],
                     ["commit", "-m", f"ops: resolve {LANE} entry fired {entry.get('fired_utc')} (backfill chain)",
                      "--", JOURNAL.as_posix()]):
            rc, _, _ = self.git(*argv)
            if rc:
                raise Stop(f"git {argv[0]} of the journal failed", "inspect `git status`; rerun")
        self.push()

    def push(self) -> None:
        rc, _, _ = self.git("push", "origin", BRANCH)
        if rc == 0:
            return
        rc, _, _ = self.git("pull", "--rebase", "origin", BRANCH)
        if rc:
            self.git("rebase", "--abort")
            raise Stop(f"origin/{BRANCH} moved and the journal commit does not rebase onto it",
                       "merge ops/trigger_journal.jsonl by hand as an ORDERED UNION (operators handbook), push, "
                       "then rerun")
        rc, _, _ = self.git("push", "origin", BRANCH)
        if rc:
            raise Stop(f"pushing the journal to origin/{BRANCH} failed twice", "check the network and push by hand")

    def harvest(self, entry: dict, verify: bool) -> None:
        """Wait for an in-flight entry's run, verify its outputs (legs), fast-forward, resolve, push."""
        run = self.find_run(self.fire_commit(entry))
        self.log(f"waiting for run {run['databaseId']} ({entry.get('note', '')[:100]})")
        self.wait_run(int(run["databaseId"]))
        if verify:
            self.verify_outputs(entry["note"])
        self.sync()
        self.resolve_oldest(entry)

    # ------------------------------------------------------------------ the loop
    def plan(self, count: int, in_flight: list[dict] = ()) -> list[dict]:
        """The next `count` campaign legs, planned from what has landed in this checkout plus the legs in flight
        (counted as landed, whether or not their outputs have been pulled yet)."""
        cov = self.bp.coverage()
        flying = []
        for e in in_flight:
            batch, indices, models = parse_note(e["note"])
            flying.append({"params": {"models": ",".join(models), "pairs_file": f"data/simulated/{batch}.json",
                                      "indices": ",".join(str(i) for i in indices)}})
        cov = self.bp._as_if_landed(cov, flying)
        blocked: list = []
        legs = self.bp.campaign_plan(cov, count, self.args.include_medgemma15, self.selection, blocked)
        for b, m, name in blocked:
            self.log(f"BLOCKED by an existing part name: {m} on {b} ({name}); the planner skips it")
        return legs

    def check_leg(self, leg: dict) -> None:
        if leg["trigger"] != LANE:
            raise Stop(f"the planner proposed a {leg['trigger']} fire", "this chain fires logits-eval only")
        if self.ft.is_paid_fire(leg["trigger"], leg["params"]):
            raise Stop("the planner proposed a paid fire", "this chain fires $0 legs only")
        try:
            self.ft.validate_params(leg["trigger"], leg["params"])
        except ValueError as exc:
            raise Stop(f"the planned params do not validate: {exc}", "report this planner bug")

    def lane_is_parked(self) -> bool:
        path = self.repo / ".github" / "trigger" / f"{LANE}.json"
        try:
            return self.ft.is_park_params(LANE, json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return False

    def park(self) -> None:
        legs, parks = self.classify()
        for e in parks:
            self.harvest(e, verify=False)
        if self.lane_is_parked():
            self.log("the lane is already parked")
            return
        self.fire_trigger("park", "--trigger", LANE, *self.settle_flags())
        _, parks = self.classify()
        if not parks:
            raise Stop("the park did not journal", "run `python scripts/fire_trigger.py status`; rerun")
        self.harvest(parks[-1], verify=False)
        self.log("parked; the lane rests on its no-op default")

    def dry_run(self) -> int:
        legs = self.plan(self.args.dry_run_legs)
        self.log(f"dry run: the next {len(legs)} leg(s) of the campaign (nothing is fired):")
        for leg in legs:
            self.log("  " + self.bp._fmt_cmd({**leg, "note": leg["note"] + CHAIN_TAG}))
        return 0

    def main(self) -> int:
        if self.args.dry_run:
            return self.dry_run()
        self.preflight()
        while True:
            legs, parks = self.classify()
            for e in parks:   # a park waiting ahead of the legs (e.g. this chain's own, before a resume)
                self.harvest(e, verify=False)
            legs, _ = self.classify()
            for e in legs:
                try:
                    parse_note(e["note"])
                except ValueError:
                    raise Stop(f"an in-flight entry's note does not name its leg: {e['note'][:160]!r}",
                               "let it land, verify it by hand, resolve it (harvest-resolve), then rerun")
            done_firing = self.args.stop_after is not None and self.fired >= self.args.stop_after
            plan = [] if done_firing or len(legs) >= 2 else self.plan(1, legs)
            nxt = plan[0] if plan else None
            if nxt is None:
                if legs:
                    self.harvest(legs[0], verify=True)
                    continue
                break
            self.check_leg(nxt)
            self.require_clean()
            # a fresh _nonce (ignored by CI) so a leg re-planned after a failed run still changes the trigger file
            params = {**nxt["params"], "_nonce": f"backfill-chain-{self.now():%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"}
            self.fire_trigger("fire", "--trigger", LANE, "--params", json.dumps(params),
                              "--note", nxt["note"] + CHAIN_TAG, *self.settle_flags())
            self.fired += 1
            self.log(f"fired leg {self.fired}: {nxt['note']}")
        self.park()
        self.log(f"done: fired {self.fired} leg(s) this run"
                 + (" (--stop-after reached)" if self.args.stop_after is not None and
                    self.fired >= self.args.stop_after else "; the campaign plan is empty"))
        return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(ENGINE), help="engine checkout on main (default: this one)")
    ap.add_argument("--dry-run", action="store_true", help="print the next legs and change nothing")
    ap.add_argument("--dry-run-legs", type=int, default=10, help="legs a dry run prints (default 10)")
    ap.add_argument("--stop-after", type=int, default=None, metavar="N",
                    help="fire at most N legs this run, then let them land, park and stop")
    ap.add_argument("--medgemma15-priority", metavar="FILE", default=None,
                    help="add phase 3: medgemma-1.5-4b-it on this selection (scripts/select_priority_pairs.py)")
    ap.add_argument("--include-medgemma15", action="store_true", help="add phase 4: medgemma-1.5-4b-it's rest")
    ap.add_argument("--gh", default="gh", help="the gh executable (default: gh on PATH)")
    ap.add_argument("--poll-seconds", type=float, default=60.0)
    ap.add_argument("--find-run-minutes", type=float, default=15.0,
                    help="how long to wait for a fire's run to appear, or for a queued run to clear")
    ap.add_argument("--max-wait-hours", type=float, default=6.0, help="the longest a run may take before stopping")
    ap.add_argument("--log", default=None, help="log file (default: the system temp directory; never committed)")
    return ap


def main(argv: list[str] | None = None, run=None, sleep=time.sleep, now=None) -> int:
    args = build_parser().parse_args(argv)
    if args.stop_after is not None and args.stop_after < 0:
        raise SystemExit("--stop-after must be 0 or more")
    log = Path(args.log) if args.log else Path(tempfile.gettempdir()) / (
        f"backfill_chain_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log")
    kwargs = {"now": now} if now else {}
    chain = Chain(Path(args.repo).resolve(), args, log, run=run, sleep=sleep, **kwargs)
    chain.log(f"backfill chain starting; log {log}")
    try:
        return chain.main()
    except Stop as stop:
        chain.log(f"STOPPED: {stop.reason}")
        chain.log(f"NEXT: {stop.todo}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
