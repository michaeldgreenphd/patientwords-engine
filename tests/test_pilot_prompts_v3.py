"""The version-3 pilot run kit (pilot/prompts_v3/) must run unchanged under the harness-version-2 code in
pilot/scripts/common.py: version 3 changes only the generation prompt's rule text, so it carries exactly the
version-2 markers, its design.json is a valid version-2 design, and every prompt derive_plan plans from it renders
clean, lists every probe ending and carries each rule added from the owner's review of run pilot_v2_20261002. The
checker prompt is version 2's byte for byte, and the design differs from version 2's only in its note.

The rules are checked by the sentences that state them, which hold no medical vocabulary (engine AGENTS.md: that
lives in data files, never in Python source); the kit's example words stay in design.json's prompt_examples, and the
template must not carry them. The codebook decision that goes with the kit (D1, codebook v0.3: the checker is not a
gate for keeping stimuli) is checked here too, with version 0.2's files pinned unchanged; tests/test_pilot_codebook.py
checks that the current codebook rebuilds from its inputs."""
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "pilot" / "prompts_v2"
V3 = ROOT / "pilot" / "prompts_v3"
CODEBOOK = ROOT / "pilot" / "codebook"
GEN = (V3 / "generation_prompt.txt").read_text(encoding="utf-8")
CHK = (V3 / "checker_prompt.txt").read_text(encoding="utf-8")
DESIGN = json.loads((V3 / "design.json").read_text(encoding="utf-8"))

# Load the harness module under a unique name rather than putting pilot/scripts on sys.path (as the version-2 test
# does). This instance reads the recorded run's version-1 design.json; the plan test below imports a second instance
# that reads the version-3 design.
_spec = importlib.util.spec_from_file_location("pilot_common_v3_test", ROOT / "pilot" / "scripts" / "common.py")
assert _spec is not None and _spec.loader is not None, "pilot/scripts/common.py is missing"
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

# The sentences that state each rule added or changed in version 3, as the rendered prompt carries them, keyed by the
# README's heading for the rule. None holds a marker, so each appears verbatim in every rendered prompt.
V3_RULES = {
    "rule 3, first person only": (
        "3. First person. Both sentences are the patient speaking or writing about themselves, in the first person",
        "The speaker is always the patient, never a relative, a clinician or a narrator describing someone else"),
    "rule 4, the clinical phrase as a clinician writes it": (
        "Where such a standard term exists, use it rather than a description.",
        "Write it the way a clinician writes it in a note, in its usual word order and with the details a clinician "
        "would add, not as a stiff phrase built to fit the blank; the sentence around it stays the patient's own "
        "words (rule 3)."),
    "rule 5, common slang only": (
        "Use only slang that most adult patients would recognise; avoid regional, dated or rare slang.",
        "the second a vaguer or slangier one (slang only as rule 5 allows)"),
    "rule 6, at most one brand-name concept per call": (
        "6. Brand names, at most one concept per call.",
        "At most one of this call's concepts may pair a drug's generic name with one of its brand names.",
        "Every other medicine concept must change register in another way"),
    "rule 8, keep the side, the place and the number": (
        "8. Keep the side, the place and the number.",
        "the patient phrase may be vaguer about what the thing is (rule 7), never about where it is or how many.",
        "say it in both phrases, so that neither phrase is more specific than the other."),
    "rule 9, no grid names for a region": (
        "9. No grid names for a region.",
        "on the clinical side use the standard anatomical term for that part.",
        "If the only clinical name for a place is its grid name, choose a different body part."),
}


def v3_harness(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A harness instance imported with PILOT_DIR at a directory holding the version-3 design.json, so derive_plan
    plans exactly as plan_calls.py does in a run directory the kit was copied into. common.py reads design.json once,
    at import."""
    (run_dir / "design.json").write_bytes((V3 / "design.json").read_bytes())
    monkeypatch.setenv("PILOT_DIR", str(run_dir))
    spec = importlib.util.spec_from_file_location("pilot_common_v3_plan_test", ROOT / "pilot" / "scripts" / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.HARNESS_VERSION == 2 and module.PILOT == run_dir
    return module


# both kinds of Arm A exemplar block (see tests/test_pilot_prompts_v2.py): run 2's 26 seeds, from which Arm A draws 8,
# and run 1's 6, which both arms show in full
SEED_FILES = {"run_2_seeds": ROOT / "pilot" / "runs" / "pilot_v2_20261002" / "seeds.json",
              "run_1_seeds": ROOT / "pilot" / "seeds.json"}


def test_v3_templates_have_exactly_the_version_2_markers():
    assert common.template_problems(GEN, common.generation_markers(2), "generation_prompt.txt") == []
    assert common.template_problems(CHK, common.CHECKER_MARKERS, "checker_prompt.txt") == []
    assert common.version_template_problems(GEN, "generation", 2) == []
    assert common.version_template_problems(CHK, "checker", 2) == []
    # still refused under the recorded run's version-1 design, which would drop next_word and the checker's answers
    assert common.version_template_problems(GEN, "generation", 1)
    assert common.version_template_problems(CHK, "checker", 1)


def test_v3_design_is_the_version_2_design_with_a_new_note():
    v2 = json.loads((V2 / "design.json").read_text(encoding="utf-8"))
    assert DESIGN["_note"] != v2["_note"]
    assert {k: v for k, v in DESIGN.items() if k != "_note"} == {k: v for k, v in v2.items() if k != "_note"}
    assert list(DESIGN) == list(v2)
    assert common.harness_version(DESIGN) == 2
    assert common.version_design_problems(DESIGN) == []
    common.prompt_example_texts(DESIGN)  # raises SystemExit when the examples cannot render
    example = json.loads(common.control_example_text(DESIGN))
    assert re.search(r"\b(I|I'm|my|me)\b", example["template"]), "the example negative control is not first person"


def test_v3_checker_prompt_is_version_2_byte_for_byte():
    assert (V3 / "checker_prompt.txt").read_bytes() == (V2 / "checker_prompt.txt").read_bytes()
    assert common.checker_enum_problems(CHK) == []


def test_v3_generation_prompt_keeps_the_parsed_counts_and_keys():
    keys = ", ".join(f'"{k}"' for k in common.required_fields(2))
    assert f"Each line is one JSON object with exactly these keys: {keys}." in GEN
    assert f"Return exactly {common.ROWS_PER_CALL} lines." in GEN
    assert f"- {common.ROWS_PER_CALL - common.CONTROLS_PER_CALL} lines have \"control\": \"none\"." in GEN
    assert f"- {common.CONTROLS_PER_CALL} lines have \"control\": \"negative\"." in GEN
    assert f"They cover {DESIGN['concepts_per_call']} different concepts within the cell." in GEN
    assert (f"For {DESIGN['variant_pairs_per_call']} of those concepts, put a second line immediately after the first"
            in GEN)


def test_v3_rules_are_numbered_in_order_and_every_cross_reference_resolves():
    block = GEN.split("WHAT A GOOD ROW LOOKS LIKE", 1)[1].split("OUTPUT FORMAT", 1)[0]
    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", block, flags=re.M)]
    assert numbers == list(range(1, 11))
    cited = [int(n) for pair in re.findall(r"\brules? (\d+)(?: and (\d+))?", GEN) for n in pair if n]
    assert cited and set(cited) <= set(numbers), cited


def test_v3_template_holds_no_example_words():
    words = [v for value in DESIGN["prompt_examples"].values() for v in (value if isinstance(value, list) else [value])]
    assert words and all(w not in GEN for w in words)


def test_v3_states_every_new_rule():
    for rule, sentences in V3_RULES.items():
        for s in sentences:
            assert GEN.count(s) == 1, (rule, s)
    # version 2's allowance for a relative speaking about the patient is gone
    v2_gen = (V2 / "generation_prompt.txt").read_text(encoding="utf-8")
    assert "or a relative speaking about the patient" in v2_gen and "or a relative speaking about the patient" not in GEN


@pytest.mark.parametrize("seed_file", sorted(SEED_FILES))
def test_v3_every_planned_prompt_renders_clean_with_every_rule(seed_file: str, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch):
    """Plan both arms of every cell as plan_calls.py would in a run directory holding the version-3 kit, and read
    each planned prompt: no marker left, the probe endings listed exactly as design.json gives them, the example
    negative control and the cell's swap definition shown, and every version-3 rule sentence present."""
    v3 = v3_harness(tmp_path, monkeypatch)
    seeds = v3.validate_seeds(json.loads(SEED_FILES[seed_file].read_text(encoding="utf-8")))
    plan = v3.derive_plan(seeds, GEN, "0" * 64, "0" * 64)
    assert plan["harness_version"] == 2
    assert len(plan["calls"]) == len(v3.ARMS) * len(v3.cells())
    example = v3.control_example_text(v3.DESIGN)
    definitions = {t["name"]: t["definition"] for t in DESIGN["swap_types"]}
    for call in plan["calls"]:
        prompt = call["prompt"]
        assert v3.stray_marker(prompt) is None, call["id"]
        listed = re.search(r"End the template right after an article or a possessive \(([^)]*)\)", prompt)
        assert listed is not None, call["id"]
        assert [w.strip() for w in listed.group(1).split(",")] == DESIGN["probe_endings"], call["id"]
        assert example in prompt and definitions[call["swap_type"]] in prompt, call["id"]
        for rule, sentences in V3_RULES.items():
            assert all(s in prompt for s in sentences), (call["id"], rule)


def test_codebook_v0_3_records_that_the_checker_is_not_a_gate():
    rules = json.loads((CODEBOOK / "codebook_rules.json").read_text(encoding="utf-8"))
    assert rules["version"] == "0.3"
    d1 = [q for q in rules["settled_questions"] if q["id"] == "D1"]
    assert len(d1) == 1 and d1[0]["ruling"].startswith("No. Physician review in the verification app")
    assert "2026-10-04" in d1[0]["basis"] and d1[0]["examples"] == []  # run 2's rows are not in this codebook's export
    md = (CODEBOOK / "codebook_v0.3.md").read_text(encoding="utf-8")
    assert "**D1. Does the checker decide which stimuli are kept?** No." in md
    readme = (V3 / "README.md").read_text(encoding="utf-8")
    assert "decision D1 in codebook v0.3" in readme


def test_codebook_v0_2_files_are_unchanged():
    """Version 0.3 is a new codebook; version 0.2's files stay as committed, built from the rules file whose SHA-256
    they record (in the git history since the rules file moved to 0.3)."""
    pinned = {"codebook_v0.2.json": "1bcb52b0b724eca16f18997aa60fb45cad0ef59a15236eef20ec1617466d07ff",
              "codebook_v0.2.md": "5745b3b870a592170f4a2dcd365773efc72aadffb6563d86f02461dee20c85c0"}
    for name, digest in pinned.items():
        assert hashlib.sha256((CODEBOOK / name).read_bytes()).hexdigest() == digest, name
