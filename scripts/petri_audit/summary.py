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
from functools import lru_cache
from pathlib import Path
from typing import Any

from .framework import MANIFEST_SCHEMA, OUTCOME_REGISTRY, ROOT, load_json, sha256_file
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


@lru_cache(maxsize=1)
def _schema() -> dict:
    """The manifest schema, read once: the closed field sets the summary
    validates against are the schema's, never a second copy kept here."""
    return load_json(MANIFEST_SCHEMA)


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


NULL = type(None)


def _type_names(types: tuple[type, ...]) -> str:
    return " or ".join("null" if t is NULL else t.__name__ for t in types)


def _member(obj: Any, key: str, where: str, types: tuple[type, ...] | None = None) -> Any:
    """A key a collection member must carry, of the type the count expects.
    Its value may legitimately be None (a root branch's parent) where the
    schema allows it, so `types` says which; an absent key, or a value of
    another type, is a gap in every count that reads it, never a value
    (Codex, PR #27: `.get()` read a missing survivor flag as False and a
    missing parent as a root; presence alone read `survivor_exported:
    "false"` as a survivor). A bool never passes for an int."""
    if not isinstance(obj, dict):
        raise TypeError(f"{where} is not an object")
    if key not in obj:
        raise KeyError(f"{where} lacks {key!r}")
    value = obj[key]
    if types is not None and (not isinstance(value, types) or (isinstance(value, bool) and bool not in types)):
        raise TypeError(f"{where} {key!r} is not {_type_names(types)} (got {type(value).__name__})")
    return value


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
            out["eval_status"] = _member(doc, "status", "sanitised_log.json", (str,))
        except (ValueError, TypeError, OSError, KeyError) as exc:
            unavailable["eval_status"] = f"sanitised_log.json: {_reason(exc)}"
    try:
        out["seeds"] = [{"seed_id": _member(s, "seed_id", f"seed #{i}", (str,)),
                         "claim_grade_eligible": _member(s, "claim_grade_eligible", f"seed {s.get('seed_id', i)!r}", (bool,))}
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
        branch_ids: set[str] | None = set()       # every branch the manifest records has an exported record, by contract
        branches_n = survivors = no_condition = 0
        for i, t in enumerate(trees):
            where = f"tree {t.get('tree_id', i)!r}" if isinstance(t, dict) else f"tree #{i}"
            seed_id = _member(t, "seed_id", where, (str,))
            survivors += _member(t, "survivor_exported", where, (bool,))
            # each tree's own collection is required too (Codex, PR #27): a tree without `branches` is a gap in every
            # branch-derived count, not zero branches
            try:
                tree_branches = _collection(t, "branches")
            except (KeyError, TypeError) as exc:
                raise KeyError(f"{where}: {_reason(exc)}") from exc
            for j, b in enumerate(tree_branches):
                bwhere = f"{where} branch {b.get('branch_id', j)!r}" if isinstance(b, dict) else f"{where} branch #{j}"
                branches_n += 1
                branch_ids.add(_member(b, "conversation_id", bwhere, (str,)))
                condition = _member(b, "condition_id", bwhere, (str, NULL))
                if condition is None:
                    no_condition += 1
                else:
                    cells.add((seed_id, condition))
                anchor = _member(b, "branched_from_turn_id", bwhere, (int, NULL))
                if _member(b, "parent_branch_id", bwhere, (str, NULL)) is not None:
                    anchors.append(anchor)
        out.update(trees=len(trees), branches=branches_n, conditions=len(cells), branches_without_condition_id=no_condition,
                   shared_prefix_branches={"anchored": sum(1 for a in anchors if a is not None),
                                           "without_resolved_anchor": sum(1 for a in anchors if a is None)},
                   survivors_exported=survivors)
    except (KeyError, TypeError) as exc:
        out.update({f: None for f in tree_fields})
        unavailable["trees"] = _reason(exc)
        branch_ids = None
    try:
        refused = _collection(manifest, "integrity", "records_refused")
        out["refused"] = {"count": len(refused),
                          "reasons": [f"{_member(r, 'branch_id', f'refusal #{i}', (str,))}: {_member(r, 'reason', f'refusal #{i}', (str,))}"
                                      for i, r in enumerate(refused)]}
    except (KeyError, TypeError) as exc:
        out["refused"] = None
        unavailable["refused"] = _reason(exc)
    try:
        by_role: dict[str, dict] = {}
        for i, r in enumerate(_collection(manifest, "usage", "by_role")):
            role = _member(r, "role", f"usage.by_role #{i}", (str,))
            # the schema does not make roles unique; a repeated role is a gap, never the last row by list order
            # (Codex, PR #27, eleventh round)
            if role in by_role:
                raise ValueError(f"usage.by_role carries more than one {role!r} row (#{i} repeats an earlier one)")
            by_role[role] = r
        if "target" not in by_role:
            raise KeyError("manifest usage.by_role carries no target row")
        counts = {"calls": _member(by_role["target"], "calls", "usage.by_role target row", (int,)),
                  "calls_without_usage": _member(by_role["target"], "calls_without_usage", "usage.by_role target row", (int,))}
        _bounded_counts(counts, "usage.by_role target row")
        out["target_calls"], out["target_calls_without_usage"] = counts["calls"], counts["calls_without_usage"]
    except (KeyError, TypeError, ValueError) as exc:
        out["target_calls"] = out["target_calls_without_usage"] = None
        unavailable["target_calls"] = _reason(exc)
    transcripts_path = run_dir / "transcripts.jsonl"
    if transcripts_path.is_file():
        records = _read_jsonl(transcripts_path)
        # ids are unique across the file by contract; a duplicate (identical or conflicting) is a problem of its own
        # and never hides the first record's diagnostics (Codex, PR #27)
        seen: dict[Any, dict] = {}
        bad = 0
        details: list[str] = []
        for i, r in enumerate(records):
            if isinstance(r, dict):
                try:
                    probs = list(record_problems(r))
                except Exception as exc:  # noqa: BLE001 - a record the validator cannot even read is its own problem
                    probs = [f"record cannot be validated: {type(exc).__name__}: {exc}"]
            else:
                probs = ["not an object"]
            cid = r.get("conversation_id") if isinstance(r, dict) else None
            if cid is None:
                probs.append("no conversation_id")
            elif cid in seen:
                probs.append("duplicate conversation_id (" + ("identical record" if seen[cid] == r else "conflicting record") + ")")
            else:
                seen[cid] = r
            if probs:
                bad += 1
                details.append(f"record #{i} ({str(cid)[:12]}): {'; '.join(probs[:3])}")
        # the export's id set must equal the manifest's branch ids: the adapter lists a branch only after exporting its
        # record, so a record the manifest does not name, or a branch without a record, is a sealed mismatch that no
        # per-record check and no digest detects (Codex, PR #27, eleventh round)
        if branch_ids is None:
            id_match: dict[str, Any] = {"unavailable": "manifest branches unavailable"}
        else:
            not_in_manifest = sorted(str(c) for c in set(seen) - branch_ids)
            without_record = sorted(branch_ids - set(seen))
            id_match = {"records_not_in_manifest": len(not_in_manifest), "branches_without_record": len(without_record)}
            if not_in_manifest:
                details.append(f"record ids the manifest names no branch for: {', '.join(c[:12] for c in not_in_manifest[:3])}")
            if without_record:
                details.append(f"manifest branches with no exported record: {', '.join(c[:12] for c in without_record[:3])}")
        out["records"] = {"count": len(records), "unique_conversation_ids": len(seen), "with_problems": bad, "id_match": id_match,
                          "problems": details[:6]}
    else:
        # a missing export is a gap, never a count of zero (Codex, PR #27); the manifest-derived counts stand
        out["records"] = {"unavailable": "transcripts.jsonl is missing from the run directory"}
    out["unavailable_fields"] = unavailable
    return out


def _judge_row_from_sidecar(run_dir: Path, what: str, judge_started: Path | str | None = None) -> list[dict]:
    """The judge of record reported from its cost sidecar when judgments.jsonl
    carries no judge row: the file is absent (the judge died before opening
    it), or it exists empty or with rule rows only, which is exactly what a
    judge killed during its first provider call leaves, because the loop
    opens the file before that call (Codex, PR #27, tenth round: that shape
    bypassed the fallback and omitted the paid judge). The workflow's fallback
    sidecar books the ceiling; the judge is reported from it, never omitted.
    No sidecar is a named gap whenever anything shows a judge ran, and the
    workflow's judge-start marker (`judge_started`, set before the judge is
    invoked) is such evidence: a judge that died before opening its file,
    whose fallback sidecar was never written either, is reported from the
    marker (Codex, PR #27, eleventh round)."""
    from .spend import resolve_registry_price

    side = _judge_sidecar(run_dir)
    if not side:
        started = judge_started is not None and Path(judge_started).is_file()
        if what == "no judgments.jsonl" and not started:
            return []                         # nothing shows a judge ran
        evidence = f"{what}, the judge-start marker is set" if started else what
        return [{"model": "(judge of record)", "calls": None, "calls_without_usage": None, "input_tokens": None, "output_tokens": None,
                 "status": USAGE_UNAVAILABLE, "price_source": None, "note": f"judge of record: {evidence}, and no judge sidecar exists"}]
    if "unavailable" in side:
        return [{"model": "(judge of record)", "calls": None, "calls_without_usage": None, "input_tokens": None, "output_tokens": None,
                 "status": USAGE_UNAVAILABLE, "price_source": None,
                 "note": f"judge of record: {what} and the judge sidecar is unavailable ({side['unavailable']})"}]
    price = resolve_registry_price(side["judge_model"])
    zero = price.input_per_mtok == 0 and price.output_per_mtok == 0
    return [{"model": side["judge_model"], "calls": None, "calls_without_usage": None, "input_tokens": None, "output_tokens": None,
             "status": USAGE_MOCK if zero else USAGE_UNAVAILABLE, "price_source": price.source,
             "note": f"judge of record: {what}; the judge sidecar books {side['cost_basis']}"}]


def _judge_usage_rows(run_dir: Path, judge_started: Path | str | None = None) -> list[dict]:
    """One usage row per judge model aggregated from judgments.jsonl, which
    the judge step writes after the manifest's usage table was closed
    (Codex, PR #27: the table omitted every paid judge call). A file that
    cannot be read is a row that says so, never an omitted judge; a file
    with no judge row falls back to the sidecar (`_judge_row_from_sidecar`)."""
    from .spend import resolve_registry_price

    path = run_dir / "judgments.jsonl"
    if not path.is_file():
        return _judge_row_from_sidecar(run_dir, "no judgments.jsonl", judge_started)
    try:
        rows = _read_jsonl(path)
        per: dict[str, dict[str, Any]] = {}
        rows_per: dict[str, int] = {}
        for i, j in enumerate(rows):
            where = f"judgments.jsonl row #{i}"
            method = _member(j, "method", where, (str,))
            if method == "rule":
                continue                      # rule rows are not calls
            if method != "judge":
                # only the known non-call method is skipped; any other value is a row whose attempts and tokens would
                # otherwise vanish from the table (Codex, PR #27, eleventh round)
                raise ValueError(f"{where} 'method' {method!r} is neither 'judge' nor 'rule'")
            spec = _member(j, "judge_model", where, (str,))
            agg = per.setdefault(spec, {"calls": 0, "calls_without_usage": 0, "input_tokens": 0, "output_tokens": 0})
            rows_per[spec] = rows_per.get(spec, 0) + 1
            # the row records the requests the provider received for it (`provider_attempts`, written by the judge
            # loop): every charged retry was one without usage (Codex, PR #27), and a row whose retry the ceiling
            # refused made exactly its charged attempts, not one more (independent review of PR #27: `1 + retries`
            # counted the refused retry as a request), so the count is read and checked against the retries, never
            # derived
            retries = _member(j, "retry_attempts_charged", where, (int,))
            attempts = _member(j, "provider_attempts", where, (int,))
            if retries < 0 or attempts < 1 or not retries <= attempts <= retries + 1:
                raise ValueError(f"{where} 'provider_attempts' {attempts} does not agree with 'retry_attempts_charged' {retries}")
            agg["calls"] += attempts
            if _member(j, "usage_missing", where, (bool,)):
                agg["calls_without_usage"] += attempts
            else:
                agg["calls_without_usage"] += attempts - 1
                tokens = {k: _member(j, k, where, (int,)) for k in ("input_tokens", "output_tokens")}
                _bounded_counts(tokens, where)
                agg["input_tokens"] += tokens["input_tokens"]
                agg["output_tokens"] += tokens["output_tokens"]
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return [{"model": "(judge of record)", "calls": None, "calls_without_usage": None, "input_tokens": None, "output_tokens": None,
                 "status": USAGE_UNAVAILABLE, "price_source": None, "note": f"judge of record: judgments.jsonl unreadable ({_reason(exc)})"}]
    if not per:
        return _judge_row_from_sidecar(run_dir, f"judgments.jsonl has no judge row ({len(rows)} non-judge row(s))", judge_started)
    out = []
    for spec, agg in sorted(per.items()):
        price = resolve_registry_price(spec)
        zero = price.input_per_mtok == 0 and price.output_per_mtok == 0
        out.append({"model": spec, **agg, "status": usage_status(agg, price.source, zero), "price_source": price.source,
                    "note": (f"judge of record, aggregated from judgments.jsonl ({rows_per[spec]} judge row(s), "
                             f"{agg['calls']} provider attempt(s))")})
    return out


def _bounded_counts(fields: dict[str, Any], where: str) -> None:
    """Usage counters are non-negative, and a row cannot miss usage on more
    calls than it made. A valid integer outside those bounds is a named gap,
    never a labelled row (Codex, PR #27, tenth round: `calls_without_usage:
    -1` read as "nothing missing" and a priced row with negative counts was
    labelled provider-measured)."""
    for key, value in fields.items():
        if value is not None and value < 0:
            raise ValueError(f"{where} {key!r} is negative ({value})")
    calls, without = fields.get("calls"), fields.get("calls_without_usage")
    if calls is not None and without is not None and without > calls:
        raise ValueError(f"{where} 'calls_without_usage' {without} exceeds 'calls' {calls}")


def _usage(manifest: dict, run_dir: Path | None = None, judge_started: Path | str | None = None) -> list[dict] | dict:
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
            fields = {"calls": _member(r, "calls", where, (int,)), "calls_without_usage": _member(r, "calls_without_usage", where, (int,)),
                      "input_tokens": _member(r, "input_tokens", where, (int, NULL)),
                      "output_tokens": _member(r, "output_tokens", where, (int, NULL))}
            _bounded_counts(fields, where)
        except (KeyError, TypeError, ValueError) as exc:
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
    if run_dir is not None:
        rows.extend(_judge_usage_rows(run_dir, judge_started))
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
    # every file at any depth (Codex, PR #27: the artifact uploads nested directories recursively, so a file inside
    # one must be counted and scanned like any other); an empty directory is listed by name
    for p in sorted(run_dir.rglob("*")):
        rel = p.relative_to(run_dir).as_posix()
        if p.is_dir():
            if not any(p.iterdir()):
                unexpected[rel + "/"] = None
            continue
        size = p.stat().st_size
        if p.parent == run_dir and p.name in PUBLISHED_FILES:
            files[p.name] = size
        elif p.parent == run_dir and p.name.endswith(".report.json"):
            sidecars[p.name] = size
        else:
            unexpected[rel] = size
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


NUMBER = (int, float)


def _sidecar_files(run_dir: Path, *, judge: bool) -> list[Path]:
    """The cost sidecars directly inside the run directory, by filename
    pattern: `*.judge.report.json` for the judge, every other
    `*.report.json` for the target."""
    return sorted(p for p in run_dir.glob("*.report.json")
                  if p.is_file() and (p.name.endswith(".judge.report.json") == judge))


def _sidecar(run_dir: Path) -> dict | None:
    """The target cost sidecar the ledger folds. Its spend fields are required
    and typed (Codex, PR #27): a sidecar missing `cost_usd` is an
    unavailable spend record, never a table with a dash in it."""
    # located by pattern (Codex, PR #27): a flat artifact extraction keeps the sidecar's original name under a
    # directory of the downloader's choosing, so the directory name never reconstructs it
    found = _sidecar_files(run_dir, judge=False)
    if not found:
        return None
    if len(found) > 1:
        return {"path": ", ".join(p.name for p in found), "unavailable": f"{len(found)} target cost sidecars in the run directory"}
    path = found[0]
    where = path.name
    try:
        # a sidecar the non-atomic write left truncated is this section's gap, never an exception that takes the
        # target usage with it (Codex, PR #27, eleventh round)
        r = load_json(path)
        if not isinstance(r, dict):
            raise TypeError(f"{where} is not an object")
        return {"path": path.name, "cost_usd": _member(r, "cost_usd", where, NUMBER), "cost_basis": _member(r, "cost_basis", where, (str,)),
                "billing_channel": _member(r, "billing_channel", where, (str,)),
                "usage_missing_models": _member(r, "usage_missing_models", where, (list,)),
                "max_spend_usd": _member(r, "max_spend_usd", where, NUMBER), "spend_report_reason": r.get("spend_report_reason")}
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return {"path": path.name, "unavailable": _reason(exc)}


def _judge_sidecar(run_dir: Path) -> dict | None:
    found = _sidecar_files(run_dir, judge=True)
    if not found:
        return None
    if len(found) > 1:
        return {"path": ", ".join(p.name for p in found), "unavailable": f"{len(found)} judge cost sidecars in the run directory"}
    path = found[0]
    where = path.name
    try:
        r = load_json(path)
        if not isinstance(r, dict):
            raise TypeError(f"{where} is not an object")
        return {"path": path.name, "judge_model": _member(r, "judge_model", where, (str,)), "cost_usd": _member(r, "cost_usd", where, NUMBER),
                "cost_basis": _member(r, "cost_basis", where, (str,)), "billing_channel": _member(r, "billing_channel", where, (str,)),
                "planned": r.get("planned"), "cumulative": r.get("cumulative"), "aborted": r.get("aborted"), "truncated": r.get("truncated")}
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return {"path": path.name, "unavailable": _reason(exc)}


def _judge_prompts(manifest: dict, run_dir: Path, seeds_path: Path | str | None) -> dict:
    """What the judge of record WOULD be asked, planned from the exported
    records without any call: the count of planned calls and the UTF-8 byte
    length distribution of their prompts, which is what the per-call input
    bound (`judge_runner.estimate_input_tokens`) prices. Spec-independent, so
    it says nothing about dollars."""
    if seeds_path is None:
        return {"unavailable": "no seed file given"}
    from .framework import ADVICE_RUBRIC
    from .judge_runner import estimate_input_tokens, load_rubric, plan_run
    from .seeds import load_seed_file

    # the inputs must be the run's own (Codex, PR #27). A paid run's own commit steps move HEAD past the recorded
    # engine commit even when no input changed, so HEAD is never compared with the sha: each input file in the
    # checkout is compared blob-by-blob with the same path at the recorded commit (git show <sha>:<path>). When git
    # cannot serve the commit (the all-zero placeholder, a shallow checkout), the registry is still checked against
    # the manifest's digest and plan_run refuses seed drift by the recorded seed digests; the rubric, which the
    # manifest does not record, is then reported unverified rather than assumed
    engine_sha = _dig(manifest, "adapter", "engine_sha")
    pinned = isinstance(engine_sha, str) and engine_sha != "0" * 40
    verified = {name: (_blob_matches(engine_sha, path) if pinned else None)
                for name, path in (("seeds", Path(seeds_path)), ("outcome_registry", OUTCOME_REGISTRY), ("rubric", ADVICE_RUBRIC))}
    differing = [name for name, ok in verified.items() if ok is False]
    if differing:
        return {"unavailable": f"{', '.join(differing)} in the checkout differ from the run's engine commit "
                               f"{engine_sha[:12]}; the statistics would describe prompts the run never used"}
    registry_sha = sha256_file(OUTCOME_REGISTRY)
    if _dig(manifest, "framework", "outcome_registry_sha256") != registry_sha:
        return {"unavailable": "the outcome registry in the checkout does not digest to the manifest's outcome_registry_sha256"}
    records = _read_jsonl(run_dir / "transcripts.jsonl")
    seed_set = load_seed_file(seeds_path)
    plans = plan_run(records, manifest, seed_set.seeds, outcomes=load_json(OUTCOME_REGISTRY), rubric=load_rubric())
    sizes = [len(p.prompt.encode("utf-8")) for p in plans if p.prompt is not None]
    return {"planned_calls": len(sizes), "not_applicable": sum(1 for p in plans if p.prompt is None),
            "prompt_bytes": byte_stats(sizes),
            "input_bound_tokens_total": sum(estimate_input_tokens(p.prompt) for p in plans if p.prompt is not None),
            "inputs": {"engine_sha": engine_sha, "verified_against_engine_commit": verified,
                       "outcome_registry_sha256": registry_sha, "seeds_checked_by_digest": True,
                       "rubric_sha256": sha256_file(ADVICE_RUBRIC), "rubric_pinned_by_manifest": False}}


def _blob_matches(sha: str, path: Path) -> bool | None:
    """Whether the file at `path` in the checkout is byte-identical to the
    same path at commit `sha` (git show <sha>:<path>); None when git cannot
    say (unknown commit, a path outside the repository, no git)."""
    import hashlib
    import subprocess

    try:
        rel = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
        out = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=ROOT, capture_output=True, check=True)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None
    return hashlib.sha256(out.stdout).hexdigest() == sha256_file(path)


def byte_stats(sizes: list[int]) -> dict[str, int | float] | None:
    """min / median / max / total of byte counts; the median is the numeric
    median as `statistics.median` returns it (a half-byte value for an even
    count with middle values of different parity), never truncated (Codex,
    PR #27)."""
    if not sizes:
        return None
    return {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes), "total": sum(sizes)}


def _closed_object(value: Any, spec: dict, where: str) -> None:
    """`value` against a schema fragment of the shape the manifest uses for
    its reported blocks: an object with `required` keys, no additional
    properties, and members typed integer (with a minimum), boolean (with an
    optional const) or object-of-integers. Raises the same exceptions the
    member checks raise; the caller turns them into an `unavailable`."""
    if not isinstance(value, dict):
        raise TypeError(f"{where} is not an object")
    missing = [k for k in spec.get("required", []) if k not in value]
    if missing:
        raise KeyError(f"{where} lacks {', '.join(repr(k) for k in missing)}")
    unknown = sorted(set(value) - set(spec.get("properties", {})))
    if unknown and spec.get("additionalProperties") is False:
        raise KeyError(f"{where} carries unknown key(s) {', '.join(repr(k) for k in unknown)}")
    for key, prop in spec.get("properties", {}).items():
        if key not in value:
            continue
        v, kw = value[key], f"{where} {key!r}"
        kind = prop.get("type")
        if kind == "integer":
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(f"{kw} is not int (got {type(v).__name__})")
            if v < prop.get("minimum", 0):
                raise ValueError(f"{kw} is negative ({v})")
        elif kind == "boolean":
            if not isinstance(v, bool):
                raise TypeError(f"{kw} is not bool (got {type(v).__name__})")
            if "const" in prop and v != prop["const"]:
                raise ValueError(f"{kw} must be {prop['const']} (got {v})")
        elif kind == "object" and prop.get("additionalProperties", {}).get("type") == "integer":
            if not isinstance(v, dict):
                raise TypeError(f"{kw} is not an object (got {type(v).__name__})")
            for k2, v2 in v.items():
                if isinstance(v2, bool) or not isinstance(v2, int):
                    raise TypeError(f"{kw}[{k2!r}] is not int (got {type(v2).__name__})")
                if v2 < prop["additionalProperties"].get("minimum", 0):
                    raise ValueError(f"{kw}[{k2!r}] is negative ({v2})")


def _contract_checks(manifest: dict) -> dict | None:
    """`execution.contract_checks` validated against the schema's closed set
    before it is rendered: every required check present, no unknown check,
    each a `status` from the schema's enum with a string-or-null `detail`
    (Codex, PR #27, eleventh round: a table missing `holdout_seal` rendered
    as a complete table). None when absent; `unavailable` with the reason
    when present and malformed."""
    checks = _dig(manifest, "execution", "contract_checks")
    if checks is None:
        return None
    where = "execution.contract_checks"
    try:
        _closed_object(checks, _schema()["properties"]["execution"]["properties"]["contract_checks"], where)
        statuses = _schema()["$defs"]["check"]["properties"]["status"]["enum"]
        for name, c in checks.items():
            cw = f"{where}.{name}"
            status = _member(c, "status", cw, (str,))
            if status not in statuses:
                raise ValueError(f"{cw} 'status' {status!r} is not one of {statuses}")
            _member(c, "detail", cw, (str, NULL))
            extra = sorted(set(c) - {"status", "detail"})
            if extra:
                raise KeyError(f"{cw} carries unknown key(s) {', '.join(repr(k) for k in extra)}")
    except (KeyError, TypeError, ValueError) as exc:
        return {"unavailable": _reason(exc)}
    return checks


def _redaction(manifest: dict) -> dict | None:
    """`artifacts.sanitiser.redaction_report` validated against the schema's
    closed set (every counter present and non-negative, the booleans typed
    with their consts, the by-type maps integer-valued) before it is rendered
    as a measurement (Codex, PR #27, eleventh round: a report missing a
    counter rendered with the field silently absent). None when absent."""
    report = _dig(manifest, "artifacts", "sanitiser", "redaction_report")
    if report is None:
        return None
    spec = _schema()["properties"]["artifacts"]["properties"]["sanitiser"]["properties"]["redaction_report"]
    try:
        _closed_object(report, spec, "artifacts.sanitiser.redaction_report")
    except (KeyError, TypeError, ValueError) as exc:
        return {"unavailable": _reason(exc)}
    return report


def run_summary(run_dir: Path | str | None, *, mode: str, raw_eval_dir: Path | str | None = None,
                seeds_path: Path | str | None = None, params: dict | None = None,
                judge_started: Path | str | None = None) -> dict:
    """Everything the summary reports, as data; `render_markdown` renders it.
    `judge_started` is the workflow's judge-start marker file, evidence that
    a judge was invoked even when it left no file behind."""
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
                       "contract_checks": _guard(_contract_checks, manifest),
                       "target": _dig(manifest, "models", "target", "inspect_name"),
                       "lock_sha256": _dig(manifest, "harness", "environment_lock_sha256"),
                       "journal_nonce": _dig(manifest, "spend", "journal_nonce")}
    out["structure"] = _guard(_structure, manifest, run_dir)
    out["usage"] = _guard(_usage, manifest, run_dir, judge_started)
    out["redaction"] = _guard(_redaction, manifest)
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
        if checks is None:
            lines += ["Contract checks: unavailable (execution.contract_checks is absent)", ""]
        elif not isinstance(checks, dict) or "unavailable" in checks:
            lines += ["Contract checks: unavailable (" + str(checks.get("unavailable") if isinstance(checks, dict) else checks) + ")", ""]
        else:
            lines += _table("Contract checks", [(k, f"{v.get('status')}" + (f" ({v.get('detail')})" if v.get("detail") else ""))
                                                for k, v in checks.items()])
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
                ("records vs manifest branches (not in manifest / without record)",
                 _fmt((st.get("records") or {}).get("id_match", "unavailable"))),
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
        if red is None:
            lines += ["Sanitiser redaction report: unavailable (absent)", ""]
        elif not isinstance(red, dict) or "unavailable" in red:
            lines += ["Sanitiser redaction report: unavailable (" + str(red.get("unavailable") if isinstance(red, dict) else red) + ")", ""]
        else:
            lines += _table("Sanitiser redaction report", [(k, _fmt(v)) for k, v in red.items()])
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
                ("input bound, tokens, summed over calls (bytes + framing allowance)", jp.get("input_bound_tokens_total")),
                ("inputs used (pinned to the run where the manifest records them)", _fmt(jp.get("inputs")))])
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
