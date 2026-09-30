"""Write manifest.json from the files on disk: model facts (from manifest_model.json), date, seeds and their stated
provenance, prompt hashes, protocol hash, script hashes. The first run records protocol_sha256_at_write; later runs
keep that value and add protocol_sha256_now so a change to the frozen protocol is visible.

  python3 scripts/write_manifest.py                    # plan-time manifest
  python3 scripts/write_manifest.py finalize           # adds output hashes and the finalize timestamp
  python3 scripts/write_manifest.py [finalize] --reset # start fresh metadata after the inputs changed

A manifest already on disk lends its creation time, finalization time and run records to the next write. When the
planned inputs have changed since it was written (the seed file, the design file or a prompt template), keeping
those would pair new prompts with the previous run's provenance, so the write is refused unless --reset is passed;
--reset records metadata_reset_utc and starts the timestamps and run records afresh (Codex review of PR #52).
manifest_model.json, the operator's statement of the session and model that served the run, is frozen the same
way: its hash is recorded at the first write, an edit after that is refused unless --reset is passed, and since
--reset clears the run records and `finalize` requires both subagent runs recorded (record_run.py, which takes the
model evidence from the transcripts), the outputs cannot be finalized under model facts written after the run
without a visible reset and re-recording (Codex review of PR #52). `finalize` further requires each run record's
journal_sha256 to be the source_sha256 of the stage's result file, every transcript to report a model id, and every
reported id to be the model the facts declare (session_model_at_run or session_last_served_model_at_run, a bracketed
suffix such as [1m] disregarded), so the results cannot be sealed under a model their own transcripts contradict;
record_run.py matches the transcripts to the journal's started agents, so that evidence is every agent's. The
copied journals under workflows/ are required outputs whose hashes must be the run records', and each result file's
protocol_sha256 (from the agent labels) must be the frozen protocol's; a PROTOCOL.md changed since the first
manifest refuses every write except --reset, which starts a new run (Codex review of PR #52).

Both plans must have been built from the files on disk: calls.json from the seed file, the design file and the
generation template, and checker_batches.json from the checker template, the seed file and the parsed generation
rows; a stale plan is refused with or without --reset. `finalize` requires every output of a complete run (the fixed
list below, one generated/<call>.jsonl per planned call, one raw file per logged attempt), no file under generated/
that belongs to no planned call, a checked.jsonl that is the parse of the checker plan on disk, a review bundle that
samples it, a summary.json whose recorded input and script hashes match the files and code on disk (with
summary.md its recorded rendering), and every derived file equal to what the current code derives again from the two
recorded result files. A plan-time
rewrite of a finalized manifest keeps finalized_utc and output_hashes only while every hashed output and every
script hash is unchanged; otherwise both are cleared and the message says to finalize again (Codex review of PR #52).
"""
from __future__ import annotations

import datetime as dt
import json
import platform
import re
import sys

import compute_summary
import make_workflow_scripts
from common import (
    ARMS,
    CHECKER_BATCH,
    CONTROLS_PER_CALL,
    K_EXEMPLARS,
    LEGACY_UNBOUND_SOURCES,
    MASTER_SEED,
    N_BOOT,
    N_BROKEN,
    N_KNOWN_GOOD,
    N_REVIEW,
    PILOT,
    ROWS_PER_CALL,
    SPECIALTIES,
    SWAP_TYPES,
    checked_problems,
    generation_problems,
    legacy_protocol_problems,
    load_calls,
    load_checker_batches,
    read_csv,
    read_jsonl,
    review_problems,
    script_hashes,
    sha256_file,
    sha256_text,
    summary_problems,
)
from rederive import rederive_problems

INPUT_HASH_KEYS = ("seeds_json_sha256", "design_json_sha256")
TEMPLATE_KEYS = ("generation_prompt_template", "checker_prompt_template")
# every output of a complete run, before the per-call files; finalize refuses while any is missing
REQUIRED_OUTPUTS = ("calls.json", "workflow_generation_result.json", "workflow_checker_result.json", "call_log.jsonl",
                    "generated/all_rows.jsonl", "generated/format_failures.jsonl",
                    "checker_set.jsonl", "checker_key.jsonl", "checker_batches.json", "checked.jsonl",
                    "checker_log.jsonl", "review_sheet.csv", "review_key.csv", "review_map.json", "summary.json",
                    "summary.md", "seeds.json", "design.json", "PROTOCOL.md", "HANDOFF.md", "manifest_model.json",
                    # the copied journals and the scripts that ran: the record of how the run was produced, compared
                    # with the run records
                    "workflows/generation.journal.jsonl", "workflows/checker.journal.jsonl",
                    "workflows/generation.workflow.js", "workflows/checker.workflow.js")


def seed_provenance() -> dict:
    """The provenance the seed file itself states: the distinct `provenance` values across its seeds (a seed without
    one is reported as MISSING, never assumed) and the file's own note."""
    data = json.loads((PILOT / "seeds.json").read_text(encoding="utf-8"))
    values = sorted({s.get("provenance", "MISSING") for s in data["seeds"]})
    return {"values": values, "n_seeds_without_provenance": sum(1 for s in data["seeds"] if "provenance" not in s),
            "file_note": data.get("_note")}


def input_changes(old: dict, current: dict) -> list[str]:
    """Which planned inputs differ from the manifest on disk: the seed and design file hashes, and the prompt
    templates (compared only when both manifests know them)."""
    changes = [k for k in INPUT_HASH_KEYS if old.get(k) != current.get(k)]
    op, cp = old.get("prompt_hashes", {}), current.get("prompt_hashes", {})
    changes += [f"prompt_hashes.{k}" for k in TEMPLATE_KEYS if k in op and k in cp and op[k] != cp[k]]
    # the model facts are frozen from the first manifest that recorded their hash (Codex review of PR #52)
    if "manifest_model_sha256" in old and old["manifest_model_sha256"] != current.get("manifest_model_sha256"):
        changes.append("manifest_model_sha256")
    return changes


MODEL_KEYS = ("session_model_at_run", "session_last_served_model_at_run")


def model_id(s: str) -> str:
    """A model id with a bracketed context suffix (claude-x[1m]) dropped, for comparing the declared model with the
    ids the transcripts report."""
    return re.sub(r"\[[^\]]*\]$", "", s.strip())


def run_problems(model: dict, runs: dict, protocol_sha256: str) -> list[str]:
    """Why the run records do not vouch for the recorded results (Codex review of PR #52): a stage not recorded; a
    record whose journal_sha256 is not the source_sha256 of the stage's result file (the record describes another
    run); a copied journal under workflows/ missing or not the recorded one; a result file whose protocol_sha256
    (from the agent labels) is not the frozen protocol, unless it is one of the recorded run's legacy results, which
    are sealed only under the protocol they ran under (LEGACY_PROTOCOL_SHA256, so a protocol rewritten and
    re-baselined with --reset cannot be finalized over them); a
    record from before the transcripts were matched to the journal's agents, or one in which a started agent's
    transcript reports no model id; or a reported model id that is not the model the model facts declare
    (MODEL_KEYS, a bracketed suffix disregarded). Empty when both records bind and agree."""
    problems = []
    declared = {model_id(model[k]) for k in MODEL_KEYS if isinstance(model.get(k), str) and model[k].strip()}
    if not isinstance(model.get("session_model_at_run"), str) or not model["session_model_at_run"].strip():
        problems.append("manifest_model.json declares no session_model_at_run to reconcile the transcripts against")
    for stage in ("generation", "checker"):
        rec = runs.get(stage)
        if not isinstance(rec, dict) or not rec.get("run_id"):
            problems.append(f"runs.{stage} not recorded; run record_run.py for it (a --reset clears the run records)")
            continue
        result_path = PILOT / f"workflow_{stage}_result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        source, stamp = result.get("source_sha256"), result.get("protocol_sha256")
        if not rec.get("journal_sha256") or rec.get("journal_sha256") != source:
            problems.append(f"runs.{stage}.journal_sha256 {str(rec.get('journal_sha256'))[:12]!r} is not the "
                            f"source_sha256 of {result_path.name} ({str(source)[:12]!r}); record the run that produced "
                            f"the recorded result")
        copy = PILOT / "workflows" / f"{stage}.journal.jsonl"
        if not copy.exists() or sha256_file(copy) != rec.get("journal_sha256"):
            problems.append(f"workflows/{stage}.journal.jsonl is missing or is not the journal runs.{stage} records; "
                            f"copy the run's journal.jsonl there")
        script = PILOT / "workflows" / f"{stage}.workflow.js"
        if not rec.get("workflow_script_sha256"):
            problems.append(f"runs.{stage}: recorded before the workflow script was bound; run record_run.py --replace")
        elif not script.exists() or sha256_file(script) != rec["workflow_script_sha256"]:
            problems.append(f"workflows/{stage}.workflow.js is missing or is not the script runs.{stage} recorded")
        elif source not in LEGACY_UNBOUND_SOURCES:
            # the script is a function of the plan and the frozen protocol: rendered again, it must be the file that
            # ran; the recorded run's scripts predate the label form and stand as the record of what ran
            try:
                rendered, _ = make_workflow_scripts.render(stage)
            except SystemExit as e:
                rendered = None
                problems.append(f"workflows/{stage}.workflow.js cannot be rendered again from the plan: {e}")
            if rendered is not None and script.read_text(encoding="utf-8") != rendered:
                problems.append(f"workflows/{stage}.workflow.js is not what the current code renders from the plan "
                                f"and the frozen protocol")
        if stamp is None and source in LEGACY_UNBOUND_SOURCES:  # the recorded run's: only under its own protocol
            problems += [f"{result_path.name}: {p}" for p in legacy_protocol_problems(result, protocol_sha256)]
        elif stamp != protocol_sha256:
            problems.append(f"{result_path.name}: protocol_sha256 {str(stamp)[:12]!r} is not the frozen protocol "
                            f"({protocol_sha256[:12]}); the responses were produced under another protocol")
        seen = (rec.get("model_evidence") or {}).get("model_strings_in_transcripts") or {}
        without = rec.get("agents_without_model_id")
        if not isinstance(without, list):
            problems.append(f"runs.{stage}: recorded before the transcripts were matched to the journal's agents; "
                            f"run record_run.py --replace for it")
        elif without or not seen:
            problems.append(f"runs.{stage}: {len(without) or 'the'} agent transcript(s) report no model id "
                            f"({without[:3]}); the results cannot be attributed")
        elif declared:
            foreign = sorted(mid for mid in seen if model_id(mid) not in declared)
            if foreign:
                problems.append(f"runs.{stage}: transcripts report model(s) {foreign} but manifest_model.json declares "
                                f"{sorted(declared)}; record the model that served the run before finalizing")
    return problems


def summary_recompute_problems() -> list[str]:
    """summary.json and summary.md compared with a fresh computation from the files on disk (compute_summary.compute),
    not with the hashes the summary itself declares: a value edited in summary.json under unchanged hashes was sealed
    (Codex review of PR #52). Empty when both are what the current code computes now."""
    try:
        s_now, md_now = compute_summary.compute()
    except SystemExit as e:
        return [f"the summary no longer computes from the files on disk: {e}"]
    s_now["summary_md_sha256"] = sha256_text(md_now)
    problems = []
    if json.loads((PILOT / "summary.json").read_text(encoding="utf-8")) != json.loads(json.dumps(s_now)):
        problems.append("summary.json is not what compute_summary.py computes from the files on disk now")
    if (PILOT / "summary.md").read_text(encoding="utf-8") != md_now:
        problems.append("summary.md is not what compute_summary.py renders from the files on disk now")
    return problems


def finalize_hashes(calls: dict) -> dict[str, str]:
    """Hashes of every output of a complete run. Every expected file must exist, nothing unexpected may sit under
    generated/, and checked.jsonl must be the parse of the checker plan on disk; a manifest finalized over a missing
    or foreign artifact would claim a complete bundle (Codex review of PR #52)."""
    expected = list(REQUIRED_OUTPUTS)
    missing = [o for o in expected if not (PILOT / o).exists()]
    if missing:
        raise SystemExit(f"write_manifest: cannot finalize, {len(missing)} required output(s) missing: "
                         f"{', '.join(missing)}; run the steps that write them first")
    expected += [f"generated/{c['id']}.jsonl" for c in calls["calls"]]
    expected += [f"generated/raw/{e['call_id']}__attempt{e['attempt']}.txt"
                 for e in read_jsonl(PILOT / "call_log.jsonl") if e.get("attempt", 0) >= 1]
    missing = [o for o in expected if not (PILOT / o).exists()]
    if missing:
        raise SystemExit(f"write_manifest: cannot finalize, {len(missing)} per-call output(s) missing (first: "
                         f"{missing[0]}); re-run parse_generation.py on the complete result")
    present = ({f"generated/{p.name}" for p in (PILOT / "generated").glob("*.jsonl")}
               | {f"generated/raw/{p.name}" for p in (PILOT / "generated" / "raw").glob("*.txt")})
    unexpected = sorted(present - set(expected))
    if unexpected:
        raise SystemExit(f"write_manifest: cannot finalize, {len(unexpected)} file(s) under generated/ belong to no "
                         f"planned call or logged attempt (first: {unexpected[0]}); parse_generation.py --replace "
                         f"clears a previous parse")
    call_log = read_jsonl(PILOT / "call_log.jsonl")
    all_rows = read_jsonl(PILOT / "generated" / "all_rows.jsonl")
    problems = generation_problems(calls, call_log, all_rows, read_jsonl(PILOT / "generated" / "format_failures.jsonl"))
    for c in calls["calls"]:  # each per-call file holds exactly its call's rows from all_rows.jsonl
        if read_jsonl(PILOT / "generated" / f"{c['id']}.jsonl") != [r for r in all_rows if r.get("call_id") == c["id"]]:
            problems.append(f"generated/{c['id']}.jsonl differs from the rows for {c['id']} in generated/all_rows.jsonl")
    if problems:
        raise SystemExit("write_manifest: cannot finalize, call_log.jsonl and generated/all_rows.jsonl are not the "
                         "parse of the call plan on disk:\n  " + "\n  ".join(problems[:5]))
    checked = read_jsonl(PILOT / "checked.jsonl")
    plan_sha = sha256_file(PILOT / "checker_batches.json")
    problems = checked_problems(checked, read_jsonl(PILOT / "checker_key.jsonl"),
                                read_jsonl(PILOT / "checker_set.jsonl"), plan_sha)
    if problems:
        raise SystemExit("write_manifest: cannot finalize, checked.jsonl is not the parse of the checker plan on "
                         "disk:\n  " + "\n  ".join(problems[:5]))
    problems = review_problems(json.loads((PILOT / "review_map.json").read_text(encoding="utf-8")),
                               read_csv(PILOT / "review_sheet.csv"), read_csv(PILOT / "review_key.csv"), checked,
                               plan_sha)
    if problems:
        raise SystemExit("write_manifest: cannot finalize, the review bundle does not sample the checked rows on "
                         "disk:\n  " + "\n  ".join(problems[:5]))
    problems = summary_problems(json.loads((PILOT / "summary.json").read_text(encoding="utf-8")))
    if problems:
        raise SystemExit("write_manifest: cannot finalize, summary.json was not computed from the files on disk or "
                         "under the current code; re-run compute_summary.py:\n  " + "\n  ".join(problems[:5]))
    problems = rederive_problems(calls)
    if problems:
        raise SystemExit("write_manifest: cannot finalize, the bundle does not reproduce from its recorded result "
                         "files under the current code; re-run the chain from parse_generation.py:\n  "
                         + "\n  ".join(problems[:5]))
    problems = summary_recompute_problems()  # the numbers themselves, computed again (Codex review of PR #52)
    if problems:
        raise SystemExit("write_manifest: cannot finalize, the summary on disk is not what the current code computes "
                         "from the files on disk; re-run compute_summary.py:\n  " + "\n  ".join(problems[:5]))
    return {o: sha256_file(PILOT / o) for o in expected}


def main(finalize: bool, reset: bool = False) -> None:
    path = PILOT / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model = json.loads((PILOT / "manifest_model.json").read_text(encoding="utf-8"))
    calls = load_calls()  # every prompt verified against its stored hash
    protocol_now = sha256_file(PILOT / "PROTOCOL.md")
    current = {"seeds_json_sha256": sha256_file(PILOT / "seeds.json"),
               "design_json_sha256": sha256_file(PILOT / "design.json"),
               "manifest_model_sha256": sha256_file(PILOT / "manifest_model.json"),
               "prompt_hashes": {"generation_prompt_template": calls["generation_prompt_template_sha256"]}}
    cb = PILOT / "checker_batches.json"
    cbdata = load_checker_batches() if cb.exists() else None
    # both plans must have been rendered from the inputs on disk: a changed seed or design file with a stale
    # calls.json would pair new input hashes with old prompts, and a checker template edited after batching, or a
    # re-parsed generation, would be recorded under a stale checker plan's hashes (Codex review of PR #52)
    planned = calls.get("input_hashes")
    if not isinstance(planned, dict):
        raise SystemExit("write_manifest: calls.json records no input_hashes; re-run plan_calls.py so the plan is "
                         "bound to its inputs")
    template_now = sha256_text((PILOT / "prompts" / "generation_prompt.txt").read_text(encoding="utf-8"))
    stale = [k for k in INPUT_HASH_KEYS if planned.get(k) != current[k]]
    if planned.get("generation_prompt_template_sha256") != template_now:
        stale.append("generation_prompt_template_sha256")
    if stale:
        raise SystemExit(f"write_manifest: calls.json was planned from different inputs ({', '.join(stale)} changed "
                         f"since plan_calls.py ran); re-run plan_calls.py before writing the manifest")
    if cbdata:
        cplanned = cbdata.get("input_hashes")
        if not isinstance(cplanned, dict):
            raise SystemExit("write_manifest: checker_batches.json records no input_hashes; re-run "
                             "build_checker_set.py so the checker plan is bound to its inputs")
        all_rows = PILOT / "generated" / "all_rows.jsonl"
        clive = {"checker_prompt_template_sha256":
                 sha256_text((PILOT / "prompts" / "checker_prompt.txt").read_text(encoding="utf-8")),
                 "seeds_json_sha256": current["seeds_json_sha256"],
                 "all_rows_jsonl_sha256": sha256_file(all_rows) if all_rows.exists() else None}
        cstale = [k for k, v in clive.items() if cplanned.get(k) != v]
        if cstale:
            raise SystemExit(f"write_manifest: checker_batches.json was built from different inputs "
                             f"({', '.join(cstale)} changed since build_checker_set.py ran); rebuild the checker set "
                             f"after the new generation, or move the stale plan aside for a plan-time manifest")
        current["prompt_hashes"]["checker_prompt_template"] = clive["checker_prompt_template_sha256"]
    # the protocol is frozen from the first manifest: a later change invalidates the run rather than being sealed as
    # "protocol_unchanged: false" (Codex review of PR #52); --reset re-baselines it for a new run, whose results
    # must then carry the new hash in their labels
    if old and not reset and old.get("protocol_sha256_at_write") not in (None, protocol_now):
        raise SystemExit(f"write_manifest: PROTOCOL.md changed since the manifest first recorded it "
                         f"({old['protocol_sha256_at_write'][:12]} then, {protocol_now[:12]} now); the protocol is frozen "
                         f"and a change invalidates the run: restore it, or start a new run in a fresh directory")
    changes = input_changes(old, current) if old else []
    if changes and not reset:
        raise SystemExit(f"write_manifest: {', '.join(changes)} changed since manifest.json was written (created "
                         f"{old.get('created_utc')}, runs {sorted(old.get('runs', {}))}); a rerun with new inputs must "
                         f"not keep the previous run's timestamps and run records: pass --reset to start fresh metadata")
    base = {} if (reset or not old) else old  # the metadata carried forward, none after a reset
    # a plan-time rewrite after finalize keeps the finalization time and the output hashes only while every hashed
    # output is unchanged on disk; a finalization time without the hashes it vouched for would claim a verified
    # bundle (Codex review of PR #52)
    scripts_now = script_hashes()  # the executing scripts, wherever the run directory is (Codex review of PR #52)
    workflows_now = ({p.name: sha256_file(p) for p in sorted((PILOT / "workflows").glob("*.js"))}
                     if (PILOT / "workflows").exists() else {})
    carried = base.get("output_hashes") if not finalize else None
    changed_outputs = ([o for o, h in carried.items() if not (PILOT / o).exists() or sha256_file(PILOT / o) != h]
                       if carried else [])
    # a finalized manifest also names the code its outputs stand under: a script edited since finalize clears the
    # finalization too, or the rewrite would attribute the outputs to code that never produced them (Codex review
    # of PR #52)
    changed_scripts = ([n for n in sorted(set(base.get("script_hashes", {})) | set(scripts_now))
                        if base.get("script_hashes", {}).get(n) != scripts_now.get(n)]
                       + [n for n in sorted(set(base.get("workflow_script_hashes", {})) | set(workflows_now))
                          if base.get("workflow_script_hashes", {}).get(n) != workflows_now.get(n)]) if carried else []
    keep_final = bool(carried) and not changed_outputs and not changed_scripts
    m = {
        "pilot": "stimulus-generation measurement-validity pilot",
        "date_utc": base.get("date_utc", now[:10]),
        "created_utc": base.get("created_utc", now),
        "finalized_utc": now if finalize else (base.get("finalized_utc") if keep_final else None),
        "metadata_reset_utc": now if (reset and old) else base.get("metadata_reset_utc"),
        "model": model,
        "manifest_model_sha256": current["manifest_model_sha256"],
        "python": platform.python_version(),
        "seeds": {"master_seed": MASTER_SEED, "exemplar_sampling": "random.Random(20260929), one draw of K per cell in cell order",
                  "named_streams": {p: f"random.Random('{MASTER_SEED}:{p}')" for p in ("broken", "checker_shuffle", "review", "bootstrap")}},
        "design": {"specialties": SPECIALTIES, "swap_types": SWAP_TYPES, "arms": ARMS, "rows_per_call": ROWS_PER_CALL,
                   "controls_per_call": CONTROLS_PER_CALL, "k_exemplars_requested": K_EXEMPLARS,
                   "k_exemplars_used": calls["k_exemplars_used"], "n_seed_cases": calls["n_seeds"],
                   # read from the seed file in use, never fixed here: a rerun with real seeds must record theirs
                   "seed_provenance": seed_provenance(),
                   "checker_batch": CHECKER_BATCH, "n_broken": N_BROKEN, "n_known_good_requested": N_KNOWN_GOOD,
                   "n_review": N_REVIEW, "n_boot": N_BOOT},
        "protocol_sha256_at_write": base.get("protocol_sha256_at_write", protocol_now),
        "protocol_sha256_now": protocol_now,
        "protocol_unchanged": base.get("protocol_sha256_at_write", protocol_now) == protocol_now,
        "seeds_json_sha256": current["seeds_json_sha256"],
        "design_json_sha256": current["design_json_sha256"],
        "prompt_hashes": {
            "generation_prompt_template": calls["generation_prompt_template_sha256"],
            "generation_calls": {c["id"]: {"prompt_sha256": c["prompt_sha256"], "exemplar_ids": c["exemplar_ids"]} for c in calls["calls"]},
        },
        "script_hashes": scripts_now,
        "workflow_script_hashes": workflows_now,
    }
    if cbdata:
        # the value checked against the live template above, not the plan file's own copy of it
        m["prompt_hashes"]["checker_prompt_template"] = current["prompt_hashes"]["checker_prompt_template"]
        m["prompt_hashes"]["checker_batches"] = {x["batch_id"]: x["prompt_sha256"] for x in cbdata["batches"]}
    m["runs"] = base.get("runs", {})
    if keep_final:
        m["output_hashes"] = carried
    if finalize:
        # the run records carry the model evidence read from the transcripts and the journal each result came
        # from; without both, bound to the result files and agreeing with the declared model, the model facts
        # above would stand alone (Codex review of PR #52); a --reset clears them so they are recorded again
        problems = run_problems(model, m["runs"], protocol_now)
        if problems:
            raise SystemExit("write_manifest: cannot finalize, the run records do not vouch for the recorded "
                             "results:\n  " + "\n  ".join(problems[:5]))
        m["output_hashes"] = finalize_hashes(calls)  # refuses an incomplete bundle before anything is written
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cleared = ([f"{len(changed_outputs)} hashed output(s) changed or missing (first: {changed_outputs[0]})"]
               if changed_outputs else []) + ([f"{len(changed_scripts)} script(s) changed (first: {changed_scripts[0]})"]
                                             if changed_scripts else [])
    note = f"; finalization cleared: {' and '.join(cleared)} since finalize, re-run write_manifest.py finalize" if cleared else ""
    print(f"manifest.json written ({'finalized' if finalize else 'planned'}"
          f"{', metadata reset' if (reset and old) else ''}){note}; protocol unchanged: {m['protocol_unchanged']}")


if __name__ == "__main__":
    main(finalize="finalize" in sys.argv[1:], reset="--reset" in sys.argv[1:])
