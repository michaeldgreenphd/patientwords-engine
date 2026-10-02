"""The version-2 pilot run kit (pilot/prompts_v2/: generation_prompt.txt, checker_prompt.txt, design.json) must match
the harness-version-2 code in pilot/scripts/common.py: every marker the renderer fills appears exactly once and no
unknown marker appears, a rendered generation prompt carries no leftover marker, design.json selects harness version 2
with its version-2 data, the generation prompt asks for the five keys and the row and concept counts the parser and
the summary expect, and the checker prompt offers every answer value the version-2 schema accepts. Version 2 needs the
harness change that reads harness_version; the prompts do not run under the recorded run's version-1 design. The
codebook they rest on is checked by tests/test_pilot_codebook.py.

The example words the generation prompt's rules show live in design.json's prompt_examples and render through
markers, so the template holds no example vocabulary (Codex review of PR #69). Every prompt rendered from the
refactored template is byte-identical to the one rendered from the template run pilot_v2_20261002 planned from, kept
as a JSON fixture (tests/fixtures/pilot_v2_generation_prompt_before_refactor.json): the prompts compared are the ones
derive_plan plans under the version-2 design for both arms, from two seed files that give the two kinds of Arm A
exemplar block (the recorded run's 6 seeds, and 12 neutral seeds in tests/fixtures/pilot_v2_neutral_seeds.json)."""
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Load the harness module under a unique name rather than putting pilot/scripts on sys.path, so a bare `common`
# elsewhere can never shadow it or be shadowed by it (Copilot review of PR #69).
_spec = importlib.util.spec_from_file_location("pilot_common_v2_test", ROOT / "pilot" / "scripts" / "common.py")
assert _spec is not None and _spec.loader is not None, "pilot/scripts/common.py is missing"
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

V2 = ROOT / "pilot" / "prompts_v2"
GEN = (V2 / "generation_prompt.txt").read_text(encoding="utf-8")
CHK = (V2 / "checker_prompt.txt").read_text(encoding="utf-8")
DESIGN = json.loads((V2 / "design.json").read_text(encoding="utf-8"))
BEFORE = json.loads((ROOT / "tests" / "fixtures" / "pilot_v2_generation_prompt_before_refactor.json")
                    .read_text(encoding="utf-8"))
SEEDS = json.loads((ROOT / "pilot" / "seeds.json").read_text(encoding="utf-8"))["seeds"]


def render(template: str, specialty: str, swap_type: str, exemplars: list[dict]) -> str:
    return common.render_generation_prompt(template, DESIGN, specialty, swap_type, exemplars)


def test_v2_templates_have_exactly_the_renderer_markers():
    assert common.template_problems(GEN, common.generation_markers(2), "generation_prompt.txt") == []
    assert common.template_problems(CHK, common.CHECKER_MARKERS, "checker_prompt.txt") == []
    # the version-2 markers are version 2's: a version-1 template carrying them is refused as naming unknown markers
    assert any("unknown marker" in p for p in common.template_problems(GEN, common.generation_markers(1), "g"))
    assert common.generation_markers(1) == common.GENERATION_MARKERS


def test_v2_example_markers_are_checked_like_the_others():
    marker = "{{NEXT_WORD_EXAMPLES}}"
    assert GEN.count(marker) == 1
    missing = common.template_problems(GEN.replace(marker, "x"), common.generation_markers(2), "g")
    repeated = common.template_problems(GEN.replace(marker, marker + " " + marker), common.generation_markers(2), "g")
    unknown = common.template_problems(GEN.replace(marker, "{{NEXT_WORD_EXAMPLE}}"), common.generation_markers(2), "g")
    assert missing == [f"g: marker {marker} occurs 0 times, not once"]
    assert repeated == [f"g: marker {marker} occurs 2 times, not once"]
    assert f"g: marker {marker} occurs 0 times, not once" in unknown
    assert "g: unknown marker(s) ['{{NEXT_WORD_EXAMPLE}}']" in unknown


def test_v2_generation_prompt_renders_clean_for_every_cell():
    example = common.control_example_text(DESIGN)  # the version-2 example, with next_word
    assert json.loads(example)["next_word"] and list(json.loads(example)) == common.REQUIRED_FIELDS_V2
    for specialty in DESIGN["specialties"]:
        for t in DESIGN["swap_types"]:
            prompt = render(GEN, specialty, t["name"], SEEDS[:8])
            assert common.stray_marker(prompt) is None, (specialty, t["name"])
            assert example in prompt and t["definition"] in prompt
    checker = CHK.replace("{{ITEMS}}", "{}")
    assert common.stray_marker(checker) is None


def v2_harness(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A second instance of the harness module, imported with PILOT_DIR at a directory holding the version-2 kit's
    design.json, so its derive_plan plans under harness version 2 exactly as plan_calls.py does in a version-2 run
    directory. common.py reads design.json once, at import: the instance above reads the recorded run's version-1
    design, under which derive_plan refuses the version-2 template."""
    (run_dir / "design.json").write_bytes((V2 / "design.json").read_bytes())
    monkeypatch.setenv("PILOT_DIR", str(run_dir))
    spec = importlib.util.spec_from_file_location("pilot_common_v2_plan_test", ROOT / "pilot" / "scripts" / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.HARNESS_VERSION == 2 and module.PILOT == run_dir
    return module


# The two seed files the plan below is derived from, one per kind of Arm A exemplar block: with 6 seeds K = 6, so both
# arms show all six and differ only in order (PROTOCOL.md); with more than K_EXEMPLARS (8) seeds Arm A draws 8 and
# shows seeds that Arm B never does. The earlier loop over SEEDS[:8] and SEEDS[-8:] rendered neither kind: with the
# recorded run's 6 seeds both slices were the same list, in file order.
SEED_FILES = {"recorded_run_6_seeds": ROOT / "pilot" / "seeds.json",  # Arm A: all six seeds, in drawn order
              "neutral_12_seeds": ROOT / "tests" / "fixtures" / "pilot_v2_neutral_seeds.json"}  # Arm A: 8 drawn of 12


def test_v2_refactor_template_is_the_planned_template_with_its_examples():
    """The fixture is the template run pilot_v2_20261002 planned from (its hash the one that run recorded); the
    refactored template with only its example markers rendered from design.json is that template byte for byte."""
    before = BEFORE["template"]
    assert common.sha256_text(before) == BEFORE["sha256"] == (
        "a1431f41e06cc4ca74490254ce5c215856f0d57f37337f9776ac36bc51f81883")
    examples_only = GEN
    for marker, text in common.prompt_example_texts(DESIGN).items():
        examples_only = examples_only.replace(marker, text)
    assert examples_only == before


@pytest.mark.parametrize("seed_file", sorted(SEED_FILES))
def test_v2_refactor_renders_every_planned_prompt_byte_identical(seed_file: str, tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch):
    """The example words moved from the template into design.json; nothing a subagent reads changed. The plan is
    derived as plan_calls.py derives it (derive_plan under the version-2 design), so both arms' exemplar blocks are
    the ones a run shows: Arm B the first k seeds in file order in every call, Arm A one draw of k per cell from the
    seeded stream. Every planned prompt, for both arms, must equal the template run pilot_v2_20261002 planned from
    rendered with the exemplars the plan records for that call. The test first requires that the seed file gives the
    kind of Arm A block it stands for, so the comparison cannot pass over one kind of block twice."""
    v2 = v2_harness(tmp_path, monkeypatch)
    seeds = v2.validate_seeds(json.loads(SEED_FILES[seed_file].read_text(encoding="utf-8")))
    plan = v2.derive_plan(seeds, GEN, "0" * 64, "0" * 64)
    k = plan["k_exemplars_used"]
    first_k = [s["id"] for s in seeds[:k]]
    arm = {a: [c for c in plan["calls"] if c["arm"] == a] for a in v2.ARMS}
    assert len(arm["A"]) == len(arm["B"]) == len(v2.cells())
    # Arm B: the first k seeds in file order, one block for every call
    assert all(c["exemplar_ids"] == first_k for c in arm["B"])
    # Arm A: k distinct seeds per call in drawn order, never Arm B's block, and not one block for every cell
    assert all(len(set(c["exemplar_ids"])) == k and c["exemplar_ids"] != first_k for c in arm["A"])
    assert len({tuple(c["exemplar_ids"]) for c in arm["A"]}) > 1
    shown_by_a = {i for c in arm["A"] for i in c["exemplar_ids"]}
    if seed_file == "recorded_run_6_seeds":  # k = n = 6: Arm A shows the same six seeds as Arm B, reordered
        assert (k, len(seeds)) == (6, 6) and shown_by_a == set(first_k)
    else:  # k = 8 of 12: Arm A also shows seeds that Arm B never shows
        assert (k, len(seeds)) == (common.K_EXEMPLARS, 12) and shown_by_a - set(first_k)
    by_id = {s["id"]: s for s in seeds}
    for c in plan["calls"]:
        exemplars = [by_id[i] for i in c["exemplar_ids"]]
        assert c["prompt"] == v2.render_generation_prompt(BEFORE["template"], v2.DESIGN, c["specialty"],
                                                          c["swap_type"], exemplars), c["id"]


def test_v2_template_holds_no_example_words():
    examples = DESIGN["prompt_examples"]
    assert set(examples) == set(common.V2_PROMPT_EXAMPLES)
    words = [v for value in examples.values() for v in (value if isinstance(value, list) else [value])]
    assert words and all(w not in GEN for w in words)
    assert all(w in BEFORE["template"] for w in words)  # each was in the template before the move


def test_v2_prompt_examples_are_validated():
    ex = DESIGN["prompt_examples"]
    for bad in ({k: v for k, v in ex.items() if k != "next_words"},  # a field missing
                dict(ex, extra="x"),  # a field the renderer does not know
                dict(ex, technical_term=""),  # empty
                dict(ex, plain_word=' padded '),  # surrounding space
                dict(ex, leaflet_wording='a "quoted" phrase'),  # a double quote inside the template's quotes
                dict(ex, vaguer_patient_term="{{EXEMPLARS}}"),  # a marker riding in
                dict(ex, patient_phrases=[]),  # an empty list
                dict(ex, clinical_note_phrases=["x", "x"]),  # a repeat
                dict(ex, next_words=["Two words"]),  # not a next word rule 7 allows
                dict(ex, probe_point_examples=["... and then"])):  # not ending on a probe ending
        with pytest.raises(SystemExit):
            common.prompt_example_texts(dict(DESIGN, prompt_examples=bad))
    with pytest.raises(SystemExit):
        common.prompt_example_texts({k: v for k, v in DESIGN.items() if k != "prompt_examples"})
    # the prompt examples are version-2 data: a version-1 design carrying them is refused like the other version-2 keys
    v1 = json.loads((ROOT / "pilot" / "design.json").read_text(encoding="utf-8"))
    assert common.version_design_problems(dict(v1, prompt_examples=ex))
    assert common.version_design_problems({k: v for k, v in DESIGN.items() if k != "prompt_examples"})


def test_v2_design_selects_harness_version_2_with_its_data():
    assert common.harness_version(DESIGN) == 2
    assert common.version_design_problems(DESIGN) == []
    assert DESIGN["probe_endings"] == ["a", "an", "the", "my", "his", "her", "their", "your", "our"]
    assert (DESIGN["concepts_per_call"], DESIGN["variant_pairs_per_call"]) == (12, 4)
    assert DESIGN["review_sampling"] == "one_row_per_concept"
    # a copy of the recorded run's design: the same cells in the same order (only the control example, the prompt
    # examples and the version-2 keys differ)
    v1 = json.loads((ROOT / "pilot" / "design.json").read_text(encoding="utf-8"))
    assert (DESIGN["specialties"], DESIGN["swap_types"]) == (v1["specialties"], v1["swap_types"])
    assert "harness_version" not in v1 and "prompt_examples" not in v1  # the recorded run stays version 1


def test_v2_generation_prompt_asks_for_the_five_keys():
    keys = ", ".join(f'"{k}"' for k in common.required_fields(2))
    assert f"Each line is one JSON object with exactly these keys: {keys}." in GEN
    assert common.version_template_problems(GEN, "generation", 2) == []
    # the version-2 prompts are refused under version 1, which would drop next_word and the further checker answers
    assert common.version_template_problems(GEN, "generation", 1)
    assert common.version_template_problems(CHK, "checker", 1)


def test_v2_generation_prompt_asks_for_the_parsed_row_and_concept_counts():
    assert f"Return exactly {common.ROWS_PER_CALL} lines." in GEN
    assert f"- {common.ROWS_PER_CALL - common.CONTROLS_PER_CALL} lines have \"control\": \"none\"." in GEN
    assert f"- {common.CONTROLS_PER_CALL} lines have \"control\": \"negative\"." in GEN
    assert f"They cover {DESIGN['concepts_per_call']} different concepts within the cell." in GEN
    assert f"For {DESIGN['variant_pairs_per_call']} of those concepts, put a second line immediately after the first" in GEN


def test_v2_generation_prompt_lists_the_probe_endings():
    assert "End the template right after an article or a possessive ({{PROBE_ENDINGS}})" in GEN
    prompt = render(GEN, DESIGN["specialties"][0], DESIGN["swap_types"][0]["name"], SEEDS[:8])
    listed = re.search(r"End the template right after an article or a possessive \(([^)]*)\)", prompt)
    assert listed is not None
    assert [w.strip() for w in listed.group(1).split(",")] == DESIGN["probe_endings"]


def test_v2_checker_prompt_names_every_enum_value():
    assert common.checker_enum_problems(CHK) == []
    for value in (*common.CHECKER_VERDICTS, *common.CHECKER_RELATIONS, *common.CHECKER_SENTENCE_NATURAL,
                  *common.CHECKER_PATIENT_REALISM):
        assert f'"{value}"' in CHK, value
    for field in ("equivalent", *common.CHECKER_V2_FIELDS):
        assert re.search(rf"\b{field}\b", CHK), field
    # the prompt's own consistency rule is the one the parser flags against
    assert '"yes" when relation is same, same_brand or broader; "no" when relation is narrower or different' in CHK
    assert {r for r, eq in common.RELATION_EQUIVALENT.items() if eq == "yes"} == {"same", "same_brand", "broader"}
