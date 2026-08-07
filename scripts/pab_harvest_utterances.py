"""D6 harvest: paired patient utterances from PatientAgentBench transcripts.

Owner decision 2026-08-04 HARVEST-TRACE: harvest-existing, engine-side only
(docs/decisions_20260804_pab.md). Extracts the simulated patient's own turns
(`human`-typed messages) from run directories, paired across literacy arms by
the transcript contract's pair key (the scenario text — hashed in the output,
never quoted), so identical clinical situations yield matched low/high-literacy
phrasings of the same needs.

Layer 2 discipline: reads run dirs as data, imports nothing of theirs. The
harvested utterance text is derived from CC-BY-NC-4.0 runner output — the
output file stays in this repo (`data/pab/`), never ships to the site, and any
onward artifact passes `scripts/seal_check.py` first.

Probe-frame conversion is deliberately NOT here: turning an utterance into a
next-token frame (cut point, target token, screening) is instrument design —
`docs/patientagentbench_integration_design.md` Tier 2 requires it stated as
ours, and it gets its own reviewed step. This script's job ends at clean,
paired, provenance-stamped utterances.

Usage:
  python scripts/pab_harvest_utterances.py --run <run-dir> [--run <run-dir> ...]
      [--contract data/pab_transcript_contract.json] [--out data/pab/harvest_<stamp>.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ARM_RE = re.compile(r"health_literacy=(\w+)")


def literacy_arm(personality: str) -> str | None:
    """Arm label from the free-trait personality spec; None when absent.

    Grammar duplicated from the contract's arm rules on purpose (license
    boundary): `pw:` specs carry trait=level pairs separated by `;`.
    """
    if not isinstance(personality, str) or not personality.startswith("pw:"):
        return None
    m = _ARM_RE.search(personality)
    return m.group(1) if m else None


def pair_key(entry: dict, fields) -> str:
    """Hash of the contract-declared pairing fields — joins arms of one case
    without any case text reaching the output."""
    basis = "\x1f".join(str(entry.get(f, "")) for f in fields)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def patient_utterances(entry: dict) -> list[str]:
    out = []
    for msg in entry.get("conversation") or []:
        if msg.get("type") == "human":
            text = str(msg.get("content") or "").strip()
            if text:
                out.append(text)
    return out


def harvest(run_dirs, contract) -> dict:
    fields = contract.get("pair_key_fields") or ["scenario"]
    groups: dict[str, dict] = {}
    skipped = {"no_arm": 0, "no_utterances": 0, "not_a_dict": 0}
    for rd in run_dirs:
        rd = Path(rd)
        for exp in sorted(p for p in rd.iterdir() if p.is_dir()):
            conv_path = exp / "conversations.json"
            if not conv_path.exists():
                continue
            for entry in json.loads(conv_path.read_text(encoding="utf-8")):
                if not isinstance(entry, dict):
                    # Real runs carry null placeholders for conversations the
                    # runner aborted (observed live, run 31140382136).
                    skipped["not_a_dict"] += 1
                    continue
                arm = literacy_arm(entry.get("personality", ""))
                if arm is None:
                    skipped["no_arm"] += 1
                    continue
                utts = patient_utterances(entry)
                if not utts:
                    skipped["no_utterances"] += 1
                    continue
                key = pair_key(entry, fields)
                slot = groups.setdefault(key, {"pair_key": key, "arms": {}})
                slot["arms"].setdefault(arm, []).append({
                    "run": rd.name, "experiment": exp.name,
                    "num_turns": entry.get("num_turns"),
                    "utterances": utts,
                })
    complete = [g for g in groups.values() if {"low", "high"} <= set(g["arms"])]
    return {
        "_": ("Paired patient utterances harvested from PAB transcripts "
              "(owner decision 2026-08-04 HARVEST-TRACE: harvest-existing). "
              "ENGINE-SIDE ONLY: utterance text derives from CC-BY-NC-4.0 "
              "runner output and never ships to the site; scenario text "
              "appears only as a hash. Probe-frame conversion is a separate, "
              "reviewed step - see the script docstring."),
        "_license": {
            "derived_from": "PatientAgentBench (Amazon Science), CC-BY-NC-4.0",
            "nature": ("LLM patient-simulator utterances conditioned on benchmark "
                       "cases; derived work, not verbatim case text"),
            "terms": "CC-BY-NC-4.0 applies to this file's utterance content",
            "use": "non-commercial research (mechanistic-interpretability study)",
            "committed_under": ("owner authorization, docs/decisions_20260804_pab.md "
                                "HARVEST-TRACE + Addendum 2 (2026-08-07)"),
        },
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pair_key_fields": list(fields),
        "runs": [str(r) for r in run_dirs],
        "n_groups": len(groups),
        "n_complete_pairs": len(complete),
        "skipped": skipped,
        "groups": sorted(groups.values(), key=lambda g: g["pair_key"]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--contract",
                    default=str(ROOT / "data" / "pab_transcript_contract.json"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    result = harvest(args.run, contract)
    out = Path(args.out) if args.out else (
        ROOT / "data" / "pab" /
        f"harvest_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out} · {result['n_complete_pairs']} complete pairs "
          f"of {result['n_groups']} groups · skipped {result['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
