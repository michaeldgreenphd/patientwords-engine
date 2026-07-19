#!/usr/bin/env python3
"""Backfill planner: compute simulation coverage gaps and emit the next $0 fire per lane.

Owner goal (2026-07-19): full coverage of every simulation batch on three axes -
  (1) circuit TRACE  : gemma-2-2b hosted attribution graph (the only hosted-graph model)
  (2) j-lens LENS    : JACOBIAN_LENS readout WITH save_raw (feeds the transport / logit-lens
                       site exporters; save_raw is what makes them foldable into the cycle)
  (3) cross-model PREDICTIONS: next-token logits across the model registry

All three are $0 (hosted trace / hosted lens / CPU logits). This script is READ-ONLY: it
reads committed data/simulated/pairs_*.json + trace_out/ and PRINTS the highest-priority
next fire per lane as a ready `scripts/fire_trigger.py` command. It never fires anything;
the caller (the daily cycle) fires whichever lanes are free, respecting one-running +
one-pending queue discipline.

Priority (documented so the cycle is predictable):
  - LENS first  : unblocks the static transport/loglens figures (owner's j-lens thread) and
                  is the sparsest axis; chunked to 25 (a mid-run 429 loses only a chunk).
  - TRACE next  : completes the base gemma trace set (6-ish gaps).
  - PREDICTIONS : cross-model logits; MEDICAL models first (meditron3-8b, apertus, medgemma
                  are furthest behind), then the least-covered model overall. 8B models use
                  small chunks; 2-4B models larger.
Batch-level granularity (v1): each lane emits the OLDEST batch missing that axis. Partial
(chunk-level) resume is left to the trace part-file checkpointing already in CI.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]

# Cross-model prediction registry (order = fallback priority after medical).
# Mirrors logits_eval.HF_IDS minus dropped/superseded ids; gemma-2-9b is on hold.
MODELS = [
    "gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b", "llama-3.2-3b",
    "olmo-2-1b", "gemma-2-2b-it", "medgemma-4b-it", "meditron3-8b", "apertus-8b-meditronfo",
]
MEDICAL = {"medgemma-4b-it", "meditron3-8b", "apertus-8b-meditronfo"}
# 8B-class models trace ~2-4x slower per pair on CPU -> smaller chunks.
BIG = {"meditron3-8b", "apertus-8b-meditronfo"}

LENS_CHUNK = 25       # 429 caution: a mid-run window loss costs only a chunk
LOGITS_CHUNK_BIG = 25
LOGITS_CHUNK = 50


def _max_index(rel: str, pat: str) -> int:
    """Highest 1-based result index measured across a dir's summary parts (0 if none).
    Backfill chunks fire contiguously from offset 0, so the highest measured index is the
    resume point: the next fire uses offset = max_index (0-based) to continue the batch."""
    hi = 0
    for f in glob.glob(str(ENGINE / "trace_out" / rel / pat)):
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in data.get("results", []):
            idx = r.get("index")
            if isinstance(idx, int):
                hi = max(hi, idx)
    return hi


def _saveraw_pairs(rel: str) -> int:
    """Distinct pairs with committed save_raw (.gz files come in clinical+patient per pair)."""
    return len(glob.glob(str(ENGINE / "trace_out" / rel / "jlens_raw" / "*.gz"))) // 2


def _pair_count(batch: str) -> int:
    try:
        return len(json.loads((ENGINE / "data" / "simulated" / f"{batch}.json").read_text()))
    except Exception:
        return 0


def batches() -> list[str]:
    out = []
    for p in sorted(glob.glob(str(ENGINE / "data/simulated/pairs_*.json"))):
        if p.endswith(".report.json"):
            continue
        out.append(os.path.basename(p)[:-5])
    return out


def coverage() -> dict:
    """Per-batch DEPTH: how many of a batch's pairs are measured on each axis (not just
    presence). A batch axis is complete when measured >= n."""
    rows = {}
    for b in batches():
        n = _pair_count(b)
        rows[b] = {
            "n": n,
            "trace": _max_index(b, "batch_summary*.json"),
            "lens": min(_max_index(f"{b}__jlens_gemma-2-2b", "jlens_summary*.json"),
                        # lens is only useful with save_raw; gate lens depth on raw depth
                        _saveraw_pairs(f"{b}__jlens_gemma-2-2b") or 0),
            "models": {m: _max_index(f"{b}__{m}", "batch_summary*.json") for m in MODELS},
        }
    return rows


def _resume(depth: int, n: int, chunk: int):
    """(offset, limit) for the next chunk of a partly-covered batch, or None if complete."""
    if depth >= n:
        return None
    return depth, min(chunk, n - depth)


def _next_lens(cov: dict):
    """Oldest batch whose lens+save_raw depth is short; resume at the next offset."""
    for b in sorted(cov):
        r = cov[b]
        step = _resume(r["lens"], r["n"], LENS_CHUNK)
        if step:
            off, lim = step
            return {
                "trigger": "jlens-readout",
                "params": {"models": "gemma-2-2b", "pairs_file": f"data/simulated/{b}.json",
                           "limit": str(lim), "offset": str(off), "topn": "8",
                           "lens_type": "JACOBIAN_LENS", "save_raw": "true", "commit_outputs": "true"},
                "note": f"backfill LENS+save_raw: {b} pairs {off + 1}-{off + lim}/{r['n']} (jlens gemma-2-2b)",
            }
    return None


def _next_trace(cov: dict):
    for b in sorted(cov):
        r = cov[b]
        step = _resume(r["trace"], r["n"], 50)
        if step:
            off, lim = step
            return {
                "trigger": "circuit-trace",
                "params": {"graph_models": "gemma-2-2b", "mode": "2panel",
                           "pairs_file": f"data/simulated/{b}.json", "offsets": str(off),
                           "sample_size": str(lim), "commit_outputs": "true"},
                "note": f"backfill TRACE: {b} pairs {off + 1}-{off + lim}/{r['n']} (gemma-2-2b 2panel)",
            }
    return None


def _next_logits(cov: dict):
    """(model, batch) gap by priority: medical models first, then least-covered model;
    resume partial batches at the next offset."""
    covered = {m: sum(1 for b in cov if cov[b]["models"][m] >= cov[b]["n"] > 0) for m in MODELS}
    order = sorted(MODELS, key=lambda m: (m not in MEDICAL, covered[m]))
    for m in order:
        chunk = LOGITS_CHUNK_BIG if m in BIG else LOGITS_CHUNK
        for b in sorted(cov):
            r = cov[b]
            step = _resume(r["models"][m], r["n"], chunk)
            if step:
                off, lim = step
                return {
                    "trigger": "logits-eval",
                    "params": {"models": m, "pairs_file": f"data/simulated/{b}.json",
                               "limit": str(lim), "offset": str(off), "commit_outputs": "true"},
                    "note": f"backfill PREDICTIONS: {b} pairs {off + 1}-{off + lim}/{r['n']} x {m}",
                }
    return None


def plan(cov: dict) -> dict:
    return {"jlens-readout": _next_lens(cov), "circuit-trace": _next_trace(cov),
            "logits-eval": _next_logits(cov)}


def _fmt_cmd(step: dict) -> str:
    return (f"python scripts/fire_trigger.py fire --trigger {step['trigger']} "
            f"--params '{json.dumps(step['params'], separators=(',', ':'))}' "
            f"--note {json.dumps(step['note'])}")


def _complete(depth: int, n: int) -> bool:
    return n > 0 and depth >= n


def summarize(cov: dict) -> None:
    n = len(cov)
    trace = sum(_complete(r["trace"], r["n"]) for r in cov.values())
    lens = sum(_complete(r["lens"], r["n"]) for r in cov.values())
    full = sum(1 for r in cov.values() if _complete(r["trace"], r["n"]) and _complete(r["lens"], r["n"])
               and all(_complete(r["models"][m], r["n"]) for m in MODELS))
    print(f"coverage over {n} pairs_ batches (COMPLETE = all pairs measured): "
          f"trace {trace}/{n} | lens+save_raw {lens}/{n} | fully-covered {full}/{n}")
    per = {m: sum(_complete(cov[b]["models"][m], cov[b]["n"]) for b in cov) for m in MODELS}
    print("  cross-model complete:", " ".join(f"{m.split('-')[0]}:{per[m]}" for m in MODELS))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = ap.parse_args()
    cov = coverage()
    steps = plan(cov)
    if args.json:
        print(json.dumps({"coverage": {b: {"n": r["n"], "trace": r["trace"], "lens": r["lens"],
                                           "models_complete": sum(_complete(r["models"][m], r["n"])
                                                                  for m in MODELS)}
                                       for b, r in cov.items()}, "next": steps}, indent=1))
        return 0
    summarize(cov)
    print("\nNEXT FIRE PER LANE (fire whichever lanes are free; respect one-running+one-pending):")
    for lane, step in steps.items():
        if step is None:
            print(f"\n[{lane}] COMPLETE - no gaps.")
        else:
            print(f"\n[{lane}] {step['note']}\n  {_fmt_cmd(step)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
