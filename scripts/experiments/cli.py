"""Command line for the experiment package: ``python -m scripts.experiments.cli <command>``.

Everything here is offline. No command loads a model, opens a network connection or fires a trigger.

Commands: ``validate``, ``plan``, ``run-fixture``, ``collect``, ``compare``, ``bundle``, ``capabilities``.
Each prints one JSON object. Exit codes: 0 success; 1 the command finished and the run is not clean (an
attempt ended ``failed`` or ``invalid``, or ``collect --require-complete`` found missing tasks); 2 a refusal,
printed as ``{"status": "refused", "code": ..., "detail": ...}``; 3 a configuration error (the holdout seal or
the results policy could not be evaluated), which is not a refusal.

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
from scripts.experiments.common import PROTOCOL_SCHEMA, Refusal, digest, read_json, require, write_json
from scripts.experiments.compare import compare_run
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
    return EXIT_NOT_CLEAN if summary["by_state"]["failed"] or summary["by_state"]["invalid"] else EXIT_OK


def cmd_collect(args: argparse.Namespace) -> int:
    store = RunStore(args.run_dir, allow_roots=args.allow_root)
    collected = store.collect()
    assembly = collected["assembly"]
    _emit({"status": "collected", "collected": str(store.collected_path),
           "assembly_sha256": collected["assembly_sha256"], "complete": assembly["complete"],
           "by_state": assembly["by_state"], "counts": assembly["counts"],
           "missing": [f"{m['task_id']}.r{m['replicate']}" for m in assembly["missing"]],
           "uncertain": assembly["uncertain"], "duplicate_identical": assembly["duplicate_identical"],
           "reused_events": collected["metrics"]["reused_events"],
           "executed_attempts": collected["metrics"]["executed_attempts"]})
    return EXIT_NOT_CLEAN if args.require_complete and not assembly["complete"] else EXIT_OK


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
    bundle = build_bundle(args.run_dir, allow_roots=args.allow_root)
    out = write_json(args.out, bundle, args.allow_root)
    _emit({"status": "bundled", "bundle": str(out), "schema_version": bundle["schema_version"],
           "families": len(bundle["comparisons"]), "capability_rows": len(bundle["capability_rows"]),
           "by_state": bundle["execution"]["by_state"], "limitations": bundle["limitations"]})
    return EXIT_OK


def cmd_capabilities(args: argparse.Namespace) -> int:
    matrix = _matrix(args)
    rows = caps.rows_for_model(matrix, args.model)
    _emit({"schema_version": matrix["schema_version"], "as_of": matrix["as_of"],
           "status_order": matrix["status_order"], "model": args.model, "rows": rows})
    return EXIT_OK


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
    sub.add_argument("--require-complete", action="store_true", help="exit 1 when planned tasks are missing")
    allow_root(sub)

    sub = add("compare", cmd_compare, "Derive per-family comparison blocks from a collected run.")
    sub.add_argument("--run-dir", type=Path, required=True)
    sub.add_argument("--out", type=Path, required=True)
    allow_root(sub)

    sub = add("bundle", cmd_bundle, "Export the preview bundle from a collected run.")
    sub.add_argument("--run-dir", type=Path, required=True)
    sub.add_argument("--out", type=Path, required=True)
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
