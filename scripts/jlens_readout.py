"""Hosted Jacobian-lens depth readouts per pair, via Neuronpedia's lens API.

For each stress pair this calls POST {NEURONPEDIA_BASE_URL}/api/lens/prompt
twice (clinical prompt, patient prompt) and records, per layer, whether the
pair's clinical target token appears in the lens top-N readout at the final
prompt position - the depth profile behind the absence-vs-suppression
question (docs/jlens_evaluation.md). $0: hosted inference, no weights, no
Anthropic calls. Requires NEURONPEDIA_API_KEY, so this runs in CI, not in
the sandbox (whose egress proxy blocks neuronpedia.org).

Method credit: the Jacobian lens is Gurnee et al., "Verbalizable
Representations Form a Global Workspace in Language Models," Transformer
Circuits, 2026 (reference implementation github.com/anthropics/jacobian-lens,
Apache-2.0); the hosted endpoint is Neuronpedia's deployment of it.

The response token/lens schema is not documented, so parsing is defensive:
every run can save the raw per-prompt responses (--save-raw) and the parser
extracts what it recognizes, recording parse_status per pair instead of
crashing the batch. A model Neuronpedia does not serve is recorded as
supported=false in jlens_probe.json (exit 0): probe runs across the model
matrix use that to discover the support overlap.

Output: <out>/jlens_summary.part_NN.json (NN = offset+1), joined downstream
by (batch stem, results[i]["index"], model) exactly like the logits path.
The file name deliberately differs from batch_summary* so behavioral
collectors never ingest lens readouts as probability measurements.

Usage:
  python scripts/jlens_readout.py --pairs data/simulated/pairs_<STAMP>.json \
      --model qwen3-1.7b --out trace_out/pairs_<STAMP>__jlens_qwen3-1.7b \
      [--limit 3] [--offset 0] [--topn 8] [--save-raw]

No medical vocabulary lives in this file.
"""

import argparse
import gzip
import json
import os
import time
from pathlib import Path

NEURONPEDIA_BASE_URL = os.environ.get("NEURONPEDIA_BASE_URL", "https://www.neuronpedia.org")
LENS_ENDPOINT = "/api/lens/prompt"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 4
RETRY_SLEEP = 15.0  # doubles per retry: 15s, 30s, 60s (mirrors graph_client)
# 4xx statuses that mean "this model is not served for the lens", not a bug.
UNSUPPORTED_STATUS = {400, 404, 422}


def lens_request_body(model_id, prompt, topn):
    """Request body for /api/lens/prompt (schema read from the open-source
    webapp route on 2026-07-11): non-streaming, prompt positions only."""
    return {
        "modelId": model_id,
        "prompt": prompt,
        "type": ["JACOBIAN_LENS"],
        "topN": topn,
        "temperature": 0,
        "numCompletionTokens": 0,
        "filterNonWordTokens": False,
        "stream": False,
    }


def post_lens(session, body, timeout=180.0):
    """One lens call with graph_client's retry policy. Returns (json, None) on
    success, (None, 'unsupported: ...') when the model is not served, and
    raises on persistent 5xx/connectivity failure."""
    import requests

    last_err = None
    for attempt in range(ATTEMPTS):
        if attempt:
            wait = RETRY_SLEEP * 2 ** (attempt - 1)
            print(f"  retry {attempt}/{ATTEMPTS - 1} in {wait:.0f}s ({last_err})")
            time.sleep(wait)
        try:
            resp = session.post(NEURONPEDIA_BASE_URL + LENS_ENDPOINT, json=body, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            last_err = err
            continue
        if resp.status_code in UNSUPPORTED_STATUS:
            detail = resp.text[:300]
            return None, f"unsupported ({resp.status_code}): {detail}"
        if resp.status_code in RETRYABLE_STATUS:
            last_err = f"HTTP {resp.status_code}"
            continue
        resp.raise_for_status()
        return resp.json(), None
    raise RuntimeError(f"lens call failed after {ATTEMPTS} attempts: {last_err}")


def target_variants(target):
    """Token-string variants that count as the target in a lens readout list.
    Lens tokens come back as decoded strings; wordpiece leading-space and case
    of the first character are tokenizer artifacts, not semantics."""
    t = (target or "").strip()
    if not t:
        return set()
    variants = {t, " " + t}
    swapped = (t[0].swapcase() + t[1:]) if t else t
    variants |= {swapped, " " + swapped}
    return variants


def _as_list(value):
    return value if isinstance(value, list) else []


def _iter_layer_entries(node):
    """Yield (layer_number, top_token_list) from a token-position entry of
    unknown shape. Handles the shapes we consider plausible for the lens
    payload; anything unrecognized yields nothing (parse_status records it).

    Recognized shapes, checked in order:
      {"layers": [{"layer": 3, "topTokens"|"top"|"tokens": [...]}, ...]}
      {"lens": {"JACOBIAN_LENS": <same as above>}} (or lowercase key)
      {"3": [...], "4": [...]} - dict keyed by layer number
    """
    if not isinstance(node, dict):
        return
    lens = node.get("lens")
    if isinstance(lens, dict):
        for key in ("JACOBIAN_LENS", "jacobian_lens", "jacobian"):
            if key in lens:
                yield from _iter_layer_entries(lens[key] if isinstance(lens[key], dict)
                                               else {"layers": lens[key]})
                return
    layers = node.get("layers")
    if isinstance(layers, list):
        for entry in layers:
            if not isinstance(entry, dict):
                continue
            num = entry.get("layer", entry.get("layerNum", entry.get("l")))
            tops = next((_as_list(entry[k]) for k in ("topTokens", "top", "tokens", "topN")
                         if k in entry), [])
            if num is not None:
                yield num, tops
        return
    numeric = {k: v for k, v in node.items() if str(k).lstrip("-").isdigit()}
    if numeric and all(isinstance(v, list) for v in numeric.values()):
        for k, v in sorted(numeric.items(), key=lambda kv: int(kv[0])):
            yield int(k), v


def _token_string(item):
    """The token text from one top-N item: 'tok', {'token': 'tok', ...}, or
    ['tok', value]."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("token", "tok", "text", "t"):
            if isinstance(item.get(key), str):
                return item[key]
    if isinstance(item, list) and item and isinstance(item[0], str):
        return item[0]
    return None


def depth_profile(response, target, topn):
    """(profile, parse_status) for the FINAL prompt position of one response.

    profile: [{"layer": n, "target_rank": r|None, "top1": str|None}, ...] -
    target_rank is 1-based within the top-N readout, None when absent. Empty
    profile + status explain what shape defeated the parser."""
    variants = target_variants(target)
    tokens = _as_list(response.get("tokens")) if isinstance(response, dict) else []
    if not tokens:
        return [], "no tokens[] in response"
    final = tokens[-1]
    profile = []
    for layer, tops in _iter_layer_entries(final):
        strings = [_token_string(item) for item in tops[:topn]]
        rank = next((i + 1 for i, s in enumerate(strings) if s in variants), None)
        profile.append({"layer": layer, "target_rank": rank,
                        "top1": strings[0] if strings else None})
    if not profile:
        return [], f"unrecognized layer shape; final-position keys: {sorted(final)[:12]}"
    profile.sort(key=lambda e: e["layer"])
    return profile, "ok"


def classify(clin_profile, pat_profile):
    """Depth classification for one pair, from the two profiles.

    first_layer: earliest layer where the target enters the top-N.
    'suppressed' = target readable somewhere in depth under the patient
    phrasing but NOT at the last layer; 'absent' = never readable;
    'retained' = readable at the last layer too. None when unparsed."""
    def first_layer(profile):
        return next((e["layer"] for e in profile if e["target_rank"]), None)

    def last_layer_rank(profile):
        return profile[-1]["target_rank"] if profile else None

    out = {
        "first_layer": {"clinical": first_layer(clin_profile),
                        "patient": first_layer(pat_profile)},
        "last_layer_rank": {"clinical": last_layer_rank(clin_profile),
                            "patient": last_layer_rank(pat_profile)},
    }
    if not pat_profile:
        out["patient_depth_class"] = None
    elif first_layer(pat_profile) is None:
        out["patient_depth_class"] = "absent"
    elif last_layer_rank(pat_profile) is None:
        out["patient_depth_class"] = "suppressed"
    else:
        out["patient_depth_class"] = "retained"
    return out


def save_raw(out_dir, index, side, response):
    raw_dir = Path(out_dir) / "jlens_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"pair_{index:03d}_{side}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(response, fh)
    return str(path)


def build_result(index, pair, clin, pat, topn):
    target = pair.get("target_clinical_token") or ""
    clin_profile, clin_status = depth_profile(clin, target, topn) if clin else ([], "no response")
    pat_profile, pat_status = depth_profile(pat, target, topn) if pat else ([], "no response")
    result = {
        "index": index,
        "prompts": {"clinical": pair["top_prompt"], "patient": pair["bottom_prompt"]},
        "target_token": target or None,
        "depth": {"clinical": clin_profile, "patient": pat_profile},
        "parse_status": {"clinical": clin_status, "patient": pat_status},
    }
    result.update(classify(clin_profile, pat_profile))
    return result


def build_summary(model_id, results, start_index=1, topn=8):
    return {
        "mode": "jlens",
        "backend": "jlens-hosted",
        "graph_model": model_id,
        "lens_type": "JACOBIAN_LENS",
        "top_n": topn,
        "start_index": start_index,
        "endpoint": LENS_ENDPOINT,
        "method_credit": ("Jacobian lens: Gurnee et al., Transformer Circuits 2026; "
                          "reference implementation github.com/anthropics/jacobian-lens; "
                          "hosted by neuronpedia.org"),
        "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--model", required=True, help="Neuronpedia model id, e.g. qwen3-1.7b")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0, help="first N pairs after offset (0 = all)")
    parser.add_argument("--offset", type=int, default=0, help="skip N pairs; part number = offset+1")
    parser.add_argument("--topn", type=int, default=8, choices=range(1, 9))
    parser.add_argument("--save-raw", action="store_true",
                        help="gzip the raw API responses under <out>/jlens_raw/")
    args = parser.parse_args(argv)

    import requests

    api_key = os.environ.get("NEURONPEDIA_API_KEY")
    if not api_key:
        raise SystemExit("NEURONPEDIA_API_KEY is required (hosted lens endpoint)")
    session = requests.Session()
    session.headers["x-api-key"] = api_key

    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))  # top-level list
    chunk = pairs[args.offset:args.offset + args.limit] if args.limit else pairs[args.offset:]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    part = f"part_{args.offset + 1:02d}"

    results = []
    for i, pair in enumerate(chunk):
        index = args.offset + i + 1
        responses = {}
        for side, prompt in (("clinical", pair["top_prompt"]),
                             ("patient", pair["bottom_prompt"])):
            body = lens_request_body(args.model, prompt, args.topn)
            response, unsupported = post_lens(session, body)
            if unsupported:
                probe = {"model": args.model, "supported": False, "detail": unsupported,
                         "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                (out_dir / "jlens_probe.json").write_text(
                    json.dumps(probe, indent=1) + "\n", encoding="utf-8")
                print(f"model {args.model} not served by the lens endpoint: {unsupported}")
                return 0
            responses[side] = response
            if args.save_raw:
                save_raw(out_dir, index, side, response)
        results.append(build_result(index, pair, responses["clinical"],
                                    responses["patient"], args.topn))
        print(f"pair {index}: clinical={results[-1]['parse_status']['clinical']} "
              f"patient={results[-1]['parse_status']['patient']} "
              f"class={results[-1]['patient_depth_class']}")

    summary = build_summary(args.model, results, start_index=args.offset + 1, topn=args.topn)
    (out_dir / f"jlens_summary.{part}.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    probe = {"model": args.model, "supported": True, "pairs_measured": len(results),
             "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out_dir / "jlens_probe.json").write_text(json.dumps(probe, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out_dir / f'jlens_summary.{part}.json'} ({len(results)} pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
