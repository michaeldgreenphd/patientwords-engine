"""Does the measured urgency drop under everyday wording depend on the judge? (exploratory, 2026-11-06)

Owner decision on the decision page, 2026-11-06 (ag-offline-first: "Judge register-bias sensitivity"). The concern,
raised by an Antigravity review: the advice judge grades the assistant's reply, and a reply to a colloquial patient
reads warmer and less clinical. If the judge rates that prose as less urgent, part of the measured urgency drop is
grading, not advice. Three checks, all offline, on data already on main:

1. **Wave 2's registered contrast under other judges.** `mode: rejudge` re-graded every wave-2 run
   (`data/petri/w2_register_contrast.json` `run_list`) with OpenAI GPT-5.4 mini and Claude Haiku 5.5 (campaign
   xjudge-v1, `docs/exploratory/xjudge_20261031.md`). For each judge this builds a scratch copy of each run directory
   with that judge's `judgments.jsonl` and `analysis_rows.jsonl` in place of the judge of record's. It then runs the
   registered analysis's own functions on the copies (`petri_w2_register_contrast.prepare` and `final_analysis`), so
   the triples, comparability rules, tests and wording-row selection are the registered ones. A re-grade's judgments
   do not digest to the source manifest's recorded value, by construction, so the registered script would refuse
   them. Each file is verified by its own verifier first instead: the source run by `petri_audit.manifest.verify_run`,
   the re-grade by `petri_audit.rejudge.verify_output`. Only after both pass is the source-digest check skipped for
   the copies. The judge of record goes through the same harness as a control, and must reproduce the committed
   result. This is NOT the registered analysis: it is a sensitivity analysis of it, outside every registered claim.
2. **Single-turn advice: the judge against the human coder, by arm.** The blinded owner coding
   (`data/advice/human/`, 25 responses) joined to the judge of record's tier by response hash. Signed difference in tier
   steps, judge minus human.
3. **Single-turn advice: the judge against the Jev classifier, by arm.** The published Jev calibration cases
   (`data/jev_calibration.json` in the site checkout, 1,810 responses; the arm is in each case key). Signed difference,
   Jev minus judge, with a percentile bootstrap over responses (seeded). Responses to one stimulus from several models
   are not independent, so the intervals are labelled unclustered.

None of these is a human-validated measure of urgency. Agreement among LLM judges cannot rule out a bias they share;
check 2 is the only non-LLM reference, and at 8-9 responses per arm it can detect only large biases.

Usage:
  python scripts/judge_register_sensitivity.py --out /tmp/judge_register_sensitivity.json
      [--site ../patientwords] [--judges openrouter-openai-gpt-5.4-mini openrouter-anthropic-claude-haiku-5.5]
      [--seed 20261106] [--bootstrap 2000]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import petri_w2_register_contrast as w2  # noqa: E402
from petri_audit.manifest import verify_run  # noqa: E402
from petri_audit.rejudge import verify_output  # noqa: E402

W2_RESULT = ROOT / "data" / "petri" / "w2_register_contrast.json"
REJUDGE_DIR = ROOT / "data" / "petri" / "rejudge"
RUNS_DIR = ROOT / "data" / "petri" / "runs"
OF_RECORD = "of_record"
DEFAULT_JUDGES = ("openrouter-openai-gpt-5.4-mini", "openrouter-anthropic-claude-haiku-5.5")
SWAPPED = ("judgments.jsonl", "analysis_rows.jsonl")


def _test(t: dict[str, Any]) -> dict[str, Any]:
    return {k: t.get(k) for k in ("triples", "negative", "positive", "tied", "p", "significant", "direction")}


def summarize(out: dict[str, Any]) -> dict[str, Any]:
    """The rows of final_analysis this report compares across judges."""
    s2, s3, s4 = out["section_10_2"], out["section_10_3"], out["section_10_4"]
    eff = s2["effect_size"]
    return {
        "primary": _test(s2["primary_sign_test"]),
        "scenario_gate": {k: s2["scenario_gate"].get(k) for k in ("scenarios", "p", "significant", "direction")},
        "wording_row": s2["wording"].get("row_id"),
        "effect": {"triples": eff.get("triples"), "proportion_D_negative": eff.get("proportion_D_negative"),
                   "median_D": eff.get("median_D"), "mean_D": eff.get("mean_D")},
        "decomposition": {k: _test(v) for k, v in s3["tests"].items()},
        "decomposition_holm": {k: {"p_holm": v.get("p_holm"), "significant_after_holm": v.get("significant_after_holm")}
                               for k, v in s3["holm"].items()},
        "decomposition_statement": s3["statement"]["statement_id"],
        "sensitivity": {k: _test(v) for k, v in s4.items() if isinstance(v, dict) and "negative" in v},
    }


def w2_under_judge(judge: str, scratch: Path) -> dict[str, Any]:
    """final_analysis over the wave-2 runs with `judge`'s judgments in place of the judge of record's."""
    run_list = json.loads(W2_RESULT.read_text(encoding="utf-8"))["run_list"]
    copies = []
    for rel in run_list:
        src = ROOT / rel
        problems = verify_run(src)
        if problems:
            raise SystemExit(f"{rel}: the source run does not verify: {problems}")
        judged = src if judge == OF_RECORD else REJUDGE_DIR / judge / src.name
        if judge != OF_RECORD:
            problems = verify_output(judged, RUNS_DIR)
            if problems:
                raise SystemExit(f"{judged}: the re-grade does not verify: {problems}")
        dst = scratch / judge / src.name
        dst.mkdir(parents=True)
        for f in src.iterdir():
            if f.is_file() and f.name not in SWAPPED:
                shutil.copy2(f, dst / f.name)
        for name in SWAPPED:
            shutil.copy2(judged / name, dst / name)
        copies.append(dst)
    if judge == OF_RECORD:
        prep = w2.prepare(copies)
    else:
        registered = w2.verify_run
        w2.verify_run = lambda path: []  # every file was verified above by its own verifier
        try:
            prep = w2.prepare(copies)
        finally:
            w2.verify_run = registered
    return w2.final_analysis(prep)


def _mean(xs: list[int]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def human_vs_judge() -> dict[str, Any]:
    """Judge-of-record tier minus the blinded human tier, per arm (check 2)."""
    human = ROOT / "data" / "advice" / "human"
    keymap = json.loads((human / "coding_keymap.json").read_text(encoding="utf-8"))["map"]
    codings = {}
    for f in sorted(human.glob("codings_*.json")):
        codings.update({c["coding_id"]: c for c in json.loads(f.read_text(encoding="utf-8"))["codings"]})
    order = [t["id"] for t in json.loads((ROOT / "data" / "advice_rubric.draft.json").read_text(encoding="utf-8"))["tiers"]]
    need = {v["response_sha256"] for v in keymap.values()}
    machine: dict[str, str] = {}
    for f in sorted((ROOT / "data" / "advice").glob("judgments_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            j = json.loads(line)
            if j.get("response_sha256") in need and j.get("tier") in order:
                machine.setdefault(j["response_sha256"], j["tier"])
    by: dict[str, list[int]] = {}
    for cid, km in keymap.items():
        c, m = codings.get(cid), machine.get(km["response_sha256"])
        if c and c.get("tier") in order and m:
            by.setdefault(km["arm"], []).append(order.index(m) - order.index(c["tier"]))
    return {arm: {"n": len(d), "judge_minus_human": dict(sorted(Counter(d).items())), "mean": _mean(d)}
            for arm, d in sorted(by.items())}


def jev_vs_judge(site: Path, seed: int, resamples: int) -> dict[str, Any] | None:
    """Jev tier minus judge-of-record tier, per arm, with an unclustered bootstrap (check 3)."""
    path = site / "data" / "jev_calibration.json"
    if not path.is_file():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    order = d["tier_order"]
    by: dict[str, list[int]] = {}
    for key, v in d["cases_summary"].items():
        m = re.search(r"#\d+_(clinical|patient|translated)_", key)
        if m and v.get("primary_judge_tier") in order and v.get("pred_tier") in order:
            by.setdefault(m.group(1), []).append(order.index(v["pred_tier"]) - order.index(v["primary_judge_tier"]))
    rng = random.Random(seed)
    out = {}
    for arm, xs in sorted(by.items()):
        boots = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(resamples))
        out[arm] = {"n": len(xs), "exact": round(xs.count(0) / len(xs), 4), "mean_jev_minus_judge": _mean(xs),
                    "interval_95_unclustered": [round(boots[int(0.025 * resamples)], 4),
                                                round(boots[int(0.975 * resamples) - 1], 4)],
                    "judge_lower": sum(1 for x in xs if x > 0), "judge_higher": sum(1 for x in xs if x < 0)}
    return {"source": str(path.relative_to(site)), "seed": seed, "resamples": resamples, "by_arm": out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--site", type=Path, default=ROOT.parent / "patientwords")
    ap.add_argument("--judges", nargs="+", default=list(DEFAULT_JUDGES))
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args(argv)
    report: dict[str, Any] = {"exploratory": True, "seed": args.seed, "wave2": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for judge in (OF_RECORD, *args.judges):
            report["wave2"][judge] = summarize(w2_under_judge(judge, Path(tmp)))
    committed = summarize(json.loads(W2_RESULT.read_text(encoding="utf-8")))
    report["wave2_control_reproduces_committed"] = report["wave2"][OF_RECORD] == committed
    report["single_turn_human_vs_judge"] = human_vs_judge()
    report["single_turn_jev_vs_judge"] = jev_vs_judge(args.site, args.seed, args.bootstrap)
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0 if report["wave2_control_reproduces_committed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
