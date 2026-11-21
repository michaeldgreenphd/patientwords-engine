#!/usr/bin/env python3
"""Deterministic assembler & engine-gate runner for the Slang & Everyday-Question Stress Pack.

Compiles per-batch / per-seed drafts in `drafts/slang_stress_20261120/` into:
  - `next_token/candidates.json` & `next_token/sources.md`
  - `advice/manual_vignettes.json` & `advice/sources.md`
  - `petri/petri_seeds_slang.draft.json`, `petri/lay_careful_swaps_slang.draft.json`, & `petri/sources.md`

Performs a two-pass byte-for-byte SHA-256 deterministic rebuild verification, and with
`--run-engine-gates` executes the official offline engine validators and holdout-seal
scans, writing:
  - `next_token/check_report.json`
  - `advice/build_dryrun_report.json`
  - `petri/validate_seeds_report.json`

Usage:
  python3 drafts/slang_stress_20261120/tools/assemble_pack.py --lane all
  python3 drafts/slang_stress_20261120/tools/assemble_pack.py --lane all --require-audits --run-engine-gates
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_PACK_DIR = TOOLS_DIR.parent
ROOT = DEFAULT_PACK_DIR.parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import validate_pack as vp  # noqa: E402
from scripts.petri_audit import cli as petri_cli  # noqa: E402
from scripts.petri_audit import seal as petri_seal  # noqa: E402
from scripts.petri_audit import seeds as petri_seeds  # noqa: E402
from scripts.petri_audit.framework import canonical_json, load_json  # noqa: E402


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def rel_or_name(path: Path, pack_dir: Path | None = None) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        if pack_dir is not None:
            try:
                return path.resolve().relative_to(pack_dir.resolve()).as_posix()
            except ValueError:
                pass
        return path.name


def md_cell(val: Any) -> str:
    if val is None:
        return "—"
    text = str(val).replace("\r\n", " ").replace("\n", " ").strip()
    return text.replace("|", "\\|") if text else "—"


def _load_advice_eval_module() -> Any:
    name = "_slang_pack_advice_eval"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "advice_eval.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def scan_seeds(
    seed_set: petri_seeds.SeedSet,
    extra_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Run Petri holdout-seal verification over seed target-visible strings and assembled files."""
    registry = petri_seal.sealed_registry()
    if not registry:
        return {
            "status": "not_run",
            "sealed_phrases_checked": 0,
            "seed_text_hits_count": 0,
            "file_scan": {"status": "not_run", "detail": "sealed registry computed empty"},
            "ok": False,
        }
    strings = [s for seed in seed_set.seeds.values() for s in petri_seeds.target_visible_strings(seed)]
    if hasattr(petri_seal, "scan_seeds"):
        seed_hits = getattr(petri_seal, "scan_seeds")(seed_set, registry)  # pragma: no cover
    else:
        seed_hits = petri_seal.seed_texts_against_registry(strings, registry)
    paths_to_scan = [seed_set.path, *(extra_paths or [])]
    file_res = petri_seal.scan_paths(paths_to_scan, registry)
    ok = (len(seed_hits) == 0) and (file_res.status == "pass")
    return {
        "status": "pass" if ok else "fail",
        "sealed_phrases_checked": len(registry),
        "target_visible_strings_checked": len(strings),
        "seed_text_hits_count": len(seed_hits),
        "file_scan": file_res.as_check(),
        "ok": ok,
    }


def assemble_next_token(pack_dir: Path, plan: dict[str, Any] | None) -> list[Path]:
    lane_dir = pack_dir / "next_token"
    batches_dir = lane_dir / "batches"
    if plan and isinstance(plan.get("next_token"), list):
        batch_ids = sorted({str(e["batch"]) for e in plan["next_token"]})
    else:
        batch_ids = sorted(p.stem for p in batches_dir.glob("*.json"))

    all_items: list[dict[str, Any]] = []
    for bid in batch_ids:
        bpath = batches_dir / f"{bid}.json"
        batch_items = json.loads(bpath.read_text(encoding="utf-8"))
        all_items.extend(batch_items)
    all_items.sort(key=lambda x: str(x["id"]))

    candidates_out = lane_dir / "candidates.json"
    candidates_out.write_text(json.dumps(all_items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cat_counts = collections.Counter(str(it["trap_category"]) for it in all_items)
    tier_counts = collections.Counter(int(it["clinical_tier_expected"]) for it in all_items)
    stype_counts: collections.Counter[str] = collections.Counter()
    cited_items = 0
    rows_md: list[str] = []

    for it in all_items:
        cid = str(it["id"])
        cat = str(it["trap_category"])
        tier = str(it["clinical_tier_expected"])
        c_span = str((it.get("swap_spans") or {}).get("clinical_span", ""))
        p_span = str((it.get("swap_spans") or {}).get("patient_span", ""))
        ev_list = it.get("source_evidence") or []
        if any(ev.get("source_type") != "none" for ev in ev_list if isinstance(ev, dict)):
            cited_items += 1
        for ev in ev_list:
            stype = str(ev.get("source_type", ""))
            stype_counts[stype] += 1
            rows_md.append(
                f"| `{md_cell(cid)}` | `{md_cell(cat)}` | {md_cell(tier)} | {md_cell(c_span)} | "
                f"{md_cell(p_span)} | {md_cell(ev.get('expression'))} | `{md_cell(stype)}` | "
                f"{md_cell(ev.get('identifier'))} | {md_cell(ev.get('quote'))} |"
            )

    total_items = len(all_items)
    cited_share = f"{(cited_items / total_items * 100.0):.1f}%" if total_items else "0.0%"
    cat_summary = ", ".join(f"`{k}`: {cat_counts[k]}" for k in sorted(cat_counts))
    tier_summary = ", ".join(f"Tier {k}: {tier_counts[k]}" for k in sorted(tier_counts, reverse=True))
    stype_summary = ", ".join(f"`{k}`: {stype_counts[k]}" for k in sorted(stype_counts))

    md_lines = [
        "# Lane 1 (`next_token`) — Slang & Everyday-Question Stress Pack Provenance",
        "",
        "> **Status:** Exploratory synthetic stimulus drafts awaiting owner review, clinician review, and patient-language review. Zero `PMC` identifiers are used.",
        "",
        "## Summary",
        "",
        f"- **Total candidate pairs:** {total_items}",
        f"- **Pairs with external citation (`source_type != 'none'`):** {cited_items}/{total_items} ({cited_share})",
        f"- **By trap category:** {cat_summary}",
        f"- **By expected clinical tier:** {tier_summary}",
        f"- **Source evidence rows by type:** {stype_summary}",
        "",
        "## Source Evidence Table",
        "",
        "| ID | Category | Tier | Clinical Span | Patient Span | Expression | Source Type | Identifier | Quote / Evidence |",
        "|---|---|---:|---|---|---|---|---|---|",
        *rows_md,
        "",
    ]
    sources_md_out = lane_dir / "sources.md"
    sources_md_text = "\n".join(md_lines)
    if vp.PMC_RE.search(sources_md_text):
        raise ValueError("next_token/sources.md contains a forbidden PMC identifier")
    sources_md_out.write_text(sources_md_text, encoding="utf-8")
    return [candidates_out, sources_md_out]


def assemble_advice(pack_dir: Path, plan: dict[str, Any] | None) -> list[Path]:
    lane_dir = pack_dir / "advice"
    batches_dir = lane_dir / "batches"
    if plan and isinstance(plan.get("advice"), list):
        batch_ids = sorted({str(e["batch"]) for e in plan["advice"]})
    else:
        batch_ids = sorted(p.stem for p in batches_dir.glob("*.json"))

    all_items: list[dict[str, Any]] = []
    for bid in batch_ids:
        bpath = batches_dir / f"{bid}.json"
        batch_items = json.loads(bpath.read_text(encoding="utf-8"))
        all_items.extend(batch_items)
    all_items.sort(key=lambda x: str(x["id"]))

    manual_out = lane_dir / "manual_vignettes.json"
    manual_out.write_text(json.dumps(all_items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cat_counts = collections.Counter(str((it.get("notes") or {}).get("trap_category", "")) for it in all_items)
    tier_counts = collections.Counter(str((it.get("reference") or {}).get("tier", "")) for it in all_items)
    variant_counts = collections.Counter(str(it.get("variant", "")) for it in all_items)
    unique_situations = len({str(it.get("situation_id", "")) for it in all_items})
    stype_counts: collections.Counter[str] = collections.Counter()
    cited_items = 0
    rows_md: list[str] = []

    for it in all_items:
        cid = str(it["id"])
        sit = str(it.get("situation_id", ""))
        var = str(it.get("variant", ""))
        notes = it.get("notes") or {}
        cat = str(notes.get("trap_category", ""))
        tier = str((it.get("reference") or {}).get("tier", ""))
        p_span = str(notes.get("patient_span", ""))
        srcs = notes.get("sources") or []
        if any(s.get("source_type") != "none" for s in srcs if isinstance(s, dict)):
            cited_items += 1
        for src in srcs:
            stype = str(src.get("source_type", ""))
            stype_counts[stype] += 1
            rows_md.append(
                f"| `{md_cell(cid)}` | `{md_cell(sit)}` | `{md_cell(var)}` | `{md_cell(cat)}` | "
                f"`{md_cell(tier)}` | {md_cell(p_span)} | {md_cell(src.get('expression'))} | "
                f"`{md_cell(stype)}` | {md_cell(src.get('identifier'))} | {md_cell(src.get('quote'))} |"
            )

    total_items = len(all_items)
    cited_share = f"{(cited_items / total_items * 100.0):.1f}%" if total_items else "0.0%"
    cat_summary = ", ".join(f"`{k}`: {cat_counts[k]}" for k in sorted(cat_counts))
    tier_summary = ", ".join(f"`{k}`: {tier_counts[k]}" for k in sorted(tier_counts))
    var_summary = ", ".join(f"`{k}`: {variant_counts[k]}" for k in sorted(variant_counts))
    stype_summary = ", ".join(f"`{k}`: {stype_counts[k]}" for k in sorted(stype_counts))

    md_lines = [
        "# Lane 2 (`advice`) — Slang & Everyday-Question Stress Pack Provenance",
        "",
        "> **Status:** Exploratory manual advice vignettes awaiting owner review, clinician review, and patient-language review (`reference.basis` is non-claim-grade; no `adjudicated_by`). Zero `PMC` identifiers are used.",
        "",
        "## Summary",
        "",
        f"- **Total manual vignettes:** {total_items} across **{unique_situations}** unique `situation_id`s",
        f"- **Vignettes with external citation (`source_type != 'none'`):** {cited_items}/{total_items} ({cited_share})",
        f"- **By trap category:** {cat_summary}",
        f"- **By proposed reference tier:** {tier_summary}",
        f"- **By variant:** {var_summary}",
        f"- **Source rows by type:** {stype_summary}",
        "",
        "## Source Evidence Table",
        "",
        "| ID | Situation | Variant | Category | Tier | Patient Span | Expression | Source Type | Identifier | Quote / Evidence |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *rows_md,
        "",
    ]
    sources_md_out = lane_dir / "sources.md"
    sources_md_text = "\n".join(md_lines)
    if vp.PMC_RE.search(sources_md_text):
        raise ValueError("advice/sources.md contains a forbidden PMC identifier")
    sources_md_out.write_text(sources_md_text, encoding="utf-8")
    return [manual_out, sources_md_out]


def _merge_lexicon_entries(entries_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in entries_list:
        pair = (str(raw["clinical"]), str(raw["lay"]))
        if pair not in by_pair:
            by_pair[pair] = copy.deepcopy(raw)
        else:
            cur = by_pair[pair]
            seen_chv = {(lk["term"].lower(), lk["cui"]) for lk in cur.get("chv", [])}
            for lk in raw.get("chv", []):
                key = (lk["term"].lower(), lk["cui"])
                if key not in seen_chv:
                    cur.setdefault("chv", []).append(copy.deepcopy(lk))
                    seen_chv.add(key)
            if raw.get("not_in_chv"):
                merged_nic = sorted(
                    {*(t.strip() for t in cur.get("not_in_chv", [])), *(t.strip() for t in raw["not_in_chv"])}
                )
                cur["not_in_chv"] = merged_nic
            if raw.get("web_sources"):
                existing_ws = {canonical_json(w): w for w in cur.get("web_sources", [])}
                for w in raw["web_sources"]:
                    existing_ws.setdefault(canonical_json(w), copy.deepcopy(w))
                cur["web_sources"] = [existing_ws[k] for k in sorted(existing_ws)]

    merged: list[dict[str, Any]] = []
    for pair in sorted(by_pair.keys()):
        entry = by_pair[pair]
        ordered: dict[str, Any] = {
            "clinical": entry["clinical"],
            "lay": entry["lay"],
            "relation": entry["relation"],
            "chv": entry.get("chv", []),
        }
        if entry.get("not_in_chv"):
            ordered["not_in_chv"] = sorted({t.strip() for t in entry["not_in_chv"] if t.strip()})
        if entry.get("web_sources"):
            ordered["web_sources"] = entry["web_sources"]
        ordered["basis"] = entry["basis"]
        merged.append(ordered)
    return merged


def assemble_petri(pack_dir: Path, plan: dict[str, Any] | None) -> list[Path]:
    lane_dir = pack_dir / "petri"
    seeds_dir = lane_dir / "seeds"
    plan_by_seed: dict[str, dict[str, Any]] = {}
    if plan and isinstance(plan.get("petri"), list):
        for e in plan["petri"]:
            plan_by_seed[str(e["seed_id"])] = e
        seed_ids = sorted(plan_by_seed.keys())
    else:
        seed_ids = sorted(p.stem for p in seeds_dir.glob("*.json"))

    seed_docs = [json.loads((seeds_dir / f"{sid}.json").read_text(encoding="utf-8")) for sid in seed_ids]

    widened_schema = vp.widened_petri_seed_schema()
    w3_swaps_doc = load_json(vp.W3_SWAPS_PATH)

    seeds_out = lane_dir / "petri_seeds_slang.draft.json"
    swaps_out = lane_dir / "lay_careful_swaps_slang.draft.json"

    seeds_payload = {
        "schema_version": "0.1",
        "status": "draft pending owner review",
        "_readme": (
            "Exploratory slang & everyday-question stress-pack seed definitions for Petri-hosted, "
            "PatientWords-owned multi-turn experiments (drafts/slang_stress_20261120/SPEC.md). "
            "seed_schema is copied from docs/framework/petri_seeds_w3.draft.json with pilot_wave widened "
            "to [1, 2, 3, 4]. Every seed here carries pilot_wave 4, mode 'scripted', claim_grade_eligible true, "
            "ten user turns under sustained register exposure across clinical, lay_careful, and colloquial arms, "
            "constant speaker identity, and generation {temperature: 1.0, max_tokens: 4096, seed_requested: null}. "
            "Every lay_careful turn is mechanically derived from its clinical turn via the ordered replacements in "
            "lay_careful_swaps_slang.draft.json. All turn texts are newly authored synthetic examples awaiting "
            "owner review, clinician review, and patient-language review."
        ),
        "seed_schema": widened_schema,
        "seeds": [doc["seed"] for doc in seed_docs],
    }
    seeds_out.write_text(json.dumps(seeds_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    swaps_by_seed: dict[str, dict[str, Any]] = {}
    raw_lexicon: list[dict[str, Any]] = []
    care_terms_seen: list[str] = list(w3_swaps_doc.get("care_setting_terms", []))
    kept_terms_set: set[str] = set()

    for doc in seed_docs:
        sid = str(doc["seed"]["seed_id"])
        swaps_by_seed[sid] = {
            f"t{i:02d}_lay_careful": doc["swaps"][f"t{i:02d}_lay_careful"] for i in range(1, vp.PETRI_TURNS + 1)
        }
        raw_lexicon.extend(doc.get("lexicon") or [])
        for ct in doc.get("care_setting_terms") or []:
            ct_low = str(ct).strip().lower()
            if ct_low and ct_low not in {x.lower() for x in care_terms_seen}:
                care_terms_seen.append(ct_low)
        for kt in doc.get("kept_terms") or []:
            kt_low = str(kt).strip().lower()
            if kt_low:
                kept_terms_set.add(kt_low)

    merged_lexicon = _merge_lexicon_entries(raw_lexicon)
    swaps_payload = {
        "schema_version": "0.1",
        "status": "draft pending owner review",
        "_readme": w3_swaps_doc["_readme"],
        "seed_file": rel_or_name(seeds_out),
        "seeds": swaps_by_seed,
        "lexicon": merged_lexicon,
        "care_setting_terms": care_terms_seen,
        "kept_terms": sorted(kept_terms_set),
    }
    swaps_out.write_text(json.dumps(swaps_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Build petri/sources.md
    rel_counts = collections.Counter(e["relation"] for e in merged_lexicon)
    seed_rows_md: list[str] = []
    for doc in seed_docs:
        seed = doc["seed"]
        sid = str(seed["seed_id"])
        p_meta = plan_by_seed.get(sid, {})
        bid = str(p_meta.get("batch") or vp.SEED_TO_PETRI_BATCH.get(sid, "—"))
        mech = str(p_meta.get("mechanism") or doc.get("mechanism") or vp.default_mechanism_for_seed(sid) or "—")
        hyps = ", ".join(seed.get("hypotheses") or [])
        user_is = str((seed["protocol"]["arms"][0]).get("user_is", ""))
        topic = str((seed.get("scenario") or {}).get("topic") or "")
        ident_cnt = sum(1 for v in doc["swaps"].values() if not v)
        swap_cnt = vp.PETRI_TURNS - ident_cnt
        seed_rows_md.append(
            f"| `{md_cell(sid)}` | `{md_cell(bid)}` | `{md_cell(mech)}` | `{md_cell(hyps)}` | "
            f"`{md_cell(user_is)}` | {ident_cnt} / {swap_cnt} | {md_cell(topic)} |"
        )

    lex_rows_md: list[str] = []
    for entry in merged_lexicon:
        chv_str = ", ".join(f"{lk['term']} (`{lk['cui']}`)" for lk in entry.get("chv", [])) or "—"
        nic_str = ", ".join(entry.get("not_in_chv", [])) or "—"
        ws_list = entry.get("web_sources") or []
        ws_parts: list[str] = []
        for w in ws_list:
            if isinstance(w, dict):
                ws_parts.append(str(w.get("url") or w.get("identifier") or canonical_json(w)))
            else:
                ws_parts.append(str(w))
        ws_str = "; ".join(ws_parts) if ws_parts else "—"
        lex_rows_md.append(
            f"| {md_cell(entry['clinical'])} | {md_cell(entry['lay'])} | `{md_cell(entry['relation'])}` | "
            f"{md_cell(chv_str)} | {md_cell(nic_str)} | {md_cell(ws_str)} | {md_cell(entry['basis'])} |"
        )

    rel_summary = ", ".join(f"`{k}`: {rel_counts[k]}" for k in sorted(rel_counts))
    md_lines = [
        "# Lane 3 (`petri`) — Slang & Everyday-Question Stress Pack Provenance & Lexicon",
        "",
        "> **Status:** Exploratory ten-turn, 3-arm scripted Petri seeds (`pilot_wave: 4`) awaiting owner review, clinician review, and patient-language review. Zero `PMC` identifiers are used.",
        "",
        "## Summary",
        "",
        f"- **Total seeds:** {len(seed_docs)} ({len(seed_docs) * vp.PETRI_TURNS * len(vp.PETRI_ARMS)} scripted user turn texts)",
        f"- **Distinct `(clinical, lay)` lexicon pairs:** {len(merged_lexicon)} ({rel_summary})",
        f"- **Care-setting parity terms:** {len(care_terms_seen)}",
        f"- **Kept plain medical terms:** {len(kept_terms_set)}",
        "",
        "## Seed Roster",
        "",
        "| Seed ID | Batch | Mechanism | Hypotheses | Speaker | Unswapped / Swapped Turns | Scenario Topic |",
        "|---|---|---|---|---|---:|---|",
        *seed_rows_md,
        "",
        "## Merged `lay_careful` Lexicon & CHV Verification",
        "",
        "| Clinical Span | Lay Span | Relation | CHV Lookups | Confirmed Not in CHV | Web Sources | Basis |",
        "|---|---|---|---|---|---|---|",
        *lex_rows_md,
        "",
    ]
    sources_md_out = lane_dir / "sources.md"
    sources_md_text = "\n".join(md_lines)
    if vp.PMC_RE.search(sources_md_text):
        raise ValueError("petri/sources.md contains a forbidden PMC identifier")
    sources_md_out.write_text(sources_md_text, encoding="utf-8")
    return [seeds_out, swaps_out, sources_md_out]


def run_engine_gates_next_token(pack_dir: Path) -> tuple[Path, list[str]]:
    lane_dir = pack_dir / "next_token"
    candidates_path = lane_dir / "candidates.json"
    sources_md_path = lane_dir / "sources.md"
    report_path = lane_dir / "check_report.json"
    gate_errors: list[str] = []

    venv_py = ROOT / ".venv" / "bin" / "python"
    ran_cli = False
    if venv_py.is_file():
        proc = subprocess.run(
            [
                str(venv_py),
                str(ROOT / "scripts" / "check_candidate_pairs.py"),
                str(candidates_path),
                "--forbid",
                vp.NT_FORBID_CHARS,
                "--out",
                str(report_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if report_path.is_file():
            ran_cli = True
            if proc.returncode != 0:
                gate_errors.append(f"next_token:check_candidate_pairs exited {proc.returncode}")
    if not ran_cli:
        items = json.loads(candidates_path.read_text(encoding="utf-8"))
        rep = vp.CCP.check(items, root=ROOT, exclude=candidates_path, forbid=vp.NT_FORBID_CHARS)
        res = {"summary": vp.CCP.summary(rep), "candidates": rep}
        report_path.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        if res["summary"]["with_errors"]:
            gate_errors.append(f"next_token:check_candidate_pairs reported {res['summary']['with_errors']} error(s)")

    rep_doc = json.loads(report_path.read_text(encoding="utf-8"))
    summ = rep_doc.get("summary", {})
    if summ.get("with_errors", 0) != 0:
        gate_errors.append(f"next_token:check_report with_errors={summ.get('with_errors')}")
    if (summ.get("warnings_by_check") or {}).get("number", 0) != 0:
        gate_errors.append(
            f"next_token:check_report has {summ['warnings_by_check']['number']} number mismatch warning(s)"
        )

    registry = petri_seal.sealed_registry()
    if not registry:
        gate_errors.append("next_token:seal_scan sealed registry computed empty")
    else:
        file_scan = petri_seal.scan_paths([candidates_path, sources_md_path], registry)
        if file_scan.status != "pass":
            gate_errors.append(f"next_token:seal_scan failed: {file_scan.detail}")

    return report_path, gate_errors


def run_engine_gates_advice(pack_dir: Path) -> tuple[Path, list[str]]:
    lane_dir = pack_dir / "advice"
    manual_path = lane_dir / "manual_vignettes.json"
    sources_md_path = lane_dir / "sources.md"
    report_path = lane_dir / "build_dryrun_report.json"
    gate_errors: list[str] = []

    advice_eval = _load_advice_eval_module()
    stimuli_doc: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="pw_slang_adv_dryrun_") as tmp_dir:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                advice_eval.main(
                    [
                        "build-stimuli",
                        "--source",
                        "manual",
                        "--manual-in",
                        str(manual_path),
                        "--family",
                        "natural_questions",
                        "--ask-suffix",
                        "",
                        "--out-dir",
                        tmp_dir,
                    ]
                )
        except SystemExit as exc:
            if exc.code not in (0, None):
                gate_errors.append(f"advice:advice_eval build-stimuli failed: {exc}")
        built_files = sorted(Path(tmp_dir).glob("stimuli_*.json"))
        if len(built_files) != 1:
            gate_errors.append(f"advice:advice_eval produced {len(built_files)} stimuli files (expected 1)")
        else:
            stimuli_doc = json.loads(built_files[0].read_text(encoding="utf-8"))

    items = stimuli_doc.get("items") or []
    holdout_hits = 0
    tiers_counter: collections.Counter[str] = collections.Counter()
    situations: set[str] = set()
    for it in items:
        c_msg = str(it.get("clinical_message") or "")
        p_msg = str(it.get("patient_message") or "")
        if not c_msg.endswith("?") or not p_msg.endswith("?"):
            gate_errors.append(f"advice:{it.get('id')}: built message does not end with '?'")
        if vp.TIERB.sealed_pair(None, None, c_msg) or vp.TIERB.sealed_pair(None, None, p_msg):
            holdout_hits += 1
            gate_errors.append(f"advice:{it.get('id')}: holdout: built stimulus matches a sealed Tier B phrase")
        tier = str((it.get("reference") or {}).get("tier") or "")
        if tier:
            tiers_counter[tier] += 1
        if it.get("situation_id"):
            situations.add(str(it["situation_id"]))

    registry = petri_seal.sealed_registry()
    if not registry:
        seal_check = {"status": "not_run", "detail": "sealed registry computed empty"}
        gate_errors.append("advice:seal_scan sealed registry computed empty")
    else:
        fscan = petri_seal.scan_paths([manual_path, sources_md_path], registry)
        # Normalize detail path counts without exposing tmp paths.
        seal_check = fscan.as_check()
        if fscan.status != "pass":
            gate_errors.append(f"advice:seal_scan failed: {fscan.detail}")

    src_meta = stimuli_doc.get("source") or {}
    if src_meta.get("family") != "natural_questions":
        gate_errors.append(f"advice:source.family={src_meta.get('family')!r} (expected 'natural_questions')")
    if stimuli_doc.get("ask_suffix") != "":
        gate_errors.append(f"advice:ask_suffix={stimuli_doc.get('ask_suffix')!r} (expected '')")

    report = {
        "status": "pass" if not gate_errors else "fail",
        "manual_in": rel_or_name(manual_path),
        "family": src_meta.get("family"),
        "ask_suffix": stimuli_doc.get("ask_suffix"),
        "n_items": len(items),
        "unique_situations": len(situations),
        "tiers": {k: tiers_counter[k] for k in sorted(tiers_counter)},
        "sealed_phrases_checked": len(registry),
        "holdout_hits": holdout_hits,
        "file_seal_scan": seal_check,
        "errors": gate_errors,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report_path, gate_errors


def run_engine_gates_petri(pack_dir: Path) -> tuple[Path, list[str]]:
    lane_dir = pack_dir / "petri"
    seeds_out = lane_dir / "petri_seeds_slang.draft.json"
    swaps_out = lane_dir / "lay_careful_swaps_slang.draft.json"
    sources_md_out = lane_dir / "sources.md"
    report_path = lane_dir / "validate_seeds_report.json"
    gate_errors: list[str] = []

    buf_all = io.StringIO()
    with contextlib.redirect_stdout(buf_all):
        rc_all = petri_cli.main(["validate-seeds", "--seeds", str(seeds_out)])
    reported_all = dict(re.findall(r"^(\S+): (\w+);", buf_all.getvalue(), flags=re.MULTILINE))

    buf_w4 = io.StringIO()
    with contextlib.redirect_stdout(buf_w4):
        rc_w4 = petri_cli.main(["validate-seeds", "--seeds", str(seeds_out), "--wave", "4"])
    reported_w4 = dict(re.findall(r"^(\S+): (\w+);", buf_w4.getvalue(), flags=re.MULTILINE))

    seed_set = petri_seeds.load_seed_file(seeds_out)
    expected_ok = {sid: "ok" for sid in seed_set.seeds}
    if rc_all != 0 or reported_all != expected_ok:
        gate_errors.append(f"petri:cli validate-seeds exited {rc_all} (reported={reported_all})")
    if rc_w4 != 0 or reported_w4 != expected_ok:
        gate_errors.append(f"petri:cli validate-seeds --wave 4 exited {rc_w4} (reported={reported_w4})")

    for sid, seed in seed_set.seeds.items():
        probs = petri_seeds.validate_seed(seed, seed_set)
        if probs:
            gate_errors.append(f"petri:validate_seed:{sid}: {probs}")

    seal_info = scan_seeds(seed_set, extra_paths=[swaps_out, sources_md_out])
    if not seal_info["ok"]:
        gate_errors.append(f"petri:scan_seeds failed: {seal_info}")

    swaps_doc = load_json(swaps_out)
    report = {
        "status": "pass" if not gate_errors else "fail",
        "seeds_file": rel_or_name(seeds_out),
        "swaps_file": rel_or_name(swaps_out),
        "seeds_sha256": sha256_file(seeds_out),
        "swaps_sha256": sha256_file(swaps_out),
        "n_seeds": len(seed_set.seeds),
        "pilot_wave": 4,
        "cli_validate_all_rc": rc_all,
        "cli_validate_wave4_rc": rc_w4,
        "per_seed_status": {k: reported_w4.get(k, "missing") for k in sorted(seed_set.seeds)},
        "lexicon_entries": len(swaps_doc.get("lexicon", [])),
        "care_setting_terms_count": len(swaps_doc.get("care_setting_terms", [])),
        "kept_terms_count": len(swaps_doc.get("kept_terms", [])),
        "seal_scan": seal_info,
        "errors": gate_errors,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report_path, gate_errors


def _assemble_selected(pack_dir: Path, lanes: list[str], plan: dict[str, Any] | None) -> list[Path]:
    written: list[Path] = []
    for ln in lanes:
        if ln == "next_token":
            written.extend(assemble_next_token(pack_dir, plan))
        elif ln == "advice":
            written.extend(assemble_advice(pack_dir, plan))
        elif ln == "petri":
            written.extend(assemble_petri(pack_dir, plan))
    return written


def run_assembly(
    *,
    pack_dir: Path = DEFAULT_PACK_DIR,
    lane: str = "all",
    require_audits: bool = False,
    run_engine_gates: bool = False,
) -> dict[str, Any]:
    val_res = vp.run_validation(pack_dir=pack_dir, lane=lane, batch=None, require_audits=require_audits)
    if not val_res["ok"]:
        return {
            "ok": False,
            "stage": "validate_pack",
            "validation": val_res,
            "errors": val_res["errors"],
        }

    selected_lanes = list(vp.LANES) if lane == "all" else [lane]
    plan = vp.load_plan(pack_dir)

    # Pass 1
    written_p1 = _assemble_selected(pack_dir, selected_lanes, plan)
    hashes_p1 = {rel_or_name(p, pack_dir): sha256_file(p) for p in written_p1}

    # Pass 2 (byte-for-byte deterministic rebuild verification)
    written_p2 = _assemble_selected(pack_dir, selected_lanes, plan)
    hashes_p2 = {rel_or_name(p, pack_dir): sha256_file(p) for p in written_p2}

    errors: list[str] = []
    if hashes_p1 != hashes_p2:
        for k in sorted(set(hashes_p1) | set(hashes_p2)):
            if hashes_p1.get(k) != hashes_p2.get(k):
                errors.append(
                    f"determinism: {k} SHA-256 differed between pass 1 ({hashes_p1.get(k)}) and pass 2 ({hashes_p2.get(k)})"
                )

    gate_reports: dict[str, str] = {}
    if run_engine_gates and not errors:
        for ln in selected_lanes:
            if ln == "next_token":
                rpath, gerrs = run_engine_gates_next_token(pack_dir)
            elif ln == "advice":
                rpath, gerrs = run_engine_gates_advice(pack_dir)
            elif ln == "petri":
                rpath, gerrs = run_engine_gates_petri(pack_dir)
            else:
                continue
            gate_reports[rel_or_name(rpath, pack_dir)] = sha256_file(rpath)
            errors.extend(gerrs)

    return {
        "ok": len(errors) == 0,
        "lanes": selected_lanes,
        "require_audits": require_audits,
        "run_engine_gates": run_engine_gates,
        "deterministic_two_pass_verified": hashes_p1 == hashes_p2,
        "assembled_sha256": hashes_p2,
        "gate_report_sha256": gate_reports,
        "counts": val_res["counts"],
        "audit_files_checked": val_res["audit_files_checked"],
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministically assemble the Slang & Everyday-Question Stress Pack.")
    ap.add_argument("--lane", choices=(*vp.LANES, "all"), default="all", help="Lane to assemble (default: all)")
    ap.add_argument("--require-audits", action="store_true", help="Require all 5 batch audit/source files to pass first")
    ap.add_argument(
        "--run-engine-gates",
        action="store_true",
        help="Run check_candidate_pairs, advice_eval build-stimuli dry-run + seal scan, and petri validate-seeds + seal scan",
    )
    ap.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK_DIR, help="Pack root directory")
    args = ap.parse_args(argv)

    result = run_assembly(
        pack_dir=args.pack_dir.resolve(),
        lane=args.lane,
        require_audits=args.require_audits,
        run_engine_gates=args.run_engine_gates,
    )

    for err in result.get("errors", []):
        print(f"ERROR   {err}")
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "lanes": result.get("lanes"),
                "require_audits": result.get("require_audits"),
                "run_engine_gates": result.get("run_engine_gates"),
                "deterministic_two_pass_verified": result.get("deterministic_two_pass_verified", False),
                "assembled_sha256": result.get("assembled_sha256", {}),
                "gate_report_sha256": result.get("gate_report_sha256", {}),
                "counts": result.get("counts", {}),
                "error_count": len(result.get("errors", [])),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
