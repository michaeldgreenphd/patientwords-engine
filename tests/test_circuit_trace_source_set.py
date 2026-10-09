"""The circuit-trace lane's `source_set` key (2026-10-09).

gemma-3-4b-it has no default graph source set on Neuronpedia, so every hosted
request this study sent for it came back HTTP 400 "Source Set Missing" (run
37960184793). The key passes a set through `medlang-batch-eval --source-set`.
Held here, each by running or parsing what CI runs:

- the fire path (scripts/fire_trigger.py, exit 3) and the params job's push-path
  heredoc, run as CI runs it, accept a slug and refuse the same values: anything
  that is not a short lower-case slug, a source set with more than one graph
  model, and a source set committed into trace_out/;
- the params job's `defaults` dict carries the key with an empty default, the
  dispatch path reads it, and the run step passes `--source-set` only when the
  resolved value is non-empty;
- batch_eval sends `sourceSetName` on the hosted request only when a set is
  given, tags features from that set, and records it in the summary;
- the exporters keep gating gemma-3-4b-it's clinical mass on the model, not on
  the summary's source_set.

The pairs written here are abstract placeholders, never study stimuli.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from conftest import build_fetcher, make_graph

import medlang_circuits.batch_eval as batch_eval
import medlang_circuits.graph_client as gc
from medlang_circuits.neuronpedia_features import FeatureFetcher

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "circuit_trace_evaluation.yml"
# the trigger directory, spelled once so no test body carries the literal path
TRIGGER_SUBDIR = Path(".github") / "trigger"
GEMMA3_SET = "gemmascope-2-transcoder-262k"


def _load_fire_trigger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fire_trigger_source_set", ROOT / "scripts" / "fire_trigger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ft = _load_fire_trigger()


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _params_step() -> dict:
    return next(s for s in _workflow()["jobs"]["params"]["steps"] if s.get("id") == "params")


def _params_heredoc() -> str:
    m = re.search(r"python - <<'EOF'\n(.*?)\nEOF", _params_step()["run"], re.S)
    assert m, "the params step no longer carries its python heredoc"
    return m.group(1)


def _run_step() -> dict:
    return next(s for s in _workflow()["jobs"]["trace"]["steps"]
                if str(s.get("name", "")).startswith("Run batch evaluation"))


def _run_params(tmp_path: Path, cfg: dict) -> tuple[int, dict, str]:
    """Run the params heredoc on the push path, as CI runs it; returns (rc, the outputs it wrote, stderr)."""
    trigger_dir = tmp_path / TRIGGER_SUBDIR
    trigger_dir.mkdir(parents=True, exist_ok=True)
    (trigger_dir / "circuit-trace.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith("IN_")}
    env.update({"EVENT_NAME": "push", "GITHUB_OUTPUT": str(out)})
    proc = subprocess.run([sys.executable, "-"], input=_params_heredoc(), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    outputs = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())
    return proc.returncode, outputs, proc.stderr


def _run_dispatch(tmp_path: Path, inputs: dict[str, str]) -> tuple[int, dict, str]:
    """Run the params heredoc on the dispatch path, as CI runs it, with these workflow_dispatch inputs."""
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith("IN_")}
    env.update({"EVENT_NAME": "workflow_dispatch", "GITHUB_OUTPUT": str(out)})
    env.update({"IN_" + k.upper(): v for k, v in inputs.items()})
    proc = subprocess.run([sys.executable, "-"], input=_params_heredoc(), cwd=tmp_path, capture_output=True,
                          text=True, env=env)
    outputs = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())
    return proc.returncode, outputs, proc.stderr


@pytest.fixture
def repo(tmp_path):
    """A throwaway repo layout for `fire --no-git` (tests/test_fire_trigger.py's fixture): a stub workflow naming
    the trigger path, and ops/."""
    (tmp_path / TRIGGER_SUBDIR).mkdir(parents=True)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "stub.yml").write_text('on:\n  push:\n    paths:\n      - ".github/trigger/circuit-trace.json"\n',
                                 encoding="utf-8")
    (tmp_path / "ops").mkdir()
    return tmp_path


def _fire(repo: Path, params: dict) -> int:
    argv = ["fire", "--repo", str(repo), "--trigger", "circuit-trace", "--params", json.dumps(params),
            "--note", "source_set test fire", "--no-git"]
    return ft.main(argv)


# the follow-up probe this key exists for: two pairs of gemma-3-4b-it, nothing committed
PROBE = {"graph_models": ["gemma-3-4b-it"], "source_set": GEMMA3_SET, "mode": "2panel",
         "pairs_file": "data/simulated/pairs_x.json", "offsets": [0], "sample_size": "2",
         "commit_outputs": "false"}

# Each is refused by both sides. A control character is refused before the slug rule reads the value (both sides'
# control-character check), so the newline case is held by the message "control character".
BAD_SLUGS = [
    "Gemmascope-2-transcoder-262k",      # upper case
    "-gemmascope",                       # would read as an option on the command line
    "gemmascope 2",                      # space
    "gemmascope;id",                     # shell metacharacter
    "$(id)",
    "`id`",
    "a/b",                               # path separator
    "a_b",                               # underscore is not in the slug alphabet
    "a" * 65,                            # longer than 64
    "gemmascope-2-transcoder-262k\n",    # control character
    None,                                # JSON null: both sides read it as the string "None"
    ["gemmascope-2-transcoder-262k"],    # a list: both sides read its str()
]


# --- the fire path ------------------------------------------------------------------------------------------------

def test_source_set_is_a_known_circuit_trace_key():
    assert "source_set" in ft.KNOWN_KEYS["circuit-trace"]


_NO_LIST = {k: v for k, v in PROBE.items() if k != "graph_models"}


@pytest.mark.parametrize("params", [
    PROBE,
    {**PROBE, "graph_models": "gemma-3-4b-it"},
    {**_NO_LIST, "graph_model": "gemma-3-4b-it"},
    {**_NO_LIST, "graph_model": "gemma-3-4b-it", "graph_models": ""},
    # the pilot root commits only summary parts, where no collector reads
    {**PROBE, "commit_outputs": True, "output_root": "pilot/traces",
     "pairs_file": "pilot/runs/run_a/trace/run_a_p.json"},
], ids=["list", "string", "graph_model", "empty-graph_models", "pilot-root-commit"])
def test_the_fire_path_accepts_a_slug_for_one_model(repo, params):
    assert ft.circuit_trace_source_set_problems(params) == []
    assert ft.validate_params("circuit-trace", params) is None
    assert _fire(repo, params) == 0
    written = json.loads((repo / TRIGGER_SUBDIR / "circuit-trace.json").read_text(encoding="utf-8"))
    assert written["source_set"] == GEMMA3_SET


@pytest.mark.parametrize("value", BAD_SLUGS, ids=repr)
def test_the_fire_path_refuses_anything_but_a_slug_with_exit_3(repo, value, capsys):
    assert _fire(repo, {**PROBE, "source_set": value}) == 3
    err = capsys.readouterr().err
    assert "source_set" in err and ("lower-case slug" in err or "control character" in err), err
    assert not (repo / TRIGGER_SUBDIR / "circuit-trace.json").exists()
    assert not (repo / "ops" / "trigger_journal.jsonl").exists()


@pytest.mark.parametrize("models", [["gemma-3-4b-it", "qwen3-4b"], "gemma-3-4b-it,gemma-2-2b",
                                    "gemma-3-4b-it qwen3-4b", "all", ["all"]], ids=repr)
def test_the_fire_path_refuses_a_source_set_with_several_graph_models(repo, models, capsys):
    assert _fire(repo, {**PROBE, "graph_models": models}) == 3
    assert "graph models" in capsys.readouterr().err
    assert not (repo / "ops" / "trigger_journal.jsonl").exists()


@pytest.mark.parametrize("commit", ["true", True, "TRUE"], ids=repr)
def test_the_fire_path_refuses_a_source_set_committed_into_trace_out(repo, commit, capsys):
    assert _fire(repo, {**PROBE, "commit_outputs": commit}) == 3
    assert "uncalibrated clinical mass" in capsys.readouterr().err


def test_without_a_source_set_every_earlier_shape_still_passes():
    """The key's absence (and "") is the server default: several models and a trace_out/ commit pass as before."""
    for params in ({"graph_models": "all", "commit_outputs": "true"},
                   {"graph_models": ["gemma-2-2b", "qwen3-4b"], "commit_outputs": "true", "source_set": ""},
                   dict(ft.PARK_DEFAULTS["circuit-trace"])):
        assert ft.circuit_trace_source_set_problems(params) == []
        assert ft.validate_params("circuit-trace", params) is None
    assert "source_set" not in ft.PARK_DEFAULTS["circuit-trace"]


def test_the_models_resolve_as_the_params_job_resolves_them():
    assert ft.circuit_trace_models({}) == ["gemma-2-2b"]
    assert ft.circuit_trace_models({"graph_model": "gemma-3-4b-it"}) == ["gemma-3-4b-it"]
    assert ft.circuit_trace_models({"graph_models": ["qwen3-4b", "gemma-3-4b-it"]}) == ["qwen3-4b", "gemma-3-4b-it"]
    assert ft.circuit_trace_models({"graph_models": "all"}) == list(ft.CIRCUIT_TRACE_ALL_MODELS)
    heredoc = _params_heredoc()
    expanded = re.search(r'if "all" in models:\n\s+models = (\[[^\]]*\])', heredoc)
    assert expanded and json.loads(expanded.group(1)) == list(ft.CIRCUIT_TRACE_ALL_MODELS)


def test_the_two_slug_patterns_are_one():
    heredoc = _params_heredoc()
    m = re.search(r're\.fullmatch\(r"([^"]+)", source_set\)', heredoc)
    assert m, "the params job no longer checks source_set with re.fullmatch"
    assert m.group(1) == ft.CIRCUIT_TRACE_SOURCE_SET_RE.pattern


# --- the params job, run as CI runs it ------------------------------------------------------------------------------

def test_the_params_jobs_defaults_dict_has_the_key_with_an_empty_default():
    """The push path copies only keys of `defaults` from the trigger file, so a key missing there is silently
    dropped (AGENTS.md, Tests); its default must be "" so a fire without it passes no --source-set."""
    block = _params_step()["run"]
    block = block[block.index("defaults = {"):]
    block = block[:block.index("}") + 1]
    assert '"source_set": ""' in block


def test_the_params_job_resolves_the_probe(tmp_path):
    rc, outputs, err = _run_params(tmp_path, PROBE)
    assert rc == 0, err
    assert json.loads(outputs["config"])["source_set"] == GEMMA3_SET
    assert json.loads(outputs["models"]) == ["gemma-3-4b-it"]


def test_the_params_job_resolves_an_absent_key_to_empty(tmp_path):
    rc, outputs, err = _run_params(tmp_path, dict(ft.PARK_DEFAULTS["circuit-trace"]))
    assert rc == 0, err
    assert json.loads(outputs["config"])["source_set"] == ""


@pytest.mark.parametrize("value", BAD_SLUGS, ids=repr)
def test_the_params_job_refuses_every_value_the_fire_path_refuses(tmp_path, value):
    cfg = {**PROBE, "source_set": value}
    assert ft.circuit_trace_source_set_problems(cfg) or ft.control_char_values(cfg)
    rc, outputs, err = _run_params(tmp_path, cfg)
    assert rc != 0 and outputs == {}, err
    assert "source_set" in err


@pytest.mark.parametrize("cfg", [
    {**PROBE, "graph_models": ["gemma-3-4b-it", "qwen3-4b"]},
    {**PROBE, "graph_models": "all"},
    {**PROBE, "commit_outputs": True},
    {**PROBE, "commit_outputs": "true"},
], ids=["two-models", "all", "commit-bool", "commit-str"])
def test_the_params_job_and_the_fire_path_refuse_the_same_shapes(tmp_path, cfg):
    assert ft.circuit_trace_source_set_problems(cfg)
    rc, outputs, err = _run_params(tmp_path, cfg)
    assert rc != 0 and outputs == {}, err
    assert "source_set" in err


def test_the_dispatch_path_reads_the_input(tmp_path):
    assert "IN_SOURCE_SET" in _params_step()["env"]
    inputs = _workflow()[True]["workflow_dispatch"]["inputs"]
    assert inputs["source_set"]["type"] == "string" and inputs["source_set"]["default"] == ""
    rc, outputs, err = _run_dispatch(tmp_path, {"graph_model": "gemma-3-4b-it", "source_set": GEMMA3_SET,
                                                "commit_outputs": "false"})
    assert rc == 0, err
    assert json.loads(outputs["config"])["source_set"] == GEMMA3_SET
    rc, outputs, err = _run_dispatch(tmp_path, {"graph_model": "gemma-3-4b-it", "source_set": "$(id)"})
    assert rc != 0 and outputs == {} and "source_set" in err


def test_the_run_step_passes_the_flag_only_when_the_value_is_non_empty(tmp_path):
    """The run step's bash, cut at the medlang-batch-eval call, prints the argument array it would pass."""
    step = _run_step()
    assert step["env"]["SOURCE_SET"] == "${{ fromJson(needs.params.outputs.config).source_set }}"
    script = step["run"]
    assert "${{ fromJson(needs.params.outputs.config).source_set }}" not in script, \
        "the value reaches bash only through the environment, never interpolated into the script"
    script = re.sub(r"\$\{\{[^}]*\}\}", "X", script)            # the expressions Actions would substitute
    script = script.replace('medlang-batch-eval "${ARGS[@]}"', 'printf "%s\\n" "${ARGS[@]}"')
    assert 'printf "%s\\n" "${ARGS[@]}"' in script

    def args(source_set: str) -> list[str]:
        env = {**os.environ, "OFFSET": "0", "OUT_DIR": "out", "SOURCE_SET": source_set, "SCREEN": "",
               "MITIGATE": "false", "GEN_EXPL": "0", "STEER_VALIDATE": "0", "STEER_BOOST": "0", "STEER_PLACEBO": "0",
               "MEDLANG_TRANSLATION_PLACEBO": "0"}
        proc = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True, env=env)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.splitlines()

    assert "--source-set" not in args("")
    with_set = args(GEMMA3_SET)
    assert with_set[with_set.index("--source-set") + 1] == GEMMA3_SET


# --- batch_eval: the hosted request, the fetcher and the summary ----------------------------------------------------

class _Resp:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _FakeRequests:
    """Drop-in for graph_client.requests (tests/test_graph_client.py's): records generate bodies, no network."""

    def __init__(self):
        self.posts: list[dict] = []
        outer = self

        class _Session:
            def __init__(self):
                self.headers = {}

            def post(self, url, json=None, timeout=None):
                outer.posts.append(json)
                return _Resp({})

            def get(self, url, timeout=None):
                return _Resp({"url": "https://files.example/graph.json"})

        self.Session = _Session

    def get(self, url, timeout=None):
        return _Resp(make_graph())


def _run_batch(tmp_path, monkeypatch, source_set):
    fake = _FakeRequests()
    monkeypatch.setattr(gc, "requests", fake)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    monkeypatch.delenv(gc.GRAPH_MODEL_ENV_VAR, raising=False)
    fetcher_calls: list[dict] = []

    def fetcher(**kwargs):
        # the real class decides whether a set is accepted (it raises without one for gemma-3-4b-it); the stub
        # answers the feature lookups, so nothing reaches the network
        fetcher_calls.append(kwargs)
        real = FeatureFetcher(**kwargs)
        stub = build_fetcher()
        stub.source_set = real.source_set
        return stub

    monkeypatch.setattr(batch_eval, "FeatureFetcher", fetcher)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(json.dumps([{"top_prompt": "one phrasing of the fox",
                                  "bottom_prompt": "another phrasing of the fox"}]), encoding="utf-8")
    out = tmp_path / "out"
    batch_eval.run_batch(str(pairs), out_dir=str(out), use_llm_translation=False, dpi=50,
                         graph_model="gemma-3-4b-it", source_set=source_set)
    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    return fake.posts, fetcher_calls, summary


def test_batch_eval_sends_source_set_name_and_tags_from_it_when_given(tmp_path, monkeypatch):
    posts, fetcher_calls, summary = _run_batch(tmp_path, monkeypatch, GEMMA3_SET)
    assert len(posts) == 2                                    # clinical + patient
    for body in posts:
        assert body["modelId"] == "gemma-3-4b-it"
        assert body["sourceSetName"] == GEMMA3_SET
    assert [c["source_set"] for c in fetcher_calls] == [GEMMA3_SET]
    assert summary["graph_model"] == "gemma-3-4b-it"
    assert summary["source_set"] == GEMMA3_SET


def test_batch_eval_omits_source_set_name_when_not_given(tmp_path, monkeypatch):
    """Today's request, unchanged: no sourceSetName (the server's default, which gemma-3-4b-it lacks), and the
    fetcher falls back to NullFetcher because no set is registered for the model, so the summary names none."""
    posts, fetcher_calls, summary = _run_batch(tmp_path, monkeypatch, None)
    assert len(posts) == 2
    assert all("sourceSetName" not in body for body in posts)
    assert [c["source_set"] for c in fetcher_calls] == [None]
    assert summary["source_set"] is None


# --- publication stays gated on the model ---------------------------------------------------------------------------

def _featured_set(path: Path) -> set[str]:
    m = re.search(r"^FEATURED = (\{[^}]*\})", path.read_text(encoding="utf-8"), re.M)
    assert m, f"{path.name} no longer defines FEATURED as a literal set"
    return set(json.loads(m.group(1).replace("{", "[").replace("}", "]")))


@pytest.mark.parametrize("script", ["export_frontend_simulated.py", "export_archive.py"])
def test_gemma_3_clinical_mass_stays_unpublished(script):
    """Both exporters null clinical_mass by model id (FEATURED), not by the summary's source_set, so a gemma-3-4b-it
    summary that names a source set still publishes none. (PR #93 replaces FEATURED with CALIBRATED_FEATURE_MODELS;
    gemma-3-4b-it is in neither.)"""
    path = ROOT / "scripts" / script
    if "CALIBRATED_FEATURE_MODELS" in path.read_text(encoding="utf-8"):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from feature_models import CALIBRATED_FEATURE_MODELS  # type: ignore[import-not-found]
        finally:
            sys.path.pop(0)
        assert "gemma-3-4b-it" not in CALIBRATED_FEATURE_MODELS
    else:
        assert "gemma-3-4b-it" not in _featured_set(path)
