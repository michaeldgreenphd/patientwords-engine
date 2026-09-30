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

Exporters that publish per-pair rows ask ``sealed_pair`` whether one row is
sealed. It applies ``stamp_rows``' rule to a single row, reads the dashboard
and batch files from this repository (not the working directory), and raises
``SealError`` when the rule cannot be evaluated, so an exporter refuses
instead of publishing rows the seal never checked.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
from pathlib import Path

_BATCH_RE = re.compile(r"pairs_(\d{8}T\d{6}Z)")

# sealed_pair's inputs, resolved from this file so the seal gives the same
# answer whatever directory an exporter is run from. Until 2026-09-30 the
# exporters used the cwd-relative dashboard default of tierb_start_stamp below;
# run from outside the repo root they found no dashboard, sealed nothing and
# said nothing. The older functions keep their defaults for their own callers.
REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = REPO_ROOT / "ops" / "dashboard.json"
SIMULATED_DIR = REPO_ROOT / "data" / "simulated"


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


class SealError(RuntimeError):
    """The holdout seal cannot be evaluated for a row; the caller must write nothing.

    Deliberately not a ValueError: export_jlens_depth treats ValueError as a data
    refusal (exit 3, which the publish chain reads as success with no change),
    while an unevaluable seal is a configuration error. Messages name batches,
    indices and paths only, never prompt text.
    """


def _read_pairs(path: Path) -> list:
    """A batch file's list of pairs; SealError when it is missing, unreadable or not a list."""
    try:
        pairs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SealError(f"cannot read batch file {path} ({type(exc).__name__})") from exc
    if not isinstance(pairs, list):
        raise SealError(f"batch file {path} is not a list of pairs")
    return pairs


def _accepted_at(pairs: list | tuple, batch: str, index: object) -> str:
    """The accepted clinical prompt (``top_prompt``) of pair ``index`` (1-based); SealError when
    the index is not an integer inside the batch or the pair carries no prompt."""
    if isinstance(index, bool) or not isinstance(index, int) or not 0 < index <= len(pairs):
        raise SealError(f"{batch}#{index}: index is not a pair of the batch file ({len(pairs)} pairs)")
    entry = pairs[index - 1]
    top = entry.get("top_prompt") if isinstance(entry, dict) else None
    if not isinstance(top, str) or not top:
        raise SealError(f"{batch}#{index}: the batch file's pair carries no top_prompt")
    return top


@functools.lru_cache(maxsize=None)
def _seal_context(dashboard_path: str, simulated_dir: str) -> tuple[str, frozenset[str], dict[str, list]]:
    """(Tier B start stamp, registered holdout phrases, {Tier B stem: pairs}), read once per path pair.

    Refuses (SealError) when the dashboard has no Tier B start, when any Tier B batch
    file cannot be read (holdout_phrases would skip it and the phrase set would be
    incomplete), or when the phrase set comes back empty. Errors are not cached.
    """
    start = tierb_start_stamp(dashboard_path)
    if not start:
        raise SealError(f"no tierb.start_utc in {dashboard_path} (missing or unreadable file, or wrong branch); "
                        "the holdout rule cannot be applied")
    tierb_batches: dict[str, list] = {}
    for bp in sorted(Path(simulated_dir).glob("pairs_*.json")):
        if bp.name.endswith(".report.json") or not is_tierb_batch(bp.stem, start):
            continue
        tierb_batches[bp.stem] = _read_pairs(bp)
    phrases = holdout_phrases(simulated_dir, dashboard_path)
    if not phrases:
        raise SealError(f"holdout_phrases returned empty from {simulated_dir}; the holdout rule cannot be applied")
    return start, frozenset(phrases), tierb_batches


@functools.lru_cache(maxsize=None)
def _other_batch(path: str) -> tuple:
    """A non-Tier-B batch file's pairs, read once (only for rows that carry no prompt)."""
    return tuple(_read_pairs(Path(path)))


def sealed_pair(batch: str | None, index: int | None, clinical_prompt: str | None, *,
                dashboard_path: str | Path | None = None,
                simulated_dir: str | Path | None = None) -> bool:
    """True when the row (batch, 1-based index) with this trace-time clinical prompt is sealed.

    The rule is ``stamp_rows``' rule for one row. A row is sealed when
      1. its clinical prompt is a registered holdout phrase (``holdout_phrases``;
         Amendment 3: sealed anywhere, including alias and re-run stems), or
      2. it belongs to a Tier B batch whose ACCEPTED prompt for that index
         (``top_prompt`` in the batch file) hashes holdout (Amendment 1), or
      3. it belongs to a Tier B batch and its trace-time prompt hashes holdout
         (the conservative union of divergence-log row 2026-07-17).

    ``clinical_prompt`` is the prompt the row was traced with. A row that carries
    none (the steering and position-scan summaries) passes None or "", and the
    accepted prompt from ``data/simulated/<batch>.json`` stands in for it; the
    lens summaries' trace-time prompts equal the accepted ones.

    The dashboard and batch files default to this repository's copies, whatever
    the working directory. It fails closed, raising SealError where stamp_rows
    would treat the row as unsealed: no Tier B start stamp, an empty phrase set,
    an unreadable Tier B batch file, a Tier B row whose batch has no file or
    whose index is outside it, a prompt that is not a string, or a prompt-less
    row whose batch file cannot supply one.
    """
    dash = Path(dashboard_path) if dashboard_path is not None else DASHBOARD_PATH
    sim = Path(simulated_dir) if simulated_dir is not None else SIMULATED_DIR
    start, phrases, tierb_batches = _seal_context(str(dash), str(sim))
    if clinical_prompt is not None and not isinstance(clinical_prompt, str):
        raise SealError(f"{batch}#{index}: clinical prompt is a {type(clinical_prompt).__name__}, not a string")
    tierb = is_tierb_batch(batch, start)
    accepted = None
    if tierb:
        pairs = tierb_batches.get(batch)
        if pairs is None:
            raise SealError(f"Tier B batch {batch} has no batch file in {sim}")
        accepted = _accepted_at(pairs, batch, index)
    clin = clinical_prompt or None
    if clin is None:
        if tierb:
            clin = accepted
        elif not batch:
            raise SealError(f"a row with no batch name and no clinical prompt (index {index}) cannot be checked")
        else:
            clin = _accepted_at(_other_batch(str(sim / f"{batch}.json")), batch, index)
    return (clin in phrases) or is_holdout(accepted) or (tierb and is_holdout(clin))
