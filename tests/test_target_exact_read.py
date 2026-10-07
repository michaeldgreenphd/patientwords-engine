"""Exact target reads (2026-10-07): a recorded target probability is the target token's own.

The earlier hosted read (targets.target_probability with anchor_matches) kept the likeliest logit that matched the
target by prefix in either direction, so a neighbour's probability was recorded under the target's name:
' ant' read as ' anti' (the neighbour begins with the target) and ' antibiotic' read as ' anti' (the neighbour is
the target's first part). Separately, an unscreened pair whose intended target was missing from the reference side
was measured on the top logit with nothing in the result saying so. These tests pin the new read: exact or missing
(with a named reason and diagnostics, never a value), the intended wordpiece rule kept and recorded, substitutions
flagged. Tokens here are abstract stand-ins; no medical vocabulary.
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
    select_logits,
    target_probability,
    token_key,
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
    # the documented case: target ' ant', the likelier ' anti' begins with it
    g = hosted_graph([(" xtra", 0.448), (" hour", 0.147), (" anti", 0.068), (" ant", 0.041)])
    assert target_probability(g, anchor=label(" ant")) == (label(" anti"), 0.068)  # the legacy borrow
    read = read_exact(g, label(" ant"))
    assert read == {"status": "exact", "token": label(" ant"), "probability": 0.041, "rank": 4, "returned": 4}


def test_a_likelier_token_that_is_the_targets_first_part_is_not_read():
    # target ' antibiotic' absent; ' anti' is its first part and sits in the spread
    g = hosted_graph([(" xtra", 0.137), (" Ad", 0.107), (" anti", 0.094), (" hour", 0.073)])
    assert target_probability(g, anchor=label(" antibiotic")) == (label(" anti"), 0.094)  # the legacy borrow
    read = read_exact(g, label(" antibiotic"))
    assert read["status"] == "missing"
    assert read["reason"] == "target_not_in_returned_logits"
    assert "probability" not in read and "token" not in read
    assert read["prefix_candidates"] == [[label(" anti"), 0.094, "token_is_leading_piece_of_target"]]


def test_a_missing_read_lists_neighbours_in_both_directions_as_diagnostics_only():
    g = hosted_graph([(" antis", 0.3), (" an", 0.2), (" anti", 0.1), (" Ant", 0.05), (" zz", 0.01)])
    read = read_exact(g, label(" ant"))
    assert read["status"] == "missing" and read["returned"] == 5
    # nearest first: same length (the case variant), then one character longer, then two; stubs (' an') excluded
    assert read["prefix_candidates"] == [
        [label(" Ant"), 0.05, "case_variant"],
        [label(" anti"), 0.1, "target_is_leading_piece_of_token"],
        [label(" antis"), 0.3, "target_is_leading_piece_of_token"],
    ]


def test_identity_normalises_only_the_leading_space():
    g = hosted_graph([(" Ant", 0.5), (" ant", 0.2), ("▁doc", 0.1)])
    assert token_key(label(" ant")) == "ant" and token_key(label("▁doc")) == "doc"
    assert read_exact(g, "ant")["probability"] == 0.2          # a target written without its leading space
    assert read_exact(g, label(" ant"))["probability"] == 0.2  # case is identity: ' Ant' is another token
    assert read_exact(g, " doc")["probability"] == 0.1         # the SentencePiece marker is a leading space
    assert read_exact(g, label(" ANT"))["status"] == "missing"


def test_two_tokens_differing_only_in_the_leading_space_are_told_apart_or_refused():
    g = hosted_graph([(" ant", 0.3), ("ant", 0.2)])
    assert read_exact(g, label(" ant"))["probability"] == 0.3
    assert read_exact(g, label("ant"))["probability"] == 0.2
    # a target spelt like neither ('Ġant' normalises to ' ant'): picks ' ant'; two ' ant' labels: refused
    assert read_exact(g, "Ġant")["probability"] == 0.3
    dup = hosted_graph([(" ant", 0.3), (" ant", 0.2)])
    read = read_exact(dup, label(" ant"))
    assert read["status"] == "missing" and read["reason"] == "ambiguous_exact_match"
    assert read["exact_candidates"] == [[label(" ant"), 0.3], [label(" ant"), 0.2]]


def test_the_read_sees_every_returned_logit_including_those_pruned_for_display():
    g = hosted_graph([(f" t{i}x", round(0.3 - i * 0.04, 3)) for i in range(7)])
    select_logits(g, keep_top_k=5)
    assert len([n for n in g["nodes"] if n["feature_type"] == "logit"]) == 5
    assert len(returned_logits(g)) == 7
    read = read_exact(g, label(" t6x"))
    assert read["status"] == "exact" and read["probability"] == 0.06 and read["rank"] == 7
    assert target_probability(g, anchor=label(" t6x")) is None  # the legacy read saw the pruned graph only


def test_missing_reads_name_their_reason():
    assert read_exact(hosted_graph([(" a1x", 0.5)]), None)["reason"] == "no_target_token"
    assert read_exact(hosted_graph([(" a1x", 0.5)]), label(" "))["reason"] == "no_target_token"
    assert read_exact(hosted_graph([]), label(" a1x"))["reason"] == "no_returned_logits"


def test_resolve_target_keeps_the_wordpiece_rule_explicit_and_refuses_extensions():
    # the intended target is split by the tokenizer: its leading piece is measured, and the record says so
    g = hosted_graph([(" ant", 0.517), (" old", 0.096), (" anti", 0.088), (" Ant", 0.038)])
    read = resolve_target(g, " antacid")
    assert read["status"] == "leading_wordpiece" and read["token"] == label(" ant") and read["probability"] == 0.517
    assert "alternatives" not in read  # ' anti' is not a leading piece of ' antacid'; ' Ant' differs in case
    # several pieces: the likeliest is measured, as before, and the others are listed
    g2 = hosted_graph([(" anti", 0.3), (" antihist", 0.1)])
    read2 = resolve_target(g2, " antihistamines")
    assert read2["token"] == label(" anti") and read2["alternatives"] == [[label(" antihist"), 0.1]]
    # a likelier token that only BEGINS with the intended target is another token: never taken
    g3 = hosted_graph([(" antibiotics", 0.4), (" anti", 0.2)])
    assert target_probability(g3, anchor=" antibiotic") == (label(" antibiotics"), 0.4)  # the legacy read
    read3 = resolve_target(g3, " antibiotic")
    assert read3["status"] == "leading_wordpiece" and read3["token"] == label(" anti")
    g4 = hosted_graph([(" antibiotics", 0.4), (" xyz", 0.2)])
    read4 = resolve_target(g4, " antibiotic")
    assert read4["status"] == "missing"
    assert read4["prefix_candidates"] == [[label(" antibiotics"), 0.4, "target_is_leading_piece_of_token"]]
    # stub pieces stay excluded
    assert resolve_target(hosted_graph([(" an", 0.9)]), " antacid")["status"] == "missing"


# ---- through run_batch -----------------------------------------------------------------------------------------


def _run(tmp_path: Path, monkeypatch, spreads: dict[str, list[tuple[str, float]]], pair: dict[str, Any],
         **kwargs: Any) -> dict[str, Any]:
    traced = []

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        traced.append(prompt)
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
        "clin": [(" antibiotic", 0.641), (" anti", 0.098), (" oral", 0.06)],
        "pat": [(" xtra", 0.137), (" Ad", 0.107), (" anti", 0.094), (" hour", 0.073)],
    }, {"top_prompt": "clin one", "bottom_prompt": "pat one", "target_clinical_token": " antibiotic"})
    assert r["target_token"] == label(" antibiotic")
    assert r["probabilities"] == {"clinical": 0.641, "patient": None}  # not 0.094, the ' anti' value
    assert r["language_penalty"] is None
    tr = r["target_read"]
    assert tr["match"] == "exact" and tr["substituted"] is False and tr["measured_token"] == r["target_token"]
    assert tr["sides"]["clinical"]["status"] == "exact"
    assert tr["sides"]["patient"]["status"] == "missing"
    assert tr["sides"]["patient"]["reason"] == "target_not_in_returned_logits"
    assert tr["sides"]["patient"]["prefix_candidates"][0][:2] == [label(" anti"), 0.094]


def test_2panel_reads_the_exact_token_when_a_likelier_extension_is_present(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" ant", 0.491), (" anti", 0.182), (" hour", 0.094)],
        "pat": [(" xtra", 0.448), (" hour", 0.147), (" anti", 0.068), (" ant", 0.041)],
    }, {"top_prompt": "clin two", "bottom_prompt": "pat two", "target_clinical_token": " antacid"},
        screen_targets=0.02)
    assert r["target_token"] == label(" ant")
    assert r["probabilities"]["patient"] == 0.041  # the legacy read recorded 0.068
    assert r["language_penalty"] == pytest.approx(0.041 - 0.491)
    tr = r["target_read"]
    assert tr["match"] == "leading_wordpiece" and tr["substituted"] is False
    assert r["screening"]["observed_clinical"] == [label(" ant"), 0.491]


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
        "clin": [(" pillow", 0.5), (" bed", 0.1)],
        "pat": [(" pillow", 0.2)],
    }, {"top_prompt": "clin four", "bottom_prompt": "pat four", "target_clinical_token": " pill"})
    assert r["target_read"]["match"] == "top_logit" and r["target_read"]["substituted"] is True
    assert r["target_read"]["intended_read"]["prefix_candidates"] == [
        [label(" pillow"), 0.5, "target_is_leading_piece_of_token"]]


def test_screening_never_substitutes_and_records_why(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" to", 0.668), (" antibiotics", 0.1)],
        "pat": [(" to", 0.2)],
    }, {"top_prompt": "clin five", "bottom_prompt": "pat five", "target_clinical_token": " antibiotic"},
        screen_targets=0.02)
    assert r["screening"]["status"] == "screened_out"
    assert r["screening"]["probe_extension"] == "to"  # the extension changed the prompts, not the target
    assert r["target_token"] is None and r["probabilities"] == {"clinical": None, "patient": None}
    tr = r["target_read"]
    assert tr["match"] is None and tr["substituted"] is False and tr["measured_token"] is None
    assert tr["sides"]["clinical"]["prefix_candidates"] == [
        [label(" antibiotics"), 0.1, "target_is_leading_piece_of_token"]]


def test_a_leading_wordpiece_passes_the_screen_on_the_record(tmp_path, monkeypatch):
    # The kept wordpiece rule: with no exact token, a leading piece stands for the target. The hosted path cannot
    # tell a split target from an atomic one whose first part happens to be a token, so the match is recorded and
    # the measured token is read exactly on both sides - never the intended word's value under another name.
    r = _run(tmp_path, monkeypatch, {
        "clin": [(" to", 0.6), (" anti", 0.1)],
        "pat": [(" anti", 0.05), (" antibiotic", 0.04)],
    }, {"top_prompt": "clin seven", "bottom_prompt": "pat seven", "target_clinical_token": " antibiotic"},
        screen_targets=0.02)
    assert r["screening"]["status"] == "passed"
    assert r["target_token"] == label(" anti") and r["probabilities"] == {"clinical": 0.1, "patient": 0.05}
    assert r["target_read"]["match"] == "leading_wordpiece" and r["target_read"]["substituted"] is False


def test_no_intended_target_is_not_a_substitution(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, {"clin": [(" to", 0.6)], "pat": [(" to", 0.3)]},
             {"top_prompt": "clin six", "bottom_prompt": "pat six"})
    assert r["target_read"]["match"] == "top_logit" and r["target_read"]["substituted"] is None


def test_quadrant_and_dialect_sides_read_exactly(tmp_path, monkeypatch):
    spreads = {
        "I have": [(" antibiotic", 0.6), (" anti", 0.1)],
        "I been": [(" anti", 0.3)],
    }

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        return hosted_graph(spreads["I been" if "been" in prompt else "I have"])

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "q.json"
    pairs.write_text(json.dumps([{"frames": {"standard": "I have{term}, so", "nonstandard": "I been{term}, so"},
                                  "terms": {"medical": " qa", "patient": " qb"},
                                  "target_clinical_token": " antibiotic"}]), encoding="utf-8")
    q = batch_eval.run_batch(str(pairs), out_dir=str(tmp_path / "q"), mode="4quadrant", dpi=40,
                             fetcher=build_fetcher())[0]
    assert q["probabilities"] == {"A": 0.6, "B": None, "C": 0.6, "D": None}
    assert q["target_read"]["sides"]["B"]["reason"] == "target_not_in_returned_logits"

    pairs.write_text(json.dumps([{"baseline_prompt": "I have one", "target_clinical_token": " antibiotic",
                                  "variants": [{"dialect": "d1", "prompt": "I been one"}]}]), encoding="utf-8")
    d = batch_eval.run_batch(str(pairs), out_dir=str(tmp_path / "d"), mode="dialect", dpi=40,
                             fetcher=build_fetcher())[0]
    assert d["baseline_probability"] == 0.6 and d["variants"][0]["probability"] is None
    assert d["target_read"]["sides"]["variants"][0]["status"] == "missing"
