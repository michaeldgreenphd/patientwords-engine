"""The lane's job summary: what a run of the petri-audit lane produced, read
from the files it wrote and rendered for the GitHub Actions step summary
(design memo section 14: the first `dry_run` replaces the pilot's structural
assumptions with measurements). Python 3.11-safe; imports nothing from the
harness.

Every quantity here is one of three kinds, and the rendering labels each:

- **measured structural quantities** (call counts, trees, branches, records,
  byte sizes, redaction counts, refusals, check statuses): read from the
  manifest, the exports and the raw log on disk, valid under any target;
- **provider usage status** per model: `provider-measured` when the model is
  priced and every call returned a usage block, `mock/non-metered` when the
  model is a zero-price mock or placeholder (the locked inspect-ai's mockllm
  returns no usage block, and its token counts are not provider-metered
  tokens), `unavailable` when a priced model returned no usage for a call;
- **cost**: the sidecar's `cost_usd` and `cost_basis`, exactly 0 for a
  zero-price target.

Nothing here decides anything: a section that cannot be computed reports why
(`unavailable`) rather than a default, and the command never fails the job
over its own output.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from .framework import OUTCOME_REGISTRY, load_json, sha256_file
from .manifest import CHAIN_FILE, artifact_problems, manifest_problems, verify_chain
from .spend import resolve_price, usage_is_missing
from .transcripts import record_problems

ATTACHMENT_MARK = "attachment://"
PUBLISHED_FILES = ("manifest.json", "transcripts.jsonl", "rule_outcomes.jsonl", "sanitised_log.json")
USAGE_PROVIDER_MEASURED = "provider-measured"
USAGE_MOCK = "mock/non-metered"
USAGE_UNAVAILABLE = "unavailable"


def _guard(fn, *args, **kwargs) -> Any:
    """Run one section; an exception becomes an explicit `unavailable` entry
    (never a silent gap, never a failed summary step)."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - the summary reports every failure by name
        return {"unavailable": f"{type(exc).__name__}: {exc}"}


def usage_status(row: dict, price_source: str, zero_priced: bool) -> str:
    """The provenance label of one usage row (see the module docstring)."""
    if zero_priced:
        return USAGE_MOCK
    if usage_is_missing(row):
        return USAGE_UNAVAILABLE
    return USAGE_PROVIDER_MEASURED


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _structure(manifest: dict, run_dir: Path, eval_status: str | None) -> dict:
    trees = manifest.get("trees") or []
    branches = [b for t in trees for b in t.get("branches") or []]
    child = [b for b in branches if b.get("parent_branch_id") is not None]
    refused = (manifest.get("integrity") or {}).get("records_refused") or []
    by_role = {r["role"]: r for r in (manifest.get("usage") or {}).get("by_role") or []}
    target = by_role.get("target") or {}
    records = _read_jsonl(run_dir / "transcripts.jsonl") if (run_dir / "transcripts.jsonl").is_file() else []
    problems = {r["conversation_id"]: record_problems(r) for r in records}
    bad = {k: v for k, v in problems.items() if v}
    return {
        "eval_status": eval_status,
        "seeds": [{"seed_id": s["seed_id"], "claim_grade_eligible": s.get("claim_grade_eligible")} for s in manifest.get("seeds") or []],
        "trees": len(trees),
        "branches": len(branches),
        "conditions": len({b.get("condition_id") for b in branches}),
        "shared_prefix_branches": {"anchored": sum(1 for b in child if b.get("branched_from_turn_id") is not None),
                                   "without_resolved_anchor": sum(1 for b in child if b.get("branched_from_turn_id") is None)},
        "survivors_exported": sum(1 for t in trees if t.get("survivor_exported")),
        "records": {"count": len(records), "with_problems": len(bad),
                    "problems": [f"{k[:12]}: {'; '.join(v[:3])}" for k, v in list(bad.items())[:5]]},
        "refused": {"count": len(refused), "reasons": [f"{r.get('branch_id')}: {r.get('reason')}" for r in refused]},
        "target_calls": target.get("calls"),
        "target_calls_without_usage": target.get("calls_without_usage"),
        "max_turns": (manifest.get("execution") or {}).get("max_turns"),
        "max_tool_rounds_per_turn": (manifest.get("execution") or {}).get("max_tool_rounds_per_turn"),
        "epochs": (manifest.get("execution") or {}).get("epochs"),
    }


def _usage(manifest: dict) -> list[dict]:
    rows = []
    for r in (manifest.get("usage") or {}).get("by_model") or []:
        price = resolve_price(r["model"])
        zero = price.input_per_mtok == 0 and price.output_per_mtok == 0
        rows.append({"model": r["model"], "calls": r.get("calls"), "calls_without_usage": r.get("calls_without_usage"),
                     "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
                     "status": usage_status(r, price.source, zero), "price_source": price.source})
    return rows


def _raw_eval(manifest: dict, raw_eval_dir: Path | None) -> dict:
    recorded = (manifest.get("artifacts") or {}).get("raw_eval_log_sha256")
    files = sorted(raw_eval_dir.glob("*.eval")) if raw_eval_dir and raw_eval_dir.is_dir() else []
    out = {"recorded_sha256": recorded, "files": []}
    for f in files:
        digest = sha256_file(f)
        out["files"].append({"name": f.name, "bytes": f.stat().st_size, "sha256": digest,
                             "matches_manifest": (digest == recorded) if recorded else None})
    if not files:
        out["note"] = "no raw .eval found" + (f" under {raw_eval_dir}" if raw_eval_dir else " (no directory given)")
    return out


def _published(run_dir: Path) -> dict:
    sizes = {name: (run_dir / name).stat().st_size for name in PUBLISHED_FILES if (run_dir / name).is_file()}
    sidecars = {p.name: p.stat().st_size for p in sorted(run_dir.glob("*.report.json"))}
    refs = 0
    for name in sizes:
        refs += (run_dir / name).read_text(encoding="utf-8").count(ATTACHMENT_MARK)
    return {"files": sizes, "cost_sidecars": sidecars, "total_bytes": sum(sizes.values()) + sum(sidecars.values()),
            "attachment_references": refs}


def _integrity(manifest: dict, run_dir: Path) -> dict:
    chain_ok, chain_msg = verify_chain(run_dir.parent) if (run_dir.parent / CHAIN_FILE).is_file() else (None, "no chain file")
    return {"manifest_problems": manifest_problems(manifest), "artifact_problems": artifact_problems(manifest, run_dir.parent),
            "chain": {"ok": chain_ok, "message": chain_msg},
            "attachments_resolved": (manifest.get("integrity") or {}).get("attachments_resolved")}


def _sidecar(run_dir: Path) -> dict | None:
    path = run_dir / f"{run_dir.name}.report.json"
    if not path.is_file():
        return None
    r = load_json(path)
    return {"path": path.name, "cost_usd": r.get("cost_usd"), "cost_basis": r.get("cost_basis"),
            "billing_channel": r.get("billing_channel"), "usage_missing_models": r.get("usage_missing_models"),
            "max_spend_usd": r.get("max_spend_usd"), "spend_report_reason": r.get("spend_report_reason")}


def _judge_sidecar(run_dir: Path) -> dict | None:
    path = run_dir / f"{run_dir.name}.judge.report.json"
    if not path.is_file():
        return None
    r = load_json(path)
    return {"path": path.name, "cost_usd": r.get("cost_usd"), "cost_basis": r.get("cost_basis"),
            "billing_channel": r.get("billing_channel"), "planned": r.get("planned"), "cumulative": r.get("cumulative"),
            "aborted": r.get("aborted"), "truncated": r.get("truncated")}


def _judge_prompts(manifest: dict, run_dir: Path, seeds_path: Path | str | None) -> dict:
    """What the judge of record WOULD be asked, planned from the exported
    records without any call: the count of planned calls and the UTF-8 byte
    length distribution of their prompts, which is what the per-call input
    bound (`judge_runner.estimate_input_tokens`) prices. Spec-independent, so
    it says nothing about dollars."""
    if seeds_path is None:
        return {"unavailable": "no seed file given"}
    from .judge_runner import estimate_input_tokens, load_rubric, plan_run
    from .seeds import load_seed_file

    records = _read_jsonl(run_dir / "transcripts.jsonl")
    seed_set = load_seed_file(seeds_path)
    plans = plan_run(records, manifest, seed_set.seeds, outcomes=load_json(OUTCOME_REGISTRY), rubric=load_rubric())
    sizes = sorted(len(p.prompt.encode("utf-8")) for p in plans if p.prompt is not None)
    return {"planned_calls": len(sizes), "not_applicable": sum(1 for p in plans if p.prompt is None),
            "prompt_bytes": ({"min": sizes[0], "median": int(statistics.median(sizes)), "max": sizes[-1], "total": sum(sizes)}
                             if sizes else None),
            "input_bound_tokens_total": sum(estimate_input_tokens(p.prompt) for p in plans if p.prompt is not None)}


def run_summary(run_dir: Path | str | None, *, mode: str, raw_eval_dir: Path | str | None = None,
                seeds_path: Path | str | None = None, params: dict | None = None) -> dict:
    """Everything the summary reports, as data; `render_markdown` renders it."""
    run_dir = Path(run_dir) if run_dir else None
    raw_dir = Path(raw_eval_dir) if raw_eval_dir else None
    out: dict[str, Any] = {"mode": mode, "params": params, "run_dir": str(run_dir) if run_dir else None,
                           "run_dir_exists": bool(run_dir and run_dir.is_dir()),
                           "raw_eval_present": bool(raw_dir and raw_dir.is_dir() and any(raw_dir.glob("*.eval")))}
    if mode == "preflight":
        out["note"] = ("preflight: the run, adapt and judge steps are gated off by mode, so no model is called and no "
                       "run directory or raw log should exist")
    manifest_path = run_dir / "manifest.json" if run_dir else None
    if manifest_path is None or not manifest_path.is_file():
        out["manifest"] = None
        out["sidecar"] = _guard(_sidecar, run_dir) if run_dir and run_dir.is_dir() else None
        out["judge_sidecar"] = _guard(_judge_sidecar, run_dir) if run_dir and run_dir.is_dir() else None
        out["raw_eval"] = _guard(_raw_eval, {}, raw_dir)
        return out
    manifest = load_json(manifest_path)
    sanitised = run_dir / "sanitised_log.json"
    # the eval's own status, from the sanitised projection (the manifest is left untouched: its digests are checked below)
    eval_status = load_json(sanitised).get("status") if sanitised.is_file() else None
    out["manifest"] = {"run_id": manifest.get("run_id"), "eval_id": manifest.get("eval_id"),
                       "claim_grade_eligible": (manifest.get("execution") or {}).get("claim_grade_eligible"),
                       "contract_checks": (manifest.get("execution") or {}).get("contract_checks"),
                       "target": (manifest.get("models") or {}).get("target", {}).get("inspect_name"),
                       "lock_sha256": (manifest.get("harness") or {}).get("environment_lock_sha256"),
                       "journal_nonce": (manifest.get("spend") or {}).get("journal_nonce")}
    out["structure"] = _guard(_structure, manifest, run_dir, eval_status)
    out["usage"] = _guard(_usage, manifest)
    out["redaction"] = ((manifest.get("artifacts") or {}).get("sanitiser") or {}).get("redaction_report")
    out["raw_eval"] = _guard(_raw_eval, manifest, raw_dir)
    out["published"] = _guard(_published, run_dir)
    out["integrity"] = _guard(_integrity, manifest, run_dir)
    out["sidecar"] = _guard(_sidecar, run_dir)
    out["judge_sidecar"] = _guard(_judge_sidecar, run_dir)
    out["judge_prompts"] = _guard(_judge_prompts, manifest, run_dir, seeds_path)
    return out


# ------------------------------------------------------------- rendering


def _row(k: Any, v: Any) -> str:
    return f"| {k} | {v} |"


def _table(title: str, rows: list[tuple[Any, Any]]) -> list[str]:
    return [f"**{title}**", "", "| | |", "|---|---|"] + [_row(k, v) for k, v in rows] + [""]


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (dict, list)):
        return "`" + json.dumps(v, ensure_ascii=False) + "`"
    return str(v)


def render_markdown(s: dict) -> str:
    lines = [f"## Petri audit ({s.get('mode')})", ""]
    if s.get("note"):
        lines += [s["note"], ""]
    if s.get("params"):
        lines += _table("Parameters resolved by CI", sorted(s["params"].items()))
    lines += _table("Run directory", [("path", s.get("run_dir")), ("exists", s.get("run_dir_exists")),
                                      ("raw .eval present outside the checkout", s.get("raw_eval_present"))])
    m = s.get("manifest")
    if not m:
        lines += ["No manifest (no adapted run).", ""]
    else:
        lines += _table("Manifest", [("run_id", m.get("run_id")), ("eval_id", m.get("eval_id")), ("target", m.get("target")),
                                     ("claim_grade_eligible", m.get("claim_grade_eligible")),
                                     ("environment lock sha256", m.get("lock_sha256")), ("journal_nonce", _fmt(m.get("journal_nonce")))])
        checks = m.get("contract_checks") or {}
        lines += _table("Contract checks", [(k, f"{v.get('status')}" + (f" ({v.get('detail')})" if v.get("detail") else ""))
                                            for k, v in checks.items()])
        st = s.get("structure") or {}
        if "unavailable" in st:
            lines += ["Structure: unavailable (" + st["unavailable"] + ")", ""]
        else:
            lines += _table("Measured structure (valid under any target)", [
                ("eval status", st.get("eval_status")), ("seeds", _fmt(st.get("seeds"))), ("epochs", st.get("epochs")),
                ("trees (samples)", st.get("trees")), ("conditions", st.get("conditions")), ("branches", st.get("branches")),
                ("shared-prefix branches", _fmt(st.get("shared_prefix_branches"))), ("survivors exported", st.get("survivors_exported")),
                ("target calls (generates)", st.get("target_calls")),
                ("target calls without a usage block", st.get("target_calls_without_usage")),
                ("records exported", (st.get("records") or {}).get("count")),
                ("records with schema or pairing problems", (st.get("records") or {}).get("with_problems")),
                ("records refused by the adapter", (st.get("refused") or {}).get("count")),
                ("max turns / tool rounds per turn", f"{st.get('max_turns')} / {st.get('max_tool_rounds_per_turn')}")])
            reasons = (st.get("refused") or {}).get("reasons") or []
            if reasons:
                lines += ["Refusals:", ""] + [f"- {r}" for r in reasons] + [""]
            probs = (st.get("records") or {}).get("problems") or []
            if probs:
                lines += ["Record problems:", ""] + [f"- {p}" for p in probs] + [""]
        usage = s.get("usage")
        if isinstance(usage, dict) and "unavailable" in usage:
            lines += ["Usage: unavailable (" + usage["unavailable"] + ")", ""]
        elif usage:
            lines += ["**Usage status per model** (provider-measured / mock/non-metered / unavailable)", "",
                      "| model | calls | calls without usage | input tokens | output tokens | status | price source |",
                      "|---|---|---|---|---|---|---|"]
            lines += [f"| {r['model']} | {_fmt(r['calls'])} | {_fmt(r['calls_without_usage'])} | {_fmt(r['input_tokens'])} | "
                      f"{_fmt(r['output_tokens'])} | **{r['status']}** | {r['price_source']} |" for r in usage]
            lines += ["", "Token counts of a mock/non-metered model are not provider-metered tokens; provider usage exists "
                      "only for a provider-measured row.", ""]
        red = s.get("redaction")
        if red:
            lines += _table("Sanitiser redaction report", [(k, _fmt(v)) for k, v in red.items()])
        raw = s.get("raw_eval") or {}
        rows = [("recorded sha256", raw.get("recorded_sha256"))]
        for f in raw.get("files") or []:
            rows.append((f["name"], f"{f['bytes']} bytes, sha256 {f['sha256'][:12]}…, matches manifest: {f['matches_manifest']}"))
        if raw.get("note"):
            rows.append(("note", raw["note"]))
        if raw.get("unavailable"):
            rows.append(("unavailable", raw["unavailable"]))
        lines += _table("Raw .eval (private artifact, never committed)", rows)
        pub = s.get("published") or {}
        if "unavailable" in pub:
            lines += ["Published exports: unavailable (" + pub["unavailable"] + ")", ""]
        else:
            rows = [(k, f"{v} bytes") for k, v in (pub.get("files") or {}).items()]
            rows += [(k, f"{v} bytes (cost sidecar)") for k, v in (pub.get("cost_sidecars") or {}).items()]
            rows += [("total", f"{pub.get('total_bytes')} bytes"), ("unresolved attachment:// references", pub.get("attachment_references"))]
            lines += _table("Sanitised exports (byte sizes)", rows)
        integ = s.get("integrity") or {}
        if "unavailable" in integ:
            lines += ["Integrity: unavailable (" + integ["unavailable"] + ")", ""]
        else:
            lines += _table("Integrity", [("manifest schema problems", _fmt(integ.get("manifest_problems"))),
                                          ("artifact digest problems", _fmt(integ.get("artifact_problems"))),
                                          ("hash chain", f"{(integ.get('chain') or {}).get('ok')} ({(integ.get('chain') or {}).get('message')})"),
                                          ("attachments resolved (manifest)", integ.get("attachments_resolved"))])
        jp = s.get("judge_prompts") or {}
        if "unavailable" in jp:
            lines += ["Judge prompts (planned, no call): unavailable (" + jp["unavailable"] + ")", ""]
        else:
            lines += _table("Judge prompts the judge of record would receive (planned from the exports; no call made)", [
                ("planned calls", jp.get("planned_calls")), ("not applicable", jp.get("not_applicable")),
                ("prompt UTF-8 bytes (min / median / max / total)", _fmt(jp.get("prompt_bytes"))),
                ("input bound, tokens, summed over calls (bytes + framing allowance)", jp.get("input_bound_tokens_total"))])
    for label, key in (("Target cost sidecar", "sidecar"), ("Judge cost sidecar", "judge_sidecar")):
        sc = s.get(key)
        if isinstance(sc, dict) and "unavailable" in sc:
            lines += [f"{label}: unavailable ({sc['unavailable']})", ""]
        elif sc:
            lines += _table(label, [(k, _fmt(v)) for k, v in sc.items()])
        else:
            lines += [f"{label}: none written.", ""]
    return "\n".join(lines) + "\n"
