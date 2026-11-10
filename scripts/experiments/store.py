"""Run store: shards, journal, resume, reuse and the single collector.

Layout of one run directory::

    plan.json
    journal.jsonl                                              append-only
    shards/<worker>/<task_id>.r<replicate>.a<attempt>.envelope.json
    payloads/<sha256>.json                                     content-addressed
    collected.json

What the store guarantees, and what it does not:

* Every file except the journal is written to a temporary file and fsynced first. The plan, payloads and
  ``collected.json`` are then put in place with ``os.replace``; an attempt envelope is put in place with
  ``os.link``, which never replaces an existing file. The journal is opened with ``O_APPEND`` and each line is
  fsynced. A reader never sees half an envelope.
* A ``started`` line is journaled before an attempt runs and an ``ended`` line after. A ``started`` with no
  ``ended`` and no envelope of that attempt is an uncertain attempt. It is kept and reported; the store cannot
  tell whether it executed. A ``started`` with no ``ended`` whose envelope is on disk is listed separately as
  ``ended_line_missing``: its outcome is the envelope's.
* Reuse is keyed on ``(spec_sha256, replicate)``. Anything that changes the spec (input, method block, model,
  settings, protocol) changes the key, so nothing is reused. Replicate 1 has its own key. Under one key, a
  completed envelope is reused only when its payload file still has the recorded SHA-256, the adapter source
  files have the hashes the envelope recorded, and the adapter's input identity (the fixture files, a basis
  manifest: the inputs outside the spec) equals the recorded one. When one of these differs the task is
  executed again as a new attempt and counted as executed. An adapter without the ``input_identity`` hook has
  a null identity recorded and is reused on the first two conditions alone.
* Workers write to separate shard directories. Two workers started at the same time on the same run directory
  both execute the same tasks: there is no task claim and no exactly-once guarantee. The collector collapses
  identical duplicates and refuses two completed envelopes that name different payloads. Attempts of one
  number that ended in different states in two shards are both kept and listed (``attempt_outcomes_differ``);
  a completed envelope is preferred. A worker name must belong to one process at a time; an envelope file is
  created exclusively, so of two processes that pick the same attempt file one refuses ``attempt_collision``.
* The collector is the only assembler. It verifies every payload hash each time it runs.
* ``payloads/``, ``shards/``, each shard directory and ``journal.jsonl`` must be real entries inside the run
  directory. A symbolic link in their place refuses ``run_dir_symlink``, so a write cannot leave the directory
  whose path was checked.

Fixture timings recorded here are real wall-clock measurements of this process. They say nothing about a
model run.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.experiments.adapters import input_identity, load_adapter
from scripts.experiments.common import (
    COLLECTED_SCHEMA, ENGINE, EXECUTION_STATES, FIXTURE_BACKEND, NOT_APPLICABLE, SAFE_NAME, UNCERTAIN, Refusal,
    atomic_write_bytes, atomic_write_json, check_output_path, digest, exclusive_write_bytes, json_bytes, read_json,
    require, sha256_bytes, sha256_file, utc_now,
)
from scripts.experiments.envelope import (
    NOT_EXECUTED_STATES, build_envelope, method_block, null_pointers, validate_envelope,
)
from scripts.experiments.planner import validate_plan

STAGES = ("preflight", "execute", "validate", "write")
TIMING_CAVEAT = ("Wall-clock seconds measured in the named process on offline fixtures. They say nothing about a "
                 "model run and must not be used to size one.")
EXECUTION_GUARANTEE = ("No exactly-once claim. Each attempt is journaled before and after it runs. Identical "
                       "duplicates are kept once, two completed results with different payloads refuse, attempts "
                       "that ended in different states in two shards are listed, and an attempt with a start, no "
                       "end and no envelope is listed as uncertain: it may or may not have executed.")


@lru_cache(maxsize=1)
def engine_commit() -> str | None:
    """HEAD of the engine checkout, or None when it cannot be read. The working tree may differ from it, which
    is why envelopes also record the SHA-256 of the adapter source files."""
    try:
        done = subprocess.run(["git", "-C", str(ENGINE), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    value = done.stdout.strip()
    return value if done.returncode == 0 and len(value) == 40 else None


def _source_hashes(adapter: Any) -> dict[str, str]:
    """SHA-256 of the source files an adapter's payloads depend on: ``scripts/exploratory_methods.py``, the
    adapter's own module, and any further files the adapter lists in an optional ``source_files`` attribute
    (modules it imports for its arithmetic). The reuse check compares these with the envelope's record."""
    files = [ENGINE / "scripts" / "exploratory_methods.py"]
    module_file = getattr(sys.modules.get(type(adapter).__module__), "__file__", None)
    if module_file:
        files.append(Path(module_file))
    files.extend(Path(extra) for extra in getattr(adapter, "source_files", ()))
    hashes = {}
    for file in files:
        try:
            name = file.resolve().relative_to(ENGINE).as_posix()
        except ValueError:
            name = file.name
        hashes[name] = sha256_file(file)
    return hashes


class RunStore:
    """One run directory. Construction applies the output-path rules; it creates nothing."""

    def __init__(self, run_dir: Path | str, *, allow_roots: Iterable[Path | str] = ()) -> None:
        self.allow_roots = tuple(allow_roots)
        self.run_dir = check_output_path(run_dir, self.allow_roots)
        self.plan_path = self.run_dir / "plan.json"
        self.journal_path = self.run_dir / "journal.jsonl"
        self.shards_dir = self.run_dir / "shards"
        self.payloads_dir = self.run_dir / "payloads"
        self.collected_path = self.run_dir / "collected.json"
        self.check_layout()

    def check_layout(self) -> None:
        """Refuse a run directory in which ``payloads/``, ``shards/``, a shard directory or ``journal.jsonl``
        is a symbolic link or resolves outside the run directory.

        The output-path rules are applied to the run directory itself. Writes below it follow links in these
        entries, so a link there would send payloads, envelopes or journal lines to a place that was never
        checked. Called at construction, before a run and before every assembly.
        """
        entries = [self.payloads_dir, self.shards_dir, self.journal_path]
        if self.shards_dir.is_dir() and not self.shards_dir.is_symlink():
            entries.extend(sorted(self.shards_dir.iterdir()))
        for entry in entries:
            if entry.is_symlink():
                outside = True
            elif entry.exists():
                outside = self.run_dir not in entry.resolve().parents
            else:
                continue
            require(not outside, "run_dir_symlink",
                    f"{entry.relative_to(self.run_dir).as_posix()} in {self.run_dir} is a symbolic link or "
                    "resolves outside the run directory; the store writes only inside the directory whose path "
                    "it checked. Remove the link or use a new run directory")

    # ------------------------------------------------------------------ plan

    def compatible_with(self, plan: Mapping[str, Any]) -> bool:
        """True when the directory holds no plan or a plan of the same protocol hash."""
        if not self.plan_path.exists():
            return True
        return read_json(self.plan_path)["protocol"]["sha256"] == plan["protocol"]["sha256"]

    def open_plan(self, plan: dict[str, Any]) -> None:
        """Start or resume the run for ``plan``. A directory that holds another protocol's plan refuses."""
        validate_plan(plan)
        require(self.compatible_with(plan), "incompatible_resume",
                f"{self.run_dir} holds a plan for another protocol hash; use a new run directory "
                "(--new-run-dir) so that no result of the other protocol is reused or overwritten")
        if not self.plan_path.exists() or read_json(self.plan_path) != plan:
            atomic_write_json(self.plan_path, plan)

    def read_plan(self) -> dict[str, Any]:
        require(self.plan_path.is_file(), "no_plan", f"{self.run_dir} holds no plan.json")
        return validate_plan(read_json(self.plan_path))

    # --------------------------------------------------------------- journal

    def append_journal(self, event: Mapping[str, Any]) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        line = (json.dumps(dict(event), sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            handle = os.open(self.journal_path, flags, 0o644)
        except OSError:
            self.check_layout()  # a link put in the journal's place refuses by name
            raise
        try:
            # A line cut off by a crash has no newline. Without one here, this event would be appended to that
            # line and both would be unparseable; with it, only the cut-off line is.
            size = os.fstat(handle).st_size
            if size and os.pread(handle, 1, size - 1) != b"\n":
                line = b"\n" + line
            os.write(handle, line)
            os.fsync(handle)
        finally:
            os.close(handle)

    def read_journal(self) -> list[dict[str, Any]]:
        """Journal events in file order. A line that is not JSON (a write cut off by a crash) is kept as
        ``{"event": "unparseable", "line": n}``; it is reported, never dropped."""
        if not self.journal_path.exists():
            return []
        events = []
        for number, line in enumerate(self.journal_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                events.append(event if isinstance(event, dict) else {"event": "unparseable", "line": number})
            except ValueError:
                events.append({"event": "unparseable", "line": number})
        return events

    @staticmethod
    def _ident(event: Mapping[str, Any]) -> tuple[Any, ...]:
        return (event.get("spec_sha256"), event.get("replicate"), event.get("attempt"), event.get("worker"),
                event.get("run_id"))

    def _recorded_attempts(self, index: Mapping[tuple[str, int], list[tuple[Path, dict[str, Any]]]] | None = None
                           ) -> dict[tuple[Any, ...], tuple[Path, dict[str, Any]]]:
        """Every attempt that has an envelope on disk, keyed like a journal event (spec, replicate, attempt,
        worker, run id)."""
        index = self._index() if index is None else index
        return {(doc["spec_sha256"], doc["replicate"], doc["attempt"], path.parent.name, doc["run_id"]): (path, doc)
                for entries in index.values() for path, doc in entries}

    def _started_without_end(self, events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        events = self.read_journal() if events is None else events
        ended = {self._ident(e) for e in events if e.get("event") == "ended"}
        return [e for e in events if e.get("event") == "started" and self._ident(e) not in ended]

    def uncertain_attempts(self, events: list[dict[str, Any]] | None = None,
                           index: Mapping[tuple[str, int], list[tuple[Path, dict[str, Any]]]] | None = None
                           ) -> list[dict[str, Any]]:
        """Attempts with a ``started`` line, no ``ended`` line and no envelope of that attempt on disk.

        An attempt whose envelope was written before the process stopped has a known outcome, so it is not
        uncertain; ``ended_line_missing`` lists those.
        """
        recorded = self._recorded_attempts(index)
        return [e for e in self._started_without_end(events) if self._ident(e) not in recorded]

    def ended_line_missing(self, events: list[dict[str, Any]] | None = None,
                           index: Mapping[tuple[str, int], list[tuple[Path, dict[str, Any]]]] | None = None
                           ) -> list[dict[str, Any]]:
        """Attempts with a ``started`` line and no ``ended`` line whose envelope is on disk: the process
        stopped after the envelope write and before the journal line. One row per attempt, with the envelope's
        path and state."""
        recorded = self._recorded_attempts(index)
        rows = []
        for event in self._started_without_end(events):
            found = recorded.get(self._ident(event))
            if found is not None:
                path, doc = found
                rows.append({"task_id": event.get("task_id"), "replicate": event.get("replicate"),
                             "attempt": event.get("attempt"), "worker": event.get("worker"),
                             "run_id": event.get("run_id"), "started_utc": event.get("utc"),
                             "state": doc["status"]["execution"],
                             "envelope_path": path.relative_to(self.run_dir).as_posix()})
        return rows

    # ------------------------------------------------------------- envelopes

    def envelope_files(self) -> list[Path]:
        return sorted(self.shards_dir.glob("*/*.envelope.json")) if self.shards_dir.is_dir() else []

    def _index(self) -> dict[tuple[str, int], list[tuple[Path, dict[str, Any]]]]:
        index: dict[tuple[str, int], list[tuple[Path, dict[str, Any]]]] = {}
        for path in self.envelope_files():
            doc = read_json(path)
            index.setdefault((doc["spec_sha256"], doc["replicate"]), []).append((path, doc))
        return index

    def _write_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        data = json_bytes(payload)
        sha = sha256_bytes(data)
        path = self.payloads_dir / f"{sha}.json"
        if path.exists():
            require(path.read_bytes() == data, "payload_hash",
                    f"payloads/{sha}.json holds bytes that do not hash to its name")
        else:
            atomic_write_bytes(path, data)
        return {"kind": payload["kind"], "sha256": sha, "path": f"payloads/{sha}.json", "bytes": len(data)}

    # ------------------------------------------------------------------ run

    def _history(self, key: tuple[str, int], existing: list[tuple[Path, dict[str, Any]]],
                 uncertain: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One entry per earlier attempt number of this key, from envelopes first and the journal second."""
        by_attempt: dict[int, dict[str, Any]] = {}
        for event in uncertain:
            if (event.get("spec_sha256"), event.get("replicate")) == key and type(event.get("attempt")) is int:
                by_attempt[event["attempt"]] = {
                    "attempt": event["attempt"], "state": UNCERTAIN, "worker": event.get("worker"),
                    "reason": "a start was journaled and no end was; whether the attempt executed is unknown",
                    "started_utc": event.get("utc")}
        for path, doc in existing:
            for entry in doc["attempt_history"]:
                if entry["attempt"] == doc["attempt"] or entry["attempt"] not in by_attempt:
                    by_attempt[entry["attempt"]] = dict(entry)
        return [by_attempt[n] for n in sorted(by_attempt)]

    def _attempt(self, task: dict[str, Any], context: dict[str, Any], registry: Mapping[str, str] | None,
                 seconds: dict[str, float]) -> tuple[str, str | None, dict[str, Any] | None, Any]:
        """Run one ready task. Returns ``(state, reason, payload, adapter)``."""
        adapter, reason = load_adapter(task["spec"]["method"]["id"], registry)
        if adapter is None:
            return "unavailable", reason, None, None
        clock = time.perf_counter()
        try:
            state, why = adapter.preflight(task, context)
        except Refusal as exc:  # recorded like an execution refusal, so the loop goes on to the next task
            return "invalid", f"preflight: {exc.code}: {exc}", None, adapter
        except Exception as exc:  # an adapter error at preflight is a failed attempt, recorded with its type
            return "failed", f"preflight: {type(exc).__name__}: {exc}", None, adapter
        finally:
            seconds["preflight"] += time.perf_counter() - clock
        if state != "ready":
            require(state in ("unavailable", "unsupported") and bool(why), "adapter_contract",
                    "preflight must return ready, or unavailable or unsupported with a reason")
            return state, why, None, adapter
        clock = time.perf_counter()
        try:
            payload = adapter.execute_fixture(task, context)
        except Refusal as exc:
            seconds["execute"] += time.perf_counter() - clock
            if exc.code == "unsupported_operation":
                return "unsupported", f"unsupported_operation: {exc}", None, adapter
            return "invalid", f"{exc.code}: {exc}", None, adapter
        except Exception as exc:  # an adapter error is a failed attempt, recorded with its type
            seconds["execute"] += time.perf_counter() - clock
            return "failed", f"{type(exc).__name__}: {exc}", None, adapter
        seconds["execute"] += time.perf_counter() - clock
        clock = time.perf_counter()
        try:
            require(isinstance(payload, dict) and payload.get("kind") in adapter.payload_kinds,
                    "method_payload_mismatch", "The adapter returned a payload kind it does not declare")
            adapter.validate_payload(payload, task, context)
            json_bytes(payload)  # NaN or infinity anywhere in the payload refuses here
        except Refusal as exc:
            return "invalid", f"{exc.code}: {exc}", None, adapter
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            return "invalid", f"malformed payload: {type(exc).__name__}: {exc}", None, adapter
        finally:
            seconds["validate"] += time.perf_counter() - clock
        return "completed", None, payload, adapter

    def _record(self, *, run_id: str, worker: str, task: dict[str, Any], protocol: Mapping[str, Any],
                attempt: int, history: list[dict[str, Any]], state: str, reason: str | None,
                payload: dict[str, Any] | None, started_utc: str | None, runtime: float | None,
                adapter: Any, identity: str | None = None) -> Path:
        """Write the payload (when completed) and the envelope of one attempt; return the envelope path.

        ``identity`` is the adapter's input identity for the task, or None when the adapter has no hook or the
        inputs could not be identified; a null is listed in ``not_recorded``.
        """
        reference = None
        if state == "completed":
            try:
                reference = self._write_payload(payload)
            except Refusal as exc:
                state, reason, payload = "failed", f"{exc.code}: {exc}", None
        # An attempt that ended unavailable or unsupported at preflight computed nothing: it accepts no unit
        # and records no resource, like a task that was never ready.
        executed = runtime is not None and state not in NOT_EXECUTED_STATES
        counts = {"requested": 1, "accepted": 0, "completed": 0, "failed": 0, "exclusions": []}
        if executed:
            counts["accepted"] = 1
            counts["completed"] = int(state == "completed")
            counts["failed"] = int(state == "failed")
            if state == "invalid":
                counts["exclusions"] = [{"reason": "invalid_payload", "n": 1}]
        resources = {"runtime_seconds": runtime if executed else None, "peak_memory_bytes": None,
                     "storage_bytes": reference["bytes"] if reference else None, "usage": None, "cost_usd": None,
                     "measured": executed}
        spec = task["spec"]
        fixture = spec["settings"]["backend"] == FIXTURE_BACKEND
        environment = {
            "source_commits": {"engine": engine_commit()},
            "packages": {"python": platform.python_version()},
            "lock_sha256": None,
            "backend": spec["settings"]["backend"],
            "device": NOT_APPLICABLE,
            # What ran: fixture arithmetic on JSON numbers is Python float64. The dtype the protocol declares
            # for the model is in the task spec.
            "dtype": "float64" if executed else NOT_APPLICABLE,
            "quantization": "none" if executed else NOT_APPLICABLE,
            "attention_implementation": NOT_APPLICABLE,
            "sampling": {"seed": protocol["seed"], "sampled": False},
        }
        if adapter is not None:
            environment["source_files_sha256"] = _source_hashes(adapter)
            environment["input_identity_sha256"] = identity
        block = method_block(spec["method"], payload)
        not_recorded = ["/environment/lock_sha256"] + null_pointers(block["fitted_artifact"],
                                                                    "/method/fitted_artifact")
        if adapter is not None and identity is None:
            not_recorded.append("/environment/input_identity_sha256")
        if block["output_head"] is None:
            not_recorded.append("/method/output_head")
        if environment["source_commits"]["engine"] is None:
            not_recorded.append("/environment/source_commits/engine")
        family = next(f for f in protocol["case_families"] if f["family_id"] == spec["family_id"])
        if family["legacy_join"] is None:
            not_recorded.append("/source/legacy_join")
        envelope = build_envelope(
            run_id=run_id, task=task, protocol=protocol, attempt=attempt,
            attempt_history=history + [{"attempt": attempt, "state": state, "reason": reason,
                                        "started_utc": started_utc, "worker": worker}],
            execution=state, reason=reason,
            payload={k: reference[k] for k in ("kind", "sha256", "path")} if reference else None,
            counts=counts, resources=resources, environment=environment,
            provider="none_offline_fixture" if fixture and executed else "not_contacted",
            route="offline_fixture" if fixture and executed else "not_executed",
            alignment="token_ids_supplied_by_protocol_not_retokenized",
            not_recorded=not_recorded, output_head=block["output_head"], payload_root=self.run_dir)
        path = (self.shards_dir / worker
                / f"{task['task_id']}.r{task['replicate']}.a{attempt}.envelope.json")
        try:
            # Exclusive: of two processes that picked the same attempt file, one writes and the other refuses.
            exclusive_write_bytes(path, json_bytes(envelope))
        except FileExistsError:
            raise Refusal("attempt_collision", f"{path.name} already exists in shard {worker}") from None
        return path

    def run_fixture(self, plan: dict[str, Any], worker: str, *, fixtures_dir: Path | str,
                    protocol: Mapping[str, Any], stop_after: int | None = None,
                    registry: Mapping[str, str] | None = None,
                    capabilities: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Execute the plan's ready tasks on offline fixtures, in plan order, and record every other task's state.

        ``stop_after=N`` stops before the (N+1)th execution, which simulates an interruption: later tasks are
        left without an envelope. Running again resumes. A task with a completed, hash-verified envelope for its
        ``(spec_sha256, replicate)`` whose recorded adapter source hashes and input identity still hold is
        counted ``reused`` and is not executed. When they do not hold, the task is executed again as a new
        attempt and its id is listed in ``inputs_changed_task_ids``.
        """
        require(isinstance(worker, str) and bool(SAFE_NAME.fullmatch(worker)), "worker_name",
                "worker must be 1-64 characters from A-Z a-z 0-9 _ . - and start with a letter or digit")
        require(stop_after is None or (type(stop_after) is int and stop_after >= 0), "stop_after",
                "stop_after must be a non-negative integer")
        require(digest(dict(protocol)) == plan["protocol"]["sha256"], "protocol_mismatch",
                "The protocol supplied to run_fixture is not the one the plan was built from")
        self.check_layout()
        self.open_plan(plan)
        run_id = f"{utc_now().replace('-', '').replace(':', '')}-{worker}-{os.getpid()}"
        context = {"fixtures_dir": Path(fixtures_dir), "protocol": protocol,
                   "capabilities": capabilities if capabilities is not None else plan["capability_matrix"]}
        seconds = {stage: 0.0 for stage in STAGES}
        summary: dict[str, Any] = {
            "run_id": run_id, "worker": worker, "executed": 0, "reused": 0, "recorded_not_ready": 0,
            "already_recorded": 0, "by_state": {state: 0 for state in EXECUTION_STATES}, "stopped_early": False,
            "executed_task_ids": [], "reused_task_ids": [], "inputs_changed_task_ids": []}
        self.append_journal({"event": "run_started", "run_id": run_id, "worker": worker, "utc": utc_now(),
                             "stop_after": stop_after})
        index = self._index()
        uncertain = self.uncertain_attempts(index=index)
        summary["uncertain_before_run"] = len(uncertain)
        inputs: dict[tuple[str, int], dict[str, Any]] = {}

        def current(task: dict[str, Any]) -> dict[str, Any]:
            """What the task's inputs outside its spec are now: adapter source hashes and input identity."""
            key = (task["spec_sha256"], task["replicate"])
            if key not in inputs:
                inputs[key] = self._current_inputs(task, context, registry)
            return inputs[key]

        for task in plan["tasks"]:
            key = (task["spec_sha256"], task["replicate"])
            existing = index.get(key, [])
            journaled = [e["attempt"] for e in uncertain
                         if (e.get("spec_sha256"), e.get("replicate")) == key and type(e.get("attempt")) is int]
            attempt = max([doc["attempt"] for _, doc in existing] + journaled + [0]) + 1
            ident = {"task_id": task["task_id"], "spec_sha256": task["spec_sha256"],
                     "replicate": task["replicate"], "worker": worker, "run_id": run_id}
            if task["planned_state"] != "ready":
                if any(doc["status"] == {"execution": task["planned_state"], "reason": task["reason"]}
                       for _, doc in existing):
                    summary["already_recorded"] += 1
                    continue
                clock = time.perf_counter()
                path = self._record(run_id=run_id, worker=worker, task=task, protocol=protocol, attempt=attempt,
                                    history=self._history(key, existing, uncertain),
                                    state=task["planned_state"], reason=task["reason"], payload=None,
                                    started_utc=None, runtime=None, adapter=None)
                seconds["write"] += time.perf_counter() - clock
                index.setdefault(key, []).append((path, read_json(path)))
                summary["recorded_not_ready"] += 1
                summary["by_state"][task["planned_state"]] += 1
                continue
            reusable, changed = self._reuse(existing, current(task))
            if reusable:
                self.append_journal({"event": "reused", "utc": utc_now(), **ident})
                summary["reused"] += 1
                summary["reused_task_ids"].append(task["task_id"])
                continue
            if stop_after is not None and summary["executed"] >= stop_after:
                summary["stopped_early"] = True
                break
            started_utc = utc_now()
            started = {"event": "started", "attempt": attempt, "utc": started_utc, **ident}
            if changed:
                # A completed result exists and is not reused: say why in the journal and in the summary.
                started["completed_result_not_reused"] = changed
                summary["inputs_changed_task_ids"].append(task["task_id"])
            self.append_journal(started)
            clock = time.perf_counter()
            state, reason, payload, adapter = self._attempt(task, context, registry, seconds)
            runtime = time.perf_counter() - clock
            clock = time.perf_counter()
            path = self._record(run_id=run_id, worker=worker, task=task, protocol=protocol, attempt=attempt,
                                history=self._history(key, existing, uncertain), state=state, reason=reason,
                                payload=payload, started_utc=started_utc, runtime=runtime, adapter=adapter,
                                identity=current(task)["input_identity"])
            seconds["write"] += time.perf_counter() - clock
            recorded = read_json(path)
            index.setdefault(key, []).append((path, recorded))
            self.append_journal({"event": "ended", "attempt": attempt, "utc": utc_now(),
                                 "state": recorded["status"]["execution"],
                                 "reason": recorded["status"]["reason"], **ident})
            summary["executed"] += 1
            summary["executed_task_ids"].append(task["task_id"])
            summary["by_state"][recorded["status"]["execution"]] += 1
        ready = [t for t in plan["tasks"] if t["planned_state"] == "ready"]
        summary["remaining_ready"] = sum(
            1 for t in ready if not self._reuse(index.get((t["spec_sha256"], t["replicate"]), []), current(t))[0])
        summary["stage_seconds"] = {stage: round(value, 6) for stage, value in seconds.items()}
        summary["stage_seconds_measured"] = True
        summary["timing_caveat"] = TIMING_CAVEAT
        self.append_journal({"event": "run_ended", "run_id": run_id, "worker": worker, "utc": utc_now(),
                             "executed": summary["executed"], "reused": summary["reused"],
                             "stopped_early": summary["stopped_early"],
                             "stage_seconds": summary["stage_seconds"], "measured": True})
        return summary

    @staticmethod
    def _current_inputs(task: dict[str, Any], context: dict[str, Any],
                        registry: Mapping[str, str] | None) -> dict[str, Any]:
        """The adapter source hashes and the adapter's input identity for ``task``, as they are now."""
        adapter, _reason = load_adapter(task["spec"]["method"]["id"], registry)
        if adapter is None:
            return {"adapter": False, "implemented": False, "input_identity": None, "source_files": None}
        implemented, identity = input_identity(adapter, task, context)
        return {"adapter": True, "implemented": implemented, "input_identity": identity,
                "source_files": _source_hashes(adapter)}

    def _reuse(self, existing: list[tuple[Path, dict[str, Any]]],
               current: Mapping[str, Any]) -> tuple[bool, list[str]]:
        """``(reusable, why_not)`` for one ``(spec_sha256, replicate)``.

        Reusable: a completed envelope validates, its payload file still has its hash, and the inputs outside
        the spec are the ones it recorded (adapter source hashes, and the input identity when the adapter has
        the hook). ``why_not`` lists, for each completed and hash-verified envelope that is not reused, what
        differs; it is empty when no such envelope exists.
        """
        changed: list[str] = []
        for _path, doc in existing:
            if doc["status"]["execution"] != "completed":
                continue
            try:
                if not validate_envelope(doc, payload_root=self.run_dir)["payload_verified"]:
                    continue
            except Refusal:
                continue
            difference = self._inputs_difference(doc["environment"], current)
            if difference is None:
                return True, []
            changed.append(difference)
        return False, changed

    @staticmethod
    def _inputs_difference(environment: Mapping[str, Any], current: Mapping[str, Any]) -> str | None:
        """None when the envelope's recorded inputs outside the spec equal the current ones, else what differs."""
        if not current["adapter"]:
            return "the adapter cannot be loaded now, so its source files cannot be compared"
        if environment.get("source_files_sha256") != current["source_files"]:
            return "adapter source files differ from the hashes the envelope recorded"
        if not current["implemented"]:
            return None  # no input_identity hook: reuse on the payload hash and source hashes, as before
        recorded = environment.get("input_identity_sha256")
        if recorded is None:
            return "the envelope records no input identity"
        if current["input_identity"] is None:
            return "the adapter's inputs cannot be identified now"
        if recorded != current["input_identity"]:
            return "the adapter's inputs (fixture files or basis) differ from the identity the envelope recorded"
        return None

    # -------------------------------------------------------------- collect

    def assemble(self) -> dict[str, Any]:
        """Read every shard and return the deterministic assembly. Writes nothing.

        Refuses: an envelope that fails validation (including ``payload_hash`` for altered payload bytes), an
        envelope of another protocol (``incompatible_shard``), an envelope whose family, variant, method or
        input differs from the planned task of its ``spec_sha256`` (``envelope_task_mismatch``), and two
        completed envelopes of one ``(spec_sha256, replicate)`` with different payload hashes
        (``duplicate_conflict``).

        Two shards that hold the same attempt number of one key with different outcomes do not refuse: each is
        an honest record of its own process (a transient failure in one worker, a completed attempt in the
        other). The completed envelope is kept, as it is across attempt numbers, and the differing outcomes are
        listed in ``attempt_outcomes_differ``.
        """
        self.check_layout()
        plan = self.read_plan()
        planned = {(t["spec_sha256"], t["replicate"]): t for t in plan["tasks"]}
        groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for path in self.envelope_files():
            rel = path.relative_to(self.run_dir).as_posix()
            try:
                doc = read_json(path)
                validate_envelope(doc, payload_root=self.run_dir)
            except Refusal as exc:
                raise Refusal(exc.code, f"{rel}: {exc}") from exc
            except ValueError as exc:
                raise Refusal("invalid_envelope", f"{rel}: not JSON: {exc}") from exc
            require(doc["protocol"]["sha256"] == plan["protocol"]["sha256"], "incompatible_shard",
                    f"{rel} belongs to another protocol hash")
            require(path.name == f"{doc['task_id']}.r{doc['replicate']}.a{doc['attempt']}.envelope.json",
                    "shard_name", f"{rel}: the file name does not match the envelope's task, replicate and attempt")
            task = planned.get((doc["spec_sha256"], doc["replicate"]))
            if task is not None:
                # The row below is filed under the envelope's own labels, so they must be the planned task's.
                spec = task["spec"]
                stated = {"family_id": doc["source"]["family_id"], "variant": doc["source"]["variant"],
                          "method": doc["method"]["id"], "prompt_sha256": doc["input"]["prompt_sha256"],
                          "token_sha256": doc["input"]["token_sha256"], "n_tokens": doc["input"]["n_tokens"]}
                wanted = {"family_id": spec["family_id"], "variant": spec["variant"], "method": spec["method"]["id"],
                          "prompt_sha256": spec["input"]["prompt_sha256"],
                          "token_sha256": spec["input"]["token_sha256"], "n_tokens": task["estimate"]["tokens"]}
                differing = sorted(key for key in wanted if stated[key] != wanted[key])
                require(not differing, "envelope_task_mismatch",
                        f"{rel}: {differing} differ from the planned task with the same spec_sha256")
            groups.setdefault((doc["spec_sha256"], doc["replicate"]), []).append({
                "path": rel, "worker": path.parent.name, "doc": doc, "sha256": sha256_file(path),
                "execution": doc["status"]["execution"],
                "payload_sha256": doc["payload"]["sha256"] if doc["payload"] else None})

        tasks, duplicate_identical, unplanned, outcomes_differ = [], [], [], []
        for key in sorted(groups, key=lambda k: (k[0][:16], k[1])):
            group = sorted(groups[key], key=lambda e: (e["doc"]["attempt"], e["worker"], e["path"]))
            name = f"task {key[0][:16]} replicate {key[1]}"
            completed = [e for e in group if e["execution"] == "completed"]
            hashes = sorted({e["payload_sha256"] for e in completed})
            if len(hashes) > 1:
                identities = sorted({str(e["doc"]["environment"].get("input_identity_sha256")) for e in completed})
                sources = {json.dumps(e["doc"]["environment"].get("source_files_sha256"), sort_keys=True)
                           for e in completed}
                cause = ("The envelopes record different input identities or adapter source hashes, so the "
                         "fixture files or the adapter changed between the attempts"
                         if len(identities) > 1 or len(sources) > 1 else
                         "The envelopes record the same input identity and adapter source hashes")
                raise Refusal("duplicate_conflict",
                              f"{name}: completed envelopes name different payload hashes {hashes} in "
                              f"{[e['path'] for e in completed]}. {cause}. No envelope is deleted or preferred "
                              "here; run the plan in a new run directory to get one result per task")
            by_attempt: dict[int, list[dict[str, Any]]] = {}
            for entry in group:
                by_attempt.setdefault(entry["doc"]["attempt"], []).append(entry)
            for number, entries in sorted(by_attempt.items()):
                if len({e["execution"] for e in entries}) > 1:
                    outcomes_differ.append({
                        "task_id": key[0][:16], "replicate": key[1], "attempt": number,
                        "outcomes": [{"worker": e["worker"], "state": e["execution"], "envelope_path": e["path"]}
                                     for e in entries]})
            if completed:
                kept, same = completed[0], completed[1:]
            else:
                last = by_attempt[max(by_attempt)]
                kept, same = last[0], [e for e in last[1:] if e["execution"] == last[0]["execution"]]
            if same:
                duplicate_identical.append({"task_id": key[0][:16], "replicate": key[1], "kept": kept["path"],
                                            "also": [e["path"] for e in same],
                                            "payload_sha256": kept["payload_sha256"]})
            doc = kept["doc"]
            row = {
                "task_id": doc["task_id"], "spec_sha256": key[0], "replicate": key[1],
                "family_id": doc["source"]["family_id"], "variant": doc["source"]["variant"],
                "method": doc["method"]["id"],
                "planned_state": planned[key]["planned_state"] if key in planned else None,
                "execution": kept["execution"], "reason": doc["status"]["reason"], "attempt": doc["attempt"],
                "worker": kept["worker"], "envelope": {"path": kept["path"], "sha256": kept["sha256"]},
                "payload": doc["payload"],
                "attempts": [{"attempt": e["doc"]["attempt"], "worker": e["worker"], "state": e["execution"],
                              "envelope_path": e["path"]} for e in group],
            }
            if key in planned:
                tasks.append(row)
            else:
                unplanned.append(row)
        missing = [{"task_id": t["task_id"], "replicate": t["replicate"], "family_id": t["spec"]["family_id"],
                    "variant": t["spec"]["variant"], "method": t["spec"]["method"]["id"],
                    "planned_state": t["planned_state"]}
                   for key, t in sorted(planned.items(), key=lambda item: (item[1]["task_id"], item[0][1]))
                   if key not in groups]
        completed_keys = {(row["spec_sha256"], row["replicate"]) for row in tasks if row["execution"] == "completed"}
        events = self.read_journal()
        index = {key: [(self.run_dir / e["path"], e["doc"]) for e in group] for key, group in groups.items()}
        uncertain = [{"task_id": e.get("task_id"), "replicate": e.get("replicate"), "attempt": e.get("attempt"),
                      "worker": e.get("worker"), "run_id": e.get("run_id"), "started_utc": e.get("utc"),
                      "a_completed_envelope_exists_for_this_task":
                          (e.get("spec_sha256"), e.get("replicate")) in completed_keys}
                     for e in self.uncertain_attempts(events, index)]
        ended_line_missing = self.ended_line_missing(events, index)
        by_state = {state: sum(1 for row in tasks if row["execution"] == state) for state in EXECUTION_STATES}
        by_state["not_run"] += len(missing)
        ready = [t for t in plan["tasks"] if t["planned_state"] == "ready"]
        ready_completed = sum(1 for t in ready if (t["spec_sha256"], t["replicate"]) in completed_keys)
        return {
            "protocol": plan["protocol"], "synthetic": plan["synthetic"],
            "plan_sha256": digest(plan),
            "tasks": tasks, "missing": missing, "unplanned": unplanned, "uncertain": uncertain,
            "ended_line_missing": ended_line_missing,
            "duplicate_identical": duplicate_identical,
            "attempt_outcomes_differ": outcomes_differ,
            "journal_unparseable_lines": [e["line"] for e in events if e.get("event") == "unparseable"],
            "by_state": by_state,
            "counts": {"planned": len(planned), "with_envelope": len(tasks), "missing": len(missing),
                       "unplanned": len(unplanned), "uncertain_attempts": len(uncertain),
                       "ended_line_missing": len(ended_line_missing),
                       "duplicate_identical": len(duplicate_identical),
                       "attempt_outcomes_differ": len(outcomes_differ),
                       "ready_planned": len(ready),
                       "ready_completed": ready_completed},
            # ``complete``: every planned task has an envelope. ``ready_complete``: every task planned as ready
            # has a completed envelope. A run can be complete and compute nothing; the second flag says so.
            "complete": not missing,
            "ready_complete": ready_completed == len(ready),
        }

    def collect(self) -> dict[str, Any]:
        """Assemble the run and write ``collected.json``. The ``assembly`` block depends only on the files in the
        run directory; the ``metrics`` block also holds this process's own timings."""
        clock = time.perf_counter()
        assembly = self.assemble()
        assemble_seconds = time.perf_counter() - clock
        events = self.read_journal()
        payload_files = sorted({row["payload"]["path"] for row in assembly["tasks"] + assembly["unplanned"]
                                if row["payload"]})
        ended_runs = {e["run_id"]: e for e in events if e.get("event") == "run_ended"}
        planned = assembly["counts"]["planned"]
        metrics = {
            "measured": True, "timing_caveat": TIMING_CAVEAT,
            "collect_stage_seconds": {"assemble_and_verify": round(assemble_seconds, 6)},
            "runs": [{"run_id": e["run_id"], "worker": e.get("worker"), "executed": e.get("executed"),
                      "reused": e.get("reused"), "stopped_early": e.get("stopped_early"),
                      "stage_seconds": e.get("stage_seconds"), "measured": True}
                     for e in events if e.get("event") == "run_ended"],
            "runs_without_end": sorted(e["run_id"] for e in events
                                       if e.get("event") == "run_started" and e["run_id"] not in ended_runs),
            "executed_attempts": sum(1 for e in events if e.get("event") == "started"),
            "reused_events": sum(1 for e in events if e.get("event") == "reused"),
            "artifact_bytes": {
                "payloads": sum((self.run_dir / p).stat().st_size for p in payload_files),
                "envelopes": sum(p.stat().st_size for p in self.envelope_files()),
                "journal": self.journal_path.stat().st_size if self.journal_path.exists() else 0,
            },
            "missingness": {"planned": planned, "missing": assembly["counts"]["missing"],
                            "fraction_missing": assembly["counts"]["missing"] / planned if planned else None},
        }
        collected = {"schema_version": COLLECTED_SCHEMA, "execution_guarantee": EXECUTION_GUARANTEE,
                     "digest_convention": "scripts.exploratory_methods.digest",
                     "assembly": assembly, "assembly_sha256": digest(assembly), "metrics": metrics}
        atomic_write_json(self.collected_path, collected)
        return collected

    def read_collected(self) -> dict[str, Any]:
        """``collected.json``, refused when it is absent or no longer matches the shards on disk."""
        require(self.collected_path.is_file(), "not_collected", f"{self.run_dir} holds no collected.json; run collect")
        collected = read_json(self.collected_path)
        require(collected.get("schema_version") == COLLECTED_SCHEMA
                and collected.get("assembly_sha256") == digest(self.assemble()), "stale_collected",
                "collected.json does not match the shards and payloads on disk; run collect again")
        return collected

    def read_payload(self, reference: Mapping[str, Any]) -> dict[str, Any]:
        """A payload by its envelope reference, with its SHA-256 checked again."""
        path = self.run_dir / reference["path"]
        require(path.is_file() and sha256_file(path) == reference["sha256"], "payload_hash",
                f"{reference['path']} is missing or its bytes changed")
        return read_json(path)


def run_fixture(plan: dict[str, Any], worker: str, *, run_dir: Path | str, fixtures_dir: Path | str,
                protocol: Mapping[str, Any], stop_after: int | None = None,
                allow_roots: Iterable[Path | str] = (), registry: Mapping[str, str] | None = None) -> dict[str, Any]:
    """``RunStore(run_dir).run_fixture(...)``: execute ready tasks in plan order, resumably."""
    return RunStore(run_dir, allow_roots=allow_roots).run_fixture(
        plan, worker, fixtures_dir=fixtures_dir, protocol=protocol, stop_after=stop_after, registry=registry)


def collect(run_dir: Path | str, *, allow_roots: Iterable[Path | str] = ()) -> dict[str, Any]:
    """``RunStore(run_dir).collect()``: the single deterministic assembler of a run directory."""
    return RunStore(run_dir, allow_roots=allow_roots).collect()
