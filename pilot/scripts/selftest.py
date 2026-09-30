"""Self-test: known-value checks of the interval and TF-IDF helpers, the 8-of-N exemplar sampling path, and an
end-to-end dry run of every script on fabricated responses inside a temporary copy of the pilot directory.

Run: python3 scripts/selftest.py. It never touches the real pilot outputs.
"""
from __future__ import annotations

import importlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
common = importlib.import_module("common")  # the scripts import each other by bare name


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def unit_tests() -> None:
    w = common.wilson(7, 10)
    check(abs(w["p"] - 0.7) < 1e-12 and abs(w["lo"] - 0.3968) < 5e-4 and abs(w["hi"] - 0.8922) < 5e-4,
          f"wilson(7,10) = {w['lo']:.4f}..{w['hi']:.4f} (reference 0.3968..0.8922)")
    check(common.wilson(0, 0)["p"] is None, "wilson(0,0) is undefined, not an error")
    d = common.newcombe_diff(56, 70, 48, 80)
    check(abs(d["diff"] - 0.2) < 1e-12 and abs(d["lo"] - 0.0524) < 2e-3 and abs(d["hi"] - 0.3339) < 2e-3,
          f"newcombe(56/70 vs 48/80) = {d['diff']:.3f} [{d['lo']:.4f}, {d['hi']:.4f}] (reference 0.0524..0.3339)")
    tf = common.Tfidf(["the patient has ___ today", "the patient has ___ today", "unrelated words here"])
    a, b, c = (tf.vector(x) for x in ["the patient has ___ today", "the patient has ___ today", "unrelated words here"])
    check(abs(common.cosine(a, b) - 1.0) < 1e-12 and common.cosine(a, c) == 0.0, "tfidf cosine: identical 1, disjoint 0")
    check("___" not in tf.idf, "blank marker is not a token")
    check(tf.vector("___") is None and tf.vector("a") is None, "a template with no TF-IDF token yields no vector, not zeros")
    m, pairs = common.mean_pairwise([a, b, c])
    check(pairs == 3 and abs(m - 1 / 3) < 1e-12, "mean pairwise over 3 vectors uses 3 pairs")
    dummies = [{"id": f"d{i}"} for i in range(12)]
    r1, r2 = random.Random(common.MASTER_SEED), random.Random(common.MASTER_SEED)
    s1, s2 = r1.sample(dummies, 8), r2.sample(dummies, 8)
    check(len(s1) == 8 and len({d["id"] for d in s1}) == 8 and s1 == s2, "8 of 12 sampled without replacement, deterministic")
    # the example negative control the generation prompt shows comes from design.json, rendered as one JSON object and
    # refused unless it is a negative control of the required shape (Codex on PR #52)
    good = dict(common.DESIGN["control_example"])
    check(common.control_example_text({"control_example": good}) == json.dumps(good, ensure_ascii=False),
          "the control example renders from design.json as one compact JSON object")
    for label, bad in (("missing", None),
                       ("in another key order", {"patient_term": good["patient_term"], "clinical_term": good["clinical_term"],
                                                 "template": good["template"], "control": "negative"}),
                       ("not marked negative", dict(good, control="none")),
                       ("without a blank", dict(good, template="no blank here")),
                       ("two concepts", dict(good, patient_term=good["patient_term"] + " and more"))):
        try:
            common.control_example_text({"control_example": bad})
            refused = False
        except SystemExit:
            refused = True
        check(refused, f"a control example that is {label} is refused before planning")
    row, reason = common.validate_line('{"clinical_term": "a", "patient_term": "b", "template": "x ___ y", "control": "none"}')
    check(row is not None and reason == "ok", "valid line validates")
    check(common.validate_line('{"clinical_term": "a", "patient_term": "b", "template": "x y", "control": "none"}')[1]
          == "template_blank_count_not_1", "template without a blank is a format failure")
    check(common.validate_line('{"clinical_term": "a", "patient_term": "b", "template": "x ___ y"}')[1]
          == "missing_field:control", "missing control is a format failure")
    check(common.validate_line("```json")[1] == "not_json", "a fence line is a format failure")
    keyed = '{"clinical_term": "a", "patient_term": "b", "template": "no blank", "control": "none"}'
    check(common.attempt_failed(None) and common.attempt_failed("Sorry, prose only")
          and not common.attempt_failed("prose\n" + keyed),
          "generation retry rule: an empty response or one with no line carrying the keys fails; a keyed line does not")
    check(common.checker_attempt_failed(None) and common.checker_attempt_failed({"verdicts": []})
          and not common.checker_attempt_failed({"verdicts": [{"id": "c1", "equivalent": "yes", "reason": ""}]}),
          "checker retry rule: nothing or an empty verdict list fails; a verdict list does not")
    check(common.control_is_faithful({"clinical_term": "Alpha beta", "patient_term": "alpha  beta."}), "control fidelity")
    # two terms of punctuation alone both normalize to "": no lexical content to compare, never faithful (Codex on PR #52)
    check(not common.control_measurable({"clinical_term": "...", "patient_term": "??"})
          and not common.control_is_faithful({"clinical_term": "...", "patient_term": "??"})
          and common.control_measurable({"clinical_term": "a.", "patient_term": "A"}),
          "a control whose term keeps no letter or digit is unmeasurable, not faithful")
    check(len(common.SPECIALTIES) == 3 and len(common.SWAP_DEFINITIONS) == 3, "design factors load from design.json")
    # surface form: casing, punctuation and spacing removed, letters of every script kept (Codex on PR #52)
    check(common.surface_key("Résumé, naïve") == "résuménaïve"
          and common.surface_key("Слово, второе") == "слововторое"
          and common.surface_key("Alpha beta") == common.surface_key("alpha  beta."),
          "surface_key keeps letters of every script and removes only casing, punctuation and spacing")
    # the seed contract is checked before any plan (Codex on PR #52)
    good_seed = {"id": "s1", "clinical_term": "a", "patient_term": "b", "template": "x ___ y", "specialty": "s",
                 "swap_type": "t"}
    check(common.validate_seeds({"seeds": [good_seed]})[0]["id"] == "s1", "a well-formed seed file validates")
    for bad, label in (({"seeds": [good_seed, dict(good_seed)]}, "duplicate id"),
                       ({"seeds": [dict(good_seed, template="x y")]}, "template without a blank"),
                       ({"seeds": [dict(good_seed, patient_term=" ")]}, "blank patient_term"),
                       ({"seeds": []}, "empty seed list")):
        try:
            common.validate_seeds(bad)
            refused = False
        except SystemExit:
            refused = True
        check(refused, f"seed file with a {label} is refused")
    bar = importlib.import_module("build_api_requests")
    verdict = bar.RESULT_SHAPES["checker"]["shape"]["batches"][0]["attempts"][0]["result"]["verdicts"][0]
    check(set(verdict) == {"id", "equivalent", "reason"}, "checker result contract shows verdict objects")
    # broken pairs: targets come only from rows that have a donor (Codex on PR #52); with (A,X), (A,Y), (B,X) the
    # row (A,X) has none, while (A,Y) and (B,X) can be re-paired with each other
    bcs = importlib.import_module("build_checker_set")
    rows = [{"id": "ax", "clinical_term": "A", "patient_term": "X"}, {"id": "ay", "clinical_term": "A", "patient_term": "Y"},
            {"id": "bx", "clinical_term": "B", "patient_term": "X"}]
    elig = bcs.eligible_targets(rows)
    check(set(elig) == {"ay", "bx"} and [d["id"] for d in elig["ay"]] == ["bx"] and [d["id"] for d in elig["bx"]] == ["ay"],
          "eligible broken-pair targets exclude the row with no donor")
    # bootstrap: a two-row cell resamples to copies of one row in about half the replicates; the replicate is then
    # undefined and counted, and the cell set stays fixed (Codex on PR #52)
    cs = importlib.import_module("compute_summary")
    tf = common.Tfidf(["one ___ two", "three ___ four", "five ___ six"])
    v1, v2, v3 = (tf.vector(x) for x in ["one ___ two", "three ___ four", "five ___ six"])
    boot = cs.bootstrap_diversity({"A": {"c1": [v1, v2], "c2": [v1, v2, v3]}, "B": {"c1": [v1, v3], "c2": [v2, v3, v1]}},
                                  [v1], random.Random(3), 200)
    check(boot["fixed_cells"] == {"A": ["c1", "c2"], "B": ["c1", "c2"]}, "bootstrap cell set is the fixed set")
    check(boot["n_undefined"]["A"] > 0 and len(boot["boot"]["A"]) + boot["n_undefined"]["A"] == 200,
          f"undefined replicates are skipped and counted ({boot['n_undefined']['A']} of 200 for arm A)")
    check(len(boot["boot_diff"]) + boot["n_undefined_diff"] == 200, "difference replicates account for every draw")


def fake_response(call: dict, r: random.Random, broken_first: bool) -> list[dict]:
    if broken_first:
        return [{"attempt": 1, "raw": "Sorry, here is some prose and no JSON.", "null_return": False},
                {"attempt": 2, "raw": fake_rows(call, r), "null_return": False}]
    return [{"attempt": 1, "raw": fake_rows(call, r), "null_return": False}]


def fake_rows(call: dict, r: random.Random) -> str:
    lines = []
    for i in range(16):
        w = f"{call['cell']}_{r.randrange(1000)}"
        lines.append(json.dumps({"clinical_term": f"clin {w} {i}", "patient_term": f"lay {w} {i}",
                                 "template": f"The patient mentions ___ during the visit {r.randrange(50)}, and",
                                 "control": "none"}))
    for i in range(4):
        lines.append(json.dumps({"clinical_term": f"Concept {i}", "patient_term": f"concept {i}.",
                                 "template": "She describes ___ at night, and", "control": "negative"}))
    if call["arm"] == "A" and call["specialty"] == common.SPECIALTIES[1]:  # the specialty name stays in design.json
        lines.append('{"clinical_term": "x", "patient_term": "y", "template": "no blank here", "control": "none"}')
        lines.append("not json at all")
        # format-valid, but neither term keeps a letter or digit: counted as unmeasurable, not faithful
        lines.append('{"clinical_term": "...", "patient_term": "??", "template": "She points to ___ and", "control": "negative"}')
    return "\n".join(lines)


def dry_run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pilot_selftest_"))
    try:
        for name in ("seeds.json", "design.json", "manifest_model.json", "PROTOCOL.md", "HANDOFF.md", "prompts"):
            src = HERE.parent / name
            (shutil.copytree if src.is_dir() else shutil.copy)(src, tmp / name)
        # the temporary seed file states its own provenance; the summary and the manifest must repeat it, not the
        # original run's label (Codex on PR #52)
        seeds_doc = json.loads((tmp / "seeds.json").read_text(encoding="utf-8"))
        for sd in seeds_doc["seeds"]:
            sd["provenance"] = "selftest provenance, not study data"
        (tmp / "seeds.json").write_text(json.dumps(seeds_doc, ensure_ascii=False), encoding="utf-8")
        # a run writes its own protocol and handoff before planning (Codex on PR #52); the dry run's say what they are
        proto = (tmp / "PROTOCOL.md").read_text(encoding="utf-8")
        (tmp / "PROTOCOL.md").write_text("# Dry run of scripts/selftest.py\n\nFabricated responses in a temporary "
                                         "directory; the recorded protocol follows for the script contract.\n\n" + proto,
                                         encoding="utf-8")
        (tmp / "HANDOFF.md").write_text("# Self-test dry run\n\nFabricated responses; no assumptions, results or review "
                                        "rounds are recorded here.\n\n<!-- results:begin -->\n<!-- results:end -->\n",
                                        encoding="utf-8")
        # the model facts must name the model the fabricated transcripts report, or finalize refuses (Codex on PR #52)
        model_path = tmp / "manifest_model.json"
        model_doc = json.loads(model_path.read_text(encoding="utf-8"))
        model_doc["session_model_at_run"] = "selftest-model[test]"  # the bracketed suffix is disregarded
        model_doc["session_last_served_model_at_run"] = "selftest-model"
        model_path.write_text(json.dumps(model_doc, indent=2) + "\n", encoding="utf-8")
        # transcript fixtures, named by run id as the Workflow tool names them; each result file records the hash of
        # the journal it was extracted from, and record_run.py binds the record to it (Codex on PR #52)
        gdir, cdir, odir = tmp / "wf_selftest_gen", tmp / "wf_selftest_chk", tmp / "wf_selftest_other"
        for d in (gdir, cdir, odir):
            d.mkdir()
        # another run's journal, for the refusal checks: its hash is no result file's source
        (odir / "journal.jsonl").write_text('{"type": "launched"}\n{"type": "started", "key": "k1", "agentId": "a1", '
                                            '"label": "other 1"}\n', encoding="utf-8")
        (odir / "agent-a1.jsonl").write_text('{"model":"selftest-model"}\n', encoding="utf-8")
        proto = common.sha256_file(tmp / "PROTOCOL.md")  # the frozen protocol's hash, as the agent labels carry it
        env = {**os.environ, "PILOT_DIR": str(tmp)}

        last_err = [""]  # the last script's stderr, so a check can name the refusal that fired

        def run(script: str, *args: str, expect_failure: bool = False) -> str:
            out = subprocess.run([sys.executable, str(HERE / script), *args], env=env, capture_output=True, text=True,
                                 check=False)
            last_err[0] = out.stderr
            check((out.returncode != 0) if expect_failure else (out.returncode == 0),
                  f"{script} {' '.join(args)}{' (expected to refuse)' if expect_failure else ''}\n{out.stdout}{out.stderr}")
            return out.stdout
        # a template missing a marker, repeating one, or carrying an unknown one cannot launch an experiment
        # (Codex on PR #52)
        gp = tmp / "prompts" / "generation_prompt.txt"
        gp_text = gp.read_text(encoding="utf-8")
        for bad in (gp_text.replace("{{SPECIALTY}}", ""), gp_text + "\n{{SPECIALTY}}",
                    gp_text.replace("{{SWAP_TYPE}}", "{{SWAP_TYPO}}"), gp_text.replace("{{CONTROL_EXAMPLE}}", "")):
            gp.write_text(bad, encoding="utf-8")
            run("plan_calls.py", expect_failure=True)
        gp.write_text(gp_text, encoding="utf-8")
        check(not (tmp / "calls.json").exists(),
              "a generation template missing, repeating or misspelling a marker is refused before planning")
        # a design file whose control example is not a negative control (two concepts) cannot be planned from
        design_bytes0 = (tmp / "design.json").read_bytes()
        ddoc0 = json.loads(design_bytes0.decode("utf-8"))
        ddoc0["control_example"]["patient_term"] += " and more"
        (tmp / "design.json").write_text(json.dumps(ddoc0, ensure_ascii=False), encoding="utf-8")
        run("plan_calls.py", expect_failure=True)
        (tmp / "design.json").write_bytes(design_bytes0)
        check(not (tmp / "calls.json").exists(), "a design file whose control example is not a negative control is refused")
        run("plan_calls.py")
        # a prompt edited together with its stored hash is self-consistent but not the plan the inputs derive:
        # every reader of calls.json derives the plan again and refuses it (Codex on PR #52)
        plan_bytes = (tmp / "calls.json").read_bytes()
        pdoc = json.loads(plan_bytes.decode("utf-8"))
        pdoc["calls"][0]["prompt"] += "\nEdited after planning."
        pdoc["calls"][0]["prompt_sha256"] = common.sha256_text(pdoc["calls"][0]["prompt"])
        (tmp / "calls.json").write_text(json.dumps(pdoc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run("write_manifest.py", expect_failure=True)
        run("make_workflow_scripts.py", "generation", expect_failure=True)
        (tmp / "calls.json").write_bytes(plan_bytes)
        check(not (tmp / "manifest.json").exists() and not (tmp / "workflows").exists(),
              "a plan edited together with its hashes is refused by every reader before anything is written")
        calls = json.loads((tmp / "calls.json").read_text())["calls"]
        r = random.Random(1)
        # the fabricated run as a journal in the Workflow tool's shape (a started and a result record per attempt,
        # labels carrying the prompt and protocol hashes, a transcript per agent), extracted like a real run's, so
        # the summary and finalize can extract the result again from the copied journal (Codex on PR #52); the
        # last planned call is left out: a planned call with no response record must stay in every denominator
        records = [{"type": "launched"}]
        n_gen_agents = 0
        for c in calls[:-1]:
            for a in fake_response(c, r, broken_first=(c["id"] == calls[3]["id"])):
                n_gen_agents += 1
                key, agent = f"gk{n_gen_agents}", f"g{n_gen_agents:02d}"
                records.append({"type": "started", "key": key, "agentId": agent,
                                "label": f"{c['id']} attempt {a['attempt']} sha256={c['prompt_sha256']} protocol={proto}"})
                records.append({"type": "result", "key": key, "agentId": agent, "result": a["raw"]})
                (gdir / f"agent-{agent}.jsonl").write_text('{"model":"selftest-model"}\n', encoding="utf-8")
        (gdir / "journal.jsonl").write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(gdir / "journal.jsonl"))
        gen = json.loads((tmp / "workflow_generation_result.json").read_text(encoding="utf-8"))
        check(len(gen["calls"]) == 17 and gen["protocol_sha256"] == proto
              and gen["source_sha256"] == common.sha256_file(gdir / "journal.jsonl"),
              "the fabricated journal extracts to 17 calls carrying the protocol and journal hashes")
        (tmp / "workflows").mkdir(exist_ok=True)  # the copy the summary and finalize extract the result from again
        shutil.copy(gdir / "journal.jsonl", tmp / "workflows" / "generation.journal.jsonl")
        keyed_line = '{"clinical_term": "extra", "patient_term": "line", "template": "added ___ later", "control": "none"}'
        run("parse_generation.py", str(tmp / "workflow_generation_result.json"))
        run("parse_generation.py", str(tmp / "workflow_generation_result.json"), expect_failure=True)  # outputs exist: refuse

        def n_outputs() -> int:
            return len(list((tmp / "generated").glob("*.jsonl"))) + len(list((tmp / "generated" / "raw").glob("*.txt")))

        def with_attempts(numbers: list[int]) -> dict:
            first = gen["calls"][0]
            atts = [dict(first["attempts"][0], attempt=n) for n in numbers]
            return {"calls": [dict(first, attempts=atts)] + gen["calls"][1:]}
        # a result file that fails the contract is refused with --replace too, and the previous outputs stay intact
        # (Codex on PR #52): duplicate or unplanned ids, no calls list, repeated or reversed or too many attempt
        # numbers, and a prompt hash that is not the plan's (or none at all)
        before = n_outputs()
        first = gen["calls"][0]
        unhashed = {k: v for k, v in first.items() if k != "prompt_sha256"}
        for label, bad in (("duplicate call id", {"calls": gen["calls"] + [gen["calls"][0]]}),
                           ("unplanned call id", {"calls": gen["calls"] + [dict(gen["calls"][0], id="not_planned")]}),
                           ("no calls list", {"nope": []}),
                           ("repeated attempt number", with_attempts([1, 1])),
                           ("reversed attempt numbers", with_attempts([2, 1])),
                           ("three attempts", with_attempts([1, 2, 3])),
                           ("retry after a valid first attempt", with_attempts([1, 2])),
                           ("foreign prompt hash", {"calls": [dict(first, prompt_sha256="0" * 64)] + gen["calls"][1:]}),
                           ("missing prompt hash", {"calls": [unhashed] + gen["calls"][1:]}),
                           ("foreign protocol hash", {"protocol_sha256": "0" * 64, "calls": gen["calls"]}),
                           ("missing protocol hash", {"protocol_sha256": None, "calls": gen["calls"]})):
            (tmp / "wf_bad.json").write_text(json.dumps({"source_sha256": gen["source_sha256"], "protocol_sha256": proto, **bad}))
            run("parse_generation.py", str(tmp / "wf_bad.json"), "--replace", expect_failure=True)
            check(n_outputs() == before, f"a result with a {label} is refused and leaves the previous outputs intact")
        # --unbound is accepted only for the recorded run's own result files (by source_sha256): a hashless result
        # of any other origin is refused with it, and the recorded run's journal parses only with it (Codex on PR #52)
        (tmp / "wf_unbound.json").write_text(json.dumps({"calls": [unhashed] + gen["calls"][1:]}))
        run("parse_generation.py", str(tmp / "wf_unbound.json"), "--replace", "--unbound", expect_failure=True)
        check(n_outputs() == before, "--unbound on a result that is not the recorded run's is refused")
        fab_bytes = (tmp / "workflow_generation_result.json").read_bytes()
        run("extract_workflow_journal.py", "generation", str(HERE.parent / "workflows" / "generation.journal.jsonl"), "--replace")
        run("parse_generation.py", str(tmp / "workflow_generation_result.json"), "--replace", expect_failure=True)  # no hashes
        # ... and only under the protocol the recorded run ran under: the dry run's protocol is another, so --unbound
        # is refused here too, and accepted once that protocol is on disk (Codex on PR #52)
        run("parse_generation.py", str(tmp / "workflow_generation_result.json"), "--replace", "--unbound", expect_failure=True)
        check(n_outputs() == before and "was produced under protocol" in last_err[0],
              "the recorded run's result is refused with --unbound under a protocol it did not run under")
        dry_proto_bytes = (tmp / "PROTOCOL.md").read_bytes()
        (tmp / "PROTOCOL.md").write_bytes((HERE.parent / "PROTOCOL.md").read_bytes())
        run("parse_generation.py", str(tmp / "workflow_generation_result.json"), "--replace", "--unbound")
        (tmp / "PROTOCOL.md").write_bytes(dry_proto_bytes)
        log = common.read_jsonl(tmp / "call_log.jsonl")
        check(all(e["plan_binding"].startswith("none") for e in log),
              "the recorded run's journal parses only with --unbound and under its own protocol, and the call log says so")
        (tmp / "workflow_generation_result.json").write_bytes(fab_bytes)
        run("parse_generation.py", str(tmp / "workflow_generation_result.json"), "--replace")
        check(all(e["plan_binding"] == "prompt_sha256" for e in common.read_jsonl(tmp / "call_log.jsonl")),
              "a bound parse records the binding in every call log entry")
        by_id = {c["id"]: c for c in calls}
        check(all(e["prompt_sha256"] == by_id[e["call_id"]]["prompt_sha256"] for e in common.read_jsonl(tmp / "call_log.jsonl"))
              and all(r["prompt_sha256"] == by_id[r["call_id"]]["prompt_sha256"]
                      for r in common.read_jsonl(tmp / "generated" / "all_rows.jsonl")),
              "every call log entry and every row carries its planned prompt's hash")
        run("compute_summary.py", expect_failure=True)  # checked.jsonl does not exist yet: refuse, no partial summary
        cp = tmp / "prompts" / "checker_prompt.txt"
        cp_text = cp.read_text(encoding="utf-8")
        cp.write_text(cp_text.replace("{{ITEMS}}", "{{ITEM}}"), encoding="utf-8")
        run("build_checker_set.py", expect_failure=True)
        cp.write_text(cp_text, encoding="utf-8")
        check(not (tmp / "checker_batches.json").exists(), "a checker template without its marker is refused before batching")
        run("build_checker_set.py")
        # a row whose text was edited under intact ids, attempts and prompt hashes passes the structural check; the
        # builder derives the generation again from the copied journal and refuses, and so does every reader of a
        # checker plan built over such rows, before any checker work is emitted (Codex on PR #52)
        cb_files = ("checker_batches.json", "checker_set.jsonl", "checker_key.jsonl")
        cb_bytes = {n: (tmp / n).read_bytes() for n in cb_files}
        rows_bytes = (tmp / "generated" / "all_rows.jsonl").read_bytes()
        edited_rows = common.read_jsonl(tmp / "generated" / "all_rows.jsonl")
        edited_rows[0]["clinical_term"] += " edited after the run"
        common.write_jsonl(tmp / "generated" / "all_rows.jsonl", edited_rows)
        run("build_checker_set.py", expect_failure=True)
        check(all((tmp / n).read_bytes() == cb_bytes[n] for n in cb_files)
              and "all_rows.jsonl is not what the current code derives" in last_err[0],
              "a row edited under intact ids and hashes is refused by the checker-set builder, which writes nothing")
        # the plan derived by hand from the edited rows (build_checker_set.derive is pure) is self-consistent, and
        # every reader of the checker plan still refuses it, since the rows are not the recorded journal's
        bcs = importlib.import_module("build_checker_set")
        blind_e, truth_e, plan_e = bcs.derive(edited_rows, seeds_doc["seeds"], cp_text, common.sha256_file(tmp / "seeds.json"),
                                              common.sha256_file(tmp / "generated" / "all_rows.jsonl"))
        common.write_jsonl(tmp / "checker_set.jsonl", blind_e)
        common.write_jsonl(tmp / "checker_key.jsonl", truth_e)
        (tmp / "checker_batches.json").write_text(json.dumps(plan_e, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run("make_workflow_scripts.py", "checker", expect_failure=True)
        check("all_rows.jsonl is not what the current code derives" in last_err[0], "the workflow-script writer names the rows")
        run("build_api_requests.py", "checker", "--model", "example-model", expect_failure=True)
        check(not (tmp / "workflows" / "checker.workflow.js").exists() and not (tmp / "api_requests_checker.json").exists(),
              "a checker plan built over rows that are not the recorded journal's is refused before any checker work is emitted")
        (tmp / "generated" / "all_rows.jsonl").write_bytes(rows_bytes)
        for n in cb_files:
            (tmp / n).write_bytes(cb_bytes[n])
        # the request builder writes one body per call with the recorded prompt hash, and sends nothing
        run("build_api_requests.py", "generation", "--model", "example-model")
        reqs = json.loads((tmp / "api_requests_generation.json").read_text())["requests"]
        by_id = {c["id"]: c for c in calls}
        check(len(reqs) == 18 and all(x["prompt_sha256"] == by_id[x["id"]]["prompt_sha256"]
                                      and x["request"]["messages"][0]["content"] == by_id[x["id"]]["prompt"]
                                      for x in reqs) and "output_config" not in reqs[0]["request"],
              "api request bodies match calls.json prompts and carry no output schema for generation")
        run("build_api_requests.py", "checker", "--model", "example-model")
        creqs = json.loads((tmp / "api_requests_checker.json").read_text())["requests"]
        check(len(creqs) >= 1 and creqs[0]["request"]["output_config"]["format"]["type"] == "json_schema",
              "checker request bodies carry the verdict schema")
        batches = json.loads((tmp / "checker_batches.json").read_text())["batches"]
        key = {k["id"]: k for k in common.read_jsonl(tmp / "checker_key.jsonl")}
        crecords = [{"type": "launched"}]
        for i, b in enumerate(batches, 1):
            verdicts = []
            for iid in b["item_ids"]:
                src = key[iid]["source"]
                v = "no" if src == "broken" else ("yes" if r.random() < 0.9 else "unclear")
                verdicts.append({"id": iid, "equivalent": v, "reason": "fabricated for the self-test"})
            agent = f"c{i:02d}"
            crecords.append({"type": "started", "key": f"ck{i}", "agentId": agent,
                             "label": f"{b['batch_id']} attempt 1 sha256={b['prompt_sha256']} protocol={proto}"})
            crecords.append({"type": "result", "key": f"ck{i}", "agentId": agent, "result": {"verdicts": verdicts}})
            (cdir / f"agent-{agent}.jsonl").write_text('{"model":"selftest-model"}\n', encoding="utf-8")
        (cdir / "journal.jsonl").write_text("".join(json.dumps(x) + "\n" for x in crecords), encoding="utf-8")
        run("extract_workflow_journal.py", "checker", str(cdir / "journal.jsonl"))
        chk = json.loads((tmp / "workflow_checker_result.json").read_text(encoding="utf-8"))
        shutil.copy(cdir / "journal.jsonl", tmp / "workflows" / "checker.journal.jsonl")
        b0 = chk["batches"][0]
        for label, bad in (("duplicate batch id", {"batches": chk["batches"] + [b0]}),
                           ("repeated attempt number", {"batches": [dict(b0, attempts=b0["attempts"] * 2)] + chk["batches"][1:]}),
                           ("retry after a verdict list", {"batches": [dict(b0, attempts=[b0["attempts"][0], dict(b0["attempts"][0], attempt=2)])]
                                                           + chk["batches"][1:]}),
                           ("foreign prompt hash", {"batches": [dict(b0, prompt_sha256="0" * 64)] + chk["batches"][1:]})):
            (tmp / "wf_chk_bad.json").write_text(json.dumps({"source_sha256": chk["source_sha256"], "protocol_sha256": proto, **bad}))
            run("parse_checker.py", str(tmp / "wf_chk_bad.json"), expect_failure=True)
            check(not (tmp / "checked.jsonl").exists(), f"a checker result with a {label} is refused and writes nothing")
        run("parse_checker.py", str(tmp / "wf_chk_bad.json"), "--unbound", expect_failure=True)
        check(not (tmp / "checked.jsonl").exists(), "--unbound on a checker result that is not the recorded run's is refused")
        run("parse_checker.py", str(tmp / "workflow_checker_result.json"))
        # a previous checker parse is never written over without --replace, and every row carries the plan's hash
        # (Codex on PR #52)
        checked_text = (tmp / "checked.jsonl").read_text(encoding="utf-8")
        run("parse_checker.py", str(tmp / "workflow_checker_result.json"), expect_failure=True)
        check((tmp / "checked.jsonl").read_text(encoding="utf-8") == checked_text,
              "a second checker parse without --replace is refused and leaves checked.jsonl intact")
        run("parse_checker.py", str(tmp / "workflow_checker_result.json"), "--replace")
        plan_sha = common.sha256_file(tmp / "checker_batches.json")
        check((tmp / "checked.jsonl").read_text(encoding="utf-8") == checked_text
              and all(c["checker_plan_sha256"] == plan_sha for c in common.read_jsonl(tmp / "checked.jsonl")),
              "--replace rewrites the same verdicts, each row stamped with the checker plan's hash")
        # a verdict entry whose reason is missing or not text is invalid: counted, its item recorded as missing,
        # never coerced into a string (Codex on PR #52)
        cdoc_r = json.loads((tmp / "workflow_checker_result.json").read_text(encoding="utf-8"))
        first_v = cdoc_r["batches"][0]["attempts"][0]["result"]["verdicts"]
        first_v[0]["reason"] = 42
        del first_v[1]["reason"]
        (tmp / "wf_chk_reason.json").write_text(json.dumps(cdoc_r), encoding="utf-8")
        run("parse_checker.py", str(tmp / "wf_chk_reason.json"), "--replace")
        rows_r = {c["id"]: c for c in common.read_jsonl(tmp / "checked.jsonl")}
        log_r = {e["batch_id"]: e for e in common.read_jsonl(tmp / "checker_log.jsonl")}
        check(rows_r[first_v[0]["id"]]["verdict"] == "missing" and rows_r[first_v[1]["id"]]["verdict"] == "missing"
              and log_r[cdoc_r["batches"][0]["batch_id"]]["n_invalid_value"] == 2,
              "a verdict with a non-text or missing reason is counted as invalid and its item recorded as missing")
        run("parse_checker.py", str(tmp / "workflow_checker_result.json"), "--replace")
        check((tmp / "checked.jsonl").read_text(encoding="utf-8") == checked_text, "the real checker parse is restored")
        # a bare result-file name is looked up under the run directory when the current directory has none, and a
        # name found in neither is refused (a laptop rerun on 2026-09-30 ran the documented command from the checkout)
        bare = subprocess.run([sys.executable, str(HERE / "parse_checker.py"), "workflow_checker_result.json", "--replace"],
                              env=env, capture_output=True, text=True, check=False, cwd=str(HERE))
        check(bare.returncode == 0 and "read from the run directory" in bare.stdout
              and (tmp / "checked.jsonl").read_text(encoding="utf-8") == checked_text,
              "a bare result-file name is resolved under PILOT_DIR and parses the same verdicts")
        run("parse_checker.py", "no_such_result.json", "--replace", expect_failure=True)
        run("make_review_sheet.py")
        # a sheet carrying human annotations is never regenerated (Codex on PR #52)
        original_sheet = (tmp / "review_sheet.csv").read_bytes()  # bytes, so the restore is exact
        lines = original_sheet.decode("utf-8").splitlines()
        lines[1] = lines[1][: lines[1].rfind(",,")] + ",reviewed,a note"  # fill my_label and my_notes on row 1
        (tmp / "review_sheet.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        run("make_review_sheet.py", expect_failure=True)
        (tmp / "review_sheet.csv").write_bytes(original_sheet)
        # every attempt, final or not, must be what the recorded result derives: a stale non-final entry (the
        # retried call's first attempt) refuses the summary before any number is computed (Codex on PR #52)
        log_bytes = (tmp / "call_log.jsonl").read_bytes()
        log_rows = common.read_jsonl(tmp / "call_log.jsonl")
        next(e for e in log_rows if e.get("is_final") is False)["n_lines"] += 1
        common.write_jsonl(tmp / "call_log.jsonl", log_rows)
        run("compute_summary.py", expect_failure=True)
        (tmp / "call_log.jsonl").write_bytes(log_bytes)
        check(not (tmp / "summary.json").exists(),
              "a call log whose non-final attempt differs from the recorded result refuses the summary")
        # the handoff must carry the results block for the summary to write into (Codex on PR #52)
        handoff_bytes = (tmp / "HANDOFF.md").read_bytes()
        (tmp / "HANDOFF.md").write_text("# Self-test dry run\n\nNo markers here.\n", encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        (tmp / "HANDOFF.md").write_bytes(handoff_bytes)
        run("compute_summary.py")
        s = json.loads((tmp / "summary.json").read_text())
        yes = s["E4"]["generated"]["yes_over_answered"]
        check(f"judged yes {yes['x']} / {yes['n']} = {yes['p']:.3f}" in (tmp / "HANDOFF.md").read_text(encoding="utf-8")
              and (tmp / "HANDOFF.md").read_text(encoding="utf-8").startswith("# Self-test dry run\n\nFabricated"),
              "compute_summary writes the results block into the handoff, leaving the text outside the markers")
        check(s["run"]["n_retried_calls"] == 1, "one retried call recorded")
        cw = s["run"]["calls_with_valid_rows"]
        check(cw["n"] == 18 and cw["x"] == 17 and s["run"]["calls_without_response"] == 1
              and len(s["run"]["per_call"]) == 18 and s["run"]["per_call"][-1]["status"] == "no_response_recorded",
              "a planned call with no response record counts as a failed final call (17 / 18)")
        for a in ("A", "B"):  # regression: a bootstrap that counted copy pairs put the interval above the estimate
            e = s["E3"]["arm_mean_of_cells"][a]
            check(e["lo"] <= e["mean"] <= e["hi"], f"arm {a} within-cell bootstrap interval contains the point estimate")
            e = s["E3"]["vs_seeds"][a]
            check(e["lo"] <= e["mean"] <= e["hi"], f"arm {a} vs-seeds bootstrap interval contains the point estimate")
        check(s["E1"]["failure_reasons"].get("template_blank_count_not_1") == 3 and s["E1"]["failure_reasons"].get("not_json") == 3,
              f"format failures counted: {s['E1']['failure_reasons']}")
        C = s["controls"]
        n_unmeasurable = sum(1 for c in calls[:-1] if c["arm"] == "A" and c["specialty"] == common.SPECIALTIES[1])
        check(n_unmeasurable > 0 and C["unmeasurable"] == n_unmeasurable
              and C["faithful"]["n"] == C["n_control_rows"] - n_unmeasurable and C["faithful"]["x"] == C["faithful"]["n"],
              f"{n_unmeasurable} control(s) with no lexical content counted as unmeasurable and excluded from the "
              f"fidelity denominator")
        check(s["E4"]["checker_specificity_broken"]["unclear_counts_as_miss"]["p"] == 1.0, "specificity computed")
        check(s["review"]["n"] == 40, "review sheet has 40 rows")
        check(s["seed_provenance"] == ["selftest provenance, not study data"], "summary records the seed file's provenance")
        # checked.jsonl must be the parse of the checker plan on disk, and the plan must come from the rows on disk:
        # a foreign plan stamp, an altered item, a missing item, or a plan built from other rows is refused and the
        # summary already written stays as it was (Codex on PR #52)
        summary_text = (tmp / "summary.json").read_text(encoding="utf-8")
        checked_rows = common.read_jsonl(tmp / "checked.jsonl")
        swapped = [dict(c) for c in checked_rows]
        swapped[0]["patient_term"], swapped[1]["patient_term"] = swapped[1]["patient_term"], swapped[0]["patient_term"]
        for label, rows_ in (("foreign plan stamp", [dict(checked_rows[0], checker_plan_sha256="0" * 64)] + checked_rows[1:]),
                             ("altered item", swapped),
                             ("missing item", checked_rows[:-1])):
            common.write_jsonl(tmp / "checked.jsonl", rows_)
            run("compute_summary.py", expect_failure=True)
            check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
                  f"a checked.jsonl with a {label} is refused and the summary on disk is unchanged")
        (tmp / "checked.jsonl").write_text(checked_text, encoding="utf-8")
        plan_text = (tmp / "checker_batches.json").read_text(encoding="utf-8")
        plan_doc = json.loads(plan_text)
        plan_doc["input_hashes"]["all_rows_jsonl_sha256"] = "0" * 64
        (tmp / "checker_batches.json").write_text(json.dumps(plan_doc), encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        (tmp / "checker_batches.json").write_text(plan_text, encoding="utf-8")
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "a checker plan built from other generation rows is refused and the summary on disk is unchanged")
        # the parsed generation must be the call plan's: a re-planned prompt hash with the old outputs in place is
        # refused by the summary and by the checker-set builder (Codex on PR #52)
        calls_text = (tmp / "calls.json").read_text(encoding="utf-8")
        calls_doc = json.loads(calls_text)
        calls_doc["calls"][0]["prompt"] += "\nedited after the run"  # a consistent re-plan: prompt and hash agree
        calls_doc["calls"][0]["prompt_sha256"] = common.sha256_text(calls_doc["calls"][0]["prompt"])
        (tmp / "calls.json").write_text(json.dumps(calls_doc, ensure_ascii=False), encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        run("build_checker_set.py", expect_failure=True)
        (tmp / "calls.json").write_text(calls_text, encoding="utf-8")
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "outputs parsed under another prompt hash are refused by the summary and the checker-set builder")
        # a log that names the right plan beside rows it did not count (a parse interrupted between the two
        # writes) is refused (Codex on PR #52)
        rows_bytes = (tmp / "generated" / "all_rows.jsonl").read_bytes()
        common.write_jsonl(tmp / "generated" / "all_rows.jsonl", common.read_jsonl(tmp / "generated" / "all_rows.jsonl")[:-1])
        run("compute_summary.py", expect_failure=True)
        run("build_checker_set.py", expect_failure=True)
        (tmp / "generated" / "all_rows.jsonl").write_bytes(rows_bytes)
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "rows that do not match the final log records' counts are refused by the summary and the checker-set builder")
        # a failure that belongs to no planned final attempt is refused, not counted into E1 (Codex on PR #52)
        fail_bytes = (tmp / "generated" / "format_failures.jsonl").read_bytes()
        stale_failure = {"call_id": "not_a_planned_call", "arm": "A", "cell": "x", "attempt": 1, "line_index": 1,
                         "reason": "not_json", "line": "stale", "prompt_sha256": "0" * 64}
        common.write_jsonl(tmp / "generated" / "format_failures.jsonl",
                           common.read_jsonl(tmp / "generated" / "format_failures.jsonl") + [stale_failure])
        run("compute_summary.py", expect_failure=True)
        (tmp / "generated" / "format_failures.jsonl").write_bytes(fail_bytes)
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "a failure outside the planned final attempts is refused and the summary on disk is unchanged")
        # a plan whose stored hash is not the hash of its prompt is refused by every reader, before any workflow
        # script or request bundle is written (Codex on PR #52)
        calls_doc = json.loads(calls_text)
        calls_doc["calls"][0]["prompt_sha256"] = "0" * 64
        (tmp / "calls.json").write_text(json.dumps(calls_doc, ensure_ascii=False), encoding="utf-8")
        run("make_workflow_scripts.py", "generation", expect_failure=True)
        run("build_api_requests.py", "generation", "--model", "example-model", expect_failure=True)
        run("compute_summary.py", expect_failure=True)
        (tmp / "calls.json").write_text(calls_text, encoding="utf-8")
        plan_doc = json.loads(plan_text)
        plan_doc["batches"][0]["prompt_sha256"] = "0" * 64
        (tmp / "checker_batches.json").write_text(json.dumps(plan_doc, ensure_ascii=False), encoding="utf-8")
        run("make_workflow_scripts.py", "checker", expect_failure=True)
        run("parse_checker.py", str(tmp / "workflow_checker_result.json"), "--replace", expect_failure=True)
        # a checker prompt edited together with its hash is self-consistent but not what the rows, seeds and template
        # derive: refused by every reader before a workflow script or request bundle is written (Codex on PR #52)
        plan_doc = json.loads(plan_text)
        plan_doc["batches"][0]["prompt"] += "\nEdited after batching."
        plan_doc["batches"][0]["prompt_sha256"] = common.sha256_text(plan_doc["batches"][0]["prompt"])
        (tmp / "checker_batches.json").write_text(json.dumps(plan_doc, ensure_ascii=False), encoding="utf-8")
        run("make_workflow_scripts.py", "checker", expect_failure=True)
        run("build_api_requests.py", "checker", "--model", "example-model", expect_failure=True)
        (tmp / "checker_batches.json").write_text(plan_text, encoding="utf-8")
        key_text = (tmp / "checker_key.jsonl").read_bytes()
        key_rows = common.read_jsonl(tmp / "checker_key.jsonl")
        key_rows[0]["source"] = "edited"
        common.write_jsonl(tmp / "checker_key.jsonl", key_rows)
        run("make_workflow_scripts.py", "checker", expect_failure=True)  # the key is part of the derived bundle
        (tmp / "checker_key.jsonl").write_bytes(key_text)
        check(not list((tmp / "workflows").glob("*.js")) if (tmp / "workflows").exists() else True,
              "an inconsistent plan is refused by the workflow-script and request builders and the parsers; nothing written")
        run("make_workflow_scripts.py", "generation")
        run("make_workflow_scripts.py", "checker")
        check(len(list((tmp / "workflows").glob("*.js"))) == 2, "consistent plans yield the two workflow scripts")
        wf_text = (tmp / "workflows" / "generation.workflow.js").read_text(encoding="utf-8")
        check(json.dumps(proto) in wf_text and "protocol=${PROTOCOL}" in wf_text,
              "the workflow scripts put the frozen protocol's hash in every agent label")
        # the review bundle must sample these checked rows: a map stamped with another plan, or a key verdict that
        # differs from the checked row, is refused (Codex on PR #52)
        map_text = (tmp / "review_map.json").read_text(encoding="utf-8")
        map_doc = json.loads(map_text)
        check(map_doc["checker_plan_sha256"] == plan_sha, "review_map.json is stamped with the checker plan's hash")
        map_doc["checker_plan_sha256"] = "0" * 64
        (tmp / "review_map.json").write_text(json.dumps(map_doc), encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        (tmp / "review_map.json").write_text(map_text, encoding="utf-8")
        key_bytes = (tmp / "review_key.csv").read_bytes()  # bytes: the CSV's CRLF endings must survive the restore
        klines = key_bytes.decode("utf-8").splitlines()
        klines[1] = klines[1][: klines[1].rfind(",") + 1] + ("no" if klines[1].endswith("yes") else "yes")
        (tmp / "review_key.csv").write_text("\n".join(klines) + "\n", encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        (tmp / "review_key.csv").write_bytes(key_bytes)
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "a review bundle from another plan, or a key verdict that differs from the checked row, is refused")
        # a verdict outside {yes, no, unclear, missing} would leave both the answered and the missing counts and
        # shrink every denominator unseen: refused by checked_problems (Codex on PR #52)
        checked_bytes = (tmp / "checked.jsonl").read_bytes()
        rows_v = common.read_jsonl(tmp / "checked.jsonl")
        rows_v[0]["verdict"] = "maybe"
        common.write_jsonl(tmp / "checked.jsonl", rows_v)
        run("compute_summary.py", expect_failure=True)
        (tmp / "checked.jsonl").write_bytes(checked_bytes)
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "a checked row with a verdict outside the set is refused and the summary stays as it was")
        run("write_manifest.py")
        m = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m["design"]["seed_provenance"]["values"] == ["selftest provenance, not study data"]
              and m["design"]["seed_provenance"]["n_seeds_without_provenance"] == 0,
              "manifest records the seed file's provenance")
        check(m["script_hashes"] == common.script_hashes() and len(m["script_hashes"]) > 0,
              "the manifest hashes the executing scripts, not a scripts directory under the run (Codex on PR #52)")
        # record_run refuses a directory that is not a run's transcripts, a run id that is not the directory's name,
        # a journal that is not the one the stage's result was extracted from, and never writes over a recorded run
        # without --replace (Codex on PR #52)
        run("record_run.py", "generation", "wf_selftest_gen", str(tmp / "no_such_dir"), expect_failure=True)
        run("record_run.py", "generation", "some-other-id", str(gdir), expect_failure=True)
        run("record_run.py", "generation", "wf_selftest_other", str(odir), expect_failure=True)  # another run's journal
        # the transcripts must be exactly the journal's started agents: one unrelated transcript would otherwise
        # stand as the model evidence for every agent (Codex on PR #52)
        (gdir / "agent-zz.jsonl").write_text('{"model":"selftest-model"}\n', encoding="utf-8")
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), expect_failure=True)
        (gdir / "agent-zz.jsonl").unlink()
        (gdir / "agent-g02.jsonl").rename(gdir / "agent-g02.jsonl.aside")
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), expect_failure=True)
        (gdir / "agent-g02.jsonl.aside").rename(gdir / "agent-g02.jsonl")
        check("runs" not in json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
              or "generation" not in json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))["runs"],
              "a transcript of an agent the journal did not start, or a started agent without one, is refused")
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir))
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), expect_failure=True)
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), "--replace")
        # the extra JSON may not carry a computed key, which could otherwise replace the evidence (Codex on PR #52)
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), '{"agents_without_model_id": []}', "--replace",
            expect_failure=True)
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), '{"operator_note": "kept"}', "--replace")
        mr = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))["runs"]["generation"]
        check(mr["run_id"] == "wf_selftest_gen" and mr["agents_started"] == n_gen_agents
              and mr["agent_transcripts"] == n_gen_agents
              and mr["operator_note"] == "kept"
              and mr["agents_without_model_id"] == []
              and mr["journal_sha256"] == common.sha256_file(gdir / "journal.jsonl")
              and mr["model_evidence"]["model_strings_in_transcripts"] == {"selftest-model": n_gen_agents},
              "record_run binds the record to the journal the result was extracted from, matches every started agent's "
              "transcript, and replaces a record only with --replace")
        # finalize needs both subagent runs recorded: the run records carry the model evidence read from the
        # transcripts (Codex on PR #52)
        run("write_manifest.py", "finalize", expect_failure=True)
        run("record_run.py", "checker", "wf_selftest_chk", str(cdir))
        # the copied journals under workflows/ (in place since the extractions) are required outputs compared with
        # the run records, and the result files are extracted again from them (Codex on PR #52)
        # finalize hashes every required output and refuses a missing one; a plan-time rewrite after finalize keeps
        # the hashes only while the outputs are unchanged (Codex on PR #52)
        run("write_manifest.py", "finalize")
        # the review sheet is a summary input: filled after the summary, it refuses finalize until the summary is
        # computed again, and no number changes since the summary reads no annotation (Codex on PR #52)
        s_before = json.loads((tmp / "summary.json").read_text(encoding="utf-8"))
        sheet_lines = (tmp / "review_sheet.csv").read_bytes().decode("utf-8").splitlines()
        sheet_lines[1] = sheet_lines[1][: sheet_lines[1].rfind(",,")] + ",reviewed,filled after the summary"
        (tmp / "review_sheet.csv").write_text("\n".join(sheet_lines) + "\n", encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        run("compute_summary.py")
        s_after = json.loads((tmp / "summary.json").read_text(encoding="utf-8"))
        check({k: v for k, v in s_after.items() if k != "input_hashes"}
              == {k: v for k, v in s_before.items() if k != "input_hashes"}
              and s_after["input_hashes"]["review_sheet.csv"] != s_before["input_hashes"]["review_sheet.csv"],
              "a review sheet filled after the summary refuses finalize; recomputing changes only its input hash")
        run("write_manifest.py", "finalize")
        mf = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(isinstance(mf["finalized_utc"], str)
              and {"checked.jsonl", "summary.json", "HANDOFF.md", f"generated/{calls[-1]['id']}.jsonl",
                   f"generated/raw/{calls[0]['id']}__attempt1.txt"} <= set(mf["output_hashes"]),
              "finalize hashes every required output, per-call files included")
        check({"workflow_generation_result.json", "workflow_checker_result.json"} <= set(mf["output_hashes"]),
              "finalize hashes the two recorded result files")
        # the run records must vouch for the results: a record bound to another journal, transcripts that report a
        # model the facts do not declare, or transcripts that report none, refuse finalize (Codex on PR #52)
        manifest_bytes = (tmp / "manifest.json").read_bytes()
        mdoc_runs = json.loads(manifest_bytes.decode("utf-8"))
        mdoc_runs["runs"]["generation"]["journal_sha256"] = "0" * 64
        (tmp / "manifest.json").write_text(json.dumps(mdoc_runs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "manifest.json").write_bytes(manifest_bytes)
        copy_path = tmp / "workflows" / "checker.journal.jsonl"
        copy_bytes = copy_path.read_bytes()
        copy_path.write_bytes(copy_bytes + b'{"type": "extra"}\n')
        run("write_manifest.py", "finalize", expect_failure=True)
        copy_path.unlink()
        run("write_manifest.py", "finalize", expect_failure=True)
        copy_path.write_bytes(copy_bytes)
        # the workflow scripts are required outputs, bound to the run records and rendered again from the plan and
        # the protocol at finalize (Codex on PR #52)
        wf_path = tmp / "workflows" / "generation.workflow.js"
        wf_bytes = wf_path.read_bytes()
        check(json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))["runs"]["generation"]["workflow_script_sha256"]
              == common.sha256_file(wf_path), "the run record carries the hash of the workflow script that ran")
        wf_path.write_bytes(wf_bytes + b"\n// edited after the run\n")
        run("write_manifest.py", "finalize", expect_failure=True)
        wf_path.unlink()
        run("write_manifest.py", "finalize", expect_failure=True)
        wf_path.write_bytes(wf_bytes)
        agent_bytes = (gdir / "agent-g01.jsonl").read_bytes()
        (gdir / "agent-g01.jsonl").write_text('{"model":"another-model"}\n', encoding="utf-8")
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), "--replace")
        run("write_manifest.py", "finalize", expect_failure=True)
        (gdir / "agent-g01.jsonl").write_text('{"type":"no model string here"}\n', encoding="utf-8")  # the rest report one
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), "--replace")
        run("write_manifest.py", "finalize", expect_failure=True)
        (gdir / "agent-g01.jsonl").write_bytes(agent_bytes)
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir), "--replace")
        m_after = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m_after["finalized_utc"] is None and "output_hashes" not in m_after,
              "replacing a run record clears the finalization until the next finalize (Codex on PR #52)")
        run("write_manifest.py", "finalize")
        mf = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(mf["runs"]["generation"]["model_evidence"]["model_strings_in_transcripts"] == {"selftest-model": n_gen_agents},
              "finalize refuses a record bound to another journal, a transcript model the facts do not declare, and "
              "an agent transcript with no model id; it passes once the record agrees again")
        # the bundle must reproduce from the recorded result files under the current code: a changed response, a
        # changed verdict, or a review map that is not the draw refuses finalize (Codex on PR #52)
        gen_bytes = (tmp / "workflow_generation_result.json").read_bytes()
        gdoc = json.loads(gen_bytes.decode("utf-8"))
        gdoc["calls"][0]["attempts"][0]["raw"] += "\n" + keyed_line
        (tmp / "workflow_generation_result.json").write_text(json.dumps(gdoc), encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        # a result edited in a field no downstream file derives from, its source_sha256 kept, is refused too: the
        # result is extracted again from the copied journal by the summary and by finalize (Codex on PR #52)
        gdoc = json.loads(gen_bytes.decode("utf-8"))
        gdoc["calls"][0]["attempts"][0]["agent_id"] = "forged"
        (tmp / "workflow_generation_result.json").write_text(json.dumps(gdoc), encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        run("compute_summary.py", expect_failure=True)
        (tmp / "workflow_generation_result.json").write_bytes(gen_bytes)
        chk_bytes = (tmp / "workflow_checker_result.json").read_bytes()
        cdoc = json.loads(chk_bytes.decode("utf-8"))
        v0 = cdoc["batches"][0]["attempts"][0]["result"]["verdicts"][0]
        v0["equivalent"] = "no" if v0["equivalent"] != "no" else "yes"
        (tmp / "workflow_checker_result.json").write_text(json.dumps(cdoc), encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "workflow_checker_result.json").write_bytes(chk_bytes)
        map_bytes = (tmp / "review_map.json").read_bytes()
        mdoc = json.loads(map_bytes.decode("utf-8"))
        mdoc["allocation"] = {a: 0 for a in mdoc["allocation"]}
        (tmp / "review_map.json").write_text(json.dumps(mdoc, indent=2) + "\n", encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "review_map.json").write_bytes(map_bytes)
        # a script edited since the summary was computed refuses finalize until compute_summary.py runs again
        summary_bytes0 = (tmp / "summary.json").read_bytes()
        sdoc0 = json.loads(summary_bytes0.decode("utf-8"))
        sdoc0["script_hashes"]["common.py"] = "0" * 64
        (tmp / "summary.json").write_text(json.dumps(sdoc0, indent=2) + "\n", encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "summary.json").write_bytes(summary_bytes0)
        # a value edited in summary.json under unchanged hashes is refused: finalize computes the summary again and
        # compares it (Codex on PR #52)
        sdoc1 = json.loads(summary_bytes0.decode("utf-8"))
        sdoc1["E1"]["overall"]["x"] = 999
        (tmp / "summary.json").write_text(json.dumps(sdoc1, indent=2) + "\n", encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "summary.json").write_bytes(summary_bytes0)
        check(json.loads((tmp / "manifest.json").read_text(encoding="utf-8")) == mf,
              "finalize refuses a changed response, a changed verdict, a review map that is not the draw, and a "
              "script changed since the summary; the manifest stays as it was")
        # a summary that predates a change to one of its inputs is refused at finalize, even when every other
        # validator passes: a verdict's reason is compared by none of them (Codex on PR #52)
        checked_now = (tmp / "checked.jsonl").read_text(encoding="utf-8")
        rows_now = common.read_jsonl(tmp / "checked.jsonl")
        rows_now[0]["reason"] = "edited after the summary was computed"
        common.write_jsonl(tmp / "checked.jsonl", rows_now)
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "checked.jsonl").write_text(checked_now, encoding="utf-8")
        check(json.loads((tmp / "manifest.json").read_text(encoding="utf-8")) == mf,
              "finalize refuses a summary computed from earlier inputs and leaves the manifest as it was")
        # a handoff whose results block is not the summary's rendering is refused at finalize (Codex on PR #52)
        hand_bytes = (tmp / "HANDOFF.md").read_bytes()
        hand_text = hand_bytes.decode("utf-8")
        edited = hand_text.replace(f"judged yes {yes['x']} / {yes['n']}", f"judged yes {yes['x'] + 1} / {yes['n']}")
        check(edited != hand_text, "the results block holds the equivalence count to edit")
        (tmp / "HANDOFF.md").write_text(edited, encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "HANDOFF.md").write_text(hand_text.replace("<!-- results:end -->", ""), encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "HANDOFF.md").write_bytes(hand_bytes)
        check(json.loads((tmp / "manifest.json").read_text(encoding="utf-8")) == mf,
              "a handoff whose results block differs from the summary, or lacks a marker, refuses finalize")
        # a summary whose recorded input hashes omit one of the inputs is refused, not validated on the rest
        summary_bytes = (tmp / "summary.json").read_bytes()
        sdoc = json.loads(summary_bytes.decode("utf-8"))
        del sdoc["input_hashes"]["checked.jsonl"]
        (tmp / "summary.json").write_text(json.dumps(sdoc, indent=2) + "\n", encoding="utf-8")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "summary.json").write_bytes(summary_bytes)
        # a per-call file that does not hold its call's rows from all_rows.jsonl is refused at finalize
        first_call_file = tmp / "generated" / f"{calls[0]['id']}.jsonl"
        call_bytes = first_call_file.read_bytes()
        first_call_file.write_bytes(b"")
        run("write_manifest.py", "finalize", expect_failure=True)
        first_call_file.write_bytes(call_bytes)
        check(json.loads((tmp / "manifest.json").read_text(encoding="utf-8")) == mf,
              "finalize refuses a summary missing an input hash and a per-call file that differs from all_rows.jsonl")
        (tmp / "summary.json").rename(tmp / "summary.json.aside")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "summary.json.aside").rename(tmp / "summary.json")
        check(json.loads((tmp / "manifest.json").read_text(encoding="utf-8")) == mf,
              "a missing required output refuses finalize and leaves the manifest as it was")
        run("write_manifest.py")
        m3 = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m3["finalized_utc"] == mf["finalized_utc"] and m3["output_hashes"] == mf["output_hashes"],
              "a plan-time rewrite keeps the finalization time and output hashes while the outputs are unchanged")
        # a script edited since finalize clears the finalization too (Codex on PR #52): the manifest on disk
        # records the scripts as they were, so one recorded hash is made stale, as an edit since would make it
        stale_m = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        first_script = sorted(stale_m["script_hashes"])[0]
        stale_m["script_hashes"][first_script] = "0" * 64
        (tmp / "manifest.json").write_text(json.dumps(stale_m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run("write_manifest.py")
        m3b = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m3b["finalized_utc"] is None and "output_hashes" not in m3b and m3b["script_hashes"][first_script] != "0" * 64,
              "a plan-time rewrite after a script changed clears the finalization time and the hashes")
        run("write_manifest.py", "finalize")
        md_text = (tmp / "summary.md").read_text(encoding="utf-8")
        (tmp / "summary.md").write_text(md_text + "edited after finalize\n", encoding="utf-8")
        run("write_manifest.py")
        m4 = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m4["finalized_utc"] is None and "output_hashes" not in m4,
              "a plan-time rewrite after an output changed clears the finalization time and the hashes")
        (tmp / "summary.md").write_text(md_text, encoding="utf-8")
        run("write_manifest.py", "finalize")
        # an input refactor: text moved between the generation template and design.json with no rendered prompt
        # changed (Codex on PR #52). A plain write refuses the changed input; --refactor-inputs accepts it only with a
        # reason, not combined with --reset, and only when the re-planned calls carry the recorded prompt hashes; it
        # is recorded under input_refactors with the run records kept and the finalization cleared; nothing to
        # record, a refactor that changes a prompt, and a changed seed file are refused
        design_bytes = (tmp / "design.json").read_bytes()
        ddoc = json.loads(design_bytes.decode("utf-8"))
        (tmp / "design.json").write_text(json.dumps(ddoc, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
        run("write_manifest.py", expect_failure=True)  # calls.json was planned from the previous design file
        run("plan_calls.py")
        run("write_manifest.py", expect_failure=True)  # a changed input without --reset
        run("write_manifest.py", "--refactor-inputs", "", expect_failure=True)
        run("write_manifest.py", "--refactor-inputs", "self-test", "--reset", expect_failure=True)
        m_before = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        run("write_manifest.py", "--refactor-inputs", "self-test: design.json re-serialized, no prompt changed")
        m_ref = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        ref = m_ref["input_refactors"]
        check(len(ref) == 1 and ref[0]["before"]["design_json_sha256"] == m_before["design_json_sha256"]
              and ref[0]["after"]["design_json_sha256"] == m_ref["design_json_sha256"] != m_before["design_json_sha256"]
              and ref[0]["changed"] == ["design_json_sha256"] and ref[0]["generation_calls_unchanged"] == 18
              and m_ref["runs"] == m_before["runs"] and m_ref["created_utc"] == m_before["created_utc"]
              and m_ref["finalized_utc"] is None and "output_hashes" not in m_ref
              and m_ref["prompt_hashes"]["generation_calls"] == m_before["prompt_hashes"]["generation_calls"],
              "an input refactor with every prompt unchanged is recorded with its hashes, keeps the run records, clears the finalization")
        run("write_manifest.py", "--refactor-inputs", "again", expect_failure=True)  # nothing changed since
        run("write_manifest.py", "finalize", expect_failure=True)  # summary.json still records the previous design hash
        s_prev = json.loads((tmp / "summary.json").read_text(encoding="utf-8"))
        run("compute_summary.py")
        s_now = json.loads((tmp / "summary.json").read_text(encoding="utf-8"))
        check(all(s_now[k] == s_prev[k] for k in ("E1", "E2", "E3", "E4", "E5", "controls", "run")),
              "the recomputation after an input refactor changes no number")
        run("write_manifest.py", "finalize")
        check(isinstance(json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))["finalized_utc"], str),
              "the refactored bundle finalizes again")
        ddoc2 = json.loads((tmp / "design.json").read_text(encoding="utf-8"))
        ddoc2["swap_types"][0]["definition"] += " (edited)"  # a change that alters a prompt is not a refactor
        (tmp / "design.json").write_text(json.dumps(ddoc2, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
        run("plan_calls.py")
        run("write_manifest.py", "--refactor-inputs", "a prompt changed", expect_failure=True)
        check(any(s in last_err[0] for s in ("not the recorded run's", "no longer validates against the plan",
                                             "is not what the current code derives")),
              "a refactor that changes a rendered prompt is refused: the recorded responses no longer validate against the plan")
        # the manifest's own comparison, in-process: the re-planned calls must carry the recorded prompt hashes
        wm0 = importlib.import_module("write_manifest")
        rec = {"c1": {"prompt_sha256": "a" * 64, "exemplar_ids": ["s1"]}}
        old0 = {"design_json_sha256": "d" * 64, "prompt_hashes": {"generation_prompt_template": "t" * 64, "generation_calls": rec}}
        cur0 = {"design_json_sha256": "e" * 64, "prompt_hashes": {"generation_prompt_template": "t" * 64}}
        same = {"calls": [{"id": "c1", "prompt_sha256": "a" * 64, "exemplar_ids": ["s1"]}]}
        other = {"calls": [{"id": "c1", "prompt_sha256": "b" * 64, "exemplar_ids": ["s1"]}]}
        okrec = wm0.input_refactor_record(old0, cur0, same, ["design_json_sha256"], "r", "now")
        try:
            wm0.input_refactor_record(old0, cur0, other, ["design_json_sha256"], "r", "now")
            refused = False
        except SystemExit as e:
            refused = "not the recorded run's" in str(e)
        check(okrec["generation_calls_unchanged"] == 1 and okrec["before"]["design_json_sha256"] == "d" * 64 and refused,
              "the manifest records a refactor whose calls match the recorded prompt hashes and refuses one whose do not")
        (tmp / "design.json").write_text(json.dumps(ddoc, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
        run("plan_calls.py")
        seeds_bytes = (tmp / "seeds.json").read_bytes()  # the seed file is not refactorable
        (tmp / "seeds.json").write_text(json.dumps(json.loads(seeds_bytes.decode("utf-8")), indent=4, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
        run("plan_calls.py")
        run("write_manifest.py", "--refactor-inputs", "seeds re-serialized", expect_failure=True)
        (tmp / "seeds.json").write_bytes(seeds_bytes)
        run("plan_calls.py")
        run("write_manifest.py")
        check(isinstance(json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))["finalized_utc"], str),
              "with the inputs back as sealed, a plain rewrite keeps the finalization")
        # a checker template edited after batching is refused: the manifest must not record a stale checker plan
        tpl = tmp / "prompts" / "checker_prompt.txt"
        tpl_text = tpl.read_text(encoding="utf-8")
        tpl.write_text(tpl_text + "\nedited after batching\n", encoding="utf-8")
        run("write_manifest.py", expect_failure=True)
        tpl.write_text(tpl_text, encoding="utf-8")
        # the protocol is frozen: a change after the first manifest refuses every write instead of sealing
        # protocol_unchanged: false, and the recorded results, stamped with the protocol they ran under, are refused
        # by the parsers; restored, the finalization stands (Codex on PR #52)
        proto_bytes = (tmp / "PROTOCOL.md").read_bytes()
        (tmp / "PROTOCOL.md").write_bytes(proto_bytes + b"\nEdited after the run.\n")
        run("write_manifest.py", expect_failure=True)
        run("write_manifest.py", "finalize", expect_failure=True)
        run("parse_generation.py", str(tmp / "workflow_generation_result.json"), "--replace", expect_failure=True)
        (tmp / "PROTOCOL.md").write_bytes(proto_bytes)
        run("write_manifest.py")
        m_proto = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m_proto["protocol_unchanged"] is True and isinstance(m_proto["finalized_utc"], str),
              "a changed protocol refuses every write and the stamped results; restored, the finalization stands")
        # the recorded run's two legacy results (no protocol stamp) are sealed only under the protocol they ran under:
        # a protocol rewritten and re-baselined with --reset cannot be finalized over them (Codex on PR #52)
        wm = importlib.import_module("write_manifest")
        legacy_gen = next(k for k, v in common.LEGACY_UNBOUND_SOURCES.items() if v.startswith("generation"))
        legacy_result = {"source_sha256": legacy_gen, "protocol_sha256": None, "calls": []}
        check(common.legacy_protocol_problems(legacy_result, "1" * 64)
              and not common.legacy_protocol_problems(legacy_result, common.LEGACY_PROTOCOL_SHA256)
              and not common.legacy_protocol_problems({"source_sha256": legacy_gen, "protocol_sha256": proto}, "1" * 64)
              and not common.legacy_protocol_problems({"source_sha256": "0" * 64, "protocol_sha256": None}, "1" * 64),
              "a legacy result is attributed to the protocol it ran under and to no other; stamped or foreign results are not its concern")
        result_path = tmp / "workflow_generation_result.json"
        result_bytes_legacy = result_path.read_bytes()
        result_path.write_text(json.dumps(legacy_result), encoding="utf-8")
        wm.PILOT = tmp  # run_problems reads the result files and the copies under the directory the name binds to
        runs_now = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))["runs"]
        under_reset = wm.run_problems(model_doc, runs_now, "1" * 64)
        under_own = wm.run_problems(model_doc, runs_now, common.LEGACY_PROTOCOL_SHA256)
        wm.PILOT = common.PILOT
        result_path.write_bytes(result_bytes_legacy)
        check(any("was produced under protocol" in p for p in under_reset)
              and not any("was produced under protocol" in p for p in under_own),
              "finalize refuses a legacy result under a reset protocol and accepts it under the one it ran under")
        # manifest_model.json is frozen from the first manifest that recorded its hash: an edit after the run is
        # refused without --reset, and --reset clears the run records, so finalize needs them recorded again
        # (Codex on PR #52)
        model_doc = json.loads(model_path.read_text(encoding="utf-8"))
        model_doc["harness_version"] = "edited after the run"
        model_path.write_text(json.dumps(model_doc, indent=2) + "\n", encoding="utf-8")
        run("write_manifest.py", expect_failure=True)
        run("write_manifest.py", "finalize", expect_failure=True)
        m_kept = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        run("write_manifest.py", "--reset")
        m_reset = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m_kept["model"]["harness_version"] != "edited after the run"
              and m_reset["model"]["harness_version"] == "edited after the run"
              and m_reset["manifest_model_sha256"] == common.sha256_file(model_path)
              and m_reset["runs"] == {} and m_reset["finalized_utc"] is None
              and isinstance(m_reset["metadata_reset_utc"], str),
              "an edited manifest_model.json is refused without --reset; --reset records it and clears the run records")
        run("write_manifest.py", "finalize", expect_failure=True)  # no run records after the reset
        run("record_run.py", "generation", "wf_selftest_gen", str(gdir))
        run("record_run.py", "checker", "wf_selftest_chk", str(cdir))
        run("write_manifest.py", "finalize")
        # the journal extractor reads the prompt hash from a labelled agent and leaves it null for a legacy label
        journal = [{"type": "launched"},
                   {"type": "started", "key": "k1", "agentId": "a1",
                    "label": f"{calls[0]['id']} attempt 1 sha256={calls[0]['prompt_sha256']} protocol={proto}"},
                   {"type": "result", "key": "k1", "agentId": "a1", "result": "{}"},
                   {"type": "started", "key": "k2", "agentId": "a2", "label": f"{calls[1]['id']} attempt 1 protocol={proto}"},
                   {"type": "result", "key": "k2", "agentId": "a2", "result": "{}"},
                   {"type": "started", "key": "k3", "agentId": "a3",
                    "label": f"{calls[2]['id']} attempt 1 sha256={calls[2]['prompt_sha256']} protocol={proto}"},
                   {"type": "result", "key": "k3", "agentId": "a3",
                    "result": {"clinical_term": "a", "patient_term": "b", "template": "x ___ y", "control": "none"}}]
        (tmp / "journal.jsonl").write_text("".join(json.dumps(j) + "\n" for j in journal), encoding="utf-8")
        result_backup = (tmp / "workflow_generation_result.json").read_bytes()  # the run's own result, restored below
        run("extract_workflow_journal.py", "generation", str(tmp / "journal.jsonl"), "--replace")  # the run's file exists
        extracted = (tmp / "workflow_generation_result.json").read_text(encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal.jsonl"), expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == extracted,
              "a second extraction without --replace is refused and the result file is untouched")
        ext = {c["id"]: c for c in json.loads((tmp / "workflow_generation_result.json").read_text(encoding="utf-8"))["calls"]}
        check(ext[calls[0]["id"]]["prompt_sha256"] == calls[0]["prompt_sha256"] and ext[calls[1]["id"]]["prompt_sha256"] is None,
              "the journal extractor carries the prompt hash from the agent label and null without it")
        a3 = ext[calls[2]["id"]]["attempts"][0]
        check(a3["raw"] is None and a3["unexpected_result_type"] == "dict" and a3["null_return"] is False,
              "a non-text generation result is recorded as no text with its type, never serialized into a response")
        # two agents carrying one label would collapse into one attempt: the journal is refused (Codex on PR #52)
        dup = journal + [{"type": "started", "key": "k4", "agentId": "a4",
                          "label": f"{calls[0]['id']} attempt 1 sha256={calls[0]['prompt_sha256']} protocol={proto}"},
                         {"type": "result", "key": "k4", "agentId": "a4", "result": "{}"}]
        (tmp / "journal_dup.jsonl").write_text("".join(json.dumps(j) + "\n" for j in dup), encoding="utf-8")
        result_text = (tmp / "workflow_generation_result.json").read_text(encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_dup.jsonl"), "--replace", expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a journal with two agents on one label is refused and the previous result file is untouched")
        # a well-formed label whose id is not in the plan refuses the journal instead of vanishing (Codex on PR #52)
        foreign = journal + [{"type": "started", "key": "k5", "agentId": "a5", "label": "not_a_planned_call attempt 1"},
                             {"type": "result", "key": "k5", "agentId": "a5", "result": "{}"}]
        (tmp / "journal_foreign.jsonl").write_text("".join(json.dumps(j) + "\n" for j in foreign), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_foreign.jsonl"), "--replace", expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a journal with an agent outside the plan is refused and the previous result file is untouched")
        # a result record with no started agent refuses the journal instead of reading as no response (Codex on PR #52)
        orphan = journal + [{"type": "result", "key": "k9", "agentId": "a9", "result": "{}"}]
        (tmp / "journal_orphan.jsonl").write_text("".join(json.dumps(j) + "\n" for j in orphan), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_orphan.jsonl"), "--replace", expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a journal with a result record for no started agent is refused and the previous result file is untouched")
        # two started records sharing one (key, agentId) under two labels would read one response as two calls, and
        # a started record without key or agentId could match no result: both refused (Codex on PR #52)
        twin_label = f"{calls[3]['id']} attempt 1 sha256={calls[3]['prompt_sha256']} protocol={proto}"
        twin = journal + [{"type": "started", "key": "k1", "agentId": "a1", "label": twin_label}]
        (tmp / "journal_twin.jsonl").write_text("".join(json.dumps(j) + "\n" for j in twin), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_twin.jsonl"), "--replace", expect_failure=True)
        nokey = journal + [{"type": "started", "label": twin_label}]
        (tmp / "journal_nokey.jsonl").write_text("".join(json.dumps(j) + "\n" for j in nokey), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_nokey.jsonl"), "--replace", expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a journal with two started records on one agent identity, or a started record without one, is refused")
        # a started record whose label is not in the run's form refuses the journal; a truncated record with such a
        # label is listed as without a result rather than skipped as unlabelled (Codex on PR #52)
        badlabel = journal + [{"type": "started", "key": "k10", "agentId": "a10", "label": "not a label"},
                              {"type": "result", "key": "k10", "agentId": "a10", "result": "{}"}]
        (tmp / "journal_badlabel.jsonl").write_text("".join(json.dumps(j) + "\n" for j in badlabel), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_badlabel.jsonl"), "--replace", expect_failure=True)
        badtrunc = journal + [{"type": "started", "key": "k11", "agentId": "a11", "label": "not a label"}]
        (tmp / "journal_badtrunc.jsonl").write_text("".join(json.dumps(j) + "\n" for j in badtrunc), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_badtrunc.jsonl"), "--replace", expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a started record with a malformed label is refused, with or without a result, and the result file is untouched")
        # two started records reusing one agent id, whatever their keys, are refused: one agent's response and
        # transcript would stand for two calls (Codex on PR #52)
        reuse = journal + [{"type": "started", "key": "k9", "agentId": "a1",
                            "label": f"{calls[6]['id']} attempt 1 sha256={calls[6]['prompt_sha256']} protocol={proto}"},
                           {"type": "result", "key": "k9", "agentId": "a1", "result": "{}"}]
        (tmp / "journal_reuse.jsonl").write_text("".join(json.dumps(j) + "\n" for j in reuse), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_reuse.jsonl"), "--replace", expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a journal with two started records reusing one agent id is refused and the previous result file is untouched")
        # a started agent with no result record is not a null return: refused unless --allow-missing-results, which
        # leaves the attempt out and lists the agent; labels with differing protocol hashes are refused (Codex on PR #52)
        trunc = journal + [{"type": "started", "key": "k7", "agentId": "a7",
                            "label": f"{calls[4]['id']} attempt 1 sha256={calls[4]['prompt_sha256']} protocol={proto}"}]
        (tmp / "journal_trunc.jsonl").write_text("".join(json.dumps(j) + "\n" for j in trunc), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_trunc.jsonl"), "--replace", expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a started agent without a result record refuses the journal and leaves the previous result file untouched")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_trunc.jsonl"), "--replace", "--allow-missing-results")
        ext2 = json.loads((tmp / "workflow_generation_result.json").read_text(encoding="utf-8"))
        check(ext2["agents_without_result_record"] == [{"agent_id": "a7", "label": trunc[-1]["label"]}]
              and calls[4]["id"] not in {c["id"] for c in ext2["calls"]} and ext2["protocol_sha256"] == proto,
              "--allow-missing-results leaves the attempt out, lists the agent, and the result carries the protocol hash")
        conflict = journal + [{"type": "started", "key": "k8", "agentId": "a8",
                               "label": f"{calls[5]['id']} attempt 1 sha256={calls[5]['prompt_sha256']} protocol={'1' * 64}"},
                              {"type": "result", "key": "k8", "agentId": "a8", "result": "{}"}]
        (tmp / "journal_conflict.jsonl").write_text("".join(json.dumps(j) + "\n" for j in conflict), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_conflict.jsonl"), "--replace", expect_failure=True)
        # the run's own result back in place: every reader of the checker plan derives the generation from the copied
        # journal first, so the checker extraction below needs the result the copy extracts to (Codex on PR #52)
        (tmp / "workflow_generation_result.json").write_bytes(result_backup)
        # a checker result that is not an object (a non-JSON string, a number) is kept verbatim with its type and
        # counted by the extractor, and the parser logs it as a malformed return, not a null one (Codex on PR #52)
        cb = json.loads((tmp / "checker_batches.json").read_text(encoding="utf-8"))["batches"]
        cj = [{"type": "launched"},
              {"type": "started", "key": "c1", "agentId": "ca1", "label": f"{cb[0]['batch_id']} attempt 1 sha256={cb[0]['prompt_sha256']} protocol={proto}"},
              {"type": "result", "key": "c1", "agentId": "ca1", "result": "Sorry, no verdicts, just prose."},
              {"type": "started", "key": "c2", "agentId": "ca2", "label": f"{cb[1]['batch_id']} attempt 1 sha256={cb[1]['prompt_sha256']} protocol={proto}"},
              {"type": "result", "key": "c2", "agentId": "ca2", "result": 42},
              {"type": "started", "key": "c3", "agentId": "ca3", "label": f"{cb[2]['batch_id']} attempt 1 sha256={cb[2]['prompt_sha256']} protocol={proto}"},
              {"type": "result", "key": "c3", "agentId": "ca3", "result": None}]  # an explicit null return
        (tmp / "journal_chk.jsonl").write_text("".join(json.dumps(j) + "\n" for j in cj), encoding="utf-8")
        chk_backup = (tmp / "workflow_checker_result.json").read_bytes()
        checked_backup = (tmp / "checked.jsonl").read_bytes()
        chklog_backup = (tmp / "checker_log.jsonl").read_bytes()
        run("extract_workflow_journal.py", "checker", str(tmp / "journal_chk.jsonl"), "--replace")
        ex = json.loads((tmp / "workflow_checker_result.json").read_text(encoding="utf-8"))
        exb = {b["batch_id"]: b["attempts"][0] for b in ex["batches"]}
        a1, a2, a3 = exb[cb[0]["batch_id"]], exb[cb[1]["batch_id"]], exb[cb[2]["batch_id"]]
        check(ex["non_object_results"] == 2 and ex["source_sha256"] == common.sha256_file(tmp / "journal_chk.jsonl")
              and a1["result"] is None and a1["raw_return"] == "Sorry, no verdicts, just prose." and a1["unexpected_result_type"] == "str"
              and a1["null_return"] is False and a2["raw_return"] == "42" and a2["unexpected_result_type"] == "int"
              and a3["result"] is None and a3["null_return"] is True and "raw_return" not in a3,
              "a non-object checker result is kept verbatim with its type and counted; a null return stays a null return")
        run("parse_checker.py", str(tmp / "workflow_checker_result.json"), "--replace")
        clog = {e["batch_id"]: e for e in common.read_jsonl(tmp / "checker_log.jsonl")}
        e1, e3 = clog[cb[0]["batch_id"]], clog[cb[2]["batch_id"]]
        check(e1["malformed_return"] is True and e1["null_return"] is False and e1["status"] == "failed"
              and e3["malformed_return"] is False and e3["null_return"] is True and e3["status"] == "failed",
              "the checker log tells a malformed return from a null return")
        (tmp / "workflow_checker_result.json").write_bytes(chk_backup)
        (tmp / "checked.jsonl").write_bytes(checked_backup)
        (tmp / "checker_log.jsonl").write_bytes(chklog_backup)
        # a rerun whose inputs changed must not inherit the previous manifest's metadata (Codex on PR #52), and a
        # plan that was not re-rendered after the inputs changed is refused even with --reset
        seeds_doc["seeds"][0]["clinical_term"] = "changed for the rerun check"
        (tmp / "seeds.json").write_text(json.dumps(seeds_doc, ensure_ascii=False), encoding="utf-8")
        run("write_manifest.py", "--reset", expect_failure=True)  # calls.json still from the old seeds: refuse
        run("plan_calls.py")
        run("compute_summary.py", expect_failure=True)  # the previous parse under re-planned prompts: refuse
        run("build_checker_set.py", expect_failure=True)
        run("write_manifest.py", expect_failure=True)  # seeds changed: refuse
        # the previous run's checker plan was built from the old seeds: refused even with --reset until it is
        # rebuilt after the new generation or moved aside (Codex on PR #52)
        run("write_manifest.py", "--reset", expect_failure=True)
        (tmp / "checker_batches.json").unlink()
        run("write_manifest.py", "--reset")
        m2 = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(isinstance(m2.get("metadata_reset_utc"), str) and m2["runs"] == {} and m2["finalized_utc"] is None
              and m2["seeds_json_sha256"] != m["seeds_json_sha256"],
              "write_manifest refuses changed inputs and starts fresh metadata with --reset")
        md = (tmp / "summary.md").read_text()
        check("Estimand 5" in md and "\u2014" not in md, "summary.md rendered, no em-dash")
        print("dry run summary.md head:\n" + "\n".join(md.splitlines()[:6]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unit_tests()
    dry_run()
    print("selftest: all checks passed")
