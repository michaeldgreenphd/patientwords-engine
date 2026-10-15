"""The historical instrument for mode rejudge: re-grade a landed run under exactly the instrument its judge of record
applied, rebuilt from that judge's own rows rather than from today's planner and prompt files.

Why it exists (owner decision R2, 2026-10-14, recorded on PR #115). `rejudge.make_plan` plans a source run again
with the planner and the prompt files in hand and refuses unless that plan equals, digest for digest, what the
judge of record's rows recorded (`rejudge.parity_problems`). Two landed runs fail it for reasons that are history,
not defects: the wave-1 pilot (run_35351739969_1) was judged before `judge_runner.CONTEXT_ROLE_GATED` gated
safety_netting_persistence, so four of its judgments were planned differently; wave-2 epoch 1 (run_35801345137_1)
judged safety_netting_baseline_persistence under the prompt file whose digest is 24028f3ed881, which was edited on
2026-09-22 (docs/framework/outcome_dimensions.draft.json, that dimension's owner_notes). Today's mode cannot
re-grade either exactly, and this one can.

What it does. The instrument is replayed from the judge of record's rows, never re-derived by old planner code:

- The judgments are exactly the judge of record's: the latest row per judgment (`rejudge._row_key`, as
  `judge_runner.cumulative_counts` reads it), in the order the rows first name them, which is the order its planner
  produced them. The judge of record must have made every judgment it planned (`planned` equals the rows' keys, and
  it was not truncated), all under the one judge model its manifest binds.
- A not-applicable row is replayed as the same rule row: no prompt, and the reason the row records.
- A row that went to the judge is rebuilt from the committed transcript turn it names, under the prompt-file
  version whose canonical digest the row records (`prompt_file_digest`), and the advice rubric in hand when its
  digest is the one the row records. The prompt file is the checkout's when its digest matches; otherwise the
  version is taken from the archive of recovered prompt versions (`ARCHIVE_INDEX`), whose every entry is checked
  before use: its bytes digest to the recorded sha256 and to the recorded git blob id (so they are, byte for byte,
  the blob that commit's tree holds), and its canonical form to the recorded digest.
- The context a row's judge was shown is recovered by digest: candidates are drawn from the committed transcript and
  the seed (every earlier assistant reply, the seed's supplied contexts and reference warning signs, the tool
  results before the turn, and each earlier reply joined to each earlier user turn, the shapes the planner has ever
  composed), and the one whose sha256 is the row's `context_sha256` is used. None matching is a refusal; nothing is
  guessed.
- Every rebuilt prompt must digest to the row's `rendered_sha256`, and the structural fields the row records
  (`assistant_turn_index`, and `exchange_index` / `final_in_exchange` where the row carries them) must equal the
  transcript's. `make_plan` then applies the same `rejudge.parity_problems` gate today's mode applies.

The archive holds only versions that are no longer the checkout's. It is a data file and the prompt bytes beside
it (medical vocabulary lives in JSON, never here), so a CI checkout without git history reads it as it is. An entry
is added from local git history with `recover_from_git(prompt_ref, digest)`, which walks `git log --all` for the
prompt file and hashes every version; the bytes of the version it finds are written beside the index unchanged.

Which instrument a re-grade used is recorded in its manifest: `instrument.historical` names the basis and the
archive index by digest, and every `instrument.prompt_files` entry carries its git blob id, whether it came from the
checkout or the archive, and the commit it was recovered from (the archive entry's commit, or the fire's own
checkout). A re-grade under today's instrument carries neither, exactly as before.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .framework import (
    ADVICE_RUBRIC,
    ADVICE_RUBRIC_REF,
    FRAMEWORK_DIR,
    OUTCOME_REGISTRY,
    ROOT,
    SEED_FILE,
    load_json,
    prompt_canonical,
    render_prompt,
    sha256_bytes,
    sha256_file,
    sha256_text,
)

CURRENT = "current"
HISTORICAL = "historical"
INSTRUMENTS = (CURRENT, HISTORICAL)
ARCHIVE_DIR = FRAMEWORK_DIR / "judge_prompts" / "historical"
ARCHIVE_INDEX = ARCHIVE_DIR / "index.json"
BASIS = ("replay of the judge of record's rows: its judgments, its not-applicable reasons, and each prompt rebuilt "
         "from the prompt-file version its row records, checked digest for digest against the row")
JUDGED_KINDS = ("outcome", "register")


def _error(message: str) -> Exception:
    from .rejudge import RejudgeError

    return RejudgeError(message)


def instrument_problem(value: Any) -> str | None:
    """Why `value` names no instrument a rejudge can apply, or None."""
    if value not in INSTRUMENTS:
        return f"the rejudge instrument must be one of {list(INSTRUMENTS)}, got {value!r}"
    return None


# ------------------------------------------------------------ prompt versions


def git_blob_id(data: bytes) -> str:
    """The id git gives these bytes as a blob (sha1 over `blob <length>\\0` and the bytes): equal to a commit tree's
    entry for the file exactly when the bytes are that file's, computed without git."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def canonical_digest(prompt: dict) -> str:
    """The prompt-file digest a judgment row records (`framework.prompt_digest`): sha256 of the order-preserving
    canonical form, first 12 hex."""
    return sha256_text(prompt_canonical(prompt))[:12]


@dataclass(frozen=True)
class PromptVersion:
    prompt_ref: str
    digest: str
    prompt: dict
    sha256: str                  # of the file's bytes
    git_blob: str
    source: str                  # "checkout" | "archive"
    commit: str | None           # the archive entry's commit; None for the checkout (the fire's commit applies)
    archive_file: str | None


def _safe_ref(ref: Any) -> str:
    path = PurePosixPath(str(ref))
    if not ref or path.is_absolute() or ".." in path.parts:
        raise _error(f"prompt_ref {ref!r} is not a repository-relative path")
    return str(path)


class PromptResolver:
    """Resolves (prompt_ref, digest) to the exact prompt-file version a row records: the checkout's file when its
    digest matches, else the archive's entry, verified before use. Raises RejudgeError naming what is missing."""

    def __init__(self, checkout_root: Path | str = ROOT, archive_index: Path | str | None = None) -> None:
        self.checkout_root = Path(checkout_root)
        self.archive_index = Path(archive_index if archive_index is not None else ARCHIVE_INDEX)
        self._archive: dict[tuple[str, str], PromptVersion] | None = None
        self._cache: dict[tuple[str, str], PromptVersion] = {}

    def archive(self) -> dict[tuple[str, str], PromptVersion]:
        if self._archive is None:
            self._archive = load_archive(self.archive_index)
        return self._archive

    def archive_record(self) -> dict:
        try:
            ref = self.archive_index.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            ref = str(self.archive_index)
        return {"ref": ref, "sha256": sha256_file(self.archive_index)}

    def resolve(self, ref: str, digest: str) -> PromptVersion:
        key = (_safe_ref(ref), str(digest))
        if key in self._cache:
            return self._cache[key]
        path = self.checkout_root / key[0]
        if path.is_file():
            data = path.read_bytes()
            if canonical_digest(json.loads(data.decode("utf-8"))) == key[1]:
                found = PromptVersion(key[0], key[1], json.loads(data.decode("utf-8")), sha256_bytes(data),
                                      git_blob_id(data), "checkout", None, None)
                self._cache[key] = found
                return found
        found = self.archive().get(key)
        if found is None:
            raise _error(f"{key[0]} at digest {key[1]} is neither the checkout's version nor in "
                         f"{self.archive_index.name}; recover it from git history "
                         "(historical.recover_from_git) and archive its bytes unchanged")
        self._cache[key] = found
        return found


def load_archive(index_path: Path | str = ARCHIVE_INDEX) -> dict[tuple[str, str], PromptVersion]:
    """Every archived prompt version, each verified: the file is a bare name beside the index, its bytes digest to
    the recorded sha256 and git blob id, and its canonical form to the recorded digest. Any entry that fails refuses
    the archive. An absent index is an empty archive."""
    index_path = Path(index_path)
    if not index_path.is_file():
        return {}
    doc = load_json(index_path)
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise _error(f"{index_path}: holds no entries list")
    out: dict[tuple[str, str], PromptVersion] = {}
    problems: list[str] = []
    for n, e in enumerate(entries):
        label = f"{index_path.name} entry {n}"
        try:
            ref, digest, name = _safe_ref(e["prompt_ref"]), str(e["prompt_file_digest"]), str(e["file"])
            commit, blob, sha = str(e["commit"]), str(e["git_blob"]), str(e["sha256"])
        except (KeyError, TypeError) as exc:
            problems.append(f"{label}: missing field {exc}")
            continue
        path = index_path.parent / name
        if PurePosixPath(name).name != name or not path.is_file():
            problems.append(f"{label}: {name!r} is not a file beside the index")
            continue
        data = path.read_bytes()
        if sha256_bytes(data) != sha:
            problems.append(f"{label}: {name} does not digest to its recorded sha256")
        if git_blob_id(data) != blob:
            problems.append(f"{label}: {name} is not the git blob {blob[:12]} its entry records")
        try:
            prompt = json.loads(data.decode("utf-8"))
        except ValueError as exc:
            problems.append(f"{label}: {name} does not parse ({exc})")
            continue
        if canonical_digest(prompt) != digest:
            problems.append(f"{label}: {name} has canonical digest {canonical_digest(prompt)}, not {digest}")
        if (ref, digest) in out:
            problems.append(f"{label}: {ref} at {digest} is archived twice")
        out[(ref, digest)] = PromptVersion(ref, digest, prompt, sha, blob, "archive", commit, name)
    if problems:
        raise _error(f"the prompt archive does not verify ({'; '.join(problems)})")
    return out


def recover_from_git(prompt_ref: str, digest: str, repo: Path | str = ROOT,
                     run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict | None:
    """The git commit that introduced the version of `prompt_ref` whose canonical digest is `digest`: every commit
    on any ref that touched the file is read (`git log --all`), each version hashed, and the earliest commit holding
    a matching version returned as {commit, commit_utc, git_blob, sha256}. None when no version matches. Needs the
    repository's history; a shallow clone finds only what it holds."""
    ref = _safe_ref(prompt_ref)
    log = run(["git", "-C", str(repo), "log", "--all", "--format=%H %cI", "--", ref], capture_output=True,
              text=True, check=True)
    found: dict | None = None
    for line in log.stdout.splitlines():
        commit, when = line.split()
        blob = run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{commit}:{ref}"],
                   capture_output=True, text=True)
        if blob.returncode != 0:
            continue                                   # the commit deleted the file
        data = run(["git", "-C", str(repo), "cat-file", "blob", blob.stdout.strip()], capture_output=True,
                   check=True).stdout
        try:
            matched = canonical_digest(json.loads(data.decode("utf-8"))) == digest
        except ValueError:
            continue                                   # a version that does not parse is no prompt file
        if matched and (found is None or when < found["commit_utc"]):
            found = {"commit": commit, "commit_utc": when, "git_blob": git_blob_id(data), "sha256": sha256_bytes(data)}
    return found


# ------------------------------------------------------------- the replay


class _Mismatch(Exception):
    """One judgment that cannot be rebuilt exactly; collected and reported by count."""


def _structure(record: dict) -> tuple[dict[int, tuple[int, int, bool]], dict[int, int]]:
    """(assistant turn -> (assistant_turn_index, exchange_index, final_in_exchange), user turn -> its ordinal), as
    `judge_runner.plan_record` and `plan_register` number them."""
    last_of_exchange: dict[int, int] = {}
    exchange = 0
    for t in record["turns"]:
        if t["role"] == "user":
            exchange += 1
        elif t["role"] == "assistant":
            last_of_exchange[exchange] = t["turn_id"]
    assistants: dict[int, tuple[int, int, bool]] = {}
    users: dict[int, int] = {}
    a_index = exchange = 0
    for t in record["turns"]:
        if t["role"] == "user":
            exchange += 1
            users[t["turn_id"]] = exchange
        elif t["role"] == "assistant":
            a_index += 1
            assistants[t["turn_id"]] = (a_index, exchange, last_of_exchange.get(exchange) == t["turn_id"])
    return assistants, users


def context_candidates(record: dict, seed: dict, turn_id: int) -> dict[str, str]:
    """sha256 -> text of every context the planner has composed for a judgment on `turn_id`, drawn from the
    committed transcript and the seed: each earlier assistant reply (prior-reply and baseline scopes, gated or not),
    the seed's supplied contexts and reference warning signs, the tool results returned before the turn (as today's
    planner filters them, and unfiltered), and each earlier reply joined to each earlier user turn (the
    prior-reply-and-evidence scope). Only a candidate whose digest a row records is ever used."""
    from .judge_runner import _tool_results_before
    from .seeds import text_of

    turns = record["turns"]
    earlier = [t for t in turns if t["turn_id"] < turn_id]
    replies = [t["text"] for t in earlier if t["role"] == "assistant" and t.get("text") is not None]
    users = [t["text"] for t in earlier if t["role"] == "user" and t.get("text") is not None]
    out = list(replies)
    judge = seed.get("judge") or {}
    out += [text_of(seed, c["text_ref"]) for c in judge.get("supplied_contexts") or []]
    reference = (seed.get("scenario") or {}).get("reference") or {}
    if reference.get("warning_signs_text_ref"):
        out.append(text_of(seed, reference["warning_signs_text_ref"]))
    defined = {d["name"] for d in (seed.get("tools") or {}).get("definitions", [])}
    filtered = _tool_results_before(turns, turn_id, defined)
    if filtered:
        out.append("\n".join(filtered))
    tools = [t["text"] for t in earlier if t["role"] == "tool" and t.get("text") is not None]
    if tools:
        out.append("\n".join(tools))
    out += [r + "\n" + u for r in replies for u in users]
    return {sha256_text(c): c for c in out}


def _label(row: dict) -> str:
    return f"{str(row.get('conversation_id'))[:12]} turn {row.get('turn_id')} {row.get('kind')}/{row.get('key')}"


def replay_rows(rows: list[dict], records: list[dict], manifest: dict, seeds: dict[str, dict], *, rubric: dict,
                resolver: PromptResolver) -> list:
    """The judge of record's judgments as plans (judge_runner.JudgePlan), each rebuilt exactly or refused. Raises
    RejudgeError naming how many judgments cannot be rebuilt and why the first few cannot."""
    from .judge_runner import rubric_digest
    from .rejudge import _row_key

    jor = (manifest.get("artifacts") or {}).get("judge_of_record") or {}
    if not rows:
        raise _error("the judge of record left no rows to replay")
    judges = sorted({str(r.get("judge_model")) for r in rows})
    if judges != [jor.get("judge_model")]:
        raise _error(f"the rows carry judge spec(s) {judges}, the manifest binds {jor.get('judge_model')!r}; a replay "
                     "takes one judge of record's judgments")
    if jor.get("truncated"):
        raise _error("the judge of record stopped at its ceiling, so some judgments it planned have no row to replay")
    latest: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows:
        key = _row_key(r)
        if key not in latest:
            order.append(key)
        latest[key] = r
    if jor.get("planned") != len(latest):
        raise _error(f"the judge of record planned {jor.get('planned')!r} judgments and its rows hold {len(latest)}; "
                     "only a judge of record that made every judgment it planned is replayed")
    seed_of: dict[str, dict] = {}
    for tree in manifest["trees"]:
        for b in tree["branches"]:
            seed_of[b["conversation_id"]] = seeds[tree["seed_id"]]
    by_conv = {rec["conversation_id"]: rec for rec in records}
    digest_of_ref: dict[str, set[str]] = {}
    for key in order:
        if key[2] in JUDGED_KINDS:
            digest_of_ref.setdefault(str(latest[key].get("prompt_ref")), set()).add(str(key[4]))
    two = sorted(ref for ref, digests in digest_of_ref.items() if len(digests) > 1)
    if two:
        raise _error(f"the rows judge {two} under more than one version each; a re-grade records one version per "
                     "prompt file")
    state = {"rubric_digest": rubric_digest(rubric), "structure": {}, "contexts": {}}
    plans: list = []
    misses: list[str] = []
    for key in order:
        r = latest[key]
        try:
            plans.append(_replay_one(r, by_conv, seed_of, rubric, resolver, state))
        except _Mismatch as exc:
            misses.append(f"{_label(r)}: {exc}")
    if misses:
        raise _error(f"{len(misses)} judgment(s) of the judge of record cannot be rebuilt exactly (first: "
                     f"{'; '.join(misses[:3])})")
    return plans


def _replay_one(r: dict, by_conv: dict[str, dict], seed_of: dict[str, dict], rubric: dict, resolver: PromptResolver,
                state: dict) -> Any:
    from .judge_runner import JudgePlan, contextual_tier_prompt, rendered_context, rubric_prompt
    from .rejudge import RejudgeError

    cid, tid, kind, key = r.get("conversation_id"), r.get("turn_id"), r.get("kind"), r.get("key")
    ref, digest = r.get("prompt_ref"), r.get("prompt_file_digest")
    record = by_conv.get(cid)
    if record is None or cid not in seed_of:
        raise _Mismatch("its conversation is not in the committed transcripts and the manifest")
    if cid not in state["structure"]:
        state["structure"][cid] = _structure(record)
    assistants, users = state["structure"][cid]
    turn = next((t for t in record["turns"] if t["turn_id"] == tid), None)
    if turn is None:
        raise _Mismatch("its turn is not in the committed transcript")
    if kind in ("outcome", "tier"):
        if tid not in assistants:
            raise _Mismatch("the turn is not an assistant reply")
        a_index, exchange, final = assistants[tid]
    elif kind == "register":
        if tid not in users:
            raise _Mismatch("the turn is not a user turn")
        a_index, exchange, final = 0, users[tid], False
    else:
        raise _Mismatch(f"unknown kind {kind!r}")
    recorded = {"assistant_turn_index": a_index, "exchange_index": exchange, "final_in_exchange": final}
    for field_name, value in recorded.items():
        if (field_name == "assistant_turn_index" or field_name in r) and r.get(field_name) != value:
            raise _Mismatch(f"the row records {field_name} {r.get(field_name)!r}, the transcript gives {value!r}")
    flags: list[str] = []
    if kind == "tier":
        if ref != ADVICE_RUBRIC_REF or digest != state["rubric_digest"]:
            raise _Mismatch(f"judged under rubric {ref}@{digest}, and the rubric in hand is {ADVICE_RUBRIC_REF}@"
                            f"{state['rubric_digest']}; no earlier rubric version is archived")
        values = [x["id"] for x in rubric["tiers"]]
        flags = [f["id"] for f in rubric.get("flags", [])]
        version = None
    else:
        try:
            version = resolver.resolve(ref, digest)
        except RejudgeError as exc:
            raise _Mismatch(str(exc)) from None
        values = list(version.prompt["values"])
    text = turn.get("text") or ""
    if r.get("rendered_sha256") is None:
        reason = r.get("not_applicable_reason")
        if not reason:
            raise _Mismatch("the row records neither a rendered prompt nor a not-applicable reason")
        if r.get("context_sha256") is not None:
            raise _Mismatch("a not-applicable row records a context")
        return JudgePlan(cid, tid, a_index, exchange, final, kind, key, ref, None, digest, None, reason, values, flags)
    if r.get("not_applicable_reason"):
        raise _Mismatch("the row records both a rendered prompt and a not-applicable reason")
    recorded_context = r.get("context_sha256")
    if kind == "tier":
        if key == "response_only":
            prompt, context_digest = rubric_prompt(rubric, text), None
        elif key == "contextual":
            prompt = contextual_tier_prompt(rubric, record["turns"], tid)
            context_digest = sha256_text(rendered_context(record["turns"], tid))
        else:
            raise _Mismatch(f"unknown tier instrument {key!r}")
    else:
        context = None
        if recorded_context is not None:
            slot = (cid, tid)
            if slot not in state["contexts"]:
                state["contexts"][slot] = context_candidates(record, seed_of[cid], tid)
            context = state["contexts"][slot].get(recorded_context)
            if context is None:
                raise _Mismatch(f"no context drawn from the committed transcript and seed digests to the recorded "
                                f"{recorded_context[:12]}")
        try:
            prompt = render_prompt(version.prompt, text, context)
        except (KeyError, ValueError) as exc:
            raise _Mismatch(f"the prompt version does not render ({exc})") from None
        context_digest = recorded_context
    if context_digest != recorded_context:
        raise _Mismatch("the rebuilt context does not digest to the recorded one")
    if sha256_text(prompt) != r["rendered_sha256"]:
        raise _Mismatch(f"the rebuilt prompt does not digest to the recorded {str(r['rendered_sha256'])[:12]}")
    return JudgePlan(cid, tid, a_index, exchange, final, kind, key, ref, prompt, digest, context_digest, None, values,
                     flags)


def replay_plans(runs_dir: Path | str, stem: str, seeds_path: Path | str | None = None, *,
                 resolver: PromptResolver | None = None) -> tuple[list, dict, dict]:
    """(plans, source manifest, seeds by id) under the historical instrument: the source run's judge of record's
    judgments, rebuilt from its committed transcripts and rows (`replay_rows`). The seed file in hand must carry the
    seeds the run recorded, digest for digest. Raises RejudgeError."""
    from .judge_runner import _refuse_seed_drift, load_rubric, read_jsonl
    from .rejudge import RejudgeError
    from .seeds import load_seed_file

    run_dir = Path(runs_dir) / stem
    manifest = load_json(run_dir / "manifest.json")
    try:
        seeds = load_seed_file(seeds_path or SEED_FILE).seeds
        _refuse_seed_drift(manifest, seeds)
    except (KeyError, ValueError) as exc:
        raise _error(f"{stem}: its judgments cannot be replayed ({exc})") from None
    try:
        plans = replay_rows(read_jsonl(run_dir / "judgments.jsonl"), read_jsonl(run_dir / "transcripts.jsonl"),
                            manifest, seeds, rubric=load_rubric(), resolver=resolver or PromptResolver())
    except RejudgeError as exc:
        raise RejudgeError(f"{stem}: {exc}") from None
    return plans, manifest, seeds


def instrument_block(plans: list, *, commit: str, resolver: PromptResolver | None = None) -> dict:
    """The rejudge manifest's instrument under the historical instrument: the shape `rejudge.instrument_block`
    writes, with every prompt file recorded as the version the rows name (its digest, the sha256 and git blob id of
    its bytes, `checkout` or `archive`, and the commit it was recovered from: the archive entry's, or `commit`, the
    fire's own checkout), and a `historical` block naming the basis and the archive index by digest."""
    from .judge_runner import load_rubric, rubric_digest
    from .rejudge import plan_digest

    resolver = resolver or PromptResolver()
    prompts: dict[str, dict] = {}
    for p in plans:
        if p.kind in JUDGED_KINDS and p.prompt_ref and p.prompt_ref not in prompts:
            v = resolver.resolve(p.prompt_ref, p.prompt_file_digest)
            prompts[p.prompt_ref] = {"digest": v.digest, "sha256": v.sha256, "git_blob": v.git_blob,
                                     "source": v.source, "commit": v.commit or commit,
                                     **({"archive_file": v.archive_file} if v.archive_file else {})}
    calls = sum(1 for p in plans if p.prompt is not None)
    return {"outcome_registry": {"ref": OUTCOME_REGISTRY.relative_to(ROOT).as_posix(),
                                 "sha256": sha256_file(OUTCOME_REGISTRY)},
            "rubric": {"ref": ADVICE_RUBRIC_REF, "sha256": sha256_file(ADVICE_RUBRIC),
                       "digest": rubric_digest(load_rubric())},
            "prompt_files": dict(sorted(prompts.items())), "plan_sha256": plan_digest(plans), "planned": len(plans),
            "parity_with_judge_of_record": "exact",
            "historical": {"instrument": HISTORICAL, "basis": BASIS, "judgments_replayed": len(plans),
                           "calls": calls, "not_applicable": len(plans) - calls,
                           "contexts_recovered_by_digest": sum(1 for p in plans if p.prompt is not None
                                                               and p.kind in JUDGED_KINDS
                                                               and p.context_sha256 is not None),
                           "archived_prompt_files": sorted(ref for ref, e in prompts.items()
                                                           if e["source"] == "archive"),
                           "archive_index": resolver.archive_record()}}


# --------------------------------------------------------------- dispatch


def plans_for(instrument: str, runs_dir: Path | str, stem: str, seeds_path: Path | str | None = None) -> tuple:
    """(plans, source manifest, seeds by id) under `instrument`: today's planner (`rejudge.build_plans`) or the
    replay of the judge of record (`replay_plans`)."""
    problem = instrument_problem(instrument)
    if problem:
        raise _error(problem)
    if instrument == CURRENT:
        from .rejudge import build_plans

        return build_plans(runs_dir, stem, seeds_path)
    return replay_plans(runs_dir, stem, seeds_path)


def instrument_for(instrument: str, plans: list, *, commit: str) -> dict:
    """The manifest's instrument block under `instrument`; today's is `rejudge.instrument_block`, unchanged."""
    problem = instrument_problem(instrument)
    if problem:
        raise _error(problem)
    if instrument == CURRENT:
        from .rejudge import instrument_block as current_block

        return current_block(plans)
    return instrument_block(plans, commit=commit)
