"""Offline unit tests for scripts/multi_instrument_join.py on synthetic run trees.

Uses abstract placeholder strings only (zero domain vocabulary) and creates all
inputs and outputs inside pytest's temporary directory outside Git checkouts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import multi_instrument_join as mij
from scripts.experiments.common import Refusal, prompt_digest
from scripts.tierb_split import SEAL_CONFIG_EXIT

FORBIDDEN_KEY_SUBSTRINGS = (
    "combined",
    "composite",
    "overall",
    "consensus",
    "score",
    "understanding",
    "merged",
    "aggregate",
)

PLACEHOLDER_STRINGS = (
    "alpha formal prompt one",
    "alpha casual prompt one",
    "alpha translated prompt one",
    "alpha formal prompt one extended",
    "beta formal prompt two",
    "beta casual prompt two",
    "holdout sentinel phrase zero",
    " omega",
    " delta",
    "completion token alpha",
    "L0_F1 -> Output \" omega\"",
)


def _find_holdout_prompt(prefix: str = "synthetic holdout candidate ") -> str:
    """Deterministically find an abstract string whose SHA-1 mod 10 equals 0."""
    for i in range(200):
        candidate = f"{prefix}{i}"
        if int(hashlib.sha1(candidate.encode("utf-8")).hexdigest(), 16) % 10 == 0:
            return candidate
    raise AssertionError("failed to construct sha1 mod 10 == 0 string")


def _find_explore_prompt(prefix: str = "synthetic explore candidate ") -> str:
    """Deterministically find an abstract string whose SHA-1 mod 10 is nonzero."""
    for i in range(200):
        candidate = f"{prefix}{i}"
        if int(hashlib.sha1(candidate.encode("utf-8")).hexdigest(), 16) % 10 != 0:
            return candidate
    raise AssertionError("failed to construct sha1 mod 10 != 0 string")


def _keys_of(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys_of(v)}
    if isinstance(value, list):
        return {k for item in value for k in _keys_of(item)}
    return set()


def _write_json(path: Path, obj: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return path


def _setup_seal_env(root: Path) -> tuple[Path, Path, str, str]:
    """Create a minimal valid dashboard and Tier B batch so sealed_pair evaluates cleanly."""
    sim_dir = root / "sim_inputs"
    dash_path = root / "dashboard_cfg.json"
    holdout_prompt = _find_holdout_prompt()
    explore_prompt = _find_explore_prompt()
    _write_json(dash_path, {"tierb": {"start_utc": "2026-07-10T00:00:00Z"}})
    _write_json(
        sim_dir / "pairs_20260710T120000Z.json",
        [
            {"top_prompt": holdout_prompt, "bottom_prompt": "alpha casual prompt one"},
            {"top_prompt": explore_prompt, "bottom_prompt": "beta casual prompt two"},
        ],
    )
    return dash_path, sim_dir, holdout_prompt, explore_prompt


def _case_at(doc: dict[str, Any], stem: str, index: int, model: str) -> dict[str, Any]:
    return next(c for c in doc["cases"] if c["key"] == {"stem": stem, "index": index, "model": model})


def test_all_eight_instruments_and_mixed_backend_directory(tmp_path: Path) -> None:
    dash, sim, _holdout, explore = _setup_seal_env(tmp_path)
    _write_json(
        sim / "pairs_20260701T000000Z.json",
        [
            {"top_prompt": "alpha formal prompt one", "bottom_prompt": "alpha casual prompt one"},
            {"top_prompt": explore, "bottom_prompt": "beta casual prompt two"},
        ],
    )
    trace_root = tmp_path / "traces"
    prompts_1 = {"clinical": "alpha formal prompt one", "patient": "alpha casual prompt one"}
    prompts_2 = {"clinical": explore, "patient": "beta casual prompt two"}
    rev_sha = "a" * 40

    # 1. Mixed directory holding BOTH hosted_graph (index 1) and cpu_logits (index 1 and 2).
    _write_json(
        trace_root / "pairs_20260701T000000Z__toy-model" / "batch_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "hosted",
            "graph_model": "toy-model",
            "source_set": "toy-source-set",
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": {**prompts_1, "translated": "alpha translated prompt one"},
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.42, "patient": 0.11},
                    "language_penalty": -0.31,
                    "clinical_mass": {"clinical": 0.5, "patient": 0.2},
                    "error_share": {"clinical": 0.1, "patient": 0.2},
                    "circuit_diff": {"shared_features": 4, "unique_to_a": 3, "unique_to_b": 5},
                    "top_path": {"clinical": 'L0_F1 -> Output " omega"', "patient": 'L0_F2 -> Output " delta"'},
                    "target_read": {
                        "rule": "exact_token/2026-10-07",
                        "intended_target": " omega",
                        "measured_token": " omega",
                        "match": "exact",
                        "substituted": False,
                        "reference_side": "clinical",
                    },
                    "mitigation_recovery": 0.18,
                }
            ],
        },
    )
    _write_json(
        trace_root / "pairs_20260701T000000Z__toy-model" / "batch_summary.part_02.json",
        {
            "mode": "2panel",
            "backend": "logits",
            "graph_model": "toy-model",
            "inference": {"dtype": "bfloat16", "device": "cpu", "revision": rev_sha, "environment": "github-actions"},
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": prompts_1,
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.4201, "patient": 0.1102},
                    "language_penalty": -0.3099,
                    "flipped": True,
                    "anchor_fallback": False,
                    "predictive_spread": {
                        "clinical": [['Output " omega"', 0.4201]],
                        "patient": [['Output " delta"', 0.35]],
                    },
                },
                {
                    "index": 2,
                    "mode": "2panel",
                    "prompts": prompts_2,
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.3, "patient": 0.25},
                    "language_penalty": -0.05,
                },
            ],
        },
    )

    # Non-summary probe and mitigation cost sidecars are skipped, not rejected.
    _write_json(trace_root / "pairs_20260701T000000Z__toy-model" / "mitigation.part_01.report.json", {"cost_usd": 0.0})
    _write_json(trace_root / "pairs_20260701T000000Z__jlens_toy-model" / "jlens_probe.json", {"ok": True})
    _write_json(trace_root / "spec_a__jsteer_toy-model" / "jsteer_probe.json", {"ok": True})

    # 3. Activation patching
    _write_json(
        trace_root / "pairs_20260701T000000Z__patch_toy-model" / "batch_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "activation_patch",
            "graph_model": "toy-model",
            "inference": {"dtype": "bfloat16", "device": "cpu", "revision": None},
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": prompts_1,
                    "target_token": " omega",
                    "probabilities": {"clinical": 0.42, "patient": 0.11},
                    "language_penalty": -0.31,
                    "patching": {
                        "hook_point": "blocks.{layer}.hook_resid_post",
                        "metric": "normalized_prob_recovery",
                        "placeholder": False,
                        "align": "shared_suffix",
                        "clean_prob": 0.42,
                        "corrupt_prob": 0.11,
                        "layers": [0, 1],
                        "positions": [{"index": 3, "token": " one", "aligned_clean_index": 3}],
                        "recovery": [[0.0], [1.0]],
                        "patched_prob": [[0.11], [0.42]],
                    },
                }
            ],
        },
    )

    # 4 & 5. Jacobian lens and Logit lens
    for sub_dir, lens_type in (
        ("pairs_20260701T000000Z__jlens_toy-model", "JACOBIAN_LENS"),
        ("pairs_20260701T000000Z__loglens_toy-model", "LOGIT_LENS"),
    ):
        _write_json(
            trace_root / sub_dir / "jlens_summary.part_01.json",
            {
                "mode": "jlens",
                "backend": "jlens-hosted",
                "graph_model": "toy-model",
                "lens_type": lens_type,
                "top_n": 8,
                "results": [
                    {
                        "index": 1,
                        "prompts": prompts_1,
                        "target_token": " omega",
                        "parse_status": {"clinical": "ok", "patient": "ok"},
                        "first_layer": {"clinical": 0, "patient": None},
                        "last_layer_rank": {"clinical": 1, "patient": None},
                        "patient_depth_class": "absent",
                        "depth": {
                            "clinical": [{"layer": 0, "target_rank": 1, "match": "exact", "top1": " omega"}],
                            "patient": [{"layer": 0, "target_rank": None, "match": None, "top1": " delta"}],
                        },
                    }
                ],
            },
        )

    # 6. Lens steering (joins via dataset + spec_index, not run_dir + index)
    _write_json(
        trace_root / "spec_a__jsteer_toy-model" / "jsteer_summary.part_01.json",
        {
            "mode": "jsteer",
            "backend": "jlens-hosted",
            "graph_model": "toy-model",
            "spec": "spec_a.json",
            "layers": [1],
            "strengths": [0.5],
            "top_n": 8,
            "results": [
                {
                    "index": 99,
                    "dataset": "pairs_20260701T000000Z",
                    "spec_index": 1,
                    "class": "absent",
                    "target_token": " omega",
                    "winner_token": " delta",
                    "calls": {
                        "baseline": {
                            "first_layer": None,
                            "final_rank": None,
                            "completion": "completion token alpha",
                            "parse_status": "ok",
                        }
                    },
                }
            ],
        },
    )

    # 7. Depth probe at two topk settings (depth_ and depth_k200_ strip to same stem, keyed by topk)
    for prefix, topk in (("depth_", 10), ("depth_k200_", 200)):
        _write_json(
            trace_root / f"{prefix}pairs_20260701T000000Z__toy-model" / "depth_probe.part_01.json",
            {
                "mode": "depth_probe",
                "backend": "interp-engine-eager",
                "graph_model": "toy-model",
                "instrument": {"topk": topk, "min_coverage": 0.3, "divergence_threshold": 0.25},
                "inference": {"dtype": "bfloat16", "device": "cpu", "revision": rev_sha},
                "results": [
                    {
                        "index": 1,
                        "prompts": prompts_1,
                        "first_divergence_layer": 1,
                        "final_gap": 0.4,
                        "max_abs_gap": 0.4,
                        "layers_informative": 2,
                        "layers_measured": 2,
                        "gap": [0.0, 0.4],
                        "curves": {
                            "clinical": [{"layer": 0, "expected_tier": 2.0, "coverage": 0.5, "top": " omega"}],
                            "patient": [{"layer": 0, "expected_tier": 1.6, "coverage": 0.5, "top": " delta"}],
                        },
                    }
                ],
            },
        )

    # 8. Float32 verify (verify_ prefix stripped)
    _write_json(
        trace_root / "verify_pairs_20260701T000000Z__toy-model" / "verify_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "interp-engine",
            "graph_model": "toy-model",
            "inference": {"dtype": "float32", "device": "cpu", "revision": rev_sha},
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": prompts_1,
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.42, "patient": 0.11},
                    "language_penalty": -0.31,
                    "token_parity": {"clinical": True, "patient": True},
                }
            ],
        },
    )

    out_path = tmp_path / "joined.json"
    exit_code = mij.main(
        [
            "--trace-root",
            str(trace_root),
            "--dashboard",
            str(dash),
            "--simulated-dir",
            str(sim),
            "--out",
            str(out_path),
        ]
    )
    assert exit_code == 0
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    mij.validate_output_document(doc)

    assert doc["counts"]["part_files_read"] == 9
    assert doc["counts"]["non_summary_json_skipped"] == 3
    assert doc["counts"]["case_count"] == 2
    assert doc["counts"]["by_instrument_count"] == {"1": 1, "8": 1}

    case1 = _case_at(doc, "pairs_20260701T000000Z", 1, "toy-model")
    assert case1["instrument_count"] == 8
    assert case1["instruments_present"] == list(mij.INSTRUMENT_ORDER)
    assert set(case1["instruments"]["depth_probe"]["by_topk"]) == {"10", "200"}
    assert case1["instruments"]["depth_probe"]["duplicate_parts"] is False
    assert case1["instruments"]["depth_probe"]["value_conflict"] is False

    checks = case1["checks"]
    assert checks["prompt_sha256_match"] is True
    assert checks["prompt_missing_on_instrument"] is True  # lens_steering records no prompt
    assert checks["target_label_match"] is True
    assert checks["target_label_raw_match"] is False  # 'Output " omega"' vs ' omega'
    assert checks["target_label_missing_on_instrument"] is False  # depth_probe does not count as missing target
    assert checks["hosted_target_read_recorded"] is True
    assert checks["revision_recorded"] is False  # hosted & patch lacked revision
    assert checks["any_revision_recorded"] is True
    assert checks["revisions_match"] is True
    assert checks["duplicate_parts_present"] is False
    assert checks["duplicate_value_conflict"] is False

    # Zero prompt/target/completion prose and zero forbidden cross-instrument keys anywhere in output.
    serialized = out_path.read_text(encoding="utf-8")
    assert not [phrase for phrase in PLACEHOLDER_STRINGS if phrase in serialized]
    bad_keys = [k for k in _keys_of(doc) if any(word in k.lower() for word in FORBIDDEN_KEY_SUBSTRINGS)]
    assert bad_keys == []


def test_context_stimulus_set_and_derived_batches_stay_unmerged(tmp_path: Path) -> None:
    dash, sim, _holdout, explore = _setup_seal_env(tmp_path)
    _write_json(
        sim / "base_set.json",
        [{"top_prompt": "alpha formal prompt one", "bottom_prompt": "alpha casual prompt one"}],
    )
    _write_json(
        sim / "base_set__context.json",
        [
            {
                "top_prompt": explore,
                "bottom_prompt": "beta casual prompt two",
                "generation": {"derived_from": {"batch": "base_set.json", "index": 1}},
            }
        ],
    )
    _write_json(
        sim / "downgrade_subset.json",
        [
            {
                "top_prompt": "alpha formal prompt one",
                "bottom_prompt": "alpha casual prompt one",
                "generation": {"downgrade_source": {"batch": "base_set", "index": 1, "models": ["toy-model"]}},
            }
        ],
    )

    trace_root = tmp_path / "traces"
    for dir_name, prompts in (
        ("base_set", {"clinical": "alpha formal prompt one", "patient": "alpha casual prompt one"}),
        ("base_set__context", {"clinical": explore, "patient": "beta casual prompt two"}),
        ("downgrade_subset", {"clinical": "alpha formal prompt one", "patient": "alpha casual prompt one"}),
    ):
        _write_json(
            trace_root / dir_name / "batch_summary.part_01.json",
            {
                "mode": "2panel",
                "backend": "hosted",
                "graph_model": "toy-model",
                "results": [
                    {
                        "index": 1,
                        "mode": "2panel",
                        "prompts": prompts,
                        "target_token": 'Output " omega"',
                        "probabilities": {"clinical": 0.5, "patient": 0.2},
                    }
                ],
            },
        )
    _write_json(
        trace_root / "base_set__context__jlens_toy-model" / "jlens_summary.part_01.json",
        {
            "mode": "jlens",
            "backend": "jlens-hosted",
            "graph_model": "toy-model",
            "lens_type": "JACOBIAN_LENS",
            "results": [
                {
                    "index": 1,
                    "prompts": {"clinical": explore, "patient": "beta casual prompt two"},
                    "target_token": " omega",
                    "depth": {"clinical": [], "patient": []},
                }
            ],
        },
    )

    doc = mij.build_multi_instrument_records(
        trace_root=trace_root,
        data_dirs=[sim],
        dashboard_path=dash,
        simulated_dir=sim,
    )
    assert doc["counts"]["case_count"] == 3
    assert doc["counts"]["derived_cases_with_source_key"] == 2

    base_case = _case_at(doc, "base_set", 1, "toy-model")
    ctx_case = _case_at(doc, "base_set__context", 1, "toy-model")
    dg_case = _case_at(doc, "downgrade_subset", 1, "toy-model")

    assert base_case["instrument_count"] == 1
    assert base_case["source_key"] is None

    # __context stays its own stimulus set and joins its own jlens run without merging into base_set.
    assert ctx_case["instrument_count"] == 2
    assert ctx_case["source_key"] == {"stem": "base_set", "index": 1, "model": "toy-model", "via": "derived_from"}
    assert ctx_case["derived_from"] == {
        "batch": "base_set",
        "raw_batch": "base_set.json",
        "index": 1,
        "variant": None,
        "quadrant": None,
    }

    assert dg_case["instrument_count"] == 1
    assert dg_case["source_key"] == {"stem": "base_set", "index": 1, "model": "toy-model", "via": "downgrade_source"}
    assert dg_case["downgrade_source"] == {
        "batch": "base_set",
        "raw_batch": "base_set",
        "index": 1,
        "models": ["toy-model"],
    }


def test_duplicate_parts_retain_all_candidates_in_numeric_order_and_flag_conflicts(tmp_path: Path) -> None:
    dash, sim, _holdout, explore = _setup_seal_env(tmp_path)
    trace_root = tmp_path / "traces"
    prompts = {"clinical": explore, "patient": "beta casual prompt two"}

    # Index 1: identical values across part_02 and part_10 -> duplicate_parts=True, value_conflict=False.
    # Index 2: differing probabilities across part_11 and part_100 -> numeric order preserved, value_conflict=True.
    for part_name, prob_idx2 in (("part_10.json", 0.3), ("part_02.json", 0.3)):
        _write_json(
            trace_root / "dup_set__toy-model" / f"batch_summary.{part_name}",
            {
                "mode": "2panel",
                "backend": "logits",
                "graph_model": "toy-model",
                "inference": {"revision": "b" * 40},
                "results": [
                    {
                        "index": 1,
                        "mode": "2panel",
                        "prompts": prompts,
                        "target_token": 'Output " omega"',
                        "probabilities": {"clinical": prob_idx2, "patient": 0.1},
                    }
                ],
            },
        )

    for part_name, prob_clin in (("part_100.json", 0.45), ("part_11.json", 0.25)):
        _write_json(
            trace_root / "dup_set__toy-model" / f"batch_summary.{part_name}",
            {
                "mode": "2panel",
                "backend": "logits",
                "graph_model": "toy-model",
                "inference": {"revision": "b" * 40},
                "results": [
                    {
                        "index": 2,
                        "mode": "2panel",
                        "prompts": prompts,
                        "target_token": 'Output " omega"',
                        "probabilities": {"clinical": prob_clin, "patient": 0.1},
                    }
                ],
            },
        )

    doc = mij.build_multi_instrument_records(
        trace_root=trace_root,
        dashboard_path=dash,
        simulated_dir=sim,
    )
    case_same = _case_at(doc, "dup_set", 1, "toy-model")
    cands_same = case_same["instruments"]["cpu_logits"]["candidates"]
    assert [Path(c["provenance"]["part_path"]).name for c in cands_same] == [
        "batch_summary.part_02.json",
        "batch_summary.part_10.json",
    ]
    assert case_same["checks"]["duplicate_parts_present"] is True
    assert case_same["checks"]["duplicate_value_conflict"] is False

    case_diff = _case_at(doc, "dup_set", 2, "toy-model")
    cands_diff = case_diff["instruments"]["cpu_logits"]["candidates"]
    assert [Path(c["provenance"]["part_path"]).name for c in cands_diff] == [
        "batch_summary.part_11.json",
        "batch_summary.part_100.json",
    ]
    assert [c["values"]["probabilities"]["clinical"] for c in cands_diff] == [0.25, 0.45]
    assert case_diff["checks"]["duplicate_parts_present"] is True
    assert case_diff["checks"]["duplicate_value_conflict"] is True


def test_prompt_and_target_mismatch_flags_from_recorded_strings(tmp_path: Path) -> None:
    dash, sim, _holdout, explore = _setup_seal_env(tmp_path)
    trace_root = tmp_path / "traces"

    # Hosted row extended prompt and fell back to another target; index 2 is screened_out (target_token: None).
    _write_json(
        trace_root / "mismatch_set" / "batch_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "hosted",
            "graph_model": "toy-model",
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": {"clinical": "alpha formal prompt one extended", "patient": "alpha casual prompt one"},
                    "target_token": 'Output " delta"',
                    "probabilities": {"clinical": 0.2, "patient": 0.1},
                },
                {
                    "index": 2,
                    "mode": "2panel",
                    "prompts": {"clinical": explore, "patient": "beta casual prompt two"},
                    "target_token": None,
                    "probabilities": {"clinical": None, "patient": None},
                    "screening": {"status": "screened_out"},
                },
            ],
        },
    )
    _write_json(
        trace_root / "mismatch_set__toy-model" / "batch_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "logits",
            "graph_model": "toy-model",
            "inference": {"revision": "1" * 40},
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": {"clinical": "alpha formal prompt one", "patient": "alpha casual prompt one"},
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.3, "patient": 0.1},
                },
                {
                    "index": 2,
                    "mode": "2panel",
                    "prompts": {"clinical": explore, "patient": "beta casual prompt two"},
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.3, "patient": 0.1},
                },
            ],
        },
    )

    doc = mij.build_multi_instrument_records(
        trace_root=trace_root,
        dashboard_path=dash,
        simulated_dir=sim,
    )
    c1 = _case_at(doc, "mismatch_set", 1, "toy-model")
    assert c1["checks"]["prompt_sha256_match"] is False
    assert c1["checks"]["target_label_match"] is False
    assert c1["checks"]["target_label_raw_match"] is False
    assert c1["checks"]["hosted_target_read_recorded"] is False

    c2 = _case_at(doc, "mismatch_set", 2, "toy-model")
    assert c2["checks"]["prompt_sha256_match"] is True
    assert c2["checks"]["target_label_match"] is None  # only 1 instrument recorded a target string
    assert c2["checks"]["target_label_missing_on_instrument"] is True
    assert (
        c2["instruments"]["cpu_logits"]["candidates"][0]["provenance"]["target_label_sha256"]
        == prompt_digest(" omega")
    )


def test_seal_excludes_holdout_pairs_propagates_across_runs_and_fails_closed_on_seal_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dash, sim, holdout_prompt, explore_prompt = _setup_seal_env(tmp_path)
    probe_holdout = _find_holdout_prompt("probe extended holdout ")

    # Derived batch pointing to index 1 (sealed) of pairs_20260710T120000Z.
    _write_json(
        sim / "derived_set.json",
        [
            {
                "top_prompt": explore_prompt,
                "bottom_prompt": "beta casual prompt two",
                "generation": {"derived_from": {"batch": "pairs_20260710T120000Z", "index": 1}},
            }
        ],
    )

    trace_root = tmp_path / "traces"
    # Index 1 is sealed via accepted prompt; Index 2 is unsealed in logits, but probe-extended to holdout in hosted!
    _write_json(
        trace_root / "pairs_20260710T120000Z__toy-model" / "batch_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "logits",
            "graph_model": "toy-model",
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": {"clinical": holdout_prompt, "patient": "alpha casual prompt one"},
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.4, "patient": 0.2},
                },
                {
                    "index": 2,
                    "mode": "2panel",
                    "prompts": {"clinical": explore_prompt, "patient": "beta casual prompt two"},
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.4, "patient": 0.2},
                },
            ],
        },
    )
    _write_json(
        trace_root / "pairs_20260710T120000Z" / "batch_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "hosted",
            "graph_model": "other-model",
            "results": [
                {
                    "index": 2,
                    "mode": "2panel",
                    "prompts": {"clinical": probe_holdout, "patient": "beta casual prompt two"},
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.4, "patient": 0.2},
                }
            ],
        },
    )
    _write_json(
        trace_root / "derived_set__toy-model" / "batch_summary.part_01.json",
        {
            "mode": "2panel",
            "backend": "logits",
            "graph_model": "toy-model",
            "results": [
                {
                    "index": 1,
                    "mode": "2panel",
                    "prompts": {"clinical": explore_prompt, "patient": "beta casual prompt two"},
                    "target_token": 'Output " omega"',
                    "probabilities": {"clinical": 0.4, "patient": 0.2},
                }
            ],
        },
    )

    doc = mij.build_multi_instrument_records(
        trace_root=trace_root,
        data_dirs=[sim],
        dashboard_path=dash,
        simulated_dir=sim,
    )
    # Pair 1 sealed directly; Pair 2 sealed across models via hosted probe extension; derived_set#1 sealed via source!
    assert doc["cases"] == []
    assert doc["counts"]["sealed_pairs_excluded"] == 3
    assert doc["counts"]["sealed_cases_excluded"] == 4
    assert holdout_prompt not in json.dumps(doc)
    assert probe_holdout not in json.dumps(doc)

    # Missing dashboard triggers SealError -> CLI returns SEAL_CONFIG_EXIT (2) and writes nothing.
    bad_out = tmp_path / "never_written.json"
    code = mij.main(
        [
            "--trace-root",
            str(trace_root),
            "--dashboard",
            str(tmp_path / "missing_dashboard.json"),
            "--simulated-dir",
            str(sim),
            "--out",
            str(bad_out),
        ]
    )
    captured = capsys.readouterr()
    assert code == SEAL_CONFIG_EXIT
    assert "CONFIG ERROR:" in captured.err
    assert not bad_out.exists()


def test_output_guard_refuses_git_checkout_and_protected_roots(tmp_path: Path) -> None:
    dash, sim, _holdout, _explore = _setup_seal_env(tmp_path)
    trace_root = tmp_path / "traces"
    trace_root.mkdir()

    # Inside a Git checkout without --allow-root is refused.
    fake_repo = tmp_path / "repo_checkout"
    (fake_repo / ".git").mkdir(parents=True)
    with pytest.raises(Refusal) as exc_git:
        mij.write_records(fake_repo / "out.json", {"schema_version": mij.SCHEMA_VERSION, "engine_commit": None, "counts": {}, "cases": []})
    assert exc_git.value.code == "git_checkout"

    # Protected directory names are refused even outside Git checkouts and even with allow_roots.
    for protected in ("trace_out", "data", "pilot", "ops"):
        target = tmp_path / protected / "joined.json"
        code = mij.main(
            [
                "--trace-root",
                str(trace_root),
                "--dashboard",
                str(dash),
                "--simulated-dir",
                str(sim),
                "--allow-root",
                str(tmp_path),
                "--out",
                str(target),
            ]
        )
        assert code == mij.EXIT_REFUSED
        assert not target.exists()


def test_quadrant_dialect_modes_and_unknown_instrument_refusal(tmp_path: Path) -> None:
    dash, sim, _holdout, explore = _setup_seal_env(tmp_path)
    trace_root = tmp_path / "traces"

    _write_json(
        trace_root / "quad_set" / "batch_summary.part_01.json",
        {
            "mode": "4quadrant",
            "backend": "hosted",
            "graph_model": "toy-model",
            "results": [
                {
                    "index": 1,
                    "mode": "4quadrant",
                    "prompts": {
                        "A": explore,
                        "B": "beta casual prompt two",
                        "C": "alpha formal prompt one",
                        "D": "alpha casual prompt one",
                    },
                    "target_token": 'Output " omega"',
                    "probabilities": {"A": 0.4, "B": 0.35, "C": 0.2, "D": 0.15},
                }
            ],
        },
    )
    _write_json(
        trace_root / "dialect_set" / "batch_summary.part_01.json",
        {
            "mode": "dialect",
            "backend": "hosted",
            "graph_model": "toy-model",
            "results": [
                {
                    "index": 1,
                    "mode": "dialect",
                    "baseline_prompt": explore,
                    "target_token": 'Output " omega"',
                    "baseline_probability": 0.44,
                    "variants": [{"dialect": "var_a", "prompt": "beta casual prompt two", "probability": 0.31, "delta_vs_baseline": -0.13}],
                }
            ],
        },
    )

    doc = mij.build_multi_instrument_records(trace_root=trace_root, dashboard_path=dash, simulated_dir=sim)
    assert doc["counts"]["case_count"] == 2
    d_case = _case_at(doc, "dialect_set", 1, "toy-model")
    assert d_case["instruments"]["hosted_graph"]["candidates"][0]["values"]["probabilities"] == {"baseline": 0.44}

    # Unknown backend/mode combination refuses loudly rather than skipping silently.
    _write_json(
        trace_root / "bad_set" / "batch_summary.part_01.json",
        {"mode": "2panel", "backend": "unrecognized_backend", "graph_model": "toy-model", "results": []},
    )
    with pytest.raises(Refusal) as exc_bad:
        mij.build_multi_instrument_records(trace_root=trace_root, dashboard_path=dash, simulated_dir=sim)
    assert exc_bad.value.code == "unknown_instrument"
