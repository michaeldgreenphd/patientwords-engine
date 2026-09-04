"""Tier-vocabulary sensitivity analysis: does the asymmetry survive re-tiering?

Every downgrade count and significance star rests on the owner-reviewed-v1,
domain-review-pending urgency vocabulary. This analysis asks how much of the
next-token downgrade>upgrade asymmetry (and the advice arm's near-null) is an
artifact of the contested assignments, by recomputing everything under
bracketing perturbations of every checklist-flagged token
(data/tier_sensitivity_spec.draft.json, extracted from
docs/tier_review_checklist.md):

  baseline  the v1 vocabulary as published
  exclude   every flagged token removed (its calls become uninformative)
  floor     every flagged token assigned tier 0 (maximally downgrade-friendly
            on the clinical side, upgrade-hostile on the patient side)
  ceiling   every flagged token assigned tier 4 (the reverse extreme)

If a model's downgrades>upgrades holds under all four, no re-tiering of the
flagged set can flip it. The advice arm is checked separately under the
spec's tier-ladder collapses (merging adjacent tiers of the 4-step ladder).

Reads the committed collector row file (urgency_shift.json at the repo root)
and the site advice payload; writes ops/tier_sensitivity.json. $0, offline.

Usage:
  python scripts/tier_sensitivity.py [--rows urgency_shift.json]
      [--tiers data/urgency_tiers.draft.json]
      [--spec data/tier_sensitivity_spec.draft.json]
      [--advice ../patientwords/data/advice_scenarios.json]
      [--out ops/tier_sensitivity.json]
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def sign_test(k_down: int, k_up: int):
    """Two-sided exact sign test (mirrors scripts/urgency_shift.py)."""
    n = k_down + k_up
    if n == 0:
        return None
    k = min(k_down, k_up)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 5)


def perturbed_vocab(vocab: dict, spec: dict, scenario: str) -> dict:
    flagged = set(spec["deciders"]) | set(spec["blockers"])
    out = {k: dict(v) for k, v in vocab.items()}
    if scenario == "baseline":
        return out
    if scenario == "exclude":
        for t in flagged:
            out.pop(t, None)
        return out
    fixed = 0 if scenario == "floor" else 4
    for t in flagged:
        out[t] = {"tier": fixed}
    return out


def tier_of(vocab: dict, token) -> int | None:
    if not token:
        return None
    e = vocab.get(str(token).strip().lower())
    return e["tier"] if e and e.get("tier") is not None else None


def next_token_scenarios(rows: list[dict], vocab: dict, spec: dict) -> dict:
    """Per-model down/up + sign test under each vocabulary scenario.

    Re-tiers each flipped row's top tokens directly (the greedy-continuation
    refinement in the collector applies to a token only when the token itself
    is unclassified; flagged tokens are classified in every scenario except
    exclude, where dropping the call entirely is the intended behavior)."""
    out = {}
    for scen in ("baseline", "exclude", "floor", "ceiling"):
        pv = perturbed_vocab(vocab, spec, scen)
        per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in rows:
            if not r.get("flipped"):
                continue
            tc = tier_of(pv, r.get("top_clinical"))
            tp = tier_of(pv, r.get("top_patient"))
            if tc is None or tp is None:
                continue
            if tp < tc:
                per[r["model"]][0] += 1
            elif tp > tc:
                per[r["model"]][1] += 1
        out[scen] = {
            m: {"downgrades": d, "upgrades": u, "sign_p": sign_test(d, u)}
            for m, (d, u) in sorted(per.items())
        }
    return out


def advice_scenarios(payload: dict, spec: dict) -> dict:
    """Pooled modal-tier moves under the identity ladder and each collapse."""
    order = payload.get("tier_order") or []
    results = {}
    ladders = {"baseline": []}
    ladders.update(spec.get("advice_tier_collapses", {}))
    for name, merges in ladders.items():
        rank = {t: i for i, t in enumerate(order)}
        for group in merges:
            lo = min(rank[t] for t in group if t in rank)
            for t in group:
                if t in rank:
                    rank[t] = lo
        down = up = same = 0
        for s in payload.get("scenarios", []):
            for t in s.get("tier_summary") or []:
                c, p = rank.get(t.get("clinical")), rank.get(t.get("patient"))
                if c is None or p is None:
                    continue
                if p < c:
                    down += 1
                elif p > c:
                    up += 1
                else:
                    same += 1
        results[name] = {"down": down, "up": up, "unchanged": same,
                         "sign_p": sign_test(down, up)}
    return results


def verdicts(nt: dict) -> dict:
    """Per-model: does down>up hold in every scenario; does p<0.05 hold in every?"""
    models = sorted({m for scen in nt.values() for m in scen})
    out = {}
    for m in models:
        entries = [nt[s][m] for s in nt if m in nt[s]]
        out[m] = {
            "asymmetry_all_scenarios": all(e["downgrades"] > e["upgrades"] for e in entries),
            "significant_all_scenarios": all(
                e["sign_p"] is not None and e["sign_p"] < 0.05 for e in entries),
            "down_up_range": [
                [min(e["downgrades"] for e in entries), max(e["downgrades"] for e in entries)],
                [min(e["upgrades"] for e in entries), max(e["upgrades"] for e in entries)],
            ],
        }
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rows", default="urgency_shift.json")
    ap.add_argument("--tiers", default="data/urgency_tiers.draft.json")
    ap.add_argument("--spec", default="data/tier_sensitivity_spec.draft.json")
    ap.add_argument("--advice", default="../patientwords/data/advice_scenarios.json")
    ap.add_argument("--out", default="ops/tier_sensitivity.json")
    args = ap.parse_args(argv)

    rows_doc = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    rows = rows_doc["rows"] if isinstance(rows_doc, dict) else rows_doc
    vocab = json.loads(Path(args.tiers).read_text(encoding="utf-8"))["tokens"]
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))

    nt = next_token_scenarios(rows, vocab, spec)
    payload = {}
    adv = {}
    if Path(args.advice).is_file():
        payload = json.loads(Path(args.advice).read_text(encoding="utf-8"))
        adv = advice_scenarios(payload, spec)

    v = verdicts(nt)
    out = {
        "_": ("Vocabulary-sensitivity bounds for the downgrade asymmetry and the advice near-null. "
              "Scenarios bracket every checklist-flagged token: exclude / floor(0) / ceiling(4). "
              "A claim that survives all scenarios cannot be flipped by re-tiering the flagged set. "
              "Spec: " + args.spec + "; vocabulary: " + args.tiers + " (draft, domain review pending)."),
        "flagged_tokens": {"deciders": spec["deciders"], "blockers": spec["blockers"]},
        "next_token": nt,
        "next_token_verdicts": v,
        "advice_pooled": adv,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")

    survive = [m for m, e in v.items() if e["asymmetry_all_scenarios"]]
    sig = [m for m, e in v.items() if e["significant_all_scenarios"]]
    print(f"next-token asymmetry survives all 4 scenarios: {len(survive)}/{len(v)} models "
          f"({', '.join(survive) if len(survive) < len(v) else 'all'})")
    print(f"sign-test p<0.05 in all 4 scenarios: {len(sig)}/{len(v)} models"
          + (f" ({', '.join(sorted(set(v) - set(sig)))} fail)" if len(sig) < len(v) else ""))
    for name, e in adv.items():
        print(f"advice {name}: {e['down']} down / {e['up']} up (p={e['sign_p']})")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
