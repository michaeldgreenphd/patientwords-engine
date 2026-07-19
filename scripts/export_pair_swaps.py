"""Per-pair patient swap + baseline sentence for the census table: data/jlens_swaps.json.

The depth-census table on the technical page (#ad-pairs) lists each pair's
clinical target. This adds, per pair, the colloquial patient swap (the differing
patient-side span vs the clinical prompt) and the full verbatim baseline (patient)
sentence for the on-hover contextual frame. Keyed "<batch_stem>#<index>" so the
frontend joins the census blocks in data/jlens_depth.json; block ids are read
from that payload so the swap map stays scoped to what the census shows.

Reads only the committed pair batches under data/simulated. No medical
vocabulary lives in this file (terms come from the data).

Usage:
  python scripts/export_pair_swaps.py [--depth ../patientwords/data/jlens_depth.json] \
      [--out data/jlens_swaps.json] [--site ../patientwords]
"""

import argparse
import difflib
import json
from pathlib import Path


def patient_swap(top_prompt, bottom_prompt, width=44):
    """The patient-side differing span vs the clinical prompt (the colloquial
    swap), trimmed at a word boundary. None when the prompts do not differ."""
    a = (top_prompt or "").split()
    b = (bottom_prompt or "").split()
    span = []
    for op, _a0, _a1, b0, b1 in difflib.SequenceMatcher(a=a, b=b).get_opcodes():
        if op != "equal":
            span.extend(b[b0:b1])
    text = " ".join(span).strip(" ,;:.")
    if not text:
        return None
    if len(text) <= width:
        return text
    cut = text[:width]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut) + "…"


def build_swaps(block_stems, simulated_dir):
    """{ "<stem>#<index>": {target, swap, baseline} } for every pair in the
    referenced batches that exists under simulated_dir."""
    out = {}
    for stem in block_stems:
        path = Path(simulated_dir) / f"{stem}.json"
        try:
            pairs = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(pairs, list):
            continue
        for index, pair in enumerate(pairs, start=1):
            if not isinstance(pair, dict):
                continue
            out[f"{stem}#{index}"] = {
                "target": (pair.get("target_clinical_token") or "").strip() or None,
                "swap": patient_swap(pair.get("top_prompt"), pair.get("bottom_prompt")),
                "baseline": (pair.get("bottom_prompt") or "").strip() or None,
            }
    return out


def block_stems(depth_path):
    """Block ids from a jlens_depth.json payload (the census the table renders)."""
    try:
        payload = json.loads(Path(depth_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [b.get("id") for b in payload.get("blocks", []) if b.get("id")]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--simulated-dir", default="data/simulated")
    parser.add_argument("--depth", default="../patientwords/data/jlens_depth.json",
                        help="census payload whose block ids scope the swap map")
    parser.add_argument("--out", default="data/jlens_swaps.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    stems = block_stems(args.depth)
    if not stems:
        print(f"refused: no block ids in {args.depth}")
        return 3
    swaps = build_swaps(stems, args.simulated_dir)
    if not swaps:
        print(f"refused: no pairs resolved under {args.simulated_dir}")
        return 3

    payload = {
        "_": ("patient swap + baseline per (batch#index) for the depth-census table; "
              "swap = differing patient-side span, baseline = verbatim patient sentence"),
        "swaps": swaps,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"jlens swaps: {len(swaps)} pairs -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "jlens_swaps.json"
        if site_copy.parent.is_dir():
            site_copy.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
            print(f"site copy -> {site_copy}")
        else:
            print(f"note: site dir {site_copy.parent} absent; skipped site copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
