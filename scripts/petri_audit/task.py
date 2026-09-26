"""Study Task assembly around the pinned Petri interfaces and the `eval()`
invocation (design memo sections 5 and 13). Python 3.12 only.

One Inspect Sample per (seed, arm, system-prompt variant) with an explicit id;
repeats are epochs; the target is `target_agent(system_required=False)` so the
conversation matches the engine's no-system-prompt elicitation unless the seed
stages one; the auditor is the scripted controller, which calls no model, or,
for a run of autonomous seeds, the adaptive controller, which calls the model
bound to the `auditor` role (docs/petri_adaptive_design.md); a run is one mode or
the other, never both; no scorer is attached (Petri's judge is not the judge of
record). Prices reach
Inspect through `set_model_info` so `cost_limit` can start, including the
`none/none` placeholder that role-only invocation resolves `task.model` to.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.log import EvalLog
from inspect_ai.model import GenerateConfig, Model, ModelCost, ModelInfo, get_model, set_model_info
from inspect_petri import audit_solver, target_agent

from .adaptive import adaptive_prompt_digest, load_adaptive_prompt
from .controller import AUDITOR_ROLE, adaptive_auditor, scripted_auditor
from .seeds import SeedSet, conditions, seed_digest
from .spend import Price, resolve_price

SEED_INSTRUCTION = ("PatientWords scripted protocol: the controller stages the seed's texts verbatim and writes "
                    "nothing of its own (docs/framework/petri_seeds.draft.json).")
PLACEHOLDER_MODEL = "none/none"


def run_mode(seeds: list[dict]) -> str:
    """The one execution mode of a run: every seed scripted, or every seed autonomous. A mixed selection is refused:
    the two controllers are different Tasks, and a manifest records one execution mode."""
    modes = {s.get("mode") for s in seeds}
    if len(modes) != 1 or not modes <= {"scripted", "autonomous"}:
        raise ValueError(f"a run executes one mode, scripted or autonomous; the selection holds {sorted(map(str, modes))}")
    return modes.pop()


def samples_for(seed_set: SeedSet, seeds: list[dict], *, autonomous: bool = False) -> list[Sample]:
    samples: list[Sample] = []
    for seed in seeds:
        if seed.get("mode") != ("autonomous" if autonomous else "scripted"):
            # each controller executes its own mode only: a scripted seed handed to the adaptive controller would be
            # rewritten by the auditor, an autonomous one handed to the scripted controller would run as a script
            # (Codex round 2)
            raise ValueError(f"{seed['seed_id']}: mode {seed.get('mode')!r} is not this run's "
                             f"{'autonomous' if autonomous else 'scripted'} mode")
        for cond in conditions(seed):
            metadata: dict[str, Any] = {
                "seed_id": seed["seed_id"], "seed_sha256": seed_digest(seed), "seed_file": str(seed_set.path),
                "condition_id": cond["condition_id"], "arm_id": cond["arm_id"], "variant_id": cond["variant_id"],
                "user_is": cond["user_is"], "register_exposure": seed["protocol"]["register_exposure"],
                "pilot_wave": seed["pilot_wave"],
            }
            if seed.get("tools"):
                # Petri reads `metadata["tools"]` as the target's fixed tool definitions (ToolInfo shape).
                metadata["tools"] = [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
                                     for t in seed["tools"]["definitions"]]
            samples.append(Sample(id=f"{seed['seed_id']}::{cond['condition_id']}", input=SEED_INSTRUCTION,
                                  metadata=metadata))
    return samples


def study_task(seed_set: SeedSet, seeds: list[dict], *, name: str = "patientwords-petri-audit") -> Task:
    """The Task: the scripted or the adaptive controller (run_mode), no-system-prompt-capable target, no scorer."""
    autonomous = run_mode(seeds) == "autonomous"
    prompt = load_adaptive_prompt() if autonomous else None
    auditor = adaptive_auditor(seed_set, prompt) if autonomous else scripted_auditor(seed_set)
    meta: dict[str, Any] = {"seed_file": str(seed_set.path), "seed_file_sha256": seed_set.file_sha256,
                            "seed_ids": [s["seed_id"] for s in seeds]}
    if prompt is not None:
        # the instruction file of record, as the run read it: the adapter binds the manifest to this digest and refuses
        # a prompt file in hand that differs (Codex review of PR #50: a readapt would otherwise seal the checkout's)
        meta["auditor_prompt_sha256"] = adaptive_prompt_digest(prompt)
    return Task(
        dataset=MemoryDataset(samples_for(seed_set, seeds, autonomous=autonomous), name=name),
        solver=audit_solver(auditor=auditor, target=target_agent(system_required=False, cache=False)),
        scorer=None,
        name=name,
        metadata={"patientwords": meta},
    )


def register_prices(models: list[str], registry: dict | None = None) -> dict[str, Price]:
    """Register a price for every model role and the placeholder so Inspect's
    per-sample cost_limit can start; the source of each price is returned for
    the manifest. Cache rates are the bounded ones the sidecar reprices with
    (spend.CACHE_*_MULTIPLIER): the input rate for reads and twice it for
    writes, since a write at the input rate understated Anthropic's 1.25x and
    2x cache-write prices (2026-09-23)."""
    out: dict[str, Price] = {}
    for model in [*models, PLACEHOLDER_MODEL]:
        price = resolve_price(model, registry)
        set_model_info(model, ModelInfo(cost=ModelCost(input=price.input_per_mtok, output=price.output_per_mtok,
                                                       input_cache_write=price.cache_write_per_mtok,
                                                       input_cache_read=price.cache_read_per_mtok)))
        out[model] = price
    return out


def generation_config(seed: dict) -> GenerateConfig:
    gen = seed["generation"]
    kwargs: dict[str, Any] = {"max_tokens": int(gen["max_tokens"])}
    if gen.get("temperature") is not None:
        kwargs["temperature"] = float(gen["temperature"])
    if gen.get("seed_requested") is not None:
        kwargs["seed"] = int(gen["seed_requested"])
    return GenerateConfig(**kwargs)


def build_target(target: str | Model, seeds: list[dict]) -> Model:
    """The target Model under the seeds' one shared generation block, built
    before anything is marked started. `get_model` raises here, before any
    provider call, for an unknown provider (ValueError) and for an API key
    variable that is unset or empty (PrerequisiteError: an Actions secret that
    does not exist arrives as an empty string). A model name the provider
    does not serve is NOT caught here: construction accepts any name, and the
    first call fails. A Model passed in is returned as given."""
    configs = {seed["seed_id"]: seed["generation"] for seed in seeds}
    if len({(c["temperature"], c["max_tokens"], c["seed_requested"]) for c in configs.values()}) != 1:
        raise ValueError("every seed in one run must share the same generation block; split the run")
    return get_model(target, config=generation_config(seeds[0])) if isinstance(target, str) else target


def build_auditor(auditor: str | Model) -> Model:
    """The auditor Model, built before anything is marked started, as the target is: construction raises for an
    unknown provider or an empty key variable before any provider call. It carries the prompt file's sampling
    settings as its role config, so the log (and models.auditor.config in the manifest) records what every call was
    sent; the controller passes the same settings on each call (review of PR #50: the manifest recorded {})."""
    if not isinstance(auditor, str):
        return auditor
    gen = load_adaptive_prompt()["generation"]
    return get_model(auditor, config=GenerateConfig(max_tokens=int(gen["max_tokens"]),
                                                    temperature=float(gen["temperature"])))


def run_study(task: Task, *, target: str | Model, seeds: list[dict], epochs: int, log_dir: Path | str,
              token_limit: int | None, cost_limit: float | None, log_model_api: bool = True,
              fail_on_error: bool = False, max_retries: int = 2, registry: dict | None = None,
              started_marker: Path | str | None = None, auditor: str | Model | None = None) -> EvalLog:
    """Run the Task against the target under the seed's generation config with
    every layer of the spend discipline that lives on this side: prices
    registered, per-sample token and cost limits, raw calls logged, sample
    errors recorded rather than aborting the run. `started_marker`, when
    given, is created after the model is built and its price registered and
    immediately before the eval, the first point at which a provider call can
    spend."""
    target_model = build_target(target, seeds)
    autonomous = run_mode(seeds) == "autonomous"
    if autonomous != (auditor is not None):
        raise ValueError("an autonomous run needs an auditor model and a scripted run takes none")
    roles: dict[str, Model] = {"target": target_model}
    if auditor is not None:
        # Inspect's per-sample token and cost limits count every role's calls, the auditor's included
        roles[AUDITOR_ROLE] = build_auditor(auditor)
    register_prices([str(m) for m in roles.values()], registry)
    if started_marker is not None:
        # the workflow's always()-gated fallback spend report imputes the full target ceiling when this marker exists
        # and no adapted report does; written before get_model, it booked max_spend for a missing key or an unknown
        # provider that never reached a provider (2026-09-23)
        marker = Path(started_marker)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    [log] = inspect_eval(
        task,
        model_roles=roles,
        epochs=epochs,
        log_dir=str(log_dir),
        log_model_api=log_model_api,
        token_limit=token_limit,
        cost_limit=cost_limit,
        fail_on_error=fail_on_error,
        max_retries=max_retries,
        display="none",
    )
    return log
