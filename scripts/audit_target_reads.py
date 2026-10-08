"""Audit the target-token probabilities recorded in committed batch summaries. Read only.

The hosted trace path read a target's probability with a prefix-tolerant,
case-blind match that kept the likeliest matching logit
(``medlang_circuits/targets.py``, ``target_probability`` with
``anchor_matches``), so a recorded value could be another token's: a likelier
token that begins with the target, or a likelier token that is the target's
first part. Separately, with no screen, a target missing from the reference
side was replaced by the top logit (``_resolve_reference``). Since 2026-10-07
new traces read exactly and record a ``target_read`` block; this script
measures how far the earlier reads reach in what is already committed. It
changes nothing.

Inputs: every ``batch_summary*.json`` under ``trace_out/`` and ``pilot/traces/``
(``--root`` is the engine checkout; ``--trace-root`` repeats to replace the two
defaults). Each result's sides are checked against the predictive spread stored
for that same side, token identity being ``targets.same_token`` (the hosted
wrapper removed, a leading SentencePiece or byte-level marker read as a space,
the leading space and case significant):

* ``consistent``: the exact target token is in the stored spread and the
  recorded probability equals its probability there; or the result's own
  ``target_read`` record (written since 2026-10-07) read that side exactly with
  the recorded probability (``identity: target_read``), which covers a target
  measured below the display cut or tied at it.
* ``prefix_mismatch``: the exact target token is in the stored spread with a
  different probability. Both values are reported, with the spread tokens that
  carry the recorded value and their prefix relation to the target.
* ``target_absent_from_spread``: a probability is recorded but the exact target
  token is not in the stored spread. ``value_source`` says what in the spread
  carries the recorded value: ``prefix_neighbour`` (a token the prefix-tolerant
  read accepts, the borrowed case), ``unrelated_token``, or ``not_in_spread``
  (no spread token has that value: the value came from outside the stored
  spread, as on the logits lane, which reads the target by token id at any rank
  and stores the top ten, or from a forced target kept outside the top five).
* ``unverifiable_no_spread``: a probability is recorded but no spread is stored
  for that side (activation-patching summaries).
* ``not_measured``: the recorded probability is null. Not checked.

A flagged side is ``borrowed`` when the backend read token text (hosted) and it
is a ``prefix_mismatch`` or its value is carried by a prefix neighbour. The
logits lane reads by token id, so its equal values are bfloat16 ties at the
spread's cut-off and are listed but never counted as borrowed. A borrowed side
is in a published field only on the clinical or patient side of a published
2panel row (the payload carries ``prob_clinical``, ``prob_patient`` and the
penalty; it carries no translated or dialect value).

Substitutions, per result: the measured token (``target_token``) against the
intended target, taken from ``screening.intended_target``, else
``target_read.intended_target``, else the pairs file the trace directory was
made from (``data/**/<stem>.json`` or ``pilot/runs/**/<stem>.json``) joined on
``results[i]["index"]`` and verified by the result's prompt text (a screening
probe extension accepted; for a dialect result the baseline and every variant
prompt, in order), a join that does not verify being counted as
``intended_unknown``, never guessed. An intended target written without its
leading space is compared with the space added, as the read does. Relations:
``exact``; ``leading_wordpiece`` (the measured token is a proper leading piece
of the intended target, leading space included, at least three characters:
the intended wordpiece rule); ``short_leading_wordpiece`` (a shorter leading
piece: on the logits lane the documented first-token rule, not a
substitution; on the hosted path neither read accepts a piece that short, so
there it can only be the top-logit fallback and is counted as a substitution);
and the substitutions ``space_variant`` and ``space_variant_wordpiece`` (the
same text, or a leading piece of it, without the intended leading space),
``case_variant``, ``case_variant_wordpiece``, ``extension`` (the measured
token begins with the intended target), ``unrelated`` (the top-logit or
forced-target fallback) and ``whitespace_token``. ``site_anchor_fallback``
repeats the site exporter's own rule for comparison with the published flag. A
hosted ``leading_wordpiece`` whose intended word is itself a token that model
returns in some stored spread is listed under
``wordpiece_reads_of_returned_tokens``: the word is not split in that
vocabulary, so the wordpiece rule measured another token for it (the hosted
path has no tokenizer to tell the two cases apart).

Two reading rules, because the readers disagree on duplicates. A trace
directory can hold one index in more than one part:

* ``counts`` (last part): the site exporter, ``export_archive.py`` and
  ``paired_stats.py``'s validity section read the last part in sorted
  filename order. ``effective`` marks that occurrence. ``backend_agreement.py``
  also takes the last part, but in numeric part order (``part_100`` after
  ``part_36``); ``numeric_last_part`` marks its occurrence, and
  ``part_order_disagreements`` lists every index where the two orders pick
  different parts (none in the committed data on 2026-10-07).
* ``counts_urgency_first_part``: ``urgency_shift.py`` reads
  ``trace_out/*/batch_summary.part_*.json`` in sorted order, skips
  ``txcorpus_`` directories and keeps the FIRST result per (model, batch,
  index) that has both a clinical and a patient spread. Its rows carry the
  penalty into ``paired_stats.py``, ``paired_stats_rigor.py`` and
  ``convergence_tracker.py``. ``urgency_read`` marks that occurrence.

Every occurrence is listed in ``findings`` and ``substitutions`` with both
marks.

A summary whose shape would read as zero rows (a root that is not an object,
no ``results``, ``results`` that is not a list, or a result that is not an
object), whose recorded probabilities are malformed (an unknown mode; a
missing or non-object ``probabilities``, or one without exactly its mode's
sides; a dialect result without ``baseline_probability`` or with malformed
``variants``; any value that is not a finite number or null), or that holds
a malformed predictive_spread entry (not a [string label, finite
probability] pair), is refused with every such file named: nothing is ever
read as an empty collection or dropped silently. A well-formed summary with an
empty ``results`` list is read, and listed under ``empty_summaries``.

Published rows (``--site-payload``, the site's ``data/simulated_scenarios.json``,
optional): an effective finding in a part the site exporter reads for that
model (``trace_out/<stem>`` for gemma-2-2b, ``trace_out/<stem>__<model>`` for
the others) whose (batch, index, model) is a payload scenario's model object is
marked ``published``, with the payload's own probability for that side.

A requested trace root that does not exist is refused, never skipped: an absent
root would read as an audit that found nothing. The report's ``engine_sha``
carries ``scripts/provenance_stamp.py``'s ``+dirty`` marker when the scanned
checkout has uncommitted or untracked changes.

The report goes to ``--out``; there is no default, and a path under a trace
root is refused, so nothing is ever written into ``trace_out/`` or
``pilot/traces/``. Prompt text is never written to the report.

Usage:
  python scripts/audit_target_reads.py --out /tmp/target_read_audit.json \\
      [--root .] [--site-payload ../patientwords/data/simulated_scenarios.json]

No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medlang_circuits.targets import (  # noqa: E402
    FOUND_STATUSES,
    MIN_PIECE_CHARS,
    prefix_relation,
    same_token,
    token_form,
    token_key,
    token_text,
)

SCHEMA = "patientwords-target-read-audit/2"
DEFAULT_TRACE_ROOTS = ("trace_out", "pilot/traces")
PAIRS_SEARCH = ("data", "pilot/runs")
BASE_MODEL = "gemma-2-2b"
SUBSTITUTION_RELATIONS = ("space_variant", "space_variant_wordpiece", "case_variant", "case_variant_wordpiece",
                          "extension", "unrelated", "whitespace_token")
FLAGGED_SIDE_STATUSES = ("prefix_mismatch", "target_absent_from_spread")
# Backends whose target read matched token text, where a value equal to a prefix neighbour's is the borrowed
# value. The logits lane reads the target by token id at any rank: its equal values are bfloat16 ties at the
# top-10 cut-off (2026-10-07: every such spread token sat at the bottom of its spread), not borrowing.
TEXT_READ_BACKENDS = ("hosted",)
# The payload's per-model probability key for each 2panel side; no other side is in a published field.
PAYLOAD_PROB_KEYS = {"clinical": "prob_clinical", "patient": "prob_patient"}
# urgency_shift.py skips these trace directories (their "patient" side is a rewrite).
URGENCY_SKIP_PREFIX = "txcorpus_"


class AuditRefusal(SystemExit):
    pass


def refuse(message: str) -> None:
    raise AuditRefusal(f"audit_target_reads: refusing, nothing written: {message}")


def is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---- sides --------------------------------------------------------------------------------------------------


def iter_sides(result: dict[str, Any]) -> Iterator[tuple[str, Any, Any]]:
    """(side, recorded probability, stored spread or None) for every side the result records a probability for,
    in each mode's own shape: 2panel/translation/4quadrant ``probabilities`` keyed like ``predictive_spread``;
    dialect ``baseline_probability`` and ``variants[j].probability`` against ``predictive_spread.baseline`` and
    ``predictive_spread.variants[j]``."""
    spreads = result.get("predictive_spread")
    spreads = spreads if isinstance(spreads, dict) else {}
    if result.get("mode") == "dialect" or "baseline_probability" in result:
        yield "baseline", result.get("baseline_probability"), spreads.get("baseline")
        variant_spreads = spreads.get("variants") if isinstance(spreads.get("variants"), list) else []
        for j, variant in enumerate(result.get("variants") or [], start=1):
            spread = variant_spreads[j - 1] if j - 1 < len(variant_spreads) else None
            yield f"variant_{j:02d}", (variant or {}).get("probability"), spread
        return
    probabilities = result.get("probabilities")
    for side, recorded in (probabilities.items() if isinstance(probabilities, dict) else []):
        yield side, recorded, spreads.get(side)


def spread_entries(spread: Any) -> list[tuple[str, float]] | None:
    if not isinstance(spread, list):
        return None
    out = []
    for entry in spread:
        if isinstance(entry, (list, tuple)) and len(entry) == 2 and isinstance(entry[0], str) and is_num(entry[1]):
            out.append((entry[0], float(entry[1])))
    return out


def target_read_side(result: dict[str, Any], side: str) -> dict[str, Any] | None:
    """The result's own read record for one side (``target_read``, written since 2026-10-07), or None."""
    sides = (result.get("target_read") or {}).get("sides") if isinstance(result.get("target_read"), dict) else None
    if not isinstance(sides, dict):
        return None
    if side.startswith("variant_") and isinstance(sides.get("variants"), list):
        j = int(side.split("_")[1]) - 1
        record = sides["variants"][j] if 0 <= j < len(sides["variants"]) else None
    else:
        record = sides.get(side)
    return record if isinstance(record, dict) else None


def check_side(target: str | None, recorded: Any, spread: Any, read: dict[str, Any] | None = None) -> dict[str, Any]:
    """One side's status (module docstring) with the evidence for it. ``read`` is the side's own
    ``target_read`` record when the result carries one."""
    if not is_num(recorded):
        return {"status": "not_measured"}
    if read is not None and read.get("status") in FOUND_STATUSES and read.get("probability") == recorded \
            and same_token(read.get("token"), target):
        return {"status": "consistent", "identity": "target_read"}
    entries = spread_entries(spread)
    if entries is None:
        return {"status": "unverifiable_no_spread", "recorded": recorded}
    # A whitespace target (the legacy fallback measured bare-space top tokens) has no text for same_token; its
    # recorded value is checked against the identical label.
    exact = [(label, p) for label, p in entries
             if (same_token(label, target) if token_key(target) else label == target)]
    carriers = [[label, p, prefix_relation(label, target) or "unrelated"] for label, p in entries
                if p == recorded and not any(label == e[0] for e in exact)]
    if exact:
        if any(p == recorded for _, p in exact):
            return {"status": "consistent"}
        return {"status": "prefix_mismatch", "recorded": recorded, "exact": [p for _, p in exact],
                "exact_token": exact[0][0], "recorded_carried_by": carriers}
    if any(c[2] != "unrelated" for c in carriers):
        source = "prefix_neighbour"
    elif carriers:
        source = "unrelated_token"
    else:
        source = "not_in_spread"
    return {"status": "target_absent_from_spread", "recorded": recorded, "value_source": source,
            "recorded_carried_by": carriers, "spread_len": len(entries)}


# ---- substitution -------------------------------------------------------------------------------------------


def intended_form(intended: str) -> str:
    """The intended target as the read compares it: written without a leading space, it gets the one a word
    after a word carries (``resolve_target``'s ``leading_space_added``)."""
    form = token_form(intended)
    return form if form[:1].isspace() else " " + form


def relation(measured: Any, intended: Any) -> str:
    """The measured token's relation to the intended target (module docstring), on ``token_form``."""
    if not isinstance(intended, str) or not token_key(intended):
        return "no_intended_target"
    if not isinstance(measured, str):
        return "no_measured_token"
    if not token_key(measured):
        return "whitespace_token"
    if same_token(measured, intended) or same_token(measured, intended_form(intended)):
        return "exact"
    m, i = token_form(measured), intended_form(intended)
    if len(m) < len(i) and i.startswith(m):
        return "leading_wordpiece" if len(token_key(measured)) >= MIN_PIECE_CHARS else "short_leading_wordpiece"
    mk, ik = token_key(measured), token_key(intended)
    if mk == ik:
        return "space_variant"
    if len(mk) >= MIN_PIECE_CHARS and len(mk) < len(ik) and ik.startswith(mk):
        return "space_variant_wordpiece"
    mf, inf = mk.casefold(), ik.casefold()
    if mf == inf:
        return "case_variant"
    if len(mk) >= MIN_PIECE_CHARS and len(mf) < len(inf) and inf.startswith(mf):
        return "case_variant_wordpiece"
    if mk.startswith(ik):
        return "extension"
    return "unrelated"


def is_substitution(rel: str, backend: Any) -> bool:
    """A substitution relation, or a piece shorter than either read accepts on a text-read backend (there it can
    only be the top-logit fallback)."""
    return rel in SUBSTITUTION_RELATIONS or (rel == "short_leading_wordpiece" and backend in TEXT_READ_BACKENDS)


def site_anchor_fallback(measured: Any, intended: Any) -> bool:
    """scripts/export_frontend_simulated.py's anchor_fallback rule, restated for comparison: a measured token
    (wrapper and surrounding whitespace removed) that the intended target, stripped, does not begin with,
    compared case-insensitively."""
    def bare(label: Any) -> str | None:
        text = token_text(label) if isinstance(label, str) else None
        return (text or "").strip() or None
    m = bare(measured)
    i = (intended or "").strip() if isinstance(intended, str) else ""
    return bool(m and i and not i.lower().startswith(m.lower()))


# ---- pairs files --------------------------------------------------------------------------------------------


def index_pairs_files(root: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = defaultdict(list)
    for base in PAIRS_SEARCH:
        for path in sorted((root / base).rglob("*.json")):
            if not path.name.endswith(".report.json"):
                found[path.stem].append(path)
    return found


def load_pairs(path: Path) -> list[Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def prompts_match(result: dict[str, Any], pair: dict[str, Any]) -> bool:
    """The result was traced from this pair: its prompts are the pair's, allowing the probe extension a
    screened result records."""
    prompts = result.get("prompts") if isinstance(result.get("prompts"), dict) else {}
    ext = (result.get("screening") or {}).get("probe_extension") if isinstance(result.get("screening"), dict) \
        else None

    def same(traced: Any, source: Any) -> bool:
        if not isinstance(traced, str) or not isinstance(source, str):
            return False
        return traced == source or bool(ext and traced == source.rstrip() + " " + ext)

    mode = result.get("mode")
    if mode == "dialect":
        # the baseline and every variant prompt, in order: a pairs file re-finalised with the same baseline but
        # other variants is another trace's source
        traced = [v.get("prompt") if isinstance(v, dict) else None for v in result.get("variants") or []]
        source = [v.get("prompt") if isinstance(v, dict) else None for v in pair.get("variants") or []]
        return (same(result.get("baseline_prompt"), pair.get("baseline_prompt") or pair.get("top_prompt"))
                and len(traced) == len(source) and all(same(t, w) for t, w in zip(traced, source)))
    if mode == "4quadrant":
        from medlang_circuits.batch_eval import _quadrant_prompts  # lazy: plotting stack
        try:
            want = _quadrant_prompts(pair)
        except (ValueError, KeyError, TypeError):
            return False
        return all(same(prompts.get(k), want.get(k)) for k in want)
    if mode == "translation":
        return same(prompts.get("patient"), pair.get("patient_prompt") or pair.get("bottom_prompt"))
    return same(prompts.get("clinical"), pair.get("top_prompt")) and same(prompts.get("patient"),
                                                                          pair.get("bottom_prompt"))


# ---- scan ---------------------------------------------------------------------------------------------------


def trace_dirs(root: Path, trace_roots: list[str]) -> list[tuple[str, Path]]:
    dirs = set()
    for tr in trace_roots:
        base = root / tr
        if not base.is_dir():  # main refuses a missing root before audit() runs; a programmatic caller too
            refuse(f"trace root {tr} is not a directory under {root}; an absent root would read as a clean audit")
        for part in base.rglob("batch_summary*.json"):
            dirs.add((tr, part.parent))
    return sorted(dirs, key=lambda d: (d[0], str(d[1])))


def numeric_part_key(part_rel: str) -> tuple[int, int, str]:
    """backend_agreement.py's part order: files without a part number first, then by part NUMBER."""
    m = re.search(r"part_(\d+)", Path(part_rel).name)
    return (1, int(m.group(1)), part_rel) if m else (0, 0, part_rel)


def site_reads(trace_root: str, dir_name: str, stem: str | None, model: str, part_rel: str) -> bool:
    """The site exporter reads this part for this model: trace_out/<stem> for the base model and
    trace_out/<stem>__<model> for every other (export_frontend_simulated.model_dir), part files only."""
    if trace_root != "trace_out" or not stem or not Path(part_rel).name.startswith("batch_summary.part_"):
        return False
    return dir_name == (stem if model == BASE_MODEL else f"{stem}__{model}")


def token_vocabulary(loaded: dict[Path, list[tuple[Path, dict]]]) -> dict[str, set[str]]:
    """Per model, the token forms seen anywhere in its stored spreads: evidence that a word is one token in that
    model's vocabulary."""
    vocab: dict[str, set[str]] = defaultdict(set)
    for d, parts in loaded.items():
        for _, summary in parts:
            model = summary.get("graph_model") or (d.name.split("__")[1] if "__" in d.name else BASE_MODEL)
            for r in summary.get("results", []) or []:
                spreads = r.get("predictive_spread") if isinstance(r, dict) else None
                stack = list(spreads.values()) if isinstance(spreads, dict) else []
                while stack:
                    item = stack.pop()
                    entries = spread_entries(item)
                    if entries:
                        vocab[model].update(token_form(label) for label, _ in entries)
                    elif isinstance(item, list):
                        stack.extend(x for x in item if isinstance(x, list))
    return vocab


def git_sha(root: Path) -> str | None:
    """The scanned checkout's commit with provenance_stamp's ``+dirty`` marker when its working tree has
    uncommitted or untracked changes, so counts from a modified tree are never attributed to a clean commit."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import engine_sha
    return engine_sha(root)


def read_payload(path: Path | None) -> tuple[dict[tuple[str, int, str], dict], dict[str, Any] | None]:
    if path is None:
        return {}, None
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    rows: dict[tuple[str, int, str], dict] = {}
    for s in payload.get("scenarios", []):
        for model, obj in (s.get("models") or {}).items():
            if isinstance(obj, dict):
                rows[(s.get("batch"), s.get("batch_index"), model)] = obj
    return rows, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                  "scenarios": len(payload.get("scenarios", []))}


def malformed_summaries(root: Path, loaded: dict[Path, list[tuple[Path, Any]]]) -> list[tuple[str, str]]:
    """Every summary whose shape would make it read as zero rows: a root that is not an object, no ``results``,
    ``results`` that is not a list, or a result that is not an object. An empty ``results`` list is well formed;
    the report lists it under ``empty_summaries``."""
    bad = []
    for parts in loaded.values():
        for part, summary in parts:
            rel = part.relative_to(root).as_posix()
            if not isinstance(summary, dict):
                bad.append((rel, "root is not an object"))
            elif "results" not in summary:
                bad.append((rel, "no results"))
            elif not isinstance(summary["results"], list):
                bad.append((rel, "results is not a list"))
            elif any(not isinstance(r, dict) for r in summary["results"]):
                bad.append((rel, "a result is not an object"))
            else:
                for r in summary["results"]:
                    why = probability_problem(r) or spread_problem(r)
                    if why:
                        bad.append((rel, f"index {r.get('index')}: {why}"))
                        break
    return bad


# The probability sides each mode must record (2panel may add the translated mitigation side).
REQUIRED_SIDES = {"2panel": {"clinical", "patient"}, "translation": {"patient", "translated"},
                  "4quadrant": {"A", "B", "C", "D"}}
OPTIONAL_SIDES = {"2panel": {"translated"}}


def num_or_null(value: Any) -> bool:
    return value is None or (is_num(value) and math.isfinite(value))


def probability_problem(result: dict[str, Any]) -> str | None:
    """Why a result's recorded probabilities are malformed, or None: an unknown mode; a dialect result without
    ``baseline_probability`` or with ``variants`` that are not a list of objects each holding ``probability``; any
    other mode without a ``probabilities`` object holding exactly its sides. Every value must be a finite number or
    null (a side recorded as not measured). An absent or malformed collection would otherwise read as no sides."""
    mode = result.get("mode")
    if mode == "dialect":
        if "baseline_probability" not in result or not num_or_null(result["baseline_probability"]):
            return "baseline_probability is absent or not a number or null"
        variants = result.get("variants")
        if not isinstance(variants, list) or any(not isinstance(v, dict) or "probability" not in v
                                                 or not num_or_null(v["probability"]) for v in variants):
            return "variants is not a list of objects each with a probability"
        return None
    if mode not in REQUIRED_SIDES:
        return f"unknown mode {mode!r}"
    probabilities = result.get("probabilities")
    if not isinstance(probabilities, dict):
        return "probabilities is absent or not an object"
    sides, required = set(probabilities), REQUIRED_SIDES[mode]
    if not required <= sides:
        return f"probabilities lacks {', '.join(sorted(required - sides))}"
    if sides - required - OPTIONAL_SIDES.get(mode, set()):
        return f"probabilities has unexpected sides {', '.join(sorted(sides - required - OPTIONAL_SIDES.get(mode, set())))}"
    if not all(num_or_null(v) for v in probabilities.values()):
        return "a probability is not a number or null"
    return None


def spread_problem(result: dict[str, Any]) -> str | None:
    """Why a result's stored predictive_spread is malformed, or None. A result may carry no spread (the
    activation-patching summaries do not): its sides are then unverifiable_no_spread, by name. A spread that is
    present must be an object of sides, each a list of [label, probability] entries (a dialect result's
    ``variants`` a list of such lists), every label a string and every probability a finite number."""
    spread = result.get("predictive_spread")
    if spread is None:
        return None
    if not isinstance(spread, dict):
        return "predictive_spread is not an object"
    for side, value in spread.items():
        lists = value if side == "variants" and result.get("mode") == "dialect" else [value]
        if not isinstance(lists, list):
            return f"predictive_spread.{side} is not a list"
        for entries in lists:
            if not isinstance(entries, list):
                return f"predictive_spread.{side} is not a list"
            for entry in entries:
                if not (isinstance(entry, (list, tuple)) and len(entry) == 2 and isinstance(entry[0], str)
                        and is_num(entry[1]) and math.isfinite(entry[1])):
                    return f"predictive_spread.{side} holds a malformed entry {json.dumps(entry)[:60]}"
    return None


def urgency_reads(root: Path, loaded: dict[Path, list[tuple[Path, dict]]]) -> set[tuple[str, int]]:
    """(part, position in its results list) of every result ``urgency_shift.py`` ingests - the occurrence itself,
    so an index repeated within one part is told apart: trace_out/*/batch_summary.part_*.json in sorted
    order, txcorpus_ directories skipped, the first result per (model, batch, index) with a non-empty clinical and
    patient spread."""
    seen: set[tuple[str, str, Any]] = set()
    chosen: set[tuple[str, Any]] = set()
    parts = sorted(((part, summary) for parts in loaded.values() for part, summary in parts
                    if part.parent.parent == root / "trace_out" and part.name.startswith("batch_summary.part_")),
                   key=lambda item: item[0].relative_to(root).as_posix())  # urgency_shift sorts glob strings
    for part, summary in parts:
        run_dir = part.parent.name
        stem, _, suffix = run_dir.partition("__")
        if stem.startswith(URGENCY_SKIP_PREFIX):
            continue
        model = summary.get("graph_model") or suffix or BASE_MODEL
        for position, r in enumerate(summary.get("results", []) or []):
            if not isinstance(r, dict) or (model, stem, r.get("index")) in seen:
                continue
            spread = r.get("predictive_spread") or {}
            if any(not [e for e in (spread.get(side) or []) if (token_text(e[0]) or "").strip()]
                   for side in ("clinical", "patient")):
                continue
            seen.add((model, stem, r.get("index")))
            chosen.add((part.relative_to(root).as_posix(), position))
    return chosen


class Tally:
    """Counts under one reading rule, overall and by group."""

    GROUPS = ("by_root", "by_dir", "by_batch", "by_model", "by_backend")

    def __init__(self) -> None:
        self.overall: Counter = Counter()
        self.groups: dict[str, dict[str, Counter]] = {g: defaultdict(Counter) for g in self.GROUPS}

    def bump(self, keys: list[tuple[str, str]], name: str, n: int = 1) -> None:
        self.overall[name] += n
        for group, key in keys:
            self.groups[group][key][name] += n

    def report(self) -> dict[str, Any]:
        return {"overall": dict(sorted(self.overall.items())),
                **{g: {k: dict(sorted(v.items())) for k, v in sorted(c.items())} for g, c in self.groups.items()}}


def audit(root: Path, trace_roots: list[str], payload_path: Path | None) -> dict[str, Any]:
    pairs_index = index_pairs_files(root)
    payload_rows, payload_meta = read_payload(payload_path)
    findings: list[dict[str, Any]] = []
    substitutions: list[dict[str, Any]] = []
    last, first = Tally(), Tally()
    joins: Counter = Counter()
    unjoined_dirs: dict[str, str] = {}
    payload_seen: set[tuple[str | None, Any, str]] = set()
    summaries = 0
    superseded = 0
    order_disagreements: list[dict[str, Any]] = []
    dirs = trace_dirs(root, trace_roots)
    loaded = {d: [(part, json.loads(part.read_text(encoding="utf-8")))
                  for part in sorted(d.glob("batch_summary*.json"))] for _, d in dirs}
    malformed = malformed_summaries(root, loaded)
    if malformed:
        refuse("malformed batch summaries, which would read as zero rows: "
               + "; ".join(f"{path} ({why})" for path, why in malformed))
    empty = sorted(part.relative_to(root).as_posix() for parts in loaded.values() for part, s in parts
                   if not s["results"])
    vocabulary = token_vocabulary(loaded)
    urgency = urgency_reads(root, loaded)
    wordpiece_tokens: list[dict[str, Any]] = []

    for trace_root, d in dirs:
        rel_dir = d.relative_to(root).as_posix()
        stem = d.name.split("__")[0] if d.name != Path(trace_root).name else None
        pairs: list[Any] | None = None
        candidates = pairs_index.get(stem or "", [])
        if len(candidates) == 1:
            pairs = load_pairs(candidates[0])
            if pairs is None:
                unjoined_dirs[rel_dir] = "pairs_file_not_a_list"
        else:
            unjoined_dirs[rel_dir] = "no_pairs_file" if not candidates else "several_pairs_files"
        # Each occurrence is (part, position in its results list), so an index repeated within one part is told
        # apart: the exporter, export_archive and backend_agreement keep the LAST occurrence (a later one
        # overwrites), urgency_shift the FIRST eligible one.
        occurrences: list[tuple[str, int, dict, dict]] = []
        for part, summary in loaded[d]:
            summaries += 1
            for position, r in enumerate(summary.get("results", []) or []):
                if isinstance(r, dict):
                    occurrences.append((part.relative_to(root).as_posix(), position, summary, r))
        last_for: dict[Any, tuple[str, int]] = {}
        for part_rel, position, _, r in occurrences:
            last_for[r.get("index")] = (part_rel, position)
        numeric_last_for: dict[Any, tuple[str, int]] = {}
        for part_rel, position, _, r in sorted(occurrences, key=lambda o: numeric_part_key(o[0])):
            numeric_last_for[r.get("index")] = (part_rel, position)
        for index, (part_rel, _) in last_for.items():
            if numeric_last_for[index][0] != part_rel:
                order_disagreements.append({"dir": rel_dir, "index": index, "last_part": part_rel,
                                            "numeric_last_part": numeric_last_for[index][0]})
        for part_rel, position, summary, r in occurrences:
            index = r.get("index")
            model = summary.get("graph_model") or (d.name.split("__")[1] if "__" in d.name else BASE_MODEL)
            backend = summary.get("backend")
            effective = last_for.get(index) == (part_rel, position)
            numeric_last = numeric_last_for.get(index) == (part_rel, position)
            urgency_read = (part_rel, position) in urgency
            superseded += not effective
            target = r.get("target_token")
            base = {"dir": rel_dir, "part": part_rel, "position": position, "index": index, "batch": stem,
                    "model": model,
                    "backend": backend, "mode": r.get("mode"), "effective": effective, "urgency_read": urgency_read,
                    "numeric_last_part": numeric_last}
            payload_obj = (payload_rows.get((stem, index, model))
                           if effective and site_reads(trace_root, d.name, stem, model, part_rel) else None)
            keys = [("by_root", trace_root), ("by_dir", rel_dir), ("by_batch", stem or rel_dir),
                    ("by_model", model), ("by_backend", str(backend))]

            def bump(name: str, n: int = 1) -> None:
                if effective:
                    last.bump(keys, name, n)
                if urgency_read:
                    first.bump(keys, name, n)

            bump("results")
            borrowed_sides: list[str] = []
            for side, recorded, spread in iter_sides(r):
                verdict = check_side(target, recorded, spread, target_read_side(r, side))
                status = verdict["status"]
                bump(f"sides.{status}")
                if status == "target_absent_from_spread":
                    bump(f"sides.target_absent_from_spread.{verdict['value_source']}")
                if status in FLAGGED_SIDE_STATUSES:
                    borrowed = backend in TEXT_READ_BACKENDS and (
                        status == "prefix_mismatch" or verdict.get("value_source") == "prefix_neighbour")
                    if borrowed:
                        borrowed_sides.append(side)
                    entry = {**base, "side": side, "target_token": target, **verdict, "borrowed": borrowed}
                    if payload_obj is not None:
                        entry["published"] = True
                        entry["published_field"] = PAYLOAD_PROB_KEYS.get(side) if r.get("mode") == "2panel" else None
                        if entry["published_field"]:
                            entry["payload_probability"] = payload_obj.get(entry["published_field"])
                    elif effective and payload_rows:
                        entry["published"] = False
                    findings.append(entry)
            if borrowed_sides:
                bump("results_with_borrowed_value")
                if payload_obj is not None:
                    bump("published_results_with_borrowed_value")
                    if r.get("mode") == "2panel" and any(side in PAYLOAD_PROB_KEYS for side in borrowed_sides):
                        bump("published_results_with_borrowed_value_in_a_published_field")

            intended, source = None, None
            screening = r.get("screening") if isinstance(r.get("screening"), dict) else {}
            target_read = r.get("target_read") if isinstance(r.get("target_read"), dict) else {}
            if screening.get("intended_target") is not None:
                intended, source = screening.get("intended_target"), "screening"
            elif "intended_target" in target_read:
                intended, source = target_read.get("intended_target"), "target_read"
            elif pairs is not None and isinstance(index, int) and 1 <= index <= len(pairs) \
                    and isinstance(pairs[index - 1], dict):
                if prompts_match(r, pairs[index - 1]):
                    intended, source = pairs[index - 1].get("target_clinical_token"), "pairs_file"
                    joins["verified"] += effective
                else:
                    source = "join_refused_prompt_mismatch"
                    joins["refused_prompt_mismatch"] += effective
            else:
                source = "no_join"
                joins["no_join"] += effective
            rel = relation(target, intended) if source not in ("join_refused_prompt_mismatch", "no_join") \
                else "intended_unknown"
            bump(f"target.{rel}")
            if rel == "leading_wordpiece" and backend in TEXT_READ_BACKENDS \
                    and intended_form(intended) in vocabulary.get(model, set()):
                # The intended word itself is a token this model returns elsewhere, so it is not split: the
                # wordpiece rule measured another token for it.
                bump("target.leading_wordpiece.intended_is_a_returned_token")
                if effective or urgency_read:
                    wordpiece_tokens.append({**base, "intended_target": intended, "measured_token": target,
                                             **({"published": payload_obj is not None} if payload_rows else {})})
            if is_substitution(rel, backend):
                bump("substitutions")
                entry = {**base, "intended_target": intended, "intended_source": source, "measured_token": target,
                         "relation": rel, "site_anchor_fallback": site_anchor_fallback(target, intended),
                         "recorded_substituted_flag": target_read.get("substituted"),
                         "screening_status": screening.get("status")}
                if payload_obj is not None:
                    entry["published"] = True
                    entry["payload_anchor_fallback"] = payload_obj.get("anchor_fallback")
                    bump("published_substitutions")
                    if not payload_obj.get("anchor_fallback"):
                        bump("published_substitutions_not_flagged")
                elif effective and payload_rows:
                    entry["published"] = False
                substitutions.append(entry)
            if payload_obj is not None:
                bump("published_results")
                payload_seen.add((stem, index, model))

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_sha": git_sha(root),
        "inputs": {"root": str(root), "trace_roots": trace_roots, "summaries": summaries,
                   "site_payload": payload_meta},
        "rules": {
            "sides": "recorded probability vs the exact target token's probability in the same side's stored "
                     "predictive_spread, or the side's own target_read record; statuses consistent, "
                     "prefix_mismatch, target_absent_from_spread (value_source prefix_neighbour, unrelated_token, "
                     "not_in_spread), unverifiable_no_spread, not_measured",
            "borrowed": "a hosted side is borrowed when it is a prefix_mismatch or its recorded value is carried by "
                        "a prefix neighbour in the spread; in a published field only on a published 2panel row's "
                        "clinical or patient side",
            "substitution": "measured token vs intended target on token_form; substitutions are "
                            + ", ".join(SUBSTITUTION_RELATIONS) + ", and short_leading_wordpiece on hosted",
            "counting": "counts: the last part per index in sorted file-name order (site exporter, export_archive, "
                        "paired_stats validity); backend_agreement takes the last part in numeric part order, marked "
                        "numeric_last_part, with part_order_disagreements listing every index where the two orders "
                        "differ; counts_urgency_first_part: urgency_shift.py's first result per "
                        "(model, batch, index) with both spreads (its rows feed paired_stats, paired_stats_rigor, "
                        "convergence_tracker); findings and substitutions list every occurrence with both marks",
        },
        "counts": last.report(),
        "counts_urgency_first_part": first.report(),
        "superseded_duplicate_results": superseded,
        # well-formed summaries that hold no result (none in the committed data on 2026-10-07), listed so an empty
        # summary is never read as a clean one
        "empty_summaries": empty,
        # backend_agreement.py orders parts numerically (part_100 after part_36); the exporter, export_archive and
        # paired_stats validity sort file names. Every index where the two orders pick different parts:
        "part_order_disagreements": order_disagreements,
        "joins": dict(sorted(joins.items())),
        # payload model objects with no committed summary result the site exporter would read: not auditable here
        "payload_rows_without_summary": sorted([list(k) for k in set(payload_rows) - payload_seen],
                                               key=lambda k: (str(k[0]), k[1] if isinstance(k[1], int) else -1,
                                                              str(k[2]))),
        "unjoined_dirs": dict(sorted(unjoined_dirs.items())),
        "findings": findings,
        "substitutions": substitutions,
        "wordpiece_reads_of_returned_tokens": wordpiece_tokens,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path, help="report path (required; never under a trace root)")
    ap.add_argument("--root", type=Path, default=ROOT, help="engine checkout to scan (default: this one)")
    ap.add_argument("--trace-root", action="append", default=None,
                    help=f"trace root relative to --root, repeatable (default: {', '.join(DEFAULT_TRACE_ROOTS)})")
    ap.add_argument("--site-payload", type=Path, default=None,
                    help="the site's data/simulated_scenarios.json, to mark published rows (optional)")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    trace_roots = args.trace_root or list(DEFAULT_TRACE_ROOTS)
    out = args.out.resolve()
    for tr in trace_roots:
        if out.is_relative_to((root / tr).resolve()):
            refuse(f"--out {out} is under the trace root {tr}; this audit writes nothing there")
    missing = [tr for tr in trace_roots if not (root / tr).is_dir()]
    if missing:
        refuse(f"trace root(s) {', '.join(missing)} not found under {root}; an absent root would read as a clean "
               "audit. Pass --trace-root for each root that exists")
    if args.site_payload is not None and not args.site_payload.is_file():
        refuse(f"--site-payload {args.site_payload} is not a file")
    report = audit(root, trace_roots, args.site_payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    o, f = report["counts"]["overall"], report["counts_urgency_first_part"]["overall"]
    print(f"audit_target_reads: {report['inputs']['summaries']} summaries; last part: {o.get('results', 0)} results, "
          f"{o.get('results_with_borrowed_value', 0)} with a borrowed value, {o.get('substitutions', 0)} "
          f"substitutions; urgency first part: {f.get('results', 0)} results, "
          f"{f.get('results_with_borrowed_value', 0)} borrowed, {f.get('substitutions', 0)} substitutions; "
          f"report at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
