"""Site dataset for the per-position transport view: data/jlens_transport.json.

Promotes the per-position lens scan (scripts/jlens_position_scan.py, until now
an ops-only artifact) to a site payload the frontend can read:

- exemplar: one pair, the FULL position x layer legibility grid under both
  phrasings (target rank within the top-N readout at every prompt position and
  layer, or null when absent) - the clinical answer legible somewhere inside
  the sentence even where it never reaches the answer position;
- census: across every pair with committed raw, how the clinical target's
  legibility resolves at the final (answer) position vs. earlier positions -
  reaches_answer / transport_gap (legible mid-sentence but never at the answer)
  / never_readable, per phrasing.

EXPLORATORY. The Jacobian lens is a correlational readout, not causal evidence;
nothing here is an intervention. Reads only committed
trace_out/*__jlens_<model>/jlens_raw/*.json.gz (runs fired with --save-raw), so
coverage is limited to those runs. The per-position transport question and the
top-K window sensitivity are the referee-adjacent items scripts/
jlens_position_scan.py already answers; this file only joins that output to an
exemplar grid and writes the site copy, mirroring export_jlens_depth.

Method credit is pulled from the summary's method_credit field, never typed.
No medical vocabulary lives in this file.

Usage:
  python scripts/export_jlens_transport.py \
      --model gemma-2-2b [--exemplar-batch pairs_20260711T051145Z --exemplar-index 2] \
      [--out data/jlens_transport.json] [--site ../patientwords]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jlens_position_scan as jps  # noqa: E402  (script-style; imports jlens_readout as jps.jr)
from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp  # noqa: E402

METHOD_CREDIT_FALLBACK = (
    "Jacobian lens: Gurnee et al., Transformer Circuits, 2026; reference "
    "implementation github.com/anthropics/jacobian-lens (Apache-2.0); hosted "
    "readout by neuronpedia.org."
)
SCOPE = ("hosted Jacobian lens, per-position top-N readout; EXPLORATORY, "
         "correlational (not an intervention); coverage limited to save_raw runs")

_TIERB_START = tierb_start_stamp()
_ACCEPT_CACHE = {}


def _sealed(batch, index):
    """Amendment 1/3 holdout seal (mirrors export_jlens_depth): True iff
    (batch, index) is a Tier B pair whose ACCEPTED prompt hashes holdout, so
    confirmatory-holdout pairs never enter this exported census or exemplar."""
    if not is_tierb_batch(batch or "", _TIERB_START):
        return False
    if batch not in _ACCEPT_CACHE:
        fp = Path("data/simulated") / f"{batch}.json"
        try:
            _ACCEPT_CACHE[batch] = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _ACCEPT_CACHE[batch] = None
    pairs = _ACCEPT_CACHE[batch]
    idx = index or 0
    if not pairs or not (0 < idx <= len(pairs)):
        return False
    return is_holdout(pairs[idx - 1].get("top_prompt"))


# --------------------------------------------------------------------------- #
# Pure functions (unit-tested offline against fake raw responses)
# --------------------------------------------------------------------------- #


def position_layer_grid(response, target, topn=8):
    """The full position x layer legibility grid for one raw lens response.

    For every prompt position, the target's 1-based rank within the top-N lens
    readout at each layer (None when the target is absent from that cell). Uses
    the same parser + match rules as jlens_readout, so 'readable' means exactly
    what the depth census means. Returns tokens (position/token per row), grid
    ([n_positions][n_layers] of rank|None), first_layer (per position, the
    earliest layer the target enters the window, or None), layers (the layer
    numbers, columns of grid), and answer_position (index of the final row)."""
    variants = jps.jr.target_variants(target)
    tokens_meta, grid, first_layer = [], [], []
    layers = None
    for tok in response.get("tokens", []) if isinstance(response, dict) else []:
        entries = sorted(
            (list(jps.jr._layer_entries_from_results(tok, response))
             or list(jps.jr._iter_layer_entries(tok))),
            key=lambda e: e[0],
        )
        if layers is None and entries:
            layers = [layer for layer, _ in entries]
        ranks, formed_at = [], None
        for layer, tops in entries:
            rank = None
            for i, item in enumerate(tops[:topn]):
                if jps.jr.target_match(jps.jr._token_string(item), variants):
                    rank = i + 1
                    break
            ranks.append(rank)
            if rank is not None and formed_at is None:
                formed_at = layer
        tokens_meta.append({"position": tok.get("position"), "token": tok.get("token")})
        grid.append(ranks)
        first_layer.append(formed_at)
    return {
        "tokens": tokens_meta,
        "grid": grid,
        "first_layer": first_layer,
        "layers": layers or [],
        "answer_position": (len(tokens_meta) - 1) if tokens_meta else None,
    }


def side_transport(response, target):
    """Per-phrasing transport summary for one raw response, reusing the landed
    scan primitives so it agrees with ops/jlens_position_scan.json exactly.

    final_readable: target in the top-8 window at the final (answer) position.
    n_mid_readable: non-final positions where it is readable.
    transport_gap: readable at some non-final position but NOT at the answer -
      the concept is present inside the sentence yet is not carried to the point
      where the model commits to the next word.
    windows_first_layer: first readable layer at the answer position per top-K."""
    positions = jps.position_profiles(response, target)
    final = positions[-1] if positions else None
    non_final = [p for p in positions[:-1] if p["best_rank"] is not None]
    final_readable = bool(final and final["best_rank"] is not None)
    return {
        "final_readable": final_readable,
        "n_mid_readable": len(non_final),
        "transport_gap": bool(non_final) and not final_readable,
        "windows_first_layer": jps.window_profile(response, target),
    }


def summarize_side(records):
    """Census counts over a list of side_transport dicts for one phrasing."""
    return {
        "n": len(records),
        "reaches_answer": sum(1 for r in records if r["final_readable"]),
        "transport_gap": sum(1 for r in records if r["transport_gap"]),
        "never_readable": sum(1 for r in records
                              if not r["final_readable"] and r["n_mid_readable"] == 0),
        "mid_readable_any": sum(1 for r in records if r["n_mid_readable"] > 0),
    }


def pick_exemplar_index(per_pair):
    """Choose the exemplar by rule, sharpest transport story first: a patient
    transport_gap (concept legible mid-sentence, gone at the answer); else a
    pair the clinical wording reads out somewhere but the patient wording never
    does (the absent contrast); else the pair with the most patient mid-sentence
    positions; else the first pair. Returns (batch, index) or None."""
    def has(entry, side, key):
        s = entry.get(side)
        return bool(s and s.get(key))

    for want in ("transport_gap",):
        for e in per_pair:
            if has(e, "patient", want):
                return e["batch"], e["index"]
    for e in per_pair:
        pat, clin = e.get("patient"), e.get("clinical")
        if (pat and not pat["final_readable"] and pat["n_mid_readable"] == 0
                and clin and (clin["final_readable"] or clin["n_mid_readable"] > 0)):
            return e["batch"], e["index"]
    ranked = sorted(
        (e for e in per_pair if e.get("patient")),
        key=lambda e: e["patient"]["n_mid_readable"], reverse=True)
    if ranked:
        return ranked[0]["batch"], ranked[0]["index"]
    return (per_pair[0]["batch"], per_pair[0]["index"]) if per_pair else None


def rank_exemplars(per_pair, limit=5):
    """Up to `limit` strong contrast exemplars as (batch, index), best story
    first, one per target.

    A strong example needs a clinical-side signal (the answer reads out
    somewhere) and a clear patient-side contrast: a transport gap, an outright
    absence, or (failing those) a later/weaker patient reading. Deduped by
    target so the set shows different concepts, not the same word repeated."""
    def score(entry):
        clin, pat = entry.get("clinical"), entry.get("patient")
        if not clin or not pat:
            return None
        if not (clin["final_readable"] or clin["n_mid_readable"] > 0):
            return None  # no clinical signal to contrast against
        value = float(clin["n_mid_readable"])  # a richer clinical trace reads clearer
        if pat["transport_gap"]:
            value += 100
        elif not pat["final_readable"] and pat["n_mid_readable"] == 0:
            value += 50 + (10 if clin["final_readable"] else 0)  # clean absence contrast
        elif pat["final_readable"]:
            value += 20  # both wordings read out (hedge / later)
        return value

    scored = [(score(e), e) for e in per_pair]
    scored = [(s, e) for s, e in scored if s is not None]
    scored.sort(key=lambda se: se[0], reverse=True)
    out, seen = [], set()
    for _value, entry in scored:
        target = (entry.get("target") or "").lower()
        if target in seen:
            continue
        seen.add(target)
        out.append((entry["batch"], entry["index"]))
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- #
# I/O (edges)
# --------------------------------------------------------------------------- #


def collect_pairs(scan_result, model):
    """Per-pair transport records for `model` from a jps.scan() result, sealed
    Tier B holdout pairs dropped. Each entry: {batch, index, target,
    clinical|patient: side-summary or None}."""
    by_pair = {}
    for s in scan_result.get("scans", []):
        if s.get("model") != model or _sealed(s.get("batch"), s.get("index")):
            continue
        by_pair.setdefault((s["batch"], s["index"]), {})[s["side"]] = s
    per_pair = []
    for (batch, index), sides in sorted(by_pair.items()):
        ref = sides.get("clinical") or sides.get("patient") or {}
        entry = {"batch": batch, "index": index,
                 "target": (ref.get("target_token") or "").strip() or None}
        for side_name in ("clinical", "patient"):
            s = sides.get(side_name)
            entry[side_name] = None if not s else {
                "final_readable": s["final_readable"],
                "n_mid_readable": s["n_non_final_readable_positions"],
                "transport_gap": s["transport_gap"],
                "windows_first_layer": s["windows_first_layer"],
            }
        per_pair.append(entry)
    return per_pair


def load_raw(trace_root, batch, model, index, side):
    """The committed raw response for one (batch, model, index, side), or None."""
    path = (Path(trace_root) / f"{batch}__jlens_{model}" / "jlens_raw"
            / f"pair_{index:03d}_{side}.json.gz")
    if not path.is_file():
        return None
    return jps._load_raw(path)


def load_summary_meta(trace_root, batch, model):
    """(method_credit, top_n) from the batch's lens summary; fallbacks if absent."""
    path = Path(trace_root) / f"{batch}__jlens_{model}" / "jlens_summary.part_01.json"
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return METHOD_CREDIT_FALLBACK, 8
    return summary.get("method_credit") or METHOD_CREDIT_FALLBACK, summary.get("top_n") or 8


def build_exemplar(trace_root, batch, index, model, topn, target):
    """Both-phrasing position x layer grids for the exemplar pair, or None when
    its raw is missing."""
    clin_raw = load_raw(trace_root, batch, model, index, "clinical")
    pat_raw = load_raw(trace_root, batch, model, index, "patient")
    if clin_raw is None or pat_raw is None:
        return None
    clin = position_layer_grid(clin_raw, target, topn)
    pat = position_layer_grid(pat_raw, target, topn)
    return {
        "batch": batch,
        "index": index,
        "target": (target or "").strip() or None,
        "layers": clin.get("layers") or pat.get("layers") or [],
        "sides": {"clinical": clin, "patient": pat},
        "transport": {
            "clinical": side_transport(clin_raw, target),
            "patient": side_transport(pat_raw, target),
        },
    }


def build_payload(trace_root, model, exemplar_batch=None, exemplar_index=None, max_exemplars=5):
    """The data/jlens_transport.json payload, or None when no raw exists for
    the model (caller refuses rather than overwrite the committed site copy)."""
    scan_result = jps.scan(Path(trace_root))
    per_pair = collect_pairs(scan_result, model)
    if not per_pair:
        return None

    clin_records = [e["clinical"] for e in per_pair if e["clinical"]]
    pat_records = [e["patient"] for e in per_pair if e["patient"]]

    if exemplar_index is not None:
        chosen = [(exemplar_batch or per_pair[0]["batch"], exemplar_index)]
    else:
        chosen = rank_exemplars(per_pair, max_exemplars)
        if not chosen:
            fallback = pick_exemplar_index(per_pair)
            chosen = [fallback] if fallback else []
    exemplars = []
    for batch, index in chosen:
        entry = next((e for e in per_pair if e["batch"] == batch and e["index"] == index), None)
        target = entry["target"] if entry else None
        _, topn = load_summary_meta(trace_root, batch, model)
        built = build_exemplar(trace_root, batch, index, model, topn, target)
        if built:
            exemplars.append(built)

    batches = sorted({e["batch"] for e in per_pair})
    method_credit, topn = load_summary_meta(trace_root, batches[0], model)
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "scope": SCOPE,
        "method_credit": method_credit,
        "top_n": topn,
        "windows": scan_result.get("windows", ["1", "2", "4", "8"]),
        "n_pairs": len(per_pair),
        "census": {
            "clinical": summarize_side(clin_records),
            "patient": summarize_side(pat_records),
        },
        "exemplar": (exemplars[0] if exemplars else None),  # back-compat: first of the set
        "exemplars": exemplars,
        "per_pair": per_pair,
        "source": f"trace_out/*__jlens_{model}/jlens_raw (committed save_raw responses)",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--model", default="gemma-2-2b")
    parser.add_argument("--exemplar-batch", default=None,
                        help="batch stem for the exemplar pair (default: inferred)")
    parser.add_argument("--exemplar-index", type=int, default=None,
                        help="1-based pair index for a single explicit exemplar")
    parser.add_argument("--max-exemplars", type=int, default=5,
                        help="how many strong exemplars to emit for the selector (default 5)")
    parser.add_argument("--out", default="data/jlens_transport.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    payload = build_payload(args.trace_root, args.model,
                            args.exemplar_batch, args.exemplar_index,
                            max_exemplars=args.max_exemplars)
    if payload is None:
        # Mirror jlens_insights F-H08: a sparse checkout with no committed raw
        # must never overwrite the published transport payload with an empty one.
        print(f"refused: no committed jlens_raw for {args.model} under {args.trace_root} "
              "- not overwriting outputs")
        return 3

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    exs = payload.get("exemplars") or []
    print(f"jlens transport: {payload['n_pairs']} pairs · "
          f"patient transport_gap {payload['census']['patient']['transport_gap']} "
          f"never {payload['census']['patient']['never_readable']} · "
          f"{len(exs)} exemplars [" + ", ".join((e.get("target") or "?") for e in exs) + f"] -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "jlens_transport.json"
        if site_copy.parent.is_dir():
            site_copy.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
            print(f"site copy -> {site_copy}")
        else:
            print(f"note: site dir {site_copy.parent} absent; skipped site copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
