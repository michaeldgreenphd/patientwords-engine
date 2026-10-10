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

The 2026-10-09 exploratory models (EXPLORATORY; owner decision 2026-10-09) are planned apart from
the axes above and never displace an original model's gap. Their target is PARITY: per batch, the
deepest any original model has measured it (_parity_target). Their coverage is read as the set of
indices measured, not the highest one, because a model's parts need not be contiguous.
  - `--exploratory`: the SWEEP, gemma-4-e2b and qwen3.5-2b-base together, one fire per batch
    carrying both models (the workflow fans `models` out as a matrix), a whole batch per fire.
    The Routine's section 3e fires this (docs/routine_standing_prompt.md).
  - `--exploratory --medgemma15-selection FILE`: medgemma-1.5-4b-it on the pairs a selection file
    from scripts/select_priority_pairs.py names, first, as `indices` fires within their batches.
  - `--exploratory --include-medgemma15`: medgemma-1.5-4b-it on everything else to parity, after the
    sweep (the "rest"); it fills only pairs not yet measured, as `indices` fires when the gaps are
    not one contiguous run, so no part is measured twice or overwritten.
  - `--next N` prints the next N legs (each later leg planned as if the earlier ones had landed),
    so a session can keep one running and one pending.
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
# each passed its limit-3 probe on 2026-10-09 (logits-eval run 37960095244).
MODELS = [
    "gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b", "llama-3.2-3b",
    "olmo-2-1b", "gemma-2-2b-it", "medgemma-4b-it", "meditron3-8b", "apertus-8b-meditronfo",
    "gemma-4-e2b", "qwen3.5-2b-base", "medgemma-1.5-4b-it",
]
# The original backfill's medical-first set. medgemma-1.5-4b-it is medical too but is not in it:
# medical-first ordered the 2026-07 backfill of the original models, and the exploratory models
# have their own plan (owner, 2026-10-09: the two fast models' sweep first, medgemma-1.5 on a
# priority selection, then the rest).
MEDICAL = {"medgemma-4b-it", "meditron3-8b", "apertus-8b-meditronfo"}
# Post-registration exploratory models (docs/prereg_divergence_log.md, 2026-10-09).
EXPLORATORY = ("gemma-4-e2b", "qwen3.5-2b-base", "medgemma-1.5-4b-it")
# Fired together, one fire per batch: the default exploratory sweep.
SWEEP_MODELS = ("gemma-4-e2b", "qwen3.5-2b-base")
# Behind --medgemma15-selection (priority pairs) and --include-medgemma15 (the rest).
MEDGEMMA15 = "medgemma-1.5-4b-it"
# Slow per pair on the CPU runner -> small chunks: the 8B class (~2-4 min/pair) and
# medgemma-1.5-4b-it (~120 s/pair measured 2026-10-09: 25 pairs ~ 50 min of a 240-min job).
BIG = {"meditron3-8b", "apertus-8b-meditronfo", "medgemma-1.5-4b-it"}
# A whole batch per fire (the largest batch is 119 pairs). Measured 2026-10-09: gemma-4-e2b ~5 s/pair
# (119 pairs ~ 10 min) and qwen3.5-2b-base ~60 s/pair (119 pairs ~ 119 min, half the 240-min timeout,
# so no batch needs splitting at that rate).
FAST = {"gemma-4-e2b", "qwen3.5-2b-base"}
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
    Each class keeps a job's measured compute to at most half of the workflow's 240-minute timeout."""
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


def _indices(rel: str, pat: str) -> set[int]:
    """Every 1-based result index measured across a dir's summary parts (empty if none)."""
    found: set[int] = set()
    for f in glob.glob(str(ENGINE / "trace_out" / rel / pat)):
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in data.get("results", []):
            idx = r.get("index")
            if isinstance(idx, int):
                found.add(idx)
    return found


def _max_index(rel: str, pat: str) -> int:
    """Highest 1-based result index measured across a dir's summary parts (0 if none).
    Backfill chunks fire contiguously from offset 0, so the highest measured index is the
    resume point: the next fire uses offset = max_index (0-based) to continue the batch."""
    return max(_indices(rel, pat), default=0)


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
    presence). A batch axis is complete when measured >= n. For the exploratory models,
    `measured` also holds the set of indices measured."""
    rows = {}
    for b in batches():
        n = _pair_count(b)
        measured = {m: _indices(f"{b}__{m}", "batch_summary*.json") for m in EXPLORATORY}
        rows[b] = {
            "n": n,
            "trace": _max_index(b, "batch_summary*.json"),
            "lens": min(_max_index(f"{b}__jlens_gemma-2-2b", "jlens_summary*.json"),
                        # lens is only useful with save_raw; gate lens depth on raw depth
                        _saveraw_pairs(f"{b}__jlens_gemma-2-2b") or 0),
            "models": {m: (max(measured[m], default=0) if m in measured
                           else _max_index(f"{b}__{m}", "batch_summary*.json")) for m in MODELS},
            "measured": measured,
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


def _next_logits(cov: dict, allow_deferred: bool = True):
    """(model, batch) gap of an ORIGINAL model by priority: medical models first, then the
    least-covered model; resume partial batches at the next offset. When allow_deferred is
    False the two 8B medical models are skipped entirely (held to last), so the fast models
    finish first. The exploratory models are planned by exploratory_legs, never here."""
    reference = _reference_models()
    candidates = reference if allow_deferred else [m for m in reference if m not in DEFERRED_LAST]
    covered = {m: sum(1 for b in cov if cov[b]["models"][m] >= cov[b]["n"] > 0) for m in candidates}
    order = sorted(candidates, key=lambda m: (m not in MEDICAL, covered[m]))
    for m in order:
        chunk = _logits_chunk(m)
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


def load_selection(path: str | Path) -> dict[str, set[int]]:
    """{batch stem: selected 1-based indices} from a scripts/select_priority_pairs.py output file."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, set[int]] = {}
    for p in doc["pairs"]:
        out.setdefault(p["batch"], set()).add(int(p["index"]))
    return out


def _leg(batch: str, n: int, models: list[str], chosen: list[int], label: str) -> dict:
    """One logits-eval fire: a contiguous run as offset/limit (the usual part name), any other set of
    indices as `indices`; both name the part for its first index."""
    params = {"models": ",".join(models), "pairs_file": f"data/simulated/{batch}.json"}
    if chosen[-1] - chosen[0] + 1 == len(chosen):
        params.update({"limit": str(len(chosen)), "offset": str(chosen[0] - 1)})
        where = f"pairs {chosen[0]}-{chosen[-1]}/{n}"
    else:
        params["indices"] = ",".join(str(i) for i in chosen)
        where = f"pairs {params['indices']}/{n}"
    params["commit_outputs"] = "true"
    return {"trigger": "logits-eval", "params": params,
            "note": f"backfill PREDICTIONS ({label}): {batch} {where} x {'+'.join(models)}"}


def exploratory_legs(cov: dict, models: tuple[str, ...] = SWEEP_MODELS, count: int = 1,
                     selection: dict[str, set[int]] | None = None, label: str = "exploratory, to parity") -> list:
    """The next `count` fires bringing `models` to parity, oldest batch first. Each fire covers the
    first pairs (at most the smallest chunk among `models`) the lead model - the first in `models`
    still short on that batch - has not measured, and carries every model in `models` that has
    measured none of them; models are fired together whenever their gaps agree, which is always the
    case for a sweep that only ever fired them together. Later fires are planned as if the earlier
    ones had landed. With `selection`, the target is only the selected indices of each batch."""
    measured = {b: {m: set(cov[b]["measured"][m]) for m in models} for b in cov}
    chunk = min(_logits_chunk(m) for m in models)
    legs = []
    for b in sorted(cov):
        target = set(range(1, _parity_target(cov[b]) + 1))
        if selection is not None:
            target &= selection.get(b, set())
        while len(legs) < count:
            missing = {m: sorted(target - measured[b][m]) for m in models}
            lead = next((m for m in models if missing[m]), None)
            if lead is None:
                break
            chosen = missing[lead][:chunk]
            fired = [m for m in models if set(chosen) <= set(missing[m])]
            legs.append(_leg(b, cov[b]["n"], fired, chosen, label))
            for m in fired:
                measured[b][m].update(chosen)
        if len(legs) >= count:
            break
    return legs


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
    targets = {b: set(range(1, _parity_target(r) + 1)) for b, r in cov.items()}
    due = [b for b in cov if targets[b]]
    for m in EXPLORATORY:
        out[m] = {
            "pairs": sum(len(targets[b] & cov[b]["measured"][m]) for b in due),
            "target_pairs": sum(len(targets[b]) for b in due),
            "batches_at_parity": sum(1 for b in due if targets[b] <= cov[b]["measured"][m]),
            "batches": len(due),
        }
    return out


def exploratory_plan(cov: dict, count: int = 1, include_medgemma15: bool = False,
                     medgemma15_selection: dict[str, set[int]] | None = None) -> list:
    """The exploratory legs a caller asked for: medgemma-1.5-4b-it's selected pairs alone when a
    selection is given; otherwise the sweep, then (with include_medgemma15) medgemma-1.5-4b-it's rest
    once the sweep is at parity."""
    if medgemma15_selection is not None:
        return exploratory_legs(cov, (MEDGEMMA15,), count, medgemma15_selection,
                                label="exploratory, medgemma-1.5 priority selection")
    legs = exploratory_legs(cov, SWEEP_MODELS, count)
    if include_medgemma15 and len(legs) < count:
        legs += exploratory_legs(cov, (MEDGEMMA15,), count - len(legs), label="exploratory, to parity")
    return legs


def plan(cov: dict, defer_8b_medical: bool = True, exploratory_only: bool = False, count: int = 1,
         include_medgemma15: bool = False, medgemma15_selection: dict[str, set[int]] | None = None) -> dict:
    if exploratory_only:
        # the Routine's section 3e (and a session's chain): the exploratory legs, and no other lane
        legs = exploratory_plan(cov, count, include_medgemma15, medgemma15_selection)
        return {"logits-eval": legs[0] if legs else None}
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    ap.add_argument("--include-8b-medical", action="store_true",
                    help="do not defer the 8B medical models (backfill them alongside the rest)")
    ap.add_argument("--exploratory", action="store_true",
                    help="plan only the 2026-10-09 exploratory models' next PREDICTIONS legs toward parity "
                         "(logits-eval lane only): the gemma-4-e2b + qwen3.5-2b-base sweep, one fire per batch; "
                         "the Routine's section 3e")
    ap.add_argument("--include-medgemma15", action="store_true",
                    help="with --exploratory: after the sweep reaches parity, plan medgemma-1.5-4b-it's remaining "
                         "pairs (only pairs it has not measured)")
    ap.add_argument("--medgemma15-selection", metavar="FILE",
                    help="with --exploratory: plan medgemma-1.5-4b-it on this selection's pairs only "
                         "(scripts/select_priority_pairs.py output), before anything else for it")
    ap.add_argument("--next", type=int, default=1, metavar="N",
                    help="with --exploratory: print the next N legs, each planned as if the earlier ones had "
                         "landed (a session keeping one running and one pending uses 2)")
    args = ap.parse_args(argv)
    if (args.include_medgemma15 or args.medgemma15_selection or args.next != 1) and not args.exploratory:
        ap.error("--include-medgemma15, --medgemma15-selection and --next go with --exploratory")
    if args.include_medgemma15 and args.medgemma15_selection:
        ap.error("--medgemma15-selection plans the priority pairs alone; run --include-medgemma15 separately")
    if args.next < 1:
        ap.error("--next must be at least 1")
    cov = coverage()
    selection = load_selection(args.medgemma15_selection) if args.medgemma15_selection else None
    if args.exploratory:
        legs = exploratory_plan(cov, args.next, args.include_medgemma15, selection)
        steps = {"logits-eval": legs[0] if legs else None}
    else:
        legs = []
        steps = plan(cov, defer_8b_medical=not args.include_8b_medical)
    if args.json:
        print(json.dumps({"coverage": {b: {"n": r["n"], "trace": r["trace"], "lens": r["lens"],
                                           "models_complete": sum(_complete(r["models"][m], r["n"])
                                                                  for m in _reference_models())}
                                       for b, r in cov.items()},
                          "exploratory_parity": exploratory_parity(cov), "next": steps,
                          **({"next_legs": legs} if args.exploratory else {})}, indent=1))
        return 0
    summarize(cov)
    if args.exploratory:
        print(f"\nNEXT EXPLORATORY LEG{'S' if args.next > 1 else ''} (logits-eval only; fire only when the lane "
              "has room - one running + one pending):")
        if not legs:
            print("\n[logits-eval] AT PARITY - nothing to fire for the models planned.")
        for step in legs:
            print(f"\n[logits-eval] {step['note']}\n  {_fmt_cmd(step)}")
        return 0
    print("\nNEXT FIRE PER LANE (fire whichever lanes are free; respect one-running+one-pending):")
    for lane, step in steps.items():
        if step is None:
            print(f"\n[{lane}] COMPLETE - no gaps.")
        else:
            print(f"\n[{lane}] {step['note']}\n  {_fmt_cmd(step)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
