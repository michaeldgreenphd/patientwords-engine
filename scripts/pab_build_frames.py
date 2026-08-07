"""Frame construction: PAB harvested utterance pairs into 2panel batch entries.

Implements docs/pab_frame_spec_20260805.md (methodology pre-committed 2026-08-05)
under the owner authorization of 2026-08-07 (docs/decisions_20260804_pab.md
addendum 2, PAB-LANE-PUSH: frame-building + gemma traces + j-lens on the study
branch's $0 lanes). Reads a `scripts/pab_harvest_utterances.py` output file,
extracts one clinical-description span per literacy arm, embeds both spans of a
pair in the SAME carrier frame from `data/pab_frames.json` (pure syntax - the
spans carry all medical content), and writes a `pabharvest_<stamp>.json` batch
in the 2panel input shape of `medlang_circuits/batch_eval.py`.

Span extraction (spec rule 1, mechanical): from each arm's FIRST substantive
utterance, take the contiguous clinical-description clause - drop leading
greeting tokens (hi/hello/hey/greetings/thanks/thank you; matched
case-insensitively), take the first sentence, strip a trailing request clause
starting with 'can you'/'could you'/'please'. Original casing is preserved
("substantive" is operational: the first utterance whose span survives the
strip non-empty). A pair is BUILT only when both arms yield a span; every
exclusion is counted in the build-metadata sidecar, never silent.

Schema finding (read from medlang_circuits/batch_eval.py `evaluate_pair` and
medlang_circuits/targets.py, 2026-08-07): under ``--screen-targets``,
``target_clinical_token`` IS REQUIRED. The screening measurement is
``target_probability(clinical_graph, anchor=anchor) if anchor else None`` -
``force_target_tokens`` is never consulted by screening, and with no anchor
``observed`` stays None through both the initial measure and the single
probe-extension re-measure, so every anchor-less pair is unconditionally
recorded as ``screening.screened_out`` ("intended target not in the traced
clinical spread") and its patient side is never traced. The anchor -> forced
targets -> top-logit fallback (``_resolve_reference``) exists only on the
UNSCREENED path. Design consequence here: entries carry
``target_clinical_token`` only when ``--anchors`` supplies a per-frame token
inventory as data (medical vocabulary never enters Python source, and the
frames file is pure carrier syntax by rule; one token per carrier frame's
continuation class is not a hand-picked per-pair target - it is validated
empirically by the 0.02 screen exactly as Tier B generator-proposed targets
are). Without ``--anchors`` the batch is built target-less, the sidecar
records ``screening_ready: false``, and the batch must be traced WITHOUT
``--screen-targets`` (reference falls back to the clinical top logit) or
rebuilt with anchors - firing it screened would screen out 100% of pairs.

Output identity (spec rule 4): the batch stem MUST start with ``pabharvest_``
- outside the ``pairs_`` observational regex by construction, exploratory
only. The batch file is a bare JSON array (the shape `run_batch` requires);
build metadata rides in a ``<stem>.build.json`` sidecar per the repo's sidecar
convention. License boundary: harvested text is CC-BY-NC-4.0-derived, so the
output stays in ``data/pab/`` (never ``data/simulated/``, never the site)
until an owner decision; any onward artifact passes ``scripts/seal_check.py``.

Usage:
  python scripts/pab_build_frames.py --harvest data/pab/harvest_<stamp>.json
      [--frames data/pab_frames.json] [--anchors <frame-anchor data file>]
      [--out data/pab/pabharvest_<utcstamp>.json]
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROVENANCE = "pabharvest"

# Leading greeting tokens (spec: greetings/logistics are excluded mechanically).
_GREETING_RE = re.compile(r"^(?:(?:hi|hello|hey|greetings|thanks|thank\s+you)\b[\s,.!-]*)+", re.IGNORECASE)

# First-sentence boundary: terminal punctuation followed by whitespace/end, so
# in-number periods do not cut the clause.
_SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")

# Trailing tool-directed request clause (spec: tool-directed requests excluded).
_REQUEST_TAIL_RE = re.compile(r"[\s,;:\-]*\b(?:can\s+you|could\s+you|please)\b.*$", re.IGNORECASE | re.DOTALL)


def extract_span(utterance: str) -> str:
    """Contiguous clinical-description clause of one utterance; '' when none.

    Mechanical, in this order: strip leading greeting tokens; take the first
    sentence; strip the trailing request clause; trim separators. Casing of
    the surviving span is preserved untouched.
    """
    text = str(utterance or "").strip()
    text = _GREETING_RE.sub("", text)
    match = _SENTENCE_END_RE.search(text)
    if match:
        text = text[: match.start()]
    text = _REQUEST_TAIL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip().strip(",;:-").strip()
    return text


def arm_span(records: list[dict]) -> tuple[str, dict] | None:
    """Span + source stamp from an arm's first substantive utterance.

    Records are scanned in deterministic (run, experiment) order; the first
    utterance whose extracted span is non-empty wins. None when no utterance
    in the arm yields a span.
    """
    ordered = sorted(records or [], key=lambda r: (str(r.get("run", "")), str(r.get("experiment", ""))))
    for rec in ordered:
        for utt in rec.get("utterances") or []:
            span = extract_span(utt)
            if span:
                return span, {"run": rec.get("run"), "experiment": rec.get("experiment")}
    return None


def load_frames(frames_data: dict) -> list[dict]:
    """Validated frame inventory, sorted by id (the output-order contract)."""
    frames = frames_data.get("frames") or []
    if not frames:
        raise ValueError("frames file carries no frames")
    ids = [f.get("id") for f in frames]
    if len(set(ids)) != len(ids) or not all(ids):
        raise ValueError(f"frame ids must be present and unique; got {ids}")
    for frame in frames:
        if "{span}" not in str(frame.get("template", "")):
            raise ValueError(f"frame {frame.get('id')!r} template lacks the {{span}} placeholder")
    return sorted(frames, key=lambda f: f["id"])


def apply_frame(template: str, span: str) -> str:
    return template.replace("{span}", span)


def build(harvest: dict, frames_data: dict, anchors: dict | None = None) -> tuple[list[dict], dict]:
    """(batch entries, build metadata) from a harvest dict + frame inventory.

    Deterministic: groups sorted by pair_key, frames by frame id; one entry
    per (built pair x frame), same frame for both arms, top = HIGH-literacy
    span (clinical side), bottom = LOW-literacy span (patient side).
    """
    frames = load_frames(frames_data)
    if anchors is not None:
        anchor_map = {k: v for k, v in anchors.items() if not str(k).startswith("_")}
        missing = [f["id"] for f in frames if f["id"] not in anchor_map]
        if missing:
            raise ValueError(f"anchors file lacks target tokens for frames {missing}")
    else:
        anchor_map = None

    exclusions = {"missing_arm": 0, "no_span_low": 0, "no_span_high": 0, "no_span_both": 0}
    excluded_pairs: list[dict] = []
    entries: list[dict] = []
    pairs_built = 0

    for group in sorted(harvest.get("groups") or [], key=lambda g: g.get("pair_key", "")):
        key = group.get("pair_key", "")
        arms = group.get("arms") or {}
        if not {"low", "high"} <= set(arms):
            exclusions["missing_arm"] += 1
            excluded_pairs.append({"pair_key": key, "reason": "missing_arm"})
            continue
        low = arm_span(arms["low"])
        high = arm_span(arms["high"])
        if low is None or high is None:
            reason = "no_span_both" if low is None and high is None else (
                "no_span_low" if low is None else "no_span_high")
            exclusions[reason] += 1
            excluded_pairs.append({"pair_key": key, "reason": reason})
            continue
        (low_span, low_src), (high_span, high_src) = low, high
        pairs_built += 1
        for frame in frames:
            entry = {
                "top_prompt": apply_frame(frame["template"], high_span),
                "bottom_prompt": apply_frame(frame["template"], low_span),
                "pair_key": key,
                "frame_id": frame["id"],
                "provenance": PROVENANCE,
                "generation": {
                    "provenance": PROVENANCE,
                    "pair_key": key,
                    "frame_id": frame["id"],
                    "frame_class": frame.get("elicits"),
                    "spans": {"low": low_span, "high": high_span},
                    "source": {"low": low_src, "high": high_src},
                },
            }
            if anchor_map is not None:
                entry["target_clinical_token"] = anchor_map[frame["id"]]
            entries.append(entry)

    metadata = {
        "_": ("Build metadata for a pabharvest_* 2panel batch (docs/pab_frame_spec_20260805.md; "
              "owner authorization 2026-08-07, docs/decisions_20260804_pab.md addendum 2). "
              "ENGINE-SIDE ONLY: entries embed CC-BY-NC-4.0-derived harvested utterance text - "
              "the batch stays in data/pab/, never data/simulated/, never the site; any onward "
              "artifact passes scripts/seal_check.py first. Exploratory by construction "
              "(pabharvest_ stem is outside the pairs_ observational regex)."),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harvest_generated_utc": harvest.get("generated_utc"),
        "frame_ids": [f["id"] for f in frames],
        "counts": {
            "groups_seen": len(harvest.get("groups") or []),
            "pairs_built": pairs_built,
            "frames_used": len(frames),
            "entries": len(entries),
        },
        "exclusions": exclusions,
        "excluded_pairs": excluded_pairs,
        "same_need_note": (
            "Arms are joined by the harvest's hashed scenario key, so the case is held fixed by "
            "construction (spec rule 1); no mechanical same-need test exists, and the "
            "different-needs exclusion class remains available to human review."),
        "screening": {
            "target_clinical_token_present": anchor_map is not None,
            "screening_ready": anchor_map is not None,
            "note": (
                "target_clinical_token is REQUIRED under --screen-targets (see script docstring); "
                "anchors supplied per frame from a data file." if anchor_map is not None else
                "target_clinical_token is REQUIRED under --screen-targets (see script docstring); "
                "built WITHOUT anchors - trace unscreened (top-logit reference) or rebuild with --anchors."),
        },
    }
    return entries, metadata


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harvest", required=True, help="pab_harvest_utterances.py output file")
    ap.add_argument("--frames", default=str(ROOT / "data" / "pab_frames.json"))
    ap.add_argument("--anchors", default=None,
                    help="optional data file mapping frame_id -> target token (enables --screen-targets fires)")
    ap.add_argument("--out", default=None,
                    help="batch path; stem must start with 'pabharvest_' (default data/pab/pabharvest_<utcstamp>.json)")
    args = ap.parse_args(argv)

    harvest = json.loads(Path(args.harvest).read_text(encoding="utf-8"))
    frames_data = json.loads(Path(args.frames).read_text(encoding="utf-8"))
    anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8")) if args.anchors else None

    out = Path(args.out) if args.out else (
        ROOT / "data" / "pab" /
        f"pabharvest_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json")
    if not out.name.startswith("pabharvest_"):
        raise SystemExit(f"batch stem must start with 'pabharvest_' (spec rule 4); got {out.name!r}")

    entries, metadata = build(harvest, frames_data, anchors)
    metadata["harvest"] = Path(args.harvest).name
    metadata["frames_file"] = Path(args.frames).name
    metadata["anchors_file"] = Path(args.anchors).name if args.anchors else None

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sidecar = out.with_name(out.stem + ".build.json")
    sidecar.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = metadata["counts"]
    print(f"wrote {out} · {counts['entries']} entries "
          f"({counts['pairs_built']} pairs x {counts['frames_used']} frames) · "
          f"exclusions {metadata['exclusions']} · sidecar {sidecar.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
