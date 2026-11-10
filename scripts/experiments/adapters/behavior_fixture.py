"""Payload kind ``behavior_next_token/1`` from independently supplied fixture logits.

The fixture file ``behavior_logits.json`` holds one full-vocabulary next-token logit vector per (family,
variant). This adapter scores each protocol target with ``scripts.exploratory_methods.rank_target``: softmax
over the complete vocabulary, descending-logit rank with ties broken by the smaller token id. It runs no model.
The numbers describe the fixture, not any checkpoint.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from scripts.exploratory_methods import rank_target
from scripts.experiments.common import FIXTURE_BACKEND, FIXTURE_MODEL, digest, integer, require, sha256_bytes

FIXTURE_FILE = "behavior_logits.json"
FIXTURE_SCHEMA = "patientwords.fixture-behavior-logits/1"
PAYLOAD_KIND = "behavior_next_token/1"
EXTRACTION = "fixture_supplied_next_token_logits"


def _family(protocol: dict[str, Any], family_id: str) -> dict[str, Any]:
    for family in protocol["case_families"]:
        if family["family_id"] == family_id:
            return family
    raise KeyError(family_id)


class BehaviorFixtureAdapter:
    method_ids: tuple[str, ...] = ("behavior_next_token",)
    payload_kinds: tuple[str, ...] = (PAYLOAD_KIND,)

    def capabilities(self) -> list[dict]:
        return [{
            "model": dict(FIXTURE_MODEL), "method": "behavior_next_token", "backend": FIXTURE_BACKEND,
            "dtype": None, "artifact": None, "status": "runtime_verified_offline_fixture",
            "evidence": [{"source": "tests/test_experiments_core.py", "date": "2026-11-10"}],
            "status_note": "Fixture-supplied next-token logits scored offline. It says nothing about a real model.",
        }]

    def _load(self, context: dict) -> dict[str, Any]:
        """The fixture file, read once per run: ``{"doc", "sha256", "problem"}``.

        The bytes are read once and both parsed and hashed, so the recorded hash is the hash of what was
        scored. ``doc`` is None with a ``problem`` sentence when the file is absent, is not JSON or is not a
        JSON object; ``sha256`` is None only when the file is absent.
        """
        path = Path(context["fixtures_dir"]) / FIXTURE_FILE
        cache = context.setdefault("_cache", {})
        key = ("behavior", str(path))
        if key not in cache:
            if not path.is_file():
                cache[key] = {"doc": None, "sha256": None,
                              "problem": f"fixture file {FIXTURE_FILE} is not present in {path.parent}"}
            else:
                data = path.read_bytes()
                entry: dict[str, Any] = {"doc": None, "sha256": sha256_bytes(data), "problem": None}
                try:
                    doc = json.loads(data.decode("utf-8"))
                except ValueError:
                    entry["problem"] = f"fixture file {FIXTURE_FILE} in {path.parent} is not JSON"
                else:
                    if isinstance(doc, dict):
                        entry["doc"] = doc
                    else:
                        entry["problem"] = f"fixture file {FIXTURE_FILE} in {path.parent} is not a JSON object"
                cache[key] = entry
        return cache[key]

    def _row(self, task: dict, context: dict) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        doc = self._load(context)["doc"]
        if doc is None:
            return None, None
        spec = task["spec"]
        listed = doc.get("rows", [])
        rows = [row for row in (listed if isinstance(listed, list) else [])
                if isinstance(row, dict) and row.get("family_id") == spec["family_id"]
                and row.get("variant") == spec["variant"]]
        return doc, (rows[0] if len(rows) == 1 else None)

    def input_identity(self, task: dict, context: dict) -> str | None:
        """Digest of the fixture file's bytes: the one input of a behaviour task outside its spec."""
        sha = self._load(context)["sha256"]
        return digest({"adapter_inputs": {FIXTURE_FILE: sha}}) if sha is not None else None

    def preflight(self, task: dict, context: dict) -> tuple[str, str | None]:
        doc, row = self._row(task, context)
        if doc is None:
            return "unavailable", self._load(context)["problem"]
        if row is None:
            spec = task["spec"]
            return "unavailable", f"no single fixture logits row for {spec['family_id']}:{spec['variant']}"
        return "ready", None

    def execute_fixture(self, task: dict, context: dict) -> dict:
        doc, row = self._row(task, context)
        require(doc is not None and row is not None, "fixture_missing", "preflight was not ready for this task")
        require(doc.get("schema_version") == FIXTURE_SCHEMA and doc.get("synthetic") is True
                and doc.get("extraction") == EXTRACTION, "fixture_identity",
                f"{FIXTURE_FILE} must be a synthetic {FIXTURE_SCHEMA} file")
        spec = task["spec"]
        logits = row.get("logits")
        size = doc.get("vocabulary_size")
        require(integer(size, 1) and isinstance(logits, list) and len(logits) == size, "vocabulary_size",
                "Each row must hold one logit per vocabulary entry; a top-k list cannot give full-vocabulary values")
        targets = []
        for target in _family(context["protocol"], spec["family_id"])["targets"]:
            # rank_target refuses non-finite logits (invalid_logits) and targets outside the vocabulary.
            scored = rank_target(logits, {"id": target["id"], "role": target.get("role", "answer"),
                                          "token_ids": target["token_ids"]}, set(), [1])
            targets.append({key: scored[key] for key in (
                "target_id", "role", "token_id", "matching", "sequence_status", "full_vocab_probability",
                "raw_rank")})
        return {
            "kind": PAYLOAD_KIND, "synthetic": True,
            "family_id": spec["family_id"], "variant": spec["variant"],
            "input": {"prompt_sha256": row.get("prompt_sha256"), "token_sha256": row.get("token_sha256")},
            "model": {"hf_id": doc.get("model", {}).get("hf_id"), "revision": doc.get("model", {}).get("revision")},
            "extraction": EXTRACTION,
            "probability_kind": "full_vocabulary_softmax_of_fixture_logits",
            "rank_tie_rule": "descending_logit_then_ascending_token_id",
            "vocabulary_size": size, "logits_sha256": digest(logits),
            "targets": targets,
            "fixture": {"file": FIXTURE_FILE, "sha256": self._load(context)["sha256"]},
            "limitations": ["synthetic_not_measurement", "first_target_token_only_no_sequence_scoring"],
        }

    def validate_payload(self, payload: dict, task: dict, context: dict) -> None:
        spec = task["spec"]
        require(isinstance(payload, dict) and payload.get("kind") == PAYLOAD_KIND, "payload_kind",
                f"expected {PAYLOAD_KIND}")
        require(payload.get("synthetic") is True, "synthetic_label", "a fixture payload must say synthetic")
        require(payload.get("family_id") == spec["family_id"] and payload.get("variant") == spec["variant"]
                and payload.get("input") == spec["input"], "row_misalignment",
                "The fixture row's family, variant or input hashes differ from the planned task")
        require(payload.get("model") == {"hf_id": spec["model"]["hf_id"], "revision": spec["model"]["revision"]},
                "model_mismatch", "The fixture was supplied for another model or revision")
        size = payload.get("vocabulary_size")
        require(integer(size, 1), "vocabulary_size", "vocabulary_size must be a positive integer")
        wanted = [t["id"] for t in _family(context["protocol"], spec["family_id"])["targets"]]
        rows = payload.get("targets")
        require(isinstance(rows, list) and [r.get("target_id") for r in rows] == wanted, "missing_targets",
                "The payload must score every protocol target once, in protocol order")
        for row in rows:
            probability = row.get("full_vocab_probability")
            require(type(probability) is float and math.isfinite(probability) and 0.0 < probability <= 1.0,
                    "invalid_probability", f"{row.get('target_id')}: probability must be finite and in (0, 1]")
            require(integer(row.get("raw_rank"), 1) and row["raw_rank"] <= size, "invalid_rank",
                    f"{row.get('target_id')}: raw_rank must lie in 1..vocabulary_size")


ADAPTER = BehaviorFixtureAdapter()
