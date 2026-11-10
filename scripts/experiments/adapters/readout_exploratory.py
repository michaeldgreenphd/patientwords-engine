"""Payload kind ``lens_readout_report/1``: one task's slice of an exploratory v1 report.

This adapter adds no lens arithmetic. It calls ``scripts.exploratory_methods.build_report`` on a synthetic
specification and packet (``readout_spec.json`` and ``readout_packet.json`` in the fixtures directory) and keeps
the rows of one case, one variant and one method. The v1 contract is unchanged: the same string
``patientwords.exploratory/1``, the same validator, the same refusals.

Three limits follow from v1 and are kept visible:

* A v1 packet must hold ``logit_lens``, ``j_lens`` and ``jpp`` rows together. This adapter files
  ``logit_lens`` rows only. The synthetic ``j_lens`` and ``jpp`` rows in the packet are never filed.
* A v1 report embeds its whole specification, prompt text included, under ``provenance``. The payload carries
  hashes only and never copies that block.
* Ranks and probabilities are for the first target token; ``exact_sequence_score`` stays null.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from scripts.exploratory_methods import SCHEMA as V1_SCHEMA
from scripts.exploratory_methods import build_report
from scripts.experiments.common import FIXTURE_BACKEND, FIXTURE_MODEL, digest, integer, require, sha256_bytes

SPEC_FILE = "readout_spec.json"
PACKET_FILE = "readout_packet.json"
PAYLOAD_KIND = "lens_readout_report/1"
VARIANT_MAP_KEY = "experiment_variant_map"
SCORE_KEYS = ("target_id", "role", "token_id", "matching", "sequence_status", "exact_sequence_score", "raw_rank",
              "filtered_rank", "excluded_candidate", "full_vocab_probability", "top_k")


class ReadoutExploratoryAdapter:
    method_ids: tuple[str, ...] = ("logit_lens",)
    payload_kinds: tuple[str, ...] = (PAYLOAD_KIND,)

    def capabilities(self) -> list[dict]:
        return [{
            "model": dict(FIXTURE_MODEL), "method": "logit_lens", "backend": FIXTURE_BACKEND,
            "dtype": None, "artifact": None, "status": "runtime_verified_offline_fixture",
            "evidence": [{"source": "tests/test_experiments_core.py", "date": "2026-11-10"}],
            "status_note": "A synthetic packet joined by scripts/exploratory_methods.build_report. No lens "
                           "arithmetic runs; the packet supplies the readout logits.",
        }]

    def _raw(self, context: dict) -> dict[str, Any] | None:
        """The bytes and SHA-256 of both fixture files, read once per run. None when either file is absent.
        Parsing and hashing use these same bytes, so a recorded hash is the hash of what was read."""
        directory = Path(context["fixtures_dir"])
        cache = context.setdefault("_cache", {})
        key = ("readout_files", str(directory))
        if key not in cache:
            paths = {name: directory / name for name in (SPEC_FILE, PACKET_FILE)}
            if not all(path.is_file() for path in paths.values()):
                cache[key] = None
            else:
                data = {name: path.read_bytes() for name, path in paths.items()}
                cache[key] = {"bytes": data, "files": {name: sha256_bytes(data[name]) for name in sorted(data)}}
        return cache[key]

    def input_identity(self, task: dict, context: dict) -> str | None:
        """Digest of the two fixture files' bytes: the inputs of a readout task outside its spec."""
        raw = self._raw(context)
        return digest({"adapter_inputs": raw["files"]}) if raw is not None else None

    def _load(self, context: dict) -> dict[str, Any] | None:
        """Spec, packet and the v1 report, built once per fixtures directory. None when a file is absent."""
        directory = Path(context["fixtures_dir"])
        cache = context.setdefault("_cache", {})
        key = ("readout", str(directory))
        if key not in cache:
            raw = self._raw(context)
            if raw is None:
                cache[key] = None
            else:
                spec, packet = (json.loads(raw["bytes"][name].decode("utf-8")) for name in (SPEC_FILE, PACKET_FILE))
                cache[key] = {"spec": spec, "report": build_report(spec, packet), "files": dict(raw["files"])}
        return cache[key]

    @staticmethod
    def _v1_names(loaded: dict[str, Any], task: dict) -> tuple[dict[str, Any] | None, str | None]:
        spec = task["spec"]
        case = next((c for c in loaded["spec"]["cases"] if c["id"] == spec["family_id"]), None)
        v1_variant = loaded["spec"].get(VARIANT_MAP_KEY, {}).get(spec["variant"])
        if case is None or v1_variant not in case["variants"]:
            return None, None
        return case, v1_variant

    def preflight(self, task: dict, context: dict) -> tuple[str, str | None]:
        directory = Path(context["fixtures_dir"])
        raw = self._raw(context)
        if raw is None:
            return "unavailable", f"{SPEC_FILE} and {PACKET_FILE} are not both present in {directory}"
        try:
            spec_doc = json.loads(raw["bytes"][SPEC_FILE].decode("utf-8"))
            case = next((c for c in spec_doc["cases"] if c["id"] == task["spec"]["family_id"]), None)
            v1_variant = spec_doc.get(VARIANT_MAP_KEY, {}).get(task["spec"]["variant"])
        except (KeyError, TypeError, ValueError) as exc:
            return "unavailable", f"{SPEC_FILE} is not a readable v1 specification: {type(exc).__name__}"
        if case is None or v1_variant not in case.get("variants", {}):
            return "unavailable", (f"the v1 specification has no case and variant for "
                                   f"{task['spec']['family_id']}:{task['spec']['variant']}")
        return "ready", None

    def execute_fixture(self, task: dict, context: dict) -> dict:
        loaded = self._load(context)
        require(loaded is not None, "fixture_missing", "preflight was not ready for this task")
        spec, method = task["spec"], task["spec"]["method"]
        case, v1_variant = self._v1_names(loaded, task)
        require(case is not None, "fixture_missing", "preflight was not ready for this task")
        v1_spec, report = loaded["spec"], loaded["report"]
        entry = case["variants"][v1_variant]
        last = len(entry["token_ids"]) - 1
        wanted_positions = [last] if method.get("positions") == "last" else list(range(last + 1))
        readouts = [
            {"layer": row["layer"], "position": row["position"],
             "scores": [{key: score[key] for key in SCORE_KEYS} for score in row["scores"]]}
            for row in report["readouts"]
            if row["case_id"] == case["id"] and row["variant"] == v1_variant and row["method"] == method["id"]
            and row["layer"] in method["layers"] and row["position"] in wanted_positions]
        readouts.sort(key=lambda row: (row["layer"], row["position"]))
        return {
            "kind": PAYLOAD_KIND, "synthetic": True,
            "family_id": spec["family_id"], "variant": spec["variant"],
            "method": method["id"], "v1_case_id": case["id"], "v1_variant": v1_variant,
            "input": {"prompt_sha256": entry["prompt_sha256"], "token_sha256": entry["token_sha256"]},
            "model": {"hf_id": v1_spec["model"]["id"], "revision": v1_spec["model"]["revision"]},
            "source_report": {
                "schema_version": report["schema_version"], "execution_status": report["execution_status"],
                "spec_sha256": report["spec_sha256"], "packet_sha256": report["packet_sha256"],
                "digest_convention": "scripts.exploratory_methods.digest",
                "files": loaded["files"], "limitations": report["limitations"],
            },
            "capture_site": v1_spec["capture_site"], "layer_index_base": v1_spec["layer_index_base"],
            "output_head": v1_spec["final_norm"],
            "probability_kind": "lens_readout_softmax",
            "rank_tie_rule": report["rank_tie_rule"],
            "filter": {"id": v1_spec["vocabulary_filter"]["id"],
                       "excluded_token_ids": sorted(x["token_id"] for x in v1_spec["vocabulary_filter"]["excluded"])},
            "top_k": list(v1_spec["top_k"]),
            "layers": sorted(method["layers"]), "positions": wanted_positions, "last_position": last,
            "readouts": readouts,
            "limitations": ["synthetic_not_measurement", "first_target_token_only_no_sequence_scoring",
                            "v1_packet_also_holds_j_lens_and_jpp_rows_not_filed_here"],
        }

    def validate_payload(self, payload: dict, task: dict, context: dict) -> None:
        spec, method = task["spec"], task["spec"]["method"]
        require(isinstance(payload, dict) and payload.get("kind") == PAYLOAD_KIND, "payload_kind",
                f"expected {PAYLOAD_KIND}")
        require(payload.get("synthetic") is True
                and payload.get("source_report", {}).get("schema_version") == V1_SCHEMA
                and payload["source_report"].get("execution_status") == "synthetic", "synthetic_label",
                "a v1 report is synthetic evidence only")
        require(payload.get("method") == method["id"] and payload.get("family_id") == spec["family_id"]
                and payload.get("variant") == spec["variant"] and payload.get("input") == spec["input"],
                "row_misalignment",
                "The v1 case's method, family, variant or input hashes differ from the planned task")
        require(payload.get("model") == {"hf_id": spec["model"]["hf_id"], "revision": spec["model"]["revision"]},
                "model_mismatch", "The v1 specification names another model or revision")
        require(payload.get("capture_site") == method.get("capture_site") and payload.get("layer_index_base") == 0,
                "capture_mismatch", "capture site or layer index base differs from the planned method")
        positions = payload.get("positions")
        require(isinstance(positions, list) and bool(positions) and all(integer(p) for p in positions),
                "readout_grid", "positions must be a non-empty list of integers")
        expected = [(layer, position) for layer in sorted(method["layers"]) for position in positions]
        rows = payload.get("readouts")
        require(isinstance(rows, list) and [(r.get("layer"), r.get("position")) for r in rows] == expected,
                "readout_grid", "Every planned layer and position must be present exactly once, in order")
        family = next(f for f in context["protocol"]["case_families"] if f["family_id"] == spec["family_id"])
        wanted = sorted((t["id"], t.get("role", "answer"), t["token_ids"][0]) for t in family["targets"])
        excluded = set(payload.get("filter", {}).get("excluded_token_ids", []))
        for row in rows:
            # The v1 specification is a file outside the protocol. Its targets must be the protocol's own:
            # the same ids, roles and first token ids, each once. The detail names ids and token ids only.
            got = sorted((score.get("target_id"), score.get("role"), score.get("token_id"))
                         for score in row["scores"])
            require(got == wanted, "missing_targets",
                    f"layer {row['layer']} position {row['position']}: the readout scores (target_id, role, "
                    f"token_id) {got} are not the protocol family's targets {wanted}")
            for score in row["scores"]:
                probability = score.get("full_vocab_probability")
                require(type(probability) is float and math.isfinite(probability) and 0.0 < probability <= 1.0,
                        "invalid_probability", "readout probability must be finite and in (0, 1]")
                require(integer(score.get("raw_rank"), 1), "invalid_rank", "raw_rank must be a positive integer")
                is_excluded = score.get("token_id") in excluded
                require(score.get("excluded_candidate") is is_excluded
                        and (score.get("filtered_rank") is None) == is_excluded
                        and (is_excluded or integer(score["filtered_rank"], 1)), "invalid_rank",
                        "filtered_rank is null exactly when the target token is in the exclusion list")
                require(is_excluded or score["filtered_rank"] <= score["raw_rank"], "invalid_rank",
                        "a filtered rank cannot be worse than the raw rank")


ADAPTER = ReadoutExploratoryAdapter()
