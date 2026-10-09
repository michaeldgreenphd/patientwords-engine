"""Revision pinning for every Hugging Face load (enforced 2026-10-09).

`scripts/logits_eval.py` used to load each model from the repo's moving `main`
and only record the commit it got. EPFLiGHT/Apertus-8B-MeditronFO replaced its
weights upstream on 2026-10-06, after all 102 landed summaries for
`apertus-8b-meditronfo` recorded ef2b141d..., so the next fire would have
measured a different model under the same short id. These tests hold the pin
table and the refusals in place for the four loaders: logits_eval,
depth_probe, verify_probs and activation_patch.

Offline: transformers, torch, interp_engine and transformer_lens are replaced
by small fakes in sys.modules, so nothing is imported for real or downloaded.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


le = _load("logits_eval")
ap = _load("activation_patch")
dp = _load("depth_probe")
vp = _load("verify_probs")

APERTUS_LANDED = "ef2b141da7ccc347c2a13b2518370ba6a8a2b745"
MEDITRON3_LANDED = "783c241b18b84692689e0336170b345e5732e48e"
OTHER_SHA = "4409c940755421bb9b2e2e6ad8df48f52b02932f"   # Apertus's 2026-10-06 replacement weights


# --- the table --------------------------------------------------------------------------------------------------------

def test_every_live_registry_id_has_a_full_sha_pin():
    for short_id in set(le.HF_IDS) - le.TOMBSTONES:
        pin = le.HF_REVISIONS.get(short_id)
        assert pin is not None and le.FULL_SHA.fullmatch(pin), (short_id, pin)


def test_pins_and_tombstones_partition_the_registry():
    assert set(le.HF_REVISIONS) <= set(le.HF_IDS)
    assert set(le.HF_IDS) - set(le.HF_REVISIONS) == le.TOMBSTONES
    assert le.TOMBSTONES == {"biomistral-7b", "meditron-7b", "gemma-2-9b"}


def test_apertus_is_pinned_to_the_weights_every_landed_summary_measured():
    assert le.HF_REVISIONS["apertus-8b-meditronfo"] == APERTUS_LANDED


def test_meditron3_points_at_its_new_org_with_the_landed_commit():
    assert le.HF_IDS["meditron3-8b"] == "EPFLiGHT/Meditron3-8B"
    assert le.HF_REVISIONS["meditron3-8b"] == MEDITRON3_LANDED


def test_pins_match_what_the_landed_logits_summaries_recorded():
    """Each pin is the one non-null revision its model's landed summaries recorded (older summaries
    predate revision capture and carry no `revision` key). A pin that drifts from the record, or a model
    whose summaries start recording a second commit, fails here."""
    seen = {}
    for path in ROOT.glob("trace_out/*/batch_summary*.json"):
        s = json.loads(path.read_text(encoding="utf-8"))
        if s.get("backend") != "logits":
            continue
        rev = (s.get("inference") or {}).get("revision")
        if rev is not None:
            seen.setdefault(s.get("graph_model"), set()).add(rev)
    if not seen:
        pytest.skip("no landed logits summaries in this checkout")
    for model, revs in seen.items():
        assert revs == {le.HF_REVISIONS[model]}, (model, revs)


def test_activation_patch_ids_share_the_logits_eval_repos_and_pins():
    for short_id, repo in ap.HF_IDS.items():
        assert le.HF_IDS[short_id] == repo, short_id
        assert short_id in le.HF_REVISIONS, short_id


# --- resolution (before anything is downloaded) -----------------------------------------------------------------------

def test_short_id_resolves_to_its_pin():
    assert le.resolve_pinned_model("apertus-8b-meditronfo") == ("EPFLiGHT/Apertus-8B-MeditronFO", APERTUS_LANDED)
    # repeating the pin is allowed
    assert le.resolve_pinned_model("apertus-8b-meditronfo", APERTUS_LANDED)[1] == APERTUS_LANDED


@pytest.mark.parametrize("tomb", sorted({"biomistral-7b", "meditron-7b", "gemma-2-9b"}))
def test_tombstones_are_refused(tomb):
    with pytest.raises(le.UnpinnedModelError, match="tombstone"):
        le.resolve_pinned_model(tomb)


def test_short_id_with_a_contradicting_revision_is_refused():
    with pytest.raises(le.RevisionMismatchError):
        le.resolve_pinned_model("apertus-8b-meditronfo", OTHER_SHA)


def test_arbitrary_repo_needs_an_explicit_full_sha():
    with pytest.raises(le.UnpinnedModelError, match="--revision"):
        le.resolve_pinned_model("some-org/some-model")
    with pytest.raises(le.UnpinnedModelError, match="40-hex"):
        le.resolve_pinned_model("some-org/some-model", "main")
    with pytest.raises(le.UnpinnedModelError, match="40-hex"):
        le.resolve_pinned_model("some-org/some-model", OTHER_SHA[:12])
    assert le.resolve_pinned_model("some-org/some-model", OTHER_SHA) == ("some-org/some-model", OTHER_SHA)


def test_registered_repo_under_other_weights_is_refused():
    with pytest.raises(le.RevisionMismatchError, match="apertus-8b-meditronfo"):
        le.resolve_pinned_model("EPFLiGHT/Apertus-8B-MeditronFO", OTHER_SHA)
    assert le.resolve_pinned_model("EPFLiGHT/Apertus-8B-MeditronFO", APERTUS_LANDED)[1] == APERTUS_LANDED


def test_check_resolved_revision_refuses_other_and_missing_commits():
    le.check_resolved_revision("r/m", APERTUS_LANDED, APERTUS_LANDED)
    with pytest.raises(le.RevisionMismatchError):
        le.check_resolved_revision("r/m", APERTUS_LANDED, OTHER_SHA)
    with pytest.raises(le.RevisionMismatchError):
        le.check_resolved_revision("r/m", APERTUS_LANDED, None)


# --- fakes ------------------------------------------------------------------------------------------------------------

def _fake_transformers(monkeypatch, commit):
    """A transformers stand-in recording every from_pretrained call; the model's config resolves to `commit`."""
    calls = []

    class _Tok:
        @staticmethod
        def from_pretrained(repo, **kw):
            calls.append(("tokenizer", repo, kw))
            return types.SimpleNamespace(kind="tokenizer")

    class _Model:
        @staticmethod
        def from_pretrained(repo, **kw):
            calls.append(("model", repo, kw))
            return types.SimpleNamespace(config=types.SimpleNamespace(_commit_hash=commit), eval=lambda: None)

    fake = types.ModuleType("transformers")
    fake.AutoTokenizer = _Tok
    fake.AutoModelForCausalLM = _Model
    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = "bf16"
    monkeypatch.setitem(sys.modules, "transformers", fake)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    return calls


def _no_ml_imports(monkeypatch):
    """Any import of the ML stack fails: a refusal must happen before it."""
    for name in ("transformers", "torch", "interp_engine", "transformer_lens"):
        monkeypatch.setitem(sys.modules, name, None)


# --- logits_eval ------------------------------------------------------------------------------------------------------

def test_load_pinned_passes_revision_to_tokenizer_and_model(monkeypatch):
    calls = _fake_transformers(monkeypatch, APERTUS_LANDED)
    le.load_pinned("EPFLiGHT/Apertus-8B-MeditronFO", APERTUS_LANDED)
    assert [c[0] for c in calls] == ["tokenizer", "model"]
    for _, repo, kw in calls:
        assert repo == "EPFLiGHT/Apertus-8B-MeditronFO"
        assert kw["revision"] == APERTUS_LANDED
        assert kw["trust_remote_code"] is False
    assert calls[1][2]["use_safetensors"] is True


def test_load_pinned_refuses_a_resolved_commit_other_than_the_pin(monkeypatch):
    _fake_transformers(monkeypatch, OTHER_SHA)
    with pytest.raises(le.RevisionMismatchError):
        le.load_pinned("EPFLiGHT/Apertus-8B-MeditronFO", APERTUS_LANDED)


def _pairs(tmp_path, pairs=()):
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps(list(pairs)), encoding="utf-8")
    return str(p)


@pytest.mark.parametrize("argv_tail", [
    ["--model", "gemma-2-9b"],                                    # tombstone
    ["--model", "some-org/some-model"],                           # repo id, no --revision
    ["--model", "apertus-8b-meditronfo", "--revision", OTHER_SHA],  # contradicts the pin
])
def test_logits_main_refuses_before_importing_anything(monkeypatch, tmp_path, argv_tail):
    _no_ml_imports(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        le.main(["--pairs", _pairs(tmp_path), "--out", str(tmp_path / "out"), *argv_tail])
    assert exc.value.code not in (0, None)
    assert "refused:" in str(exc.value.code)
    assert not (tmp_path / "out").exists()


def test_logits_main_refuses_a_mismatched_load(monkeypatch, tmp_path):
    _fake_transformers(monkeypatch, OTHER_SHA)
    with pytest.raises(SystemExit) as exc:
        le.main(["--pairs", _pairs(tmp_path), "--model", "apertus-8b-meditronfo",
                 "--out", str(tmp_path / "out")])
    assert "RevisionMismatchError" in str(exc.value.code)
    assert not (tmp_path / "out").exists()


def test_logits_summary_records_the_pin_beside_the_resolved_revision(monkeypatch, tmp_path):
    _fake_transformers(monkeypatch, APERTUS_LANDED)
    monkeypatch.setattr(le, "build_result", lambda i, pair, tok, fn, topk: {
        "index": i, "probabilities": {"clinical": None, "patient": None}, "language_penalty": None})
    out = tmp_path / "out"
    le.main(["--pairs", _pairs(tmp_path, [{"top_prompt": "a", "bottom_prompt": "b"}]),
             "--model", "apertus-8b-meditronfo", "--out", str(out)])
    s = json.loads((out / "batch_summary.part_01.json").read_text(encoding="utf-8"))
    assert s["inference"]["revision"] == APERTUS_LANDED
    assert s["inference"]["revision_pinned"] == APERTUS_LANDED
    assert s["inference"]["hf_id"] == "EPFLiGHT/Apertus-8B-MeditronFO"
    assert s["completed"] is True


def test_build_summary_keeps_revision_and_adds_revision_pinned():
    s = le.build_summary("m", "r/m", [], revision="a" * 40, revision_pinned="a" * 40)
    assert s["inference"]["revision"] == "a" * 40
    assert s["inference"]["revision_pinned"] == "a" * 40


# --- interp-engine loaders (depth_probe, verify_probs) ----------------------------------------------------------------

def _fake_interp_engine(monkeypatch, commit):
    seen = {}

    def load_model(hf_id, **kw):
        seen["hf_id"], seen["kw"] = hf_id, kw
        return types.SimpleNamespace(hf_model=types.SimpleNamespace(config=types.SimpleNamespace(_commit_hash=commit)),
                                     n_layers=2, tokenizer=kw.get("tokenizer"))

    lifecycle = types.SimpleNamespace(warmup=lambda: None, shutdown=lambda: None)
    fake = types.ModuleType("interp_engine")
    fake.load_model = load_model
    fake.sync_model = lambda model: lifecycle
    monkeypatch.setitem(sys.modules, "interp_engine", fake)
    return seen


def _tiers(tmp_path):
    p = tmp_path / "tiers.json"
    p.write_text(json.dumps({"status": "test", "tokens": {}}), encoding="utf-8")
    return str(p)


def _engine_argv(script, tmp_path, model, out):
    argv = ["--pairs", _pairs(tmp_path), "--model", model, "--out", str(out)]
    return argv + (["--tiers", _tiers(tmp_path)] if script is dp else [])


@pytest.mark.parametrize("script", [dp, vp], ids=["depth_probe", "verify_probs"])
def test_engine_loader_pins_tokenizer_and_weights_and_records_both(monkeypatch, tmp_path, script):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    calls = _fake_transformers(monkeypatch, None)
    seen = _fake_interp_engine(monkeypatch, le.HF_REVISIONS["qwen3-4b"])
    out = tmp_path / "out"
    script.main(_engine_argv(script, tmp_path, "qwen3-4b", out))
    pin = le.HF_REVISIONS["qwen3-4b"]
    assert seen["hf_id"] == "Qwen/Qwen3-4B"
    assert seen["kw"]["model_kwargs"] == {"revision": pin}
    assert seen["kw"]["trust_remote_code"] is False
    assert calls == [("tokenizer", "Qwen/Qwen3-4B", {"revision": pin, "trust_remote_code": False})]
    (summary,) = list(out.glob("*.json"))
    inf = json.loads(summary.read_text(encoding="utf-8"))["inference"]
    # depth_probe recorded revision null on every run before this change (its flush never passed it)
    assert inf["revision"] == pin
    assert inf["revision_pinned"] == pin


@pytest.mark.parametrize("script", [dp, vp], ids=["depth_probe", "verify_probs"])
def test_engine_loader_refuses_a_mismatched_load(monkeypatch, tmp_path, script):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    _fake_transformers(monkeypatch, None)
    _fake_interp_engine(monkeypatch, OTHER_SHA)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        script.main(_engine_argv(script, tmp_path, "qwen3-4b", out))
    assert "RevisionMismatchError" in str(exc.value.code)
    assert not out.exists()


@pytest.mark.parametrize("script", [dp, vp], ids=["depth_probe", "verify_probs"])
def test_engine_loader_refuses_a_tombstone_before_importing_the_engine(monkeypatch, tmp_path, script):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    _no_ml_imports(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        script.main(_engine_argv(script, tmp_path, "meditron-7b", tmp_path / "out"))
    assert "UnpinnedModelError" in str(exc.value.code)


# --- activation_patch (transformer_lens) ------------------------------------------------------------------------------

def _fake_transformer_lens(monkeypatch):
    seen = {}

    class HookedTransformer:
        @classmethod
        def from_pretrained_no_processing(cls, name, **kw):
            seen["name"], seen["kw"] = name, kw
            return types.SimpleNamespace(eval=lambda: None)

    fake = types.ModuleType("transformer_lens")
    fake.HookedTransformer = HookedTransformer
    monkeypatch.setitem(sys.modules, "transformer_lens", fake)
    return seen


def test_activation_patch_load_pins_tokenizer_weights_and_transformer_lens(monkeypatch):
    pin = le.HF_REVISIONS["gemma-2-2b"]
    calls = _fake_transformers(monkeypatch, pin)
    seen = _fake_transformer_lens(monkeypatch)
    model = ap.load_model("gemma-2-2b")
    assert [(c[0], c[1], c[2]["revision"]) for c in calls] == [
        ("tokenizer", "google/gemma-2-2b", pin), ("model", "google/gemma-2-2b", pin)]
    assert seen["kw"]["revision"] == pin
    assert model.resolved_revision == pin


def test_activation_patch_load_refuses_mismatch_and_unregistered(monkeypatch):
    _fake_transformers(monkeypatch, OTHER_SHA)
    _fake_transformer_lens(monkeypatch)
    errors = ap._logits_eval()
    with pytest.raises(errors.RevisionMismatchError):
        ap.load_model("gemma-2-2b")
    # an id logits_eval knows but transformer_lens support was never checked for is a bare repo id here
    with pytest.raises(errors.UnpinnedModelError):
        ap.load_model("llama-3.2-3b")


def test_activation_patch_main_refuses_an_unpinned_repo_before_importing(monkeypatch, tmp_path):
    _no_ml_imports(monkeypatch)
    pairs = _pairs(tmp_path, [{"top_prompt": "a", "bottom_prompt": "b", "target_clinical_token": " c"}])
    with pytest.raises(SystemExit) as exc:
        ap.main(["--pairs", pairs, "--model", "some-org/some-model", "--out", str(tmp_path / "out")])
    assert "UnpinnedModelError" in str(exc.value.code)


def test_activation_patch_scaffold_needs_no_pin_and_records_nulls(tmp_path):
    pairs = _pairs(tmp_path, [{"top_prompt": "a", "bottom_prompt": "b", "target_clinical_token": " c"}])
    ap.main(["--pairs", pairs, "--model", "some-org/some-model", "--out", str(tmp_path / "out"), "--scaffold"])
    s = json.loads((tmp_path / "out" / "batch_summary.part_01.json").read_text(encoding="utf-8"))
    assert s["inference"]["revision"] is None
    assert s["inference"]["revision_pinned"] is None
