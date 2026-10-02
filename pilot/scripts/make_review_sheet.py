"""Draw the human review sample: 40 checked generated rows, allocated to arms in proportion to their checked row
counts (largest remainder), sampled and ordered with a named seed, checker verdict withheld from the sheet.

Writes review_sheet.csv, review_key.csv, review_map.json (review id to generated row id, stamped with the hash of
the checker plan whose parse the sheet samples, so a later step can refuse a stale bundle; Codex review of PR #52).

Under harness version 2 (design.json review_sampling "one_row_per_concept") the draw takes at most one row per
concept, a concept being (call, surface key of clinical_term, template), so a concept's two phrasings never both
reach the reviewer: the 40 rows are allocated to arms in proportion to their concepts (largest remainder), concepts
are sampled with the same named stream, then one row per sampled concept from that stream, then shuffled. The map
records sampling, n_concepts_by_arm and n_unique_concepts_in_sample, and review_key.csv also carries the checker's
relation, sentence_natural and patient_realism. A version-1 draw is byte-identical to the recorded run's.

  python3 scripts/make_review_sheet.py [--replace]

A run directory whose manifest.json is finalized is not written into without --replace (common.finalized_run_guard).
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

from common import (
    ARMS,
    CHECKER_V2_FIELDS,
    N_REVIEW,
    PILOT,
    call_id_of,
    checked_problems,
    concept_key,
    finalized_run_guard,
    plan_version,
    read_jsonl,
    review_key_columns,
    rng,
    sha256_file,
    write_csv,
)


def annotated_rows(sheet_path: Path) -> list[str]:
    """Ids of rows in an existing review sheet that carry a label or a note: human work that no rerun may erase
    (Codex review of PR #52)."""
    if not sheet_path.exists():
        return []
    with sheet_path.open(newline="", encoding="utf-8") as fh:
        return [row.get("id", "?") for row in csv.DictReader(fh)
                if (row.get("my_label") or "").strip() or (row.get("my_notes") or "").strip()]


def main(replace: bool = False) -> None:
    finalized_run_guard("make_review_sheet", replace)
    sheet_path = PILOT / "review_sheet.csv"
    done = annotated_rows(sheet_path)
    if done:
        raise SystemExit(f"make_review_sheet: review_sheet.csv holds annotations on {len(done)} row(s) (first: "
                         f"{done[0]}); a sheet with human work is not regenerated. Move it aside to draw a new one.")
    all_checked = read_jsonl(PILOT / "checked.jsonl")
    plan_sha = sha256_file(PILOT / "checker_batches.json")
    version = plan_version(json.loads((PILOT / "checker_batches.json").read_text(encoding="utf-8")))
    problems = checked_problems(all_checked, read_jsonl(PILOT / "checker_key.jsonl"),
                                read_jsonl(PILOT / "checker_set.jsonl"), plan_sha, version)
    if problems:  # the sheet samples the plan's parse and nothing else (Codex review of PR #52)
        raise SystemExit("make_review_sheet: checked.jsonl is not the parse of the checker plan on disk; re-run "
                         "parse_checker.py on that plan's result:\n  " + "\n  ".join(problems[:5]))
    sheet, key, review_map = derive(all_checked, plan_sha, version=version)
    write_csv(sheet_path, sheet, ["id", "clinical_term", "patient_term", "template", "my_label", "my_notes"])
    write_csv(PILOT / "review_key.csv", key, review_key_columns(version))
    (PILOT / "review_map.json").write_text(json.dumps(review_map, indent=2) + "\n", encoding="utf-8")
    print(f"review sheet: {len(sheet)} rows, allocation {review_map['allocation']}, checked rows by arm "
          f"{review_map['n_checked_by_arm']}"
          + (f", concepts by arm {review_map['n_concepts_by_arm']}, {review_map['n_unique_concepts_in_sample']} "
             f"concepts in the sample" if version >= 2 else ""))


def derive(all_checked: list[dict], plan_sha: str, *, version: int) -> tuple[list[dict], list[dict], dict]:
    """The draw itself, pure and deterministic under the named seed: (sheet rows, key rows, the review_map.json
    document). main writes these; write_manifest.py finalize derives them again from the checked rows and refuses a
    bundle whose files differ (Codex review of PR #52). `version` is the checker plan's harness version: 2 draws one
    row per concept (derive_one_per_concept)."""
    if version >= 2:
        return derive_one_per_concept(all_checked, plan_sha)
    checked = [c for c in all_checked if c["source"] == "generated"]
    by_arm = {a: [c for c in checked if c["arm"] == a] for a in ARMS}
    total = sum(len(v) for v in by_arm.values())
    n = min(N_REVIEW, total)
    quota = {a: n * len(by_arm[a]) / total for a in ARMS} if total else {a: 0 for a in ARMS}
    alloc = {a: math.floor(q) for a, q in quota.items()}
    for a in sorted(ARMS, key=lambda a: quota[a] - alloc[a], reverse=True)[: n - sum(alloc.values())]:
        alloc[a] += 1
    r = rng("review")
    chosen = []
    for a in ARMS:
        chosen.extend(r.sample(by_arm[a], min(alloc[a], len(by_arm[a]))))
    r.shuffle(chosen)
    sheet, key, mapping = [], [], {}
    for i, c in enumerate(chosen):
        rid = f"r{i + 1:03d}"
        sheet.append({"id": rid, "clinical_term": c["clinical_term"], "patient_term": c["patient_term"],
                      "template": c["template"], "my_label": "", "my_notes": ""})
        key.append({"id": rid, "arm": c["arm"], "cell": c["cell"], "checker_verdict": c["verdict"]})
        mapping[rid] = c["row_id"]
    review_map = {"allocation": alloc, "n_checked_by_arm": {a: len(v) for a, v in by_arm.items()},
                  # the checker plan whose parse this sheet samples
                  "checker_plan_sha256": plan_sha, "map": mapping}
    return sheet, key, review_map


def largest_remainder(n: int, sizes: dict[str, int]) -> dict[str, int]:
    """n split across the arms in proportion to `sizes`, floors first, then one more to the largest remainders (ties in
    ARMS order, as Python's stable sort leaves them)."""
    total = sum(sizes.values())
    quota = {a: n * sizes[a] / total for a in ARMS} if total else {a: 0 for a in ARMS}
    alloc = {a: math.floor(q) for a, q in quota.items()}
    for a in sorted(ARMS, key=lambda a: quota[a] - alloc[a], reverse=True)[: n - sum(alloc.values())]:
        alloc[a] += 1
    return alloc


def row_concept(c: dict) -> tuple[str, str, str]:
    """A checked generated row's concept: its call (from arm and cell), clinical term surface key and template."""
    return concept_key(call_id_of(c["arm"], c["cell"]), c["clinical_term"], c["template"])


def derive_one_per_concept(all_checked: list[dict], plan_sha: str) -> tuple[list[dict], list[dict], dict]:
    """The version-2 draw: concepts are the checked generated rows grouped by row_concept, in the order of each
    concept's smallest row id; min(N_REVIEW, concepts) are allocated to arms in proportion to concepts per arm by
    largest remainder; the named stream `review` samples that many concepts per arm (arms in ARMS order), then picks
    one row of each sampled concept (rows in row-id order) in the order sampled, then shuffles the picks. A concept's
    rows share their call and so their arm."""
    checked = sorted((c for c in all_checked if c["source"] == "generated"), key=lambda c: c["row_id"])
    concepts: dict[tuple[str, str, str], list[dict]] = {}
    for c in checked:
        concepts.setdefault(row_concept(c), []).append(c)
    by_arm = {a: [rows for rows in concepts.values() if rows[0]["arm"] == a] for a in ARMS}
    n = min(N_REVIEW, sum(len(v) for v in by_arm.values()))
    alloc = largest_remainder(n, {a: len(v) for a, v in by_arm.items()})
    r = rng("review")
    sampled = []
    for a in ARMS:
        sampled.extend(r.sample(by_arm[a], min(alloc[a], len(by_arm[a]))))
    chosen = [r.choice(rows) for rows in sampled]
    r.shuffle(chosen)
    sheet, key, mapping = [], [], {}
    for i, c in enumerate(chosen):
        rid = f"r{i + 1:03d}"
        sheet.append({"id": rid, "clinical_term": c["clinical_term"], "patient_term": c["patient_term"],
                      "template": c["template"], "my_label": "", "my_notes": ""})
        # a missing verdict has no further answers: an empty cell, as the CSV reads back
        key.append({"id": rid, "arm": c["arm"], "cell": c["cell"], "checker_verdict": c["verdict"],
                    **{f"checker_{f}": c.get(f) or "" for f in CHECKER_V2_FIELDS}})
        mapping[rid] = c["row_id"]
    review_map = {"allocation": alloc, "n_checked_by_arm": {a: sum(1 for c in checked if c["arm"] == a) for a in ARMS},
                  "sampling": "one_row_per_concept",
                  "n_concepts_by_arm": {a: len(v) for a, v in by_arm.items()},
                  "n_unique_concepts_in_sample": len({row_concept(c) for c in chosen}),
                  # the checker plan whose parse this sheet samples
                  "checker_plan_sha256": plan_sha, "map": mapping}
    return sheet, key, review_map


if __name__ == "__main__":
    main(replace="--replace" in sys.argv[1:])
