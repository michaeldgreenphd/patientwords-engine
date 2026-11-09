#!/usr/bin/env python3
"""Comma test on 18 hand-authored pairs: the analysis fixed in docs/exploratory/comma_test_plan_20261109.md.

Exploratory. Reads only committed trace parts:

  trace_out/agscen_commas_20261109*/batch_summary.part_*.json   the 18 pairs as written (-comma) and with every
                                                                comma deleted (-nocomma), data/simulated/
                                                                agscen_commas_20261109.json
  trace_out/agscen_r5_20261108*/batch_summary.part_*.json       the round-5 rewrites (<scale id>-r5),
                                                                data/simulated/agscen_r5_20261108.json

Seven models: hosted gemma-2-2b (the directory without a model suffix) and six logits models. Per pair and model:
penalty (the engine's language_penalty, everyday minus clinical probability of the clinical target), p_clinical
(the clinical side's target probability) and class (downgrade / upgrade / lateral / uninformative, with the tier
rules of scripts/urgency_shift.py copied below and data/urgency_tiers.draft.json).

Units: one per distinct (clinical sentence, target), because five dose groups share a clinical sentence between
two pairs. A model's row counts only when both variants have a number. Pair value = mean over models; unit value =
mean over its pairs. Exact two-sided sign test over units; units at exactly 0 are dropped and counted.

  1. commas: penalty(comma) - penalty(nocomma), 13 units
  2. baseline: p_clinical(comma) - p_clinical(nocomma), 13 units
  3. class: pairs and model rows that downgrade, comma and nocomma (descriptive)
  4. connective: penalty(nocomma) - penalty(r5) on 13 pairs (10 units), leaving out sc-029, sc-040, sc-042,
     sc-050, sc-052 (their rewrites also changed hyphens); sensitivity without sc-035, sc-039, sc-049 (8 units)

    python scripts/comma_test_analysis.py [--root .] [--out results.json]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import re
from pathlib import Path
from typing import Any

COMMAS = "agscen_commas_20261109"
R5 = "agscen_r5_20261108"
HOSTED = "gemma-2-2b (hosted)"
HYPHEN_REWRITES = {"sc-029", "sc-040", "sc-042", "sc-050", "sc-052"}
AND_TO_WITH = {"sc-035", "sc-039", "sc-049"}


def load_vocab(root: Path) -> dict[str, Any]:
    return json.loads((root / "data" / "urgency_tiers.draft.json").read_text(encoding="utf-8"))["tokens"]


# tier, bare and classify: copied from scripts/urgency_shift.py (which parses arguments on import).
def tier(vocab: dict[str, Any], token: str | None, cont: dict[str, str] | None = None) -> int | None:
    if not token:
        return None
    key = str(token).strip().lower()
    if cont:
        phrase = cont.get(str(token).strip()) or cont.get(key)
        if phrase:
            for w in reversed(str(phrase).lower().split()):
                e = vocab.get(w.strip('.,!?\'"'))
                if e and e["tier"] is not None:
                    return e["tier"]
    e = vocab.get(key)
    return e["tier"] if e else None


def bare(label: Any) -> str | None:
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


def classify(vocab: dict[str, Any], top_c: str | None, top_p: str | None,
             cont_c: dict[str, str] | None = None, cont_p: dict[str, str] | None = None) -> str:
    tc, tp = tier(vocab, top_c, cont_c), tier(vocab, top_p, cont_p)
    if tc is None or tp is None:
        return "uninformative"
    return "downgrade" if tp < tc else "upgrade" if tp > tc else "lateral"


def sign_test(pos: int, neg: int) -> float:
    """Exact two-sided sign test."""
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def read_rows(root: Path, stem: str, vocab: dict[str, Any]) -> dict[tuple[int, str], dict[str, Any]]:
    """(1-based pair index, model) -> {penalty, p_clinical, class} from every committed part of one stem."""
    rows: dict[tuple[int, str], dict[str, Any]] = {}
    for path in sorted(glob.glob(str(root / "trace_out" / f"{stem}*" / "batch_summary.part_*.json"))):
        run = Path(path).parent.name
        if run != stem and not run.startswith(stem + "__"):
            continue
        model = run.split("__", 1)[1] if "__" in run else HOSTED
        for r in json.loads(Path(path).read_text(encoding="utf-8"))["results"]:
            sp = r.get("predictive_spread") or {}
            sc, spp = sp.get("clinical") or [], sp.get("patient") or []
            cont = r.get("continuations") or {}
            cls = (classify(vocab, bare(sc[0][0]), bare(spp[0][0]), cont.get("clinical"), cont.get("patient"))
                   if sc and spp else None)
            key = (r["index"], model)
            assert key not in rows, f"duplicate result {key} in {stem}"
            rows[key] = {"penalty": num(r.get("language_penalty")),
                         "p_clinical": num((r.get("probabilities") or {}).get("clinical")),
                         "class": cls}
    return rows


def paired(a: dict[str, dict[str, Any]], b: dict[str, dict[str, Any]], measure: str) -> dict[str, float]:
    """model -> a - b, for models where both are numbers."""
    return {m: a[m][measure] - b[m][measure] for m in a.keys() & b.keys()
            if a[m][measure] is not None and b[m][measure] is not None}


def contrast(diffs: dict[str, dict[str, float]], unit_of: dict[str, str]) -> dict[str, Any]:
    """diffs: scale id -> model -> difference. Pair value = model mean; unit value = mean of its pairs."""
    pair_val = {i: sum(d.values()) / len(d) for i, d in diffs.items() if d}
    units: dict[str, list[float]] = collections.defaultdict(list)
    for i, v in pair_val.items():
        units[unit_of[i]].append(v)
    unit_val = {u: sum(v) / len(v) for u, v in units.items()}
    pos = sum(v > 0 for v in unit_val.values())
    neg = sum(v < 0 for v in unit_val.values())
    zero = sum(v == 0 for v in unit_val.values())
    vals = list(unit_val.values())
    return {"units": len(unit_val), "up": pos, "down": neg, "zero": zero, "p": round(sign_test(pos, neg), 4),
            "mean_unit": round(sum(vals) / len(vals), 4) if vals else None,
            "median_unit": round(sorted(vals)[len(vals) // 2] if len(vals) % 2 else
                                 sum(sorted(vals)[len(vals) // 2 - 1:len(vals) // 2 + 1]) / 2, 4) if vals else None,
            "pairs": {i: round(v, 4) for i, v in sorted(pair_val.items())},
            "models_per_pair": {i: len(d) for i, d in sorted(diffs.items())}}


def class_counts(rows_by_id: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    down_rows = up_rows = classed = down_pairs = 0
    for per_model in rows_by_id.values():
        cls = [v["class"] for v in per_model.values() if v["class"] and v["class"] != "uninformative"]
        d, u = cls.count("downgrade"), cls.count("upgrade")
        down_rows += d
        up_rows += u
        classed += len(cls)
        down_pairs += d >= 1 and d > u
    return {"pairs": len(rows_by_id), "downgrade_pairs": down_pairs, "downgrade_rows": down_rows,
            "upgrade_rows": up_rows, "classed_rows": classed}


def analyse(root: Path) -> dict[str, Any]:
    vocab = load_vocab(root)
    commas = json.loads((root / "data" / "simulated" / f"{COMMAS}.json").read_text(encoding="utf-8"))
    r5 = json.loads((root / "data" / "simulated" / f"{R5}.json").read_text(encoding="utf-8"))
    rc, rr = read_rows(root, COMMAS, vocab), read_rows(root, R5, vocab)

    def per_model(rows: dict[tuple[int, str], dict[str, Any]], index: int) -> dict[str, dict[str, Any]]:
        return {m: v for (i, m), v in rows.items() if i == index}

    comma, nocomma, unit_of = {}, {}, {}
    for idx, pair in enumerate(commas, 1):
        g = pair["generation"]
        (comma if g["variant"] == "comma" else nocomma)[g["scale_id"]] = per_model(rc, idx)
        if g["variant"] == "nocomma":
            unit_of[g["scale_id"]] = pair["top_prompt"] + "\x00" + pair["target_clinical_token"]
    rewrite = {p["generation"]["rewrites"]: per_model(rr, idx)
               for idx, p in enumerate(r5, 1) if p["generation"].get("rewrites")}
    ids = sorted(comma)
    assert sorted(nocomma) == ids and len(ids) == 18 and set(rewrite) == set(ids)

    out: dict[str, Any] = {"models": sorted({m for (_, m) in rc}), "distinct_clinical_units": len(set(unit_of.values()))}
    missing = {i: sorted(set(out["models"]) - (comma[i].keys() & nocomma[i].keys())) for i in ids}
    out["missing_model_rows"] = {i: m for i, m in missing.items() if m}
    out["1_commas_penalty"] = contrast({i: paired(comma[i], nocomma[i], "penalty") for i in ids}, unit_of)
    out["2_commas_baseline"] = contrast({i: paired(comma[i], nocomma[i], "p_clinical") for i in ids}, unit_of)
    out["3_commas_class"] = {"comma": class_counts(comma), "nocomma": class_counts(nocomma)}
    kept = [i for i in ids if i not in HYPHEN_REWRITES]
    out["4_connective_penalty"] = contrast({i: paired(nocomma[i], rewrite[i], "penalty") for i in kept}, unit_of)
    out["4_connective_class"] = {"nocomma": class_counts({i: nocomma[i] for i in kept}),
                                 "r5": class_counts({i: rewrite[i] for i in kept})}
    narrow = [i for i in kept if i not in AND_TO_WITH]
    out["4s_connective_penalty_insert_only"] = contrast(
        {i: paired(nocomma[i], rewrite[i], "penalty") for i in narrow}, unit_of)
    out["4_hyphen_rewrites_reported_alone"] = {
        i: round(sum(d.values()) / len(d), 4) if (d := paired(nocomma[i], rewrite[i], "penalty")) else None
        for i in sorted(HYPHEN_REWRITES)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    res = analyse(a.root)
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
