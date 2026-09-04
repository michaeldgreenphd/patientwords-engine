"""Crosswalk: draft urgency lexicon vs PAB's clinician-validated triage rubric.

Implements docs/pab_crosswalk_spec_20260804.md exactly — the spec (endpoints,
direction predictions, severity->floor map, exclusion rules) was committed
before any agreement number existed; this script computes only what it
pre-registers. See the spec for why the naive urgency-mass-vs-score test is
wrong and the de-escalation-gap test is right.

Reads PatientAgentBench run directories strictly as data (Layer 2: nothing of
theirs is imported), scores each conversation's assistant turns with the draft
tier vocabulary, and tests whether the lexicon-detected de-escalation gap
predicts the jury's triage score. Output carries counts and statistics only —
no conversation text, no vocabulary terms (the transcripts are CC-BY-NC and
medical terms stay in data files).

Usage:
  python scripts/pab_tier_crosswalk.py --run <run-dir> [--run <run-dir> ...]
      [--tiers data/urgency_tiers.draft.json]
      [--map data/pab_severity_tier_map.json] [--out ops/pab_crosswalk.json]

Each run dir holds benchmark_cases.json plus experiment subdirs with
conversations.json / evaluations.json (upstream's output layout).
"""

from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TOKEN_RE = re.compile(r"[a-z][a-z']*")

SEED = 7
BOOT = 5000
PERMS = 10000


# ---------------------------------------------------------------- lexicon side

def load_tiers(path: Path) -> dict:
    vocab = json.loads(path.read_text(encoding="utf-8"))
    return {tok: spec.get("tier") for tok, spec in vocab.get("tokens", {}).items()
            if spec.get("tier") is not None}


def lexicon_signal(text: str, tiers: dict) -> dict | None:
    """Occurrence-weighted care-level signal over one conversation's assistant text.

    None when no tier-assigned token appears (no signal — an exclusion, never a
    zero, which would fabricate a maximal de-escalation gap).
    """
    counts: dict[int, int] = {}
    for tok in _TOKEN_RE.findall(text.lower()):
        tier = tiers.get(tok)
        if tier is not None:
            counts[tier] = counts.get(tier, 0) + 1
    total = sum(counts.values())
    if not total:
        return None
    mean = sum(t * n for t, n in counts.items()) / total
    return {"mean_tier": round(mean, 4), "max_tier": max(counts),
            "tier_token_occurrences": total}


# ------------------------------------------------------------------- run side

def iter_conversations(run_dir: Path):
    """Yield (experiment_name, evaluation_entry, case) joined via the scenario
    text — the transcript contract's pair key (case_id carries arm suffixes)."""
    cases = {}
    cases_path = run_dir / "benchmark_cases.json"
    if cases_path.exists():
        for c in json.loads(cases_path.read_text(encoding="utf-8")):
            cases[c.get("patient_story")] = c
    for exp in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        ev_path = exp / "evaluations.json"
        if not ev_path.exists():
            continue
        for entry in json.loads(ev_path.read_text(encoding="utf-8")):
            yield exp.name, entry, cases.get(entry.get("scenario"))


def assistant_text(entry: dict) -> str:
    msgs = entry.get("conversation") or []
    return " ".join(str(m.get("content") or "") for m in msgs if m.get("type") == "ai")


def build_rows(run_dirs, tiers, floors, clinical_tasks):
    rows, excl = [], {"no_case_join": 0, "non_clinical_task": 0,
                      "no_lexicon_signal": 0, "no_triage_score": 0}
    # Diagnostics are categorical labels and counts only (license-clean): which
    # task_type strings the cases actually carry, and where joins fail, so an
    # all-exclusions result is attributable without opening the artifact by
    # hand (n=0 on run 31140382136 was undiagnosable from the counts alone).
    diag = {"task_types_seen": {}, "join_misses_by_experiment": {}}
    for rd in run_dirs:
        for exp, entry, case in iter_conversations(Path(rd)):
            if case is None:
                excl["no_case_join"] += 1
                diag["join_misses_by_experiment"][exp] = (
                    diag["join_misses_by_experiment"].get(exp, 0) + 1)
                continue
            tt = case.get("task_type")
            diag["task_types_seen"][str(tt)] = diag["task_types_seen"].get(str(tt), 0) + 1
            if clinical_tasks and tt not in clinical_tasks:
                excl["non_clinical_task"] += 1
                continue
            triage = (entry.get("evaluation") or {}).get("rubric_scores", {}).get("triage_quality")
            if triage is None:
                excl["no_triage_score"] += 1
                continue
            sig = lexicon_signal(assistant_text(entry), tiers)
            if sig is None:
                excl["no_lexicon_signal"] += 1
                continue
            floor = floors.get(case.get("severity_level"))
            if floor is None:
                excl.setdefault("unmapped_severity", 0)
                excl["unmapped_severity"] += 1
                continue
            rows.append({
                "experiment": exp,
                "personality": entry.get("personality"),
                "severity": case.get("severity_level"),
                "floor": floor,
                "triage": float(triage),
                "gap_mean": round(max(0.0, floor - sig["mean_tier"]), 4),
                "gap_max": float(max(0, floor - sig["max_tier"])),
                "signal": sig,
            })
    excl["_diagnostics"] = diag
    return rows, excl


# ------------------------------------------------------------------ statistics

def _rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def endpoint1(rows, rng):
    xs = [r["gap_mean"] for r in rows]
    ys = [r["triage"] for r in rows]
    rho = spearman(xs, ys)
    if rho is None:
        return {"n": len(rows), "rho": None,
                "note": "fewer than 3 usable conversations"}
    boots = []
    n = len(rows)
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        b = spearman([xs[i] for i in idx], [ys[i] for i in idx])
        if b is not None:
            boots.append(b)
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else None
    hi = boots[int(0.975 * len(boots)) - 1] if boots else None
    return {"n": n, "rho": round(rho, 4),
            "ci95_bootstrap": [round(lo, 4), round(hi, 4)] if boots else None,
            "prediction": "rho < 0 if the lexicon measures what the jury measures",
            "underpowered_note": ("pilot n; a CI covering zero reads as "
                                  "'underpowered', never 'no agreement'")}


def endpoint2(rows, rng):
    low = [r["gap_mean"] for r in rows if r["triage"] <= 2]
    high = [r["gap_mean"] for r in rows if r["triage"] >= 4]
    if not low or not high:
        return {"n_low": len(low), "n_high": len(high),
                "note": "a group is empty; separation test not computable"}
    observed = sum(a > b for a in low for b in high) + 0.5 * sum(
        a == b for a in low for b in high)
    observed /= len(low) * len(high)  # rank-biserial-style overlap statistic
    pooled = low + high
    n_low = len(low)
    count = 0
    for _ in range(PERMS):
        rng.shuffle(pooled)
        pl, ph = pooled[:n_low], pooled[n_low:]
        stat = (sum(a > b for a in pl for b in ph)
                + 0.5 * sum(a == b for a in pl for b in ph)) / (len(pl) * len(ph))
        if stat >= observed:
            count += 1
    return {"n_low": len(low), "n_high": len(high),
            "overlap_stat": round(observed, 4),
            "p_one_sided_permutation": round((count + 1) / (PERMS + 1), 4),
            "prediction": "gap larger where the jury scored <=2"}


def descriptive(rows):
    out = {}
    for r in rows:
        key = r["experiment"]
        cell = out.setdefault(key, {"flag_and_low": 0, "flag_and_ok": 0,
                                    "noflag_and_low": 0, "noflag_and_ok": 0})
        flag = r["gap_mean"] > 0
        low = r["triage"] <= 3
        cell["flag_and_low" if flag and low else
             "flag_and_ok" if flag else
             "noflag_and_low" if low else "noflag_and_ok"] += 1
    return out


# ------------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="append", required=True,
                    help="PAB run directory (repeatable; pooled)")
    ap.add_argument("--tiers", default=str(ROOT / "data" / "urgency_tiers.draft.json"))
    ap.add_argument("--map", dest="map_path",
                    default=str(ROOT / "data" / "pab_severity_tier_map.json"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    tiers = load_tiers(Path(args.tiers))
    smap = json.loads(Path(args.map_path).read_text(encoding="utf-8"))
    floors = smap["floors"]
    clinical = smap.get("clinical_task_types") or []

    rows, excl = build_rows(args.run, tiers, floors, clinical)
    rng = random.Random(SEED)
    report = {
        "_": ("Crosswalk per docs/pab_crosswalk_spec_20260804.md: does the draft "
              "urgency lexicon's de-escalation gap predict the PAB jury's triage "
              "score? Agreement pilot bounding a draft instrument with a "
              "clinician-validated one; NOT a validation, and no license to "
              "soften the site's draft label. Counts and statistics only - no "
              "conversation text, no vocabulary terms."),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "spec": "docs/pab_crosswalk_spec_20260804.md",
        "runs": [str(r) for r in args.run],
        "vocabulary": str(Path(args.tiers).name),
        "severity_map": {"floors": floors, "source": str(Path(args.map_path).name)},
        "seed": SEED, "bootstrap": BOOT, "permutations": PERMS,
        "n_rows": len(rows), "exclusions": excl,
        "endpoint1_direction": endpoint1(rows, rng),
        "endpoint2_separation": endpoint2(rows, rng),
        "descriptive_per_experiment": descriptive(rows),
        "sensitivity_perturbed_map": {},
    }
    for name, alt in (smap.get("perturbations") or {}).items():
        alt_rows, _ = build_rows(args.run, tiers, alt, clinical)
        report["sensitivity_perturbed_map"][name] = endpoint1(
            alt_rows, random.Random(SEED))

    out = Path(args.out) if args.out else (
        ROOT / "ops" / f"pab_crosswalk_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out} · n={len(rows)} rows · "
          f"rho={report['endpoint1_direction'].get('rho')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
