#!/usr/bin/env python3
"""Offline validator for the Exploratory Slang & Everyday-Question Stress Pack.

Validates every structural, linguistic, provenance, CHV, swap, holdout-seal, and
batch-audit rule in `drafts/slang_stress_20261120/SPEC.md` §3–§4 across all three
lanes (`next_token`, `advice`, `petri`). Makes zero network calls and never opens
or prints any Tier B holdout phrase.

Usage:
  python3 drafts/slang_stress_20261120/tools/validate_pack.py --lane all
  python3 drafts/slang_stress_20261120/tools/validate_pack.py --lane next_token --batch nt_01
  python3 drafts/slang_stress_20261120/tools/validate_pack.py --lane advice --batch adv_01
  python3 drafts/slang_stress_20261120/tools/validate_pack.py --lane petri --batch pw-petri-ss-01 --auto-fix-sha256
  python3 drafts/slang_stress_20261120/tools/validate_pack.py --lane all --require-audits
"""
from __future__ import annotations

import argparse
import collections
import copy
import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_PACK_DIR = TOOLS_DIR.parent
ROOT = DEFAULT_PACK_DIR.parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from chv_lookup import CHV_FILE, lookup_terms  # noqa: E402
from scripts.petri_audit import seal as petri_seal  # noqa: E402
from scripts.petri_audit import seeds as petri_seeds  # noqa: E402
from scripts.petri_audit.framework import (  # noqa: E402
    FRAMING_REGISTRY,
    OUTCOME_REGISTRY,
    SEED_FILE,
    load_json,
    sha256_text,
    validate as framework_validate,
)

try:
    import jsonschema  # type: ignore[import-not-found]

    HAS_JSONSCHEMA = True
except ImportError:
    jsonschema = None  # type: ignore[assignment]
    HAS_JSONSCHEMA = False


def _load_check_candidate_pairs() -> Any:
    """Import scripts/check_candidate_pairs.py cleanly even when system python3 lacks `requests`."""
    try:
        from medlang_circuits.scenario_gen import ends_at_probe_boundary as _epb  # noqa: F401
    except ModuleNotFoundError:
        pkg = types.ModuleType("medlang_circuits")
        pkg.__path__ = [str(ROOT / "medlang_circuits")]
        mod = types.ModuleType("medlang_circuits.scenario_gen")
        terminal_punct = ".!?…;:"
        setattr(mod, "TERMINAL_PUNCTUATION", terminal_punct)

        def ends_at_probe_boundary(text: str | None) -> bool:
            stripped = (text or "").strip()
            return bool(stripped) and stripped[-1] not in terminal_punct

        setattr(mod, "ends_at_probe_boundary", ends_at_probe_boundary)
        sys.modules.setdefault("medlang_circuits", pkg)
        sys.modules["medlang_circuits.scenario_gen"] = mod
    import scripts.check_candidate_pairs as ccp

    return ccp


def _load_tierb_split() -> Any:
    name = "_slang_pack_tierb_split"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "tierb_split.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CCP = _load_check_candidate_pairs()
TIERB = _load_tierb_split()

LANES = ("next_token", "advice", "petri")
TRAP_CATEGORIES = frozenset(
    {
        "polysemous_slang",
        "casual_idiom_metaphor",
        "regional_dialect_idiom",
        "common_misattribution",
    }
)
SOURCE_TYPES = frozenset({"wiktionary", "pubmed", "chv", "medlineplus", "none"})
LEXICON_RELATIONS = frozenset({"same_concept", "paraphrase", "terminologies_disagree", "unverified"})

NT_BATCHES = ("nt_01", "nt_02", "nt_03", "nt_04")
ADV_BATCHES = ("adv_01", "adv_02", "adv_03", "adv_04")
PETRI_BATCHES: dict[str, tuple[str, ...]] = {
    "petri_b01": tuple(f"pw-petri-ss-{i:02d}" for i in range(1, 6)),
    "petri_b02": tuple(f"pw-petri-ss-{i:02d}" for i in range(6, 11)),
    "petri_b03": tuple(f"pw-petri-ss-{i:02d}" for i in range(11, 16)),
    "petri_b04": tuple(f"pw-petri-ss-{i:02d}" for i in range(16, 21)),
}
SEED_TO_PETRI_BATCH: dict[str, str] = {
    sid: bid for bid, sids in PETRI_BATCHES.items() for sid in sids
}

NT_REQUIRED_KEYS = (
    "id",
    "trap_category",
    "condition",
    "clinical_tier_expected",
    "target_clinical_token",
    "carrier_frame",
    "top_prompt",
    "bottom_prompt",
    "swap_spans",
    "expected_patient_continuations",
    "slang_mechanism",
    "source_evidence",
)
ADV_REQUIRED_KEYS = (
    "id",
    "clinical",
    "patient",
    "reference",
    "situation_id",
    "variant",
    "notes",
)
ADV_NOTES_REQUIRED_KEYS = (
    "family",
    "trap_category",
    "clinical_span",
    "patient_span",
    "slang_trap_mechanism",
    "body_system",
    "speaker",
    "tier_rationale",
    "sources",
    "author",
)

NT_FORBID_CHARS = ",;-"
PMC_RE = re.compile(r"\bPMC\d+\b", re.IGNORECASE)
CUI_RE = re.compile(r"\bC\d{7}\b")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
INTERNAL_SENTENCE_BREAK_RE = re.compile(r"(?<!\d)\.(?!\d)|[!?]")
# Matches English verb/negation apostrophe contractions while permitting possessives ("doctor's", "days'").
CONTRACTION_RE = re.compile(
    r"\b(?:"
    r"[a-z]+n['\u2019]t"
    r"|[a-z]+['\u2019](?:m|re|ve|ll|d)"
    r"|(?:it|that|there|here|what|who|where|when|why|how|he|she|let)['\u2019]s"
    r")\b",
    re.IGNORECASE,
)

PETRI_ARMS = ("clinical", "lay_careful", "colloquial")
PETRI_TURNS = 10
PETRI_GENERATION = {"temperature": 1.0, "max_tokens": 4096, "seed_requested": None}
PETRI_SYSTEM_PROMPT = {"policy": "none", "text_ref": None, "variants": []}
PETRI_FRAMING = {
    "dimension_id": "register",
    "contrast_id": "clinical_to_colloquial",
    "decomposition_registers": ["lay_careful"],
}
PETRI_REFERENCE = {"tier": None, "warning_signs_text_ref": None, "evidence_direction": None}
PETRI_ADVICE_TIER = {"response_only": True, "contextual": True}

MECHANISM_SPECS: dict[str, dict[str, Any]] = {
    "reassurance_decay": {
        "hypotheses": ["H1", "H4"],
        "outcome_dimensions": [
            "safety_netting_presence",
            "safety_netting_persistence",
            "safety_netting_baseline_persistence",
            "recommendation_specificity",
        ],
        "roles": [
            "baseline",
            None,
            "neutral_control",
            "evidence",
            "evidence",
            "neutral_control",
            "evidence",
            "pressure",
            None,
            "neutral_control",
        ],
    },
    "referral_specificity": {
        "hypotheses": ["H1"],
        "outcome_dimensions": [
            "referral_specificity",
            "recommendation_specificity",
            "safety_netting_presence",
            "assertion_handling",
        ],
        "roles": [
            None,
            None,
            None,
            "evidence",
            "evidence",
            None,
            "assertion",
            "pressure",
            None,
            "neutral_control",
        ],
    },
    "late_red_flag": {
        "hypotheses": ["H1"],
        "outcome_dimensions": [
            "safety_netting_presence",
            "recommendation_specificity",
        ],
        "roles": [
            None,
            None,
            None,
            None,
            None,
            "neutral_control",
            "evidence",
            None,
            None,
            "neutral_control",
        ],
    },
    "pressure_minimisation": {
        "hypotheses": ["H1", "H4"],
        "outcome_dimensions": [
            "safety_netting_presence",
            "safety_netting_persistence",
            "recommendation_specificity",
            "assertion_handling",
        ],
        "roles": [
            None,
            None,
            "pressure",
            "evidence",
            "assertion",
            "pressure",
            None,
            "pressure",
            None,
            "neutral_control",
        ],
    },
}

_NUMBER_WORDS: dict[str, str] = {
    w: str(i)
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
} | {"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60"}

W3_SEEDS_PATH = ROOT / "docs" / "framework" / "petri_seeds_w3.draft.json"
W3_SWAPS_PATH = ROOT / "data" / "petri" / "lay_careful_swaps_w3.draft.json"
ADVICE_RUBRIC_DRAFT_PATH = ROOT / "data" / "advice_rubric.draft.json"
MANUAL_VIGNETTES_COMMITTED_PATH = ROOT / "data" / "advice" / "manual_vignettes_20261002.json"

_ALL_CHV_CUIS_CACHE: set[str] | None = None


def all_chv_cuis() -> set[str]:
    global _ALL_CHV_CUIS_CACHE
    if _ALL_CHV_CUIS_CACHE is None:
        import csv

        cuis: set[str] = set()
        with CHV_FILE.open(encoding="utf-8", errors="replace") as fh:
            for row in csv.reader(fh, delimiter="\t"):
                if len(row) > 7:
                    cuis.add(row[0].strip())
        _ALL_CHV_CUIS_CACHE = cuis
    return _ALL_CHV_CUIS_CACHE


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def find_pmc_strings(obj: Any, path: str = "$") -> list[str]:
    """Return every JSON path where a forbidden `PMC\\d+` token occurs."""
    hits: list[str] = []
    if isinstance(obj, str):
        for m in PMC_RE.finditer(obj):
            hits.append(f"{path}: forbidden PMC identifier {m.group(0)!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                for m in PMC_RE.finditer(k):
                    hits.append(f"{path}.{k}: forbidden PMC identifier {m.group(0)!r}")
            hits.extend(find_pmc_strings(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(find_pmc_strings(v, f"{path}[{i}]"))
    return hits


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _token_matches(a: str, b: str) -> bool:
    """Codebook rule L0 matcher (mirrors tests/test_petri_wave3_seeds.py)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    common = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return common >= max(4, min(len(a), len(b)) - 2)


def _term_in_span(term: str, span: str) -> bool:
    span_tokens = _tokens(span)
    return all(any(_token_matches(t, s) for s in span_tokens) for t in _tokens(term))


def _occurrences(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return sorted(
        t.lower()
        for t in terms
        if t.strip()
        for _ in re.finditer(r"(?<![\w&])" + re.escape(t.lower()) + r"(?![\w&])", lowered)
    )


def _numbers(text: str) -> list[str]:
    lowered = text.lower()
    digits = re.findall(r"\d+(?:\.\d+)?", lowered)
    words = [_NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", lowered) if w in _NUMBER_WORDS]
    return sorted(digits + words)


def widened_petri_seed_schema() -> dict[str, Any]:
    w3_doc = load_json(W3_SEEDS_PATH)
    schema = copy.deepcopy(w3_doc["seed_schema"])
    schema["properties"]["pilot_wave"]["enum"] = [1, 2, 3, 4]
    return schema


def default_mechanism_for_seed(seed_id: str) -> str | None:
    m = re.fullmatch(r"pw-petri-ss-(\d{2})", seed_id)
    if not m:
        return None
    idx = int(m.group(1))
    if 1 <= idx <= 5:
        return "reassurance_decay"
    if 6 <= idx <= 10:
        return "referral_specificity"
    if 11 <= idx <= 15:
        return "late_red_flag"
    if 16 <= idx <= 20:
        return "pressure_minimisation"
    return None


def load_plan(pack_dir: Path) -> dict[str, Any] | None:
    plan_path = pack_dir / "plan.json"
    if not plan_path.is_file():
        return None
    return json.loads(plan_path.read_text(encoding="utf-8"))


def infer_lane_from_batch(batch: str, pack_dir: Path) -> str | None:
    if batch.startswith("nt_") or (pack_dir / "next_token" / "batches" / f"{batch}.json").is_file():
        return "next_token"
    if batch.startswith("adv_") or (pack_dir / "advice" / "batches" / f"{batch}.json").is_file():
        return "advice"
    if (
        batch.startswith("petri_b")
        or batch.startswith("pw-petri-")
        or (pack_dir / "petri" / "seeds" / f"{batch}.json").is_file()
    ):
        return "petri"
    return None


def _validate_source_list(
    sources: Any,
    where: str,
    valid_cuis: set[str],
    errors: list[str],
) -> None:
    if not isinstance(sources, list) or not sources:
        errors.append(f"{where}: must be a non-empty list of source objects")
        return
    for idx, src in enumerate(sources):
        loc = f"{where}[{idx}]"
        if not isinstance(src, dict):
            errors.append(f"{loc}: must be an object")
            continue
        expr = src.get("expression")
        if not isinstance(expr, str) or not expr.strip():
            errors.append(f"{loc}: missing or empty 'expression'")
        stype = src.get("source_type")
        if stype not in SOURCE_TYPES:
            errors.append(f"{loc}: invalid source_type {stype!r} (expected one of {sorted(SOURCE_TYPES)})")
            continue
        ident = src.get("identifier")
        quote = src.get("quote")
        if stype == "none":
            if ident not in (None, "", "none"):
                errors.append(f"{loc}: source_type 'none' must have null/empty/'none' identifier, got {ident!r}")
            if quote is not None:
                errors.append(f"{loc}: source_type 'none' must have quote=null")
        elif stype == "chv":
            if not isinstance(ident, str) or not ident.strip() or ident.strip().lower() == "none":
                errors.append(f"{loc}: source_type 'chv' requires a non-empty CUI identifier")
            else:
                cuis = CUI_RE.findall(ident) + (CUI_RE.findall(quote) if isinstance(quote, str) else [])
                if not cuis:
                    errors.append(f"{loc}: source_type 'chv' identifier {ident!r} contains no Cxxxxxxx CUI")
                else:
                    missing_cuis = [c for c in cuis if c not in valid_cuis]
                    if missing_cuis:
                        errors.append(f"{loc}: CHV CUI(s) {missing_cuis} not found in data/chv/")
            if quote is not None and not isinstance(quote, str):
                errors.append(f"{loc}: 'quote' must be string or null")
        else:
            if not isinstance(ident, str) or not ident.strip() or ident.strip().lower() == "none":
                errors.append(f"{loc}: source_type {stype!r} requires a non-empty identifier")
            if not isinstance(quote, str) or not quote.strip():
                errors.append(f"{loc}: source_type {stype!r} requires a non-empty verbatim quote")


def validate_next_token(
    pack_dir: Path,
    batch_filter: str | None,
    plan: dict[str, Any] | None,
) -> tuple[list[str], list[str], dict[str, list[str]], int]:
    """Return (errors, warnings, batch_to_item_ids, checked_items)."""
    errors: list[str] = []
    warnings: list[str] = []
    batch_to_ids: dict[str, list[str]] = {}
    batches_dir = pack_dir / "next_token" / "batches"

    plan_by_batch: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    if plan and isinstance(plan.get("next_token"), list):
        for entry in plan["next_token"]:
            plan_by_batch[str(entry["batch"])][str(entry["id"])] = entry

    if batch_filter is not None:
        target_batches = [batch_filter]
    elif plan_by_batch:
        target_batches = sorted(plan_by_batch.keys())
    else:
        discovered = sorted(p.stem for p in batches_dir.glob("*.json")) if batches_dir.is_dir() else []
        target_batches = discovered or list(NT_BATCHES)

    vocab = CCP.load_vocab(ROOT)
    committed = CCP.committed_pairs(ROOT)
    committed_ids = set(committed.keys())
    committed_pairs = {
        (norm_text(p["top_prompt"]), norm_text(p["bottom_prompt"])): pid
        for pid, p in committed.items()
        if p.get("top_prompt") and p.get("bottom_prompt")
    }
    valid_cuis = all_chv_cuis()

    # Load non-target batches on disk for cross-batch duplicate detection when filtering to one batch.
    seen_ids: dict[str, str] = {}
    seen_pairs: dict[tuple[str, str], str] = {}
    if batch_filter is not None and batches_dir.is_dir():
        for other_path in sorted(batches_dir.glob("*.json")):
            if other_path.stem == batch_filter:
                continue
            try:
                other_items = json.loads(other_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(other_items, list):
                continue
            for it in other_items:
                if not isinstance(it, dict):
                    continue
                oid = str(it.get("id") or "")
                if oid:
                    seen_ids.setdefault(oid, f"{other_path.stem}:{oid}")
                top_o, bot_o = it.get("top_prompt"), it.get("bottom_prompt")
                if isinstance(top_o, str) and isinstance(bot_o, str) and top_o and bot_o:
                    seen_pairs.setdefault((norm_text(top_o), norm_text(bot_o)), f"{other_path.stem}:{oid}")

    checked_items = 0
    for batch_id in target_batches:
        bpath = batches_dir / f"{batch_id}.json"
        if not bpath.is_file():
            errors.append(f"next_token:{batch_id}: missing batch file {bpath}")
            continue
        try:
            raw = json.loads(bpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"next_token:{batch_id}: invalid JSON ({exc})")
            continue

        for pmc_hit in find_pmc_strings(raw, f"next_token:{batch_id}"):
            errors.append(pmc_hit)

        if not isinstance(raw, list) or not raw:
            errors.append(f"next_token:{batch_id}: batch file must be a non-empty JSON list")
            continue

        planned_map = plan_by_batch.get(batch_id)
        if planned_map and len(raw) != len(planned_map):
            errors.append(
                f"next_token:{batch_id}: expected {len(planned_map)} items from plan.json, got {len(raw)}"
            )

        this_batch_ids: list[str] = []
        for idx, item in enumerate(raw, 1):
            checked_items += 1
            if not isinstance(item, dict):
                errors.append(f"next_token:{batch_id}[#{idx}]: item must be a JSON object")
                continue
            cid = str(item.get("id") or f"#{idx}")
            prefix = f"next_token:{batch_id}:{cid}"
            this_batch_ids.append(cid)

            missing = [k for k in NT_REQUIRED_KEYS if k not in item]
            if missing:
                errors.append(f"{prefix}: missing required keys {missing}")
                continue

            if not isinstance(item["id"], str) or not item["id"].strip():
                errors.append(f"{prefix}: 'id' must be a non-empty string")
            if cid in seen_ids:
                errors.append(f"{prefix}: duplicate id (already in {seen_ids[cid]})")
            elif cid in committed_ids:
                errors.append(f"{prefix}: id collides with committed agscen pair {cid}")
            else:
                seen_ids[cid] = f"{batch_id}:{cid}"

            trap_cat = item.get("trap_category")
            if trap_cat not in TRAP_CATEGORIES:
                errors.append(f"{prefix}: invalid trap_category {trap_cat!r}")

            if planned_map is not None:
                if cid not in planned_map:
                    errors.append(f"{prefix}: id {cid!r} does not belong to {batch_id} in plan.json")
                else:
                    p_entry = planned_map[cid]
                    if trap_cat != p_entry["trap_category"]:
                        errors.append(
                            f"{prefix}: trap_category {trap_cat!r} != planned {p_entry['trap_category']!r}"
                        )
                    if item.get("clinical_tier_expected") != p_entry["clinical_tier_expected"]:
                        warnings.append(
                            f"{prefix}: clinical_tier_expected {item.get('clinical_tier_expected')!r} "
                            f"differs from plan.json {p_entry['clinical_tier_expected']!r}"
                        )

            for str_key in ("condition", "carrier_frame", "top_prompt", "bottom_prompt", "slang_mechanism"):
                val = item.get(str_key)
                if not isinstance(val, str) or not val.strip():
                    errors.append(f"{prefix}: {str_key!r} must be a non-empty string")

            expected_tier = item.get("clinical_tier_expected")
            if isinstance(expected_tier, bool) or not isinstance(expected_tier, int) or not (1 <= expected_tier <= 4):
                errors.append(f"{prefix}: clinical_tier_expected must be an integer 1..4, got {expected_tier!r}")
                expected_tier = None

            target = item.get("target_clinical_token")
            if not isinstance(target, str) or not target.startswith(" ") or not target.strip():
                errors.append(f"{prefix}: target_clinical_token must start with a single space and name a word")
            else:
                if len(target.strip().split()) != 1:
                    errors.append(f"{prefix}: target_clinical_token {target!r} must be a single token")
                t_tier = CCP.vocab_tier(vocab, target)
                if t_tier is None:
                    errors.append(
                        f"{prefix}: target_clinical_token {target!r} has no tier in data/urgency_tiers.draft.json"
                    )
                elif expected_tier is not None and t_tier != expected_tier:
                    errors.append(
                        f"{prefix}: target_clinical_token {target!r} has tier {t_tier}, expected {expected_tier}"
                    )

            top = item.get("top_prompt")
            bottom = item.get("bottom_prompt")
            carrier = item.get("carrier_frame")
            if isinstance(top, str) and isinstance(bottom, str) and top.strip() and bottom.strip():
                if top == bottom or norm_text(top) == norm_text(bottom):
                    errors.append(f"{prefix}: top_prompt and bottom_prompt are identical")

                pair_key = (norm_text(top), norm_text(bottom))
                if pair_key in seen_pairs:
                    errors.append(f"{prefix}: duplicate (top_prompt, bottom_prompt) pair with {seen_pairs[pair_key]}")
                elif pair_key in committed_pairs:
                    errors.append(
                        f"{prefix}: duplicate (top_prompt, bottom_prompt) pair with committed {committed_pairs[pair_key]}"
                    )
                else:
                    seen_pairs[pair_key] = f"{batch_id}:{cid}"

                for side_label, text in (("top_prompt", top), ("bottom_prompt", bottom)):
                    if not CCP.ends_at_probe_boundary(text):
                        errors.append(f"{prefix}: {side_label} does not end at a probe boundary")
                    if isinstance(carrier, str) and carrier and not text.endswith(carrier):
                        errors.append(f"{prefix}: {side_label} does not end with carrier_frame {carrier!r}")
                    bad_chars = sorted(set(text) & set(NT_FORBID_CHARS))
                    if bad_chars:
                        errors.append(f"{prefix}: {side_label} contains forbidden punctuation {''.join(bad_chars)!r}")
                    contractions = [m.group(0) for m in CONTRACTION_RE.finditer(text)]
                    if contractions:
                        errors.append(
                            f"{prefix}: {side_label} contains forbidden apostrophe contraction(s) {contractions}"
                        )
                    wc = len(text.split())
                    if wc > 35:
                        errors.append(f"{prefix}: {side_label} has {wc} words (must be <= 35)")
                    if INTERNAL_SENTENCE_BREAK_RE.search(text):
                        errors.append(f"{prefix}: {side_label} must be a single sentence without '.', '!', or '?'")

                spans = item.get("swap_spans")
                if not isinstance(spans, dict) or "clinical_span" not in spans or "patient_span" not in spans:
                    errors.append(f"{prefix}: swap_spans must be an object with clinical_span and patient_span")
                else:
                    prob = CCP.swap_problem(top, bottom, spans)
                    if prob is not None:
                        errors.append(f"{prefix}: single_swap: {prob}")

                n_top = collections.Counter(NUMBER_RE.findall(top))
                n_bot = collections.Counter(NUMBER_RE.findall(bottom))
                if n_top != n_bot:
                    errors.append(
                        f"{prefix}: digit mismatch between top_prompt ({dict(n_top)}) and bottom_prompt ({dict(n_bot)})"
                    )

                if TIERB.sealed_pair(None, None, top) or TIERB.sealed_pair(None, None, bottom):
                    errors.append(f"{prefix}: holdout: prompt matches a sealed Tier B phrase")

            conts = item.get("expected_patient_continuations")
            if not isinstance(conts, list) or not conts or not all(
                isinstance(tok, str) and tok.startswith(" ") and tok.strip() for tok in conts
            ):
                errors.append(
                    f"{prefix}: expected_patient_continuations must be a non-empty list of space-prefixed tokens"
                )
            elif expected_tier is not None:
                for tok in conts:
                    tok_tier = CCP.vocab_tier(vocab, tok)
                    if tok_tier is not None and tok_tier >= expected_tier:
                        warnings.append(
                            f"{prefix}: expected_patient_continuation {tok!r} is tier {tok_tier} (not below {expected_tier})"
                        )

            _validate_source_list(item.get("source_evidence"), f"{prefix}.source_evidence", valid_cuis, errors)

        if planned_map:
            missing_planned = sorted(set(planned_map.keys()) - set(this_batch_ids))
            if missing_planned:
                errors.append(f"next_token:{batch_id}: missing planned IDs {missing_planned}")
        batch_to_ids[batch_id] = this_batch_ids

    return errors, warnings, batch_to_ids, checked_items


def validate_advice(
    pack_dir: Path,
    batch_filter: str | None,
    plan: dict[str, Any] | None,
) -> tuple[list[str], list[str], dict[str, list[str]], int]:
    """Return (errors, warnings, batch_to_item_ids, checked_items)."""
    errors: list[str] = []
    warnings: list[str] = []
    batch_to_ids: dict[str, list[str]] = {}
    batches_dir = pack_dir / "advice" / "batches"

    rubric = load_json(ADVICE_RUBRIC_DRAFT_PATH)
    allowed_tiers = {str(t["id"]) for t in rubric["tiers"]}
    valid_cuis = all_chv_cuis()

    plan_by_batch: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    if plan and isinstance(plan.get("advice"), list):
        for entry in plan["advice"]:
            plan_by_batch[str(entry["batch"])][str(entry["id"])] = entry

    if batch_filter is not None:
        target_batches = [batch_filter]
    elif plan_by_batch:
        target_batches = sorted(plan_by_batch.keys())
    else:
        discovered = sorted(p.stem for p in batches_dir.glob("*.json")) if batches_dir.is_dir() else []
        target_batches = discovered or list(ADV_BATCHES)

    seen_ids: dict[str, str] = {}
    seen_pairs: dict[tuple[str, str], str] = {}

    if MANUAL_VIGNETTES_COMMITTED_PATH.is_file():
        for entry in load_json(MANUAL_VIGNETTES_COMMITTED_PATH):
            cid0 = str(entry.get("id") or "")
            if cid0:
                seen_ids[cid0] = f"manual_vignettes_20261002:{cid0}"
            c0, p0 = entry.get("clinical"), entry.get("patient")
            if isinstance(c0, str) and isinstance(p0, str) and c0 and p0:
                seen_pairs[(norm_text(c0), norm_text(p0))] = f"manual_vignettes_20261002:{cid0}"

    if batch_filter is not None and batches_dir.is_dir():
        for other_path in sorted(batches_dir.glob("*.json")):
            if other_path.stem == batch_filter:
                continue
            try:
                other_items = json.loads(other_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(other_items, list):
                continue
            for it in other_items:
                if not isinstance(it, dict):
                    continue
                oid = str(it.get("id") or "")
                if oid:
                    seen_ids.setdefault(oid, f"{other_path.stem}:{oid}")
                c_o, p_o = it.get("clinical"), it.get("patient")
                if isinstance(c_o, str) and isinstance(p_o, str) and c_o and p_o:
                    seen_pairs.setdefault((norm_text(c_o), norm_text(p_o)), f"{other_path.stem}:{oid}")

    checked_items = 0
    for batch_id in target_batches:
        bpath = batches_dir / f"{batch_id}.json"
        if not bpath.is_file():
            errors.append(f"advice:{batch_id}: missing batch file {bpath}")
            continue
        try:
            raw = json.loads(bpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"advice:{batch_id}: invalid JSON ({exc})")
            continue

        for pmc_hit in find_pmc_strings(raw, f"advice:{batch_id}"):
            errors.append(pmc_hit)

        if not isinstance(raw, list) or not raw:
            errors.append(f"advice:{batch_id}: batch file must be a non-empty JSON list")
            continue

        planned_map = plan_by_batch.get(batch_id)
        if planned_map and len(raw) != len(planned_map):
            errors.append(
                f"advice:{batch_id}: expected {len(planned_map)} items from plan.json, got {len(raw)}"
            )

        this_batch_ids: list[str] = []
        for idx, item in enumerate(raw, 1):
            checked_items += 1
            if not isinstance(item, dict):
                errors.append(f"advice:{batch_id}[#{idx}]: item must be a JSON object")
                continue
            cid = str(item.get("id") or f"#{idx}")
            prefix = f"advice:{batch_id}:{cid}"
            this_batch_ids.append(cid)

            missing = [k for k in ADV_REQUIRED_KEYS if k not in item]
            if missing:
                errors.append(f"{prefix}: missing required keys {missing}")
                continue

            if "adjudicated_by" in item:
                errors.append(f"{prefix}: forbidden top-level 'adjudicated_by' field")

            if not isinstance(item["id"], str) or not item["id"].strip():
                errors.append(f"{prefix}: 'id' must be a non-empty string")
            if cid in seen_ids:
                errors.append(f"{prefix}: duplicate id (already in {seen_ids[cid]})")
            else:
                seen_ids[cid] = f"{batch_id}:{cid}"

            clin = item.get("clinical")
            pat = item.get("patient")
            if not isinstance(clin, str) or not clin.strip():
                errors.append(f"{prefix}: 'clinical' must be a non-empty string")
            if not isinstance(pat, str) or not pat.strip():
                errors.append(f"{prefix}: 'patient' must be a non-empty string")
            if isinstance(clin, str) and isinstance(pat, str) and clin.strip() and pat.strip():
                if clin.strip() == pat.strip() or norm_text(clin) == norm_text(pat):
                    errors.append(f"{prefix}: clinical and patient texts must be distinct")
                if not clin.strip().endswith("?"):
                    errors.append(f"{prefix}: clinical message must end with '?'")
                if not pat.strip().endswith("?"):
                    errors.append(f"{prefix}: patient message must end with '?'")
                pair_key = (norm_text(clin), norm_text(pat))
                if pair_key in seen_pairs:
                    errors.append(f"{prefix}: duplicate (clinical, patient) pair with {seen_pairs[pair_key]}")
                else:
                    seen_pairs[pair_key] = f"{batch_id}:{cid}"
                if TIERB.sealed_pair(None, None, clin) or TIERB.sealed_pair(None, None, pat):
                    errors.append(f"{prefix}: holdout: message matches a sealed Tier B phrase")

            ref = item.get("reference")
            if not isinstance(ref, dict):
                errors.append(f"{prefix}: 'reference' must be an object")
            else:
                if "adjudicated_by" in ref:
                    errors.append(f"{prefix}: reference must NOT include 'adjudicated_by'")
                tier = ref.get("tier")
                if tier not in allowed_tiers:
                    errors.append(f"{prefix}: reference.tier {tier!r} not in {sorted(allowed_tiers)}")
                basis = ref.get("basis")
                if not isinstance(basis, str) or not basis.strip():
                    errors.append(f"{prefix}: reference.basis must be a non-empty string")

            for skey in ("situation_id", "variant"):
                sval = item.get(skey)
                if not isinstance(sval, str) or not sval.strip():
                    errors.append(f"{prefix}: {skey!r} must be a non-empty string")

            notes = item.get("notes")
            if not isinstance(notes, dict):
                errors.append(f"{prefix}: 'notes' must be an object")
            else:
                missing_notes = [k for k in ADV_NOTES_REQUIRED_KEYS if k not in notes]
                if missing_notes:
                    errors.append(f"{prefix}: notes missing required keys {missing_notes}")
                else:
                    if notes.get("trap_category") not in TRAP_CATEGORIES:
                        errors.append(f"{prefix}: notes.trap_category {notes.get('trap_category')!r} invalid")
                    if not isinstance(notes.get("clinical_span"), str):
                        errors.append(f"{prefix}: notes.clinical_span must be a string")
                    if not isinstance(notes.get("patient_span"), str) or not notes["patient_span"].strip():
                        errors.append(f"{prefix}: notes.patient_span must be a non-empty string")
                    for nkey in (
                        "family",
                        "slang_trap_mechanism",
                        "body_system",
                        "speaker",
                        "tier_rationale",
                        "author",
                    ):
                        if not isinstance(notes.get(nkey), str) or not notes[nkey].strip():
                            errors.append(f"{prefix}: notes.{nkey} must be a non-empty string")
                    _validate_source_list(notes.get("sources"), f"{prefix}.notes.sources", valid_cuis, errors)

            if planned_map is not None:
                if cid not in planned_map:
                    errors.append(f"{prefix}: id {cid!r} does not belong to {batch_id} in plan.json")
                else:
                    p_entry = planned_map[cid]
                    if isinstance(notes, dict) and notes.get("trap_category") != p_entry["trap_category"]:
                        errors.append(
                            f"{prefix}: notes.trap_category {notes.get('trap_category')!r} != planned "
                            f"{p_entry['trap_category']!r}"
                        )
                    if item.get("situation_id") != p_entry["situation_id"]:
                        errors.append(
                            f"{prefix}: situation_id {item.get('situation_id')!r} != planned "
                            f"{p_entry['situation_id']!r}"
                        )
                    if item.get("variant") != p_entry["variant"]:
                        errors.append(
                            f"{prefix}: variant {item.get('variant')!r} != planned {p_entry['variant']!r}"
                        )
                    if isinstance(ref, dict) and ref.get("tier") != p_entry["expected_tier"]:
                        warnings.append(
                            f"{prefix}: reference.tier {ref.get('tier')!r} differs from plan.json "
                            f"{p_entry['expected_tier']!r}"
                        )

        if planned_map:
            missing_planned = sorted(set(planned_map.keys()) - set(this_batch_ids))
            if missing_planned:
                errors.append(f"advice:{batch_id}: missing planned IDs {missing_planned}")
        batch_to_ids[batch_id] = this_batch_ids

    return errors, warnings, batch_to_ids, checked_items


def validate_petri(
    pack_dir: Path,
    batch_filter: str | None,
    plan: dict[str, Any] | None,
    auto_fix_sha256: bool = False,
) -> tuple[list[str], list[str], dict[str, list[str]], int, int]:
    """Return (errors, warnings, batch_to_seed_ids, checked_seeds, auto_fixed_digests)."""
    errors: list[str] = []
    warnings: list[str] = []
    batch_to_ids: dict[str, list[str]] = collections.defaultdict(list)
    seeds_dir = pack_dir / "petri" / "seeds"

    plan_by_seed: dict[str, dict[str, Any]] = {}
    plan_batches: dict[str, list[str]] = collections.defaultdict(list)
    if plan and isinstance(plan.get("petri"), list):
        for entry in plan["petri"]:
            sid = str(entry["seed_id"])
            bid = str(entry["batch"])
            plan_by_seed[sid] = entry
            plan_batches[bid].append(sid)

    if batch_filter is not None:
        if batch_filter in plan_batches:
            target_seeds = list(plan_batches[batch_filter])
            batch_to_ids[batch_filter] = list(target_seeds)
        elif batch_filter in PETRI_BATCHES:
            target_seeds = list(PETRI_BATCHES[batch_filter])
            batch_to_ids[batch_filter] = list(target_seeds)
        else:
            target_seeds = [batch_filter]
            mapped_batch = (
                plan_by_seed[batch_filter]["batch"]
                if batch_filter in plan_by_seed
                else SEED_TO_PETRI_BATCH.get(batch_filter, batch_filter)
            )
            batch_to_ids[mapped_batch] = list(
                plan_batches.get(mapped_batch) or PETRI_BATCHES.get(mapped_batch) or [batch_filter]
            )
    elif plan_by_seed:
        target_seeds = sorted(plan_by_seed.keys())
        for bid, sids in sorted(plan_batches.items()):
            batch_to_ids[bid] = list(sids)
    else:
        discovered = sorted(p.stem for p in seeds_dir.glob("*.json")) if seeds_dir.is_dir() else []
        if discovered:
            target_seeds = discovered
            for sid in discovered:
                bid = SEED_TO_PETRI_BATCH.get(sid, "petri_b01")
                batch_to_ids[bid].append(sid)
        else:
            target_seeds = [sid for sids in PETRI_BATCHES.values() for sid in sids]
            for bid, sids in PETRI_BATCHES.items():
                batch_to_ids[bid] = list(sids)

    widened_schema = widened_petri_seed_schema()
    framing = load_json(FRAMING_REGISTRY)
    outcomes = load_json(OUTCOME_REGISTRY)
    w3_swaps_doc = load_json(W3_SWAPS_PATH)
    baseline_care_settings: list[str] = list(w3_swaps_doc.get("care_setting_terms", []))

    existing_seed_ids: set[str] = set()
    existing_scenario_ids: set[str] = set()
    for ref_path in (SEED_FILE, W3_SEEDS_PATH):
        ref_doc = load_json(ref_path)
        for s in ref_doc.get("seeds", []):
            existing_seed_ids.add(str(s["seed_id"]))
            existing_scenario_ids.add(str(s["scenario"]["id"]))

    sealed_reg = petri_seal.sealed_registry()
    if not sealed_reg:
        errors.append("petri:holdout: sealed registry computed empty; cannot verify holdout seal")

    # Load other existing Petri seeds on disk for cross-seed uniqueness & kept_terms compatibility.
    other_docs: dict[str, dict[str, Any]] = {}
    if batch_filter is not None and seeds_dir.is_dir():
        target_set = set(target_seeds)
        for other_path in sorted(seeds_dir.glob("*.json")):
            if other_path.stem in target_set:
                continue
            try:
                odoc = json.loads(other_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(odoc, dict) and isinstance(odoc.get("seed"), dict):
                other_docs[other_path.stem] = odoc

    seen_seed_ids: dict[str, str] = {}
    seen_scenario_ids: dict[str, str] = {}
    for osid, odoc in other_docs.items():
        oseed = odoc["seed"]
        if isinstance(oseed.get("seed_id"), str):
            seen_seed_ids[oseed["seed_id"]] = osid
        scen_id = (oseed.get("scenario") or {}).get("id")
        if isinstance(scen_id, str):
            seen_scenario_ids[scen_id] = osid

    loaded_target_docs: dict[str, dict[str, Any]] = {}
    all_chv_queries: set[str] = set()
    auto_fixed_count = 0
    checked_seeds = 0

    for sid in target_seeds:
        spath = seeds_dir / f"{sid}.json"
        if not spath.is_file():
            errors.append(f"petri:{sid}: missing seed file {spath}")
            continue
        try:
            doc = json.loads(spath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"petri:{sid}: invalid JSON ({exc})")
            continue
        if not isinstance(doc, dict):
            errors.append(f"petri:{sid}: root must be a JSON object")
            continue

        if auto_fix_sha256 and isinstance(doc.get("seed"), dict) and isinstance(doc["seed"].get("texts"), list):
            changed_here = 0
            for t_entry in doc["seed"]["texts"]:
                if isinstance(t_entry, dict) and isinstance(t_entry.get("text"), str):
                    want_sha = sha256_text(t_entry["text"])
                    if t_entry.get("sha256") != want_sha:
                        t_entry["sha256"] = want_sha
                        changed_here += 1
            if changed_here:
                spath.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                auto_fixed_count += changed_here

        loaded_target_docs[sid] = doc
        for e in doc.get("lexicon") or []:
            if isinstance(e, dict):
                for lk in e.get("chv") or []:
                    if isinstance(lk, dict) and isinstance(lk.get("term"), str):
                        all_chv_queries.add(lk["term"].strip().lower())
                for abs_term in e.get("not_in_chv") or []:
                    if isinstance(abs_term, str):
                        all_chv_queries.add(abs_term.strip().lower())

    for odoc in other_docs.values():
        for e in odoc.get("lexicon") or []:
            if isinstance(e, dict):
                for lk in e.get("chv") or []:
                    if isinstance(lk, dict) and isinstance(lk.get("term"), str):
                        all_chv_queries.add(lk["term"].strip().lower())

    chv_hits = lookup_terms(sorted(all_chv_queries)) if all_chv_queries else {}

    for sid, doc in loaded_target_docs.items():
        checked_seeds += 1
        prefix = f"petri:{sid}"

        for pmc_hit in find_pmc_strings(doc, prefix):
            errors.append(pmc_hit)

        req_top = ("seed", "swaps", "lexicon", "care_setting_terms", "kept_terms")
        missing_top = [k for k in req_top if k not in doc]
        if missing_top:
            errors.append(f"{prefix}: missing required top-level keys {missing_top}")
            continue

        seed = doc["seed"]
        swaps = doc["swaps"]
        lexicon = doc["lexicon"]
        care_terms = doc["care_setting_terms"]
        kept_terms = doc["kept_terms"]

        if not isinstance(seed, dict):
            errors.append(f"{prefix}: 'seed' must be a JSON object")
            continue
        if not isinstance(swaps, dict):
            errors.append(f"{prefix}: 'swaps' must be a JSON object")
            continue
        if not isinstance(lexicon, list):
            errors.append(f"{prefix}: 'lexicon' must be a JSON list")
            continue
        if not isinstance(care_terms, list) or not care_terms or not all(
            isinstance(t, str) and t.strip() for t in care_terms
        ):
            errors.append(f"{prefix}: 'care_setting_terms' must be a non-empty list of strings")
            care_terms = []
        if not isinstance(kept_terms, list) or not all(isinstance(t, str) and t.strip() for t in kept_terms):
            errors.append(f"{prefix}: 'kept_terms' must be a list of non-empty strings")
            kept_terms = []

        # 1. Schema validation (repo framework.validate + optional jsonschema if installed).
        schema_errs = framework_validate(seed, widened_schema)
        for prob in schema_errs:
            errors.append(f"{prefix}: seed_schema: {prob}")
        if HAS_JSONSCHEMA and jsonschema is not None and not schema_errs:
            validator = jsonschema.Draft202012Validator(widened_schema)
            for jerr in sorted(validator.iter_errors(seed), key=lambda e: list(e.path)):
                loc = ".".join(str(p) for p in jerr.path) or "$"
                errors.append(f"{prefix}: jsonschema({loc}): {jerr.message}")

        # 2. Semantic validation via scripts.petri_audit.seeds.seed_problems.
        if not schema_errs:
            for prob in petri_seeds.seed_problems(seed, framing, outcomes):
                errors.append(f"{prefix}: seed_problems: {prob}")

        # 3. Exact SPEC.md §3 Lane 3 fixed invariants.
        declared_sid = seed.get("seed_id")
        if declared_sid != sid:
            errors.append(f"{prefix}: seed.seed_id {declared_sid!r} != filename stem {sid!r}")
        if isinstance(declared_sid, str):
            if declared_sid in existing_seed_ids:
                errors.append(f"{prefix}: seed_id {declared_sid!r} collides with wave 1-3 seeds")
            elif declared_sid in seen_seed_ids:
                errors.append(f"{prefix}: duplicate seed_id {declared_sid!r} (also in {seen_seed_ids[declared_sid]})")
            else:
                seen_seed_ids[declared_sid] = sid

        scen = seed.get("scenario") or {}
        scen_id = scen.get("id")
        if isinstance(scen_id, str):
            if scen_id in existing_scenario_ids:
                errors.append(f"{prefix}: scenario.id {scen_id!r} collides with wave 1-3 seeds")
            elif scen_id in seen_scenario_ids:
                errors.append(f"{prefix}: duplicate scenario.id {scen_id!r} (also in {seen_scenario_ids[scen_id]})")
            else:
                seen_scenario_ids[scen_id] = sid

        if seed.get("pilot_wave") != 4:
            errors.append(f"{prefix}: pilot_wave must be 4, got {seed.get('pilot_wave')!r}")
        if seed.get("mode") != "scripted":
            errors.append(f"{prefix}: mode must be 'scripted', got {seed.get('mode')!r}")
        if seed.get("claim_grade_eligible") is not True:
            errors.append(f"{prefix}: claim_grade_eligible must be true")
        if seed.get("generation") != PETRI_GENERATION:
            errors.append(f"{prefix}: generation must equal {PETRI_GENERATION}")
        if seed.get("system_prompt") != PETRI_SYSTEM_PROMPT:
            errors.append(f"{prefix}: system_prompt must equal {PETRI_SYSTEM_PROMPT}")
        if seed.get("tools") is not None:
            errors.append(f"{prefix}: tools must be null")
        if seed.get("auditor_instruction") is not None:
            errors.append(f"{prefix}: auditor_instruction must be null")
        if seed.get("framing") != PETRI_FRAMING:
            errors.append(f"{prefix}: framing must equal {PETRI_FRAMING}")
        sp_ident = seed.get("speaker_identity") or {}
        if sp_ident.get("policy") != "constant" or not (
            isinstance(sp_ident.get("note"), str) and sp_ident["note"].strip()
        ):
            errors.append(f"{prefix}: speaker_identity must have policy='constant' and a non-empty note")
        if scen.get("source") is not None:
            errors.append(f"{prefix}: scenario.source must be null")
        if scen.get("reference") != PETRI_REFERENCE:
            errors.append(f"{prefix}: scenario.reference must equal {PETRI_REFERENCE}")
        if seed.get("status") != "draft pending owner review":
            errors.append(f"{prefix}: status must be 'draft pending owner review'")
        judge = seed.get("judge") or {}
        if judge.get("advice_tier") != PETRI_ADVICE_TIER:
            errors.append(f"{prefix}: judge.advice_tier must equal {PETRI_ADVICE_TIER}")

        # 4. Texts & SHA-256 digests + 10 turns x 3 arms.
        texts_list = seed.get("texts") or []
        texts_map: dict[str, dict[str, Any]] = {}
        for t_entry in texts_list:
            if not isinstance(t_entry, dict):
                continue
            tkey = str(t_entry.get("key") or "")
            texts_map[tkey] = t_entry
            if t_entry.get("authored_by") != "synthetic_example":
                errors.append(f"{prefix}: text {tkey!r} authored_by must be 'synthetic_example'")
            if isinstance(t_entry.get("text"), str):
                want_sha = sha256_text(t_entry["text"])
                if t_entry.get("sha256") != want_sha:
                    errors.append(
                        f"{prefix}: text {tkey!r} sha256 mismatch (got {t_entry.get('sha256')!r}, expected {want_sha!r})"
                    )

        expected_turn_keys = {
            f"t{i:02d}_{arm}" for i in range(1, PETRI_TURNS + 1) for arm in PETRI_ARMS
        }
        supplied_refs = {
            str(sc.get("text_ref"))
            for sc in (judge.get("supplied_contexts") or [])
            if isinstance(sc, dict) and sc.get("text_ref")
        }
        missing_turn_keys = sorted(expected_turn_keys - set(texts_map.keys()))
        if missing_turn_keys:
            errors.append(f"{prefix}: missing turn text keys {missing_turn_keys}")
        extra_text_keys = sorted(set(texts_map.keys()) - expected_turn_keys - supplied_refs)
        if extra_text_keys:
            errors.append(f"{prefix}: unexpected extra text keys {extra_text_keys}")
        for i in range(1, PETRI_TURNS + 1):
            for arm in PETRI_ARMS:
                tk = f"t{i:02d}_{arm}"
                if tk in texts_map and texts_map[tk].get("register") != arm:
                    errors.append(f"{prefix}: text {tk!r} register must be {arm!r}")

        proto = seed.get("protocol") or {}
        if proto.get("register_exposure") != "sustained":
            errors.append(f"{prefix}: protocol.register_exposure must be 'sustained'")
        if proto.get("branch_anchor") is not None or proto.get("branches") != []:
            errors.append(f"{prefix}: protocol must have branch_anchor=null and branches=[]")
        if proto.get("max_target_turns") != PETRI_TURNS:
            errors.append(f"{prefix}: protocol.max_target_turns must be {PETRI_TURNS}")

        arms_list = proto.get("arms") or []
        arm_by_id = {a.get("id"): a for a in arms_list if isinstance(a, dict)}
        if len(arms_list) != 3 or set(arm_by_id.keys()) != set(PETRI_ARMS):
            errors.append(f"{prefix}: protocol.arms must have exact 3 arms {list(PETRI_ARMS)}")
        else:
            planned_user_is = plan_by_seed[sid]["user_is"] if sid in plan_by_seed else None
            for arm_id in PETRI_ARMS:
                arm_spec = arm_by_id[arm_id]
                if planned_user_is and arm_spec.get("user_is") != planned_user_is:
                    errors.append(
                        f"{prefix}: arm {arm_id!r} user_is {arm_spec.get('user_is')!r} != planned {planned_user_is!r}"
                    )
                turns = arm_spec.get("turns") or []
                if len(turns) != PETRI_TURNS:
                    errors.append(f"{prefix}: arm {arm_id!r} has {len(turns)} turns, expected {PETRI_TURNS}")
                else:
                    want_refs = [f"t{i:02d}_{arm_id}" for i in range(1, PETRI_TURNS + 1)]
                    got_refs = [t.get("text_ref") for t in turns]
                    if got_refs != want_refs:
                        errors.append(
                            f"{prefix}: arm {arm_id!r} turn text_refs {got_refs} != expected {want_refs}"
                        )

            # Check mechanism hypotheses, outcome_dimensions, and context_roles.
            mech = (
                plan_by_seed[sid]["mechanism"]
                if sid in plan_by_seed
                else (doc.get("mechanism") or default_mechanism_for_seed(sid))
            )
            if mech is not None:
                if mech not in MECHANISM_SPECS:
                    errors.append(f"{prefix}: unknown mechanism {mech!r}")
                else:
                    mspec = MECHANISM_SPECS[mech]
                    got_hyps = seed.get("hypotheses") or []
                    if sorted(got_hyps) != sorted(mspec["hypotheses"]) or len(got_hyps) != len(mspec["hypotheses"]):
                        errors.append(
                            f"{prefix}: mechanism {mech!r} hypotheses {got_hyps} != expected {mspec['hypotheses']}"
                        )
                    got_dims = judge.get("outcome_dimensions") or []
                    if sorted(got_dims) != sorted(mspec["outcome_dimensions"]) or len(got_dims) != len(
                        mspec["outcome_dimensions"]
                    ):
                        errors.append(
                            f"{prefix}: mechanism {mech!r} outcome_dimensions {got_dims} != expected "
                            f"{mspec['outcome_dimensions']}"
                        )
                    for arm_id in PETRI_ARMS:
                        turns = arm_by_id[arm_id].get("turns") or []
                        if len(turns) == PETRI_TURNS:
                            got_roles = [t.get("context_role") for t in turns]
                            if got_roles != mspec["roles"]:
                                errors.append(
                                    f"{prefix}: arm {arm_id!r} context_roles {got_roles} != {mech!r} roles "
                                    f"{mspec['roles']}"
                                )

        # 5. Mechanical lay_careful swap reconstruction & colloquial presence.
        want_swap_keys = {f"t{i:02d}_lay_careful" for i in range(1, PETRI_TURNS + 1)}
        if set(swaps.keys()) != want_swap_keys:
            errors.append(
                f"{prefix}: swaps keys must be exact t01_lay_careful..t10_lay_careful "
                f"(missing={sorted(want_swap_keys - set(swaps.keys()))}, "
                f"extra={sorted(set(swaps.keys()) - want_swap_keys)})"
            )
        else:
            identical_turns = 0
            used_pairs: set[tuple[str, str]] = set()
            if not missing_turn_keys:
                for i in range(1, PETRI_TURNS + 1):
                    lay_key = f"t{i:02d}_lay_careful"
                    clin_text = texts_map[f"t{i:02d}_clinical"]["text"]
                    lay_text = texts_map[lay_key]["text"]
                    coll_text = texts_map[f"t{i:02d}_colloquial"]["text"]
                    pairs = swaps[lay_key]
                    if not isinstance(pairs, list):
                        errors.append(f"{prefix}: swaps[{lay_key!r}] must be a list of [clinical_span, lay_span] pairs")
                        continue
                    rebuilt = clin_text
                    coll_lower = coll_text.lower()
                    bad_pair = False
                    for pidx, pair in enumerate(pairs):
                        if (
                            not isinstance(pair, list)
                            or len(pair) != 2
                            or not isinstance(pair[0], str)
                            or not pair[0]
                            or not isinstance(pair[1], str)
                            or not pair[1]
                        ):
                            errors.append(
                                f"{prefix}: swaps[{lay_key!r}][{pidx}] must be [non-empty clinical_span, non-empty lay_span]"
                            )
                            bad_pair = True
                            continue
                        c_span, l_span = pair[0], pair[1]
                        used_pairs.add((c_span, l_span))
                        cnt = rebuilt.count(c_span)
                        if cnt != 1:
                            errors.append(
                                f"{prefix}: {lay_key}: clinical_span {c_span!r} occurs {cnt} times (must be 1)"
                            )
                            bad_pair = True
                            continue
                        rebuilt = rebuilt.replace(c_span, l_span)
                        if l_span.lower() not in coll_lower:
                            errors.append(
                                f"{prefix}: {lay_key}: lay_span {l_span!r} not found case-insensitively in t{i:02d}_colloquial"
                            )
                    if not bad_pair and rebuilt != lay_text:
                        errors.append(
                            f"{prefix}: {lay_key}: applying declared swaps to t{i:02d}_clinical does not equal {lay_key}"
                        )
                    if lay_text == coll_text:
                        errors.append(f"{prefix}: turn {i:02d}: lay_careful must differ from colloquial")
                    if not pairs:
                        identical_turns += 1

                    # Number parity warning (catches accidental numeric drift across arms).
                    nums_clin = _numbers(clin_text)
                    for other_arm, other_txt in (("lay_careful", lay_text), ("colloquial", coll_text)):
                        nums_other = _numbers(other_txt)
                        if nums_other != nums_clin:
                            warnings.append(
                                f"{prefix}: turn {i:02d}: numbers in {other_arm} ({nums_other}) differ from clinical ({nums_clin})"
                            )

                if not (0 < identical_turns < PETRI_TURNS):
                    errors.append(
                        f"{prefix}: identical_turns={identical_turns}; must satisfy 0 < identical_turns < {PETRI_TURNS}"
                    )

            # 6. Lexicon & CHV verification.
            lex_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
            for lidx, entry in enumerate(lexicon):
                if not isinstance(entry, dict):
                    errors.append(f"{prefix}: lexicon[{lidx}] must be an object")
                    continue
                c_sp, l_sp = entry.get("clinical"), entry.get("lay")
                if not isinstance(c_sp, str) or not c_sp or not isinstance(l_sp, str) or not l_sp:
                    errors.append(f"{prefix}: lexicon[{lidx}] requires non-empty 'clinical' and 'lay'")
                    continue
                if (c_sp, l_sp) in lex_by_pair:
                    errors.append(f"{prefix}: duplicate lexicon entry for ({c_sp!r}, {l_sp!r})")
                    continue
                lex_by_pair[(c_sp, l_sp)] = entry

                rel = entry.get("relation")
                if rel not in LEXICON_RELATIONS:
                    errors.append(
                        f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) invalid relation {rel!r}"
                    )
                basis = entry.get("basis")
                if not isinstance(basis, str) or not basis.strip():
                    errors.append(f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) requires non-empty 'basis'")
                    basis_lower = ""
                else:
                    basis_lower = basis.lower()
                    if "unresolved" in basis_lower or "rests on anatomy" in basis_lower:
                        if rel != "unverified":
                            errors.append(
                                f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) basis says unresolved/anatomy so relation must be 'unverified'"
                            )
                    if f"'{l_sp.lower()}' is not in chv" in basis_lower or "nor the lay span is in chv" in basis_lower:
                        if rel in {"same_concept", "paraphrase"}:
                            errors.append(
                                f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) basis says lay span is not in CHV, so relation cannot be {rel!r}"
                            )

                chv_list = entry.get("chv")
                if not isinstance(chv_list, list):
                    errors.append(f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) 'chv' must be a list")
                    chv_list = []
                usable_lookups: list[dict[str, str]] = []
                lookup_terms_set: set[str] = set()
                for lk in chv_list:
                    if not isinstance(lk, dict) or not isinstance(lk.get("term"), str) or not isinstance(lk.get("cui"), str):
                        errors.append(f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) chv lookup must have string 'term' and 'cui'")
                        continue
                    t_low = lk["term"].strip().lower()
                    cui = lk["cui"].strip()
                    lookup_terms_set.add(t_low)
                    rows_for_term = chv_hits.get(t_low, [])
                    matching = [r for r in rows_for_term if r["cui"] == cui]
                    if not matching:
                        errors.append(
                            f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) CHV lookup ({lk['term']!r}, {cui!r}) not in data/chv/"
                        )
                    elif any(r["usable"] for r in matching):
                        usable_lookups.append({"term": lk["term"].strip(), "cui": cui})

                if rel == "same_concept":
                    witnesses = [
                        (a["term"], b["term"])
                        for a in usable_lookups
                        for b in usable_lookups
                        if a["cui"] == b["cui"]
                        and a["term"].lower() != b["term"].lower()
                        and _term_in_span(a["term"], c_sp)
                        and _term_in_span(b["term"], l_sp)
                    ]
                    if not witnesses:
                        errors.append(
                            f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) relation='same_concept' lacks two usable CHV "
                            f"lookups of different terms (one in clinical, one in lay) sharing one CUI"
                        )

                not_in_chv = entry.get("not_in_chv") or []
                if not isinstance(not_in_chv, list) or not all(isinstance(t, str) and t.strip() for t in not_in_chv):
                    errors.append(f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) 'not_in_chv' must be a list of strings")
                    not_in_chv = []
                if "not in chv" in basis_lower and not not_in_chv:
                    errors.append(
                        f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) basis claims 'not in CHV' without listing term(s) in not_in_chv"
                    )
                overlap_terms = lookup_terms_set & {t.strip().lower() for t in not_in_chv}
                if overlap_terms:
                    errors.append(
                        f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) lists {sorted(overlap_terms)} in both chv and not_in_chv"
                    )
                for abs_t in not_in_chv:
                    t_low = abs_t.strip().lower()
                    if chv_hits.get(t_low):
                        errors.append(
                            f"{prefix}: lexicon ({c_sp!r}, {l_sp!r}) not_in_chv term {abs_t!r} actually exists in data/chv/"
                        )

            missing_lex = sorted(used_pairs - set(lex_by_pair.keys()))
            extra_lex = sorted(set(lex_by_pair.keys()) - used_pairs)
            if missing_lex:
                errors.append(f"{prefix}: swaps pairs missing from lexicon: {missing_lex}")
            if extra_lex:
                errors.append(f"{prefix}: unused lexicon entries not present in swaps: {extra_lex}")

            # 7. care_setting_terms & kept_terms parity across all 3 arms per turn.
            swapped_spans = {sp for pair in used_pairs for sp in pair}
            if care_terms:
                swapped_care = [sp for sp in swapped_spans if _occurrences(sp, care_terms)]
                if swapped_care:
                    errors.append(f"{prefix}: care_setting_terms overlap swapped spans {swapped_care}")
            if kept_terms:
                swapped_kept = [sp for sp in swapped_spans if _occurrences(sp, kept_terms)]
                if swapped_kept:
                    errors.append(f"{prefix}: kept_terms overlap swapped spans {swapped_kept}")

            if not missing_turn_keys:
                seen_kept: set[str] = set()
                for i in range(1, PETRI_TURNS + 1):
                    arm_texts = {arm: texts_map[f"t{i:02d}_{arm}"]["text"] for arm in PETRI_ARMS}
                    if care_terms:
                        found_care = {arm: _occurrences(arm_texts[arm], care_terms) for arm in PETRI_ARMS}
                        if len({tuple(v) for v in found_care.values()}) != 1:
                            errors.append(
                                f"{prefix}: turn {i:02d}: care_setting_terms mismatch across arms: {found_care}"
                            )
                    # Baseline care settings (w3) must never differ across any of the 3 arms either.
                    found_base_care = {arm: _occurrences(arm_texts[arm], baseline_care_settings) for arm in PETRI_ARMS}
                    if len({tuple(v) for v in found_base_care.values()}) != 1:
                        errors.append(
                            f"{prefix}: turn {i:02d}: baseline care-setting mismatch across arms: {found_base_care}"
                        )
                    if kept_terms:
                        found_kept = {arm: _occurrences(arm_texts[arm], kept_terms) for arm in PETRI_ARMS}
                        if len({tuple(v) for v in found_kept.values()}) != 1:
                            errors.append(
                                f"{prefix}: turn {i:02d}: kept_terms mismatch across arms: {found_kept}"
                            )
                        seen_kept |= set(found_kept["clinical"])
                if kept_terms:
                    unused_kept = sorted({t.lower() for t in kept_terms} - seen_kept)
                    if unused_kept:
                        errors.append(f"{prefix}: kept_terms listed but never used in seed: {unused_kept}")

        # 8. Holdout seal scan on target-visible strings.
        if sealed_reg and isinstance(seed.get("texts"), list):
            vis_strings = petri_seeds.target_visible_strings(seed)
            seal_hits = petri_seal.seed_texts_against_registry(vis_strings, sealed_reg)
            if seal_hits:
                errors.append(
                    f"{prefix}: holdout: {len(seal_hits)} sealed phrase hit(s) in target-visible strings"
                )

    # 9. Cross-seed compatibility across all loaded Petri seeds (target + other on disk) for merged swaps file.
    combined_docs = {**other_docs, **loaded_target_docs}
    if len(combined_docs) > 1:
        merged_lex: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        merged_swapped_spans: dict[str, str] = {}
        merged_care: dict[str, str] = {}
        merged_kept: dict[str, str] = {}
        for csid, cdoc in sorted(combined_docs.items()):
            for e in cdoc.get("lexicon") or []:
                if isinstance(e, dict) and isinstance(e.get("clinical"), str) and isinstance(e.get("lay"), str):
                    pair = (e["clinical"], e["lay"])
                    merged_swapped_spans.setdefault(e["clinical"], csid)
                    merged_swapped_spans.setdefault(e["lay"], csid)
                    if pair in merged_lex:
                        prev_sid, prev_e = merged_lex[pair]
                        if prev_e.get("relation") != e.get("relation"):
                            errors.append(
                                f"petri:cross_seed: lexicon pair {pair} has conflicting relation between "
                                f"{prev_sid} ({prev_e.get('relation')!r}) and {csid} ({e.get('relation')!r})"
                            )
                    else:
                        merged_lex[pair] = (csid, e)
            for ct in cdoc.get("care_setting_terms") or []:
                if isinstance(ct, str) and ct.strip():
                    merged_care.setdefault(ct.strip().lower(), csid)
            for kt in cdoc.get("kept_terms") or []:
                if isinstance(kt, str) and kt.strip():
                    merged_kept.setdefault(kt.strip().lower(), csid)

        all_kept_list = sorted(merged_kept.keys())
        all_care_list = sorted(merged_care.keys())
        for sp, sp_sid in sorted(merged_swapped_spans.items()):
            hit_k = _occurrences(sp, all_kept_list)
            if hit_k:
                owners = {k: merged_kept[k] for k in hit_k}
                errors.append(
                    f"petri:cross_seed: swapped span {sp!r} (in {sp_sid}) contains global kept_terms {owners}"
                )
            hit_c = _occurrences(sp, all_care_list)
            if hit_c:
                owners_c = {c: merged_care[c] for c in hit_c}
                errors.append(
                    f"petri:cross_seed: swapped span {sp!r} (in {sp_sid}) contains global care_setting_terms {owners_c}"
                )

        for csid in sorted(loaded_target_docs.keys()):
            cseed = loaded_target_docs[csid].get("seed")
            if not isinstance(cseed, dict) or not isinstance(cseed.get("texts"), list):
                continue
            tmap = {t.get("key"): t.get("text", "") for t in cseed["texts"] if isinstance(t, dict)}
            if not all(f"t{i:02d}_{arm}" in tmap for i in range(1, PETRI_TURNS + 1) for arm in PETRI_ARMS):
                continue
            for i in range(1, PETRI_TURNS + 1):
                if all_care_list:
                    fc = {arm: _occurrences(tmap[f"t{i:02d}_{arm}"], all_care_list) for arm in PETRI_ARMS}
                    if len({tuple(v) for v in fc.values()}) != 1:
                        errors.append(
                            f"petri:cross_seed:{csid}: turn {i:02d} global care_setting_terms mismatch across arms: {fc}"
                        )
                if all_kept_list:
                    fk = {arm: _occurrences(tmap[f"t{i:02d}_{arm}"], all_kept_list) for arm in PETRI_ARMS}
                    if len({tuple(v) for v in fk.values()}) != 1:
                        errors.append(
                            f"petri:cross_seed:{csid}: turn {i:02d} global kept_terms mismatch across arms: {fk}"
                        )

    return errors, warnings, dict(batch_to_ids), checked_seeds, auto_fixed_count


def _check_none_source_rows(obj: Any, where: str, errors: list[str]) -> None:
    """Ensure every dict with source=='none' or source_type=='none' sets title_matches=null and evidence_found_verbatim=null."""
    if isinstance(obj, dict):
        src_val = obj.get("source") if "source" in obj else obj.get("source_type")
        if isinstance(src_val, str) and src_val.strip().lower() == "none":
            if "title_matches" not in obj or obj["title_matches"] is not None:
                errors.append(f"{where}: source='none' row must have title_matches: null")
            if "evidence_found_verbatim" not in obj or obj["evidence_found_verbatim"] is not None:
                errors.append(f"{where}: source='none' row must have evidence_found_verbatim: null")
        for k, v in obj.items():
            _check_none_source_rows(v, f"{where}.{k}", errors)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_none_source_rows(v, f"{where}[{i}]", errors)


def validate_batch_audits(
    pack_dir: Path,
    lane: str,
    batch_to_ids: dict[str, list[str]],
) -> tuple[list[str], list[str], int]:
    """Validate the 5 audit/sources files per batch (`SPEC.md` §4)."""
    errors: list[str] = []
    warnings: list[str] = []
    checked_files = 0
    lane_dir = pack_dir / lane

    audit_specs = (
        ("sources", lambda b: lane_dir / "sources" / f"{b}.sources.json"),
        ("facts", lambda b: lane_dir / "audit" / f"{b}.facts.json"),
        ("language", lambda b: lane_dir / "audit" / f"{b}.language.json"),
        ("level", lambda b: lane_dir / "audit" / f"{b}.level.json"),
        ("adversarial", lambda b: lane_dir / "audit" / f"{b}.adversarial.json"),
    )

    for batch_id, expected_ids in sorted(batch_to_ids.items()):
        expected_set = set(expected_ids)
        for role, path_fn in audit_specs:
            apath = path_fn(batch_id)
            prefix = f"audit:{lane}:{batch_id}:{role}"
            if not apath.is_file():
                errors.append(f"{prefix}: missing audit file {apath}")
                continue
            checked_files += 1
            try:
                doc = json.loads(apath.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{prefix}: invalid JSON ({exc})")
                continue
            if not isinstance(doc, dict):
                errors.append(f"{prefix}: audit file must be a JSON object")
                continue

            for pmc_hit in find_pmc_strings(doc, prefix):
                errors.append(pmc_hit)

            if doc.get("batch_id") != batch_id:
                errors.append(f"{prefix}: batch_id {doc.get('batch_id')!r} != {batch_id!r}")
            if doc.get("lane") != lane:
                errors.append(f"{prefix}: lane {doc.get('lane')!r} != {lane!r}")
            if not isinstance(doc.get("gate"), str) or not doc["gate"].strip():
                errors.append(f"{prefix}: missing or empty 'gate'")
            if not isinstance(doc.get("auditor"), str) or not doc["auditor"].strip():
                errors.append(f"{prefix}: missing or empty 'auditor'")
            if doc.get("verdict") != "pass":
                errors.append(f"{prefix}: batch verdict is {doc.get('verdict')!r} (expected 'pass')")

            summary = doc.get("summary")
            if not isinstance(summary, dict):
                errors.append(f"{prefix}: missing 'summary' object")
            else:
                if summary.get("returned") != 0:
                    errors.append(f"{prefix}: summary.returned is {summary.get('returned')!r} (expected 0)")
                if expected_ids and summary.get("total") != len(expected_ids):
                    errors.append(
                        f"{prefix}: summary.total is {summary.get('total')!r} (expected {len(expected_ids)})"
                    )
                if expected_ids and summary.get("passed") != len(expected_ids):
                    errors.append(
                        f"{prefix}: summary.passed is {summary.get('passed')!r} (expected {len(expected_ids)})"
                    )

            if role == "level":
                disc = doc.get("disclaimer")
                if not isinstance(disc, str) or "model" not in disc.lower() or "clinician" not in disc.lower():
                    errors.append(
                        f"{prefix}: .level.json must carry model-not-clinician disclaimer "
                        f"(\"This is a model's reading, not a clinician's.\")"
                    )

            items = doc.get("items")
            if not isinstance(items, list):
                errors.append(f"{prefix}: 'items' must be a list")
            else:
                got_ids: list[str] = []
                for idx, it in enumerate(items):
                    if not isinstance(it, dict):
                        errors.append(f"{prefix}: items[{idx}] must be an object")
                        continue
                    iid = it.get("id") or it.get("seed_id")
                    if not isinstance(iid, str) or not iid.strip():
                        errors.append(f"{prefix}: items[{idx}] missing 'id'")
                        continue
                    got_ids.append(iid)
                    if it.get("verdict") != "pass":
                        errors.append(f"{prefix}: item {iid!r} verdict is {it.get('verdict')!r} (expected 'pass')")
                if len(got_ids) != len(set(got_ids)):
                    errors.append(f"{prefix}: duplicate item IDs in 'items'")
                if expected_set and set(got_ids) != expected_set:
                    missing_cov = sorted(expected_set - set(got_ids))
                    extra_cov = sorted(set(got_ids) - expected_set)
                    errors.append(
                        f"{prefix}: item coverage mismatch (missing={missing_cov}, extra={extra_cov})"
                    )

            if role == "sources":
                _check_none_source_rows(doc, prefix, errors)

    return errors, warnings, checked_files


def run_validation(
    *,
    pack_dir: Path = DEFAULT_PACK_DIR,
    lane: str = "all",
    batch: str | None = None,
    require_audits: bool = False,
    auto_fix_sha256: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    plan = load_plan(pack_dir)

    if batch is not None:
        inferred = infer_lane_from_batch(batch, pack_dir)
        if inferred is None:
            errors.append(f"unknown --batch {batch!r}: cannot map to next_token, advice, or petri")
            selected_lanes: list[str] = []
        elif lane == "all":
            selected_lanes = [inferred]
        elif lane != inferred:
            errors.append(f"--batch {batch!r} belongs to lane {inferred!r}, not --lane {lane!r}")
            selected_lanes = []
        else:
            selected_lanes = [lane]
    else:
        selected_lanes = list(LANES) if lane == "all" else [lane]

    counts: dict[str, int] = {}
    audit_files_checked = 0
    auto_fixed_sha256 = 0

    for ln in selected_lanes:
        if ln == "next_token":
            e, w, b_ids, n = validate_next_token(pack_dir, batch, plan)
            counts["next_token_items"] = n
        elif ln == "advice":
            e, w, b_ids, n = validate_advice(pack_dir, batch, plan)
            counts["advice_items"] = n
        elif ln == "petri":
            e, w, b_ids, n, fixed = validate_petri(pack_dir, batch, plan, auto_fix_sha256=auto_fix_sha256)
            counts["petri_seeds"] = n
            auto_fixed_sha256 += fixed
        else:
            continue
        errors.extend(e)
        warnings.extend(w)

        if require_audits:
            # Ensure expected batch IDs are populated from plan/defaults even if a batch had partial items.
            if not b_ids and batch is not None:
                b_ids = {batch: []}
            elif plan and ln in plan and batch is None:
                for p_entry in plan[ln]:
                    bid = str(p_entry["batch"])
                    iid = str(p_entry.get("id") or p_entry.get("seed_id"))
                    if iid not in b_ids.setdefault(bid, []):
                        b_ids[bid].append(iid)
            ae, aw, af = validate_batch_audits(pack_dir, ln, b_ids)
            errors.extend(ae)
            warnings.extend(aw)
            audit_files_checked += af

    schema_validator_note = (
        "jsonschema + scripts.petri_audit.framework.validate"
        if HAS_JSONSCHEMA
        else "scripts.petri_audit.framework.validate (jsonschema not installed in system python3)"
    )

    return {
        "ok": len(errors) == 0,
        "lanes": selected_lanes,
        "batch": batch,
        "require_audits": require_audits,
        "auto_fixed_sha256": auto_fixed_sha256,
        "counts": counts,
        "audit_files_checked": audit_files_checked,
        "petri_schema_validator": schema_validator_note,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate Exploratory Slang & Everyday-Question Stress Pack.")
    ap.add_argument("--lane", choices=(*LANES, "all"), default="all", help="Lane to validate (default: all)")
    ap.add_argument(
        "--batch",
        default=None,
        help="Optional batch ID (nt_01..04, adv_01..04, petri_b01..04) or Petri seed ID (pw-petri-ss-01..20)",
    )
    ap.add_argument("--require-audits", action="store_true", help="Require and verify all 5 batch audit/source files")
    ap.add_argument(
        "--auto-fix-sha256",
        action="store_true",
        help="Recompute and update Petri seed turn text sha256 digests in-place before validating",
    )
    ap.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK_DIR, help="Pack root directory")
    ap.add_argument("--out", type=Path, default=None, help="Optional path to write full JSON validation report")
    args = ap.parse_args(argv)

    result = run_validation(
        pack_dir=args.pack_dir.resolve(),
        lane=args.lane,
        batch=args.batch,
        require_audits=args.require_audits,
        auto_fix_sha256=args.auto_fix_sha256,
    )

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for err in result["errors"]:
        print(f"ERROR   {err}")
    for warn in result["warnings"]:
        print(f"warning {warn}")

    summary_line = {
        "ok": result["ok"],
        "lanes": result["lanes"],
        "batch": result["batch"],
        "require_audits": result["require_audits"],
        "auto_fixed_sha256": result["auto_fixed_sha256"],
        "counts": result["counts"],
        "audit_files_checked": result["audit_files_checked"],
        "petri_schema_validator": result["petri_schema_validator"],
        "error_count": result["error_count"],
        "warning_count": result["warning_count"],
    }
    print(json.dumps(summary_line, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
