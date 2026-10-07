"""scripts/audit_target_reads.py on synthetic summaries: what it flags, what it counts, what it never writes.

Tokens are abstract stand-ins; no medical vocabulary.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import build_fetcher

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_target_reads as audit  # noqa: E402

import medlang_circuits.batch_eval as batch_eval  # noqa: E402


def out(tok: str) -> str:
    return f'Output "{tok}"'


def pair(i: int, target: str | None) -> dict[str, Any]:
    p: dict[str, Any] = {"top_prompt": f"clin {i}", "bottom_prompt": f"pat {i}"}
    if target is not None:
        p["target_clinical_token"] = target
    return p


def result(i: int, target: str | None, pc: Any, pp: Any, sc: list, sp: list | None, **extra: Any) -> dict:
    r = {"index": i, "mode": "2panel", "prompts": {"clinical": f"clin {i}", "patient": f"pat {i}"},
         "target_token": target, "probabilities": {"clinical": pc, "patient": pp},
         "language_penalty": (pp - pc) if pc is not None and pp is not None else None,
         "predictive_spread": {"clinical": sc, **({"patient": sp} if sp is not None else {})}}
    r.update(extra)
    return r


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def engine(tmp_path: Path) -> Path:
    root = tmp_path / "engine"
    stem = "pairs_20990101T000000Z"
    write(root / f"data/simulated/{stem}.json", [
        pair(1, " qa"), pair(2, " antacid"), pair(3, " antibiotic"), pair(4, " qzr"), pair(5, " qq"),
        pair(6, " antibiotic"),
    ])
    hosted = [
        # 1: consistent on both sides
        result(1, out(" qa"), 0.5, 0.2, [[out(" qa"), 0.5]], [[out(" zz"), 0.3], [out(" qa"), 0.2]]),
        # 2: the target begins a likelier token on the patient side; the legacy read took its value
        result(2, out(" ant"), 0.49, 0.068, [[out(" ant"), 0.49], [out(" anti"), 0.18]],
               [[out(" xtra"), 0.448], [out(" anti"), 0.068], [out(" ant"), 0.041]]),
        # 3: the target is absent on the patient side; its first part carries the recorded value
        result(3, out(" antibiotic"), 0.64, 0.094, [[out(" antibiotic"), 0.64], [out(" anti"), 0.098]],
               [[out(" xtra"), 0.137], [out(" anti"), 0.094]]),
        # 4: the intended target is missing on the clinical side and the top logit was measured instead
        result(4, out(" to"), 0.668, 0.223, [[out(" to"), 0.668]], [[out(" to"), 0.223]]),
        # 5: screened out
        result(5, None, None, None, [[out(" to"), 0.5]], None,
               screening={"status": "screened_out", "intended_target": " qq", "observed_clinical": None}),
        # 6: the wordpiece rule measured ' anti' for ' antibiotic', a token this model returns (result 3)
        result(6, out(" anti"), 0.2, 0.1, [[out(" anti"), 0.2]], [[out(" anti"), 0.1]]),
    ]
    write(root / f"trace_out/{stem}/batch_summary.part_01.json",
          {"mode": "2panel", "backend": "hosted", "graph_model": "gemma-2-2b", "results": hosted})
    # a later part re-records index 3 unchanged: one more occurrence, the same effective result
    write(root / f"trace_out/{stem}/batch_summary.part_06.json",
          {"mode": "2panel", "backend": "hosted", "graph_model": "gemma-2-2b", "results": [hosted[2]]})
    # the logits lane reads by token id: a tie at the spread's cut-off is not a borrowed value
    write(root / f"trace_out/{stem}__qwen3-4b/batch_summary.part_01.json",
          {"mode": "2panel", "backend": "logits", "graph_model": "qwen3-4b", "results": [
              result(3, out(" antibiotic"), 0.3, 0.0197, [[out(" antibiotic"), 0.3]],
                     [[out(" xtra"), 0.5], [out(" anti"), 0.0197]])]})
    # a pilot root with a pairs file under pilot/runs
    write(root / "pilot/runs/run_x/trace/pilot_pairs.json", [pair(1, " qqa")])
    write(root / "pilot/traces/pilot_pairs/batch_summary.part_01.json",
          {"mode": "2panel", "backend": "hosted", "graph_model": "gemma-2-2b", "results": [
              result(1, out(" qqa"), 0.4, 0.1, [[out(" qqa"), 0.4]], [[out(" qqab"), 0.1]])]})
    write(root / "site.json", {"scenarios": [
        {"batch": stem, "batch_index": i, "models": {"gemma-2-2b": {
            "prob_clinical": r["probabilities"]["clinical"], "prob_patient": r["probabilities"]["patient"],
            "anchor_fallback": i == 4}}} for i, r in enumerate(hosted, start=1) if i != 5]})
    return root


def run(engine: Path, tmp_path: Path, *extra: str) -> dict[str, Any]:
    report = tmp_path / "report" / "audit.json"
    assert audit.main(["--root", str(engine), "--out", str(report), *extra]) == 0
    return json.loads(report.read_text(encoding="utf-8"))


def listing(root: Path) -> list[tuple[str, bytes]]:
    return sorted((p.relative_to(root).as_posix(), p.read_bytes()) for p in root.rglob("*") if p.is_file())


def test_the_audit_flags_both_borrow_directions_and_the_substitution(engine, tmp_path):
    before = listing(engine)
    rep = run(engine, tmp_path, "--site-payload", str(engine / "site.json"))
    assert listing(engine) == before  # read only: nothing written into the engine tree
    o = rep["counts"]["overall"]
    assert o["results"] == 8 and o["superseded_duplicate_results"] == 1
    assert o["sides.prefix_mismatch"] == 1
    assert o["sides.target_absent_from_spread.prefix_neighbour"] == 3  # hosted #3, the logits tie, the pilot row
    assert o["results_with_borrowed_value"] == 3                      # hosted #2 and #3, pilot #1
    assert o["published_results_with_borrowed_value"] == 2
    assert o["substitutions"] == 1 and o["target.unrelated"] == 1 and o["published_substitutions"] == 1
    assert o["target.no_measured_token"] == 1 and o["target.leading_wordpiece"] == 2
    assert o["target.leading_wordpiece.intended_is_a_returned_token"] == 1

    mismatch = [f for f in rep["findings"] if f["status"] == "prefix_mismatch"]
    assert len(mismatch) == 1
    m = mismatch[0]
    assert (m["index"], m["side"], m["recorded"], m["exact"]) == (2, "patient", 0.068, [0.041])
    assert m["recorded_carried_by"] == [[out(" anti"), 0.068, "target_is_leading_piece_of_token"]]
    assert m["borrowed"] is True and m["published"] is True and m["payload_probability"] == 0.068

    absent = [f for f in rep["findings"] if f["index"] == 3 and f["backend"] == "hosted"]
    assert [f["effective"] for f in absent] == [False, True]  # both occurrences listed, the later one effective
    assert absent[1]["value_source"] == "prefix_neighbour"
    assert absent[1]["recorded_carried_by"] == [[out(" anti"), 0.094, "token_is_leading_piece_of_target"]]

    tie = [f for f in rep["findings"] if f["backend"] == "logits"]
    assert len(tie) == 1 and tie[0]["value_source"] == "prefix_neighbour" and tie[0]["borrowed"] is False

    (sub,) = [s for s in rep["substitutions"] if s["effective"]]
    assert (sub["index"], sub["intended_target"], sub["measured_token"], sub["relation"]) == (
        4, " qzr", out(" to"), "unrelated")
    assert sub["intended_source"] == "pairs_file" and sub["site_anchor_fallback"] is True
    assert sub["payload_anchor_fallback"] is True

    (wp,) = rep["wordpiece_reads_of_returned_tokens"]
    assert (wp["index"], wp["intended_target"], wp["measured_token"]) == (6, " antibiotic", out(" anti"))

    c = rep["counts"]
    assert c["by_root"]["pilot/traces"]["results_with_borrowed_value"] == 1
    assert c["by_model"]["qwen3-4b"].get("results_with_borrowed_value", 0) == 0
    assert c["by_batch"]["pairs_20990101T000000Z"]["results_with_borrowed_value"] == 2
    assert rep["joins"] == {"verified": 7}


def test_a_join_whose_prompts_differ_is_refused_not_guessed(engine, tmp_path):
    p = engine / "data/simulated/pairs_20990101T000000Z.json"
    pairs = json.loads(p.read_text(encoding="utf-8"))
    pairs[3]["top_prompt"] = "something else"
    p.write_text(json.dumps(pairs), encoding="utf-8")
    rep = run(engine, tmp_path)
    assert rep["counts"]["overall"]["target.intended_unknown"] == 1
    assert rep["counts"]["overall"].get("substitutions", 0) == 0
    assert rep["joins"]["refused_prompt_mismatch"] == 1


def test_the_report_is_never_written_under_a_trace_root(engine, tmp_path):
    with pytest.raises(audit.AuditRefusal, match="trace root"):
        audit.main(["--root", str(engine), "--out", str(engine / "trace_out" / "x.json")])
    with pytest.raises(audit.AuditRefusal, match="trace root"):
        audit.main(["--root", str(engine), "--out", str(engine / "pilot/traces/sub/x.json")])
    with pytest.raises(SystemExit):
        audit.main(["--root", str(engine)])  # --out is required: there is no default path
    assert not (engine / "trace_out" / "x.json").exists()


def test_results_written_by_the_new_read_carry_no_borrowed_value(tmp_path, monkeypatch):
    # The legacy read would have recorded ' anti' (0.068) and ' anti' (0.094) on these patient sides.
    spreads = {"clin a": [(" ant", 0.49), (" anti", 0.18)], "pat a": [(" xtra", 0.4), (" anti", 0.068), (" ant", 0.041)],
               "clin b": [(" antibiotic", 0.64), (" anti", 0.09)], "pat b": [(" xtra", 0.1), (" anti", 0.094)]}

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        from test_target_exact_read import hosted_graph
        return hosted_graph(spreads[prompt])

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    root = tmp_path / "engine"
    stem = "pairs_20990202T000000Z"
    pairs = [{"top_prompt": "clin a", "bottom_prompt": "pat a", "target_clinical_token": " antacid"},
             {"top_prompt": "clin b", "bottom_prompt": "pat b", "target_clinical_token": " antibiotic"}]
    write(root / f"data/simulated/{stem}.json", pairs)
    batch_eval.run_batch(str(root / f"data/simulated/{stem}.json"), out_dir=str(tmp_path / "run"), dpi=40,
                         fetcher=build_fetcher())
    (root / f"trace_out/{stem}").mkdir(parents=True)
    shutil.copy(tmp_path / "run" / "batch_summary.json", root / f"trace_out/{stem}/batch_summary.part_01.json")
    rep = run(root, tmp_path)
    o = rep["counts"]["overall"]
    assert o["results"] == 2 and o.get("results_with_borrowed_value", 0) == 0
    assert o["sides.consistent"] == 3 and o["sides.not_measured"] == 1  # the absent target is null, not borrowed
