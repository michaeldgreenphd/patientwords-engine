"""Small test SDK: generated response models plus schema-validated HTTP transport.

The OpenAPI resource and its external draft-07 schema are the authority. The
transport is handwritten; generated.py is not. No endpoint or field definitions
are copied here. No proxy, redirect, or non-loopback request is allowed.
"""
from __future__ import annotations

import http.client
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft7Validator

from .generated import SimulatedScenarios

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def contract() -> tuple[str, dict[str, Any]]:
    """Resolve only the declared, local response schema; never fetch references."""
    api = json.loads((CONTRACTS / "simulated_scenarios.openapi.json").read_text())
    resource, operations = next(iter(api["paths"].items()))
    ref = operations["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    path = (CONTRACTS / ref).resolve()
    if path.parent != CONTRACTS.resolve():
        raise ValueError("response schema must be a local contract file")
    schema = json.loads(path.read_text())
    Draft7Validator.check_schema(schema)
    return resource, schema


def validate(payload: Any) -> dict[str, Any]:
    """Validate raw decoded response, then exercise the generated response model."""
    _, schema = contract()
    Draft7Validator(schema).validate(payload)
    SimulatedScenarios.model_validate(payload)
    return payload


def fetch(base: str) -> dict[str, Any]:
    """GET the declared static resource, preserving bytes until JSON validation."""
    url = urlsplit(base)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.username or url.query:
        raise ValueError("test client requires an explicit http://127.0.0.1:PORT base")
    resource, _ = contract()
    connection = http.client.HTTPConnection("127.0.0.1", url.port, timeout=10)
    try:
        connection.request("GET", url.path.rstrip("/") + resource, headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"HTTP status {response.status}, expected 200")
        if response.getheader("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("HTTP response is not application/json")
        raw = response.read()
    finally:
        connection.close()

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON numeric constant: {value}")

    return validate(json.loads(raw, parse_constant=reject_constant))
