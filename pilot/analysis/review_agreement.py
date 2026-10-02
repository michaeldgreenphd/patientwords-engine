"""Compare the owner's blind review of a version-2 pilot run with the checker's structured answers.

This answers one question for the run: on the 40 sampled pairs, does the automated checker judge what the owner
judges? It runs after the owner's review, outside the run's sealed summary (the summary hashes the review sheet
before it is filled), and writes agreement.json and agreement.md next to the review export.

Inputs:
- the run directory (checked.jsonl with the version-2 checker fields, review_map.json mapping review ids to rows);
- a review export in the shape of pilot/codebook/review_export_*.json: one row per reviewed sample id with the
  owner's stored first answers and the flag checker_shown_before_first_answer.

Method. Only first answers given while the checker's answer was hidden are used; a row whose checker answer was on
screen first is refused, not dropped, because it would not be a blind label. Each comparison pairs one owner question
with the checker field that answers the same question on the same option set:
- same (yes/no/unclear) against the checker's equivalent;
- precision (as_precise/vaguer/more_specific) against the precision implied by the checker's relation (same and
  same_brand: as_precise; broader: vaguer; narrower: more_specific); a relation of different has no precision and is
  counted, not compared;
- sentence (both/clinical_only/patient_only/neither) against sentence_natural, and collapsed to both-versus-not;
- patient_real (real/textbook/unlikely) against patient_realism, and collapsed to real-versus-not;
- keep against the checker-side keep rule of codebook R8 (keep when both sentences read naturally), reported as
  sensitivity, specificity and positive predictive value for the owner's keep.
Rows where either side left the question unanswered are counted per comparison, never imputed. Raw agreement has a
95% Wilson interval; Cohen's unweighted kappa has a percentile bootstrap interval over rows (--seed, default
20261002, and --resamples, default 2000, both recorded in the output).

Usage: review_agreement.py --run-dir <run> --export <review export json> [--out-dir <dir>] [--seed N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

Z = 1.959964
PRECISION_OF_RELATION = {"same": "as_precise", "same_brand": "as_precise", "broader": "vaguer",
                         "narrower": "more_specific", "different": None}
COMPARISONS = [  # (name, owner field, checker field, label set or None, owner->value, checker->value)
    ("same", "same", "verdict", ("yes", "no", "unclear"), None, None),
    ("precision", "precision", "relation", ("as_precise", "vaguer", "more_specific"), None, "precision"),
    ("sentence", "sentence", "sentence_natural", ("both", "clinical_only", "patient_only", "neither"), None, None),
    ("sentence_both_vs_not", "sentence", "sentence_natural", ("both", "not"), "both_vs_not", "both_vs_not"),
    ("realism", "patient_real", "patient_realism", ("real", "textbook", "unlikely"), None, None),
    ("realism_real_vs_not", "patient_real", "patient_realism", ("real", "not"), "real_vs_not", "real_vs_not"),
]


class AgreementError(ValueError):
    """An input that cannot give a faithful comparison; the message names the row or field."""


def wilson(x: int, n: int) -> dict | None:
    if n <= 0:
        return None
    p = x / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return {"x": x, "n": n, "p": round(p, 4), "lo": round(max(0.0, c - h), 4), "hi": round(min(1.0, c + h), 4)}


def kappa(pairs: list[tuple[str, str]], labels: tuple[str, ...]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n) for lab in labels)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def kappa_interval(pairs: list[tuple[str, str]], labels: tuple[str, ...], rng: random.Random,
                   resamples: int) -> list[float] | None:
    """Percentile bootstrap over rows; resamples whose kappa is undefined (one label only) are counted out."""
    if len(pairs) < 2:
        return None
    ks = []
    for _ in range(resamples):
        k = kappa([pairs[rng.randrange(len(pairs))] for _ in pairs], labels)
        if k is not None:
            ks.append(k)
    if len(ks) < resamples // 2:
        return None
    ks.sort()
    return [round(ks[int(0.025 * (len(ks) - 1))], 4), round(ks[int(0.975 * (len(ks) - 1))], 4)]


def _value(v: str | None, mode: str | None) -> str | None:
    if v is None or mode is None:
        return v
    if mode == "precision":
        return PRECISION_OF_RELATION.get(v, "__invalid__")
    if mode == "both_vs_not":
        return "both" if v == "both" else "not"
    if mode == "real_vs_not":
        return "real" if v == "real" else "not"
    raise AgreementError(f"unknown mode {mode}")


def compare(run_dir: Path, export: dict, seed: int, resamples: int) -> dict:
    mapping = json.loads((run_dir / "review_map.json").read_text(encoding="utf-8")).get("map") or {}
    checked = {}
    for line in (run_dir / "checked.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            if c.get("source") == "generated":
                checked[c["row_id"]] = c
    rows = sorted(export.get("rows", []), key=lambda r: r["sample_id"])
    if not rows:
        raise AgreementError("the export has no rows")
    joined = []
    for r in rows:
        sid = r["sample_id"]
        owner = r.get("owner") or {}
        if owner.get("checker_shown_before_first_answer") is not False:
            raise AgreementError(f"{sid}: the checker's answer was shown before the first answer; not a blind label")
        row_id = mapping.get(sid)
        if row_id is None:
            raise AgreementError(f"{sid}: not in review_map.json")
        if row_id not in checked:
            raise AgreementError(f"{sid}: row {row_id} has no checker entry")
        c = checked[row_id]
        missing = [k for k in ("relation", "sentence_natural", "patient_realism") if k not in c]
        if missing:
            raise AgreementError(f"{sid}: checker entry lacks version-2 fields {missing}; run is not version 2")
        joined.append((sid, owner.get("first_answers") or {}, c))
    rng = random.Random(seed)
    out: dict = {"comparisons": {}}
    for name, of, cf, labels, omode, cmode in COMPARISONS:
        pairs, unanswered, not_comparable = [], 0, 0
        for sid, fa, c in joined:
            a, b = _value(fa.get(of), omode), _value(c.get(cf), cmode)
            if a is None or (c.get("verdict") == "missing"):
                unanswered += 1
                continue
            if b is None:
                not_comparable += 1
                continue
            if a not in labels or b not in labels:
                raise AgreementError(f"{sid}: {name} values {a!r}/{b!r} are outside {labels}")
            pairs.append((a, b))
        k = kappa(pairs, labels)
        out["comparisons"][name] = {
            "owner_field": of, "checker_field": cf, "labels": list(labels), "n_compared": len(pairs),
            "unanswered_or_missing": unanswered, "not_comparable": not_comparable,
            "agreement": wilson(sum(a == b for a, b in pairs), len(pairs)),
            "kappa": None if k is None else round(k, 4),
            "kappa_ci95_bootstrap": kappa_interval(pairs, labels, rng, resamples),
            "confusion_owner_rows_checker_cols": {a: {b: sum(x == a and y == b for x, y in pairs) for b in labels}
                                                  for a in labels},
        }
    rule_keep = [(fa.get("keep"), c.get("sentence_natural") == "both") for _, fa, c in joined
                 if fa.get("keep") is not None and c.get("verdict") != "missing"]
    tp = sum(k == "keep" and pred for k, pred in rule_keep)
    fn = sum(k == "keep" and not pred for k, pred in rule_keep)
    fp = sum(k != "keep" and pred for k, pred in rule_keep)
    tn = sum(k != "keep" and not pred for k, pred in rule_keep)
    out["keep_rule_r8"] = {"rule": "checker keeps a pair when sentence_natural is both", "n": len(rule_keep),
                           "sensitivity": wilson(tp, tp + fn), "specificity": wilson(tn, tn + fp),
                           "ppv": wilson(tp, tp + fp), "counts": {"tp": tp, "fn": fn, "fp": fp, "tn": tn}}
    out["seed"], out["resamples"] = seed, resamples
    return out


def render_md(result: dict) -> str:
    lines = [f"# Owner against checker, run {result['run']}", "",
             f"Blind first answers only. Bootstrap seed {result['seed']}, {result['resamples']} resamples.", "",
             "| Question | Compared | Agreement (95% CI) | Kappa (95% CI) | Unanswered | Not comparable |",
             "|---|---|---|---|---|---|"]
    for name, c in result["comparisons"].items():
        a = c["agreement"]
        agr = "—" if a is None else f"{a['x']}/{a['n']} ({100 * a['p']:.0f}%, {100 * a['lo']:.0f}-{100 * a['hi']:.0f}%)"
        ci = c["kappa_ci95_bootstrap"]
        kap = "—" if c["kappa"] is None else f"{c['kappa']:.2f}" + (f" ({ci[0]:.2f} to {ci[1]:.2f})" if ci else "")
        lines.append(f"| {name} | {c['n_compared']} | {agr} | {kap} | {c['unanswered_or_missing']} | "
                     f"{c['not_comparable']} |")
    k = result["keep_rule_r8"]

    def fmt(w: dict | None) -> str:
        return "—" if w is None else f"{w['x']}/{w['n']} ({100 * w['p']:.0f}%)"

    lines += ["", (f"Keep rule R8 ({k['rule']}), against the owner's keep on {k['n']} rows: sensitivity "
                   f"{fmt(k['sensitivity'])}, specificity {fmt(k['specificity'])}, positive predictive value "
                   f"{fmt(k['ppv'])}."), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--export", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--resamples", type=int, default=2000)
    a = ap.parse_args(argv)
    run_dir, export_path = Path(a.run_dir), Path(a.export)
    out_dir = Path(a.out_dir) if a.out_dir else export_path.parent
    try:
        export_bytes = export_path.read_bytes()
        result = compare(run_dir, json.loads(export_bytes), a.seed, a.resamples)
    except (AgreementError, FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        print(f"review_agreement: refused: {e}", file=sys.stderr)
        return 2
    result = {"run": run_dir.name, "export": export_path.name,
              "export_sha256": hashlib.sha256(export_bytes).hexdigest(),
              "checked_sha256": hashlib.sha256((run_dir / "checked.jsonl").read_bytes()).hexdigest(), **result}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "agreement.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    (out_dir / "agreement.md").write_text(render_md(result), encoding="utf-8")
    print(f"review_agreement: wrote {out_dir / 'agreement.json'} and agreement.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
