"""Export a preview bundle (``patientwords.experiment-bundle/1``) from a collected run directory.

The bundle is the one file a browser preview reads: a protocol summary, plan totals, the per-family comparison
blocks, the capability rows the plan used, evidence labels, provenance hashes and limitations. It copies no
prompt text and no target text unless the explicit exports described below apply. It holds no clock value,
so the same run directory gives the same bytes.

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

Explicit prompt-text export (added 2026-11-10, optional in the schema). ``build_bundle`` writes
``protocol.families[].variant_text.<variant>`` (``prompt`` and ``prompt_sha256``) and
``protocol.families[].prompt_text_export`` only when all of these hold:

* the caller passes the protocol document (``bundle --protocol``), and its digest is the plan's protocol hash
  (``protocol_mismatch`` otherwise);
* the family's ``facts`` list holds the marker ``publication:prompt_text_approved`` (``PROMPT_TEXT_MARKER``).
  A family without the marker has no ``variant_text``. The marker is part of the protocol, so it is part of
  the protocol hash every task of the run is bound to;
* the family has tasks in the plan (an excluded family has none) and each prompt's SHA-256 is the hash the
  plan's tasks record for that variant (``prompt_hash`` otherwise);
* for a non-synthetic protocol: the evidence block says ``public`` with no restriction reason
  (``prompt_text_restricted`` otherwise), and the seal check that protocol validation applies passes again
  at export time for the family's legacy row and for every variant prompt (``holdout_refusal`` otherwise; a
  seal that cannot be evaluated raises ``SealError`` and nothing is written). A refusal names the family and
  the variant and never repeats text.

A synthetic protocol's placeholder text is exported under the same marker without a seal check, as protocol
validation does for it; the bundle stays ``synthetic_fixture`` and ``not_published``. ``variant_inputs`` is
unchanged and stays closed: a hash entry cannot hold text.

Explicit target-text export (added 2026-11-11, optional in the schema). A reader of a paired comparison needs
to know which word's probability moved. ``build_bundle`` writes ``protocol.families[].target_text`` and
``protocol.families[].target_text_export`` only when the family's ``facts`` list holds a second marker,
``publication:target_text_approved`` (``TARGET_TEXT_MARKER``), in addition to the prompt-text marker, and every
condition of the prompt-text export above holds. The prompt-text marker alone exports no target text, as
before. The target marker without the prompt marker is refused (``target_text_without_prompt_text``): a target
shown without its prompts has no reading. For a non-synthetic protocol the seal is also asked about each
target's text (``holdout_refusal``).

``target_text`` is keyed by target id: ``{"text", "n_tokens", "partial_token_endpoint"}``. ``text`` is the
protocol's own ``targets[].text``, copied; it is never derived from a token id. ``n_tokens`` is the length of
the protocol's ``targets[].token_ids``. ``partial_token_endpoint`` is true when the target spans more than one
token: the behaviour endpoint reads the first target token only (``first_target_token_only_no_sequence_scoring``
below), so the value shown for such a target is the probability of its first token and not of the whole text.
The text of that first token alone is not recorded anywhere and a page must not invent it.

A bundle built from a synthetic protocol always lists ``synthetic_not_measurement``. It is a rendering input
for a preview and is not a publication artifact: its evidence block says ``not_published``.
"""
from __future__ import annotations

import platform
from typing import Any, Callable, Iterable, Mapping

from scripts.experiments.common import (
    BUNDLE_SCHEMA, digest, prompt_digest, read_json, require, require_structure,
)
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
# The marker a protocol family carries in ``facts`` when its prompt text is approved for publication. The
# protocol schema is closed and has no dedicated field for this; ``facts`` is the per-family list of strings
# the existing validator accepts. See docs/experiment_interface/preview.md, *Prompt text*.
PROMPT_TEXT_MARKER = "publication:prompt_text_approved"
# The second marker, for the family's target text. It is honoured only together with the prompt-text marker.
TARGET_TEXT_MARKER = "publication:target_text_approved"
RowRestriction = Callable[[str | None, int | None, str | None], str | None]


def _default_row_restriction() -> RowRestriction:
    from scripts import results_policy

    return results_policy.row_restriction


def approved_prompt_text(protocol: Mapping[str, Any] | None, plan: Mapping[str, Any],
                         variant_inputs: Mapping[str, Mapping[str, Mapping[str, Any]]],
                         row_restriction: RowRestriction | None = None) -> dict[str, dict[str, Any]]:
    """``{family_id: {"variant_text": {...}, "prompt_text_export": {...}}}`` for the families whose prompt
    text may be written into a bundle. Empty when no protocol is passed or no family carries the marker. A
    family that also carries ``TARGET_TEXT_MARKER`` gets ``target_text`` and ``target_text_export`` as well.

    The rules are in this module's docstring. ``row_restriction`` defaults to
    ``scripts.results_policy.row_restriction``; tests pass a stub so that no sealed text is read. It is not
    called for a synthetic protocol.
    """
    if protocol is None:
        return {}
    require(isinstance(protocol, Mapping) and digest(dict(protocol)) == plan["protocol"]["sha256"],
            "protocol_mismatch", "The protocol passed for prompt-text export is not the protocol this run's plan "
            "was built from")
    marked = [family for family in protocol["case_families"] if PROMPT_TEXT_MARKER in family.get("facts", [])]
    target_only = sorted(family["family_id"] for family in protocol["case_families"]
                         if TARGET_TEXT_MARKER in family.get("facts", []) and family not in marked)
    require(not target_only, "target_text_without_prompt_text",
            f"{', '.join(target_only)}: the target-text marker is honoured only together with the prompt-text "
            "marker; a target shown without its prompts has no reading")
    if not marked:
        return {}
    synthetic = plan["synthetic"]
    if not synthetic:
        evidence = plan["evidence"]
        reasons = evidence.get("restriction_reasons", [])
        require(evidence.get("visibility") == "public" and not reasons, "prompt_text_restricted",
                f"Prompt text is exported only for a protocol whose evidence block says visibility 'public' "
                f"with no restriction reason; this one says {evidence.get('visibility')!r} with {len(reasons)} "
                "restriction reason(s)")
    check = None if synthetic else (row_restriction or _default_row_restriction())
    out: dict[str, dict[str, Any]] = {}
    for family in marked:
        family_id, variants = family["family_id"], family["variants"]
        if family_id not in variant_inputs:
            continue  # an excluded family has no task; nothing of it was run, so nothing of it is exported
        if check is not None:
            join = family.get("legacy_join")
            if join is not None:
                restriction = check(join["batch"], join["batch_index"], variants.get("clinical", {}).get("prompt"))
                require(restriction is None, "holdout_refusal",
                        f"{family_id}: legacy row ({join['batch']}, {join['batch_index']}) is restricted: "
                        f"{restriction}; its prompt text is not exported")
            for name in sorted(variants):
                if not variants[name]["prompt"]:
                    continue
                restriction = check(None, None, variants[name]["prompt"])
                require(restriction is None, "holdout_refusal",
                        f"{family_id}:{name}: the variant's prompt is restricted: {restriction}; its text is "
                        "not exported")
        text: dict[str, dict[str, str]] = {}
        for name in sorted(variants):
            recorded = variant_inputs[family_id].get(name, {}).get("prompt_sha256")
            require(recorded is not None and prompt_digest(variants[name]["prompt"]) == recorded, "prompt_hash",
                    f"{family_id}:{name}: the protocol's prompt is not the prompt the plan's tasks were built "
                    "from (SHA-256 differs or the variant has no task)")
            text[name] = {"prompt": variants[name]["prompt"], "prompt_sha256": recorded}
        seal_state = "not_applicable_synthetic" if synthetic else "passed_at_export"
        out[family_id] = {
            "variant_text": text,
            "prompt_text_export": {"basis": "protocol_marker", "marker": PROMPT_TEXT_MARKER,
                                   "seal_check": seal_state}}
        if TARGET_TEXT_MARKER in family.get("facts", []):
            targets: dict[str, dict[str, Any]] = {}
            for target in sorted(family["targets"], key=lambda t: t["id"]):
                if check is not None:
                    restriction = check(None, None, target["text"])
                    require(restriction is None, "holdout_refusal",
                            f"{family_id}:{target['id']}: the target's text is restricted: {restriction}; it is "
                            "not exported")
                n_tokens = len(target["token_ids"])
                # Copied from the protocol. Never decoded from a token id: a plan and a payload hold ids only.
                targets[target["id"]] = {"text": target["text"], "n_tokens": n_tokens,
                                         "partial_token_endpoint": n_tokens > 1}
            out[family_id]["target_text"] = targets
            out[family_id]["target_text_export"] = {"basis": "protocol_marker", "marker": TARGET_TEXT_MARKER,
                                                    "seal_check": seal_state}
    return out


def build_bundle(run_dir: Any, *, allow_roots: Iterable[Any] = (), protocol: Mapping[str, Any] | None = None,
                 row_restriction: RowRestriction | None = None) -> dict[str, Any]:
    """The bundle document for a collected run directory. Reads only; the caller writes it.

    ``protocol`` is the protocol document the plan was built from. It is needed only for the explicit
    prompt-text export (module docstring); without it the bundle holds hashes and no text.
    """
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
    prompt_text = approved_prompt_text(protocol, plan, variant_inputs, row_restriction)
    families = [{**family, "variant_inputs": {name: variant_inputs[family["family_id"]][name]
                                              for name in sorted(variant_inputs[family["family_id"]])},
                 **prompt_text.get(family["family_id"], {})}
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
