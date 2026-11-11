"""Pending scientific differences and their dispositions (scripts/payload_dispositions.py), the exporter's
refusal (scripts/export_frontend_simulated.py) and its backend label rule.

A full export on 2026-11-10 would have changed two published qwen3-4b rows to another backend's values,
removed qwen3-4b from eleven rows and flipped the model's capability label, with no decision recorded
(docs/corrections/payload_summary_dedupe_20261110.md). These tests pin:

* what counts as a difference (a changed measured value, a measurement that is no longer there, a changed
  capability label) and what does not (new rows, batches and models, a value where none was published,
  display order, joins, trace links, render lists, the summary block);
* that only an entry covering exactly the difference, with the owner's ``accept_candidate``, passes;
* that the exporter refuses before its first write, in a real and in a dry run, and names no token or prompt;
* the backend label rule: a model's ``traced_by_model`` backend and ``graphs`` follow its exported rows, not
  its first stamp's directory;
* the committed record against the accounting file, the legacy-rows record and, when the sibling site is on
  disk, the published payload.

Every fixture phrase and token is an abstract placeholder that begins with ``zq``; none is a study stimulus.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import payload_dispositions as pd  # noqa: E402
from scripts import results_policy as rp  # noqa: E402

EXPORTER = ROOT / "scripts" / "export_frontend_simulated.py"
RECORD = ROOT / pd.RECORD_REL
ACCOUNTING = ROOT / "ops" / "payload_reexport_accounting_20261110.json"
LEGACY = ROOT / "data" / "results_policy" / "legacy_payload_rows.v1.json"
B1, B2 = "pairs_20200101T000000Z", "pairs_20200102T000000Z"


# ---------------------------------------------------------------- synthetic payloads (pure tests)

def obj(p_clin: float = 0.4, p_pat: float = 0.2, token: str = "zqtok", top_pat: str = "zqother",
        **over: Any) -> dict[str, Any]:
    """One model object as the exporter writes it: all thirteen measured fields."""
    made = {"prob_clinical": p_clin, "prob_patient": p_pat, "language_penalty": round(p_pat - p_clin, 4),
            "anchor_fallback": False, "top_clinical": [token, p_clin], "top_patient": [top_pat, 0.3],
            "spread_clinical": [[token, p_clin], ["zqthird", 0.1]], "spread_patient": [[top_pat, 0.3]],
            "target_token": token, "flipped": token != top_pat, "screening": None, "circuit_diff": None,
            "clinical_mass": None}
    made.update(over)
    return made


def scenario(batch: str, index: int, models: dict[str, Any], display: int = 0) -> dict[str, Any]:
    base = models.get("gemma-2-2b") or next(iter(models.values()))
    return {"index": display or index, "batch": batch, "batch_index": index,
            "clinical_prompt": f"zq clinical wording {batch} {index}", "patient_prompt": f"zq plain wording {index}",
            "intended_target": "zqtok", "models": models, **{k: base[k] for k in pd.MEASURED_FIELDS}}


def meta(model: str, **over: Any) -> dict[str, Any]:
    made = {"id": model, "label": f"label of {model}", "graph_model": model, "source_set": None, "features": False,
            "attention_replacement": False, "graphs": model == "gemma-2-2b", "available": True, "n_traced": 2,
            "default": model == "gemma-2-2b"}
    made.update(over)
    return made


def published() -> dict[str, Any]:
    """Two rows of one batch; gemma-2-2b (hosted) on both, qwen3-4b (logits) on both."""
    return {
        "batches": [{"batch": B1}],
        "summary": {"model": "gemma-2-2b", "penalty": {"n_phrases": 2, "mean_phrase_deduped": -0.2}},
        "traced": {"graph_model": "gemma-2-2b", "mode": "2panel", "backend": "hosted"},
        "traced_by_model": {"gemma-2-2b": {"graph_model": "gemma-2-2b", "mode": "2panel", "backend": "hosted"},
                            "qwen3-4b": {"graph_model": "qwen3-4b", "mode": "2panel", "backend": "logits"}},
        "models_meta": [meta("gemma-2-2b"), meta("qwen3-4b")],
        "scenarios": [scenario(B1, 1, {"gemma-2-2b": obj(), "qwen3-4b": obj(0.5, 0.1)}),
                      scenario(B1, 2, {"gemma-2-2b": obj(0.3, 0.3), "qwen3-4b": obj(0.6, 0.2)})],
    }


def row(payload: dict[str, Any], batch: str, index: int) -> dict[str, Any]:
    return next(s for s in payload["scenarios"] if (s["batch"], s["batch_index"]) == (batch, index))


def identities(differences: list[dict[str, Any]]) -> list[tuple]:
    return [pd.identity(d) for d in differences]


# ---------------------------------------------------------------- the field lists against the exporter

def _exporter_tree() -> ast.Module:
    return ast.parse(EXPORTER.read_text(encoding="utf-8"))


def _returned_dict_keys(tree: ast.Module, function: str) -> list[str]:
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
    ret = next(n for n in ast.walk(fn) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict))
    return [k.value for k in ret.value.keys]


def test_the_measured_fields_are_exactly_what_the_exporter_writes_per_model_and_the_contract_requires():
    tree = _exporter_tree()
    assert sorted(_returned_dict_keys(tree, "build_model_obj")) == sorted(pd.MEASURED_FIELDS)
    compat = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                  and getattr(n.targets[0], "id", None) == "COMPAT")
    assert sorted(ast.literal_eval(compat)) == sorted(pd.MEASURED_FIELDS)      # the top-level mirror
    schema = json.loads((ROOT / "scripts/contracts/simulated_scenarios.v1.schema.json").read_text(encoding="utf-8"))
    assert sorted(schema["definitions"]["model"]["required"]) == sorted(pd.MEASURED_FIELDS)
    assert set(pd.DERIVED_FROM) <= set(pd.MEASURED_FIELDS)


def test_every_models_meta_and_traced_field_the_exporter_writes_is_classified():
    """A field added to the exporter's models_meta has to be put in one of the two lists here: compared as a
    capability label, or named as not compared with its reason."""
    tree = _exporter_tree()
    assign = next(n for n in tree.body if isinstance(n, ast.Assign)
                  and getattr(n.targets[0], "id", None) == "models_meta")
    written = [k.value for k in assign.value.elt.keys]
    assert sorted(written) == sorted([*pd.MODELS_META_CAPABILITY, *pd.MODELS_META_NOT_COMPARED])
    assert not set(pd.MODELS_META_CAPABILITY) & set(pd.MODELS_META_NOT_COMPARED)
    source = EXPORTER.read_text(encoding="utf-8")
    keys = re.search(r"for key in \(([^)]*)\):\n\s+if summary\.get\(key\):\n\s+meta\[key\]", source)
    assert keys and tuple(ast.literal_eval(f"({keys.group(1)})")) == pd.TRACED_FIELDS


# ---------------------------------------------------------------- what is not a difference

def test_identical_payloads_and_non_measurement_churn_are_not_differences():
    reference, candidate = published(), published()
    assert pd.scientific_differences(reference, candidate) == []
    # display order, the joins of later publish steps, trace links, render lists, the summary block, counts
    for i, s in enumerate(candidate["scenarios"]):
        s["index"] = 40 + i
        s["trace_url"] = f"https://example.invalid/traces/{i}"
        s["depth_class"] = "late"
        s["urgency"] = {"flip_class": "downgrade", "tier_shift": -0.4}
        s["html"] = f"modes/simulated/{B1}/index_{i + 1:02d}.html"
        s["models"]["gemma-2-2b"]["html"] = s["html"]
        s["models"]["qwen3-4b"]["urgency"] = {"flip_class": None, "tier_shift": 0.1}
        s["rationale"], s["topic"] = "zq rationale", "zq topic"
    candidate["summary"] = {"model": "gemma-2-2b", "penalty": {"n_phrases": 1, "mean_phrase_deduped": -0.1}}
    candidate["urgency_meta"] = {"per_model_deduped": {"qwen3-4b": {"n_phrases": 1}}}
    candidate["traces_site"] = {"_provenance": {"engine_sha": "abc", "generated_utc": "2020-01-02T00:00:00Z"}}
    candidate["featured"], candidate["depth_model"], candidate["holdout_withheld"] = {"x": []}, "gemma-2-2b", 3
    candidate["archive"] = {"release_url": "https://example.invalid/releases"}
    for m in candidate["models_meta"]:
        m["n_traced"], m["label"] = 99, "another display name"
    assert pd.scientific_differences(reference, candidate) == []


def test_new_rows_a_new_batch_and_a_new_model_on_existing_rows_are_not_differences():
    reference, candidate = published(), published()
    candidate["scenarios"].insert(1, scenario(B1, 7, {"gemma-2-2b": obj(0.9, 0.1)}))              # a new row
    candidate["scenarios"].append(scenario(B2, 1, {"gemma-2-2b": obj(), "qwen3-4b": obj()}))        # a new batch
    candidate["batches"].append({"batch": B2})
    for s in candidate["scenarios"]:
        s["models"]["olmo-2-1b"] = obj(0.7, 0.6)                                                    # a new model
    candidate["models_meta"].append(meta("olmo-2-1b", graphs=True, features=True))
    candidate["traced_by_model"]["olmo-2-1b"] = {"graph_model": "olmo-2-1b", "backend": "hosted"}
    assert pd.scientific_differences(reference, candidate) == []


def test_a_value_where_the_reference_had_none_is_not_a_difference():
    reference, candidate = published(), published()
    # row 2 of the reference: screened out, patient side never measured
    unmeasured = row(reference, B1, 2)["models"]["qwen3-4b"]
    unmeasured.update(prob_patient=None, language_penalty=None, top_patient=None, spread_patient=[], flipped=False,
                      clinical_mass=None, circuit_diff=None)
    filled = row(candidate, B1, 2)["models"]["qwen3-4b"]
    filled.update(circuit_diff={"shared_features": 3, "unique_to_a": 1, "unique_to_b": 2},
                  clinical_mass={"clinical": 0.2, "patient": 0.1})
    assert filled["flipped"] is True and unmeasured["flipped"] is False      # derived: no patient side, no flip
    assert pd.scientific_differences(reference, candidate) == []
    # the same object entirely unmeasured in the reference: its removal takes nothing published away
    blank = {k: None for k in pd.MEASURED_FIELDS} | {"spread_clinical": [], "spread_patient": [],
                                                      "flipped": False, "anchor_fallback": False}
    row(reference, B1, 2)["models"]["qwen3-4b"] = blank
    del row(candidate, B1, 2)["models"]["qwen3-4b"]
    assert pd.scientific_differences(reference, candidate) == []


def test_the_summary_only_restamp_is_not_a_difference():
    """scripts/restamp_payload_summary.py rewrites summary.penalty and leaves every scenario's bytes."""
    reference, candidate = published(), published()
    candidate["summary"]["penalty"] = {"n_phrases": 1, "mean_phrase_deduped": -0.19, "ci95": [-0.3, -0.1]}
    assert pd.scientific_differences(reference, candidate) == []
    assert pd.review(pd.scientific_differences(reference, candidate), pd.Record()) == []


# ---------------------------------------------------------------- what is a difference

def test_a_changed_measured_value_is_a_difference_compared_exactly_and_described_without_text():
    reference, candidate = published(), published()
    changed = row(candidate, B1, 1)["models"]["qwen3-4b"]
    changed.update(prob_clinical=0.037, prob_patient=0.058, language_penalty=0.021000000000000005,
                   target_token="zqto", top_clinical=["zqto", 0.309])
    [difference] = pd.scientific_differences(reference, candidate)
    assert pd.identity(difference) == ("row", B1, 1, "qwen3-4b") and difference["change"] == "values_changed"
    assert difference["fields"] == ["language_penalty", "prob_clinical", "prob_patient", "target_token",
                                    "top_clinical"]
    assert difference["reference"]["values"]["language_penalty"] == -0.4
    assert difference["candidate"]["values"]["language_penalty"] == 0.021000000000000005   # as stored, unrounded
    assert difference["reference"]["values"]["target_token_chars"] == 5
    assert difference["candidate"]["values"]["target_token_chars"] == 4
    assert difference["reference"]["measurement_sha256"] != difference["candidate"]["measurement_sha256"]
    dumped = json.dumps(difference) + pd.describe(difference)
    assert "zq" not in dumped                                           # no token, no prompt
    assert "language_penalty -0.4 -> 0.021000000000000005" in pd.describe(difference)
    # a rounding-sized change is a change: these are published numbers
    reference, candidate = published(), published()
    row(candidate, B1, 2)["models"]["gemma-2-2b"]["prob_clinical"] = 0.30000000000000004
    assert [d["fields"] for d in pd.scientific_differences(reference, candidate)] == [["prob_clinical"]]


def test_a_changed_token_at_the_same_probability_a_flag_and_a_value_that_became_null_are_differences():
    reference, candidate = published(), published()
    row(candidate, B1, 1)["models"]["qwen3-4b"]["top_patient"] = ["zqelse", 0.3]        # another token, same p
    row(candidate, B1, 2)["models"]["qwen3-4b"]["flipped"] = False                      # was true
    row(candidate, B1, 2)["models"]["gemma-2-2b"]["prob_patient"] = None                # was 0.3
    found = {pd.identity(d)[1:]: d["fields"] for d in pd.scientific_differences(reference, candidate)}
    assert found == {(B1, 1, "qwen3-4b"): ["top_patient"], (B1, 2, "qwen3-4b"): ["flipped"],
                     (B1, 2, "gemma-2-2b"): ["prob_patient"]}
    assert pd.same(1, 1.0) and not pd.same(True, 1) and not pd.same(0, False) and not pd.same(None, 0)
    assert pd.same([["a", 0.5]], [["a", 0.5]]) and not pd.same([["a", 0.5]], [["a", 0.5], ["b", 0.1]])


def test_a_model_removed_from_a_row_and_a_removed_row_are_differences():
    reference, candidate = published(), published()
    del row(candidate, B1, 1)["models"]["qwen3-4b"]
    candidate["scenarios"] = [s for s in candidate["scenarios"] if s["batch_index"] != 2]
    found = {pd.identity(d)[1:]: d for d in pd.scientific_differences(reference, candidate)}
    assert {k: v["change"] for k, v in found.items()} == {
        (B1, 1, "qwen3-4b"): "model_removed", (B1, 2, "gemma-2-2b"): "row_removed",
        (B1, 2, "qwen3-4b"): "row_removed"}
    removed = found[(B1, 1, "qwen3-4b")]
    assert removed["candidate"] is None and "prob_clinical" in removed["fields"]
    assert "circuit_diff" not in removed["fields"]                      # it held no value: nothing is lost
    assert "published prob_clinical 0.5" in pd.describe(removed) and "no longer there" in pd.describe(removed)


def test_a_capability_label_flip_is_a_difference_and_only_for_a_model_in_both_payloads():
    reference, candidate = published(), published()
    next(m for m in candidate["models_meta"] if m["id"] == "qwen3-4b")["graphs"] = True
    candidate["traced_by_model"]["qwen3-4b"]["backend"] = "hosted"
    differences = pd.scientific_differences(reference, candidate)
    assert identities(differences) == [("metadata", "models_meta", "qwen3-4b", "graphs"),
                                       ("metadata", "traced_by_model", "qwen3-4b", "backend")]
    assert [pd.describe(d) for d in differences] == ["models_meta.qwen3-4b.graphs: false -> true",
                                                     "traced_by_model.qwen3-4b.backend: logits -> hosted"]
    # every capability field, and a field the candidate dropped
    reference, candidate = published(), published()
    qwen = next(m for m in candidate["models_meta"] if m["id"] == "qwen3-4b")
    qwen.update(features=True, source_set="transcoder-xx", attention_replacement=True)
    del candidate["traced_by_model"]["gemma-2-2b"]["mode"]
    assert identities(pd.scientific_differences(reference, candidate)) == [
        ("metadata", "models_meta", "qwen3-4b", "source_set"), ("metadata", "models_meta", "qwen3-4b", "features"),
        ("metadata", "models_meta", "qwen3-4b", "attention_replacement"),
        ("metadata", "traced_by_model", "gemma-2-2b", "mode")]
    # a model that left the candidate is reported row by row, not through its labels
    reference, candidate = published(), published()
    candidate["models_meta"] = [m for m in candidate["models_meta"] if m["id"] != "qwen3-4b"]
    del candidate["traced_by_model"]["qwen3-4b"]
    for s in candidate["scenarios"]:
        del s["models"]["qwen3-4b"]
    assert {d["scope"] for d in pd.scientific_differences(reference, candidate)} == {"row"}


def test_an_older_payload_without_models_is_compared_through_its_base_mirror():
    reference, candidate = published(), published()
    for s in reference["scenarios"]:
        del s["models"]                                                 # the top-level fields are the base model's
    del reference["traced_by_model"]
    assert pd.scientific_differences(reference, candidate) == []
    row(candidate, B1, 1)["models"]["gemma-2-2b"]["prob_clinical"] = 0.41
    candidate["traced_by_model"]["gemma-2-2b"]["backend"] = "logits"
    assert identities(pd.scientific_differences(reference, candidate)) == [
        ("row", B1, 1, "gemma-2-2b"), ("metadata", "traced_by_model", "gemma-2-2b", "backend")]


def test_published_rows_without_an_identity_cannot_be_compared_and_never_pass():
    reference, candidate = published(), published()
    del reference["scenarios"][0]["batch"]
    differences = pd.scientific_differences(reference, candidate)
    assert {"scope": "unidentified", "count": 1} in differences
    [verdict] = [v for v in pd.review(differences, pd.Record()) if v["difference"]["scope"] == "unidentified"]
    assert verdict["passes"] is False and verdict["status"] == "cannot_be_compared"
    # a scenario that carries no measurement (a stale render pointer) is not one of them
    reference = {"scenarios": [{"html": f"modes/simulated/{B1}/index_03.html"}]}
    assert pd.scientific_differences(reference, published()) == []


# ---------------------------------------------------------------- dispositions

def _accepted(difference: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {**pd.pending_entry(difference), "disposition": pd.ACCEPT, "decided_by": "owner",
            "decision_ref": "docs/decision.md#d4", **over}


def _one_change() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    reference, candidate = published(), published()
    row(candidate, B1, 1)["models"]["qwen3-4b"].update(prob_clinical=0.45, language_penalty=-0.35)
    [difference] = pd.scientific_differences(reference, candidate)
    return reference, candidate, difference


def _verdict(difference: dict[str, Any], entries: list[Any], **record: Any) -> dict[str, Any]:
    [verdict] = pd.review([difference], pd.Record(entries=entries, **record))
    return verdict


def test_a_difference_with_no_entry_and_a_pending_entry_do_not_pass():
    _, _, difference = _one_change()
    assert _verdict(difference, [])["status"] == "no_disposition"
    pending = pd.pending_entry(difference)
    assert pending["disposition"] == "pending" and pending["decided_by"] is None and pending["decision_ref"] is None
    verdict = _verdict(difference, [pending])
    assert verdict["passes"] is False and verdict["status"] == "pending"
    assert pd.refused([verdict]) == [verdict]


def test_only_the_owners_accept_candidate_for_exactly_this_difference_passes():
    _, _, difference = _one_change()
    verdict = _verdict(difference, [_accepted(difference)], exists=lambda rel: rel == "docs/decision.md")
    assert verdict["passes"] is True and verdict["status"] == "accept_candidate"
    assert "docs/decision.md#d4" in verdict["reason"]
    for disposition in (pd.KEEP, pd.WITHHOLD):                          # decided, and not in the candidate's favour
        verdict = _verdict(difference, [_accepted(difference, disposition=disposition)])
        assert verdict["passes"] is False and verdict["status"] == disposition
    # two entries for the same difference that disagree: neither is taken
    verdict = _verdict(difference, [pd.pending_entry(difference), _accepted(difference)])
    assert verdict["passes"] is False and verdict["status"] == "conflicting_entries"
    assert _verdict(difference, [_accepted(difference), _accepted(difference)])["passes"] is True
    assert set(pd.DISPOSITIONS) == {"pending", "accept_candidate", "keep_reference", "withhold"}


def test_a_disposition_whose_recorded_values_are_not_the_actual_ones_does_not_pass():
    _, _, difference = _one_change()
    for mutate in (lambda e: e["candidate"]["values"].__setitem__("prob_clinical", 0.46),
                   lambda e: e["reference"]["values"].__setitem__("prob_clinical", 0.51),
                   lambda e: e["candidate"].__setitem__("measurement_sha256", "0" * 64),
                   lambda e: e.__setitem__("fields", ["prob_clinical"]),
                   lambda e: e.__setitem__("change", "model_removed"),
                   lambda e: e.__setitem__("candidate", None)):
        entry = copy.deepcopy(_accepted(difference))
        mutate(entry)
        verdict = _verdict(difference, [entry])
        assert verdict["passes"] is False and verdict["status"] == "values_do_not_match", entry
    # an entry for another identity is no entry for this one
    other = copy.deepcopy(_accepted(difference))
    other["batch_index"] = 2
    assert _verdict(difference, [other])["status"] == "no_disposition"
    # the removal accepted: a later export that brings a value back is another difference
    reference, candidate = published(), published()
    del row(candidate, B1, 1)["models"]["qwen3-4b"]
    [removal] = pd.scientific_differences(reference, candidate)
    assert _verdict(removal, [_accepted(removal)])["passes"] is True
    _, _, changed = _one_change()
    assert _verdict(changed, [_accepted(removal)])["status"] == "values_do_not_match"


def test_an_accepting_entry_needs_the_owner_a_decision_document_and_a_committed_record():
    _, _, difference = _one_change()
    for over, says in (({"decided_by": "session"}, "the owner's"), ({"decided_by": None}, "the owner's"),
                       ({"decision_ref": ""}, "decision_ref is empty"), ({"decision_ref": None}, "decision_ref"),
                       ({"disposition": "approved"}, "is not one of")):
        verdict = _verdict(difference, [_accepted(difference, **over)])
        assert verdict["passes"] is False and verdict["status"] == "invalid_entry" and says in verdict["reason"]
    verdict = _verdict(difference, [_accepted(difference)], exists=lambda rel: False)
    assert verdict["status"] == "invalid_entry" and "not a committed file" in verdict["reason"]
    verdict = _verdict(difference, [_accepted(difference)], committed=False)
    assert verdict["passes"] is False and verdict["status"] == "record_not_committed"
    assert _verdict(difference, [_accepted(difference)], committed=True)["passes"] is True
    assert pd.entry_problem({**pd.pending_entry(difference), "decided_by": "owner"}) == \
        "a pending entry names no decision"
    assert pd.entry_problem("not an object") and pd.entry_problem({"scope": "file"})


def test_a_metadata_difference_is_disposed_the_same_way():
    reference, candidate = published(), published()
    next(m for m in candidate["models_meta"] if m["id"] == "qwen3-4b")["graphs"] = True
    [difference] = pd.scientific_differences(reference, candidate)
    assert _verdict(difference, [pd.pending_entry(difference)])["status"] == "pending"
    assert _verdict(difference, [_accepted(difference)])["passes"] is True
    assert _verdict(difference, [_accepted(difference, candidate=False)])["status"] == "values_do_not_match"


def test_the_table_lists_refusals_first_explains_each_status_once_and_counts_what_it_does_not_list():
    reference, candidate = published(), published()
    for s in candidate["scenarios"]:
        s["models"]["qwen3-4b"]["prob_clinical"] = 0.99
    del row(candidate, B1, 2)["models"]["gemma-2-2b"]
    differences = pd.scientific_differences(reference, candidate)
    reviewed = pd.review(differences, pd.Record(entries=[_accepted(differences[0])]))
    lines = pd.format_table(reviewed)
    assert [line.split()[0] for line in lines[:3]] == ["REFUSED", "REFUSED", "accepted"]
    assert sum("[no_disposition] no entry in" in line for line in lines) == 1      # the explanation, once
    assert "zq" not in "\n".join(lines)
    short = pd.format_table(reviewed, limit=1)
    assert "... and 2 more (1 without an accepting disposition)" in short[1]


def test_a_record_that_cannot_be_read_is_refused_and_an_absent_one_disposes_nothing(tmp_path):
    assert pd.parse_record(None, source="x").entries == []
    for bad in ("{not json", json.dumps([]), json.dumps({"schema": "other/1", "entries": []}),
                json.dumps({"schema": pd.SCHEMA, "entries": {}})):
        with pytest.raises(pd.DispositionError):
            pd.parse_record(bad, source="x")
    with pytest.raises(pd.DispositionError):
        pd.load_payload("[]", "a payload")
    record = pd.load_record(tmp_path)                                   # not a git checkout, no record
    assert record.entries == [] and record.committed is None


# ---------------------------------------------------------------- synthetic engine and site (exporter tests)

S1, S2 = "20200101T000000Z", "20200102T000000Z"
PHRASES = ["zq alpha wording 0", "zq alpha wording 1", "zq alpha wording 2"]


def _write(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


def _result(index: int, p_clin: float = 0.4, p_pat: float = 0.2) -> dict[str, Any]:
    clinical = PHRASES[index - 1]
    return {"index": index, "prompts": {"clinical": clinical, "patient": f"{clinical} plain"},
            "probabilities": {"clinical": p_clin, "patient": p_pat}, "language_penalty": round(p_pat - p_clin, 4),
            "target_token": 'Output " zqtok"',
            "predictive_spread": {"clinical": [['Output " zqtok"', p_clin]], "patient": [['Output " zqother"', 0.3]]}}


def base_engine(engine: Path, stamps: tuple[str, ...] = (S1,), base_rows: tuple[int, ...] = (1, 2, 3)) -> Path:
    """Per stamp: the batch file, its report, a hosted gemma-2-2b part and its renders. No Tier B start
    covers these stamps, so nothing is withheld."""
    _write(engine / "ops" / "dashboard.json", {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}})
    for stamp in stamps:
        stem = f"pairs_{stamp}"
        _write(engine / "data" / "simulated" / f"{stem}.json",
               [{"top_prompt": p, "bottom_prompt": f"{p} plain", "target_clinical_token": " zqtok"} for p in PHRASES])
        _write(engine / "data" / "simulated" / f"{stem}.report.json", {"accepted": len(PHRASES)})
        _write(engine / "trace_out" / stem / "batch_summary.part_01.json",
               {"graph_model": "gemma-2-2b", "backend": "hosted", "mode": "2panel",
                "results": [_result(i) for i in base_rows]})
        for i in base_rows:
            _write(engine / "trace_out" / stem / f"index_{i:02d}.html", f"<html>render {stem} {i}</html>")
    return engine


def part(engine: Path, stamp: str, model: str, number: int, backend: str, rows: dict[int, tuple[float, float]],
         pinned: bool = True) -> Path:
    """One summary part of ``model`` in ``stamp``'s directory. A logits part is read only when pinned."""
    path = _write(engine / "trace_out" / f"pairs_{stamp}__{model}" / f"batch_summary.part_{number:02d}.json",
                  {"graph_model": model, "backend": backend, "mode": "2panel", "source_set": None,
                   "results": [_result(i, *p) for i, p in rows.items()]})
    manifest_path = engine / rp.RELEASE_MANIFEST
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists()
                else {"schema": rp.MANIFEST_SCHEMA, "parts": {}})
    rel = path.relative_to(engine).as_posix()
    manifest["parts"].pop(rel, None)
    if backend == "logits" and pinned:
        manifest["parts"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write(manifest_path, manifest)
    return path


def export(engine: Path, site: Path, stamps: str = S1, models: str = "gemma-2-2b,qwen3-4b",
           *extra: str) -> subprocess.CompletedProcess[str]:
    (site / "data").mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, str(EXPORTER), "--engine", str(engine), "--frontend", str(site),
                           "--stamps", stamps, "--models", models, *extra],
                          capture_output=True, text=True, cwd=str(engine), timeout=120)


def git(root: Path, *argv: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                           "-c", "commit.gpgsign=false", *argv], check=True, capture_output=True, text=True).stdout


def commit_all(root: Path, message: str = "state") -> None:
    if not (root / ".git").exists():
        git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts}


def payload_of(site: Path) -> dict[str, Any]:
    return json.loads((site / pd.PAYLOAD_REL).read_text(encoding="utf-8"))


QWEN = {1: (0.5, 0.1), 2: (0.6, 0.2), 3: (0.7, 0.3)}


@pytest.fixture
def released(tmp_path):
    """An engine with gemma-2-2b (hosted) and qwen3-4b (pinned logits) on three rows, and a site git checkout
    whose HEAD commit holds the export of exactly that."""
    engine, site = base_engine(tmp_path / "engine"), tmp_path / "site"
    part(engine, S1, "qwen3-4b", 1, "logits", QWEN)
    first = export(engine, site)
    assert first.returncode == 0, first.stderr + first.stdout
    assert "difference(s) from" not in first.stdout                     # no payload yet: no reference
    commit_all(site, "published")
    return engine, site


# ---------------------------------------------------------------- the exporter's refusal

def test_the_exporter_refuses_a_changed_published_value_before_any_write_copy_or_prune(released):
    engine, site = released
    _write(site / "modes" / "simulated" / "pairs_20190101T000000Z" / "index_01.html", "<html>orphan</html>")
    commit_all(site, "an unlisted render the next export would prune")
    part(engine, S1, "qwen3-4b", 1, "logits", {**QWEN, 2: (0.61, 0.2)})          # row 2 re-measured
    _write(engine / "trace_out" / f"pairs_{S1}" / "index_01.html", "<html>a newer render</html>")
    before = files(site)
    for extra in ((), ("--dry-run",)):
        proc = export(engine, site, S1, "gemma-2-2b,qwen3-4b", *extra)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "refusing: this export changes 1 published measurement" in proc.stderr
        assert "Nothing was written or pruned" in proc.stderr
        assert f"REFUSED  [no_disposition] ({B1}, 2, qwen3-4b) values_changed: prob_clinical 0.6 -> 0.61" in proc.stdout
        assert "in the site's HEAD commit" in proc.stdout and "scenarios (" not in proc.stdout
        assert "zq" not in proc.stdout + proc.stderr                    # no prompt, no token
        assert files(site) == before                                    # payload, renders, the orphan: untouched
    # the same export of unchanged inputs is not refused, and then it prunes and copies
    part(engine, S1, "qwen3-4b", 1, "logits", QWEN)
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stderr
    assert "difference(s) from" not in proc.stdout and "1 unlisted render(s) pruned" in proc.stdout
    assert (site / "modes" / "simulated" / B1 / "index_01.html").read_text(encoding="utf-8") == "<html>a newer render</html>"


def test_the_exporter_refuses_a_model_removed_from_published_rows(released):
    engine, site = released
    part(engine, S1, "qwen3-4b", 1, "logits", QWEN, pinned=False)       # the membership no longer reads it
    before = files(site)
    proc = export(engine, site)
    assert proc.returncode == 1 and "changes 3 published measurement" in proc.stderr
    assert proc.stdout.count("model_removed") == 3 and f"({B1}, 3, qwen3-4b) model_removed" in proc.stdout
    assert files(site) == before
    proc = export(engine, site, S1, "gemma-2-2b")                       # left out with --models: the same loss
    assert proc.returncode == 1 and proc.stdout.count("model_removed") == 3
    assert files(site) == before


def test_the_exporter_refuses_a_dropped_stamp(tmp_path):
    engine, site = base_engine(tmp_path / "engine", (S1, S2)), tmp_path / "site"
    assert export(engine, site, f"{S1},{S2}", "gemma-2-2b").returncode == 0
    commit_all(site)
    proc = export(engine, site, S2, "gemma-2-2b")
    assert proc.returncode == 1 and proc.stdout.count("row_removed") == 3
    assert f"({B1}, 1, gemma-2-2b) row_removed" in proc.stdout


def test_the_exporter_refuses_a_capability_label_flip(released):
    """The same rows with the same values, now read from a hosted part: only the label changes."""
    engine, site = released
    (engine / "trace_out" / f"pairs_{S1}__qwen3-4b" / "batch_summary.part_01.json").unlink()
    part(engine, S1, "qwen3-4b", 2, "hosted", QWEN)
    before = files(site)
    proc = export(engine, site)
    assert proc.returncode == 1 and "changes 2 published measurement(s) or capability label(s)" in proc.stderr
    assert "REFUSED  [no_disposition] models_meta.qwen3-4b.graphs: false -> true" in proc.stdout
    assert "REFUSED  [no_disposition] traced_by_model.qwen3-4b.backend: logits -> hosted" in proc.stdout
    assert files(site) == before


def test_new_rows_a_new_batch_and_a_new_model_are_exported_without_a_disposition(tmp_path):
    engine, site = base_engine(tmp_path / "engine", (S1, S2), base_rows=(1, 2)), tmp_path / "site"
    part(engine, S1, "qwen3-4b", 1, "logits", {1: QWEN[1]})
    assert export(engine, site, S1).returncode == 0
    commit_all(site)
    published_rows = {(s["batch"], s["batch_index"]): s["index"] for s in payload_of(site)["scenarios"]}
    assert published_rows == {(B1, 1): 1, (B1, 2): 2}
    # a third row of the published batch, a second batch, qwen3-4b on a second row, a model new to the payload
    _write(engine / "trace_out" / f"pairs_{S1}" / "batch_summary.part_03.json",
           {"graph_model": "gemma-2-2b", "backend": "hosted", "mode": "2panel", "results": [_result(3)]})
    part(engine, S1, "qwen3-4b", 2, "logits", {2: QWEN[2]})
    part(engine, S1, "qwen3-1.7b", 1, "logits", {1: (0.2, 0.2), 2: (0.3, 0.1)})
    proc = export(engine, site, f"{S1},{S2}", "gemma-2-2b,qwen3-4b,qwen3-1.7b")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "difference(s) from" not in proc.stdout
    after = payload_of(site)
    assert {(s["batch"], s["batch_index"]): s["index"] for s in after["scenarios"]} == {
        (B1, 1): 1, (B1, 2): 2, (B1, 3): 3, (B2, 1): 4, (B2, 2): 5}
    assert [m["id"] for m in after["models_meta"]] == ["gemma-2-2b", "qwen3-4b", "qwen3-1.7b"]
    assert set(row(after, B1, 2)["models"]) == {"gemma-2-2b", "qwen3-4b", "qwen3-1.7b"}


def test_the_exporter_passes_a_difference_only_with_the_owners_recorded_disposition(released, tmp_path):
    engine, site = released
    part(engine, S1, "qwen3-4b", 1, "logits", {**QWEN, 2: (0.61, 0.2)})
    scratch = tmp_path / "scratch-site"                                 # no payload there: no reference
    assert export(engine, scratch).returncode == 0
    record_path = engine / pd.RECORD_REL
    assert pd.main(["propose", "--reference", str(site / pd.PAYLOAD_REL), "--candidate",
                    str(scratch / pd.PAYLOAD_REL), "--engine", str(engine), "--write"]) == 0
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["schema"] == pd.SCHEMA and record["count"] == 1
    [entry] = record["entries"]
    assert entry["disposition"] == "pending" and (entry["batch"], entry["batch_index"]) == (B1, 2)
    before = files(site)

    def refused_with(status: str) -> None:
        _write(record_path, record)
        proc = export(engine, site)
        assert proc.returncode == 1 and f"REFUSED  [{status}] ({B1}, 2, qwen3-4b)" in proc.stdout, proc.stdout
        assert files(site) == before

    refused_with("pending")
    entry.update(disposition="accept_candidate", decided_by="owner", decision_ref="docs/decision.md#row-2")
    refused_with("invalid_entry")                                       # the decision document does not exist
    _write(engine / "docs" / "decision.md", "the owner accepts the re-measured row 2")
    entry["candidate"]["values"]["prob_clinical"] = 0.62                # not what the export holds
    refused_with("values_do_not_match")
    entry["candidate"]["values"]["prob_clinical"] = 0.61
    entry["decided_by"] = "session"
    refused_with("invalid_entry")
    entry["decided_by"] = "owner"
    _write(record_path, record)
    proc = export(engine, site)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"accepted [accept_candidate] ({B1}, 2, qwen3-4b) values_changed" in proc.stdout
    assert "1 difference(s)" in proc.stdout and "0 without an accepting owner disposition, 1 accepted" in proc.stdout
    assert row(payload_of(site), B1, 2)["models"]["qwen3-4b"]["prob_clinical"] == 0.61
    # proposing again adds nothing: the difference is covered
    assert pd.main(["propose", "--reference", str(scratch / pd.PAYLOAD_REL), "--candidate",
                    str(site / pd.PAYLOAD_REL), "--engine", str(engine), "--write"]) == 0
    assert json.loads(record_path.read_text(encoding="utf-8"))["count"] == 1


def test_an_accepting_record_that_is_not_committed_in_the_engine_does_not_pass(released, tmp_path):
    engine, site = released
    part(engine, S1, "qwen3-4b", 1, "logits", {**QWEN, 2: (0.61, 0.2)})
    scratch = tmp_path / "scratch-site"
    assert export(engine, scratch).returncode == 0
    [difference] = pd.scientific_differences(payload_of(site), payload_of(scratch))
    _write(engine / "docs" / "decision.md", "the owner accepts the re-measured row 2")
    commit_all(engine, "engine without a record")
    _write(engine / pd.RECORD_REL, {"schema": pd.SCHEMA, "entries": [_accepted(difference)]})
    proc = export(engine, site)                                         # the record is an untracked file
    assert proc.returncode == 1 and "REFUSED  [record_not_committed]" in proc.stdout
    commit_all(engine, "the reviewed record")
    assert pd.load_record(engine).committed is True
    assert export(engine, site, S1, "gemma-2-2b,qwen3-4b", "--dry-run").returncode == 0


def test_the_reference_is_the_sites_head_commit_whatever_the_working_tree_holds(released):
    engine, site = released
    part(engine, S1, "qwen3-4b", 1, "logits", {**QWEN, 2: (0.61, 0.2)})
    (site / pd.PAYLOAD_REL).unlink()                                    # deleting the file is not a way through
    proc = export(engine, site)
    assert proc.returncode == 1 and "values_changed" in proc.stdout
    assert not (site / pd.PAYLOAD_REL).exists()
    _write(site / pd.PAYLOAD_REL, "{}")                                 # nor is emptying it
    assert export(engine, site).returncode == 1
    reference, enforced, where = pd.site_reference(site)
    assert enforced is True and "HEAD commit" in where and json.loads(reference)["scenarios"]


def test_a_payload_on_disk_that_head_does_not_hold_is_the_reference_and_an_unreadable_one_refuses(tmp_path):
    engine, site = base_engine(tmp_path / "engine"), tmp_path / "site"
    part(engine, S1, "qwen3-4b", 1, "logits", QWEN)
    _write(site / "README.txt", "a site checkout with no payload committed")
    commit_all(site)
    assert pd.site_reference(site) == (None, True, f"{pd.PAYLOAD_REL} on disk (the site's HEAD commit holds none)")
    assert export(engine, site).returncode == 0                         # no payload anywhere: no reference
    part(engine, S1, "qwen3-4b", 1, "logits", {**QWEN, 2: (0.61, 0.2)})
    proc = export(engine, site)                                         # the uncommitted payload is the reference
    assert proc.returncode == 1 and "on disk (the site's HEAD commit holds none)" in proc.stdout
    _write(site / pd.PAYLOAD_REL, "{truncated")
    proc = export(engine, site)
    assert proc.returncode == 1 and "cannot be compared with what the site publishes" in proc.stderr
    assert (site / pd.PAYLOAD_REL).read_text(encoding="utf-8") == "{truncated"


def test_a_directory_that_is_not_a_git_checkout_is_reported_and_not_enforced(tmp_path):
    """verify.md's temporary regeneration and scripts/check_frontend_boundary.py export into a copy of the
    site without ``.git``; the boundary check exports synthetic stamps over the copied published payload."""
    engine, site = base_engine(tmp_path / "engine", (S1, S2)), tmp_path / "copy"
    part(engine, S1, "qwen3-4b", 1, "logits", QWEN)
    assert export(engine, site, S1).returncode == 0
    assert pd.site_reference(site)[1] is False
    proc = export(engine, site, S2, "gemma-2-2b")                       # other stamps entirely
    assert proc.returncode == 0, proc.stderr
    assert "6 difference(s) from data/simulated_scenarios.json on disk" in proc.stdout
    assert "not enforced:" in proc.stdout and "is not a git checkout" in proc.stdout
    assert "differs  [no_disposition]" in proc.stdout and "REFUSED" not in proc.stdout
    assert {s["batch"] for s in payload_of(site)["scenarios"]} == {B2}


# Git words one error differently across versions. For a ``.git`` file that names a directory that does not
# exist, git 2.43 prints "fatal: not a git repository: <directory>". The git on GitHub's hosted runners on
# 2026-11-11 (2.56) prints a message that ends "... does not point to a valid repository: <site>/.git" (its
# start was cut off in the log this was read from). The export has two guards that can refuse such a site.
# The render-prune guard (scripts/sparse_guard.py) reads the first wording as "no checkout here" and lets
# the export reach the disposition check, which refuses; under the second wording the prune guard refuses
# first. The test pinned the disposition check's message and failed on the hosted runner for that reason.
GIT_WORDINGS = ("the installed git", "a git that words a .git file pointing nowhere as the hosted runner's does")


def _reword_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Put a stand-in ``git`` first on PATH. It runs the real git with the same arguments, output and exit
    status, and replaces only the older wording of that one error with the newer wording."""
    real = shutil.which("git")
    assert real, "git is not installed"
    shim = tmp_path / "git_shim" / "git"
    _write(shim, "#!/bin/sh\n"
                 'err=$(mktemp)\n'
                 f'"{real}" "$@" 2>"$err"; rc=$?\n'
                 "if [ $rc -ne 0 ] && grep -q 'not a git repository: /nonexistent/zq' \"$err\"; then\n"
                 '  echo "fatal: .git file does not point to a valid repository: /nonexistent/zq" >&2\n'
                 'else\n'
                 '  cat "$err" >&2\n'
                 'fi\n'
                 'rm -f "$err"\n'
                 'exit $rc\n')
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim.parent}{os.pathsep}{os.environ['PATH']}")


@pytest.mark.parametrize("wording", GIT_WORDINGS)
def test_a_checkout_git_cannot_read_is_refused_not_taken_for_a_disposable_copy(released, wording, tmp_path,
                                                                             monkeypatch):
    """Without this a site whose git answers with an error (a refused directory, a damaged ``.git``) would
    read as a copy, and its differences would be printed and not enforced. Whichever guard refuses first,
    the export stops with exit 1, says why, takes no difference for unenforced and leaves the site as it was."""
    engine, site = released
    part(engine, S1, "qwen3-4b", 1, "logits", {**QWEN, 2: (0.61, 0.2)})
    damaged = site.parent / "damaged"
    (site / ".git").rename(damaged)
    _write(site / ".git", "gitdir: /nonexistent/zq")
    if wording != GIT_WORDINGS[0]:
        _reword_git(tmp_path, monkeypatch)
    before = files(site)
    with pytest.raises(pd.DispositionError, match="git cannot say whether"):
        pd.site_reference(site)
    proc = export(engine, site)
    assert proc.returncode == 1, proc.stderr + proc.stdout
    by_disposition_check = "cannot be compared with what the site publishes" in proc.stderr
    by_prune_guard = "cannot tell whether the site checkout hides renders" in proc.stderr
    assert by_disposition_check != by_prune_guard, proc.stderr          # exactly one guard speaks
    if wording != GIT_WORDINGS[0]:
        assert by_prune_guard, proc.stderr                              # the newer wording is not "no checkout"
    if by_disposition_check:
        assert "Nothing was written or pruned" in proc.stderr
    assert "not enforced" not in proc.stdout and files(site) == before


# ---------------------------------------------------------------- the backend label rule (decision D3)

def _labels(site: Path, model: str = "qwen3-4b") -> tuple[Any, Any]:
    payload = payload_of(site)
    return (payload["traced_by_model"][model].get("backend"),
            next(m for m in payload["models_meta"] if m["id"] == model)["graphs"])


def test_a_hosted_probe_in_the_first_stamp_beside_an_unread_logits_part_does_not_label_the_model_hosted(tmp_path):
    """The regression of docs/corrections/payload_summary_dedupe_20261110.md, section 4.4: the first stamp's
    qwen3-4b directory holds a hosted part (read) and a logits part the pin does not list (not read); every
    other row of the model is a logits row. Until 2026-11-11 the label came from that one directory and read
    "hosted", graphs true."""
    engine, site = base_engine(tmp_path / "engine", (S1, S2)), tmp_path / "site"
    part(engine, S1, "qwen3-4b", 1, "hosted", {1: (0.037, 0.058), 2: (0.218, 0.103)})
    part(engine, S1, "qwen3-4b", 3, "logits", {3: (0.3, 0.8)}, pinned=False)
    part(engine, S2, "qwen3-4b", 1, "logits", QWEN)
    proc = export(engine, site, f"{S1},{S2}")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _labels(site) == ("logits", False)
    assert _labels(site, "gemma-2-2b") == ("hosted", True)
    assert ("qwen3-4b: rows read from parts of more than one backend (hosted 2, logits 3); labelled logits, "
            "graphs false") in proc.stdout
    assert "logits part outside the pinned manifest 1" in proc.stdout
    payload = payload_of(site)
    # a label correction: every measured value is the part's own
    assert row(payload, B1, 1)["models"]["qwen3-4b"]["prob_clinical"] == 0.037
    assert row(payload, B1, 2)["models"]["qwen3-4b"]["language_penalty"] == round(0.103 - 0.218, 4)
    assert "qwen3-4b" not in row(payload, B1, 3)["models"]
    assert row(payload, B2, 3)["models"]["qwen3-4b"]["prob_patient"] == 0.3
    assert payload["traced"] == payload["traced_by_model"]["gemma-2-2b"]


def test_a_model_of_hosted_parts_only_and_one_of_logits_parts_only_keep_their_labels(tmp_path):
    engine, site = base_engine(tmp_path / "engine", (S1, S2)), tmp_path / "site"
    part(engine, S1, "qwen3-4b", 1, "hosted", QWEN)
    part(engine, S2, "qwen3-4b", 1, "hosted", QWEN)
    part(engine, S1, "qwen3-1.7b", 1, "logits", QWEN)
    part(engine, S2, "qwen3-1.7b", 1, "logits", QWEN)
    proc = export(engine, site, f"{S1},{S2}", "gemma-2-2b,qwen3-4b,qwen3-1.7b")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _labels(site, "gemma-2-2b") == ("hosted", True)
    assert _labels(site, "qwen3-4b") == ("hosted", True)
    assert _labels(site, "qwen3-1.7b") == ("logits", False)
    assert "more than one backend" not in proc.stdout
    assert payload_of(site)["traced_by_model"]["qwen3-4b"] == {"graph_model": "qwen3-4b", "mode": "2panel",
                                                               "backend": "hosted"}


def test_the_label_follows_the_exported_rows_within_one_directory_too(tmp_path):
    engine, site = base_engine(tmp_path / "engine"), tmp_path / "site"
    # the last part read states "hosted"; rows 2 and 3 are still logits rows
    part(engine, S1, "qwen3-4b", 1, "logits", QWEN)
    part(engine, S1, "qwen3-4b", 2, "hosted", {1: (0.5, 0.1)})
    assert export(engine, site).returncode == 0
    assert _labels(site) == ("logits", False)
    # a hosted probe alone: its two rows are all the model publishes, and they have graphs
    engine, site = base_engine(tmp_path / "engine2"), tmp_path / "site2"
    part(engine, S1, "qwen3-4b", 1, "hosted", {1: QWEN[1], 2: QWEN[2]})
    part(engine, S1, "qwen3-4b", 3, "logits", {3: QWEN[3]}, pinned=False)
    assert export(engine, site).returncode == 0
    assert _labels(site) == ("hosted", True)
    # the directory metadata says logits (the last part read) and no exported row is a logits row
    engine, site = base_engine(tmp_path / "engine3", base_rows=(1, 2)), tmp_path / "site3"
    part(engine, S1, "qwen3-4b", 1, "hosted", {1: QWEN[1], 2: QWEN[2]})
    part(engine, S1, "qwen3-4b", 3, "logits", {3: QWEN[3]})            # row 3 is not in the base ordering
    assert export(engine, site).returncode == 0
    assert _labels(site) == ("hosted", True)


# ---------------------------------------------------------------- the routine path names the refusal

def test_the_skill_and_the_standing_prompt_quote_the_exporters_refusal_and_say_what_a_cycle_does():
    """The Routine reaches the exporter through docs/routine_standing_prompt.md section 5 and the
    publish-site-data skill. Both name the refusal by the text the exporter prints, and both send the
    differences to decisions_pending and the cycle on to the catalogue-only chain."""
    refusal = "refusing: this export changes"
    assert refusal in EXPORTER.read_text(encoding="utf-8")
    skill = (ROOT / ".claude/skills/publish-site-data/SKILL.md").read_text(encoding="utf-8")
    prompt = (ROOT / "docs/routine_standing_prompt.md").read_text(encoding="utf-8")
    cycle = (ROOT / ".claude/skills/daily-ops-cycle/SKILL.md").read_text(encoding="utf-8")
    for name, text in (("skill", skill), ("standing prompt", prompt), ("cycle skill", cycle)):
        flat = " ".join(text.split())
        assert refusal in flat, name
        assert "decisions_pending" in flat and "REFUSED" in flat, name
        assert "atalogue-only" in flat, name
    assert pd.RECORD_REL in skill and pd.RECORD_REL in prompt
    assert "do not run steps 2, 3b and 4" in " ".join(skill.split())
    assert "Never write, change or remove a disposition" in skill
    assert "never write a disposition" in " ".join(prompt.split())
    # the step-1 text sits before the release steps, whose order tests/test_results_release.py pins
    assert skill.index("Published measurements (since 2026-11-11)") < skill.index("**2. Urgency collector.**")


# ---------------------------------------------------------------- site_reference

def test_site_reference_reads_disk_only_outside_a_git_checkout(tmp_path):
    assert pd.site_reference(tmp_path / "absent") == (None, False, f"{pd.PAYLOAD_REL} on disk")
    _write(tmp_path / "plain" / pd.PAYLOAD_REL, {"scenarios": []})
    data, enforced, where = pd.site_reference(tmp_path / "plain")
    assert json.loads(data) == {"scenarios": []} and enforced is False and where.endswith("on disk")
    nested = tmp_path / "repo" / "inner"                                 # inside a checkout, not its root
    _write(nested / pd.PAYLOAD_REL, {"scenarios": []})
    commit_all(tmp_path / "repo")
    assert pd.site_reference(nested)[1] is False and pd.site_reference(tmp_path / "repo")[1] is True


# ---------------------------------------------------------------- the committed record

def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        return [found for k, v in value.items() for found in _strings(v, f"{path}/{k}")]
    if isinstance(value, list):
        return [found for i, v in enumerate(value) for found in _strings(v, f"{path}/{i}")]
    return []


def test_the_committed_record_is_well_formed_closed_and_holds_no_token_or_prompt_text():
    record = load(RECORD)
    assert record["schema"] == pd.SCHEMA and record["dispositions"] == pd.DISPOSITIONS
    entries = pd.parse_record(RECORD.read_bytes(), source=pd.RECORD_REL).entries
    assert record["count"] == len(entries) == len({(pd.identity(e), json.dumps(e["candidate"], sort_keys=True))
                                                   for e in entries})
    allowed_text = {"scope", "batch", "model", "change", "disposition", "decided_by", "decision_ref",
                    "open_decision", "block", "field", "measurement_sha256", "note"}
    for entry in entries:
        assert pd.entry_problem(entry, lambda rel: (ROOT / rel).is_file()) is None, pd.identity(entry)
        assert set(entry) <= set(pd.ROW_KEYS) | set(pd.META_KEYS) | {"disposition", "decided_by", "decision_ref",
                                                                     "open_decision", "note"}
        for where, text in _strings(entry):
            key = where.rsplit("/", 1)[-1]
            if "/fields/" in where:
                assert text in pd.MEASURED_FIELDS, where
            elif key == "measurement_sha256":
                assert re.fullmatch(r"[0-9a-f]{64}", text), where
            elif "/values/" in where:
                assert key == "screening" and re.fullmatch(r"[a-z_]{1,40}", text), where
            else:
                assert key in allowed_text and re.fullmatch(r"[A-Za-z0-9_ .#/-]{1,120}", text), (where, text)
        if entry["scope"] == "row":
            for side in (entry["reference"], entry["candidate"]):
                assert side is None or set(side["values"]) == set(pd.text_free({}))
        if entry["disposition"] != pd.PENDING:
            assert entry["decided_by"] == "owner" and (ROOT / entry["decision_ref"].partition("#")[0]).is_file()
        assert entry.get("open_decision") in (None, *record["open_decisions"])


def test_the_seeded_entries_are_the_thirteen_rows_of_the_accounting_file_with_its_values():
    """ops/payload_reexport_accounting_20261110.json is the record of the regeneration the entries were seeded
    from. Both files are committed, so this comparison always runs. An entry seeded later is not in it."""
    accounting = load(ACCOUNTING)
    seeded = {(e["batch"], e["batch_index"], e["model"]): e for e in load(RECORD)["entries"]
              if e.get("open_decision") in ("D1", "D4")}
    rows = {(r["batch"], r["batch_index"], r["model"]): r for r in accounting["rows"]}
    assert set(seeded) == set(rows) and len(rows) == accounting["payload_diff"]["rows_touched"] == 13

    def without_join(block: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if block is None else {k: v for k, v in block.items() if k != "urgency"}

    for key, entry in seeded.items():
        recorded = rows[key]
        assert entry["reference"]["values"] == without_join(recorded["published"]), key
        assert (entry["candidate"] or {}).get("values") == without_join(recorded["regenerated"]), key
        if recorded["change"] == "model object removed":
            assert entry["change"] == "model_removed" and entry["open_decision"] == "D1"
        else:
            assert entry["change"] == "values_changed" and entry["open_decision"] == "D4"
            # the accounting lists every differing key; a value where the published row had none
            # (circuit_diff: the logits lane has no graph) is an addition, not a difference
            assert set(recorded["fields_differing"]) - set(entry["fields"]) <= {"circuit_diff"}
            assert set(entry["fields"]) <= set(recorded["fields_differing"])
    by_class = accounting["payload_diff"]["by_class"]
    assert sum(e["change"] == "model_removed" for e in seeded.values()) == by_class["row_object:removed"] == 11


def test_the_eleven_removals_are_the_legacy_rows_and_carry_the_same_measurement_hash():
    legacy = {(e["batch"], e["batch_index"], e["model"]): e for e in load(LEGACY)["entries"]}
    removals = {(e["batch"], e["batch_index"], e["model"]): e for e in load(RECORD)["entries"]
                if e.get("open_decision") == "D1"}
    assert set(removals) == set(legacy) and len(legacy) == 11
    for key, entry in removals.items():
        assert entry["reference"]["measurement_sha256"] == legacy[key]["payload_measurement_sha256"], key
        assert entry["reference"]["values"] == {k: v for k, v in legacy[key]["payload_row"].items()
                                                if k != "urgency"}, key


def _site_payload() -> dict[str, Any]:
    override = os.environ.get("PW_SITE_ROOT")
    site = Path(override) if override else ROOT.parent / "patientwords"
    if not (site / pd.PAYLOAD_REL).is_file():
        if override:
            pytest.fail(f"PW_SITE_ROOT={override} holds no {pd.PAYLOAD_REL}")
        pytest.skip(f"sibling checkout ../patientwords absent ({site}); set PW_SITE_ROOT to compare the record "
                    "with the published payload")
    return load(site / pd.PAYLOAD_REL)


def test_each_pending_entry_still_describes_the_published_payload_and_the_engine_part():
    """A pending entry whose reference is no longer what the site publishes is stale: the difference it
    recorded was published or withdrawn without the entry being decided."""
    payload = _site_payload()
    rows = {(s.get("batch"), s.get("batch_index")): s for s in payload["scenarios"]}
    pending = [e for e in load(RECORD)["entries"] if e["disposition"] == pd.PENDING and e["scope"] == "row"]
    for entry in pending:
        published_obj = (rows.get((entry["batch"], entry["batch_index"])) or {}).get("models", {}).get(entry["model"])
        assert published_obj is not None, pd.identity(entry)
        assert pd.measurement_sha256(published_obj) == entry["reference"]["measurement_sha256"], pd.identity(entry)
        assert pd.text_free(published_obj) == entry["reference"]["values"], pd.identity(entry)
        if entry["candidate"] is None:
            continue
        # the candidate's numbers are the engine part's own (the hosted part at this directory)
        directory = ROOT / "trace_out" / f"{entry['batch']}__{entry['model']}"
        if not directory.is_dir():
            pytest.skip(f"{directory} is not on disk (partial checkout)")
        results = [r for p in sorted(directory.glob("batch_summary.part_*.json"))
                   for r in load(p).get("results", []) if load(p).get("backend") == "hosted"
                   and r.get("index") == entry["batch_index"]]
        assert results, pd.identity(entry)
        values = entry["candidate"]["values"]
        assert (values["prob_clinical"], values["prob_patient"], values["language_penalty"]) == (
            results[-1]["probabilities"]["clinical"], results[-1]["probabilities"]["patient"],
            results[-1]["language_penalty"]), pd.identity(entry)
