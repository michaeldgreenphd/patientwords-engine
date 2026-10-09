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
                  are furthest behind), then the least-covered model overall. Slow models
                  (8B, and medgemma-1.5-4b-it at ~120 s/pair) use small chunks; 2-4B models
                  larger; gemma-4-e2b (~5 s/pair) a whole batch per fire.
                  The three 2026-10-09 exploratory models (EXPLORATORY) come after every
                  original model, so they never displace an original model's gap, and their
                  target is PARITY: per batch, the deepest any original model has measured.
                  `--exploratory` plans their legs alone (fastest first) for the Routine's
                  section 3e (docs/routine_standing_prompt.md).
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
# The last three are the 2026-10-09 post-registration exploratory additions (EXPLORATORY below):
# each passed its limit-3 probe on 2026-10-09 (logits-eval run 37960095244) and joins here for a
# $0 backfill to parity with the original ten (docs/model_matrix.md has the timings and estimate).
MODELS = [
    "gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b", "llama-3.2-3b",
    "olmo-2-1b", "gemma-2-2b-it", "medgemma-4b-it", "meditron3-8b", "apertus-8b-meditronfo",
    "gemma-4-e2b", "qwen3.5-2b-base", "medgemma-1.5-4b-it",
]
# The original backfill's medical-first set. medgemma-1.5-4b-it is medical too but is deliberately
# not in it: medical-first ordered the 2026-07 backfill of the original models, and the exploratory
# models are ordered by EXPLORATORY instead.
MEDICAL = {"medgemma-4b-it", "meditron3-8b", "apertus-8b-meditronfo"}
# Post-registration exploratory models (docs/prereg_divergence_log.md, 2026-10-09). They sit after
# every original model in the default plan, are left out of the 8B-release gate, and are complete
# at PARITY (_parity_target), not at every pair of every batch. Tuple order is their priority among
# themselves: fastest measured rate first (about 5, 60 and 120 s/pair in the 2026-10-09 probe), so
# each model reaches parity, and is usable, before the next starts, and the slowest cannot hold up
# the other two - the reasoning DEFERRED_LAST applies to the 8B pair. That puts medgemma-1.5-4b-it
# last, where the medical-first rule would have put it first.
EXPLORATORY = ("gemma-4-e2b", "qwen3.5-2b-base", "medgemma-1.5-4b-it")
# Slow per pair on the CPU runner -> small chunks: the 8B class (~2-4 min/pair) and
# medgemma-1.5-4b-it (~120 s/pair measured 2026-10-09: 25 pairs ~ 50 min of a 240-min job).
BIG = {"meditron3-8b", "apertus-8b-meditronfo", "medgemma-1.5-4b-it"}
# Fast per pair -> a whole batch per fire (the largest batch is 119 pairs): gemma-4-e2b measured
# ~5 s/pair 2026-10-09, so 120 pairs ~ 10 min.
FAST = {"gemma-4-e2b"}
# The two 8B medical models are held to LAST (owner 2026-07-20): their logits jobs
# are multi-hour (weight-load dominated), so backfilling them alongside the fast
# models would stall the whole campaign. They are released only once every OTHER
# axis is complete (trace, lens, and every non-deferred original model's predictions), so
# the faster models' behavior is available for decisions while these catch up in
# the background. Toggle with --include-8b-medical.
DEFERRED_LAST = {"meditron3-8b", "apertus-8b-meditronfo"}

LENS_CHUNK = 25       # 429 caution: a mid-run window loss costs only a chunk
LOGITS_CHUNK_BIG = 25
LOGITS_CHUNK = 50
LOGITS_CHUNK_FAST = 120


def _logits_chunk(model: str) -> int:
    """Pairs per logits-eval fire, by the model's speed class (BIG, FAST, else the 2-4B default).
    Each class keeps a job's measured compute to roughly an hour or less of the workflow's
    240-minute timeout."""
    if model in BIG:
        return LOGITS_CHUNK_BIG
    if model in FAST:
        return LOGITS_CHUNK_FAST
    return LOGITS_CHUNK


def _reference_models() -> list[str]:
    """The original models: every MODELS entry that is not an exploratory addition."""
    return [m for m in MODELS if m not in EXPLORATORY]


def _parity_target(row: dict) -> int:
    """How deep an exploratory model must measure a batch to be at parity: the deepest any original
    model has measured it (capped at the batch size). 0 for a batch no original model has measured
    (pairs_20260721T132205Z and the one-pair scenario-generation parks, as of 2026-10-09), so parity
    never sends an exploratory model past the original axis."""
    return min(row["n"], max((row["models"][m] for m in _reference_models()), default=0))


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


def _next_logits(cov: dict, allow_deferred: bool = True, exploratory_only: bool = False):
    """(model, batch) gap by priority: original medical models first, then the least-covered
    original model, then the EXPLORATORY models in their own order; resume partial batches at
    the next offset. An original model's target is every pair of the batch; an exploratory
    model's is parity (_parity_target). When allow_deferred is False the two 8B medical models
    are skipped entirely (held to last), and so are the exploratory models, which rank after
    them. exploratory_only plans the exploratory models alone (the Routine's section 3e)."""
    if exploratory_only:
        order = list(EXPLORATORY)
    else:
        reference = _reference_models()
        candidates = reference if allow_deferred else [m for m in reference if m not in DEFERRED_LAST]
        covered = {m: sum(1 for b in cov if cov[b]["models"][m] >= cov[b]["n"] > 0) for m in candidates}
        order = sorted(candidates, key=lambda m: (m not in MEDICAL, covered[m]))
        if allow_deferred:
            order += list(EXPLORATORY)
    for m in order:
        chunk = _logits_chunk(m)
        exploratory = m in EXPLORATORY
        for b in sorted(cov):
            r = cov[b]
            target = _parity_target(r) if exploratory else r["n"]
            step = _resume(r["models"][m], target, chunk)
            if step:
                off, lim = step
                label = "backfill PREDICTIONS (exploratory, to parity)" if exploratory else "backfill PREDICTIONS"
                return {
                    "trigger": "logits-eval",
                    "params": {"models": m, "pairs_file": f"data/simulated/{b}.json",
                               "limit": str(lim), "offset": str(off), "commit_outputs": "true"},
                    "note": f"{label}: {b} pairs {off + 1}-{off + lim}/{r['n']} x {m}",
                }
    return None


def _others_complete(cov: dict) -> bool:
    """True once trace, lens, and every non-deferred original model's predictions are complete
    across all batches - the gate that releases the deferred 8B-medical backfill. The
    exploratory models are not part of it: adding them must not re-hold the 8B pair."""
    for r in cov.values():
        if not _complete(r["trace"], r["n"]) or not _complete(r["lens"], r["n"]):
            return False
        for m in _reference_models():
            if m not in DEFERRED_LAST and not _complete(r["models"][m], r["n"]):
                return False
    return True


def exploratory_parity(cov: dict) -> dict:
    """Per exploratory model: pairs measured toward parity, the parity target in pairs, and
    batches at parity out of the batches with a nonzero target."""
    out = {}
    targets = {b: _parity_target(r) for b, r in cov.items()}
    due = [b for b in cov if targets[b] > 0]
    for m in EXPLORATORY:
        out[m] = {
            "pairs": sum(min(cov[b]["models"][m], targets[b]) for b in due),
            "target_pairs": sum(targets[b] for b in due),
            "batches_at_parity": sum(1 for b in due if cov[b]["models"][m] >= targets[b]),
            "batches": len(due),
        }
    return out


def plan(cov: dict, defer_8b_medical: bool = True, exploratory_only: bool = False) -> dict:
    if exploratory_only:
        # the Routine's section 3e: the exploratory models' next leg, and no other lane
        return {"logits-eval": _next_logits(cov, exploratory_only=True)}
    # Hold the 8B medical models until every other axis is done, then release them.
    allow_deferred = (not defer_8b_medical) or _others_complete(cov)
    return {"jlens-readout": _next_lens(cov), "circuit-trace": _next_trace(cov),
            "logits-eval": _next_logits(cov, allow_deferred=allow_deferred)}


def _fmt_cmd(step: dict) -> str:
    return (f"python scripts/fire_trigger.py fire --trigger {step['trigger']} "
            f"--params '{json.dumps(step['params'], separators=(',', ':'))}' "
            f"--note {json.dumps(step['note'])}")


def _complete(depth: int, n: int) -> bool:
    return n > 0 and depth >= n


def summarize(cov: dict) -> None:
    n = len(cov)
    reference = _reference_models()
    trace = sum(_complete(r["trace"], r["n"]) for r in cov.values())
    lens = sum(_complete(r["lens"], r["n"]) for r in cov.values())
    full = sum(1 for r in cov.values() if _complete(r["trace"], r["n"]) and _complete(r["lens"], r["n"])
               and all(_complete(r["models"][m], r["n"]) for m in reference))
    print(f"coverage over {n} pairs_ batches (COMPLETE = all pairs measured): "
          f"trace {trace}/{n} | lens+save_raw {lens}/{n} | fully-covered {full}/{n}")
    per = {m: sum(_complete(cov[b]["models"][m], cov[b]["n"]) for b in cov) for m in reference}
    print("  cross-model complete:", " ".join(f"{m.split('-')[0]}:{per[m]}" for m in reference))
    released = _others_complete(cov)
    held = ", ".join(sorted(DEFERRED_LAST))
    print(f"  8B-medical ({held}): {'RELEASED - all other axes complete' if released else 'HELD until every other axis is complete'}")
    print("  exploratory, at parity with the original models (pairs; batches):",
          " ".join(f"{m}:{p['pairs']}/{p['target_pairs']};{p['batches_at_parity']}/{p['batches']}"
                   for m, p in exploratory_parity(cov).items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    ap.add_argument("--include-8b-medical", action="store_true",
                    help="do not defer the 8B medical models (backfill them alongside the rest)")
    ap.add_argument("--exploratory", action="store_true",
                    help="plan only the 2026-10-09 exploratory models' next PREDICTIONS leg toward parity "
                         "(logits-eval lane only; the Routine's section 3e)")
    args = ap.parse_args()
    cov = coverage()
    steps = plan(cov, defer_8b_medical=not args.include_8b_medical, exploratory_only=args.exploratory)
    if args.json:
        print(json.dumps({"coverage": {b: {"n": r["n"], "trace": r["trace"], "lens": r["lens"],
                                           "models_complete": sum(_complete(r["models"][m], r["n"])
                                                                  for m in _reference_models())}
                                       for b, r in cov.items()},
                          "exploratory_parity": exploratory_parity(cov), "next": steps}, indent=1))
        return 0
    summarize(cov)
    if args.exploratory:
        print("\nNEXT EXPLORATORY LEG (logits-eval only; fire only when the lane has no active entry):")
    else:
        print("\nNEXT FIRE PER LANE (fire whichever lanes are free; respect one-running+one-pending):")
    for lane, step in steps.items():
        if step is None:
            done = "AT PARITY - every exploratory model; nothing to fire." if args.exploratory \
                else "COMPLETE - no gaps."
            print(f"\n[{lane}] {done}")
        else:
            print(f"\n[{lane}] {step['note']}\n  {_fmt_cmd(step)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
