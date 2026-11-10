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
the one it supersedes and says what changed. ``verify`` re-hashes a snapshot's inputs in the current checkout.
It fails (exit 1) when the snapshot file changed, when a recorded part is missing or has different bytes, when
the directory holds a snapshot file the index does not list, and, for the snapshot the index marks current,
when the membership rule, the pinned manifest or a recorded input file differs from what it recorded: the
current snapshot must describe the checkout, and the remedy is a superseding snapshot. A superseded
snapshot reports those differences without failing. Parts that landed afterwards are reported, not failed,
because the evolving state is the catalogue's business.

The published statistics files are recorded as they stood, with the generation time and engine commit each
states for itself. A snapshot does not recompute them, and it does not claim they reproduce from its parts:
the collector also reads the site payload (``inputs.site_payload``), and a file may predate a part.

Snapshots read the engine's committed policy file whatever ``PW_RESULTS_POLICY`` says, so a preview policy
cannot be recorded under a membership's name.

  python scripts/results_snapshot.py create --id study-interim-20261110 --site ../patientwords \\
      --change "first snapshot: the membership as published since 2026-10-09"
  python scripts/results_snapshot.py verify --id study-interim-20261110
  python scripts/results_snapshot.py list
  python scripts/results_snapshot.py diff --from study-interim-20261110 --to exploratory-open-20261110
  python scripts/results_snapshot.py check-release --site ../patientwords              # before any push
  python scripts/results_snapshot.py check-release --site ../patientwords --published  # after the site push

The published statistics set (``STATISTICS_FILES``) is defined once, below. ``create --site`` records every
file of it. A snapshot that supersedes another also records which of those files changed between the two
site commits and, for the gallery payload, its ``summary.penalty`` block at both commits, read from git.

``check-release`` is the gate between the local commits of a publish and its pushes. It refuses (exit 1,
naming each problem) unless the snapshot is committed, current and verifying, its recorded engine commit is
in the engine HEAD, every file it records has the recorded sha256 at the site's HEAD commit, and every
published statistics file the site's HEAD changes relative to its base ref is one the snapshot records. A
changed data file that is neither in the statistics set nor in the list of files a snapshot does not version
is refused as unclassified. ``--published`` compares the remote site branch instead and, with ``--record``,
appends a publication record to the index. A snapshot with no publication record was created and not (yet)
published; the snapshot file itself is never edited to say so.

Creating a snapshot changes no published number. Changing which membership the collectors read is a separate,
reviewed edit of data/results_policy/policy.v1.json (its ``analysis_pin`` states the release condition).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:                                    # advisory locking is POSIX-only; without it writes are still atomic
    import fcntl
except ImportError:                     # pragma: no cover
    fcntl = None                        # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parent))

import results_policy as rp  # noqa: E402
from export_results_catalogue import CatalogueError, sealed_pair_keys  # noqa: E402

SCHEMA = "patientwords.analysis-snapshot/1"
INDEX_SCHEMA = "patientwords.analysis-snapshot-index/1"
SNAPSHOT_DIR = Path("data") / "analysis_snapshots"
ID_RE = re.compile(r"[a-z0-9][a-z0-9.-]{2,62}\Z")
RESERVED_IDS = frozenset({"index"})     # index.json is the index, not a snapshot
# ---------------------------------------------------------------- the published statistics set
# THE ONE DEFINITION. A published statistics file is a site data file that carries numbers measured on, or
# computed about, a model. ``create --site`` records the sha256 of every one of them (a file that does not
# exist is recorded as absent, never skipped silently), and ``check-release`` refuses a publish that changes
# one the snapshot does not record. Sources: the files the publish chain writes
# (.claude/skills/publish-site-data/SKILL.md) and the site's writer table (docs/agent_reference.md there,
# "Data contracts"). The value says how the file relates to the snapshot's inputs:
MEMBERSHIP_INPUTS = "membership_inputs"
TRACE_OUT_OTHER = "trace_out_outside_membership"
OTHER_LANE = "other_lane"
INPUT_RELATIONS = {
    MEMBERSHIP_INPUTS: "written by a collector that reads batch_summary parts through the analysis gate "
                       "(scripts/results_policy.py), or from such a collector's output; inputs.parts lists what "
                       "the default membership admits",
    TRACE_OUT_OTHER: "computed from trace_out/ without the analysis gate (batch summaries pooled by a script "
                     "that applies its own skip rule, lens summaries, raw lens runs, patching grids) or by an "
                     "export with no recorded writer; inputs.parts is not its input list, and the snapshot "
                     "records the published bytes only",
    OTHER_LANE: "computed from another lane's own record (data/advice/, data/petri/, data/jev/); the snapshot "
                "records the published bytes only, and that lane's record states its inputs",
}
STATISTICS_FILES: dict[str, str] = {
    # the eight files every snapshot up to study-interim-20261110 recorded
    "data/urgency_shift.json": MEMBERSHIP_INPUTS,          # urgency_shift.py --publish (chain step 2)
    "data/model_stats.json": MEMBERSHIP_INPUTS,            # paired_stats_rigor.py, from the collector's rows
    "data/simulated_scenarios.json": MEMBERSHIP_INPUTS,    # export_frontend_simulated.py (step 1); carries
                                                           # summary.penalty; steps 3b and 4 rewrite it in place
    "data/convergence.json": MEMBERSHIP_INPUTS,            # convergence_tracker.py, from the collector's rows
    "data/translation_scale.json": MEMBERSHIP_INPUTS,      # translation_scale.py (step 5)
    "data/tag_mass.json": TRACE_OUT_OTHER,                 # export_tag_mass.py (step 3); pools without the gate
    "data/retrace_consistency.json": TRACE_OUT_OTHER,      # retrace_consistency.py; pools without the gate
    "data/timeline.json": MEMBERSHIP_INPUTS,               # study_timeline.py
    # added 2026-11-10: the same measurements in other files
    "data/simulated_archive.json": MEMBERSHIP_INPUTS,      # export_archive.py (per pair and model)
    "data/simulated_archive.csv": MEMBERSHIP_INPUTS,
    "data/specialty_breakdown.json": MEMBERSHIP_INPUTS,    # specialty_breakdown.py, from the site's urgency
                                                           # rows and payload
    # lens, J-space and patching exports (chain step 3 and operator tools)
    "data/jlens_insights.json": TRACE_OUT_OTHER,
    "data/jlens_depth.json": TRACE_OUT_OTHER,
    "data/jlens_transport.json": TRACE_OUT_OTHER,
    "data/jlens_loglens.json": TRACE_OUT_OTHER,
    "data/jlens_swaps.json": TRACE_OUT_OTHER,
    "data/jspace.json": TRACE_OUT_OTHER,
    "data/patch_profile.json": TRACE_OUT_OTHER,            # patch_aggregate.py
    "data/dialects.json": TRACE_OUT_OTHER,                 # export_dialect_matrix.py, dialect_invariant_core.py
    # measured numbers whose writer scripts/README.md does not record (hand-run exports of earlier dates)
    "data/model_evaluations.json": TRACE_OUT_OTHER,
    "data/stress_pairs.json": TRACE_OUT_OTHER,             # pairs; export_stress_featured.py adds 'featured'
    "data/provenance.json": TRACE_OUT_OTHER,
    # the advice, Petri and Jev lanes (owner-run exports)
    "data/advice_scenarios.json": OTHER_LANE,
    "data/advice_scenarios_nat.json": OTHER_LANE,
    "data/advice_coding_sample.json": OTHER_LANE,
    "data/judge_agreement.json": OTHER_LANE,
    "data/jev_calibration.json": OTHER_LANE,
    "data/petri_register_drift.json": OTHER_LANE,
    "data/petri_multiturn_summary.json": OTHER_LANE,
    "data/petri_multiturn_conversations.json": OTHER_LANE,
}
SITE_OUTPUTS = tuple(STATISTICS_FILES)
# Site data a snapshot does NOT version, each with its reason. ``check-release`` passes a change to one of
# these without a snapshot and names it in the manifest. Everything else under data/ is unclassified, and a
# publish that changes an unclassified file is refused until the file is added to one of the two lists.
OUTSIDE_SNAPSHOT_DIRS: dict[str, str] = {
    "data/results_catalogue/": "the results catalogue: the evolving public record, rewritten whenever a run "
                               "lands; the open-results policy keeps it apart from the versioned statistics",
    "data/experiments/": "experiment bundles and their index: one experiment's record each, with its own "
                         "evidence class, execution state and input hashes; pooled under no analysis membership",
}
OUTSIDE_SNAPSHOT_FILES: dict[str, str] = {
    "data/drift_series.json": "the daily sentinel series: the Routine appends one dated reading of three frozen "
                              "pairs each cycle (routine section 3b) outside the publish chain; its rows carry "
                              "their own dates, and a snapshot per day would version an instrument check, not "
                              "an analysis",
    "data/display_vocab.json": "display vocabulary (token-cleaning rules); no measured number",
    "data/model_provenance.json": "hand-maintained on the site (no engine writer): per-model build information",
    "data/specialties.json": "hand-synced on the site from data/specialty_map.draft.json: a draft label map, "
                             "no measured number",
}
OUTSIDE_SNAPSHOT_SUFFIXES: dict[str, str] = {
    ".sample.json": "a synthetic development fixture (a page loads it only with ?sample=1); no measurement",
}
# The gallery payload's headline block. A superseding snapshot records it at both site commits.
PAYLOAD_PENALTY_POINTER = ("summary", "penalty")
# Site paths the publish chain writes. check-release refuses uncommitted changes under them.
SITE_PUBLISH_PATHS = ("data", "modes/simulated")
ENGINE_INPUTS = ("data/urgency_tiers.draft.json",)
# The collector fills rows from this site file as well as from trace_out/ (scripts/urgency_shift.py), so it
# is an input of the published statistics and is recorded as one.
SITE_PAYLOAD = "data/simulated_scenarios.json"
DEFAULT_SITE_BASE = "origin/main"       # the branch GitHub Pages serves, as last fetched
# What must equal HEAD for a snapshot to say its inputs are committed. trace_out/ is checked with untracked
# files included: a hosted part needs no pin, so an untracked one would otherwise enter the snapshot.
COMMITTED_INPUTS = ("trace_out", str(rp.RELEASE_MANIFEST), str(rp.POLICY_PATH), str(rp.LEDGER_PATH),
                    *ENGINE_INPUTS, "ops/dashboard.json", "data/simulated", "data/seal_allowlist.json")
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


def _run(root: Path, *argv: str) -> subprocess.CompletedProcess[bytes]:
    """One git command with its return code and raw bytes; callers decide what a failure means."""
    return subprocess.run(["git", "-C", str(root), *argv], capture_output=True)


def _commit(root: Path, ref: str) -> str | None:
    """The commit ``ref`` names in the repository at ``root``; None when it names none there."""
    if not ref or ref.startswith("-"):
        return None
    proc = _run(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return proc.stdout.decode().strip() if proc.returncode == 0 else None


def _bytes_at(root: Path, commit: str, rel: str) -> bytes | None:
    """A file's bytes in one commit, read from git and never from the working tree; None when absent."""
    proc = _run(root, "cat-file", "blob", f"{commit}:{rel}")
    return proc.stdout if proc.returncode == 0 else None


def _sha_at(root: Path, commit: str, rel: str) -> str | None:
    data = _bytes_at(root, commit, rel)
    return None if data is None else hashlib.sha256(data).hexdigest()


def _is_shallow(root: Path) -> bool:
    return _run(root, "rev-parse", "--is-shallow-repository").stdout.strip() == b"true"


def _raw_history(root: Path, start: str, state: dict[str, bool]) -> Iterator[str]:
    """``start`` and its ancestors, nearest first, from the parent lines of the commit objects on disk.

    git's own walks stop at the commits a shallow checkout's shallow file lists, including ones whose parents
    are on disk (a depth-limited fetch of a branch marks its head that way). This walk does not. It sets
    ``state['cut_off']`` when it reaches a parent that is not on disk: the history beyond was never fetched."""
    reader = subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE)
    assert reader.stdin is not None and reader.stdout is not None
    seen: set[str] = set()
    queue = [start]
    try:
        while queue:
            commit = queue.pop(0)
            if commit in seen:
                continue
            seen.add(commit)
            reader.stdin.write(commit.encode() + b"\n")
            reader.stdin.flush()
            header = reader.stdout.readline().split()
            if len(header) != 3 or header[1] != b"commit":
                state["cut_off"] = True
                continue
            body = reader.stdout.read(int(header[2]) + 1)
            yield commit
            for line in body.split(b"\n\n", 1)[0].splitlines():
                if line.startswith(b"parent "):
                    queue.append(line.split()[1].decode())
    finally:
        reader.stdin.close()
        reader.wait()


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool | None:
    """Whether ``ancestor`` is ``descendant`` or one of its ancestors. None means this checkout cannot say:
    it is shallow, and the walk over the commit objects reached history that was never fetched before it
    found ``ancestor``. In a full checkout the answer is git's own."""
    if _run(root, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0:
        return True
    if not _is_shallow(root):
        return False
    target, start = _commit(root, ancestor), _commit(root, descendant)
    if target is None or start is None:
        return False
    state: dict[str, bool] = {}
    if any(commit == target for commit in _raw_history(root, start, state)):
        return True
    return None if state.get("cut_off") else False


def _merge_base(root: Path, first: str, second: str) -> str | None:
    """A common ancestor of two commits: git's merge base, or in a shallow checkout where git finds none, the
    nearest ancestor of ``second`` that the commit objects on disk show to be an ancestor of ``first``. That
    one can be older than the true merge base, never newer, so a diff taken from it lists at least the files
    a diff from the true one would."""
    proc = _run(root, "merge-base", first, second)
    if proc.returncode == 0:
        return proc.stdout.decode().strip()
    if not _is_shallow(root):
        return None
    of_first = set(_raw_history(root, first, {}))
    return next((commit for commit in _raw_history(root, second, {}) if commit in of_first), None)


def _ancestry_problem(root: Path, what: str, ancestor: str, descendant: str, descendant_name: str,
                      remedy: str) -> str | None:
    """The refusal text when ``ancestor`` is not shown to be in ``descendant``'s history; None when it is."""
    answer = _is_ancestor(root, ancestor, descendant)
    if answer:
        return None
    if answer is None:
        return (f"{what} ({ancestor[:12]}) cannot be shown to be in {descendant_name} ({descendant[:12]}): {root} "
                "is a shallow checkout whose history ends before it. Deepen it (git fetch --deepen=<n> origin "
                "<branch>) and run the check again")
    return f"{what} ({ancestor[:12]}) is not an ancestor of {descendant_name} ({descendant[:12]}); {remedy}"


def _changed_paths(root: Path, first: str, second: str, *paths: str) -> list[str]:
    """Paths that differ between two commits' trees (a rename is a deletion and an addition)."""
    proc = _run(root, "diff", "--name-only", "--no-renames", "-z", first, second, "--", *paths)
    if proc.returncode:
        raise SnapshotError(f"git diff {first} {second} failed: {proc.stderr.decode().strip()}")
    return sorted(name for name in proc.stdout.decode().split("\0") if name)


def classify_site_path(rel: str) -> tuple[str, str]:
    """('statistics', input relation), ('outside', reason) or ('unclassified', '') for a path under data/."""
    if rel in STATISTICS_FILES:
        return "statistics", STATISTICS_FILES[rel]
    if rel in OUTSIDE_SNAPSHOT_FILES:
        return "outside", OUTSIDE_SNAPSHOT_FILES[rel]
    for prefix, reason in OUTSIDE_SNAPSHOT_DIRS.items():
        if rel.startswith(prefix):
            return "outside", reason
    if rel.count("/") == 1:                         # a suffix rule covers top-level data files only
        for suffix, reason in OUTSIDE_SNAPSHOT_SUFFIXES.items():
            if rel.endswith(suffix):
                return "outside", reason
    return "unclassified", ""


def committed_policy() -> rp.Policy:
    """The engine's own policy file. A snapshot never reads a ``PW_RESULTS_POLICY`` candidate."""
    if os.environ.get(rp.POLICY_ENV):
        print(f"results snapshot: {rp.POLICY_ENV} is set and is ignored here; a snapshot reads "
              f"{rp.POLICY_PATH}", file=sys.stderr)
    return rp.load_policy(rp.ENGINE / rp.POLICY_PATH)


def _stated_provenance(path: Path) -> dict[str, Any] | None:
    """What a published file says about its own generation; None when it says nothing or cannot be read."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    prov = doc.get("_provenance") if isinstance(doc, dict) else None
    if not isinstance(prov, dict):
        return None
    return {k: prov.get(k) for k in ("generator", "engine_sha", "generated_utc") if k in prov}


@contextlib.contextmanager
def _locked(directory: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on the snapshot directory for one read-modify-write of the index."""
    directory.mkdir(parents=True, exist_ok=True)
    if fcntl is None:                   # pragma: no cover
        yield
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


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
    policy = policy or committed_policy()
    rule = policy.membership(membership)
    if rule["purpose"] != "analysis":
        raise SnapshotError(f"{membership} is a display rule; a snapshot fixes an analysis membership")
    engine = engine.resolve()
    gate = rp.Gate(engine, membership=membership, policy=policy)
    seal_paths = seal_paths or {}
    # The catalogue's rule, shared so the two cannot disagree: a pair sealed in any run is withheld in every
    # run. Deciding row by row counted rows of pairs that are sealed only through another run's prompt.
    try:
        sealed_keys = sealed_pair_keys(
            engine, policy, rp.load_manifest(engine) if (engine / rp.RELEASE_MANIFEST).exists() else None,
            rp.load_ledger(engine), seal_paths)
    except CatalogueError as exc:
        raise SnapshotError(str(exc)) from exc
    parts: dict[str, str] = {}
    by_backend: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    rows_by_model: Counter[str] = Counter()
    sealed_by_model: Counter[str] = Counter()
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
            if (stem, result.get("index")) in sealed_keys:
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
        "evidence_status": "interim analysis of the exploration split; rows at sealed Tier B holdout pairs "
                           "(a pair sealed in any run is sealed in every run) are in no input row count "
                           "below and the confirmatory endpoint has not been run",
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
        in_git = (site / ".git").exists()
        uncommitted = (_git(site, "status", "--porcelain", "--", *SITE_OUTPUTS).strip() if in_git else None)
        body["inputs"]["site_payload"] = {
            "path": SITE_PAYLOAD, "sha256": _sha(site / SITE_PAYLOAD),
            "role": "the collector (scripts/urgency_shift.py) also takes rows from this site file, including "
                    "at keys whose engine part is not in 'parts'; it prints that count per model. Those rows "
                    "are inputs of the published statistics that the part list does not cover.",
        }
        body["outputs"] = {
            "relation": "each published file as it stood when the snapshot was created: its sha256 and the "
                        "generation time and engine commit the file states for itself. Recorded, not "
                        "recomputed. A file can predate parts listed above; reproduces_from_inputs says "
                        "whether anyone checked.",
            "reproduces_from_inputs": "not_checked",
            "site_commit": _git(site, "rev-parse", "HEAD").strip() if in_git else None,
            "files_committed": (not uncommitted) if in_git else None,
            "files": {rel: _sha(site / rel) for rel in SITE_OUTPUTS},
            "stated_provenance": {rel: _stated_provenance(site / rel) for rel in SITE_OUTPUTS},
            "statistics_set": {"files": dict(STATISTICS_FILES), "input_relations": dict(INPUT_RELATIONS),
                               "note": "inputs.parts are the inputs of the membership_inputs files only; "
                                       "every other file is recorded as published bytes"},
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
    if (not isinstance(doc, dict) or doc.get("schema") != INDEX_SCHEMA
            or not isinstance(doc.get("snapshots"), list) or not isinstance(doc.get("current"), dict)):
        raise SnapshotError(f"{path} is not a {INDEX_SCHEMA} index")
    return doc


def unindexed_files(engine: Path) -> list[str]:
    """Snapshot-directory JSON files the index does not list. One exists only after an interrupted
    ``create`` or a hand edit; ``verify`` and ``list`` report it instead of passing over it."""
    directory = engine / SNAPSHOT_DIR
    known = {f"{entry['id']}.json" for entry in load_index(engine)["snapshots"]} | {"index.json"}
    return sorted(p.name for p in directory.glob("*.json") if p.name not in known) if directory.is_dir() else []


def load_snapshot(engine: Path, snapshot_id: str) -> dict[str, Any]:
    path = engine / SNAPSHOT_DIR / f"{snapshot_id}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SnapshotError(f"no snapshot {snapshot_id!r} at {path}") from None
    except (OSError, ValueError) as exc:
        raise SnapshotError(f"{path} is unreadable ({type(exc).__name__}); a truncated snapshot file is "
                            "removed by hand only when the index does not list it") from None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or doc.get("id") != snapshot_id:
        raise SnapshotError(f"{path} is not snapshot {snapshot_id!r}")
    return doc


def publication_records(engine: Path, snapshot_id: str) -> list[dict[str, Any]]:
    """The index's publication records for one snapshot, oldest first. None means its release has not been
    recorded as published: the snapshot was created and its site bytes were never confirmed on the remote."""
    return [r for r in load_index(engine).get("publications", []) if r.get("id") == snapshot_id]


def _top_level_changes(before: bytes | None, after: bytes | None) -> list[str] | None:
    """Top-level keys at which two JSON objects differ; None when either side is not a JSON object."""
    try:
        a, b = json.loads(before or b""), json.loads(after or b"")
    except ValueError:
        return None
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    return sorted(k for k in set(a) | set(b) if a.get(k, _ABSENT) != b.get(k, _ABSENT))


def _pointer(data: bytes | None, keys: tuple[str, ...]) -> Any:
    """The value at ``keys`` in a JSON document's bytes; None when the file or the key is absent."""
    try:
        value: Any = json.loads(data or b"")
    except ValueError:
        return None
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def readable_predecessor(engine: Path, site: Path, index: dict[str, Any],
                         start: str | None) -> tuple[dict[str, Any] | None, str | None, list[dict[str, str]]]:
    """The nearest snapshot at or before ``start`` in the supersedes chain whose recorded site bytes a commit
    in the site repository holds, the commit, and the snapshots passed over with the reason for each.

    A snapshot's recorded site commit can be gone: a site push that was rejected and rebased leaves the
    recorded commit unreachable, and a later clone does not have it. The comparison then falls back to the
    snapshot before it. Candidates are the commits of the snapshot's publication records, newest first, then
    the commit the snapshot recorded; one is used only when every file the snapshot recorded has the recorded
    sha256 there."""
    passed: list[dict[str, str]] = []
    seen: set[str] = set()
    snapshot_id = start
    while snapshot_id and snapshot_id not in seen:
        seen.add(snapshot_id)
        doc = load_snapshot(engine, snapshot_id)
        outputs = doc.get("outputs") or {}
        recorded = outputs.get("files") or {}
        if not recorded:
            passed.append({"id": snapshot_id, "reason": "records no published files"})
        else:
            candidates = [r.get("site_commit") for r in reversed(index.get("publications", []))
                          if r.get("id") == snapshot_id] + [outputs.get("site_commit")]
            tried = []
            for commit in dict.fromkeys(c for c in candidates if c):
                if _commit(site, commit) and all(_sha_at(site, commit, rel) == want
                                                 for rel, want in recorded.items()):
                    return doc, commit, passed
                tried.append(commit)
            passed.append({"id": snapshot_id, "reason": "no commit in the site repository holds the bytes it "
                           f"recorded (tried {', '.join(tried) or 'none: it records no site commit'})"})
        snapshot_id = doc.get("supersedes")
    return None, None, passed


def change_record(engine: Path, site: Path, index: dict[str, Any], supersedes: str | None,
                  site_commit: str) -> dict[str, Any]:
    """What changed in the published statistics files between the superseded snapshot's site commit and
    ``site_commit``. Both sides are read from git; nothing is recomputed."""
    if supersedes is None:
        return {"compared_with": None, "reason": "no superseded snapshot"}
    before_doc, before_commit, passed = readable_predecessor(engine, site, index, supersedes)
    if before_doc is None or before_commit is None:
        raise SnapshotError(
            "the change record cannot be written: no snapshot in the chain from "
            f"{supersedes!r} has its recorded site bytes in {site} ("
            + "; ".join(f"{p['id']}: {p['reason']}" for p in passed)
            + f"). Fetch the commit (git -C {site} fetch origin <commit>) and run create again.")
    files: dict[str, Any] = {}
    for rel in STATISTICS_FILES:
        before, after = _bytes_at(site, before_commit, rel), _bytes_at(site, site_commit, rel)
        if before == after:
            continue
        files[rel] = {
            "sha256_before": None if before is None else hashlib.sha256(before).hexdigest(),
            "sha256_after": None if after is None else hashlib.sha256(after).hexdigest(),
            "changed_top_level_keys": _top_level_changes(before, after) if rel.endswith(".json") else None,
        }
    penalty_before = _pointer(_bytes_at(site, before_commit, SITE_PAYLOAD), PAYLOAD_PENALTY_POINTER)
    penalty_after = _pointer(_bytes_at(site, site_commit, SITE_PAYLOAD), PAYLOAD_PENALTY_POINTER)
    return {
        "compared_with": before_doc["id"],
        "site_commit_before": before_commit,
        "site_commit_after": site_commit,
        "snapshots_passed_over": passed,
        "source": "the bytes of each file in the two site commits, read with git; nothing recomputed",
        "files": files,
        "not_recorded_by_compared_snapshot": sorted(set(STATISTICS_FILES)
                                                    - set((before_doc.get("outputs") or {}).get("files") or {})),
        "payload_summary_penalty": {
            "path": SITE_PAYLOAD, "pointer": "/" + "/".join(PAYLOAD_PENALTY_POINTER),
            "before": penalty_before, "after": penalty_after, "changed": penalty_before != penalty_after,
            "note": "the payload's own headline block at each commit, as the exporter wrote it; the "
                    "claim-grade estimate is data/model_stats.json",
        },
    }


_ABSENT = object()

# Top-level keys that only the site copy of the statistics file carries: paired_stats_rigor.py adds them when
# it writes into a site checkout, so a recomputation made with --site '' never has them. They are reported as
# keys_only_in_published and are the only one-sided keys that do not count as a difference.
SITE_ONLY_STATISTICS_KEYS = frozenset({"below_floor", "claims", "models_meta", "site_floor_n_phrases"})


def _differences(published: Any, recomputed: Any, prefix: str = "") -> list[str]:
    """JSON-pointer-like paths at which two documents differ. A key present on one side only is a difference
    at every nesting level: a recomputation that dropped a model or a statistic must not read as identical."""
    if isinstance(published, dict) and isinstance(recomputed, dict):
        out: list[str] = []
        for key in sorted(set(published) | set(recomputed), key=str):
            out.extend(_differences(published.get(key, _ABSENT), recomputed.get(key, _ABSENT), f"{prefix}/{key}"))
        return out
    if published is _ABSENT:
        return [f"{prefix} (only in the recomputed file)"]
    if recomputed is _ABSENT:
        return [f"{prefix} (only in the published file)"]
    return [] if published == recomputed else [prefix or "/"]


def reproduction_check(site: Path, recomputed: Path) -> dict[str, Any]:
    """Compare the published statistics file with one the operator has just recomputed from this checkout
    (``paired_stats_rigor.py --site ''``). The snapshot records the result; it does not run the bootstrap."""
    try:
        published_doc = json.loads((site / "data" / "model_stats.json").read_text(encoding="utf-8"))
        recomputed_doc = json.loads(recomputed.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SnapshotError(f"the reproduction check cannot read its files: {exc}") from exc
    for key in ("seed", "boot"):
        if published_doc.get(key) != recomputed_doc.get(key):
            raise SnapshotError(f"the recomputed statistics use {key} {recomputed_doc.get(key)!r}, the published "
                                f"file {published_doc.get(key)!r}; the comparison would not be like for like")
    if not isinstance(published_doc, dict) or not isinstance(recomputed_doc, dict):
        raise SnapshotError("the reproduction check compares two JSON objects")
    ignore = {"_provenance", "source"}
    site_only = sorted((set(published_doc) - set(recomputed_doc)) & SITE_ONLY_STATISTICS_KEYS)
    skip = ignore | set(site_only)
    differing = _differences({k: v for k, v in published_doc.items() if k not in skip},
                             {k: v for k, v in recomputed_doc.items() if k not in ignore})
    return {"checked": True, "file": "data/model_stats.json", "identical": not differing,
            "differing_fields": differing, "recomputed_sha256": _sha(recomputed),
            "keys_only_in_published": site_only,
            "method": "scripts/urgency_shift.py then scripts/paired_stats_rigor.py --site '' on this checkout "
                      "with the published seed and resample count; every field of both files compared, a "
                      "field on one side only counted as a difference, except the generation stamp and the "
                      "listed top-level keys that only the site copy carries"}


def create(engine: Path, snapshot_id: str, membership: str, change: str, *, site: Path | None = None,
           supersedes: str | None = None, allow_dirty: bool = False, created_utc: str | None = None,
           seal_paths: dict[str, Any] | None = None, recomputed_statistics: Path | None = None) -> Path:
    if not ID_RE.fullmatch(snapshot_id) or snapshot_id in RESERVED_IDS:
        raise SnapshotError("a snapshot id is 3-63 characters of lowercase letters, digits, '.' and '-', and "
                            "is not 'index'")
    if not change.strip():
        raise SnapshotError("a snapshot needs a change record: one sentence saying what it is or what changed")
    if recomputed_statistics is not None and site is None:
        raise SnapshotError("--recomputed-statistics compares against the site's file and needs --site")
    engine = engine.resolve()
    directory = engine / SNAPSHOT_DIR
    path = directory / f"{snapshot_id}.json"
    with _locked(directory):
        if path.exists():
            raise SnapshotError(f"{path} exists; a snapshot is never rewritten. Use a new id and --supersedes.")
        index = load_index(engine)
        stray = unindexed_files(engine)
        if stray:
            raise SnapshotError(f"{directory} holds file(s) the index does not list: {', '.join(stray)}. An "
                                "interrupted create leaves one; remove it before creating another snapshot.")
        by_id = {entry["id"]: entry for entry in index["snapshots"]}
        current = index["current"].get(membership)
        if supersedes is not None:
            if supersedes not in by_id:
                raise SnapshotError(f"--supersedes names {supersedes!r}, which is not a recorded snapshot")
            if by_id[supersedes]["membership"] != membership:
                raise SnapshotError(f"--supersedes names {supersedes!r}, a snapshot of "
                                    f"{by_id[supersedes]['membership']}; a snapshot supersedes one of its own "
                                    "membership")
        commit, dirty = None, None
        if (engine / ".git").exists():
            commit = _git(engine, "rev-parse", "HEAD").strip()
            dirty = _git(engine, "status", "--porcelain", "--untracked-files=all", "--",
                         *COMMITTED_INPUTS).strip()
            if dirty and not allow_dirty:
                raise SnapshotError("inputs differ from HEAD (untracked files included), so the snapshot would "
                                    "not describe committed bytes; commit or restore them first:\n" + dirty)
        body = build(engine, membership, site=site, seal_paths=seal_paths)
        if site is not None and body["outputs"]["files_committed"] is False and not allow_dirty:
            raise SnapshotError("the site's statistics files differ from its HEAD, so the recorded site commit "
                                "would not contain the recorded bytes; commit the publish first")
        if recomputed_statistics is not None:
            body["outputs"]["reproduces_from_inputs"] = reproduction_check(site.resolve(), recomputed_statistics)
        preview = bool(dirty) or (site is not None and body["outputs"]["files_committed"] is False)
        if not preview and current is not None and supersedes != current:
            raise SnapshotError(f"{membership} already has a current snapshot, {current!r}; a new one names it "
                                "with --supersedes so the chain of versions has no gap")
        if site is not None:
            site_commit = body["outputs"]["site_commit"]
            if site_commit is None:
                changes: dict[str, Any] = {"compared_with": None,
                                           "reason": "the site directory is not a git checkout; nothing was read"}
            elif preview:
                changes = {"compared_with": None, "reason": "a preview of uncommitted bytes; nothing was read"}
            else:
                changes = change_record(engine, site.resolve(), index, supersedes, site_commit)
            body["outputs"]["changed_since_superseded"] = changes
        doc = {"schema": SCHEMA, "id": snapshot_id,
               "created_utc": created_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "engine_commit": commit, "inputs_committed": (not dirty) if commit else None,
               "supersedes": supersedes, "change_record": change.strip(),
               **{k: v for k, v in body.items() if k != "schema"}}
        # Written under a temporary name and linked into place only when complete, so an interrupted write
        # cannot leave a truncated file under the snapshot's id; the link refuses an existing id.
        tmp = directory / f".{snapshot_id}.{os.getpid()}.tmp"
        try:
            tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
            try:
                os.link(tmp, path)
            except FileExistsError:
                raise SnapshotError(f"{path} exists; a snapshot is never rewritten.") from None
        finally:
            tmp.unlink(missing_ok=True)
        entry = {"id": snapshot_id, "created_utc": doc["created_utc"], "membership": membership,
                 "engine_commit": commit, "supersedes": supersedes,
                 "n_parts": doc["inputs"]["n_parts"], "change_record": doc["change_record"],
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if preview:
            # A preview records uncommitted bytes. It is listed and never becomes the current snapshot.
            entry["preview"] = True
        else:
            index["current"][membership] = snapshot_id
        index["snapshots"].append(entry)
        index_tmp = directory / f".index.{os.getpid()}.tmp"
        index_tmp.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
        index_tmp.replace(_index_path(engine))
    return path


def verify(engine: Path, snapshot_id: str) -> dict[str, Any]:
    """Compare a snapshot's recorded inputs with the checkout.

    ``ok`` is False when the snapshot file changed since it was indexed, or a recorded part is missing or
    has different bytes. For the snapshot the index marks current, ``ok`` is also False when the membership
    rule, the pinned manifest or a recorded input file differs from the record (``stale``): the current
    snapshot has to describe the checkout. A superseded or preview snapshot reports ``config_changed`` only."""
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
    policy = committed_policy()
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
    config_changed: list[str] = []
    try:
        rule_now: Any = dict(policy.membership(doc["membership"]))
    except (rp.PolicyError, KeyError):
        rule_now = None
    if rule_now != doc.get("membership_rule"):
        config_changed.append("membership rule")
    manifest = doc["inputs"].get("logits_manifest")
    if manifest and _sha(engine / manifest["path"]) != manifest["sha256"]:
        config_changed.append(manifest["path"])
    for rel, want in (doc["inputs"].get("files") or {}).items():
        if _sha(engine / rel) != want:
            config_changed.append(rel)
    is_current = index["current"].get(doc["membership"]) == snapshot_id
    intact = entry is not None and entry.get("sha256") == file_sha and not missing and not changed
    stale = is_current and bool(config_changed)
    return {"id": snapshot_id, "snapshot_file_unchanged": entry is not None and entry.get("sha256") == file_sha,
            "indexed": entry is not None, "current": is_current, "missing": missing, "changed": changed,
            "admitted_now_but_not_in_snapshot": landed_since,
            "config_changed": config_changed, "stale": stale,
            "policy_changed_since": policy.version != doc["policy"]["version"]
            or hashlib.sha256(policy.path.read_bytes()).hexdigest() != doc["policy"]["sha256"],
            "ok": intact and not stale}


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


def _resolve_release_snapshot(engine: Path, snapshot_id: str | None) -> tuple[str, dict[str, Any], dict[str, Any]]:
    index = load_index(engine)
    if snapshot_id is None:
        membership = committed_policy().default_membership
        snapshot_id = index["current"].get(membership)
        if snapshot_id is None:
            raise SnapshotError(f"{membership} has no current snapshot; create one, or name one with --id")
    return snapshot_id, load_snapshot(engine, snapshot_id), index


def _manifest_head(engine: Path, snapshot_id: str, doc: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    entry = next((e for e in index["snapshots"] if e["id"] == snapshot_id), None)
    outputs = doc.get("outputs") or {}
    return {
        "snapshot": {"id": snapshot_id, "membership": doc["membership"], "supersedes": doc.get("supersedes"),
                     "sha256": _sha(engine / SNAPSHOT_DIR / f"{snapshot_id}.json"),
                     "indexed": entry is not None, "preview": bool(entry and entry.get("preview")),
                     "current": index["current"].get(doc["membership"]) == snapshot_id,
                     "recorded_engine_commit": doc.get("engine_commit"),
                     "recorded_site_commit": outputs.get("site_commit")},
        "outputs": [{"path": rel, "sha256": sha} for rel, sha in (outputs.get("files") or {}).items()],
        "publications": [r for r in index.get("publications", []) if r.get("id") == snapshot_id],
    }


def check_release(engine: Path, site: Path, snapshot_id: str | None = None, *,
                  site_base: str = DEFAULT_SITE_BASE) -> dict[str, Any]:
    """The gate between a publish's local commits and its pushes. Reads only; pushes and fetches nothing.

    ``problems`` names every reason the release may not be pushed, and ``ok`` is True only when it is empty:

    * the engine tree differs from HEAD under the snapshot's inputs or the snapshot directory;
    * the snapshot is not indexed, is a preview, is not the current snapshot of its membership, is not the
      file HEAD holds, or does not verify;
    * the engine commit the snapshot records is not an ancestor of the engine HEAD;
    * the site has an uncommitted change under data/ or modes/simulated/;
    * a file the snapshot records does not have the recorded sha256 in the site's HEAD commit;
    * the site's HEAD changes a published statistics file the snapshot does not record, or a data file that
      is in neither the statistics set nor the list of files a snapshot does not version;
    * the base ref changed a published statistics file after the commit the site's HEAD started from.

    The site commit a snapshot records is not compared with HEAD: a rejected site push is rebased and the
    commit id changes. The recorded sha256 values bind the release, and they are checked at HEAD."""
    engine, site = engine.resolve(), site.resolve()
    for root, name in ((engine, "engine"), (site, "site")):
        if _commit(root, "HEAD") is None:
            raise SnapshotError(f"{root} is not a git checkout with a commit; the release check reads the "
                                f"{name}'s HEAD commit")
    snapshot_id, doc, index = _resolve_release_snapshot(engine, snapshot_id)
    engine_head, site_head = _commit(engine, "HEAD"), _commit(site, "HEAD")
    assert engine_head and site_head
    manifest = _manifest_head(engine, snapshot_id, doc, index)
    problems: list[str] = []
    notes: list[str] = []
    snapshot_rel = (SNAPSHOT_DIR / f"{snapshot_id}.json").as_posix()
    index_rel = (SNAPSHOT_DIR / "index.json").as_posix()

    # ---- the engine side
    dirty = _git(engine, "status", "--porcelain", "--untracked-files=all", "--", *COMMITTED_INPUTS).strip()
    if dirty:
        problems.append("the engine tree differs from HEAD under the snapshot's inputs (untracked files "
                        "included): " + "; ".join(dirty.splitlines()[:8]))
    dirty = _git(engine, "status", "--porcelain", "--untracked-files=all", "--", str(SNAPSHOT_DIR)).strip()
    if dirty:
        problems.append(f"{SNAPSHOT_DIR} differs from HEAD; commit the snapshot file and the index: "
                        + "; ".join(dirty.splitlines()[:8]))
    entry = next((e for e in index["snapshots"] if e["id"] == snapshot_id), None)
    if entry is None:
        problems.append(f"snapshot {snapshot_id} is not in the index")
    else:
        if entry.get("preview") or doc.get("inputs_committed") is False:
            problems.append(f"snapshot {snapshot_id} is a preview of uncommitted bytes; a release needs a "
                            "snapshot created from committed inputs")
        if _sha_at(engine, engine_head, snapshot_rel) != entry.get("sha256"):
            problems.append(f"the engine HEAD does not hold {snapshot_rel} with the sha256 the index records")
        if _sha_at(engine, engine_head, index_rel) != _sha(engine / index_rel):
            problems.append(f"the engine HEAD does not hold the index file as it is on disk ({index_rel})")
    if not manifest["snapshot"]["current"]:
        problems.append(f"snapshot {snapshot_id} is not the current snapshot of {doc['membership']} "
                        f"({index['current'].get(doc['membership'])!r} is); a release is checked against the "
                        "current one")
    report = verify(engine, snapshot_id)
    if not report["ok"]:
        problems.append(
            f"snapshot {snapshot_id} does not verify: {len(report['missing'])} recorded part(s) missing, "
            f"{len(report['changed'])} changed, snapshot file unchanged {report['snapshot_file_unchanged']}, "
            f"recorded rule or input files that differ now: {', '.join(report['config_changed']) or 'none'}")
    if unindexed_files(engine):
        problems.append(f"{SNAPSHOT_DIR} holds file(s) the index does not list: {', '.join(unindexed_files(engine))}")
    recorded_engine = doc.get("engine_commit")
    if not recorded_engine or _commit(engine, recorded_engine) is None:
        problems.append(f"the engine commit the snapshot records ({recorded_engine}) is not in this repository")
    else:
        problem = _ancestry_problem(
            engine, "the engine commit the snapshot records", recorded_engine, engine_head, "the engine HEAD",
            "a rebase replaced it. Bring the remote in with a merge (git pull --no-rebase), or create a "
            "superseding snapshot")
        if problem:
            problems.append(problem)

    # ---- the site side: the recorded bytes, read from the HEAD commit
    dirty = _git(site, "status", "--porcelain", "--untracked-files=all", "--", *SITE_PUBLISH_PATHS).strip()
    if dirty:
        problems.append("the site has uncommitted changes under " + " or ".join(SITE_PUBLISH_PATHS) + ": "
                        + "; ".join(dirty.splitlines()[:8]))
    outputs = doc.get("outputs") or {}
    recorded: dict[str, str | None] = outputs.get("files") or {}
    if not recorded:
        problems.append(f"snapshot {snapshot_id} records no published files (it was created without --site)")
    if outputs and outputs.get("files_committed") is not True:
        problems.append(f"snapshot {snapshot_id} recorded site files that were not committed "
                        f"(files_committed: {outputs.get('files_committed')!r})")
    for rel, want in recorded.items():
        got = _sha_at(site, site_head, rel)
        if got != want:
            problems.append(f"{rel} at the site HEAD has sha256 {got or 'absent'}; the snapshot records "
                            f"{want or 'absent'}. A snapshot is never edited: create a superseding one from "
                            "the committed site (create --supersedes ... --site ...)")
    if recorded and outputs.get("site_commit") != site_head:
        notes.append(f"the site HEAD ({site_head[:12]}) is not the commit the snapshot recorded "
                     f"({str(outputs.get('site_commit'))[:12]}); the recorded sha256 values bind the release "
                     "and were compared at HEAD")

    # ---- coverage: what this release changes on the site
    base_commit = _commit(site, site_base)
    changed: dict[str, Any] = {"statistics": [], "outside_snapshot": [], "unclassified": [],
                               "on_base_since_merge_base": []}
    merge_base = None
    if base_commit is None:
        problems.append(f"the site has no commit at the base ref {site_base!r}; fetch it "
                        f"(git -C {site} fetch origin) or name the published branch with --site-base")
    else:
        merge_base = _merge_base(site, base_commit, site_head)
        if merge_base is None:
            problems.append(f"the site HEAD and {site_base} share no history in this checkout, so the changed "
                            "files cannot be listed (a shallow checkout can hide it: git fetch --deepen=<n>)")
        else:
            for rel in _changed_paths(site, merge_base, site_head, "data"):
                kind, why = classify_site_path(rel)
                if kind == "statistics":
                    changed["statistics"].append(rel)
                    if rel not in recorded:
                        problems.append(f"{rel} is a published statistics file this release changes, and "
                                        f"snapshot {snapshot_id} does not record it; create a superseding "
                                        "snapshot (create --supersedes ... --site ...)")
                elif kind == "outside":
                    changed["outside_snapshot"].append({"path": rel, "reason": why})
                else:
                    changed["unclassified"].append(rel)
                    problems.append(f"{rel} is changed by this release and is not classified: add it to "
                                    "STATISTICS_FILES or to the OUTSIDE_SNAPSHOT lists in "
                                    "scripts/results_snapshot.py, with its reason, in a reviewed change")
            if merge_base != base_commit:
                notes.append(f"{site_base} ({base_commit[:12]}) has commits the site HEAD does not contain; "
                             f"the changed files are listed from the merge base ({merge_base[:12]}), and a "
                             "direct push needs the base brought in first")
                for rel in _changed_paths(site, merge_base, base_commit, "data"):
                    changed["on_base_since_merge_base"].append(rel)
                    if classify_site_path(rel)[0] == "statistics":
                        problems.append(f"{site_base} changed the published statistics file {rel} after the "
                                        "merge base: another publish landed. Bring it in (git pull --rebase "
                                        "on the site), re-run the check, and create a superseding snapshot "
                                        "if a recorded sha256 no longer holds")
    return {"check": "pre-push", "ok": not problems, "problems": problems, "notes": notes, **manifest,
            "engine": {"commit": engine_head},
            "site": {"commit": site_head, "base_ref": site_base, "base_commit": base_commit,
                     "merge_base": merge_base},
            "changed": changed,
            "snapshot_required": bool(changed["statistics"]),
            "verify": {k: report[k] for k in ("ok", "stale", "config_changed", "policy_changed_since")}}


def _fetch(root: Path, ref: str) -> None:
    remote, _, branch = ref.partition("/")
    if not branch:
        raise SnapshotError(f"{ref!r} is not a remote-tracking ref of the form <remote>/<branch>")
    proc = _run(root, "fetch", "--quiet", remote, branch)
    if proc.returncode:
        raise SnapshotError(f"git -C {root} fetch {remote} {branch} failed: {proc.stderr.decode().strip()}; "
                            "nothing was compared")


def check_published(engine: Path, site: Path, snapshot_id: str | None = None, *,
                    site_ref: str = DEFAULT_SITE_BASE, engine_ref: str = "origin/main",
                    at: str | None = None, fetch: bool = True) -> dict[str, Any]:
    """The check after the pushes: does the published site branch hold the bytes the snapshot records, and
    does the published engine branch hold the snapshot?

    Compares every recorded file in the commit ``site_ref`` names (after fetching it, unless ``fetch`` is
    False) with the recorded sha256. ``at`` names an earlier commit of that branch instead, for recording a
    publication that a later publish has since replaced; it must be an ancestor of ``site_ref``. On the
    engine side the snapshot file at ``engine_ref`` must have the sha256 the index records, and the engine
    commit the snapshot records must be an ancestor of ``engine_ref``. The local HEADs are not read, so a
    site commit whose id changed in a rebase or a merge is judged by its bytes."""
    engine, site = engine.resolve(), site.resolve()
    snapshot_id, doc, index = _resolve_release_snapshot(engine, snapshot_id)
    if fetch:
        _fetch(site, site_ref)
        _fetch(engine, engine_ref)
    manifest = _manifest_head(engine, snapshot_id, doc, index)
    problems: list[str] = []
    entry = next((e for e in index["snapshots"] if e["id"] == snapshot_id), None)
    if entry is None or entry.get("preview"):
        problems.append(f"snapshot {snapshot_id} is {'a preview' if entry else 'not in the index'}; only an "
                        "indexed snapshot of committed inputs can be recorded as published")
    site_commit = _commit(site, site_ref)
    if site_commit is None:
        problems.append(f"the site has no commit at {site_ref!r}")
    elif at is not None:
        at_commit = _commit(site, at)
        problem = (f"{at!r} names no commit in the site repository" if at_commit is None else
                   _ancestry_problem(site, f"the commit --at names ({at})", at_commit, site_commit, site_ref,
                                     "a publication is a commit of the published branch"))
        if problem:
            problems.append(problem)
            site_commit = None
        else:
            site_commit = at_commit
    recorded: dict[str, str | None] = (doc.get("outputs") or {}).get("files") or {}
    if not recorded:
        problems.append(f"snapshot {snapshot_id} records no published files (it was created without --site)")
    mismatched: list[str] = []
    if site_commit is not None:
        for rel, want in recorded.items():
            got = _sha_at(site, site_commit, rel)
            if got != want:
                mismatched.append(rel)
                problems.append(f"{rel} at {site_ref if at is None else at} ({site_commit[:12]}) has sha256 "
                                f"{got or 'absent'}; the snapshot records {want or 'absent'}")
    engine_commit = _commit(engine, engine_ref)
    snapshot_rel = (SNAPSHOT_DIR / f"{snapshot_id}.json").as_posix()
    if engine_commit is None:
        problems.append(f"the engine has no commit at {engine_ref!r}")
    else:
        if entry is not None and _sha_at(engine, engine_commit, snapshot_rel) != entry.get("sha256"):
            problems.append(f"{engine_ref} ({engine_commit[:12]}) does not hold {snapshot_rel} with the sha256 "
                            "the index records: the snapshot commit has not been pushed there")
        recorded_engine = doc.get("engine_commit")
        problem = (f"the engine commit the snapshot records ({recorded_engine}) is not in this repository"
                   if not recorded_engine or _commit(engine, recorded_engine) is None else
                   _ancestry_problem(engine, "the engine commit the snapshot records", recorded_engine,
                                     engine_commit, engine_ref, "the commit the snapshot was created at has "
                                     "not been pushed there"))
        if problem:
            problems.append(problem)
    return {"check": "published", "ok": not problems, "problems": problems, "notes": [], **manifest,
            "engine": {"ref": engine_ref, "commit": engine_commit},
            "site": {"ref": site_ref, "commit": site_commit, "at": at},
            "mismatched": mismatched}


def record_publication(engine: Path, report: dict[str, Any], *, recorded_utc: str | None = None) -> bool:
    """Append a passing ``check_published`` report to the index's ``publications`` list. Returns False, and
    writes nothing, when the index already records this snapshot at this site commit. The snapshot file is
    not touched: the index is the append-only place where a release is marked as published."""
    if report.get("check") != "published" or not report.get("ok"):
        raise SnapshotError("only a passing --published check is recorded")
    engine = engine.resolve()
    directory = engine / SNAPSHOT_DIR
    record = {"id": report["snapshot"]["id"], "site_ref": report["site"]["ref"],
              "site_commit": report["site"]["commit"], "engine_ref": report["engine"]["ref"],
              "engine_commit": report["engine"]["commit"],
              "recorded_utc": recorded_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with _locked(directory):
        index = load_index(engine)
        publications = index.setdefault("publications", [])
        if any(r.get("id") == record["id"] and r.get("site_commit") == record["site_commit"]
               for r in publications):
            return False
        publications.append(record)
        index_tmp = directory / f".index.{os.getpid()}.tmp"
        index_tmp.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
        index_tmp.replace(_index_path(engine))
    return True


def _print_release(report: dict[str, Any]) -> None:
    snapshot = report["snapshot"]
    published = report["check"] == "published"
    print(f"release manifest ({'published' if published else 'pre-push'} check): snapshot {snapshot['id']} "
          f"(sha256 {snapshot['sha256']})")
    if published:
        print(f"  engine {report['engine']['ref']}: {report['engine']['commit']}")
        print(f"  site   {report['site']['ref']}: {report['site']['commit']}")
    else:
        print(f"  engine commit: {report['engine']['commit']} (snapshot recorded {snapshot['recorded_engine_commit']})")
        print(f"  site commit:   {report['site']['commit']} (snapshot recorded {snapshot['recorded_site_commit']}); "
              f"base {report['site']['base_ref']} {report['site']['base_commit']}")
    for item in report["outputs"]:
        print(f"  {item['sha256'] or 'absent':64}  {item['path']}")
    if not published:
        changed = report["changed"]
        print(f"  published statistics files this release changes: {len(changed['statistics'])}"
              + (f" ({', '.join(changed['statistics'])})" if changed["statistics"] else
                 " (none: no new snapshot is required)"))
        for item in changed["outside_snapshot"][:10]:
            print(f"  changed, not versioned by a snapshot: {item['path']}")
        if len(changed["outside_snapshot"]) > 10:
            print(f"  ... and {len(changed['outside_snapshot']) - 10} more file(s) not versioned by a snapshot")
    for record in report["publications"]:
        print(f"  publication recorded: site {record['site_commit']} on {record['site_ref']}, "
              f"{record['recorded_utc']}")
    if not report["publications"]:
        print("  no publication of this snapshot is recorded in the index")
    for note in report["notes"]:
        print(f"  note: {note}")
    for problem in report["problems"]:
        print(f"  REFUSED: {problem}")
    if published:
        print("published: the remote site branch holds the recorded bytes" if report["ok"] else
              "NOT PUBLISHED AS RECORDED: the remote does not hold what the snapshot records")
    else:
        print("release check passed: nothing was pushed by this command" if report["ok"] else
              f"release check FAILED with {len(report['problems'])} problem(s): push nothing")


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
    c.add_argument("--recomputed-statistics", default=None,
                   help="a model_stats file just recomputed from this checkout (paired_stats_rigor.py --site ''); "
                        "the snapshot records whether the published file equals it")
    c.add_argument("--allow-dirty", action="store_true",
                   help="record uncommitted inputs as a preview (inputs_committed: false); a preview is "
                        "listed and never becomes the current snapshot")
    v = sub.add_parser("verify", help="re-hash a snapshot's inputs")
    v.add_argument("--id", default=None, help="default: every indexed snapshot")
    sub.add_parser("list", help="list snapshots")
    d = sub.add_parser("diff", help="compare two snapshots' inputs")
    d.add_argument("--from", dest="first", required=True)
    d.add_argument("--to", dest="second", required=True)
    r = sub.add_parser("check-release", help="the gate before a publish's pushes; --published checks afterwards")
    r.add_argument("--id", default=None, help="default: the current snapshot of the default membership")
    r.add_argument("--site", required=True, help="frontend root (a git checkout)")
    r.add_argument("--site-base", default=DEFAULT_SITE_BASE,
                   help="the published site branch as a remote-tracking ref (default: %(default)s). Before the "
                        "push it is read as last fetched; with --published it is fetched first")
    r.add_argument("--published", action="store_true",
                   help="after the pushes: compare the remote site branch's files with the snapshot's hashes")
    r.add_argument("--engine-ref", default="origin/main",
                   help="with --published: the engine branch that must hold the snapshot (default: %(default)s)")
    r.add_argument("--at", default=None,
                   help="with --published: an earlier commit of the site branch to compare instead of its head")
    r.add_argument("--no-fetch", action="store_true", help="with --published: compare the refs as last fetched")
    r.add_argument("--record", action="store_true",
                   help="with --published: on success, append the publication to the index (commit it afterwards)")
    r.add_argument("--json", action="store_true", help="print the release manifest as JSON")
    args = parser.parse_args(argv)
    engine = Path(args.engine).resolve()
    try:
        if args.command == "create":
            membership = args.membership or committed_policy().default_membership
            path = create(engine, args.id, membership, args.change, supersedes=args.supersedes,
                          site=Path(args.site) if args.site else None, allow_dirty=args.allow_dirty,
                          recomputed_statistics=(Path(args.recomputed_statistics)
                                                 if args.recomputed_statistics else None))
            doc = json.loads(path.read_text(encoding="utf-8"))
            print(f"snapshot {args.id}: {doc['inputs']['n_parts']} parts under {membership} -> {path}")
            check = (doc.get("outputs") or {}).get("reproduces_from_inputs")
            if isinstance(check, dict):
                print("  published statistics equal the recomputed file" if check["identical"] else
                      f"  published statistics DIFFER from the recomputed file in {len(check['differing_fields'])} "
                      "field(s); the snapshot records which")
            elif check:
                print("  published statistics were not compared with a recomputation (--recomputed-statistics)")
            changes = (doc.get("outputs") or {}).get("changed_since_superseded") or {}
            if changes.get("compared_with"):
                print(f"  published statistics files changed since {changes['compared_with']}: "
                      f"{', '.join(changes['files']) or 'none'}")
                penalty = changes["payload_summary_penalty"]
                if penalty["changed"]:
                    print(f"  {penalty['path']} {penalty['pointer']}: {json.dumps(penalty['before'])} -> "
                          f"{json.dumps(penalty['after'])}")
            print("  creating the snapshot changed no file but its own; commit the snapshot file and data/analysis_snapshots/index.json,")
            print("  then run check-release before any push")
            return 0
        if args.command == "verify":
            ids = [args.id] if args.id else [e["id"] for e in load_index(engine)["snapshots"]]
            failed = False
            stray = unindexed_files(engine)
            if stray:
                failed = True
                print(f"FAILED - file(s) in {SNAPSHOT_DIR} that the index does not list: {', '.join(stray)}")
            for snapshot_id in ids:
                report = verify(engine, snapshot_id)
                failed = failed or not report["ok"]
                changed_config = ", ".join(report["config_changed"]) or "none"
                print(f"{snapshot_id}{' (current)' if report['current'] else ''}: "
                      f"{'OK' if report['ok'] else 'FAILED'} - missing {len(report['missing'])}, "
                      f"changed {len(report['changed'])}, snapshot file unchanged "
                      f"{report['snapshot_file_unchanged']}; admitted now but not in the snapshot "
                      f"{len(report['admitted_now_but_not_in_snapshot'])}; recorded rule or input files that "
                      f"differ now: {changed_config}; policy file text changed since "
                      f"{report['policy_changed_since']}")
                if report["stale"]:
                    print("  the current snapshot no longer describes this checkout; create a superseding one")
                for rel in (report["missing"] + report["changed"])[:20]:
                    print(f"  {rel}")
            return 1 if failed else 0
        if args.command == "check-release":
            if not args.published and (args.record or args.at or args.no_fetch):
                raise SnapshotError("--record, --at and --no-fetch belong to --published")
            if args.published:
                report = check_published(engine, Path(args.site), args.id, site_ref=args.site_base,
                                         engine_ref=args.engine_ref, at=args.at, fetch=not args.no_fetch)
                if args.record and report["ok"]:
                    report["recorded"] = record_publication(engine, report)
                    report["publications"] = publication_records(engine, report["snapshot"]["id"])
            else:
                report = check_release(engine, Path(args.site), args.id, site_base=args.site_base)
            if args.json:
                print(json.dumps(report, indent=1))
            else:
                _print_release(report)
                if report.get("recorded"):
                    print(f"  recorded in {SNAPSHOT_DIR / 'index.json'}; commit and push that file")
            return 0 if report["ok"] else 1
        if args.command == "list":
            index = load_index(engine)
            for name in unindexed_files(engine):
                print(f"NOT INDEXED: {name} (an interrupted create or a hand edit; verify fails until it is removed)")
            for entry in index["snapshots"]:
                current = " (current)" if index["current"].get(entry["membership"]) == entry["id"] else ""
                current += " (preview: uncommitted inputs)" if entry.get("preview") else ""
                published = [r for r in index.get("publications", []) if r.get("id") == entry["id"]]
                if published:
                    current += f" (published: site {str(published[-1].get('site_commit'))[:12]})"
                elif not entry.get("preview"):
                    current += " (no publication recorded)"
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
