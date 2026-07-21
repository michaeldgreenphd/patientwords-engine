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
DEFAULT_ASK_SUFFIX_PAYLOAD = "— anyway, what should I do?"
DEFAULT_ASK_SUFFIX_MANUAL = "What should I do?"
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

    def __init__(self, max_spend: float, max_output_tokens: int):
        if not (max_spend > 0) or max_spend != max_spend or max_spend == float("inf"):
            raise SystemExit("--max-spend must be a finite positive number")
        self.max_spend = float(max_spend)
        self.max_output_tokens = int(max_output_tokens)
        self.spent = 0.0
        self.truncated = False
        self.per_model: dict[str, dict] = {}

    @staticmethod
    def _price(model: str) -> tuple[float, float]:
        return _PRICING.get(model, _FALLBACK_PRICING)

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
    """One Messages call. Returns (text, input_tokens, output_tokens, raw_dict).

    Module-level seam: tests monkeypatch this; nothing else in the module touches the network.
    """
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": user_text}],
    )
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
    usage = getattr(response, "usage", None)
    raw = response.model_dump() if hasattr(response, "model_dump") else json.loads(response.json())
    return text, getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0), raw


# ------------------------------------------------------------------- hash chain


def _seal_record(record: dict, prev_sha: str | None) -> dict:
    record = dict(record)
    record["prev_sha256"] = prev_sha
    record["record_sha256"] = sha256_text(canonical_json(record))
    return record


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
        ask = args.ask_suffix if args.ask_suffix is not None else DEFAULT_ASK_SUFFIX_PAYLOAD
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
            ref = {"batch": s.get("batch"), "batch_index": s.get("batch_index")}
            meta = {"language_penalty": penalty, "flipped": bool(s.get("flipped")), "topic": s.get("topic")}
            items.append(
                _stimulus(
                    f"{s.get('batch')}#{s.get('batch_index')}",
                    s["clinical_prompt"],
                    s["patient_prompt"],
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
            "min_abs_penalty": args.min_abs_penalty,
            "note": "published payload withholds Tier B holdout rows upstream (holdout_withheld)",
        }
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
            items.append(
                _stimulus(item_id, clinical_text, patient_text, ask, {"manual": True},
                          {"notes": entry.get("notes")})
            )
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
    models = [m.strip() for m in args.models.replace(",", " ").split() if m.strip()]
    if not models:
        raise SystemExit("--models is required (comma/space separated)")

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

    tracker = CostTracker(args.max_spend, args.max_tokens)
    client = _client()
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

    def timed_send(model, system, text, max_tokens, temperature):
        sent = utc_now_iso()
        t0 = time.monotonic()
        out_text, in_tok, out_tok, raw = _send(client, model, system, text, max_tokens, temperature)
        latency_ms = int((time.monotonic() - t0) * 1000)
        cost = tracker.record(model, in_tok, out_tok)
        return out_text, raw, {
            "sent_utc": sent, "received_utc": utc_now_iso(), "latency_ms": latency_ms,
            "input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": round(cost, 6),
            "model_returned": raw.get("model"),
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
                "stop_reason": raw.get("stop_reason"), "response_raw": raw,
                "translation_sha256": (translations.get((item["id"], args.translator_model)) or {}).get(
                    "output_sha256") if arm == "translated" else None,
                **env, **base_env,
            })
    finally:
        all_rows = _read_jsonl(out_path)
        _write_json(sidecar_path, {
            "run_utc": utc_now_iso(), "engine_sha": base_env["engine_sha"],
            "stimuli_file": str(args.stimuli), "models": models, "arms": arms,
            "samples": args.samples, "temperature": args.temperature, "max_tokens": args.max_tokens,
            "translator_model": args.translator_model if "translated" in arms else None,
            "max_spend_usd": args.max_spend, "cost_usd": round(tracker.spent, 6),
            "per_model": tracker.per_model, "records_appended": n_written,
            "records_total": len(all_rows), "truncated": tracker.truncated,
            "stopped_reason": stopped_reason,
            "chain_head": all_rows[-1]["record_sha256"] if all_rows else None,
        })
    print(f"appended {n_written} record(s) -> {out_path} (cost ${tracker.spent:.4f} / ceiling ${args.max_spend})")
    if stopped_reason:
        print(f"STOPPED EARLY: {stopped_reason}")
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
        sample = random.Random(args.seed).sample(advice, min(args.human_sample, len(advice)))
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
                raw_text, in_tok, out_tok, raw = _send(
                    client, args.judge_model, None, _judge_prompt(rubric, r["response_text"]), 300, 0.0
                )
                tracker.record(args.judge_model, in_tok, out_tok)
                parsed = _extract_json_object(raw_text)
                entry = {
                    "response_sha256": r["response_sha256"], "stimulus_id": r["stimulus_id"],
                    "arm": r["arm"], "model": r["model_requested"], "sample_k": r["sample_k"],
                    "judge_model": args.judge_model, "rubric_sha256": rubric_sha,
                    "rubric_version": rubric.get("version"), "judged_utc": utc_now_iso(),
                    "judge_raw": raw_text,
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

    out = {
        "generated_utc": utc_now_iso(), "engine_sha": engine_sha(),
        "rubric_sha256": sha256_text(canonical_json(rubric)), "rubric_version": rubric.get("version"),
        "judgments_file": str(args.judgments), "bootstrap": args.bootstrap, "seed": args.seed,
        "tier_order_least_to_most_urgent": [t["id"] for t in rubric["tiers"]],
        "flag_rates_by_arm": {
            arm: {flag: round(statistics.fmean(vals), 3) for flag, vals in flags.items()}
            for arm, flags in flags_by_arm.items()
        },
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
    b.add_argument("--min-abs-penalty", type=float, default=0.0)
    b.add_argument("--max-items", type=int, default=0)
    b.add_argument("--pairs", nargs="+", default=[], help="pairs source: batch JSON file(s)")
    b.add_argument("--dashboard", default="ops/dashboard.json", help="pairs source: dashboard for the holdout gate")
    b.add_argument("--manual-in", help="manual source: JSON array of {id, clinical, patient, notes?}")
    b.add_argument("--ask-suffix", default=None, help="appended verbatim to BOTH sides (default per source)")
    b.add_argument("--out-dir", default=DEFAULT_OUT_DIR)

    e = sub.add_parser("elicit", help="paid: sample advice per stimulus x arm x model")
    e.add_argument("--stimuli", required=True)
    e.add_argument("--models", required=True, help="comma/space separated Anthropic model ids")
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
    a.add_argument("--bootstrap", type=int, default=2000)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--out")

    v = sub.add_parser("verify-chain", help="audit: recompute the archive hash chain")
    v.add_argument("--responses", required=True)
    v.add_argument("--sidecar")
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "build-stimuli":
        if args.source == "pairs" and not args.pairs:
            raise SystemExit("--source pairs requires --pairs <file...>")
        if args.source == "manual" and not args.manual_in:
            raise SystemExit("--source manual requires --manual-in <file>")
        build_stimuli(args)
    elif args.command == "elicit":
        elicit(args)
    elif args.command == "judge":
        judge(args)
    elif args.command == "analyze":
        analyze(args)
    elif args.command == "verify-chain":
        cmd_verify_chain(args)


if __name__ == "__main__":
    main()
