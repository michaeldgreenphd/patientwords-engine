"""Fail-closed manual CI preparation; no runtime imports in readiness checks."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import urllib.request
from typing import Any

try:
    from scripts.exploratory_baseline_preflight import Refusal, ROOT, digest, read_plan
except ModuleNotFoundError:
    from exploratory_baseline_preflight import Refusal, ROOT, digest, read_plan

OWNER = "michaeldgreenphd"
ENGINE_REPO = f"{OWNER}/patientwords-engine"
CAUSALAB_REPO = f"{OWNER}/patient-words-causalab"
READINESS_SCHEMA = "patientwords.baseline-ci-readiness/1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
SAFE_FILES = re.compile(
    r"(?:config\.json|generation_config\.json|tokenizer\.json|tokenizer_config\.json|"
    r"special_tokens_map\.json|vocab\.json|merges\.txt|model\.safetensors\.index\.json|"
    r"model(?:-\d{5}-of-\d{5})?\.safetensors)\Z"
)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object or return an explicit format refusal."""
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Refusal("invalid_json_object", path.name)
    return value


def sha256(path: Path) -> str:
    """Hash a file without retaining the full payload in memory."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def external_directory(path: Path, *, create: bool = False) -> Path:
    """Refuse outputs in a checkout, including symlink aliases."""
    resolved = path.resolve()
    if any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
        raise Refusal("repository_output", "use a fresh external run directory")
    if create:
        resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def write_receipt(path: Path, value: dict[str, Any]) -> None:
    """Write a new external receipt; never overwrite an earlier attempt."""
    external_directory(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def dispatch_context(env: dict[str, str]) -> str:
    """Only the owner's manual dispatch of the default-branch workflow can execute."""
    checks = {
        "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": ENGINE_REPO, "GITHUB_REF": "refs/heads/main",
        "GITHUB_ACTOR": OWNER, "GITHUB_TRIGGERING_ACTOR": OWNER,
        "GITHUB_WORKFLOW_REF": f"{ENGINE_REPO}/.github/workflows/exploratory_baseline_preflight.yml@refs/heads/main",
    }
    if any(env.get(key) != value for key, value in checks.items()):
        raise Refusal("untrusted_dispatch", "owner/default-branch manual dispatch required")
    commit = env.get("GITHUB_SHA", "")
    if not SHA.fullmatch(commit):
        raise Refusal("missing_engine_commit", "the dispatch must identify one exact commit")
    return commit


def readiness(record: dict[str, Any], plan: dict[str, Any], now: datetime) -> list[str]:
    """List every unmet execution prerequisite without installing or downloading."""
    if record.get("schema_version") != READINESS_SCHEMA:
        raise Refusal("readiness_schema_mismatch", READINESS_SCHEMA)
    missing = []
    if record.get("expected_runtime_versions") != plan["environments"]:
        missing.append("runtime_build_declaration_mismatch")
    if record.get("status") != "reviewed_ready_for_owner_dispatch":
        missing.append("execution_not_approved")
    if not isinstance(record.get("causalab_commit"), str) or not SHA.fullmatch(record["causalab_commit"]):
        missing.append("reviewed_causalab_commit_missing")
    runner = record.get("runner")
    if not isinstance(runner, dict) or (
        not isinstance(runner.get("id"), int) or isinstance(runner.get("id"), bool) or runner["id"] <= 0
        or not isinstance(runner.get("labels"), list)
        or not {"self-hosted", "Linux", "X64"}.issubset(runner["labels"])
        or len(runner["labels"]) < 4
        or any(not isinstance(x, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", x) for x in runner["labels"])
        or not isinstance(runner.get("name"), str) or not runner["name"]
        or not runner.get("capacity_evidence")
    ):
        missing.append("suitable_existing_runner_unestablished")
    budget = record.get("runner_budget")
    if not isinstance(budget, dict) or (
        budget.get("billable") is not False or budget.get("total_budget_usd") != 0
        or not budget.get("approval_reference") or budget.get("provider_budget_usd") != 0
    ):
        missing.append("zero_cost_runner_budget_unestablished")
    if record.get("linux_runtime_reviewed") is not True:
        missing.append("linux_runtime_setup_not_reviewed")
    seal = record.get("current_seal_attestation")
    try:
        stamp = datetime.fromisoformat(seal["checked_at_utc"].replace("Z", "+00:00"))
        seal_valid = (
            seal["status"] == "clean" and seal["source_spec_sha256"] == plan["source_spec"]["sha256"]
            and re.fullmatch(r"[0-9a-f]{64}", seal["artifact_sha256"]) and seal["review_reference"]
            and stamp.tzinfo is not None and timedelta(0) <= now - stamp <= timedelta(hours=24)
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        seal_valid = False
    if not seal_valid:
        missing.append("current_seal_attestation_missing")
    return missing


def api_json(url: str) -> dict[str, Any]:
    """Read public metadata without using a credential or accepting arbitrary hosts."""
    if not url.startswith(("https://api.github.com/repos/", "https://huggingface.co/api/models/")):
        raise Refusal("unsupported_metadata_host", "only public repository metadata is used")
    request = urllib.request.Request(url, headers={"User-Agent": "PatientWords-baseline-preflight/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise Refusal("metadata_format", "expected an object")
    return value


def trusted_commit(repository: str, commit: str) -> dict[str, Any]:
    """Require the exact code to have reached the owner's reviewed default branch."""
    if repository not in (ENGINE_REPO, CAUSALAB_REPO) or not SHA.fullmatch(commit):
        raise Refusal("unsupported_code_source", "owner repositories and full commits only")
    root = f"https://api.github.com/repos/{repository}"
    if api_json(root).get("default_branch") != "main":
        raise Refusal("default_branch_changed", repository)
    value = api_json(f"{root}/compare/{commit}...main")
    if (value.get("status") not in ("ahead", "identical") or value.get("base_commit", {}).get("sha") != commit
            or value.get("merge_base_commit", {}).get("sha") != commit):
        raise Refusal("unreviewed_code_commit", repository)
    return {"repository": repository, "commit": commit, "default_branch_ancestry": "verified"}


def effective_capacity(memory: int, available: int, cpus: int, free_disk: int,
                       cgroup_limits: list[tuple[int | None, int | None, float | None]],
                       requirements: dict[str, Any]) -> dict[str, Any]:
    """Apply all enclosing cgroup limits; swap never contributes to RAM."""
    for limit, used, quota in cgroup_limits:
        if limit is not None:
            if limit <= 0 or used is None or used < 0:
                raise Refusal("invalid_cgroup_limit", "memory limit/current unavailable")
            memory = min(memory, limit)
            available = min(available, max(0, limit - used))
        if quota is not None:
            if quota <= 0:
                raise Refusal("invalid_cgroup_limit", "CPU quota must be positive")
            cpus = min(cpus, int(quota))
    result = {"effective_ram_bytes": memory, "available_ram_bytes": available,
              "effective_logical_cpus": cpus, "free_disk_bytes": free_disk, "swap_counted": False}
    if (memory < requirements["minimum_ram_bytes"] or available < requirements["minimum_ram_bytes"] // 2
            or cpus < requirements["minimum_logical_cpus"] or free_disk < requirements["minimum_free_disk_bytes"]):
        raise Refusal("insufficient_capacity", json.dumps(result, sort_keys=True))
    return result


def measure_capacity(path: Path, requirements: dict[str, Any]) -> dict[str, Any]:
    """Measure the actual Linux allocation before dependency or weight downloads."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise Refusal("unsupported_runner", "Linux x86_64 CPU runner required")
    info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    memory = int(info["MemTotal"].split()[0]) * 1024
    available = int(info["MemAvailable"].split()[0]) * 1024
    cpus = len(os.sched_getaffinity(0))
    groups = Path("/proc/self/cgroup").read_text().splitlines()
    unified = [line[3:] for line in groups if line.startswith("0::")]
    if len(unified) != 1 or any(".." == part for part in Path(unified[0]).parts):
        raise Refusal("unsupported_cgroup_layout", "review this allocation before execution")
    base = Path("/sys/fs/cgroup")
    node = base / unified[0].lstrip("/")
    if not node.is_dir():
        raise Refusal("unknown_cgroup_allocation", "cannot establish the effective allocation")
    limits = []
    for ancestor in (node, *node.parents):
        if not ancestor.is_relative_to(base):
            break
        limit, current, quota = None, None, None
        if (ancestor / "memory.max").exists():
            raw = (ancestor / "memory.max").read_text().strip()
            if raw != "max":
                limit = int(raw)
                current = int((ancestor / "memory.current").read_text())
        if (ancestor / "cpu.max").exists():
            value, period = (ancestor / "cpu.max").read_text().split()
            if value != "max":
                quota = int(value) / int(period)
        limits.append((limit, current, quota))
    return effective_capacity(memory, available, cpus, shutil.disk_usage(path).free, limits, requirements)


def model_files(metadata: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Preview a bounded safe-format file inventory before any model download."""
    if metadata.get("sha") != plan["model"]["revision"] or metadata.get("id") != plan["model"]["id"]:
        raise Refusal("model_metadata_mismatch", "immutable model revision differs")
    rows = []
    for item in metadata.get("siblings", []):
        name = item.get("rfilename", "")
        if not isinstance(name, str) or not SAFE_FILES.fullmatch(name):
            continue
        size = item.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise Refusal("unknown_download_size", name)
        lfs = item.get("lfs", {})
        sha = lfs.get("sha256")
        if name.endswith(".safetensors") and (
            not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha) or lfs.get("size") != size
        ):
            raise Refusal("missing_weight_digest", name)
        rows.append({"path": name, "size": size, "expected_sha256": sha})
    names = {row["path"] for row in rows}
    if (len(names) != len(rows) or not {"config.json", "tokenizer.json", "tokenizer_config.json"} <= names
            or not any(name.endswith(".safetensors") for name in names)):
        raise Refusal("incomplete_download_inventory", "config, tokenizer and safe weights are required")
    if sum(row["size"] for row in rows) > plan["resources"]["maximum_model_download_bytes"]:
        raise Refusal("download_cap_exceeded", "stop before staging weights")
    return sorted(rows, key=lambda row: row["path"])


def runtime_receipt(plan: dict[str, Any], backend: str, versions: dict[str, str],
                    python_version: str) -> dict[str, Any]:
    """Verify exact distribution build strings before weights are staged."""
    if backend not in plan["environments"]:
        raise Refusal("unsupported_backend", "a declared independent environment is required")
    if versions != plan["environments"][backend] or python_version != plan["runtime_python_version"]:
        raise Refusal("runtime_build_mismatch", json.dumps({"backend": backend, "versions": versions,
                                                          "python_version": python_version}, sort_keys=True))
    return {"schema_version": "patientwords.baseline-runtime/1", "backend": backend, "versions": versions,
            "python_version": python_version, "plan_sha256": digest(plan)}


def require_runtime_receipts(plan: dict[str, Any], directory: Path) -> None:
    """Require both checked environments before the model download API is called."""
    for backend in ("engine", "causalab"):
        path = directory / f"{backend}.runtime.json"
        if not path.is_file():
            raise Refusal("runtime_check_missing", backend)
        record = read_json(path).get("runtime", {})
        expected = runtime_receipt(plan, backend, record.get("versions", {}), record.get("python_version", ""))
        if record != expected:
            raise Refusal("runtime_receipt_mismatch", backend)


def stage_model(plan: dict[str, Any], cache: Path, out: Path) -> None:
    """Future CI stage only: preview, stage pinned safe files, then verify all bytes."""
    dispatch_context(dict(os.environ))
    measure_capacity(out.parent, plan["resources"])
    require_runtime_receipts(plan, out.parent)
    external_directory(cache)
    url = f"https://huggingface.co/api/models/{plan['model']['id']}/revision/{plan['model']['revision']}?blobs=true"
    rows = model_files(api_json(url), plan)
    required_disk = plan["resources"]["minimum_free_disk_bytes"] + sum(row["size"] for row in rows)
    if shutil.disk_usage(out.parent).free < required_disk:
        raise Refusal("insufficient_staging_reserve", "safe-file download must leave the declared free-disk reserve")
    write_receipt(out.parent / "download_preview.json", {"model": plan["model"], "files": rows})
    from huggingface_hub import snapshot_download
    snapshot = Path(snapshot_download(repo_id=plan["model"]["id"], revision=plan["model"]["revision"],
                                      cache_dir=str(cache), allow_patterns=[row["path"] for row in rows],
                                      token=False, max_workers=2))
    for row in rows:
        path = snapshot / row["path"]
        if not path.resolve().is_relative_to(cache.resolve()) or path.stat().st_size != row["size"]:
            raise Refusal("download_size_mismatch", row["path"])
        actual = sha256(path)
        if row["expected_sha256"] is not None and actual != row["expected_sha256"]:
            raise Refusal("download_digest_mismatch", row["path"])
        row["actual_sha256"] = actual
        path.chmod(0o444)
    write_receipt(out, {"model": plan["model"], "files": rows, "status": "integrity_verified"})


def main() -> int:
    """Expose dry readiness separately from explicitly gated CI operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("readiness", "capacity", "environment", "stage-model"), default="readiness")
    parser.add_argument("--record", type=Path, default=ROOT / "data/exploratory/baseline_ci_readiness.v1.json")
    parser.add_argument("--plan", type=Path, default=ROOT / "data/exploratory/baseline_preflight.v1.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backend", choices=("engine", "causalab"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        plan, _ = read_plan(args.plan)
        record = read_json(args.record)
        missing = readiness(record, plan, datetime.now(timezone.utc))
        result: dict[str, Any] = {"status": "blocked" if missing else "prepared_not_executed", "blockers": missing}
        if args.execute or args.mode != "readiness":
            engine = dispatch_context(dict(os.environ))
            if missing:
                raise Refusal("execution_prerequisites_missing", ", ".join(missing))
            sources = [trusted_commit(ENGINE_REPO, engine), trusted_commit(CAUSALAB_REPO, record["causalab_commit"])]
            result.update({"sources": sources, "status": "ready_for_manual_execution"})
            if args.out is None:
                raise Refusal("missing_receipt_path", "an external receipt is required")
            if args.mode != "readiness" and os.environ.get("RUNNER_NAME") != record["runner"]["name"]:
                raise Refusal("runner_identity_mismatch", "actual runner differs from reviewed inventory")
            if args.mode == "capacity":
                result["capacity"] = measure_capacity(args.out.parent, plan["resources"])
            if args.mode == "environment":
                if args.backend is None:
                    raise Refusal("missing_backend", "environment check requires a backend")
                try:
                    versions = {name: importlib.metadata.version(name) for name in plan["environments"][args.backend]}
                except importlib.metadata.PackageNotFoundError as exc:
                    raise Refusal("runtime_package_missing", str(exc.name)) from exc
                result["runtime"] = runtime_receipt(plan, args.backend, versions, platform.python_version())
            if args.mode == "stage-model":
                if args.cache is None:
                    raise Refusal("missing_cache_path", "an external cache is required")
                stage_model(plan, args.cache, args.out)
                return 0
            if args.mode == "readiness":
                write_receipt(args.out.parent / "execution.json", {
                    "schema_version": "patientwords.baseline-execution/1",
                    "commits": {"engine": engine, "causalab": record["causalab_commit"]},
                })
        if args.out is not None:
            write_receipt(args.out, result)
        if args.github_output is not None:
            with args.github_output.open("a") as stream:
                stream.write(f"ready={'true' if args.execute and not missing else 'false'}\n")
                if args.execute and not missing:
                    stream.write(f"runner_labels={json.dumps(record['runner']['labels'])}\n")
                    stream.write(f"causalab_commit={record['causalab_commit']}\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
        value = {"status": "refused", "code": getattr(exc, "code", "preparation_error"), "message": str(exc)}
        if args.out is not None and not args.out.exists():
            write_receipt(args.out, value)
        print(json.dumps(value, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
