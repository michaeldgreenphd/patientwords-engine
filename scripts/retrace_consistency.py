"""Test-retest consistency: the same phrase, traced more than once.

Groups every landed hosted-trace result by (model, clinical prompt, patient
prompt) across all of trace_out. Whenever the identical prompt pair was traced
in two or more runs (alias re-traces, re-measured sets), it reports how far the
probabilities moved and whether the top word changed. The forward pass of a
frozen model is deterministic, so any movement bounds the hosted instrument's
run-to-run stability rather than the model's.

Three layers are compared, each at the precision the files record
(probabilities are stored to 3 decimals):
- target-token probabilities and the full top-k spread lists (words + probs),
- the top word under each wording,
- clinical_mass, compared only between runs that share the same graph
  parameters (node budget and thresholds), because the attribution graph is
  parameter-sensitive by design; cross-parameter differences are reported
  separately and are not noise.

Writes ops/retrace_consistency.json; the printed last line is the summary
verdict. No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tierb_split import holdout_phrases  # noqa: E402  (script-style module)


def collect(trace_root: Path):
    """{(model, clinical, patient): [record, ...]} across every batch summary.

    Amendment 3 (2026-07-14): a Tier B holdout phrase is sealed from every
    public data file, keyed on the phrase and applied to every re-run stem
    (repeatability_r*, _txopus/_txplacebo), so it is skipped here.
    """
    sealed = holdout_phrases()
    groups = defaultdict(list)
    for part in sorted(trace_root.glob("*/batch_summary*.json")):
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if summary.get("backend") not in (None, "hosted"):
            continue  # logits runs are locally deterministic; this measures the hosted path
        model = summary.get("graph_model") or "gemma-2-2b"
        gp = summary.get("generation_params") or {}
        params_sig = json.dumps([gp.get("max_feature_nodes"), gp.get("node_threshold"),
                                 gp.get("edge_threshold")])
        for row in summary.get("results", []):
            prompts = row.get("prompts") or {}
            clin, pat = prompts.get("clinical"), prompts.get("patient")
            probs = row.get("probabilities") or {}
            if not clin or not pat or probs.get("clinical") is None:
                continue
            if clin in sealed:
                continue  # amendment 3: phrase-keyed holdout seal, all runs
            outputs = row.get("outputs") or {}
            spread = row.get("predictive_spread") or {}
            cmass = row.get("clinical_mass") or {}
            groups[(model, clin, pat)].append({
                "run": part.parent.name,
                "part": part.name,
                "params_sig": params_sig,
                "p_clinical": probs.get("clinical"),
                "p_patient": probs.get("patient"),
                "top_clinical": (outputs.get("clinical") or [None])[0],
                "top_patient": (outputs.get("patient") or [None])[0],
                "spread_sig": json.dumps([spread.get("clinical"), spread.get("patient")]),
                "cmass_clinical": cmass.get("clinical"),
                "cmass_patient": cmass.get("patient"),
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
        spread_sigs = {r["spread_sig"] for r in recs}
        # clinical_mass: same-parameter repeats only; cross-parameter runs are
        # expected to differ (pruning budget), flagged separately
        by_params = {}
        for r in recs:
            if r["cmass_clinical"] is not None:
                by_params.setdefault(r["params_sig"], []).append(r["cmass_clinical"])
        cmass_same = [max(v) - min(v) for v in by_params.values() if len(v) > 1]
        rows.append({
            "model": model,
            "clinical_prompt": clin[:70],
            "n_traces": len(recs),
            "runs": sorted(by_run),
            "spread_p_clinical": round(max(pc) - min(pc), 6) if len(pc) > 1 else None,
            "spread_p_patient": round(max(pp) - min(pp), 6) if len(pp) > 1 else None,
            "top_clinical_stable": len(tc) <= 1,
            "top_patient_stable": len(tp) <= 1,
            "spread_lists_identical": len(spread_sigs) <= 1,
            "cmass_same_params_spread": round(max(cmass_same), 6) if cmass_same else None,
            "cmass_param_variants": len(by_params),
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
    lists_ok = sum(1 for r in rows if r["spread_lists_identical"])
    cmass_spreads = [r["cmass_same_params_spread"] for r in rows
                     if r["cmass_same_params_spread"] is not None]
    multi_param = sum(1 for r in rows if r["cmass_param_variants"] > 1)
    payload = {
        "note": ("comparisons are at the precision the summaries record "
                 "(probabilities: 3 decimals); the retraced pairs are the ones that "
                 "happened to be traced repeatedly, not a designed sample"),
        "pairs_retraced": len(rows),
        "prob_spread_max": round(max(spreads), 6) if spreads else None,
        "prob_spread_mean": round(sum(spreads) / len(spreads), 6) if spreads else None,
        "top_word_stable_pairs": stable_tops,
        "spread_lists_identical_pairs": lists_ok,
        "cmass_same_params_spread_max": round(max(cmass_spreads), 6) if cmass_spreads else None,
        "cmass_same_params_pairs": len(cmass_spreads),
        "cmass_multi_param_pairs": multi_param,
        "rows": sorted(rows, key=lambda r: -(r["spread_p_clinical"] or 0)),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload["_provenance"] = provenance("retrace_consistency.py")
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not rows:
        print("retrace consistency: no phrase traced more than once yet")
    else:
        print(f"retrace consistency: {len(rows)} pairs traced 2+ times · "
              f"max prob spread {payload['prob_spread_max']} (stored precision) · "
              f"top word stable {stable_tops}/{len(rows)} · full spread lists identical "
              f"{lists_ok}/{len(rows)} · clinical_mass same-params max spread "
              f"{payload['cmass_same_params_spread_max']} over {len(cmass_spreads)} pairs")


if __name__ == "__main__":
    main()
