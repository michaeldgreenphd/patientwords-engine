"""Compute every estimand from the pipeline's files and write summary.json and summary.md. No number in
summary.md is typed by hand: the markdown is rendered from the same dictionaries the JSON holds.
"""
from __future__ import annotations

import json
from collections import Counter

from common import (
    ARMS,
    N_BOOT,
    PILOT,
    Tfidf,
    cell_id,
    cells,
    cosine,
    dup_key,
    load_seeds,
    mean_cross,
    mean_pairwise,
    newcombe_diff,
    read_jsonl,
    rng,
    wilson,
)


def fmt(v, nd=3):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def ci(w):
    if w.get("p") is None and w.get("mean") is None and w.get("diff") is None:
        return "n/a"
    lo, hi = w.get("lo"), w.get("hi")
    return f"[{fmt(lo)}, {fmt(hi)}]" if lo is not None else "n/a"


def prop_row(label, w):
    return f"| {label} | {w['x']} / {w['n']} | {fmt(w['p'])} | {ci(w)} |"


def main() -> None:
    seeds = load_seeds()
    calls = json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))
    call_log = read_jsonl(PILOT / "call_log.jsonl")
    rows = read_jsonl(PILOT / "generated" / "all_rows.jsonl")
    failures = read_jsonl(PILOT / "generated" / "format_failures.jsonl")
    checked = read_jsonl(PILOT / "checked.jsonl")
    checker_meta = json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8"))
    review = json.loads((PILOT / "review_map.json").read_text(encoding="utf-8")) if (PILOT / "review_map.json").exists() else {}
    cell_ids = [cell_id(s, t) for s, t in cells()]
    S: dict = {"n_seeds": len(seeds), "k_exemplars_used": calls["k_exemplars_used"],
               "k_exemplars_requested": calls["k_exemplars_requested"]}

    # ---- run overview
    finals = [e for e in call_log if e.get("is_final")]
    S["run"] = {"n_calls": len(calls["calls"]), "n_attempts": len(call_log),
                "n_retried_calls": sum(1 for e in call_log if e.get("is_final") is False),
                "calls_with_valid_rows": wilson(sum(1 for e in finals if e["n_valid"] > 0), len(finals)),
                "per_call": [{k: e[k] for k in ("call_id", "arm", "cell", "attempt", "n_lines", "n_valid",
                                                 "n_invalid", "n_control", "n_noncontrol", "reasons")} for e in finals],
                "non_final_attempts": [{k: e.get(k) for k in ("call_id", "attempt", "n_lines", "n_valid", "reasons",
                                                               "null_return")} for e in call_log
                                       if e.get("is_final") is False]}

    # ---- E1 format validity (primary: final attempts)
    def fv(entries):
        return wilson(sum(e["n_valid"] for e in entries), sum(e["n_lines"] for e in entries))
    S["E1"] = {"overall": fv(finals), "by_arm": {a: fv([e for e in finals if e["arm"] == a]) for a in ARMS},
               "by_cell": {c: fv([e for e in finals if e["cell"] == c]) for c in cell_ids},
               "failure_reasons": dict(Counter(f["reason"] for f in failures)),
               "all_attempts_pooled": fv(call_log)}

    # ---- controls (secondary)
    ctrl = [r for r in rows if r["control"] == "negative"]
    S["controls"] = {"n_control_rows": len(ctrl), "expected": 4 * len(calls["calls"]),
                     "faithful": wilson(sum(1 for r in ctrl if r["control_faithful"]), len(ctrl)),
                     "by_arm": {a: wilson(sum(1 for r in ctrl if r["arm"] == a and r["control_faithful"]),
                                          sum(1 for r in ctrl if r["arm"] == a)) for a in ARMS}}

    # ---- E2 novelty (non-control rows; per arm in protocol order; vs seeds and earlier rows of the same arm)
    gen = [r for r in rows if r["control"] == "none"]
    seed_keys = {dup_key(s) for s in seeds}
    seed_clin = {s["clinical_term"].lower() for s in seeds}
    seed_pat = {s["patient_term"].lower() for s in seeds}

    def novelty(subset):
        seen, novel = set(seed_keys), 0
        sc, sp, nc, np_ = set(seed_clin), set(seed_pat), 0, 0
        for r in sorted(subset, key=lambda r: (r["cell_index"], 0 if r["arm"] == "A" else 1, r["line_index"])):
            k = dup_key(r)
            if k not in seen:
                novel += 1
            seen.add(k)
            c, p = r["clinical_term"].lower(), r["patient_term"].lower()
            if c not in sc:
                nc += 1
            sc.add(c)
            if p not in sp:
                np_ += 1
            sp.add(p)
        return {"pair": wilson(novel, len(subset)), "clinical_term_only": wilson(nc, len(subset)),
                "patient_term_only": wilson(np_, len(subset))}
    S["E2"] = {"by_arm": {a: novelty([r for r in gen if r["arm"] == a]) for a in ARMS}, "pooled": novelty(gen),
               "duplicates_of_seeds": sum(1 for r in gen if dup_key(r) in seed_keys)}

    # ---- E3 diversity: TF-IDF fit on all non-control templates plus seed templates
    tf = Tfidf([r["template"] for r in gen] + [s["template"] for s in seeds])
    vec = {r["id"]: tf.vector(r["template"]) for r in gen}
    seed_vecs = [tf.vector(s["template"]) for s in seeds]
    by_arm_cell = {a: {c: [vec[r["id"]] for r in gen if r["arm"] == a and r["cell"] == c] for c in cell_ids} for a in ARMS}
    r_boot = rng("bootstrap")
    E3 = {"within_cell": {a: {} for a in ARMS}, "arm_mean_of_cells": {}, "vs_seeds": {}, "diff_A_minus_B": {},
          "n_boot": N_BOOT, "tfidf_fit_docs": tf.n}
    for a in ARMS:
        for c in cell_ids:
            m, pairs = mean_pairwise(by_arm_cell[a][c])
            E3["within_cell"][a][c] = {"n_rows": len(by_arm_cell[a][c]), "n_pairs": pairs, "mean": m}

    def mean_pairwise_distinct(vecs, idx):
        """Mean cosine over unordered pairs of DISTINCT original rows among the resampled indices idx. A bootstrap
        resample repeats rows; a pair of two copies of one row is not a pair of distinct rows (section 5.3) and
        would contribute a cosine of 1, so such pairs are excluded."""
        total, pairs = 0.0, 0
        for i in range(len(idx)):
            for j in range(i + 1, len(idx)):
                if idx[i] != idx[j]:
                    total += cosine(vecs[idx[i]], vecs[idx[j]])
                    pairs += 1
        return total / pairs if pairs else None

    def arm_stat(cellvecs, cellidx):
        vals = [mean_pairwise_distinct(cellvecs[c], cellidx[c]) for c in cell_ids]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def resample_idx(n):
        return [r_boot.randrange(n) for _ in range(n)] if n else []
    point = {a: arm_stat(by_arm_cell[a], {c: list(range(len(by_arm_cell[a][c]))) for c in cell_ids}) for a in ARMS}
    cross_point = {a: mean_cross([v for c in cell_ids for v in by_arm_cell[a][c]], seed_vecs) for a in ARMS}
    boot = {a: [] for a in ARMS}
    boot_cross = {a: [] for a in ARMS}
    boot_diff, boot_cross_diff = [], []
    for _ in range(N_BOOT):
        st, cr = {}, {}
        for a in ARMS:
            idx = {c: resample_idx(len(by_arm_cell[a][c])) for c in cell_ids}
            st[a] = arm_stat(by_arm_cell[a], idx)
            allv = [by_arm_cell[a][c][i] for c in cell_ids for i in idx[c]]
            cr[a] = mean_cross(allv, seed_vecs)[0]
            if st[a] is not None:
                boot[a].append(st[a])
            if cr[a] is not None:
                boot_cross[a].append(cr[a])
        if st["A"] is not None and st["B"] is not None:
            boot_diff.append(st["A"] - st["B"])
        if cr["A"] is not None and cr["B"] is not None:
            boot_cross_diff.append(cr["A"] - cr["B"])
    from common import percentile

    def pct(vals):
        return {"lo": percentile(vals, 0.025), "hi": percentile(vals, 0.975)} if vals else {"lo": None, "hi": None}
    for a in ARMS:
        E3["arm_mean_of_cells"][a] = {"mean": point[a], "n_rows": sum(len(v) for v in by_arm_cell[a].values()),
                                      "n_cells_with_pairs": sum(1 for v in by_arm_cell[a].values() if len(v) >= 2),
                                      **pct(boot[a])}
        E3["vs_seeds"][a] = {"mean": cross_point[a][0], "n_pairs": cross_point[a][1], **pct(boot_cross[a])}
    E3["diff_A_minus_B"] = {"within_cell": {"diff": (point["A"] - point["B"]) if None not in point.values() else None,
                                            **pct(boot_diff)},
                            "vs_seeds": {"diff": (cross_point["A"][0] - cross_point["B"][0])
                                         if None not in (cross_point["A"][0], cross_point["B"][0]) else None,
                                         **pct(boot_cross_diff)}}
    S["E3"] = E3

    # ---- E4 semantic equivalence, with checker sensitivity and specificity
    def verdict_counts(items):
        return dict(Counter(i["verdict"] for i in items))

    def p_yes(items):
        answered = [i for i in items if i["verdict"] in ("yes", "no", "unclear")]
        return {"yes_over_answered": wilson(sum(1 for i in answered if i["verdict"] == "yes"), len(answered)),
                "unclear_over_answered": wilson(sum(1 for i in answered if i["verdict"] == "unclear"), len(answered)),
                "missing": sum(1 for i in items if i["verdict"] == "missing"), "counts": verdict_counts(items)}
    gen_checked = [c for c in checked if c["source"] == "generated"]
    good = [c for c in checked if c["source"] == "seed"]
    broken = [c for c in checked if c["source"] == "broken"]
    good_ans = [c for c in good if c["verdict"] != "missing"]
    broken_ans = [c for c in broken if c["verdict"] != "missing"]
    S["E4"] = {"generated": p_yes(gen_checked), "by_arm": {a: p_yes([c for c in gen_checked if c["arm"] == a]) for a in ARMS},
               "by_cell": {c: p_yes([x for x in gen_checked if x["cell"] == c]) for c in cell_ids},
               "checker_sensitivity_known_good": {
                   "unclear_counts_as_miss": wilson(sum(1 for c in good_ans if c["verdict"] == "yes"), len(good_ans)),
                   "unclear_excluded": wilson(sum(1 for c in good_ans if c["verdict"] == "yes"),
                                              sum(1 for c in good_ans if c["verdict"] != "unclear")),
                   "counts": verdict_counts(good)},
               "checker_specificity_broken": {
                   "unclear_counts_as_miss": wilson(sum(1 for c in broken_ans if c["verdict"] == "no"), len(broken_ans)),
                   "unclear_excluded": wilson(sum(1 for c in broken_ans if c["verdict"] == "no"),
                                              sum(1 for c in broken_ans if c["verdict"] != "unclear")),
                   "counts": verdict_counts(broken)},
               "checker_set": {k: checker_meta[k] for k in ("n_items", "n_generated", "n_known_good", "n_broken", "notes")}}

    # ---- E5 exemplar sensitivity: Arm A minus Arm B
    def nd(wa, wb):
        return newcombe_diff(wa["x"], wa["n"], wb["x"], wb["n"])
    S["E5"] = {"novelty_pair": nd(S["E2"]["by_arm"]["A"]["pair"], S["E2"]["by_arm"]["B"]["pair"]),
               "diversity_within_cell": E3["diff_A_minus_B"]["within_cell"],
               "diversity_vs_seeds": E3["diff_A_minus_B"]["vs_seeds"],
               "equivalence_yes": nd(S["E4"]["by_arm"]["A"]["yes_over_answered"], S["E4"]["by_arm"]["B"]["yes_over_answered"])}
    S["review"] = {"n": len(review.get("map", {})), "allocation": review.get("allocation"),
                   "checked_by_arm": review.get("n_checked_by_arm")}

    (PILOT / "summary.json").write_text(json.dumps(S, indent=2) + "\n", encoding="utf-8")

    # ---- markdown, rendered from S only
    L = []
    L.append("# Pilot summary (computed by scripts/compute_summary.py)")
    L.append("")
    L.append(f"Seeds: {S['n_seeds']} (synthetic placeholders; see HANDOFF.md). Exemplars per call: "
             f"{S['k_exemplars_used']} used, {S['k_exemplars_requested']} requested. Proportions carry 95% Wilson "
             f"intervals; means carry 95% percentile bootstrap intervals ({N_BOOT} resamples); differences of "
             f"proportions carry Newcombe score intervals. Values are shown to 3 decimals.")
    L.append("")
    L.append("## Run overview")
    L.append("")
    R = S["run"]
    L.append(f"| Quantity | Value |\n|---|---|\n| Generation calls | {R['n_calls']} |\n| Attempts (including retries) | "
             f"{R['n_attempts']} |\n| Calls retried | {R['n_retried_calls']} |\n| Calls with at least one valid row | "
             f"{R['calls_with_valid_rows']['x']} / {R['calls_with_valid_rows']['n']} "
             f"(Wilson {ci(R['calls_with_valid_rows'])}) |")
    L.append("")
    L.append("| Call | Attempt | Lines | Valid | Invalid | Controls | Non-control | Failure reasons |\n|---|---|---|---|---|---|---|---|")
    for e in R["per_call"]:
        L.append(f"| {e['call_id']} | {e['attempt']} | {e['n_lines']} | {e['n_valid']} | {e['n_invalid']} | "
                 f"{e['n_control']} | {e['n_noncontrol']} | {', '.join(f'{k}: {v}' for k, v in e['reasons'].items() if k != 'ok') or 'none'} |")
    if R["non_final_attempts"]:
        L.append("")
        L.append("Non-final (retried) attempts:")
        L.append("")
        L.append("| Call | Attempt | Lines | Valid | Null return | Reasons |\n|---|---|---|---|---|---|")
        for e in R["non_final_attempts"]:
            L.append(f"| {e['call_id']} | {e['attempt']} | {e['n_lines']} | {e['n_valid']} | {e['null_return']} | {e['reasons']} |")
    L.append("")
    L.append("## Estimand 1: format validity (final attempts)")
    L.append("")
    L.append("| Scope | Valid / lines | Proportion | 95% Wilson |\n|---|---|---|---|")
    L.append(prop_row("All calls", S["E1"]["overall"]))
    for a in ARMS:
        L.append(prop_row(f"Arm {a}", S["E1"]["by_arm"][a]))
    for c in cell_ids:
        L.append(prop_row(f"Cell {c}", S["E1"]["by_cell"][c]))
    L.append(prop_row("All attempts pooled (secondary)", S["E1"]["all_attempts_pooled"]))
    L.append("")
    L.append(f"Failure reasons (final attempts): {S['E1']['failure_reasons'] or 'none'}")
    L.append("")
    L.append("## Negative controls (secondary)")
    L.append("")
    C = S["controls"]
    L.append(f"Control rows returned and valid: {C['n_control_rows']} (expected {C['expected']}).")
    L.append("")
    L.append("| Scope | Faithful (surface form only) / controls | Proportion | 95% Wilson |\n|---|---|---|---|")
    L.append(prop_row("Both arms", C["faithful"]))
    for a in ARMS:
        L.append(prop_row(f"Arm {a}", C["by_arm"][a]))
    L.append("")
    L.append("## Estimand 2: novelty (non-control rows)")
    L.append("")
    L.append("| Scope | Key | Novel / rows | Proportion | 95% Wilson |\n|---|---|---|---|---|")
    for a in ARMS:
        for k, lab in (("pair", "(clinical_term, patient_term) pair"), ("clinical_term_only", "clinical_term"),
                       ("patient_term_only", "patient_term")):
            w = S["E2"]["by_arm"][a][k]
            L.append(f"| Arm {a} | {lab} | {w['x']} / {w['n']} | {fmt(w['p'])} | {ci(w)} |")
    w = S["E2"]["pooled"]["pair"]
    L.append(f"| Pooled (secondary) | (clinical_term, patient_term) pair | {w['x']} / {w['n']} | {fmt(w['p'])} | {ci(w)} |")
    L.append("")
    L.append(f"Rows that exactly duplicate a seed pair (case-insensitive): {S['E2']['duplicates_of_seeds']}.")
    L.append("")
    L.append("## Estimand 3: diversity (mean pairwise TF-IDF cosine of templates; lower means more diverse)")
    L.append("")
    L.append(f"TF-IDF fitted on {E3['tfidf_fit_docs']} templates (all non-control generated rows plus the seeds).")
    L.append("")
    L.append("| Arm | Cell | Rows | Pairs | Mean cosine |\n|---|---|---|---|---|")
    for a in ARMS:
        for c in cell_ids:
            e = E3["within_cell"][a][c]
            L.append(f"| {a} | {c} | {e['n_rows']} | {e['n_pairs']} | {fmt(e['mean'])} |")
    L.append("")
    L.append("| Arm | Mean of cell means | 95% bootstrap | Rows | Cells with pairs |\n|---|---|---|---|---|")
    for a in ARMS:
        e = E3["arm_mean_of_cells"][a]
        L.append(f"| {a} | {fmt(e['mean'])} | {ci(e)} | {e['n_rows']} | {e['n_cells_with_pairs']} |")
    L.append("")
    L.append("| Arm | Generated vs seed templates, mean cosine | 95% bootstrap | Pairs |\n|---|---|---|---|")
    for a in ARMS:
        e = E3["vs_seeds"][a]
        L.append(f"| {a} | {fmt(e['mean'])} | {ci(e)} | {e['n_pairs']} |")
    L.append("")
    L.append("## Estimand 4: semantic equivalence (checker), reported with the checker's own validation")
    L.append("")
    E4 = S["E4"]
    cs = E4["checker_set"]
    L.append(f"Checker set: {cs['n_items']} items = {cs['n_generated']} generated + {cs['n_known_good']} known-good seed rows + "
             f"{cs['n_broken']} broken pairs. Notes: {'; '.join(cs['notes']) or 'none'}.")
    L.append("")
    L.append("| Checker validation | Hits / answered | Proportion | 95% Wilson | Verdict counts |\n|---|---|---|---|---|")
    for lab, key in (("Sensitivity on known-good (unclear counts as miss)", ("checker_sensitivity_known_good", "unclear_counts_as_miss")),
                     ("Sensitivity on known-good (unclear excluded)", ("checker_sensitivity_known_good", "unclear_excluded")),
                     ("Specificity on broken (unclear counts as miss)", ("checker_specificity_broken", "unclear_counts_as_miss")),
                     ("Specificity on broken (unclear excluded)", ("checker_specificity_broken", "unclear_excluded"))):
        w = E4[key[0]][key[1]]
        L.append(f"| {lab} | {w['x']} / {w['n']} | {fmt(w['p'])} | {ci(w)} | {E4[key[0]]['counts']} |")
    L.append("")
    L.append("| Scope | Judged equivalent / answered | Proportion | 95% Wilson | Unclear / answered | Missing | Counts |\n|---|---|---|---|---|---|---|")
    for lab, e in [("All generated", E4["generated"])] + [(f"Arm {a}", E4["by_arm"][a]) for a in ARMS] + \
                  [(f"Cell {c}", E4["by_cell"][c]) for c in cell_ids]:
        w, u = e["yes_over_answered"], e["unclear_over_answered"]
        L.append(f"| {lab} | {w['x']} / {w['n']} | {fmt(w['p'])} | {ci(w)} | {u['x']} / {u['n']} | {e['missing']} | {e['counts']} |")
    L.append("")
    L.append("## Estimand 5: exemplar sensitivity, Arm A (random exemplars) minus Arm B (fixed exemplars)")
    L.append("")
    E5 = S["E5"]
    L.append("| Estimand | Arm A | Arm B | A minus B | 95% interval for the difference |\n|---|---|---|---|---|")
    L.append(f"| 2 novelty (pair) | {fmt(S['E2']['by_arm']['A']['pair']['p'])} | {fmt(S['E2']['by_arm']['B']['pair']['p'])} | "
             f"{fmt(E5['novelty_pair']['diff'])} | {ci(E5['novelty_pair'])} (Newcombe) |")
    L.append(f"| 3 within-cell diversity (mean cosine) | {fmt(E3['arm_mean_of_cells']['A']['mean'])} | "
             f"{fmt(E3['arm_mean_of_cells']['B']['mean'])} | {fmt(E5['diversity_within_cell']['diff'])} | "
             f"{ci(E5['diversity_within_cell'])} (bootstrap) |")
    L.append(f"| 3 generated vs seeds (mean cosine) | {fmt(E3['vs_seeds']['A']['mean'])} | {fmt(E3['vs_seeds']['B']['mean'])} | "
             f"{fmt(E5['diversity_vs_seeds']['diff'])} | {ci(E5['diversity_vs_seeds'])} (bootstrap) |")
    L.append(f"| 4 equivalence (yes / answered) | {fmt(E4['by_arm']['A']['yes_over_answered']['p'])} | "
             f"{fmt(E4['by_arm']['B']['yes_over_answered']['p'])} | {fmt(E5['equivalence_yes']['diff'])} | "
             f"{ci(E5['equivalence_yes'])} (Newcombe) |")
    L.append("")
    L.append("## Human review sample")
    L.append("")
    L.append(f"review_sheet.csv holds {S['review']['n']} rows; allocation by arm {S['review']['allocation']} from checked rows "
             f"by arm {S['review']['checked_by_arm']}. Agreement is not computed here.")
    L.append("")
    (PILOT / "summary.md").write_text("\n".join(L), encoding="utf-8")
    print("summary.json and summary.md written")


if __name__ == "__main__":
    main()
