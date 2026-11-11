#!/usr/bin/env python3
"""Recompute the gallery payload's ``summary`` block from the payload's own rows, and nothing else.

Why this exists. Until 2026-11-10 ``scripts/payload_summary.py`` keyed its phrase dedupe on a field the
exporter's rows do not carry, so the published ``summary.penalty`` counted every scored row as its own phrase
(``docs/corrections/payload_summary_dedupe_20261110.md``). The exporter, ``scripts/export_frontend_simulated.py``,
has no option that rewrites the summary and keeps the published rows: a full export also re-reads every summary
part, so it carries whatever else has changed in ``trace_out/`` since the last publish. Those are different
kinds of change (changed inputs, a changed analysis population) and are decided separately. This tool applies
the producer's own corrected function, ``payload_summary.build_summary``, to the scenarios already in the
published file, so the bug correction can be published alone.

What it changes. Only ``summary.penalty.n_phrases``, ``summary.penalty.mean_phrase_deduped`` and
``summary.penalty.ci95``. It refuses (exit 2, nothing written) when the recomputed summary differs from the
published one anywhere else, because the payload is then not one whose rows produced its own summary, and when
the published block is neither the pre-correction form nor already correct. The file is written exactly as the
exporter writes it (``json.dumps(payload, indent=2)`` and a final newline), and the tool refuses a file that is
not in that form, so every byte outside the summary block is unchanged.

  python scripts/restamp_payload_summary.py --site ../patientwords --dry-run
  python scripts/restamp_payload_summary.py --site ../patientwords

Exit 0: written, or already correct (nothing written). Exit 2: refused. The next full export writes the same
summary from the same rows; this tool is not a step of the publish chain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from payload_summary import build_summary  # noqa: E402

PAYLOAD_REL = Path("data") / "simulated_scenarios.json"
# The only fields the 2026-11-10 correction changes. Every other field of the summary must be reproduced
# exactly from the payload's rows, or the tool refuses.
CORRECTED_FIELDS = ("n_phrases", "mean_phrase_deduped", "ci95")


class RestampError(RuntimeError):
    """The payload is not one this tool can correct; nothing is written."""


def recompute(payload: dict[str, Any]) -> dict[str, Any]:
    """The summary the corrected producer writes for this payload's own scenarios."""
    summary = payload.get("summary")
    scenarios = payload.get("scenarios")
    if not isinstance(summary, dict) or not isinstance(scenarios, list):
        raise RestampError("the payload has no 'summary' object or no 'scenarios' list")
    totals, penalty = summary.get("totals"), summary.get("penalty")
    if not isinstance(totals, dict) or not isinstance(penalty, dict):
        raise RestampError("the summary has no 'totals' or no 'penalty' object; an older payload is re-exported, "
                           "not restamped")
    accepted, withheld, model = totals.get("accepted"), totals.get("holdout_withheld"), summary.get("model")
    if type(accepted) is not int or type(withheld) is not int or not isinstance(model, str):
        raise RestampError("summary.totals.accepted, summary.totals.holdout_withheld or summary.model is missing")
    return build_summary(scenarios, accepted, withheld, base_model=model)


def restamp(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(new_summary, change)``. ``change`` is empty when the published summary is already correct.

    Raises ``RestampError`` when the two summaries differ outside the corrected fields, or when the published
    block is not the pre-correction form (one phrase per scored row)."""
    old = payload["summary"] if isinstance(payload.get("summary"), dict) else {}
    new = recompute(payload)
    if new == old:
        return new, {}
    outside = sorted(k for k in set(old) | set(new) if k != "penalty" and old.get(k) != new.get(k))
    old_pen, new_pen = old["penalty"], new["penalty"]
    outside += sorted(f"penalty.{k}" for k in set(old_pen) | set(new_pen)
                      if k not in CORRECTED_FIELDS and old_pen.get(k) != new_pen.get(k))
    if outside:
        raise RestampError("the summary recomputed from the payload's rows differs from the published one outside "
                           f"the corrected fields ({', '.join(outside)}); this payload needs a full export")
    if not (old_pen.get("n_phrases") == old_pen.get("n_scored_rows")
            and old_pen.get("mean_phrase_deduped") == old_pen.get("mean_rows_raw")):
        raise RestampError("the published summary.penalty is neither the pre-correction form (one phrase per "
                           "scored row) nor what the corrected producer writes; it is not restamped")
    change = {k: {"before": old_pen.get(k), "after": new_pen.get(k)} for k in CORRECTED_FIELDS
              if old_pen.get(k) != new_pen.get(k)}
    return new, change


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True, help="frontend checkout whose data/simulated_scenarios.json is read")
    parser.add_argument("--dry-run", action="store_true", help="report the change and write nothing")
    args = parser.parse_args(argv)
    path = Path(args.site) / PAYLOAD_REL
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RestampError("the payload is not a JSON object")
        if (json.dumps(payload, indent=2) + "\n").encode("utf-8") != raw:
            raise RestampError("the file is not in the exporter's own serialization (indent 2, final newline); "
                               "rewriting it would change bytes outside the summary")
        summary, change = restamp(payload)
    except (OSError, ValueError, RestampError) as exc:
        print(f"restamp payload summary: refused, nothing written: {exc}", file=sys.stderr)
        return 2
    before = hashlib.sha256(raw).hexdigest()
    if not change:
        print(f"restamp payload summary: {path} already holds the corrected summary (sha256 {before}); "
              "nothing written")
        return 0
    payload["summary"] = summary
    out = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    for field, pair in change.items():
        print(f"  summary.penalty.{field}: {pair['before']} -> {pair['after']}")
    pen = summary["penalty"]
    print(f"  unchanged: n_scored_rows {pen['n_scored_rows']}, mean_rows_raw {pen['mean_rows_raw']}, totals, "
          f"and all {len(payload['scenarios'])} scenarios")
    print(f"  sha256 {before} -> {hashlib.sha256(out).hexdigest()}")
    if args.dry_run:
        print("  DRY RUN: nothing was written")
        return 0
    path.write_bytes(out)
    print(f"restamp payload summary: wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
