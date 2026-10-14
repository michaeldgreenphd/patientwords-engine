"""The cost sidecar of a live jev-audit run: the spend ledger's record of what the run cost.

`scripts/audit_jev_calibration.py` writes a report but no sidecar, so `scripts/ledger_update.py` could not fold its
spend (the 2026-10-12 run's $0.11 never reached the ledger). The jev-audit workflow runs this after every live run,
failure or not, and commits the sidecar on its own, the way the Petri lane commits its sidecars.

What is booked, failing closed:
- the report exists: its billed spend (`metrics.total_cost_usd`). When some calls came back without provider billing
  (`metrics.unbilled_calls_count` > 0), the report's estimate over every call (`metrics.total_estimated_cost_usd`) is
  booked when larger, so an unbilled call is never booked at zero.
- no report, but the run started (the workflow writes a start marker just before the paid step): the fire's whole
  `max_spend`, labelled `ceiling_imputed:report_missing`, because the calls made before the failure are unknown.
- no report and no start marker: nothing was called and nothing is written.

The sidecar names its billing channel (`openrouter`: the Jev decisions endpoint bills the OpenRouter key), which the
ledger would otherwise derive from model names and book to Anthropic.

    python scripts/jev_audit_sidecar.py --report artifacts/jev_pilot_report.json --out data/jev/runs/X.report.json \\
        --model typesafe/jev-1.13 --max-spend 0.10 --nonce eq01 --started-marker "$RUNNER_TEMP/jev_started" \\
        --run-utc 2026-10-14T00:00:00Z
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

BILLING_CHANNEL = "openrouter"
TASK = "jev-audit"


def _cost(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"report metrics.{field} must be a non-negative number, got {value!r}")
    return float(value)


def build_sidecar(report: dict | None, *, report_sha256: str | None, model: str, max_spend: float,
                  nonce: str | None, started: bool, run_utc: str) -> dict | None:
    """The sidecar for one live run, or None when the run made no call (no report and no start marker)."""
    base = {"task": TASK, "model": model, "billing_channel": BILLING_CHANNEL, "max_spend_usd": max_spend,
            "journal_nonce": nonce or None}
    if report is None:
        if not started:
            return None
        return {**base, "run_utc": run_utc, "cost_usd": round(max_spend, 6),
                "cost_basis": "ceiling_imputed:report_missing", "source_report_sha256": None,
                "unbilled_calls_count": None, "calls": None}
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("report has no metrics object")
    billed = _cost(metrics.get("total_cost_usd"), "total_cost_usd")
    estimated = _cost(metrics.get("total_estimated_cost_usd"), "total_estimated_cost_usd")
    unbilled = metrics.get("unbilled_calls_count")
    if isinstance(unbilled, bool) or not isinstance(unbilled, int) or unbilled < 0:
        raise ValueError(f"report metrics.unbilled_calls_count must be a non-negative integer, got {unbilled!r}")
    if unbilled:
        cost, basis = max(billed, estimated), "billed_plus_estimate_for_unbilled_calls"
    else:
        cost, basis = billed, "provider_billed"
    calls = len(report.get("cases") or []) + len(report.get("petri_cases") or [])
    stamp = (report.get("metadata") or {}).get("timestamp_utc") or run_utc
    return {**base, "run_utc": stamp, "cost_usd": round(cost, 6), "cost_basis": basis,
            "source_report_sha256": report_sha256, "unbilled_calls_count": unbilled, "calls": calls,
            "interrupted": bool((report.get("metadata") or {}).get("interrupted"))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True, help="the audit's --out-json report (may be absent after a failure)")
    ap.add_argument("--out", required=True, help="the sidecar to write, <name>.report.json")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-spend", required=True, type=float)
    ap.add_argument("--nonce", default="")
    ap.add_argument("--started-marker", required=True, help="written by the workflow just before the paid step")
    ap.add_argument("--run-utc", required=True)
    args = ap.parse_args(argv)
    if not math.isfinite(args.max_spend) or args.max_spend <= 0:
        print(f"Refused: --max-spend must be a positive finite number, got {args.max_spend}", file=sys.stderr)
        return 2
    report_path = Path(args.report)
    report = sha = None
    if report_path.is_file():
        raw = report_path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        try:
            report = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            # an unreadable report cannot bound the spend: book the ceiling, as for a missing one
            print(f"report {report_path} is unreadable ({exc}); booking the ceiling", file=sys.stderr)
            report = None
    try:
        sidecar = build_sidecar(report, report_sha256=sha, model=args.model, max_spend=args.max_spend,
                                nonce=args.nonce, started=Path(args.started_marker).is_file(), run_utc=args.run_utc)
    except ValueError as exc:
        print(f"report {report_path}: {exc}; booking the ceiling", file=sys.stderr)
        sidecar = build_sidecar(None, report_sha256=None, model=args.model, max_spend=args.max_spend,
                                nonce=args.nonce, started=True, run_utc=args.run_utc)
    if sidecar is None:
        print("no report and no start marker: the run made no call; no sidecar written")
        return 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: ${sidecar['cost_usd']:.6f} ({sidecar['cost_basis']}, {BILLING_CHANNEL})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
