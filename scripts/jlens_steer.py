"""Lens steering-swap causal check (docs/lens_steering_design.md, EXPLORATORY).

For each spec item (a patient-side prompt with its clinical target token),
call the hosted lens endpoint once unsteered (baseline) and once per
(layer, strength) with `swapToken` set to the target, then read the target's
final-position rank profile from each response with the pinned lens parser.
Prediction under test: hijack-class pairs recover at lower strength than
capture-class pairs (the taxonomy's causal check).

The steering fields (steerTokens/steerLayers/steerStrength/swapToken) were
read from the open-source webapp on 2026-07-11 and have never been exercised
here: the response shape under steering is UNVERIFIED. Every run saves raw;
parse_status is recorded per call; a persistent 4xx on the steering fields is
recorded as steering_supported=false and exits 0 (probe-negative evidence,
same contract as model support discovery). $0: hosted, no Anthropic calls.

Usage:
  NEURONPEDIA_API_KEY=... python scripts/jlens_steer.py \
      --spec data/steer_pilot_spec.json --out trace_out/steer_pilot__jsteer_gemma-2-2b \
      [--limit 2] [--offset 0] [--topn 8]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]

_JR_SPEC = importlib.util.spec_from_file_location(
    "jlens_readout", ENGINE / "scripts" / "jlens_readout.py")
jr = importlib.util.module_from_spec(_JR_SPEC)
_JR_SPEC.loader.exec_module(jr)


def steer_request_body(model_id, prompt, topn, target, layer, strength,
                       num_completion_tokens=1, swap_source=None):
    """Baseline body plus the steering fields, per the route's OpenAPI schema
    (verified against the webapp source 2026-07-14 after the first probe's 400:
    steer tokens are {token, type} objects; steerStrength is a signed fraction
    of each position's residual norm; swapToken replaces steerTokens[0]'s
    readout). `layer`/`strength` None = unsteered baseline call. `swap_source`
    set = swap arm: replace the source readout with the target instead of
    additively injecting."""
    body = jr.lens_request_body(model_id, prompt, topn)
    body["numCompletionTokens"] = num_completion_tokens
    if layer is None:
        return body
    if swap_source is not None:
        body["steerTokens"] = [{"token": swap_source, "type": "JACOBIAN_LENS"}]
        body["swapToken"] = {"token": target, "type": "JACOBIAN_LENS"}
        body["steerLayers"] = [layer]
    else:
        body["steerTokens"] = [{"token": target, "type": "JACOBIAN_LENS"}]
        body["steerLayers"] = [layer]
        body["steerStrength"] = strength
    return body


def final_rank_profile(response, target, topn):
    """(first_layer, final_rank, parse_status) for the FINAL PROMPT position.

    With numCompletionTokens > 0 the response appends generated-token entries,
    so tokens[-1] is the completion, not the prompt's final position (probe
    round 2, 2026-07-14: baseline final_rank came back None while the
    completion WAS the target). Trim generated entries before parsing."""
    tokens = response.get("tokens") if isinstance(response, dict) else None
    if isinstance(tokens, list):
        prompt_tokens = [t for t in tokens
                         if not (isinstance(t, dict)
                                 and (t.get("is_generated") or t.get("kind") == "generated"))]
        if prompt_tokens:
            response = dict(response, tokens=prompt_tokens)
    profile, status = jr.depth_profile(response, target, topn)
    if not profile:
        return None, None, status
    first = next((rec["layer"] for rec in profile if rec.get("target_rank") is not None), None)
    return first, profile[-1].get("target_rank"), status


def completion_token(response):
    """First generated token, when the endpoint returns one."""
    for tok in response.get("tokens", []) if isinstance(response, dict) else []:
        if tok.get("is_generated") or tok.get("kind") == "generated":
            return tok.get("token")
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0, help="first N items after offset (0 = all)")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--topn", type=int, default=8, choices=range(1, 9))
    args = parser.parse_args(argv)

    import requests

    api_key = os.environ.get("NEURONPEDIA_API_KEY")
    if not api_key:
        raise SystemExit("NEURONPEDIA_API_KEY is required (hosted lens endpoint)")
    session = requests.Session()
    session.headers["x-api-key"] = api_key

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    model = spec["model"]
    layers, strengths = spec["layers"], spec["strengths"]
    nct = spec.get("num_completion_tokens", 1)
    items = spec["items"][args.offset:args.offset + args.limit] if args.limit \
        else spec["items"][args.offset:]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    part = f"part_{args.offset + 1:02d}"

    results = []
    for i, item in enumerate(items):
        index = args.offset + i + 1
        target = item["target"]
        winner = item.get("winner")
        calls = [("baseline", None, None, None)] + [
            (f"L{la}_s{st:g}", la, st, None) for la in layers for st in strengths]
        # swap arm: replace the patient-side winner's readout with the target,
        # one call per layer; skipped when the winner IS the target (held pairs)
        if winner and winner != target:
            calls += [(f"L{la}_swap", la, None, winner) for la in layers]
        row = {"index": index, "dataset": item["dataset"], "spec_index": item["index"],
               "class": item["class"], "target_token": target, "winner_token": winner,
               "calls": {}}
        for label, layer, strength, swap_source in calls:
            body = steer_request_body(model, item["prompt"], args.topn, target,
                                      layer, strength, nct, swap_source)
            try:
                response, unsupported = jr.post_lens(session, body)
            except RuntimeError as err:
                if results or row["calls"]:
                    raise  # mid-run failure is real; abort loudly
                probe = {"model": model, "steering_supported": False,
                         "detail": f"{err} (persistent failure on the first call; "
                                   "could also be a transient outage - re-probe)",
                         "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                (out_dir / "jsteer_probe.json").write_text(
                    json.dumps(probe, indent=1) + "\n", encoding="utf-8")
                print(f"steering probe negative: {probe['detail']}")
                return 0
            if unsupported:
                probe = {"model": model, "steering_supported": False, "detail": unsupported,
                         "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                (out_dir / "jsteer_probe.json").write_text(
                    json.dumps(probe, indent=1) + "\n", encoding="utf-8")
                print(f"steering not served: {unsupported}")
                return 0
            jr.save_raw(out_dir, index, label, response)  # schema unverified: raw always
            first, final_rank, status = final_rank_profile(response, target, args.topn)
            row["calls"][label] = {"first_layer": first, "final_rank": final_rank,
                                   "completion": completion_token(response),
                                   "parse_status": status}
        results.append(row)
        base = row["calls"].get("baseline", {})
        print(f"item {index} [{item['class']}]: baseline final_rank={base.get('final_rank')} "
              + " ".join(f"{k}={v['final_rank']}" for k, v in row["calls"].items()
                         if k != "baseline"))

    summary = {
        "mode": "jsteer",
        "backend": "jlens-hosted",
        "graph_model": model,
        "spec": args.spec,
        "layers": layers,
        "strengths": strengths,
        "top_n": args.topn,
        "start_index": args.offset + 1,
        "endpoint": jr.LENS_ENDPOINT,
        "_": ("EXPLORATORY steering-swap pilot (docs/lens_steering_design.md). "
              "No confirmatory claim; fresh pre-registered endpoints required first."),
        "method_credit": ("Jacobian lens + steering: Gurnee et al., Transformer Circuits "
                          "2026; hosted by neuronpedia.org"),
        "results": results,
    }
    (out_dir / f"jsteer_summary.{part}.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    probe = {"model": model, "steering_supported": True, "items_measured": len(results),
             "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out_dir / "jsteer_probe.json").write_text(json.dumps(probe, indent=1) + "\n",
                                               encoding="utf-8")
    print(f"-> {out_dir / f'jsteer_summary.{part}.json'} ({len(results)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
