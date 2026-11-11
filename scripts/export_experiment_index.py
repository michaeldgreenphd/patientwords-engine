#!/usr/bin/env python3
"""Write the experiment comparison index the site's experiments page lists: ``data/experiments/index.json``.

The page ``experiments/index.html`` reads this one file when its address names no bundle and links to every
comparison in it, so a reader does not write an address parameter by hand. The index is built from the bundle
files (``patientwords.experiment-bundle/1``, written by ``python -m scripts.experiments.cli bundle``) that are
present under the site's ``data/`` directory. It holds labels, counts and hashes copied from each bundle; it
holds no prompt text and no measurement.

A bundle is listed only when its own evidence block says it may be published:

* it is not synthetic (``evidence.synthetic`` and ``protocol.synthetic`` are false, the evidence class is not
  ``synthetic_fixture`` and the limitations do not say ``synthetic_not_measurement``);
* ``evidence.visibility`` is ``public``;
* ``evidence.restriction_reasons`` is empty;
* the file validates against ``schemas/experiments/bundle.v1.schema.json``;
* its path under ``data/`` is one the page accepts as an address (see ``addressable``).

Every other bundle file is counted and named under ``not_listed`` with its reasons and is never linked. This
writer does not move, change or delete a bundle file. A bundle that may not be published should not be under
the site's ``data/`` at all: ``scripts/experiment_index_contract.py`` reports it as an error.

Prompt text. A listed bundle may hold prompt text in ``protocol.families[].variant_text`` (the explicit export
of ``scripts/experiments/bundle.py``). Before such a bundle is listed, every exported prompt is asked of the
holdout seal again (``scripts/results_policy.row_restriction``: the family's legacy row when it has one, and
each prompt as a bare phrase). If any is restricted, or the seal cannot be evaluated, the run stops with exit 2
and writes nothing. The message names the file, the family and the variant, never the text. A site with no
text-carrying eligible bundle does not need the seal's inputs.

No study bundle exists on 2026-11-10, so the index the site holds lists nothing.

Usage:

    python scripts/export_experiment_index.py --site ../patientwords            # writes data/experiments/index.json
    python scripts/export_experiment_index.py --site ../patientwords --dry-run  # prints the totals, writes nothing

Exit codes: 0 written (or computed, with ``--dry-run``); 2 refused, nothing written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frontend_contract_schema import check_schema_subset  # noqa: E402
from provenance_stamp import engine_sha  # noqa: E402

ENGINE = Path(__file__).resolve().parents[1]
SCHEMA = "patientwords.experiment-index/1"
BUNDLE_SCHEMA = "patientwords.experiment-bundle/1"
BUNDLE_MARK = b"patientwords.experiment-bundle/"
BUNDLE_SCHEMA_PATH = ENGINE / "schemas" / "experiments" / "bundle.v1.schema.json"
INDEX_SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "experiment_index.v1.schema.json"
INDEX_FILE = "experiments/index.json"
SYNTHETIC_CLASS = "synthetic_fixture"
SYNTHETIC_LIMITATION = "synthetic_not_measurement"
ELIGIBILITY = ("Listed: a patientwords.experiment-bundle/1 file under the site's data directory whose evidence "
               "block says it is not synthetic, has visibility 'public' and no restriction reason, that validates "
               "against the bundle schema and whose path the experiments page accepts. Every other bundle file is "
               "named under not_listed with its reasons and is never linked.")
# A path under data/ that the page's address rule accepts (``bundleRefusal`` in the site's
# experiments/index.html; mirrored as ``bundle_param_refusal`` in scripts/check_experiment_preview.py).
# tests/test_experiment_index.py compares this rule with that mirror on its case table.
_SEGMENT = r"[A-Za-z0-9_-][A-Za-z0-9._-]*"
_ADDRESS = re.compile(rf"{_SEGMENT}(/{_SEGMENT})*\Z")
MAX_ADDRESS = 200

RowRestriction = Callable[[str | None, int | None, str | None], str | None]


class IndexRefusal(Exception):
    """The index cannot be written. Reported with exit 2; nothing is written."""


def addressable(relative: str) -> bool:
    """Whether the experiments page accepts ``relative`` (a path under ``data/``) as its ``bundle`` address."""
    return (0 < len(relative) <= MAX_ADDRESS and ".." not in relative and relative.endswith(".json")
            and bool(_ADDRESS.fullmatch(relative)))


def find_bundle_files(data_dir: Path) -> list[Path]:
    """Every ``.json`` file under ``data_dir`` whose bytes name a bundle schema, sorted by relative path.

    The index file itself is skipped. A file is opened in full only here and only to look for the schema name;
    whether it is a bundle is decided on the parsed document by ``classify``."""
    found = []
    for path in sorted(data_dir.rglob("*.json"), key=lambda p: p.relative_to(data_dir).as_posix()):
        if not path.is_file() or path.relative_to(data_dir).as_posix() == INDEX_FILE:
            continue
        try:
            if BUNDLE_MARK in path.read_bytes():
                found.append(path)
        except OSError:
            found.append(path)  # unreadable: classified as such, never skipped silently
    return found


def _structural_errors(doc: Any) -> list[str]:
    errors: list[str] = []
    schema = json.loads(BUNDLE_SCHEMA_PATH.read_text(encoding="utf-8"))
    check_schema_subset(lambda _artifact, where, why: errors.append(f"{where}: {why}"), "bundle", doc, schema)
    return errors


def ineligibility(doc: Any, relative: str) -> list[str]:
    """The reasons a parsed bundle document is not listed; empty when it is eligible. Fails closed: a label
    that is absent or has an unexpected type counts against the bundle."""
    if not isinstance(doc, dict) or doc.get("schema_version") != BUNDLE_SCHEMA:
        return ["not_bundle_version_1"]
    reasons: list[str] = []
    evidence = doc.get("evidence") if isinstance(doc.get("evidence"), dict) else {}
    protocol = doc.get("protocol") if isinstance(doc.get("protocol"), dict) else {}
    limitations = doc.get("limitations") if isinstance(doc.get("limitations"), list) else []
    if (evidence.get("synthetic") is not False or protocol.get("synthetic") is not False
            or evidence.get("evidence_class") == SYNTHETIC_CLASS or SYNTHETIC_LIMITATION in limitations):
        reasons.append("synthetic")
    if evidence.get("visibility") != "public":
        reasons.append("visibility_not_public")
    if evidence.get("restriction_reasons") != []:
        reasons.append("restricted")
    if _structural_errors(doc):
        reasons.append("invalid_structure")
    if not addressable(relative):
        reasons.append("path_not_addressable")
    return reasons


def _default_row_restriction() -> RowRestriction:
    import results_policy

    return results_policy.row_restriction


def check_exported_text(doc: Mapping[str, Any], relative: str, row_restriction: RowRestriction | None) -> int:
    """Ask the seal about every prompt an eligible bundle exports. Returns the number of families with text.

    Raises ``IndexRefusal`` when a prompt, or a target text exported beside it, is restricted. A ``SealError``
    from the seal propagates to ``main``.
    The seal is not consulted for a bundle without ``variant_text``."""
    families = [f for f in doc["protocol"]["families"] if isinstance(f, dict) and f.get("variant_text")]
    if not families:
        return 0
    check = row_restriction or _default_row_restriction()
    for family in families:
        family_id, text = family.get("family_id"), family["variant_text"]
        join = family.get("legacy_join")
        if isinstance(join, dict):
            restriction = check(join.get("batch"), join.get("batch_index"), (text.get("clinical") or {}).get("prompt"))
            if restriction is not None:
                raise IndexRefusal(f"data/{relative}: family {family_id}: legacy row ({join.get('batch')}, "
                                   f"{join.get('batch_index')}) is restricted ({restriction}) and the bundle "
                                   "exports its prompt text")
        for name in sorted(text):
            prompt = text[name].get("prompt")
            if not prompt:
                continue
            restriction = check(None, None, prompt)
            if restriction is not None:
                raise IndexRefusal(f"data/{relative}: family {family_id}, variant {name}: the exported prompt "
                                   f"text is restricted ({restriction})")
        targets = family.get("target_text")
        for target_id in sorted(targets) if isinstance(targets, dict) else ():
            target = targets[target_id].get("text") if isinstance(targets[target_id], dict) else None
            if not target:
                continue
            restriction = check(None, None, target)
            if restriction is not None:
                raise IndexRefusal(f"data/{relative}: family {family_id}, target {target_id}: the exported "
                                   f"target text is restricted ({restriction})")
    return len(families)


def _entry(doc: Mapping[str, Any], relative: str, sha256: str, text_cases: int) -> dict[str, Any]:
    protocol, evidence = doc["protocol"], doc["evidence"]
    model = protocol["model"]
    endpoint = protocol["primary_endpoint"]

    def label(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    return {
        "bundle": relative, "bundle_sha256": sha256,
        "protocol": {"id": protocol["id"], "version": protocol["version"], "sha256": protocol["sha256"]},
        "model": {"study_id": label(model.get("study_id")), "hf_id": label(model.get("hf_id"))},
        "evidence_class": evidence["evidence_class"], "clinical_review": evidence["clinical_review"],
        "visibility": evidence["visibility"], "analysis_memberships": list(evidence["analysis_memberships"]),
        "cases": len(doc["comparisons"]), "methods": list(protocol["methods"]),
        "primary_endpoint": {key: label(endpoint.get(key)) for key in ("method", "metric", "target")},
        "prompt_text_cases": text_cases,
    }


def build_index(site: Path, *, row_restriction: RowRestriction | None = None) -> dict[str, Any]:
    """The index document for the site checkout at ``site``, without its provenance stamp. Reads only.

    The same site gives the same document. Raises ``IndexRefusal`` when ``site`` has no ``data`` directory or
    an eligible bundle exports restricted text."""
    data_dir = site / "data"
    if not data_dir.is_dir():
        raise IndexRefusal(f"{site} has no data/ directory (not a site checkout)")
    listed: list[dict[str, Any]] = []
    not_listed: list[dict[str, Any]] = []
    files = find_bundle_files(data_dir)
    counted = 0
    for path in files:
        relative = path.relative_to(data_dir).as_posix()
        try:
            raw = path.read_bytes()
            doc = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            counted += 1
            not_listed.append({"file": relative, "reasons": ["unreadable"]})
            continue
        version = doc.get("schema_version") if isinstance(doc, dict) else None
        if not (isinstance(version, str) and version.encode().startswith(BUNDLE_MARK)):
            continue  # a file that mentions the schema name and is not a bundle (documentation, a receipt)
        counted += 1
        reasons = ineligibility(doc, relative)
        if reasons:
            not_listed.append({"file": relative, "reasons": reasons})
            continue
        text_cases = check_exported_text(doc, relative, row_restriction)
        listed.append(_entry(doc, relative, hashlib.sha256(raw).hexdigest(), text_cases))
    listed.sort(key=lambda entry: (entry["protocol"]["id"], entry["protocol"]["version"], entry["bundle"]))
    index = {
        "schema_version": SCHEMA, "bundle_schema": BUNDLE_SCHEMA, "eligibility": ELIGIBILITY,
        "comparisons": listed, "not_listed": not_listed,
        "totals": {"bundle_files": counted, "listed": len(listed), "not_listed": len(not_listed)},
    }
    errors: list[str] = []
    check_schema_subset(lambda _artifact, where, why: errors.append(f"{where}: {why}"), INDEX_FILE, index,
                        json.loads(INDEX_SCHEMA_PATH.read_text(encoding="utf-8")))
    if errors:
        raise IndexRefusal("the index does not match its own schema: " + "; ".join(errors[:5]))
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True, help="frontend repository root; writes <site>/data/experiments/"
                                                      "index.json")
    parser.add_argument("--dry-run", action="store_true", help="compute and print the totals; write nothing")
    args = parser.parse_args(argv)
    site = Path(args.site).resolve()
    try:
        index = build_index(site)
    except IndexRefusal as exc:
        print(f"experiment index: refusing, nothing written: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        if type(exc).__name__ != "SealError":
            raise
        print(f"experiment index: the holdout seal could not be evaluated, nothing written: {exc}",
              file=sys.stderr)
        return 2
    index["_provenance"] = {"generator": "scripts/export_experiment_index.py", "engine_sha": engine_sha(ENGINE),
                            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    totals = index["totals"]
    print(f"experiment index: {totals['bundle_files']} bundle file(s) under data/, {totals['listed']} listed, "
          f"{totals['not_listed']} not listed")
    for row in index["not_listed"]:
        print(f"  not listed - data/{row['file']}: {', '.join(row['reasons'])}", file=sys.stderr)
    if args.dry_run:
        print("  DRY RUN: nothing was written")
        return 0
    out = site / "data" / INDEX_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
