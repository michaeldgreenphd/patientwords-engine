"""Publish every scenario's interactive trace to the companion Pages repo.

The main site ships only the N most consequential renders (exporter
--max-renders); this script gives the long tail a home: it copies each
published scenario's interactive HTML render into the patientwords-traces
repo (served by GitHub Pages) and stamps a per-scenario ``trace_url`` into
the site payload so every row can link a live trace. Owner decision
2026-07-21 ("traces available on a separate site").

Seal-safe by construction: the source of truth is the site payload — only
scenarios the exporter already published get a trace copied; nothing under
the Tier B holdout seal is reachable from here. Incremental: a render whose
destination already holds the same bytes is not re-copied, so a run touches
only new and changed renders. "Same" is decided by content, never by size or
modification time: a re-traced render can keep its byte size (found
2026-11-20, see same_content). The traces repository's nightly build has its
own copy step (.github/workflows/build.yml there); a change to this rule
belongs in both.
Refuses (exit 3, payload untouched) when the traces repo checkout is absent.
No medical vocabulary lives in this file.

Usage:
  python scripts/export_traces_site.py [--payload ../patientwords/data/simulated_scenarios.json]
      [--trace-root trace_out] [--traces-repo ../patientwords-traces]
      [--base-url https://michaeldgreenphd.github.io/patientwords-traces]
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance


_CHUNK = 1 << 20  # bytes read from each file per comparison step


def render_source(trace_root: Path, batch: str, index: int) -> Path:
    return trace_root / batch / f"index_{index:02d}.html"


def same_content(a: Path, b: Path) -> bool:
    """True when the two files hold the same bytes.

    A different size proves different content, so it is checked first and
    nothing is read. An equal size proves nothing. Found 2026-11-20: equal
    size (with a destination no older than the source) counted as unchanged,
    and t/pairs_20260719T132706Z/index_44.html in the traces repository
    stayed at an earlier trace of the same 1,615,110 bytes. Equal-sized files
    are therefore read in full. Modification times are not consulted: a
    checkout sets them to the checkout time."""
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as file_a, b.open("rb") as file_b:
        while True:
            chunk_a, chunk_b = file_a.read(_CHUNK), file_b.read(_CHUNK)
            if chunk_a != chunk_b:
                return False
            if not chunk_a:
                return True


def publish(payload: dict, trace_root: Path, traces_repo: Path | None, base_url: str):
    """Copy renders + stamp trace_url; returns (copied, unchanged, missing).

    A destination counts as unchanged only when it holds the source's bytes
    (same_content); any other existing destination is overwritten.

    ``traces_repo=None`` is stamp-only: set trace_url for every scenario whose
    render exists locally, copying nothing — for when the traces repo builds
    itself in its own CI (same payload + same render set, so the same URLs)."""
    copied = unchanged = missing = 0
    for s in payload.get("scenarios", []):
        batch, index = s.get("batch"), s.get("batch_index")
        if not batch or not isinstance(index, int):
            missing += 1
            continue
        src = render_source(trace_root, batch, index)
        if not src.is_file():
            missing += 1
            continue
        rel = f"t/{batch}/{src.name}"
        if traces_repo is None:
            unchanged += 1
        else:
            dst = traces_repo / rel
            if dst.is_file() and same_content(src, dst):
                unchanged += 1
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        s["trace_url"] = f"{base_url.rstrip('/')}/{rel}"
    return copied, unchanged, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--payload", default="../patientwords/data/simulated_scenarios.json")
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--traces-repo", default="../patientwords-traces")
    parser.add_argument("--base-url",
                        default="https://michaeldgreenphd.github.io/patientwords-traces")
    parser.add_argument("--stamp-only", action="store_true",
                        help="only stamp trace_url into the payload (no copying, no traces "
                             "checkout needed) - for when the traces repo builds itself in "
                             "its own CI from the same payload + render set")
    args = parser.parse_args(argv)

    traces_repo: Path | None = None
    if not args.stamp_only:
        traces_repo = Path(args.traces_repo)
        if not (traces_repo / ".git").exists():
            print(f"refused: traces repo checkout not found at {traces_repo} - payload untouched")
            return 3

    payload_path = Path(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    copied, unchanged, missing = publish(payload, Path(args.trace_root), traces_repo,
                                         args.base_url)
    payload["traces_site"] = {
        "base_url": args.base_url.rstrip("/"),
        "_provenance": provenance("export_traces_site.py"),
    }
    payload_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    dest = "stamp-only (no copy)" if traces_repo is None else f"-> {traces_repo}"
    print(f"traces site: {copied} copied, {unchanged} stamped/unchanged, {missing} without a "
          f"render {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
