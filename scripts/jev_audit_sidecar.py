"""The cost sidecar of a live jev-audit run: the spend ledger's record of what the run cost.

`scripts/audit_jev_calibration.py` writes a report but no sidecar, so `scripts/ledger_update.py` could not fold its
spend (the 2026-10-12 run's $0.11 never reached the ledger). The jev-audit workflow runs this after every live run,
failure or not, and commits the sidecar on its own, the way the Petri lane commits its sidecars.

What is booked, failing closed. The booking is made from the report's rows, which must account for its totals
(`metrics.total_cost_usd` and `metrics.unbilled_calls_count`):
- each billed call (a row with `cost_usd`) at its billed cost, and each unbilled call (`cost_usd` null) at its own
  list-price estimate (`estimated_cost_usd`), so an unbilled call is never booked at zero (Codex review of PR #110:
  the earlier max(billed, estimate over all calls) could fall below billed plus the unbilled calls' estimates).
- an unbilled call whose estimate is zero or absent (the client defaults the estimate to zero when the response
  carries no token counts) cannot be priced, so the whole `max_spend` is booked.
- a resumed run (the workflow restored an earlier run's checkpoint): only the rows this run scored, when the earlier
  run's own cost sidecar is on the branch (`--resumed-source-sidecar`, a jev-audit sidecar), since that sidecar booked
  the restored rows and the runner folds them, and their cost, into this report. When it is absent (its commit
  failed, or the run was on another ref), the restored rows are booked here too, so their spend is not lost (Codex
  review of PR #110).
- the report is marked interrupted (the runner writes a partial report when a call raised or the ceiling stopped it):
  at least the whole `max_spend`, because the call that failed may have been billed and is in no row.
- no report, but the run started (the workflow writes a start marker just before the paid step): the fire's whole
  `max_spend`, labelled `ceiling_imputed:report_missing`, because the calls made before the failure are unknown.
- no report and no start marker: nothing was called and nothing is written.

The sidecar names its billing channel (`openrouter`: the Jev decisions endpoint bills the OpenRouter key), which the
ledger would otherwise derive from model names and book to Anthropic.

    python scripts/jev_audit_sidecar.py --report artifacts/jev_pilot_report.json --out data/jev/runs/X.report.json \\
        --model typesafe/jev-1.13 --max-spend 0.10 --nonce eq01 --started-marker "$RUNNER_TEMP/jev_started" \\
        --run-utc 2026-10-14T00:00:00Z [--resumed-checkpoint restored.json --resumed-run-id 123]
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
        raise ValueError(f"report {field} must be a non-negative number, got {value!r}")
    return float(value)


def _row_key(row: dict, phase: str) -> tuple:
    """A row's identity in a report and in a checkpoint: an advice case by id, a Petri row by conversation and turn."""
    if phase == "advice":
        return ("advice", row.get("id"))
    return ("petri", row.get("conversation_id"), row.get("turn_index"))


def _keyed_rows(doc: dict, fields: tuple[tuple[str, str], ...], what: str) -> list[tuple[tuple, dict]]:
    rows: list[tuple[tuple, dict]] = []
    for field, phase in fields:
        part = doc.get(field, [])
        if not isinstance(part, list) or not all(isinstance(r, dict) for r in part):
            raise ValueError(f"{what} {field} must be a list of objects")
        rows.extend((_row_key(r, phase), r) for r in part)
    return rows


def build_sidecar(report: dict | None, *, report_sha256: str | None, model: str, max_spend: float,
                  nonce: str | None, started: bool, run_utc: str, resumed: dict | None = None,
                  resumed_run_id: str | None = None) -> dict | None:
    """The sidecar for one live run, or None when the run made no call (no report and no start marker). `resumed` is
    the checkpoint the workflow restored before the run, whose rows an earlier run's sidecar already booked. Raises
    ValueError when the report cannot bound the spend; the caller then books the ceiling."""
    base = {"task": TASK, "model": model, "billing_channel": BILLING_CHANNEL, "max_spend_usd": max_spend,
            "journal_nonce": nonce or None, "resumed_from_run_id": resumed_run_id or None}
    if report is None:
        if not started:
            return None
        return {**base, "run_utc": run_utc, "cost_usd": round(max_spend, 6),
                "cost_basis": "ceiling_imputed:report_missing", "source_report_sha256": None,
                "unbilled_calls_count": None, "calls": None, "resumed_rows": None}
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("report has no metrics object")
    billed_total = _cost(metrics.get("total_cost_usd"), "metrics.total_cost_usd")
    unbilled = metrics.get("unbilled_calls_count")
    if isinstance(unbilled, bool) or not isinstance(unbilled, int) or unbilled < 0:
        raise ValueError(f"report metrics.unbilled_calls_count must be a non-negative integer, got {unbilled!r}")
    rows = _keyed_rows(report, (("cases", "advice"), ("petri_cases", "petri")), "report")
    # the rows must account for the report's totals, so the booking below, made from rows, is the report's spend
    if sum(1 for _, r in rows if r.get("cost_usd") is None) != unbilled:
        raise ValueError(f"report metrics.unbilled_calls_count is {unbilled} but a different number of rows have no "
                         "billed cost")
    billed_rows = sum(_cost(r["cost_usd"], "rows' cost_usd") for _, r in rows if r.get("cost_usd") is not None)
    if abs(billed_rows - billed_total) > 2e-6:
        raise ValueError(f"report rows bill ${billed_rows:.6f} but metrics.total_cost_usd is ${billed_total:.6f}")
    restored: set[tuple] = set()
    if resumed is not None:
        restored = {key for key, _ in _keyed_rows(resumed, (("advice_cases", "advice"), ("petri_cases", "petri")),
                                                   "resumed checkpoint")}
        if restored - {key for key, _ in rows}:
            raise ValueError("checkpoint rows are missing from the report; the resumed rows cannot be told apart from "
                             "this run's")
    cost, unbilled_here = 0.0, 0
    for key, row in rows:
        if key in restored:
            continue
        if row.get("cost_usd") is not None:
            cost += _cost(row["cost_usd"], "rows' cost_usd")
            continue
        estimate = _cost(row.get("estimated_cost_usd"), "rows' estimated_cost_usd")
        if estimate <= 0:
            raise ValueError("an unbilled call has no positive estimate, so its spend is unknown")
        cost += estimate
        unbilled_here += 1
    basis = "billed_plus_estimate_for_unbilled_calls" if unbilled_here else "provider_billed"
    meta = report.get("metadata") or {}
    interrupted = "interrupted" in meta
    if interrupted and cost < max_spend:
        cost, basis = max_spend, "ceiling_imputed:interrupted"
    stamp = meta.get("timestamp_utc") or run_utc
    return {**base, "run_utc": stamp, "cost_usd": round(cost, 6), "cost_basis": basis,
            "source_report_sha256": report_sha256, "unbilled_calls_count": unbilled_here,
            "calls": len(rows) - len(restored), "resumed_rows": len(restored), "interrupted": interrupted}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True, help="the audit's --out-json report (may be absent after a failure)")
    ap.add_argument("--out", required=True, help="the sidecar to write, <name>.report.json")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-spend", required=True, type=float)
    ap.add_argument("--nonce", default="")
    ap.add_argument("--started-marker", required=True, help="written by the workflow just before the paid step")
    ap.add_argument("--run-utc", required=True)
    ap.add_argument("--resumed-checkpoint", help="the checkpoint the workflow restored before the run, if any")
    ap.add_argument("--resumed-run-id", help="the workflow run that checkpoint came from")
    ap.add_argument("--resumed-source-sidecar",
                    help="the earlier run's cost sidecar, data/jev/runs/jev_audit_<run id>_1.report.json; the restored "
                         "rows are left out of this booking only when it is present and is a jev-audit sidecar")
    args = ap.parse_args(argv)
    if not math.isfinite(args.max_spend) or args.max_spend <= 0:
        print(f"Refused: --max-spend must be a positive finite number, got {args.max_spend}", file=sys.stderr)
        return 2
    # a run that left no report is dated by its start marker, which the runner writes (an ISO timestamp) just before
    # its first live request, so spend that began before midnight UTC is booked to that day (Codex review of PR #110)
    run_utc = args.run_utc
    marker = Path(args.started_marker)
    if marker.is_file():
        stamp = marker.read_text(encoding="utf-8").strip()
        if len(stamp) == 20 and stamp.endswith("Z") and stamp[4] == "-" and stamp[10] == "T":
            run_utc = stamp
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
        resumed = None
        if args.resumed_checkpoint:
            try:
                resumed = json.loads(Path(args.resumed_checkpoint).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"resumed checkpoint {args.resumed_checkpoint} is unreadable ({exc})") from exc
            if not isinstance(resumed, dict):
                raise ValueError("resumed checkpoint is not a JSON object")
            source = Path(args.resumed_source_sidecar) if args.resumed_source_sidecar else None
            try:
                booked = (source is not None and source.is_file()
                          and json.loads(source.read_text(encoding="utf-8")).get("task") == TASK)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                booked = False
            if not booked:
                print(f"the resumed run's cost sidecar ({source}) is not on this branch; booking the restored rows "
                      "here as well", file=sys.stderr)
                resumed = None
        sidecar = build_sidecar(report, report_sha256=sha, model=args.model, max_spend=args.max_spend,
                                nonce=args.nonce, started=Path(args.started_marker).is_file(), run_utc=run_utc,
                                resumed=resumed, resumed_run_id=args.resumed_run_id)
    except ValueError as exc:
        print(f"report {report_path}: {exc}; booking the ceiling", file=sys.stderr)
        sidecar = build_sidecar(None, report_sha256=None, model=args.model, max_spend=args.max_spend,
                                nonce=args.nonce, started=True, run_utc=run_utc,
                                resumed_run_id=args.resumed_run_id)
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
