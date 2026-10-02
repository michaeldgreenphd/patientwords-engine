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
