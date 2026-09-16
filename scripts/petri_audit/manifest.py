"""Run manifest assembly, validation and hash chain
(docs/framework/petri_run_manifest.schema.json, draft 0.2; design memo section 9).

The manifest is the closed execution sidecar: everything Petri-specific lives
here, the transcript stays generic. Two digests:

- `identity_sha256`: the manifest with the chain block removed and the
  record-dependent artifact fields blanked (the transcript, rule-outcome and
  judgment digests, the judgment path and the judge-of-record block).
  Transcript records carry it in `provenance.run_manifest.sha256`; it cannot
  cover the transcript digest because the transcript carries it, and it does
  not cover the judge stage because judging happens after the records are
  bound.
- `manifest_sha256`: the whole manifest with that one field blanked.
  `prev_sha256` links each run's manifest to the previous one under the same
  data directory, so the family is append-only and any rewrite is detectable.

One reseal is legitimate: `bind_judgments` fills the judgment fields after the
judge of record runs, keeps the identity digest (asserted), and replaces the
chain line of the manifest it reseals, which must still be the chain head.
`verify_chain` checks every manifest's digest and link and, since the first
Codex review of the lane (PR #26), also that every artifact a manifest names
exists and digests to its recorded value, so a judgment file altered or
removed after binding is detected.
"""
from __future__ import annotations

from pathlib import Path

from .framework import MANIFEST_SCHEMA, canonical_json, load_json, sha256_file, sha256_text, validate_with_refs, write_json

MANIFEST_VERSION = "0.2"
CHAIN_FILE = "manifests.chain"           # one manifest digest per line, append-only, per data directory
RECORD_DEPENDENT_FIELDS = ("transcripts_sha256", "rule_outcomes_sha256", "judgments_path", "judgments_sha256",
                           "judge_of_record")
ARTIFACT_FAMILIES = ("sanitised_log", "transcripts", "rule_outcomes", "judgments")


def identity_digest(manifest: dict) -> str:
    body = {k: v for k, v in manifest.items() if k != "chain"}
    artifacts = dict(body.get("artifacts") or {})
    for key in RECORD_DEPENDENT_FIELDS:
        if key in artifacts:
            artifacts[key] = None
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


def artifact_problems(manifest: dict, data_dir: Path) -> list[str]:
    """Every artifact the manifest names (relative to the runs directory)
    exists and digests to its recorded value; a null path is one not yet
    written (judgments before judging)."""
    problems: list[str] = []
    artifacts = manifest.get("artifacts") or {}
    pairs = [(artifacts.get(f"{fam}_path"), artifacts.get(f"{fam}_sha256"), fam) for fam in ARTIFACT_FAMILIES]
    judge = artifacts.get("judge_of_record")
    if isinstance(judge, dict):
        pairs.append((judge.get("report_path"), judge.get("report_sha256"), "judge_of_record.report"))
    for rel, digest, fam in pairs:
        if rel is None:
            continue
        fpath = data_dir / rel
        if not fpath.is_file():
            problems.append(f"{fam}: {rel} is missing")
        elif sha256_file(fpath) != digest:
            problems.append(f"{fam}: {rel} does not digest to its recorded value")
    return problems


def verify_chain(data_dir: Path) -> tuple[bool, str]:
    """Every manifest the chain file names exists, digests to its recorded
    value, links to the previous line, and names only artifacts that exist
    and digest to their recorded values."""
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
        problems = artifact_problems(manifest, data_dir)
        if problems:
            return False, f"line {n + 1}: {rel}: " + "; ".join(problems)
        prev = digest
    return True, f"chain intact ({prev})"


def replace_chain_head(data_dir: Path, manifest_path: Path, old_digest: str, new_digest: str) -> None:
    """Rewrite the chain's last line for a manifest being resealed. Only the
    head may be resealed: a later manifest links to this one's digest, and
    changing an interior line would break every successor."""
    path = data_dir / CHAIN_FILE
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rel = manifest_path.resolve().relative_to(data_dir.resolve()).as_posix()
    if not lines or lines[-1] != f"{rel} {old_digest}":
        raise ValueError(f"{rel} is not the chain head; only the head manifest can be resealed")
    lines[-1] = f"{rel} {new_digest}"
    path.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")


def bind_judgments(run_dir: Path, *, judgments_path: Path, report_path: Path, judge_of_record: dict) -> dict:
    """After the judge of record has written `judgments.jsonl` and its report,
    record both in the run's manifest (path, digest, provenance), reseal it
    with the same `prev_sha256`, assert the identity digest is unchanged (so
    every transcript bound to it stays bound), validate, write, and replace
    the chain head line. Raises rather than writing anything on any failure."""
    run_dir = Path(run_dir)
    data_dir = run_dir.parent
    manifest_path = run_dir / "manifest.json"
    manifest = load_json(manifest_path)
    before_identity = manifest["chain"]["identity_sha256"]
    before_digest = manifest["chain"]["manifest_sha256"]

    def rel(p: Path) -> str:
        return p.resolve().relative_to(data_dir.resolve()).as_posix()

    manifest["artifacts"]["judgments_path"] = rel(judgments_path)
    manifest["artifacts"]["judgments_sha256"] = sha256_file(judgments_path)
    manifest["artifacts"]["judge_of_record"] = {**judge_of_record, "report_path": rel(report_path),
                                                "report_sha256": sha256_file(report_path)}
    sealed = seal_manifest(manifest, manifest["chain"]["prev_sha256"])
    if sealed["chain"]["identity_sha256"] != before_identity:
        raise ValueError("binding the judgments changed the run's identity digest; nothing written")
    problems = manifest_problems(sealed)
    if problems:
        raise ValueError("manifest does not validate after binding the judgments: " + "; ".join(problems[:8]))
    replace_chain_head(data_dir, manifest_path, before_digest, sealed["chain"]["manifest_sha256"])
    write_manifest(manifest_path, sealed)
    return sealed


def write_manifest(path: Path, manifest: dict) -> None:
    write_json(path, manifest)
