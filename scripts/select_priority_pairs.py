#!/usr/bin/env python3
"""Select the pairs medgemma-1.5-4b-it measures first: a deterministic, documented priority set.

Owner decision 2026-10-09: the exploratory sweep covers gemma-4-e2b and qwen3.5-2b-base; medgemma-1.5-4b-it
(~120 s/pair, 80 runner-hours for everything) first measures "the most interesting stimuli from the current
sets", then the rest. "Interesting" is not defined by the owner; these criteria are a PROPOSAL for the owner
to confirm or change (each is a flag):

  (a) TASK SET - every main-study tracing pair of the newest physician task bundle
      (data/verification/tasks_*.json, items of family tracing_pair with provenance.subset main_study),
      read by identifier only (provenance.source_id, "<batch>#<index>"). These pairs are already under
      physician review, so a medgemma-1.5 measurement on them is directly comparable to that review.
  (b) CROSS-MODEL CONSENSUS - pairs whose published urgency rows (the site's data/urgency_shift.json, the
      collector's existing output: no new measurement) show a directional urgency-tier flip (flip_class
      downgrade or upgrade) in at least --k of the original models. One model's language penalty or flip
      label is not a stable measurement (AGENTS.md, known measurement limitations: the 2026-09-04 negative
      control flipped a top-1 prediction in 14 of 50 pairs with a neutral clause), so the signal used is
      agreement across models, never one model's |penalty|.

Excluded: any pair the Tier B holdout seals (tierb_split.sealed_pair on the batch file's accepted prompt,
which is the prompt logits_eval.py measures; it fails closed), and any pair outside the committed
data/simulated/pairs_*.json batches.

Order and cap: task-set pairs first, in the bundle's rank order; then consensus pairs by the number of
models flipping (most first), then batch, then index. The first --cap pairs are kept. Nothing is random:
the same inputs give the same file, and the output records "randomness": "none" together with the sha256
of every input. No prompt or phrase text is read into the output or printed - identifiers and counts only.

Usage:
  python scripts/select_priority_pairs.py --site ../patientwords [--k 5] [--cap 100] [--out FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from publication_hold import HELD_MODELS  # noqa: E402  (script-style module)
from tierb_split import SealError, sealed_pair  # noqa: E402  (script-style module)

SCHEMA = "priority_pairs/1"
DIRECTIONAL = ("downgrade", "upgrade")
_BATCH_RE = re.compile(r"pairs_\d{8}T\d{6}Z(?:_[a-z0-9]+)?")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def newest_task_bundle(engine: Path = ENGINE) -> Path:
    """The newest physician task bundle, by its stamped file name."""
    bundles = sorted((engine / "data" / "verification").glob("tasks_*.json"))
    if not bundles:
        raise SystemExit("refused: no data/verification/tasks_*.json task bundle to read")
    return bundles[-1]


def task_set_pairs(bundle: dict) -> list[tuple[str, int]]:
    """(batch, index) of every main-study tracing pair, in the bundle's rank order. Identifiers only."""
    items = [i for i in bundle.get("items", [])
             if i.get("family") == "tracing_pair" and (i.get("provenance") or {}).get("subset") == "main_study"]
    items.sort(key=lambda i: (i["provenance"].get("rank", 0), i["provenance"]["source_id"]))
    out = []
    for item in items:
        batch, _, index = item["provenance"]["source_id"].partition("#")
        if not index.isdigit():
            raise SystemExit(f"refused: task item {item.get('item_id')} has no '<batch>#<index>' source_id")
        out.append((batch, int(index)))
    return out


def consensus_counts(rows: list[dict], models: set[str]) -> dict[tuple[str, int], int]:
    """(batch, index) -> how many of `models` show a directional urgency-tier flip on that pair."""
    flips: dict[tuple[str, int], set[str]] = {}
    for r in rows:
        if r.get("model") in models and r.get("flip_class") in DIRECTIONAL:
            flips.setdefault((r["batch"], int(r["index"])), set()).add(r["model"])
    return {key: len(ms) for key, ms in flips.items()}


def select(task_pairs: list[tuple[str, int]], counts: dict[tuple[str, int], int], k: int, cap: int,
           batch_sizes: dict[str, int], sealed) -> tuple[list[dict], dict]:
    """The ranked, capped selection and the counts of what each rule took and dropped. `sealed(batch, index)`
    answers the holdout seal for one pair."""
    ranked: list[tuple[str, int, list[str]]] = []
    seen: dict[tuple[str, int], list[str]] = {}
    for key in task_pairs:
        seen.setdefault(key, []).append("task_set")
    for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if n >= k:
            seen.setdefault(key, []).append(f"tier_flip_in_{n}_models")
    order = [*task_pairs, *[key for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if n >= k]]
    stats = {"task_set_pairs": len(task_pairs), "consensus_pairs": sum(1 for n in counts.values() if n >= k),
             "excluded_not_a_batch_pair": 0, "excluded_sealed": 0, "duplicates_merged": 0}
    taken: set[tuple[str, int]] = set()
    for key in order:
        if key in taken:
            stats["duplicates_merged"] += 1
            continue
        batch, index = key
        if not _BATCH_RE.fullmatch(batch) or not 1 <= index <= batch_sizes.get(batch, 0):
            stats["excluded_not_a_batch_pair"] += 1
            taken.add(key)
            continue
        if sealed(batch, index):
            stats["excluded_sealed"] += 1
            taken.add(key)
            continue
        taken.add(key)
        ranked.append((batch, index, seen[key]))
    stats["eligible"] = len(ranked)
    kept = ranked[:cap]
    stats["kept"] = len(kept)
    stats["dropped_by_cap"] = len(ranked) - len(kept)
    stats["batches"] = len({b for b, _, _ in kept})
    pairs = [{"batch": b, "index": i, "reasons": reasons, "tier_flip_models": counts.get((b, i), 0)}
             for b, i, reasons in kept]
    return pairs, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", default="../patientwords", help="site checkout whose data/urgency_shift.json is read")
    ap.add_argument("--tasks", default=None, help="physician task bundle (default: the newest data/verification/"
                                                  "tasks_*.json)")
    ap.add_argument("--k", type=int, default=5, help="minimum number of original models with a directional "
                                                     "urgency-tier flip (criterion b)")
    ap.add_argument("--cap", type=int, default=100, help="maximum pairs kept (~120 s/pair each on medgemma-1.5)")
    ap.add_argument("--no-task-set", action="store_true", help="drop criterion (a)")
    ap.add_argument("--out", default=None, help="output file (default: data/selections/"
                                                "medgemma15_priority_<UTC date>.json)")
    args = ap.parse_args(argv)
    if args.k < 1 or args.cap < 1:
        ap.error("--k and --cap must be at least 1")

    tasks_path = Path(args.tasks) if args.tasks else newest_task_bundle()
    urgency_path = Path(args.site) / "data" / "urgency_shift.json"
    if not urgency_path.is_file():
        raise SystemExit(f"refused: {urgency_path} not found; pass --site <a site checkout>")
    bundle = json.loads(tasks_path.read_text(encoding="utf-8"))
    rows = json.loads(urgency_path.read_text(encoding="utf-8"))["rows"]
    batch_sizes = {p.stem: len(json.loads(p.read_text(encoding="utf-8")))
                   for p in sorted((ENGINE / "data" / "simulated").glob("pairs_*.json"))
                   if not p.name.endswith(".report.json")}
    originals = {r["model"] for r in rows} - HELD_MODELS
    task_pairs = [] if args.no_task_set else task_set_pairs(bundle)

    def sealed(batch: str, index: int) -> bool:
        try:
            return sealed_pair(batch, index, None)
        except SealError as exc:
            raise SystemExit(f"refused: the holdout seal cannot be evaluated for {batch}#{index}: {exc}")

    pairs, stats = select(task_pairs, consensus_counts(rows, originals), args.k, args.cap, batch_sizes, sealed)
    now = datetime.now(timezone.utc)
    doc = {
        "schema": SCHEMA,
        "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "for_model": "medgemma-1.5-4b-it",
        "status": "proposal: criteria await owner confirmation (docs/model_matrix.md)",
        "randomness": "none: a deterministic ranking, so there is no seed",
        "criteria": {
            "task_set": None if args.no_task_set else
            "main-study tracing pairs of the physician task bundle, in its rank order",
            "consensus": f"directional urgency-tier flip (downgrade or upgrade) in >= {args.k} of the original "
                         "models' published urgency rows",
            "k": args.k, "cap": args.cap, "models_counted": sorted(originals),
            "excluded": "pairs the Tier B holdout seals (tierb_split.sealed_pair, accepted prompt); pairs outside "
                        "the committed data/simulated/pairs_*.json batches",
            "order": "task-set pairs first (bundle rank), then consensus pairs by models flipping (most first), "
                     "batch, index",
        },
        "sources": [{"path": str(tasks_path.relative_to(ENGINE)) if tasks_path.is_relative_to(ENGINE)
                     else str(tasks_path), "sha256": _sha256(tasks_path)},
                    {"path": "patientwords:data/urgency_shift.json", "sha256": _sha256(urgency_path)}],
        "counts": stats,
        "pairs": pairs,
    }
    out = Path(args.out) if args.out else ENGINE / "data" / "selections" / f"medgemma15_priority_{now:%Y%m%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"selected {stats['kept']} pairs in {stats['batches']} batches -> {out}")
    print("counts: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
