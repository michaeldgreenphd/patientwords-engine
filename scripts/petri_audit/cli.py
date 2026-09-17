"""Command line for the Petri lane (design memo section 13). Every subcommand
that could spend money refuses to run outside the conditions the lane sets:
`run` needs a target model spec, prices, a lock that matches, seeds that
validate, and a pre-flight bound under `max_spend`; `preflight` performs the
same checks and calls nothing.

    python -m scripts.petri_audit.cli validate-seeds [--seeds FILE] [--seed-id ID ...] [--wave N]
    python -m scripts.petri_audit.cli verify-lock [--lock FILE]
    python -m scripts.petri_audit.cli preflight --target SPEC --max-spend USD [--epochs N] [--token-limit N]
    python -m scripts.petri_audit.cli run --target SPEC --max-spend USD --out-dir DIR [--log-model-api true|false] [...]
    python -m scripts.petri_audit.cli adapt --eval FILE --out-dir DIR --custody STR --max-spend USD [--run-params FILE] [...]
    python -m scripts.petri_audit.cli spend-report --out FILE --run-id ID --target SPEC --max-spend USD [--eval FILE]
    python -m scripts.petri_audit.cli judge --run-dir DIR --judge-model SPEC --judge-max-spend USD [...]
    python -m scripts.petri_audit.cli judge-spend-report --run-dir DIR --judge-model SPEC --judge-max-spend USD
    python -m scripts.petri_audit.cli analyze --run-dir DIR
    python -m scripts.petri_audit.cli verify-chain --data-dir DIR
    python -m scripts.petri_audit.cli run-summary --run-dir DIR --mode MODE [--raw-eval-dir DIR] [--seeds FILE] [...]

Python 3.11 can run everything except `run` and `adapt`, which import the
harness and are 3.12 only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .envlock import load_lock, report_lines, verify_lock
from .framework import ENV_LOCK, OUTCOME_REGISTRY, ROOT, SEED_FILE, load_json, sha256_file, write_json
from .manifest import bind_judgments, reseal_problems, verify_chain
from .seal import sealed_registry, seed_texts_against_registry
from .seeds import conditions, load_seed_file, select_seeds, target_visible_strings, validate_seed
from .spend import (
    judge_billing_channel,
    preflight_bound,
    resolve_price,
    resolve_registry_price,
    usage_from_samples,
    write_report_sidecar,
)

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
    # the holdout seal is checked here, before any model call, not only at adaptation (Codex round 6): a seed that
    # copied a sealed phrase would otherwise expose the holdout to the target before the adapter refused publication
    registry_sealed = sealed_registry()
    if not registry_sealed:
        # an empty registry is not a clean scan (Codex round 7): without tierb.start_utc in the dashboard or the
        # Tier B batches, nothing can establish that the seeds carry no sealed phrase, so the run is refused
        print("holdout seal: the sealed registry is empty or unavailable (no tierb.start_utc in the dashboard, or no "
              "Tier B batches); the holdout cannot be established unexposed, so the run is refused before any model call",
              file=sys.stderr)
        return 6, {}
    # every string the target can receive, the tool definitions included (Codex round 8)
    sealed_hits = seed_texts_against_registry([s for seed in seeds for s in target_visible_strings(seed)], registry_sealed)
    if sealed_hits:
        print(f"holdout seal: {len(sealed_hits)} sealed phrase(s) in the selected seeds ({', '.join(sealed_hits[:5])}); "
              "the pilot uses the explore split only; refused before any model call", file=sys.stderr)
        return 6, {}
    print(f"holdout seal: {len(registry_sealed)} sealed phrases, no hit in the selected seeds")
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
    # the limits the run actually passes to Inspect, for `adapt --run-params` to record in the manifest
    write_json(out_dir / "run_params.json", {
        "target": args.target, "max_spend_usd": args.max_spend, "judge_max_spend_usd": args.judge_max_spend,
        "cost_limit_per_sample_usd": per_sample_cost, "token_limit_per_sample": args.token_limit,
        "epochs": args.epochs, "samples": facts["samples"], "log_model_api": args.log_model_api == "true",
        "seed_ids": [s["seed_id"] for s in facts["seeds"]]})
    log = run_study(task, target=args.target, seeds=facts["seeds"], epochs=args.epochs, log_dir=out_dir / "logs",
                    token_limit=args.token_limit, cost_limit=per_sample_cost, log_model_api=args.log_model_api == "true")
    print(f"eval {log.eval.eval_id} status {log.status}; log {log.location}")
    return 0 if log.status == "success" else 7


def cmd_adapt(args: argparse.Namespace) -> int:
    from .adapter import adapt_run  # 3.12 only

    seed_set = load_seed_file(args.seeds)
    run_params = load_json(args.run_params) if args.run_params else {}
    spend = {"max_spend_usd": args.max_spend, "judge_max_spend_usd": args.judge_max_spend,
             "journal_nonce": args.journal_nonce,
             "cost_limit_per_sample_usd": args.cost_limit if args.cost_limit is not None
             else run_params.get("cost_limit_per_sample_usd"),
             "token_limit_per_sample": args.token_limit if args.token_limit is not None
             else run_params.get("token_limit_per_sample")}
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
                             extra={"raw_eval_log_sha256": m["artifacts"]["raw_eval_log_sha256"]},
                             target=m["models"]["target"]["inspect_name"])
    return 0


def cmd_spend_report(args: argparse.Namespace) -> int:
    """A cost sidecar for an attempted run that produced no adapted report
    (the run failed, or adaptation did): priced from whatever the retained log
    records, the ceiling imputed for a priced target when the log records
    calls without usage or no log exists at all, exactly zero only for a
    zero-price target (Codex round 3)."""
    target = args.target
    model_usage: dict[str, dict] = {}
    extra: dict = {"spend_report_reason": args.reason, "eval_log": None, "run_status": None}
    if args.eval:
        from inspect_ai.log import read_eval_log  # 3.12 only

        log = read_eval_log(str(args.eval))
        extra.update(eval_log=Path(args.eval).name, run_status=log.status, eval_id=log.eval.eval_id)
        # token counts from the sample aggregates, else from the retained events' own usage (Codex round 7: a row
        # with calls and zero tokens priced a paid call at zero); calls counted from the events
        model_usage = usage_from_samples(log.samples or [])
        if not model_usage and log.stats and log.stats.model_usage:
            for model, usage in log.stats.model_usage.items():
                model_usage[model] = {"input_tokens": int(usage.input_tokens or 0), "output_tokens": int(usage.output_tokens or 0),
                                      "total_tokens": int(usage.total_tokens or 0), "calls": 0, "calls_without_usage": 0}
    if not model_usage:
        # no evidence of what was spent: the target's usage is recorded as missing, which prices a paid target at the
        # ceiling and a zero-price target at zero
        model_usage[target] = {"input_tokens": None, "output_tokens": None, "calls": 0, "calls_without_usage": 0}
        extra["spend_report_reason"] += "; no usage recorded, ceiling imputed for a priced target"
    run_utc = args.run_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = write_report_sidecar(Path(args.out), run_id=args.run_id, eval_id=extra.get("eval_id") or args.run_id,
                                  model_usage=model_usage, max_spend_usd=args.max_spend,
                                  judge_max_spend_usd=args.judge_max_spend, run_utc=run_utc, extra=extra)
    print(f"spend report {args.out}: cost_usd {report['cost_usd']} ({report['cost_basis']}); {args.reason}")
    return 0


def cmd_judge_spend_report(args: argparse.Namespace) -> int:
    """The judge cost sidecar for a judge step that started and left none (the
    process died, or the client raised before run_judgments could write). A
    missing sidecar means the last call is unaccounted for whether or not
    earlier rows survived (the process may have died after a request was
    charged and before its row was flushed), and every call was admitted
    under `can_afford`, so the judge ceiling bounds the total: a priced judge
    is booked at its ceiling with the surviving rows' sum recorded beside it,
    a zero-price judge at zero (Codex rounds 4 and 5)."""
    from .judge_runner import TIER_TEMPERATURE, cumulative_counts, read_jsonl

    run_dir = Path(args.run_dir)
    report_path = run_dir / f"{run_dir.name}.judge.report.json"
    if report_path.is_file():
        print(f"{report_path} exists; nothing to impute")
        return 0
    judgments_path = run_dir / "judgments.jsonl"
    rows = read_jsonl(judgments_path)
    price = resolve_registry_price(args.judge_model)
    channel = judge_billing_channel(args.judge_model)
    zero_priced = price.input_per_mtok == 0 and price.output_per_mtok == 0
    rows_cost = round(sum(float(j.get("cost_usd") or 0.0) for j in rows), 8)
    if zero_priced:
        cost, basis = 0.0, "engine_repriced_from_inspect_model_usage"
        reason = f"judge step started and left no sidecar; zero-price judge, {len(rows)} row(s) survived"
    else:
        cost, basis = float(args.judge_max_spend), "ceiling_imputed:judge_aborted_without_sidecar"
        reason = (f"judge step started and left no sidecar; {len(rows)} row(s) survived summing to {rows_cost}, the last "
                  "call is unaccounted for, so the judge ceiling is booked")
    sidecar = {"run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "judgments_file": "judgments.jsonl",
               "judge_model": args.judge_model, "cost_usd": cost, "run_cost_usd": cost, "prior_cost_usd": 0.0,
               "rows_cost_usd": rows_cost, "cost_basis": basis, "max_spend_usd": float(args.judge_max_spend), "truncated": None, "aborted": True,
               "abort_error": None, "spend_report_reason": reason, "cumulative": cumulative_counts(rows),
               "judgments_sha256": sha256_file(judgments_path) if judgments_path.is_file() else None,
               "judge_max_tokens": args.judge_max_tokens, "temperature": TIER_TEMPERATURE,
               "task": "petri-audit-judge", "run_id": run_dir.name, "billing_channel": channel,
               "price_source": price.source, "input_per_mtok": price.input_per_mtok, "output_per_mtok": price.output_per_mtok}
    write_json(report_path, sidecar)
    print(f"judge spend report {report_path}: cost_usd {cost} ({basis}); {reason}")
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    from .adapter import read_records
    from .judge_runner import (
        TIER_TEMPERATURE,
        JudgeAborted,
        RegistryJudge,
        SpendCeiling,
        cumulative_counts,
        judge_settings_problems,
        labels_from_manifest,
        load_rubric,
        plan_run,
        read_jsonl,
        run_judgments,
    )

    run_dir = Path(args.run_dir)
    # Codex round 5: the run must be resealable before any paid call, or the rows and the sidecar would be written
    # and the binding would then find the run is no longer the chain head, leaving the manifest's digests stale
    refusals = reseal_problems(run_dir)
    if refusals:
        for r in refusals:
            print(f"refused before any judge call: {r}", file=sys.stderr)
        return 9
    manifest = load_json(run_dir / "manifest.json")
    # the judge of record is one spec under one generation setting: a bound judge or existing rows under another
    # spec or token allowance refuse the pass before any call, because dedupe_key carries the spec and a second
    # spec would re-judge every plan, and a second allowance would mix caps under one provenance (Codex rounds 7, 8)
    pinned = judge_settings_problems(run_dir, manifest, args.judge_model, args.judge_max_tokens)
    if pinned:
        for p in pinned:
            print(f"refused before any judge call: {p}", file=sys.stderr)
        return 10
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
    try:
        sidecar = run_judgments(plans, client, out_path=judgments_path, ceiling=ceiling,
                                judge_max_tokens=args.judge_max_tokens, labels=labels_from_manifest(manifest),
                                report_path=report_path,
                                sidecar_extra={"task": "petri-audit-judge", "run_id": manifest["run_id"],
                                               "eval_id": manifest["eval_id"], "billing_channel": channel,
                                               "price_source": price.source, "input_per_mtok": price.input_per_mtok,
                                               "output_per_mtok": price.output_per_mtok})
    except JudgeAborted as exc:
        # the sidecar was written before the exception reached here; the judgments are not bound (the manifest
        # keeps saying no judge of record ran) and the step fails, with the charged calls booked
        print(json.dumps(exc.sidecar, indent=2))
        print(f"judge aborted: {exc}; sidecar written, judgments not bound", file=sys.stderr)
        return 8
    # bind the judgment family into the manifest and reseal the chain head, so verify-chain covers it; the counts
    # are the run's, from the complete file, never this invocation's alone (Codex round 4)
    totals = cumulative_counts(read_jsonl(judgments_path))
    sealed = bind_judgments(run_dir, judgments_path=judgments_path, report_path=report_path,
                            judge_of_record={"judge_model": args.judge_model, "billing_channel": channel,
                                             "price_source": price.source, "judged_utc": sidecar["run_utc"],
                                             "cost_usd": sidecar["cost_usd"], "truncated": sidecar["truncated"],
                                             "planned": sidecar["planned"], "judged": totals["judged"],
                                             "null": totals["null"], "not_applicable": totals["not_applicable"],
                                             "judge_max_tokens": args.judge_max_tokens, "temperature": TIER_TEMPERATURE})
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


def cmd_run_summary(args: argparse.Namespace) -> int:
    """The job summary (Markdown on stdout, JSON to --json-out): measured
    structure, usage status per model, cost, redaction counts, integrity.
    Reports its own gaps as `unavailable` and never fails the job."""
    from .summary import render_markdown, run_summary

    params = load_json(args.params_file) if args.params_file else None
    summary = run_summary(args.run_dir, mode=args.mode, raw_eval_dir=args.raw_eval_dir, seeds_path=args.seeds, params=params)
    if args.json_out:
        write_json(args.json_out, summary)
    print(render_markdown(summary), end="")
    return 0


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
    p.add_argument("--run-params", default=None,
                   help="the run_params.json `run` wrote beside its logs; supplies cost_limit and token_limit when not given")
    p.add_argument("--report", action="store_true", help="also write the <dir>.report.json cost sidecar")
    p.set_defaults(func=cmd_adapt)

    p = sub.add_parser("spend-report")
    p.add_argument("--out", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--max-spend", type=float, required=True)
    p.add_argument("--judge-max-spend", type=float, default=None)
    p.add_argument("--eval", default=None, help="the retained raw log, when one exists")
    p.add_argument("--run-utc", default=None)
    p.add_argument("--reason", default="run attempted but no adapted report exists")
    p.set_defaults(func=cmd_spend_report)

    p = sub.add_parser("judge-spend-report")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--judge-model", required=True)
    p.add_argument("--judge-max-spend", type=float, required=True)
    p.add_argument("--judge-max-tokens", type=int, default=None)
    p.set_defaults(func=cmd_judge_spend_report)

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

    p = sub.add_parser("run-summary")
    p.add_argument("--run-dir", default=None, help="the adapted run directory (absent under preflight)")
    p.add_argument("--mode", required=True, choices=["preflight", "dry_run", "run"])
    p.add_argument("--raw-eval-dir", default=None, help="where the run step wrote the raw .eval (outside the checkout)")
    p.add_argument("--seeds", default=None, help="seed file, for the planned judge prompt sizes (no call is made)")
    p.add_argument("--params-file", default=None, help="the parameters the params job resolved, as JSON")
    p.add_argument("--json-out", default=None)
    p.set_defaults(func=cmd_run_summary)

    p = sub.add_parser("digest")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_digest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
