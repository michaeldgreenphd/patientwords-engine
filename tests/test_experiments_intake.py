"""scripts/experiments/intake.py: an authored batch of case families -> review packet and measurement manifest.

Everything here runs on ``tests/fixtures/experiments/intake_families_synthetic.json``: eight placeholder families
with abstract wording. No test reads a real stimulus, loads a model or writes inside the checkout.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.experiments import cli, intake
from scripts.experiments.common import Refusal, digest, prompt_digest, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "experiments" / "intake_families_synthetic.json"
BATCH_SHA = sha256_bytes(FIXTURE.read_bytes())
MEASURED_STEM = "agscen_r7b_20261109"       # a stem with landed measurements under trace_out/


def _batch() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _verdicts(batch_sha: str = BATCH_SHA, **decisions: str) -> dict:
    return {"source": {"families_sha256": batch_sha}, "owner_read_utc": "2000-01-01T00:00:00Z",
            "families": [{"family_id": f["family_id"], "owner_verdict": decisions.get(f["family_id"].replace("-", "_"), "right"),
                          "owner_reasons": [], "owner_note": ""} for f in _batch()]}


def _run(batch: list[dict] | None = None, **options) -> dict:
    design = intake.load_design()
    options.setdefault("sealed", lambda text: False)
    return intake.run_intake(_batch() if batch is None else batch, batch_id="synthetic", batch_sha256=BATCH_SHA,
                             source_ref="fixture", design=design,
                             design_sha256=sha256_bytes(intake.DESIGN_PATH.read_bytes()), **options)


def _family(manifest: dict, fid: str) -> dict:
    return next(r for r in manifest["families"] if r["family_id"] == fid)


def _review(fid: str, role: str, texts_sha: str, value: str | None = "same", **over) -> dict:
    rubric = json.loads(intake.RUBRIC_PATH.read_text(encoding="utf-8"))["pair_equivalence_review"]
    items = next(r["reviews"] for r in rubric["reviewers"] if r["role"] == role)
    return {"family_id": fid, "role": role, "reviewer": "placeholder reviewer", "reviewer_kind": "human",
            "date": "2000-01-01", "texts_sha256": texts_sha, "items": {i: value for i in items}, **over}


def test_the_design_file_is_a_draft_and_names_only_known_variants_and_strata() -> None:
    design = intake.load_design()
    assert design["status"].startswith("draft") and design["protocol"]["status"] == "draft, not signed"
    assert {c["suffix"] for c in design["contrasts"]} == {"reg", "mpar", "epar", "chg", "attr", "qb", "qc"}
    assert design["strata"]["register"]["confirmatory_candidate"] is True
    assert not design["strata"]["patient_explanation"]["confirmatory_candidate"]
    assert not design["strata"]["syntax_crossing"]["confirmatory_candidate"]
    assert "triage accuracy" in design["endpoint"]["is_not"]


def test_a_clean_batch_passes_software_validation_and_nothing_else_is_implied() -> None:
    manifest = _run()
    assert manifest["software_validation"]["status"] == "passed" and manifest["software_validation"]["errors"] == 0
    assert len(manifest["families"]) == 8 and all(r["admissible"] for r in manifest["families"])
    for row in manifest["families"]:
        assert row["review"]["status"] == "domain_review_pending"
        assert row["review"]["owner_read"] == {"status": "not_read"}
        assert row["review"]["clinician"]["status"] == row["review"]["patient_language_reviewer"]["status"] == "not_reviewed"
        assert set(row["review"]["clinician"]["items"].values()) == {None}          # never entered as 'same'
        assert row["eligibility"]["publication"]["shareable"] is True              # shared whatever the effect
        blocked = row["eligibility"]["confirmatory"]["blocked_by"]
        assert not row["eligibility"]["confirmatory"]["eligible"]
        assert {"protocol_not_signed", "clinician_review_missing", "patient_language_review_missing",
                "owner_read_not_read"} <= set(blocked)
    assert manifest["inventory"]["confirmatory_eligible"] == 0


def test_the_three_manipulations_and_the_two_family_flags_stay_in_their_own_strata() -> None:
    manifest = _run()
    strata = {c["id"]: c["stratum"] for r in manifest["families"] for c in r["contrasts"]}
    assert strata["s-01-reg"] == strata["s-01-mpar"] == strata["s-01-chg"] == "register"
    assert strata["s-01-attr"] == strata["s-03-attr"] == "patient_explanation"       # a belief is added: not register
    assert strata["s-01-qb"] == strata["s-07-qc"] == "syntax_crossing"
    assert strata["s-02-reg"] == "register_with_dialect" and _family(manifest, "s-02")["flags"] == ["dialect"]
    assert strata["s-05-reg"] == "new_carrier" and _family(manifest, "s-05")["flags"] == ["new_carrier"]
    for row in manifest["families"]:
        if row["flags"]:
            assert f"exploratory_stratum:{row['register_stratum']}" in row["eligibility"]["confirmatory"]["blocked_by"]
    counts = manifest["inventory"]["all_admissible"]["contrasts_by_stratum_and_role"]
    assert counts["register/contrast"] == 6 and counts["patient_explanation/contrast"] == 2
    assert counts["syntax_crossing/contrast"] == 4 and counts["register/paraphrase_control"] == 12
    assert len(manifest["comparisons_not_made"]) == 2 and "Care tiers are not compared" in manifest["comparisons_not_made"][0]


def test_the_manifest_holds_hashes_and_no_prompt_text() -> None:
    manifest = _run()
    blob = json.dumps(manifest)
    for family in _batch():
        row = _family(manifest, family["family_id"])
        assert row["family_sha256"] == digest(family) and row["texts_sha256"] == digest(family["texts"])
        for name, value in family["texts"].items():
            assert row["variants"][name]["sha256"] == prompt_digest(value) and value not in blob
    assert manifest["batch"]["sha256"] == BATCH_SHA and manifest["design"]["sha256"]


def test_splits_keep_a_family_whole_are_seeded_and_are_never_redrawn() -> None:
    first, again = _run(split_seed=7), _run(split_seed=7)
    assert first["splits"] == again["splits"] and first["splits"]["seed_for_new_assignments"] == 7
    assert {r["split"] for r in first["families"]} <= set(intake.SPLITS)             # one split per family: all wordings
    record = {"seed": 7, "strata": {f["family_id"]: f["right_care"] for f in _batch()},
              "splits": {r["family_id"]: r["split"] for r in first["families"]}}
    kept = _run(split_records=[record], split_seed=999)                             # another seed changes nothing
    assert [r["split"] for r in kept["families"]] == [r["split"] for r in first["families"]]
    assert kept["splits"]["newly_assigned"] == [] and kept["splits"]["records_checked"][0]["reproduces_from_its_seed"]
    unassigned = _run()
    assert {r["split"] for r in unassigned["families"]} == {None}
    assert "split_unassigned" in unassigned["families"][0]["eligibility"]["confirmatory"]["blocked_by"]
    clash = {"splits": {**record["splits"], "s-01": "validation" if record["splits"]["s-01"] != "validation" else "discovery"}}
    with pytest.raises(Refusal) as refusal:
        _run(split_records=[record, clash])
    assert refusal.value.code == "split_conflict"


def test_no_split_and_no_subset_is_chosen_after_measurement() -> None:
    with pytest.raises(Refusal) as refusal:
        _run(split_seed=7, stem=MEASURED_STEM)
    assert refusal.value.code == "split_after_measurement"
    record = {"splits": {r["family_id"]: r["split"] for r in _run(split_seed=7)["families"]}}
    read_back = _run(split_records=[record], stem=MEASURED_STEM)                    # a recorded split is only read
    assert read_back["measurements"]["existing_run_directories"] and read_back["splits"]["newly_assigned"] == []
    options = dict(split_records=[record], verdicts=[_verdicts()], mechanistic_families=1, mechanistic_seed=3)
    before = _run(**options)
    with pytest.raises(Refusal) as refusal:
        _run(**options, stem=MEASURED_STEM)
    assert refusal.value.code == "subset_after_measurement"
    assert _run(**options, stem=MEASURED_STEM, previous_manifest=before)["mechanistic_subset"] == before["mechanistic_subset"]


def test_the_mechanistic_subset_is_a_seeded_draw_from_kept_unflagged_discovery_families() -> None:
    record = {"splits": {f["family_id"]: "discovery" for f in _batch()}}
    manifest = _run(split_records=[record], verdicts=[_verdicts(s_06="excluded")], mechanistic_families=3, mechanistic_seed=11)
    subset = manifest["mechanistic_subset"]
    assert subset["status"] == "selected_before_outcomes" and subset["outcome_selected"] is False
    assert len(subset["families"]) == 3 and subset == _run(
        split_records=[record], verdicts=[_verdicts(s_06="excluded")], mechanistic_families=3, mechanistic_seed=11)["mechanistic_subset"]
    assert not {"s-02", "s-05", "s-06"} & set(subset["families"])                  # dialect, new carrier, excluded
    work = manifest["estimated_work"]["mechanistic_subset"]
    assert work["sites_per_contrast_with_controls"] == 4 and work["runner_minutes"] == {"low": 120, "high": 180}
    assert work["measured"] is False and "one fitted basis per model" in subset["ica_basis"]
    held_out = _run(split_records=[{"splits": {f["family_id"]: "fresh_test" for f in _batch()}}],
                    verdicts=[_verdicts()], mechanistic_families=3, mechanistic_seed=11)
    assert held_out["mechanistic_subset"]["families"] == []                         # held-out families are not drawn
    assert _run()["mechanistic_subset"]["status"] == "not_selected"


@pytest.mark.parametrize("mutate, expected", [
    (lambda f: f["texts"].update(everyday=f["texts"]["everyday"] + " now"), "boundary"),
    (lambda f: f["changed_fact"].update(fact_id="f9"), "changed_fact"),
    (lambda f: f["swap_spans"].update(everyday_span="other words"), "single_swap"),
    (lambda f: f["changed_fact"].update(right_care_after=f["right_care"]), "changed_fact"),
    (lambda f: f["texts"].update(medical=f["texts"]["medical"].replace("alpha with", "alpha, with")), "style"),
    (lambda f: f.update(target_token=" doctor"), "tier"),
    (lambda f: f["everyday_sources"][1].update(quote_type="none"), "sources"),
    (lambda f: f["texts"].pop("quad_b"), "shape"),
    (lambda f: f["texts"].pop("medical_paraphrase"), "shape"),
])
def test_structural_errors_are_named_and_fail_software_validation(mutate, expected) -> None:
    batch = _batch()
    mutate(batch[0])
    manifest = _run(batch)
    check = manifest["software_validation"]
    assert check["status"] == "failed" and check["errors"] >= 1
    messages = [m for r in manifest["families"] for m in r["validation"]["errors"]] + [
        m for u in check["unusable_families"] for m in u["errors"]]
    assert any(expected in m for m in messages), messages
    rows = [r for r in manifest["families"] if r["family_id"] == "s-01"]
    assert not rows or (not rows[0]["admissible"] and not rows[0]["eligibility"]["publication"]["shareable"])


def test_duplicate_cases_are_found_inside_a_batch_and_against_earlier_batches() -> None:
    batch = _batch()
    batch[1]["texts"]["everyday"] = batch[0]["texts"]["everyday"]
    batch[1]["swap_spans"] = dict(batch[0]["swap_spans"])
    batch[2]["condition"] = batch[0]["condition"].upper()
    batch.append(copy.deepcopy(batch[3]))
    manifest = _run(batch)
    assert any("duplicate: text everyday is also a text of s-01" in m for m in _family(manifest, "s-02")["validation"]["errors"])
    assert any("duplicate_case" in m for m in _family(manifest, "s-03")["validation"]["warnings"])
    assert any("family_id appears 2 times" in m for m in _family(manifest, "s-04")["validation"]["errors"])
    earlier = _batch()[:2]
    earlier[0]["family_id"] = "p-01"                                                # the same case under another id
    earlier[1]["reference_facts"][0]["text"] = "another fact"                       # the same id, another family
    against = _run(prior_batches={"earlier": earlier})
    assert any("is also a text of p-01 of earlier" in m for m in _family(against, "s-01")["validation"]["errors"])
    assert any("ids are stable" in m for m in _family(against, "s-02")["validation"]["errors"])


def test_an_owner_read_applies_only_to_the_texts_it_was_made_on() -> None:
    manifest = _run(verdicts=[_verdicts(s_02="excluded")])
    assert _family(manifest, "s-01")["review"]["owner_read"]["status"] == "kept"
    assert _family(manifest, "s-02")["review"]["owner_read"]["status"] == "excluded"
    assert "owner_read_excluded" in _family(manifest, "s-02")["eligibility"]["confirmatory"]["blocked_by"]
    assert manifest["inventory"]["owner_kept"]["families"] == 7
    assert _family(manifest, "s-01")["review"]["status"] == "domain_review_pending"  # a read is not a domain review
    earlier = _batch()
    reworded = _batch()
    reworded[3]["texts"]["everyday_paraphrase"] = reworded[3]["texts"]["everyday_paraphrase"].replace("got", "had")
    with pytest.raises(Refusal) as refusal:
        _run(reworded, verdicts=[_verdicts("0" * 64)])
    assert refusal.value.code == "verdicts_source_missing"
    stale = _run(reworded, verdicts=[_verdicts("0" * 64)], read_batches={"0" * 64: earlier})
    read = _family(stale, "s-04")["review"]["owner_read"]
    assert read["status"] == "stale" and read["previous"]["decision"] == "kept"
    assert _family(stale, "s-03")["review"]["owner_read"]["status"] == "kept"


def test_domain_review_follows_the_rubric_and_is_never_inferred() -> None:
    sha = {r["family_id"]: r["texts_sha256"] for r in _run()["families"]}
    doc = {"schema": intake.REVIEWS_SCHEMA, "reviews": [
        _review("s-01", "clinician", sha["s-01"]), _review("s-01", "patient_language_reviewer", sha["s-01"]),
        _review("s-03", "clinician", sha["s-03"]),                                           # one reviewer only
        _review("s-04", "clinician", sha["s-04"], value=None),                               # nothing recorded
        _review("s-06", "clinician", sha["s-06"], items={"severity": "different"}),
        _review("s-07", "clinician", "f" * 64)]}                                              # other texts
    manifest = _run(reviews=[doc], split_seed=5)
    status = {r["family_id"]: r["review"]["status"] for r in manifest["families"]}
    assert status["s-01"] == "reviewed" and status["s-03"] == status["s-04"] == status["s-07"] == "domain_review_pending"
    assert status["s-06"] == "removed_by_review" and _family(manifest, "s-06")["split"] is None
    assert manifest["splits"]["source"]["s-06"] == "removed by review before the split"
    assert _family(manifest, "s-07")["review"]["clinician"]["status"] == "stale"
    assert _family(manifest, "s-04")["review"]["clinician"]["status"] == "incomplete"
    assert "clinician_review_missing" not in _family(manifest, "s-01")["eligibility"]["confirmatory"]["blocked_by"]
    assert not _family(manifest, "s-01")["eligibility"]["confirmatory"]["eligible"]        # protocol not signed, not read
    with pytest.raises(Refusal) as refusal:
        _run(reviews=[{"schema": intake.REVIEWS_SCHEMA,
                       "reviews": [_review("s-01", "clinician", sha["s-01"], reviewer_kind="language model")]}])
    assert refusal.value.code == "not_a_review"
    form = intake.review_form(_run())
    assert len(form["reviews"]) == 16 and all(set(r["items"].values()) == {None} and r["reviewer"] is None for r in form["reviews"])


def test_alignment_is_read_from_recorded_token_ids_and_is_not_recorded_without_them() -> None:
    assert _family(_run(), "s-01")["contrasts"][0]["alignment"] == {"status": "not_recorded"}
    assert _family(_run(), "s-01")["target"]["endpoint_partial"] == "not_recorded"
    vocabulary: dict[str, int] = {}
    prompts = {prompt_digest(t): [vocabulary.setdefault(w, len(vocabulary)) for w in t.split()]
               for f in _batch() for t in f["texts"].values()}
    doc = {"schema": intake.TOKENIZATION_SCHEMA, "tokenizer_id": "fixture/toy-tokenizer", "tokenizer_revision": "1" * 40,
           "source": "word ids made by this test; not a tokenizer", "prompts": prompts,
           "targets": {" ER": [1], " hospital": [2, 3]}}
    manifest = _run(tokenizations=[doc])
    key = "fixture/toy-tokenizer@" + "1" * 12
    by_id = {c["id"]: c["alignment"][key] for r in manifest["families"] for c in r["contrasts"]}
    assert by_id["s-01-reg"]["class"] == "position_aligned" and by_id["s-01-reg"]["suffix_tokens"] == 8
    assert by_id["s-01-chg"]["class"] == "suffix_aligned"                               # stretches of other lengths
    assert by_id["s-01-attr"]["class"] == "suffix_aligned" and by_id["s-01-attr"]["top_stretch_tokens"] == 0
    assert _family(manifest, "s-01")["target"]["endpoint_partial"] is False
    assert _family(manifest, "s-02")["target"]["endpoint_partial"] is True               # a two-token target
    assert _family(manifest, "s-03")["target"]["tokens"][key] == "not_recorded"
    assert manifest["tokenization"][0]["prompts_recorded"] == len(prompts)


def test_the_inventory_names_pinned_models_and_estimates_from_recorded_rates_only() -> None:
    manifest = _run(verdicts=[_verdicts()], split_seed=7, models=["gemma-2-2b", "olmo-2-1b"])
    assert [m["study_id"] for m in manifest["models"]] == ["gemma-2-2b", "olmo-2-1b"]
    assert all(len(m["revision"]) == 40 and m["tokenizer_revision"] == m["revision"] for m in manifest["models"])
    work = manifest["estimated_work"]["behavioural_pass_owner_kept"]
    assert work["pairs"] == manifest["inventory"]["owner_kept"]["contrasts"] == 38 and work["measured"] is False
    assert work["no_recorded_rate"] == ["gemma-2-2b"] and set(work["cpu_logits"]["per_model"]) == {"olmo-2-1b"}
    assert work["cpu_logits"]["runner_seconds"] == 38 * 44.0
    assert manifest["estimated_work"]["domain_review"]["minutes"] == "not_recorded"
    with pytest.raises(Refusal) as refusal:
        _run(models=["no-such-model"])
    assert refusal.value.code == "unknown_model"
    assert _run()["models"] == "not_recorded"


def test_a_pairs_file_is_reconciled_contrast_by_contrast() -> None:
    families = {f["family_id"]: f for f in _batch()}
    pairs = [{"top_prompt": families["s-01"]["texts"]["medical"], "bottom_prompt": families["s-01"]["texts"]["everyday"],
              "target_clinical_token": " ER", "generation": {"id": "s-01-reg"}},
             {"top_prompt": families["s-04"]["texts"]["medical"], "bottom_prompt": "another text",
              "target_clinical_token": " doctor", "generation": {"id": "s-04-reg"}},
             {"top_prompt": "x", "bottom_prompt": "y", "target_clinical_token": " ER", "generation": {"id": "other-1"}}]
    lane = _run(pairs_file=pairs, pairs_file_ref="pairs.json")["lane_input"]
    assert lane["identical"] == 1 and lane["index_of"] == {"s-01-reg": 1} and lane["differs"] == ["s-04-reg"]
    assert "s-02-reg" in lane["absent"] and lane["not_in_this_batch"] == ["other-1"]


def test_outputs_are_reproducible_and_never_overwritten(tmp_path: Path) -> None:
    _, files = intake.intake_files(FIXTURE, batch_id="synthetic", split_seed=7, sealed=lambda text: False)
    _, again = intake.intake_files(FIXTURE, batch_id="synthetic", split_seed=7, sealed=lambda text: False)
    assert files == again and set(files) == set(intake.OUTPUT_NAMES)
    out = tmp_path / "packet"
    assert set(intake.write_outputs(out, files).values()) == {"written"}
    assert set(intake.write_outputs(out, files).values()) == {"unchanged"}
    _, other = intake.intake_files(FIXTURE, batch_id="synthetic", split_seed=8, sealed=lambda text: False)
    before = (out / "intake_manifest.json").read_bytes()
    with pytest.raises(Refusal) as refusal:
        intake.write_outputs(out, other)
    assert refusal.value.code == "output_differs" and (out / "intake_manifest.json").read_bytes() == before
    with pytest.raises(Refusal) as refusal:
        intake.write_outputs(tmp_path / "data" / "packet", files)
    assert refusal.value.code == "protected_root"
    with pytest.raises(Refusal) as refusal:
        intake.write_outputs(ROOT / "intake_out_not_allowed", files)
    assert refusal.value.code == "git_checkout" and not (ROOT / "intake_out_not_allowed").exists()
    packet = files["review_packet.md"].decode("utf-8")
    assert "No model output appears in this packet." in packet and "abstract fact alpha of case 1" in packet
    assert "Changed fact `f2`" in packet and "An abstract evidence sentence." in packet and "no source" in packet


def test_the_command_line_writes_three_files_and_exits_1_on_a_structural_error(tmp_path: Path, capsys) -> None:
    out = tmp_path / "out"
    code = cli.main(["intake", "--batch", str(FIXTURE), "--batch-id", "synthetic", "--split-seed", "7", "--out", str(out)])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0 and summary["status"] == "intake" and set(summary["outputs"].values()) == {"written"}
    assert sorted(p.name for p in out.iterdir()) == sorted(intake.OUTPUT_NAMES)
    assert summary["output_sha256"]["intake_manifest.json"] == sha256_bytes((out / "intake_manifest.json").read_bytes())
    assert cli.main(["intake", "--batch", str(FIXTURE), "--batch-id", "synthetic", "--split-seed", "7", "--out", str(out)]) == 0
    assert set(json.loads(capsys.readouterr().out)["outputs"].values()) == {"unchanged"}
    broken = _batch()
    broken[0]["carrier_frame"] = "so I need to see the"
    bad = tmp_path / "broken.json"
    bad.write_text(json.dumps(broken), encoding="utf-8")
    assert cli.main(["intake", "--batch", str(bad), "--batch-id", "synthetic", "--no-write"]) == 1
    assert json.loads(capsys.readouterr().out)["software_validation"]["status"] == "failed"
    assert cli.main(["intake", "--batch", str(FIXTURE), "--batch-id", "synthetic"]) == 2      # neither --out nor --no-write
    assert json.loads(capsys.readouterr().out)["code"] == "invalid_input"
