"""Frontier-model advice elicitation: paired clinical/patient vignettes, logged for audit.

The next-token study measures probabilities; this arm measures the *advice* deployed
assistants give for the same clinical situation phrased two ways. Three stimulus modes:

  1. ``build-stimuli --source payload`` - reuse situations the study has already
     validated (the published site payload: screened-in, measured, holdout-withheld).
  2. ``build-stimuli --source manual`` - owner-authored paired vignettes.
  3. ``elicit --arms clinical,patient,translated`` - the translated arm inserts an LLM
     patient->clinical translation step before elicitation, mirroring the study's
     translation-mitigation panel, to test whether translation recovers the advice.

Pipeline stages are strictly separated so only elicitation is irreproducible:

  build-stimuli -> elicit (paid; append-only JSONL, per-record hash chain) ->
  judge (paid; maps responses to rubric tiers; re-runnable forever from the archive) ->
  analyze (offline; paired stats) ; verify-chain audits the archive integrity.

Audit-not-reproducible design: every API call appends one record carrying the full
request, the full raw response, UTC send/receive times, latency, the exact model
version string the provider returned, the engine git sha, a sha256 of the response
text, and the sha256 of the previous record (a tamper-evident chain whose head is
committed in the run's .report.json sidecar, in the same commit as the data).

Conventions honored: no medical vocabulary in this file (stimuli, rubric tiers, and
judge wording are data); paid calls run under a hard --max-spend ceiling with a cost
sidecar; data/advice/ is append-only; Tier B holdout pairs are refused as stimuli
(and the --source pairs path hard-errors when the holdout set cannot be computed).
This arm EVALUATES model advice for measurement; it never dispenses advice.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import random
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = "data/advice"
DEFAULT_PAYLOAD = "../patientwords/data/simulated_scenarios.json"
DEFAULT_RUBRIC = "data/advice_rubric.json"
# Appended verbatim to BOTH sides of every pair, so the minimal-pair property of the
# stimuli is preserved: the two arms still differ only in the swapped span.
# no em-dashes or commas in the suffix: they read as LLM-styled text rather
# than typed consumer speech (owner preference, 2026-07-22)
DEFAULT_ASK_SUFFIX_PAYLOAD = "... anyway what should I do?"
DEFAULT_ASK_SUFFIX_MANUAL = "What should I do?"
# --complete-with-target keeps "anyway" so the completed set differs from the
# truncated registered set ONLY in the target word being present vs cut off.
DEFAULT_ASK_SUFFIX_COMPLETED = "Anyway what should I do?"
ARMS = ("clinical", "patient", "translated")
DEFAULT_MAX_TOKENS = 1024
DEFAULT_SAMPLES = 3
EST_INPUT_TOKENS = 400  # worst-case per-call input sizing for the pre-call budget check

try:  # pricing lives in the package; keep a fallback so this script imports standalone
    from medlang_circuits.evaluate_models import PRICING as _PRICING
except Exception:  # pragma: no cover - exercised only outside the dev install
    _PRICING = {}
_FALLBACK_PRICING = (10.0, 50.0)

_TRANSLATE_SYSTEM_FALLBACK = (
    "Translate this colloquial patient statement into standard clinical terminology. "
    "Preserve the sentence structure and length as closely as possible - change only the "
    "colloquial terms, keep everything else (including any trailing incomplete phrasing) intact. "
    "Respond with only the translated sentence."
)


def _translate_system() -> str:
    try:
        from medlang_circuits.llm_client import _TRANSLATE_SYSTEM

        return _TRANSLATE_SYSTEM
    except Exception:  # pragma: no cover
        return _TRANSLATE_SYSTEM_FALLBACK


# ------------------------------------------------------------ provider registry

DEFAULT_PROVIDERS = "data/advice_providers.json"
# Anthropic works with no registry file so single-vendor runs stay zero-config.
_BUILTIN_PROVIDERS = {
    "anthropic": {"api": "anthropic", "consumer_product": "claude.ai free tier"},
}


def _load_providers(path: str | Path) -> dict:
    """Registry of consumer products -> API endpoints/models. Data, not code.

    The registry pins, per provider: the OpenAI-compatible base_url, the env var
    naming its key (Actions secret), the consumer_default model (the study's
    average-consumer proxy - the free/default tier of the product), pricing for
    the ceiling math, and a consumer_proxy_note documenting how faithful the API
    proxy is to the real product. Providers whose consumer product has no public
    API (api: "manual_ui") are measured only via import-manual-responses.
    """
    p = Path(path)
    registry = dict(_BUILTIN_PROVIDERS)
    if p.is_file():
        loaded = _load_json(p)
        for name, cfg in loaded.items():
            if isinstance(cfg, dict) and not name.startswith("_"):
                registry[name] = {**registry.get(name, {}), **cfg}
    return registry


def _resolve_spec(spec: str, registry: dict) -> dict:
    """'provider:model' | 'provider' (consumer default) | bare model (anthropic)."""
    if ":" in spec:
        provider, model = spec.split(":", 1)
    elif spec in registry:
        provider, model = spec, ""
    else:
        provider, model = "anthropic", spec
    cfg = registry.get(provider)
    if cfg is None:
        raise SystemExit(f"unknown provider {provider!r}; registry knows: {sorted(registry)} "
                         f"(copy data/advice_providers.example.json to {DEFAULT_PROVIDERS} and review)")
    if cfg.get("api") == "manual_ui":
        raise SystemExit(f"provider {provider!r} has no public API for its consumer product - "
                         "capture responses in the real product UI and use import-manual-responses")
    model = model or cfg.get("consumer_default", "")
    if not model:
        raise SystemExit(f"provider {provider!r}: no model given and no consumer_default in the registry")
    return {"spec": f"{provider}:{model}", "provider": provider, "model": model, "cfg": cfg}


# --------------------------------------------------------------------------- utils


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def engine_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _load_json(path: str | Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str | Path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


def _read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    p = Path(path)
    if not p.is_file():
        return rows
    with open(p, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise SystemExit(f"{path}:{line_no}: corrupt JSONL line ({exc}); refusing to continue") from exc
    return rows


# ---------------------------------------------------------------- cost accounting


class CostTracker:
    """Hard spend ceiling; sized to this pipeline's max_tokens rather than the eval defaults."""

    def __init__(self, max_spend: float, max_output_tokens: int, custom_pricing: dict | None = None):
        if not (max_spend > 0) or max_spend != max_spend or max_spend == float("inf"):
            raise SystemExit("--max-spend must be a finite positive number")
        self.max_spend = float(max_spend)
        self.max_output_tokens = int(max_output_tokens)
        self.custom_pricing = dict(custom_pricing or {})  # spec/model -> (in, out) USD per Mtok
        self.spent = 0.0
        self.truncated = False
        self.per_model: dict[str, dict] = {}

    def _price(self, key: str) -> tuple[float, float]:
        for candidate in (key, key.split(":", 1)[-1]):
            if candidate in self.custom_pricing:
                return tuple(self.custom_pricing[candidate])
            if candidate in _PRICING:
                return _PRICING[candidate]
        return _FALLBACK_PRICING

    def can_afford(self, model: str) -> bool:
        in_p, out_p = self._price(model)
        worst = EST_INPUT_TOKENS * in_p / 1e6 + self.max_output_tokens * out_p / 1e6
        if self.spent + worst > self.max_spend:
            self.truncated = True
            return False
        return True

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        in_p, out_p = self._price(model)
        cost = input_tokens * in_p / 1e6 + output_tokens * out_p / 1e6
        self.spent += cost
        bucket = self.per_model.setdefault(
            model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
        )
        bucket["calls"] += 1
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["cost"] += cost
        return cost


# ------------------------------------------------------------------ API call seam


def _client():
    """Lazy Anthropic client; module-level seam so tests monkeypatch _send instead."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("anthropic package unavailable - pip install -e '.[llm]'") from exc
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY unset - paid stages run only in CI with the Actions secret")
    return anthropic.Anthropic(api_key=key)


def _send(client, model: str, system: str | None, user_text: str, max_tokens: int, temperature: float):
    """One Messages call. Returns (text, input_tokens, output_tokens, raw_dict, headers).

    Module-level seam: tests monkeypatch this; nothing else in the module touches the
    network. Headers ride along for build forensics (request id, api version) - the
    SDK's with_raw_response wrapper exposes them; older stubs returning a 4-tuple are
    tolerated by every caller (headers default to {}).
    """
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": user_text}],
    )
    if system:
        kwargs["system"] = system
    headers: dict = {}
    raw_api = getattr(client.messages, "with_raw_response", None)
    if raw_api is not None:
        wrapped = raw_api.create(**kwargs)
        headers = {str(k).lower(): str(v) for k, v in dict(getattr(wrapped, "headers", {}) or {}).items()}
        response = wrapped.parse()
    else:  # pragma: no cover - older SDKs without the wrapper
        response = client.messages.create(**kwargs)
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
    usage = getattr(response, "usage", None)
    raw = response.model_dump() if hasattr(response, "model_dump") else json.loads(response.json())
    return text, getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0), raw, headers


_LAST_CALL_AT: dict[str, float] = {}


def _pace(provider: str, cfg: dict) -> None:
    """Space calls to one provider by the registry's min_interval_seconds.

    Free consumer tiers enforce tight request budgets, and retries alone make
    it WORSE — every retry is itself a request against the quota (run 1b died
    on sustained Gemini free-tier 429s after 16 successes, 2026-07-22).
    Pacing is data: the registry entry decides, per provider."""
    interval = cfg.get("min_interval_seconds")
    if not interval:
        return
    last = _LAST_CALL_AT.get(provider)
    now = time.monotonic()
    if last is not None and now - last < float(interval):
        time.sleep(float(interval) - (now - last))
    _LAST_CALL_AT[provider] = time.monotonic()


RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504, 522, 529})
COMPAT_RETRIES = 5
COMPAT_BACKOFF_SECONDS = (2, 4, 8, 16, 32)


def _send_anthropic_retrying(client, model, system, user_text, max_tokens, temperature):
    """_send plus transient-status retries, mirroring _send_compat's policy.

    The Anthropic path originally had none: pilot 2b died mid-run on a single
    Cloudflare 522 from api.anthropic.com during a translation call after the
    SDK's own quick retries gave up (run 29913634215, 2026-07-22). Honors the
    error body's retry_after when present (1-120 s cap)."""
    for attempt in range(COMPAT_RETRIES + 1):
        try:
            return _send(client, model, system, user_text, max_tokens, temperature)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status not in RETRYABLE_STATUSES or attempt >= COMPAT_RETRIES:
                raise
            wait = COMPAT_BACKOFF_SECONDS[min(attempt, len(COMPAT_BACKOFF_SECONDS) - 1)]
            body = getattr(exc, "body", None)
            if isinstance(body, dict) and body.get("retry_after") is not None:
                try:
                    wait = max(1.0, min(float(body["retry_after"]), 120.0))
                except (TypeError, ValueError):
                    pass
            print(f"anthropic {model}: transient {status}; retry {attempt + 1}/{COMPAT_RETRIES} in {wait}s")
            time.sleep(wait)


def _finish_reason(raw) -> str | None:
    """Why generation stopped, across API shapes: Anthropic surfaces stop_reason at the
    top level; OpenAI-compatible providers (all compat-path vendors incl. OpenRouter)
    put finish_reason on the first choice. Without this, a max-token truncation on the
    compat path is unattributable in the archive's convenience field (the full raw
    response is archived either way, so older records remain recoverable)."""
    if not isinstance(raw, dict):
        return None
    if raw.get("stop_reason") is not None:
        return raw.get("stop_reason")
    choices = raw.get("choices") or [{}]
    return (choices[0] or {}).get("finish_reason")


def _send_compat(cfg: dict, model: str, system: str | None, user_text: str,
                 max_tokens: int, temperature: float):
    """One OpenAI-compatible chat call (OpenAI, Gemini, xAI, DeepSeek, Moonshot,
    OpenRouter, ... all expose this shape). Same return tuple as _send; same
    monkeypatch seam for tests. The provider's key comes from the env var named
    in the registry (an Actions secret in CI - never a local file).

    Transient statuses (429/500/502/503/504 - free consumer tiers throw these
    routinely; run 1 died on a single Gemini 503, 2026-07-22) retry with
    exponential backoff, honoring Retry-After when the provider sends one.
    Anything else, or exhaustion, raises: the elicit loop archives what landed
    and a re-fire resumes past it."""
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("requests package unavailable - pip install requests") from exc
    key_env = cfg.get("key_env", "")
    key = os.environ.get(key_env, "")
    if not key:
        raise SystemExit(f"{key_env or 'provider key env'} unset - add it as an Actions secret "
                         "and pass it through the workflow env block")
    base_url = cfg["base_url"].rstrip("/")
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user_text}
    ]
    for attempt in range(COMPAT_RETRIES + 1):
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            timeout=180,
        )
        if resp.status_code in RETRYABLE_STATUSES and attempt < COMPAT_RETRIES:
            try:
                wait = float(resp.headers.get("Retry-After", ""))
            except (TypeError, ValueError):
                wait = COMPAT_BACKOFF_SECONDS[min(attempt, len(COMPAT_BACKOFF_SECONDS) - 1)]
            wait = min(max(wait, 1.0), 120.0)
            print(f"transient {resp.status_code} from {base_url} ({model}); "
                  f"retry {attempt + 1}/{COMPAT_RETRIES} in {wait:.0f}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        raw = resp.json()
        text = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        usage = raw.get("usage") or {}
        headers = {str(k).lower(): str(v) for k, v in dict(resp.headers or {}).items()}
        return text.strip(), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), raw, headers


def _build_info(raw, headers) -> dict:
    """Forensic fields for a call: request id and api-version from response headers,
    plus any body-level build fingerprint (system_fingerprint class) lifted to a
    first-class field. Provider absence -> nulls; the full raw body is archived
    regardless, so nothing is lost when a vendor renames these."""
    headers = headers or {}
    def pick(*names):
        for n in names:
            v = headers.get(n)
            if v:
                return v
        return None
    raw = raw if isinstance(raw, dict) else {}
    return {
        "request_id": pick("request-id", "x-request-id", "openrouter-request-id", "x-amzn-requestid"),
        "api_version": pick("anthropic-version", "openai-version", "api-version"),
        "build_fingerprint": raw.get("system_fingerprint") or raw.get("build_fingerprint"),
    }


# ------------------------------------------------------------------- hash chain


def _seal_record(record: dict, prev_sha: str | None) -> dict:
    record = dict(record)
    record["prev_sha256"] = prev_sha
    record["record_sha256"] = sha256_text(canonical_json(record))
    return record


def _cumulative_from_records(rows: list[dict]) -> tuple[float, dict]:
    """Ledger-facing totals recomputed from the archive itself.

    Sidecars overwrite per stimuli-stem, so a per-run cost_usd silently drops
    earlier runs' spend from the daily guard once a resume overwrites it. The
    records are the durable source: every paid record carries its own cost_usd,
    so the archive-cumulative sum is always the true total for the stem."""
    total = 0.0
    per_model: dict[str, dict] = {}
    for r in rows:
        if "cost_usd" not in r:
            continue  # advice_skipped and other zero-call bookkeeping records
        cost = float(r.get("cost_usd") or 0.0)
        bucket = per_model.setdefault(
            r.get("model_requested") or "?",
            {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        )
        bucket["calls"] += 1
        bucket["input_tokens"] += int(r.get("input_tokens") or 0)
        bucket["output_tokens"] += int(r.get("output_tokens") or 0)
        bucket["cost"] += cost
        total += cost
    return round(total, 6), per_model


def verify_chain(rows: list[dict]) -> tuple[bool, str]:
    prev = None
    for i, row in enumerate(rows):
        stored = row.get("record_sha256")
        body = {k: v for k, v in row.items() if k != "record_sha256"}
        if row.get("prev_sha256") != prev:
            return False, f"record {i}: prev_sha256 broken (expected {prev!r})"
        if sha256_text(canonical_json(body)) != stored:
            return False, f"record {i}: record_sha256 mismatch (content altered)"
        prev = stored
    return True, f"chain intact over {len(rows)} records (head {prev})"


# ------------------------------------------------------------------ build-stimuli


def _load_tierb_split():
    path = Path(__file__).resolve().parent / "tierb_split.py"
    spec = importlib.util.spec_from_file_location("tierb_split", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stimulus(item_id, clinical_text, patient_text, ask_suffix, source_ref=None, meta=None):
    def assemble(body: str) -> str:
        return f"{body.rstrip()} {ask_suffix}".strip()

    clinical_msg = assemble(clinical_text)
    patient_msg = assemble(patient_text)
    return {
        "id": item_id,
        "source_ref": source_ref or {},
        "clinical_body": clinical_text,
        "patient_body": patient_text,
        "clinical_message": clinical_msg,
        "patient_message": patient_msg,
        "clinical_sha256": sha256_text(clinical_msg),
        "patient_sha256": sha256_text(patient_msg),
        "meta": meta or {},
    }


def build_stimuli(args) -> Path:
    items = []
    if args.source == "payload":
        complete = bool(getattr(args, "complete_with_target", False))
        overrides = json.loads(getattr(args, "complete_override", None) or "{}")
        if overrides and not complete:
            raise SystemExit("--complete-override requires --complete-with-target")
        ask = args.ask_suffix if args.ask_suffix is not None else (
            DEFAULT_ASK_SUFFIX_COMPLETED if complete else DEFAULT_ASK_SUFFIX_PAYLOAD)
        payload = _load_json(args.payload)
        scenarios = payload.get("scenarios") or []
        picked = 0
        for s in scenarios:
            if (s.get("screening") or {}).get("status") == "screened_out":
                continue
            if not s.get("clinical_prompt") or not s.get("patient_prompt"):
                continue
            if args.only_flips and not s.get("flipped"):
                continue
            penalty = s.get("language_penalty")
            if args.min_abs_penalty and (penalty is None or abs(penalty) < args.min_abs_penalty):
                continue
            # hedges: the next-token top HELD but its probability collapsed -
            # the complementary stress condition to --only-flips (does the
            # advice shift even when the top prediction did not?)
            if getattr(args, "only_hedges", False) and (
                    s.get("flipped") or penalty is None or penalty >= 0):
                continue
            ref = {"batch": s.get("batch"), "batch_index": s.get("batch_index")}
            meta = {"language_penalty": penalty, "flipped": bool(s.get("flipped")), "topic": s.get("topic")}
            item_id = f"{s.get('batch')}#{s.get('batch_index')}"
            c_body, p_body = s["clinical_prompt"], s["patient_prompt"]
            if complete:
                # Finish the measured probe sentence with the pair's own
                # intended word (payload data, e.g. the full word behind a
                # wordpiece target) so the stimulus is a complete thought.
                # Same word on both sides: the single-swap discipline holds.
                # Owner-approved overrides (data passed at build time) cover
                # pairs whose intended word is not a complete noun.
                word = str(overrides.get(item_id) or s.get("intended_target")
                           or s.get("target_token") or "").strip()
                if not word:
                    print(f"skip {item_id}: nothing to complete with "
                          "(no intended_target/target_token in the payload)")
                    continue
                c_body = f"{c_body.rstrip()} {word}."
                p_body = f"{p_body.rstrip()} {word}."
                meta["completed_with"] = word
                if item_id in overrides:
                    meta["completion_override"] = True
            items.append(
                _stimulus(
                    item_id,
                    c_body,
                    p_body,
                    ask,
                    ref,
                    meta,
                )
            )
            picked += 1
            if args.max_items and picked >= args.max_items:
                break
        source_desc = {
            "kind": "payload",
            "path": str(args.payload),
            "only_flips": bool(args.only_flips),
            "only_hedges": bool(getattr(args, "only_hedges", False)),
            "min_abs_penalty": args.min_abs_penalty,
            "complete_with_target": complete,
            "complete_overrides": overrides,
            "note": "published payload withholds Tier B holdout rows upstream (holdout_withheld)",
        }
        if complete:
            for it in items:
                print("  completed:", it["patient_message"])
    elif args.source == "pairs":
        ask = args.ask_suffix if args.ask_suffix is not None else DEFAULT_ASK_SUFFIX_PAYLOAD
        tierb = _load_tierb_split()
        start_stamp = tierb.tierb_start_stamp(args.dashboard)
        excluded = 0
        for pairs_path in args.pairs:
            batch_name = Path(pairs_path).stem
            if tierb._BATCH_RE.fullmatch(batch_name) and start_stamp is None:
                raise SystemExit(
                    f"{pairs_path}: looks like a Tier B batch but the holdout set cannot be computed "
                    f"(tierb.start_utc is null in {args.dashboard}). On a stale checkout this silently "
                    "yields an EMPTY holdout set - point --dashboard at the ops-truth branch copy."
                )
            is_tierb = tierb.is_tierb_batch(batch_name, start_stamp)
            for idx, pair in enumerate(_load_json(pairs_path), start=1):
                top, bottom = pair.get("top_prompt"), pair.get("bottom_prompt")
                if not top or not bottom:
                    continue
                if is_tierb and tierb.is_holdout(top):
                    excluded += 1
                    continue
                items.append(
                    _stimulus(f"{batch_name}#{idx}", top, bottom, ask, {"batch": batch_name, "batch_index": idx})
                )
        source_desc = {
            "kind": "pairs",
            "paths": [str(p) for p in args.pairs],
            "holdout_excluded": excluded,
            "tierb_start_stamp": start_stamp,
        }
        if excluded:
            print(f"holdout guard: excluded {excluded} sealed Tier B pair(s)")
    else:  # manual
        ask = args.ask_suffix if args.ask_suffix is not None else DEFAULT_ASK_SUFFIX_MANUAL
        raw = _load_json(args.manual_in)
        if not isinstance(raw, list) or not raw:
            raise SystemExit(f"{args.manual_in}: expected a non-empty JSON array")
        seen_ids: set[str] = set()
        for i, entry in enumerate(raw):
            item_id = str(entry.get("id") or f"manual_{i + 1:03d}")
            clinical_text = (entry.get("clinical") or "").strip()
            patient_text = (entry.get("patient") or "").strip()
            if not clinical_text or not patient_text:
                raise SystemExit(f"{args.manual_in}: item {item_id}: both 'clinical' and 'patient' are required")
            if clinical_text == patient_text:
                raise SystemExit(f"{args.manual_in}: item {item_id}: clinical and patient texts are identical")
            if item_id in seen_ids:
                raise SystemExit(f"{args.manual_in}: duplicate id {item_id}")
            seen_ids.add(item_id)
            item = _stimulus(item_id, clinical_text, patient_text, ask, {"manual": True},
                             {"notes": entry.get("notes")})
            # A2: optional clinician-adjudicated reference tier (data authored
            # by owner + domain reviewer; analyze scores accuracy/under/over
            # against it). Passed through verbatim; tier validity is checked
            # at analyze time against the rubric actually in force.
            ref = entry.get("reference")
            if ref is not None:
                if not isinstance(ref, dict) or not ref.get("tier"):
                    raise SystemExit(f"{args.manual_in}: item {item_id}: 'reference' must be an "
                                     "object with at least a 'tier'")
                item["reference"] = ref
            # B2/B3/B4 schema: optional situation grouping + variant tag so
            # manual vignettes can carry misattribution / paraphrase /
            # messiness designs; analyze-side comparisons come in phase 2.
            for key in ("situation_id", "variant"):
                if entry.get(key) is not None:
                    if not isinstance(entry[key], str) or not entry[key].strip():
                        raise SystemExit(f"{args.manual_in}: item {item_id}: '{key}' must be a "
                                         "non-empty string when present")
                    item[key] = entry[key].strip()
            items.append(item)
        source_desc = {"kind": "manual", "path": str(args.manual_in)}

    if not items:
        raise SystemExit("no stimuli selected - loosen the filters or check the source file")

    stamp = utc_stamp()
    out_path = Path(args.out_dir) / f"stimuli_{stamp}.json"
    _write_json(
        out_path,
        {
            "created_utc": utc_now_iso(),
            "engine_sha": engine_sha(),
            "source": source_desc,
            "ask_suffix": ask,
            "n_items": len(items),
            "items": items,
        },
    )
    print(f"wrote {len(items)} paired stimuli -> {out_path}")
    print("review the assembled messages by eye before eliciting; the pair texts are the experiment.")
    return out_path


# ------------------------------------------------------------------------ elicit


def _done_keys(rows: list[dict]) -> set[tuple]:
    done = set()
    for r in rows:
        if r.get("record_type") == "advice":
            done.add(("advice", r["stimulus_id"], r["arm"], r["model_requested"], r["sample_k"]))
        elif r.get("record_type") == "translation":
            done.add(("translation", r["stimulus_id"], r["model_requested"]))
    return done


def elicit(args) -> Path:
    stimuli_doc = _load_json(args.stimuli)
    items = stimuli_doc["items"][args.offset: (args.offset + args.limit) if args.limit else None]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for arm in arms:
        if arm not in ARMS:
            raise SystemExit(f"unknown arm {arm!r}; expected any of {ARMS}")
    registry = _load_providers(args.providers)
    specs = [m.strip() for m in args.models.replace(",", " ").split() if m.strip()]
    if not specs:
        raise SystemExit("--models is required: 'provider' (consumer default), 'provider:model', "
                         "or a bare Anthropic model id")
    resolved = {}
    for s in specs:
        r = _resolve_spec(s, registry)
        resolved[r["spec"]] = r
    models = list(resolved)  # canonical provider:model spec strings
    custom_pricing = {}
    for r in resolved.values():
        pricing = (r["cfg"].get("pricing") or {}).get(r["model"]) or r["cfg"].get("default_pricing")
        if pricing:
            custom_pricing[r["spec"]] = (float(pricing[0]), float(pricing[1]))

    stem = Path(args.stimuli).stem
    out_path = Path(args.out_dir) / f"responses_{stem}.jsonl"
    sidecar_path = Path(args.out_dir) / f"responses_{stem}.report.json"
    existing = _read_jsonl(out_path)
    ok, msg = verify_chain(existing)
    if not ok:
        raise SystemExit(f"{out_path}: existing archive fails chain verification ({msg}); refusing to append")
    done = _done_keys(existing)
    prev_sha = existing[-1]["record_sha256"] if existing else None
    translations = {
        (r["stimulus_id"], r["model_requested"]): r for r in existing if r.get("record_type") == "translation"
    }

    planned = []
    for item in items:
        if "translated" in arms and (item["id"], args.translator_model) not in translations:
            planned.append(("translation", item, None, None))
        for arm in arms:
            for model in models:
                for k in range(1, args.samples + 1):
                    if ("advice", item["id"], arm, model, k) not in done:
                        planned.append(("advice", item, arm, (model, k)))
    print(f"plan: {len(planned)} call(s) over {len(items)} stimuli x arms {arms} x models {models} "
          f"x K={args.samples} (resume skipped {len(done)} already-archived)")
    if args.dry_run:
        return out_path

    tracker = CostTracker(args.max_spend, args.max_tokens, custom_pricing)
    client_box: list = []  # Anthropic client, created only when an anthropic-api call happens

    def anthropic_client():
        if not client_box:
            client_box.append(_client())
        return client_box[0]

    ask_suffix = stimuli_doc.get("ask_suffix", "")
    base_env = {"engine_sha": engine_sha(), "stimuli_sha256": sha256_text(canonical_json(stimuli_doc))}
    n_written = 0
    stopped_reason = None

    def append(record: dict) -> None:
        nonlocal prev_sha, n_written
        sealed = _seal_record(record, prev_sha)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sealed, ensure_ascii=False) + "\n")
        prev_sha = sealed["record_sha256"]
        n_written += 1

    def timed_send(spec_key, system, text, max_tokens, temperature):
        r = resolved.get(spec_key)  # None for the bare-model translator: anthropic path
        if r is not None:
            _pace(r["provider"], r["cfg"])
        sent = utc_now_iso()
        t0 = time.monotonic()
        if r is None or r["cfg"].get("api", "anthropic") == "anthropic":
            endpoint = "anthropic"
            model = r["model"] if r else spec_key
            res = _send_anthropic_retrying(
                anthropic_client(), model, system, text, max_tokens, temperature)
        else:
            endpoint = r["cfg"].get("base_url", "")
            res = _send_compat(r["cfg"], r["model"], system, text,
                               max_tokens, temperature)
        out_text, in_tok, out_tok, raw = res[:4]
        headers = res[4] if len(res) > 4 else {}
        latency_ms = int((time.monotonic() - t0) * 1000)
        cost = tracker.record(spec_key, in_tok, out_tok)
        return out_text, raw, {
            "sent_utc": sent, "received_utc": utc_now_iso(), "latency_ms": latency_ms,
            "input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": round(cost, 6),
            "model_returned": raw.get("model"),
            "provider": (r or {}).get("provider", "anthropic"), "endpoint": endpoint,
            **_build_info(raw, headers),
        }

    try:
        for kind, item, arm, extra in planned:
            if kind == "translation":
                model = args.translator_model
                if not tracker.can_afford(model):
                    stopped_reason = f"max_spend ceiling (${args.max_spend}) before translation of {item['id']}"
                    break
                text, raw, env = timed_send(
                    model, _translate_system(), item["patient_body"], args.max_tokens, args.translation_temperature
                )
                record = {
                    "record_type": "translation", "stimulus_id": item["id"],
                    "model_requested": model, "arm": None, "sample_k": None,
                    "request": {"system": "translate", "input_body": item["patient_body"],
                                "temperature": args.translation_temperature, "max_tokens": args.max_tokens},
                    "output_text": text, "output_sha256": sha256_text(text),
                    "response_raw": raw, **env, **base_env,
                }
                append(record)
                translations[(item["id"], model)] = record
                continue

            model, k = extra
            if arm == "clinical":
                message = item["clinical_message"]
            elif arm == "patient":
                message = item["patient_message"]
            else:
                tr = translations.get((item["id"], args.translator_model))
                if tr is None or not tr.get("output_text"):
                    append({
                        "record_type": "advice_skipped", "stimulus_id": item["id"], "arm": arm,
                        "model_requested": model, "sample_k": k,
                        "reason": "translation unavailable", **base_env,
                    })
                    continue
                message = f"{tr['output_text'].rstrip()} {ask_suffix}".strip()
            if not tracker.can_afford(model):
                stopped_reason = f"max_spend ceiling (${args.max_spend}) at {item['id']}/{arm}/{model}/k{k}"
                break
            text, raw, env = timed_send(model, None, message, args.max_tokens, args.temperature)
            append({
                "record_type": "advice", "stimulus_id": item["id"], "arm": arm,
                "model_requested": model, "sample_k": k,
                "request": {"system": None, "message": message, "temperature": args.temperature,
                            "max_tokens": args.max_tokens},
                "response_text": text, "response_sha256": sha256_text(text),
                "stop_reason": _finish_reason(raw), "response_raw": raw,
                "translation_sha256": (translations.get((item["id"], args.translator_model)) or {}).get(
                    "output_sha256") if arm == "translated" else None,
                **env, **base_env,
            })
    finally:
        all_rows = _read_jsonl(out_path)
        cum_cost, cum_per_model = _cumulative_from_records(all_rows)
        _write_json(sidecar_path, {
            "run_utc": utc_now_iso(), "engine_sha": base_env["engine_sha"],
            "stimuli_file": str(args.stimuli), "models": models, "arms": arms,
            "providers_registry": str(args.providers),
            "providers": {spec: r["provider"] for spec, r in resolved.items()},
            "samples": args.samples, "temperature": args.temperature, "max_tokens": args.max_tokens,
            "translator_model": args.translator_model if "translated" in arms else None,
            "max_spend_usd": args.max_spend,
            "cost_usd": cum_cost, "cost_basis": "cumulative_from_records",
            "run_cost_usd": round(tracker.spent, 6),
            "per_model": cum_per_model, "run_per_model": tracker.per_model,
            "records_appended": n_written,
            "records_total": len(all_rows), "truncated": tracker.truncated,
            "stopped_reason": stopped_reason,
            "chain_head": all_rows[-1]["record_sha256"] if all_rows else None,
        })
    print(f"appended {n_written} record(s) -> {out_path} (cost ${tracker.spent:.4f} / ceiling ${args.max_spend})")
    if stopped_reason:
        print(f"STOPPED EARLY: {stopped_reason}")
    return out_path


# ------------------------------------------------------- import-manual-responses


def import_manual(args) -> Path:
    """Append UI-captured responses (products with no consumer API) to the audit chain.

    For Copilot / Meta AI-class products the average consumer's product has no
    public API; responses are captured by hand in the real product UI and imported
    here. Records enter the same hash chain with record_type "advice" (so judge
    and analyze treat them uniformly) plus a capture block that marks the
    provenance manual_ui - never disguised as API output (response_raw is null).
    """
    stimuli_doc = _load_json(args.stimuli)
    items = {i["id"]: i for i in stimuli_doc["items"]}
    entries = _load_json(args.manual_in)
    if not isinstance(entries, list) or not entries:
        raise SystemExit(f"{args.manual_in}: expected a non-empty JSON array")

    stem = Path(args.stimuli).stem
    out_path = Path(args.out_dir) / f"responses_{stem}.jsonl"
    sidecar_path = Path(args.out_dir) / f"responses_{stem}.report.json"
    existing = _read_jsonl(out_path)
    ok, msg = verify_chain(existing)
    if not ok:
        raise SystemExit(f"{out_path}: existing archive fails chain verification ({msg}); refusing to append")
    prev_sha = existing[-1]["record_sha256"] if existing else None
    next_k: dict[tuple, int] = {}
    for r in existing:
        if r.get("record_type") == "advice":
            key = (r["stimulus_id"], r["arm"], r["model_requested"])
            next_k[key] = max(next_k.get(key, 0), r["sample_k"] or 0)

    base_env = {"engine_sha": engine_sha(), "stimuli_sha256": sha256_text(canonical_json(stimuli_doc))}
    n = 0
    with open(out_path, "a", encoding="utf-8") as f:
        for i, e in enumerate(entries):
            where = f"{args.manual_in}: entry {i + 1}"
            sid, arm = e.get("stimulus_id"), e.get("arm")
            if sid not in items:
                raise SystemExit(f"{where}: unknown stimulus_id {sid!r} (not in {args.stimuli})")
            if arm not in ("clinical", "patient"):
                raise SystemExit(f"{where}: arm must be 'clinical' or 'patient' (the translated arm "
                                 "requires the pipeline's logged translation step)")
            product = (e.get("product") or "").strip()
            text = (e.get("response_text") or "").strip()
            captured = e.get("captured_utc")
            if not product or not text or not captured:
                raise SystemExit(f"{where}: product, response_text, and captured_utc are required")
            spec = f"{product}:consumer_ui"
            key = (sid, arm, spec)
            next_k[key] = next_k.get(key, 0) + 1
            record = _seal_record({
                "record_type": "advice", "stimulus_id": sid, "arm": arm,
                "model_requested": spec, "sample_k": next_k[key],
                "request": {"system": None, "message": items[sid][f"{arm}_message"],
                            "temperature": None, "max_tokens": None},
                "response_text": text, "response_sha256": sha256_text(text),
                "stop_reason": None, "response_raw": None, "translation_sha256": None,
                "capture": {"method": "manual_ui", "product": product,
                            "model_claimed": e.get("model_claimed"), "captured_utc": captured,
                            "note": e.get("note")},
                "sent_utc": captured, "received_utc": captured, "latency_ms": None,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "model_returned": e.get("model_claimed"), "provider": product,
                "endpoint": "manual_ui", **base_env,
            }, prev_sha)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            prev_sha = record["record_sha256"]
            n += 1

    all_rows = _read_jsonl(out_path)
    sidecar = _load_json(sidecar_path) if sidecar_path.is_file() else {"cost_usd": 0.0}
    sidecar.update({
        "chain_head": all_rows[-1]["record_sha256"], "records_total": len(all_rows),
        "manual_imports": (sidecar.get("manual_imports") or []) + [
            {"imported_utc": utc_now_iso(), "source": str(args.manual_in), "records": n}
        ],
    })
    _write_json(sidecar_path, sidecar)
    print(f"imported {n} manual UI record(s) -> {out_path} (provenance capture.method=manual_ui, cost $0)")
    return out_path


# ------------------------------------------------------------------------- judge


def _extract_json_object(text: str):
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start: i + 1])
                except ValueError:
                    start = None
    return None


def _judge_prompt(rubric: dict, response_text: str) -> str:
    tiers = "\n".join(f"- {t['id']}: {t['definition']}" for t in rubric["tiers"])
    flags = "\n".join(f"- {f['id']}: {f['definition']}" for f in rubric.get("flags", []))
    return rubric["judge_instructions"].format(tiers=tiers, flags=flags, response=response_text)


def judge(args) -> Path:
    rubric = _load_json(args.rubric)
    rubric_sha = sha256_text(canonical_json(rubric))
    tier_ids = [t["id"] for t in rubric["tiers"]]
    rows = _read_jsonl(args.responses)
    ok, msg = verify_chain(rows)
    if not ok:
        raise SystemExit(f"{args.responses}: {msg} - refusing to judge a tampered archive")
    advice = [r for r in rows if r.get("record_type") == "advice"]

    out_path = Path(args.out) if args.out else Path(args.responses).with_name(
        Path(args.responses).stem.replace("responses_", "judgments_") + ".jsonl")
    existing = _read_jsonl(out_path)
    done = {(j["response_sha256"], j["rubric_sha256"], j["judge_model"]) for j in existing}
    todo = [r for r in advice if (r["response_sha256"], rubric_sha, args.judge_model) not in done]

    if args.human_sample:
        # A4: stratify by arm — the judge cannot be fully blinded to register
        # (responses echo the user's words), so judge-vs-human agreement must
        # be reportable PER ARM at comparable n. Rows stay blinded (text only).
        rng = random.Random(args.seed)
        by_arm: dict[str, list[dict]] = {}
        for r in advice:
            by_arm.setdefault(r.get("arm") or "?", []).append(r)
        arms_present = sorted(by_arm)
        want = min(args.human_sample, len(advice))
        per_arm = max(1, want // max(1, len(arms_present)))
        sample = []
        for arm in arms_present:
            pool = by_arm[arm]
            sample.extend(rng.sample(pool, min(per_arm, len(pool))))
        # top up to the requested n from the remainder, still seeded
        if len(sample) < want:
            chosen = {id(r) for r in sample}
            rest = [r for r in advice if id(r) not in chosen]
            sample.extend(rng.sample(rest, min(want - len(sample), len(rest))))
        rng.shuffle(sample)  # no arm-blocked ordering hints for the coder
        human_path = out_path.with_name(out_path.stem + "_human_sample.csv")
        with open(human_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["response_sha256", "response_text", "tier", "flags", "coder", "notes"])
            for r in sample:
                w.writerow([r["response_sha256"], r["response_text"], "", "", "", ""])
        print(f"blinded human-coding sample ({len(sample)} rows) -> {human_path}")

    print(f"judging {len(todo)} response(s) ({len(done)} already judged under this rubric/judge)")
    if args.dry_run or not todo:
        return out_path

    tracker = CostTracker(args.max_spend, 300)
    client = _client()
    n = 0
    try:
        with open(out_path, "a", encoding="utf-8") as f:
            for r in todo:
                if not tracker.can_afford(args.judge_model):
                    print(f"STOPPED EARLY: judge max_spend ceiling (${args.max_spend})")
                    break
                # Blinding: the judge sees the response text only - never the prompt or arm.
                res = _send_anthropic_retrying(
                    client, args.judge_model, None, _judge_prompt(rubric, r["response_text"]), 300, 0.0
                )
                raw_text, in_tok, out_tok, raw = res[:4]
                judge_headers = res[4] if len(res) > 4 else {}
                tracker.record(args.judge_model, in_tok, out_tok)
                parsed = _extract_json_object(raw_text)
                entry = {
                    "response_sha256": r["response_sha256"], "stimulus_id": r["stimulus_id"],
                    "arm": r["arm"], "model": r["model_requested"], "sample_k": r["sample_k"],
                    "judge_model": args.judge_model, "rubric_sha256": rubric_sha,
                    "rubric_version": rubric.get("version"), "judged_utc": utc_now_iso(),
                    "judge_raw": raw_text,
                    "judge_request_id": _build_info(raw, judge_headers).get("request_id"),
                }
                if parsed and parsed.get("tier") in tier_ids:
                    entry["tier"] = parsed["tier"]
                    entry["flags"] = {k: bool(v) for k, v in (parsed.get("flags") or {}).items()}
                else:
                    entry["tier"] = None
                    entry["judge_error"] = "unparseable or unknown tier"
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                n += 1
    finally:
        sidecar = out_path.with_suffix(".report.json")
        _write_json(sidecar, {
            "run_utc": utc_now_iso(), "responses_file": str(args.responses), "rubric_sha256": rubric_sha,
            "judge_model": args.judge_model, "judged": n, "cost_usd": round(tracker.spent, 6),
            "max_spend_usd": args.max_spend, "truncated": tracker.truncated,
        })
    print(f"judged {n} -> {out_path} (cost ${tracker.spent:.4f})")
    return out_path


# ----------------------------------------------------------------------- analyze


def _modal_tier(tiers: list[str], rank: dict[str, int]) -> str | None:
    present = [t for t in tiers if t]
    if not present:
        return None
    counts: dict[str, int] = {}
    for t in present:
        counts[t] = counts.get(t, 0) + 1
    best = max(counts.values())
    # deterministic tie-break: among modal tiers, take the most urgent (highest rank)
    return max((t for t, c in counts.items() if c == best), key=lambda t: rank.get(t, -1))


def _pairwise_disagreement(labels: list) -> float | None:
    """P(two randomly chosen labels differ); None with fewer than 2 labels.
    The 'lottery' primitive (A3): applied to models' modal tiers it is the
    consumer lottery, applied to one model's K samples the self-lottery."""
    n = len(labels)
    if n < 2:
        return None
    counts: dict = {}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1
    same = sum(k * (k - 1) for k in counts.values())
    return 1.0 - same / (n * (n - 1))


def _text_covariates(text: str) -> tuple[int, float]:
    """(word count, Flesch-Kincaid grade). Arithmetic only — no vocabulary:
    sentences = runs of .!? ; syllables = vowel groups per word (min 1)."""
    words = [w.strip(".,;:!?()[]\"'") for w in text.split()]
    words = [w for w in words if w]
    n_words = len(words)
    if not n_words:
        return 0, 0.0
    n_sent = max(1, len([s for s in re.split(r"[.!?]+", text) if s.strip()]))
    n_syl = sum(max(1, len(re.findall(r"[aeiouyAEIOUY]+", w))) for w in words)
    grade = 0.39 * (n_words / n_sent) + 11.8 * (n_syl / n_words) - 15.59
    return n_words, round(grade, 2)


def analyze(args) -> Path:
    rubric = _load_json(args.rubric)
    rank = {t["id"]: i for i, t in enumerate(rubric["tiers"])}
    judgments = _read_jsonl(args.judgments)
    cells: dict[tuple, list[str]] = {}
    flags_by_arm: dict[str, dict[str, list[bool]]] = {}
    for j in judgments:
        if j.get("tier") is None:
            continue
        cells.setdefault((j["stimulus_id"], j["model"], j["arm"]), []).append(j["tier"])
        for flag, value in (j.get("flags") or {}).items():
            flags_by_arm.setdefault(j["arm"], {}).setdefault(flag, []).append(bool(value))

    per_cell = {}
    for key, tiers in cells.items():
        modal = _modal_tier(tiers, rank)
        per_cell[key] = {
            "modal": modal, "n": len(tiers),
            "agreement": round(tiers.count(modal) / len(tiers), 3),
            "unanimous": len(set(tiers)) == 1,
        }

    stim_models = sorted({(s, m) for (s, m, _a) in per_cell})
    paired, recovery = [], []
    for stim, model in stim_models:
        c = per_cell.get((stim, model, "clinical"))
        p = per_cell.get((stim, model, "patient"))
        t = per_cell.get((stim, model, "translated"))
        if c and p:
            diff = rank[p["modal"]] - rank[c["modal"]]
            cls = "downgrade" if diff < 0 else ("upgrade" if diff > 0 else "same")
            paired.append({"stimulus_id": stim, "model": model, "clinical": c["modal"],
                           "patient": p["modal"], "rank_diff": diff, "class": cls})
            if t:
                cr, pr, tr = rank[c["modal"]], rank[p["modal"]], rank[t["modal"]]
                if pr == cr:
                    outcome = "no_change_needed"
                elif tr == cr:
                    outcome = "recovered"
                elif abs(cr - tr) < abs(cr - pr) and (cr - tr) * (cr - pr) > 0:
                    outcome = "partial"
                elif (cr - tr) * (cr - pr) < 0:
                    outcome = "overshoot"
                else:
                    outcome = "unrecovered"
                recovery.append({"stimulus_id": stim, "model": model, "translated": t["modal"],
                                 "outcome": outcome})

    def _boot(values_by_stim: dict[str, list[float]], fn, n_boot: int, seed: int):
        stims = sorted(values_by_stim)
        if not stims:
            return None
        rng = random.Random(seed)
        stats = []
        for _ in range(n_boot):
            sample = [v for s in (rng.choice(stims) for _ in stims) for v in values_by_stim[s]]
            stats.append(fn(sample))
        stats.sort()
        return {"mean": round(fn([v for vs in values_by_stim.values() for v in vs]), 4),
                "ci95": [round(stats[int(0.025 * n_boot)], 4), round(stats[int(0.975 * n_boot) - 1], 4)],
                "n_stimuli": len(stims)}

    by_model: dict[str, dict] = {}
    for model in sorted({m for (_s, m) in stim_models}):
        rows = [p for p in paired if p["model"] == model]
        diffs_by_stim: dict[str, list[float]] = {}
        down_by_stim: dict[str, list[float]] = {}
        for p in rows:
            diffs_by_stim.setdefault(p["stimulus_id"], []).append(p["rank_diff"])
            down_by_stim.setdefault(p["stimulus_id"], []).append(1.0 if p["class"] == "downgrade" else 0.0)
        by_model[model] = {
            "n_paired": len(rows),
            "downgrades": sum(1 for p in rows if p["class"] == "downgrade"),
            "upgrades": sum(1 for p in rows if p["class"] == "upgrade"),
            "mean_rank_diff": _boot(diffs_by_stim, statistics.fmean, args.bootstrap, args.seed),
            "downgrade_rate": _boot(down_by_stim, statistics.fmean, args.bootstrap, args.seed + 1),
            "recovery": {o: sum(1 for r in recovery if r["model"] == model and r["outcome"] == o)
                         for o in ("recovered", "partial", "unrecovered", "overshoot", "no_change_needed")},
            "within_prompt": {
                arm: {
                    "mean_agreement": round(statistics.fmean(
                        [c["agreement"] for k, c in per_cell.items() if k[1] == model and k[2] == arm]), 3),
                    "unanimous_share": round(statistics.fmean(
                        [1.0 if c["unanimous"] else 0.0
                         for k, c in per_cell.items() if k[1] == model and k[2] == arm]), 3),
                } for arm in ARMS if any(k[1] == model and k[2] == arm for k in per_cell)
            },
        }

    def _mean3(vals):
        return round(statistics.fmean(vals), 3) if vals else None

    # A2: reference-tier scoring — clinician ground truth from the stimuli
    # file (data authored by owner + domain reviewer, never Python). Turns
    # difference into quality: accuracy / under- / over-triage per model x
    # arm, and the thesis endpoint under_triage_patient_minus_clinical.
    reference_scoring = None
    if getattr(args, "stimuli", None):
        refs = {}
        for it in _load_json(args.stimuli).get("items", []):
            tier = (it.get("reference") or {}).get("tier")
            if tier is not None:
                if tier not in rank:
                    raise SystemExit(f"{args.stimuli}: item {it.get('id')}: reference tier "
                                     f"{tier!r} is not a tier id of the rubric in force")
                refs[it["id"]] = rank[tier]
        if refs:
            per_ma: dict[tuple, dict] = {}
            for (stim, model, arm), cell in per_cell.items():
                if stim not in refs or cell["modal"] is None:
                    continue
                d = rank[cell["modal"]] - refs[stim]
                rec = per_ma.setdefault((model, arm), {"n": 0, "correct": 0, "under": 0, "over": 0})
                rec["n"] += 1
                rec["correct"] += int(d == 0)
                rec["under"] += int(d < 0)
                rec["over"] += int(d > 0)
            thesis = {}
            for model in sorted({m for (_s, m) in stim_models}):
                diffs: dict[str, list[float]] = {}
                for stim in refs:
                    c = per_cell.get((stim, model, "clinical"))
                    p = per_cell.get((stim, model, "patient"))
                    if c and p and c["modal"] and p["modal"]:
                        u_c = 1.0 if rank[c["modal"]] < refs[stim] else 0.0
                        u_p = 1.0 if rank[p["modal"]] < refs[stim] else 0.0
                        diffs[stim] = [u_p - u_c]
                if diffs:
                    thesis[model] = _boot(diffs, statistics.fmean, args.bootstrap, args.seed + 2)
            reference_scoring = {
                "n_referenced_stimuli": len(refs),
                "by_model_arm": {
                    f"{m}|{a}": {"n": v["n"], "accuracy": round(v["correct"] / v["n"], 3),
                                 "under_triage_rate": round(v["under"] / v["n"], 3),
                                 "over_triage_rate": round(v["over"] / v["n"], 3)}
                    for (m, a), v in sorted(per_ma.items())},
                "under_triage_patient_minus_clinical": thesis,
            }

    # A3: dispersion — the "wide-ranging" statistics, computed from the same
    # judged cells (no new spend).
    modal_by_stim_arm: dict[tuple, list[str]] = {}
    ranks_all_samples: dict[tuple, list[int]] = {}
    for (stim, model, arm), tiers in cells.items():
        modal = per_cell[(stim, model, arm)]["modal"]
        if modal is not None:
            modal_by_stim_arm.setdefault((stim, arm), []).append(modal)
        ranks_all_samples.setdefault((stim, arm), []).extend(rank[t] for t in tiers)
    consumer_by_arm = {}
    range_models_by_arm = {}
    range_samples_by_arm = {}
    for arm in sorted({a for (_s, a) in modal_by_stim_arm}):
        ds = [_pairwise_disagreement(v) for (s, a), v in modal_by_stim_arm.items() if a == arm]
        ds = [d for d in ds if d is not None]
        consumer_by_arm[arm] = _mean3(ds)
        rm = [max(rank[t] for t in v) - min(rank[t] for t in v)
              for (s, a), v in modal_by_stim_arm.items() if a == arm and len(v) >= 2]
        range_models_by_arm[arm] = {"mean": _mean3(rm), "max": max(rm) if rm else None}
        rs = [max(v) - min(v)
              for (s, a), v in ranks_all_samples.items() if a == arm and len(v) >= 2]
        range_samples_by_arm[arm] = {"mean": _mean3(rs), "max": max(rs) if rs else None}
    self_lottery = {}
    for model in sorted({m for (_s, m, _a) in cells}):
        ds = [_pairwise_disagreement(tiers) for (s, m, a), tiers in cells.items() if m == model]
        ds = [d for d in ds if d is not None]
        self_lottery[model] = _mean3(ds)
    dispersion = {
        "_": ("consumer lottery = P(two randomly chosen models' modal tiers disagree) per "
              "stimulus x arm; self lottery = P(two of one model's K samples disagree); "
              "agreement = 1 - consumer lottery (models-as-raters proportion, deliberately "
              "not a kappa family); ranges are max-min tier rank"),
        "consumer_lottery_by_arm": consumer_by_arm,
        "inter_model_agreement_by_arm": {
            a: (None if v is None else round(1 - v, 3)) for a, v in consumer_by_arm.items()},
        "self_lottery_by_model": self_lottery,
        "tier_range_across_models_by_arm": range_models_by_arm,
        "tier_range_across_samples_by_arm": range_samples_by_arm,
    }

    # A3: length + readability covariates from the raw responses (length
    # confounds every quality measure; readability-by-register is an equity
    # finding in itself).
    response_covariates = None
    if getattr(args, "responses", None):
        cov_cells: dict[tuple, list[tuple]] = {}
        for r in _read_jsonl(args.responses):
            if r.get("record_type") != "advice" or not r.get("response_text"):
                continue
            cov_cells.setdefault((r.get("model_requested"), r.get("arm")),
                                 []).append(_text_covariates(r["response_text"]))
        response_covariates = {
            f"{m}|{a}": {"n": len(v), "mean_words": _mean3([x[0] for x in v]),
                         "mean_fk_grade": _mean3([x[1] for x in v])}
            for (m, a), v in sorted(cov_cells.items())}

    out = {
        "generated_utc": utc_now_iso(), "engine_sha": engine_sha(),
        "rubric_sha256": sha256_text(canonical_json(rubric)), "rubric_version": rubric.get("version"),
        "judgments_file": str(args.judgments), "bootstrap": args.bootstrap, "seed": args.seed,
        "tier_order_least_to_most_urgent": [t["id"] for t in rubric["tiers"]],
        "flag_rates_by_arm": {
            arm: {flag: round(statistics.fmean(vals), 3) for flag, vals in flags.items()}
            for arm, flags in flags_by_arm.items()
        },
        "reference_scoring": reference_scoring,
        "dispersion": dispersion,
        "response_covariates": response_covariates,
        "per_model": by_model, "paired": paired, "recovery": recovery,
    }
    out_path = Path(args.out) if args.out else Path(args.judgments).with_name(
        Path(args.judgments).stem.replace("judgments_", "analysis_") + ".json")
    _write_json(out_path, out)
    for model, block in by_model.items():
        mrd = block["mean_rank_diff"] or {}
        print(f"{model}: {block['n_paired']} paired | downgrades {block['downgrades']} "
              f"| mean rank diff {mrd.get('mean')} CI95 {mrd.get('ci95')} | recovery {block['recovery']}")
    print(f"analysis -> {out_path}")
    return out_path


# ------------------------------------------------------------------ verify-chain


def recover_archive(args) -> Path:
    """Land an archive snapshot from a CI artifact after a killed run (append-only).

    A job-timeout kill leaves the elicited records only in the run's uploaded
    artifact: the archive JSONL is intact (each append is a complete line) but
    the sidecar was never rewritten and the commit step could not push. This
    lands that snapshot so a resume fire skips the already-paid records.

    Guards: the restored file must be a byte-prefix extension of the committed
    archive with an intact hash chain. Only a trailing partially-written line
    may be dropped (the kill can interrupt the final append; it never completed,
    so it is not a record). Anything else — a divergent prefix, a corrupt
    interior line, a broken chain — is reported and refused, never repaired.
    The sidecar is rebuilt from the records themselves (cumulative cost basis,
    which is what the ledger folds)."""
    stem = Path(args.stimuli).stem
    committed_path = Path(args.out_dir) / f"responses_{stem}.jsonl"
    sidecar_path = Path(args.out_dir) / f"responses_{stem}.report.json"
    restored_path = Path(args.restored_dir) / f"responses_{stem}.jsonl"
    if not restored_path.is_file():
        raise SystemExit(f"{restored_path}: no restored archive found")

    raw = restored_path.read_bytes()
    lines = raw.split(b"\n")
    dropped_partial = False
    if lines and lines[-1] == b"":
        lines = lines[:-1]  # normal trailing newline
    elif lines:
        try:
            json.loads(lines[-1].decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            dropped_partial = True
            lines = lines[:-1]
    rows = []
    for line_no, ln in enumerate(lines, 1):
        text = ln.decode("utf-8").strip()
        if not text:
            continue
        try:
            rows.append(json.loads(text))
        except ValueError as exc:
            raise SystemExit(
                f"{restored_path}:{line_no}: corrupt interior JSONL line ({exc}); "
                "refusing to recover — report, never repair"
            ) from exc
    if not rows:
        raise SystemExit(f"{restored_path}: no complete records to recover")
    ok, msg = verify_chain(rows)
    if not ok:
        raise SystemExit(f"{restored_path}: restored archive fails chain verification ({msg}); refusing")

    content = b"".join(ln + b"\n" for ln in lines if ln.strip())
    committed_rows = _read_jsonl(committed_path)
    if committed_rows:
        committed_bytes = committed_path.read_bytes()
        if not content.startswith(committed_bytes):
            raise SystemExit(
                f"{restored_path}: not a byte-prefix extension of the committed archive "
                f"({committed_path}); refusing to recover — report, never repair"
            )
    appended = len(rows) - len(committed_rows)
    if appended < 0:
        raise SystemExit(
            f"{restored_path}: fewer records ({len(rows)}) than the committed archive "
            f"({len(committed_rows)}); refusing"
        )

    committed_path.parent.mkdir(parents=True, exist_ok=True)
    with open(committed_path, "wb") as f:
        f.write(content)
    cum_cost, cum_per_model = _cumulative_from_records(rows)
    _write_json(sidecar_path, {
        "run_utc": utc_now_iso(), "engine_sha": engine_sha(),
        "stimuli_file": str(args.stimuli),
        "recovered_from_run_id": args.source_run_id or None,
        "cost_usd": cum_cost, "cost_basis": "cumulative_from_records",
        "per_model": cum_per_model,
        "records_appended": appended, "records_total": len(rows),
        "dropped_partial_final_line": dropped_partial,
        "chain_head": rows[-1]["record_sha256"],
    })
    print(f"recovered {appended} record(s) -> {committed_path} "
          f"({len(rows)} total, cumulative cost ${cum_cost:.4f}"
          f"{', dropped 1 partial final line' if dropped_partial else ''})")
    return committed_path


def cmd_verify_chain(args) -> None:
    rows = _read_jsonl(args.responses)
    ok, msg = verify_chain(rows)
    print(msg)
    if args.sidecar:
        sidecar = _load_json(args.sidecar)
        head = rows[-1]["record_sha256"] if rows else None
        if sidecar.get("chain_head") != head:
            print(f"sidecar chain_head mismatch: sidecar={sidecar.get('chain_head')} archive={head}")
            ok = False
    if not ok:
        raise SystemExit(2)


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build-stimuli", help="assemble paired advice vignettes")
    b.add_argument("--source", choices=("payload", "pairs", "manual"), required=True)
    b.add_argument("--payload", default=DEFAULT_PAYLOAD)
    b.add_argument("--only-flips", action="store_true", help="payload source: measured flips only")
    b.add_argument("--only-hedges", action="store_true",
                   help="payload source: non-flips with a negative penalty only "
                        "(top held, probability collapsed); combine with --min-abs-penalty")
    b.add_argument("--min-abs-penalty", type=float, default=0.0)
    b.add_argument("--complete-with-target", action="store_true",
                   help="payload source: finish each probe sentence with the pair's intended "
                        "word so stimuli are complete thoughts instead of trailing off "
                        "(same word both sides; default suffix drops the ellipsis)")
    b.add_argument("--complete-override", default=None,
                   help="JSON object mapping item ids to owner-approved completion words "
                        "(overrides intended_target for pairs whose word is not a complete noun)")
    b.add_argument("--max-items", type=int, default=0)
    b.add_argument("--pairs", nargs="+", default=[], help="pairs source: batch JSON file(s)")
    b.add_argument("--dashboard", default="ops/dashboard.json", help="pairs source: dashboard for the holdout gate")
    b.add_argument("--manual-in", help="manual source: JSON array of {id, clinical, patient, notes?}")
    b.add_argument("--ask-suffix", default=None, help="appended verbatim to BOTH sides (default per source)")
    b.add_argument("--out-dir", default=DEFAULT_OUT_DIR)

    e = sub.add_parser("elicit", help="paid: sample advice per stimulus x arm x model")
    e.add_argument("--stimuli", required=True)
    e.add_argument("--models", required=True,
                   help="comma/space separated: 'provider' (registry consumer default = the "
                        "average-consumer proxy), 'provider:model', or a bare Anthropic model id")
    e.add_argument("--providers", default=DEFAULT_PROVIDERS,
                   help="provider registry JSON (copy data/advice_providers.example.json and review)")
    e.add_argument("--arms", default="clinical,patient")
    e.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    e.add_argument("--temperature", type=float, default=1.0)
    e.add_argument("--translation-temperature", type=float, default=0.0)
    e.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    e.add_argument("--translator-model", default="claude-haiku-4-5")
    e.add_argument("--max-spend", type=float, required=True)
    e.add_argument("--offset", type=int, default=0)
    e.add_argument("--limit", type=int, default=0)
    e.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    e.add_argument("--dry-run", action="store_true")

    j = sub.add_parser("judge", help="paid: map archived responses to rubric tiers (re-runnable)")
    j.add_argument("--responses", required=True)
    j.add_argument("--rubric", default=DEFAULT_RUBRIC)
    j.add_argument("--judge-model", default="claude-haiku-4-5")
    j.add_argument("--max-spend", type=float, required=True)
    j.add_argument("--out")
    j.add_argument("--human-sample", type=int, default=0, help="also export a blinded human-coding CSV sample")
    j.add_argument("--seed", type=int, default=7)
    j.add_argument("--dry-run", action="store_true")

    a = sub.add_parser("analyze", help="offline: paired tier stats, recovery, variance decomposition")
    a.add_argument("--judgments", required=True)
    a.add_argument("--rubric", default=DEFAULT_RUBRIC)
    a.add_argument("--stimuli", default=None,
                   help="stimuli file whose items may carry clinician reference tiers "
                        "(A2: enables accuracy / under- / over-triage scoring)")
    a.add_argument("--responses", default=None,
                   help="responses archive for length + readability covariates (A3)")
    a.add_argument("--bootstrap", type=int, default=2000)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--out")

    m = sub.add_parser("import-manual-responses",
                       help="append UI-captured responses (products with no consumer API) to the chain")
    m.add_argument("--stimuli", required=True)
    m.add_argument("--in", dest="manual_in", required=True,
                   help="JSON array: {stimulus_id, arm, product, model_claimed?, captured_utc, "
                        "response_text, note?}")
    m.add_argument("--out-dir", default=DEFAULT_OUT_DIR)

    v = sub.add_parser("verify-chain", help="audit: recompute the archive hash chain")
    v.add_argument("--responses", required=True)
    v.add_argument("--sidecar")

    rec = sub.add_parser("recover-archive",
                         help="land a CI-artifact archive snapshot after a killed run "
                              "(append-only byte-prefix extension, chain-verified)")
    rec.add_argument("--restored-dir", required=True,
                     help="directory holding the downloaded artifact's data/advice files")
    rec.add_argument("--stimuli", required=True)
    rec.add_argument("--source-run-id", default="",
                     help="CI run id the artifact came from (provenance, recorded in the sidecar)")
    rec.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "build-stimuli":
        if args.source == "pairs" and not args.pairs:
            raise SystemExit("--source pairs requires --pairs <file...>")
        if args.source == "manual" and not args.manual_in:
            raise SystemExit("--source manual requires --manual-in <file>")
        if args.complete_with_target and args.source != "payload":
            raise SystemExit("--complete-with-target only applies to --source payload")
        build_stimuli(args)
    elif args.command == "elicit":
        elicit(args)
    elif args.command == "import-manual-responses":
        import_manual(args)
    elif args.command == "judge":
        judge(args)
    elif args.command == "analyze":
        analyze(args)
    elif args.command == "verify-chain":
        cmd_verify_chain(args)
    elif args.command == "recover-archive":
        recover_archive(args)


if __name__ == "__main__":
    main()
