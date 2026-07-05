"""Compare attribution graphs for clinical vs. colloquial patient medical language.

Modules:
    graph_client         - generate attribution graphs (hosted neuronpedia.org API or local graph server)
    feature_tagger       - Task 1: classify graph features as clinical / off_target / structural
    compare_viz          - Task 2: stacked two-panel HTML + PNG visualization
    translate            - Task 3: patient-language -> clinical-language translation (Anthropic API stub)
    pipeline             - Task 3: end-to-end orchestration
"""

from medlang_circuits.feature_tagger import annotate_graph, classify_text
from medlang_circuits.pipeline import run_comparison
from medlang_circuits.translate import translate_to_clinical

__all__ = ["annotate_graph", "classify_text", "run_comparison", "translate_to_clinical"]
