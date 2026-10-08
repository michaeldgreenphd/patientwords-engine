"""scripts/audit_target_reads.py on synthetic summaries: what it flags, what it counts, what it never writes.

Every token here is an abstract stand-in (' xab', ' xabi', ' xabicor', ...) chosen only for its prefix relations.
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

STEM = "pairs_20990101T000000Z"


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


def passed(intended: str) -> dict[str, Any]:
    return {"screening": {"status": "passed", "intended_target": intended, "min_prob": 0.02}}


INTENDED = {1: " qa", 2: " xabmel", 3: " xabicor", 4: " qzr", 5: " qq", 6: " xabicor", 7: " qup", 8: " qtx",
            9: " qecto", 10: " qzt", 11: " qzz", 12: " qambel"}


@pytest.fixture
def engine(tmp_path: Path) -> Path:
    root = tmp_path / "engine"
    write(root / f"data/simulated/{STEM}.json", [pair(i, INTENDED[i]) for i in range(1, 13)])
    hosted = [
        # 1: consistent on both sides
        result(1, out(" qa"), 0.5, 0.2, [[out(" qa"), 0.5]], [[out(" zz"), 0.3], [out(" qa"), 0.2]]),
        # 2: the target begins a likelier token on the patient side; the legacy read took its value
        result(2, out(" xab"), 0.49, 0.068, [[out(" xab"), 0.49], [out(" xabi"), 0.18]],
               [[out(" qqq"), 0.448], [out(" xabi"), 0.068], [out(" xab"), 0.041]]),
        # 3: the target is absent on the patient side; its first part carries the recorded value
        result(3, out(" xabicor"), 0.64, 0.094, [[out(" xabicor"), 0.64], [out(" xabi"), 0.098]],
               [[out(" qqq"), 0.137], [out(" xabi"), 0.094]]),
        # 4: the intended target is missing on the clinical side and the top logit was measured instead
        result(4, out(" to"), 0.668, 0.223, [[out(" to"), 0.668]], [[out(" to"), 0.223]]),
        # 5: screened out
        result(5, None, None, None, [[out(" to"), 0.5]], None,
               screening={"status": "screened_out", "intended_target": " qq", "observed_clinical": None}),
        # 6: the wordpiece rule measured ' xabi' for ' xabicor', a token this model returns (result 3); its
        # translated side, which no published field carries, took a likelier extension's value
        result(6, out(" xabi"), 0.2, 0.1, [[out(" xabi"), 0.2]], [[out(" xabi"), 0.1]]),
        # 7: the legacy prefix match took a likelier extension of the intended word, on the screened path
        result(7, out(" qupel"), 0.5, 0.2, [[out(" qupel"), 0.5]], [[out(" qupel"), 0.2]], **passed(" qup")),
        # 8: a case variant (the legacy match folded case)
        result(8, out(" QTX"), 0.4, 0.1, [[out(" QTX"), 0.4]], [[out(" QTX"), 0.1]]),
        # 9: a two-character top logit that happens to begin the intended word: neither read accepts it
        result(9, out(" qe"), 0.3, 0.1, [[out(" qe"), 0.3]], [[out(" qe"), 0.1]]),
        # 10: the target is absent on the patient side and only an unrelated token shares its value: not borrowed
        result(10, out(" qzt"), 0.3, 0.05, [[out(" qzt"), 0.3]], [[out(" zzz"), 0.05]]),
        # 11: a top-logit substitution that a later re-run part replaces (the two reading rules differ)
        result(11, out(" to"), 0.6, 0.3, [[out(" to"), 0.6]], [[out(" to"), 0.3]]),
        # 12: a case-variant leading piece the site's case-insensitive rule does not flag
        result(12, out(" Qam"), 0.3, 0.1, [[out(" Qam"), 0.3]], [[out(" Qam"), 0.1]], **passed(" qambel")),
    ]
    hosted[5]["probabilities"]["translated"] = 0.09
    hosted[5]["predictive_spread"]["translated"] = [[out(" xabis"), 0.09]]
    summary = {"mode": "2panel", "backend": "hosted", "graph_model": "gemma-2-2b"}
    write(root / f"trace_out/{STEM}/batch_summary.part_01.json", {**summary, "results": hosted})
    # a later part re-records index 3 unchanged: one more occurrence, the same effective result
    write(root / f"trace_out/{STEM}/batch_summary.part_06.json", {**summary, "results": [hosted[2]]})
    # a later part re-measures index 11 exactly: the exporter reads it, urgency_shift keeps the first
    write(root / f"trace_out/{STEM}/batch_summary.part_09.json", {**summary, "results": [
        result(11, out(" qzz"), 0.4, 0.2, [[out(" qzz"), 0.4]], [[out(" qzz"), 0.2]], **passed(" qzz"))]})
    # the logits lane reads by token id: a tie at the spread's cut-off is not a borrowed value, and a short
    # first token is its documented first-token rule, not a substitution
    logits = {"mode": "2panel", "backend": "logits", "graph_model": "qwen3-4b"}
    write(root / f"trace_out/{STEM}__qwen3-4b/batch_summary.part_01.json", {**logits, "results": [
        result(3, out(" xabicor"), 0.3, 0.0197, [[out(" xabicor"), 0.3]], [[out(" qqq"), 0.5], [out(" xabi"), 0.0197]]),
        result(9, out(" qe"), 0.3, 0.1, [[out(" qe"), 0.3]], [[out(" qe"), 0.1]])]})
    # a gemma-2-2b logits directory the site exporter never reads: never published, whatever the payload holds
    write(root / f"trace_out/{STEM}__gemma-2-2b/batch_summary.part_01.json", {**logits, "graph_model": "gemma-2-2b",
          "results": [result(4, out(" "), 0.2, 0.1, [[out(" "), 0.2]], [[out(" "), 0.1]])]})
    # a pilot root with a pairs file under pilot/runs
    write(root / "pilot/runs/run_x/trace/pilot_pairs.json", [pair(1, " qqa")])
    write(root / "pilot/traces/pilot_pairs/batch_summary.part_01.json",
          {**summary, "results": [result(1, out(" qqa"), 0.4, 0.1, [[out(" qqa"), 0.4]], [[out(" qqab"), 0.1]])]})
    published = {i: r for i, r in enumerate(hosted, start=1) if i not in (5, 11)}
    write(root / "site.json", {"scenarios": [
        {"batch": STEM, "batch_index": i, "models": {"gemma-2-2b": {
            "prob_clinical": r["probabilities"]["clinical"], "prob_patient": r["probabilities"]["patient"],
            "anchor_fallback": i in (4, 7)}}} for i, r in published.items()]})
    return root


def run(engine: Path, tmp_path: Path, *extra: str) -> dict[str, Any]:
    report = tmp_path / "report" / "audit.json"
    assert audit.main(["--root", str(engine), "--out", str(report), *extra]) == 0
    return json.loads(report.read_text(encoding="utf-8"))


def listing(root: Path) -> list[tuple[str, bytes]]:
    return sorted((p.relative_to(root).as_posix(), p.read_bytes()) for p in root.rglob("*") if p.is_file())


def subs(rep: dict[str, Any], **match: Any) -> list[dict[str, Any]]:
    return [s for s in rep["substitutions"] if all(s.get(k) == v for k, v in match.items())]


def test_the_audit_flags_both_borrow_directions(engine, tmp_path):
    before = listing(engine)
    rep = run(engine, tmp_path, "--site-payload", str(engine / "site.json"))
    assert listing(engine) == before  # read only: nothing written into the engine tree
    o = rep["counts"]["overall"]
    assert o["results"] == 16 and rep["superseded_duplicate_results"] == 2
    assert o["sides.prefix_mismatch"] == 1
    # hosted #3, hosted #6's translated side, the logits tie, the pilot row
    assert o["sides.target_absent_from_spread.prefix_neighbour"] == 4
    assert o["sides.target_absent_from_spread.unrelated_token"] == 1   # hosted #10
    assert o["results_with_borrowed_value"] == 4                       # hosted #2, #3 and #6, pilot #1
    assert o["published_results_with_borrowed_value"] == 3
    # #6 is borrowed on its translated side only, which no published field carries
    assert o["published_results_with_borrowed_value_in_a_published_field"] == 2
    (tx,) = [f for f in rep["findings"] if f["index"] == 6 and f["side"] == "translated"]
    assert tx["borrowed"] is True and tx["published"] is True and tx["published_field"] is None

    (m,) = [f for f in rep["findings"] if f["status"] == "prefix_mismatch"]
    assert (m["index"], m["side"], m["recorded"], m["exact"]) == (2, "patient", 0.068, [0.041])
    assert m["recorded_carried_by"] == [[out(" xabi"), 0.068, "target_is_leading_piece_of_token"]]
    assert m["borrowed"] is True and m["published"] is True and m["payload_probability"] == 0.068
    assert m["published_field"] == "prob_patient"

    absent = [f for f in rep["findings"] if f["index"] == 3 and f["backend"] == "hosted"]
    assert [f["effective"] for f in absent] == [False, True]  # both occurrences listed, the later one effective
    assert absent[1]["value_source"] == "prefix_neighbour"
    assert absent[1]["recorded_carried_by"] == [[out(" xabi"), 0.094, "token_is_leading_piece_of_target"]]

    (tie,) = [f for f in rep["findings"] if f["backend"] == "logits" and f["index"] == 3]
    assert tie["value_source"] == "prefix_neighbour" and tie["borrowed"] is False
    (unrelated,) = [f for f in rep["findings"] if f["index"] == 10]
    assert unrelated["value_source"] == "unrelated_token" and unrelated["borrowed"] is False

    c = rep["counts"]
    assert c["by_root"]["pilot/traces"]["results_with_borrowed_value"] == 1
    assert c["by_model"]["qwen3-4b"].get("results_with_borrowed_value", 0) == 0
    assert c["by_batch"][STEM]["results_with_borrowed_value"] == 3


def test_the_audit_classifies_each_kind_of_substitution(engine, tmp_path):
    rep = run(engine, tmp_path, "--site-payload", str(engine / "site.json"))
    o = rep["counts"]["overall"]
    # hosted: #4 top logit, #7 extension, #8 case variant, #9 short piece, #12 case-variant piece; logits: the
    # bare-space first token in the gemma logits directory. Not: the logits short first token (#9 on qwen).
    assert o["substitutions"] == 6
    assert o["target.unrelated"] == 1 and o["target.extension"] == 1 and o["target.case_variant"] == 1
    assert o["target.case_variant_wordpiece"] == 1 and o["target.whitespace_token"] == 1
    assert o["target.short_leading_wordpiece"] == 2 and o["target.no_measured_token"] == 1
    assert o["target.leading_wordpiece"] == 2 and o["target.leading_wordpiece.intended_is_a_returned_token"] == 1

    (ext,) = subs(rep, index=7)
    assert ext["relation"] == "extension" and ext["screening_status"] == "passed" and ext["intended_source"] == "screening"
    assert ext["site_anchor_fallback"] is True and ext["payload_anchor_fallback"] is True
    (case,) = subs(rep, index=8)
    assert case["relation"] == "case_variant" and case["site_anchor_fallback"] is False
    (piece,) = subs(rep, index=12)
    assert piece["relation"] == "case_variant_wordpiece" and piece["site_anchor_fallback"] is False  # case-blind rule
    (short,) = subs(rep, index=9, backend="hosted")
    assert short["relation"] == "short_leading_wordpiece" and short["published"] is True
    assert not subs(rep, index=9, backend="logits")
    (top,) = subs(rep, index=4, backend="hosted")
    assert top["relation"] == "unrelated" and top["site_anchor_fallback"] is True and top["intended_source"] == "pairs_file"
    (ws,) = subs(rep, backend="logits")
    assert ws["dir"].endswith("__gemma-2-2b") and ws["relation"] == "whitespace_token" and ws["published"] is False

    assert o["published_substitutions"] == 5 and o["published_substitutions_not_flagged"] == 3  # #8, #9, #12

    (wp,) = rep["wordpiece_reads_of_returned_tokens"]
    assert (wp["index"], wp["intended_target"], wp["measured_token"]) == (6, " xabicor", out(" xabi"))
    assert rep["joins"] == {"verified": 12}  # the other effective results name their target in screening


def test_both_reading_rules_are_counted(engine, tmp_path):
    rep = run(engine, tmp_path)
    last, first = rep["counts"]["overall"], rep["counts_urgency_first_part"]["overall"]
    # index 11: the exporter reads the exact re-run, urgency_shift the earlier substituted part
    assert [s["effective"] for s in subs(rep, index=11)] == [False]
    assert subs(rep, index=11)[0]["urgency_read"] is True
    # urgency_shift keys rows by (model, batch, index) across directories: the gemma-2-2b logits directory's #4
    # repeats the hosted directory's key, which sorts first, so that substitution is not in its rows
    (ws,) = subs(rep, backend="logits")
    assert ws["effective"] is True and ws["urgency_read"] is False
    assert last["substitutions"] == 6 and first["substitutions"] == 6
    assert {s["index"] for s in subs(rep, urgency_read=True)} == {4, 7, 8, 9, 11, 12}
    # urgency_shift skips results without both spreads (the screened-out #5) and never reads pilot/traces
    assert last["results"] == 16 and first["results"] == 13
    assert "pilot/traces" not in rep["counts_urgency_first_part"]["by_root"]


def test_a_join_whose_prompts_differ_is_refused_not_guessed(engine, tmp_path):
    p = engine / f"data/simulated/{STEM}.json"
    pairs = json.loads(p.read_text(encoding="utf-8"))
    pairs[3]["top_prompt"] = "something else"
    p.write_text(json.dumps(pairs), encoding="utf-8")
    rep = run(engine, tmp_path)
    assert rep["counts"]["overall"]["target.intended_unknown"] == 2  # hosted #4 and the gemma logits #4
    assert not subs(rep, index=4)
    assert rep["joins"]["refused_prompt_mismatch"] == 2


def test_the_report_is_never_written_under_a_trace_root(engine, tmp_path):
    with pytest.raises(audit.AuditRefusal, match="trace root"):
        audit.main(["--root", str(engine), "--out", str(engine / "trace_out" / "x.json")])
    with pytest.raises(audit.AuditRefusal, match="trace root"):
        audit.main(["--root", str(engine), "--out", str(engine / "pilot/traces/sub/x.json")])
    with pytest.raises(SystemExit):
        audit.main(["--root", str(engine)])  # --out is required: there is no default path
    assert not (engine / "trace_out" / "x.json").exists()


def _new_read_engine(tmp_path: Path, monkeypatch, spreads: dict[str, list[tuple[str, float]]],
                     pairs: list[dict[str, Any]]) -> Path:
    from test_target_exact_read import hosted_graph

    monkeypatch.setattr(batch_eval, "generate_graph",
                        lambda prompt, slug=None, backend="hosted", **params: hosted_graph(spreads[prompt]))
    root = tmp_path / "engine"
    stem = "pairs_20990202T000000Z"
    write(root / f"data/simulated/{stem}.json", pairs)
    batch_eval.run_batch(str(root / f"data/simulated/{stem}.json"), out_dir=str(tmp_path / "run"), dpi=40,
                         fetcher=build_fetcher())
    (root / f"trace_out/{stem}").mkdir(parents=True)
    shutil.copy(tmp_path / "run" / "batch_summary.json", root / f"trace_out/{stem}/batch_summary.part_01.json")
    return root


def test_results_written_by_the_new_read_carry_no_borrowed_value(tmp_path, monkeypatch):
    # The legacy read would have recorded ' xabi' (0.068) and ' xabi' (0.094) on these patient sides.
    root = _new_read_engine(tmp_path, monkeypatch, {
        "clin a": [(" xab", 0.49), (" xabi", 0.18)], "pat a": [(" qqq", 0.4), (" xabi", 0.068), (" xab", 0.041)],
        "clin b": [(" xabicor", 0.64), (" xabi", 0.09)], "pat b": [(" qqq", 0.1), (" xabi", 0.094)]},
        [{"top_prompt": "clin a", "bottom_prompt": "pat a", "target_clinical_token": " xabmel"},
         {"top_prompt": "clin b", "bottom_prompt": "pat b", "target_clinical_token": " xabicor"}])
    rep = run(root, tmp_path, "--trace-root", "trace_out")
    o = rep["counts"]["overall"]
    assert o["results"] == 2 and o.get("results_with_borrowed_value", 0) == 0
    assert o["sides.consistent"] == 3 and o["sides.not_measured"] == 1  # the absent target is null, not borrowed


def test_a_new_exact_read_tied_at_the_display_cut_is_consistent(tmp_path, monkeypatch):
    # The patient target ties with a prefix neighbour at the fifth/sixth place: the stored top-five spread holds
    # the neighbour, not the target. The result's own target_read record says the value is the target's.
    root = _new_read_engine(tmp_path, monkeypatch, {
        "clin a": [(" xab", 0.49), (" xabi", 0.18)],
        "pat a": [(" q1z", 0.3), (" q2z", 0.2), (" q3z", 0.1), (" q4z", 0.05), (" xabi", 0.041), (" xab", 0.041),
                  (" q7z", 0.01)]},
        [{"top_prompt": "clin a", "bottom_prompt": "pat a", "target_clinical_token": " xabmel"}])
    summary = json.loads(next((root / "trace_out").rglob("batch_summary.part_01.json")).read_text(encoding="utf-8"))
    r = summary["results"][0]
    assert r["probabilities"]["patient"] == 0.041
    assert out(" xab") not in [t for t, _ in r["predictive_spread"]["patient"]]
    rep = run(root, tmp_path, "--trace-root", "trace_out")
    assert rep["counts"]["overall"].get("results_with_borrowed_value", 0) == 0
    assert rep["counts"]["overall"]["sides.consistent"] == 2


def test_a_sides_own_read_counts_only_when_it_records_that_value():
    target = out(" xab")
    spread = [[out(" qqq"), 0.448], [out(" xabi"), 0.068], [out(" xab"), 0.041]]
    agrees = {"status": "exact", "token": target, "probability": 0.041}
    assert audit.check_side(target, 0.041, spread, agrees) == {"status": "consistent", "identity": "target_read"}
    differs = {"status": "exact", "token": target, "probability": 0.041}
    assert audit.check_side(target, 0.068, spread, differs)["status"] == "prefix_mismatch"
    other = {"status": "exact", "token": out(" xabi"), "probability": 0.068}
    assert audit.check_side(target, 0.068, spread, other)["status"] == "prefix_mismatch"
    missing = {"status": "missing", "reason": "target_not_in_returned_logits"}
    assert audit.check_side(target, 0.068, spread, missing)["status"] == "prefix_mismatch"


def test_relations_keep_the_leading_space():
    assert audit.relation(out(" xab"), " xab") == "exact"
    assert audit.relation(out(" xab"), "xab") == "exact"  # an unspaced intended word gets its space, as the read does
    assert audit.relation(out("xab"), " xab") == "space_variant"
    assert audit.relation(out("xab"), " xabmel") == "space_variant_wordpiece"
    assert audit.relation(out(" xab"), " xabmel") == "leading_wordpiece"
    assert audit.relation(out(" xa"), " xabmel") == "short_leading_wordpiece"
    assert audit.relation(out(" Xab"), " xab") == "case_variant"
    assert audit.relation(out(" xabicors"), " xabicor") == "extension"
    assert audit.relation(out(" "), " xab") == "whitespace_token"
    assert audit.is_substitution("space_variant", "logits") and audit.is_substitution("short_leading_wordpiece", "hosted")
    assert not audit.is_substitution("short_leading_wordpiece", "logits")


def test_the_first_part_rule_skips_translated_corpus_directories(tmp_path):
    # urgency_shift.py never ingests txcorpus_ directories: their "patient" side is a rewrite
    root = tmp_path / "engine"
    stem = "txcorpus_20990101T000000Z"
    write(root / f"data/simulated/{stem}.json", [pair(1, " qzr")])
    write(root / f"trace_out/{stem}/batch_summary.part_01.json", {"mode": "2panel", "backend": "hosted",
          "graph_model": "gemma-2-2b", "results": [result(1, out(" to"), 0.6, 0.3, [[out(" to"), 0.6]],
                                                          [[out(" to"), 0.3]])]})
    rep = run(root, tmp_path, "--trace-root", "trace_out")
    assert rep["counts"]["overall"]["substitutions"] == 1
    assert rep["counts_urgency_first_part"]["overall"] == {}
    (s,) = subs(rep)
    assert s["effective"] is True and s["urgency_read"] is False


def test_a_missing_trace_root_is_refused_not_read_as_clean(engine, tmp_path):
    shutil.rmtree(engine / "pilot/traces")
    with pytest.raises(audit.AuditRefusal, match="pilot/traces"):
        audit.main(["--root", str(engine), "--out", str(tmp_path / "r.json")])
    assert not (tmp_path / "r.json").exists()
    assert run(engine, tmp_path, "--trace-root", "trace_out")["inputs"]["trace_roots"] == ["trace_out"]


def test_a_dirty_checkout_is_marked_in_the_provenance(engine, tmp_path):
    import subprocess
    git = ["git", "-C", str(engine), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
           "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "fixture"], check=True)
    clean = run(engine, tmp_path)["engine_sha"]
    assert clean and not clean.endswith("+dirty")
    (engine / "trace_out" / "note.txt").write_text("uncommitted", encoding="utf-8")
    assert run(engine, tmp_path)["engine_sha"] == clean + "+dirty"


def test_numeric_part_order_is_marked_beside_the_exporters_name_order(tmp_path):
    # backend_agreement.py reads part_100 after part_36; the exporter's name sort reads part_36 last
    root = tmp_path / "engine"
    stem = "pairs_20990404T000000Z"
    write(root / f"data/simulated/{stem}.json", [pair(i, " qa") for i in range(1, 6)])
    summary = {"mode": "2panel", "backend": "hosted", "graph_model": "gemma-2-2b"}
    write(root / f"trace_out/{stem}/batch_summary.part_36.json", {**summary, "results": [
        result(5, out(" qa"), 0.5, 0.2, [[out(" qa"), 0.5]], [[out(" qa"), 0.2]])]})
    write(root / f"trace_out/{stem}/batch_summary.part_100.json", {**summary, "results": [
        result(5, out(" to"), 0.5, 0.2, [[out(" to"), 0.5]], [[out(" to"), 0.2]])]})
    rep = run(root, tmp_path, "--trace-root", "trace_out")
    assert rep["part_order_disagreements"] == [{"dir": f"trace_out/{stem}", "index": 5,
                                                "last_part": f"trace_out/{stem}/batch_summary.part_36.json",
                                                "numeric_last_part": f"trace_out/{stem}/batch_summary.part_100.json"}]
    (sub,) = subs(rep)  # the part_100 substitution: backend_agreement's reading, not the exporter's
    assert sub["numeric_last_part"] is True and sub["effective"] is False


@pytest.mark.parametrize("bad,why", [
    ({"mode": "2panel"}, "no results"), ({"results": None}, "results is not a list"),
    ({"results": {"1": {}}}, "results is not a list"), ([], "root is not an object"),
    ({"results": [1, "x"]}, "a result is not an object"),
])
def test_a_malformed_summary_is_refused_not_read_as_zero_rows(engine, tmp_path, bad, why):
    write(engine / f"trace_out/{STEM}/batch_summary.part_99.json", bad)
    with pytest.raises(audit.AuditRefusal, match=rf"trace_out/{STEM}/batch_summary.part_99.json \({why}\)"):
        audit.main(["--root", str(engine), "--out", str(tmp_path / "r.json")])
    assert not (tmp_path / "r.json").exists()


def test_an_empty_summary_is_read_and_listed(engine, tmp_path):
    write(engine / f"trace_out/{STEM}/batch_summary.part_99.json", {"mode": "2panel", "results": []})
    rep = run(engine, tmp_path)
    assert rep["empty_summaries"] == [f"trace_out/{STEM}/batch_summary.part_99.json"]
    assert rep["counts"]["overall"]["results"] == 16


def test_the_report_rules_name_the_reader_of_each_order(engine, tmp_path):
    counting = run(engine, tmp_path)["rules"]["counting"]
    exporter_rule = counting.split(";")[0]
    assert "file-name order" in exporter_rule and "backend_agreement" not in exporter_rule
    assert "numeric_last_part" in counting



@pytest.mark.parametrize("spread,why", [
    ({"clinical": [[out(" qa"), "bad"]]}, "malformed entry"), ({"clinical": [[out(" qa")]]}, "malformed entry"),
    ({"clinical": [[3, 0.5]]}, "malformed entry"), ({"clinical": [[out(" qa"), float("nan")]]}, "malformed entry"),
    ({"clinical": [[out(" qa"), True]]}, "malformed entry"), ({"clinical": None}, "is not a list"),
    ([[out(" qa"), 0.5]], "is not an object"),
])
def test_a_malformed_spread_entry_is_refused_not_dropped(engine, tmp_path, spread, why):
    r = result(1, out(" qa"), 0.5, 0.2, [[out(" qa"), 0.5]], [[out(" qa"), 0.2]])
    r["predictive_spread"] = spread
    path = engine / f"trace_out/{STEM}/batch_summary.part_99.json"
    path.write_text(json.dumps({"mode": "2panel", "results": [r]}), encoding="utf-8")  # NaN is written as NaN
    with pytest.raises(audit.AuditRefusal, match=rf"batch_summary.part_99.json \(index 1: predictive_spread.*{why}"):
        audit.main(["--root", str(engine), "--out", str(tmp_path / "r.json")])


def test_a_dialect_spreads_variants_are_validated_too(engine, tmp_path):
    r = {"index": 1, "mode": "dialect", "baseline_probability": 0.5, "target_token": out(" qa"),
         "variants": [{"probability": 0.2}], "predictive_spread": {"baseline": [[out(" qa"), 0.5]],
                                                                  "variants": [[[out(" qa"), "x"]]]}}
    write(engine / f"trace_out/{STEM}/batch_summary.part_99.json", {"mode": "dialect", "results": [r]})
    with pytest.raises(audit.AuditRefusal, match="predictive_spread.variants holds a malformed entry"):
        audit.main(["--root", str(engine), "--out", str(tmp_path / "r.json")])


def test_an_index_repeated_within_one_part_is_read_as_each_consumer_reads_it(tmp_path):
    # exporter and archive keep the LAST occurrence in a part; urgency_shift keeps the FIRST eligible one
    root = tmp_path / "engine"
    stem = "pairs_20990505T000000Z"
    write(root / f"data/simulated/{stem}.json", [pair(1, " qa")])
    first = result(1, out(" to"), 0.6, 0.3, [[out(" to"), 0.6]], [[out(" to"), 0.3]])   # a substitution
    last = result(1, out(" qa"), 0.5, 0.2, [[out(" qa"), 0.5]], [[out(" qa"), 0.2]])    # exact
    write(root / f"trace_out/{stem}/batch_summary.part_01.json",
          {"mode": "2panel", "backend": "hosted", "graph_model": "gemma-2-2b", "results": [first, last]})
    rep = run(root, tmp_path, "--trace-root", "trace_out")
    assert rep["counts"]["overall"]["results"] == 1 and rep["counts_urgency_first_part"]["overall"]["results"] == 1
    assert rep["counts"]["overall"].get("substitutions", 0) == 0
    assert rep["counts_urgency_first_part"]["overall"]["substitutions"] == 1
    (sub,) = subs(rep)
    assert (sub["position"], sub["effective"], sub["urgency_read"]) == (0, False, True)
    assert rep["superseded_duplicate_results"] == 1


def test_a_well_formed_dialect_spread_is_read(engine, tmp_path):
    r = {"index": 1, "mode": "dialect", "baseline_probability": 0.5, "target_token": out(" qa"),
         "variants": [{"probability": 0.2}], "predictive_spread": {"baseline": [[out(" qa"), 0.5]],
                                                                  "variants": [[[out(" qa"), 0.2]]]}}
    write(engine / f"trace_out/{STEM}/batch_summary.part_99.json", {"mode": "dialect", "results": [r]})
    assert run(engine, tmp_path)["counts"]["overall"]["sides.consistent"] > 0


@pytest.mark.parametrize("change,why", [
    ({"probabilities": []}, "probabilities is absent or not an object"),
    ({"probabilities": None}, "probabilities is absent or not an object"),
    ({"probabilities": {"clinical": 0.5}}, "probabilities lacks patient"),
    ({"probabilities": {"clinical": 0.5, "patient": 0.2, "x": 0.1}}, "probabilities has unexpected sides x"),
    ({"probabilities": {"clinical": "0.5", "patient": 0.2}}, "a probability is not a number or null"),
    ({"mode": "fivepanel"}, "unknown mode"),
])
def test_a_malformed_probability_collection_is_refused_not_read_as_no_sides(engine, tmp_path, change, why):
    r = result(1, out(" qa"), 0.5, 0.2, [[out(" qa"), 0.5]], [[out(" qa"), 0.2]])
    r.update(change)
    write(engine / f"trace_out/{STEM}/batch_summary.part_99.json", {"mode": "2panel", "results": [r]})
    with pytest.raises(audit.AuditRefusal, match=rf"part_99.json \(index 1: {why}"):
        audit.main(["--root", str(engine), "--out", str(tmp_path / "r.json")])


@pytest.mark.parametrize("change,why", [
    ({"baseline_probability": "x"}, "baseline_probability is absent"),
    ({"variants": [{"prompt": "v"}]}, "variants is not a list of objects each with a probability"),
    ({"variants": None}, "variants is not a list of objects each with a probability"),
])
def test_a_malformed_dialect_probability_is_refused(engine, tmp_path, change, why):
    r = {"index": 1, "mode": "dialect", "baseline_probability": 0.5, "target_token": out(" qa"),
         "variants": [{"probability": 0.2}], "predictive_spread": {"baseline": [[out(" qa"), 0.5]]}}
    r.update(change)
    write(engine / f"trace_out/{STEM}/batch_summary.part_99.json", {"mode": "dialect", "results": [r]})
    with pytest.raises(audit.AuditRefusal, match=why):
        audit.main(["--root", str(engine), "--out", str(tmp_path / "r.json")])


def _dialect_engine(tmp_path: Path, source_variants: list[str]) -> Path:
    root = tmp_path / "engine"
    stem = "dialects_20990606T000000Z"
    write(root / f"data/simulated/{stem}.json", [{"baseline_prompt": "base one", "target_clinical_token": " qzr",
                                                 "variants": [{"dialect": f"d{i}", "prompt": p}
                                                              for i, p in enumerate(source_variants)]}])
    r = {"index": 1, "mode": "dialect", "baseline_prompt": "base one", "target_token": out(" to"),
         "baseline_probability": 0.5, "variants": [{"prompt": "var a", "probability": 0.2},
                                                   {"prompt": "var b", "probability": 0.1}],
         "predictive_spread": {"baseline": [[out(" to"), 0.5]], "variants": [[[out(" to"), 0.2]], [[out(" to"), 0.1]]]}}
    write(root / f"trace_out/{stem}/batch_summary.part_01.json", {"mode": "dialect", "backend": "hosted",
                                                                  "graph_model": "gemma-2-2b", "results": [r]})
    return root


def test_a_dialect_join_checks_every_variant_prompt_in_order(tmp_path):
    rep = run(_dialect_engine(tmp_path / "same", ["var a", "var b"]), tmp_path / "same", "--trace-root", "trace_out")
    assert rep["joins"] == {"verified": 1} and rep["counts"]["overall"]["substitutions"] == 1
    for name, variants in (("order", ["var b", "var a"]), ("other", ["var a", "var c"]), ("fewer", ["var a"])):
        rep = run(_dialect_engine(tmp_path / name, variants), tmp_path / name, "--trace-root", "trace_out")
        assert rep["joins"] == {"refused_prompt_mismatch": 1}, name
        assert rep["counts"]["overall"]["target.intended_unknown"] == 1 and not subs(rep), name


def test_the_compact_evidence_lists_published_rows_and_the_quoted_figures(engine, tmp_path):
    compact_path = tmp_path / "compact.json"
    rep = run(engine, tmp_path, "--site-payload", str(engine / "site.json"), "--compact-out", str(compact_path),
              "--site-ref", "site@abc")
    c = json.loads(compact_path.read_text(encoding="utf-8"))
    assert c["schema"] == "patientwords-target-read-audit-compact/1"
    assert c["site_payload"]["sha256"] == rep["inputs"]["site_payload"]["sha256"]
    assert c["site_payload"]["site_ref"] == "site@abc" and c["engine_sha"] == rep["engine_sha"]
    assert c["counts_last_part"]["overall"] == rep["counts"]["overall"]
    assert c["counts_urgency_first_part"]["overall"] == rep["counts_urgency_first_part"]["overall"]
    rows = {r["index"]: r for r in c["published_rows"]}
    # borrowed #2 (patient, published field) and #3; #6 translated-only borrow and wordpiece; substitutions #4,7,8,9,12
    assert sorted(rows) == [2, 3, 4, 6, 7, 8, 9, 12]
    assert rows[2]["borrowed"][0]["published_field"] == "prob_patient"
    assert rows[6]["borrowed"][0]["side"] == "translated" and "published_field" not in rows[6]["borrowed"][0]
    assert rows[6]["wordpiece"] == {"intended_target": " xabicor", "measured_token": out(" xabi")}
    assert rows[7]["substitution"]["mechanism"] == "prefix_match"
    assert rows[9]["substitution"]["mechanism"] == "top_logit_fallback"
    q = c["quoted"]
    assert q["published_scenarios_borrowed_in_a_published_field"] == 2
    assert q["published_substituted_rows"] == 5 and q["published_substituted_rows_not_flagged"] == 3
    assert q["published_substituted_rows_by_mechanism"] == {"prefix_match": 3, "top_logit_fallback": 2}
    assert (q["prefix_match_extensions"], q["prefix_match_case_variants"], q["prefix_match_screened"]) == (1, 2, 2)
    assert "clin " not in compact_path.read_text(encoding="utf-8")  # no prompt text


def test_the_compact_evidence_needs_the_site_payload(engine, tmp_path):
    with pytest.raises(audit.AuditRefusal, match="needs --site-payload"):
        audit.main(["--root", str(engine), "--out", str(tmp_path / "r.json"), "--compact-out",
                    str(tmp_path / "c.json")])
