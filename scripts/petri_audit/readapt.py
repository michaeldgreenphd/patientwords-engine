"""Re-adaptation of a landed run's raw log (petri-audit `mode: readapt`).

A paid run whose target calls completed but whose adaptation failed leaves a
cost sidecar under `data/petri/runs/<stem>/` and its raw `.eval` in a 90-day
workflow artifact (`petri-audit-raw-eval-<run id>-1`), and nothing else. Mode
readapt downloads that artifact in CI, adapts it under the current sanitiser
into the ORIGINAL run directory, so the outputs sit beside the sidecar that
already booked the target spend, and then runs the judge of record as mode run
does. It makes no target call.

This module holds the checks and the provenance record, and imports nothing
from the harness, so the whole contract is testable under the engine's
ordinary 3.11 environment. Every check refuses by name:

- the source artifact must be exactly the one named for the source run, not
  expired, and listed under that run (`select_source_artifact`);
- the source run directory must hold the landed target cost sidecar and
  nothing else, and the manifest chain must not name it (`run_dir_problems`):
  a landed run is never rewritten, and its sidecar is never rewritten either;
- the sidecar must be the fallback writer's (`spend_report_reason`), carry the
  source fire's nonce, and name the `.eval` and eval id it priced
  (`source_report`), so the downloaded file is bound to the spend it booked;
- the log's own record of what ran (target, seeds, epochs, token limit,
  log_model_api) must equal what the readapt fire states (`log_problems`).

`provenance_block` is what the manifest records as `readapt`
(docs/framework/petri_run_manifest.schema.json): the source workflow run, the
artifact's id and digest, the landed sidecar's digest (which `verify-run` and
`verify-chain` check, so a later rewrite of it is detected), and the
re-adapting workflow run, attempt, commit and nonce.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .framework import load_json, sha256_file
from .manifest import CHAIN_FILE

MODE = "readapt"
ARTIFACT_PREFIX = "petri-audit-raw-eval-"
_RUN_ID = re.compile(r"^[0-9]+$")
# the files adaptation writes; any of them in the source directory means it was adapted already
ADAPTED_FILES = ("manifest.json", "transcripts.jsonl", "rule_outcomes.jsonl", "sanitised_log.json", "judgments.jsonl",
                 "analysis_rows.jsonl")


class ReadaptError(ValueError):
    """A named refusal: the re-adaptation does not start (or stops before writing anything)."""


def check_run_id(value: Any, what: str = "source_run_id") -> str:
    """A GitHub workflow run id: ASCII digits only (`str.isdigit` also admits
    superscripts and other Unicode digits, which no run id carries)."""
    text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    if not _RUN_ID.fullmatch(text):
        raise ReadaptError(f"{what} must be a numeric workflow run id, got {value!r}")
    return text


def source_stem(source_run_id: Any) -> str:
    """The source run's directory name. Mode run refuses an Actions-tab re-run,
    so a paid run's only attempt is 1 and its stem is `run_<id>_1`."""
    return f"run_{check_run_id(source_run_id)}_1"


def artifact_name(source_run_id: Any) -> str:
    """The name the workflow's raw-log upload gives the source run's artifact."""
    return f"{ARTIFACT_PREFIX}{check_run_id(source_run_id)}-1"


def target_report_name(stem: str) -> str:
    return f"{stem}.report.json"


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def select_source_artifact(listing: Any, source_run_id: Any, now: datetime | None = None) -> dict:
    """The source run's raw-log artifact from the REST listing
    `GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts`, or a named
    refusal: the listing is incomplete, no artifact (or more than one) carries
    the exact name, it has expired, its `workflow_run.id` is another run's, or
    it records no id. The digest is recorded as the API gives it and as null
    when the API gives none; it is never invented."""
    run_id = check_run_id(source_run_id)
    name = artifact_name(run_id)
    if not isinstance(listing, dict) or not isinstance(listing.get("artifacts"), list):
        raise ReadaptError(f"the artifact listing for run {run_id} is not an object with an `artifacts` list")
    artifacts = [a for a in listing["artifacts"] if isinstance(a, dict)]
    total = listing.get("total_count")
    if isinstance(total, int) and not isinstance(total, bool) and total > len(artifacts):
        raise ReadaptError(f"the artifact listing for run {run_id} holds {len(artifacts)} of {total} artifacts; an "
                           "incomplete listing cannot establish which artifact is the source log")
    matches = [a for a in artifacts if a.get("name") == name]
    if not matches:
        found = sorted(str(a.get("name")) for a in artifacts)
        raise ReadaptError(f"run {run_id} has no artifact named {name} (it lists {found or 'none'}); the raw log was "
                           "never uploaded, or the run id is not the source run's")
    if len(matches) > 1:
        raise ReadaptError(f"run {run_id} lists {len(matches)} artifacts named {name}; the source log is ambiguous")
    art = matches[0]
    if art.get("expired") is not False:
        raise ReadaptError(f"artifact {name} of run {run_id} is expired (expired={art.get('expired')!r}, expires_at "
                           f"{art.get('expires_at')!r}); the raw log is gone and the run cannot be re-adapted")
    expires = _parse_utc(art.get("expires_at"))
    moment = now or datetime.now(timezone.utc)
    if expires is not None and expires <= moment:
        raise ReadaptError(f"artifact {name} of run {run_id} expired at {art.get('expires_at')}; the raw log is gone")
    workflow_run = art.get("workflow_run")
    listed_run = workflow_run.get("id") if isinstance(workflow_run, dict) else None
    if listed_run is not None and str(listed_run) != run_id:
        raise ReadaptError(f"artifact {name} is listed under workflow run {listed_run}, not the source run {run_id}")
    art_id = art.get("id")
    if not isinstance(art_id, int) or isinstance(art_id, bool) or art_id < 1:
        raise ReadaptError(f"artifact {name} of run {run_id} records no usable id ({art_id!r})")
    digest = art.get("digest")
    size = art.get("size_in_bytes")
    return {"id": art_id, "name": name,
            "digest": digest if isinstance(digest, str) and digest else None,
            "size_in_bytes": size if isinstance(size, int) and not isinstance(size, bool) else None,
            "created_at": art.get("created_at") if isinstance(art.get("created_at"), str) else None,
            "expires_at": art.get("expires_at") if isinstance(art.get("expires_at"), str) else None}


def run_dir_problems(runs_dir: Path | str, stem: str) -> list[str]:
    """Why `<runs_dir>/<stem>` cannot receive a re-adaptation: it must exist and
    hold exactly the landed target cost sidecar, and the chain file must not
    name its manifest (a manifest removed after it was chained is a rewrite
    too). Empty when the directory is the state a run whose adaptation failed
    leaves behind."""
    runs_dir = Path(runs_dir)
    run_dir = runs_dir / stem
    if not run_dir.is_dir():
        return [f"{stem}: no such run directory under {runs_dir}; a readapt recovers a run whose target spend already "
                "landed, and this one has no landed sidecar"]
    problems: list[str] = []
    names = sorted(p.name for p in run_dir.iterdir())
    report = target_report_name(stem)
    if report not in names:
        problems.append(f"{stem}: the landed target cost sidecar {report} is missing, so the source run's target spend "
                        "is not booked and a readapt (which books none) would leave it unbooked")
    adapted = [n for n in names if n in ADAPTED_FILES]
    if adapted:
        problems.append(f"{stem}: already holds adapted outputs ({', '.join(adapted)}); a landed run is never rewritten")
    other = [n for n in names if n != report and n not in ADAPTED_FILES]
    if other:
        problems.append(f"{stem}: holds files other than the landed target sidecar ({', '.join(other)}); a readapt "
                        "writes only into the state a failed adaptation leaves")
    chain = runs_dir / CHAIN_FILE
    if chain.is_file():
        rel = f"{stem}/manifest.json"
        if any(ln.strip().rsplit(" ", 1)[0] == rel for ln in chain.read_text(encoding="utf-8").splitlines() if ln.strip()):
            problems.append(f"{stem}: {CHAIN_FILE} already names {rel}; the run was adapted and chained once, and a second "
                            "line for the same path would replace a stored measurement")
    return problems


def source_report(runs_dir: Path | str, stem: str) -> dict:
    """The landed target sidecar of the source run, as the readapt binds it:
    its path (relative to the runs directory, as manifests record paths),
    digest, the source fire's nonce and the log it priced. Refuses a sidecar
    that is not the fallback writer's (an adapted run wrote its own report and
    is refused by `run_dir_problems` too), carries no nonce, or does not name
    the `.eval` and the eval id."""
    path = Path(runs_dir) / stem / target_report_name(stem)
    if not path.is_file():
        raise ReadaptError(f"{stem}: the landed target cost sidecar {path.name} is missing")
    try:
        report = load_json(path)
    except (OSError, ValueError) as exc:
        raise ReadaptError(f"{stem}: {path.name} does not parse ({exc})") from None
    if not isinstance(report, dict):
        raise ReadaptError(f"{stem}: {path.name} holds a {type(report).__name__}, not an object")
    missing = [k for k in ("journal_nonce", "eval_id", "eval_log", "spend_report_reason")
               if not isinstance(report.get(k), str) or not report.get(k)]
    if missing:
        raise ReadaptError(f"{stem}: {path.name} records no {', '.join(missing)}; a readapt needs the fallback sidecar "
                           "of an attempted run, which records the fire's nonce, the eval id and the .eval it priced")
    return {"path": f"{stem}/{path.name}", "sha256": sha256_file(path), "journal_nonce": report["journal_nonce"],
            "eval_id": report["eval_id"], "eval_log": report["eval_log"]}


def eval_file_problems(eval_path: Path | str, expected_name: str) -> list[str]:
    """The downloaded log is the one the landed sidecar priced: it exists, it
    carries the file name the sidecar records, and it is the only `.eval` in
    its directory (the artifact held the source run's log directory)."""
    eval_path = Path(eval_path)
    problems: list[str] = []
    if not eval_path.is_file():
        return [f"{eval_path}: the downloaded raw log is missing"]
    if eval_path.name != expected_name:
        problems.append(f"the downloaded raw log is {eval_path.name}, but the landed sidecar priced {expected_name}; "
                        "this is not the source run's log")
    others = sorted(p.name for p in eval_path.parent.glob("*.eval") if p.name != eval_path.name)
    if others:
        problems.append(f"the source artifact held more than one .eval ({eval_path.name}, {', '.join(others)}); "
                        "the log to re-adapt is ambiguous")
    return problems


def expected_from_params(params: dict, seed_ids: list[str]) -> dict:
    """What the readapt fire states the source run executed, in the form the
    log records it. `params` are the params job's resolved outputs (strings);
    `seed_ids` the selection those params make from the seed file."""
    try:
        epochs, token_limit = int(str(params["epochs"])), int(str(params["token_limit"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ReadaptError(f"the readapt params carry no usable epochs/token_limit ({exc})") from None
    log_model_api = str(params.get("log_model_api", "")).strip().lower()
    if log_model_api not in ("true", "false"):
        raise ReadaptError(f"the readapt params carry log_model_api {params.get('log_model_api')!r}, not true or false")
    target = params.get("target")
    if not isinstance(target, str) or not target:
        raise ReadaptError("the readapt params name no target")
    return {"target": target, "seed_ids": list(seed_ids), "epochs": epochs, "token_limit": token_limit,
            "log_model_api": log_model_api == "true"}


def log_problems(expected: dict, observed: dict) -> list[str]:
    """Each way the log's record of what ran differs from what the readapt
    fire states: the eval id the landed sidecar priced, the target, the seed
    selection (as a set: the run records it in the file's order), the epochs,
    the per-sample token limit and log_model_api. A value the log does not
    record is a problem, never a match."""
    problems: list[str] = []
    for key in ("eval_id", "target", "epochs", "token_limit", "log_model_api"):
        if key not in expected:
            continue
        mine, theirs = expected[key], observed.get(key)
        if theirs is None:
            problems.append(f"the log records no {key}; it cannot be shown to be the run this readapt names")
        elif mine != theirs:
            problems.append(f"{key}: the log records {theirs!r}, the readapt states {mine!r}")
    if "seed_ids" in expected:
        theirs = observed.get("seed_ids")
        if not isinstance(theirs, list):
            problems.append("the log records no seed selection; it cannot be shown to be the run this readapt names")
        elif sorted(theirs) != sorted(expected["seed_ids"]):
            problems.append(f"seed_ids: the log records {sorted(theirs)}, the readapt selects {sorted(expected['seed_ids'])}")
    return problems


def plan(*, params: dict, listing: Any, runs_dir: Path | str, seed_ids: list[str], journal_entries: list[dict],
         readapt_run_id: Any, readapt_run_attempt: Any, readapt_commit: str, now: datetime | None = None) -> dict:
    """Everything the adapt step needs to re-adapt the source run, established
    before the download: the source run and stem, the artifact, the landed
    sidecar (digest, nonce, log name), the digest of the trigger content the
    source fire journaled, what the log must record, and the re-adapting run.
    Raises ReadaptError naming every problem found with the run directory."""
    if str(params.get("mode", "")).strip().lower() != MODE:
        raise ReadaptError(f"readapt planning needs mode {MODE}, got {params.get('mode')!r}")
    source_run_id = check_run_id(params.get("source_run_id"))
    stem = source_stem(source_run_id)
    problems = run_dir_problems(runs_dir, stem)
    if problems:
        raise ReadaptError("; ".join(problems))
    report = source_report(runs_dir, stem)
    nonce = params.get("_nonce")
    if not isinstance(nonce, str) or not nonce:
        raise ReadaptError("the readapt fire carries no _nonce; its judge spend could never be reconciled")
    if nonce == report["journal_nonce"]:
        raise ReadaptError(f"the readapt fire's nonce {nonce!r} is the source fire's; each fire books its own spend")
    source_entries = [e for e in journal_entries
                      if e.get("trigger") == "petri-audit" and e.get("nonce") == report["journal_nonce"]]
    if len(source_entries) != 1:
        raise ReadaptError(f"{len(source_entries)} petri-audit journal entries carry the source nonce "
                           f"{report['journal_nonce']!r}; exactly one fire must account for the source run")
    params_sha = source_entries[0].get("params_sha256")
    if not isinstance(params_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", params_sha):
        raise ReadaptError(f"the source fire's journal entry records no params_sha256 ({params_sha!r}); the parameters "
                           "it ran under cannot be identified")
    commit = str(readapt_commit or "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReadaptError(f"readapt_commit must be a 40-hex commit id, got {readapt_commit!r}")
    try:
        attempt = int(str(readapt_run_attempt))
    except ValueError:
        attempt = 0
    if attempt < 1:
        raise ReadaptError(f"readapt_run_attempt must be a positive integer, got {readapt_run_attempt!r}")
    expected = expected_from_params(params, seed_ids)
    expected["eval_id"] = report["eval_id"]
    return {"source_run_id": source_run_id, "run_stem": stem,
            "artifact": select_source_artifact(listing, source_run_id, now=now),
            "target_report": report, "source_params_sha256": params_sha, "expected": expected,
            "readapt": {"workflow_run_id": check_run_id(readapt_run_id, "readapt_run_id"),
                        "workflow_run_attempt": attempt, "commit": commit, "journal_nonce": nonce}}


def provenance_block(plan_: dict) -> dict:
    """The manifest's `readapt` block, from a plan."""
    return {"source_workflow_run_id": plan_["source_run_id"], "source_run_stem": plan_["run_stem"],
            "source_journal_nonce": plan_["target_report"]["journal_nonce"],
            "source_params_sha256": plan_["source_params_sha256"],
            "source_eval_log": plan_["target_report"]["eval_log"],
            "source_artifact": dict(plan_["artifact"]),
            "target_report": {"path": plan_["target_report"]["path"], "sha256": plan_["target_report"]["sha256"]},
            "readapt_workflow_run_id": plan_["readapt"]["workflow_run_id"],
            "readapt_workflow_run_attempt": plan_["readapt"]["workflow_run_attempt"],
            "readapt_commit": plan_["readapt"]["commit"],
            "readapt_journal_nonce": plan_["readapt"]["journal_nonce"]}


def kept_report_problems(report_path: Path | str, *, expected_sha256: str, eval_id: str) -> list[str]:
    """The landed target sidecar, which a readapt leaves exactly as it is: it
    must still be the bytes the plan bound and price the log just adapted."""
    report_path = Path(report_path)
    if not report_path.is_file():
        return [f"{report_path.name}: the landed target sidecar is gone; the source run's target spend is unbooked"]
    problems: list[str] = []
    if sha256_file(report_path) != expected_sha256:
        problems.append(f"{report_path.name} changed after the readapt bound it; a landed sidecar is never rewritten")
    try:
        recorded = load_json(report_path).get("eval_id")
    except (OSError, ValueError, AttributeError):
        recorded = None
    if recorded != eval_id:
        problems.append(f"{report_path.name} priced eval {recorded!r}, not the adapted log's {eval_id!r}")
    return problems
