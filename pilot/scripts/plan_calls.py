"""Plan the 18 generation calls: sample Arm A exemplars with the integer seed, fix Arm B exemplars, render every
prompt from prompts/generation_prompt.txt, and write calls.json with a SHA-256 per rendered prompt.

Run once before generation. Do not edit the prompt template after running it. The plan is common.derive_plan's
output exactly, and common.load_calls derives it again for every reader, refusing a calls.json that differs (Codex
review of PR #52).

  python3 scripts/plan_calls.py [--replace]

A run directory whose manifest.json is finalized is a sealed record: the plan is not written there unless --replace
is passed (common.finalized_run_guard), so a call with PILOT_DIR unset cannot re-plan the recorded run at pilot/.
"""
from __future__ import annotations

import json
import sys

from common import K_EXEMPLARS, PILOT, derive_plan, finalized_run_guard, load_seeds, sha256_file


def main(replace: bool = False) -> None:
    finalized_run_guard("plan_calls", replace)
    seeds = load_seeds()
    template = (PILOT / "prompts" / "generation_prompt.txt").read_text(encoding="utf-8")
    out = derive_plan(seeds, template, sha256_file(PILOT / "seeds.json"), sha256_file(PILOT / "design.json"))
    (PILOT / "calls.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"calls.json: {len(out['calls'])} calls, n_seeds={out['n_seeds']}, k_exemplars={out['k_exemplars_used']} "
          f"(requested {K_EXEMPLARS})")
    for c in out["calls"]:
        print(f"  {c['id']:45s} exemplars={c['exemplar_ids']}")


if __name__ == "__main__":
    main(replace="--replace" in sys.argv[1:])
