#!/usr/bin/env python3
"""Immutable analysis snapshots: what a published analysis was computed from, by version.

The results catalogue (scripts/export_results_catalogue.py) changes whenever a run lands. A statistic must not:
a number a page or a sentence cites has to keep resolving to the inputs it was computed from. A snapshot is
that record. It fixes, for one membership rule (scripts/results_policy.py) at one engine commit:

* every summary part the membership admits, with the sha256 of its bytes (hosted parts included, which the
  2026-10-09 logits manifest never covered);
* the policy version and file hash, the membership rule as written, and the manifest it pins;
* what was left out and why, as counts (other cohorts, unpinned parts, hand-authored sets, sealed rows);
* the models, the correction families they form, and per-model row denominators with sealed rows excluded;
* the sha256 of each published statistics file, when a site checkout is given, and the seed, resample count
  and family sizes those files state.

Snapshots are never rewritten: ``create`` refuses an id that exists, and a correction is a new id that names
the one it supersedes and says what changed. ``verify`` re-hashes a snapshot's inputs in the current checkout
and fails when any recorded input is missing or different; parts that landed afterwards are reported, not
failed, because the evolving state is the catalogue's business.

  python scripts/results_snapshot.py create --id study-interim-20261110 --site ../patientwords \\
      --change "first snapshot: the membership as published since 2026-10-09"
  python scripts/results_snapshot.py verify --id study-interim-20261110
  python scripts/results_snapshot.py list
  python scripts/results_snapshot.py diff --from study-interim-20261110 --to exploratory-open-20261110

Creating a snapshot changes no published number. Changing which membership the collectors read is a separate,
reviewed edit of data/results_policy/policy.v1.json (its ``analysis_pin`` states the release condition).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import results_policy as rp  # noqa: E402

SCHEMA = "patientwords.analysis-snapshot/1"
INDEX_SCHEMA = "patientwords.analysis-snapshot-index/1"
SNAPSHOT_DIR = Path("data") / "analysis_snapshots"
ID_RE = re.compile(r"[a-z0-9][a-z0-9.-]{2,62}\Z")
# Published statistics files a snapshot records when a site checkout is given. A file that does not exist is
# recorded as absent, never skipped silently.
SITE_OUTPUTS = ("data/urgency_shift.json", "data/model_stats.json", "data/simulated_scenarios.json",
                "data/convergence.json", "data/translation_scale.json", "data/tag_mass.json",
                "data/retrace_consistency.json", "data/timeline.json")
ENGINE_INPUTS = ("data/urgency_tiers.draft.json",)
ENDPOINTS = [
    "next-token probability of the first encoded target token under each wording (a lexical proxy, not "
    "whole-answer correctness)",
    "language penalty: patient-wording minus clinical-wording probability of that token",
    "top-token flip and its urgency-tier class against data/urgency_tiers.draft.json (draft vocabulary, "
    "domain review pending)",
]


class SnapshotError(RuntimeError):
    """The snapshot cannot be created or read soundly; nothing is written."""


def _git(root: Path, *argv: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *argv], capture_output=True, text=True)
    if proc.returncode:
        raise SnapshotError(f"git {' '.join(argv)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _statistics_block(site: Path) -> dict[str, Any] | None:
    """Seed, resample count and correction families as the published statistics file states them."""
    try:
        doc = json.loads((site / "data" / "model_stats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    families = (doc.get("benjamini_hochberg") or {}).get("families") or {}
    return {
        "source": "data/model_stats.json",
        "seed": doc.get("seed"), "boot": doc.get("boot"),
        "simultaneous_ci": doc.get("simultaneous_ci"),
        "correction_families": {name: {"across": fam.get("across"), "n_tests": fam.get("n_tests")}
                                for name, fam in families.items()},
        "models": doc.get("models"),
        "generated_by": doc.get("_provenance"),
        "caution": "the bootstrap uses one random stream consumed in sorted model order "
                   "(scripts/paired_stats_rigor.py), so the seed reproduces an interval only with this exact "
                   "model set",
    }


def build(engine: Path, membership: str, *, site: Path | None = None, policy: rp.Policy | None = None,
          seal_paths: dict[str, Any] | None = None) -> dict[str, Any]:
    """The snapshot body for ``membership`` over the checkout at ``engine`` (no id, time or change record)."""
    policy = policy or rp.load_policy()
    rule = policy.membership(membership)
    if rule["purpose"] != "analysis":
        raise SnapshotError(f"{membership} is a display rule; a snapshot fixes an analysis membership")
    engine = engine.resolve()
    gate = rp.Gate(engine, membership=membership, policy=policy)
    parts: dict[str, str] = {}
    by_backend: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    rows_by_model: Counter[str] = Counter()
    sealed_by_model: Counter[str] = Counter()
    seal_paths = seal_paths or {}
    for part in sorted((engine / "trace_out").glob("*/batch_summary*.json")):
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SnapshotError(f"{part} is unreadable ({type(exc).__name__}); a snapshot cannot skip it") from exc
        if not gate.admit(part, summary):
            continue
        rel = part.relative_to(engine).as_posix()
        parts[rel] = rp.sha256_file(part)
        stem, suffix = rp.run_dir_parts(part.parent.name)
        model = summary.get("graph_model") or suffix or "gemma-2-2b"
        by_backend[summary["backend"]] += 1
        by_model[model] += 1
        by_class[policy.stimulus_class(stem)] += 1
        if policy.stimulus_class(stem) != "study_batch" or rp.instrument_of(suffix):
            continue
        for result in summary.get("results", []):
            clinical = (result.get("prompts") or {}).get("clinical") if isinstance(result, dict) else None
            if rp.row_restriction(stem, result.get("index"), clinical, **seal_paths):
                sealed_by_model[model] += 1
            else:
                rows_by_model[model] += 1
    models = sorted(by_model)
    registered = sorted(m for m in models if policy.cohort_of(m) == "registered_20260709")
    manifest_rel = rule["logits_manifest"]
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "membership": membership,
        "membership_rule": dict(rule),
        "policy": {"version": policy.version, "sha256": hashlib.sha256(policy.path.read_bytes()).hexdigest()},
        "evidence_status": "interim analysis of the exploration split; sealed Tier B holdout rows are in no "
                           "input row count below and the confirmatory endpoint has not been run",
        "endpoints": ENDPOINTS,
        "inputs": {
            "n_parts": len(parts),
            "by_backend": dict(sorted(by_backend.items())),
            "by_stimulus_class": dict(sorted(by_class.items())),
            "parts_by_model": dict(sorted(by_model.items())),
            "logits_manifest": ({"path": manifest_rel, "sha256": _sha(engine / manifest_rel)}
                                if manifest_rel else None),
            "files": {rel: _sha(engine / rel) for rel in ENGINE_INPUTS},
            "parts": parts,
        },
        "exclusions": {"parts_outside_membership": dict(sorted(gate.held.items())),
                       "study_rows_withheld_by_seal": dict(sorted(sealed_by_model.items()))},
        "families": {
            "models": models,
            "registered_cohort": registered,
            "post_registration": [m for m in models if m not in registered],
            "correction": "Benjamini-Hochberg within each family in scripts/paired_stats_rigor.py; the "
                          "preregistration lists the corrected per-model test as secondary and exploratory "
                          "(docs/preregistration_tierB.md)",
        },
        "denominators": {"study_rows_by_model": dict(sorted(rows_by_model.items())),
                         "note": "result rows on generated study batches in the admitted parts, sealed rows "
                                 "excluded; each analysis script applies its own further population filters "
                                 "and records them"},
    }
    if site is not None:
        site = site.resolve()
        body["outputs"] = {
            "relation": "sha256 of each published file as it stood when the snapshot was created; recorded, "
                        "not recomputed",
            "site_commit": _git(site, "rev-parse", "HEAD").strip() if (site / ".git").exists() else None,
            "files": {rel: _sha(site / rel) for rel in SITE_OUTPUTS},
        }
        body["statistics"] = _statistics_block(site)
    return body


def _index_path(engine: Path) -> Path:
    return engine / SNAPSHOT_DIR / "index.json"


def load_index(engine: Path) -> dict[str, Any]:
    path = _index_path(engine)
    if not path.exists():
        return {"schema": INDEX_SCHEMA, "rule": "append-only; a snapshot file is never rewritten",
                "current": {}, "snapshots": []}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != INDEX_SCHEMA or not isinstance(doc.get("snapshots"), list):
        raise SnapshotError(f"{path} is not a {INDEX_SCHEMA} index")
    return doc


def load_snapshot(engine: Path, snapshot_id: str) -> dict[str, Any]:
    path = engine / SNAPSHOT_DIR / f"{snapshot_id}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SnapshotError(f"no snapshot {snapshot_id!r} at {path}") from None
    if doc.get("schema") != SCHEMA or doc.get("id") != snapshot_id:
        raise SnapshotError(f"{path} is not snapshot {snapshot_id!r}")
    return doc


def create(engine: Path, snapshot_id: str, membership: str, change: str, *, site: Path | None = None,
           supersedes: str | None = None, allow_dirty: bool = False, created_utc: str | None = None,
           seal_paths: dict[str, Any] | None = None) -> Path:
    if not ID_RE.fullmatch(snapshot_id):
        raise SnapshotError("a snapshot id is 3-63 characters of lowercase letters, digits, '.' and '-'")
    if not change.strip():
        raise SnapshotError("a snapshot needs a change record: one sentence saying what it is or what changed")
    path = engine / SNAPSHOT_DIR / f"{snapshot_id}.json"
    if path.exists():
        raise SnapshotError(f"{path} exists; a snapshot is never rewritten. Use a new id and --supersedes.")
    index = load_index(engine)
    known = {entry["id"] for entry in index["snapshots"]}
    if supersedes is not None and supersedes not in known:
        raise SnapshotError(f"--supersedes names {supersedes!r}, which is not a recorded snapshot")
    commit, dirty = None, None
    if (engine / ".git").exists():
        commit = _git(engine, "rev-parse", "HEAD").strip()
        dirty = _git(engine, "status", "--porcelain", "--untracked-files=no", "--", "trace_out",
                     str(rp.RELEASE_MANIFEST), str(rp.POLICY_PATH)).strip()
        if dirty and not allow_dirty:
            raise SnapshotError("tracked inputs differ from HEAD, so the snapshot would not describe committed "
                                "bytes; commit or restore them first:\n" + dirty)
    body = build(engine, membership, site=site, seal_paths=seal_paths)
    doc = {"schema": SCHEMA, "id": snapshot_id,
           "created_utc": created_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "engine_commit": commit, "inputs_committed": (not dirty) if commit else None,
           "supersedes": supersedes, "change_record": change.strip(),
           **{k: v for k, v in body.items() if k != "schema"}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:        # exclusive: never overwrite
        json.dump(doc, handle, indent=1)
        handle.write("\n")
    index["snapshots"].append({"id": snapshot_id, "created_utc": doc["created_utc"], "membership": membership,
                               "engine_commit": commit, "supersedes": supersedes,
                               "n_parts": doc["inputs"]["n_parts"], "change_record": doc["change_record"],
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    index["current"][membership] = snapshot_id
    tmp = _index_path(engine).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    tmp.replace(_index_path(engine))
    return path


def verify(engine: Path, snapshot_id: str) -> dict[str, Any]:
    """Compare a snapshot's recorded inputs with the checkout. ``ok`` is False when the snapshot file itself
    changed since it was indexed, or any recorded part is missing or has different bytes."""
    engine = engine.resolve()
    doc = load_snapshot(engine, snapshot_id)
    index = load_index(engine)
    entry = next((e for e in index["snapshots"] if e["id"] == snapshot_id), None)
    file_sha = hashlib.sha256((engine / SNAPSHOT_DIR / f"{snapshot_id}.json").read_bytes()).hexdigest()
    missing, changed = [], []
    for rel, want in doc["inputs"]["parts"].items():
        got = _sha(engine / rel)
        if got is None:
            missing.append(rel)
        elif got != want:
            changed.append(rel)
    policy = rp.load_policy()
    gate = rp.Gate(engine, membership=doc["membership"], policy=policy)
    landed_since = []
    for part in sorted((engine / "trace_out").glob("*/batch_summary*.json")):
        rel = part.relative_to(engine).as_posix()
        if rel in doc["inputs"]["parts"]:
            continue
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
            if gate.admit(part, summary):
                landed_since.append(rel)
        except (OSError, ValueError, rp.ReleaseError):
            continue
    return {"id": snapshot_id, "snapshot_file_unchanged": entry is not None and entry.get("sha256") == file_sha,
            "indexed": entry is not None, "missing": missing, "changed": changed,
            "admitted_now_but_not_in_snapshot": landed_since,
            "policy_changed_since": policy.version != doc["policy"]["version"]
            or hashlib.sha256(policy.path.read_bytes()).hexdigest() != doc["policy"]["sha256"],
            "ok": entry is not None and entry.get("sha256") == file_sha and not missing and not changed}


def diff(engine: Path, first: str, second: str) -> dict[str, Any]:
    a, b = load_snapshot(engine, first), load_snapshot(engine, second)
    pa, pb = a["inputs"]["parts"], b["inputs"]["parts"]
    da, db = a["denominators"]["study_rows_by_model"], b["denominators"]["study_rows_by_model"]
    return {
        "from": first, "to": second,
        "memberships": [a["membership"], b["membership"]],
        "parts": {"only_in_from": len(set(pa) - set(pb)), "only_in_to": len(set(pb) - set(pa)),
                  "in_both_same_bytes": sum(1 for p in set(pa) & set(pb) if pa[p] == pb[p]),
                  "in_both_different_bytes": sorted(p for p in set(pa) & set(pb) if pa[p] != pb[p])},
        "models": {"added": sorted(set(b["families"]["models"]) - set(a["families"]["models"])),
                   "removed": sorted(set(a["families"]["models"]) - set(b["families"]["models"]))},
        "study_rows_by_model": {m: {"from": da.get(m, 0), "to": db.get(m, 0)}
                                for m in sorted(set(da) | set(db)) if da.get(m, 0) != db.get(m, 0)},
        "post_registration_family_size": {"from": len(a["families"]["post_registration"]),
                                          "to": len(b["families"]["post_registration"])},
        "note": "a larger post-registration family changes every adjusted q-value in that family, and a "
                "changed model set changes bootstrap intervals drawn from the shared random stream; neither "
                "is comparable across snapshots without recomputation",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", default=str(rp.ENGINE), help="engine repository root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create", help="write a new immutable snapshot")
    c.add_argument("--id", required=True)
    c.add_argument("--membership", default=None, help="default: the policy's default membership")
    c.add_argument("--change", required=True, help="one sentence: what this snapshot is, or what changed")
    c.add_argument("--supersedes", default=None)
    c.add_argument("--site", default=None, help="frontend root; records the published statistics files' hashes")
    c.add_argument("--allow-dirty", action="store_true",
                   help="record uncommitted inputs (marked inputs_committed: false); for previews only")
    v = sub.add_parser("verify", help="re-hash a snapshot's inputs")
    v.add_argument("--id", default=None, help="default: every indexed snapshot")
    sub.add_parser("list", help="list snapshots")
    d = sub.add_parser("diff", help="compare two snapshots' inputs")
    d.add_argument("--from", dest="first", required=True)
    d.add_argument("--to", dest="second", required=True)
    args = parser.parse_args(argv)
    engine = Path(args.engine).resolve()
    try:
        if args.command == "create":
            membership = args.membership or rp.load_policy().default_membership
            path = create(engine, args.id, membership, args.change, supersedes=args.supersedes,
                          site=Path(args.site) if args.site else None, allow_dirty=args.allow_dirty)
            doc = json.loads(path.read_text(encoding="utf-8"))
            print(f"snapshot {args.id}: {doc['inputs']['n_parts']} parts under {membership} -> {path}")
            print("  no published number changed; commit the snapshot file and data/analysis_snapshots/index.json")
            return 0
        if args.command == "verify":
            ids = [args.id] if args.id else [e["id"] for e in load_index(engine)["snapshots"]]
            failed = False
            for snapshot_id in ids:
                report = verify(engine, snapshot_id)
                failed = failed or not report["ok"]
                print(f"{snapshot_id}: {'OK' if report['ok'] else 'FAILED'} - missing {len(report['missing'])}, "
                      f"changed {len(report['changed'])}, snapshot file unchanged "
                      f"{report['snapshot_file_unchanged']}; admitted now but not in the snapshot "
                      f"{len(report['admitted_now_but_not_in_snapshot'])}; policy changed since "
                      f"{report['policy_changed_since']}")
                for rel in (report["missing"] + report["changed"])[:20]:
                    print(f"  {rel}")
            return 1 if failed else 0
        if args.command == "list":
            index = load_index(engine)
            for entry in index["snapshots"]:
                current = " (current)" if index["current"].get(entry["membership"]) == entry["id"] else ""
                print(f"{entry['id']}{current}: {entry['membership']}, {entry['n_parts']} parts, "
                      f"{entry['created_utc']} - {entry['change_record']}")
            return 0
        print(json.dumps(diff(engine, args.first, args.second), indent=1))
        return 0
    except rp.SealError as exc:
        return rp.seal_config_error(exc)
    except (SnapshotError, rp.ReleaseError) as exc:
        print(f"results snapshot: refused, nothing written: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
