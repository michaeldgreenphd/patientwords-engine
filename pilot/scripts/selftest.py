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
    m, pairs = common.mean_pairwise([a, b, c])
    check(pairs == 3 and abs(m - 1 / 3) < 1e-12, "mean pairwise over 3 vectors uses 3 pairs")
    dummies = [{"id": f"d{i}"} for i in range(12)]
    r1, r2 = random.Random(common.MASTER_SEED), random.Random(common.MASTER_SEED)
    s1, s2 = r1.sample(dummies, 8), r2.sample(dummies, 8)
    check(len(s1) == 8 and len({d["id"] for d in s1}) == 8 and s1 == s2, "8 of 12 sampled without replacement, deterministic")
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
    check(common.control_is_faithful({"clinical_term": "Chest pain", "patient_term": "chest  pain."}), "control fidelity")
    check(len(common.SPECIALTIES) == 3 and len(common.SWAP_DEFINITIONS) == 3, "design factors load from design.json")
    # surface form: casing, punctuation and spacing removed, letters of every script kept (Codex on PR #52)
    check(common.surface_key("Café au lait") == "caféaulait"
          and common.surface_key("Пневмония, острая") == "пневмонияострая"
          and common.surface_key("Chest pain") == common.surface_key("chest  pain."),
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
    if call["arm"] == "A" and call["cell"].startswith("neurology"):
        lines.append('{"clinical_term": "x", "patient_term": "y", "template": "no blank here", "control": "none"}')
        lines.append("not json at all")
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
        env = {**os.environ, "PILOT_DIR": str(tmp)}

        def run(script: str, *args: str, expect_failure: bool = False) -> str:
            out = subprocess.run([sys.executable, str(HERE / script), *args], env=env, capture_output=True, text=True,
                                 check=False)
            check((out.returncode != 0) if expect_failure else (out.returncode == 0),
                  f"{script} {' '.join(args)}{' (expected to refuse)' if expect_failure else ''}\n{out.stdout}{out.stderr}")
            return out.stdout
        run("plan_calls.py")
        calls = json.loads((tmp / "calls.json").read_text())["calls"]
        r = random.Random(1)
        # the last planned call is left out of the result: a planned call with no response record must stay in
        # every call-level denominator (Codex on PR #52)
        gen = {"calls": [{"id": c["id"], "arm": c["arm"], "cell": c["cell"], "prompt_sha256": c["prompt_sha256"],
                          "attempts": fake_response(c, r, broken_first=(c["id"] == calls[3]["id"]))} for c in calls[:-1]]}
        (tmp / "wf_gen.json").write_text(json.dumps(gen))
        run("parse_generation.py", str(tmp / "wf_gen.json"))
        run("parse_generation.py", str(tmp / "wf_gen.json"), expect_failure=True)  # outputs exist: refuse

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
                           ("missing prompt hash", {"calls": [unhashed] + gen["calls"][1:]})):
            (tmp / "wf_bad.json").write_text(json.dumps(bad))
            run("parse_generation.py", str(tmp / "wf_bad.json"), "--replace", expect_failure=True)
            check(n_outputs() == before, f"a result with a {label} is refused and leaves the previous outputs intact")
        (tmp / "wf_unbound.json").write_text(json.dumps({"calls": [unhashed] + gen["calls"][1:]}))
        run("parse_generation.py", str(tmp / "wf_unbound.json"), "--replace", "--unbound")  # legacy result: allowed
        log = common.read_jsonl(tmp / "call_log.jsonl")
        check(all(e["plan_binding"].startswith("none") for e in log), "an --unbound parse says so in every call log entry")
        run("parse_generation.py", str(tmp / "wf_gen.json"), "--replace")
        check(all(e["plan_binding"] == "prompt_sha256" for e in common.read_jsonl(tmp / "call_log.jsonl")),
              "a bound parse records the binding in every call log entry")
        by_id = {c["id"]: c for c in calls}
        check(all(e["prompt_sha256"] == by_id[e["call_id"]]["prompt_sha256"] for e in common.read_jsonl(tmp / "call_log.jsonl"))
              and all(r["prompt_sha256"] == by_id[r["call_id"]]["prompt_sha256"]
                      for r in common.read_jsonl(tmp / "generated" / "all_rows.jsonl")),
              "every call log entry and every row carries its planned prompt's hash")
        run("compute_summary.py", expect_failure=True)  # checked.jsonl does not exist yet: refuse, no partial summary
        run("build_checker_set.py")
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
        chk = {"batches": []}
        for b in batches:
            verdicts = []
            for iid in b["item_ids"]:
                src = key[iid]["source"]
                v = "no" if src == "broken" else ("yes" if r.random() < 0.9 else "unclear")
                verdicts.append({"id": iid, "equivalent": v, "reason": "fabricated for the self-test"})
            chk["batches"].append({"batch_id": b["batch_id"], "prompt_sha256": b["prompt_sha256"],
                                   "attempts": [{"attempt": 1, "result": {"verdicts": verdicts}}]})
        (tmp / "wf_chk.json").write_text(json.dumps(chk))
        b0 = chk["batches"][0]
        for label, bad in (("duplicate batch id", {"batches": chk["batches"] + [b0]}),
                           ("repeated attempt number", {"batches": [dict(b0, attempts=b0["attempts"] * 2)] + chk["batches"][1:]}),
                           ("retry after a verdict list", {"batches": [dict(b0, attempts=[b0["attempts"][0], dict(b0["attempts"][0], attempt=2)])]
                                                           + chk["batches"][1:]}),
                           ("foreign prompt hash", {"batches": [dict(b0, prompt_sha256="0" * 64)] + chk["batches"][1:]})):
            (tmp / "wf_chk_bad.json").write_text(json.dumps(bad))
            run("parse_checker.py", str(tmp / "wf_chk_bad.json"), expect_failure=True)
            check(not (tmp / "checked.jsonl").exists(), f"a checker result with a {label} is refused and writes nothing")
        run("parse_checker.py", str(tmp / "wf_chk.json"))
        # a previous checker parse is never written over without --replace, and every row carries the plan's hash
        # (Codex on PR #52)
        checked_text = (tmp / "checked.jsonl").read_text(encoding="utf-8")
        run("parse_checker.py", str(tmp / "wf_chk.json"), expect_failure=True)
        check((tmp / "checked.jsonl").read_text(encoding="utf-8") == checked_text,
              "a second checker parse without --replace is refused and leaves checked.jsonl intact")
        run("parse_checker.py", str(tmp / "wf_chk.json"), "--replace")
        plan_sha = common.sha256_file(tmp / "checker_batches.json")
        check((tmp / "checked.jsonl").read_text(encoding="utf-8") == checked_text
              and all(c["checker_plan_sha256"] == plan_sha for c in common.read_jsonl(tmp / "checked.jsonl")),
              "--replace rewrites the same verdicts, each row stamped with the checker plan's hash")
        run("make_review_sheet.py")
        # a sheet carrying human annotations is never regenerated (Codex on PR #52)
        original_sheet = (tmp / "review_sheet.csv").read_text(encoding="utf-8")
        lines = original_sheet.splitlines()
        lines[1] = lines[1][: lines[1].rfind(",,")] + ",reviewed,a note"  # fill my_label and my_notes on row 1
        (tmp / "review_sheet.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        run("make_review_sheet.py", expect_failure=True)
        (tmp / "review_sheet.csv").write_text(original_sheet, encoding="utf-8")
        run("compute_summary.py")
        s = json.loads((tmp / "summary.json").read_text())
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
        calls_doc["calls"][0]["prompt_sha256"] = "0" * 64
        (tmp / "calls.json").write_text(json.dumps(calls_doc), encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        run("build_checker_set.py", expect_failure=True)
        (tmp / "calls.json").write_text(calls_text, encoding="utf-8")
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "outputs parsed under another prompt hash are refused by the summary and the checker-set builder")
        # the review bundle must sample these checked rows: a map stamped with another plan, or a key verdict that
        # differs from the checked row, is refused (Codex on PR #52)
        map_text = (tmp / "review_map.json").read_text(encoding="utf-8")
        map_doc = json.loads(map_text)
        check(map_doc["checker_plan_sha256"] == plan_sha, "review_map.json is stamped with the checker plan's hash")
        map_doc["checker_plan_sha256"] = "0" * 64
        (tmp / "review_map.json").write_text(json.dumps(map_doc), encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        (tmp / "review_map.json").write_text(map_text, encoding="utf-8")
        key_text = (tmp / "review_key.csv").read_text(encoding="utf-8")
        klines = key_text.splitlines()
        klines[1] = klines[1][: klines[1].rfind(",") + 1] + ("no" if klines[1].endswith("yes") else "yes")
        (tmp / "review_key.csv").write_text("\n".join(klines) + "\n", encoding="utf-8")
        run("compute_summary.py", expect_failure=True)
        (tmp / "review_key.csv").write_text(key_text, encoding="utf-8")
        check((tmp / "summary.json").read_text(encoding="utf-8") == summary_text,
              "a review bundle from another plan, or a key verdict that differs from the checked row, is refused")
        (tmp / "scripts").mkdir()  # a stand-in for the code the manifest hashes; the dry run itself runs HERE's scripts
        (tmp / "scripts" / "marker.py").write_text("# selftest marker\n", encoding="utf-8")
        run("write_manifest.py")
        m = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m["design"]["seed_provenance"]["values"] == ["selftest provenance, not study data"]
              and m["design"]["seed_provenance"]["n_seeds_without_provenance"] == 0,
              "manifest records the seed file's provenance")
        # finalize hashes every required output and refuses a missing one; a plan-time rewrite after finalize keeps
        # the hashes only while the outputs are unchanged (Codex on PR #52)
        run("write_manifest.py", "finalize")
        mf = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(isinstance(mf["finalized_utc"], str)
              and {"checked.jsonl", "summary.json", "HANDOFF.md", f"generated/{calls[-1]['id']}.jsonl",
                   f"generated/raw/{calls[0]['id']}__attempt1.txt"} <= set(mf["output_hashes"]),
              "finalize hashes every required output, per-call files included")
        (tmp / "summary.json").rename(tmp / "summary.json.aside")
        run("write_manifest.py", "finalize", expect_failure=True)
        (tmp / "summary.json.aside").rename(tmp / "summary.json")
        check(json.loads((tmp / "manifest.json").read_text(encoding="utf-8")) == mf,
              "a missing required output refuses finalize and leaves the manifest as it was")
        run("write_manifest.py")
        m3 = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m3["finalized_utc"] == mf["finalized_utc"] and m3["output_hashes"] == mf["output_hashes"],
              "a plan-time rewrite keeps the finalization time and output hashes while the outputs are unchanged")
        # a script edited since finalize clears the finalization too (Codex on PR #52)
        (tmp / "scripts" / "marker.py").write_text("# selftest marker, edited after finalize\n", encoding="utf-8")
        run("write_manifest.py")
        m3b = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m3b["finalized_utc"] is None and "output_hashes" not in m3b,
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
        # a checker template edited after batching is refused: the manifest must not record a stale checker plan
        tpl = tmp / "prompts" / "checker_prompt.txt"
        tpl_text = tpl.read_text(encoding="utf-8")
        tpl.write_text(tpl_text + "\nedited after batching\n", encoding="utf-8")
        run("write_manifest.py", expect_failure=True)
        tpl.write_text(tpl_text, encoding="utf-8")
        # the journal extractor reads the prompt hash from a labelled agent and leaves it null for a legacy label
        journal = [{"type": "launched"},
                   {"type": "started", "key": "k1", "agentId": "a1",
                    "label": f"{calls[0]['id']} attempt 1 sha256={calls[0]['prompt_sha256']}"},
                   {"type": "result", "key": "k1", "agentId": "a1", "result": "{}"},
                   {"type": "started", "key": "k2", "agentId": "a2", "label": f"{calls[1]['id']} attempt 1"},
                   {"type": "result", "key": "k2", "agentId": "a2", "result": "{}"},
                   {"type": "started", "key": "k3", "agentId": "a3",
                    "label": f"{calls[2]['id']} attempt 1 sha256={calls[2]['prompt_sha256']}"},
                   {"type": "result", "key": "k3", "agentId": "a3",
                    "result": {"clinical_term": "a", "patient_term": "b", "template": "x ___ y", "control": "none"}}]
        (tmp / "journal.jsonl").write_text("".join(json.dumps(j) + "\n" for j in journal), encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal.jsonl"))
        ext = {c["id"]: c for c in json.loads((tmp / "workflow_generation_result.json").read_text(encoding="utf-8"))["calls"]}
        check(ext[calls[0]["id"]]["prompt_sha256"] == calls[0]["prompt_sha256"] and ext[calls[1]["id"]]["prompt_sha256"] is None,
              "the journal extractor carries the prompt hash from the agent label and null without it")
        a3 = ext[calls[2]["id"]]["attempts"][0]
        check(a3["raw"] is None and a3["unexpected_result_type"] == "dict" and a3["null_return"] is False,
              "a non-text generation result is recorded as no text with its type, never serialized into a response")
        # two agents carrying one label would collapse into one attempt: the journal is refused (Codex on PR #52)
        dup = journal + [{"type": "started", "key": "k4", "agentId": "a4",
                          "label": f"{calls[0]['id']} attempt 1 sha256={calls[0]['prompt_sha256']}"},
                         {"type": "result", "key": "k4", "agentId": "a4", "result": "{}"}]
        (tmp / "journal_dup.jsonl").write_text("".join(json.dumps(j) + "\n" for j in dup), encoding="utf-8")
        result_text = (tmp / "workflow_generation_result.json").read_text(encoding="utf-8")
        run("extract_workflow_journal.py", "generation", str(tmp / "journal_dup.jsonl"), expect_failure=True)
        check((tmp / "workflow_generation_result.json").read_text(encoding="utf-8") == result_text,
              "a journal with two agents on one label is refused and the previous result file is untouched")
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
