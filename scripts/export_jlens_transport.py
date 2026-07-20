"""Site dataset for the per-position transport view: data/jlens_transport.json.

Promotes the per-position lens scan (scripts/jlens_position_scan.py, until now
an ops-only artifact) to a site payload the transport figure reads:

- exemplars: a small PINNED set of contrast pairs (default 5), each carrying the
  FULL position x layer legibility grid under both phrasings (the target's rank
  within the top-N lens readout at every prompt position and layer, or null when
  absent - the clinical answer legible somewhere inside the sentence even where
  it never reaches the answer position) plus the model's own top prediction at
  the answer position and a paper-style open-vocabulary `readout` (the J-lens
  top-k decoded tokens per layer at the answer position - what the model leans
  toward as the answer forms, e.g. doctor -> doctor -> cardio). Only the fields
  the figure draws are kept per side (tokens, grid, answer_position, answer,
  readout); the per-side first_layer/layers duplicates and the per-exemplar
  transport summary are dropped to bound weight.
- census: over the representative batch (--census-batch), how the clinical
  target's legibility resolves at the final (answer) position vs. earlier
  positions - reaches_answer / transport_gap (legible mid-sentence but never at
  the answer) / never_readable, per phrasing. per_pair is the census cohort
  (grid-free), the provenance of those counts.

Stability & size. The exemplar set is PINNED (--exemplar-pins) so a nightly
regen does not churn the figure as backfill widens coverage; without pins it
falls back to deterministic score-ranking. per_pair is scoped to the census
batch (not every batch), so the file stays bounded as coverage grows. The
payload is written as COMPACT JSON - the grids are ~90% null and pretty-printing
them dominated the file; the frontend parses compact and indented identically.

Graceful partial coverage (mirrors export_jlens_depth F-H08). Reads only
committed trace_out/*__jlens_<model>/jlens_raw/*.json.gz (runs fired with
--save-raw). With no committed raw, a census batch with no committed coverage,
or no drawable exemplar, it REFUSES (returns None) and leaves the published
payload untouched - never overwrites a good file with a degraded one.

EXPLORATORY: the Jacobian lens is a correlational readout, not causal evidence;
nothing here is an intervention. Method credit is pulled from the summary's
method_credit field, never typed. No medical vocabulary lives in this file
(exemplars are pinned by (batch, index), never by term).

Frontend data contract (technical/index.html, transport figure) - see
FRONTEND_CONTRACT below; a validator can assert those paths after each regen.

Nightly invocation (the pinned set the published figure shows):
  python scripts/export_jlens_transport.py --model gemma-2-2b \
      --census-batch pairs_20260711T051145Z \
      --exemplar-pins pairs_20260712T163501Z:22,pairs_20260712T163501Z:7,pairs_20260712T163501Z:11,pairs_20260712T163501Z:83,pairs_20260712T163501Z:87 \
      --out data/jlens_transport.json --site ../patientwords
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

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

# Exactly what technical/index.html's transport figure reads from this payload.
# A validator can assert these paths exist and are well-typed after each regen;
# every other field is provenance/metadata the figure never touches.
FRONTEND_CONTRACT = {
    "census.patient": ("n", "reaches_answer", "transport_gap", "never_readable"),
    "exemplars[]": ("target", "layers", "sides.clinical", "sides.patient", "render?"),
    "exemplars[].sides.<side>": ("tokens[].token", "grid", "answer_position",
                                 "answer.token", "answer.prob", "answer.on_target",
                                 "answer.trace_url", "readout[].{layer,final,tokens}",
                                 "pos_readout{<pos>:[top-3]}"),
}

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


def lens_trace_url(model, prompt):
    """A Neuronpedia hosted-lens link for `prompt` on `model` (the live version
    of exactly what this figure reads out). The lens lives at
    neuronpedia.org/<model>/jlens; the prompt query pre-fills it where the page
    supports it and otherwise lands on the lens tool for the model."""
    return "https://www.neuronpedia.org/" + model + "/jlens?prompt=" + quote(prompt or "", safe="")


def _prompt_from_raw(response):
    """Reconstruct the prompt text from a raw response's token strings (drops
    the leading BOS marker)."""
    toks = (response.get("tokens") or []) if isinstance(response, dict) else []
    return "".join((t.get("token") or "") for t in toks
                   if (t.get("token") or "").strip() != "<bos>").strip()


def answer_prediction(response, target, model):
    """The model's ACTUAL top-1 token + probability at the answer position
    (final token, final layer, where the Jacobian lens equals the model output),
    whether that token is the intended target, and a live lens link. None when
    the raw lacks the final-layer top-token list."""
    tokens = (response.get("tokens") or []) if isinstance(response, dict) else []
    if not tokens:
        return None
    entry = next((r for r in (tokens[-1].get("results") or []) if isinstance(r, dict)), None)
    if not entry:
        return None
    top_tokens = entry.get("top_tokens") or []
    if not top_tokens or not top_tokens[-1]:
        return None
    token = jps.jr._token_string(top_tokens[-1][0])
    top_probs = entry.get("top_probs") or []
    prob = None
    if top_probs and top_probs[-1]:
        try:
            prob = round(float(top_probs[-1][0]), 4)
        except (TypeError, ValueError):
            prob = None
    return {
        "token": (token or "").strip() or None,
        "prob": prob,
        "on_target": bool(jps.jr.target_match(token, jps.jr.target_variants(target))),
        "trace_url": lens_trace_url(model, _prompt_from_raw(response)),
    }


# Depth ladder for the paper-style readout: the final layer plus a few samples
# from the coherent late band (as fractions of depth). The J-lens decodes to
# confident-but-meaningless artifacts in early/mid layers (e.g. "RenderAtEndOf"
# at high probability), so the readout stays in the top quarter where the decode
# is semantically meaningful - probability cannot separate the junk.
_READOUT_FRACS = (1.0, 0.94, 0.88, 0.82, 0.76)


def _readout_layer_idxs(n):
    """Indices into an n-long layer axis for the readout ladder, final first."""
    if n <= 0:
        return []
    last = n - 1
    return sorted({min(last, max(0, round(f * last))) for f in _READOUT_FRACS}, reverse=True)


def answer_readout(response, topk=3):
    """Open-vocabulary J-lens top-k decoded tokens at the answer (final) position
    for the depth ladder - the paper-style 'what is the model leaning toward'
    readout as the answer forms (e.g. doctor -> doctor -> cardio). Unlike the
    grid (which tracks one pre-chosen target), this names whatever the lens reads
    out. Each entry: {layer, final, tokens}. [] when the raw lacks final-position
    layer entries."""
    tokens = (response.get("tokens") or []) if isinstance(response, dict) else []
    if not tokens:
        return []
    final = tokens[-1]
    entries = sorted(
        (list(jps.jr._layer_entries_from_results(final, response))
         or list(jps.jr._iter_layer_entries(final))),
        key=lambda e: e[0],
    )
    if not entries:
        return []
    last_i = len(entries) - 1
    out = []
    for idx in _readout_layer_idxs(len(entries)):
        layer, tops = entries[idx]
        words = [w for w in (jps.jr._token_string(t).strip() for t in (tops or [])[:topk]) if w]
        if words:
            out.append({"layer": layer, "final": idx == last_i, "tokens": words})
    return out


def pos_readout(response, grid, topk=3):
    """Per-position open-vocab marginalia: the top-k decoded tokens at each prompt
    position where the TARGET is legible (grid.first_layer set), using the same
    final-layer open-vocab decode as answer_readout. Bounded on purpose - only
    legible positions, top-k each - so the file stays small. Keyed by the grid
    row index (aligns with side.tokens / side.grid). {} when nothing is legible."""
    tokens = (response.get("tokens") or []) if isinstance(response, dict) else []
    first_layer = grid.get("first_layer") or []
    out = {}
    for i, tok in enumerate(tokens):
        if i >= len(first_layer) or first_layer[i] is None:
            continue  # only positions where the target is legible (keeps it bounded)
        entries = sorted(
            (list(jps.jr._layer_entries_from_results(tok, response))
             or list(jps.jr._iter_layer_entries(tok))),
            key=lambda e: e[0],
        )
        if not entries:
            continue
        _layer, tops = entries[-1]  # final-layer readout at this position
        words = [w for w in (jps.jr._token_string(t).strip() for t in (tops or [])[:topk]) if w]
        if words:
            out[str(i)] = words
    return out


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


def load_render_map(scenarios_path):
    """{(batch, index): html} for pairs that carry a committed circuit-tracer
    render (scenario.html), so a chosen exemplar can deep-link to the real
    trace. Empty when the scenarios payload is missing or unreadable."""
    try:
        payload = json.loads(Path(scenarios_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for scenario in payload.get("scenarios", []):
        html = scenario.get("html")
        batch, index = scenario.get("batch"), scenario.get("batch_index")
        if html and batch is not None and index is not None:
            out[(batch, index)] = html
    return out


def _slim_side(grid, raw, target, model):
    """Just the exemplar-side fields the transport figure draws: the per-position
    tokens, the position x layer rank grid, the answer position, and the model's
    own top prediction there. The per-side first_layer/layers arrays are dropped
    - the figure indexes the exemplar's single shared `layers` axis, not these."""
    return {
        "tokens": grid.get("tokens", []),
        "grid": grid.get("grid", []),
        "answer_position": grid.get("answer_position"),
        "answer": answer_prediction(raw, target, model),
        "readout": answer_readout(raw),   # paper-style open-vocab decode per layer
        # per-position marginalia: top-3 decoded tokens at each legible position
        "pos_readout": pos_readout(raw, grid),
    }


def build_exemplar(trace_root, batch, index, model, topn, target):
    """Both-phrasing position x layer grids for the exemplar pair, slimmed to the
    fields the figure reads, or None when its raw is missing."""
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
        "sides": {
            "clinical": _slim_side(clin, clin_raw, target, model),
            "patient": _slim_side(pat, pat_raw, target, model),
        },
    }


def build_payload(trace_root, model, exemplar_batch=None, exemplar_index=None,
                  max_exemplars=5, render_map=None, census_batch=None,
                  exemplar_pins=None):
    """The data/jlens_transport.json payload, or None when the committed raw is
    too sparse to publish honestly (no raw at all, a census batch with no
    coverage, or no drawable exemplar) - the caller then leaves the published
    copy untouched rather than overwrite it with a degraded one.

    The census is computed over `census_batch` (a representative run) so it is
    not skewed by the traced pairs picked for the selector; per_pair carries just
    that cohort. Exemplars come from `exemplar_pins` (an ordered committed list,
    pins without raw skipped) when given, else from deterministic score-ranking
    over pairs that carry a committed circuit-tracer render (`render_map`);
    either way each answer token can deep-link to the real trace."""
    scan_result = jps.scan(Path(trace_root))
    all_pairs = collect_pairs(scan_result, model)
    if not all_pairs:
        return None
    render_map = render_map or {}

    # census over the representative batch (unbiased by the traced-pair picks);
    # refuse rather than silently widen the denominator to every batch, which
    # would bias the census when the pinned batch has no coverage.
    census_pairs = [e for e in all_pairs if e["batch"] == census_batch] if census_batch else all_pairs
    if not census_pairs:
        return None
    clin_records = [e["clinical"] for e in census_pairs if e["clinical"]]
    pat_records = [e["patient"] for e in census_pairs if e["patient"]]

    # exemplar selection, most stable first: explicit single index > pinned list
    # (skip pins lacking raw) > deterministic score-ranking over rendered pairs.
    if exemplar_index is not None:
        chosen = [(exemplar_batch or all_pairs[0]["batch"], exemplar_index)]
    elif exemplar_pins:
        chosen = list(exemplar_pins)
    else:
        candidates = [e for e in all_pairs if (e["batch"], e["index"]) in render_map] or all_pairs
        chosen = rank_exemplars(candidates, max_exemplars)
        if not chosen:
            fallback = pick_exemplar_index(candidates)
            chosen = [fallback] if fallback else []

    by_key = {(e["batch"], e["index"]): e for e in all_pairs}
    exemplars = []
    for batch, index in chosen:
        if len(exemplars) >= max_exemplars:
            break
        entry = by_key.get((batch, index))
        target = entry["target"] if entry else None
        _, topn = load_summary_meta(trace_root, batch, model)
        built = build_exemplar(trace_root, batch, index, model, topn, target)
        if built:
            built["render"] = render_map.get((batch, index))  # circuit-tracer trace path
            exemplars.append(built)
    if not exemplars:                       # the chosen pairs have no committed raw
        return None

    batches = sorted({e["batch"] for e in all_pairs})
    method_credit, topn = load_summary_meta(trace_root, batches[0], model)
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "scope": SCOPE,
        "method_credit": method_credit,
        "top_n": topn,
        "windows": scan_result.get("windows", ["1", "2", "4", "8"]),
        "census_batch": census_batch if (census_batch and census_pairs is not all_pairs) else None,
        "n_pairs": len(census_pairs),
        "census": {
            "clinical": summarize_side(clin_records),
            "patient": summarize_side(pat_records),
        },
        "exemplars": exemplars,
        "per_pair": census_pairs,   # census cohort (grid-free): provenance of `census`
        "source": f"trace_out/*__jlens_{model}/jlens_raw (committed save_raw responses)",
    }


def _dump(payload):
    """Compact JSON (the grids are ~90% null; pretty-printing them dominated the
    file). The frontend parses this identically to indent-formatted JSON."""
    return json.dumps(payload, separators=(",", ":")) + "\n"


def _parse_pins(spec):
    """'batch:index[,batch:index...]' -> [(batch, index), ...]; '' -> None."""
    if not spec:
        return None
    pins = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        batch, _, idx = tok.rpartition(":")
        pins.append((batch, int(idx)))
    return pins or None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--model", default="gemma-2-2b")
    parser.add_argument("--exemplar-batch", default=None,
                        help="batch stem for the exemplar pair (default: inferred)")
    parser.add_argument("--exemplar-index", type=int, default=None,
                        help="1-based pair index for a single explicit exemplar")
    parser.add_argument("--exemplar-pins", default=None,
                        help="ordered 'batch:index[,batch:index...]' exemplar pins; keeps the "
                             "selector stable across nightly regens (pins without raw are skipped)")
    parser.add_argument("--max-exemplars", type=int, default=5,
                        help="how many strong exemplars to emit for the selector (default 5)")
    parser.add_argument("--scenarios", default="../patientwords/data/simulated_scenarios.json",
                        help="site scenarios payload; its committed renders scope the exemplars "
                             "and give each answer token a circuit-tracer deep-link ('' disables)")
    parser.add_argument("--census-batch", default="pairs_20260711T051145Z",
                        help="representative batch the transport census is computed over")
    parser.add_argument("--out", default="data/jlens_transport.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    render_map = load_render_map(args.scenarios) if args.scenarios else {}
    payload = build_payload(args.trace_root, args.model,
                            args.exemplar_batch, args.exemplar_index,
                            max_exemplars=args.max_exemplars,
                            render_map=render_map, census_batch=args.census_batch,
                            exemplar_pins=_parse_pins(args.exemplar_pins))
    if payload is None:
        # Mirror jlens_insights F-H08: a sparse checkout with no committed raw
        # must never overwrite the published transport payload with an empty one.
        print(f"refused: no committed jlens_raw for {args.model} under {args.trace_root} "
              "- not overwriting outputs")
        return 3

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_dump(payload), encoding="utf-8")
    exs = payload.get("exemplars") or []
    linked = sum(1 for e in exs if e.get("render"))
    print(f"jlens transport: census {payload['n_pairs']} pairs (batch {payload.get('census_batch')}) · "
          f"patient never {payload['census']['patient']['never_readable']} · "
          f"{len(exs)} exemplars ({linked} circuit-linked) ["
          + ", ".join((e.get("target") or "?") for e in exs) + f"] -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "jlens_transport.json"
        if site_copy.parent.is_dir():
            site_copy.write_text(_dump(payload), encoding="utf-8")
            print(f"site copy -> {site_copy}")
        else:
            print(f"note: site dir {site_copy.parent} absent; skipped site copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
