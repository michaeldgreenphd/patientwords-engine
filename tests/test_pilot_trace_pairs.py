"""pilot/analysis/trace_pairs.py turns a finished version-2 pilot run into a circuit-trace pairs file. These tests
build a small fake run directory and check selection, ordering, targets, provenance, the refusals, and that its
surface key and next-word rule match the harness's. The words of the fake rows live in
tests/fixtures/pilot_trace_pairs_terms.json (engine AGENTS.md: medical vocabulary lives in data files, never in Python
source); the next-word variants below are built from the fixture's word."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TERMS = json.loads((ROOT / "tests" / "fixtures" / "pilot_trace_pairs_terms.json").read_text(encoding="utf-8"))
WORD = TERMS["row"]["next_word"]
PROBE_ENDINGS = ["my", "the"]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None, f"{rel} is missing"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tp = _load("pilot_trace_pairs_test", "pilot/analysis/trace_pairs.py")


@pytest.fixture(scope="module")
def common():
    return _load("pilot_common_trace_test", "pilot/scripts/common.py")


def _row(rid: str, control: str = "none", **fields) -> dict:
    """A fake generated row: the fixture's text fields, overridden by `fields` (template, clinical_term,
    patient_term, next_word)."""
    row = {"id": rid, "call_id": "A__x__y", "arm": "A", "cell": "x__y", "line_index": int(rid[-2:]), **TERMS["row"],
           "control": control, "prompt_sha256": "p" * 64}
    row.update(fields)
    return row


def _run(tmp_path: Path, rows: list[dict], verdicts: dict[str, str], version=2, finalized=True,
         probe_endings=PROBE_ENDINGS) -> Path:
    """A fake finished run directory; probe_endings None leaves the key out of design.json."""
    run = tmp_path / "pilot_test_run"
    (run / "generated").mkdir(parents=True)
    design = {"specialties": ["x"], "swap_types": [{"name": "y", "definition": "d"}]}
    if probe_endings is not None:
        design["probe_endings"] = probe_endings
    if version is not None:
        design["harness_version"] = version
    (run / "design.json").write_text(json.dumps(design), encoding="utf-8")
    (run / "manifest.json").write_text(json.dumps({"finalized_utc": "2026-10-02T00:00:00Z" if finalized else None}),
                                       encoding="utf-8")
    (run / "generated" / "all_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    checked = [{"source": "generated", "row_id": rid, "verdict": v, "relation": "same", "sentence_natural": "both",
                "patient_realism": "real"} for rid, v in verdicts.items()]
    checked.append({"source": "seed", "row_id": None, "verdict": "yes"})
    (run / "checked.jsonl").write_text("".join(json.dumps(c) + "\n" for c in checked), encoding="utf-8")
    return run


def test_the_fixture_row_fills_the_expected_sentences():
    """The expected sentences are written out in the fixture; this ties them to its row, so a fixture edit that
    changes one but not the other fails here rather than in a selection test."""
    row, expected = TERMS["row"], TERMS["expected"]
    assert row["template"].count("___") == 1
    assert expected["top_prompt"] == row["template"].replace("___", row["clinical_term"])
    assert expected["bottom_prompt"] == row["template"].replace("___", row["patient_term"])
    assert row["template"].split()[-1] in PROBE_ENDINGS
    assert TERMS["template_off_probe_point"].split()[-1] not in PROBE_ENDINGS


def test_selects_checker_yes_rows_in_run_order_with_spaced_targets(tmp_path):
    second = TERMS["second_next_word"]
    rows = [_row("r01"), _row("r02"), _row("r03", control="negative"), _row("r04", next_word=second)]
    run = _run(tmp_path, rows, {"r01": "yes", "r02": "no", "r04": "yes"})
    pairs, meta = tp.build(run)
    assert [p["pilot"]["row_id"] for p in pairs] == ["r01", "r04"]
    assert pairs[0]["top_prompt"] == TERMS["expected"]["top_prompt"]
    assert pairs[0]["bottom_prompt"] == TERMS["expected"]["bottom_prompt"]
    assert [p["target_clinical_token"] for p in pairs] == [" " + WORD, " " + second]
    assert all(p["pilot"]["probe_point"] for p in pairs)
    assert meta["counts"]["not_selected"] == {"checker equivalent 'no'": 1, "negative control (not requested)": 1}
    with_controls, _ = tp.build(run, include_controls=True)
    assert [p["pilot"]["row_id"] for p in with_controls] == ["r01", "r03", "r04"]


def test_probe_point_flag_is_false_when_the_template_ends_elsewhere(tmp_path):
    run = _run(tmp_path, [_row("r01", template=TERMS["template_off_probe_point"])], {"r01": "yes"})
    pairs, meta = tp.build(run)
    assert pairs[0]["pilot"]["probe_point"] is False and meta["counts"]["at_probe_point"] == 0


def test_probe_endings_compare_case_insensitively_and_an_absent_list_is_refused(tmp_path):
    """The probe endings are lowercased once, after design.json is read (Copilot review of PR #74), and a version-2
    design without a list of them is refused rather than read as no probe ending, which would flag every pair as
    off the probe point."""
    pairs, meta = tp.build(_run(tmp_path / "upper", [_row("r01")], {"r01": "yes"}, probe_endings=["MY", "The"]))
    assert pairs[0]["pilot"]["probe_point"] is True and meta["counts"]["at_probe_point"] == 1
    for i, endings in enumerate([None, [], "my", ["my", 3], ["my", ""]]):
        run = _run(tmp_path / f"bad{i}", [_row("r01")], {"r01": "yes"}, probe_endings=endings)
        with pytest.raises(tp.TraceInputError, match="probe_endings"):
            tp.build(run)


@pytest.mark.parametrize("version,finalized,match", [(None, True, "harness_version"), (1, True, "harness_version"),
                                                     (2, False, "not finalized")])
def test_refuses_runs_that_are_not_finished_version_2(tmp_path, version, finalized, match):
    run = _run(tmp_path, [_row("r01")], {"r01": "yes"}, version=version, finalized=finalized)
    with pytest.raises(tp.TraceInputError, match=match):
        tp.build(run)


def test_refuses_rather_than_drops_untraceable_or_unjudged_rows(tmp_path):
    with pytest.raises(tp.TraceInputError, match="no checker verdict"):
        tp.build(_run(tmp_path / "a", [_row("r01"), _row("r02")], {"r01": "yes"}))
    with pytest.raises(tp.TraceInputError, match="exactly one"):
        tp.build(_run(tmp_path / "b", [_row("r01", template="___ and ___")], {"r01": "yes"}))
    with pytest.raises(tp.TraceInputError, match="row r01: next_word .* breaks the version-2 next_word rule"):
        tp.build(_run(tmp_path / "c", [_row("r01", next_word=TERMS["two_word_next_word"])], {"r01": "yes"}))
    with pytest.raises(tp.TraceInputError, match="nothing to trace"):
        tp.build(_run(tmp_path / "d", [_row("r01")], {"r01": "no"}))


# variants of the fixture's next word, by the part of the protocol's rule each one tests
OUTSIDE_THE_RULE = {"capital": WORD.capitalize(), "all capitals": WORD.upper(), "end punctuation": WORD + "!",
                    "full stop": WORD + ".", "digit": WORD + "2", "underscore": f"{WORD}_{WORD}",
                    "two hyphens": f"{WORD}-{WORD}-{WORD}", "hyphen and apostrophe": f"{WORD}-{WORD}'{WORD}",
                    "leading hyphen": "-" + WORD, "trailing hyphen": WORD + "-", "leading apostrophe": "'" + WORD,
                    "space": f"{WORD} {WORD}", "leading space": " " + WORD, "newline": WORD + "\n", "empty": ""}
INSIDE_THE_RULE = {"plain": WORD, "one hyphen": f"{WORD}-{WORD}", "one apostrophe": f"{WORD}'{WORD}",
                   "one typographic apostrophe": f"{WORD}’{WORD}", "letters of another script": "été"}


def test_refuses_a_next_word_outside_the_protocol_rule(tmp_path):
    """PROTOCOL.md section 4 of run 2: next_word is "a non-empty lowercase word of letters (one internal hyphen or
    apostrophe allowed)". The earlier check refused only spaces, so a capital or punctuation reached the trace target
    (Copilot review of PR #74)."""
    for i, (case, word) in enumerate(OUTSIDE_THE_RULE.items()):
        run = _run(tmp_path / f"out{i}", [_row("r01", next_word=word)], {"r01": "yes"})
        with pytest.raises(tp.TraceInputError, match="row r01: next_word .* breaks the version-2 next_word rule"):
            tp.build(run)
            pytest.fail(f"{case}: {word!r} was accepted")
    for i, (case, word) in enumerate(INSIDE_THE_RULE.items()):
        pairs, _ = tp.build(_run(tmp_path / f"in{i}", [_row("r01", next_word=word)], {"r01": "yes"}))
        assert pairs[0]["target_clinical_token"] == " " + word, case


def test_next_word_rule_is_the_harness_rule(common):
    """trace_pairs.py copies the parser's rule rather than importing common (whose import reads PILOT_DIR's design);
    the copy must be the same pattern and give the same answer on every case, so the trace refuses exactly what the
    parser would have refused."""
    assert tp.NEXT_WORD_RE.pattern == common.NEXT_WORD_RE.pattern
    for case, value in {**OUTSIDE_THE_RULE, **INSIDE_THE_RULE, "null": None, "number": 7, "list": [WORD]}.items():
        assert tp.next_word_ok(value) is common.next_word_ok(value), case
    assert not any(tp.next_word_ok(w) for w in OUTSIDE_THE_RULE.values())
    assert all(tp.next_word_ok(w) for w in INSIDE_THE_RULE.values())


@pytest.mark.parametrize("key", ["id", "clinical_term", "patient_term", "template", "next_word", "control"])
def test_refuses_a_row_without_a_key_a_pair_is_built_from(tmp_path, key):
    """Every row of all_rows.jsonl is checked before any is selected, so a row the checker rejected is refused too,
    by its line, its id and the missing key (Copilot review of PR #74); before, a missing term or template raised a
    KeyError that main() reported without the row."""
    rows = [_row("r01"), _row("r02")]
    del rows[1][key]
    run = _run(tmp_path, rows, {"r01": "yes", "r02": "no"})
    who = r"a row without an id" if key == "id" else r"row r02"
    with pytest.raises(tp.TraceInputError, match=rf"^all_rows\.jsonl line 2 \({who}\) lacks the required key\(s\) {key}$"):
        tp.build(run)
    assert tp.main(["--run-dir", str(run)]) == 2


def test_refuses_a_line_that_is_not_a_json_object(tmp_path):
    run = _run(tmp_path, [_row("r01")], {"r01": "yes"})
    with (run / "generated" / "all_rows.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("[1, 2]\n")
    with pytest.raises(tp.TraceInputError, match=r"all_rows\.jsonl line 2 is not a JSON object"):
        tp.build(run)


@pytest.mark.parametrize("key,value", [("clinical_term", None), ("clinical_term", "  "), ("patient_term", 3)])
def test_refuses_a_selected_row_whose_term_is_not_a_non_empty_string(tmp_path, key, value):
    run = _run(tmp_path, [_row("r01", **{key: value})], {"r01": "yes"})
    with pytest.raises(tp.TraceInputError, match=f"row r01: {key} is not a non-empty string"):
        tp.build(run)


def test_main_writes_the_pairs_and_a_sidecar_with_the_output_hash(tmp_path):
    run = _run(tmp_path, [_row("r01")], {"r01": "yes"})
    assert tp.main(["--run-dir", str(run)]) == 0
    out = run / "trace" / "trace_pairs.json"
    meta = json.loads(out.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["output"]["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert json.loads(out.read_text(encoding="utf-8"))[0]["target_clinical_token"] == " " + WORD
    assert tp.main(["--run-dir", str(tmp_path / "missing")]) == 2


def test_surface_key_matches_the_harness(common):
    for s in TERMS["surface_key_strings"]:
        assert tp.surface_key(s) == common.surface_key(s)


def test_review_sample_selects_the_sampled_rows_in_review_order_whatever_the_checker_said(tmp_path):
    rows = [_row("r01"), _row("r02"), _row("r03", control="negative"), _row("r04")]
    run = _run(tmp_path, rows, {"r01": "yes", "r02": "no", "r04": "unclear"})
    (run / "review_map.json").write_text(json.dumps({"map": {"r001": "r04", "r002": "r02"}}), encoding="utf-8")
    pairs, meta = tp.build(run, review_sample=True)
    assert [(p["pilot"]["review_id"], p["pilot"]["row_id"]) for p in pairs] == [("r001", "r04"), ("r002", "r02")]
    assert [p["pilot"]["checker"]["verdict"] for p in pairs] == ["unclear", "no"]
    assert meta["selection"].startswith("exactly the blind review sample")
    with pytest.raises(tp.TraceInputError, match="select different rows"):
        tp.build(run, include_controls=True, review_sample=True)
    (run / "review_map.json").write_text(json.dumps({"map": {"r001": "r99"}}), encoding="utf-8")
    with pytest.raises(tp.TraceInputError, match="absent from all_rows"):
        tp.build(run, review_sample=True)
