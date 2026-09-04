"""PAB-anchored tier-ladder sensitivity scenario (engine-side only).

Owner decision 2026-08-04 (TIER-VOCAB-SENS: engine-side-only, see
docs/decisions_20260804_pab.md): score the urgency-shift analysis under the
care ladder implicit in PatientAgentBench's clinician-validated triage rubric
anchors, as a sensitivity scenario beside the draft vocabulary — never as a
replacement, and never shipped to the site.

The transform is deliberately STRUCTURAL, not lexical: their rubric anchors
distinguish emergency / provider evaluation / monitoring / self-care and do
not attest the draft ladder's specialist(3) vs generalist(2) split, so the
scenario collapses tier 3 into tier 2 for every token. No token's medical
meaning is re-judged here, and no vocabulary text enters this file — terms
live only in the JSON data files (repo hard convention).

Known limitation, disclosed: their "monitoring" anchor has no counterpart in
the draft ladder (closest seam is 1/0); it is NOT modeled by this scenario.

Usage:
  python scripts/pab_tier_scenario.py emit
      write data/urgency_tiers.pab_anchored.json from the draft file
  python scripts/pab_tier_scenario.py run --workdir <dir>
      emit, run the collector under both vocabularies (full outputs stay in
      --workdir, never in the repo), write the comparison to
      ops/pab_tier_scenario.json
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFT = ROOT / "data" / "urgency_tiers.draft.json"
ANCHORED = ROOT / "data" / "urgency_tiers.pab_anchored.json"
OUT = ROOT / "ops" / "pab_tier_scenario.json"

COLLAPSE_FROM = "3"
COLLAPSE_TO = 2

HEADER = (
    "PAB-anchored sensitivity vocabulary, derived mechanically from "
    "urgency_tiers.draft.json by scripts/pab_tier_scenario.py: tier 3 "
    "(specialist care) collapsed into tier 2 (provider evaluation), because "
    "the PatientAgentBench triage-rubric anchors (Vatanparvar et al. 2026, "
    "CC-BY-NC-4.0 rubric; only the ladder STRUCTURE is used here, no rubric "
    "text) do not attest a specialist/generalist distinction. ENGINE-SIDE "
    "ONLY per owner decision 2026-08-04 TIER-VOCAB-SENS; not clinician-"
    "validated as a lexicon; never published to the site. The draft file's "
    "'monitoring' gap is a disclosed limitation, not modeled."
)

STATUS = "pab-anchor-informed structural scenario · unreviewed · engine-side only"


def build_anchored(draft: dict) -> dict:
    """Collapse tier 3 -> 2 across the vocabulary; everything else verbatim."""
    out = copy.deepcopy(draft)
    out["_"] = HEADER
    out["status"] = STATUS
    tiers = dict(out.get("tiers", {}))
    if COLLAPSE_FROM in tiers:
        merged = f"{tiers.get(str(COLLAPSE_TO), '')} (incl. former tier {COLLAPSE_FROM})"
        tiers[str(COLLAPSE_TO)] = merged
        del tiers[COLLAPSE_FROM]
    out["tiers"] = tiers
    n = 0
    for tok in out.get("tokens", {}).values():
        if tok.get("tier") == int(COLLAPSE_FROM):
            tok["tier"] = COLLAPSE_TO
            tok["scenario_note"] = "collapsed 3->2 by pab_tier_scenario"
            n += 1
    out["scenario_meta"] = {
        "derived_from": "data/urgency_tiers.draft.json",
        "transform": f"tier {COLLAPSE_FROM} -> {COLLAPSE_TO}, structural",
        "tokens_moved": n,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return out


def emit() -> dict:
    draft = json.loads(DRAFT.read_text())
    anchored = build_anchored(draft)
    ANCHORED.write_text(json.dumps(anchored, indent=2, ensure_ascii=False) + "\n")
    return anchored


def _collector(tiers: Path, out: Path, frontend: str) -> dict:
    cmd = [
        sys.executable, str(ROOT / "scripts" / "urgency_shift.py"),
        "--tiers", str(tiers), "--out", str(out), "--frontend", frontend,
    ]
    subprocess.run(cmd, check=True, cwd=ROOT)
    return json.loads(out.read_text())["summary"]


def _model_rows(summary: dict, block: str) -> dict:
    rows = {}
    for model, v in summary.get(block, {}).items():
        rows[model] = {"downgrades": v.get("downgrades"), "upgrades": v.get("upgrades"),
                       "mean_tier_shift": v.get("mean_tier_shift")}
    return rows


def compare(base: dict, scen: dict) -> dict:
    """Side-by-side of the classification tallies the site narrative rests on.

    per_model_deduped (one flip per phrase) is the claim-grade view; the raw
    per_model tallies pseudoreplicate and are kept for reference only.
    """
    def totals(s):
        return {"flip_classes": s.get("flip_classes"),
                "mean_tier_shift": s.get("mean_tier_shift"),
                "flips": s.get("flips")}

    def rows(block):
        b, s = _model_rows(base, block), _model_rows(scen, block)
        return {m: {"baseline": b.get(m), "pab_anchored": s.get(m)}
                for m in sorted(set(b) | set(s))}

    return {
        "totals": {"baseline": totals(base), "pab_anchored": totals(scen)},
        "per_model_deduped": rows("per_model_deduped"),
        "per_model_raw": rows("per_model"),
        "headline_downgrader": {
            "baseline": base.get("headline_downgrader"),
            "pab_anchored": scen.get("headline_downgrader"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["emit", "run"])
    ap.add_argument("--workdir", default=None,
                    help="directory for the full collector outputs (required for run; "
                         "keep it OUTSIDE the repo — full row files are not committed)")
    ap.add_argument("--frontend", default="../patientwords")
    args = ap.parse_args(argv)

    emit()
    if args.mode == "emit":
        print(f"wrote {ANCHORED.relative_to(ROOT)}")
        return 0

    if not args.workdir:
        ap.error("run mode requires --workdir")
    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    base = _collector(DRAFT, wd / "urgency_shift.baseline.json", args.frontend)
    scen = _collector(ANCHORED, wd / "urgency_shift.pab_anchored.json", args.frontend)

    report = {
        "_": ("Sensitivity comparison: urgency-shift classifications under the draft "
              "ladder vs the PAB-anchored structural collapse (3->2). Engine-side "
              "only, owner decision 2026-08-04 TIER-VOCAB-SENS. Full row files stay "
              "in the run's --workdir, uncommitted."),
        "vocabulary_baseline": str(DRAFT.relative_to(ROOT)),
        "vocabulary_scenario": str(ANCHORED.relative_to(ROOT)),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "comparison": compare(base, scen),
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
