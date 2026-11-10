"""Shared names, hashing and guarded writes for the experiment package.

Hashing has two rules and they are never mixed:

* Canonical identity of a JSON value (protocol, task spec, token array, plan) is
  ``scripts.exploratory_methods.digest``: SHA-256 of ``json.dumps(value, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False, allow_nan=False)`` in UTF-8. This package imports that
  function; it does not copy it. ``scripts/exploratory_baseline_preflight.py`` has another ``digest`` that
  leaves ``ensure_ascii`` at its default, so the two disagree on any value holding a non-ASCII character.
  Nothing here uses the baseline module's function.
* Identity of a file (payloads, envelopes, fixtures) is the SHA-256 of its bytes.

Nothing in this module loads a model, opens a socket or reads a measurement.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from scripts.exploratory_methods import Refusal, digest, prompt_digest, require
from scripts.frontend_contract_schema import check_schema_subset

__all__ = [
    "Refusal", "require", "digest", "prompt_digest", "atomic_write_json", "sha256_file", "EXECUTION_STATES",
    "protected_root",
]

ENGINE = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ENGINE / "schemas" / "experiments"

PROTOCOL_SCHEMA = "patientwords.experiment-protocol/1"
PLAN_SCHEMA = "patientwords.experiment-plan/1"
ENVELOPE_SCHEMA = "patientwords.experiment-envelope/1"
BUNDLE_SCHEMA = "patientwords.experiment-bundle/1"
CAPABILITY_SCHEMA = "patientwords.capability-matrix/1"
COLLECTED_SCHEMA = "patientwords.experiment-collected/1"
COMPARISON_SCHEMA = "patientwords.experiment-comparison/1"
RATES_SCHEMA = "patientwords.experiment-rates/1"

# Execution state of a task or envelope. Never mixed with visibility or with the size of an effect.
EXECUTION_STATES = ("not_run", "unsupported", "unavailable", "invalid", "failed", "completed")
# One extra word, used only inside attempt histories and the collector's report: a start was journaled and no
# end was. Whether the attempt executed is unknown, so it is not one of the six states above.
UNCERTAIN = "uncertain"
PLANNED_STATES = ("ready", "unsupported", "unavailable")

# Visibility words of an evidence block. "public" and "restricted" are the two values
# scripts/results_policy.py (classify_part) assigns under docs/open_results_policy.md; that module exposes no
# constant for them. "not_published" is this package's word for a synthetic document, which is never shared.
VISIBILITIES = ("public", "restricted", "not_published")

# Weakest to strongest. A later status never follows from an earlier one.
CAPABILITY_STATUSES = (
    "unsupported", "architecture_supported", "artifact_available_identity_unknown", "artifact_available",
    "runtime_verified_offline_fixture", "parity_passed",
)

SPLITS = ("discovery", "validation", "fresh_test")
REQUIRED_VARIANTS = ("clinical", "colloquial", "normalized")
OPTIONAL_VARIANTS = ("within_register_paraphrase", "changed_fact_control")
VARIANTS = REQUIRED_VARIANTS + OPTIONAL_VARIANTS

METHOD_IDS = (
    "behavior_next_token", "logit_lens", "j_lens", "jpp", "ica_lens", "attribution_graph", "conversation_audit",
)
REPRESENTATION_TYPES = (
    "neuron", "sae_latent", "transcoder_feature", "ica_component", "attention_head", "workspace_readout",
    "graph_node",
)
PAYLOAD_KINDS = (
    "behavior_next_token/1", "lens_readout_report/1", "ica_scores/1", "conversation_ref/1",
    "attribution_graph_ref/1",
)
# Which payload kinds a method may file. The adapter modules declare the same kinds
# (tests/test_experiments_core.py compares them), so a lens readout cannot be filed as an ICA score.
METHOD_PAYLOAD_KINDS: dict[str, tuple[str, ...]] = {
    "behavior_next_token": ("behavior_next_token/1",),
    "logit_lens": ("lens_readout_report/1",),
    "j_lens": ("lens_readout_report/1",),
    "jpp": ("lens_readout_report/1",),
    "ica_lens": ("ica_scores/1",),
    "attribution_graph": ("attribution_graph_ref/1",),
    "conversation_audit": ("conversation_ref/1",),
}
# A method that reads no internal representation records this string, not null.
NOT_APPLICABLE = "not_applicable"
METHOD_REPRESENTATION: dict[str, str] = {
    "behavior_next_token": NOT_APPLICABLE,
    "logit_lens": "workspace_readout",
    "j_lens": "workspace_readout",
    "jpp": "workspace_readout",
    "ica_lens": "ica_component",
    "attribution_graph": "graph_node",
    "conversation_audit": NOT_APPLICABLE,
}
# Methods whose block must carry capture_site, layer_index_base and layers.
LAYERED_METHODS = ("logit_lens", "j_lens", "jpp", "ica_lens")

# Methods that read through a fitted artifact (a lens, a basis, a transcoder set).
FITTED_METHODS = ("j_lens", "jpp", "ica_lens", "attribution_graph")

DTYPE_BYTES = {"float16": 2, "bfloat16": 2, "float32": 4, "float64": 8}

# The one toy model the offline fixtures describe. It names no real checkpoint.
FIXTURE_BACKEND = "fixture"
FIXTURE_MODEL = {
    "study_id": "toy-model",
    "hf_id": "fixture/toy-model",
    "revision": "1111111111111111111111111111111111111111",
}

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")

# Same set as the --out rule of scripts/exploratory_methods.py.
PROTECTED_ROOTS = frozenset({"trace_out", "data", "pilot", "ops", "modes", ".github", ".claude", ".githooks", ".git"})


def integer(value: Any, lower: int = 0) -> bool:
    """A real int (bool and float refused) at or above ``lower``."""
    return type(value) is int and value >= lower


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def utc_now() -> str:
    """Wall-clock UTC, to the second. Only the run store calls this; plans and bundles hold no clock value."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    """SHA-256 of a file's bytes."""
    return sha256_bytes(Path(path).read_bytes())


def json_bytes(obj: Any) -> bytes:
    """The exact bytes every writer in this package puts on disk for ``obj``: sorted keys, two-space indent,
    UTF-8 without escapes, a final newline, NaN and infinity refused. The same value gives the same bytes."""
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def protected_root(path: Path | str) -> str | None:
    """The protected directory name found in the resolved path, or None.

    Symlinks are resolved first, so a link into ``trace_out`` is seen as ``trace_out``. The check is on path
    components anywhere in the path, as in ``scripts/exploratory_methods.py``: a scratch directory that happens
    to be named ``data`` is refused too. That is deliberate; it costs a rename and cannot write a measurement.
    """
    hits = sorted(PROTECTED_ROOTS.intersection(Path(path).resolve().parts))
    return hits[0] if hits else None


def git_checkout_of(path: Path | str) -> Path | None:
    """The nearest ancestor of the resolved path that holds a ``.git`` entry (directory or file), or None."""
    resolved = Path(path).resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            return parent
    return None


def check_output_path(path: Path | str, allow_roots: Iterable[Path | str] = ()) -> Path:
    """Refuse a write target under a protected root or inside a Git checkout; return the resolved path.

    ``allow_roots`` lifts the Git-checkout rule for paths under the named directories. It never lifts the
    protected-root rule: ``--allow-root`` cannot make ``trace_out`` or ``data`` writable.
    """
    resolved = Path(path).resolve()
    hit = protected_root(resolved)
    require(hit is None, "protected_root", f"{resolved} is under the protected root {hit!r}")
    checkout = git_checkout_of(resolved)
    if checkout is not None:
        allowed = any(resolved == Path(root).resolve() or Path(root).resolve() in resolved.parents
                      for root in allow_roots)
        require(allowed, "git_checkout",
                f"{resolved} is inside the Git checkout {checkout}; pass --allow-root for a directory that holds it")
    return resolved


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Write through a temporary file in the same directory, fsync it, then ``os.replace`` it into place.

    A reader sees the old file or the new file, never a partial one. The directory entry is fsynced where the
    platform allows it. This function checks no path rule; callers go through ``write_json`` or the run store.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except BaseException:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise
    _fsync_directory(target.parent)


def _fsync_directory(directory: Path) -> None:
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def exclusive_write_bytes(path: Path | str, data: bytes) -> None:
    """Create ``path`` holding ``data``; raise ``FileExistsError`` when the name is already taken.

    The bytes go to a temporary file in the same directory, are fsynced, and the name is then made with
    ``os.link``, which never replaces an existing entry. Of two processes that write the same name, exactly one
    succeeds, and a reader never sees a partial file. Where the filesystem has no hard links the file is
    created with ``O_EXCL`` instead: still exclusive, and a reader may then see it while it is being written.
    This function checks no path rule; the run store calls it for attempt envelopes.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_name, target)
        except FileExistsError:
            raise
        except OSError:
            direct = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(direct, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    _fsync_directory(target.parent)


def atomic_write_json(path: Path | str, obj: Any) -> None:
    """``atomic_write_bytes`` of ``json_bytes(obj)``."""
    atomic_write_bytes(path, json_bytes(obj))


def write_json(path: Path | str, obj: Any, allow_roots: Iterable[Path | str] = ()) -> Path:
    """The guarded writer every public output goes through: path rules first, then an atomic write."""
    resolved = check_output_path(path, allow_roots)
    atomic_write_json(resolved, obj)
    return resolved


@lru_cache(maxsize=16)
def load_schema(name: str) -> dict[str, Any]:
    """``schemas/experiments/<name>.v1.schema.json``, written in the subset ``check_schema_subset`` accepts."""
    return read_json(SCHEMA_DIR / f"{name}.v1.schema.json")


def structural_errors(doc: Any, name: str) -> list[str]:
    """Structural errors of ``doc`` against the named schema, as ``path: message`` strings.

    The schema files are executed here, not only kept as documentation. They state types, required keys and
    closed objects. Vocabularies and cross-field rules are enforced by the validators in this package.
    """
    errors: list[str] = []
    check_schema_subset(lambda _artifact, where, why: errors.append(f"{where}: {why}"), name, doc,
                        load_schema(name))
    return errors


def require_structure(doc: Any, name: str, code: str = "invalid_input") -> None:
    errors = structural_errors(doc, name)
    require(not errors, code, f"{name} schema: " + "; ".join(errors[:5])
            + (f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""))
