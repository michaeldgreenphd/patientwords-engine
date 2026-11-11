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

Verdict from criteria written before a run (added 2026-11-11). With
``--criteria FILE --comparison NAME`` the report gains a ``verdict`` block. FILE
is a preview record such as
``data/experiments/protocols/first_run_stage_a.preview.v1.json``; its
``parity_criteria.<stage>.<comparison>`` names the sides compared, the two
thresholds and the reference file with its SHA-256. The verdict is ``pass`` (or
``consistent``, where the criteria call it that), ``fail`` or ``inconclusive``,
with every precondition and its outcome listed. A precondition that does not
hold, or that this script could not check, gives ``inconclusive``: a verdict is
never issued on a comparison whose preconditions are unknown. A side whose two
target labels differ is set aside and never counted as a disagreement between
implementations, because the two values are probabilities of different tokens.
Without ``--criteria`` the report is what it was before.

Usage:
  python scripts/backend_agreement.py \
      --reference trace_out/pairs_<STAMP> \
      --candidate trace_out/pairs_<STAMP>__gemma-2-2b \
      [--out ops/backend_agreement.json] [--near 0.01] [--far 0.02]

No medical vocabulary lives in this file.
"""

import argparse
import glob
import hashlib
import json
import math
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


# ---------------------------------------------------------------- verdict from criteria written before a run

GRID = 1e-9          # recorded probabilities sit on a 1e-4 grid; this absorbs binary rounding of their difference


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label_of(result):
    """The token a result's probabilities are of, as the lane recorded it."""
    return (result or {}).get("target_token")


def stage_verdict(rows, criteria, preconditions, label_results=None):
    """``pass`` / ``fail`` / ``inconclusive`` for one comparison, from criteria fixed before the run.

    ``rows`` are the joined ``(index, reference, candidate)`` rows. ``criteria`` is one block of a preview
    record's ``parity_criteria``: ``comparable_sides`` (absent: every side of every row), ``pass_max`` or
    ``consistent_max``, and ``fail_above``. ``preconditions`` is a list of ``{"name", "holds", "detail"}``
    that the caller evaluated; ``holds`` is True, False or None (not checked). ``label_results`` are the
    results whose target labels the candidate must share (default: the reference's).
    """
    ok_word = "pass" if "pass_max" in criteria else "consistent"
    ok_max, fail_above = criteria.get("pass_max", criteria.get("consistent_max")), criteria["fail_above"]
    by_index = {index: (ref, cand) for index, ref, cand in rows}
    listed = criteria.get("comparable_sides")
    wanted = ([(entry["batch_index"], entry["side"]) for entry in listed] if listed is not None
              else [(index, side) for index in sorted(by_index) for side in SIDES])
    checks = [dict(item) for item in preconditions]
    compared, set_aside = [], []
    for index, side in wanted:
        if index not in by_index:
            set_aside.append({"index": index, "side": side, "reason": "row_not_in_both_runs"})
            continue
        ref, cand = by_index[index]
        expected_label = label_of((label_results or {}).get(index)) if label_results is not None else label_of(ref)
        if label_of(cand) is None or label_of(cand) != expected_label or label_of(cand) != label_of(ref):
            set_aside.append({"index": index, "side": side, "reason": "target_labels_differ"})
            continue
        a, b = (ref.get("probabilities") or {}).get(side), (cand.get("probabilities") or {}).get(side)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (a, b)):
            set_aside.append({"index": index, "side": side, "reason": "value_missing_or_not_finite"})
            continue
        compared.append({"index": index, "side": side, "reference": a, "candidate": b,
                         "abs_delta": round(abs(a - b), 6)})
    checks.append({"name": "every side of the declared set was compared", "holds": not set_aside,
                   "detail": f"{len(compared)} of {len(wanted)} sides compared; {len(set_aside)} set aside"})
    failed = [item["name"] for item in checks if item["holds"] is False]
    unchecked = [item["name"] for item in checks if item["holds"] is None]
    deltas = [row["abs_delta"] for row in compared]
    if failed or unchecked:
        verdict = "inconclusive"
        reason = ("a precondition does not hold: " + "; ".join(failed) if failed
                  else "a precondition was not checked: " + "; ".join(unchecked))
    elif any(delta > fail_above + GRID for delta in deltas):
        verdict, reason = "fail", f"{sum(d > fail_above + GRID for d in deltas)} side(s) above {fail_above}"
    elif all(delta <= ok_max + GRID for delta in deltas):
        verdict, reason = ok_word, f"every one of the {len(deltas)} sides is at or below {ok_max}"
    else:
        verdict = "inconclusive"
        reason = (f"{sum(d > ok_max + GRID for d in deltas)} side(s) above {ok_max} and none above {fail_above}")
    return {"verdict": verdict, "reason": reason, "outcomes": [ok_word, "fail", "inconclusive"],
            "thresholds": {f"{ok_word}_max": ok_max, "fail_above": fail_above},
            "sides_declared": len(wanted), "sides_compared": len(compared),
            "max_abs_delta": max(deltas) if deltas else None,
            "mean_abs_delta": round(statistics.mean(deltas), 6) if deltas else None,
            "preconditions": checks, "set_aside": set_aside,
            "compared": sorted(compared, key=lambda row: (row["index"], row["side"]))}


def _candidate_summaries(run_dir, pattern=None):
    return [json.loads(Path(path).read_text(encoding="utf-8")) for path in summary_paths(run_dir, pattern)]


def criteria_preconditions(preview, criteria, candidate_dir, candidate_results, root, candidate_pattern=None):
    """The preconditions of a preview record that can be read from files: identity of the candidate run,
    token parity, finite values, and the SHA-256 of both reference parts. Returns (preconditions, label rows)."""
    root = Path(root)
    protocol = json.loads((root / preview["protocol"]["path"]).read_text(encoding="utf-8"))
    model, n_rows = protocol["model"], preview["inputs"]["batch"]["rows"]
    summaries = _candidate_summaries(candidate_dir, candidate_pattern)
    inference = [summary.get("inference") or {} for summary in summaries]
    revision_ok = bool(inference) and all(i.get("revision") == model["revision"]
                                          and i.get("revision_pinned") == model["revision"] for i in inference)
    dtype_ok = bool(inference) and all(i.get("dtype") == model["dtype"] for i in inference)
    complete = (bool(summaries) and all(summary.get("completed") is True for summary in summaries)
                and sorted(candidate_results) == list(range(1, n_rows + 1)))
    parity = [side.get("match") for result in candidate_results.values()
              for side in (result.get("token_parity") or {}).values()]
    values = [(result.get("probabilities") or {}).get(side) for result in candidate_results.values() for side in SIDES]
    finite = (len(values) == 2 * n_rows and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values))
    shas = []
    for name in ("landed_hosted_part", "landed_cpu_part"):
        entry = preview["inputs"][name]
        path = root / entry["path"]
        shas.append((name, path.is_file() and file_sha256(path) == entry["sha256"]))
    label_dir = (root / preview["inputs"]["landed_cpu_part"]["path"]).parent
    label_results = load_run(str(label_dir))[0] if label_dir.is_dir() else {}
    labels_ok = bool(label_results) and all(
        label_of(candidate_results.get(index)) is not None
        and label_of(candidate_results.get(index)) == label_of(label_results.get(index))
        for index in range(1, n_rows + 1))
    return [
        {"name": "the candidate records the pinned revision as loaded and as pinned", "holds": revision_ok,
         "detail": f"expected {model['revision']}"},
        {"name": "the candidate's dtype is the protocol's", "holds": dtype_ok, "detail": f"expected {model['dtype']}"},
        {"name": "the candidate is complete with the batch's row indices", "holds": complete,
         "detail": f"expected completed true and indices 1 to {n_rows}"},
        {"name": "token parity holds on every prompt", "holds": len(parity) == 2 * n_rows and all(p is True for p in parity),
         "detail": f"{sum(p is True for p in parity)} of {2 * n_rows} prompts match"},
        {"name": "every candidate target label equals the landed CPU part's label", "holds": labels_ok,
         "detail": f"label reference: {preview['inputs']['landed_cpu_part']['path']}"},
        {"name": "every candidate probability is present and finite", "holds": finite,
         "detail": f"{len(values)} values read"},
        *[{"name": f"{name} has the recorded SHA-256", "holds": ok, "detail": preview["inputs"][name]["path"]}
          for name, ok in shas],
        # The package version is a claim the summary makes about itself; the criteria name it, so it is listed.
        {"name": "the candidate records the pinned interp_engine version",
         "holds": (None if not inference else all(
             (i.get("environment") or {}).get("interp_engine") == criteria_engine_version(root) for i in inference)),
         "detail": f"expected {criteria_engine_version(root)} (constraints.txt)"},
    ], label_results


def criteria_engine_version(root):
    """The interp-engine version the lane is pinned to, read from constraints.txt; None when it is not pinned."""
    path = Path(root) / "constraints.txt"
    if not path.is_file():
        return None
    match = re.search(r"^interp-engine==(\S+)", path.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def main(argv=None):
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
    ap.add_argument("--criteria", default=None,
                    help="preview record whose parity_criteria were written before the run; adds a verdict block")
    ap.add_argument("--stage", default="stage_a", help="key under parity_criteria (default stage_a)")
    ap.add_argument("--comparison", default=None, help="key under the stage, e.g. hosted or cpu_bfloat16")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]),
                    help="directory the preview record's relative paths resolve against (default: the checkout)")
    args = ap.parse_args(argv)
    if bool(args.criteria) != bool(args.comparison):
        raise SystemExit("--criteria and --comparison are given together")

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
    if args.criteria:
        preview = json.loads(Path(args.criteria).read_text(encoding="utf-8"))
        criteria = preview["parity_criteria"][args.stage][args.comparison]
        expected_reference = Path(args.root) / criteria["reference"]["path"]
        preconditions, label_results = criteria_preconditions(
            preview, criteria, args.candidate, cand_results, args.root, args.candidate_pattern)
        reference_files = [Path(path).resolve() for path in summary_paths(args.reference, args.reference_pattern)]
        preconditions.append({
            "name": "the reference read is the file the criteria name", "detail": criteria["reference"]["path"],
            "holds": reference_files == [expected_reference.resolve()]
            and file_sha256(expected_reference) == criteria["reference"]["sha256"]})
        report["verdict"] = {"criteria": args.criteria, "criteria_status": preview["parity_criteria"].get("status"),
                             "stage": args.stage, "comparison": args.comparison,
                             **stage_verdict(rows, criteria, preconditions, label_results)}
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    print(text)


if __name__ == "__main__":
    main()
