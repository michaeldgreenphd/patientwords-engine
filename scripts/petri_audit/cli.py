"""Command line for the Petri lane (design memo section 13). Every subcommand
that could spend money refuses to run outside the conditions the lane sets:
`run` needs a target model spec, prices, a lock that matches, seeds that
validate, and a pre-flight bound under `max_spend`; `preflight` performs the
same checks and calls nothing.

    python -m scripts.petri_audit.cli validate-seeds [--seeds FILE] [--seed-id ID ...] [--wave N]
    python -m scripts.petri_audit.cli verify-lock [--lock FILE]
    python -m scripts.petri_audit.cli preflight --target SPEC --max-spend USD [--epochs N] [--token-limit N]
    python -m scripts.petri_audit.cli run --target SPEC --max-spend USD --out-dir DIR [--started-marker FILE] [...]
    python -m scripts.petri_audit.cli adapt --eval FILE --out-dir DIR --custody STR --max-spend USD [--run-params FILE] [...]
    python -m scripts.petri_audit.cli readapt-plan --params-file FILE --listing FILE --readapt-run-id ID [...] --out FILE
    python -m scripts.petri_audit.cli adapt --readapt PLAN --eval FILE --out-dir DIR [...]   (mode readapt)
    python -m scripts.petri_audit.cli spend-report --out FILE --run-id ID --target SPEC --max-spend USD [--eval FILE]
    python -m scripts.petri_audit.cli judge --run-dir DIR --judge-model SPEC --judge-max-spend USD [...]
    python -m scripts.petri_audit.cli judge-spend-report --run-dir DIR --judge-model SPEC --judge-max-spend USD
    python -m scripts.petri_audit.cli analyze --run-dir DIR
    python -m scripts.petri_audit.cli verify-chain --data-dir DIR
    python -m scripts.petri_audit.cli verify-run --run-dir DIR
    python -m scripts.petri_audit.cli run-summary --run-dir DIR --mode MODE [--raw-eval-dir DIR] [--seeds FILE] [...]
    python -m scripts.petri_audit.cli repro-pack --vendor V --publication-state S --run-dir DIR [...]
    python -m scripts.petri_audit.cli repro-pack --check | --record-sent VERSION --sent-to ROLE   (repro_pack.py)
    python -m scripts.petri_audit.cli rejudge-plan --params-file FILE --rejudge-run-id ID [...] --out PLAN   (mode rejudge)
    python -m scripts.petri_audit.cli rejudge --plan PLAN --started-dir DIR
    python -m scripts.petri_audit.cli rejudge-spend-report --plan PLAN --started-dir DIR
    python -m scripts.petri_audit.cli verify-rejudge (--plan PLAN | --dir DIR ... | --root DIR) [--runs-dir DIR]
    python -m scripts.petri_audit.cli rejudge-summary --plan PLAN [--seal-scan]
    python -m scripts.petri_audit.cli rejudge-rehearse --source-run STEM --out-root DIR   ($0, mock judge, local)

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

from . import readapt, rejudge, repro_pack
from .envlock import load_lock, report_lines, verify_lock
from .framework import ENV_LOCK, OUTCOME_REGISTRY, ROOT, SEED_FILE, load_json, sha256_file, write_json
from .manifest import bind_judgments, reseal_problems, verify_chain, verify_run
from .seal import sealed_registry, seed_texts_against_registry
from .seeds import conditions, load_seed_file, seed_digest, select_seeds, target_visible_strings, validate_seed
from .spend import (
    billing_channel,
    cache_booking_problems,
    dearest_price,
    judge_billing_channel,
    judge_key_routing_problems,
    openrouter_price_problems,
    preflight_bound,
    registry_spec_to_inspect,
    resolve_price,
    resolve_registry_price,
    target_provider_problems,
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


def cmd_build_adaptive_seeds(args: argparse.Namespace) -> int:
    """Derive the adaptive-auditor seed file from the scripted one (adaptive.adaptive_seed_file) and write it, or with
    --check compare it with the file on disk. The file is derived, never edited by hand."""
    from . import adaptive

    doc = adaptive.adaptive_seed_file(load_json(Path(args.source)), wave=args.wave)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    out = Path(args.out)
    if args.check:
        same = out.is_file() and out.read_text(encoding="utf-8") == text
        print(f"{out}: {'matches the derivation' if same else 'DIFFERS from the derivation; rebuild it'}")
        return 0 if same else 1
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}: {len(doc['seeds'])} adaptive seed(s) from {args.source}")
    return 0


def cmd_verify_lock(args: argparse.Namespace) -> int:
    report = verify_lock(load_lock(args.lock), harness_commit_known=not args.no_harness_commit, lock_path=args.lock)
    print("\n".join(report_lines(report)))
    return 0 if report.ok else 3


def _judge_price_problems(spec: str) -> list[str]:
    """`spend.openrouter_price_problems` for a registry-form judge spec. A
    spec that cannot be expanded to an Inspect name (a bare provider with no
    consumer_default) cannot be priced either, so it is a problem, not a crash."""
    try:
        return openrouter_price_problems(registry_spec_to_inspect(spec))
    except ValueError as exc:
        return [str(exc)]


def _preflight(args: argparse.Namespace) -> tuple[int, dict]:
    """Shared by preflight and run: the target and the judge each bill the
    account the lane books them to, seeds validate, lock matches, price
    resolves, bound fits. Returns (exit code, facts)."""
    # first, before the seeds, the seal or the lock are read: a direct-vendor target spelling (openai/..., google/...),
    # or a judge spec whose registry provider bills a third key (google:, GEMINI_API_KEY), bills its own vendor while
    # every spend guard books it to the Anthropic lane, so no amount of checking below makes it runnable (2026-09-23)
    routing_problems = target_provider_problems(args.target)
    auditor = getattr(args, "auditor_model", None)
    if auditor:
        # the auditor is billed and booked exactly as a target is: its spelling names Anthropic or OpenRouter
        routing_problems += [p.replace("target", "auditor", 1) for p in target_provider_problems(auditor)]
        if billing_channel([auditor]) != billing_channel([args.target]):
            routing_problems.append(f"auditor {auditor!r} bills the {billing_channel([auditor])} channel but target "
                                    f"{args.target!r} bills {billing_channel([args.target])}: one fire carries one "
                                    "commitment on one account")
    if args.judge_model:
        routing_problems += judge_key_routing_problems(args.judge_model)
    if routing_problems:
        for p in routing_problems:
            print(f"pre-flight: REFUSED - {p}", file=sys.stderr)
        return 5, {}
    seed_set = load_seed_file(args.seeds)
    seeds = select_seeds(seed_set, args.seed_id or None, args.wave)
    problems = {s["seed_id"]: validate_seed(s, seed_set) for s in seeds}
    modes = {s.get("mode") for s in seeds}
    for seed in seeds:
        # each controller executes its own mode only (task.run_mode): an autonomous seed runs under the adaptive
        # controller, which needs an auditor model, and a scripted one never meets an auditor (Codex round 2)
        if len(modes) > 1:
            problems[seed["seed_id"]].append(f"a run executes one mode; this selection mixes {sorted(map(str, modes))}")
        elif seed.get("mode") == "autonomous" and not auditor:
            problems[seed["seed_id"]].append("an autonomous seed needs --auditor-model (the adaptive auditor)")
        elif seed.get("mode") == "scripted" and auditor:
            problems[seed["seed_id"]].append("a scripted seed takes no auditor: nothing but data reaches the target")
        elif seed.get("mode") not in ("scripted", "autonomous"):
            problems[seed["seed_id"]].append(f"mode {seed.get('mode')!r} has no execution path")
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
        # an `openrouter:` judge needs a reviewed per-model price, as the target does below: the judge ceiling is
        # enforced per call at this price, and the catch-all it would otherwise take is not a reviewed rate
        judge_unpriced = _judge_price_problems(args.judge_model)
        if judge_unpriced:
            for p in judge_unpriced:
                print(f"pre-flight: REFUSED - judge {args.judge_model}: {p}", file=sys.stderr)
            return 5, {}
        judge_price = resolve_registry_price(args.judge_model)
        print(f"judge {args.judge_model}: {judge_billing_channel(args.judge_model)} channel, in {judge_price.input_per_mtok}/Mtok "
              f"out {judge_price.output_per_mtok}/Mtok ({judge_price.source})")
    # an `openrouter/` target without a reviewed per-model price is refused before the bound is computed from the
    # catch-all (2026-09-23): the bound, Inspect's cost_limit and the sidecar would all rest on an unreviewed rate
    target_unpriced = openrouter_price_problems(args.target)
    if auditor:
        target_unpriced += [f"(auditor) {p}" for p in openrouter_price_problems(auditor)]
    if target_unpriced:
        for p in target_unpriced:
            print(f"pre-flight: REFUSED - target {p}", file=sys.stderr)
        return 5, {}
    # and only once the cost sidecar books its prompt-cache tokens: Inspect counts them outside input_tokens, and a
    # reviewed price ~5% above list leaves no margin for them to be booked at $0 the way the catch-all did (review of
    # 2026-09-23). Not the judge: its per-call ceiling books OpenRouter's prompt_tokens, cached ones included
    target_cache = cache_booking_problems(args.target)
    if auditor:
        target_cache += [f"(auditor) {p}" for p in cache_booking_problems(auditor)]
    if target_cache:
        for p in target_cache:
            print(f"pre-flight: REFUSED - target {p}", file=sys.stderr)
        return 5, {}
    price = resolve_price(args.target)
    print(f"price {args.target}: in {price.input_per_mtok}/Mtok out {price.output_per_mtok}/Mtok ({price.source})")
    if auditor:
        # Inspect's per-sample token limit counts the auditor's calls with the target's (task.run_study), so the
        # bound prices every token at the dearest rate of either model
        auditor_price = resolve_price(auditor)
        print(f"price {auditor} (auditor): in {auditor_price.input_per_mtok}/Mtok out "
              f"{auditor_price.output_per_mtok}/Mtok ({auditor_price.source})")
        price = dearest_price(price, auditor_price)
    samples = sum(len(conditions(s)) for s in seeds)
    bound = preflight_bound(samples=samples, epochs=args.epochs, token_limit=args.token_limit, price=price,
                            judge_reserve_usd=args.judge_max_spend or 0.0, max_spend_usd=args.max_spend)
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
    from .task import build_auditor, build_target, run_study, study_task  # 3.12 only

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    task = study_task(facts["seed_set"], facts["seeds"])
    # max_spend is the target ceiling alone (the judge has its own); Inspect's cost_limit is per sample
    per_sample_cost = args.max_spend / max(1, facts["samples"] * args.epochs)
    # the limits the run actually passes to Inspect, for `adapt --run-params` to record in the manifest
    write_json(out_dir / "run_params.json", {
        "target": args.target, "auditor": args.auditor_model, "max_spend_usd": args.max_spend,
        "judge_max_spend_usd": args.judge_max_spend,
        "cost_limit_per_sample_usd": per_sample_cost, "token_limit_per_sample": args.token_limit,
        "epochs": args.epochs, "samples": facts["samples"], "log_model_api": args.log_model_api == "true",
        "journal_nonce": args.journal_nonce or None,
        "seed_ids": [s["seed_id"] for s in facts["seeds"]]})
    try:
        target_model = build_target(args.target, facts["seeds"])
        auditor_model = build_auditor(args.auditor_model) if args.auditor_model else None
    except Exception as exc:  # noqa: BLE001 - every construction failure precedes the first provider call
        # exit 11: nothing was called and the start marker was not written, so the workflow's fallback spend report
        # books nothing for this fire (2026-09-23: the marker used to be written before the model was built)
        reason = " ".join(str(exc).split())[:400]          # Inspect's messages span lines; the key variable is named late
        print(f"target {args.target!r} or auditor {args.auditor_model!r} could not be built ({type(exc).__name__}: "
              f"{reason}); no provider call was made and the start marker was not written", file=sys.stderr)
        return 11
    log = run_study(task, target=target_model, seeds=facts["seeds"], epochs=args.epochs, log_dir=out_dir / "logs",
                    token_limit=args.token_limit, cost_limit=per_sample_cost, log_model_api=args.log_model_api == "true",
                    started_marker=args.started_marker, auditor=auditor_model)
    print(f"eval {log.eval.eval_id} status {log.status}; log {log.location}")
    return 0 if log.status == "success" else 7


def readapt_pre_problems(args: argparse.Namespace, plan: dict) -> list[str]:
    """Mode readapt's refusals before the harness is imported and before anything is written: the output directory
    is the source run's own and holds only its landed target sidecar, still the bytes the plan bound; the log is
    the one that sidecar priced; and nothing names another fire's nonce."""
    out_dir = Path(args.out_dir)
    problems: list[str] = []
    if out_dir.name != plan.get("run_stem"):
        problems.append(f"--out-dir {out_dir.name} is not the source run's directory {plan.get('run_stem')!r}; a readapt "
                        "writes beside the sidecar that booked the source run's target spend")
    problems += readapt.run_dir_problems(out_dir.parent, out_dir.name)
    report = plan["target_report"]
    problems += readapt.eval_file_problems(args.eval, report["eval_log"])
    problems += readapt.kept_report_problems(out_dir / readapt.target_report_name(out_dir.name),
                                             expected_sha256=report["sha256"], eval_id=report["eval_id"])
    # the judge sidecars earlier readapts of this run committed are spend records already booked to their own fires:
    # still the set and the bytes the plan bound (a plan written before they were admitted binds none)
    problems += readapt.kept_prior_problems(out_dir, plan.get("prior_judge_reports") or [])
    if args.run_params:
        problems.append("--run-params is the run step's record; a readapt ran no run step and takes the per-sample "
                        "limits from the log's own config")
    if args.journal_nonce and args.journal_nonce != report["journal_nonce"]:
        problems.append(f"--journal-nonce {args.journal_nonce!r} is not the source fire's {report['journal_nonce']!r}; "
                        "the manifest's spend block describes the run that spent on the target")
    return problems


def write_target_report(out_dir: Path, manifest: dict, *, max_spend: float, judge_max_spend: float | None,
                        plan: dict | None = None) -> int:
    """`adapt --report`: the target cost sidecar, written once and never rewritten. A readapt (`plan`) leaves the
    source run's landed sidecar exactly as it is, after checking it is still the bytes the plan bound and prices the
    log just adapted: the target spend was booked when the source run failed, and booking it again, or changing
    the file the ledger already folded, would count it twice. Returns the exit code."""
    out_dir = Path(out_dir)
    path = out_dir / readapt.target_report_name(out_dir.name)
    if plan is not None:
        problems = readapt.kept_report_problems(path, expected_sha256=plan["target_report"]["sha256"],
                                                eval_id=manifest["eval_id"])
        for p in problems:
            print(f"refused: {p}", file=sys.stderr)
        if problems:
            return 11
        print(f"{path.name}: the source run's landed target cost sidecar, left unchanged (a readapt makes no target "
              "call and books no target spend)")
        return 0
    if path.exists():
        print(f"refused: {path.name} exists; a cost sidecar is never rewritten", file=sys.stderr)
        return 11
    usage = {r["model"]: r for r in manifest["usage"]["by_model"]}
    write_report_sidecar(path, run_id=manifest["run_id"], eval_id=manifest["eval_id"], model_usage=usage,
                         max_spend_usd=max_spend, judge_max_spend_usd=judge_max_spend, run_utc=manifest["created_utc"],
                         extra={"raw_eval_log_sha256": manifest["artifacts"]["raw_eval_log_sha256"],
                                "journal_nonce": manifest["spend"]["journal_nonce"]},
                         target=manifest["models"]["target"]["inspect_name"])
    return 0


def cmd_adapt(args: argparse.Namespace) -> int:
    plan = None
    if args.readapt:
        plan = load_json(args.readapt)
        problems = readapt_pre_problems(args, plan)
        for p in problems:
            print(f"refused before adapting: {p}", file=sys.stderr)
        if problems:
            return 11

    from .adapter import adapt_run  # 3.12 only

    seed_set = load_seed_file(args.seeds)
    run_params = load_json(args.run_params) if args.run_params else {}
    spend = {"max_spend_usd": args.max_spend, "judge_max_spend_usd": args.judge_max_spend,
             # the fire's nonce: given to adapt directly, else the one `run` recorded (PR B, 2026-09-18); a readapt
             # records the SOURCE fire's, the one whose target spend this log is
             "journal_nonce": (plan["target_report"]["journal_nonce"] if plan is not None
                               else args.journal_nonce or run_params.get("journal_nonce") or None),
             "cost_limit_per_sample_usd": args.cost_limit if args.cost_limit is not None
             else run_params.get("cost_limit_per_sample_usd"),
             "token_limit_per_sample": args.token_limit if args.token_limit is not None
             else run_params.get("token_limit_per_sample")}
    result = adapt_run(args.eval, seed_set, args.out_dir, custody=args.custody, spend=spend,
                       engine_sha=engine_sha(), lock_path=args.lock,
                       readapt=({"expected": plan["expected"], "provenance": readapt.provenance_block(plan)}
                                if plan is not None else None))
    m = result.manifest
    print(f"adapted {len(result.records)} record(s) into {result.out_dir}; refused {len(result.refused)}; "
          f"claim_grade_eligible={m['execution']['claim_grade_eligible']}")
    for k, v in m["execution"]["contract_checks"].items():
        print(f"  {k}: {v['status']}" + (f" ({v['detail']})" if v["detail"] else ""))
    if args.report:
        return write_target_report(Path(args.out_dir), m, max_spend=args.max_spend,
                                   judge_max_spend=args.judge_max_spend, plan=plan)
    return 0


def cmd_readapt_plan(args: argparse.Namespace) -> int:
    """Mode readapt, before the download: locate the source run's raw-log artifact in the REST listing, check the
    source run directory and its landed sidecar, find the source fire in the journal, and state what the log must
    record (scripts/petri_audit/readapt.py). Writes the plan the adapt step reads; makes no model call."""
    from .reconcile import read_journal

    try:
        params = load_json(args.params_file)
        if not isinstance(params, dict):
            raise readapt.ReadaptError(f"{args.params_file} holds a {type(params).__name__}, not the resolved params")
        seed_set = load_seed_file(params.get("seeds_file") or SEED_FILE)
        ids = str(params.get("seed_ids") or "").split()
        seeds = select_seeds(seed_set, ids or None, None if ids else int(str(params.get("wave"))))
        plan = readapt.plan(params=params, listing=load_json(args.listing), runs_dir=Path(args.runs_dir),
                            seed_ids=[s["seed_id"] for s in seeds], journal_entries=read_journal(args.journal),
                            readapt_run_id=args.readapt_run_id, readapt_run_attempt=args.readapt_run_attempt,
                            readapt_commit=args.readapt_commit,
                            # the adapt step compares these with the digests the source run's samples recorded
                            seed_digests={s["seed_id"]: seed_digest(s) for s in seeds})
    except (readapt.ReadaptError, ValueError, KeyError, OSError) as exc:
        print(f"readapt refused before the download: {exc}", file=sys.stderr)
        return 12
    write_json(Path(args.out), plan)
    art = plan["artifact"]
    print(f"readapt plan: source run {plan['source_run_id']} ({plan['run_stem']}, nonce "
          f"{plan['target_report']['journal_nonce']}), artifact {art['name']} id {art['id']} digest {art['digest']}, "
          f"expires {art['expires_at']}; log {plan['target_report']['eval_log']}; readapt nonce "
          f"{plan['readapt']['journal_nonce']}")
    return 0


def cmd_spend_report(args: argparse.Namespace) -> int:
    """A cost sidecar for an attempted run that produced no adapted report
    (the run failed, or adaptation did): priced from whatever the retained log
    records, the ceiling imputed for a priced target when the log records
    calls without usage or no log exists at all, exactly zero only for a
    zero-price target (Codex round 3)."""
    target = args.target
    model_usage: dict[str, dict] = {}
    extra: dict = {"spend_report_reason": args.reason, "eval_log": None, "run_status": None,
                   "journal_nonce": args.journal_nonce or None}
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
                                      "total_tokens": int(usage.total_tokens or 0),
                                      # Inspect counts cached tokens outside input_tokens; reprice_usage prices them
                                      "input_tokens_cache_read": usage.input_tokens_cache_read,
                                      "input_tokens_cache_write": usage.input_tokens_cache_write,
                                      "calls": 0, "calls_without_usage": 0}
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


def _readapt_judge_identity(run_dir: Path) -> dict:
    """The join key a readapt's judge sidecar carries: the readapt fire's nonce and the log's eval id, from the
    manifest's `readapt` block (scripts/petri_audit/readapt.py). A readapt makes no target call, so its fire
    reserved the judge's spend alone, and the judge writes into the SOURCE run's directory, whose target sidecar
    names the source fire; without its own nonce the judge's cost would be joined to that fire. Empty for a run
    adapted in the ordinary way (the judge sidecar is joined through its directory, as before), and for a run
    directory with no manifest yet."""
    path = Path(run_dir) / "manifest.json"
    if not path.is_file():
        return {}
    manifest = load_json(path)
    block = manifest.get("readapt") if isinstance(manifest, dict) else None
    if block is None:
        return {}
    nonce = block.get("readapt_journal_nonce") if isinstance(block, dict) else None
    if not isinstance(nonce, str) or not nonce:
        raise ValueError(f"{path}: the readapt block records no readapt_journal_nonce, so the judge's spend cannot be "
                         "joined to the fire that reserved it")
    return {"journal_nonce": nonce, "eval_id": manifest.get("eval_id")}


def _judge_report_path(run_dir: Path) -> Path:
    """The judge cost sidecar of the judge pass about to run in `run_dir`: `<dir>.judge.report.json` for a run
    adapted in the ordinary way; for a readapt, the name `readapt.judge_report_name` gives it from the manifest's
    `readapt` block, so a retry after a readapt whose judge failed writes beside the sidecar that failure
    committed instead of over it. Raises ValueError for a readapt block that names no usable workflow run."""
    run_dir = Path(run_dir)
    ordinary = run_dir / f"{run_dir.name}.judge.report.json"
    path = run_dir / "manifest.json"
    if not path.is_file():
        return ordinary
    manifest = load_json(path)
    block = manifest.get("readapt") if isinstance(manifest, dict) else None
    if block is None:
        return ordinary
    run_id = block.get("readapt_workflow_run_id") if isinstance(block, dict) else None
    try:
        return run_dir / readapt.judge_report_name(run_dir.name, run_id)
    except readapt.ReadaptError as exc:
        raise ValueError(f"{path}: the readapt block names no usable readapt_workflow_run_id ({exc}), so the judge's "
                         "sidecar cannot be named apart from an earlier readapt's") from None


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
    # a readapt's judge was reserved by the readapt fire, not the source fire its directory names; the sidecar carries
    # that fire's nonce and the log's eval id so reconciliation joins it to the right commitment (reconcile.py), and
    # it is named for the readapt's own workflow run, so an earlier readapt's sidecar in the same directory is never
    # read as this judge's (which would impute nothing for a judge that spent) and never rewritten
    try:
        identity: dict = _readapt_judge_identity(run_dir)
    except (OSError, ValueError) as exc:
        # the ceiling is still booked; the missing join key is named in the record rather than guessed
        identity = {"journal_nonce_unavailable": f"manifest.json could not be read ({type(exc).__name__}: {exc})"}
    try:
        report_path = _judge_report_path(run_dir)
    except (OSError, ValueError) as exc:
        # the ordinary name, which no readapt writes, so no earlier readapt's sidecar is taken for this one; the
        # reason the readapt name could not be formed is recorded beside the booked ceiling
        report_path = run_dir / f"{run_dir.name}.judge.report.json"
        identity["judge_report_name_unavailable"] = f"{type(exc).__name__}: {exc}"
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
    sidecar.update(identity)
    write_json(report_path, sidecar)
    print(f"judge spend report {report_path}: cost_usd {cost} ({basis}); {reason}")
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    # first, before the harness is imported or the run read: a judge spec whose registry provider bills a third key
    # (google:, GEMINI_API_KEY) bills its own vendor while the guard books it to the Anthropic lane. Pre-flight refuses
    # it before the target spends; this refuses it again for a judge step reached without that pre-flight (2026-09-23)
    routing_problems = judge_key_routing_problems(args.judge_model)
    if routing_problems:
        for p in routing_problems:
            print(f"refused before any judge call: {p}", file=sys.stderr)
        return 5
    # the workflow's pre-flight already refused an unreviewed `openrouter:` judge before the target spent; a judge pass
    # started on its own (a local re-judge of a landed run) never passed that pre-flight, so it is refused here too,
    # before the run is read, since the check needs nothing from the run or the harness
    unpriced = _judge_price_problems(args.judge_model)
    if unpriced:
        for p in unpriced:
            print(f"refused before any judge call: {p}", file=sys.stderr)
        return 5

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
    try:
        readapt_identity = _readapt_judge_identity(run_dir)
        # the sidecar's basename is run-unique (the ledger keys sidecars by filename, Codex round 2) and, under a
        # readapt, unique to the re-adapting workflow run, so a retry never rewrites an earlier readapt's sidecar
        report_path = _judge_report_path(run_dir)
    except ValueError as exc:
        print(f"refused before any judge call: {exc}", file=sys.stderr)
        return 9
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
    try:
        sidecar = run_judgments(plans, client, out_path=judgments_path, ceiling=ceiling,
                                judge_max_tokens=args.judge_max_tokens, labels=labels_from_manifest(manifest),
                                report_path=report_path,
                                sidecar_extra={"task": "petri-audit-judge", "run_id": manifest["run_id"],
                                               "eval_id": manifest["eval_id"], "billing_channel": channel,
                                               "price_source": price.source, "input_per_mtok": price.input_per_mtok,
                                               "output_per_mtok": price.output_per_mtok, **readapt_identity})
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


def cmd_reconcile_spend(args: argparse.Namespace) -> int:
    """Join the lane's paid journal entries to the landed cost sidecars on the fire nonce and name every gap
    (scripts/petri_audit/reconcile.py). Exit 1 only under --strict with problems; the report itself never fails."""
    from .reconcile import reconcile, render_markdown

    result = reconcile(args.journal, args.runs, args.dashboard, rejudge_dir=args.rejudge)
    print(render_markdown(result), end="")
    if args.json_out:
        write_json(Path(args.json_out), result)
    return 1 if (args.strict and result["problems"]) else 0


def cmd_verify_run(args: argparse.Namespace) -> int:
    """One run directory on its own (no chain file): the check a downloaded
    dry-run exports artifact can pass."""
    problems = verify_run(Path(args.run_dir))
    for p in problems:
        print(p, file=sys.stderr)
    print(f"{args.run_dir}: " + ("run directory verifies on its own" if not problems else f"{len(problems)} problem(s)"))
    return 0 if not problems else 6


def _seal_gate_summary(text: str, mode: str, run_dir: str | None) -> str:
    """The rendered summary is a publication (the job summary of a public
    repository), so it passes the holdout seal that every published file
    passes. The step is `always()`, so it runs after a rejected seal check
    too, and the text quotes manifest strings the seal never scanned (a
    refusal reason carries Inspect's sample error); a hit, an unchecked scan
    or a scan that fails to run withholds the summary in full and prints the
    verdict alone: a status and a count, never a phrase or a label."""
    from .seal import scan_strings, sealed_registry

    stem = Path(run_dir).name if run_dir else "no run directory"
    try:
        result = scan_strings([text], sealed_registry(), what="rendered run summary")
    except Exception as exc:  # noqa: BLE001 - fail closed: a summary that was not scanned is not published
        return (f"## Petri audit ({mode}, {stem}): summary withheld\n\nthe holdout seal scan of the rendered summary "
                f"did not run ({type(exc).__name__}: {exc}); the summary data is in the run-summary JSON under the "
                "runner's temp directory, which is not published\n")
    if result.status == "pass":
        return text
    return (f"## Petri audit ({mode}, {stem}): summary withheld\n\nholdout seal scan of the rendered summary: "
            f"**{result.status}** ({result.detail}); the summary is not published until the seal-check step's "
            "verdict is understood; its data is in the run-summary JSON under the runner's temp directory, which is "
            "not published\n")


def cmd_run_summary(args: argparse.Namespace) -> int:
    """The job summary (Markdown on stdout, JSON to --json-out): measured
    structure, usage status per model, cost, redaction counts, integrity.
    Reports its own gaps as `unavailable` and never fails the job. With
    `--seal-scan` the rendered text passes the holdout seal before it is
    printed (see `_seal_gate_summary`)."""
    from .summary import render_markdown, run_summary

    params = load_json(args.params_file) if args.params_file else None
    summary = run_summary(args.run_dir, mode=args.mode, raw_eval_dir=args.raw_eval_dir, seeds_path=args.seeds, params=params,
                          judge_started=args.judge_started_marker)
    if args.json_out:
        write_json(args.json_out, summary)
    try:
        text = render_markdown(summary)
    except Exception as exc:  # noqa: BLE001 - the summary step never fails the job over its own output
        text = (f"## Petri audit ({args.mode})\n\nrender failed: {type(exc).__name__}: {exc}; the summary data follows\n\n"
                "```json\n" + json.dumps(summary, indent=2, default=str) + "\n```\n")
    if args.seal_scan:
        text = _seal_gate_summary(text, args.mode, args.run_dir)
    print(text, end="")
    return 0


def cmd_rejudge_plan(args: argparse.Namespace) -> int:
    """Mode rejudge, before any call: every source run verifies and is chained, its judge of record is another judge
    under the same allowance, its output directory is free, and the judgments planned from its committed
    transcripts are exactly the ones its judge of record made (scripts/petri_audit/rejudge.py). Writes the plan the
    rejudge step reads; makes no model call."""
    from .reconcile import read_journal

    try:
        params = load_json(args.params_file)
        if not isinstance(params, dict):
            raise rejudge.RejudgeError(f"{args.params_file} holds a {type(params).__name__}, not the resolved params")
        journal = read_journal(args.journal) if Path(args.journal).is_file() else []
        plan = rejudge.make_plan(params=params, runs_dir=Path(args.runs_dir), rejudge_root=Path(args.rejudge_root),
                                 journal_entries=journal, workflow_run_id=args.rejudge_run_id,
                                 workflow_run_attempt=args.rejudge_run_attempt, commit=args.rejudge_commit)
    except (rejudge.RejudgeError, ValueError, KeyError, OSError) as exc:
        print(f"rejudge refused before any call: {exc}", file=sys.stderr)
        return 12
    write_json(Path(args.out), plan)
    print(f"rejudge plan: judge {plan['judge_model']} ({'rehearsal, $0' if plan['rehearsal'] else 'paid'}), fire "
          f"ceiling ${plan['judge_max_spend_usd']:.4f}, judge_max_tokens {plan['judge_max_tokens']}, nonce "
          f"{plan['fire']['journal_nonce']!r}")
    for source in plan["sources"]:
        est = source["estimate"]
        print(f"  {source['run_stem']}: {source['planned']} planned judgment(s), parity with the judge of record "
              f"{source['source']['judge_of_record']['judge_model']!r} exact; plan {source['plan_sha256'][:12]}; "
              f"{len(source['prior_judge_reports'])} earlier fire sidecar(s) kept")
        print(f"    expected ${est['expected_usd']:.4f}: {est['calls']} call(s), the judge of record's "
              f"{est['recorded_input_tokens']} input and {est['recorded_output_tokens']} output tokens at "
              f"{est['input_per_mtok']}/{est['output_per_mtok']} per Mtok ({est['price_source']}); "
              f"{est['calls_without_recorded_usage']} call(s) without recorded usage taken at their bound")
        print(f"    worst case ${est['worst_case_usd']:.4f}: the same input, every answer at {plan['judge_max_tokens']} "
              f"output tokens")
    total = plan["estimate"]
    print(f"  fire: expected ${total['expected_usd']:.4f} + last-call headroom ${total['last_call_headroom_usd']:.4f} = "
          f"${total['required_usd']:.4f} needed, worst case ${total['worst_case_usd']:.4f}, against the ceiling "
          f"${plan['judge_max_spend_usd']:.4f}")
    print("  the estimate ASSUMES the new judge's token counts are close to the judge of record's; a different "
          "tokenizer or longer answers move it, and the worst case bounds the answers")
    return 0


def cmd_rejudge(args: argparse.Namespace) -> int:
    """Mode rejudge's paid step (free for the mockllm/judge rehearsal): judge every planned judgment of each source
    run with the plan's judge, then write the analysis rows and the manifest. Exit 8 when the judge client raised
    (its sidecar is written and the outputs of that run are not)."""
    plan = load_json(args.plan)
    try:
        # the same pre-call routing check `cli judge` makes, for a plan reached without the plan step's
        if not plan["rehearsal"]:
            problems = rejudge.judge_spec_refusals(plan["judge_model"])
            if problems:
                raise rejudge.RejudgeError("; ".join(problems))
        outcome = rejudge.execute(plan, started_dir=Path(args.started_dir))
    except (rejudge.RejudgeError, ValueError, KeyError, OSError) as exc:
        # before a run's first call this is a refusal; after one, whatever that run's judge charged is in its sidecar
        print(f"rejudge stopped: {exc}", file=sys.stderr)
        return 13
    for r in outcome["results"]:
        if r["status"] in ("complete", "truncated"):
            c = r["counts"]
            print(f"{r['run_stem']}: {r['status']}; planned {c['planned']}, judged {c['judged']}, null {c['null']} "
                  f"(null share {c['null_share']}), not applicable {c['not_applicable']}; cost "
                  f"${float(r['cost_usd']):.4f}")
        else:
            print(f"{r['run_stem']}: {r['status']}" + (f" ({r.get('reason') or r.get('error')})"
                                                          if r.get("reason") or r.get("error") else ""))
    print(f"rejudge spent ${outcome['spent_usd']:.4f} of the fire's ${float(plan['judge_max_spend_usd']):.4f}")
    return 8 if outcome["aborted"] else 0


def cmd_rejudge_spend_report(args: argparse.Namespace) -> int:
    """The judge sidecar of every source run whose rejudge judge started and left none: that run's allotment of
    the fire's ceiling is booked (rejudge.impute_missing_reports). Nothing for a run that never started."""
    if not Path(args.plan).is_file():
        print("rejudge plan absent (the plan step refused or never ran): no judge started, nothing to book")
        return 0
    written = rejudge.impute_missing_reports(load_json(args.plan), Path(args.started_dir))
    for path in written:
        print(f"rejudge judge spend report {path}: the run's allotment of the fire's judge ceiling is booked")
    if not written:
        print("every rejudge judge that started left its own sidecar; nothing to impute")
    return 0


def cmd_verify_rejudge(args: argparse.Namespace) -> int:
    """Re-grade directories on their own (rejudge.verify_output), each against the source run it names; with
    --plan, the directories this fire wrote a manifest into (rejudge.fire_outputs), whatever happened to a later
    run. Once all of them verify: --copy-to copies each under it (`<slug>/<stem>`) for the artifact upload,
    --verified-list writes their paths one per line, and --stage-list writes exactly what the workflow stages (those
    directories and this fire's sidecars, an aborted run's included), one path per line. Nothing is written when
    any directory fails to verify."""
    import shutil

    runs_dir = Path(args.runs_dir)
    dirs: list[Path] = [Path(d) for d in args.dir]
    sidecars: list[Path] = []
    if args.root:
        dirs += rejudge.output_dirs(args.root)
    if args.plan:
        plan = load_json(args.plan)
        written, sidecars = rejudge.fire_outputs(plan)
        dirs += written
        root = Path(plan["rejudge_root"]) / plan["judge_slug"]
        for source in plan["sources"]:
            d = root / source["run_stem"]
            if d not in written:
                print(f"{d}: no re-grade written (not started, or its judge failed); nothing to verify or stage "
                      "but its sidecar, if any")
    ok, msg = verify_chain(runs_dir)
    problems = [] if ok else [f"{runs_dir}: the manifests chain does not verify ({msg})"]
    for d in dirs:
        found = rejudge.verify_output(d, runs_dir)
        problems += [f"{d}: {p}" for p in found]
        if not found:
            print(f"{d}: re-grade verifies on its own, and its source run still verifies")
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 6
    if args.copy_to:
        Path(args.copy_to).mkdir(parents=True, exist_ok=True)
        for d in dirs:
            dest = Path(args.copy_to) / d.parent.name / d.name
            shutil.copytree(d, dest)
        print(f"copied {len(dirs)} verified re-grade director{'y' if len(dirs) == 1 else 'ies'} to {args.copy_to}")
    if args.verified_list:
        Path(args.verified_list).write_text("".join(f"{d}\n" for d in dirs), encoding="utf-8")
    if args.stage_list:
        staged = [str(d) for d in dirs] + [str(p) for p in sidecars if p.parent not in dirs]
        Path(args.stage_list).write_text("".join(f"{p}\n" for p in staged), encoding="utf-8")
        print(f"to stage: {len(dirs)} verified re-grade director{'y' if len(dirs) == 1 else 'ies'} and "
              f"{len(staged) - len(dirs)} further sidecar(s) of this fire")
    return 0


def cmd_rejudge_summary(args: argparse.Namespace) -> int:
    """The rejudge job's summary: counts and cost per source run, never text (rejudge.render_summary). With
    --seal-scan it passes the holdout seal before it is printed, as run-summary does."""
    try:
        text = rejudge.render_summary(load_json(args.plan)) if Path(args.plan).is_file() else \
            rejudge.render_summary(None, plan_error="the plan step refused or never ran; see its log")
    except Exception as exc:  # noqa: BLE001 - the summary step never fails the job over its own output
        text = f"## Petri rejudge\n\nsummary render failed: {type(exc).__name__}: {exc}\n"
    if args.seal_scan:
        text = _seal_gate_summary(text, rejudge.MODE, None)
    print(text, end="")
    return 0


def recorded_seed_file(runs_dir: Path, stem: str) -> str:
    """The seed file a landed run recorded for its seeds (manifest `seeds[].file`, repository-relative), or the
    scripted seed file for a manifest that records none. A run whose seeds name more than one file is refused: no
    single file can be the one it ran from."""
    manifest = load_json(Path(runs_dir) / stem / "manifest.json")
    files = {s.get("file") for s in manifest.get("seeds") or [] if isinstance(s, dict) and s.get("file")}
    if len(files) > 1:
        raise rejudge.RejudgeError(f"{stem}: its manifest records seeds from more than one file ({sorted(files)}); "
                                   "pass --seeds")
    return str(ROOT / files.pop()) if files else str(SEED_FILE)


def cmd_rejudge_rehearse(args: argparse.Namespace) -> int:
    """The $0 rehearsal, locally: plan a rejudge of one landed run with the mock judge (every answer the first
    declared value), run it into --out-root (outside the repository), and verify the result. Makes no provider
    call, writes nothing under the checkout, and computes no register contrast (the analysis rows are the
    per-judgment projection only). Prints counts and digests, never text."""
    out_root = Path(args.out_root).resolve()
    repo = ROOT.resolve()
    if out_root == repo or repo in out_root.parents:
        print(f"refused: --out-root {out_root} is inside the repository; a rehearsal writes outside it, so nothing it "
              "writes can be committed or folded into the ledger", file=sys.stderr)
        return 2
    runs_dir = Path(args.runs_dir)
    try:
        source = rejudge.source_record(runs_dir, args.source_run)
        tokens = args.judge_max_tokens or source["judge_of_record"]["judge_max_tokens"]
        # the seed file the run recorded, unless --seeds names one (review of PR #50: the scripted default refused
        # every autonomous run, whose seeds live in the adaptive file)
        seeds_file = args.seeds or recorded_seed_file(runs_dir, args.source_run)
        params = {"mode": rejudge.MODE, "source_runs": args.source_run, "judge": "true",
                  "judge_model": rejudge.MOCK_JUDGE, "judge_max_spend": "0.01", "judge_max_tokens": str(tokens),
                  "commit_outputs": "false", "seeds_file": seeds_file, "_nonce": ""}
        plan = rejudge.make_plan(params=params, runs_dir=runs_dir, rejudge_root=out_root, journal_entries=[],
                                 workflow_run_id="0", workflow_run_attempt="1", commit="0" * 40)
        out_root.mkdir(parents=True, exist_ok=True)
        write_json(out_root / "plan.json", plan)
        outcome = rejudge.execute(plan, started_dir=out_root / "_started")
    except (rejudge.RejudgeError, ValueError, KeyError, OSError) as exc:
        print(f"rehearsal refused: {exc}", file=sys.stderr)
        return 12
    failed = 0
    for r in outcome["results"]:
        print(f"{r['run_stem']}: {r['status']}")
        if r["status"] not in ("complete", "truncated"):
            failed += 1
            continue
        d = Path(r["out_dir"])
        problems = rejudge.verify_output(d, runs_dir)
        m = load_json(d / rejudge.MANIFEST_NAME)
        c = m["counts"]
        print(f"  parity with judge of record {m['source']['judge_of_record']['judge_model']!r}: "
              f"{m['instrument']['parity_with_judge_of_record']}; plan {m['instrument']['plan_sha256'][:12]}")
        print(f"  planned {c['planned']}, judged {c['judged']}, null {c['null']}, not applicable "
              f"{c['not_applicable']} (judge of record: planned {m['source']['judge_of_record']['planned']}, "
              f"not applicable {m['source']['judge_of_record']['not_applicable']}); cost ${m['cost_usd']:.4f}")
        print(f"  null share {c['null_share']} (judge of record {c['judge_of_record_null_share']}); the judge of "
              f"record's recorded tokens: {m['estimate']['recorded_input_tokens']} in, "
              f"{m['estimate']['recorded_output_tokens']} out over {m['estimate']['calls']} call(s)")
        print(f"  analysis rows {m['artifacts']['analysis_rows']['rows']}; verify: "
              + ("clean" if not problems else "; ".join(problems)))
        failed += bool(problems)
    print(f"rehearsal outputs under {out_root}")
    return 0 if not failed else 6


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
        p.add_argument("--auditor-model", default=None,
                       help="Inspect model string of the adaptive auditor; required for autonomous seeds and refused "
                            "for scripted ones (docs/petri_adaptive_design.md)")

    p = sub.add_parser("validate-seeds")
    common_seeds(p)
    p.set_defaults(func=cmd_validate_seeds)

    p = sub.add_parser("build-adaptive-seeds", help="derive the adaptive-auditor seed file from the scripted seed file")
    p.add_argument("--source", default=str(SEED_FILE))
    p.add_argument("--out", default=str(ROOT / "docs" / "framework" / "petri_seeds_adaptive.draft.json"))
    p.add_argument("--wave", type=int, default=2)
    p.add_argument("--check", action="store_true", help="compare with the file on disk instead of writing it")
    p.set_defaults(func=cmd_build_adaptive_seeds)

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
    p.add_argument("--journal-nonce", default=None,
                   help="the fire's _nonce from the trigger file; recorded in run_params.json, the manifest and the cost sidecar")
    p.add_argument("--log-model-api", choices=["true", "false"], default="true",
                   help="retain every raw provider request/response in the (never committed) .eval; "
                        "false leaves generation_config_pinned unprovable, so the run cannot be claim-grade")
    p.add_argument("--started-marker", default=None,
                   help="file created once the target model is built, immediately before the eval; the workflow's "
                        "fallback spend report imputes the target ceiling only when it exists")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("adapt")
    common_seeds(p)
    common_lock(p)
    p.add_argument("--eval", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--custody", required=True, help="e.g. github_actions_artifact:90d")
    # no --target: the manifest's target, and the registry spec derived from it, come from the log itself (2026-09-23)
    p.add_argument("--max-spend", type=float, required=True)
    p.add_argument("--judge-max-spend", type=float, default=None)
    p.add_argument("--journal-nonce", default=None)
    p.add_argument("--cost-limit", type=float, default=None)
    p.add_argument("--token-limit", type=int, default=None)
    p.add_argument("--run-params", default=None,
                   help="the run_params.json `run` wrote beside its logs; supplies cost_limit and token_limit when not given")
    p.add_argument("--report", action="store_true",
                   help="also write the <dir>.report.json cost sidecar (under --readapt: check the landed one and leave it)")
    p.add_argument("--readapt", default=None,
                   help="mode readapt: the plan `readapt-plan` wrote; adapt the source run's log into its own directory, "
                        "beside its landed target sidecar, and record the provenance in the manifest")
    p.set_defaults(func=cmd_adapt)

    p = sub.add_parser("readapt-plan")
    p.add_argument("--params-file", required=True, help="the params job's resolved outputs, as JSON (mode readapt)")
    p.add_argument("--listing", required=True,
                   help="the REST listing of the source run's artifacts (GET .../actions/runs/{id}/artifacts), as JSON")
    p.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    p.add_argument("--journal", default=str(ROOT / "ops" / "trigger_journal.jsonl"))
    p.add_argument("--readapt-run-id", required=True, help="this workflow run's id (GITHUB_RUN_ID)")
    p.add_argument("--readapt-run-attempt", required=True, help="this workflow run's attempt (GITHUB_RUN_ATTEMPT)")
    p.add_argument("--readapt-commit", required=True, help="the commit this workflow run checked out (GITHUB_SHA)")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_readapt_plan)

    p = sub.add_parser("spend-report")
    p.add_argument("--out", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--max-spend", type=float, required=True)
    p.add_argument("--judge-max-spend", type=float, default=None)
    p.add_argument("--eval", default=None, help="the retained raw log, when one exists")
    p.add_argument("--run-utc", default=None)
    p.add_argument("--reason", default="run attempted but no adapted report exists")
    p.add_argument("--journal-nonce", default=None, help="the fire's _nonce, so the fallback sidecar reconciles with the journal")
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

    p = sub.add_parser("verify-run")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=cmd_verify_run)

    p = sub.add_parser("reconcile-spend")
    p.add_argument("--journal", default=str(ROOT / "ops" / "trigger_journal.jsonl"))
    p.add_argument("--runs", default=str(ROOT / "data" / "petri" / "runs"))
    p.add_argument("--rejudge", default=str(rejudge.DEFAULT_ROOT),
                   help="the rejudge root (data/petri/rejudge); its judge sidecars are joined to rejudge fires")
    p.add_argument("--dashboard", default=str(ROOT / "ops" / "dashboard.json"))
    p.add_argument("--json-out", default=None)
    p.add_argument("--strict", action="store_true", help="exit 1 when any problem is reported")
    p.set_defaults(func=cmd_reconcile_spend)

    p = sub.add_parser("run-summary")
    p.add_argument("--run-dir", default=None, help="the adapted run directory (absent under preflight)")
    p.add_argument("--mode", required=True, choices=["preflight", "dry_run", "run", readapt.MODE])
    p.add_argument("--raw-eval-dir", default=None, help="where the run step wrote the raw .eval (outside the checkout)")
    p.add_argument("--seeds", default=None, help="seed file, for the planned judge prompt sizes (no call is made)")
    p.add_argument("--params-file", default=None, help="the parameters the params job resolved, as JSON")
    p.add_argument("--json-out", default=None)
    p.add_argument("--judge-started-marker", default=None,
                   help="the workflow's judge-start marker file; when it exists, a judge that left no file is still reported")
    p.add_argument("--seal-scan", action="store_true",
                   help="pass the rendered text through the holdout seal before printing it; a hit or an unchecked scan "
                        "withholds the summary and prints the verdict alone")
    p.set_defaults(func=cmd_run_summary)

    p = sub.add_parser("rejudge-plan")
    p.add_argument("--params-file", required=True, help="the params job's resolved outputs, as JSON (mode rejudge)")
    p.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    p.add_argument("--rejudge-root", default=str(rejudge.DEFAULT_ROOT))
    p.add_argument("--journal", default=str(ROOT / "ops" / "trigger_journal.jsonl"))
    p.add_argument("--rejudge-run-id", required=True, help="this workflow run's id (GITHUB_RUN_ID)")
    p.add_argument("--rejudge-run-attempt", required=True, help="this workflow run's attempt (GITHUB_RUN_ATTEMPT)")
    p.add_argument("--rejudge-commit", required=True, help="the commit this workflow run checked out (GITHUB_SHA)")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_rejudge_plan)

    p = sub.add_parser("rejudge")
    p.add_argument("--plan", required=True, help="the plan `rejudge-plan` wrote")
    p.add_argument("--started-dir", required=True,
                   help="where a marker is written before each run's first judge call (outside the checkout); the "
                        "fallback `rejudge-spend-report` books the allotment of a run that started and left no sidecar")
    p.set_defaults(func=cmd_rejudge)

    p = sub.add_parser("rejudge-spend-report")
    p.add_argument("--plan", required=True)
    p.add_argument("--started-dir", required=True)
    p.set_defaults(func=cmd_rejudge_spend_report)

    p = sub.add_parser("verify-rejudge")
    p.add_argument("--plan", default=None, help="verify the re-grade directories this plan's fire wrote")
    p.add_argument("--dir", action="append", default=[], help="a re-grade directory (<root>/<judge slug>/<stem>)")
    p.add_argument("--root", default=None, help="verify every re-grade directory under this root")
    p.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    p.add_argument("--copy-to", default=None, help="copy every verified directory here once all of them verify")
    p.add_argument("--verified-list", default=None, help="write the verified directories here, one per line")
    p.add_argument("--stage-list", default=None,
                   help="write what the workflow stages here, one path per line: the verified directories and this "
                        "fire's sidecars (with --plan)")
    p.set_defaults(func=cmd_verify_rejudge)

    p = sub.add_parser("rejudge-summary")
    p.add_argument("--plan", required=True)
    p.add_argument("--seal-scan", action="store_true")
    p.set_defaults(func=cmd_rejudge_summary)

    p = sub.add_parser("rejudge-rehearse")
    p.add_argument("--source-run", required=True, help="a landed run stem under --runs-dir, e.g. run_36076994201_1")
    p.add_argument("--out-root", required=True, help="a directory outside the repository")
    p.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    p.add_argument("--seeds", default=None,
                   help="the seed file to plan from (default: the one the source run recorded in its manifest)")
    p.add_argument("--judge-max-tokens", type=int, default=None,
                   help="default: the source run's judge of record's allowance (any other is refused by the plan)")
    p.set_defaults(func=cmd_rejudge_rehearse)

    p = sub.add_parser("digest")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("repro-pack",
                       help="a deterministic vendor reproduction pack over landed runs (dist/, never committed); "
                            "--check audits pack freshness, --record-sent logs a send (scripts/petri_audit/repro_pack.py)")
    repro_pack.add_arguments(p)
    p.set_defaults(func=repro_pack.cmd_repro_pack)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
