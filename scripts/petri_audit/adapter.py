"""The deterministic `.eval` adapter (design memo section 9). Python 3.12 only.

Reads one Inspect log with attachments resolved and timelines rebound, walks
each sample's target timeline, and writes, under one output directory:

- `transcripts.jsonl`: one transcript 0.2 record per trajectory node
  (root-to-node path, replayed prefix included), bound to the manifest's
  identity digest;
- `rule_outcomes.jsonl`: the rule outcomes per record;
- `sanitised_log.json`: the allowlist projection of the raw log;
- `manifest.json`: the closed run manifest with the contract checks, sealed
  into the directory's hash chain.

The same log and the same seed file produce byte-identical outputs: every
timestamp comes from the log, never from the clock, and every ordering is the
log's creation order. Nothing is dropped silently: a record the adapter cannot
write is listed in `integrity.records_refused` with its reason, an empty
branch is counted, and every contract check carries a detail string.
"""
from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from inspect_ai.event import InfoEvent, ModelEvent, TimelineSpan
from inspect_ai.log import EvalLog, EvalSample, read_eval_log
from inspect_ai.log._resolve import rebind_sample_timelines
from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
from inspect_petri import select_timeline
from inspect_scout import span_messages

from .checks import (
    ROOT_BRANCH,
    branch_staged_texts,
    claim_grade_eligible,
    condition_text_pool,
    coverage_problems,
    expected_stimuli,
    staging_problems,
    stimulus_problems,
)
from .controller import INFO_SOURCE
from .envlock import installed_harness_commit, load_lock
from .framework import (
    FRAMING_REGISTRY,
    OUTCOME_REGISTRY,
    ROOT,
    sha256_file,
    sha256_text,
    write_json,
)
from .manifest import MANIFEST_VERSION, append_chain, chain_head, manifest_problems, seal_manifest, write_manifest
from .rules import rule_record
from .sanitizer import _project_eval, allowlist_digest, load_allowlist, sanitise_log
from .seal import scan_strings, sealed_registry, seed_texts_against_registry
from .seeds import SeedSet, conditions, seed_digest, text_of, tool_result_for
from .spend import pricing_source_digest, reprice_usage
from .transcripts import bind_manifest, build_record, conversation_id, record_problems

ADAPTER_NAME = "petri_audit.adapter"
ADAPTER_VERSION = "0.1"
# inspect-ai 0.3.237 forwards GenerateConfig.seed on these providers (design memo section 2); anthropic and
# google never send it; mock and placeholder models have no provider behaviour to record.
SEED_FORWARDING: dict[str, bool | None] = {
    "openai": True, "openrouter": True, "openai-api": True, "together": True, "ollama": True, "vllm": True,
    "azureai": True, "grok": True, "groq": True, "hf": True, "mistral": True, "sagemaker": True,
    "vllm_completions": True, "anthropic": False, "google": False, "mockllm": None, "none": None,
}
_BRANCH_NAME = re.compile(r"^branch (\d+)$")


class AdapterError(RuntimeError):
    pass


def utc_seconds(stamp: str | None) -> str | None:
    """Inspect's ISO timestamps reformatted to the schema's second-precision Z
    form; None stays None (never a guess)."""
    if not stamp:
        return None
    parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Check:
    status: str = "not_run"
    detail: str | None = None

    def fail(self, detail: str) -> None:
        self.status = "fail"
        self.detail = detail if self.detail is None else f"{self.detail}; {detail}"

    def ok(self, detail: str | None = None) -> None:
        if self.status == "not_run":
            self.status, self.detail = "pass", detail

    def as_dict(self) -> dict:
        return {"status": self.status, "detail": self.detail}


@dataclass
class AdaptResult:
    out_dir: Path
    manifest: dict
    records: list[dict]
    rule_records: list[dict]
    refused: list[dict] = field(default_factory=list)

    @property
    def claim_grade_eligible(self) -> bool:
        return bool(self.manifest["execution"]["claim_grade_eligible"])


# ---------------------------------------------------------------- messages


def _message_to_simple(m: Any) -> dict:
    out: dict[str, Any] = {"role": m.role, "text": m.text or "", "id": m.id, "tool_calls": None, "tool_call_id": None,
                           "prefill": bool((m.metadata or {}).get("prefill")) if getattr(m, "metadata", None) else False}
    if isinstance(m, ChatMessageAssistant) and m.tool_calls:
        out["tool_calls"] = [{"call_id": c.id, "name": c.function, "arguments": dict(c.arguments or {}),
                              "parse_error": c.parse_error} for c in m.tool_calls]
    if isinstance(m, ChatMessageTool):
        out["tool_call_id"] = m.tool_call_id
        if m.error is not None and not out["text"]:
            out["text"] = m.error.message
    return out


def _creation_index(span: TimelineSpan, fallback: int) -> int:
    m = _BRANCH_NAME.match(span.name or "")
    return int(m.group(1)) if m else fallback


def _walk_nodes(root: TimelineSpan) -> list[tuple[TimelineSpan, TimelineSpan | None, int]]:
    """(span, parent span, creation index) for the root and every descendant,
    in creation order."""
    out: list[tuple[TimelineSpan, TimelineSpan | None, int]] = [(root, None, _creation_index(root, 1))]
    fallback = 1_000_000

    def collect(node: TimelineSpan) -> None:
        nonlocal fallback
        for b in node.branches:
            out.append((b, node, _creation_index(b, fallback)))
            fallback += 1
            collect(b)

    collect(root)
    out.sort(key=lambda x: x[2])
    return out


def _pw_events(sample: EvalSample) -> list[dict]:
    return [e.data for e in sample.events if isinstance(e, InfoEvent) and e.source == INFO_SOURCE and isinstance(e.data, dict)]


def _target_model_events(sample: EvalSample) -> list[ModelEvent]:
    return [e for e in sample.events if isinstance(e, ModelEvent) and e.role == "target"]


# ------------------------------------------------------------------ adapt


def adapt_run(eval_path: Path | str, seed_set: SeedSet, out_dir: Path | str, *, custody: str, spend: dict,
              registry_spec: str | None = None, engine_sha: str | None = None, lock_path: Path | str | None = None,
              registry: dict | None = None, harness_commit: str | None = None) -> AdaptResult:
    eval_path, out_dir = Path(eval_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log: EvalLog = read_eval_log(str(eval_path), resolve_attachments=True)
    if log.samples is None:
        raise AdapterError(f"{eval_path}: log has no samples")
    spec = log.eval
    raw_sha = sha256_file(eval_path)
    allowlist = load_allowlist()
    created_utc = utc_seconds(spec.created) or spec.created
    import_utc = utc_seconds(log.stats.completed_at) or created_utc
    target_role = (spec.model_roles or {}).get("target")
    target_name = target_role.model if target_role else spec.model
    target_provider = target_name.split("/", 1)[0] if "/" in target_name else "anthropic"

    checks = {k: Check() for k in ("stimulus_digest_identity", "arms_in_one_run", "generation_config_pinned",
                                   "no_prefill", "no_cache", "tool_results_from_data", "holdout_seal")}
    refused: list[dict] = []
    records: list[dict] = []
    rule_records: list[dict] = []
    trees: list[dict] = []
    dropped_empty = 0
    served_all: set[str] = set()
    role_usage: dict[str, dict[str, Any]] = {}
    model_usage: dict[str, dict[str, Any]] = {}
    seen_counts: dict[str, dict[str, int]] = {}
    any_tools = False
    prefill_seen = False
    cache_seen = False
    calls_missing = 0
    config_detail: list[str] = []
    seeds_used: dict[str, dict] = {}
    max_turns = 0

    def usage_row(bucket: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
        return bucket.setdefault(key, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                                       "input_tokens_cache_read": None, "input_tokens_cache_write": None,
                                       "reasoning_tokens": None, "calls": 0, "calls_without_usage": 0})

    def accumulate(bucket: dict[str, dict[str, Any]], key: str, usage: Any) -> None:
        row = usage_row(bucket, key)
        row["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
        row["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
        row["total_tokens"] += int(getattr(usage, "total_tokens", 0) or 0)
        for attr in ("input_tokens_cache_read", "input_tokens_cache_write", "reasoning_tokens"):
            value = getattr(usage, attr, None)
            if value is not None:
                row[attr] = (row[attr] or 0) + int(value)

    for sample in sorted(log.samples, key=lambda s: (str(s.id), s.epoch)):
        sample = rebind_sample_timelines(sample)
        meta = sample.metadata or {}
        seed_id = meta.get("seed_id")
        seed = seed_set.seeds.get(seed_id) if seed_id else None
        tree_id = f"{sample.id}#{sample.epoch}"
        if seed is None:
            refused.append({"branch_id": f"{tree_id}:{ROOT_BRANCH}", "reason": f"sample metadata names no known seed ({seed_id!r})"})
            continue
        seeds_used[seed_id] = seed
        max_turns = max(max_turns, seed["protocol"]["max_target_turns"])
        if seed.get("tools"):
            any_tools = True
        cond = next((c for c in conditions(seed) if c["condition_id"] == meta.get("condition_id")), None)
        if cond is None:
            refused.append({"branch_id": f"{tree_id}:{ROOT_BRANCH}", "reason": f"unknown condition {meta.get('condition_id')!r}"})
            continue
        counts = seen_counts.setdefault(seed_id, {})
        counts[cond["condition_id"]] = counts.get(cond["condition_id"], 0) + 1
        if sample.error:
            refused.append({"branch_id": f"{tree_id}:{ROOT_BRANCH}", "reason": f"sample error: {sample.error}"})
            continue
        model_events = _target_model_events(sample)
        for role, usage in (sample.role_usage or {}).items():
            accumulate(role_usage, role, usage)
        for model, usage in (sample.model_usage or {}).items():
            accumulate(model_usage, model, usage)
        # calls are counted from the events themselves, so a model Inspect recorded no usage for still shows its
        # calls; a call whose output carries no usage block is counted as such and never priced as zero
        # (spend.reprice_usage refuses a priced model with missing usage)
        for e in model_events:
            for bucket, key in ((model_usage, e.model), (role_usage, e.role or "target")):
                row = usage_row(bucket, key)
                row["calls"] += 1
                if e.output is None or e.output.usage is None:
                    row["calls_without_usage"] += 1
        served = {e.output.model for e in model_events if e.output and e.output.model}
        served_all |= served
        # config and raw-request checks read the retained raw request, never the merged config
        expected_gen = seed["generation"]
        for e in model_events:
            if e.cache:
                cache_seen = True
            if e.call is None or not isinstance(e.call.request, dict):
                calls_missing += 1
                continue
            req = e.call.request
            for key, want in (("temperature", expected_gen["temperature"]), ("max_tokens", expected_gen["max_tokens"])):
                if key not in req:
                    config_detail.append(f"{key}: not_sent")
                elif want is not None and req[key] != want:
                    config_detail.append(f"{key}: sent {req[key]!r}, seed {want!r}")
        pw = _pw_events(sample)
        staged = [d for d in pw if d.get("pw") == "staged"]
        branch_infos = [d for d in pw if d.get("pw") == "branch"]
        timeline = select_timeline(sample.timelines or [], "target")
        nodes = _walk_nodes(timeline.root)
        condition_shas = condition_text_pool(seed, cond)
        branches_out: list[dict] = []
        child_index = 0
        for order, (span, parent, creation) in enumerate(nodes):
            if parent is None:
                branch_id, parent_id, anchor_msg = ROOT_BRANCH, None, None
            else:
                if child_index >= len(branch_infos):
                    refused.append({"branch_id": f"{tree_id}:{span.id}", "reason": "trajectory has no matching branch record"})
                    child_index += 1
                    continue
                info = branch_infos[child_index]
                child_index += 1
                branch_id, parent_id, anchor_msg = info["branch_id"], info["parent_branch_id"], info["anchor_message_id"]
                if span.branched_from != anchor_msg:
                    refused.append({"branch_id": f"{tree_id}:{branch_id}",
                                    "reason": f"branch anchor {span.branched_from!r} differs from the recorded anchor {anchor_msg!r}"})
                    continue
            messages = span_messages(span)
            if not messages:
                dropped_empty += 1
                continue
            simple = [_message_to_simple(m) for m in messages]
            if any(m["prefill"] for m in simple):
                prefill_seen = True
            conv_id = conversation_id(spec.eval_id, sample.uuid or str(sample.id), branch_id)
            record = build_record(simple, conversation_id=conv_id, source_system="inspect_petri", source_model=target_name,
                                  model_version=(min(served) if len(served) == 1 else None), captured_utc=created_utc,
                                  user_is=cond["user_is"], import_utc=import_utc, importer_sha=engine_sha,
                                  run_manifest_sha256=None, run_manifest_ref=None)
            if len(served) > 1:
                refused.append({"branch_id": f"{tree_id}:{branch_id}", "reason": f"more than one served model string on the tree: {sorted(served)}"})
                continue
            problems = record_problems({**record, "provenance": {**record["provenance"], "run_manifest": None}})
            if problems:
                refused.append({"branch_id": f"{tree_id}:{branch_id}", "reason": "; ".join(problems[:5])})
                continue
            # staged-text identity: the record's user and system turns are exactly the sequence this condition
            # and branch declare (never merely members of the seed's text pool), and the controller's staging
            # records for the branch name the same texts; tool results are the seed's templates with the
            # recorded query substituted, and a generated error result is a contract failure, not seed data
            where = f"{tree_id}:{branch_id}"
            try:
                expected = expected_stimuli(seed, cond, branch_id)
                staged_here = branch_staged_texts(seed, cond, branch_id)
            except KeyError as exc:
                checks["stimulus_digest_identity"].fail(f"{where}: {exc}")
                expected, staged_here = [], []
            for problem in stimulus_problems(expected, record["turns"], where=where):
                checks["stimulus_digest_identity"].fail(problem)
            staged_shas = [s.get("sha256") for s in staged
                           if s.get("kind") in ("user", "system") and s.get("branch_id") == branch_id]
            for problem in staging_problems(staged_here, staged_shas, where=where):
                checks["stimulus_digest_identity"].fail(problem)
            for turn in record["turns"]:
                if turn["role"] == "tool":
                    hit = next((s for s in staged if s.get("kind") == "tool_result" and s.get("tool_call_id") == turn["tool_call_id"]), None)
                    if hit is None:
                        checks["tool_results_from_data"].fail(f"{where} turn {turn['turn_id']}: tool result has no staging record")
                    elif hit.get("status") != "success":
                        checks["tool_results_from_data"].fail(
                            f"{where} turn {turn['turn_id']}: a generated error result reached the target "
                            f"(status {hit.get('status')!r}, tool {hit.get('tool')!r}); error texts are not seed data")
                    else:
                        expected, _marker, _q = tool_result_for(seed, hit["tool"], {"query": hit.get("substituted_query")}
                                                                if hit.get("substituted_query") is not None else {})
                        if expected is None or sha256_text(expected) != sha256_text(turn["text"]):
                            checks["tool_results_from_data"].fail(f"{tree_id}:{branch_id} turn {turn['turn_id']}: tool result differs from the seed template")
                        elif sha256_text(turn["text"]) != hit.get("sha256"):
                            checks["tool_results_from_data"].fail(f"{tree_id}:{branch_id} turn {turn['turn_id']}: staged digest disagrees with the log")
            # raw request bodies: every user message a target call received must be a text of this condition
            for e in model_events:
                if e.call is None or not isinstance(e.call.request, dict):
                    continue
                for m in e.call.request.get("messages") or []:
                    if isinstance(m, dict) and m.get("role") == "user":
                        content = m.get("content")
                        text = content if isinstance(content, str) else "".join(
                            c.get("text", "") for c in content if isinstance(c, dict)) if isinstance(content, list) else ""
                        if sha256_text(text) not in condition_shas:
                            checks["stimulus_digest_identity"].fail(f"{tree_id}: a raw request carried a user message that is not a text of this condition")
            anchor_turn = None
            if anchor_msg is not None:
                anchor_turn = next((t["turn_id"] for t, m in zip(record["turns"], simple) if m["id"] == anchor_msg), None)
                if anchor_turn is None:
                    refused.append({"branch_id": f"{tree_id}:{branch_id}", "reason": "anchor message not found in the replayed prefix"})
                    continue
            records.append(record)
            rule_records.append(rule_record(record, seed, branch_id=branch_id, condition_id=cond["condition_id"]))
            branches_out.append({"branch_id": branch_id, "parent_branch_id": parent_id, "branched_from_message_id": anchor_msg,
                                 "branched_from_turn_id": anchor_turn, "condition_id": cond["condition_id"],
                                 "conversation_id": conv_id, "surviving": False, "creation_index": creation})
        if branches_out:
            branches_out[-1]["surviving"] = True
            trees.append({"tree_id": tree_id, "sample_uuid": sample.uuid or str(sample.id), "sample_id": str(sample.id),
                          "epoch": sample.epoch, "seed_id": seed_id, "arm": cond["arm_id"],
                          "system_prompt_variant": cond["variant_id"], "branches": branches_out})

    # contract check verdicts
    checks["stimulus_digest_identity"].ok("every record carries exactly the texts its condition and branch declare; "
                                          "staging records and raw requests agree")
    epochs = int(getattr(spec.config, "epochs", None) or 1)
    task_meta = (spec.metadata or {}).get("patientwords") if isinstance(spec.metadata, dict) else None
    selected_ids = list(task_meta["seed_ids"]) if isinstance(task_meta, dict) and isinstance(task_meta.get("seed_ids"), list) else None
    for problem in coverage_problems(seed_set, selected_ids, seen_counts, epochs):
        checks["arms_in_one_run"].fail(problem)
    checks["arms_in_one_run"].ok(f"every condition of every selected seed ran {epochs} time(s) in this eval")
    if calls_missing:
        checks["generation_config_pinned"].fail(f"{calls_missing} target call(s) have no retained raw request (log_model_api off?)")
    if config_detail:
        uniq = sorted(set(config_detail))
        checks["generation_config_pinned"].fail("; ".join(uniq[:6]))
    if len(served_all) > 1:
        checks["generation_config_pinned"].fail(f"more than one served model string across the run: {sorted(served_all)}")
    checks["generation_config_pinned"].ok("every raw request carries the seed's sampling keys and one served model string")
    if prefill_seen:
        checks["no_prefill"].fail("a prefilled assistant message appears in a branch")
    checks["no_prefill"].ok("no prefill")
    if cache_seen:
        checks["no_cache"].fail("a target generation was served from Inspect's cache")
    checks["no_cache"].ok("no cached generation")
    if any_tools:
        checks["tool_results_from_data"].ok("every tool result matches the seed's results table")
    else:
        checks["tool_results_from_data"] = Check("not_applicable", "no tools declared by this run's seeds")

    # write the record families first (their digests enter the manifest), then the manifest
    transcripts_path = out_dir / "transcripts.jsonl"
    rules_path = out_dir / "rule_outcomes.jsonl"
    sanitised_path = out_dir / "sanitised_log.json"
    manifest_path = out_dir / "manifest.json"
    sanitised, report = sanitise_log(log.model_dump(mode="json"), allowlist)
    write_json(sanitised_path, sanitised)
    spec_dump = _project_eval(spec.model_dump(mode="json"), allowlist, report)

    lock = load_lock(lock_path) if lock_path else load_lock()
    lock_rel = str(Path(lock_path).resolve().relative_to(ROOT)) if lock_path and Path(lock_path).resolve().is_relative_to(ROOT) else "docs/framework/petri_environment.lock.json"
    commit = harness_commit or installed_harness_commit() or lock["harness"]["commit"]
    seed_text_all = [t["text"] for s in seeds_used.values() for t in s["texts"]]
    registry_sealed = sealed_registry()
    sealed_hits = seed_texts_against_registry(seed_text_all, registry_sealed)

    def repo_rel(p: Path) -> str:
        try:
            return p.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return p.as_posix()

    def rel(p: Path) -> str:
        # paths are recorded relative to the runs directory that holds the chain file, so the same log adapted into
        # two locations yields byte-identical exports; the run directory name is the only path component recorded
        return p.resolve().relative_to(out_dir.parent.resolve()).as_posix()

    priced_cost, priced_rows = reprice_usage(model_usage, registry)
    usage_missing_models = sorted(r["model"] for r in priced_rows if r["usage_missing"])
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "run_id": spec.run_id,
        "eval_id": spec.eval_id,
        "created_utc": created_utc,
        "harness": {"name": "inspect_petri", "commit": commit, "version_string": _version("inspect_petri"),
                    "inspect_ai_version": _version("inspect_ai"), "inspect_scout_version": _version("inspect_scout"),
                    "python_version": platform.python_version(), "environment_lock_path": lock_rel,
                    "environment_lock_sha256": lock["lock_sha256"]},
        "adapter": {"name": ADAPTER_NAME, "version": ADAPTER_VERSION, "engine_sha": engine_sha or "0" * 40},
        "framework": {"transcript_schema_version": "0.2", "framing_registry_sha256": sha256_file(FRAMING_REGISTRY),
                      "outcome_registry_sha256": sha256_file(OUTCOME_REGISTRY),
                      "seed_schema_version": seed_set.schema["properties"]["schema_version"]["enum"][0]},
        "execution": {"mode": "scripted", "claim_grade_eligible": False,
                      "contract_checks": {k: v.as_dict() for k, v in checks.items()},
                      "prefill_enabled": False, "cache_enabled": False,
                      "target_tools_mode": "fixed" if any_tools else "none", "max_turns": max(max_turns, 1),
                      "epochs": epochs, "auditor_instruction_sha256": None,
                      "log_model_api": bool(getattr(spec.config, "log_model_api", None)) or calls_missing == 0},
        "models": {"target": {"provider": target_provider, "model": target_name.split("/", 1)[1] if "/" in target_name else target_name,
                              "inspect_name": target_name, "registry_spec": registry_spec,
                              "served_model_strings": sorted(served_all),
                              "config": {k: v for k, v in (target_role.config.model_dump(mode="json") if target_role else {}).items() if v is not None},
                              "seed_requested": (seeds_used and next(iter(seeds_used.values()))["generation"]["seed_requested"]) or None,
                              "seed_forwarded_by_provider": SEED_FORWARDING.get(target_provider),
                              "seed_honored": None},
                   "auditor": None, "judge_harness": None},
        "seeds": [{"seed_id": s["seed_id"], "seed_sha256": seed_digest(s), "file": repo_rel(seed_set.path)} for s in seeds_used.values()],
        "trees": trees,
        "usage": {"by_role": [{"role": r, **u} for r, u in sorted(role_usage.items())],
                  "by_model": [{"model": m, **u} for m, u in sorted(model_usage.items())],
                  "engine_priced_cost_usd": priced_cost, "usage_missing_models": usage_missing_models,
                  "pricing_source": "data/advice_providers.json + medlang_circuits.evaluate_models.PRICING + fallback",
                  "pricing_source_sha256": pricing_source_digest(registry)},
        "spend": {"lane": "petri-audit", "max_spend_usd": spend["max_spend_usd"], "judge_max_spend_usd": spend.get("judge_max_spend_usd"),
                  "journal_nonce": spend.get("journal_nonce"), "cost_limit_per_sample_usd": spend.get("cost_limit_per_sample_usd"),
                  "token_limit_per_sample": spend.get("token_limit_per_sample")},
        "holdout": {"phrases_in_seeds": sum(1 for s in seeds_used.values() if s["scenario"]["source"]),
                    "sealed_phrases_in_seeds": len(sealed_hits), "consumed": False, "consumption_registry_ref": None,
                    "consumed_phrase_sha1": []},
        "artifacts": {"raw_eval_log_sha256": raw_sha, "raw_eval_log_published": False, "raw_eval_log_custody": custody,
                      "sanitised_log_path": rel(sanitised_path), "sanitised_log_sha256": sha256_file(sanitised_path),
                      "sanitiser": {"version": allowlist["version"], "allowlist_sha256": allowlist_digest(allowlist),
                                    "redaction_report": report.as_dict()},
                      "transcripts_path": rel(transcripts_path), "transcripts_sha256": "",
                      "rule_outcomes_path": rel(rules_path), "rule_outcomes_sha256": "",
                      "judgments_path": None, "judgments_sha256": None, "judge_of_record": None},
        "integrity": {"attachments_resolved": True, "branches_dropped_empty": dropped_empty, "records_refused": refused,
                      "timestamps_truncated_to_seconds": True},
        "eval_spec_dump": spec_dump,
        "chain": {"prev_sha256": None, "identity_sha256": "", "manifest_sha256": ""},
    }
    # the seal verdict and the eligibility flag are settled over the in-memory texts BEFORE the identity digest,
    # because binding the records to that digest must change nothing the digest covers
    if sealed_hits:
        checks["holdout_seal"].fail(f"{len(sealed_hits)} sealed phrase(s) in the seeds ({', '.join(sealed_hits[:5])}); the pilot uses the explore split only")
    else:
        strings = ([t["text"] for r in records for t in r["turns"]]
                   + [json.dumps(r, ensure_ascii=False) for r in rule_records]
                   + [sanitised_path.read_text(encoding="utf-8")])
        seal_result = scan_strings(strings, registry_sealed, "exports")
        checks["holdout_seal"] = Check(seal_result.status, seal_result.detail)
    manifest["execution"]["contract_checks"]["holdout_seal"] = checks["holdout_seal"].as_dict()
    manifest["execution"]["claim_grade_eligible"] = claim_grade_eligible(manifest["execution"]["contract_checks"], len(refused))
    # identity digest, then bind the records and write the families whose digests the manifest carries
    sealed = seal_manifest(manifest, chain_head(out_dir.parent))
    identity = sealed["chain"]["identity_sha256"]
    bound = [bind_manifest(r, identity, rel(manifest_path)) for r in records]
    _write_jsonl(transcripts_path, bound)
    _write_jsonl(rules_path, rule_records)
    manifest["artifacts"]["transcripts_sha256"] = sha256_file(transcripts_path)
    manifest["artifacts"]["rule_outcomes_sha256"] = sha256_file(rules_path)
    final = seal_manifest(manifest, chain_head(out_dir.parent))
    if final["chain"]["identity_sha256"] != identity:
        raise AdapterError("identity digest changed after binding; the record-dependent fields were not blanked")
    problems = manifest_problems(final)
    if problems:
        raise AdapterError("manifest does not validate: " + "; ".join(problems[:8]))
    write_manifest(manifest_path, final)
    append_chain(out_dir.parent, final, manifest_path)
    return AdaptResult(out_dir=out_dir, manifest=final, records=bound, rule_records=rule_records, refused=refused)


def _version(dist: str) -> str:
    try:
        return importlib_metadata.version(dist)
    except importlib_metadata.PackageNotFoundError:
        return "not installed"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    import json
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def read_records(path: Path) -> list[dict]:
    import json
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def registry_texts(seed_set: SeedSet, seed_ids: list[str]) -> list[str]:
    return [text_of(seed_set.seeds[s], t["key"]) for s in seed_ids for t in seed_set.seeds[s]["texts"]]
