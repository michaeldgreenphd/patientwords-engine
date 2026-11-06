"""The PAB frame spec's preregistered endpoints on the traced harvest batch (exploratory, 2026-11-06).

`docs/pab_frame_spec_20260805.md` fixed two directional endpoints before any frame was built:
  1. harvested low-literacy spans show a negative mean language penalty relative to their paired high-literacy spans;
  2. formation depth is later or weaker for the low-literacy spans.
The 52 entries of `data/pab/pabharvest_20260807T025446Z.json` (13 pairs x 4 carrier frames) were circuit-traced and
lens-read on gemma-2-2b in August, and never reported against these endpoints. Owner decision on the decision page,
2026-11-06 (pab-step1: "Yes, write the report").

Sides: each entry's top prompt is the high-literacy span and its bottom prompt the low-literacy span, in the same
carrier frame (`scripts/pab_build_frames.py`). The study's language penalty is p(target | bottom) - p(target | top)
(`medlang_circuits/batch_eval.py`), so a negative penalty means the low-literacy wording lost probability on the
clinical target.

- Unit: the pair, not the entry. The four frames of a pair share one utterance per arm. A pair's statistic is the
  mean over its entries that have a value.
- Missing values: entries screened out at the preregistered 0.02 threshold were never traced on the low-literacy
  side. They have no penalty, are counted by reason, and are never counted as zero.
- Exact reads: each penalty is checked to be read on exactly the entry's anchor token. The traces predate the
  2026-10-07 exact-read change.
- Formation (endpoint 2) uses the census's own rules (`scripts/jlens_insights.py`): `formation_layer` (readable for 2
  consecutive layers in the top-8 window), `lock_in_layer` and the `classify` taxonomy. "Later or weaker" for a pair
  means the low-literacy side forms later than the high-literacy side, or never forms where the high side does.
- Comparison: the same model's language penalty on the study's own observational pairs (the engine's urgency row
  file, `urgency_shift.json`: gemma-2-2b rows of observational `pairs_<STAMP>` batches minus the outcome-selected
  stamps, holdout phrases excluded, one mean per phrase).

License boundary: the harvested utterances are CC-BY-NC-4.0-derived. This script prints and writes counts, pair
hashes (`pair_key`) and frame ids only, never utterance text.

Usage:
  python scripts/pab_endpoints.py --out /tmp/pab_endpoints.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from jlens_insights import classify, formation_layer, lock_in_layer  # noqa: E402
from sign_test_exact import sign_test  # noqa: E402
from urgency_headline import population  # noqa: E402

STEM = "pabharvest_20260807T025446Z"
BATCH = ROOT / "data" / "pab" / f"{STEM}.json"
TRACE = ROOT / "trace_out" / STEM
LENS = ROOT / "trace_out" / f"{STEM}__jlens_gemma-2-2b"
URGENCY_ROWS = ROOT / "urgency_shift.json"


def _bare(token: Any) -> str | None:
    if not isinstance(token, str):
        return None
    t = token.strip()
    if t.startswith('Output "') and t.endswith('"'):
        t = t[len('Output "'):-1]
    return t.strip() or None


def _results(folder: Path, pattern: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for part in sorted(folder.glob(pattern)):
        for r in json.loads(part.read_text(encoding="utf-8")).get("results", []):
            out[r["index"]] = r
    return out


def entries() -> list[dict[str, Any]]:
    """One record per batch entry: its pair, frame, anchor, screening status, penalty and lens formation."""
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    traces = _results(TRACE, "batch_summary*.json")
    lens = _results(LENS, "jlens_summary*.json")
    out = []
    for i, e in enumerate(batch, start=1):
        t = traces.get(i) or {}
        screening = (t.get("screening") or {}).get("status")
        pen = t.get("language_penalty")
        read = _bare(t.get("target_token"))
        rec: dict[str, Any] = {
            "index": i, "pair_key": e["pair_key"], "frame_id": e["frame_id"],
            "traced": i in traces, "screening": screening,
            "penalty": pen if isinstance(pen, (int, float)) else None,
            "read_exact": (read == _bare(e.get("target_clinical_token"))) if read else None,
        }
        if rec["penalty"] is None:
            probs = t.get("probabilities") or {}
            rec["missing_reason"] = ("not traced" if i not in traces else
                                     "screened out at 0.02 (low-literacy side never traced)"
                                     if screening == "screened_out" else
                                     "passed screening; low-literacy probability not recorded"
                                     if probs.get("clinical") is not None and probs.get("patient") is None else
                                     "no penalty recorded")
        lr = lens.get(i)
        if lr:
            status = lr.get("parse_status")
            ok = all(v == "ok" for v in status.values()) if isinstance(status, dict) else status in (None, "ok")
            depth = lr.get("depth") or {}
            hi, lo = depth.get("clinical") or [], depth.get("patient") or []
            if ok and hi and lo:
                row = {"clin_formed": formation_layer(hi), "pat_formed": formation_layer(lo),
                       "pat_final_rank": lo[-1].get("target_rank")}
                rec["lens"] = {"high_formed": row["clin_formed"], "low_formed": row["pat_formed"],
                               "low_lock_in": lock_in_layer(lo), "n_layers": len(lo), "class": classify(row)}
            else:
                rec["lens"] = None
                rec["lens_missing_reason"] = "parse not ok" if not ok else "a side has no depth profile"
        else:
            rec["lens"] = None
            rec["lens_missing_reason"] = "not lens-read"
        out.append(rec)
    return out


def endpoint_penalty(recs: list[dict[str, Any]]) -> dict[str, Any]:
    by_pair: dict[str, list[float]] = defaultdict(list)
    for r in recs:
        if r["penalty"] is not None:
            by_pair[r["pair_key"]].append(r["penalty"])
    means = {k: sum(v) / len(v) for k, v in by_pair.items()}
    neg = sum(1 for m in means.values() if m < 0)
    pos = sum(1 for m in means.values() if m > 0)
    vals = sorted(means.values())
    return {
        "pairs_total": len({r["pair_key"] for r in recs}),
        "pairs_with_a_penalty": len(means),
        "entries_with_a_penalty": sum(len(v) for v in by_pair.values()),
        "pair_mean_of_means": round(sum(vals) / len(vals), 4) if vals else None,
        "pair_median": round(statistics.median(vals), 4) if vals else None,
        "pairs_negative": neg, "pairs_positive": pos, "pairs_zero": len(vals) - neg - pos,
        "sign_test_p_two_sided": sign_test(neg, pos),
        "preregistered_direction": "negative",
        "pair_means": {k: round(v, 4) for k, v in sorted(means.items())},
    }


def endpoint_formation(recs: list[dict[str, Any]]) -> dict[str, Any]:
    lens = [r for r in recs if r.get("lens")]
    classes = Counter(r["lens"]["class"] for r in lens)
    per_pair: dict[str, Counter] = defaultdict(Counter)
    for r in lens:
        hi, lo = r["lens"]["high_formed"], r["lens"]["low_formed"]
        if hi is None and lo is None:
            verdict = "neither forms"
        elif hi is not None and lo is None:
            verdict = "low later or weaker"
        elif hi is None:
            verdict = "low earlier or stronger"
        elif lo > hi:
            verdict = "low later or weaker"
        elif lo < hi:
            verdict = "low earlier or stronger"
        else:
            verdict = "same layer"
        per_pair[r["pair_key"]][verdict] += 1
    later = earlier = 0
    for c in per_pair.values():
        d = c["low later or weaker"] - c["low earlier or stronger"]
        later += d > 0
        earlier += d < 0
    return {
        "entries_lens_read": len(lens),
        "low_side_class": dict(sorted(classes.items())),
        "entry_verdicts": dict(sorted(Counter(v for c in per_pair.values() for v in c.elements()).items())),
        "pairs_low_later_majority": later, "pairs_low_earlier_majority": earlier,
        "pairs_no_direction": len(per_pair) - later - earlier,
        "sign_test_p_two_sided": sign_test(later, earlier),
        "preregistered_direction": "low later or weaker",
    }


def study_reference() -> dict[str, Any] | None:
    """gemma-2-2b language penalty on the study's observational pairs, one mean per phrase."""
    if not URGENCY_ROWS.is_file():
        return None
    rows = json.loads(URGENCY_ROWS.read_text(encoding="utf-8"))["rows"]
    held = {r["clinical_prompt"] for r in rows if r.get("tierb_split") == "holdout"}
    by_phrase: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if (r.get("model") == "gemma-2-2b" and population(r.get("batch")) == "observational"
                and r.get("clinical_prompt") not in held and isinstance(r.get("language_penalty"), (int, float))):
            by_phrase[r.get("clinical_prompt") or f"{r['batch']}#{r['index']}"].append(r["language_penalty"])
    vals = sorted(sum(v) / len(v) for v in by_phrase.values())
    if not vals:
        return None
    q = statistics.quantiles(vals, n=4)
    return {"phrases": len(vals), "mean": round(sum(vals) / len(vals), 4), "median": round(statistics.median(vals), 4),
            "quartiles": [round(x, 4) for x in q], "share_negative": round(sum(1 for v in vals if v < 0) / len(vals), 4),
            "source": "urgency_shift.json rows (engine root), gemma-2-2b, observational population"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    recs = entries()
    report = {
        "exploratory": True, "batch": STEM, "spec": "docs/pab_frame_spec_20260805.md",
        "entries": len(recs),
        "missing_penalty": dict(Counter(r.get("missing_reason") for r in recs if r["penalty"] is None)),
        "penalty_reads_exact": dict(Counter(str(r["read_exact"]) for r in recs if r["penalty"] is not None)),
        "missing_lens": dict(Counter(r.get("lens_missing_reason") for r in recs if not r.get("lens"))),
        "endpoint_1_penalty": endpoint_penalty(recs),
        "endpoint_2_formation": endpoint_formation(recs),
        "study_reference_gemma_2_2b": study_reference(),
        "entries_detail": [{k: v for k, v in r.items()} for r in recs],
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "entries_detail"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
