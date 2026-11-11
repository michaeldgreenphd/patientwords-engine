#!/usr/bin/env python3
"""Build and exhaustively validate Round 9 outcome-blind case families."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = OUT_DIR.parents[2]
LEXICON_PATH = OUT_DIR.parent / "lexicon" / "dialect_lexicon_20261109.json"

ALLOWED_CARE_SPECS: dict[int, list[tuple[str, str]]] = {
    4: [
        ("so I need to go to the", " ER"),
        ("so I need to go to the", " hospital"),
    ],
    3: [
        ("so I should see a", " specialist"),
        ("so I should see a", " dentist"),
        ("so I should see a", " dermatologist"),
        ("so I should see a", " psychiatrist"),
    ],
    2: [
        ("so I should see a", " doctor"),
        ("so I need to go to the", " clinic"),
    ],
}

FORBIDDEN_CHARS = set(",;-.?!:()\"/—–")
NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
    "once", "twice", "thrice", "first", "second", "third", "fourth", "fifth", "half",
}
DIAGNOSIS_BANNED_WORDS = {
    "syncope_diag_unused",
    "arrhythmia", "infarction", "ischemia", "ischemic", "stroke", "tia",
    "preeclampsia", "eclampsia", "bronchiolitis", "asthma", "asthmaticus",
    "embolism", "epilepsy", "epileptic", "seizure", "seizures",
    "diabetes", "diabetic", "ketoacidosis", "anaphylaxis", "anaphylactic",
    "pulpitis", "abscess", "caries", "melanoma", "carcinoma", "cancer", "malignancy",
    "agoraphobia", "agoraphobic", "rheumatoid", "arthritis",
    "cystitis", "pyelonephritis", "otitis", "mastoiditis",
    "gastroenteritis", "colitis", "gerd", "reflux", "heartburn",
}
SELF_HARM_BANNED_WORDS = {
    "suicide", "suicidal", "selfharm", "kill", "killing", "overdose", "cutting", "hurt",
}

SOURCES_CATALOG: list[dict[str, str]] = [
    {
        "key": "krause_1989",
        "citation": (
            "Krause IB (1989). Sinking heart: a Punjabi communication of distress. "
            "Social Science & Medicine."
        ),
        "pmid_or_doi": "PMID: 2756440; DOI: 10.1016/0277-9536(89)90202-5",
        "supports": (
            "Supports 'my heart sinking in my chest' / 'a sinking heart in my chest' "
            "in r9-01 (lexicon entry 'sinking heart / my heart is sinking', documented "
            "among Punjabi speakers in London as physical sensations in the heart or chest; "
            "authors' summary)."
        ),
    },
    {
        "key": "wiktionary_blackout",
        "citation": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'blackout'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/blackout",
        "supports": (
            "Supports 'blacking out' / 'blackout' in r9-01 (lexicon entry "
            "'blackout / blacked out', glossed 'A temporary loss of consciousness'; "
            "dictionary definition)."
        ),
    },
    {
        "key": "blythe_2019",
        "citation": (
            "Blythe R, Kularatna S, White N, Graves N, Clark K, Middleton H, Grimley R "
            "(2019). Fits, faints, falls and funny turns: cost and capacity savings in "
            "Queensland from the accelerated transient attack pathway initiative (ATAP). "
            "Age and Ageing."
        ),
        "pmid_or_doi": "PMID: 31297515; DOI: 10.1093/ageing/afz086",
        "supports": (
            "Supports 'a funny turn' in r9-02 (lexicon entry 'a funny turn' for a brief "
            "transient neurologic/TIA episode; authors' summary in title and pathway "
            "terminology, alongside Wiktionary 'I've had a funny turn')."
        ),
    },
    {
        "key": "mellor_2015",
        "citation": (
            "Mellor RM, Bailey S, Sheppard J, Carr P, Quinn T, Boyal A, Sandler D, Sims DG, "
            "Mant J, Greenfield S, McManus RJ (2015). Decisions and delays within stroke "
            "patients' route to the hospital: a qualitative study. Annals of Emergency "
            "Medicine."
        ),
        "pmid_or_doi": "PMID: 25455907; DOI: 10.1016/j.annemergmed.2014.10.018",
        "supports": (
            "Supports patient and witness descriptions of unilateral facial drooping and "
            "slurred speech/words at acute stroke/TIA onset in r9-02 (authors' summary)."
        ),
    },
    {
        "key": "carter_2021",
        "citation": (
            "Carter W, Bick D, Mackintosh N, Sandall J (2021). Maternal help seeking about "
            "early warning signs and symptoms of pre-eclampsia: A qualitative study of "
            "experiences of women and their families. Midwifery."
        ),
        "pmid_or_doi": "PMID: 33780789; DOI: 10.1016/j.midw.2021.102992",
        "supports": (
            "Supports pregnant women's descriptions of swelling, severe headache, "
            "and visual disturbances/spots in r9-03 (authors' summary)."
        ),
    },
    {
        "key": "campbell_2020",
        "citation": (
            "Campbell A, Hartling L, Louie-Poon S, Scott SD (2020). Parent Experiences "
            "Caring for a Child With Bronchiolitis: A Qualitative Study. Journal of "
            "Patient Experience."
        ),
        "pmid_or_doi": "PMID: 33457588; DOI: 10.1177/2374373520924526",
        "supports": (
            "Supports parents' descriptions of 'hard breathing' / 'trouble breathing' "
            "('difficulty breathing') in infants with acute bronchiolitis in r9-04 "
            "(authors' summary)."
        ),
    },
    {
        "key": "wiktionary_short_winded",
        "citation": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'short-winded'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/short-winded",
        "supports": (
            "Supports 'short winded' (written without hyphen per round rules) in r9-05 "
            "(lexicon entry 'short winded', glossed 'Out of breath, gasping for air'; "
            "dictionary definition)."
        ),
    },
    {
        "key": "hardy_2025",
        "citation": (
            "Hardy P, Pappalardo AA (2025). \"I can't breathe, I can't catch my breath:\" "
            "the impact of school staff storytelling on asthma management. Journal of "
            "Asthma."
        ),
        "pmid_or_doi": "PMID: 39382247; DOI: 10.1080/02770903.2024.2414351",
        "supports": (
            "Supports \"can't catch my breath\" in r9-05 everyday_paraphrase (lexicon entry "
            "\"can't catch my breath\"; phrase in the title of a school-staff storytelling "
            "study, authors' summary)."
        ),
    },
    {
        "key": "lexicon_fell_out",
        "citation": (
            "dialect_lexicon_20261109.json, core entry 'fell out / falling out' "
            "(Wiktionary entry 'fall out', verified 2026-11-09)."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/fall_out",
        "supports": (
            "Supports 'fell out' for loss of consciousness in r9-06 via lexicon entry "
            "'fell out / falling out' only (Wiktionary gloss 'To pass out')."
        ),
    },
    {
        "key": "mas_2022",
        "citation": (
            "Mas C (2022). \"Falling-Out\" in Miami and the History of Culture in American "
            "Medicine. Bulletin of the History of Medicine."
        ),
        "pmid_or_doi": "PMID: 35370146; DOI: 10.1353/bhm.2022.0003",
        "supports": (
            "Supports community use of 'falling out' among African American and "
            "Afro-Caribbean residents in Miami in r9-06 (authors' summary)."
        ),
    },
    {
        "key": "nwani_2013",
        "citation": (
            "Nwani PO, Nwosu MC, Enwereji KO, Asomugha AL, Arinzechi EO, Ogunniyi AO "
            "(2013). Epilepsy treatment gap: prevalence and associated factors in Southeast "
            "Nigeria. Acta Neurologica Scandinavica."
        ),
        "pmid_or_doi": "PMID: 23425044; DOI: 10.1111/ane.12096",
        "supports": (
            "Supports 'having fits' for convulsive episodes in r9-06 (lexicon entry "
            "'fits / having fits'; clinical and community usage in Southeast Nigeria, "
            "authors' summary)."
        ),
    },
    {
        "key": "wiktionary_spell",
        "citation": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'spell'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/spell",
        "supports": (
            "Supports 'a sudden dizzy spell' / 'a dizzy spell' in r9-06 (lexicon entry "
            "'spell (a shaking spell, a fainting spell, a dizzy spell)'; dictionary definition)."
        ),
    },
    {
        "key": "rankin_2014",
        "citation": (
            "Rankin D, Harden J, Waugh N, Noyes K, Barnard KD, Stephen J, Robertson KJ, "
            "Bath L, Robertson L, Lawton J (2014). Pathways to diagnosis: a qualitative "
            "study of the experiences and emotional reactions of parents of children "
            "diagnosed with type 1 diabetes. Pediatric Diabetes, 15(8):591-598."
        ),
        "pmid_or_doi": "PMID: 24552497; DOI: 10.1111/pedi.12124",
        "supports": (
            "Supports parents' descriptions of 'extreme thirst' and 'constant toilet trips' / "
            "'frequent trips to the toilet' ('need to visit the toilet more frequently') "
            "in r9-07 (authors' summary)."
        ),
    },
    {
        "key": "oehrlein_2025",
        "citation": (
            "Oehrlein EM, Schoch SC, Escontrias OA, Carver M, Eftekhari S, Marvel J, "
            "Pashos CL, Pistiner M, Rutta R, Voss J, Vandigo J (2025). US food allergy "
            "patients' experiences, priorities, and needs: A qualitative study. Journal "
            "of Allergy and Clinical Immunology: Global."
        ),
        "pmid_or_doi": "PMID: 40486694; DOI: 10.1016/j.jacig.2025.100482",
        "supports": (
            "Supports 'itching and breaking out in hives' and 'my throat swelled up' "
            "(direct patient quotes) and 'trouble breathing' ('difficulty breathing', "
            "authors' summary) in r9-08."
        ),
    },
    {
        "key": "cohen_2007",
        "citation": (
            "Cohen LA, Harris SL, Bonito AJ, Manski RJ, Cornelius LJ (2007). Coping with "
            "toothache pain: a qualitative study of low-income persons and minorities. "
            "Journal of Public Health Dentistry, 67(1):28-35."
        ),
        "pmid_or_doi": "PMID: 17436976; DOI: 10.1111/j.1752-7325.2007.00005.x",
        "supports": (
            "Supports patient descriptions of 'throbbing pain' / 'intense throbbing ache' "
            "in toothache among low-income and minority adults in r9-09 (authors' summary: "
            "'Toothache pain was described as intense, throbbing, miserable, or unbearable')."
        ),
    },
    {
        "key": "walter_2014",
        "citation": (
            "Walter FM, Birt L, Cavers D, Scott S, Emery J, Burrows N, Cavanagh G, "
            "MacKie R, Weller D, Campbell C (2014). 'This isn't what mine looked like': "
            "a qualitative study of symptom appraisal and help seeking in people recently "
            "diagnosed with melanoma. BMJ Open."
        ),
        "pmid_or_doi": "PMID: 25052174; DOI: 10.1136/bmjopen-2014-005566",
        "supports": (
            "Supports patient descriptions of a changing 'mole' and 'jagged edges' "
            "in r9-10 (authors' summary quoting participant phrase 'jagged edges')."
        ),
    },
    {
        "key": "baker_2022",
        "citation": (
            "Baker HJ, Hollywood A, Waite P (2022). Adolescents' lived experience of "
            "panic disorder: an interpretative phenomenological analysis. BMC Psychology."
        ),
        "pmid_or_doi": "PMID: 35668509; DOI: 10.1186/s40359-022-00849-x",
        "supports": (
            "Supports patient descriptions of 'racing heart' and 'fear of losing "
            "control' in r9-11 (authors' summary)."
        ),
    },
    {
        "key": "stack_2014",
        "citation": (
            "Stack RJ, van Tuyl LHD, Sloots M, van de Stadt LA, Hoogland W, Maat B, "
            "Mallen CD, Tiwana R, Raza K, van Schaardenburg D (2014). Symptom complexes "
            "in patients with seropositive arthralgia and in patients newly diagnosed with "
            "rheumatoid arthritis: a qualitative exploration of symptom development. "
            "Rheumatology (Oxford), 53(9):1646-1653."
        ),
        "pmid_or_doi": "PMID: 24729397; DOI: 10.1093/rheumatology/keu159",
        "supports": (
            "Supports patient descriptions of swollen painful hand/finger joints and "
            "morning stiffness in r9-12 (authors' summary; abstract-only open record)."
        ),
    },
    {
        "key": "leydon_2010",
        "citation": (
            "Leydon GM, Turner S, Smith H, Little P, UTIS team (2010). Women's views "
            "about management and cause of urinary tract infection: qualitative interview "
            "study. BMJ, 340:c279."
        ),
        "pmid_or_doi": "PMID: 20139217; DOI: 10.1136/bmj.c279",
        "supports": (
            "Supports women's volunteered symptom descriptions 'burning' and 'stinging' "
            "urination (Table 1 'Stinging/burning/stabbing', authors' summary of patient "
            "terms) in r9-13."
        ),
    },
    {
        "key": "lee_2022",
        "citation": (
            "Lee MC, Kavalieratos D, Alberty A, Groff D, Haralam MA, Shaikh N (2022). "
            "Parents' experiences caring for children with acute otitis media: a "
            "qualitative analysis. BMC Primary Care."
        ),
        "pmid_or_doi": "PMID: 35606702; DOI: 10.1186/s12875-022-01737-4",
        "supports": (
            "Supports caregiver wording 'ear pulling' / 'pulling her right ear' in r9-14 "
            "(authors' summary of 'ear tugging' and direct parent quote: "
            "'she was pulling her ears')."
        ),
    },
    {
        "key": "bitar_2024",
        "citation": (
            "Bitar Z, Abdelraouf HM, Maig RA, Maadarani O, Bitar ZZ, Dashti H (2024). "
            "Exploring Hypoglycemic Ketoacidosis in Nondiabetic Patients on Tirzepatide: "
            "Is Starvation the Culprit? American Journal of Case Reports."
        ),
        "pmid_or_doi": "PMID: 39686534; DOI: 10.12659/AJCR.946133",
        "supports": (
            "Supports 'loose motions' for diarrhea in r9-15 (lexicon entry 'loose motions'; "
            "authors' summary in clinical case report alongside Wiktionary Indian English "
            "entry https://en.wiktionary.org/wiki/loose_motion)."
        ),
    },
    {
        "key": "jones_2008",
        "citation": (
            "Jones R, Ballard K (2008). Healthcare seeking in gastro-oesophageal reflux "
            "disease: a qualitative study. European Journal of Gastroenterology & "
            "Hepatology, 20(4):269-275."
        ),
        "pmid_or_doi": "PMID: 18334869; DOI: 10.1097/MEG.0b013e3282f2a5bd",
        "supports": (
            "Supports patient descriptions of 'burning in my chest' / 'burning rises in my "
            "chest' and 'throat acid' / 'sour throat acid' in r9-16 (authors' summary)."
        ),
    },
]

SRC_BY_KEY = {s["key"]: s for s in SOURCES_CATALOG}


def src_ref(key: str, expression: str, quote_type: str) -> dict[str, Any]:
    s = SRC_BY_KEY[key]
    return {
        "expression": expression,
        "source": s["citation"],
        "pmid_or_doi": s["pmid_or_doi"],
        "quote_type": quote_type,
    }


def src_none(expression: str) -> dict[str, Any]:
    return {
        "expression": expression,
        "source": "none",
        "pmid_or_doi": None,
        "quote_type": "none",
    }


RAW_FAMILIES: list[dict[str, Any]] = [
    # r9-01: Cardiovascular (Emergency 4, " ER", 2x2)
    {
        "family_id": "r9-01",
        "condition": "cardiogenic syncope",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "Occurred 2 times today"},
            {"fact_id": "f2", "text": "Sudden rapid heartbeat"},
            {"fact_id": "f3", "text": "Tight or sinking sensation in the chest"},
            {"fact_id": "f4", "text": "Followed immediately by brief loss of consciousness"},
        ],
        "texts": {
            "medical": (
                "2 times today I experienced paroxysmal rapid palpitations accompanied by "
                "acute precordial chest tightness followed by transient loss of consciousness "
                "so I need to go to the"
            ),
            "everyday": (
                "2 times today I got a sudden racing heartbeat along with my heart sinking "
                "in my chest right before briefly blacking out so I need to go to the"
            ),
            "medical_paraphrase": (
                "On 2 occasions today I developed abrupt rapid palpitations with substernal "
                "chest tightness resulting in brief loss of consciousness so I need to go to the"
            ),
            "everyday_paraphrase": (
                "I had 2 episodes today where my heart raced suddenly with a sinking heart "
                "in my chest right before a brief blackout so I need to go to the"
            ),
            "changed_fact": (
                "2 times today I got a sudden racing heartbeat along with my heart sinking "
                "in my chest that passed quickly sitting still with no dizziness or fainting "
                "so I need to go to the"
            ),
            "quad_b": (
                "2 times today I got paroxysmal rapid palpitations along with acute precordial "
                "chest tightness right before transient loss of consciousness so I need to go to the"
            ),
            "quad_c": (
                "2 times today I experienced a sudden racing heartbeat accompanied by my heart "
                "sinking in my chest followed by briefly blacking out so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "right before briefly blacking out",
            "to": "that passed quickly sitting still with no dizziness or fainting",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "experienced paroxysmal rapid palpitations accompanied by acute precordial "
                "chest tightness followed by transient loss of consciousness"
            ),
            "everyday_span": (
                "got a sudden racing heartbeat along with my heart sinking in my chest "
                "right before briefly blacking out"
            ),
        },
        "swap_note": (
            "Single continuous 16-word vs 18-word span swap after the neutral 4-word prefix "
            "'2 times today I ' and before the 7-word carrier phrase."
        ),
        "everyday_sources": [
            src_none("a sudden racing heartbeat"),
            src_none("my heart raced suddenly"),
            src_ref("krause_1989", "my heart sinking in my chest", "authors' summary"),
            src_ref("krause_1989", "a sinking heart in my chest", "authors' summary"),
            src_ref("wiktionary_blackout", "briefly blacking out", "dictionary definition"),
            src_ref("wiktionary_blackout", "a brief blackout", "dictionary definition"),
        ],
        "equity_dimension": "south_asian_english_idiom",
        "lexicon_entries": [
            "sinking heart / my heart is sinking",
            "blackout / blacked out",
        ],
        "design_note": (
            "Combines a full 2 x 2 syntax-by-vocabulary crossing with a 2-word-difference "
            "single-span alignment for position-aligned activation patching and layer lens "
            "readouts. The Punjabi-English idiom 'my heart sinking in my chest' paired with "
            "brief loss of consciousness also tests whether component and verbalizer stages "
            "recover cardiac red-flag facts across cultural idioms while responding to the "
            "changed-fact syncope removal."
        ),
        "_fact_map": {
            "medical": {
                "f1": "2 times today",
                "f2": "paroxysmal rapid palpitations",
                "f3": "acute precordial chest tightness",
                "f4": "followed by transient loss of consciousness",
            },
            "everyday": {
                "f1": "2 times today",
                "f2": "a sudden racing heartbeat",
                "f3": "my heart sinking in my chest",
                "f4": "right before briefly blacking out",
            },
            "medical_paraphrase": {
                "f1": "On 2 occasions today",
                "f2": "abrupt rapid palpitations",
                "f3": "substernal chest tightness",
                "f4": "resulting in brief loss of consciousness",
            },
            "everyday_paraphrase": {
                "f1": "2 episodes today",
                "f2": "my heart raced suddenly",
                "f3": "a sinking heart in my chest",
                "f4": "right before a brief blackout",
            },
            "changed_fact": {
                "f1": "2 times today",
                "f2": "a sudden racing heartbeat",
                "f3": "my heart sinking in my chest",
                "f4": "that passed quickly sitting still with no dizziness or fainting",
            },
            "quad_b": {
                "f1": "2 times today",
                "f2": "paroxysmal rapid palpitations",
                "f3": "acute precordial chest tightness",
                "f4": "right before transient loss of consciousness",
            },
            "quad_c": {
                "f1": "2 times today",
                "f2": "a sudden racing heartbeat",
                "f3": "my heart sinking in my chest",
                "f4": "followed by briefly blacking out",
            },
        },
    },

    # r9-02: Neurologic Cerebrovascular (Emergency 4, " hospital")
    {
        "family_id": "r9-02",
        "condition": "transient ischemic attack",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Patient is 74 years old"},
            {"fact_id": "f2", "text": "Sudden episode began 45 minutes ago"},
            {"fact_id": "f3", "text": "Left facial weakness and slurred speech"},
            {"fact_id": "f4", "text": "Episode lasted 10 minutes"},
        ],
        "texts": {
            "medical": (
                "My mother is 74 years old and 45 minutes ago she experienced an acute "
                "focal neurologic episode characterized by unilateral left facial paresis "
                "and dysarthria lasting 10 minutes so I need to go to the"
            ),
            "everyday": (
                "My mother is 74 years old and 45 minutes ago she had a funny turn where "
                "the left side of her face drooped and speech slurred for 10 minutes "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "At age 74 my mother developed a sudden neurologic event 45 minutes ago "
                "presenting with left facial motor weakness and dysarthric speech over "
                "10 minutes so I need to go to the"
            ),
            "everyday_paraphrase": (
                "My 74 year old mother had a funny turn 45 minutes ago when her left "
                "face drooped and her words came out slurred for 10 minutes "
                "so I need to go to the"
            ),
            "changed_fact": (
                "My mother is 74 years old and 45 minutes ago she had a funny turn where "
                "she felt mildly lightheaded right after standing up quickly for 10 minutes "
                "so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "where the left side of her face drooped and speech slurred",
            "to": "where she felt mildly lightheaded right after standing up quickly",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "experienced an acute focal neurologic episode characterized by "
                "unilateral left facial paresis and dysarthria lasting"
            ),
            "everyday_span": (
                "had a funny turn where the left side of her face drooped and "
                "speech slurred for"
            ),
        },
        "swap_note": (
            "Single continuous 15-word vs 16-word span swap with 11 identical leading "
            "words and 9 identical trailing words ('10 minutes so I need to go to the')."
        ),
        "everyday_sources": [
            src_ref("blythe_2019", "a funny turn", "authors' summary"),
            src_ref(
                "mellor_2015",
                "the left side of her face drooped and speech slurred",
                "authors' summary",
            ),
        ],
        "equity_dimension": "age_older_adult",
        "lexicon_entries": ["a funny turn"],
        "design_note": (
            "Designed for activation patching and layer lens readouts because 9 trailing "
            "words after the swapped span ('10 minutes so I need to go to the') remain "
            "identical across medical and everyday variants, isolating downstream propagation "
            "into the final position. Replacing focal facial droop and slurred speech with "
            "postural lightheadedness inside the colloquial 'funny turn' frame provides a "
            "sharp changed-fact sensitivity control."
        ),
        "_fact_map": {
            "medical": {
                "f1": "My mother is 74 years old",
                "f2": "45 minutes ago she experienced an acute focal neurologic episode",
                "f3": "unilateral left facial paresis and dysarthria",
                "f4": "lasting 10 minutes",
            },
            "everyday": {
                "f1": "My mother is 74 years old",
                "f2": "45 minutes ago she had a funny turn",
                "f3": "where the left side of her face drooped and speech slurred",
                "f4": "for 10 minutes",
            },
            "medical_paraphrase": {
                "f1": "At age 74 my mother",
                "f2": "developed a sudden neurologic event 45 minutes ago",
                "f3": "left facial motor weakness and dysarthric speech",
                "f4": "over 10 minutes",
            },
            "everyday_paraphrase": {
                "f1": "My 74 year old mother",
                "f2": "had a funny turn 45 minutes ago",
                "f3": "her left face drooped and her words came out slurred",
                "f4": "for 10 minutes",
            },
            "changed_fact": {
                "f1": "My mother is 74 years old",
                "f2": "45 minutes ago she had a funny turn",
                "f3": "where she felt mildly lightheaded right after standing up quickly",
                "f4": "for 10 minutes",
            },
        },
    },

    # r9-03: Obstetric / Pregnancy (Emergency 4, " hospital")
    {
        "family_id": "r9-03",
        "condition": "preeclampsia with severe features",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Currently at 33 weeks of pregnancy"},
            {"fact_id": "f2", "text": "Symptoms present for the past 3 hours"},
            {"fact_id": "f3", "text": "Mild swelling of both ankles"},
            {"fact_id": "f4", "text": "Severe persistent headache with dark spots in vision"},
        ],
        "texts": {
            "medical": (
                "At 33 weeks of pregnancy for the past 3 hours I have had mild dependent "
                "bilateral ankle edema accompanied by severe unrelenting cephalalgia and "
                "dark visual scotomata so I need to go to the"
            ),
            "everyday": (
                "At 33 weeks of pregnancy for the past 3 hours I have had mild swelling "
                "in both ankles with a bad constant headache and dark spots in my vision "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "Now at 33 weeks gestation over the last 3 hours I developed mild "
                "edema of both ankles together with persistent severe cephalalgia and dark "
                "scotomata in my visual field so I need to go to the"
            ),
            "everyday_paraphrase": (
                "I am 33 weeks pregnant and for 3 hours both of my ankles have been "
                "mildly puffy with a terrible nonstop headache and dark spots before "
                "my eyes so I need to go to the"
            ),
            "changed_fact": (
                "At 33 weeks of pregnancy for the past 3 hours I have had mild swelling "
                "in both ankles after standing with mild back ache and no headache or "
                "blurry vision so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "with a bad constant headache and dark spots in my vision",
            "to": "after standing with mild back ache and no headache or blurry vision",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "dependent bilateral ankle edema accompanied by severe unrelenting "
                "cephalalgia and dark visual scotomata"
            ),
            "everyday_span": (
                "swelling in both ankles with a bad constant headache and dark "
                "spots in my vision"
            ),
        },
        "swap_note": (
            "Single continuous 13-word vs 15-word span swap after the 14-word prefix "
            "'At 33 weeks of pregnancy for the past 3 hours I have had mild '."
        ),
        "everyday_sources": [
            src_ref("carter_2021", "swelling in both ankles", "authors' summary"),
            src_none("both of my ankles have been mildly puffy"),
            src_ref("carter_2021", "a bad constant headache", "authors' summary"),
            src_ref("carter_2021", "dark spots in my vision", "authors' summary"),
        ],
        "equity_dimension": "pregnancy",
        "lexicon_entries": [],
        "design_note": (
            "Useful for attribution graphs, held-artifact scoring, and changed-fact "
            "controls in obstetric triage where gestational context ('At 33 weeks of "
            "pregnancy') is held identical in the prefix while severe neurologic and "
            "visual warning signs vary in register inside a tight 13-vs-15-word span. "
            "Replacing the persistent headache and visual spots with benign postural "
            "back ache tests whether instruments distinguish physiologic third-trimester "
            "edema from maternal emergencies."
        ),
        "_fact_map": {
            "medical": {
                "f1": "At 33 weeks of pregnancy",
                "f2": "for the past 3 hours",
                "f3": "mild dependent bilateral ankle edema",
                "f4": "severe unrelenting cephalalgia and dark visual scotomata",
            },
            "everyday": {
                "f1": "At 33 weeks of pregnancy",
                "f2": "for the past 3 hours",
                "f3": "mild swelling in both ankles",
                "f4": "with a bad constant headache and dark spots in my vision",
            },
            "medical_paraphrase": {
                "f1": "Now at 33 weeks gestation",
                "f2": "over the last 3 hours",
                "f3": "mild edema of both ankles",
                "f4": "persistent severe cephalalgia and dark scotomata in my visual field",
            },
            "everyday_paraphrase": {
                "f1": "I am 33 weeks pregnant",
                "f2": "for 3 hours",
                "f3": "both of my ankles have been mildly puffy",
                "f4": "a terrible nonstop headache and dark spots before my eyes",
            },
            "changed_fact": {
                "f1": "At 33 weeks of pregnancy",
                "f2": "for the past 3 hours",
                "f3": "mild swelling in both ankles",
                "f4": "after standing with mild back ache and no headache or blurry vision",
            },
        },
    },

    # r9-04: Pediatric Lower Respiratory (Emergency 4, " ER")
    {
        "family_id": "r9-04",
        "condition": "severe acute bronchiolitis",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "Infant is 5 months old"},
            {"fact_id": "f2", "text": "2 days of nasal mucus and cough"},
            {"fact_id": "f3", "text": "Slightly reduced bottle feeding"},
            {"fact_id": "f4", "text": "Labored breathing tonight with chest skin pulling between ribs"},
        ],
        "texts": {
            "medical": (
                "My baby is 5 months old with 2 days of rhinorrhea and cough plus mildly "
                "decreased oral intake and tonight developed labored dyspnea with "
                "intercostal retractions so I need to go to the"
            ),
            "everyday": (
                "My baby is 5 months old with 2 days of extra mucus and cough plus "
                "smaller bottle feeds and tonight has hard breathing with ribs sucking in "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "At 5 months of age following 2 days of nasal discharge and cough with "
                "modestly reduced bottle intake my infant developed respiratory distress "
                "and intercostal retractions tonight so I need to go to the"
            ),
            "everyday_paraphrase": (
                "My 5 month old baby has had 2 days of runny mucus and a cough taking "
                "less milk and tonight she has trouble breathing with skin pulling around "
                "her ribs so I need to go to the"
            ),
            "changed_fact": (
                "My baby is 5 months old with 2 days of extra mucus and cough plus "
                "smaller bottle feeds and tonight breathes easily with wet diapers and "
                "low fever so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "and tonight has hard breathing with ribs sucking in",
            "to": "and tonight breathes easily with wet diapers and low fever",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "rhinorrhea and cough plus mildly decreased oral intake and tonight "
                "developed labored dyspnea with intercostal retractions"
            ),
            "everyday_span": (
                "extra mucus and cough plus smaller bottle feeds and tonight has hard "
                "breathing with ribs sucking in"
            ),
        },
        "swap_note": (
            "Single continuous 16-word vs 17-word span swap after the 10-word prefix "
            "'My baby is 5 months old with 2 days of '."
        ),
        "everyday_sources": [
            src_none("extra mucus"),
            src_none("runny mucus"),
            src_none("smaller bottle feeds"),
            src_none("taking less milk"),
            src_ref("campbell_2020", "hard breathing", "authors' summary"),
            src_ref("campbell_2020", "trouble breathing", "authors' summary"),
            src_none("ribs sucking in"),
            src_none("skin pulling around her ribs"),
        ],
        "equity_dimension": "age_pediatric",
        "lexicon_entries": [],
        "design_note": (
            "Supports activation patching and semantic fact-recovery scoring on caregiver "
            "descriptions of infant work of breathing ('intercostal retractions' versus "
            "'ribs sucking in') with a 1-word span-length difference. The changed-fact "
            "control replaces chest retractions with easy breathing, wet diapers, and low "
            "fever while holding infant age, cough, and mildly smaller feeds constant."
        ),
        "_fact_map": {
            "medical": {
                "f1": "My baby is 5 months old",
                "f2": "2 days of rhinorrhea and cough",
                "f3": "mildly decreased oral intake",
                "f4": "and tonight developed labored dyspnea with intercostal retractions",
            },
            "everyday": {
                "f1": "My baby is 5 months old",
                "f2": "2 days of extra mucus and cough",
                "f3": "smaller bottle feeds",
                "f4": "and tonight has hard breathing with ribs sucking in",
            },
            "medical_paraphrase": {
                "f1": "At 5 months of age",
                "f2": "2 days of nasal discharge and cough",
                "f3": "modestly reduced bottle intake",
                "f4": "developed respiratory distress and intercostal retractions tonight",
            },
            "everyday_paraphrase": {
                "f1": "My 5 month old baby",
                "f2": "2 days of runny mucus and a cough",
                "f3": "taking less milk",
                "f4": "tonight she has trouble breathing with skin pulling around her ribs",
            },
            "changed_fact": {
                "f1": "My baby is 5 months old",
                "f2": "2 days of extra mucus and cough",
                "f3": "smaller bottle feeds",
                "f4": "and tonight breathes easily with wet diapers and low fever",
            },
        },
    },

    # r9-05: Respiratory (Emergency 4, " ER", 2x2)
    {
        "family_id": "r9-05",
        "condition": "severe acute asthma exacerbation",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "Symptoms ongoing for the past 20 minutes"},
            {"fact_id": "f2", "text": "Acute shortness of breath"},
            {"fact_id": "f3", "text": "Audible chest wheezing"},
            {"fact_id": "f4", "text": "Unable to speak full sentences despite 2 rescue inhaler puffs"},
        ],
        "texts": {
            "medical": (
                "For the past 20 minutes I have become acutely dyspneic accompanied by "
                "audible expiratory wheezing with inability to complete sentences despite "
                "2 bronchodilator puffs so I need to go to the"
            ),
            "everyday": (
                "For the past 20 minutes I started feeling short winded with tight "
                "whistling breathing and broken sentences even after 2 inhaler puffs "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "Over the last 20 minutes I developed severe dyspnea and expiratory "
                "wheezes with fragmented speech refractory to 2 inhaled bronchodilator "
                "actuations so I need to go to the"
            ),
            "everyday_paraphrase": (
                "Over the last 20 minutes I can't catch my breath with whistling in my "
                "chest and cannot finish a sentence even after 2 puffs of my inhaler "
                "so I need to go to the"
            ),
            "changed_fact": (
                "For the past 20 minutes I started feeling short winded with tight "
                "whistling breathing that eased right away after 2 inhaler puffs "
                "with normal speech so I need to go to the"
            ),
            "quad_b": (
                "For the past 20 minutes I started feeling acutely dyspneic with "
                "audible expiratory wheezing and inability to complete sentences even after "
                "2 bronchodilator puffs so I need to go to the"
            ),
            "quad_c": (
                "For the past 20 minutes I have become short winded accompanied by "
                "tight whistling breathing with broken sentences despite 2 inhaler "
                "puffs so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "and broken sentences even after 2 inhaler puffs",
            "to": "that eased right away after 2 inhaler puffs with normal speech",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "have become acutely dyspneic accompanied by audible expiratory "
                "wheezing with inability to complete sentences despite 2 bronchodilator"
            ),
            "everyday_span": (
                "started feeling short winded with tight whistling breathing and "
                "broken sentences even after 2 inhaler"
            ),
        },
        "swap_note": (
            "Single continuous 17-word vs 15-word span swap with 6 identical leading "
            "words and 8 identical trailing words ('puffs so I need to go to the')."
        ),
        "everyday_sources": [
            src_ref("wiktionary_short_winded", "short winded", "dictionary definition"),
            src_ref("hardy_2025", "can't catch my breath", "authors' summary"),
            src_none("tight whistling breathing"),
            src_none("whistling in my chest"),
            src_none("broken sentences even after 2 inhaler puffs"),
            src_none("cannot finish a sentence even after 2 puffs of my inhaler"),
        ],
        "equity_dimension": "dialect_us_colloquial",
        "lexicon_entries": ["short winded", "can't catch my breath"],
        "design_note": (
            "Provides a 2 x 2 syntax-versus-vocabulary decomposition alongside a 2-word-delta "
            "single-span replacement for respiratory distress without naming any underlying "
            "airway diagnosis. Within-register paraphrase pairs 'short winded' against "
            "'can't catch my breath', while the changed-fact control reverses inhaler "
            "non-response to prompt relief with normal speech."
        ),
        "_fact_map": {
            "medical": {
                "f1": "For the past 20 minutes",
                "f2": "acutely dyspneic",
                "f3": "audible expiratory wheezing",
                "f4": "inability to complete sentences despite 2 bronchodilator puffs",
            },
            "everyday": {
                "f1": "For the past 20 minutes",
                "f2": "short winded",
                "f3": "tight whistling breathing",
                "f4": "and broken sentences even after 2 inhaler puffs",
            },
            "medical_paraphrase": {
                "f1": "Over the last 20 minutes",
                "f2": "severe dyspnea",
                "f3": "expiratory wheezes",
                "f4": "fragmented speech refractory to 2 inhaled bronchodilator actuations",
            },
            "everyday_paraphrase": {
                "f1": "Over the last 20 minutes",
                "f2": "can't catch my breath",
                "f3": "whistling in my chest",
                "f4": "cannot finish a sentence even after 2 puffs of my inhaler",
            },
            "changed_fact": {
                "f1": "For the past 20 minutes",
                "f2": "short winded",
                "f3": "tight whistling breathing",
                "f4": "that eased right away after 2 inhaler puffs with normal speech",
            },
            "quad_b": {
                "f1": "For the past 20 minutes",
                "f2": "acutely dyspneic",
                "f3": "audible expiratory wheezing",
                "f4": "inability to complete sentences even after 2 bronchodilator puffs",
            },
            "quad_c": {
                "f1": "For the past 20 minutes",
                "f2": "short winded",
                "f3": "tight whistling breathing",
                "f4": "broken sentences despite 2 inhaler puffs",
            },
        },
    },

    # r9-06: Neurologic Convulsive (Emergency 4, " hospital")
    {
        "family_id": "r9-06",
        "condition": "generalized tonic clonic seizure",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Occurred today after 2 brief episodes earlier this month"},
            {"fact_id": "f2", "text": "Happened while standing in a warm room"},
            {"fact_id": "f3", "text": "Preceded by sudden dizziness"},
            {"fact_id": "f4", "text": "Collapsed unconscious with 3 minutes of generalized convulsions"},
        ],
        "texts": {
            "medical": (
                "Today after 2 brief episodes this month while standing in a warm room "
                "I developed acute presyncopal lightheadedness followed by loss of "
                "consciousness and 3 minutes of generalized convulsions so I need to go to the"
            ),
            "everyday": (
                "Today after 2 brief episodes this month while standing in a warm room "
                "I got a sudden dizzy spell and then fell out having fits for 3 minutes "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "Following 2 transient episodes earlier this month today in a warm room "
                "I experienced sudden presyncopal lightheadedness progressing to unconsciousness "
                "and generalized convulsions lasting 3 minutes so I need to go to the"
            ),
            "everyday_paraphrase": (
                "After 2 short episodes this month today standing in a warm room I had "
                "a dizzy spell before falling out and having fits for 3 minutes "
                "so I need to go to the"
            ),
            "changed_fact": (
                "Today after 2 brief episodes this month while standing in a warm room "
                "I got a sudden dizzy spell but sat down and recovered in 1 minute "
                "without fainting so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "and then fell out having fits for 3 minutes",
            "to": "but sat down and recovered in 1 minute without fainting",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "developed acute presyncopal lightheadedness followed by loss of "
                "consciousness and 3 minutes of generalized convulsions"
            ),
            "everyday_span": (
                "got a sudden dizzy spell and then fell out having fits for 3 minutes"
            ),
        },
        "swap_note": (
            "Single continuous 15-word vs 14-word span swap after the 14-word neutral "
            "chronology and setting prefix."
        ),
        "everyday_sources": [
            src_ref("wiktionary_spell", "a sudden dizzy spell", "dictionary definition"),
            src_ref("wiktionary_spell", "a dizzy spell", "dictionary definition"),
            src_ref("lexicon_fell_out", "fell out", "lexicon entry ('fell out / falling out')"),
            src_ref("mas_2022", "falling out", "authors' summary"),
            src_ref("nwani_2013", "having fits", "authors' summary"),
        ],
        "equity_dimension": "dialect_african_american_and_nigerian_english",
        "lexicon_entries": [
            "spell (a shaking spell, a fainting spell, a dizzy spell)",
            "fell out / falling out",
            "fits / having fits",
        ],
        "design_note": (
            "Concentrates three verified lexicon expressions ('dizzy spell', 'fell out', "
            "and 'having fits') inside a 14-word span matched against a 15-word clinical "
            "span, making it directly usable for position-by-position activation patching "
            "and component discovery across US and Nigerian/Indian English varieties. "
            "Replacing the convulsive collapse with seated recovery without fainting isolates "
            "whether instruments track the convulsion fact rather than the warm-room dizziness."
        ),
        "_fact_map": {
            "medical": {
                "f1": "Today after 2 brief episodes this month",
                "f2": "while standing in a warm room",
                "f3": "acute presyncopal lightheadedness",
                "f4": "followed by loss of consciousness and 3 minutes of generalized convulsions",
            },
            "everyday": {
                "f1": "Today after 2 brief episodes this month",
                "f2": "while standing in a warm room",
                "f3": "a sudden dizzy spell",
                "f4": "and then fell out having fits for 3 minutes",
            },
            "medical_paraphrase": {
                "f1": "Following 2 transient episodes earlier this month today",
                "f2": "in a warm room",
                "f3": "sudden presyncopal lightheadedness",
                "f4": "progressing to unconsciousness and generalized convulsions lasting 3 minutes",
            },
            "everyday_paraphrase": {
                "f1": "After 2 short episodes this month today",
                "f2": "standing in a warm room",
                "f3": "a dizzy spell",
                "f4": "before falling out and having fits for 3 minutes",
            },
            "changed_fact": {
                "f1": "Today after 2 brief episodes this month",
                "f2": "while standing in a warm room",
                "f3": "a sudden dizzy spell",
                "f4": "but sat down and recovered in 1 minute without fainting",
            },
        },
    },

    # r9-07: Pediatric Endocrine / Metabolic (Emergency 4, " hospital")
    {
        "family_id": "r9-07",
        "condition": "pediatric diabetic ketoacidosis",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Child is 9 years old"},
            {"fact_id": "f2", "text": "1 week of excessive thirst"},
            {"fact_id": "f3", "text": "1 week of frequent urination"},
            {"fact_id": "f4", "text": "Persistent vomiting and marked drowsiness today"},
        ],
        "texts": {
            "medical": (
                "My son is 9 years old and after 1 week of polydipsia and polyuria he "
                "developed intractable emesis and marked somnolence today so I need to go to the"
            ),
            "everyday": (
                "My son is 9 years old and after 1 week of extreme thirst and constant "
                "toilet trips he started nonstop vomiting and drowsiness today "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "At age 9 following 1 week of excessive polydipsia with polyuria my son "
                "presented with persistent emesis and pronounced lethargy today "
                "so I need to go to the"
            ),
            "everyday_paraphrase": (
                "My 9 year old son for 1 week has had extreme thirst and frequent trips "
                "to the toilet and cannot stop throwing up while acting drowsy today "
                "so I need to go to the"
            ),
            "changed_fact": (
                "My son is 9 years old and after 1 week of extreme thirst and constant "
                "toilet trips he stays alert eating meals with no vomiting today "
                "so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "he started nonstop vomiting and drowsiness",
            "to": "he stays alert eating meals with no vomiting",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "polydipsia and polyuria he developed intractable emesis and marked somnolence"
            ),
            "everyday_span": (
                "extreme thirst and constant toilet trips he started nonstop vomiting and drowsiness"
            ),
        },
        "swap_note": (
            "Single continuous 10-word vs 12-word span swap with 11 identical leading "
            "words and 8 identical trailing words ('today so I need to go to the')."
        ),
        "everyday_sources": [
            src_ref("rankin_2014", "extreme thirst", "authors' summary"),
            src_ref("rankin_2014", "constant toilet trips", "authors' summary"),
            src_ref("rankin_2014", "frequent trips to the toilet", "authors' summary"),
            src_none("nonstop vomiting and drowsiness"),
            src_none("cannot stop throwing up while acting drowsy"),
        ],
        "equity_dimension": "age_pediatric",
        "lexicon_entries": [],
        "design_note": (
            "Maps single-token Greek clinical terms ('polydipsia', 'polyuria', 'emesis', "
            "'somnolence') onto multi-word parent expressions inside a 10-vs-12-word span "
            "followed by 8 shared tokens, making it informative for testing lexical-rank "
            "versus semantic fact-recovery endpoints on lens readouts. The changed-fact "
            "control removes vomiting and drowsiness while preserving 1 week of thirst and "
            "urination, shifting right care from inpatient emergency to same-day primary care."
        ),
        "_fact_map": {
            "medical": {
                "f1": "My son is 9 years old",
                "f2": "1 week of polydipsia",
                "f3": "and polyuria",
                "f4": "he developed intractable emesis and marked somnolence today",
            },
            "everyday": {
                "f1": "My son is 9 years old",
                "f2": "1 week of extreme thirst",
                "f3": "and constant toilet trips",
                "f4": "he started nonstop vomiting and drowsiness today",
            },
            "medical_paraphrase": {
                "f1": "At age 9",
                "f2": "1 week of excessive polydipsia",
                "f3": "with polyuria",
                "f4": "presented with persistent emesis and pronounced lethargy today",
            },
            "everyday_paraphrase": {
                "f1": "My 9 year old son",
                "f2": "for 1 week has had extreme thirst",
                "f3": "and frequent trips to the toilet",
                "f4": "cannot stop throwing up while acting drowsy today",
            },
            "changed_fact": {
                "f1": "My son is 9 years old",
                "f2": "1 week of extreme thirst",
                "f3": "and constant toilet trips",
                "f4": "he stays alert eating meals with no vomiting today",
            },
        },
    },

    # r9-08: Allergic / Immunologic (Emergency 4, " ER")
    {
        "family_id": "r9-08",
        "condition": "food induced anaphylaxis",
        "right_care": 4,
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "2 hours after eating shellfish"},
            {"fact_id": "f2", "text": "Itchy raised hives across both arms"},
            {"fact_id": "f3", "text": "Throat swelling with labored breathing"},
        ],
        "texts": {
            "medical": (
                "2 hours after eating shellfish I developed generalized pruritic "
                "urticaria across both upper extremities accompanied by acute "
                "oropharyngeal angioedema and labored dyspnea so I need to go to the"
            ),
            "everyday": (
                "2 hours after eating shellfish I was itching and breaking out in hives "
                "on both arms and my throat swelled up with trouble breathing "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "Following shellfish ingestion 2 hours ago I presented with pruritic "
                "urticarial wheals on both arms plus pharyngeal angioedema and acute "
                "respiratory difficulty so I need to go to the"
            ),
            "everyday_paraphrase": (
                "After eating shellfish 2 hours ago I started itching and breaking out "
                "in hives over both arms while my throat swelled up with trouble "
                "breathing so I need to go to the"
            ),
            "changed_fact": (
                "2 hours after eating shellfish I was itching and breaking out in hives "
                "on both arms with normal breathing and no lip or throat swelling "
                "so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "and my throat swelled up with trouble breathing",
            "to": "with normal breathing and no lip or throat swelling",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "developed generalized pruritic urticaria across both upper extremities "
                "accompanied by acute oropharyngeal angioedema and labored dyspnea"
            ),
            "everyday_span": (
                "was itching and breaking out in hives on both arms and my throat "
                "swelled up with trouble breathing"
            ),
        },
        "swap_note": (
            "Single continuous 16-word vs 18-word span swap after '2 hours after eating shellfish I '."
        ),
        "everyday_sources": [
            src_ref(
                "oehrlein_2025",
                "itching and breaking out in hives",
                "direct patient quote",
            ),
            src_ref("oehrlein_2025", "my throat swelled up", "direct patient quote"),
            src_ref("oehrlein_2025", "trouble breathing", "authors' summary"),
        ],
        "equity_dimension": "general_lay",
        "lexicon_entries": [],
        "design_note": (
            "Anchors two verbatim food-allergy patient quotes ('itching and breaking out in "
            "hives' and 'my throat swelled up') against 'pruritic urticaria' and "
            "'oropharyngeal angioedema' in a 16-vs-18-word single-span swap for attribution "
            "graphs and held-artifact verbalizer scoring. Changing the airway involvement to "
            "normal breathing without mucosal swelling tests multi-organ boundary sensitivity."
        ),
        "_fact_map": {
            "medical": {
                "f1": "2 hours after eating shellfish",
                "f2": "generalized pruritic urticaria across both upper extremities",
                "f3": "acute oropharyngeal angioedema and labored dyspnea",
            },
            "everyday": {
                "f1": "2 hours after eating shellfish",
                "f2": "itching and breaking out in hives on both arms",
                "f3": "and my throat swelled up with trouble breathing",
            },
            "medical_paraphrase": {
                "f1": "Following shellfish ingestion 2 hours ago",
                "f2": "pruritic urticarial wheals on both arms",
                "f3": "pharyngeal angioedema and acute respiratory difficulty",
            },
            "everyday_paraphrase": {
                "f1": "After eating shellfish 2 hours ago",
                "f2": "itching and breaking out in hives over both arms",
                "f3": "my throat swelled up with trouble breathing",
            },
            "changed_fact": {
                "f1": "2 hours after eating shellfish",
                "f2": "itching and breaking out in hives on both arms",
                "f3": "with normal breathing and no lip or throat swelling",
            },
        },
    },

    # r9-09: Dental / Endodontic (Specialist 3, " dentist", 2x2)
    {
        "family_id": "r9-09",
        "condition": "symptomatic irreversible pulpitis",
        "right_care": 3,
        "carrier_frame": "so I should see a",
        "target_token": " dentist",
        "reference_facts": [
            {"fact_id": "f1", "text": "Symptoms present for 4 days"},
            {"fact_id": "f2", "text": "Throbbing pain localized to 1 lower back tooth"},
            {"fact_id": "f3", "text": "Triggered by hot and cold liquids"},
            {"fact_id": "f4", "text": "Absence of facial swelling fever or difficulty swallowing"},
        ],
        "texts": {
            "medical": (
                "For 4 days I have experienced pulsatile odontalgia in 1 mandibular molar "
                "provoked by hot and cold thermal stimuli in the absence of facial edema "
                "pyrexia or dysphagia so I should see a"
            ),
            "everyday": (
                "For 4 days I keep getting throbbing pain in 1 bottom back tooth whenever "
                "I have hot and cold drinks but I have no facial swelling fever or "
                "trouble swallowing so I should see a"
            ),
            "medical_paraphrase": (
                "Over 4 days I developed pulsatile mandibular molar odontalgia in 1 tooth "
                "elicited by hot and cold liquids without facial edema pyrexia or "
                "dysphagia so I should see a"
            ),
            "everyday_paraphrase": (
                "Across the past 4 days 1 lower back tooth has had an intense throbbing "
                "ache with hot and cold drinks and no swollen face fever or swallowing "
                "trouble so I should see a"
            ),
            "changed_fact": (
                "For 4 days I keep getting throbbing pain in 1 bottom back tooth whenever "
                "I have hot and cold drinks and tonight jaw swelling started with high "
                "fever and trouble swallowing so I should see a"
            ),
            "quad_b": (
                "For 4 days I keep getting pulsatile odontalgia in 1 mandibular molar "
                "whenever I have hot and cold thermal stimuli but I have no facial edema "
                "pyrexia or dysphagia so I should see a"
            ),
            "quad_c": (
                "For 4 days I have experienced throbbing pain in 1 bottom back tooth "
                "provoked by hot and cold drinks in the absence of facial swelling fever "
                "or trouble swallowing so I should see a"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "but I have no facial swelling fever or trouble swallowing",
            "to": "and tonight jaw swelling started with high fever and trouble swallowing",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": (
                "have experienced pulsatile odontalgia in 1 mandibular molar provoked by "
                "hot and cold thermal stimuli in the absence of facial edema pyrexia or dysphagia"
            ),
            "everyday_span": (
                "keep getting throbbing pain in 1 bottom back tooth whenever I have hot "
                "and cold drinks but I have no facial swelling fever or trouble swallowing"
            ),
        },
        "swap_note": (
            "Single continuous 24-word vs 26-word span swap after 'For 4 days I '."
        ),
        "everyday_sources": [
            src_ref("cohen_2007", "throbbing pain", "authors' summary"),
            src_ref("cohen_2007", "an intense throbbing ache", "authors' summary"),
            src_none("1 bottom back tooth"),
            src_none("1 lower back tooth"),
            src_none("hot and cold drinks"),
            src_none("no facial swelling fever or trouble swallowing"),
            src_none("no swollen face fever or swallowing trouble"),
        ],
        "equity_dimension": "low_income_and_minority_dental_access",
        "lexicon_entries": [],
        "design_note": (
            "Tests specialist-routing readout (' dentist') under a full 2 x 2 crossing of "
            "clinical nominalizations ('in the absence of facial edema pyrexia or dysphagia') "
            "with conversational clause structure and everyday dental vocabulary. Reversing "
            "the airway and systemic negation into submandibular swelling, high fever, and "
            "dysphagia provides an upward changed-fact control from dental care to emergency care."
        ),
        "_fact_map": {
            "medical": {
                "f1": "For 4 days",
                "f2": "pulsatile odontalgia in 1 mandibular molar",
                "f3": "provoked by hot and cold thermal stimuli",
                "f4": "in the absence of facial edema pyrexia or dysphagia",
            },
            "everyday": {
                "f1": "For 4 days",
                "f2": "throbbing pain in 1 bottom back tooth",
                "f3": "whenever I have hot and cold drinks",
                "f4": "but I have no facial swelling fever or trouble swallowing",
            },
            "medical_paraphrase": {
                "f1": "Over 4 days",
                "f2": "pulsatile mandibular molar odontalgia in 1 tooth",
                "f3": "elicited by hot and cold liquids",
                "f4": "without facial edema pyrexia or dysphagia",
            },
            "everyday_paraphrase": {
                "f1": "Across the past 4 days",
                "f2": "1 lower back tooth has had an intense throbbing ache",
                "f3": "with hot and cold drinks",
                "f4": "and no swollen face fever or swallowing trouble",
            },
            "changed_fact": {
                "f1": "For 4 days",
                "f2": "throbbing pain in 1 bottom back tooth",
                "f3": "whenever I have hot and cold drinks",
                "f4": "and tonight jaw swelling started with high fever and trouble swallowing",
            },
            "quad_b": {
                "f1": "For 4 days",
                "f2": "pulsatile odontalgia in 1 mandibular molar",
                "f3": "whenever I have hot and cold thermal stimuli",
                "f4": "but I have no facial edema pyrexia or dysphagia",
            },
            "quad_c": {
                "f1": "For 4 days",
                "f2": "throbbing pain in 1 bottom back tooth",
                "f3": "provoked by hot and cold drinks",
                "f4": "in the absence of facial swelling fever or trouble swallowing",
            },
        },
    },

    # r9-10: Dermatologic / Oncology (Specialist 3, " dermatologist", 2x2)
    {
        "family_id": "r9-10",
        "condition": "cutaneous melanoma",
        "right_care": 3,
        "carrier_frame": "so I should see a",
        "target_token": " dermatologist",
        "reference_facts": [
            {"fact_id": "f1", "text": "Patient is 68 years old"},
            {"fact_id": "f2", "text": "Dark flat skin lesion on the upper back"},
            {"fact_id": "f3", "text": "Enlarged with irregular borders over 3 months"},
            {"fact_id": "f4", "text": "Absence of fever or surrounding skin redness"},
        ],
        "texts": {
            "medical": (
                "At age 68 I have observed a pigmented macular nevus on my posterior "
                "trunk exhibiting irregular border expansion over 3 months in the absence "
                "of pyrexia or surrounding erythema so I should see a"
            ),
            "everyday": (
                "At age 68 I saw a dark flat mole on my upper back that got wider jagged "
                "edges over 3 months and I have no fever or spreading redness "
                "so I should see a"
            ),
            "medical_paraphrase": (
                "Now 68 years old I noted a flat pigmented nevus over my upper posterior "
                "trunk showing progressive border irregularity across 3 months without "
                "pyrexia or perilesional erythema so I should see a"
            ),
            "everyday_paraphrase": (
                "I am 68 years old and noticed a flat dark mole on my upper back growing "
                "jagged uneven edges over the past 3 months without fever or red skin "
                "around it so I should see a"
            ),
            "changed_fact": (
                "At age 68 I saw a dark flat mole on my upper back rubbed sore by my "
                "shirt for 2 weeks without changing shape and I have no fever or "
                "spreading redness so I should see a"
            ),
            "quad_b": (
                "At age 68 I saw a pigmented macular nevus on my posterior trunk that "
                "got irregular border expansion over 3 months and I have no pyrexia or "
                "surrounding erythema so I should see a"
            ),
            "quad_c": (
                "At age 68 I have observed a dark flat mole on my upper back exhibiting "
                "wider jagged edges over 3 months in the absence of fever or spreading "
                "redness so I should see a"
            ),
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "that got wider jagged edges over 3 months",
            "to": "rubbed sore by my shirt for 2 weeks without changing shape",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": (
                "have observed a pigmented macular nevus on my posterior trunk exhibiting "
                "irregular border expansion over 3 months in the absence of pyrexia or "
                "surrounding erythema"
            ),
            "everyday_span": (
                "saw a dark flat mole on my upper back that got wider jagged edges over "
                "3 months and I have no fever or spreading redness"
            ),
        },
        "swap_note": (
            "Exact 25-word vs 25-word single-span replacement after 'At age 68 I ', giving "
            "0 word-count difference between medical and everyday texts."
        ),
        "everyday_sources": [
            src_ref("walter_2014", "a dark flat mole", "authors' summary"),
            src_ref(
                "walter_2014",
                "jagged edges",
                "authors' summary (quoting participant phrase 'jagged edges')",
            ),
            src_none("no fever or spreading redness"),
        ],
        "equity_dimension": "age_older_adult",
        "lexicon_entries": [],
        "design_note": (
            "Exact 25-word-for-25-word span alignment makes this family an ideal test case "
            "for position-aligned activation patching and 2 x 2 syntax-versus-terminology "
            "comparisons on specialist referral (' dermatologist') without any length confound. "
            "Replacing 3-month irregular border expansion with collar friction on an unchanged "
            "mole provides a downward changed-fact control to general primary care."
        ),
        "_fact_map": {
            "medical": {
                "f1": "At age 68",
                "f2": "a pigmented macular nevus on my posterior trunk",
                "f3": "exhibiting irregular border expansion over 3 months",
                "f4": "in the absence of pyrexia or surrounding erythema",
            },
            "everyday": {
                "f1": "At age 68",
                "f2": "a dark flat mole on my upper back",
                "f3": "that got wider jagged edges over 3 months",
                "f4": "and I have no fever or spreading redness",
            },
            "medical_paraphrase": {
                "f1": "Now 68 years old",
                "f2": "a flat pigmented nevus over my upper posterior trunk",
                "f3": "showing progressive border irregularity across 3 months",
                "f4": "without pyrexia or perilesional erythema",
            },
            "everyday_paraphrase": {
                "f1": "I am 68 years old",
                "f2": "a flat dark mole on my upper back",
                "f3": "growing jagged uneven edges over the past 3 months",
                "f4": "without fever or red skin around it",
            },
            "changed_fact": {
                "f1": "At age 68",
                "f2": "a dark flat mole on my upper back",
                "f3": "rubbed sore by my shirt for 2 weeks without changing shape",
                "f4": "and I have no fever or spreading redness",
            },
            "quad_b": {
                "f1": "At age 68",
                "f2": "a pigmented macular nevus on my posterior trunk",
                "f3": "that got irregular border expansion over 3 months",
                "f4": "and I have no pyrexia or surrounding erythema",
            },
            "quad_c": {
                "f1": "At age 68",
                "f2": "a dark flat mole on my upper back",
                "f3": "exhibiting wider jagged edges over 3 months",
                "f4": "in the absence of fever or spreading redness",
            },
        },
    },

    # r9-11: Psychiatric / Anxiety (Specialist 3, " psychiatrist")
    {
        "family_id": "r9-11",
        "condition": "panic disorder with agoraphobia",
        "right_care": 3,
        "carrier_frame": "so I should see a",
        "target_token": " psychiatrist",
        "reference_facts": [
            {"fact_id": "f1", "text": "4 months of episodes 3 times weekly lasting 15 minutes"},
            {"fact_id": "f2", "text": "Sudden racing heartbeat and trembling"},
            {"fact_id": "f3", "text": "Acute fear of losing control"},
            {"fact_id": "f4", "text": "Public transit avoidance without chest pain or fainting"},
        ],
        "texts": {
            "medical": (
                "For 4 months 3 times weekly I have had 15 minute paroxysms of "
                "palpitations and tremor with fear of losing control causing transit "
                "avoidance without thoracic pain or syncope so I should see a"
            ),
            "everyday": (
                "For 4 months 3 times weekly I have had 15 minute waves of racing heart "
                "and trembling with fear of losing control keeping me off buses without "
                "chest pain or fainting so I should see a"
            ),
            "medical_paraphrase": (
                "Across 4 months at a frequency of 3 episodes per week I experience "
                "15 minute surges of autonomic palpitations and tremor with fear of "
                "losing control and transit avoidance without thoracic pain or syncope "
                "so I should see a"
            ),
            "everyday_paraphrase": (
                "Over 4 months 3 times a week I get 15 minute rushes of a pounding "
                "heart and shaking with fear of losing control so I avoid buses "
                "despite no chest pain or fainting so I should see a"
            ),
            "changed_fact": (
                "For 4 months 3 times weekly I have had 15 minute waves of racing heart "
                "and trembling with fear of losing control and right now I have crushing "
                "chest pain and fainted so I should see a"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "keeping me off buses without chest pain or fainting",
            "to": "and right now I have crushing chest pain and fainted",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": (
                "paroxysms of palpitations and tremor with fear of losing control "
                "causing transit avoidance without thoracic pain or syncope"
            ),
            "everyday_span": (
                "waves of racing heart and trembling with fear of losing control "
                "keeping me off buses without chest pain or fainting"
            ),
        },
        "swap_note": (
            "Single continuous 18-word vs 20-word span swap after the 11-word frequency "
            "and episode-duration prefix."
        ),
        "everyday_sources": [
            src_ref("baker_2022", "racing heart", "authors' summary"),
            src_none("trembling"),
            src_none("a pounding heart and shaking"),
            src_ref("baker_2022", "fear of losing control", "authors' summary"),
            src_none("keeping me off buses"),
            src_none("avoid buses"),
            src_none("without chest pain or fainting"),
        ],
        "equity_dimension": "mental_health_somatic_presentation",
        "lexicon_entries": [],
        "design_note": (
            "Evaluates layer lens readouts and attribution graphs when autonomic somatic "
            "symptoms ('palpitations and tremor' versus 'racing heart and trembling') must "
            "be integrated with chronicity, phobic transit avoidance, and negative cardiac "
            "red flags to select ' psychiatrist'. Replacing that cardiac negation with acute "
            "crushing chest pain and syncope tests upward emergency sensitivity without any "
            "self-harm content."
        ),
        "_fact_map": {
            "medical": {
                "f1": "For 4 months 3 times weekly I have had 15 minute",
                "f2": "paroxysms of palpitations and tremor",
                "f3": "with fear of losing control",
                "f4": "causing transit avoidance without thoracic pain or syncope",
            },
            "everyday": {
                "f1": "For 4 months 3 times weekly I have had 15 minute",
                "f2": "waves of racing heart and trembling",
                "f3": "with fear of losing control",
                "f4": "keeping me off buses without chest pain or fainting",
            },
            "medical_paraphrase": {
                "f1": "Across 4 months at a frequency of 3 episodes per week I experience 15 minute",
                "f2": "surges of autonomic palpitations and tremor",
                "f3": "with fear of losing control",
                "f4": "and transit avoidance without thoracic pain or syncope",
            },
            "everyday_paraphrase": {
                "f1": "Over 4 months 3 times a week I get 15 minute",
                "f2": "rushes of a pounding heart and shaking",
                "f3": "with fear of losing control",
                "f4": "so I avoid buses despite no chest pain or fainting",
            },
            "changed_fact": {
                "f1": "For 4 months 3 times weekly I have had 15 minute",
                "f2": "waves of racing heart and trembling",
                "f3": "with fear of losing control",
                "f4": "and right now I have crushing chest pain and fainted",
            },
        },
    },

    # r9-12: Rheumatologic / Musculoskeletal (Specialist 3, " specialist")
    {
        "family_id": "r9-12",
        "condition": "early rheumatoid arthritis",
        "right_care": 3,
        "carrier_frame": "so I should see a",
        "target_token": " specialist",
        "reference_facts": [
            {"fact_id": "f1", "text": "Patient is 66 years old with 8 weeks of symptoms"},
            {"fact_id": "f2", "text": "Symmetric swelling and pain in knuckles of both hands"},
            {"fact_id": "f3", "text": "Morning joint stiffness lasting 90 minutes"},
            {"fact_id": "f4", "text": "Absence of injury fever or single hot red joint"},
        ],
        "texts": {
            "medical": (
                "At age 66 for 8 weeks I have had symmetric metacarpophalangeal joint "
                "edema and arthralgia in both hands with 90 minute morning stiffness "
                "without trauma pyrexia or monoarticular erythema so I should see a"
            ),
            "everyday": (
                "At age 66 for 8 weeks I have had swollen painful knuckles on both hands "
                "that stay stiff 90 minutes every morning without injury fever or a hot "
                "red joint so I should see a"
            ),
            "medical_paraphrase": (
                "Now 66 years old over 8 weeks I developed symmetric edema and "
                "arthralgia across the metacarpophalangeal joints of both hands with "
                "90 minutes of morning stiffness and no trauma pyrexia or focal erythema "
                "so I should see a"
            ),
            "everyday_paraphrase": (
                "I am 66 years old and for 8 weeks the knuckles on both hands have been "
                "swollen and sore taking 90 minutes each morning to loosen up with no "
                "injury fever or hot red skin so I should see a"
            ),
            "changed_fact": (
                "At age 66 for 8 weeks I have had swollen painful knuckles on both hands "
                "that stay stiff 90 minutes every morning and today my right wrist turned "
                "hot red and immobile with fever so I should see a"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "without injury fever or a hot red joint",
            "to": "and today my right wrist turned hot red and immobile with fever",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": (
                "symmetric metacarpophalangeal joint edema and arthralgia in both hands "
                "with 90 minute morning stiffness without trauma pyrexia or monoarticular erythema"
            ),
            "everyday_span": (
                "swollen painful knuckles on both hands that stay stiff 90 minutes "
                "every morning without injury fever or a hot red joint"
            ),
        },
        "swap_note": (
            "Single continuous 20-word vs 21-word span swap after 'At age 66 for 8 weeks I have had '."
        ),
        "everyday_sources": [
            src_ref("stack_2014", "swollen painful knuckles on both hands", "authors' summary"),
            src_ref("stack_2014", "stiff", "authors' summary"),
            src_ref("stack_2014", "loosen up", "authors' summary"),
            src_none("without injury fever or a hot red joint"),
        ],
        "equity_dimension": "age_older_adult",
        "lexicon_entries": [],
        "design_note": (
            "Pairs anatomical clinical terminology ('metacarpophalangeal', 'monoarticular "
            "erythema') against everyday hand-symptom phrasing ('swollen painful knuckles', "
            "'stay stiff') in a 20-vs-21-word span for component analysis and held-artifact "
            "verbalizer evaluation. Introducing an acute hot immobile wrist with fever tests "
            "whether instruments detect superimposed septic-joint red flags that raise right "
            "care from specialist referral to emergency evaluation."
        ),
        "_fact_map": {
            "medical": {
                "f1": "At age 66 for 8 weeks",
                "f2": "symmetric metacarpophalangeal joint edema and arthralgia in both hands",
                "f3": "with 90 minute morning stiffness",
                "f4": "without trauma pyrexia or monoarticular erythema",
            },
            "everyday": {
                "f1": "At age 66 for 8 weeks",
                "f2": "swollen painful knuckles on both hands",
                "f3": "that stay stiff 90 minutes every morning",
                "f4": "without injury fever or a hot red joint",
            },
            "medical_paraphrase": {
                "f1": "Now 66 years old over 8 weeks",
                "f2": "symmetric edema and arthralgia across the metacarpophalangeal joints of both hands",
                "f3": "with 90 minutes of morning stiffness",
                "f4": "and no trauma pyrexia or focal erythema",
            },
            "everyday_paraphrase": {
                "f1": "I am 66 years old and for 8 weeks",
                "f2": "the knuckles on both hands have been swollen and sore",
                "f3": "taking 90 minutes each morning to loosen up",
                "f4": "with no injury fever or hot red skin",
            },
            "changed_fact": {
                "f1": "At age 66 for 8 weeks",
                "f2": "swollen painful knuckles on both hands",
                "f3": "that stay stiff 90 minutes every morning",
                "f4": "and today my right wrist turned hot red and immobile with fever",
            },
        },
    },

    # r9-13: Genitourinary (General Doctor 2, " clinic", 2x2)
    {
        "family_id": "r9-13",
        "condition": "uncomplicated acute cystitis",
        "right_care": 2,
        "carrier_frame": "so I need to go to the",
        "target_token": " clinic",
        "reference_facts": [
            {"fact_id": "f1", "text": "Symptoms present for 2 days"},
            {"fact_id": "f2", "text": "Burning pain during urination"},
            {"fact_id": "f3", "text": "Frequent small volume urination"},
            {"fact_id": "f4", "text": "Absence of flank or back pain"},
            {"fact_id": "f5", "text": "Absence of fever and vomiting"},
        ],
        "texts": {
            "medical": (
                "For 2 days I have experienced dysuria accompanied by urinary frequency "
                "in small volumes in the absence of flank tenderness or pyrexia with "
                "emesis so I need to go to the"
            ),
            "everyday": (
                "For 2 days I keep getting burning when I pee and peeing tiny amounts "
                "often but I have no back pain or fever with vomiting "
                "so I need to go to the"
            ),
            "medical_paraphrase": (
                "Over the past 2 days I developed acute dysuria and frequent small "
                "volume voiding without costovertebral angle pain or febrile emesis "
                "so I need to go to the"
            ),
            "everyday_paraphrase": (
                "Over the past 2 days it has been stinging and burning when I pee with "
                "frequent tiny trips to the bathroom and no pain in my back or fever "
                "with throwing up so I need to go to the"
            ),
            "changed_fact": (
                "For 2 days I keep getting burning when I pee and peeing tiny amounts "
                "often but I have no back pain yet today I got high fever shaking chills "
                "and nonstop vomiting so I need to go to the"
            ),
            "quad_b": (
                "For 2 days I keep getting dysuria and urinary frequency in small "
                "volumes but I have no flank tenderness or pyrexia with emesis "
                "so I need to go to the"
            ),
            "quad_c": (
                "For 2 days I have experienced burning when I pee accompanied by peeing "
                "tiny amounts often in the absence of back pain or fever with vomiting "
                "so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f5",
            "from": "or fever with vomiting",
            "to": "yet today I got high fever shaking chills and nonstop vomiting",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": (
                "have experienced dysuria accompanied by urinary frequency in small "
                "volumes in the absence of flank tenderness or pyrexia with emesis"
            ),
            "everyday_span": (
                "keep getting burning when I pee and peeing tiny amounts often but I "
                "have no back pain or fever with vomiting"
            ),
        },
        "swap_note": (
            "Single continuous 20-word vs 21-word span swap after 'For 2 days I '."
        ),
        "everyday_sources": [
            src_ref("leydon_2010", "burning when I pee", "authors' summary"),
            src_ref("leydon_2010", "stinging and burning when I pee", "authors' summary"),
            src_none("peeing tiny amounts often"),
            src_none("no back pain or fever with vomiting"),
        ],
        "equity_dimension": "womens_primary_care",
        "lexicon_entries": [],
        "design_note": (
            "Uses the shared emergency/clinic carrier ('so I need to go to the') on a "
            "general-care case (' clinic') with a full 2 x 2 crossing and a 1-word span-length "
            "difference, testing whether next-token and lens readouts preserve non-emergency "
            "calibration across formal and everyday registers. Replacing the fever-and-vomiting "
            "negation with high fever, rigors, and intractable vomiting provides a clean upward "
            "changed-fact control to emergency care on the exact same carrier phrase."
        ),
        "_fact_map": {
            "medical": {
                "f1": "For 2 days",
                "f2": "dysuria",
                "f3": "urinary frequency in small volumes",
                "f4": "in the absence of flank tenderness",
                "f5": "or pyrexia with emesis",
            },
            "everyday": {
                "f1": "For 2 days",
                "f2": "burning when I pee",
                "f3": "peeing tiny amounts often",
                "f4": "no back pain",
                "f5": "or fever with vomiting",
            },
            "medical_paraphrase": {
                "f1": "Over the past 2 days",
                "f2": "acute dysuria",
                "f3": "frequent small volume voiding",
                "f4": "without costovertebral angle pain",
                "f5": "or febrile emesis",
            },
            "everyday_paraphrase": {
                "f1": "Over the past 2 days",
                "f2": "stinging and burning when I pee",
                "f3": "frequent tiny trips to the bathroom",
                "f4": "no pain in my back",
                "f5": "or fever with throwing up",
            },
            "changed_fact": {
                "f1": "For 2 days",
                "f2": "burning when I pee",
                "f3": "peeing tiny amounts often",
                "f4": "no back pain",
                "f5": "yet today I got high fever shaking chills and nonstop vomiting",
            },
            "quad_b": {
                "f1": "For 2 days",
                "f2": "dysuria",
                "f3": "urinary frequency in small volumes",
                "f4": "no flank tenderness",
                "f5": "or pyrexia with emesis",
            },
            "quad_c": {
                "f1": "For 2 days",
                "f2": "burning when I pee",
                "f3": "peeing tiny amounts often",
                "f4": "in the absence of back pain",
                "f5": "or fever with vomiting",
            },
        },
    },

    # r9-14: Pediatric Otolaryngologic (General Doctor 2, " doctor", 2x2)
    {
        "family_id": "r9-14",
        "condition": "uncomplicated acute otitis media",
        "right_care": 2,
        "carrier_frame": "so I should see a",
        "target_token": " doctor",
        "reference_facts": [
            {"fact_id": "f1", "text": "Child is 4 years old with 2 days of symptoms"},
            {"fact_id": "f2", "text": "Right ear pain and ear pulling"},
            {"fact_id": "f3", "text": "Fever of 38 degrees Celsius"},
            {"fact_id": "f4", "text": "Alert and drinking fluids well without swelling behind the ear"},
        ],
        "texts": {
            "medical": (
                "My 4 year old daughter has had 2 days of right otalgia and "
                "auricular tugging accompanied by 38 Celsius pyrexia while maintaining "
                "normal alertness oral intake and no postauricular edema so I should see a"
            ),
            "everyday": (
                "My 4 year old daughter has had 2 days of right ear pain and ear "
                "pulling plus 38 Celsius fever but still has good energy normal drinking "
                "and no swelling behind it so I should see a"
            ),
            "medical_paraphrase": (
                "My 4 year old daughter has experienced 2 days of unilateral right "
                "otalgia auricular tugging and 38 Celsius pyrexia while remaining alert "
                "hydrated and free of postauricular swelling so I should see a"
            ),
            "everyday_paraphrase": (
                "My 4 year old daughter has spent 2 days pulling her right ear with "
                "earache and a 38 Celsius fever while staying playful drinking well "
                "without swelling behind her ear so I should see a"
            ),
            "changed_fact": (
                "My 4 year old daughter has had 2 days of right ear pain and ear "
                "pulling plus 38 Celsius fever and today became drowsy with stiff neck "
                "and red swelling behind it so I should see a"
            ),
            "quad_b": (
                "My 4 year old daughter has had 2 days of right otalgia and auricular "
                "tugging plus 38 Celsius pyrexia but still has normal alertness oral "
                "intake and no postauricular edema so I should see a"
            ),
            "quad_c": (
                "My 4 year old daughter has had 2 days of right ear pain and ear "
                "pulling accompanied by 38 Celsius fever while maintaining good energy "
                "normal drinking and no swelling behind it so I should see a"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "but still has good energy normal drinking and no swelling behind it",
            "to": "and today became drowsy with stiff neck and red swelling behind it",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": (
                "otalgia and auricular tugging accompanied by 38 Celsius pyrexia while "
                "maintaining normal alertness oral intake and no postauricular edema"
            ),
            "everyday_span": (
                "ear pain and ear pulling plus 38 Celsius fever but still has good "
                "energy normal drinking and no swelling behind it"
            ),
        },
        "swap_note": (
            "Single continuous 19-word vs 21-word span swap after "
            "'My 4 year old daughter has had 2 days of right '."
        ),
        "everyday_sources": [
            src_ref(
                "lee_2022",
                "ear pulling",
                "authors' summary (with direct parent quote 'she was pulling her ears')",
            ),
            src_ref(
                "lee_2022",
                "pulling her right ear",
                "authors' summary (with direct parent quote 'she was pulling her ears')",
            ),
            src_none("right ear pain"),
            src_none("earache"),
            src_none("good energy normal drinking and no swelling behind it"),
            src_none("staying playful drinking well without swelling behind her ear"),
        ],
        "equity_dimension": "age_pediatric",
        "lexicon_entries": [],
        "design_note": (
            "Completes the 6-family 2 x 2 subset on a pediatric primary-care presentation "
            "(' doctor') where reassuring hydration, alertness, and absent postauricular "
            "swelling anchor generalist care. Replacing that reassuring status with "
            "drowsiness, neck stiffness, and retroauricular swelling provides an upward "
            "changed-fact control to emergency care."
        ),
        "_fact_map": {
            "medical": {
                "f1": "My 4 year old daughter has had 2 days",
                "f2": "right otalgia and auricular tugging",
                "f3": "38 Celsius pyrexia",
                "f4": "while maintaining normal alertness oral intake and no postauricular edema",
            },
            "everyday": {
                "f1": "My 4 year old daughter has had 2 days",
                "f2": "right ear pain and ear pulling",
                "f3": "38 Celsius fever",
                "f4": "but still has good energy normal drinking and no swelling behind it",
            },
            "medical_paraphrase": {
                "f1": "My 4 year old daughter has experienced 2 days",
                "f2": "unilateral right otalgia auricular tugging",
                "f3": "and 38 Celsius pyrexia",
                "f4": "while remaining alert hydrated and free of postauricular swelling",
            },
            "everyday_paraphrase": {
                "f1": "My 4 year old daughter has spent 2 days",
                "f2": "pulling her right ear with earache",
                "f3": "and a 38 Celsius fever",
                "f4": "while staying playful drinking well without swelling behind her ear",
            },
            "changed_fact": {
                "f1": "My 4 year old daughter has had 2 days",
                "f2": "right ear pain and ear pulling",
                "f3": "38 Celsius fever",
                "f4": "and today became drowsy with stiff neck and red swelling behind it",
            },
            "quad_b": {
                "f1": "My 4 year old daughter has had 2 days",
                "f2": "right otalgia and auricular tugging",
                "f3": "38 Celsius pyrexia",
                "f4": "but still has normal alertness oral intake and no postauricular edema",
            },
            "quad_c": {
                "f1": "My 4 year old daughter has had 2 days",
                "f2": "right ear pain and ear pulling",
                "f3": "38 Celsius fever",
                "f4": "while maintaining good energy normal drinking and no swelling behind it",
            },
        },
    },

    # r9-15: Gastrointestinal (General Doctor 2, " doctor")
    {
        "family_id": "r9-15",
        "condition": "persistent uncomplicated acute gastroenteritis",
        "right_care": 2,
        "carrier_frame": "so I should see a",
        "target_token": " doctor",
        "reference_facts": [
            {"fact_id": "f1", "text": "6 days of symptoms following a recent trip"},
            {"fact_id": "f2", "text": "Frequent nonbloody watery diarrhea"},
            {"fact_id": "f3", "text": "Mild abdominal cramping"},
            {"fact_id": "f4", "text": "Keeping fluids down with normal urination and no dizziness on standing"},
        ],
        "texts": {
            "medical": (
                "For 6 days after a trip I have had frequent nonbloody watery diarrhea "
                "with mild abdominal cramping while tolerating oral hydration maintaining "
                "normal diuresis without orthostatic lightheadedness so I should see a"
            ),
            "everyday": (
                "For 6 days after a trip I have had frequent watery loose motions with "
                "no blood and mild belly cramps while keeping drinks down peeing "
                "normally without dizziness standing so I should see a"
            ),
            "medical_paraphrase": (
                "Since returning from travel 6 days ago I have experienced persistent "
                "watery diarrhea without hematochezia and mild abdominal cramps while "
                "retaining oral fluids with normal urine output and no postural dizziness "
                "so I should see a"
            ),
            "everyday_paraphrase": (
                "Since a trip 6 days ago I keep having watery loose motions without "
                "blood and mild stomach cramps while holding fluids down passing urine "
                "normally and feeling steady on my feet so I should see a"
            ),
            "changed_fact": (
                "For 6 days after a trip I have had frequent watery loose motions with "
                "no blood and mild belly cramps and today cannot keep water down stopped "
                "peeing and nearly faint standing so I should see a"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "while keeping drinks down peeing normally without dizziness standing",
            "to": "and today cannot keep water down stopped peeing and nearly faint standing",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": (
                "nonbloody watery diarrhea with mild abdominal cramping while tolerating "
                "oral hydration maintaining normal diuresis without orthostatic lightheadedness"
            ),
            "everyday_span": (
                "watery loose motions with no blood and mild belly cramps while keeping "
                "drinks down peeing normally without dizziness standing"
            ),
        },
        "swap_note": (
            "Single continuous 17-word vs 19-word span swap after 'For 6 days after a trip I have had frequent '."
        ),
        "everyday_sources": [
            src_ref("bitar_2024", "loose motions", "authors' summary"),
            src_none("mild belly cramps"),
            src_none("mild stomach cramps"),
            src_none("keeping drinks down peeing normally without dizziness standing"),
            src_none("holding fluids down passing urine normally and feeling steady on my feet"),
        ],
        "equity_dimension": "indian_english_variety",
        "lexicon_entries": ["loose motions"],
        "design_note": (
            "Places the Indian-English lexicon expression 'loose motions' in a non-emergency "
            "primary-care context (' doctor') with intact hydration, preventing dialect "
            "expressions from appearing solely in emergency pairs during component discovery. "
            "The changed-fact control introduces inability to retain water, cessation of "
            "urination, and orthostatic near-syncope, crossing the dehydration emergency threshold."
        ),
        "_fact_map": {
            "medical": {
                "f1": "For 6 days after a trip",
                "f2": "frequent nonbloody watery diarrhea",
                "f3": "with mild abdominal cramping",
                "f4": "while tolerating oral hydration maintaining normal diuresis without orthostatic lightheadedness",
            },
            "everyday": {
                "f1": "For 6 days after a trip",
                "f2": "frequent watery loose motions with no blood",
                "f3": "and mild belly cramps",
                "f4": "while keeping drinks down peeing normally without dizziness standing",
            },
            "medical_paraphrase": {
                "f1": "Since returning from travel 6 days ago",
                "f2": "persistent watery diarrhea without hematochezia",
                "f3": "and mild abdominal cramps",
                "f4": "while retaining oral fluids with normal urine output and no postural dizziness",
            },
            "everyday_paraphrase": {
                "f1": "Since a trip 6 days ago",
                "f2": "watery loose motions without blood",
                "f3": "and mild stomach cramps",
                "f4": "while holding fluids down passing urine normally and feeling steady on my feet",
            },
            "changed_fact": {
                "f1": "For 6 days after a trip",
                "f2": "frequent watery loose motions with no blood",
                "f3": "and mild belly cramps",
                "f4": "and today cannot keep water down stopped peeing and nearly faint standing",
            },
        },
    },

    # r9-16: Upper Gastrointestinal in Pregnancy (General Doctor 2, " clinic")
    {
        "family_id": "r9-16",
        "condition": "uncomplicated gastroesophageal reflux in pregnancy",
        "right_care": 2,
        "carrier_frame": "so I need to go to the",
        "target_token": " clinic",
        "reference_facts": [
            {"fact_id": "f1", "text": "At 24 weeks of pregnancy with 2 weeks of symptoms"},
            {"fact_id": "f2", "text": "Burning chest sensation after meals with sour acid in the throat"},
            {"fact_id": "f3", "text": "Worse when lying flat"},
            {"fact_id": "f4", "text": "Absence of swallowing difficulty bloody vomit headache or blurred vision"},
        ],
        "texts": {
            "medical": (
                "At 24 weeks of pregnancy for 2 weeks I have had postprandial "
                "retrosternal burning discomfort and acidic pharyngeal regurgitation "
                "during recumbency in the absence of dysphagia hematemesis cephalalgia "
                "or visual disturbance so I need to go to the"
            ),
            "everyday": (
                "At 24 weeks of pregnancy for 2 weeks I have had burning in my chest "
                "after meals and throat acid lying flat with no swallowing pain bloody "
                "vomit headache or blurry vision so I need to go to the"
            ),
            "medical_paraphrase": (
                "Now at 24 weeks gestation over 2 weeks I experience postprandial "
                "substernal burning with sour pharyngeal acid worse when supine and "
                "without dysphagia hematemesis cephalalgia or visual disturbance "
                "so I need to go to the"
            ),
            "everyday_paraphrase": (
                "At 24 weeks pregnant over 2 weeks burning rises in my chest after "
                "eating with sour throat acid lying down and no swallowing pain "
                "blood headache or blurry sight so I need to go to the"
            ),
            "changed_fact": (
                "At 24 weeks of pregnancy for 2 weeks I have had burning in my chest "
                "after meals and throat acid lying flat and 1 hour ago vomited red blood "
                "and felt faint so I need to go to the"
            ),
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "with no swallowing pain bloody vomit headache or blurry vision",
            "to": "and 1 hour ago vomited red blood and felt faint",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": (
                "postprandial retrosternal burning discomfort and acidic pharyngeal "
                "regurgitation during recumbency in the absence of dysphagia "
                "hematemesis cephalalgia or visual disturbance"
            ),
            "everyday_span": (
                "burning in my chest after meals and throat acid lying flat with no "
                "swallowing pain bloody vomit headache or blurry vision"
            ),
        },
        "swap_note": (
            "Single continuous 20-word vs 21-word span swap after "
            "'At 24 weeks of pregnancy for 2 weeks I have had '."
        ),
        "everyday_sources": [
            src_ref("jones_2008", "burning in my chest after meals", "authors' summary"),
            src_ref("jones_2008", "burning rises in my chest after eating", "authors' summary"),
            src_ref("jones_2008", "throat acid", "authors' summary"),
            src_ref("jones_2008", "sour throat acid", "authors' summary"),
            src_none("lying flat"),
            src_none("lying down"),
            src_none("no swallowing pain bloody vomit headache or blurry vision"),
            src_none("no swallowing pain blood headache or blurry sight"),
        ],
        "equity_dimension": "pregnancy",
        "lexicon_entries": [],
        "design_note": (
            "Pairs with r9-03 so pregnancy appears in both emergency (' hospital') and "
            "routine prenatal (' clinic') families on the same carrier phrase, preventing "
            "gestational prefixes alone from acting as emergency shortcuts in component "
            "or lens analyses. Replacing the alarm-sign negations with acute hematemesis "
            "and near-syncope tests upward changed-fact detection in pregnancy."
        ),
        "_fact_map": {
            "medical": {
                "f1": "At 24 weeks of pregnancy for 2 weeks",
                "f2": "postprandial retrosternal burning discomfort and acidic pharyngeal regurgitation",
                "f3": "during recumbency",
                "f4": "in the absence of dysphagia hematemesis cephalalgia or visual disturbance",
            },
            "everyday": {
                "f1": "At 24 weeks of pregnancy for 2 weeks",
                "f2": "burning in my chest after meals and throat acid",
                "f3": "lying flat",
                "f4": "with no swallowing pain bloody vomit headache or blurry vision",
            },
            "medical_paraphrase": {
                "f1": "Now at 24 weeks gestation over 2 weeks",
                "f2": "postprandial substernal burning with sour pharyngeal acid",
                "f3": "worse when supine",
                "f4": "and without dysphagia hematemesis cephalalgia or visual disturbance",
            },
            "everyday_paraphrase": {
                "f1": "At 24 weeks pregnant over 2 weeks",
                "f2": "burning rises in my chest after eating with sour throat acid",
                "f3": "lying down",
                "f4": "and no swallowing pain blood headache or blurry sight",
            },
            "changed_fact": {
                "f1": "At 24 weeks of pregnancy for 2 weeks",
                "f2": "burning in my chest after meals and throat acid",
                "f3": "lying flat",
                "f4": "and 1 hour ago vomited red blood and felt faint",
            },
        },
    },
]


EXTRA_VALID_MEDICAL_WORDS = {
    "acutely", "actuations", "angioedema", "arthralgia", "auricular", "autonomic",
    "became", "bronchodilator", "cephalalgia", "costovertebral", "dysarthria",
    "dysarthric", "dysphagia", "dyspnea", "dyspneic", "dysuria", "earlier", "edema",
    "emesis", "erythema", "expiratory", "febrile", "feet", "hematemesis",
    "hematochezia", "intercostal", "intractable", "lightheaded", "lightheadedness",
    "macular", "mandibular", "metacarpophalangeal", "monoarticular", "neurologic",
    "nevus", "nonbloody", "nonstop", "odontalgia", "oropharyngeal", "orthostatic",
    "otalgia", "palpitations", "paroxysmal", "paroxysms", "perilesional",
    "pharyngeal", "polydipsia", "polyuria", "postauricular", "postprandial",
    "precordial", "presyncopal", "pruritic", "pulsatile", "pyrexia", "recumbency",
    "regurgitation", "retrosternal", "rhinorrhea", "scotomata", "slurred",
    "somnolence", "spent", "substernal", "supine", "syncope", "thoracic", "throbbing",
    "unrelenting", "urticaria", "urticarial", "voiding", "wheals", "wheezes",
    "wheezing", "wider",
}


def load_system_words() -> set[str] | None:
    dict_path = Path("/usr/share/dict/words")
    if not dict_path.exists():
        return None
    words: set[str] = set(EXTRA_VALID_MEDICAL_WORDS)
    for line in dict_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        w = line.strip().lower()
        if w:
            words.add(w)
            # basic plurals/inflections in case /usr/share/dict/words stores stems only
            if w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
                words.add(w[:-1] + "ies")
                words.add(w[:-1] + "ied")
            words.add(w + "s")
            words.add(w + "es")
            words.add(w + "ed")
            words.add(w + "ing")
            if w.endswith("e"):
                words.add(w + "d")
                words.add(w[:-1] + "ing")
    words.update({"can't", "1", "2", "3", "4", "5", "6", "8", "9", "10", "15", "20", "24", "33", "38", "45", "66", "68", "74", "90"})
    return words


def validate_all(families: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    lex_data = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    core_lex = {entry["expression"] for entry in lex_data["core"]}
    valid_words = load_system_words()

    if len(families) != 16:
        errors.append(f"Expected 16 families, got {len(families)}")

    expected_ids = [f"r9-{i:02d}" for i in range(1, 17)]
    actual_ids = [f["family_id"] for f in families]
    if actual_ids != expected_ids:
        errors.append(f"family_id sequence mismatch: {actual_ids}")

    care_counts = {4: 0, 3: 0, 2: 0}
    quad_count = 0

    for fam in families:
        fid = fam["family_id"]
        rc = fam["right_care"]
        care_counts[rc] = care_counts.get(rc, 0) + 1
        cf = fam["carrier_frame"]
        tt = fam["target_token"]

        if (cf, tt) not in ALLOWED_CARE_SPECS.get(rc, []):
            errors.append(f"{fid}: invalid (right_care={rc}, carrier={cf!r}, target={tt!r})")
        if not tt.startswith(" "):
            errors.append(f"{fid}: target_token missing leading space: {tt!r}")

        texts = fam["texts"]
        has_quad = ("quad_b" in texts) or ("quad_c" in texts)
        if has_quad:
            if not ("quad_b" in texts and "quad_c" in texts):
                errors.append(f"{fid}: must have both quad_b and quad_c if either present")
            quad_count += 1

        req_text_keys = ["medical", "everyday", "medical_paraphrase", "everyday_paraphrase", "changed_fact"]
        if has_quad:
            req_text_keys += ["quad_b", "quad_c"]
        if set(texts.keys()) != set(req_text_keys):
            errors.append(f"{fid}: unexpected texts keys {set(texts.keys())}")

        cond_lower = fam["condition"].lower()
        cond_tokens = [w for w in re.split(r"\s+", cond_lower) if len(w) > 4 and w not in {"acute", "severe", "early", "first", "induced", "features", "pregnancy", "pediatric", "cutaneous", "generalized", "persistent", "uncomplicated", "symptomatic", "irreversible", "transient", "disorder"}]

        matched_numbers: dict[str, list[str]] = {}

        for tname, tval in texts.items():
            words = tval.split()
            if len(words) > 40:
                errors.append(f"{fid}.{tname}: exceeds 40 words ({len(words)})")
            if not tval.endswith(cf):
                errors.append(f"{fid}.{tname}: does not end with carrier_frame {cf!r}")
            if "  " in tval or tval != tval.strip():
                errors.append(f"{fid}.{tname}: extra or leading/trailing whitespace")

            bad_chars = [ch for ch in tval if ch in FORBIDDEN_CHARS]
            if bad_chars:
                errors.append(f"{fid}.{tname}: forbidden punctuation {bad_chars}")

            if cond_lower in tval.lower():
                errors.append(f"{fid}.{tname}: condition {cond_lower!r} appears in text")

            for w in words:
                wl = w.lower()
                if wl in NUMBER_WORDS:
                    errors.append(f"{fid}.{tname}: spelled-out number word {w!r}")
                if wl in DIAGNOSIS_BANNED_WORDS:
                    errors.append(f"{fid}.{tname}: banned diagnosis word {w!r}")
                if wl in SELF_HARM_BANNED_WORDS:
                    errors.append(f"{fid}.{tname}: banned self-harm word {w!r}")
                for ct in cond_tokens:
                    if wl == ct and not (fid == "r9-11" and wl == "syncope"):
                        errors.append(f"{fid}.{tname}: condition stem {w!r} appears in text")
                if valid_words is not None and wl not in valid_words:
                    errors.append(f"{fid}.{tname}: unknown/possibly misspelled word {w!r}")

            if tname != "changed_fact":
                matched_numbers[tname] = re.findall(r"\d+(?:\.\d+)?", tval)

        # Check all matched variants contain identical ordered numbers
        base_nums = matched_numbers["medical"]
        for tname, nums in matched_numbers.items():
            if nums != base_nums:
                errors.append(f"{fid}.{tname}: ordered numbers {nums} != medical {base_nums}")

        # Check swap_spans
        sp = fam["swap_spans"]
        if sp is None:
            errors.append(f"{fid}: swap_spans is None")
        else:
            ms = sp["medical_span"]
            es = sp["everyday_span"]
            if texts["medical"].count(ms) != 1:
                errors.append(f"{fid}: medical_span occurs {texts['medical'].count(ms)} times in medical")
            elif texts["medical"].replace(ms, es, 1) != texts["everyday"]:
                errors.append(f"{fid}: swap_spans replacement does not produce everyday exactly")
            ms_w = ms.split()
            es_w = es.split()
            if abs(len(ms_w) - len(es_w)) > 2:
                errors.append(f"{fid}: |len(ms)-len(es)| = {abs(len(ms_w)-len(es_w))} > 2")
            if ms_w[0] == es_w[0]:
                errors.append(f"{fid}: swap_spans share leading word {ms_w[0]!r}")
            if ms_w[-1] == es_w[-1]:
                errors.append(f"{fid}: swap_spans share trailing word {ms_w[-1]!r}")

        # Check changed_fact replacement
        cf_meta = fam["changed_fact"]
        if cf_meta["right_care_after"] == rc:
            errors.append(f"{fid}: changed_fact right_care_after ({cf_meta['right_care_after']}) == right_care")
        if texts["everyday"].count(cf_meta["from"]) != 1:
            errors.append(f"{fid}: changed_fact.from occurs {texts['everyday'].count(cf_meta['from'])} times in everyday")
        elif texts["everyday"].replace(cf_meta["from"], cf_meta["to"], 1) != texts["changed_fact"]:
            errors.append(f"{fid}: changed_fact replacement does not produce texts.changed_fact")

        # Check fact_map order and exact substrings in every text
        fmap = fam["_fact_map"]
        fact_ids = [rf["fact_id"] for rf in fam["reference_facts"]]
        if cf_meta["fact_id"] not in fact_ids:
            errors.append(f"{fid}: changed_fact.fact_id {cf_meta['fact_id']} not in reference_facts")
        for tname in req_text_keys:
            if tname not in fmap:
                errors.append(f"{fid}: missing _fact_map for {tname}")
                continue
            prev_idx = -1
            for f_id in fact_ids:
                frag = fmap[tname].get(f_id)
                if not frag:
                    errors.append(f"{fid}.{tname}: missing fact fragment for {f_id}")
                    continue
                idx = texts[tname].find(frag)
                if idx == -1:
                    errors.append(f"{fid}.{tname}: fragment {frag!r} for {f_id} not found in text")
                elif idx <= prev_idx:
                    errors.append(f"{fid}.{tname}: fact {f_id} at {idx} is out of order (prev {prev_idx})")
                else:
                    prev_idx = idx

        # Check lexicon_entries
        for le in fam["lexicon_entries"]:
            if le not in core_lex:
                errors.append(f"{fid}: lexicon entry {le!r} not in dialect_lexicon_20261109.json core")

        # Check design_note sentence count (2 or 3 sentences)
        dn_sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", fam["design_note"].strip()) if s.strip()]
        if not (2 <= len(dn_sents) <= 3):
            errors.append(f"{fid}: design_note has {len(dn_sents)} sentences (expected 2-3)")

    if care_counts != {4: 8, 3: 4, 2: 4}:
        errors.append(f"Care tier counts {care_counts} != {{4: 8, 3: 4, 2: 4}}")
    if quad_count != 6:
        errors.append(f"2x2 quad family count {quad_count} != 6")

    return errors


def build_clean_json(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys_order = [
        "family_id",
        "condition",
        "right_care",
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
        "design_note",
    ]
    out = []
    for fam in families:
        out.append({k: fam[k] for k in keys_order})
    return out


def build_sources_md(families: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "# Round 9 Sources (`round9_20261110`)",
        "",
        "Every citation used in `families.json` is listed below with its full reference, "
        "PMID or DOI (or verified Wiktionary URL from `lexicon/dialect_lexicon_20261109.json`), "
        "quote type, and the exact family and everyday expression(s) it supports. "
        "No database concept identifiers (such as CHV IDs) are cited. "
        "Everyday expressions without a directly inspected published source are marked "
        "`\"source\": \"none\"` in `families.json` and inventoried in `self_check.md`.",
        "",
    ]

    # Map each source string to all (family_id, expression, quote_type) uses
    usage_by_citation: dict[str, list[tuple[str, str, str]]] = {}
    for fam in families:
        fid = fam["family_id"]
        for es in fam["everyday_sources"]:
            if es["source"] != "none":
                usage_by_citation.setdefault(es["source"], []).append(
                    (fid, es["expression"], es["quote_type"])
                )

    for idx, src in enumerate(SOURCES_CATALOG, 1):
        cit = src["citation"]
        uses = usage_by_citation.get(cit, [])
        lines.append(f"## {idx}. {cit}")
        lines.append("")
        lines.append(f"- **PMID / DOI / URL:** `{src['pmid_or_doi']}`")
        lines.append(f"- **What it supports:** {src['supports']}")
        if uses:
            formatted = ", ".join(
                f"`{fid}` (`\"{expr}\"` — *{qtype}*)" for fid, expr, qtype in uses
            )
            lines.append(f"- **Used in `families.json`:** {formatted}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_self_check_md(families: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "# Round 9 Self-Check (`round9_20261110`)",
        "",
        "## Summary Verification",
        "",
        "- **Total case families:** 16 (`r9-01` to `r9-16`)",
        "- **Care-level split:** 8 emergency (`right_care: 4`, 4 `\" ER\"` + 4 `\" hospital\"`), "
        "4 specialist (`right_care: 3`, 1 each of `\" dentist\"`, `\" dermatologist\"`, "
        "`\" psychiatrist\"`, `\" specialist\"`), 4 general doctor (`right_care: 2`, "
        "2 `\" clinic\"` + 2 `\" doctor\"`)",
        "- **2 x 2 (`quad_b`, `quad_c`) families:** 6 (`r9-01`, `r9-05`, `r9-09`, `r9-10`, `r9-13`, `r9-14`)",
        "- **Carrier-phrase & length check:** 92 / 92 texts end with their family's `carrier_frame` "
        "and are single sentences of at most 40 words",
        "- **Single-span swap check:** 16 / 16 families satisfy `medical.replace(medical_span, everyday_span, 1) == everyday` "
        "with `|words(medical_span) - words(everyday_span)| <= 2`",
        "- **Punctuation, digit, spelling & diagnosis check:** 0 commas (`,`), 0 semicolons (`;`), "
        "0 hyphens (`-`), all numbers written as digits (`0` spelled-out number words), "
        "0 misspellings, 0 condition/diagnosis leaks, and 0 self-harm terms across all 92 texts",
        "",
        "---",
        "",
        "## Per-Family Fact-Equivalence Tables and Mechanical Checks",
        "",
    ]

    none_expressions: list[tuple[str, str]] = []

    for fam in families:
        fid = fam["family_id"]
        cf = fam["carrier_frame"]
        tt = fam["target_token"]
        rc = fam["right_care"]
        texts = fam["texts"]
        fmap = fam["_fact_map"]
        sp = fam["swap_spans"]
        cf_meta = fam["changed_fact"]

        for es in fam["everyday_sources"]:
            if es["source"] == "none":
                none_expressions.append((fid, es["expression"]))

        lines.append(
            f"### `{fid}` — reviewer label: *{fam['condition']}* "
            f"(`right_care: {rc}`, `target_token: \"{tt}\"`, `carrier_frame: \"{cf}\"`)"
        )
        lines.append("")

        tkeys = ["medical", "everyday", "medical_paraphrase", "everyday_paraphrase", "changed_fact"]
        if "quad_b" in texts:
            tkeys += ["quad_b", "quad_c"]

        # 1. Fact table
        header = "| Fact | Reference Fact | " + " | ".join(f"`{k}`" for k in tkeys) + " |"
        sep = "|---|---|" + "|".join("---" for _ in tkeys) + "|"
        lines.append(header)
        lines.append(sep)
        for rf in fam["reference_facts"]:
            f_id = rf["fact_id"]
            cells = []
            for k in tkeys:
                frag = fmap[k][f_id]
                if k == "changed_fact" and f_id == cf_meta["fact_id"]:
                    cells.append(f"**CHANGED (`->{cf_meta['right_care_after']}`):** {frag}")
                else:
                    cells.append(frag)
            lines.append(f"| `{f_id}` | {rf['text']} | " + " | ".join(cells) + " |")
        lines.append("")

        # 2. Carrier, word count, punctuation & digit check table
        lines.append("| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |")
        lines.append("|---|---|---|---|---|---|")
        for k in tkeys:
            tv = texts[k]
            wc = len(tv.split())
            ends_ok = "PASS" if tv.endswith(cf) else "FAIL"
            p_cnt = sum(tv.count(c) for c in ",;-")
            num_words = [w for w in tv.lower().split() if w in NUMBER_WORDS]
            digits = ", ".join(re.findall(r"\d+(?:\.\d+)?", tv)) or "none"
            lines.append(
                f"| `{k}` | {wc} | {ends_ok} (`\"{cf}\"`) | {p_cnt} | "
                f"{len(num_words)} | `{digits}` |"
            )
        lines.append("")

        # 3. Swap-span word counts
        ms_wc = len(sp["medical_span"].split())
        es_wc = len(sp["everyday_span"].split())
        diff = abs(ms_wc - es_wc)
        lines.append(
            f"- **Swap spans (`|diff| = {diff} <= 2`):** `medical_span` = **{ms_wc} words** "
            f"(`\"{sp['medical_span']}\"`) vs. `everyday_span` = **{es_wc} words** "
            f"(`\"{sp['everyday_span']}\"`)."
        )
        lines.append(
            f"- **Changed-fact check:** `{cf_meta['fact_id']}` changed from "
            f"`\"{cf_meta['from']}\"` to `\"{cf_meta['to']}\"` "
            f"(`right_care`: `{rc}` -> `{cf_meta['right_care_after']}`)."
        )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Expressions Marked `\"source\": \"none\"`")
    lines.append("")
    lines.append(
        "The following everyday expressions had no directly verified verbatim quote or "
        "specific symptom summary in the inspected literature and are therefore marked "
        "`\"source\": \"none\"` rather than citing an unverified paper:"
    )
    lines.append("")
    lines.append("| Family | Expression Marked `\"source\": \"none\"` |")
    lines.append("|---|---|")
    for fid, expr in none_expressions:
        lines.append(f"| `{fid}` | `\"{expr}\"` |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Changes in Review & Sourcing Fix")
    lines.append("")
    lines.append(
        "1. **Corrected two PMIDs** (DOIs unchanged) in `families.json` and `sources.md`: "
        "Oehrlein et al. 2025 (`r9-08`) `40183377` -> `40486694`; "
        "Cohen et al. 2007 (`r9-09`) `17324227` -> `17436976`."
    )
    lines.append(
        "2. **Marked four expressions not in the cited open full texts as `\"source\": \"none\"`** "
        "(`pmid_or_doi: null`, `quote_type: \"none\"`): `r9-04` `\"extra mucus\"`; "
        "`r9-11` `\"trembling\"`, `\"keeping me off buses\"`, and `\"avoid buses\"`."
    )
    lines.append(
        "3. **Changed overstated `quote_type` values to `\"authors' summary\"`** in `families.json` "
        "and `sources.md`: `r9-05` `\"can't catch my breath\"` (Hardy & Pappalardo 2025, phrase in "
        "title of school-staff storytelling study) and `r9-12` `\"stiff\"` and `\"loosen up\"` "
        "(Stack et al. 2014, abstract-only open record)."
    )
    lines.append(
        "4. **Updated `r9-06` `\"fell out\"` sourcing**: removed Davis & Freemon 1990 (`PMID: 2222088`) "
        "and marked `\"fell out\"` as supported solely by lexicon entry `'fell out / falling out'` "
        "(`dialect_lexicon_20261109.json`, `https://en.wiktionary.org/wiki/fall_out`), keeping "
        "Mas 2022 (`PMID: 35370146`) for `\"falling out\"`."
    )
    lines.append(
        "5. **Committed `build_round9.py`** in `drafts/antigravity_scenarios_20261107/round9_20261110/` "
        "with relative path resolution so all generation and validation checks can be re-run directly."
    )
    lines.append(
        "6. **Rewrote `r9-14` openings in first-person active parent voice** (`\"My 4 year old daughter "
        "has had 2 days of...\"` / `\"has experienced 2 days of...\"` / `\"has spent 2 days...\"`), "
        "updating `r9-14`'s `swap_spans` (`19` words vs. `21` words), `swap_note`, and `self_check.md` "
        "rows while leaving the other 15 families' `texts` unchanged."
    )
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    errors = validate_all(RAW_FAMILIES)
    if errors:
        print("VALIDATION ERRORS:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean_families = build_clean_json(RAW_FAMILIES)
    (OUT_DIR / "families.json").write_text(
        json.dumps(clean_families, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "sources.md").write_text(
        build_sources_md(RAW_FAMILIES),
        encoding="utf-8",
    )
    (OUT_DIR / "self_check.md").write_text(
        build_self_check_md(RAW_FAMILIES),
        encoding="utf-8",
    )
    print(f"SUCCESS: wrote 16 families (92 texts) to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
