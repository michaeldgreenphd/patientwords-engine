"""Command line for the experiment package: ``python -m scripts.experiments.cli <command>``.

Everything here is offline. No command loads a model, opens a network connection or fires a trigger.

Commands: ``validate``, ``plan``, ``run-fixture``, ``collect``, ``compare``, ``bundle``, ``capabilities``,
``intake``.
Each prints one JSON object. Exit codes: 0 success; 1 the command finished and the run is not clean (an
attempt ended ``failed`` or ``invalid``; ``run-fixture`` was not stopped by ``--stop-after`` and left a ready
task without a completed result; or ``collect --require-complete`` found a planned task without an envelope
or a ready task without a completed result that counts: a completed result whose task was executed again
under changed inputs without completing does not count; or ``intake`` found a structural error in the
batch, in which case its three files are still written so the errors can be read); 2 a refusal, printed as
``{"status": "refused", "code": ..., "detail": ...}``; 3 a configuration error (the holdout seal or the
results policy could not be evaluated), which is not a refusal.

Writers refuse a path under ``trace_out``, ``data``, ``pilot``, ``ops``, ``modes``, ``.github``, ``.claude``,
``.githooks`` or ``.git``, and any path inside a Git checkout unless ``--allow-root`` names a directory that
holds it. ``--allow-root`` never lifts the protected-root rule.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.experiments import capabilities as caps
from scripts.experiments.bundle import build_bundle
from scripts.experiments.common import (
    PROTOCOL_SCHEMA, Refusal, digest, read_json, require, sha256_bytes, write_json,
)
from scripts.experiments.compare import compare_run
from scripts.experiments.intake import ROOT as INTAKE_ROOT, file_record, intake_files, write_outputs
from scripts.experiments.planner import build_plan, validate_plan
from scripts.experiments.protocol import validate_protocol
from scripts.experiments.store import RunStore

EXIT_OK, EXIT_NOT_CLEAN, EXIT_REFUSED, EXIT_CONFIG = 0, 1, 2, 3
CONFIG_ERRORS = ("SealError", "ReleaseError", "PolicyError")


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))


def _load(path: Path, what: str) -> Any:
    try:
        return read_json(path)
    except OSError as exc:
        raise Refusal("unreadable_input", f"{what} {path}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise Refusal("invalid_input", f"{what} {path} is not JSON: {exc}") from exc


def _matrix(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "capabilities", None):
        return caps.validate_matrix(_load(args.capabilities, "capability matrix"))
    return caps.load_matrix()


def _find_protocol(args: argparse.Namespace, plan: dict[str, Any]) -> dict[str, Any]:
    """The protocol a plan was built from: ``--protocol`` when given, else the JSON file in the fixtures
    directory whose canonical digest is the plan's protocol hash."""
    wanted = plan["protocol"]["sha256"]
    if args.protocol:
        protocol = _load(args.protocol, "protocol")
        require(digest(protocol) == wanted, "protocol_mismatch",
                f"{args.protocol} is not the protocol this plan was built from")
        return protocol
    for path in sorted(Path(args.fixtures).glob("*.json")):
        try:
            doc = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and doc.get("schema_version") == PROTOCOL_SCHEMA and digest(doc) == wanted:
            return doc
    raise Refusal("protocol_not_found",
                  f"No protocol with digest {wanted[:12]} in {args.fixtures}; pass --protocol")


def cmd_validate(args: argparse.Namespace) -> int:
    _emit(validate_protocol(_load(args.protocol, "protocol")))
    return EXIT_OK


def cmd_plan(args: argparse.Namespace) -> int:
    protocol = _load(args.protocol, "protocol")
    rates = _load(args.rates, "rates file") if args.rates else None
    plan = build_plan(protocol, _matrix(args), replicates=args.replicates, rates=rates)
    out = write_json(args.out, plan, args.allow_root)
    _emit({"status": "planned", "plan": str(out), "protocol": plan["protocol"], "replicates": plan["replicates"],
           "adapters": plan["adapters"], "totals": plan["totals"]})
    return EXIT_OK


def cmd_run_fixture(args: argparse.Namespace) -> int:
    plan = validate_plan(_load(args.plan, "plan"))
    protocol = _find_protocol(args, plan)
    store = RunStore(args.run_dir, allow_roots=args.allow_root)
    if args.new_run_dir and not store.compatible_with(plan):
        store = RunStore(Path(f"{store.run_dir}__{plan['protocol']['sha256'][:12]}"), allow_roots=args.allow_root)
    summary = store.run_fixture(plan, args.worker, fixtures_dir=args.fixtures, protocol=protocol,
                                stop_after=args.stop_after)
    _emit({"status": "ran", "run_dir": str(store.run_dir), **summary})
    # A run that was not stopped on request and still leaves ready tasks without a completed result computed
    # less than its plan asked for (absent or unreadable fixtures, for example). That is not a clean run.
    unfinished = summary["remaining_ready"] > 0 and not summary["stopped_early"]
    not_clean = summary["by_state"]["failed"] or summary["by_state"]["invalid"] or unfinished
    return EXIT_NOT_CLEAN if not_clean else EXIT_OK


def cmd_collect(args: argparse.Namespace) -> int:
    store = RunStore(args.run_dir, allow_roots=args.allow_root)
    collected = store.collect()
    assembly = collected["assembly"]
    _emit({"status": "collected", "collected": str(store.collected_path),
           "assembly_sha256": collected["assembly_sha256"], "complete": assembly["complete"],
           "ready_complete": assembly["ready_complete"],
           "by_state": assembly["by_state"], "counts": assembly["counts"],
           "missing": [f"{m['task_id']}.r{m['replicate']}" for m in assembly["missing"]],
           "uncertain": assembly["uncertain"], "ended_line_missing": assembly["ended_line_missing"],
           "duplicate_identical": assembly["duplicate_identical"],
           "attempt_outcomes_differ": assembly["attempt_outcomes_differ"],
           "completed_under_superseded_inputs": assembly["completed_under_superseded_inputs"],
           "reused_events": collected["metrics"]["reused_events"],
           "executed_attempts": collected["metrics"]["executed_attempts"]})
    finished = assembly["complete"] and assembly["ready_complete"]
    return EXIT_NOT_CLEAN if args.require_complete and not finished else EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    comparison = compare_run(args.run_dir, allow_roots=args.allow_root)
    out = write_json(args.out, comparison, args.allow_root)
    entries = [entry for family in comparison["families"] for entry in family["comparisons"]]
    _emit({"status": "compared", "comparison": str(out), "families": len(comparison["families"]),
           "comparison_entries": len(entries),
           "behavior_blocks_computed": sum(1 for e in entries if e.get("behavior", {}).get("status") == "computed"),
           "readout_blocks_computed": sum(1 for e in entries for b in e["readout"].values()
                                          if b["status"] == "computed"),
           "ica_blocks_computed": sum(1 for e in entries if e.get("ica", {}).get("status") == "computed"),
           "methods_not_run": comparison["methods_not_run"]})
    return EXIT_OK


def cmd_bundle(args: argparse.Namespace) -> int:
    protocol = _load(args.protocol, "protocol") if args.protocol else None
    bundle = build_bundle(args.run_dir, allow_roots=args.allow_root, protocol=protocol)
    out = write_json(args.out, bundle, args.allow_root)
    _emit({"status": "bundled", "bundle": str(out), "schema_version": bundle["schema_version"],
           "families": len(bundle["comparisons"]), "capability_rows": len(bundle["capability_rows"]),
           "by_state": bundle["execution"]["by_state"], "limitations": bundle["limitations"],
           # Families whose prompt text the bundle holds: only with --protocol, and only families the protocol
           # marks (scripts/experiments/bundle.py, PROMPT_TEXT_MARKER).
           "prompt_text_families": sorted(f["family_id"] for f in bundle["protocol"]["families"]
                                          if "variant_text" in f)})
    return EXIT_OK


def cmd_capabilities(args: argparse.Namespace) -> int:
    matrix = _matrix(args)
    rows = caps.rows_for_model(matrix, args.model)
    _emit({"schema_version": matrix["schema_version"], "as_of": matrix["as_of"],
           "status_order": matrix["status_order"], "model": args.model, "rows": rows})
    return EXIT_OK


def _records(paths: list[Path]) -> list[dict[str, str]]:
    """File records of one repeatable input, by name and hash."""
    return sorted((file_record(p) for p in paths), key=lambda r: (r["name"], r["sha256"]))


def cmd_intake(args: argparse.Namespace) -> int:
    require(args.no_write or args.out is not None, "invalid_input", "Pass --out DIR, or --no-write")
    read_batches = {}
    for path in args.read_batch:
        read_batches[sha256_bytes(path.read_bytes())] = _load(path, "read batch")
    prior = {}
    for item in args.prior_batch:
        label, _, path = item.partition("=")
        require(bool(label) and bool(path), "invalid_input", "--prior-batch takes LABEL=PATH")
        prior[label] = _load(Path(path), "prior batch")
    lexicon = None
    if args.lexicon:
        doc = _load(args.lexicon, "lexicon")
        lexicon = {e["expression"] for part in ("core", "folk_meaning") for e in doc.get(part) or []}
    manifest, files = intake_files(
        args.batch, batch_id=args.batch_id, source_ref=args.source_ref, design_path=args.design, root=args.root,
        verdicts=[_load(p, "verdicts") for p in args.verdicts], read_batches=read_batches,
        reviews=[_load(p, "reviews") for p in args.reviews], prior_batches=prior,
        concerns=[_load(p, "concerns") for p in args.concerns],
        source_checks=[_load(p, "source check") for p in args.source_check],
        split_records=[_load(p, "split record") for p in args.split_record], split_seed=args.split_seed,
        models=args.model, tokenizations=[_load(p, "tokenization") for p in args.tokenization],
        mechanistic_families=args.mechanistic_families, mechanistic_seed=args.mechanistic_seed,
        previous_manifest=_load(args.previous_manifest, "previous manifest") if args.previous_manifest else None,
        stem=args.stem, pairs_file=_load(args.pairs_file, "pairs file") if args.pairs_file else None,
        pairs_file_ref=args.pairs_file.name if args.pairs_file else None,
        input_hashes={key: value for key, value in {
            # Repeatable inputs are listed in a fixed order, so the manifest does not depend on argument order.
            "verdicts": _records(args.verdicts),
            "read_batches": _records(args.read_batch),
            "reviews": _records(args.reviews),
            "concerns": _records(args.concerns),
            "source_checks": _records(args.source_check),
            "prior_batches": sorted(({"label": item.partition("=")[0], **file_record(Path(item.partition("=")[2]))}
                                     for item in args.prior_batch), key=lambda r: (r["label"], r["name"], r["sha256"])),
            "split_records": _records(args.split_record),
            "tokenizations": _records(args.tokenization),
            "previous_manifest": file_record(args.previous_manifest) if args.previous_manifest else None,
            "pairs_file": file_record(args.pairs_file) if args.pairs_file else None,
            "lexicon": file_record(args.lexicon) if args.lexicon else None}.items() if value},
        forbid=args.forbid, max_words=args.max_words, lexicon=lexicon)
    outputs = {} if args.no_write else write_outputs(args.out, files, args.allow_root)
    check = manifest["software_validation"]
    _emit({"status": "intake", "batch": manifest["batch"], "outputs": outputs,
           "output_sha256": {name: sha256_bytes(data) for name, data in files.items()},
           "software_validation": {k: check[k] for k in ("status", "errors", "warnings", "by_check")},
           "inventory": manifest["inventory"], "splits": manifest["splits"]["counts"],
           "mechanistic_subset": manifest["mechanistic_subset"]["families"],
           "measurements": manifest["measurements"]["existing_run_directories"]})
    return EXIT_NOT_CLEAN if check["status"] == "failed" else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.experiments.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler: Any, text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=text, description=text)
        sub.set_defaults(handler=handler)
        return sub

    def allow_root(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--allow-root", type=Path, action="append", default=[], metavar="DIR",
                         help="permit output under DIR although it lies inside a Git checkout (repeatable)")

    sub = add("validate", cmd_validate, "Validate a protocol; exit 0 valid, 2 refused.")
    sub.add_argument("--protocol", type=Path, required=True)

    sub = add("plan", cmd_plan, "Expand a protocol into a deterministic plan.")
    sub.add_argument("--protocol", type=Path, required=True)
    sub.add_argument("--out", type=Path, required=True)
    sub.add_argument("--rates", type=Path, help="measured rates with source and sample size")
    sub.add_argument("--replicates", type=int, help="override the protocol's replicate count")
    sub.add_argument("--capabilities", type=Path, help="capability matrix file (default: the committed one)")
    allow_root(sub)

    sub = add("run-fixture", cmd_run_fixture, "Execute a plan's ready tasks on offline fixtures; resumable.")
    sub.add_argument("--plan", type=Path, required=True)
    sub.add_argument("--fixtures", type=Path, required=True)
    sub.add_argument("--run-dir", type=Path, required=True)
    sub.add_argument("--protocol", type=Path, help="the protocol (default: found in --fixtures by its digest)")
    sub.add_argument("--worker", default="w0")
    sub.add_argument("--stop-after", type=int, metavar="N", help="stop after N executions (simulated interruption)")
    sub.add_argument("--new-run-dir", action="store_true",
                     help="if --run-dir holds another protocol's plan, use <run-dir>__<protocol hash> instead")
    allow_root(sub)

    sub = add("collect", cmd_collect, "Assemble shards into collected.json; verifies every payload hash.")
    sub.add_argument("--run-dir", type=Path, required=True)
    sub.add_argument("--require-complete", action="store_true",
                     help="exit 1 when a planned task has no envelope or a ready task has no completed result")
    allow_root(sub)

    sub = add("compare", cmd_compare, "Derive per-family comparison blocks from a collected run.")
    sub.add_argument("--run-dir", type=Path, required=True)
    sub.add_argument("--out", type=Path, required=True)
    allow_root(sub)

    sub = add("bundle", cmd_bundle, "Export the preview bundle from a collected run.")
    sub.add_argument("--run-dir", type=Path, required=True)
    sub.add_argument("--out", type=Path, required=True)
    sub.add_argument("--protocol", type=Path,
                     help="the protocol the plan was built from; needed only to export the prompt text of "
                          "families the protocol marks as approved for publication (default: no text)")
    allow_root(sub)

    sub = add("intake", cmd_intake, "Authored batch of case families -> review packet, review form and proposed "
                                    "measurement manifest. Offline; exit 1 when software validation fails.")
    sub.add_argument("--batch", type=Path, required=True, help="the authored families file (a JSON list)")
    sub.add_argument("--batch-id", required=True, help="stable name of the batch, for example r9_20261110")
    sub.add_argument("--source-ref", help="where the batch file came from (path and commit); recorded as given")
    sub.add_argument("--out", type=Path, help="directory for the three outputs; omit with --no-write")
    sub.add_argument("--no-write", action="store_true", help="print the summary and write nothing")
    sub.add_argument("--design", type=Path, help="intake design file (default: the committed one)")
    sub.add_argument("--verdicts", type=Path, action="append", default=[], help="owner read of a batch version")
    sub.add_argument("--read-batch", type=Path, action="append", default=[],
                     help="the batch version a verdicts file was recorded on, when it is not --batch")
    sub.add_argument("--reviews", type=Path, action="append", default=[], help="returned review form")
    sub.add_argument("--concerns", type=Path, action="append", default=[],
                     help="known content concerns with their dispositions; kept apart from the owner's read")
    sub.add_argument("--source-check", type=Path, action="append", default=[],
                     help="a recorded check of the citations: record found, evidence sentence found")
    sub.add_argument("--prior-batch", action="append", default=[], metavar="LABEL=PATH",
                     help="an earlier families file, for duplicate cases and reused ids")
    sub.add_argument("--split-record", type=Path, action="append", default=[],
                     help="a recorded split assignment; its families keep their split")
    sub.add_argument("--split-seed", type=int, help="seed for families with no recorded split")
    sub.add_argument("--model", action="append", default=[], help="study id of a model to plan for (repeatable)")
    sub.add_argument("--tokenization", type=Path, action="append", default=[], help="recorded token ids of the prompts")
    sub.add_argument("--mechanistic-families", type=int, default=0, help="size of the mechanistic subset")
    sub.add_argument("--mechanistic-seed", type=int)
    sub.add_argument("--previous-manifest", type=Path, help="an earlier manifest of this batch")
    sub.add_argument("--stem", help="lane stem of the batch, to look for existing measurements under trace_out/")
    sub.add_argument("--pairs-file", type=Path, help="a lane-readable pairs file to reconcile the contrasts with")
    sub.add_argument("--lexicon", type=Path, help="dialect lexicon; lexicon_entries are checked against it")
    sub.add_argument("--forbid", default=",;-", help="characters no text may use (default: %(default)r)")
    sub.add_argument("--max-words", type=int, default=40)
    sub.add_argument("--root", type=Path, default=INTAKE_ROOT, help=argparse.SUPPRESS)
    allow_root(sub)

    sub = add("capabilities", cmd_capabilities, "Print capability matrix rows.")
    sub.add_argument("--model", help="study id or Hugging Face id")
    sub.add_argument("--capabilities", type=Path, help="capability matrix file (default: the committed one)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except Refusal as exc:
        _emit({"status": "refused", "code": exc.code, "detail": str(exc)})
        return EXIT_REFUSED
    except RuntimeError as exc:
        if type(exc).__name__ not in CONFIG_ERRORS:
            raise
        _emit({"status": "config_error", "code": type(exc).__name__, "detail": str(exc),
               "note": "Not a refusal: the seal or policy could not be evaluated. Nothing was written."})
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
