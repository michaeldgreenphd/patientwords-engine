"""Open-results policy: one place that decides what a trace_out summary part may be used for.

The publication hold of 2026-10-09 answered one question with one boolean ("may this part be read?") and so tied
together things that are independent. This module keeps them apart. For every ``trace_out/<stem>[__<suffix>]/
batch_summary*.json`` part it reports six separate facts:

1. ``execution_state``   - what the run recorded about finishing: completed, partial, empty, or not recorded.
2. ``artifact_integrity`` - whether the bytes are readable, well-formed and equal to any sha256 recorded for them.
3. ``evidence_class``    - what kind of evidence it is (registered cohort, post-registration exploratory model,
   hand-authored exploratory example). Declared metadata in data/results_policy/policy.v1.json, never a ban.
4. ``clinical_review``   - the review status of its stimuli. Pending stays visible as pending.
5. ``visibility``        - public, or restricted with a named reason (integrity failure, redistribution limit).
   The Tier B seal is a row-level restriction: ``row_restriction`` asks scripts/tierb_split.py per row.
6. ``analysis``          - for each named membership rule, whether the part may enter that analysis, and why not.

A result does not have to be confirmatory, reviewed, significant or favourable to be shared. It has to be intact
and unrestricted. Joining a statistic is a different decision, taken by a membership rule:

* ``study-interim/1``    - the rule every collector applied from 2026-10-09: every stimulus family except the
  hand-authored sets (each collector then keeps the families it analyses), the three 2026-10-09
  post-registration models excluded, CPU-logits parts read only when the pinned manifest
  (data/publication_release/logits_parts.json) lists their sha256. It is the default, so the published statistics
  keep their inputs until a new versioned snapshot is cut (scripts/results_snapshot.py).
* ``exploratory-open/1`` - every intact part of every declared model cohort, on the same stimulus families. A
  separately declared analysis with its own multiple-testing family; its outputs go to their own files.
* ``public-display/1``   - everything shareable. The results catalogue (scripts/export_results_catalogue.py)
  reads with this rule, so new parts become visible without anyone approving them one by one.

A part that is absent from a manifest is not defective: it is only outside the membership that pins that
manifest. A part whose bytes differ from a recorded sha256 (the pin or the ledger) is refused by every
membership, the default one included, so a modified file cannot stand in for the version that was recorded.
What the ledger cannot show is a change made before a part was first recorded; git history is the record
for that. A model that no cohort declares is listed in the catalogue and enters no analysis until it is
declared: a new model cannot join a statistic by landing. Hashes are recorded automatically in an append-only ledger
(data/results_policy/part_ledger.v1.json, written by the catalogue exporter); a recorded hash is never rewritten.

``Gate`` keeps the interface collectors already use (``admit``, ``held``, ``report``). A missing or unknown
``backend`` and a missing manifest still raise ``ReleaseError``: pooling parts the rule could not evaluate, or
dropping every logits row, would both be silent changes. Every skip is counted and printed, never silent.
scripts/publication_hold.py remains as the import path older callers use; it holds no rule of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from scripts import tierb_split as _tierb_split
except ImportError:  # run as a script from scripts/
    import tierb_split as _tierb_split

# The seal's own error type and exit helper, re-exported so a caller catches the class this module raises.
# scripts/ modules load under two names (``scripts.x`` and ``x``); catching ``tierb_split.SealError`` imported
# the other way would miss the exception (found by tests/test_results_catalogue.py, 2026-11-10).
SealError = _tierb_split.SealError
seal_config_error = _tierb_split.seal_config_error

ENGINE = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("data") / "results_policy" / "policy.v1.json"
LEDGER_PATH = Path("data") / "results_policy" / "part_ledger.v1.json"
RELEASE_MANIFEST = Path("data") / "publication_release" / "logits_parts.json"
POLICY_SCHEMA = "patientwords.results-policy/1"
LEDGER_SCHEMA = "patientwords.part-ledger/1"
MANIFEST_SCHEMA = "logits_release/1"

STUDY_INTERIM = "study-interim/1"
EXPLORATORY_OPEN = "exploratory-open/1"
PUBLIC_DISPLAY = "public-display/1"

BACKENDS_WITHOUT_MANIFEST = ("hosted", "activation_patch")
KNOWN_BACKENDS = BACKENDS_WITHOUT_MANIFEST + ("logits",)
# Suffixes after ``__`` that name an instrument run, not a model's behavioural summary.
INSTRUMENT_PREFIXES = ("jlens_", "loglens_", "jsteer_")
INSTRUMENT_NAMES = ("patch", "context", "lenspairs")

EXECUTION_STATES = ("completed", "partial", "empty", "completion_not_recorded", "unreadable")
INTEGRITY_STATES = ("recorded_match", "unrecorded", "changed_since_recorded", "malformed", "unreadable")
# Integrity states under which a part is never read, for display or for any analysis.
INTEGRITY_FAILURES = ("changed_since_recorded", "malformed", "unreadable")


class ReleaseError(RuntimeError):
    """The policy, a manifest or a part's own metadata is missing or malformed, so no sound decision exists."""


class PolicyError(ReleaseError):
    """The policy file itself is missing, malformed or names an unknown membership."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_dir_parts(run_dir: str) -> tuple[str, str | None]:
    """(stem, suffix) of a ``<stem>[__<suffix>]`` run directory; suffix is None for a bare stem."""
    stem, sep, suffix = run_dir.partition("__")
    return stem, (suffix if sep else None)


def run_dir_model(run_dir: str) -> str | None:
    """The suffix after ``__`` (a model id, or an instrument suffix such as ``jlens_gemma-2-2b`` or ``patch``),
    or None for a bare ``<stem>`` (gemma-2-2b's hosted traces)."""
    return run_dir_parts(run_dir)[1]


def instrument_of(suffix: str | None) -> str | None:
    """The instrument a run-directory suffix names (``jlens``, ``patch``, ...), or None for a model suffix.
    A suffix can have several ``__`` segments (``lenspairs__jlens_gemma-2-2b``); the last segment that names
    an instrument decides, so such a directory is never read as a model called by its whole suffix."""
    if not suffix:
        return None
    for segment in reversed(suffix.split("__")):
        for prefix in INSTRUMENT_PREFIXES:
            if segment.startswith(prefix):
                return prefix.rstrip("_")
        if segment in INSTRUMENT_NAMES:
            return segment
    return None


# ---------------------------------------------------------------- the policy file

@dataclass(frozen=True)
class Policy:
    """The parsed policy document. Read-only; build with ``load_policy``."""

    doc: Mapping[str, Any]
    path: Path

    @property
    def version(self) -> str:
        return self.doc["policy_version"]

    @property
    def default_membership(self) -> str:
        return self.doc["default_membership"]

    def cohort_of(self, model: str | None) -> str | None:
        """The model cohort that declares ``model``, or None for an id no cohort names."""
        for name, cohort in self.doc["model_cohorts"].items():
            if model in cohort["models"]:
                return name
        return None

    def cohort_models(self, cohort: str) -> frozenset[str]:
        return frozenset(self.doc["model_cohorts"][cohort]["models"])

    def membership(self, membership: str) -> Mapping[str, Any]:
        try:
            return self.doc["memberships"][membership]
        except KeyError:
            raise PolicyError(f"{self.path}: unknown membership {membership!r}; known: "
                              f"{sorted(self.doc['memberships'])}") from None

    def excluded_models(self, membership: str) -> frozenset[str]:
        """Model ids whose cohort the membership excludes."""
        cohorts = self.membership(membership)["exclude_model_cohorts"]
        return frozenset(m for c in cohorts for m in self.cohort_models(c))

    def stimulus_class(self, stem: str) -> str:
        """The name of the stimulus class a run-directory stem belongs to; ``unclassified`` when none matches."""
        for name, entry in self.doc["stimulus_classes"].items():
            match = entry.get("match") if name != "_default" else None
            if not match:
                continue
            if "stem_prefix" in match and stem.startswith(match["stem_prefix"]):
                return name
            if "stem_regex" in match and re.fullmatch(match["stem_regex"], stem):
                return name
        return "unclassified"

    def stimulus_entry(self, stimulus_class: str) -> Mapping[str, Any]:
        classes = self.doc["stimulus_classes"]
        return classes.get(stimulus_class, classes["_default"])

    def evidence_class(self, stimulus_class: str, model: str | None) -> str:
        """The stimulus class decides when it declares a class; otherwise the model's cohort does."""
        declared = self.stimulus_entry(stimulus_class).get("evidence_class")
        if declared:
            return declared
        if stimulus_class == "unclassified":
            return "unclassified"                # a model's cohort says nothing about an undeclared family
        cohort = self.cohort_of(model)
        return self.doc["model_cohorts"][cohort]["evidence_class"] if cohort else "unclassified"


def _validate_policy(doc: Any, path: Path) -> None:
    def bad(why: str) -> PolicyError:
        return PolicyError(f"{path} is not a valid {POLICY_SCHEMA} policy: {why}")

    if not isinstance(doc, dict) or doc.get("schema") != POLICY_SCHEMA:
        raise bad("wrong or missing 'schema'")
    for key in ("policy_version", "model_cohorts", "stimulus_classes", "memberships", "default_membership",
                "restrictions"):
        if key not in doc:
            raise bad(f"missing {key!r}")
    for key in ("model_cohorts", "stimulus_classes", "memberships", "restrictions"):
        if not isinstance(doc[key], dict) or not all(isinstance(v, dict) for v in doc[key].values()):
            raise bad(f"{key!r} must be an object of objects")
    pin = doc.get("analysis_pin")
    if pin is not None and (not isinstance(pin, dict) or type(pin.get("auto_advance")) is not bool):
        raise bad("analysis_pin.auto_advance must be the JSON boolean true or false")
    seen: dict[str, str] = {}
    for name, cohort in doc["model_cohorts"].items():
        if not isinstance(cohort.get("models"), list) or not isinstance(cohort.get("evidence_class"), str):
            raise bad(f"cohort {name!r} needs 'models' and 'evidence_class'")
        for model in cohort["models"]:
            if model in seen:
                raise bad(f"model {model!r} is in cohorts {seen[model]!r} and {name!r}")
            seen[model] = name
    if "_default" not in doc["stimulus_classes"]:
        raise bad("stimulus_classes needs a '_default' entry")
    for name, entry in doc["stimulus_classes"].items():
        if not isinstance(entry.get("clinical_review"), str) or type(entry.get("rows_exported")) is not bool:
            raise bad(f"stimulus class {name!r} needs 'clinical_review' and a boolean 'rows_exported'")
        restriction = entry.get("restriction")
        if restriction is not None and restriction not in doc["restrictions"]:
            raise bad(f"stimulus class {name!r} names unknown restriction {restriction!r}")
    for name, rule in doc["memberships"].items():
        if rule.get("purpose") not in ("analysis", "display"):
            raise bad(f"membership {name!r} needs purpose 'analysis' or 'display'")
        for key in ("exclude_stimulus_classes", "exclude_model_cohorts"):
            if not isinstance(rule.get(key), list):
                raise bad(f"membership {name!r} must state {key!r} as a list (empty when it excludes nothing)")
        for cls in rule["exclude_stimulus_classes"]:
            if cls not in doc["stimulus_classes"]:
                raise bad(f"membership {name!r} excludes unknown stimulus class {cls!r}")
        for cohort in rule["exclude_model_cohorts"]:
            if cohort not in doc["model_cohorts"]:
                raise bad(f"membership {name!r} excludes unknown cohort {cohort!r}")
        if "logits_manifest" not in rule:
            raise bad(f"membership {name!r} must state 'logits_manifest' (a path or null)")
    if doc["default_membership"] not in doc["memberships"]:
        raise bad("default_membership is not a declared membership")
    for name, restriction in doc["restrictions"].items():
        for key in ("scope", "decided_by", "responsible_role", "release_condition"):
            if not isinstance(restriction.get(key), str) or not restriction[key]:
                raise bad(f"restriction {name!r} needs a non-empty {key!r}: a restriction without a reason, a "
                          "responsible role and a release condition is a hold, and this policy has none")


@lru_cache(maxsize=16)
def _load_policy(path: str, mtime_ns: int | None, size: int | None) -> Policy:
    """Cached on the file's modification time and size, so a policy rewritten during a process is re-read."""
    file = Path(path)
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PolicyError(f"{file} is missing: nothing can be classified without the results policy") from None
    except (OSError, ValueError) as exc:
        raise PolicyError(f"{file} is unreadable: {exc}") from None
    _validate_policy(doc, file)
    return Policy(doc=doc, path=file)


POLICY_ENV = "PW_RESULTS_POLICY"
_OVERRIDE_ANNOUNCED: set[str] = set()


def load_policy(path: Path | str | None = None) -> Policy:
    """The policy at ``path``, else at ``$PW_RESULTS_POLICY``, else this repository's own (resolved from this
    file, like tierb_split's seal inputs, so a collector run from another working directory or over a synthetic
    root applies the same rules).

    The environment variable exists for offline previews and tests of a candidate policy. Whenever it decides
    which file is read, one line naming that file goes to stderr, once per process: every caller passes
    through here (``publication_hold`` evaluates its compatibility names at import), so no collector can read
    a candidate policy without saying so. ``Gate.describe`` names the file as well. To read the committed
    policy whatever the environment says, pass its path: ``load_policy(ENGINE / POLICY_PATH)``."""
    if path is None:
        override = os.environ.get(POLICY_ENV)
        if override:
            if override not in _OVERRIDE_ANNOUNCED:
                _OVERRIDE_ANNOUNCED.add(override)
                print(f"results policy: {POLICY_ENV} is set; reading {override} instead of the committed "
                      f"{POLICY_PATH.as_posix()}", file=sys.stderr)
            path = override
        else:
            path = ENGINE / POLICY_PATH
    file = Path(path)
    try:
        stat = file.stat()
        identity: tuple[int | None, int | None] = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        identity = (None, None)
    return _load_policy(str(file), *identity)


# ---------------------------------------------------------------- recorded hashes: manifest and ledger

def load_manifest(root: Path | str, rel: Path | str = RELEASE_MANIFEST) -> dict[str, str]:
    """{repo-relative part path: sha256} from a ``logits_release/1`` manifest under ``root``."""
    path = Path(root) / rel
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReleaseError(f"{path} is missing: this membership pins its logits parts to that manifest, so "
                           "they cannot be read without it") from None
    except (OSError, ValueError) as exc:
        raise ReleaseError(f"{path} is unreadable: {exc}") from None
    if not isinstance(doc, dict) or doc.get("schema") != MANIFEST_SCHEMA:
        raise ReleaseError(f"{path} is not a {MANIFEST_SCHEMA} manifest with a {{path: sha256}} 'parts' map")
    parts = doc.get("parts")
    if not isinstance(parts, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and len(v) == 64 for k, v in parts.items()):
        raise ReleaseError(f"{path} is not a {MANIFEST_SCHEMA} manifest with a {{path: sha256}} 'parts' map")
    return parts


def load_ledger(root: Path | str) -> dict[str, str]:
    """{repo-relative part path: first recorded sha256}. An absent ledger records nothing, and that is not an
    error: the ledger is a reproducibility record, not a gate a part must pass through to be read."""
    path = Path(root) / LEDGER_PATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise ReleaseError(f"{path} is unreadable: {exc}") from None
    parts = doc.get("parts") if isinstance(doc, dict) else None
    if doc.get("schema") != LEDGER_SCHEMA or not isinstance(parts, dict) or not all(
            isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("sha256"), str)
            and len(v["sha256"]) == 64 for k, v in parts.items()):
        raise ReleaseError(f"{path} is not a {LEDGER_SCHEMA} ledger with a {{path: {{sha256, ...}}}} 'parts' map")
    return {k: v["sha256"] for k, v in parts.items()}


def record_parts(root: Path | str, hashes: Mapping[str, str], *, recorded_utc: str,
                 recorded_at_commit: str | None) -> dict[str, list[str]]:
    """Append first-seen part hashes to the ledger under ``root``. A path already recorded keeps its first
    hash whatever is passed: the return value lists ``added`` paths and ``conflicts`` (recorded hash differs).
    Nothing is written when there is nothing to add."""
    path = Path(root) / LEDGER_PATH
    if path.exists():
        load_ledger(root)                                   # refuse to extend a malformed ledger
        doc = json.loads(path.read_text(encoding="utf-8"))
    else:
        doc = {"schema": LEDGER_SCHEMA,
               "rule": "append-only: the first sha256 recorded for a part is never rewritten; a part whose "
                       "bytes later differ is refused by scripts/results_policy.py",
               "parts": {}}
    added, conflicts = [], []
    for rel in sorted(hashes):
        known = doc["parts"].get(rel)
        if known is None:
            doc["parts"][rel] = {"sha256": hashes[rel], "first_recorded_utc": recorded_utc,
                                 "first_recorded_at_commit": recorded_at_commit}
            added.append(rel)
        elif known["sha256"] != hashes[rel]:
            conflicts.append(rel)
    if added:
        doc["count"] = len(doc["parts"])
        doc["parts"] = dict(sorted(doc["parts"].items()))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        tmp.replace(path)
    return {"added": added, "conflicts": conflicts}


# ---------------------------------------------------------------- classification

@dataclass
class PartDecision:
    """Everything the policy says about one summary part. Each field is decided independently."""

    path: str
    run_dir: str
    stem: str
    model: str | None
    instrument: str | None
    backend: str | None
    stimulus_class: str
    model_cohort: str | None
    execution_state: str
    n_results: int | None
    pairs_requested: int | None
    artifact_integrity: str
    integrity_detail: str | None
    sha256: str | None
    evidence_class: str
    clinical_review: str
    visibility: str
    restriction_reasons: list[str] = field(default_factory=list)
    rows_exported: bool = False
    rows_reason: str | None = None
    analysis: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def execution_state(summary: Any) -> tuple[str, int | None, int | None]:
    """(state, number of results, pairs requested) from a parsed summary. A finished run with a zero or null
    effect is ``completed``: the state describes the run, never the size or direction of what it measured."""
    if not isinstance(summary, dict) or not isinstance(summary.get("results"), list):
        return "unreadable", None, None
    n = len(summary["results"])
    requested = summary.get("pairs_requested")
    requested = requested if type(requested) is int else None
    if n == 0:
        return "empty", 0, requested
    if summary.get("completed") is False or "_partial" in summary:
        return "partial", n, requested
    if summary.get("completed") is True:
        return "completed", n, requested
    return "completion_not_recorded", n, requested


def _model_readings(summary: Mapping[str, Any], run_dir: str, model: str | None) -> list[str]:
    """Every reading of the part's model, in the order the old gate consulted them."""
    return [m for m in (model, summary.get("graph_model"), run_dir_model(run_dir)) if isinstance(m, str) and m]


def _integrity(rel: str, part: Path, backend: Any, recorded: Iterable[Mapping[str, str] | None]
               ) -> tuple[str, str | None, str | None]:
    """(state, detail, sha256). ``recorded`` are the hash maps to compare against (manifest, ledger)."""
    if backend is None:
        return "malformed", "summary has no 'backend' key", None
    if backend not in KNOWN_BACKENDS:
        return "malformed", f"unrecognized backend {backend!r}", None
    try:
        digest = sha256_file(part)
    except OSError as exc:
        return "unreadable", str(exc), None
    wanted = [m[rel] for m in recorded if m and rel in m]
    if not wanted:
        return "unrecorded", None, digest
    if any(w != digest for w in wanted):
        return "changed_since_recorded", "bytes differ from a recorded sha256", digest
    return "recorded_match", None, digest


def undeclared_graph_model(policy: Policy, summary: Mapping[str, Any]) -> str | None:
    """The part's own ``graph_model`` when it names a model that no cohort declares, else None. Only the
    part's explicit declaration is judged: a run-directory suffix can name a stimulus variant or an
    instrument, and a part without ``graph_model`` is a legacy base-model trace."""
    model = summary.get("graph_model")
    if isinstance(model, str) and model and policy.cohort_of(model) is None and instrument_of(model) is None:
        return model
    return None


def _membership_reason(policy: Policy, membership: str, *, stimulus_class: str, readings: list[str],
                       backend: Any, rel: str, integrity: str, visibility: str,
                       manifest: Mapping[str, str] | None, digest: str | None,
                       undeclared_model: str | None = None) -> str | None:
    """None when the membership admits the part, else the one reason it does not. The order matches the rule
    the collectors applied before this module existed, so their counts keep their meaning."""
    rule = policy.membership(membership)
    if stimulus_class in rule["exclude_stimulus_classes"]:
        return f"stimulus class {stimulus_class} (not a study batch)"
    excluded = policy.excluded_models(membership)
    for model in readings:
        if model in excluded:
            return f"model {model} (cohort {policy.cohort_of(model)}, outside this membership)"
    if backend is None:
        return "malformed part: no 'backend' key"
    if backend not in KNOWN_BACKENDS:
        return f"malformed part: unrecognized backend {backend!r}"
    if rule["purpose"] == "analysis" and undeclared_model:
        return f"model {undeclared_model} is in no declared cohort"
    pinned = rule["logits_manifest"]
    if pinned:
        # The 2026-10-09 rule: hosted and activation-patching parts are read as they are; a logits part is
        # read only when the pinned manifest lists the sha256 of its bytes. Added 2026-11-10: a part whose
        # bytes differ from its ledger record is refused here too.
        if backend not in BACKENDS_WITHOUT_MANIFEST:
            if manifest is None:
                return "pinned manifest missing"
            want = manifest.get(rel)
            if want is None:
                return "logits part outside the pinned manifest"
            if want != digest:
                return "logits part changed since it was recorded"
        if integrity in INTEGRITY_FAILURES:
            return f"artifact integrity: {integrity}"
        return None
    if integrity in INTEGRITY_FAILURES:
        return f"artifact integrity: {integrity}"
    if rule["purpose"] == "display" and visibility != "public":
        return "restricted"
    return None


def classify_part(root: Path | str, part: Path | str, summary: Any, model: str | None = None, *,
                  policy: Policy | None = None, manifest: Mapping[str, str] | None = None,
                  ledger: Mapping[str, str] | None = None) -> PartDecision:
    """The full decision for one part. Never raises on a malformed part: it reports the defect as its
    integrity state, so a catalogue can list the part and say what is wrong with it.

    ``manifest`` and ``ledger`` are the recorded hashes to compare against; pass ``load_manifest(root)`` and
    ``load_ledger(root)``. With neither, integrity is ``unrecorded`` for every readable, well-formed part,
    and a logits part is outside any membership that pins a manifest (reason ``pinned manifest missing``):
    this function has no optional-manifest mode, so it never calls a part pinned without seeing the pin.
    """
    policy = policy or load_policy()
    root = Path(root).resolve()
    part = Path(part)
    part = part if part.is_absolute() else Path.cwd() / part
    rel = part.resolve().relative_to(root).as_posix()
    run_dir = part.parent.name
    stem, suffix = run_dir_parts(run_dir)
    summary_map: Mapping[str, Any] = summary if isinstance(summary, dict) else {}
    backend = summary_map.get("backend")
    readings = _model_readings(summary_map, run_dir, model)
    instrument = instrument_of(suffix)
    resolved_model = None if instrument else (readings[0] if readings else None)
    stimulus_class = policy.stimulus_class(stem)
    entry = policy.stimulus_entry(stimulus_class)
    state, n_results, requested = execution_state(summary)
    integrity, detail, digest = _integrity(rel, part, backend, (manifest, ledger))
    if state == "unreadable":
        integrity, detail = "unreadable", "summary is not a JSON object with a 'results' list"

    reasons: list[str] = []
    if integrity in INTEGRITY_FAILURES:
        reasons.append(f"artifact_integrity:{integrity}")
    if entry.get("restriction"):
        reasons.append(entry["restriction"])
    visibility = "restricted" if reasons else "public"

    analysis = {}
    for membership in policy.doc["memberships"]:
        reason = _membership_reason(policy, membership, stimulus_class=stimulus_class, readings=readings,
                                    backend=backend, rel=rel, integrity=integrity, visibility=visibility,
                                    manifest=manifest, digest=digest,
                                    undeclared_model=undeclared_graph_model(policy, summary_map))
        analysis[membership] = {"eligible": reason is None, "reason": reason}

    rows_exported = bool(entry["rows_exported"]) and visibility == "public" and not instrument
    rows_reason = None
    if not rows_exported:
        rows_reason = (entry.get("rows_reason") if not entry["rows_exported"]
                       else "; ".join(reasons) if reasons
                       else f"instrument run ({instrument}): a typed artifact with its own exporter")
    return PartDecision(
        path=rel, run_dir=run_dir, stem=stem, model=resolved_model, instrument=instrument, backend=backend,
        stimulus_class=stimulus_class, model_cohort=policy.cohort_of(resolved_model),
        execution_state=state, n_results=n_results, pairs_requested=requested,
        artifact_integrity=integrity, integrity_detail=detail, sha256=digest,
        evidence_class=policy.evidence_class(stimulus_class, resolved_model),
        clinical_review=entry["clinical_review"], visibility=visibility, restriction_reasons=reasons,
        rows_exported=rows_exported, rows_reason=rows_reason, analysis=analysis)


def row_restriction(batch: str | None, index: int | None, clinical_prompt: str | None, **seal_paths: Any
                    ) -> str | None:
    """``"sealed_holdout"`` when the Tier B seal covers the row, else None. scripts/tierb_split.py is the only
    implementation of the seal; this is the policy's name for its answer. ``SealError`` propagates: a seal
    that cannot be evaluated is a configuration error, never a reason to publish the row."""
    return "sealed_holdout" if _tierb_split.sealed_pair(batch, index, clinical_prompt, **seal_paths) else None


# ---------------------------------------------------------------- the gate collectors use

class Gate:
    """Admits or skips summary parts for one collector run under one membership rule, and counts every skip
    by reason. ``held`` keeps its name because collectors and the timeline payload read it; it counts parts
    outside the membership, which are not hidden: the results catalogue lists them."""

    def __init__(self, root: Path | str = ".", manifest_optional: bool = False, membership: str | None = None,
                 policy: Policy | None = None) -> None:
        """``manifest_optional`` is for readers that publish nothing (audit_target_reads.py's mirror of the
        collector): under a membership that pins a manifest, with no manifest at ``root`` they read logits
        parts instead of refusing. Every publishing collector leaves it False."""
        self.root = Path(root).resolve()
        self.manifest_optional = manifest_optional
        self.policy = policy or load_policy()
        self.membership = membership or self.policy.default_membership
        self.rule = self.policy.membership(self.membership)
        self._manifest: dict[str, str] | None = None
        self._ledger: dict[str, str] | None = None
        self.held: Counter[str] = Counter()

    def _rel(self, part: Path) -> str:
        path = Path(part)
        path = path if path.is_absolute() else Path.cwd() / path
        return path.resolve().relative_to(self.root).as_posix()

    def _pinned_manifest(self) -> dict[str, str] | None:
        """The membership's logits manifest, loaded on first need; None when it is optional and absent."""
        if self._manifest is None:
            rel = self.rule["logits_manifest"]
            if self.manifest_optional and not (self.root / rel).exists():
                return None
            self._manifest = load_manifest(self.root, rel)
        return self._manifest

    def reason(self, part: Path | str, summary: Mapping[str, Any], model: str | None = None) -> str | None:
        """None when the membership admits the part, else why not. Raises ``ReleaseError`` when the part's
        own metadata cannot support a decision."""
        part = Path(part)
        run_dir = part.parent.name
        stem = run_dir_parts(run_dir)[0]
        stimulus_class = self.policy.stimulus_class(stem)
        if stimulus_class in self.rule["exclude_stimulus_classes"]:
            return f"stimulus class {stimulus_class} (not a study batch)"
        excluded = self.policy.excluded_models(self.membership)
        for reading in _model_readings(summary, run_dir, model):
            if reading in excluded:
                return f"model {reading} (cohort {self.policy.cohort_of(reading)}, outside this membership)"
        backend = summary.get("backend")
        if backend is None:
            raise ReleaseError(f"{part}: summary missing required 'backend' key; cannot decide membership")
        if backend not in KNOWN_BACKENDS:
            raise ReleaseError(f"{part}: unrecognized backend {backend!r}; expected 'logits', 'hosted', or "
                               "'activation_patch'")
        if self.rule["purpose"] == "analysis":
            undeclared = undeclared_graph_model(self.policy, summary)
            if undeclared:
                return f"model {undeclared} is in no declared cohort"
        if self._ledger is None:
            self._ledger = load_ledger(self.root)
        if self.rule["logits_manifest"]:
            if backend not in BACKENDS_WITHOUT_MANIFEST:
                manifest = self._pinned_manifest()
                if manifest is None:
                    return None                          # manifest_optional and no manifest on disk
                want = manifest.get(self._rel(part))
                if want is None:
                    return "logits part outside the pinned manifest"
                if want != sha256_file(part):
                    return "logits part changed since it was recorded"
            # The path is resolved against the root only when a ledger exists to consult, so a part outside
            # the root is read as before the ledger existed.
            if self._ledger:
                try:
                    recorded_sha = self._ledger.get(self._rel(part))
                except ValueError:
                    recorded_sha = None
                if recorded_sha is not None and recorded_sha != sha256_file(part):
                    return "artifact integrity: changed_since_recorded"
            return None
        if not isinstance(summary.get("results"), list):
            return "artifact integrity: unreadable"
        rel = self._rel(part)
        recorded = [self._ledger]
        legacy = self.root / RELEASE_MANIFEST
        if legacy.exists():
            recorded.append(load_manifest(self.root))
        integrity, _, _ = _integrity(rel, part, backend, recorded)
        if integrity in INTEGRITY_FAILURES:
            return f"artifact integrity: {integrity}"
        if self.rule["purpose"] == "display":
            entry = self.policy.stimulus_entry(stimulus_class)
            if entry.get("restriction"):
                return f"restricted: {entry['restriction']}"
        return None

    def admit(self, part: Path | str, summary: Mapping[str, Any], model: str | None = None) -> bool:
        """True when the part may be read under this gate's membership. ``model`` is the collector's own
        reading of the part's model (graph_model or directory suffix); the other readings are checked too."""
        reason = self.reason(part, summary, model)
        if reason is None:
            return True
        self.held[reason] += 1
        return False

    def describe(self) -> str:
        """One line naming the membership and policy in force, for a collector's stdout."""
        own = self.policy.path.resolve() == (ENGINE / POLICY_PATH).resolve()
        source = "" if own else f"; policy file overridden: {self.policy.path}"
        return f"analysis membership {self.membership} (policy {self.policy.version}{source})"

    def report(self) -> str:
        """One line for stdout, or "" when nothing was skipped."""
        if not self.held:
            return ""
        return (f"membership {self.membership} (scripts/results_policy.py), parts not read: "
                + ", ".join(f"{reason} {n}" for reason, n in sorted(self.held.items())))


def is_exploratory_run_dir(run_dir: str, policy: Policy | None = None) -> bool:
    """True for a run directory whose stimulus class the default membership excludes (today the hand-authored
    ``agscen_`` sets), whatever the suffix (a model id or an instrument such as ``jlens_<model>``)."""
    policy = policy or load_policy()
    rule = policy.membership(policy.default_membership)
    return policy.stimulus_class(run_dir_parts(run_dir)[0]) in rule["exclude_stimulus_classes"]


def outside_default_membership(model: str | None, policy: Policy | None = None) -> bool:
    """True when the default membership excludes the model's cohort."""
    policy = policy or load_policy()
    return model in policy.excluded_models(policy.default_membership)
