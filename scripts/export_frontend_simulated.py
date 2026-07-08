"""Merge engine trace outputs into the frontend's Simulated Scenarios section.

Reads (engine repo), for each batch stamp and each traced model:
  data/simulated/pairs_<STAMP>.json + .report.json         - batch + cost sidecar
  trace_out/pairs_<STAMP>/batch_summary.part_*.json        - gemma base summaries
  trace_out/pairs_<STAMP>__<MODEL>/batch_summary.part_*.json - other models
  trace_out/pairs_<STAMP>[__<MODEL>]/index_NN*.html/png    - renders

The same phrases are traced across several circuit-tracer models; every model
writes to its own dir (gemma-2-2b keeps the bare stem, others get a __<model>
suffix). Each scenario carries per-model measurements under scenario.models,
with gemma-2-2b mirrored to the top level so an unchanged reader still shows
the base view.

Writes (frontend repo working tree; review before committing):
  modes/simulated/pairs_<STAMP>/index_NN*.html/png          - base (gemma) renders
  modes/simulated/pairs_<STAMP>__<MODEL>/index_NN.html      - only with --preview-models all
  modes/simulated/preview.html                              - first base render (stable path)
  data/simulated_scenarios.json

Usage:
  python scripts/export_frontend_simulated.py --frontend ../patientwords \\
      --stamps 20260706T201750Z[,<later-stamp>...] [--engine .] \\
      [--models gemma-2-2b,gemma-3-4b-it,qwen3-4b,qwen3-1.7b] [--preview-models base]

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

# The circuit-tracer models, in registry order (gemma-2-2b is the base/default).
# Only gemma-2-2b has a transcoder source set, so clinical-feature attribution
# (the "Med circuit" meter, auto-interp accents) is meaningful for it alone;
# the others trace + measure next-token behavior but render structure-only.
BASE_MODEL = "gemma-2-2b"
MODELS = ["gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b"]
LABELS = {
    "gemma-2-2b": "Gemma 2 2B",
    "gemma-3-4b-it": "Gemma 3 4B-it",
    "qwen3-4b": "Qwen3 4B",
    "qwen3-1.7b": "Qwen3 1.7B · LoRSA attn",
}
FEATURED = {"gemma-2-2b"}          # models with a real transcoder source set
QK = {"qwen3-1.7b"}                # traced with LoRSA attention replacement
# Base-model fields mirrored to the top level for backward compatibility, so a
# reader that doesn't understand scenario.models still shows the gemma view.
COMPAT = ["prob_clinical", "prob_patient", "language_penalty", "flipped",
          "top_clinical", "top_patient", "spread_clinical", "spread_patient",
          "target_token", "anchor_fallback", "screening", "circuit_diff",
          "clinical_mass"]

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--engine", default=".", help="engine repo root (default: cwd)")
parser.add_argument("--frontend", required=True, help="frontend repo root")
parser.add_argument("--stamps", required=True,
                    help="comma-separated batch UTC stamps in display order")
parser.add_argument("--models", default=",".join(MODELS),
                    help="comma-separated circuit-tracer models to merge; a model's "
                         "trace dir is used only where present (default: all four)")
parser.add_argument("--preview-models", choices=["base", "all"], default="base",
                    help="'base' publishes only gemma renders for the demo cap (the site "
                         "stays a lightweight preview); 'all' also publishes each other "
                         "model's render for the same top scenarios")
parser.add_argument("--no-pngs", action="store_true",
                    help="skip PNG copies (recommended for large series - the interactive "
                         "HTML renders are the essential artifact and GitHub Pages repos "
                         "should stay light)")
parser.add_argument("--max-renders", type=int, default=25,
                    help="cap interactive renders copied to the public site to the N most "
                         "consequential scenarios (flips first, then largest language penalty); "
                         "every scenario still gets its lightweight numbers. 0 = no cap. The "
                         "full render set lives in the engine repo / a run archive.")
parser.add_argument("--archive-url", default="",
                    help="URL of the back-end render archive (a GitHub Release on the engine "
                         "repo). Recorded in the payload so data-only scenarios can point at "
                         "the full circuit render. See scripts/archive_run.py + the "
                         "archive_renders workflow.")
args = parser.parse_args()

ENGINE = Path(args.engine)
FRONTEND = Path(args.frontend)
STAMPS = [s.strip() for s in args.stamps.split(",") if s.strip()]
WANT_MODELS = [m.strip() for m in args.models.split(",") if m.strip()]


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


def model_dir(stem, model):
    """Where a model's trace outputs live; gemma keeps the bare stem."""
    if model == BASE_MODEL:
        d = ENGINE / f"trace_out/{stem}"
        return d if d.is_dir() else ENGINE / "trace_out"  # legacy flat layout
    return ENGINE / f"trace_out/{stem}__{model}"


def read_trace_dir(trace_dir):
    """Collect per-index results + traced-model metadata from a dir's part files."""
    results = {}
    meta = {}
    screen = None
    for part in sorted(trace_dir.glob("batch_summary.part_*.json")):
        summary = json.loads(part.read_text(encoding="utf-8"))
        for key in ("graph_model", "source_set", "mode", "backend"):
            if summary.get(key):
                meta[key] = summary[key]
        if summary.get("screen_targets") is not None:
            screen = summary["screen_targets"]
        for r in summary.get("results", []):
            results[r["index"]] = r
    return results, meta, screen


def build_model_obj(r, pair, featured):
    """The measurements that vary by traced model, for one scenario."""
    spread = r.get("predictive_spread", {})
    top_c, top_p = top(spread.get("clinical")), top(spread.get("patient"))
    probs = r.get("probabilities", {})
    measured = tok(r.get("target_token"))
    intended = (pair.get("target_clinical_token") or "").strip()
    # clinical_mass is only meaningful for a model with a transcoder source set.
    # NullFetcher models report ~0.0 (no feature is tagged clinical), which would
    # read as a false "zero clinical mass" - coerce to None so the UI shows "-".
    return {
        "prob_clinical": probs.get("clinical"),
        "prob_patient": probs.get("patient"),
        "language_penalty": r.get("language_penalty"),
        # A measured token that is a leading wordpiece of the intended target
        # (' ant' for ' antacid') is normal tokenization; anything else means the
        # measurement anchored on the clinical top logit.
        "anchor_fallback": bool(
            measured and intended and not intended.lower().startswith(measured.lower())
        ),
        "top_clinical": top_c,
        "top_patient": top_p,
        "spread_clinical": clean_spread(spread.get("clinical")),
        "spread_patient": clean_spread(spread.get("patient")),
        "target_token": measured,
        "flipped": bool(top_c and top_p and top_c[0] != top_p[0]),
        "screening": r.get("screening"),
        "circuit_diff": r.get("circuit_diff"),
        "clinical_mass": r.get("clinical_mass") if featured else None,
    }


batches = []
scenarios = []
traced_by_model = {}
display_index = 0
first_preview = None

for stamp in STAMPS:
    stem = f"pairs_{stamp}"
    batch = json.loads((ENGINE / f"data/simulated/{stem}.json").read_text(encoding="utf-8"))
    report = json.loads((ENGINE / f"data/simulated/{stem}.report.json").read_text(encoding="utf-8"))

    results_by_model = {}
    screen_targets = None
    for m in WANT_MODELS:
        d = model_dir(stem, m)
        if not d.is_dir():
            continue
        res, meta, scr = read_trace_dir(d)
        if not res:
            continue
        results_by_model[m] = res
        traced_by_model.setdefault(m, meta)
        if m == BASE_MODEL and scr is not None:
            screen_targets = scr

    # Numbering follows the base (gemma) ordering so ?sim=N URLs stay stable; if a
    # stamp was never traced on gemma, fall back to the first available model.
    base_results = results_by_model.get(BASE_MODEL)
    if base_results is None and results_by_model:
        base_results = results_by_model[next(iter(results_by_model))]
    if not base_results:
        sys.exit(f"no trace dirs for stamp {stamp} - pull the engine branch first")

    for index in sorted(base_results):
        display_index += 1
        pair = batch[index - 1]
        gen = pair.get("generation", {})
        base_r = base_results[index]

        models_obj = {m: build_model_obj(res[index], pair, m in FEATURED)
                      for m, res in results_by_model.items() if index in res}
        base = models_obj.get(BASE_MODEL) or next(iter(models_obj.values()))

        entry = {
            "index": display_index,
            "batch": stem,
            "batch_index": index,
            # phrase-level, identical across models
            "clinical_prompt": base_r["prompts"]["clinical"],
            "patient_prompt": base_r["prompts"]["patient"],
            "intended_target": (pair.get("target_clinical_token") or "").strip(),
            "rationale": gen.get("rationale"),
            "patient_term": gen.get("patient_term"),
            "clinical_term": gen.get("clinical_term"),
            "topic": gen.get("topic"),
            "topics": gen.get("topics", []),
            "models": models_obj,
        }
        entry.update({k: base.get(k) for k in COMPAT})  # backward-compat top level
        entry["_render"] = {"stem": stem, "index": index,
                            "dirs": {m: str(model_dir(stem, m)) for m in models_obj}}
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
    stem, index, dirs = meta["stem"], meta["index"], meta["dirs"]

    # Base (gemma) render is the public preview.
    base_dir = Path(dirs[BASE_MODEL]) if BASE_MODEL in dirs else None
    published = False
    if base_dir and base_dir.is_dir():
        out_modes = FRONTEND / "modes/simulated" / stem
        for key in ("html", "png"):
            if args.no_pngs and key == "png":
                continue
            src = base_dir / f"index_{index:02d}.{key}"
            if src.is_file():
                out_modes.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out_modes / src.name)
                rel = f"modes/simulated/{stem}/{src.name}"
                e[key] = rel
                if BASE_MODEL in e["models"]:
                    e["models"][BASE_MODEL][key] = rel
                if key == "html":
                    published = True
                    if first_preview is None:
                        first_preview = out_modes / src.name

    # Optionally publish each other model's render for the same scenario.
    if args.preview_models == "all":
        for m in e["models"]:
            if m == BASE_MODEL or m not in dirs:
                continue
            mdir = Path(dirs[m])
            src = mdir / f"index_{index:02d}.html"
            if mdir.is_dir() and src.is_file():
                out_m = FRONTEND / "modes/simulated" / f"{stem}__{m}"
                out_m.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out_m / src.name)
                e["models"][m]["html"] = f"modes/simulated/{stem}__{m}/{src.name}"

    if published:
        copied += 1
for e in scenarios:
    e.pop("_render", None)  # drop the private marker from every entry

if first_preview is not None:
    shutil.copy2(first_preview, FRONTEND / "modes/simulated/preview.html")
    # one raster survives --no-pngs: the og:image for link unfurls
    for stamp in STAMPS:
        candidate = ENGINE / f"trace_out/pairs_{stamp}" / first_preview.name.replace(".html", ".png")
        if candidate.is_file():
            shutil.copy2(candidate, FRONTEND / "modes/simulated/preview.png")
            break

models_meta = [
    {
        "id": m,
        "label": LABELS.get(m, m),
        "graph_model": traced_by_model.get(m, {}).get("graph_model", m),
        "source_set": traced_by_model.get(m, {}).get("source_set"),
        "features": m in FEATURED,
        "attention_replacement": m in QK,
        # whether this model has an attribution graph at all. The logits backend
        # (models Neuronpedia can't render) measures next-token behavior only, so
        # the front end tells the reader there is no circuit graph rather than
        # implying one is hidden in the archive.
        "graphs": traced_by_model.get(m, {}).get("backend") != "logits",
        "available": True,
        "n_traced": sum(1 for s in scenarios if m in s.get("models", {})),
        "default": m == BASE_MODEL,
    }
    for m in MODELS
    if any(m in s.get("models", {}) for s in scenarios)
]

payload = {
    "batches": batches,
    "traced": traced_by_model.get(BASE_MODEL, {}),
    "traced_by_model": traced_by_model,
    "models_meta": models_meta,
    "scenarios": scenarios,
}
if args.archive_url:
    payload["archive"] = {"release_url": args.archive_url}
out_data = FRONTEND / "data/simulated_scenarios.json"
out_data.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
measured_n = sum(1 for s in scenarios
                 if not (s.get("screening") or {}).get("status") == "screened_out")
data_only = len(scenarios) - copied
model_line = ", ".join(f"{mm['id']} ({mm['n_traced']})" for mm in models_meta) or "none"
print(f"{len(scenarios)} scenarios ({measured_n} measured) across {len(batches)} batch(es) -> {out_data}")
print(f"  models: {model_line}")
print(f"  {copied} interactive renders published (cap {args.max_renders or 'none'}); "
      f"{data_only} scenarios are data-only on the public site")

# Over ~100 scenarios the full render set is heavy enough that it belongs in a
# back-end archive, not the site repo. Nudge the operator with a ready-to-fire
# trigger for the archive_renders workflow (see docs/archiving.md).
if len(scenarios) > 100 and not args.archive_url:
    run_dirs = []
    for s in STAMPS:
        stem_s = f"pairs_{s}"
        run_dirs.append(f"trace_out/{stem_s}")
        for m in WANT_MODELS:
            if m != BASE_MODEL and (ENGINE / f"trace_out/{stem_s}__{m}").is_dir():
                run_dirs.append(f"trace_out/{stem_s}__{m}")
    trigger = {"tag": "renders-<date>", "runs": run_dirs, "prune": False}
    print(f"\n  Note: {len(scenarios)} scenarios (>100) - archive the full render set to a")
    print("  GitHub Release so the back-end keeps it without bloating git. Fire:")
    print("    .github/trigger/archive-renders.json =")
    print("    " + json.dumps(trigger))
    print("  then re-run this export with --archive-url <release-url> to link data-only rows.")
