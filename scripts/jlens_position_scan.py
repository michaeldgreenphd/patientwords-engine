"""Per-position lens transport scan + top-K window sensitivity, from saved raw.

Two referee-adjacent questions the landed lens summaries cannot answer, because
they keep only the final-position top-8 profile:

1. Window sensitivity (referee worklist item 7): "readable" means "in the top-8
   lens window". Do the depth conclusions survive at top-1/2/4? Recomputed here
   per pair from the raw per-layer top-8 lists.
2. Transport: under each phrasing, is the clinical target readable at any
   NON-final prompt position even when it never becomes readable at the final
   (answer) position? If yes, the failure is transport to the answer position,
   not failure to represent the concept mid-sentence.

Reads every trace_out/*__jlens_*/jlens_raw/pair_*.json.gz (raw responses are
committed only for runs fired with save_raw). Targets come from the batch file
in data/simulated/. Writes ops/jlens_position_scan.json. Offline, $0. The lens
is a correlational readout; nothing here is causal evidence.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]

_JR_SPEC = importlib.util.spec_from_file_location(
    "jlens_readout", ENGINE / "scripts" / "jlens_readout.py")
jr = importlib.util.module_from_spec(_JR_SPEC)
_JR_SPEC.loader.exec_module(jr)

WINDOWS = (1, 2, 4, 8)
_RAW_RE = re.compile(r"pair_(\d+)_(clinical|patient)\.json(\.gz)?$")


def _load_raw(path: Path) -> dict:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def position_profiles(response: dict, target: str) -> list[dict]:
    """Per prompt position: best (lowest) 1-based target rank across layers and
    the first layer where the target enters the top-8 window."""
    variants = jr.target_variants(target)
    out = []
    for tok in response.get("tokens", []):
        entries = (list(jr._layer_entries_from_results(tok, response))
                   or list(jr._iter_layer_entries(tok)))
        best_rank, first_layer = None, None
        for layer, tops in entries:
            for i, item in enumerate(tops[:8]):
                if jr.target_match(jr._token_string(item), variants):
                    if best_rank is None or i + 1 < best_rank:
                        best_rank = i + 1
                    if first_layer is None:
                        first_layer = layer
                    break
        out.append({"position": tok.get("position"), "token": tok.get("token"),
                    "best_rank": best_rank, "first_layer_top8": first_layer})
    return out


def window_profile(response: dict, target: str) -> dict:
    """Final-position first-readable layer per top-K window."""
    variants = jr.target_variants(target)
    tokens = response.get("tokens") or []
    if not tokens:
        return {str(k): None for k in WINDOWS}
    final = tokens[-1]
    entries = (list(jr._layer_entries_from_results(final, response))
               or list(jr._iter_layer_entries(final)))
    first = {k: None for k in WINDOWS}
    for layer, tops in entries:
        for i, item in enumerate(tops[:8]):
            if jr.target_match(jr._token_string(item), variants):
                rank = i + 1
                for k in WINDOWS:
                    if rank <= k and first[k] is None:
                        first[k] = layer
                break
    return {str(k): first[k] for k in WINDOWS}


def _batch_targets(stem: str) -> dict[int, dict]:
    batch_path = ENGINE / "data" / "simulated" / f"{stem}.json"
    if not batch_path.is_file():
        return {}
    pairs = json.loads(batch_path.read_text(encoding="utf-8"))
    return {i: p for i, p in enumerate(pairs, start=1)}


def scan(trace_root: Path) -> dict:
    scans = []
    for raw_dir in sorted(trace_root.glob("*__jlens_*/jlens_raw")):
        run_dir = raw_dir.parent.name
        stem, model = run_dir.split("__jlens_", 1)
        pairs = _batch_targets(stem)
        for raw_path in sorted(raw_dir.iterdir()):
            m = _RAW_RE.search(raw_path.name)
            if not m:
                continue
            index, side = int(m.group(1)), m.group(2)
            pair = pairs.get(index)
            if not pair:
                continue
            target = pair.get("target_clinical_token") or ""
            response = _load_raw(raw_path)
            positions = position_profiles(response, target)
            final = positions[-1] if positions else None
            non_final = [p for p in positions[:-1] if p["best_rank"] is not None]
            scans.append({
                "batch": stem, "model": model, "index": index, "side": side,
                "target_token": target,
                "windows_first_layer": window_profile(response, target),
                "final_readable": bool(final and final["best_rank"] is not None),
                "n_non_final_readable_positions": len(non_final),
                "non_final_positions": [
                    {"position": p["position"], "token": p["token"],
                     "first_layer_top8": p["first_layer_top8"]} for p in non_final],
                "transport_gap": bool(non_final) and not (final and final["best_rank"] is not None),
            })
    return {
        "_": ("Per-position lens transport scan + top-K window sensitivity from saved "
              "raw lens responses. transport_gap: target readable at a non-final prompt "
              "position but never at the final (answer) position. Correlational readout; "
              "coverage limited to runs fired with save_raw. Referee worklist item 7 "
              "(window) + lens program item 2 (transport), 2026-07-14."),
        "windows": [str(k) for k in WINDOWS],
        "n_responses": len(scans),
        "scans": scans,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default=str(ENGINE / "trace_out"))
    parser.add_argument("--out", default=str(ENGINE / "ops/jlens_position_scan.json"))
    args = parser.parse_args()
    result = scan(Path(args.trace_root))
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for s in result["scans"]:
        print(f"{s['batch']} pair {s['index']} {s['side']}: "
              f"final={'yes' if s['final_readable'] else 'NO'} "
              f"midsentence={s['n_non_final_readable_positions']} pos "
              f"windows={s['windows_first_layer']}"
              + ("  <- transport gap" if s["transport_gap"] else ""))
    print(f"-> {args.out} ({result['n_responses']} responses)")


if __name__ == "__main__":
    sys.exit(main())
