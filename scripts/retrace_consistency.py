"""Test-retest consistency: the same phrase, traced more than once.

Groups every landed hosted-trace result by (model, clinical prompt, patient
prompt) across all of trace_out. Whenever the identical prompt pair was traced
in two or more runs (alias re-traces, re-measured sets), it reports how far the
probabilities moved and whether the top word changed. The forward pass of a
frozen model is deterministic, so any movement bounds the hosted instrument's
run-to-run stability rather than the model's.

Writes ops/retrace_consistency.json; the printed last line is the summary
verdict. No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def collect(trace_root: Path):
    """{(model, clinical, patient): [record, ...]} across every batch summary."""
    groups = defaultdict(list)
    for part in sorted(trace_root.glob("*/batch_summary*.json")):
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if summary.get("backend") not in (None, "hosted"):
            continue  # logits runs are locally deterministic; this measures the hosted path
        model = summary.get("graph_model") or "gemma-2-2b"
        for row in summary.get("results", []):
            prompts = row.get("prompts") or {}
            clin, pat = prompts.get("clinical"), prompts.get("patient")
            probs = row.get("probabilities") or {}
            if not clin or not pat or probs.get("clinical") is None:
                continue
            outputs = row.get("outputs") or {}
            groups[(model, clin, pat)].append({
                "run": part.parent.name,
                "part": part.name,
                "p_clinical": probs.get("clinical"),
                "p_patient": probs.get("patient"),
                "top_clinical": (outputs.get("clinical") or [None])[0],
                "top_patient": (outputs.get("patient") or [None])[0],
            })
    return groups


def compare(groups):
    """Per re-traced pair: max prob spread and top-word agreement across runs."""
    rows = []
    for (model, clin, _pat), records in groups.items():
        runs = {r["run"] for r in records}
        if len(runs) < 2:
            continue
        # one record per run (chunk parts of the same run are one measurement)
        by_run = {}
        for r in records:
            by_run.setdefault(r["run"], r)
        recs = list(by_run.values())
        if len(recs) < 2:
            continue
        pc = [r["p_clinical"] for r in recs if r["p_clinical"] is not None]
        pp = [r["p_patient"] for r in recs if r["p_patient"] is not None]
        tc = {r["top_clinical"] for r in recs if r["top_clinical"]}
        tp = {r["top_patient"] for r in recs if r["top_patient"]}
        rows.append({
            "model": model,
            "clinical_prompt": clin[:70],
            "n_traces": len(recs),
            "runs": sorted(by_run),
            "spread_p_clinical": round(max(pc) - min(pc), 6) if len(pc) > 1 else None,
            "spread_p_patient": round(max(pp) - min(pp), 6) if len(pp) > 1 else None,
            "top_clinical_stable": len(tc) <= 1,
            "top_patient_stable": len(tp) <= 1,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--out", default="ops/retrace_consistency.json")
    args = parser.parse_args()

    rows = compare(collect(Path(args.trace_root)))
    spreads = [r["spread_p_clinical"] for r in rows if r["spread_p_clinical"] is not None] + \
              [r["spread_p_patient"] for r in rows if r["spread_p_patient"] is not None]
    stable_tops = sum(1 for r in rows if r["top_clinical_stable"] and r["top_patient_stable"])
    payload = {
        "pairs_retraced": len(rows),
        "prob_spread_max": round(max(spreads), 6) if spreads else None,
        "prob_spread_mean": round(sum(spreads) / len(spreads), 6) if spreads else None,
        "top_word_stable_pairs": stable_tops,
        "rows": sorted(rows, key=lambda r: -(r["spread_p_clinical"] or 0)),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not rows:
        print("retrace consistency: no phrase traced more than once yet")
    else:
        print(f"retrace consistency: {len(rows)} pairs traced 2+ times · "
              f"max prob spread {payload['prob_spread_max']} · mean {payload['prob_spread_mean']} · "
              f"top word stable on {stable_tops}/{len(rows)} pairs")


if __name__ == "__main__":
    main()
