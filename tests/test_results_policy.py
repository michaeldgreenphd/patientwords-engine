"""The open-results policy (scripts/results_policy.py, data/results_policy/policy.v1.json; owner direction of
2026-11-10): sharing a result, admitting it to an analysis, trusting its bytes and restricting it are four
separate decisions.

tests/test_publication_hold.py keeps the guarantee the 2026-10-09 hold was introduced for (the default
membership's statistics do not move when new parts land). These tests cover what the hold could not express:

* a valid, unsealed post-registration result is visible and is not in the study membership;
* a part missing from the pinned manifest is not defective;
* a hand-authored example is visible, labelled as pending review, and in no study membership;
* a null result and an incomplete run are both listed, with different execution states;
* a part whose bytes changed after its hash was recorded is refused everywhere, and the recorded hash is never
  rewritten;
* a sealed row and a redistribution-limited stimulus family stay restricted;
* every restriction in the policy file names its reason, a responsible role and a release condition.

All phrases are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

from scripts import results_policy as rp  # noqa: E402
from scripts import tierb_split  # noqa: E402

BATCH = "pairs_20200101T000000Z"
POLICY_FILE = ROOT / "data" / "results_policy" / "policy.v1.json"
_SPREAD = {"clinical": [["alpha", 0.6], ["beta", 0.2]], "patient": [["beta", 0.5], ["alpha", 0.3]]}
_TIERS = {"status": "synthetic tiers - test only", "tiers": {"1": "tier one", "2": "tier two"},
          "tokens": {"alpha": {"tier": 2}, "beta": {"tier": 1}}}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_results_policy", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _summary(indexes, graph_model, backend="logits", penalty=-0.3, **extra):
    return {"graph_model": graph_model, "backend": backend, "source_set": None, "completed": True,
            "pairs_requested": len(indexes),
            "results": [{"index": i, "prompts": {"clinical": f"alpha prompt {i}", "patient": f"beta prompt {i}"},
                         "probabilities": {"clinical": 0.6, "patient": 0.6 + penalty},
                         "predictive_spread": _SPREAD, "language_penalty": penalty} for i in indexes], **extra}


def _part(root: Path, run_dir: str, summary, name="batch_summary.part_01.json") -> Path:
    path = root / "trace_out" / run_dir / name
    _write(path, summary)
    return path


def _manifest(root: Path, parts) -> None:
    listed = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in parts}
    _write(root / rp.RELEASE_MANIFEST, {"schema": rp.MANIFEST_SCHEMA, "parts": listed})


def _decide(root: Path, part: Path) -> rp.PartDecision:
    return rp.classify_part(root, part, json.loads(part.read_text(encoding="utf-8")),
                            manifest=rp.load_manifest(root), ledger=rp.load_ledger(root))


@pytest.fixture
def root(tmp_path):
    """A hosted base part and a pinned qwen3-4b logits part: the state the study membership describes."""
    engine = tmp_path / "engine"
    base = _part(engine, BATCH, _summary([1, 2, 3], "gemma-2-2b", "hosted"))
    pinned = _part(engine, f"{BATCH}__qwen3-4b", _summary([1, 2, 3], "qwen3-4b"))
    _manifest(engine, [pinned])
    assert base.exists()
    return engine


# ---------------------------------------------------------------- the policy file itself

def test_the_committed_policy_is_valid_and_agrees_with_the_code_that_names_the_same_cohorts():
    policy = rp.load_policy(POLICY_FILE)
    assert policy.version == "open-results/1" and policy.default_membership == rp.STUDY_INTERIM
    planner, rigor = _load("backfill_planner"), _load("paired_stats_rigor")
    assert policy.cohort_models("post_registration_20261009") == set(planner.EXPLORATORY)
    assert policy.cohort_models("registered_20260709") == set(rigor._PREREG_MODELS)
    assert policy.excluded_models(rp.STUDY_INTERIM) == set(planner.EXPLORATORY)
    assert policy.excluded_models(rp.EXPLORATORY_OPEN) == policy.excluded_models(rp.PUBLIC_DISPLAY) == frozenset()


def test_stimulus_classes_agree_with_the_metadata_the_batches_themselves_carry():
    """Classification is declared metadata, checked against the sidecars: every hand-authored set says so in
    its own ``status``, and no other sidecar does."""
    policy = rp.load_policy(POLICY_FILE)
    prefix = policy.doc["stimulus_classes"]["hand_authored_exploratory"]["sidecar_status_prefix"]
    seen = 0
    for sidecar in sorted((ROOT / "data" / "simulated").glob("*.report.json")):
        status = json.loads(sidecar.read_text(encoding="utf-8")).get("status")
        stem = sidecar.name[:-len(".report.json")]
        declared = policy.stimulus_class(stem) == "hand_authored_exploratory"
        assert declared == (isinstance(status, str) and status.startswith(prefix)), sidecar.name
        seen += declared
    assert seen >= 7
    insights = _load("jlens_insights")
    for text_restricted in insights.TEXT_RESTRICTED_PREFIXES:
        entry = policy.stimulus_entry(policy.stimulus_class(text_restricted + "20200101T000000Z"))
        assert entry.get("restriction") == "redistribution_limited_text" and entry["rows_exported"] is False


def test_a_restriction_without_a_reason_role_or_release_condition_is_refused(tmp_path):
    for missing in ("decided_by", "responsible_role", "release_condition"):
        doc = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
        del doc["restrictions"]["sealed_holdout"][missing]
        _write(tmp_path / f"{missing}.json", doc)
        with pytest.raises(rp.PolicyError, match="this policy has none"):
            rp.load_policy(tmp_path / f"{missing}.json")


def test_a_model_in_two_cohorts_or_an_unknown_membership_is_refused(tmp_path):
    doc = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    doc["model_cohorts"]["post_registration_2026_07"]["models"].append("gemma-2-2b")
    _write(tmp_path / "twice.json", doc)
    with pytest.raises(rp.PolicyError, match="is in cohorts"):
        rp.load_policy(tmp_path / "twice.json")
    with pytest.raises(rp.PolicyError, match="unknown membership"):
        rp.Gate(tmp_path, membership="no-such-membership/9")


# ---------------------------------------------------------------- visible is not the same as pooled

def test_a_valid_post_registration_result_is_public_and_outside_the_study_membership(root):
    part = _part(root, f"{BATCH}__gemma-4-e2b", _summary([1, 2, 3], "gemma-4-e2b"))
    d = _decide(root, part)
    assert d.visibility == "public" and d.restriction_reasons == [] and d.rows_exported is True
    assert d.evidence_class == "exploratory_post_registration" and d.model_cohort == "post_registration_20261009"
    assert d.execution_state == "completed" and d.artifact_integrity == "unrecorded"
    assert d.analysis[rp.PUBLIC_DISPLAY] == {"eligible": True, "reason": None}
    assert d.analysis[rp.EXPLORATORY_OPEN]["eligible"] is True
    assert d.analysis[rp.STUDY_INTERIM]["eligible"] is False
    assert "cohort post_registration_20261009" in d.analysis[rp.STUDY_INTERIM]["reason"]
    summary = json.loads(part.read_text(encoding="utf-8"))
    assert rp.Gate(root, membership=rp.PUBLIC_DISPLAY).admit(part, summary) is True
    assert rp.Gate(root).admit(part, summary) is False


def test_a_part_missing_from_the_pinned_manifest_is_not_a_defect(root):
    part = _part(root, f"{BATCH}__qwen3-4b", _summary([4], "qwen3-4b"), "batch_summary.part_04.json")
    d = _decide(root, part)
    assert d.artifact_integrity == "unrecorded" and d.visibility == "public"
    assert d.evidence_class == "registered_cohort"
    assert d.analysis[rp.STUDY_INTERIM] == {"eligible": False, "reason": "logits part outside the pinned manifest"}
    assert d.analysis[rp.EXPLORATORY_OPEN]["eligible"] and d.analysis[rp.PUBLIC_DISPLAY]["eligible"]


def test_a_hand_authored_example_is_visible_labelled_and_in_no_study_membership(root):
    hosted = _part(root, "agscen_20990101", _summary([1, 2], "gemma-2-2b", "hosted"))
    logits = _part(root, "agscen_20990101__qwen3-4b", _summary([1, 2], "qwen3-4b"))
    for part in (hosted, logits):
        d = _decide(root, part)
        assert d.visibility == "public" and d.rows_exported is True
        assert d.evidence_class == "exploratory_hand_authored"
        assert d.clinical_review == "owner_read_equivalence_and_domain_review_pending"
        assert d.analysis[rp.PUBLIC_DISPLAY]["eligible"] is True
        for membership in (rp.STUDY_INTERIM, rp.EXPLORATORY_OPEN):
            assert d.analysis[membership]["eligible"] is False
            assert "hand_authored_exploratory" in d.analysis[membership]["reason"]


def test_a_null_result_is_a_completed_result_and_an_incomplete_run_is_listed_as_incomplete(root):
    null = _part(root, f"{BATCH}__olmo-2-1b", _summary([1, 2], "olmo-2-1b", penalty=0.0))
    partial = _part(root, f"{BATCH}__llama-3.2-3b", _summary([1], "llama-3.2-3b", completed=False,
                                                              _partial="in-progress flush"))
    empty = _part(root, f"{BATCH}__gemma-2-2b-it", _summary([], "gemma-2-2b-it"))
    unstated = _summary([1], "gemma-3-4b-it")
    del unstated["completed"]
    unstated_part = _part(root, f"{BATCH}__gemma-3-4b-it", unstated)
    states = {p.parent.name.split("__")[1]: _decide(root, p) for p in (null, partial, empty, unstated_part)}
    assert states["olmo-2-1b"].execution_state == "completed"
    assert states["llama-3.2-3b"].execution_state == "partial"
    assert states["gemma-2-2b-it"].execution_state == "empty" and states["gemma-2-2b-it"].n_results == 0
    assert states["gemma-3-4b-it"].execution_state == "completion_not_recorded"
    # none of the four is hidden: the state describes the run, and each stays public and displayable
    assert all(d.visibility == "public" and d.analysis[rp.PUBLIC_DISPLAY]["eligible"] for d in states.values())


# ---------------------------------------------------------------- a modified artifact cannot pass for the recorded one

def test_a_part_changed_after_its_hash_was_recorded_is_refused_everywhere_and_the_record_is_kept(root):
    part = _part(root, f"{BATCH}__gemma-4-e2b", _summary([1, 2, 3], "gemma-4-e2b"))
    rel = part.relative_to(root).as_posix()
    first = rp.sha256_file(part)
    out = rp.record_parts(root, {rel: first}, recorded_utc="2026-11-10T00:00:00Z", recorded_at_commit="a" * 40)
    assert out == {"added": [rel], "conflicts": []}
    assert _decide(root, part).artifact_integrity == "recorded_match"

    _write(part, _summary([1, 2, 3], "gemma-4-e2b", penalty=-0.9))           # rewritten in place
    d = _decide(root, part)
    assert d.artifact_integrity == "changed_since_recorded" and d.visibility == "restricted"
    assert d.restriction_reasons == ["artifact_integrity:changed_since_recorded"] and d.rows_exported is False
    assert not any(d.analysis[m]["eligible"] for m in (rp.PUBLIC_DISPLAY, rp.EXPLORATORY_OPEN, rp.STUDY_INTERIM))
    summary = json.loads(part.read_text(encoding="utf-8"))
    for membership in (rp.PUBLIC_DISPLAY, rp.EXPLORATORY_OPEN):
        gate = rp.Gate(root, membership=membership)
        assert gate.admit(part, summary) is False
        assert "artifact integrity: changed_since_recorded 1" in gate.report()

    again = rp.record_parts(root, {rel: rp.sha256_file(part)}, recorded_utc="2026-11-11T00:00:00Z",
                            recorded_at_commit="b" * 40)
    assert again == {"added": [], "conflicts": [rel]}
    assert rp.load_ledger(root)[rel] == first                                # the first record stands


def test_a_pinned_logits_part_whose_bytes_changed_leaves_every_membership(root):
    part = root / "trace_out" / f"{BATCH}__qwen3-4b" / "batch_summary.part_01.json"
    assert _decide(root, part).analysis[rp.STUDY_INTERIM]["eligible"] is True
    _write(part, _summary([1, 2, 3, 3], "qwen3-4b"))
    d = _decide(root, part)
    assert d.artifact_integrity == "changed_since_recorded"
    assert d.analysis[rp.STUDY_INTERIM]["reason"] == "logits part changed since it was recorded"
    assert d.analysis[rp.PUBLIC_DISPLAY]["eligible"] is False


def test_a_malformed_part_is_listed_as_malformed_and_a_gate_refuses_to_guess(root):
    part = _part(root, f"{BATCH}__olmo-2-1b", {"graph_model": "olmo-2-1b", "results": []})
    d = _decide(root, part)
    assert d.artifact_integrity == "malformed" and d.visibility == "restricted"
    assert not d.analysis[rp.PUBLIC_DISPLAY]["eligible"]
    for membership in (rp.STUDY_INTERIM, rp.EXPLORATORY_OPEN, rp.PUBLIC_DISPLAY):
        with pytest.raises(rp.ReleaseError, match="missing required 'backend' key"):
            rp.Gate(root, membership=membership).admit(part, json.loads(part.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- restrictions that remain

def test_a_redistribution_limited_family_is_listed_without_rows(root):
    part = _part(root, "pabharvest_20200101T000000Z", _summary([1], "gemma-2-2b", "hosted"))
    d = _decide(root, part)
    assert d.visibility == "restricted" and d.restriction_reasons == ["redistribution_limited_text"]
    assert d.rows_exported is False and "licence review" in d.rows_reason
    assert d.analysis[rp.PUBLIC_DISPLAY] == {"eligible": False, "reason": "restricted"}
    gate = rp.Gate(root, membership=rp.PUBLIC_DISPLAY)
    assert gate.admit(part, json.loads(part.read_text(encoding="utf-8"))) is False
    assert "restricted: redistribution_limited_text 1" in gate.report()


def test_an_unclassified_family_is_listed_with_counts_only_and_says_how_to_change_that(root):
    part = _part(root, "dialects_20200101T000000Z", _summary([1], "gemma-2-2b", "hosted"))
    d = _decide(root, part)
    assert d.stimulus_class == "unclassified" and d.visibility == "public"
    assert d.rows_exported is False and "Release condition" in d.rows_reason


def test_the_row_restriction_is_the_tier_b_seal_and_fails_closed(tmp_path):
    sealed = next(f"alpha prompt {i}" for i in range(1, 500) if tierb_split.is_holdout(f"alpha prompt {i}"))
    open_ = next(f"alpha prompt {i}" for i in range(1, 500) if not tierb_split.is_holdout(f"alpha prompt {i}"))
    simulated = tmp_path / "data" / "simulated"
    _write(simulated / f"{BATCH}.json", [{"top_prompt": sealed}, {"top_prompt": open_}])
    dashboard = tmp_path / "dashboard.json"
    _write(dashboard, {"tierb": {"start_utc": "2019-12-31T00:00:00Z"}})
    paths = {"dashboard_path": dashboard, "simulated_dir": simulated}
    assert rp.row_restriction(BATCH, 1, sealed, **paths) == "sealed_holdout"
    assert rp.row_restriction(BATCH, 2, open_, **paths) is None
    # Amendment 3: the phrase is sealed on every stem, a hand-authored set included
    assert rp.row_restriction("agscen_20990101", 1, sealed, **paths) == "sealed_holdout"
    unstamped = tmp_path / "dashboard_without_a_start.json"        # a new path: the seal caches a readable context
    _write(unstamped, {"tierb": {"start_utc": None}})
    with pytest.raises(rp.SealError):
        rp.row_restriction(BATCH, 1, sealed, dashboard_path=unstamped, simulated_dir=simulated)


# ---------------------------------------------------------------- the collector

def _urgency(root: Path, tag: str, payload_models: dict, env: dict | None = None) -> tuple[int, dict, str]:
    _write(root / "tiers.json", _TIERS)
    _write(root / "ops" / "dashboard.json", {"tierb": {"start_utc": "2026-07-10T01:14:38Z"}})
    _write(root / "data" / "simulated" / f"{BATCH}.json",
           [{"top_prompt": f"alpha prompt {i}", "generation": {"topic": "topic-a"}} for i in (1, 2, 3, 4)])
    site = root.parent / f"site_{tag}"
    _write(site / "data" / "simulated_scenarios.json",
           {"batches": [{"batch": BATCH}], "scenarios": [
               {"batch": BATCH, "batch_index": i, "clinical_prompt": f"alpha prompt {i}",
                "models": copy.deepcopy(payload_models)} for i in (1, 2, 3, 4)]})
    rows = root.parent / f"rows_{tag}.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "urgency_shift.py"), "--tiers", "tiers.json",
                           "--out", str(rows), "--frontend", str(site)], cwd=root, capture_output=True,
                          text=True, timeout=120, env={**os.environ, **(env or {})})
    doc = json.loads(rows.read_text(encoding="utf-8")) if rows.exists() else {}
    return proc.returncode, doc, proc.stdout + proc.stderr


_PAYLOAD_MODEL = {"spread_clinical": [["alpha", 0.6], ["beta", 0.2]], "spread_patient": [["beta", 0.5], ["alpha", 0.3]],
                  "language_penalty": -0.3}


def test_a_payload_model_outside_the_membership_never_reaches_the_rows(root, tmp_path):
    """Regression (2026-11-10): urgency_shift.py filled rows from the site payload without asking the gate, so
    a payload that displayed a model outside the membership would have pooled it into every aggregate."""
    rc, doc, out = _urgency(root, "default", {"gemma-4-e2b": _PAYLOAD_MODEL, "olmo-2-1b": _PAYLOAD_MODEL})
    assert rc == 0, out
    models = {r["model"] for r in doc["rows"]}
    assert "gemma-4-e2b" not in models and "gemma-4-e2b" not in doc["summary"]["per_model"]
    assert "olmo-2-1b" in models                                            # an ordinary payload-only model still fills
    assert "site payload row of model gemma-4-e2b (outside this membership) 4" in out
    assert "analysis membership study-interim/1 (policy open-results/1)" in out

    candidate = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    candidate["default_membership"] = rp.EXPLORATORY_OPEN
    _write(tmp_path / "candidate.json", candidate)
    rc, doc, out = _urgency(root, "open", {"gemma-4-e2b": _PAYLOAD_MODEL},
                            env={rp.POLICY_ENV: str(tmp_path / "candidate.json")})
    assert rc == 0, out
    assert "gemma-4-e2b" in {r["model"] for r in doc["rows"]}                 # the fixture does reach the fill loop
    assert "analysis membership exploratory-open/1" in out and "policy file overridden" in out


def test_the_separately_declared_analysis_reads_new_parts_and_the_study_analysis_does_not(root, tmp_path):
    _part(root, f"{BATCH}__gemma-4-e2b", _summary([1, 2, 3], "gemma-4-e2b"))
    _part(root, f"{BATCH}__qwen3-4b", _summary([4], "qwen3-4b"), "batch_summary.part_04.json")
    _part(root, "agscen_20990101__qwen3-4b", _summary([1, 2], "qwen3-4b"))
    rc, study, out = _urgency(root, "study", {})
    assert rc == 0, out
    assert {(r["model"], r["index"]) for r in study["rows"]} == {
        ("gemma-2-2b", 1), ("gemma-2-2b", 2), ("gemma-2-2b", 3), ("qwen3-4b", 1), ("qwen3-4b", 2), ("qwen3-4b", 3)}
    candidate = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    candidate["default_membership"] = rp.EXPLORATORY_OPEN
    _write(tmp_path / "candidate.json", candidate)
    rc, open_, out = _urgency(root, "open2", {}, env={rp.POLICY_ENV: str(tmp_path / "candidate.json")})
    assert rc == 0, out
    got = {(r["model"], r["batch"], r["index"]) for r in open_["rows"]}
    assert ("gemma-4-e2b", BATCH, 1) in got and ("qwen3-4b", BATCH, 4) in got
    assert not any(batch.startswith("agscen_") for _, batch, _ in got)        # examples join no analysis
    assert "stimulus class hand_authored_exploratory (not a study batch) 1" in out
