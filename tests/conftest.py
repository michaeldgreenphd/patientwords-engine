import pytest

# Abstract test vocabulary - real term lists live in the user's local keyword_config.json.
TEST_KEYWORD_CONFIG = {
    "clinical": ["alpha", "beta term"],
    "off_target": ["gamma"],
    "structural": ["punctuation", "syntax"],
}


class StubFetcher:
    """Maps (layer, index) -> canned feature details without network access."""

    def __init__(self, details: dict):
        self.details = details
        self.calls = []

    def get(self, layer, index):
        self.calls.append((layer, index))
        return self.details.get((layer, index), {"description": "", "top_tokens": []})


def make_graph():
    """Minimal old-schema (schema 0) gemma-2-2b graph: feature = layer*100000 + index."""
    return {
        "metadata": {
            "slug": "test-graph",
            "scan": "gemma-2-2b",
            "prompt": "the quick brown fox",
            "prompt_tokens": ["the", " quick", " brown", " fox"],
        },
        "qParams": {},
        "nodes": [
            {"node_id": "E_100_0", "feature": 100, "layer": "E", "ctx_idx": 0,
             "feature_type": "embedding", "jsNodeId": "E_100-0", "clerp": "the"},
            {"node_id": "3_00042_1", "feature": 300042, "layer": "3", "ctx_idx": 1,
             "feature_type": "cross layer transcoder", "jsNodeId": "3_42-1", "clerp": "",
             "influence": 0.3, "activation": 5.0},
            {"node_id": "7_00007_2", "feature": 700007, "layer": "7", "ctx_idx": 2,
             "feature_type": "cross layer transcoder", "jsNodeId": "7_7-2", "clerp": "",
             "influence": 0.5, "activation": 2.0},
            {"node_id": "9_00001_3", "feature": 900001, "layer": "9", "ctx_idx": 3,
             "feature_type": "cross layer transcoder", "jsNodeId": "9_1-3", "clerp": "",
             "influence": 0.6, "activation": 1.0},
            {"node_id": "err_5_2", "feature": None, "layer": "5", "ctx_idx": 2,
             "feature_type": "mlp reconstruction error", "jsNodeId": "err_5-2", "clerp": ""},
            {"node_id": "L_999_3", "feature": 999, "layer": "26", "ctx_idx": 3,
             "feature_type": "logit", "jsNodeId": "L_999-3", "clerp": "jumps (p=0.81)"},
        ],
        "links": [
            {"source": "E_100_0", "target": "3_00042_1", "weight": 2.0},
            {"source": "3_00042_1", "target": "7_00007_2", "weight": 4.0},
            {"source": "7_00007_2", "target": "L_999_3", "weight": 6.0},
            {"source": "9_00001_3", "target": "L_999_3", "weight": -1.5},
        ],
    }


@pytest.fixture
def graph():
    return make_graph()


def build_fetcher():
    return StubFetcher({
        (3, 42): {"description": "references to alpha and beta term contexts", "top_tokens": ["alpha"]},
        (7, 7): {"description": "gamma-related concepts", "top_tokens": ["gamma"]},
        (9, 1): {"description": "something entirely unmatched", "top_tokens": []},
    })


@pytest.fixture
def fetcher():
    return build_fetcher()
