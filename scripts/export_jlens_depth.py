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
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp  # noqa: E402

_TIERB_START = tierb_start_stamp()
_ACCEPT_CACHE = {}


def _sealed(dataset, index):
    """Amendment 1/3 phrase-keyed holdout seal for every published aggregate:
    True iff (dataset, index) is a Tier B pair whose ACCEPTED prompt hashes
    holdout. Applied at every export surface (blocks, translation, steering)."""
    if not is_tierb_batch(dataset or "", _TIERB_START):
        return False
    if dataset not in _ACCEPT_CACHE:
        fp = Path("data/simulated") / f"{dataset}.json"
        try:
            _ACCEPT_CACHE[dataset] = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _ACCEPT_CACHE[dataset] = None
    pairs = _ACCEPT_CACHE[dataset]
    idx = index or 0
    if not pairs or not (0 < idx <= len(pairs)):
        return False
    return is_holdout(pairs[idx - 1].get("top_prompt"))

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
    summary = json.loads(path.read_text(encoding="utf-8"))
    # Amendment 1/3: sealed holdout pairs never enter blocks, counts, examples,
    # or the translation class join (this reader feeds all of them).
    if is_tierb_batch(stem, _TIERB_START):
        summary["results"] = [r for r in summary["results"]
                              if not _sealed(stem, r.get("index"))]
    return summary, str(path)


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


def build_block(stem, label, annotate_index=None):
    """One unit-rows block for a lens-measured set."""
    summary, path = load_summary(stem)
    pairs = [{"index": r["index"], "class": r["patient_depth_class"],
              "target": (r["target_token"] or "").strip()}
             for r in summary["results"]]
    counts = {}
    for u in pairs:
        counts[u["class"]] = counts.get(u["class"], 0) + 1
    return {
        "id": stem, "label": label, "counts": counts, "pairs": pairs,
        "annotation": (units_annotation(summary["results"], annotate_index)
                       if annotate_index else None),
        "source": path,
    }


def translation_split(stems, rows_path="urgency_shift.json", model="gemma-2-2b"):
    """Depth class x translation recovery, joined per pair on lens-measured
    sets whose collector rows carry the translated third panel. Exploratory;
    one row per (set, index), preferring the row that has a recovery value."""
    bundle = json.loads(Path(rows_path).read_text(encoding="utf-8"))
    joined = []
    for stem in stems:
        try:
            summary, _ = load_summary(stem)
        except OSError:
            continue
        classes = {r["index"]: r["patient_depth_class"] for r in summary["results"]}
        best = {}
        for row in bundle.get("rows", []):
            if (row.get("batch") != stem or row.get("model") != model
                    or row.get("tierb_split") == "holdout"):  # Amendment 1/3 seal
                continue
            idx = row.get("index")
            if idx not in classes:
                continue
            rec = row.get("urgency_recovery")
            if idx not in best or (rec is not None and best[idx] is None):
                best[idx] = rec
        for idx, rec in sorted(best.items()):
            if rec is not None:
                joined.append({"set": stem, "index": idx,
                               "class": classes[idx], "recovery": rec})
    by_class = {}
    for j in joined:
        by_class.setdefault(j["class"], []).append(j["recovery"])
    return {
        "source_rows": rows_path,
        "sets": stems,
        "pairs": joined,
        "by_class": {c: {"n": len(v), "mean_recovery": round(sum(v) / len(v), 3)}
                     for c, v in sorted(by_class.items())},
        "note": ("exploratory; recovery = expected care-urgency tier of the translated "
                 "panel minus the everyday wording (probability-weighted, reviewed v1 "
                 "tiers), split by the lens depth class of the everyday wording"),
    }


def pick_examples(blocks_spec, max_suppressed=4, max_absent=2):
    """Worked examples for the site, selected by rule rather than by hand:
    every lost-late (suppressed) pair, capped, strongest clinical hold first;
    plus the never-formed pairs whose clinical wording holds best at the
    output - the sharpest contrasts the readout can show."""
    candidates = []
    for stem, label in blocks_spec:
        summary, _ = load_summary(stem)
        for r in summary["results"]:
            cls = r.get("patient_depth_class")
            if cls not in ("suppressed", "absent"):
                continue
            clin = r["depth"]["clinical"]
            pat = r["depth"]["patient"]
            clin_last = clin[-1]["target_rank"] if clin else None
            winner = next((e["top1"] for e in reversed(pat) if e.get("top1")), None)
            _, snippet = contrast_labels(r["prompts"]["clinical"], r["prompts"]["patient"])
            candidates.append({
                "set": label.split("·")[0].strip(), "stem": stem, "index": r["index"],
                "class": cls,
                "target": (r["target_token"] or "").strip(),
                "winner": (winner or "").strip() or None,
                "snippet": snippet,
                "prompts": r["prompts"],
                "clin_ranks": rank_map(clin), "pat_ranks": rank_map(pat),
                "clin_last_rank": clin_last,
            })
    def hold(c):  # smaller = stronger clinical hold at the output
        return (c["clin_last_rank"] if c["clin_last_rank"] is not None else 99, c["index"])
    suppressed = sorted([c for c in candidates if c["class"] == "suppressed"], key=hold)
    absent = sorted([c for c in candidates if c["class"] == "absent"
                     and c["clin_last_rank"] is not None], key=hold)
    return suppressed[:max_suppressed] + absent[:max_absent]


def steering_split(trace_root=Path("trace_out")):
    """Pair-level swap restoration by lens class from the landed steering pilot
    (EXPLORATORY; owner-approved for the router's steering column 2026-07-17).
    Dedupes spec items measured in more than one pilot run; a pair is restored
    if any swap call read the target at rank 1. Class names map to the census
    labels: hijack -> suppressed, capture -> absent."""
    pairs = {}
    for part in sorted(trace_root.glob("*jsteer_*/jsteer_summary.part_*.json")):
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for r in summary.get("results", []):
            if _sealed(r.get("dataset"), r.get("spec_index")):
                continue  # Amendment 1/3: sealed holdout out of the steering aggregate
            key = (r.get("dataset"), r.get("spec_index"))
            e = pairs.setdefault(key, {"class": r.get("class"), "unres": False,
                                       "restored": False, "measured": False})
            if r.get("steer_unresolvable"):
                e["unres"] = True
                continue
            swaps = {k: v for k, v in (r.get("calls") or {}).items() if k.endswith("_swap")}
            if swaps:
                e["measured"] = True
                if any(v.get("final_rank") == 1 for v in swaps.values()):
                    e["restored"] = True
    name_map = {"hijack": "suppressed", "capture": "absent", "held": "retained"}
    by_class = {}
    for e in pairs.values():
        cls = name_map.get(e["class"], e["class"])
        c = by_class.setdefault(cls, {"n": 0, "restored": 0, "unresolvable": 0})
        if e["measured"]:
            c["n"] += 1
            c["restored"] += int(e["restored"])
        elif e["unres"]:
            c["unresolvable"] += 1
    if not by_class:
        return None
    return {
        "_": ("EXPLORATORY pilot (docs/lens_steering_design.md): swap intervention, pair-level "
              "rank-1 restoration at either frozen layer. Unresolvable = multi-wordpiece target, "
              "excluded before comparison. Amendment 4 registers the confirmatory version on "
              "post-adoption batches."),
        "intervention": "swap",
        "by_class": by_class,
    }


def build_payload(blocks_spec, exemplar_stem, exemplar_index, annotate=None):
    """blocks_spec: list of (stem, label); annotate: (stem, index) or None."""
    blocks = []
    for stem, label in blocks_spec:
        ann_idx = annotate[1] if annotate and annotate[0] == stem else None
        blocks.append(build_block(stem, label, ann_idx))

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
        "blocks": blocks,
        "units": blocks[0],  # back-compat alias: first block is the newest batch
        "translation": translation_split([b["id"] for b in blocks]),
        "steering": steering_split(),
        "examples": pick_examples(blocks_spec),
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
    parser.add_argument("--block", action="append", required=True, metavar="STEM=LABEL",
                        help="lens-measured set to include, newest first (repeatable)")
    parser.add_argument("--exemplar-stem", required=True)
    parser.add_argument("--exemplar-index", type=int, required=True)
    parser.add_argument("--annotate", default=None, metavar="STEM:INDEX",
                        help="pair whose data derives the unit-rows example line")
    parser.add_argument("--out", default="data/jlens_depth.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    blocks_spec = []
    for spec in args.block:
        stem, _, label = spec.partition("=")
        blocks_spec.append((stem, label or stem))
    annotate = None
    if args.annotate:
        stem, _, idx = args.annotate.partition(":")
        annotate = (stem, int(idx))

    try:
        payload = build_payload(blocks_spec, args.exemplar_stem, args.exemplar_index,
                                annotate=annotate)
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
