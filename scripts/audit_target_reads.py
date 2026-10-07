"""Audit the target-token probabilities recorded in committed batch summaries. Read only.

The hosted trace path read a target's probability with a prefix-tolerant match
that kept the likeliest matching logit (``medlang_circuits/targets.py``,
``target_probability`` with ``anchor_matches``), so a recorded value could be
another token's: ' ant' read as ' anti' (a likelier token that begins with the
target) and ' antibiotic' read as ' anti' (a likelier token that is the target's
first part). Separately, with no screen, a target missing from the reference
side was replaced by the top logit (``_resolve_reference``). Since 2026-10-07 new
traces read exactly and record a ``target_read`` block; this script measures how
far the earlier reads reach in what is already committed. It changes nothing.

Inputs: every ``batch_summary*.json`` under ``trace_out/`` and ``pilot/traces/``
(``--root`` is the engine checkout; ``--trace-root`` repeats to replace the two
defaults). Each result's sides are checked against the predictive spread stored
for that same side:

* ``consistent``: the exact target token is in the stored spread and the
  recorded probability equals its probability there.
* ``prefix_mismatch``: the exact target token is in the stored spread with a
  different probability. Both values are reported, with the spread tokens that
  carry the recorded value and their prefix relation to the target.
* ``target_absent_from_spread``: a probability is recorded but the exact target
  token is not in the stored spread. ``value_source`` says what in the spread
  carries the recorded value: ``prefix_neighbour`` (a token the prefix-tolerant
  read accepts, the borrowed case), ``unrelated_token``, or ``not_in_spread``
  (no spread token has that value: the value came from outside the stored
  spread, as on the logits lane, which reads the target by token id at any rank
  and stores the top ten, or from a forced target kept outside the top five).
* ``unverifiable_no_spread``: a probability is recorded but no spread is stored
  for that side (activation-patching summaries).

A flagged side is ``borrowed`` when the backend read token text (hosted) and it
is a ``prefix_mismatch`` or its value is carried by a prefix neighbour. The
logits lane reads by token id, so its equal values are bfloat16 ties at the
spread's cut-off and are listed but never counted as borrowed.
* ``not_measured``: the recorded probability is null. Not checked.

Token identity is the exact token text (the hosted ``Output "..."`` wrapper
removed, nothing else); a target recorded in another wrapping is matched on
``targets.token_key`` (leading space normalised, case kept) and counted as such.

Substitutions, per result: the measured token (``target_token``) against the
intended target, taken from ``screening.intended_target``, else
``target_read.intended_target``, else the pairs file the trace directory was
made from (``data/**/<stem>.json`` or ``pilot/runs/**/<stem>.json``) joined on
``results[i]["index"]`` and verified by the result's prompt text (a screening
probe extension accepted), a join that does not verify being counted as
``intended_unknown``, never guessed. Relations, on ``token_key``:
``exact``, ``leading_wordpiece`` (the measured token is a proper leading piece
of the intended target, at least three characters: the intended wordpiece
rule), ``short_leading_wordpiece`` (a shorter leading piece, as the logits lane
measures when a tokenizer splits a target after one or two characters: the
lane's documented first-token rule, not a substitution, counted so its reach is
visible), and the substitutions ``case_variant``, ``case_variant_wordpiece``,
``extension`` (the measured token begins with the intended target),
``unrelated`` (the top-logit or forced-target fallback) and
``whitespace_token``. ``site_anchor_fallback`` repeats the site exporter's own
rule for comparison with the published flag. A hosted ``leading_wordpiece``
whose intended word is itself a token that model returns in some stored spread
is listed under ``wordpiece_reads_of_returned_tokens``: the word is not split in
that vocabulary, so the wordpiece rule measured another token for it (the
hosted path has no tokenizer to tell the two cases apart).

Duplicates: a trace directory can hold one index in more than one part. Every
occurrence is checked; ``effective`` marks the one the site exporter reads (the
last part in sorted filename order), and the counts are over effective results.

Published rows (``--site-payload``, the site's ``data/simulated_scenarios.json``,
optional): an effective finding in a part the site exporter reads for that
model (``trace_out/<stem>`` for gemma-2-2b, ``trace_out/<stem>__<model>`` for
the others) whose (batch, index, model) is a payload scenario's model object is
marked ``published``, with the payload's own probability for that side.

The report goes to ``--out``; there is no default, and a path under a trace
root is refused, so nothing is ever written into ``trace_out/`` or
``pilot/traces/``. Prompt text is never written to the report.

Usage:
  python scripts/audit_target_reads.py --out /tmp/target_read_audit.json \\
      [--root .] [--site-payload ../patientwords/data/simulated_scenarios.json]

No medical vocabulary lives in this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medlang_circuits.targets import (  # noqa: E402
    MIN_PIECE_CHARS,
    prefix_relation,
    token_key,
    token_text,
)

SCHEMA = "patientwords-target-read-audit/1"
DEFAULT_TRACE_ROOTS = ("trace_out", "pilot/traces")
PAIRS_SEARCH = ("data", "pilot/runs")
BASE_MODEL = "gemma-2-2b"
SUBSTITUTION_RELATIONS = ("case_variant", "case_variant_wordpiece", "extension", "unrelated",
                          "whitespace_token")
FLAGGED_SIDE_STATUSES = ("prefix_mismatch", "target_absent_from_spread")
# Backends whose target read matched token text, where a value equal to a prefix neighbour's is the borrowed
# value. The logits lane reads the target by token id at any rank: its equal values are bfloat16 ties at the
# top-10 cut-off (2026-10-07: every such spread token sat at the bottom of its spread), not borrowing.
TEXT_READ_BACKENDS = ("hosted",)
# The payload's per-model probability key for each 2panel side.
PAYLOAD_PROB_KEYS = {"clinical": "prob_clinical", "patient": "prob_patient"}


class AuditRefusal(SystemExit):
    pass


def refuse(message: str) -> None:
    raise AuditRefusal(f"audit_target_reads: refusing, nothing written: {message}")


def is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---- sides --------------------------------------------------------------------------------------------------


def iter_sides(result: dict[str, Any]) -> Iterator[tuple[str, Any, Any]]:
    """(side, recorded probability, stored spread or None) for every side the result records a probability for,
    in each mode's own shape: 2panel/translation/4quadrant ``probabilities`` keyed like ``predictive_spread``;
    dialect ``baseline_probability`` and ``variants[j].probability`` against ``predictive_spread.baseline`` and
    ``predictive_spread.variants[j]``."""
    spreads = result.get("predictive_spread")
    spreads = spreads if isinstance(spreads, dict) else {}
    if result.get("mode") == "dialect" or "baseline_probability" in result:
        yield "baseline", result.get("baseline_probability"), spreads.get("baseline")
        variant_spreads = spreads.get("variants") if isinstance(spreads.get("variants"), list) else []
        for j, variant in enumerate(result.get("variants") or [], start=1):
            spread = variant_spreads[j - 1] if j - 1 < len(variant_spreads) else None
            yield f"variant_{j:02d}", (variant or {}).get("probability"), spread
        return
    probabilities = result.get("probabilities")
    for side, recorded in (probabilities.items() if isinstance(probabilities, dict) else []):
        yield side, recorded, spreads.get(side)


def spread_entries(spread: Any) -> list[tuple[str, float]] | None:
    if not isinstance(spread, list):
        return None
    out = []
    for entry in spread:
        if isinstance(entry, (list, tuple)) and len(entry) == 2 and isinstance(entry[0], str) and is_num(entry[1]):
            out.append((entry[0], float(entry[1])))
    return out


def check_side(target: str | None, recorded: Any, spread: Any) -> dict[str, Any]:
    """One side's status (module docstring) with the evidence for it."""
    if not is_num(recorded):
        return {"status": "not_measured"}
    entries = spread_entries(spread)
    if entries is None:
        return {"status": "unverifiable_no_spread", "recorded": recorded}
    exact = [(label, p) for label, p in entries if token_text(label) == token_text(target)]
    identity = "token_text"
    if not exact and token_key(target):
        exact = [(label, p) for label, p in entries if token_key(label) == token_key(target)]
        identity = "token_key"
    carriers = [[label, p, prefix_relation(label, target) or "unrelated"] for label, p in entries
                if p == recorded and not any(label == e[0] for e in exact)]
    if exact:
        if any(p == recorded for _, p in exact):
            return {"status": "consistent", **({"identity": identity} if identity != "token_text" else {})}
        return {"status": "prefix_mismatch", "recorded": recorded, "exact": [p for _, p in exact],
                "exact_token": exact[0][0], "identity": identity, "recorded_carried_by": carriers}
    if any(c[2] != "unrelated" for c in carriers):
        source = "prefix_neighbour"
    elif carriers:
        source = "unrelated_token"
    else:
        source = "not_in_spread"
    return {"status": "target_absent_from_spread", "recorded": recorded, "value_source": source,
            "recorded_carried_by": carriers, "spread_len": len(entries)}


# ---- substitution -------------------------------------------------------------------------------------------


def relation(measured: Any, intended: Any) -> str:
    """The measured token's relation to the intended target (module docstring)."""
    if not isinstance(intended, str) or not token_key(intended):
        return "no_intended_target"
    if not isinstance(measured, str):
        return "no_measured_token"
    m, i = token_key(measured), token_key(intended)
    if not m:
        return "whitespace_token"
    if m == i:
        return "exact"
    if len(m) < len(i) and i.startswith(m):
        return "leading_wordpiece" if len(m) >= MIN_PIECE_CHARS else "short_leading_wordpiece"
    mf, inf = m.casefold(), i.casefold()
    if mf == inf:
        return "case_variant"
    if len(m) >= MIN_PIECE_CHARS and len(mf) < len(inf) and inf.startswith(mf):
        return "case_variant_wordpiece"
    if i and m.startswith(i):
        return "extension"
    return "unrelated"


def site_anchor_fallback(measured: Any, intended: Any) -> bool:
    """scripts/export_frontend_simulated.py's anchor_fallback rule, restated for comparison: a measured token
    (wrapper and surrounding whitespace removed) that the intended target, stripped, does not begin with,
    compared case-insensitively."""
    def bare(label: Any) -> str | None:
        text = token_text(label) if isinstance(label, str) else None
        return (text or "").strip() or None
    m = bare(measured)
    i = (intended or "").strip() if isinstance(intended, str) else ""
    return bool(m and i and not i.lower().startswith(m.lower()))


# ---- pairs files --------------------------------------------------------------------------------------------


def index_pairs_files(root: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = defaultdict(list)
    for base in PAIRS_SEARCH:
        for path in sorted((root / base).rglob("*.json")):
            if not path.name.endswith(".report.json"):
                found[path.stem].append(path)
    return found


def load_pairs(path: Path) -> list[Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def prompts_match(result: dict[str, Any], pair: dict[str, Any]) -> bool:
    """The result was traced from this pair: its prompts are the pair's, allowing the probe extension a
    screened result records."""
    prompts = result.get("prompts") if isinstance(result.get("prompts"), dict) else {}
    ext = (result.get("screening") or {}).get("probe_extension") if isinstance(result.get("screening"), dict) \
        else None

    def same(traced: Any, source: Any) -> bool:
        if not isinstance(traced, str) or not isinstance(source, str):
            return False
        return traced == source or bool(ext and traced == source.rstrip() + " " + ext)

    mode = result.get("mode")
    if mode == "dialect":
        return same(result.get("baseline_prompt"), pair.get("baseline_prompt") or pair.get("top_prompt"))
    if mode == "4quadrant":
        from medlang_circuits.batch_eval import _quadrant_prompts  # lazy: plotting stack
        try:
            want = _quadrant_prompts(pair)
        except (ValueError, KeyError, TypeError):
            return False
        return all(same(prompts.get(k), want.get(k)) for k in want)
    if mode == "translation":
        return same(prompts.get("patient"), pair.get("patient_prompt") or pair.get("bottom_prompt"))
    return same(prompts.get("clinical"), pair.get("top_prompt")) and same(prompts.get("patient"),
                                                                          pair.get("bottom_prompt"))


# ---- scan ---------------------------------------------------------------------------------------------------


def trace_dirs(root: Path, trace_roots: list[str]) -> list[tuple[str, Path]]:
    dirs = set()
    for tr in trace_roots:
        base = root / tr
        if not base.is_dir():
            continue
        for part in base.rglob("batch_summary*.json"):
            dirs.add((tr, part.parent))
    return sorted(dirs, key=lambda d: (d[0], str(d[1])))


def site_reads(trace_root: str, dir_name: str, stem: str | None, model: str, part_rel: str) -> bool:
    """The site exporter reads this part for this model: trace_out/<stem> for the base model and
    trace_out/<stem>__<model> for every other (export_frontend_simulated.model_dir), part files only."""
    if trace_root != "trace_out" or not stem or not Path(part_rel).name.startswith("batch_summary.part_"):
        return False
    return dir_name == (stem if model == BASE_MODEL else f"{stem}__{model}")


def token_vocabulary(loaded: dict[Path, list[tuple[Path, dict]]]) -> dict[str, set[str]]:
    """Per model, the token keys seen anywhere in its stored spreads: evidence that a word is one token in that
    model's vocabulary."""
    vocab: dict[str, set[str]] = defaultdict(set)
    for d, parts in loaded.items():
        for _, summary in parts:
            model = summary.get("graph_model") or (d.name.split("__")[1] if "__" in d.name else BASE_MODEL)
            for r in summary.get("results", []) or []:
                spreads = r.get("predictive_spread") if isinstance(r, dict) else None
                stack = list(spreads.values()) if isinstance(spreads, dict) else []
                while stack:
                    item = stack.pop()
                    entries = spread_entries(item)
                    if entries:
                        vocab[model].update(token_key(label) for label, _ in entries)
                    elif isinstance(item, list):
                        stack.extend(x for x in item if isinstance(x, list))
    return vocab


def git_sha(root: Path) -> str | None:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=False)
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def read_payload(path: Path | None) -> tuple[dict[tuple[str, int, str], dict], dict[str, Any] | None]:
    if path is None:
        return {}, None
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    rows: dict[tuple[str, int, str], dict] = {}
    for s in payload.get("scenarios", []):
        for model, obj in (s.get("models") or {}).items():
            if isinstance(obj, dict):
                rows[(s.get("batch"), s.get("batch_index"), model)] = obj
    return rows, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                  "scenarios": len(payload.get("scenarios", []))}


def audit(root: Path, trace_roots: list[str], payload_path: Path | None) -> dict[str, Any]:
    pairs_index = index_pairs_files(root)
    payload_rows, payload_meta = read_payload(payload_path)
    findings: list[dict[str, Any]] = []
    substitutions: list[dict[str, Any]] = []
    counts: dict[str, dict[str, Counter]] = {k: defaultdict(Counter) for k in
                                             ("by_root", "by_dir", "by_batch", "by_model", "by_backend")}
    overall: Counter = Counter()
    joins: Counter = Counter()
    unjoined_dirs: dict[str, str] = {}
    payload_seen: set[tuple[str | None, Any, str]] = set()
    summaries = 0
    dirs = trace_dirs(root, trace_roots)
    loaded = {d: [(part, json.loads(part.read_text(encoding="utf-8")))
                  for part in sorted(d.glob("batch_summary*.json"))] for _, d in dirs}
    vocabulary = token_vocabulary(loaded)
    wordpiece_tokens: list[dict[str, Any]] = []

    for trace_root, d in dirs:
        rel_dir = d.relative_to(root).as_posix()
        stem = d.name.split("__")[0] if d.name != Path(trace_root).name else None
        pairs: list[Any] | None = None
        pairs_path = None
        candidates = pairs_index.get(stem or "", [])
        if len(candidates) == 1:
            pairs_path = candidates[0]
            pairs = load_pairs(pairs_path)
            if pairs is None:
                unjoined_dirs[rel_dir] = "pairs_file_not_a_list"
        else:
            unjoined_dirs[rel_dir] = "no_pairs_file" if not candidates else "several_pairs_files"
        occurrences: list[tuple[str, dict, dict]] = []
        for part, summary in loaded[d]:
            summaries += 1
            for r in summary.get("results", []) or []:
                if isinstance(r, dict):
                    occurrences.append((part.relative_to(root).as_posix(), summary, r))
        last_part_for: dict[Any, str] = {}
        for part_rel, _, r in occurrences:
            last_part_for[r.get("index")] = part_rel
        for part_rel, summary, r in occurrences:
            index = r.get("index")
            model = summary.get("graph_model") or (d.name.split("__")[1] if "__" in d.name else BASE_MODEL)
            backend = summary.get("backend")
            effective = last_part_for.get(index) == part_rel
            target = r.get("target_token")
            base = {"dir": rel_dir, "part": part_rel, "index": index, "batch": stem, "model": model,
                    "backend": backend, "mode": r.get("mode"), "effective": effective}
            payload_obj = (payload_rows.get((stem, index, model))
                           if effective and site_reads(trace_root, d.name, stem, model, part_rel) else None)
            keys = [("by_root", trace_root), ("by_dir", rel_dir), ("by_batch", stem or rel_dir),
                    ("by_model", model), ("by_backend", str(backend))]

            def bump(name: str, n: int = 1) -> None:
                if not effective:
                    return
                overall[name] += n
                for group, key in keys:
                    counts[group][key][name] += n

            bump("results")
            if not effective:
                overall["superseded_duplicate_results"] += 1
            flagged_here = False
            for side, recorded, spread in iter_sides(r):
                verdict = check_side(target, recorded, spread)
                status = verdict["status"]
                bump(f"sides.{status}")
                if status == "target_absent_from_spread":
                    bump(f"sides.target_absent_from_spread.{verdict['value_source']}")
                if status in FLAGGED_SIDE_STATUSES:
                    borrowed = backend in TEXT_READ_BACKENDS and (
                        status == "prefix_mismatch" or verdict.get("value_source") == "prefix_neighbour")
                    flagged_here = flagged_here or borrowed
                    entry = {**base, "side": side, "target_token": target, **verdict, "borrowed": borrowed}
                    if payload_obj is not None:
                        entry["published"] = True
                        key = PAYLOAD_PROB_KEYS.get(side)
                        if key:
                            entry["payload_probability"] = payload_obj.get(key)
                    elif effective and payload_rows:
                        entry["published"] = False
                    findings.append(entry)
            if flagged_here:
                bump("results_with_borrowed_value")
                if payload_obj is not None:
                    bump("published_results_with_borrowed_value")

            intended, source = None, None
            screening = r.get("screening") if isinstance(r.get("screening"), dict) else {}
            target_read = r.get("target_read") if isinstance(r.get("target_read"), dict) else {}
            if screening.get("intended_target") is not None:
                intended, source = screening.get("intended_target"), "screening"
            elif "intended_target" in target_read:
                intended, source = target_read.get("intended_target"), "target_read"
            elif pairs is not None and isinstance(index, int) and 1 <= index <= len(pairs) \
                    and isinstance(pairs[index - 1], dict):
                if prompts_match(r, pairs[index - 1]):
                    intended, source = pairs[index - 1].get("target_clinical_token"), "pairs_file"
                    joins["verified"] += effective
                else:
                    source = "join_refused_prompt_mismatch"
                    joins["refused_prompt_mismatch"] += effective
            else:
                source = "no_join"
                joins["no_join"] += effective
            rel = relation(target, intended) if source not in ("join_refused_prompt_mismatch", "no_join") \
                else "intended_unknown"
            bump(f"target.{rel}")
            if rel == "leading_wordpiece" and backend in TEXT_READ_BACKENDS \
                    and token_key(intended) in vocabulary.get(model, set()):
                # The intended word itself is a token this model returns elsewhere, so it is not split: the
                # wordpiece rule measured another token for it.
                bump("target.leading_wordpiece.intended_is_a_returned_token")
                if effective:
                    wordpiece_tokens.append({**base, "intended_target": intended, "measured_token": target,
                                             **({"published": payload_obj is not None} if payload_rows else {})})
            if rel in SUBSTITUTION_RELATIONS:
                bump("substitutions")
                entry = {**base, "intended_target": intended, "intended_source": source, "measured_token": target,
                         "relation": rel, "site_anchor_fallback": site_anchor_fallback(target, intended),
                         "recorded_substituted_flag": target_read.get("substituted")}
                if payload_obj is not None:
                    entry["published"] = True
                    entry["payload_anchor_fallback"] = payload_obj.get("anchor_fallback")
                    bump("published_substitutions")
                elif effective and payload_rows:
                    entry["published"] = False
                substitutions.append(entry)
            if payload_obj is not None:
                bump("published_results")
                payload_seen.add((stem, index, model))

    def plain(group: dict[str, Counter]) -> dict[str, dict[str, int]]:
        return {k: dict(sorted(v.items())) for k, v in sorted(group.items())}

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_sha": git_sha(root),
        "inputs": {"root": str(root), "trace_roots": trace_roots, "summaries": summaries,
                   "site_payload": payload_meta},
        "rules": {
            "sides": "recorded probability vs the exact target token's probability in the same side's stored "
                     "predictive_spread; statuses consistent, prefix_mismatch, target_absent_from_spread "
                     "(value_source prefix_neighbour, unrelated_token, not_in_spread), unverifiable_no_spread, "
                     "not_measured",
            "borrowed": "a side is borrowed when it is a prefix_mismatch or its recorded value is carried by a "
                        "prefix neighbour in the spread",
            "substitution": "measured token vs intended target on token_key; substitutions are "
                            + ", ".join(SUBSTITUTION_RELATIONS),
            "counting": "counts are over effective results (the part the site exporter reads for each index); "
                        "findings and substitutions list every occurrence with its effective flag",
        },
        "counts": {"overall": dict(sorted(overall.items())), **{k: plain(v) for k, v in counts.items()}},
        "joins": dict(sorted(joins.items())),
        # payload model objects with no committed summary result the site exporter would read: not auditable here
        "payload_rows_without_summary": sorted([list(k) for k in set(payload_rows) - payload_seen],
                                               key=lambda k: (str(k[0]), k[1] if isinstance(k[1], int) else -1, str(k[2]))),
        "unjoined_dirs": dict(sorted(unjoined_dirs.items())),
        "findings": findings,
        "substitutions": substitutions,
        "wordpiece_reads_of_returned_tokens": wordpiece_tokens,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path, help="report path (required; never under a trace root)")
    ap.add_argument("--root", type=Path, default=ROOT, help="engine checkout to scan (default: this one)")
    ap.add_argument("--trace-root", action="append", default=None,
                    help=f"trace root relative to --root, repeatable (default: {', '.join(DEFAULT_TRACE_ROOTS)})")
    ap.add_argument("--site-payload", type=Path, default=None,
                    help="the site's data/simulated_scenarios.json, to mark published rows (optional)")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    trace_roots = args.trace_root or list(DEFAULT_TRACE_ROOTS)
    out = args.out.resolve()
    for tr in trace_roots:
        if out.is_relative_to((root / tr).resolve()):
            refuse(f"--out {out} is under the trace root {tr}; this audit writes nothing there")
    if args.site_payload is not None and not args.site_payload.is_file():
        refuse(f"--site-payload {args.site_payload} is not a file")
    report = audit(root, trace_roots, args.site_payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    o = report["counts"]["overall"]
    print(f"audit_target_reads: {report['inputs']['summaries']} summaries, {o.get('results', 0)} effective results; "
          f"{o.get('results_with_borrowed_value', 0)} with a borrowed value, {o.get('substitutions', 0)} "
          f"substitutions; report at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
