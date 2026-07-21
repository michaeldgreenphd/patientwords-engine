"""Holdout-seal integrity check (audit 2026-07-21, R-C folded into the daily cycle).

Recomputes the Tier B sealed set via tierb_split (Amendment 1 split, Amendment 3
phrase-keyed widening) and sweeps published artifacts for any sealed phrase, by
exact and whitespace/case-normalized substring match. The report NEVER contains
phrase text — hits are path + batch#index + count only (the report must not
become the leak).

Exit codes: 0 clean, 1 leak found, 2 configuration problem (e.g. the sealed set
computes EMPTY — a main checkout's null tierb.start_utc does that; run from the
ops-truth working branch, audit drift-register 1).

Usage:
  python scripts/seal_check.py [--site ../patientwords] [--dashboard ops/dashboard.json]
      [--simulated data/simulated] [--extra docs,ops]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:  # invoked from the repo root (CLI/cycle) vs loaded by path (tests)
    from scripts.tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp

SCAN_SUFFIXES = {".json", ".html", ".md", ".csv", ".txt", ".yml"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def sealed_registry(simulated_dir: str, dashboard_path: str) -> dict[str, str]:
    """sealed phrase -> 'batch#index' label (labels only ever leave this module)."""
    start = tierb_start_stamp(dashboard_path)
    registry: dict[str, str] = {}
    if not start:
        return registry
    for bp in sorted(Path(simulated_dir).glob("pairs_*.json")):
        if bp.name.endswith(".report.json") or not is_tierb_batch(bp.stem, start):
            continue
        try:
            pairs = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for i, pair in enumerate(pairs, start=1):
            phrase = (pair.get("top_prompt") or "").strip()
            if phrase and is_holdout(phrase):
                registry[phrase] = f"{bp.stem}#{i}"
    return registry


def scan_file(path: Path, registry: dict[str, str]) -> list[str]:
    """batch#index labels of sealed phrases found in this file (never the text)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    lowered = norm(text)
    hits = []
    for phrase, label in registry.items():
        if phrase in text or norm(phrase) in lowered:
            hits.append(label)
    return hits


def scan_roots(roots: list[Path], registry: dict[str, str],
               exclude_parts: tuple[str, ...] = ("modes", ".git", "trace_out",
                                                 "data/simulated")) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    for root in roots:
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = [p for p in root.rglob("*") if p.suffix in SCAN_SUFFIXES]
        else:
            continue
        for p in candidates:
            rel = str(p)
            if any(part in rel for part in exclude_parts):
                continue  # the registry's own source files are not leaks
            hits = scan_file(p, registry)
            if hits:
                findings[rel] = sorted(hits)
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="../patientwords")
    parser.add_argument("--dashboard", default="ops/dashboard.json")
    parser.add_argument("--simulated", default="data/simulated")
    parser.add_argument("--extra", default="docs,ops",
                        help="comma-separated extra engine roots to sweep")
    args = parser.parse_args(argv)

    registry = sealed_registry(args.simulated, args.dashboard)
    if not registry:
        print("seal check: CONFIG ERROR - sealed set computed EMPTY (null tierb.start_utc? "
              "wrong branch?). Run from the ops-truth working branch.")
        return 2

    roots = [Path(args.site)] + [Path(x.strip()) for x in args.extra.split(",") if x.strip()]
    findings = scan_roots(roots, registry)
    if findings:
        print(f"seal check: LEAK - {sum(len(v) for v in findings.values())} sealed-phrase "
              f"hit(s) in {len(findings)} file(s):")
        for path, labels in sorted(findings.items()):
            print(f"  {path} :: {', '.join(labels)}")
        print("Breach protocol: stop publishing, follow the 2026-07-14 remediation "
              "precedent, put the hit list (paths+labels only) in the digest headline.")
        return 1
    print(f"seal check: CLEAN - {len(registry)} sealed phrases, no hits across "
          f"{len(roots)} root(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
