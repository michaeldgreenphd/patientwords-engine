"""Build the blind checker set: every generated non-control format-valid row, the known-good seed rows, and the
deliberately broken pairs (patient_term re-paired across rows within the same cell). Shuffle, assign opaque ids,
and render the checker prompts in batches of 30.

Writes checker_set.jsonl (what the checker sees), checker_key.jsonl (truth, kept separate), checker_batches.json.
"""
from __future__ import annotations

import json
from collections import defaultdict

from common import (
    CHECKER_BATCH,
    N_BROKEN,
    N_KNOWN_GOOD,
    PILOT,
    cell_id,
    cells,
    generation_problems,
    load_calls,
    load_seeds,
    read_jsonl,
    rng,
    sha256_file,
    sha256_text,
    surface_key,
    write_jsonl,
)


def donors_for(target: dict, cand: list[dict]) -> list[dict]:
    """Rows of the same cell whose clinical and patient terms both differ from the target's after removing casing,
    punctuation and spacing: re-pairing the target with any of them gives a pair generated for a different concept."""
    return [d for d in cand if d["id"] != target["id"]
            and surface_key(d["clinical_term"]) != surface_key(target["clinical_term"])
            and surface_key(d["patient_term"]) != surface_key(target["patient_term"])]


def eligible_targets(cand: list[dict]) -> dict[str, list[dict]]:
    """Target row id to its donors, for the rows that have at least one donor. Targets are sampled from these, so a
    cell never falls short of its quota while eligible rows remain (Codex review of PR #52)."""
    out = {}
    for t in cand:
        donors = donors_for(t, cand)
        if donors:
            out[t["id"]] = donors
    return out


def main() -> None:
    all_rows = read_jsonl(PILOT / "generated" / "all_rows.jsonl")
    calls = load_calls()
    problems = generation_problems(calls, read_jsonl(PILOT / "call_log.jsonl"), all_rows)
    if problems:  # rows from another plan must not enter the checker set (Codex review of PR #52)
        raise SystemExit("build_checker_set: the parsed generation is not the call plan's; re-run parse_generation.py "
                         "on that plan's result:\n  " + "\n  ".join(problems[:5]))
    rows = [r for r in all_rows if r["control"] == "none"]
    seeds = load_seeds()
    items, key, notes = [], [], []

    for r in rows:
        items.append({"clinical_term": r["clinical_term"], "patient_term": r["patient_term"], "template": r["template"]})
        key.append({"source": "generated", "row_id": r["id"], "arm": r["arm"], "cell": r["cell"]})

    n_good = min(N_KNOWN_GOOD, len(seeds))
    if n_good < N_KNOWN_GOOD:
        notes.append(f"known-good rows: {n_good} seeds available, {N_KNOWN_GOOD} requested")
    for s in seeds[:n_good]:
        items.append({"clinical_term": s["clinical_term"], "patient_term": s["patient_term"], "template": s["template"]})
        key.append({"source": "seed", "row_id": s["id"], "arm": None, "cell": cell_id(s["specialty"], s["swap_type"])})

    r = rng("broken")
    pool = defaultdict(list)
    for row in rows:
        pool[row["cell"]].append(row)
    cell_ids = [cell_id(s, t) for s, t in cells()]
    alloc = {c: N_BROKEN // len(cell_ids) for c in cell_ids}
    for c in r.sample(cell_ids, N_BROKEN % len(cell_ids)):
        alloc[c] += 1
    n_broken = 0
    for c in cell_ids:
        cand = pool[c]
        elig = eligible_targets(cand)
        eligible = [t for t in cand if t["id"] in elig]  # cell order preserved, so the draw is reproducible
        if len(eligible) < alloc[c]:
            notes.append(f"broken pairs: cell {c} has {len(eligible)} eligible rows of {len(cand)}, {alloc[c]} wanted")
        targets = r.sample(eligible, min(alloc[c], len(eligible)))
        for t in targets:
            d = r.choice(elig[t["id"]])
            items.append({"clinical_term": t["clinical_term"], "patient_term": d["patient_term"],
                          "template": t["template"]})
            key.append({"source": "broken", "row_id": t["id"], "arm": t["arm"], "cell": c, "donor_row_id": d["id"]})
            n_broken += 1
    if n_broken < N_BROKEN:
        notes.append(f"broken pairs: built {n_broken} of {N_BROKEN}")

    order = list(range(len(items)))
    rng("checker_shuffle").shuffle(order)
    blind, truth = [], []
    for pos, i in enumerate(order):
        cid = f"c{pos + 1:04d}"
        blind.append({"id": cid, **items[i]})
        truth.append({"id": cid, **key[i]})
    write_jsonl(PILOT / "checker_set.jsonl", blind)
    write_jsonl(PILOT / "checker_key.jsonl", truth)

    template = (PILOT / "prompts" / "checker_prompt.txt").read_text(encoding="utf-8")
    batches = []
    for b in range(0, len(blind), CHECKER_BATCH):
        chunk = blind[b:b + CHECKER_BATCH]
        prompt = template.replace("{{ITEMS}}", "\n".join(json.dumps(x, ensure_ascii=False) for x in chunk))
        batches.append({"batch_id": f"batch{len(batches) + 1:02d}", "item_ids": [x["id"] for x in chunk],
                        "prompt_sha256": sha256_text(prompt), "prompt": prompt})
    out = {"checker_prompt_template_sha256": sha256_text(template),
           # the inputs this plan was built from: a later step refuses a plan whose template, seeds or generation
           # rows have changed since, instead of recording a stale plan (Codex review of PR #52)
           "input_hashes": {"checker_prompt_template_sha256": sha256_text(template),
                            "seeds_json_sha256": sha256_file(PILOT / "seeds.json"),
                            "all_rows_jsonl_sha256": sha256_file(PILOT / "generated" / "all_rows.jsonl")},
           "batch_size": CHECKER_BATCH,
           "n_items": len(blind), "n_generated": len(rows), "n_known_good": n_good, "n_broken": n_broken,
           "notes": notes, "batches": batches}
    (PILOT / "checker_batches.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"checker set: {len(blind)} items = {len(rows)} generated + {n_good} known-good + {n_broken} broken; "
          f"{len(batches)} batches of <= {CHECKER_BATCH}")
    for n in notes:
        print("  note:", n)


if __name__ == "__main__":
    main()
