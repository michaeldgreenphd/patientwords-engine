"""Build the blind checker set: every generated non-control format-valid row, the known-good seed rows, and the
deliberately broken pairs (patient_term re-paired across rows within the same cell). Shuffle, assign opaque ids,
and render the checker prompts in batches of 30.

Writes checker_set.jsonl (what the checker sees), checker_key.jsonl (truth, kept separate), checker_batches.json.

  python3 scripts/build_checker_set.py [--replace]

Under harness version 2 the plan records `harness_version` and the checker template must name every version-2
answer field and value (common.checker_enum_problems); a version-1 plan is byte-identical to the recorded run's. A
run directory whose manifest.json is finalized is not written into without --replace (common.finalized_run_guard).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

from common import (
    CHECKER_BATCH,
    CHECKER_MARKERS,
    HARNESS_VERSION,
    N_BROKEN,
    N_KNOWN_GOOD,
    PILOT,
    cell_id,
    cells,
    finalized_run_guard,
    generation_problems,
    load_calls,
    load_seeds,
    read_jsonl,
    rng,
    sha256_file,
    sha256_text,
    stray_marker,
    surface_key,
    template_problems,
    version_template_problems,
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


def derive(all_rows: list[dict], seeds: list[dict], template: str, seeds_sha: str,
           all_rows_sha: str) -> tuple[list[dict], list[dict], dict]:
    """The construction itself, pure and deterministic under the named seeds: (blind set, truth key, the
    checker_batches.json document). main writes these; write_manifest.py finalize derives them again from the files
    on disk and refuses a bundle whose files differ (Codex review of PR #52)."""
    rows = [r for r in all_rows if r["control"] == "none"]
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

    problems = (template_problems(template, CHECKER_MARKERS, "prompts/checker_prompt.txt")
                + version_template_problems(template, "checker", HARNESS_VERSION))
    if problems:
        raise SystemExit("the checker prompt template cannot be rendered; fix it before batching:\n  "
                         + "\n  ".join(problems))
    batches = []
    for b in range(0, len(blind), CHECKER_BATCH):
        chunk = blind[b:b + CHECKER_BATCH]
        prompt = template.replace("{{ITEMS}}", "\n".join(json.dumps(x, ensure_ascii=False) for x in chunk))
        stray = stray_marker(prompt)  # a marker or a brace carried in by an item's own text
        if stray is not None:
            raise SystemExit(f"a rendered checker prompt still carries a marker or stray braces {stray!r}; refusing to batch")
        batches.append({"batch_id": f"batch{len(batches) + 1:02d}", "item_ids": [x["id"] for x in chunk],
                        "prompt_sha256": sha256_text(prompt), "prompt": prompt})
    out = {**({"harness_version": HARNESS_VERSION} if HARNESS_VERSION >= 2 else {}),  # version 1: no key, as recorded
           "checker_prompt_template_sha256": sha256_text(template),
           # the inputs this plan was built from: a later step refuses a plan whose template, seeds or generation
           # rows have changed since, instead of recording a stale plan (Codex review of PR #52)
           "input_hashes": {"checker_prompt_template_sha256": sha256_text(template),
                            "seeds_json_sha256": seeds_sha,
                            "all_rows_jsonl_sha256": all_rows_sha},
           "batch_size": CHECKER_BATCH,
           "n_items": len(blind), "n_generated": len(rows), "n_known_good": n_good, "n_broken": n_broken,
           "notes": notes, "batches": batches}
    return blind, truth, out


def main(replace: bool = False) -> None:
    finalized_run_guard("build_checker_set", replace)
    all_rows = read_jsonl(PILOT / "generated" / "all_rows.jsonl")
    calls = load_calls()
    problems = generation_problems(calls, read_jsonl(PILOT / "call_log.jsonl"), all_rows,
                                   read_jsonl(PILOT / "generated" / "format_failures.jsonl"))
    if problems:  # rows from another plan must not enter the checker set (Codex review of PR #52)
        raise SystemExit("build_checker_set: the parsed generation is not the call plan's; re-run parse_generation.py "
                         "on that plan's result:\n  " + "\n  ".join(problems[:5]))
    import rederive  # the scripts import each other by bare name; rederive imports this module for derive

    # the structural check above passes rows whose text was edited under intact ids, attempts and prompt hashes;
    # the rows must be what the recorded generation journal derives before any checker work is built from them,
    # not only at the summary, after the checker agents have run (Codex review of PR #52)
    problems = rederive.generation_rederive_problems(calls)
    if problems:
        raise SystemExit("build_checker_set: the rows on disk are not what the recorded generation journal derives; "
                         "re-run parse_generation.py --replace on its extraction:\n  " + "\n  ".join(problems[:5]))
    template = (PILOT / "prompts" / "checker_prompt.txt").read_text(encoding="utf-8")
    blind, truth, out = derive(all_rows, load_seeds(), template, sha256_file(PILOT / "seeds.json"),
                               sha256_file(PILOT / "generated" / "all_rows.jsonl"))
    write_jsonl(PILOT / "checker_set.jsonl", blind)
    write_jsonl(PILOT / "checker_key.jsonl", truth)
    (PILOT / "checker_batches.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"checker set: {len(blind)} items = {out['n_generated']} generated + {out['n_known_good']} known-good + "
          f"{out['n_broken']} broken; {len(out['batches'])} batches of <= {CHECKER_BATCH}")
    for n in out["notes"]:
        print("  note:", n)


if __name__ == "__main__":
    main(replace="--replace" in sys.argv[1:])
