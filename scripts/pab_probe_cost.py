"""Cost estimator for a PatientAgentBench trait-sweep probe (integration Layer 2, $0, offline).

The benchmark's own scale is 1,200 scenarios per model; the operational ceiling
here is $2/day (``scripts/fire_trigger.py``). Those two numbers decide whether a
probe is possible at all, so this puts an arithmetic floor under the plan in
``docs/pab_first_probe_costing.md`` rather than a guess, and lets the shape be
re-costed before anything is fired.

The model. A run is ``arms x cases`` conversations. Each conversation costs:

* **the patient agent** one call per turn, re-reading its system prompt and the
  dialogue so far;
* **the assistant agent** ``ASSISTANT_CALLS_PER_TURN`` calls per turn (a tool
  call and an answer), re-reading its system prompt, the patient profile, the
  tool schemas, and the dialogue so far;
* **each jury model** one call per rubric, each re-reading that rubric's prompt
  plus the profile, the scenario, and the whole transcript.

Context is re-sent every call, so input tokens grow quadratically in turns.
Evaluation dominates: the six rubric prompts are ~12k tokens before any
transcript is added, and they are re-read by every jury model on every
conversation.

Sizes come from measuring the shipped artifacts (see PROMPT_TOKENS); prices are
AWS Bedrock on-demand list, the same figures the benchmark's own registry
carries. Both are declared here so a stale number is visible rather than buried.

  python scripts/pab_probe_cost.py                        # the documented plan
  python scripts/pab_probe_cost.py --cases 40 --turns 10  # re-cost a variant
  python scripts/pab_probe_cost.py --json

Exit codes: 0 within the ceiling, 1 over it.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import ceil

# Daily operational ceiling enforced by scripts/fire_trigger.py for engine CI.
# A Bedrock probe does not run through that guard, so the ceiling has to be
# honoured by construction: the plan must fit a day's budget before it is fired.
DAILY_CEILING_USD = 2.0

# Chars per token. tiktoken cannot be used here (its encoding file is fetched
# over the network and this repo's sandbox blocks that), so sizes are measured
# in characters and divided. 3.6 is conservative for English prose mixed with
# XML profiles and JSON tool schemas, which tokenize denser than prose alone.
CHARS_PER_TOKEN = 3.6

# Measured from the benchmark's shipped artifacts on 2026-08-04: prompt
# templates, the 20-scenario sample's patient stories and profile XML, the 15
# sandbox tool schemas, and the six rubric prompts.
PROMPT_TOKENS = {
    "patient_system": 2001,      # template + persona block + story + profile XML
    "assistant_system": 441,     # template only
    "patient_profile": 797,      # profile XML, also re-sent to assistant and jury
    "scenario": 357,             # patient story, re-sent to the jury per rubric
    "tool_schemas": 2985,        # 15 sandbox tools, names + descriptions + schemas
    "rubric_prompts_total": 12175,   # all six rubric prompts
}

N_RUBRICS = 6

# Per-turn dialogue growth and reply lengths, in tokens. Deliberately generous:
# a probe that fits at these numbers fits at the real ones.
TURN_GROWTH = 500            # assistant reply + tool result + patient reply
ASSISTANT_CALLS_PER_TURN = 1.6
ASSISTANT_OUTPUT_PER_CALL = 200
PATIENT_OUTPUT_PER_TURN = 100
RUBRIC_OUTPUT = 150

# AWS Bedrock on-demand list price, USD per 1M tokens (input, output).
PRICES = {
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

# The plan in docs/pab_first_probe_costing.md.
DEFAULT_PLAN = {
    "arms": 4,
    "cases": 13,
    "turns": 3,
    "patient_model": "qwen3-235b-bedrock",
    "assistant_models": ["claude-haiku-4.5-bedrock"],
    "jury_models": ["claude-opus-4.8-bedrock"],
}


def _cost(model: str, tokens_in: float, tokens_out: float) -> float:
    if model not in PRICES:
        raise KeyError(f"no price for {model!r}. Known: {', '.join(sorted(PRICES))}")
    price_in, price_out = PRICES[model]
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
        "patient_in": _accumulated(PROMPT_TOKENS["patient_system"], 1, turns),
        "patient_out": PATIENT_OUTPUT_PER_TURN * turns,
        "assistant_in": _accumulated(assistant_base, ASSISTANT_CALLS_PER_TURN, turns),
        "assistant_out": ASSISTANT_OUTPUT_PER_CALL * ASSISTANT_CALLS_PER_TURN * turns,
        "jury_in_per_model": jury_in,
        "jury_out_per_model": RUBRIC_OUTPUT * N_RUBRICS,
    }


def estimate(arms: int, cases: int, turns: int, patient_model: str,
             assistant_models: list[str], jury_models: list[str]) -> dict:
    """Total spend for a probe, broken down by role."""
    per_conv = conversation_tokens(turns)
    convs_per_assistant = arms * cases
    total_convs = convs_per_assistant * len(assistant_models)

    patient = _cost(patient_model, per_conv["patient_in"] * total_convs,
                    per_conv["patient_out"] * total_convs)
    assistant = sum(
        _cost(model, per_conv["assistant_in"] * convs_per_assistant,
              per_conv["assistant_out"] * convs_per_assistant)
        for model in assistant_models
    )
    jury = sum(
        _cost(model, per_conv["jury_in_per_model"] * total_convs,
              per_conv["jury_out_per_model"] * total_convs)
        for model in jury_models
    )
    total = patient + assistant + jury
    return {
        "arms": arms,
        "cases": cases,
        "turns": turns,
        "patient_model": patient_model,
        "assistant_models": list(assistant_models),
        "jury_models": list(jury_models),
        "conversations_per_assistant": convs_per_assistant,
        "conversations_total": total_convs,
        "usd": {
            "patient": round(patient, 4),
            "assistant": round(assistant, 4),
            "jury": round(jury, 4),
            "total": round(total, 4),
        },
        "usd_per_conversation": round(total / total_convs, 5) if total_convs else 0.0,
        "ceiling_usd": DAILY_CEILING_USD,
        "fits_daily_ceiling": total <= DAILY_CEILING_USD,
        "headroom_usd": round(DAILY_CEILING_USD - total, 4),
        # The ceiling is per day, not a total budget: a probe larger than it is
        # not forbidden, it is scheduled.
        "days_at_ceiling": ceil(total / DAILY_CEILING_USD) if total > 0 else 0,
    }


def max_cases_within_ceiling(arms: int, turns: int, patient_model: str,
                             assistant_models: list[str], jury_models: list[str],
                             ceiling: float = DAILY_CEILING_USD) -> int:
    """Largest per-arm n whose total stays under the ceiling."""
    unit = estimate(arms, 1, turns, patient_model, assistant_models,
                    jury_models)["usd"]["total"]
    return int(ceiling // unit) if unit > 0 else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arms", type=int, default=DEFAULT_PLAN["arms"])
    parser.add_argument("--cases", type=int, default=DEFAULT_PLAN["cases"],
                        help="cases per arm (per-arm n)")
    parser.add_argument("--turns", type=int, default=DEFAULT_PLAN["turns"])
    parser.add_argument("--patient-model", default=DEFAULT_PLAN["patient_model"])
    parser.add_argument("--assistant-model", action="append", dest="assistant_models")
    parser.add_argument("--jury-model", action="append", dest="jury_models")
    parser.add_argument("--no-jury", action="store_true",
                        help="generation only (manipulation check, no scoring)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    result = estimate(
        args.arms, args.cases, args.turns, args.patient_model,
        args.assistant_models or DEFAULT_PLAN["assistant_models"],
        [] if args.no_jury else (args.jury_models or DEFAULT_PLAN["jury_models"]),
    )
    if args.as_json:
        print(json.dumps(result, indent=2))
        return 0 if result["fits_daily_ceiling"] else 1

    usd = result["usd"]
    print(f"{result['arms']} arms x {result['cases']} cases x {result['turns']} turns "
          f"= {result['conversations_total']} conversations")
    for role in ("patient", "assistant", "jury"):
        share = usd[role] / usd["total"] * 100 if usd["total"] else 0
        print(f"  {role:<10} ${usd[role]:>7.3f}  ({share:>4.1f}%)")
    print(f"  {'TOTAL':<10} ${usd['total']:>7.3f}  "
          f"(${result['usd_per_conversation']:.4f}/conversation)")
    verdict = ("within, headroom $%.3f" % result["headroom_usd"]
               if result["fits_daily_ceiling"]
               else "over: %d days at the ceiling" % result["days_at_ceiling"])
    print(f"daily ceiling ${result['ceiling_usd']:.2f}: {verdict}")
    return 0 if result["fits_daily_ceiling"] else 1


if __name__ == "__main__":
    sys.exit(main())
