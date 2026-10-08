"""Exact target reads (2026-10-07): a recorded target probability is the target token's own.

The earlier hosted read (targets.target_probability with anchor_matches) kept the likeliest logit that matched the
target by prefix in either direction, case-blind and space-blind, so a neighbour's probability was recorded under
the target's name: a target read off a likelier token that begins with it (' xab' as ' xabi'), and a target read
off a likelier token that is its first part (' xabicor' as ' xabi'). Separately, an unscreened pair whose intended
target was missing from the reference side was measured on the top logit with nothing in the result saying so.
These tests pin the new read: exact or missing (a named reason and diagnostics, never a value), the leading space
significant on hosted labels, the intended wordpiece rule kept and recorded, substitutions flagged.

Every token here is an abstract stand-in (' xab', ' xabi', ' xabicor', ...) chosen only for its prefix relations.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import build_fetcher, make_graph

import medlang_circuits.batch_eval as batch_eval
from medlang_circuits.targets import (
    read_exact,
    resolve_target,
    returned_logits,
    same_token,
    select_logits,
    target_probability,
    token_form,
)


def hosted_graph(logits: list[tuple[str, float]]) -> dict[str, Any]:
    """The fixture graph with its logit set replaced by hosted-format labels: 'Output " tok" (p=0.123)'."""
    g = make_graph()
    g["nodes"] = [n for n in g["nodes"] if n["feature_type"] != "logit"]
    g["links"] = [link for link in g["links"] if link["target"] != "L_999_3"]
    for i, (tok, p) in enumerate(logits):
        nid = f"L_{i}"
        g["nodes"].append({"node_id": nid, "feature": 2000 + i, "layer": "26", "ctx_idx": 3,
                           "feature_type": "logit", "jsNodeId": f"{nid}-3", "clerp": f'Output "{tok}" (p={p})'})
        g["links"].append({"source": "7_00007_2", "target": nid, "weight": 1.0})
    return g


def label(tok: str) -> str:
    return f'Output "{tok}"'


# ---- the read itself -------------------------------------------------------------------------------------------


def test_a_likelier_token_that_begins_with_the_target_is_not_read():
    g = hosted_graph([(" qqq", 0.448), (" hour", 0.147), (" xabi", 0.068), (" xab", 0.041)])
    assert target_probability(g, anchor=label(" xab")) == (label(" xabi"), 0.068)  # the legacy borrow
    read = read_exact(g, label(" xab"))
    assert read == {"status": "exact", "token": label(" xab"), "probability": 0.041, "rank": 4, "returned": 4}


def test_a_likelier_token_that_is_the_targets_first_part_is_not_read():
    g = hosted_graph([(" qqq", 0.137), (" Qd", 0.107), (" xabi", 0.094), (" hour", 0.073)])
    assert target_probability(g, anchor=label(" xabicor")) == (label(" xabi"), 0.094)  # the legacy borrow
    read = read_exact(g, label(" xabicor"))
    assert read["status"] == "missing"
    assert read["reason"] == "target_not_in_returned_logits"
    assert "probability" not in read and "token" not in read
    assert read["prefix_candidates"] == [[label(" xabi"), 0.094, "token_is_leading_piece_of_target"]]


def test_a_missing_read_lists_neighbours_in_both_directions_as_diagnostics_only():
    g = hosted_graph([(" xabis", 0.3), (" xa", 0.2), (" xabi", 0.1), (" Xab", 0.05), (" zz", 0.01)])
    read = read_exact(g, label(" xab"))
    assert read["status"] == "missing" and read["returned"] == 5
    # nearest first: same length (the case variant), then one character longer, then two; stubs (' xa') excluded
    assert read["prefix_candidates"] == [
        [label(" Xab"), 0.05, "case_variant"],
        [label(" xabi"), 0.1, "target_is_leading_piece_of_token"],
        [label(" xabis"), 0.3, "target_is_leading_piece_of_token"],
    ]


def test_the_leading_space_is_significant_on_hosted_labels_in_both_directions():
    g = hosted_graph([(" Xab", 0.5), (" xab", 0.2), ("xab", 0.05), ("▁qdo", 0.1)])
    assert read_exact(g, label(" xab"))["probability"] == 0.2   # not the unspaced 'xab'
    assert read_exact(g, label("xab"))["probability"] == 0.05   # not the spaced ' xab'
    assert read_exact(g, label(" XAB"))["status"] == "missing"  # case is identity too
    assert read_exact(g, " qdo")["probability"] == 0.1          # a SentencePiece marker reads as a space
    assert read_exact(g, "Ġqdo")["probability"] == 0.1     # and so does a byte-level one
    only_spaced = hosted_graph([(" xab", 0.3)])
    read = read_exact(only_spaced, label("xab"))
    assert read["reason"] == "target_not_in_returned_logits"
    assert read["prefix_candidates"] == [[label(" xab"), 0.3, "space_variant"]]
    only_unspaced = hosted_graph([("xab", 0.3)])
    assert read_exact(only_unspaced, label(" xab"))["prefix_candidates"] == [[label("xab"), 0.3, "space_variant"]]
    marker = hosted_graph([("\u2581xab", 0.3)])  # a marker-spelt label is a space variant of the unspaced target
    assert read_exact(marker, label("xab"))["prefix_candidates"] == [[label("\u2581xab"), 0.3, "space_variant"]]
    assert token_form(label("▁qdo")) == " qdo" and not same_token(label("xab"), label(" xab"))


def test_bare_labels_whose_spacing_was_parsed_away_still_match():
    # The local/test clerp format 'tok (p=...)' loses its surrounding whitespace in parse_logit_clerp.
    g = make_graph()
    assert read_exact(g, " jumps")["probability"] == 0.81
    assert read_exact(g, "jumps")["probability"] == 0.81


def test_two_identical_labels_are_refused_not_guessed():
    read = read_exact(hosted_graph([(" xab", 0.3), (" xab", 0.2)]), label(" xab"))
    assert read["status"] == "missing" and read["reason"] == "ambiguous_exact_match"
    assert read["exact_candidates"] == [[label(" xab"), 0.3], [label(" xab"), 0.2]]


def test_the_read_sees_every_returned_logit_including_those_pruned_for_display():
    g = hosted_graph([(f" t{i}x", round(0.3 - i * 0.04, 3)) for i in range(7)])
    select_logits(g, keep_top_k=5)
    assert len([n for n in g["nodes"] if n["feature_type"] == "logit"]) == 5
    assert len(returned_logits(g)) == 7
    read = read_exact(g, label(" t6x"))
    assert read["status"] == "exact" and read["probability"] == 0.06 and read["rank"] == 7
    assert target_probability(g, anchor=label(" t6x")) is None  # the legacy read saw the pruned graph only


def test_select_logits_keeps_the_measured_targets_node():
    g = hosted_graph([(f" t{i}x", round(0.3 - i * 0.04, 3)) for i in range(7)])
    info = select_logits(g, keep_top_k=5, keep_labels=[label(" t6x")])
    kept = {n["clerp"] for n in g["nodes"] if n["feature_type"] == "logit"}
    assert 'Output " t6x" (p=0.06)' in kept and len(kept) == 6
    assert info["kept_for_measurement"] == [label(" t6x")]


def test_missing_reads_name_their_reason():
    assert read_exact(hosted_graph([(" a1x", 0.5)]), None)["reason"] == "no_target_token"
    assert read_exact(hosted_graph([(" a1x", 0.5)]), label(" "))["reason"] == "no_target_token"
    assert read_exact(hosted_graph([]), label(" a1x"))["reason"] == "no_returned_logits"
    g = hosted_graph([(" xabi", 0.2)])
    g["nodes"].append({"node_id": "L_np", "feature_type": "logit", "clerp": 'Output " xab"'})  # no probability
    assert read_exact(g, label(" xab"))["reason"] == "unparseable_probability"


def test_resolve_target_keeps_the_wordpiece_rule_explicit_and_refuses_extensions():
    # the intended target is split by the tokenizer: its leading piece is measured, and the record says so
    g = hosted_graph([(" xab", 0.517), (" old", 0.096), (" xabi", 0.088), (" Xab", 0.038)])
    read = resolve_target(g, " xabmel")
    assert read["status"] == "leading_wordpiece" and read["token"] == label(" xab") and read["probability"] == 0.517
    assert "alternatives" not in read  # ' xabi' is not a leading piece of ' xabmel'; ' Xab' differs in case
    # several pieces: the likeliest is measured, as before, and the others are listed
    g2 = hosted_graph([(" xabi", 0.3), (" xabiho", 0.1)])
    read2 = resolve_target(g2, " xabihomes")
    assert read2["token"] == label(" xabi") and read2["alternatives"] == [[label(" xabiho"), 0.1]]
    # a likelier token that only BEGINS with the intended target is another token: never taken
    g3 = hosted_graph([(" xabicors", 0.4), (" xabi", 0.2)])
    assert target_probability(g3, anchor=" xabicor") == (label(" xabicors"), 0.4)  # the legacy read
    read3 = resolve_target(g3, " xabicor")
    assert read3["status"] == "leading_wordpiece" and read3["token"] == label(" xabi")
    g4 = hosted_graph([(" xabicors", 0.4), (" qqq", 0.2)])
    read4 = resolve_target(g4, " xabicor")
    assert read4["status"] == "missing"
    assert read4["prefix_candidates"] == [[label(" xabicors"), 0.4, "target_is_leading_piece_of_token"]]
    # stub pieces stay excluded
    assert resolve_target(hosted_graph([(" xa", 0.9)]), " xabmel")["status"] == "missing"


def test_resolve_target_respects_the_leading_space_of_pieces():
    # an unspaced token is not a piece of a spaced target, in either direction
    assert resolve_target(hosted_graph([("xab", 0.5)]), " xabmel")["status"] == "missing"
    read = resolve_target(hosted_graph([("xab", 0.5), (" xab", 0.1)]), " xabmel")
    assert read["token"] == label(" xab") and "alternatives" not in read


def test_an_unspaced_intended_target_is_read_with_its_space_first_on_the_record():
    # Some pairs files spell the intended word without the space a word after a word carries. After a prompt that
    # ends in a word, the spaced token is the intended one, so it is read first.
    read = resolve_target(hosted_graph([(" qdoc", 0.4), (" zz", 0.1)]), "qdoc")
    assert read["status"] == "exact" and read["token"] == label(" qdoc")
    assert read["intended_spacing"] == "leading_space_added"
    both = resolve_target(hosted_graph([("qdoc", 0.4), (" qdoc", 0.1)]), "qdoc")
    assert both["token"] == label(" qdoc") and both["intended_spacing"] == "leading_space_added"
    only_unspaced = resolve_target(hosted_graph([("qdoc", 0.4), (" zz", 0.1)]), "qdoc")
    assert only_unspaced["token"] == label("qdoc") and only_unspaced["intended_spacing"] == "as_written"
    piece = resolve_target(hosted_graph([(" xab", 0.4)]), "xabmel")
    assert piece["status"] == "leading_wordpiece" and piece["intended_spacing"] == "leading_space_added"
    assert "intended_spacing" not in resolve_target(hosted_graph([(" qdoc", 0.4)]), " qdoc")


def test_the_spaced_form_is_read_when_the_unspaced_one_is_unparseable_and_both_misses_are_recorded():
    g = hosted_graph([(" qdoc", 0.3)])
    g["nodes"].append({"node_id": "L_np", "feature_type": "logit", "clerp": 'Output "qdoc"'})  # no probability
    read = resolve_target(g, "qdoc")
    assert read["token"] == label(" qdoc") and read["intended_spacing"] == "leading_space_added"
    neither = resolve_target(hosted_graph([(" zz", 0.3)]), "qdoc")
    assert neither["status"] == "missing" and neither["reason"] == "target_not_in_returned_logits"
    assert neither["intended_spacing"] == "both_tried" and neither["forms_tried"] == [" qdoc", "qdoc"]
    g2 = hosted_graph([(" zz", 0.3)])
    g2["nodes"].append({"node_id": "L_np", "feature_type": "logit", "clerp": 'Output "qdoc"'})
    unparsed = resolve_target(g2, "qdoc")
    assert unparsed["reason"] == "unparseable_probability" and unparsed["intended_spacing"] == "both_tried"


# ---- through run_batch -----------------------------------------------------------------------------------------


def _run(tmp_path: Path, monkeypatch, spreads: dict[str, list[tuple[str, float]]], pair: dict[str, Any],
         **kwargs: Any) -> dict[str, Any]:
    def fake_generate(prompt, slug=None, backend="hosted", **params):
        role = next(k for k in spreads if prompt.startswith(k))
        return hosted_graph(spreads[role])

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(json.dumps([pair]), encoding="utf-8")
    results = batch_eval.run_batch(str(pairs), out_dir=str(tmp_path / "out"), dpi=40, fetcher=build_fetcher(),
                                   **kwargs)
    summary = json.loads((tmp_path / "out" / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["results"][0]["target_read"] == json.loads(json.dumps(results[0]["target_read"]))
    return results[0]


def test_2panel_patient_side_never_borrows_a_neighbours_value(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" xabicor", 0.641), (" xabi", 0.098), (" zor", 0.06)],
        "pat": [(" qqq", 0.137), (" Qd", 0.107), (" xabi", 0.094), (" hour", 0.073)],
    }, {"top_prompt": "clin one", "bottom_prompt": "pat one", "target_clinical_token": " xabicor"})
    assert r["target_token"] == label(" xabicor")
    assert r["probabilities"] == {"clinical": 0.641, "patient": None}  # not 0.094, the ' xabi' value
    assert r["language_penalty"] is None
    tr = r["target_read"]
    assert tr["match"] == "exact" and tr["substituted"] is False and tr["measured_token"] == r["target_token"]
    assert tr["sides"]["clinical"]["status"] == "exact"
    assert tr["sides"]["patient"]["status"] == "missing"
    assert tr["sides"]["patient"]["reason"] == "target_not_in_returned_logits"
    assert tr["sides"]["patient"]["prefix_candidates"][0][:2] == [label(" xabi"), 0.094]


def test_2panel_reads_the_exact_token_when_a_likelier_extension_is_present(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" xab", 0.491), (" xabi", 0.182), (" hour", 0.094)],
        "pat": [(" qqq", 0.448), (" hour", 0.147), (" xabi", 0.068), (" xab", 0.041)],
    }, {"top_prompt": "clin two", "bottom_prompt": "pat two", "target_clinical_token": " xabmel"},
        screen_targets=0.02)
    assert r["target_token"] == label(" xab")
    assert r["probabilities"]["patient"] == 0.041  # the legacy read recorded 0.068
    assert r["language_penalty"] == pytest.approx(0.041 - 0.491)
    tr = r["target_read"]
    assert tr["match"] == "leading_wordpiece" and tr["substituted"] is False
    assert r["screening"]["observed_clinical"] == [label(" xab"), 0.491]


def test_a_target_measured_below_the_display_cut_keeps_its_node_in_the_render(tmp_path, monkeypatch):
    pat = [(f" q{i}z", round(0.3 - i * 0.04, 3)) for i in range(6)] + [(" xab", 0.04)]
    r = _run(tmp_path, monkeypatch, {"clin": [(" xab", 0.5)], "pat": pat},
             {"top_prompt": "clin nine", "bottom_prompt": "pat nine", "target_clinical_token": " xab"})
    assert r["probabilities"]["patient"] == 0.04 and r["target_read"]["sides"]["patient"]["rank"] == 7
    assert label(" xab") not in [t for t, _ in r["predictive_spread"]["patient"]]  # the spread stays the top five
    tagged = json.loads((tmp_path / "out" / "pair_01_patient.tagged.json").read_text(encoding="utf-8"))
    logits = [n["clerp"] for n in tagged["nodes"] if n["feature_type"] == "logit"]
    assert 'Output " xab" (p=0.04)' in logits and len(logits) == 6


def test_an_unscreened_top_logit_substitution_is_flagged(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" to", 0.668), (" a", 0.116), (" some", 0.023)],
        "pat": [(" to", 0.223), (" missed", 0.119)],
    }, {"top_prompt": "clin three", "bottom_prompt": "pat three", "target_clinical_token": " qzrhythm"})
    # the existing fallback still measures the top logit, but the result now says so
    assert r["target_token"] == label(" to")
    assert r["probabilities"] == {"clinical": 0.668, "patient": 0.223}
    tr = r["target_read"]
    assert tr["intended_target"] == " qzrhythm" and tr["measured_token"] == label(" to")
    assert tr["match"] == "top_logit" and tr["substituted"] is True
    assert tr["intended_read"]["status"] == "missing"
    assert tr["intended_read"]["reason"] == "target_not_in_returned_logits"


def test_an_unscreened_extension_is_a_flagged_substitution_not_a_match(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" qupel", 0.5), (" zbd", 0.1)],
        "pat": [(" qupel", 0.2)],
    }, {"top_prompt": "clin four", "bottom_prompt": "pat four", "target_clinical_token": " qup"})
    assert r["target_read"]["match"] == "top_logit" and r["target_read"]["substituted"] is True
    assert r["target_read"]["intended_read"]["prefix_candidates"] == [
        [label(" qupel"), 0.5, "target_is_leading_piece_of_token"]]


def test_screening_never_substitutes_and_records_why(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" to", 0.668), (" xabicors", 0.1)],
        "pat": [(" to", 0.2)],
    }, {"top_prompt": "clin five", "bottom_prompt": "pat five", "target_clinical_token": " xabicor"},
        screen_targets=0.02)
    assert r["screening"]["status"] == "screened_out"
    assert r["screening"]["probe_extension"] == "to"  # the extension changed the prompts, not the target
    assert r["target_token"] is None and r["probabilities"] == {"clinical": None, "patient": None}
    tr = r["target_read"]
    assert tr["match"] is None and tr["substituted"] is False and tr["measured_token"] is None
    assert tr["sides"]["clinical"]["prefix_candidates"] == [
        [label(" xabicors"), 0.1, "target_is_leading_piece_of_token"]]


def test_a_leading_wordpiece_passes_the_screen_on_the_record(tmp_path, monkeypatch):
    # The kept wordpiece rule: with no exact token, a leading piece stands for the target. The hosted path cannot
    # tell a split target from a whole-token one whose first part happens to be a token, so the match is recorded
    # and the measured token is read exactly on both sides - never the intended word's value under another name.
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" to", 0.6), (" xabi", 0.1)],
        "pat": [(" xabi", 0.05), (" xabicor", 0.04)],
    }, {"top_prompt": "clin seven", "bottom_prompt": "pat seven", "target_clinical_token": " xabicor"},
        screen_targets=0.02)
    assert r["screening"]["status"] == "passed"
    assert r["target_token"] == label(" xabi") and r["probabilities"] == {"clinical": 0.1, "patient": 0.05}
    assert r["target_read"]["match"] == "leading_wordpiece" and r["target_read"]["substituted"] is False


def test_no_intended_target_is_not_a_substitution(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {"clin": [(" to", 0.6)], "pat": [(" to", 0.3)]},
             {"top_prompt": "clin six", "bottom_prompt": "pat six"})
    assert r["target_read"]["match"] == "top_logit" and r["target_read"]["substituted"] is None


def test_a_whitespace_top_logit_is_not_measured(tmp_path, monkeypatch):
    # The legacy fallback measured a bare-space top token as the target (' ' for an intended word the tokenizer
    # splits after its space). It has no text to read: the result records why and claims no substitution.
    r = _run(tmp_path, monkeypatch, {"clin": [(" ", 0.5), (" to", 0.2)], "pat": [(" ", 0.4)]},
             {"top_prompt": "clin eight", "bottom_prompt": "pat eight", "target_clinical_token": " qz9"})
    assert r["target_token"] is None and r["probabilities"] == {"clinical": None, "patient": None}
    tr = r["target_read"]
    assert tr["match"] == "top_logit" and tr["substituted"] is False and tr["measured_token"] is None
    assert tr["sides"]["clinical"]["reason"] == "no_target_token"
    assert tr["intended_read"]["reason"] == "target_not_in_returned_logits"


def test_quadrant_and_dialect_sides_read_exactly(tmp_path, monkeypatch):
    spreads = {
        "I have": [(" xabicor", 0.6), (" xabi", 0.1)],
        "I been": [(" xabi", 0.3)],
    }

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        return hosted_graph(spreads["I been" if "been" in prompt else "I have"])

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "q.json"
    pairs.write_text(json.dumps([{"frames": {"standard": "I have{term}, so", "nonstandard": "I been{term}, so"},
                                  "terms": {"medical": " qa", "patient": " qb"},
                                  "target_clinical_token": " xabicor"}]), encoding="utf-8")
    q = batch_eval.run_batch(str(pairs), out_dir=str(tmp_path / "q"), mode="4quadrant", dpi=40,
                             fetcher=build_fetcher())[0]
    assert q["probabilities"] == {"A": 0.6, "B": None, "C": 0.6, "D": None}
    assert q["target_read"]["sides"]["B"]["reason"] == "target_not_in_returned_logits"

    pairs.write_text(json.dumps([{"baseline_prompt": "I have one", "target_clinical_token": " xabicor",
                                  "variants": [{"dialect": "d1", "prompt": "I been one"}]}]), encoding="utf-8")
    d = batch_eval.run_batch(str(pairs), out_dir=str(tmp_path / "d"), mode="dialect", dpi=40,
                             fetcher=build_fetcher())[0]
    assert d["baseline_probability"] == 0.6 and d["variants"][0]["probability"] is None
    assert d["target_read"]["sides"]["variants"][0]["status"] == "missing"


def test_translation_and_mitigation_missing_sides_are_null(tmp_path, monkeypatch):
    spreads = {"tx": [(" xabicor", 0.6)], "pat": [(" xabicor", 0.2), (" xabi", 0.3)], "clin": [(" xabicor", 0.6)]}
    order = []

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        order.append(prompt.split()[0])
        key = prompt.split()[0]
        return hosted_graph(spreads["tx"] if key == "tx" and "only" not in prompt else
                            [(" xabi", 0.5)] if key == "tx" else spreads[key])

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    monkeypatch.setattr(batch_eval, "translate_to_clinical",
                        lambda text, use_llm=True, model=None: {"text": "tx " + text, "method": "stub"})
    pairs = tmp_path / "t.json"
    pairs.write_text(json.dumps([{"patient_prompt": "pat one", "target_clinical_token": " xabicor"}]), encoding="utf-8")
    t = batch_eval.run_batch(str(pairs), out_dir=str(tmp_path / "t"), mode="translation", dpi=40,
                             fetcher=build_fetcher())[0]
    assert t["probabilities"] == {"patient": 0.2, "translated": 0.6}  # the exact token, not ' xabi' (0.3)
    assert order == ["tx", "pat"]  # the reference side is traced first, so the patient trace keeps its node
    pairs.write_text(json.dumps([{"top_prompt": "clin one", "bottom_prompt": "pat only",
                                  "target_clinical_token": " xabicor"}]), encoding="utf-8")
    m = batch_eval.run_batch(str(pairs), out_dir=str(tmp_path / "m"), show_mitigation=True, dpi=40,
                             fetcher=build_fetcher())[0]
    assert m["probabilities"]["translated"] is None and m["mitigation_recovery"] is None
    assert m["language_penalty"] == pytest.approx(0.2 - 0.6)


def test_the_spacing_flag_is_surfaced_in_target_read_and_screening(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {"clin": [(" qdoc", 0.5), ("qdoc", 0.1)], "pat": [(" qdoc", 0.2)]},
             {"top_prompt": "clin ten", "bottom_prompt": "pat ten", "target_clinical_token": "qdoc"},
             screen_targets=0.02)
    assert r["target_token"] == label(" qdoc") and r["probabilities"] == {"clinical": 0.5, "patient": 0.2}
    assert r["target_read"]["intended_spacing"] == "leading_space_added"
    assert r["screening"]["intended_spacing"] == "leading_space_added"


def test_a_screened_out_unspaced_target_records_both_spellings_tried(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {"clin": [(" zz", 0.5)], "pat": [(" zz", 0.2)]},
             {"top_prompt": "clin eleven", "bottom_prompt": "pat eleven", "target_clinical_token": "qdoc"},
             screen_targets=0.02)
    assert r["screening"]["status"] == "screened_out" and r["screening"]["intended_spacing"] == "both_tried"
    assert r["target_read"]["intended_spacing"] == "both_tried"


def test_an_exact_token_that_cannot_be_read_is_reported_not_replaced_by_a_piece():
    g = hosted_graph([(" xabi", 0.3)])
    g["nodes"].append({"node_id": "L_np", "feature_type": "logit", "clerp": 'Output " xabicor"'})  # no probability
    read = resolve_target(g, " xabicor")
    assert read["status"] == "missing" and read["reason"] == "unparseable_probability"
    dup = resolve_target(hosted_graph([(" xabicor", 0.2), (" xabicor", 0.1), (" xabi", 0.3)]), " xabicor")
    assert dup["status"] == "missing" and dup["reason"] == "ambiguous_exact_match"
    spaced = hosted_graph([(" xabi", 0.3)])
    spaced["nodes"].append({"node_id": "L_np", "feature_type": "logit", "clerp": 'Output " xabicor"'})
    unspaced = resolve_target(spaced, "xabicor")
    # the preferred spaced form is the one that failed: recorded as such
    assert unspaced["reason"] == "unparseable_probability" and unspaced["intended_spacing"] == "leading_space_added"


def test_a_duplicated_leading_wordpiece_is_ambiguous_not_guessed():
    read = resolve_target(hosted_graph([(" xabi", 0.3), (" xabi", 0.1)]), " xabicor")
    assert read["status"] == "missing" and read["reason"] == "ambiguous_wordpiece" and "probability" not in read
    assert read["wordpiece_candidates"] == [[label(" xabi"), 0.3], [label(" xabi"), 0.1]]
    # a duplicate among the other pieces does not touch the chosen one, and stays listed
    other = resolve_target(hosted_graph([(" xabi", 0.3), (" xab", 0.1), (" xab", 0.05)]), " xabicor")
    assert other["status"] == "leading_wordpiece" and other["token"] == label(" xabi")
    assert other["alternatives"] == [[label(" xab"), 0.1], [label(" xab"), 0.05]]


def test_a_failed_preferred_spaced_form_is_not_replaced_by_the_as_written_spelling():
    # two ' qdoc' labels (the preferred spaced form, ambiguous) and one readable 'qdoc'
    read = resolve_target(hosted_graph([(" qdoc", 0.3), (" qdoc", 0.2), ("qdoc", 0.1)]), "qdoc")
    assert read["status"] == "missing" and read["reason"] == "ambiguous_exact_match" and "probability" not in read
    assert read["intended_spacing"] == "leading_space_added"
    g = hosted_graph([("qdoc", 0.1)])
    g["nodes"].append({"node_id": "L_np", "feature_type": "logit", "clerp": 'Output " qdoc"'})  # spaced, unparseable
    unparsed = resolve_target(g, "qdoc")
    assert unparsed["reason"] == "unparseable_probability" and unparsed["intended_spacing"] == "leading_space_added"


def test_equivalent_spellings_of_one_wordpiece_are_ambiguous():
    # ' xab' and the marker-spelt '▁xab' are one token under same_token: two values, no way to choose
    read = resolve_target(hosted_graph([(" xab", 0.3), ("▁xab", 0.1)]), " xabmel")
    assert read["status"] == "missing" and read["reason"] == "ambiguous_wordpiece"
    assert read["wordpiece_candidates"] == [[label(" xab"), 0.3], [label("▁xab"), 0.1]]
    # the exact read already compares by same_token, so the same pair is ambiguous there too
    exact = read_exact(hosted_graph([(" xab", 0.3), ("▁xab", 0.1)]), label(" xab"))
    assert exact["reason"] == "ambiguous_exact_match"
    # a different piece is not a duplicate of the chosen one
    ok = resolve_target(hosted_graph([(" xabi", 0.3), ("▁xab", 0.1)]), " xabicor")
    assert ok["token"] == label(" xabi") and ok["alternatives"] == [[label("▁xab"), 0.1]]


def unreadable(g: dict[str, Any], tok: str) -> dict[str, Any]:
    """Add a logit node for ``tok`` whose probability does not parse."""
    g["nodes"].append({"node_id": f"L_np{len(g['nodes'])}", "feature_type": "logit", "clerp": f'Output "{tok}"'})
    return g


def test_an_unreadable_copy_of_the_exact_token_makes_the_read_ambiguous():
    read = read_exact(unreadable(hosted_graph([(" xab", 0.45), (" zz", 0.1)]), " xab"), label(" xab"))
    assert read["status"] == "missing" and read["reason"] == "ambiguous_exact_match" and "probability" not in read
    assert read["exact_candidates"] == [[label(" xab"), 0.45], [label(" xab"), None]]


def test_unreadable_wordpieces_are_never_skipped():
    # an unreadable copy of the chosen piece: ambiguous
    dup = resolve_target(unreadable(hosted_graph([(" xabi", 0.3)]), " xabi"), " xabicor")
    assert dup["reason"] == "ambiguous_wordpiece" and "probability" not in dup
    assert dup["wordpiece_candidates"] == [[label(" xabi"), 0.3], [label(" xabi"), None]]
    # a longer unreadable piece: the shorter readable one may not stand in for it
    longer = resolve_target(unreadable(hosted_graph([(" xab", 0.3)]), " xabico"), " xabicor")
    assert longer["status"] == "missing" and longer["reason"] == "unparseable_probability"
    assert longer["wordpiece_candidates"] == [[label(" xab"), 0.3], [label(" xabico"), None]]
    # only unreadable pieces
    only = resolve_target(unreadable(hosted_graph([(" zz", 0.3)]), " xabi"), " xabicor")
    assert only["reason"] == "unparseable_probability"
    # an unreadable token that is not a piece changes nothing
    fine = resolve_target(unreadable(hosted_graph([(" xabi", 0.3)]), " qq"), " xabicor")
    assert fine["status"] == "leading_wordpiece" and fine["token"] == label(" xabi")
