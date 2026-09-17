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
from .manifest import CHAIN_FILE, artifact_problems, manifest_problems, verify_chain, verify_run
from .spend import resolve_price, usage_is_missing
from .transcripts import record_problems

ATTACHMENT_MARK = "attachment://"
# every file the lane can write into a run directory and commit; anything else found there is inventoried as
# unexpected, never skipped (Codex, PR #27: a fixed tuple omitted the judged run's judgments and analysis rows)
PUBLISHED_FILES = ("manifest.json", "transcripts.jsonl", "rule_outcomes.jsonl", "sanitised_log.json",
                   "judgments.jsonl", "analysis_rows.jsonl")
TEXT_SUFFIXES = (".json", ".jsonl")
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


def _collection(manifest: dict, *path: str) -> list:
    """A list the manifest must carry at `path`; a missing or mistyped one
    raises, so the caller marks the fields that depend on it unavailable
    instead of counting an absent collection as zero (Codex, PR #27)."""
    node: Any = manifest
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"manifest lacks {'.'.join(path)!r}")
        node = node[key]
    if not isinstance(node, list):
        raise TypeError(f"manifest {'.'.join(path)!r} is not a list")
    return node


def _reason(exc: BaseException) -> str:
    """The message alone (str(KeyError(...)) wraps it in quotes)."""
    return str(exc.args[0]) if exc.args else str(exc)


def _dig(obj: Any, *keys: str) -> Any:
    """Nested metadata read without raising: None whenever a level is not an
    object or a key is absent (Codex, PR #27: `models.target: null` raised
    AttributeError out of the header before any guarded section ran).
    Header fields are informational, so an absent one is a dash; counted
    collections go through `_collection` and `_member` instead."""
    node = obj
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _member(obj: Any, key: str, where: str) -> Any:
    """A key a collection member must carry. Its value may legitimately be
    None (a root branch's parent), so presence is what is required; an
    absent key is a gap in every count that reads it, never a value (Codex,
    PR #27: `.get()` read a missing survivor flag as False and a missing
    parent as a root)."""
    if not isinstance(obj, dict):
        raise TypeError(f"{where} is not an object")
    if key not in obj:
        raise KeyError(f"{where} lacks {key!r}")
    return obj[key]


def _structure(manifest: dict, run_dir: Path) -> dict:
    """The measured structure. Every field is either a value read from a
    collection the manifest carries, with every member key it reads
    present, or None with the reason recorded in `unavailable_fields`;
    nothing here is a default."""
    unavailable: dict[str, str] = {}
    out: dict[str, Any] = {"max_turns": _dig(manifest, "execution", "max_turns"),
                           "max_tool_rounds_per_turn": _dig(manifest, "execution", "max_tool_rounds_per_turn"),
                           "epochs": _dig(manifest, "execution", "epochs")}
    # the eval's own status, from the sanitised projection; a file that is missing, does not parse or carries no
    # status is a named gap (Codex, PR #27: the parse used to sit outside every guard)
    sanitised = run_dir / "sanitised_log.json"
    out["eval_status"] = None
    if not sanitised.is_file():
        unavailable["eval_status"] = "sanitised_log.json is missing from the run directory"
    else:
        try:
            doc = load_json(sanitised)
            if not isinstance(doc, dict):
                raise TypeError(f"sanitised_log.json holds a {type(doc).__name__}, not an object")
            out["eval_status"] = _member(doc, "status", "sanitised_log.json")
        except (ValueError, TypeError, OSError, KeyError) as exc:
            unavailable["eval_status"] = f"sanitised_log.json: {_reason(exc)}"
    try:
        out["seeds"] = [{"seed_id": _member(s, "seed_id", f"seed #{i}"),
                         "claim_grade_eligible": _member(s, "claim_grade_eligible", f"seed {s.get('seed_id', i)!r}")}
                        for i, s in enumerate(_collection(manifest, "seeds"))]
    except (KeyError, TypeError) as exc:
        # a missing seeds collection is a gap, never an empty seed list (Codex, PR #27)
        out["seeds"] = None
        unavailable["seeds"] = _reason(exc)
    tree_fields = ("trees", "branches", "conditions", "branches_without_condition_id", "shared_prefix_branches", "survivors_exported")
    try:
        trees = _collection(manifest, "trees")
        cells: set[tuple[Any, Any]] = set()       # (seed_id, condition_id): condition ids repeat across seeds
        anchors: list[Any] = []
        branches_n = survivors = no_condition = 0
        for i, t in enumerate(trees):
            where = f"tree {t.get('tree_id', i)!r}" if isinstance(t, dict) else f"tree #{i}"
            seed_id = _member(t, "seed_id", where)
            survivors += bool(_member(t, "survivor_exported", where))
            # each tree's own collection is required too (Codex, PR #27): a tree without `branches` is a gap in every
            # branch-derived count, not zero branches
            try:
                tree_branches = _collection(t, "branches")
            except (KeyError, TypeError) as exc:
                raise KeyError(f"{where}: {_reason(exc)}") from exc
            for j, b in enumerate(tree_branches):
                bwhere = f"{where} branch {b.get('branch_id', j)!r}" if isinstance(b, dict) else f"{where} branch #{j}"
                branches_n += 1
                condition = _member(b, "condition_id", bwhere)
                if condition is None:
                    no_condition += 1
                else:
                    cells.add((seed_id, condition))
                anchor = _member(b, "branched_from_turn_id", bwhere)
                if _member(b, "parent_branch_id", bwhere) is not None:
                    anchors.append(anchor)
        out.update(trees=len(trees), branches=branches_n, conditions=len(cells), branches_without_condition_id=no_condition,
                   shared_prefix_branches={"anchored": sum(1 for a in anchors if a is not None),
                                           "without_resolved_anchor": sum(1 for a in anchors if a is None)},
                   survivors_exported=survivors)
    except (KeyError, TypeError) as exc:
        out.update({f: None for f in tree_fields})
        unavailable["trees"] = _reason(exc)
    try:
        refused = _collection(manifest, "integrity", "records_refused")
        out["refused"] = {"count": len(refused),
                          "reasons": [f"{_member(r, 'branch_id', f'refusal #{i}')}: {_member(r, 'reason', f'refusal #{i}')}"
                                      for i, r in enumerate(refused)]}
    except (KeyError, TypeError) as exc:
        out["refused"] = None
        unavailable["refused"] = _reason(exc)
    try:
        by_role = {_member(r, "role", f"usage.by_role #{i}"): r for i, r in enumerate(_collection(manifest, "usage", "by_role"))}
        if "target" not in by_role:
            raise KeyError("manifest usage.by_role carries no target row")
        out["target_calls"] = _member(by_role["target"], "calls", "usage.by_role target row")
        out["target_calls_without_usage"] = _member(by_role["target"], "calls_without_usage", "usage.by_role target row")
    except (KeyError, TypeError) as exc:
        out["target_calls"] = out["target_calls_without_usage"] = None
        unavailable["target_calls"] = _reason(exc)
    transcripts_path = run_dir / "transcripts.jsonl"
    if transcripts_path.is_file():
        records = _read_jsonl(transcripts_path)
        problems = {r["conversation_id"]: record_problems(r) for r in records}
        bad = {k: v for k, v in problems.items() if v}
        out["records"] = {"count": len(records), "with_problems": len(bad),
                          "problems": [f"{k[:12]}: {'; '.join(v[:3])}" for k, v in list(bad.items())[:5]]}
    else:
        # a missing export is a gap, never a count of zero (Codex, PR #27); the manifest-derived counts stand
        out["records"] = {"unavailable": "transcripts.jsonl is missing from the run directory"}
    out["unavailable_fields"] = unavailable
    return out


def _usage(manifest: dict) -> list[dict] | dict:
    rows = []
    for i, r in enumerate(_collection(manifest, "usage", "by_model")):
        # every key the label reads must be present (Codex, PR #27): `usage_is_missing` reads an absent
        # calls_without_usage as 0, which labelled a damaged row provider-measured
        where = f"usage.by_model row #{i}"
        try:
            model = _member(r, "model", where)
            if not isinstance(model, str):
                raise TypeError(f"{where} model is not a string")
            where = f"{where} ({model!r})"
            fields = {k: _member(r, k, where) for k in ("calls", "calls_without_usage", "input_tokens", "output_tokens")}
        except (KeyError, TypeError) as exc:
            return {"unavailable": _reason(exc)}
        price = resolve_price(model)
        zero = price.input_per_mtok == 0 and price.output_per_mtok == 0
        rows.append({"model": model, **fields, "status": usage_status(r, price.source, zero), "price_source": price.source})
    if not rows:
        # a run with samples but no target model event leaves by_model empty while the adapter names the target in
        # usage_missing_models and the sidecar imputes its ceiling; that state is reported, never an omitted section
        # (Codex, PR #27)
        missing = (manifest.get("usage") or {}).get("usage_missing_models")
        if not isinstance(missing, list) or not missing:
            return {"unavailable": "usage.by_model is empty and usage_missing_models names no model"}
        for model in missing:
            price = resolve_price(model)
            zero = price.input_per_mtok == 0 and price.output_per_mtok == 0
            rows.append({"model": model, "calls": None, "calls_without_usage": None, "input_tokens": None, "output_tokens": None,
                         "status": USAGE_MOCK if zero else USAGE_UNAVAILABLE, "price_source": price.source,
                         "note": "no usage row recorded (no model event); named in usage_missing_models"})
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
    """Every entry of the run directory, by kind: the published families
    present, the cost sidecars, and anything else (a directory, a stray
    file), which is inventoried by name rather than skipped. The attachment
    scan covers every JSON or JSONL file found, whatever its kind."""
    files: dict[str, int] = {}
    sidecars: dict[str, int] = {}
    unexpected: dict[str, int | None] = {}
    refs = 0
    for p in sorted(run_dir.iterdir()):
        if p.is_dir():
            unexpected[p.name + "/"] = None
            continue
        size = p.stat().st_size
        if p.name in PUBLISHED_FILES:
            files[p.name] = size
        elif p.name.endswith(".report.json"):
            sidecars[p.name] = size
        else:
            unexpected[p.name] = size
        if p.suffix in TEXT_SUFFIXES:
            refs += p.read_text(encoding="utf-8", errors="replace").count(ATTACHMENT_MARK)
    total = sum(files.values()) + sum(sidecars.values()) + sum(v for v in unexpected.values() if v is not None)
    return {"files": files, "cost_sidecars": sidecars, "unexpected": unexpected, "total_bytes": total,
            "attachment_references": refs}


def _integrity(manifest: dict, run_dir: Path) -> dict:
    chain_ok, chain_msg = verify_chain(run_dir.parent) if (run_dir.parent / CHAIN_FILE).is_file() else (None, "no chain file")
    return {"manifest_problems": manifest_problems(manifest), "artifact_problems": artifact_problems(manifest, run_dir.parent),
            # the check a downloaded run directory can pass on its own (no chain file): cli verify-run
            "run_self_verification": verify_run(run_dir),
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
    sizes = [len(p.prompt.encode("utf-8")) for p in plans if p.prompt is not None]
    return {"planned_calls": len(sizes), "not_applicable": sum(1 for p in plans if p.prompt is None),
            "prompt_bytes": byte_stats(sizes),
            "input_bound_tokens_total": sum(estimate_input_tokens(p.prompt) for p in plans if p.prompt is not None)}


def byte_stats(sizes: list[int]) -> dict[str, int | float] | None:
    """min / median / max / total of byte counts; the median is the numeric
    median as `statistics.median` returns it (a half-byte value for an even
    count with middle values of different parity), never truncated (Codex,
    PR #27)."""
    if not sizes:
        return None
    return {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes), "total": sum(sizes)}


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

    def without_manifest(reason: str | None) -> dict:
        # no usable manifest: whatever the run directory holds (a partial adaptation, a sidecar) and the raw log are
        # still inventoried (Codex, PR #27); a dry run that failed before or during its manifest leaves this shape
        out["manifest"] = None
        out["manifest_error"] = reason
        present = bool(run_dir and run_dir.is_dir())
        out["published"] = _guard(_published, run_dir) if present else None
        out["sidecar"] = _guard(_sidecar, run_dir) if present else None
        out["judge_sidecar"] = _guard(_judge_sidecar, run_dir) if present else None
        out["raw_eval"] = _guard(_raw_eval, {}, raw_dir)
        return out

    if manifest_path is None or not manifest_path.is_file():
        return without_manifest(None)
    try:
        manifest = load_json(manifest_path)
        if not isinstance(manifest, dict):
            raise TypeError(f"manifest.json holds a {type(manifest).__name__}, not an object")
    except (ValueError, TypeError, OSError) as exc:
        # a truncated or unreadable manifest is reported by name and the rest still inventoried (Codex, PR #27)
        return without_manifest(f"manifest.json does not parse: {type(exc).__name__}: {exc}")
    out["manifest"] = {"run_id": manifest.get("run_id"), "eval_id": manifest.get("eval_id"),
                       "claim_grade_eligible": _dig(manifest, "execution", "claim_grade_eligible"),
                       "contract_checks": _dig(manifest, "execution", "contract_checks"),
                       "target": _dig(manifest, "models", "target", "inspect_name"),
                       "lock_sha256": _dig(manifest, "harness", "environment_lock_sha256"),
                       "journal_nonce": _dig(manifest, "spend", "journal_nonce")}
    out["structure"] = _guard(_structure, manifest, run_dir)
    out["usage"] = _guard(_usage, manifest)
    out["redaction"] = _dig(manifest, "artifacts", "sanitiser", "redaction_report")
    out["raw_eval"] = _guard(_raw_eval, manifest, raw_dir)
    out["published"] = _guard(_published, run_dir)
    out["integrity"] = _guard(_integrity, manifest, run_dir)
    out["sidecar"] = _guard(_sidecar, run_dir)
    out["judge_sidecar"] = _guard(_judge_sidecar, run_dir)
    out["judge_prompts"] = _guard(_judge_prompts, manifest, run_dir, seeds_path)
    return out


# ------------------------------------------------------------- rendering


def _row(k: Any, v: Any) -> str:
    return f"| {k} | {_fmt(v)} |"          # None renders as a dash, never as the word None


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
    if isinstance(s.get("params"), dict) and s["params"]:
        lines += _table("Parameters resolved by CI", sorted(s["params"].items()))
    lines += _table("Run directory", [("path", s.get("run_dir")), ("exists", s.get("run_dir_exists")),
                                      ("raw .eval present outside the checkout", s.get("raw_eval_present"))])
    m = s.get("manifest")
    if not m:
        lines += ["No manifest (" + (s.get("manifest_error") or "no adapted run") + ").", ""]
    else:
        lines += _table("Manifest", [("run_id", m.get("run_id")), ("eval_id", m.get("eval_id")), ("target", m.get("target")),
                                     ("claim_grade_eligible", m.get("claim_grade_eligible")),
                                     ("environment lock sha256", m.get("lock_sha256")), ("journal_nonce", _fmt(m.get("journal_nonce")))])
        checks = m.get("contract_checks")
        if isinstance(checks, dict):
            lines += _table("Contract checks", [(k, (f"{v.get('status')}" + (f" ({v.get('detail')})" if v.get("detail") else ""))
                                                    if isinstance(v, dict) else _fmt(v)) for k, v in checks.items()])
        else:
            lines += ["Contract checks: unavailable (execution.contract_checks is " + ("absent" if checks is None else "not an object") + ")", ""]
        st = s.get("structure") or {}
        if "unavailable" in st:
            lines += ["Structure: unavailable (" + st["unavailable"] + ")", ""]
        else:
            lines += _table("Measured structure (valid under any target)", [
                ("eval status", st.get("eval_status")), ("seeds", _fmt(st.get("seeds"))), ("epochs", st.get("epochs")),
                ("trees (samples)", st.get("trees")), ("conditions (distinct seed × condition cells)", st.get("conditions")),
                ("branches", st.get("branches")),
                ("shared-prefix branches", _fmt(st.get("shared_prefix_branches"))), ("survivors exported", st.get("survivors_exported")),
                ("target calls (generates)", st.get("target_calls")),
                ("target calls without a usage block", st.get("target_calls_without_usage")),
                ("records exported", (st.get("records") or {}).get("count", "unavailable: " + str((st.get("records") or {}).get("unavailable")))),
                ("records with schema or pairing problems", (st.get("records") or {}).get("with_problems", "unavailable")),
                ("records refused by the adapter", (st.get("refused") or {}).get("count") if st.get("refused") is not None else None),
                ("max turns / tool rounds per turn", f"{st.get('max_turns')} / {st.get('max_tool_rounds_per_turn')}")]
                + ([("branches without a condition id", st["branches_without_condition_id"])]
                   if st.get("branches_without_condition_id") is not None else []))
            missing = st.get("unavailable_fields") or {}
            if missing:
                lines += ["Structure fields unavailable (not zero):", ""] + [f"- {k}: {v}" for k, v in missing.items()] + [""]
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
                      f"{_fmt(r['output_tokens'])} | **{r['status']}**" + (f" ({r['note']})" if r.get("note") else "")
                      + f" | {r['price_source']} |" for r in usage]
            lines += ["", "Token counts of a mock/non-metered model are not provider-metered tokens; provider usage exists "
                      "only for a provider-measured row.", ""]
        red = s.get("redaction")
        if isinstance(red, dict) and red:
            lines += _table("Sanitiser redaction report", [(k, _fmt(v)) for k, v in red.items()])
        else:
            lines += ["Sanitiser redaction report: unavailable (" + ("absent" if red is None else "not an object") + ")", ""]
        integ = s.get("integrity") or {}
        if "unavailable" in integ:
            lines += ["Integrity: unavailable (" + integ["unavailable"] + ")", ""]
        else:
            lines += _table("Integrity", [("manifest schema problems", _fmt(integ.get("manifest_problems"))),
                                          ("artifact digest problems", _fmt(integ.get("artifact_problems"))),
                                          ("run directory verifies on its own (cli verify-run)", _fmt(integ.get("run_self_verification"))),
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
    # the raw log's measurements are rendered whether or not a manifest exists: a failed adaptation is exactly when
    # they are needed (Codex, PR #27)
    raw = s.get("raw_eval") or {}
    rows = [("recorded sha256 (manifest)", raw.get("recorded_sha256"))]
    for f in raw.get("files") or []:
        rows.append((f["name"], f"{f['bytes']} bytes, sha256 {f['sha256'][:12]}…, matches manifest: {f['matches_manifest']}"))
    if raw.get("note"):
        rows.append(("note", raw["note"]))
    if raw.get("unavailable"):
        rows.append(("unavailable", raw["unavailable"]))
    lines += _table("Raw .eval (private artifact, never committed)", rows)
    pub = s.get("published")
    if isinstance(pub, dict) and "unavailable" in pub:
        lines += ["Run directory contents: unavailable (" + pub["unavailable"] + ")", ""]
    elif pub:
        rows = [(k, f"{v} bytes") for k, v in (pub.get("files") or {}).items()]
        rows += [(k, f"{v} bytes (cost sidecar)") for k, v in (pub.get("cost_sidecars") or {}).items()]
        rows += [(k, ("directory" if v is None else f"{v} bytes") + " (UNEXPECTED: not a file the lane writes)")
                 for k, v in (pub.get("unexpected") or {}).items()]
        rows += [("total", f"{pub.get('total_bytes')} bytes"), ("unresolved attachment:// references", pub.get("attachment_references"))]
        lines += _table("Run directory contents (byte sizes)" + ("" if m else ", no manifest: partial or failed adaptation"), rows)
    for label, key in (("Target cost sidecar", "sidecar"), ("Judge cost sidecar", "judge_sidecar")):
        sc = s.get(key)
        if isinstance(sc, dict) and "unavailable" in sc:
            lines += [f"{label}: unavailable ({sc['unavailable']})", ""]
        elif sc:
            lines += _table(label, [(k, _fmt(v)) for k, v in sc.items()])
        else:
            lines += [f"{label}: none written.", ""]
    return "\n".join(lines) + "\n"
