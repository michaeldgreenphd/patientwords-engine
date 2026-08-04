"""Tests for the STAGED PatientAgentBench probe workflow (ops/pab_ci/).

The workflow is parked outside .github/ on purpose: copying it in is what makes
it real and pushing a trigger is what makes it spend, and both are owner
decisions. It is tested here anyway, because the one thing worse than an
unlanded workflow is a landed one that is wrong -- CI-side behaviour cannot be
exercised from this repo, so the wiring has to be checked by reading it, the way
CLAUDE.md prescribes.

Two failure modes these tests exist for:

* the push-path `defaults` dict not covering every trigger key. Unknown keys in
  a trigger file are silently ignored by design, so a key present in the trigger
  but missing from `defaults` is dropped without a word -- a run that quietly
  uses a default nobody chose.
* a secret reaching a log. Both repositories are public.
"""

import ast
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ROOT = Path(__file__).resolve().parents[1]
STAGED_DIR = _ROOT / "ops" / "pab_ci"
WORKFLOW_PATH = STAGED_DIR / "pab_probe.yml"
TRIGGER_KEY = "pab-probe"


@pytest.fixture(scope="module")
def raw() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow(raw) -> dict:
    return yaml.safe_load(raw)


@pytest.fixture(scope="module")
def defaults(raw) -> dict:
    """The push-path defaults dict, read out of the params heredoc."""
    block = re.search(r"defaults = (\{.*?\})\n", raw, re.DOTALL)
    assert block, "could not find the defaults dict in the params heredoc"
    literal = re.sub(r"\n\s*#[^\n]*", "", block.group(1))
    return ast.literal_eval(literal)


@pytest.fixture(scope="module")
def dispatch_inputs(workflow) -> dict:
    on = workflow.get("on") or workflow.get(True)
    return on["workflow_dispatch"]["inputs"]


def step_named(workflow, prefix, job="probe"):
    for step in workflow["jobs"][job]["steps"]:
        if step.get("name", "").startswith(prefix):
            return step
    raise AssertionError(f"no step named {prefix!r}")


class TestStagingBoundary:
    def test_staged_copy_is_kept(self):
        """The staged copy stays as the reviewed source of the landed file."""
        assert WORKFLOW_PATH.is_file()

    def test_landed_copy_matches_the_staged_one(self):
        """Landed 2026-08-04 by owner authorization. The two must not drift:
        the staged file is what these tests read, so a divergent landed copy
        would be untested."""
        landed = _ROOT / ".github" / "workflows" / "pab_probe.yml"
        if not landed.exists():
            pytest.skip("workflow not landed")
        assert landed.read_text(encoding="utf-8") == WORKFLOW_PATH.read_text(encoding="utf-8")


class TestWorkflowShape:
    def test_yaml_parses(self, workflow):
        assert isinstance(workflow, dict)
        assert workflow["name"].startswith("PatientAgentBench Probe")

    def test_has_both_entry_paths(self, workflow):
        # PyYAML reads a bare `on:` key as the boolean True.
        on = workflow.get("on") or workflow.get(True)
        assert "workflow_dispatch" in on
        assert on["push"]["paths"] == [f".github/trigger/{TRIGGER_KEY}.json"]

    def test_concurrency_cannot_evict_other_runs(self, workflow):
        """Every workflow here is one-running-plus-one-pending per group. A
        probe must have its own group or it could evict a pending trace, logits
        or lens run."""
        concurrency = workflow["concurrency"]
        assert concurrency["cancel-in-progress"] is False
        assert concurrency["group"].startswith("pab-probe-")

    def test_jobs_are_params_then_probe(self, workflow):
        assert list(workflow["jobs"]) == ["params", "probe"]
        assert workflow["jobs"]["probe"]["needs"] == "params"


class TestParamsWiring:
    """The heredoc pitfall CLAUDE.md names explicitly."""

    def test_defaults_cover_every_dispatch_input(self, defaults, dispatch_inputs):
        missing = sorted(set(dispatch_inputs) - set(defaults))
        assert missing == [], (
            f"trigger keys with no entry in the push-path defaults dict: {missing}. "
            "Unknown keys are silently ignored, so these would be dropped."
        )

    def test_defaults_add_nothing_the_dispatch_path_lacks(self, defaults,
                                                         dispatch_inputs):
        extra = sorted(set(defaults) - set(dispatch_inputs))
        assert extra == [], f"defaults keys with no dispatch input: {extra}"

    def test_every_param_is_exported_as_a_job_output(self, workflow, defaults):
        outputs = workflow["jobs"]["params"]["outputs"]
        assert sorted(outputs) == sorted(defaults)

    def test_defaults_are_all_strings(self, defaults):
        """The push path stringifies everything; a non-string default would
        compare unequal to the trigger value it is meant to mirror."""
        assert all(isinstance(v, str) for v in defaults.values())

    def test_max_spend_default_is_small(self, defaults):
        assert 0 < float(defaults["max_spend"]) <= 0.25

    def test_default_stage_is_the_cheap_one(self, defaults):
        """A trigger fired with no stage must land on the smoke test, not a
        full generate."""
        assert defaults["stage"] == "smoke"


class TestSpendGuards:
    def test_max_spend_is_validated_before_any_run(self, raw):
        assert 'raise SystemExit("max_spend must be > 0")' in raw

    def test_unknown_stage_is_refused(self, raw):
        assert "unknown stage" in raw

    def test_every_paid_step_carries_a_ceiling_or_a_config(self, workflow):
        assert "--max-spend" in step_named(workflow, "Tool-calling")["run"]

    @pytest.mark.parametrize("step", ["Generate", "Score an existing run"])
    def test_paid_run_stages_enforce_the_ceiling(self, workflow, step):
        """`max_spend` is bookkeeping until something stops the run. These two
        stages spend per-conversation and are the ones that can run away, so
        each must hand its ceiling to the fork's budget guard."""
        env = step_named(workflow, step)["env"]
        assert env["PW_MAX_SPEND_USD"] == "${{ needs.params.outputs.max_spend }}"

    @pytest.mark.parametrize("step", ["Generate", "Score an existing run"])
    def test_paid_run_stages_write_a_cost_sidecar(self, workflow, step):
        """A run that spends and leaves no sidecar is invisible to
        ledger_update.py, which folds data/pab/*.report.json."""
        report = step_named(workflow, step)["env"]["PW_SPEND_REPORT"]
        assert report.startswith("../data/pab/")
        assert report.endswith(".report.json")

    def test_generation_runs_sequentially(self, workflow):
        """The config orders assistants most-expensive-first so a ceiling trip
        loses a known tail. Parallel generation would scatter the loss across
        every model instead, which is only true while --max-parallel is 1."""
        commands = [line for line in step_named(workflow, "Generate")["run"].splitlines()
                    if not line.strip().startswith("#")]
        assert not any("--max-parallel" in line for line in commands)


class TestSecrets:
    def test_openrouter_key_is_bound_from_secrets(self, raw):
        assert "OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}" in raw

    def test_anthropic_key_only_on_the_scoring_stage(self, workflow):
        with_anthropic = [s for s in workflow["jobs"]["probe"]["steps"]
                          if "ANTHROPIC_API_KEY" in (s.get("env") or {})]
        assert len(with_anthropic) == 1
        assert with_anthropic[0].get("name", "").startswith("Score an existing run")

    def test_generation_stage_needs_no_anthropic_key(self, workflow):
        """The invariant is which *secrets* the step can reach, not the size of
        its env: the budget vars added alongside carry no credentials."""
        env = step_named(workflow, "Generate")["env"]
        secrets = {k: v for k, v in env.items() if "secrets." in str(v)}
        assert set(secrets) == {"OPENROUTER_API_KEY"}
        assert "ANTHROPIC_API_KEY" not in env

    def test_no_secret_is_echoed(self, raw):
        for line in raw.splitlines():
            if "secrets." in line and ("echo" in line or "print(" in line):
                pytest.fail(f"a secret may reach the log: {line.strip()}")

    def test_no_literal_key_material(self, raw):
        assert not re.search(r"sk-[a-zA-Z0-9_\-]{16,}", raw)


class TestLicenceBoundary:
    def test_the_fork_is_cloned_outside_this_repo_s_tree(self, workflow):
        checkout = step_named(workflow, "Check out the fork")
        assert checkout["with"]["path"].startswith(".pab-fork")

    def test_transcripts_are_uploaded_not_committed(self, workflow):
        """Conversations are derived from CC-BY-NC-4.0 cases; this repo is MIT.
        They leave as a build artifact until the boundary for derived artifacts
        is decided."""
        steps = workflow["jobs"]["probe"]["steps"]
        upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact"))
        assert upload["with"]["path"].startswith(".pab-fork/output")
        commit = step_named(workflow, "Commit the cost sidecar")
        assert "git add data/pab" in commit["run"]
        assert ".pab-fork" not in commit["run"]

    def test_sidecar_lands_where_the_ledger_scans(self, workflow):
        """ledger_update.py scans data/pab/*.report.json; a sidecar written
        anywhere else is spend the $2/day guard never sees."""
        assert "data/pab/" in step_named(workflow, "Tool-calling")["run"]


class TestRunbookIsPresent:
    def test_readme_explains_what_landing_it_does(self):
        readme = (STAGED_DIR / "README.md").read_text(encoding="utf-8")
        for phrase in ("fire_trigger.py", "OPENROUTER_API_KEY", "max_spend"):
            assert phrase in readme


class TestFireGuardRegistration:
    """KNOWN_KEYS must mirror the workflow's defaults dict exactly.

    The guard hard-errors on an unknown key precisely because CI silently
    ignores one; if the two sets drift, the guard either blocks a valid fire or
    waves through a typo that runs with defaults nobody chose.
    """

    @staticmethod
    def _fire_trigger():
        import importlib.util
        path = _ROOT / "scripts" / "fire_trigger.py"
        spec = importlib.util.spec_from_file_location("fire_trigger", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_trigger_is_registered(self):
        ft = self._fire_trigger()
        assert TRIGGER_KEY in ft.TRIGGERS

    def test_trigger_is_marked_paid(self):
        """It spends OpenRouter and, on the evaluate stage, Anthropic. An
        unpaid marking would skip the daily-ceiling check entirely."""
        ft = self._fire_trigger()
        assert TRIGGER_KEY in ft.PAID_TRIGGERS

    def test_known_keys_match_the_workflow_defaults(self, defaults):
        ft = self._fire_trigger()
        assert ft.KNOWN_KEYS[TRIGGER_KEY] == frozenset(defaults)


class TestGracefulStop:
    """A run that is cancelled at GitHub's 6h JOB limit loses everything: the
    remaining steps never run, so the transcripts are not uploaded and the cost
    sidecar is not written. Money spent, nothing to show, nothing in the ledger.
    Ending the STEP early instead keeps the job alive to save both."""

    def test_generation_stops_itself_before_the_job_limit(self, workflow):
        run = step_named(workflow, "Generate")["run"]
        assert "timeout --signal=INT" in run, (
            "generation has no self-imposed deadline; a slow run is cancelled "
            "by GitHub and its transcripts are lost"
        )
        assert "generate_timeout_minutes" in run

    def test_the_default_deadline_leaves_room_to_save_the_run(self, raw):
        """The upload and commit steps still have to run after generation
        stops, inside GitHub's 360-minute job limit."""
        default = re.search(
            r'generate_timeout_minutes:.*?default: "(\d+)"', raw, re.S).group(1)
        assert int(default) <= 330, (
            f"a {default}-minute deadline leaves under 30 minutes to upload "
            "and commit before the job is cancelled"
        )

    def test_an_early_stop_does_not_fail_the_job(self, workflow):
        """124 is timeout's deadline, 130 is SIGINT. Both mean 'partial run,
        keep the steps that save it' -- if they failed the job, the upload and
        the sidecar would be lost exactly when they matter most."""
        run = step_named(workflow, "Generate")["run"]
        assert "124|130" in run

    def test_partial_transcripts_are_still_uploaded(self, workflow):
        upload = step_named(workflow, "Upload transcripts")
        assert upload["if"].startswith("always()")
