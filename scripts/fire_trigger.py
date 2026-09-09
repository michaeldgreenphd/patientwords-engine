"""Fire a push-to-run CI trigger safely: queue guard, key validation, spend ceiling ($0, local).

Every paid or networked workflow in this repo starts when its file under
.github/trigger/ changes on a pushed branch. Each workflow has a per-branch
concurrency group with cancel-in-progress: false - one running + one pending
run - so pushing a THIRD trigger change silently evicts the pending run. This
script is the only sanctioned way for agent sessions to fire triggers: it
journals every fire to ops/trigger_journal.jsonl, refuses a third stacked fire,
validates parameter keys against the workflow inputs (CI silently ignores
unknown keys, so a typo means a run with defaults - catching it locally is the
whole point), and enforces the daily spend ceiling from ops/dashboard.json for
the paid triggers (scenario-generation, model-evaluation).

Usage:
  python scripts/fire_trigger.py fire --trigger circuit-trace \
      --params '{"graph_model": "gemma-2-2b", "mode": "2panel", "_nonce": "x1"}' \
      --note "why this run fires"
  python scripts/fire_trigger.py resolve --trigger circuit-trace    # after the run lands
  python scripts/fire_trigger.py status
  python scripts/fire_trigger.py publish   # after exit 1: the push was rejected, main moved

A journal entry is ACTIVE while resolved and evicted are both false and it is
younger than MEDLANG_TRIGGER_EXPIRE_HOURS (default 8; chunked workflow runs
never exceed ~6h, so expiry is a safety valve for entries nobody resolved).
Paid entries record their max_spend, and the daily ceiling counts committed
spend = landed (dashboard) + in-flight (active paid entries fired today).

Resolving stamps resolved_utc. A fire of the SAME trigger within
MEDLANG_TRIGGER_SETTLE_MINUTES (default 15) of that stamp is refused (exit 6):
the resolved run may still occupy the GitHub concurrency group even though its
output landed locally, so firing now can enter the group as a third run and
silently supersede the still-pending run (the 2026-07-09 queue-eviction seam).
Pass --ignore-settle once the prior run is confirmed terminal in GitHub.

Exit codes: 0 fired/ok, 2 queue refusal, 3 bad params, 4 budget refusal,
5 no-op fire (trigger file already holds the params), 6 settle refusal (a
same-trigger run was resolved inside the settle window and may still hold the
GitHub concurrency group), 7 unwired trigger (no workflow on this branch reads
that trigger file, so the fire would run nothing), 1 git failure.
No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import contextlib
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRIGGERS = (
    "circuit-trace",
    "logits-eval",
    "activation-patching",
    "jlens-readout",
    "scenario-generation",
    "model-evaluation",
    "archive-renders",
    "advice-eval",
    "pab-probe",
)
# advice-eval: elicit AND judge spend Anthropic/provider tokens (2026-07-21)
# pab-probe: patient/assistant/sandbox legs bill the prepaid OpenRouter key and
# the evaluate stage bills Anthropic (2026-08-04, exploratory arm).
PAID_TRIGGERS = frozenset({"scenario-generation", "model-evaluation", "advice-eval", "pab-probe"})
# A circuit-trace fire with show_mitigation=true makes Anthropic translation
# calls (the only paid path outside PAID_TRIGGERS). Its cost has no max_spend
# param, so the guard imputes a conservative flat commitment per fire.
MITIGATION_IMPUTED_USD = 0.15

# Resting-state parks: the cheapest legitimate stage per trigger, with
# commit_outputs false wherever the workflow supports the key. A trigger file
# at rest is a loaded default any branch operation can pull (merges, rebases,
# and first-appearance pushes all fire the workflow), so its committed content
# must never be the last expensive thing that ran. Parking goes through the
# full fire path - journal, queue, settle, budget - and costs one cheap run
# per park; after that, every accidental re-fire runs this no-op instead.
# scenario-generation and model-evaluation have no commit flag (their archives
# always land), so their parks are 1-item haiku runs (~$0.002/accident).
PARK_TINY_PAIRS = "data/simulated/pairs_20260706T172135Z.json"  # 2-pair batch, known good
PARK_DEFAULTS = {
    "circuit-trace": {"mode": "2panel", "pairs_file": PARK_TINY_PAIRS, "sample_size": "1",
                      "offsets": "0", "commit_outputs": "false"},
    "logits-eval": {"models": "qwen3-1.7b", "pairs_file": PARK_TINY_PAIRS, "limit": "1",
                    "offset": "0", "commit_outputs": "false"},
    "activation-patching": {"pairs_file": PARK_TINY_PAIRS, "offsets": "0", "limit": "1",
                            "commit_outputs": "false"},
    "jlens-readout": {"models": "gemma-2-2b", "pairs_file": PARK_TINY_PAIRS, "limit": "1",
                      "offset": "0", "topn": "1", "lens_type": "JACOBIAN_LENS",
                      "save_raw": "false", "commit_outputs": "false"},
    "scenario-generation": {"task": "pairs", "num": "1", "topics": "general wellness",
                            "anthropic_model": "claude-haiku-4-5", "max_spend": "0.01"},
    "model-evaluation": {"model_selection": "claude-haiku-4-5", "scenario": "two_step",
                         "sample_size": "1", "pairs_file": PARK_TINY_PAIRS,
                         "max_spend": "0.01"},
    "archive-renders": {"tag": "park-noop", "runs": ["trace_out/pairs_20260706T172135Z"],
                        "no_pngs": "true"},
    # advice-eval: elicit over an archive whose (models x samples) cells are fully
    # covered plans 0 calls; judge off. A true $0 no-op even when re-fired.
    "advice-eval": {"stimuli_file": "data/advice/stimuli_20260827T141036Z.json",
                    "models": "anthropic:claude-haiku-4-5", "samples": "1",
                    "max_spend": "0.01", "judge": "false", "commit_outputs": "false"},
    # pab-probe: not parked - its workflow lives on the PAB branch only.
}
PARK_NOTE = ("PARK (resting-state rule): cheapest no-op default committed so branch operations "
             "that touch this trigger file re-run a $0/negligible stage instead of the last "
             "expensive fire; commit_outputs false where the workflow supports it. "
             "Owner-approved maintenance hardening, 2026-08-27.")


def is_mitigation_fire(trigger, params):
    return trigger == "circuit-trace" and str(params.get("show_mitigation", "")).lower() in ("true", "1")
DEFAULT_EXPIRE_HOURS = 8.0
DEFAULT_SETTLE_MINUTES = 15.0
DEFAULT_DAILY_CEILING_USD = 2.0
# The prepaid OpenRouter key's own daily ceiling (PAB-branch lanes model;
# minimal port 2026-08-07 for advice-eval fires whose models are all
# OpenRouter-routed - owner routing instruction, decisions Addendum 3).
DEFAULT_OPENROUTER_DAILY_CEILING_USD = 10.0


WORKFLOW_DIR_RELPATH = ".github/workflows"


def workflow_reads_trigger(repo, trigger: str) -> bool:
    """True when some workflow on this branch reads this trigger's file path.

    CI fires on a push that changes .github/trigger/<trigger>.json, so a trigger
    key is only live where a workflow names that path. Checked per branch: the
    same key can be wired on one branch and absent on another."""
    needle = f"{TRIGGER_DIR_RELPATH}/{trigger}.json"
    wf_dir = repo / WORKFLOW_DIR_RELPATH
    try:
        entries = sorted(wf_dir.iterdir())
    except OSError:
        return False
    for path in entries:
        if path.suffix not in (".yml", ".yaml"):
            continue
        try:
            if needle in path.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def fire_lane(trigger: str, params: dict) -> str:
    """Which prepaid account a fire bills: "anthropic" (default) or "openrouter".

    Only an advice-eval fire whose models spec names NO Anthropic model bills
    the OpenRouter key alone (registry: bare ids are Anthropic; provider specs
    starting anthropic: are Anthropic; everything else routes via OpenRouter
    or an OpenRouter-compatible endpoint). Mixed or ambiguous specs stay on
    the anthropic lane - fail closed."""
    if trigger != "advice-eval":
        return "anthropic"
    models = str(params.get("models") or "").strip()
    if not models:
        return "anthropic"  # workflow default is an Anthropic model
    specs = [s for s in models.replace(",", " ").split() if s]
    for spec in specs:
        provider = spec.split(":", 1)[0] if ":" in spec else ""
        if provider == "anthropic" or ":" not in spec:
            return "anthropic"
    return "openrouter"
JOURNAL_RELPATH = Path("ops") / "trigger_journal.jsonl"
DASHBOARD_RELPATH = Path("ops") / "dashboard.json"
OVERRIDES_RELPATH = Path("ops") / "budget_overrides.json"
TRIGGER_DIR_RELPATH = Path(".github") / "trigger"
GIT_HOOKS_RELPATH = Path(".githooks")
PUSH_BACKOFF_SECONDS = (2, 4, 8, 16)

# Exact key sets, each verified against its workflow's params-resolution heredoc
# (the push-path reads of .github/trigger/<name>.json). Unknown non-underscore
# keys are a hard error for EVERY trigger: CI silently ignores unknown keys, so
# a typo means a run with defaults that can cost money or evict queued runs.
KNOWN_KEYS = {
    # circuit_trace_evaluation.yml `defaults` dict (verified 2026-07-09): graph_model,
    # graph_models, mode, pairs_file, offsets, sample_size, screen_targets, show_mitigation,
    # commit_outputs, max_n_logits, desired_logit_prob, node_threshold, edge_threshold,
    # max_feature_nodes, generate_explanations, steer_validate, steer_boost, steer_placebo,
    # steer_strength, steer_boost_strength, steer_rank_offset, translation_model.
    "circuit-trace": frozenset({
        "graph_model", "graph_models", "mode", "pairs_file", "offsets", "sample_size",
        "screen_targets", "show_mitigation", "commit_outputs", "max_n_logits",
        "desired_logit_prob", "node_threshold", "edge_threshold", "max_feature_nodes",
        "generate_explanations", "steer_validate", "steer_boost", "steer_placebo",
        "steer_strength", "steer_boost_strength", "steer_rank_offset", "translation_model",
        "translation_placebo",
    }),
    # logits_evaluation.yml `defaults` dict (re-verified 2026-09-04): models, pairs_file,
    # limit, offset, commit_outputs, mode, layers, topk, dtype. `dtype` belongs to
    # mode: verify (float32 vs bfloat16); the other two modes ignore it.
    "logits-eval": frozenset({"models", "pairs_file", "limit", "offset", "commit_outputs",
                              "mode", "layers", "topk", "dtype"}),
    # activation_patching.yml `defaults` dict (verified 2026-07-09): pairs_file, limit,
    # layers, positions, model, offsets, commit_outputs.
    "activation-patching": frozenset({
        "pairs_file", "limit", "layers", "positions", "model", "offsets", "commit_outputs",
    }),
    # jlens_readout.yml `defaults` dict (verified 2026-07-11; lens_type and
    # steer_spec added 2026-07-14): models, pairs_file, limit, offset, topn,
    # lens_type, steer_spec, save_raw, commit_outputs.
    "jlens-readout": frozenset({
        "models", "pairs_file", "limit", "offset", "topn", "lens_type", "steer_spec",
        "save_raw", "commit_outputs",
    }),
    # scenario_generation.yml `defaults` dict (verified 2026-07-09): task, num, topics,
    # seed_pairs, feedback, phrase, term, target_token, num_baselines, dialects,
    # anthropic_model, max_spend, graph_models, trace_sample_size.
    "scenario-generation": frozenset({
        "task", "num", "topics", "seed_pairs", "feedback", "phrase", "term",
        "target_token", "num_baselines", "dialects", "anthropic_model", "max_spend",
        "graph_models", "trace_sample_size",
    }),
    # model_evaluation.yml `defaults` dict (verified 2026-07-12): model_selection,
    # max_spend, sample_size, scenario, pairs_file.
    "model-evaluation": frozenset({"model_selection", "scenario", "sample_size", "max_spend", "pairs_file"}),
    # archive_renders.yml push path reads exactly cfg["tag"], cfg["runs"],
    # cfg.get("no_pngs"), cfg.get("prune"), cfg.get("prune_only"),
    # cfg.get("allow_shrink") (verified 2026-09-08; the last two added then).
    "archive-renders": frozenset({"tag", "runs", "no_pngs", "prune", "prune_only", "allow_shrink"}),
    # advice_evaluation.yml `defaults` dict (verified 2026-07-22; gen_config
    # added 2026-08-21 with the generation mode): stimuli_file, models, arms,
    # samples, temperature, max_tokens, translator_model, max_spend, judge,
    # judge_model, judge_max_spend, rubric, offset, limit, commit_outputs,
    # restore_artifact_run_id (recovery merge of a killed run's uploaded
    # archive artifact before elicit resumes), restore_merge_fork, gen_config
    # (generation-only run: author new paired stimuli, skip elicitation),
    # judge_max_tokens (second-judge support 2026-08-21: per-call output cap
    # for provider-registry judge models).
    "advice-eval": frozenset({
        "stimuli_file", "models", "arms", "samples", "temperature", "max_tokens",
        "translator_model", "max_spend", "judge", "judge_model", "judge_max_spend",
        "judge_max_tokens", "rubric", "offset", "limit", "commit_outputs",
        "restore_artifact_run_id", "restore_merge_fork", "gen_config",
    }),
    # pab_probe.yml `defaults` dict (verified 2026-08-04 against the params
    # heredoc by tests/test_pab_ci_staged.py): stage, fork_ref, cases_file,
    # config_file, assistant, turns, run_dir, max_spend, commit_sidecar,
    # catalog_search, catalog_require, artifact_run_id,
    # generate_timeout_minutes.
    "pab-probe": frozenset({
        "stage", "fork_ref", "cases_file", "config_file", "assistant", "turns",
        "run_dir", "max_spend", "commit_sidecar", "catalog_search",
        "catalog_require", "artifact_run_id", "generate_timeout_minutes",
        "artifact_run_id_2",
    }),
}


def utc_now():
    return datetime.now(timezone.utc)


def iso_utc(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(stamp):
    """Datetime for an iso8601Z stamp, or None when it does not parse."""
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def expire_hours_from_env():
    """Expiry window in hours: a finite float > 0 from the environment, else the
    default (with a warning when the variable is set but unusable - a negative
    or non-finite value must not silently disable the queue guard)."""
    raw = os.environ.get("MEDLANG_TRIGGER_EXPIRE_HOURS", "")
    if not raw:
        return DEFAULT_EXPIRE_HOURS
    try:
        hours = float(raw)
    except ValueError:
        hours = None
    if hours is None or not math.isfinite(hours) or hours <= 0:
        print(
            f"warning: MEDLANG_TRIGGER_EXPIRE_HOURS={raw!r} is not a finite number > 0; "
            f"using the default {DEFAULT_EXPIRE_HOURS}",
            file=sys.stderr,
        )
        return DEFAULT_EXPIRE_HOURS
    return hours


def settle_minutes_from_env():
    """Settle window in minutes: a finite float > 0 from the environment, else the
    default (with a warning when the variable is set but unusable - a negative or
    non-finite value must not silently disable the settle guard)."""
    raw = os.environ.get("MEDLANG_TRIGGER_SETTLE_MINUTES", "")
    if not raw:
        return DEFAULT_SETTLE_MINUTES
    try:
        minutes = float(raw)
    except ValueError:
        minutes = None
    if minutes is None or not math.isfinite(minutes) or minutes <= 0:
        print(
            f"warning: MEDLANG_TRIGGER_SETTLE_MINUTES={raw!r} is not a finite number > 0; "
            f"using the default {DEFAULT_SETTLE_MINUTES}",
            file=sys.stderr,
        )
        return DEFAULT_SETTLE_MINUTES
    return minutes


def load_journal(path):
    """Journal entries from a JSON Lines file. Blank lines are skipped; unknown
    fields ride along untouched. Any other unparseable line is a hard stop
    (SystemExit) naming the line: fail closed, because a silently dropped entry
    undercounts the active queue (admitting an evicting third fire) and the
    next whole-file rewrite would erase it. The operator repairs by hand."""
    entries = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return entries
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            entry = None
        if not isinstance(entry, dict):
            raise SystemExit(
                f"corrupt journal line {lineno} in {path}: {line!r} - fix the journal by hand "
                "(a dropped entry would undercount the active queue and then be erased on rewrite)"
            )
        entries.append(entry)
    return entries


def save_journal(path, entries):
    """Atomic rewrite: serialize to a sibling tmp file, then os.replace over the
    journal, so a failed write can never leave a truncated file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    os.replace(tmp, path)


def entry_is_active(entry, now, expire_hours):
    """Active = not resolved, not evicted, and younger than expire_hours."""
    if entry.get("resolved") or entry.get("evicted"):
        return False
    fired = parse_utc(entry.get("fired_utc"))
    if fired is None:
        return False
    return (now - fired) < timedelta(hours=expire_hours)


def active_entries(entries, trigger, now, expire_hours):
    """Active entries for one trigger, oldest first (journal order breaks ties)."""
    active = [e for e in entries if e.get("trigger") == trigger and entry_is_active(e, now, expire_hours)]
    return sorted(active, key=lambda e: parse_utc(e["fired_utc"]))


def recently_resolved(entries, trigger, now, settle_minutes):
    """Entries for `trigger` resolved within the last settle_minutes, newest first.

    A resolved entry's GitHub run may still occupy the concurrency group even
    after its output lands locally; only entries carrying a parseable resolved_utc
    count (entries resolved before resolved_utc existed cannot gate a fire)."""
    hits = []
    for entry in entries:
        if entry.get("trigger") != trigger or not entry.get("resolved"):
            continue
        stamp = parse_utc(entry.get("resolved_utc"))
        if stamp is None:
            continue
        if (now - stamp) < timedelta(minutes=settle_minutes):
            hits.append(entry)
    return sorted(hits, key=lambda e: parse_utc(e["resolved_utc"]), reverse=True)


def validate_params(trigger, params):
    """ValueError on non-dict params or on any unknown non-underscore key.

    Every trigger's key set in KNOWN_KEYS is verified against its workflow's
    params-resolution heredoc; there is no warn-only tier."""
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}; expected one of {', '.join(TRIGGERS)}")
    if not isinstance(params, dict):
        raise ValueError(f"params must be a JSON object (dict), got {type(params).__name__}")
    keys = {str(k) for k in params if not str(k).startswith("_")}
    unknown = sorted(keys - KNOWN_KEYS[trigger])
    if unknown:
        raise ValueError(
            f"unknown {trigger} key(s) {unknown}: CI silently ignores unknown keys, so a typo "
            f"means a run with defaults; allowed keys: {sorted(KNOWN_KEYS[trigger])}"
        )
    # commit_outputs must be stated explicitly wherever the workflow supports it:
    # the push path defaults it to false, so omitting the key runs the whole
    # measurement and then silently discards the results at the commit gate
    # (seven meditron fires were lost this way before 2026-07-31).
    if "commit_outputs" in KNOWN_KEYS[trigger] and "commit_outputs" not in keys:
        raise ValueError(
            f"{trigger} params must state commit_outputs explicitly (\"true\" or \"false\"): "
            "the workflow's push-path default is false, which measures and then discards "
            "every output when the runner is reclaimed"
        )


def parse_max_spend(value):
    """Validated max_spend as a float, or None when unusable.

    Accepts str/int/float that parse to a finite number > 0. Rejects bool
    (float(True) == 1.0 would silently pass), NaN (every comparison with NaN
    is False, so it would sail past the ceiling), +/-inf, zero, and negatives.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def judge_is_on(params):
    return str(params.get("judge", "")).lower() in ("true", "1")


def fire_commitment(params):
    """(commitment, error) — the fire's full worst-case spend the daily
    ceiling must absorb: max_spend, plus judge_max_spend when the fire judges
    (advice-eval's judge pass has its own ceiling CI enforces separately; the
    guard would otherwise never see it — handoff rev 2 accounting gap). A
    judged fire without a usable judge_max_spend is invalid: CI would fall
    back to the workflow default, invisible to this guard."""
    max_spend = parse_max_spend(params.get("max_spend"))
    if max_spend is None:
        return None, (
            f"max_spend must be a finite number > 0 (str/int/float), got {params.get('max_spend')!r}"
        )
    if judge_is_on(params):
        judge = parse_max_spend(params.get("judge_max_spend"))
        if judge is None:
            return None, (
                "judge=true requires a usable judge_max_spend (finite number > 0): the judge "
                f"pass is a second ceiling the daily guard must count, got {params.get('judge_max_spend')!r}"
            )
        max_spend += judge
    return max_spend, None


def inflight_max_spend(entries, today, now, expire_hours, lane="anthropic"):
    """Sum of max_spend across ACTIVE journal entries of BOTH paid triggers
    fired on `today` (YYYY-MM-DD UTC): spend already committed to CI but not
    yet landed on the dashboard."""
    total = 0.0
    for entry in entries:
        # paid triggers always record max_spend; mitigation circuit-trace
        # entries record their imputed commitment the same way
        if entry.get("trigger") not in PAID_TRIGGERS and entry.get("max_spend") is None:
            continue
        if entry.get("lane", "anthropic") != lane:
            continue
        if not entry_is_active(entry, now, expire_hours):
            continue
        fired = parse_utc(entry.get("fired_utc"))
        if fired is None or fired.astimezone(timezone.utc).strftime("%Y-%m-%d") != today:
            continue
        pending = parse_max_spend(entry.get("max_spend"))
        if pending is not None:
            total += pending
    return total


def budget_check(params, dashboard, today, entries=(), now=None, expire_hours=DEFAULT_EXPIRE_HOURS,
                 overrides=None, trigger=None):
    """(kind, reason) against the daily spend ceiling for a paid trigger.

    kind is "ok", "ceiling" (over the daily ceiling - the only refusal
    --override-budget may bypass), or "invalid" (missing/unusable max_spend -
    never overridable). Committed spend = landed (spend.today.spent_usd when
    spend.today.date equals `today`) + in-flight (active paid journal entries
    fired today; see inflight_max_spend). Tolerates a missing/partial
    dashboard: ceiling defaults to DEFAULT_DAILY_CEILING_USD.
    """
    if "max_spend" not in params:
        return "invalid", "paid trigger params must include max_spend"
    max_spend, commit_err = fire_commitment(params)
    if max_spend is None:
        return "invalid", commit_err
    spend = dashboard.get("spend") if isinstance(dashboard, dict) else None
    if not isinstance(spend, dict):
        spend = {}
    lane = fire_lane(trigger or "", params)
    if lane == "openrouter":
        # Lanes model (minimal port 2026-08-07, PAB-branch precedent): a fire
        # that bills only the prepaid OpenRouter key counts against that key's
        # own daily ceiling. Dated owner overrides apply to the Anthropic
        # ceiling only ("for anthropic") and are ignored here.
        try:
            ceiling = float(spend.get("openrouter_daily_ceiling_usd",
                                      DEFAULT_OPENROUTER_DAILY_CEILING_USD))
        except (TypeError, ValueError):
            ceiling = DEFAULT_OPENROUTER_DAILY_CEILING_USD
        override_note = ""
    else:
        try:
            ceiling = float(spend.get("daily_ceiling_usd", DEFAULT_DAILY_CEILING_USD))
        except (TypeError, ValueError):
            ceiling = DEFAULT_DAILY_CEILING_USD
        override_note = ""
        ov = (overrides or {}).get(today)
        if isinstance(ov, dict):
            try:
                ceiling = float(ov["ceiling_usd"])
                override_note = f" [owner ceiling override for {today}: {ov.get('reason', 'no reason recorded')}]"
            except (KeyError, TypeError, ValueError):
                pass  # malformed override: fail closed to the standing ceiling
    today_rec = spend.get("today")
    landed = 0.0
    if isinstance(today_rec, dict) and today_rec.get("date") == today:
        # Channel-scoped guard (owner decision 2026-08-04 CHANNEL-SPLIT):
        # each lane counts the channel where the ledger records it. Dashboards
        # without the split fall back to the pooled figure — fail closed:
        # the other lane's spend then still blocks the day.
        if lane == "openrouter":
            raw = today_rec.get("openrouter_usd", today_rec.get("spent_usd", 0.0))
        else:
            raw = today_rec.get("anthropic_usd", today_rec.get("spent_usd", 0.0))
        try:
            landed = float(raw)
        except (TypeError, ValueError):
            landed = 0.0
    if now is None:
        now = utc_now()
    inflight = inflight_max_spend(entries, today, now, expire_hours, lane=lane)
    committed = landed + inflight
    if max_spend + committed > ceiling:
        return "ceiling", (
            f"max_spend {max_spend:.2f} + today's committed {committed:.2f} "
            f"(landed {landed:.2f} + in-flight {inflight:.2f}) "
            f"would exceed the daily ceiling {ceiling:.2f} USD [{lane} lane]{override_note}"
        )
    return "ok", (
        f"max_spend {max_spend:.2f} + today's committed {committed:.2f} "
        f"(landed {landed:.2f} + in-flight {inflight:.2f}) within the daily ceiling {ceiling:.2f} USD "
        f"[{lane} lane]{override_note}"
    )


def queue_view(entries, now, expire_hours):
    """Dashboard-shaped queue: {group: {running, pending}} from active journal
    entries, oldest active first."""
    view = {}
    for trigger in TRIGGERS:
        active = active_entries(entries, trigger, now, expire_hours)
        slots = [
            {"fired_utc": e.get("fired_utc", ""), "commit": e.get("commit", ""), "note": e.get("note", "")}
            for e in active[:2]
        ]
        view[trigger] = {
            "running": slots[0] if slots else None,
            "pending": slots[1] if len(slots) > 1 else None,
        }
    return view


def load_dashboard(path):
    """Dashboard dict; {} when the file is missing or does not parse."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_budget_overrides(path):
    """Owner-authorized dated ceiling raises: {"YYYY-MM-DD": {"ceiling_usd": N, "reason": "..."}}.

    A committed, self-expiring alternative to --override-budget (which stays
    forbidden in ops practice): the raise applies to exactly one UTC day and the
    authorization travels with the file in git. Missing or malformed file means
    no overrides - the guard fails closed to the standing ceiling.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def update_dashboard_queue(dash_path, trigger, entries, now, expire_hours):
    """Rewrite this trigger's queue group in ops/dashboard.json from the journal."""
    dashboard = load_dashboard(dash_path)
    dashboard.setdefault("schema_version", 1)
    queue = dashboard.get("queue")
    if not isinstance(queue, dict):
        queue = {}
    queue[trigger] = queue_view(entries, now, expire_hours)[trigger]
    dashboard["queue"] = queue
    dashboard["updated_utc"] = iso_utc(now)
    dashboard["updated_by"] = "session"
    dash_path = Path(dash_path)
    dash_path.parent.mkdir(parents=True, exist_ok=True)
    dash_path.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")


def _git(repo, *argv, env=None):
    merged = {**os.environ, **env} if env else None
    return subprocess.run(["git", "-C", str(repo), *argv], capture_output=True, text=True, env=merged)


@contextlib.contextmanager
def dashboard_side_effect(repo, keep):
    """Run a queue-block rewrite of ops/dashboard.json and, unless `keep`, put the
    file back exactly as it was. The daily Routine session is the dashboard's only
    committer (AGENTS.md, Single-writer); every other caller gets the journal update
    with no dashboard change left in its working tree. Byte-restore, not git
    checkout, so it also holds in a checkout that is not a git repo (the tests)."""
    path = repo / DASHBOARD_RELPATH
    before = path.read_bytes() if path.exists() else None
    yield
    if keep:
        return
    if before is None:
        if path.exists():
            path.unlink()
    else:
        path.write_bytes(before)


def ensure_git_hooks(repo):
    """Point core.hooksPath at .githooks so the pre-commit and pre-push guards run
    inside git for every caller in this checkout. Every subcommand does this on
    entry, so a fresh clone is guarded from the Routine's first `status` on; a
    directory that is not a git work tree (the tests) is left alone. Returns True
    when the setting was written."""
    if not (repo / GIT_HOOKS_RELPATH).is_dir():
        return False
    proc = _git(repo, "rev-parse", "--is-inside-work-tree")
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        return False
    return _git(repo, "config", "core.hooksPath", GIT_HOOKS_RELPATH.as_posix()).returncode == 0


@contextlib.contextmanager
def fire_token(repo):
    """One-shot proof for .githooks/pre-commit and pre-push that fire_trigger.py is
    the committer: the token file <git-dir>/pw_fire_token exists only inside this
    block and the same value travels in PW_FIRE_TOKEN in git's environment. Yields
    the env mapping to pass to _git. A checkout with no git dir gets the env and
    no file, which is harmless because no hook runs there."""
    proc = _git(repo, "rev-parse", "--git-dir")
    git_dir = proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else ".git"
    token_dir = Path(git_dir) if Path(git_dir).is_absolute() else repo / git_dir
    token_path = token_dir / "pw_fire_token"
    token = secrets.token_hex(16)
    try:
        try:
            token_path.write_text(token, encoding="utf-8")
        except OSError:
            pass
        yield {"PW_FIRE_TOKEN": token}
    finally:
        try:
            token_path.unlink()
        except (FileNotFoundError, OSError):
            pass


def _push_with_token(repo, branch, env=None, oid=None):
    """Push under the one-shot token. `env` is the mapping fire_token yielded when
    the caller already holds a token for the whole publish; without it this
    function takes its own for the push alone. With `oid`, push exactly that
    commit to refs/heads/<branch> rather than the branch name: a refspec source
    may be any object, and naming the branch would carry along whatever another
    process commits to it between the caller's validation and the push (or
    during a retry's backoff), uninspected, to a public repository."""
    refspec = f"{oid}:refs/heads/{branch}" if oid else branch
    if env is not None:
        return _git(repo, "push", "-u", "origin", refspec, env=env)
    with fire_token(repo) as own:
        return _git(repo, "push", "-u", "origin", refspec, env=own)


def _head_oid(repo):
    """HEAD's commit id, or None when git cannot say."""
    proc = _git(repo, "rev-parse", "--verify", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def git_publish(repo, paths, message, backoff=PUSH_BACKOFF_SECONDS):
    """git add + commit + push -u origin <current branch>, retrying the push
    with backoff on nonzero exit. Returns True on success. The only function
    that touches git - the --no-git path never reaches it. The commit and the
    push both run under one fire token, which is what lets a trigger-file change
    through .githooks/pre-commit and pre-push."""
    proc = _git(repo, "add", "--", *[str(p) for p in paths])
    if proc.returncode != 0:
        print(f"git add failed: {proc.stderr.strip()}", file=sys.stderr)
        return False
    with fire_token(repo) as env:
        proc = _git(repo, "commit", "-m", message, env=env)
        if proc.returncode != 0:
            print(f"git commit failed: {proc.stderr.strip() or proc.stdout.strip()}", file=sys.stderr)
            return False
        proc = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        if proc.returncode != 0:
            print(f"git rev-parse failed: {proc.stderr.strip()}", file=sys.stderr)
            return False
        branch = proc.stdout.strip()
        head = _head_oid(repo)                  # the commit just made: push it, not the branch name
        if head is None:
            print("git rev-parse HEAD failed", file=sys.stderr)
            return False
        for attempt, delay in enumerate((0,) + tuple(backoff)):
            if delay:
                print(f"push retry {attempt}/{len(backoff)} in {delay}s", file=sys.stderr)
                time.sleep(delay)
            proc = _push_with_token(repo, branch, env, oid=head)
            if proc.returncode == 0:
                return True
            print(f"git push failed: {proc.stderr.strip()}", file=sys.stderr)
    return False


MANIFEST_DIR_RELPATH = Path("render_archives")


def archive_tag_has_manifest(repo: Path, tag: str, remote_ref: str | None = None) -> bool | None:
    """Whether render_archives/<tag>.manifest.json exists at HEAD, at `remote_ref`
    (a fetched remote-tracking ref, when given), or in the working tree. Git first:
    the cloud checkouts exclude render_archives/ from the sparse cone, so the file
    is tracked but absent on disk. Returns None when git failed inside a work
    tree (an error is never read as "no manifest"); a directory that is not a git
    work tree (the tests) is answered from the filesystem alone."""
    rel = MANIFEST_DIR_RELPATH / f"{tag}.manifest.json"
    inside = _git(repo, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return (repo / rel).exists()
    for ref in ["HEAD"] + ([remote_ref] if remote_ref else []):
        proc = _git(repo, "ls-tree", "--name-only", ref, "--", rel.as_posix())
        if proc.returncode != 0:
            return None
        if proc.stdout.strip():
            return True
    return (repo / rel).exists()


def _param_is_true(value: object) -> bool:
    """The two spellings archive_renders.yml's as_bool reads as true."""
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def is_park_params(trigger: str, params: dict) -> bool:
    """True when `params` is exactly the lane's park: PARK_DEFAULTS[trigger] plus
    the script's own underscore keys with _parked true. Provenance by content,
    not by flag: a park is the resting-state no-op by definition (no PNGs, the
    park tag), so a fire that reproduces it exactly is one, whoever wrote it, and
    a retry through `publish` can recognise it without the park command path."""
    if trigger not in PARK_DEFAULTS or not _param_is_true(params.get("_parked")):
        return False
    return {k: v for k, v in params.items() if not k.startswith("_")} == PARK_DEFAULTS[trigger]


def refuse_reused_archive_tag(repo: Path, trigger: str, params: dict, *, reuse_tag: bool, parked: bool) -> int | None:
    """None when an archive-renders fire may proceed; else 8, with the refusal
    printed. A tag that already has a manifest on this branch, or on the branch's
    freshly fetched remote tip, names a Release whose asset the workflow uploads
    with --clobber. The duplicate p3 fire of 2026-09-08 (a misread journal)
    rebuilt an HTML-only bundle over a 405 MB asset and left 157 PNGs in neither
    the tree nor the Release until a recovery run put them back. The CI shrink
    guard (#15) now refuses that upload, but only after a runner has spun up and
    the asset been downloaded; refusing here is earlier and free.

    Exempt: `reuse_tag` (the operator means it: a superset re-archive, or a
    deliberate override with allow_shrink in the params; the CI guard still
    checks the result); `parked`, set by the park command path or recognised by
    content (is_park_params: the lane's PARK_DEFAULTS exactly, plus _parked), since
    a park re-fires its own no-op tag by design and uploads no PNGs (a `_parked`
    flag on any other params grants nothing); and prune_only fires, which upload
    nothing and reuse the tag whose Release already holds the PNGs by design.
    The remote tip is checked because CI's manifest commit can land after the
    local HEAD was cut; the local fire then fails its push, and the rebased
    retry must not carry a duplicate tag past this guard."""
    if trigger != "archive-renders" or reuse_tag or parked or _param_is_true(params.get("prune_only")):
        return None
    tag = str(params.get("tag", ""))
    if not tag:
        return None
    remote_ref = None
    inside = _git(repo, "rev-parse", "--is-inside-work-tree")
    if inside.returncode == 0 and inside.stdout.strip() == "true":
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch and branch != "HEAD" and _git(repo, "remote", "get-url", "origin").returncode == 0:
            fetched = _git(repo, "fetch", "origin", branch)
            if fetched.returncode != 0:
                print(f"refused: cannot fetch origin/{branch} to check whether tag {tag!r} already has a manifest "
                      f"there ({fetched.stderr.strip()}); the reused-tag guard needs the branch tip.", file=sys.stderr)
                return 8
            remote_ref = f"origin/{branch}"
    found = archive_tag_has_manifest(repo, tag, remote_ref)
    if found is None:
        print(f"refused: git could not tell whether {MANIFEST_DIR_RELPATH}/{tag}.manifest.json exists at HEAD"
              + (f" or {remote_ref}" if remote_ref else "") + "; the reused-tag guard fails closed on a git "
              "error. Repair the checkout (docs/fresh_session_bootstrap.md) and fire again.", file=sys.stderr)
        return 8
    if found:
        print(
            f"refused: {MANIFEST_DIR_RELPATH}/{tag}.manifest.json is already on this branch"
            + (f" or its remote tip {remote_ref}" if remote_ref else "") + f", so tag {tag!r} names a Release "
            "this fire would re-upload over with --clobber (the 2026-09-08 duplicate-fire incident). Pick a "
            "fresh tag for new runs. To re-archive the same tag on purpose (a superset, or with allow_shrink "
            "in the params), pass --reuse-tag; the CI shrink guard still checks the result.",
            file=sys.stderr,
        )
        return 8
    return None


def cmd_fire(args):
    repo = Path(args.repo).resolve()
    expire_hours = expire_hours_from_env()
    now = utc_now()

    # 1-2. Parse and validate params (trigger name already constrained by argparse choices).
    if args.params_file:
        try:
            raw = Path(args.params_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"refused: cannot read --params-file {args.params_file}: {exc}", file=sys.stderr)
            return 3
    else:
        raw = args.params
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"refused: params are not valid JSON ({exc})", file=sys.stderr)
        return 3
    try:
        validate_params(args.trigger, params)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3

    # 3. Queue guard: one running + one pending; a third push evicts the pending run.
    journal_path = repo / JOURNAL_RELPATH
    entries = load_journal(journal_path)
    actives = active_entries(entries, args.trigger, now, expire_hours)
    to_evict = None
    if len(actives) >= 2:
        if not args.force_evict:
            print(
                f"refused: {len(actives)} active journal entries for {args.trigger}. The workflow's "
                "concurrency group holds one running + one pending run; pushing a third trigger change "
                "silently evicts the pending run. Wait and `resolve` the landed run, or pass "
                "--force-evict to deliberately replace the pending one. Active entries:",
                file=sys.stderr,
            )
            for e in actives:
                print(f"  fired {e.get('fired_utc', '?')}  note={e.get('note', '')!r}", file=sys.stderr)
            return 2
        to_evict = actives[-1]  # newest active = the pending run this push will replace

    # 3b. Settle guard: a same-trigger entry resolved within the settle window may
    # still occupy the GitHub concurrency group even though its output landed
    # locally. Firing now can enter the group as a third run and let GitHub silently
    # supersede the still-pending run (the 2026-07-09 queue-eviction seam). Refuse
    # unless the operator confirms the prior run is terminal with --ignore-settle.
    if not args.ignore_settle:
        settle_minutes = settle_minutes_from_env()
        recent = recently_resolved(entries, args.trigger, now, settle_minutes)
        if recent:
            newest = recent[0]
            print(
                f"refused: a {args.trigger} entry was resolved at {newest.get('resolved_utc', '?')}, "
                f"within the {settle_minutes:g}-minute settle window; that run may still occupy the "
                "concurrency group in GitHub, so firing now risks entering as a third run and silently "
                "superseding the pending run (the queue-eviction seam). Wait out the settle window, or "
                "pass --ignore-settle once you have confirmed the prior run is terminal. Recently resolved:",
                file=sys.stderr,
            )
            for e in recent:
                print(f"  resolved {e.get('resolved_utc', '?')}  note={e.get('note', '')!r}", file=sys.stderr)
            return 6

    # 4. Budget guard for the paid triggers: committed = landed + in-flight max_spend.
    # Mitigation circuit-trace fires are paid too (Anthropic translation calls);
    # they carry no max_spend param, so a flat imputed commitment is used.
    max_spend = None
    if args.trigger in PAID_TRIGGERS or is_mitigation_fire(args.trigger, params):
        budget_params = params if args.trigger in PAID_TRIGGERS \
            else dict(params, max_spend=str(MITIGATION_IMPUTED_USD))
        dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
        overrides = load_budget_overrides(repo / OVERRIDES_RELPATH)
        kind, reason = budget_check(budget_params, dashboard, now.strftime("%Y-%m-%d"),
                                    entries=entries, now=now, expire_hours=expire_hours,
                                    overrides=overrides, trigger=args.trigger)
        if kind == "ok":
            print(reason)
        elif kind == "ceiling" and args.override_budget:
            print(f"warning: budget override in effect ({reason})", file=sys.stderr)
        else:
            print(f"refused: {reason}", file=sys.stderr)
            return 4
        # full commitment (max_spend + judge_max_spend on judged fires) so the
        # journal entry's in-flight figure matches what budget_check counted
        max_spend, _ = fire_commitment(budget_params)  # valid here: budget_check vetted it

    # 5. Refuse a fire no workflow on THIS branch can answer. A key in TRIGGERS
    # with no workflow reading its trigger path is worse than an unknown key:
    # unknown keys hard-error, but a known-but-unwired key validates, writes the
    # file, journals the fire, pushes - and runs nothing, leaving a journal entry
    # for a run that never existed (owner decision 2026-08-15, filed as "a control
    # with nothing behind it"). The key itself is NOT dropped: pab-probe is wired
    # on the PAB branch (.github/workflows/pab_probe.yml), so deleting it here
    # would strand that branch's tooling. The branch-local check is the fix.
    trigger_path = repo / TRIGGER_DIR_RELPATH / f"{args.trigger}.json"
    if not workflow_reads_trigger(repo, args.trigger):
        print(
            f"refused: no workflow on this branch reads {TRIGGER_DIR_RELPATH}/{args.trigger}.json - "
            "the fire would push, journal, and run nothing. Wire a workflow, or fire from the "
            "branch that has one.",
            file=sys.stderr,
        )
        return 7

    # 5b. archive-renders: refuse a tag whose Release already exists (see
    # refuse_reused_archive_tag for the incident and the exemptions).
    rc = refuse_reused_archive_tag(repo, args.trigger, params, reuse_tag=args.reuse_tag,
                                   parked=getattr(args, "parked", False) or is_park_params(args.trigger, params))
    if rc is not None:
        return rc
    content = json.dumps(params, separators=(",", ":")) + "\n"
    try:
        unchanged = trigger_path.read_text(encoding="utf-8") == content
    except OSError:
        unchanged = False
    if unchanged:
        print(
            f"refused: {trigger_path} already holds exactly this content - a push would not change "
            'the file, so the workflow would NOT fire; add a "_nonce" key to force a change',
            file=sys.stderr,
        )
        return 5

    # 6. Write trigger file + journal entry + dashboard queue (or describe, with --dry-run).
    entry = {
        "trigger": args.trigger,
        "fired_utc": iso_utc(now),
        "commit": "",
        "note": args.note,
        "resolved": False,
        "evicted": False,
    }
    if max_spend is not None:
        entry["max_spend"] = max_spend  # in-flight commitment budget_check will count
        entry["lane"] = fire_lane(args.trigger, params)  # which prepaid key the commitment holds
    if args.dry_run:
        print(f"[dry-run] would write {trigger_path}: {content.strip()}")
        if to_evict is not None:
            print(f"[dry-run] would mark evicted: fired {to_evict.get('fired_utc', '?')} "
                  f"note={to_evict.get('note', '')!r}")
        print(f"[dry-run] would append to {journal_path}: {json.dumps(entry)}")
        print(f"[dry-run] would update queue group {args.trigger!r} in {repo / DASHBOARD_RELPATH}")
        if not args.no_git:
            print(f"[dry-run] would git add/commit/push ('Fire {args.trigger}: {args.note}')")
        return 0
    if to_evict is not None:
        to_evict["evicted"] = True
        print(f"evicted pending entry: fired {to_evict.get('fired_utc', '?')} note={to_evict.get('note', '')!r}")
    entries.append(entry)
    trigger_path.parent.mkdir(parents=True, exist_ok=True)
    trigger_path.write_text(content, encoding="utf-8")
    save_journal(journal_path, entries)
    with dashboard_side_effect(repo, keep=args.keep_dashboard):
        update_dashboard_queue(repo / DASHBOARD_RELPATH, args.trigger, entries, now, expire_hours)

    # 7. Publish the trigger file and the journal, unless --no-git. The dashboard is
    # never committed here: its single committer is the daily Routine session.
    if not args.no_git:
        if not git_publish(repo, [trigger_path, journal_path],
                           f"Fire {args.trigger}: {args.note}"):
            print("fire written locally but git publish failed - resolve by hand", file=sys.stderr)
            return 1
    slot = "pending" if len(active_entries(entries, args.trigger, now, expire_hours)) > 1 else "running"
    print(f"fired {args.trigger} ({slot} slot); `resolve --trigger {args.trigger}` once the run lands")
    return 0


# Paths a fire commits. `publish` re-pushes only commits confined to these, so it
# cannot become a general tokened push around .githooks/pre-push and the Bash guard.
PUBLISHABLE_RELPATHS = (TRIGGER_DIR_RELPATH, JOURNAL_RELPATH)


def unpublished_commits(repo: Path, branch: str, head: str = "HEAD") -> tuple[int, list[str]]:
    """(count, changed paths) of commits on `head` that origin/<branch> lacks. Both
    from git; the caller has fetched, so origin/<branch> is current. `head` is a
    commit id once publish has chosen the commit it will push, so a commit
    another process adds to the branch meanwhile is outside the range."""
    count = _git(repo, "rev-list", "--count", f"origin/{branch}..{head}")
    if count.returncode != 0:
        raise RuntimeError(count.stderr.strip() or "git rev-list failed")
    # Every path any of those commits touches, not the merge-base-to-head diff: a
    # file added in one commit and deleted in a later one is absent from that
    # diff yet would be pushed, and this repository is public.
    changed = _git(repo, "log", "--format=", "--name-only", f"origin/{branch}..{head}")
    if changed.returncode != 0:
        raise RuntimeError(changed.stderr.strip() or "git log failed")
    return int(count.stdout.strip() or 0), sorted({line.strip() for line in changed.stdout.split("\n") if line.strip()})


def unpublished_merges(repo: Path, branch: str, head: str = "HEAD") -> list[str]:
    """Merge commits among the commits origin/<branch> lacks. `git log --name-only`
    omits a merge commit's own diff (--diff-merges=off is its default), so a
    path that only the merge result introduced - a file added while resolving
    the merge - is invisible to unpublished_commits; and a rebase onto a branch
    that has not moved leaves the merge in place. A fire is a linear commit, so
    the range must hold no merge at all."""
    proc = _git(repo, "rev-list", "--merges", f"origin/{branch}..{head}")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git rev-list --merges failed")
    return proc.stdout.split()


def _refuse_merges(merges: list[str], branch: str) -> int | None:
    if not merges:
        return None
    print(f"refused: the unpushed history holds {len(merges)} merge commit(s): " + ", ".join(m[:12] for m in merges)
          + ". `publish` inspects each commit's own diff, which git omits for a merge, so a file that only the "
          "merge result introduced would be pushed unseen to a public repository. Linearize by hand: check "
          f"`git show <merge>` for anything only the merge added, then `git rebase --force-rebase origin/{branch}` "
          "(it replays the non-merge commits and drops what only the merge result held), and `publish` again.",
          file=sys.stderr)
    return 3


def is_publishable(relpath: str) -> bool:
    """Exactly the journal, or exactly one known trigger's JSON file directly under
    the trigger directory. Nothing nested, nothing else: the repository is public
    and the tokened push publishes every commit it carries."""
    path = Path(relpath)
    if path == JOURNAL_RELPATH:
        return True
    return path.parent == TRIGGER_DIR_RELPATH and path.suffix == ".json" and path.stem in TRIGGERS


def _git_show(repo: Path, ref: str, relpath: str) -> str | None:
    """The file's content at `ref`, or None when git has no such blob."""
    proc = _git(repo, "show", f"{ref}:{relpath}")
    return proc.stdout if proc.returncode == 0 else None


def journal_at(repo: Path, ref: str) -> tuple[list[dict] | None, list[str]]:
    """(entries, problems) of the journal committed at `ref` (a commit id, or
    origin/<branch>). entries is None when `ref` has no journal. A line that is
    not a JSON object is a problem, never a skipped line: the same fail-closed
    rule as load_journal, because a line this check cannot read is one a rewrite
    would silently delete."""
    text = _git_show(repo, ref, JOURNAL_RELPATH.as_posix())
    if text is None:
        return None, []
    entries, problems = [], []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"{ref} journal line {lineno} is not JSON ({exc.msg}); repair it by hand before "
                            "publishing")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{ref} journal line {lineno} is not a JSON object ({line.strip()[:40]!r}); repair it "
                            "by hand before publishing")
            continue
        entries.append(entry)
    return entries, problems


def journal_entries_added(repo: Path, branch: str, ref: str | None = None) -> list[dict]:
    """Journal entries present locally but not at origin/<branch>: the entries the
    unpushed commits appended. Keyed on (trigger, fired_utc), which is what the
    ORDERED UNION rule dedupes on too. `ref` names the commit to read the local
    journal from; None reads the working tree (the uncommitted-fire case)."""
    remote, _ = journal_at(repo, f"origin/{branch}")
    before = {(e.get("trigger"), e.get("fired_utc")) for e in (remote or [])}
    if ref is None:
        local = load_journal(repo / JOURNAL_RELPATH)
    else:
        local = journal_at(repo, ref)[0] or []
    return [e for e in local if (e.get("trigger"), e.get("fired_utc")) not in before]


JOURNAL_MONOTONIC_FIELDS = {"resolved", "evicted", "resolved_utc"}


def journal_drops_remote_entries(repo: Path, branch: str, ref: str = "HEAD") -> list[str]:
    """Problems with the journal at `ref` relative to origin/<branch>'s: a line on
    either side that cannot be parsed, a remote entry missing (keyed on (trigger,
    fired_utc)), or one whose fields changed other than the monotonic
    resolve/evict updates (resolved and evicted stay JSON booleans and may go
    false to true only - entry_is_active reads any non-empty string as true, so
    the string "false" would hide a live run - and a resolve must carry a
    parseable resolved_utc, as cmd_resolve writes one: without it the entry
    leaves the queue and the settle guard both). A hand-resolved rebase conflict
    that took the local side would otherwise truncate the journal, and the
    guards would then approve a push that hides a live run."""
    remote, problems = journal_at(repo, f"origin/{branch}")
    if remote is None:
        return []                                   # no remote journal yet: nothing to preserve
    local_entries, local_problems = journal_at(repo, ref)
    problems.extend(local_problems)
    local = {(e.get("trigger"), e.get("fired_utc")): e for e in (local_entries or [])}
    for entry in remote:
        key = (entry.get("trigger"), entry.get("fired_utc"))
        mine = local.get(key)
        if mine is None:
            problems.append(f"missing remote entry {key[0]} fired {key[1]}")
            continue
        for field in ("resolved", "evicted"):
            if field in mine and not isinstance(mine[field], bool):
                problems.append(f"{key[0]} fired {key[1]}: {field} is {mine[field]!r}, not a JSON boolean")
        for field, value in entry.items():
            if field in JOURNAL_MONOTONIC_FIELDS:
                if field in ("resolved", "evicted") and value is True and mine.get(field) is not True:
                    problems.append(f"{key[0]} fired {key[1]}: {field} went true -> {mine.get(field)!r}")
                if field == "resolved_utc" and mine.get(field) != value:
                    problems.append(f"{key[0]} fired {key[1]}: resolved_utc changed")
            elif mine.get(field) != value:
                problems.append(f"{key[0]} fired {key[1]}: {field} changed")
        if mine.get("resolved") and not entry.get("resolved") and parse_utc(mine.get("resolved_utc")) is None:
            problems.append(f"{key[0]} fired {key[1]}: resolved without a parseable resolved_utc (the settle "
                            "guard needs it; cmd_resolve writes one)")
    return problems


def cmd_publish(args: argparse.Namespace) -> int:
    """Re-publish a fire whose push was rejected (exit 1: "fire written locally but git
    publish failed"), the case docs/operators_handbook.md section 4 covers. The
    trigger file, journal entry and commit already exist locally; main moved
    underneath (CI's output commits and other sessions interleave with every
    session's pushes), so the push was non-fast-forward. A hand `git push` is
    refused by .githooks/pre-push and the Bash guard because the commit carries a
    trigger-file change, which is correct: only this script may publish one. This
    subcommand is that publish: fetch, rebase the local commits onto the remote
    branch, and push under the one-shot fire token.

    It publishes a journaled fire and nothing else, and it re-runs the fire's
    guards against the state the rebase produced, because that state can differ
    from the one cmd_fire approved: the unpushed commits must change exactly one
    trigger file plus the journal, the journal must gain an active entry for that
    trigger (the fire), the trigger file must validate and be wired on this
    branch, the lane must still have room (queue and settle guards, other
    sessions may have fired meanwhile), and a paid fire must still fit under the
    ceiling with the rebased dashboard and journal. Any of those failing refuses
    with cmd_fire's exit code and leaves the rebased commits local. Never re-fires:
    a fire that failed to publish is still one fire."""
    repo = Path(args.repo).resolve()
    proc = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    branch = proc.stdout.strip() if proc.returncode == 0 else ""
    if not branch or branch == "HEAD":
        print("refused: not on a branch (detached HEAD); check out the branch the fire was made on",
              file=sys.stderr)
        return 3
    proc = _git(repo, "fetch", "origin", branch)
    if proc.returncode != 0:
        print(f"git fetch failed: {proc.stderr.strip()}", file=sys.stderr)
        return 1
    # A dirty checkout is never rebased over (git can finish a rebase with exit 0
    # and still leave an autostash's re-application conflicted). One dirty state
    # is the script's own: git_publish exits 1 before the commit too (a failed
    # `git add` or `git commit`), leaving the fire's two files written and
    # uncommitted while `rev-list` sees nothing ahead. That fire is committed here
    # under the token, exactly as cmd_fire would have; any other dirt is refused.
    rc = _commit_uncommitted_fire(repo, branch, args.dry_run)
    if rc is not None:
        return rc
    try:
        count, changed = unpublished_commits(repo, branch)
    except RuntimeError as exc:
        print(f"git failed: {exc}", file=sys.stderr)
        return 1
    if count == 0:
        print(f"nothing to publish: origin/{branch} already has every local commit")
        return 0
    try:
        rc = _refuse_merges(unpublished_merges(repo, branch), branch)
    except RuntimeError as exc:
        print(f"git failed: {exc}", file=sys.stderr)
        return 1
    if rc is not None:
        return rc
    rc = _publishable_fire(count, changed)
    if rc is not None:
        return rc
    trigger = next(Path(c).stem for c in changed if Path(c).parent == TRIGGER_DIR_RELPATH)
    if args.dry_run:
        print(f"[dry-run] would rebase {count} commit(s) onto origin/{branch}, re-run the {trigger} fire's "
              "guards, and push under the fire token: " + ", ".join(changed))
        return 0
    proc = _git(repo, "rebase", f"origin/{branch}")
    if proc.returncode != 0:
        _git(repo, "rebase", "--abort")
        print("rebase onto origin/" + branch + " failed and was aborted; the checkout is as it was before. "
              "Resolve by hand: `git pull --rebase origin " + branch + "`, and for a journal conflict keep "
              "both sides as an ORDERED UNION (docs/operators_handbook.md, section 4), then run `publish` "
              "again. Never re-fire.\n" + (proc.stderr.strip() or proc.stdout.strip()), file=sys.stderr)
        return 1
    unmerged = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout.strip()
    if unmerged:
        print("refused: the rebase left unmerged paths; resolve them by hand before publishing:\n" + unmerged,
              file=sys.stderr)
        return 1
    # From here on every check reads one commit id, captured now, never the branch
    # name: a commit another process adds to the branch while the checks run is
    # outside the range they inspect and outside the push. The one commit
    # `publish` itself may add (the journal correction) is verified to sit on
    # exactly this commit and to change only the journal.
    head = _head_oid(repo)
    if head is None:
        print("git rev-parse HEAD failed after rebase", file=sys.stderr)
        return 1
    try:
        count, changed = unpublished_commits(repo, branch, head)  # what the rebase left to push
        merges = unpublished_merges(repo, branch, head)           # a rebase onto an unmoved branch keeps a merge
    except RuntimeError as exc:
        print(f"git failed after rebase: {exc}", file=sys.stderr)
        return 1
    rc = _refuse_merges(merges, branch)
    if rc is not None:
        return rc
    rc = _publishable_fire(count, changed)
    if rc is not None:
        return rc
    rc, head = _revalidate_fire(repo, branch, trigger, args, head)
    if rc is not None:
        return rc
    try:
        count, changed = unpublished_commits(repo, branch, head)  # a corrected record adds a journal commit
        merges = unpublished_merges(repo, branch, head)
    except RuntimeError as exc:
        print(f"git failed before push: {exc}", file=sys.stderr)
        return 1
    rc = _refuse_merges(merges, branch) or _publishable_fire(count, changed)
    if rc is not None:
        return rc
    for attempt, delay in enumerate((0,) + tuple(PUSH_BACKOFF_SECONDS)):
        if delay:
            print(f"push retry {attempt}/{len(PUSH_BACKOFF_SECONDS)} in {delay}s", file=sys.stderr)
            time.sleep(delay)
        proc = _push_with_token(repo, branch, oid=head)
        if proc.returncode == 0:
            print(f"published {count} commit(s) ({head[:12]}) to origin/{branch}: " + ", ".join(changed))
            moved = _head_oid(repo)
            if moved != head:
                print(f"warning: {branch} moved to {(moved or '?')[:12]} during the push; only {head[:12]} was "
                      "validated and published, and the later commits stay local and unpublished.",
                      file=sys.stderr)
            return 0
        print(f"git push failed: {proc.stderr.strip()}", file=sys.stderr)
    print("publish failed after retries; the local commits are intact, run `publish` again once the "
          "remote is reachable", file=sys.stderr)
    return 1


def _commit_uncommitted_fire(repo: Path, branch: str, dry_run: bool = False) -> int | None:
    """None when the checkout is clean or held exactly one uncommitted fire that
    is now committed; else the refusal's exit code."""
    status = _git(repo, "status", "--porcelain", "--untracked-files=no").stdout
    dirty = sorted({line[3:].strip() for line in status.splitlines() if line.strip()})
    if not dirty:
        return None
    triggers = [Path(c).stem for c in dirty if Path(c).parent == TRIGGER_DIR_RELPATH]
    journal = JOURNAL_RELPATH.as_posix() in dirty
    if len(triggers) == 1 and journal and len(dirty) == 2 and triggers[0] in TRIGGERS:
        trigger = triggers[0]
        mine = [e for e in journal_entries_added(repo, branch)
                if e.get("trigger") == trigger and not e.get("resolved") and not e.get("evicted")]
        if len(mine) != 1:
            print(f"refused: the uncommitted trigger change for {trigger} is accompanied by {len(mine)} new active "
                  "journal entries, not one; repair the journal by hand before publishing.", file=sys.stderr)
            return 3
        note = mine[0].get("note", "")
        if dry_run:
            print(f"[dry-run] would commit the uncommitted {trigger} fire under the fire token ({note!r}), then "
                  "rebase, re-run its guards and push; nothing written")
            return 0
        proc = _git(repo, "add", "--", TRIGGER_DIR_RELPATH.as_posix() + f"/{trigger}.json", JOURNAL_RELPATH.as_posix())
        if proc.returncode != 0:
            print(f"git add failed: {proc.stderr.strip()}", file=sys.stderr)
            return 1
        with fire_token(repo) as env:
            proc = _git(repo, "commit", "-m", f"Fire {trigger}: {note}", env=env)
        if proc.returncode != 0:
            print(f"git commit failed: {proc.stderr.strip() or proc.stdout.strip()}", file=sys.stderr)
            return 1
        print(f"committed the uncommitted {trigger} fire (its earlier commit had failed): {note!r}")
        return None
    print("refused: the checkout has uncommitted changes to tracked files that are not one fire's trigger "
          "file plus its journal entry; commit or stash them first (a `resolve` leaves the journal modified: "
          "commit it, a journal-only commit publishes with the fire):\n" + "\n".join(dirty), file=sys.stderr)
    return 3


def _publishable_fire(count: int, changed: list[str]) -> int | None:
    """None when the unpushed commits look like one fire (exactly one trigger file
    plus the journal, nothing else); otherwise print the refusal and return 3."""
    foreign = [c for c in changed if not is_publishable(c)]
    if foreign:
        print(f"refused: the {count} unpushed commit(s) change files outside "
              f"{TRIGGER_DIR_RELPATH.as_posix()}/ and {JOURNAL_RELPATH.as_posix()}: "
              + ", ".join(foreign) + ". `publish` re-publishes a fire and nothing else; "
              "push other work with a plain `git push` from a commit that carries no trigger change.",
              file=sys.stderr)
        return 3
    triggers = [Path(c).stem for c in changed if Path(c).parent == TRIGGER_DIR_RELPATH]
    if not triggers:
        print("refused: no trigger file among the unpushed commits, so nothing here needs the fire token; "
              "push with a plain `git push`.", file=sys.stderr)
        return 3
    if len(triggers) > 1 or triggers[0] not in TRIGGERS:
        print("refused: a fire changes exactly one known trigger file; the unpushed commits change: "
              + ", ".join(triggers), file=sys.stderr)
        return 3
    if JOURNAL_RELPATH.as_posix() not in changed:
        print("refused: the trigger change carries no journal entry, so it is not a fire this script made; "
              "a trigger change without a journal record is never published.", file=sys.stderr)
        return 3
    return None


def _revalidate_fire(repo: Path, branch: str, trigger: str, args: argparse.Namespace,
                     head: str) -> tuple[int | None, str]:
    """cmd_fire's guards, re-run against commit `head` (what the rebase produced)
    for the fire its unpushed commits carry. Returns (None, commit to push) when
    it may be pushed - the commit is `head`, or the journal-correction commit
    made on top of it - else (the refusal's exit code, head), with the rebased
    commits left local for a later `publish`. The trigger file and journal are
    read from `head`, never from the working tree, so what is checked is what
    is pushed."""
    now = utc_now()
    expire_hours = expire_hours_from_env()
    rel = (TRIGGER_DIR_RELPATH / f"{trigger}.json").as_posix()
    try:
        text = _git_show(repo, head, rel)
        if text is None:
            raise ValueError(f"no {rel} at {head[:12]}")
        params = json.loads(text)
        validate_params(trigger, params)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"refused: {rel} at {head[:12]} does not hold a valid fire: {exc}", file=sys.stderr)
        return 3, head
    if not workflow_reads_trigger(repo, trigger):
        print(f"refused: no workflow on this branch reads {TRIGGER_DIR_RELPATH}/{trigger}.json - "
              "the push would run nothing.", file=sys.stderr)
        return 7, head
    # The rebase just integrated the remote tip: a manifest CI committed for this
    # tag after the fire was cut is at HEAD now, and the guard that ran before the
    # first push could not have seen it.
    rc = refuse_reused_archive_tag(repo, trigger, params, reuse_tag=getattr(args, "reuse_tag", False),
                                   parked=is_park_params(trigger, params))
    if rc is not None:
        return rc, head
    # The workflow's paths filter sees the push as a whole: a commit that restored
    # the trigger file after the fire leaves the final tree unchanged, so the push
    # would land, fire nothing, and leave a journal entry for a run that never
    # started.
    unchanged = _git(repo, "diff", "--quiet", f"origin/{branch}", head, "--", rel)
    if unchanged.returncode == 0:
        print(f"refused: {rel} is identical at origin/{branch} and {head[:12]}, so the push would change no "
              "trigger file and CI would run nothing while the journal entry held a queue slot. If the fire was "
              "undone on purpose, mark its journal entry \"evicted\": true by hand and push the journal "
              "with a plain `git push`.", file=sys.stderr)
        return 3, head
    dropped = journal_drops_remote_entries(repo, branch, head)
    if dropped:
        print(f"refused: the local journal does not preserve origin/{branch}'s entries (a hand-resolved conflict "
              "that took the local side?); every remote entry must survive with only resolve/evict updates. "
              "Restore them per the ORDERED UNION rule (docs/operators_handbook.md, section 4), commit, and "
              "`publish` again:\n  " + "\n  ".join(dropped), file=sys.stderr)
        return 3, head
    entries, problems = journal_at(repo, head)
    if entries is None or problems:
        print(f"refused: no readable journal at {head[:12]}:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 3, head
    added = {(e.get("trigger"), e.get("fired_utc")) for e in journal_entries_added(repo, branch, head)}
    # Taken from `entries` (not from journal_entries_added's separate parse) so
    # the corrections below land in the list save_journal writes.
    mine = [e for e in entries
            if (e.get("trigger"), e.get("fired_utc")) in added
            and e.get("trigger") == trigger and not e.get("resolved") and not e.get("evicted")]
    if not mine:
        print(f"refused: the unpushed journal lines add no active {trigger} entry, so the trigger change "
              "is not a journaled fire; nothing is published.", file=sys.stderr)
        return 3, head
    if len(mine) > 1:
        print(f"refused: the unpushed commits carry {len(mine)} active {trigger} fires; one push runs the lane "
              "once, with the last trigger content, so the earlier fire would never run while its journal "
              "entry held a queue slot and, if paid, a spend commitment. Keep one: mark the superseded "
              "entries \"evicted\": true in the journal by hand, commit, and `publish` again. Entries:",
              file=sys.stderr)
        for e in mine:
            print(f"  fired {e.get('fired_utc', '?')}  note={e.get('note', '')!r}", file=sys.stderr)
        return 3, head
    fire = mine[0]
    key = (fire.get("trigger"), fire.get("fired_utc"))
    others = [e for e in entries if (e.get("trigger"), e.get("fired_utc")) != key]
    paid = trigger in PAID_TRIGGERS or is_mitigation_fire(trigger, params)
    budget_params = None
    if paid:
        budget_params = params if trigger in PAID_TRIGGERS else dict(params, max_spend=str(MITIGATION_IMPUTED_USD))
    # Corrections to the fire's own record, applied in one journal-only commit
    # that publishes with the fire:
    # - a fire published long after it was made would carry a stale stamp into
    #   the accounting (budget counts in-flight entries fired today, the queue
    #   expires entries older than expire_hours): restamp to the publication
    #   time, the original kept alongside, when the entry is from another UTC
    #   day or older than an hour or than half the expiry window;
    # - a paid fire's max_spend and lane are what inflight_max_spend counts for
    #   the running job: they must equal what cmd_fire computes from the final
    #   params, not what a hand edit during conflict recovery left.
    corrections = []
    fired = parse_utc(fire.get("fired_utc"))
    threshold = min(timedelta(hours=1), timedelta(hours=expire_hours) / 2)
    if fired is None or fired.date() != now.date() or (now - fired) >= threshold:
        # setdefault: a restamped fire whose push then failed is restamped again
        # on the next publish, and the time it was actually made must survive
        fire.setdefault("fired_utc_original", fire.get("fired_utc"))
        fire["fired_utc"] = iso_utc(now)
        fire["published_utc"] = iso_utc(now)
        corrections.append(f"fired_utc {key[1]} -> {iso_utc(now)} (original kept as fired_utc_original)")
    if paid:
        expected_spend, error = fire_commitment(budget_params)
        if error:
            print(f"refused: {error}", file=sys.stderr)
            return 4, head
        expected_lane = fire_lane(trigger, params)
        if fire.get("max_spend") != expected_spend or fire.get("lane") != expected_lane:
            corrections.append(f"max_spend {fire.get('max_spend')!r} -> {expected_spend!r}, "
                               f"lane {fire.get('lane')!r} -> {expected_lane!r}")
            fire["max_spend"], fire["lane"] = expected_spend, expected_lane
    elif "max_spend" in fire or "lane" in fire:
        corrections.append("max_spend/lane removed: not a paid fire")
        fire.pop("max_spend", None)
        fire.pop("lane", None)
    if corrections:
        save_journal(repo / JOURNAL_RELPATH, entries)
        proc = _git(repo, "add", "--", JOURNAL_RELPATH.as_posix())
        if proc.returncode == 0:
            proc = _git(repo, "commit", "-m", f"Journal: correct the {trigger} fire's record on publish "
                        f"(fired {key[1]}): " + "; ".join(corrections))
        if proc.returncode != 0:
            print(f"git failed while correcting the fire's record: {proc.stderr.strip() or proc.stdout.strip()}",
                  file=sys.stderr)
            return 1, head
        # The commit just made must sit on `head` and change only the journal;
        # otherwise another process committed to the branch meanwhile and the
        # correction now rides on a commit nothing here inspected.
        corrected = _head_oid(repo)
        parent = _git(repo, "rev-parse", "--verify", f"{corrected}^").stdout.strip() if corrected else ""
        touched = _git(repo, "diff", "--name-only", head, corrected or head).stdout.split()
        if corrected is None or parent != head or touched != [JOURNAL_RELPATH.as_posix()]:
            print(f"refused: {branch} moved from {head[:12]} to {(parent or '?')[:12]} while publish ran, so the "
                  f"journal correction commit {(corrected or '?')[:12]} sits on a commit nothing here inspected. "
                  "Nothing is pushed. Inspect the branch, drop what does not belong, and `publish` again.",
                  file=sys.stderr)
            return 3, head
        print(f"corrected the {trigger} fire's journal record: " + "; ".join(corrections))
        head = corrected
    # 3. Queue guard, as cmd_fire ran it before appending this entry: other
    # sessions may have filled the lane while this fire sat unpublished.
    actives = active_entries(others, trigger, now, expire_hours)
    if len(actives) >= 2:
        print(f"refused: {len(actives)} other {trigger} entries are active in the rebased journal; pushing "
              "this fire now would enter the concurrency group as a third run and silently evict the "
              "pending one. Wait, `resolve` the landed run, then `publish` again. Active entries:",
              file=sys.stderr)
        for e in actives:
            print(f"  fired {e.get('fired_utc', '?')}  note={e.get('note', '')!r}", file=sys.stderr)
        return 2, head
    # 3b. Settle guard.
    if not args.ignore_settle:
        settle_minutes = settle_minutes_from_env()
        recent = recently_resolved(others, trigger, now, settle_minutes)
        if recent:
            newest = recent[0]
            print(f"refused: a {trigger} entry was resolved at {newest.get('resolved_utc', '?')}, within the "
                  f"{settle_minutes:g}-minute settle window; pass --ignore-settle once that run is confirmed "
                  "terminal in GitHub, then `publish` again.", file=sys.stderr)
            return 6, head
    # 4. Budget guard, with the rebased dashboard and journal; the entry's own
    # max_spend is excluded from in-flight exactly as when cmd_fire approved it.
    if paid:
        dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
        overrides = load_budget_overrides(repo / OVERRIDES_RELPATH)
        kind, reason = budget_check(budget_params, dashboard, now.strftime("%Y-%m-%d"),
                                    entries=others, now=now, expire_hours=expire_hours,
                                    overrides=overrides, trigger=trigger)
        if kind == "ok":
            print(reason)
        elif kind == "ceiling" and args.override_budget:
            print(f"warning: budget override in effect ({reason})", file=sys.stderr)
        else:
            print(f"refused: {reason}", file=sys.stderr)
            return 4, head
    return None, head


def cmd_park(args):
    """Fire the resting-state park default for one trigger (or every parkable one).

    Each park is a real fire: it runs the full guard chain and costs one cheap
    run in that trigger's lane. With --all, triggers park sequentially and the
    first refusal stops the batch so the operator can read the guard's reason."""
    triggers = sorted(PARK_DEFAULTS) if args.all else [args.trigger]
    if not args.all and args.trigger not in PARK_DEFAULTS:
        print(f"refused: no park default for {args.trigger!r} (parkable: {sorted(PARK_DEFAULTS)})",
              file=sys.stderr)
        return 3
    for trigger in triggers:
        params = dict(PARK_DEFAULTS[trigger])
        params["_parked"] = "true"
        params["_nonce"] = iso_utc(utc_now())  # guarantee the file changes so the push fires
        ns = argparse.Namespace(
            repo=args.repo, trigger=trigger, params=json.dumps(params), params_file=None,
            note=PARK_NOTE, force_evict=False, ignore_settle=args.ignore_settle,
            reuse_tag=False, parked=True,  # the park path alone exempts its tag from the reused-tag refusal
            dry_run=args.dry_run, no_git=args.no_git, keep_dashboard=args.keep_dashboard,
            override_budget=False,
        )
        print(f"-- parking {trigger}")
        rc = cmd_fire(ns)
        if rc != 0:
            print(f"park stopped at {trigger} (exit {rc}); earlier parks stand", file=sys.stderr)
            return rc
    return 0


def cmd_resolve(args):
    repo = Path(args.repo).resolve()
    expire_hours = expire_hours_from_env()
    now = utc_now()
    journal_path = repo / JOURNAL_RELPATH
    entries = load_journal(journal_path)
    actives = active_entries(entries, args.trigger, now, expire_hours)
    if not actives:
        print(f"no active journal entries for {args.trigger}; nothing to resolve")
        return 0
    targets = actives if args.all else actives[:1]
    for entry in targets:
        entry["resolved"] = True
        entry["resolved_utc"] = iso_utc(now)  # opens the settle window a later fire must respect
        print(f"resolved: fired {entry.get('fired_utc', '?')} note={entry.get('note', '')!r}")
    save_journal(journal_path, entries)
    if (repo / DASHBOARD_RELPATH).exists():
        with dashboard_side_effect(repo, keep=args.keep_dashboard):
            update_dashboard_queue(repo / DASHBOARD_RELPATH, args.trigger, entries, now, expire_hours)
    return 0


def cmd_status(args):
    repo = Path(args.repo).resolve()
    expire_hours = expire_hours_from_env()
    now = utc_now()
    entries = load_journal(repo / JOURNAL_RELPATH)
    for trigger in TRIGGERS:
        actives = active_entries(entries, trigger, now, expire_hours)
        print(f"{trigger}: {len(actives)} active")
        for e in actives:
            fired = parse_utc(e.get("fired_utc"))
            age = f"{(now - fired).total_seconds() / 3600:.1f}h ago" if fired else "unparseable stamp"
            print(f"  fired {e.get('fired_utc', '?')} ({age})  note={e.get('note', '')!r}")
    print("dashboard queue view:")
    print(json.dumps(queue_view(entries, now, expire_hours), indent=2))
    dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
    if dashboard:
        print(f"dashboard last updated {dashboard.get('updated_utc', '?')} by {dashboard.get('updated_by', '?')}")
    return 0


def cmd_budget_gate(args):
    """CI-side twin of cmd_fire's paid-path budget check (audit S2, owner-approved
    2026-08-19). fire_trigger's ceiling is client-side only: a direct push of a
    trigger file (merge, rebase, hand edit) runs the paid workflow without it.
    This subcommand runs the SAME budget_check inside the workflow, against the
    checked-out dashboard/journal/overrides, so the daily aggregate holds
    server-side too. Exit 0 = clear (or a free fire); exit 6 = refuse the run.
    """
    repo = Path(args.repo).resolve()
    if args.params_file:
        params_path = Path(args.params_file)
    else:
        params_path = repo / TRIGGER_DIR_RELPATH / f"{args.trigger}.json"
    try:
        params = json.loads(params_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"budget-gate: cannot read params ({params_path}): {exc}", file=sys.stderr)
        return 6
    if args.trigger not in PAID_TRIGGERS and not is_mitigation_fire(args.trigger, params):
        print(f"budget-gate: {args.trigger} is a free fire; clear")
        return 0
    budget_params = params if args.trigger in PAID_TRIGGERS \
        else dict(params, max_spend=str(MITIGATION_IMPUTED_USD))
    now = utc_now()
    entries = load_journal(repo / JOURNAL_RELPATH)
    dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
    overrides = load_budget_overrides(repo / OVERRIDES_RELPATH)
    kind, reason = budget_check(budget_params, dashboard, now.strftime("%Y-%m-%d"),
                                entries=entries, now=now,
                                expire_hours=expire_hours_from_env(),
                                overrides=overrides, trigger=args.trigger)
    if kind == "ok":
        print(f"budget-gate: clear - {reason}")
        return 0
    print(f"budget-gate: REFUSED - {reason}", file=sys.stderr)
    return 6


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]),
                        help="repo root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)

    fire = sub.add_parser("fire", parents=[common], help="write a trigger file, journal it, and push")
    fire.add_argument("--trigger", required=True, choices=TRIGGERS)
    params = fire.add_mutually_exclusive_group(required=True)
    params.add_argument("--params", help="workflow parameters as a JSON object string")
    params.add_argument("--params-file", help="path to a JSON file holding the parameters object")
    fire.add_argument("--note", default="", help="why this run fires (journal + commit message)")
    fire.add_argument("--force-evict", action="store_true",
                      help="deliberately replace the pending run when two entries are already active")
    fire.add_argument("--reuse-tag", action="store_true",
                      help="archive-renders only: fire a tag whose manifest is already on this branch "
                           "(a deliberate re-archive); without it such a fire is refused (exit 8)")
    fire.add_argument("--ignore-settle", action="store_true",
                      help="fire despite a same-trigger resolve inside the settle window, once "
                           "the prior run is confirmed terminal in GitHub")
    fire.add_argument("--dry-run", action="store_true", help="print what would happen; write nothing")
    fire.add_argument("--no-git", action="store_true", help="write files but skip git add/commit/push")
    fire.add_argument("--keep-dashboard", action="store_true",
                    help="leave the ops/dashboard.json queue update in the working tree "
                         "(daily Routine session only; every other caller gets it restored)")
    fire.add_argument("--override-budget", action="store_true",
                      help="proceed past a daily-ceiling refusal only; a missing or "
                           "invalid max_spend is never overridable")
    fire.set_defaults(func=cmd_fire)

    park = sub.add_parser("park", parents=[common],
                          help="fire the resting-state no-op default for a trigger (or --all), "
                               "so accidental re-fires run a cheap stage instead of the last "
                               "expensive one")
    park_t = park.add_mutually_exclusive_group(required=True)
    park_t.add_argument("--trigger", choices=sorted(PARK_DEFAULTS))
    park_t.add_argument("--all", action="store_true", help="park every parkable trigger, sequentially")
    park.add_argument("--ignore-settle", action="store_true",
                      help="park despite a same-trigger resolve inside the settle window, once "
                           "the prior run is confirmed terminal in GitHub")
    park.add_argument("--dry-run", action="store_true", help="print what would happen; write nothing")
    park.add_argument("--no-git", action="store_true", help="write files but skip git add/commit/push")
    park.add_argument("--keep-dashboard", action="store_true",
                    help="leave the ops/dashboard.json queue update in the working tree "
                         "(daily Routine session only; every other caller gets it restored)")
    park.set_defaults(func=cmd_park)

    resolve = sub.add_parser("resolve", parents=[common], help="mark the oldest active entry resolved")
    resolve.add_argument("--trigger", required=True, choices=TRIGGERS)
    resolve.add_argument("--all", action="store_true", help="resolve every active entry for the trigger")
    resolve.add_argument("--keep-dashboard", action="store_true",
                    help="leave the ops/dashboard.json queue update in the working tree "
                         "(daily Routine session only; every other caller gets it restored)")
    resolve.set_defaults(func=cmd_resolve)

    publish = sub.add_parser("publish", parents=[common],
                             help="re-push a fire whose push was rejected (exit 1): fetch, rebase, re-run "
                                  "the fire's guards against the rebased journal and dashboard, push under "
                                  "the fire token; publishes one journaled fire and nothing else; never re-fires")
    publish.add_argument("--dry-run", action="store_true", help="report what would be pushed; write nothing")
    publish.add_argument("--ignore-settle", action="store_true",
                         help="as for fire: the lane's recently resolved run is confirmed terminal in GitHub")
    publish.add_argument("--override-budget", action="store_true",
                         help="as for fire: proceed past a daily-ceiling refusal only")
    publish.add_argument("--reuse-tag", action="store_true",
                         help="as for fire: an archive-renders tag that already has a manifest is meant")
    publish.set_defaults(func=cmd_publish)

    status = sub.add_parser("status", parents=[common], help="per-trigger active counts and queue view")
    status.set_defaults(func=cmd_status)

    gate = sub.add_parser("budget-gate", parents=[common],
                          help="CI-side daily-ceiling check; exit 6 refuses the run")
    gate.add_argument("--trigger", required=True, choices=TRIGGERS)
    gate.add_argument("--params-file", default=None,
                      help="params JSON path (default: this checkout's trigger file - "
                           "correct for push-fired runs; workflow_dispatch should pass "
                           "its resolved params explicitly)")
    gate.set_defaults(func=cmd_budget_gate)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    ensure_git_hooks(Path(args.repo).resolve())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
