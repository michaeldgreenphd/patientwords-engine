"""Study Task assembly around the pinned Petri interfaces and the `eval()`
invocation (design memo sections 5 and 13). Python 3.12 only.

One Inspect Sample per (seed, arm, system-prompt variant) with an explicit id;
repeats are epochs; the target is `target_agent(system_required=False)` so the
conversation matches the engine's no-system-prompt elicitation unless the seed
stages one; the auditor is the scripted controller, which calls no model; no
scorer is attached (Petri's judge is not the judge of record). Prices reach
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

from .controller import scripted_auditor
from .seeds import SeedSet, conditions, seed_digest
from .spend import Price, resolve_price

SEED_INSTRUCTION = ("PatientWords scripted protocol: the controller stages the seed's texts verbatim and writes "
                    "nothing of its own (docs/framework/petri_seeds.draft.json).")
PLACEHOLDER_MODEL = "none/none"


def samples_for(seed_set: SeedSet, seeds: list[dict]) -> list[Sample]:
    samples: list[Sample] = []
    for seed in seeds:
        if seed.get("mode") != "scripted":
            # the scripted controller is the only task path; an autonomous seed (LLM auditor) has none yet and must
            # never be executed as if it were scripted (Codex round 2)
            raise ValueError(f"{seed['seed_id']}: mode {seed.get('mode')!r} has no execution path; only scripted seeds run")
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
    """The Task: scripted auditor, no-system-prompt-capable target, no scorer."""
    return Task(
        dataset=MemoryDataset(samples_for(seed_set, seeds), name=name),
        solver=audit_solver(auditor=scripted_auditor(seed_set), target=target_agent(system_required=False, cache=False)),
        scorer=None,
        name=name,
        metadata={"patientwords": {"seed_file": str(seed_set.path), "seed_file_sha256": seed_set.file_sha256,
                                   "seed_ids": [s["seed_id"] for s in seeds]}},
    )


def register_prices(models: list[str], registry: dict | None = None) -> dict[str, Price]:
    """Register a price for every model role and the placeholder so Inspect's
    per-sample cost_limit can start; the source of each price is returned for
    the manifest. Cache rates are filled at the input rate (worst case)."""
    out: dict[str, Price] = {}
    for model in [*models, PLACEHOLDER_MODEL]:
        price = resolve_price(model, registry)
        set_model_info(model, ModelInfo(cost=ModelCost(input=price.input_per_mtok, output=price.output_per_mtok,
                                                       input_cache_write=price.input_per_mtok,
                                                       input_cache_read=price.input_per_mtok)))
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


def run_study(task: Task, *, target: str | Model, seeds: list[dict], epochs: int, log_dir: Path | str,
              token_limit: int | None, cost_limit: float | None, log_model_api: bool = True,
              fail_on_error: bool = False, max_retries: int = 2, registry: dict | None = None,
              started_marker: Path | str | None = None) -> EvalLog:
    """Run the Task against the target under the seed's generation config with
    every layer of the spend discipline that lives on this side: prices
    registered, per-sample token and cost limits, raw calls logged, sample
    errors recorded rather than aborting the run. `started_marker`, when
    given, is created after the model is built and its price registered and
    immediately before the eval, the first point at which a provider call can
    spend."""
    target_model = build_target(target, seeds)
    register_prices([str(target_model)], registry)
    if started_marker is not None:
        # the workflow's always()-gated fallback spend report imputes the full target ceiling when this marker exists
        # and no adapted report does; written before get_model, it booked max_spend for a missing key or an unknown
        # provider that never reached a provider (2026-09-23)
        marker = Path(started_marker)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    [log] = inspect_eval(
        task,
        model_roles={"target": target_model},
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
