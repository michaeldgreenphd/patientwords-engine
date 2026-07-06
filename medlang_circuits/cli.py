"""Command-line entry point.

Examples:
    # full pipeline (auto-translation of the patient phrasing)
    medlang-compare --patient "I've got the blues, so I need to talk to a"

    # explicit prompt pair, local graph server, no PNG
    medlang-compare \
        --patient "I've got the blues, so I need to talk to a" \
        --clinical "I have depression, so I need to talk to a" \
        --backend local --no-png

    # tag an existing graph JSON in place (no generation)
    medlang-compare tag path/to/graph.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from medlang_circuits.feature_tagger import annotate_graph
from medlang_circuits.graph_client import add_graph_cli_arguments, generation_params_from_args
from medlang_circuits.pipeline import run_comparison


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    argv = sys.argv[1:] if argv is None else argv

    if argv and argv[0] == "tag":
        return _tag_command(argv[1:])

    parser = argparse.ArgumentParser(prog="medlang-compare", description="Compare attribution graphs for two phrasings.")
    parser.add_argument("--patient", required=True, help="Colloquial patient phrasing (next-token prompt)")
    parser.add_argument("--clinical", default=None, help="Clinical phrasing; auto-translated when omitted")
    parser.add_argument("--backend", choices=["hosted", "local"], default="hosted")
    parser.add_argument("--out", default="medlang_out", help="Output directory")
    parser.add_argument("--llm-classifier", action="store_true", help="Use the Anthropic fallback for unmatched features")
    parser.add_argument("--no-llm-translation", action="store_true", help="Skip the API translation (phrase table only)")
    parser.add_argument("--no-png", action="store_true", help="Skip the matplotlib PNG export")
    add_graph_cli_arguments(parser)
    args = parser.parse_args(argv)

    result = run_comparison(
        patient_prompt=args.patient,
        clinical_prompt=args.clinical,
        backend=args.backend,
        out_dir=args.out,
        use_llm_translation=not args.no_llm_translation,
        use_llm_classifier=args.llm_classifier,
        render_png=not args.no_png,
        graph_model=args.graph_model,
        source_set=args.source_set,
        generation_params=generation_params_from_args(args),
    )
    print(json.dumps(result, indent=2))
    return 0


def _tag_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="medlang-compare tag", description="Tag an existing graph JSON in place.")
    parser.add_argument("graph_json", help="Path to a graph JSON file")
    parser.add_argument("--llm-classifier", action="store_true")
    args = parser.parse_args(argv)

    with open(args.graph_json, encoding="utf-8") as f:
        graph = json.load(f)
    llm_classifier = None
    if args.llm_classifier:
        from medlang_circuits.llm_client import classify_feature_with_llm

        llm_classifier = classify_feature_with_llm
    annotate_graph(graph, llm_classifier=llm_classifier)
    with open(args.graph_json, "w", encoding="utf-8") as f:
        json.dump(graph, f)
    print(json.dumps(graph["metadata"].get("medlang_summary", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
