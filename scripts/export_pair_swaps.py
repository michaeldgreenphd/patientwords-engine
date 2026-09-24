"""Per-pair patient swap + baseline sentence for the census table: data/jlens_swaps.json.

The depth-census table on the technical page (#ad-pairs) lists each pair's
clinical target. This adds, per pair, the colloquial patient swap (the differing
patient-side span vs the clinical prompt) and the full verbatim baseline (patient)
sentence for the on-hover contextual frame. Keyed "<batch_stem>#<index>" so the
frontend joins the census blocks in data/jlens_depth.json; block ids are read
from that payload so the swap map stays scoped to what the census shows.

Reads the committed pair batches under data/simulated, and the trace-time
clinical prompts under trace_out for the holdout rule. No medical vocabulary
lives in this file (terms come from the data).

Tier B holdout rows are withheld (owner ruling 3, 2026-09-23). The file carries
patient-side text only, which the registered seal (clinical phrases) does not
cover, but from its first version (2026-07-19) it published holdout rows'
verbatim patient sentences: 184 of the 194 holdout rows at site 0756f2a. The rule is the one the other
exporters apply (export_frontend_simulated.py, export_archive.py): withhold a
pair when its accepted clinical prompt is a registered holdout phrase anywhere
(Amendment 3, phrase-keyed, so alias and re-run stems are covered), or when it
is a Tier B pair whose accepted prompt, or any trace-time clinical prompt,
hashes holdout (Amendment 1; the trace-time reading is the conservative union
of divergence-log row 2026-07-17). The count is published as holdout_withheld.
A dashboard with no tierb.start_utc makes the rule unenforceable, so the export
refuses (exit 2) rather than publish unfiltered. So does a trace-time source it
cannot read in full (Codex review of PR #32): no --trace-out directory, a Tier B
batch with no batch_summary part in any model's trace dir, a part that does not
parse or is not {"results": [...]}, or a result row without an integer index
and a clinical prompt. An absent source is not an empty one: a trace-time prompt
that hashes holdout would go unseen and the row would publish. Tier A and alias
stems never consult the trace store.

Usage:
  python scripts/export_pair_swaps.py [--depth ../patientwords/data/jlens_depth.json] \
      [--out data/jlens_swaps.json] [--site ../patientwords] \
      [--dashboard ops/dashboard.json] [--trace-out trace_out]
"""

import argparse
import difflib
import json
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
    from scripts.tierb_split import holdout_phrases, is_holdout, is_tierb_batch, tierb_start_stamp
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance
    from tierb_split import holdout_phrases, is_holdout, is_tierb_batch, tierb_start_stamp


class TraceStoreError(RuntimeError):
    """The trace-time half of the holdout rule cannot be evaluated; the export refuses."""


class HoldoutRule:
    """The Tier B withholding rule as the publishing exporters apply it."""

    def __init__(self, simulated_dir: str, dashboard_path: str, trace_root: str | None = None) -> None:
        self.start: str | None = tierb_start_stamp(dashboard_path)
        self.sealed: set[str] = holdout_phrases(simulated_dir, dashboard_path)
        self.trace_root = Path(trace_root) if trace_root else None
        self._traced: dict[str, dict[int, set[str]]] = {}

    def traced_prompts(self, stem: str) -> dict[int, set[str]]:
        """{index: trace-time clinical prompts} over every model's trace dir of a stem.

        Raises TraceStoreError when the trace store is absent, when the stem has
        no batch_summary part in any model's dir, or when any part or result row
        cannot be read as {"results": [{"index": int, "prompts": {"clinical": str}}]}.
        Only Tier B stems reach here (withholds)."""
        if stem in self._traced:
            return self._traced[stem]
        root = self.trace_root
        if root is None or not root.is_dir():
            raise TraceStoreError(f"no trace store at {root}; the trace-time prompts of Tier B batch "
                                  f"{stem} cannot be read")
        dirs = [d for d in (root / stem, *sorted(root.glob(f"{stem}__*"))) if d.is_dir()]
        parts = [part for d in dirs for part in sorted(d.glob("batch_summary*.json"))]
        if not parts:
            raise TraceStoreError(f"Tier B batch {stem} has no batch_summary part under {root} "
                                  f"(never traced, or missing from this checkout)")
        found: dict[int, set[str]] = {}
        bad_parts: list[str] = []
        bad_rows = 0
        for part in parts:
            try:
                summary = json.loads(part.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                bad_parts.append(part.name)
                continue
            results = summary.get("results") if isinstance(summary, dict) else None
            if not isinstance(results, list):
                bad_parts.append(part.name)
                continue
            for r in results:
                prompts = r.get("prompts") if isinstance(r, dict) else None
                clinical = prompts.get("clinical") if isinstance(prompts, dict) else None
                index = r.get("index") if isinstance(r, dict) else None
                if type(index) is not int or not isinstance(clinical, str) or not clinical:
                    bad_rows += 1
                    continue
                found.setdefault(index, set()).add(clinical)
        if bad_parts or bad_rows:
            raise TraceStoreError(f"Tier B batch {stem}: {len(bad_parts)} unreadable or malformed "
                                  f"batch_summary part(s) {sorted(set(bad_parts))[:3]} and {bad_rows} "
                                  f"result row(s) without an integer index and a clinical prompt")
        self._traced[stem] = found
        return found

    def withholds(self, stem: str, index: int, pair: dict) -> bool:
        top = pair.get("top_prompt")
        if top and (top in self.sealed or top.strip() in self.sealed):
            return True
        if not is_tierb_batch(stem, self.start):
            return False
        if is_holdout(top):
            return True
        return any(is_holdout(p) for p in self.traced_prompts(stem).get(index, ()))


def patient_swap(top_prompt, bottom_prompt, width=44):
    """The patient-side differing span vs the clinical prompt (the colloquial
    swap), trimmed at a word boundary. None when the prompts do not differ."""
    a = (top_prompt or "").split()
    b = (bottom_prompt or "").split()
    span = []
    for op, _a0, _a1, b0, b1 in difflib.SequenceMatcher(a=a, b=b).get_opcodes():
        if op != "equal":
            span.extend(b[b0:b1])
    text = " ".join(span).strip(" ,;:.")
    if not text:
        return None
    if len(text) <= width:
        return text
    cut = text[:width]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut) + "…"


def build_swaps(block_stems, simulated_dir, rule: HoldoutRule | None = None,
                withheld: list[str] | None = None):
    """{ "<stem>#<index>": {target, swap, baseline} } for every pair in the
    referenced batches that exists under simulated_dir. With a rule, pairs it
    withholds are left out and their keys appended to ``withheld``."""
    out = {}
    for stem in block_stems:
        path = Path(simulated_dir) / f"{stem}.json"
        try:
            pairs = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(pairs, list):
            continue
        for index, pair in enumerate(pairs, start=1):
            if not isinstance(pair, dict):
                continue
            if rule is not None and rule.withholds(stem, index, pair):
                if withheld is not None:
                    withheld.append(f"{stem}#{index}")
                continue
            out[f"{stem}#{index}"] = {
                "target": (pair.get("target_clinical_token") or "").strip() or None,
                "swap": patient_swap(pair.get("top_prompt"), pair.get("bottom_prompt")),
                "baseline": (pair.get("bottom_prompt") or "").strip() or None,
            }
    return out


def block_stems(depth_path):
    """Block ids from a jlens_depth.json payload (the census the table renders)."""
    try:
        payload = json.loads(Path(depth_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [b.get("id") for b in payload.get("blocks", []) if b.get("id")]


def insights_datasets(insights_path):
    """Distinct datasets that appear in jlens_insights.points (the capture/hijack
    census). These extend beyond the depth-census blocks (e.g. drift_sentinel_*),
    so the hijack tooltips + outlier labels get a base sentence on EVERY track,
    not just the depth-census batches (owner 2026-07-20)."""
    try:
        payload = json.loads(Path(insights_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted({p.get("dataset") for p in payload.get("points", []) if p.get("dataset")})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--simulated-dir", default="data/simulated")
    parser.add_argument("--depth", default="../patientwords/data/jlens_depth.json",
                        help="census payload whose block ids scope the swap map")
    parser.add_argument("--insights", default="../patientwords/data/jlens_insights.json",
                        help="jlens_insights payload; its points[].dataset widen coverage "
                             "so hijack/capture tooltips cover every track ('' to skip)")
    parser.add_argument("--out", default="data/jlens_swaps.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    parser.add_argument("--dashboard", default="ops/dashboard.json",
                        help="ops dashboard carrying tierb.start_utc (the holdout rule needs it)")
    parser.add_argument("--trace-out", default="trace_out",
                        help="engine trace store; trace-time clinical prompts join the holdout rule")
    args = parser.parse_args(argv)

    # Union the depth-census blocks with every dataset the capture/hijack census
    # references, so tooltips/outlier labels get a base sentence on ALL tracks.
    stems = sorted(set(block_stems(args.depth))
                   | (set(insights_datasets(args.insights)) if args.insights else set()))
    if not stems:
        print(f"refused: no block ids in {args.depth} or datasets in {args.insights}")
        return 3
    rule = HoldoutRule(args.simulated_dir, args.dashboard, args.trace_out)
    if not rule.start or not rule.sealed:
        print(f"CONFIG ERROR: the Tier B holdout set computes empty from {args.dashboard} "
              f"(null tierb.start_utc? wrong branch?); refusing to publish unfiltered swaps")
        return 2
    if not args.trace_out or not Path(args.trace_out).is_dir():
        print(f"CONFIG ERROR: no trace store at --trace-out {args.trace_out!r}; the holdout rule "
              f"reads trace-time clinical prompts from it. Refusing to publish unfiltered swaps")
        return 2
    withheld: list[str] = []
    try:
        swaps = build_swaps(stems, args.simulated_dir, rule, withheld)
    except TraceStoreError as exc:
        print(f"refused: {exc}. Nothing was written")
        return 2
    if not swaps:
        print(f"refused: no pairs resolved under {args.simulated_dir}")
        return 3

    payload = {
        "_": ("patient swap + baseline per (batch#index) for the depth-census table; "
              "swap = differing patient-side span, baseline = verbatim patient sentence. "
              "Tier B confirmatory-holdout pairs are withheld (count in holdout_withheld)."),
        "holdout_withheld": len(withheld),
        "swaps": swaps,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload["_provenance"] = provenance("export_pair_swaps.py")
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"jlens swaps: {len(swaps)} pairs -> {out} "
          f"({len(withheld)} confirmatory-holdout pairs withheld)")
    if args.site:
        site_copy = Path(args.site) / "data" / "jlens_swaps.json"
        if site_copy.parent.is_dir():
            site_copy.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
            print(f"site copy -> {site_copy}")
        else:
            print(f"note: site dir {site_copy.parent} absent; skipped site copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
