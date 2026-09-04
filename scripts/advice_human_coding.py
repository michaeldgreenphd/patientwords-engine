"""Human-coding instrument support for the advice arm's registered validation gate.

The advice pre-registration requires a BLINDED human-coded sample (n=25,
stratified by arm) with judge-vs-human agreement reported per arm before any
claim-grade use of machine codings. This script feeds and scores the site's
coding page (patientwords llm/code.html):

  build-sample  -> data/advice_coding_sample.json (site copy optional): the
                   blinded payload — opaque coding_id + response text + the
                   rubric's tiers/flags, deterministically shuffled. NO arm,
                   model, prompt, or machine tier appears in the payload.
                   A keymap (coding_id -> response_sha256/arm/model) is written
                   engine-side for scoring.
  score         -> agreement report: human vs machine judge, overall and PER
                   ARM (the registered stratification), raw agreement +
                   linearly-weighted kappa on tier ranks + per-flag agreement.

Blinding is procedural: both repos are public, so the keymap is committable —
the discipline is that the coder codes from the page only and never consults
the keymap; commit the keymap together with the codings export, after coding.
Coders are recorded by name in the export (the owner for now, clinicians
later — the schema is multi-coder: score accepts several codings files and
also reports human-vs-human agreement when given more than one).

Codings exports land in data/advice/human/ (append-only, like everything in
data/advice/). Nothing here quotes stimulus phrase text: the payload carries
model RESPONSE text only, which is already published in advice_scenarios.json.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARMS = ("clinical", "patient", "translated")


def _load_advice_eval():
    path = Path(__file__).resolve().parent / "advice_eval.py"
    spec = importlib.util.spec_from_file_location("advice_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_sample(args) -> Path:
    ae = _load_advice_eval()
    rows = ae._read_jsonl(args.responses)
    ok, msg = ae.verify_chain(rows)
    if not ok:
        raise SystemExit(f"{args.responses}: {msg} - refusing to sample a tampered archive")
    advice = [r for r in rows if r.get("record_type") == "advice" and r.get("response_text")]
    if not advice:
        raise SystemExit("no advice records with text")
    rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))

    # Stratified selection: round-robin over arms, seeded, no duplicate responses.
    rng = random.Random(args.seed)
    by_arm = {arm: [r for r in advice if r["arm"] == arm] for arm in ARMS}
    for arm in ARMS:
        rng.shuffle(by_arm[arm])
    picked, seen = [], set()
    while len(picked) < args.n and any(by_arm.values()):
        for arm in ARMS:
            if len(picked) >= args.n:
                break
            while by_arm[arm]:
                r = by_arm[arm].pop()
                if r["response_sha256"] not in seen:
                    seen.add(r["response_sha256"])
                    picked.append(r)
                    break
    if len(picked) < args.n:
        print(f"note: only {len(picked)} distinct responses available (asked for {args.n})")

    items, keymap = [], {}
    for r in picked:
        coding_id = hashlib.sha256(f"{r['response_sha256']}|{args.seed}".encode()).hexdigest()[:12]
        items.append({"coding_id": coding_id, "response_text": r["response_text"]})
        keymap[coding_id] = {"response_sha256": r["response_sha256"], "stimulus_id": r["stimulus_id"],
                             "arm": r["arm"], "model": r["model_requested"], "sample_k": r["sample_k"]}
    rng.shuffle(items)  # presentation order carries no arm/model structure

    coders = []
    for part in (args.coders or "").split(";"):
        part = part.strip()
        if part and "=" in part:
            cid, label = part.split("=", 1)
            coders.append({"id": cid.strip(), "label": label.strip()})
    if not coders:
        raise SystemExit("--coders must name at least one coder as id=label (the page's attribution menu)")

    payload = {
        "_readme": ("Blinded human-coding sample for the advice arm's registered validation gate. "
                    "Response text only - no arm, model, prompt, or machine coding appears here. "
                    "Codings are recorded locally by llm/code.html and enter the study only when "
                    "the exported file is committed to the engine repo (data/advice/human/). "
                    "The coders roster is the page's attribution menu - regenerate with --coders "
                    "to add clinician coders later."),
        "generated_utc": utc_now_iso(),
        "seed": args.seed,
        "coders": coders,
        "source_responses": str(args.responses),
        "rubric": {"version": rubric.get("version"),
                   "sha256": hashlib.sha256(json.dumps(rubric, sort_keys=True).encode()).hexdigest(),
                   "tiers": rubric["tiers"], "flags": rubric.get("flags", [])},
        "n_items": len(items),
        "items": items,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    km_path = Path(args.keymap_out)
    km_path.parent.mkdir(parents=True, exist_ok=True)
    km_path.write_text(json.dumps({"seed": args.seed, "generated_utc": payload["generated_utc"],
                                   "map": keymap}, indent=1) + "\n", encoding="utf-8")
    print(f"blinded payload: {len(items)} items -> {out}")
    print(f"keymap (do not consult while coding; commit with the codings export) -> {km_path}")
    arms = {}
    for v in keymap.values():
        arms[v["arm"]] = arms.get(v["arm"], 0) + 1
    print(f"stratification: {arms}")
    if args.site:
        site_copy = Path(args.site) / "data" / "advice_coding_sample.json"
        site_copy.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"site copy -> {site_copy}")
    return out


def _weighted_kappa(pairs: list, order: list) -> float | None:
    """Linearly-weighted Cohen's kappa over tier ranks; None when degenerate."""
    if not pairs:
        return None
    k = len(order)
    rank = {t: i for i, t in enumerate(order)}
    w = [[1 - abs(i - j) / (k - 1) for j in range(k)] for i in range(k)]
    n = len(pairs)
    obs = [[0.0] * k for _ in range(k)]
    for a, b in pairs:
        obs[rank[a]][rank[b]] += 1 / n
    pa = [sum(obs[i][j] for j in range(k)) for i in range(k)]
    pb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    po = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    pe = sum(w[i][j] * pa[i] * pb[j] for i in range(k) for j in range(k))
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def score(args) -> dict:
    ae = _load_advice_eval()
    keymap = json.loads(Path(args.keymap).read_text(encoding="utf-8"))["map"]
    rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
    order = [t["id"] for t in rubric["tiers"]]
    machine = {}
    for j in ae._read_jsonl(args.judgments):
        if j.get("tier") is not None:
            machine[j["response_sha256"]] = j
    coders = []
    for path in args.codings:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        coders.append((doc.get("coder") or Path(path).stem, {c["coding_id"]: c for c in doc["codings"]}))

    report = {"generated_utc": utc_now_iso(), "rubric_version": rubric.get("version"),
              "tier_order": order, "coders": [c for c, _ in coders], "vs_machine": {}, "inter_human": None}
    for coder, codings in coders:
        pairs_by_arm: dict[str, list] = {}
        flag_hits: dict[str, list] = {}
        missing_machine = 0
        for cid, c in codings.items():
            km = keymap.get(cid)
            if not km or not c.get("tier"):
                continue
            m = machine.get(km["response_sha256"])
            if not m:
                missing_machine += 1
                continue
            pairs_by_arm.setdefault(km["arm"], []).append((c["tier"], m["tier"]))
            for f in rubric.get("flags", []):
                fid = f["id"]
                hv, mv = (c.get("flags") or {}).get(fid), (m.get("flags") or {}).get(fid)
                if hv is not None and mv is not None:
                    flag_hits.setdefault(fid, []).append(bool(hv) == bool(mv))
        entry = {"n_coded": sum(len(v) for v in pairs_by_arm.values()), "missing_machine": missing_machine,
                 "by_arm": {}, "overall": {}}
        all_pairs = [p for v in pairs_by_arm.values() for p in v]
        for arm, pairs in sorted(pairs_by_arm.items()):
            agree = sum(1 for a, b in pairs if a == b)
            entry["by_arm"][arm] = {"n": len(pairs), "raw_agreement": round(agree / len(pairs), 3),
                                    "weighted_kappa": _weighted_kappa(pairs, order)}
        agree = sum(1 for a, b in all_pairs if a == b)
        entry["overall"] = {"n": len(all_pairs),
                            "raw_agreement": round(agree / len(all_pairs), 3) if all_pairs else None,
                            "weighted_kappa": _weighted_kappa(all_pairs, order),
                            "flags": {fid: round(sum(v) / len(v), 3) for fid, v in flag_hits.items()}}
        report["vs_machine"][coder] = entry

    if len(coders) >= 2:
        (c1, a), (c2, b) = coders[0], coders[1]
        shared = [(a[cid]["tier"], b[cid]["tier"]) for cid in a if cid in b
                  and a[cid].get("tier") and b[cid].get("tier")]
        agree = sum(1 for x, y in shared if x == y)
        report["inter_human"] = {"coders": [c1, c2], "n": len(shared),
                                 "raw_agreement": round(agree / len(shared), 3) if shared else None,
                                 "weighted_kappa": _weighted_kappa(shared, order)}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("coders", "vs_machine", "inter_human")}, indent=1))
    print(f"agreement report -> {out}")
    return report


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-sample", help="blinded coding payload + engine-side keymap")
    b.add_argument("--responses", required=True)
    b.add_argument("--rubric", default="data/advice_rubric.json")
    b.add_argument("--n", type=int, default=25)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--out", default="data/advice_coding_sample.json")
    b.add_argument("--keymap-out", default="data/advice/human/coding_keymap.json")
    b.add_argument("--site", default=None)
    b.add_argument("--coders", default="owner=Michael D. Green (study owner)",
                   help="semicolon-separated id=label roster for the page's coder menu; "
                        "add clinicians later by regenerating with an extended roster")
    s = sub.add_parser("score", help="human-vs-machine agreement, per arm (registered gate)")
    s.add_argument("--codings", nargs="+", required=True, help="exported codings JSON file(s) from llm/code.html")
    s.add_argument("--keymap", default="data/advice/human/coding_keymap.json")
    s.add_argument("--judgments", required=True)
    s.add_argument("--rubric", default="data/advice_rubric.json")
    s.add_argument("--out", default="data/advice/human/agreement_report.json")
    args = parser.parse_args(argv)
    build_sample(args) if args.command == "build-sample" else score(args)


if __name__ == "__main__":
    main()
