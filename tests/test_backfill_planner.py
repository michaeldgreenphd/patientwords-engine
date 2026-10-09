"""backfill_planner: depth-aware coverage + next-fire priority (offline, fixture-based)."""

import importlib.util
import json
import re
import shlex
from pathlib import Path

import yaml


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_planner.py"
    spec = importlib.util.spec_from_file_location("backfill_planner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bp = _load()


def _summary(indices):
    return {"results": [{"index": i} for i in indices]}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "ENGINE", tmp_path)
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_A.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}] * 3))
    (sim / "pairs_B.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}] * 4))
    tr = tmp_path / "trace_out"
    # A: gemma trace complete (3/3); B: trace absent
    (tr / "pairs_A").mkdir(parents=True)
    (tr / "pairs_A" / "batch_summary.part_01.json").write_text(json.dumps(_summary([1, 2, 3])))
    # A: lens partial (2/3 pairs of save_raw), B: none
    lens = tr / "pairs_A__jlens_gemma-2-2b"
    (lens / "jlens_raw").mkdir(parents=True)
    (lens / "jlens_summary.part_01.json").write_text(json.dumps(_summary([1, 2])))
    for p in (1, 2):
        for side in ("clinical", "patient"):
            (lens / "jlens_raw" / f"pair_{p:03d}_{side}.json.gz").write_bytes(b"x")
    return tr, sim


def test_depth_coverage_and_resume(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cov = bp.coverage()
    assert cov["pairs_A"]["n"] == 3 and cov["pairs_B"]["n"] == 4
    assert cov["pairs_A"]["trace"] == 3          # complete
    assert cov["pairs_B"]["trace"] == 0          # absent
    assert cov["pairs_A"]["lens"] == 2           # 2/3 save_raw pairs -> partial
    # trace lane resumes the incomplete batch (B, from offset 0)
    tr = bp._next_trace(cov)
    assert tr["params"]["pairs_file"].endswith("pairs_B.json")
    assert tr["params"]["offsets"] == "0"
    # lens lane resumes A at offset 2 (pairs 3/3), since A is the oldest incomplete
    ln = bp._next_lens(cov)
    assert ln["params"]["pairs_file"].endswith("pairs_A.json")
    assert ln["params"]["offset"] == "2" and ln["params"]["limit"] == "1"
    assert ln["params"]["save_raw"] == "true" and ln["params"]["lens_type"] == "JACOBIAN_LENS"


def test_logits_priority_medical_first(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cov = bp.coverage()
    step = bp._next_logits(cov)
    # no model has any logits here, so a MEDICAL model must be chosen first
    assert step["params"]["models"] in bp.MEDICAL
    # 8B medical models use the small chunk
    if step["params"]["models"] in bp.BIG:
        assert int(step["params"]["limit"]) <= bp.LOGITS_CHUNK_BIG


def test_8b_medical_deferred_until_others_complete(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)  # sparse: trace/lens/predictions all incomplete
    cov = bp.coverage()
    # every axis is short, so the 8B medical models are HELD: the logits lane must
    # offer a NON-deferred model, never meditron3-8b / apertus-8b-meditronfo.
    assert bp._others_complete(cov) is False
    step = bp.plan(cov)["logits-eval"]
    assert step["params"]["models"] not in bp.DEFERRED_LAST
    # the override releases them (default priority = medical-first, incl. the 8B pair)
    forced = bp._next_logits(cov, allow_deferred=True)
    assert forced["params"]["models"] in bp.MEDICAL


def test_8b_medical_released_once_others_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "ENGINE", tmp_path)
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_A.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}]))
    tr = tmp_path / "trace_out"
    # trace + lens + EVERY non-deferred model complete; only the 8B medical pair is absent
    (tr / "pairs_A").mkdir(parents=True)
    (tr / "pairs_A" / "batch_summary.json").write_text(json.dumps(_summary([1])))
    lens = tr / "pairs_A__jlens_gemma-2-2b"
    (lens / "jlens_raw").mkdir(parents=True)
    (lens / "jlens_summary.json").write_text(json.dumps(_summary([1])))
    for side in ("clinical", "patient"):
        (lens / "jlens_raw" / f"pair_001_{side}.json.gz").write_bytes(b"x")
    for m in bp.MODELS:
        if m in bp.DEFERRED_LAST:
            continue
        (tr / f"pairs_A__{m}").mkdir(parents=True)
        (tr / f"pairs_A__{m}" / "batch_summary.json").write_text(json.dumps(_summary([1])))
    cov = bp.coverage()
    assert bp._others_complete(cov) is True
    step = bp.plan(cov)["logits-eval"]                 # now released
    assert step is not None and step["params"]["models"] in bp.DEFERRED_LAST


def test_complete_batch_yields_no_fire(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "ENGINE", tmp_path)
    sim = tmp_path / "data" / "simulated"
    sim.mkdir(parents=True)
    (sim / "pairs_A.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}]))
    tr = tmp_path / "trace_out"
    # fully cover the single-pair batch on every axis
    (tr / "pairs_A").mkdir(parents=True)
    (tr / "pairs_A" / "batch_summary.json").write_text(json.dumps(_summary([1])))
    lens = tr / "pairs_A__jlens_gemma-2-2b"
    (lens / "jlens_raw").mkdir(parents=True)
    (lens / "jlens_summary.json").write_text(json.dumps(_summary([1])))
    for side in ("clinical", "patient"):
        (lens / "jlens_raw" / f"pair_001_{side}.json.gz").write_bytes(b"x")
    for m in bp.MODELS:
        (tr / f"pairs_A__{m}").mkdir(parents=True)
        (tr / f"pairs_A__{m}" / "batch_summary.json").write_text(json.dumps(_summary([1])))
    cov = bp.coverage()
    steps = bp.plan(cov)
    assert steps["circuit-trace"] is None
    assert steps["jlens-readout"] is None
    assert steps["logits-eval"] is None


# --- the 2026-10-09 exploratory models (gemma-4-e2b, qwen3.5-2b-base, medgemma-1.5-4b-it) ---

_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ft = _load_script("fire_trigger")
logits_eval = _load_script("logits_eval")   # imports torch lazily, so loading it needs neither torch nor network

# Seconds per pair between consecutive pairs in the limit-3 probe, logits-eval run 37960095244 (2026-10-09).
PROBE_SECONDS_PER_PAIR = {"gemma-4-e2b": 5, "qwen3.5-2b-base": 60, "medgemma-1.5-4b-it": 120}


def _write_summary(tr, rel, indices, part="part_01"):
    (tr / rel).mkdir(parents=True, exist_ok=True)
    (tr / rel / f"batch_summary.{part}.json").write_text(json.dumps(_summary(list(indices))))


def _complete_originals(root, monkeypatch, sizes, skip=()):
    """Batches of the given sizes with trace, lens and every ORIGINAL model complete, except the batches in
    skip, which nothing has measured. The exploratory models have nothing."""
    monkeypatch.setattr(bp, "ENGINE", root)
    sim = root / "data" / "simulated"
    sim.mkdir(parents=True)
    tr = root / "trace_out"
    for name, n in sizes.items():
        (sim / f"{name}.json").write_text(json.dumps([{"top_prompt": "x", "bottom_prompt": "y"}] * n))
        if name in skip:
            continue
        idx = range(1, n + 1)
        _write_summary(tr, name, idx)
        lens = tr / f"{name}__jlens_gemma-2-2b"
        (lens / "jlens_raw").mkdir(parents=True)
        (lens / "jlens_summary.json").write_text(json.dumps(_summary(list(idx))))
        for p in idx:
            for side in ("clinical", "patient"):
                (lens / "jlens_raw" / f"pair_{p:03d}_{side}.json.gz").write_bytes(b"x")
        for m in bp.MODELS:
            if m not in bp.EXPLORATORY:
                _write_summary(tr, f"{name}__{m}", idx)
    return tr


def test_exploratory_models_are_registered_pinned_and_chunked_inside_the_timeout():
    assert set(bp.EXPLORATORY) == set(PROBE_SECONDS_PER_PAIR) == set(bp.SWEEP_MODELS) | {bp.MEDGEMMA15}
    assert set(bp.EXPLORATORY) <= set(bp.MODELS)
    assert not set(bp.EXPLORATORY) & (bp.DEFERRED_LAST | bp.MEDICAL)
    wf = yaml.safe_load((_ROOT / ".github" / "workflows" / "logits_evaluation.yml").read_text(encoding="utf-8"))
    timeout_min = wf["jobs"]["eval"]["timeout-minutes"]
    for m, secs in PROBE_SECONDS_PER_PAIR.items():
        # the workflow can load it, at a pinned commit (every loader refuses an unpinned short id)
        assert m in logits_eval.HF_IDS and re.fullmatch(r"[0-9a-f]{40}", logits_eval.HF_REVISIONS[m]), m
        chunk = bp._logits_chunk(m)
        assert chunk >= 1
        # well inside the job timeout: a full chunk's measured compute stays at or under half of it, which leaves
        # room for the weight load and for a rate measured on only three pairs
        assert chunk * secs <= timeout_min * 60 / 2, (m, chunk, secs, timeout_min)
    # the sweep fires a whole batch (the largest is 119 pairs) for both models; medgemma-1.5 uses the small chunk
    assert all(bp._logits_chunk(m) >= 119 for m in bp.SWEEP_MODELS)
    assert bp.MEDGEMMA15 in bp.BIG and bp._logits_chunk(bp.MEDGEMMA15) == bp.LOGITS_CHUNK_BIG


def test_exploratory_models_never_enter_the_default_plan(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)                       # sparse: every original model has gaps
    cov = bp.coverage()
    for defer in (True, False):
        assert bp.plan(cov, defer_8b_medical=defer)["logits-eval"]["params"]["models"] not in bp.EXPLORATORY
    # once every original model is complete the 8B gate opens although the exploratory models have nothing,
    # and the default plan still has nothing to fire: the exploratory models are planned only by --exploratory
    root = tmp_path / "complete"
    root.mkdir()
    _complete_originals(root, monkeypatch, {"pairs_A": 2})
    cov = bp.coverage()
    assert bp._others_complete(cov) is True
    assert bp.plan(cov)["logits-eval"] is None
    assert bp.plan(cov, exploratory_only=True)["logits-eval"]["params"]["models"] == "gemma-4-e2b,qwen3.5-2b-base"


def test_the_sweep_fires_both_models_a_whole_batch_at_a_time_to_parity(tmp_path, monkeypatch):
    # pairs_A: 130 pairs, every original model complete; pairs_B: 3 pairs nothing has measured (as with the
    # unbooked pairs_20260721T132205Z and the one-pair parks), so parity never sends an exploratory model there
    tr = _complete_originals(tmp_path, monkeypatch, {"pairs_A": 130, "pairs_B": 3}, skip=("pairs_B",))
    cov = bp.coverage()
    assert bp._parity_target(cov["pairs_A"]) == 130 and bp._parity_target(cov["pairs_B"]) == 0
    steps = bp.plan(cov, exploratory_only=True)
    assert set(steps) == {"logits-eval"}               # this mode plans no other lane
    assert steps["logits-eval"]["params"] == {"models": "gemma-4-e2b,qwen3.5-2b-base",
                                              "pairs_file": "data/simulated/pairs_A.json",
                                              "limit": "120", "offset": "0", "commit_outputs": "true"}
    assert "exploratory" in steps["logits-eval"]["note"]
    # --next 2 plans the second leg as if the first had landed: the rest of the batch, both models
    legs = bp.exploratory_legs(cov, count=5)
    assert [(x["params"]["offset"], x["params"]["limit"]) for x in legs] == [("0", "120"), ("120", "10")]
    # one model's leg failed: the lagging model is fired alone for its own gap, never re-measuring the other
    _write_summary(tr, "pairs_A__gemma-4-e2b", range(1, 121))
    _write_summary(tr, "pairs_A__qwen3.5-2b-base", range(1, 121))
    _write_summary(tr, "pairs_A__gemma-4-e2b", range(121, 131), part="part_121")
    step = bp.plan(bp.coverage(), exploratory_only=True)["logits-eval"]
    assert (step["params"]["models"], step["params"]["offset"], step["params"]["limit"]) == \
        ("qwen3.5-2b-base", "120", "10")
    # both at parity: nothing to fire, although pairs_B is unmeasured; medgemma-1.5 is not in the sweep
    _write_summary(tr, "pairs_A__qwen3.5-2b-base", range(121, 131), part="part_121")
    cov = bp.coverage()
    assert bp.plan(cov, exploratory_only=True)["logits-eval"] is None
    par = bp.exploratory_parity(cov)
    assert all(par[m]["pairs"] == par[m]["target_pairs"] == 130 for m in bp.SWEEP_MODELS)
    assert par[bp.MEDGEMMA15]["pairs"] == 0
    # --include-medgemma15 then plans the rest for medgemma-1.5 alone, in its small chunks
    step = bp.plan(cov, exploratory_only=True, include_medgemma15=True)["logits-eval"]
    assert step["params"] == {"models": bp.MEDGEMMA15, "pairs_file": "data/simulated/pairs_A.json",
                              "limit": str(bp.LOGITS_CHUNK_BIG), "offset": "0", "commit_outputs": "true"}


def test_medgemma15_selection_first_then_the_rest_without_overlap_or_part_collision(tmp_path, monkeypatch):
    """The priority selection is measured as `indices` fires inside the original batch; the rest later fills only
    the gaps, and every part is named for its first index, so no part name repeats and no pair is measured twice."""
    tr = _complete_originals(tmp_path, monkeypatch, {"pairs_A": 60})
    sel_file = tmp_path / "sel.json"
    sel_file.write_text(json.dumps({"pairs": [{"batch": "pairs_A", "index": i} for i in (5, 6, 7, 30, 58)]}))
    selection = bp.load_selection(sel_file)
    legs = bp.exploratory_plan(bp.coverage(), count=10, medgemma15_selection=selection)
    assert len(legs) == 1 and legs[0]["params"]["indices"] == "5,6,7,30,58"
    assert "limit" not in legs[0]["params"] and "offset" not in legs[0]["params"]
    assert ft.validate_params("logits-eval", legs[0]["params"]) is None
    parts = {"part_05"}                                  # the part logits_eval.py and the workflow name for it
    _write_summary(tr, f"pairs_A__{bp.MEDGEMMA15}", [5, 6, 7, 30, 58], part="part_05")
    assert bp.exploratory_plan(bp.coverage(), count=10, medgemma15_selection=selection) == []
    # the rest: every remaining index exactly once, in chunks of LOGITS_CHUNK_BIG, sweep at parity first
    for m in bp.SWEEP_MODELS:
        _write_summary(tr, f"pairs_A__{m}", range(1, 61))
    rest = bp.exploratory_plan(bp.coverage(), count=10, include_medgemma15=True)
    covered = []
    for leg in rest:
        p = leg["params"]
        assert p["models"] == bp.MEDGEMMA15 and ft.validate_params("logits-eval", p) is None
        idx = [int(i) for i in p["indices"].split(",")] if "indices" in p else \
            list(range(int(p["offset"]) + 1, int(p["offset"]) + int(p["limit"]) + 1))
        assert len(idx) <= bp.LOGITS_CHUNK_BIG
        part = f"part_{idx[0]:02d}"
        assert part not in parts, part
        parts.add(part)
        covered += idx
    assert sorted(covered) == sorted(set(range(1, 61)) - {5, 6, 7, 30, 58})


def test_emitted_exploratory_command_passes_fire_trigger_and_the_park_queues_behind_it(tmp_path, monkeypatch,
                                                                                        capsys):
    """The command the planner prints is what the Routine's section 3e runs: as printed, it must pass
    fire_trigger.py's key and lane validation, and the park the section queues right behind it must pass the
    queue guard, leaving the park as the trigger file's content at rest."""
    _complete_originals(tmp_path / "engine", monkeypatch, {"pairs_A": 30})
    step = bp.plan(bp.coverage(), exploratory_only=True)["logits-eval"]
    assert ft.validate_params("logits-eval", step["params"]) is None
    argv = shlex.split(bp._fmt_cmd(step))
    assert argv[:3] == ["python", "scripts/fire_trigger.py", "fire"]
    repo = tmp_path / "repo"
    (repo / ".github" / "trigger").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    lane_file = Path(".github") / "trigger" / "logits-eval.json"
    (repo / ".github" / "workflows" / "stub.yml").write_text(
        f'on:\n  push:\n    paths:\n      - "{lane_file.as_posix()}"\n', encoding="utf-8")
    (repo / "ops").mkdir()
    assert ft.main(argv[2:] + ["--repo", str(repo), "--no-git", "--dry-run"]) == 0
    assert "[dry-run]" in capsys.readouterr().out
    # fired (without git): the leg is the running entry, and the park is accepted as the pending one
    assert ft.main(argv[2:] + ["--repo", str(repo), "--no-git", "--keep-dashboard"]) == 0
    assert ft.main(["park", "--repo", str(repo), "--trigger", "logits-eval", "--no-git", "--keep-dashboard"]) == 0
    entries = ft.load_journal(repo / "ops" / "trigger_journal.jsonl")
    assert [e["note"] for e in entries] == [step["note"], ft.PARK_NOTE]
    assert ft.is_park_params("logits-eval", json.loads((repo / lane_file).read_text(encoding="utf-8")))


def test_the_routine_step_runs_this_mode_and_stops_on_the_string_it_prints(tmp_path, monkeypatch, capsys):
    """docs/routine_standing_prompt.md section 3e runs `--exploratory` and stops on `AT PARITY`; both must stay
    what the planner accepts and prints, or the step fires forever or never."""
    prompt = (_ROOT / "docs" / "routine_standing_prompt.md").read_text(encoding="utf-8")
    step_text = " ".join(prompt[prompt.index("\n3e. "):prompt.index("\n## 4 ")].split())
    for token in ("python scripts/backfill_planner.py --exploratory", "AT PARITY", "0 active journal entries",
                  "python scripts/fire_trigger.py park --trigger logits-eval --keep-dashboard"):
        assert token in step_text, token
    assert "--include-medgemma15" not in step_text and "--medgemma15-selection" not in step_text
    assert "§3e" in prompt[prompt.index("\n## 4 "):]
    tr = _complete_originals(tmp_path, monkeypatch, {"pairs_A": 4})
    assert bp.main(["--exploratory"]) == 0
    out = capsys.readouterr().out
    assert "AT PARITY" not in out and "--trigger logits-eval" in out and "--trigger circuit-trace" not in out
    for m in bp.SWEEP_MODELS:
        _write_summary(tr, f"pairs_A__{m}", range(1, 5))
    assert bp.main(["--exploratory"]) == 0
    assert "AT PARITY" in capsys.readouterr().out
