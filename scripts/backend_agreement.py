"""Cross-backend agreement: do two measurement backends report the same numbers?

The study's probabilities come from two different implementations. gemma-2-2b is
measured through Neuronpedia's hosted attribution-graph endpoint (``backend:
"hosted"``); every other model is measured by direct forward passes in CI
(``backend: "logits"``). ``scripts/retrace_consistency.py`` already answers "does
one backend reproduce itself"; nothing answered "do two backends agree with each
other on the same model and the same prompts", which is a different question and
the one a reader asks about a hosted measurement.

This script answers it offline from committed artifacts. Point it at two run
directories for the SAME pairs stem and the SAME model, and it joins their
results on ``results[i]["index"]``, refuses any row whose two prompts are not
byte-identical, and reports:

- per-side |dp| between the two backends (mean/median/max, and the count over
  each of two thresholds), so a per-pair number's cross-backend precision is a
  measured quantity rather than an assumption;
- the same for ``language_penalty``, plus each backend's mean penalty over the
  rows both measured -- the aggregate the published claim actually rests on;
- CENSORING, per side: rows where the reference reported null and the candidate
  reported a value. The hosted path reads probabilities off a truncated top-N
  logit list, so a target below that floor is recorded as null; a local softmax
  has no floor. Reported per side because the censoring is not symmetric and its
  asymmetry runs in the same direction as the effect under study.

Nothing here re-measures anything: it is arithmetic over the summary chunks
files already on disk. $0, offline, no network, no model weights.

Usage:
  python scripts/backend_agreement.py \
      --reference trace_out/pairs_<STAMP> \
      --candidate trace_out/pairs_<STAMP>__gemma-2-2b \
      [--out ops/backend_agreement.json] [--near 0.01] [--far 0.02]

No medical vocabulary lives in this file.
"""

import argparse
import glob
import json
import os
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

SIDES = ("clinical", "patient")
DEFAULT_NEAR = 0.01
DEFAULT_FAR = 0.02


# The two summary families this script can read. `batch_summary*` is a published
# measurement (hosted graphs or the logits lane); `verify_summary*` is a
# verification re-measurement from `scripts/verify_probs.py`. They live in
# separate run directories by construction, which is what lets the pattern be
# inferred rather than passed.
SUMMARY_PATTERNS = ("batch_summary*.json", "verify_summary*.json")


_PART_RE = re.compile(r"part_(\d+)")


def _part_sorted(paths):
    """Chunk files in NUMERIC part order.

    "A later part wins on a duplicate index" is only true if later parts sort
    later. A plain string sort puts part_100..part_109 between part_10 and
    part_11 and part_351 before part_36; three batches on disk already reach
    part_100+, so once an overlapping fill-in chunk lands there the EARLIER
    chunk would silently win. Files without a part number sort first, in name
    order, so a bare batch_summary.json is still overridden by any part.
    """
    def key(path):
        m = _PART_RE.search(os.path.basename(path))
        return (1, int(m.group(1)), path) if m else (0, 0, path)
    return sorted(paths, key=key)


def summary_paths(run_dir, pattern=None):
    """The summary chunks in one run directory, and which family they came from.

    A run directory holds one family or the other. Finding both means the caller
    pointed at a directory where a verification run was written over a published
    one - refused rather than resolved, because picking either would silently
    compare something other than what was asked for.
    """
    if pattern:
        paths = _part_sorted(glob.glob(os.path.join(run_dir, pattern)))
        if not paths:
            raise SystemExit(f"no {pattern} under {run_dir}")
        return paths
    found = {pat: _part_sorted(glob.glob(os.path.join(run_dir, pat))) for pat in SUMMARY_PATTERNS}
    hits = {pat: paths for pat, paths in found.items() if paths}
    if len(hits) > 1:
        raise SystemExit(
            f"{run_dir} holds more than one summary family ({', '.join(hits)}); "
            f"pass --reference-pattern/--candidate-pattern to say which to read")
    if not hits:
        raise SystemExit(f"no {' or '.join(SUMMARY_PATTERNS)} under {run_dir}")
    return next(iter(hits.values()))


def load_run(run_dir, pattern=None):
    """Every summary chunk in one run directory, joined by index.

    Chunked CI runs write ``<family>.part_NN.json`` per chunk, so a run is
    the union of its parts. A later part wins on a duplicate index (a re-run
    fill-in chunk is written after the chunk it replaces).
    """
    paths = summary_paths(run_dir, pattern)
    results, meta = {}, {}
    for path in paths:
        summary = json.loads(Path(path).read_text(encoding="utf-8"))
        for key in ("backend", "graph_model", "model", "source_set", "generation_params"):
            if key in summary and key not in meta:
                meta[key] = summary[key]
        for result in summary.get("results", []):
            index = result.get("index")
            if index is not None:
                results[index] = result
    meta["parts"] = len(paths)
    meta["n_results"] = len(results)
    return results, meta


def prompts_of(result):
    prompts = result.get("prompts") or {}
    return tuple(prompts.get(side) for side in SIDES)


def join(reference, candidate):
    """Rows present in both runs whose prompts are byte-identical.

    A prompt mismatch is never averaged over: the two runs would be measuring
    different stimuli under the same index, which is the one failure that would
    look like a small disagreement instead of a joined-wrong dataset.
    """
    rows, mismatched = [], []
    for index in sorted(set(reference) & set(candidate)):
        ref, cand = reference[index], candidate[index]
        if prompts_of(ref) != prompts_of(cand):
            mismatched.append(index)
            continue
        rows.append((index, ref, cand))
    return rows, mismatched


def _spread(values):
    if not values:
        return {"n": 0, "mean": None, "median": None, "max": None}
    return {"n": len(values),
            "mean": round(statistics.mean(values), 6),
            "median": round(statistics.median(values), 6),
            "max": round(max(values), 6)}


def _over(values, threshold):
    return sum(1 for v in values if v > threshold)


def compare(rows, near=DEFAULT_NEAR, far=DEFAULT_FAR):
    """Agreement, censoring, and the two mean penalties, from joined rows."""
    deltas, worst = [], []
    censored = {side: {"reference_null_candidate_measured": 0, "candidate_measured": 0}
                for side in SIDES}
    penalty_deltas, ref_penalties, cand_penalties = [], [], []

    for index, ref, cand in rows:
        ref_p = ref.get("probabilities") or {}
        cand_p = cand.get("probabilities") or {}
        for side in SIDES:
            a, b = ref_p.get(side), cand_p.get(side)
            if b is not None:
                censored[side]["candidate_measured"] += 1
                if a is None:
                    censored[side]["reference_null_candidate_measured"] += 1
            if a is None or b is None:
                continue
            delta = abs(a - b)
            deltas.append(delta)
            worst.append({"index": index, "side": side, "reference": a,
                          "candidate": b, "abs_delta": round(delta, 6)})
        ref_pen, cand_pen = ref.get("language_penalty"), cand.get("language_penalty")
        if ref_pen is not None and cand_pen is not None:
            penalty_deltas.append(abs(ref_pen - cand_pen))
            ref_penalties.append(ref_pen)
            cand_penalties.append(cand_pen)

    worst.sort(key=lambda r: -r["abs_delta"])
    for side in SIDES:
        c = censored[side]
        total = c["candidate_measured"]
        c["rate"] = round(c["reference_null_candidate_measured"] / total, 4) if total else None

    return {
        "thresholds": {"near": near, "far": far},
        "probability": {**_spread(deltas),
                        "over_near": _over(deltas, near),
                        "over_far": _over(deltas, far)},
        "penalty": {**_spread(penalty_deltas),
                    "over_near": _over(penalty_deltas, near),
                    "over_far": _over(penalty_deltas, far),
                    "mean_reference": round(statistics.mean(ref_penalties), 6) if ref_penalties else None,
                    "mean_candidate": round(statistics.mean(cand_penalties), 6) if cand_penalties else None},
        "censoring": censored,
        "worst": worst[:10],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--reference", required=True, help="run dir treated as the reference backend")
    ap.add_argument("--candidate", required=True, help="run dir compared against it")
    ap.add_argument("--out", default=None, help="write the report JSON here")
    ap.add_argument("--reference-pattern", default=None,
                    help="summary glob for --reference (inferred when the run dir holds "
                         "only one of %s)" % ", ".join(SUMMARY_PATTERNS))
    ap.add_argument("--candidate-pattern", default=None,
                    help="summary glob for --candidate")
    ap.add_argument("--near", type=float, default=DEFAULT_NEAR)
    ap.add_argument("--far", type=float, default=DEFAULT_FAR)
    args = ap.parse_args()

    ref_results, ref_meta = load_run(args.reference, args.reference_pattern)
    cand_results, cand_meta = load_run(args.candidate, args.candidate_pattern)
    rows, mismatched = join(ref_results, cand_results)
    report = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reference": {"dir": args.reference, **ref_meta},
        "candidate": {"dir": args.candidate, **cand_meta},
        "joined_pairs": len(rows),
        "prompt_mismatched_indices": mismatched,
        **compare(rows, args.near, args.far),
    }
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    print(text)


if __name__ == "__main__":
    main()
