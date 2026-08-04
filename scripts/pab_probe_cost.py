"""Cost estimator for a PatientAgentBench trait-sweep probe (integration Layer 2, $0, offline).

The benchmark's own scale is 1,200 scenarios per model; the operational ceiling
here is $2/day (``scripts/fire_trigger.py``), and an OpenRouter probe adds a
second, harder one: the prepaid balance on the key. Those numbers decide whether
a probe is possible at all, so this puts an arithmetic floor under the plan in
``docs/pab_first_probe_costing.md`` rather than a guess, and lets the shape be
re-costed before anything is fired.

The model. A run is ``arms x cases`` conversations. Each conversation costs:

* **the sandbox generator** one call, which builds the offices and doctors the
  tools operate on. Easy to forget -- the runner creates its client internally
  and discards the response -- and it is a per-conversation call, not a
  per-run one;
* **the patient agent** one call per turn, re-reading its system prompt and the
  dialogue so far;
* **the assistant agent** ``ASSISTANT_CALLS_PER_TURN`` calls per turn (a tool
  call and an answer), re-reading its system prompt, the patient profile, the
  tool schemas, and the dialogue so far;
* **each jury model** one call per rubric, each re-reading that rubric's prompt
  plus the profile, the scenario, and the whole transcript.

Context is re-sent every call, so input tokens grow quadratically in turns.
Evaluation dominates: the six rubric prompts are ~12k tokens before a transcript
is added, and they are re-read by every jury model on every conversation.

Prices are never invented. Every model resolves through :func:`resolve_price`
against a named in-repo source, and a model with no verified price returns None
-- the total then renders N/A rather than a number, matching the upstream
registry's own rule (*None → unpriced; cost renders as N/A (never guessed)*).

  python scripts/pab_probe_cost.py                        # the documented plan
  python scripts/pab_probe_cost.py --cases 40 --turns 10  # re-cost a variant
  python scripts/pab_probe_cost.py --preset bedrock       # the superseded plan
  python scripts/pab_probe_cost.py --json

Exit codes: 0 within the ceiling, 1 over it or not fully priced.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import ceil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Daily operational ceiling enforced by scripts/fire_trigger.py for engine CI.
# A probe does not run through that guard, so the ceiling has to be honoured by
# construction: the plan must fit a day's budget before it is fired.
DAILY_CEILING_USD = 2.0

# Chars per token. tiktoken cannot be used here (its encoding file is fetched
# over the network and this repo's sandbox blocks that), so sizes are measured
# in characters and divided. 3.6 is conservative for English prose mixed with
# XML profiles and JSON tool schemas, which tokenize denser than prose alone.
CHARS_PER_TOKEN = 3.6

# Measured from the benchmark's shipped artifacts on 2026-08-04: prompt
# templates, the 20-scenario sample's patient stories and profile XML, the 15
# sandbox tool schemas, the sandbox generation prompt, and the six rubric prompts.
PROMPT_TOKENS = {
    "patient_system": 2001,      # template + persona block + story + profile XML
    "assistant_system": 441,     # template only
    "patient_profile": 797,      # profile XML, also re-sent to assistant and jury
    "scenario": 357,             # patient story, re-sent to the jury per rubric
    "tool_schemas": 2985,        # 15 sandbox tools, names + descriptions + schemas
    "rubric_prompts_total": 12175,   # all six rubric prompts
    "sandbox_prompt": 483,       # sandbox generation prompt
}

N_RUBRICS = 6

# Per-turn dialogue growth and reply lengths, in tokens. Deliberately generous:
# a probe that fits at these numbers fits at the real ones.
TURN_GROWTH = 500            # assistant reply + tool result + patient reply
ASSISTANT_CALLS_PER_TURN = 1.6
ASSISTANT_OUTPUT_PER_CALL = 200
PATIENT_OUTPUT_PER_TURN = 100
RUBRIC_OUTPUT = 150
SANDBOX_OUTPUT = 700         # JSON for the generated offices and doctors

# ---------------------------------------------------------------------------
# Prices, USD per 1M tokens (input, output), each from a named in-repo source.
# ---------------------------------------------------------------------------

# AWS Bedrock on-demand list, mirroring the benchmark's own registry. Retained
# so the OpenRouter re-costing can be diffed against the superseded plan.
BEDROCK_PRICES = {
    "claude-opus-4.8-bedrock": (5.00, 25.00),
    "claude-sonnet-5-bedrock": (2.00, 10.00),
    "claude-haiku-4.5-bedrock": (1.00, 5.00),
    "nova-lite-bedrock": (0.30, 2.50),
    "deepseek-v3-bedrock": (0.58, 1.68),
    "llama3-3-70b-bedrock": (0.72, 0.72),
    "qwen3-235b-bedrock": (0.22, 0.88),
    "qwen3-32b-bedrock": (0.15, 0.60),
    "gpt-oss-120b-bedrock": (0.15, 0.60),
}
BEDROCK_SOURCE = "AWS Bedrock on-demand list price (PatientAgentBench model_registry.py)"

# Direct Anthropic API, read from this repo's own table so the jury leg is
# priced from a source the study already maintains.
ANTHROPIC_SOURCE = "medlang_circuits/evaluate_models.py :: PRICING"

# OpenRouter, read from this repo's reviewed provider registry. Its header
# records the convention: "pricing = [input, output] USD per Mtok, used only by
# the local spend-ceiling math (worst-case, cache-miss rates); the true bill is
# the provider's" -- list price plus roughly a 5% aggregator margin. Every
# estimate built on these is therefore an upper bound.
PROVIDERS_PATH = REPO_ROOT / "data" / "advice_providers.json"
OPENROUTER_SOURCE = "data/advice_providers.json (reviewed provider registry)"
OPENROUTER_PREFIX = "openrouter:"


def _anthropic_prices() -> dict:
    """Direct-API Anthropic prices from this repo's table.

    Invoked as ``python scripts/pab_probe_cost.py`` the interpreter puts
    ``scripts/`` on the path, not the repo root, so the package import needs the
    same retry seal_check.py uses. Getting this wrong is quiet: the jury leg
    would render N/A on a plan that is in fact fully priced.
    """
    try:
        from medlang_circuits.evaluate_models import PRICING
    except ImportError:
        sys.path.insert(0, str(REPO_ROOT))
        try:
            from medlang_circuits.evaluate_models import PRICING
        except ImportError:  # pragma: no cover - only outside the dev install
            return {}
    return dict(PRICING)


def openrouter_prices(path: Path = PROVIDERS_PATH) -> dict:
    """``openrouter:vendor/model -> (input, output)`` from the provider registry.

    Reads every provider whose base_url is OpenRouter, taking its
    ``consumer_default`` price from ``default_pricing`` and any per-model
    override from ``pricing``. Missing or unreadable file yields an empty table,
    which makes those models unpriced rather than guessed.
    """
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    prices: dict = {}
    for name, entry in registry.items():
        if name.startswith("_") or not isinstance(entry, dict):
            continue
        if OPENROUTER_PREFIX.rstrip(":") not in str(entry.get("base_url", "")):
            continue
        default_slug = entry.get("consumer_default")
        default_price = entry.get("default_pricing")
        if default_slug and default_price:
            prices[OPENROUTER_PREFIX + default_slug] = tuple(default_price)
        for slug, price in (entry.get("pricing") or {}).items():
            prices[OPENROUTER_PREFIX + slug] = tuple(price)
    return prices


def resolve_price(model: str) -> tuple:
    """``((input, output), source)`` for a model, or ``(None, reason)``.

    Never falls back to a default rate. An unknown model is unpriced, and the
    caller renders N/A.
    """
    if model.startswith(OPENROUTER_PREFIX):
        table = openrouter_prices()
        if model in table:
            return table[model], OPENROUTER_SOURCE
        return None, f"no verified OpenRouter price for {model!r}"
    if model in BEDROCK_PRICES:
        return BEDROCK_PRICES[model], BEDROCK_SOURCE
    anthropic = _anthropic_prices()
    if model in anthropic:
        return anthropic[model], ANTHROPIC_SOURCE
    return None, f"no verified price for {model!r}"


def _cost(model: str, tokens_in: float, tokens_out: float):
    """USD for a leg, or None when the model is unpriced."""
    price, _source = resolve_price(model)
    if price is None:
        return None
    price_in, price_out = price
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def _accumulated(base: float, calls_per_turn: float, turns: int) -> float:
    """Input tokens when every call re-sends the context accumulated so far."""
    return sum(calls_per_turn * (base + TURN_GROWTH * t) for t in range(turns))


def conversation_tokens(turns: int) -> dict:
    """Per-conversation token counts for one conversation, by role."""
    transcript = TURN_GROWTH * turns
    assistant_base = (
        PROMPT_TOKENS["assistant_system"]
        + PROMPT_TOKENS["patient_profile"]
        + PROMPT_TOKENS["tool_schemas"]
    )
    jury_in = PROMPT_TOKENS["rubric_prompts_total"] + N_RUBRICS * (
        PROMPT_TOKENS["patient_profile"] + PROMPT_TOKENS["scenario"] + transcript
    )
    return {
        "sandbox_in": PROMPT_TOKENS["sandbox_prompt"],
        "sandbox_out": SANDBOX_OUTPUT,
        "patient_in": _accumulated(PROMPT_TOKENS["patient_system"], 1, turns),
        "patient_out": PATIENT_OUTPUT_PER_TURN * turns,
        "assistant_in": _accumulated(assistant_base, ASSISTANT_CALLS_PER_TURN, turns),
        "assistant_out": ASSISTANT_OUTPUT_PER_CALL * ASSISTANT_CALLS_PER_TURN * turns,
        "jury_in_per_model": jury_in,
        "jury_out_per_model": RUBRIC_OUTPUT * N_RUBRICS,
    }


# The plan in docs/pab_first_probe_costing.md, and the Bedrock shape it replaced.
PRESETS = {
    "openrouter": {
        "arms": 4,
        "cases": 13,
        "turns": 3,
        "sandbox_model": "openrouter:openai/gpt-5.4-mini",
        "patient_model": "openrouter:x-ai/grok-4.3",
        "assistant_models": ["openrouter:openai/gpt-5.4-mini"],
        "jury_models": ["claude-opus-4-8"],
    },
    "bedrock": {
        "arms": 4,
        "cases": 13,
        "turns": 3,
        "sandbox_model": "claude-haiku-4.5-bedrock",
        "patient_model": "qwen3-235b-bedrock",
        "assistant_models": ["claude-haiku-4.5-bedrock"],
        "jury_models": ["claude-opus-4.8-bedrock"],
    },
}
DEFAULT_PLAN = PRESETS["openrouter"]


def estimate(arms: int, cases: int, turns: int, patient_model: str,
             assistant_models: list, jury_models: list,
             sandbox_model: str | None = None) -> dict:
    """Total spend for a probe, broken down by role.

    ``usd.total`` is None whenever any role is unpriced; ``usd.priced_subtotal``
    still reports what the priced roles come to, so a partly-priced plan is
    informative without being passed off as complete.
    """
    per_conv = conversation_tokens(turns)
    convs_per_assistant = arms * cases
    total_convs = convs_per_assistant * len(assistant_models)
    sandbox_model = sandbox_model or assistant_models[0]

    legs = {
        "sandbox": _cost(sandbox_model, per_conv["sandbox_in"] * total_convs,
                         per_conv["sandbox_out"] * total_convs),
        "patient": _cost(patient_model, per_conv["patient_in"] * total_convs,
                         per_conv["patient_out"] * total_convs),
    }

    assistant_costs = [
        _cost(model, per_conv["assistant_in"] * convs_per_assistant,
              per_conv["assistant_out"] * convs_per_assistant)
        for model in assistant_models
    ]
    legs["assistant"] = (
        None if any(c is None for c in assistant_costs) else sum(assistant_costs)
    )

    jury_costs = [
        _cost(model, per_conv["jury_in_per_model"] * total_convs,
              per_conv["jury_out_per_model"] * total_convs)
        for model in jury_models
    ]
    legs["jury"] = (
        0.0 if not jury_models
        else None if any(c is None for c in jury_costs) else sum(jury_costs)
    )

    unpriced = sorted(role for role, cost in legs.items() if cost is None)
    priced_subtotal = round(sum(c for c in legs.values() if c is not None), 4)
    total = None if unpriced else priced_subtotal

    return {
        "arms": arms,
        "cases": cases,
        "turns": turns,
        "sandbox_model": sandbox_model,
        "patient_model": patient_model,
        "assistant_models": list(assistant_models),
        "jury_models": list(jury_models),
        "conversations_per_assistant": convs_per_assistant,
        "conversations_total": total_convs,
        "usd": {
            **{role: (None if cost is None else round(cost, 4))
               for role, cost in legs.items()},
            "priced_subtotal": priced_subtotal,
            "total": total,
        },
        "unpriced_roles": unpriced,
        "price_sources": {
            model: resolve_price(model)[1]
            for model in [sandbox_model, patient_model, *assistant_models, *jury_models]
        },
        "usd_per_conversation": (
            None if total is None or not total_convs else round(total / total_convs, 5)
        ),
        "ceiling_usd": DAILY_CEILING_USD,
        "fits_daily_ceiling": total is not None and total <= DAILY_CEILING_USD,
        "headroom_usd": None if total is None else round(DAILY_CEILING_USD - total, 4),
        # The ceiling is per day, not a total budget: a probe larger than it is
        # not forbidden, it is scheduled.
        "days_at_ceiling": (
            None if total is None else ceil(total / DAILY_CEILING_USD) if total > 0 else 0
        ),
    }


def max_cases_within_ceiling(arms: int, turns: int, patient_model: str,
                             assistant_models: list, jury_models: list,
                             sandbox_model: str | None = None,
                             ceiling: float = DAILY_CEILING_USD) -> int:
    """Largest per-arm n whose total stays under the ceiling (0 if unpriced)."""
    unit = estimate(arms, 1, turns, patient_model, assistant_models, jury_models,
                    sandbox_model)["usd"]["total"]
    if unit is None or unit <= 0:
        return 0
    return int(ceiling // unit)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", choices=sorted(PRESETS), default="openrouter",
                        help="model set to cost (default: openrouter)")
    parser.add_argument("--arms", type=int)
    parser.add_argument("--cases", type=int, help="cases per arm (per-arm n)")
    parser.add_argument("--turns", type=int)
    parser.add_argument("--sandbox-model")
    parser.add_argument("--patient-model")
    parser.add_argument("--assistant-model", action="append", dest="assistant_models")
    parser.add_argument("--jury-model", action="append", dest="jury_models")
    parser.add_argument("--no-jury", action="store_true",
                        help="generation only (manipulation check, no scoring)")
    parser.add_argument("--balance", type=float,
                        help="prepaid balance to check the total against")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    plan = PRESETS[args.preset]
    result = estimate(
        args.arms or plan["arms"],
        args.cases or plan["cases"],
        args.turns or plan["turns"],
        args.patient_model or plan["patient_model"],
        args.assistant_models or plan["assistant_models"],
        [] if args.no_jury else (args.jury_models or plan["jury_models"]),
        args.sandbox_model or plan["sandbox_model"],
    )
    if args.balance is not None:
        total = result["usd"]["total"]
        result["prepaid_balance_usd"] = args.balance
        result["fits_prepaid_balance"] = total is not None and total <= args.balance

    if args.as_json:
        print(json.dumps(result, indent=2))
        return 0 if result["fits_daily_ceiling"] else 1

    usd = result["usd"]
    print(f"{result['arms']} arms x {result['cases']} cases x {result['turns']} turns "
          f"= {result['conversations_total']} conversations  [{args.preset}]")
    for role in ("sandbox", "patient", "assistant", "jury"):
        value = usd[role]
        if value is None:
            print(f"  {role:<10}      N/A  (unpriced)")
            continue
        share = value / usd["priced_subtotal"] * 100 if usd["priced_subtotal"] else 0
        print(f"  {role:<10} ${value:>7.3f}  ({share:>4.1f}%)")
    if result["unpriced_roles"]:
        print(f"  {'TOTAL':<10}      N/A  (unpriced: "
              f"{', '.join(result['unpriced_roles'])}; priced roles come to "
              f"${usd['priced_subtotal']:.3f})")
        print("no total is reported for an unpriced plan; a price is never guessed")
        return 1
    print(f"  {'TOTAL':<10} ${usd['total']:>7.3f}  "
          f"(${result['usd_per_conversation']:.4f}/conversation)")
    verdict = ("within, headroom $%.3f" % result["headroom_usd"]
               if result["fits_daily_ceiling"]
               else "over: %d days at the ceiling" % result["days_at_ceiling"])
    print(f"daily ceiling ${result['ceiling_usd']:.2f}: {verdict}")
    if "prepaid_balance_usd" in result:
        fits = "within" if result["fits_prepaid_balance"] else "OVER"
        print(f"prepaid balance ${result['prepaid_balance_usd']:.2f}: {fits}")
    return 0 if result["fits_daily_ceiling"] else 1


if __name__ == "__main__":
    sys.exit(main())
