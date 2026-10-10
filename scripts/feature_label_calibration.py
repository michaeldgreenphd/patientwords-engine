"""Compare two traced models' feature labels before their clinical_mass is compared.

clinical_mass is the share of feature attribution mass on features the keyword
rule tags clinical. The rule reads each feature's Neuronpedia autointerp
description, so the number depends on the labels as much as on the model: a
source set whose labels are shorter, sparser or written by another explainer
tags fewer features clinical for reasons unrelated to the model. Before a second
model's clinical_mass is published beside gemma-2-2b's (an owner decision; see
scripts/feature_models.py), this script measures, from two trace directories
over the same pairs:

  per model   - feature nodes and unique features (layer, index) in the tagged
                graphs; the share with a non-empty description; the share tagged
                clinical by the rule as applied at trace time (node["medlang"]
                ["category"]); how each category was reached (keyword, llm,
                default, undecodable); the share of descriptions the fetcher
                joined from two or more explanations (it joins with " | ");
                mean description length in words; and the per-pair clinical_mass
                distribution per phrasing, from the batch summaries.
  per pair    - clinical_mass side by side on the pairs both directories traced
                with identical prompts (joined on the global 1-based ``index``).
                Pairs traced by one side only, and pairs whose prompts differ,
                are listed and excluded, never merged.

Inputs. A trace directory holds ``batch_summary*.json`` (committed) and
``pair_NN_<role>.tagged.json`` (the tagged graphs: CI keeps these in the run's
workflow artifact, ``circuit-trace-<model>-<mode>-<run>-offset<k>``, not in git).
The tagged graphs are the only place a trace stores feature descriptions, so a
directory without them is refused (MissingTaggedGraphsError) rather than
reported from the summaries alone (download the artifact into the directory
first). So is a directory whose tagged graphs are not exactly the (index, role)
pairs its summaries report as traced (TaggedGraphSetMismatchError: a chunked run
has one artifact per offset, and every one is needed), and a tagged graph whose
``metadata.scan`` is not the summaries' graph_model (GraphModelMismatchError),
or whose ``metadata.medlang_summary.feature_source_set`` (the set its labels
were fetched from, recorded by the tagger since 2026-10-09) is missing or is not
the summaries' ``source_set`` (TaggingSourceSetMismatchError: for example an
untagged NullFetcher artifact of the same pairs). Graphs tagged before
2026-10-09 record no source set, so both models must be traced after that date.
Label coverage and clinical_mass are thus always measured over the same pairs.
No network: nothing is fetched, and the fetcher's on-disk cache is not read (it
lives on the CI runner and is not uploaded). This is a 2panel tool: the traced
sides are read from each result's ``clinical_mass`` keys.

Statistics. Shares are plain proportions over the stated denominator, which is
reported beside each. clinical_mass quantiles use linear interpolation between
order statistics (statistics.quantiles, method="inclusive"); a null
clinical_mass is counted in ``n_null`` and excluded from the statistics, never
read as zero. ``mean_difference_b_minus_a`` is the mean of the per-pair
differences over pairs where both values are present.

Sampling. ``--examples K`` draws K clinical-tagged feature descriptions per
model for reading by eye, with ``random.Random(seed)`` over the unique features
sorted by (layer, index); the seed and K are written into the report. K = 0
draws nothing.

Usage:
  python scripts/feature_label_calibration.py <dir_a> <dir_b> [--out report.json]
      [--examples 10] [--seed 7]

Exit codes: 0 report written; 2 an input was refused (the error is named).
No medical vocabulary lives in this file: categories and descriptions come from
the trace data and the keyword config the tracer used.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from medlang_circuits.feature_tagger import FEATURE_SOURCE_SET_KEY, SUMMARY_KEY
    from medlang_circuits.schema_utils import is_feature_node, node_layer_and_index
except ImportError:  # invoked as `python scripts/feature_label_calibration.py` without an install
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from medlang_circuits.feature_tagger import FEATURE_SOURCE_SET_KEY, SUMMARY_KEY
    from medlang_circuits.schema_utils import is_feature_node, node_layer_and_index

REPORT_RULE = "feature_label_calibration/2026-10-09"
DEFAULT_SEED = 7
DEFAULT_EXAMPLES = 10
CLINICAL = "clinical"
EXPLANATION_JOIN = " | "  # neuronpedia_features._extract_description joins explanations with this
TAGGED_RE = re.compile(r"^pair_(\d+)_([A-Za-z0-9_]+)\.tagged\.json$")


class CalibrationInputError(Exception):
    """An input the comparison cannot use; the subclass name says which."""


class MissingSummariesError(CalibrationInputError):
    """The directory holds no batch_summary*.json."""


class MissingTaggedGraphsError(CalibrationInputError):
    """The directory holds no pair_NN_<role>.tagged.json, so no descriptions to measure."""


class UntaggedGraphError(CalibrationInputError):
    """A tagged graph has a feature node with no medlang annotation."""


class MixedModelError(CalibrationInputError):
    """The summaries in one directory name more than one graph_model or source_set."""


class DuplicateIndexError(CalibrationInputError):
    """Two summary parts in one directory both report the same pair index."""


class TaggedGraphSetMismatchError(CalibrationInputError):
    """The tagged graphs are not exactly the (index, role) set the summaries report as traced."""


class GraphModelMismatchError(CalibrationInputError):
    """A tagged graph's metadata.scan is missing or names another model than the summaries."""


class TaggingSourceSetMismatchError(CalibrationInputError):
    """A tagged graph does not record the summaries' source set as the set its labels came from."""


class GraphPromptMismatchError(CalibrationInputError):
    """A tagged graph's metadata.prompt does not match the prompt recorded in the summary."""


BOS_TOKENS_RE = re.compile(r"^(?:<\|[a-zA-Z0-9_.-]+\|>|<[a-zA-Z0-9_.-]+>|\s)+")


def prompts_match(graph_prompt: Any, summary_prompt: Any) -> bool:
    """True when graph metadata.prompt matches the prompt recorded in the summary part.

    Neuronpedia may record the prompt with a prepended model BOS or special token
    (such as '<bos>' or '<|endoftext|>'), so leading special tokens are stripped
    or checked via suffix match."""
    if not isinstance(graph_prompt, str) or not isinstance(summary_prompt, str):
        return False
    g, s = graph_prompt.strip(), summary_prompt.strip()
    if not g or not s:
        return False
    if g == s:
        return True
    g_clean = BOS_TOKENS_RE.sub("", g).strip()
    s_clean = BOS_TOKENS_RE.sub("", s).strip()
    if g_clean == s_clean:
        return True
    return g.endswith(s)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CalibrationInputError(f"{path}: unreadable JSON ({exc})") from exc


def load_summaries(trace_dir: Path) -> dict[str, Any]:
    """graph_model, source_set and results-by-index from every batch_summary*.json."""
    parts = sorted(trace_dir.glob("batch_summary*.json"))
    if not parts:
        raise MissingSummariesError(f"{trace_dir}: no batch_summary*.json")
    models, source_sets = set(), set()
    results: dict[int, dict[str, Any]] = {}
    for part in parts:
        summary = _read_json(part)
        models.add(summary.get("graph_model"))
        source_sets.add(summary.get("source_set"))
        for row in summary.get("results", []):
            index = row.get("index")
            if index in results:
                raise DuplicateIndexError(f"{trace_dir}: index {index} appears in more than one summary part")
            results[index] = row
    if len(models) != 1 or len(source_sets) != 1:
        raise MixedModelError(f"{trace_dir}: graph_model {sorted(map(str, models))}, "
                              f"source_set {sorted(map(str, source_sets))}")
    return {"graph_model": models.pop(), "source_set": source_sets.pop(),
            "parts": len(parts), "results": results}


def _share(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def expected_graphs(results: dict[int, dict[str, Any]]) -> set[tuple[int, str]]:
    """(index, role) of every graph the summaries say was traced and tagged.

    A 2panel result's ``clinical_mass`` has one key per traced side (a screened-out
    pair has ``clinical`` only; --show-mitigation adds ``translated``), and each
    traced side wrote ``pair_NN_<role>.tagged.json``."""
    return {(index, role) for index, row in results.items() for role in (row.get("clinical_mass") or {})}


def _list_preview(items: list[tuple[int, str]], limit: int = 10) -> str:
    shown = ", ".join(f"{i}/{r}" for i, r in items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def tagged_graph_stats(trace_dir: Path, graph_model: str | None, source_set: str | None,
                       results: dict[int, dict[str, Any]], examples: int, seed: int) -> dict[str, Any]:
    """Label coverage and clinical tagging over every tagged graph in the directory.

    The graphs must be exactly the ``expected`` (index, role) set the summaries
    report as traced: a missing graph (only some of a chunked run's offset
    artifacts downloaded) or an extra one (an artifact whose summary part is not
    here) would measure labels over a different population of pairs than the
    clinical_mass the same report gives, so either is refused. Every graph must
    also name ``graph_model`` (the summaries' model) in metadata.scan, record
    ``source_set`` in its tagging metadata, and match the prompt recorded in the
    summary for that pair and role."""
    expected = expected_graphs(results)
    paths = sorted(p for p in trace_dir.glob("pair_*.tagged.json") if TAGGED_RE.match(p.name))
    if not paths:
        raise MissingTaggedGraphsError(
            f"{trace_dir}: no pair_NN_<role>.tagged.json. Feature descriptions are stored only in the "
            "tagged graphs, which CI keeps in the circuit-trace workflow artifact "
            "(circuit-trace-<model>-<mode>-<run>-offset<k>); download it into this directory")
    found = {(int(m.group(1)), m.group(2)) for p in paths if (m := TAGGED_RE.match(p.name))}
    missing, extra = sorted(expected - found), sorted(found - expected)
    if missing or extra:
        raise TaggedGraphSetMismatchError(
            f"{trace_dir}: the tagged graphs do not match the summaries' traced pairs (index/role). "
            + (f"Missing {len(missing)}: {_list_preview(missing)}; download every "
               "circuit-trace-<model>-<mode>-<run>-offset<k> artifact of the run. " if missing else "")
            + (f"Not in any summary {len(extra)}: {_list_preview(extra)}; add the matching "
               "batch_summary part or remove these graphs." if extra else ""))
    nodes = described = clinical = multi = undecodable = 0
    words: list[int] = []
    methods: Counter[str] = Counter()
    unique: dict[tuple[int, int], dict[str, Any]] = {}
    for path in paths:
        m = TAGGED_RE.match(path.name)
        assert m is not None
        pair_idx, role = int(m.group(1)), m.group(2)
        graph = _read_json(path)
        meta = graph.get("metadata") or {}
        if meta.get("scan") != graph_model:
            raise GraphModelMismatchError(
                f"{path}: metadata.scan is {meta.get('scan')!r} but the directory's summaries name "
                f"graph_model {graph_model!r}; a tagged graph from another model or run is in this directory")
        tagging = meta.get(SUMMARY_KEY) or {}
        if FEATURE_SOURCE_SET_KEY not in tagging:
            raise TaggingSourceSetMismatchError(
                f"{path}: records no {SUMMARY_KEY}.{FEATURE_SOURCE_SET_KEY}, so the source set its labels came "
                "from cannot be checked (graphs tagged before 2026-10-09 do not record it); re-trace the pairs")
        if tagging[FEATURE_SOURCE_SET_KEY] != source_set:
            raise TaggingSourceSetMismatchError(
                f"{path}: labels were tagged from source set {tagging[FEATURE_SOURCE_SET_KEY]!r} but the "
                f"directory's summaries name {source_set!r}; a tagged graph from another trace is in this directory")
        summary_prompt = (results.get(pair_idx, {}).get("prompts") or {}).get(role)
        if not prompts_match(meta.get("prompt"), summary_prompt):
            raise GraphPromptMismatchError(
                f"{path}: metadata.prompt ({meta.get('prompt')!r}) does not match summary prompt for pair "
                f"{pair_idx}/{role} ({summary_prompt!r}); a tagged graph from another run or prompt set is in "
                "this directory")
        for node in graph.get("nodes", []):
            if not is_feature_node(node):
                continue
            note = node.get("medlang")
            if not isinstance(note, dict) or "category" not in note:
                raise UntaggedGraphError(f"{path}: feature node {node.get('node_id')!r} carries no medlang tag")
            nodes += 1
            methods[str(note.get("method"))] += 1
            description = (note.get("description") or "").strip()
            if description:
                described += 1
                words.append(len(description.split()))
                multi += EXPLANATION_JOIN in description
            clinical += note.get("category") == CLINICAL
            key = node_layer_and_index(node, meta.get("schema_version"), meta["scan"])
            if key is None:
                undecodable += 1
                continue
            unique.setdefault(key, {"description": description, "category": note.get("category")})
    u_described = sum(1 for f in unique.values() if f["description"])
    u_clinical = [k for k, f in sorted(unique.items()) if f["category"] == CLINICAL]
    drawn = random.Random(seed).sample(u_clinical, min(examples, len(u_clinical))) if examples else []
    return {
        "tagged_graphs": len(paths),
        "feature_nodes": {
            "n": nodes,
            "share_described": _share(described, nodes),
            "share_clinical": _share(clinical, nodes),
            "share_described_multi_explanation": _share(multi, described),
            "mean_description_words": round(statistics.fmean(words), 2) if words else None,
            "methods": dict(sorted(methods.items())),
            "n_undecodable": undecodable,
        },
        "unique_features": {
            "n": len(unique),
            "share_described": _share(u_described, len(unique)),
            "share_clinical": _share(len(u_clinical), len(unique)),
        },
        "clinical_examples": [{"layer": k[0], "index": k[1], "description": unique[k]["description"]}
                              for k in sorted(drawn)],
    }


def distribution(values: list[float | None]) -> dict[str, Any]:
    """n, n_null and summary statistics of the non-null values (nulls are never zeros)."""
    present = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    out: dict[str, Any] = {"n": len(present), "n_null": len(values) - len(present)}
    if present:
        out.update(mean=round(statistics.fmean(present), 4), median=round(statistics.median(present), 4),
                   min=round(min(present), 4), max=round(max(present), 4))
        if len(present) >= 2:
            q1, _, q3 = statistics.quantiles(present, n=4, method="inclusive")
            out.update(q25=round(q1, 4), q75=round(q3, 4))
    return out


def _mass(row: dict[str, Any], role: str) -> float | None:
    value = (row.get("clinical_mass") or {}).get(role)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def compare_pairs(a: dict[int, dict[str, Any]], b: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Side-by-side clinical_mass on the pairs both sides traced with identical prompts."""
    shared = sorted(set(a) & set(b))
    mismatch = [i for i in shared if (a[i].get("prompts") or {}) != (b[i].get("prompts") or {})]
    joined = [i for i in shared if i not in mismatch]
    roles = sorted({role for i in joined for row in (a[i], b[i]) for role in (row.get("clinical_mass") or {})})
    rows = [{"index": i, **{f"{side}_{role}": _mass(src[i], role)
                            for role in roles for side, src in (("a", a), ("b", b))}}
            for i in joined]
    side_by_side = {}
    for role in roles:
        both = [(x, y) for i in joined
                if (x := _mass(a[i], role)) is not None and (y := _mass(b[i], role)) is not None]
        side_by_side[role] = {
            "a": distribution([_mass(a[i], role) for i in joined]),
            "b": distribution([_mass(b[i], role) for i in joined]),
            "n_both": len(both),
            "mean_difference_b_minus_a": round(statistics.fmean(y - x for x, y in both), 4) if both else None,
        }
    return {"n_joined": len(joined), "only_in_a": sorted(set(a) - set(b)), "only_in_b": sorted(set(b) - set(a)),
            "prompt_mismatch": mismatch, "clinical_mass_side_by_side": side_by_side, "rows": rows}


def model_report(trace_dir: Path, examples: int, seed: int) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    summaries = load_summaries(trace_dir)
    results = summaries["results"]
    roles = sorted({role for row in results.values() for role in (row.get("clinical_mass") or {})})
    report = {
        "dir": str(trace_dir),
        "graph_model": summaries["graph_model"],
        "source_set": summaries["source_set"],
        "summary_parts": summaries["parts"],
        "n_results": len(results),
        **tagged_graph_stats(trace_dir, summaries["graph_model"], summaries["source_set"],
                             results, examples, seed),
        "clinical_mass": {role: distribution([_mass(row, role) for row in results.values()]) for role in roles},
    }
    if summaries["source_set"] is None:
        report["warning"] = ("source_set is null: traced with NullFetcher, so no feature was labelled "
                             "and clinical_mass is the ~0 artifact")
    return report, results


def build_report(dir_a: Path, dir_b: Path, examples: int = DEFAULT_EXAMPLES,
                 seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """The full calibration report for two trace directories (raises CalibrationInputError)."""
    report_a, results_a = model_report(dir_a, examples, seed)
    report_b, results_b = model_report(dir_b, examples, seed)
    return {"rule": REPORT_RULE, "seed": seed, "examples_per_model": examples,
            "models": {"a": report_a, "b": report_b}, "pairs": compare_pairs(results_a, results_b)}


def _print_summary(report: dict[str, Any]) -> None:
    for side, m in report["models"].items():
        f, u = m["feature_nodes"], m["unique_features"]
        print(f"{side}: {m['graph_model']} / {m['source_set']} - {m['tagged_graphs']} tagged graphs, "
              f"{f['n']} feature nodes ({u['n']} unique): described {f['share_described']}, "
              f"clinical {f['share_clinical']} (unique: {u['share_described']}, {u['share_clinical']})")
    pairs = report["pairs"]
    print(f"pairs joined {pairs['n_joined']} (only a {len(pairs['only_in_a'])}, only b "
          f"{len(pairs['only_in_b'])}, prompt mismatch {len(pairs['prompt_mismatch'])})")
    for role, s in pairs["clinical_mass_side_by_side"].items():
        print(f"clinical_mass[{role}]: a mean {s['a'].get('mean')} / b mean {s['b'].get('mean')} "
              f"over {s['n_both']} pairs with both; mean b-a {s['mean_difference_b_minus_a']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dir_a", type=Path, help="trace dir of the reference model (e.g. gemma-2-2b)")
    parser.add_argument("dir_b", type=Path, help="trace dir of the model under check, same pairs")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--examples", type=int, default=DEFAULT_EXAMPLES,
                        help=f"clinical-tagged descriptions to sample per model (default {DEFAULT_EXAMPLES})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"seed for the example draw, recorded in the report (default {DEFAULT_SEED})")
    args = parser.parse_args(argv)
    if args.examples < 0:
        parser.error("--examples must be >= 0")
    try:
        report = build_report(args.dir_a, args.dir_b, examples=args.examples, seed=args.seed)
    except CalibrationInputError as exc:
        print(f"refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    _print_summary(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
