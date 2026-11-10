#!/usr/bin/env python3
"""Advance the logits input pin of the study-interim membership, or show what an advance would add.

Under the open-results policy (scripts/results_policy.py, docs/open_results_policy.md) this manifest is not a
publication gate: a part that is absent from it is public in the results catalogue. It is the input pin of the
``study-interim/1`` analysis membership. The collectors that compute the published statistics read a CPU-logits
part (``trace_out/*/batch_summary*.json`` with ``"backend": "logits"``) only when
data/publication_release/logits_parts.json lists its path with the sha256 of its bytes, so a statistic changes
only when the pin is advanced on purpose.

  python scripts/publication_release.py                        # --check: what is committed but not pinned
  python scripts/publication_release.py --release              # pin every eligible committed logits part
  python scripts/publication_release.py --release --models qwen3-4b,olmo-2-1b   # pin only these models' new parts

``--release`` lists the logits parts git tracks under trace_out/ that the membership could admit (its excluded
model cohorts and stimulus classes are left out: including one of those is a reviewed edit of
data/results_policy/policy.v1.json, not a pin), hashes them, and writes the manifest. Entries already pinned
are always kept; ``--models`` limits which models' new parts are added, so adding one model no longer pins
every other model's backfill in the same action. It refuses when any tracked file under trace_out/ differs
from HEAD, so the manifest describes committed bytes only.

Advancing the pin changes the published statistics at the next publish. Record the new state as a versioned
snapshot in the same change: ``python scripts/results_snapshot.py create --id study-interim-<date> --supersedes
<previous id> --change "<what was added>"``. Inside the Routine's environment (PW_ROUTINE=1) the advance is
refused unless the policy file's ``analysis_pin.auto_advance`` is true; that flag and its release condition are
the one remaining control on this step, and they are stated in the policy file. It does not commit.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from publication_hold import (  # noqa: E402  (script-style module)
    MANIFEST_SCHEMA, RELEASE_MANIFEST, ReleaseError, is_exploratory_run_dir, is_held, is_held_run_dir,
    load_manifest, load_policy, sha256_file)


def _git(root: Path, *argv: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *argv], capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit(f"refused: git {' '.join(argv)} failed: {proc.stderr.strip()}")
    return proc.stdout


def committed_logits_parts(root: Path) -> dict[str, str]:
    """{path: sha256} of every tracked logits part under trace_out/ that the default membership could admit:
    parts of an excluded model cohort or stimulus class are left out (a pin could never admit them)."""
    out: dict[str, str] = {}
    for rel in sorted(_git(root, "ls-files", "-z", "--", "trace_out").split("\0")):
        path = Path(rel)
        if not rel or path.parent.parent != Path("trace_out") or not path.name.startswith("batch_summary"):
            continue
        if not path.name.endswith(".json") or is_held_run_dir(path.parent.name):
            continue
        if is_exploratory_run_dir(path.parent.name):
            continue
        try:
            summary = json.loads((root / path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"refused: {rel} is tracked but unreadable ({exc}); nothing was written")
        backend = summary.get("backend")
        if backend is None:
            raise SystemExit(f"refused: {rel} is missing required 'backend' key; nothing was written")
        if backend in ("hosted", "activation_patch"):
            continue
        if backend != "logits":
            raise SystemExit(f"refused: {rel} has unrecognized backend {backend!r}; nothing was written")
        if is_held(summary.get("graph_model")):
            continue
        out[rel] = sha256_file(root / path)
    return out


def compare(current: dict[str, str], manifest: dict[str, str]) -> dict[str, list[str]]:
    return {"unreleased": sorted(set(current) - set(manifest)),
            "changed_since_release": sorted(p for p in set(current) & set(manifest) if current[p] != manifest[p]),
            "released_but_gone": sorted(set(manifest) - set(current))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--release", action="store_true", help="pin the eligible committed logits parts")
    ap.add_argument("--models", default="",
                    help="with --release: add new parts of these comma-separated models only; parts already "
                         "pinned are kept whatever this names")
    ap.add_argument("--repo", default=str(ENGINE), help="engine repository root (default: this checkout)")
    args = ap.parse_args(argv)
    root = Path(args.repo).resolve()
    current = committed_logits_parts(root)
    try:
        manifest = load_manifest(root)
    except ReleaseError as exc:
        if not args.release:
            raise SystemExit(f"refused: {exc}")
        manifest = {}
    diff = compare(current, manifest)
    print(f"committed logits parts the membership could admit: {len(current)}; pinned: {len(manifest)}; "
          + "; ".join(f"{k.replace('_', ' ')}: {len(v)}" for k, v in diff.items()))
    for key, paths in diff.items():
        for p in paths[:20]:
            print(f"  {key}: {p}")
        if len(paths) > 20:
            print(f"  {key}: ... and {len(paths) - 20} more")
    if not args.release:
        return 0
    pin = load_policy().doc.get("analysis_pin") or {}
    if os.environ.get("PW_ROUTINE") and not pin.get("auto_advance"):
        raise SystemExit("refused: never the Routine's action while analysis_pin.auto_advance is false in "
                         "data/results_policy/policy.v1.json (PW_ROUTINE is set). Release condition: "
                         + str(pin.get("release_condition")))
    dirty = _git(root, "status", "--porcelain", "--untracked-files=no", "--", "trace_out").strip()
    if dirty:
        raise SystemExit("refused: tracked files under trace_out/ differ from HEAD, so a release would not describe "
                         "committed bytes; commit or restore them first:\n" + dirty)
    only = {m.strip() for m in args.models.split(",") if m.strip()}
    if only:
        added = {p: h for p, h in current.items() if p not in manifest
                 and Path(p).parent.name.partition("__")[2] in only}
        changed = sorted(p for p in manifest if p in current and current[p] != manifest[p])
        if changed:
            raise SystemExit("refused: pinned parts differ from HEAD, so a scoped advance would keep stale "
                             "hashes: " + ", ".join(changed[:5]))
        current = {**{p: h for p, h in manifest.items() if p in current}, **added}
        print(f"scoped to {sorted(only)}: {len(added)} new part(s) pinned, {len(manifest)} kept")
    doc = {"schema": MANIFEST_SCHEMA,
           "released_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "released_at_commit": _git(root, "rev-parse", "HEAD").strip(),
           "rule": "input pin of the study-interim/1 analysis membership: its collectors read a logits part only "
                   "when it is listed here with the sha256 of its bytes (scripts/results_policy.py). A part "
                   "absent from this file is not hidden; the results catalogue lists it. Written by "
                   "scripts/publication_release.py --release",
           "count": len(current), "parts": current}
    path = root / RELEASE_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"pinned {len(current)} logits parts -> {path.relative_to(root)}; commit it with a new snapshot "
          "(scripts/results_snapshot.py create) so the statistics change is versioned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
