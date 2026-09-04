"""Build negative-control pairs from a measured batch ($0, offline, no model).

The study's headline number is a *difference* between two phrasings. Nothing so
far establishes what that difference reads when there is nothing to read. The
translation and steering paths have placebo arms; the core clinical-vs-patient
contrast does not. This builds one, from the same prompts already measured, so
the control is matched to the treatment rather than a new stimulus set.

Two arms, written as ordinary pairs files the logits lane can measure unchanged:

* ``identity`` — the clinical prompt against itself. The penalty must come back
  **exactly 0.0**. It measures nothing about language; it is an instrument
  check, and a non-zero result means the measurement path carries state between
  the two forward passes, or the join key is wrong. Cheap, and it fails loudly.

* ``qualified`` — the clinical prompt against a **longer clinical** phrasing of
  itself. This is the real control. A clinical-register qualifier from
  ``data/control_qualifiers.draft.json`` is inserted immediately before the
  prompt's ``, so `` clause, which adds words in the same region where the
  clinical/patient difference lives and leaves the continuation and the target
  position untouched.

**Why length matters here.** On ``pairs_20260710T011743Z`` the patient span is
longer than the clinical span in **49 of 50 pairs**, by 4.02 words on average.
The headline effect is therefore confounded with prompt length, and a control
that held length constant would be an easier test than the treatment and would
read ~0 for the wrong reason. The qualifiers are sized (mean 4.2 words) to
reproduce that difference while holding register constant.

**How to read the result.** If ``qualified`` reads ~0, length and surface
verbosity are not driving the penalty, and the effect is attributable to
register. If it reads an appreciable fraction of the study's mean penalty, that
fraction is not register and the headline needs to be reported net of it.

**The limitation, stated rather than buried.** The real pairs *substitute* one
span for another; this control *inserts* a clause. Same register, comparable
length, different edit operation. A stronger control substitutes an LLM-authored
clinical paraphrase of equal length — that is the paid `medlang-generate` path
and is the version to run if this one shows anything.

No medical vocabulary lives in this file: prompts come from the measured batch,
qualifier clauses from the data file.

Usage:
  python scripts/build_control_pairs.py --pairs data/simulated/pairs_<STAMP>.json \
      --arm qualified --out data/simulated/control_qualified_<STAMP>.json
"""

import argparse
import json
from pathlib import Path

SO = ", so "
DEFAULT_QUALIFIERS = "data/control_qualifiers.draft.json"


def load_qualifiers(path: str) -> list[str]:
    """Qualifier clause texts, in file order (the assignment is round-robin)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    texts = [q["text"] for q in doc["qualifiers"]]
    if not texts:
        raise SystemExit(f"{path} lists no qualifiers")
    return texts


def qualify(prompt: str, qualifier: str) -> str:
    """Insert `qualifier` before the prompt's final ', so ' clause.

    Splits on the LAST occurrence so a setup clause containing its own ', so '
    cannot move the insertion point away from the continuation.
    """
    if SO not in prompt:
        raise ValueError(f"no {SO!r} clause to insert before: {prompt!r}")
    head, _, tail = prompt.rpartition(SO)
    return f"{head}, {qualifier}{SO}{tail}"


def build_pair(pair: dict, arm: str, qualifier: str | None) -> dict:
    """One control pair, in the same schema the logits lane reads.

    `top_prompt` stays the untouched clinical prompt so the control's clinical
    side is literally the measured one; only `bottom_prompt` changes.
    """
    clinical = pair["top_prompt"]
    if arm == "identity":
        bottom = clinical
    elif arm == "qualified":
        bottom = qualify(clinical, qualifier)
    else:
        raise SystemExit(f"unknown arm {arm!r}")
    gen = dict(pair.get("generation") or {})
    return {
        "top_prompt": clinical,
        "bottom_prompt": bottom,
        "target_clinical_token": pair.get("target_clinical_token"),
        "generation": {
            **gen,
            "control_arm": arm,
            "control_qualifier": qualifier,
            # Both sides are clinical here; the patient_term field would be a
            # lie, and downstream readers key off it.
            "patient_term": None,
            "source_top_prompt": clinical,
            "source_bottom_prompt": pair.get("bottom_prompt"),
            "word_delta": len(bottom.split()) - len(clinical.split()),
        },
    }


def build(pairs: list[dict], arm: str, qualifiers: list[str]) -> tuple[list[dict], list[dict]]:
    """(control pairs, skipped records). Skips are recorded, never dropped."""
    out, skipped = [], []
    for offset, pair in enumerate(pairs):
        index = offset + 1
        if not pair.get("top_prompt"):
            skipped.append({"index": index, "reason": "no top_prompt"})
            continue
        qualifier = qualifiers[offset % len(qualifiers)] if arm == "qualified" else None
        try:
            built = build_pair(pair, arm, qualifier)
        except ValueError as exc:
            skipped.append({"index": index, "reason": str(exc)})
            continue
        built["generation"]["source_index"] = index
        out.append(built)
    return out, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pairs", required=True, help="measured batch to derive the control from")
    ap.add_argument("--arm", required=True, choices=("identity", "qualified"))
    ap.add_argument("--out", required=True, help="control pairs file to write")
    ap.add_argument("--qualifiers", default=DEFAULT_QUALIFIERS)
    args = ap.parse_args()

    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    qualifiers = load_qualifiers(args.qualifiers)
    built, skipped = build(pairs, args.arm, qualifiers)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built, indent=1) + "\n", encoding="utf-8")

    deltas = [p["generation"]["word_delta"] for p in built]
    mean = sum(deltas) / len(deltas) if deltas else 0.0
    print(f"wrote {out} — {len(built)} pairs, arm={args.arm}")
    print(f"  word delta: mean {mean:+.2f}, range {min(deltas, default=0)}..{max(deltas, default=0)}")
    if skipped:
        # Recorded rather than silently dropped: a control with missing rows is
        # a different control.
        print(f"  SKIPPED {len(skipped)}: {skipped}")


if __name__ == "__main__":
    main()
