"""Contract check of the experiment comparison index (``data/experiments/index.json``) in a site checkout.

``check_experiment_index(rep, site)`` is written to be called from ``validate`` in
``scripts/validate_frontend_contract.py``, next to ``check_results_catalogue``. ``rep`` is that module's
``Report`` (``err(artifact, path, message)`` and a ``notes`` list); nothing is imported from it.

The rules are written here and nothing is imported from the producer (``scripts/export_experiment_index.py``),
so a producer defect is not repeated by its own check. ``tests/test_experiment_index.py`` compares the two on
a table of cases. Only files under ``scripts/`` are read besides the site: site CI checks out ``scripts/``,
``data/``, ``ops/`` and ``docs/`` of the engine and not ``schemas/``. For that reason this check does not
validate a bundle against ``schemas/experiments/bundle.v1.schema.json``; the producer does.

What is checked:

* The index exists whenever the site has the page that requests it (``experiments/index.html``). A missing
  file is a failed request on the public page.
* The index has the structure of ``scripts/contracts/experiment_index.v1.schema.json``.
* Every bundle file under ``data/`` (a ``.json`` whose ``schema_version`` names an experiment bundle) may be
  published: version 1, not synthetic, visibility ``public``, no restriction reason. A bundle that fails any
  of these is an error wherever it lies, listed or not: the directory is public.
* The index lists exactly the publishable bundles whose path the page accepts. A listed path that is absent is
  a failed request; a publishable bundle that is not listed means the index is stale.
* Each entry's hash is the SHA-256 of the file's bytes and its labels are the bundle's own, so a hand-edited
  index does not pass. The totals equal the lists.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

INDEX_NAME = "experiments/index.json"
PAGE = "experiments/index.html"
INDEX_SCHEMA_VERSION = "patientwords.experiment-index/1"
BUNDLE_VERSION_1 = "patientwords.experiment-bundle/1"
BUNDLE_PREFIX = "patientwords.experiment-bundle/"
INDEX_SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "experiment_index.v1.schema.json"

# File-relative loading, as scripts/validate_frontend_contract.py does: no sys.path change.
_SPEC = importlib.util.spec_from_file_location(
    "_patientwords_experiment_index_schema", Path(__file__).resolve().with_name("frontend_contract_schema.py"))
assert _SPEC is not None and _SPEC.loader is not None
_ADAPTER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ADAPTER)

_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*\Z")


def page_accepts(relative: str) -> bool:
    """The address rule of the experiments page, for a path under ``data/``: at most 200 characters, no
    ``..``, every segment starts with a letter, digit, ``_`` or ``-`` and uses ``A-Z a-z 0-9 . _ -`` only, and
    the name ends in ``.json``."""
    if not relative or len(relative) > 200 or ".." in relative or not relative.endswith(".json"):
        return False
    return all(_NAME.match(part) for part in relative.split("/"))


def publication_problems(doc: Any) -> list[str]:
    """Why a parsed bundle document may not be published; empty when it may. Absent labels count against it."""
    if not isinstance(doc, dict) or doc.get("schema_version") != BUNDLE_VERSION_1:
        return ["it is not a version 1 bundle"]
    problems = []
    evidence = doc.get("evidence")
    protocol = doc.get("protocol")
    evidence = evidence if isinstance(evidence, dict) else {}
    protocol = protocol if isinstance(protocol, dict) else {}
    limitations = doc.get("limitations")
    synthetic = (evidence.get("synthetic") is not False or protocol.get("synthetic") is not False
                 or evidence.get("evidence_class") == "synthetic_fixture"
                 or not isinstance(limitations, list) or "synthetic_not_measurement" in limitations)
    if synthetic:
        problems.append("it is synthetic or does not say that it is not")
    if evidence.get("visibility") != "public":
        problems.append(f"its visibility is {evidence.get('visibility')!r}, not 'public'")
    reasons = evidence.get("restriction_reasons")
    if not isinstance(reasons, list) or reasons:
        problems.append("it names a restriction reason or does not record the list")
    return problems


def _bundles(data_dir: Path) -> dict[str, tuple[bytes, Any]]:
    """``{relative path: (bytes, parsed document or None)}`` for every bundle-like ``.json`` under ``data/``."""
    found: dict[str, tuple[bytes, Any]] = {}
    for path in sorted(data_dir.rglob("*.json")):
        relative = path.relative_to(data_dir).as_posix()
        if relative == INDEX_NAME or not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if BUNDLE_PREFIX.encode() not in raw:
            continue
        try:
            doc = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue  # not JSON: no page can render it as a bundle; other checks report unreadable artifacts
        version = doc.get("schema_version") if isinstance(doc, dict) else None
        if isinstance(version, str) and version.startswith(BUNDLE_PREFIX):
            found[relative] = (raw, doc)
    return found


def check_experiment_index(rep: Any, site: Path) -> None:
    """Report every violation of the rules in this module's docstring through ``rep.err``."""
    data_dir = site / "data"
    bundles = _bundles(data_dir) if data_dir.is_dir() else {}
    publishable = set()
    for relative, (_raw, doc) in bundles.items():
        problems = publication_problems(doc)
        if problems:
            rep.err(relative, "$.evidence", "an experiment bundle that may not be published is under the site's "
                    "data directory: " + "; ".join(problems))
        elif not page_accepts(relative):
            rep.err(relative, "-", "the experiments page refuses this path as an address, so the bundle cannot "
                    "be listed")
        else:
            publishable.add(relative)

    path = data_dir / INDEX_NAME
    if not path.is_file():
        if (site / PAGE).is_file():
            rep.err(INDEX_NAME, "-", f"artifact missing: {PAGE} requests it (a failed request on the public page); "
                    "write it with scripts/export_experiment_index.py")
        else:
            rep.notes.append(f"{INDEX_NAME} :: - :: no experiment index and no experiments page")
        return
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        rep.err(INDEX_NAME, "-", f"unreadable: {error}")
        return
    schema = json.loads(INDEX_SCHEMA_PATH.read_text(encoding="utf-8"))
    _ADAPTER.check_schema_subset(rep.err, INDEX_NAME, index, schema)
    if not isinstance(index, dict):
        return
    if index.get("schema_version") != INDEX_SCHEMA_VERSION:
        rep.err(INDEX_NAME, "$.schema_version", f"expected {INDEX_SCHEMA_VERSION!r}, got "
                f"{index.get('schema_version')!r}")
    if index.get("bundle_schema") != BUNDLE_VERSION_1:
        rep.err(INDEX_NAME, "$.bundle_schema", f"expected {BUNDLE_VERSION_1!r}")
    entries = index.get("comparisons") if isinstance(index.get("comparisons"), list) else []
    listed: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"$.comparisons[{i}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("bundle"), str):
            continue  # the schema check has reported it
        relative = entry["bundle"]
        if relative in listed:
            rep.err(INDEX_NAME, where, f"{relative} is listed twice")
        listed.add(relative)
        if not page_accepts(relative):
            rep.err(INDEX_NAME, f"{where}.bundle", f"the experiments page refuses the address {relative!r}")
            continue
        if relative not in bundles:
            rep.err(INDEX_NAME, f"{where}.bundle", f"data/{relative} is listed but is not a published bundle file "
                    "(a failed request on the public page)")
            continue
        raw, doc = bundles[relative]
        if relative not in publishable:
            rep.err(INDEX_NAME, f"{where}.bundle", f"data/{relative} is listed and may not be published")
            continue
        if entry.get("bundle_sha256") != hashlib.sha256(raw).hexdigest():
            rep.err(INDEX_NAME, f"{where}.bundle_sha256", f"not the SHA-256 of data/{relative}; the index is stale")
        evidence, protocol = doc.get("evidence", {}), doc.get("protocol", {})
        own = {
            "evidence_class": evidence.get("evidence_class"), "clinical_review": evidence.get("clinical_review"),
            "visibility": evidence.get("visibility"), "analysis_memberships": evidence.get("analysis_memberships"),
            "protocol": {key: protocol.get(key) for key in ("id", "version", "sha256")},
            "cases": len(doc["comparisons"]) if isinstance(doc.get("comparisons"), list) else None,
            "methods": protocol.get("methods"),
        }
        for key, value in own.items():
            if entry.get(key) != value:
                rep.err(INDEX_NAME, f"{where}.{key}", f"{entry.get(key)!r} is not what data/{relative} records "
                        f"({value!r})")
    for relative in sorted(publishable - listed):
        rep.err(INDEX_NAME, "$.comparisons", f"data/{relative} may be published and is not listed; the index is "
                "stale (rerun scripts/export_experiment_index.py)")
    not_listed = index.get("not_listed") if isinstance(index.get("not_listed"), list) else []
    named = {row.get("file") for row in not_listed if isinstance(row, dict)}
    for relative in sorted(named & listed):
        rep.err(INDEX_NAME, "$.not_listed", f"{relative} is both listed and not listed")
    totals = index.get("totals") if isinstance(index.get("totals"), dict) else {}
    expected = {"listed": len(entries), "not_listed": len(not_listed), "bundle_files": len(entries) + len(not_listed)}
    for key, value in expected.items():
        if totals.get(key) != value:
            rep.err(INDEX_NAME, f"$.totals.{key}", f"{totals.get(key)!r} does not equal the {value} in the lists")
