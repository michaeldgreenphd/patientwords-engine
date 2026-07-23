"""Export the advice-arm archive into the site payload for the LLM responses page.

Reads a stimuli file plus its hash-chained responses archive (and, when present,
the judgments file) from data/advice/, and writes data/advice_scenarios.json —
the contract the frontend page llm/index.html renders: per scenario, the clinical
wording with every model's response beneath it, then the patient wording with the
same models' responses, then (when the translation arm ran) the machine-translated
wording and its responses. Every sample per (scenario, wording, model) is
published — the page pairs its scenario pager with an attempt switcher.

Safety properties, matching the other site exporters:
- verifies the archive hash chain first and REFUSES (exit 3, site file untouched)
  on any break — a tampered or truncated archive can never reach the site;
- refuses when there are no advice records (a partial cycle cannot blank the page);
- publishes response text, tiers, and run metadata only — never judge raw output,
  never provider API keys (none exist in the archive), never stimuli meta beyond
  the topic label;
- stimuli built from the published payload are Tier B holdout-safe by construction
  (the payload withholds sealed rows upstream); pairs-sourced stimuli were already
  filtered by tierb_split at build time.

Usage:
  python scripts/export_advice_scenarios.py \
      --stimuli data/advice/stimuli_<STAMP>.json \
      [--sample-k 1] [--max-scenarios 0] [--archive-url <release url>] \
      --out data/advice_scenarios.json --site ../patientwords
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# One display row per model family when a provider's arm changed access path mid-run
# (pre-registration access amendments name each reroute). Keys are the rerouted spec,
# values the family's canonical display spec. Provenance (run.models) always lists the
# raw per-path specs; only scenario rows merge.
DISPLAY_ALIASES = {
    "openrouter:google/gemini-3.5-flash": "google:gemini-3.5-flash",  # AI Studio daily quota reroute, 2026-07-22
}


def _load_advice_eval():
    path = Path(__file__).resolve().parent / "advice_eval.py"
    spec = importlib.util.spec_from_file_location("advice_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _refuse(reason: str) -> "SystemExit":
    print(f"refused: {reason} (site file left untouched)")
    return SystemExit(3)


def build_payload(stimuli_path: Path, ae, max_scenarios: int = 0,
                  archive_url: str | None = None) -> dict:
    stimuli_doc = json.loads(stimuli_path.read_text(encoding="utf-8"))
    stem = stimuli_path.stem
    adv_dir = stimuli_path.parent
    responses_path = adv_dir / f"responses_{stem}.jsonl"
    judgments_path = adv_dir / f"judgments_{stem}.jsonl"
    sidecar_path = adv_dir / f"responses_{stem}.report.json"

    rows = ae._read_jsonl(responses_path)
    ok, msg = ae.verify_chain(rows)
    if not ok:
        raise _refuse(f"{responses_path}: {msg}")
    advice = [r for r in rows if r.get("record_type") == "advice"]
    if not advice:
        raise _refuse(f"{responses_path}: no advice records")

    tiers: dict[str, dict] = {}
    rubric_version = None
    if judgments_path.is_file():
        for j in ae._read_jsonl(judgments_path):
            if j.get("tier") is not None:
                tiers[j["response_sha256"]] = j  # later passes overwrite earlier ones
                rubric_version = j.get("rubric_version") or rubric_version

    # ALL samples per (stimulus, arm, model), sorted by attempt number — the page
    # carries an attempt switcher, so every draw is published, not a chosen one.
    # Display aliasing: google's arm was rerouted to OpenRouter mid-pilot when the direct
    # AI Studio free tier hit its daily quota (pre-registration access amendment,
    # 2026-07-22). Records keep the exact spec they were elicited under; for display the
    # two access paths are one model row, joined as the analysis joins them. A (stimulus,
    # arm, k) cell elicited under both paths keeps the direct-path record; each published
    # sample still carries its own model_returned, so the serving path stays visible.
    cells: dict[tuple, list] = {}
    for r in advice:
        spec = DISPLAY_ALIASES.get(r["model_requested"], r["model_requested"])
        cells.setdefault((r["stimulus_id"], r["arm"], spec), []).append(r)
    for key, recs in cells.items():
        display_spec = key[2]
        recs.sort(key=lambda r: ((r.get("sample_k") or 0),
                                 r["model_requested"] != display_spec,  # direct path wins the tie
                                 r.get("sent_utc") or ""))
        seen_k: set = set()
        deduped = []
        for r in recs:
            if r.get("sample_k") in seen_k:
                continue
            seen_k.add(r.get("sample_k"))
            deduped.append(r)
        cells[key] = deduped

    def sample_entry(r: dict) -> dict:
        judged = tiers.get(r.get("response_sha256"))
        return {
            "k": r.get("sample_k"),
            "text": r.get("response_text"),
            "tier": judged.get("tier") if judged else None,
            "refusal": bool((judged.get("flags") or {}).get("refusal")) if judged else None,
            "sent_utc": r.get("sent_utc"),
            "model_returned": r.get("model_returned"),
        }

    def model_block(spec: str, recs: list) -> dict:
        return {
            "model": spec,
            "provider": spec.split(":", 1)[0],
            "model_returned": next((r.get("model_returned") for r in recs if r.get("model_returned")), None),
            "samples": [sample_entry(r) for r in recs],
        }

    model_order: list[str] = []
    for r in advice:
        spec = DISPLAY_ALIASES.get(r["model_requested"], r["model_requested"])
        if spec not in model_order:
            model_order.append(spec)

    scenarios = []
    for item in stimuli_doc.get("items", []):
        sid = item["id"]
        def arm_block(arm: str, message: str | None):
            responses = []
            for spec in model_order:
                recs = cells.get((sid, arm, spec))
                if recs:
                    responses.append(model_block(spec, recs))
            if not responses and message is None:
                return None
            return {"message": message, "responses": responses}

        clinical = arm_block("clinical", item.get("clinical_message"))
        patient = arm_block("patient", item.get("patient_message"))
        translated_recs = [recs for key, recs in cells.items() if key[0] == sid and key[1] == "translated"]
        translated = None
        if translated_recs:
            t_msg = (translated_recs[0][0].get("request") or {}).get("message")
            translated = arm_block("translated", t_msg)
        if not any(b and b["responses"] for b in (clinical, patient, translated)):
            continue  # stimulus never elicited (offset/limit chunking) — skip, don't blank
        # per-model judged tier counts for this scenario, both arms — main() reduces
        # these to modal tiers + downgrade flags once the rubric's tier order is known
        tc: dict[str, dict] = {}
        for spec in model_order:
            per_arm = {}
            for arm in ("clinical", "patient"):
                counts: dict[str, int] = {}
                for r in cells.get((sid, arm, spec), []):
                    judged = tiers.get(r.get("response_sha256"))
                    if judged and judged.get("tier"):
                        counts[judged["tier"]] = counts.get(judged["tier"], 0) + 1
                if counts:
                    per_arm[arm] = counts
            if len(per_arm) == 2:
                tc[spec] = per_arm
        scenarios.append({
            "id": sid,
            "topic": (item.get("meta") or {}).get("topic"),
            "wording_gap": None,  # joined in main from the next-token payload when available
            "tier_counts_by_model": tc or None,
            "clinical": clinical,
            "patient": patient,
            "translated": translated,
        })
        if max_scenarios and len(scenarios) >= max_scenarios:
            break

    if not scenarios:
        raise _refuse("no stimulus has any archived responses")

    # Per-model figure block: mechanical measures now (n, mean words), coded-tier
    # aggregates whenever judgments exist. Clinician re-grades re-enter through the
    # judgments file, so re-running this exporter moves the published figure.
    def _arm_stats(spec: str, arm: str) -> dict:
        words: list[int] = []
        tier_counts: dict[str, int] = {}
        flag_counts: dict[str, int] = {}
        n_judged = 0
        for (_sid, a, sp), recs in cells.items():
            if a != arm or sp != spec:
                continue
            for r in recs:
                text = r.get("response_text") or ""
                if text:
                    words.append(len(text.split()))
                judged = tiers.get(r.get("response_sha256"))
                if judged and judged.get("tier"):
                    tier_counts[judged["tier"]] = tier_counts.get(judged["tier"], 0) + 1
                    n_judged += 1
                    fl = judged.get("flags") or {}
                    for k, v in fl.items():
                        if v:
                            flag_counts[k] = flag_counts.get(k, 0) + 1
                    # derived interaction patterns (owner direction 2026-07-23):
                    # probing en route to a referral vs probing instead of advising
                    if fl.get("clarifying_question") and fl.get("professional_referral"):
                        flag_counts["question_then_referral"] = flag_counts.get("question_then_referral", 0) + 1
                    if fl.get("clarifying_question") and fl.get("refusal"):
                        flag_counts["question_no_advice"] = flag_counts.get("question_no_advice", 0) + 1
        return {
            "n": len(words),
            "mean_words": round(sum(words) / len(words)) if words else None,
            "tier_counts": tier_counts or None,
            "tier_mean_rank": None,  # filled in main once the rubric's tier order is known
            "n_judged": n_judged,
            "flag_rates": {k: round(c / n_judged, 3) for k, c in sorted(flag_counts.items())} if n_judged else None,
        }

    # Answer stability vs wording: per model, mean pairwise word-set overlap
    # (Jaccard) between attempts at the IDENTICAL wording (the model's natural
    # variation) and between the clinical and patient wordings of the same
    # stimulus. Purely mechanical - lowercased [a-z'] word sets, no vocabulary,
    # no grading. If re-wording moves the answer more than re-asking does, the
    # wording itself changed the advice.
    def _wordset(text: str) -> frozenset:
        return frozenset(re.findall(r"[a-z']+", text.lower()))

    def _jaccard(a: frozenset, b: frozenset) -> float | None:
        u = a | b
        return len(a & b) / len(u) if u else None

    def _similarity(spec: str) -> dict | None:
        within: list[float] = []
        between: list[float] = []
        stim_ids = set()
        for (sid, _a, sp), _recs in cells.items():
            if sp == spec:
                stim_ids.add(sid)
        for sid in stim_ids:
            sets = {}
            for arm in ("clinical", "patient"):
                sets[arm] = [_wordset(r["response_text"])
                             for r in cells.get((sid, arm, spec), []) if r.get("response_text")]
            for arm in ("clinical", "patient"):
                s = sets[arm]
                for i in range(len(s)):
                    for j in range(i + 1, len(s)):
                        v = _jaccard(s[i], s[j])
                        if v is not None:
                            within.append(v)
            for a in sets["clinical"]:
                for b in sets["patient"]:
                    v = _jaccard(a, b)
                    if v is not None:
                        between.append(v)
        if not within or not between:
            return None
        return {"reasked": round(sum(within) / len(within), 3),
                "reworded": round(sum(between) / len(between), 3),
                "n_stimuli": len(stim_ids)}

    model_summary = [{"model": spec,
                      "clinical": _arm_stats(spec, "clinical"),
                      "patient": _arm_stats(spec, "patient"),
                      "similarity": _similarity(spec)}
                     for spec in model_order]

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.is_file() else {}
    sent = sorted(r["sent_utc"] for r in advice if r.get("sent_utc"))
    # provenance stays per access path: raw specs, never display aliases
    raw_order: list[str] = []
    per_model_counts: dict[str, int] = {}
    for r in advice:
        if r["model_requested"] not in raw_order:
            raw_order.append(r["model_requested"])
        per_model_counts[r["model_requested"]] = per_model_counts.get(r["model_requested"], 0) + 1
    returned: dict[str, str] = {}
    for r in advice:
        if r.get("model_returned") and r["model_requested"] not in returned:
            returned[r["model_requested"]] = r["model_returned"]
    # A3 (2026-07-23): every DISTINCT served build per spec - (model_returned,
    # build_fingerprint) with its first/last sent window - so the page can show
    # exactly which vendor builds produced the archive, and the drift sentinel
    # can diff weeks. Old records lack build_fingerprint; they aggregate as null.
    builds_by_spec: dict[str, dict] = {}
    for r in advice:
        spec = r["model_requested"]
        key = (r.get("model_returned"), r.get("build_fingerprint"))
        b = builds_by_spec.setdefault(spec, {}).setdefault(key, {
            "model_returned": r.get("model_returned"),
            "build_fingerprint": r.get("build_fingerprint"),
            "n": 0, "first_sent_utc": None, "last_sent_utc": None})
        b["n"] += 1
        su = r.get("sent_utc")
        if su:
            if b["first_sent_utc"] is None or su < b["first_sent_utc"]:
                b["first_sent_utc"] = su
            if b["last_sent_utc"] is None or su > b["last_sent_utc"]:
                b["last_sent_utc"] = su
    cost = sidecar.get("cost_usd")
    n_scenario_ids = len({r["stimulus_id"] for r in advice})

    return {
        "generated_utc": ae.utc_now_iso(),
        "engine_sha": ae.engine_sha(),
        "source": {
            "stimuli_file": str(stimuli_path).replace(str(REPO_ROOT) + "/", ""),
            "responses_file": str(responses_path).replace(str(REPO_ROOT) + "/", ""),
            "judgments_file": str(judgments_path).replace(str(REPO_ROOT) + "/", "")
                              if judgments_path.is_file() else None,
            "archive_url": archive_url,
        },
        "run": {
            "first_sent_utc": sent[0] if sent else None,
            "last_sent_utc": sent[-1] if sent else None,
            "n_calls": len(rows),
            "cost_usd": cost,
            "cost_per_scenario": round(cost / n_scenario_ids, 4)
                                 if isinstance(cost, (int, float)) and n_scenario_ids else None,
            "samples_per_cell": sidecar.get("samples")
                                or (max((len(recs) for recs in cells.values()), default=None)),
            "temperature": sidecar.get("temperature"),
            "models": [{"spec": spec, "provider": spec.split(":", 1)[0],
                        "model_returned": returned.get(spec),
                        "n_responses": per_model_counts.get(spec, 0),
                        "builds": sorted(builds_by_spec.get(spec, {}).values(),
                                         key=lambda b: (b["first_sent_utc"] or ""))} for spec in raw_order],
        },
        "chain_head": sidecar.get("chain_head") or (rows[-1]["record_sha256"] if rows else None),
        "rubric_version": rubric_version,
        "tier_order": None,  # filled from the rubric when judgments exist (see main)
        "model_summary": model_summary,
        "scenarios": scenarios,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stimuli", required=True)
    parser.add_argument("--max-scenarios", type=int, default=0)
    parser.add_argument("--archive-url", default=None,
                        help="GitHub Release URL for the full archive, if one exists")
    parser.add_argument("--rubric", default="data/advice_rubric.json",
                        help="rubric path, used only to publish tier_order when judgments exist")
    parser.add_argument("--out", default="data/advice_scenarios.json")
    parser.add_argument("--site", default=None, help="frontend checkout; copies the payload into <site>/data/")
    args = parser.parse_args(argv)

    ae = _load_advice_eval()
    payload = build_payload(Path(args.stimuli), ae, args.max_scenarios, args.archive_url)
    if payload["rubric_version"] and Path(args.rubric).is_file():
        rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
        payload["tier_order"] = [t["id"] for t in rubric.get("tiers", [])] or None
    if payload["tier_order"]:
        ranks = {t: i + 1 for i, t in enumerate(payload["tier_order"])}
        for m in payload["model_summary"]:
            for arm in ("clinical", "patient"):
                tc = m[arm].get("tier_counts")
                if tc:
                    total = sum(tc.values())
                    m[arm]["tier_mean_rank"] = round(
                        sum(ranks.get(t, 0) * c for t, c in tc.items()) / total, 2)

        def modal(counts: dict) -> str:
            # ties break toward the more urgent tier - the safety-conservative reading
            return max(counts, key=lambda t: (counts[t], ranks.get(t, 0)))

        for s in payload["scenarios"]:
            tcbm = s.get("tier_counts_by_model")
            if not tcbm:
                continue
            summary = []
            for spec, per_arm in tcbm.items():
                c, p = modal(per_arm["clinical"]), modal(per_arm["patient"])
                drop = ranks.get(c, 0) - ranks.get(p, 0)  # positive = patient coded less urgent
                summary.append({"model": spec, "clinical": c, "patient": p,
                                "drop": drop, "downgrade": drop > 0})
            s["tier_summary"] = summary

    # join the next-token wording gap per scenario (id = "<batch>#<index>") from the
    # simulated payload, so the site can plot advice drops against the token-level gap
    site_payload = None
    for cand in ([Path(args.site) / "data" / "simulated_scenarios.json"] if args.site else []) + \
                [REPO_ROOT.parent / "patientwords" / "data" / "simulated_scenarios.json"]:
        if Path(cand).is_file():
            site_payload = json.loads(Path(cand).read_text(encoding="utf-8"))
            break
    if site_payload:
        gaps = {}
        for sc in site_payload.get("scenarios", []):
            if sc.get("batch") is not None and sc.get("batch_index") is not None:
                gaps[f"{sc['batch']}#{sc['batch_index']}"] = sc.get("language_penalty")
        for s in payload["scenarios"]:
            if s["id"] in gaps:
                s["wording_gap"] = gaps[s["id"]]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(payload['scenarios'])} scenarios -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "advice_scenarios.json"
        site_copy.parent.mkdir(parents=True, exist_ok=True)
        site_copy.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"site copy -> {site_copy}")


if __name__ == "__main__":
    main()
