"""Reconstruct mitigation (translation) cost sidecars for historical trace runs.

The translation panel is the only paid call inside a circuit-trace run. Until
2026-07-31 nothing captured its usage and nothing committed a sidecar, so
`ledger_update` booked $0 for every `--show-mitigation` run the study ever
fired. Going forward `batch_eval.write_mitigation_sidecar` records the API's
own token counts. This script covers the runs that predate that fix.

**These costs are IMPUTED, not measured.** The Anthropic usage counts for
those calls were never recorded anywhere — not in the repo, not in the run
artifacts — so they cannot be recovered. What the committed batch summaries do
carry, per translated pair, is exact:

  * the translation model (`translation_model`),
  * the input text (`prompts.patient`) and the system prompt the arm used
    (a constant in llm_client), and
  * the output text (`prompts.translated`).

Cost is therefore estimated from real per-call text at ~4 characters/token and
the published price table. Every sidecar this writes carries `imputed: true`
and its method, so a reader can never mistake it for a metered figure. Expect
the estimate to be within roughly ±25% of the true charge; use it to close the
accounting gap, not to audit Anthropic's invoice.

Usage:
  python scripts/backfill_mitigation_costs.py [--trace-dir trace_out] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from medlang_circuits.evaluate_models import _price
from medlang_circuits.llm_client import _PLACEBO_SYSTEM, _TRANSLATE_SYSTEM

CHARS_PER_TOKEN = 4.0
LLM_METHODS = ("llm", "llm_placebo")


def tokens_for(text: str) -> int:
    return int(math.ceil(len(text or "") / CHARS_PER_TOKEN))


def landed_utc(path: Path) -> str | None:
    """Commit date of the summary file - when the run's outputs actually landed.

    Booking to the real day matters: charging weeks-old spend to today would
    poison the daily ceiling guard (the lesson ledger_update records from the
    2026-07-29 bootstrap)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(path)],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None
    return out.replace("+00:00", "Z") or None


def sidecar_for(summary_path: Path) -> tuple[Path, dict] | None:
    """(sidecar path, payload) reconstructed from one committed batch summary."""
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    per_model: dict[str, dict] = {}
    for result in data.get("results", []):
        method = result.get("translation_method")
        if method not in LLM_METHODS:
            continue
        model = result.get("translation_model")
        if not model:
            continue
        prompts = result.get("prompts") or {}
        system = _PLACEBO_SYSTEM if method == "llm_placebo" else _TRANSLATE_SYSTEM
        entry = per_model.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        entry["calls"] += 1
        entry["input_tokens"] += tokens_for(system) + tokens_for(prompts.get("patient"))
        entry["output_tokens"] += tokens_for(prompts.get("translated"))
    if not per_model:
        return None
    total = 0.0
    for model, entry in per_model.items():
        in_price, out_price = _price(model)
        cost = entry["input_tokens"] * in_price / 1e6 + entry["output_tokens"] * out_price / 1e6
        entry["cost_usd"] = round(cost, 6)
        total += cost
    # batch_summary.part_11.json -> mitigation.part_11.report.json
    stem = summary_path.name.replace("batch_summary", "mitigation").replace(".json", "")
    sidecar = summary_path.parent / f"{stem}.report.json"
    payload = {
        "_": ("IMPUTED mitigation (translation) cost, reconstructed from the committed "
              "batch summary. The API usage counts for these calls were never recorded "
              "and cannot be recovered; this is an estimate from the real per-call text."),
        "kind": "mitigation",
        "imputed": True,
        "imputation_method": (f"~{CHARS_PER_TOKEN:.0f} chars/token over the arm's system prompt "
                              "plus prompts.patient (input) and prompts.translated (output)"),
        "source_summary": summary_path.name,
        "run_utc": landed_utc(summary_path),
        "start_index": data.get("start_index"),
        "calls": sum(e["calls"] for e in per_model.values()),
        "input_tokens": sum(e["input_tokens"] for e in per_model.values()),
        "output_tokens": sum(e["output_tokens"] for e in per_model.values()),
        "per_model": per_model,
        "cost_usd": round(total, 6),
    }
    return sidecar, payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trace-dir", default="trace_out")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    written = skipped = 0
    total = 0.0
    for summary in sorted(Path(args.trace_dir).glob("*/batch_summary*.json")):
        built = sidecar_for(summary)
        if built is None:
            continue
        sidecar, payload = built
        if sidecar.exists():
            skipped += 1
            continue
        total += payload["cost_usd"]
        written += 1
        print(f"  {sidecar.parent.name}/{sidecar.name}: {payload['calls']} calls, "
              f"${payload['cost_usd']:.4f} imputed")
        if not args.dry_run:
            sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} sidecar(s), ${total:.4f} imputed total; {skipped} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
