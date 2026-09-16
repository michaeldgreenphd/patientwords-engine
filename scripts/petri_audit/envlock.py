"""Exact integration-environment lock: read it, digest it, and compare the
running interpreter's environment to it (docs/petri_integration_design.md
section 11). A run refuses to start on any difference; the manifest records the
lock digest under `harness.environment_lock_sha256`.

3.11-safe: the verifier only reads package metadata, so the engine's ordinary
environment can check the lock file's integrity without the harness installed.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

from .framework import ENV_LOCK, load_json

HARNESS_DISTRIBUTION = "inspect_petri"


def load_lock(path: Path | str = ENV_LOCK) -> dict:
    return load_json(path)


def lock_digest(lock: dict) -> str:
    """sha256 over the lock minus its own `lock_sha256`, the rule the lock file
    states in `sha256_rule`."""
    body = {k: v for k, v in lock.items() if k != "lock_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def installed_versions(names: list[str]) -> dict[str, str | None]:
    """{distribution: version or None when absent} for the given names."""
    out: dict[str, str | None] = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def installed_harness_commit() -> str | None:
    """The git commit the harness was installed from, read from the
    distribution's direct_url.json (pip and uv write it for VCS installs). None
    when the metadata carries no commit, which a lock verification reports as a
    difference rather than a pass."""
    try:
        dist = metadata.distribution(HARNESS_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return None
    raw = dist.read_text("direct_url.json")
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except ValueError:
        return None
    vcs = info.get("vcs_info") or {}
    commit = vcs.get("commit_id")
    return commit if isinstance(commit, str) and commit else None


@dataclass
class LockReport:
    lock_path: str
    lock_sha256: str
    digest_matches: bool
    differences: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.digest_matches and not self.differences


def verify_lock(lock: dict, *, python_version: str | None = None, versions: dict[str, str | None] | None = None,
                harness_commit: str | None = None, harness_commit_known: bool = True,
                lock_path: str = str(ENV_LOCK)) -> LockReport:
    """Compare an environment to the lock. Every difference is named; nothing
    is assumed. `harness_commit_known` False records that the environment
    cannot report its harness commit (a non-VCS install), which is itself a
    difference for a study run."""
    python_version = python_version or platform.python_version()
    names = list(lock["packages"])
    versions = versions if versions is not None else installed_versions(names)
    differences: list[str] = []
    if python_version != lock["python"]["version"]:
        differences.append(f"python {python_version} != locked {lock['python']['version']}")
    for name, want in lock["packages"].items():
        have = versions.get(name)
        if have is None:
            differences.append(f"{name}: not installed (locked {want})")
        elif have != want:
            differences.append(f"{name}: {have} != locked {want}")
    if harness_commit_known:
        commit = harness_commit if harness_commit is not None else installed_harness_commit()
        if commit is None:
            differences.append("harness commit: not recorded by the installation (not a VCS install)")
        elif commit != lock["harness"]["commit"]:
            differences.append(f"harness commit {commit} != locked {lock['harness']['commit']}")
    digest = lock_digest(lock)
    return LockReport(lock_path=lock_path, lock_sha256=lock["lock_sha256"],
                      digest_matches=(digest == lock["lock_sha256"]), differences=differences)


def report_lines(report: LockReport) -> list[str]:
    lines = [f"environment lock {report.lock_path}: digest {'ok' if report.digest_matches else 'MISMATCH'}"]
    lines += [f"  differs: {d}" for d in report.differences]
    lines.append("  verdict: " + ("match" if report.ok else "REFUSE (environment differs from the lock)"))
    return lines


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify the running environment against the Petri environment lock.")
    parser.add_argument("--lock", default=str(ENV_LOCK))
    parser.add_argument("--no-harness-commit", action="store_true",
                        help="do not require the harness commit (integrity check of the lock file only)")
    args = parser.parse_args(argv)
    lock = load_lock(args.lock)
    report = verify_lock(lock, harness_commit_known=not args.no_harness_commit, lock_path=args.lock)
    print("\n".join(report_lines(report)))
    return 0 if report.ok else 3


if __name__ == "__main__":
    sys.exit(main())
