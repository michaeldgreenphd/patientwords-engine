"""Adapter registry for the experiment package.

An adapter turns one planned task into one typed payload. Each adapter module exposes a module-level ``ADAPTER``
object that satisfies the ``Adapter`` protocol below. Adapters in this milestone run on offline fixtures only.

Modules are imported on first use, by name, so that an optional adapter that is not in the checkout is
reported as a state and never as an import error.
"""
from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any, Iterator, Protocol, runtime_checkable

from scripts.experiments.common import HEX64, METHOD_IDS, METHOD_PAYLOAD_KINDS, Refusal, require


@runtime_checkable
class Adapter(Protocol):
    """What the planner, the run store and the envelope validator ask of an adapter."""

    method_ids: tuple[str, ...]
    payload_kinds: tuple[str, ...]

    def capabilities(self) -> list[dict]:
        """What this adapter can do offline, as capability-matrix row dicts (fixture backend only)."""

    def preflight(self, task: dict, context: dict) -> tuple[str, str | None]:
        """``(planned_state, reason)`` for one task: ``("ready", None)`` or ``("unavailable", why)``."""

    def execute_fixture(self, task: dict, context: dict) -> dict:
        """The typed payload for one task, from offline fixtures. An adapter that cannot do this raises
        ``Refusal("unsupported_operation", ...)``."""

    def validate_payload(self, payload: dict, task: dict, context: dict) -> None:
        """Raise ``Refusal`` when the payload does not match the task (shape, hashes, row alignment)."""


# ---------------------------------------------------------------------------------------------------------
# OPTIONAL HOOK, not part of the ``Adapter`` protocol above:
#
#     def input_identity(self, task: dict, context: dict) -> str | None
#
# It returns the SHA-256 (64 lowercase hex digits) that identifies every input of this task which the task spec
# does not cover: the bytes of the fixture files, a basis manifest, an activation dataset. Build it with
# ``scripts.experiments.common.digest`` over a mapping of input name to file SHA-256. Return None when those
# inputs cannot be read now. The method must not execute the task and must not raise for an absent file.
#
# The run store records the value in the envelope as ``environment.input_identity_sha256`` and reuses a
# completed envelope only when the value computed now equals the recorded one. An adapter without the hook has
# a null value recorded (listed in ``not_recorded``) and its completed envelopes are reused on the payload
# hash and the adapter source hashes alone, as before the hook existed.
# ---------------------------------------------------------------------------------------------------------
#
# OPTIONAL ATTRIBUTE: ``source_files``, a tuple of paths of further source files the adapter's payloads depend
# on (modules it imports for its arithmetic). The store hashes them into ``environment.source_files_sha256``
# beside the adapter module itself, and a changed hash stops reuse.
# ---------------------------------------------------------------------------------------------------------
INPUT_IDENTITY_HOOK = "input_identity"


def input_identity(adapter: Any, task: dict, context: dict) -> tuple[bool, str | None]:
    """``(implemented, digest)`` for one task.

    ``implemented`` is False when the adapter has no ``input_identity`` method; the digest is then None and
    means "not recorded". With the hook, the digest is its return value, or None when the hook returns None or
    raises: the inputs cannot be identified now, which never equals a recorded identity. A return value that
    is neither None nor 64 hex digits refuses ``adapter_contract``.
    """
    hook = getattr(adapter, INPUT_IDENTITY_HOOK, None)
    if not callable(hook):
        return False, None
    try:
        value = hook(task, context)
    except Exception:  # unreadable inputs: no identity now; preflight or execution reports the cause
        return True, None
    require(value is None or (isinstance(value, str) and bool(HEX64.fullmatch(value))), "adapter_contract",
            f"{type(adapter).__module__}.{INPUT_IDENTITY_HOOK} must return 64 hex digits or None")
    return True, value


# ---------------------------------------------------------------------------------------------------------
# EXTENSION POINT. Method id -> module path. To add an adapter, add its module under this package and one line
# here; nothing else in the planner or the store names an adapter module.
#
# "ica_lens" is listed although scripts/experiments/adapters/ica.py is written by a later task. While that file
# is absent, adapter_status("ica_lens") is ("absent", "adapter module not present: ...") and the planner marks
# ica_lens tasks unavailable with that reason.
#
# j_lens, jpp, attribution_graph and conversation_audit have no line: they have no executable adapter in this
# milestone. The planner states their tasks from the capability matrix alone.
# ---------------------------------------------------------------------------------------------------------
ADAPTER_MODULES: dict[str, str] = {
    "behavior_next_token": "scripts.experiments.adapters.behavior_fixture",
    "logit_lens": "scripts.experiments.adapters.readout_exploratory",
    "ica_lens": "scripts.experiments.adapters.ica",
}

ABSENT_REASON = "adapter module not present"
NO_ADAPTER_REASON = "no executable adapter for this method in this milestone"


def _import(module_path: str) -> tuple[Any | None, str | None]:
    """``(module, None)`` or ``(None, reason)``. Only a missing module is turned into a reason.

    A module that exists and fails for another reason (a syntax error, a bug at import) raises: that is a
    defect to fix, not a state to report.
    """
    try:
        return importlib.import_module(module_path), None
    except ModuleNotFoundError as exc:
        if exc.name == module_path:
            return None, f"{ABSENT_REASON}: {module_path}"
        if exc.name and not module_path.startswith(exc.name + "."):
            return None, f"adapter dependency not importable: {exc.name} (needed by {module_path})"
        raise


def load_adapter(method_id: str, registry: Mapping[str, str] | None = None) -> tuple[Adapter | None, str | None]:
    """``(adapter, None)`` when the method's adapter is importable, else ``(None, reason)``."""
    require(method_id in METHOD_IDS, "unknown_method", f"{method_id!r} is not one of {list(METHOD_IDS)}")
    modules = ADAPTER_MODULES if registry is None else registry
    module_path = modules.get(method_id)
    if module_path is None:
        return None, NO_ADAPTER_REASON
    module, reason = _import(module_path)
    if module is None:
        return None, reason
    adapter = getattr(module, "ADAPTER", None)
    require(adapter is not None and isinstance(adapter, Adapter), "adapter_contract",
            f"{module_path} must expose ADAPTER with method_ids, payload_kinds and the four adapter methods")
    require(method_id in adapter.method_ids, "adapter_contract",
            f"{module_path} does not declare method {method_id}")
    for declared in adapter.method_ids:
        require(set(adapter.payload_kinds) <= set(METHOD_PAYLOAD_KINDS.get(declared, ())), "adapter_contract",
                f"{module_path} declares payload kinds {adapter.payload_kinds} outside those of {declared}")
    return adapter, None


def adapter_status(method_id: str, registry: Mapping[str, str] | None = None) -> tuple[str, str | None]:
    """``("present", None)``, ``("absent", reason)`` or ``("none", reason)`` for one method.

    ``absent``: the registry names a module and it cannot be imported. ``none``: the registry has no module.
    """
    adapter, reason = load_adapter(method_id, registry)
    if adapter is not None:
        return "present", None
    return ("none" if reason == NO_ADAPTER_REASON else "absent"), reason


class _LazyAdapters(Mapping[str, Adapter]):
    """``ADAPTERS[method_id]`` imports the adapter on first use. A method without an importable adapter is not
    a key: ``ADAPTERS.get("ica_lens")`` is None while the ICA module is absent, and iteration skips it."""

    def __getitem__(self, method_id: str) -> Adapter:
        try:
            adapter, _reason = load_adapter(method_id)
        except Refusal as exc:
            if exc.code == "unknown_method":
                raise KeyError(method_id) from exc
            raise
        if adapter is None:
            raise KeyError(method_id)
        return adapter

    def __iter__(self) -> Iterator[str]:
        return (method for method in ADAPTER_MODULES if adapter_status(method)[0] == "present")

    def __len__(self) -> int:
        return sum(1 for _ in self)


ADAPTERS: Mapping[str, Adapter] = _LazyAdapters()
