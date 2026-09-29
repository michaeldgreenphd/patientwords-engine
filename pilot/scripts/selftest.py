"""Self-test: known-value checks of the interval and TF-IDF helpers, the 8-of-N exemplar sampling path, and an
end-to-end dry run of every script on fabricated responses inside a temporary copy of the pilot directory.

Run: python3 scripts/selftest.py. It never touches the real pilot outputs.
"""
from __future__ import annotations

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
import common  # noqa: E402


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
        for name in ("seeds.json", "prompts"):
            src = HERE.parent / name
            (shutil.copytree if src.is_dir() else shutil.copy)(src, tmp / name)
        env = {**os.environ, "PILOT_DIR": str(tmp)}

        def run(script: str, *args: str) -> str:
            out = subprocess.run([sys.executable, str(HERE / script), *args], env=env, capture_output=True, text=True,
                                 check=False)
            check(out.returncode == 0, f"{script} {' '.join(args)}\n{out.stdout}{out.stderr}")
            return out.stdout
        run("plan_calls.py")
        calls = json.loads((tmp / "calls.json").read_text())["calls"]
        r = random.Random(1)
        gen = {"calls": [{"id": c["id"], "arm": c["arm"], "cell": c["cell"],
                          "attempts": fake_response(c, r, broken_first=(c["id"] == calls[3]["id"]))} for c in calls]}
        (tmp / "wf_gen.json").write_text(json.dumps(gen))
        run("parse_generation.py", str(tmp / "wf_gen.json"))
        run("build_checker_set.py")
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
        run("parse_checker.py", str(tmp / "wf_chk.json"))
        run("make_review_sheet.py")
        run("compute_summary.py")
        s = json.loads((tmp / "summary.json").read_text())
        check(s["run"]["n_retried_calls"] == 1, "one retried call recorded")
        for a in ("A", "B"):  # regression: a bootstrap that counted copy pairs put the interval above the estimate
            e = s["E3"]["arm_mean_of_cells"][a]
            check(e["lo"] <= e["mean"] <= e["hi"], f"arm {a} within-cell bootstrap interval contains the point estimate")
            e = s["E3"]["vs_seeds"][a]
            check(e["lo"] <= e["mean"] <= e["hi"], f"arm {a} vs-seeds bootstrap interval contains the point estimate")
        check(s["E1"]["failure_reasons"].get("template_blank_count_not_1") == 3 and s["E1"]["failure_reasons"].get("not_json") == 3,
              f"format failures counted: {s['E1']['failure_reasons']}")
        check(s["E4"]["checker_specificity_broken"]["unclear_counts_as_miss"]["p"] == 1.0, "specificity computed")
        check(s["review"]["n"] == 40, "review sheet has 40 rows")
        md = (tmp / "summary.md").read_text()
        check("Estimand 5" in md and "—" not in md, "summary.md rendered, no em-dash")
        print("dry run summary.md head:\n" + "\n".join(md.splitlines()[:6]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unit_tests()
    dry_run()
    print("selftest: all checks passed")
