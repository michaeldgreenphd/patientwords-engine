"""Experiment run store: resume, reuse, journal, collector, write guards.

Offline, synthetic fixtures only. Executions are counted by wrapping the adapters' ``execute_fixture``; the
assertions are on that count, not only on what the store reports about itself. Interruptions are simulated
(``stop_after``, an exception raised inside an adapter); no process is killed, so these tests do not show what
a power loss leaves on disk.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from scripts.experiments import capabilities, common, planner
from scripts.experiments.adapters import behavior_fixture, readout_exploratory
from scripts.experiments.common import Refusal
from scripts.experiments.store import RunStore

ENGINE = Path(__file__).resolve().parents[1]
FIXTURES = ENGINE / "tests" / "fixtures" / "experiments"
PROTECTED = ("trace_out", "data", "pilot", "ops", "modes", ".github", ".claude", ".githooks", ".git")


@pytest.fixture
def protocol() -> dict:
    return json.loads((FIXTURES / "protocol_synthetic.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> dict:
    return capabilities.load_matrix()


@pytest.fixture
def plan(protocol: dict, matrix: dict) -> dict:
    return planner.build_plan(protocol, matrix)


@pytest.fixture
def executions(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str, int]]:
    """Every real call of an adapter's execute_fixture, as (method, family, variant, replicate)."""
    calls: list[tuple[str, str, str, int]] = []
    for module in (behavior_fixture, readout_exploratory):
        original = module.ADAPTER.execute_fixture

        def counted(task: dict, context: dict, _original: object = original) -> dict:
            spec = task["spec"]
            calls.append((spec["method"]["id"], spec["family_id"], spec["variant"], task["replicate"]))
            return _original(task, context)

        monkeypatch.setattr(module.ADAPTER, "execute_fixture", counted)
    return calls


def run(store: RunStore, plan: dict, protocol: dict, worker: str = "w0", **kwargs: object) -> dict:
    return store.run_fixture(plan, worker, fixtures_dir=kwargs.pop("fixtures_dir", FIXTURES), protocol=protocol,
                             **kwargs)


def tree(root: Path) -> dict[str, str]:
    """Relative path -> SHA-256 of every envelope and payload file under a run directory."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("shards", "payloads") for p in sorted((root / folder).rglob("*.json"))}


def journal_lines(store: RunStore) -> list[str]:
    return store.journal_path.read_text(encoding="utf-8").splitlines()


def code_of(action: object) -> str:
    with pytest.raises(Refusal) as caught:
        action()
    return caught.value.code


# ------------------------------------------------------------------------------------ resume and reuse

def test_interrupted_run_resumes_with_only_the_remaining_tasks(plan: dict, protocol: dict, tmp_path: Path,
                                                               executions: list) -> None:
    store = RunStore(tmp_path / "run")
    first = run(store, plan, protocol, stop_after=2)
    assert (first["executed"], first["reused"], first["stopped_early"], first["remaining_ready"]) == (2, 0, True, 16)
    assert len(executions) == 2
    second = run(store, plan, protocol)
    # 18 ready tasks in the plan: 2 done before the stop, 16 left.
    assert (second["executed"], second["reused"], second["stopped_early"], second["remaining_ready"]) == (16, 2, False, 0)
    assert len(executions) == 18 and len(set(executions)) == 18
    assert set(second["reused_task_ids"]) == set(first["executed_task_ids"])
    assert not set(second["executed_task_ids"]) & set(first["executed_task_ids"])
    events = store.read_journal()
    assert sum(e["event"] == "started" for e in events) == sum(e["event"] == "ended" for e in events) == 18
    assert sum(e["event"] == "reused" for e in events) == 2
    assert store.uncertain_attempts() == []


def test_a_finished_run_is_reused_unchanged(plan: dict, protocol: dict, tmp_path: Path, executions: list) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    before = tree(store.run_dir)
    again = run(store, plan, protocol)
    assert (again["executed"], again["reused"], again["recorded_not_ready"], again["already_recorded"]) == (0, 18, 0, 18)
    assert len(executions) == 18
    assert tree(store.run_dir) == before
    # 18 completed envelopes + 18 state envelopes; payloads are content-addressed, one per completed task.
    assert len(list(store.shards_dir.rglob("*.envelope.json"))) == 36
    assert len(list(store.payloads_dir.glob("*.json"))) == 18


def test_stop_after_counts_executions_only(plan: dict, protocol: dict, tmp_path: Path, executions: list) -> None:
    store = RunStore(tmp_path / "run")
    assert run(store, plan, protocol, stop_after=0)["executed"] == 0 and executions == []
    summary = run(store, plan, protocol, stop_after=3)
    assert summary["executed"] == 3 and len(executions) == 3
    assert code_of(lambda: run(store, plan, protocol, stop_after=-1)) == "stop_after"
    assert code_of(lambda: run(store, plan, protocol, worker="../w0")) == "worker_name"


def test_replicate_one_is_not_satisfied_by_replicate_zero(protocol: dict, matrix: dict, plan: dict, tmp_path: Path,
                                                         executions: list) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    assert len(executions) == 18 and {call[3] for call in executions} == {0}
    two = planner.build_plan(protocol, matrix, replicates=2)
    summary = run(store, two, protocol)
    # Same protocol hash, so the directory is compatible. Replicate 0 is reused; replicate 1 is executed.
    assert (summary["executed"], summary["reused"]) == (18, 18)
    assert len(executions) == 36 and sorted(call[3] for call in executions) == [0] * 18 + [1] * 18
    assembly = store.collect()["assembly"]
    assert assembly["counts"]["planned"] == 72 and assembly["by_state"]["completed"] == 36
    keys = {(row["spec_sha256"], row["replicate"]) for row in assembly["tasks"]}
    assert len(keys) == 72 and len({key[0] for key in keys}) == 36


def test_a_changed_protocol_is_not_reused_and_refuses_the_old_directory(protocol: dict, matrix: dict, plan: dict,
                                                                        tmp_path: Path, executions: list) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    changed = copy.deepcopy(protocol)
    changed["methods"][1]["layers"] = [0]
    changed_plan = planner.build_plan(changed, matrix)
    assert not {t["spec_sha256"] for t in plan["tasks"]} & {t["spec_sha256"] for t in changed_plan["tasks"]}
    assert code_of(lambda: run(store, changed_plan, changed)) == "incompatible_resume"
    assert len(executions) == 18
    fresh = RunStore(tmp_path / "run2")
    summary = run(fresh, changed_plan, changed)
    assert (summary["executed"], summary["reused"]) == (18, 0) and len(executions) == 36
    assert code_of(lambda: run(fresh, changed_plan, protocol)) == "protocol_mismatch"


def test_a_crash_leaves_an_uncertain_attempt_that_is_kept_and_reported(plan: dict, protocol: dict, tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    store = RunStore(tmp_path / "run")
    original = behavior_fixture.ADAPTER.execute_fixture
    calls = []

    def interrupted(task: dict, context: dict) -> dict:
        calls.append(task["task_id"])
        if len(calls) == 2:
            raise KeyboardInterrupt  # not an Exception: the store does not catch it, as with a killed process
        return original(task, context)

    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(store, plan, protocol)
    crashed = calls[1]
    uncertain = store.uncertain_attempts()
    assert [(e["task_id"], e["attempt"]) for e in uncertain] == [(crashed, 1)]
    lines_after_crash = journal_lines(store)
    assert json.loads(lines_after_crash[-1])["event"] == "started"
    collected = store.collect()
    assert [(u["task_id"], u["attempt"], u["a_completed_envelope_exists_for_this_task"])
            for u in collected["assembly"]["uncertain"]] == [(crashed, 1, False)]
    assert collected["assembly"]["complete"] is False
    assert len(collected["metrics"]["runs_without_end"]) == 1

    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", original)
    summary = run(store, plan, protocol)
    assert summary["uncertain_before_run"] == 1 and summary["remaining_ready"] == 0
    # The journal is append-only: the crashed attempt's line is still there, byte for byte.
    assert journal_lines(store)[:len(lines_after_crash)] == lines_after_crash
    retried = common.read_json(next(store.shards_dir.glob(f"w0/{crashed}.r0.a2.envelope.json")))
    assert retried["attempt"] == 2 and retried["status"]["execution"] == "completed"
    assert [(h["attempt"], h["state"]) for h in retried["attempt_history"]] == [(1, "uncertain"), (2, "completed")]
    after = store.collect()["assembly"]
    assert after["complete"] is True and after["by_state"]["completed"] == 18
    assert [(u["task_id"], u["a_completed_envelope_exists_for_this_task"]) for u in after["uncertain"]] == [
        (crashed, True)]


def test_a_torn_journal_line_is_reported_not_dropped(plan: dict, protocol: dict, tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol, stop_after=1)
    with store.journal_path.open("a", encoding="utf-8") as handle:
        handle.write('{"event": "started", "task_id": "0123')
    assert store.collect()["assembly"]["journal_unparseable_lines"] == [len(journal_lines(store))]


def test_a_failed_attempt_is_recorded_and_retried(plan: dict, protocol: dict, tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    store = RunStore(tmp_path / "run")
    original = readout_exploratory.ADAPTER.execute_fixture
    monkeypatch.setattr(readout_exploratory.ADAPTER, "execute_fixture",
                        lambda task, context: (_ for _ in ()).throw(RuntimeError("placeholder failure")))
    first = run(store, plan, protocol)
    assert first["by_state"]["failed"] == 9 and first["by_state"]["completed"] == 9 and first["remaining_ready"] == 9
    failed = next(common.read_json(p) for p in store.envelope_files()
                  if common.read_json(p)["status"]["execution"] == "failed")
    assert failed["status"]["reason"] == "RuntimeError: placeholder failure" and failed["payload"] is None
    assert failed["counts"] == {"requested": 1, "accepted": 1, "completed": 0, "failed": 1, "exclusions": []}
    assert store.collect()["assembly"]["by_state"]["failed"] == 9
    monkeypatch.setattr(readout_exploratory.ADAPTER, "execute_fixture", original)
    second = run(store, plan, protocol)
    assert (second["executed"], second["reused"], second["by_state"]["completed"]) == (9, 9, 9)
    assembly = store.collect()["assembly"]
    assert assembly["by_state"]["completed"] == 18 and assembly["by_state"]["failed"] == 0
    row = next(r for r in assembly["tasks"] if r["method"] == "logit_lens")
    assert [(a["attempt"], a["state"]) for a in row["attempts"]] == [(1, "failed"), (2, "completed")]
    assert row["attempt"] == 2


def altered_fixtures(tmp_path: Path, edit: object) -> Path:
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, target, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    path = target / "behavior_logits.json"
    path.write_text(edit(path.read_text(encoding="utf-8")), encoding="utf-8")
    return target


def test_misaligned_or_non_finite_fixture_rows_end_invalid(plan: dict, protocol: dict, tmp_path: Path) -> None:
    def misalign(text: str) -> str:
        doc = json.loads(text)
        doc["rows"][0]["token_sha256"] = "0" * 64
        doc["rows"][1]["logits"][0] = float("nan")
        return json.dumps(doc)

    store = RunStore(tmp_path / "run")
    summary = run(store, plan, protocol, fixtures_dir=altered_fixtures(tmp_path, misalign))
    assert summary["by_state"]["invalid"] == 2 and summary["by_state"]["completed"] == 16
    invalid = sorted((common.read_json(p) for p in store.envelope_files()
                      if common.read_json(p)["status"]["execution"] == "invalid"),
                     key=lambda e: e["status"]["reason"])
    assert [e["status"]["reason"].split(":")[0] for e in invalid] == ["invalid_logits", "row_misalignment"]
    for doc in invalid:
        assert doc["payload"] is None
        assert doc["counts"] == {"requested": 1, "accepted": 1, "completed": 0, "failed": 0,
                                 "exclusions": [{"reason": "invalid_payload", "n": 1}]}


def test_a_missing_fixture_file_is_unavailable_not_failed(plan: dict, protocol: dict, tmp_path: Path) -> None:
    fixtures = altered_fixtures(tmp_path, lambda text: text)
    (fixtures / "behavior_logits.json").unlink()
    store = RunStore(tmp_path / "run")
    summary = run(store, plan, protocol, fixtures_dir=fixtures)
    # 9 behaviour tasks lose their input; they join the 9 planned-unavailable jpp tasks.
    assert summary["by_state"] == {"not_run": 0, "unsupported": 9, "unavailable": 18, "invalid": 0, "failed": 0,
                                   "completed": 9}
    assert store.collect()["assembly"]["counts"]["ready_completed"] == 9


# --------------------------------------------------------------------------------------------- collector

def test_two_workers_are_assembled_deterministically(plan: dict, protocol: dict, tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol, worker="worker-a", stop_after=5)
    run(store, plan, protocol, worker="worker-b")
    first = store.collect()
    assembly = first["assembly"]
    assert assembly["complete"] is True and assembly["counts"]["planned"] == 36
    assert assembly["by_state"] == {"not_run": 0, "unsupported": 9, "unavailable": 9, "invalid": 0, "failed": 0,
                                    "completed": 18}
    order = [(row["task_id"], row["replicate"]) for row in assembly["tasks"]]
    assert order == sorted(order) and len(order) == 36
    completed = [row for row in assembly["tasks"] if row["execution"] == "completed"]
    assert sorted(row["worker"] for row in completed) == ["worker-a"] * 5 + ["worker-b"] * 13
    second = store.collect()
    assert second["assembly"] == assembly and second["assembly_sha256"] == first["assembly_sha256"]
    assert first["assembly_sha256"] == common.digest(assembly)
    assert first["metrics"]["measured"] is True and "say nothing about a model run" in first["metrics"]["timing_caveat"]
    assert first["metrics"]["executed_attempts"] == 18 and first["metrics"]["reused_events"] == 5
    assert first["metrics"]["missingness"] == {"planned": 36, "missing": 0, "fraction_missing": 0.0}
    assert first["metrics"]["artifact_bytes"]["payloads"] == sum(
        p.stat().st_size for p in store.payloads_dir.glob("*.json"))


def two_full_shards(plan: dict, protocol: dict, tmp_path: Path) -> RunStore:
    """Workers a and b each ran the whole plan without seeing the other, as two machines would."""
    store, other = RunStore(tmp_path / "run"), RunStore(tmp_path / "elsewhere")
    run(store, plan, protocol, worker="worker-a")
    run(other, plan, protocol, worker="worker-b")
    shutil.copytree(other.shards_dir / "worker-b", store.shards_dir / "worker-b")
    for payload in other.payloads_dir.glob("*.json"):
        assert (store.payloads_dir / payload.name).read_bytes() == payload.read_bytes()
    return store


def test_identical_duplicates_are_kept_once(plan: dict, protocol: dict, tmp_path: Path) -> None:
    store = two_full_shards(plan, protocol, tmp_path)
    assembly = store.collect()["assembly"]
    assert assembly["counts"]["with_envelope"] == 36 and len(assembly["tasks"]) == 36
    assert assembly["counts"]["duplicate_identical"] == 36
    assert {row["worker"] for row in assembly["tasks"]} == {"worker-a"}
    for duplicate in assembly["duplicate_identical"]:
        assert duplicate["kept"].startswith("shards/worker-a/")
        assert [p.split("/")[1] for p in duplicate["also"]] == ["worker-b"]
    assert len(list(store.payloads_dir.glob("*.json"))) == 18


def first_completed_b(store: RunStore) -> tuple[Path, dict]:
    for path in sorted((store.shards_dir / "worker-b").glob("*.envelope.json")):
        doc = common.read_json(path)
        if doc["status"]["execution"] == "completed" and doc["method"]["id"] == "behavior_next_token":
            return path, doc
    raise AssertionError("no completed behaviour envelope in worker-b")


def test_conflicting_duplicates_are_refused(plan: dict, protocol: dict, tmp_path: Path) -> None:
    store = two_full_shards(plan, protocol, tmp_path)
    path, doc = first_completed_b(store)
    payload = common.read_json(store.run_dir / doc["payload"]["path"])
    payload["targets"][0]["full_vocab_probability"] = 0.5
    data = common.json_bytes(payload)
    sha = hashlib.sha256(data).hexdigest()
    (store.payloads_dir / f"{sha}.json").write_bytes(data)
    doc["payload"].update({"sha256": sha, "path": f"payloads/{sha}.json"})
    common.atomic_write_json(path, doc)
    with pytest.raises(Refusal) as caught:
        store.collect()
    assert caught.value.code == "duplicate_conflict" and doc["task_id"] in str(caught.value)


def test_overlapping_shards_that_disagree_are_refused(plan: dict, protocol: dict, tmp_path: Path) -> None:
    store = two_full_shards(plan, protocol, tmp_path)
    path, doc = first_completed_b(store)
    doc["status"] = {"execution": "failed", "reason": "placeholder disagreement"}
    doc["attempt_history"][-1].update({"state": "failed", "reason": "placeholder disagreement"})
    doc["payload"] = None
    doc["counts"].update({"completed": 0, "failed": 1})
    doc["resources"]["storage_bytes"] = None
    common.atomic_write_json(path, doc)
    with pytest.raises(Refusal) as caught:
        store.collect()
    assert caught.value.code == "shard_disagreement"
    assert "worker-a" in str(caught.value) and "worker-b" in str(caught.value)


def test_missing_tasks_are_listed_and_counted_as_not_run(plan: dict, protocol: dict, tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol, stop_after=3)
    collected = store.collect()
    assembly = collected["assembly"]
    with_envelope = {(row["task_id"], row["replicate"]) for row in assembly["tasks"]}
    planned = {(t["task_id"], t["replicate"]) for t in plan["tasks"]}
    missing = {(m["task_id"], m["replicate"]) for m in assembly["missing"]}
    assert missing == planned - with_envelope and missing
    assert assembly["complete"] is False and assembly["by_state"]["not_run"] == len(missing)
    assert assembly["by_state"]["completed"] == 3
    assert collected["metrics"]["missingness"]["fraction_missing"] == pytest.approx(len(missing) / 36)
    assert sum(assembly["by_state"].values()) == 36


def test_altered_payload_bytes_are_detected(plan: dict, protocol: dict, tmp_path: Path, executions: list) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    store.collect()
    victim = sorted(store.payloads_dir.glob("*.json"))[0]
    victim.write_bytes(victim.read_bytes() + b" ")
    with pytest.raises(Refusal) as caught:
        store.collect()
    assert caught.value.code == "payload_hash" and victim.name in str(caught.value)
    assert code_of(store.read_collected) == "payload_hash"
    # A resume does not trust the altered file and does not overwrite it: the task is executed again and the
    # attempt ends failed, because the content-addressed name is already held by other bytes.
    summary = run(store, plan, protocol)
    assert (summary["executed"], summary["reused"], summary["by_state"]["failed"]) == (1, 17, 1)
    assert len(executions) == 19


def test_shards_of_another_protocol_and_misnamed_shards_are_refused(protocol: dict, matrix: dict, plan: dict,
                                                                   tmp_path: Path) -> None:
    store, other = RunStore(tmp_path / "run"), RunStore(tmp_path / "other")
    run(store, plan, protocol)
    changed = copy.deepcopy(protocol)
    changed["seed"] = 8
    run(other, planner.build_plan(changed, matrix), changed, worker="worker-x")
    shutil.copytree(other.shards_dir / "worker-x", store.shards_dir / "worker-x")
    shutil.copytree(other.payloads_dir, store.payloads_dir, dirs_exist_ok=True)
    assert code_of(store.collect) == "incompatible_shard"
    shutil.rmtree(store.shards_dir / "worker-x")
    envelope_file = store.envelope_files()[0]
    envelope_file.rename(envelope_file.with_name("renamed.r0.a1.envelope.json"))
    assert code_of(store.collect) == "shard_name"


def test_collected_json_must_match_the_shards_on_disk(plan: dict, protocol: dict, tmp_path: Path) -> None:
    store = RunStore(tmp_path / "run")
    assert code_of(store.collect) == "no_plan"
    run(store, plan, protocol, stop_after=4)
    assert code_of(store.read_collected) == "not_collected"
    store.collect()
    assert store.read_collected()["assembly"]["by_state"]["completed"] == 4
    run(store, plan, protocol)
    assert code_of(store.read_collected) == "stale_collected"


# ------------------------------------------------------------------------------------------ write guards

@pytest.mark.parametrize("root", PROTECTED)
def test_writers_refuse_protected_roots(root: str, plan: dict, tmp_path: Path) -> None:
    target = tmp_path / root / "experiments" / "run"
    assert common.protected_root(target) == root
    assert code_of(lambda: RunStore(target)) == "protected_root"
    assert code_of(lambda: RunStore(target, allow_roots=[tmp_path])) == "protected_root"
    assert code_of(lambda: common.write_json(target / "plan.json", plan)) == "protected_root"
    assert code_of(lambda: common.write_json(target / "plan.json", plan, [tmp_path])) == "protected_root"
    assert not (tmp_path / root).exists()


def test_a_symlink_into_a_protected_root_is_refused(tmp_path: Path) -> None:
    (tmp_path / "trace_out").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "trace_out", target_is_directory=True)
    assert code_of(lambda: RunStore(tmp_path / "link" / "run")) == "protected_root"


def test_writers_refuse_a_git_checkout_unless_a_root_is_allowed(plan: dict, protocol: dict, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    inside = checkout / "experiment_runs" / "run"
    assert code_of(lambda: RunStore(inside)) == "git_checkout"
    assert code_of(lambda: common.write_json(checkout / "plan.json", plan)) == "git_checkout"
    assert code_of(lambda: RunStore(inside, allow_roots=[tmp_path / "unrelated"])) == "git_checkout"
    assert not (checkout / "experiment_runs").exists()
    store = RunStore(inside, allow_roots=[checkout / "experiment_runs"])
    assert run(store, plan, protocol, stop_after=1)["executed"] == 1
    # --allow-root lifts the checkout rule only. A protected root inside the allowed directory stays refused.
    assert code_of(lambda: RunStore(checkout / "data" / "run", allow_roots=[checkout])) == "protected_root"


def test_the_engine_checkout_itself_is_refused() -> None:
    assert code_of(lambda: RunStore(ENGINE / "experiment_runs" / "run")) == "git_checkout"
    assert code_of(lambda: RunStore(ENGINE / "trace_out" / "run", allow_roots=[ENGINE])) == "protected_root"
    assert code_of(lambda: common.write_json(ENGINE / "tests" / "fixtures" / "experiments" / "x.json", {})) == \
        "git_checkout"
    assert not (ENGINE / "experiment_runs").exists()


def test_writes_are_atomic_and_leave_no_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "out" / "doc.json"
    common.atomic_write_json(target, {"b": 1, "a": [1, 2]})
    assert target.read_bytes() == b'{\n  "a": [\n    1,\n    2\n  ],\n  "b": 1\n}\n'
    common.atomic_write_json(target, {"a": 2})
    assert json.loads(target.read_text()) == {"a": 2}
    assert [p.name for p in target.parent.iterdir()] == ["doc.json"]
    with pytest.raises(ValueError):
        common.atomic_write_json(target, {"a": float("nan")})
    assert json.loads(target.read_text()) == {"a": 2} and [p.name for p in target.parent.iterdir()] == ["doc.json"]
