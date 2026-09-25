"""Tests for scripts/export_petri_multiturn.py, the exporter behind the site's Multi-turn page.

SYNTHETIC input only. The design note's section 10.6 forbids computing or inspecting a register contrast on landed data
before the one-time final analysis, so every run directory and every section 10 artifact here is built by
scripts/petri_multiturn_synthetic.py: the seed file's scripted turns, placeholder replies, grades drawn from a seeded
generator over the values the judge's own planner allows, and an artifact computed from those rows. Nothing under
data/petri/runs is read.

The site contract the output is held to is tests/fixtures/petri_multiturn_site_contract.json: the key skeleton of the
site's own sample files (patientwords PR #9), so a key the page reads that the exporter drops, or a key the exporter
adds, fails here. Seed ids come from data/petri/multiturn_measures.json, never from this file.
"""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from scripts import export_petri_multiturn as ex
from scripts import petri_multiturn_synthetic as syn
from scripts import validate_frontend_contract as vfc
from scripts.petri_audit.framework import ADVICE_RUBRIC, OUTCOME_REGISTRY, SEED_FILE, load_json
from scripts.petri_audit.seeds import tool_result_for

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "tests" / "fixtures" / "petri_multiturn_site_contract.json").read_text("utf-8"))
SEEDS = {s["seed_id"]: s for s in load_json(SEED_FILE)["seeds"]}
RUBRIC = load_json(ADVICE_RUBRIC)
REGISTRY = load_json(OUTCOME_REGISTRY)
VOCAB = load_json(ex.VOCABULARY_FILE)
MECH = {mid: m["seeds"] for mid, m in VOCAB["mechanisms"].items()}
# one seed with a scripted tool and one with two speakers, in each scenario set (the second set's tool seed is the
# vocabulary's example seed, and carries declared term swaps)
ORIGINAL = [MECH["tool-clarify"][0], MECH["identity-register"][0]]
SECOND = [MECH["tool-clarify"][1], MECH["identity-register"][1]]
SETS = {"original": ORIGINAL, "second": SECOND}
FIRES = [syn.Fire("t1", "discovery", {"original": 1, "second": 1}),
         syn.Fire("t2", "prospective", {"original": 2, "second": 2})]
NO_SEAL: dict[str, str] = {}      # the sealed set is not the subject of most tests; one test gives its own

# the paths whose items are alternatives (an assistant or a tool message; a value or a not-applicable cell), and the
# keys the exporter adds there beyond the site's samples (both reported to the site)
ALTERNATIVES = {"$.conversations[].exchanges[].interim[]": {"fixture"},
                "$.conversations[].exchanges[].vals{}": {"superseded"}}


def skeleton(obj, path="$", out=None):
    """The same walk that produced the fixture: key lists per path, '*' for an open map, opaque paths skipped."""
    out = {} if out is None else out
    if path in CONTRACT["opaque"]:
        return out
    if isinstance(obj, dict):
        if path in CONTRACT["open_maps"]:
            out[path] = "*"
            for v in obj.values():
                skeleton(v, path + "{}", out)
        else:
            keys = out.setdefault(path, [])
            for k, v in obj.items():
                if k not in keys:
                    keys.append(k)
                skeleton(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for v in obj:
            skeleton(v, path + "[]", out)
    return out


def assert_site_keys(doc, which, *, sample):
    """The document carries exactly the site sample's keys at every path the site defines, and no other path."""
    site, ours = CONTRACT[which], skeleton(doc)
    assert set(ours) <= set(site), f"paths the site's samples do not have: {sorted(set(ours) - set(site))}"
    for path, keys in site.items():
        assert path in ours, f"{which}: the page reads {path}, which the export lacks"
        if keys == "*":
            assert ours[path] == "*", path
            continue
        want = set(keys) - (set() if sample or path != "$" else {"sample", "_note"})
        if path in ALTERNATIVES:
            assert set(ours[path]) <= want | ALTERNATIVES[path], (path, ours[path])
        else:
            assert set(ours[path]) == want, (path, ours[path], sorted(want))


def build(root: Path, **edits) -> syn.Campaign:
    return syn.build_campaign(root, seeds=SEEDS, sets=SETS, fires=FIRES, rubric=RUBRIC, registry=REGISTRY,
                              rng_seed=11, **edits)


def export(camp: syn.Campaign, tmp: Path, artifact: dict | None = None, name: str = "artifact.json", **kw):
    path = tmp / name
    path.write_text(json.dumps(artifact if artifact is not None else syn.build_artifact(camp)), encoding="utf-8")
    kw.setdefault("disclosure_log", tmp / "no_disclosure_log.jsonl")
    kw.setdefault("seal_registry", NO_SEAL)
    return ex.export(camp.run_dirs, path, **kw)


def refused(camp: syn.Campaign, tmp: Path, artifact: dict | None = None, **kw) -> str:
    with pytest.raises(ex.ExportRefusal) as info:
        export(camp, tmp, artifact, **kw)
    return str(info.value)


@pytest.fixture(scope="module")
def shared(tmp_path_factory):
    """One synthetic campaign, never edited, for the tests that vary only the artifact or the side inputs."""
    root = tmp_path_factory.mktemp("campaign")
    return build(root), root


def note_rows():
    """Section 10.2's table and 10.3's bullets, read from the design note by this test (not through the exporter)."""
    note = (ROOT / "docs" / "petri_wave2_design.md").read_text("utf-8")
    s2 = note[note.index("### 10.2 "):note.index("### 10.3 ")]
    lines = [ln for ln in s2.splitlines() if ln.startswith("|")]
    rows = {f"row{i}": [c.strip() for c in ln.strip("|").split("|")][3] for i, ln in enumerate(lines[2:], 1)}
    s3 = " ".join(note[note.index("### 10.3 "):note.index("### 10.4 ")].split())
    return rows, s3


# ------------------------------------------------------------------ the end-to-end export


def test_end_to_end_export_has_exactly_the_site_keys(tmp_path):
    camp = build(tmp_path / "c")
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    result = export(camp, tmp_path)
    written = ex.write_site(site, result.summary, result.conversations)
    assert [p.name for p in written] == ["petri_multiturn_summary.json", "petri_multiturn_conversations.json"]
    summary = json.loads(written[0].read_text("utf-8"))
    conversations = json.loads(written[1].read_text("utf-8"))
    assert_site_keys(summary, "summary", sample=False)
    assert_site_keys(conversations, "conversations", sample=False)
    assert "sample" not in summary and "sample" not in conversations

    # the triples, the partitions and the scenario means are keyed as the page reads them
    artifact = json.loads((tmp_path / "artifact.json").read_text("utf-8"))
    assert len(summary["triples"]) == len(artifact["triples"]) == 12      # 2 epochs x (1 + 2 speakers) x 2 sets
    assert {t["partition"] for t in summary["triples"]} == {"seen_before_plan", "prospective"}
    for mine, theirs in zip(summary["triples"], artifact["triples"]):
        assert mine["seed_id"] == theirs["seed_id"] and mine["epoch"] == theirs["campaign_epoch"]
        assert mine["scenario_id"] == SEEDS[theirs["seed_id"]]["scenario"]["id"]
        assert mine["eligible"] is theirs["contrasts"]["primary"]["enters"] is True
        assert mine["D"] == theirs["contrasts"]["primary"]["D"]
    gate = artifact["section_10_2"]["scenario_gate"]
    assert summary["scenario_means"] == {SEEDS[s]["scenario"]["id"]: m for s, m in gate["scenario_means"].items()}
    pst = artifact["section_10_2"]["primary_sign_test"]
    assert summary["primary"] == {"triples": pst["triples"], "negative": pst["negative"], "positive": pst["positive"],
                                  "tied": pst["tied"], "p_two_sided": pst["p"], "gate_p": gate["p"],
                                  "gate_passed": artifact["section_10_2"]["wording"]["gate_same_direction"]}
    assert summary["seed"] == artifact["bootstrap_seed"]
    assert summary["status"] == {"final": True, "clinician_review": "pending",
                                 "vendor_pack": {"version": None, "sent": None}}
    assert summary["provenance"] == {"runs": [r.stem for r in camp.runs], "analysis_commit": "c" * 40,
                                     "verify": "python -m scripts.petri_audit.cli verify-chain --data-dir "
                                               "data/petri/runs"}
    assert [r["seed_id"] for r in summary["repeats"]] == ORIGINAL + SECOND
    assert all(r["epochs"] == 2 for r in summary["repeats"])

    # every conversation of every triple, ten graded exchanges each, the seeds and the example
    assert len(conversations["conversations"]) == 2 * (3 + 6 + 3 + 6)
    assert all(len(c["exchanges"]) == 10 and all(e["reply_is_graded"] for e in c["exchanges"])
               for c in conversations["conversations"])
    assert [s["seed_id"] for s in conversations["seeds"]] == ORIGINAL + SECOND
    assert {s["set"] for s in conversations["seeds"]} == {"original", "second"}
    assert conversations["example"]["seed_id"] == VOCAB["example"]["seed_id"]
    assert [m["id"] for m in conversations["measures"]] == [m["id"] for m in VOCAB["measures"]]
    identity = {c["identity"] for c in conversations["conversations"] if c["seed_id"] == ORIGINAL[1]}
    assert len(identity) == 2 and None not in identity


def test_the_scripted_lookup_result_carries_fixture_true(shared, tmp_path):
    camp, _ = shared
    convs = export(camp, tmp_path).conversations["conversations"]
    tools = [(c, it) for c in convs for e in c["exchanges"] for it in e["interim"] if it["role"] == "tool"]
    tool_seeds = {c["seed_id"] for c, _ in tools}
    assert tool_seeds == {ORIGINAL[0], SECOND[0]}
    for c, item in tools:
        seed = SEEDS[c["seed_id"]]
        scripted, _, _ = tool_result_for(seed, seed["tools"]["results"][0]["tool"], {"query": syn.TOOL_QUERY})
        assert item == {"role": "tool", "text": scripted, "fixture": True}
    assert all(set(it) == {"role", "text"} for c in convs for e in c["exchanges"] for it in e["interim"]
               if it["role"] == "assistant")


def test_a_tool_result_that_is_not_the_scripted_text_is_refused(tmp_path):
    def tamper(stem, records):
        for t in records[0]["turns"]:
            if t["role"] == "tool":
                t["text"] = t["text"] + " (edited)"
        return records
    camp = build(tmp_path / "c", transcript_edit=tamper)
    assert "not the seed's scripted result" in refused(camp, tmp_path)


def test_a_triple_below_its_floor_is_not_eligible_and_keeps_its_descriptive_D(tmp_path):
    camp = build(tmp_path / "c", judgment_edit=syn.below_floor(1))
    artifact = syn.build_artifact(camp)
    out = export(camp, tmp_path, artifact).summary
    not_in = [t for t in artifact["triples"] if not t["contrasts"]["primary"]["enters"]]
    assert len(not_in) == 1 and len(not_in[0]["contrasts"]["primary"]["comparable_exchanges"]) == 7
    mine = out["triples"][artifact["triples"].index(not_in[0])]
    assert mine["eligible"] is False and isinstance(mine["D"], float)
    assert out["primary"]["triples"] == len(artifact["triples"]) - 1


def test_a_superseded_grade_is_flagged_and_kept(tmp_path):
    def old_prompt(stem, rows):
        r = next(r for r in rows if r["kind"] == "outcome" and r["key"] == "safety_netting_presence"
                 and r["final_in_exchange"] and r["value"] != "not_applicable")
        r["prompt_file_digest"] = "000000000000"
        return rows
    camp = build(tmp_path / "c", judgment_edit=old_prompt)
    convs = export(camp, tmp_path).conversations["conversations"]
    flagged = [e["vals"]["sn"] for c in convs for e in c["exchanges"] if "superseded" in e["vals"].get("sn", {})]
    assert len(flagged) == len(FIRES) and all(cell["superseded"] == "000000000000" and "v" in cell
                                              for cell in flagged)


# ------------------------------------------------------------------ refusals


def test_refuses_a_non_final_artifact(shared, tmp_path):
    camp, _ = shared
    assert "is not final" in refused(camp, tmp_path, syn.build_artifact(camp, final=False))


def test_refuses_a_truncated_artifact(shared, tmp_path):
    camp, _ = shared
    assert "administratively truncated" in refused(camp, tmp_path, syn.build_artifact(camp, truncated=True))


def test_refuses_an_artifact_run_from_uncommitted_inputs(shared, tmp_path):
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    artifact["identity"]["uncommitted_changes"]["script"] = [" M scripts/petri_w2_register_contrast.py"]
    assert "did not show committed" in refused(camp, tmp_path, artifact)


def test_refuses_runs_that_are_not_the_artifacts(shared, tmp_path):
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(ex.ExportRefusal, match="not the runs the section 10 artifact covers"):
        ex.export(camp.run_dirs[:1], path, seal_registry=NO_SEAL)
    changed = json.loads(json.dumps(artifact))
    changed["coverage"]["runs"][0]["judgments_sha256"] = "0" * 64
    assert "judgments.jsonl is not the file the section 10 artifact read" in refused(camp, tmp_path, changed)
    changed = json.loads(json.dumps(artifact))
    changed["coverage"]["runs"][1]["run_id"] = "another run"
    assert "is not the artifact's" in refused(camp, tmp_path, changed)


def test_refuses_a_missing_final_row(tmp_path):
    def drop(stem, rows):
        cid = rows[0]["conversation_id"]
        return [r for r in rows if not (r["conversation_id"] == cid and r["exchange_index"] == 4
                                        and r["final_in_exchange"] and r["key"] == "contextual")]
    camp = build(tmp_path / "c", judgment_edit=drop)
    assert "no final row for exchange 4: tier:contextual" in refused(camp, tmp_path)


def test_refuses_a_missing_rule_outcome(tmp_path):
    camp = build(tmp_path / "c", rule_edit=lambda stem, rules: rules[1:])
    assert "no rule outcome" in refused(camp, tmp_path)


@pytest.mark.parametrize("edit, says", [
    (lambda m: m["harness"].pop("environment_lock_sha256"), "environment_lock_sha256 is missing"),
    (lambda m: m["artifacts"].update(raw_eval_log_published=True), "raw_eval_log_published is True"),
    (lambda m: m["artifacts"].pop("raw_eval_log_custody"), "not bound with its custody"),
    (lambda m: m.pop("holdout"), "no holdout block"),
    (lambda m: m["execution"]["contract_checks"].update(holdout_seal={"status": "not_run"}), "holdout-seal"),
])
def test_refuses_missing_publication_conditions(tmp_path, edit, says):
    def change(stem, manifest):
        if stem.endswith("0001_1"):
            edit(manifest)
        return manifest
    camp = build(tmp_path / "c", manifest_edit=change)
    message = refused(camp, tmp_path)
    assert "publication conditions do not hold" in message and says in message


def test_refuses_a_missing_measure_mapping(shared, tmp_path):
    camp, _ = shared
    doc = json.loads(json.dumps(VOCAB))
    dropped = next(m for m in doc["measures"] if m["row"] == ["outcome", "tool_evidence_use"])
    doc["measures"].remove(dropped)
    path = tmp_path / "vocabulary.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    message = refused(camp, tmp_path, vocabulary_path=path)
    assert "outcome:tool_evidence_use" in message and "no measure in the page vocabulary" in message


def test_refuses_a_measure_that_disagrees_with_the_registry(shared, tmp_path):
    camp, _ = shared
    doc = json.loads(json.dumps(VOCAB))
    doc["measures"][2]["values"] = list(reversed(doc["measures"][2]["values"]))
    path = tmp_path / "vocabulary.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert "are not the registry's" in refused(camp, tmp_path, vocabulary_path=path)


def test_refuses_a_D_the_rows_do_not_reproduce(shared, tmp_path):
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    prim = artifact["triples"][0]["contrasts"]["primary"]
    prim["sum"] += 1
    assert "the rows give D" in refused(camp, tmp_path, artifact)


def test_scenario_means_are_the_checked_exact_means_never_the_unchecked_mirror(shared, tmp_path):
    """Regression (Codex review of 2026-09-24): only scenario_means_exact was checked, and the page was given the
    float mirror scenario_means, so a stale mirror entry was published and a missing one raised a KeyError."""
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    gate = artifact["section_10_2"]["scenario_gate"]
    sid = next(iter(gate["scenario_means"]))
    stale = json.loads(json.dumps(artifact))
    stale["section_10_2"]["scenario_gate"]["scenario_means"][sid] += 0.5
    assert "the artifact disagrees with itself" in refused(camp, tmp_path, stale)
    missing = json.loads(json.dumps(artifact))
    del missing["section_10_2"]["scenario_gate"]["scenario_means"][sid]
    assert "the artifact disagrees with itself" in refused(camp, tmp_path, missing)
    out = export(camp, tmp_path, artifact).summary["scenario_means"]
    assert out == {SEEDS[s]["scenario"]["id"]: float(Fraction(m)) for s, m in gate["scenario_means_exact"].items()}


def test_refuses_wording_that_differs_from_the_design_note(shared, tmp_path):
    camp, _ = shared
    doc = json.loads(ex.WORDING_FILE.read_text("utf-8"))
    doc["section_10_2"]["rows"][4]["text"] = doc["section_10_2"]["rows"][4]["text"].replace("did not", "did")
    path = tmp_path / "wording.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert "row5 differs from section 10.2's table" in refused(camp, tmp_path, wording_path=path)


def test_a_sealed_phrase_is_refused_by_label_only(shared, tmp_path):
    camp, _ = shared
    phrase = "[Synthetic reply to exchange 3"
    message = refused(camp, tmp_path, seal_registry={phrase: "sealed-label-7"})
    assert "sealed-label-7" in message and phrase not in message


# ------------------------------------------------------------------ the registered wording, carried verbatim


@pytest.mark.parametrize("row", ["row1", "row2", "row3", "row4/row1", "row4/row3", "row5"])
def test_headline_text_is_the_design_notes_row_verbatim(shared, tmp_path, row):
    camp, _ = shared
    rows, _ = note_rows()
    out = export(camp, tmp_path, syn.build_artifact(camp, wording_row=row)).summary
    assert out["headline"] == {"row_id": row, "text": rows[row.split("/")[0]]}


def test_style_sentence_is_the_design_notes_statement_verbatim(shared, tmp_path):
    camp, _ = shared
    _, s3 = note_rows()
    out = export(camp, tmp_path, syn.build_artifact(camp, statement="not_separated")).summary["style_sentence"]
    assert out["row_id"] == "not_separated" and f"**Paired difference not significant:** {out['text']}" in s3
    out = export(camp, tmp_path, syn.build_artifact(camp, statement="style_larger", also_lowered=True),
                 name="a2.json").summary["style_sentence"]
    assert out["row_id"] == "style_larger+vocabulary_also_lowered"
    assert f"style significant and negative:** {out['text']} - **Paired difference not significant:**" in s3


@pytest.mark.parametrize("kw, headline", [
    ({"wording_row": "not_computable", "selectable": False}, {"row_id": "not_computable", "text": None}),
    ({"wording_row": "no_prespecified_row", "selectable": False}, {"row_id": "no_prespecified_row", "text": None}),
    ({"wording_row": "row5", "selectable": False}, {"row_id": "not_selectable_as_registered:row5", "text": None}),
])
def test_unworded_and_unselectable_rows_are_carried_by_name(shared, tmp_path, kw, headline):
    camp, _ = shared
    assert export(camp, tmp_path, syn.build_artifact(camp, **kw)).summary["headline"] == headline


@pytest.mark.parametrize("kw, style", [
    ({"statement": "not_computable"}, {"row_id": "not_computable", "text": None}),
    ({"statement": "no_prespecified_statement"}, {"row_id": "no_prespecified_statement", "text": None}),
    ({"section_10_3_refused": True}, {"row_id": "refused", "text": None}),
])
def test_unworded_statements_are_carried_by_name(shared, tmp_path, kw, style):
    camp, _ = shared
    assert export(camp, tmp_path, syn.build_artifact(camp, **kw)).summary["style_sentence"] == style


def test_the_wording_file_is_the_design_notes(tmp_path):
    wording = ex.load_wording(ex.WORDING_FILE, ex.DESIGN_NOTE)
    rows, _ = note_rows()
    assert wording.rows == rows
    assert set(wording.statements) == {"style_larger", "not_separated"}


# ------------------------------------------------------------------ status, provenance, the diff


def test_vendor_pack_is_the_latest_petri_entry_for_anthropic(shared, tmp_path):
    camp, _ = shared
    log = tmp_path / "disclosure_log.jsonl"
    entries = [{"pack_version": "vadvice", "lane": "advice", "vendor": "anthropic", "sent_utc": "2026-08-01T00:00:00Z"},
               {"pack_version": "vpetri1", "lane": "petri", "vendor": "anthropic", "sent_utc": None},
               {"pack_version": "vother", "lane": "petri", "vendor": "another-vendor", "sent_utc": None},
               {"pack_version": "vpetri2", "lane": "petri", "vendor": "anthropic", "sent_utc": "2026-09-25T09:00:00Z"},
               {"pack_version": "vlater", "vendor": "anthropic", "sent_utc": None}]
    log.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    status = export(camp, tmp_path, disclosure_log=log).summary["status"]
    assert status["vendor_pack"] == {"version": "vpetri2", "sent": "2026-09-25T09:00:00Z"}
    log.write_text(json.dumps(entries[0]) + "\n", encoding="utf-8")
    assert export(camp, tmp_path, disclosure_log=log).summary["status"]["vendor_pack"] == {"version": None,
                                                                                          "sent": None}
    log.write_text(json.dumps(entries[1]) + "\nnot json\n", encoding="utf-8")
    assert "line 2 does not parse" in refused(camp, tmp_path, disclosure_log=log)


def test_clinician_review_is_pending_while_a_source_is_draft_and_never_inferred():
    assert ex.clinician_review({"advice rubric": "DRAFT pending review", "seed file": "reviewed"}) == (
        "pending", ["advice rubric"])
    with pytest.raises(ex.ExportRefusal, match="no file records a clinician review"):
        ex.clinician_review({"advice rubric": "reviewed", "seed file": None})


def test_diff_cells_names_every_changed_cell():
    old = {"primary": {"p_two_sided": 0.5, "gate_passed": False}, "triples": [{"D": 0.0}], "gone": 1}
    new = {"primary": {"p_two_sided": 0.04, "gate_passed": None}, "triples": [{"D": 0.0}, {"D": -1.0}], "new": 2}
    assert ex.diff_cells(old, new) == ["- $.gone: 1", "~ $.primary.p_two_sided: 0.5 -> 0.04",
                                       "~ $.primary.gate_passed: false -> null", "+ $.triples[1]: {\"D\": -1.0}",
                                       "+ $.new: 2"]
    assert ex.diff_cells(new, json.loads(json.dumps(new))) == []


def test_cli_writes_both_files_and_prints_the_previous_diff(shared, tmp_path, capsys):
    camp, _ = shared
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(syn.build_artifact(camp)), encoding="utf-8")
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    args = ["--analysis", str(artifact), "--site", str(site), "--disclosure-log", str(tmp_path / "none.jsonl"),
            *map(str, camp.run_dirs)]
    assert ex.main(args) == 0
    first = json.loads((site / "data" / "petri_multiturn_summary.json").read_text("utf-8"))
    json.loads((site / "data" / "petri_multiturn_conversations.json").read_text("utf-8"))
    previous = tmp_path / "previous.json"
    first["primary"]["p_two_sided"] = 0.123
    first["triples"][2]["D"] = 9.0
    previous.write_text(json.dumps(first), encoding="utf-8")
    capsys.readouterr()
    assert ex.main([*args, "--previous", str(previous), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "--previous" in out and "2 changed cell(s)" in out
    assert "~ $.primary.p_two_sided: 0.123 -> " in out and "~ $.triples[2].D: 9.0 -> " in out
    assert "dry run: nothing written" in out


def test_cli_refuses_with_exit_2_and_writes_nothing(shared, tmp_path, capsys):
    camp, _ = shared
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(syn.build_artifact(camp, final=False)), encoding="utf-8")
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    assert ex.main(["--analysis", str(artifact), "--site", str(site), *map(str, camp.run_dirs)]) == 2
    assert "refused:" in capsys.readouterr().err
    assert list((site / "data").iterdir()) == []


# ------------------------------------------------------------------ the sample fixtures and the site's gate


def test_write_samples_matches_the_site_samples(tmp_path):
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    assert ex.main(["--write-samples", "--site", str(site)]) == 0
    summary = json.loads((site / "data" / "petri_multiturn_summary.sample.json").read_text("utf-8"))
    conversations = json.loads((site / "data" / "petri_multiturn_conversations.sample.json").read_text("utf-8"))
    assert_site_keys(summary, "summary", sample=True)
    assert_site_keys(conversations, "conversations", sample=True)
    seed = VOCAB["samples"]["rng_seed"]
    assert summary["sample"] is conversations["sample"] is True
    assert summary["seed"] == conversations["seed"] == seed
    assert summary["_note"].startswith("SYNTHETIC SAMPLE") and conversations["_note"].startswith("SYNTHETIC SAMPLE")
    assert summary["headline"]["row_id"] == summary["style_sentence"]["row_id"] == "SAMPLE"
    assert summary["status"]["final"] is False and summary["provenance"]["analysis_commit"] == "SAMPLE"
    assert [s["seed_id"] for s in conversations["seeds"]] == VOCAB["samples"]["seed_ids"]
    texts = [x for c in conversations["conversations"] for e in c["exchanges"]
             for x in (e["user"], e["reply"], *(i["text"] for i in e["interim"]))]
    assert texts and all(x.startswith("[Sample ") for x in texts)
    assert len(summary["triples"]) == len(VOCAB["samples"]["seed_ids"]) * VOCAB["samples"]["epochs"]


def test_exported_and_sample_files_pass_the_contract_validator(shared, tmp_path):
    camp, _ = shared
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    result = export(camp, tmp_path)
    ex.write_site(site, result.summary, result.conversations)
    ex.write_site(site, *ex.sample_export(seal_registry=NO_SEAL), sample=True)
    rep = vfc.Report()
    vfc.check_owner_run(rep, site)
    assert rep.errors == [] and rep.warnings == [] and rep.notes == []
