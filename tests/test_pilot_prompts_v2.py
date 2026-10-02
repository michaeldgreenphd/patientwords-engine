"""The version-2 pilot run kit (pilot/prompts_v2/: generation_prompt.txt, checker_prompt.txt, design.json) must match
the harness-version-2 code in pilot/scripts/common.py: every marker the renderer fills appears exactly once and no
unknown marker appears, a rendered generation prompt carries no leftover marker, design.json selects harness version 2
with its version-2 data, the generation prompt asks for the five keys and the row and concept counts the parser and
the summary expect, and the checker prompt offers every answer value the version-2 schema accepts. Version 2 needs the
harness change that reads harness_version; the prompts do not run under the recorded run's version-1 design. The
codebook they rest on is checked by tests/test_pilot_codebook.py."""
import importlib.util
import json
import re
from pathlib import Path

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


def test_v2_templates_have_exactly_the_renderer_markers():
    assert common.template_problems(GEN, common.GENERATION_MARKERS, "generation_prompt.txt") == []
    assert common.template_problems(CHK, common.CHECKER_MARKERS, "checker_prompt.txt") == []


def test_v2_generation_prompt_renders_clean_for_every_cell():
    example = common.control_example_text(DESIGN)  # the version-2 example, with next_word
    assert json.loads(example)["next_word"] and list(json.loads(example)) == common.REQUIRED_FIELDS_V2
    for specialty in DESIGN["specialties"]:
        for t in DESIGN["swap_types"]:
            prompt = (GEN.replace("{{SPECIALTY}}", specialty).replace("{{SWAP_TYPE}}", t["name"])
                      .replace("{{SWAP_DEFINITION}}", t["definition"]).replace("{{CONTROL_EXAMPLE}}", example)
                      .replace("{{EXEMPLARS}}", "{}"))
            assert common.stray_marker(prompt) is None, (specialty, t["name"])
    checker = CHK.replace("{{ITEMS}}", "{}")
    assert common.stray_marker(checker) is None


def test_v2_design_selects_harness_version_2_with_its_data():
    assert common.harness_version(DESIGN) == 2
    assert common.version_design_problems(DESIGN) == []
    assert DESIGN["probe_endings"] == ["a", "an", "the", "my", "his", "her", "their", "your", "our"]
    assert (DESIGN["concepts_per_call"], DESIGN["variant_pairs_per_call"]) == (12, 4)
    assert DESIGN["review_sampling"] == "one_row_per_concept"
    # a copy of the recorded run's design: the same cells in the same order (only the control example and the
    # version-2 keys differ)
    v1 = json.loads((ROOT / "pilot" / "design.json").read_text(encoding="utf-8"))
    assert (DESIGN["specialties"], DESIGN["swap_types"]) == (v1["specialties"], v1["swap_types"])
    assert "harness_version" not in v1  # the recorded run stays version 1


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
    listed = re.search(r"End the template right after an article or a possessive \(([^)]*)\)", GEN)
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
