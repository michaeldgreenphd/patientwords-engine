"""Command line for the Petri lane (design memo section 13). Every subcommand
that could spend money refuses to run outside the conditions the lane sets:
`run` needs a target model spec, prices, a lock that matches, seeds that
validate, and a pre-flight bound under `max_spend`; `preflight` performs the
same checks and calls nothing.

    python -m scripts.petri_audit.cli validate-seeds [--seeds FILE] [--seed-id ID ...] [--wave N]
    python -m scripts.petri_audit.cli verify-lock [--lock FILE]
    python -m scripts.petri_audit.cli preflight --target SPEC --max-spend USD [--epochs N] [--token-limit N]
    python -m scripts.petri_audit.cli run --target SPEC --max-spend USD --out-dir DIR [--log-model-api true|false] [...]
    python -m scripts.petri_audit.cli adapt --eval FILE --out-dir DIR --custody STR --max-spend USD [...]
    python -m scripts.petri_audit.cli judge --run-dir DIR --judge-model SPEC --judge-max-spend USD [...]
    python -m scripts.petri_audit.cli analyze --run-dir DIR
    python -m scripts.petri_audit.cli verify-chain --data-dir DIR

Python 3.11 can run everything except `run` and `adapt`, which import the
harness and are 3.12 only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .envlock import load_lock, report_lines, verify_lock
from .framework import ENV_LOCK, OUTCOME_REGISTRY, ROOT, SEED_FILE, load_json, sha256_file
from .manifest import bind_judgments, verify_chain
from .seeds import conditions, load_seed_file, select_seeds, validate_seed
from .spend import judge_billing_channel, preflight_bound, resolve_price, resolve_registry_price, write_report_sidecar

DEFAULT_RUNS_DIR = ROOT / "data" / "petri" / "runs"


def engine_sha() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        return out.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def cmd_validate_seeds(args: argparse.Namespace) -> int:
    seed_set = load_seed_file(args.seeds)
    seeds = select_seeds(seed_set, args.seed_id or None, args.wave)
    bad = 0
    for seed in seeds:
        problems = validate_seed(seed, seed_set)
        status = "ok" if not problems else "REFUSED"
        print(f"{seed['seed_id']}: {status}; {len(conditions(seed))} condition(s), wave {seed['pilot_wave']}, "
              f"{seed['protocol']['register_exposure']}")
        for p in problems:
            print(f"  - {p}")
        bad += bool(problems)
    return 0 if not bad else 4


def cmd_verify_lock(args: argparse.Namespace) -> int:
    report = verify_lock(load_lock(args.lock), harness_commit_known=not args.no_harness_commit, lock_path=args.lock)
    print("\n".join(report_lines(report)))
    return 0 if report.ok else 3


def _preflight(args: argparse.Namespace) -> tuple[int, dict]:
    """Shared by preflight and run: seeds validate, lock matches, price resolves,
    bound fits. Returns (exit code, facts)."""
    seed_set = load_seed_file(args.seeds)
    seeds = select_seeds(seed_set, args.seed_id or None, args.wave)
    problems = {s["seed_id"]: validate_seed(s, seed_set) for s in seeds}
    for seed in seeds:
        if seed.get("mode") != "scripted":
            # the validator admits autonomous seeds as data; no task path executes them yet, and the scripted
            # controller must never be handed one (Codex round 2)
            problems[seed["seed_id"]].append(f"mode {seed.get('mode')!r} has no execution path; only scripted seeds run")
    if any(problems.values()):
        for sid, ps in problems.items():
            for p in ps:
                print(f"seed {sid}: {p}", file=sys.stderr)
        return 4, {}
    lock_report = verify_lock(load_lock(args.lock), harness_commit_known=not args.no_harness_commit, lock_path=args.lock)
    print("\n".join(report_lines(lock_report)))
    if not lock_report.ok:
        return 3, {}
    if args.judge_model:
        # a judge spec the registry cannot resolve must fail here, before the target spends (Codex round 2)
        from .judge_runner import judge_spec_problems

        judge_problems = judge_spec_problems(args.judge_model)
        if judge_problems:
            for p in judge_problems:
                print(p, file=sys.stderr)
            return 5, {}
        judge_price = resolve_registry_price(args.judge_model)
        print(f"judge {args.judge_model}: {judge_billing_channel(args.judge_model)} channel, in {judge_price.input_per_mtok}/Mtok "
              f"out {judge_price.output_per_mtok}/Mtok ({judge_price.source})")
    price = resolve_price(args.target)
    samples = sum(len(conditions(s)) for s in seeds)
    bound = preflight_bound(samples=samples, epochs=args.epochs, token_limit=args.token_limit, price=price,
                            judge_reserve_usd=args.judge_max_spend or 0.0, max_spend_usd=args.max_spend)
    print(f"price {args.target}: in {price.input_per_mtok}/Mtok out {price.output_per_mtok}/Mtok ({price.source})")
    print(f"pre-flight bound: {samples} sample(s) x {args.epochs} epoch(s) x {args.token_limit} tokens -> "
          f"${bound.total_usd:.4f} against max_spend ${args.max_spend:.4f} (target calls); "
          f"judge ceiling ${bound.judge_reserve_usd:.4f} is its own commitment, enforced per call")
    if not bound.within:
        print("pre-flight: REFUSED - the target worst case exceeds max_spend", file=sys.stderr)
        return 5, {}
    return 0, {"seed_set": seed_set, "seeds": seeds, "price": price, "bound": bound, "samples": samples}


def cmd_preflight(args: argparse.Namespace) -> int:
    code, _ = _preflight(args)
    print("preflight: clear (no model call made)" if code == 0 else f"preflight: refused ({code})")
    return code


def cmd_run(args: argparse.Namespace) -> int:
    code, facts = _preflight(args)
    if code:
        return code
    from .task import run_study, study_task  # 3.12 only

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    task = study_task(facts["seed_set"], facts["seeds"])
    # max_spend is the target ceiling alone (the judge has its own); Inspect's cost_limit is per sample
    per_sample_cost = args.max_spend / max(1, facts["samples"] * args.epochs)
    log = run_study(task, target=args.target, seeds=facts["seeds"], epochs=args.epochs, log_dir=out_dir / "logs",
                    token_limit=args.token_limit, cost_limit=per_sample_cost, log_model_api=args.log_model_api == "true")
    print(f"eval {log.eval.eval_id} status {log.status}; log {log.location}")
    return 0 if log.status == "success" else 7


def cmd_adapt(args: argparse.Namespace) -> int:
    from .adapter import adapt_run  # 3.12 only

    seed_set = load_seed_file(args.seeds)
    spend = {"max_spend_usd": args.max_spend, "judge_max_spend_usd": args.judge_max_spend,
             "journal_nonce": args.journal_nonce, "cost_limit_per_sample_usd": args.cost_limit,
             "token_limit_per_sample": args.token_limit}
    result = adapt_run(args.eval, seed_set, args.out_dir, custody=args.custody, spend=spend, registry_spec=args.target,
                       engine_sha=engine_sha(), lock_path=args.lock)
    m = result.manifest
    print(f"adapted {len(result.records)} record(s) into {result.out_dir}; refused {len(result.refused)}; "
          f"claim_grade_eligible={m['execution']['claim_grade_eligible']}")
    for k, v in m["execution"]["contract_checks"].items():
        print(f"  {k}: {v['status']}" + (f" ({v['detail']})" if v["detail"] else ""))
    if args.report:
        usage = {r["model"]: r for r in m["usage"]["by_model"]}
        write_report_sidecar(Path(args.out_dir) / f"{Path(args.out_dir).name}.report.json", run_id=m["run_id"],
                             eval_id=m["eval_id"], model_usage=usage, max_spend_usd=args.max_spend,
                             judge_max_spend_usd=args.judge_max_spend, run_utc=m["created_utc"],
                             extra={"raw_eval_log_sha256": m["artifacts"]["raw_eval_log_sha256"]})
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    from .adapter import read_records
    from .judge_runner import (
        RegistryJudge,
        SpendCeiling,
        labels_from_manifest,
        load_rubric,
        plan_run,
        run_judgments,
    )

    run_dir = Path(args.run_dir)
    manifest = load_json(run_dir / "manifest.json")
    records = read_records(run_dir / "transcripts.jsonl")
    seed_set = load_seed_file(args.seeds)
    plans = plan_run(records, manifest, seed_set.seeds, outcomes=load_json(OUTCOME_REGISTRY), rubric=load_rubric())
    # the judge spec is registry form (provider:model or a bare Anthropic id), so it is normalised before pricing
    price = resolve_registry_price(args.judge_model)
    channel = judge_billing_channel(args.judge_model)
    ceiling = SpendCeiling(args.judge_max_spend, price.input_per_mtok, price.output_per_mtok, args.judge_max_tokens)
    client = RegistryJudge(args.judge_model)
    judgments_path = run_dir / "judgments.jsonl"
    # the sidecar's basename is run-unique: the ledger keys sidecars by filename (Codex round 2)
    report_path = run_dir / f"{run_dir.name}.judge.report.json"
    sidecar = run_judgments(plans, client, out_path=judgments_path, ceiling=ceiling,
                            judge_max_tokens=args.judge_max_tokens, labels=labels_from_manifest(manifest),
                            report_path=report_path,
                            sidecar_extra={"task": "petri-audit-judge", "run_id": manifest["run_id"],
                                           "eval_id": manifest["eval_id"], "billing_channel": channel,
                                           "price_source": price.source, "input_per_mtok": price.input_per_mtok,
                                           "output_per_mtok": price.output_per_mtok})
    # bind the judgment family into the manifest and reseal the chain head, so verify-chain covers it
    sealed = bind_judgments(run_dir, judgments_path=judgments_path, report_path=report_path,
                            judge_of_record={"judge_model": args.judge_model, "billing_channel": channel,
                                             "price_source": price.source, "judged_utc": sidecar["run_utc"],
                                             "cost_usd": sidecar["cost_usd"], "truncated": sidecar["truncated"],
                                             "planned": sidecar["planned"], "judged": sidecar["judged"],
                                             "null": sidecar["null"], "not_applicable": sidecar["not_applicable"]})
    print(json.dumps(sidecar, indent=2))
    print(f"manifest resealed: judgments bound ({sealed['artifacts']['judgments_sha256'][:12]}), "
          f"identity {sealed['chain']['identity_sha256'][:12]} unchanged")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from .adapter import read_records
    from .judge_runner import analysis_rows, judged_value_counts

    run_dir = Path(args.run_dir)
    manifest = load_json(run_dir / "manifest.json")
    judgments = read_records(run_dir / "judgments.jsonl")
    seed_set = load_seed_file(args.seeds)
    rows = analysis_rows(judgments, manifest, seed_set.seeds)
    out = run_dir / "analysis_rows.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "estimator_eligible": sum(r["estimator_eligible"] for r in rows),
                      "exploratory_eligible": sum(r["exploratory_eligible"] for r in rows),
                      "run_claim_grade_eligible": bool(manifest["execution"]["claim_grade_eligible"]),
                      "by_key": judged_value_counts(judgments)}, indent=2))
    return 0


def cmd_verify_chain(args: argparse.Namespace) -> int:
    ok, msg = verify_chain(Path(args.data_dir))
    print(msg)
    return 0 if ok else 6


def cmd_digest(args: argparse.Namespace) -> int:
    for p in args.paths:
        print(f"{sha256_file(p)}  {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="petri_audit", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common_seeds(p: argparse.ArgumentParser) -> None:
        p.add_argument("--seeds", default=str(SEED_FILE))
        p.add_argument("--seed-id", action="append", default=[])
        p.add_argument("--wave", type=int, default=None)

    def common_lock(p: argparse.ArgumentParser) -> None:
        p.add_argument("--lock", default=str(ENV_LOCK))
        p.add_argument("--no-harness-commit", action="store_true")

    def common_spend(p: argparse.ArgumentParser) -> None:
        p.add_argument("--target", required=True, help="Inspect model string, e.g. anthropic/claude-haiku-4-5")
        p.add_argument("--max-spend", type=float, required=True)
        p.add_argument("--judge-max-spend", type=float, default=None)
        p.add_argument("--judge-model", default=None,
                       help="registry judge spec, resolved and priced before any target call when judging")
        p.add_argument("--epochs", type=int, default=1)
        p.add_argument("--token-limit", type=int, default=20000)

    p = sub.add_parser("validate-seeds")
    common_seeds(p)
    p.set_defaults(func=cmd_validate_seeds)

    p = sub.add_parser("verify-lock")
    common_lock(p)
    p.set_defaults(func=cmd_verify_lock)

    p = sub.add_parser("preflight")
    common_seeds(p)
    common_lock(p)
    common_spend(p)
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("run")
    common_seeds(p)
    common_lock(p)
    common_spend(p)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--log-model-api", choices=["true", "false"], default="true",
                   help="retain every raw provider request/response in the (never committed) .eval; "
                        "false leaves generation_config_pinned unprovable, so the run cannot be claim-grade")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("adapt")
    common_seeds(p)
    common_lock(p)
    p.add_argument("--eval", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--custody", required=True, help="e.g. github_actions_artifact:90d")
    p.add_argument("--target", default=None)
    p.add_argument("--max-spend", type=float, required=True)
    p.add_argument("--judge-max-spend", type=float, default=None)
    p.add_argument("--journal-nonce", default=None)
    p.add_argument("--cost-limit", type=float, default=None)
    p.add_argument("--token-limit", type=int, default=None)
    p.add_argument("--report", action="store_true", help="also write the <dir>.report.json cost sidecar")
    p.set_defaults(func=cmd_adapt)

    p = sub.add_parser("judge")
    common_seeds(p)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--judge-model", required=True)
    p.add_argument("--judge-max-spend", type=float, required=True)
    p.add_argument("--judge-max-tokens", type=int, default=300)
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("analyze")
    common_seeds(p)
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("verify-chain")
    p.add_argument("--data-dir", default=str(DEFAULT_RUNS_DIR))
    p.set_defaults(func=cmd_verify_chain)

    p = sub.add_parser("digest")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_digest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
