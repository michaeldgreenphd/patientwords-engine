"""Post-hoc interpretability analyses over landed trace outputs ($0, offline).

Four analyses feeding docs/findings_synthesis.md:

1. named-features   - which tagged features carry the effect, by frequency in
                      top attribution paths and by causal use in the boost arms
2. consistency      - cross-model per-pair penalty agreement (trace vs logits)
3. tokenization     - does target-token piece length predict the penalty?
4. depth            - where categories live: feature depth by category, plus
                      circuit overlap between the paired prompts

Reads every trace_out/*/batch_summary.part_*.json; writes a JSON bundle and
prints a readable summary. No medical vocabulary lives in this file - every
label it prints comes from the trace data.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

PATH_FEATURE = re.compile(r"\[L(\d+)·([A-Z])\]\s*([^→]+)")


def load_parts(trace_root: Path):
    """Yield (dir_name, summary_dict) for every landed chunk summary."""
    for part in sorted(trace_root.glob("*/batch_summary.part_*.json")):
        try:
            yield part.parent.name, json.loads(part.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def path_features(result: dict):
    """(layer, category_letter, label) triples from every panel's top path."""
    for panel, path in (result.get("top_path") or {}).items():
        if not isinstance(path, str):
            continue
        for layer, cat, label in PATH_FEATURE.findall(path):
            yield panel, int(layer), cat, label.strip().rstrip(".| ")


def named_features(summaries):
    """Feature labels ranked by how often they anchor a top attribution path,
    split by category; plus the exact feature set the boost arms steered."""
    by_cat: dict[str, Counter] = defaultdict(Counter)
    layer_of: dict[str, list[int]] = defaultdict(list)
    boosted: Counter = Counter()
    boosted_meta: dict[str, dict] = {}
    for _, summary in summaries:
        for r in summary.get("results", []):
            for _panel, layer, cat, label in path_features(r):
                by_cat[cat][label] += 1
                layer_of[label].append(layer)
            for f in (r.get("steering_boost") or {}).get("boosted_features", []) or []:
                key = f"L{f['layer']}/{f['index']}"
                boosted[key] += 1
                boosted_meta.setdefault(key, {"label": f.get("label", ""),
                                              "mass": f.get("mass")})
    out = {}
    for cat, counter in by_cat.items():
        out[cat] = [{"label": lbl, "count": c,
                     "mean_layer": round(sum(layer_of[lbl]) / len(layer_of[lbl]), 1)}
                    for lbl, c in counter.most_common(15)]
    out["boosted"] = [{"feature": k, "uses": v, **boosted_meta[k]}
                      for k, v in boosted.most_common(12)]
    return out


def consistency(summaries):
    """Per-pair penalty agreement between the traced base model and each
    logits-only sibling run of the same batch stem."""
    runs: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for dirname, summary in summaries:
        stem, _, suffix = dirname.partition("__")
        model = summary.get("graph_model", "gemma-2-2b")
        if suffix and model == "gemma-2-2b":
            continue  # same-model condition arm (e.g. __context), not a sibling model
        for r in summary.get("results", []):
            lp = r.get("language_penalty")
            if isinstance(lp, (int, float)):
                runs[(stem, model)][r["index"]] = lp
    base = "gemma-2-2b"
    rows = []
    others = sorted({m for (_, m) in runs if m != base})
    for other in others:
        xs, ys = [], []
        for (stem, model), by_idx in runs.items():
            if model != other:
                continue
            base_map = runs.get((stem, base), {})
            for idx, lp in by_idx.items():
                if idx in base_map:
                    xs.append(base_map[idx])
                    ys.append(lp)
        if xs:
            same_sign = sum(1 for x, y in zip(xs, ys) if (x >= 0) == (y >= 0))
            rows.append({"model": other, "n": len(xs),
                         "pearson_r": None if (r := pearson(xs, ys)) is None else round(r, 3),
                         "sign_agreement": round(same_sign / len(xs), 3)})
    return rows


def tokenization(summaries):
    """Does the target's first-piece length predict the base-model penalty?
    A strong link would mean the effect is partly a tokenizer artifact."""
    lens, pens = [], []
    for dirname, summary in summaries:
        if "__" in dirname:
            continue  # base model only
        for r in summary.get("results", []):
            lp = r.get("language_penalty")
            tgt = r.get("target_token") or ""
            m = re.search(r'"\s*(.+?)"', tgt)
            if not (isinstance(lp, (int, float)) and m):
                continue
            lens.append(len(m.group(1).strip()))
            pens.append(lp)
    r = pearson(lens, pens)
    return {"n": len(lens), "pearson_r_len_vs_penalty": None if r is None else round(r, 3)}


def depth(summaries):
    """Where each category lives (feature depth in layers), and how much of
    the circuit the paired prompts share."""
    layers: dict[str, list[int]] = defaultdict(list)
    shared_frac = []
    for dirname, summary in summaries:
        if "__" in dirname:
            continue
        for r in summary.get("results", []):
            for _panel, layer, cat, _label in path_features(r):
                layers[cat].append(layer)
            cd = r.get("circuit_diff") or {}
            tot = sum(cd.get(k, 0) for k in ("shared_features", "unique_to_a", "unique_to_b"))
            if tot:
                shared_frac.append(cd["shared_features"] / tot)
    out = {cat: {"n": len(v), "mean_layer": round(sum(v) / len(v), 2),
                 "min": min(v), "max": max(v)}
           for cat, v in sorted(layers.items())}
    if shared_frac:
        sf = sorted(shared_frac)
        out["circuit_overlap"] = {
            "n_pairs": len(sf),
            "mean_shared_fraction": round(sum(sf) / len(sf), 3),
            "median_shared_fraction": round(sf[len(sf) // 2], 3),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace-root", default="trace_out", type=Path)
    ap.add_argument("--out", default=None, type=Path,
                    help="write the JSON bundle here")
    args = ap.parse_args()
    summaries = list(load_parts(args.trace_root))
    bundle = {
        "named_features": named_features(summaries),
        "consistency": consistency(summaries),
        "tokenization": tokenization(summaries),
        "depth": depth(summaries),
        "n_chunk_summaries": len(summaries),
    }
    if args.out:
        args.out.write_text(json.dumps(bundle, indent=1, ensure_ascii=False),
                            encoding="utf-8")
    print(json.dumps(bundle, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
