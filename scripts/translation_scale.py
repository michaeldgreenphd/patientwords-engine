"""Translation recovery at scale: per-model recovery from the txcorpus logits runs.

The txcorpus batch (scripts/translate_corpus.py) is a 2panel set whose
top_prompt is the HAIKU-TRANSLATED (clinical-worded) sentence and whose
bottom_prompt is the ORIGINAL patient sentence. logits_eval maps
clinical=top_prompt (translated) and patient=bottom_prompt (patient), so a
SINGLE txcorpus run of a model yields both sides of the recovery for every
phrase — no cross-join to any other batch is needed or used:

  recovery = p(target | translated) - p(target | patient)   [probabilities.clinical - probabilities.patient]

Reproducibility (2026-07-19 rewrite): every number here is recomputed from the
committed txcorpus trace_out. n is the count of committed measured rows for the
model; nothing is dropped by a join, and nothing is read from an off-repo
source. The earlier version cross-joined each translated row to a separate
source-batch patient run — which both mislabeled the sides and silently dropped
rows (reporting n=154/290 from 350 committed rows), so its numbers could not be
reproduced from committed data. That approach is retired.

`gap_closed` is intentionally null: the txcorpus "clinical" side IS the
translated rewrite, so clinical-patient == recovery and any gap_closed would be
a tautological 1.0. A meaningful gap_closed would need an independent
true-clinical baseline the self-contained txcorpus measurement does not carry;
rather than invent one, the field is null and n_with_headroom counts phrases
the translation meaningfully helped (recovery > 1pp).

Everything is EXPLORATORY (owner request 2026-07-14): the txcorpus stem never
enters confirmatory populations, and urgency_shift.py skips its trace dirs.
Writes ops/translation_scale.json (+ optional site copy). Offline, $0.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance

ENGINE = Path(__file__).resolve().parents[1]

# Model -> family, for the frontend's base / instruction-tuned / medical grouping.
# Classification only (no medical vocabulary); models absent here render as "other".
MODEL_FAMILY = {
    "gemma-2-2b": "base",
    "olmo-2-1b": "base",
    "llama-3.2-3b": "base",
    "gemma-2-2b-it": "instruction-tuned",
    "gemma-3-4b-it": "instruction-tuned",
    "qwen3-1.7b": "instruction-tuned",
    "qwen3-4b": "instruction-tuned",
    "medgemma-4b-it": "medical",
    "meditron3-8b": "medical",
    "apertus-8b-meditronfo": "medical",
}

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
        model = model_suffix or data.get("graph_model") or "gemma-2-2b"
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
    """{(stem, index): {'formed': layer|None}} from landed lens summaries."""
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
    """Formation-depth recovery (gemma-2-2b, EXPLORATORY): for corpus sentences
    read by the lens under BOTH wordings, did translation move the answer from
    never-forms to forms? Uses the txcorpus lens pull (translated side) joined to
    the source batch's lens pull (patient side); gemma-2-2b only."""
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
    corpora = [c for c in sorted(simulated_dir.glob("txcorpus_*.json"))
               if not c.name.endswith(".report.json")]
    if not corpora:
        return {"_": "no txcorpus batch landed yet", "corpora": [], "per_model": {}}
    tx_results = _results(trace_root, "txcorpus_")

    per_model: dict[str, list[dict]] = {}
    measured_stems: set[str] = set()
    for corpus_path in corpora:
        cstem = corpus_path.stem
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        for i, pair in enumerate(corpus, start=1):
            models = {m for (s, m, idx) in tx_results if s == cstem and idx == i}
            for model in models:
                r = tx_results.get((cstem, model, i))
                if not r:
                    continue
                pr = r.get("probabilities") or {}
                # clinical = top_prompt = translated; patient = bottom_prompt = patient
                p_translated, p_patient = pr.get("clinical"), pr.get("patient")
                if p_translated is None or p_patient is None:
                    continue
                target = _tok(r.get("target_token"))
                top_translated, top_patient = _tops(r)
                measured_stems.add(cstem)
                per_model.setdefault(model, []).append({
                    "recovery": p_translated - p_patient,
                    "top_restored": bool(target and top_translated == target and top_patient != target),
                    "top_lost": bool(target and top_patient == target and top_translated != target),
                })

    summary = {}
    for model, rows in sorted(per_model.items()):
        recs = [r["recovery"] for r in rows]
        summary[model] = {
            "n": len(rows),
            "family": MODEL_FAMILY.get(model, "other"),
            "mean_recovery": round(statistics.fmean(recs), 4),
            "median_recovery": round(statistics.median(recs), 4),
            "share_recovery_positive": round(sum(1 for v in recs if v > 0) / len(rows), 4),
            "n_with_headroom": sum(1 for v in recs if v > 0.01),
            "mean_gap_closed": None,  # see module docstring: undefined self-contained
            "top_restored": sum(1 for r in rows if r["top_restored"]),
            "top_lost": sum(1 for r in rows if r["top_lost"]),
        }
    return {
        "_": ("EXPLORATORY translation recovery at scale, recomputed from committed "
              "txcorpus logits (2026-07-19). recovery = p(target|translated) - "
              "p(target|patient), both from the SAME txcorpus run per model "
              "(top_prompt=translated, bottom_prompt=patient); no cross-join, no "
              "dropped rows, n = committed measured rows. n_with_headroom = phrases "
              "the translation meaningfully helped (recovery > 1pp). top_restored / "
              "top_lost = phrases whose top-1 prediction returns to / leaves the "
              "clinical target under translation vs patient wording. mean_gap_closed "
              "is null: the translated side IS the clinical rewrite, so there is no "
              "independent clinical baseline to close a gap against."),
        "corpora": sorted(measured_stems),
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
    result["_provenance"] = provenance("translation_scale.py")
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for model, s in result["per_model"].items():
        print(f"{model} [{s['family']}]: n={s['n']} mean recovery {s['mean_recovery']:+.4f} "
              f"(positive {s['share_recovery_positive']:.0%}) "
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
