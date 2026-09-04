"""Export inter-judge tier agreement into the site payload for the methods page.

Reads every judgments archive under data/advice/, pairs each response's primary
judgment (bare Anthropic model id) with its secondary judgment (provider-spec
judge, appended beside the primary for inter-judge agreement only), and writes
data/judge_agreement.json — a 4x4 tier confusion matrix plus the headline
agreement rates the methods page renders. Secondary judgments never drive
published tiers anywhere in the pipeline (advice_eval.is_secondary_judge gates
them out of the scenario exporter); this payload is the disclosure of how far
the two graders agree.

Safety properties, matching the other site exporters:
- refuses (exit 3, site file untouched) when no paired judgments exist;
- publishes tier labels and counts only — never judge raw output, never
  response or stimulus text;
- consistency-checks its own headline numbers against the matrix before
  writing (exact = trace, n = cell sum).

Usage:
  python scripts/export_judge_agreement.py \
      [--judgments-glob "data/advice/judgments_*.jsonl"] \
      [--rubric data/advice_rubric.draft.json] \
      --out data/judge_agreement.json --site ../patientwords
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_advice_eval():
    path = Path(__file__).resolve().parent / "advice_eval.py"
    spec = importlib.util.spec_from_file_location("advice_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _refuse(reason: str) -> "SystemExit":
    print(f"refused: {reason} (site file left untouched)")
    return SystemExit(3)


def build_payload(judgment_paths, ae, tier_order: list[str]) -> dict:
    rank = {t: i for i, t in enumerate(tier_order)}
    # response_sha256 -> {"primary": row, "secondary": row}; later passes
    # overwrite earlier ones, the same overwrite rule the scenario exporter
    # applies to primary tiers.
    paired: dict[str, dict] = {}
    coverage = []
    rubric_version = None
    secondary_specs: dict[str, int] = {}
    window: list[str] = []
    for path in judgment_paths:
        n_primary = n_secondary = 0
        for j in ae._read_jsonl(path):
            if j.get("tier") not in rank:
                continue
            slot = "secondary" if ae.is_secondary_judge(j.get("judge_model")) else "primary"
            if slot == "secondary":
                n_secondary += 1
                secondary_specs[j["judge_model"]] = secondary_specs.get(j["judge_model"], 0) + 1
                if j.get("judged_utc"):
                    window.append(j["judged_utc"])
            else:
                n_primary += 1
                rubric_version = j.get("rubric_version") or rubric_version
            paired.setdefault(j["response_sha256"], {})[slot] = j["tier"]
        coverage.append({
            "judgments_file": str(path).replace(str(REPO_ROOT) + "/", ""),
            "n_primary": n_primary,
            "n_secondary": n_secondary,
        })

    both = [(v["primary"], v["secondary"]) for v in paired.values()
            if "primary" in v and "secondary" in v]
    if not both:
        raise _refuse("no response carries both a primary and a secondary judgment")

    matrix = [[0] * len(tier_order) for _ in tier_order]
    exact = within_one = sec_up = pri_up = 0
    for p, s in both:
        matrix[rank[p]][rank[s]] += 1
        d = rank[s] - rank[p]
        if d == 0:
            exact += 1
        if abs(d) <= 1:
            within_one += 1
        if d > 0:
            sec_up += 1
        elif d < 0:
            pri_up += 1
    n = len(both)
    if sum(map(sum, matrix)) != n or sum(matrix[i][i] for i in range(len(tier_order))) != exact:
        raise _refuse("internal consistency check failed (matrix does not reproduce headline counts)")

    return {
        "generated_utc": ae.utc_now_iso(),
        "engine_sha": ae.engine_sha(),
        "rubric_version": rubric_version,
        "tier_order": tier_order,
        "primary_judge": "claude-haiku-4-5",
        "secondary_judges": secondary_specs,
        "secondary_window_utc": {"first": min(window), "last": max(window)} if window else None,
        "n_paired": n,
        "exact": {"n": exact, "rate": round(exact / n, 4)},
        "within_one": {"n": within_one, "rate": round(within_one / n, 4)},
        "lean": {"secondary_more_urgent": sec_up, "primary_more_urgent": pri_up},
        # matrix[i][j] = responses the primary judge put in tier_order[i] and the
        # secondary judge put in tier_order[j]
        "matrix": matrix,
        "coverage": coverage,
        "policy": "secondary judgments are disclosure only; published tiers come from the primary judge",
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--judgments-glob", default="data/advice/judgments_*.jsonl")
    parser.add_argument("--rubric", default="data/advice_rubric.draft.json",
                        help="rubric path; its tier list fixes the matrix axis order")
    parser.add_argument("--out", default="data/judge_agreement.json")
    parser.add_argument("--site", default=None, help="frontend checkout; copies the payload into <site>/data/")
    args = parser.parse_args(argv)

    ae = _load_advice_eval()
    rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
    tier_order = [t["id"] for t in rubric["tiers"]]
    paths = sorted(Path(p) for p in glob.glob(args.judgments_glob))
    if not paths:
        raise _refuse(f"no judgments files match {args.judgments_glob}")
    payload = build_payload(paths, ae, tier_order)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote n_paired={payload['n_paired']} exact={payload['exact']['rate']:.1%} -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "judge_agreement.json"
        site_copy.parent.mkdir(parents=True, exist_ok=True)
        site_copy.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"site copy -> {site_copy}")


if __name__ == "__main__":
    main()
