"""Amendment 1 confirmatory-holdout split for Tier B (pre-registered 2026-07-09).

Every accepted Tier B pair is assigned to an analysis split by deterministic
hash of its clinical prompt: ``sha1(clinical_prompt) mod 10 == 0`` (~10%) is
the **holdout**, analyzed exactly once after collection ends. Interim analyses
during the collection week (nightly critic, dashboard deltas, synthesis
drafts, published aggregate counts) use ONLY the ~90% exploration split.

This module is the single implementation of that rule. The collector
(urgency_shift.py) stamps every row; aggregate consumers exclude
``tierb_split == "holdout"`` rows. Rows are never dropped from the data
files — the flag keeps the split auditable.

A batch counts as Tier B iff it is a ``pairs_<STAMP>`` batch whose stamp is
at or after ``tierb.start_utc`` in ops/dashboard.json (stamped by the
go/no-go session when batch 1 fired). Tier A batches and alias/dialect
batches carry no flag.
"""

import hashlib
import json
import re
from pathlib import Path

_BATCH_RE = re.compile(r"pairs_(\d{8}T\d{6}Z)")


def is_holdout(clinical_prompt):
    """Deterministic ~10% membership; empty/missing prompts stay explore."""
    if not clinical_prompt:
        return False
    digest = hashlib.sha1(clinical_prompt.encode("utf-8")).hexdigest()
    return int(digest, 16) % 10 == 0


def tierb_start_stamp(dashboard_path="ops/dashboard.json"):
    """tierb.start_utc as a compact batch-comparable stamp, or None pre-start."""
    try:
        dashboard = json.loads(Path(dashboard_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    start = (dashboard.get("tierb") or {}).get("start_utc")
    if not start:
        return None
    return re.sub(r"[-:]", "", start)  # 2026-07-10T01:14:38Z -> 20260710T011438Z


def is_tierb_batch(batch_name, start_stamp):
    if not start_stamp:
        return False
    m = _BATCH_RE.fullmatch(batch_name or "")
    return bool(m) and m.group(1) >= start_stamp


def stamp_rows(rows, dashboard_path="ops/dashboard.json"):
    """Set row["tierb_split"] to "holdout"/"explore" on Tier B rows in place.

    Non-Tier-B rows are left unflagged. Returns the number of holdout rows.
    """
    start = tierb_start_stamp(dashboard_path)
    n_holdout = 0
    for row in rows:
        if not is_tierb_batch(row.get("batch"), start):
            continue
        held = is_holdout(row.get("clinical_prompt"))
        row["tierb_split"] = "holdout" if held else "explore"
        n_holdout += held
    return n_holdout
