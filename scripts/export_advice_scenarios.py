"""Export the advice-arm archive into the site payload for the LLM responses page.

Reads a stimuli file plus its hash-chained responses archive (and, when present,
the judgments file) from data/advice/, and writes data/advice_scenarios.json —
the contract the frontend page llm/index.html renders: per scenario, the clinical
wording with every model's response beneath it, then the patient wording with the
same models' responses, then (when the translation arm ran) the machine-translated
wording and its responses. One displayed sample per (scenario, wording, model);
the archive keeps all K.

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
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_advice_eval():
    path = Path(__file__).resolve().parent / "advice_eval.py"
    spec = importlib.util.spec_from_file_location("advice_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _refuse(reason: str) -> "SystemExit":
    print(f"refused: {reason} (site file left untouched)")
    return SystemExit(3)


def build_payload(stimuli_path: Path, ae, sample_k: int = 1, max_scenarios: int = 0,
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

    # one displayed record per (stimulus, arm, model): prefer sample_k, else lowest k
    cells: dict[tuple, dict] = {}
    kmax: dict[tuple, int] = {}
    for r in advice:
        key = (r["stimulus_id"], r["arm"], r["model_requested"])
        kmax[key] = max(kmax.get(key, 0), r.get("sample_k") or 0)
        cur = cells.get(key)
        if cur is None or (r.get("sample_k") == sample_k and cur.get("sample_k") != sample_k) \
                or (cur.get("sample_k") != sample_k and (r.get("sample_k") or 9e9) < (cur.get("sample_k") or 9e9)):
            cells[key] = r

    def resp_entry(r: dict, key: tuple) -> dict:
        judged = tiers.get(r.get("response_sha256"))
        return {
            "model": r.get("model_requested"),
            "provider": r.get("provider"),
            "text": r.get("response_text"),
            "tier": judged.get("tier") if judged else None,
            "refusal": bool((judged.get("flags") or {}).get("refusal")) if judged else None,
            "sample_k": r.get("sample_k"),
            "n_samples": kmax.get(key),
            "sent_utc": r.get("sent_utc"),
            "model_returned": r.get("model_returned"),
        }

    model_order: list[str] = []
    for r in advice:
        if r["model_requested"] not in model_order:
            model_order.append(r["model_requested"])

    scenarios = []
    for item in stimuli_doc.get("items", []):
        sid = item["id"]
        def arm_block(arm: str, message: str | None):
            responses = []
            for spec in model_order:
                r = cells.get((sid, arm, spec))
                if r is not None:
                    responses.append(resp_entry(r, (sid, arm, spec)))
            if not responses and message is None:
                return None
            return {"message": message, "responses": responses}

        clinical = arm_block("clinical", item.get("clinical_message"))
        patient = arm_block("patient", item.get("patient_message"))
        translated_cells = [cells[k] for k in cells if k[0] == sid and k[1] == "translated"]
        translated = None
        if translated_cells:
            t_msg = (translated_cells[0].get("request") or {}).get("message")
            translated = arm_block("translated", t_msg)
        if not any(b and b["responses"] for b in (clinical, patient, translated)):
            continue  # stimulus never elicited (offset/limit chunking) — skip, don't blank
        scenarios.append({
            "id": sid,
            "topic": (item.get("meta") or {}).get("topic"),
            "clinical": clinical,
            "patient": patient,
            "translated": translated,
        })
        if max_scenarios and len(scenarios) >= max_scenarios:
            break

    if not scenarios:
        raise _refuse("no stimulus has any archived responses")

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.is_file() else {}
    sent = sorted(r["sent_utc"] for r in advice if r.get("sent_utc"))
    per_model_counts: dict[str, int] = {}
    for r in advice:
        per_model_counts[r["model_requested"]] = per_model_counts.get(r["model_requested"], 0) + 1
    returned: dict[str, str] = {}
    for r in advice:
        if r.get("model_returned") and r["model_requested"] not in returned:
            returned[r["model_requested"]] = r["model_returned"]
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
            "samples_per_cell": sidecar.get("samples") or (statistics.mode(kmax.values()) if kmax else None),
            "temperature": sidecar.get("temperature"),
            "models": [{"spec": spec, "provider": spec.split(":", 1)[0],
                        "model_returned": returned.get(spec),
                        "n_responses": per_model_counts.get(spec, 0)} for spec in model_order],
        },
        "chain_head": sidecar.get("chain_head") or (rows[-1]["record_sha256"] if rows else None),
        "rubric_version": rubric_version,
        "tier_order": None,  # filled from the rubric when judgments exist (see main)
        "scenarios": scenarios,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stimuli", required=True)
    parser.add_argument("--sample-k", type=int, default=1,
                        help="which sample to display per cell (archive keeps all K)")
    parser.add_argument("--max-scenarios", type=int, default=0)
    parser.add_argument("--archive-url", default=None,
                        help="GitHub Release URL for the full archive, if one exists")
    parser.add_argument("--rubric", default="data/advice_rubric.json",
                        help="rubric path, used only to publish tier_order when judgments exist")
    parser.add_argument("--out", default="data/advice_scenarios.json")
    parser.add_argument("--site", default=None, help="frontend checkout; copies the payload into <site>/data/")
    args = parser.parse_args(argv)

    ae = _load_advice_eval()
    payload = build_payload(Path(args.stimuli), ae, args.sample_k, args.max_scenarios, args.archive_url)
    if payload["rubric_version"] and Path(args.rubric).is_file():
        rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
        payload["tier_order"] = [t["id"] for t in rubric.get("tiers", [])] or None

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
