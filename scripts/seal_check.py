"""Holdout-seal integrity check (audit 2026-07-21, R-C folded into the daily cycle).

Recomputes the Tier B sealed set via tierb_split (Amendment 1 split, Amendment 3
phrase-keyed widening) and sweeps published artifacts for any sealed phrase, by
whitespace/case-normalized substring match over the file's text and its decoded
views: HTML entities (a rendered page spells an apostrophe ``&#x27;``), JSON
string escapes (the payload exporter writes ASCII-escaped JSON) and, for CSV,
doubled quotes. A phrase that is not plain ASCII is also matched exactly, since
case-folding such text can change its length. The report NEVER contains phrase
text: hits are path + batch#index + count only (the report must not become the
leak).

What is not scanned, and why (rewritten 2026-09-23; history in
docs/prereg_divergence_log.md):

- The engine's registry sources: the ``--simulated`` directory, matched by
  RESOLVED path. The batch files there are where the sealed phrases are defined,
  so they are not leaks. Until 2026-09-23 this was a substring test on the path
  string ("data/simulated", "modes", ".git", "trace_out"), which also skipped
  the site's data/simulated_scenarios.json and data/simulated_archive.{json,csv},
  the site's whole modes/ render tree, and .github/.
- The engine's own measurement store: the ``--trace-out`` directory, by resolved
  path. Its batch summaries and renders carry every traced pair's prompts by
  construction; the seal is enforced by the consumers that drop holdout rows,
  and the store is append-only (AGENTS.md), so a hit there could never be
  remediated. None of the default roots contains it; the exclusion only matters
  when a caller sweeps the engine root. A directory named trace_out anywhere
  else (a site, a staging copy, a reviewer packet) is a copy and IS scanned.
- ``.git`` directories, by path component (history is not an artifact this
  check can remediate; the owner decides on history).

Allowlist (``--allowlist``, default data/seal_allowlist.json; owner rulings
only). An entry names a sealed label, the published row and field that contain
it, and the full sha256 of that containing field. The checker reads the field
from the registry sources, confirms the hash, and masks occurrences of that
exact field before matching the entry's sealed phrase, so any other occurrence
of the phrase, bare or inside different text, still flags. An entry is inactive,
and suppresses nothing, when its hash no longer matches, its label is not
sealed, its field does not contain the phrase, or its field is itself sealed.
The file stores no phrase text.

Exit codes: 0 clean, 1 leak found, 2 configuration problem (the sealed set
computes EMPTY - a checkout with a null tierb.start_utc does that - or the
allowlist file is malformed).

Usage:
  python scripts/seal_check.py [--site ../patientwords] [--dashboard ops/dashboard.json]
      [--simulated data/simulated] [--trace-out trace_out] [--extra docs,ops]
      [--allowlist data/seal_allowlist.json]
"""

import argparse
import hashlib
import html
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

try:  # invoked from the repo root (CLI/cycle) vs loaded by path (tests)
    from scripts.tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp

# .jsonl added 2026-09-16 (owner correction 9): the Petri lane publishes
# transcript, judgment and rule-outcome families as .jsonl, and a scan that
# skipped them would clear a leak it never read.
SCAN_SUFFIXES = {".json", ".jsonl", ".html", ".md", ".csv", ".txt", ".yml"}

_LABEL_RE = re.compile(r"^(?P<stem>[A-Za-z0-9_.\-]+)#(?P<index>[1-9][0-9]*)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOW_KEYS = ("label", "containing", "field", "sha256", "ruling_date", "reason")
_MASK = "\x00"  # not whitespace, so normalization cannot join text across a mask


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sealed_registry(simulated_dir: str, dashboard_path: str) -> dict[str, str]:
    """sealed phrase -> 'batch#index' label (labels only ever leave this module)."""
    start = tierb_start_stamp(dashboard_path)
    registry: dict[str, str] = {}
    if not start:
        return registry
    for bp in sorted(Path(simulated_dir).glob("pairs_*.json")):
        if bp.name.endswith(".report.json") or not is_tierb_batch(bp.stem, start):
            continue
        try:
            pairs = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for i, pair in enumerate(pairs, start=1):
            phrase = (pair.get("top_prompt") or "").strip()
            if phrase and is_holdout(phrase):
                registry[phrase] = f"{bp.stem}#{i}"
    return registry


# --------------------------------------------------------------------------- #
# Decoded views of a file's text
# --------------------------------------------------------------------------- #

_JSON_ESCAPE = re.compile(r'\\(?:u([0-9a-fA-F]{4})|(["\\/bfnrt]))')
_JSON_SIMPLE = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_SURROGATE = re.compile("[\ud800-\udfff]")


def json_unescape(text: str) -> str:
    """Undo JSON string escaping wherever it occurs in a larger text.

    Matches are consumed left to right, so an escaped backslash followed by
    ``u0041`` stays literal. Surrogate pairs written as two escapes are joined."""
    if "\\" not in text:
        return text
    out = _JSON_ESCAPE.sub(
        lambda m: chr(int(m.group(1), 16)) if m.group(1) else _JSON_SIMPLE[m.group(2)], text)
    if _SURROGATE.search(out):
        out = out.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    return out


def text_views(text: str, suffix: str = "") -> list[str]:
    """The text plus each distinct decoded spelling a publisher's encoder can
    give a phrase: HTML entities, JSON escapes, both orders of the two, and
    CSV's doubled quotes. Views equal to an earlier one are dropped."""
    views = [text]

    def add(view: str) -> None:
        if view not in views:
            views.append(view)

    unescaped = html.unescape(text) if "&" in text else text
    decoded = json_unescape(text)
    add(unescaped)
    add(decoded)
    add(json_unescape(unescaped))
    add(html.unescape(decoded) if "&" in decoded else decoded)
    if suffix == ".csv":
        add(text.replace('""', '"'))
    return views


# --------------------------------------------------------------------------- #
# Allowlist (owner rulings keyed on the containing field's sha256)
# --------------------------------------------------------------------------- #

@dataclass
class Allowlist:
    active: dict[str, list[str]] = field(default_factory=dict)   # sealed label -> containing texts
    entries: list[dict] = field(default_factory=list)            # the file's entries, as loaded
    notes: list[str] = field(default_factory=list)               # one line per inactive entry (labels only)


def load_allowlist(path: str | Path) -> list[dict]:
    """The entries of an allowlist file; [] when the file does not exist.

    Raises ValueError on a malformed file or entry, so a typo can never
    silently widen or narrow what the check suppresses."""
    p = Path(path)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{p}: not valid JSON ({exc.msg})") from exc
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{p}: expected an object with an 'entries' list")
    for n, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"{p}: entry {n} is not an object")
        missing = [k for k in _ALLOW_KEYS if not isinstance(entry.get(k), str) or not entry[k].strip()]
        if missing:
            raise ValueError(f"{p}: entry {n} lacks {', '.join(missing)}")
        for key in ("label", "containing"):
            if not _LABEL_RE.match(entry[key]):
                raise ValueError(f"{p}: entry {n} {key} is not batch#index")
        if not _SHA256_RE.match(entry["sha256"]):
            raise ValueError(f"{p}: entry {n} sha256 is not 64 lowercase hex digits (never a prefix)")
    return entries


def _containing_text(simulated_dir: str | Path, containing: str, field_name: str) -> str | None:
    m = _LABEL_RE.match(containing)
    if not m:
        return None
    try:
        rows = json.loads((Path(simulated_dir) / f"{m['stem']}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    index = int(m["index"])
    if not isinstance(rows, list) or index > len(rows) or not isinstance(rows[index - 1], dict):
        return None
    value = rows[index - 1].get(field_name)
    return value if isinstance(value, str) else None


def resolve_allowlist(entries: list[dict], registry: dict[str, str],
                      simulated_dir: str | Path) -> Allowlist:
    """Activate each entry whose containing field still hashes to its sha256,
    contains its sealed phrase, and is not itself sealed."""
    by_label = {label: phrase for phrase, label in registry.items()}
    allow = Allowlist(entries=list(entries))
    for entry in entries:
        where = f"{entry['label']} in {entry['containing']}.{entry['field']}"
        phrase = by_label.get(entry["label"])
        text = _containing_text(simulated_dir, entry["containing"], entry["field"])
        if phrase is None:
            reason = "label is not in the sealed registry"
        elif text is None:
            reason = "containing field not found in the registry sources"
        elif sha256_hex(text) != entry["sha256"]:
            reason = "containing field no longer matches its sha256"
        elif text in registry or text.strip() in registry or is_holdout(text):
            reason = "containing field is itself sealed"
        elif phrase not in text and norm(phrase) not in norm(text):
            reason = "containing field does not contain the sealed phrase"
        else:
            allow.active.setdefault(entry["label"], []).append(text)
            continue
        allow.notes.append(f"allowlist entry {where} INACTIVE ({reason}); it suppresses nothing")
    return allow


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #

def encoded_forms(text: str) -> list[str]:
    """The spellings a publisher's encoder can give a text (plain, JSON-escaped
    with and without ASCII escapes, HTML-escaped, CSV-quoted), longest first so
    masking replaces a whole escaped form before any shorter one inside it."""
    forms = {text, json.dumps(text)[1:-1], json.dumps(text, ensure_ascii=False)[1:-1],
             html.escape(text), html.escape(text, quote=False), text.replace('"', '""')}
    return sorted(forms, key=len, reverse=True)


def _mask(text: str, needles: list[str]) -> str:
    for needle in needles:
        if needle:
            text = text.replace(needle, _MASK)
    return text


def _found(phrase: str, views: list[str], nviews: list[str]) -> bool:
    nphrase = norm(phrase)
    if any(nphrase in v for v in nviews):
        return True
    # For ASCII text the normalized match subsumes the exact one; lower() on
    # other scripts can change lengths, so match those phrases exactly as well.
    return not phrase.isascii() and any(phrase in v for v in views)


def scan_text(text: str, registry: dict[str, str], allow: Allowlist | None = None,
              suffix: str = "") -> tuple[list[str], list[str]]:
    """(hit labels, allowlisted labels) for one text; never the phrase text.

    A label is allowlisted only when every occurrence of its phrase in the
    text lies inside an active containing field of that same label."""
    views = text_views(text, suffix)
    nviews = list(dict.fromkeys(norm(v) for v in views))
    hits: list[str] = []
    allowlisted: list[str] = []
    for phrase, label in registry.items():
        if not _found(phrase, views, nviews):
            continue
        containing = (allow.active.get(label) if allow else None) or []
        if containing:
            forms = [f for c in containing for f in encoded_forms(c)]
            nforms = sorted({norm(f) for f in forms}, key=len, reverse=True)
            masked = [_mask(v, forms) for v in views]
            nmasked = [_mask(v, nforms) for v in nviews]
            if not _found(phrase, masked, nmasked):
                allowlisted.append(label)
                continue
        hits.append(label)
    return hits, allowlisted


def scan_file(path: Path, registry: dict[str, str], allow: Allowlist | None = None) -> list[str]:
    """batch#index labels of sealed phrases found in this file (never the text)."""
    return scan_file_detail(path, registry, allow)[0]


def scan_file_detail(path: Path, registry: dict[str, str],
                     allow: Allowlist | None = None) -> tuple[list[str], list[str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []
    return scan_text(text, registry, allow, path.suffix.lower())


@dataclass
class Sweep:
    findings: dict[str, list[str]] = field(default_factory=dict)     # path -> hit labels
    allowlisted: dict[str, list[str]] = field(default_factory=dict)  # path -> suppressed labels
    files_scanned: int = 0


def _excluded(path: Path, excluded: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == d or resolved.is_relative_to(d) for d in excluded)


def _candidates(root: Path, excluded: list[Path]):
    if root.is_file():
        if root.suffix.lower() in SCAN_SUFFIXES and not _excluded(root, excluded):
            yield root
        return
    if not root.is_dir() or _excluded(root, excluded):
        return
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames
                             if d != ".git" and not _excluded(here / d, excluded))
        for name in sorted(filenames):
            p = here / name
            if p.suffix.lower() in SCAN_SUFFIXES and not _excluded(p, excluded):
                yield p


def scan_roots(roots: list[Path], registry: dict[str, str],
               exclude_dirs: list[str | Path] | tuple = (),
               allow: Allowlist | None = None) -> Sweep:
    """Sweep every scannable file under the roots, skipping only the given
    directories (by resolved path) and .git directories (by path component)."""
    excluded = [Path(d).resolve() for d in exclude_dirs]
    sweep = Sweep()
    for root in roots:
        for p in _candidates(Path(root), excluded):
            sweep.files_scanned += 1
            hits, allowlisted = scan_file_detail(p, registry, allow)
            if hits:
                sweep.findings[str(p)] = sorted(hits)
            if allowlisted:
                sweep.allowlisted[str(p)] = sorted(allowlisted)
    return sweep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="../patientwords")
    parser.add_argument("--dashboard", default="ops/dashboard.json")
    parser.add_argument("--simulated", default="data/simulated",
                        help="the engine's registry sources; excluded from the sweep by resolved path")
    parser.add_argument("--trace-out", default="trace_out",
                        help="the engine's own measurement store; excluded by resolved path")
    parser.add_argument("--extra", default="docs,ops",
                        help="comma-separated extra engine roots to sweep")
    parser.add_argument("--allowlist", default="data/seal_allowlist.json",
                        help="owner-ruled allowlist (absent file = no allowlist)")
    args = parser.parse_args(argv)

    registry = sealed_registry(args.simulated, args.dashboard)
    if not registry:
        print("seal check: CONFIG ERROR - sealed set computed EMPTY (null tierb.start_utc? "
              "wrong branch?). Run from the ops-truth working branch.")
        return 2
    try:
        entries = load_allowlist(args.allowlist)
    except ValueError as exc:
        print(f"seal check: CONFIG ERROR - allowlist malformed: {exc}")
        return 2
    allow = resolve_allowlist(entries, registry, args.simulated)

    roots = [Path(args.site)] + [Path(x.strip()) for x in args.extra.split(",") if x.strip()]
    sweep = scan_roots(roots, registry, exclude_dirs=[args.simulated, args.trace_out], allow=allow)
    if sweep.findings:
        print(f"seal check: LEAK - {sum(len(v) for v in sweep.findings.values())} sealed-phrase "
              f"hit(s) in {len(sweep.findings)} file(s):")
        for path, labels in sorted(sweep.findings.items()):
            print(f"  {path} :: {', '.join(labels)}")
        print("Breach protocol: stop publishing, follow the 2026-07-14 remediation "
              "precedent, put the hit list (paths+labels only) in the digest headline.")
    else:
        print(f"seal check: CLEAN - {len(registry)} sealed phrases, no hits across "
              f"{len(roots)} root(s) ({sweep.files_scanned} file(s) scanned)")
    if entries:
        rulings: dict[str, list[str]] = {}
        for e in entries:
            rulings.setdefault(e["label"], []).append(
                f"{e['containing']}.{e['field']} (ruling {e['ruling_date']})")
        print(f"allowlist: {sum(len(v) for v in allow.active.values())} of {len(entries)} "
              f"entr{'y' if len(entries) == 1 else 'ies'} active; "
              f"{len(sweep.allowlisted)} file(s) had only allowlisted occurrences")
        for path, labels in sorted(sweep.allowlisted.items()):
            why = "; ".join(f"{lab} inside {' or '.join(rulings[lab])}" for lab in labels)
            print(f"  allowlisted: {path} :: {why}")
        for note in allow.notes:
            print(f"  {note}")
    return 1 if sweep.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
