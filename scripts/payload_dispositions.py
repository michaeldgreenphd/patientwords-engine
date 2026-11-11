#!/usr/bin/env python3
"""Pending scientific differences between the published gallery payload and a candidate, and their dispositions.

A full export of the site's ``data/simulated_scenarios.json`` can change what a reader was already shown: a
measured value at a published ``(batch, batch_index, model)``, a measurement that is no longer there, or a
model's capability label. The contract gate does not see that (both payloads are well formed), and a new
analysis snapshot would record the changed file as a fresh sha256 without anyone having decided the change
(``docs/corrections/payload_summary_dedupe_20261110.md``). This module is the one definition of such a
difference and of what lets one through. Two callers use it:

* ``scripts/export_frontend_simulated.py``, before its first write or prune in the site checkout;
* ``scripts/results_snapshot.py``: ``create`` refuses and ``check-release`` prints one ``REFUSED:`` line per
  difference, comparing the payload in two site commits.

What is a difference (``scientific_differences``; reference = what is published, candidate = what would be):

* for every ``(batch, batch_index, model)`` that holds a measured value in the reference: a measured field
  whose value is not exactly the reference's (``values_changed``; a value that became null is one), the model
  no longer on the row (``model_removed``), or the row no longer in the payload (``row_removed``);
* for every model in both payloads' ``models_meta``: a changed capability field (``MODELS_META_CAPABILITY``),
  and a changed field of its ``traced_by_model`` entry (``TRACED_FIELDS``).

What is not: a new batch, a new row, a new model on an existing row, a value where the reference had none;
the display ``index``; the joins a later publish step embeds (``urgency``, ``depth_class``, ``urgency_meta``,
``depth_model``, ``featured``); ``trace_url`` and ``traces_site``; the render lists (``html``, ``png``); the
``summary`` block, which the contract gate recomputes; ``models_meta[].n_traced``, a count that follows from
rows added or removed; and the stimulus text, which the append-only batch files own.

Values are compared exactly, as stored. The exporter copies them from the summary parts and computes nothing
that depends on run order, so two exports of the same inputs give the same values; a tolerance would only
hide a changed published number.

The top-level base-model mirror of a scenario is compared only when the scenario has no ``models`` object
(an older payload): the exporter derives the mirror from ``models``, and the contract gate checks that the
two agree. ``traced`` is the exporter's copy of ``traced_by_model[<base model>]`` and is read only when an
older payload has no ``traced_by_model``.

A difference passes only when the committed record ``data/results_policy/payload_dispositions.v1.json`` holds
an entry that covers exactly it (identity, change, fields, and the reference and candidate values) with the
disposition ``accept_candidate``, ``decided_by`` ``"owner"`` and a ``decision_ref`` naming the committed
document that records the decision. ``pending``, ``keep_reference`` and ``withhold`` never pass; they say
what the owner has or has not decided. There is no option that skips the check.

No prompt, target or token text is printed or recorded here: tokens are reduced to their length, token
lists to their length, and a sha256 over the measured fields covers the rest
(``data/results_policy/legacy_payload_rows.v1.json`` uses the same row hash).

  python scripts/payload_dispositions.py check --reference <published payload> --candidate <new payload>
  python scripts/payload_dispositions.py propose --reference ... --candidate ... [--write]

``check`` prints the table and exits 0 (no difference, or every difference accepted), 1 (a difference without
an accepting disposition) or 2 (a file could not be read). ``propose`` prints, and with ``--write`` appends to
the record, a ``pending`` entry for each difference the record does not cover yet. It never writes another
disposition and never changes an existing entry: a decision is entered by hand in a reviewed commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

SCHEMA = "patientwords.payload-dispositions/1"
RECORD_REL = "data/results_policy/payload_dispositions.v1.json"
PAYLOAD_REL = "data/simulated_scenarios.json"
BASE_MODEL = "gemma-2-2b"

# The per-model measurement object, exactly as export_frontend_simulated.build_model_obj writes it
# (tests/test_payload_dispositions.py reads the exporter's source and the contract schema to keep the three equal).
MEASURED_FIELDS: tuple[str, ...] = (
    "prob_clinical", "prob_patient", "language_penalty", "anchor_fallback", "top_clinical", "top_patient",
    "spread_clinical", "spread_patient", "target_token", "flipped", "screening", "circuit_diff", "clinical_mass")
# Two fields are computed from other fields. They count as measured only when what they are computed from
# is there: ``flipped`` is false, not unknown, on a row with one side missing.
DERIVED_FROM: dict[str, tuple[str, ...]] = {"flipped": ("top_clinical", "top_patient"),
                                            "anchor_fallback": ("target_token",)}
# models_meta: every field the exporter writes is in exactly one of these two.
MODELS_META_CAPABILITY: tuple[str, ...] = ("graph_model", "source_set", "features", "attention_replacement",
                                           "graphs", "available", "default")
MODELS_META_NOT_COMPARED: dict[str, str] = {
    "id": "the identity the comparison is keyed on",
    "label": "a display name",
    "n_traced": "a count of rows; it follows from rows added or removed, which are compared one by one",
}
# traced_by_model[<model>]: the block ``graphs`` is derived from.
TRACED_FIELDS: tuple[str, ...] = ("graph_model", "source_set", "mode", "backend")

PENDING, ACCEPT, KEEP, WITHHOLD = "pending", "accept_candidate", "keep_reference", "withhold"
DISPOSITIONS: dict[str, str] = {
    PENDING: "the owner has not decided; an export or release that makes this difference is refused",
    ACCEPT: "the owner accepts the candidate as recorded here (a changed value, or a removal); the difference "
            "passes while the reference and candidate values are exactly the recorded ones",
    KEEP: "the owner keeps the published value; an export that changes it is refused until the exporter "
          "reproduces the published value, and then there is no difference",
    WITHHOLD: "the owner accepts neither value: the row is to show as not measured for this model. An export "
              "that still carries a value is refused; the removal, once the exporter makes it, is a new "
              "difference with its own entry",
}
DECIDED_BY = "owner"
ROW_KEYS = ("scope", "batch", "batch_index", "model", "change", "fields", "reference", "candidate")
META_KEYS = ("scope", "block", "model", "field", "reference", "candidate")
HEADLINE_FIELDS = ("prob_clinical", "prob_patient", "language_penalty", "flipped")   # the numbers a table row shows
MAX_TABLE_ROWS = 60

_ABSENT = object()
_STATUS = re.compile(r"[a-z_]{1,40}\Z")
_PLAIN = re.compile(r"[A-Za-z0-9 ._:/+-]{0,64}\Z")


class DispositionError(RuntimeError):
    """The record or a payload cannot be read soundly; a caller refuses."""


# ---------------------------------------------------------------- exact comparison

def same(a: Any, b: Any) -> bool:
    """Exact equality of two JSON values as stored: a boolean equals only a boolean, numbers compare by
    value with no tolerance, lists element by element in order, objects key by key."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(v, b[k]) for k, v in a.items())
    return type(a) is type(b) and a == b


def has_value(obj: Mapping[str, Any], name: str) -> bool:
    """Whether ``obj`` holds a measured value in ``name``: not null, not an empty list or object, and for a
    derived field only when every field it is computed from holds one."""
    sources = DERIVED_FROM.get(name)
    if sources is not None:
        return obj.get(name) is not None and all(has_value(obj, s) for s in sources)
    value = obj.get(name)
    return value is not None and value != [] and value != {}


# ---------------------------------------------------------------- text-free description of one measurement

def measurement_sha256(obj: Mapping[str, Any]) -> str:
    """sha256 over the measured fields of one model object: UTF-8 JSON, sorted keys, compact separators,
    non-ASCII kept. For an object that holds all of them and no render path this is the legacy record's
    ``payload_measurement_sha256`` (the object without its ``urgency`` join)."""
    kept = {k: obj[k] for k in MEASURED_FIELDS if k in obj}
    return hashlib.sha256(json.dumps(kept, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _number(value: Any) -> Any:
    return value if value is None or isinstance(value, (bool, int, float)) else None


def _top_p(value: Any) -> Any:
    return _number(value[1]) if isinstance(value, list) and len(value) == 2 else None


def text_free(obj: Mapping[str, Any]) -> dict[str, Any]:
    """Numbers, booleans, counts and lengths of one model object's measured fields. No token or prompt text:
    the keys are the legacy record's ``payload_row`` keys without the ``urgency`` join."""
    screening = obj.get("screening")
    status = screening.get("status") if isinstance(screening, dict) else None
    mass = obj.get("clinical_mass")
    target = obj.get("target_token")
    return {
        "prob_clinical": _number(obj.get("prob_clinical")),
        "prob_patient": _number(obj.get("prob_patient")),
        "language_penalty": _number(obj.get("language_penalty")),
        "flipped": _number(obj.get("flipped")),
        "anchor_fallback": _number(obj.get("anchor_fallback")),
        "screening": status if isinstance(status, str) and _STATUS.match(status) else None,
        "clinical_mass": ({k: _number(v) for k, v in sorted(mass.items()) if isinstance(k, str)
                           and _STATUS.match(k)} if isinstance(mass, dict) else None),
        "circuit_diff_present": has_value(obj, "circuit_diff"),
        "top_clinical_p": _top_p(obj.get("top_clinical")),
        "top_patient_p": _top_p(obj.get("top_patient")),
        "spread_clinical_n": len(obj["spread_clinical"]) if isinstance(obj.get("spread_clinical"), list) else None,
        "spread_patient_n": len(obj["spread_patient"]) if isinstance(obj.get("spread_patient"), list) else None,
        "target_token_chars": len(target) if isinstance(target, str) else None,
    }


def _side(obj: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return None if obj is None else {"measurement_sha256": measurement_sha256(obj), "values": text_free(obj)}


# ---------------------------------------------------------------- the comparison (pure)

def _base_model(payload: Mapping[str, Any]) -> str:
    traced = payload.get("traced")
    named = traced.get("graph_model") if isinstance(traced, dict) else None
    return named if isinstance(named, str) and named else BASE_MODEL


def _model_objects(scenario: Mapping[str, Any], base_model: str) -> dict[str, Mapping[str, Any]]:
    """model id -> measurement object of one scenario. A scenario without a ``models`` object (an older
    payload) is read through its top-level base-model fields."""
    models = scenario.get("models")
    if isinstance(models, dict):
        return {m: o for m, o in models.items() if isinstance(m, str) and isinstance(o, dict)}
    top = {name: scenario[name] for name in MEASURED_FIELDS if name in scenario}
    return {base_model: top} if any(has_value(top, name) for name in top) else {}


def _rows(payload: Mapping[str, Any]) -> tuple[dict[tuple[str, int, str], Mapping[str, Any]],
                                                 set[tuple[str, int]], int]:
    """((batch, batch_index, model) -> object, the (batch, batch_index) present, the number of scenarios that
    hold a measured value and no usable identity)."""
    base = _base_model(payload)
    rows: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    present: set[tuple[str, int]] = set()
    unidentified = 0
    scenarios = payload.get("scenarios")
    for scenario in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(scenario, dict):
            continue
        batch, index = scenario.get("batch"), scenario.get("batch_index")
        objects = _model_objects(scenario, base)
        if not isinstance(batch, str) or not batch or isinstance(index, bool) or not isinstance(index, int):
            if any(has_value(obj, name) for obj in objects.values() for name in MEASURED_FIELDS):
                unidentified += 1
            continue
        present.add((batch, index))
        for model, obj in objects.items():
            rows.setdefault((batch, index, model), obj)
    return rows, present, unidentified


def _meta_by_model(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    meta = payload.get("models_meta")
    return {m["id"]: m for m in (meta if isinstance(meta, list) else [])
            if isinstance(m, dict) and isinstance(m.get("id"), str)}


def _traced_by_model(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    block = payload.get("traced_by_model")
    if isinstance(block, dict):
        return {m: v for m, v in block.items() if isinstance(m, str) and isinstance(v, dict)}
    traced = payload.get("traced")
    return {_base_model(payload): traced} if isinstance(traced, dict) and traced else {}


def _meta_differences(block: str, names: Iterable[str], reference: Mapping[str, Mapping[str, Any]],
                      candidate: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for model in sorted(set(reference) & set(candidate)):
        for name in names:
            if name not in reference[model]:
                continue                                    # an older payload without the field: nothing published
            before, after = reference[model][name], candidate[model].get(name, _ABSENT)
            if after is _ABSENT or not same(before, after):
                out.append({"scope": "metadata", "block": block, "model": model, "field": name,
                            "reference": before, "candidate": None if after is _ABSENT else after})
    return out


def scientific_differences(reference: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every difference between the published payload and the candidate that changes a published
    measurement or capability label (module docstring). Pure: reads its two arguments and nothing else.

    A row difference is ``{"scope": "row", "batch", "batch_index", "model", "change", "fields", "reference",
    "candidate"}``: ``change`` is ``values_changed``, ``model_removed`` or ``row_removed``; ``fields`` are the
    measured fields that differ (for a removal, the ones that held a value); each side is
    ``{"measurement_sha256", "values"}`` with ``values`` text-free, and ``candidate`` is null for a removal.
    A metadata difference is ``{"scope": "metadata", "block", "model", "field", "reference", "candidate"}``.
    A reference scenario that holds a measured value and no ``(batch, batch_index)`` cannot be compared; all
    of them are reported as one difference of scope ``unidentified``, which no disposition covers."""
    ref_rows, _, unidentified = _rows(reference)
    cand_rows, cand_present, _ = _rows(candidate)
    out: list[dict[str, Any]] = []
    for key in sorted(ref_rows):
        batch, index, model = key
        ref_obj = ref_rows[key]
        measured = [name for name in MEASURED_FIELDS if has_value(ref_obj, name)]
        if not measured:
            continue
        cand_obj = cand_rows.get(key)
        if cand_obj is None:
            change, names = ("model_removed" if (batch, index) in cand_present else "row_removed"), measured
        else:
            change = "values_changed"
            names = [n for n in measured if not same(ref_obj.get(n), cand_obj.get(n, None))]
            if not names:
                continue
        out.append({"scope": "row", "batch": batch, "batch_index": index, "model": model, "change": change,
                    "fields": sorted(names), "reference": _side(ref_obj), "candidate": _side(cand_obj)})
    if unidentified:
        out.append({"scope": "unidentified", "count": unidentified})
    out += _meta_differences("models_meta", MODELS_META_CAPABILITY, _meta_by_model(reference),
                             _meta_by_model(candidate))
    out += _meta_differences("traced_by_model", TRACED_FIELDS, _traced_by_model(reference),
                             _traced_by_model(candidate))
    return out


# ---------------------------------------------------------------- the record and the review (pure)

def identity(item: Mapping[str, Any]) -> tuple[Any, ...]:
    """What a difference or a record entry is about, without its values."""
    if item.get("scope") == "row":
        return ("row", item.get("batch"), item.get("batch_index"), item.get("model"))
    if item.get("scope") == "metadata":
        return ("metadata", item.get("block"), item.get("model"), item.get("field"))
    return (item.get("scope"),)


def covers(entry: Mapping[str, Any], difference: Mapping[str, Any]) -> bool:
    """Whether ``entry`` records exactly this difference: the same identity, change, fields and both sides."""
    keys = ROW_KEYS if difference.get("scope") == "row" else META_KEYS if difference.get("scope") == "metadata" \
        else ()
    return bool(keys) and all(k in entry and same(entry[k], difference[k]) for k in keys)


def entry_problem(entry: Any, exists: Callable[[str], bool] | None = None) -> str | None:
    """Why a record entry cannot be relied on; None when it is well formed. ``exists`` says whether a
    repository-relative path is a committed file, for ``decision_ref``."""
    if not isinstance(entry, dict):
        return "the entry is not an object"
    keys = ROW_KEYS if entry.get("scope") == "row" else META_KEYS if entry.get("scope") == "metadata" else None
    if keys is None:
        return f"scope {entry.get('scope')!r} is not 'row' or 'metadata'"
    missing = [k for k in keys if k not in entry]
    if missing:
        return f"missing {', '.join(missing)}"
    disposition = entry.get("disposition")
    if disposition not in DISPOSITIONS:
        return f"disposition {disposition!r} is not one of {', '.join(DISPOSITIONS)}"
    decided_by, ref = entry.get("decided_by"), entry.get("decision_ref")
    if disposition == PENDING:
        return None if decided_by is None and ref is None else "a pending entry names no decision"
    if decided_by != DECIDED_BY:
        return f"decided_by is {decided_by!r}; a disposition other than pending is the owner's ({DECIDED_BY!r})"
    if not isinstance(ref, str) or not ref.strip():
        return "decision_ref is empty; it names the committed document that records the owner's decision"
    path = ref.partition("#")[0].strip()
    if exists is not None and not exists(path):
        return f"decision_ref names {path!r}, which is not a committed file of the engine"
    return None


@dataclass
class Record:
    """The disposition record as one caller read it."""
    entries: list[Any] = field(default_factory=list)
    source: str = "no record"
    committed: bool | None = None       # None: the record's checkout is not a git repository
    exists: Callable[[str], bool] | None = None


def parse_record(data: bytes | str | None, *, source: str, committed: bool | None = None,
                 exists: Callable[[str], bool] | None = None) -> Record:
    """A record from its bytes; ``None`` is a checkout without one, which disposes nothing. Raises
    ``DispositionError`` when the bytes are not a record: an unreadable record is not an empty one."""
    if data is None:
        return Record(source=f"{source} (absent: no difference is disposed)", committed=committed, exists=exists)
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise DispositionError(f"{source} is not JSON ({exc})") from exc
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or not isinstance(doc.get("entries"), list):
        raise DispositionError(f"{source} is not a {SCHEMA} record with an 'entries' list")
    return Record(entries=doc["entries"], source=source, committed=committed, exists=exists)


def _is_git_root(root: Path) -> bool:
    """Whether ``root`` is the top directory of a git work tree. Raises ``DispositionError`` when that
    cannot be told (git refuses the directory, times out, or is missing while ``.git`` exists): a checkout
    that git cannot read must not be taken for a disposable copy, where differences are not enforced."""
    marker = (root / ".git").exists()
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True,
                              text=True, timeout=60, env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError:
        if marker:
            raise DispositionError(f"{root} holds a .git and git is not installed") from None
        return False
    except subprocess.TimeoutExpired as exc:
        raise DispositionError(f"git rev-parse timed out under {root}") from exc
    if proc.returncode == 0:
        return Path(proc.stdout.strip()).resolve() == root.resolve()
    if "not a git repository" in proc.stderr and not marker:
        return False
    detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else f"exit {proc.returncode}"
    raise DispositionError(f"git cannot say whether {root} is a checkout ({detail})")


def _git_head_bytes(root: Path, rel: str) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(root), "cat-file", "blob", f"HEAD:{rel}"], capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


def load_record(engine: Path) -> Record:
    """The record of the engine checkout at ``engine``, from its working tree. In a git checkout
    ``committed`` says whether the file is exactly what HEAD holds; an accepting entry of a record that is
    not committed does not pass (``review``). A directory that is not a git checkout is a synthetic tree."""
    engine = Path(engine)
    path = engine / RECORD_REL
    in_git = engine.is_dir() and _is_git_root(engine)
    committed: bool | None = None
    if in_git:
        status = subprocess.run(["git", "-C", str(engine), "status", "--porcelain", "--untracked-files=all",
                                 "--", RECORD_REL], capture_output=True, text=True)
        committed = status.returncode == 0 and not status.stdout.strip()
    try:
        data: bytes | None = path.read_bytes()
    except FileNotFoundError:
        data = None
    except OSError as exc:
        raise DispositionError(f"{path} cannot be read ({type(exc).__name__})") from exc

    def exists(rel: str) -> bool:
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            return False
        return _git_head_bytes(engine, rel) is not None if in_git else (engine / rel).is_file()

    return parse_record(data, source=RECORD_REL, committed=committed, exists=exists)


def review(differences: Iterable[Mapping[str, Any]], record: Record) -> list[dict[str, Any]]:
    """Each difference with its verdict: ``{"difference", "passes", "status", "reason"}``. Only an entry that
    covers the difference exactly, is well formed, says ``accept_candidate`` and comes from a committed
    record passes."""
    by_identity: dict[tuple[Any, ...], list[Any]] = {}
    for entry in record.entries:
        if isinstance(entry, dict):
            by_identity.setdefault(identity(entry), []).append(entry)
    out = []
    for difference in differences:
        verdict = {"difference": difference, "passes": False}
        candidates = by_identity.get(identity(difference), [])
        matching = [e for e in candidates if covers(e, difference)]
        if difference.get("scope") == "unidentified":
            verdict.update(status="cannot_be_compared",
                           reason="published rows without (batch, batch_index) cannot be compared; restore the "
                                  "published payload from git")
        elif not candidates:
            verdict.update(status="no_disposition", reason=f"no entry in {RECORD_REL}")
        elif not matching:
            verdict.update(status="values_do_not_match",
                           reason=f"{RECORD_REL} has an entry for this identity whose recorded change, fields "
                                  "or values are not the actual ones")
        elif len({json.dumps(e.get("disposition")) for e in matching}) > 1:
            verdict.update(status="conflicting_entries",
                           reason=f"{RECORD_REL} holds entries for exactly this difference with different "
                                  "dispositions; keep one")
        else:
            entry = matching[0]
            problem = entry_problem(entry, record.exists)
            disposition = entry.get("disposition")
            if problem:
                verdict.update(status="invalid_entry", reason=problem)
            elif disposition != ACCEPT:
                verdict.update(status=disposition, reason=DISPOSITIONS[disposition].partition(";")[0])
            elif record.committed is False:
                verdict.update(status="record_not_committed",
                               reason=f"{RECORD_REL} differs from the engine's HEAD commit; commit the reviewed "
                                      "record first")
            else:
                verdict.update(passes=True, status=ACCEPT,
                               reason=f"owner disposition, {entry.get('decision_ref')}")
        out.append(verdict)
    return out


# ---------------------------------------------------------------- printing: identities, field names, numbers

def _show(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return value if _PLAIN.match(value) else f"<text, {len(value)} characters>"
    return f"<{type(value).__name__}>"


def describe(difference: Mapping[str, Any]) -> str:
    """One line for a difference: its identity, the change, field names and numbers. Never token text."""
    scope = difference.get("scope")
    if scope == "metadata":
        return (f"{difference['block']}.{difference['model']}.{difference['field']}: "
                f"{_show(difference['reference'])} -> {_show(difference['candidate'])}")
    if scope != "row":
        return f"{difference.get('count')} published scenario(s) hold a measured value and no (batch, batch_index)"
    before = difference["reference"]["values"]
    after = (difference["candidate"] or {}).get("values")
    identity_text = f"({difference['batch']}, {difference['batch_index']}, {difference['model']})"
    if after is None:
        numbers = "; ".join(f"{name} {_show(before[name])}" for name in HEADLINE_FIELDS)
        return (f"{identity_text} {difference['change']}: published {numbers}; "
                f"{len(difference['fields'])} measured field(s) no longer there")
    numbers = "; ".join(f"{name} {_show(before[name])} -> {_show(after[name])}" for name in HEADLINE_FIELDS)
    return f"{identity_text} {difference['change']}: {numbers}; fields: {', '.join(difference['fields'])}"


def format_table(reviewed: list[dict[str, Any]], *, limit: int = MAX_TABLE_ROWS,
                 enforced: bool = True) -> list[str]:
    """The reviewed differences as lines, the ones that do not pass first, then one line per status saying
    what it means. Beyond ``limit`` differences the rest are counted. ``enforced`` False is for a caller
    that reports and does not refuse (a site directory that is not a git checkout)."""
    ordered = sorted(reviewed, key=lambda v: v["passes"])
    word = "REFUSED " if enforced else "differs "
    lines = [f"  {word if not v['passes'] else 'accepted'} [{v['status']}] {describe(v['difference'])}"
             for v in ordered[:limit]]
    if len(ordered) > limit:
        rest = ordered[limit:]
        lines.append(f"  ... and {len(rest)} more ({sum(1 for v in rest if not v['passes'])} without an "
                     "accepting disposition)")
    reasons: dict[str, str] = {}
    for verdict in ordered:
        reasons.setdefault(verdict["status"], verdict["reason"])
    return lines + [f"  [{status}] {reason}" for status, reason in reasons.items()]


def refused(reviewed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [v for v in reviewed if not v["passes"]]


def load_payload(data: bytes | str, what: str) -> dict[str, Any]:
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise DispositionError(f"{what} is not JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise DispositionError(f"{what} is not a JSON object")
    return doc


# ---------------------------------------------------------------- the reference a site directory offers

def site_reference(site: Path, rel: str = PAYLOAD_REL) -> tuple[bytes | None, bool, str]:
    """(the published payload's bytes or None, whether a difference from it is enforced, where it was read).

    In a git checkout the reference is the payload in the HEAD commit: that is what a push publishes from,
    and the working-tree copy can be the leftover of an earlier or abandoned run. When HEAD holds none, the
    file on disk is the reference. A difference from either is enforced.

    A directory that is not the root of a git checkout is a disposable copy (verify.md's temporary
    regeneration, scripts/check_frontend_boundary.py, a test): nothing can be committed or pushed from it, so
    the difference is reported and not enforced. ``results_snapshot.py check-release`` enforces it on the
    committed site."""
    site = Path(site)
    on_disk: bytes | None
    try:
        on_disk = (site / rel).read_bytes()
    except FileNotFoundError:
        on_disk = None
    except OSError as exc:
        raise DispositionError(f"{site / rel} cannot be read ({type(exc).__name__})") from exc
    if site.is_dir() and _is_git_root(site):
        head = _git_head_bytes(site, rel)
        if head is not None:
            return head, True, f"{rel} in the site's HEAD commit"
        return on_disk, True, f"{rel} on disk (the site's HEAD commit holds none)"
    return on_disk, False, f"{rel} on disk"


def review_payloads(reference: bytes | str, candidate: bytes | str | Mapping[str, Any], record: Record, *,
                    reference_name: str = "the published payload",
                    candidate_name: str = "the candidate payload") -> list[dict[str, Any]]:
    """Parse, compare and review in one step. Raises ``DispositionError`` on an unreadable payload."""
    cand = candidate if isinstance(candidate, Mapping) else load_payload(candidate, candidate_name)
    return review(scientific_differences(load_payload(reference, reference_name), cand), record)


# ---------------------------------------------------------------- the record's writer: pending entries only

RECORD_HEAD: dict[str, Any] = {
    "schema": SCHEMA,
    "what_this_is": "Differences between the published gallery payload (data/simulated_scenarios.json in the "
                    "sibling site repository) and what an export or a release would publish in its place, each "
                    "with the owner's disposition. scripts/export_frontend_simulated.py and "
                    "scripts/results_snapshot.py refuse a difference unless an entry here covers exactly it "
                    "with accept_candidate.",
    "what_it_is_not": "Not a membership rule, not a pin and not a hold on publication: a publish that changes "
                      "no published measurement and no capability label needs no entry.",
    "checked_by": "scripts/payload_dispositions.py; tests/test_payload_dispositions.py",
    "dispositions": DISPOSITIONS,
    "rule": "Only accept_candidate passes, and only with decided_by \"owner\" and a decision_ref naming the "
            "committed document that records the decision. scripts/payload_dispositions.py propose writes "
            "pending entries and nothing else; a decision is entered by hand in a reviewed commit.",
    "omitted": "No prompt, target or token text. 'values' holds numbers, booleans, counts and lengths; "
               "measurement_sha256 covers the tokens (the row hash of legacy_payload_rows.v1.json without the "
               "urgency join).",
}


def pending_entry(difference: Mapping[str, Any]) -> dict[str, Any]:
    keys = ROW_KEYS if difference["scope"] == "row" else META_KEYS
    return {**{k: difference[k] for k in keys}, "disposition": PENDING, "decided_by": None, "decision_ref": None}


def propose(reviewed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A pending entry for every difference no entry covers yet (``no_disposition`` or
    ``values_do_not_match``). Covered differences keep their entries untouched."""
    return [pending_entry(v["difference"]) for v in reviewed
            if v["status"] in ("no_disposition", "values_do_not_match")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "print the differences and their dispositions"),
                       ("propose", "print (or with --write, append) pending entries for uncovered differences")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--reference", required=True, type=Path, help="the published payload")
        p.add_argument("--candidate", required=True, type=Path, help="the payload that would replace it")
        p.add_argument("--engine", default=Path(__file__).resolve().parents[1], type=Path,
                       help="engine checkout whose record is read (default: this one)")
    sub.choices["propose"].add_argument("--write", action="store_true",
                                        help=f"append the pending entries to {RECORD_REL}")
    args = parser.parse_args(argv)
    try:
        record = load_record(args.engine)
        reviewed = review_payloads(args.reference.read_bytes(), args.candidate.read_bytes(), record,
                                   reference_name=str(args.reference), candidate_name=str(args.candidate))
    except (DispositionError, OSError) as exc:
        print(f"payload dispositions: refused, nothing written: {exc}", file=sys.stderr)
        return 2
    not_passing = refused(reviewed)
    print(f"{len(reviewed)} difference(s) from {args.reference}: {len(not_passing)} without an accepting "
          f"disposition, {len(reviewed) - len(not_passing)} accepted ({record.source})")
    for line in format_table(reviewed):
        print(line)
    if args.command == "check":
        return 1 if not_passing else 0
    new = propose(reviewed)
    if not args.write:
        print(json.dumps(new, indent=1))
        return 0
    path = args.engine / RECORD_REL
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(RECORD_HEAD, entries=[])
    entries = [*doc["entries"], *new]
    doc = {**{k: v for k, v in doc.items() if k not in ("count", "entries")}, "count": len(entries),
           "entries": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(new)} pending entr{'y' if len(new) == 1 else 'ies'} appended to {path}; a decision is entered "
          "by hand in a reviewed commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
