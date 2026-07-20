"""J-space worked-example exporter (scripts/export_jspace.py) - offline.

Pins the triple read from a mitigation batch_summary, the divergent-trigger
extraction, the middle-layer concept decode against fake raw lens responses (the
CONFIRMED hosted schema), and the empirical/placeholder gate (a missing worked-
example lens trace must leave the empirical:false placeholder untouched). No network.
"""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_jspace", _ROOT / "scripts" / "export_jspace.py")
ext = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ext)


def _resp(per_position_top_tokens, positions_tokens):
    """A raw lens response in the confirmed schema (mirrors the transport test)."""
    n_layers = len(per_position_top_tokens[0]) if per_position_top_tokens else 0
    tokens = []
    for (pos, tok), top_tokens in zip(positions_tokens, per_position_top_tokens):
        tokens.append({"kind": "token", "position": pos, "token": tok,
                       "results": [{"type": "JACOBIAN_LENS", "top_tokens": top_tokens}]})
    return {"meta": {"layers_by_type": {"JACOBIAN_LENS": list(range(n_layers))}},
            "tokens": tokens, "done": {}}


def _write_mitigation(root, batch, index, clinical, patient, translated, target):
    d = root / batch
    d.mkdir(parents=True)
    (d / "batch_summary.part_01.json").write_text(json.dumps({
        "mode": "2panel",
        "results": [{"index": index, "target_token": f'Output "{target}"',
                     "prompts": {"clinical": clinical, "patient": patient,
                                 "translated": translated}}],
    }), encoding="utf-8")


def test_clean_target_and_divergent_word():
    assert ext._clean_target('Output " dermatologist"') == "dermatologist"
    # the clinical term vs the colloquial term is the trigger for each side
    assert ext.divergent_word("I have this itchy rash, so I see a",
                              "I have severe dermatitis, so I see a") == "dermatitis"
    assert ext.divergent_word("same words", "same words") == ""


def test_mid_concepts_reads_the_middle_band_not_the_answer():
    # 5 layers; the middle band (0.35-0.65 of 0..4 -> layers 1..2) carries "skin"/"derm";
    # the final layer carries the answer "dermatologist" and must NOT dominate concepts.
    resp = _resp([
        [[" a"], [" skin", " rash"], [" derm", " skin"], [" x"], [" dermatologist"]],
    ], [(0, "answer")])
    concepts = ext.mid_concepts(resp)
    assert "skin" in concepts and "derm" in concepts
    assert "dermatologist" not in concepts          # middle band, not the final answer
    assert ext.answer_word(resp) == "dermatologist"  # but the output IS the final answer


def test_load_triple_and_placeholder_when_lens_absent(tmp_path):
    root = tmp_path / "trace_out"
    _write_mitigation(root, "mitig", 6,
                      "I have severe dermatitis, so I see a",
                      "I have this itchy rash, so I see a",
                      "I have pruritic dermatitis, so I see a", " dermatologist")
    triple = ext.load_triple(str(root), "mitig", 6)
    assert triple["target"] == "dermatologist" and triple["clinical"].startswith("I have severe")
    # no worked-example lens raw committed -> build_payload returns None (placeholder kept)
    assert ext.build_payload(triple, str(root), "absent_batch", "gemma-2-2b", 1, 2) is None


def test_build_payload_empirical_when_all_three_traced(tmp_path):
    root = tmp_path / "trace_out"
    _write_mitigation(root, "mitig", 6,
                      "I have severe dermatitis all over, so I should see a",
                      "I have this itchy rash all over, so I should see a",
                      "I have pruritic dermatitis all over, so I should see a", " dermatologist")
    triple = ext.load_triple(str(root), "mitig", 6)
    # lens batch traces pair1 = clinical(top)+patient(bottom), pair2 = clinical+translated
    lens = root / "jsw__jlens_gemma-2-2b" / "jlens_raw"
    lens.mkdir(parents=True)

    def _dump(name, answer_final):
        # 4 layers; middle band decodes "skin"; the final layer is the panel output
        resp = _resp([[[" a"], [" skin"], [" skin"], [answer_final]]], [(0, "ans")])
        import gzip
        with gzip.open(lens / name, "wt") as fh:
            json.dump(resp, fh)
    _dump("pair_001_clinical.json.gz", " dermatologist")   # clinical -> on target
    _dump("pair_001_patient.json.gz", " doctor")           # patient -> generic (off target)
    _dump("pair_002_patient.json.gz", " dermatologist")    # translation -> recovers

    payload = ext.build_payload(triple, str(root), "jsw", "gemma-2-2b", 1, 2)
    assert payload["empirical"] is True
    p = payload["panels"]
    assert p["clinical"]["on_target"] is True and p["clinical"]["output"] == "dermatologist"
    assert p["patient"]["on_target"] is False and p["patient"]["output"] == "doctor"
    assert p["translation"]["on_target"] is True and p["translation"]["trigger"] == ""
    assert p["clinical"]["trigger"] == "dermatitis" and p["patient"]["trigger"] == "rash"
    assert "skin" in p["clinical"]["concepts"]
