"""Count the published urgency rows that join no published scenario, by cause.

``scripts/urgency_shift.py --publish`` writes every trimmed row to the site's
``data/urgency_shift.json``: rows from re-traces, experiments, drift sentinels,
batches the exporter does not publish, and pairs the exporter leaves out, next to
the rows of published scenarios. The site's clinical page counts every row, so
the rows stay; this module records how many of them join nothing and why, as the
payload's top-level ``unjoinable_rows`` key:

  {"n": <total>,
   "by_cause": {"not_a_generation_batch": {"n": <count>, "stems": {<stem>: <count>}},
                "batch_not_in_payload":   {...},
                "pair_not_in_payload":    {...}}}

Counts and batch stems only (the stems are the rows' own ``batch`` values, which
the published rows already carry); no phrase text and no holdout keys.

Join rule, the one ``scripts/validate_frontend_contract.py`` applies: a row joins
when its (``batch``, ``index``) equals some scenario's (``batch``, ``batch_index``)
in the site's ``data/simulated_scenarios.json``. The model is not part of the key.
The contract check compares its own count of unjoinable rows with ``n`` and fails
on any difference.

Causes, decided in this order for a row that does not join:
  not_a_generation_batch  the stem is not ``pairs_<YYYYMMDDTHHMMSSZ>`` exactly
                          (re-trace, experiment, sentinel, translation-panel and
                          other run directories: ``pairs_<stamp>_<suffix>`` counts here)
  batch_not_in_payload    a generation batch the payload does not publish
                          (not in its ``batches`` list and no scenario carries it)
  pair_not_in_payload     the payload publishes the batch but not this pair

A payload that is missing, unreadable, not an object, without a non-empty
``scenarios`` list, or holding a scenario without a string ``batch`` and an
integer ``batch_index`` is refused (``PayloadRefusal``): counting against it would
be a guess. A row without a string ``batch`` and an integer ``index`` is refused
for the same reason.

No medical vocabulary lives in this file.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

GENERATION_BATCH_RE = re.compile(r"pairs_\d{8}T\d{6}Z")
CAUSES = ("not_a_generation_batch", "batch_not_in_payload", "pair_not_in_payload")


class PayloadRefusal(Exception):
    """The site payload, or a row, cannot support an exact unjoinable count."""


def _is_int(value: Any) -> bool:
    """An integer that is not a bool (True is an int in Python, never a JSON index)."""
    return isinstance(value, int) and not isinstance(value, bool)


def read_payload(path: Path) -> dict[str, Any]:
    """Load the site's simulated_scenarios.json for joining; refuse anything that is not a usable payload."""
    if not path.is_file():
        raise PayloadRefusal(f"site payload {path} is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise PayloadRefusal(f"site payload {path} is unreadable: {err}") from err
    if not isinstance(payload, dict):
        raise PayloadRefusal(f"site payload {path} is not a JSON object")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise PayloadRefusal(f"site payload {path} has no non-empty 'scenarios' list")
    malformed = sum(1 for s in scenarios
                    if not (isinstance(s, dict) and isinstance(s.get("batch"), str) and _is_int(s.get("batch_index"))))
    if malformed:
        raise PayloadRefusal(f"site payload {path}: {malformed} scenario(s) without a string 'batch' and an "
                             "integer 'batch_index'")
    return payload


def payload_join_keys(payload: Mapping[str, Any]) -> set[tuple[str, int]]:
    """The (batch, batch_index) of every scenario: the keys a row must match to join."""
    return {(s["batch"], s["batch_index"]) for s in payload["scenarios"]}


def payload_batch_stems(payload: Mapping[str, Any]) -> set[str]:
    """Every batch the payload publishes: those in its ``batches`` list and those its scenarios carry."""
    stems = {s["batch"] for s in payload["scenarios"]}
    for entry in payload.get("batches") or []:
        if isinstance(entry, dict) and isinstance(entry.get("batch"), str):
            stems.add(entry["batch"])
    return stems


def unjoinable_cause(batch: str, batch_stems: set[str]) -> str:
    """Why a row of ``batch`` that joins no scenario does not join (the caller has already tested the key)."""
    if not GENERATION_BATCH_RE.fullmatch(batch):
        return "not_a_generation_batch"
    if batch not in batch_stems:
        return "batch_not_in_payload"
    return "pair_not_in_payload"


def count_unjoinable(rows: Iterable[Mapping[str, Any]], payload: Mapping[str, Any]) -> dict[str, Any]:
    """The ``unjoinable_rows`` record for ``rows`` against ``payload`` (read with ``read_payload``).

    Counts only; the rows are neither changed nor filtered. Every cause is present, with n 0 and no stems when
    nothing falls under it, and stems are sorted so the record is byte-stable for the same inputs.
    """
    keys = payload_join_keys(payload)
    stems = payload_batch_stems(payload)
    by_cause: dict[str, Counter] = {cause: Counter() for cause in CAUSES}
    for i, row in enumerate(rows):
        batch, index = row.get("batch"), row.get("index")
        if not isinstance(batch, str) or not _is_int(index):
            raise PayloadRefusal(f"row {i} has no join key: needs a string 'batch' and an integer 'index'")
        if (batch, index) in keys:
            continue
        by_cause[unjoinable_cause(batch, stems)][batch] += 1
    causes = {cause: {"n": sum(counts.values()), "stems": dict(sorted(counts.items()))}
              for cause, counts in by_cause.items()}
    return {"n": sum(c["n"] for c in causes.values()), "by_cause": causes}
