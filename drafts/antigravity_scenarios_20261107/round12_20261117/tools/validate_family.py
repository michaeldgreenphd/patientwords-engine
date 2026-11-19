#!/usr/bin/env python3
"""Deterministic offline validator for Round 12 case-family drafts and audit gates.

Enforces Round 12 SPEC.md sections 3, 4, 5, 7, 8, and 10 without network calls or model providers:
  - Plain register families only (right_care in {2, 3, 4}, lexicon_entries == [], zero dialect/folk forms)
  - Zero contractions (active first-person 'I ', 'Im ', or 'My '; no apostrophe contractions; only
    noun possessives like "doctor's" or "parents'" keep an apostrophe)
  - <= 40 words, single unpunctuated sentence ending in carrier_frame, zero ',;-', digits for numbers
  - Diagnosis never named in prompt text; zero self-harm/suicide content
  - Single continuous swap_spans within 2 words; single-fact changed_fact control (Rules A & D,
    plus <= 1 emergency control moving to level 4 through bleeding per batch)
  - No repeated condition or prompt text across Rounds 9, 10, 11 (batches 01-06), and Round 12
  - No repeated changed_fact.to across Round 11 (batches 01-06) and Round 12 (Rule D)
  - Citation format, Rule B structure, source_fit_rows, <= 3 stated negatives per batch

Compatible with Python 3.9+ (sandbox system Python) and Python 3.12+ (.venv).
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any

ROUND12_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_ROOT = ROUND12_DIR.parent
ROUND11_DIR = SCENARIOS_ROOT / "round11_20261114"
DEFAULT_LEXICON_PATH = SCENARIOS_ROOT / "lexicon" / "dialect_lexicon_20261109.json"
DEFAULT_R9_PATH = SCENARIOS_ROOT / "round9_20261110" / "families.json"
DEFAULT_R10_PATH = SCENARIOS_ROOT / "round10_20261112_rev1" / "families.json"
DEFAULT_PLAN_PATH = ROUND12_DIR / "plan.json"
DEFAULT_LEDGER_PATH = ROUND12_DIR / "ledger.json"
DEFAULT_URGENCY_TIERS_PATH = Path("/Users/michaelgreen/pw-main/data/urgency_tiers.draft.json")

FAMILY_ID_RE = re.compile(r"^r12-(?:0(?:0[1-9]|[1-3]\d|4[0-8])|b0[12]-rep[1-6])$")
BATCH_NAME_RE = re.compile(r"^batch_0([12])$")

# Round 12 has only care levels 4, 3, and 2 (no self-care L1 families).
ALLOWED_CARE_SPECS: dict[int, set[tuple[str, str]]] = {
    4: {
        ("so I need to go to the", " ER"),
        ("so I need to go to the", " hospital"),
    },
    3: {
        ("so I should see a", " specialist"),
        ("so I should see a", " dentist"),
        ("so I should see a", " dermatologist"),
        ("so I should see a", " psychiatrist"),
        ("so I should see a", " therapist"),
    },
    2: {
        ("so I should see a", " doctor"),
        ("so I need to go to the", " clinic"),
    },
}

REQUIRED_FAMILY_KEYS = (
    "family_id",
    "condition",
    "right_care",
    "level_rationale",
    "carrier_frame",
    "target_token",
    "reference_facts",
    "texts",
    "changed_fact",
    "swap_spans",
    "swap_note",
    "everyday_sources",
    "equity_dimension",
    "lexicon_entries",
    "protocol_flags",
    "design_note",
)
OPTIONAL_FAMILY_KEYS = ("attribution", "fact_map")

REQUIRED_TEXT_KEYS = (
    "medical",
    "everyday",
    "medical_paraphrase",
    "everyday_paraphrase",
    "changed_fact",
)
OPTIONAL_TEXT_KEYS = (
    "everyday_attribution",
    "quad_b",
    "quad_c",
)
ALL_TEXT_KEYS_ORDERED = REQUIRED_TEXT_KEYS + OPTIONAL_TEXT_KEYS

EVERYDAY_SOURCE_KEYS = (
    "expression",
    "source",
    "title",
    "pmid_or_doi",
    "inspected_url",
    "access",
    "location",
    "quote_type",
    "evidence",
    "adaptation",
)
ATTRIBUTION_KEYS = (
    "clause",
    "explains",
    "source",
    "title",
    "pmid_or_doi",
    "inspected_url",
    "access",
    "location",
    "quote_type",
    "evidence",
    "adaptation",
)
SOURCE_FIT_ROW_KEYS = (
    "family_id",
    "expression",
    "identifier",
    "source_population",
    "source_speaker",
    "family_population",
    "fit",
    "note",
)
ALLOWED_SOURCE_SPEAKERS = {"patient", "carer", "clinician", "authors"}

FORBIDDEN_PROMPT_CHARS = set(",;-–—?!:()[]\"“”‘’/\\")
ASCII_WORD_RE = re.compile(r"^[A-Za-z0-9']+$")
TRIPLE_LETTER_RE = re.compile(r"([a-zA-Z])\1\1")

# Contraction patterns (SPEC.md section 4, "Contractions")
CONTRACTION_SUFFIX_RE = re.compile(r"(?:'m|'re|'ve|'ll|'d|n't)$", re.IGNORECASE)
EXPLICIT_APOSTROPHE_CONTRACTIONS = {
    "it's", "that's", "what's", "there's", "here's", "he's", "she's",
    "who's", "where's", "how's", "when's", "why's", "let's",
    "something's", "nothing's", "everything's", "this's", "which's",
    "y'all", "'cause", "'til", "'em", "ma'am", "o'clock", "ain't",
}
APOSTROPHE_LESS_CONTRACTIONS = {
    "dont", "cant", "wont", "didnt", "doesnt", "isnt", "arent",
    "wasnt", "werent", "hasnt", "havent", "hadnt", "couldnt",
    "wouldnt", "shouldnt", "mustnt", "mightnt", "neednt", "aint",
    "ive", "youre", "theyre", "youve", "weve", "theyve",
    "youd", "theyd", "youll", "theyll",
    "thats", "whats", "theres", "heres", "whos", "wheres", "hows", "whens", "whys",
}
SINGULAR_POSSESSIVE_RE = re.compile(r"^[A-Za-z]{2,}'s$")
PLURAL_POSSESSIVE_RE = re.compile(r"^[A-Za-z]{2,}s'$")
# Words immediately after "<noun>'s" that prove "'s" is a verb contraction ("is"/"has"), not a possessive
NON_POSSESSIVE_FOLLOWERS = {
    "a", "an", "the", "been", "got", "not", "never", "already",
}

CARDINAL_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
}

# Disease/diagnosis labels banned inside prompt texts (SPEC.md section 4:
# "The diagnosis is never named in a text. condition is a label for reviewers only").
DIAGNOSIS_BANNED_WORDS = {
    "abruption", "acne", "actinic", "addison", "adhd", "alopecia", "alzheimer", "anaphylaxis",
    "aneurysm", "angina", "appendicitis", "arthritis", "asthma", "bipolar",
    "blepharitis", "boerhaave", "borreliosis", "bppv", "bronchiectasis", "bronchiolitis",
    "bursitis", "cancer", "candidiasis", "carcinoma", "cataract", "cataracts",
    "cauda", "celiac", "cellulitis", "chalazion", "cheilitis", "chlamydia", "cholangitis",
    "cholecystitis", "cirrhosis", "clostridioides", "colitis", "concussion",
    "conjunctivitis", "costochondritis", "crohn", "croup", "cushing", "cystitis", "dementia",
    "dengue", "dermatitis", "diabetes", "diabetic", "difficile", "dissection",
    "diverticulitis", "dupuytren", "dvt", "eclampsia", "ectopic", "eczema",
    "embolism", "encephalitis", "encephalopathy", "endocarditis", "endometriosis", "epicondylitis",
    "epididymitis", "epiglottitis", "epilepsy", "equina", "erysipelas", "fasciitis",
    "fibroid", "fibroids", "fibromyalgia", "fluorosis", "ganglion", "gastritis", "giardia",
    "giardiasis", "gingivitis", "glaucoma", "gonorrhea", "gout", "gouty",
    "granuloma", "guillain", "hashimoto", "hayfever", "hemothorax", "hepatitis", "herpes",
    "hidradenitis", "hordeolum", "hyperthyroidism", "hypomania", "hypomanic", "hypothyroidism",
    "impetigo", "infarction", "intertrigo", "intussusception", "iritis",
    "keratitis", "keratosis", "ketoacidosis", "labyrinthitis", "leukemia",
    "leukoplakia", "lichen", "ludwig", "lupus", "lyme", "lymphoma", "malaria",
    "mastitis", "mastoiditis", "melanoma", "meniere", "meningitis", "migraine", "molluscum",
    "morton", "myasthenia", "myocarditis", "neuroma", "ocd", "onychomycosis",
    "osteoarthritis", "osteomyelitis", "otitis", "otosclerosis", "pancreatitis",
    "parkinson", "paronychia", "pemphigoid", "pemphigus", "pericarditis",
    "pericoronitis", "periodontitis", "pinkeye", "pneumonia", "pneumothorax",
    "podagra", "polyneuropathy", "polyposis", "preeclampsia", "priapism", "psoriasis", "ptsd",
    "pulpitis", "pyelonephritis", "quinsy", "rabies", "raynaud", "retinopathy", "rhabdomyolysis",
    "rheumatoid", "rhinitis", "rhinosinusitis", "ringworm", "rosacea", "scabies",
    "schizophrenia", "sciatica", "scleritis", "sclerosis", "sepsis", "shingles",
    "sialolithiasis", "sinusitis", "sjogren", "spondylitis", "stroke", "stye",
    "subarachnoid", "syphilis", "tendinitis", "tendinopathy", "tetanus", "thrombosis",
    "thrush", "thyroiditis", "thyrotoxic", "tinea", "tonsillitis", "torsion",
    "trichomoniasis", "trigeminal", "tuberculosis", "ulcer", "uveitis", "vitiligo",
    "volvulus", "xerosis", "zoster",
}

DIAGNOSIS_BANNED_PHRASES = (
    "heart attack",
    "retinal detachment",
    "central retinal artery occlusion",
    "carpal tunnel",
    "plantar fasciitis",
    "plantar warts",
    "plantar wart",
    "swimmers ear",
    "swimmer's ear",
    "yeast infection",
    "vestibular neuritis",
    "erythema nodosum",
    "erythema infectiosum",
    "restless legs syndrome",
    "restless leg syndrome",
    "sleep apnea",
    "scarlet fever",
    "tardive dyskinesia",
    "guillain barre",
    "myasthenia gravis",
    "basal cell",
    "graves disease",
    "bells palsy",
    "bell's palsy",
)

SELF_HARM_BANNED_WORDS = {
    "suicide", "suicidal", "selfharm", "overdose", "overdosed",
}
SELF_HARM_BANNED_PHRASES = (
    "self harm",
    "kill myself",
    "killing myself",
    "kill himself",
    "kill herself",
    "hurt myself",
    "hurting myself",
    "hurt himself",
    "hurt herself",
    "end my life",
    "want to die",
    "better off dead",
)

PASSIVE_CHART_PHRASES = (
    "was diagnosed",
    "were diagnosed",
    "been diagnosed",
    "was told",
    "been told",
    "presented with",
    "presents with",
    "complains of",
    "complaining of",
)

COURSE_EXPECTATION_PHRASES = (
    "will pass",
    "go away",
    "clear up",
    "get better",
    "wear off",
    "sleep it off",
    "settle down",
    "resolve on its own",
)

COMMON_MISSPELLINGS = {
    "achey", "alergy", "allergys", "breathlesness", "brething", "caugh", "chestt",
    "diarhea", "diarreah", "dizy", "docter", "feaver", "headach", "hemorhage",
    "hosptial", "itchyness", "medecine", "naucea", "phlem", "recieve", "seperate",
    "stomache", "swolen", "symtom", "symtoms", "temperture", "throbbingg",
    "vomitting", "whezing",
}

DB_ID_PATTERN = re.compile(
    r"\b(?:PMC\d+|PMCID|EuropePMC|MED\d+|NCT\d+|CRD\d+|C\d{7}|ORCID)\b",
    re.IGNORECASE,
)

LIT_PMID_DOI_RE = re.compile(
    r"^(?:PMID:\s*\d+(?:;\s*DOI:\s*10\.\S+)?|DOI:\s*10\.\S+)$"
)
LIT_URL_RE = re.compile(
    r"^(?:https://pubmed\.ncbi\.nlm\.nih\.gov/\d+/?|https://doi\.org/10\.\S+)$"
)
DICT_URL_RE = re.compile(
    r"^https://(?:"
    r"en\.wiktionary\.org/wiki/\S+|"
    r"www\.merriam-webster\.com/dictionary/\S+|"
    r"dictionary\.cambridge\.org/\S+|"
    r"(?:www\.)?daredictionary\.com/\S+|"
    r"dare\.wisc\.edu/\S+"
    r")$"
)

STATED_NEG_NOTE_RE = re.compile(r'"?stated_negative"?\s*:\s*true\b', re.IGNORECASE)

# Surface matchers for the 13 core expressions in lexicon/dialect_lexicon_20261109.json
CORE_LEXICON_PATTERNS: dict[str, re.Pattern[str]] = {
    "fell out / falling out": re.compile(r"\b(?:fell|fall|falls|falling)\s+out\b", re.IGNORECASE),
    "spell (a shaking spell, a fainting spell, a dizzy spell)": re.compile(r"\bspells?\b", re.IGNORECASE),
    "smothering / I'm smothering": re.compile(r"\bsmother(?:ing|ed|s)?\b", re.IGNORECASE),
    "short winded": re.compile(r"\bshort\s+winded\b", re.IGNORECASE),
    "a misery in my chest (or side, or back)": re.compile(r"\bmiser(?:y|ies)\b", re.IGNORECASE),
    "can't catch my breath": re.compile(
        r"\bcatch\s+(?:my|his|her|their|our)\s+breath\b", re.IGNORECASE
    ),
    "swimmy headed / my head feels swimmy": re.compile(r"\bswimmy\b", re.IGNORECASE),
    "a funny turn": re.compile(r"\bfunny\s+turns?\b", re.IGNORECASE),
    "giddiness / feeling giddy": re.compile(r"\bgidd(?:y|iness)\b", re.IGNORECASE),
    "fits / having fits": re.compile(r"\bfits?\b", re.IGNORECASE),
    "sinking heart / my heart is sinking": re.compile(
        r"\b(?:sinking\s+heart|heart\s+(?:is\s+|was\s+|keeps\s+)?sinking)\b", re.IGNORECASE
    ),
    "loose motions": re.compile(r"\bloose\s+motions?\b", re.IGNORECASE),
    "blackout / blacked out": re.compile(
        r"\b(?:blackouts?|black(?:ed|ing)?\s+out)\b", re.IGNORECASE
    ),
}

FOLK_LEXICON_PATTERNS: dict[str, re.Pattern[str]] = {
    "high blood": re.compile(r"\bhigh\s+blood\b(?!\s+(?:pressure|sugar))", re.IGNORECASE),
    "low blood": re.compile(r"\blow\s+blood\b(?!\s+(?:pressure|sugar))", re.IGNORECASE),
    "sugar / my sugar": re.compile(r"\b(?:my|his|her)\s+sugar\b(?!\s+level)", re.IGNORECASE),
    "bad blood": re.compile(r"\bbad\s+blood\b", re.IGNORECASE),
    "nervios / ataque de nervios": re.compile(r"\bnervios\b", re.IGNORECASE),
    "empacho": re.compile(r"\bempacho\b", re.IGNORECASE),
    "susto": re.compile(r"\bsusto\b", re.IGNORECASE),
    "it's just gastric": re.compile(r"\bjust\s+gastric\b", re.IGNORECASE),
}

SPEC_PRIOR_SHORT_CONDITIONS = {
    "cardiogenic syncope",
    "transient ischemic attack",
    "preeclampsia",
    "bronchiolitis",
    "asthma exacerbation",
    "tonic clonic seizure",
    "pediatric diabetic ketoacidosis",
    "food anaphylaxis",
    "pulpitis",
    "melanoma",
    "panic disorder",
    "early rheumatoid arthritis",
    "cystitis",
    "otitis media",
    "gastroenteritis",
    "reflux in pregnancy",
    "cauda equina",
    "pharyngitis with drooling",
    "skin infection with syncope",
    "pediatric lower respiratory infection with cyanosis",
    "upper gastrointestinal bleeding",
    "febrile respiratory illness in pregnancy",
    "fluid overload with orthopnea",
    "shingles with confusion",
    "gum disease with loose teeth",
    "plaque eruption",
    "persistent low mood",
    "post-collision trauma symptoms",
    "cataract",
    "heavy menstrual bleeding",
    "sinus infection",
    "hypothyroid-type fatigue",
    "pediatric purulent eye discharge",
    "oral thrush from an inhaler",
    "tick-bite rash",
    "anaemia-type breathlessness",
    "athlete's foot",
    "diaper rash",
    "winter dry skin",
    "hay fever",
}

_CF_LEADING_FILLER_RE = re.compile(
    r"^(?:(?:and|with|now|just|only|still|got|have|had|has|get|gets|started|saw|noticed|feel|feels|is|are|a|an|the|my|his|her|that|those)\s+)+",
    re.IGNORECASE,
)

# Stock control phrases already overused in Round 11 (Rule D, SPEC.md section 4)
RULE_D_BANNED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("40 C fever (Round 11 r11-014, r11-015, r11-039)", re.compile(r"\b40(?:\.0)?\s*c\b", re.IGNORECASE)),
    ("swelling behind ... ear (Round 11 r11-012, r11-040)", re.compile(r"\bswelling\s+behind\b.*\bear\b", re.IGNORECASE)),
    ("turning blue (Round 11 r11-017, r11-041)", re.compile(r"\bturning\s+blue\b", re.IGNORECASE)),
    ("yellow pus (Round 11 r11-023, r11-047, r11-048)", re.compile(r"\byellow\s+pus\b", re.IGNORECASE)),
    ("pus on ... tonsils (Round 11 r11-026)", re.compile(r"\bpus\s+on\b.*\btonsils?\b", re.IGNORECASE)),
    ("yellow phlegm (Round 11 r11-006)", re.compile(r"\byellow\s+phlegm\b", re.IGNORECASE)),
    ("double vision / seeing double (Round 11 r11-018, r11-022)", re.compile(r"\b(?:double\s+vision|seeing\s+double)\b", re.IGNORECASE)),
    ("gasping for breath/air (Round 11 r11-037)", re.compile(r"\bgasping\s+for\s+(?:breath|air)\b", re.IGNORECASE)),
    ("throw up repeatedly (Round 11 r11-024)", re.compile(r"\bthrow(?:ing)?\s+up\s+repeatedly\b", re.IGNORECASE)),
    ("falling to the floor (Round 11 r11-044)", re.compile(r"\bfalling\s+to\s+the\s+floor\b", re.IGNORECASE)),
)

# Bleeding emergency escalation detector (SPEC.md section 4 Rule D:
# "At most 1 emergency control per batch may move to level 4 through bleeding.")
BLEEDING_CONTROL_RE = re.compile(
    r"\b(?:bleed(?:ing|s)?|bled|hemorrhag\w*|blood(?!\s+(?:pressure|sugar|test|tests|draw|work|vessel|vessels))|bloody)\b",
    re.IGNORECASE,
)

ALLOWED_CONCERN_KINDS = {
    "control_adds_fact",
    "control_level_disputed",
    "level_disputed",
    "fact_parity",
    "stated_negative",
    "wording",
    "label",
    "source_fit",
    "other",
}
ALLOWED_CONCERN_APPLIES_TO = {
    "reg", "mpar", "epar", "chg", "attr", "qb", "qc", "family", "label",
}
ALLOWED_MODEL_OPEN_DISPOSITIONS = {
    "pending_clinical_review",
    "pending_patient_language_review",
    "open",
    "revised_pending_reread",
}


def normalize_space(text: str) -> str:
    return " ".join(text.strip().lower().split())


def normalize_cf_to_core(text: str) -> str:
    norm = normalize_space(text)
    stripped = _CF_LEADING_FILLER_RE.sub("", norm).strip()
    return stripped or norm


def extract_numbers(text: str) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def load_dropped_ids(ledger_path: Path = DEFAULT_LEDGER_PATH) -> set[str]:
    """Return family_ids marked state=='dropped' in Round 12 ledger.json."""
    if not ledger_path.exists():
        return set()
    try:
        doc = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {
        str(row["family_id"])
        for row in doc.get("families", [])
        if isinstance(row, dict) and row.get("state") == "dropped" and "family_id" in row
    }


def _ingest_prior_family(
    fam: dict[str, Any],
    label: str,
    *,
    prior_conditions: dict[str, str],
    prior_texts: dict[str, str],
    prior_cf_to: dict[str, str],
    include_cf_to: bool,
) -> None:
    fid = fam.get("family_id", label)
    cond = fam.get("condition")
    if isinstance(cond, str) and cond.strip():
        prior_conditions[normalize_space(cond)] = f"{label}:{fid}"
    texts = fam.get("texts", {})
    if isinstance(texts, dict):
        for tname, tval in texts.items():
            if isinstance(tval, str) and tval.strip():
                prior_texts[normalize_space(tval)] = f"{label}:{fid}.{tname}"
    if include_cf_to:
        cf_obj = fam.get("changed_fact")
        if isinstance(cf_obj, dict) and isinstance(cf_obj.get("to"), str) and cf_obj["to"].strip():
            cf_to_str = cf_obj["to"]
            prior_cf_to[normalize_space(cf_to_str)] = f"{label}:{fid} ({cf_to_str!r})"
            prior_cf_to[normalize_cf_to_core(cf_to_str)] = f"{label}:{fid} ({cf_to_str!r})"


def load_reference_data(
    *,
    lexicon_path: Path = DEFAULT_LEXICON_PATH,
    urgency_tiers_path: Path = DEFAULT_URGENCY_TIERS_PATH,
    plan_path: Path = DEFAULT_PLAN_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    r9_path: Path = DEFAULT_R9_PATH,
    r10_path: Path = DEFAULT_R10_PATH,
    r11_dir: Path = ROUND11_DIR,
    current_batch_name: str | None = None,
    current_batch_dir: Path | None = None,
    exclude_current_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Load lexicon, target token tiers (tier field only), plan slots, and all prior batches."""
    lex_doc = json.loads(lexicon_path.read_text(encoding="utf-8"))
    core_entries = {row["expression"] for row in lex_doc.get("core", [])}
    folk_entries = {row["expression"] for row in lex_doc.get("folk_meaning", [])}

    # SPEC.md section 3: "Read only the tier values in that file."
    tiers_raw = json.loads(urgency_tiers_path.read_text(encoding="utf-8"))
    token_tiers: dict[str, int | None] = {
        tok: meta.get("tier")
        for tok, meta in tiers_raw.get("tokens", {}).items()
        if isinstance(meta, dict)
    }

    plan_by_id: dict[str, dict[str, Any]] = {}
    if plan_path.exists():
        plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
        for slot in plan_doc.get("slots", []):
            plan_by_id[slot["family_id"]] = slot
        for res in plan_doc.get("reserves", []):
            plan_by_id[res["reserve_id"]] = res

    prior_conditions: dict[str, str] = {
        normalize_space(c): "SPEC.md_prior_list" for c in SPEC_PRIOR_SHORT_CONDITIONS
    }
    prior_texts: dict[str, str] = {}
    prior_cf_to: dict[str, str] = {}

    prior_files: list[tuple[str, Path, bool]] = [
        ("r9", r9_path, False),
        ("r10", r10_path, False),
    ]
    for k in range(1, 7):
        prior_files.append((f"r11_b{k:02d}", r11_dir / f"batch_{k:02d}" / "families.json", True))

    if current_batch_name and BATCH_NAME_RE.match(current_batch_name):
        bnum = int(current_batch_name.split("_")[1])
        for k in range(1, bnum):
            prev_r12_fam = ROUND12_DIR / f"batch_{k:02d}" / "families.json"
            if prev_r12_fam.exists():
                prior_files.append((f"r12_b{k:02d}", prev_r12_fam, True))

    for label, fpath, inc_cf in prior_files:
        if not fpath.exists():
            continue
        fams = json.loads(fpath.read_text(encoding="utf-8"))
        for fam in fams:
            if isinstance(fam, dict):
                _ingest_prior_family(
                    fam,
                    label,
                    prior_conditions=prior_conditions,
                    prior_texts=prior_texts,
                    prior_cf_to=prior_cf_to,
                    include_cf_to=inc_cf,
                )

    # Also cross-check non-dropped sibling drafts already present in current_batch_dir/drafts
    # when validating a subset of drafts in a batch.
    dropped_ids = load_dropped_ids(ledger_path)
    excl = exclude_current_ids or set()
    if current_batch_dir is not None:
        sibling_drafts_dir = current_batch_dir / "drafts"
        if sibling_drafts_dir.exists():
            for spath in sorted(sibling_drafts_dir.glob("*.json")):
                sfid = spath.stem
                if sfid in excl or sfid in dropped_ids:
                    continue
                try:
                    sdoc = json.loads(spath.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(sdoc, dict):
                    real_fid = str(sdoc.get("family_id", sfid))
                    if real_fid in excl or real_fid in dropped_ids:
                        continue
                    _ingest_prior_family(
                        sdoc,
                        f"{current_batch_dir.name}_draft",
                        prior_conditions=prior_conditions,
                        prior_texts=prior_texts,
                        prior_cf_to=prior_cf_to,
                        include_cf_to=True,
                    )

    return {
        "core_lexicon": core_entries,
        "folk_lexicon": folk_entries,
        "all_lexicon": core_entries | folk_entries,
        "token_tiers": token_tiers,
        "plan_by_id": plan_by_id,
        "dropped_ids": dropped_ids,
        "prior_conditions": prior_conditions,
        "prior_texts": prior_texts,
        "prior_cf_to": prior_cf_to,
    }


def _check_word_boundary_occurrence(haystack: str, needle: str) -> tuple[bool, str]:
    """Verify needle occurs exactly once in haystack and aligns on whole words."""
    count = haystack.count(needle)
    if count != 1:
        return False, f"occurs {count} times (must occur exactly once)"
    idx = haystack.index(needle)
    end = idx + len(needle)
    if idx > 0 and haystack[idx - 1] != " ":
        return False, "does not start on a space-delimited word boundary"
    if end < len(haystack) and haystack[end] != " ":
        return False, "does not end on a space-delimited word boundary"
    return True, ""


def _check_no_forbidden_db_ids(value: str, context: str, errors: list[str]) -> None:
    m = DB_ID_PATTERN.search(value)
    if m:
        errors.append(f"{context}: forbidden database identifier {m.group(0)!r} (only PMID and DOI allowed)")


def _check_word_contraction(
    word: str,
    next_word: str | None,
    context: str,
    errors: list[str],
) -> None:
    """Enforce Round 12 SPEC.md section 4 Contractions rule on a single token."""
    wl = word.lower()
    if word == "im":
        errors.append(f"{context}: lowercase 'im' must be capitalized 'Im' or written 'I am' (SPEC.md section 4)")
        return
    if wl in APOSTROPHE_LESS_CONTRACTIONS:
        errors.append(
            f"{context}: unexpanded contraction {word!r} is forbidden "
            "(SPEC.md section 4: only 'Im' is allowed; write other contractions in full)"
        )
        return
    if "'" not in word:
        return

    if CONTRACTION_SUFFIX_RE.search(wl) or wl in EXPLICIT_APOSTROPHE_CONTRACTIONS:
        errors.append(
            f"{context}: apostrophe contraction {word!r} is forbidden in Round 12 "
            "(SPEC.md section 4: write 'Im' for \"I'm\" and write all other contractions in full)"
        )
        return

    if SINGULAR_POSSESSIVE_RE.match(word):
        nw = (next_word or "").lower()
        if nw in NON_POSSESSIVE_FOLLOWERS:
            errors.append(
                f"{context}: {word!r} before {next_word!r} reads as an 'is'/'has' contraction, "
                "not a noun possessive (SPEC.md section 4)"
            )
        return

    if PLURAL_POSSESSIVE_RE.match(word):
        return

    errors.append(
        f"{context}: invalid apostrophe token {word!r} "
        "(SPEC.md section 4: no apostrophe contractions; only noun possessives like \"doctor's\" keep an apostrophe)"
    )


def _validate_source_item(
    rec: Any,
    *,
    is_attribution: bool,
    fid: str,
    everyday_texts_joined: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    expected_keys = ATTRIBUTION_KEYS if is_attribution else EVERYDAY_SOURCE_KEYS
    label = "attribution" if is_attribution else "everyday_sources item"
    if not isinstance(rec, dict):
        errors.append(f"{fid}: {label} must be a JSON object")
        return

    missing = [k for k in expected_keys if k not in rec]
    extra = [k for k in rec if k not in expected_keys]
    if missing or extra:
        errors.append(f"{fid}: {label} key mismatch; missing={missing}, extra={extra}")
        return

    phrase_key = "clause" if is_attribution else "expression"
    phrase = rec[phrase_key]
    if not isinstance(phrase, str) or not phrase.strip() or phrase != phrase.strip():
        errors.append(f"{fid}: {label}.{phrase_key} must be a non-empty trimmed string")
        return

    if is_attribution:
        explains = rec["explains"]
        if not isinstance(explains, str) or not explains.strip():
            errors.append(f"{fid}: attribution.explains must be a non-empty string")
        else:
            _check_no_forbidden_db_ids(explains, f"{fid}:attribution.explains", errors)

    if phrase not in everyday_texts_joined:
        errors.append(
            f"{fid}: {label}.{phrase_key} {phrase!r} does not appear verbatim in any everyday variant text"
        )

    qt = rec["quote_type"]
    if qt not in {"direct patient quote", "authors' summary", "dictionary definition", "none"}:
        errors.append(f"{fid}: invalid quote_type {qt!r} on {phrase!r}")
        return

    src = rec["source"]
    if not isinstance(src, str) or not src.strip():
        errors.append(f"{fid}: {label}.source must be a non-empty string on {phrase!r}")
        return

    if src == "none":
        if qt != "none":
            errors.append(f"{fid}: source='none' requires quote_type='none' on {phrase!r}")
        for k in ("title", "pmid_or_doi", "inspected_url", "access", "location", "evidence", "adaptation"):
            if rec[k] is not None:
                errors.append(f"{fid}: source='none' requires {k}=null on {phrase!r}")
        return

    if qt == "none":
        errors.append(f"{fid}: cited source cannot have quote_type='none' on {phrase!r}")

    for k in ("source", "title", "pmid_or_doi", "inspected_url", "access", "location", "evidence"):
        val = rec[k]
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{fid}: cited source missing non-empty {k} on {phrase!r}")
        else:
            _check_no_forbidden_db_ids(val, f"{fid}:{phrase}:{k}", errors)

    access = rec.get("access")
    if access == "title only":
        errors.append(
            f"{fid}: access='title only' is forbidden on {phrase!r} (SPEC.md section 7: mark unsourced as 'none')"
        )
    elif access not in {"full text", "abstract only"}:
        errors.append(f"{fid}: access must be 'full text' or 'abstract only' on {phrase!r}, got {access!r}")

    adaptation = rec.get("adaptation")
    if adaptation is not None:
        if not isinstance(adaptation, str) or not adaptation.strip():
            errors.append(f"{fid}: adaptation must be null or a non-empty string on {phrase!r}")
        else:
            _check_no_forbidden_db_ids(adaptation, f"{fid}:{phrase}:adaptation", errors)

    url = rec.get("inspected_url")
    pmid_or_doi = rec.get("pmid_or_doi")
    if isinstance(url, str) and isinstance(pmid_or_doi, str):
        if qt == "dictionary definition":
            if not DICT_URL_RE.match(url):
                errors.append(
                    f"{fid}: dictionary definition URL {url!r} on {phrase!r} must be Merriam-Webster, "
                    "Cambridge, DARE, or Wiktionary (SPEC.md section 7)"
                )
            if not DICT_URL_RE.match(pmid_or_doi):
                errors.append(
                    f"{fid}: dictionary definition pmid_or_doi {pmid_or_doi!r} on {phrase!r} "
                    "must hold the allowed dictionary entry URL"
                )
        else:
            if not LIT_PMID_DOI_RE.match(pmid_or_doi):
                errors.append(
                    f"{fid}: literature pmid_or_doi {pmid_or_doi!r} on {phrase!r} must match "
                    "'PMID: <digits>[; DOI: 10.<...>]' or 'DOI: 10.<...>'"
                )
            if not LIT_URL_RE.match(url):
                errors.append(
                    f"{fid}: literature inspected_url {url!r} on {phrase!r} must be "
                    "https://pubmed.ncbi.nlm.nih.gov/<PMID>/ or https://doi.org/10.<DOI>"
                )

    evidence = rec.get("evidence")
    if isinstance(evidence, str) and evidence.strip():
        if " / " in evidence:
            errors.append(
                f"{fid}: evidence on {phrase!r} contains ' / ' joining multiple quotes "
                "(SPEC.md section 5.10: copy each sentence separately)"
            )
        if qt != "dictionary definition" and adaptation is None and phrase not in evidence:
            errors.append(
                f"{fid}: {phrase!r} has adaptation=null but is not an exact case-sensitive substring of evidence"
            )


def is_draft_stated_negative(fam: dict[str, Any]) -> bool:
    design_note = fam.get("design_note")
    if isinstance(design_note, str) and STATED_NEG_NOTE_RE.search(design_note):
        return True
    if isinstance(design_note, dict) and design_note.get("stated_negative") is True:
        return True
    return False


def is_bleeding_l4_control(fam: dict[str, Any]) -> bool:
    cf = fam.get("changed_fact")
    if not isinstance(cf, dict):
        return False
    if cf.get("right_care_after") != 4:
        return False
    cf_to = cf.get("to")
    return isinstance(cf_to, str) and bool(BLEEDING_CONTROL_RE.search(cf_to))


def validate_family_dict(
    fam: Any,
    ref: dict[str, Any],
    *,
    expected_family_id: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validate a single family dictionary against Round 12 SPEC.md sections 3, 4, 5, and 7."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(fam, dict):
        return ["Draft root must be a JSON object"], warnings

    fid = fam.get("family_id")
    if not isinstance(fid, str) or not FAMILY_ID_RE.match(fid):
        errors.append(f"Invalid family_id {fid!r} (expected r12-001..r12-048 or r12-b01/02-rep1..6)")
        fid_str = str(fid or "<unknown>")
    else:
        fid_str = fid
        if expected_family_id and fid != expected_family_id:
            errors.append(f"{fid_str}: filename stem {expected_family_id!r} != family_id {fid!r}")

    missing_keys = [k for k in REQUIRED_FAMILY_KEYS if k not in fam]
    extra_keys = [k for k in fam if k not in REQUIRED_FAMILY_KEYS and k not in OPTIONAL_FAMILY_KEYS]
    if missing_keys:
        errors.append(f"{fid_str}: missing required top-level keys: {missing_keys}")
    if extra_keys:
        errors.append(f"{fid_str}: unexpected top-level keys: {extra_keys}")
    if missing_keys:
        return errors, warnings

    # Condition check (no repeats across Rounds 9, 10, 11, and Round 12)
    cond = fam["condition"]
    if not isinstance(cond, str) or not cond.strip():
        errors.append(f"{fid_str}: condition must be a non-empty string")
    else:
        norm_cond = normalize_space(cond)
        if norm_cond in ref["prior_conditions"]:
            errors.append(
                f"{fid_str}: condition {cond!r} repeats prior condition ({ref['prior_conditions'][norm_cond]})"
            )
        _check_no_forbidden_db_ids(cond, f"{fid_str}:condition", errors)

    # Right care, carrier_frame, target_token, and urgency_tiers.draft.json tier check
    rc = fam["right_care"]
    carrier = fam["carrier_frame"]
    target = fam["target_token"]
    if type(rc) is not int or rc not in {2, 3, 4}:
        errors.append(
            f"{fid_str}: right_care must be int in {{2, 3, 4}} in Round 12 (no self-care L1 families), got {rc!r}"
        )
    else:
        if not isinstance(carrier, str) or not isinstance(target, str):
            errors.append(f"{fid_str}: carrier_frame and target_token must be strings")
        else:
            if (carrier, target) not in ALLOWED_CARE_SPECS[rc]:
                errors.append(
                    f"{fid_str}: (carrier_frame, target_token)=({carrier!r}, {target!r}) "
                    f"is not allowed for right_care={rc}"
                )
            if not target.startswith(" ") or len(target.strip()) == 0:
                errors.append(f"{fid_str}: target_token {target!r} must have a single leading space")
            else:
                tok_key = target.lstrip(" ").lower()
                draft_tier = ref["token_tiers"].get(tok_key, "<missing>")
                if draft_tier != rc:
                    errors.append(
                        f"{fid_str}: target_token {target!r} (key {tok_key!r}) has tier={draft_tier!r} "
                        f"in data/urgency_tiers.draft.json, expected right_care={rc}"
                    )

    # String metadata checks
    for str_key in ("level_rationale", "swap_note", "equity_dimension"):
        val = fam[str_key]
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{fid_str}: {str_key} must be a non-empty string")
        else:
            _check_no_forbidden_db_ids(val, f"{fid_str}:{str_key}", errors)

    design_note = fam["design_note"]
    if not isinstance(design_note, str) or not design_note.strip():
        errors.append(
            f"{fid_str}: design_note must be a non-empty string (Round 11 schema; if marking a stated "
            "negative, include '\"stated_negative\": true' and the reason inside design_note)"
        )
    else:
        _check_no_forbidden_db_ids(design_note, f"{fid_str}:design_note", errors)
        if STATED_NEG_NOTE_RE.search(design_note) and len(design_note.strip()) < 35:
            errors.append(f"{fid_str}: design_note marks stated_negative=true without explaining the reason")

    # Reference facts (3 to 5 checkable statements)
    ref_facts = fam["reference_facts"]
    ref_fact_ids: list[str] = []
    if not isinstance(ref_facts, list) or not (3 <= len(ref_facts) <= 5):
        errors.append(
            f"{fid_str}: reference_facts must be a list of 3 to 5 facts, got "
            f"{len(ref_facts) if isinstance(ref_facts, list) else type(ref_facts).__name__}"
        )
    else:
        for idx, rf in enumerate(ref_facts, start=1):
            expected_fid = f"f{idx}"
            if not isinstance(rf, dict) or set(rf.keys()) != {"fact_id", "text"}:
                errors.append(f"{fid_str}: reference_facts[{idx - 1}] must have exact keys {{'fact_id', 'text'}}")
                continue
            if rf["fact_id"] != expected_fid:
                errors.append(
                    f"{fid_str}: reference_facts[{idx - 1}].fact_id must be {expected_fid!r}, got {rf['fact_id']!r}"
                )
            if not isinstance(rf["text"], str) or not rf["text"].strip():
                errors.append(f"{fid_str}: reference_facts[{idx - 1}].text must be a non-empty string")
            else:
                _check_no_forbidden_db_ids(rf["text"], f"{fid_str}:reference_facts.{expected_fid}", errors)
            ref_fact_ids.append(rf["fact_id"])

    # Texts & variant presence
    texts = fam["texts"]
    if not isinstance(texts, dict):
        errors.append(f"{fid_str}: texts must be a JSON object")
        return errors, warnings

    missing_tkeys = [k for k in REQUIRED_TEXT_KEYS if k not in texts]
    extra_tkeys = [k for k in texts if k not in ALL_TEXT_KEYS_ORDERED]
    if missing_tkeys:
        errors.append(f"{fid_str}: texts missing required keys: {missing_tkeys}")
    if extra_tkeys:
        errors.append(f"{fid_str}: texts has unknown keys: {extra_tkeys}")
    if missing_tkeys:
        return errors, warnings

    has_quad = ("quad_b" in texts) or ("quad_c" in texts)
    if has_quad and not ("quad_b" in texts and "quad_c" in texts):
        errors.append(f"{fid_str}: quad_b and quad_c must both be present or both be absent")

    has_att_text = "everyday_attribution" in texts
    has_att_obj = "attribution" in fam and fam["attribution"] is not None
    if "attribution" in fam and fam["attribution"] is None:
        errors.append(f"{fid_str}: omit 'attribution' key completely when family has no everyday_attribution")
    if has_att_text != has_att_obj:
        errors.append(
            f"{fid_str}: texts.everyday_attribution ({has_att_text}) and attribution object ({has_att_obj}) must co-occur"
        )

    # SPEC.md section 3: L4 and L3 families all have everyday_attribution; L2 families do not.
    if rc in {3, 4} and not has_att_text:
        errors.append(
            f"{fid_str}: right_care={rc} family must include texts.everyday_attribution and attribution (SPEC.md section 3)"
        )
    elif rc == 2 and has_att_text:
        errors.append(f"{fid_str}: right_care=2 family must not include everyday_attribution (SPEC.md section 3)")

    # Plain-register lexicon_entries & protocol_flags (SPEC.md sections 3 & 4)
    lex_entries = fam["lexicon_entries"]
    if not isinstance(lex_entries, list) or len(lex_entries) != 0:
        errors.append(
            f"{fid_str}: lexicon_entries must be [] (empty list) in Round 12 (all families are plain register)"
        )

    pflags = fam["protocol_flags"]
    expected_pflag_keys = {
        "has_dialect_lexicon",
        "has_quad_2x2_syntax",
        "has_patient_attribution",
        "intervention_notes",
    }
    if not isinstance(pflags, dict) or set(pflags.keys()) != expected_pflag_keys:
        errors.append(f"{fid_str}: protocol_flags must have exact keys {sorted(expected_pflag_keys)}")
    else:
        if pflags["has_dialect_lexicon"] is not False:
            errors.append(f"{fid_str}: protocol_flags.has_dialect_lexicon must be false in Round 12")
        if pflags["has_quad_2x2_syntax"] is not has_quad:
            errors.append(f"{fid_str}: protocol_flags.has_quad_2x2_syntax must equal {has_quad}")
        if pflags["has_patient_attribution"] is not has_att_text:
            errors.append(f"{fid_str}: protocol_flags.has_patient_attribution must equal {has_att_text}")
        inotes = pflags["intervention_notes"]
        if not isinstance(inotes, str) or not inotes.strip():
            errors.append(f"{fid_str}: protocol_flags.intervention_notes must be a non-empty string")
        else:
            _check_no_forbidden_db_ids(inotes, f"{fid_str}:protocol_flags.intervention_notes", errors)

    # Check alignment with plan.json slot/reserve if registered
    plan_slot = ref["plan_by_id"].get(fid_str)
    if plan_slot:
        if plan_slot.get("group") != "plain_register":
            errors.append(f"{fid_str}: plan.json group={plan_slot.get('group')!r} != 'plain_register'")
        if rc != plan_slot["right_care"]:
            errors.append(f"{fid_str}: right_care={rc} != plan.json right_care={plan_slot['right_care']}")
        if carrier != plan_slot["carrier_frame"]:
            errors.append(
                f"{fid_str}: carrier_frame={carrier!r} != plan.json carrier_frame={plan_slot['carrier_frame']!r}"
            )
        if target != plan_slot["target_token"]:
            errors.append(
                f"{fid_str}: target_token={target!r} != plan.json target_token={plan_slot['target_token']!r}"
            )
        if has_att_text != bool(plan_slot["has_attribution"]):
            errors.append(
                f"{fid_str}: has_attribution={has_att_text} != plan.json has_attribution={plan_slot['has_attribution']}"
            )
        if has_quad != bool(plan_slot["has_quad"]):
            errors.append(f"{fid_str}: has_quad={has_quad} != plan.json has_quad={plan_slot['has_quad']}")

    # Validate each text variant
    med_numbers = Counter(extract_numbers(texts["medical"])) if isinstance(texts.get("medical"), str) else Counter()
    seen_variant_texts: dict[str, str] = {}

    for tname in ALL_TEXT_KEYS_ORDERED:
        if tname not in texts:
            continue
        tval = texts[tname]
        if not isinstance(tval, str) or not tval.strip():
            errors.append(f"{fid_str}.{tname}: must be a non-empty string")
            continue
        if tval != tval.strip() or "  " in tval or "\n" in tval or "\r" in tval or "\t" in tval:
            errors.append(f"{fid_str}.{tname}: must be single-spaced with no leading/trailing whitespace or newlines")

        # Active first-person opening without "I'm " (SPEC.md section 4 Contractions)
        if tval.startswith("I'm "):
            errors.append(
                f"{fid_str}.{tname}: starts with \"I'm \" — Round 12 forbids apostrophe contractions; write 'Im ' or 'I am '"
            )
        elif not (tval.startswith("I ") or tval.startswith("Im ") or tval.startswith("My ")):
            errors.append(f"{fid_str}.{tname}: must start in active first person ('I ', 'Im ', or 'My ')")

        tlow = tval.lower()
        for pphrase in PASSIVE_CHART_PHRASES:
            if pphrase in tlow:
                errors.append(f"{fid_str}.{tname}: contains passive/chart phrase {pphrase!r}")

        # Carrier ending
        if isinstance(carrier, str) and not tval.endswith(" " + carrier):
            errors.append(f"{fid_str}.{tname}: must end with ' ' + carrier_frame ({carrier!r})")

        # Forbidden punctuation & single-sentence check
        bad_chars = sorted({ch for ch in tval if ch in FORBIDDEN_PROMPT_CHARS})
        if bad_chars:
            errors.append(f"{fid_str}.{tname}: contains forbidden punctuation/characters {bad_chars}")
        if re.search(r"(?<!\d)\.|\.(?!\d)", tval):
            errors.append(f"{fid_str}.{tname}: contains sentence period '.' (must be a single unpunctuated sentence)")

        words = tval.split()
        if len(words) > 40:
            errors.append(f"{fid_str}.{tname}: {len(words)} words exceeds 40-word maximum")

        for w_idx, w in enumerate(words):
            if not ASCII_WORD_RE.match(w):
                errors.append(f"{fid_str}.{tname}: non-ASCII or punctuated word token {w!r}")
                continue
            next_w = words[w_idx + 1] if w_idx + 1 < len(words) else None
            _check_word_contraction(w, next_w, f"{fid_str}.{tname}", errors)

            wl = w.lower()
            wl_bare = wl.strip("'")
            wl_stem = re.sub(r"'s$", "", wl_bare)
            if wl_bare in CARDINAL_NUMBER_WORDS:
                errors.append(f"{fid_str}.{tname}: spelled-out number word {w!r} (write numbers as digits)")
            if wl_bare in DIAGNOSIS_BANNED_WORDS or wl_stem in DIAGNOSIS_BANNED_WORDS:
                errors.append(f"{fid_str}.{tname}: names banned diagnosis term {w!r}")
            if wl_bare in SELF_HARM_BANNED_WORDS or wl_stem in SELF_HARM_BANNED_WORDS:
                errors.append(f"{fid_str}.{tname}: contains banned self-harm word {w!r}")
            if wl_bare in COMMON_MISSPELLINGS or TRIPLE_LETTER_RE.search(wl_bare):
                errors.append(f"{fid_str}.{tname}: suspected misspelling {w!r}")

        for dphrase in DIAGNOSIS_BANNED_PHRASES:
            if re.search(r"\b" + re.escape(dphrase) + r"\b", tlow):
                errors.append(f"{fid_str}.{tname}: names banned diagnosis phrase {dphrase!r}")
        for shphrase in SELF_HARM_BANNED_PHRASES:
            if re.search(r"\b" + re.escape(shphrase) + r"\b", tlow):
                errors.append(f"{fid_str}.{tname}: contains banned self-harm phrase {shphrase!r}")

        # No dialect or folk lexicon form in any text (SPEC.md sections 3 & 8 G1)
        for lex, pat in CORE_LEXICON_PATTERNS.items():
            if pat.search(tval):
                errors.append(
                    f"{fid_str}.{tname}: plain-register family uses dialect lexicon form {lex!r}"
                )
        for lex, pat in FOLK_LEXICON_PATTERNS.items():
            if pat.search(tval):
                errors.append(
                    f"{fid_str}.{tname}: plain-register family uses folk lexicon form {lex!r}"
                )

        if tname != "changed_fact":
            cur_nums = Counter(extract_numbers(tval))
            if cur_nums != med_numbers:
                warnings.append(
                    f"{fid_str}.{tname}: digit tokens {dict(cur_nums)} differ from medical {dict(med_numbers)}"
                )

        norm_t = normalize_space(tval)
        if norm_t in seen_variant_texts:
            errors.append(
                f"{fid_str}.{tname}: identical text to {fid_str}.{seen_variant_texts[norm_t]}"
            )
        else:
            seen_variant_texts[norm_t] = tname

        if norm_t in ref["prior_texts"]:
            errors.append(
                f"{fid_str}.{tname}: text duplicates prior/sibling prompt ({ref['prior_texts'][norm_t]})"
            )

    # Swap spans (SPEC.md section 4: single continuous stretch, <= 2 words length diff)
    swap_spans = fam["swap_spans"]
    if not isinstance(swap_spans, dict) or set(swap_spans.keys()) != {"medical_span", "everyday_span"}:
        errors.append(f"{fid_str}: swap_spans must have exact keys {{'medical_span', 'everyday_span'}}")
    else:
        mspan = swap_spans["medical_span"]
        espan = swap_spans["everyday_span"]
        if not isinstance(mspan, str) or not mspan.strip() or mspan != mspan.strip():
            errors.append(f"{fid_str}: swap_spans.medical_span must be a non-empty trimmed string")
        elif not isinstance(espan, str) or not espan.strip() or espan != espan.strip():
            errors.append(f"{fid_str}: swap_spans.everyday_span must be a non-empty trimmed string")
        else:
            if mspan == espan:
                errors.append(f"{fid_str}: medical_span and everyday_span cannot be identical")
            ok_occ, reason = _check_word_boundary_occurrence(texts["medical"], mspan)
            if not ok_occ:
                errors.append(f"{fid_str}: swap_spans.medical_span {reason} in texts.medical")
            elif texts["medical"].replace(mspan, espan, 1) != texts["everyday"]:
                errors.append(
                    f"{fid_str}: texts.medical.replace(medical_span, everyday_span, 1) != texts.everyday"
                )
            else:
                prefix_end_suffix = texts["medical"].split(mspan, 1)[1]
                if isinstance(carrier, str) and not (
                    prefix_end_suffix == " " + carrier or prefix_end_suffix.endswith(" " + carrier)
                ):
                    errors.append(f"{fid_str}: swap_spans.medical_span overlaps carrier_frame")
            wdiff = abs(len(mspan.split()) - len(espan.split()))
            if wdiff > 2:
                errors.append(
                    f"{fid_str}: |words(medical_span) - words(everyday_span)| = {wdiff} > 2 "
                    f"({len(mspan.split())} vs {len(espan.split())} words)"
                )

    # Changed-fact control (SPEC.md sections 2, 4 Rules A & D)
    cf = fam["changed_fact"]
    if not isinstance(cf, dict) or set(cf.keys()) != {"fact_id", "from", "to", "right_care_after"}:
        errors.append(f"{fid_str}: changed_fact must have exact keys {{'fact_id', 'from', 'to', 'right_care_after'}}")
    else:
        if cf["fact_id"] not in ref_fact_ids:
            errors.append(f"{fid_str}: changed_fact.fact_id {cf['fact_id']!r} not in reference_facts {ref_fact_ids}")
        cf_from = cf["from"]
        cf_to = cf["to"]
        rc_after = cf["right_care_after"]
        if not isinstance(cf_from, str) or not cf_from.strip() or cf_from != cf_from.strip():
            errors.append(f"{fid_str}: changed_fact.from must be a non-empty trimmed string")
        elif not isinstance(cf_to, str) or not cf_to.strip() or cf_to != cf_to.strip():
            errors.append(f"{fid_str}: changed_fact.to must be a non-empty trimmed string")
        else:
            if cf_from == cf_to:
                errors.append(f"{fid_str}: changed_fact.from and changed_fact.to cannot be identical")
            ok_cf, reason_cf = _check_word_boundary_occurrence(texts["everyday"], cf_from)
            if not ok_cf:
                errors.append(f"{fid_str}: changed_fact.from {reason_cf} in texts.everyday")
            elif texts["everyday"].replace(cf_from, cf_to, 1) != texts["changed_fact"]:
                errors.append(f"{fid_str}: texts.everyday.replace(from, to, 1) != texts.changed_fact")
            else:
                cf_suffix = texts["everyday"].split(cf_from, 1)[1]
                if isinstance(carrier, str) and not (
                    cf_suffix == " " + carrier or cf_suffix.endswith(" " + carrier)
                ):
                    errors.append(f"{fid_str}: changed_fact.from overlaps carrier_frame")

            # Rule D applies to every family in Round 12 against Round 11 + earlier/sibling Round 12
            prior_cf_map = ref.get("prior_cf_to", {})
            norm_cf = normalize_space(cf_to)
            core_cf = normalize_cf_to_core(cf_to)
            hit_prior = prior_cf_map.get(norm_cf) or prior_cf_map.get(core_cf)
            if hit_prior:
                errors.append(
                    f"{fid_str}: Rule D violation — changed_fact.to {cf_to!r} repeats wording already used in "
                    f"Round 11/12 ({hit_prior})"
                )
            for pat_label, pat_re in RULE_D_BANNED_PATTERNS:
                if pat_re.search(cf_to):
                    errors.append(
                        f"{fid_str}: Rule D violation — changed_fact.to {cf_to!r} reuses stock control wording "
                        f"({pat_label})"
                    )

        if type(rc_after) is not int or rc_after not in {1, 2, 3, 4}:
            errors.append(f"{fid_str}: changed_fact.right_care_after must be int in {{1, 2, 3, 4}}, got {rc_after!r}")
        elif type(rc) is int and rc_after == rc:
            errors.append(f"{fid_str}: changed_fact.right_care_after ({rc_after}) must differ from right_care ({rc})")

    # Everyday sources & attribution checks (SPEC.md sections 5.8, 5.10, 5.11, 7)
    everyday_joined = " || ".join(
        texts[k]
        for k in ("everyday", "everyday_paraphrase", "changed_fact", "everyday_attribution", "quad_c")
        if k in texts and isinstance(texts[k], str)
    )

    ev_sources = fam["everyday_sources"]
    if not isinstance(ev_sources, list) or len(ev_sources) == 0:
        errors.append(f"{fid_str}: everyday_sources must be a non-empty list")
    else:
        for srec in ev_sources:
            _validate_source_item(
                srec,
                is_attribution=False,
                fid=fid_str,
                everyday_texts_joined=everyday_joined,
                errors=errors,
                warnings=warnings,
            )

    if has_att_obj and has_att_text:
        att = fam["attribution"]
        _validate_source_item(
            att,
            is_attribution=True,
            fid=fid_str,
            everyday_texts_joined=everyday_joined,
            errors=errors,
            warnings=warnings,
        )
        if isinstance(att, dict) and isinstance(att.get("clause"), str) and isinstance(carrier, str):
            clause = att["clause"]
            if texts["everyday"].endswith(" " + carrier):
                ev_prefix = texts["everyday"][: -(len(carrier) + 1)]
                expected_att_text = f"{ev_prefix} {clause} {carrier}"
                if texts["everyday_attribution"] != expected_att_text:
                    errors.append(
                        f"{fid_str}: texts.everyday_attribution must insert attribution.clause immediately "
                        f"before carrier_frame; expected {expected_att_text!r}"
                    )
            cl_low = clause.lower()
            for cphrase in COURSE_EXPECTATION_PHRASES:
                if cphrase in cl_low:
                    errors.append(
                        f"{fid_str}: attribution.clause contains course-expectation phrase {cphrase!r} "
                        "(SPEC.md section 5.8: must state perceived cause, not course)"
                    )

    return errors, warnings


def validate_audit_files(
    fam: dict[str, Any],
    batch_dir: Path,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Verify all 5 audit/source gate files exist under batch_dir and have verdict == 'pass'."""
    errors: list[str] = []
    warnings: list[str] = []
    fid = fam["family_id"]

    cited_count = sum(
        1 for s in fam.get("everyday_sources", []) if isinstance(s, dict) and s.get("source") != "none"
    )
    att = fam.get("attribution")
    if isinstance(att, dict) and att.get("source") != "none":
        cited_count += 1

    gate_specs = [
        ("G7", batch_dir / "sources" / f"{fid}.json"),
        ("G4", batch_dir / "audit" / f"{fid}.facts.json"),
        ("G5", batch_dir / "audit" / f"{fid}.language.json"),
        ("G6", batch_dir / "audit" / f"{fid}.level.json"),
        ("G8", batch_dir / "audit" / f"{fid}.adversarial.json"),
    ]

    meta: dict[str, Any] = {
        "stated_negative_from_language": False,
        "source_fit_rows": [],
    }

    for expected_gate, gpath in gate_specs:
        if not gpath.exists():
            errors.append(f"{fid}: missing {expected_gate} gate file {gpath.relative_to(batch_dir)}")
            continue
        try:
            doc = json.loads(gpath.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{fid}: invalid JSON in {gpath.relative_to(batch_dir)}: {exc}")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{fid}: {gpath.relative_to(batch_dir)} root must be a JSON object")
            continue
        if doc.get("family_id") != fid:
            errors.append(
                f"{fid}: {gpath.relative_to(batch_dir)} has family_id={doc.get('family_id')!r}, expected {fid!r}"
            )
        if "gate" in doc and doc["gate"] != expected_gate:
            errors.append(
                f"{fid}: {gpath.relative_to(batch_dir)} has gate={doc['gate']!r}, expected {expected_gate!r}"
            )
        verdict = doc.get("verdict")
        if verdict != "pass":
            fault = doc.get("fault_text") or doc.get("reason") or "no fault_text recorded"
            errors.append(
                f"{fid}: gate {expected_gate} ({gpath.relative_to(batch_dir)}) verdict={verdict!r} ({fault})"
            )
            continue

        if expected_gate == "G7":
            rows = doc.get("source_fit_rows")
            if not isinstance(rows, list):
                errors.append(f"{fid}: sources/{fid}.json missing list 'source_fit_rows'")
            else:
                if len(rows) != cited_count:
                    errors.append(
                        f"{fid}: sources/{fid}.json has {len(rows)} source_fit_rows, "
                        f"expected {cited_count} (one per cited expression/attribution)"
                    )
                clean_rows: list[dict[str, Any]] = []
                for r_idx, row in enumerate(rows):
                    if not isinstance(row, dict):
                        errors.append(f"{fid}: source_fit_rows[{r_idx}] must be an object")
                        continue
                    missing_rk = [k for k in SOURCE_FIT_ROW_KEYS if k not in row]
                    extra_rk = [k for k in row if k not in SOURCE_FIT_ROW_KEYS]
                    if missing_rk or extra_rk:
                        errors.append(
                            f"{fid}: source_fit_rows[{r_idx}] key mismatch; missing={missing_rk}, extra={extra_rk}"
                        )
                        continue
                    if row["family_id"] != fid:
                        errors.append(f"{fid}: source_fit_rows[{r_idx}].family_id != {fid!r}")
                    if row["fit"] not in {"same", "adjacent", "different"}:
                        errors.append(
                            f"{fid}: source_fit_rows[{r_idx}].fit={row['fit']!r} must be same|adjacent|different"
                        )
                    if row["source_speaker"] not in ALLOWED_SOURCE_SPEAKERS:
                        errors.append(
                            f"{fid}: source_fit_rows[{r_idx}].source_speaker={row['source_speaker']!r} "
                            f"must be one of {sorted(ALLOWED_SOURCE_SPEAKERS)}"
                        )
                    note_val = "" if row["note"] is None else row["note"]
                    if not isinstance(note_val, str):
                        errors.append(f"{fid}: source_fit_rows[{r_idx}].note must be string or null")
                        note_val = str(note_val)
                    if row["fit"] != "same" and not note_val.strip():
                        errors.append(
                            f"{fid}: source_fit_rows[{r_idx}] has fit={row['fit']!r} so 'note' must explain adaptation"
                        )
                    for rk in ("expression", "identifier", "source_population", "source_speaker", "family_population"):
                        rv = row[rk]
                        if not isinstance(rv, str) or not rv.strip():
                            errors.append(f"{fid}: source_fit_rows[{r_idx}].{rk} must be a non-empty string")
                        else:
                            _check_no_forbidden_db_ids(rv, f"{fid}:source_fit_rows[{r_idx}].{rk}", errors)
                    _check_no_forbidden_db_ids(note_val, f"{fid}:source_fit_rows[{r_idx}].note", errors)
                    clean_rows.append(
                        {
                            "family_id": row["family_id"],
                            "expression": row["expression"],
                            "identifier": row["identifier"],
                            "source_population": row["source_population"],
                            "source_speaker": row["source_speaker"],
                            "family_population": row["family_population"],
                            "fit": row["fit"],
                            "note": note_val,
                        }
                    )
                meta["source_fit_rows"] = clean_rows

        elif expected_gate == "G5":
            if doc.get("stated_negative") is True:
                meta["stated_negative_from_language"] = True
                if doc.get("stated_negative_justified") is False:
                    errors.append(f"{fid}: audit/{fid}.language.json marks stated_negative_justified=false")
                if not is_draft_stated_negative(fam):
                    errors.append(
                        f"{fid}: audit/{fid}.language.json flagged stated_negative=true, "
                        "so draft design_note must record '\"stated_negative\": true' with reason (SPEC.md section 4)"
                    )

        elif expected_gate == "G6":
            serialized_low = json.dumps(doc).lower()
            if "model" not in serialized_low or "clinician" not in serialized_low:
                errors.append(
                    f"{fid}: audit/{fid}.level.json must explicitly state this is a model's reading, not a clinician's"
                )

    return errors, warnings, meta


def validate_concerns_file(concerns_path: Path, expected_batch_id: str | None = None) -> list[str]:
    """Validate `concerns_selfreported.json` deterministically against SPEC.md section 10."""
    errors: list[str] = []
    if not concerns_path.exists():
        return [f"Missing concerns file: {concerns_path}"]
    try:
        doc = json.loads(concerns_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Invalid JSON in {concerns_path}: {exc}"]
    if not isinstance(doc, dict):
        return [f"{concerns_path}: root must be a JSON object"]
    if doc.get("schema") != "patientwords.intake-concerns/1":
        errors.append(f"{concerns_path}: schema must be 'patientwords.intake-concerns/1', got {doc.get('schema')!r}")
    if expected_batch_id and doc.get("batch_id") != expected_batch_id:
        errors.append(f"{concerns_path}: batch_id={doc.get('batch_id')!r} != expected {expected_batch_id!r}")
    concerns = doc.get("concerns")
    if not isinstance(concerns, list):
        errors.append(f"{concerns_path}: 'concerns' must be a list")
        return errors

    seen_cids: set[str] = set()
    for idx, rec in enumerate(concerns):
        if not isinstance(rec, dict):
            errors.append(f"{concerns_path}: concerns[{idx}] must be an object")
            continue
        cid = rec.get("concern_id")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(f"{concerns_path}: concerns[{idx}].concern_id must be non-empty string")
        elif cid in seen_cids:
            errors.append(f"{concerns_path}: duplicate concern_id {cid!r}")
        else:
            seen_cids.add(cid)

        fid = rec.get("family_id")
        if not isinstance(fid, str) or not FAMILY_ID_RE.match(fid):
            errors.append(f"{concerns_path}: concerns[{idx}] invalid family_id {fid!r}")

        kind = rec.get("kind")
        if kind not in ALLOWED_CONCERN_KINDS:
            errors.append(f"{concerns_path}: {cid}: invalid kind {kind!r}")

        applies = rec.get("applies_to")
        if not isinstance(applies, list) or not applies or any(a not in ALLOWED_CONCERN_APPLIES_TO for a in applies):
            errors.append(f"{concerns_path}: {cid}: invalid applies_to {applies!r}")

        if not isinstance(rec.get("text"), str) or not rec["text"].strip():
            errors.append(f"{concerns_path}: {cid}: text must be non-empty string")

        raised_by = rec.get("raised_by")
        raised_by_kind = rec.get("raised_by_kind")
        if not isinstance(raised_by, str) or not raised_by.startswith("Antigravity "):
            errors.append(f"{concerns_path}: {cid}: raised_by must start with 'Antigravity ', got {raised_by!r}")
        if raised_by_kind != "model":
            errors.append(f"{concerns_path}: {cid}: raised_by_kind must be 'model', got {raised_by_kind!r}")
        if not isinstance(rec.get("raised_on"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", rec["raised_on"]):
            errors.append(f"{concerns_path}: {cid}: raised_on must be YYYY-MM-DD")

        disp = rec.get("disposition")
        if not isinstance(disp, dict):
            errors.append(f"{concerns_path}: {cid}: disposition must be an object")
            continue
        dstatus = disp.get("status")
        if dstatus == "withdrawn":
            if disp.get("by") != raised_by or disp.get("by_kind") != raised_by_kind:
                errors.append(
                    f"{concerns_path}: {cid}: withdrawn disposition must set by={raised_by!r} and "
                    f"by_kind={raised_by_kind!r} (SPEC.md section 10)"
                )
            if not isinstance(disp.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", disp["date"]):
                errors.append(f"{concerns_path}: {cid}: withdrawn disposition requires YYYY-MM-DD 'date'")
            if not isinstance(disp.get("note"), str) or not disp["note"].strip():
                errors.append(f"{concerns_path}: {cid}: withdrawn disposition requires non-empty 'note'")
        elif dstatus in ALLOWED_MODEL_OPEN_DISPOSITIONS:
            if "note" not in disp or not isinstance(disp["note"], str):
                errors.append(f"{concerns_path}: {cid}: disposition requires string 'note'")
        else:
            errors.append(
                f"{concerns_path}: {cid}: invalid model disposition status {dstatus!r} "
                "(only a person closes a concern; models use pending_clinical_review, "
                "pending_patient_language_review, open, or withdrawn)"
            )

    return errors


def validate_batch_collection(
    families: list[dict[str, Any]],
    ref: dict[str, Any],
    *,
    batch_dir: Path | None = None,
    require_audits: bool = False,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Validate a collection of family dicts, cross-family uniqueness, Rule D caps, <=3 stated negatives, and audits."""
    all_errors: list[str] = []
    all_warnings: list[str] = []

    seen_ids: set[str] = set()
    seen_conditions: dict[str, str] = {}
    seen_texts: dict[str, str] = {}
    seen_cf_to: dict[str, str] = {}
    stated_neg_ids: list[str] = []
    bleeding_l4_ids: list[str] = []
    collected_source_fit_rows: list[dict[str, Any]] = []

    for fam in families:
        errs, warns = validate_family_dict(fam, ref)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        if not isinstance(fam, dict) or "family_id" not in fam:
            continue

        fid = str(fam["family_id"])
        if fid in seen_ids:
            all_errors.append(f"{fid}: duplicate family_id in batch collection")
        seen_ids.add(fid)

        cond = fam.get("condition")
        if isinstance(cond, str) and cond.strip():
            nc = normalize_space(cond)
            if nc in seen_conditions:
                all_errors.append(
                    f"{fid}: condition {cond!r} duplicates {seen_conditions[nc]} within this batch"
                )
            else:
                seen_conditions[nc] = fid

        cf_obj = fam.get("changed_fact")
        if isinstance(cf_obj, dict) and isinstance(cf_obj.get("to"), str) and cf_obj["to"].strip():
            cf_to_str = cf_obj["to"]
            for key_cf in {normalize_space(cf_to_str), normalize_cf_to_core(cf_to_str)}:
                if key_cf in seen_cf_to and seen_cf_to[key_cf].split(" ")[0] != fid:
                    all_errors.append(
                        f"{fid}: Rule D violation — changed_fact.to {cf_to_str!r} duplicates "
                        f"{seen_cf_to[key_cf]} within this batch"
                    )
                else:
                    seen_cf_to[key_cf] = f"{fid} ({cf_to_str!r})"

        if is_bleeding_l4_control(fam):
            bleeding_l4_ids.append(fid)

        texts = fam.get("texts")
        if isinstance(texts, dict):
            for tname, tval in texts.items():
                if isinstance(tval, str) and tval.strip():
                    nt = normalize_space(tval)
                    if nt in seen_texts and seen_texts[nt].split(".")[0] != fid:
                        all_errors.append(f"{fid}.{tname}: prompt text duplicates {seen_texts[nt]} in this batch")
                    else:
                        seen_texts[nt] = f"{fid}.{tname}"

        fam_stated_neg = is_draft_stated_negative(fam)
        if require_audits:
            if batch_dir is None:
                all_errors.append(f"{fid}: --require-audits requires a resolvable batch_NN directory")
            else:
                a_errs, a_warns, a_meta = validate_audit_files(fam, batch_dir)
                all_errors.extend(a_errs)
                all_warnings.extend(a_warns)
                if a_meta["stated_negative_from_language"]:
                    fam_stated_neg = True
                collected_source_fit_rows.extend(a_meta["source_fit_rows"])

        if fam_stated_neg:
            stated_neg_ids.append(fid)

    if len(bleeding_l4_ids) > 1:
        all_errors.append(
            f"Rule D violation: {len(bleeding_l4_ids)} emergency controls in batch move to level 4 through bleeding "
            f"({bleeding_l4_ids}); SPEC.md section 4 allows at most 1 per batch"
        )

    if len(stated_neg_ids) > 3:
        all_errors.append(
            f"Batch stated_negative count is {len(stated_neg_ids)} ({stated_neg_ids}), exceeding max 3 per batch "
            "(SPEC.md section 4)"
        )

    summary = {
        "families_checked": len(families),
        "stated_negative_count": len(stated_neg_ids),
        "stated_negative_ids": stated_neg_ids,
        "bleeding_l4_control_count": len(bleeding_l4_ids),
        "bleeding_l4_control_ids": bleeding_l4_ids,
        "source_fit_rows": collected_source_fit_rows,
    }
    return all_errors, all_warnings, summary


def _resolve_draft_paths(
    args: argparse.Namespace,
    dropped_ids: set[str],
) -> tuple[list[Path], Path | None, str | None]:
    batch_dir: Path | None = None
    batch_name: str | None = None
    if args.batch:
        bpath = Path(args.batch)
        if not bpath.is_absolute():
            cand = ROUND12_DIR / bpath
            bpath = cand if cand.exists() or bpath.parts[0].startswith("batch_") else bpath.resolve()
        batch_dir = bpath.resolve()
        batch_name = batch_dir.name

    explicit_files: list[str] = list(args.files or [])
    if args.family:
        for item in args.family:
            explicit_files.extend(item)

    paths: list[Path] = []
    if explicit_files:
        for raw in explicit_files:
            cand_p = Path(raw)
            if not cand_p.is_absolute() and not cand_p.exists() and (ROUND12_DIR / cand_p).exists():
                p = (ROUND12_DIR / cand_p).resolve()
            else:
                p = cand_p.resolve()
            paths.append(p)
            if batch_dir is None and p.parent.name == "drafts":
                batch_dir = p.parent.parent
                batch_name = batch_dir.name
    elif batch_dir is not None:
        drafts_dir = batch_dir / "drafts"
        if args.ids:
            wanted: list[str] = []
            for item in args.ids:
                wanted.extend(x.strip() for x in item.split(",") if x.strip())
            paths = [drafts_dir / f"{fid}.json" for fid in wanted]
        elif drafts_dir.exists():
            paths = [
                p
                for p in sorted(drafts_dir.glob("*.json"))
                if args.include_dropped or p.stem not in dropped_ids
            ]

    return paths, batch_dir, batch_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Round 12 draft family JSON files offline.")
    parser.add_argument("files", nargs="*", help="Path(s) to batch_NN/drafts/<family_id>.json")
    parser.add_argument(
        "--family",
        action="append",
        nargs="+",
        help="Path(s) to batch_NN/drafts/<family_id>.json (alias for positional files)",
    )
    parser.add_argument("--batch", help="Batch name (batch_01 or batch_02) or path to batch_NN directory")
    parser.add_argument("--ids", nargs="*", help="Specific family IDs when using --batch")
    parser.add_argument(
        "--include-dropped",
        action="store_true",
        help="Include dropped families when globbing --batch without --ids",
    )
    parser.add_argument(
        "--require-audits",
        action="store_true",
        help="Also verify sources/<id>.json and audit/<id>.{facts,language,level,adversarial}.json pass",
    )
    parser.add_argument(
        "--check-concerns",
        help="Optional path to batch_NN/concerns_selfreported.json to validate against SPEC.md section 10",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON validation summary")
    args = parser.parse_args(argv)

    if args.check_concerns and not args.files and not args.family and not args.batch:
        cpath = Path(args.check_concerns).resolve()
        expected_bid = None
        if cpath.parent.name in {"batch_01", "batch_02"}:
            expected_bid = f"r12_b{cpath.parent.name.split('_')[1]}"
        cerrs = validate_concerns_file(cpath, expected_batch_id=expected_bid)
        if args.json:
            print(json.dumps({"ok": len(cerrs) == 0, "errors": cerrs}, indent=2, ensure_ascii=False))
        else:
            for e in cerrs:
                print(f"ERROR: {e}")
            print(f"[{'PASS' if not cerrs else 'FAIL'}] checked concerns file {cpath} (errors={len(cerrs)})")
        return 0 if not cerrs else 1

    dropped_ids = load_dropped_ids()
    paths, batch_dir, batch_name = _resolve_draft_paths(args, dropped_ids)
    if not paths:
        parser.error("Provide one or more draft JSON files (positional or --family) or --batch batch_NN")

    loaded_families: list[dict[str, Any]] = []
    load_errors: list[str] = []
    current_ids: set[str] = {p.stem for p in paths}

    for p in paths:
        if not p.exists():
            load_errors.append(f"Missing draft file: {p}")
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            load_errors.append(f"Invalid JSON in {p}: {exc}")
            continue
        if isinstance(doc, dict) and p.parent.name == "drafts" and p.stem != doc.get("family_id"):
            load_errors.append(f"{p}: filename stem {p.stem!r} != family_id {doc.get('family_id')!r}")
        if not isinstance(doc, dict):
            load_errors.append(f"{p}: root must be a JSON object")
            continue
        if isinstance(doc.get("family_id"), str):
            current_ids.add(doc["family_id"])
        loaded_families.append(doc)

    ref = load_reference_data(
        current_batch_name=batch_name,
        current_batch_dir=batch_dir,
        exclude_current_ids=current_ids,
    )

    errs, warns, summary = validate_batch_collection(
        loaded_families,
        ref,
        batch_dir=batch_dir,
        require_audits=args.require_audits,
    )
    all_errors = load_errors + errs

    if args.check_concerns:
        cpath = Path(args.check_concerns).resolve()
        expected_bid = f"r12_b{batch_name.split('_')[1]}" if batch_name in {"batch_01", "batch_02"} else None
        all_errors.extend(validate_concerns_file(cpath, expected_batch_id=expected_bid))

    if args.json:
        out = {
            "ok": len(all_errors) == 0,
            "files_checked": [str(p) for p in paths],
            "require_audits": args.require_audits,
            "errors": all_errors,
            "warnings": warns,
            "summary": {
                "families_checked": summary["families_checked"],
                "stated_negative_count": summary["stated_negative_count"],
                "stated_negative_ids": summary["stated_negative_ids"],
                "bleeding_l4_control_count": summary["bleeding_l4_control_count"],
                "bleeding_l4_control_ids": summary["bleeding_l4_control_ids"],
                "source_fit_rows_count": len(summary["source_fit_rows"]),
            },
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for w in warns:
            print(f"WARNING: {w}")
        for e in all_errors:
            print(f"ERROR: {e}")
        status = "PASS" if not all_errors else "FAIL"
        print(
            f"[{status}] checked {len(paths)} draft file(s) "
            f"(errors={len(all_errors)}, warnings={len(warns)}, "
            f"stated_negatives={summary['stated_negative_count']}, "
            f"bleeding_l4_controls={summary['bleeding_l4_control_count']}, "
            f"require_audits={args.require_audits})"
        )

    return 0 if not all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
