"""J-space schematic panels for methods Step 4 + technical Part 2: data/jspace.json.

Traces ONE worked example - a clinical/patient pair plus its LLM clinical-translation
- through the hosted J-lens and reports, per panel: the verbatim input, the divergent
trigger word to emphasize, the model's MIDDLE-LAYER open-vocab concepts (the lens's top
residual-stream tokens halfway up the stack), the model's next-word output, and whether
that output is the clinical target.

The three prompt texts + the clinical target come from a committed 2panel
`--show-mitigation` result (its `prompts.{clinical,patient,translated}` triple). The
concepts + output come from the committed J-lens save_raw of those same three prompts.

`empirical:true` is emitted ONLY when all three panels have a real committed lens trace;
otherwise the existing placeholder (empirical:false) is preserved untouched, so the
frontend keeps its hand-authored 'Illustrative schematic' figure. No medical vocabulary
lives in this file - every term is read from the committed data.

Usage:
  python scripts/export_jspace.py \
      --mitigation-batch urgency_downgrades_20260707T1 --mitigation-index 6 \
      --lens-batch jspace_worked_20260720 [--site ../patientwords]
"""

import argparse
import difflib
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jlens_position_scan as jps  # noqa: E402  (script-style; reuses jlens_readout as jps.jr)

# The residual-stream readout band, as a fraction of stack depth: the concepts are
# what the lens decodes HALFWAY up (not the final answer), so this stays central.
_MID_BAND = (0.35, 0.65)
_MAX_CONCEPTS = 6


def _clean_target(raw):
    """The bare target token from a mitigation `target_token` ('Output " x"' -> 'x')."""
    m = re.search(r'Output\s+"(.*)"', raw or "")
    return (m.group(1) if m else (raw or "")).strip()


def load_triple(mitigation_root, batch, index):
    """{clinical, patient, translated, target} for one mitigation pair, or None.

    Reads the committed 2panel --show-mitigation batch_summary parts and returns the
    verbatim prompt triple plus the clinical target for `index` (1-based)."""
    root = Path(mitigation_root) / batch
    for part in sorted(root.glob("batch_summary*.json")):
        try:
            results = json.loads(part.read_text(encoding="utf-8")).get("results", [])
        except (OSError, ValueError):
            continue
        for r in results:
            if r.get("index") != index:
                continue
            prompts = r.get("prompts") or {}
            if not (prompts.get("clinical") and prompts.get("patient")
                    and prompts.get("translated")):
                return None
            return {
                "clinical": prompts["clinical"],
                "patient": prompts["patient"],
                "translated": prompts["translated"],
                "target": _clean_target(r.get("target_token")),
            }
    return None


def divergent_word(reference, variant):
    """The word in `variant` that diverges from `reference` (the trigger to emphasize),
    or '' when they do not differ - the single most salient differing token, trimmed."""
    a, b = (reference or "").split(), (variant or "").split()
    span = []
    for op, _a0, _a1, b0, b1 in difflib.SequenceMatcher(a=a, b=b).get_opcodes():
        if op != "equal":
            span.extend(b[b0:b1])
    # the last content word of the differing span reads best as the trigger
    words = [w.strip(" ,;:.").strip() for w in span if w.strip(" ,;:.")]
    return words[-1] if words else ""


def _load_raw(path):
    try:
        with gzip.open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _final_entries(response):
    """Sorted (layer, top_tokens) at the answer (final) position, or []."""
    tokens = (response.get("tokens") or []) if isinstance(response, dict) else []
    if not tokens:
        return []
    final = tokens[-1]
    return sorted(
        (list(jps.jr._layer_entries_from_results(final, response))
         or list(jps.jr._iter_layer_entries(final))),
        key=lambda e: e[0],
    )


def mid_concepts(response, topk=3, max_concepts=_MAX_CONCEPTS):
    """The lens's top open-vocab tokens at the answer position across the MIDDLE
    layer band - what the model is 'considering' halfway up the stack. Deduped in
    first-seen order, capped. [] when the raw lacks answer-position layer entries."""
    entries = _final_entries(response)
    if not entries:
        return []
    n = len(entries)
    lo, hi = int(_MID_BAND[0] * (n - 1)), int(_MID_BAND[1] * (n - 1))
    seen, out = set(), []
    for layer, tops in entries[lo:hi + 1] or entries[n // 2:n // 2 + 1]:
        for t in (tops or [])[:topk]:
            w = jps.jr._token_string(t).strip()
            if w and w.lower() not in seen:
                seen.add(w.lower())
                out.append(w)
    return out[:max_concepts]


def answer_word(response):
    """The model's own top predicted next word (final-layer, answer position), or ''."""
    entries = _final_entries(response)
    if not entries:
        return ""
    _layer, tops = entries[-1]
    for t in (tops or []):
        w = jps.jr._token_string(t).strip()
        if w:
            return w
    return ""


def build_panel(raw, input_text, trigger, target):
    """One empirical panel from a raw lens response, or None when the raw is absent."""
    if raw is None:
        return None
    output = answer_word(raw)
    on_target = bool(target and jps.jr.target_match(output, jps.jr.target_variants(target)))
    return {
        "input": input_text,
        "trigger": trigger,
        "concepts": mid_concepts(raw),
        "output": output,
        "on_target": on_target,
    }


def raw_path(trace_root, lens_batch, model, index, side):
    return (Path(trace_root) / f"{lens_batch}__jlens_{model}" / "jlens_raw"
            / f"pair_{index:03d}_{side}.json.gz")


def build_payload(triple, trace_root, lens_batch, model, clin_idx, trans_idx):
    """The empirical data/jspace.json payload, or None when any panel's lens raw is
    missing (the caller then leaves the committed placeholder untouched).

    The worked-example lens batch traces the triple as two pairs:
      pair <clin_idx>: clinical (top) + patient (bottom)
      pair <trans_idx>: clinical (top) + translated (bottom)
    so clinical/patient come from pair clin_idx, translated from pair trans_idx's
    patient side."""
    clin_raw = _load_raw(raw_path(trace_root, lens_batch, model, clin_idx, "clinical"))
    pat_raw = _load_raw(raw_path(trace_root, lens_batch, model, clin_idx, "patient"))
    trans_raw = _load_raw(raw_path(trace_root, lens_batch, model, trans_idx, "patient"))

    clin_trigger = divergent_word(triple["patient"], triple["clinical"])
    pat_trigger = divergent_word(triple["clinical"], triple["patient"])
    panels = {
        "clinical": build_panel(clin_raw, triple["clinical"], clin_trigger, triple["target"]),
        "patient": build_panel(pat_raw, triple["patient"], pat_trigger, triple["target"]),
        "translation": build_panel(trans_raw, triple["translated"], "", triple["target"]),
    }
    if any(p is None for p in panels.values()):
        return None
    return {
        "empirical": True,
        "note": f"{model}, middle-layer readout.",
        "panels": panels,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mitigation-root", default="trace_out")
    parser.add_argument("--mitigation-batch", default="urgency_downgrades_20260707T1",
                        help="a committed 2panel --show-mitigation batch (clinical/patient/"
                             "translated triple + target)")
    parser.add_argument("--mitigation-index", type=int, default=6,
                        help="1-based pair index of the worked example within that batch")
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--lens-batch", default="jspace_worked_20260720",
                        help="the J-lens save_raw batch that traced the worked-example triple")
    parser.add_argument("--model", default="gemma-2-2b")
    parser.add_argument("--clin-index", type=int, default=1,
                        help="lens-batch pair index holding clinical(top)+patient(bottom)")
    parser.add_argument("--trans-index", type=int, default=2,
                        help="lens-batch pair index holding clinical(top)+translated(bottom)")
    parser.add_argument("--out", default="data/jspace.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    triple = load_triple(args.mitigation_root, args.mitigation_batch, args.mitigation_index)
    if not triple:
        print(f"refused: no clinical/patient/translated triple for "
              f"{args.mitigation_batch}#{args.mitigation_index}")
        return 3

    payload = build_payload(triple, args.trace_root, args.lens_batch, args.model,
                            args.clin_index, args.trans_index)
    if payload is None:
        # The worked-example lens trace has not landed yet: preserve the committed
        # placeholder (empirical:false) exactly, per the frontend's disclaimer contract.
        print(f"note: worked-example lens raw for {args.lens_batch} not committed yet; "
              f"leaving the empirical:false placeholder untouched")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8")
    print(f"jspace: empirical panels for {args.mitigation_batch}#{args.mitigation_index} "
          f"(target {triple['target']!r}) -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "jspace.json"
        if site_copy.parent.is_dir():
            site_copy.write_text(text, encoding="utf-8")
            print(f"site copy -> {site_copy}")
        else:
            print(f"note: site dir {site_copy.parent} absent; skipped site copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
