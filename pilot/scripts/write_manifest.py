"""Write manifest.json from the files on disk: model facts (from manifest_model.json), date, seeds, prompt hashes,
protocol hash, script hashes. The first run records protocol_sha256_at_write; later runs keep that value and add
protocol_sha256_now so a change to the frozen protocol is visible.

  python3 scripts/write_manifest.py            # plan-time manifest
  python3 scripts/write_manifest.py finalize   # adds output hashes and the finalize timestamp
"""
from __future__ import annotations

import datetime as dt
import json
import platform
import sys

from common import (
    ARMS,
    CHECKER_BATCH,
    CONTROLS_PER_CALL,
    K_EXEMPLARS,
    MASTER_SEED,
    N_BOOT,
    N_BROKEN,
    N_KNOWN_GOOD,
    N_REVIEW,
    PILOT,
    ROWS_PER_CALL,
    SPECIALTIES,
    SWAP_TYPES,
    sha256_file,
)


def main(finalize: bool) -> None:
    path = PILOT / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model = json.loads((PILOT / "manifest_model.json").read_text(encoding="utf-8"))
    calls = json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))
    protocol_now = sha256_file(PILOT / "PROTOCOL.md")
    m = {
        "pilot": "stimulus-generation measurement-validity pilot",
        "date_utc": old.get("date_utc", now[:10]),
        "created_utc": old.get("created_utc", now),
        "finalized_utc": now if finalize else old.get("finalized_utc"),
        "model": model,
        "python": platform.python_version(),
        "seeds": {"master_seed": MASTER_SEED, "exemplar_sampling": "random.Random(20260929), one draw of K per cell in cell order",
                  "named_streams": {p: f"random.Random('{MASTER_SEED}:{p}')" for p in ("broken", "checker_shuffle", "review", "bootstrap")}},
        "design": {"specialties": SPECIALTIES, "swap_types": SWAP_TYPES, "arms": ARMS, "rows_per_call": ROWS_PER_CALL,
                   "controls_per_call": CONTROLS_PER_CALL, "k_exemplars_requested": K_EXEMPLARS,
                   "k_exemplars_used": calls["k_exemplars_used"], "n_seed_cases": calls["n_seeds"],
                   "seed_provenance": "synthetic placeholders written by the agent; nothing was attached",
                   "checker_batch": CHECKER_BATCH, "n_broken": N_BROKEN, "n_known_good_requested": N_KNOWN_GOOD,
                   "n_review": N_REVIEW, "n_boot": N_BOOT},
        "protocol_sha256_at_write": old.get("protocol_sha256_at_write", protocol_now),
        "protocol_sha256_now": protocol_now,
        "protocol_unchanged": old.get("protocol_sha256_at_write", protocol_now) == protocol_now,
        "seeds_json_sha256": sha256_file(PILOT / "seeds.json"),
        "design_json_sha256": sha256_file(PILOT / "design.json"),
        "prompt_hashes": {
            "generation_prompt_template": calls["generation_prompt_template_sha256"],
            "generation_calls": {c["id"]: {"prompt_sha256": c["prompt_sha256"], "exemplar_ids": c["exemplar_ids"]} for c in calls["calls"]},
        },
        "script_hashes": {p.name: sha256_file(p) for p in sorted((PILOT / "scripts").glob("*.py"))},
        "workflow_script_hashes": {p.name: sha256_file(p) for p in sorted((PILOT / "workflows").glob("*.js"))} if (PILOT / "workflows").exists() else {},
    }
    cb = PILOT / "checker_batches.json"
    if cb.exists():
        b = json.loads(cb.read_text(encoding="utf-8"))
        m["prompt_hashes"]["checker_prompt_template"] = b["checker_prompt_template_sha256"]
        m["prompt_hashes"]["checker_batches"] = {x["batch_id"]: x["prompt_sha256"] for x in b["batches"]}
    m["runs"] = old.get("runs", {})
    if finalize:
        outputs = ["calls.json", "call_log.jsonl", "checker_set.jsonl", "checker_key.jsonl", "checker_batches.json",
                   "checked.jsonl", "checker_log.jsonl", "review_sheet.csv", "review_key.csv", "review_map.json",
                   "summary.json", "summary.md", "seeds.json", "design.json", "PROTOCOL.md", "HANDOFF.md",
                   "manifest_model.json"]
        m["output_hashes"] = {o: sha256_file(PILOT / o) for o in outputs if (PILOT / o).exists()}
        gen = sorted((PILOT / "generated").glob("*.jsonl"))
        m["output_hashes"].update({f"generated/{p.name}": sha256_file(p) for p in gen})
        raw = sorted((PILOT / "generated" / "raw").glob("*.txt"))
        m["output_hashes"].update({f"generated/raw/{p.name}": sha256_file(p) for p in raw})
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest.json written ({'finalized' if finalize else 'planned'}); protocol unchanged: {m['protocol_unchanged']}")


if __name__ == "__main__":
    main(finalize=len(sys.argv) > 1 and sys.argv[1] == "finalize")
