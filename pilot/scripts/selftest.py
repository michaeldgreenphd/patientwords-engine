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
        for name in ("seeds.json", "design.json", "manifest_model.json", "PROTOCOL.md", "prompts"):
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
        gen = {"calls": [{"id": c["id"], "arm": c["arm"], "cell": c["cell"],
                          "attempts": fake_response(c, r, broken_first=(c["id"] == calls[3]["id"]))} for c in calls[:-1]]}
        (tmp / "wf_gen.json").write_text(json.dumps(gen))
        run("parse_generation.py", str(tmp / "wf_gen.json"))
        run("parse_generation.py", str(tmp / "wf_gen.json"), expect_failure=True)  # outputs exist: refuse

        def n_outputs() -> int:
            return len(list((tmp / "generated").glob("*.jsonl"))) + len(list((tmp / "generated" / "raw").glob("*.txt")))
        # a result file that fails the contract is refused with --replace too, and the previous outputs stay intact
        # (Codex on PR #52): a duplicate call id, an unplanned id, and a file without a calls list
        before = n_outputs()
        for label, bad in (("duplicate call id", {"calls": gen["calls"] + [gen["calls"][0]]}),
                           ("unplanned call id", {"calls": gen["calls"] + [dict(gen["calls"][0], id="not_planned")]}),
                           ("no calls list", {"nope": []})):
            (tmp / "wf_bad.json").write_text(json.dumps(bad))
            run("parse_generation.py", str(tmp / "wf_bad.json"), "--replace", expect_failure=True)
            check(n_outputs() == before, f"a result with a {label} is refused and leaves the previous outputs intact")
        run("parse_generation.py", str(tmp / "wf_gen.json"), "--replace")
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
            chk["batches"].append({"batch_id": b["batch_id"], "attempts": [{"attempt": 1, "result": {"verdicts": verdicts}}]})
        (tmp / "wf_chk.json").write_text(json.dumps(chk))
        (tmp / "wf_chk_bad.json").write_text(json.dumps({"batches": chk["batches"] + [chk["batches"][0]]}))
        run("parse_checker.py", str(tmp / "wf_chk_bad.json"), expect_failure=True)  # duplicate batch id: refuse
        run("parse_checker.py", str(tmp / "wf_chk.json"))
        run("make_review_sheet.py")
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
        run("write_manifest.py")
        m = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        check(m["design"]["seed_provenance"]["values"] == ["selftest provenance, not study data"]
              and m["design"]["seed_provenance"]["n_seeds_without_provenance"] == 0,
              "manifest records the seed file's provenance")
        # a rerun whose inputs changed must not inherit the previous manifest's metadata (Codex on PR #52)
        seeds_doc["seeds"][0]["clinical_term"] = "changed for the rerun check"
        (tmp / "seeds.json").write_text(json.dumps(seeds_doc, ensure_ascii=False), encoding="utf-8")
        run("plan_calls.py")
        run("write_manifest.py", expect_failure=True)  # seeds changed: refuse
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
