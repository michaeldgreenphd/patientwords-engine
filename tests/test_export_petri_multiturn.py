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

import dataclasses
import json
import os
import shutil
import subprocess
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
# the eight plan seeds (each mechanism's original-set and second-set seed) over three fires, 30 triples: 10.2's gate
# can reject only with at least six scenarios (its smallest p is 2/2^k), and 10.3's Holm family needs more non-tied
# second-set triples than the four-seed campaign has, so the rows and statements that need them use this campaign
FULL_SETS = {"original": [m[0] for m in MECH.values()], "second": [m[1] for m in MECH.values()]}
FULL_FIRES = [syn.Fire("f1", "discovery", {"original": 1, "second": 1}),
              syn.Fire("f2", "prospective", {"original": 2, "second": 2}),
              syn.Fire("f3", "prospective", {"original": 3, "second": 3})]
# a sealed set of one placeholder phrase no synthetic text contains, so the export's seal scan runs and passes (an
# empty set scans nothing and is refused); the sealed phrases themselves are never the subject here
SEAL = {"zq sealed placeholder phrase zq": "pairs_T#1"}

# the paths whose items are alternatives (an assistant or a tool message; a value or a not-applicable cell), and the
# keys the exporter adds there beyond the site's samples (both reported to the site)
ALTERNATIVES = {"$.conversations[].exchanges[].interim[]": {"fixture"},
                "$.conversations[].exchanges[].vals{}": {"superseded"}}
# keys every document carries beyond the site's samples at patientwords PR #9's fixture commit, reported to the site
# (Codex review of 2026-09-24: the exporter commit is recorded in the provenance; Codex review of PR #39, 2026-09-25:
# so is the sha256 of the section 10 artifact, which binds the page to the analysis its cited pack was built from)
ADDED = {"$.provenance": {"exporter_commit", "analysis_sha256"}}


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
        want = (set(keys) | ADDED.get(path, set())) - (set() if sample or path != "$" else {"sample", "_note"})
        if path in ALTERNATIVES:
            assert set(ours[path]) <= want | ALTERNATIVES[path], (path, ours[path])
        else:
            assert set(ours[path]) == want, (path, ours[path], sorted(want))


def build(root: Path, **edits) -> syn.Campaign:
    return syn.build_campaign(root, seeds=SEEDS, sets=SETS, fires=FIRES, rubric=RUBRIC, registry=REGISTRY,
                              rng_seed=11, **edits)


def designed(root: Path, design: syn.Design, *, full: bool = True, **edits) -> syn.Campaign:
    """A campaign whose final response-only tier grades the design fixes: the eight-seed campaign, or (full=False)
    the four-seed one, whose gate cannot reject."""
    sets, fires = (FULL_SETS, FULL_FIRES) if full else (SETS, FIRES)
    return syn.build_campaign(root, seeds=SEEDS, sets=sets, fires=fires, rubric=RUBRIC, registry=REGISTRY,
                              rng_seed=11, design=design, **edits)


def ranks(colloquial: int, careful_lay: int, clinical: int) -> syn.Design:
    """A design giving each wording one rank at every exchange."""
    by_register = {ex.COLLOQUIAL: colloquial, ex.CAREFUL_LAY: careful_lay, ex.CLINICAL: clinical}
    return lambda cell: by_register[cell.register]


def shift(offset) -> syn.Design:
    """A design: careful-lay and clinical grades rank 1, the colloquial grade 1 + offset(cell), so a triple's
    D(colloquial, clinical) is the mean of its offsets."""
    return lambda cell: 1 + offset(cell) if cell.register == ex.COLLOQUIAL else 1


def first_speaker(seed_id: str):
    return syn.layout(SEEDS[seed_id])[0][0]


def export(camp: syn.Campaign, tmp: Path, artifact: dict | None = None, name: str = "artifact.json", **kw):
    path = tmp / name
    path.write_text(json.dumps(artifact if artifact is not None else syn.build_artifact(camp)), encoding="utf-8")
    kw.setdefault("disclosure_log", tmp / "no_disclosure_log.jsonl")
    kw.setdefault("seal_registry", SEAL)
    kw.setdefault("checkout", ex.synthetic_checkout(camp.root))
    kw.setdefault("plan_path", camp.plan_path)
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
    assert summary["provenance"] == {"runs": [r.stem for r in camp.runs], "analysis_commit": syn.ANALYSIS_COMMIT,
                                     "analysis_sha256": ex.sha256_file(tmp_path / "artifact.json"),
                                     "exporter_commit": ex.SYNTHETIC_COMMIT,
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


def test_rule_outcomes_keep_the_lanes_query_text_list_in_exports_and_samples(shared, tmp_path):
    """Regression (Codex review of 2026-09-24): the lane writes query_text as a list of every call's arguments
    (scripts/petri_audit/rules.py), but the synthetic runs carried one string and the samples replaced it with one
    string, so the page was built against a type the real files never carry."""
    camp, _ = shared
    convs = export(camp, tmp_path).conversations["conversations"]
    called = [c["rule"]["query_text"] for c in convs if c["rule"]["tool_invoked"]]
    assert called and all(q == [json.dumps({"query": syn.TOOL_QUERY})] for q in called)
    assert all(c["rule"]["query_text"] is None for c in convs if not c["rule"]["tool_invoked"])
    _, sample = ex.sample_export(seal_registry=SEAL)
    queries = [c["rule"]["query_text"] for c in sample["conversations"]]
    listed = [q for q in queries if q is not None]
    assert listed and all(q == ["[Sample query text 1: placeholder.]"] for q in listed)


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


def test_refuses_a_self_consistent_artifact_over_a_subset_of_the_registered_triples(shared, tmp_path):
    """Regression (Codex review of 2026-09-25): the exporter checked only the triples the artifact listed, so an
    artifact computed over part of the campaign (an epoch or a scenario dropped, every listed triple landed and its
    counts and tests consistent with them) was exported with altered counts and p-values. The plan fixes the set."""
    camp, _ = shared
    first_fire = dataclasses.replace(camp, runs=camp.runs[:1])
    msg = refused(camp, tmp_path, syn.build_artifact(first_fire))
    assert "triples are not the registered final set of" in msg and "missing " in msg and "(t2)" in msg
    one_set = dataclasses.replace(camp, sets={**camp.sets, "second": []})
    msg = refused(camp, tmp_path, syn.build_artifact(one_set))
    assert "triples are not the registered final set of" in msg and SECOND[0] in msg
    doubled = syn.build_artifact(camp)
    doubled["triples"] = doubled["triples"][:-1] + doubled["triples"][:1]
    msg = refused(camp, tmp_path, doubled)
    assert "not registered, or listed twice: " + doubled["triples"][0]["seed_id"] in msg


def test_refuses_a_plan_the_analysis_did_not_read_or_that_contradicts_itself(shared, tmp_path):
    camp, _ = shared
    plan = load_json(camp.plan_path)
    other = tmp_path / "plan.json"
    other.write_text(json.dumps({**plan, "note": "edited"}), encoding="utf-8")
    assert "the registered triple set is read from the plan the analysis read" in refused(camp, tmp_path,
                                                                                         plan_path=other)
    other.write_text(json.dumps({**plan, "final_triples": plan["final_triples"] + 1}), encoding="utf-8")
    artifact = syn.build_artifact(camp)
    artifact["coverage"]["plan"]["sha256"] = ex.sha256_file(other)
    msg = refused(camp, tmp_path, artifact, plan_path=other)
    assert f"triples {plan['partition_triples']}, not the {plan['final_triples'] + 1}" in msg
    # 10.3's set, which the recomputed statement reads, must be one of the plan's scenario sets
    other.write_text(json.dumps({**plan, "decomposition_set": "third"}), encoding="utf-8")
    artifact["coverage"]["plan"]["sha256"] = ex.sha256_file(other)
    msg = refused(camp, tmp_path, artifact, plan_path=other)
    assert "decomposition_set 'third' is not one of its scenario sets ['original', 'second']" in msg


def _stale(artifact: dict, where: str, value) -> dict:
    node = artifact["section_10_2"]
    *parents, leaf = where.split(".")
    for part in parents:
        node = node[part]
    node[leaf] = value
    return artifact


@pytest.mark.parametrize("where,value", [
    ("primary_sign_test.p", 0.5), ("primary_sign_test.non_tied", 99), ("primary_sign_test.direction", "flipped"),
    ("primary_sign_test.alpha", 0.1), ("scenario_gate.p", 0.5), ("scenario_gate.p_exact", "1/2"),
    ("scenario_gate.scenarios", 99), ("scenario_gate.direction", "flipped"), ("scenario_gate.significant", "flipped"),
    ("wording.gate_same_direction", "flipped"),
])
def test_refuses_published_test_fields_the_entering_triples_do_not_give(shared, tmp_path, where, value):
    """Regression (Codex review of 2026-09-25): the p-values, direction, non_tied and scenario count were published
    from the artifact unchecked, while only the counts and exact means were checked, so a stale field reached the page
    (and the direction drove the 'does it repeat' counts). Each is recomputed and must equal the artifact's."""
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    if value == "flipped":
        node = artifact["section_10_2"][where.split(".")[0]]
        leaf = where.split(".")[1]
        value = (not node[leaf]) if isinstance(node[leaf], bool) else {"negative": "positive"}.get(node[leaf],
                                                                                                    "negative")
    msg = refused(camp, tmp_path, _stale(artifact, where, value))
    assert ("the primary sign test records (non_tied, p, direction, alpha)" in msg
            or "the scenario gate records (scenarios, p, p_exact, direction, significant, alpha" in msg), msg


def test_published_test_fields_are_the_recomputed_values(shared, tmp_path):
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    s = export(camp, tmp_path, artifact).summary
    pst, gate = artifact["section_10_2"]["primary_sign_test"], artifact["section_10_2"]["scenario_gate"]
    assert s["primary"]["p_two_sided"] == ex.exact_sign_test_p(min(pst["negative"], pst["positive"]),
                                                               pst["negative"] + pst["positive"])
    assert s["primary"]["gate_p"] == float(Fraction(gate["p_exact"]))


@pytest.mark.parametrize("breakage", ["no chain file", "a run left out of the chain", "a malformed line",
                                      "a manifest changed after sealing"])
def test_refuses_runs_the_verify_chain_command_would_not_examine(tmp_path, breakage):
    """Regression (Codex review of 2026-09-25): the exact-parent check did not show that the printed command verifies
    the exported runs. verify_chain succeeds with no chain file and checks only the manifests the chain names, so a run
    under the right directory but outside the chain was exported. The chain must exist, verify and name every run."""
    camp = build(tmp_path / "c")
    chain = camp.run_dirs[0].parent / ex.CHAIN_FILE
    lines = chain.read_text().splitlines()
    artifact = syn.build_artifact(camp)
    if breakage == "no chain file":
        chain.unlink()
        expected = "has no manifests.chain"
    elif breakage == "a run left out of the chain":
        chain.write_text("\n".join(lines[:-1]) + "\n")
        expected = f"runs ['{camp.runs[-1].stem}'] are not in"
    elif breakage == "a malformed line":
        chain.write_text("\n".join(lines) + "\ngarbage\n")
        expected = "cannot be read (ValueError"
    else:
        man = camp.run_dirs[0] / "manifest.json"
        doc = json.loads(man.read_text())
        doc["created_utc"] = "2026-09-30T00:00:00Z"
        man.write_text(json.dumps(doc, indent=1) + "\n")
        artifact["coverage"]["runs"][0]["manifest_sha256"] = ex.sha256_file(man)
        expected = "does not verify: line 1"
    assert expected in refused(camp, tmp_path, artifact)


def test_refuses_runs_that_are_not_the_artifacts(shared, tmp_path):
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(ex.ExportRefusal, match="not the runs the section 10 artifact covers"):
        ex.export(camp.run_dirs[:1], path, seal_registry=SEAL, checkout=ex.synthetic_checkout(camp.root),
                  plan_path=camp.plan_path)
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


def test_refuses_an_export_the_seal_scan_did_not_run_on(shared, tmp_path):
    """Regression (Codex review of 2026-09-25): only a failing scan was refused, so an empty sealed set, which scans
    nothing and reports not_run, let the export through."""
    camp, _ = shared
    msg = refused(camp, tmp_path, seal_registry={})
    assert "the holdout-seal scan of the export is 'not_run', not 'pass'" in msg


def test_refuses_eligibility_the_rows_do_not_give(tmp_path):
    """Regression (Codex review of 2026-09-25): comparable_exchanges and enters were taken from the artifact, so an
    analysis run over another window or floor, every statistic consistent with it, was exported. Each triple's
    comparable exchanges are recomputed over 10.1's window, enters against its floor, and the artifact's coverage must
    name that window and floor."""
    camp = build(tmp_path / "c", judgment_edit=syn.below_floor(1))
    # a floor of 7 lets in the triple 10.1 leaves out, with counts, tests and the row consistent with it
    low = syn.build_artifact(camp, floor=7)
    assert "(window, floor) ('exchanges 1-10', 7), not 10.1's ('exchanges 1-10', 8)" in refused(camp, tmp_path, low)
    for head in low["coverage"]["contrasts"].values():
        head["floor"] = 8
    msg = refused(camp, tmp_path, low)
    assert "the artifact records enters True, and its 7 comparable exchanges against 10.1's floor of 8 give False" in msg
    # a window of exchanges 1-9: every triple's D over nine exchanges
    short = syn.build_artifact(camp, window=range(1, 10))
    assert "(window, floor) ('exchanges 1-9', 8)" in refused(camp, tmp_path, short)
    for head in short["coverage"]["contrasts"].values():
        head["window"] = "exchanges 1-10"
    assert "comparable; the rows give [4, 5, 6, 7, 8, 9, 10]" in refused(camp, tmp_path, short)


def test_refuses_a_triple_whose_run_records_another_fires_nonce(tmp_path):
    """Regression (Codex review of 2026-09-25): a triple's conversations were read from the run the artifact named
    without checking that the run is the triple's fire."""
    def other_fire(stem, manifest):
        if stem == syn.run_stem(2):
            manifest["spend"]["journal_nonce"] = "t1"
        return manifest
    camp = build(tmp_path / "c", manifest_edit=other_fire)
    assert "records journal nonce 't1' (spend.journal_nonce), not the triple's 't2'" in refused(camp, tmp_path)


def test_refuses_an_analysis_commit_the_checkout_does_not_hold(shared, tmp_path):
    """Regression (Codex review of 2026-09-25): identity.commit was only format-checked. synthetic_checkout holds one
    commit, the synthetic artifact's; any other well-formed id is refused."""
    camp, _ = shared
    msg = refused(camp, tmp_path, syn.build_artifact(camp, commit="d" * 40))
    assert f"analysis commit {'d' * 40} is not a commit in this repository" in msg


def test_refuses_a_rule_outcome_the_transcript_does_not_give(tmp_path):
    """Regression (Codex review of 2026-09-25): the stored rule outcomes were published verbatim. They are recomputed
    with rules.rule_outcomes from the bound transcript and the seed, and a stored value that differs is refused."""
    def tamper(stem, rules):
        if stem == syn.run_stem(1):
            rules[0]["outcomes"]["tool_calls_total"] += 1
        return rules
    camp = build(tmp_path / "c", rule_edit=tamper)
    msg = refused(camp, tmp_path)
    assert "is not what scripts/petri_audit/rules.py" in msg and "they differ in ['tool_calls_total']" in msg


# ------------------------------------------------------------------ the campaign's models, and transcripts bound to their run

MODELS = VOCAB["campaign_models"]
OTHER_TARGET, OTHER_SERVED, OTHER_JUDGE = "anthropic/another-model", "another-model-snapshot", "another-judge"


def _in_run(k: int, edit):
    """An edit hook applied to the k-th run only."""
    def hook(stem, doc):
        if stem == syn.run_stem(k):
            edit(doc)
        return doc
    return hook


def _first_judgment(judgments):
    judgments[0]["judge_model"] = OTHER_JUDGE


def _first_source(field, value):
    def edit(records):
        records[0]["source"][field] = value
    return edit


@pytest.mark.parametrize("hook, edit, says", [
    ("manifest_edit", lambda m: m["models"]["target"].update(inspect_name=OTHER_TARGET),
     f"its target (models.target.inspect_name) is '{OTHER_TARGET}', not a registered target {MODELS['target']}"),
    ("manifest_edit", lambda m: m["models"]["target"]["served_model_strings"].append(OTHER_SERVED),
     f"the provider served the target as ['{OTHER_SERVED}'] (models.target.served_model_strings), not a registered"),
    ("manifest_edit", lambda m: m["models"]["target"].update(served_model_strings=[]),
     "models.target.served_model_strings is [], not the model strings the provider returned"),
    ("manifest_edit", lambda m: m.pop("models"), "the manifest records no models.target"),
    # Antigravity review of 2026-09-25: the page states the target was sampled at temperature 1
    ("manifest_edit", lambda m: m["models"]["target"]["config"].update(temperature=0.7),
     "its target was sampled at temperature 0.7 (models.target.config.temperature), not the registered 1.0"),
    ("manifest_edit", lambda m: m["models"]["target"].update(config={}),
     "its target was sampled at temperature None (models.target.config.temperature), not the registered 1.0"),
    # Codex, PR #43: the configured temperature is what was requested; the adapter's contract check says whether the
    # raw requests carried it
    ("manifest_edit", lambda m: m["execution"]["contract_checks"]["generation_config_pinned"].update(status="fail"),
     "its generation_config_pinned contract check is 'fail', not pass"),
    ("manifest_edit", lambda m: m["execution"]["contract_checks"].pop("generation_config_pinned"),
     "its generation_config_pinned contract check is None, not pass"),
    ("manifest_edit", lambda m: m["artifacts"]["judge_of_record"].update(judge_model=OTHER_JUDGE),
     f"its judge of record (artifacts.judge_of_record.judge_model) is '{OTHER_JUDGE}', not a registered judge"),
    ("judgment_edit", _first_judgment,
     f"1 judgment(s) record judge_model '{OTHER_JUDGE}', not a registered judge {MODELS['judge']}"),
    ("transcript_edit", _first_source("model", OTHER_TARGET),
     f"source.model '{OTHER_TARGET}' is not a registered target {MODELS['target']}"),
    ("transcript_edit", _first_source("model_version", OTHER_SERVED),
     f"source.model_version '{OTHER_SERVED}' is not a registered model string {MODELS['target_served']}"),
])
def test_refuses_a_run_of_another_target_or_judge(tmp_path, hook, edit, says):
    """Regression (Codex review of 2026-09-25): the exporter never read which models produced the data, so a
    registered fire run on another target, or graded by another judge, was published under the page's text, which
    names the target and says the same model graded it. The manifest's target and served model strings, its judge of
    record, every judgment's judge_model and every transcript's source must be the campaign's registered ones
    (data/petri/multiturn_measures.json campaign_models), and the ones that are not are named."""
    camp = build(tmp_path / "c", **{hook: _in_run(2, edit)})
    msg = refused(camp, tmp_path)
    assert syn.run_stem(2) in msg and says in msg, msg


def test_a_transcript_without_a_model_version_is_read(tmp_path):
    """The control for the test above: the adapter records no source.model_version when the provider served more than
    one string in the run (the manifest's served_model_strings, all registered, then name them), and that is read."""
    camp = build(tmp_path / "c", transcript_edit=_in_run(2, _first_source("model_version", None)))
    assert export(camp, tmp_path).summary["provenance"]["runs"] == [r.stem for r in camp.runs]


def test_a_vocabulary_without_well_formed_campaign_models_is_refused(shared, tmp_path):
    """The registered models are read from the page vocabulary, and a vocabulary without them, or with a list that is
    missing, empty or repeats a model, is refused by name (never read as 'any model')."""
    camp, _ = shared
    for change, says in ((lambda d: d.pop("campaign_models"), "campaign_models must be {target, target_served, judge}"),
                         (lambda d: d["campaign_models"].update(judge=[]), "campaign_models.judge must be a non-empty"),
                         (lambda d: d["campaign_models"].update(target=["a", "a"]), "campaign_models.target must be"),
                         (lambda d: d["campaign_models"].pop("target_served"), "campaign_models.target_served must"),
                         (lambda d: d["campaign_models"].pop("target_temperature"),
                          "campaign_models.target_temperature must be the finite number the page states"),
                         (lambda d: d["campaign_models"].update(target_temperature="1"),
                          "campaign_models.target_temperature must be the finite number the page states"),
                         # Codex, PR #43: Python's json reads Infinity and NaN as floats
                         (lambda d: d["campaign_models"].update(target_temperature=float("inf")),
                          "campaign_models.target_temperature must be the finite number the page states"),
                         (lambda d: d["campaign_models"].update(target_temperature=float("nan")),
                          "campaign_models.target_temperature must be the finite number the page states")):
        doc = json.loads(json.dumps(VOCAB))
        change(doc)
        path = tmp_path / "vocabulary.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert says in refused(camp, tmp_path, vocabulary_path=path)


def test_the_samples_are_built_from_the_vocabularys_registered_models(tmp_path):
    """The sample path has no exemption from the model check: the SYNTHETIC campaign records the vocabulary's
    registered models, so a vocabulary registering others still writes samples, and a campaign recording models the
    vocabulary does not register is refused like a landed run."""
    doc = json.loads(json.dumps(VOCAB))
    doc["campaign_models"] = {"target": [OTHER_TARGET], "target_served": [OTHER_SERVED], "judge": [OTHER_JUDGE],
                              "target_temperature": 1.0}
    path = tmp_path / "vocabulary.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert ex.sample_export(vocabulary_path=path, seal_registry=SEAL) == ex.sample_export(seal_registry=SEAL)
    camp = build(tmp_path / "c", models=doc["campaign_models"])
    assert f"its target (models.target.inspect_name) is '{OTHER_TARGET}'" in refused(camp, tmp_path)


@pytest.mark.parametrize("case, says", [
    ("another run's identity", "provenance.run_manifest names another manifest identity"),
    ("no binding", "provenance.run_manifest names no manifest identity"),
    ("no provenance", "provenance.run_manifest names no manifest identity"),
])
def test_refuses_a_transcript_not_bound_to_its_runs_manifest(tmp_path, case, says):
    """Regression (Codex review of 2026-09-25): load_run read every transcript record without checking that it is
    bound to its run. Each record's provenance.run_manifest.sha256 must be the manifest's identity digest, the pairing
    check scripts/petri_audit/summary.py makes: a record of another run (here, one naming the first run's identity in
    the second run's file) or one with no binding is refused."""
    first: list[str] = []

    def edit(stem, records):
        first.append(records[0]["provenance"]["run_manifest"]["sha256"])
        if stem == syn.run_stem(2):
            if case == "another run's identity":
                records[0]["provenance"]["run_manifest"]["sha256"] = first[0]
            elif case == "no binding":
                records[0]["provenance"]["run_manifest"] = None
            else:
                del records[0]["provenance"]
        return records
    camp = build(tmp_path / "c", transcript_edit=edit)
    assert first[0] != first[1]
    msg = refused(camp, tmp_path)
    assert f"run {syn.run_stem(2)}: 1 transcript record(s) are not records of this run" in msg and says in msg, msg
    if case == "another run's identity":
        assert f"({first[0][:12]})" in msg


def _first_record(change):
    def edit(records):
        change(records[0])
    return edit


def _tool_turn(record):
    return next(t for t in record["turns"] if t["role"] == "tool")


def _calling_turn(record):
    return next(t for t in record["turns"] if t.get("tool_calls"))


@pytest.mark.parametrize("change, says", [
    (lambda r: r["turns"][0].pop("role"), "turn #1: role None is not one of ['user', 'assistant', 'system', 'tool']"),
    (lambda r: r["turns"][0].update(text=None), "turn #1: text is not a string"),
    (lambda r: r["turns"][1].update(turn_id="2"), "turn #2: turn_id '2' is not an integer"),
    (lambda r: r["turns"][1].update(turn_id=1), "turn ids repeat: [1]"),
    (lambda r: r["turns"][0].update(tool_calls=[]), "turn #1: tool_calls are not an assistant turn's list"),
    (lambda r: _calling_turn(r)["tool_calls"][0].pop("name"), "tool_calls are not an assistant turn's list"),
    (lambda r: _calling_turn(r)["tool_calls"][0].update(arguments=["q"]), "tool_calls are not an assistant turn's"),
    (lambda r: _tool_turn(r).update(tool_call_id="call_elsewhere"), "names no tool call in this record"),
    (lambda r: r.update(turns=[]), "no turns"),
    (lambda r: r.pop("source"), "no source block"),
])
def test_refuses_a_transcript_record_the_exporter_cannot_read(tmp_path, change, says):
    """Regression (Codex review of 2026-09-25): a transcript record's shape was never checked, so a turn without a
    role or text, a repeated turn id or a malformed tool call raised a KeyError or was misread. Each record is checked
    as far as the exporter and rules.rule_outcomes read it, and the problem is named."""
    camp = build(tmp_path / "c", transcript_edit=_in_run(1, _first_record(change)))
    msg = refused(camp, tmp_path)
    assert f"run {syn.run_stem(1)}: 1 transcript record(s) are not records of this run" in msg and says in msg, msg


def test_the_manifest_identity_must_be_the_digest_of_its_body(shared):
    """The identity the records are held to is the manifest's own: chain.identity_sha256 recorded, and equal to the
    identity digest of the manifest body, else refused (a record bound to a stale identity is bound to no manifest)."""
    camp, _ = shared
    manifest = json.loads((camp.run_dirs[0] / "manifest.json").read_text("utf-8"))
    assert ex.manifest_identity(manifest, "r") == manifest["chain"]["identity_sha256"]
    stale = json.loads(json.dumps(manifest))
    stale["spend"]["journal_nonce"] = "edited"
    with pytest.raises(ex.ExportRefusal, match="is not the identity digest of the manifest body"):
        ex.manifest_identity(stale, "r")
    for value in (None, "0" * 12):
        stale["chain"]["identity_sha256"] = value
        with pytest.raises(ex.ExportRefusal, match="records no identity digest"):
            ex.manifest_identity(stale, "r")


# ------------------------------------------------------------------ the registered wording, carried verbatim


def _one_positive_triple_per_scenario(cell) -> int:
    """Colloquial offsets for no_prespecified_row: in every scenario the first fire's first-speaker triple has D = +1
    and every other triple D = -1/10 (one exchange lower), so 22 of 30 triples are negative (sign test p = 0.016) while
    all eight scenario means are positive (gate p = 2/256)."""
    if cell.fire.nonce == "f1" and cell.speaker == first_speaker(cell.seed_id):
        return 1
    return -1 if cell.exchange == 1 else 0


def _one_scenario_below_floor(cell) -> int | None:
    """Every triple D = -1, except that the first plan seed's clinical grades at exchanges 1-3 are nulls, so none of
    its triples reaches 10.1's floor: the gate runs on 7 of the plan's 8 scenarios."""
    if cell.seed_id == FULL_SETS["original"][0] and cell.register == ex.CLINICAL and cell.exchange <= 3:
        return None
    return 0 if cell.register == ex.COLLOQUIAL else 1


# each 10.2 outcome, by the campaign whose recomputed tests select it: (the eight-seed campaign?, the design)
ROW_DESIGNS = {
    # all 30 triples negative, all 8 scenario means negative, the prospective replication negative
    "row1": (True, shift(lambda c: -1)),
    # the prospective triples tied, so the replication has no direction
    "row2": (True, shift(lambda c: -1 if c.fire.partition == "discovery" else 0)),
    # four scenarios: the gate's smallest p is 2/16, so it cannot reject
    "row3": (False, shift(lambda c: -1)),
    "row4/row1": (True, shift(lambda c: 1)),
    "row4/row2": (True, shift(lambda c: 1 if c.fire.partition == "discovery" else 0)),
    "row4/row3": (False, shift(lambda c: 1)),
    # six negative and six positive triples
    "row5": (False, shift(lambda c: -1 if c.fire.nonce == "t1" else 1)),
    # every triple tied: no sign test ran
    "not_computable": (False, shift(lambda c: 0)),
    "no_prespecified_row": (True, shift(_one_positive_triple_per_scenario)),
    "row1 on 7 of 8 scenarios": (True, _one_scenario_below_floor),
}


@pytest.mark.parametrize("row", ["row1", "row2", "row3", "row4/row1", "row4/row2", "row4/row3", "row5"])
def test_each_headline_row_is_the_one_the_recomputed_tests_select_worded_verbatim(tmp_path, row):
    """Regression (Codex review of 2026-09-25): the headline row was published from the artifact unchecked. Each row
    is now exercised by a campaign whose statistics select it, and the exporter's own selection (the analysis's
    wording_row rule over the recomputed tests) is what the page gets, its text the design note's cell verbatim."""
    full, design = ROW_DESIGNS[row]
    camp = designed(tmp_path / "c", design, full=full)
    artifact = syn.build_artifact(camp)
    assert (artifact["section_10_2"]["wording"]["row_id"], artifact["section_10_2"]["wording"][
        "selectable_as_registered"]) == (row, True)
    rows, _ = note_rows()
    assert export(camp, tmp_path, artifact).summary["headline"] == {"row_id": row, "text": rows[row.split("/")[0]]}


@pytest.mark.parametrize("case, headline", [
    ("not_computable", {"row_id": "not_computable", "text": None}),
    ("no_prespecified_row", {"row_id": "no_prespecified_row", "text": None}),
    ("row1 on 7 of 8 scenarios", {"row_id": "not_selectable_as_registered:row1", "text": None}),
])
def test_unworded_and_unselectable_rows_are_carried_by_name(tmp_path, case, headline):
    full, design = ROW_DESIGNS[case]
    camp = designed(tmp_path / "c", design, full=full)
    assert export(camp, tmp_path, syn.build_artifact(camp)).summary["headline"] == headline


@pytest.mark.parametrize("field, value", [("row_id", "row2"), ("row_id", "row4/row1"),
                                          ("selectable_as_registered", False)])
def test_refuses_a_headline_row_the_recomputed_tests_do_not_select(tmp_path, field, value):
    """Regression (Codex review of 2026-09-25): an artifact whose wording block names another row, or calls the row
    not selectable, with every test field consistent, was published with that row."""
    camp = designed(tmp_path / "c", ROW_DESIGNS["row1"][1])
    artifact = syn.build_artifact(camp)
    artifact["section_10_2"]["wording"][field] = value
    msg = refused(camp, tmp_path, artifact)
    assert "the recomputed primary test, scenario gate and prospective replication select ('row1', True)" in msg


# each 10.3 statement, by the ranks (colloquial, careful lay, clinical) of the eight-seed campaign's grades that give it
STATEMENT_DESIGNS = {
    # style -2, vocabulary 0, paired difference -2 in every second-set triple
    "style_larger": ranks(0, 2, 2),
    # style -2, vocabulary -1, paired difference -1
    "style_larger+vocabulary_also_lowered": ranks(0, 2, 3),
    # the second fire's triples have paired difference +2 and the others -2: 10 of 15 negative, p = 0.30
    "not_separated": lambda c: {ex.COLLOQUIAL: 0, ex.CAREFUL_LAY: 0 if c.fire.nonce == "f2" else 2,
                                ex.CLINICAL: 2}[c.register],
    # style 0, vocabulary -2, paired difference +2: significant, and positive
    "no_prespecified_statement": ranks(1, 1, 3),
    # style -1 and vocabulary -1 everywhere: every paired difference tied
    "not_computable": ranks(0, 1, 2),
}


@pytest.mark.parametrize("statement", ["style_larger", "style_larger+vocabulary_also_lowered", "not_separated"])
def test_each_style_sentence_is_the_one_the_recomputed_decomposition_selects_worded_verbatim(tmp_path, statement):
    """Regression (Codex review of 2026-09-25): the 10.3 statement was published from the artifact unchecked. Each is
    now exercised by a campaign whose decomposition gives it, recomputed from the rows by the exporter."""
    camp = designed(tmp_path / "c", STATEMENT_DESIGNS[statement])
    artifact = syn.build_artifact(camp)
    st = artifact["section_10_3"]["statement"]
    assert st["statement_id"] + ("+vocabulary_also_lowered" if st["vocabulary_also_lowered"] else "") == statement
    out = export(camp, tmp_path, artifact).summary["style_sentence"]
    _, s3 = note_rows()
    text = ex.load_wording(ex.WORDING_FILE, ex.DESIGN_NOTE).statements[statement.split("+")[0]]
    assert out == {"row_id": statement, "text": text} and text in s3


@pytest.mark.parametrize("case", ["not_computable", "no_prespecified_statement", "refused"])
def test_unworded_statements_are_carried_by_name(tmp_path, case):
    camp = designed(tmp_path / "c", STATEMENT_DESIGNS.get(case, ranks(0, 2, 2)))
    artifact = syn.build_artifact(camp, section_10_3_refused=case == "refused")
    assert export(camp, tmp_path, artifact).summary["style_sentence"] == {"row_id": case, "text": None}


@pytest.mark.parametrize("field, value", [("statement_id", "not_separated"), ("statement_id", "no_prespecified_statement"),
                                          ("vocabulary_also_lowered", True)])
def test_refuses_a_statement_the_recomputed_decomposition_does_not_give(tmp_path, field, value):
    """Regression (Codex review of 2026-09-25): an artifact naming another 10.3 statement, or adding the vocabulary
    clause, was published with it."""
    camp = designed(tmp_path / "c", STATEMENT_DESIGNS["style_larger"])
    artifact = syn.build_artifact(camp)
    artifact["section_10_3"]["statement"][field] = value
    msg = refused(camp, tmp_path, artifact)
    assert "the recomputed decomposition on scenario set second gives ('style_larger', False)" in msg


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


def test_cli_writes_both_files_and_prints_the_previous_diff(shared, tmp_path, capsys, monkeypatch):
    camp, _ = shared
    monkeypatch.setattr(ex, "REPOSITORY", ex.synthetic_checkout(camp.root))
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(syn.build_artifact(camp)), encoding="utf-8")
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    args = ["--analysis", str(artifact), "--site", str(site), "--disclosure-log", str(tmp_path / "none.jsonl"),
            "--plan", str(camp.plan_path), *map(str, camp.run_dirs)]
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


@pytest.mark.parametrize("case", ["no inputs", "one input missing", "another commit's script", "path escapes"])
def test_refuses_an_analysis_commit_that_does_not_hold_the_recorded_inputs(shared, tmp_path, case):
    """Regression (Codex review of 2026-09-25): has_commit proved only that the id names some commit, so an unrelated
    existing commit passed as the analysis revision. The commit must hold every input the artifact records
    (identity.inputs) with the recorded sha256."""
    camp, _ = shared
    artifact = syn.build_artifact(camp)
    inputs = artifact["identity"]["inputs"]
    if case == "no inputs":
        del artifact["identity"]["inputs"]
        expected = "records no identity.inputs, so its analysis commit cannot be shown"
    elif case == "one input missing":
        del inputs["judge_runner"]
        expected = "records no identity.inputs for ['judge_runner']"
    elif case == "another commit's script":
        inputs["script"]["sha256"] = "0" * 64                 # the commit holds other bytes than the analysis read
        expected = "records its script scripts/petri_multiturn_synthetic.py as sha256 000000000000, but its analysis"
    else:
        inputs["plan"]["path"] = "../plan.json"
        expected = "records identity.inputs.plan as"
    assert expected in refused(camp, tmp_path, artifact)


def test_blob_sha256_reads_a_file_as_a_commit_holds_it(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    for cmd in (["init", "-q"], ["add", "a.txt"], ["commit", "-q", "-m", "one"]):
        if cmd[0] == "add":
            (repo / "a.txt").write_text("one", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    (repo / "a.txt").write_text("two", encoding="utf-8")         # the working tree moves; the commit does not
    assert ex.blob_sha256(head, "a.txt", root=repo) == ex.hashlib.sha256(b"one").hexdigest()
    assert ex.blob_sha256(head, "b.txt", root=repo) is None


def test_the_runs_must_be_this_checkouts_not_a_copy_in_another_data_petri_runs(shared, tmp_path, capsys, monkeypatch):
    """Regression (Codex review of 2026-09-24): any directory ending in data/petri/runs was accepted, so an export of
    copied runs printed a verify-chain command that names the checkout's own runs, not the bytes exported."""
    camp, _ = shared
    # the CLI's own checkout, except that it holds the synthetic analysis commit
    monkeypatch.setattr(ex, "REPOSITORY", dataclasses.replace(
        ex.REPOSITORY, has_commit=lambda sha: sha == syn.ANALYSIS_COMMIT,
        file_sha256_at=ex.synthetic_checkout(camp.root).file_sha256_at))
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(syn.build_artifact(camp)), encoding="utf-8")
    # the CLI exports only from this checkout's data/petri/runs; the synthetic runs sit in another one
    assert ex.main(["--analysis", str(artifact), "--dry-run", "--disclosure-log", str(tmp_path / "none.jsonl"),
                    "--plan", str(camp.plan_path), *map(str, camp.run_dirs)]) == 2
    err = capsys.readouterr().err
    assert f"not in {ex.ROOT / 'data' / 'petri' / 'runs'}" in err and "would verify other bytes" in err
    # and given the campaign's own runs directory, a copy of its runs elsewhere is refused just the same
    copy = tmp_path / "copy" / "data" / "petri" / "runs"
    for d in camp.run_dirs:
        shutil.copytree(d, copy / d.name)
    with pytest.raises(ex.ExportRefusal, match="the directory the page's verify-chain command"):
        ex.export([copy / d.name for d in camp.run_dirs], artifact, disclosure_log=tmp_path / "none.jsonl",
                  seal_registry=SEAL, checkout=ex.synthetic_checkout(camp.root), plan_path=camp.plan_path)


def test_the_exporter_commit_is_recorded_and_names_every_file_the_export_read(shared, tmp_path):
    """Regression (Codex review of 2026-09-24): the exporter's revision was printed after writing and never recorded,
    so the published files did not say which exporter produced them."""
    camp, _ = shared
    seen: list[Path] = []
    checkout = ex.Checkout(camp.root / "data" / "petri" / "runs", lambda paths: seen.extend(paths) or "e" * 40,
                           lambda sha: sha == syn.ANALYSIS_COMMIT, ex.synthetic_checkout(camp.root).file_sha256_at)
    out = export(camp, tmp_path, checkout=checkout).summary["provenance"]
    assert out["exporter_commit"] == "e" * 40
    read = {Path(p).resolve() for p in seen}
    must = [Path(ex.__file__), ex.SEED_FILE, ex.ADVICE_RUBRIC, ex.OUTCOME_REGISTRY, ex.VOCABULARY_FILE,
            ex.WORDING_FILE, ex.DESIGN_NOTE, ex.SWAPS_FILE, tmp_path / "artifact.json",
            tmp_path / "no_disclosure_log.jsonl", ROOT / "scripts" / "petri_audit" / "judge_runner.py",
            *(d / n for d in camp.run_dirs
              for n in ("manifest.json", "judgments.jsonl", "transcripts.jsonl", "rule_outcomes.jsonl"))]
    assert not [str(p) for p in must if p.resolve() not in read]


def _repo_git(repo: Path, *argv: str) -> str:
    """git in a throwaway repository, isolated from the user's and the system's configuration."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "synthetic", "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
                "GIT_COMMITTER_NAME": "synthetic", "GIT_COMMITTER_EMAIL": "synthetic@example.invalid"})
    return subprocess.run(["git", "-C", str(repo), *argv], check=True, capture_output=True, env=env).stdout.decode()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_commit_exists_accepts_only_a_commit_object_of_the_repository(shared, tmp_path):
    """Regression (Codex review of 2026-09-25): REPOSITORY's has_commit is `git cat-file -e <sha>^{commit}` in the
    checkout, so a well-formed id of no commit, or of a tree or blob, is refused, and an export from a repository
    that holds the artifact's commit goes through."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_git(repo, "init", "-q")
    (repo / "a.json").write_text("{}", encoding="utf-8")
    _repo_git(repo, "add", "-A")
    _repo_git(repo, "commit", "-q", "-m", "one")
    head = _repo_git(repo, "rev-parse", "HEAD").strip()
    tree = _repo_git(repo, "rev-parse", "HEAD^{tree}").strip()
    blob = _repo_git(repo, "rev-parse", "HEAD:a.json").strip()
    assert ex.commit_exists(head, root=repo)
    assert not any(ex.commit_exists(x, root=repo) for x in ("d" * 40, tree, blob))
    camp, _ = shared
    checkout = ex.Checkout(camp.root / "data" / "petri" / "runs", lambda _paths: "e" * 40,
                           lambda sha: ex.commit_exists(sha, root=repo),
                           lambda _sha, path: ex.sha256_file(syn.input_file(camp.root, path)))
    held = export(camp, tmp_path, syn.build_artifact(camp, commit=head), checkout=checkout).summary
    assert held["provenance"]["analysis_commit"] == head
    assert "is not a commit in this repository" in refused(camp, tmp_path, syn.build_artifact(camp, commit=tree),
                                                           checkout=checkout)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_checkout_identity_names_a_clean_checkout_and_refuses_anything_else(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    _repo_git(repo, "init", "-q")
    for name, text in (("data/a.json", "{}"), ("data/b.json", "[]"), ("other.txt", "x"), (".gitignore", "ign.json\n")):
        (repo / name).write_text(text, encoding="utf-8")
    _repo_git(repo, "add", "-A")
    _repo_git(repo, "commit", "-q", "-m", "inputs")
    head = _repo_git(repo, "rev-parse", "HEAD").strip()
    inputs = [repo / "data" / "a.json", repo / "data" / "b.json", repo / "data" / "absent.json"]
    assert ex.checkout_identity(inputs, root=repo) == head      # an input absent from disk and index is fine
    (repo / "scratch.txt").write_text("untracked, not read", encoding="utf-8")
    assert ex.checkout_identity(inputs, root=repo) == head

    def says(paths) -> str:
        with pytest.raises(ex.ExportRefusal) as info:
            ex.checkout_identity(paths, root=repo)
        return str(info.value)
    (repo / "other.txt").write_text("changed", encoding="utf-8")         # a tracked file the list does not name
    assert "tracked files differ from HEAD" in says(inputs) and "other.txt" in says(inputs)
    _repo_git(repo, "add", "other.txt")                                  # staged is not committed either
    assert "other.txt" in says(inputs)
    _repo_git(repo, "commit", "-q", "-m", "other")
    (repo / "data" / "new.json").write_text("{}", encoding="utf-8")
    (repo / "ign.json").write_text("{}", encoding="utf-8")
    message = says([*inputs, repo / "data" / "new.json", repo / "ign.json"])
    assert "data/new.json is not tracked" in message and "ign.json is not tracked" in message
    assert f"{tmp_path / 'elsewhere.json'} is outside the checkout" in says([tmp_path / "elsewhere.json"])
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ex.ExportRefusal, match="git cannot report on the checkout"):
        ex.checkout_identity([], root=plain)


def test_cli_refuses_with_exit_2_and_writes_nothing(shared, tmp_path, capsys):
    camp, _ = shared
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(syn.build_artifact(camp, final=False)), encoding="utf-8")
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    assert ex.main(["--analysis", str(artifact), "--site", str(site), *map(str, camp.run_dirs)]) == 2
    assert "refused:" in capsys.readouterr().err
    assert list((site / "data").iterdir()) == []


# ------------------------------------------------------------------ the pair is written fully or not at all


PAIR = ("petri_multiturn_summary.json", "petri_multiturn_conversations.json")


def _pair_bytes(data: Path) -> dict[str, bytes | None]:
    return {n: (data / n).read_bytes() if (data / n).is_file() else None for n in PAIR}


def _fail_second_replacement(monkeypatch, data: Path, exc: BaseException) -> None:
    """os.replace raises `exc` the first time anything is renamed onto the conversations file, i.e. after the summary
    has been replaced and before the conversations file is (a failure between the two replacements)."""
    real, fired = os.replace, []

    def flaky(src, dst, *a, **kw):
        if Path(dst) == data / PAIR[1] and not fired:
            fired.append(src)
            raise exc
        return real(src, dst, *a, **kw)
    monkeypatch.setattr(os, "replace", flaky)


@pytest.mark.parametrize("before", ["old pair", "no pair"])
def test_a_failure_between_the_two_replacements_leaves_the_previous_pair(tmp_path, monkeypatch, before):
    """Regression (Codex review of 2026-09-24): the two files were renamed into place one after the other, so a
    failure after the first rename left a new summary beside the old conversations."""
    data = tmp_path / "site" / "data"
    data.mkdir(parents=True)
    if before == "old pair":
        ex.write_site(data.parent, {"generation": "old"}, {"generation": "old"})
    previous = _pair_bytes(data)
    _fail_second_replacement(monkeypatch, data, OSError("simulated failure between the two replacements"))
    with pytest.raises(OSError, match="simulated failure"):
        ex.write_site(data.parent, {"generation": "new"}, {"generation": "new"})
    assert _pair_bytes(data) == previous
    assert sorted(p.name for p in data.iterdir()) == (sorted(PAIR) if before == "old pair" else [])


class _Killed(BaseException):
    """Stands for the process dying: nothing after it runs."""


def test_a_write_killed_between_the_replacements_is_caught_by_the_gate_and_rolled_back(tmp_path, monkeypatch):
    """A kill between the two renames runs no handler, so the mixed pair stays on disk beside the swap directory and
    its journal: the contract validator fails the site over it, and the next write, or recover_interrupted_write,
    puts the previous pair back first."""
    site = tmp_path / "site"
    data = site / "data"
    data.mkdir(parents=True)
    ex.write_site(site, {"generation": "old"}, {"generation": "old"})
    previous = _pair_bytes(data)
    with monkeypatch.context() as m:
        _fail_second_replacement(m, data, _Killed())
        m.setattr(ex, "recover_interrupted_write", lambda *a, **kw: False)   # a killed process recovers nothing
        with pytest.raises(_Killed):
            ex.write_site(site, {"generation": "new"}, {"generation": "new"})
    mixed = _pair_bytes(data)
    assert mixed[PAIR[0]] != previous[PAIR[0]] and mixed[PAIR[1]] == previous[PAIR[1]]
    swap = ex.swap_dir(data, sample=False)
    assert (swap / "journal.json").is_file()
    rep = vfc.Report()
    vfc.check_owner_run(rep, site)
    assert any(e.startswith(f"data/{swap.name} :: ") and "interrupted write" in e for e in rep.errors)

    assert ex.recover_interrupted_write(data) is True
    assert _pair_bytes(data) == previous and not swap.exists()
    rep = vfc.Report()
    vfc.check_owner_run(rep, site)
    assert not any("interrupted write" in e for e in rep.errors)


def test_the_next_write_rolls_back_an_interrupted_one_then_writes_the_whole_pair(tmp_path, monkeypatch):
    site = tmp_path / "site"
    data = site / "data"
    data.mkdir(parents=True)
    ex.write_site(site, {"generation": "old"}, {"generation": "old"})
    with monkeypatch.context() as m:
        _fail_second_replacement(m, data, _Killed())
        m.setattr(ex, "recover_interrupted_write", lambda *a, **kw: False)
        with pytest.raises(_Killed):
            ex.write_site(site, {"generation": "new"}, {"generation": "new"})
    ex.write_site(site, {"generation": "newer"}, {"generation": "newer"})
    assert [json.loads((data / n).read_text("utf-8")) for n in PAIR] == [{"generation": "newer"}] * 2
    assert sorted(p.name for p in data.iterdir()) == sorted(PAIR)


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
    assert summary["status"]["final"] is False
    assert summary["provenance"]["analysis_commit"] == summary["provenance"]["exporter_commit"] == "SAMPLE"
    assert summary["provenance"]["analysis_sha256"] == "SAMPLE"
    assert [s["seed_id"] for s in conversations["seeds"]] == VOCAB["samples"]["seed_ids"]
    texts = [x for c in conversations["conversations"] for e in c["exchanges"]
             for x in (e["user"], e["reply"], *(i["text"] for i in e["interim"]))]
    assert texts and all(x.startswith("[Sample ") for x in texts)
    assert len(summary["triples"]) == len(VOCAB["samples"]["seed_ids"]) * VOCAB["samples"]["epochs"]


def test_exported_and_sample_files_pass_the_contract_validator(shared, tmp_path):
    camp, _ = shared
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    ex.write_site(site, *ex.sample_export(seal_registry=SEAL), sample=True)
    # with no Petri pack sent, the real summary cites none, and the validator refuses exactly that (decision 16)
    result = export(camp, tmp_path)
    ex.write_site(site, result.summary, result.conversations)
    rep = vfc.Report()
    vfc.check_owner_run(rep, site)
    assert sorted(rep.errors) == [f"petri_multiturn_summary.json :: $.status.vendor_pack.{k} :: null where a value is "
                                  f"required" for k in ("sent", "version")] and rep.warnings == [] and rep.notes == []
    log = tmp_path / "disclosure_log.jsonl"
    log.write_text(json.dumps({"pack_version": "petri-v000000000001", "lane": "petri", "vendor": "anthropic",
                               "sent_utc": "2026-09-25T00:00:00Z"}) + "\n", encoding="utf-8")
    result = export(camp, tmp_path, disclosure_log=log)
    ex.write_site(site, result.summary, result.conversations)
    rep = vfc.Report()
    vfc.check_owner_run(rep, site)
    assert rep.errors == [] and rep.warnings == [] and rep.notes == []
