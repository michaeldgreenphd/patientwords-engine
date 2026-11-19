#!/usr/bin/env python3
"""Deterministic batch assembler and Gate G1-G3 runner for Round 12 (`@builder`).

Owned outputs under `round12_20261117/batch_NN/` (writes nowhere else):
  - `families.json`
  - `sources.md`
  - `source_fit.json`
  - `check_pairs.json`
  - `check_report.json` (when `--run-gates` executes Gate G2)
  - `intake_summary.json` (when `--run-gates` executes Gate G3)

Never writes `self_check.md`, `concerns_selfreported.json`, `drafts/`, `sources/`,
`audit/`, `plan.json`, `ledger.json`, `progress.md`, `revisions.json`, or `final_report.md`.
Never edits `SPEC.md` or earlier rounds, and never runs git commit/push.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import validate_family as vf  # noqa: E402

ROUND12_DIR = vf.ROUND12_DIR
ROUND11_DIR = vf.ROUND11_DIR
SCENARIOS_ROOT = vf.SCENARIOS_ROOT
REPO_ROOT = SCENARIOS_ROOT.parent.parent
DEFAULT_LEDGER_PATH = ROUND12_DIR / "ledger.json"
DEFAULT_PLAN_PATH = ROUND12_DIR / "plan.json"
DEFAULT_PW_MAIN = REPO_ROOT.parent / "pw-main"
DEFAULT_VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

BATCH_NAME_RE = re.compile(r"^batch_0([12])$")


def _parse_id_args(raw_list: list[str] | None) -> list[str]:
    if not raw_list:
        return []
    out: list[str] = []
    for item in raw_list:
        for tok in item.split(","):
            tok_s = tok.strip()
            if tok_s:
                out.append(tok_s)
    return out


def _build_canonical_order_map(plan_path: Path) -> dict[str, tuple[int, int, str]]:
    order_map: dict[str, tuple[int, int, str]] = {}
    if plan_path.exists():
        plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
        for idx, slot in enumerate(plan_doc.get("slots", [])):
            fid = slot["family_id"]
            order_map[fid] = (0, idx, fid)
        for idx, res in enumerate(plan_doc.get("reserves", [])):
            rid = res["reserve_id"]
            order_map[rid] = (1, idx, rid)
    return order_map


def resolve_selected_family_ids(
    batch_name: str,
    *,
    passed_ids: list[str],
    rehearsal_ids: list[str],
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    plan_path: Path = DEFAULT_PLAN_PATH,
) -> tuple[list[str], bool]:
    """Return canonically ordered `(family_ids, is_rehearsal)` for `batch_name`."""
    if passed_ids and rehearsal_ids:
        raise ValueError("Pass at most one of --passed or --rehearsal-ids")

    is_rehearsal = bool(rehearsal_ids)
    if rehearsal_ids:
        raw_ids = rehearsal_ids
    elif passed_ids:
        raw_ids = passed_ids
    else:
        if not ledger_path.exists():
            raise FileNotFoundError(f"ledger.json not found at {ledger_path}")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        raw_ids = [
            row["family_id"]
            for row in ledger.get("families", [])
            if row.get("batch") == batch_name and row.get("state") == "passed"
        ]

    if not raw_ids:
        raise ValueError(f"No passed/rehearsal family IDs resolved for {batch_name}")

    order_map = _build_canonical_order_map(plan_path)
    unique_ids = sorted(
        set(raw_ids),
        key=lambda fid: order_map.get(fid, (2, 0, fid)),
    )
    return unique_ids, is_rehearsal


def canonicalize_family(fam: dict[str, Any]) -> dict[str, Any]:
    """Return a clean family object with deterministic Round 11/12 key order."""
    clean_facts = [
        {"fact_id": rf["fact_id"], "text": rf["text"]}
        for rf in fam["reference_facts"]
    ]
    raw_texts = fam["texts"]
    clean_texts: dict[str, str] = {}
    for k in vf.ALL_TEXT_KEYS_ORDERED:
        if k in raw_texts:
            clean_texts[k] = raw_texts[k]

    cf = fam["changed_fact"]
    clean_cf = {
        "fact_id": cf["fact_id"],
        "from": cf["from"],
        "to": cf["to"],
        "right_care_after": cf["right_care_after"],
    }

    out: dict[str, Any] = {
        "family_id": fam["family_id"],
        "condition": fam["condition"],
        "right_care": fam["right_care"],
        "level_rationale": fam["level_rationale"],
        "carrier_frame": fam["carrier_frame"],
        "target_token": fam["target_token"],
        "reference_facts": clean_facts,
        "texts": clean_texts,
        "changed_fact": clean_cf,
    }

    if "attribution" in fam and fam["attribution"] is not None:
        att = fam["attribution"]
        out["attribution"] = {k: att[k] for k in vf.ATTRIBUTION_KEYS}

    out["swap_spans"] = {
        "medical_span": fam["swap_spans"]["medical_span"],
        "everyday_span": fam["swap_spans"]["everyday_span"],
    }
    out["swap_note"] = fam["swap_note"]
    out["everyday_sources"] = [
        {k: srec[k] for k in vf.EVERYDAY_SOURCE_KEYS}
        for srec in fam["everyday_sources"]
    ]
    out["equity_dimension"] = fam["equity_dimension"]
    out["lexicon_entries"] = list(fam["lexicon_entries"])

    pf = fam["protocol_flags"]
    out["protocol_flags"] = {
        "has_dialect_lexicon": pf["has_dialect_lexicon"],
        "has_quad_2x2_syntax": pf["has_quad_2x2_syntax"],
        "has_patient_attribution": pf["has_patient_attribution"],
        "intervention_notes": pf["intervention_notes"],
    }
    out["design_note"] = fam["design_note"]
    return out


def build_check_pairs(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build Round 11/12 candidates format (`-reg`, `-cf`, `-att`) for check_candidate_pairs.py."""
    reg_pairs: list[dict[str, Any]] = []
    cf_pairs: list[dict[str, Any]] = []
    att_pairs: list[dict[str, Any]] = []

    for fam in families:
        fid = fam["family_id"]
        texts = fam["texts"]
        reg_pairs.append(
            {
                "id": f"{fid}-reg",
                "pair_kind": "register_swap",
                "top_prompt": texts["medical"],
                "bottom_prompt": texts["everyday"],
                "target_clinical_token": fam["target_token"],
                "swap_spans": {
                    "clinical_span": fam["swap_spans"]["medical_span"],
                    "patient_span": fam["swap_spans"]["everyday_span"],
                },
                "carrier_frame": fam["carrier_frame"],
                "clinical_tier_expected": fam["right_care"],
                "lexicon_entries": list(fam["lexicon_entries"]),
            }
        )
        cf = fam["changed_fact"]
        cf_pairs.append(
            {
                "id": f"{fid}-cf",
                "pair_kind": "changed_fact_control",
                "top_prompt": texts["everyday"],
                "bottom_prompt": texts["changed_fact"],
                "target_clinical_token": fam["target_token"],
                "swap_spans": {
                    "clinical_span": cf["from"],
                    "patient_span": cf["to"],
                },
                "carrier_frame": fam["carrier_frame"],
                "clinical_tier_expected": fam["right_care"],
            }
        )
        if "attribution" in fam:
            att_pairs.append(
                {
                    "id": f"{fid}-att",
                    "pair_kind": "patient_attribution",
                    "top_prompt": texts["everyday"],
                    "bottom_prompt": texts["everyday_attribution"],
                    "target_clinical_token": fam["target_token"],
                    "swap_spans": {
                        "clinical_span": "",
                        "patient_span": " " + fam["attribution"]["clause"],
                    },
                    "carrier_frame": fam["carrier_frame"],
                    "clinical_tier_expected": fam["right_care"],
                }
            )

    return reg_pairs + cf_pairs + att_pairs


def _dictionary_name_from_url(url: str | None) -> str | None:
    if not isinstance(url, str):
        return None
    u = url.lower()
    if "en.wiktionary.org/" in u:
        return "Wiktionary"
    if "merriam-webster.com/" in u:
        return "Merriam-Webster"
    if "dictionary.cambridge.org/" in u:
        return "Cambridge"
    if "daredictionary.com/" in u or "dare.wisc.edu/" in u:
        return "Dictionary of American Regional English"
    return None


def compute_citation_summary(families: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute cited-share metrics and exact dictionaries cited (SPEC.md sections 7 & 10)."""
    ev_total = 0
    ev_cited = 0
    att_total = 0
    att_cited = 0
    dicts_used: list[str] = []
    care_counts = {"4": 0, "3": 0, "2": 0}

    for fam in families:
        rc_str = str(fam["right_care"])
        if rc_str in care_counts:
            care_counts[rc_str] += 1
        for srec in fam["everyday_sources"]:
            ev_total += 1
            if srec["source"] != "none":
                ev_cited += 1
                if srec["quote_type"] == "dictionary definition":
                    dname = _dictionary_name_from_url(srec.get("inspected_url"))
                    if dname and dname not in dicts_used:
                        dicts_used.append(dname)
        if "attribution" in fam:
            att_total += 1
            att = fam["attribution"]
            if att["source"] != "none":
                att_cited += 1
                if att["quote_type"] == "dictionary definition":
                    dname = _dictionary_name_from_url(att.get("inspected_url"))
                    if dname and dname not in dicts_used:
                        dicts_used.append(dname)

    all_total = ev_total + att_total
    all_cited = ev_cited + att_cited
    return {
        "care_level_counts": care_counts,
        "everyday_expressions_total": ev_total,
        "everyday_expressions_cited": ev_cited,
        "everyday_expressions_cited_share": round(ev_cited / ev_total, 4) if ev_total > 0 else None,
        "attribution_clauses_total": att_total,
        "attribution_clauses_cited": att_cited,
        "attribution_clauses_cited_share": round(att_cited / att_total, 4) if att_total > 0 else None,
        "all_rows_total": all_total,
        "all_rows_cited": all_cited,
        "all_rows_cited_share": round(all_cited / all_total, 4) if all_total > 0 else None,
        "unsourced_rows_count": all_total - all_cited,
        "dictionaries_cited": dicts_used,
    }


def build_sources_md(batch_name: str, families: list[dict[str, Any]], dicts_cited: list[str]) -> str:
    """Build deterministic `sources.md` for Round 12 `batch_NN`."""
    grouped_order: list[str] = []
    grouped_meta: dict[str, dict[str, Any]] = {}
    unsourced_items: list[tuple[str, str, str]] = []

    def _add_record(fid: str, kind_label: str, phrase: str, rec: dict[str, Any]) -> None:
        if rec["source"] == "none":
            unsourced_items.append((fid, kind_label, phrase))
            return
        key = rec["pmid_or_doi"].strip()
        if key not in grouped_meta:
            grouped_order.append(key)
            grouped_meta[key] = {
                "source": rec["source"],
                "title": rec["title"],
                "pmid_or_doi": rec["pmid_or_doi"],
                "inspected_url": rec["inspected_url"],
                "access_set": [rec["access"]],
                "uses": [],
            }
        else:
            if rec["access"] not in grouped_meta[key]["access_set"]:
                grouped_meta[key]["access_set"].append(rec["access"])
        grouped_meta[key]["uses"].append(
            {
                "family_id": fid,
                "kind": kind_label,
                "phrase": phrase,
                "quote_type": rec["quote_type"],
                "location": rec["location"],
                "evidence": rec["evidence"],
                "adaptation": rec["adaptation"],
                "access": rec["access"],
            }
        )

    for fam in families:
        fid = fam["family_id"]
        for srec in fam["everyday_sources"]:
            _add_record(fid, "everyday expression", srec["expression"], srec)
        if "attribution" in fam:
            att = fam["attribution"]
            _add_record(fid, "attribution clause", att["clause"], att)

    bnum_str = batch_name.split("_")[1]
    if dicts_cited:
        dict_scope_line = (
            f"- **Dictionary lexical-sense scope:** Dictionary entries cited in this batch ({', '.join(dicts_cited)}) "
            "attest lexical senses and grammatical definitions only and do **NOT** by themselves establish contemporary "
            "demographic or community frequency unless accompanied by a population source."
        )
    else:
        dict_scope_line = (
            "- **Dictionary lexical-sense scope:** Zero dictionary entries are cited in this batch; all cited sources "
            "are peer-reviewed PubMed/DOI records."
        )

    lines: list[str] = [
        f"# Round 12 Batch {bnum_str} Sources (`round12_20261117/{batch_name}`)",
        "",
        "Every cited source in `families.json` (across both `everyday_sources` and `attribution`) is listed below "
        "with its `title`, `PMID` and `DOI` (or verified dictionary entry URL), `inspected_url`, what was directly "
        "opened (`access`: `full text` or `abstract only` — zero title-only sources), exact section/paragraph/sense "
        "`location`, `quote_type` (`\"direct patient quote\"`, `\"authors' summary\"`, or `\"dictionary definition\"`), "
        "exact verbatim `evidence`, and explicit `adaptation` separating the verbatim source text from how it was "
        "adapted into first-person scenario stimulus wording. No database identifiers other than `PMID` and `DOI` are "
        "used anywhere. Expressions and attribution clauses without a directly inspected Rule-B-compliant source "
        "sentence are marked `\"source\": \"none\"`.",
        "",
        "## Scope and Provenance Disclaimers",
        "",
        dict_scope_line,
        "- **Synthetic test stimuli (not real patient records):** Source-inspired synthetic scenarios in "
        "`families.json` are test stimuli constructed for language-model evaluation, **NOT** real patient records; "
        "verbatim source excerpts (`evidence`) are recorded separately from first-person scenario adaptations (`adaptation`).",
        "",
    ]

    if not grouped_order:
        lines.append("No external literature or dictionary sources cited in this selection; all items marked `\"source\": \"none\"`.")
        lines.append("")
    else:
        for idx, key in enumerate(grouped_order, start=1):
            meta = grouped_meta[key]
            access_str = " / ".join(meta["access_set"])
            lines.append(f"## {idx}. {meta['source']}")
            lines.append("")
            lines.append(f"- **Title:** {meta['title']}")
            lines.append(f"- **PMID / DOI / URL:** `{meta['pmid_or_doi']}`")
            lines.append(f"- **Inspected URL:** `{meta['inspected_url']}`")
            lines.append(f"- **Access opened:** `{access_str}`")
            lines.append(f"- **Supported Round 12 (`{batch_name}`) items:**")
            for u in meta["uses"]:
                adapt_str = (
                    "`null` *(exact case-sensitive verbatim substring in `evidence`)*"
                    if u["adaptation"] is None
                    else f"`{u['adaptation']}`"
                )
                lines.append(
                    f"  - `{u['family_id']}` ({u['kind']} `\"{u['phrase']}\"` — *{u['quote_type']}*)"
                )
                lines.append(f"    - **Location:** `{u['location']}`")
                lines.append(f"    - **Verbatim `evidence`:** `{u['evidence']}`")
                lines.append(f"    - **Scenario `adaptation`:** {adapt_str}")
            lines.append("")

    if unsourced_items:
        lines.extend(
            [
                "---",
                "",
                "## Unsourced Expressions and Attribution Clauses (`\"source\": \"none\"`)",
                "",
                "| Family | Kind | Phrase |",
                "|---|---|---|",
            ]
        )
        for fid, klabel, phrase in unsourced_items:
            lines.append(f"| `{fid}` | {klabel} | `\"{phrase}\"` |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_source_fit_doc(batch_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble `source_fit.json` from validated per-family `source_fit_rows`."""
    fit_counts = {"same": 0, "adjacent": 0, "different": 0}
    for r in rows:
        fit_counts[r["fit"]] += 1
    total = len(rows)
    same_share = round(fit_counts["same"] / total, 4) if total > 0 else None
    return {
        "schema": "patientwords.round12.source-fit/1",
        "batch": batch_name,
        "summary": {
            "cited_expressions": total,
            "fit_counts": fit_counts,
            "same_share": same_share,
            "meets_half_same_target": (fit_counts["same"] * 2 >= total) if total > 0 else True,
        },
        "rows": rows,
    }


def _assemble_payloads_from_disk(
    batch_dir: Path,
    selected_ids: list[str],
    ref: dict[str, Any],
    *,
    require_audits: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    raw_families: list[dict[str, Any]] = []
    for fid in selected_ids:
        dpath = batch_dir / "drafts" / f"{fid}.json"
        if not dpath.exists():
            raise FileNotFoundError(f"Missing draft file {dpath}")
        doc = json.loads(dpath.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("family_id") != fid:
            raise ValueError(f"{dpath}: family_id mismatch (got {doc.get('family_id')!r}, expected {fid!r})")
        raw_families.append(doc)

    errs, warns, val_summary = vf.validate_batch_collection(
        raw_families,
        ref,
        batch_dir=batch_dir,
        require_audits=require_audits,
    )
    if errs:
        joined = "\n  - ".join(errs)
        raise ValueError(f"Gate G1 / audit validation failed ({len(errs)} error(s)):\n  - {joined}")

    clean_families = [canonicalize_family(f) for f in raw_families]
    check_pairs = build_check_pairs(clean_families)
    citation_summary = compute_citation_summary(clean_families)
    sources_md = build_sources_md(batch_dir.name, clean_families, citation_summary["dictionaries_cited"])
    source_fit_doc = build_source_fit_doc(batch_dir.name, val_summary["source_fit_rows"])

    payloads = {
        "families.json": json.dumps(clean_families, indent=2, ensure_ascii=False) + "\n",
        "check_pairs.json": json.dumps(check_pairs, indent=2, ensure_ascii=False) + "\n",
        "sources.md": sources_md,
        "source_fit.json": json.dumps(source_fit_doc, indent=2, ensure_ascii=False) + "\n",
    }

    db_errors: list[str] = []
    for fname, content in payloads.items():
        m = vf.DB_ID_PATTERN.search(content)
        if m:
            db_errors.append(f"Generated {fname} contains forbidden DB identifier {m.group(0)!r}")
    if db_errors:
        raise ValueError("; ".join(db_errors))

    meta = {
        "warnings": warns,
        "families_count": len(clean_families),
        "check_pairs_count": len(check_pairs),
        "stated_negative_count": val_summary["stated_negative_count"],
        "stated_negative_ids": val_summary["stated_negative_ids"],
        "bleeding_l4_control_count": val_summary["bleeding_l4_control_count"],
        "bleeding_l4_control_ids": val_summary["bleeding_l4_control_ids"],
        "citation_summary": citation_summary,
        "source_fit_summary": source_fit_doc["summary"],
    }
    return payloads, meta


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_gate_commands(
    batch_dir: Path,
    *,
    python_bin: Path,
    pw_main: Path,
) -> tuple[list[str], list[str]]:
    batch_name = batch_dir.name
    m = BATCH_NAME_RE.match(batch_name)
    if not m:
        raise ValueError(f"Invalid batch name {batch_name!r}; expected batch_01 or batch_02")
    bnum = int(m.group(1))

    try:
        batch_arg_prefix = str(batch_dir.relative_to(REPO_ROOT))
    except ValueError:
        batch_arg_prefix = str(batch_dir)

    g2_cmd = [
        str(python_bin),
        str(pw_main / "scripts" / "check_candidate_pairs.py"),
        f"{batch_arg_prefix}/check_pairs.json",
        "--forbid",
        ",;-",
        "--lexicon",
        "drafts/antigravity_scenarios_20261107/lexicon/dialect_lexicon_20261109.json",
        "--out",
        f"{batch_arg_prefix}/check_report.json",
    ]

    r_abs = str(SCENARIOS_ROOT)
    g3_cmd = [
        str(python_bin),
        "-m",
        "scripts.experiments.cli",
        "intake",
        "--batch",
        str(batch_dir / "families.json"),
        "--batch-id",
        f"r12_b{bnum:02d}",
        "--prior-batch",
        f"r9={r_abs}/round9_20261110/families.json",
        "--prior-batch",
        f"r10={r_abs}/round10_20261112_rev1/families.json",
    ]
    for k in range(1, 7):
        r11_fam = ROUND11_DIR / f"batch_{k:02d}" / "families.json"
        if not r11_fam.exists():
            raise FileNotFoundError(f"Round 11 prior batch file missing for G3 intake: {r11_fam}")
        g3_cmd.extend(["--prior-batch", f"r11_b{k:02d}={r11_fam}"])
    for k in range(1, bnum):
        prev_fam = ROUND12_DIR / f"batch_{k:02d}" / "families.json"
        if not prev_fam.exists():
            raise FileNotFoundError(
                f"Prior Round 12 batch file missing for G3 intake: {prev_fam} (finish batch_{k:02d} first)"
            )
        g3_cmd.extend(["--prior-batch", f"r12_b{k:02d}={prev_fam}"])
    g3_cmd.extend(
        [
            "--lexicon",
            f"{r_abs}/lexicon/dialect_lexicon_20261109.json",
            "--no-write",
        ]
    )
    return g2_cmd, g3_cmd


def run_gates_g2_g3(
    batch_dir: Path,
    *,
    python_bin: Path,
    pw_main: Path,
) -> dict[str, Any]:
    g2_cmd, g3_cmd = build_gate_commands(batch_dir, python_bin=python_bin, pw_main=pw_main)

    # Gate G2: check_candidate_pairs.py (run from REPO_ROOT)
    g2_proc = subprocess.run(
        g2_cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    report_path = batch_dir / "check_report.json"
    if not report_path.exists():
        raise RuntimeError(
            f"Gate G2 failed to produce {report_path} (exit={g2_proc.returncode}): "
            f"{g2_proc.stderr.strip() or g2_proc.stdout.strip()}"
        )
    g2_report = json.loads(report_path.read_text(encoding="utf-8"))
    g2_errors = g2_report.get("summary", {}).get("with_errors", -1)
    g2_warnings = g2_report.get("summary", {}).get("with_warnings", 0)
    g2_warning_details = {
        cid: cval.get("warnings", [])
        for cid, cval in g2_report.get("candidates", {}).items()
        if isinstance(cval, dict) and cval.get("warnings")
    }
    if g2_proc.returncode != 0 or g2_errors != 0:
        raise RuntimeError(
            f"Gate G2 failed: exit={g2_proc.returncode}, with_errors={g2_errors} in {report_path}"
        )

    # Gate G3: scripts.experiments.cli intake (run from pw_main)
    g3_proc = subprocess.run(
        g3_cmd,
        cwd=str(pw_main),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_str = g3_proc.stdout.strip()
    if not stdout_str:
        raise RuntimeError(
            f"Gate G3 produced empty stdout (exit={g3_proc.returncode}): {g3_proc.stderr.strip()}"
        )
    try:
        intake_doc = json.loads(stdout_str)
    except Exception as exc:
        raise RuntimeError(
            f"Gate G3 stdout is not valid JSON (exit={g3_proc.returncode}): {exc}\n{stdout_str[:500]}"
        ) from exc

    intake_summary_path = batch_dir / "intake_summary.json"
    intake_summary_path.write_text(
        json.dumps(intake_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    intake_status = intake_doc.get("status")
    sw_errors = intake_doc.get("software_validation", {}).get("errors")
    sw_warnings = intake_doc.get("software_validation", {}).get("warnings")
    if g3_proc.returncode != 0 or intake_status != "intake" or sw_errors != 0:
        raise RuntimeError(
            f"Gate G3 failed: exit={g3_proc.returncode}, status={intake_status!r}, "
            f"software_validation.errors={sw_errors!r} (saved to {intake_summary_path})"
        )

    out_gates: dict[str, Any] = {
        "g2": {
            "pass": True,
            "candidates": g2_report.get("summary", {}).get("candidates"),
            "with_errors": g2_errors,
            "with_warnings": g2_warnings,
            "warnings_by_check": g2_report.get("summary", {}).get("warnings_by_check", {}),
            "warning_details": g2_warning_details,
            "report_path": str(report_path),
        },
        "g3": {
            "pass": True,
            "status": intake_status,
            "software_validation_errors": sw_errors,
            "software_validation_warnings": sw_warnings,
            "intake_summary_path": str(intake_summary_path),
        },
    }

    # Optional read-only validation of concerns_selfreported.json (stdout only; never overwrites intake_summary.json)
    concerns_path = batch_dir / "concerns_selfreported.json"
    if concerns_path.exists():
        expected_bid = f"r12_b{batch_dir.name.split('_')[1]}"
        c_schema_errs = vf.validate_concerns_file(concerns_path, expected_batch_id=expected_bid)
        if c_schema_errs:
            raise RuntimeError(f"concerns_selfreported.json failed SPEC schema check: {c_schema_errs}")

        g3_concerns_cmd = list(g3_cmd) + ["--concerns", str(concerns_path)]
        g3c_proc = subprocess.run(
            g3_concerns_cmd,
            cwd=str(pw_main),
            capture_output=True,
            text=True,
            check=False,
        )
        c_stdout = g3c_proc.stdout.strip()
        try:
            c_doc = json.loads(c_stdout) if c_stdout else {}
        except Exception as exc:
            raise RuntimeError(
                f"concerns_selfreported.json intake check produced non-JSON stdout (exit={g3c_proc.returncode}): {exc}"
            ) from exc
        c_status = c_doc.get("status")
        c_errors = c_doc.get("software_validation", {}).get("errors")
        if g3c_proc.returncode != 0 or c_status != "intake" or c_errors != 0:
            raise RuntimeError(
                f"concerns_selfreported.json intake check failed (exit={g3c_proc.returncode}, "
                f"status={c_status!r}): {json.dumps(c_doc)}"
            )
        out_gates["concerns_selfreported_check"] = {
            "pass": True,
            "status": c_status,
            "software_validation_errors": c_errors,
            "concerns_inventory": c_doc.get("inventory", {}).get("concerns", {}),
        }

    return out_gates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministically assemble Round 12 batch artifacts and verify Gates G1-G3."
    )
    parser.add_argument("--batch", required=True, help="Batch name (batch_01 or batch_02) or path")
    parser.add_argument(
        "--passed",
        nargs="*",
        help="Explicit passed family IDs (space- or comma-separated); defaults to ledger.json state=='passed'",
    )
    parser.add_argument(
        "--rehearsal-ids",
        nargs="*",
        help="Rehearsal family ID(s) (e.g. r12-001) to assemble and verify end-to-end",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and build in memory without writing batch files",
    )
    parser.add_argument(
        "--no-require-audits",
        action="store_true",
        help="Allow dry-run assembly before audit files exist (only valid with --dry-run)",
    )
    parser.add_argument(
        "--check-concerns",
        action="store_true",
        help="Require and validate batch_NN/concerns_selfreported.json offline against SPEC.md section 10",
    )
    parser.add_argument(
        "--run-gates",
        action="store_true",
        help="Also execute Gate G2 (check_candidate_pairs.py) and Gate G3 (experiments.cli intake)",
    )
    parser.add_argument(
        "--python",
        default=str(DEFAULT_VENV_PYTHON),
        help="Python interpreter for --run-gates (default: .venv/bin/python)",
    )
    parser.add_argument(
        "--pw-main",
        default=str(DEFAULT_PW_MAIN),
        help="Path to main worktree ../pw-main (default: /Users/michaelgreen/pw-main)",
    )
    args = parser.parse_args(argv)

    if args.no_require_audits and not args.dry_run:
        parser.error("--no-require-audits is only permitted with --dry-run")

    raw_bpath = Path(args.batch)
    if not raw_bpath.is_absolute():
        cand = ROUND12_DIR / raw_bpath
        batch_dir = (cand if cand.exists() or raw_bpath.name.startswith("batch_") else raw_bpath).resolve()
    else:
        batch_dir = raw_bpath.resolve()

    batch_name = batch_dir.name
    if not BATCH_NAME_RE.match(batch_name):
        parser.error(f"Batch directory name must be batch_01 or batch_02, got {batch_name!r}")

    try:
        selected_ids, is_rehearsal = resolve_selected_family_ids(
            batch_name,
            passed_ids=_parse_id_args(args.passed),
            rehearsal_ids=_parse_id_args(args.rehearsal_ids),
        )
        ref = vf.load_reference_data(current_batch_name=batch_name, current_batch_dir=None)
        require_audits = not args.no_require_audits

        payloads_pass1, meta = _assemble_payloads_from_disk(
            batch_dir,
            selected_ids,
            ref,
            require_audits=require_audits,
        )

        concerns_path = batch_dir / "concerns_selfreported.json"
        concerns_schema_result: dict[str, Any] | None = None
        if args.check_concerns or concerns_path.exists():
            expected_bid = f"r12_b{batch_name.split('_')[1]}"
            cerrs = vf.validate_concerns_file(concerns_path, expected_batch_id=expected_bid)
            if cerrs:
                raise ValueError(f"concerns_selfreported.json failed schema validation: {cerrs}")
            cdoc = json.loads(concerns_path.read_text(encoding="utf-8"))
            concerns_schema_result = {
                "pass": True,
                "concerns_count": len(cdoc.get("concerns", [])),
            }

        if args.dry_run:
            payloads_pass2, _ = _assemble_payloads_from_disk(
                batch_dir,
                selected_ids,
                ref,
                require_audits=require_audits,
            )
            for fname in payloads_pass1:
                if payloads_pass1[fname].encode("utf-8") != payloads_pass2[fname].encode("utf-8"):
                    raise RuntimeError(f"Gate G1 non-deterministic rebuild detected on {fname}")
            print(
                json.dumps(
                    {
                        "status": "dry_run_ok",
                        "batch": batch_name,
                        "rehearsal": is_rehearsal,
                        "selected_ids": selected_ids,
                        **meta,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        batch_dir.mkdir(parents=True, exist_ok=True)
        written_hashes: dict[str, str] = {}
        for fname, content in payloads_pass1.items():
            out_path = batch_dir / fname
            out_path.write_text(content, encoding="utf-8")
            written_hashes[fname] = _sha256_bytes(out_path.read_bytes())

        # Gate G1: Independent second pass from disk inputs, verifying byte-for-byte reproducibility
        ref_pass2 = vf.load_reference_data(current_batch_name=batch_name, current_batch_dir=None)
        payloads_pass2, _ = _assemble_payloads_from_disk(
            batch_dir,
            selected_ids,
            ref_pass2,
            require_audits=require_audits,
        )
        for fname, rebuilt_str in payloads_pass2.items():
            rebuilt_hash = _sha256_bytes(rebuilt_str.encode("utf-8"))
            disk_bytes = (batch_dir / fname).read_bytes()
            disk_hash = _sha256_bytes(disk_bytes)
            if rebuilt_hash != written_hashes[fname] or disk_hash != rebuilt_hash:
                raise RuntimeError(
                    f"Gate G1 byte-for-byte rebuild mismatch on {fname}: "
                    f"written={written_hashes[fname]} rebuilt={rebuilt_hash}"
                )

        stop_rule_warnings: list[str] = []
        if not is_rehearsal and len(selected_ids) < 16:
            stop_rule_warnings.append(
                f"STOP RULE 1 WARNING: {batch_name} has {len(selected_ids)} < 16 passed families (SPEC.md section 9)"
            )

        python_bin = Path(args.python)
        pw_main = Path(args.pw_main).resolve()
        gate_results: dict[str, Any] = {
            "g1": {
                "pass": True,
                "sha256": written_hashes,
            }
        }
        if concerns_schema_result is not None:
            gate_results["concerns_schema"] = concerns_schema_result

        if args.run_gates:
            g2_g3 = run_gates_g2_g3(batch_dir, python_bin=python_bin, pw_main=pw_main)
            gate_results.update(g2_g3)
        else:
            g2_cmd, g3_cmd = build_gate_commands(batch_dir, python_bin=python_bin, pw_main=pw_main)
            gate_results["next_commands"] = {
                "g2_cwd": str(REPO_ROOT),
                "g2_cmd": shlex.join(g2_cmd),
                "g3_cwd": str(pw_main),
                "g3_cmd": f"{shlex.join(g3_cmd)} > {shlex.quote(str(batch_dir / 'intake_summary.json'))}",
            }

        result_summary = {
            "status": "assembled",
            "batch": batch_name,
            "rehearsal": is_rehearsal,
            "selected_ids": selected_ids,
            "stop_rule_warnings": stop_rule_warnings,
            **meta,
            "gates": gate_results,
        }
        print(json.dumps(result_summary, indent=2, ensure_ascii=False))
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
