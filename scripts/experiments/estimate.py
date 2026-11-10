"""Grid-level resource estimates for case families x models x replicates.

Every number this module returns is arithmetic on its inputs. None is a measurement. The planner
(``scripts/experiments/planner.py``) already estimates activation bytes and an ICA fitting workspace per task;
this module calls those two functions and adds the three formulas the planner lacks:

* CPU-logits runner time from a seconds-per-pair rate the caller supplies, with a stated allowance for
  failed attempts;
* logits storage, full vocabulary or top-k;
* weight bytes from a parameter count.

The only rates the repository records in machine-readable form are ``backfill_planner.SECONDS_PER_PAIR``:
the slowest rate six models showed on the legacy first-token endpoint of the logits-eval lane, model load
included. ``recorded_slowest_rates`` returns them with their source text. Their sample size is not recorded, so
this module does not write a ``patientwords.experiment-rates/1`` file from them: that schema requires
``n_samples``, and inventing one would be a fabricated provenance field.

No model is loaded and no socket is opened. Run ``python -m scripts.experiments.estimate --help``.
"""
from __future__ import annotations

import argparse
import json
import math
from typing import Any, Mapping, Sequence

from scripts import backfill_planner
from scripts.experiments.common import DTYPE_BYTES, Refusal, integer, require
from scripts.experiments.planner import estimate_activation_bytes, estimate_fit_bytes

TIME_FORMULA = ("runner_seconds = ceil(pair_equivalents * (1 + failed_attempt_fraction)) * seconds_per_pair, "
                "summed over models; pair_equivalents = case_families * replicates * prompts_per_family / 2")
LEG_FORMULA = "legs = ceil(attempted_pairs / max(1, floor(leg_budget_seconds / seconds_per_pair)))"
LOGITS_FORMULA = ("full vocabulary: positions * vocab_size * bytes_per_value(dtype); "
                  "top-k: positions * top_k * (4 + bytes_per_value(dtype)), a 4-byte token id beside each value")
WEIGHTS_FORMULA = "weight_bytes = parameters * bytes_per_value(dtype)"
INDEX_BYTES = 4


def _number(value: Any, lower: float = 0.0) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= lower


def recorded_slowest_rates() -> dict[str, Any]:
    """The seconds-per-pair constants the backfill planner sizes legs with, and where they come from."""
    return {
        "seconds_per_pair": dict(backfill_planner.SECONDS_PER_PAIR),
        "source": "scripts/backfill_planner.py SECONDS_PER_PAIR: " + backfill_planner.RATES_SOURCE,
        "leg_budget_seconds": backfill_planner.HALF_TIMEOUT_S,
        "n_samples": None,
        "label": "measured (slowest successful run per model; sample size not recorded)",
    }


def attempted_units(units: float, failed_attempt_fraction: float) -> int:
    """Units of work to budget for when a stated fraction of attempts fails and is run again: ceil(u * (1 + f))."""
    require(_number(units) and _number(failed_attempt_fraction), "invalid_estimate_input",
            "units and failed_attempt_fraction must be finite and non-negative")
    return math.ceil(round(units * (1 + failed_attempt_fraction), 9))


def estimate_cpu_logits_seconds(case_families: int, rates: Mapping[str, float], *, replicates: int = 1,
                                prompts_per_family: int = 2, failed_attempt_fraction: float = 0.0,
                                leg_budget_seconds: int | None = None) -> dict[str, Any]:
    """Runner seconds for the legacy first-token endpoint over a grid, per model and in total.

    ``rates`` maps a model id to seconds per pair. A pair is two prompts, which is the unit the recorded rates
    use. A family with three variants is 1.5 pair-equivalents: an assumption that time scales with the number of
    prompts. The recorded rates include model load, so short legs cost more per pair than this predicts and the
    total is not a wall-clock time: queueing, install and matrix parallelism are outside the formula.
    """
    require(integer(case_families) and integer(replicates, 1) and integer(prompts_per_family, 1),
            "invalid_estimate_input", "case_families, replicates and prompts_per_family must be integers; "
            "replicates and prompts_per_family at least 1")
    require(isinstance(rates, Mapping) and len(rates) > 0 and all(_number(r) and r > 0 for r in rates.values()),
            "invalid_estimate_input", "rates must map at least one model to a positive seconds-per-pair value")
    require(leg_budget_seconds is None or integer(leg_budget_seconds, 1), "invalid_estimate_input",
            "leg_budget_seconds must be a positive integer or None")
    pair_equivalents = case_families * replicates * prompts_per_family / 2
    attempted = attempted_units(pair_equivalents, failed_attempt_fraction)
    per_model: dict[str, Any] = {}
    for model in sorted(rates):
        entry: dict[str, Any] = {"seconds_per_pair": rates[model], "runner_seconds": attempted * rates[model]}
        if leg_budget_seconds is not None:
            pairs_per_leg = max(1, math.floor(leg_budget_seconds / rates[model]))
            entry["pairs_per_leg"] = pairs_per_leg
            entry["legs"] = math.ceil(attempted / pairs_per_leg)
        per_model[model] = entry
    return {
        "pair_equivalents": pair_equivalents,
        "attempted_pair_equivalents": attempted,
        "per_model": per_model,
        "runner_seconds": sum(entry["runner_seconds"] for entry in per_model.values()),
        "formula": TIME_FORMULA if leg_budget_seconds is None else TIME_FORMULA + "; " + LEG_FORMULA,
        "assumptions": [
            "time scales with the number of prompts, so a family of v variants is v / 2 pairs",
            f"failed_attempt_fraction = {failed_attempt_fraction} is a stated allowance, not a measured rate",
            "the rates are for the legacy first-token endpoint and include model load",
            "runner seconds are not wall-clock time: queueing, install and parallelism are not modelled",
        ],
        "measured": False,
    }


def estimate_logits_bytes(positions: int, vocab_size: int, dtype: str, *, top_k: int | None = None) -> int:
    """Bytes of stored next-token logits, uncompressed: the whole vocabulary per position, or top-k with ids."""
    require(integer(positions) and integer(vocab_size, 1), "invalid_estimate_input",
            "positions must be a non-negative integer and vocab_size a positive integer")
    require(dtype in DTYPE_BYTES, "unknown_dtype", f"dtype must be one of {sorted(DTYPE_BYTES)}; got {dtype!r}")
    if top_k is None:
        return positions * vocab_size * DTYPE_BYTES[dtype]
    require(integer(top_k, 1) and top_k <= vocab_size, "invalid_estimate_input",
            "top_k must be an integer between 1 and vocab_size")
    return positions * top_k * (INDEX_BYTES + DTYPE_BYTES[dtype])


def estimate_weight_bytes(parameters: int, dtype: str) -> int:
    """Bytes of the weights held in memory at one dtype, before headers, tokenizer files and transient copies."""
    require(integer(parameters, 1), "invalid_estimate_input", "parameters must be a positive integer")
    require(dtype in DTYPE_BYTES, "unknown_dtype", f"dtype must be one of {sorted(DTYPE_BYTES)}; got {dtype!r}")
    return parameters * DTYPE_BYTES[dtype]


def estimate_grid_storage(case_families: int, *, replicates: int, prompts_per_family: int,
                          tokens_per_prompt: int, layers: int, hidden_size: int, dtype: str,
                          vocab_size: int | None = None, top_k: int | None = None) -> dict[str, Any]:
    """Activation and logits bytes for one model over a grid, all positions and last position only.

    ``vocab_size`` None leaves the logits fields None: a width or vocabulary that is not recorded is reported as
    missing, never as zero.
    """
    require(integer(case_families) and integer(replicates, 1) and integer(prompts_per_family, 1)
            and integer(tokens_per_prompt, 1), "invalid_estimate_input",
            "case_families must be a non-negative integer; the other counts positive integers")
    prompts = case_families * replicates * prompts_per_family
    tokens = prompts * tokens_per_prompt
    out: dict[str, Any] = {
        "prompts": prompts, "tokens": tokens,
        "activation_bytes_all_positions": estimate_activation_bytes(tokens, layers, hidden_size, dtype),
        "activation_bytes_last_position": estimate_activation_bytes(prompts, layers, hidden_size, dtype),
        "logits_bytes_last_position_full_vocab": None, "logits_bytes_last_position_top_k": None,
        "assumptions": [f"every prompt has {tokens_per_prompt} tokens: an upper bound the caller states, not a "
                        "measured length", "uncompressed arrays, no container overhead"],
        "measured": False,
    }
    if vocab_size is not None:
        out["logits_bytes_last_position_full_vocab"] = estimate_logits_bytes(prompts, vocab_size, dtype)
        if top_k is not None:
            out["logits_bytes_last_position_top_k"] = estimate_logits_bytes(prompts, vocab_size, dtype, top_k=top_k)
    return out


def _rates_from_args(pairs: Sequence[str]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for item in pairs:
        model, sep, value = item.partition("=")
        require(bool(sep) and bool(model), "invalid_estimate_input", f"--rate takes MODEL=SECONDS; got {item!r}")
        try:
            rates[model] = float(value)
        except ValueError as exc:
            raise Refusal("invalid_estimate_input", f"--rate {item!r}: {value!r} is not a number") from exc
    return rates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grid estimates from stated formulas. Nothing printed is a "
                                                 "measurement.")
    parser.add_argument("--families", type=int, required=True, help="case families in the grid")
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--prompts-per-family", type=int, default=2, help="variants per family (2 = one pair)")
    parser.add_argument("--failed-attempt-fraction", type=float, default=0.0,
                        help="allowance for failed attempts that are run again (an assumption)")
    parser.add_argument("--rate", action="append", default=[], metavar="MODEL=SECONDS",
                        help="seconds per pair for one model; repeatable. Default: the recorded slowest rates")
    parser.add_argument("--tokens-per-prompt", type=int, help="with --layers and --hidden-size: storage estimate")
    parser.add_argument("--layers", type=int)
    parser.add_argument("--hidden-size", type=int)
    parser.add_argument("--dtype", default="float32", choices=sorted(DTYPE_BYTES))
    parser.add_argument("--vocab-size", type=int)
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--fit-samples", type=int, help="with --hidden-size: ICA or whitening workspace bytes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        recorded = recorded_slowest_rates()
        rates = _rates_from_args(args.rate) or recorded["seconds_per_pair"]
        out: dict[str, Any] = {
            "rates_source": "command line (--rate)" if args.rate else recorded["source"],
            "time": estimate_cpu_logits_seconds(
                args.families, rates, replicates=args.replicates, prompts_per_family=args.prompts_per_family,
                failed_attempt_fraction=args.failed_attempt_fraction,
                leg_budget_seconds=recorded["leg_budget_seconds"]),
        }
        if args.tokens_per_prompt is not None and args.layers is not None and args.hidden_size is not None:
            out["storage"] = estimate_grid_storage(
                args.families, replicates=args.replicates, prompts_per_family=args.prompts_per_family,
                tokens_per_prompt=args.tokens_per_prompt, layers=args.layers, hidden_size=args.hidden_size,
                dtype=args.dtype, vocab_size=args.vocab_size, top_k=args.top_k)
        if args.fit_samples is not None and args.hidden_size is not None:
            out["fit_bytes"] = estimate_fit_bytes(args.fit_samples, args.hidden_size, args.dtype)
    except Refusal as refusal:
        print(json.dumps({"status": "refused", "code": refusal.code, "detail": str(refusal)}, indent=2))
        return 2
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
