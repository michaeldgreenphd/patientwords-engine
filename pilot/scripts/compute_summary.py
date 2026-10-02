"""Compute every estimand from the pipeline's files and write summary.json and summary.md. No number in
summary.md is typed by hand: the markdown is rendered from the same dictionaries the JSON holds.

Under harness version 2 (recorded in calls.json and checker_batches.json) the summary also reports, as descriptives
outside the protocol's estimands: the checker's relation for generated, known-good and broken items, the precision
view derived from it, the yes-rate by relation and the answers flagged inconsistent; the checker's sentence_natural
and patient_realism for generated rows, by arm; probe-point compliance; variant-design compliance per call; next_word
statistics; and the review sample's one-row-per-concept figures. summary.json then records `harness_version`. A
version-1 summary and its markdown are byte-identical to the recorded run's.
"""
from __future__ import annotations

import json
import platform
import random
from collections import Counter
from itertools import pairwise

from common import (
    ARMS,
    CHECKER_RELATIONS,
    CHECKER_V2_FIELDS,
    CHECKER_VERDICTS,
    CONCEPTS_PER_CALL,
    CONTROL_VALUES,
    MASTER_SEED,
    N_BOOT,
    PILOT,
    PRECISION_VALUES,
    PROBE_ENDINGS,
    RELATION_PRECISION,
    SUMMARY_INPUTS,
    VARIANT_PAIRS_PER_CALL,
    Tfidf,
    cell_id,
    cells,
    checked_problems,
    concept_key,
    control_measurable,
    cosine,
    dup_key,
    generation_problems,
    load_calls,
    load_checker_batches,
    load_seeds,
    mean_cross,
    mean_pairwise,
    newcombe_diff,
    percentile,
    plan_version,
    probe_point_ok,
    read_csv,
    read_jsonl,
    review_problems,
    rng,
    script_hashes,
    sealed_interpreter_guard,
    sha256_file,
    sha256_text,
    surface_key,
    wilson,
    write_results_block,
)
from rederive import rederive_problems

Vector = dict[str, float]


def fmt(v: object, nd: int = 3) -> str:
    """A value for the markdown: floats to nd decimals, None as n/a."""
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def ci(w: dict) -> str:
    """The [lo, hi] of an interval record, or n/a when it has none."""
    if w.get("p") is None and w.get("mean") is None and w.get("diff") is None:
        return "n/a"
    lo, hi = w.get("lo"), w.get("hi")
    return f"[{fmt(lo)}, {fmt(hi)}]" if lo is not None else "n/a"


def prop_row(label: str, w: dict) -> str:
    """One markdown table row for a Wilson record."""
    return f"| {label} | {w['x']} / {w['n']} | {fmt(w['p'])} | {ci(w)} |"


def mean_pairwise_distinct(vecs: list[Vector], idx: list[int]) -> float | None:
    """Mean cosine over unordered pairs of DISTINCT original rows among the resampled indices idx. A bootstrap
    resample repeats rows; a pair of two copies of one row is not a pair of distinct rows (PROTOCOL.md 5.3) and
    would contribute a cosine of 1, so such pairs are excluded. None when no such pair exists."""
    total, pairs = 0.0, 0
    for i in range(len(idx)):
        for j in range(i + 1, len(idx)):
            if idx[i] != idx[j]:
                total += cosine(vecs[idx[i]], vecs[idx[j]])
                pairs += 1
    return total / pairs if pairs else None


def bootstrap_diversity(by_arm_cell: dict[str, dict[str, list[Vector]]], seed_vecs: list[Vector],
                        r: random.Random, n_boot: int) -> dict:
    """Percentile-bootstrap replicates for estimand 3. Rows are resampled with replacement within each cell, jointly
    for both arms in each replicate (the same replicate feeds the arm intervals and the A minus B interval).

    The cell set is fixed: an arm's statistic is the unweighted mean over the cells that have at least two rows in
    the point estimate, in every replicate. A replicate in which one of those cells resamples to copies of a single
    row has no defined within-cell statistic; it is then skipped for that arm (and for the difference) and counted in
    n_undefined, never computed over a different set of cells (Codex review of PR #52)."""
    arms = list(by_arm_cell)
    fixed = {a: [c for c, v in by_arm_cell[a].items() if len(v) >= 2] for a in arms}
    boot: dict[str, list[float]] = {a: [] for a in arms}
    boot_cross: dict[str, list[float]] = {a: [] for a in arms}
    undefined = {a: 0 for a in arms}
    boot_diff: list[float] = []
    boot_cross_diff: list[float] = []
    undefined_diff = 0
    for _ in range(n_boot):
        st: dict[str, float | None] = {}
        cr: dict[str, float | None] = {}
        for a in arms:
            idx = {c: [r.randrange(len(v)) for _ in v] for c, v in by_arm_cell[a].items()}
            vals = [mean_pairwise_distinct(by_arm_cell[a][c], idx[c]) for c in fixed[a]]
            st[a] = sum(vals) / len(vals) if vals and all(v is not None for v in vals) else None
            allv = [by_arm_cell[a][c][i] for c in by_arm_cell[a] for i in idx[c]]
            cr[a] = mean_cross(allv, seed_vecs)[0]
            if st[a] is None:
                undefined[a] += 1
            else:
                boot[a].append(st[a])
            if cr[a] is not None:
                boot_cross[a].append(cr[a])
        if len(arms) == 2:
            a0, a1 = arms
            if st[a0] is not None and st[a1] is not None:
                boot_diff.append(st[a0] - st[a1])
            else:
                undefined_diff += 1
            if cr[a0] is not None and cr[a1] is not None:
                boot_cross_diff.append(cr[a0] - cr[a1])
    return {"fixed_cells": fixed, "boot": boot, "boot_cross": boot_cross, "boot_diff": boot_diff,
            "boot_cross_diff": boot_cross_diff, "n_undefined": undefined, "n_undefined_diff": undefined_diff}


def pct(vals: list[float]) -> dict:
    """The 2.5th and 97.5th percentiles of bootstrap replicates, or None when there are none."""
    return {"lo": percentile(vals, 0.025), "hi": percentile(vals, 0.975)} if vals else {"lo": None, "hi": None}


def probe_point_summary(rows: list[dict], cell_ids: list[str], endings: tuple[str, ...]) -> dict:
    """Version 2, descriptive: the share of rows whose template, stripped, ends on a probe ending (common.probe_point_ok),
    over every format-valid row of the final attempts, controls included, by control kind, arm and cell. A row that
    misses is still a valid row; this is not a format failure."""
    def share(sub: list[dict]) -> dict:
        return wilson(sum(1 for r in sub if probe_point_ok(r["template"], endings)), len(sub))
    return {"endings": list(endings), "population": "format-valid rows of the final attempts, controls included",
            "overall": share(rows), "by_control": {k: share([r for r in rows if r["control"] == k]) for k in CONTROL_VALUES},
            "by_arm": {a: share([r for r in rows if r["arm"] == a]) for a in ARMS},
            "by_cell": {c: share([r for r in rows if r["cell"] == c]) for c in cell_ids}}


def variant_call(none_rows: list[dict]) -> dict:
    """One call's variant-design counts over its format-valid control "none" rows of the final attempt, ordered by
    line_index. An adjacent variant pair is two neighbours in that order that share the template and next_word
    exactly, have different patient_term surface keys, and share clinical_term exactly (`pairs_exact`) or by surface
    key (`pairs_clinical_surface`, which includes the exact ones). Concepts are counted by common.concept_key (clinical
    term surface key and template, within the call): `concepts` distinct ones, `non_adjacent_repeats` rows whose
    concept occurred earlier but not on the row before, `runs_of_three_or_more` maximal runs of one concept of length
    three or more."""
    rows = sorted(none_rows, key=lambda r: r["line_index"])
    exact = surface = 0
    for a, b in pairwise(rows):
        rest = (a["template"] == b["template"] and a["next_word"] == b["next_word"]
                and surface_key(a["patient_term"]) != surface_key(b["patient_term"]))
        exact += rest and a["clinical_term"] == b["clinical_term"]
        surface += rest and surface_key(a["clinical_term"]) == surface_key(b["clinical_term"])
    seen: set = set()
    prev, run, runs3, nonadj = None, 0, 0, 0
    for r in rows:
        k = concept_key(r["call_id"], r["clinical_term"], r["template"])
        if k == prev:
            run += 1
        else:
            runs3 += run >= 3
            nonadj += k in seen
            run = 1
        seen.add(k)
        prev = k
    runs3 += run >= 3
    return {"n_rows": len(rows), "concepts": len(seen), "pairs_exact": int(exact), "pairs_clinical_surface": int(surface),
            "non_adjacent_repeats": int(nonadj), "runs_of_three_or_more": int(runs3)}


def variant_design_summary(rows: list[dict], finals: list[dict], pairs: int, concepts: int) -> dict:
    """Version 2, descriptive: variant_call for every planned call (a call with no response record counts, with zero
    rows); a call is compliant when it has exactly `pairs` exact adjacent variant pairs and `concepts` concepts.
    Calls compliant over all planned calls carry a Wilson interval, overall and by arm; non-compliant calls are
    flagged by id."""
    per_call = []
    for e in finals:
        v = variant_call([r for r in rows if r["call_id"] == e["call_id"] and r["control"] == "none"])
        per_call.append({"call_id": e["call_id"], "arm": e["arm"], **v,
                         "compliant": v["pairs_exact"] == pairs and v["concepts"] == concepts})
    def share(sub: list[dict]) -> dict:
        return wilson(sum(1 for c in sub if c["compliant"]), len(sub))
    return {"definition": f"per call, over the final attempt's format-valid control none rows ordered by line_index: "
                          f"compliant when exactly {pairs} adjacent pairs share clinical_term, template and next_word "
                          f"with different patient_term surface keys, and the rows cover exactly {concepts} concepts "
                          f"(clinical_term surface key and template)",
            "expected_pairs_per_call": pairs, "expected_concepts_per_call": concepts,
            "calls_compliant": share(per_call), "by_arm": {a: share([c for c in per_call if c["arm"] == a]) for a in ARMS},
            **{k: sum(c[k] for c in per_call) for k in ("pairs_exact", "pairs_clinical_surface", "non_adjacent_repeats",
                                                          "runs_of_three_or_more")},
            "flagged_calls": [c["call_id"] for c in per_call if not c["compliant"]], "per_call": per_call}


def next_word_summary(rows: list[dict]) -> dict:
    """Version 2, descriptive: the next_word of every format-valid row of the final attempts, controls included: the
    number of rows, of distinct words, and the 10 most common words (ties broken alphabetically)."""
    counts = Counter(r["next_word"] for r in rows)
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {"population": "format-valid rows of the final attempts, controls included", "n_rows": len(rows),
            "n_distinct": len(counts), "most_common": [{"word": w, "n": n} for w, n in top]}


def checker_v2_summary(checked: list[dict]) -> dict:
    """Version 2, descriptive: the checker's further answers over answered items (a missing verdict carries none).
    relation for generated, known-good and broken items; the precision view derived from it (same and same_brand as
    as_precise, broader as vaguer, narrower as more_specific, different as not_applicable); the yes-rate by relation
    on generated items; the answers whose equivalent contradicts their relation (kept, flagged inconsistent); and
    sentence_natural and patient_realism for generated items, overall and by arm. Every allowed value is listed, with
    its count, zero included."""
    sources = {"generated": "generated", "known_good": "seed", "broken": "broken"}
    answered = {k: [c for c in checked if c["source"] == s and c["verdict"] != "missing"] for k, s in sources.items()}

    def dist(items: list[dict], field: str) -> dict[str, int]:
        n = Counter(i[field] for i in items)
        return {v: n.get(v, 0) for v in CHECKER_V2_FIELDS[field]}
    relation = {k: dist(v, "relation") for k, v in answered.items()}
    gen = answered["generated"]
    flagged = [c for c in checked if c.get("inconsistent")]
    return {"population": "answered items (verdict not missing)",
            "n_answered": {k: len(v) for k, v in answered.items()},
            "relation": relation,
            "precision": {k: {p: sum(n for r, n in rel.items() if RELATION_PRECISION[r] == p) for p in PRECISION_VALUES}
                          for k, rel in relation.items()},
            "yes_by_relation": {r: wilson(sum(1 for c in gen if c["relation"] == r and c["verdict"] == "yes"),
                                          sum(1 for c in gen if c["relation"] == r)) for r in CHECKER_RELATIONS},
            "inconsistent": {**{k: sum(1 for c in flagged if c["source"] == s) for k, s in sources.items()},
                             "total": len(flagged), "item_ids": [c["id"] for c in flagged]},
            "sentence_natural": {"generated": dist(gen, "sentence_natural"),
                                 "by_arm": {a: dist([c for c in gen if c["arm"] == a], "sentence_natural") for a in ARMS}},
            "patient_realism": {"generated": dist(gen, "patient_realism"),
                                "by_arm": {a: dist([c for c in gen if c["arm"] == a], "patient_realism") for a in ARMS}}}


def compute() -> tuple[dict, str]:
    """Every estimand and the markdown rendering, pure: (summary, summary.md text). main writes them; write_manifest.py
    finalize computes them again and refuses a summary on disk that differs (Codex review of PR #52)."""
    seeds = load_seeds()
    calls = load_calls()  # every prompt verified against its stored hash
    version = plan_version(calls)  # load_calls and load_checker_batches derive both plans under the design's version
    call_log = read_jsonl(PILOT / "call_log.jsonl")
    rows = read_jsonl(PILOT / "generated" / "all_rows.jsonl")
    failures = read_jsonl(PILOT / "generated" / "format_failures.jsonl")
    checked = read_jsonl(PILOT / "checked.jsonl")
    plan_path = PILOT / "checker_batches.json"
    checker_meta = load_checker_batches()
    # the checker plan must have been built from the generation rows and seeds on disk, and checked.jsonl must be
    # that plan's parse: a count-only check let a previous run's verdicts join a new run's rows (Codex review of
    # PR #52)
    planned_inputs = checker_meta.get("input_hashes")
    if not isinstance(planned_inputs, dict):
        raise SystemExit("compute_summary: checker_batches.json records no input_hashes; re-run build_checker_set.py "
                         "so the checker plan is bound to its inputs")
    live = {"seeds_json_sha256": sha256_file(PILOT / "seeds.json"),
            "all_rows_jsonl_sha256": sha256_file(PILOT / "generated" / "all_rows.jsonl")}
    stale = [k for k, v in live.items() if planned_inputs.get(k) != v]
    if stale:
        raise SystemExit(f"compute_summary: checker_batches.json was built from different inputs ({', '.join(stale)} "
                         f"changed since build_checker_set.py ran); rebuild the checker set and re-run the checker")
    problems = checked_problems(checked, read_jsonl(PILOT / "checker_key.jsonl"),
                                read_jsonl(PILOT / "checker_set.jsonl"), sha256_file(plan_path), version)
    if problems:
        shown = problems[:5] + ([f"... and {len(problems) - 5} more"] if len(problems) > 5 else [])
        raise SystemExit("compute_summary: checked.jsonl is not the parse of the checker plan on disk; re-run "
                         "parse_checker.py on that plan's result:\n  " + "\n  ".join(shown))
    # the parsed generation must be the call plan's: final records and rows carry the planned prompt's hash, so a
    # previous run's responses cannot be summarized under re-planned prompts (Codex review of PR #52)
    gen_problems = generation_problems(calls, call_log, rows, failures)
    if gen_problems:
        shown = gen_problems[:5] + ([f"... and {len(gen_problems) - 5} more"] if len(gen_problems) > 5 else [])
        raise SystemExit("compute_summary: call_log.jsonl and generated/all_rows.jsonl are not the parse of the call "
                         "plan on disk; re-run parse_generation.py on that plan's result:\n  " + "\n  ".join(shown))
    if not (PILOT / "review_map.json").exists():
        raise SystemExit("compute_summary: review_map.json is missing; run make_review_sheet.py first")
    review = json.loads((PILOT / "review_map.json").read_text(encoding="utf-8"))
    # the review bundle must sample these checked rows: stamped with the plan and equal field for field (Codex
    # review of PR #52)
    rev_problems = review_problems(review, read_csv(PILOT / "review_sheet.csv"), read_csv(PILOT / "review_key.csv"),
                                   checked, sha256_file(plan_path), version)
    if rev_problems:
        shown = rev_problems[:5] + ([f"... and {len(rev_problems) - 5} more"] if len(rev_problems) > 5 else [])
        raise SystemExit("compute_summary: the review bundle does not sample the checked rows on disk; re-run "
                         "make_review_sheet.py (move a sheet with annotations aside first):\n  " + "\n  ".join(shown))
    cell_ids = [cell_id(s, t) for s, t in cells()]
    S: dict = {"harness_version": version} if version >= 2 else {}  # version 1: no key, as recorded
    S.update({"n_seeds": len(seeds), "k_exemplars_used": calls["k_exemplars_used"],
               "k_exemplars_requested": calls["k_exemplars_requested"],
               # what the seed file says about itself; a seed without a provenance field is reported, not assumed
               "seed_provenance": sorted({s.get("provenance", "MISSING") for s in seeds}),
               # the seeds behind every random draw, so the intervals are reproducible from this file alone
               "seeds": {"master_seed": MASTER_SEED, "exemplar_sampling": f"random.Random({MASTER_SEED})",
                         "bootstrap": f"random.Random('{MASTER_SEED}:bootstrap')", "n_boot": N_BOOT,
                         "broken_pairs": f"random.Random('{MASTER_SEED}:broken')",
                         "checker_shuffle": f"random.Random('{MASTER_SEED}:checker_shuffle')",
                         "review_sample": f"random.Random('{MASTER_SEED}:review')"}})
    # the files this summary was computed from, so finalize can refuse a summary that predates any of them (Codex
    # review of PR #52)
    S["input_hashes"] = {name: sha256_file(PILOT / name) for name in SUMMARY_INPUTS}
    S["script_hashes"] = script_hashes()  # the code this summary stands under; finalize refuses a later edit

    # ---- run overview
    # every attempt, final or not, must be what the recorded result files derive under the current code: a call log
    # left by an interrupted --replace could carry a stale first attempt into the retry and pooled-attempt numbers,
    # and finalize would catch it only afterwards (Codex review of PR #52)
    problems = rederive_problems(calls)
    if problems:
        raise SystemExit("compute_summary: the files on disk are not what the current code derives from the two "
                         "recorded result files; re-run the chain from parse_generation.py:\n  " + "\n  ".join(problems[:5]))
    finals = [e for e in call_log if e.get("is_final")]  # one per planned call, checked by generation_problems
    S["run"] = {"n_calls": len(calls["calls"]), "n_attempts": len(call_log),
                "n_retried_calls": sum(1 for e in call_log if e.get("is_final") is False),
                "calls_with_valid_rows": wilson(sum(1 for e in finals if e["n_valid"] > 0), len(finals)),
                "calls_without_response": sum(1 for e in finals if e.get("status") == "no_response_recorded"),
                "per_call": [{k: e[k] for k in ("call_id", "arm", "cell", "attempt", "n_lines", "n_valid",
                                                 "n_invalid", "n_control", "n_noncontrol", "reasons", "status")}
                             for e in finals],
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
    # a control whose term keeps no letter or digit has no lexical content to compare: excluded from the fidelity
    # denominator and counted, never scored as faithful (Codex review of PR #52)
    meas = [r for r in ctrl if control_measurable(r)]
    S["controls"] = {"n_control_rows": len(ctrl), "expected": 4 * len(calls["calls"]),
                     "unmeasurable": len(ctrl) - len(meas),
                     "faithful": wilson(sum(1 for r in meas if r["control_faithful"]), len(meas)),
                     "by_arm": {a: wilson(sum(1 for r in meas if r["arm"] == a and r["control_faithful"]),
                                          sum(1 for r in meas if r["arm"] == a)) for a in ARMS}}

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
    # a template with no TF-IDF token has no measurable similarity: it is excluded from every cosine and counted,
    # never scored as 0 against everything and passed as maximally diverse (Codex review of PR #52)
    vec_all = {r["id"]: tf.vector(r["template"]) for r in gen}
    unmeasurable = [r for r in gen if vec_all[r["id"]] is None]
    vec = {k: v for k, v in vec_all.items() if v is not None}
    seed_vec_all = [(s["id"], tf.vector(s["template"])) for s in seeds]
    seed_vecs = [v for _, v in seed_vec_all if v is not None]
    by_arm_cell = {a: {c: [vec[r["id"]] for r in gen if r["arm"] == a and r["cell"] == c and r["id"] in vec]
                       for c in cell_ids} for a in ARMS}
    E3: dict = {"within_cell": {a: {} for a in ARMS}, "arm_mean_of_cells": {}, "vs_seeds": {}, "diff_A_minus_B": {},
                "n_boot": N_BOOT, "bootstrap_seed": S["seeds"]["bootstrap"], "tfidf_fit_docs": tf.n,
                "unmeasurable_templates": {"n": len(unmeasurable),
                                           "by_arm": {a: sum(1 for r in unmeasurable if r["arm"] == a) for a in ARMS},
                                           "row_ids": [r["id"] for r in unmeasurable]},
                "unmeasurable_seed_templates": [sid for sid, v in seed_vec_all if v is None]}
    for a in ARMS:
        for c in cell_ids:
            m, pairs = mean_pairwise(by_arm_cell[a][c])
            E3["within_cell"][a][c] = {"n_rows": len(by_arm_cell[a][c]), "n_pairs": pairs, "mean": m}
    B = bootstrap_diversity(by_arm_cell, seed_vecs, rng("bootstrap"), N_BOOT)
    # the point estimate over the same fixed cell set the replicates use (cells with at least two rows)
    point = {}
    for a in ARMS:
        vals = [E3["within_cell"][a][c]["mean"] for c in B["fixed_cells"][a]]
        point[a] = sum(vals) / len(vals) if vals else None
    cross_point = {a: mean_cross([v for c in cell_ids for v in by_arm_cell[a][c]], seed_vecs) for a in ARMS}
    for a in ARMS:
        E3["arm_mean_of_cells"][a] = {"mean": point[a], "n_rows": sum(len(v) for v in by_arm_cell[a].values()),
                                      "n_cells_with_pairs": len(B["fixed_cells"][a]),
                                      "n_boot_effective": len(B["boot"][a]),
                                      "n_undefined_replicates": B["n_undefined"][a], **pct(B["boot"][a])}
        E3["vs_seeds"][a] = {"mean": cross_point[a][0], "n_pairs": cross_point[a][1], **pct(B["boot_cross"][a])}
    E3["diff_A_minus_B"] = {"within_cell": {"diff": (point["A"] - point["B"]) if None not in point.values() else None,
                                            "n_boot_effective": len(B["boot_diff"]),
                                            "n_undefined_replicates": B["n_undefined_diff"], **pct(B["boot_diff"])},
                            "vs_seeds": {"diff": (cross_point["A"][0] - cross_point["B"][0])
                                         if None not in (cross_point["A"][0], cross_point["B"][0]) else None,
                                         **pct(B["boot_cross_diff"])}}
    S["E3"] = E3

    # ---- E4 semantic equivalence, with checker sensitivity and specificity
    def verdict_counts(items):
        return dict(Counter(i["verdict"] for i in items))

    def p_yes(items):
        answered = [i for i in items if i["verdict"] in CHECKER_VERDICTS]  # checked_problems admits nothing else
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
    if version >= 2:  # descriptives outside the protocol's estimands (see the module docstring)
        S["review"].update({k: review.get(k) for k in ("sampling", "n_concepts_by_arm", "n_unique_concepts_in_sample")})
        S["probe_point"] = probe_point_summary(rows, cell_ids, PROBE_ENDINGS)
        S["variant_design"] = variant_design_summary(rows, finals, VARIANT_PAIRS_PER_CALL, CONCEPTS_PER_CALL)
        S["next_word"] = next_word_summary(rows)
        S["checker_v2"] = checker_v2_summary(checked)

    # ---- markdown, rendered from S only (summary.json is written after it, carrying the rendering's hash)
    L = []
    L.append("# Pilot summary (computed by scripts/compute_summary.py)")
    L.append("")
    L.append(f"Seeds: {S['n_seeds']} (provenance as the seed file states it: {'; '.join(S['seed_provenance'])}). Exemplars per call: "
             f"{S['k_exemplars_used']} used, {S['k_exemplars_requested']} requested. Proportions carry 95% Wilson "
             f"intervals; means carry 95% percentile bootstrap intervals ({N_BOOT} resamples, stream "
             f"{S['seeds']['bootstrap']}); differences of proportions carry Newcombe score intervals. Master seed "
             f"{S['seeds']['master_seed']}; every named stream is listed under seeds in summary.json. Values are shown "
             f"to 3 decimals.")
    L.append("")
    if version >= 2:
        L.append(f"Harness version {version}: rows carry next_word, the checker also answers relation, sentence_natural "
                 f"and patient_realism, and the sections marked version 2 report descriptives outside the protocol's "
                 f"estimands.")
        L.append("")
    L.append("## Run overview")
    L.append("")
    R = S["run"]
    L.append(f"| Quantity | Value |\n|---|---|\n| Generation calls | {R['n_calls']} |\n| Attempts (including retries) | "
             f"{R['n_attempts']} |\n| Calls retried | {R['n_retried_calls']} |\n| Calls with at least one valid row | "
             f"{R['calls_with_valid_rows']['x']} / {R['calls_with_valid_rows']['n']} "
             f"(Wilson {ci(R['calls_with_valid_rows'])}) |\n| Calls with no response record | "
             f"{R['calls_without_response']} |")
    L.append("")
    L.append("| Call | Attempt | Lines | Valid | Invalid | Controls | Non-control | Failure reasons |\n|---|---|---|---|---|---|---|---|")
    for e in R["per_call"]:
        reasons = ', '.join(f'{k}: {v}' for k, v in e['reasons'].items() if k != 'ok') or 'none'
        if e["status"] == "no_response_recorded":
            reasons = "no response record"
        L.append(f"| {e['call_id']} | {e['attempt']} | {e['n_lines']} | {e['n_valid']} | {e['n_invalid']} | "
                 f"{e['n_control']} | {e['n_noncontrol']} | {reasons} |")
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
    L.append(f"Controls with no lexical content in a term (no letter or digit after normalization; excluded from the "
             f"fidelity denominator and counted): {C['unmeasurable']}.")
    L.append("")
    L.append("| Scope | Faithful (surface form only) / controls | Proportion | 95% Wilson |\n|---|---|---|---|")
    L.append(prop_row("Both arms", C["faithful"]))
    for a in ARMS:
        L.append(prop_row(f"Arm {a}", C["by_arm"][a]))
    L.append("")
    if version >= 2:
        L.extend(v2_generation_markdown(S, cell_ids))
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
    U = E3["unmeasurable_templates"]
    L.append(f"Templates with no TF-IDF token (no measurable similarity; excluded from every cosine and counted): "
             f"{U['n']} generated (Arm A {U['by_arm']['A']}, Arm B {U['by_arm']['B']}), "
             f"{len(E3['unmeasurable_seed_templates'])} seed.")
    L.append("")
    L.append("| Arm | Cell | Rows | Pairs | Mean cosine |\n|---|---|---|---|---|")
    for a in ARMS:
        for c in cell_ids:
            e = E3["within_cell"][a][c]
            L.append(f"| {a} | {c} | {e['n_rows']} | {e['n_pairs']} | {fmt(e['mean'])} |")
    L.append("")
    L.append("| Arm | Mean of cell means | 95% bootstrap | Rows | Cells with pairs | Replicates used | Undefined replicates |\n"
             "|---|---|---|---|---|---|---|")
    for a in ARMS:
        e = E3["arm_mean_of_cells"][a]
        L.append(f"| {a} | {fmt(e['mean'])} | {ci(e)} | {e['n_rows']} | {e['n_cells_with_pairs']} | "
                 f"{e['n_boot_effective']} | {e['n_undefined_replicates']} |")
    L.append("")
    L.append("The cell set is fixed across replicates (cells with at least two rows). A replicate in which a cell "
             "resamples to copies of one row has no within-cell statistic; it is skipped and counted, never computed "
             "over fewer cells.")
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
    if version >= 2:
        L.extend(v2_checker_markdown(S["checker_v2"]))
    L.append("## Estimand 5: exemplar sensitivity, Arm A (random exemplars) minus Arm B (fixed exemplars)")
    L.append("")
    E5 = S["E5"]
    L.append("| Estimand | Arm A | Arm B | A minus B | 95% interval for the difference |\n|---|---|---|---|---|")
    L.append(f"| 2 novelty (pair) | {fmt(S['E2']['by_arm']['A']['pair']['p'])} | {fmt(S['E2']['by_arm']['B']['pair']['p'])} | "
             f"{fmt(E5['novelty_pair']['diff'])} | {ci(E5['novelty_pair'])} (Newcombe) |")
    L.append(f"| 3 within-cell diversity (mean cosine) | {fmt(E3['arm_mean_of_cells']['A']['mean'])} | "
             f"{fmt(E3['arm_mean_of_cells']['B']['mean'])} | {fmt(E5['diversity_within_cell']['diff'])} | "
             f"{ci(E5['diversity_within_cell'])} (bootstrap, {E5['diversity_within_cell']['n_boot_effective']} replicates, "
             f"{E5['diversity_within_cell']['n_undefined_replicates']} undefined) |")
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
    if version >= 2:
        R2 = S["review"]
        L.append(f"Version 2 sampling: {R2['sampling']} (a concept is the call, the clinical term's surface key and the "
                 f"template); concepts by arm {R2['n_concepts_by_arm']}; {R2['n_unique_concepts_in_sample']} distinct "
                 f"concepts among the {R2['n']} rows. review_key.csv also carries the checker's relation, "
                 f"sentence_natural and patient_realism.")
        L.append("")
    return S, "\n".join(L)


def counts_cell(d: dict[str, int]) -> str:
    """A value-to-count mapping for a table cell, in the listed order."""
    return ", ".join(f"{k} {v}" for k, v in d.items())


def v2_generation_markdown(S: dict, cell_ids: list[str]) -> list[str]:
    """The version-2 generation descriptives: probe point, variant design, next_word."""
    pp, vd, nw = S["probe_point"], S["variant_design"], S["next_word"]
    L = ["## Probe point (version 2, descriptive; not a format failure)", "",
         (f"A template meets the probe point when, stripped, its last word is one of {', '.join(pp['endings'])} "
          f"(case-insensitive). Population: {pp['population']}."), "",
         "| Scope | Ending on a probe word / rows | Proportion | 95% Wilson |\n|---|---|---|---|",
         prop_row("All rows", pp["overall"])]
    L += [prop_row(f"Control {k}", pp["by_control"][k]) for k in pp["by_control"]]
    L += [prop_row(f"Arm {a}", pp["by_arm"][a]) for a in ARMS]
    L += [prop_row(f"Cell {c}", pp["by_cell"][c]) for c in cell_ids]
    L += ["", "## Variant design (version 2, descriptive)", "", f"Definition: {vd['definition']}.", "",
          "| Scope | Compliant calls / calls | Proportion | 95% Wilson |\n|---|---|---|---|",
          prop_row("All calls", vd["calls_compliant"])]
    L += [prop_row(f"Arm {a}", vd["by_arm"][a]) for a in ARMS]
    L += ["", (f"Adjacent variant pairs: {vd['pairs_exact']} with the clinical term exact, "
               f"{vd['pairs_clinical_surface']} with it equal in surface form (expected "
               f"{vd['expected_pairs_per_call']} per call). Same-concept rows that are not adjacent: "
               f"{vd['non_adjacent_repeats']}. Runs of three or more rows of one concept: "
               f"{vd['runs_of_three_or_more']}. Flagged calls: {', '.join(vd['flagged_calls']) or 'none'}."), "",
          ("| Call | Rows (control none) | Concepts | Pairs (exact) | Pairs (surface) | Non-adjacent repeats | "
           "Runs of 3+ | Compliant |\n|---|---|---|---|---|---|---|---|")]
    L += [(f"| {c['call_id']} | {c['n_rows']} | {c['concepts']} | {c['pairs_exact']} | {c['pairs_clinical_surface']} | "
           f"{c['non_adjacent_repeats']} | {c['runs_of_three_or_more']} | {'yes' if c['compliant'] else 'no'} |")
          for c in vd["per_call"]]
    L += ["", "## next_word (version 2)", "",
          f"Population: {nw['population']}: {nw['n_rows']} rows, {nw['n_distinct']} distinct words.", "",
          "| next_word | Rows |\n|---|---|"]
    L += [f"| {x['word']} | {x['n']} |" for x in nw["most_common"]]
    L.append("")
    return L


def v2_checker_markdown(cv: dict) -> list[str]:
    """The version-2 checker descriptives: relation, precision, yes-rate by relation, inconsistent answers,
    sentence_natural and patient_realism."""
    L = ["## Checker relation, precision, sentence and realism (version 2, descriptive)", "",
         (f"Population: {cv['population']}; answered generated {cv['n_answered']['generated']}, known-good "
          f"{cv['n_answered']['known_good']}, broken {cv['n_answered']['broken']}."), "",
         "| Items | Relation counts | Precision (derived from relation) |\n|---|---|---|"]
    L += [f"| {k.replace('_', '-')} | {counts_cell(cv['relation'][k])} | {counts_cell(cv['precision'][k])} |"
          for k in ("generated", "known_good", "broken")]
    L += ["", "| Relation (generated) | Judged equivalent / answered | Proportion | 95% Wilson |\n|---|---|---|---|"]
    L += [prop_row(r, w) for r, w in cv["yes_by_relation"].items()]
    inc = cv["inconsistent"]
    L += ["", (f"Answers whose equivalent contradicts their relation (kept as given, flagged inconsistent): "
               f"{inc['total']} (generated {inc['generated']}, known-good {inc['known_good']}, broken "
               f"{inc['broken']})."),
          "", "| Scope (generated) | sentence_natural | patient_realism |\n|---|---|---|",
          (f"| All | {counts_cell(cv['sentence_natural']['generated'])} | "
           f"{counts_cell(cv['patient_realism']['generated'])} |")]
    L += [(f"| Arm {a} | {counts_cell(cv['sentence_natural']['by_arm'][a])} | "
           f"{counts_cell(cv['patient_realism']['by_arm'][a])} |") for a in ARMS]
    L.append("")
    return L


def main() -> None:
    sealed_interpreter_guard("compute_summary", platform.python_version())  # before anything is computed or written
    S, md = compute()
    (PILOT / "summary.md").write_text(md, encoding="utf-8", newline="\n")
    S["summary_md_sha256"] = sha256_text(md)  # the rendering this summary stands for (equal to the file's hash)
    (PILOT / "summary.json").write_text(json.dumps(S, indent=2) + "\n", encoding="utf-8")
    write_results_block(S)  # the handoff's Results section, from the same dictionaries (Codex review of PR #52)
    print("summary.json and summary.md written; results block written into HANDOFF.md")


if __name__ == "__main__":
    main()
