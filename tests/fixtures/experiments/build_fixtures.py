"""Regenerate the synthetic experiment fixtures in this directory.

    python tests/fixtures/experiments/build_fixtures.py [OUT_DIR]

Writes ``protocol_synthetic.json``, ``behavior_logits.json``, ``readout_spec.json`` and
``readout_packet.json``. Stdlib only. It imports nothing from ``scripts/``: the hashes below are computed with
``hashlib`` directly, so the fixtures do not depend on the code they test.

Everything here is a placeholder. The "prompts" are words from an eight-entry toy vocabulary. The logits are
hand-chosen numbers. No file holds a real prompt, a real target, a real token id or a real model output.

``readout_spec.json`` and ``readout_packet.json`` are derived from the exploratory v1 synthetic fixtures
(``tests/fixtures/exploratory/synthetic_spec.json``): the v1 conventions and the three method blocks are copied
from that file as it is on disk, which this script reads and never edits. Model, cases, plan and logits are
replaced with the toy slice below.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
V1_SPEC = HERE.parent / "exploratory" / "synthetic_spec.json"

VOCABULARY = ["alpha", "beta", "gamma", "delta", "tail", "omega", "%", "/"]
REVISION = "1" * 40
MODEL = {"study_id": "toy-model", "hf_id": "fixture/toy-model", "revision": REVISION,
         "tokenizer_id": "fixture/toy-tokenizer", "tokenizer_revision": REVISION,
         "hidden_size": 8, "n_layers": 3, "dtype": "float32", "backend": "fixture"}
SEED = 7
TARGETS = [{"id": "t1", "role": "answer", "text": "omega", "token_ids": [5]},
           {"id": "c1", "role": "intermediate", "text": "delta", "token_ids": [3]}]
V1_VARIANT = {"clinical": "source", "colloquial": "recipient", "normalized": "normalized"}

# family id -> (split, facts, {variant: token ids}). A prompt is its tokens' words joined by one space.
FAMILIES: dict[str, tuple[str, list[str], dict[str, list[int]]]] = {
    "fam-1": ("discovery", ["fact_a", "fact_b"],
              {"clinical": [0, 4], "colloquial": [1, 4], "normalized": [2, 4]}),
    "fam-2": ("validation", ["fact_c"],
              {"clinical": [0, 1, 4], "colloquial": [1, 0, 4], "normalized": [2, 0, 4]}),
    "fam-3": ("fresh_test", ["fact_d", "fact_e"],
              {"clinical": [3, 0, 4], "colloquial": [3, 1, 4], "normalized": [3, 2, 4]}),
}

# Next-token logits are the natural log of these integer weights, so each softmax probability is
# weight / sum(weights) and can be checked by hand. Target t1 is token 5; target c1 is token 3.
#   fam-1: sums 12 -> t1 = 4/12, 2/12, 3/12   (clinical - colloquial = +1/6; colloquial - normalized = -1/12)
#   fam-2: sums 16 -> t1 = 8/16, 2/16, 4/16   (+3/8; -1/8)
#   fam-3: sums 10 -> t1 = 3/10, 3/10, 1/10   (0 exactly; +1/5)
BEHAVIOR_WEIGHTS: dict[str, dict[str, list[int]]] = {
    "fam-1": {"clinical": [1, 1, 1, 2, 1, 4, 1, 1], "colloquial": [1, 1, 4, 1, 1, 2, 1, 1],
              "normalized": [1, 1, 2, 1, 1, 3, 2, 1]},
    "fam-2": {"clinical": [2, 1, 1, 1, 1, 8, 1, 1], "colloquial": [2, 1, 1, 1, 1, 2, 1, 7],
              "normalized": [2, 1, 1, 1, 1, 4, 1, 5]},
    "fam-3": {"clinical": [1, 1, 1, 1, 1, 3, 1, 1], "colloquial": [1, 1, 1, 1, 1, 3, 1, 1],
              "normalized": [1, 1, 1, 1, 3, 1, 1, 1]},
}

# Two readout cells are written out by hand so that a test can check ranks without running any formula:
# logit_lens, layer 1, last position of fam-1. With tokens 6 and 7 excluded by the vocabulary filter,
#   clinical:   t1 (token 5, logit 5.0) has raw rank 3 and filtered rank 1
#   colloquial: t1 (token 5, logit 0.0) has raw rank 8 and filtered rank 6
HAND_READOUTS = {("fam-1", "clinical", "logit_lens", 1): [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 6.0],
                 ("fam-1", "colloquial", "logit_lens", 1): [5.0, 4.0, 3.0, 2.0, 1.0, 0.0, 7.0, 6.0]}
METHODS = ("logit_lens", "j_lens", "jpp")
READOUT_LAYERS = (0, 1)


def canonical(value: Any) -> str:
    """SHA-256 of canonical JSON, the rule of scripts/exploratory_methods.digest, restated with the stdlib."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def prompt_of(token_ids: list[int]) -> str:
    return " ".join(VOCABULARY[t] for t in token_ids)


def variant_entry(token_ids: list[int]) -> dict[str, Any]:
    prompt = prompt_of(token_ids)
    return {"prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "token_ids": token_ids, "token_sha256": canonical(token_ids)}


def behavior_logits(family: str, variant: str) -> list[float]:
    return [math.log(weight) for weight in BEHAVIOR_WEIGHTS[family][variant]]


def readout_logits(family: str, variant: str, method: str, layer: int, position: int, last: int) -> list[float]:
    """A permutation of 0..7 that depends on every coordinate; the two hand-written cells override it."""
    if position == last and (family, variant, method, layer) in HAND_READOUTS:
        return HAND_READOUTS[(family, variant, method, layer)]
    step = (1, 3, 5)[METHODS.index(method)] if layer == 0 else (7, 5, 3)[METHODS.index(method)]
    shift = (sorted(FAMILIES).index(family) * 3 + sorted(V1_VARIANT).index(variant) * 2 + position) % 8
    return [float((index * step + shift) % 8) for index in range(8)]


def build_protocol() -> dict[str, Any]:
    return {
        "schema_version": "patientwords.experiment-protocol/1",
        "protocol_id": "synthetic-slice-1", "version": "1", "synthetic": True, "seed": SEED,
        "notes": "Synthetic placeholders only. Three families, one per split. No real prompt, target or model.",
        "evidence": {"evidence_class": "synthetic_fixture", "clinical_review": "not_applicable_synthetic"},
        "model": MODEL,
        "input_settings": {"chat_template": None, "add_special_tokens": True, "truncation": False},
        "case_families": [
            {"family_id": family, "split": split, "review_status": "synthetic_placeholder", "legacy_join": None,
             "facts": facts, "variants": {name: variant_entry(ids) for name, ids in variants.items()},
             "targets": TARGETS}
            for family, (split, facts, variants) in FAMILIES.items()],
        "methods": [
            {"id": "behavior_next_token"},
            {"id": "logit_lens", "capture_site": "block_output", "layer_index_base": 0,
             "layers": list(READOUT_LAYERS), "positions": "all"},
            {"id": "j_lens", "capture_site": "block_output", "layer_index_base": 0, "layers": [1]},
            {"id": "jpp", "capture_site": "block_output", "layer_index_base": 0, "layers": [1],
             "artifact": {"id": "fixture/toy-jpp-lens", "sha256": "4" * 64, "fit_model_revision": None,
                          "fit_tokenizer_revision": None}},
        ],
        "comparisons": [{"id": "clinical_vs_colloquial", "a": "clinical", "b": "colloquial"},
                        {"id": "colloquial_vs_normalized", "a": "colloquial", "b": "normalized"}],
        "replicates": 1,
        "primary_endpoint": {"method": "behavior_next_token", "metric": "full_vocab_probability", "target": "t1"},
        "exclusions": [],
    }


def build_behavior(protocol: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for family in protocol["case_families"]:
        for name, entry in family["variants"].items():
            rows.append({"family_id": family["family_id"], "variant": name,
                         "prompt_sha256": entry["prompt_sha256"], "token_sha256": entry["token_sha256"],
                         "weights": BEHAVIOR_WEIGHTS[family["family_id"]][name],
                         "logits": behavior_logits(family["family_id"], name)})
    return {"schema_version": "patientwords.fixture-behavior-logits/1", "synthetic": True,
            "extraction": "fixture_supplied_next_token_logits",
            "note": "Hand-chosen values. logits[i] = ln(weights[i]), so softmax probability i is "
                    "weights[i] / sum(weights). Not a model output.",
            "model": {"hf_id": MODEL["hf_id"], "revision": MODEL["revision"]},
            "vocabulary_size": len(VOCABULARY), "rows": rows}


def build_readout(protocol: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    template = json.loads(V1_SPEC.read_text(encoding="utf-8"))
    v1_model = {"id": MODEL["hf_id"], "study_id": MODEL["study_id"], "revision": REVISION,
                "tokenizer_id": MODEL["tokenizer_id"], "tokenizer_revision": REVISION, "precision": MODEL["dtype"],
                "backend": MODEL["backend"], "hidden_size": MODEL["hidden_size"], "intermediate_size": 16,
                "n_layers": MODEL["n_layers"]}
    methods = json.loads(json.dumps(template["methods"]))
    for name in ("j_lens", "jpp"):
        methods[name].update({"model_id": v1_model["id"], "model_revision": REVISION,
                              "tokenizer_revision": REVISION})
    cases = []
    for number, family in enumerate(protocol["case_families"], start=1):
        variants = {}
        for name, entry in family["variants"].items():
            variants[V1_VARIANT[name]] = {**entry, "positions": list(range(len(entry["token_ids"])))}
        cases.append({"id": family["family_id"], "family_id": family["family_id"],
                      "template_family": f"template-{family['family_id']}", "split": family["split"],
                      "holdout_status": "unsealed_reviewed", "review_provenance": "synthetic fixture only",
                      "join": {"batch": "synthetic_only", "index": number, "model": v1_model["study_id"]},
                      "variants": variants, "targets": TARGETS})
    plan = [{"id": "self-fam-1", "case_id": "fam-1", "donor": "recipient", "recipient": "recipient",
             "kind": "observed_replacement", "component": "block_output", "layer": 1, "positions": [[1, 1]],
             "channels": None, "control": "self", "seed": SEED}]
    spec = {
        "schema_version": template["schema_version"], "synthetic": True,
        "publication": template["publication"], "output_namespace": template["output_namespace"],
        "seed": SEED, "model": v1_model, "capture_site": template["capture_site"],
        "layer_index_base": template["layer_index_base"], "final_norm": template["final_norm"],
        "input_settings": template["input_settings"], "methods": methods,
        "fixed_layers": list(READOUT_LAYERS), "top_k": template["top_k"],
        "gap_threshold": template["gap_threshold"],
        "vocabulary_filter": {"id": "experiment-fixture-exclusions-v1", "excluded": [
            {"token_id": 6, "reason": "prespecified symbol audit"},
            {"token_id": 7, "reason": "prespecified punctuation audit"}]},
        "cases": cases, "intervention_plan": plan,
        "experiment_variant_map": V1_VARIANT,
        "derived_from": {"path": "tests/fixtures/exploratory/synthetic_spec.json",
                         "sha256": hashlib.sha256(V1_SPEC.read_bytes()).hexdigest(),
                         "kept": ["schema_version", "publication", "output_namespace", "capture_site",
                                  "layer_index_base", "final_norm", "input_settings", "methods", "top_k",
                                  "gap_threshold"],
                         "replaced": ["model", "cases", "intervention_plan", "vocabulary_filter", "fixed_layers"]},
    }
    readouts, outputs = [], []
    for family in protocol["case_families"]:
        for name, entry in family["variants"].items():
            last = len(entry["token_ids"]) - 1
            outputs.append({"case_id": family["family_id"], "variant": V1_VARIANT[name],
                            "extraction": "model.logits[0,-1]",
                            "logits": behavior_logits(family["family_id"], name)})
            for method in METHODS:
                for layer in READOUT_LAYERS:
                    for position in range(last + 1):
                        readouts.append({"case_id": family["family_id"], "variant": V1_VARIANT[name],
                                         "method": method, "layer": layer, "position": position,
                                         "logits": readout_logits(family["family_id"], name, method, layer,
                                                                  position, last)})
    packet = {
        "schema_version": template["schema_version"], "execution_status": "synthetic",
        "spec_sha256": canonical(spec), "model": v1_model, "vocabulary": VOCABULARY,
        "readouts": readouts, "model_outputs": outputs,
        # A self patch: the recipient's own activations, so the logits equal its baseline and the edit is 0.
        "interventions": [{**plan[0], "logits": behavior_logits("fam-1", "colloquial"), "edit_l2": 0.0}],
        "environment": {"kind": "synthetic_fixture", "model_execution": False, "seed": SEED},
        "runtime_seconds": None, "peak_memory_bytes": None,
    }
    return spec, packet


def build_all() -> dict[str, Any]:
    protocol = build_protocol()
    spec, packet = build_readout(protocol)
    return {"protocol_synthetic.json": protocol, "behavior_logits.json": build_behavior(protocol),
            "readout_spec.json": spec, "readout_packet.json": packet}


def render(document: Any) -> str:
    return json.dumps(document, indent=1, ensure_ascii=False, allow_nan=False) + "\n"


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else HERE
    out.mkdir(parents=True, exist_ok=True)
    for name, document in build_all().items():
        (out / name).write_text(render(document), encoding="utf-8")
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
