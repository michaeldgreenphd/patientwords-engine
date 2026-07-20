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


def holdout_phrases(simulated_dir="data/simulated", dashboard_path="ops/dashboard.json"):
    """The set of ACCEPTED clinical prompts assigned to the Tier B holdout.

    Amendment 3 (in force 2026-07-14): a phrase flagged holdout anywhere is
    sealed everywhere. The seal is keyed on the accepted prompt (``top_prompt``
    in the batch file), so trace-time screening probe extensions, alias /
    mitigation stems (``pairs_<STAMP>_txopus``), and re-run stems
    (``repeatability_r*``) all seal under the same registered phrase even though
    those stems do not fullmatch the Tier B batch pattern.
    """
    start = tierb_start_stamp(dashboard_path)
    phrases = set()
    if not start:
        return phrases
    for bp in sorted(Path(simulated_dir).glob("pairs_*.json")):
        if bp.name.endswith(".report.json") or not is_tierb_batch(bp.stem, start):
            continue
        try:
            pairs = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for pair in pairs:
            tp = pair.get("top_prompt")
            if is_holdout(tp):
                phrases.add(tp)
    return phrases


def accepted_prompt_map(simulated_dir="data/simulated", dashboard_path="ops/dashboard.json"):
    """{(stem, 1-based index): accepted top_prompt} for every Tier B batch pair.

    Lets a consumer recover the ACCEPTED prompt for a probe-extended trace row
    whose trace-time clinical prompt differs from the string the split hashed.
    """
    start = tierb_start_stamp(dashboard_path)
    out = {}
    if not start:
        return out
    for bp in sorted(Path(simulated_dir).glob("pairs_*.json")):
        if bp.name.endswith(".report.json") or not is_tierb_batch(bp.stem, start):
            continue
        try:
            pairs = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for i, pair in enumerate(pairs, start=1):
            out[(bp.stem, i)] = pair.get("top_prompt")
    return out


def stamp_rows(rows, dashboard_path="ops/dashboard.json", simulated_dir="data/simulated"):
    """Set row["tierb_split"] to "holdout"/"explore" in place, phrase-keyed.

    A row is sealed holdout if its clinical prompt is a registered holdout
    phrase (seal-anywhere), if its accepted prompt hashes holdout (covers
    trace-time probe extensions), or if it is a Tier B row whose trace-time
    prompt hashes holdout. Alias/re-run rows of a holdout phrase are flagged
    too, so downstream ``!= "holdout"`` filters cannot leak them. Genuinely
    non-Tier-B, non-holdout rows stay unflagged. Returns the holdout count.
    """
    start = tierb_start_stamp(dashboard_path)
    sealed = holdout_phrases(simulated_dir, dashboard_path)
    accept = accepted_prompt_map(simulated_dir, dashboard_path)
    n_holdout = 0
    for row in rows:
        clin = row.get("clinical_prompt")
        acc = accept.get((row.get("batch"), row.get("index")))
        tierb = is_tierb_batch(row.get("batch"), start)
        held = (clin in sealed) or is_holdout(acc) or (tierb and is_holdout(clin))
        if held:
            row["tierb_split"] = "holdout"
            n_holdout += 1
        elif tierb:
            row["tierb_split"] = "explore"
    return n_holdout
