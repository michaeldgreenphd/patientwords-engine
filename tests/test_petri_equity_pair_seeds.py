"""Tests for the paired equity studies: version 2 (docs/framework/petri_seeds_equity_v2.draft.json; owner decision
2026-10-14) and version 3 (docs/framework/petri_seeds_equity_v3.draft.json; owner decision Q7 of 2026-10-14, drafted
2026-10-31). Every test runs on both sets.

Each equity seed has a matched control: the same clinical course without the barrier details (housing, insurance and
stigma in version 2; language, distance and cost in version 3).
The pairing, the shared turns, the warning-sign turn and the warning-sign terms are data
(data/petri/equity_v2_pairs.draft.json), and every seed id is read from there, so no scenario vocabulary is written in
this file (AGENTS.md hard conventions)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from scripts.petri_audit import checks, cli, framework, judge_runner, seeds, token_budget, transcripts
from scripts.petri_audit.framework import load_json, sha256_text

ROOT = Path(__file__).resolve().parents[1]
# (seed file, lay_careful swaps, pairing) per study
STUDIES = {
    version: (ROOT / "docs" / "framework" / f"petri_seeds_equity_{version}.draft.json",
              ROOT / "data" / "petri" / f"lay_careful_swaps_equity_{version}.draft.json",
              ROOT / "data" / "petri" / f"equity_{version}_pairs.draft.json")
    for version in ("v2", "v3")
}
ARMS = ("clinical", "colloquial", "lay_careful")
TURNS = 10

Seed = dict[str, Any]


@pytest.fixture(scope="module", params=sorted(STUDIES))
def study(request: pytest.FixtureRequest) -> tuple[Path, Path, Path]:
    return STUDIES[request.param]


@pytest.fixture(scope="module")
def seed_file(study: tuple[Path, Path, Path]) -> Path:
    return study[0]


@pytest.fixture(scope="module")
def doc(seed_file: Path) -> dict[str, Any]:
    return load_json(seed_file)


@pytest.fixture(scope="module")
def by_id(doc: dict[str, Any]) -> dict[str, Seed]:
    return {s["seed_id"]: s for s in doc["seeds"]}


@pytest.fixture(scope="module")
def pairs(study: tuple[Path, Path, Path]) -> dict[str, Any]:
    return load_json(study[2])


def _texts(seed: Seed) -> dict[str, str]:
    return {t["key"]: t["text"] for t in seed["texts"]}


def _roles(seed: Seed, arm: str) -> list[str | None]:
    return [t["context_role"] for t in next(a for a in seed["protocol"]["arms"] if a["id"] == arm)["turns"]]


def test_pairs_name_every_seed_once(doc: dict[str, Any], pairs: dict[str, Any], seed_file: Path) -> None:
    named = [p[k] for p in pairs["pairs"] for k in ("equity", "control")]
    assert sorted(named) == sorted(s["seed_id"] for s in doc["seeds"])
    assert len(set(named)) == len(named)
    assert pairs["seed_file"] == str(seed_file.relative_to(ROOT))


def test_every_seed_validates(seed_file: Path) -> None:
    seed_set = seeds.load_seed_file(seed_file)
    for seed_id, seed in seed_set.seeds.items():
        assert seeds.validate_seed(seed, seed_set) == [], seed_id


def test_validate_seeds_cli_accepts_the_file(doc: dict[str, Any], seed_file: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate-seeds", "--seeds", str(seed_file)]) == 0
    out = capsys.readouterr().out
    assert all(f"{s['seed_id']}: ok" in out for s in doc["seeds"])


def test_every_text_digest_matches_its_text(doc: dict[str, Any]) -> None:
    for seed in doc["seeds"]:
        for t in seed["texts"]:
            assert t["sha256"] == sha256_text(t["text"]), (seed["seed_id"], t["key"])


def test_structure_is_the_same_in_every_seed(doc: dict[str, Any]) -> None:
    """Exploratory study: not claim-grade. Ten scripted turns in three patient arms, sustained exposure, and one
    sequence of context roles shared by every arm of every seed, so a pair differs only in its texts."""
    role_sequences: set[tuple[str | None, ...]] = set()
    for seed in doc["seeds"]:
        sid, proto = seed["seed_id"], seed["protocol"]
        assert seed["mode"] == "scripted" and seed["claim_grade_eligible"] is False, sid
        assert seed["speaker_identity"]["policy"] == "constant", sid
        assert proto["register_exposure"] == "sustained" and proto["max_target_turns"] == TURNS, sid
        assert [a["id"] for a in proto["arms"]] == list(ARMS), sid
        assert {a["user_is"] for a in proto["arms"]} == {"patient"}, sid
        assert {len(a["turns"]) for a in proto["arms"]} == {TURNS}, sid
        role_sequences |= {tuple(_roles(seed, arm)) for arm in ARMS}
    assert len(role_sequences) == 1


def test_the_evidence_role_is_only_at_the_pivot_turn(doc: dict[str, Any], pairs: dict[str, Any]) -> None:
    """The only turn marked evidence is pivot_turn. The role is a label; the text it labels is checked below."""
    pivot = pairs["pivot_turn"]
    for seed in doc["seeds"]:
        roles = _roles(seed, "clinical")
        assert [i for i, r in enumerate(roles, 1) if r == "evidence"] == [pivot], seed["seed_id"]


def _affirmed(text: str, terms: list[str], cues: list[str]) -> list[str]:
    """The terms `text` affirms: each occurrence whose sentence has no negation cue before it ("no fever" is a
    negated mention; "a fever of" an affirmed one)."""
    found = []
    for sentence in re.split(r"[.?!]\s", text.lower()):
        for term in terms:
            for m in re.finditer(re.escape(term.lower()), sentence):
                before = sentence[:m.start()]
                if not any(re.search(rf"\b{re.escape(c)}\b", before) for c in cues):
                    found.append(term)
    return found


def test_the_warning_signs_are_affirmed_only_at_the_pivot_turn(by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """The scripted texts, not only the role label (Codex review of PR #108): in every arm of every seed, the
    scenario's warning-sign terms are affirmed at pivot_turn and nowhere else; earlier turns may only deny them. eq02
    (2026-10-13) put warning signs at turns 4, 5 and 7 of the first equity seeds, and every wording reached the top
    tier by turn 4."""
    pivot, cues = pairs["pivot_turn"], pairs["negation_cues"]
    for pair in pairs["pairs"]:
        assert pair["warning_signs"]
        for seed_id in (pair["equity"], pair["control"]):
            texts = _texts(by_id[seed_id])
            for n in range(1, TURNS + 1):
                for arm in ARMS:
                    affirmed = _affirmed(texts[f"t{n:02d}_{arm}"], pair["warning_signs"], cues)
                    if n == pivot:
                        assert affirmed, (seed_id, n, arm)
                    else:
                        assert affirmed == [], (seed_id, n, arm, affirmed)


def test_the_affirmation_check_tells_a_denial_from_a_sign() -> None:
    # abstract tokens: the real terms live in the pairs file and are exercised by the test above
    assert _affirmed("Today I have no alphasign.", ["alphasign"], ["no"]) == []
    assert _affirmed("Today I have an alphasign of 39.", ["alphasign"], ["no"]) == ["alphasign"]
    assert _affirmed("No betasign. Tonight an alphasign started.", ["alphasign"], ["no"]) == ["alphasign"]


def test_matched_pairs_share_the_clinical_course(by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """Shared turns are byte-identical in every arm of the equity seed and its control; every other turn differs in
    every arm, where the equity seed carries its housing, insurance and stigma details."""
    for pair in pairs["pairs"]:
        eq, ctl = _texts(by_id[pair["equity"]]), _texts(by_id[pair["control"]])
        shared = set(pair["shared_turns"])
        assert pairs["pivot_turn"] in shared
        for n in range(1, TURNS + 1):
            for arm in ARMS:
                key = f"t{n:02d}_{arm}"
                if n in shared:
                    assert eq[key] == ctl[key], (pair["equity"], key)
                else:
                    assert eq[key] != ctl[key], (pair["equity"], key)


def test_both_arms_of_a_pair_judge_barrier_help_against_the_same_obstacle(
        by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """barrier_help (drafted 2026-10-31) keeps the arm hidden only if the equity seed and its control give the judge
    the same obstacle text: the control, which never states the obstacle, then gives the rate at which that help
    appears unprompted. A pair judges it in both seeds or in neither."""
    for pair in pairs["pairs"]:
        eq, ctl = by_id[pair["equity"]], by_id[pair["control"]]
        judged = {"barrier_help" in s["judge"]["outcome_dimensions"] for s in (eq, ctl)}
        assert len(judged) == 1, pair["equity"]
        if judged == {True}:
            refs = [next(c["text_ref"] for c in s["judge"]["supplied_contexts"] if c["dimension_id"] == "barrier_help")
                    for s in (eq, ctl)]
            obstacle = [_texts(s)[ref] for s, ref in zip((eq, ctl), refs)]
            assert obstacle[0] == obstacle[1] and obstacle[0].strip(), pair["equity"]


def test_barrier_help_without_an_obstacle_is_refused(seed_file: Path) -> None:
    seed_set = seeds.load_seed_file(seed_file)
    seed = next((s for s in seed_set.seeds.values() if "barrier_help" in s["judge"]["outcome_dimensions"]), None)
    if seed is None:
        pytest.skip("this study does not judge barrier_help")
    broken = {**seed, "judge": {**seed["judge"], "supplied_contexts": [
        c for c in seed["judge"]["supplied_contexts"] if c["dimension_id"] != "barrier_help"]}}
    assert "barrier_help is judged but no obstacle is supplied as context" in seeds.validate_seed(broken, seed_set)


def _barrier_help_plans(seed: Seed, reply: str) -> list[judge_runner.JudgePlan]:
    texts = _texts(seed)
    arm = next(a for a in seed["protocol"]["arms"] if a["id"] == "clinical")
    messages = []
    for i, turn in enumerate(arm["turns"], 1):
        messages += [{"role": "user", "text": texts[turn["text_ref"]], "id": f"u{i}"},
                     {"role": "assistant", "text": reply, "id": f"a{i}"}]
    record = transcripts.build_record(messages, conversation_id="c" * 64, source_system="inspect_petri",
                                      source_model="mockllm/model", model_version="mockllm",
                                      captured_utc="2026-10-31T00:00:00Z", user_is="patient",
                                      import_utc="2026-10-31T00:00:00Z", importer_sha=None,
                                      run_manifest_sha256="a" * 64, run_manifest_ref=None)
    gated = judge_runner.gated_turn_ids_for(record, seed, checks.ROOT_BRANCH, "clinical")
    plans = judge_runner.plan_record(record, seed, outcomes=framework.load_json(framework.OUTCOME_REGISTRY),
                                     rubric=judge_runner.load_rubric(), branched_from_turn_id=None,
                                     gated_turn_ids=gated)
    return [p for p in plans if p.key == "barrier_help"]


def test_barrier_help_judges_the_replies_to_the_pressure_turns_blind_to_the_arm(
        by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """Only the replies that answer a pressure turn are judged, against the obstacle, and the judge's prompt for the
    same reply is byte-identical whether the reply came from the equity seed or its control."""
    pair = next((p for p in pairs["pairs"] if "barrier_help" in by_id[p["equity"]]["judge"]["outcome_dimensions"]),
                None)
    if pair is None:
        pytest.skip("this study does not judge barrier_help")
    eq, ctl = (_barrier_help_plans(by_id[pair[k]], "reply text") for k in ("equity", "control"))
    pressure = [i for i, role in enumerate(_roles(by_id[pair["equity"]], "clinical"), 1) if role == "pressure"]
    assert pressure and [p.exchange_index for p in eq if p.prompt is not None] == pressure
    assert {p.not_applicable_reason for p in eq if p.prompt is None} == {"this reply does not answer a pressure turn"}
    obstacle = _texts(by_id[pair["equity"]])["obstacle"]
    judged = [p for p in eq if p.prompt is not None]
    assert all(obstacle in p.prompt and "reply text" in p.prompt for p in judged)
    assert [p.prompt for p in judged] == [p.prompt for p in ctl if p.prompt is not None]


def _one_span_deleted(longer: str, shorter: str) -> bool:
    """True when `shorter` is `longer` with exactly one non-empty contiguous span removed."""
    if len(shorter) >= len(longer):
        return False
    head = next((i for i, (a, b) in enumerate(zip(longer, shorter)) if a != b), len(shorter))
    return any(longer[:i] + longer[i + len(longer) - len(shorter):] == shorter for i in range(head + 1))


def test_clause_removed_turns_change_only_the_equity_clause(by_id: dict[str, Seed], pairs: dict[str, Any]) -> None:
    """On the turns the pairs file names, the control is the equity text with one span (the equity clause) deleted, so
    the clinical exposure the turn describes is the same in both (Codex review of PR #108: the foot control had
    changed the footwear exposure as well)."""
    for pair in pairs["pairs"]:
        eq, ctl = _texts(by_id[pair["equity"]]), _texts(by_id[pair["control"]])
        assert pair["clause_removed_turns"] and not set(pair["clause_removed_turns"]) & set(pair["shared_turns"])
        for n in pair["clause_removed_turns"]:
            for arm in ARMS:
                key = f"t{n:02d}_{arm}"
                assert _one_span_deleted(eq[key], ctl[key]), (pair["control"], key)


def test_declared_hypotheses_are_those_of_the_judged_outcomes(doc: dict[str, Any]) -> None:
    """A seed's hypotheses are copied onto every analysis row (judge_runner.analysis_rows), so they must be exactly the
    hypotheses of the outcome dimensions it judges (Codex review of PR #108: H2 was declared, which these seeds do not
    measure, and H4 was missing)."""
    registry = {d["id"]: set(d.get("hypotheses") or [])
                for d in load_json(ROOT / "docs" / "framework" / "outcome_dimensions.draft.json")["dimensions"]}
    for seed in doc["seeds"]:
        judged: set[str] = set().union(*(registry[d] for d in seed["judge"]["outcome_dimensions"]))
        assert set(seed["hypotheses"]) == judged, (seed["seed_id"], seed["hypotheses"], sorted(judged))


def test_lay_careful_is_the_clinical_text_with_its_swaps(doc: dict[str, Any], study: tuple[Path, Path, Path]) -> None:
    seed_file, swaps_file, _ = study
    swaps = load_json(swaps_file)
    assert swaps["seed_file"] == str(seed_file.relative_to(ROOT))
    for seed in doc["seeds"]:
        sid, texts = seed["seed_id"], _texts(seed)
        for n in range(1, TURNS + 1):
            t = f"t{n:02d}"
            out = texts[f"{t}_clinical"]
            for clinical_span, lay_span in swaps["seeds"][sid][f"{t}_lay_careful"]:
                assert clinical_span in out, (sid, t, clinical_span)
                out = out.replace(clinical_span, lay_span, 1)
                assert lay_span.lower() in texts[f"{t}_colloquial"].lower(), (sid, t, lay_span)
            assert out == texts[f"{t}_lay_careful"], (sid, t)


def test_colloquial_turns_are_lower_case(doc: dict[str, Any]) -> None:
    """The framing registry's colloquial register: casual orthography, lower case."""
    for seed in doc["seeds"]:
        for key, text in _texts(seed).items():
            if key.endswith("_colloquial"):
                assert text == text.lower(), (seed["seed_id"], key)


def test_every_conversation_fits_the_token_limit_ten_turn_runs_use(seed_file: Path) -> None:
    """The pre-flight projection (scripts/petri_audit/token_budget.py) clears every condition at 40,000 tokens."""
    seed_set = seeds.load_seed_file(seed_file)
    problems, _ = token_budget.token_limit_report(list(seed_set.seeds.values()), token_limit=40000)
    assert problems == []
