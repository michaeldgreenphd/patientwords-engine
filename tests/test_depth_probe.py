"""Offline tests for the depth probe's pure functions.

No torch, no interp-engine, no network: everything under test takes spreads and
a vocabulary as plain data, which is why the measurement seam
(``measure_depth``) is separate from the scoring.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dp = _load("depth_probe")

# Abstract placeholders only: real terms live in the tier data file.
VOCAB = {
    "alpha": {"tier": 4},
    "bravo": {"tier": 2},
    "charlie": {"tier": 0},
    "delta": {"tier": None},
}


def test_bare_strips_the_graph_label_wrapper():
    assert dp.bare('Output " alpha"') == "alpha"
    assert dp.bare("alpha") == "alpha"
    assert dp.bare('Output ""') is None
    assert dp.bare(None) is None


def test_tier_of_returns_none_for_unknown_and_excluded():
    assert dp.tier_of("alpha", VOCAB) == 4
    assert dp.tier_of("delta", VOCAB) is None      # explicitly excluded
    assert dp.tier_of("echo", VOCAB) is None       # unassigned
    assert dp.tier_of(None, VOCAB) is None


def test_expected_tier_is_probability_weighted_over_assigned_mass_only():
    spread = [["alpha", 0.5], ["bravo", 0.3], ["echo", 0.2]]
    tier, cov = dp.expected_tier(spread, VOCAB, min_cov=0.3)
    assert cov == 0.8                              # 'echo' carries no tier
    assert tier == round((0.5 * 4 + 0.3 * 2) / 0.8, 4)


def test_expected_tier_refuses_below_min_coverage():
    spread = [["echo", 0.9], ["alpha", 0.1]]
    tier, cov = dp.expected_tier(spread, VOCAB, min_cov=0.3)
    assert tier is None and cov == 0.1


def test_expected_tier_matches_urgency_shift_on_shared_input():
    """The published analysis is the reference implementation; this probe must
    not quietly define a second, different 'expected tier'.

    urgency_shift.py runs its whole analysis at import (it is a script), so the
    reference is obtained by exec'ing just its expected_tier/tier/bare
    definitions against the same vocabulary.
    """
    src = (SCRIPTS / "urgency_shift.py").read_text(encoding="utf-8")
    wanted = ("def tier(", "def bare(", "def expected_tier(")
    blocks = []
    for marker in wanted:
        i = src.index(marker)
        j = src.index("\ndef ", i + 1)
        blocks.append(src[i:j])
    ns = {"vocab": VOCAB, "re": __import__("re")}
    exec("\n\n".join(blocks), ns)  # noqa: S102 - our own repo's source

    spread = [["alpha", 0.44], ["bravo", 0.31], ["charlie", 0.15], ["echo", 0.10]]
    ref_tier, ref_cov = ns["expected_tier"](spread, 0.3)
    probe_tier, probe_cov = dp.expected_tier(spread, VOCAB, min_cov=0.3)
    assert round(ref_tier, 4) == probe_tier
    assert round(ref_cov, 4) == probe_cov


def test_depth_curve_is_ordered_and_carries_coverage():
    spreads = {
        5: [["alpha", 0.9], ["echo", 0.1]],
        0: [["echo", 0.95], ["alpha", 0.05]],
        2: [["bravo", 0.7], ["charlie", 0.3]],
    }
    curve = dp.depth_curve(spreads, VOCAB, min_cov=0.3)
    assert [r["layer"] for r in curve] == [0, 2, 5]
    assert curve[0]["expected_tier"] is None       # below coverage
    assert curve[0]["top"] == "echo"
    assert curve[2]["expected_tier"] == 4.0


def test_curve_gap_is_patient_minus_clinical_and_none_propagates():
    clinical = [{"layer": 0, "expected_tier": 3.0}, {"layer": 1, "expected_tier": None}]
    patient = [{"layer": 0, "expected_tier": 1.0}, {"layer": 1, "expected_tier": 2.0}]
    gap = dp.curve_gap(clinical, patient)
    assert gap[0]["gap"] == -2.0                   # patient sits lower
    assert gap[1]["gap"] is None


def test_first_divergence_takes_the_shallowest_layer_over_threshold():
    gap = [{"layer": 0, "gap": 0.1}, {"layer": 1, "gap": None},
           {"layer": 2, "gap": -0.6}, {"layer": 3, "gap": -1.2}]
    assert dp.first_divergence(gap, 0.25) == 2
    assert dp.first_divergence(gap, 5.0) is None


def test_build_result_summarizes_both_curves():
    pair = {"top_prompt": "C", "bottom_prompt": "P"}
    clinical = [{"layer": 0, "expected_tier": 3.0}, {"layer": 1, "expected_tier": 3.0}]
    patient = [{"layer": 0, "expected_tier": 3.0}, {"layer": 1, "expected_tier": 1.0}]
    r = dp.build_result(7, pair, (clinical, patient), threshold=0.25)
    assert r["index"] == 7
    assert r["first_divergence_layer"] == 1
    assert r["final_gap"] == -2.0
    assert r["max_abs_gap"] == 2.0
    assert r["layers_informative"] == 2 and r["layers_measured"] == 2


def test_build_summary_labels_the_lens_and_carries_instrument_provenance():
    s = dp.build_summary("m", "org/m", [], 1, min_cov=0.3, topk=10, threshold=0.25,
                         tiers_path="data/urgency_tiers.draft.json",
                         tiers_status="owner-reviewed v1 - domain review pending")
    assert s["lens"] == "logit_lens"
    assert s["mode"] == "depth_probe"
    assert s["source_set"] is None
    assert "not the registered Jacobian lens" in s["instrument"]["note"]
    assert s["instrument"]["tiers_status"].startswith("owner-reviewed")
    assert s["inference"]["device"] == "cpu"


def test_resolve_layers_forms():
    assert dp.resolve_layers("all", 4) == [0, 1, 2, 3]
    assert dp.resolve_layers("every:2", 5) == [0, 2, 4]
    assert dp.resolve_layers("0,3", 4) == [0, 3]


def test_resolve_layers_rejects_out_of_range():
    try:
        dp.resolve_layers("0,99", 4)
    except ValueError as exc:
        assert "out of range" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_part_filename_uses_the_global_offset(tmp_path):
    """Chunked runs must not clobber: the part number is the 1-based start."""
    assert f"depth_probe.part_{14:02d}.json" == "depth_probe.part_14.json"


# --- CI wiring (the params heredoc cannot be exercised, only read) -----------

WORKFLOW = ROOT / ".github" / "workflows" / "logits_evaluation.yml"


def _workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_yaml_still_parses_and_exposes_the_new_outputs():
    import yaml
    doc = yaml.safe_load(_workflow_text())
    outputs = doc["jobs"]["params"]["outputs"]
    assert "mode" in outputs and "layers" in outputs


def test_push_path_defaults_dict_contains_every_trigger_key():
    """CI silently ignores unknown keys, and a key missing from the heredoc
    defaults dict is silently dropped on the push path."""
    fire = _load("fire_trigger")
    text = _workflow_text()
    params_run = text[text.index("defaults = {"):text.index("EOF\n\n  eval:")]
    for key in fire.KNOWN_KEYS["logits-eval"]:
        assert f'"{key}"' in params_run, f"workflow defaults dict is missing {key}"


def test_depth_mode_writes_a_distinct_dir_and_filename():
    """A depth probe is a different instrument; it must not land in the
    behavioral batch_summary set that the frontend exporter globs. The readout
    window is in the directory name so re-running at a different topk cannot
    overwrite an earlier window's results."""
    text = _workflow_text()
    assert 'OUT_DIR=trace_out/depth_k${TOPK}_${STEM}__${MODEL}' in text
    assert 'SUMMARY_FILE=depth_probe.$PART.json' in text
    assert 'SUMMARY_FILE=batch_summary.$PART.json' in text


def test_exactly_one_measure_step_runs_per_mode():
    """The lane carries three measure steps and each mode must select exactly
    one. A negated guard (`mode != 'depth'`) satisfied "only one" while there
    were two modes, and would silently run the behavioral step under a third;
    the check is therefore per-mode arithmetic, not a string match.
    """
    import yaml

    steps = yaml.safe_load(_workflow_text())["jobs"]["eval"]["steps"]
    measure = {s.get("name", ""): s.get("if", "") for s in steps
               if s.get("name", "").startswith(("Measure ", "Re-measure "))}
    assert len(measure) == 3, measure
    for mode in ("logits", "depth", "verify"):
        selected = [name for name, cond in measure.items() if f"mode == '{mode}'" in cond]
        assert len(selected) == 1, f"mode {mode!r} selects {selected}"


def test_verify_mode_writes_a_filename_no_behavioral_collector_globs():
    """A verification run re-measures pairs the logits lane already published.
    Landing it as batch_summary* would make the collectors read one set of
    prompts as two independent measurements."""
    text = _workflow_text()
    assert "OUT_DIR=trace_out/verify_${STEM}__${MODEL}" in text
    assert "SUMMARY_FILE=verify_summary.$PART.json" in text


def test_verify_mode_installs_interp_engine():
    """It measures through interp-engine; without the install step it would
    fail on import after the model download."""
    import yaml

    steps = yaml.safe_load(_workflow_text())["jobs"]["eval"]["steps"]
    install = next(s for s in steps if "Install interp-engine" in s.get("name", ""))
    assert "mode == 'verify'" in install["if"]
    assert "mode == 'depth'" in install["if"]


def test_verify_is_an_accepted_mode_value():
    """The params job hard-errors on an unknown mode, so a trigger asking for
    verify has to be listed there or the lane refuses the run."""
    assert '"logits", "depth", "verify"' in _workflow_text()


def test_verify_dtype_has_a_push_path_default():
    """The push-path `defaults` dict must contain every trigger key: a key
    missing there is dropped from a trigger file without error."""
    assert '"dtype": "float32"' in _workflow_text()


def test_interp_engine_is_installed_without_the_vllm_extra():
    """[vllm] would pull GB of CUDA wheels onto a CPU runner and cannot work there."""
    text = _workflow_text()
    assert "pip install --quiet -c constraints.txt interp-engine" in text
    assert "interp-engine[vllm]" not in text


def test_interp_engine_is_pinned_in_constraints():
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    assert "interp-engine==" in constraints
    assert "einops==" in constraints


# --- regression: the 2026-09-02 double-wrap crash ---------------------------

def test_measure_depth_passes_the_model_through_untouched(monkeypatch):
    """`layer_logits` is a sync free function that wraps the model itself.
    Handing it a `sync_model(...)` facade instead of the raw model raised
    'TypeError: A coroutine object is required' on the first pilot run.
    """
    import types

    seen = {}
    sentinel = types.SimpleNamespace(
        to_tokens=lambda p: [[1, 2, 3]],
        to_string=lambda i: f"tok{i}",
    )

    class FakeRow:
        def float(self):
            return self

    class FakeLogits:
        """[n_rows, vocab]; only the last row is read."""
        def __getitem__(self, idx):
            assert idx == -1, "measure_depth must read the LAST prompt position"
            return FakeRow()

    def fake_layer_logits(model, tokens, layers_by_type):
        seen["model"] = model
        seen["layers"] = layers_by_type
        return {"logit_lens": {0: FakeLogits()}}

    fake_ie = types.ModuleType("interp_engine")
    fake_ie.layer_logits = fake_layer_logits
    fake_torch = types.ModuleType("torch")
    fake_torch.softmax = lambda logits, dim: "probs"
    fake_torch.topk = lambda probs, k: types.SimpleNamespace(
        values=types.SimpleNamespace(tolist=lambda: [0.6, 0.4]),
        indices=types.SimpleNamespace(tolist=lambda: [7, 8]),
    )
    monkeypatch.setitem(sys.modules, "interp_engine", fake_ie)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    spreads = dp.measure_depth(sentinel, "a prompt", [0], topk=2)
    assert seen["model"] is sentinel, "measure_depth must not re-wrap the model"
    assert seen["layers"] == {"logit_lens": [0]}
    assert spreads == {0: [["tok7", 0.6], ["tok8", 0.4]]}


def test_main_uses_sync_model_only_for_lifecycle():
    """Source-level guard for the same bug: the object handed to measure_depth
    must be the raw load_model result, not the sync facade."""
    src = (SCRIPTS / "depth_probe.py").read_text(encoding="utf-8")
    assert "model = load_model(" in src
    assert "sync_model(load_model(" not in src
    assert "lifecycle = sync_model(model)" in src


def test_topk_is_a_trigger_param_and_reaches_the_script():
    """Step 1 of the integration plan re-runs the same measurement through a
    wider readout window; the window must be settable from the trigger."""
    fire = _load("fire_trigger")
    text = _workflow_text()
    assert "topk" in fire.KNOWN_KEYS["logits-eval"]
    assert '"topk": "10"' in text                      # push-path default
    assert '--topk "$TOPK"' in text                    # actually passed through
