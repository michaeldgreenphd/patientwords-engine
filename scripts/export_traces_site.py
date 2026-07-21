"""Publish every scenario's interactive trace to the companion Pages repo.

The main site ships only the N most consequential renders (exporter
--max-renders); this script gives the long tail a home: it copies each
published scenario's interactive HTML render into the patientwords-traces
repo (served by GitHub Pages) and stamps a per-scenario ``trace_url`` into
the site payload so every row can link a live trace. Owner decision
2026-07-21 ("traces available on a separate site").

Seal-safe by construction: the source of truth is the site payload — only
scenarios the exporter already published get a trace copied; nothing under
the Tier B holdout seal is reachable from here. Incremental: unchanged
renders are not re-copied, so the nightly run touches only new batches.
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


def render_source(trace_root: Path, batch: str, index: int) -> Path:
    return trace_root / batch / f"index_{index:02d}.html"


def publish(payload: dict, trace_root: Path, traces_repo: Path, base_url: str):
    """Copy renders + stamp trace_url; returns (copied, unchanged, missing)."""
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
        dst = traces_repo / rel
        if dst.is_file() and dst.stat().st_size == src.stat().st_size \
                and dst.stat().st_mtime >= src.stat().st_mtime:
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
    args = parser.parse_args(argv)

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
    print(f"traces site: {copied} copied, {unchanged} unchanged, {missing} without a render "
          f"-> {traces_repo} (commit+push there, then the payload's trace_url links go live)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
