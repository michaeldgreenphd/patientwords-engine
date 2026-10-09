"""scripts/backfill_chain.py, offline: gh, git and the CI runs are faked; fire_trigger.py is the real script run
with --no-git against a throwaway repo, so its queue, settle and key guards are the real ones.

The fake world lands a fired leg's parts the moment it is fired (as a finished CI run would) unless a test says
otherwise. Every stop rule, a resume, the 1-running + 1-pending discipline and the closing park are exercised.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_chain_test", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chain_mod = _load("backfill_chain")
ft = _load("fire_trigger")
bp = _load("backfill_planner")

LANE_FILE = Path(".github") / "trigger" / "logits-eval.json"
ORIGINALS = [m for m in bp.MODELS if m not in bp.EXPLORATORY]


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _part(model: str, indices, completed: bool = True) -> dict:
    return {"graph_model": model, "backend": "logits", "completed": completed,
            "results": [{"index": i} for i in indices]}


@pytest.fixture
def repo(tmp_path):
    """Two batches every original model has measured in full, so the campaign is the sweep: two legs."""
    root = tmp_path / "engine"
    for stem, n in (("pairs_20990101T000000Z", 3), ("pairs_20990102T000000Z", 2)):
        _write(root / "data" / "simulated" / f"{stem}.json", [{"top_prompt": "x", "bottom_prompt": "y"}] * n)
        for m in ORIGINALS:
            _write(root / "trace_out" / f"{stem}__{m}" / "batch_summary.part_01.json", _part(m, range(1, n + 1)))
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "stub.yml").write_text(
        f'on:\n  push:\n    paths:\n      - "{LANE_FILE.as_posix()}"\n', encoding="utf-8")
    _write(root / LANE_FILE, {**ft.PARK_DEFAULTS["logits-eval"], "_parked": "true", "_nonce": "start"})
    (root / "ops").mkdir(exist_ok=True)
    (root / "ops" / "trigger_journal.jsonl").write_text("", encoding="utf-8")
    return root


class World:
    """Fakes gh, git and CI for one engine root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[list[str]] = []
        self.commits: list[tuple[str, str, str]] = []   # (sha, journal nonce, message)
        self.runs: dict[str, dict] = {}
        self.conclusion = "success"
        self.land = True
        self.partial = False
        self.gh_ok = True
        self.dirty = ""
        self.ff_ok = True
        self.queued = 0          # gh reports this many polls with a queued run
        self.journal_dirty = False
        self.max_active = 0

    def _fire_trigger(self, argv: list[str]) -> tuple[int, str, str]:
        sub = argv[2]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = ft.main(argv[2:] + ["--repo", str(self.root)] + (["--no-git"] if sub in ("fire", "park") else []))
        if rc == 0 and sub in ("fire", "park"):
            entries = ft.load_journal(self.root / "ops" / "trigger_journal.jsonl")
            note = entries[-1]["note"]
            sha = f"{len(self.commits) + 1:040x}"
            self.commits.append((sha, entries[-1]["nonce"], f"Fire logits-eval: {note}"))
            self.runs[sha] = {"databaseId": len(self.commits), "status": "completed",
                              "conclusion": self.conclusion, "event": "push"}
            if sub == "fire" and self.land:
                params = json.loads(argv[argv.index("--params") + 1])
                batch = Path(params["pairs_file"]).stem
                idx = ([int(i) for i in params["indices"].split(",")] if params.get("indices") else
                       list(range(int(params["offset"]) + 1, int(params["offset"]) + int(params["limit"]) + 1)))
                for m in params["models"].split(","):
                    got = idx[:-1] if self.partial else idx
                    _write(self.root / "trace_out" / f"{batch}__{m}" / f"batch_summary.part_{idx[0]:02d}.json",
                           _part(m, got, completed=not self.partial))
            active = ft.active_entries(entries, "logits-eval", datetime.now(timezone.utc), 8)
            self.max_active = max(self.max_active, len(active))
        if rc == 0 and sub == "resolve":
            self.journal_dirty = True
        return rc, out.getvalue(), ""

    def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        self.calls.append(argv)
        if argv[0] == sys.executable:
            return self._fire_trigger(argv)
        if argv[0] == "gh":
            if not self.gh_ok:
                return 127, "", "gh: command not found"
            if argv[1:3] == ["auth", "status"]:
                return 0, "", ""
            if argv[1:3] == ["run", "list"] and "--commit" in argv:
                sha = argv[argv.index("--commit") + 1]
                return 0, json.dumps([self.runs[sha]] if sha in self.runs else []), ""
            if argv[1:3] == ["run", "list"]:
                if self.queued:
                    self.queued -= 1
                    return 0, json.dumps([{"databaseId": 99, "status": "queued"}]), ""
                return 0, "[]", ""
            if argv[1:3] == ["run", "view"]:
                run = next(r for r in self.runs.values() if str(r["databaseId"]) == argv[3])
                return 0, json.dumps({"status": run["status"], "conclusion": run["conclusion"]}), ""
        if argv[0] == "git":
            sub = argv[3:]
            if sub[0] == "status":
                lines = [self.dirty] if self.dirty else []
                if self.journal_dirty:
                    lines.append(" M ops/trigger_journal.jsonl")
                return 0, "\n".join(lines) + ("\n" if lines else ""), ""
            if sub[0] == "rev-parse":
                return 0, "main\n", ""
            if sub[:2] == ["pull", "--ff-only"]:
                return (0, "", "") if self.ff_ok else (1, "", "fatal: Not possible to fast-forward")
            if sub[0] == "log":
                needle = next(a for a in sub if a.startswith("--grep="))[len("--grep="):]
                nonce = next(a for a in sub if a.startswith("-S"))[2:]
                hits = [sha for sha, n, msg in self.commits if needle in msg and n == nonce]
                return 0, "".join(f"{sha}\n" for sha in reversed(hits)), ""   # git log lists newest first
            if sub[0] == "show":
                path = self.root / sub[1].split(":", 1)[1]
                return (0, path.read_text(encoding="utf-8"), "") if path.exists() else (128, "", "no such path")
            if sub[0] == "commit":
                self.journal_dirty = False
            return 0, "", ""
        raise AssertionError(f"unexpected command {argv}")


def _run(repo: Path, world: World, *extra: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = chain_mod.main(["--repo", str(repo), "--log", str(repo.parent / "chain.log"), "--poll-seconds", "0",
                             *extra], run=world, sleep=lambda s: None)
    return rc, out.getvalue()


def _journal(repo: Path) -> list[dict]:
    return ft.load_journal(repo / "ops" / "trigger_journal.jsonl")


def test_the_chain_fires_the_sweep_keeps_one_pending_verifies_resolves_and_parks(repo):
    world = World(repo)
    rc, out = _run(repo, world)
    assert rc == 0, out
    entries = _journal(repo)
    notes = [e["note"] for e in entries]
    assert len(notes) == 3 and notes[2] == ft.PARK_NOTE
    assert all(n.endswith(chain_mod.CHAIN_TAG) and "gemma-4-e2b+qwen3.5-2b-base" in n for n in notes[:2])
    assert all(e["resolved"] for e in entries)                          # legs and park all harvested
    assert world.max_active == 2                                        # one running + one pending, never three
    assert ft.is_park_params("logits-eval", json.loads((repo / LANE_FILE).read_text()))
    fires = [c for c in world.calls if c[0] == sys.executable]
    assert not any(flag in c for c in fires for flag in chain_mod.FORBIDDEN_FLAGS)
    commits = [c for c in world.calls if c[0] == "git" and c[3] == "commit"]
    assert commits and all(c[-1] == "ops/trigger_journal.jsonl" for c in commits)   # the journal alone
    assert "done: fired 2 leg(s)" in out and (repo.parent / "chain.log").read_text().count("$ ") > 10


def test_ignore_settle_only_after_github_shows_nothing_queued(repo):
    world = World(repo)
    world.queued = 2
    rc, out = _run(repo, world)
    assert rc == 0, out
    settles = [c for c in world.calls if c[0] == sys.executable and "--ignore-settle" in c]
    assert settles                                                      # the fires after a resolve needed it
    first = world.calls.index(settles[0])
    queue_checks = [i for i, c in enumerate(world.calls)
                    if c[0] == "gh" and c[1:3] == ["run", "list"] and "--commit" not in c]
    assert len([i for i in queue_checks if i < first]) >= 3           # it waited out the queued run first


def test_stop_after_fires_that_many_then_drains_and_parks(repo):
    world = World(repo)
    rc, out = _run(repo, world, "--stop-after", "1")
    assert rc == 0, out
    notes = [e["note"] for e in _journal(repo)]
    assert len(notes) == 2 and notes[1] == ft.PARK_NOTE and "--stop-after reached" in out


def test_rerunning_resumes_from_what_landed(repo):
    world = World(repo)
    assert _run(repo, world, "--stop-after", "1")[0] == 0
    rc, out = _run(repo, world)
    assert rc == 0, out
    legs = [e["note"] for e in _journal(repo) if e["note"].endswith(chain_mod.CHAIN_TAG)]
    assert len(legs) == 2 and legs[0] != legs[1]                        # the second run fired the other batch
    assert "pairs_20990102T000000Z" in legs[1]
    assert _run(repo, world)[0] == 0                                    # nothing left: parked already, no fire
    assert len([e for e in _journal(repo) if e["note"].endswith(chain_mod.CHAIN_TAG)]) == 2


def test_resume_harvests_a_leg_left_in_flight(repo):
    world = World(repo)
    # an earlier chain fired a leg and died before harvesting it
    leg = bp.campaign_plan(_cov(repo), 1)[0]
    world._fire_trigger([sys.executable, "fire_trigger.py", "fire", "--trigger", "logits-eval", "--params",
                         json.dumps({**leg["params"], "_nonce": "earlier-" + leg["note"][-12:]}), "--note",
                         leg["note"] + chain_mod.CHAIN_TAG])
    rc, out = _run(repo, world)
    assert rc == 0, out
    legs = [e for e in _journal(repo) if e["note"].endswith(chain_mod.CHAIN_TAG)]
    assert len(legs) == 2 and all(e["resolved"] for e in legs)


def _cov(repo: Path) -> dict:
    bp.ENGINE = repo
    return bp.coverage()


@pytest.mark.parametrize("setup,needle", [
    (lambda w, r: setattr(w, "gh_ok", False), "gh is not available"),
    (lambda w, r: setattr(w, "dirty", " M scripts/x.py"), "uncommitted changes"),
    (lambda w, r: setattr(w, "ff_ok", False), "cannot be fast-forwarded"),
    (lambda w, r: setattr(w, "conclusion", "failure"), "concluded 'failure'"),
    (lambda w, r: setattr(w, "conclusion", "cancelled"), "concluded 'cancelled'"),
    (lambda w, r: setattr(w, "land", False), "did not land"),
    (lambda w, r: setattr(w, "partial", True), "not what was asked"),
])
def test_every_stop_rule_exits_nonzero_with_a_reason_and_a_next_step(repo, setup, needle):
    world = World(repo)
    setup(world, repo)
    rc, out = _run(repo, world)
    assert rc == 1
    assert "STOPPED: " in out and needle in out and "NEXT: " in out


def test_an_unexpected_active_entry_stops_the_chain(repo):
    world = World(repo)
    world._fire_trigger([sys.executable, "fire_trigger.py", "fire", "--trigger", "logits-eval", "--params",
                         json.dumps({**ft.PARK_DEFAULTS["logits-eval"], "limit": "1", "_nonce": "someone"}),
                         "--note", "someone else's fire"])
    rc, out = _run(repo, world)
    assert rc == 1 and "did not fire" in out


def test_a_nonzero_fire_trigger_exit_stops_the_chain(repo):
    world = World(repo)
    # two foreign-looking but chain-tagged legs already fill the lane, so a third fire is refused by fire_trigger
    plan = bp.campaign_plan(_cov(repo), 2)
    for leg in plan:
        world._fire_trigger([sys.executable, "fire_trigger.py", "fire", "--trigger", "logits-eval", "--params",
                             json.dumps({**leg["params"], "_nonce": "earlier-" + leg["note"][-12:]}), "--note",
                         leg["note"] + chain_mod.CHAIN_TAG])
    chain = chain_mod.Chain(repo, chain_mod.build_parser().parse_args(["--repo", str(repo)]),
                            repo.parent / "c.log", run=world, sleep=lambda s: None)
    with pytest.raises(chain_mod.Stop, match="fire_trigger.py fire exited 2"):
        chain.fire_trigger("fire", "--trigger", "logits-eval", "--params", json.dumps(plan[0]["params"]),
                           "--note", "third")


def test_forbidden_flags_and_non_logits_or_paid_fires_are_refused(repo):
    chain = chain_mod.Chain(repo, chain_mod.build_parser().parse_args(["--repo", str(repo)]),
                            repo.parent / "c.log", run=World(repo), sleep=lambda s: None)
    for flag in chain_mod.FORBIDDEN_FLAGS:
        with pytest.raises(chain_mod.Stop, match="refusing to pass"):
            chain.fire_trigger("fire", flag)
    with pytest.raises(chain_mod.Stop, match="proposed a circuit-trace fire"):
        chain.check_leg({"trigger": "circuit-trace", "params": {}})
    src = (ROOT / "scripts" / "backfill_chain.py").read_text(encoding="utf-8")
    assert "publication_release" not in src.split('"""', 2)[2]          # it never releases anything


def test_dry_run_prints_the_plan_and_changes_nothing(repo):
    world = World(repo)
    rc, out = _run(repo, world, "--dry-run")
    assert rc == 0 and "dry run" in out and "--trigger logits-eval" in out
    assert _journal(repo) == [] and not any(c[0] in ("gh", sys.executable) for c in world.calls)


def test_parse_note_round_trips_the_planners_legs(repo):
    for leg in bp.campaign_plan(_cov(repo), 5):
        batch, idx, models = chain_mod.parse_note(leg["note"] + chain_mod.CHAIN_TAG)
        assert (batch, idx, ",".join(models)) == (bp.leg_batch(leg), bp.leg_indices(leg), leg["params"]["models"])
    assert chain_mod.parse_note("backfill PREDICTIONS (x): pairs_A pairs 4,9/12 x m1") == ("pairs_A", [4, 9], ["m1"])
    with pytest.raises(ValueError):
        chain_mod.parse_note("PARK (resting-state rule)")


def test_after_a_failed_run_is_resolved_by_hand_a_rerun_fires_the_leg_again(repo):
    world = World(repo)
    world.conclusion = "failure"
    world.land = False
    assert _run(repo, world)[0] == 1
    with contextlib.redirect_stdout(io.StringIO()):
        assert ft.main(["resolve", "--trigger", "logits-eval", "--all", "--repo", str(repo)]) == 0
    world.conclusion, world.land, world.journal_dirty = "success", True, False
    rc, out = _run(repo, world)
    assert rc == 0, out
    notes = [e["note"] for e in _journal(repo) if e["note"].endswith(chain_mod.CHAIN_TAG)]
    assert len(set(notes)) == 2 and len(notes) == 4                    # the same two legs, fired again
