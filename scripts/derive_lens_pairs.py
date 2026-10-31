"""Derive J-lens reader pairs from dialect and 4-quadrant batches.

`scripts/jlens_readout.py` reads one clinical and one patient prompt per pair
(`top_prompt`, `bottom_prompt`). Dialect and quadrant batches hold other
shapes, so the lens backfill skipped them. This script writes one reader pair
per comparison, against the standard clinical prompt (owner decision on the
decision page, 2026-10-31: "baseline vs each variant, and quadrant A vs B, C
and D"):

- dialect record (`baseline_prompt`, `variants`): baseline vs each variant;
- quadrant record (`quadrants` or `frames` x `terms`): A vs B (morphosyntax
  only), A vs C (lexicon only) and A vs D (both). The four prompts are
  resolved by `medlang_circuits.batch_eval._quadrant_prompts`, the function
  the circuit traces used, so the lens reads the same strings.

Each source record's comparisons are written consecutively, so a truncated
lens run still yields complete sets for the records it reached. No API calls;
costs nothing.

Usage:
  python scripts/derive_lens_pairs.py data/simulated/<batch>.json [...] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from medlang_circuits.batch_eval import _quadrant_prompts

METHOD = "programmatic lens-pair derivation (scripts/derive_lens_pairs.py)"
QUADRANT_CONTRASTS = {
    "B": "morphosyntax only (nonstandard frame, medical term)",
    "C": "lexicon only (standard frame, patient term)",
    "D": "morphosyntax and lexicon (nonstandard frame, patient term)",
}


def record_kind(record: dict[str, Any]) -> str:
    """Return 'dialect' or 'quadrant' for one source record, or raise."""
    if record.get("variants") and (record.get("baseline_prompt") or record.get("top_prompt")):
        return "dialect"
    if "quadrants" in record or ("frames" in record and "terms" in record):
        return "quadrant"
    raise ValueError("record is neither a dialect record (baseline_prompt + variants) "
                     "nor a quadrant record (quadrants, or frames + terms)")


def _target_fields(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"target_clinical_token": record.get("target_clinical_token")}
    if record.get("force_target_tokens"):
        out["force_target_tokens"] = record["force_target_tokens"]
    return out


def derive_record(record: dict[str, Any], batch_name: str, index: int) -> list[dict[str, Any]]:
    """Reader pairs for one source record (1-based `index` in its batch)."""
    kind = record_kind(record)
    pairs: list[dict[str, Any]] = []
    if kind == "dialect":
        baseline = record.get("baseline_prompt") or record["top_prompt"]
        for j, variant in enumerate(record["variants"], start=1):
            if not variant.get("prompt") or not variant.get("dialect"):
                raise ValueError(f"{batch_name} record {index} variant {j}: needs 'dialect' and 'prompt'")
            pairs.append({
                "top_prompt": baseline,
                "bottom_prompt": variant["prompt"],
                **_target_fields(record),
                "generation": {
                    "derived_from": {"batch": batch_name, "index": index, "variant": j},
                    "lens_comparison": {"kind": "dialect", "reference": "baseline",
                                        "compared": variant["dialect"]},
                    "method": METHOD,
                    "source_term": record.get("term"),
                    "source_held_fixed": record.get("held_fixed"),
                },
            })
        return pairs
    prompts = _quadrant_prompts(record)
    for cell, contrast in QUADRANT_CONTRASTS.items():
        pairs.append({
            "top_prompt": prompts["A"],
            "bottom_prompt": prompts[cell],
            **_target_fields(record),
            "generation": {
                "derived_from": {"batch": batch_name, "index": index, "quadrant": cell},
                "lens_comparison": {"kind": "quadrant", "reference": "A", "compared": cell,
                                    "contrast": contrast},
                "method": METHOD,
                "source_generation": record.get("generation") or {},
            },
        })
    return pairs


def derive_batch(batch_path: Path, out_dir: Path | None = None) -> tuple[Path, Path, int]:
    """Write `<stem>__lenspairs.json` and its `.report.json`; return both paths and the pair count."""
    records = json.loads(batch_path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError(f"{batch_path}: expected a non-empty JSON array of records")
    derived: list[dict[str, Any]] = []
    kinds: set[str] = set()
    for i, record in enumerate(records, start=1):
        kinds.add(record_kind(record))
        derived.extend(derive_record(record, batch_path.name, i))
    target_dir = out_dir or batch_path.parent
    out_path = target_dir / f"{batch_path.stem}__lenspairs.json"
    out_path.write_text(json.dumps(derived, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {
        "derived_from": batch_path.name,
        "source_records": len(records),
        "kinds": sorted(kinds),
        "pairs": len(derived),
        "comparisons": ("dialect: baseline vs each variant; quadrant: A vs B, C and D "
                        "(owner decision 2026-10-31)"),
        "cost_usd": 0.0,
        "note": "programmatic derivation; no API calls",
    }
    report_path = out_path.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out_path, report_path, len(derived)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="+", type=Path, help="Dialect or quadrant batch JSON files")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Output directory (default: beside each source batch)")
    args = parser.parse_args(argv)
    for batch in args.batches:
        out_path, report_path, n = derive_batch(batch, args.out_dir)
        print(f"{n} reader pairs -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
