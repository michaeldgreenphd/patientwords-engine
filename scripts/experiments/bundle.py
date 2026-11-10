"""Export a preview bundle (``patientwords.experiment-bundle/1``) from a collected run directory.

The bundle is the one file a browser preview reads: a protocol summary, plan totals, the per-family comparison
blocks, the capability rows the plan used, evidence labels, provenance hashes and limitations. It copies no
prompt text and no target text. It holds no clock value, so the same run directory gives the same bytes.

A bundle built from a synthetic protocol always lists ``synthetic_not_measurement``. It is a rendering input
for a preview and is not a publication artifact: its evidence block says ``not_published``.
"""
from __future__ import annotations

import platform
from typing import Any, Iterable

from scripts.experiments.common import BUNDLE_SCHEMA, digest, read_json, require_structure
from scripts.experiments.compare import compare_run
from scripts.experiments.store import TIMING_CAVEAT, RunStore

SYNTHETIC_LIMITATIONS = (
    "synthetic_not_measurement",
    "no_real_model_was_loaded_and_no_parity_with_one_was_tested",
    "fixture_timings_say_nothing_about_model_runs",
)
GENERAL_LIMITATIONS = (
    "no_statistic_computed_one_value_per_family_variant_replicate",
    "first_target_token_only_no_sequence_scoring",
    "blocks_are_separate_and_never_combined_into_one_score",
)


def build_bundle(run_dir: Any, *, allow_roots: Iterable[Any] = ()) -> dict[str, Any]:
    """The bundle document for a collected run directory. Reads only; the caller writes it."""
    store = RunStore(run_dir, allow_roots=allow_roots)
    comparison = compare_run(run_dir, allow_roots=allow_roots)
    collected, plan = store.read_collected(), store.read_plan()
    assembly, summary = collected["assembly"], plan["protocol_summary"]

    capability_rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for task in plan["tasks"]:
        capability = task["capability"]
        key = (task["spec"]["method"]["id"], capability["status"], task["planned_state"], task["reason"])
        row = capability_rows.setdefault(key, {
            "method": task["spec"]["method"]["id"], "backend": task["spec"]["settings"]["backend"],
            "status": capability["status"], "evidence": capability["evidence"],
            "status_note": capability["status_note"], "declared_by": capability["declared_by"],
            "planned_state": task["planned_state"], "reason": task["reason"], "tasks": 0})
        row["tasks"] += 1

    engine_commits, source_files = set(), {}
    for row in assembly["tasks"]:
        envelope = read_json(store.run_dir / row["envelope"]["path"])
        engine_commits.add(envelope["environment"]["source_commits"].get("engine"))
        source_files.update(envelope["environment"].get("source_files_sha256", {}))

    limitations = list(GENERAL_LIMITATIONS)
    if plan["synthetic"]:
        limitations = list(SYNTHETIC_LIMITATIONS) + limitations
    if not assembly["complete"]:
        limitations.append("incomplete_run_some_planned_tasks_have_no_envelope")
    if assembly["uncertain"]:
        limitations.append("uncertain_attempts_present_see_execution")

    bundle = {
        "schema_version": BUNDLE_SCHEMA,
        "protocol": {
            **plan["protocol"], "synthetic": plan["synthetic"], "seed": plan["seed"],
            "replicates": plan["replicates"], "model": summary["model"],
            "input_settings": summary["input_settings"], "families": summary["families"],
            "methods": summary["methods"], "comparisons": summary["comparisons"],
            "primary_endpoint": summary["primary_endpoint"], "excluded": plan["excluded"],
        },
        "evidence": {
            "evidence_class": plan["evidence"]["evidence_class"],
            "clinical_review": plan["evidence"]["clinical_review"],
            "visibility": plan["evidence"].get("visibility", "not_published" if plan["synthetic"] else None),
            "restriction_reasons": plan["evidence"].get("restriction_reasons", []),
            "analysis_memberships": plan["evidence"].get("analysis_memberships", []),
            "synthetic": plan["synthetic"],
        },
        "plan_totals": {**plan["totals"], "adapters": plan["adapters"], "estimate_notes": plan["estimate_notes"]},
        "execution": {
            "by_state": assembly["by_state"], "counts": assembly["counts"], "complete": assembly["complete"],
            "missing": assembly["missing"], "uncertain": assembly["uncertain"],
            "duplicate_identical": assembly["duplicate_identical"],
            "execution_guarantee": collected["execution_guarantee"],
            "timing_caveat": TIMING_CAVEAT,
        },
        "comparisons": comparison["families"],
        "methods_not_run": comparison["methods_not_run"],
        "sign_convention": comparison["sign_convention"],
        "block_rule": comparison["block_rule"],
        "statistics": comparison["statistics"],
        "capability_rows": [capability_rows[key] for key in sorted(capability_rows, key=str)],
        "provenance": {
            "digest_convention": "scripts.exploratory_methods.digest",
            "protocol_sha256": plan["protocol"]["sha256"],
            "plan_sha256": comparison["plan_sha256"],
            "assembly_sha256": collected["assembly_sha256"],
            "comparison_sha256": digest(comparison),
            "capability_matrix": plan["capability_matrix"],
            "engine_commits": sorted(c for c in engine_commits if c is not None),
            "engine_commit_not_recorded": None in engine_commits,
            "source_files_sha256": dict(sorted(source_files.items())),
            "packages": {"python": platform.python_version()},
            "payloads": [{"task_id": r["task_id"], "replicate": r["replicate"], "method": r["method"],
                          "kind": r["payload"]["kind"], "sha256": r["payload"]["sha256"]}
                         for r in assembly["tasks"] if r["payload"]],
        },
        "limitations": limitations,
    }
    require_structure(bundle, "bundle")
    return bundle
