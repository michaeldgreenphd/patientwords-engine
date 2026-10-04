"""Rank earlier advice stimuli by how many models downgraded them, and write a rerun selection.

Offline and $0: reads only the committed archives under ``data/advice/`` and writes
two new files from one run, refusing to overwrite either (``data/advice/`` is
append-only):

- the ranking report (``--report-out``): the selection rule, each selected item
  with its metrics (rank, downgrade counts, null probabilities, the noise-floor
  decision, the per-model cells), the null's expected and observed counts, the
  seed and permutations, the judge, the excluded models, the rubric, the sha256
  of every input file, the row accounting and the per-model summary;
- the selection (``--selection-out``): exactly the shape that
  ``advice_eval.py build-stimuli --source selection`` reads, which refuses any
  other key (``SELECTION_KEYS`` and ``SELECTION_ENTRY_KEYS`` there):

      {"rule": <the report's rule text>,
       "items": [{"file": "data/advice/stimuli_<stamp>.json", "id": "<stimulus id>"}, ...],
       "notes": <the report's path and sha256, the seed, the permutations, and that the selection is post hoc>}

  Items are in rank order. The report is written first and the sha256 in the
  notes is that of the report file as written, so a selection names exactly one
  report.

The unique key of an item is the pair (file, id), not the id alone: the same
stimulus id can be selected from two stimuli files (two forms of one
situation), and in the report such items carry
``same_situation_also_selected_from``. ``build-stimuli --source selection``
keeps the output ids unique by renaming the later item ``<id>~<file stem>``.

Methodology (every step is the repository's own definition, restated here so a
reader of the output can reconstruct it without reading the caller):

1. Inputs. Every ``judgments_<stem>.jsonl`` in the advice directory (or the stems
   named with ``--stem``, each at most once), with its ``responses_<stem>.jsonl``
   and the stimuli file ``<stem>.json``. Each responses archive must pass
   ``verify_chain``; a broken chain is a refusal, as in the exporter. An archive
   cut back to an earlier prefix still passes ``verify_chain``, so the archive
   must also hold exactly the ``records_total`` records and end at the
   ``chain_head`` that its sidecar ``responses_<stem>.report.json`` recorded when
   the records were written; a missing sidecar, a missing or malformed field, or
   a mismatch is a refusal. Every advice record must carry the
   ``stimuli_sha256`` of the loaded stimuli document (``advice_eval``'s
   canonical hash, ``sha256_text(canonical_json(doc))``), so responses elicited
   from another version of the stimuli file are refused. The sha256 of every
   file the ranking is computed from is recorded in the output; the sidecar is
   read only for the two values above, which a passing check makes equal to
   values the recorded archive sha256 already determines, so it is not listed.
2. Judge. Only the primary judge (``--judge-model``, default ``claude-haiku-4-5``).
   Provider-spec judges (``provider:model``) are secondary second opinions and
   are excluded, as ``analyze`` and the exporter exclude them; any other bare
   judge label is excluded too, so the ranking rests on one judge. Judgment rows
   with a null tier are judge failures (the judge retries them) and carry no
   tier. Every judgment row carries the ``rubric_sha256`` it was made under
   (the canonical hash of the rubric, as ``advice_eval.py judge`` writes it);
   primary-judge rows made under a rubric other than ``--rubric`` are a different
   instrument and are excluded and counted, and an archive none of whose
   primary-judge rows were made under ``--rubric`` is refused. When one response
   has several primary judgments, the last one in the file wins ("later passes
   overwrite earlier ones", as in the exporter).
3. One sample per (stimulus file, stimulus id, arm, model, sample k), chosen the
   exporter's way (``export_advice_scenarios.build_payload``): response records
   are grouped by (stimulus id, arm, display model), where ``DISPLAY_ALIASES``
   folds a rerouted access path into its model family; within a group they are
   sorted by (sample_k, rerouted-path-after-direct-path, sent_utc) and the first
   record per k is kept. The kept record's tier is the primary judgment of its
   ``response_sha256``. A kept record with no primary tier contributes nothing,
   as in the exporter.
4. Modal tier per (file, stimulus, model, arm) over its samples, ties broken
   toward the more urgent tier (``advice_eval._modal_tier``; tier order from the
   rubric file, least to most urgent).
5. A downgrade is a patient-arm modal tier below the clinical-arm modal tier for
   the same (file, stimulus, model); its drop is the number of tiers between
   them. Only cells with judged samples on both arms are paired. The translated
   arm is not part of this comparison.
6. Ranking. Models whose spec contains an ``--exclude-model`` substring (default
   ``gemini``: those responses were truncated at max_tokens 1024 because the
   model's reasoning tokens used most of the budget, and the site withholds
   every Gemini arm) do not count. Stimuli are ranked by the number of remaining
   models with a downgrade; ties by the summed tier drop over those downgrades;
   then by the share of patient samples coded below the clinical modal tier,
   pooled over the remaining models; then by file and id, so the order is total.
7. Null. For each paired cell, the clinical and patient tier labels are pooled
   and reassigned at random to arms of the original sizes, ``--permutations``
   times; q is the share of reassignments that produce a downgrade. Each cell's
   generator is ``random.Random("<seed>|<file>|<stimulus>|<model>")``, so a
   cell's draws do not depend on which other cells or files are in the run.
   Under the null that wording has no effect, a stimulus's downgrade count is a
   sum of independent Bernoulli(q) over its counted models (Poisson-binomial);
   ``p_tail`` is P(count >= observed), not corrected for the number of stimuli
   tested.
8. Noise floor. The ranking statistic is the downgrade count, so the
   multiplicity correction is made on the count: E(k), the expected number of
   ranked stimuli that reach at least k downgrades under the null, is the sum
   of every ranked stimulus's tail at k, and it bounds the chance that any
   stimulus reaches k (union bound). An item with count k clears the noise floor
   when E(k) < 0.05. The output also gives the Bonferroni-adjusted per-stimulus
   p (p_tail times the number of ranked stimuli, capped at 1), which is more
   conservative here because most stimuli cannot reach a high count at all
   (they have fewer models, or cells whose samples all agree, where q = 0).

Malformed rows are refused, never skipped: a judgment row missing a field,
with a field of the wrong type, with a tier the rubric does not define, or
pointing at a response the archive does not hold stops the run with the file
and line, as does an advice record whose ``stimuli_sha256`` is absent or names
another stimuli document. Excluded rows are counted by reason in the output.

This script ranks archived machine codings (provisional, rubric draft); it
dispenses no advice and makes no claim-grade statement. The selection is post
hoc, so a rerun of it is a replication test and should regress toward the mean.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent

DEFAULT_ADVICE_DIR = "data/advice"
DEFAULT_RUBRIC = "data/advice_rubric.draft.json"
DEFAULT_JUDGE = "claude-haiku-4-5"
DEFAULT_EXCLUDE = ("gemini",)
DEFAULT_EXCLUDE_NOTE = ("Gemini responses via OpenRouter stopped at the max_tokens 1024 limit on 1149 of 1178 "
                        "calls, because reasoning tokens used most of the budget, and the site withholds every "
                        "Gemini arm")
DEFAULT_SEED = 11
DEFAULT_PERMUTATIONS = 1000
DEFAULT_TOP = 15
NOISE_FLOOR_ALPHA = 0.05
COMPARED_ARMS = ("clinical", "patient")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - the scripts ship together
        raise SystemExit(f"cannot load scripts/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ae = _load_module("advice_eval")
_exporter = _load_module("export_advice_scenarios")
DISPLAY_ALIASES: dict[str, str] = dict(_exporter.DISPLAY_ALIASES)


# ----------------------------------------------------------------------- reading


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _display_path(path: Path) -> str:
    """Repo-relative POSIX path when the file is inside this checkout, else as given."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _read_jsonl_numbered(path: Path) -> list[tuple[int, Any]]:
    """(line number, parsed value) for every non-blank line; a corrupt line is a refusal."""
    rows: list[tuple[int, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append((line_no, json.loads(line)))
            except ValueError as exc:
                raise SystemExit(f"{path}:{line_no}: corrupt JSONL line ({exc}); refusing") from exc
    return rows


def _is_pos_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _judgment_problem(row: Any) -> str | None:
    """Why a judgment row is malformed, or None when it is well formed. The tier is checked here only for its type:
    which tier ids are valid depends on the rubric the row was made under, so load_archive checks membership for rows
    made under the supplied rubric and sets rows made under another rubric aside unread."""
    if not isinstance(row, dict):
        return "not a JSON object"
    sha = row.get("response_sha256")
    if not isinstance(sha, str) or not _SHA256_RE.match(sha):
        return "response_sha256 is not a 64-character hex digest"
    rubric_sha = row.get("rubric_sha256")
    if not isinstance(rubric_sha, str) or not _SHA256_RE.match(rubric_sha):
        return "rubric_sha256 is not a 64-character hex digest (every judgment records the rubric it was made under)"
    for key in ("stimulus_id", "model", "judge_model"):
        if not _nonempty_str(row.get(key)):
            return f"{key} is missing or not a non-empty string"
    if row.get("arm") not in ae.ARMS:
        return f"arm {row.get('arm')!r} is not one of {ae.ARMS}"
    if not _is_pos_int(row.get("sample_k")):
        return f"sample_k {row.get('sample_k')!r} is not a positive integer"
    if "tier" not in row:
        return "tier field is absent (a judge failure is recorded as tier null)"
    tier = row["tier"]
    if tier is not None and not _nonempty_str(tier):
        return f"tier {tier!r} is neither null nor a non-empty string"
    return None


def _advice_problem(row: dict) -> str | None:
    """Why an advice response record is malformed, or None."""
    if not _nonempty_str(row.get("stimulus_id")):
        return "stimulus_id is missing or not a non-empty string"
    if row.get("arm") not in ae.ARMS:
        return f"arm {row.get('arm')!r} is not one of {ae.ARMS}"
    if not _nonempty_str(row.get("model_requested")):
        return "model_requested is missing or not a non-empty string"
    if not _is_pos_int(row.get("sample_k")):
        return f"sample_k {row.get('sample_k')!r} is not a positive integer"
    sha = row.get("response_sha256")
    if not isinstance(sha, str) or not _SHA256_RE.match(sha):
        return "response_sha256 is not a 64-character hex digest"
    sent = row.get("sent_utc")
    if sent is not None and not isinstance(sent, str):
        return "sent_utc is neither a string nor null"
    stimuli_sha = row.get("stimuli_sha256")
    if not isinstance(stimuli_sha, str) or not _SHA256_RE.match(stimuli_sha):
        return "stimuli_sha256 is not a 64-character hex digest (every advice record names the stimuli it was sent from)"
    return None


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def check_sidecar(responses_path: Path, sidecar_path: Path, rows: list[dict]) -> None:
    """Refuse unless the archive holds exactly the records its sidecar recorded when they were written.

    ``verify_chain`` proves each record follows the one before it, so an archive cut back to an earlier prefix
    still verifies. Every writer of a responses archive (``advice_eval.py`` elicit, import-manual-responses and
    recover) also writes ``records_total`` and ``chain_head`` to ``responses_<stem>.report.json``; every committed
    sidecar carries both (2026-10-03). A missing sidecar, a missing or malformed field, or a value the archive does
    not match is a refusal, never a skipped check."""
    if not sidecar_path.is_file():
        raise SystemExit(f"{sidecar_path}: missing; it records the record count and chain head that "
                         f"{responses_path.name} must match, so a truncated archive cannot pass; refusing")
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"{sidecar_path}: not valid JSON ({exc}); refusing") from exc
    if not isinstance(sidecar, dict):
        raise SystemExit(f"{sidecar_path}: not a JSON object; refusing")
    total, head = sidecar.get("records_total"), sidecar.get("chain_head")
    if not _is_count(total):
        raise SystemExit(f"{sidecar_path}: records_total {total!r} is missing or not a non-negative integer; refusing")
    if not (head is None and total == 0) and (not isinstance(head, str) or not _SHA256_RE.match(head)):
        raise SystemExit(f"{sidecar_path}: chain_head {head!r} is missing or not a 64-character hex digest; refusing")
    if total != len(rows):
        raise SystemExit(f"{responses_path}: holds {len(rows)} record(s) but {sidecar_path.name} records "
                         f"records_total {total}; refusing to rank a truncated or unrecorded archive")
    archive_head = rows[-1].get("record_sha256") if rows else None
    if head != archive_head:
        raise SystemExit(f"{responses_path}: ends at record {str(archive_head)[:12]} but {sidecar_path.name} records "
                         f"chain_head {str(head)[:12]}; refusing to rank an archive its sidecar does not describe")


@dataclass
class Archive:
    """One stimuli file's judged samples, after the exporter's dedupe."""

    stem: str
    stimuli_path: Path
    inputs: list[dict[str, str]]
    # (stimulus id, display model, arm) -> tiers of the kept samples, in k order
    cells: dict[tuple[str, str, str], list[str]] = field(default_factory=dict)
    judgment_rows: dict[str, int] = field(default_factory=dict)
    response_records: dict[str, int] = field(default_factory=dict)


def _bump(counter: dict[str, int], key: str, by: int = 1) -> None:
    counter[key] = counter.get(key, 0) + by


def load_archive(advice_dir: Path, stem: str, tier_ids: set[str], judge_model: str,
                 rubric_sha256: str) -> Archive:
    """Read one (stimuli, responses, judgments) triple and return its judged cells.

    Refuses on a missing file, a broken hash chain, an archive its sidecar's
    records_total and chain_head do not describe, a malformed advice record or
    judgment row, an advice record elicited from another stimuli document
    (stimuli_sha256), a stimulus id the stimuli file does not define, a judgment
    that names a response the archive does not hold (or holds under another
    key), and an archive whose primary-judge rows were none of them made under
    the rubric whose canonical hash is ``rubric_sha256``.
    """
    stimuli_path = advice_dir / f"{stem}.json"
    responses_path = advice_dir / f"responses_{stem}.jsonl"
    judgments_path = advice_dir / f"judgments_{stem}.jsonl"
    for p in (stimuli_path, responses_path, judgments_path):
        if not p.is_file():
            raise SystemExit(f"{p}: missing; every judged stem needs its stimuli, responses and judgments files")
    inputs = [{"path": _display_path(p), "sha256": _sha256_file(p)}
              for p in (stimuli_path, responses_path, judgments_path)]
    arc = Archive(stem=stem, stimuli_path=stimuli_path, inputs=inputs)

    stimuli_doc = json.loads(stimuli_path.read_text(encoding="utf-8"))
    items = stimuli_doc.get("items") if isinstance(stimuli_doc, dict) else None
    if not isinstance(items, list):
        raise SystemExit(f"{stimuli_path}: no 'items' list; refusing")
    stimulus_ids = {it.get("id") for it in items if isinstance(it, dict)}
    # the hash advice_eval.py elicit stamps on every record it sends from this document
    stimuli_sha256 = ae.sha256_text(ae.canonical_json(stimuli_doc))

    numbered = _read_jsonl_numbered(responses_path)
    rows = [r for _n, r in numbered]
    for line_no, row in numbered:
        if not isinstance(row, dict):
            raise SystemExit(f"{responses_path}:{line_no}: record is not a JSON object; refusing")
    ok, msg = ae.verify_chain(rows)
    if not ok:
        raise SystemExit(f"{responses_path}: {msg}; refusing to rank a tampered or truncated archive")
    check_sidecar(responses_path, advice_dir / f"responses_{stem}.report.json", rows)

    advice: list[dict] = []
    for line_no, row in numbered:
        rtype = row.get("record_type")
        if rtype != "advice":
            _bump(arc.response_records, f"not_advice:{rtype}")
            continue
        problem = _advice_problem(row)
        if problem:
            raise SystemExit(f"{responses_path}:{line_no}: malformed advice record: {problem}; refusing")
        if row["stimulus_id"] not in stimulus_ids:
            raise SystemExit(f"{responses_path}:{line_no}: stimulus id {row['stimulus_id']!r} is not in "
                             f"{stimuli_path.name}; refusing")
        if row["stimuli_sha256"] != stimuli_sha256:
            raise SystemExit(f"{responses_path}:{line_no}: the response was elicited from a stimuli document with "
                             f"canonical sha256 {row['stimuli_sha256'][:12]}, but {stimuli_path.name} hashes to "
                             f"{stimuli_sha256[:12]}; refusing to rank responses against text they were not sent")
        advice.append(row)
    keys_by_sha: dict[str, set[tuple[str, str, str, int]]] = {}
    for r in advice:
        keys_by_sha.setdefault(r["response_sha256"], set()).add(
            (r["stimulus_id"], r["arm"], r["model_requested"], r["sample_k"]))

    # Judgments: validate every row, then keep the last primary non-null tier per response made under the rubric.
    tier_by_sha: dict[str, str] = {}
    other_rubrics: dict[str, int] = {}
    primary_under_rubric = 0
    for line_no, row in _read_jsonl_numbered(judgments_path):
        problem = _judgment_problem(row)
        if problem:
            raise SystemExit(f"{judgments_path}:{line_no}: malformed judgment row: {problem}; refusing")
        if row["rubric_sha256"] == rubric_sha256 and row["tier"] is not None and row["tier"] not in tier_ids:
            # a row made under the supplied rubric must use its tiers (any judge); a row made under another rubric
            # may use that rubric's tiers and is set aside below without its tier being read
            raise SystemExit(f"{judgments_path}:{line_no}: malformed judgment row: tier {row['tier']!r} is not a "
                             f"tier id of the rubric it was made under ({rubric_sha256[:12]}); refusing")
        keys = keys_by_sha.get(row["response_sha256"])
        if keys is None:
            raise SystemExit(f"{judgments_path}:{line_no}: judgment for response "
                             f"{row['response_sha256'][:12]} which {responses_path.name} does not hold; refusing")
        if (row["stimulus_id"], row["arm"], row["model"], row["sample_k"]) not in keys:
            raise SystemExit(f"{judgments_path}:{line_no}: judgment's (stimulus, arm, model, k) does not match "
                             f"the archived response {row['response_sha256'][:12]}; refusing")
        if ae.is_secondary_judge(row["judge_model"]):
            _bump(arc.judgment_rows, "excluded:secondary_judge")
            continue
        if row["judge_model"] != judge_model:
            _bump(arc.judgment_rows, "excluded:other_judge")
            continue
        if row["rubric_sha256"] != rubric_sha256:
            # the same judge under another rubric is a different instrument (as in referral_destination.py)
            _bump(arc.judgment_rows, "excluded:other_rubric")
            _bump(other_rubrics, row["rubric_sha256"][:12])
            continue
        primary_under_rubric += 1
        if row["tier"] is None:
            _bump(arc.judgment_rows, "excluded:null_tier")
            continue
        if row["response_sha256"] in tier_by_sha:
            _bump(arc.judgment_rows, "excluded:superseded_by_later_judgment")
        tier_by_sha[row["response_sha256"]] = row["tier"]
    if other_rubrics and not primary_under_rubric:
        raise SystemExit(f"{judgments_path}: every {judge_model} judgment was made under another rubric "
                         f"({', '.join(f'{d} ({n} rows)' for d, n in sorted(other_rubrics.items()))}), none under "
                         f"the supplied rubric {rubric_sha256[:12]}; refusing to rank this archive under it")
    arc.judgment_rows["used"] = len(tier_by_sha)  # rows left after the exclusions above

    # Exporter dedupe: one record per (stimulus, arm, display model, k).
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for r in advice:
        spec = DISPLAY_ALIASES.get(r["model_requested"], r["model_requested"])
        groups.setdefault((r["stimulus_id"], r["arm"], spec), []).append(r)
    _bump(arc.response_records, "advice", len(advice))
    for (sid, arm, spec), recs in sorted(groups.items()):
        recs.sort(key=lambda r: (r["sample_k"], r["model_requested"] != spec, r.get("sent_utc") or ""))
        seen_k: set[int] = set()
        for r in recs:
            if r["sample_k"] in seen_k:
                _bump(arc.response_records, "excluded:duplicate_sample")
                continue
            seen_k.add(r["sample_k"])
            if arm not in COMPARED_ARMS:
                _bump(arc.response_records, "excluded:translated_arm")
                continue
            tier = tier_by_sha.get(r["response_sha256"])
            if tier is None:
                _bump(arc.response_records, "excluded:no_primary_tier")
                continue
            arc.cells.setdefault((sid, spec, arm), []).append(tier)
            _bump(arc.response_records, "used")
    return arc


# --------------------------------------------------------------------- statistics


def modal_tier(tiers: list[str], rank: dict[str, int]) -> str:
    """Most frequent tier; ties go to the more urgent tier (the analyze/exporter rule)."""
    modal = ae._modal_tier(tiers, rank)
    if modal is None:  # pragma: no cover - callers pass non-empty lists
        raise ValueError("modal tier of an empty cell")
    return modal


def downgrade_null_probability(clinical: list[str], patient: list[str], rank: dict[str, int],
                               permutations: int, rng: random.Random) -> float:
    """Share of within-cell arm-label permutations that produce a downgrade."""
    pool = list(clinical) + list(patient)
    n_c = len(clinical)
    hits = 0
    for _ in range(permutations):
        rng.shuffle(pool)
        if rank[modal_tier(pool[:n_c], rank)] > rank[modal_tier(pool[n_c:], rank)]:
            hits += 1
    return hits / permutations


def poisson_binomial(probabilities: list[float]) -> list[float]:
    """Distribution of the number of successes over independent Bernoulli(q_i)."""
    dist = [1.0]
    for q in probabilities:
        nxt = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            nxt[i] += v * (1.0 - q)
            nxt[i + 1] += v * q
        dist = nxt
    return dist


def tail(dist: list[float], k: int) -> float:
    """P(X >= k) from a distribution list; 0 beyond its support."""
    return min(1.0, sum(dist[k:])) if k < len(dist) else 0.0


def _cell_rng(seed: int, stem: str, sid: str, model: str) -> random.Random:
    # A str seed is hashed with sha512 by random.Random (seeding version 2), so this
    # is stable across runs and Python processes and independent of PYTHONHASHSEED.
    return random.Random(f"{seed}|{stem}|{sid}|{model}")


@dataclass
class PairedCell:
    stem: str
    sid: str
    model: str
    clinical: list[str]
    patient: list[str]
    clinical_modal: str
    patient_modal: str
    drop: int
    patient_below: int
    q_null: float


def paired_cells(archives: list[Archive], rank: dict[str, int], seed: int,
                 permutations: int) -> list[PairedCell]:
    out: list[PairedCell] = []
    for arc in archives:
        models_by_sid: dict[str, set[str]] = {}
        for (sid, model, _arm) in arc.cells:
            models_by_sid.setdefault(sid, set()).add(model)
        for sid in sorted(models_by_sid):
            for model in sorted(models_by_sid[sid]):
                c = arc.cells.get((sid, model, "clinical"))
                p = arc.cells.get((sid, model, "patient"))
                if not c or not p:
                    continue
                cm, pm = modal_tier(c, rank), modal_tier(p, rank)
                q = downgrade_null_probability(c, p, rank, permutations, _cell_rng(seed, arc.stem, sid, model))
                out.append(PairedCell(
                    stem=arc.stem, sid=sid, model=model, clinical=list(c), patient=list(p),
                    clinical_modal=cm, patient_modal=pm, drop=rank[cm] - rank[pm],
                    patient_below=sum(1 for t in p if rank[t] < rank[cm]), q_null=q))
    return out


def _excluded(model: str, substrings: list[str]) -> bool:
    return any(s in model for s in substrings)


def rank_stimuli(cells: list[PairedCell], exclude: list[str]) -> list[dict[str, Any]]:
    """Per-stimulus aggregates over the counted models, ranked by the documented key."""
    by_stim: dict[tuple[str, str], list[PairedCell]] = {}
    for c in cells:
        by_stim.setdefault((c.stem, c.sid), []).append(c)
    rows: list[dict[str, Any]] = []
    for (stem, sid), group in by_stim.items():
        counted = [c for c in group if not _excluded(c.model, exclude)]
        if not counted:
            continue
        downs = [c for c in counted if c.drop > 0]
        n_patient = sum(len(c.patient) for c in counted)
        below = sum(c.patient_below for c in counted)
        dist = poisson_binomial([c.q_null for c in counted])
        rows.append({
            "stem": stem, "sid": sid,
            "n_models": len(counted),
            "downgrades": len(downs),
            "sum_drop": sum(c.drop for c in downs),
            "severe_downgrades": sum(1 for c in counted if c.drop >= 2),
            "upgrades": sum(1 for c in counted if c.drop < 0),
            "patient_samples_below_clinical_modal": below,
            "patient_samples": n_patient,
            "share_below": below / n_patient if n_patient else 0.0,
            "n_models_with_excluded": len(group),
            "downgrades_with_excluded": sum(1 for c in group if c.drop > 0),
            "null_dist": dist,
            "counted": counted,
        })
    rows.sort(key=lambda r: (-r["downgrades"], -r["sum_drop"], -r["share_below"], r["stem"], r["sid"]))
    return rows


def per_model_summary(cells: list[PairedCell]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in cells:
        m = out.setdefault(c.model, {"paired": 0, "downgrades": 0, "upgrades": 0, "severe_downgrades": 0,
                                     "null_expected_downgrades": 0.0})
        m["paired"] += 1
        m["downgrades"] += int(c.drop > 0)
        m["upgrades"] += int(c.drop < 0)
        m["severe_downgrades"] += int(c.drop >= 2)
        m["null_expected_downgrades"] += c.q_null
    for m in out.values():
        m["downgrade_rate"] = round(m["downgrades"] / m["paired"], 4)
        m["excess_downgrades_per_pair"] = round((m["downgrades"] - m["null_expected_downgrades"]) / m["paired"], 4)
        m["null_expected_downgrades"] = round(m["null_expected_downgrades"], 3)
    return dict(sorted(out.items()))


# ------------------------------------------------------------------------- output


def build_report(advice_dir: Path, stems: list[str], rubric_path: Path, judge_model: str,
                 exclude: list[str], exclude_note: str, top: int, seed: int,
                 permutations: int, command: str = "") -> dict[str, Any]:
    """The ranking report: the rule, the selected items with their metrics, and everything needed to recompute
    them (seed, permutations, judge, exclusions, rubric, input sha256s, row accounting)."""
    if permutations < 1:
        raise SystemExit("--permutations must be at least 1")
    if top < 1:
        raise SystemExit("--top must be at least 1")
    refuse_duplicate_stems(stems)
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    tier_order = [t["id"] for t in rubric["tiers"]]
    rank = {t: i for i, t in enumerate(tier_order)}
    rubric_sha256 = ae.sha256_text(ae.canonical_json(rubric))   # the hash advice_eval.py judge stamps on each row
    archives = [load_archive(advice_dir, stem, set(tier_order), judge_model, rubric_sha256) for stem in stems]
    cells = paired_cells(archives, rank, seed, permutations)
    ranked = rank_stimuli(cells, exclude)
    if not ranked:
        raise SystemExit("no stimulus has a paired clinical/patient cell from a counted model; nothing to rank")
    n_tested = len(ranked)
    max_count = max(len(r["null_dist"]) for r in ranked)
    expected_at_or_above = [sum(tail(r["null_dist"], k) for r in ranked) for k in range(max_count + 1)]
    observed_at_or_above = [sum(1 for r in ranked if r["downgrades"] >= k) for k in range(max_count + 1)]
    distribution: dict[str, int] = {}
    for r in ranked:
        distribution[str(r["downgrades"])] = distribution.get(str(r["downgrades"]), 0) + 1

    id_files: dict[str, list[str]] = {}
    for r in ranked[:top]:
        id_files.setdefault(r["sid"], []).append(r["stem"])

    items: list[dict[str, Any]] = []
    clearing: list[int] = []
    for i, r in enumerate(ranked[:top], 1):
        d = r["downgrades"]
        p_tail = tail(r["null_dist"], d)
        p_bonf = min(1.0, p_tail * n_tested)
        clears = d > 0 and expected_at_or_above[d] < NOISE_FLOOR_ALPHA
        if clears:
            clearing.append(i)
        stim_path = advice_dir / f"{r['stem']}.json"
        item: dict[str, Any] = {
            "file": _display_path(stim_path),
            "id": r["sid"],
            "rank": i,
            "downgrades": d,
            "models_counted": r["n_models"],
            "sum_drop": r["sum_drop"],
            "severe_downgrades": r["severe_downgrades"],
            "upgrades": r["upgrades"],
            "patient_samples_below_clinical_modal": r["patient_samples_below_clinical_modal"],
            "patient_samples": r["patient_samples"],
            "share_patient_samples_below_clinical_modal": round(r["share_below"], 4),
            "downgrades_with_excluded_models": r["downgrades_with_excluded"],
            "models_with_excluded_models": r["n_models_with_excluded"],
            "null_expected_downgrades": round(sum(c.q_null for c in r["counted"]), 4),
            "p_tail": round(p_tail, 6),
            "p_tail_bonferroni": round(p_bonf, 6),
            "null_expected_stimuli_at_or_above": round(expected_at_or_above[d], 4),
            "observed_stimuli_at_or_above": observed_at_or_above[d],
            "clears_noise_floor": clears,
            "per_model": [{
                "model": c.model, "clinical_modal": c.clinical_modal, "patient_modal": c.patient_modal,
                "drop": c.drop, "n_clinical": len(c.clinical), "n_patient": len(c.patient),
                "patient_below_clinical_modal": c.patient_below, "q_null": round(c.q_null, 4),
            } for c in r["counted"]],
        }
        if len(id_files[r["sid"]]) > 1:
            others = [s for s in id_files[r["sid"]] if s != r["stem"]]
            item["same_situation_also_selected_from"] = [_display_path(advice_dir / f"{s}.json") for s in others]
        items.append(item)

    rule = (
        f"Post-hoc selection of the top {top} earlier advice stimuli by cross-model advice downgrade, "
        f"computed by scripts/advice_rerun_select.py from the committed archives. Metric: for each "
        f"(stimuli file, stimulus, model), the modal tier of the judged samples on each arm (primary "
        f"judge {judge_model} only, one sample per (file, stimulus, arm, model, k) chosen the exporter's "
        f"way, ties toward the more urgent tier); a downgrade is a patient-arm modal tier below the "
        f"clinical-arm modal tier. Stimuli are ranked by the number of models with a downgrade, not "
        f"counting models whose spec contains {', '.join(repr(s) for s in exclude) or 'nothing'} "
        f"({exclude_note}); ties by summed tier drop, then by the share of patient samples coded below "
        f"the clinical modal tier, then by file and id. The selection is post hoc: it was chosen after "
        f"seeing these codings, {n_tested} stimuli were ranked, and the codings are provisional machine "
        f"codings under rubric {rubric.get('version')}. Noise floor: a within-cell arm-label permutation "
        f"null (seed {seed}, {permutations} permutations per cell) gives each stimulus's chance of reaching "
        f"its downgrade count; an item with count k clears the noise floor when the expected number of the "
        f"{n_tested} ranked stimuli reaching at least k under that null is below {NOISE_FLOOR_ALPHA}. Items "
        f"clearing it: {', '.join('#' + str(i) for i in clearing) if clearing else 'none'}; the rest are "
        f"consistent with chance. Under the more conservative Bonferroni adjustment of each item's own "
        f"tail probability, "
        f"{_bonferroni_phrase(items)}. A rerun of this selection is therefore a replication test, and its "
        f"downgrade counts should be expected to regress toward the mean."
    )
    inputs = [entry for arc in archives for entry in arc.inputs]
    inputs.append({"path": _display_path(rubric_path), "sha256": _sha256_file(rubric_path)})
    return {
        "rule": rule,
        "items": items,
        "selection": {
            "top": top, "n_stimuli_ranked": n_tested,
            "items_clearing_noise_floor": clearing,
            "noise_floor": (f"null_expected_stimuli_at_or_above(k) < {NOISE_FLOOR_ALPHA}, where k is the item's "
                            "downgrade count (a union bound on the chance that any ranked stimulus reaches k)"),
            "items_clearing_bonferroni": [it["rank"] for it in items
                                          if it["downgrades"] > 0 and it["p_tail_bonferroni"] < NOISE_FLOOR_ALPHA],
            "post_hoc": True,
            "downgrade_count_distribution": dict(sorted(distribution.items(), key=lambda kv: int(kv[0]))),
            "null_expected_stimuli_at_or_above": [round(v, 4) for v in expected_at_or_above],
            "observed_stimuli_at_or_above": observed_at_or_above,
        },
        "seed": seed,
        "permutations": permutations,
        "judge_model": judge_model,
        "excluded_models": {"substrings": list(exclude), "note": exclude_note},
        "rubric": {"path": _display_path(rubric_path), "version": rubric.get("version"),
                   "canonical_sha256": rubric_sha256, "tier_order": tier_order},
        "display_aliases": DISPLAY_ALIASES,
        "inputs": inputs,
        "row_accounting": {arc.stem: {"judgment_rows": dict(sorted(arc.judgment_rows.items())),
                                      "response_records": dict(sorted(arc.response_records.items()))}
                           for arc in archives},
        "per_model": per_model_summary(cells),
        "generated_utc": ae.utc_now_iso(),
        "engine_sha": ae.engine_sha(),
        "script": "scripts/advice_rerun_select.py",
        "command": command,
    }


def refuse_duplicate_stems(stems: list[str]) -> None:
    """Refuse a stem named more than once: its archive would be loaded twice and every one of its cells counted
    twice, in the downgrade counts and as independent draws in the null."""
    repeated = sorted({s for s in stems if stems.count(s) > 1})
    if repeated:
        raise SystemExit(f"stem(s) named more than once: {', '.join(repeated)}; each archive is ranked once, so a "
                         "repeated --stem would count its cells twice; refusing")


def _bonferroni_phrase(items: list[dict[str, Any]]) -> str:
    passing = [it for it in items if it["downgrades"] > 0 and it["p_tail_bonferroni"] < NOISE_FLOOR_ALPHA]
    if passing:
        return "items clearing " + str(NOISE_FLOOR_ALPHA) + ": " + ", ".join(
            f"#{it['rank']} (adjusted p {it['p_tail_bonferroni']:.4f})" for it in passing)
    best = min(items, key=lambda it: it["p_tail_bonferroni"])
    return (f"no item clears {NOISE_FLOOR_ALPHA} (smallest adjusted p {best['p_tail_bonferroni']:.4f}, "
            f"item #{best['rank']})")


def selection_for_builder(report: dict[str, Any], report_path: str, report_sha256: str) -> dict[str, Any]:
    """The selection file that ``advice_eval.py build-stimuli --source selection`` reads: exactly
    {rule, items: [{file, id}], notes}, the items in rank order. The builder refuses any other key, so every
    metric stays in the report, which the notes name by path and sha256."""
    notes = (f"Items in rank order from the ranking report {report_path} (sha256 {report_sha256}), written in the "
             f"same run of {report['script']} with seed {report['seed']} and {report['permutations']} permutations "
             "per cell; that report holds each item's metrics, the null, the noise-floor decision and the sha256 of "
             "every input. The selection is post hoc: the items were chosen after seeing these codings, so a rerun "
             "of them is a replication test.")
    ranked = sorted(report["items"], key=lambda it: it["rank"])
    return {"rule": report["rule"], "items": [{"file": it["file"], "id": it["id"]} for it in ranked], "notes": notes}


def _write_new(path: Path, doc: dict[str, Any]) -> None:
    """Write a JSON document to a file that must not exist yet (mode "x"; data/advice/ is append-only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")


def discover_stems(advice_dir: Path) -> list[str]:
    stems = sorted(p.name[len("judgments_"):-len(".jsonl")] for p in advice_dir.glob("judgments_*.jsonl"))
    if not stems:
        raise SystemExit(f"{advice_dir}: no judgments_*.jsonl files")
    return stems


def _print_table(report: dict[str, Any]) -> None:
    print(f"{'#':>2} {'stimuli file':34} {'stimulus id':36} {'down/n':>7} {'drop':>4} {'sev':>3} {'up':>3} "
          f"{'below':>6} {'+excl':>6} {'p_tail':>8} {'E(k)':>8} clears")
    for it in report["items"]:
        print(f"{it['rank']:>2} {Path(it['file']).stem:34} {it['id']:36} "
              f"{it['downgrades']:>3}/{it['models_counted']:<3} {it['sum_drop']:>4} {it['severe_downgrades']:>3} "
              f"{it['upgrades']:>3} {it['share_patient_samples_below_clinical_modal']:>6.3f} "
              f"{it['downgrades_with_excluded_models']:>2}/{it['models_with_excluded_models']:<3} "
              f"{it['p_tail']:>8.4f} {it['null_expected_stimuli_at_or_above']:>8.4f} {it['clears_noise_floor']}")
    print("ranked:", report["selection"]["n_stimuli_ranked"],
          "| distribution:", report["selection"]["downgrade_count_distribution"])


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--advice-dir", default=DEFAULT_ADVICE_DIR)
    parser.add_argument("--stem", action="append", default=None,
                        help="stimuli stem to include (repeatable); default: every judgments_*.jsonl")
    parser.add_argument("--rubric", default=DEFAULT_RUBRIC)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE)
    parser.add_argument("--exclude-model", action="append", default=None,
                        help=f"model-spec substring not counted in the ranking (repeatable; default {DEFAULT_EXCLUDE})")
    parser.add_argument("--exclude-note", default=DEFAULT_EXCLUDE_NOTE)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    parser.add_argument("--report-out", default=None,
                        help="ranking report to write: the rule, each item's metrics, the null and the inputs' "
                             "sha256 (refused if it exists: data/advice/ is append-only)")
    parser.add_argument("--selection-out", default=None,
                        help="selection to write for advice_eval.py build-stimuli --source selection, exactly "
                             "{rule, items: [{file, id}], notes} (refused if it exists); requires --report-out, "
                             "whose path and sha256 its notes carry")
    parser.add_argument("--print-table", action="store_true", help="print the ranked items (ids and metrics only)")
    args = parser.parse_args(argv)

    advice_dir = Path(args.advice_dir)
    report_out = Path(args.report_out) if args.report_out else None
    selection_out = Path(args.selection_out) if args.selection_out else None
    if (report_out is None) != (selection_out is None):
        raise SystemExit("--report-out and --selection-out are written together: the selection's notes name the "
                         "report by path and sha256")
    if report_out is not None and selection_out is not None:
        if report_out.resolve() == selection_out.resolve():
            raise SystemExit("--report-out and --selection-out name the same file")
        # both checked before anything is computed or written, so a refusal leaves no half-written pair
        for out in (report_out, selection_out):
            if out.exists():
                raise SystemExit(f"{out}: exists; data/advice/ is append-only, so write a new file instead")
    stems = args.stem or discover_stems(advice_dir)
    refuse_duplicate_stems(stems)
    exclude = list(args.exclude_model) if args.exclude_model is not None else list(DEFAULT_EXCLUDE)
    cli_args = list(argv) if argv is not None else sys.argv[1:]
    report = build_report(advice_dir, stems, Path(args.rubric), args.judge_model, exclude,
                          args.exclude_note, args.top, args.seed, args.permutations,
                          command="python scripts/advice_rerun_select.py " + " ".join(cli_args))
    if args.print_table or report_out is None:
        _print_table(report)
    if report_out is not None and selection_out is not None:
        _write_new(report_out, report)
        report_sha256 = _sha256_file(report_out)   # the file as written, so the notes name exactly these bytes
        _write_new(selection_out, selection_for_builder(report, _display_path(report_out), report_sha256))
        print(f"wrote the ranking report ({len(report['items'])} item(s)) -> {report_out}")
        print(f"wrote the selection for build-stimuli -> {selection_out} (report sha256 {report_sha256})")
    return report


if __name__ == "__main__":
    main()
