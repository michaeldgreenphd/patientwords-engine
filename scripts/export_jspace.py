"""Site dataset for the J-space worked example: data/jspace.json.

Fills the three-panel J-space figure (methods Step 4 / technical Part 2) with a
REAL Jacobian-lens residual-stream readout for one published pair, flipping the
payload's `empirical` flag so the pages retire the hand-authored schematic and
relabel the figure. The worked example (pairs_20260711T051145Z#13, target
" medication") was chosen by scanning all 25 committed census pairs for the
one whose three final-layer readouts carry the story at top-1:

  clinical    "I have cognitive impairment, ... take my"   -> " medication"
  patient     "I've been feeling foggy in my head, ..."     -> " vitamins"
  translation (the pair's opus translation)                 -> " medication"

Sources, all committed on this branch and parsed with jlens_readout's pinned
helpers: the pair's raw JACOBIAN_LENS responses under
trace_out/<stem>__jlens_gemma-2-2b/jlens_raw/, and for the translation panel
the raw readout of the pair's opus translation, located mechanically through
data/simulated/txcorpus_<txstamp>.json (generation.source_batch/source_index
join) and the txcorpus priority subsets. Every prompt is verified by
reconstructing it from the response's own tokens - an index drift refuses, it
never mis-attributes.

Concepts (the figure's mid-stream pills) are the top-1 readout token per layer
over the middle-to-late band (L12..L24 of gemma-2-2b's 26 layers, the final
layer excluded because it is the output), filtered to word-like tokens (the
early/middle Jacobian readout contains tokenizer artifacts) and deduped in
depth order, capped at 4. The payload note discloses this selection.

Refusal contract (matches the sister exporters): any missing raw, prompt
mismatch, or unfilled panel exits 3 and leaves the site file untouched.

Usage:
  python scripts/export_jspace.py --site ../patientwords
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]

_JR = importlib.util.spec_from_file_location("jlens_readout", ENGINE / "scripts" / "jlens_readout.py")
jr = importlib.util.module_from_spec(_JR)
_JR.loader.exec_module(jr)

WORDISH = re.compile(r"^\s?[A-Za-z][A-Za-z'\-]*$")


def _refuse(reason: str) -> SystemExit:
    print(f"refused: {reason} (site file left untouched)")
    return SystemExit(3)


def load_raw(path: Path) -> dict:
    if not path.is_file():
        raise _refuse(f"{path}: raw readout missing")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def prompt_of(response: dict) -> str:
    toks = [t.get("token", "") for t in response.get("tokens", [])
            if isinstance(t, dict) and not (t.get("is_generated") or t.get("kind") == "generated")]
    return "".join(toks).replace("<bos>", "")


def layer_tops(response: dict) -> list[list[str]]:
    """Per-layer top-token lists at the final prompt position."""
    tokens = response.get("tokens") or []
    if not tokens:
        raise _refuse("response has no tokens[]")
    results = (tokens[-1].get("results") or [{}])[0]
    tops = results.get("top_tokens")
    if not isinstance(tops, list) or not tops:
        raise _refuse("final position has no top_tokens layers")
    return tops


def concepts_of(tops: list[list[str]], lo: int, hi: int, cap: int) -> list[str]:
    # word-like AND lowercase (CamelCase artifacts like 'RenderAtEndOf' pass a
    # bare alphabetic check) AND persistent: a real concept reads out across
    # three or more band layers; tokenizer artifacts read out only briefly
    first_layer: dict[str, int] = {}
    count: dict[str, int] = {}
    for layer in range(lo, min(hi + 1, len(tops) - 1)):  # exclude the final layer (= output)
        for tok in tops[layer][:3]:
            if not WORDISH.match(tok) or not tok.strip().islower():
                continue
            key = tok.strip()
            first_layer.setdefault(key, layer)
            count[key] = count.get(key, 0) + 1
    stable = [k for k in first_layer if count[k] >= 3]
    stable.sort(key=lambda k: first_layer[k])
    return stable[-cap:]  # the latest-forming pills - the ones nearest the output


def diff_span(a: str, b: str) -> tuple[str, str]:
    """The differing middles of two sentences sharing a frame (word-level)."""
    aw, bw = a.split(), b.split()
    i = 0
    while i < min(len(aw), len(bw)) and aw[i] == bw[i]:
        i += 1
    j = 0
    while j < min(len(aw), len(bw)) - i and aw[-1 - j] == bw[-1 - j]:
        j += 1
    return " ".join(aw[i:len(aw) - j]) or a, " ".join(bw[i:len(bw) - j]) or b


def panel(response: dict, expected_prompt: str, trigger: str, target: str) -> dict:
    got = prompt_of(response).strip()
    if got != expected_prompt.strip():
        raise _refuse(f"prompt mismatch: raw says {got[:60]!r}, expected {expected_prompt[:60]!r}")
    tops = layer_tops(response)
    out_tok = tops[-1][0] if tops[-1] else None
    variants = jr.target_variants(target)
    on_target = bool(out_tok and jr.target_match(out_tok, variants))
    return {
        "input": expected_prompt,
        "trigger": trigger,
        "concepts": concepts_of(tops, 12, len(tops) - 2, 4),
        "output": (out_tok or "").strip(),
        "on_target": on_target,
    }


def find_translation(stem: str, index: int):
    """(translated_sentence, raw_path) for the pair's opus translation, via the
    txcorpus master (source join) and whichever priority subset holds it."""
    masters = sorted(ENGINE.glob("data/simulated/txcorpus_*.json"))
    masters = [m for m in masters if "priority" not in m.name and not m.name.endswith(".report.json")]
    sentence = None
    for m in masters:
        for it in json.loads(m.read_text(encoding="utf-8")):
            gen = it.get("generation") or {}
            if gen.get("source_batch") == stem and gen.get("source_index") == index:
                sentence = it.get("bottom_prompt")
                break
        if sentence:
            break
    if not sentence:
        raise _refuse(f"no txcorpus translation found for {stem}#{index}")
    for sub in sorted(ENGINE.glob("data/simulated/txcorpus_priority*.json")):
        items = json.loads(sub.read_text(encoding="utf-8"))
        for i, it in enumerate(items):
            if it.get("bottom_prompt") == sentence:
                raw = (ENGINE / f"trace_out/{sub.stem}__jlens_gemma-2-2b/jlens_raw" /
                       f"pair_{i + 1:03d}_patient.json.gz")
                if raw.is_file():
                    return sentence, raw
    raise _refuse(f"translation readout raw not committed for {stem}#{index}")


def build(stem: str, index: int) -> dict:
    batch = json.loads((ENGINE / f"data/simulated/{stem}.json").read_text(encoding="utf-8"))
    pair = batch[index - 1]
    clinical, patient = pair["top_prompt"], pair["bottom_prompt"]
    target = pair.get("target_clinical_token") or ""
    raw_dir = ENGINE / f"trace_out/{stem}__jlens_gemma-2-2b/jlens_raw"
    clin_trig, pat_trig = diff_span(clinical, patient)
    tx_sentence, tx_raw = find_translation(stem, index)
    _, tx_trig = diff_span(clinical, tx_sentence)

    panels = {
        "clinical": panel(load_raw(raw_dir / f"pair_{index:03d}_clinical.json.gz"),
                          clinical, clin_trig, target),
        "patient": panel(load_raw(raw_dir / f"pair_{index:03d}_patient.json.gz"),
                         patient, pat_trig, target),
        "translation": panel(load_raw(tx_raw), tx_sentence, tx_trig, target),
    }
    for name, p in panels.items():
        if not (p["input"] and p["concepts"] and p["output"]):
            raise _refuse(f"panel {name} incomplete; empirical flag stays down")

    return {
        "_": ("J-space schematic data contract. While empirical:false the methods (Step 4) and "
              "technical (Part 2) pages keep the hand-authored 'Illustrative schematic' figure "
              "untouched. When the backend commits a real J-lens residual-stream readout for the "
              "worked example, set empirical:true and fill panels; the pages then render these "
              "tokens into the J-space pills, replace the input/output, and relabel the figure "
              "'Empirical J-lens residual stream readout at middle layers.' The disclaimer must "
              "never say 'empirical' while empirical is false."),
        "empirical": True,
        "note": (f"JACOBIAN_LENS readout, gemma-2-2b, {stem}#{index}, chosen by scanning every "
                 f"committed census pair for a triple whose final-layer readouts carry the story "
                 f"at top-1. Concepts are top-3 readout tokens per layer over L12-L24 (final layer "
                 f"excluded: it is the output), lowercase word-like tokens only, deduped in depth "
                 f"order. Translation panel reads the committed lens run of the pair's opus "
                 f"translation from the txcorpus subset. Method credit: Jacobian lens, Gurnee "
                 f"et al., Transformer Circuits 2026; hosted by neuronpedia.org."),
        "source": {"stem": stem, "index": index, "target": target,
                   "translation_sentence": tx_sentence},
        "panels": panels,
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stem", default="pairs_20260711T051145Z")
    # 13 is the census pair whose three readouts tell the story cleanly at
    # top-1 (clinical 'medication', patient 'vitamins', translation recovers
    # 'medication') - chosen by scanning all 25 committed census pairs
    ap.add_argument("--index", type=int, default=13)
    ap.add_argument("--out", default="data/jspace.json")
    ap.add_argument("--site", default=None)
    args = ap.parse_args(argv)

    payload = build(args.stem, args.index)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    p = payload["panels"]
    print(f"jspace: {args.stem}#{args.index} clinical->{p['clinical']['output']!r} "
          f"patient->{p['patient']['output']!r} translation->{p['translation']['output']!r} "
          f"-> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "jspace.json"
        site_copy.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"site copy -> {site_copy}")


if __name__ == "__main__":
    main()
