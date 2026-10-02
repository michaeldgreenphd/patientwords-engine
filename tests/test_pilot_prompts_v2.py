"""The version-2 pilot prompts (pilot/prompts_v2/) must drop into a run's prompts/ folder without any harness change:
every marker the renderer fills appears exactly once and no unknown marker appears, a rendered generation prompt
carries no leftover marker, and the output contract the parser enforces (rows and negative controls per call) is the
one the prompt asks for. The codebook they rest on must parse and cite only reviewed examples."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load the harness module under a unique name rather than putting pilot/scripts on sys.path, so a bare `common`
# elsewhere can never shadow it or be shadowed by it (Copilot review of PR #69).
_spec = importlib.util.spec_from_file_location("pilot_common_v2_test", ROOT / "pilot" / "scripts" / "common.py")
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

V2 = ROOT / "pilot" / "prompts_v2"


def test_v2_templates_have_exactly_the_renderer_markers():
    gen = (V2 / "generation_prompt.txt").read_text(encoding="utf-8")
    chk = (V2 / "checker_prompt.txt").read_text(encoding="utf-8")
    assert common.template_problems(gen, common.GENERATION_MARKERS, "generation_prompt.txt") == []
    assert common.template_problems(chk, common.CHECKER_MARKERS, "checker_prompt.txt") == []


def test_v2_generation_prompt_renders_clean_for_every_cell():
    gen = (V2 / "generation_prompt.txt").read_text(encoding="utf-8")
    example = common.control_example_text(common.DESIGN)
    for specialty in common.SPECIALTIES:
        for swap_type, definition in common.SWAP_DEFINITIONS.items():
            prompt = (gen.replace("{{SPECIALTY}}", specialty).replace("{{SWAP_TYPE}}", swap_type)
                      .replace("{{SWAP_DEFINITION}}", definition).replace("{{CONTROL_EXAMPLE}}", example)
                      .replace("{{EXEMPLARS}}", "{}"))
            assert common.stray_marker(prompt) is None, (specialty, swap_type)


def test_v2_generation_prompt_asks_for_the_parsed_row_counts():
    gen = (V2 / "generation_prompt.txt").read_text(encoding="utf-8")
    assert f"Return exactly {common.ROWS_PER_CALL} lines." in gen
    assert f"- {common.ROWS_PER_CALL - common.CONTROLS_PER_CALL} lines have \"control\": \"none\"." in gen
    assert f"- {common.CONTROLS_PER_CALL} lines have \"control\": \"negative\"." in gen


def test_codebook_cites_only_its_own_examples():
    book = json.loads((ROOT / "pilot" / "codebook" / "codebook_v0.1.json").read_text(encoding="utf-8"))
    cited = {e for part in ("rules", "open_questions", "clinician_questions") for x in book[part] for e in x["examples"]}
    listed = {e["sample_id"] for e in book["examples"]}
    assert cited == listed
    assert book["baseline"]["reviewed"] == common.N_REVIEW
    assert book["baseline"]["all_blind_first_answers"] is True
