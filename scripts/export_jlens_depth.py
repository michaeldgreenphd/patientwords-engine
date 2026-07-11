"""Site dataset for the depth-readout sections: data/jlens_depth.json.

Joins the hosted Jacobian-lens summaries with the activation-patching grid
into the single file the frontend's depth figures read (start-here unit rows,
methods combined lens + causal figure). Every number on those pages traces
here, and everything here is computed from committed run artifacts.

Contents:
- units: per-pair depth class for the unit rows (one batch, all pairs);
- exemplar: one pair measured by BOTH instruments - lens ranks per layer for
  both phrasings, plus the per-layer max patched probability between the two
  measured levels (clean = clinical wording, corrupt = everyday wording);
- integrity + credit notes the pages surface verbatim.

The exemplar is refused (exit 3) when its patch grid is degenerate:
clean_prob <= corrupt_prob (the inverted-denominator seam from grid run 1)
or an all-null recovery matrix. The caller picks the exemplar; the guard
keeps a bad pair from silently reaching the site.

Usage:
  python scripts/export_jlens_depth.py \
      --units-batch pairs_20260711T051145Z \
      --exemplar-stem urgency_downgrades_20260707T1 --exemplar-index 4 \
      [--out data/jlens_depth.json] [--site ../patientwords]

No medical vocabulary lives in this file.
"""

import argparse
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

CLASS_LABELS = {"retained": "kept", "suppressed": "lost late", "absent": "never formed"}
METHOD_CREDIT = ("Jacobian lens: Gurnee et al., Transformer Circuits, 2026; reference "
                 "implementation github.com/anthropics/jacobian-lens (Apache-2.0); hosted "
                 "readout by neuronpedia.org. The lens is a readout, not an intervention; "
                 "causal evidence comes from activation patching.")
INTEGRITY_NOTE = ("The gemma-2-2b-it model id returns lens readouts identical to the base "
                  "model across all measured pairs (verified 2026-07-11); one model is "
                  "reported until Neuronpedia confirms separate hosts.")


def load_summary(stem, model="gemma-2-2b"):
    path = Path("trace_out") / f"{stem}__jlens_{model}" / "jlens_summary.part_01.json"
    return json.loads(path.read_text(encoding="utf-8")), str(path)


def contrast_labels(clinical, patient, width=34):
    """The differing span of each prompt, for the lane sub-labels. Derived
    from the prompts themselves so the labels stay data-traceable."""
    matcher = difflib.SequenceMatcher(a=clinical.split(), b=patient.split())
    a_span, b_span = [], []
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op != "equal":
            a_span.extend(clinical.split()[a0:a1])
            b_span.extend(patient.split()[b0:b1])
    def trim(s, fallback):
        s = s or fallback
        if len(s) <= width:
            return s
        cut = s[:width]
        return cut.rsplit(" ", 1)[0] if " " in cut else cut  # word boundary
    return (trim(" ".join(a_span), clinical).rstrip(",;:"),
            trim(" ".join(b_span), patient).rstrip(",;:"))


def rank_map(profile):
    """{layer: rank} for layers where the target is readable."""
    return {str(e["layer"]): e["target_rank"] for e in profile if e.get("target_rank")}


def patch_join(stem, index):
    """(patched per-layer max, clean, corrupt, path) for one pair from the
    patching grid; ValueError when the grid cannot support the figure."""
    path = Path("trace_out") / f"{stem}__patch" / f"batch_summary.part_{index:02d}.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    result = next(r for r in summary["results"] if r["index"] == index)
    p = result["patching"]
    clean, corrupt = p["clean_prob"], p["corrupt_prob"]
    if clean is None or corrupt is None or clean <= corrupt:
        raise ValueError(f"pair {index}: degenerate patch grid (clean={clean}, corrupt={corrupt})")
    per_layer = []
    for row in p["patched_prob"]:
        vals = [v for v in row if v is not None]
        per_layer.append(round(max(vals), 4) if vals else None)
    if not any(v is not None for v in per_layer):
        raise ValueError(f"pair {index}: all-null patched_prob matrix")
    return per_layer, round(clean, 4), round(corrupt, 4), str(path)


def units_annotation(results, index):
    """One-line example for the unit rows, derived from the pair's own data:
    the shared prompt tail plus target versus the everyday wording's actual
    top word at the output layer. None when the pair cannot support it."""
    r = next((x for x in results if x["index"] == index), None)
    if not r or r.get("patient_depth_class") != "suppressed":
        return None
    tail = " ".join(r["prompts"]["patient"].split()[-2:])
    final = next((e for e in reversed(r["depth"]["patient"]) if e.get("top1")), None)
    if not final:
        return None
    target = (r["target_token"] or "").strip()
    winner = (final["top1"] or "").strip()
    return {"index": index,
            "text": f"“{tail} {target}” becomes “{tail} {winner}”"}


def build_payload(units_batch, exemplar_stem, exemplar_index, annotate_index=19):
    units_summary, units_path = load_summary(units_batch)
    units = [{"index": r["index"], "class": r["patient_depth_class"],
              "target": (r["target_token"] or "").strip()}
             for r in units_summary["results"]]
    counts = {}
    for u in units:
        counts[u["class"]] = counts.get(u["class"], 0) + 1
    annotation = units_annotation(units_summary["results"], annotate_index)

    ex_summary, ex_lens_path = load_summary(exemplar_stem)
    ex = next(r for r in ex_summary["results"] if r["index"] == exemplar_index)
    patched, clean, corrupt, patch_path = patch_join(exemplar_stem, exemplar_index)
    label_c, label_p = contrast_labels(ex["prompts"]["clinical"], ex["prompts"]["patient"])

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "gemma-2-2b",
        "scope": ("hosted Jacobian lens, top-8 readout per layer; exploratory measurement; "
                  "Amendment 1 exploration split only"),
        "method_credit": METHOD_CREDIT,
        "integrity_note": INTEGRITY_NOTE,
        "class_labels": CLASS_LABELS,
        "units": {
            "batch": units_batch,
            "counts": counts,
            "pairs": units,
            "annotation": annotation,
            "source": units_path,
        },
        "exemplar": {
            "stem": exemplar_stem,
            "index": exemplar_index,
            "target": (ex["target_token"] or "").strip(),
            "prompts": ex["prompts"],
            "labels": {"clinical": label_c, "patient": label_p},
            "clin_ranks": rank_map(ex["depth"]["clinical"]),
            "pat_ranks": rank_map(ex["depth"]["patient"]),
            "layers": 26,
            "clean_prob": clean,
            "corrupt_prob": corrupt,
            "patched": patched,
            "sources": {"lens": ex_lens_path, "patch": patch_path},
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--units-batch", required=True, help="stem of the unit-rows batch")
    parser.add_argument("--exemplar-stem", required=True)
    parser.add_argument("--exemplar-index", type=int, required=True)
    parser.add_argument("--out", default="data/jlens_depth.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    try:
        payload = build_payload(args.units_batch, args.exemplar_stem, args.exemplar_index)
    except ValueError as exc:
        print(f"refused: {exc}")
        return 3
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out}")
    if args.site:
        site = Path(args.site) / "data" / "jlens_depth.json"
        site.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"site copy -> {site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
