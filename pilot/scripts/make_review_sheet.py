"""Draw the human review sample: 40 checked generated rows, allocated to arms in proportion to their checked row
counts (largest remainder), sampled and ordered with a named seed, checker verdict withheld from the sheet.

Writes review_sheet.csv, review_key.csv, review_map.json (review id to generated row id, stamped with the hash of
the checker plan whose parse the sheet samples, so a later step can refuse a stale bundle; Codex review of PR #52).
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from common import ARMS, N_REVIEW, PILOT, checked_problems, read_jsonl, rng, sha256_file, write_csv


def annotated_rows(sheet_path: Path) -> list[str]:
    """Ids of rows in an existing review sheet that carry a label or a note: human work that no rerun may erase
    (Codex review of PR #52)."""
    if not sheet_path.exists():
        return []
    with sheet_path.open(newline="", encoding="utf-8") as fh:
        return [row.get("id", "?") for row in csv.DictReader(fh)
                if (row.get("my_label") or "").strip() or (row.get("my_notes") or "").strip()]


def main() -> None:
    sheet_path = PILOT / "review_sheet.csv"
    done = annotated_rows(sheet_path)
    if done:
        raise SystemExit(f"make_review_sheet: review_sheet.csv holds annotations on {len(done)} row(s) (first: "
                         f"{done[0]}); a sheet with human work is not regenerated. Move it aside to draw a new one.")
    all_checked = read_jsonl(PILOT / "checked.jsonl")
    plan_sha = sha256_file(PILOT / "checker_batches.json")
    problems = checked_problems(all_checked, read_jsonl(PILOT / "checker_key.jsonl"),
                                read_jsonl(PILOT / "checker_set.jsonl"), plan_sha)
    if problems:  # the sheet samples the plan's parse and nothing else (Codex review of PR #52)
        raise SystemExit("make_review_sheet: checked.jsonl is not the parse of the checker plan on disk; re-run "
                         "parse_checker.py on that plan's result:\n  " + "\n  ".join(problems[:5]))
    sheet, key, review_map = derive(all_checked, plan_sha)
    write_csv(sheet_path, sheet, ["id", "clinical_term", "patient_term", "template", "my_label", "my_notes"])
    write_csv(PILOT / "review_key.csv", key, ["id", "arm", "cell", "checker_verdict"])
    (PILOT / "review_map.json").write_text(json.dumps(review_map, indent=2) + "\n", encoding="utf-8")
    print(f"review sheet: {len(sheet)} rows, allocation {review_map['allocation']}, checked rows by arm "
          f"{review_map['n_checked_by_arm']}")


def derive(all_checked: list[dict], plan_sha: str) -> tuple[list[dict], list[dict], dict]:
    """The draw itself, pure and deterministic under the named seed: (sheet rows, key rows, the review_map.json
    document). main writes these; write_manifest.py finalize derives them again from the checked rows and refuses a
    bundle whose files differ (Codex review of PR #52)."""
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


if __name__ == "__main__":
    main()
