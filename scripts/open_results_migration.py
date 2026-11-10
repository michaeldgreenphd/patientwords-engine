#!/usr/bin/env python3
"""Dry-run of the move from the publication hold to the open-results policy: what changes, counted.

Reads the engine checkout and writes a report; it publishes nothing and changes no measurement, manifest,
ledger or site file. It answers, with reasons and without any stimulus text:

* which parts and rows become visible that the hold kept out of everything (``newly_visible``);
* which rows and parts stay restricted, and under which named restriction (``still_restricted``);
* which parts are invalid (unreadable, malformed, or changed after a hash was recorded) (``invalid``);
* which parts are outside each analysis membership, and why (``analysis_ineligible``);
* what the study statistics would become if the separately declared ``exploratory-open/1`` membership were
  used instead of ``study-interim/1``: per-model counts, sign tests, the two Benjamini-Hochberg families and
  their adjusted values, and the simultaneous-interval width (``aggregates``). The collector and the statistics
  script are run twice into a temporary directory, once per membership; nothing they write leaves it.

The second run uses a candidate policy file through ``PW_RESULTS_POLICY`` (the documented preview route). The
first run's rows are compared with the engine's committed ``urgency_shift.json`` so the report states whether
the default membership still reproduces the published inputs.

  python scripts/open_results_migration.py --site ../patientwords --out ops/open_results_migration_20261110.json

Sealed rows are counted and never read into the report. Exit 2 when the seal or the policy cannot be evaluated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import results_policy as rp  # noqa: E402
from provenance_stamp import engine_sha  # noqa: E402

SCHEMA = "patientwords.open-results-migration/1"
SCRIPTS = Path(__file__).resolve().parent


def classify_all(engine: Path, policy: rp.Policy, seal_paths: dict[str, Any] | None = None) -> dict[str, Any]:
    """Counts of parts and rows by what the policy change does to them."""
    manifest = rp.load_manifest(engine) if (engine / rp.RELEASE_MANIFEST).exists() else None
    ledger = rp.load_ledger(engine)
    seal_paths = seal_paths or {}
    newly_parts: Counter[tuple[str, str, str]] = Counter()
    newly_rows: Counter[tuple[str, str, str]] = Counter()
    already = Counter()
    invalid: Counter[str] = Counter()
    restricted_parts: Counter[str] = Counter()
    sealed_rows: Counter[str] = Counter()
    listed_without_rows: Counter[str] = Counter()
    outside: dict[str, Counter[str]] = {m: Counter() for m in policy.doc["memberships"]}
    execution: Counter[str] = Counter()
    for part in sorted((engine / "trace_out").glob("*/batch_summary*.json")):
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            summary = None
        d = rp.classify_part(engine, part, summary, policy=policy, manifest=manifest, ledger=ledger)
        execution[d.execution_state] += 1
        for membership, verdict in d.analysis.items():
            if not verdict["eligible"]:
                outside[membership][verdict["reason"]] += 1
        if d.artifact_integrity in rp.INTEGRITY_FAILURES:
            invalid[d.artifact_integrity] += 1
            continue
        if d.visibility == "restricted":
            for reason in d.restriction_reasons:
                restricted_parts[reason] += 1
            continue
        in_study = d.analysis[rp.STUDY_INTERIM]["eligible"]
        n_public = 0
        if d.rows_exported:
            for result in summary["results"]:
                clinical = (result.get("prompts") or {}).get("clinical")
                if rp.row_restriction(d.stem, result.get("index"), clinical, **seal_paths):
                    sealed_rows["inside study-interim/1" if in_study else "outside study-interim/1"] += 1
                else:
                    n_public += 1
        else:
            listed_without_rows[d.stimulus_class if not d.instrument else f"instrument:{d.instrument}"] += 1
        if in_study:
            already["parts"] += 1
            already["rows_now_listed_per_row"] += n_public
            continue
        key = (d.analysis[rp.STUDY_INTERIM]["reason"], d.model or "-", d.evidence_class)
        newly_parts[key] += 1
        newly_rows[key] += n_public

    def table(parts: Counter, rows: Counter) -> list[dict[str, Any]]:
        return [{"reason_outside_study_membership": reason, "model": model, "evidence_class": evidence,
                 "parts": parts[(reason, model, evidence)], "public_rows": rows[(reason, model, evidence)]}
                for reason, model, evidence in sorted(parts)]

    return {
        "execution_state_of_all_parts": dict(sorted(execution.items())),
        "already_in_published_statistics": dict(already),
        "newly_visible": {"parts": sum(newly_parts.values()), "public_rows": sum(newly_rows.values()),
                          "by_reason_model": table(newly_parts, newly_rows)},
        "still_restricted": {
            "rows_withheld_by_tier_b_seal": dict(sorted(sealed_rows.items())),
            "parts_by_restriction": dict(sorted(restricted_parts.items())),
            "note": "sealed rows are counted, never listed; the seal is unchanged by this policy",
        },
        "listed_without_rows": {"parts_by_family": dict(sorted(listed_without_rows.items())),
                                "note": "visible in the catalogue with counts and hashes; rows need a policy "
                                        "entry for the stimulus family or belong to a typed instrument exporter"},
        "invalid": dict(sorted(invalid.items())),
        "analysis_ineligible": {m: dict(sorted(c.items())) for m, c in outside.items()},
    }


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> str:
    proc = subprocess.run([sys.executable, *argv], cwd=cwd, env=env, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"{' '.join(argv[:1])} failed ({proc.returncode}): {proc.stderr[-800:]}")
    return proc.stdout


def _collector_view(rows_path: Path) -> dict[str, Any]:
    doc = json.loads(rows_path.read_text(encoding="utf-8"))
    per_model = doc["summary"]["per_model"]
    return {"rows": len(doc["rows"]),
            "rows_sha256": hashlib.sha256(json.dumps(doc["rows"], sort_keys=True).encode()).hexdigest(),
            "holdout_rows_excluded_from_aggregates": doc["summary"].get("tierb_holdout_rows_excluded"),
            "per_model": {m: {k: v.get(k) for k in ("n", "flips", "downgrades", "upgrades", "sign_test_p",
                                                    "mean_tier_shift")} for m, v in sorted(per_model.items())}}


def _stats_view(bundle_path: Path) -> dict[str, Any]:
    doc = json.loads(bundle_path.read_text(encoding="utf-8"))
    families = doc["benjamini_hochberg"]["families"]
    return {
        "seed": doc.get("seed"), "boot": doc.get("boot"), "simultaneous_ci": doc.get("simultaneous_ci"),
        "families": {name: {"across": fam["across"], "n_tests": fam["n_tests"]} for name, fam in families.items()},
        "per_model": {m: {"registration": v.get("registration"), "n_unique_phrases": v.get("n_unique_phrases"),
                          "penalty_mean": v["penalty"]["mean"], "penalty_ci95": v["penalty"]["ci95"],
                          "penalty_ci95_simultaneous": v["penalty"].get("ci95_simultaneous"),
                          "downgrades": v["sign_test"]["downgrades"], "upgrades": v["sign_test"]["upgrades"],
                          "p_raw": v["sign_test"]["p_raw"], "p_bh": v["sign_test"]["p_bh"]}
                      for m, v in sorted(doc["per_model"].items())},
    }


def _baseline_collector(engine: Path, site: Path, ref: str, work: Path, env: dict[str, str]) -> dict[str, Any]:
    """Run scripts/urgency_shift.py as it was at ``ref`` over the same checkout and return its output's hash.
    Only scripts/ is taken from the ref; measurements and the site payload are the working tree's."""
    old = work / "baseline"
    old.mkdir()
    archive = subprocess.run(["git", "-C", str(engine), "archive", ref, "scripts"], capture_output=True)
    if archive.returncode:
        raise RuntimeError(f"git archive {ref} failed: {archive.stderr.decode('utf-8', 'replace').strip()}")
    subprocess.run(["tar", "-x", "-C", str(old)], input=archive.stdout, check=True)
    _run([str(old / "scripts" / "urgency_shift.py"), "--frontend", str(site), "--out", str(old / "urgency.json")],
         engine, env)
    commit = subprocess.run(["git", "-C", str(engine), "rev-parse", ref], capture_output=True, text=True)
    return {"ref": ref, "commit": commit.stdout.strip() or None,
            "output_sha256": hashlib.sha256((old / "urgency.json").read_bytes()).hexdigest()}


def aggregates(engine: Path, site: Path, policy: rp.Policy, boot: int, seed: int,
               baseline_ref: str | None = None) -> dict[str, Any]:
    """Run the collector and the statistics under both memberships, in a temporary directory."""
    out: dict[str, Any] = {"boot": boot, "seed": seed, "memberships": {}}
    with tempfile.TemporaryDirectory(prefix="pw-open-results-") as tmp:
        work = Path(tmp)
        candidate = dict(policy.doc)
        candidate["default_membership"] = rp.EXPLORATORY_OPEN
        (work / "candidate_policy.json").write_text(json.dumps(candidate), encoding="utf-8")
        for membership, extra_env in ((rp.STUDY_INTERIM, {}),
                                      (rp.EXPLORATORY_OPEN, {rp.POLICY_ENV: str(work / "candidate_policy.json")})):
            env = {k: v for k, v in os.environ.items() if k != rp.POLICY_ENV} | extra_env
            tag = membership.split("/")[0]
            rows_path, stats_path = work / f"urgency_{tag}.json", work / f"stats_{tag}.json"
            log = _run([str(SCRIPTS / "urgency_shift.py"), "--frontend", str(site), "--out", str(rows_path)],
                       engine, env)
            if f"analysis membership {membership}" not in log:
                raise RuntimeError(f"the collector did not report membership {membership}; refusing to label its "
                                   "output")
            _run([str(SCRIPTS / "paired_stats_rigor.py"), "--rows", str(rows_path), "--out", str(stats_path),
                  "--site", "", "--boot", str(boot), "--seed", str(seed)], engine, env)
            if membership == rp.STUDY_INTERIM and baseline_ref:
                base = _baseline_collector(engine, site, baseline_ref, work, env)
                new_sha = hashlib.sha256(rows_path.read_bytes()).hexdigest()
                out["collector_code_before_and_after"] = {
                    **base, "this_checkout_output_sha256": new_sha,
                    "byte_identical": base["output_sha256"] == new_sha,
                    "meaning": "the collector as it was at the baseline ref and the collector reading through "
                               "scripts/results_policy.py write the same bytes from the same inputs"}
            skipped = next((line for line in log.splitlines() if "parts not read" in line), "")
            out["memberships"][membership] = {"collector": _collector_view(rows_path),
                                              "statistics": _stats_view(stats_path),
                                              "collector_skip_line": skipped}
        committed = engine / "urgency_shift.json"
        if committed.exists():
            doc = json.loads(committed.read_text(encoding="utf-8"))
            sha = hashlib.sha256(json.dumps(doc["rows"], sort_keys=True).encode()).hexdigest()
            study = out["memberships"][rp.STUDY_INTERIM]["collector"]
            recomputed = json.loads((work / "urgency_study-interim.json").read_text(encoding="utf-8"))["rows"]

            def keys(rows: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
                return Counter((r["model"], r["batch"]) for r in rows)
            extra, gone = keys(recomputed) - keys(doc["rows"]), keys(doc["rows"]) - keys(recomputed)
            out["default_membership_vs_committed_rows"] = {
                "committed_file": "urgency_shift.json", "committed_rows": len(doc["rows"]),
                "recomputed_rows": study["rows"], "identical": sha == study["rows_sha256"],
                "rows_only_in_recomputed_by_model_batch": {f"{m} {b}": n for (m, b), n in sorted(extra.items())},
                "rows_only_in_committed_by_model_batch": {f"{m} {b}": n for (m, b), n in sorted(gone.items())},
                "reading": "a difference here comes from inputs that landed after the committed file was "
                           "written (hosted parts are read without a pin), not from the policy module; "
                           "collector_code_before_and_after is the code comparison"}
    a = out["memberships"][rp.STUDY_INTERIM]["statistics"]
    b = out["memberships"][rp.EXPLORATORY_OPEN]["statistics"]
    changes = {}
    for model in sorted(set(a["per_model"]) | set(b["per_model"])):
        before, after = a["per_model"].get(model), b["per_model"].get(model)
        changes[model] = {
            "in_study_interim": before is not None, "in_exploratory_open": after is not None,
            "n_unique_phrases": [before and before["n_unique_phrases"], after and after["n_unique_phrases"]],
            "penalty_mean": [before and before["penalty_mean"], after and after["penalty_mean"]],
            "penalty_ci95": [before and before["penalty_ci95"], after and after["penalty_ci95"]],
            "down_up": [before and [before["downgrades"], before["upgrades"]],
                        after and [after["downgrades"], after["upgrades"]]],
            "p_bh": [before and before["p_bh"], after and after["p_bh"]],
        }
    out["changes_if_exploratory_open_replaced_study_interim"] = {
        "family_sizes": {name: [a["families"][name]["n_tests"], b["families"][name]["n_tests"]]
                         for name in a["families"]},
        "simultaneous_ci_m": [(a["simultaneous_ci"] or {}).get("m"), (b["simultaneous_ci"] or {}).get("m")],
        "per_model": changes,
        "reading": "each pair is [study-interim/1, exploratory-open/1]. The second column is a different "
                   "analysis with a different multiple-testing family and, because the bootstrap shares one "
                   "random stream across the model set, different intervals even for unchanged data. It is "
                   "reported so the change is known before any switch; it replaces nothing.",
    }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", default=str(rp.ENGINE))
    parser.add_argument("--site", default=None,
                        help="frontend root; with it the aggregate comparison is computed (the collector reads "
                             "its payload). Without it only the visibility counts are reported.")
    parser.add_argument("--out", required=True, help="JSON report path")
    parser.add_argument("--baseline-ref", default=None,
                        help="a git ref from before the policy module (for example d8d0855d); also run that "
                             "ref's collector over the same inputs and record whether the bytes are identical")
    parser.add_argument("--boot", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    engine = Path(args.engine).resolve()
    try:
        policy = rp.load_policy()
        report: dict[str, Any] = {
            "schema": SCHEMA,
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "engine_sha": engine_sha(engine),
            "policy": {"version": policy.version, "default_membership": policy.default_membership,
                       "sha256": hashlib.sha256(policy.path.read_bytes()).hexdigest()},
            "what_this_is": "a dry run: counts and recomputed aggregates only; nothing published, no "
                            "measurement or manifest changed, no stimulus text included",
            "visibility": classify_all(engine, policy),
        }
        if args.site:
            report["aggregates"] = aggregates(engine, Path(args.site).resolve(), policy, args.boot, args.seed,
                                              args.baseline_ref)
    except rp.SealError as exc:
        return rp.seal_config_error(exc)
    except (rp.ReleaseError, RuntimeError) as exc:
        print(f"open-results migration: refused, nothing written: {exc}", file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    v = report["visibility"]
    print(f"newly visible: {v['newly_visible']['parts']} parts, {v['newly_visible']['public_rows']} rows; "
          f"still sealed: {sum(v['still_restricted']['rows_withheld_by_tier_b_seal'].values())} rows; "
          f"restricted parts: {sum(v['still_restricted']['parts_by_restriction'].values())}; "
          f"invalid: {sum(v['invalid'].values())} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
