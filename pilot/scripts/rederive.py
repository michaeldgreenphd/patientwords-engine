"""Every derived artifact derived again, with the current code, from the two recorded result files and compared
with the file on disk. write_manifest.py finalize runs it before sealing a bundle, and compute_summary.py before
computing a number: a call log whose non-final attempt no longer matches the recorded result (an interrupted
--replace) would otherwise feed plausible stale retry and pooled-attempt statistics into the summary, caught only at
finalize (Codex review of PR #52).
"""
from __future__ import annotations

import json

import build_checker_set
import extract_workflow_journal
import make_review_sheet
import parse_checker
import parse_generation
from common import PILOT, load_seeds, log_binding, read_csv, read_jsonl, sha256_file

JOURNAL_COPIES = {"generation": "workflows/generation.journal.jsonl", "checker": "workflows/checker.journal.jsonl"}


def extraction_problems(stages: tuple[str, ...] = ("generation", "checker")) -> list[str]:
    """Why a recorded result file is not what the copied journal under workflows/ yields: the copy missing, no longer
    extracting, or extracting to a document that differs from the result file in anything but the journal's path
    (`source`). A result edited while keeping its self-declared source_sha256 would otherwise be re-parsed, recomputed
    and sealed as that run's (Codex review of PR #52). Empty when the named stages' result files are the copies'
    extractions."""
    problems = []
    for stage in stages:
        rel = JOURNAL_COPIES[stage]
        result_path = PILOT / f"workflow_{stage}_result.json"
        copy = PILOT / rel
        if not result_path.exists():
            problems.append(f"{result_path.name} is missing")
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if not copy.exists():
            problems.append(f"{rel} is missing; copy the run's journal.jsonl there (the result is extracted again from it)")
            continue
        try:
            doc = extract_workflow_journal.extract(stage, str(copy),
                                                   allow_missing=bool(result.get("agents_without_result_record")))
        except SystemExit as e:
            problems.append(f"{rel} no longer extracts: {e}")
            continue
        if {k: v for k, v in doc.items() if k != "source"} != {k: v for k, v in result.items() if k != "source"}:
            problems.append(f"{result_path.name} is not what the current code extracts from {rel} (a response or a "
                            f"field differs); re-extract it with --replace from the run's journal")
    return problems


def generation_rederive_problems(calls: dict) -> list[str]:
    """The generation stage alone: workflow_generation_result.json extracted again from the copied journal, then rows,
    failures, call log and raw texts derived again from it with the current code and compared with the files on
    disk. build_checker_set.py and load_checker_batches (every reader of the checker plan) run it before any checker
    work is built or emitted: a row whose text was edited under intact ids, attempts and prompt hashes passed
    generation_problems, and checker work was emitted for data absent from the recorded journal, caught only at the
    summary, after the checker agents had run (Codex review of PR #52). Empty when the generation reproduces."""
    problems = extraction_problems(("generation",))
    if problems:
        return problems
    calls_meta = {c["id"]: c for c in calls["calls"]}
    call_log = read_jsonl(PILOT / "call_log.jsonl")
    unbound = log_binding(call_log)
    if unbound is None:
        return ["call_log.jsonl: plan_binding is missing or mixed across its entries; re-run parse_generation.py"]
    gen_result = json.loads((PILOT / "workflow_generation_result.json").read_text(encoding="utf-8"))
    try:
        by_id = parse_generation.validate_result(gen_result, calls_meta, unbound)
    except SystemExit as e:
        return [f"workflow_generation_result.json no longer validates against the plan: {e}"]
    rows, failures, log, raw_texts = parse_generation.derive(by_id, calls_meta, parse_generation.binding_label(unbound))
    if rows != read_jsonl(PILOT / "generated" / "all_rows.jsonl"):
        problems.append("generated/all_rows.jsonl is not what the current code derives from workflow_generation_result.json")
    if failures != read_jsonl(PILOT / "generated" / "format_failures.jsonl"):
        problems.append("generated/format_failures.jsonl is not what the current code derives from the recorded result")
    if log != call_log:
        problems.append("call_log.jsonl is not what the current code derives from workflow_generation_result.json")
    for name, text in raw_texts.items():
        p = PILOT / "generated" / "raw" / name
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            problems.append(f"generated/raw/{name} differs from the response recorded in workflow_generation_result.json")
    return problems


def rederive_problems(calls: dict) -> list[str]:
    """Every derived artifact derived again, with the current code, from the two recorded result files and compared
    with the file on disk: first the generation stage (generation_rederive_problems: the result file from the copied
    journal under workflows/, then rows, failures, call log and raw texts from it); then the checker result file
    from its copied journal (extraction_problems); the checker set, key and plan from the rows, the seeds and the
    checker template; checked rows and checker log from workflow_checker_result.json; the review sheet, key and map
    from the checked rows (the sheet's own two annotation columns excepted). A bundle whose stored responses no
    longer reproduce its files, or whose files were written by earlier code, is refused (Codex review of PR #52).
    Empty when everything reproduces."""
    problems = generation_rederive_problems(calls)
    if problems:
        return problems
    problems = extraction_problems(("checker",))
    if problems:
        return problems
    rows = read_jsonl(PILOT / "generated" / "all_rows.jsonl")  # proven above to be what the recorded result derives
    template = (PILOT / "prompts" / "checker_prompt.txt").read_text(encoding="utf-8")
    blind, truth, plan_doc = build_checker_set.derive(rows, load_seeds(), template, sha256_file(PILOT / "seeds.json"),
                                                      sha256_file(PILOT / "generated" / "all_rows.jsonl"))
    if blind != read_jsonl(PILOT / "checker_set.jsonl"):
        problems.append("checker_set.jsonl is not what the current code derives from the rows and seeds")
    if truth != read_jsonl(PILOT / "checker_key.jsonl"):
        problems.append("checker_key.jsonl is not what the current code derives from the rows and seeds")
    if plan_doc != json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8")):
        problems.append("checker_batches.json is not what the current code derives from the rows, seeds and template")
    if problems:
        return problems
    checker_log = read_jsonl(PILOT / "checker_log.jsonl")
    cunbound = log_binding(checker_log)
    if cunbound is None:
        return ["checker_log.jsonl: plan_binding is missing or mixed across its entries; re-run parse_checker.py"]
    chk_result = json.loads((PILOT / "workflow_checker_result.json").read_text(encoding="utf-8"))
    try:
        cby = parse_checker.validate_result(chk_result, {b["batch_id"]: b["prompt_sha256"] for b in plan_doc["batches"]},
                                            cunbound)
    except SystemExit as e:
        return [f"workflow_checker_result.json no longer validates against the checker plan: {e}"]
    plan_sha = sha256_file(PILOT / "checker_batches.json")
    checked, clog = parse_checker.derive(cby, plan_doc["batches"], {x["id"]: x for x in blind}, truth,
                                         parse_checker.binding_label(cunbound), plan_sha)
    if checked != read_jsonl(PILOT / "checked.jsonl"):
        problems.append("checked.jsonl is not what the current code derives from workflow_checker_result.json")
    if clog != checker_log:
        problems.append("checker_log.jsonl is not what the current code derives from workflow_checker_result.json")
    if problems:
        return problems
    sheet, key, rmap = make_review_sheet.derive(checked, plan_sha)
    term_cols = ("id", "clinical_term", "patient_term", "template")
    if [{k: r[k] for k in term_cols} for r in sheet] != [{k: r.get(k) for k in term_cols} for r in read_csv(PILOT / "review_sheet.csv")]:
        problems.append("review_sheet.csv (its term columns) is not the draw the current code makes from checked.jsonl")
    if key != read_csv(PILOT / "review_key.csv"):
        problems.append("review_key.csv is not the draw the current code makes from checked.jsonl")
    if rmap != json.loads((PILOT / "review_map.json").read_text(encoding="utf-8")):
        problems.append("review_map.json is not the draw the current code makes from checked.jsonl")
    return problems
