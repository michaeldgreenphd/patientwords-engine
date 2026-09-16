"""Run manifest assembly, validation and hash chain
(docs/framework/petri_run_manifest.schema.json, draft 0.2; design memo section 9).

The manifest is the closed execution sidecar: everything Petri-specific lives
here, the transcript stays generic. Two digests:

- `identity_sha256`: the manifest with the chain block removed and the
  record-dependent artifact digests blanked. Transcript records carry it in
  `provenance.run_manifest.sha256`; it cannot cover the transcript digest
  because the transcript carries it.
- `manifest_sha256`: the whole manifest with that one field blanked.
  `prev_sha256` links each run's manifest to the previous one under the same
  data directory, so the family is append-only and any rewrite is detectable.
"""
from __future__ import annotations

from pathlib import Path

from .framework import MANIFEST_SCHEMA, canonical_json, load_json, sha256_text, validate_with_refs, write_json

MANIFEST_VERSION = "0.2"
CHAIN_FILE = "manifests.chain"           # one manifest digest per line, append-only, per data directory
RECORD_DEPENDENT_DIGESTS = ("transcripts_sha256", "rule_outcomes_sha256", "judgments_sha256")


def identity_digest(manifest: dict) -> str:
    body = {k: v for k, v in manifest.items() if k != "chain"}
    artifacts = dict(body.get("artifacts") or {})
    for key in RECORD_DEPENDENT_DIGESTS:
        if key in artifacts:
            artifacts[key] = "" if artifacts[key] is not None else None
    body["artifacts"] = artifacts
    return sha256_text(canonical_json(body))


def manifest_digest(manifest: dict) -> str:
    body = dict(manifest)
    chain = dict(body.get("chain") or {})
    chain["manifest_sha256"] = ""
    body["chain"] = chain
    return sha256_text(canonical_json(body))


def seal_manifest(manifest: dict, prev_sha256: str | None) -> dict:
    """Return the manifest with its chain block completed."""
    out = dict(manifest)
    out["chain"] = {"prev_sha256": prev_sha256, "identity_sha256": identity_digest(out), "manifest_sha256": ""}
    out["chain"]["manifest_sha256"] = manifest_digest(out)
    return out


def manifest_problems(manifest: dict, schema: dict | None = None) -> list[str]:
    schema = schema or load_json(MANIFEST_SCHEMA)
    problems = validate_with_refs(manifest, schema)
    chain = manifest.get("chain") or {}
    if chain.get("identity_sha256") != identity_digest(manifest):
        problems.append("chain.identity_sha256 does not match the manifest body")
    if chain.get("manifest_sha256") != manifest_digest(manifest):
        problems.append("chain.manifest_sha256 does not match the manifest body")
    return problems


def chain_head(data_dir: Path) -> str | None:
    path = data_dir / CHAIN_FILE
    if not path.is_file():
        return None
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines[-1].split()[-1] if lines else None


def append_chain(data_dir: Path, manifest: dict, manifest_path: Path) -> None:
    path = data_dir / CHAIN_FILE
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{manifest_path.relative_to(data_dir).as_posix()} {manifest['chain']['manifest_sha256']}\n")


def verify_chain(data_dir: Path) -> tuple[bool, str]:
    """Every manifest the chain file names exists, digests to its recorded
    value, and links to the previous line."""
    path = data_dir / CHAIN_FILE
    if not path.is_file():
        return True, "no chain file (no manifests yet)"
    prev: str | None = None
    for n, line in enumerate(ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()):
        rel, digest = line.rsplit(" ", 1)
        mpath = data_dir / rel
        if not mpath.is_file():
            return False, f"line {n + 1}: {rel} is missing"
        manifest = load_json(mpath)
        if manifest_digest(manifest) != digest or manifest["chain"]["manifest_sha256"] != digest:
            return False, f"line {n + 1}: {rel} does not digest to {digest}"
        if manifest["chain"]["prev_sha256"] != prev:
            return False, f"line {n + 1}: {rel} links to {manifest['chain']['prev_sha256']!r}, expected {prev!r}"
        prev = digest
    return True, f"chain intact ({prev})"


def write_manifest(path: Path, manifest: dict) -> None:
    write_json(path, manifest)
