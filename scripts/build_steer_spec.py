"""Build the steering-100 spec (audit item 3, owner-approved 2026-07-28).

Expands the 20-item lens-steering pilot (data/steer_pilot_spec.json, protocol
pinned 2026-07-14) to a 100-phrase spec drawn from the whole traced corpus:

  eligible   - gemma-2-2b 2panel results where the clinical side's top token IS
               the registered target and the patient side's top token is not
               (the restoration condition the steering protocol tests);
  dedup      - one item per patient prompt (re-traced phrases collapse);
  exclusions - POPULATION-DEF B stamps stay out; holdout pairs were never
               traced so cannot appear;
  class      - lens depth class (retained/suppressed/absent) joined from
               landed jlens summaries; 'unknown' when no lens row exists;
  sampling   - seeded, stratified: every suppressed-class flip is taken (the
               rare class the mitigation argument leans on), the remainder
               fills evenly from retained/absent/unknown.

Grid fields (layers, strengths, completion tokens) are copied verbatim from
the pilot spec so the two runs stay protocol-identical. $0 hosted; the spec
carries phrase text, so run seal_check before committing the output.
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import re
from pathlib import Path

POP_DEF_B = {"pairs_20260713T031252Z", "pairs_20260713T135755Z", "pairs_20260713T050939Z"}
TOKEN_RE = re.compile(r'"\s*(.+?)"')


def _token(quoted):
    m = TOKEN_RE.search(quoted or "")
    return (" " + m.group(1).strip()) if m else None


def collect_candidates(trace_root: Path):
    lens = {}
    for d in glob.glob(str(trace_root / "pairs_*__jlens_gemma-2-2b")):
        stem = Path(d).name.split("__")[0]
        for f in glob.glob(d + "/jlens_summary*.json"):
            for r in json.loads(Path(f).read_text(encoding="utf-8")).get("results", []):
                lens.setdefault(stem, {})[r["index"]] = r.get("patient_depth_class")

    seen_prompts = set()
    items = []
    for f in sorted(glob.glob(str(trace_root / "pairs_*/batch_summary*.json"))):
        stem = Path(f).parent.name
        if "__" in stem or stem in POP_DEF_B:
            continue
        for r in json.loads(Path(f).read_text(encoding="utf-8")).get("results", []):
            spread = r.get("predictive_spread") or {}
            clin, pat = spread.get("clinical") or [], spread.get("patient") or []
            target = _token(r.get("target_token"))
            prompts = r.get("prompts") or {}
            if not (target and clin and pat and prompts.get("patient")):
                continue
            clin_top, pat_top = _token(clin[0][0]), _token(pat[0][0])
            if clin_top != target or pat_top == target or pat_top is None:
                continue
            key = prompts["patient"]
            if key in seen_prompts:
                continue
            seen_prompts.add(key)
            items.append({
                "dataset": stem,
                "index": r["index"],
                "class": lens.get(stem, {}).get(r["index"]) or "unknown",
                "prompt": prompts["patient"],
                "target": target,
                "winner": pat_top,
            })
    return items


def stratified_sample(items, n, seed):
    rng = random.Random(seed)
    by_class: dict[str, list] = {}
    for it in items:
        by_class.setdefault(it["class"], []).append(it)
    for v in by_class.values():
        v.sort(key=lambda it: (it["dataset"], it["index"]))
        rng.shuffle(v)
    picked = list(by_class.pop("suppressed", []))[:n]
    rest = ["retained", "absent", "unknown"]
    while len(picked) < n and any(by_class.get(c) for c in rest):
        for c in rest:
            if len(picked) >= n:
                break
            if by_class.get(c):
                picked.append(by_class[c].pop())
    picked.sort(key=lambda it: (it["dataset"], it["index"]))
    return picked


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pilot", default="data/steer_pilot_spec.json")
    ap.add_argument("--trace-root", default="trace_out", type=Path)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/steer_spec_100_20260728.json")
    args = ap.parse_args(argv)

    pilot = json.loads(Path(args.pilot).read_text(encoding="utf-8"))
    candidates = collect_candidates(args.trace_root)
    picked = stratified_sample(candidates, args.n, args.seed)

    classes: dict[str, int] = {}
    for it in picked:
        classes[it["class"]] = classes.get(it["class"], 0) + 1
    spec = {
        "_": ("Steering-100 spec (audit item 3, owner-approved 2026-07-28). Protocol grid copied "
              "verbatim from data/steer_pilot_spec.json (2026-07-14). Items: gemma-2-2b flips where "
              "the clinical side tops with the registered target and the patient side does not; "
              f"one item per patient prompt; POPULATION-DEF B excluded; seed {args.seed}; "
              f"class counts {json.dumps(classes, sort_keys=True)} from landed lens rows."),
        "model": pilot["model"],
        "layers": pilot["layers"],
        "strengths": pilot["strengths"],
        "num_completion_tokens": pilot["num_completion_tokens"],
        "items": picked,
    }
    Path(args.out).write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(picked)} items -> {args.out} (from {len(candidates)} eligible; classes {classes})")
    return 0


if __name__ == "__main__":
    main()
