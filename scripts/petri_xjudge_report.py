"""Exploratory cross-vendor judging report for the Petri lane (campaign xjudge-v1, owner approval 2026-10-31).

Two questions, both exploratory and outside every registered analysis:

1. **Do judges from two vendors agree?** Every landed Petri run has a judge of record (Claude Haiku 4.5), and
   `mode: rejudge` re-grades the same transcripts with other judges (an OpenAI model through OpenRouter, Claude Haiku
   5.5) under `data/petri/rejudge/<judge slug>/<stem>/`. A rejudge plans exactly the judgments the judge of record made,
   prompt digest for prompt digest (`scripts/petri_audit/rejudge.py`), so two judges' rows are paired here on the
   judgment's identity (tree, branch, turn, exchange, kind, key) and kept only when both rows carry the same
   `rendered_sha256`. A pair whose digests differ is counted and dropped, never pooled.
   Per (kind, key) and per judge pair it reports the paired count, exact agreement, Cohen's kappa and, for the two
   advice tiers, the linear-weighted kappa and the mean signed difference in tier steps (second judge minus first),
   each with a percentile bootstrap interval that resamples whole conversations (rows of one conversation are not
   independent), seeded with random.Random(--seed). Rows whose value is null or `not_applicable` under either judge
   are left out of agreement and counted beside it.

2. **Is advice to patients who name structural barriers as urgent as advice to matched controls?** The equity v2 seeds
   (`docs/framework/petri_seeds_equity_v2.draft.json`, pairing `data/petri/equity_v2_pairs.draft.json`) give each
   equity scenario a control with the same clinical course; the warning sign arrives at the pairing's `pivot_turn`
   (8) in byte-identical text, and the next turn presses to delay (a shelter bed and fear of being treated as
   drug-seeking, against a work meeting). For each run, judge, pair and register this reports the response-only tier
   at the pivot exchange and each later exchange, whether the reply at each later exchange stays at the pivot reply's
   tier or above ("held"), and the share of emergency tiers. With one epoch these are a handful of conversations per
   target: the report gives counts and differences, no test, and says so.

The tier order is read from the rubric (`data/advice_rubric.draft.json`), never written here, and only rows with
`final_in_exchange` true are used, as in `scripts/petri_w2_register_contrast.py`. The report records the inputs it read
(path and sha256 of each judgments file), the seed, and the commit.

Usage:
  python scripts/petri_xjudge_report.py --out-dir /tmp/xjudge [--runs-dir data/petri/runs]
      [--rejudge-dir data/petri/rejudge] [--extra-rejudge-dir DIR ...] [--extra-runs-dir DIR ...]
      [--seed 20261031] [--bootstrap 2000]

`--extra-*` dirs hold outputs that are not on this checkout's branch (for example landed outputs from an unmerged
branch, exported with `git archive`); the report labels every run and re-grade with the directory it came from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "data" / "advice_rubric.draft.json"
EQUITY_PAIRS = ROOT / "data" / "petri" / "equity_v2_pairs.draft.json"
TIER_KEYS = ("response_only", "contextual")
NOT_APPLICABLE = "not_applicable"
DEFAULT_SEED = 20261031
DEFAULT_BOOTSTRAP = 2000


# ------------------------------------------------------------------ inputs

@dataclass
class JudgeSet:
    """The judgments one judge made over one source run."""
    stem: str
    judge: str
    role: str                    # "judge_of_record" or "rejudge"
    origin: str                  # the directory the file came from
    path: Path
    rows: list[dict] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def single_judge(rows: list[dict], path: Path) -> str:
    judges = {r.get("judge_model") for r in rows}
    if len(judges) != 1:
        raise ValueError(f"{path}: expected one judge_model, found {sorted(map(str, judges))}")
    return str(next(iter(judges)))


def load_judge_sets(runs_dirs: Iterable[Path], rejudge_dirs: Iterable[Path]) -> list[JudgeSet]:
    """Judge-of-record judgments under each runs dir (`<stem>/judgments.jsonl`) and every re-grade under each rejudge
    dir (`<slug>/<stem>/judgments.jsonl`). A file with more than one judge model is refused."""
    sets: list[JudgeSet] = []
    for runs_dir in runs_dirs:
        for path in sorted(runs_dir.glob("run_*/judgments.jsonl")):
            rows = read_jsonl(path)
            if rows:
                sets.append(JudgeSet(path.parent.name, single_judge(rows, path), "judge_of_record", str(runs_dir),
                                     path, rows))
    for rejudge_dir in rejudge_dirs:
        for path in sorted(rejudge_dir.glob("*/run_*/judgments.jsonl")):
            rows = read_jsonl(path)
            if rows:
                sets.append(JudgeSet(path.parent.name, single_judge(rows, path), "rejudge", str(rejudge_dir),
                                     path, rows))
    return sets


def tier_rank() -> dict[str, int]:
    rubric = json.loads(RUBRIC.read_text(encoding="utf-8"))
    return {t["id"]: i for i, t in enumerate(rubric["tiers"])}


# ------------------------------------------------------------------ agreement

def identity(row: dict) -> tuple:
    return (row["tree_id"], row["branch_id"], row["turn_id"], row.get("exchange_index"), row["kind"], row["key"])


def usable(row: dict) -> bool:
    return row.get("value") is not None and row.get("value") != NOT_APPLICABLE


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Unweighted Cohen's kappa; None when undefined (no pairs, or chance agreement 1)."""
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[c] * right[c] for c in set(left) | set(right)) / (n * n)
    return None if expected >= 1.0 else (observed - expected) / (1.0 - expected)


def weighted_kappa(pairs: list[tuple[int, int]], k: int) -> float | None:
    """Linear-weighted kappa over ranks 0..k-1; None when undefined."""
    n = len(pairs)
    if not n or k < 2:
        return None
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    disagree_obs = sum(abs(a - b) for a, b in pairs) / (n * (k - 1))
    disagree_exp = sum(left[i] * right[j] * abs(i - j) for i in left for j in right) / (n * n * (k - 1))
    return None if disagree_exp == 0 else 1.0 - disagree_obs / disagree_exp


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def bootstrap_ci(clusters: dict[str, list], stat, reps: int, rng: random.Random) -> tuple[float, float] | None:
    """Percentile 95% interval of stat(pooled rows) over conversations resampled with replacement."""
    keys = sorted(clusters)
    if len(keys) < 2 or reps <= 0:
        return None
    draws: list[float] = []
    for _ in range(reps):
        pooled = [row for key in (rng.choice(keys) for _ in keys) for row in clusters[key]]
        value = stat(pooled)
        if value is not None:
            draws.append(value)
    if len(draws) < reps * 0.9:
        return None
    return percentile(draws, 0.025), percentile(draws, 0.975)


def pair_judges(first: JudgeSet, second: JudgeSet) -> dict[str, Any]:
    """Pair two judges' rows over one source run on the judgment's identity, final-in-exchange rows only."""
    a = {identity(r): r for r in first.rows if r.get("final_in_exchange", True)}
    b = {identity(r): r for r in second.rows if r.get("final_in_exchange", True)}
    shared = sorted(set(a) & set(b), key=str)
    digest_mismatch = [k for k in shared if a[k].get("rendered_sha256") != b[k].get("rendered_sha256")]
    paired = [(a[k], b[k]) for k in shared if k not in set(digest_mismatch)]
    return {"only_first": len(set(a) - set(b)), "only_second": len(set(b) - set(a)),
            "digest_mismatch": len(digest_mismatch), "paired": paired}


def agreement_table(paired_rows: list[tuple[dict, dict]], ranks: dict[str, int], reps: int,
                    rng: random.Random) -> list[dict]:
    by_dim: dict[tuple[str, str], list[tuple[dict, dict]]] = defaultdict(list)
    for ra, rb in paired_rows:
        by_dim[(ra["kind"], ra["key"])].append((ra, rb))
    out = []
    for (kind, key), rows in sorted(by_dim.items()):
        both = [(ra, rb) for ra, rb in rows if usable(ra) and usable(rb)]
        na_split = sum(1 for ra, rb in rows if (ra.get("value") == NOT_APPLICABLE) != (rb.get("value") == NOT_APPLICABLE))
        null_either = sum(1 for ra, rb in rows if ra.get("value") is None or rb.get("value") is None)
        values = [(str(ra["value"]), str(rb["value"])) for ra, rb in both]
        clusters: dict[str, list] = defaultdict(list)
        for (ra, rb), v in zip(both, values):
            clusters[ra["conversation_id"]].append(v)
        entry: dict[str, Any] = {
            "kind": kind, "key": key, "rows": len(rows), "paired_usable": len(both),
            "not_applicable_disagreements": na_split, "null_under_either": null_either,
            "exact_agreement": (sum(x == y for x, y in values) / len(values)) if values else None,
            "kappa": cohen_kappa(values),
            "kappa_ci95": bootstrap_ci(clusters, cohen_kappa, reps, rng),
            "first_values": dict(Counter(x for x, _ in values)), "second_values": dict(Counter(y for _, y in values)),
            "conversations": len(clusters),
        }
        if kind == "tier" and values and all(x in ranks and y in ranks for x, y in values):
            ranked = [(ranks[x], ranks[y]) for x, y in values]
            rclusters: dict[str, list] = defaultdict(list)
            for (ra, _), r in zip(both, ranked):
                rclusters[ra["conversation_id"]].append(r)
            k = len(ranks)
            entry["weighted_kappa"] = weighted_kappa(ranked, k)
            entry["weighted_kappa_ci95"] = bootstrap_ci(rclusters, lambda p: weighted_kappa(p, k), reps, rng)
            mean_diff = lambda p: (sum(y - x for x, y in p) / len(p)) if p else None  # noqa: E731
            entry["mean_step_second_minus_first"] = mean_diff(ranked)
            entry["mean_step_ci95"] = bootstrap_ci(rclusters, mean_diff, reps, rng)
            entry["second_higher"] = sum(y > x for x, y in ranked)
            entry["second_lower"] = sum(y < x for x, y in ranked)
        out.append(entry)
    return out


# ------------------------------------------------------------------ equity contrast

def equity_contrast(js: JudgeSet, pairs_spec: dict, ranks: dict[str, int]) -> list[dict]:
    """Per pair and register: the response-only tier at the pivot exchange and each later one, equity against control.

    Exchanges are the controller's `exchange_index` on the root branch; the pivot exchange is the pairing's
    `pivot_turn` (the seeds' user turn n is exchange n). A reply is "held" when its tier ranks at or above the
    pivot reply's."""
    pivot = int(pairs_spec["pivot_turn"])
    tiers: dict[tuple[str, str], dict[int, str]] = defaultdict(dict)
    for r in js.rows:
        if (r["kind"], r["key"]) != ("tier", "response_only") or r.get("branch_id") != "root":
            continue
        if not r.get("final_in_exchange", True) or not usable(r):
            continue
        tiers[(r["seed_id"], r["condition_id"])][int(r["exchange_index"])] = str(r["value"])
    out = []
    for pair in pairs_spec["pairs"]:
        for arm in sorted({c for (s, c) in tiers if s in (pair["equity"], pair["control"])}):
            row: dict[str, Any] = {"run": js.stem, "judge": js.judge, "equity_seed": pair["equity"],
                                   "control_seed": pair["control"], "register": arm}
            for side, seed in (("equity", pair["equity"]), ("control", pair["control"])):
                series = tiers.get((seed, arm), {})
                later = sorted(e for e in series if e > pivot)
                at_pivot = series.get(pivot)
                row[side] = {
                    "pre_pivot_tiers": [series.get(e) for e in range(1, pivot)],
                    "pivot_tier": at_pivot,
                    "later_tiers": {e: series[e] for e in later},
                    "held_after_pivot": (all(ranks[series[e]] >= ranks[at_pivot] for e in later)
                                         if at_pivot in ranks and later else None),
                    "emergency_share_from_pivot": (sum(series[e] == "emergency" for e in [pivot, *later]) /
                                                   len([pivot, *later]) if at_pivot is not None else None),
                }
            out.append(row)
    return out


def summarize_equity(rows: list[dict], ranks: dict[str, int]) -> list[dict]:
    """Per run and judge: held counts and emergency shares from the pivot on, and the mean tier rank before the
    pivot (exchanges 1 to pivot-1, where the equity seeds carry the housing, insurance and stigma details), equity
    against control."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["run"], r["judge"])].append(r)
    out = []
    for (run, judge), rs in sorted(groups.items()):
        entry: dict[str, Any] = {"run": run, "judge": judge, "conversations_per_side": len(rs)}
        for side in ("equity", "control"):
            held = [r[side]["held_after_pivot"] for r in rs if r[side]["held_after_pivot"] is not None]
            shares = [r[side]["emergency_share_from_pivot"] for r in rs
                      if r[side]["emergency_share_from_pivot"] is not None]
            pre = [ranks[t] for r in rs for t in r[side]["pre_pivot_tiers"] if t in ranks]
            entry[side] = {"held": sum(held), "held_of": len(held),
                           "mean_emergency_share_from_pivot": (sum(shares) / len(shares)) if shares else None,
                           "mean_pre_pivot_rank": (sum(pre) / len(pre)) if pre else None, "pre_pivot_rows": len(pre)}
        out.append(entry)
    return out


# ------------------------------------------------------------------ report

def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def fmt(x: Any, digits: int = 2) -> str:
    if x is None:
        return "—"
    if isinstance(x, tuple | list) and len(x) == 2:
        return f"[{fmt(x[0], digits)}, {fmt(x[1], digits)}]"
    return f"{x:.{digits}f}" if isinstance(x, float) else str(x)


def build_report(sets: list[JudgeSet], seed: int, reps: int) -> dict[str, Any]:
    ranks = tier_rank()
    rng = random.Random(seed)
    by_stem: dict[str, list[JudgeSet]] = defaultdict(list)
    for js in sets:
        by_stem[js.stem].append(js)
    agreement = []
    for stem, group in sorted(by_stem.items()):
        records = [g for g in group if g.role == "judge_of_record"]
        others = [g for g in group if g.role == "rejudge"]
        # every re-grade against the judge of record, and each pair of re-grades with each other
        comparisons = [(r, o) for r in records for o in others]
        comparisons += [(others[i], others[j]) for i in range(len(others)) for j in range(i + 1, len(others))]
        for first, second in comparisons:
            p = pair_judges(first, second)
            agreement.append({"run": stem, "first": first.judge, "first_origin": first.origin,
                              "second": second.judge, "second_origin": second.origin,
                              "only_first": p["only_first"], "only_second": p["only_second"],
                              "digest_mismatch": p["digest_mismatch"], "paired_rows": len(p["paired"]),
                              "dimensions": agreement_table(p["paired"], ranks, reps, rng)})
    pairs_spec = json.loads(EQUITY_PAIRS.read_text(encoding="utf-8"))
    equity_seeds = {s for p in pairs_spec["pairs"] for s in (p["equity"], p["control"])}
    equity_rows = [row for js in sets if any(r.get("seed_id") in equity_seeds for r in js.rows)
                   for row in equity_contrast(js, pairs_spec, ranks)]
    return {
        "status": "exploratory (campaign xjudge-v1); not a registered analysis and not a study claim",
        "commit": git_commit(), "bootstrap_seed": seed, "bootstrap_reps": reps,
        "tier_order": sorted(ranks, key=ranks.get),
        "inputs": [{"run": js.stem, "judge": js.judge, "role": js.role, "origin": js.origin,
                    "path": str(js.path), "sha256": sha256_file(js.path), "rows": len(js.rows)} for js in sets],
        "agreement": agreement,
        "equity_contrast": equity_rows,
        "equity_summary": summarize_equity(equity_rows, ranks),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Petri cross-vendor judging report (exploratory)", "",
             f"Status: {report['status']}. Commit {report['commit']}; bootstrap seed {report['bootstrap_seed']}, "
             f"{report['bootstrap_reps']} conversation-level resamples.", "", "## Inputs", "",
             "| Run | Judge | Role | Rows | Origin |", "|---|---|---|---|---|"]
    for i in report["inputs"]:
        lines.append(f"| {i['run']} | `{i['judge']}` | {i['role']} | {i['rows']} | {i['origin']} |")
    lines += ["", "## Judge agreement", ""]
    for a in report["agreement"]:
        lines += [f"### {a['run']}: `{a['first']}` vs `{a['second']}`", "",
                  f"Paired rows {a['paired_rows']}; only first {a['only_first']}, only second {a['only_second']}, "
                  f"prompt-digest mismatches dropped {a['digest_mismatch']}.", "",
                  "| Dimension | Usable pairs | Exact | κ [95% CI] | Weighted κ [95% CI] | Mean step (2nd−1st) [95% CI] |"
                  " 2nd higher / lower | N/A splits |",
                  "|---|---|---|---|---|---|---|---|"]
        for d in a["dimensions"]:
            lines.append(
                f"| {d['kind']}/{d['key']} | {d['paired_usable']} | {fmt(d['exact_agreement'])} | "
                f"{fmt(d['kappa'])} {fmt(d['kappa_ci95'])} | {fmt(d.get('weighted_kappa'))} "
                f"{fmt(d.get('weighted_kappa_ci95'))} | {fmt(d.get('mean_step_second_minus_first'))} "
                f"{fmt(d.get('mean_step_ci95'))} | {fmt(d.get('second_higher'))} / {fmt(d.get('second_lower'))} | "
                f"{d['not_applicable_disagreements']} |")
        lines.append("")
    if report["equity_summary"]:
        lines += ["## Equity v2: advice after the warning sign", "",
                  "Held = every reply after the pivot exchange ranks at or above the pivot reply's tier. "
                  "Counts of conversations; no test is run on this many.", "",
                  "Pre-pivot rank: mean tier rank over exchanges before the warning sign (0 = self_care, 3 = emergency).",
                  "",
                  "| Run | Judge | Equity held | Control held | Equity emergency share | Control emergency share |"
                  " Equity pre-pivot rank | Control pre-pivot rank |",
                  "|---|---|---|---|---|---|---|---|"]
        for s in report["equity_summary"]:
            e, c = s["equity"], s["control"]
            lines.append(f"| {s['run']} | `{s['judge']}` | {e['held']}/{e['held_of']} | {c['held']}/{c['held_of']} | "
                         f"{fmt(e['mean_emergency_share_from_pivot'])} | {fmt(c['mean_emergency_share_from_pivot'])} | "
                         f"{fmt(e['mean_pre_pivot_rank'])} | {fmt(c['mean_pre_pivot_rank'])} |")
        lines += ["", "| Run | Judge | Pair | Register | Equity pivot → later | Control pivot → later |",
                  "|---|---|---|---|---|---|"]
        for r in report["equity_contrast"]:
            def path(side: dict) -> str:
                return f"{side['pivot_tier']} → {', '.join(side['later_tiers'].values()) or '—'}"
            lines.append(f"| {r['run']} | `{r['judge']}` | {r['equity_seed'].replace('pw-petri-equity-v2-', '')} | "
                         f"{r['register']} | {path(r['equity'])} | {path(r['control'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs-dir", type=Path, default=ROOT / "data" / "petri" / "runs")
    ap.add_argument("--rejudge-dir", type=Path, default=ROOT / "data" / "petri" / "rejudge")
    ap.add_argument("--extra-runs-dir", type=Path, action="append", default=[])
    ap.add_argument("--extra-rejudge-dir", type=Path, action="append", default=[])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    sets = load_judge_sets([args.runs_dir, *args.extra_runs_dir], [args.rejudge_dir, *args.extra_rejudge_dir])
    if not sets:
        print("refused: no judgments found")
        return 3
    report = build_report(sets, args.seed, args.bootstrap)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "xjudge_report.json").write_text(json.dumps(report, indent=1, default=list) + "\n",
                                                     encoding="utf-8")
    (args.out_dir / "xjudge_report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out_dir / 'xjudge_report.json'} and xjudge_report.md "
          f"({len(sets)} judge sets, {len(report['agreement'])} comparisons)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
