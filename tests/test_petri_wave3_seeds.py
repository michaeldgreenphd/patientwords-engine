"""The wave-3 seed file (docs/framework/petri_seeds_w3.draft.json; docs/petri_wave3_design.md).

Wave 3 lives in its own file with its own copy of the seed schema, which differs from the wave-1/2 schema in
`pilot_wave` alone, so the wave-1/2 file and tests/test_petri_framework_data.py, which pins it, are untouched. Every
check runs offline: validation goes through scripts/petri_audit/seeds.py as the CLI's validate-seeds does, the seal scan
reads the repository's own sealed registry (ops/dashboard.json and data/simulated) as cli preflight does, and the
lexicon check reads the repository's copy of the Consumer Health Vocabulary (data/chv). Seed ids and medical words
are read from the data files, never written here (AGENTS.md hard conventions).
"""
from __future__ import annotations

import copy
import csv
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import cli, seal, seeds  # noqa: E402
from scripts.petri_audit.framework import SEED_FILE, load_json, sha256_text, validate  # noqa: E402

W3_FILE = ROOT / "docs" / "framework" / "petri_seeds_w3.draft.json"
W3_SWAPS = ROOT / "data" / "petri" / "lay_careful_swaps_w3.draft.json"
W3_PLAN = ROOT / "data" / "petri" / "w3_register_contrast_plan.json"
CHV_FILE = ROOT / "data" / "chv" / "CHV_concepts_terms_flatfile_20110204.tsv"
RUNS_DIR = ROOT / "data" / "petri" / "runs"
ARMS = ("clinical", "colloquial", "lay_careful")
TURNS = 10
GENERATION = {"temperature": 1.0, "max_tokens": 4096, "seed_requested": None}
LEXICON_RELATIONS = {"same_concept", "paraphrase", "terminologies_disagree", "unverified"}


@pytest.fixture(scope="module")
def w3_set() -> seeds.SeedSet:
    return seeds.load_seed_file(W3_FILE)


@pytest.fixture(scope="module")
def w3_doc() -> dict:
    return load_json(W3_FILE)


@pytest.fixture(scope="module")
def w12_doc() -> dict:
    return load_json(SEED_FILE)


@pytest.fixture(scope="module")
def swaps() -> dict:
    return load_json(W3_SWAPS)


@pytest.fixture(scope="module")
def plan() -> dict:
    return load_json(W3_PLAN)


def _texts(seed: dict) -> dict[str, str]:
    return {t["key"]: t["text"] for t in seed["texts"]}


def _roles(seed: dict, arm: str = "clinical") -> list[str | None]:
    return [t["context_role"] for t in next(a for a in seed["protocol"]["arms"] if a["id"] == arm)["turns"]]


# ------------------------------------------------------------------ validation


def test_every_wave_three_seed_validates_through_the_seed_module(w3_set):
    """Schema and semantic checks, through the function cli validate-seeds and preflight call, with the file's own
    schema."""
    assert len(w3_set.seeds) == 8
    for seed_id, seed in w3_set.seeds.items():
        assert seeds.validate_seed(seed, w3_set) == [], seed_id


def test_validate_seeds_accepts_the_file_by_path_and_by_wave(capsys):
    """The CLI path the workflow runs (`validate-seeds --seeds "$SEEDS_FILE"`), with and without --wave 3; nothing in
    the CLI refuses a third wave."""
    assert cli.main(["validate-seeds", "--seeds", str(W3_FILE)]) == 0
    assert cli.main(["validate-seeds", "--seeds", str(W3_FILE), "--wave", "3"]) == 0
    out = capsys.readouterr().out
    assert out.count(": ok;") == 16 and "REFUSED" not in out


def test_the_schema_is_the_wave_two_schema_with_pilot_wave_widened_to_three(w3_doc, w12_doc):
    w3_schema, w12_schema = w3_doc["seed_schema"], w12_doc["seed_schema"]
    assert w3_schema["properties"]["pilot_wave"]["enum"] == [1, 2, 3]
    assert w12_schema["properties"]["pilot_wave"]["enum"] == [1, 2], "the wave-1/2 schema is not widened"
    expected = copy.deepcopy(w12_schema)
    expected["properties"]["pilot_wave"] = w3_schema["properties"]["pilot_wave"]
    assert w3_schema == expected, "the copy differs from the wave-1/2 schema in pilot_wave alone"
    broken = copy.deepcopy(w3_doc["seeds"][0])
    broken["pilot_wave"] = 4
    assert any("not in" in p for p in validate(broken, w3_schema))
    assert any("not in" in p for p in validate(w3_doc["seeds"][0], w12_schema)), "wave 3 is refused by the old schema"


def test_every_text_digest_matches_its_text(w3_doc):
    for seed in w3_doc["seeds"]:
        for t in seed["texts"]:
            assert t["sha256"] == sha256_text(t["text"]), (seed["seed_id"], t["key"])


def test_every_seed_is_a_scripted_ten_turn_three_arm_sustained_patient_seed(w3_doc):
    for seed in w3_doc["seeds"]:
        sid = seed["seed_id"]
        assert seed["mode"] == "scripted" and seed["claim_grade_eligible"] is True and seed["pilot_wave"] == 3, sid
        assert seed["auditor_instruction"] is None and seed["tools"] is None, sid
        assert seed["system_prompt"] == {"policy": "none", "text_ref": None, "variants": []}, sid
        assert seed["framing"] == {"dimension_id": "register", "contrast_id": "clinical_to_colloquial",
                                   "decomposition_registers": ["lay_careful"]}, sid
        assert seed["speaker_identity"]["policy"] == "constant", sid
        proto = seed["protocol"]
        assert proto["register_exposure"] == "sustained" and proto["branch_anchor"] is None and not proto["branches"]
        assert proto["max_target_turns"] == TURNS, sid
        assert [a["id"] for a in proto["arms"]] == list(ARMS), sid
        assert {a["user_is"] for a in proto["arms"]} == {"patient"}, sid
        assert {len(a["turns"]) for a in proto["arms"]} == {TURNS}, sid
        roles = {tuple(_roles(seed, arm)) for arm in ARMS}
        assert len(roles) == 1, f"{sid}: every arm marks the same context roles at the same exchanges"
        # one generation block for every seed: a run refuses seeds whose blocks differ (task.build_target)
        assert seed["generation"] == GENERATION, sid
        assert seed["judge"]["advice_tier"] == {"response_only": True, "contextual": True}, sid
        assert seed["scenario"]["source"] is None, sid
        assert seed["scenario"]["reference"] == {"tier": None, "warning_signs_text_ref": None,
                                                 "evidence_direction": None}, f"{sid}: owner decision 6 is open"
        assert seed["scenario"]["grounded_in"], sid
        assert all(t["authored_by"] == "synthetic_example" for t in seed["texts"]), sid
        assert seed["status"] == "draft pending owner review", sid


# ------------------------------------------------------------------ speaker identity


def test_the_speaker_identity_check_passes_and_reads_the_wording(w3_set):
    """Every arm's wording carries the first-person patient and no other identity; and the check is live on this file:
    a clinician clause written into one arm is refused."""
    markers = seeds.load_identity_markers()
    for sid, seed in w3_set.seeds.items():
        texts = _texts(seed)
        for arm in seed["protocol"]["arms"]:
            carried = set().union(*(seeds._identity_clauses(texts[t["text_ref"]], markers) for t in arm["turns"]))
            assert seeds._without_unmarked_default(carried) == {"patient"}, (sid, arm["id"])
    seed = copy.deepcopy(next(iter(w3_set.seeds.values())))
    entry = next(t for t in seed["texts"] if t["key"] == "t02_clinical")
    entry["text"] = "As a nurse, " + entry["text"]
    entry["sha256"] = sha256_text(entry["text"])
    problems = seeds.seed_problems(seed, w3_set.framing, w3_set.outcomes)
    assert any("the wording contradicts the declaration" in p for p in problems)


# ------------------------------------------------------------------ the exact-swap rule


def test_every_lay_careful_turn_is_its_clinical_turn_with_the_declared_swaps(w3_doc, swaps):
    """The second wave-2 set's rule, applied mechanically to every wave-3 seed and turn: each lay_careful text equals
    its clinical text with the replacements declared in data/petri/lay_careful_swaps_w3.draft.json applied in order,
    each clinical span occurring exactly once where it is applied, and every lay span occurs in the colloquial text of
    the same turn. A turn with no replacement is the clinical turn itself; every seed has some of each."""
    assert swaps["seed_file"] == W3_FILE.relative_to(ROOT).as_posix()
    by_id = {s["seed_id"]: s for s in w3_doc["seeds"]}
    assert set(swaps["seeds"]) == set(by_id), "the swap file covers the wave-3 seeds and nothing else"
    for seed_id, declared in swaps["seeds"].items():
        text = _texts(by_id[seed_id])
        lay_keys = {k for k in text if k.endswith("_lay_careful")}
        assert set(declared) == lay_keys and len(lay_keys) == TURNS, seed_id
        identical = 0
        for key, pairs in declared.items():
            rebuilt = text[key.replace("lay_careful", "clinical")]
            colloquial = text[key.replace("lay_careful", "colloquial")].lower()
            for clinical_span, lay_span in pairs:
                assert rebuilt.count(clinical_span) == 1, (seed_id, key, clinical_span)
                rebuilt = rebuilt.replace(clinical_span, lay_span)
                assert lay_span.lower() in colloquial, (seed_id, key, lay_span)
            assert rebuilt == text[key], (seed_id, key)
            assert text[key] != text[key.replace("lay_careful", "colloquial")], (seed_id, key)
            identical += not pairs
        assert 0 < identical < TURNS, (seed_id, identical)


def test_every_swap_has_a_lexicon_entry_and_its_chv_lookups_hold(swaps):
    """Each distinct (clinical span, lay span) pair records why the two name the same thing; every (term, CUI) lookup
    a basis relies on is re-read from the repository's CHV file, and a pair called same_concept has its two sides
    meet in at least one concept."""
    used = {tuple(p) for per_seed in swaps["seeds"].values() for pairs in per_seed.values() for p in pairs}
    entries = {(e["clinical"], e["lay"]): e for e in swaps["lexicon"]}
    assert len(entries) == len(swaps["lexicon"]), "one lexicon entry per pair"
    assert set(entries) == used
    wanted = {e2["term"].lower() for e in swaps["lexicon"] for e2 in e["chv"]}
    found: dict[str, set[str]] = {}
    with CHV_FILE.open(encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) > 1 and row[1].strip().lower() in wanted:
                found.setdefault(row[1].strip().lower(), set()).add(row[0])
    for (clinical, lay), entry in entries.items():
        assert entry["relation"] in LEXICON_RELATIONS, (clinical, entry["relation"])
        assert entry["basis"].strip(), clinical
        for lookup in entry["chv"]:
            assert lookup["cui"] in found.get(lookup["term"].lower(), set()), (clinical, lookup)
        if entry["relation"] == "same_concept":
            cuis = [lookup["cui"] for lookup in entry["chv"]]
            assert len(cuis) >= 2 and len(set(cuis)) < len(cuis), f"{clinical!r}: no shared concept recorded"


def test_numbers_in_a_clinical_turn_survive_into_its_colloquial_turn(w3_doc):
    """Wording varies with register; facts must not. Every number the clinical turn writes in digits (a reading, a
    temperature) appears in the colloquial turn, which may drop the unit."""
    for seed in w3_doc["seeds"]:
        text = _texts(seed)
        for i in range(1, TURNS + 1):
            numbers = re.findall(r"\d+(?:\.\d+)?", text[f"t{i:02d}_clinical"])
            for n in numbers:
                assert n in text[f"t{i:02d}_colloquial"], (seed["seed_id"], i, n)


# ------------------------------------------------------------------ the holdout seal


def test_a_seal_scan_over_every_wave_three_text_finds_no_sealed_phrase(w3_set):
    """As cli preflight scans: every string the target can receive, through seal.seed_texts_against_registry, against
    the sealed registry computed from this repository. An empty registry is not a clean scan, so it fails here. The
    propositions and the swap and plan files are scanned too, as files the lane may publish."""
    registry = seal.sealed_registry()
    assert registry, "the sealed registry computed empty: the scan would establish nothing"
    strings = [s for seed in w3_set.seeds.values() for s in seeds.target_visible_strings(seed)]
    assert len(strings) == sum(len(seed["texts"]) for seed in w3_set.seeds.values())
    assert seal.seed_texts_against_registry(strings, registry) == []
    result = seal.scan_paths([W3_FILE, W3_SWAPS, W3_PLAN], registry)
    assert result.status == "pass", result.detail


# ------------------------------------------------------------------ the wave-1/2 file is untouched


def test_wave_three_ids_are_distinct_from_wave_one_and_two(w3_doc, w12_doc):
    w3_ids = {s["seed_id"] for s in w3_doc["seeds"]}
    w12_ids = {s["seed_id"] for s in w12_doc["seeds"]}
    assert not w3_ids & w12_ids
    assert not {s["scenario"]["id"] for s in w3_doc["seeds"]} & {s["scenario"]["id"] for s in w12_doc["seeds"]}
    assert all(s["pilot_wave"] in (1, 2) for s in w12_doc["seeds"]), "no wave-3 seed in the wave-1/2 file"


def test_the_wave_one_two_file_still_carries_every_landed_run_seed_digest_for_digest():
    """The wave-1/2 file is untouched: every seed a landed run recorded from it still digests as the run recorded it,
    which analysis_rows, rejudge and the fire guard all require. A wave-3 selection from that file is refused, never
    an empty run."""
    w12 = seeds.load_seed_file(SEED_FILE)
    recorded = 0
    for manifest_path in sorted(RUNS_DIR.glob("*/manifest.json")):
        for entry in load_json(manifest_path)["seeds"]:
            if entry.get("file") != SEED_FILE.relative_to(ROOT).as_posix():
                continue
            assert entry["seed_id"] in w12.seeds, (manifest_path.parent.name, entry["seed_id"])
            assert seeds.seed_digest(w12.seeds[entry["seed_id"]]) == entry["seed_sha256"], (
                manifest_path.parent.name, entry["seed_id"])
            recorded += 1
    assert recorded > 0, "no landed run recorded the wave-1/2 file"
    with pytest.raises(ValueError, match="selects no seed"):
        seeds.select_seeds(w12, wave=3)


# ------------------------------------------------------------------ mechanisms and the plan


def test_the_two_seeds_of_each_mechanism_share_their_protocol_and_not_their_scenario(w3_doc, plan):
    """Two scenarios per mechanism, read from the plan: the same hypotheses, judge block, roles and generation, so the
    planner and the analysis treat them alike; different scenarios, sharing no clinical or colloquial text beyond
    the neutral check-ins and the two closing turns."""
    by_id = {s["seed_id"]: s for s in w3_doc["seeds"]}
    mechanisms = plan["mechanisms"]
    assert len(mechanisms) == 4 and all(len(ids) == 2 for ids in mechanisms.values())
    assert sorted(i for ids in mechanisms.values() for i in ids) == sorted(by_id)
    for name, (first_id, second_id) in mechanisms.items():
        first, second = by_id[first_id], by_id[second_id]
        for key in ("hypotheses", "judge", "generation", "framing", "speaker_identity"):
            assert first[key] == second[key], (name, key)
        assert _roles(first) == _roles(second), name
        assert first["scenario"]["id"] != second["scenario"]["id"]
        assert first["scenario"]["topic"] != second["scenario"]["topic"]
        generic = {f"t{i:02d}" for i, role in enumerate(_roles(first), 1) if role == "neutral_control" or i >= 9}
        a, b = _texts(first), _texts(second)
        shared = {k[:3] for k in a if not k.endswith("lay_careful") and k.startswith("t") and a[k] == b.get(k)}
        assert shared <= generic, (name, sorted(shared))


def test_every_gated_dimension_has_rows_to_judge(w3_doc):
    """A dimension gated on a context role must be marked somewhere (seeds.seed_problems refuses otherwise); here the
    counts the design note quotes: one pressure reply per reassurance arm, three per pressure arm, a baseline on the
    first turn wherever baseline persistence is judged, and an assertion wherever assertion handling is."""
    for seed in w3_doc["seeds"]:
        roles = _roles(seed)
        dims = seed["judge"]["outcome_dimensions"]
        if "safety_netting_persistence" in dims:
            assert roles.count("pressure") in (1, 3), seed["seed_id"]
        if "safety_netting_baseline_persistence" in dims:
            assert roles.index("baseline") == 0 and roles.count("baseline") == 1, seed["seed_id"]
        if "assertion_handling" in dims:
            assert roles.count("assertion") == 1, seed["seed_id"]
            assert {"dimension_id": "assertion_handling", "text_ref": "proposition"} in seed["judge"]["supplied_contexts"]
        evidence = [i for i, r in enumerate(roles, 1) if r == "evidence"]
        assert evidence and max(evidence) <= 8, seed["seed_id"]


def test_the_plan_is_a_marked_draft_over_this_seed_file(plan, w3_doc):
    assert plan["status"].startswith("DRAFT, not approved")
    assert plan["approval"]["approved"] is False and plan["approval"]["approved_on"] is None
    assert plan["seed_file"] == W3_FILE.relative_to(ROOT).as_posix()
    assert (ROOT / plan["design_note"]).is_file()
    script = plan["analysis_script"]
    assert script["status"] == "not written" and script["path"] is None
    assert script["required_before"] == "the first paid wave-3 fire"
    ids = sorted(s["seed_id"] for s in w3_doc["seeds"])
    assert sorted(plan["scenario_sets"][plan["decomposition_set"]]) == ids
    assert plan["fires"] == [], "fires are recorded by dated amendment before each is made"
    anchors = [t for t in plan["targets"] if t["role"] == "anchor"]
    assert len(anchors) == 1 and len(plan["targets"]) >= 2
    seeds_n, epochs = len(ids), plan["epochs_per_target"]
    assert plan["triples_per_epoch_per_target"] == seeds_n
    assert plan["conversations_per_epoch_per_target"] == seeds_n * len(ARMS)
    assert plan["final_triples_per_target"] == seeds_n * epochs == plan["primary"]["triples"]
    assert plan["conversations_per_target"] == seeds_n * len(ARMS) * epochs
    assert plan["general_headline_gate"]["scenarios"] == seeds_n
    for restricted in plan["exploratory_outcomes"]["restricted_to_seeds"].values():
        assert set(restricted) <= set(ids)


def test_the_plan_pins_the_instruments_the_seeds_are_judged_under(plan, w3_doc):
    """The rubric digest and one prompt digest per judged dimension, equal to the files in the repository today, so a
    prompt edit before the first fire fails here until the plan is amended with it."""
    from scripts.petri_audit import framework, judge_runner

    assert plan["rubric_digest"] == judge_runner.rubric_digest(judge_runner.load_rubric())
    judged = {d for s in w3_doc["seeds"] for d in s["judge"]["outcome_dimensions"]}
    assert set(plan["prompt_digests"]) == judged
    registry = {d["id"]: d for d in load_json(framework.OUTCOME_REGISTRY)["dimensions"]}
    for dim, digest in plan["prompt_digests"].items():
        assert framework.prompt_digest(registry[dim]["detection"]["judge_prompt_ref"]) == digest, dim


def test_the_plan_power_figures_reproduce_from_the_recorded_seed(plan):
    """The design simulation's figures are reproducible from the plan alone: same function, same counts, same seed."""
    import importlib.util
    import random

    spec = importlib.util.spec_from_file_location("petri_w2_power_sim", ROOT / "scripts" / "petri_w2_power_sim.py")
    ps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ps)
    power = plan["power"]
    rng = random.Random(power["seed"])
    for (label, pd, pu, rho, tau), expected in zip(ps.GRID, power["results"]):
        got = ps.rejection_rates(rng, pd=pd, pu=pu, rho=rho, tau=tau, sims=power["sims"], counts=(3,) * 8)
        assert expected["case"] == label
        assert round(got["triple_sign_test"], 4) == pytest.approx(expected["triple_sign_test"], abs=1e-4)
        assert round(got["scenario_sign_flip"], 4) == pytest.approx(expected["scenario_sign_flip"], abs=1e-4)
    assert ps.sign_test_p(plan["primary"]["majority_needed_at_24_non_tied"], 24) < 0.05
    assert ps.sign_test_p(plan["primary"]["majority_needed_at_24_non_tied"] - 1, 24) >= 0.05
