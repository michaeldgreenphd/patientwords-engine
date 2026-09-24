"""Frozen near-twin list for the Tier B holdout sensitivity readout (Tier B Amendment 5).

Registered 2026-09-23, before unsealing (docs/prereg_amendment5_near_twins.md).
A sealed holdout phrase is a NEAR TWIN when some non-sealed phrase that interim
analysis used or the public site showed is at least 90% similar to it by
character. The endpoint's consistency readout is then also reported without the
twins, so the writeup can say how independent of the explore split the holdout
really was.

Definition, exactly as registered:

- Sealed set: ``seal_check.sealed_registry`` (Amendment 1 hash of the accepted
  clinical prompt over the Tier B ``pairs_<STAMP>`` batches; 183 phrases on
  2026-09-23). Labels are ``batch#index`` of the phrase's last occurrence, as the
  registry reports them.
- Comparison set, the union of (a) the explore split: the accepted clinical
  prompt (``top_prompt``) of every Tier B ``pairs_<STAMP>`` pair that is not in
  the sealed set; and (b) the phrases published on the site: every
  ``clinical_prompt`` string in the site's ``data/simulated_scenarios.json``
  (``scenarios[]``) and ``data/simulated_archive.json`` (the array), less any
  that is itself a sealed phrase (exact string, as the seal is defined).
- Normalization: ``seal_check.norm`` (lowercase, whitespace runs to one space,
  stripped), applied to both sides; the comparison set is deduplicated after it.
- Metric: ``difflib.SequenceMatcher(None, a, b).ratio()`` with difflib's
  defaults (autojunk on), ``a`` the sealed phrase and ``b`` the comparison
  phrase (the ratio is not symmetric in general, so the order is part of the
  definition). ``real_quick_ratio`` and ``quick_ratio`` are upper bounds of
  ``ratio`` and are used only to skip pairs that cannot reach the threshold.
- Threshold: a sealed phrase is a twin iff its best ratio is >= 0.90.

Every input row must carry its phrase. A batch pair that is not an object or
has no non-empty ``top_prompt`` string, a site row that is not an object or has
no non-empty ``clinical_prompt`` string, or a file of the wrong shape, stops the
run with ``MalformedInputError`` and a per-file count (exit 2, nothing
written): dropping such rows would shrink the comparison set without a word.

There is no randomness and no seed: the output depends only on the inputs,
whose fingerprints the output records under ``inputs``: the sha256 of every
Tier B batch file read (``batch_files_sha256``), of the dashboard file
(``dashboard_sha256``; the Routine rewrites it daily) and of its ``tierb``
block, the only part read (``dashboard_tierb_sha256``, canonical JSON: sorted
keys, compact separators, UTF-8), and of both site files, with the engine and
site commits. The commits alone do not identify the inputs: a dirty checkout
or a custom --simulated/--dashboard path reads other contents under the same
commit (Codex review of PR #32). The output carries labels and counts
only, never phrase text, and not the partner of each twin (naming it would
point at a near-copy of a sealed phrase).

Usage:
  python scripts/tierb_near_twins.py --site ../patientwords [--out data/tierb_near_twins.json]
  python scripts/tierb_near_twins.py --site ../patientwords --check   # recompute, compare, write nothing
"""

import argparse
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

try:  # invoked from the repo root vs loaded by path (tests)
    from scripts.seal_check import norm, sealed_registry
    from scripts.tierb_split import is_tierb_batch, tierb_start_stamp
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from seal_check import norm, sealed_registry
    from tierb_split import is_tierb_batch, tierb_start_stamp

THRESHOLD = 0.90
SITE_FILES = ("data/simulated_scenarios.json", "data/simulated_archive.json")
REGISTERED = "2026-09-23"


class MalformedInputError(ValueError):
    """An input file or row lacks the phrase the registered definition reads."""


def _phrases(rows: object, key: str, where: str, bad: dict[str, int]) -> list[str]:
    """``rows[i][key]`` for every row; a row that is not an object with a
    non-empty string there is counted against ``where`` in ``bad``, not skipped."""
    out: list[str] = []
    if not isinstance(rows, list):
        raise MalformedInputError(f"{where}: expected an array of rows, found {type(rows).__name__}")
    for row in rows:
        value = row.get(key) if isinstance(row, dict) else None
        if isinstance(value, str) and value.strip():
            out.append(value)
        else:
            bad[where] = bad.get(where, 0) + 1
    return out


def _refuse_bad(bad: dict[str, int], key: str) -> None:
    if bad:
        detail = "; ".join(f"{where}: {n} row(s)" for where, n in sorted(bad.items()))
        raise MalformedInputError(f"rows that are not objects with a non-empty {key} string: {detail}. "
                                  f"Refusing: skipping them would shrink the comparison set")


def tierb_batch_files(simulated_dir: str, start: str | None) -> list[Path]:
    """The Tier B ``pairs_<STAMP>`` batch files, the engine inputs both sets are drawn from."""
    if not start:
        return []
    return [bp for bp in sorted(Path(simulated_dir).glob("pairs_*.json"))
            if not bp.name.endswith(".report.json") and is_tierb_batch(bp.stem, start)]


def batch_phrases(simulated_dir: str, dashboard_path: str) -> list[str]:
    """The stripped accepted clinical prompt of every Tier B pairs_<STAMP> pair.
    Raises MalformedInputError on a batch pair without a top_prompt string."""
    out: list[str] = []
    bad: dict[str, int] = {}
    for bp in tierb_batch_files(simulated_dir, tierb_start_stamp(dashboard_path)):
        rows = json.loads(bp.read_text(encoding="utf-8"))
        out.extend(top.strip() for top in _phrases(rows, "top_prompt", bp.name, bad))
    _refuse_bad(bad, "top_prompt")
    return out


def explore_phrases(simulated_dir: str, dashboard_path: str, sealed: set[str]) -> list[str]:
    """Accepted clinical prompts of every Tier B pairs_<STAMP> pair outside the sealed set."""
    return [top for top in batch_phrases(simulated_dir, dashboard_path) if top not in sealed]


def site_phrases(site: str | Path) -> list[str]:
    """Every clinical_prompt string in the site's per-row payloads (SITE_FILES).

    A missing file is an error, not an empty list: the comparison set would
    silently shrink and the twin count with it. So is a payload of the wrong
    shape or a row without a clinical_prompt string (MalformedInputError)."""
    scenarios = json.loads((Path(site) / SITE_FILES[0]).read_text(encoding="utf-8"))
    archive = json.loads((Path(site) / SITE_FILES[1]).read_text(encoding="utf-8"))
    if not isinstance(scenarios, dict):
        raise MalformedInputError(f"{SITE_FILES[0]}: expected an object with a scenarios array")
    bad: dict[str, int] = {}
    out = [*_phrases(scenarios.get("scenarios"), "clinical_prompt", SITE_FILES[0], bad),
           *_phrases(archive, "clinical_prompt", SITE_FILES[1], bad)]
    _refuse_bad(bad, "clinical_prompt")
    return out


def near_twins(sealed: dict[str, str], comparison: list[str],
               threshold: float = THRESHOLD) -> list[str]:
    """Sorted labels of sealed phrases whose best ratio against the comparison
    set is >= threshold. ``sealed`` maps phrase -> label; ``comparison`` must
    already exclude the sealed phrases themselves (exact strings). A comparison
    phrase that differs from a sealed one only in case or spacing is a
    different string, so it stays and scores 1.0."""
    remaining: dict[str, list[str]] = {}
    for phrase, label in sorted(sealed.items(), key=lambda kv: kv[1]):
        remaining.setdefault(norm(phrase), []).append(label)
    candidates = sorted({norm(c) for c in comparison})
    twins: list[str] = []
    matcher = difflib.SequenceMatcher(None)
    for b in candidates:
        if not remaining:
            break
        matcher.set_seq2(b)
        for a in list(remaining):
            matcher.set_seq1(a)
            if (matcher.real_quick_ratio() >= threshold and matcher.quick_ratio() >= threshold
                    and matcher.ratio() >= threshold):
                twins.extend(remaining.pop(a))
    return sorted(twins)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git_head(repo: str | Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except (subprocess.CalledProcessError, OSError):
        return None


def compute(simulated_dir: str, dashboard_path: str, site: str | Path) -> dict:
    tierb_phrases = batch_phrases(simulated_dir, dashboard_path)   # validates every row first
    registry = sealed_registry(simulated_dir, dashboard_path)
    if not registry:
        raise SystemExit("CONFIG ERROR: the sealed set computes empty (null tierb.start_utc? wrong branch?)")
    sealed = set(registry)
    explore = [top for top in tierb_phrases if top not in sealed]
    published = [p for p in site_phrases(site) if p.strip() not in sealed]
    comparison = explore + published
    twins = near_twins(registry, comparison)

    dashboard_bytes = Path(dashboard_path).read_bytes()
    dashboard = json.loads(dashboard_bytes.decode("utf-8"))
    campaign = {Path(b.get("file", "")).stem for b in (dashboard.get("tierb") or {}).get("batches", [])}
    campaign_labels = {label for label in registry.values() if label.split("#")[0] in campaign}
    return {
        "_": ("Tier B Amendment 5 (registered 2026-09-23, before unsealing): the frozen list of sealed "
              "holdout phrases that have a near twin (difflib ratio >= 0.90 on seal_check.norm text) "
              "among the explore split's accepted prompts and the site's published clinical prompts. "
              "The endpoint's consistency readout is reported on the registered population and again "
              "without these labels. Labels and counts only; no phrase text, no partner labels. "
              "Recomputed by scripts/tierb_near_twins.py; never edited by hand."),
        "registered": REGISTERED,
        "amendment": "docs/prereg_amendment5_near_twins.md",
        "method": {
            "metric": "difflib.SequenceMatcher(None, a, b).ratio(), autojunk default",
            "a": "sealed phrase, normalized", "b": "comparison phrase, normalized",
            "normalization": "scripts/seal_check.py norm(): lowercase, whitespace runs to one space, strip",
            "threshold": THRESHOLD, "rule": "twin iff max ratio over the comparison set >= threshold",
            "sealed_set": "scripts/seal_check.py sealed_registry()",
            "comparison_set": ("explore split: accepted top_prompt of every Tier B pairs_<STAMP> pair not in "
                               "the sealed set; plus every clinical_prompt in the site's "
                               + " and ".join(SITE_FILES) + ", less sealed phrases; deduplicated after "
                               "normalization"),
            "seed": None, "deterministic": True,
        },
        "inputs": {
            "tierb_start_utc": (dashboard.get("tierb") or {}).get("start_utc"),
            "engine_head": _git_head(simulated_dir),
            "dashboard_sha256": hashlib.sha256(dashboard_bytes).hexdigest(),
            "dashboard_tierb_sha256": _sha256_json(dashboard.get("tierb")),
            "batch_files_sha256": {bp.name: _sha256_file(bp) for bp in
                                   tierb_batch_files(simulated_dir, tierb_start_stamp(dashboard_path))},
            "site_head": _git_head(site),
            "site_files_sha256": {f: _sha256_file(Path(site) / f) for f in SITE_FILES},
        },
        "counts": {
            "sealed_phrases": len(registry),
            "comparison_phrases": len({norm(c) for c in comparison}),
            "explore_split_phrases": len({norm(c) for c in explore}),
            "site_published_phrases": len({norm(c) for c in published}),
            "twins": len(twins),
            "remaining_after_pruning": len(registry) - len(twins),
            "campaign_sealed_phrases": len(campaign_labels),
            "campaign_twins": len(set(twins) & campaign_labels),
            "campaign_remaining_after_pruning": len(campaign_labels - set(twins)),
        },
        "twin_labels": twins,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="../patientwords")
    parser.add_argument("--simulated", default="data/simulated")
    parser.add_argument("--dashboard", default="ops/dashboard.json")
    parser.add_argument("--out", default="data/tierb_near_twins.json")
    parser.add_argument("--check", action="store_true",
                        help="recompute and compare the twin labels with --out; write nothing")
    args = parser.parse_args(argv)

    try:
        result = compute(args.simulated, args.dashboard, args.site)
    except MalformedInputError as exc:
        print(f"refused: {exc}; nothing was written or compared")
        return 2
    c = result["counts"]
    print(f"near twins: {c['twins']} of {c['sealed_phrases']} sealed phrases "
          f"({c['remaining_after_pruning']} remain); campaign {c['campaign_twins']} of "
          f"{c['campaign_sealed_phrases']} ({c['campaign_remaining_after_pruning']} remain); "
          f"{c['comparison_phrases']} comparison phrases")
    out = Path(args.out)
    if args.check:
        frozen = json.loads(out.read_text(encoding="utf-8"))
        if frozen.get("twin_labels") != result["twin_labels"]:
            gained = sorted(set(result["twin_labels"]) - set(frozen.get("twin_labels", [])))
            lost = sorted(set(frozen.get("twin_labels", [])) - set(result["twin_labels"]))
            print(f"MISMATCH with {out}: now also {gained}; no longer {lost}")
            return 1
        print(f"matches the frozen list in {out}")
        return 0
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
