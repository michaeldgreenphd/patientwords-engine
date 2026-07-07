"""Merge engine trace outputs into the frontend's Simulated Scenarios section.

Reads (engine repo), for each batch stamp:
  data/simulated/pairs_<STAMP>.json + .report.json     - batch + cost sidecar
  trace_out/pairs_<STAMP>/batch_summary.part_*.json    - per-chunk trace summaries
  trace_out/pairs_<STAMP>/index_NN*.html/png           - renders + circuit diffs

Writes (frontend repo working tree; review before committing):
  modes/simulated/pairs_<STAMP>/index_NN*.html/png
  modes/simulated/preview.html                          - first measured render (stable path)
  data/simulated_scenarios.json

Usage:
  python scripts/export_frontend_simulated.py --frontend ../patientwords \\
      --stamps 20260706T201750Z[,<later-stamp>...] [--engine .]

Multiple stamps present one evaluation series (a batch plus its feedback
top-ups): scenarios get one global display numbering, and each carries its
batch stem + in-batch index for provenance.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--engine", default=".", help="engine repo root (default: cwd)")
parser.add_argument("--frontend", required=True, help="frontend repo root")
parser.add_argument("--stamps", required=True,
                    help="comma-separated batch UTC stamps in display order")
parser.add_argument("--no-pngs", action="store_true",
                    help="skip PNG copies (recommended for large series - the interactive "
                         "HTML renders are the essential artifact and GitHub Pages repos "
                         "should stay light)")
parser.add_argument("--max-renders", type=int, default=25,
                    help="cap interactive renders copied to the public site to the N most "
                         "consequential scenarios (flips first, then largest language penalty); "
                         "every scenario still gets its lightweight numbers. 0 = no cap. The "
                         "full render set lives in the engine repo / a run archive.")
args = parser.parse_args()

ENGINE = Path(args.engine)
FRONTEND = Path(args.frontend)


def tok(label):
    """Logit labels arrive as 'Output \" nap\"' - return the bare token."""
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


def top(spread_side):
    entry = (spread_side or [None])[0]
    if not entry:
        return None
    return [tok(entry[0]), entry[1]]


def clean_spread(spread_side):
    return [[tok(label), prob] for label, prob in (spread_side or []) if tok(label)]


batches = []
scenarios = []
traced_meta = {}
display_index = 0
first_preview = None

for stamp in [s.strip() for s in args.stamps.split(",") if s.strip()]:
    stem = f"pairs_{stamp}"
    batch_path = ENGINE / f"data/simulated/{stem}.json"
    report_path = ENGINE / f"data/simulated/{stem}.report.json"
    trace_dir = ENGINE / f"trace_out/{stem}"
    if not trace_dir.is_dir():
        trace_dir = ENGINE / "trace_out"  # legacy flat layout

    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    results = {}
    screen_targets = None
    for part in sorted(trace_dir.glob("batch_summary.part_*.json")):
        summary = json.loads(part.read_text(encoding="utf-8"))
        for key in ("graph_model", "source_set", "mode", "backend"):
            if summary.get(key):
                traced_meta[key] = summary[key]
        if summary.get("screen_targets") is not None:
            screen_targets = summary["screen_targets"]
        for r in summary.get("results", []):
            results[r["index"]] = r
    if not results:
        sys.exit(f"no batch_summary.part_*.json under {trace_dir} - pull the engine branch first")

    for index in sorted(results):
        r = results[index]
        display_index += 1
        pair = batch[index - 1]
        gen = pair.get("generation", {})
        spread = r.get("predictive_spread", {})
        top_c, top_p = top(spread.get("clinical")), top(spread.get("patient"))
        probs = r.get("probabilities", {})
        measured = tok(r.get("target_token"))
        intended = (pair.get("target_clinical_token") or "").strip()

        entry = {
            "index": display_index,
            "batch": stem,
            "batch_index": index,
            "clinical_prompt": r["prompts"]["clinical"],
            "patient_prompt": r["prompts"]["patient"],
            "target_token": measured,
            "intended_target": intended,
            # A measured token that is a leading wordpiece of the intended
            # target (' ant' for ' antacid') is normal tokenization; anything
            # else means the measurement anchored on the clinical top logit.
            "anchor_fallback": bool(
                measured and intended and not intended.lower().startswith(measured.lower())
            ),
            "prob_clinical": probs.get("clinical"),
            "prob_patient": probs.get("patient"),
            "language_penalty": r.get("language_penalty"),
            "top_clinical": top_c,
            "top_patient": top_p,
            "spread_clinical": clean_spread(spread.get("clinical")),
            "spread_patient": clean_spread(spread.get("patient")),
            "flipped": bool(top_c and top_p and top_c[0] != top_p[0]),
            "rationale": gen.get("rationale"),
            "patient_term": gen.get("patient_term"),
            "clinical_term": gen.get("clinical_term"),
            "topic": gen.get("topic"),
            "topics": gen.get("topics", []),
            "screening": r.get("screening"),
            "circuit_diff": r.get("circuit_diff"),
            "clinical_mass": r.get("clinical_mass"),
        }
        entry["_render"] = {"trace_dir": str(trace_dir), "stem": stem, "index": index}
        scenarios.append(entry)

    batches.append({
        "batch": stem,
        "generated": {
            "model": report.get("model"),
            "run_timestamp": report.get("run_timestamp"),
            "cost_usd": report.get("cost_usd"),
            "max_spend_usd": report.get("max_spend_usd"),
            "accepted": report.get("accepted"),
            "rejected": report.get("rejected"),
            "rejection_reasons": report.get("rejection_reasons", []),
            "topics": report.get("topics", []),
            "sidecar": f"data/simulated/{stem}.report.json",
        },
        "screen_targets": screen_targets,
    })

# Public site keeps interactive renders only for the most consequential
# scenarios (flips first, then largest |language penalty|); every scenario
# still carries its numbers. The full render set is archived separately.
def _consequence(e):
    lp = e.get("language_penalty")
    mag = abs(lp) if isinstance(lp, (int, float)) else 0.0
    return (1 if e.get("flipped") else 0) * 10 + mag

ranked = sorted(scenarios, key=_consequence, reverse=True)
demo = ranked if args.max_renders <= 0 else ranked[:args.max_renders]
copied = 0
for e in demo:
    meta = e.get("_render")
    if not meta:
        continue
    src_dir = Path(meta["trace_dir"]); stem = meta["stem"]; index = meta["index"]
    out_modes = FRONTEND / "modes/simulated" / stem
    # full comparison only on the public site (the circuit-diff view is
    # showcased on the syntax edge-views); keeps the demo set light
    for suffix, key in ((("", "html")), ("", "png")):
        ext = "html" if key.endswith("html") else "png"
        if args.no_pngs and ext == "png":
            continue
        src = src_dir / f"index_{index:02d}{suffix}.{ext}"
        if src.is_file():
            out_modes.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out_modes / src.name)
            e[key] = f"modes/simulated/{stem}/{src.name}"
            if key == "html" and first_preview is None:
                first_preview = out_modes / src.name
    copied += 1
for e in scenarios:
    e.pop("_render", None)  # drop the private marker from every entry

if first_preview is not None:
    shutil.copy2(first_preview, FRONTEND / "modes/simulated/preview.html")
    # one raster survives --no-pngs: the og:image for link unfurls
    for stamp in [s.strip() for s in args.stamps.split(",") if s.strip()]:
        candidate = ENGINE / f"trace_out/pairs_{stamp}" / first_preview.name.replace(".html", ".png")
        if candidate.is_file():
            shutil.copy2(candidate, FRONTEND / "modes/simulated/preview.png")
            break

payload = {
    "batches": batches,
    "traced": traced_meta,
    "scenarios": scenarios,
}
out_data = FRONTEND / "data/simulated_scenarios.json"
out_data.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
measured_n = sum(1 for s in scenarios
                 if not (s.get("screening") or {}).get("status") == "screened_out")
data_only = len(scenarios) - copied
print(f"{len(scenarios)} scenarios ({measured_n} measured) across {len(batches)} batch(es) -> {out_data}")
print(f"  {copied} interactive renders published (cap {args.max_renders or 'none'}); "
      f"{data_only} scenarios are data-only on the public site")
