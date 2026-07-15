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


PERSISTENCE = 2  # consecutive readable layers = formation (adopted 2026-07-14)


def _formation(layers, persistence=PERSISTENCE):
    """First layer where the target stays readable for `persistence` layers;
    same rule as jlens_insights.formation_layer (kept in sync by test)."""
    ranks = [rec.get("target_rank") for rec in layers]
    run = 0
    for i, r in enumerate(ranks):
        run = run + 1 if r is not None else 0
        if run >= persistence:
            return layers[i - persistence + 1]["layer"]
    return None


def _lens_profiles(trace_root: Path, stem_prefix: str) -> dict:
    """{(stem, index): {'formed': layer|None}} from landed lens summaries
    (gemma-2-2b, patient/translated side = the summary's 'patient' profile)."""
    out = {}
    for part in sorted(trace_root.glob(f"{stem_prefix}*__jlens_gemma-2-2b/jlens_summary.part_*.json")):
        stem = part.parent.name.split("__jlens_")[0]
        data = json.loads(part.read_text(encoding="utf-8"))
        for r in data.get("results", []):
            status = r.get("parse_status")
            if isinstance(status, dict) and any(v != "ok" for v in status.values()):
                continue
            pat = (r.get("depth") or {}).get("patient") or []
            if pat:
                out[(stem, r["index"])] = {"formed": _formation(pat)}
    return out


def lens_recovery(trace_root: Path, simulated_dir: Path) -> dict:
    """Formation-depth recovery: for corpus sentences read by the lens under
    BOTH wordings (patient side via the source batch's regular pull,
    translated side via a txcorpus pull), did translation move the answer
    from never-forms to forms? EXPLORATORY (pre-A2 phrases)."""
    src_lens = _lens_profiles(trace_root, "pairs_")
    tx_lens = _lens_profiles(trace_root, "txcorpus_")
    if not tx_lens:
        return {"n_paired": 0, "_": "no translated-side lens readouts landed yet"}
    joined = []
    for corpus_path in sorted(simulated_dir.glob("txcorpus_*.json")):
        if corpus_path.name.endswith(".report.json"):
            continue
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        cstem = corpus_path.stem
        for i, pair in enumerate(corpus, start=1):
            gen = pair.get("generation") or {}
            tx = tx_lens.get((cstem, i))
            src = src_lens.get((gen.get("source_batch"), gen.get("source_index")))
            if tx is None or src is None:
                continue
            joined.append({"patient_formed": src["formed"], "translated_formed": tx["formed"]})
    never = [j for j in joined if j["patient_formed"] is None]
    return {
        "_": ("Lens view of translation, gemma-2-2b, EXPLORATORY (phrases predate "
              "amendment 2 adoption): formation = readable for 2 consecutive layers "
              "in the top-8 window, per the adopted counting rules."),
        "n_paired": len(joined),
        "patient_never_formed": len(never),
        "recovered_to_formed": sum(1 for j in never if j["translated_formed"] is not None),
        "formed_both": sum(1 for j in joined
                           if j["patient_formed"] is not None and j["translated_formed"] is not None),
        "lost_by_translation": sum(1 for j in joined
                                   if j["patient_formed"] is not None and j["translated_formed"] is None),
    }


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
    parser.add_argument("--site", default=None,
                        help="site repo root; also writes data/translation_scale.json there")
    args = parser.parse_args()
    result = analyze(Path(args.trace_root), Path(args.simulated_dir))
    result["lens_recovery"] = lens_recovery(Path(args.trace_root), Path(args.simulated_dir))
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for model, s in result["per_model"].items():
        print(f"{model}: n={s['n']} mean recovery {s['mean_recovery']:+.4f} "
              f"(positive {s['share_recovery_positive']:.0%}) "
              f"gap closed {s['mean_gap_closed']} "
              f"top restored {s['top_restored']} / lost {s['top_lost']}")
    lr = result["lens_recovery"]
    if lr.get("n_paired"):
        print(f"lens: {lr['recovered_to_formed']} of {lr['patient_never_formed']} "
              f"never-formed phrases now form; {lr['lost_by_translation']} lost")
    print(f"-> {args.out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "translation_scale.json"
        site_copy.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        print(f"site copy -> {site_copy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
