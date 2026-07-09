"""Score urgency shift: does patient phrasing move predictions toward less urgent care?

Not all prediction flips are equal. A flip from "dermatologist" to "doctor" changes
the urgency of the recommended action; a flip between two synonyms does not. This
scores every traced scenario against an urgency-tier vocabulary (a reviewed JSON
data file - no medical vocabulary lives in this script):

  expected tier   probability-weighted mean tier over the tier-assigned tokens in a
                  side's spread (renormalized; requires >= --min-coverage of spread
                  mass to be tier-assigned, else null)
  tier shift      patient expected tier - clinical expected tier (negative = patient
                  wording points at less urgent care)
  flip class      compares the literal top-1 tokens: downgrade / upgrade / lateral
                  (same tier) / uninformative (either top-1 unassigned)

Usage:
  python scripts/urgency_shift.py [--tiers data/urgency_tiers.draft.json]
      [--frontend ../patientwords] [--min-coverage 0.3] [--out urgency_shift.json]
"""

import argparse
import glob
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--tiers", default="data/urgency_tiers.draft.json")
parser.add_argument("--frontend", default="../patientwords")
parser.add_argument("--min-coverage", type=float, default=0.3,
                    help="minimum share of a spread's mass that must be tier-assigned")
parser.add_argument("--out", default="urgency_shift.json")
parser.add_argument("--publish", default="",
                    help="frontend repo root: also write a trimmed data/urgency_shift.json "
                         "for the site (summary + join-keyed rows + vocabulary status)")
args = parser.parse_args()

vocab = json.loads(Path(args.tiers).read_text(encoding="utf-8"))["tokens"]


def tier(token, cont=None):
    """Tier for a token; when a greedy continuation exists ('new' -> 'new sleeping
    pill'), try the completed phrase's words right-to-left first - the head noun
    carries the urgency information."""
    if not token:
        return None
    key = str(token).strip().lower()
    if cont:
        phrase = cont.get(str(token).strip()) or cont.get(key)
        if phrase:
            for w in reversed(str(phrase).lower().split()):
                e = vocab.get(w.strip('.,!?\'"'))
                if e and e["tier"] is not None:
                    return e["tier"]
    e = vocab.get(key)
    return e["tier"] if e else None


def bare(label):
    if not isinstance(label, str):
        return None
    m = re.match(r'Output "\s*(.*)"$', label)
    return (m.group(1) if m else label).strip() or None


def expected_tier(spread, min_cov, cont=None):
    """Probability-weighted mean tier; None when too little mass is tier-assigned."""
    total = wsum = cov = 0.0
    for token, prob in spread or []:
        total += prob
        tr = tier(token, cont)
        if tr is not None:
            cov += prob
            wsum += prob * tr
    if not total or cov / total < min_cov:
        return None, (cov / total if total else 0.0)
    return wsum / cov, cov / total


def classify(top_c, top_p, cont_c=None, cont_p=None):
    tc, tp = tier(top_c, cont_c), tier(top_p, cont_p)
    if tc is None or tp is None:
        return "uninformative"
    if tp < tc:
        return "downgrade"
    if tp > tc:
        return "upgrade"
    return "lateral"


rows = []


def add(model, name, index, prompts, spread_c, spread_p, topic=None,
        penalty=None, spread_t=None, cont_c=None, cont_p=None):
    if not spread_c or not spread_p:
        return
    et_c, cov_c = expected_tier(spread_c, args.min_coverage, cont_c)
    et_p, cov_p = expected_tier(spread_p, args.min_coverage, cont_p)
    top_c = spread_c[0][0] if spread_c else None
    top_p = spread_p[0][0] if spread_p else None
    flipped = bool(top_c and top_p and top_c != top_p)
    rows.append({
        "model": model, "batch": name, "index": index, "topic": topic,
        "clinical_prompt": (prompts or {}).get("clinical"),
        "top_clinical": top_c, "top_patient": top_p,
        # how strongly each side commits to its top prediction - a downgrade at
        # p=0.5 is different evidence from one at p=0.1
        "p_top_clinical": round(spread_c[0][1], 3) if spread_c else None,
        "p_top_patient": round(spread_p[0][1], 3) if spread_p else None,
        "tier_top_clinical": tier(top_c, cont_c), "tier_top_patient": tier(top_p, cont_p),
        "flipped": flipped,
        "flip_class": classify(top_c, top_p, cont_c, cont_p) if flipped else None,
        "expected_tier_clinical": None if et_c is None else round(et_c, 3),
        "expected_tier_patient": None if et_p is None else round(et_p, 3),
        "tier_shift": None if (et_c is None or et_p is None) else round(et_p - et_c, 3),
        "language_penalty": penalty,
        "coverage": [round(cov_c, 2), round(cov_p, 2)],
        # word counts [clinical, patient] for the length-confound check:
        # colloquial rewrites tend to run longer, and penalty must not
        # reduce to prompt length
        "prompt_words": [
            len(p.split()) if isinstance(p := (prompts or {}).get(side), str) else None
            for side in ("clinical", "patient")
        ],
    })
    # mitigation runs carry a third, translated side: does translating the
    # patient sentence restore the URGENCY, not just the probability?
    if spread_t:
        et_t, _ = expected_tier(spread_t, args.min_coverage)
        r = rows[-1]
        r["top_translated"] = spread_t[0][0]
        r["tier_top_translated"] = tier(spread_t[0][0])
        r["expected_tier_translated"] = None if et_t is None else round(et_t, 3)
        et_p_val = r["expected_tier_patient"]
        r["urgency_recovery"] = (None if (et_t is None or et_p_val is None)
                                 else round(et_t - et_p_val, 3))


# site payload (bare-token spreads, per model)
site = Path(args.frontend) / "data/simulated_scenarios.json"
# topic lookup: (batch stem, 1-based index) -> condition area, from the batch files
topics = {}
for bf in glob.glob("data/simulated/pairs_*.json"):
    if bf.endswith(".report.json"):
        continue
    stem = Path(bf).stem
    try:
        batch = json.loads(Path(bf).read_text(encoding="utf-8"))
    except Exception:
        continue
    for i, pair in enumerate(batch, start=1):
        topics[(stem, i)] = (pair.get("generation") or {}).get("topic")

# engine trace_out summaries first - they carry continuations
seen = set()
# all 2panel-schema runs: generated batches AND curated subsets (mitigation etc.);
# non-2panel dirs are skipped harmlessly because add() requires clinical+patient spreads
for part in sorted(glob.glob("trace_out/*/batch_summary.part_*.json")):
    run_dir = Path(part).parent.name
    stem, _, model_suffix = run_dir.partition("__")
    summary = json.loads(Path(part).read_text(encoding="utf-8"))
    model = summary.get("graph_model") or model_suffix or "gemma-2-2b"
    for r in summary.get("results", []):
        if (model, stem, r["index"]) in seen:
            continue
        sp = r.get("predictive_spread") or {}

        def clean(side):
            return [[bare(t), p] for t, p in (sp.get(side) or []) if bare(t)]

        cont = r.get("continuations") or {}
        add(model, stem, r["index"], r.get("prompts"), clean("clinical"), clean("patient"),
            topic=topics.get((stem, r["index"])),
            penalty=r.get("language_penalty"), spread_t=clean("translated") or None,
            cont_c=cont.get("clinical"), cont_p=cont.get("patient"))
        seen.add((model, stem, r["index"]))

# site payload fills anything the engine tree lacks
if site.is_file():
    payload = json.loads(site.read_text(encoding="utf-8"))
    for s in payload.get("scenarios", []):
        for mid, m in (s.get("models") or {}).items():
            if (mid, s.get("batch"), s.get("batch_index")) in seen:
                continue
            add(mid, s.get("batch"), s.get("batch_index"),
                {"clinical": s.get("clinical_prompt")},
                m.get("spread_clinical"), m.get("spread_patient"),
                topic=s.get("topic") or topics.get((s.get("batch"), s.get("batch_index"))),
                penalty=m.get("language_penalty"))

flips = [r for r in rows if r["flipped"]]
down = [r for r in flips if r["flip_class"] == "downgrade"]
up = [r for r in flips if r["flip_class"] == "upgrade"]
shifts = [r["tier_shift"] for r in rows if r["tier_shift"] is not None]

summary = {
    "measurements": len(rows),
    "flips": len(flips),
    "flip_classes": {
        "downgrade": len(down), "upgrade": len(up),
        "lateral": sum(1 for r in flips if r["flip_class"] == "lateral"),
        "uninformative": sum(1 for r in flips if r["flip_class"] == "uninformative"),
    },
    "mean_tier_shift": round(sum(shifts) / len(shifts), 4) if shifts else None,
    "tier_shift_n": len(shifts),
    "per_model": {},
}
def sign_test(k_down, k_up):
    """Two-sided exact sign test: is the downgrade/upgrade split consistent with 50/50?"""
    import math
    n = k_down + k_up
    if n == 0:
        return None
    k = min(k_down, k_up)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 5)


for model in sorted({r["model"] for r in rows}):
    mr = [r for r in rows if r["model"] == model]
    ms = [r["tier_shift"] for r in mr if r["tier_shift"] is not None]
    mf = [r for r in mr if r["flipped"]]
    d = sum(1 for r in mf if r["flip_class"] == "downgrade")
    u = sum(1 for r in mf if r["flip_class"] == "upgrade")
    # confident downgrades: the patient side commits to the downgraded action
    conf = [r for r in mf if r["flip_class"] == "downgrade"
            and (r["p_top_patient"] or 0) >= 0.2]
    summary["per_model"][model] = {
        "n": len(mr), "flips": len(mf),
        "downgrades": d, "upgrades": u,
        "sign_test_p": sign_test(d, u),
        "confident_downgrades_p>=0.2": len(conf),
        "mean_tier_shift": round(sum(ms) / len(ms), 4) if ms else None,
    }

# Cross-model concordance: do the models downgrade on the SAME phrases?
# Correlated downgrades point at the language; uncorrelated ones at the model.
by_phrase = {}
for r in rows:
    by_phrase.setdefault((r["batch"], r["index"]), {})[r["model"]] = r
multi = {k: v for k, v in by_phrase.items() if len(v) >= 2}
conc = {
    "phrases_measured_by_2plus_models": len(multi),
    "downgrade_on_any_model": 0, "downgrade_on_2plus_models": 0,
    "flip_on_2plus_models": 0,
    "pairwise_downgrade_overlap": {},
}
for k, v in multi.items():
    dg = [m for m, r in v.items() if r["flip_class"] == "downgrade"]
    fl = [m for m, r in v.items() if r["flipped"]]
    if dg:
        conc["downgrade_on_any_model"] += 1
    if len(dg) >= 2:
        conc["downgrade_on_2plus_models"] += 1
    if len(fl) >= 2:
        conc["flip_on_2plus_models"] += 1
models_seen = sorted({r["model"] for r in rows})
for i, a in enumerate(models_seen):
    for b in models_seen[i + 1:]:
        both = [v for v in multi.values() if a in v and b in v]
        da = {id(v) for v in both if v[a]["flip_class"] == "downgrade"}
        db = {id(v) for v in both if v[b]["flip_class"] == "downgrade"}
        union = da | db
        conc["pairwise_downgrade_overlap"][f"{a} & {b}"] = {
            "phrases": len(both), "either": len(union), "both": len(da & db),
            "jaccard": round(len(da & db) / len(union), 3) if union else None,
        }
summary["concordance"] = conc

# Per-condition breakdown: where do the downgrades live?
by_topic = {}
for r in rows:
    t = r.get("topic") or "(unlabeled)"
    by_topic.setdefault(t, []).append(r)
translated = [r for r in rows if r.get("urgency_recovery") is not None]
if translated:
    summary["mitigation"] = {
        "n": len(translated),
        "mean_urgency_recovery": round(sum(r["urgency_recovery"] for r in translated)
                                       / len(translated), 4),
        "restored_top_tier": sum(1 for r in translated
                                 if (r.get("tier_top_translated") or -1) >= (r.get("tier_top_clinical") or 0)),
    }

summary["per_condition"] = {}
for t, tr in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
    ts = [r["tier_shift"] for r in tr if r["tier_shift"] is not None]
    summary["per_condition"][t] = {
        "n": len(tr),
        "downgrades": sum(1 for r in tr if r["flip_class"] == "downgrade"),
        "upgrades": sum(1 for r in tr if r["flip_class"] == "upgrade"),
        "mean_tier_shift": round(sum(ts) / len(ts), 4) if ts else None,
    }

Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n",
                          encoding="utf-8")
if args.publish:
    vocab_meta = json.loads(Path(args.tiers).read_text(encoding="utf-8"))
    trimmed = [{k: r.get(k) for k in ("batch", "index", "model", "tier_top_clinical",
                                      "tier_top_patient", "flip_class", "tier_shift",
                                      "urgency_recovery")}
               for r in rows if r["flipped"] or r.get("tier_shift") is not None]
    # measured example words per tier, so the site can explain the tiers in
    # plain language without linking readers to a data file; base model only,
    # readable whole-word tokens, most frequent first. Wordpiece fragments are
    # excluded via the vocabulary's own review notes (data-driven, no
    # vocabulary in source).
    vocab_tokens = vocab_meta.get("tokens", {})
    tier_counts: dict = {}
    for r in rows:
        if r.get("model") != "gemma-2-2b":
            continue
        for tok_key, tier_key in (("top_clinical", "tier_top_clinical"),
                                  ("top_patient", "tier_top_patient")):
            tok, tr_ = r.get(tok_key), r.get(tier_key)
            if tr_ is None or not isinstance(tok, str):
                continue
            tok = tok.strip()
            if len(tok) < 3 or not tok.replace("-", "").isalpha():
                continue
            note = (vocab_tokens.get(tok) or {}).get("note", "")
            if "fragment" in note:
                continue
            tier_counts.setdefault(str(tr_), {})
            tier_counts[str(tr_)][tok] = tier_counts[str(tr_)].get(tok, 0) + 1
    tier_examples = {t: [w for w, _ in sorted(c.items(), key=lambda kv: -kv[1])[:3]]
                     for t, c in tier_counts.items()}
    site_payload = {
        "vocabulary_status": vocab_meta.get("status", "draft pending domain review"),
        "tiers": vocab_meta.get("tiers"),
        "tier_examples": tier_examples,
        "summary": {k: summary[k] for k in ("measurements", "flips", "flip_classes",
                                            "per_model", "concordance", "mitigation")
                    if k in summary},
        "rows": trimmed,
    }
    site_path = Path(args.publish) / "data/urgency_shift.json"
    site_path.write_text(json.dumps(site_payload, indent=1) + "\n", encoding="utf-8")
    print(f"site copy -> {site_path} ({len(trimmed)} rows)")
print(json.dumps(summary, indent=1))
print(f"\nDowngrade flips ({len(down)}), most confident first:")
for r in sorted(down, key=lambda r: -(r["p_top_patient"] or 0))[:20]:
    print(f"  [{r['model']}] {r['batch']}#{r['index']}: "
          f"{r['top_clinical']!r}(t{r['tier_top_clinical']}, p={r['p_top_clinical']}) -> "
          f"{r['top_patient']!r}(t{r['tier_top_patient']}, p={r['p_top_patient']}) | "
          f"{(r['clinical_prompt'] or '')[:52]}")
print(f"-> {args.out}")
