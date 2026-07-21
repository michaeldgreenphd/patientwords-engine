"""Embed the pages' runtime joins into the payload at publish time (audit M2+M3).

The scenario table and start-here JS join urgency rows and lens depth classes
onto scenarios at load time; failures degrade silently to em-dashes, and the
redirect gallery re-derives "most consequential" with its own scoring and a
vocabulary blocklist hardcoded in page JS. This post-collector pass moves all
of that into the data, matching the verified page semantics exactly
(docs/audits/m123_verified_specs_20260721.json):

- scenario.models[<m>].urgency = {flip_class, tier_top_clinical,
  tier_top_patient, tier_shift, urgency_recovery?} joined on the urgency row
  key (batch, index, model) — the row-side field is ``index``, the
  scenario-side is ``batch_index``; base model mirrored at scenario.urgency.
- scenario.depth_class from the depth payload's blocks (key block.id + pair
  index; no model in the key) + payload.depth_model gate for the pages.
- payload.urgency_meta = {vocabulary_status, tiers, per_model_deduped?}.
- payload.featured.redirect_gallery: the gallery's exact candidate filter,
  score ((tier_drop)*100 + clean*40 + patient_top_prob*10, untiered patient
  top = half a tier below 0), diversity caps (<=2 per patient answer, <=1 per
  clinical answer), N=6 — with the token-clean test driven by
  data/display_vocab.json (vocabulary lives in data, never in this file).

Runs AFTER urgency_shift --publish (and the depth exporter) in the publish
chain; idempotent; refuses (payload untouched) when the payload is absent.
No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

URGENCY_FIELDS = ("flip_class", "tier_top_clinical", "tier_top_patient", "tier_shift")
GALLERY_N = 6
CLEAN_BONUS = 40
UNTIERED_PATIENT = -0.5


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def urgency_obj(row: dict) -> dict:
    obj = {k: row.get(k) for k in URGENCY_FIELDS}
    if isinstance(row.get("urgency_recovery"), (int, float)):
        obj["urgency_recovery"] = row["urgency_recovery"]
    return obj


def embed_urgency(payload: dict, urg: dict, base_model: str) -> int:
    rows = {(r.get("batch"), r.get("index"), r.get("model")): r
            for r in urg.get("rows", [])}
    embedded = 0
    for s in payload.get("scenarios", []):
        for m in list((s.get("models") or {})):
            row = rows.get((s.get("batch"), s.get("batch_index"), m))
            if row:
                s["models"][m]["urgency"] = urgency_obj(row)
                embedded += 1
                if m == base_model:
                    s["urgency"] = s["models"][m]["urgency"]
    summary = urg.get("summary") or {}
    meta = {}
    for key in ("vocabulary_status", "tiers", "per_model_deduped"):
        if key in summary:
            meta[key] = summary[key]
        elif key in urg:
            meta[key] = urg[key]
    if meta:
        payload["urgency_meta"] = meta
    return embedded


def embed_depth(payload: dict, depth: dict) -> int:
    classes = {}
    for block in depth.get("blocks", []):
        for u in block.get("pairs") or []:
            if u.get("index") is not None and u.get("class"):
                classes[(block.get("id"), u["index"])] = u["class"]
    embedded = 0
    for s in payload.get("scenarios", []):
        cls = classes.get((s.get("batch"), s.get("batch_index")))
        if cls:
            s["depth_class"] = cls
            embedded += 1
    if depth.get("model"):
        payload["depth_model"] = depth["model"]
    return embedded


def token_clean(token, vocab: dict):
    """The gallery's clean-token test: shape regex + data-driven blocklist."""
    t = str(token or "").strip()
    if not re.match(r"^[A-Za-z][A-Za-z'’-]{2,}$", t):
        return False
    return t.lower() not in {w.lower() for w in vocab.get("fragment_blocklist", [])}


def redirect_gallery(payload: dict, urg: dict, vocab: dict, base_model: str) -> list[dict]:
    by_key = {(s.get("batch"), s.get("batch_index")): s
              for s in payload.get("scenarios", [])}
    candidates = []
    for u in urg.get("rows", []):
        if u.get("model") != base_model or u.get("flip_class") != "downgrade":
            continue
        if not isinstance(u.get("tier_top_clinical"), (int, float)):
            continue
        s = by_key.get((u.get("batch"), u.get("index")))
        if not s or not s.get("spread_clinical") or not s.get("spread_patient"):
            continue
        ct = s["spread_clinical"][0][0]
        pt, pp_raw = s["spread_patient"][0][0], s["spread_patient"][0][1]
        pp = pp_raw if isinstance(pp_raw, (int, float)) else 0
        pat_t = u["tier_top_patient"] if isinstance(u.get("tier_top_patient"), (int, float)) \
            else UNTIERED_PATIENT
        clean = token_clean(ct, vocab) and token_clean(pt, vocab)
        tier_drop = u["tier_top_clinical"] - pat_t
        score = tier_drop * 100 + (CLEAN_BONUS if clean else 0) + pp * 10
        candidates.append({
            "batch": s.get("batch"), "batch_index": s.get("batch_index"),
            "model": base_model, "score": round(score, 4),
            "components": {"tier_drop": tier_drop,
                           "clean_bonus": CLEAN_BONUS if clean else 0,
                           "patient_top_prob": pp},
            # diversity keys mirror the page: lowercased, NOT trimmed
            "_pt": str(pt).lower(), "_ct": str(ct).lower(),
            "_order": s.get("index") if isinstance(s.get("index"), int) else 10**9,
        })
    candidates.sort(key=lambda c: (-c["score"], c["_order"]))
    picks, pt_count, ct_count = [], {}, {}
    for c in candidates:
        if len(picks) >= GALLERY_N:
            break
        if pt_count.get(c["_pt"], 0) >= 2 or ct_count.get(c["_ct"], 0) >= 1:
            continue
        pt_count[c["_pt"]] = pt_count.get(c["_pt"], 0) + 1
        ct_count[c["_ct"]] = ct_count.get(c["_ct"], 0) + 1
        c = {k: v for k, v in c.items() if not k.startswith("_")}
        c["rank"] = len(picks) + 1
        picks.append(c)
    return picks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="../patientwords")
    parser.add_argument("--base-model", default="gemma-2-2b")
    args = parser.parse_args(argv)

    data = Path(args.site) / "data"
    payload_path = data / "simulated_scenarios.json"
    payload = load_json(payload_path)
    if not payload or not payload.get("scenarios"):
        print(f"refused: no payload at {payload_path} - nothing touched")
        return 3

    urg = load_json(data / "urgency_shift.json")
    depth = load_json(data / "jlens_depth.json")
    vocab = load_json(data / "display_vocab.json") or {}

    n_urg = embed_urgency(payload, urg, args.base_model) if urg else 0
    n_depth = embed_depth(payload, depth) if depth else 0
    gallery = redirect_gallery(payload, urg, vocab, args.base_model) if urg else []
    if gallery:
        payload.setdefault("featured", {})["redirect_gallery"] = gallery

    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"embedded: {n_urg} urgency joins, {n_depth} depth classes, "
          f"{len(gallery)} gallery picks"
          + ("" if vocab else " (display_vocab.json absent: no clean bonuses)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
