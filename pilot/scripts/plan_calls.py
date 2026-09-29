"""Plan the 18 generation calls: sample Arm A exemplars with the integer seed, fix Arm B exemplars, render every
prompt from prompts/generation_prompt.txt, and write calls.json with a SHA-256 per rendered prompt.

Run once before generation. Do not edit the prompt template after running it.
"""
from __future__ import annotations

import json

from common import (
    K_EXEMPLARS,
    MASTER_SEED,
    PILOT,
    SWAP_DEFINITIONS,
    call_id,
    cell_id,
    cells,
    load_seeds,
    rng,
    sha256_file,
    sha256_text,
)


def render_exemplars(rows: list[dict]) -> str:
    return "\n".join(json.dumps({"clinical_term": r["clinical_term"], "patient_term": r["patient_term"],
                                 "template": r["template"], "control": "none"}, ensure_ascii=False) for r in rows)


def main() -> None:
    seeds = load_seeds()
    n = len(seeds)
    k = min(K_EXEMPLARS, n)
    template = (PILOT / "prompts" / "generation_prompt.txt").read_text(encoding="utf-8")
    r = rng("exemplars")
    fixed = seeds[:k]  # Arm B: the first k seeds in file order, identical in every call
    calls = []
    for specialty, swap_type in cells():
        sampled = r.sample(seeds, k)  # Arm A: one draw per cell, consumed in fixed cell order
        for arm, exemplars in (("A", sampled), ("B", fixed)):
            prompt = (template.replace("{{SPECIALTY}}", specialty)
                      .replace("{{SWAP_TYPE}}", swap_type)
                      .replace("{{SWAP_DEFINITION}}", SWAP_DEFINITIONS[swap_type])
                      .replace("{{EXEMPLARS}}", render_exemplars(exemplars)))
            calls.append({"id": call_id(arm, specialty, swap_type), "arm": arm, "specialty": specialty,
                          "swap_type": swap_type, "cell": cell_id(specialty, swap_type), "k_exemplars": k,
                          "exemplar_ids": [e["id"] for e in exemplars], "prompt_sha256": sha256_text(prompt),
                          "prompt": prompt})
    out = {"master_seed": MASTER_SEED, "n_seeds": n, "k_exemplars_used": k, "k_exemplars_requested": K_EXEMPLARS,
           "generation_prompt_template_sha256": sha256_text(template),
           # the inputs this plan was rendered from: write_manifest.py refuses a plan whose inputs have since changed
           "input_hashes": {"seeds_json_sha256": sha256_file(PILOT / "seeds.json"),
                            "design_json_sha256": sha256_file(PILOT / "design.json"),
                            "generation_prompt_template_sha256": sha256_text(template)},
           "calls": calls}
    (PILOT / "calls.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"calls.json: {len(calls)} calls, n_seeds={n}, k_exemplars={k} (requested {K_EXEMPLARS})")
    for c in calls:
        print(f"  {c['id']:45s} exemplars={c['exemplar_ids']}")


if __name__ == "__main__":
    main()
