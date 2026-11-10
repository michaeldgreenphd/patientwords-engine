"""Acceptance test of the first offline milestone: the whole synthetic slice through the command line.

One clearly synthetic family set (clinical, colloquial and normalized variants) goes through protocol
validation, a deterministic plan, an interrupted run, a resumed run, collection, comparison and the preview
bundle, with the optional ICA adapter and the existing readout boundary both exercised. What this pins:

* incompatible method and model combinations stay visible as ``unsupported`` or ``unavailable`` with a reason;
* an interruption followed by a resume executes each task once (5, then 22) and reuses the rest;
* a third run executes nothing: unchanged results are reused;
* a changed input changes every affected task identity and is refused in the old run directory;
* an independent replicate is executed, never satisfied from the first replicate's results;
* nothing is written inside the checkout or under a protected data root.

Everything is a toy fixture. This is a software check and says nothing about a model.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures" / "experiments"
PROTOCOL = FX / "protocol_synthetic_ica.json"


def cli(*argv: str, expect: int = 0) -> dict:
    proc = subprocess.run([sys.executable, "-m", "scripts.experiments.cli", *argv], cwd=ROOT, capture_output=True,
                          text=True, timeout=300)
    assert proc.returncode == expect, (argv, proc.returncode, proc.stdout[-600:], proc.stderr[-600:])
    return json.loads(proc.stdout)


def test_the_committed_ica_protocol_is_the_synthetic_protocol_plus_the_fixture_method_block() -> None:
    base = json.loads((FX / "protocol_synthetic.json").read_text(encoding="utf-8"))
    block = json.loads((FX / "ica" / "fixture_index.json").read_text(encoding="utf-8"))["method_block"]
    expected = copy.deepcopy(base)
    expected["protocol_id"] = "synthetic-slice-ica-1"
    expected["methods"].append(block)
    assert json.loads(PROTOCOL.read_text(encoding="utf-8")) == expected
    assert expected["synthetic"] is True and expected["evidence"]["evidence_class"] == "synthetic_fixture"


def test_the_whole_slice_runs_interrupts_resumes_and_reuses(tmp_path: Path) -> None:
    plan, runs = tmp_path / "plan.json", tmp_path / "runs"
    assert cli("validate", "--protocol", str(PROTOCOL))["families"] == 3
    planned = cli("plan", "--protocol", str(PROTOCOL), "--out", str(plan))
    totals = planned["totals"]
    assert totals["tasks"] == 45 and totals["by_planned_state"] == {"ready": 27, "unavailable": 9, "unsupported": 9}
    assert totals["by_method"]["ica_lens"]["ready"] == 9 and totals["by_method"]["logit_lens"]["ready"] == 9
    assert totals["by_method"]["jpp"]["unavailable"] == 9 and totals["by_method"]["j_lens"]["unsupported"] == 9
    assert totals["runtime_seconds_estimate"] is None and totals["estimates"]["measured"] is False
    assert json.loads(plan.read_text(encoding="utf-8")) == json.loads(plan.read_text(encoding="utf-8"))

    run = ("run-fixture", "--plan", str(plan), "--fixtures", str(FX), "--run-dir", str(runs))
    first = cli(*run, "--stop-after", "5")
    assert (first["executed"], first["reused"], first["stopped_early"], first["remaining_ready"]) == (5, 0, True, 22)
    second = cli(*run)
    assert (second["executed"], second["reused"], second["remaining_ready"]) == (22, 5, 0)
    third = cli(*run)
    assert (third["executed"], third["reused"]) == (0, 27)                       # unchanged results: no new work

    collected = cli("collect", "--run-dir", str(runs), "--require-complete")
    assert collected["complete"] is True and collected["executed_attempts"] == 27 and collected["missing"] == []
    assert collected["by_state"] == {"completed": 27, "failed": 0, "invalid": 0, "not_run": 0, "unavailable": 9,
                                     "unsupported": 9}
    assert collected["counts"]["uncertain_attempts"] == 0 and collected["counts"]["duplicate_identical"] == 0

    compared = cli("compare", "--run-dir", str(runs), "--out", str(tmp_path / "compare.json"))
    assert compared["behavior_blocks_computed"] == 6 and compared["ica_blocks_computed"] == 6
    not_run = {m["method"]: m for m in compared["methods_not_run"]}
    assert set(not_run) == {"j_lens", "jpp"} and all(m["reasons"] for m in not_run.values())
    assert not_run["j_lens"]["states"] == {"unsupported": 9} and not_run["jpp"]["states"] == {"unavailable": 9}

    bundled = cli("bundle", "--run-dir", str(runs), "--out", str(tmp_path / "bundle.json"))
    assert bundled["limitations"][0] == "synthetic_not_measurement"
    bundle = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["schema_version"] == "patientwords.experiment-bundle/1"
    assert bundle["evidence"]["evidence_class"] == "synthetic_fixture"
    text = json.dumps(bundle)
    assert "understanding_score" not in text and "risk_score" not in text     # typed blocks, no merged score

    # Fields added to bundle version 1 on 2026-11-10 for the browser preview. Each expected value comes from
    # the fixture protocol or from the run summaries above, not from the bundle.
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    for family in bundle["protocol"]["families"]:
        source = next(f for f in protocol["case_families"] if f["family_id"] == family["family_id"])
        assert family["variant_inputs"] == {
            name: {"prompt_sha256": entry["prompt_sha256"], "token_sha256": entry["token_sha256"],
                   "n_tokens": len(entry["token_ids"])} for name, entry in source["variants"].items()}
    prompts = [entry["prompt"] for f in protocol["case_families"] for entry in f["variants"].values()]
    assert prompts and all(prompts) and not [prompt for prompt in prompts if prompt in text]
    counts = bundle["execution"]["counts"]
    assert counts["executed_attempts"] == first["executed"] + second["executed"] + third["executed"] == 27
    assert counts["reused_events"] == first["reused"] + second["reused"] + third["reused"] == 32
    declared = next(m for m in protocol["methods"] if m["id"] == "ica_lens")["basis"]["preprocessing"]
    blocks = [entry["ica"] for family in bundle["comparisons"] for entry in family["comparisons"]]
    assert len(blocks) == 6 and {block["preprocessing_mode"] for block in blocks} == {declared}
    assert all(block["preprocessing_read_from"] for block in blocks)


def test_the_slice_exports_placeholder_prompt_text_only_for_marked_families(tmp_path: Path) -> None:
    """The explicit prompt-text export through the command line (added 2026-11-10). The marker is one string in
    a family's ``facts``; it changes the protocol hash, so the marked protocol is a different run."""
    marked = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    marked["case_families"][0]["facts"].append("publication:prompt_text_approved")
    path, plan, runs = tmp_path / "marked.json", tmp_path / "plan.json", tmp_path / "runs"
    path.write_text(json.dumps(marked), encoding="utf-8")
    assert cli("validate", "--protocol", str(path))["protocol_sha256"] != cli(
        "validate", "--protocol", str(PROTOCOL))["protocol_sha256"]
    cli("plan", "--protocol", str(path), "--out", str(plan))
    cli("run-fixture", "--plan", str(plan), "--fixtures", str(FX), "--protocol", str(path), "--run-dir", str(runs))
    cli("collect", "--run-dir", str(runs), "--require-complete")
    plain = cli("bundle", "--run-dir", str(runs), "--out", str(tmp_path / "plain.json"))
    assert plain["prompt_text_families"] == []
    prompts = {f["family_id"]: [e["prompt"] for e in f["variants"].values()] for f in marked["case_families"]}
    assert not [p for group in prompts.values() for p in group if p in (tmp_path / "plain.json").read_text("utf-8")]
    exported = cli("bundle", "--run-dir", str(runs), "--out", str(tmp_path / "text.json"), "--protocol", str(path))
    assert exported["prompt_text_families"] == ["fam-1"] and exported["limitations"][0] == "synthetic_not_measurement"
    bundle = json.loads((tmp_path / "text.json").read_text(encoding="utf-8"))
    families = {f["family_id"]: f for f in bundle["protocol"]["families"]}
    assert [v["prompt"] for v in families["fam-1"]["variant_text"].values()] == [
        marked["case_families"][0]["variants"][name]["prompt"] for name in sorted(families["fam-1"]["variant_text"])]
    assert "variant_text" not in families["fam-2"] and "variant_text" not in families["fam-3"]
    assert bundle["evidence"]["evidence_class"] == "synthetic_fixture" and bundle["evidence"]["visibility"] == (
        "not_published")
    refused = cli("bundle", "--run-dir", str(runs), "--out", str(tmp_path / "wrong.json"), "--protocol",
                  str(PROTOCOL), expect=2)
    assert refused["code"] == "protocol_mismatch" and not (tmp_path / "wrong.json").exists()


def test_a_changed_input_is_new_work_and_is_refused_in_the_old_run_directory(tmp_path: Path) -> None:
    plan, runs = tmp_path / "plan.json", tmp_path / "runs"
    cli("plan", "--protocol", str(PROTOCOL), "--out", str(plan))
    cli("run-fixture", "--plan", str(plan), "--fixtures", str(FX), "--run-dir", str(runs))
    before = {t["task_id"] for t in json.loads(plan.read_text(encoding="utf-8"))["tasks"]}

    changed = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    changed["seed"] = changed["seed"] + 1                                      # a configuration change
    (tmp_path / "changed.json").write_text(json.dumps(changed), encoding="utf-8")
    plan2 = tmp_path / "plan2.json"
    cli("plan", "--protocol", str(tmp_path / "changed.json"), "--out", str(plan2))
    after = {t["task_id"] for t in json.loads(plan2.read_text(encoding="utf-8"))["tasks"]}
    assert before.isdisjoint(after)                                           # every task identity changed
    refused = cli("run-fixture", "--plan", str(plan2), "--fixtures", str(FX), "--protocol",
                  str(tmp_path / "changed.json"), "--run-dir", str(runs), expect=2)
    assert refused["status"] == "refused" and refused["code"] == "incompatible_resume"


def test_an_independent_replicate_is_executed_not_served_from_the_first(tmp_path: Path) -> None:
    plan, runs = tmp_path / "plan.json", tmp_path / "runs"
    planned = cli("plan", "--protocol", str(PROTOCOL), "--out", str(plan), "--replicates", "2")
    assert planned["totals"]["tasks"] == 90
    result = cli("run-fixture", "--plan", str(plan), "--fixtures", str(FX), "--run-dir", str(runs))
    assert (result["executed"], result["reused"]) == (54, 0)                   # 27 ready tasks, twice


def test_the_slice_cannot_write_into_the_checkout_or_a_measurement_root(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    cli("plan", "--protocol", str(PROTOCOL), "--out", str(plan))
    for target in (ROOT / "exp_runs", ROOT / "trace_out" / "exp_runs", ROOT / "data" / "exp_runs"):
        refused = cli("run-fixture", "--plan", str(plan), "--fixtures", str(FX), "--run-dir", str(target), expect=2)
        assert refused["status"] == "refused"
        assert not target.exists()
