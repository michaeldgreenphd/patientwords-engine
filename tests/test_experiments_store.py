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

from scripts.experiments import bundle as bundle_module
from scripts.experiments import capabilities, cli, common, compare, envelope, planner
from scripts.experiments import store as store_module
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


def test_overlapping_shards_that_disagree_are_listed_and_the_completed_result_is_kept(plan: dict, protocol: dict,
                                                                                    tmp_path: Path) -> None:
    # Owner decision 2026-11-10: a differing outcome of one attempt number in two shards no longer refuses
    # (it made the directory uncollectable for good). It is listed; two completed payloads still refuse.
    store = two_full_shards(plan, protocol, tmp_path)
    path, doc = first_completed_b(store)
    doc["status"] = {"execution": "failed", "reason": "placeholder disagreement"}
    doc["attempt_history"][-1].update({"state": "failed", "reason": "placeholder disagreement"})
    doc["payload"] = None
    doc["counts"].update({"completed": 0, "failed": 1})
    doc["resources"]["storage_bytes"] = None
    common.atomic_write_json(path, doc)
    assembly = store.collect()["assembly"]
    differing, = assembly["attempt_outcomes_differ"]
    assert (differing["task_id"], differing["attempt"]) == (doc["task_id"], 1)
    assert [(o["worker"], o["state"]) for o in differing["outcomes"]] == [("worker-a", "completed"),
                                                                           ("worker-b", "failed")]
    row = next(r for r in assembly["tasks"] if r["task_id"] == doc["task_id"])
    assert (row["execution"], row["worker"]) == ("completed", "worker-a")
    assert assembly["by_state"]["completed"] == 18 and assembly["counts"]["attempt_outcomes_differ"] == 1
    # The failed envelope is not counted as an identical duplicate of the completed one.
    assert doc["task_id"] not in {d["task_id"] for d in assembly["duplicate_identical"]}


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


# --------------------------------------------------------------------- findings of the 2026-11-10 review

def copy_fixtures(tmp_path: Path, name: str = "fixtures") -> Path:
    target = tmp_path / name
    shutil.copytree(FIXTURES, target, ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    return target


def swap_two_weights(fixtures: Path) -> None:
    """Exchange the logits of the first two fixture rows. Still a valid synthetic fixture; other numbers."""
    path = fixtures / "behavior_logits.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["rows"][0]["logits"], doc["rows"][1]["logits"] = doc["rows"][1]["logits"], doc["rows"][0]["logits"]
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_a_changed_fixture_file_is_executed_again_not_served_the_old_payload(plan: dict, protocol: dict,
                                                                            tmp_path: Path, executions: list) -> None:
    # Regression: the reuse check read only the old payload's own hash, so a changed fixture gave reused 18.
    fixtures = copy_fixtures(tmp_path)
    store = RunStore(tmp_path / "run")
    first = run(store, plan, protocol, fixtures_dir=fixtures)
    assert (first["executed"], first["reused"], first["inputs_changed_task_ids"]) == (18, 0, [])
    recorded = {common.read_json(p)["environment"].get("input_identity_sha256") for p in store.envelope_files()
                if common.read_json(p)["status"]["execution"] == "completed"}
    assert len(recorded) == 2 and all(len(value) == 64 for value in recorded)   # one per adapter's file set
    unchanged = run(store, plan, protocol, fixtures_dir=fixtures)
    assert (unchanged["executed"], unchanged["reused"]) == (0, 18) and len(executions) == 18

    swap_two_weights(fixtures)
    second = run(store, plan, protocol, fixtures_dir=fixtures)
    # The 9 behaviour tasks read the changed file; the 9 readout tasks read two other files and are reused.
    assert (second["executed"], second["reused"], second["remaining_ready"]) == (9, 9, 0)
    assert len(second["inputs_changed_task_ids"]) == 9 and len(executions) == 27
    assert {call[0] for call in executions[18:]} == {"behavior_next_token"}
    # Second attempts only: a run id is a second-resolution stamp, so two runs of one test can share it.
    started = [e for e in store.read_journal() if e.get("event") == "started" and e["attempt"] == 2]
    assert len(started) == 9 and all("differ from the identity" in e["completed_result_not_reused"][0] for e in started)
    # A third run reuses the new attempts: their recorded identity is the current one.
    third = run(store, plan, protocol, fixtures_dir=fixtures)
    assert (third["executed"], third["reused"]) == (0, 18) and len(executions) == 27
    # The new payload of the first row is the fresh computation, not the old one.
    fresh = RunStore(tmp_path / "fresh")
    run(fresh, plan, protocol, fixtures_dir=fixtures)
    task = plan["tasks"][0]
    assert task["spec"]["method"]["id"] == "behavior_next_token"
    new = common.read_json(store.shards_dir / "w0" / f"{task['task_id']}.r0.a2.envelope.json")
    again = common.read_json(fresh.shards_dir / "w0" / f"{task['task_id']}.r0.a1.envelope.json")
    old = common.read_json(store.shards_dir / "w0" / f"{task['task_id']}.r0.a1.envelope.json")
    assert new["payload"]["sha256"] == again["payload"]["sha256"] != old["payload"]["sha256"]
    # Two completed results of one task now name different payloads: the collector refuses and says why.
    with pytest.raises(Refusal) as caught:
        store.collect()
    assert caught.value.code == "duplicate_conflict"
    assert "different input identities" in str(caught.value) and "new run directory" in str(caught.value)
    assert fresh.collect()["assembly"]["by_state"]["completed"] == 18


def test_a_changed_adapter_source_is_executed_again(plan: dict, protocol: dict, tmp_path: Path, executions: list,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: the envelope recorded source_files_sha256 and the reuse check never read it.
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    original = store_module._source_hashes

    def edited(adapter: object) -> dict[str, str]:
        hashes = dict(original(adapter))
        if adapter is behavior_fixture.ADAPTER:
            hashes["scripts/experiments/adapters/behavior_fixture.py"] = "0" * 64
        return hashes

    monkeypatch.setattr(store_module, "_source_hashes", edited)
    second = run(store, plan, protocol)
    assert (second["executed"], second["reused"]) == (9, 9) and len(executions) == 27
    assert {call[0] for call in executions[18:]} == {"behavior_next_token"}
    started = [e for e in store.read_journal() if e.get("event") == "started" and e["attempt"] == 2]
    assert len(started) == 9
    assert all("adapter source files differ" in e["completed_result_not_reused"][0] for e in started)
    # The payloads are the same bytes, so the collector keeps one and lists the other as an identical duplicate.
    assembly = store.collect()["assembly"]
    assert assembly["by_state"]["completed"] == 18 and assembly["counts"]["duplicate_identical"] == 9


def test_an_adapter_may_list_further_source_files_and_a_change_in_one_stops_reuse(
        plan: dict, protocol: dict, tmp_path: Path, executions: list, monkeypatch: pytest.MonkeyPatch) -> None:
    helper = tmp_path / "helper_module.py"
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(behavior_fixture.BehaviorFixtureAdapter, "source_files", (helper,), raising=False)
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    task = plan["tasks"][0]
    doc = common.read_json(store.shards_dir / "w0" / f"{task['task_id']}.r0.a1.envelope.json")
    assert doc["environment"]["source_files_sha256"]["helper_module.py"] == hashlib.sha256(b"VALUE = 1\n").hexdigest()
    assert run(store, plan, protocol)["reused"] == 18
    helper.write_text("VALUE = 2\n", encoding="utf-8")
    again = run(store, plan, protocol)
    assert (again["executed"], again["reused"]) == (9, 9) and len(executions) == 27


def test_an_adapter_without_the_identity_hook_records_null_and_is_reused_as_before(
        plan: dict, protocol: dict, tmp_path: Path, executions: list, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(behavior_fixture.BehaviorFixtureAdapter, "input_identity")
    fixtures = copy_fixtures(tmp_path)
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol, fixtures_dir=fixtures)
    task = plan["tasks"][0]
    doc = common.read_json(store.shards_dir / "w0" / f"{task['task_id']}.r0.a1.envelope.json")
    assert doc["environment"]["input_identity_sha256"] is None
    assert "/environment/input_identity_sha256" in doc["not_recorded"]
    assert envelope.validate_envelope(doc, payload_root=store.run_dir)["status"] == "validated"
    swap_two_weights(fixtures)
    again = run(store, plan, protocol, fixtures_dir=fixtures)
    # No hook: nothing says the inputs changed, so the store behaves as it did before the hook existed.
    assert (again["executed"], again["reused"]) == (0, 18) and len(executions) == 18


def test_a_recorded_identity_is_required_once_the_adapter_has_the_hook(plan: dict, protocol: dict, tmp_path: Path,
                                                                      executions: list,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    store = RunStore(tmp_path / "run")
    hook = behavior_fixture.BehaviorFixtureAdapter.input_identity
    monkeypatch.delattr(behavior_fixture.BehaviorFixtureAdapter, "input_identity")
    run(store, plan, protocol)
    monkeypatch.setattr(behavior_fixture.BehaviorFixtureAdapter, "input_identity", hook, raising=False)
    second = run(store, plan, protocol)
    # The old envelopes record no identity, so their inputs cannot be confirmed: executed again, same payloads.
    assert (second["executed"], second["reused"]) == (9, 9)
    assert store.collect()["assembly"]["counts"]["duplicate_identical"] == 9


def invoke(capsys: pytest.CaptureFixture, *argv: object) -> tuple[int, dict]:
    code = cli.main([str(a) for a in argv])
    return code, json.loads(capsys.readouterr().out)


def test_a_run_that_completes_no_ready_task_is_not_clean_anywhere(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    # Regression: with no fixture files every ready task ended unavailable and all three commands exited 0.
    plan_path, run_dir, empty = tmp_path / "plan.json", tmp_path / "run", tmp_path / "no_fixtures"
    empty.mkdir()
    protocol_path = FIXTURES / "protocol_synthetic.json"
    assert invoke(capsys, "plan", "--protocol", protocol_path, "--out", plan_path)[0] == 0
    code, out = invoke(capsys, "run-fixture", "--plan", plan_path, "--fixtures", empty, "--protocol", protocol_path,
                       "--run-dir", run_dir)
    assert code == 1 and out["by_state"]["completed"] == 0 and out["by_state"]["unavailable"] == 27
    assert (out["remaining_ready"], out["stopped_early"]) == (18, False)
    code, out = invoke(capsys, "collect", "--run-dir", run_dir, "--require-complete")
    assert code == 1 and (out["complete"], out["ready_complete"]) == (True, False)
    assert (out["counts"]["ready_planned"], out["counts"]["ready_completed"], out["counts"]["missing"]) == (18, 0, 0)
    assert invoke(capsys, "collect", "--run-dir", run_dir)[0] == 0          # without the flag it only reports
    code, out = invoke(capsys, "bundle", "--run-dir", run_dir, "--out", tmp_path / "bundle.json")
    assert code == 0
    assert bundle_module.READY_NOT_COMPLETED in out["limitations"] and bundle_module.NOTHING_COMPLETED in out["limitations"]
    built = common.read_json(tmp_path / "bundle.json")
    assert built["execution"]["ready_complete"] is False and common.structural_errors(built, "bundle") == []
    # An attempt that ended unavailable at preflight computed nothing: no unit accepted, no resource recorded.
    doc = next(d for d in map(common.read_json, RunStore(run_dir).envelope_files())
               if d["method"]["id"] == "behavior_next_token")
    assert doc["status"]["execution"] == "unavailable" and doc["counts"]["accepted"] == 0
    assert doc["resources"]["measured"] is False and doc["resources"]["runtime_seconds"] is None
    assert doc["environment"]["dtype"] == "not_applicable" and doc["model"]["provider"] == "not_contacted"


def test_a_run_stopped_on_request_and_a_finished_run_keep_exit_zero(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    plan_path, run_dir = tmp_path / "plan.json", tmp_path / "run"
    protocol_path = FIXTURES / "protocol_synthetic.json"
    invoke(capsys, "plan", "--protocol", protocol_path, "--out", plan_path)
    args = ("run-fixture", "--plan", plan_path, "--fixtures", FIXTURES, "--run-dir", run_dir)
    code, out = invoke(capsys, *args, "--stop-after", 3)
    assert (code, out["stopped_early"], out["remaining_ready"]) == (0, True, 15)
    code, out = invoke(capsys, *args)
    assert (code, out["remaining_ready"]) == (0, 0)
    code, out = invoke(capsys, "collect", "--run-dir", run_dir, "--require-complete")
    assert (code, out["complete"], out["ready_complete"]) == (0, True, True)
    code, out = invoke(capsys, "bundle", "--run-dir", run_dir, "--out", tmp_path / "bundle.json")
    assert not {bundle_module.READY_NOT_COMPLETED, bundle_module.NOTHING_COMPLETED,
                bundle_module.OUTCOMES_DIFFER} & set(out["limitations"])


def test_a_preflight_exception_is_a_recorded_attempt_and_the_run_goes_on(plan: dict, protocol: dict, tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: adapter.preflight was called outside any try block; its exception left run_fixture on the
    # first task, so no task was ever recorded.
    calls = []

    def broken(task: dict, context: dict) -> tuple[str, str | None]:
        calls.append(task["task_id"])
        if len(calls) == 1:
            raise ValueError("placeholder: unreadable input")
        raise Refusal("placeholder_code", "placeholder refusal")

    monkeypatch.setattr(behavior_fixture.ADAPTER, "preflight", broken)
    store = RunStore(tmp_path / "run")
    summary = run(store, plan, protocol)
    assert summary["by_state"] == {"not_run": 0, "unsupported": 9, "unavailable": 9, "invalid": 8, "failed": 1,
                                   "completed": 9}
    assert summary["executed"] == 18 and summary["remaining_ready"] == 9 and store.uncertain_attempts() == []
    docs = [common.read_json(p) for p in store.envelope_files()]
    failed, = [d for d in docs if d["status"]["execution"] == "failed"]
    assert failed["status"]["reason"] == "preflight: ValueError: placeholder: unreadable input"
    assert failed["counts"] == {"requested": 1, "accepted": 1, "completed": 0, "failed": 1, "exclusions": []}
    invalid = [d for d in docs if d["status"]["execution"] == "invalid"]
    assert {d["status"]["reason"] for d in invalid} == {"preflight: placeholder_code: placeholder refusal"}
    events = store.read_journal()
    assert sum(e["event"] == "started" for e in events) == sum(e["event"] == "ended" for e in events) == 18
    assert store.collect()["assembly"]["by_state"]["completed"] == 9


def test_an_adapter_that_breaks_the_preflight_contract_still_refuses(plan: dict, protocol: dict, tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(behavior_fixture.ADAPTER, "preflight", lambda task, context: ("maybe", None))
    assert code_of(lambda: run(RunStore(tmp_path / "run"), plan, protocol)) == "adapter_contract"


def test_a_truncated_fixture_file_gives_json_and_exit_one_not_a_traceback(tmp_path: Path,
                                                                         capsys: pytest.CaptureFixture) -> None:
    fixtures = copy_fixtures(tmp_path)
    logits = fixtures / "behavior_logits.json"
    logits.write_text(logits.read_text(encoding="utf-8")[:400], encoding="utf-8")
    plan_path, protocol_path = tmp_path / "plan.json", FIXTURES / "protocol_synthetic.json"
    invoke(capsys, "plan", "--protocol", protocol_path, "--out", plan_path)
    code, out = invoke(capsys, "run-fixture", "--plan", plan_path, "--fixtures", fixtures, "--protocol", protocol_path,
                       "--run-dir", tmp_path / "run")
    # The 9 readout tasks do not read that file and complete; the 18 non-ready states are recorded too.
    assert code == 1 and out["status"] == "ran" and out["by_state"]["completed"] == 9
    assert out["by_state"]["unavailable"] == 18 and out["recorded_not_ready"] == 18 and out["uncertain_before_run"] == 0
    store = RunStore(tmp_path / "run")
    reasons = {d["status"]["reason"] for d in map(common.read_json, store.envelope_files())
               if d["method"]["id"] == "behavior_next_token"}
    assert len(reasons) == 1 and "is not JSON" in reasons.pop()
    assert len(store.envelope_files()) == 36 and store.uncertain_attempts() == []


@pytest.mark.parametrize("entry", ["payloads", "shards", "shards/w0", "journal.jsonl"])
def test_a_symlink_inside_the_run_directory_is_refused(entry: str, plan: dict, protocol: dict, tmp_path: Path) -> None:
    # Regression: only the run directory itself was checked, so a linked payloads/ or shards/ took the writes.
    elsewhere = tmp_path / "trace_out" / "landed"
    elsewhere.mkdir(parents=True)
    assert code_of(lambda: RunStore(elsewhere)) == "protected_root"
    run_dir = tmp_path / "run"
    link = run_dir / entry
    link.parent.mkdir(parents=True)
    if entry == "journal.jsonl":
        (elsewhere / "journal.jsonl").write_text("", encoding="utf-8")
        link.symlink_to(elsewhere / "journal.jsonl")
    else:
        link.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(Refusal) as caught:
        RunStore(run_dir)
    assert caught.value.code == "run_dir_symlink" and entry in str(caught.value)
    assert [p.name for p in elsewhere.iterdir()] == (["journal.jsonl"] if entry == "journal.jsonl" else [])
    assert (elsewhere / "journal.jsonl").read_text(encoding="utf-8") == "" if entry == "journal.jsonl" else True


def test_a_link_added_after_the_store_was_opened_is_refused_before_any_write(plan: dict, protocol: dict,
                                                                            tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    store = RunStore(tmp_path / "run")
    store.run_dir.mkdir()
    (store.run_dir / "payloads").symlink_to(elsewhere, target_is_directory=True)
    assert code_of(lambda: run(store, plan, protocol)) == "run_dir_symlink"
    assert list(elsewhere.iterdir()) == [] and not store.journal_path.exists()
    (store.run_dir / "payloads").unlink()
    run(store, plan, protocol, stop_after=1)
    (elsewhere / "w9").mkdir()
    (store.shards_dir / "w9").symlink_to(elsewhere / "w9", target_is_directory=True)
    assert code_of(store.collect) == "run_dir_symlink"
    # A broken link is a link too.
    (store.shards_dir / "w9").unlink()
    (store.shards_dir / "w8").symlink_to(tmp_path / "does_not_exist")
    assert code_of(store.collect) == "run_dir_symlink"


def test_a_transient_failure_in_a_racing_worker_does_not_make_the_run_uncollectable(
        plan: dict, protocol: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: w0 failed attempt 1 of a task and w1 completed attempt 1 of it; collect refused
    # shard_disagreement, and a clean resume added nothing, so the directory stayed refused.
    store, other = RunStore(tmp_path / "run"), RunStore(tmp_path / "elsewhere")
    original = behavior_fixture.ADAPTER.execute_fixture
    calls = []

    def fails_once(task: dict, context: dict) -> dict:
        calls.append(task["task_id"])
        if len(calls) == 1:
            raise RuntimeError("placeholder transient failure")
        return original(task, context)

    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", fails_once)
    first = run(store, plan, protocol, worker="w0")
    assert first["by_state"]["failed"] == 1 and first["by_state"]["completed"] == 17
    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", original)
    # w1 ran without seeing w0's shard, as a second process started at the same moment would.
    run(other, plan, protocol, worker="w1")
    shutil.copytree(other.shards_dir / "w1", store.shards_dir / "w1")
    shutil.copytree(other.payloads_dir, store.payloads_dir, dirs_exist_ok=True)

    collected = store.collect()
    assembly = collected["assembly"]
    differing, = assembly["attempt_outcomes_differ"]
    assert (differing["task_id"], differing["replicate"], differing["attempt"]) == (calls[0], 0, 1)
    assert [(o["worker"], o["state"]) for o in differing["outcomes"]] == [("w0", "failed"), ("w1", "completed")]
    assert all(o["envelope_path"].startswith(f"shards/{o['worker']}/") for o in differing["outcomes"])
    row = next(r for r in assembly["tasks"] if r["task_id"] == calls[0])
    assert (row["execution"], row["worker"], row["attempt"]) == ("completed", "w1", 1)
    assert assembly["by_state"] == {"not_run": 0, "unsupported": 9, "unavailable": 9, "invalid": 0, "failed": 0,
                                    "completed": 18}
    assert assembly["ready_complete"] is True
    resumed = run(store, plan, protocol, worker="w0")
    assert (resumed["executed"], resumed["reused"]) == (0, 18)
    assert store.collect()["assembly_sha256"] == collected["assembly_sha256"]
    assert compare.compare_run(store.run_dir)["families"]
    built = bundle_module.build_bundle(store.run_dir)
    assert bundle_module.OUTCOMES_DIFFER in built["limitations"]
    assert built["execution"]["attempt_outcomes_differ"] == assembly["attempt_outcomes_differ"]
    assert common.structural_errors(built, "bundle") == []


def test_an_attempt_whose_envelope_is_on_disk_is_not_listed_as_uncertain(plan: dict, protocol: dict, tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a stop after the envelope write and before the journal's "ended" line left the attempt in
    # "uncertain" although its completed envelope was on disk and was reused.
    store = RunStore(tmp_path / "run")
    original = RunStore.append_journal
    ended = []

    def stops_before_the_second_ended_line(self: RunStore, event: dict) -> None:
        if event.get("event") == "ended":
            ended.append(event["task_id"])
            if len(ended) == 2:
                raise KeyboardInterrupt
        original(self, event)

    monkeypatch.setattr(RunStore, "append_journal", stops_before_the_second_ended_line)
    with pytest.raises(KeyboardInterrupt):
        run(store, plan, protocol)
    monkeypatch.setattr(RunStore, "append_journal", original)
    stopped = ended[1]
    assert (store.shards_dir / "w0" / f"{stopped}.r0.a1.envelope.json").is_file()
    assert store.uncertain_attempts() == []
    missing_line, = store.ended_line_missing()
    assert (missing_line["task_id"], missing_line["attempt"], missing_line["state"]) == (stopped, 1, "completed")
    resumed = run(store, plan, protocol)
    assert (resumed["uncertain_before_run"], resumed["executed"], resumed["reused"]) == (0, 16, 2)
    assembly = store.collect()["assembly"]
    assert assembly["uncertain"] == [] and assembly["counts"]["uncertain_attempts"] == 0
    assert [(r["task_id"], r["envelope_path"]) for r in assembly["ended_line_missing"]] == [
        (stopped, f"shards/w0/{stopped}.r0.a1.envelope.json")]
    built = bundle_module.build_bundle(store.run_dir)
    assert "uncertain_attempts_present_see_execution" not in built["limitations"]
    assert built["execution"]["ended_line_missing"] == assembly["ended_line_missing"]


def test_an_envelope_file_is_created_exclusively(plan: dict, protocol: dict, tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: `require(not path.exists())` followed by os.replace let a second process with the same
    # worker name overwrite the first one's envelope.
    target = tmp_path / "out" / "a.json"
    common.exclusive_write_bytes(target, b"first")
    with pytest.raises(FileExistsError):
        common.exclusive_write_bytes(target, b"second")
    assert target.read_bytes() == b"first" and [p.name for p in target.parent.iterdir()] == ["a.json"]

    store = RunStore(tmp_path / "run")
    original = store_module.exclusive_write_bytes

    def another_process_wrote_first(path: Path, data: bytes, **how: object) -> None:
        # The other process creates the same attempt file after this one chose its name and before it writes.
        # ``how`` carries the directory descriptor the store now writes through (second review round).
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"the other process's envelope")
        original(path, data, **how)

    monkeypatch.setattr(store_module, "exclusive_write_bytes", another_process_wrote_first)
    with pytest.raises(Refusal) as caught:
        run(store, plan, protocol)
    assert caught.value.code == "attempt_collision"
    written, = store.shards_dir.rglob("*.envelope.json")
    assert written.read_bytes() == b"the other process's envelope"


def test_an_event_after_a_cut_off_journal_line_is_still_read(plan: dict, protocol: dict, tmp_path: Path) -> None:
    # Regression: the next event was appended to the cut-off line and both became one unparseable line.
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol, stop_after=1)
    with store.journal_path.open("a", encoding="utf-8") as handle:
        handle.write('{"event": "started", "task_id": "0123')
    cut_line = len(journal_lines(store))
    second = run(store, plan, protocol, worker="w1", stop_after=0)
    events = store.read_journal()
    assert [e["line"] for e in events if e.get("event") == "unparseable"] == [cut_line]
    assert [e["worker"] for e in events if e.get("event") == "run_started"] == ["w0", "w1"]
    assert [e["worker"] for e in events if e.get("event") == "run_ended"] == ["w0", "w1"]
    assert second["executed"] == 0


def test_an_envelope_filed_under_another_tasks_labels_is_refused(plan: dict, protocol: dict, tmp_path: Path) -> None:
    # Regression: the collector took family, variant and method from the envelope, not from the planned task.
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    path = next(p for p in store.envelope_files() if common.read_json(p)["source"]["variant"] == "clinical")
    original = common.read_json(path)
    for block, key, value in (("source", "variant", "colloquial"), ("source", "family_id", "fam-9"),
                              ("input", "n_tokens", 999)):
        doc = copy.deepcopy(original)
        doc[block][key] = value
        common.atomic_write_json(path, doc)
        with pytest.raises(Refusal) as caught:
            store.collect()
        assert caught.value.code == "envelope_task_mismatch" and key in str(caught.value)
    common.atomic_write_json(path, original)
    assert store.collect()["assembly"]["complete"] is True


# -------------------------------------------------------------- second review round, 2026-11-10

def drop_first_row_and_change_the_rest(fixtures: Path, family_id: str, variant: str) -> None:
    """Fixture version B: the named row is gone and every other row has other logits. Still synthetic."""
    path = fixtures / "behavior_logits.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["rows"] = [row for row in doc["rows"] if (row["family_id"], row["variant"]) != (family_id, variant)]
    for row in doc["rows"]:
        row["logits"] = list(reversed(row["logits"]))
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_a_completed_result_is_not_collected_when_its_rerun_under_changed_inputs_did_not_complete(
        plan: dict, protocol: dict, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    # Regression: run 1 completed one task under fixture version A; version B dropped that task's row; run 2
    # executed it again (inputs changed), it ended unavailable, and the other tasks completed under B. The
    # collector kept the version A envelope: collect --require-complete exited 0 and compare computed a
    # behaviour block from one payload of each fixture version.
    fixtures = copy_fixtures(tmp_path)
    store = RunStore(tmp_path / "run")
    first = run(store, plan, protocol, fixtures_dir=fixtures, stop_after=1)
    task = next(t for t in plan["tasks"] if t["task_id"] == first["executed_task_ids"][0])
    family_id, variant = task["spec"]["family_id"], task["spec"]["variant"]
    assert task["spec"]["method"]["id"] == "behavior_next_token"
    drop_first_row_and_change_the_rest(fixtures, family_id, variant)
    second = run(store, plan, protocol, fixtures_dir=fixtures)
    assert second["inputs_changed_task_ids"] == [task["task_id"]] and second["remaining_ready"] == 1
    assert (second["executed"], second["by_state"]["completed"]) == (18, 17)
    # Nine tasks planned as unavailable, recorded in run 1 or run 2, and the one that lost its fixture row.
    assert first["by_state"]["unavailable"] + second["by_state"]["unavailable"] == 10

    assembly = store.collect()["assembly"]
    listed, = assembly["completed_under_superseded_inputs"]
    assert (listed["task_id"], listed["replicate"]) == (task["task_id"], 0)
    assert [(c["attempt"], c["worker"]) for c in listed["completed"]] == [(1, "w0")]
    later, = listed["later_attempts"]
    assert (later["attempt"], later["state"]) == (2, "unavailable")
    assert "differ from the identity" in later["completed_result_not_reused"][0]
    row = next(r for r in assembly["tasks"] if r["task_id"] == task["task_id"])
    assert (row["execution"], row["attempt"], row["payload"]) == ("unavailable", 2, None)
    assert assembly["by_state"]["completed"] == 17 and assembly["by_state"]["unavailable"] == 10
    assert (assembly["counts"]["ready_planned"], assembly["counts"]["ready_completed"]) == (18, 17)
    assert assembly["counts"]["completed_under_superseded_inputs"] == 1
    assert (assembly["complete"], assembly["ready_complete"]) == (True, False)
    # Every behaviour payload that is kept names fixture version B.
    kept = {store.read_payload(r["payload"])["fixture"]["sha256"] for r in assembly["tasks"]
            if r["method"] == "behavior_next_token" and r["execution"] == "completed"}
    assert kept == {common.sha256_file(fixtures / "behavior_logits.json")}

    code, out = invoke(capsys, "collect", "--run-dir", store.run_dir, "--require-complete")
    assert code == 1 and out["ready_complete"] is False
    assert [entry["task_id"] for entry in out["completed_under_superseded_inputs"]] == [task["task_id"]]

    compared = compare.compare_run(store.run_dir)
    family = next(f for f in compared["families"] if f["family_id"] == family_id)
    for entry in family["comparisons"]:
        expected = "not_computed" if variant in (entry["a"], entry["b"]) else "computed"
        assert entry["behavior"]["status"] == expected, entry["comparison_id"]
    assert any(variant in (e["a"], e["b"]) for e in family["comparisons"])
    built = bundle_module.build_bundle(store.run_dir)
    assert bundle_module.SUPERSEDED_INPUTS in built["limitations"]
    assert bundle_module.READY_NOT_COMPLETED in built["limitations"]
    assert built["execution"]["completed_under_superseded_inputs"] == assembly["completed_under_superseded_inputs"]
    assert common.structural_errors(built, "bundle") == []


def test_a_rerun_that_fails_under_a_changed_adapter_sets_the_old_result_aside_until_it_completes(
        plan: dict, protocol: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    original_hashes = store_module._source_hashes

    def edited(adapter: object) -> dict[str, str]:
        hashes = dict(original_hashes(adapter))
        if adapter is behavior_fixture.ADAPTER:
            hashes["scripts/experiments/adapters/behavior_fixture.py"] = "0" * 64
        return hashes

    original = behavior_fixture.ADAPTER.execute_fixture
    calls = []

    def fails_once(task: dict, context: dict) -> dict:
        calls.append(task["task_id"])
        if len(calls) == 1:
            raise RuntimeError("placeholder failure under the edited adapter")
        return original(task, context)

    monkeypatch.setattr(store_module, "_source_hashes", edited)
    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", fails_once)
    second = run(store, plan, protocol)
    assert (second["executed"], second["by_state"]["failed"], second["by_state"]["completed"]) == (9, 1, 8)
    assembly = store.collect()["assembly"]
    listed, = assembly["completed_under_superseded_inputs"]
    assert listed["task_id"] == calls[0] and listed["later_attempts"][0]["state"] == "failed"
    assert "adapter source files differ" in listed["later_attempts"][0]["completed_result_not_reused"][0]
    assert assembly["ready_complete"] is False and assembly["by_state"]["failed"] == 1
    # The other eight were executed again and completed with the same payload bytes: kept once.
    assert assembly["by_state"]["completed"] == 17 and assembly["counts"]["duplicate_identical"] == 8

    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", original)
    third = run(store, plan, protocol)
    assert (third["executed"], third["reused"]) == (1, 17)
    after = store.collect()["assembly"]
    # Attempt 3 completed under the current adapter with the bytes of attempt 1: nothing is set aside now.
    assert after["completed_under_superseded_inputs"] == [] and after["ready_complete"] is True
    assert after["by_state"]["completed"] == 18


def test_a_result_set_aside_counts_again_once_a_later_run_reuses_it_under_its_recorded_inputs(
        plan: dict, protocol: dict, tmp_path: Path) -> None:
    # The fixture file is absent for one run and is then put back unchanged. While it is absent the nine
    # behaviour tasks are executed again and end unavailable, so their completed results are set aside. The
    # third run compares the recorded inputs with the restored file, reuses all 18 and reports nothing left to
    # do; collect must then agree with it.
    fixtures = copy_fixtures(tmp_path)
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol, fixtures_dir=fixtures)
    logits = fixtures / "behavior_logits.json"
    kept = logits.read_bytes()
    logits.unlink()
    second = run(store, plan, protocol, fixtures_dir=fixtures)
    assert (second["executed"], second["by_state"]["unavailable"], second["remaining_ready"]) == (9, 9, 9)
    absent = store.collect()["assembly"]
    assert absent["counts"]["completed_under_superseded_inputs"] == 9 and absent["ready_complete"] is False
    assert all("cannot be identified now" in entry["later_attempts"][0]["completed_result_not_reused"][0]
               for entry in absent["completed_under_superseded_inputs"])
    logits.write_bytes(kept)
    third = run(store, plan, protocol, fixtures_dir=fixtures)
    assert (third["executed"], third["reused"], third["remaining_ready"]) == (0, 18, 0)
    restored = store.collect()["assembly"]
    assert restored["completed_under_superseded_inputs"] == [] and restored["ready_complete"] is True
    assert restored["by_state"]["completed"] == 18
    row = next(r for r in restored["tasks"] if r["method"] == "behavior_next_token")
    assert [(a["attempt"], a["state"]) for a in row["attempts"]] == [(1, "completed"), (2, "unavailable")]
    assert (row["execution"], row["attempt"]) == ("completed", 1)


def test_a_reuse_by_a_run_that_was_already_going_does_not_clear_a_changed_input_failure(
        plan: dict, protocol: dict, tmp_path: Path) -> None:
    """Regression (Codex, PR 167): the collector cleared a set-aside result whenever a ``reused`` line sat below
    the failed attempt's ``started`` line. Two workers on one run directory can be given different fixture
    directories, so a worker that was already running can write that line while the other worker's rerun under
    changed inputs fails. Only a run that began after the attempt ended confirms the inputs."""
    old, changed = copy_fixtures(tmp_path, "old"), copy_fixtures(tmp_path, "changed")
    (changed / "behavior_logits.json").unlink()
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol, fixtures_dir=old)
    failed = run(store, plan, protocol, worker="wB", fixtures_dir=changed)          # reruns end unavailable
    assert failed["by_state"]["unavailable"] == 9
    reusing = run(store, plan, protocol, worker="wA", fixtures_dir=old)             # reuses the old results
    assert reusing["reused"] == 18
    # Run in sequence, wA began after wB's attempts ended: its reuse confirms the recorded inputs.
    assert store.collect()["assembly"]["completed_under_superseded_inputs"] == []
    # The same events as two overlapping workers write them: wA's run began before wB's attempts.
    lines = journal_lines(store)
    events = [json.loads(line) for line in lines]
    start_a = next(i for i, e in enumerate(events) if e["event"] == "run_started" and e["worker"] == "wA")
    start_b = next(i for i, e in enumerate(events) if e["event"] == "run_started" and e["worker"] == "wB")
    moved = lines[:start_b] + [lines[start_a]] + lines[start_b:start_a] + lines[start_a + 1:]
    store.journal_path.write_text("\n".join(moved) + "\n", encoding="utf-8")
    overlapping = RunStore(tmp_path / "run").collect()["assembly"]
    assert overlapping["counts"]["completed_under_superseded_inputs"] == 9
    assert overlapping["ready_complete"] is False


def test_a_later_failure_under_the_same_inputs_does_not_set_a_completed_result_aside(
        plan: dict, protocol: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A second worker that never saw the completed result and failed twice is an honest record of that worker.
    # Its inputs are the recorded ones, so the completed envelope stays the collected result.
    store, other = RunStore(tmp_path / "run"), RunStore(tmp_path / "elsewhere")
    original = behavior_fixture.ADAPTER.execute_fixture
    first_task = plan["tasks"][0]["task_id"]

    def fails_on_the_first_task(task: dict, context: dict) -> dict:
        if task["task_id"] == first_task:
            raise RuntimeError("placeholder transient failure")
        return original(task, context)

    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", fails_on_the_first_task)
    run(store, plan, protocol, worker="w0")
    run(store, plan, protocol, worker="w0")
    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", original)
    run(other, plan, protocol, worker="w1")
    shutil.copytree(other.shards_dir / "w1", store.shards_dir / "w1")
    shutil.copytree(other.payloads_dir, store.payloads_dir, dirs_exist_ok=True)
    assembly = store.collect()["assembly"]
    row = next(r for r in assembly["tasks"] if r["task_id"] == first_task)
    assert [(a["attempt"], a["worker"], a["state"]) for a in row["attempts"]] == [
        (1, "w0", "failed"), (1, "w1", "completed"), (2, "w0", "failed")]
    assert (row["execution"], row["worker"]) == ("completed", "w1")
    assert assembly["completed_under_superseded_inputs"] == [] and assembly["ready_complete"] is True


def merged_from_two_fixture_versions(plan: dict, protocol: dict, tmp_path: Path) -> tuple[RunStore, str]:
    """A run directory in which worker a completed the first three ready tasks under fixture version A (two
    behaviour variants of the first family among them) and worker b's shard, computed elsewhere under version
    B, supplies every other task, the first family's third variant included. No task has two completed
    envelopes, so nothing refuses as a duplicate. The store was collected before the merge."""
    fixtures_a, fixtures_b = copy_fixtures(tmp_path, "fixtures_a"), copy_fixtures(tmp_path, "fixtures_b")
    swap_two_weights(fixtures_b)
    store, other = RunStore(tmp_path / "run"), RunStore(tmp_path / "elsewhere")
    done = run(store, plan, protocol, worker="worker-a", fixtures_dir=fixtures_a, stop_after=3)["executed_task_ids"]
    store.collect()
    run(other, plan, protocol, worker="worker-b", fixtures_dir=fixtures_b)
    (store.shards_dir / "worker-b").mkdir()
    for path in sorted((other.shards_dir / "worker-b").glob("*.envelope.json")):
        doc = common.read_json(path)
        if doc["status"]["execution"] == "completed" and doc["task_id"] not in done:
            shutil.copy(path, store.shards_dir / "worker-b" / path.name)
            shutil.copy(other.run_dir / doc["payload"]["path"], store.run_dir / doc["payload"]["path"])
    return store, done[0]


def test_completed_results_of_one_method_under_two_input_identities_are_refused(plan: dict, protocol: dict,
                                                                              tmp_path: Path) -> None:
    # Regression: nothing compared the recorded input identities across tasks, so results of two fixture
    # versions were assembled into one run that reported ready_complete.
    store, _ = merged_from_two_fixture_versions(plan, protocol, tmp_path)
    with pytest.raises(Refusal) as caught:
        store.collect()
    assert caught.value.code == "mixed_input_identities"
    assert "behavior_next_token" in str(caught.value) and "new run directory" in str(caught.value)
    assert code_of(lambda: compare.compare_run(store.run_dir)) == "mixed_input_identities"
    assert code_of(lambda: bundle_module.build_bundle(store.run_dir)) == "mixed_input_identities"


def test_compare_checks_the_two_sides_of_a_block_itself(plan: dict, protocol: dict, tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # The collector's check is switched off here to show that compare does not rely on it.
    store, _ = merged_from_two_fixture_versions(plan, protocol, tmp_path)
    monkeypatch.setattr(RunStore, "_recorded_inputs", staticmethod(lambda doc: ("same", "same")))
    assembly = store.collect()["assembly"]
    behaviour = [r for r in assembly["tasks"] if r["method"] == "behavior_next_token"]
    assert len({r["inputs"]["input_identity_sha256"] for r in behaviour}) == 2
    assert code_of(lambda: compare.compare_run(store.run_dir)) == "mixed_input_identities"


def test_a_resume_after_an_adapter_edit_keeps_one_recorded_input_pair_per_method(
        plan: dict, protocol: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A legitimate resume must stay collectable. Run 1 stops after five tasks; the adapter file then changes
    # in a way that leaves the payload bytes unchanged; run 2 executes the five again and the rest for the
    # first time. Each of the five has two completed envelopes; the one recorded under the pair that covers
    # every task is kept, so the method's kept envelopes record one pair.
    store = RunStore(tmp_path / "run")
    first = run(store, plan, protocol, stop_after=5)
    original_hashes = store_module._source_hashes

    def edited(adapter: object) -> dict[str, str]:
        hashes = dict(original_hashes(adapter))
        hashes["scripts/exploratory_methods.py"] = "0" * 64      # a file every adapter's payloads depend on
        return hashes

    monkeypatch.setattr(store_module, "_source_hashes", edited)
    second = run(store, plan, protocol)
    assert (second["executed"], second["reused"], second["remaining_ready"]) == (18, 0, 0)
    assembly = store.collect()["assembly"]
    assert assembly["ready_complete"] is True and assembly["counts"]["duplicate_identical"] == 5
    assert assembly["completed_under_superseded_inputs"] == []
    for method in ("behavior_next_token", "logit_lens"):
        rows = [r for r in assembly["tasks"] if r["method"] == method]
        assert {json.dumps(r["inputs"], sort_keys=True) for r in rows} == {json.dumps(rows[0]["inputs"], sort_keys=True)}
        assert rows[0]["inputs"]["source_files_sha256"]["scripts/exploratory_methods.py"] == "0" * 64
    rerun = [r for r in assembly["tasks"] if r["task_id"] in first["executed_task_ids"]]
    assert {r["attempt"] for r in rerun} == {2}
    assert compare.compare_run(store.run_dir)["families"]


def completed_copy_of(store: RunStore, not_ready: dict, attempt: int) -> dict:
    """A hand-made completed envelope for the task of ``not_ready`` (an envelope the plan-state recorder
    wrote), with a hand-made payload of a kind the method files."""
    kind = common.METHOD_PAYLOAD_KINDS[not_ready["method"]["id"]][0]
    data = common.json_bytes({"kind": kind, "note": "hand-made placeholder"})
    sha = hashlib.sha256(data).hexdigest()
    (store.payloads_dir / f"{sha}.json").write_bytes(data)
    doc = copy.deepcopy(not_ready)
    doc["attempt"] = attempt
    doc["status"] = {"execution": "completed", "reason": None}
    doc["attempt_history"] = [{**doc["attempt_history"][-1], "attempt": attempt, "state": "completed", "reason": None}]
    doc["counts"] = {"requested": 1, "accepted": 1, "completed": 1, "failed": 0, "exclusions": []}
    doc["resources"] = {**doc["resources"], "measured": True, "runtime_seconds": 0.1}
    doc["payload"] = {"kind": kind, "sha256": sha, "path": f"payloads/{sha}.json"}
    return doc


@pytest.mark.parametrize("attempt", [1, 2])
def test_a_completed_envelope_for_a_task_the_plan_does_not_mark_ready_is_refused(attempt: int, plan: dict,
                                                                               protocol: dict, tmp_path: Path) -> None:
    # Regression: removing shard_disagreement let a completed envelope for a task planned as unsupported be
    # collected as completed (by_state completed 19 with 18 ready tasks). It refuses at any attempt number;
    # at attempt 2 it was accepted before the first review round as well.
    store = RunStore(tmp_path / "run")
    run(store, plan, protocol)
    for state in ("unsupported", "unavailable"):
        recorded = next(d for d in map(common.read_json, store.envelope_files()) if d["status"]["execution"] == state)
        assert next(t for t in plan["tasks"] if t["task_id"] == recorded["task_id"])["planned_state"] == state
        forged = completed_copy_of(store, recorded, attempt)
        assert envelope.validate_envelope(forged, payload_root=store.run_dir)["status"] == "validated"
        path = store.shards_dir / "wx" / f"{forged['task_id']}.r0.a{attempt}.envelope.json"
        common.atomic_write_json(path, forged)
        with pytest.raises(Refusal) as caught:
            store.collect()
        assert caught.value.code == "plan_state_conflict"
        assert f"shards/wx/{path.name}" in str(caught.value) and state in str(caught.value)
        path.unlink()
    assert store.collect()["assembly"]["by_state"]["completed"] == 18


@pytest.mark.parametrize("entry", ["payloads", "shards", "shards/w0"])
def test_a_link_created_during_a_run_takes_no_write(entry: str, plan: dict, protocol: dict, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: the layout was checked once before the task loop. A link put at payloads/ after that check
    # received all 18 payload files of the run. The directory names below stand for a protected root.
    elsewhere = tmp_path / "trace_out" / "landed"
    elsewhere.mkdir(parents=True)
    store = RunStore(tmp_path / "run")
    original = behavior_fixture.ADAPTER.execute_fixture
    link = store.run_dir / entry

    def another_actor_links_first(task: dict, context: dict) -> dict:
        # Stands for a second process acting after run_fixture's layout check and before the first write.
        if not link.is_symlink():
            assert not link.exists()
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(elsewhere, target_is_directory=True)
        return original(task, context)

    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", another_actor_links_first)
    with pytest.raises(Refusal) as caught:
        run(store, plan, protocol)
    assert caught.value.code == "run_dir_symlink" and entry in str(caught.value)
    assert list(elsewhere.iterdir()) == []
    assert list(store.run_dir.rglob("*.envelope.json")) == []
    # The attempt has a journaled start and no envelope: it is reported as uncertain, never as completed.
    assert [e["attempt"] for e in store.uncertain_attempts()] == [1]


def test_a_write_through_a_directory_descriptor_stays_in_the_directory_that_was_opened(tmp_path: Path) -> None:
    if not common.DIR_FD_WRITES:
        pytest.skip("this platform has no directory descriptors; the store checks paths before each write")
    real, elsewhere = tmp_path / "payloads", tmp_path / "elsewhere"
    real.mkdir()
    elsewhere.mkdir()
    handle = common.os.open(real, common.os.O_RDONLY | common.os.O_DIRECTORY | common.os.O_NOFOLLOW)
    try:
        # The path is replaced by a link after the descriptor was opened.
        real.rename(tmp_path / "moved")
        real.symlink_to(elsewhere, target_is_directory=True)
        common.atomic_write_bytes(real / "a.json", b"one", dir_fd=handle)
        common.exclusive_write_bytes(real / "b.json", b"two", dir_fd=handle)
        with pytest.raises(FileExistsError):
            common.exclusive_write_bytes(real / "b.json", b"three", dir_fd=handle)
    finally:
        common.os.close(handle)
    assert list(elsewhere.iterdir()) == []
    assert sorted(p.name for p in (tmp_path / "moved").iterdir()) == ["a.json", "b.json"]
    assert (tmp_path / "moved" / "b.json").read_bytes() == b"two"


def test_without_directory_descriptors_the_store_checks_paths_before_each_write(plan: dict, protocol: dict,
                                                                              tmp_path: Path,
                                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_module, "DIR_FD_WRITES", False)
    store = RunStore(tmp_path / "run")
    assert run(store, plan, protocol)["by_state"]["completed"] == 18
    assert store.collect()["assembly"]["ready_complete"] is True
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    fresh = RunStore(tmp_path / "run2")
    original = behavior_fixture.ADAPTER.execute_fixture

    def another_actor_links_first(task: dict, context: dict) -> dict:
        if not (fresh.run_dir / "payloads").is_symlink():
            (fresh.run_dir / "payloads").symlink_to(elsewhere, target_is_directory=True)
        return original(task, context)

    monkeypatch.setattr(behavior_fixture.ADAPTER, "execute_fixture", another_actor_links_first)
    assert code_of(lambda: run(fresh, plan, protocol)) == "run_dir_symlink"
    assert list(elsewhere.iterdir()) == []
