"""EXPLORATORY: formation-depth analytics from the committed J-lens readouts.

Reads every jlens_summary.part_*.json under trace_out/*__jlens_<model>/ and
derives, per pair and side, where in depth the clinical answer forms and, on
the patient side, where the eventual wrong answer locks in. Emits the site's
technical-page payload: formation distributions, the capture-vs-hijack
taxonomy of failures, the instruction-tuning depth comparison, and a few
exemplar trajectories for the figures. Everything here is exploratory (no
pre-registered endpoint; Amendment 2 covers the confirmatory versions).
No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tierb_split import (  # noqa: E402  (script-style module)
    accepted_prompt_map, is_holdout, is_tierb_batch, tierb_start_stamp)

CREDIT = ("Jacobian lens: Gurnee et al., Transformer Circuits (2026); hosted by "
          "Neuronpedia. Readout = per-layer top-8 of the forming next-token "
          "distribution, rank recorded when the target appears.")


PERSISTENCE = 2  # consecutive readable layers required to count as formation


def formation_layer(layers, persistence=PERSISTENCE):
    """First layer where the target enters the readout AND stays for
    `persistence` consecutive layers. One-layer blips are readout noise, not
    formation (referee worklist item 7, adopted 2026-07-14). A final-layer
    appearance alone still counts as held via the final rank, not here."""
    ranks = [rec.get("target_rank") for rec in layers]
    run = 0
    for i, r in enumerate(ranks):
        run = run + 1 if r is not None else 0
        if run >= persistence:
            return layers[i - persistence + 1]["layer"]
    return None


def lock_in_layer(layers):
    """First layer from which top1 never changes again (the winner's lock-in)."""
    if not layers:
        return None
    final = layers[-1].get("top1")
    lock = layers[-1]["layer"]
    for rec in reversed(layers[:-1]):
        if rec.get("top1") == final:
            lock = rec["layer"]
        else:
            break
    return lock


def collect(trace_root: Path):
    """{model: [pair rows]}, holdout_excluded across every landed lens summary.

    Amendment 1/3: confirmatory-holdout pairs never enter interim analyses or
    public data files. Sealed on the ACCEPTED batch prompt (probe-extended
    trace prompts hash differently), and on the trace-time prompt as a backstop.
    """
    per_model = defaultdict(list)
    start = tierb_start_stamp()
    accept = accepted_prompt_map()
    holdout_excluded = 0
    for part in sorted(trace_root.glob("*__jlens_*/jlens_summary.part_*.json")):
        dataset = part.parent.name.split("__jlens_")[0]
        if (dataset.startswith("txcorpus_")
                or dataset.endswith(("_txopus", "_txplacebo", "__context"))):
            # translated/placebo/context-arm lens readouts are NOT patient
            # profiles: their "patient" side is a rewrite or a prefixed prompt.
            # translation_scale.py and the arm analyses own them; ingesting
            # here would pollute the formation census (txcorpus guard
            # 2026-07-15; arm stems added 2026-07-16 before the first census
            # regen with txopus/txplacebo lens dirs on disk).
            continue
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        model = summary.get("graph_model") or part.parent.name.split("__jlens_")[1]
        for r in summary.get("results", []):
            status = r.get("parse_status")
            if isinstance(status, dict):  # per-side statuses
                if any(v != "ok" for v in status.values()):
                    continue
            elif status not in (None, "ok"):
                continue
            depth = r.get("depth") or {}
            clin, pat = depth.get("clinical") or [], depth.get("patient") or []
            if not clin or not pat:
                continue
            if is_tierb_batch(dataset, start) and (
                    is_holdout(accept.get((dataset, r.get("index"))))
                    or is_holdout((r.get("prompts") or {}).get("clinical"))):
                holdout_excluded += 1
                continue
            row = {
                "dataset": dataset,
                "index": r.get("index"),
                "clin_formed": formation_layer(clin),
                "pat_formed": formation_layer(pat),
                "pat_final_rank": (pat[-1].get("target_rank") if pat else None),
                "pat_lock": lock_in_layer(pat),
                "n_layers": len(pat),
                "endpoint_class": r.get("patient_depth_class"),
                "pat_ranks": [rec.get("target_rank") for rec in pat],
                "clin_ranks": [rec.get("target_rank") for rec in clin],
            }
            per_model[model].append(row)
    return per_model, holdout_excluded


def classify(row):
    """Failure taxonomy on the patient side, conditioned on clinical
    readability (referee recount, adopted 2026-07-14).

    held: the target still ranks at the final layer.
    unreadable: the clinical side never forms either - the pair carries no
      clinical-side reference the patient wording could lose, so it is its
      own class, not evidence of capture.
    capture: clinical-readable; the target never entered the patient-side
      readout - the other reading owned the trajectory from the start.
    hijack: clinical-readable; the target formed at some depth and was
      pushed out by the end.
    """
    if row["pat_final_rank"] is not None:
        return "held"
    if row["clin_formed"] is None:
        return "unreadable"
    if row["pat_formed"] is None:
        return "capture"
    return "hijack"


def _formed_idx(ranks, window, persistence=PERSISTENCE):
    run = 0
    for i, r in enumerate(ranks):
        run = run + 1 if (r is not None and r <= window) else 0
        if run >= persistence:
            return i - persistence + 1
    return None


def window_sensitivity(rows, windows=(1, 2, 4, 8), persistence=PERSISTENCE):
    """Class counts re-derived at narrower top-K windows (referee item 7):
    'readable' should not be an artifact of the top-8 cutoff. The '8' column
    must equal the headline taxonomy by construction."""
    out = {}
    for k in windows:
        counts = {"held": 0, "unreadable": 0, "capture": 0, "hijack": 0,
                  "clinical_never": 0, "patient_never": 0}
        for r in rows:
            pat, clin = r["pat_ranks"], r["clin_ranks"]
            pat_final = pat[-1] if pat else None
            clin_f = _formed_idx(clin, k, persistence)
            pat_f = _formed_idx(pat, k, persistence)
            if clin_f is None:
                counts["clinical_never"] += 1
            if pat_f is None:
                counts["patient_never"] += 1
            if pat_final is not None and pat_final <= k:
                counts["held"] += 1
            elif clin_f is None:
                counts["unreadable"] += 1
            elif pat_f is None:
                counts["capture"] += 1
            else:
                counts["hijack"] += 1
        out[str(k)] = counts
    return out


def quantiles(values):
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return None
    def q(p):
        i = max(0, min(len(vs) - 1, round(p * (len(vs) - 1))))
        return vs[i]
    return {"n": len(vs), "q25": q(0.25), "median": q(0.5), "q75": q(0.75)}


def analyze(per_model, base_model, it_model, exemplar_count):
    rows = per_model.get(base_model, [])
    out = {
        "_": ("EXPLORATORY - formation-depth analytics from landed lens readouts; "
              "no pre-registered endpoint (Amendment 2 drafts the confirmatory "
              "versions). Ranks are within the lens's top-8 readout; 'never "
              "formed' means never entered that readout for at least "
              f"{PERSISTENCE} consecutive layers (one-layer blips do not count; "
              "referee item 7, adopted 2026-07-14). Capture/hijack are "
              "conditioned on clinical-readable pairs; pairs where neither "
              "wording ever reads out are the 'unreadable' class."),
        "persistence_layers": PERSISTENCE,
        "method_credit": CREDIT,
        "model": base_model,
        "n_pairs": len(rows),
        "formation": {
            "clinical": quantiles([r["clin_formed"] for r in rows]),
            "patient": quantiles([r["pat_formed"] for r in rows]),
            "clinical_never": sum(1 for r in rows if r["clin_formed"] is None),
            "patient_never": sum(1 for r in rows if r["pat_formed"] is None),
            "lag": quantiles([r["pat_formed"] - r["clin_formed"] for r in rows
                              if r["pat_formed"] is not None and r["clin_formed"] is not None]),
            "n_layers": rows[0]["n_layers"] if rows else None,
        },
        "taxonomy": {},
        "points": [
            {"dataset": r["dataset"], "index": r["index"],
             "clin_formed": r["clin_formed"], "pat_formed": r["pat_formed"],
             "class": classify(r)}
            for r in rows
        ],
    }
    tax = defaultdict(list)
    for r in rows:
        tax[classify(r)].append(r)
    for name, members in sorted(tax.items()):
        entry = {"n": len(members)}
        if name == "hijack":
            entry["formed_at"] = quantiles([m["pat_formed"] for m in members])
            entry["lock_in"] = quantiles([m["pat_lock"] for m in members])
        if name == "capture":
            entry["winner_lock_in"] = quantiles([m["pat_lock"] for m in members])
        out["taxonomy"][name] = entry
    out["window_sensitivity"] = window_sensitivity(rows)

    # exemplar trajectories for the concept figure: one held, one hijack, one capture
    exemplars = []
    for want in ("hijack", "capture", "held"):
        for r in rows:
            if classify(r) == want and r["clin_formed"] is not None:
                exemplars.append({"dataset": r["dataset"], "index": r["index"],
                                  "class": want, "clin_ranks": r["clin_ranks"],
                                  "pat_ranks": r["pat_ranks"]})
                break
        if len(exemplars) >= exemplar_count:
            break
    out["exemplars"] = exemplars

    # instruction-tuning comparison on datasets both models cover
    it_rows = per_model.get(it_model, [])
    if it_rows:
        base_by_key = {(r["dataset"], r["index"]): r for r in rows}
        paired = []
        for r in it_rows:
            b = base_by_key.get((r["dataset"], r["index"]))
            if b and r["pat_formed"] is not None and b["pat_formed"] is not None:
                paired.append({"index": r["index"], "base": b["pat_formed"],
                               "it": r["pat_formed"]})
        out["instruction_tuning"] = {
            "it_model": it_model,
            "n_paired": len(paired),
            "base_median": quantiles([p["base"] for p in paired]),
            "it_median": quantiles([p["it"] for p in paired]),
            "pairs": paired,
            "_": "patient-side formation layer, same phrases, base vs instruction-tuned",
        }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--base-model", default="gemma-2-2b")
    parser.add_argument("--it-model", default="gemma-2-2b-it")
    parser.add_argument("--exemplars", type=int, default=3)
    parser.add_argument("--out", default="ops/jlens_insights.json")
    parser.add_argument("--site", default=None,
                        help="site repo root; also writes data/jlens_insights.json there")
    args = parser.parse_args()

    per_model, holdout_excluded = collect(Path(args.trace_root))
    if not per_model.get(args.base_model):
        # F-H08 (audit 1, 2026-07-17): a sparse checkout must never overwrite
        # the committed census (ops + site copies) with an empty one.
        print(f"refused: no jlens summaries for {args.base_model} under "
              f"{args.trace_root} - not overwriting outputs")
        return 3
    payload = analyze(per_model, args.base_model, args.it_model, args.exemplars)
    payload["holdout_excluded"] = holdout_excluded  # Amendment 1/3 seal (sealed rows dropped)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"jlens insights: {payload['n_pairs']} pairs · taxonomy "
          + " ".join(f"{k}:{v['n']}" for k, v in payload["taxonomy"].items())
          + f" -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "jlens_insights.json"
        site_copy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"site copy -> {site_copy}")


if __name__ == "__main__":
    raise SystemExit(main())
