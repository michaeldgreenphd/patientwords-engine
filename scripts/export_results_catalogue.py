#!/usr/bin/env python3
"""Export the results catalogue: every run under trace_out/, what state it is in, and what it may be used for.

The catalogue is the evolving, public record of what has been measured. It is not a statistic and selects
nothing: a run is listed whether its effect is large, zero or in the unexpected direction, whether it finished
or stopped part-way, and whether or not any analysis includes it. For each run directory it records the six
independent facts of the open-results policy (scripts/results_policy.py): execution state, artifact integrity,
evidence class, clinical-review status, visibility with any restriction reason, and membership of each named
analysis. Row-level results are written for every stimulus class the policy exports rows for.

What is never written:

* a pair the Tier B seal covers. The seal is decided per PAIR, not per row: if scripts/tierb_split.py
  sealed_pair seals the pair's row in any run (the accepted prompt, a trace-time prompt with a probe extension,
  or a registered phrase), every run's row at that (stimulus set, index) is withheld and the pair's prompts
  are never written, as the gallery exporter does. A pair is also withheld when its prompt text contains a
  registered holdout phrase by scripts/seal_check.py's own matcher (case, whitespace and encodings), unless
  the owner's allowlist rules that containing field public. Withheld rows are counted, never listed. If the
  seal cannot be evaluated the run stops with exit 2 and writes nothing;
* the text of a redistribution-limited stimulus family, or rows of a part whose bytes differ from a recorded
  sha256, or of a malformed part: those runs are listed with the reason, without rows;
* clinical mass from a model/source-set pair that is not calibrated (scripts/feature_models.py): the field is
  omitted and the row says so.

Outputs, under ``<out>`` (with ``--site``, ``<site>/data/results_catalogue``):

  index.json              run-level records, totals, the policy and memberships in force
  stimuli/<stem>.json     the prompt pair of every listed row of one stimulus set, stored once per set
  rows/<run_dir>.json     row-level results of one run directory, loaded on demand by the site's catalogue page
  rows.csv, stimuli.csv   the same rows and prompt pairs, flat, for download (join on stem and index)

Prompts are stored once per stimulus set because every model is measured on the same pairs; a row whose
traced prompts differ from the set's entry (a screening probe extension) carries its own under ``prompts``.

``--record`` also appends the sha256 of every part read for the first time to the engine's append-only ledger
(data/results_policy/part_ledger.v1.json), so a later change to those bytes is detected. A recorded hash is
never rewritten. ``--dry-run`` computes everything and writes nothing.

Row and stimulus files that the new export no longer lists are deleted from ``<out>/rows`` and
``<out>/stimuli``; nothing outside ``<out>`` is touched. Usage:

  python scripts/export_results_catalogue.py --site ../patientwords --record     # publish chain
  python scripts/export_results_catalogue.py --out /tmp/catalogue --dry-run      # count only
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import results_policy as rp  # noqa: E402
import seal_check  # noqa: E402
from feature_models import clinical_mass_publishable  # noqa: E402
from provenance_stamp import engine_sha  # noqa: E402
from sparse_guard import hidden_tracked  # noqa: E402
from urgency_headline import population  # noqa: E402

SCHEMA = "patientwords.results-catalogue/1"
ROWS_SCHEMA = "patientwords.results-catalogue-rows/1"
SPREAD_TOP = 3
RUN_DIR_RE = re.compile(r"[A-Za-z0-9._-]+(__[A-Za-z0-9._-]+)?\Z")
STIMULI_SCHEMA = "patientwords.results-catalogue-stimuli/1"
CSV_COLUMNS = ("run_dir", "stem", "model", "index", "part", "evidence_class", "clinical_review", "sampling",
               "analysis_memberships", "part_state", "prob_clinical", "prob_patient", "language_penalty",
               "target_token", "top_clinical", "top_patient", "flipped", "screening_status", "own_prompts")
STIMULI_COLUMNS = ("stem", "index", "stimulus_class", "clinical_review", "sampling", "clinical_prompt",
                   "patient_prompt")

LEGEND = {
    "execution_state": {
        "completed": "the run recorded that it finished; says nothing about the size or direction of any effect",
        "partial": "the run recorded that it stopped before finishing; its landed rows are real measurements",
        "empty": "the part holds no results",
        "completion_not_recorded": "written before parts recorded completion; rows are present",
        "unreadable": "the file is not a readable summary",
    },
    "artifact_integrity": {
        "recorded_match": "bytes equal the sha256 recorded for this part",
        "unrecorded": "no sha256 was recorded before this export; this is not a defect",
        "changed_since_recorded": "bytes differ from a recorded sha256; the part is not read",
        "malformed": "required metadata is missing; the part is not read",
        "unreadable": "the file could not be read",
    },
    "evidence_class": {
        "registered_cohort": "a pre-registered model on a generated study batch; interim, not the confirmatory endpoint",
        "exploratory_post_registration": "a model added after registration; exploratory by declaration",
        "exploratory_hand_authored": "hand-authored example pairs; never part of a study analysis",
        "exploratory_third_party_source": "built from third-party source text; exploratory",
        "unclassified": "no declared class in this policy version",
    },
    "sampling": {
        "observational": "generated by the cadence sampling",
        "outcome_selected": "generated or selected to elicit an outcome; a rate over these rows describes the selection",
        "other": "another stimulus family",
    },
}


class CatalogueError(RuntimeError):
    """The export cannot be produced soundly; nothing is written."""


def bare_token(label: Any) -> str | None:
    """Logit labels arrive as 'Output " nap"'; return the bare token."""
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


def _spread(side: Any) -> list[list[Any]]:
    out = []
    for item in side or []:
        if isinstance(item, (list, tuple)) and len(item) == 2 and bare_token(item[0]):
            out.append([bare_token(item[0]), item[1]])
    return out[:SPREAD_TOP]


def _selection_index(policy: rp.Policy, engine: Path) -> dict[str, tuple[str, set[tuple[str, int]]]]:
    """{model: (label, {(batch, index)})} from the policy's sampling_labels; a missing selection file is an error,
    because a silently unlabelled outcome-selected subset is the failure the label exists to prevent."""
    index: dict[str, tuple[str, set[tuple[str, int]]]] = {}
    for entry in policy.doc.get("sampling_labels", []):
        path = engine / entry["selection"]
        try:
            pairs = json.loads(path.read_text(encoding="utf-8"))["pairs"]
        except (OSError, ValueError, KeyError) as exc:
            raise CatalogueError(f"sampling label for {entry['model']} names {path}, which cannot be read "
                                 f"({type(exc).__name__})") from exc
        index[entry["model"]] = (entry["label"], {(p["batch"], p["index"]) for p in pairs})
    return index


def build_row(result: dict[str, Any], *, selection_label: str | None, mass_publishable: bool) -> dict[str, Any]:
    """One public row: only what varies by row. Signed values are kept as measured; nothing is rounded,
    clipped or re-labelled. Facts shared by a whole part (its state, the analyses that include it) are stored
    once on the part, and prompts once per stimulus set."""
    spread = result.get("predictive_spread") or {}
    top_c, top_p = _spread(spread.get("clinical")), _spread(spread.get("patient"))
    probs = result.get("probabilities") or {}
    screening = result.get("screening") if isinstance(result.get("screening"), dict) else None
    row: dict[str, Any] = {
        "index": result.get("index"),
        "prob_clinical": probs.get("clinical"),
        "prob_patient": probs.get("patient"),
        "language_penalty": result.get("language_penalty"),
        "target_token": bare_token(result.get("target_token")),
        "spread_clinical": top_c,
        "spread_patient": top_p,
        "flipped": bool(top_c[0][0] != top_p[0][0]) if (top_c and top_p) else None,
    }
    if screening:
        row["screening"] = {"status": screening.get("status"), "reason": screening.get("reason")}
    if selection_label:
        row["sampling"] = selection_label
    if mass_publishable:
        row["clinical_mass"] = result.get("clinical_mass")
    return row


def _exportable_parts(engine: Path, policy: rp.Policy, manifest: Any, ledger: Any):
    """(run directory name, stem, part path, parsed summary) for every part whose rows the policy exports."""
    for run_path in sorted(p for p in (engine / "trace_out").iterdir() if p.is_dir()):
        stem = rp.run_dir_parts(run_path.name)[0]
        for part in sorted(run_path.glob("batch_summary*.json")):
            try:
                summary = json.loads(part.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            d = rp.classify_part(engine, part, summary, policy=policy, manifest=manifest, ledger=ledger)
            if d.rows_exported and d.analysis[rp.PUBLIC_DISPLAY]["eligible"]:
                yield run_path.name, stem, d.path, summary


def sealed_pair_keys(engine: Path, policy: rp.Policy, manifest: Any, ledger: Any,
                     seal_paths: dict[str, Any]) -> set[tuple[str, int]]:
    """Every (stimulus set, index) that must be withheld in every run.

    A pair is sealed when the seal covers its row in ANY run. One run's trace-time prompt can hash holdout
    while the accepted prompt and the other runs' prompts do not (a screening probe extension); the divergence
    log (2026-07-17) keeps such pairs sealed, and the gallery exporter withholds the whole pair. Deciding row
    by row would publish the pair's text and its other rows (found by review, 2026-11-10).

    A pair is also sealed when its prompt text contains a registered holdout phrase under the matcher that
    scripts/seal_check.py uses for the publish gate, so this exporter never writes what that gate would
    refuse. The owner's allowlist (data/seal_allowlist.json) applies exactly as it does there.

    The same pass validates each exported result: its index must be an integer and its prompts an object.
    Raises ``results_policy.SealError`` when the seal cannot be evaluated."""
    row_paths = {k: v for k, v in seal_paths.items() if k in ("dashboard_path", "simulated_dir")}
    dashboard = Path(seal_paths.get("dashboard_path") or rp._tierb_split.DASHBOARD_PATH)
    simulated = Path(seal_paths.get("simulated_dir") or rp._tierb_split.SIMULATED_DIR)
    allow_path = Path(seal_paths.get("allowlist_path") or rp.ENGINE / "data" / "seal_allowlist.json")
    registry = seal_check.sealed_registry(str(simulated), str(dashboard))
    try:
        allow = seal_check.resolve_allowlist(seal_check.load_allowlist(allow_path), registry, simulated)
    except ValueError as exc:
        raise CatalogueError(f"the seal allowlist {allow_path} is malformed: {exc}") from exc
    sealed: set[tuple[str, int]] = set()
    text_verdict: dict[tuple[Any, Any], bool] = {}
    for _run_dir, stem, rel, summary in _exportable_parts(engine, policy, manifest, ledger):
        for result in summary["results"]:
            if not isinstance(result, dict):
                raise CatalogueError(f"{rel}: a result is not an object")
            index = result.get("index")
            if type(index) is not int:
                raise CatalogueError(f"{rel}: a result's index is {type(index).__name__}, not an integer; "
                                     "rows are joined and sealed by integer index")
            prompts = result.get("prompts")
            if prompts is not None and not isinstance(prompts, dict):
                raise CatalogueError(f"{rel}#{index}: 'prompts' is {type(prompts).__name__}, not an object")
            clinical, patient = (prompts or {}).get("clinical"), (prompts or {}).get("patient")
            if (stem, index) in sealed:
                continue
            if rp.row_restriction(stem, index, clinical, **row_paths):
                sealed.add((stem, index))
                continue
            key = (clinical, patient)
            if key not in text_verdict:
                text = "\n".join(json.dumps(t, ensure_ascii=False) for t in key if isinstance(t, str))
                text_verdict[key] = bool(text) and bool(seal_check.scan_text(text, registry, allow, ".json")[0])
            if text_verdict[key]:
                sealed.add((stem, index))
    return sealed


def _penalty_sign(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "missing"
    return "negative" if value < 0 else "positive" if value > 0 else "zero"


def collect(engine: Path, *, policy: rp.Policy | None = None, seal_paths: dict[str, Any] | None = None
            ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    """(index document without provenance, {run_dir: rows document}, {stem: stimuli document},
    {part path: sha256} of every part read).

    Raises ``results_policy.SealError`` when the seal cannot be evaluated and CatalogueError on any other unsound input."""
    policy = policy or rp.load_policy()
    engine = engine.resolve()
    trace_root = engine / "trace_out"
    if not trace_root.is_dir():
        raise CatalogueError(f"{trace_root} is not a directory")
    hidden = hidden_tracked(engine, "trace_out")
    if hidden:
        raise CatalogueError(f"the engine checkout keeps {len(hidden)} tracked file(s) under trace_out/ off disk "
                             f"(sparse checkout), e.g. {hidden[0]}; a catalogue built from it would omit runs")
    manifest = rp.load_manifest(engine) if (engine / rp.RELEASE_MANIFEST).exists() else None
    ledger = rp.load_ledger(engine)
    selections = _selection_index(policy, engine)
    seal_paths = seal_paths or {}
    sealed_keys = sealed_pair_keys(engine, policy, manifest, ledger, seal_paths)
    membership_ids = list(policy.doc["memberships"])
    analysis_ids = [m for m in membership_ids if policy.membership(m)["purpose"] == "analysis"]

    runs: list[dict[str, Any]] = []
    stimuli: dict[str, dict[int, dict[str, Any]]] = {}
    rows_docs: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    totals: Counter[str] = Counter()
    by_axis: dict[str, Counter[str]] = {axis: Counter() for axis in (
        "execution_state", "artifact_integrity", "evidence_class", "clinical_review", "visibility",
        "stimulus_class")}
    membership_parts: Counter[str] = Counter()
    membership_rows: Counter[str] = Counter()
    restriction_counts: Counter[str] = Counter()

    for run_path in sorted(p for p in trace_root.iterdir() if p.is_dir()):
        run_dir = run_path.name
        if not RUN_DIR_RE.fullmatch(run_dir):
            raise CatalogueError(f"unexpected run directory name {run_dir!r}; refusing to build a file path from it")
        stem, suffix = rp.run_dir_parts(run_dir)
        instrument = rp.instrument_of(suffix)
        part_paths = sorted(run_path.glob("batch_summary*.json"))
        other_kinds = Counter(re.sub(r"(\.part_\d+)?\.json(\.gz)?$", "", f.name)
                              for f in run_path.glob("*summary*.json*") if not f.name.startswith("batch_summary"))
        parts_out: list[dict[str, Any]] = []
        row_parts: list[dict[str, Any]] = []
        run_counts: Counter[str] = Counter()
        decisions: list[rp.PartDecision] = []
        seen_index: set[Any] = set()
        for part in part_paths:
            try:
                summary = json.loads(part.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                summary = None
            d = rp.classify_part(engine, part, summary, policy=policy, manifest=manifest, ledger=ledger)
            decisions.append(d)
            # Only bytes that pass integrity are offered to the ledger. Recording a part that already
            # differs from its pin would make the changed bytes its first recorded hash, and restoring the
            # original would then fail against the ledger for good.
            if d.sha256 and d.artifact_integrity in ("unrecorded", "recorded_match"):
                hashes[d.path] = d.sha256
            totals["parts"] += 1
            for axis in ("execution_state", "artifact_integrity", "evidence_class", "clinical_review",
                         "visibility", "stimulus_class"):
                by_axis[axis][getattr(d, axis)] += 1
            for reason in d.restriction_reasons:
                restriction_counts[reason] += 1
            eligible = [m for m in membership_ids if d.analysis[m]["eligible"]]
            for m in eligible:
                membership_parts[m] += 1
            part_out = {
                "name": part.name, "sha256": d.sha256, "backend": d.backend,
                "execution_state": d.execution_state, "n_results": d.n_results,
                "pairs_requested": d.pairs_requested, "artifact_integrity": d.artifact_integrity,
                "in": eligible,
                "outside": {m: d.analysis[m]["reason"] for m in membership_ids if not d.analysis[m]["eligible"]},
            }
            if d.integrity_detail:
                part_out["integrity_detail"] = d.integrity_detail
            parts_out.append(part_out)
            if not (d.rows_exported and d.analysis[rp.PUBLIC_DISPLAY]["eligible"]):
                continue
            mass_ok = clinical_mass_publishable(summary.get("graph_model") or d.model, summary.get("source_set"))
            label, chosen = selections.get(d.model or "", (None, set()))
            row_memberships = [m for m in analysis_ids if d.analysis[m]["eligible"]]
            part_rows: list[dict[str, Any]] = []
            for result in summary["results"]:
                index = result.get("index")
                clinical = (result.get("prompts") or {}).get("clinical")
                if (stem, index) in sealed_keys:          # the pair is sealed in every run, not only this one
                    run_counts["rows_withheld_sealed"] += 1
                    restriction_counts["sealed_holdout"] += 1
                    continue
                row = build_row(result, mass_publishable=mass_ok,
                                selection_label=label if (stem, index) in chosen else None)
                pair = {"clinical_prompt": clinical, "patient_prompt": (result.get("prompts") or {}).get("patient")}
                known = stimuli.setdefault(stem, {}).setdefault(index, pair)
                if known != pair:
                    row["prompts"] = pair            # traced with different text than the set's entry
                    run_counts["rows_own_prompts"] += 1
                if index in seen_index:
                    run_counts["rows_duplicate_index"] += 1
                seen_index.add(index)
                part_rows.append(row)
                run_counts["rows_public"] += 1
                run_counts[f"penalty_{_penalty_sign(row['language_penalty'])}"] += 1
                if row["flipped"]:
                    run_counts["rows_flipped"] += 1
                if (row.get("screening") or {}).get("status") == "screened_out":
                    run_counts["rows_screened_out"] += 1
                for m in row_memberships:
                    membership_rows[m] += 1
                membership_rows[rp.PUBLIC_DISPLAY] += 1
            if part_rows and not mass_ok:
                restriction_counts["uncalibrated_clinical_mass"] += 1
            if part_rows:
                row_parts.append({"name": part.name, "execution_state": d.execution_state,
                                  "analysis_memberships": row_memberships,
                                  "clinical_mass": "per row" if mass_ok else
                                  "not published: this model and source set are not calibrated",
                                  "rows": part_rows})

        first = decisions[0] if decisions else None
        stimulus_class = first.stimulus_class if first else policy.stimulus_class(stem)
        entry = policy.stimulus_entry(stimulus_class)
        model = first.model if first else (None if instrument else suffix)
        if instrument:
            model = None
        # A run is restricted when its stimulus class is, or when every part it has is. A run with one failed
        # part and one intact part stays public: the intact part's rows are listed and the failed part carries
        # its own integrity state and reason (restriction_reasons names it at run level too).
        visibility = ("restricted" if entry.get("restriction")
                      or (decisions and all(d.visibility == "restricted" for d in decisions)) else "public")
        reasons = sorted({r for d in decisions for r in d.restriction_reasons}
                         | ({entry["restriction"]} if entry.get("restriction") else set()))
        if not decisions:
            rows_reason = (f"instrument run ({instrument}): a typed artifact with its own exporter" if instrument
                           else "no batch_summary part in this directory")
        elif row_parts:
            rows_reason = None
        else:
            rows_reason = next((d.rows_reason for d in decisions if d.rows_reason), None) or (
                "every row is withheld by the Tier B seal" if run_counts["rows_withheld_sealed"] else "no rows")
        run = {
            "run_dir": run_dir, "stem": stem, "model": model, "instrument": instrument,
            "backends": sorted({d.backend for d in decisions if isinstance(d.backend, str)}),
            "stimulus_class": stimulus_class,
            "model_cohort": first.model_cohort if first else policy.cohort_of(model),
            "evidence_class": first.evidence_class if first else policy.evidence_class(stimulus_class, model),
            "clinical_review": entry["clinical_review"],
            "sampling": population(stem),
            "visibility": visibility, "restriction_reasons": reasons,
            "execution_states": dict(sorted(Counter(d.execution_state for d in decisions).items())),
            "n_parts": len(decisions),
            "restricted_parts": sum(1 for d in decisions if d.visibility == "restricted"),
            "analysis_parts": {m: sum(1 for d in decisions if d.analysis[m]["eligible"]) for m in membership_ids},
            "other_artifacts": dict(sorted(other_kinds.items())),
            "rows_file": f"rows/{run_dir}.json" if row_parts else None,
            "stimuli_file": f"stimuli/{stem}.json" if row_parts else None,
            "rows_reason": rows_reason,
            "counts": {key: run_counts[key] for key in (
                "rows_public", "rows_withheld_sealed", "rows_screened_out", "rows_flipped",
                "rows_duplicate_index", "rows_own_prompts", "penalty_negative", "penalty_zero", "penalty_positive",
                "penalty_missing")},
            "parts": parts_out,
            "source": f"trace_out/{run_dir}",
        }
        runs.append(run)
        totals["runs"] += 1
        for key, n in run["counts"].items():
            totals[key] += n
        if row_parts:
            totals["runs_with_rows"] += 1
            rows_docs[run_dir] = {
                "schema": ROWS_SCHEMA, "run_dir": run_dir, "stem": stem, "model": model,
                "evidence_class": run["evidence_class"], "clinical_review": run["clinical_review"],
                "sampling": run["sampling"], "rows_withheld_sealed": run_counts["rows_withheld_sealed"],
                "endpoint": "next-token probability of the first encoded target token (a lexical proxy, not "
                            "whole-answer correctness)",
                "stimuli_file": f"stimuli/{stem}.json",
                "parts": row_parts,
            }

    stimuli_docs = {}
    for stem, pairs in stimuli.items():
        cls = policy.stimulus_class(stem)
        stimuli_docs[stem] = {
            "schema": STIMULI_SCHEMA, "stem": stem, "stimulus_class": cls,
            "clinical_review": policy.stimulus_entry(cls)["clinical_review"], "sampling": population(stem),
            "source": f"data/simulated/{stem}.json",
            "note": "Model-authored or hand-authored test phrasings, not patient statements. Sealed Tier B rows "
                    "are absent.",
            "pairs": {str(i): pairs[i] for i in sorted(pairs, key=lambda v: (not isinstance(v, int), v))},
        }
        totals["stimulus_pairs"] += len(pairs)
    totals["stimulus_sets"] = len(stimuli_docs)

    index_doc = {
        "schema": SCHEMA,
        "policy": {"version": policy.version, "sha256": hashlib.sha256(policy.path.read_bytes()).hexdigest(),
                   "default_membership": policy.default_membership,
                   "analysis_pin": policy.doc.get("analysis_pin")},
        "memberships": {m: {"label": policy.membership(m)["label"], "purpose": policy.membership(m)["purpose"],
                            "parts": membership_parts[m], "rows": membership_rows[m]} for m in membership_ids},
        # count_unit says what was counted: rows for a row-scoped restriction, parts for every other scope
        # (for the clinical-mass field: parts whose listed rows omit the field).
        "restrictions": {name: {**spec, "count": restriction_counts.get(name, 0)
                                + sum(n for r, n in restriction_counts.items() if r.startswith(name + ":")),
                                "count_unit": "rows" if spec["scope"] == "row" else "parts"}
                         for name, spec in policy.doc["restrictions"].items()},
        "totals": {**{k: totals[k] for k in sorted(totals)},
                   **{axis: dict(sorted(counter.items())) for axis, counter in by_axis.items()}},
        "legend": LEGEND,
        "notes": [
            "A listing here is not a claim. Evidence class, clinical review and analysis membership are stated "
            "per run; rows are next-token measurements of language-model behaviour, not medical advice.",
            "Rows the Tier B seal covers are counted (rows_withheld_sealed) and never listed.",
            "This catalogue is not a sample of anything: it lists every run, including zero and opposite-"
            "direction effects, partial runs and runs no analysis includes.",
        ],
        "runs": runs,
    }
    return index_doc, rows_docs, stimuli_docs, hashes


def rows_csv(rows_docs: dict[str, dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for run_dir in sorted(rows_docs):
        doc = rows_docs[run_dir]
        for part in doc["parts"]:
            for row in part["rows"]:
                flat = {
                    "run_dir": run_dir, "stem": doc["stem"], "model": doc["model"], "part": part["name"],
                    "evidence_class": doc["evidence_class"], "clinical_review": doc["clinical_review"],
                    "sampling": doc["sampling"], "part_state": part["execution_state"],
                    "top_clinical": (row["spread_clinical"] or [[None]])[0][0],
                    "top_patient": (row["spread_patient"] or [[None]])[0][0],
                    "screening_status": (row.get("screening") or {}).get("status"),
                    "own_prompts": "yes" if "prompts" in row else "", **row,
                    "analysis_memberships": ";".join(part["analysis_memberships"]),
                }
                writer.writerow(["" if flat.get(c) is None else flat[c] for c in CSV_COLUMNS])
    return buf.getvalue()


def stimuli_csv(stimuli_docs: dict[str, dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(STIMULI_COLUMNS)
    for stem in sorted(stimuli_docs):
        doc = stimuli_docs[stem]
        for index, pair in doc["pairs"].items():
            flat = {"stem": stem, "index": index, "stimulus_class": doc["stimulus_class"],
                    "clinical_review": doc["clinical_review"], "sampling": doc["sampling"], **pair}
            writer.writerow(["" if flat.get(c) is None else flat[c] for c in STIMULI_COLUMNS])
    return buf.getvalue()


def write_outputs(out: Path, index_doc: dict[str, Any], rows_docs: dict[str, dict[str, Any]],
                  stimuli_docs: dict[str, dict[str, Any]]) -> list[str]:
    """Write the index, row files, stimulus files and CSVs under ``out``; delete row and stimulus files the
    export no longer lists. Returns the deleted paths, relative to ``out``."""
    stale: list[str] = []
    for sub, docs in (("rows", rows_docs), ("stimuli", stimuli_docs)):
        directory = out / sub
        directory.mkdir(parents=True, exist_ok=True)
        for name, doc in docs.items():
            (directory / f"{name}.json").write_text(
                json.dumps(doc, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8")
        wanted = {f"{name}.json" for name in docs}
        for path in sorted(directory.glob("*.json")):
            if path.name not in wanted:
                path.unlink()
                stale.append(f"{sub}/{path.name}")
    (out / "rows.csv").write_text(rows_csv(rows_docs), encoding="utf-8")
    (out / "stimuli.csv").write_text(stimuli_csv(stimuli_docs), encoding="utf-8")
    (out / "index.json").write_text(
        json.dumps(index_doc, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", default=str(rp.ENGINE), help="engine repository root (default: this checkout)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--site", help="frontend repository root; writes <site>/data/results_catalogue")
    target.add_argument("--out", help="any other output directory (previews, tests)")
    parser.add_argument("--record", action="store_true",
                        help="append first-seen part hashes to data/results_policy/part_ledger.v1.json")
    parser.add_argument("--dry-run", action="store_true", help="compute and print the totals; write nothing")
    parser.add_argument("--dashboard", default=None,
                        help="ops/dashboard.json the seal reads its Tier B start from (default: this repository's)")
    parser.add_argument("--simulated", default=None,
                        help="data/simulated directory the seal reads batches from (default: this repository's)")
    args = parser.parse_args(argv)
    engine = Path(args.engine).resolve()
    out = (Path(args.site) / "data" / "results_catalogue") if args.site else Path(args.out)
    if args.site and not (Path(args.site) / "data").is_dir():
        print(f"results catalogue: refusing, {args.site} has no data/ directory (not a site checkout)",
              file=sys.stderr)
        return 2
    try:
        seal_paths = {key: value for key, value in (("dashboard_path", args.dashboard),
                                                    ("simulated_dir", args.simulated)) if value}
        index_doc, rows_docs, stimuli_docs, hashes = collect(engine, seal_paths=seal_paths)
    except rp.SealError as exc:
        return rp.seal_config_error(exc)    # exit 2: the publish chain stops, nothing written
    except (CatalogueError, rp.ReleaseError) as exc:
        print(f"results catalogue: refusing, nothing written: {exc}", file=sys.stderr)
        return 2
    index_doc["_provenance"] = {"generator": "scripts/export_results_catalogue.py", "engine_sha": engine_sha(engine),
                                "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    t = index_doc["totals"]
    print(f"results catalogue: {t['runs']} runs, {t['parts']} parts; rows public {t['rows_public']}, "
          f"withheld by the seal {t['rows_withheld_sealed']}; policy {index_doc['policy']['version']}")
    for m, info in index_doc["memberships"].items():
        print(f"  {m}: {info['parts']} parts, {info['rows']} rows ({info['purpose']})")
    for name, info in index_doc["restrictions"].items():
        if info["count"]:
            print(f"  restricted - {name}: {info['count']}")
    if args.dry_run:
        print("  DRY RUN: nothing was written")
        return 0
    stale = write_outputs(out, index_doc, rows_docs, stimuli_docs)
    print(f"  wrote {out / 'index.json'}, {len(rows_docs)} row file(s), {len(stimuli_docs)} stimulus file(s), "
          f"rows.csv, stimuli.csv; removed {len(stale)} stale file(s)")
    if args.record:
        result = rp.record_parts(engine, hashes, recorded_utc=index_doc["_provenance"]["generated_utc"],
                                 recorded_at_commit=engine_sha(engine))
        differing = index_doc["totals"]["artifact_integrity"].get("changed_since_recorded", 0)
        print(f"  ledger: {len(result['added'])} part hash(es) recorded for the first time; "
              f"{differing + len(result['conflicts'])} part(s) differ from their recorded hash"
              + (" (not recorded; restore the recorded bytes)" if differing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
