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
Activity governs the QUEUE. Paid entries record their max_spend, and the daily
ceiling counts committed spend = landed (dashboard) + held today: every paid
entry fired on this UTC day and not evicted, resolved or expired alike (see
entry_holds_spend; since 2026-09-23 a resolve no longer releases it).

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
import hashlib
import json
import math
import os
import contextlib
import re
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
    "petri-audit",
    "pab-probe",
)
# advice-eval: elicit AND judge spend Anthropic/provider tokens (2026-07-21)
# pab-probe: patient/assistant/sandbox legs bill the prepaid OpenRouter key and
# the evaluate stage bills Anthropic (2026-08-04, exploratory arm).
# petri-audit: the target model and the optional judge of record spend provider
# tokens when mode is `run` (2026-09-16), and the judge alone when mode is
# `readapt` (2026-09-24), and the judge alone when mode is `rejudge` with a
# real judge (2026-09-24; its `mockllm/judge` rehearsal is free); preflight and
# dry_run cost nothing but the lane is counted paid so every fire goes through
# the ceiling.
PAID_TRIGGERS = frozenset({"scenario-generation", "model-evaluation", "advice-eval", "petri-audit", "pab-probe"})
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
    # petri-audit: mode preflight validates seeds, verifies the environment lock,
    # prices and bounds the run, and calls no model; a true $0 no-op when re-fired.
    "petri-audit": {"seeds_file": "docs/framework/petri_seeds.draft.json", "seed_ids": "",
                    "wave": "1", "target": "mockllm/model", "mode": "preflight", "epochs": "1",
                    "token_limit": "20000", "max_spend": "0.01", "judge": "false",
                    "judge_model": "claude-haiku-4-5", "judge_max_spend": "0.01",
                    "judge_max_tokens": "300", "log_model_api": "true", "commit_outputs": "false"},
    # pab-probe: not parked - its workflow lives on the PAB branch only.
}
# petri-audit mode readapt (2026-09-24, owner decision after the w2e3 failure): re-adapt a paid run whose target
# calls completed but whose adaptation failed, from its 90-day raw-eval artifact, into the run's own directory, then
# run the judge of record. No target call is made, so its commitment is judge_max_spend alone (fire_commitment),
# and it is paid because the judge spends. `source_run_id` names the workflow run whose log it recovers; it is read
# by this mode only and is empty in the park. A readapt must state the parameters the source fire ran under
# (PETRI_READAPT_MATCH_KEYS), which petri_readapt_source_problems recovers from the journal and the trigger file's
# history and compares, at the fire and again in the workflow's budget gate.
PETRI_READAPT_MODE = "readapt"
PETRI_PAID_MODES = ("run", PETRI_READAPT_MODE)
PETRI_READAPT_MATCH_KEYS = ("seeds_file", "seed_ids", "wave", "target", "epochs", "token_limit", "max_spend",
                            "judge", "judge_model", "judge_max_spend", "judge_max_tokens", "log_model_api",
                            "auditor_model")
PETRI_RUNS_RELPATH = Path("data") / "petri" / "runs"
# mirrors of scripts/petri_audit/readapt.py (this script imports nothing from the lane; tests hold them equal): the
# files adaptation writes, and the name after `<stem>` of an earlier readapt's judge sidecar in the source directory
PETRI_ADAPTED_FILES = ("manifest.json", "transcripts.jsonl", "rule_outcomes.jsonl", "sanitised_log.json",
                       "judgments.jsonl", "analysis_rows.jsonl")
PETRI_READAPT_JUDGE_SUFFIX = r"\.readapt_[0-9]+\.judge\.report\.json"
# petri-audit mode rejudge (2026-09-24, owner-approved exploratory re-grading): grade the judgments of landed runs
# again under a judge other than their judge of record, from the committed transcripts, without a target call or an
# adaptation, into data/petri/rejudge/<judge slug>/<source stem>/ (scripts/petri_audit/rejudge.py). `source_runs`
# names the run stems; it is read by this mode only and is empty in the park. Its commitment is judge_max_spend
# alone, on the judge's channel; `mockllm/judge` is the free rehearsal, which never commits. Mirrors of the lane's
# names follow (this script imports nothing from the lane; tests/test_petri_audit_rejudge.py holds them equal).
PETRI_REJUDGE_MODE = "rejudge"
PETRI_REJUDGE_MOCK_JUDGE = "mockllm/judge"
PETRI_REJUDGE_RELPATH = Path("data") / "petri" / "rejudge"
PETRI_REJUDGE_STEM_RE = re.compile(r"run_[0-9]+_[0-9]+")
PETRI_REJUDGE_OUTPUT_FILES = ("judgments.jsonl", "analysis_rows.jsonl", "rejudge_manifest.json")
PETRI_REJUDGE_JUDGE_SUFFIX = r"\.rejudge_[0-9]+\.judge\.report\.json"
PETRI_JUDGE_DEFAULT = "claude-haiku-4-5"        # the params job's judge_model default
# scripts/petri_audit/spend.py ZERO_PRICE_MODELS: the test sentinels, of which only the rehearsal judge is a rejudge's
PETRI_SENTINEL_SPECS = ("mockllm/model", "mockllm/judge", "none/none")
PARK_NOTE = ("PARK (resting-state rule): cheapest no-op default committed so branch operations "
             "that touch this trigger file re-run a $0/negligible stage instead of the last "
             "expensive fire; commit_outputs false where the workflow supports it. "
             "Owner-approved maintenance hardening, 2026-08-27.")


def is_mitigation_fire(trigger, params):
    return trigger == "circuit-trace" and str(params.get("show_mitigation", "")).lower() in ("true", "1")


def petri_mode(params):
    """A petri-audit fire's mode as the workflow reads it (absent is its preflight default)."""
    return str(params.get("mode", "preflight")).strip().lower()


def is_paid_fire(trigger, params):
    """Whether this fire can spend, so the daily ceiling must count it: a
    PAID_TRIGGERS lane, or a circuit-trace fire with show_mitigation. The one
    exemption is petri-audit outside its paid modes (`run`, and `readapt`,
    whose judge spends): preflight and dry_run make no paid call, and counting
    them paid refused the lane's park once the ceiling was reached, leaving the
    last paid configuration at rest where a branch operation could re-fire it
    (Codex round 8 on PR #26). Mode is read trimmed and lower-cased so that a
    spelling like "RUN" or "READAPT" counts as paid (fail closed);
    validate_params refuses every spelling the params job would refuse
    (petri_params_problems), so none reaches the journal."""
    if is_mitigation_fire(trigger, params):
        return True
    if trigger not in PAID_TRIGGERS:
        return False
    if trigger == "petri-audit" and petri_mode(params) == PETRI_REJUDGE_MODE:
        # a rejudge spends through its judge, unless the judge is the zero-price rehearsal sentinel
        return not petri_rejudge_is_rehearsal(params)
    if trigger == "petri-audit" and petri_mode(params) not in PETRI_PAID_MODES:
        return False
    return True


def petri_rejudge_is_rehearsal(params):
    """Whether a petri-audit rejudge names the mock judge, exactly as the params job compares it: the free rehearsal
    that makes no provider call and commits nothing."""
    return _petri_job_value(params, "judge_model", PETRI_JUDGE_DEFAULT) == PETRI_REJUDGE_MOCK_JUDGE


def paid_budget_params(trigger, params):
    """The params budget_check prices for a paid fire: the fire's own for a
    PAID_TRIGGERS lane, the flat imputed commitment for a mitigation fire."""
    return params if trigger in PAID_TRIGGERS else dict(params, max_spend=str(MITIGATION_IMPUTED_USD))
DEFAULT_EXPIRE_HOURS = 8.0
DEFAULT_SETTLE_MINUTES = 15.0
DEFAULT_DAILY_CEILING_USD = 2.0
# The prepaid OpenRouter key's own daily ceiling (PAB-branch lanes model;
# minimal port 2026-08-07 for advice-eval fires whose models are all
# OpenRouter-routed - owner routing instruction, decisions Addendum 3).
DEFAULT_OPENROUTER_DAILY_CEILING_USD = 10.0


WORKFLOW_DIR_RELPATH = ".github/workflows"


def workflow_reads_trigger(repo, trigger: str, ref: str | None = None) -> bool:
    """True when some workflow on this branch reads this trigger's file path.

    CI fires on a push that changes .github/trigger/<trigger>.json, so a trigger
    key is only live where a workflow names that path. Checked per branch: the
    same key can be wired on one branch and absent on another. With `ref`, the
    workflows are read from that commit rather than the working tree: CI runs
    what the pushed commit holds, and an untracked or edited workflow file on
    disk is not that. A git error reads as not wired."""
    needle = f"{TRIGGER_DIR_RELPATH}/{trigger}.json"
    if ref is not None:
        listing = _git(repo, "ls-tree", "--name-only", ref, "--", WORKFLOW_DIR_RELPATH + "/")
        if listing.returncode != 0:
            return False
        for name in listing.stdout.split():
            if Path(name).suffix not in (".yml", ".yaml"):
                continue
            text = _git_show(repo, ref, name)
            if text is not None and needle in text:
                return True
        return False
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
    the anthropic lane - fail closed. petri-audit has its own rule
    (`_petri_lane`): its target is an Inspect model string, not a registry spec."""
    if trigger == "petri-audit":
        return _petri_lane(params)
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


PROVIDERS_RELPATH = Path("data") / "advice_providers.json"
PETRI_BOOLEAN_KEYS = ("judge", "log_model_api", "commit_outputs")
# The mode and target rules of petri_audit.yml's "Resolve parameters" step, mirrored by `petri_params_problems`
# (mode) and `petri_target_problems` (target).
# Compared exactly by the params job, the first being its default; the fourth is PR #29's mode readapt, the fifth
# mode rejudge (2026-09-24).
PETRI_MODES = ("preflight", "dry_run", "run", PETRI_READAPT_MODE, PETRI_REJUDGE_MODE)
PETRI_MOCK_TARGET = "mockllm/model"       # the params job's default target, and the only one dry_run admits
PETRI_SENTINEL_PROVIDERS = ("mockllm", "none")
PETRI_RUN_PROVIDERS = ("anthropic", "openrouter")
PETRI_RUN_TARGET_RE = re.compile(r"anthropic/[^/\s]+|openrouter/[^/\s]+/[^/\s]+")


def providers_registry(repo: str | Path | None = None) -> dict:
    """The provider registry (data/advice_providers.json) the judge specs
    resolve against; {} when the checkout lacks it (every classification then
    fails closed to the anthropic lane)."""
    root = Path(repo) if repo else Path(__file__).resolve().parents[1]
    path = root / PROVIDERS_RELPATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def petri_channels(params: dict, registry: dict | None = None) -> tuple[str, str | None]:
    """(target channel, judge channel or None) of a petri-audit fire. The
    target is an Inspect model string (`provider/model`, so OpenRouter is
    `openrouter/vendor/model`); the judge, when on, a registry spec
    (`provider:model` or a bare Anthropic id) whose channel is the provider
    registry's `key_env` (OPENROUTER_API_KEY bills OpenRouter: `openai:`,
    `xai:`, `deepseek:` and `moonshot:` route there too, not only
    `openrouter:`; Codex round 3). Anything else bills the anthropic lane, the
    one the $2/day guard bounds (fail closed; the landed sidecars classify
    identically: scripts/petri_audit/spend.py billing_channel and
    judge_billing_channel)."""
    target = str(params.get("target") or "").strip()
    target_channel = "openrouter" if target.startswith("openrouter/") else "anthropic"
    if not judge_is_on(params):
        return target_channel, None
    key_env = petri_judge_key_env(params, registry)
    return target_channel, ("openrouter" if key_env == "OPENROUTER_API_KEY" else "anthropic")


def petri_judge_key_env(params: dict, registry: dict | None = None) -> str | None:
    """The provider registry's `key_env` for a petri-audit fire's judge spec:
    None when the judge is off or its provider is not in the registry (the
    workflow's `judge_spec_problems` refuses an unknown provider)."""
    if not judge_is_on(params):
        return None
    judge = str(params.get("judge_model") or "").strip()
    registry = providers_registry() if registry is None else registry
    # the advice resolver's own rule: provider:model, a bare provider the registry knows (its consumer default),
    # else a bare Anthropic model id (Codex round 4)
    if ":" in judge:
        provider = judge.split(":", 1)[0]
    elif isinstance(registry, dict) and isinstance(registry.get(judge), dict):
        provider = judge
    else:
        provider = "anthropic"
    cfg = registry.get(provider) if isinstance(registry, dict) else None
    key_env = cfg.get("key_env") if isinstance(cfg, dict) else None
    return key_env if isinstance(key_env, str) else None


def _petri_job_value(params: dict, key: str, default: str) -> str:
    """A key's value as petri_audit.yml's params job resolves it from a
    trigger file: `str()`-ed as the job does it (a JSON boolean lower-cased,
    nothing trimmed or case-folded), else the job's default."""
    if key not in params:
        return default
    value = params[key]
    return str(value).lower() if isinstance(value, bool) else str(value)


def petri_resolved_target(params: dict) -> str:
    """The target petri_audit.yml's params job resolves from a trigger file."""
    return _petri_job_value(params, "target", PETRI_MOCK_TARGET)


def petri_resolved_mode(params: dict) -> str:
    """The mode petri_audit.yml's params job resolves from a trigger file and
    then compares exactly against PETRI_MODES."""
    return _petri_job_value(params, "mode", PETRI_MODES[0])


def petri_target_problems(params: dict) -> list[str]:
    """The params job's target refusals, in its order and stopping at the
    first, as the job does. The fire path journals its reservation before the
    job runs, so a target only the job refuses left an entry holding the queue
    slot and, in mode run, the day's ceiling for a run that never started,
    until it was resolved or expired (Codex review of PR #37, 2026-09-24).

    The paid modes, run and readapt (PETRI_PAID_MODES): not a mock sentinel
    (it prices at zero, so the paid pre-flight bound admits it for free and the
    run commits mock output as a measurement; Codex round 5 on PR #28); not a
    direct-vendor spelling (every target that is not openrouter/ is booked to
    the Anthropic lane, while openai/... bills its own key); and spelled exactly
    anthropic/<model> or openrouter/<vendor>/<model>. A readapt makes no target
    call, but it states the target its source run called (PR #29,
    petri_readapt_source_problems holds it equal to the source fire's), the
    audit job's preflight step prices that target and refuses a direct-vendor
    spelling in every mode, and a readapt's reservation holds the queue slot and
    the judge's ceiling as a run's does, so the job applies the same three rules
    to it and so does this. dry_run: the mock target only. preflight calls
    nothing, so the job checks no target there and neither does this.
    Mode is read exactly, as the job reads it: the job refuses any mode not
    spelled exactly as one of PETRI_MODES before it looks at the target, and
    petri_params_problems refuses the same spellings, so no target rule is
    applied to them here. The sentinel test trims the target, so a padded
    sentinel is refused under its own name; the job refuses it too, as a
    direct-vendor spelling."""
    mode = petri_resolved_mode(params)
    target = petri_resolved_target(params)
    if mode == "dry_run":
        if target != PETRI_MOCK_TARGET:
            return [f"petri-audit dry_run runs against {PETRI_MOCK_TARGET!r} only, got {target!r}"]
        return []
    if mode not in PETRI_PAID_MODES:
        return []
    if target.strip().split("/")[0] in PETRI_SENTINEL_PROVIDERS:
        named = "" if "target" in params else " (no target is named, and the workflow's default is the sentinel)"
        return [f"petri-audit mode {mode} must not target the test sentinel {target.strip()!r}{named}: it prices at "
                "zero, so the paid pre-flight bound admits it for free and the run commits mock output as a "
                "measurement; use mode dry_run for mockllm"]
    if "/" in target and target.split("/")[0] not in PETRI_RUN_PROVIDERS:
        return [f"petri-audit mode {mode} target {target!r} bills its own vendor key, while every target that is not "
                "openrouter/ is booked to the Anthropic lane and its ceiling; route it through OpenRouter as "
                "openrouter/<vendor>/<model> (for example openrouter/openai/gpt-5.4-mini)"]
    if not PETRI_RUN_TARGET_RE.fullmatch(target):
        return [f"petri-audit mode {mode} needs a target spelled anthropic/<model> or openrouter/<vendor>/<model>, "
                f"got {target!r}; a bare model name names no provider"]
    return []


def petri_auditor_problems(params: dict) -> list[str]:
    """The params job's `auditor_model` refusals (docs/petri_adaptive_design.md), mirrored so a fire the job would
    refuse never journals a reservation: read by preflight, dry_run, run and readapt only (a readapt calls no auditor
    but states its source run's, as it states the target, and PETRI_READAPT_MATCH_KEYS holds it equal to the source
    fire's; Codex review of PR #50); the mock under dry_run; in the paid modes spelled as a paid target is and billed
    on the target's channel, since one fire carries one commitment on one account and the lane is the target's
    (_petri_lane). The job's value is `str(value)` of the trigger key, so a JSON null reads as "None" and is refused
    as a spelling."""
    auditor = _petri_job_value(params, "auditor_model", "")
    if not auditor:
        return []
    mode = petri_resolved_mode(params)
    if mode not in ("preflight", "dry_run", "run", PETRI_READAPT_MODE):
        return [f"petri-audit auditor_model is read by preflight, dry_run, run and readapt only, got mode {mode!r}"]
    if mode == "dry_run" and auditor != PETRI_MOCK_TARGET:
        return [f"petri-audit dry_run runs its auditor against {PETRI_MOCK_TARGET!r} only, got {auditor!r}"]
    if mode in PETRI_PAID_MODES:
        if not PETRI_RUN_TARGET_RE.fullmatch(auditor):
            return [f"petri-audit mode {mode} needs an auditor spelled anthropic/<model> or openrouter/<vendor>/<model>, "
                    f"got {auditor!r}"]
        if auditor.startswith("openrouter/") != petri_resolved_target(params).startswith("openrouter/"):
            return [f"petri-audit auditor {auditor!r} and target {petri_resolved_target(params)!r} bill different "
                    "channels; one fire carries one commitment on one account"]
    return []


def petri_params_problems(params: dict, registry: dict | None = None) -> list:
    """The petri-audit invariants every entry point must enforce before a paid
    step (fire_trigger's fire path, the server-side budget-gate a
    workflow_dispatch reaches without it): one billing channel per fire, and
    boolean keys in the one spelling the workflow compares against."""
    problems = []
    # The params job compares mode exactly and exits on any other spelling, but the rest of this module reads it
    # trimmed and lower-cased (is_paid_fire), so "RUN" or " run" was priced as a paid fire, passed budget_check and
    # journaled a reservation holding the queue slot and the day's ceiling for a run the job then refused; a free
    # typo ("DRY_RUN", "bogus") journaled a queue-slot entry the same way (review of PR #37, 2026-09-24).
    mode = petri_resolved_mode(params)
    if mode not in PETRI_MODES:
        problems.append(f"petri-audit mode must be exactly one of {', '.join(PETRI_MODES)}, got {params['mode']!r}: "
                        "the params job compares it exactly and refuses any other spelling (case, padding), so "
                        "the fire would journal a reservation for a run that never starts")
    for key in PETRI_BOOLEAN_KEYS:
        if key in params:
            value = params[key]
            if not (isinstance(value, bool) or str(value) in ("true", "false")):
                problems.append(f"petri-audit {key} must be true or false (JSON boolean or the exact strings), "
                                f"got {value!r}: the workflow compares against \"true\" exactly, so any other "
                                f"spelling silently reads as false")
    if "judge_max_tokens" in params:
        # the workflow's params job parses this too; a bad value must never reach a paid step (Codex round 6)
        try:
            ok = int(str(params["judge_max_tokens"])) > 0
        except (TypeError, ValueError):
            ok = False
        if not ok:
            problems.append(f"petri-audit judge_max_tokens must be a positive integer, got {params['judge_max_tokens']!r}")
    # A paid run's `_nonce` is the ONLY join key between the journal entry that reserved its spend and the cost
    # sidecar it lands (workflow -> run_params.json -> manifest spend.journal_nonce -> both sidecar writers).
    # Without one, `cli reconcile-spend` reports the fire as unbooked and the sidecar as unaccounted, for good,
    # and the omission is easy: any other changed key already makes the trigger file differ, so the fire is not
    # refused as a no-op (Codex round 1 on PR #28). Free modes need none - the park default carries none.
    # A readapt's nonce joins its judge sidecar to it the same way (manifest `readapt` block -> judge sidecar).
    # From here the mode is read trimmed and lower-cased, as is_paid_fire reads it, so a spelling the exact check
    # above already refused still gets the paid-mode checks below (fail closed; merge of PR #29 into PR #37)
    mode = petri_mode(params)
    source_run_id = params.get("source_run_id", "")
    if mode == PETRI_READAPT_MODE:
        if isinstance(source_run_id, bool) or not re.fullmatch(r"[0-9]+", str(source_run_id)):
            problems.append(f"petri-audit mode readapt needs source_run_id, the numeric workflow run id whose raw-eval "
                            f"artifact it re-adapts, got {source_run_id!r}")
        if not judge_is_on(params):
            problems.append("petri-audit mode readapt must run the judge of record (judge true): a readapt makes no "
                            "target call, so the judge is its only spend and judge_max_spend its whole commitment; "
                            "the lane has no free re-adapt path")
    elif _petri_job_value(params, "source_run_id", ""):
        # the job's own resolution (`str(value)`): a JSON null is "None", which the job refuses outside readapt, so
        # the guard refuses it too rather than journaling a reservation for a run the job will not start (PR #41)
        problems.append(f"petri-audit source_run_id is read by mode readapt only, got {source_run_id!r} with mode "
                        f"{mode!r}: a value the workflow would ignore is refused rather than carried")
    # mode rejudge (2026-09-24): the params job's rules for it, in the same order (scripts/petri_audit/rejudge.py)
    source_runs = params.get("source_runs", "")
    rejudge_paid = False
    if mode == PETRI_REJUDGE_MODE:
        problems.extend(petri_rejudge_param_problems(params))
        rejudge_paid = not petri_rejudge_is_rehearsal(params)
    elif petri_source_runs_resolved(params):
        # the job joins a list and `str()`s anything else, so a JSON null is "None", refused outside rejudge (PR #41)
        problems.append(f"petri-audit source_runs is read by mode rejudge only, got {source_runs!r} with mode "
                        f"{mode!r}: a value the workflow would ignore is refused rather than carried")
    if mode in PETRI_PAID_MODES or rejudge_paid:
        nonce = params.get("_nonce")
        # The workflow resolves the trigger value as `str(cfg.get("_nonce") or "")`, so any FALSY scalar - 0,
        # false, "" - reaches the run as an empty nonce while this entry journals "0" or "False" and the two
        # records can never be joined (Codex round 3 on PR #28). A boolean is refused whichever way it falls.
        # Padding is refused too, not trimmed: the journal records the value as given, so a padded nonce would
        # be stored padded while the uniqueness check compared a stripped one, and re-firing the same padded
        # value would slip past it (Codex round 4 on PR #28).
        if (isinstance(nonce, bool) or not isinstance(nonce, (str, int)) or not nonce
                or not str(nonce).strip() or str(nonce) != str(nonce).strip()):
            problems.append(
                f"petri-audit mode {mode} must carry a non-empty _nonce: it is the only join key between the "
                "journal entry that reserves the spend and the cost sidecar the run lands, so a paid fire "
                f"without one can never be reconciled, got {nonce!r}")
    problems.extend(petri_target_problems(params))
    problems.extend(petri_auditor_problems(params))
    target_channel, judge_channel = petri_channels(params, registry)
    # a rejudge calls no target, so its one channel is its judge's (`_petri_lane`) and a target it does not call
    # cannot mix channels with it
    if mode != PETRI_REJUDGE_MODE and judge_channel is not None and judge_channel != target_channel:
        problems.append(
            f"petri-audit target {params.get('target')!r} bills the {target_channel} lane but judge "
            f"{params.get('judge_model')!r} bills the {judge_channel} lane: one fire carries one commitment on "
            "one account, so a mixed-channel fire is refused; judge on the target's channel or run the judge "
            "as its own fire")
    # A judge billed through a third key (today `google:`, GEMINI_API_KEY) is booked to the anthropic lane above while
    # its vendor bills its own account, so the ceiling would bound the wrong money. The workflow's pre-flight refuses it
    # at $0 (scripts/petri_audit/spend.py judge_key_routing_problems), but by then the fire's journal entry holds its
    # commitment for the rest of the UTC day, so it is refused here, before the push (review of 2026-09-23, F-TH1).
    judge_key = petri_judge_key_env(params, registry)
    if judge_key is not None and judge_key not in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        problems.append(
            f"petri-audit judge {params.get('judge_model')!r} bills {judge_key}, but every judge not billed "
            "through OPENROUTER_API_KEY is booked to the anthropic lane and its ceiling, so the ceiling would bound "
            "the wrong account; judge through OpenRouter instead (openrouter:<vendor>/<model>, for example "
            "openrouter:google/<model>)")
    return problems


def petri_source_runs_resolved(params: dict) -> str:
    """`source_runs` exactly as the params job resolves it: a JSON list joined with spaces, a JSON boolean
    lower-cased, anything else `str()`-ed (so a JSON null is "None"); "" when the key is absent."""
    if "source_runs" not in params:
        return ""
    value = params["source_runs"]
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value).lower() if isinstance(value, bool) else str(value)


def petri_source_runs(params: dict) -> list[str]:
    """The `source_runs` of a petri-audit rejudge as the params job resolves them, split on whitespace."""
    return petri_source_runs_resolved(params).split()


def petri_rejudge_param_problems(params: dict) -> list[str]:
    """The params job's refusals of a mode-rejudge trigger file, mirrored so the fire path refuses before it
    journals a reservation: source_runs names one or more run stems, none twice; the judge runs (judge true); the
    judge spec carries no padding (the job compares it exactly, and the mock rehearsal is recognised by exact
    match); and the rehearsal never commits. The key set and the booleans' spelling are checked elsewhere
    (validate_params, petri_params_problems)."""
    problems = []
    stems = petri_source_runs(params)
    if not stems:
        problems.append("petri-audit mode rejudge needs source_runs, the stems of the landed runs under "
                        "data/petri/runs it re-grades (for example run_36076994201_1)")
    bad = [s for s in stems if not PETRI_REJUDGE_STEM_RE.fullmatch(s)]
    if bad:
        problems.append(f"petri-audit mode rejudge source_runs {bad} are not run stems (run_<workflow run id>_<attempt>)")
    if len(set(stems)) != len(stems):
        problems.append(f"petri-audit mode rejudge names a source run twice ({stems}); one fire judges each run once")
    if _petri_job_value(params, "judge", "false") != "true":
        problems.append("petri-audit mode rejudge runs a judge (judge true): the judge is its only work and its only "
                        "spend")
    judge = _petri_job_value(params, "judge_model", PETRI_JUDGE_DEFAULT)
    if not judge or judge != judge.strip():
        problems.append(f"petri-audit mode rejudge needs judge_model spelled exactly, got {judge!r}")
    elif judge.lower() in PETRI_SENTINEL_SPECS and judge not in PETRI_SENTINEL_SPECS:
        # GitHub's expression `!=` compares ignoring case, so `MockLLM/Judge` would be the rehearsal to the workflow's
        # step conditions and a paid judge to every Python check (PR #41 review); the params job refuses it too
        problems.append(f"petri-audit mode rejudge judge_model {judge!r} differs from a test sentinel in case alone; "
                        "the workflow compares it ignoring case, so it is refused")
    elif judge != PETRI_REJUDGE_MOCK_JUDGE:
        problems.extend(petri_judge_spec_problems(judge))
    if judge == PETRI_REJUDGE_MOCK_JUDGE and _petri_job_value(params, "commit_outputs", "false") == "true":
        problems.append(f"petri-audit mode rejudge with the rehearsal judge {PETRI_REJUDGE_MOCK_JUDGE!r} is never "
                        "committed; it needs commit_outputs false")
    return problems


def petri_judge_spec_problems(spec: str, registry: dict | None = None) -> list[str]:
    """The rejudge plan's refusals of a (non-rehearsal) judge spec that need only the registry, mirrored so the fire
    path refuses before it journals a reservation (PR #41 review): scripts/petri_audit/judge_runner.py
    judge_spec_problems (a zero-price test sentinel; a provider the registry does not know, one with no public API,
    or no model and no consumer_default, as scripts/advice_eval.py _resolve_spec refuses them) and
    scripts/petri_audit/spend.py openrouter_price_problems (an `openrouter:` spec with no reviewed per-model price).
    The key routing rule is petri_params_problems' own."""
    spec = spec.strip()
    if spec in PETRI_SENTINEL_SPECS:
        return [f"petri-audit mode rejudge judge spec {spec!r} is a zero-price test sentinel, not a judge; only "
                f"{PETRI_REJUDGE_MOCK_JUDGE!r} is admitted, as the free rehearsal"]
    registry = providers_registry() if registry is None else registry
    registry = {"anthropic": {"api": "anthropic"}, **(registry if isinstance(registry, dict) else {})}
    if ":" in spec:
        provider, model = spec.split(":", 1)
    elif isinstance(registry.get(spec), dict) and not spec.startswith("_"):
        provider, model = spec, ""
    else:
        provider, model = "anthropic", spec
    cfg = registry.get(provider) if not provider.startswith("_") else None
    if not isinstance(cfg, dict):
        return [f"petri-audit mode rejudge judge spec {spec!r}: unknown provider {provider!r}"]
    if cfg.get("api") == "manual_ui":
        return [f"petri-audit mode rejudge judge spec {spec!r}: provider {provider!r} has no public API"]
    if not (model or str(cfg.get("consumer_default") or "")):
        return [f"petri-audit mode rejudge judge spec {spec!r}: no model given and no consumer_default"]
    if provider == "openrouter" and model not in ((cfg.get("pricing") or {}) if isinstance(cfg.get("pricing"), dict) else {}):
        return [f"petri-audit mode rejudge judge spec {spec!r} has no reviewed per-model price in "
                "data/advice_providers.json openrouter.pricing (unreviewed_openrouter_price)"]
    return []


def petri_rejudge_slug(spec: str) -> str:
    """The directory a judge's re-grades live under (scripts/petri_audit/rejudge.py judge_slug): the spec with every
    run of characters outside [A-Za-z0-9._-] replaced by one hyphen. ValueError for a spec that gives no plain name."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(spec).strip()).strip("-")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug):
        raise ValueError(f"judge spec {spec!r} gives no usable directory name ({slug!r})")
    return slug


def petri_judge_inspect_name(spec: str, registry: dict | None = None) -> str | None:
    """The Inspect-form model a registry judge spec calls (scripts/petri_audit/spend.py registry_spec_to_inspect),
    so two spellings of one judge compare equal; None for a bare provider with no consumer_default, which the
    resolver refuses."""
    spec = str(spec).strip()
    if spec in ("mockllm/model", PETRI_REJUDGE_MOCK_JUDGE, "none/none"):
        return spec
    if ":" in spec:
        provider, model = spec.split(":", 1)
        return f"{provider}/{model}"
    registry = providers_registry() if registry is None else registry
    cfg = registry.get(spec) if isinstance(registry, dict) else None
    if isinstance(cfg, dict):
        default = str(cfg.get("consumer_default") or "").strip()
        return f"{spec}/{default}" if default else None
    return f"anthropic/{spec}"


def petri_rejudge_source_problems(repo, trigger, params):
    """Why a petri-audit `mode: rejudge` fire cannot re-grade the runs it names, as a list of refusals; empty for
    every other fire. Each source run must be landed and chained (`data/petri/runs/<stem>/manifest.json`, named by
    `manifests.chain`) with a judge of record bound; the rejudge's judge must not be that judge (by exact spec, or
    by the model the spec calls) and must use its judge_max_tokens; and the output directory
    `data/petri/rejudge/<judge slug>/<stem>` must be absent or hold only earlier fires' judge sidecars, since a
    landed rejudge is never rewritten. The workflow's plan step checks all of this again and more (the source run
    verifies on its own, and the judgments planned from its transcripts are exactly its judge of record's) before
    any call; this refuses what can be seen here before the fire holds a queue slot or the day's ceiling."""
    if trigger != "petri-audit" or petri_mode(params) != PETRI_REJUDGE_MODE:
        return []
    stems = petri_source_runs(params)
    if not stems or any(not PETRI_REJUDGE_STEM_RE.fullmatch(s) for s in stems):
        return []                                        # petri_params_problems names it
    repo = Path(repo)
    judge = _petri_job_value(params, "judge_model", PETRI_JUDGE_DEFAULT)
    try:
        slug = petri_rejudge_slug(judge)
    except ValueError as exc:
        return [f"petri-audit rejudge: {exc}"]
    registry = providers_registry(repo)
    runs = repo / PETRI_RUNS_RELPATH
    chain = runs / "manifests.chain"
    chained = set()
    if chain.is_file():
        chained = {ln.strip().rsplit(" ", 1)[0] for ln in chain.read_text(encoding="utf-8").splitlines() if ln.strip()}
    try:
        tokens = int(_petri_job_value(params, "judge_max_tokens", "300"))
    except ValueError:
        tokens = None                                    # petri_params_problems names it
    problems = []
    for stem in stems:
        where = f"petri-audit rejudge of {stem}"
        manifest_path = runs / stem / "manifest.json"
        if not manifest_path.is_file():
            problems.append(f"{where}: {PETRI_RUNS_RELPATH.as_posix()}/{stem} holds no landed run (no manifest.json)")
            continue
        if f"{stem}/manifest.json" not in chained:
            problems.append(f"{where}: {PETRI_RUNS_RELPATH.as_posix()}/manifests.chain does not name it; only a landed, "
                            "chained run is re-graded")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{where}: its manifest does not parse ({exc})")
            continue
        jor = ((manifest.get("artifacts") or {}).get("judge_of_record") if isinstance(manifest, dict) else None) or {}
        of_record = jor.get("judge_model") if isinstance(jor, dict) else None
        if not of_record:
            problems.append(f"{where}: no judge of record is bound in its manifest")
        else:
            mine, theirs = petri_judge_inspect_name(judge, registry), petri_judge_inspect_name(of_record, registry)
            if judge == of_record or (mine is not None and mine == theirs):
                problems.append(f"{where}: {judge!r} is its judge of record ({of_record!r}); a rejudge grades with a "
                                "different judge")
            if tokens is not None and jor.get("judge_max_tokens") is not None and int(jor["judge_max_tokens"]) != tokens:
                problems.append(f"{where}: its judge of record ran with judge_max_tokens {jor['judge_max_tokens']}; a "
                                f"rejudge applies the same instrument, not {tokens}")
        out = repo / PETRI_REJUDGE_RELPATH / slug / stem
        if out.exists():
            names = sorted(p.name for p in out.iterdir()) if out.is_dir() else [out.name]
            landed = [n for n in names if n in PETRI_REJUDGE_OUTPUT_FILES]
            other = [n for n in names if n not in PETRI_REJUDGE_OUTPUT_FILES
                     and not re.fullmatch(re.escape(stem) + PETRI_REJUDGE_JUDGE_SUFFIX, n)]
            if landed:
                problems.append(f"{where}: {PETRI_REJUDGE_RELPATH.as_posix()}/{slug}/{stem} already holds a re-grade "
                                f"({', '.join(landed)}); a landed rejudge is never rewritten")
            elif other:
                problems.append(f"{where}: {PETRI_REJUDGE_RELPATH.as_posix()}/{slug}/{stem} holds files other than "
                                f"earlier rejudge fires' judge sidecars ({', '.join(other)})")
    return problems


def lane_params_problems(trigger: str, params: dict, registry: dict | None = None) -> list:
    """Lane-specific invariants beyond the key set; empty for lanes that have none."""
    if trigger == "petri-audit":
        return petri_params_problems(params, registry)
    return []


def _petri_lane(params: dict) -> str:
    """petri-audit (2026-09-16): one lane per fire, so the target and any judge
    must bill the same channel; validate_params and budget-gate refuse a
    mixed fire because a single journal entry cannot carry two commitments on
    two accounts (Codex rounds 2 and 3). A mixed fire that somehow reaches
    here still fails closed. A rejudge calls no target: its lane is its
    judge's (2026-09-24)."""
    target_channel, judge_channel = petri_channels(params)
    if petri_mode(params) == PETRI_REJUDGE_MODE:
        return judge_channel or "anthropic"
    if judge_channel is not None and judge_channel != target_channel:
        return "anthropic"
    return target_channel


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
    # petri_audit.yml `defaults` dict (2026-09-16; tests/test_petri_audit_workflow.py
    # checks it against the heredoc): seeds_file, seed_ids, wave, target, mode,
    # epochs, token_limit, max_spend, judge, judge_model, judge_max_spend,
    # judge_max_tokens, log_model_api, commit_outputs, source_run_id (mode
    # readapt only, 2026-09-24; empty by default and absent from the park),
    # source_runs (mode rejudge only, 2026-09-24; likewise).
    "petri-audit": frozenset({
        "seeds_file", "seed_ids", "wave", "target", "mode", "epochs", "token_limit",
        "max_spend", "judge", "judge_model", "judge_max_spend", "judge_max_tokens",
        "log_model_api", "commit_outputs", "source_run_id", "source_runs", "auditor_model",
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
    tmp.write_text(journal_text(entries), encoding="utf-8")
    os.replace(tmp, path)


def journal_text(entries) -> str:
    """The journal file's exact content for these entries: what save_journal
    writes, and what a commit of it must therefore contain."""
    return "".join(json.dumps(e) + "\n" for e in entries)


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
    bad = control_char_values(params)
    if bad:
        raise ValueError(
            f"{trigger} param value(s) {bad} carry a control character (newline, carriage return, tab): "
            "every workflow's params job writes its resolved values into $GITHUB_OUTPUT as `key=value` "
            "lines, so an embedded newline writes further key=value lines of its own and a duplicate key "
            "read later wins - a value could silently rewrite mode, target or a spend ceiling after the "
            "job's own checks passed. No legitimate value carries one"
        )
    problems = lane_params_problems(trigger, params)
    if problems:
        raise ValueError("; ".join(problems))


def reused_nonce(trigger, params, entries):
    """The refusal message when this paid fire's `_nonce` is one an existing
    journal entry of the same trigger already carries, else "". Only a paid
    fire is checked: a free fire's nonce exists to make the trigger file
    differ, and the parks deliberately reuse none at all."""
    if not is_paid_fire(trigger, params):
        return ""
    nonce = str(params.get("_nonce") or "").strip()
    if not nonce:
        return ""
    for entry in entries:
        # both sides normalised: validate_params refuses a padded nonce, but an entry journaled before that
        # rule, or by hand, may carry one (Codex round 4 on PR #28)
        if entry.get("trigger") == trigger and str(entry.get("nonce") or "").strip() == nonce:
            return (f"_nonce {nonce!r} is already on the {trigger} journal entry fired at "
                    f"{entry.get('fired_utc', '?')}: a nonce binds one journal entry to one landed cost "
                    "sidecar, so reusing it would book one cost against two commitments. Use a new nonce")
    return ""


def control_char_values(params):
    """Sorted keys whose value (or, for a list, some element) carries a control
    character. Underscore metadata is included: `_nonce` reaches $GITHUB_OUTPUT
    like any resolved value, and it is written last, where an injected line
    overrides every key before it (PR B, 2026-09-18)."""
    def dirty(value):
        return any(ord(ch) < 32 or ord(ch) == 127 for ch in str(value))

    bad = []
    for key, value in params.items():
        values = value if isinstance(value, (list, tuple)) else [value]
        if any(dirty(v) for v in values):
            bad.append(str(key))
    return sorted(bad)


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
    back to the workflow default, invisible to this guard.

    A petri-audit `mode: readapt` fire makes no target call: its max_spend is
    the SOURCE run's ceiling, recorded in the manifest and already reserved
    by the source fire, so its commitment is judge_max_spend alone. A
    `mode: rejudge` fire makes no target call either and re-grades landed
    runs with a judge alone, so its commitment is judge_max_spend too, and
    max_spend is not read. No other lane has a mode of either name."""
    mode = str(params.get("mode", "")).strip().lower()
    if mode in (PETRI_READAPT_MODE, PETRI_REJUDGE_MODE):
        judge = parse_max_spend(params.get("judge_max_spend")) if judge_is_on(params) else None
        if judge is None:
            return None, (
                f"mode {mode} commits the judge's ceiling alone, so it needs judge=true and a usable "
                f"judge_max_spend (finite number > 0), got judge={params.get('judge')!r}, "
                f"judge_max_spend={params.get('judge_max_spend')!r}"
            )
        return judge, None
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


def entry_holds_spend(entry, today, lane="anthropic"):
    """Whether this journal entry's commitment counts against `today`'s ceiling
    (YYYY-MM-DD, UTC) on `lane`: a paid entry (a PAID_TRIGGERS fire, or a
    mitigation circuit-trace fire with its imputed commitment) on that lane,
    with a usable max_spend, not evicted, and fired on `today` in UTC.

    Deliberately NOT a function of `resolved` or of the expiry window. Until
    2026-09-23 the daily sum counted only ACTIVE entries, so a resolve or the
    8-hour expiry released a paid fire's commitment - and nothing else counts
    that cost the same day: landed spend is `spend.today`, which only
    `ledger_update.py` writes and only the daily Routine commits. The ceiling
    therefore bounded each fire-to-resolve cycle, not the day. On 2026-09-23
    `budget_check` reported "today's committed 0.00" while two resolved
    petri-audit fires had committed 12.70 that UTC day (4.10 + 8.60) and 3.81
    had landed. A commitment now holds for the whole UTC day it was fired;
    the next day it is spend the ledger books, not a hold.

    Only a JSON `true` evicts. An evicted entry's run was superseded in the
    queue and never ran, so it holds nothing; but reading a hand-edited string
    such as "false" as eviction (the truthiness `entry_is_active` uses) would
    stop counting a live commitment, which is the fail-open direction here.
    An unparseable `fired_utc` names no day, so it is counted on none:
    `cmd_fire` always writes a parseable stamp, and `publish` restamps an
    entry whose stamp does not parse before it pushes it.
    """
    # paid triggers always record max_spend; mitigation circuit-trace entries record their imputed commitment
    # the same way, and every other entry records none
    if entry.get("trigger") not in PAID_TRIGGERS and entry.get("max_spend") is None:
        return False
    if entry.get("lane", "anthropic") != lane:
        return False
    if entry.get("evicted") is True:
        return False
    if parse_max_spend(entry.get("max_spend")) is None:
        return False
    fired = parse_utc(entry.get("fired_utc"))
    return fired is not None and fired.astimezone(timezone.utc).strftime("%Y-%m-%d") == today


def inflight_max_spend(entries, today, now=None, expire_hours=None, lane="anthropic"):
    """Sum of max_spend across the journal entries that hold spend on `today`
    (YYYY-MM-DD UTC) on `lane` - see entry_holds_spend. The name predates
    2026-09-23, when the sum counted only ACTIVE entries and so released a fire
    on resolve or expiry; `now` and `expire_hours` are still accepted so every
    caller keeps its call shape, and no longer affect the sum."""
    total = 0.0
    for entry in entries:
        if entry_holds_spend(entry, today, lane):
            total += parse_max_spend(entry.get("max_spend"))
    return total


def budget_check(params, dashboard, today, entries=(), now=None, expire_hours=DEFAULT_EXPIRE_HOURS,
                 overrides=None, trigger=None):
    """(kind, reason) against the daily spend ceiling for a paid trigger.

    kind is "ok", "ceiling" (over the daily ceiling - the only refusal
    --override-budget may bypass), or "invalid" (missing/unusable max_spend -
    never overridable). Committed spend = landed (spend.today.spent_usd when
    spend.today.date equals `today`) + held today (every paid journal entry
    fired on `today` and not evicted, resolved or not; see entry_holds_spend).
    Tolerates a missing/partial dashboard: ceiling defaults to
    DEFAULT_DAILY_CEILING_USD.

    The two terms overlap, deliberately. Once `ledger_update.py` has folded a
    run's cost sidecar into `spend.today`, that run is counted twice for the
    rest of its UTC day: its landed cost, and the commitment its journal entry
    still holds. That fails closed - the ceiling refuses early, never late -
    and it is the price of counting each fire for the whole day without
    joining every landed sidecar to the entry that reserved it, which only
    petri-audit's `_nonce` makes possible. Before 2026-09-23 the overlap was
    avoided by releasing the entry on resolve, on the assumption that the
    ledger had folded the run's cost by then; a resolve comes as soon as the
    run lands and the fold runs once per Routine at most, so the cost dropped
    out of the day entirely in between.

    `now` and `expire_hours` are accepted for call compatibility; the day's sum
    no longer depends on them (a fire's expiry releases its queue slot only).
    """
    # a petri-audit rejudge commits its judge's ceiling alone and reads no max_spend (fire_commitment)
    if "max_spend" not in params and str(params.get("mode", "")).strip().lower() != PETRI_REJUDGE_MODE:
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
    # "held today", not "in-flight": the term counts resolved fires too, and a report that called them in flight
    # would describe a rule this function no longer applies
    held = inflight_max_spend(entries, today, lane=lane)
    committed = landed + held
    if max_spend + committed > ceiling:
        return "ceiling", (
            f"max_spend {max_spend:.2f} + today's committed {committed:.2f} "
            f"(landed {landed:.2f} + held today {held:.2f}) "
            f"would exceed the daily ceiling {ceiling:.2f} USD [{lane} lane]{override_note}"
        )
    return "ok", (
        f"max_spend {max_spend:.2f} + today's committed {committed:.2f} "
        f"(landed {landed:.2f} + held today {held:.2f}) within the daily ceiling {ceiling:.2f} USD "
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
        proc = _git(repo, "push", "-u", "origin", refspec, env=env)
    else:
        with fire_token(repo) as own:
            proc = _git(repo, "push", "-u", "origin", refspec, env=own)
    if proc.returncode == 0 and oid:
        _ensure_upstream(repo, branch)
    return proc


def _push_rejected(proc) -> bool:
    """True when git refused the push as non-fast-forward: the remote moved again,
    which no retry of the same commit can cure; only another rebase can."""
    text = (proc.stderr or "").lower()
    return "non-fast-forward" in text or "fetch first" in text or "[rejected]" in text


def _ensure_upstream(repo, branch):
    """`push -u` records an upstream only for a local-branch source; an object-id
    refspec leaves a new branch untracked, and the `git pull --rebase` every
    later push here needs would then have no default. Set it when unset."""
    if _git(repo, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}").returncode != 0:
        _git(repo, "branch", f"--set-upstream-to=origin/{branch}", branch)


def _head_oid(repo):
    """HEAD's commit id, or None when git cannot say."""
    proc = _git(repo, "rev-parse", "--verify", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def _commit_is_exactly(repo, parent, commit, paths) -> str | None:
    """None when `commit` has `parent` as its parent (no parent when `parent` is
    None) and changes exactly `paths` relative to the repo; else what differs."""
    if commit is None:
        return "git rev-parse HEAD failed"
    got_parent = _git(repo, "rev-parse", "--verify", "--quiet", f"{commit}^")
    actual_parent = got_parent.stdout.strip() if got_parent.returncode == 0 else None
    if actual_parent != parent:
        return (f"commit {commit[:12]} sits on {(actual_parent or 'no parent')[:12]}, not on "
                f"{(parent or 'no parent')[:12]} as read before the commit")
    touched = _git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit)
    if touched.returncode != 0:
        return f"git diff-tree failed: {touched.stderr.strip()}"
    root = Path(repo).resolve()
    expected = set()
    for path in paths:
        path = Path(path)
        expected.add((path.resolve().relative_to(root) if path.is_absolute() else path).as_posix())
    actual = set(touched.stdout.split())
    if actual != expected:
        return f"commit {commit[:12]} changes {sorted(actual)}, not exactly {sorted(expected)}"
    return None


def _json_at(repo, ref: str, relpath: Path) -> dict:
    """The JSON object committed at ref:relpath; {} when absent or not an
    object, as load_dashboard and load_budget_overrides read a missing file."""
    text = _git_show(repo, ref, relpath.as_posix())
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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
    before = _head_oid(repo)                    # None on an unborn branch
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
        # The commit to push is the one just made and nothing else: the branch
        # tip read back must sit on the tip read before the commit and change
        # exactly the paths added. A commit another process made in between,
        # before or after ours, fails one of the two, and nothing is pushed.
        head = _head_oid(repo)
        problem = _commit_is_exactly(repo, before, head, paths)
        if problem:
            print(f"refusing to push: {problem}. The fire is committed locally; inspect the branch, drop what "
                  "does not belong, then `publish`.", file=sys.stderr)
            return False
        for attempt, delay in enumerate((0,) + tuple(backoff)):
            if delay:
                print(f"push retry {attempt}/{len(backoff)} in {delay}s", file=sys.stderr)
                time.sleep(delay)
            proc = _push_with_token(repo, branch, env, oid=head)
            if proc.returncode == 0:
                return True
            print(f"git push failed: {proc.stderr.strip()}", file=sys.stderr)
            if _push_rejected(proc):
                print(f"origin/{branch} moved since this checkout was rebased; retrying the same commit cannot "
                      "succeed. The fire is committed locally: run `publish` to rebase it and push.",
                      file=sys.stderr)
                return False
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


def park_passes_ceiling(trigger: str, params: dict, kind: str) -> bool:
    """Whether budget_check's verdict `kind` is a daily-ceiling refusal that is waived because this fire is the
    lane's park.

    Since 2026-09-23 a paid fire holds its commitment for its whole UTC day, resolved or not (entry_holds_spend).
    The parks of scenario-generation, model-evaluation and advice-eval are paid fires of 0.01, so on a day whose
    paid fires had reached the ceiling, the re-park docs/operators_handbook.md section 3 requires after every landed
    fire was refused with exit 4. Nothing sanctioned got past that: `park` passes no --override-budget and section
    6 forbids one. The paid config then stayed on the trigger file at rest until 00:00 UTC, when the day's holds
    reset and a merge, rebase or cherry-pick that re-fired it would pass the CI gate on its params alone. The
    resting-state rule exists to close exactly that hazard (review of the G1 change, 2026-09-23: 1.20 + 0.80 on a
    $2 day, both resolved, then the scenario-generation park refused at "held today 2.00"). Before G1 the resolve
    released the holds and the park went through.

    The waiver is narrow on purpose:
    - it applies only to a park recognised by content (is_park_params: the lane's PARK_DEFAULTS exactly, plus
      `_parked`), never by flag, so nothing else can claim it;
    - it waives only a "ceiling" verdict. An "invalid" commitment is never waived;
    - the park's journal entry still records its max_spend and holds it for the rest of the day;
    - the CI gate has no waiver. On a full day it refuses the park's own run (exit 6), so the park spends nothing.
      Its work is done once its bytes are the trigger file at rest.
    The day's actual spend therefore still cannot pass the ceiling.
    """
    return kind == "ceiling" and is_park_params(trigger, params)


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
    # 2b. A petri-audit readapt must recover the run it names, under the parameters that run's fire recorded; a
    # rejudge must re-grade landed runs with another judge into directories that hold no re-grade yet.
    readapt_problems = (petri_readapt_source_problems(repo, args.trigger, params)
                        or petri_rejudge_source_problems(repo, args.trigger, params))
    if readapt_problems:
        print("refused: " + "; ".join(readapt_problems), file=sys.stderr)
        return 3

    # 3. Queue guard: one running + one pending; a third push evicts the pending run.
    journal_path = repo / JOURNAL_RELPATH
    entries = load_journal(journal_path)
    actives = active_entries(entries, args.trigger, now, expire_hours)
    if (actives and args.trigger == "petri-audit"
            and petri_mode(params) in (PETRI_READAPT_MODE, PETRI_REJUDGE_MODE)):
        # A queued run starts from its own trigger commit, not the branch tip: a readapt queued behind a run, or
        # behind another readapt of the same source, adapts against a chain file and a run directory that predate
        # the first run's commit, and its own commit then conflicts after the judge has spent. So a readapt fires
        # only into an idle lane; chain it after the running fire lands and is resolved. A rejudge likewise: queued
        # behind another rejudge of the same judge and run it would find the output directory still empty in its
        # own checkout, spend, and conflict on commit (2026-09-24).
        mode = petri_mode(params)
        print(f"refused: {len(actives)} active {args.trigger} journal entr{'y' if len(actives) == 1 else 'ies'}; a "
              f"{mode} fires only when the lane is idle, because a queued run checks out its own trigger commit and "
              "would work against outputs that predate the running fire's. Wait for it to land, pull, `resolve`, "
              "and fire again", file=sys.stderr)
        return 2
    # ...and the rule is symmetric: nothing enters the lane behind an active readapt, whatever its mode. A mode-run
    # fire queued behind it checks out its own trigger commit, whose manifest chain predates the readapt's appended
    # head, so its outputs cannot commit after its target and judge have spent (Codex, PR #29); the park and the
    # free modes are refused too, so the lane holds the readapt alone until it lands and is resolved.
    readapt_ahead = petri_active_readapt_problems(repo, args.trigger, actives)
    if readapt_ahead:
        print("refused: " + "; ".join(readapt_ahead) + ". No petri-audit fire of any mode enters the lane while a "
              "readapt or a rejudge is active: a run queued behind it checks out a commit whose outputs predate "
              "its. Wait for it to land, pull, `resolve`, and fire again", file=sys.stderr)
        return 2
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

    # 3c. A paid fire's nonce must also be NEW. validate_params has already refused a paid petri fire without
    # one; a repeat of a nonce some earlier entry carries would bind two journal entries to one sidecar, and
    # reconcile-spend would book that single landed cost against both commitments (Codex round 1 on PR #28).
    reused = reused_nonce(args.trigger, params, entries)
    if reused:
        print(f"refused: {reused}", file=sys.stderr)
        return 3

    # 4. Budget guard for the paid triggers: committed = landed + the max_spend every paid entry fired today holds.
    # Mitigation circuit-trace fires are paid too (Anthropic translation calls);
    # they carry no max_spend param, so a flat imputed commitment is used.
    max_spend = None
    if is_paid_fire(args.trigger, params):
        budget_params = paid_budget_params(args.trigger, params)
        dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
        overrides = load_budget_overrides(repo / OVERRIDES_RELPATH)
        kind, reason = budget_check(budget_params, dashboard, now.strftime("%Y-%m-%d"),
                                    entries=entries, now=now, expire_hours=expire_hours,
                                    overrides=overrides, trigger=args.trigger)
        if kind == "ok":
            print(reason)
        elif kind == "ceiling" and args.override_budget:
            print(f"warning: budget override in effect ({reason})", file=sys.stderr)
        elif park_passes_ceiling(args.trigger, params, kind):
            # the resting-state rule outranks a full day's ceiling for the park alone; the CI gate still refuses
            # its run, so it spends nothing (see park_passes_ceiling)
            print(f"park fired past the daily ceiling ({reason}): its bytes replace the paid config at rest, and "
                  "the CI gate, which has no such waiver, refuses its own run while the day is full")
        else:
            print(f"refused: {reason}", file=sys.stderr)
            return 4
        # full commitment (max_spend + judge_max_spend on judged fires) so the
        # journal entry holds, for the rest of this UTC day, what budget_check counted
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
        # the fire's `_nonce` is the join key between this entry and what the run leaves behind: the petri-audit
        # workflow passes it into the run, the manifest records it as spend.journal_nonce and both cost-sidecar
        # writers copy it, so `scripts.petri_audit.cli reconcile-spend` can match every paid fire to its landed cost
        # (PR B, 2026-09-18); None when the fire carried no nonce
        "nonce": str(params["_nonce"]) if params.get("_nonce") not in (None, "") else None,
        # the digest of the trigger file this fire writes: the gate compares it with the file CI actually ran, so a
        # replay of the same nonce with different bytes - a formatting-only edit, a hand edit, a merge that changes
        # the content - cannot claim this reservation (Codex round 9 on PR #28)
        "params_sha256": params_digest(content),
        # and the branch it is made on: the same commit reaching a second ref by merge or cherry-pick is a second
        # workflow run, on a ref whose previous tip never carried this nonce (Codex round 11 on PR #28)
        "ref": fire_ref(repo),
    }
    if max_spend is not None:
        entry["max_spend"] = max_spend  # the commitment budget_check counts for the whole UTC day of this fire
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
    # --no-renames: with detection on, a foreign file renamed onto a publishable
    # path lists only the destination, and the source's deletion would be pushed
    # unlisted.
    changed = _git(repo, "log", "--format=", "--name-only", "--no-renames", f"origin/{branch}..{head}")
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


def fire_ref(repo):
    """The branch this fire is being made on, or None when git cannot say (a detached HEAD, `--no-git` against a
    directory that is not a repository).

    Recorded on the journal entry because a reservation is for one REF as well as one push. Every lane's workflow
    fires on any branch that changes its trigger file, and this repo's own merge rule says a merge carrying a
    trigger change re-fires it - so a paid fire made on a feature branch and then merged or cherry-picked to
    `main` appears on `main` for the first time there. The push binding alone reads that as a fresh reservation,
    and both refs spend concurrently under one nonce (Codex round 11 on PR #28).
    """
    proc = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    branch = proc.stdout.strip() if proc.returncode == 0 else ""
    if not branch or branch == "HEAD":      # no repo, or a detached HEAD, which no fire pushes from
        return None
    return branch


def journal_at_previous_tip(repo: Path, before: object) -> tuple[list[dict] | None, list[str]]:
    """(entries, problems) of the journal at `before`, a push's previous tip, for the two push bindings:
    journal_nonces_at (petri-audit) and pushed_fire_entry (the other paid lanes). entries is [] only when that
    commit provably has no journal. It is None whenever git cannot answer: no ref, the all-zero sha a ref creation
    reports, a commit this clone does not have, or a journal that is in the commit's tree but cannot be read.

    None is "unreadable", never "empty". `_git_show` fails the same way for a path that is not in the tree and for
    content git cannot read, so neither a missing commit nor a missing blob may be read as "no earlier entries".
    The commit is confirmed to exist first; a shallow clone lacks it. The blob is the case that check left open.
    The gate jobs check out full history blobless (`filter: blob:none`), so a journal blob that differs from
    HEAD's is fetched lazily when `git show` asks for it. A failed fetch (network, auth, a promisor that has gone
    away) exits nonzero just like an absent path. Both bindings read that as "no earlier entries" and so admitted a
    replay. Reproduced: a fire, then a park as the previous tip, then a push restoring the fire's bytes. The fire's
    entry was left out, and 2.41 was counted as 1.51 (review of the G4 change, 2026-09-23). `git ls-tree` reads only
    trees, which a blobless clone holds, so it tells the two apart: a path listed in the tree whose content could
    not be read is None.
    """
    if not isinstance(before, str) or not before.strip():
        return None, []
    before = before.strip()
    if set(before) == {"0"}:
        return None, []                   # the all-zero sha a ref creation reports: there is no "before" to read
    if _git(repo, "cat-file", "-e", f"{before}^{{commit}}").returncode != 0:
        return None, []
    entries, problems = journal_at(repo, before)
    if entries is not None:
        return entries, problems
    listed = _git(repo, "ls-tree", "--name-only", before, "--", JOURNAL_RELPATH.as_posix())
    if listed.returncode != 0 or listed.stdout.strip():
        return None, []                   # in the tree, or git cannot say: the content was there and was not read
    return [], []


def journal_nonces_at(repo, ref, trigger):
    """The nonces `trigger`'s journal entries carry at `ref`, or None when git cannot answer.

    None is "unreadable", never "empty" (journal_at_previous_tip): a commit this clone does not have, or a journal
    in its tree whose content could not be fetched, is not a journal with no reservations, and reading it as one
    would turn a shallow or blobless checkout into a pass. Only a commit whose tree has no journal reads as empty.
    """
    entries, _ = journal_at_previous_tip(repo, ref)
    if entries is None:
        return None
    return {e["nonce"] for e in entries
            if e.get("trigger") == trigger and isinstance(e.get("nonce"), str) and e["nonce"]}


def ref_reservation_problems(trigger, params, entries, ref, required):
    """Why this paid petri-audit run's reservation was not taken on the ref CI is running.

    The push binding asks whether the nonce was already on THIS ref before THIS push, which is the right question
    for a replay onto the same branch and the wrong one across branches: a paid fire made on a feature branch and
    then merged or cherry-picked to `main` appears on `main`'s new tip for the first time, so its previous tip
    lacks the nonce and the binding passes while the feature branch's run is still spending. Both refs then land
    sidecars carrying one nonce (Codex round 11 on PR #28). `cmd_fire` records the branch it fired on, and this
    requires CI's ref to be that one.
    """
    if trigger != "petri-audit" or not is_paid_fire(trigger, params):
        return []
    mine = reservation_entries(trigger, params, entries) or []
    if len(mine) != 1:
        return []                         # already refused by journal_reservation_problems, which names it better
    entry, nonce = mine[0], str(params.get("_nonce"))
    recorded = entry.get("ref")
    if not isinstance(recorded, str) or not recorded:
        return [f"the {trigger} journal entry for _nonce {nonce!r} records no ref, so it cannot be shown to have "
                "reserved a run on the branch CI is running; re-fire through scripts/fire_trigger.py, which "
                "records the branch it fires on"]
    if ref is None or not str(ref).strip():
        if not required:
            return []
        return [f"the {trigger} gate was not told which ref it is running on, so the reservation for _nonce "
                f"{nonce!r} cannot be shown to belong to this branch rather than the one it was fired on "
                f"({recorded!r}). The workflow passes the ref name as --ref"]
    if str(ref).strip() != recorded:
        return [f"the {trigger} reservation for _nonce {nonce!r} was taken on ref {recorded!r} but CI is running "
                f"on {str(ref).strip()!r}: the fire commit reached this branch by a merge, a cherry-pick or a "
                "rebase, and the run it reserved is the one on the ref it was fired from. Two refs cannot spend "
                "one reservation; re-fire through scripts/fire_trigger.py from this branch if a run is wanted "
                "here"]
    return []


def push_reservation_problems(repo, trigger, params, before, required):
    """Why this paid petri-audit run's reservation was not taken BY the push CI is running.

    The digest binds a reservation to one trigger CONTENT (Codex round 9); it does not bind it to one PUSH, and
    the residual I stated there turned out to be reachable rather than theoretical. A paid config running, the
    resting-state park pushed behind it as the PENDING run, and then a merge that restores the paid content
    byte-for-byte: the merge is a third push, it evicts the pending park, the digest matches because the bytes
    match, and the same reservation admits a second irreversible run. My round-9 reasoning that the park prevented
    this was wrong - the park can itself be the pending run the merge evicts (Codex round 10 on PR #28).

    `cmd_fire` writes the journal entry and the trigger file in ONE commit, so a reservation already on the branch
    before this push was taken by an earlier fire, and this push is a replay of it.

    `required` is for the one environment where not knowing is itself a refusal: inside GitHub Actions the gate is
    always running a push (a paid run is push-only, attempt 1 only, enforced in the params job), so a missing
    `--push-before` there is a workflow that stopped passing it, not a caller who had nothing to pass.
    """
    if trigger != "petri-audit" or not is_paid_fire(trigger, params):
        return []
    nonce = params.get("_nonce")
    if isinstance(nonce, bool) or nonce in (None, "") or not str(nonce).strip():
        return []                         # lane_params_problems has already refused this
    nonce = str(nonce)
    if before is None or not str(before).strip():
        if not required:
            return []
        return [f"the {trigger} gate cannot tell a fire from a replay: it was not told which commit the branch "
                f"pointed at before this push, so the reservation for _nonce {nonce!r} cannot be shown to have "
                "been taken BY this push. The workflow passes the push event's previous tip as --push-before"]
    earlier = journal_nonces_at(repo, before, trigger)
    if earlier is None:
        return [f"the {trigger} journal at {str(before).strip()!r} could not be read, so whether an earlier push "
                f"already took the reservation for _nonce {nonce!r} cannot be established; the gate needs the "
                "ref's history (check out with fetch-depth: 0) and, in a blobless clone, the journal's content at "
                "that commit, and a paid run is refused rather than guessed"]
    if nonce in earlier:
        return [f"the {trigger} reservation for _nonce {nonce!r} was already on this ref before this push: "
                "fire_trigger.py writes the entry and the trigger file in one commit, so this content was put "
                "here by something else (a merge, a revert or a hand edit) and would spend a reservation an "
                "earlier fire already took. Re-fire through scripts/fire_trigger.py, which takes a fresh one"]
    return []


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
    # The dashboard is the script's own side effect: `fire --keep-dashboard` (the
    # Routine) and `resolve` leave ops/dashboard.json modified, and it is never
    # committed here (single writer: the Routine's own commit). Set the working
    # copy aside for the publish and put it back afterwards, whatever happens.
    dashboard_path = repo / DASHBOARD_RELPATH
    set_aside = None
    dash_status = _git(repo, "status", "--porcelain", "--", DASHBOARD_RELPATH.as_posix()).stdout.strip()
    if dash_status and not dash_status.startswith("??"):
        set_aside = dashboard_path.read_text(encoding="utf-8")
        proc = _git(repo, "checkout", "--", DASHBOARD_RELPATH.as_posix())
        if proc.returncode != 0:
            print(f"git checkout of {DASHBOARD_RELPATH.as_posix()} failed: {proc.stderr.strip()}", file=sys.stderr)
            return 1
        print(f"set aside the modified {DASHBOARD_RELPATH.as_posix()} for the publish; it is restored after")
    try:
        return _publish_clean_checkout(repo, branch, args)
    finally:
        if set_aside is not None:
            dashboard_path.write_text(set_aside, encoding="utf-8")


def _check_unpushed_range(repo: Path, branch: str, head: str = "HEAD",
                          stage: str = "") -> tuple[int | None, int, list[str]]:
    """(exit code or None, count, changed paths) for origin/<branch>..head: the
    commits must exist, hold no merge, and look like exactly one fire. A count of
    zero returns None with no paths; the caller says what that means at its stage."""
    try:
        count, changed = unpublished_commits(repo, branch, head)
        merges = unpublished_merges(repo, branch, head)
    except RuntimeError as exc:
        print(f"git failed{stage}: {exc}", file=sys.stderr)
        return 1, 0, []
    if count == 0:
        return None, 0, []
    rc = _refuse_merges(merges, branch)
    if rc is None:
        rc = _publishable_fire(count, changed)
    return rc, count, changed


def _publish_clean_checkout(repo: Path, branch: str, args: argparse.Namespace) -> int:
    """cmd_publish after the fetch, with the dashboard set aside."""
    # A dirty checkout is never rebased over (git can finish a rebase with exit 0
    # and still leave an autostash's re-application conflicted). One dirty state
    # is the script's own: git_publish exits 1 before the commit too (a failed
    # `git add` or `git commit`), leaving the fire's two files written and
    # uncommitted while `rev-list` sees nothing ahead. That fire is committed here
    # under the token, exactly as cmd_fire would have; any other dirt is refused.
    rc = _commit_uncommitted_fire(repo, branch, args.dry_run)
    if rc is not None:
        return rc
    rc, count, changed = _check_unpushed_range(repo, branch)
    if rc is not None:
        return rc
    if count == 0:
        print(f"nothing to publish: origin/{branch} already has every local commit")
        return 0
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
    # What the rebase left to push; a rebase onto an unmoved branch keeps a merge.
    rc, count, changed = _check_unpushed_range(repo, branch, head, " after rebase")
    if rc is not None:
        return rc
    if count == 0:
        print(f"nothing left to publish: the rebase found origin/{branch} already carries this fire's changes "
              "(another session published the same fire?). Check the journal on origin; `resolve` as usual.")
        return 0
    rc, head = _revalidate_fire(repo, branch, trigger, args, head)
    if rc is not None:
        return rc
    # A corrected record adds a journal commit: re-check the range that is pushed.
    rc, count, changed = _check_unpushed_range(repo, branch, head, " before push")
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
        if _push_rejected(proc):
            print(f"origin/{branch} moved again since the rebase; retrying the same commit cannot succeed and "
                  "nothing was pushed. The local commits are intact: run `publish` again to rebase onto it.",
                  file=sys.stderr)
            return 1
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
          "file plus its journal entry. Stash them (`git stash`), never commit them onto the fire, and do not "
          "`git push`: the guards refuse any push while an unpushed trigger change is on the branch. A `resolve` "
          "leaves the journal modified: commit that, a journal-only commit publishes with the fire.\n"
          + "\n".join(dirty), file=sys.stderr)
    return 3


def _publishable_fire(count: int, changed: list[str]) -> int | None:
    """None when the unpushed commits look like one fire (exactly one trigger file
    plus the journal, nothing else); otherwise print the refusal and return 3."""
    foreign = [c for c in changed if not is_publishable(c)]
    if foreign:
        print(f"refused: the {count} unpushed commit(s) change files outside "
              f"{TRIGGER_DIR_RELPATH.as_posix()}/ and {JOURNAL_RELPATH.as_posix()}: "
              + ", ".join(foreign) + ". `publish` re-publishes a fire and nothing else. Move that work off "
              "this branch (stash it, or carry its commits to another branch): a plain `git push` is refused "
              "while an unpushed trigger change is on the branch, so it cannot go first.",
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
    if not workflow_reads_trigger(repo, trigger, ref=head):
        print(f"refused: no workflow at {head[:12]} reads {TRIGGER_DIR_RELPATH}/{trigger}.json - the push "
              "would run nothing (workflows are read from the commit to be pushed, not the working tree).",
              file=sys.stderr)
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
    # The rebase also integrated journal entries another session pushed while this fire sat unpushed, so a nonce
    # that was unique when `fire` checked it may not be now; publishing the duplicate would leave reconciliation
    # unable to attribute either fire's sidecar (Codex round 5 on PR #28). It is checked here, against `others`,
    # because this is where the fire's own entry is identified exactly: every entry this script writes carries
    # `commit: ""`, so a coarser filter would drop the other session's fresh entry - the very one to compare with.
    reused = reused_nonce(trigger, params, others)
    if reused:
        print(f"refused: {reused}", file=sys.stderr)
        return 3, head
    paid = is_paid_fire(trigger, params)
    budget_params = None
    if paid:
        budget_params = paid_budget_params(trigger, params)
    # Corrections to the fire's own record, applied in one journal-only commit
    # that publishes with the fire:
    # - a fire published long after it was made would carry a stale stamp into
    #   the accounting (budget counts paid entries fired today, the queue
    #   expires entries older than expire_hours): restamp to the publication
    #   time, the original kept alongside, when the entry is from another UTC
    #   day or older than an hour or than half the expiry window;
    # - a paid fire's max_spend and lane are what inflight_max_spend counts for
    #   the day of the fire: they must equal what cmd_fire computes from the final
    #   params, not what a hand edit during conflict recovery left.
    corrections = []
    fired = parse_utc(fire.get("fired_utc"))
    threshold = min(timedelta(hours=1), timedelta(hours=expire_hours) / 2)
    if fired is None or fired.astimezone(timezone.utc).date() != now.date() or (now - fired) >= threshold:
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
    # The nonce is the join key between this entry and the cost sidecar the run lands, and the run takes it from
    # the TRIGGER FILE, not from here. The supported recovery for a nonce another session took is to re-nonce the
    # trigger file and publish again - which left the entry on the old value, so the sidecar carried one nonce and
    # the journal another and reconciliation could never join them (Codex round 7 on PR #28). Written exactly as
    # cmd_fire writes it, so the two paths cannot diverge.
    published_nonce = str(params["_nonce"]) if params.get("_nonce") not in (None, "") else None
    if fire.get("nonce") != published_nonce:
        corrections.append(f"nonce {fire.get('nonce')!r} -> {published_nonce!r} (the published trigger file's)")
        fire["nonce"] = published_nonce
    # ...and the digest of what is actually being published, for the same reason: a re-nonced or hand-corrected
    # trigger file is different bytes, and the gate compares bytes (Codex round 9 on PR #28)
    published_digest = params_digest(text)
    # only when the entry HAS a digest and it is now wrong. Backfilling one onto an entry that never carried it is
    # not a correction, and it would force a journal-correction commit in states where `publish` is inspecting a
    # captured commit that is not the branch tip - where the guard below rightly refuses to make one.
    # ...and the ref it is being published to, on the same terms: `publish` pushes the current branch, so an entry
    # naming another one would be a reservation the gate refuses on arrival (Codex round 11 on PR #28)
    if fire.get("ref") and fire["ref"] != branch:
        corrections.append(f"ref {fire.get('ref')!r} -> {branch!r} (the branch being published to)")
        fire["ref"] = branch
    if fire.get("params_sha256") and fire["params_sha256"] != published_digest:
        corrections.append(f"params_sha256 {str(fire.get('params_sha256'))[:12]} -> {str(published_digest)[:12]} "
                           "(the published trigger file's)")
        fire["params_sha256"] = published_digest
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
        # The committed journal must be exactly the entries validated above: a
        # write by another process between save_journal and `git add` would
        # otherwise be committed, and the guards below would run on `entries`
        # while the push carried something else.
        if _git_show(repo, corrected, JOURNAL_RELPATH.as_posix()) != journal_text(entries):
            print(f"refused: the journal committed in {corrected[:12]} is not the corrected journal this run "
                  "validated (another process wrote ops/trigger_journal.jsonl meanwhile). Nothing is pushed; "
                  "inspect the branch and `publish` again.", file=sys.stderr)
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
    # max_spend is excluded from the day's held sum exactly as when cmd_fire approved it.
    if paid:
        # Both from the commit to be pushed, like every other input above: a
        # dashboard or override written to the working tree after `head` was
        # captured is not in what CI and the next session will read.
        dashboard = _json_at(repo, head, DASHBOARD_RELPATH)
        overrides = _json_at(repo, head, OVERRIDES_RELPATH)
        kind, reason = budget_check(budget_params, dashboard, now.strftime("%Y-%m-%d"),
                                    entries=others, now=now, expire_hours=expire_hours,
                                    overrides=overrides, trigger=trigger)
        if kind == "ok":
            print(reason)
        elif kind == "ceiling" and args.override_budget:
            print(f"warning: budget override in effect ({reason})", file=sys.stderr)
        elif park_passes_ceiling(trigger, params, kind):
            # as in cmd_fire: a park whose push was rejected must still be publishable on a full day, or the lane
            # stays unparked until 00:00 UTC (see park_passes_ceiling)
            print(f"park published past the daily ceiling ({reason}): its bytes replace the paid config at rest, "
                  "and the CI gate, which has no such waiver, refuses its own run while the day is full")
        else:
            print(f"refused: {reason}", file=sys.stderr)
            return 4, head
    return None, head


def cmd_park(args):
    """Fire the resting-state park default for one trigger (or every parkable one).

    Each park is a real fire: it runs the full guard chain and costs one cheap
    run in that trigger's lane. With --all, triggers park sequentially and the
    first refusal stops the batch so the operator can read the guard's reason.
    The one guard it passes that other fires do not is a full day's ceiling
    (park_passes_ceiling): no --override-budget is involved, and the CI gate
    still refuses the park's run on that day."""
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
    """Mark the oldest active entry (or every one, --all) resolved: it leaves the
    queue and opens the settle window. It does NOT release a paid entry's
    commitment from the daily ceiling - that holds for the whole UTC day the
    fire was made (entry_holds_spend), because until the ledger folds the run's
    sidecar nothing else counts its cost (2026-09-23)."""
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


def params_digest(text):
    """The digest of a trigger file's exact bytes, which is what CI runs.

    `cmd_fire` records it on the journal entry, so the server-side gate can ask
    whether the reservation it found was taken for THIS content or for an
    earlier fire whose run is already in flight (Codex round 9 on PR #28).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None


def reservation_entries(trigger, params, entries):
    """The journal entries that claim to reserve THIS fire, or None when the
    lane has no join key to look one up by.

    Only petri-audit's params must carry a `_nonce`, and that nonce is what
    binds a fire to its landed cost; the other paid lanes have nothing to match
    on, so they get None and every caller leaves them alone.
    """
    if trigger != "petri-audit" or not is_paid_fire(trigger, params):
        return None
    nonce = params.get("_nonce")
    if isinstance(nonce, bool) or nonce in (None, "") or not str(nonce).strip():
        return []
    # EXACT string equality against the form `cmd_fire` journals (`str(params["_nonce"])`), deliberately unlike
    # `reused_nonce`, which normalises. That one is liberal about what it REFUSES, so coercing is safe there; this
    # one AUTHORISES irreversible spend, and `reconcile` joins the journal's `nonce` to the sidecar's
    # `journal_nonce` with `==`. Coercing here meant a journal entry carrying " n " or 123 satisfied the gate for
    # params "n"/"123" and could then never be joined to the sidecar the run landed: the spend was admitted
    # against a reservation reconciliation can never close (Codex round 10 on PR #28).
    nonce = str(nonce)
    return [e for e in entries
            if e.get("trigger") == trigger and isinstance(e.get("nonce"), str) and e["nonce"] == nonce]


def journal_reservation_problems(trigger, params, entries, now=None, expire_hours=None, digest=None):
    """Why a paid petri-audit run has no journal reservation behind it, as a
    list of refusals; empty when exactly one entry accounts for it.

    `budget-gate` exists because a trigger file can reach a pushed ref without
    passing through `cmd_fire` at all - a merge, a rebase, a hand edit - and it
    already re-runs the lane invariants and the daily ceiling server-side. What
    it did NOT check is the one thing this lane's `_nonce` contract is for: that
    a paid journal entry actually reserved this spend. Without it a pushed
    `mode: run` config with any syntactically valid nonce made irreversible
    provider calls against a reservation that was never taken, and the landed
    sidecar could never be joined to anything (Codex round 7 on PR #28).

    Scoped to petri-audit because it is the lane whose params must carry a
    `_nonce`; the other paid lanes have no join key to check.
    """
    problems = []
    mine = reservation_entries(trigger, params, entries)
    if mine is None:
        return problems
    nonce = str(params.get("_nonce") or "").strip()
    if not nonce:
        # lane_params_problems has already refused this; kept so the function is safe on its own
        return [f"{trigger} mode run carries no usable _nonce, so no journal entry can account for it"]
    if not mine:
        return [f"no {trigger} journal entry carries _nonce {nonce!r}: this trigger file reached the branch "
                "without a reservation (a merge, a rebase or a hand edit), so its spend was never counted "
                "against the daily ceiling and its cost sidecar could never be joined to a fire. Fire through "
                "scripts/fire_trigger.py, which writes the entry and the trigger file in one commit"]
    if len(mine) > 1:
        when = ", ".join(str(e.get("fired_utc")) for e in mine)
        return [f"{len(mine)} {trigger} journal entries carry _nonce {nonce!r} ({when}); a nonce binds one fire "
                "to one landed cost, so this run's spend cannot be attributed"]
    entry = mine[0]
    # ACTIVE, not merely unresolved. `entry_is_active` also releases an entry whose `fired_utc` does not parse and
    # one older than the expiry window, so a stale entry is a reservation whose run has been and gone, and accepting
    # it let a merge or re-push start a second irreversible run under a dead reservation. This is the gap my own
    # round-7 check left by testing only two of the three conditions (Codex round 8).
    # This is the QUEUE reservation, and it is a different invariant from the daily sum. Since 2026-09-23 a resolved
    # or expired entry still counts against the ceiling for the whole UTC day it was fired (entry_holds_spend),
    # because its cost has not necessarily landed on the dashboard; it no longer AUTHORISES a run, because the run it
    # reserved has already happened. The two were one condition before, which is why this used to say "released".
    now = now or utc_now()
    expire_hours = expire_hours if expire_hours is not None else expire_hours_from_env()
    if entry.get("resolved"):
        problems.append(f"the {trigger} journal entry for _nonce {nonce!r} is already resolved: the run it reserved "
                        "is over, so this run would spend outside any reservation")
    elif entry.get("evicted"):
        problems.append(f"the {trigger} journal entry for _nonce {nonce!r} is marked evicted, so the queue "
                        "released its commitment and nothing reserves this run's spend")
    elif not entry_is_active(entry, now, expire_hours):
        fired = entry.get("fired_utc")
        why = ("its fired_utc does not parse" if parse_utc(fired) is None
               else f"it was fired at {fired}, more than {expire_hours:g}h ago")
        problems.append(f"the {trigger} journal entry for _nonce {nonce!r} is no longer active ({why}): the queue "
                        "released it, so nothing reserves this run's spend")
    expected, error = fire_commitment(paid_budget_params(trigger, params))
    if error:
        problems.append(f"the params carry no usable commitment to check against the journal: {error}")
    elif parse_max_spend(entry.get("max_spend")) is None or abs(parse_max_spend(entry["max_spend"]) - expected) > 1e-9:
        # `parse_max_spend`, not a hand-rolled isinstance test: it is what `inflight_max_spend` uses to decide
        # whether the entry holds anything, so anything IT rejects reserves nothing. NaN was the live hole - every
        # comparison with NaN is False, so `abs(nan - expected) > 1e-9` passed the entry here while
        # `inflight_max_spend` skipped it, and `json.loads` accepts a bare NaN in a journal line (Codex round 10).
        problems.append(f"the {trigger} journal entry for _nonce {nonce!r} reserved "
                        f"{entry.get('max_spend')!r} but these params commit {expected!r}; the daily ceiling "
                        "counted the reservation, not what this run would spend")
    # The reservation must have been taken for THIS trigger content. A formatting-only edit, a hand edit or a merge
    # can push the same paid parameters again while the original entry is still active; the run is a push on
    # attempt 1, so it passes the params guard, and matching on the nonce alone let it claim a reservation an
    # earlier run is already spending (Codex round 9 on PR #28). Both runs would then land sidecars carrying one
    # nonce and reconciliation could attribute neither. NOTE the residual: content restored byte-for-byte by a
    # merge while the first run is in flight still matches, which is what the resting-state rule and the park
    # exist to prevent - a paid config must never be the trigger file at rest.
    if digest is None:
        # never skipped: a paid run is gated on bytes, and not being able to read them is a refusal, not a pass
        # (AGENTS.md, no silent failures). In CI the file is always there - it is what fired the workflow.
        problems.append(f"the {trigger} trigger file could not be read, so the reservation for _nonce {nonce!r} "
                        "cannot be checked against the content CI is running")
    else:
        recorded = entry.get("params_sha256")
        if not isinstance(recorded, str) or not recorded:
            problems.append(f"the {trigger} journal entry for _nonce {nonce!r} records no params_sha256, so it "
                            "cannot be shown to have reserved the trigger file CI is running; re-fire through "
                            "scripts/fire_trigger.py")
        elif recorded != digest:
            problems.append(f"the {trigger} journal entry for _nonce {nonce!r} reserved trigger content "
                            f"{recorded[:12]} but CI is running {digest[:12]}: this is a replay of a nonce whose "
                            "reservation belongs to a different fire, so two runs would land one nonce")
    expected_lane = fire_lane(trigger, params)
    if entry.get("lane") != expected_lane:
        problems.append(f"the {trigger} journal entry for _nonce {nonce!r} reserved on lane "
                        f"{entry.get('lane')!r} but these params bill {expected_lane!r}; the wrong account's "
                        "ceiling was counted")
    return problems


def pushed_fire_entry(repo: Path, trigger: str, entries: list[dict], *, digest: str | None, lane: str, today: str,
                      before: str | None, ref: str | None, attempt: str | None) -> dict | None:
    """The journal entry THIS push added for THIS fire of a paid lane with no nonce contract, or None.

    `cmd_fire` runs budget_check before it appends its entry, then commits the trigger file and the entry
    together, so by the time CI runs `budget-gate` the entry is on the branch, `inflight_max_spend` counts it, and
    the gate adds the params' commitment on top. petri-audit removes its own entry by nonce; the other paid lanes
    have no join key, so `reservation_entries` returns None for them and nothing was removed. A scenario-generation
    fire of 1.50 under the $2 ceiling passed locally and was refused in CI as 3.00 - reproduced through the real
    fire path for scenario-generation, model-evaluation and advice-eval (G4, 2026-09-23). No provider call was
    made, so it failed safe, but the server-side check refused every fire the local one approved above half the
    remaining ceiling.

    An entry qualifies only when all of these hold, so anything not provably this push's own fire keeps counting:
    - its trigger matches and its params_sha256 equals `digest`, the digest of the trigger file in the checkout
      (the bytes CI runs; Codex round 9 on PR #28);
    - it holds spend today on `lane`, the lane budget_check will sum (entry_holds_spend), so exactly what was
      counted is what is removed;
    - it records `ref`, the branch CI is running on: a fire commit merged or cherry-picked onto a second branch is a
      second run there, and the entry belongs to the branch it was fired on (Codex round 11 on PR #28);
    - it is absent from the journal at `before`, the push's previous tip. `cmd_fire` writes the entry and the
      trigger file in ONE commit, so an entry already on the branch was taken by an earlier fire, and this push -
      a merge or a revert restoring the same bytes while that run may still be spending - replays it (Codex round
      10 on PR #28). Matching on the digest alone would count such a replay once too few;
    - the run is the push's FIRST attempt (`attempt` is "1", GitHub's github.run_attempt). An Actions-tab re-run
      reuses the original push event - the same github.sha, github.event.before and github.ref_name - so every
      fact above matches again on attempt 2, and leaving the entry out there admits the re-run's spend with the
      first attempt's commitment uncounted: a 1.20 fire under the $2 ceiling cleared on both attempts, 2.40
      against 2.00 (review of this change, 2026-09-23). On a later attempt the entry keeps counting for the first
      attempt and the params count for this one, the double count the gate applied before. petri_audit.yml
      refuses a paid re-run outright in its params job (Codex round 8 on PR #28); these three lanes do not, so
      this is where a re-run is caught. The residual is older than G4 and unchanged by it: attempt 3 and later
      are still counted as two commitments, not three or more, because nothing records how many earlier attempts
      spent. Refusing re-runs as petri does, or counting the attempt number, is the owner's decision.

    Entries are keyed on (trigger, fired_utc), the journal's identity everywhere else (journal_entries_added, the
    ORDERED UNION rule). None - nothing removed, the double count the gate applied before, which fails closed -
    whenever that cannot be established: no `digest`, no `ref`, no `before` (a workflow_dispatch, whose run has no
    journal entry of its own), no `attempt` or any attempt but the first, the all-zero sha of a ref creation, a
    commit this clone does not have, a journal in `before`'s tree whose content could not be fetched
    (journal_at_previous_tip), or a journal at `before` with a line that does not parse (that line could be the
    entry). The entry's max_spend is
    deliberately NOT compared with the params' commitment: advice-eval's --params-file holds the resolved params
    with the workflow's defaults filled in, so a genuine fire could fail that comparison. Several entries can
    qualify only when one push carries several fires of the same bytes, which `publish` refuses; a push runs the
    lane once, so the newest (journal order breaking ties) is removed and the rest keep counting.
    """
    if digest is None or not isinstance(ref, str) or not ref.strip():
        return None
    # exact "1", not int(): a missing, empty or unparseable attempt is not known to be the first, so it counts twice
    if not isinstance(attempt, str) or attempt.strip() != "1":
        return None
    # None from journal_at_previous_tip is "unreadable" (no ref, the all-zero sha, a commit this clone lacks, a blob
    # a blobless clone could not fetch); only [] - a tree with no journal - may read as "no earlier entries"
    earlier, problems = journal_at_previous_tip(repo, before)
    if earlier is None or problems:
        return None
    was_there = {(e.get("trigger"), e.get("fired_utc")) for e in earlier}
    candidates = [e for e in entries
                  if e.get("trigger") == trigger
                  and e.get("params_sha256") == digest
                  and e.get("ref") == ref.strip()
                  and entry_holds_spend(e, today, lane)
                  and (e.get("trigger"), e.get("fired_utc")) not in was_there]
    if not candidates:
        return None
    # entry_holds_spend has parsed every stamp; sorted is stable, so the last of equal stamps is the later line
    return sorted(candidates, key=lambda e: parse_utc(e["fired_utc"]))[-1]


def _petri_resolved(params):
    """A petri-audit trigger file's parameters as the workflow's params job resolves them: the heredoc defaults
    (the park, which tests/test_petri_audit_workflow.py pins to them) overlaid with the file's values, a list of
    seed ids joined with spaces, a JSON boolean lower-cased, everything a string."""
    resolved = dict(PARK_DEFAULTS["petri-audit"])
    # the adaptive auditor is read by some modes only and is not a key of the park (docs/petri_adaptive_design.md);
    # a readapt must state its source run's, empty for a scripted source, as the params job resolves it
    resolved.setdefault("auditor_model", "")
    for key, value in params.items():
        if key not in resolved:
            continue
        if key == "seed_ids" and isinstance(value, list):
            value = " ".join(str(s) for s in value)
        resolved[key] = str(value).lower() if isinstance(value, bool) else str(value)
    return resolved


def _petri_values_differ(key, mine, theirs):
    """Whether two resolved values of `key` would make the workflow do different things: numbers compared as
    numbers ("6.10" is 6.1), seed ids as whitespace-separated sequences, booleans canonically; a value that does
    not parse is compared as text, so it can only differ."""
    try:
        if key in ("max_spend", "judge_max_spend"):
            return abs(float(mine) - float(theirs)) > 1e-9
        if key in ("epochs", "token_limit", "judge_max_tokens", "wave"):
            return int(mine) != int(theirs)
    except ValueError:
        return mine != theirs
    if key == "seed_ids":
        return mine.split() != theirs.split()
    if key in PETRI_BOOLEAN_KEYS:
        return mine.strip().lower() != theirs.strip().lower()
    return mine != theirs


def _trigger_content_by_digest(repo, trigger, digest):
    """(commit, content) of the most recent version of the trigger file on this branch's history whose bytes
    digest to `digest` (what `cmd_fire` journals as params_sha256), or None when no version does.

    `--full-history`, because a merge that keeps one side's trigger file hides the other side's versions from
    git's default path simplification. The hand merge of a firing branch into main restores main's trigger files
    (AGENTS.md, merge danger), so on main afterwards the source fire's commit is an ancestor but its version of
    the file was not listed, and a readapt fired from main was refused as unrecoverable. The digest still binds
    the content to the journal entry, so searching every ancestor's version admits nothing the digest does not."""
    rel = (TRIGGER_DIR_RELPATH / f"{trigger}.json").as_posix()
    log = _git(repo, "log", "--full-history", "--format=%H", "--", rel)
    if log.returncode != 0:
        return None
    for commit in log.stdout.split():
        text = _git_show(repo, commit, rel)
        if text is not None and params_digest(text) == digest:
            return commit, text
    return None


def petri_active_readapt_problems(repo, trigger, actives):
    """Why a petri-audit fire may not enter the lane behind the active entries `actives`: each one that is a
    readapt, and each one whose mode cannot be established. Empty for every other trigger and for an idle lane.

    A journal entry records the digest of the trigger file its fire wrote (`params_sha256`), not its parameters,
    so the mode is read from that content: the trigger file on disk when it carries the digest (the latest fire),
    else the version in this branch's history that does. An entry with no digest, or content that cannot be found
    or parsed, cannot be shown not to be a readapt, so it refuses rather than admitting a fire behind a readapt
    it failed to see (AGENTS.md, no silent failures)."""
    if trigger != "petri-audit" or not actives:
        return []
    try:
        on_disk = (Path(repo) / TRIGGER_DIR_RELPATH / f"{trigger}.json").read_text(encoding="utf-8")
    except OSError:
        on_disk = None
    problems = []
    for entry in actives:
        label = f"the active {trigger} entry fired {entry.get('fired_utc', '?')} (nonce {entry.get('nonce')!r})"
        digest = entry.get("params_sha256")
        if not isinstance(digest, str) or not digest:
            problems.append(f"{label} records no params_sha256, so whether it is a readapt cannot be established")
            continue
        if on_disk is not None and params_digest(on_disk) == digest:
            text = on_disk
        else:
            found = _trigger_content_by_digest(repo, trigger, digest)
            text = found[1] if found is not None else None
        if text is None:
            problems.append(f"{label}: the trigger content it journaled ({digest[:12]}) is neither on disk nor in this "
                            "branch's history, so whether it is a readapt cannot be established")
            continue
        try:
            fired = json.loads(text)
        except ValueError:
            fired = None
        if not isinstance(fired, dict):
            problems.append(f"{label}: the trigger content it journaled ({digest[:12]}) is not a JSON object, so "
                            "whether it is a readapt cannot be established")
        elif petri_mode(fired) == PETRI_READAPT_MODE:
            problems.append(f"{label} is a readapt (source_run_id {fired.get('source_run_id')!r})")
        elif petri_mode(fired) == PETRI_REJUDGE_MODE:
            problems.append(f"{label} is a rejudge (source_runs {fired.get('source_runs')!r})")
    return problems


def petri_readapt_source_problems(repo, trigger, params):
    """Why a petri-audit `mode: readapt` fire does not recover the run it names, as a list of refusals; empty
    for every other fire.

    The source run is `data/petri/runs/run_<source_run_id>_1`, which must hold its landed target sidecar and no
    adapted output (a landed run is never rewritten), and that sidecar must record `run_status` success (mode run
    adapts nothing from an error or cancelled run). That sidecar names the source fire's nonce; the journal entry
    carrying it records the digest of the trigger file the source fire wrote; this branch's history of that file
    holds the content with that digest; and the readapt must state the same value for every key in
    PETRI_READAPT_MATCH_KEYS, which are the parameters the log and the judge of record ran under. Run at the fire
    and again in the workflow's budget gate (whose checkout has the full history), before any spend. Content that
    cannot be recovered is a refusal, not a pass: a readapt whose parameters cannot be shown to be the source's is
    not a recovery of it."""
    if trigger != "petri-audit" or petri_mode(params) != PETRI_READAPT_MODE:
        return []
    source = params.get("source_run_id")
    if isinstance(source, bool) or not re.fullmatch(r"[0-9]+", str(source or "")):
        return []                          # petri_params_problems names it
    repo = Path(repo)
    stem = f"run_{source}_1"
    run_dir = repo / PETRI_RUNS_RELPATH / stem
    sidecar = run_dir / f"{stem}.report.json"
    where = f"{PETRI_RUNS_RELPATH.as_posix()}/{stem}"
    if not sidecar.is_file():
        return [f"petri-audit readapt of run {source}: {where} holds no landed target sidecar {sidecar.name}; a "
                "readapt recovers a paid run whose target spend already landed, and books none itself"]
    adapted = sorted(p.name for p in run_dir.iterdir() if p.name in PETRI_ADAPTED_FILES)
    if adapted:
        return [f"petri-audit readapt of run {source}: {where} already holds adapted outputs ({', '.join(adapted)}); "
                "a landed run is never rewritten"]
    # the same directory rule the workflow's plan step applies (scripts/petri_audit/readapt.py run_dir_problems):
    # besides the target sidecar, only the judge sidecars of earlier readapts of this run, which a readapt whose
    # paid judge failed commits and which a retry leaves as they are; anything else is refused here, before the
    # reservation, rather than by the plan step after it
    other = sorted(p.name for p in run_dir.iterdir()
                   if p.name != sidecar.name and not re.fullmatch(re.escape(stem) + PETRI_READAPT_JUDGE_SUFFIX, p.name))
    if other:
        return [f"petri-audit readapt of run {source}: {where} holds files other than the landed target sidecar and "
                f"earlier readapts' judge sidecars ({', '.join(other)}); a readapt writes only into the state a failed "
                "adaptation, or a readapt whose judge failed, leaves"]
    try:
        report = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"petri-audit readapt of run {source}: {sidecar.name} does not parse ({exc})"]
    nonce = report.get("journal_nonce") if isinstance(report, dict) else None
    if not isinstance(nonce, str) or not nonce:
        return [f"petri-audit readapt of run {source}: {sidecar.name} records no journal_nonce, so the fire that "
                "ran the source run cannot be found"]
    # the fallback sidecar is written for an error or cancelled run too (it spent), but mode run adapts only a run
    # whose eval completed (`cli run` exits 0 on status success alone), so a readapt recovers only that; the plan
    # step and the adapter refuse it again (scripts/petri_audit/readapt.py), this refuses it before any reservation
    status = report.get("run_status")
    if status != "success":
        return [f"petri-audit readapt of run {source}: {sidecar.name} records run_status {status!r}, not 'success'; "
                "a readapt recovers only a run whose eval completed, since mode run publishes nothing from an error "
                "or cancelled run"]
    entries = [e for e in load_journal(repo / JOURNAL_RELPATH)
               if e.get("trigger") == "petri-audit" and e.get("nonce") == nonce]
    if len(entries) != 1:
        return [f"petri-audit readapt of run {source}: {len(entries)} journal entries carry the source nonce "
                f"{nonce!r}; exactly one fire must account for the source run"]
    digest = entries[0].get("params_sha256")
    found = _trigger_content_by_digest(repo, trigger, digest) if isinstance(digest, str) and digest else None
    if found is None:
        return [f"petri-audit readapt of run {source}: the trigger content the source fire {nonce!r} journaled "
                f"(params_sha256 {str(digest)[:12]}) is not in this branch's history of "
                f"{TRIGGER_DIR_RELPATH.as_posix()}/{trigger}.json, so the parameters it ran under cannot be "
                "recovered and the readapt cannot be shown to match them; fire from a branch that carries the "
                "source fire's commit"]
    commit, text = found
    try:
        source_params = json.loads(text)
    except ValueError as exc:
        return [f"petri-audit readapt of run {source}: the source fire's trigger file at {commit[:12]} does not "
                f"parse ({exc})"]
    mine, theirs = _petri_resolved(params), _petri_resolved(source_params)
    differ = [f"{k} {mine[k]!r} (source {theirs[k]!r})" for k in PETRI_READAPT_MATCH_KEYS
              if _petri_values_differ(k, mine[k], theirs[k])]
    if differ:
        return [f"petri-audit readapt of run {source}: the parameters differ from those the source fire {nonce!r} "
                f"ran under (its trigger file at {commit[:12]}): " + "; ".join(differ)]
    return _petri_seed_drift_problems(repo, source, commit, mine)


def _git_show_utf8(repo, ref, relpath):
    """The file's content at `ref` decoded as UTF-8 whatever the locale, or None when git has no such blob."""
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{relpath}"], capture_output=True)
    if proc.returncode != 0:
        return None
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _petri_seed_selection(text, resolved):
    """{seed_id: canonical JSON of the seed} for the selection a petri-audit run makes from a seed file's text, as
    `seeds.select_seeds` makes it from the workflow's resolved params: the listed seed ids when there are any,
    else every seed of the wave. The canonical form is `framework.canonical_json`, so two seeds are equal here
    exactly when their `seeds.seed_digest` is. Raises ValueError naming what does not resolve."""
    doc = json.loads(text)
    seeds = doc.get("seeds") if isinstance(doc, dict) else None
    if not isinstance(seeds, list) or not all(isinstance(s, dict) and isinstance(s.get("seed_id"), str) for s in seeds):
        raise ValueError("it holds no `seeds` list of objects with a seed_id")
    by_id = {s["seed_id"]: s for s in seeds}
    if len(by_id) != len(seeds):
        raise ValueError("it lists a seed id twice")
    ids = resolved["seed_ids"].split()
    if ids:
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise ValueError(f"it has no seed {missing}")
    else:
        ids = [i for i, s in by_id.items() if str(s.get("pilot_wave")) == str(int(resolved["wave"]))]
        if not ids:
            raise ValueError(f"it has no seed in wave {resolved['wave']}")
    return {i: json.dumps(by_id[i], sort_keys=True, ensure_ascii=False, separators=(",", ":")) for i in ids}


def _petri_seed_drift_problems(repo, source, commit, resolved):
    """Why the seeds a readapt would adapt against are not the seeds the source run executed. The source run
    checked out its fire commit (the one holding the journaled trigger content), so the seed file there is the
    content it ran; the readapt's adapter, judge and analysis read the seed file at this checkout's HEAD. The
    selection the params make is resolved against both and must name the same seeds with identical content (the
    per-seed digest, which the adapter checks again against the log's own per-sample record). A change elsewhere
    in the file (another wave's seeds, the file's schema block) is not drift. Refused here, before the
    reservation, and in the budget gate before the audit job; the file being unreadable is a refusal too."""
    rel = resolved["seeds_file"]
    where = f"petri-audit readapt of run {source}"
    texts = {}
    for label, ref in (("the source fire's commit", commit), ("this checkout's HEAD", "HEAD")):
        text = _git_show_utf8(repo, ref, rel)
        if text is None:
            return [f"{where}: the seed file {rel} cannot be read at {label} ({ref[:12]}), so the seeds the source "
                    "run executed cannot be compared with the ones the readapt would adapt against"]
        texts[label] = text
    selections = {}
    for label, text in texts.items():
        try:
            selections[label] = _petri_seed_selection(text, resolved)
        except (ValueError, KeyError) as exc:
            return [f"{where}: the seed file {rel} at {label} does not resolve the source run's selection ({exc})"]
    then, now = selections["the source fire's commit"], selections["this checkout's HEAD"]
    problems = []
    if sorted(then) != sorted(now):
        added, removed = sorted(set(now) - set(then)), sorted(set(then) - set(now))
        problems.append(f"the selection resolves to other seeds at HEAD than at the source fire's commit {commit[:12]} "
                        f"(added {added or 'none'}, removed {removed or 'none'})")
    for sid in sorted(set(then) & set(now)):
        if then[sid] != now[sid]:
            old = hashlib.sha256(then[sid].encode("utf-8")).hexdigest()[:12]
            new = hashlib.sha256(now[sid].encode("utf-8")).hexdigest()[:12]
            problems.append(f"seed {sid} changed since the source run (digest {old} at {commit[:12]}, {new} at HEAD)")
    if problems:
        return [f"{where}: the seeds in {rel} are not the ones the source run executed: " + "; ".join(problems)
                + ". The adapter, the judge and the analysis read the seed file in the checkout, so the log cannot "
                "be re-adapted against it; fire from a commit whose selected seeds are the source run's"]
    return []


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
    # lane invariants the fire path enforces in validate_params run here too, because a workflow_dispatch never
    # passes through fire_trigger (Codex round 3)
    problems = lane_params_problems(args.trigger, params, providers_registry(repo))
    # a readapt must be the recovery of the run it names, with that run's parameters, checked here against this
    # checkout's runs, journal and history as the fire path checked it against the operator's (mode readapt)
    problems = problems or petri_readapt_source_problems(repo, args.trigger, params)
    # ...and a rejudge must re-grade landed runs with another judge into directories that hold no re-grade yet
    problems = problems or petri_rejudge_source_problems(repo, args.trigger, params)
    if problems:
        for problem in problems:
            print(f"budget-gate: REFUSED - {problem}", file=sys.stderr)
        return 6
    if not is_paid_fire(args.trigger, params):
        print(f"budget-gate: {args.trigger} is a free fire; clear")
        return 0
    budget_params = paid_budget_params(args.trigger, params)
    now = utc_now()
    entries = load_journal(repo / JOURNAL_RELPATH)
    # the reservation itself, before the aggregate: a ceiling that holds in total says nothing about whether THIS
    # run was ever reserved (Codex round 7 on PR #28)
    # the digest is taken from the TRIGGER FILE in the checkout, not from --params-file: the workflow passes the
    # resolved params job outputs there, while what fired CI is the file itself
    trigger_on_disk = repo / TRIGGER_DIR_RELPATH / f"{args.trigger}.json"
    try:
        digest = params_digest(trigger_on_disk.read_text(encoding="utf-8"))
    except OSError:
        digest = None
    unreserved = journal_reservation_problems(args.trigger, params, entries, now=now,
                                              expire_hours=expire_hours_from_env(), digest=digest)
    # ...and the reservation must have been taken by THIS push, not merely for this content: identical bytes can
    # be restored by a merge while the first run is still spending them (Codex round 10 on PR #28)
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    unreserved += push_reservation_problems(repo, args.trigger, params, getattr(args, "push_before", None), in_ci)
    # ...and on THIS ref: "first appearance on this branch" is a fresh reservation to the push binding, which a
    # merge or cherry-pick of the fire commit onto another branch produces for free (Codex round 11 on PR #28)
    unreserved += ref_reservation_problems(args.trigger, params, entries, getattr(args, "ref", None), in_ci)
    if unreserved:
        for problem in unreserved:
            print(f"budget-gate: REFUSED - {problem}", file=sys.stderr)
        return 6
    # ...and once the reservation is found, it must not be counted TWICE. `cmd_fire` runs this check before it
    # writes the journal entry; by the time CI runs it the entry is on the branch, so `inflight_max_spend` already
    # holds this fire's commitment and adding the params' commitment on top double-counts it. The pilot's $1.50
    # came to $3.00 against the $2.00 ceiling and would have been refused server-side - the first paid fire, by the
    # guard meant to protect it (found writing the round-7 reservation test, 2026-09-18). At most ONE entry is
    # removed - on petri-audit the one this fire is bound to by nonce, on the other paid lanes the one this push
    # provably added - so nothing else's hold is lost.
    today = now.strftime("%Y-%m-%d")
    lane = fire_lane(args.trigger, budget_params)       # the lane budget_check will sum, so the test below matches it
    mine = reservation_entries(args.trigger, params, entries)
    if mine is not None:
        if len(mine) == 1 and entry_holds_spend(mine[0], today, lane):
            # removed only when the day's sum counts it, so exactly what was counted is removed. That is no longer
            # the same as ACTIVE (2026-09-23): the sum also holds entries resolved or expired earlier today, and an
            # active entry fired before midnight UTC is not in today's sum at all. The reservation check above still
            # demands an active one; this is only about not counting it twice.
            held = mine[0]
            entries = [e for e in entries if e is not held]
    else:
        # the other paid lanes have no nonce, so their own entry is found by what this push added (G4, 2026-09-23;
        # see pushed_fire_entry). Whatever cannot be shown to be this push's fire keeps counting.
        own = pushed_fire_entry(repo, args.trigger, entries, digest=digest, lane=lane, today=today,
                                before=getattr(args, "push_before", None), ref=getattr(args, "ref", None),
                                attempt=getattr(args, "run_attempt", None))
        if own is not None:
            entries = [e for e in entries if e is not own]
            print(f"budget-gate: this push's own {args.trigger} journal entry (fired {own.get('fired_utc')}) is left "
                  "out of today's held sum; the params' commitment stands in for it")
        else:
            print(f"budget-gate: no {args.trigger} journal entry is shown to be this push's own fire (a dispatch, a "
                  "replay, a re-run, or no --push-before/--ref/--run-attempt to bind one), so every held commitment "
                  "is counted")
    dashboard = load_dashboard(repo / DASHBOARD_RELPATH)
    overrides = load_budget_overrides(repo / OVERRIDES_RELPATH)
    kind, reason = budget_check(budget_params, dashboard, today,
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
    gate.add_argument("--ref",
                      help="the ref CI is running on (GitHub's github.ref_name). A paid petri-audit fire is "
                           "refused when its journal entry was fired on a different branch: the same fire commit "
                           "reaching a second ref by merge or cherry-pick is a second run, and one reservation "
                           "cannot cover both. Required for petri-audit when GITHUB_ACTIONS is set. On the other "
                           "paid lanes it is one of the facts that identify this push's own journal entry, which "
                           "is then counted once instead of twice; without it nothing is left out.")
    gate.add_argument("--push-before",
                      help="the commit this ref pointed at before the push CI is running (GitHub's "
                           "github.event.before). A paid petri-audit fire is refused when its reservation was "
                           "already on the branch at that commit: fire_trigger writes the entry and the trigger "
                           "file in one commit, so an older reservation means this push replays it. Required "
                           "for petri-audit when GITHUB_ACTIONS is set. On the other paid lanes an entry absent "
                           "at that commit is this push's own, and is counted once instead of twice; without it "
                           "(a workflow_dispatch passes an empty value) nothing is left out.")
    gate.add_argument("--run-attempt",
                      help="the run's attempt number (GitHub's github.run_attempt). On the paid lanes other than "
                           "petri-audit, this push's own journal entry is left out of the day's held sum only on "
                           "attempt 1: an Actions-tab re-run reuses the push event, so on a later attempt the entry "
                           "stands for the first attempt's commitment and keeps counting. Without it nothing is "
                           "left out. (petri-audit refuses a paid re-run in its params job instead.)")
    gate.set_defaults(func=cmd_budget_gate)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    ensure_git_hooks(Path(args.repo).resolve())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
