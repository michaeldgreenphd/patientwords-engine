"""Re-grading landed Petri runs with another judge (petri-audit `mode: rejudge`).

A landed run's judge of record graded every planned judgment once, under one
judge model. Mode rejudge grades the same judgments again under a DIFFERENT
judge model, for the exploratory question of how much the judge itself moves
the measurement. It makes no target call and runs no adaptation: it reads the
source run's COMMITTED sanitised transcripts, plans exactly the judgments the
judge of record planned (the same prompt files, the same rubric, the same
rendered prompts and contexts, checked digest for digest against the judge of
record's rows), and sends each to the new judge under the same output
allowance and temperature.

Nothing under `data/petri/runs/` is written. Each source run's re-grade goes to
its own directory, `data/petri/rejudge/<judge slug>/<source run stem>/`,
holding `judgments.jsonl`, `analysis_rows.jsonl` (judge_runner.analysis_rows),
`rejudge_manifest.json` and the judge cost sidecar
`<stem>.rejudge_<workflow run id>.judge.report.json`. The manifests chain
(`data/petri/runs/manifests.chain`) is not appended to; `verify_output` checks
a re-grade on its own: its digests, and that the source run it names still
verifies and is still the bytes it read.

Append-only, as the runs are: a directory that holds a re-grade is never
written again. The one thing a directory may hold before a fire writes into it
is the judge sidecar of an earlier fire of the same judge over the same run
whose judge step failed: the workflow commits that sidecar (its spend) and no
outputs, and a retry is admitted beside it and names its own sidecar for its
own workflow run, as a readapt retry does (scripts/petri_audit/readapt.py).

One fire, one judge, one ceiling. `source_runs` may name several runs; they are
judged in order, each under what the fire's `judge_max_spend` has left
(`max_spend_usd` in its sidecar, with `fire_judge_max_spend_usd` and
`fire_spent_before_usd` beside it), and a run whose judge stopped at the
ceiling ends the fire: later runs are not started and write nothing. A
truncated re-grade is committed with `truncated` recorded; its directory is
then closed like any other (a resume would rewrite a landed judgments file and
its manifest, which the append-only rule forbids). So the plan sizes the
ceiling before any call (`estimate_cost`): the judge of record's recorded
tokens at the new judge's registry price is the expected cost, and a
`judge_max_spend` below the expected cost of every source run plus one call's
admission headroom is refused. The estimate ASSUMES the new judge's token
counts are close to the judge of record's: another tokenizer, or longer
answers, move it; the worst case beside it takes every answer at the full
`judge_max_tokens`. Each manifest records the estimate and the share of
judgments that were not rule-level not-applicable and came back null
(`counts.null_share`, beside the judge of record's), so a re-grade that is
complete but mostly null is visible as such.

A later source run whose judge aborts does not discard an earlier one that
completed: the workflow verifies, uploads and commits every re-grade that
wrote its manifest (`verify-rejudge --stage-list`), stages exactly those
directories and the fire's sidecars, and leaves the aborted run's partial
rows uncommitted.

A paid judge's key must be in the environment before the first call's marker
is written (`judge_key_problem`): a judge that cannot make a call must not
leave a marker the fallback would book the whole allotment against.

`mockllm/judge` (MOCK_JUDGE) is the rehearsal judge: every answer is the first
declared value, priced at zero, never committed. It exercises the whole path
(CI, or `cli rejudge-rehearse` locally into a temporary directory) at $0. It is
recognised by exact match only, and a spelling that differs from a zero-price
sentinel in case alone is refused (`sentinel_case_problem`): the workflow's
expression `!=` ignores case, so such a spelling would be a paid judge to the
Python checks and the rehearsal to the step conditions.

This module imports nothing from the harness, so every check is testable
under the engine's ordinary 3.11 environment. Every refusal is named
(RejudgeError), never guessed over.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .framework import (
    ADVICE_RUBRIC,
    ADVICE_RUBRIC_REF,
    FRAMEWORK_DIR,
    OUTCOME_REGISTRY,
    ROOT,
    SEED_FILE,
    canonical_json,
    load_json,
    sha256_file,
    sha256_text,
    validate_with_refs,
    write_json,
)
from .manifest import CHAIN_FILE, verify_chain, verify_run
from .spend import (
    ZERO_PRICE_MODELS,
    judge_billing_channel,
    judge_key_routing_problems,
    openrouter_price_problems,
    registry_spec_to_inspect,
    resolve_registry_price,
)

MODE = "rejudge"
MOCK_JUDGE = "mockllm/judge"
MANIFEST_NAME = "rejudge_manifest.json"
MANIFEST_VERSION = "0.1"
MANIFEST_SCHEMA = FRAMEWORK_DIR / "petri_rejudge_manifest.schema.json"
JUDGMENTS_NAME = "judgments.jsonl"
ANALYSIS_NAME = "analysis_rows.jsonl"
OUTPUT_FILES = (JUDGMENTS_NAME, ANALYSIS_NAME, MANIFEST_NAME)
DEFAULT_ROOT = ROOT / "data" / "petri" / "rejudge"
TASK = "petri-audit-rejudge"
# a source run's directory name, as mode run writes it (`run_<workflow run id>_<attempt>`)
STEM_PATTERN = r"run_[0-9]+_[0-9]+"
# what follows `<stem>` in the name of a rejudge's judge sidecar (`judge_report_name`); scripts/fire_trigger.py holds a
# copy (PETRI_REJUDGE_JUDGE_SUFFIX), which tests/test_petri_audit_rejudge.py keeps equal to this one
JUDGE_REPORT_SUFFIX_PATTERN = r"\.rejudge_[0-9]+\.judge\.report\.json"
SLUG_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_RUN_ID = re.compile(r"[0-9]+")
_COMMIT = re.compile(r"[0-9a-f]{40}")


class RejudgeError(ValueError):
    """A named refusal: the rejudge does not start (or stops before writing anything more)."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ names


def parse_source_runs(value: Any) -> list[str]:
    """The source run stems a fire names: space-separated text (a JSON list is joined, as the params job joins
    one), each `run_<id>_<attempt>` in ASCII digits, none twice, at least one."""
    if isinstance(value, list):
        tokens = [str(v) for v in value]
    elif isinstance(value, str):
        tokens = value.split()
    else:
        raise RejudgeError(f"source_runs must be space-separated run stems, got {value!r}")
    if not tokens:
        raise RejudgeError("mode rejudge needs source_runs, the stems of the landed runs under data/petri/runs to "
                           "re-grade (for example run_36076994201_1)")
    bad = [t for t in tokens if not re.fullmatch(STEM_PATTERN, t)]
    if bad:
        raise RejudgeError(f"source_runs {bad} are not run stems (run_<workflow run id>_<attempt>)")
    if len(set(tokens)) != len(tokens):
        raise RejudgeError(f"source_runs names a run twice ({tokens}); one fire judges each run once")
    return tokens


def judge_slug(spec: str) -> str:
    """The directory a judge's re-grades live under: the spec with every run of characters outside
    [A-Za-z0-9._-] replaced by one hyphen (`openrouter:openai/gpt-5.4-mini` is `openrouter-openai-gpt-5.4-mini`).
    The manifest records the exact spec; `verify_output` checks the directory is its slug. Raises for a spec whose
    slug could name anything but one plain directory. scripts/fire_trigger.py holds a copy (petri_rejudge_slug)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(spec).strip()).strip("-")
    if not re.fullmatch(SLUG_PATTERN, slug):
        raise RejudgeError(f"judge spec {spec!r} gives no usable directory name ({slug!r})")
    return slug


def judge_report_name(stem: str, workflow_run_id: Any) -> str:
    """The judge cost sidecar a rejudge writes for one source run: named for the rejudging workflow run, so a
    retry after a fire whose judge failed never rewrites the sidecar that failure committed (the ledger keys
    sidecars by bare filename, and that one's spend is already booked to its own fire)."""
    run_id = str(workflow_run_id)
    if not _RUN_ID.fullmatch(run_id):
        raise RejudgeError(f"the rejudge workflow run id must be ASCII digits, got {workflow_run_id!r}")
    return f"{stem}.rejudge_{run_id}.judge.report.json"


def is_judge_report(name: str, stem: str) -> bool:
    return re.fullmatch(re.escape(stem) + JUDGE_REPORT_SUFFIX_PATTERN, name) is not None


def output_dir(root: Path | str, spec: str, stem: str) -> Path:
    return Path(root) / judge_slug(spec) / stem


def judge_identity(spec: str) -> str:
    """The Inspect-form model a registry judge spec calls (`spend.registry_spec_to_inspect`), so two spellings of
    one judge (`claude-haiku-4-5`, `anthropic:claude-haiku-4-5`) compare equal. A spec that cannot be expanded is a
    refusal, never treated as different."""
    try:
        return registry_spec_to_inspect(spec)
    except ValueError as exc:
        raise RejudgeError(f"judge spec {spec!r} cannot be resolved to the model it calls ({exc})") from None


def same_judge(a: str, b: str) -> bool:
    """Whether two judge specs name the same judge: the exact string, or the same model once each is expanded to
    the Inspect form it calls. Routes that reach the same weights under different provider slugs (an
    OpenRouter-routed copy of the judge of record) are not recognised here; the manifest records both specs."""
    return a.strip() == b.strip() or judge_identity(a) == judge_identity(b)


# ------------------------------------------------------------ the source


def _chain_lines(runs_dir: Path) -> dict[str, str]:
    path = runs_dir / CHAIN_FILE
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rel, digest = line.strip().rsplit(" ", 1)
            out[rel] = digest
    return out


JUDGE_OF_RECORD_KEYS = ("judge_model", "judge_max_tokens", "temperature", "planned", "judged", "null",
                        "not_applicable", "truncated", "cost_usd")


def source_record(runs_dir: Path | str, stem: str) -> dict:
    """The landed source run as a rejudge binds it: it verifies on its own (`manifest.verify_run`: its manifest,
    and every artifact it names, the judgments included), the chain file names its manifest at its current digest,
    and a judge of record is bound. Raises RejudgeError naming what is wrong."""
    runs_dir = Path(runs_dir)
    run_dir = runs_dir / stem
    if not (run_dir / "manifest.json").is_file():
        raise RejudgeError(f"{stem}: no landed run under {runs_dir} (no manifest.json); a rejudge re-grades a run "
                           "whose outputs were committed")
    problems = verify_run(run_dir)
    if problems:
        raise RejudgeError(f"{stem}: the source run does not verify on its own ({'; '.join(problems[:4])})")
    manifest = load_json(run_dir / "manifest.json")
    chained = _chain_lines(runs_dir).get(f"{stem}/manifest.json")
    if chained is None:
        raise RejudgeError(f"{stem}: {CHAIN_FILE} does not name {stem}/manifest.json; only a landed, chained run is "
                           "re-graded")
    if chained != manifest["chain"]["manifest_sha256"]:
        raise RejudgeError(f"{stem}: {CHAIN_FILE} names its manifest at {chained[:12]}, but the manifest digests to "
                           f"{manifest['chain']['manifest_sha256'][:12]}")
    artifacts = manifest.get("artifacts") or {}
    jor = artifacts.get("judge_of_record")
    if not artifacts.get("judgments_path") or not isinstance(jor, dict) or not jor.get("judge_model"):
        raise RejudgeError(f"{stem}: no judge of record is bound in its manifest, so there is nothing to re-grade "
                           "against")
    return {"run_stem": stem, "run_id": manifest.get("run_id"), "eval_id": manifest.get("eval_id"),
            "manifest_sha256": sha256_file(run_dir / "manifest.json"),
            "chain_manifest_sha256": manifest["chain"]["manifest_sha256"],
            "transcripts_sha256": artifacts.get("transcripts_sha256"),
            "judgments_sha256": artifacts.get("judgments_sha256"),
            "judge_of_record": {k: jor.get(k) for k in JUDGE_OF_RECORD_KEYS}}


def build_plans(runs_dir: Path | str, stem: str, seeds_path: Path | str | None = None) -> tuple[list, dict, dict]:
    """(plans, source manifest, seeds by id): the judgments the judge of record planned, planned again from the
    source run's committed transcripts under the prompt files, the rubric and the seed file in hand
    (`judge_runner.plan_run`, which refuses a seed file whose seeds differ from the ones the run recorded)."""
    from .judge_runner import load_rubric, plan_run, read_jsonl
    from .seeds import load_seed_file

    run_dir = Path(runs_dir) / stem
    manifest = load_json(run_dir / "manifest.json")
    records = read_jsonl(run_dir / "transcripts.jsonl")
    try:
        seed_set = load_seed_file(seeds_path or SEED_FILE)
        plans = plan_run(records, manifest, seed_set.seeds, outcomes=load_json(OUTCOME_REGISTRY), rubric=load_rubric())
    except (KeyError, ValueError) as exc:
        raise RejudgeError(f"{stem}: its judgments cannot be planned from the committed transcripts ({exc})") from None
    return plans, manifest, seed_set.seeds


def plan_key(p: Any) -> tuple:
    return (p.conversation_id, p.turn_id, p.kind, p.key, p.prompt_file_digest)


def _row_key(r: dict) -> tuple:
    return (r.get("conversation_id"), r.get("turn_id"), r.get("kind"), r.get("key"), r.get("prompt_file_digest"))


def _label(key: tuple) -> str:
    cid, tid, kind, name, _digest = key
    return f"{str(cid)[:12]} turn {tid} {kind}/{name}"


def parity_problems(plans: list, rows: list[dict]) -> list[str]:
    """Why the plans in hand are not the instrument the judge of record applied: the set of judgments (conversation,
    turn, kind, key and prompt-file digest) must be the same, and each one's rendered prompt and context must digest
    to what the judge of record's row recorded (a not-applicable plan: the same reason, and no prompt). The judge
    of record's latest row per judgment decides, as `cumulative_counts` reads it. Names identifiers only, never
    text."""
    latest: dict[tuple, dict] = {}
    for r in rows:
        latest[_row_key(r)] = r
    planned: dict[tuple, Any] = {}
    problems: list[str] = []
    for p in plans:
        if plan_key(p) in planned:
            problems.append(f"the plan names {_label(plan_key(p))} twice")
        planned[plan_key(p)] = p
    only_plan = sorted(set(planned) - set(latest), key=str)
    only_rows = sorted(set(latest) - set(planned), key=str)
    if only_plan:
        problems.append(f"{len(only_plan)} planned judgment(s) the judge of record never made (first: "
                        f"{_label(only_plan[0])}); the prompt files, the rubric or the planner changed since it ran")
    if only_rows:
        problems.append(f"{len(only_rows)} judgment(s) of the judge of record that are no longer planned (first: "
                        f"{_label(only_rows[0])}); the prompt files, the rubric or the planner changed since it ran")
    differ: list[tuple] = []
    for key in sorted(set(planned) & set(latest), key=str):
        p, r = planned[key], latest[key]
        if p.prompt is None:
            same = r.get("rendered_sha256") is None and r.get("not_applicable_reason") == p.not_applicable_reason
        else:
            same = r.get("rendered_sha256") == sha256_text(p.prompt) and r.get("context_sha256") == p.context_sha256
        if not same:
            differ.append(key)
    if differ:
        problems.append(f"{len(differ)} judgment(s) whose rendered prompt, context or not-applicable reason differs "
                        f"from what the judge of record was given (first: {_label(differ[0])})")
    return problems


def plan_digest(plans: list) -> str:
    """One digest over the plan: every judgment's identity and the digests of what the judge will be shown."""
    return sha256_text(canonical_json([[p.conversation_id, p.turn_id, p.kind, p.key, p.prompt_file_digest,
                                        sha256_text(p.prompt) if p.prompt is not None else None, p.context_sha256,
                                        p.not_applicable_reason] for p in plans]))


def instrument_block(plans: list) -> dict:
    """The instrument a rejudge applied, by digest: the outcome registry, the advice rubric, every outcome prompt
    file the plans use (its canonical digest, as the rows carry it, and its file digest), and the plan digest."""
    from .judge_runner import load_rubric, rubric_digest

    prompts: dict[str, dict] = {}
    for p in plans:
        if p.kind == "outcome" and p.prompt_ref and p.prompt_ref not in prompts:
            prompts[p.prompt_ref] = {"digest": p.prompt_file_digest, "sha256": sha256_file(ROOT / p.prompt_ref)}
    return {"outcome_registry": {"ref": OUTCOME_REGISTRY.relative_to(ROOT).as_posix(),
                                 "sha256": sha256_file(OUTCOME_REGISTRY)},
            "rubric": {"ref": ADVICE_RUBRIC_REF, "sha256": sha256_file(ADVICE_RUBRIC),
                       "digest": rubric_digest(load_rubric())},
            "prompt_files": dict(sorted(prompts.items())), "plan_sha256": plan_digest(plans), "planned": len(plans),
            "parity_with_judge_of_record": "exact"}


# --------------------------------------------------------- the output side


def output_dir_problems(out_dir: Path | str, stem: str) -> list[str]:
    """Why `out_dir` cannot receive this re-grade: it holds a re-grade already (append-only), or anything but the
    judge sidecars of earlier fires of this judge over this run (`is_judge_report`). Empty when it does not exist."""
    out_dir = Path(out_dir)
    if not out_dir.exists():
        return []
    if not out_dir.is_dir():
        return [f"{out_dir}: exists and is not a directory"]
    names = sorted(p.name for p in out_dir.iterdir())
    problems: list[str] = []
    landed = [n for n in names if n in OUTPUT_FILES]
    if landed:
        problems.append(f"{out_dir}: already holds a re-grade ({', '.join(landed)}); a landed rejudge is never "
                        "rewritten")
    other = [n for n in names if n not in OUTPUT_FILES and not is_judge_report(n, stem)]
    if other:
        problems.append(f"{out_dir}: holds files other than earlier rejudge fires' judge sidecars ({', '.join(other)})")
    return problems


def prior_reports(out_dir: Path | str, stem: str, *, judge_model: str, nonce: str | None, workflow_run_id: Any,
                  journal_entries: list[dict]) -> list[dict]:
    """The judge sidecars earlier fires of this judge over this run left in `out_dir` (a fire whose judge step
    failed commits its sidecar and nothing else), as the plan binds them: path, digest and the fire's nonce. Each
    must be a rejudge judge sidecar of this judge over this run, carry a nonce that is not this fire's and that
    exactly one petri-audit journal entry carries, and not be this fire's own. Raises RejudgeError otherwise."""
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return []
    own = judge_report_name(stem, workflow_run_id)
    found: list[dict] = []
    for path in sorted(p for p in out_dir.iterdir() if is_judge_report(p.name, stem)):
        label = f"{stem}: the earlier rejudge sidecar {path.name}"
        if path.name == own:
            raise RejudgeError(f"{label} is this fire's own and exists before it ran; a workflow run writes it once")
        try:
            report = load_json(path)
        except (OSError, ValueError) as exc:
            raise RejudgeError(f"{label} does not parse ({exc})") from None
        if not isinstance(report, dict):
            raise RejudgeError(f"{label} holds a {type(report).__name__}, not an object")
        if report.get("judge_model") != judge_model or report.get("source_run_stem") != stem:
            raise RejudgeError(f"{label} records judge {report.get('judge_model')!r} over "
                               f"{report.get('source_run_stem')!r}; a directory holds one judge's re-grades of one run")
        prior_nonce = report.get("journal_nonce")
        if not isinstance(prior_nonce, str) or not prior_nonce:
            raise RejudgeError(f"{label} records no journal_nonce, so the fire whose spend it booked cannot be found")
        if nonce and prior_nonce == nonce:
            raise RejudgeError(f"{label} carries this fire's nonce {nonce!r}; each fire books its own judge")
        entries = [e for e in journal_entries if e.get("trigger") == "petri-audit" and e.get("nonce") == prior_nonce]
        if len(entries) != 1:
            raise RejudgeError(f"{label}: {len(entries)} petri-audit journal entries carry its nonce {prior_nonce!r}; "
                               "exactly one fire must account for it")
        found.append({"path": path.name, "sha256": sha256_file(path), "journal_nonce": prior_nonce})
    return found


def kept_prior_problems(out_dir: Path | str, stem: str, prior: list[dict]) -> list[str]:
    """The earlier fires' sidecars are still exactly the ones the plan bound: the same set, each the same bytes."""
    out_dir = Path(out_dir)
    bound = {p["path"]: p["sha256"] for p in prior}
    present = sorted(p.name for p in out_dir.iterdir() if is_judge_report(p.name, stem)) if out_dir.is_dir() else []
    problems: list[str] = []
    for name in present:
        if name not in bound:
            problems.append(f"{name} appeared after the rejudge was planned; the plan bound {sorted(bound) or 'none'}")
        elif sha256_file(out_dir / name) != bound[name]:
            problems.append(f"{name} changed after the rejudge bound it; a landed judge sidecar is never rewritten")
    problems += [f"{name}, bound by the plan, is gone; its fire's judge spend is unbooked"
                 for name in sorted(set(bound) - set(present))]
    return problems


# -------------------------------------------------------------- the plan


def _money(value: Any, what: str) -> float:
    try:
        number = float(str(value))
    except ValueError:
        raise RejudgeError(f"{what} must be a finite number > 0, got {value!r}") from None
    if not math.isfinite(number) or number <= 0:
        raise RejudgeError(f"{what} must be a finite number > 0, got {value!r}")
    return number


def judge_spec_refusals(spec: str) -> list[str]:
    """Why a (non-rehearsal) judge spec cannot run on this lane, before any call: the registry must resolve it
    (`judge_runner.judge_spec_problems`, which also refuses the zero-price sentinels), its key must bill an
    account the lane books (`spend.judge_key_routing_problems`), and an `openrouter:` spec needs a reviewed
    per-model price (`spend.openrouter_price_problems`), as `cli judge` requires."""
    from .judge_runner import judge_spec_problems

    case_problem = sentinel_case_problem(spec)
    if case_problem:
        return [case_problem]
    problems = judge_spec_problems(spec)
    if problems:
        return problems
    problems = judge_key_routing_problems(spec)
    try:
        problems += openrouter_price_problems(registry_spec_to_inspect(spec))
    except ValueError as exc:
        problems.append(str(exc))
    return problems


def sentinel_case_problem(spec: str) -> str | None:
    """A spec that equals a zero-price test sentinel (`spend.ZERO_PRICE_MODELS`) in everything but case, which no
    judge is (review of PR #41): GitHub's expression `!=` compares strings ignoring case, so the workflow would read
    `MockLLM/Judge` as the rehearsal while every Python check reads it as a paid judge, sent to Anthropic as a bare
    model id and priced at the fallback rate. None for every other spec, the exact sentinels included."""
    folded = {m.lower() for m in ZERO_PRICE_MODELS}
    if spec.strip().lower() in folded and spec not in ZERO_PRICE_MODELS:
        return (f"judge spec {spec!r} differs from the test sentinel {spec.strip().lower()!r} in case alone; the "
                "workflow compares it ignoring case and the lane exactly, so it is refused rather than read two ways")
    return None


def judge_key_problem(spec: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Why the judge `spec` cannot make its first call in this environment: its registry provider names no key, or
    the key variable it names is unset or empty. Checked before the start marker is written (review of PR #41): the
    provider clients raise SystemExit on a missing key at the first call, which no handler below catches, and the
    marker would then have the fallback book the run's whole allotment for a call never made. None for the rehearsal
    judge, which calls nothing."""
    if spec == MOCK_JUDGE:
        return None
    from .judge_runner import _advice_eval_module

    environ = os.environ if environ is None else environ
    ae = _advice_eval_module()
    try:
        cfg = ae._resolve_spec(spec, ae._load_providers(ae.DEFAULT_PROVIDERS))["cfg"]
    except SystemExit as exc:
        return f"judge spec {spec!r}: {exc}"
    key_env = cfg.get("key_env") or ("ANTHROPIC_API_KEY" if cfg.get("api") == "anthropic" else None)
    if not key_env:
        return f"judge spec {spec!r}: its registry provider names no key_env, so no call can be authenticated"
    if not str(environ.get(key_env) or "").strip():
        return (f"judge {spec!r} bills {key_env}, which is unset or empty in this environment; no call is made and no "
                "start marker is written, so nothing is booked for this fire's judge")
    return None


def estimate_cost(plans: list, rows: list[dict], judge_model: str, judge_max_tokens: int) -> dict:
    """What re-grading these plans with `judge_model` is expected to cost, from the judge of record's recorded
    usage (review of PR #41). Every plan with a prompt is one call; its expected tokens are the judge of record's
    latest row for the same judgment (`cumulative_counts` reads the same row), or, where that row recorded no usage,
    the input bound `SpendCeiling` prices (`estimate_input_tokens`) and the full output allowance. The expected cost
    is those tokens at the new judge's registry price; the worst case keeps the recorded input and takes every
    answer at `judge_max_tokens`; the headroom is one call's worst case under the ceiling's own admission rule,
    which the last call needs free. ASSUMES the new judge's token counts are close to the judge of record's: a
    different tokenizer or longer answers move the expected figure, which is why the worst case is beside it."""
    from .judge_runner import estimate_input_tokens

    latest: dict[tuple, dict] = {}
    for r in rows:
        latest[_row_key(r)] = r
    price = resolve_registry_price(judge_model)
    calls = [p for p in plans if p.prompt is not None]
    tokens_in = tokens_out = without_usage = 0
    for p in calls:
        r = latest.get(plan_key(p)) or {}
        if r.get("input_tokens") is None or r.get("output_tokens") is None:
            tokens_in += estimate_input_tokens(p.prompt)
            tokens_out += judge_max_tokens
            without_usage += 1
        else:
            tokens_in += int(r["input_tokens"])
            tokens_out += int(r["output_tokens"])
    headroom = max((estimate_input_tokens(p.prompt) for p in calls), default=0) * price.input_per_mtok / 1e6 \
        + (judge_max_tokens * price.output_per_mtok / 1e6 if calls else 0.0)
    return {"calls": len(calls), "recorded_input_tokens": tokens_in, "recorded_output_tokens": tokens_out,
            "calls_without_recorded_usage": without_usage, "price_source": price.source,
            "input_per_mtok": price.input_per_mtok, "output_per_mtok": price.output_per_mtok,
            "expected_usd": round(tokens_in * price.input_per_mtok / 1e6 + tokens_out * price.output_per_mtok / 1e6, 6),
            "worst_case_usd": round(tokens_in * price.input_per_mtok / 1e6
                                    + len(calls) * judge_max_tokens * price.output_per_mtok / 1e6, 6),
            "last_call_headroom_usd": round(headroom, 6),
            "assumption": "the new judge's token counts are close to the judge of record's recorded ones"}


def null_share(judged: Any, null: Any) -> float | None:
    """The share of the judgments that were not not-applicable which came back null (no parseable value): null
    over judged plus null; None when there were none, or a count is missing."""
    if not isinstance(judged, int) or not isinstance(null, int) or judged + null == 0:
        return None
    return round(null / (judged + null), 6)


def make_plan(*, params: dict, runs_dir: Path | str, rejudge_root: Path | str, journal_entries: list[dict],
              workflow_run_id: Any, workflow_run_attempt: Any, commit: str) -> dict:
    """Everything the rejudge step needs, established before any call: the judge and its ceiling, and for each
    source run the landed run it binds (digests, judge of record), the output directory and what earlier fires
    left in it, and the plan digest after the parity check against the judge of record. `params` are the params
    job's resolved outputs (strings) with `_nonce`. Raises RejudgeError naming every problem found."""
    from .judge_runner import TIER_TEMPERATURE, read_jsonl

    if str(params.get("mode", "")) != MODE:
        raise RejudgeError(f"rejudge planning needs mode {MODE}, got {params.get('mode')!r}")
    stems = parse_source_runs(params.get("source_runs"))
    if str(params.get("judge", "")) != "true":
        raise RejudgeError("mode rejudge runs a judge (judge true): the judge is its only spend")
    judge_model = params.get("judge_model")
    if not isinstance(judge_model, str) or not judge_model or judge_model != judge_model.strip():
        raise RejudgeError(f"mode rejudge needs judge_model spelled exactly, got {judge_model!r}")
    case_problem = sentinel_case_problem(judge_model)
    if case_problem:
        raise RejudgeError(case_problem)
    rehearsal = judge_model == MOCK_JUDGE
    fire_ceiling = _money(params.get("judge_max_spend"), "judge_max_spend")
    try:
        judge_max_tokens = int(str(params.get("judge_max_tokens")))
    except ValueError:
        judge_max_tokens = 0
    if judge_max_tokens <= 0:
        raise RejudgeError(f"judge_max_tokens must be a positive integer, got {params.get('judge_max_tokens')!r}")
    commit_outputs = str(params.get("commit_outputs", ""))
    if commit_outputs not in ("true", "false"):
        raise RejudgeError(f"commit_outputs must be true or false, got {params.get('commit_outputs')!r}")
    if rehearsal and commit_outputs == "true":
        raise RejudgeError(f"a rehearsal ({MOCK_JUDGE}) is never committed; it needs commit_outputs false")
    nonce = params.get("_nonce") or None
    if not rehearsal and (not isinstance(nonce, str) or nonce != nonce.strip()):
        raise RejudgeError("a paid rejudge carries its fire's _nonce, the join key between the journal entry that "
                           f"reserved its judge's ceiling and the sidecars it lands; got {params.get('_nonce')!r}")
    run_id = str(workflow_run_id)
    if not _RUN_ID.fullmatch(run_id):
        raise RejudgeError(f"the rejudge workflow run id must be ASCII digits, got {workflow_run_id!r}")
    attempt = str(workflow_run_attempt)
    if not rehearsal and attempt != "1":
        raise RejudgeError(f"a paid rejudge runs on its workflow run's first attempt only, got attempt {attempt!r}; a "
                           "re-run has no journal reservation of its own, so re-fire through scripts/fire_trigger.py")
    if not _COMMIT.fullmatch(str(commit or "")):
        raise RejudgeError(f"the rejudge commit must be a 40-hex commit id, got {commit!r}")
    problems: list[str] = [] if rehearsal else judge_spec_refusals(judge_model)
    if problems:
        raise RejudgeError("; ".join(problems))
    slug = judge_slug(judge_model)
    runs_dir, rejudge_root = Path(runs_dir), Path(rejudge_root)
    seeds_file = str(params.get("seeds_file") or SEED_FILE)
    # the whole chain, once: every landed manifest, its links and every artifact it names (`manifest.verify_chain`)
    chain_ok, chain_msg = verify_chain(runs_dir)
    if not chain_ok:
        problems.append(f"{runs_dir}/{CHAIN_FILE} does not verify ({chain_msg})")
    sources: list[dict] = []
    for stem in stems:
        try:
            src = source_record(runs_dir, stem)
        except RejudgeError as exc:
            problems.append(str(exc))
            continue
        jor = src["judge_of_record"]
        try:
            if same_judge(judge_model, jor["judge_model"]):
                problems.append(f"{stem}: {judge_model!r} is its judge of record ({jor['judge_model']!r}); a rejudge "
                                "grades with a different judge")
        except RejudgeError as exc:
            problems.append(f"{stem}: {exc}")
        if jor.get("judge_max_tokens") is None or int(jor["judge_max_tokens"]) != judge_max_tokens:
            problems.append(f"{stem}: its judge of record ran with judge_max_tokens {jor.get('judge_max_tokens')!r}; "
                            f"a rejudge applies the same instrument, so it needs that allowance, not {judge_max_tokens}")
        if jor.get("temperature") is None or float(jor["temperature"]) != TIER_TEMPERATURE:
            problems.append(f"{stem}: its judge of record ran at temperature {jor.get('temperature')!r}; this build "
                            f"judges at {TIER_TEMPERATURE}")
        out_dir = rejudge_root / slug / stem
        dir_problems = output_dir_problems(out_dir, stem)
        problems += dir_problems
        prior: list[dict] = []
        if not dir_problems:
            try:
                prior = prior_reports(out_dir, stem, judge_model=judge_model, nonce=nonce, workflow_run_id=run_id,
                                      journal_entries=journal_entries)
            except RejudgeError as exc:
                problems.append(str(exc))
        try:
            plans, _manifest, _seeds = build_plans(runs_dir, stem, seeds_file)
        except RejudgeError as exc:
            problems.append(str(exc))
            continue
        of_record_rows = read_jsonl(runs_dir / stem / JUDGMENTS_NAME)
        parity = parity_problems(plans, of_record_rows)
        problems += [f"{stem}: {p}" for p in parity]
        sources.append({"run_stem": stem, "source": src, "prior_judge_reports": prior,
                        "plan_sha256": plan_digest(plans), "planned": len(plans),
                        "estimate": estimate_cost(plans, of_record_rows, judge_model, judge_max_tokens)})
    # the ceiling must admit the whole expected re-grade: a truncated re-grade closes its directory for good
    estimate = {"expected_usd": round(sum(x["estimate"]["expected_usd"] for x in sources), 6),
                "worst_case_usd": round(sum(x["estimate"]["worst_case_usd"] for x in sources), 6),
                "last_call_headroom_usd": max((x["estimate"]["last_call_headroom_usd"] for x in sources), default=0.0),
                "assumption": "the new judge's token counts are close to the judge of record's recorded ones"}
    estimate["required_usd"] = round(estimate["expected_usd"] + estimate["last_call_headroom_usd"], 6)
    if sources and len(sources) == len(stems) and fire_ceiling < estimate["required_usd"]:
        problems.append(f"judge_max_spend {fire_ceiling:.4f} is below the expected cost of the re-grade, "
                        f"${estimate['expected_usd']:.4f} (the judge of record's recorded tokens at {judge_model}'s "
                        f"price, assuming its token counts are close), plus ${estimate['last_call_headroom_usd']:.4f} of "
                        "headroom the ceiling needs free to admit the last call; a truncated re-grade closes its "
                        "directory for good, so raise the ceiling to at least "
                        f"${estimate['required_usd']:.4f} (worst case, every answer at judge_max_tokens: "
                        f"${estimate['worst_case_usd']:.4f})")
    if problems:
        raise RejudgeError("; ".join(problems))
    return {"mode": MODE, "rehearsal": rehearsal, "exploratory": True, "judge_model": judge_model,
            "judge_slug": slug, "judge_max_spend_usd": fire_ceiling, "judge_max_tokens": judge_max_tokens,
            "commit_outputs": commit_outputs == "true", "seeds_file": seeds_file, "runs_dir": str(runs_dir),
            "rejudge_root": str(rejudge_root), "source_runs": stems,
            "fire": {"workflow_run_id": run_id, "workflow_run_attempt": attempt, "commit": str(commit),
                     "journal_nonce": nonce},
            "estimate": estimate, "sources": sources}


# ------------------------------------------------------------ execution


def mock_answers(plans: list) -> dict[str, str]:
    """The rehearsal judge's answer to every prompt it will be shown: an outcome plan's first declared value, a tier
    plan's first tier with every declared flag false. A structural stand-in, never a measurement."""
    answers: dict[str, str] = {}
    for p in plans:
        if p.prompt is None:
            continue
        if p.kind == "tier":
            answers[p.prompt] = json.dumps({"tier": p.allowed_values[0], "flags": {f: False for f in p.allowed_flags}})
        else:
            answers[p.prompt] = p.allowed_values[0]
    return answers


def rehearsal_client(plans: list) -> Any:
    from .judge_runner import MockJudge

    answers = mock_answers(plans)
    return MockJudge(lambda prompt: answers[prompt], model_spec=MOCK_JUDGE)


def default_client(spec: str, plans: list) -> Any:
    """The judge client for a spec: the rehearsal's MockJudge for MOCK_JUDGE, else the registry's provider client."""
    if spec == MOCK_JUDGE:
        return rehearsal_client(plans)
    from .judge_runner import RegistryJudge

    return RegistryJudge(spec)


def manifest_digest(manifest: dict) -> str:
    body = dict(manifest)
    body["manifest_sha256"] = ""
    return sha256_text(canonical_json(body))


def _counts(sidecar: dict, rows: list[dict]) -> dict:
    from .judge_runner import cumulative_counts

    totals = cumulative_counts(rows)
    return {"planned": int(sidecar["planned"]), "keys": totals["keys"], "judged": totals["judged"],
            "null": totals["null"], "not_applicable": totals["not_applicable"],
            "null_share": null_share(totals["judged"], totals["null"]),
            "truncated": bool(sidecar["truncated"]), "stopped_early": bool(sidecar["stopped_early"]),
            "call_failures": int(sidecar["call_failures"]), "calls_without_usage": totals["calls_without_usage"]}


def build_manifest(*, plan: dict, source: dict, position: int, instrument: dict, sidecar: dict, rows: list[dict],
                   out_dir: Path, report_name: str, analysis_count: int, now_fn: Callable[[], str]) -> dict:
    price = resolve_registry_price(plan["judge_model"])
    manifest = {
        "rejudge_manifest_version": MANIFEST_VERSION, "mode": MODE, "exploratory": True,
        "rehearsal": bool(plan["rehearsal"]), "created_utc": now_fn(),
        "source": source["source"],
        "judge": {"judge_model": plan["judge_model"], "judge_slug": plan["judge_slug"],
                  "inspect_name": registry_spec_to_inspect(plan["judge_model"]),
                  "billing_channel": judge_billing_channel(plan["judge_model"]), "price_source": price.source,
                  "input_per_mtok": price.input_per_mtok, "output_per_mtok": price.output_per_mtok,
                  "judge_max_tokens": plan["judge_max_tokens"], "temperature": sidecar["temperature"],
                  "max_spend_usd": sidecar["max_spend_usd"], "fire_judge_max_spend_usd": plan["judge_max_spend_usd"],
                  "fire_spent_before_usd": sidecar["fire_spent_before_usd"]},
        "instrument": instrument,
        "fire": {**plan["fire"], "source_runs": list(plan["source_runs"]), "position": position},
        "counts": {**_counts(sidecar, rows),
                   "judge_of_record_null_share": null_share(source["source"]["judge_of_record"].get("judged"),
                                                            source["source"]["judge_of_record"].get("null"))},
        "estimate": dict(source["estimate"]),
        "cost_usd": sidecar["cost_usd"],
        "artifacts": {"judgments": {"path": JUDGMENTS_NAME, "sha256": sha256_file(out_dir / JUDGMENTS_NAME),
                                    "rows": len(rows)},
                      "analysis_rows": {"path": ANALYSIS_NAME, "sha256": sha256_file(out_dir / ANALYSIS_NAME),
                                        "rows": analysis_count},
                      "judge_report": {"path": report_name, "sha256": sha256_file(out_dir / report_name)}},
        "manifest_sha256": "",
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    return manifest


def started_marker(started_dir: Path | str, stem: str) -> Path:
    return Path(started_dir) / f"{stem}.json"


def execute(plan: dict, *, started_dir: Path | str, client_factory: Callable[[str, list], Any] = default_client,
            now_fn: Callable[[], str] = utc_now_iso, environ: Mapping[str, str] | None = None) -> dict:
    """Run the plan: for each source run in order, re-check what the plan bound, judge every planned judgment with
    the plan's judge under what the fire's ceiling has left, then write the analysis rows and the manifest.
    Returns {"results": [...], "aborted": bool, "spent_usd": float}. A run whose judge stopped at the ceiling ends
    the fire (later runs are `not_started` and write nothing); a judge client that raises ends it too, with its
    sidecar written (`aborted`). Before the first call for a run, a marker naming its sidecar and allotment is
    written under `started_dir` (outside the checkout), which `impute_missing_reports` reads if the process dies."""
    from .judge_runner import (
        TIER_TEMPERATURE,
        JudgeAborted,
        SpendCeiling,
        analysis_rows,
        labels_from_manifest,
        read_jsonl,
        run_judgments,
    )

    judge_model, slug = plan["judge_model"], plan["judge_slug"]
    runs_dir, root = Path(plan["runs_dir"]), Path(plan["rejudge_root"])
    fire = plan["fire"]
    # before any marker is written: a judge whose key is absent fails at its first call with SystemExit, which leaves
    # no sidecar, and the marker would have the fallback book the whole allotment for a call that was never made
    key_problem = None if plan["rehearsal"] else judge_key_problem(judge_model, environ)
    if key_problem:
        raise RejudgeError(key_problem)
    price = resolve_registry_price(judge_model)
    channel = judge_billing_channel(judge_model)
    fire_ceiling = float(plan["judge_max_spend_usd"])
    started_dir = Path(started_dir)
    started_dir.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    results: list[dict] = []
    stop_reason: str | None = None
    for position, source in enumerate(plan["sources"], start=1):
        stem = source["run_stem"]
        out_dir = root / slug / stem
        if stop_reason is not None:
            results.append({"run_stem": stem, "status": "not_started", "reason": stop_reason})
            continue
        # what the plan bound is re-read before anything is written: the source run, the output directory and the
        # earlier fires' sidecars in it, and the plan itself (the checkout the plan was made in is this one)
        problems = output_dir_problems(out_dir, stem) + kept_prior_problems(out_dir, stem, source["prior_judge_reports"])
        if sha256_file(runs_dir / stem / "manifest.json") != source["source"]["manifest_sha256"]:
            problems.append(f"{stem}: the source manifest changed after the rejudge bound it")
        plans, manifest, seeds = build_plans(runs_dir, stem, plan["seeds_file"])
        if plan_digest(plans) != source["plan_sha256"]:
            problems.append(f"{stem}: the plan built now differs from the plan the rejudge bound")
        if problems:
            raise RejudgeError("; ".join(problems))
        remaining = round(fire_ceiling - spent, 8)
        if remaining <= 0:
            # the runs before this one spent the whole ceiling without the last of them being stopped by it (its final
            # call fitted exactly); nothing is left to admit a call here, so this run is not started
            results.append({"run_stem": stem, "status": "not_started", "reason": "the fire's judge ceiling is spent"})
            stop_reason = "the fire's judge ceiling is spent"
            continue
        ceiling = SpendCeiling(remaining, price.input_per_mtok, price.output_per_mtok, plan["judge_max_tokens"])
        client = client_factory(judge_model, plans)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_name = judge_report_name(stem, fire["workflow_run_id"])
        write_json(started_marker(started_dir, stem), {"run_stem": stem, "out_dir": str(out_dir),
                                                        "report_path": str(out_dir / report_name),
                                                        "max_spend_usd": remaining, "fire_spent_before_usd": spent})
        extra = {"task": TASK, "mode": MODE, "run_id": source["source"]["run_id"],
                 "eval_id": source["source"]["eval_id"], "source_run_stem": stem, "judge_slug": slug,
                 "billing_channel": channel, "price_source": price.source, "input_per_mtok": price.input_per_mtok,
                 "output_per_mtok": price.output_per_mtok, "journal_nonce": fire["journal_nonce"],
                 "rejudge_workflow_run_id": fire["workflow_run_id"],
                 "rejudge_workflow_run_attempt": fire["workflow_run_attempt"], "rejudge_commit": fire["commit"],
                 "fire_judge_max_spend_usd": fire_ceiling, "fire_spent_before_usd": spent,
                 "fire_source_runs": list(plan["source_runs"]), "rehearsal": bool(plan["rehearsal"]),
                 "exploratory": True}
        try:
            sidecar = run_judgments(plans, client, out_path=out_dir / JUDGMENTS_NAME, ceiling=ceiling,
                                    judge_max_tokens=plan["judge_max_tokens"], labels=labels_from_manifest(manifest),
                                    report_path=out_dir / report_name, sidecar_extra=extra, now_fn=now_fn)
        except JudgeAborted as exc:
            spent = round(spent + float(exc.sidecar.get("cost_usd") or 0.0), 8)
            results.append({"run_stem": stem, "status": "aborted", "error": str(exc), "cost_usd": exc.sidecar.get("cost_usd"),
                            "report": report_name})
            stop_reason = f"the judge aborted on {stem}"
            continue
        spent = round(spent + float(sidecar["cost_usd"]), 8)
        rows = read_jsonl(out_dir / JUDGMENTS_NAME)
        arows = analysis_rows(rows, manifest, seeds)
        (out_dir / ANALYSIS_NAME).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in arows),
                                             encoding="utf-8")
        record = build_manifest(plan=plan, source=source, position=position, instrument=instrument_block(plans),
                                sidecar={**sidecar, "temperature": TIER_TEMPERATURE}, rows=rows, out_dir=out_dir,
                                report_name=report_name, analysis_count=len(arows), now_fn=now_fn)
        problems = validate_with_refs(record, load_json(MANIFEST_SCHEMA))
        if problems:
            raise RejudgeError(f"{stem}: the rejudge manifest does not validate ({'; '.join(problems[:6])})")
        write_json(out_dir / MANIFEST_NAME, record)
        results.append({"run_stem": stem, "status": "truncated" if sidecar["truncated"] else "complete",
                        "out_dir": str(out_dir), "cost_usd": sidecar["cost_usd"], "counts": record["counts"]})
        if sidecar["truncated"]:
            stop_reason = f"the fire's judge ceiling stopped the judge on {stem}"
    return {"results": results, "aborted": any(r["status"] == "aborted" for r in results), "spent_usd": spent}


# ---------------------------------------------------------- verification


def verify_output(out_dir: Path | str, runs_dir: Path | str | None = None) -> list[str]:
    """Every problem with one re-grade directory on its own: the manifest parses, validates and digests to its
    own seal; the directory is `<judge slug>/<source stem>` for the judge and run it records; every artifact
    exists and digests to its recorded value; the rows are this judge's and agree with the recorded counts; the
    sidecar is this fire's, for this run, and records the judgments file as it stands; and nothing else is in the
    directory but earlier fires' sidecars. With `runs_dir`, the source run must still be the bytes the rejudge
    read and still verify on its own (`manifest.verify_run`), with the chain file naming it at that digest."""
    from .judge_runner import cumulative_counts, read_jsonl

    out_dir = Path(out_dir)
    path = out_dir / MANIFEST_NAME
    if not path.is_file():
        return [f"{out_dir}: {MANIFEST_NAME} is missing"]
    try:
        manifest = load_json(path)
    except ValueError as exc:
        return [f"{out_dir}: {MANIFEST_NAME} does not parse ({exc})"]
    if not isinstance(manifest, dict):
        return [f"{out_dir}: {MANIFEST_NAME} holds a {type(manifest).__name__}, not an object"]
    problems = [f"manifest: {p}" for p in validate_with_refs(manifest, load_json(MANIFEST_SCHEMA))]
    if problems:
        return problems
    if manifest["manifest_sha256"] != manifest_digest(manifest):
        problems.append("manifest: manifest_sha256 does not match the manifest body")
    stem, judge = manifest["source"]["run_stem"], manifest["judge"]
    if out_dir.name != stem:
        problems.append(f"{out_dir.name}: the manifest re-grades {stem}, not the run this directory is named for")
    try:
        slug = judge_slug(judge["judge_model"])
    except RejudgeError as exc:
        problems.append(str(exc))
        slug = None
    if slug is not None and (judge["judge_slug"] != slug or out_dir.parent.name != slug):
        problems.append(f"{out_dir.parent.name}/{out_dir.name}: judge {judge['judge_model']!r} re-grades under "
                        f"{slug!r}, and the manifest records {judge['judge_slug']!r}")
    arts = manifest["artifacts"]
    for fam, entry in arts.items():
        fpath = out_dir / entry["path"]
        if Path(entry["path"]).name != entry["path"]:
            problems.append(f"{fam}: {entry['path']} is not a file directly in the re-grade directory")
        elif not fpath.is_file():
            problems.append(f"{fam}: {entry['path']} is missing")
        elif sha256_file(fpath) != entry["sha256"]:
            problems.append(f"{fam}: {entry['path']} does not digest to its recorded value")
    if arts["judgments"]["path"] != JUDGMENTS_NAME or arts["analysis_rows"]["path"] != ANALYSIS_NAME:
        problems.append("artifacts: the judgments and analysis rows are recorded under other names than the files "
                        "their consumers open")
    fire = manifest["fire"]
    try:
        expected_report = judge_report_name(stem, fire["workflow_run_id"])
    except RejudgeError as exc:
        problems.append(str(exc))
        expected_report = None
    if expected_report is not None and arts["judge_report"]["path"] != expected_report:
        problems.append(f"judge_report: recorded as {arts['judge_report']['path']}, expected {expected_report}")
    if problems:
        return problems
    rows = read_jsonl(out_dir / JUDGMENTS_NAME)
    if len(rows) != arts["judgments"]["rows"]:
        problems.append(f"judgments: {len(rows)} rows, the manifest records {arts['judgments']['rows']}")
    others = sorted({str(r.get("judge_model")) for r in rows if r.get("judge_model") != judge["judge_model"]})
    if others:
        problems.append(f"judgments: rows carry judge spec(s) {others}, not {judge['judge_model']!r}")
    totals = cumulative_counts(rows)
    counts = manifest["counts"]
    for key in ("keys", "judged", "null", "not_applicable", "calls_without_usage"):
        if totals[key] != counts[key]:
            problems.append(f"counts: {key} is {totals[key]} in the judgments, the manifest records {counts[key]}")
    if counts["null_share"] != null_share(totals["judged"], totals["null"]):
        problems.append(f"counts: null_share {counts['null_share']!r} is not the judgments' "
                        f"{null_share(totals['judged'], totals['null'])!r}")
    jor = manifest["source"]["judge_of_record"]
    if counts["judge_of_record_null_share"] != null_share(jor.get("judged"), jor.get("null")):
        problems.append("counts: judge_of_record_null_share is not the recorded judge of record's")
    analysis = read_jsonl(out_dir / ANALYSIS_NAME)
    if len(analysis) != arts["analysis_rows"]["rows"] or len(analysis) != len(rows):
        problems.append(f"analysis_rows: {len(analysis)} rows for {len(rows)} judgments (manifest "
                        f"{arts['analysis_rows']['rows']}); the analysis keeps one row per judgment")
    report = load_json(out_dir / arts["judge_report"]["path"])
    expected = {"judgments_sha256": arts["judgments"]["sha256"], "journal_nonce": fire["journal_nonce"],
                "rejudge_workflow_run_id": fire["workflow_run_id"], "source_run_stem": stem,
                "judge_model": judge["judge_model"], "cost_usd": manifest["cost_usd"],
                "max_spend_usd": judge["max_spend_usd"], "task": TASK}
    for key, value in expected.items():
        if report.get(key) != value:
            problems.append(f"judge_report: {key} is {report.get(key)!r}, the manifest records {value!r}")
    extra = sorted(p.name for p in out_dir.iterdir() if p.name not in OUTPUT_FILES and p.name != expected_report
                   and not is_judge_report(p.name, stem))
    if extra:
        problems.append(f"{out_dir.name}: holds files a rejudge does not write ({', '.join(extra)})")
    if runs_dir is not None:
        problems += source_still_verifies(Path(runs_dir), manifest["source"])
    return problems


def source_still_verifies(runs_dir: Path, source: dict) -> list[str]:
    stem = source["run_stem"]
    run_dir = runs_dir / stem
    if not (run_dir / "manifest.json").is_file():
        return [f"source {stem}: no longer under {runs_dir}"]
    problems: list[str] = []
    if sha256_file(run_dir / "manifest.json") != source["manifest_sha256"]:
        problems.append(f"source {stem}: manifest.json is not the bytes the rejudge read")
    problems += [f"source {stem}: {p}" for p in verify_run(run_dir)]
    if _chain_lines(runs_dir).get(f"{stem}/manifest.json") != source["chain_manifest_sha256"]:
        problems.append(f"source {stem}: {CHAIN_FILE} does not name its manifest at the digest the rejudge read")
    manifest = load_json(run_dir / "manifest.json")
    if (manifest.get("artifacts") or {}).get("judgments_sha256") != source["judgments_sha256"]:
        problems.append(f"source {stem}: its judge of record's judgments are not the ones the rejudge compared with")
    return problems


def fire_outputs(plan: dict) -> tuple[list[Path], list[Path]]:
    """(re-grade directories, judge sidecars) this plan's fire left: every source run's directory holding a
    manifest (the executor writes it last, after the judgments, the analysis rows and the sidecar, so a run whose
    judge aborted or died has none), and this fire's own sidecar in every source run's directory, an aborted run's
    included. What the workflow verifies, seal-checks, uploads and stages: never the partial rows of an aborted run
    (review of PR #41: a later run's abort used to discard an earlier run's completed re-grade)."""
    root = Path(plan["rejudge_root"]) / plan["judge_slug"]
    dirs: list[Path] = []
    sidecars: list[Path] = []
    for source in plan["sources"]:
        d = root / source["run_stem"]
        if (d / MANIFEST_NAME).is_file():
            dirs.append(d)
        report = d / judge_report_name(source["run_stem"], plan["fire"]["workflow_run_id"])
        if report.is_file():
            sidecars.append(report)
    return dirs, sidecars


def output_dirs(root: Path | str) -> list[Path]:
    """Every re-grade directory under a rejudge root (`<slug>/<stem>` holding a manifest)."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.parent for p in root.glob(f"*/*/{MANIFEST_NAME}"))


# ------------------------------------------------ the fallback spend report


def impute_missing_reports(plan: dict, started_dir: Path | str, now_fn: Callable[[], str] = utc_now_iso) -> list[Path]:
    """For every source run whose judge started (its marker under `started_dir`) and left no sidecar (the process
    died, or the client raised before `run_judgments` could write), a sidecar booking that run's allotment: every
    call was admitted under the ceiling, so the allotment bounds what was spent, and the rows that survived are
    summed beside it (`judge-spend-report`'s rule). A zero-price judge books zero. Returns the sidecars written."""
    from .judge_runner import TIER_TEMPERATURE, cumulative_counts, read_jsonl

    started_dir = Path(started_dir)
    judge_model = plan["judge_model"]
    price = resolve_registry_price(judge_model)
    zero_priced = price.input_per_mtok == 0 and price.output_per_mtok == 0
    fire = plan["fire"]
    written: list[Path] = []
    for source in plan["sources"]:
        stem = source["run_stem"]
        marker = started_marker(started_dir, stem)
        if not marker.is_file():
            continue
        info = load_json(marker)
        out_dir = Path(plan["rejudge_root"]) / plan["judge_slug"] / stem
        report_path = out_dir / judge_report_name(stem, fire["workflow_run_id"])
        if report_path.is_file():
            continue
        judgments = out_dir / JUDGMENTS_NAME
        rows = read_jsonl(judgments)
        rows_cost = round(sum(float(r.get("cost_usd") or 0.0) for r in rows), 8)
        allotment = float(info["max_spend_usd"])
        if zero_priced:
            cost, basis = 0.0, "engine_repriced_from_inspect_model_usage"
            reason = f"rejudge judge started on {stem} and left no sidecar; zero-price judge, {len(rows)} row(s) survived"
        else:
            cost, basis = allotment, "ceiling_imputed:judge_aborted_without_sidecar"
            reason = (f"rejudge judge started on {stem} and left no sidecar; {len(rows)} row(s) survived summing to "
                      f"{rows_cost}, the last call is unaccounted for, so this run's allotment of the fire's judge "
                      "ceiling is booked")
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(report_path, {
            "run_utc": now_fn(), "judgments_file": JUDGMENTS_NAME, "judge_model": judge_model, "cost_usd": cost,
            "run_cost_usd": cost, "prior_cost_usd": 0.0, "rows_cost_usd": rows_cost, "cost_basis": basis,
            "max_spend_usd": allotment, "truncated": None, "aborted": True, "abort_error": None,
            "spend_report_reason": reason, "cumulative": cumulative_counts(rows),
            "judgments_sha256": sha256_file(judgments) if judgments.is_file() else None,
            "judge_max_tokens": plan["judge_max_tokens"], "temperature": TIER_TEMPERATURE, "task": TASK, "mode": MODE,
            "run_id": source["source"]["run_id"], "eval_id": source["source"]["eval_id"], "source_run_stem": stem,
            "judge_slug": plan["judge_slug"], "billing_channel": judge_billing_channel(judge_model),
            "price_source": price.source, "input_per_mtok": price.input_per_mtok,
            "output_per_mtok": price.output_per_mtok, "journal_nonce": fire["journal_nonce"],
            "rejudge_workflow_run_id": fire["workflow_run_id"],
            "rejudge_workflow_run_attempt": fire["workflow_run_attempt"], "rejudge_commit": fire["commit"],
            "fire_judge_max_spend_usd": float(plan["judge_max_spend_usd"]),
            "fire_spent_before_usd": float(info["fire_spent_before_usd"]),
            "fire_source_runs": list(plan["source_runs"]), "rehearsal": bool(plan["rehearsal"]),
            "exploratory": True})
        written.append(report_path)
    return written


# ------------------------------------------------------------- the summary


def render_summary(plan: dict | None, *, plan_error: str | None = None) -> str:
    """The job summary: the judge and the fire's ceiling, then per source run what landed (from its manifest, or
    its sidecar alone), counts and cost only; never a prompt, an answer or any transcript text."""
    if plan is None:
        return f"## Petri rejudge: refused before any call\n\n{plan_error or 'no plan was written'}\n"
    est = plan.get("estimate") or {}
    lines = [f"## Petri rejudge ({'rehearsal, ' if plan['rehearsal'] else ''}exploratory): {plan['judge_model']}", "",
             f"Fire ceiling ${float(plan['judge_max_spend_usd']):.4f}; judge_max_tokens {plan['judge_max_tokens']}; "
             f"commit_outputs {str(plan['commit_outputs']).lower()}; nonce {plan['fire']['journal_nonce']!r}.",
             f"Expected ${float(est.get('expected_usd') or 0):.4f}, worst case ${float(est.get('worst_case_usd') or 0):.4f} "
             "(the judge of record's recorded tokens at this judge's price; assumes its token counts are close).", "",
             "| source run | status | planned | judged | null | null share (judge of record) | not applicable | "
             "cost (USD) | expected (USD) |",
             "|---|---|---|---|---|---|---|---|---|"]

    def share(value: Any) -> str:
        return "—" if value is None else f"{100 * float(value):.1f}%"
    root = Path(plan["rejudge_root"])
    for source in plan["sources"]:
        stem = source["run_stem"]
        out_dir = root / plan["judge_slug"] / stem
        manifest_path = out_dir / MANIFEST_NAME
        report_path = out_dir / judge_report_name(stem, plan["fire"]["workflow_run_id"])
        if manifest_path.is_file():
            try:
                m = load_json(manifest_path)
                c = m["counts"]
                status = "truncated" if c["truncated"] else "complete"
                lines.append(f"| {stem} | {status} | {c['planned']} | {c['judged']} | {c['null']} | "
                             f"{share(c['null_share'])} ({share(c['judge_of_record_null_share'])}) | "
                             f"{c['not_applicable']} | {float(m['cost_usd']):.4f} | "
                             f"{float(m['estimate']['expected_usd']):.4f} |")
                continue
            except (OSError, ValueError, KeyError, TypeError) as exc:
                lines.append(f"| {stem} | manifest unreadable ({type(exc).__name__}) | — | — | — | — | — | — | — |")
                continue
        if report_path.is_file():
            try:
                cost = f"{float(load_json(report_path)['cost_usd']):.4f}"
            except (OSError, ValueError, KeyError, TypeError):
                cost = "unavailable"
            lines.append(f"| {stem} | sidecar only (judge failed; outputs not written) | {source['planned']} | — | — | — | "
                         f"— | {cost} | — |")
        else:
            lines.append(f"| {stem} | not started | {source['planned']} | — | — | — | — | — | — |")
    return "\n".join(lines) + "\n"
