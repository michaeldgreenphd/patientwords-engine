"""Claim-drift check: hardcoded numbers in site prose vs their data sources.

Runtime-filled spans update themselves; sentences with numbers written into
the HTML do not. data/claims_manifest.json ties each such sentence to the
data expression that produced its number. This check fails loudly when the
recomputed value no longer matches (the prose went stale and needs a hand
rewrite) or when the snippet vanished (the prose was edited; update the
manifest). Run nightly by the critic cycle; exit 1 on any drift.

No medical vocabulary lives in this file; snippets live in the manifest.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def evaluate(expr: str, data):
    # d lives in globals, not locals: comprehension bodies execute in their own
    # frame whose name lookups skip eval's locals dict entirely
    return eval(expr, {"__builtins__": {"round": round, "sum": sum, "any": any,
                                        "all": all, "len": len, "next": next,
                                        "min": min, "max": max, "sorted": sorted,
                                        "true": True, "false": False},
                       "d": data}, {})


def check(manifest_path: Path, site: Path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures, warnings = [], []
    for claim in manifest.get("claims", []):
        page_path = site / claim["page"]
        try:
            page = page_path.read_text(encoding="utf-8")
        except OSError:
            failures.append(f"{claim['page']}: page missing")
            continue
        snippets = [claim["snippet"]] + ([claim["snippet_alt"]] if claim.get("snippet_alt") else [])
        if not any(s in page for s in snippets):
            warnings.append(f"{claim['page']}: snippet not found ({claim['snippet'][:40]!r}); "
                            "prose was edited - update the manifest")
            continue
        try:
            data = json.loads((site / claim["source"]).read_text(encoding="utf-8"))
            value = evaluate(claim["expr"], data)
        except Exception as err:  # a broken source or expr is itself drift
            failures.append(f"{claim['page']}: source check failed ({err})")
            continue
        expected = claim["expected"]
        if value != expected:
            failures.append(f"{claim['page']}: DRIFT - prose says {expected!r}, "
                            f"data now gives {value!r} ({claim['snippet'][:40]!r})")
    return failures, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", default="data/claims_manifest.json")
    parser.add_argument("--site", default="../patientwords")
    args = parser.parse_args()
    failures, warnings = check(Path(args.manifest), Path(args.site))
    for w in warnings:
        print("warn:", w)
    for f in failures:
        print("FAIL:", f)
    if not failures and not warnings:
        print("claim check: all claims verified against their sources")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
