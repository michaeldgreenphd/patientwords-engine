"""Capability matrix: what is known about each model revision x method x backend x artifact.

The matrix is data (``data/experiments/capability_matrix.v1.json``). Each row states one status from
``CAPABILITY_STATUSES`` with the evidence for it. The statuses are ordered and are never merged: "the
architecture is supported" and "this combination passed a recorded parity audit" are different rows.

``lookup`` never raises for an absent combination. It returns a synthesized ``unsupported`` answer that says no
row exists, so the planner shows the task with that reason. It does not drop the task.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.experiments.common import (
    CAPABILITY_SCHEMA, CAPABILITY_STATUSES, DATE, DTYPE_BYTES, ENGINE, FIXTURE_BACKEND, HEX40, HEX64, METHOD_IDS,
    Refusal, read_json, require, require_structure, text,
)

MATRIX_PATH = ENGINE / "data" / "experiments" / "capability_matrix.v1.json"
FIXTURE_CEILING = "runtime_verified_offline_fixture"


def status_rank(status: str) -> int:
    """Position of ``status`` in the weakest-to-strongest order."""
    require(status in CAPABILITY_STATUSES, "capability_status", f"unknown capability status {status!r}")
    return CAPABILITY_STATUSES.index(status)


def row_key(row: Mapping[str, Any]) -> tuple[str, str | None, str, str, str | None, str | None]:
    artifact = row.get("artifact") or {}
    return (row["model"]["hf_id"], row["model"].get("revision"), row["method"], row["backend"],
            row.get("dtype"), artifact.get("id"))


def _check_row(row: Any, where: str) -> None:
    require(isinstance(row, dict), "invalid_input", f"{where}: a row must be an object")
    model = row.get("model")
    require(isinstance(model, dict) and text(model.get("hf_id")), "capability_row", f"{where}: model.hf_id")
    require(model.get("study_id") is None or text(model["study_id"]), "capability_row", f"{where}: model.study_id")
    revision = model.get("revision")
    require(revision is None or bool(HEX40.fullmatch(str(revision))), "capability_row",
            f"{where}: model.revision must be a 40-hex commit or null when no revision is recorded")
    require(row.get("method") in METHOD_IDS, "unknown_method", f"{where}: method {row.get('method')!r}")
    require(text(row.get("backend")), "capability_row", f"{where}: backend")
    require(row.get("dtype") is None or row["dtype"] in DTYPE_BYTES, "capability_row", f"{where}: dtype")
    require(row.get("status") in CAPABILITY_STATUSES, "capability_status",
            f"{where}: status must be one of {list(CAPABILITY_STATUSES)}")
    require(text(row.get("status_note")), "capability_row", f"{where}: status_note is required")
    evidence = row.get("evidence")
    require(isinstance(evidence, list) and bool(evidence) and all(
        isinstance(e, dict) and text(e.get("source")) and bool(DATE.fullmatch(str(e.get("date", ""))))
        for e in evidence), "capability_evidence",
        f"{where}: evidence must be a non-empty list of {{source, date YYYY-MM-DD}}")
    artifact = row.get("artifact")
    if artifact is not None:
        require(isinstance(artifact, dict) and text(artifact.get("id")), "capability_row", f"{where}: artifact.id")
        sha = artifact.get("sha256")
        require(sha is None or bool(HEX64.fullmatch(str(sha))), "capability_row", f"{where}: artifact.sha256")
    if row["status"] == "parity_passed":
        record = row.get("parity_record")
        require(isinstance(record, dict) and text(record.get("source")) and text(record.get("scope"))
                and bool(DATE.fullmatch(str(record.get("date", "")))), "parity_without_record",
                f"{where}: parity_passed needs parity_record {{source, date, scope}}")


def validate_matrix(doc: Any) -> dict[str, Any]:
    """Validate a capability matrix document and return it. Refuses duplicate keys and uncited statuses."""
    try:
        require(isinstance(doc, dict) and doc.get("schema_version") == CAPABILITY_SCHEMA, "schema_version",
                f"Expected {CAPABILITY_SCHEMA}")
        require_structure(doc, "capability_matrix")
        require(doc.get("status_order") == list(CAPABILITY_STATUSES), "capability_status",
                "status_order must repeat the six statuses, weakest first")
        seen: set[tuple[Any, ...]] = set()
        for number, row in enumerate(doc["rows"]):
            where = f"rows[{number}]"
            _check_row(row, where)
            key = row_key(row)
            require(key not in seen, "duplicate_row", f"{where}: a second row for {key}")
            seen.add(key)
        return doc
    except Refusal:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Refusal("invalid_input", f"{type(exc).__name__}: {exc}") from exc


def load_matrix(path: Path | str | None = None) -> dict[str, Any]:
    """The validated matrix at ``path`` (default: the committed matrix)."""
    return validate_matrix(read_json(Path(path) if path is not None else MATRIX_PATH))


def check_adapter_rows(rows: Iterable[Any], module: str) -> list[dict[str, Any]]:
    """Rows an adapter declares for itself. An adapter may speak only for the offline fixture backend and may
    not claim more than ``runtime_verified_offline_fixture``; a real-model status belongs in the matrix file,
    where a reviewer reads its evidence."""
    checked = []
    for number, row in enumerate(rows):
        where = f"{module}.capabilities()[{number}]"
        _check_row(row, where)
        require(row["backend"] == FIXTURE_BACKEND and status_rank(row["status"]) <= status_rank(FIXTURE_CEILING),
                "adapter_capability_scope",
                f"{where}: an adapter may declare only fixture-backend rows up to {FIXTURE_CEILING}")
        checked.append({**row, "declared_by": module})
    return checked


def merge_rows(matrix: Mapping[str, Any], adapter_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Matrix rows, with each adapter-declared row replacing the matrix row of the same key."""
    merged = {row_key(row): dict(row) for row in matrix["rows"]}
    for row in adapter_rows:
        merged[row_key(row)] = dict(row)
    return list(merged.values())


def evidence_text(row: Mapping[str, Any]) -> str:
    return "; ".join(f"{e['source']} ({e['date']})" for e in row.get("evidence", []))


def _model_identity(model_revision: Mapping[str, Any] | str) -> tuple[str, str | None]:
    if isinstance(model_revision, str):
        hf_id, _, revision = model_revision.partition("@")
        return hf_id, (revision or None)
    return model_revision["hf_id"], model_revision.get("revision")


def lookup(model_revision: Mapping[str, Any] | str, method: str, backend: str, artifact: str | None = None, *,
           dtype: str | None = None, matrix: Mapping[str, Any] | None = None,
           rows: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """The capability answer for one model revision x method x backend (x artifact).

    ``model_revision`` is a mapping with ``hf_id`` and ``revision``, or the string ``"<hf_id>@<revision>"``.
    ``artifact`` is an artifact id or SHA-256. A row whose ``dtype`` is null applies to every dtype.
    Rows at exactly the asked revision are used first. If there is none, rows whose ``model.revision`` is null
    are used: such a row describes a route that records no revision (a hosted service, an audit run before
    pinning), and the answer then carries ``revision_match: "row_revision_not_recorded"``.

    Selection, in order: rows naming that artifact; else rows with no artifact; else, when no artifact was
    asked for, every row of the key. Where more than one row remains, the weakest status is returned, so an
    ambiguous question never gets the stronger answer. No row gives ``status: unsupported`` with
    ``matched: false`` and a note that says so.
    """
    require(method in METHOD_IDS, "unknown_method", f"{method!r} is not one of {list(METHOD_IDS)}")
    hf_id, revision = _model_identity(model_revision)
    pool = list(rows) if rows is not None else list((matrix if matrix is not None else load_matrix())["rows"])
    keyed = [row for row in pool
             if row["model"]["hf_id"] == hf_id and row["method"] == method and row["backend"] == backend
             and (row.get("dtype") is None or dtype is None or row["dtype"] == dtype)]
    exact = [row for row in keyed if row["model"].get("revision") == revision]
    candidates = exact or [row for row in keyed if row["model"].get("revision") is None]
    revision_match = "exact" if exact else "row_revision_not_recorded"
    generic = [row for row in candidates if row.get("artifact") is None]
    if artifact is not None:
        named = [row for row in candidates if row.get("artifact")
                 and artifact in (row["artifact"].get("id"), row["artifact"].get("sha256"))]
        chosen = named or generic
    else:
        chosen = generic or candidates
    if not chosen:
        what = f"{hf_id}@{revision} x {method} x {backend}" + (f" x {artifact}" if artifact else "")
        return {"status": "unsupported", "matched": False, "evidence": [], "evidence_text": "no capability row",
                "status_note": f"no capability row for {what}", "ambiguous": False, "artifact": None,
                "declared_by": None, "revision_match": None}
    weakest = min(chosen, key=lambda row: (status_rank(row["status"]), str(row_key(row))))
    return {"status": weakest["status"], "matched": True, "evidence": list(weakest["evidence"]),
            "evidence_text": evidence_text(weakest), "status_note": weakest["status_note"],
            "ambiguous": len(chosen) > 1, "artifact": weakest.get("artifact"),
            "declared_by": weakest.get("declared_by"), "revision_match": revision_match}


def rows_for_model(matrix: Mapping[str, Any], model: str | None = None) -> list[dict[str, Any]]:
    """Rows whose study id or Hugging Face id equals ``model``; every row when ``model`` is None."""
    return [dict(row) for row in matrix["rows"]
            if model is None or model in (row["model"].get("study_id"), row["model"]["hf_id"])]
