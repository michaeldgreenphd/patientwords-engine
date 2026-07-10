"""Registry test for scripts/logits_eval.py HF_IDS - the CPU-logits model matrix.

scripts/ is not a package, so the module loads via importlib from its file
path. logits_eval imports torch/transformers lazily inside main()/measure(),
so loading the module here needs neither installed. Offline, no network.
"""

import importlib.util
import re
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "logits_eval.py"
_SPEC = importlib.util.spec_from_file_location("logits_eval", _MODULE_PATH)
logits_eval = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(logits_eval)

# The full owner-approved matrix (docs/model_matrix.md): the original four plus
# the C1/C3/C4 + B2/B3 expansion. Exact-set assertion so an accidental removal
# or a stray key both fail loudly.
EXPECTED_IDS = {
    "gemma-2-2b",
    "gemma-3-4b-it",
    "qwen3-4b",
    "qwen3-1.7b",
    "llama-3.2-3b",
    "olmo-2-1b",
    "biomistral-7b",
    "gemma-2-2b-it",
    "gemma-2-9b",
}


def test_registry_contains_all_nine_ids():
    assert set(logits_eval.HF_IDS) == EXPECTED_IDS


def test_repo_values_look_like_org_slash_repo():
    # Hugging Face repo ids: exactly one slash, sane path characters each side.
    pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
    for short_id, hf_id in logits_eval.HF_IDS.items():
        assert pattern.match(hf_id), f"{short_id!r} maps to malformed HF repo id {hf_id!r}"


def test_expansion_maps_to_approved_repos():
    # The five additions must point at the exact owner-approved repos
    # (docs/fable_week_plan.md C-table); a near-miss repo would probe the
    # wrong weights while looking green.
    assert logits_eval.HF_IDS["llama-3.2-3b"] == "meta-llama/Llama-3.2-3B"
    assert logits_eval.HF_IDS["olmo-2-1b"] == "allenai/OLMo-2-0425-1B"
    assert logits_eval.HF_IDS["biomistral-7b"] == "BioMistral/BioMistral-7B"
    assert logits_eval.HF_IDS["gemma-2-2b-it"] == "google/gemma-2-2b-it"
    assert logits_eval.HF_IDS["gemma-2-9b"] == "google/gemma-2-9b"


def test_model_loading_supply_chain_posture():
    """Tripwire: model loading must stay safetensors-only with remote code off.

    A compromised or typosquatted HF repo attacks through two doors: pickle
    .bin weights (arbitrary code on deserialize) and trust_remote_code
    (arbitrary code on load). Both must stay closed in every loader.
    """
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    for loader in ("logits_eval.py", "activation_patch.py"):
        src = (scripts_dir / loader).read_text(encoding="utf-8")
        assert "use_safetensors=True" in src, loader
        assert "trust_remote_code=False" in src, loader
    for script in scripts_dir.glob("*.py"):
        assert "trust_remote_code=True" not in script.read_text(encoding="utf-8"), script.name

def test_build_summary_start_index_default_and_offset():
    # Chunked runs (--offset) must keep the global 1-based join key: the
    # summary's start_index and each result's index are what downstream
    # consumers (urgency collector, exporter) join back to the batch file.
    s = logits_eval.build_summary("qwen3-4b", "Qwen/Qwen3-4B", [])
    assert s["start_index"] == 1
    s = logits_eval.build_summary("qwen3-4b", "Qwen/Qwen3-4B", [], start_index=61)
    assert s["start_index"] == 61


def test_offset_chunking_wiring_matches_trace_convention():
    """Regression for the run-14 timeout: a 119-pair gemma-3 batch cannot
    finish inside the 4h CI timeout, so logits_eval chunks via --offset.
    The part filename is 1-based (part_NN = offset+1) like the trace path,
    so two chunks of one batch never clobber each other, and the workflow
    heredoc must carry the key or push-path fires silently drop it."""
    src = _MODULE_PATH.read_text(encoding="utf-8")
    assert '"--offset"' in src or "'--offset'" in src
    assert 'batch_summary.part_{start_index:02d}' in src
    wf = (_MODULE_PATH.parents[1] / ".github" / "workflows" / "logits_evaluation.yml")
    text = wf.read_text(encoding="utf-8")
    assert '"offset": "0"' in text          # push-path defaults carry the key
    assert '--offset "$OFFSET"' in text     # CLI pass-through
    assert "part_%02d' $((OFFSET + 1))" in text  # part naming from offset
