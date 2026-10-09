#!/usr/bin/env python3
"""Owner-only: release committed CPU-logits parts for publication, or show what a release would add.

The publish chain reads a logits part (``trace_out/*/batch_summary*.json`` with ``"backend": "logits"``) only
when data/publication_release/logits_parts.json lists its path with the sha256 of its bytes
(scripts/publication_hold.py). Parts the 2026-10 backfill campaign lands are therefore held until the owner
says so ("republish only when you say so", 2026-10-09).

  python scripts/publication_release.py            # --check: what is committed but not released, and why
  python scripts/publication_release.py --release  # rewrite the manifest from the logits parts committed at HEAD

``--release`` lists every logits part git tracks under trace_out/ (models in HELD_MODELS excepted: releasing one
of those is first a reviewed edit to publication_hold.py), hashes it, and writes the manifest. It refuses when
any tracked file under trace_out/ differs from HEAD, so the manifest describes committed bytes only, and it
refuses inside the Routine's environment (PW_ROUTINE=1): neither the Routine nor scripts/backfill_chain.py ever
releases. It does not commit; the owner commits the manifest, and the next publish pools the released parts.
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
    MANIFEST_SCHEMA, RELEASE_MANIFEST, ReleaseError, is_held, is_held_run_dir, load_manifest, sha256_file)


def _git(root: Path, *argv: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *argv], capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit(f"refused: git {' '.join(argv)} failed: {proc.stderr.strip()}")
    return proc.stdout


def committed_logits_parts(root: Path) -> dict[str, str]:
    """{path: sha256} of every tracked logits part under trace_out/ outside HELD_MODELS."""
    out: dict[str, str] = {}
    for rel in sorted(_git(root, "ls-files", "-z", "--", "trace_out").split("\0")):
        path = Path(rel)
        if not rel or path.parent.parent != Path("trace_out") or not path.name.startswith("batch_summary"):
            continue
        if not path.name.endswith(".json") or is_held_run_dir(path.parent.name):
            continue
        try:
            summary = json.loads((root / path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"refused: {rel} is tracked but unreadable ({exc}); nothing was written")
        if summary.get("backend") != "logits" or is_held(summary.get("graph_model")):
            continue
        out[rel] = sha256_file(root / path)
    return out


def compare(current: dict[str, str], manifest: dict[str, str]) -> dict[str, list[str]]:
    return {"unreleased": sorted(set(current) - set(manifest)),
            "changed_since_release": sorted(p for p in set(current) & set(manifest) if current[p] != manifest[p]),
            "released_but_gone": sorted(set(manifest) - set(current))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--release", action="store_true", help="rewrite the manifest from the committed logits parts")
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
    print(f"committed logits parts: {len(current)}; released: {len(manifest)}; "
          + "; ".join(f"{k.replace('_', ' ')}: {len(v)}" for k, v in diff.items()))
    for key, paths in diff.items():
        for p in paths[:20]:
            print(f"  {key}: {p}")
        if len(paths) > 20:
            print(f"  {key}: ... and {len(paths) - 20} more")
    if not args.release:
        return 0
    if os.environ.get("PW_ROUTINE"):
        raise SystemExit("refused: releasing is the owner's action, never the Routine's (PW_ROUTINE is set)")
    dirty = _git(root, "status", "--porcelain", "--untracked-files=no", "--", "trace_out").strip()
    if dirty:
        raise SystemExit("refused: tracked files under trace_out/ differ from HEAD, so a release would not describe "
                         "committed bytes; commit or restore them first:\n" + dirty)
    doc = {"schema": MANIFEST_SCHEMA,
           "released_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "released_at_commit": _git(root, "rev-parse", "HEAD").strip(),
           "rule": "the publish chain reads a logits part only when it is listed here with the sha256 of its bytes "
                   "(scripts/publication_hold.py); written by scripts/publication_release.py --release, an owner "
                   "action",
           "count": len(current), "parts": current}
    path = root / RELEASE_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"released {len(current)} logits parts -> {path.relative_to(root)}; commit it to publish them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
