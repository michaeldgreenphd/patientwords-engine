"""Write manifest.json from the files on disk: model facts (from manifest_model.json), date, seeds and their stated
provenance, prompt hashes, protocol hash, script hashes. The first run records protocol_sha256_at_write; later runs
keep that value and add protocol_sha256_now so a change to the frozen protocol is visible.

  python3 scripts/write_manifest.py                    # plan-time manifest
  python3 scripts/write_manifest.py finalize           # adds output hashes and the finalize timestamp
  python3 scripts/write_manifest.py [finalize] --reset # start fresh metadata after the inputs changed

A manifest already on disk lends its creation time, finalization time and run records to the next write. When the
planned inputs have changed since it was written (the seed file, the design file or a prompt template), keeping
those would pair new prompts with the previous run's provenance, so the write is refused unless --reset is passed;
--reset records metadata_reset_utc and starts the timestamps and run records afresh (Codex review of PR #52).
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
    sha256_text,
)

INPUT_HASH_KEYS = ("seeds_json_sha256", "design_json_sha256")
TEMPLATE_KEYS = ("generation_prompt_template", "checker_prompt_template")


def seed_provenance() -> dict:
    """The provenance the seed file itself states: the distinct `provenance` values across its seeds (a seed without
    one is reported as MISSING, never assumed) and the file's own note."""
    data = json.loads((PILOT / "seeds.json").read_text(encoding="utf-8"))
    values = sorted({s.get("provenance", "MISSING") for s in data["seeds"]})
    return {"values": values, "n_seeds_without_provenance": sum(1 for s in data["seeds"] if "provenance" not in s),
            "file_note": data.get("_note")}


def input_changes(old: dict, current: dict) -> list[str]:
    """Which planned inputs differ from the manifest on disk: the seed and design file hashes, and the prompt
    templates (compared only when both manifests know them)."""
    changes = [k for k in INPUT_HASH_KEYS if old.get(k) != current.get(k)]
    op, cp = old.get("prompt_hashes", {}), current.get("prompt_hashes", {})
    changes += [f"prompt_hashes.{k}" for k in TEMPLATE_KEYS if k in op and k in cp and op[k] != cp[k]]
    return changes


def main(finalize: bool, reset: bool = False) -> None:
    path = PILOT / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model = json.loads((PILOT / "manifest_model.json").read_text(encoding="utf-8"))
    calls = json.loads((PILOT / "calls.json").read_text(encoding="utf-8"))
    protocol_now = sha256_file(PILOT / "PROTOCOL.md")
    current = {"seeds_json_sha256": sha256_file(PILOT / "seeds.json"),
               "design_json_sha256": sha256_file(PILOT / "design.json"),
               "prompt_hashes": {"generation_prompt_template": calls["generation_prompt_template_sha256"]}}
    cb = PILOT / "checker_batches.json"
    cbdata = json.loads(cb.read_text(encoding="utf-8")) if cb.exists() else None
    if cbdata:
        current["prompt_hashes"]["checker_prompt_template"] = cbdata["checker_prompt_template_sha256"]
    # the plan itself must have been rendered from the inputs on disk: a changed seed or design file with a stale
    # calls.json would pair new input hashes with old prompts (Codex review of PR #52)
    planned = calls.get("input_hashes")
    if not isinstance(planned, dict):
        raise SystemExit("write_manifest: calls.json records no input_hashes; re-run plan_calls.py so the plan is "
                         "bound to its inputs")
    template_now = sha256_text((PILOT / "prompts" / "generation_prompt.txt").read_text(encoding="utf-8"))
    stale = [k for k in INPUT_HASH_KEYS if planned.get(k) != current[k]]
    if planned.get("generation_prompt_template_sha256") != template_now:
        stale.append("generation_prompt_template_sha256")
    if stale:
        raise SystemExit(f"write_manifest: calls.json was planned from different inputs ({', '.join(stale)} changed "
                         f"since plan_calls.py ran); re-run plan_calls.py before writing the manifest")
    changes = input_changes(old, current) if old else []
    if changes and not reset:
        raise SystemExit(f"write_manifest: {', '.join(changes)} changed since manifest.json was written (created "
                         f"{old.get('created_utc')}, runs {sorted(old.get('runs', {}))}); a rerun with new inputs must "
                         f"not keep the previous run's timestamps and run records: pass --reset to start fresh metadata")
    base = {} if (reset or not old) else old  # the metadata carried forward, none after a reset
    m = {
        "pilot": "stimulus-generation measurement-validity pilot",
        "date_utc": base.get("date_utc", now[:10]),
        "created_utc": base.get("created_utc", now),
        "finalized_utc": now if finalize else base.get("finalized_utc"),
        "metadata_reset_utc": now if (reset and old) else base.get("metadata_reset_utc"),
        "model": model,
        "python": platform.python_version(),
        "seeds": {"master_seed": MASTER_SEED, "exemplar_sampling": "random.Random(20260929), one draw of K per cell in cell order",
                  "named_streams": {p: f"random.Random('{MASTER_SEED}:{p}')" for p in ("broken", "checker_shuffle", "review", "bootstrap")}},
        "design": {"specialties": SPECIALTIES, "swap_types": SWAP_TYPES, "arms": ARMS, "rows_per_call": ROWS_PER_CALL,
                   "controls_per_call": CONTROLS_PER_CALL, "k_exemplars_requested": K_EXEMPLARS,
                   "k_exemplars_used": calls["k_exemplars_used"], "n_seed_cases": calls["n_seeds"],
                   # read from the seed file in use, never fixed here: a rerun with real seeds must record theirs
                   "seed_provenance": seed_provenance(),
                   "checker_batch": CHECKER_BATCH, "n_broken": N_BROKEN, "n_known_good_requested": N_KNOWN_GOOD,
                   "n_review": N_REVIEW, "n_boot": N_BOOT},
        "protocol_sha256_at_write": base.get("protocol_sha256_at_write", protocol_now),
        "protocol_sha256_now": protocol_now,
        "protocol_unchanged": base.get("protocol_sha256_at_write", protocol_now) == protocol_now,
        "seeds_json_sha256": current["seeds_json_sha256"],
        "design_json_sha256": current["design_json_sha256"],
        "prompt_hashes": {
            "generation_prompt_template": calls["generation_prompt_template_sha256"],
            "generation_calls": {c["id"]: {"prompt_sha256": c["prompt_sha256"], "exemplar_ids": c["exemplar_ids"]} for c in calls["calls"]},
        },
        "script_hashes": {p.name: sha256_file(p) for p in sorted((PILOT / "scripts").glob("*.py"))},
        "workflow_script_hashes": {p.name: sha256_file(p) for p in sorted((PILOT / "workflows").glob("*.js"))} if (PILOT / "workflows").exists() else {},
    }
    if cbdata:
        m["prompt_hashes"]["checker_prompt_template"] = cbdata["checker_prompt_template_sha256"]
        m["prompt_hashes"]["checker_batches"] = {x["batch_id"]: x["prompt_sha256"] for x in cbdata["batches"]}
    m["runs"] = base.get("runs", {})
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
    print(f"manifest.json written ({'finalized' if finalize else 'planned'}"
          f"{', metadata reset' if (reset and old) else ''}); protocol unchanged: {m['protocol_unchanged']}")


if __name__ == "__main__":
    main(finalize="finalize" in sys.argv[1:], reset="--reset" in sys.argv[1:])
