"""Translate the full measured corpus for the at-scale recovery test (owner, 2026-07-14).

Collects every unique patient sentence from the observational pairs_* batches
(confirmatory-holdout phrases excluded, same phrase-keyed rule as every other
publish path), rewrites each into standard clinical terminology with the SAME
system prompt the mitigation panel uses (llm_client._TRANSLATE_SYSTEM), and
writes a standard pairs file whose bottom_prompt is the translated sentence:

  data/simulated/txcorpus_<stamp>.json  (+ .report.json cost sidecar)

The stem deliberately does not match the observational regex (pairs_*), so the
corpus can never enter the confirmatory population; scripts/urgency_shift.py
also skips txcorpus_ trace dirs explicitly. Recovery is then measured for free
by the CPU logits backend (fire logits-eval on the txcorpus file): its
"language_penalty" is p(target|translated) - p(target|clinical), and
scripts/translation_scale.py joins back to the original patient rows for
per-model recovery at scale. Paid: ~$0.002/phrase on haiku; ceiling enforced.

Usage (CI, ANTHROPIC_API_KEY required):
  python scripts/translate_corpus.py --out data/simulated/txcorpus_<stamp>.json \
      --max-spend 1.50 [--model claude-haiku-4-5] [--limit 0]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(ENGINE / "scripts"))

from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp  # noqa: E402
from medlang_circuits import evaluate_models as em  # noqa: E402
from medlang_circuits.llm_client import _get_client, _translate_system  # noqa: E402

import re  # noqa: E402

_OBS_RE = re.compile(r"pairs_\d{8}T\d{6}Z")
DEFAULT_MODEL = "claude-haiku-4-5"


def collect_corpus(simulated_dir: Path, dashboard_path: Path) -> list[dict]:
    """Unique patient sentences from observational batches, holdout withheld,
    first occurrence wins (keeps the earliest batch's provenance)."""
    start = tierb_start_stamp(str(dashboard_path))
    seen: set[str] = set()
    corpus: list[dict] = []
    for batch_path in sorted(simulated_dir.glob("pairs_*.json")):
        if batch_path.name.endswith(".report.json"):
            continue
        stem = batch_path.stem
        if not _OBS_RE.fullmatch(stem):
            continue
        pairs = json.loads(batch_path.read_text(encoding="utf-8"))
        for i, pair in enumerate(pairs, start=1):
            patient = pair.get("bottom_prompt")
            clinical = pair.get("top_prompt")
            if not patient or not clinical:
                continue
            if is_tierb_batch(stem, start) and is_holdout(clinical):
                continue  # sealed: never sent anywhere, translated or not
            if patient in seen:
                continue
            seen.add(patient)
            corpus.append({
                "top_prompt": clinical,
                "patient_prompt": patient,
                "target_clinical_token": pair.get("target_clinical_token"),
                "source_batch": stem,
                "source_index": i,
            })
    return corpus


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-spend", type=float, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=0, help="first N phrases (0 = all)")
    parser.add_argument("--simulated-dir", default=str(ENGINE / "data/simulated"))
    parser.add_argument("--dashboard", default=str(ENGINE / "ops/dashboard.json"))
    args = parser.parse_args(argv)

    corpus = collect_corpus(Path(args.simulated_dir), Path(args.dashboard))
    if args.limit:
        corpus = corpus[:args.limit]
    print(f"corpus: {len(corpus)} unique patient sentences "
          f"(observational batches, holdout withheld)", file=sys.stderr)

    client = _get_client()
    tracker = em.CostTracker(max_spend=args.max_spend)
    system = _translate_system()
    out_pairs: list[dict] = []
    failed = 0
    for item in corpus:
        if not tracker.can_afford(args.model):
            print(f"ceiling reached after {len(out_pairs)} translations", file=sys.stderr)
            break
        try:
            text, tin, tout = em._call(client, args.model, system,
                                       item["patient_prompt"], max_tokens=256)
        except Exception as err:  # one bad call must not sink the corpus
            failed += 1
            print(f"  translation failed ({item['source_batch']}#{item['source_index']}): "
                  f"{err}", file=sys.stderr)
            if failed > 25:
                raise RuntimeError("too many translation failures; aborting") from err
            continue
        tracker.record(args.model, tin, tout)
        translated = text.strip()
        if not translated:
            failed += 1
            continue
        out_pairs.append({
            "top_prompt": item["top_prompt"],
            "bottom_prompt": translated,
            "target_clinical_token": item["target_clinical_token"],
            "generation": {
                "task": "txcorpus",
                "source_batch": item["source_batch"],
                "source_index": item["source_index"],
                "original_patient": item["patient_prompt"],
                "translation_model": args.model,
            },
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_pairs, indent=1) + "\n", encoding="utf-8")
    report = {
        "task": "txcorpus",
        "model": args.model,
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus_size": len(corpus),
        "translated": len(out_pairs),
        "failed": failed,
        "truncated_by_ceiling": tracker.truncated,
        "cost_usd": round(tracker.spent, 6),
        "max_spend_usd": args.max_spend,
        "usage": {"total_cost_usd": round(tracker.spent, 6), "per_model": tracker.per_model},
        "_": ("Full-corpus haiku translation for the at-scale recovery test; same "
              "system prompt as the mitigation panel. bottom_prompt is the translated "
              "sentence; measure with logits-eval, analyze with translation_scale.py."),
    }
    out_path.with_suffix("").with_suffix(".report.json").write_text(
        json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
