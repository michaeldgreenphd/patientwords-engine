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
import functools
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path

import pytest

# The checkout's root is on sys.path through pytest's `pythonpath` setting (pyproject.toml), ahead of installed copies.
from scripts.build_patient_lexicon import CONCEPTS, INCORRECT, STOP, read_incorrect, read_stop_cuis
from scripts.petri_audit import cli, seal, seeds
from scripts.petri_audit.framework import SEED_FILE, load_json, sha256_text, validate

ROOT = Path(__file__).resolve().parents[1]
W3_FILE = ROOT / "docs" / "framework" / "petri_seeds_w3.draft.json"
W3_SWAPS = ROOT / "data" / "petri" / "lay_careful_swaps_w3.draft.json"
W3_PLAN = ROOT / "data" / "petri" / "w3_register_contrast_plan.json"
CHV_DIR = ROOT / "data" / "chv"
CHV_FILE = CHV_DIR / CONCEPTS
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


def test_validate_seeds_accepts_the_file_by_path_and_by_wave(capsys, w3_set):
    """The CLI path the workflow runs (`validate-seeds --seeds "$SEEDS_FILE"`), with and without --wave 3; nothing in
    the CLI refuses a third wave. Each run's output is read on its own, so a run that drops a seed cannot be covered by
    a run that reports one twice. Only the per-seed result lines (`<seed id>: <status>; ...`) are read, as (seed id,
    status) pairs: every seed of the file must appear exactly once, as ok, and a line of any other shape is ignored."""
    for wave in ([], ["--wave", "3"]):
        assert cli.main(["validate-seeds", "--seeds", str(W3_FILE), *wave]) == 0, wave
        reported = sorted(re.findall(r"^(\S+): (\w+);", capsys.readouterr().out, flags=re.MULTILINE))
        assert reported == sorted((seed_id, "ok") for seed_id in w3_set.seeds), wave


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
            # marked_identities drops the unmarked default per turn, where seed_problems drops it over the arm; the
            # verdict is the same: a clinician or caregiver clause in any turn leaves either set unequal to {patient}.
            carried = set().union(*(seeds.marked_identities(texts[t["text_ref"]], markers) for t in arm["turns"]))
            assert carried == {"patient"}, (sid, arm["id"])
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


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _token_matches(a: str, b: str) -> bool:
    """Codebook rule L0 ignores inflection and part of speech: two tokens match when equal, or when both have at least
    four letters and share a prefix no more than two letters shorter than the shorter token (dark / darkness,
    grow / grown, drama / dramatic). Medical examples stay in the data files (AGENTS.md hard conventions)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    common = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return common >= max(4, min(len(a), len(b)) - 2)


def _term_in_span(term: str, span: str) -> bool:
    """Every token of a CHV lookup term matches some token of the span, inflection aside."""
    span_tokens = _tokens(span)
    return all(any(_token_matches(t, s) for s in span_tokens) for t in _tokens(term))


def _chv_rows(terms: Iterable[str]) -> dict[tuple[str, str], bool]:
    """(term, CUI) -> whether CHV has a row for it that scripts/build_patient_lexicon.py would use: not marked
    disparaged (column 8 of the flat file), not a published incorrect mapping, and not a stop concept."""
    return _chv_rows_cached(frozenset(t.lower() for t in terms))


@functools.lru_cache(maxsize=None)
def _chv_rows_cached(terms: frozenset[str]) -> dict[tuple[str, str], bool]:
    incorrect, stop = read_incorrect(CHV_DIR / INCORRECT), read_stop_cuis(CHV_DIR / STOP)
    rows: dict[tuple[str, str], bool] = {}
    with CHV_FILE.open(encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) > 7 and row[1].strip().lower() in terms:
                key = (row[1].strip().lower(), row[0].strip())
                usable = row[7].strip().lower() != "yes" and key[::-1] not in incorrect and key[1] not in stop
                rows[key] = rows.get(key, False) or usable
    return rows


def test_the_l0_token_match_is_neither_too_loose_nor_too_strict():
    """The matcher on everyday words, so no medical term is written in Python: an inflection, a noun against its
    adjective and a multi-word term match; a different word, a short near-miss and a short shared prefix do not."""
    assert _term_in_span("grow up", "grown up") and _term_in_span("darkness", "dark")
    assert _term_in_span("kindness of strangers", "kind of strangers")
    assert not _term_in_span("grow up", "grown out") and not _term_in_span("table leg", "table top")
    assert not _token_matches("to", "too") and not _token_matches("garden", "gate")


def test_every_swap_has_a_lexicon_entry_and_its_chv_lookups_hold(swaps):
    """Each distinct (clinical span, lay span) pair records why the two name the same thing; every (term, CUI) lookup
    a basis relies on is re-read from the repository's CHV file. A pair called same_concept must have two lookups of
    different terms, one whose term is in the clinical span and one whose term is in the lay span, sharing a CUI, both
    on CHV rows the lexicon builder would use: lookups of one side only (which rule L0's matching of an adjective
    against its noun can place in both spans), or a disparaged or incorrect mapping, do not make the two spans one
    concept."""
    used = {tuple(p) for per_seed in swaps["seeds"].values() for pairs in per_seed.values() for p in pairs}
    entries = {(e["clinical"], e["lay"]): e for e in swaps["lexicon"]}
    assert len(entries) == len(swaps["lexicon"]), "one lexicon entry per pair"
    assert set(entries) == used
    rows = _chv_rows({lookup["term"].lower() for e in swaps["lexicon"] for lookup in e["chv"]})
    for (clinical, lay), entry in entries.items():
        assert entry["relation"] in LEXICON_RELATIONS, (clinical, entry["relation"])
        assert entry["basis"].strip(), clinical
        for lookup in entry["chv"]:
            assert (lookup["term"].lower(), lookup["cui"]) in rows, (clinical, lookup)
        if entry["relation"] == "same_concept":
            usable = [lk for lk in entry["chv"] if rows[(lk["term"].lower(), lk["cui"])]]
            witnesses = [(a["term"], b["term"]) for a in usable for b in usable
                         if a["cui"] == b["cui"] and a["term"].lower() != b["term"].lower()
                         and _term_in_span(a["term"], clinical) and _term_in_span(b["term"], lay)]
            assert witnesses, (f"{clinical!r} / {lay!r}: no non-disparaged concept shared by two lookups of "
                               "different terms, one in each span")


def test_the_same_concept_check_refuses_one_sided_and_disparaged_lookups(swaps):
    """The check above is live for every same_concept entry: its lookups replaced by two copies of its clinical-side
    lookup fail it, including the entries whose clinical term also matches the lay span under rule L0; and an entry
    resting on the lexicon's disparaged lookup fails it too."""
    same = [e for e in swaps["lexicon"] if e["relation"] == "same_concept"]
    assert same
    for entry in same:
        clinical_side = next(lk for lk in entry["chv"] if _term_in_span(lk["term"], entry["clinical"]))
        one_sided = copy.deepcopy(swaps)
        target = next(e for e in one_sided["lexicon"] if (e["clinical"], e["lay"]) == (entry["clinical"], entry["lay"]))
        target["chv"] = [clinical_side, clinical_side]
        with pytest.raises(AssertionError, match="no non-disparaged concept"):
            test_every_swap_has_a_lexicon_entry_and_its_chv_lookups_hold(one_sided)
    assert any(_term_in_span(lk["term"], e["lay"]) for e in same for lk in e["chv"]
               if _term_in_span(lk["term"], e["clinical"])), "the L0 case the loop exists for is present"
    disparaged = copy.deepcopy(swaps)
    rows = _chv_rows({lk["term"] for e in swaps["lexicon"] for lk in e["chv"]})
    red = next(e for e in disparaged["lexicon"] if any(not rows[(lk["term"].lower(), lk["cui"])] for lk in e["chv"]))
    red["relation"] = "same_concept"
    with pytest.raises(AssertionError, match="no non-disparaged concept"):
        test_every_swap_has_a_lexicon_entry_and_its_chv_lookups_hold(disparaged)


def test_paraphrase_and_unverified_relations_match_their_bases(swaps):
    """A basis that says its lay span is not in CHV, or that it rests on general knowledge or anatomy, cannot be a
    same_concept or a paraphrase: the _readme's paraphrase is built from CHV's consumer words."""
    for entry in swaps["lexicon"]:
        basis = entry["basis"].lower()
        if "unresolved" in basis or "rests on anatomy" in basis:
            assert entry["relation"] == "unverified", entry["clinical"]
        if f"'{entry['lay'].lower()}' is not in chv" in basis or "nor the lay span is in chv" in basis:
            assert entry["relation"] not in {"same_concept", "paraphrase"}, entry["clinical"]


def test_every_term_a_basis_says_chv_lacks_is_absent_from_chv(swaps):
    """A basis that says CHV lacks a term lists the term under not_in_chv, and the CHV file is read to confirm it:
    one basis said CHV lacked a term the file holds as a row of its own. A listed term is never also a lookup."""
    listed = {t.lower() for e in swaps["lexicon"] for t in e.get("not_in_chv", [])}
    assert listed, "no absence claim is recorded: the check establishes nothing"
    present = sorted({term for term, _ in _chv_rows(listed)})
    assert not present, f"CHV holds terms a basis says it lacks: {present}"
    for entry in swaps["lexicon"]:
        if "not in chv" in entry["basis"].lower():
            assert entry.get("not_in_chv"), f"{entry['clinical']!r}: an absence claim without its terms"
        lookups = {lk["term"].lower() for lk in entry["chv"]}
        assert not lookups & {t.lower() for t in entry.get("not_in_chv", [])}, entry["clinical"]
    held = next(lk["term"] for e in swaps["lexicon"] for lk in e["chv"])
    assert _chv_rows({held}), "the reader finds a term CHV holds, so an empty result above is a real absence"


def test_every_codebook_rule_the_swaps_file_cites_is_quoted_in_it(swaps):
    """The stimulus pilot's codebook is in pull request #69 and not on main, so the swaps file defines every rule its
    bases or its _readme cite by quoting it, the rules named inside those quotations included."""
    readme = swaps["_readme"]
    assert "pull request #69" in readme
    quoted = set(re.findall(r"\b([LR]\d): '", readme))
    cited = set(re.findall(r"\b([LR]\d)\b", readme + " " + " ".join(e["basis"] for e in swaps["lexicon"])))
    assert cited and cited <= quoted, f"cited but not quoted: {sorted(cited - quoted)}"


_NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split())} | {"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60"}


def _numbers(text: str) -> list[str]:
    """Every number a turn states, as digits: digit tokens whole (so 1 is not found inside 10), number words mapped."""
    lowered = text.lower()
    digits = re.findall(r"\d+(?:\.\d+)?", lowered)
    words = [_NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", lowered) if w in _NUMBER_WORDS]
    return sorted(digits + words)


def test_numbers_in_a_clinical_turn_are_the_numbers_of_its_other_arms(w3_doc):
    """Wording varies with register; facts must not. The numbers a turn states, digits or words, are the same multiset
    in all three arms (the colloquial arm may write two as 2 and drop the unit)."""
    for seed in w3_doc["seeds"]:
        text = _texts(seed)
        for i in range(1, TURNS + 1):
            clinical = _numbers(text[f"t{i:02d}_clinical"])
            for arm in ("lay_careful", "colloquial"):
                assert _numbers(text[f"t{i:02d}_{arm}"]) == clinical, (seed["seed_id"], i, arm)
    assert _numbers("for 10 days") != _numbers("for 1 day"), "a digit inside a longer number is not a match"


def _occurrences(text: str, terms: list[str]) -> list[str]:
    """Each listed term as often as the text names it, as a whole word or phrase."""
    lowered = text.lower()
    return sorted(t for t in terms for _ in re.finditer(r"(?<![\w&])" + re.escape(t) + r"(?![\w&])", lowered))


def test_every_arm_of_a_turn_names_the_same_care_settings(w3_doc, swaps):
    """Care-setting words are not swapped (the swaps file's _readme), so the three arms of a turn name the same ones;
    otherwise the style contrast (colloquial against lay_careful) would carry a vocabulary change. The terms are read
    from the swaps file, and the check is live: a colloquial turn naming a different setting fails it."""
    terms = swaps["care_setting_terms"]
    assert terms
    seen = 0
    for seed in w3_doc["seeds"]:
        text = _texts(seed)
        for i in range(1, TURNS + 1):
            found = {arm: _occurrences(text[f"t{i:02d}_{arm}"], terms) for arm in ARMS}
            assert len({tuple(v) for v in found.values()}) == 1, (seed["seed_id"], i, found)
            seen += bool(found["clinical"])
    assert seen > 0, "no turn names a care setting: the check establishes nothing"
    assert _occurrences(f"waiting in {terms[0]}", terms) != _occurrences(f"waiting in {terms[1]}", terms)


def test_every_arm_of_a_turn_keeps_the_terms_the_lay_arm_keeps(w3_doc, swaps):
    """A medical term that is already the plain word is not swapped, and the colloquial arm must not reword it either,
    or the style contrast would carry a change of term: every term in the swaps file's kept_terms is named as often
    in each arm of a turn. Every listed term occurs in some clinical turn, none is part of a swapped span, and the
    check is live: a colloquial turn that rewords a kept term fails it."""
    terms = swaps["kept_terms"]
    swapped_spans = {span for e in swaps["lexicon"] for span in (e["clinical"], e["lay"])}
    assert terms and not [span for span in swapped_spans if _occurrences(span, terms)], "a kept term is swapped"
    seen: set[str] = set()
    for seed in w3_doc["seeds"]:
        text = _texts(seed)
        for i in range(1, TURNS + 1):
            found = {arm: _occurrences(text[f"t{i:02d}_{arm}"], terms) for arm in ARMS}
            assert len({tuple(v) for v in found.values()}) == 1, (seed["seed_id"], i, found)
            seen |= set(found["clinical"])
    assert seen == set(terms), f"listed but never used: {sorted(set(terms) - seen)}"
    assert _occurrences(f"i have {terms[0]}", terms) != _occurrences("i have it", terms)


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


def test_every_exploratory_test_in_the_holm_family_can_reject(plan):
    """A per-target test whose smallest attainable exact two-sided sign-test p (2 / 2^n at n triples) cannot pass
    Holm's first threshold (alpha / family size) would report 'not significant' whatever the data showed; such an
    outcome is described, not tested (referral_specificity: 6 triples per target, 0.03125 against 0.0125 in a family
    of four)."""
    exploratory = plan["exploratory_outcomes"]
    family = exploratory["family"]
    restricted = exploratory["restricted_to_seeds"]
    for outcome in family:
        n = len(restricted.get(outcome, plan["scenario_sets"][plan["decomposition_set"]])) * plan["epochs_per_target"]
        assert 2 / 2 ** n < plan["alpha"] / len(family), (outcome, n)
    assert "referral_specificity" in restricted and "referral_specificity" not in family
    assert set(exploratory["referral_specificity"]) == {"per_target", "across_targets", "wave2"}
    assert "not significant after Holm" in exploratory["referral_specificity"]["wave2"]


def test_the_plan_fixes_one_judge_route_for_every_fire(plan):
    """The wave-2 analysis refuses runs whose judge_model differ (load_runs); the wave-3 plan says so before the cost
    guidance tempts a split route, and names the refusal among the wave-2 code to carry over."""
    assert "one judge route" in plan["judge"]["one_route"]
    assert any(rule.startswith("No pooling across judge routes") for rule in plan["rules"])
    assert any("judge_model" in item for item in plan["analysis_script"]["wave2_assumptions_to_change"])


def test_the_judge_route_decides_which_targets_are_judged_in_their_own_fires(plan):
    """A fire whose target and judge bill different channels is refused (fire_trigger.petri_params_problems before
    the push, and the workflow's budget gate), so under one judge route a target is judged in its own fire only
    through a target spec on the judge's channel. The plan's list of routes that judge every registered target that
    way is recomputed with the lane's own classifiers (spend.billing_channel, spend.judge_billing_channel), so a target
    or route added without updating it fails here; the route itself is set by the dated approval."""
    from scripts.petri_audit import spend

    judge = plan["judge"]
    routes = judge["routes"]
    assert len(routes) == 2 and judge["judge_model"] in (None, *routes)
    if plan["approval"]["approved"]:
        assert judge["judge_model"] in routes, "the dated approval records the one judge route"
    channels = {route: spend.judge_billing_channel(route) for route in routes}
    assert sorted(channels.values()) == ["anthropic", "openrouter"], "the two routes bill the two channels"
    every = sorted(route for route in routes if all(
        any(spend.billing_channel([spec]) == channels[route] for spec in target["target_specs"])
        for target in plan["targets"]))
    assert every == sorted(judge["routes_judging_every_target_in_its_own_fire"])


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
    assert len(power["results"]) == len(ps.GRID), "one recorded result per parameter set"
    for (label, pd, pu, rho, tau), expected in zip(ps.GRID, power["results"], strict=True):
        got = ps.rejection_rates(rng, pd=pd, pu=pu, rho=rho, tau=tau, sims=power["sims"], counts=(3,) * 8)
        assert expected["case"] == label
        assert round(got["triple_sign_test"], 4) == pytest.approx(expected["triple_sign_test"], abs=1e-4)
        assert round(got["scenario_sign_flip"], 4) == pytest.approx(expected["scenario_sign_flip"], abs=1e-4)
    assert ps.sign_test_p(plan["primary"]["majority_needed_at_24_non_tied"], 24) < 0.05
    assert ps.sign_test_p(plan["primary"]["majority_needed_at_24_non_tied"] - 1, 24) >= 0.05


# ------------------------------------------------------------------ the proposed physician realism gate

W3_DESIGN = ROOT / "docs" / "petri_wave3_design.md"
PREREG = ROOT / "docs" / "preregistration_advice.md"
PROTOCOL = ROOT / "docs" / "verification_protocol.md"
FIRE_PLAN = ROOT / "docs" / "advice_fire_plan_20261002.md"
NUMBER_WORDS = dict(enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split()))


def _power_sim():
    import importlib.util

    spec = importlib.util.spec_from_file_location("petri_w2_power_sim", ROOT / "scripts" / "petri_w2_power_sim.py")
    ps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ps)
    return ps


def _t_quantile(p: float, df: int) -> float:
    """Student's t quantile: bisection on the CDF, the CDF by Simpson's rule on the density from 0 (the dev install
    has no scipy). Accurate to far better than the three decimals the plan records."""
    import math

    const = math.gamma((df + 1) / 2) / (math.sqrt(df * math.pi) * math.gamma(df / 2))

    def cdf(x: float, steps: int = 2000) -> float:
        h = x / steps
        f = [const * (1 + (i * h) ** 2 / df) ** (-(df + 1) / 2) for i in range(steps + 1)]
        return 0.5 + h / 3 * (f[0] + f[-1] + 4 * sum(f[1:-1:2]) + 2 * sum(f[2:-1:2]))

    lo, hi = 0.0, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < p else (lo, mid)
    return (lo + hi) / 2


def _rated_scripts(gate: dict) -> tuple[dict, dict[str, dict]]:
    """The round's bundle, checked against the hashes the gate records, and its script items by seed id."""
    rnd = gate["round"]
    bundle_path = ROOT / rnd["bundle"]
    assert hashlib.sha256(bundle_path.read_bytes()).hexdigest() == rnd["bundle_sha256"]
    bundle = load_json(bundle_path)
    assert bundle["bundle_id"] == rnd["bundle_id"]
    assert bundle["questions_sha256"] == rnd["questions_sha256"]
    script_items = [i for i in bundle["items"] if i["question_set"] == rnd["question_set"]]
    by_seed = {i["provenance"]["source_id"]: i for i in script_items}
    assert len(by_seed) == len(script_items), "one item per seed"
    return bundle, by_seed


def _rated_seed_mismatches(by_seed: dict[str, dict], seeds_by_id: dict[str, dict]) -> list[str]:
    """Seeds the bundle rated that the seed file no longer holds, or holds with another digest than the one the bundle
    recorded when physicians were given them to rate."""
    return sorted(sid for sid, item in by_seed.items()
                  if sid not in seeds_by_id or seeds.seed_digest(seeds_by_id[sid]) != item["provenance"]["seed_sha256"])


def _check_realism_gate(plan: dict, seeds_by_id: dict[str, dict]) -> None:
    """The gate block against its bundle, and, once approved, against the seed file. The bundle must be the file it
    hashes to and hold one script item per seed id, with gate keys that are the import's own keys for the per-version
    five-point question, one per arm, and flag_adds the item's other five-point questions, which the import's flag
    also covers. Those checks compare the block with the bundle it names, a committed file that is never rewritten,
    so they bind nothing else. Every comparison with the seed file (that the bundle rated each of its seeds, from its
    path, on its current digests: item_match) runs only once the owner has approved the gate, which the owner did on
    2026-10-05. A gate that is only proposed leaves the draft seeds free to be edited, added or removed, because the
    suite must not enforce a rule nobody has approved."""
    from scripts.import_verification_ratings import is_five_point, item_keys

    gate = plan["physician_realism_gate"]
    approval = gate["approval"]
    if approval["approved"]:
        assert approval["approved_by"] and approval["approved_on"], "an approval names who approved it and when"
        assert gate["status"].startswith("APPROVED") and approval["record"], "an approval says where it is recorded"
    else:
        assert gate["status"].startswith("PROPOSED") and "not in force" in gate["status"]
        assert approval["approved_by"] is None and approval["approved_on"] is None
    bundle, by_seed = _rated_scripts(gate)
    for item in by_seed.values():
        five_point = {k: spec for k, spec in item_keys(item, bundle["questions"]).items() if is_five_point(spec.scale)}
        assert sorted(k for k, spec in five_point.items() if spec.arm is not None) == sorted(gate["gate_keys"])
        assert sorted({spec.arm for spec in five_point.values() if spec.arm is not None}) == sorted(ARMS)
        assert sorted(k for k, spec in five_point.items() if spec.arm is None) == sorted(gate["flag_adds"])
        assert sorted(gate["min_answers_keys"]) == sorted(five_point), "every five-point question the gate reads has the floor"
    if approval["approved"]:
        for seed_id, item in by_seed.items():
            assert item["provenance"]["source_path"] == plan["seed_file"], seed_id
        unrated = sorted(set(seeds_by_id) - set(by_seed))
        mismatched = _rated_seed_mismatches(by_seed, seeds_by_id)
        assert not unrated and not mismatched, (
            f"seed(s) {unrated} of the seed file not rated in the round's bundle, and rated seed(s) {mismatched} "
            "edited or removed since it was exported: a script can pass only after a round rates its current text "
            "(item_match)")
    assert gate["not_flagged"] is True
    assert 2 <= gate["min_complete_ratings"] and 2 <= gate["min_answers_per_key"]
    assert 1 < gate["min_median"] <= 5
    closes = gate["round"]["closes"]
    assert "min_complete_ratings" in closes and "min_answers_per_key" in closes, \
        "the round closes on the rule's own counts, so it cannot close with items the rule then drops"


def test_the_realism_gate_is_approved_and_names_the_rated_scripts_and_their_realism_keys(plan, w3_set):
    """The gate (docs/petri_wave3_design.md section 13), approved by the owner on 2026-10-05, reads one round's import
    summary and the bundle it names; _check_realism_gate holds the checks, and with the approval recorded they include
    the seed file (item_match). It is not yet applied: no selection. Its values are the owner's choices that A6.9's
    approval record quotes (median of 3 or more, minimum 2, closing date 2026-10-31, floor 6), checked against the prose
    in test_the_gate_reads_the_same_in_the_plan_a69_section_13_and_the_protocol; a dated amendment that changes one
    changes this line with it."""
    gate = plan["physician_realism_gate"]
    assert gate["approval"]["approved"] is True and gate["approval"]["approved_on"] == "2026-10-05"
    assert gate["selection"] is None, "the selection is set by a dated amendment after the gate is applied"
    chosen = {"min_complete_ratings": 2, "min_answers_per_key": 2, "min_median": 3, "min_scenarios": 6}
    assert {k: gate[k] for k in chosen} == chosen
    assert gate["round"]["closing_date"] == "2026-10-31"
    _check_realism_gate(plan, w3_set.seeds)


def test_a_changed_seed_file_fails_the_gate_check_only_once_the_gate_is_approved(plan, w3_set):
    """Editing, adding or removing a draft seed is allowed while the gate is proposed and caught, by seed id, once
    it is approved (item_match). Both states are built as copies of the plan, so the test exercises the proposed state
    although the plan records the approval of 2026-10-05; the seed changes are made to copies as well. Whether the
    real seed file matches the bundle is test_the_realism_gate_is_approved_and_names_the_rated_scripts_and_their_
    realism_keys's check."""
    gate = plan["physician_realism_gate"]
    _bundle, by_seed = _rated_scripts(gate)
    rated = sorted(set(by_seed) & set(w3_set.seeds))
    before = _rated_seed_mismatches(by_seed, w3_set.seeds)
    base = (rated or sorted(w3_set.seeds))[0]
    new_id = f"{base}-new"
    cases = [({**copy.deepcopy(w3_set.seeds), new_id: copy.deepcopy(w3_set.seeds[base])}, new_id)]
    if rated:   # editing or removing needs a seed the bundle rated
        first, last = rated[0], rated[-1]
        edited = copy.deepcopy(w3_set.seeds)
        edited[first]["texts"][0]["text"] += " Edited."
        assert _rated_seed_mismatches(by_seed, edited) == sorted({*before, first})
        cases += [(edited, first), ({k: v for k, v in w3_set.seeds.items() if k != last}, last)]
    proposed, approved = copy.deepcopy(plan), copy.deepcopy(plan)
    proposed["physician_realism_gate"]["status"] = "PROPOSED, not in force (a copy made for this test)"
    proposed["physician_realism_gate"]["approval"].update(approved=False, approved_by=None, approved_on=None)
    approved["physician_realism_gate"]["status"] = "APPROVED (a copy made for this test)"
    approved["physician_realism_gate"]["approval"].update(approved=True, approved_by="owner", approved_on="2026-10-05",
                                                          record="this test")
    if not before and set(w3_set.seeds) == set(by_seed):
        _check_realism_gate(approved, w3_set.seeds)   # the approved check passes on a seed file the bundle rated
    for changed, named in cases:
        _check_realism_gate(proposed, changed)
        with pytest.raises(AssertionError, match=re.escape(f"'{named}'")):
            _check_realism_gate(approved, changed)


def _gate_decision(row: dict, gate: dict) -> str:
    """The rule as the plan's gate block states it, applied to one item row of the import summary: 'not enough
    ratings', 'rated unrealistic' or 'passes'. A reference for the program that will apply the gate."""
    five_point = row["five_point"]
    if row["ratings_complete"] < gate["min_complete_ratings"] or any(
            five_point[k]["n"] < gate["min_answers_per_key"] for k in gate["min_answers_keys"]):
        return "not enough ratings"
    if any(five_point[k]["median"] < gate["min_median"] for k in gate["gate_keys"]) or (gate["not_flagged"]
                                                                                       and row["flagged"]):
        return "rated unrealistic"
    return "passes"


def _summary_row(answers: dict[str, tuple]) -> dict:
    """An item row as the import writes it, from each five-point key's answers in complete ratings ("cant_judge" for
    Can't judge), with five_point and flagged computed by the import's own five_point_stats."""
    from scripts.import_verification_ratings import five_point_stats

    five_point = {k: five_point_stats(v) for k, v in answers.items()}
    return {"ratings_complete": len(next(iter(answers.values()))), "five_point": five_point,
            "flagged": any(s["majority_low"] for s in five_point.values())}


def test_the_realism_gate_needs_two_answers_on_every_question_it_reads(plan):
    """The gate reads a script's course-of-events question through the flag, and the flag is computed over numeric
    answers only. So with two physicians and one Can't judge on course_plausible, the other physician's answer alone
    would decide the flag: a 1 would drop the scenario and a 5 would pass it. The answer floor therefore covers every
    question the gate reads, flag_adds as well as gate_keys (Codex review of PR #87, 2026-10-05), and such a scenario
    is 'not enough ratings'. The other cases are the worked examples of A6.9 and section 13 at a median of 3."""
    gate = plan["physician_realism_gate"]
    assert sorted(gate["min_answers_keys"]) == sorted([*gate["gate_keys"], *gate["flag_adds"]])
    fine = {k: (4, 4) for k in gate["gate_keys"]}
    cases = [
        ({**fine, "course_plausible": ("cant_judge", 5)}, "not enough ratings"),
        ({**fine, "course_plausible": ("cant_judge", 1)}, "not enough ratings"),
        ({**fine, "realism.clinical": ("cant_judge", 5), "course_plausible": (4, 4)}, "not enough ratings"),
        ({**fine, "course_plausible": (4,)}, "not enough ratings"),
        ({**fine, "course_plausible": (3, 4)}, "passes"),
        ({k: (1, 5) for k in gate["gate_keys"]} | {"course_plausible": (1, 5)}, "passes"),
        ({**fine, "realism.colloquial": (2, 4), "course_plausible": (3, 3)}, "passes"),
        ({**fine, "realism.clinical": (2, 3), "course_plausible": (4, 4)}, "rated unrealistic"),
        ({**fine, "course_plausible": (1, 2)}, "rated unrealistic"),
        ({**fine, "course_plausible": (2, 5, 1)} | {k: (4, 4, 4) for k in gate["gate_keys"]}, "rated unrealistic"),
    ]
    for answers, expected in cases:
        assert _gate_decision(_summary_row(answers), gate) == expected, answers


def test_the_realism_gate_floor_and_counts_follow_from_the_plan(plan):
    """min_scenarios is the fewest scenario means whose sign-flip gate can reach alpha (its smallest p is 2/2^S with
    no zero mean), and each row of counts_by_scenarios_passing is the plan's own arithmetic at S seeds: 3S triples,
    the sign test's majority, the most zero scenario means at which the gate can still reach alpha (by the power
    simulation's own sign_flip_p), the t multiplier of the interval across scenario means, and power.plug_in's exact
    method at 3S triples with that block's recorded q and p. referral_by_referral_seeds_passing is the referral
    outcome's counts at each number of passing referral seeds. The eight-seed and two-referral-seed rows are the plan
    as drafted, wording included."""
    from fractions import Fraction
    from math import comb

    ps = _power_sim()
    gate = plan["physician_realism_gate"]
    alpha = plan["alpha"]
    floor = min(s for s in range(1, 64) if 2 / 2 ** s < alpha)
    assert gate["min_scenarios"] == floor
    all_seeds = len(plan["scenario_sets"][plan["decomposition_set"]])
    epochs = plan["epochs_per_target"]
    plug = plan["power"]["plug_in"]["results"]
    names = ("primary", "exchanges_6_10", "decomposition_paired_difference_before_holm")
    rates = [(float(Fraction(r["q"])), float(Fraction(r["p"]))) for r in plug[:len(names)]]

    def plug_in(n: int, q: float, p: float) -> float:
        return sum(comb(n, big) * q ** big * (1 - q) ** (n - big)
                   * sum(comb(big, k) * p ** k * (1 - p) ** (big - k)
                         for k in range(big + 1) if ps.sign_test_p(k, big) < alpha)
                   for big in range(n + 1))

    rows = gate["counts_by_scenarios_passing"]
    assert [r["scenarios"] for r in rows] == list(range(all_seeds, floor - 1, -1))
    for row in rows:
        s = row["scenarios"]
        n = s * epochs
        assert row["triples_per_target"] == n
        assert row["conversations_per_target"] == n * len(ARMS)
        need = row["majority_needed_non_tied"]
        assert ps.sign_test_p(need, n) < alpha <= ps.sign_test_p(need - 1, n), s
        assert row["general_headline_gate_smallest_p"] == f"2/{2 ** s}"
        z = row["gate_reachable_with_zero_means_at_most"]
        assert ps.sign_flip_p([0.0] * z + [1.0] * (s - z)) < alpha <= ps.sign_flip_p([0.0] * (z + 1) + [1.0] * (s - z - 1))
        assert row["effect_size_t_975"] == round(_t_quantile(0.975, s - 1), 3), s
        for name, (q, p) in zip(names, rates, strict=True):
            assert row["plug_in_power"][name] == pytest.approx(round(plug_in(n, q, p), 3), abs=1e-9), (s, name)
    full = rows[0]
    assert full["triples_per_target"] == plan["final_triples_per_target"]
    assert full["majority_needed_non_tied"] == plan["primary"]["majority_needed_at_24_non_tied"]
    assert [full["plug_in_power"][name] for name in names] == [r["power"] for r in plug[:len(names)]]
    interval = plan["effect_size"]["reported"][2]
    assert f"t(0.975, {all_seeds - 1})" in interval and f"t = {full['effect_size_t_975']}" in interval
    assert plan["general_headline_gate"]["smallest_attainable_p"].startswith(full["general_headline_gate_smallest_p"])

    referral = plan["exploratory_outcomes"]["restricted_to_seeds"]["referral_specificity"]
    pooled_over = len(plan["targets"])
    ref_rows = gate["referral_by_referral_seeds_passing"]
    assert [r["referral_seeds"] for r in ref_rows] == list(range(len(referral), -1, -1))
    for row in ref_rows:
        n = row["referral_seeds"] * epochs
        pooled = n * pooled_over
        assert row["triples_per_target"] == n and row["pooled_triples"] == pooled
        if n:
            assert row["per_target_smallest_p"] == f"2/{2 ** n}"
            need = row["pooled_majority_needed_non_tied"]
            assert ps.sign_test_p(need, pooled) < alpha <= ps.sign_test_p(need - 1, pooled), row
        else:
            assert row["per_target_smallest_p"] is None and row["pooled_majority_needed_non_tied"] is None
    drafted = plan["exploratory_outcomes"]["referral_specificity"]
    assert f"{ref_rows[0]['triples_per_target']} triples there" in drafted["per_target"]
    assert f"({ref_rows[0]['pooled_triples']} with three targets)" in drafted["across_targets"]
    assert f"needs {ref_rows[0]['pooled_majority_needed_non_tied']} of one sign" in drafted["across_targets"]


def _plan_nodes(value: object, path: str = "") -> Iterable[tuple[str, object]]:
    """(path, value) for every node of the plan below value, and (path, the key's words) for every key, so a key that
    names a count is scanned too. Paths are dotted keys, with [id] or [name] for a list entry that has one, else
    [index]: the spelling if_applied uses."""
    if isinstance(value, dict):
        children = [(f"{path}.{k}" if path else k, v, k) for k, v in value.items()]
    elif isinstance(value, list):
        children = [(f"{path}[{next((v[k] for k in ('id', 'name') if isinstance(v, dict) and isinstance(v.get(k), str)), i)}]",
                     v, None) for i, v in enumerate(value)]
    else:
        return
    for here, sub, key in children:
        if key is not None:
            yield here, key.replace("_", " ")
        yield here, sub
        yield from _plan_nodes(sub, here)


def test_if_applied_names_every_field_that_depends_on_the_passing_seeds(plan):
    """if_applied is the checklist of the amendment that applies the gate. Every field of the plan (outside the gate
    block) that holds a value tied to the seed set must be in fields, or in unchanged with a reason: the number of
    scenarios as a number or a word, 3S, 9S, 2^S, the primary's majority, t(0.975, S - 1) and its value, a
    mechanism's seed and triple counts as words, the referral seeds' triples, pooled triples and pooled majority,
    every seed id, and wording that quantifies over the seeds ("every seed", "each scenario", "all the scripts"). The
    values are derived from the plan, so the scan still means something after an amendment. A
    field can depend on the seeds without holding one of these values; if_applied lists those as well, and the scan
    cannot check them. Every listed field must exist, and every test named under tests must be in this module."""
    gate = plan["physician_realism_gate"]
    applied = gate["if_applied"]
    fields, unchanged = applied["fields"], applied["unchanged"]
    assert not set(fields) & set(unchanged)
    body = {k: v for k, v in plan.items() if k != "physician_realism_gate"}
    nodes = list(_plan_nodes(body))
    assert sorted((set(fields) | set(unchanged)) - {p for p, _ in nodes}) == [], "every listed field exists in the plan"

    ids = plan["scenario_sets"][plan["decomposition_set"]]
    s, epochs, targets = len(ids), plan["epochs_per_target"], len(plan["targets"])
    per_mechanism = max(len(v) for v in plan["mechanisms"].values())
    referral = len(plan["exploratory_outcomes"]["restricted_to_seeds"]["referral_specificity"])
    numbers = {s, epochs * s, epochs * s * len(ARMS), epochs * s * targets, 2 ** s,
               gate["counts_by_scenarios_passing"][0]["majority_needed_non_tied"],
               epochs * referral, epochs * referral * targets,
               gate["referral_by_referral_seeds_passing"][0]["pooled_majority_needed_non_tied"]}
    number_re = re.compile(r"(?<![\w.\-])(" + "|".join(str(n) for n in sorted(numbers, reverse=True)) + r")(?![\w]|\.\d)")
    t_value = f"{_t_quantile(0.975, s - 1):.3f}"
    phrases = [NUMBER_WORDS[s], f"{NUMBER_WORDS[per_mechanism]} per mechanism", f"{NUMBER_WORDS[per_mechanism]} seeds",
               f"{NUMBER_WORDS[per_mechanism]} scenarios", f"{NUMBER_WORDS[epochs * per_mechanism]} triples"]
    phrase_re = re.compile(r"\b(" + "|".join(re.escape(p) for p in phrases) + r")\b")
    # Wording that quantifies over the seed set without a count ("every seed", "each scenario", "all the scripts",
    # "every passing seed") depends on it as much as a count does (Codex review of PR #87, 2026-10-05).
    quantified_re = re.compile(r"\b(?:every|each|all)(?: of)?(?: the)?(?: \w+)? (?:seeds?|scenarios?|scripts?)\b",
                               re.IGNORECASE)

    def tied_to_the_seeds(value: object) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return value in numbers
        if isinstance(value, str):
            return bool(number_re.search(value) or phrase_re.search(value) or quantified_re.search(value)
                        or f"t(0.975, {s - 1})" in value or t_value in value or any(seed_id in value for seed_id in ids))
        return False

    found = sorted({path for path, value in nodes if tied_to_the_seeds(value)})
    listed = [*fields, *unchanged]
    uncovered = [p for p in found
                 if not any(p == q or p.startswith(q + ".") or p.startswith(q + "[") for q in listed)]
    assert uncovered == [], f"fields tied to the seed set that if_applied does not list: {uncovered}"
    # The scan finds what it is for: the fields an independent check found missing from the first draft's list.
    assert {"effect_size.reported[2]", "statements.primary[row1].text", "statements.primary[row2].text",
            "general_headline_gate.test", "general_headline_gate.smallest_attainable_p", "decomposition.registered",
            "decomposition.prespecified_secondary", "sensitivity[leave_one_scenario_out].rule",
            "sensitivity[each_mechanism_alone].rule", "exploratory_outcomes.referral_specificity.per_target",
            "exploratory_outcomes.referral_specificity.across_targets",
            "exploratory_outcomes.restricted_to_seeds.referral_specificity[0]",
            "primary.majority_needed_at_24_non_tied", "analysis_script.wave2_assumptions_to_change[7]"} <= set(found)
    assert [t for t in applied["tests"] if not callable(globals().get(t))] == []


def _section(text: str, start: str, stop: str | None) -> str:
    i = text.index(start)
    return text[i:text.index(stop, i + len(start))] if stop else text[i:]


def _md_table(text: str, header_start: str) -> list[list[str]]:
    lines = text.splitlines()
    i = next(k for k, line in enumerate(lines) if line.startswith(header_start))
    rows = []
    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


MEDIAN_OVER_EVERY_QUESTION_READ = re.compile(
    r"\b(?:each|every|all) (?:the )?questions? (?:that )?(?:the )?(?:rule|gate|it) reads\b", re.IGNORECASE)
COURSE_QUESTION = re.compile(r"course[- ]of[- ]events|course_plausible", re.IGNORECASE)


def _median_overreach(text: str) -> list[str]:
    """Sentences (or clauses split at ';' and ':') that put the median threshold on every question the rule reads, or
    on the course-of-events question, unless they say it has none. On a script the rule reads course_plausible for the
    answer floor and the flag only; gate_keys alone have the median (Codex review of PR #87, 2026-10-05)."""
    clauses = re.split(r"(?<=[.;:])\s+", text)
    return [c for c in clauses if "median" in c and not re.search(r"\bno (?:median )?threshold\b", c)
            and (MEDIAN_OVER_EVERY_QUESTION_READ.search(c) or COURSE_QUESTION.search(c))]


def test_the_gate_reads_the_same_in_the_plan_a69_section_13_and_the_protocol(plan):
    """The rule is written in four places: the plan's gate block (data), A6.9 of the preregistration, section 13 of
    the wave-3 design note and the verification protocol. Its thresholds, the round's closing counts, its closing date
    and the round's bundle must agree in all of them, so a change to one that misses another fails here. The plan's
    values must also be the ones in the owner's words that A6.9's approval record quotes (2026-10-05)."""
    gate = plan["physician_realism_gate"]
    rnd = gate["round"]
    prereg = PREREG.read_text(encoding="utf-8")
    one_line = functools.partial(re.sub, r"\s+", " ")
    a69 = one_line(_section(prereg, "### A6.9 Physician realism gate", "### Approval record"))
    record = one_line(_section(prereg, "### Approval record", None))
    s13 = one_line(_section(W3_DESIGN.read_text(encoding="utf-8"), "## 13. Physician realism gate", None))
    proto = one_line(_section(PROTOCOL.read_text(encoding="utf-8"), "**Which items the paid runs use", "\n- **"))
    ratings, answers, median = gate["min_complete_ratings"], gate["min_answers_per_key"], gate["min_median"]
    words = {w: n for n, w in NUMBER_WORDS.items()}

    def found(text: str, pattern: str) -> list[tuple[int, ...]]:
        hits = [m if isinstance(m, tuple) else (m,) for m in re.findall(pattern, text)]
        assert hits, f"{pattern!r} not found"
        return [tuple(int(x) if x.isdigit() else words[x] for x in hit) for hit in hits]

    checks = [
        (a69, r"`ratings_complete` is at least (\d+), and for each question the gate reads, `five_point\.<key>\.n` "
              r"is at least (\d+)", (ratings, answers)),
        (a69, r"`five_point\.<key>\.median` is at least (\d+)", (median,)),
        (a69, r"closes when every advice and multi-turn item has at least (\w+) complete ratings by included "
              r"physicians and at least (\w+) numeric answers", (ratings, answers)),
        (a69, r"median of at least (\d+)", (median,)),
        (a69, r"Chosen, as proposed: at least (\d+) complete ratings, with at least (\d+) numeric", (ratings, answers)),
        (a69, r"(\w+) complete ratings and (\w+) numeric answers on every question the gate reads", (ratings, answers)),
        (record, r"threshold, a median of at least (\d+) \(\"\w+\"\) on every question the gate reads; minimum "
                 r"ratings, (\d+) complete ratings and (\d+) numeric answers", (median, ratings, answers)),
        (record, r"> Gate 1: Median of (\d+) ", (median,)),
        (record, r"> Gate 2: (\d+)\b", (ratings,)),
        (record, r"> Gate 6c: (\d+)\b", (gate["min_scenarios"],)),
        (s13, r"at least (\d+) complete ratings, and at least (\d+) numeric answers", (ratings, answers)),
        (s13, r"median of at least (\d+)", (median,)),
        (proto, r"at least (\w+) complete ratings, at least (\w+) numeric answers", (ratings, answers)),
        (proto, r"a median of at least (\d+)", (median,)),
    ]
    for text, pattern, expected in checks:
        assert set(found(text, pattern)) == {expected}, pattern
    # The median threshold applies to gate_keys only. A sentence that puts it on every question the rule reads, which
    # on a script includes course_plausible, or on the course-of-events question itself, states a stricter gate than
    # the approved one. The protocol's first wording did (Codex review of PR #87, 2026-10-05).
    assert not set(gate["flag_adds"]) & set(gate["gate_keys"])
    decision_1 = one_line(_section(prereg, "1. **Threshold.**", "2. **Minimum ratings.**"))
    assert {name: _median_overreach(text) for name, text in (("protocol", proto), ("section 13", s13),
                                                             ("A6.9 decision 1", decision_1))
            if _median_overreach(text)} == {}
    assert re.search(r"course-of-events question, which has no median threshold", proto)
    assert _median_overreach("a median of at least 3 on each question the rule reads, and no flag.")
    assert _median_overreach("Each needs a median of at least 3, the course-of-events question too.")
    assert _median_overreach("Every question it reads needs a median of at least 3.")
    assert not _median_overreach("The course-of-events question has no median threshold.")
    assert answers == ratings, "the owner chose one minimum (Gate 2), for complete ratings and numeric answers alike"
    for value in (rnd["bundle"], rnd["bundle_id"], rnd["bundle_sha256"], rnd["questions_sha256"]):
        assert value in a69, value
        assert value == rnd["bundle"] or value in record, value
    assert rnd["bundle"] in s13
    closing = rnd["closing_date"]
    assert re.findall(r"> Gate 4: (\d{4}-\d\d-\d\d)", record) == [closing]
    assert f"the closing date, {closing} (UTC)" in a69 and "Extending the closing date" in a69
    assert f"closing date {closing} (UTC)" in record and "Closing date extensions" in record
    assert f"or on {closing} (UTC)" in proto
    assert "Re-pointed before round 1's bundle is fixed" in record
    floor_keys = sorted(gate["min_answers_keys"])
    assert all(f"(`{k}`)" in a69 and f"`{k}`" in s13 for k in gate["flag_adds"]), \
        "A6.9 and section 13 say the answer floor covers the flag's own questions"
    assert floor_keys == sorted([*gate["gate_keys"], *gate["flag_adds"]])
    # The accounts that rate before round 1 (the owner's test and pilot accounts, the wording-pilot physician) neither
    # fix the bundle nor count, everywhere the rule is written. The first draft fixed the bundle at the first login of
    # anyone but the test account, so the pilot physician's login would have fixed it before the pilot could reword it.
    accounts = rnd["accounts_that_do_not_fix_the_bundle"]
    assert len(accounts) == 3 and "pilot" in " ".join(accounts)
    for text in (a69, record, s13, proto):
        assert all(account in text for account in accounts), [a for a in accounts if a not in text]
    assert all("accounts_that_do_not_fix_the_bundle" in rnd[k] for k in ("bundle_rule", "excluded_raters"))
    stale = "first physician other than the owner's test account"
    assert [name for name, text in (("A6.9", a69), ("record", record), ("section 13", s13), ("protocol", proto),
                                    ("plan", one_line(json.dumps(gate)))) if stale in text] == []
    assert all("round 1 runs in a new spreadsheet" in text for text in (a69, rnd["earlier_bundle_ratings"])), \
        "how ratings on an earlier bundle stay out of the round's export"


def test_the_gate_program_spec_reads_every_file_it_compares(plan):
    """A6.9 specifies the program that will apply the gate. It must refuse when a rated message or seed has changed
    since the bundle recorded its digest, which it can see only by reading the stimuli files and the seed file as
    they are when it runs. So the spec lists them as inputs, with what it compares in each (Codex review of PR #87,
    2026-10-05): the first draft said the program read only the summary and the bundle, which would have compared
    the bundle's recorded digests with nothing."""
    gate = plan["physician_realism_gate"]
    one_line = functools.partial(re.sub, r"\s+", " ")
    prereg = PREREG.read_text(encoding="utf-8")
    a69 = one_line(_section(prereg, "### A6.9 Physician realism gate", "### Approval record"))
    spec = one_line(_section(prereg, "**Code still to write.**", "**Owner decisions"))
    s13 = one_line(_section(W3_DESIGN.read_text(encoding="utf-8"), "## 13. Physician realism gate", None))
    bundle = load_json(ROOT / gate["round"]["bundle"])
    stimuli = sorted({i["provenance"]["source_path"] for i in bundle["items"] if i["question_set"].startswith("advice")})
    assert "reads these files and no others" in spec
    for needed in ("import summary", "physician_realism_gate", "the bundle", *stimuli, "decision 6 or 7",
                   plan["seed_file"], "provenance.clinical_sha256", "provenance.patient_sha256",
                   "provenance.seed_sha256", "seed_digest", "missing"):
        assert needed in spec, f"the gate program's spec does not name {needed!r}"
    assert "seed_file" in gate["round"]["reader"] and "seed_file" in gate["item_match"]
    stale = re.compile(r"reads? only (?:the committed |that )?summary and the bundle|summary and the bundle, nothing else")
    assert [name for name, text in (("A6.9", a69), ("section 13", s13), ("plan", one_line(json.dumps(gate))))
            if stale.search(text)] == []


NOT_IN_EXPORT = "not in the export"
NEVER_CREATED = "never created"
PILOT_SHEET, NEW_SHEET = SPREADSHEETS = ("the pilot's", "a new one")


def _exclusion_refusal(excluded: list[str], expected: dict) -> str | None:
    """The exclusion check as the plan's round.expected_exclusions states it, applied to the import summary's
    exclusions.excluded_raters (the field tests/test_import_verification_ratings.py pins): None when the record agrees
    with the spreadsheet round 1 ran in and the summary excluded exactly the recorded rater codes, else why the program
    that applies the gate refuses. In a new spreadsheet none of the three accounts exists, so each is 'not in the
    export'; in the pilot's, each account created there has a rater code, and one never created is 'never created'.
    A reference for that program."""
    from scripts.import_verification_ratings import RATER_ID_RE

    values = list(expected["accounts"].values())
    if any(v is None for v in [*values, expected["spreadsheet"]]):
        return "not filled"
    if expected["spreadsheet"] not in SPREADSHEETS or any(v not in (NOT_IN_EXPORT, NEVER_CREATED)
                                                          and not RATER_ID_RE.match(v) for v in values):
        return "not a recorded value"
    if expected["spreadsheet"] == NEW_SHEET and any(v != NOT_IN_EXPORT for v in values) or (
            expected["spreadsheet"] == PILOT_SHEET and NOT_IN_EXPORT in values):
        return "disagrees with the spreadsheet"
    codes = [v for v in values if v not in (NOT_IN_EXPORT, NEVER_CREATED)]
    if len(set(codes)) != len(codes):
        return "two accounts with one code"
    if sorted(excluded) != sorted(codes):
        return "excluded raters differ"
    return None


def test_the_gate_checks_that_the_import_excluded_exactly_the_recorded_accounts(plan):
    """The three accounts that rate before round 1 are excluded at import by rater code. Those codes were written only
    in the prose of A6.9's approval record, which the gate program does not read, so an import that left out one
    --exclude-rater, or excluded a physician of the round, would have passed every comparison it makes and changed which
    items enter the paid runs (Codex review of PR #87, 2026-10-05). The plan now records them in
    round.expected_exclusions, filled by the same dated edit as the approval record before the import; until then
    every value is null and the gate cannot be applied. The program compares the summary's excluded raters with them
    exactly. Each value was first checked on its own, so a record of all three accounts 'not in the export' on the
    pilot's spreadsheet matched an import with no exclusions and counted the pilot ratings (a second finding on the
    same pull request): the record must now agree with the spreadsheet, and an account never created is 'never
    created'. Neither change alters the rule or which items pass."""
    gate = plan["physician_realism_gate"]
    rnd = gate["round"]
    expected = rnd["expected_exclusions"]
    accounts = rnd["accounts_that_do_not_fix_the_bundle"]
    assert list(expected["accounts"]) == accounts, "one entry per account that rates before round 1"
    assert all(f"'{v}'" in expected["values"] for v in (NOT_IN_EXPORT, NEVER_CREATED, *SPREADSHEETS))
    assert "exclusions.excluded_raters" in expected["check"] and "disagree with spreadsheet" in expected["check"]
    if all(v is None for v in [*expected["accounts"].values(), expected["spreadsheet"]]):
        assert _exclusion_refusal([], expected) == "not filled", "the gate cannot be applied before the record"
    else:
        codes = [v for v in expected["accounts"].values() if v not in (NOT_IN_EXPORT, NEVER_CREATED)]
        assert _exclusion_refusal(codes, expected) is None, "filled, every value one the plan allows"

    def filled(test: str | None, pilot: str | None, wording: str | None, spreadsheet: str | None) -> dict:
        return {"accounts": dict(zip(accounts, (test, pilot, wording), strict=True)), "spreadsheet": spreadsheet}

    pilot_sheet = filled("md01", "md02", "md03", PILOT_SHEET)
    new_sheet = filled(NOT_IN_EXPORT, NOT_IN_EXPORT, NOT_IN_EXPORT, NEW_SHEET)
    disagrees = "disagrees with the spreadsheet"
    cases = [
        (["md01", "md02", "md03"], pilot_sheet, None),
        (["md01", "md03"], pilot_sheet, "excluded raters differ"),                   # an --exclude-rater left out
        (["md01", "md02", "md03", "md04"], pilot_sheet, "excluded raters differ"),   # a physician of the round excluded
        (["md01", "md02", "md04"], pilot_sheet, "excluded raters differ"),
        ([], new_sheet, None),
        (["md01"], new_sheet, "excluded raters differ"),
        # The record must agree with the spreadsheet (Codex review of PR #87, 2026-10-05, second finding on the
        # record). On the pilot's spreadsheet the three accounts are in the export; recorded as absent, an import with
        # no --exclude-rater would match the empty set of codes and count the pilot ratings.
        ([], filled(NOT_IN_EXPORT, NOT_IN_EXPORT, NOT_IN_EXPORT, PILOT_SHEET), disagrees),
        (["md01", "md02"], filled("md01", "md02", NOT_IN_EXPORT, PILOT_SHEET), disagrees),
        # In a new spreadsheet none of the three accounts is set up, so a code there contradicts the record.
        (["md01"], filled("md01", NOT_IN_EXPORT, NOT_IN_EXPORT, NEW_SHEET), disagrees),
        (["md01", "md02", "md03"], filled("md01", "md02", "md03", NEW_SHEET), disagrees),
        ([], filled(NOT_IN_EXPORT, NEVER_CREATED, NOT_IN_EXPORT, NEW_SHEET), disagrees),
        # An account never created (the owner rates no pilot of their own) is named as such, and adds no code.
        (["md01", "md02"], filled("md01", NEVER_CREATED, "md02", PILOT_SHEET), None),
        (["md01", "md02", "md03"], filled("md01", NEVER_CREATED, "md02", PILOT_SHEET), "excluded raters differ"),
        (["md01", "md02"], filled("md01", "md02", None, "the pilot's"), "not filled"),
        (["md01", "md02", "md03"], filled("md01", "md02", "md03", None), "not filled"),
        (["md01", "md02"], filled("md01", "md02", "md02", "the pilot's"), "two accounts with one code"),
        (["md01", "md02", "md03"], filled("md01", "md02", "absent", "the pilot's"), "not a recorded value"),
        (["md01", "md02", "md03"], filled("md01", "md02", "md03", "another one"), "not a recorded value"),
    ]
    for excluded, record, reason in cases:
        assert _exclusion_refusal(excluded, record) == reason, (excluded, record)

    one_line = functools.partial(re.sub, r"\s+", " ")
    prereg = PREREG.read_text(encoding="utf-8")
    a69 = one_line(_section(prereg, "### A6.9 Physician realism gate", "### Approval record"))
    spec = one_line(_section(prereg, "**Code still to write.**", "**Owner decisions"))
    record = one_line(_section(prereg, "### Approval record", None))
    s13 = one_line(_section(W3_DESIGN.read_text(encoding="utf-8"), "## 13. Physician realism gate", None))
    proto = one_line(_section(PROTOCOL.read_text(encoding="utf-8"), "**Which items the paid runs use", "\n- **"))
    inputs = _section(spec, "It reads these files and no others", "It reads files 4 and 5")
    compares = _section(spec, "It reads files 4 and 5", "It compares items, not whole files")
    refuses = _section(spec, "It refuses, writing nothing", "with no passing item")
    assert "`round.expected_exclusions`" in inputs and "`exclusions.excluded_raters`" in inputs, \
        "the gate program reads the recorded exclusions and the summary's"
    assert re.search(r"`exclusions\.excluded_raters` with the rater codes in `round\.expected_exclusions`, exactly",
                     compares), "the gate program compares the two exactly"
    assert "`round.expected_exclusions` is not filled" in refuses, "and refuses while the record is not filled"
    excluded_line = _section(record, "- Excluded physicians (to fill", "- At application")
    assert "`physician_realism_gate.round.expected_exclusions`" in excluded_line
    assert [name for name, text in (("A6.9", a69), ("section 13", s13), ("protocol", proto))
            if "expected_exclusions" not in text] == []
    assert all("expected_exclusions" in rnd[k] for k in ("excluded_raters", "reader"))
    # Where the record is written, it says how it agrees with the spreadsheet, and that 'never created' is a value.
    excluded_bullet = one_line(_section(prereg, "- Excluded physicians: the owner's test account",
                                        "- The export is read"))
    for name, text in (("A6.9", excluded_bullet), ("record", excluded_line), ("section 13", s13)):
        assert '"never created"' in text and '"not in the export"' in text, name
        assert re.search(r"(?:new spreadsheet,?|In a new one,) (?:none of the three accounts|all three)", text), name
        assert re.search(r"[Ii]n the pilot's(?: spreadsheet)?, each (?:account )?(?:created there )?has its own "
                         r"(?:rater )?code[^.]*\"never created\"", text), name
    assert "does not agree with the spreadsheet round 1 ran in" in refuses
    assert "'never created'" in rnd["excluded_raters"]


def _closing_export_refusal(summary_export: dict, closing: dict) -> str | None:
    """The closing-export check as the plan's round.closing_export states it, applied to the import summary's
    inputs.export: None when the summary was built from the recorded closing export, else why the program that
    applies the gate refuses. A reference for that program."""
    from scripts.import_verification_ratings import ISO_UTC_RE, SHA256_RE

    if closing["sha256"] is None or closing["closed_utc"] is None:
        return "not filled"
    if not SHA256_RE.match(closing["sha256"]) or not ISO_UTC_RE.match(closing["closed_utc"]):
        return "not a recorded value"
    if summary_export["sha256"] != closing["sha256"] or summary_export["exported_utc"] != closing["closed_utc"]:
        return "another export"
    return None


def test_the_gate_reads_only_the_summary_of_the_recorded_closing_export(plan, tmp_path):
    """Ratings saved after round 1 closes do not count, but the gate program compared the summary only with the bundle
    and the exclusions, so a summary built from a later export of the same spreadsheet, holding ratings saved after
    the close, would have passed every check (Codex review of PR #87, 2026-10-05). The closing export's sha256 and the
    close time (its own exported_utc) are now recorded before the import, in the plan's round.closing_export and A6.9's
    approval record, and the program requires the summary's inputs.export.sha256 and inputs.export.exported_utc to
    equal them exactly. The import is run here on the committed synthetic export, so the reference check reads the
    field names the import writes. This changes neither the rule nor which items pass."""
    from scripts.import_verification_ratings import main as import_main

    rnd = plan["physician_realism_gate"]["round"]
    closing = rnd["closing_export"]
    assert set(closing) == {"sha256", "closed_utc", "values", "check"}
    assert all(f"inputs.export.{k}" in closing["values"] for k in ("sha256", "exported_utc"))
    assert all(f"inputs.export.{k}" in closing["check"] for k in ("sha256", "exported_utc"))
    assert "expected_exclusions" in closing["values"]
    assert "closing export (closing_export)" in rnd["reader"] and "inputs.export with closing_export" in rnd["reader"]
    if closing["sha256"] is None and closing["closed_utc"] is None:
        assert _closing_export_refusal({"sha256": "", "exported_utc": ""}, closing) == "not filled"

    def summarise(export: dict, name: str, indent: int | None = None) -> dict:
        path = tmp_path / f"{name}.json"   # an export is refused inside the repository
        path.write_text(json.dumps(export, indent=indent), encoding="utf-8")
        out = tmp_path / f"out_{name}"
        import_main(["--export", str(path), "--out-dir", str(out), "--resamples", "50"])
        summary = load_json(next(out.glob("*.summary.json")))
        assert summary["inputs"]["export"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        return summary["inputs"]["export"]

    fixture = load_json(ROOT / "tests" / "fixtures" / "verification_export_synthetic.json")
    assert fixture["bundle_id"] == rnd["bundle_id"], "the synthetic export is over round 1's bundle"
    at_close = summarise(fixture, "at_close")
    later = summarise({**fixture, "exported_utc": "2026-11-02T09:00:00.000Z"}, "later")
    same_time = summarise(fixture, "same_time", indent=1)   # other bytes under the same exported_utc
    assert same_time["exported_utc"] == at_close["exported_utc"] and same_time["sha256"] != at_close["sha256"]
    recorded = {"sha256": at_close["sha256"], "closed_utc": fixture["exported_utc"]}
    cases = [
        (at_close, recorded, None),
        (later, recorded, "another export"),       # a later export of the same spreadsheet
        (at_close, {**recorded, "closed_utc": later["exported_utc"]}, "another export"),
        (later, {**recorded, "sha256": later["sha256"]}, "another export"),   # the hash alone is not enough
        (same_time, recorded, "another export"),    # nor the time alone: the sha256 binds the bytes
        (at_close, {**recorded, "sha256": None}, "not filled"),
        (at_close, {**recorded, "closed_utc": None}, "not filled"),
        (at_close, {**recorded, "sha256": recorded["sha256"].upper()}, "not a recorded value"),
        (at_close, {**recorded, "closed_utc": "2026-10-20"}, "not a recorded value"),
    ]
    for summary_export, record, reason in cases:
        assert _closing_export_refusal(summary_export, record) == reason, (summary_export["exported_utc"], record)

    one_line = functools.partial(re.sub, r"\s+", " ")
    prereg = PREREG.read_text(encoding="utf-8")
    a69 = one_line(_section(prereg, "### A6.9 Physician realism gate", "### Approval record"))
    spec = one_line(_section(prereg, "**Code still to write.**", "**Owner decisions"))
    record = one_line(_section(prereg, "### Approval record", None))
    s13 = one_line(_section(W3_DESIGN.read_text(encoding="utf-8"), "## 13. Physician realism gate", None))
    proto = one_line(_section(PROTOCOL.read_text(encoding="utf-8"), "**Which items the paid runs use", "\n- **"))
    inputs = _section(spec, "It reads these files and no others", "It reads files 4 and 5")
    compares = _section(spec, "It reads files 4 and 5", "It compares items, not whole files")
    refuses = _section(spec, "It refuses, writing nothing", "with no passing item")
    assert "`inputs.export.sha256` and `inputs.export.exported_utc`" in inputs and "`round.closing_export`" in inputs
    assert re.search(r"`inputs\.export\.sha256` with `round\.closing_export\.sha256`, and its "
                     r"`inputs\.export\.exported_utc` with `round\.closing_export\.closed_utc`, exactly", compares)
    assert "`round.closing_export` is not filled" in refuses
    closing_line = _section(record, "- Closing export (to fill before the export is imported", "- At application")
    assert "`physician_realism_gate.round.closing_export`" in closing_line and "exported_utc" in closing_line
    round_bullet = _section(a69, "- Round 1 is every rating saved on that bundle", "- **Extending the closing date.**")
    assert "`physician_realism_gate.round.closing_export`" in round_bullet and "refuses a summary of any other export" \
        in round_bullet
    assert "`physician_realism_gate.round.closing_export`" in s13
    assert "refuses a summary of any other export" in proto
    assert "its `inputs.export` sha256" not in spec, "the first draft read the export's sha256 and compared it with nothing"


def test_the_closing_counts_are_read_from_a_report_that_shows_no_scores(plan):
    """The round closes early, or has its closing date extended, on counts only: complete ratings and numeric answers.
    The only report the first draft allowed before close, the app's Progress report, shows complete ratings and not
    numeric answers, and the import summary that has them puts each median beside them, so the owner could not apply
    the rule's own criterion without reading scores (Codex review of PR #87, 2026-10-05). A6.9 now specifies a counts
    report among the code still to write: per item, complete ratings and numeric answers on each question the gate
    reads, and no median, flag or score. This changes neither the rule nor which items pass."""
    rnd = plan["physician_realism_gate"]["round"]
    one_line = functools.partial(re.sub, r"\s+", " ")
    prereg = PREREG.read_text(encoding="utf-8")
    extension = one_line(_section(prereg, "- **Extending the closing date.**", "- **Items short of answers.**"))
    counts = one_line(_section(prereg, "**The counts report**", "**Owner decisions"))
    assert "counts report" in extension and "numeric answers" in extension
    assert "so it can be read for this" not in extension, "the Progress report alone does not show numeric answers"
    for needed in ("`ratings_complete`", "`five_point.<key>.n`", "for each question the gate reads",
                   "no median", "no share of low answers", "no flag", "no answer and no note",
                   "writes no file in the repository", "decide an extension"):
        assert needed in counts, f"the counts report's spec does not say {needed!r}"
    assert "counts report" in rnd["closing_date_rule"] and "no median, flag or score" in rnd["closing_date_rule"]
    assert "counts report" in rnd["closes"]


def test_a_split_wave_r_has_one_selection_path_per_family():
    """If fire-plan decision 6 splits Wave R by family, the gate writes one Wave R selection file per family. The first
    draft defined a single realism_gate_waveR path and counted the gate's output as three files (two selection files)
    everywhere, so the two families' selections had no names of their own and one could overwrite the other (Codex
    review of PR #87, 2026-10-05). A6.9 now gives each family its own path, named by the family names the stimuli
    builder offers, and every count of the gate's files allows for the split. This changes neither the rule nor which
    items pass."""
    from scripts.advice_eval import STIMULI_FAMILIES

    one_line = functools.partial(re.sub, r"\s+", " ")
    prereg = PREREG.read_text(encoding="utf-8")
    a69 = one_line(_section(prereg, "### A6.9 Physician realism gate", "### Approval record"))
    fire_plan = one_line(FIRE_PLAN.read_text(encoding="utf-8"))
    recorded = _section(a69, "**How the selection is recorded.**", "`build-stimuli --source selection` then writes")
    assert "`data/advice/realism_gate_waveR_<family>_<export stamp>.json`" in recorded
    assert "`data/advice/realism_gate_waveR_<export stamp>.json`" in recorded, "the path when Wave R is not split"
    assert all(f"`{family}`" in recorded for family in STIMULI_FAMILIES)
    split = _section(fire_plan, "- Decision 6: under its first option", "- Decision 7:")
    assert all(f"`data/advice/realism_gate_waveR_{family}_<export stamp>.json`" in split for family in STIMULI_FAMILIES)
    named = re.findall(r"realism_gate_waveR_([a-z][a-z_]*?)_<export stamp>", a69 + " " + fire_plan)
    assert named and set(named) <= set(STIMULI_FAMILIES), named
    stale = re.compile(r"\b(?:the gate's|the) (?:three|two) (?:gate |selection )?files\b|\bThree files, written together"
                       r"|\btwo selection files, `data/advice/realism_gate_waveA")
    assert [name for name, text in (("A6.9", a69), ("fire plan", fire_plan)) if stale.search(text)] == []
    counts = [a69[m.end():m.end() + 40] for m in re.finditer(r"\bthree files\b", a69, re.IGNORECASE)]
    assert counts and all(c.startswith(", or four if fire-plan decision 6 splits") for c in counts), counts

def test_the_limitations_separate_the_realism_rating_from_clinical_validation(plan):
    """Once the gate is applied, every wave-3 scenario that runs has been rated by physicians, so section 11's "eight
    invented scenarios that no clinician has reviewed" would be false, and the plan's statements would say "rated
    realistic" (Codex review of PR #87, 2026-10-05). The rating asks whether a patient could send the messages and
    whether the course of events is plausible; it sets no reference care, so the study still has no clinical
    validation. Section 11, section 2's grounding note, section 9.8, section 13 and the plan's if_applied wording for
    every statement now say both. The plan's own every_statement_carries keeps the pre-application wording until the
    amendment that applies the gate changes it. This changes neither the rule nor which items pass."""
    one_line = functools.partial(re.sub, r"\s+", " ")
    design = W3_DESIGN.read_text(encoding="utf-8")
    s11 = one_line(_section(design, "## 11. What this does not establish", "## 12."))
    grounding = one_line(_section(design, "**Grounding.**", "**`scenario.reference` stays null"))
    s98 = one_line(_section(design, "### 9.8 What each outcome permits", "### 9.9"))
    s13 = one_line(_section(design, "## 13. Physician realism gate", None))
    applied = plan["physician_realism_gate"]["if_applied"]["fields"]["statements.every_statement_carries"]
    unreviewed = re.compile(r"no clinician has reviewed|not reviewed by a clinician")
    assert not unreviewed.search(s11) and not unreviewed.search(grounding), \
        "a limitation that the gate makes false once it is applied"
    assert "(section 13)" in s11 and "(section 13)" in grounding
    assert "That rating is not clinical validation" in s11 and "`scenario.reference` is null" in s11
    for name, text in (("section 9.8", s98), ("section 13", s13), ("plan if_applied", applied)):
        assert "rated realistic by physicians in round 1" in text, name
        assert re.search(r"not (?:a )?clinical(?:ly)? validat|none of them clinically validated", text), name
    assert "until the realism gate is applied, not reviewed by a clinician" in s98
    assert "no clinician has reviewed" in plan["statements"]["every_statement_carries"], \
        "the pre-application wording, which if_applied replaces"

def test_section_13_tables_are_the_plan_rows(plan):
    """Section 13 shows the gate's counts as three tables; they must be the plan's rows, which the suite recomputes
    (test_the_realism_gate_floor_and_counts_follow_from_the_plan)."""
    gate = plan["physician_realism_gate"]
    s13 = _section(W3_DESIGN.read_text(encoding="utf-8"), "## 13. Physician realism gate", None)
    rows = gate["counts_by_scenarios_passing"]
    assert _md_table(s13, "| Scenarios passing (S) | Triples per target |") == [
        [str(r["scenarios"]), str(r["triples_per_target"]), str(r["conversations_per_target"]),
         str(r["majority_needed_non_tied"]), r["general_headline_gate_smallest_p"],
         *(f"{r['plug_in_power'][k]:.3f}" for k in ("primary", "exchanges_6_10",
                                                    "decomposition_paired_difference_before_holm"))]
        for r in rows]
    assert _md_table(s13, "| Scenarios passing (S) | t(0.975, S - 1) |") == [
        [str(r["scenarios"]), f"{r['effect_size_t_975']:.3f}", str(r["gate_reachable_with_zero_means_at_most"])]
        for r in rows]
    assert _md_table(s13, "| Referral seeds passing |") == [
        [str(r["referral_seeds"]), str(r["triples_per_target"]), r["per_target_smallest_p"] or "not computable",
         str(r["pooled_triples"]),
         "not computable" if r["pooled_majority_needed_non_tied"] is None else str(r["pooled_majority_needed_non_tied"])]
        for r in gate["referral_by_referral_seeds_passing"]]
