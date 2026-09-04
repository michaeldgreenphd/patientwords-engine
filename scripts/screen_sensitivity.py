"""Screening-threshold sensitivity sweep on the logits backend.

The hosted-trace pipeline screens pairs at --screen-targets 0.02 (clinical-side
target probability below threshold -> pair not measured). The logits backend
records every pair unscreened, so it can answer the referee's question
(docs/referee_panel_20260714.md, worklist item 12): does the 0.02 choice move
the headline mean penalty? This sweep recomputes each model's phrase-deduped
mean penalty at several thresholds applied to the clinical-side probability.

Scope matches the confirmatory population in paired_stats_rigor.py:
observational pairs_* batches only, phrase-keyed holdout exclusion, one record
per (model, clinical phrase). Reads trace_out/ locally; writes
ops/screen_sensitivity.json. $0, offline.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

try:
    from scripts.tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
except ImportError:  # direct invocation from repo root
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp

ENGINE = Path(__file__).resolve().parents[1]
_OBS_RE = re.compile(r"pairs_\d{8}T\d{6}Z")
THRESHOLDS = (0.0, 0.01, 0.02, 0.05)


def collect_rows(trace_root: Path) -> list[dict]:
    """One row per (model, batch, clinical_prompt, part-index) from logits summaries."""
    start = tierb_start_stamp(str(ENGINE / "ops/dashboard.json"))
    rows = []
    for summary in sorted(trace_root.glob("*/batch_summary*.json")):
        stem = summary.parent.name
        model = stem.split("__", 1)[1] if "__" in stem else "gemma-2-2b"
        batch = stem.split("__", 1)[0]
        if not _OBS_RE.fullmatch(batch):
            continue
        data = json.loads(summary.read_text(encoding="utf-8"))
        if data.get("backend") != "logits":
            continue  # hosted traces are already screened; the sweep needs raw rows
        for r in data.get("results", []):
            probs = r.get("probabilities") or {}
            clin, pat = probs.get("clinical"), probs.get("patient")
            if clin is None or pat is None:
                continue
            prompt = (r.get("prompts") or {}).get("clinical")
            if not prompt:
                continue
            if is_tierb_batch(batch, start) and is_holdout(prompt):
                continue
            rows.append({"model": model, "batch": batch, "prompt": prompt,
                         "clinical_p": clin, "penalty": pat - clin})
    return rows


def sweep(rows: list[dict]) -> dict:
    by_model: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_model[r["model"]][r["prompt"]].append(r)
    out = {}
    for model, phrases in sorted(by_model.items()):
        grid = {}
        for t in THRESHOLDS:
            pens = []
            for _, rs in phrases.items():
                kept = [r for r in rs if r["clinical_p"] >= t]
                if kept:
                    pens.append(statistics.fmean(r["penalty"] for r in kept))
            grid[f"{t:g}"] = {
                "n_phrases": len(pens),
                "mean_penalty": round(statistics.fmean(pens), 4) if pens else None,
                "share_screened_out": round(1 - len(pens) / len(phrases), 4) if phrases else None,
            }
        out[model] = {"n_phrases_unscreened": len(phrases), "by_threshold": grid}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default=str(ENGINE / "trace_out"))
    parser.add_argument("--out", default=str(ENGINE / "ops/screen_sensitivity.json"))
    args = parser.parse_args()

    rows = collect_rows(Path(args.trace_root))
    result = {
        "_": ("Screening-threshold sensitivity on the logits backend (unscreened rows): "
              "phrase-deduped mean penalty per model at each clinical-side probability "
              "threshold. Observational pairs_* batches only; holdout phrases excluded. "
              "Referee worklist item 12, 2026-07-14."),
        "thresholds": [f"{t:g}" for t in THRESHOLDS],
        "production_threshold": "0.02",
        "per_model": sweep(rows),
    }
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for model, block in result["per_model"].items():
        cells = " ".join(f"t={t}: {v['mean_penalty']} (n={v['n_phrases']})"
                         for t, v in block["by_threshold"].items())
        print(f"{model}: {cells}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
