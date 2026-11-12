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
LATER_STEM = "placeholder_stem"             # no directory under the real trace_out/; one under measured_root


@pytest.fixture()
def measured_root(tmp_path: Path) -> Path:
    """A root where LATER_STEM has a run directory: the same batch 'after measurement', beside the real root 'before'."""
    (tmp_path / "data" / "simulated").mkdir(parents=True)
    (tmp_path / "data" / "urgency_tiers.draft.json").write_bytes((ROOT / "data" / "urgency_tiers.draft.json").read_bytes())
    (tmp_path / "trace_out" / f"{LATER_STEM}__placeholder-model").mkdir(parents=True)
    return tmp_path


def _batch() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _verdicts(batch_sha: str = BATCH_SHA, **decisions: str) -> dict:
    return {"source": {"families_sha256": batch_sha}, "owner_read_utc": "2000-01-01T00:00:00Z",
            "families": [{"family_id": f["family_id"], "owner_verdict": decisions.get(f["family_id"].replace("-", "_"), "right"),
                          "owner_reasons": [], "owner_note": ""} for f in _batch()]}


def _run(batch: list[dict] | None = None, **options) -> dict:
    design = intake.load_design()
    options.setdefault("sealed", lambda text: False)
    if "split_seed" in options or options.get("mechanistic_families"):
        options.setdefault("stem", LATER_STEM)                 # a split or subset is assigned for a named stem
    return intake.run_intake(_batch() if batch is None else batch, batch_id="synthetic",
                             batch_sha256=options.pop("batch_sha256", BATCH_SHA),
                             source_ref="fixture", design=design,
                             design_sha256=sha256_bytes(intake.DESIGN_PATH.read_bytes()), **options)


def _family(manifest: dict, fid: str) -> dict:
    return next(r for r in manifest["families"] if r["family_id"] == fid)


def _review(fid: str, role: str, basis_sha: str, value: str | None = "same", **over) -> dict:
    rubric = json.loads(intake.RUBRIC_PATH.read_text(encoding="utf-8"))["pair_equivalence_review"]
    items = next(r["reviews"] for r in rubric["reviewers"] if r["role"] == role)
    return {"family_id": fid, "role": role, "reviewer": "placeholder reviewer", "reviewer_kind": "human",
            "date": "2000-01-01", "review_basis_sha256": basis_sha, "items": {i: value for i in items}, **over}


def _concern(cid: str, fid: str, applies: list[str], kind: str = "control_adds_fact", **disposition) -> dict:
    row = {"concern_id": cid, "family_id": fid, "kind": kind, "applies_to": applies, "text": "a placeholder concern",
           "raised_by": "placeholder reviewer", "raised_by_kind": "model", "raised_on": "2000-01-01"}
    if disposition:
        row["disposition"] = disposition
    return row


def _concerns(*rows: dict) -> dict:
    return {"schema": intake.CONCERNS_SCHEMA, "concerns": list(rows)}


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


def test_no_split_and_no_subset_is_chosen_after_measurement(measured_root: Path) -> None:
    with pytest.raises(Refusal) as refusal:
        _run(split_seed=7, stem=MEASURED_STEM)
    assert refusal.value.code == "split_after_measurement"
    strata = {f["family_id"]: f["right_care"] for f in _batch()}
    record = {"seed": 7, "strata": strata, "splits": {r["family_id"]: r["split"] for r in _run(split_seed=7)["families"]}}
    read_back = _run(split_records=[record], stem=MEASURED_STEM)                    # a bound, seeded record is only read
    assert read_back["measurements"]["existing_run_directories"] and read_back["splits"]["newly_assigned"] == []
    assert read_back["splits"]["records_timing"].startswith("Not verified by this command")
    assert _run(split_records=[record], stem=LATER_STEM)["splits"]["records_timing"] == "The batch has no measurements under its stem."
    assert _run(split_records=[record])["splits"]["records_timing"].startswith("No stem was named")
    options = dict(split_records=[record], verdicts=[_verdicts()], mechanistic_families=1, mechanistic_seed=3, stem=LATER_STEM)
    before = _run(**options)                                                        # the stem has no run directory yet
    assert before["measurements"] | {"note": ""} == {"stem": LATER_STEM, "existing_run_directories": [], "note": ""}
    assert before["mechanistic_subset"]["restored_from_previous_manifest"] is False
    with pytest.raises(Refusal) as refusal:
        _run(**options, root=measured_root)
    assert refusal.value.code == "subset_after_measurement"
    restored = _run(**options, root=measured_root, previous_manifest=before)["mechanistic_subset"]
    assert restored["families"] == before["mechanistic_subset"]["families"] and restored["restored_from_previous_manifest"] is True
    # An earlier manifest is a caller-supplied file: the command restores from it and does not vouch for its timing.
    assert restored["status"] == "restored_from_earlier_manifest" and restored["outcome_selected"] == intake.NOT_VERIFIED
    assert restored["timing"].startswith("Not verified by this command") and "possibly outcome-selected" in restored["timing"]
    assert before["mechanistic_subset"]["status"] == "selected_before_outcomes" and "timing" not in before["mechanistic_subset"]


def test_after_measurement_a_split_record_must_be_this_batchs_seeded_draw() -> None:
    strata = {f["family_id"]: f["right_care"] for f in _batch()}
    drawn = intake.assign_splits(strata, 7)
    swapped = dict(drawn)
    a, b = next((x, y) for x in drawn for y in drawn if drawn[x] != drawn[y])
    swapped[a], swapped[b] = drawn[b], drawn[a]
    other_batch = {**strata, "s-99": 4}
    for label, record in (
            ("a bare mapping", {"splits": drawn}),
            ("a hand-chosen assignment", {"seed": 7, "strata": strata, "splits": swapped}),
            ("a record of another batch", {"seed": 7, "strata": other_batch, "splits": intake.assign_splits(other_batch, 7)}),
            ("a record with other care levels", {"seed": 7, "strata": {**strata, "s-01": 1},
                                                 "splits": intake.assign_splits({**strata, "s-01": 1}, 7)})):
        with pytest.raises(Refusal) as refusal:
            _run(split_records=[record], stem=MEASURED_STEM)
        assert refusal.value.code == "split_record_unbound", label
        assert _run(split_records=[{"splits": record["splits"]}] if label == "a bare mapping" else [record])  # read freely before
    assert _run(split_records=[{"seed": 7, "strata": strata, "splits": drawn}], stem=MEASURED_STEM)["splits"]["newly_assigned"] == []


def test_after_measurement_a_subset_is_restored_only_from_a_manifest_of_this_batch_and_stem_written_before(
        measured_root: Path) -> None:
    strata = {f["family_id"]: f["right_care"] for f in _batch()}
    record = {"seed": 7, "strata": strata, "splits": intake.assign_splits(strata, 7)}
    options = dict(split_records=[record], verdicts=[_verdicts()], mechanistic_families=1, mechanistic_seed=3)
    before = _run(**options, stem=LATER_STEM)
    chosen = before["mechanistic_subset"]["families"]
    other_stem = _run(**options, stem="another_placeholder_stem")
    no_stem = {**before, "measurements": {**before["measurements"], "stem": None}}      # the command no longer writes one
    assert other_stem["measurements"]["existing_run_directories"] == []
    forged = [
        {"mechanistic_subset": {"families": chosen}},                                    # a bare family list
        no_stem,                                                                         # lists no run directory whatever exists
        other_stem,                                                                      # about another stem
        {**before, "schema": "something-else/1"},
        {**before, "batch": {**before["batch"], "batch_id": "another"}},
        {**before, "measurements": {**before["measurements"], "existing_run_directories": ["x__model"]}},   # written after
        {**before, "mechanistic_subset": {**before["mechanistic_subset"], "seed": 4}},
        {**before, "mechanistic_subset": {**before["mechanistic_subset"], "status": "not_selected"}},
        None]
    for previous in forged:
        with pytest.raises(Refusal) as refusal:
            _run(**options, stem=LATER_STEM, root=measured_root, previous_manifest=previous)
        assert refusal.value.code == "subset_after_measurement"
    assert _run(**options, stem=LATER_STEM, root=measured_root, previous_manifest=before)["mechanistic_subset"]["families"] == chosen
    changed = _batch()
    next(f for f in changed if f["family_id"] == chosen[0])["reference_facts"][0]["text"] = "another abstract fact"
    with pytest.raises(Refusal) as refusal:                                             # the chosen family is another version now
        _run(changed, **{**options, "verdicts": []}, stem=LATER_STEM, root=measured_root, previous_manifest=before)
    assert refusal.value.code == "subset_family_changed"
    excluded = {**options, "verdicts": [_verdicts(**{chosen[0].replace("-", "_"): "excluded"})]}
    with pytest.raises(Refusal) as refusal:                                             # the owner has since excluded it
        _run(**excluded, stem=LATER_STEM, root=measured_root, previous_manifest=before)
    assert refusal.value.code == "subset_family_not_candidate"
    with pytest.raises(Refusal) as refusal:                                             # no read at all: not a candidate either
        _run(**{**options, "verdicts": []}, stem=LATER_STEM, root=measured_root, previous_manifest=before)
    assert refusal.value.code == "subset_family_not_candidate"


def test_after_measurement_no_family_is_reported_as_eligible_for_a_confirmatory_statement(measured_root: Path) -> None:
    """Every other blocker is cleared here, so the split's unverified timing is the only thing left to block."""
    signed = intake.load_design()
    signed["protocol"] = {**signed["protocol"], "status": "signed (placeholder for this test)"}
    strata = {f["family_id"]: f["right_care"] for f in _batch()}
    record = {"seed": 7, "strata": strata, "splits": intake.assign_splits(strata, 7)}
    basis = {r["family_id"]: r["review_basis_sha256"] for r in _run()["families"]}
    reviews = {"schema": intake.REVIEWS_SCHEMA, "reviews": [
        _review(fid, role, sha) for fid, sha in basis.items() for role in ("clinician", "patient_language_reviewer")]}

    def run(**extra):
        return intake.run_intake(_batch(), batch_id="synthetic", batch_sha256=BATCH_SHA, source_ref="fixture", design=signed,
                                 design_sha256="0" * 64, sealed=lambda text: False, verdicts=[_verdicts()], reviews=[reviews],
                                 split_records=[record], stem=LATER_STEM, **extra)
    before, after = run(), run(root=measured_root)
    plain = [r["family_id"] for r in before["families"] if not r["flags"]]
    assert before["inventory"]["confirmatory_eligible"] == len(plain) > 0             # eligible while nothing is measured
    assert after["inventory"]["confirmatory_eligible"] == 0
    for fid in plain:
        assert _family(before, fid)["eligibility"]["confirmatory"]["blocked_by"] == []
        assert _family(after, fid)["eligibility"]["confirmatory"]["blocked_by"] == ["split_timing_not_verified"]
    assert "read from a manifest written before measurement" in _family(after, plain[0])["eligibility"]["confirmatory"]["applies_to"]


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
    # A family that a review removed is not drawn, even when it is kept by the owner and already in discovery.
    basis = {r["family_id"]: r["review_basis_sha256"] for r in _run()["families"]}
    unflagged = [r["family_id"] for r in _run()["families"] if not r["flags"]]
    removed = {"schema": intake.REVIEWS_SCHEMA, "reviews": [
        _review(unflagged[0], "clinician", basis[unflagged[0]], items={"severity": "different"})]}
    drawn = _run(split_records=[record], verdicts=[_verdicts()], reviews=[removed], mechanistic_families=8, mechanistic_seed=11)
    assert _family(drawn, unflagged[0])["review"]["status"] == "removed_by_review" and _family(drawn, unflagged[0])["split"] == "discovery"
    assert unflagged[0] not in drawn["mechanistic_subset"]["families"]
    assert sorted(drawn["mechanistic_subset"]["families"]) == sorted(unflagged[1:])


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
    sha = {r["family_id"]: r["review_basis_sha256"] for r in _run()["families"]}
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
    assert lane["duplicate_ids"] == {} and lane["rows_without_id"] == [] and lane["clean"] is False
    # A lane reads every row: a repeated id is reported with its rows, never collapsed into the last one.
    repeated = [dict(pairs[1], generation={"id": "s-01-reg"}), pairs[0], {"top_prompt": "x", "bottom_prompt": "y",
                                                                           "target_clinical_token": " ER"}, pairs[0]]
    lane = _run(pairs_file=repeated, pairs_file_ref="pairs.json")["lane_input"]
    assert lane["duplicate_ids"] == {"s-01-reg": [1, 2, 4]} and lane["rows_without_id"] == [3]
    assert lane["identical"] == 0 and "s-01-reg" not in lane["index_of"] and lane["clean"] is False
    whole = [{"top_prompt": top, "bottom_prompt": bottom, "target_clinical_token": f["target_token"], "generation": {"id": cid}}
             for f in _batch() for cid, top, bottom in (
                 (f"{f['family_id']}-{c['suffix']}", f["texts"].get(c["top"]), f["texts"].get(c["bottom"]))
                 for c in intake.load_design()["contrasts"]) if top and bottom]
    assert _run(pairs_file=whole, pairs_file_ref="pairs.json")["lane_input"]["clean"] is True
    partial = _run(pairs_file=whole[:3] + [pairs[2]], pairs_file_ref="pairs.json")["lane_input"]   # absent and foreign rows are listed
    assert partial["clean"] is True and partial["absent"] and partial["not_in_this_batch"] == ["other-1"]


def test_outputs_are_reproducible_and_never_overwritten(tmp_path: Path) -> None:
    _, files = intake.intake_files(FIXTURE, batch_id="synthetic", split_seed=7, stem=LATER_STEM, sealed=lambda text: False)
    _, again = intake.intake_files(FIXTURE, batch_id="synthetic", split_seed=7, stem=LATER_STEM, sealed=lambda text: False)
    assert files == again and set(files) == set(intake.OUTPUT_NAMES)
    out = tmp_path / "packet"
    assert set(intake.write_outputs(out, files).values()) == {"written"}
    assert set(intake.write_outputs(out, files).values()) == {"unchanged"}
    _, other = intake.intake_files(FIXTURE, batch_id="synthetic", split_seed=8, stem=LATER_STEM, sealed=lambda text: False)
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
    code = cli.main(["intake", "--batch", str(FIXTURE), "--batch-id", "synthetic", "--split-seed", "7", "--stem", LATER_STEM, "--out", str(out)])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0 and summary["status"] == "intake" and set(summary["outputs"].values()) == {"written"}
    assert sorted(p.name for p in out.iterdir()) == sorted(intake.OUTPUT_NAMES)
    assert summary["output_sha256"]["intake_manifest.json"] == sha256_bytes((out / "intake_manifest.json").read_bytes())
    assert cli.main(["intake", "--batch", str(FIXTURE), "--batch-id", "synthetic", "--split-seed", "7", "--stem", LATER_STEM, "--out", str(out)]) == 0
    assert set(json.loads(capsys.readouterr().out)["outputs"].values()) == {"unchanged"}
    broken = _batch()
    broken[0]["carrier_frame"] = "so I need to see the"
    bad = tmp_path / "broken.json"
    bad.write_text(json.dumps(broken), encoding="utf-8")
    assert cli.main(["intake", "--batch", str(bad), "--batch-id", "synthetic", "--no-write"]) == 1
    assert json.loads(capsys.readouterr().out)["software_validation"]["status"] == "failed"
    assert cli.main(["intake", "--batch", str(FIXTURE), "--batch-id", "synthetic"]) == 2      # neither --out nor --no-write
    assert json.loads(capsys.readouterr().out)["code"] == "invalid_input"


def test_a_concern_survives_the_owners_keep_and_is_closed_only_by_its_own_disposition() -> None:
    doc = _concerns(_concern("c-1", "s-01", ["chg"]), _concern("c-2", "s-02", ["reg"], kind="fact_parity"),
                    _concern("c-3", "s-03", ["family"], kind="level_disputed", status="pending_clinical_review",
                             note="left for the clinician"),
                    _concern("c-4", "s-04", ["chg"], status="accepted_as_is", by="placeholder owner", by_kind="human",
                             date="2000-01-02", note="accepted for exploratory use"))
    manifest = _run(verdicts=[_verdicts(s_06="excluded")], concerns=[doc])
    first = _family(manifest, "s-01")
    assert first["review"]["owner_read"]["status"] == "kept"                       # kept, and the concern is still open
    assert first["concerns"]["open"] == 1 and first["concerns"]["records"][0]["state"] == "open"
    assert next(c for c in first["contrasts"] if c["id"] == "s-01-chg")["open_concerns"] == ["c-1"]
    assert next(c for c in first["contrasts"] if c["id"] == "s-01-reg")["open_concerns"] == []
    confirmatory = first["eligibility"]["confirmatory"]
    assert confirmatory["controls_with_open_concerns"] == {"s-01-chg": ["c-1"]}    # reported on the control ...
    assert not any(b.startswith("open_concern") for b in confirmatory["blocked_by"])   # ... the register pair is not blocked
    assert "open_concern_on_register_pair:c-2" in _family(manifest, "s-02")["eligibility"]["confirmatory"]["blocked_by"]
    assert "open_concern_on_register_pair:c-3" in _family(manifest, "s-03")["eligibility"]["confirmatory"]["blocked_by"]
    assert _family(manifest, "s-04")["concerns"] | {"records": []} == {
        "records": [], "open": 0, "closed": 1, "note": manifest["inventory"]["concerns"]["rule"]}
    summary = manifest["inventory"]["concerns"]
    assert (summary["open"], summary["closed"]) == (3, 1)
    assert summary["owner_kept_families_with_open_concerns"] == ["s-01", "s-02", "s-03"]
    assert summary["open_by_disposition"] == {"open": 2, "pending_clinical_review": 1}
    assert _family(_run(verdicts=[_verdicts()]), "s-01")["concerns"]["records"] == []   # no concern is invented
    packet = intake.render_packet(manifest, _batch())
    assert "`c-1` **open**" in packet and "`c-4` **closed**" in packet and "pending clinical review: left for the clinician" in packet
    assert "The owner keeping a family does not close it" in packet
    form = intake.review_form(manifest)
    assert next(r for r in form["reviews"] if r["family_id"] == "s-01")["open_concerns"] == ["c-1"]


def test_a_concern_resolved_by_a_revision_reopens_for_any_other_version() -> None:
    basis = _family(_run(), "s-01")["review_basis_sha256"]
    resolved = _concern("c-1", "s-01", ["reg"], kind="wording", status="resolved_by_revision", by="placeholder owner",
                        by_kind="human", date="2000-01-02", note="reworded", resolved_in_review_basis_sha256=basis)
    assert _family(_run(concerns=[_concerns(resolved)]), "s-01")["concerns"]["records"][0]["state"] == "closed"
    revised = _batch()
    revised[0]["reference_facts"][0]["text"] = "another abstract fact"
    record = _family(_run(revised, concerns=[_concerns(resolved)]), "s-01")["concerns"]["records"][0]
    assert record["state"] == "open" and "another version" in record["state_reason"]
    for status in ("accepted_as_is", "resolved_by_revision"):                       # a model cannot close a concern
        with pytest.raises(Refusal) as refusal:
            _run(concerns=[_concerns(_concern("c-9", "s-01", ["reg"], status=status, by="a model", by_kind="model",
                                              date="2000-01-02", note="looks fine", resolved_in_review_basis_sha256=basis))])
        assert refusal.value.code == "not_a_disposition"
    pending = _run(concerns=[_concerns(
        _concern("c-7", "s-01", ["reg"], kind="wording", status="revised_pending_reread", note="reworded by the reviewer"),
        _concern("c-8", "s-01", ["label"], kind="label"),
        _concern("c-6", "s-02", ["reg"], status="withdrawn", by="placeholder reviewer", by_kind="model",
                 date="2000-01-02", note="raised in error"))])
    row = _family(pending, "s-01")
    assert [c["state"] for c in row["concerns"]["records"]] == ["open", "open"]     # a revision alone closes nothing
    assert row["eligibility"]["confirmatory"]["blocked_by"][-1] == "open_concern_on_register_pair:c-7"   # the label does not block
    assert _family(pending, "s-02")["concerns"]["closed"] == 1
    for bad in (_concern("c-9", "s-99", ["reg"]), _concern("c-9", "s-02", ["qb"]), _concern("c-9", "s-01", ["reg"], kind="nope"),
                _concern("c-9", "s-01", ["reg"], status="withdrawn")):
        with pytest.raises(Refusal) as refusal:
            _run(concerns=[_concerns(bad)])
        assert refusal.value.code == "invalid_concerns"
    for by, kind in (("another model", "model"), ("placeholder reviewer", "human"), ("placeholder owner", "human")):
        with pytest.raises(Refusal) as refusal:                                     # only the raiser withdraws a concern
            _run(concerns=[_concerns(_concern("c-9", "s-01", ["reg"], status="withdrawn", by=by, by_kind=kind,
                                              date="2000-01-02", note="not mine to withdraw"))])
        assert refusal.value.code == "not_a_disposition"


@pytest.mark.parametrize("mutate, part", [
    (lambda f: f["reference_facts"][0].update(text="another abstract fact"), "reference_facts"),
    (lambda f: f["changed_fact"].update(right_care_after=3), "care_levels"),
    (lambda f: f["reference_facts"].append({"fact_id": "f9", "text": "an added fact"}), "reference_facts"),
])
def test_a_read_and_a_review_go_stale_when_facts_or_care_labels_change_under_unchanged_prompts(mutate, part) -> None:
    before = _run()
    basis = {r["family_id"]: r["review_basis_sha256"] for r in before["families"]}
    reviews = {"schema": intake.REVIEWS_SCHEMA, "reviews": [
        _review(fid, role, basis[fid]) for fid in ("s-01", "s-02") for role in ("clinician", "patient_language_reviewer")]}
    assert _family(_run(reviews=[reviews]), "s-01")["review"]["status"] == "reviewed"
    changed = _batch()
    mutate(changed[0])
    assert changed[0]["texts"] == _batch()[0]["texts"]                              # no prompt text changed
    after = _run(changed, batch_sha256=sha256_bytes(json.dumps(changed).encode()), verdicts=[_verdicts()],
                 read_batches={BATCH_SHA: _batch()}, reviews=[reviews])
    row = _family(after, "s-01")
    assert row["texts_sha256"] == _family(before, "s-01")["texts_sha256"] and row["review_basis_sha256"] != basis["s-01"]
    read = row["review"]["owner_read"]
    assert read["status"] == "stale" and read["changed_since_read"] == [part] and read["previous"]["decision"] == "kept"
    assert row["review"]["clinician"]["status"] == row["review"]["patient_language_reviewer"]["status"] == "stale"
    assert row["review"]["status"] == "domain_review_pending"
    assert {"owner_read_stale", "clinician_review_missing"} <= set(row["eligibility"]["confirmatory"]["blocked_by"])
    untouched = _family(after, "s-02")                                             # the other family keeps both
    assert untouched["review"]["owner_read"]["status"] == "kept" and untouched["review"]["status"] == "reviewed"


def test_source_verification_is_recorded_per_citation_and_says_nothing_about_fit() -> None:
    batch = _batch()
    cited = next(e for e in batch[0]["everyday_sources"] if e["quote_type"] != "none")
    check = {"schema": intake.SOURCE_CHECK_SCHEMA, "checked_utc": "2000-01-01", "method": "placeholder lookup", "entries": [
        {"family_id": "s-01", "expression": cited["expression"], "identifier": cited["pmid_or_doi"],
         "record_matches_citation": True, "evidence_found": True}]}
    fit = _concerns(_concern("c-fit", "s-01", ["reg"], kind="source_fit", status="pending_patient_language_review",
                             note="the source describes another population"))
    manifest = _run(source_checks=[check], concerns=[fit])
    verification = _family(manifest, "s-01")["sources"]["verification"]
    assert {"expression": cited["expression"], "identifier": cited["pmid_or_doi"],
            "status": "record_and_sentence_found"} in verification["per_citation"]
    assert "does not show that patients" in verification["means"]
    assert _family(manifest, "s-01")["concerns"]["open"] == 1                      # verified, and the fit concern stays open
    assert manifest["inventory"]["source_verification"]["record_and_sentence_found"] == 1
    assert "not_checked" in manifest["inventory"]["source_verification"]
    wrong_id = {**check, "entries": [{**check["entries"][0], "identifier": "PMID: 1"}]}   # a check of another citation
    statuses = {c["expression"]: c["status"] for c in _family(_run(source_checks=[wrong_id]), "s-01")["sources"]["verification"]["per_citation"]}
    assert statuses[cited["expression"]] == "not_checked"
    twice = _batch()                                                                # one wording, two citations, one checked
    second = {**cited, "pmid_or_doi": "PMID: 2", "source": "another placeholder source"}
    twice[0]["everyday_sources"].append(second)
    rows = [c for c in _family(_run(twice, source_checks=[check]), "s-01")["sources"]["verification"]["per_citation"]
            if c["expression"] == cited["expression"]]
    assert {(c["identifier"], c["status"]) for c in rows} == {
        ("PMID: 2", "not_checked"), (cited["pmid_or_doi"], "record_and_sentence_found")} and len(rows) == 2
    section = intake.render_packet(_run(twice, source_checks=[check]), twice).split("## s-02")[0]   # family s-01 only
    packet_rows = [line for line in section.splitlines() if line.startswith(f"| {cited['expression']} |")]
    assert len(packet_rows) == 2 and sum("not checked" in line for line in packet_rows) == 1
    assert "| Citation check |" in intake.render_packet(manifest, batch)


def test_no_timing_claim_is_made_without_a_named_stem_or_under_an_unsigned_protocol() -> None:
    for options in ({"split_seed": 7, "stem": None}, {"mechanistic_families": 1, "mechanistic_seed": 3, "stem": None}):
        with pytest.raises(Refusal) as refusal:                                     # nothing is drawn for an unnamed stem
            _run(**options)
        assert refusal.value.code == "stem_required"
    row = _run()["families"][0]
    assert "stem_not_named" in row["eligibility"]["confirmatory"]["blocked_by"]
    assert "stem_not_named" not in _run(stem=LATER_STEM)["families"][0]["eligibility"]["confirmatory"]["blocked_by"]
    design = intake.load_design()
    for status in ("draft, not signed", "not signed", "unsigned", "superseded", "Draft", "signedish"):
        doc = {**design, "protocol": {**design["protocol"], "status": status}}
        manifest = intake.run_intake(_batch(), batch_id="synthetic", batch_sha256=BATCH_SHA, source_ref="fixture", design=doc,
                                     design_sha256="0" * 64, sealed=lambda text: False)
        assert "protocol_not_signed" in manifest["families"][0]["eligibility"]["confirmatory"]["blocked_by"], status
    for status in ("signed", "signed 2000-01-01 by a placeholder owner"):
        doc = {**design, "protocol": {**design["protocol"], "status": status}}
        manifest = intake.run_intake(_batch(), batch_id="synthetic", batch_sha256=BATCH_SHA, source_ref="fixture", design=doc,
                                     design_sha256="0" * 64, sealed=lambda text: False)
        assert "protocol_not_signed" not in manifest["families"][0]["eligibility"]["confirmatory"]["blocked_by"], status


def test_the_manifest_records_the_validation_parameters_the_caller_set() -> None:
    default, relaxed = _run(), _run(forbid="", max_words=60)
    assert default["software_validation"]["parameters"] | {"note": ""} == {
        "forbid": ",;-", "max_words": 40, "lexicon_supplied": False, "note": ""}
    assert relaxed["software_validation"]["parameters"]["forbid"] == "" and relaxed["software_validation"]["parameters"]["max_words"] == 60
    assert _run(lexicon={"a placeholder form"})["software_validation"]["parameters"]["lexicon_supplied"] is True
