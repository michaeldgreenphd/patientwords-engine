"""Translation recovery at scale: join txcorpus logits results to patient rows.

The txcorpus batch (scripts/translate_corpus.py) holds clinical prompts paired
with HAIKU-TRANSLATED sentences; logits-eval measures p(target) for both sides
per model. This script joins each translated measurement back to the ORIGINAL
patient measurement of the same phrase (source_batch/source_index recorded at
translation time) and reports, per model:

  recovery        = p(target | translated) - p(target | patient)
  gap closed      = recovery / (p(target | clinical) - p(target | patient))
  top restoration = share of pairs whose top prediction matches the clinical
                    top under the translated sentence but not the patient one

Everything is exploratory scale-measurement (owner request 2026-07-14); the
txcorpus stem never enters confirmatory populations, and urgency_shift.py
skips its trace dirs. Writes ops/translation_scale.json. Offline, $0.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]

_TOK_RE = re.compile(r'Output "\s*(.*)"$')


def _tok(label):
    if not isinstance(label, str):
        return None
    m = _TOK_RE.match(label)
    return (m.group(1) if m else label).strip() or None


def _results(trace_root: Path, stem_prefix: str) -> dict:
    """{(stem, model, index): result} for every summary under matching dirs."""
    out = {}
    for part in sorted(trace_root.glob(f"{stem_prefix}*/batch_summary*.json")):
        run_dir = part.parent.name
        stem, _, model_suffix = run_dir.partition("__")
        data = json.loads(part.read_text(encoding="utf-8"))
        model = data.get("graph_model") or model_suffix or "gemma-2-2b"
        for r in data.get("results", []):
            out[(stem, model, r["index"])] = r
    return out


def _tops(r):
    sp = r.get("predictive_spread") or {}
    top_c = _tok((sp.get("clinical") or [[None]])[0][0])
    top_p = _tok((sp.get("patient") or [[None]])[0][0])
    return top_c, top_p


def analyze(trace_root: Path, simulated_dir: Path) -> dict:
    corpora = sorted(simulated_dir.glob("txcorpus_*.json"))
    corpora = [c for c in corpora if not c.name.endswith(".report.json")]
    if not corpora:
        return {"_": "no txcorpus batch landed yet", "per_model": {}}
    tx_results = _results(trace_root, "txcorpus_")
    src_results = _results(trace_root, "pairs_")

    per_model: dict[str, list[dict]] = {}
    for corpus_path in corpora:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        cstem = corpus_path.stem
        for i, pair in enumerate(corpus, start=1):
            gen = pair.get("generation") or {}
            src_key_base = (gen.get("source_batch"), gen.get("source_index"))
            models = {m for (s, m, idx) in tx_results if s == cstem and idx == i}
            for model in models:
                tx = tx_results.get((cstem, model, i))
                src = src_results.get((src_key_base[0], model, src_key_base[1]))
                if not tx or not src:
                    continue
                txp = tx.get("probabilities") or {}
                srp = src.get("probabilities") or {}
                p_tr, p_cl = txp.get("patient"), txp.get("clinical")
                p_pat = srp.get("patient")
                if p_tr is None or p_pat is None or p_cl is None:
                    continue
                top_c_src, top_p_src = _tops(src)
                _, top_tr = _tops(tx)
                per_model.setdefault(model, []).append({
                    "recovery": p_tr - p_pat,
                    "gap": p_cl - p_pat,
                    "patient_top_ok": bool(top_c_src and top_p_src == top_c_src),
                    "translated_top_ok": bool(top_c_src and top_tr == top_c_src),
                })

    summary = {}
    for model, rows in sorted(per_model.items()):
        recs = [r["recovery"] for r in rows]
        gaps = [r for r in rows if r["gap"] > 0.01]  # phrases with real headroom
        summary[model] = {
            "n": len(rows),
            "mean_recovery": round(statistics.fmean(recs), 4),
            "median_recovery": round(statistics.median(recs), 4),
            "share_recovery_positive": round(sum(1 for v in recs if v > 0) / len(rows), 4),
            "n_with_headroom": len(gaps),
            "mean_gap_closed": (round(statistics.fmean(
                [min(2.0, max(-2.0, g["recovery"] / g["gap"])) for g in gaps]), 4)
                if gaps else None),
            "top_restored": sum(1 for r in rows
                                if r["translated_top_ok"] and not r["patient_top_ok"]),
            "top_lost": sum(1 for r in rows
                            if r["patient_top_ok"] and not r["translated_top_ok"]),
        }
    return {
        "_": ("EXPLORATORY translation recovery at scale: haiku-translated corpus "
              "(txcorpus batches) joined to the original patient logits rows per "
              "phrase and model. recovery = p(target|translated) - p(target|patient); "
              "gap_closed clipped to [-2, 2] and computed only where the clinical-"
              "patient gap exceeds 1pp. top_restored / top_lost count top-prediction "
              "changes relative to the clinical top. Owner request 2026-07-14."),
        "corpora": [c.stem for c in corpora],
        "per_model": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default=str(ENGINE / "trace_out"))
    parser.add_argument("--simulated-dir", default=str(ENGINE / "data/simulated"))
    parser.add_argument("--out", default=str(ENGINE / "ops/translation_scale.json"))
    args = parser.parse_args()
    result = analyze(Path(args.trace_root), Path(args.simulated_dir))
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for model, s in result["per_model"].items():
        print(f"{model}: n={s['n']} mean recovery {s['mean_recovery']:+.4f} "
              f"(positive {s['share_recovery_positive']:.0%}) "
              f"gap closed {s['mean_gap_closed']} "
              f"top restored {s['top_restored']} / lost {s['top_lost']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
