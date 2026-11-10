"""Export a preview bundle (``patientwords.experiment-bundle/1``) from a collected run directory.

The bundle is the one file a browser preview reads: a protocol summary, plan totals, the per-family comparison
blocks, the capability rows the plan used, evidence labels, provenance hashes and limitations. It copies no
prompt text and no target text. It holds no clock value, so the same run directory gives the same bytes.

Fields added to version 1 on 2026-11-10 (second review round). Each is additive and optional in the schema, so
a reader of an earlier bundle finds them absent and a reader that ignores them is unaffected:

* ``protocol.families[].variant_inputs``: per variant, ``prompt_sha256``, ``token_sha256`` and ``n_tokens``,
  taken from the plan's tasks. Hashes and a count only; never prompt text. A family the protocol excludes has
  no task, so it has no ``variant_inputs``.
* ``comparisons[].comparisons[].ica.preprocessing_mode`` and ``preprocessing_read_from``: what the ICA payloads
  record under ``basis`` (``scripts/experiments/compare.py``, ``ica_block``).
* ``execution.counts.executed_attempts`` and ``execution.counts.reused_events``: the number of ``started`` and
  of ``reused`` lines in the run directory's journal. A task found complete by two later runs counts as two
  reuse events. These are counts of journal lines, not timings.
* ``execution.completed_under_superseded_inputs``: see ``scripts/experiments/store.py``.

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
# Added when the collected run shows the condition. The counts are in ``execution.counts`` and
# ``execution.by_state``; the rows are in ``execution.attempt_outcomes_differ`` and
# ``execution.completed_under_superseded_inputs``.
READY_NOT_COMPLETED = "ready_tasks_not_completed_see_execution_counts"
NOTHING_COMPLETED = "no_task_completed_so_no_value_was_computed"
OUTCOMES_DIFFER = "attempt_outcomes_differ_between_workers_see_execution"
SUPERSEDED_INPUTS = "completed_results_under_superseded_inputs_not_counted_see_execution"
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
        key = (task["spec"]["method"]["id"], capability["status"], task["planned_state"], task["reason"],
               capability["revision_match"])
        row = capability_rows.setdefault(key, {
            "method": task["spec"]["method"]["id"], "backend": task["spec"]["settings"]["backend"],
            "status": capability["status"], "evidence": capability["evidence"],
            "status_note": capability["status_note"], "declared_by": capability["declared_by"],
            # "exact": the row names the protocol's model revision. "row_revision_not_recorded": the row
            # records no revision. null: no row matched.
            "revision_match": capability["revision_match"],
            "planned_state": task["planned_state"], "reason": task["reason"], "tasks": 0})
        row["tasks"] += 1

    # Hashes and token counts per family and variant, from the plan's tasks. No prompt text is in a plan.
    variant_inputs: dict[str, dict[str, dict[str, Any]]] = {}
    for task in plan["tasks"]:
        spec = task["spec"]
        variant_inputs.setdefault(spec["family_id"], {})[spec["variant"]] = {
            "prompt_sha256": spec["input"]["prompt_sha256"], "token_sha256": spec["input"]["token_sha256"],
            "n_tokens": task["estimate"]["tokens"]}
    families = [{**family, "variant_inputs": {name: variant_inputs[family["family_id"]][name]
                                              for name in sorted(variant_inputs[family["family_id"]])}}
                if family["family_id"] in variant_inputs else dict(family) for family in summary["families"]]
    events = store.read_journal()
    journal_counts = {"executed_attempts": sum(1 for e in events if e.get("event") == "started"),
                      "reused_events": sum(1 for e in events if e.get("event") == "reused")}

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
    if not assembly["ready_complete"]:
        limitations.append(READY_NOT_COMPLETED)
    if assembly["by_state"]["completed"] == 0:
        limitations.append(NOTHING_COMPLETED)
    if assembly["uncertain"]:
        limitations.append("uncertain_attempts_present_see_execution")
    if assembly["attempt_outcomes_differ"]:
        limitations.append(OUTCOMES_DIFFER)
    if assembly["completed_under_superseded_inputs"]:
        limitations.append(SUPERSEDED_INPUTS)

    bundle = {
        "schema_version": BUNDLE_SCHEMA,
        "protocol": {
            **plan["protocol"], "synthetic": plan["synthetic"], "seed": plan["seed"],
            "replicates": plan["replicates"], "model": summary["model"],
            "input_settings": summary["input_settings"], "families": families,
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
            "by_state": assembly["by_state"], "counts": {**assembly["counts"], **journal_counts},
            "complete": assembly["complete"],
            "ready_complete": assembly["ready_complete"],
            "missing": assembly["missing"], "uncertain": assembly["uncertain"],
            "ended_line_missing": assembly["ended_line_missing"],
            "duplicate_identical": assembly["duplicate_identical"],
            "attempt_outcomes_differ": assembly["attempt_outcomes_differ"],
            "completed_under_superseded_inputs": assembly["completed_under_superseded_inputs"],
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
