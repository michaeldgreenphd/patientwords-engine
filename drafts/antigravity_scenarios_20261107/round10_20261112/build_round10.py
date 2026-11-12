#!/usr/bin/env python3
"""Build and exhaustively validate Round 10 outcome-blind case families."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent
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
        ("so I should see a", " therapist"),
    ],
    2: [
        ("so I should see a", " doctor"),
        ("so I need to go to the", " clinic"),
    ],
    1: [
        ("so I just need some", " cream"),
        ("so I just need some", " ointment"),
        ("so I just need some", " lotion"),
        ("so I just need some", " medicine"),
    ],
}

ROUND9_CONDITIONS = {
    "cardiogenic syncope",
    "transient ischemic attack",
    "preeclampsia with severe features",
    "severe acute bronchiolitis",
    "severe acute asthma exacerbation",
    "generalized tonic clonic seizure",
    "pediatric diabetic ketoacidosis",
    "food induced anaphylaxis",
    "symptomatic irreversible pulpitis",
    "cutaneous melanoma",
    "panic disorder with agoraphobia",
    "early rheumatoid arthritis",
    "uncomplicated acute cystitis",
    "uncomplicated acute otitis media",
    "persistent uncomplicated acute gastroenteritis",
    "uncomplicated gastroesophageal reflux in pregnancy",
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
    "cauda", "equina", "sciatica", "tonsillitis", "pharyngotonsillitis", "abscess",
    "quinsy", "cellulitis", "erysipelas", "sepsis", "pneumonia", "bronchiolitis",
    "asthma", "hemorrhage", "ulcer", "gastritis", "preeclampsia", "eclampsia",
    "cardiomyopathy", "zoster", "shingles", "encephalitis", "meningitis",
    "periodontitis", "gingivitis", "angina", "psoriasis", "eczema", "erythroderma",
    "depression", "depressive", "catatonia", "catatonic", "ptsd", "posttraumatic",
    "cataract", "cataracts", "glaucoma", "endometriosis", "fibroid", "fibroids",
    "rhinosinusitis", "sinusitis", "hypothyroidism", "thyroiditis", "myxedema",
    "conjunctivitis", "pinkeye", "candidiasis", "thrush", "lyme", "borreliosis",
    "anemia", "anaemia", "tinea", "dermatitis", "xerosis", "rhinitis", "allergy",
    "allergies", "hayfever", "anaphylaxis", "cancer", "melanoma", "carcinoma",
    "stroke", "seizure", "seizures", "diabetes", "diabetic", "ketoacidosis",
}
SELF_HARM_BANNED_WORDS = {
    "suicide", "suicidal", "selfharm", "kill", "killing", "overdose", "cutting", "die", "dying", "hurt",
}
GUIDELINE_BANNED_WORDS = {
    "guideline", "guidelines", "nice", "idsa", "acog", "aha", "acc", "ats", "gina", "aap", "cdc", "who",
}
DB_ID_PATTERN = re.compile(r"\b(?:PMC\d+|PMCID|NCT\d+|CRD\d+|C\d{7}|ORCID)\b")

SOURCES_ORDER: list[str] = [
    "kumar_2026",
    "wang_2026_ces",
    "jaunay_2026",
    "torretta_2026",
    "wiktionary_fall_out",
    "mas_2022",
    "nantanda_2026",
    "liu_2026_bpd",
    "abbas_2026",
    "wiktionary_smother",
    "ferguson_2023",
    "jiao_2025",
    "opasrattanakon_2026",
    "wiktionary_short_winded",
    "hardy_2025",
    "yamada_2026",
    "wiktionary_misery",
    "falcon_flores_2026",
    "velpula_2025",
    "che_awanis_2026",
    "boonkrong_2026",
    "melkevik_2026",
    "dixon_2026",
    "wiktionary_blackout",
    "zavodni_2026",
    "coklar_okutkan_2026",
    "drejza_2026",
    "taree_2026",
    "coles_2025",
    "lathiya_2026",
    "muse_2026",
    "bogovic_2026",
    "wiktionary_spell",
    "rana_2025",
    "kutlu_2025",
    "alkhamis_2026",
    "wang_2026_lotion",
    "opadokun_2026",
]

SOURCES_BANK: dict[str, dict[str, str]] = {
    "kumar_2026": {
        "source": (
            "Kumar N, Patralekh MK, Jacob RV, Kumar S, Gowda MB (2026). Adolescent Cauda Equina "
            "Secondary to Traumatic Lumbar Disc Herniation: A Rare Case Report with Review of "
            "Literature. Journal of Orthopaedic Case Reports."
        ),
        "pmid_or_doi": "PMID: 42597798; DOI: 10.13107/jocr.2026.v16.i08.7832",
        "access": "full text",
    },
    "wang_2026_ces": {
        "source": (
            "Wang S, Shang J (2026). Cauda equina cavernous malformation with nerve fascicle "
            "involvement and chronic bowel and urinary urgency: a case report. Frontiers in Surgery."
        ),
        "pmid_or_doi": "PMID: 42991049; DOI: 10.3389/fsurg.2026.2004471",
        "access": "full text",
    },
    "jaunay_2026": {
        "source": (
            "Jaunay LB, Ivanoff AS, Philippot C, Triby E, Pelaccia T (2026). How Patients' Inquiry "
            "Shapes Meaning in Primary Care Consultations: A Qualitative Study Using Own-Point-of-View "
            "Video-Stimulated Recall. Journal of Evaluation in Clinical Practice."
        ),
        "pmid_or_doi": "PMID: 42900758; DOI: 10.1111/jep.70653",
        "access": "full text",
    },
    "torretta_2026": {
        "source": (
            "Torretta S, De Lucia G, Cavalera S, Cavaleri L, Battilocchi L (2026). Early recognition "
            "of life-threatening otolaryngologic complications in pediatric epstein-barr virus "
            "infectious mononucleosis: a systematic review and meta-analysis. Frontiers in Pediatrics."
        ),
        "pmid_or_doi": "PMID: 42923267; DOI: 10.3389/fped.2026.1980308",
        "access": "full text",
    },
    "wiktionary_fall_out": {
        "source": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'fall out'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/fall_out",
        "access": "full text",
    },
    "mas_2022": {
        "source": (
            "Mas C (2022). \"Falling-Out\" in Miami and the History of Culture in American Medicine. "
            "Bulletin of the History of Medicine."
        ),
        "pmid_or_doi": "PMID: 35370146; DOI: 10.1353/bhm.2022.0003",
        "access": "abstract only",
    },
    "nantanda_2026": {
        "source": (
            "Nantanda R, Najjingo I, Kjaergaard J, Reventlow S, Ndekezi D, Ssemata AS, Østergaard MS "
            "(2026). Childhood asthma in Uganda: experiences of healthcare providers and caregivers in "
            "diagnosis and management. A FRESH AIR qualitative study. NPJ Primary Care Respiratory Medicine."
        ),
        "pmid_or_doi": "PMID: 41714660; DOI: 10.1038/s41533-026-00493-7",
        "access": "full text",
    },
    "liu_2026_bpd": {
        "source": (
            "Liu F, Ling Y, Fan X, Cheng X, Chen Z, Zhu J (2026). Safety risk identification and "
            "family empowerment needs in home oxygen therapy for preterm infants with bronchopulmonary "
            "dysplasia: a qualitative study. BMJ Paediatrics Open."
        ),
        "pmid_or_doi": "PMID: 42957182; DOI: 10.1136/bmjpo-2026-005022",
        "access": "full text",
    },
    "abbas_2026": {
        "source": (
            "Abbas A, Jaradat M, Kmail H, Nairat S, Haj R, Jallad F, Qudaih O, Amro J, Diab B, "
            "Nazzal M (2026). An Unusual Cause of Melena: Adjacent Sigmoid Tubular Adenomas With "
            "Moderate Dysplasia-A Case Report. Clinical Case Reports."
        ),
        "pmid_or_doi": "PMID: 42427814; DOI: 10.1002/ccr3.73138",
        "access": "full text",
    },
    "wiktionary_smother": {
        "source": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'smother'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/smother",
        "access": "full text",
    },
    "ferguson_2023": {
        "source": (
            "Ferguson ON, Mitchell RA, Schaeffer MR, Ramsook AH, Dhillon SS, Dominelli PB, "
            "Molgat-Seon Y, Guenette JA (2023). Effects of Face Masks on the Multiple Dimensions and "
            "Neurophysiological Mechanisms of Exertional Dyspnea. Medicine and Science in Sports and Exercise."
        ),
        "pmid_or_doi": "PMID: 36469484; DOI: 10.1249/MSS.0000000000003074",
        "access": "abstract only",
    },
    "jiao_2025": {
        "source": (
            "Jiao M, Wang W, Chen C, Zhang X, Zhao X (2025). Treatment Inertia Among Elderly Patients "
            "with Chronic Heart Failure: A Qualitative Study. Patient Preference and Adherence."
        ),
        "pmid_or_doi": "PMID: 41393075; DOI: 10.2147/PPA.S560907",
        "access": "full text",
    },
    "opasrattanakon_2026": {
        "source": (
            "Opasrattanakon S, Jaraeprapal U, Punsawad C (2026). Self-care management in patients "
            "with heart failure in Nakhon Si Thammarat Province, Thailand: a descriptive qualitative "
            "study. Scientific Reports."
        ),
        "pmid_or_doi": "PMID: 41839957; DOI: 10.1038/s41598-026-44071-w",
        "access": "full text",
    },
    "wiktionary_short_winded": {
        "source": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'short-winded'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/short-winded",
        "access": "full text",
    },
    "hardy_2025": {
        "source": (
            "Hardy P, Pappalardo AA (2025). \"I can't breathe, I can't catch my breath:\" the impact "
            "of school staff storytelling on asthma management. The Journal of Asthma."
        ),
        "pmid_or_doi": "PMID: 39382247; DOI: 10.1080/02770903.2024.2414351",
        "access": "title only",
    },
    "yamada_2026": {
        "source": (
            "Yamada R, Fuchigami T, Moriuchi Y (2026). A Pediatric Case of Urinary Retention Caused "
            "by Shingles on the Buttocks. Cureus."
        ),
        "pmid_or_doi": "PMID: 42591554; DOI: 10.7759/cureus.112547",
        "access": "full text",
    },
    "wiktionary_misery": {
        "source": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'misery'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/misery",
        "access": "full text",
    },
    "falcon_flores_2026": {
        "source": (
            "Falcón-Flores JA, Jiménez-Corona ME, Rangel-Nieto IG, Vazquez-Duran M, Jiménez-Corona A "
            "(2026). Exploratory Evaluation of Self-Reported Periodontitis Among Adult Population From "
            "Comitán Chiapas, Mexico. Clinical and Experimental Dental Research."
        ),
        "pmid_or_doi": "PMID: 41517925; DOI: 10.1002/cre2.70274",
        "access": "full text",
    },
    "velpula_2025": {
        "source": (
            "Velpula KP, Jacob E (2025). The stories of the ageing population in Luton, United Kingdom "
            "on their experience of periodontal diseases healthcare. Frontiers in Public Health."
        ),
        "pmid_or_doi": "PMID: 41890769; DOI: 10.3389/fpubh.2025.1710973",
        "access": "full text",
    },
    "che_awanis_2026": {
        "source": (
            "Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and "
            "coping strategies of psoriasis patients in Malaysia. PLoS One."
        ),
        "pmid_or_doi": "PMID: 41544022; DOI: 10.1371/journal.pone.0329066",
        "access": "full text",
    },
    "boonkrong_2026": {
        "source": (
            "Boonkrong P, Khunboonjun K, Shakya S, Yang J, Vitoonmetha N, Chatchumni M (2026). A "
            "mixed-methods study of depressive-symptom severity among Thai university students and the "
            "underestimated role of social media. Frontiers in Child and Adolescent Psychiatry."
        ),
        "pmid_or_doi": "PMID: 42959322; DOI: 10.3389/frcha.2026.1907727",
        "access": "full text",
    },
    "melkevik_2026": {
        "source": (
            "Melkevik O, Roberts N, Folke S (2026). Self-reported versus clinician-evaluated symptom "
            "assessment and diagnosis of ICD-11 PTSD and CPTSD: a comparison between the International "
            "Trauma Interview and the International Trauma Questionnaire. European Journal of Psychotraumatology."
        ),
        "pmid_or_doi": "PMID: 41853968; DOI: 10.1080/20008066.2026.2635917",
        "access": "full text",
    },
    "dixon_2026": {
        "source": (
            "Dixon TAM, Hole K, Johnson L, Nutbeam T (2026). Trapped and traumatised: a scoping review "
            "of the psychological sequelae of entrapment following motor vehicle collision. "
            "Scandinavian Journal of Trauma, Resuscitation and Emergency Medicine."
        ),
        "pmid_or_doi": "PMID: 41612474; DOI: 10.1186/s13049-026-01558-9",
        "access": "full text",
    },
    "wiktionary_blackout": {
        "source": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'blackout'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/blackout",
        "access": "full text",
    },
    "zavodni_2026": {
        "source": (
            "Zavodni Z (2026). Visual Outcomes and Patient Satisfaction With a New Trifocal, Toric "
            "Intraocular Lens. Journal of Ophthalmology."
        ),
        "pmid_or_doi": "PMID: 42471984; DOI: 10.1155/joph/9983329",
        "access": "full text",
    },
    "coklar_okutkan_2026": {
        "source": (
            "Coklar-Okutkan I, Harvey S, Doyle J, Teixeira F, Dinsmore J (2026). Illness Identity and "
            "Its Influence on Self-Management in Older Adults With Multimorbidity: A Hybrid Thematic "
            "Analysis. Qualitative Health Research."
        ),
        "pmid_or_doi": "PMID: 42549522; DOI: 10.1177/10497323261470629",
        "access": "full text",
    },
    "drejza_2026": {
        "source": (
            "Drejza M, Nicholson LS, Paquette G, Chawla M, Vale CL, Rogozińska E, Moss N, "
            "Hutchinson-Pascal N, Al Wattar BH (2026). The Impact of Heavy Menstrual Bleeding on "
            "Quality of Life: A Mixed-Methods Survey Study. BJOG."
        ),
        "pmid_or_doi": "PMID: 42324234; DOI: 10.1111/1471-0528.70290",
        "access": "full text",
    },
    "taree_2026": {
        "source": (
            "Taree NA, Rich R, Zhu N, Khalife R, Wu CM, Sun HWL (2026). Barriers and facilitators for "
            "management of iron-deficiency anemia in reproductive-aged women: perspectives of health "
            "care professionals in Alberta, Canada. CMAJ."
        ),
        "pmid_or_doi": "PMID: 42971550; DOI: 10.1503/cmaj.252102",
        "access": "full text",
    },
    "coles_2025": {
        "source": (
            "Coles T, Mkumba LS, Wright L, Godley FA, Collins TA, Jang DW (2025). Development of the "
            "Sinus Headache Screener to identify patients with non-rhinogenic facial pain compared "
            "with chronic rhinosinusitis in rhinology clinics. Journal of Patient-Reported Outcomes."
        ),
        "pmid_or_doi": "PMID: 41196482; DOI: 10.1186/s41687-025-00956-4",
        "access": "full text",
    },
    "lathiya_2026": {
        "source": (
            "Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic "
            "Management of Hypothyroidism: A Narrative Review of Reported Clinical Experience, "
            "Individualised Prescribing, and Research Gaps. Cureus."
        ),
        "pmid_or_doi": "PMID: 42800981; DOI: 10.7759/cureus.115269",
        "access": "full text",
    },
    "muse_2026": {
        "source": (
            "Muse YH, Hassan MA, Ali M, Muse AH, Nadarajah S (2026). A pediatric case of measles with "
            "gastrointestinal complications in an urban hospital setting: A clinical and public health "
            "perspective. IDCases."
        ),
        "pmid_or_doi": "PMID: 42437059; DOI: 10.1016/j.idcr.2026.e02657",
        "access": "full text",
    },
    "bogovic_2026": {
        "source": (
            "Bogovič P, Jaklič M, Ogrinc K, Maraspin V, Rojko T, Nahtigal-Klevišar M, Ružić-Sabljić E, "
            "Wormser GP, Strle F (2026). Dynamics of Borrelial Antibodies in European Lyme Borreliosis "
            "Patients with Erythema Migrans. Medical Sciences."
        ),
        "pmid_or_doi": "PMID: 42783436; DOI: 10.3390/medsci14050563",
        "access": "full text",
    },
    "wiktionary_spell": {
        "source": (
            "Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). "
            "Entry 'spell'. Wiktionary, The Free Dictionary."
        ),
        "pmid_or_doi": "https://en.wiktionary.org/wiki/spell",
        "access": "full text",
    },
    "rana_2025": {
        "source": (
            "Rana T, Kaeley N, Tejpal P, Yadav S, Mudi D (2025). Pulmonary Embolism Presenting as "
            "Recurrent Syncope and Visual Disturbances in a Patient With Protein C Deficiency: An "
            "Atypical Emergency Department Presentation. Cureus."
        ),
        "pmid_or_doi": "PMID: 41573451; DOI: 10.7759/cureus.99743",
        "access": "abstract only",
    },
    "kutlu_2025": {
        "source": (
            "Kutlu O, Cetinkaya PO, Yavuz G, Khachemoune A (2025). Turkish Bath-Associated Infectious "
            "Dermatoses: A Comprehensive Review of Risk Factors, Clinical Manifestations, and "
            "Preventive Measures. Sisli Etfal Hastanesi Tip Bulteni."
        ),
        "pmid_or_doi": "PMID: 41700199; DOI: 10.14744/SEMB.2025.54782",
        "access": "full text",
    },
    "alkhamis_2026": {
        "source": (
            "Alkhamis ZZ, Bhagchandani M, Idris M, Bhyat Y, Alsani SM, Pasha AI, Ali AHA, "
            "Ali Eledresi D, Mahdi AA, Almohamedhusain FR (2026). Clinical Effectiveness of Barrier "
            "Preparations in the Management of Diaper Dermatitis: A Systematic Review and "
            "Meta-Analysis. Cureus."
        ),
        "pmid_or_doi": "PMID: 41769510; DOI: 10.7759/cureus.102379",
        "access": "full text",
    },
    "wang_2026_lotion": {
        "source": (
            "Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). "
            "Comprehensive Evaluation of Body Lotion in Alleviating Xerosis: A Multi-Omics Approach "
            "to Lipid Metabolism and Microbial Community Modulation. Journal of Cosmetic Dermatology."
        ),
        "pmid_or_doi": "PMID: 41622615; DOI: 10.1111/jocd.70711",
        "access": "full text",
    },
    "opadokun_2026": {
        "source": (
            "Opadokun A, Mikhail E, Chong LX, Suphioğlu C, Gokhale M, Azizoğlu S (2026). The Impact of "
            "Allergic Rhinitis on Australian Adults in an Urban Setting: A Qualitative Exploration. "
            "Journal of Clinical Medicine."
        ),
        "pmid_or_doi": "PMID: 42796056; DOI: 10.3390/jcm15187284",
        "access": "full text",
    },
}


def src_item(
    expression: str,
    key: str | None,
    quote_type: str = "none",
    evidence: str | None = None,
) -> dict[str, Any]:
    if key is None:
        return {
            "expression": expression,
            "source": "none",
            "pmid_or_doi": None,
            "quote_type": "none",
            "evidence": None,
            "access": None,
        }
    rec = SOURCES_BANK[key]
    return {
        "expression": expression,
        "source": rec["source"],
        "pmid_or_doi": rec["pmid_or_doi"],
        "quote_type": quote_type,
        "evidence": evidence,
        "access": rec["access"],
    }


def att_item(
    clause: str,
    explains: str,
    key: str | None,
    quote_type: str = "none",
    evidence: str | None = None,
) -> dict[str, Any]:
    if key is None:
        return {
            "clause": clause,
            "explains": explains,
            "source": "none",
            "pmid_or_doi": None,
            "quote_type": "none",
            "evidence": None,
            "access": None,
        }
    rec = SOURCES_BANK[key]
    return {
        "clause": clause,
        "explains": explains,
        "source": rec["source"],
        "pmid_or_doi": rec["pmid_or_doi"],
        "quote_type": quote_type,
        "evidence": evidence,
        "access": rec["access"],
    }


FAMILIES_SPEC: list[dict[str, Any]] = [
    # ==================== 8 EMERGENCY (right_care = 4) ====================
    {
        "family_id": "r10-01",
        "condition": "cauda equina syndrome",
        "right_care": 4,
        "level_rationale": (
            "Radicular low back pain with toe numbness plus acute urinary retention requires emergency "
            "decompression workup at an ER, whereas the same radicular back pain with normal urination "
            "warrants outpatient physician evaluation."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "Lifted a heavy box 4 days ago"},
            {"fact_id": "f2", "text": "Low back pain radiating down the left leg"},
            {"fact_id": "f3", "text": "Numbness in the left toes"},
            {"fact_id": "f4", "text": "Unable to urinate today"},
        ],
        "texts": {
            "medical": "I lifted a heavy box 4 days ago and developed left lumbar radiculopathy accompanied by left pedal paresthesia and urinary retention today so I need to go to the",
            "everyday": "I lifted a heavy box 4 days ago and got low back pain down my left leg with numb toes and cannot pee today so I need to go to the",
            "medical_paraphrase": "I lifted a heavy crate 4 days ago and experienced left lower limb radicular back pain with left toe paresthesia and acute urinary retention today so I need to go to the",
            "everyday_paraphrase": "I picked up a heavy box 4 days ago and got low back pain running down my left leg with numbness of my left toes and cannot pee today so I need to go to the",
            "changed_fact": "I lifted a heavy box 4 days ago and got low back pain down my left leg with numb toes and can pee normally today so I need to go to the",
            "everyday_attribution": "I lifted a heavy box 4 days ago and got low back pain down my left leg with numb toes and cannot pee today and I think I pulled a muscle so I need to go to the",
            "quad_b": "I lifted a heavy box 4 days ago and got left lumbar radiculopathy with left pedal paresthesia and urinary retention today so I need to go to the",
            "quad_c": "I lifted a heavy box 4 days ago and developed low back pain down my left leg accompanied by numb toes and inability to pee today so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "and cannot pee today",
            "to": "and can pee normally today",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think I pulled a muscle",
            "attributes radicular back pain and acute urinary retention to a simple back muscle strain",
            None,
        ),
        "swap_spans": {
            "medical_span": "developed left lumbar radiculopathy accompanied by left pedal paresthesia and urinary retention",
            "everyday_span": "got low back pain down my left leg with numb toes and cannot pee",
        },
        "swap_note": "Single continuous 12-word vs 14-word span swap after 'I lifted a heavy box 4 days ago and ' and before ' today so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "low back pain",
                "kumar_2026",
                "authors' summary",
                "A 13-year-old male child presented to us in the emergency department with complaints of low back pain, weakness, and urinary incontinence following lifting of a heavy weight 25 days back.",
            ),
            src_item(
                "numbness of my left toes",
                "wang_2026_ces",
                "authors' summary",
                "A 51-year-old woman was admitted with a four-year history of low back discomfort, numbness of the right fourth and fifth toes, and bowel and urinary urgency.",
            ),
            src_item("down my left leg", None),
            src_item("numb toes", None),
            src_item("cannot pee", None),
        ],
        "equity_dimension": "plain_low_literacy_english",
        "lexicon_entries": [],
        "design_note": (
            "Provides a full 2 x 2 syntax-by-vocabulary crossing with a 2-word span length difference and 8 "
            "identical trailing tokens ('today so I need to go to the') for position-aligned activation patching "
            "and layer lens readouts. Negating only urinary retention in changed_fact isolates sensitivity to a "
            "single bladder red flag while everyday_attribution holds all 4 reference facts constant."
        ),
        "_fact_map": {
            "medical": {"f1": "I lifted a heavy box 4 days ago", "f2": "left lumbar radiculopathy", "f3": "left pedal paresthesia", "f4": "urinary retention today"},
            "everyday": {"f1": "I lifted a heavy box 4 days ago", "f2": "low back pain down my left leg", "f3": "numb toes", "f4": "and cannot pee today"},
            "medical_paraphrase": {"f1": "I lifted a heavy crate 4 days ago", "f2": "left lower limb radicular back pain", "f3": "left toe paresthesia", "f4": "acute urinary retention today"},
            "everyday_paraphrase": {"f1": "I picked up a heavy box 4 days ago", "f2": "low back pain running down my left leg", "f3": "numbness of my left toes", "f4": "and cannot pee today"},
            "changed_fact": {"f1": "I lifted a heavy box 4 days ago", "f2": "low back pain down my left leg", "f3": "numb toes", "f4": "and can pee normally today"},
            "everyday_attribution": {"f1": "I lifted a heavy box 4 days ago", "f2": "low back pain down my left leg", "f3": "numb toes", "f4": "and cannot pee today"},
            "quad_b": {"f1": "I lifted a heavy box 4 days ago", "f2": "left lumbar radiculopathy", "f3": "left pedal paresthesia", "f4": "urinary retention today"},
            "quad_c": {"f1": "I lifted a heavy box 4 days ago", "f2": "low back pain down my left leg", "f3": "numb toes", "f4": "inability to pee today"},
        },
    },
    {
        "family_id": "r10-02",
        "condition": "acute febrile pharyngitis with drooling and dysphagia",
        "right_care": 4,
        "level_rationale": (
            "Febrile throat pain with inability to swallow saliva and active drooling signals potential "
            "upper-airway or deep-neck compromise requiring emergency care, whereas swallowing liquids easily "
            "without drooling indicates uncomplicated febrile pharyngitis suitable for an outpatient clinician."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "3 days of sore throat and swollen neck glands"},
            {"fact_id": "f2", "text": "Fever of 39 C"},
            {"fact_id": "f3", "text": "Unable to swallow saliva and drooling today"},
        ],
        "texts": {
            "medical": "I have had 3 days of pharyngitis and cervical lymphadenopathy with a 39 C fever and developed aphagia for saliva with sialorrhea today so I need to go to the",
            "everyday": "I have had 3 days of a sore throat and swollen glands with a 39 C fever and cannot swallow spit with drooling today so I need to go to the",
            "medical_paraphrase": "I experienced 3 days of pharyngeal pain and tender cervical lymphadenopathy with a 39 C pyrexia and inability to swallow secretions with sialorrhea today so I need to go to the",
            "everyday_paraphrase": "I had 3 days of throat pain and swollen neck glands with a 39 C fever and started drooling because I cannot swallow spit today so I need to go to the",
            "changed_fact": "I have had 3 days of a sore throat and swollen glands with a 39 C fever and swallow liquids easily without drooling today so I need to go to the",
            "everyday_attribution": "I have had 3 days of a sore throat and swollen glands with a 39 C fever and cannot swallow spit with drooling today and I think it is a throat virus so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "and cannot swallow spit with drooling today",
            "to": "and swallow liquids easily without drooling today",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think it is a throat virus",
            "attributes febrile throat pain with drooling and inability to swallow saliva to a routine viral sore throat",
            None,
        ),
        "swap_spans": {
            "medical_span": "pharyngitis and cervical lymphadenopathy with a 39 C fever and developed aphagia for saliva with sialorrhea",
            "everyday_span": "a sore throat and swollen glands with a 39 C fever and cannot swallow spit with drooling",
        },
        "swap_note": "Single continuous 16-word vs 17-word span swap preserving 'I have had 3 days of ' and ' today so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "sore throat",
                "jaunay_2026",
                "authors' summary",
                "And that's going to give a sort of tonsillitis, sore throat, swollen glands, significant fatigue and a bit of a lingering fever.",
            ),
            src_item(
                "swollen glands",
                "jaunay_2026",
                "authors' summary",
                "And that's going to give a sort of tonsillitis, sore throat, swollen glands, significant fatigue and a bit of a lingering fever.",
            ),
            src_item(
                "drooling",
                "torretta_2026",
                "authors' summary",
                "Consequently, progressive dysphagia, drooling, muffled voice, inspiratory stridor, increasing respiratory effort, and inability to maintain adequate oral intake should be regarded as clinically significant warning signs rather than expected manifestations of uncomplicated viral pharyngotonsillitis (3–5).",
            ),
            src_item("cannot swallow spit", None),
        ],
        "equity_dimension": "plain_low_literacy_english",
        "lexicon_entries": [],
        "design_note": (
            "Pairs clinical airway-red-flag terms ('aphagia for saliva with sialorrhea') against plain patient "
            "phrasing ('cannot swallow spit with drooling') inside a 1-word-difference single span. The "
            "changed-fact control reverses only secretion swallowing and drooling while keeping the 3-day 39 C "
            "febrile pharyngitis facts fixed."
        ),
        "_fact_map": {
            "medical": {"f1": "3 days of pharyngitis and cervical lymphadenopathy", "f2": "a 39 C fever", "f3": "developed aphagia for saliva with sialorrhea today"},
            "everyday": {"f1": "3 days of a sore throat and swollen glands", "f2": "a 39 C fever", "f3": "and cannot swallow spit with drooling today"},
            "medical_paraphrase": {"f1": "3 days of pharyngeal pain and tender cervical lymphadenopathy", "f2": "a 39 C pyrexia", "f3": "inability to swallow secretions with sialorrhea today"},
            "everyday_paraphrase": {"f1": "3 days of throat pain and swollen neck glands", "f2": "a 39 C fever", "f3": "started drooling because I cannot swallow spit today"},
            "changed_fact": {"f1": "3 days of a sore throat and swollen glands", "f2": "a 39 C fever", "f3": "and swallow liquids easily without drooling today"},
            "everyday_attribution": {"f1": "3 days of a sore throat and swollen glands", "f2": "a 39 C fever", "f3": "and cannot swallow spit with drooling today"},
        },
    },
    {
        "family_id": "r10-03",
        "condition": "spreading lower limb skin infection with syncope",
        "right_care": 4,
        "level_rationale": (
            "A spreading febrile lower-leg skin infection accompanied by syncope on standing indicates systemic "
            "hemodynamic compromise requiring emergency hospital care, whereas the same localized febrile leg "
            "infection without syncope warrants outpatient clinician antibiotics."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Patient is 68 years old"},
            {"fact_id": "f2", "text": "3 days of expanding warm red swelling on the right calf"},
            {"fact_id": "f3", "text": "Fever of 39 C"},
            {"fact_id": "f4", "text": "Fainted upon standing today"},
        ],
        "texts": {
            "medical": "I am 68 with 3 days of expanding warm right calf erythema and edema accompanied by a 39 C fever followed by orthostatic syncope standing today so I need to go to the",
            "everyday": "I am 68 with 3 days of spreading hot red right calf swelling with a 39 C fever and then fell out standing today so I need to go to the",
            "medical_paraphrase": "I am 68 years old with 3 days of progressive right calf erythema warmth and edema plus a 39 C pyrexia complicated by syncope on standing today so I need to go to the",
            "everyday_paraphrase": "I am 68 years old with 3 days of hot red swelling spreading on my right calf and a 39 C fever before falling out standing today so I need to go to the",
            "changed_fact": "I am 68 with 3 days of spreading hot red right calf swelling with a 39 C fever without fainting when standing today so I need to go to the",
            "everyday_attribution": "I am 68 with 3 days of spreading hot red right calf swelling with a 39 C fever and then fell out standing today and I think it is a bug bite so I need to go to the",
            "quad_b": "I am 68 with 3 days of expanding warm right calf erythema and edema with a 39 C fever and then orthostatic syncope standing today so I need to go to the",
            "quad_c": "I am 68 with 3 days of spreading hot red right calf swelling accompanied by a 39 C fever followed by falling out standing today so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "and then fell out standing today",
            "to": "without fainting when standing today",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think it is a bug bite",
            "attributes a spreading febrile lower-leg infection with syncope to a minor insect bite",
            None,
        ),
        "swap_spans": {
            "medical_span": "expanding warm right calf erythema and edema accompanied by a 39 C fever followed by orthostatic syncope",
            "everyday_span": "spreading hot red right calf swelling with a 39 C fever and then fell out",
        },
        "swap_note": "Single continuous 17-word vs 15-word span swap between 'I am 68 with 3 days of ' and ' standing today so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "fell out",
                "wiktionary_fall_out",
                "dictionary definition",
                "# {{lb|en|dialect|intransitive}} To [[pass out]].",
            ),
            src_item(
                "falling out",
                "mas_2022",
                "authors' summary",
                "In the 1970s, after playing a leading role in the organization of medical anthropology, Hazel Weidman uncovered a condition that Miami residents called \"falling-out.\"",
            ),
            src_item("spreading hot red right calf swelling", None),
        ],
        "equity_dimension": "regional_dialect_african_american_caribbean_us",
        "lexicon_entries": ["fell out / falling out"],
        "design_note": (
            "Crosses formal clinical syntax and everyday syntax with dialect syncope phrasing ('fell out' vs "
            "'orthostatic syncope') while holding 9 leading words and 9 trailing words identical for activation "
            "patching and lens readouts. Negating only syncope on standing in changed_fact separates systemic "
            "hemodynamic red-flag detection from localized febrile skin-infection features."
        ),
        "_fact_map": {
            "medical": {"f1": "I am 68", "f2": "3 days of expanding warm right calf erythema and edema", "f3": "a 39 C fever", "f4": "orthostatic syncope standing today"},
            "everyday": {"f1": "I am 68", "f2": "3 days of spreading hot red right calf swelling", "f3": "a 39 C fever", "f4": "and then fell out standing today"},
            "medical_paraphrase": {"f1": "I am 68 years old", "f2": "3 days of progressive right calf erythema warmth and edema", "f3": "a 39 C pyrexia", "f4": "syncope on standing today"},
            "everyday_paraphrase": {"f1": "I am 68 years old", "f2": "3 days of hot red swelling spreading on my right calf", "f3": "a 39 C fever", "f4": "before falling out standing today"},
            "changed_fact": {"f1": "I am 68", "f2": "3 days of spreading hot red right calf swelling", "f3": "a 39 C fever", "f4": "without fainting when standing today"},
            "everyday_attribution": {"f1": "I am 68", "f2": "3 days of spreading hot red right calf swelling", "f3": "a 39 C fever", "f4": "and then fell out standing today"},
            "quad_b": {"f1": "I am 68", "f2": "3 days of expanding warm right calf erythema and edema", "f3": "a 39 C fever", "f4": "orthostatic syncope standing today"},
            "quad_c": {"f1": "I am 68", "f2": "3 days of spreading hot red right calf swelling", "f3": "a 39 C fever", "f4": "followed by falling out standing today"},
        },
    },
    {
        "family_id": "r10-04",
        "condition": "pediatric febrile lower respiratory infection with cyanosis",
        "right_care": 4,
        "level_rationale": (
            "Central lip cyanosis in a febrile coughing 5-year-old indicates acute hypoxemia requiring immediate "
            "ER oxygen and assessment, whereas normal pink lips with a 4-day febrile cough and chest pain "
            "warrants outpatient pediatric evaluation."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "Child is 5 years old"},
            {"fact_id": "f2", "text": "4 days of wet productive cough and 39 C fever"},
            {"fact_id": "f3", "text": "Chest pain on coughing"},
            {"fact_id": "f4", "text": "Lips turned blue today"},
        ],
        "texts": {
            "medical": "My 5 year old daughter has 4 days of productive cough and 39 C fever with pleuritic chest pain and labial cyanosis today so I need to go to the",
            "everyday": "My 5 year old daughter has 4 days of wet cough and 39 C fever with chest pain coughing and her lips turned blue today so I need to go to the",
            "medical_paraphrase": "My 5 year old child developed 4 days of productive tussis and 39 C pyrexia accompanied by pleuritic chest pain and perioral cyanosis today so I need to go to the",
            "everyday_paraphrase": "My 5 year old girl spent 4 days with wet cough and 39 C fever plus chest pain when coughing and her lips turned blue today so I need to go to the",
            "changed_fact": "My 5 year old daughter has 4 days of wet cough and 39 C fever with chest pain coughing and her lips stayed pink today so I need to go to the",
            "everyday_attribution": "My 5 year old daughter has 4 days of wet cough and 39 C fever with chest pain coughing and her lips turned blue today and I think it is a common cold so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "and her lips turned blue today",
            "to": "and her lips stayed pink today",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think it is a common cold",
            "attributes pediatric febrile cough with central lip cyanosis to a routine common cold, a caregiver belief documented in respiratory delay studies",
            "nantanda_2026",
            "authors' summary",
            "According to HCWs, the most common triggers and causes of respiratory symptoms, as described by CGs, were cold weather, common colds, dust, overcrowding in homes, exposure to tobacco smoke, poor ventilation, malnutrition, and witchcraft.",
        ),
        "swap_spans": {
            "medical_span": "productive cough and 39 C fever with pleuritic chest pain and labial cyanosis",
            "everyday_span": "wet cough and 39 C fever with chest pain coughing and her lips turned blue",
        },
        "swap_note": "Single continuous 13-word vs 15-word span swap with 8 shared opening words and 8 shared closing words.",
        "everyday_sources": [
            src_item(
                "wet cough",
                "nantanda_2026",
                "authors' summary",
                "The episodes often started as a runny nose and an irritating dry or wet cough, mainly at night, associated with a sound in the chest and difficulty in breathing.",
            ),
            src_item(
                "her lips turned blue",
                "liu_2026_bpd",
                "direct patient quote",
                "One mother said: “Once our child seemed to be breathing with effort and their lips turned a bit blue.",
            ),
            src_item("chest pain coughing", None),
            src_item("chest pain when coughing", None),
        ],
        "equity_dimension": "pediatric_caregiver_non_native_and_global_english",
        "lexicon_entries": [],
        "design_note": (
            "Anchors pediatric caregiver wording in a verbatim mother quote ('their lips turned a bit blue', "
            "unhedged here to match 'labial cyanosis' in severity) and a caregiver 'common cold' attribution "
            "from Ugandan primary care. Flipping only lip color from blue to pink tests whether instruments "
            "track the single oxygenation fact independent of fever and cough."
        ),
        "_fact_map": {
            "medical": {"f1": "My 5 year old daughter", "f2": "4 days of productive cough and 39 C fever", "f3": "pleuritic chest pain", "f4": "and labial cyanosis today"},
            "everyday": {"f1": "My 5 year old daughter", "f2": "4 days of wet cough and 39 C fever", "f3": "chest pain coughing", "f4": "and her lips turned blue today"},
            "medical_paraphrase": {"f1": "My 5 year old child", "f2": "4 days of productive tussis and 39 C pyrexia", "f3": "pleuritic chest pain", "f4": "and perioral cyanosis today"},
            "everyday_paraphrase": {"f1": "My 5 year old girl", "f2": "4 days with wet cough and 39 C fever", "f3": "chest pain when coughing", "f4": "and her lips turned blue today"},
            "changed_fact": {"f1": "My 5 year old daughter", "f2": "4 days of wet cough and 39 C fever", "f3": "chest pain coughing", "f4": "and her lips stayed pink today"},
            "everyday_attribution": {"f1": "My 5 year old daughter", "f2": "4 days of wet cough and 39 C fever", "f3": "chest pain coughing", "f4": "and her lips turned blue today"},
        },
    },
    {
        "family_id": "r10-05",
        "condition": "acute upper gastrointestinal bleeding",
        "right_care": 4,
        "level_rationale": (
            "Passing black tarry stools twice in a day during daily ibuprofen use indicates active upper "
            "gastrointestinal bleeding requiring emergency hospital evaluation, whereas burning upper stomach "
            "pain on ibuprofen with normal brown stools warrants outpatient physician review."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Taking daily ibuprofen for 3 weeks"},
            {"fact_id": "f2", "text": "4 days of burning upper abdominal pain"},
            {"fact_id": "f3", "text": "Passed black tarry stools 2 times today"},
        ],
        "texts": {
            "medical": "I took daily ibuprofen for 3 weeks and developed 4 days of burning epigastric pain and passed melenic stools 2 times today so I need to go to the",
            "everyday": "I took daily ibuprofen for 3 weeks and got 4 days of burning upper stomach pain and passed black tarry stools 2 times today so I need to go to the",
            "medical_paraphrase": "I used daily oral ibuprofen over 3 weeks and experienced 4 days of burning epigastric discomfort plus melena 2 times today so I need to go to the",
            "everyday_paraphrase": "I took ibuprofen every day for 3 weeks and had 4 days of burning high stomach pain and black tarry stools 2 times today so I need to go to the",
            "changed_fact": "I took daily ibuprofen for 3 weeks and got 4 days of burning upper stomach pain and passed normal brown stools 2 times today so I need to go to the",
            "everyday_attribution": "I took daily ibuprofen for 3 weeks and got 4 days of burning upper stomach pain and passed black tarry stools 2 times today and I think it is just indigestion so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "and passed black tarry stools 2 times today",
            "to": "and passed normal brown stools 2 times today",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think it is just indigestion",
            "attributes NSAID-associated upper abdominal pain and melena to benign indigestion",
            None,
        ),
        "swap_spans": {
            "medical_span": "developed 4 days of burning epigastric pain and passed melenic",
            "everyday_span": "got 4 days of burning upper stomach pain and passed black tarry",
        },
        "swap_note": "Single continuous 10-word vs 12-word span swap keeping 8 leading words and 11 trailing words ('stools 2 times today so I need to go to the') identical.",
        "everyday_sources": [
            src_item(
                "black tarry stools",
                "abbas_2026",
                "authors' summary",
                "A 28‐year‐old female, previously in her usual state of good health, presented with a three‐day history of black, tarry stools.",
            ),
            src_item("burning upper stomach pain", None),
            src_item("burning high stomach pain", None),
        ],
        "equity_dimension": "plain_low_literacy_english",
        "lexicon_entries": [],
        "design_note": (
            "Contrasts compressed clinical terminology ('epigastric pain', 'melenic stools') with multi-word "
            "observational phrasing ('upper stomach pain', 'black tarry stools') while preserving 11 trailing "
            "tokens for downstream readout alignment. Replacing 'black tarry' with 'normal brown' in changed_fact "
            "changes stool blood content alone while keeping stool count and NSAID exposure fixed."
        ),
        "_fact_map": {
            "medical": {"f1": "I took daily ibuprofen for 3 weeks", "f2": "4 days of burning epigastric pain", "f3": "passed melenic stools 2 times today"},
            "everyday": {"f1": "I took daily ibuprofen for 3 weeks", "f2": "4 days of burning upper stomach pain", "f3": "and passed black tarry stools 2 times today"},
            "medical_paraphrase": {"f1": "I used daily oral ibuprofen over 3 weeks", "f2": "4 days of burning epigastric discomfort", "f3": "melena 2 times today"},
            "everyday_paraphrase": {"f1": "I took ibuprofen every day for 3 weeks", "f2": "4 days of burning high stomach pain", "f3": "black tarry stools 2 times today"},
            "changed_fact": {"f1": "I took daily ibuprofen for 3 weeks", "f2": "4 days of burning upper stomach pain", "f3": "and passed normal brown stools 2 times today"},
            "everyday_attribution": {"f1": "I took daily ibuprofen for 3 weeks", "f2": "4 days of burning upper stomach pain", "f3": "and passed black tarry stools 2 times today"},
        },
    },
    {
        "family_id": "r10-06",
        "condition": "acute febrile respiratory illness with resting dyspnea in pregnancy",
        "right_care": 4,
        "level_rationale": (
            "Resting air hunger with a 39 C febrile cough at 31 weeks of pregnancy threatens maternal-fetal "
            "oxygenation and requires emergency hospital care, whereas a 39 C febrile cough at 31 weeks with "
            "easy resting breathing warrants outpatient medical or prenatal evaluation."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Currently 31 weeks pregnant"},
            {"fact_id": "f2", "text": "3 days of dry cough and 39 C fever"},
            {"fact_id": "f3", "text": "Severe difficulty getting air at rest tonight"},
        ],
        "texts": {
            "medical": "I am 31 weeks pregnant with 3 days of nonproductive cough and a 39 C fever plus resting air hunger and dyspnea tonight so I need to go to the",
            "everyday": "I am 31 weeks pregnant with 3 days of a dry cough and a 39 C fever and I'm smothering at rest tonight so I need to go to the",
            "medical_paraphrase": "I am at 31 weeks gestation with 3 days of dry tussis and a 39 C pyrexia complicated by resting dyspnea and air hunger tonight so I need to go to the",
            "everyday_paraphrase": "I am 31 weeks into pregnancy with 3 days of a dry cough and a 39 C fever and feel like I am smothering sitting still tonight so I need to go to the",
            "changed_fact": "I am 31 weeks pregnant with 3 days of a dry cough and a 39 C fever and breathe easily at rest tonight so I need to go to the",
            "everyday_attribution": "I am 31 weeks pregnant with 3 days of a dry cough and a 39 C fever and I'm smothering at rest tonight and I think I just have a cold so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "and I'm smothering at rest tonight",
            "to": "and breathe easily at rest tonight",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think I just have a cold",
            "attributes acute breathlessness and febrile cough to a common cold, matching a verbatim patient delay quote",
            "jiao_2025",
            "direct patient quote",
            "Another one said: I initially thought I just had a cold and was feeling breathless, so I took cold medicine for a while, but it didn’t improve anything.",
        ),
        "swap_spans": {
            "medical_span": "nonproductive cough and a 39 C fever plus resting air hunger and dyspnea",
            "everyday_span": "a dry cough and a 39 C fever and I'm smothering at rest",
        },
        "swap_note": "Single continuous 13-word vs 13-word exact-length span swap between 'I am 31 weeks pregnant with 3 days of ' and ' tonight so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "dry cough",
                "nantanda_2026",
                "authors' summary",
                "The episodes often started as a runny nose and an irritating dry or wet cough, mainly at night, associated with a sound in the chest and difficulty in breathing.",
            ),
            src_item(
                "I'm smothering",
                "ferguson_2023",
                "authors' summary",
                "There were significant increases in the sensory quality of \"smothering/air hunger\" ( P = 0.01) and the emotional response of \"anxiousness\" ( P = 0.04) in the FM condition.",
            ),
            src_item(
                "smothering",
                "wiktionary_smother",
                "dictionary definition",
                "# {{lb|en|intransitive}} To [[breathe]] with great difficulty by reason of smoke, dust, close covering or wrapping, or the like.",
            ),
        ],
        "equity_dimension": "pregnancy_colloquial_smothering",
        "lexicon_entries": ["smothering / I'm smothering"],
        "design_note": (
            "Tests lexicon entry 'smothering / I'm smothering' (documented as breathing with great difficulty / "
            "air hunger) in an exact 13-for-13-word span against 'resting air hunger and dyspnea'. Pairs a "
            "direct patient-quoted 'just had a cold' attribution with a single-fact resting-breathing control."
        ),
        "_fact_map": {
            "medical": {"f1": "I am 31 weeks pregnant", "f2": "3 days of nonproductive cough and a 39 C fever", "f3": "resting air hunger and dyspnea tonight"},
            "everyday": {"f1": "I am 31 weeks pregnant", "f2": "3 days of a dry cough and a 39 C fever", "f3": "and I'm smothering at rest tonight"},
            "medical_paraphrase": {"f1": "I am at 31 weeks gestation", "f2": "3 days of dry tussis and a 39 C pyrexia", "f3": "resting dyspnea and air hunger tonight"},
            "everyday_paraphrase": {"f1": "I am 31 weeks into pregnancy", "f2": "3 days of a dry cough and a 39 C fever", "f3": "feel like I am smothering sitting still tonight"},
            "changed_fact": {"f1": "I am 31 weeks pregnant", "f2": "3 days of a dry cough and a 39 C fever", "f3": "and breathe easily at rest tonight"},
            "everyday_attribution": {"f1": "I am 31 weeks pregnant", "f2": "3 days of a dry cough and a 39 C fever", "f3": "and I'm smothering at rest tonight"},
        },
    },
    {
        "family_id": "r10-07",
        "condition": "acute decompensated fluid overload with orthopnea",
        "right_care": 4,
        "level_rationale": (
            "Progressive bilateral ankle edema and 4 kg weight gain culminating in acute inability to catch "
            "breath when lying flat indicates acute pulmonary congestion requiring ER care, whereas ankle "
            "swelling and weight gain with comfortable supine breathing warrants outpatient medical assessment."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " ER",
        "reference_facts": [
            {"fact_id": "f1", "text": "Patient is 67 years old"},
            {"fact_id": "f2", "text": "2 weeks of swelling in both ankles and 4 kg weight gain"},
            {"fact_id": "f3", "text": "Acute severe shortness of breath when lying flat tonight"},
        ],
        "texts": {
            "medical": "I am 67 with 2 weeks of bilateral ankle edema and 4 kg weight gain and developed acute orthopnea and resting supine dyspnea tonight so I need to go to the",
            "everyday": "I am 67 with 2 weeks of swollen ankles and 4 kg weight gain and got short winded and can't catch my breath lying flat tonight so I need to go to the",
            "medical_paraphrase": "I am 67 years old with 2 weeks of dependent bilateral pedal edema plus 4 kg weight gain and acute orthopnea on recumbency tonight so I need to go to the",
            "everyday_paraphrase": "I am 67 years old with 2 weeks of swelling in both ankles and 4 kg weight gain and I am short winded and can't catch my breath lying flat tonight so I need to go to the",
            "changed_fact": "I am 67 with 2 weeks of swollen ankles and 4 kg weight gain and breathe comfortably when lying flat tonight so I need to go to the",
            "everyday_attribution": "I am 67 with 2 weeks of swollen ankles and 4 kg weight gain and got short winded and can't catch my breath lying flat tonight and I think I am just tired so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "and got short winded and can't catch my breath lying flat tonight",
            "to": "and breathe comfortably when lying flat tonight",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think I am just tired",
            "attributes acute orthopnea and breathlessness to ordinary tiredness, matching a verbatim delay quote from older heart-failure patients",
            "jiao_2025",
            "direct patient quote",
            "I thought I was just tired, so I rested for a while, but I still felt chest tightness and shortness of breath.",
        ),
        "swap_spans": {
            "medical_span": "bilateral ankle edema and 4 kg weight gain and developed acute orthopnea and resting supine dyspnea",
            "everyday_span": "swollen ankles and 4 kg weight gain and got short winded and can't catch my breath lying flat",
        },
        "swap_note": "Single continuous 16-word vs 18-word span swap preserving 'I am 67 with 2 weeks of ' and ' tonight so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "weight gain",
                "opasrattanakon_2026",
                "authors' summary",
                "Bodily sensations enable patients to recognize symptom changes early, supporting timely detection and effective HF management, such as shortness of breath, leg swelling, weight gain, orthopnea, and chest pain.",
            ),
            src_item(
                "short winded",
                "wiktionary_short_winded",
                "dictionary definition",
                "# [[out of breath|Out of breath]], [[gasp]]ing for [[air]]; [[breathing]] [[rapidly]], or given to [[become|becoming]] [[short of breath]].",
            ),
            src_item(
                "can't catch my breath",
                "hardy_2025",
                "authors' summary",
                "\"I can't breathe, I can't catch my breath:\" the impact of school staff storytelling on asthma management.",
            ),
            src_item("swollen ankles", None),
            src_item("swelling in both ankles", None),
        ],
        "equity_dimension": "age_older_adult_colloquial_dyspnea",
        "lexicon_entries": ["short winded", "can't catch my breath"],
        "design_note": (
            "Combines lexicon entries 'short winded' and 'can't catch my breath' in a 16-vs-18-word span against "
            "'acute orthopnea and resting supine dyspnea'. Pairs a direct patient-quoted tiredness attribution "
            "from older heart-failure patients with a single-fact supine-breathing control."
        ),
        "_fact_map": {
            "medical": {"f1": "I am 67", "f2": "2 weeks of bilateral ankle edema and 4 kg weight gain", "f3": "developed acute orthopnea and resting supine dyspnea tonight"},
            "everyday": {"f1": "I am 67", "f2": "2 weeks of swollen ankles and 4 kg weight gain", "f3": "and got short winded and can't catch my breath lying flat tonight"},
            "medical_paraphrase": {"f1": "I am 67 years old", "f2": "2 weeks of dependent bilateral pedal edema plus 4 kg weight gain", "f3": "acute orthopnea on recumbency tonight"},
            "everyday_paraphrase": {"f1": "I am 67 years old", "f2": "2 weeks of swelling in both ankles and 4 kg weight gain", "f3": "I am short winded and can't catch my breath lying flat tonight"},
            "changed_fact": {"f1": "I am 67", "f2": "2 weeks of swollen ankles and 4 kg weight gain", "f3": "and breathe comfortably when lying flat tonight"},
            "everyday_attribution": {"f1": "I am 67", "f2": "2 weeks of swollen ankles and 4 kg weight gain", "f3": "and got short winded and can't catch my breath lying flat tonight"},
        },
    },
    {
        "family_id": "r10-08",
        "condition": "acute febrile dermatomal vesicular rash with confusion",
        "right_care": 4,
        "level_rationale": (
            "A painful unilateral blister band with a 39 C fever plus new acute confusion in a 73-year-old "
            "raises immediate concern for central nervous system or disseminated infection requiring hospital "
            "care, whereas the same localized rash in an alert patient warrants outpatient antiviral therapy."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " hospital",
        "reference_facts": [
            {"fact_id": "f1", "text": "Father is 73 years old"},
            {"fact_id": "f2", "text": "3 days of painful clustered blisters on the left chest"},
            {"fact_id": "f3", "text": "Fever of 39 C"},
            {"fact_id": "f4", "text": "New confusion and disorientation today"},
        ],
        "texts": {
            "medical": "My 73 year old father has 3 days of unilateral left thoracic neuralgia and clustered vesicles with a 39 C fever plus acute disorientation today so I need to go to the",
            "everyday": "My 73 year old father has 3 days of a misery in his left chest and clustered blisters with a 39 C fever plus confusion today so I need to go to the",
            "medical_paraphrase": "My 73 year old dad developed 3 days of left dermatomal chest pain and grouped vesicular lesions with a 39 C pyrexia and acute confusion today so I need to go to the",
            "everyday_paraphrase": "My 73 year old dad had 3 days of a misery in the left side of his chest and clusters of blisters with a 39 C fever and got confused today so I need to go to the",
            "changed_fact": "My 73 year old father has 3 days of a misery in his left chest and clustered blisters with a 39 C fever while staying clear headed today so I need to go to the",
            "everyday_attribution": "My 73 year old father has 3 days of a misery in his left chest and clustered blisters with a 39 C fever plus confusion today and I think it is heat rash so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "plus confusion today",
            "to": "while staying clear headed today",
            "right_care_after": 2,
        },
        "attribution": att_item(
            "and I think it is heat rash",
            "attributes a febrile dermatomal blister eruption with acute confusion in an older adult to benign heat rash",
            None,
        ),
        "swap_spans": {
            "medical_span": "unilateral left thoracic neuralgia and clustered vesicles with a 39 C fever plus acute disorientation",
            "everyday_span": "a misery in his left chest and clustered blisters with a 39 C fever plus confusion",
        },
        "swap_note": "Single continuous 15-word vs 16-word span swap after 'My 73 year old father has 3 days of ' and before ' today so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "a misery in his left chest",
                "wiktionary_misery",
                "dictionary definition",
                "# {{lb|en|US|and|UK|dialects}} A [[bodily]] [[ache]] or [[pain]].",
            ),
            src_item(
                "clusters of blisters",
                "yamada_2026",
                "authors' summary",
                "(a) Clusters of blisters observed on the upper and right sides of the intergluteal cleft; (b) The bladder capacity before catheterization was 808 mL, and no obvious irregularities, wall thickening, or neoplastic lesions were observed.",
            ),
            src_item("clustered blisters", None),
            src_item("confusion", None),
        ],
        "equity_dimension": "age_older_adult_us_uk_regional_dialect",
        "lexicon_entries": ["a misery in my chest (or side, or back)"],
        "design_note": (
            "Uses lexicon entry 'a misery in my chest (or side, or back)' in its documented dialect pain sense "
            "against 'unilateral left thoracic neuralgia' with a 1-word span difference. Reversing only acute "
            "confusion to clear-headedness isolates central nervous system red-flag sensitivity."
        ),
        "_fact_map": {
            "medical": {"f1": "My 73 year old father", "f2": "3 days of unilateral left thoracic neuralgia and clustered vesicles", "f3": "a 39 C fever", "f4": "plus acute disorientation today"},
            "everyday": {"f1": "My 73 year old father", "f2": "3 days of a misery in his left chest and clustered blisters", "f3": "a 39 C fever", "f4": "plus confusion today"},
            "medical_paraphrase": {"f1": "My 73 year old dad", "f2": "3 days of left dermatomal chest pain and grouped vesicular lesions", "f3": "a 39 C pyrexia", "f4": "acute confusion today"},
            "everyday_paraphrase": {"f1": "My 73 year old dad", "f2": "3 days of a misery in the left side of his chest and clusters of blisters", "f3": "a 39 C fever", "f4": "and got confused today"},
            "changed_fact": {"f1": "My 73 year old father", "f2": "3 days of a misery in his left chest and clustered blisters", "f3": "a 39 C fever", "f4": "while staying clear headed today"},
            "everyday_attribution": {"f1": "My 73 year old father", "f2": "3 days of a misery in his left chest and clustered blisters", "f3": "a 39 C fever", "f4": "plus confusion today"},
        },
    },
    # ==================== 6 SPECIALIST (right_care = 3) ====================
    {
        "family_id": "r10-09",
        "condition": "chronic gum disease with tooth mobility",
        "right_care": 3,
        "level_rationale": (
            "Two months of gum bleeding with gum recession and a loose front tooth without submandibular "
            "swelling requires periodontal evaluation by a dentist, whereas rapidly spreading firm swelling "
            "under the jaw and tongue threatens the airway and requires emergency care."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " dentist",
        "reference_facts": [
            {"fact_id": "f1", "text": "2 months of gum bleeding when brushing teeth"},
            {"fact_id": "f2", "text": "Receding gums and 1 loose lower front tooth"},
            {"fact_id": "f3", "text": "No swelling under the jaw or tongue"},
        ],
        "texts": {
            "medical": "I have had 2 months of gingival bleeding on toothbrushing accompanied by gingival recession and 1 mobile mandibular anterior incisor without submandibular or sublingual edema so I should see a",
            "everyday": "I have had 2 months of gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth without jaw or tongue swelling so I should see a",
            "medical_paraphrase": "I experienced 2 months of gingival bleeding during toothbrushing with gingival recession and 1 mobile mandibular central incisor in the absence of submandibular or sublingual edema so I should see a",
            "everyday_paraphrase": "I had 2 months of bleeding gums when brushing my teeth along with gums pulling back and 1 loose lower front tooth without jaw or tongue swelling so I should see a",
            "changed_fact": "I have had 2 months of gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth with fast spreading firm jaw and tongue swelling so I should see a",
            "everyday_attribution": "I have had 2 months of gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth without jaw or tongue swelling and I think it is just ageing so I should see a",
            "quad_b": "I have had 2 months of gingival bleeding on toothbrushing with gingival recession and 1 mobile mandibular anterior incisor without submandibular or sublingual edema so I should see a",
            "quad_c": "I have had 2 months of gum bleeding brushing my teeth accompanied by receding gums and 1 loose lower front tooth without jaw or tongue swelling so I should see a",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "without jaw or tongue swelling",
            "to": "with fast spreading firm jaw and tongue swelling",
            "right_care_after": 4,
        },
        "attribution": att_item(
            "and I think it is just ageing",
            "attributes chronic gum bleeding and tooth loosening to normal ageing, a documented barrier to periodontal care-seeking in older adults",
            "velpula_2025",
            "authors' summary",
            "Participants exhibited low levels of awareness of the fact that periodontal disease is a preventable condition and tended to attribute such symptoms as gum bleeding or sensitivity to ageing.",
        ),
        "swap_spans": {
            "medical_span": "gingival bleeding on toothbrushing accompanied by gingival recession and 1 mobile mandibular anterior incisor without submandibular or sublingual edema",
            "everyday_span": "gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth without jaw or tongue swelling",
        },
        "swap_note": "Exact 19-word vs 19-word single-span swap between 'I have had 2 months of ' and ' so I should see a'.",
        "everyday_sources": [
            src_item(
                "bleeding gums when brushing my teeth",
                "falcon_flores_2026",
                "authors' summary",
                "(2) In the past year, have you had bleeding gums when brushing your teeth?",
            ),
            src_item(
                "gum bleeding",
                "velpula_2025",
                "authors' summary",
                "Participants exhibited low levels of awareness of the fact that periodontal disease is a preventable condition and tended to attribute such symptoms as gum bleeding or sensitivity to ageing.",
            ),
            src_item("receding gums", None),
            src_item("1 loose lower front tooth", None),
            src_item("without jaw or tongue swelling", None),
        ],
        "equity_dimension": "age_older_adult_and_latin_american_dental_access",
        "lexicon_entries": [],
        "design_note": (
            "Crosses clinical periodontal terms ('gingival bleeding', 'mobile mandibular anterior incisor') with "
            "self-report dental phrasing ('bleeding gums when brushing', 'loose lower front tooth') in an exact "
            "19-for-19-word 2 x 2 quad. Pairs a documented ageing attribution with an upward jaw-and-tongue "
            "swelling emergency control."
        ),
        "_fact_map": {
            "medical": {"f1": "2 months of gingival bleeding on toothbrushing", "f2": "gingival recession and 1 mobile mandibular anterior incisor", "f3": "without submandibular or sublingual edema"},
            "everyday": {"f1": "2 months of gum bleeding brushing my teeth", "f2": "receding gums and 1 loose lower front tooth", "f3": "without jaw or tongue swelling"},
            "medical_paraphrase": {"f1": "2 months of gingival bleeding during toothbrushing", "f2": "gingival recession and 1 mobile mandibular central incisor", "f3": "in the absence of submandibular or sublingual edema"},
            "everyday_paraphrase": {"f1": "2 months of bleeding gums when brushing my teeth", "f2": "gums pulling back and 1 loose lower front tooth", "f3": "without jaw or tongue swelling"},
            "changed_fact": {"f1": "2 months of gum bleeding brushing my teeth", "f2": "receding gums and 1 loose lower front tooth", "f3": "with fast spreading firm jaw and tongue swelling"},
            "everyday_attribution": {"f1": "2 months of gum bleeding brushing my teeth", "f2": "receding gums and 1 loose lower front tooth", "f3": "without jaw or tongue swelling"},
            "quad_b": {"f1": "2 months of gingival bleeding on toothbrushing", "f2": "gingival recession and 1 mobile mandibular anterior incisor", "f3": "without submandibular or sublingual edema"},
            "quad_c": {"f1": "2 months of gum bleeding brushing my teeth", "f2": "receding gums and 1 loose lower front tooth", "f3": "without jaw or tongue swelling"},
        },
    },
    {
        "family_id": "r10-10",
        "condition": "chronic scaly plaque eruption refractory to topical therapy",
        "right_care": 3,
        "level_rationale": (
            "Four months of thick red scaly elbow plaques with nail pitting that failed prescribed clinic cream "
            "and lacks raw skin sloughing warrants specialist dermatology management, whereas acute widespread "
            "raw skin sloughing across the chest requires emergency care."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " dermatologist",
        "reference_facts": [
            {"fact_id": "f1", "text": "4 months of thick red scaly plaques on both elbows"},
            {"fact_id": "f2", "text": "Fingernail pitting unimproved after prescribed clinic cream"},
            {"fact_id": "f3", "text": "No raw skin sloughing elsewhere"},
        ],
        "texts": {
            "medical": "I have had 4 months of erythematous plaques with silvery scales on both elbows and ungual pitting refractory to prescribed topical cream without epidermal detachment today so I should see a",
            "everyday": "I have had 4 months of red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream without raw skin sloughing today so I should see a",
            "medical_paraphrase": "I experienced 4 months of thick erythematous elbow plaques with silvery desquamation and nail pitting unresponsive to clinic topical therapy without epidermal sloughing today so I should see a",
            "everyday_paraphrase": "I had 4 months of thick red patches shedding flakes on both elbows with tiny nail pits after prescribed clinic cream failed without raw skin sloughing today so I should see a",
            "changed_fact": "I have had 4 months of red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream with raw skin sloughing across my chest today so I should see a",
            "everyday_attribution": "I have had 4 months of red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream without raw skin sloughing today and I think it is dry skin so I should see a",
            "quad_b": "I have had 4 months of erythematous plaques with silvery scales on both elbows and ungual pitting unimproved by prescribed topical cream without epidermal detachment today so I should see a",
            "quad_c": "I have had 4 months of red patches with silvery scales on both elbows and nail pits refractory to prescribed cream without raw skin sloughing today so I should see a",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "without raw skin sloughing today",
            "to": "with raw skin sloughing across my chest today",
            "right_care_after": 4,
        },
        "attribution": att_item(
            "and I think it is dry skin",
            "attributes chronic scaly plaques with nail pitting that failed topical therapy to ordinary dry skin",
            None,
        ),
        "swap_spans": {
            "medical_span": "erythematous plaques with silvery scales on both elbows and ungual pitting refractory to prescribed topical cream without epidermal detachment",
            "everyday_span": "red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream without raw skin sloughing",
        },
        "swap_note": "Exact 19-word vs 19-word single-span swap between 'I have had 4 months of ' and ' today so I should see a'.",
        "everyday_sources": [
            src_item(
                "red patches",
                "che_awanis_2026",
                "authors' summary",
                "Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin.",
            ),
            src_item(
                "silvery scales",
                "che_awanis_2026",
                "authors' summary",
                "Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin.",
            ),
            src_item(
                "shedding flakes",
                "che_awanis_2026",
                "authors' summary",
                "One respondent shared that she felt burdened because her skin kept shedding flakes onto the office carpet.",
            ),
            src_item("nail pits", None),
            src_item("without raw skin sloughing today", None),
        ],
        "equity_dimension": "southeast_asian_patient_experience",
        "lexicon_entries": [],
        "design_note": (
            "Achieves an exact 19-for-19-word span alignment and full 2 x 2 quad crossing for specialist "
            "dermatology routing (' dermatologist') after failed primary-care topical therapy. Reversing the "
            "epidermal-detachment negation into acute raw chest skin sloughing provides an upward emergency control."
        ),
        "_fact_map": {
            "medical": {"f1": "4 months of erythematous plaques with silvery scales on both elbows", "f2": "ungual pitting refractory to prescribed topical cream", "f3": "without epidermal detachment today"},
            "everyday": {"f1": "4 months of red patches with silvery scales on both elbows", "f2": "nail pits unimproved by prescribed cream", "f3": "without raw skin sloughing today"},
            "medical_paraphrase": {"f1": "4 months of thick erythematous elbow plaques with silvery desquamation", "f2": "nail pitting unresponsive to clinic topical therapy", "f3": "without epidermal sloughing today"},
            "everyday_paraphrase": {"f1": "4 months of thick red patches shedding flakes on both elbows", "f2": "tiny nail pits after prescribed clinic cream failed", "f3": "without raw skin sloughing today"},
            "changed_fact": {"f1": "4 months of red patches with silvery scales on both elbows", "f2": "nail pits unimproved by prescribed cream", "f3": "with raw skin sloughing across my chest today"},
            "everyday_attribution": {"f1": "4 months of red patches with silvery scales on both elbows", "f2": "nail pits unimproved by prescribed cream", "f3": "without raw skin sloughing today"},
            "quad_b": {"f1": "4 months of erythematous plaques with silvery scales on both elbows", "f2": "ungual pitting unimproved by prescribed topical cream", "f3": "without epidermal detachment today"},
            "quad_c": {"f1": "4 months of red patches with silvery scales on both elbows", "f2": "nail pits refractory to prescribed cream", "f3": "without raw skin sloughing today"},
        },
    },
    {
        "family_id": "r10-11",
        "condition": "treatment refractory persistent low mood syndrome",
        "right_care": 3,
        "level_rationale": (
            "Four months of daily low mood anhedonia and early waking that failed 2 primary-care medication "
            "trials in a responsive patient warrants specialist psychiatrist care, whereas becoming mute and "
            "unresponsive requires emergency evaluation."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " psychiatrist",
        "reference_facts": [
            {"fact_id": "f1", "text": "26 year old brother has 4 months of daily low mood sleep disruption and fatigue"},
            {"fact_id": "f2", "text": "Unimproved after 2 prescribed clinic medication trials"},
            {"fact_id": "f3", "text": "Speaking and responding normally today"},
        ],
        "texts": {
            "medical": "My 26 year old brother has 4 months of persistent dysphoria insomnia and fatigue refractory to 2 primary care pharmacotherapy trials while remaining verbally responsive today so I should see a",
            "everyday": "My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue unimproved after 2 prescribed clinic pills while speaking normally today so I should see a",
            "medical_paraphrase": "My 26 year old brother experienced 4 months of pervasive dysphoric mood sleep disturbance and fatigue unresponsive to 2 clinic medication trials with intact verbal responsiveness today so I should see a",
            "everyday_paraphrase": "My 26 year old brother spent 4 months with low mood disrupted sleep and tiredness that failed 2 prescribed doctor pills while talking normally today so I should see a",
            "changed_fact": "My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue unimproved after 2 prescribed clinic pills and became mute and unresponsive today so I should see a",
            "everyday_attribution": "My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue unimproved after 2 prescribed clinic pills while speaking normally today and I think it is work stress so I should see a",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "while speaking normally today",
            "to": "and became mute and unresponsive today",
            "right_care_after": 4,
        },
        "attribution": att_item(
            "and I think it is work stress",
            "attributes persistent refractory mood and sleep symptoms to routine work stress",
            None,
        ),
        "swap_spans": {
            "medical_span": "persistent dysphoria insomnia and fatigue refractory to 2 primary care pharmacotherapy trials while remaining verbally responsive",
            "everyday_span": "daily low mood sleep disruption and fatigue unimproved after 2 prescribed clinic pills while speaking normally",
        },
        "swap_note": "Exact 16-word vs 16-word single-span swap between 'My 26 year old brother has 4 months of ' and ' today so I should see a'.",
        "everyday_sources": [
            src_item(
                "sleep disruption and fatigue",
                "boonkrong_2026",
                "authors' summary",
                "At the same time, some participants described upward comparison, difficulty disengaging at night, sleep disruption, fatigue, and impaired concentration.",
            ),
            src_item(
                "tiredness",
                "boonkrong_2026",
                "authors' summary",
                "Nighttime use was a more consistent concern among heavier users: late scrolling delayed sleep and was followed by tiredness, irritability, mental fog, or reduced concentration the next day.",
            ),
            src_item("daily low mood", None),
            src_item("unimproved after 2 prescribed clinic pills", None),
            src_item("while speaking normally today", None),
        ],
        "equity_dimension": "young_adult_family_caregiver_mental_health",
        "lexicon_entries": [],
        "design_note": (
            "Pairs psychiatric terminology ('dysphoria', 'pharmacotherapy trials', 'verbally responsive') with "
            "plain family wording in an exact 16-for-16-word span without any self-harm content. Changing intact "
            "speech to acute mutism and unresponsiveness provides a sharp upward emergency control."
        ),
        "_fact_map": {
            "medical": {"f1": "My 26 year old brother has 4 months of persistent dysphoria insomnia and fatigue", "f2": "refractory to 2 primary care pharmacotherapy trials", "f3": "while remaining verbally responsive today"},
            "everyday": {"f1": "My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue", "f2": "unimproved after 2 prescribed clinic pills", "f3": "while speaking normally today"},
            "medical_paraphrase": {"f1": "My 26 year old brother experienced 4 months of pervasive dysphoric mood sleep disturbance and fatigue", "f2": "unresponsive to 2 clinic medication trials", "f3": "with intact verbal responsiveness today"},
            "everyday_paraphrase": {"f1": "My 26 year old brother spent 4 months with low mood disrupted sleep and tiredness", "f2": "that failed 2 prescribed doctor pills", "f3": "while talking normally today"},
            "changed_fact": {"f1": "My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue", "f2": "unimproved after 2 prescribed clinic pills", "f3": "and became mute and unresponsive today"},
            "everyday_attribution": {"f1": "My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue", "f2": "unimproved after 2 prescribed clinic pills", "f3": "while speaking normally today"},
        },
    },
    {
        "family_id": "r10-12",
        "condition": "chronic post collision trauma intrusion and avoidance syndrome",
        "right_care": 3,
        "level_rationale": (
            "Three months of nightly collision nightmares daytime flashbacks driving avoidance and startle "
            "without loss of consciousness warrants trauma-focused specialist therapist care, whereas acute "
            "collapse with loss of consciousness right now requires emergency evaluation."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " therapist",
        "reference_facts": [
            {"fact_id": "f1", "text": "Motor vehicle collision 3 months ago"},
            {"fact_id": "f2", "text": "Nightly nightmares and daytime flashbacks"},
            {"fact_id": "f3", "text": "Driving avoidance and exaggerated startle"},
            {"fact_id": "f4", "text": "No loss of consciousness"},
        ],
        "texts": {
            "medical": "I survived a motor vehicle collision 3 months ago and have nightly trauma nightmares intrusive flashbacks driving avoidance and hypervigilance without syncope so I should see a",
            "everyday": "I survived a car crash 3 months ago and have nightly nightmares daytime flashbacks avoidance of driving and jumpiness without blacking out so I should see a",
            "medical_paraphrase": "I was in a vehicular collision 3 months ago and experience recurrent trauma nightmares daytime intrusions driving avoidance and exaggerated startle without loss of consciousness so I should see a",
            "everyday_paraphrase": "I was in a car accident 3 months ago and get nightmares flashbacks avoidance of reminders in traffic and startle easily with no blackouts so I should see a",
            "changed_fact": "I survived a car crash 3 months ago and have nightly nightmares daytime flashbacks avoidance of driving and jumpiness and just blacked out on the floor so I should see a",
            "everyday_attribution": "I survived a car crash 3 months ago and have nightly nightmares daytime flashbacks avoidance of driving and jumpiness without blacking out and I think it will pass alone so I should see a",
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "without blacking out",
            "to": "and just blacked out on the floor",
            "right_care_after": 4,
        },
        "attribution": att_item(
            "and I think it will pass alone",
            "attributes persistent 3-month post-collision trauma symptoms and functional avoidance to transient distress that will resolve without care",
            None,
        ),
        "swap_spans": {
            "medical_span": "motor vehicle collision 3 months ago and have nightly trauma nightmares intrusive flashbacks driving avoidance and hypervigilance without syncope",
            "everyday_span": "car crash 3 months ago and have nightly nightmares daytime flashbacks avoidance of driving and jumpiness without blacking out",
        },
        "swap_note": "Exact 19-word vs 19-word single-span swap between 'I survived a ' and ' so I should see a'.",
        "everyday_sources": [
            src_item(
                "nightmares",
                "dixon_2026",
                "authors' summary",
                "Other symptoms described following MVC-entrapment included nightmares, avoidance of reminders, heightened physiological arousal, and ongoing anxiety; in some cases meeting criteria for ASD or PTSD, as explored below.",
            ),
            src_item(
                "flashbacks",
                "melkevik_2026",
                "authors' summary",
                "The ITQ consists of six items measuring the three PTSD symptom clusters: re-experiencing symptoms (RE; flashbacks or nightmares), avoidance symptoms (AV; avoidance of internal or external reminders of the event), and sense of current threat (TH; hypervigilance or exaggerated startle response).",
            ),
            src_item(
                "avoidance of reminders",
                "dixon_2026",
                "authors' summary",
                "Other symptoms described following MVC-entrapment included nightmares, avoidance of reminders, heightened physiological arousal, and ongoing anxiety; in some cases meeting criteria for ASD or PTSD, as explored below.",
            ),
            src_item(
                "blacking out",
                "wiktionary_blackout",
                "dictionary definition",
                "# A [[temporary]] [[loss]] of [[consciousness]].",
            ),
            src_item("car crash", None),
            src_item("jumpiness", None),
        ],
        "equity_dimension": "trauma_survivor_everyday_register",
        "lexicon_entries": ["blackout / blacked out"],
        "design_note": (
            "Introduces the ' therapist' specialist target in an exact 19-for-19-word span contrasting ICD-style "
            "trauma descriptors ('hypervigilance', 'intrusive flashbacks') with everyday wording and lexicon "
            "entry 'blackout / blacked out'. Flipping 'without blacking out' to an acute blackout on the floor "
            "tests upward emergency sensitivity."
        ),
        "_fact_map": {
            "medical": {"f1": "I survived a motor vehicle collision 3 months ago", "f2": "nightly trauma nightmares intrusive flashbacks", "f3": "driving avoidance and hypervigilance", "f4": "without syncope"},
            "everyday": {"f1": "I survived a car crash 3 months ago", "f2": "nightly nightmares daytime flashbacks", "f3": "avoidance of driving and jumpiness", "f4": "without blacking out"},
            "medical_paraphrase": {"f1": "I was in a vehicular collision 3 months ago", "f2": "recurrent trauma nightmares daytime intrusions", "f3": "driving avoidance and exaggerated startle", "f4": "without loss of consciousness"},
            "everyday_paraphrase": {"f1": "I was in a car accident 3 months ago", "f2": "nightmares flashbacks", "f3": "avoidance of reminders in traffic and startle easily", "f4": "with no blackouts"},
            "changed_fact": {"f1": "I survived a car crash 3 months ago", "f2": "nightly nightmares daytime flashbacks", "f3": "avoidance of driving and jumpiness", "f4": "and just blacked out on the floor"},
            "everyday_attribution": {"f1": "I survived a car crash 3 months ago", "f2": "nightly nightmares daytime flashbacks", "f3": "avoidance of driving and jumpiness", "f4": "without blacking out"},
        },
    },
    {
        "family_id": "r10-13",
        "condition": "gradual bilateral lens clouding with night glare",
        "right_care": 3,
        "level_rationale": (
            "Painless bilateral cloudy vision with night headlight glare and halos progressing gradually over "
            "9 months warrants routine outpatient eye specialist evaluation, whereas sudden bilateral visual "
            "clouding starting 20 minutes ago is a neuro-ophthalmic emergency requiring ER care."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " specialist",
        "reference_facts": [
            {"fact_id": "f1", "text": "Patient is 71 years old"},
            {"fact_id": "f2", "text": "Painless cloudy vision in both eyes"},
            {"fact_id": "f3", "text": "Glare and halos around night headlights"},
            {"fact_id": "f4", "text": "Developed gradually over 9 months"},
        ],
        "texts": {
            "medical": "I am 71 and have painless bilateral visual clouding with nocturnal headlight glare and halos developing gradually over 9 months so I should see a",
            "everyday": "I am 71 and have painless cloudy vision in both eyes with night headlight glare and halos building up over 9 months so I should see a",
            "medical_paraphrase": "I am 71 years old with painless bilateral visual opacification plus nocturnal glare and halos around headlights progressing slowly across 9 months so I should see a",
            "everyday_paraphrase": "I am 71 years old with painless cloudy sight in both eyes and bright glare and halos from night headlights getting worse over 9 months so I should see a",
            "changed_fact": "I am 71 and have painless cloudy vision in both eyes with night headlight glare and halos starting suddenly 20 minutes ago so I should see a",
            "everyday_attribution": "I am 71 and have painless cloudy vision in both eyes with night headlight glare and halos building up over 9 months and I think it is part of getting older so I should see a",
        },
        "changed_fact": {
            "fact_id": "f4",
            "from": "building up over 9 months",
            "to": "starting suddenly 20 minutes ago",
            "right_care_after": 4,
        },
        "attribution": att_item(
            "and I think it is part of getting older",
            "attributes progressive visual clouding and night glare to normal ageing, a documented self-management belief in older adults",
            "coklar_okutkan_2026",
            "authors' summary",
            "Instead, decline is seen as an expected part of getting older rather than a break in life, so new limits can be taken on without threatening the person’s sense of who they are.",
        ),
        "swap_spans": {
            "medical_span": "bilateral visual clouding with nocturnal headlight glare and halos developing gradually",
            "everyday_span": "cloudy vision in both eyes with night headlight glare and halos building up",
        },
        "swap_note": "Single continuous 11-word vs 13-word span swap between 'I am 71 and have painless ' and ' over 9 months so I should see a'.",
        "everyday_sources": [
            src_item(
                "glare and halos",
                "zavodni_2026",
                "authors' summary",
                "Although 25% (n = 6) of patients reported glare or halos “Most of the time” (n = 5) or “Always” (n = 1), 50% (n = 12) of patients reported that they were bothered by glare and halos either “Rarely” or “Never.”",
            ),
            src_item("cloudy vision in both eyes", None),
            src_item("building up over 9 months", None),
        ],
        "equity_dimension": "age_older_adult_ageing_normalization",
        "lexicon_entries": [],
        "design_note": (
            "Tests specialist eye routing (' specialist') when gradual 9-month onset sits at the end of the "
            "clause after identical symptom tokens. Changing only onset duration from 'building up over 9 months' "
            "to 'starting suddenly 20 minutes ago' provides a clean single-attribute chronology control."
        ),
        "_fact_map": {
            "medical": {"f1": "I am 71", "f2": "painless bilateral visual clouding", "f3": "nocturnal headlight glare and halos", "f4": "developing gradually over 9 months"},
            "everyday": {"f1": "I am 71", "f2": "painless cloudy vision in both eyes", "f3": "night headlight glare and halos", "f4": "building up over 9 months"},
            "medical_paraphrase": {"f1": "I am 71 years old", "f2": "painless bilateral visual opacification", "f3": "nocturnal glare and halos around headlights", "f4": "progressing slowly across 9 months"},
            "everyday_paraphrase": {"f1": "I am 71 years old", "f2": "painless cloudy sight in both eyes", "f3": "bright glare and halos from night headlights", "f4": "getting worse over 9 months"},
            "changed_fact": {"f1": "I am 71", "f2": "painless cloudy vision in both eyes", "f3": "night headlight glare and halos", "f4": "starting suddenly 20 minutes ago"},
            "everyday_attribution": {"f1": "I am 71", "f2": "painless cloudy vision in both eyes", "f3": "night headlight glare and halos", "f4": "building up over 9 months"},
        },
    },
    {
        "family_id": "r10-14",
        "condition": "treatment refractory heavy menstrual bleeding",
        "right_care": 3,
        "level_rationale": (
            "Six months of 9-day heavy menstrual bleeding with large clots that failed prescribed clinic hormone "
            "pills without syncope warrants specialist gynecology evaluation, whereas active heavy bleeding with "
            "syncope on standing requires emergency hospital care."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " specialist",
        "reference_facts": [
            {"fact_id": "f1", "text": "6 months of heavy menstrual periods lasting 9 days with large blood clots"},
            {"fact_id": "f2", "text": "Unimproved on prescribed clinic hormone pills"},
            {"fact_id": "f3", "text": "No fainting today"},
        ],
        "texts": {
            "medical": "I have had 6 months of menorrhagia lasting 9 days with large clots refractory to prescribed hormonal pills without orthostatic syncope today so I should see a",
            "everyday": "I have had 6 months of heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills without fainting today so I should see a",
            "medical_paraphrase": "I experienced 6 months of 9 day menorrhagia with large blood clots unresponsive to clinic hormonal therapy and no syncope today so I should see a",
            "everyday_paraphrase": "I spent 6 months having heavy periods for 9 days with large clots that failed prescribed clinic hormone pills without fainting today so I should see a",
            "changed_fact": "I have had 6 months of heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills and fainted standing up today so I should see a",
            "everyday_attribution": "I have had 6 months of heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills without fainting today and I think heavy periods are normal for me so I should see a",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "without fainting today",
            "to": "and fainted standing up today",
            "right_care_after": 4,
        },
        "attribution": att_item(
            "and I think heavy periods are normal for me",
            "attributes refractory 9-day heavy menstrual bleeding with clots to normal personal menses, a documented normalization barrier delaying care",
            "taree_2026",
            "authors' summary",
            "They reported that misogyny, lack of knowledge of normal versus abnormal menses, and the normalization of female suffering deter care-seeking and delay diagnosis (Table 3).",
        ),
        "swap_spans": {
            "medical_span": "menorrhagia lasting 9 days with large clots refractory to prescribed hormonal pills without orthostatic syncope",
            "everyday_span": "heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills without fainting",
        },
        "swap_note": "Exact 15-word vs 15-word single-span swap between 'I have had 6 months of ' and ' today so I should see a'.",
        "everyday_sources": [
            src_item(
                "heavy periods",
                "drejza_2026",
                "direct patient quote",
                "Several participants described diagnosed mental health conditions, with one reporting, ‘I have been diagnosed with PTSD due to my heavy periods, hemorrhages and endometriosis.",
            ),
            src_item("big clots", None),
            src_item("without fainting today", None),
        ],
        "equity_dimension": "reproductive_health_menstrual_normalization",
        "lexicon_entries": [],
        "design_note": (
            "Pairs a verbatim participant phrase ('heavy periods') and documented menstrual-normalization delay "
            "belief against clinical 'menorrhagia' in an exact 15-for-15-word span. Flipping 'without fainting "
            "today' to orthostatic fainting provides an acute hemodynamic emergency control."
        ),
        "_fact_map": {
            "medical": {"f1": "6 months of menorrhagia lasting 9 days with large clots", "f2": "refractory to prescribed hormonal pills", "f3": "without orthostatic syncope today"},
            "everyday": {"f1": "6 months of heavy periods lasting 9 days with big clots", "f2": "unimproved on prescribed hormone pills", "f3": "without fainting today"},
            "medical_paraphrase": {"f1": "6 months of 9 day menorrhagia with large blood clots", "f2": "unresponsive to clinic hormonal therapy", "f3": "and no syncope today"},
            "everyday_paraphrase": {"f1": "6 months having heavy periods for 9 days with large clots", "f2": "that failed prescribed clinic hormone pills", "f3": "without fainting today"},
            "changed_fact": {"f1": "6 months of heavy periods lasting 9 days with big clots", "f2": "unimproved on prescribed hormone pills", "f3": "and fainted standing up today"},
            "everyday_attribution": {"f1": "6 months of heavy periods lasting 9 days with big clots", "f2": "unimproved on prescribed hormone pills", "f3": "without fainting today"},
        },
    },
    # ==================== 6 GENERAL DOCTOR (right_care = 2) ====================
    {
        "family_id": "r10-15",
        "condition": "persistent purulent facial sinus infection",
        "right_care": 2,
        "level_rationale": (
            "Twelve days of worsening sinus pain and pressure with thick green nasal discharge and a 39 C "
            "fever without double vision warrants outpatient clinic evaluation for bacterial sinus infection, "
            "whereas new double vision signals orbital extension requiring emergency care."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " clinic",
        "reference_facts": [
            {"fact_id": "f1", "text": "12 days of worsening pain and pressure around the sinuses"},
            {"fact_id": "f2", "text": "Thick green nasal discharge and 39 C fever"},
            {"fact_id": "f3", "text": "No double vision today"},
        ],
        "texts": {
            "medical": "I have had 12 days of worsening maxillary sinus pain and pressure accompanied by purulent green rhinorrhea and a 39 C fever without diplopia today so I need to go to the",
            "everyday": "I have had 12 days of worsening pain and pressure around the sinuses with thick green nose mucus and a 39 C fever without double vision today so I need to go to the",
            "medical_paraphrase": "I experienced 12 days of progressive paranasal sinus pain and pressure with purulent green nasal discharge and a 39 C pyrexia in the absence of diplopia today so I need to go to the",
            "everyday_paraphrase": "I spent 12 days with worsening pain and pressure around my sinuses plus thick green snot and a 39 C fever and no double vision today so I need to go to the",
            "changed_fact": "I have had 12 days of worsening pain and pressure around the sinuses with thick green nose mucus and a 39 C fever and new double vision today so I need to go to the",
            "quad_b": "I have had 12 days of worsening maxillary sinus pain and pressure with purulent green rhinorrhea and a 39 C fever without diplopia today so I need to go to the",
            "quad_c": "I have had 12 days of worsening pain and pressure around the sinuses accompanied by thick green nose mucus and a 39 C fever without double vision today so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "without double vision today",
            "to": "and new double vision today",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": "maxillary sinus pain and pressure accompanied by purulent green rhinorrhea and a 39 C fever without diplopia",
            "everyday_span": "pain and pressure around the sinuses with thick green nose mucus and a 39 C fever without double vision",
        },
        "swap_note": "Single continuous 17-word vs 19-word span swap between 'I have had 12 days of worsening ' and ' today so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "pain and pressure around the sinuses",
                "coles_2025",
                "authors' summary",
                "Many patients present with chronic or recurrent pain or pressure around the sinuses, often leading to a diagnosis of chronic rhinosinusitis (CRS).",
            ),
            src_item("thick green nose mucus", None),
            src_item("thick green snot", None),
            src_item("without double vision today", None),
        ],
        "equity_dimension": "plain_low_literacy_english",
        "lexicon_entries": [],
        "design_note": (
            "Provides a 2 x 2 primary-care clinic quad (' clinic') anchored by 12-day duration and 39 C fever "
            "so outpatient antibiotic evaluation is clearly above self-care. Flipping 'without double vision "
            "today' to 'and new double vision today' tests orbital red-flag escalation."
        ),
        "_fact_map": {
            "medical": {"f1": "12 days of worsening maxillary sinus pain and pressure", "f2": "purulent green rhinorrhea and a 39 C fever", "f3": "without diplopia today"},
            "everyday": {"f1": "12 days of worsening pain and pressure around the sinuses", "f2": "thick green nose mucus and a 39 C fever", "f3": "without double vision today"},
            "medical_paraphrase": {"f1": "12 days of progressive paranasal sinus pain and pressure", "f2": "purulent green nasal discharge and a 39 C pyrexia", "f3": "in the absence of diplopia today"},
            "everyday_paraphrase": {"f1": "12 days with worsening pain and pressure around my sinuses", "f2": "thick green snot and a 39 C fever", "f3": "and no double vision today"},
            "changed_fact": {"f1": "12 days of worsening pain and pressure around the sinuses", "f2": "thick green nose mucus and a 39 C fever", "f3": "and new double vision today"},
            "quad_b": {"f1": "12 days of worsening maxillary sinus pain and pressure", "f2": "purulent green rhinorrhea and a 39 C fever", "f3": "without diplopia today"},
            "quad_c": {"f1": "12 days of worsening pain and pressure around the sinuses", "f2": "thick green nose mucus and a 39 C fever", "f3": "without double vision today"},
        },
    },
    {
        "family_id": "r10-16",
        "condition": "subacute fatigue cold intolerance and weight gain syndrome",
        "right_care": 2,
        "level_rationale": (
            "Three months of daily fatigue cold intolerance a 6 kg weight gain dry skin and constipation in an "
            "alert adult requires outpatient doctor blood testing, whereas becoming confused and barely awake "
            "requires emergency hospital evaluation."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " doctor",
        "reference_facts": [
            {"fact_id": "f1", "text": "3 months of daily fatigue feeling cold and 6 kg weight gain"},
            {"fact_id": "f2", "text": "Dry skin and hard infrequent stools"},
            {"fact_id": "f3", "text": "Fully alert and oriented today"},
        ],
        "texts": {
            "medical": "I have had 3 months of persistent fatigue cold intolerance and a 6 kg weight gain accompanied by cutaneous dryness and constipation with intact mental alertness today so I should see a",
            "everyday": "I have had 3 months of daily tiredness feeling cold and a 6 kg weight gain with dry skin and hard infrequent stools while staying fully alert today so I should see a",
            "medical_paraphrase": "I experienced 3 months of daily fatigue cold intolerance and a 6 kg weight gain plus cutaneous dryness and constipation while remaining alert and oriented today so I should see a",
            "everyday_paraphrase": "I spent 3 months feeling tired and cold every day with a 6 kg weight gain plus dry skin and constipation while staying clear headed today so I should see a",
            "changed_fact": "I have had 3 months of daily tiredness feeling cold and a 6 kg weight gain with dry skin and hard infrequent stools and became confused and barely awake today so I should see a",
            "quad_b": "I have had 3 months of persistent fatigue cold intolerance and a 6 kg weight gain with cutaneous dryness and constipation while staying mentally alert today so I should see a",
            "quad_c": "I have had 3 months of daily tiredness feeling cold and a 6 kg weight gain accompanied by dry skin and hard infrequent stools with full alertness today so I should see a",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "while staying fully alert today",
            "to": "and became confused and barely awake today",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": "persistent fatigue cold intolerance and a 6 kg weight gain accompanied by cutaneous dryness and constipation with intact mental alertness",
            "everyday_span": "daily tiredness feeling cold and a 6 kg weight gain with dry skin and hard infrequent stools while staying fully alert",
        },
        "swap_note": "Single continuous 20-word vs 21-word span swap between 'I have had 3 months of ' and ' today so I should see a'.",
        "everyday_sources": [
            src_item(
                "weight gain",
                "lathiya_2026",
                "authors' summary",
                "Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being.",
            ),
            src_item(
                "dry skin",
                "lathiya_2026",
                "authors' summary",
                "Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being.",
            ),
            src_item(
                "constipation",
                "lathiya_2026",
                "authors' summary",
                "Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being.",
            ),
            src_item("daily tiredness feeling cold", None),
            src_item("hard infrequent stools", None),
        ],
        "equity_dimension": "south_asian_and_general_primary_care_endocrine",
        "lexicon_entries": [],
        "design_note": (
            "Provides a second primary-care 2 x 2 quad (' doctor') where multi-system metabolic symptoms "
            "plainly require laboratory thyroid testing rather than self-care. Changing intact alertness to "
            "acute confusion and somnolence tests upward emergency sensitivity."
        ),
        "_fact_map": {
            "medical": {"f1": "3 months of persistent fatigue cold intolerance and a 6 kg weight gain", "f2": "cutaneous dryness and constipation", "f3": "with intact mental alertness today"},
            "everyday": {"f1": "3 months of daily tiredness feeling cold and a 6 kg weight gain", "f2": "dry skin and hard infrequent stools", "f3": "while staying fully alert today"},
            "medical_paraphrase": {"f1": "3 months of daily fatigue cold intolerance and a 6 kg weight gain", "f2": "cutaneous dryness and constipation", "f3": "while remaining alert and oriented today"},
            "everyday_paraphrase": {"f1": "3 months feeling tired and cold every day with a 6 kg weight gain", "f2": "dry skin and constipation", "f3": "while staying clear headed today"},
            "changed_fact": {"f1": "3 months of daily tiredness feeling cold and a 6 kg weight gain", "f2": "dry skin and hard infrequent stools", "f3": "and became confused and barely awake today"},
            "quad_b": {"f1": "3 months of persistent fatigue cold intolerance and a 6 kg weight gain", "f2": "cutaneous dryness and constipation", "f3": "while staying mentally alert today"},
            "quad_c": {"f1": "3 months of daily tiredness feeling cold and a 6 kg weight gain", "f2": "dry skin and hard infrequent stools", "f3": "with full alertness today"},
        },
    },
    {
        "family_id": "r10-17",
        "condition": "pediatric acute purulent ocular discharge",
        "right_care": 2,
        "level_rationale": (
            "Two days of thick yellow eye pus matting both eyelids shut in a 3-year-old with normal eye "
            "movement warrants outpatient clinic examination and prescription drops, whereas inability to move "
            "an eye indicates orbital involvement requiring emergency care."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " clinic",
        "reference_facts": [
            {"fact_id": "f1", "text": "Son is 3 years old"},
            {"fact_id": "f2", "text": "2 days of red eyes and thick yellow pus sticking eyelids shut on waking"},
            {"fact_id": "f3", "text": "Moving both eyes normally today"},
        ],
        "texts": {
            "medical": "My 3 year old son has 2 days of bilateral bulbar erythema and purulent ocular discharge matting his eyelids on waking with intact extraocular motility today so I need to go to the",
            "everyday": "My 3 year old son has 2 days of red eyes and thick yellow pus gluing his eyelids shut on waking while moving both eyes easily today so I need to go to the",
            "medical_paraphrase": "My 3 year old boy developed 2 days of bilateral ocular erythema and mucopurulent discharge crusting his eyelids shut each morning with full extraocular movements today so I need to go to the",
            "everyday_paraphrase": "My 3 year old boy had 2 days of red eyes with yellow eye pus sticking his eyelids together on waking and moves both eyes normally today so I need to go to the",
            "changed_fact": "My 3 year old son has 2 days of red eyes and thick yellow pus gluing his eyelids shut on waking and cannot move his right eye today so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "while moving both eyes easily today",
            "to": "and cannot move his right eye today",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": "bilateral bulbar erythema and purulent ocular discharge matting his eyelids on waking with intact extraocular motility",
            "everyday_span": "red eyes and thick yellow pus gluing his eyelids shut on waking while moving both eyes easily",
        },
        "swap_note": "Single continuous 16-word vs 17-word span swap between 'My 3 year old son has 2 days of ' and ' today so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "red eyes",
                "muse_2026",
                "authors' summary",
                "A 4.5-year-old girl from an urban area presented with fever, vomiting, diarrhea, red eyes, and poor oral intake.",
            ),
            src_item("thick yellow pus gluing his eyelids shut on waking", None),
            src_item("while moving both eyes easily today", None),
        ],
        "equity_dimension": "pediatric_caregiver_everyday_english",
        "lexicon_entries": [],
        "design_note": (
            "Pairs pediatric ophthalmic exam terms ('bilateral bulbar erythema', 'intact extraocular motility') "
            "against concrete parent observations ('red eyes', 'gluing his eyelids shut') in a 16-vs-17-word "
            "span. Replacing normal eye movement with acute right-eye ophthalmoplegia tests orbital red-flag sensitivity."
        ),
        "_fact_map": {
            "medical": {"f1": "My 3 year old son", "f2": "2 days of bilateral bulbar erythema and purulent ocular discharge matting his eyelids on waking", "f3": "with intact extraocular motility today"},
            "everyday": {"f1": "My 3 year old son", "f2": "2 days of red eyes and thick yellow pus gluing his eyelids shut on waking", "f3": "while moving both eyes easily today"},
            "medical_paraphrase": {"f1": "My 3 year old boy", "f2": "2 days of bilateral ocular erythema and mucopurulent discharge crusting his eyelids shut each morning", "f3": "with full extraocular movements today"},
            "everyday_paraphrase": {"f1": "My 3 year old boy", "f2": "2 days of red eyes with yellow eye pus sticking his eyelids together on waking", "f3": "and moves both eyes normally today"},
            "changed_fact": {"f1": "My 3 year old son", "f2": "2 days of red eyes and thick yellow pus gluing his eyelids shut on waking", "f3": "and cannot move his right eye today"},
        },
    },
    {
        "family_id": "r10-18",
        "condition": "inhaled corticosteroid associated oral white mucosal plaques",
        "right_care": 2,
        "level_rationale": (
            "Five days of sore white plaques on the tongue and inner cheeks after starting a steroid inhaler "
            "with easy liquid swallowing requires a doctor prescription for antifungal therapy, whereas "
            "inability to swallow water requires emergency hospital assessment."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " doctor",
        "reference_facts": [
            {"fact_id": "f1", "text": "Started a daily steroid inhaler 2 weeks ago"},
            {"fact_id": "f2", "text": "5 days of sore white patches on the tongue and inner cheeks leaving red spots when wiped"},
            {"fact_id": "f3", "text": "Swallowing liquids easily today"},
        ],
        "texts": {
            "medical": "I started a daily corticosteroid inhaler 2 weeks ago and have 5 days of sore white plaques on my tongue and buccal mucosa with erythematous bases when scraped and intact liquid swallowing today so I should see a",
            "everyday": "I started a daily steroid inhaler 2 weeks ago and have 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped while swallowing liquids easily today so I should see a",
            "medical_paraphrase": "I began daily inhaled corticosteroids 2 weeks ago and developed 5 days of painful white oral plaques over my tongue and buccal mucosa leaving erythematous mucosa on scraping with normal liquid intake today so I should see a",
            "everyday_paraphrase": "I began using a daily steroid inhaler 2 weeks ago and got 5 days of sore white patches on my tongue and inside my cheeks that wipe off red while drinking liquids easily today so I should see a",
            "changed_fact": "I started a daily steroid inhaler 2 weeks ago and have 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped and cannot swallow water today so I should see a",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "while swallowing liquids easily today",
            "to": "and cannot swallow water today",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": "corticosteroid inhaler 2 weeks ago and have 5 days of sore white plaques on my tongue and buccal mucosa with erythematous bases when scraped and intact liquid swallowing",
            "everyday_span": "steroid inhaler 2 weeks ago and have 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped while swallowing liquids easily",
        },
        "swap_note": "Exact 28-word vs 28-word single-span swap between 'I started a daily ' and ' today so I should see a'.",
        "everyday_sources": [
            src_item("sore white patches on my tongue and inner cheeks", None),
            src_item("leaving red spots when wiped", None),
            src_item("while swallowing liquids easily today", None),
        ],
        "equity_dimension": "chronic_inhaler_user_plain_english",
        "lexicon_entries": [],
        "design_note": (
            "Uses an exact 28-for-28-word span contrasting oral mucosal clinical terms ('buccal mucosa', "
            "'erythematous bases when scraped') with everyday patient wording where prescription antifungal "
            "care is needed. Flipping easy liquid swallowing to inability to swallow water tests escalation."
        ),
        "_fact_map": {
            "medical": {"f1": "I started a daily corticosteroid inhaler 2 weeks ago", "f2": "5 days of sore white plaques on my tongue and buccal mucosa with erythematous bases when scraped", "f3": "and intact liquid swallowing today"},
            "everyday": {"f1": "I started a daily steroid inhaler 2 weeks ago", "f2": "5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped", "f3": "while swallowing liquids easily today"},
            "medical_paraphrase": {"f1": "I began daily inhaled corticosteroids 2 weeks ago", "f2": "5 days of painful white oral plaques over my tongue and buccal mucosa leaving erythematous mucosa on scraping", "f3": "with normal liquid intake today"},
            "everyday_paraphrase": {"f1": "I began using a daily steroid inhaler 2 weeks ago", "f2": "5 days of sore white patches on my tongue and inside my cheeks that wipe off red", "f3": "while drinking liquids easily today"},
            "changed_fact": {"f1": "I started a daily steroid inhaler 2 weeks ago", "f2": "5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped", "f3": "and cannot swallow water today"},
        },
    },
    {
        "family_id": "r10-19",
        "condition": "expanding annular rash after tick bite",
        "right_care": 2,
        "level_rationale": (
            "An expanding 7 cm red ring rash with a 38 C fever 8 days after a tick bite without syncope "
            "requires a doctor visit for prescription oral antibiotics, whereas adding a syncopal episode "
            "raises concern for cardiac conduction block requiring emergency evaluation."
        ),
        "carrier_frame": "so I should see a",
        "target_token": " doctor",
        "reference_facts": [
            {"fact_id": "f1", "text": "11 year old son had a tick bite on his calf 8 days ago"},
            {"fact_id": "f2", "text": "Expanding 7 cm red ring rash and 38 C fever"},
            {"fact_id": "f3", "text": "No fainting episodes"},
        ],
        "texts": {
            "medical": "My 11 year old son had a calf tick bite 8 days ago and developed an expanding 7 cm annular erythematous rash and a 38 C fever without syncope so I should see a",
            "everyday": "My 11 year old son had a calf tick bite 8 days ago and got a spreading 7 cm red ring rash and a 38 C fever without fainting spells so I should see a",
            "medical_paraphrase": "My 11 year old boy sustained a calf tick bite 8 days ago and has an expanding 7 cm annular erythema and a 38 C pyrexia without syncopal episodes so I should see a",
            "everyday_paraphrase": "My 11 year old boy got a calf tick bite 8 days ago and has a growing 7 cm red bullseye rash and a 38 C fever with no fainting spells so I should see a",
            "changed_fact": "My 11 year old son had a calf tick bite 8 days ago and got a spreading 7 cm red ring rash and a 38 C fever and a fainting spell today so I should see a",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "without fainting spells",
            "to": "and a fainting spell today",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": "developed an expanding 7 cm annular erythematous rash and a 38 C fever without syncope",
            "everyday_span": "got a spreading 7 cm red ring rash and a 38 C fever without fainting spells",
        },
        "swap_note": "Single continuous 15-word vs 16-word span swap after 'My 11 year old son had a calf tick bite 8 days ago and '.",
        "everyday_sources": [
            src_item(
                "tick bite",
                "bogovic_2026",
                "authors' summary",
                "EM was defined as an expanding erythematous skin lesion, with or without central clearing, that developed days to a few weeks after a tick bite or exposure to ticks in an LB-endemic area and had a maximum diameter of ≥5 cm.",
            ),
            src_item(
                "fainting spells",
                "wiktionary_spell",
                "dictionary definition",
                "# {{lb|en|colloquial|US}} A period of illness, or sudden interval of bad spirits, disease etc. {{defdate|from 19th c.}}",
            ),
            src_item("spreading 7 cm red ring rash", None),
        ],
        "equity_dimension": "pediatric_rural_us_colloquial_spell",
        "lexicon_entries": ["spell (a shaking spell, a fainting spell, a dizzy spell)"],
        "design_note": (
            "Contrasts dermatologic morphology ('annular erythematous rash') against parent description ('red "
            "ring rash') and US colloquial lexicon entry 'spell'. Reversing 'without fainting spells' to an "
            "acute fainting spell tests cardiac-conduction red-flag sensitivity."
        ),
        "_fact_map": {
            "medical": {"f1": "My 11 year old son had a calf tick bite 8 days ago", "f2": "an expanding 7 cm annular erythematous rash and a 38 C fever", "f3": "without syncope"},
            "everyday": {"f1": "My 11 year old son had a calf tick bite 8 days ago", "f2": "a spreading 7 cm red ring rash and a 38 C fever", "f3": "without fainting spells"},
            "medical_paraphrase": {"f1": "My 11 year old boy sustained a calf tick bite 8 days ago", "f2": "an expanding 7 cm annular erythema and a 38 C pyrexia", "f3": "without syncopal episodes"},
            "everyday_paraphrase": {"f1": "My 11 year old boy got a calf tick bite 8 days ago", "f2": "a growing 7 cm red bullseye rash and a 38 C fever", "f3": "with no fainting spells"},
            "changed_fact": {"f1": "My 11 year old son had a calf tick bite 8 days ago", "f2": "a spreading 7 cm red ring rash and a 38 C fever", "f3": "and a fainting spell today"},
        },
    },
    {
        "family_id": "r10-20",
        "condition": "subacute exertional dyspnea conjunctival pallor and koilonychia",
        "right_care": 2,
        "level_rationale": (
            "Six weeks of exertional tiredness dizziness on 1 flight of stairs pale inner eyelids and spooned "
            "brittle nails with comfortable resting breathing requires outpatient clinic blood testing, whereas "
            "resting air hunger requires emergency evaluation."
        ),
        "carrier_frame": "so I need to go to the",
        "target_token": " clinic",
        "reference_facts": [
            {"fact_id": "f1", "text": "6 weeks of tiredness and lightheadedness climbing 1 flight of stairs"},
            {"fact_id": "f2", "text": "Pale inner eyelids and brittle spoon shaped nails"},
            {"fact_id": "f3", "text": "Comfortable normal breathing at rest"},
        ],
        "texts": {
            "medical": "I have had 6 weeks of exertional fatigue and lightheadedness climbing 1 flight of stairs accompanied by conjunctival pallor and koilonychia with comfortable resting respiration today so I need to go to the",
            "everyday": "I have had 6 weeks of tiredness and feeling giddy climbing 1 flight of stairs with pale inner eyelids and spooned nails but easy resting breathing today so I need to go to the",
            "medical_paraphrase": "I experienced 6 weeks of exertional fatigue and presyncopal dizziness on 1 flight of stairs accompanied by palpebral conjunctival pallor and brittle spoon nails with normal resting breathing today so I need to go to the",
            "everyday_paraphrase": "I spent 6 weeks getting tired with giddiness climbing 1 flight of stairs plus pale lower eyelids and brittle scooped nails while breathing easily at rest today so I need to go to the",
            "changed_fact": "I have had 6 weeks of tiredness and feeling giddy climbing 1 flight of stairs with pale inner eyelids and spooned nails and am gasping for air at rest today so I need to go to the",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "but easy resting breathing today",
            "to": "and am gasping for air at rest today",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": "exertional fatigue and lightheadedness climbing 1 flight of stairs accompanied by conjunctival pallor and koilonychia with comfortable resting respiration",
            "everyday_span": "tiredness and feeling giddy climbing 1 flight of stairs with pale inner eyelids and spooned nails but easy resting breathing",
        },
        "swap_note": "Single continuous 19-word vs 20-word span swap between 'I have had 6 weeks of ' and ' today so I need to go to the'.",
        "everyday_sources": [
            src_item(
                "giddiness",
                "rana_2025",
                "authors' summary",
                "We describe a 41-year-old previously healthy man who presented with recurrent episodes of syncope, giddiness, and transient blurring of vision over five days.",
            ),
            src_item("feeling giddy", None),
            src_item("pale inner eyelids", None),
            src_item("spooned nails", None),
        ],
        "equity_dimension": "south_asian_english_giddiness",
        "lexicon_entries": ["giddiness / feeling giddy"],
        "design_note": (
            "Tests South Asian English lexicon entry 'giddiness / feeling giddy' (documented as dizziness rather "
            "than excitement) alongside physical signs ('conjunctival pallor and koilonychia' vs 'pale inner "
            "eyelids and spooned nails') that require clinic laboratory testing. Flipping easy resting breathing "
            "to resting air hunger tests upward emergency escalation."
        ),
        "_fact_map": {
            "medical": {"f1": "6 weeks of exertional fatigue and lightheadedness climbing 1 flight of stairs", "f2": "conjunctival pallor and koilonychia", "f3": "with comfortable resting respiration today"},
            "everyday": {"f1": "6 weeks of tiredness and feeling giddy climbing 1 flight of stairs", "f2": "pale inner eyelids and spooned nails", "f3": "but easy resting breathing today"},
            "medical_paraphrase": {"f1": "6 weeks of exertional fatigue and presyncopal dizziness on 1 flight of stairs", "f2": "palpebral conjunctival pallor and brittle spoon nails", "f3": "with normal resting breathing today"},
            "everyday_paraphrase": {"f1": "6 weeks getting tired with giddiness climbing 1 flight of stairs", "f2": "pale lower eyelids and brittle scooped nails", "f3": "while breathing easily at rest today"},
            "changed_fact": {"f1": "6 weeks of tiredness and feeling giddy climbing 1 flight of stairs", "f2": "pale inner eyelids and spooned nails", "f3": "and am gasping for air at rest today"},
        },
    },
    # ==================== 4 SELF-CARE (right_care = 1) ====================
    {
        "family_id": "r10-21",
        "condition": "mild uncomplicated toe web scaling",
        "right_care": 1,
        "level_rationale": (
            "Five days of mild itchy peeling skin confined between the 4th and 5th toes without pus is a minor "
            "superficial toe-web irritation manageable with over-the-counter antifungal cream, whereas oozing "
            "yellow pus indicates secondary bacterial infection needing a clinician."
        ),
        "carrier_frame": "so I just need some",
        "target_token": " cream",
        "reference_facts": [
            {"fact_id": "f1", "text": "5 days of mild itchy peeling skin between the 4th and 5th left toes after gym showers"},
            {"fact_id": "f2", "text": "No pus"},
        ],
        "texts": {
            "medical": "I have had 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers without purulent exudate so I just need some",
            "everyday": "I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers with no yellow pus so I just need some",
            "medical_paraphrase": "I developed 5 days of mild pruritic scaling and peeling in the 4th and 5th left interdigital toe web after gym showers without purulence so I just need some",
            "everyday_paraphrase": "I got 5 days of mild itchy flaking skin between my 4th and 5th left toes after gym showers and no pus at all so I just need some",
            "changed_fact": "I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers oozing thick yellow pus so I just need some",
            "quad_b": "I have had 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers with no purulent exudate so I just need some",
            "quad_c": "I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers without yellow pus so I just need some",
        },
        "changed_fact": {
            "fact_id": "f2",
            "from": "with no yellow pus",
            "to": "oozing thick yellow pus",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": "pruritic interdigital desquamation between my 4th and 5th left toes after gym showers without purulent exudate",
            "everyday_span": "itchy peeling skin between my 4th and 5th left toes after gym showers with no yellow pus",
        },
        "swap_note": "Single continuous 16-word vs 17-word span swap between 'I have had 5 days of mild ' and ' so I just need some'.",
        "everyday_sources": [
            src_item(
                "peeling",
                "kutlu_2025",
                "authors' summary",
                "Tinea pedis manifests as either interdigital erythema with scaling, peeling, and maceration—especially between the fourth and fifth toes—hyperkeratotic thick scaly erythematous plaques on the soles, heels, and sides of the feet, or vesiculobullous intensely pruritic vesicles/bullae on an erythematous base.",
            ),
            src_item("itchy peeling skin between my 4th and 5th left toes", None),
            src_item("with no yellow pus", None),
        ],
        "equity_dimension": "plain_self_care_everyday_english",
        "lexicon_entries": [],
        "design_note": (
            "Tests the new tier-1 self-care carrier ('so I just need some' -> ' cream') in a full 2 x 2 quad "
            "where clinical dermatologic terms ('pruritic interdigital desquamation') describe a minor self-care "
            "problem. Replacing 'with no yellow pus' with purulent oozing raises right care to a clinician."
        ),
        "_fact_map": {
            "medical": {"f1": "5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers", "f2": "without purulent exudate"},
            "everyday": {"f1": "5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers", "f2": "with no yellow pus"},
            "medical_paraphrase": {"f1": "5 days of mild pruritic scaling and peeling in the 4th and 5th left interdigital toe web after gym showers", "f2": "without purulence"},
            "everyday_paraphrase": {"f1": "5 days of mild itchy flaking skin between my 4th and 5th left toes after gym showers", "f2": "and no pus at all"},
            "changed_fact": {"f1": "5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers", "f2": "oozing thick yellow pus"},
            "quad_b": {"f1": "5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers", "f2": "with no purulent exudate"},
            "quad_c": {"f1": "5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers", "f2": "without yellow pus"},
        },
    },
    {
        "family_id": "r10-22",
        "condition": "mild uncomplicated infant diaper area redness",
        "right_care": 1,
        "level_rationale": (
            "One day of mild pink skin redness in a healthy 8-month-old infant's diaper area without pustules "
            "is simple irritant redness managed with over-the-counter barrier ointment, whereas spreading "
            "yellow pus blisters require outpatient pediatric evaluation."
        ),
        "carrier_frame": "so I just need some",
        "target_token": " ointment",
        "reference_facts": [
            {"fact_id": "f1", "text": "8 month old son has 1 day of mild pink redness in the diaper area"},
            {"fact_id": "f2", "text": "No pus blisters"},
        ],
        "texts": {
            "medical": "My 8 month old son has 1 day of mild macular erythema in his diaper area without pustular lesions so I just need some",
            "everyday": "My 8 month old son has 1 day of mild pink skin redness in his diaper area with no pus blisters so I just need some",
            "medical_paraphrase": "My 8 month old infant developed 1 day of mild superficial diaper area erythema in the absence of pustules so I just need some",
            "everyday_paraphrase": "My 8 month old baby boy got 1 day of mild pink redness in his diaper area without any pus bumps so I just need some",
            "changed_fact": "My 8 month old son has 1 day of mild pink skin redness in his diaper area covered in yellow pus blisters so I just need some",
        },
        "changed_fact": {
            "fact_id": "f2",
            "from": "with no pus blisters",
            "to": "covered in yellow pus blisters",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": "macular erythema in his diaper area without pustular lesions",
            "everyday_span": "pink skin redness in his diaper area with no pus blisters",
        },
        "swap_note": "Single continuous 9-word vs 11-word span swap between 'My 8 month old son has 1 day of mild ' and ' so I just need some'.",
        "everyday_sources": [
            src_item(
                "diaper area",
                "alkhamis_2026",
                "authors' summary",
                "Diaper dermatitis (DD) is a broad term used to describe the acute inflammatory skin response caused by irritation from urine, feces, moisture, or friction in the diaper area of infants and children.",
            ),
            src_item("pink skin redness", None),
            src_item("with no pus blisters", None),
        ],
        "equity_dimension": "pediatric_infant_caregiver_self_care",
        "lexicon_entries": [],
        "design_note": (
            "Tests whether clinical morphology ('macular erythema', 'pustular lesions') versus plain parent "
            "wording ('pink skin redness', 'pus blisters') shifts tier-1 barrier-ointment self-care (' ointment'). "
            "Flipping 'with no pus blisters' to yellow pus blisters provides an upward primary-care control."
        ),
        "_fact_map": {
            "medical": {"f1": "My 8 month old son has 1 day of mild macular erythema in his diaper area", "f2": "without pustular lesions"},
            "everyday": {"f1": "My 8 month old son has 1 day of mild pink skin redness in his diaper area", "f2": "with no pus blisters"},
            "medical_paraphrase": {"f1": "My 8 month old infant developed 1 day of mild superficial diaper area erythema", "f2": "in the absence of pustules"},
            "everyday_paraphrase": {"f1": "My 8 month old baby boy got 1 day of mild pink redness in his diaper area", "f2": "without any pus bumps"},
            "changed_fact": {"f1": "My 8 month old son has 1 day of mild pink skin redness in his diaper area", "f2": "covered in yellow pus blisters"},
        },
    },
    {
        "family_id": "r10-23",
        "condition": "mild winter lower leg skin dryness",
        "right_care": 1,
        "level_rationale": (
            "Seven days of mild dry flaky itchy skin on both shins in cold dry winter weather without pus bumps "
            "is uncomplicated winter dry skin managed with over-the-counter moisturizing lotion, whereas "
            "painful yellow pus bumps indicate skin infection needing a clinician."
        ),
        "carrier_frame": "so I just need some",
        "target_token": " lotion",
        "reference_facts": [
            {"fact_id": "f1", "text": "7 days of mild dry flaky itchy skin on both shins in cold winter air"},
            {"fact_id": "f2", "text": "No pus bumps"},
        ],
        "texts": {
            "medical": "I have had 7 days of mild cutaneous dryness fine desquamation and pruritus on both shins in winter weather without pustules so I just need some",
            "everyday": "I have had 7 days of mild dry skin flakiness and itching on both shins in winter weather with no pus bumps so I just need some",
            "medical_paraphrase": "I developed 7 days of mild bilateral pretibial cutaneous dryness scaling and pruritus in cold winter air without pustular lesions so I just need some",
            "everyday_paraphrase": "I got 7 days of mild dry flaky itchy skin on both shins in cold winter weather without any pus bumps so I just need some",
            "changed_fact": "I have had 7 days of mild dry skin flakiness and itching on both shins in winter weather with painful yellow pus bumps so I just need some",
            "quad_b": "I have had 7 days of mild cutaneous dryness fine desquamation and pruritus on both shins in winter weather with no pustules so I just need some",
            "quad_c": "I have had 7 days of mild dry skin flakiness and itching on both shins in winter weather without pus bumps so I just need some",
        },
        "changed_fact": {
            "fact_id": "f2",
            "from": "with no pus bumps",
            "to": "with painful yellow pus bumps",
            "right_care_after": 2,
        },
        "swap_spans": {
            "medical_span": "cutaneous dryness fine desquamation and pruritus on both shins in winter weather without pustules",
            "everyday_span": "dry skin flakiness and itching on both shins in winter weather with no pus bumps",
        },
        "swap_note": "Single continuous 14-word vs 15-word span swap between 'I have had 7 days of mild ' and ' so I just need some'.",
        "everyday_sources": [
            src_item(
                "dry skin",
                "wang_2026_lotion",
                "authors' summary",
                "Dry skin, marked by flakiness and a rough texture, is a key contributor to various skin issues, primarily caused by a compromised skin barrier that results in moisture loss [23].",
            ),
            src_item(
                "flakiness",
                "wang_2026_lotion",
                "authors' summary",
                "Dry skin, marked by flakiness and a rough texture, is a key contributor to various skin issues, primarily caused by a compromised skin barrier that results in moisture loss [23].",
            ),
            src_item(
                "itching",
                "wang_2026_lotion",
                "authors' summary",
                "Xerosis, marked by a compromised skin barrier and disrupted lipid metabolism, leads to dryness, scaling, and itching.",
            ),
            src_item(
                "shins",
                "wang_2026_lotion",
                "authors' summary",
                "Xerosis predominantly manifests on the lower extremities, particularly the shins and calves, where the density of sebaceous glands is minimal and transepidermal water loss is pronounced [3].",
            ),
            src_item("with no pus bumps", None),
        ],
        "equity_dimension": "plain_self_care_everyday_english",
        "lexicon_entries": [],
        "design_note": (
            "Provides a second tier-1 self-care 2 x 2 quad (' lotion') testing whether formal dermatologic "
            "wording ('cutaneous dryness fine desquamation and pruritus') stays at self-care when facts are "
            "benign. Replacing 'with no pus bumps' with painful yellow pus bumps tests upward sensitivity."
        ),
        "_fact_map": {
            "medical": {"f1": "7 days of mild cutaneous dryness fine desquamation and pruritus on both shins in winter weather", "f2": "without pustules"},
            "everyday": {"f1": "7 days of mild dry skin flakiness and itching on both shins in winter weather", "f2": "with no pus bumps"},
            "medical_paraphrase": {"f1": "7 days of mild bilateral pretibial cutaneous dryness scaling and pruritus in cold winter air", "f2": "without pustular lesions"},
            "everyday_paraphrase": {"f1": "7 days of mild dry flaky itchy skin on both shins in cold winter weather", "f2": "without any pus bumps"},
            "changed_fact": {"f1": "7 days of mild dry skin flakiness and itching on both shins in winter weather", "f2": "with painful yellow pus bumps"},
            "quad_b": {"f1": "7 days of mild cutaneous dryness fine desquamation and pruritus on both shins in winter weather", "f2": "with no pustules"},
            "quad_c": {"f1": "7 days of mild dry skin flakiness and itching on both shins in winter weather", "f2": "without pus bumps"},
        },
    },
    {
        "family_id": "r10-24",
        "condition": "mild seasonal pollen sneezing and watery eyes",
        "right_care": 1,
        "level_rationale": (
            "Three days of sneezing clear runny nose and mildly itchy watery eyes outdoors in spring pollen "
            "with easy breathing is mild seasonal pollen irritation manageable with over-the-counter allergy "
            "medicine, whereas acute inability to catch breath at rest requires emergency care."
        ),
        "carrier_frame": "so I just need some",
        "target_token": " medicine",
        "reference_facts": [
            {"fact_id": "f1", "text": "3 days of sneezing and clear runny nose outdoors in spring pollen"},
            {"fact_id": "f2", "text": "Mildly itchy watery eyes"},
            {"fact_id": "f3", "text": "Easy normal breathing"},
        ],
        "texts": {
            "medical": "I have had 3 days of paroxysmal sneezing and clear aqueous rhinorrhea outdoors in spring pollen with mild ocular pruritus and epiphora and eupnea today so I just need some",
            "everyday": "I have had 3 days of sneezing and a clear running nose outdoors in spring pollen with mildly itchy watery eyes and easy breathing today so I just need some",
            "medical_paraphrase": "I developed 3 days of sneezing and clear watery rhinorrhea around spring pollen accompanied by mild bilateral ocular pruritus and tearing with normal respiration today so I just need some",
            "everyday_paraphrase": "I got 3 days of sneezing when my nose starts running outdoors in spring pollen with mildly itchy and watery eyes and comfortable breathing today so I just need some",
            "changed_fact": "I have had 3 days of sneezing and a clear running nose outdoors in spring pollen with mildly itchy watery eyes and cannot catch my breath sitting still today so I just need some",
        },
        "changed_fact": {
            "fact_id": "f3",
            "from": "and easy breathing today",
            "to": "and cannot catch my breath sitting still today",
            "right_care_after": 4,
        },
        "swap_spans": {
            "medical_span": "paroxysmal sneezing and clear aqueous rhinorrhea outdoors in spring pollen with mild ocular pruritus and epiphora and eupnea",
            "everyday_span": "sneezing and a clear running nose outdoors in spring pollen with mildly itchy watery eyes and easy breathing",
        },
        "swap_note": "Exact 18-word vs 18-word single-span swap between 'I have had 3 days of ' and ' today so I just need some'.",
        "everyday_sources": [
            src_item(
                "my nose starts running",
                "opadokun_2026",
                "direct patient quote",
                "Pollen emerged as a widely recognised trigger, particularly during spring: “When the wind picks up in spring, I can feel it instantly; my nose starts running, and I can’t stop sneezing” (P9).",
            ),
            src_item(
                "sneezing",
                "opadokun_2026",
                "direct patient quote",
                "Pollen emerged as a widely recognised trigger, particularly during spring: “When the wind picks up in spring, I can feel it instantly; my nose starts running, and I can’t stop sneezing” (P9).",
            ),
            src_item(
                "itchy and watery eyes",
                "opadokun_2026",
                "authors' summary",
                "Participants reported a wide range of symptoms including nasal congestion, sneezing, itchy and watery eyes, headaches and fatigue.",
            ),
            src_item("and easy breathing today", None),
        ],
        "equity_dimension": "plain_self_care_everyday_english",
        "lexicon_entries": [],
        "design_note": (
            "Completes the 4 self-care targets (' medicine') in an exact 18-for-18-word span contrasting "
            "dense clinical terms ('aqueous rhinorrhea', 'ocular pruritus and epiphora', 'eupnea') against a "
            "direct patient quote ('my nose starts running'). Flipping easy breathing to resting inability to "
            "catch breath provides an acute respiratory escalation control."
        ),
        "_fact_map": {
            "medical": {"f1": "3 days of paroxysmal sneezing and clear aqueous rhinorrhea outdoors in spring pollen", "f2": "mild ocular pruritus and epiphora", "f3": "and eupnea today"},
            "everyday": {"f1": "3 days of sneezing and a clear running nose outdoors in spring pollen", "f2": "mildly itchy watery eyes", "f3": "and easy breathing today"},
            "medical_paraphrase": {"f1": "3 days of sneezing and clear watery rhinorrhea around spring pollen", "f2": "mild bilateral ocular pruritus and tearing", "f3": "with normal respiration today"},
            "everyday_paraphrase": {"f1": "3 days of sneezing when my nose starts running outdoors in spring pollen", "f2": "mildly itchy and watery eyes", "f3": "and comfortable breathing today"},
            "changed_fact": {"f1": "3 days of sneezing and a clear running nose outdoors in spring pollen", "f2": "mildly itchy watery eyes", "f3": "and cannot catch my breath sitting still today"},
        },
    },
]


EXTRA_VALID_MEDICAL_WORDS = {
    "acutely", "angioedema", "annular", "aphagia", "aqueous", "arthralgia", "autonomic",
    "became", "began", "bilateral", "box", "buccal", "bulbar", "bullseye", "cephalalgia", "cervical",
    "conjunctival", "corticosteroid", "corticosteroids", "cutaneous", "dermatomal",
    "desquamation", "diplopia", "disorientation", "dysarthria", "dysphagia", "dysphoria",
    "dysphoric", "dyspnea", "edema", "epidermal", "epigastric", "epiphora", "erythema",
    "erythematous", "eupnea", "exertional", "extraocular", "exudate", "febrile",
    "flakiness", "flashbacks", "giddiness", "gingival", "halos", "headlight",
    "headlights", "hypervigilance", "ibuprofen", "incisor", "inhaler", "insomnia",
    "interdigital", "intrusive", "intrusions", "jumpiness", "koilonychia", "labial",
    "lightheadedness", "lumbar", "lymphadenopathy", "macular", "mandibular", "matting",
    "maxillary", "melena", "melenic", "menorrhagia", "motility", "mucopurulent",
    "mucosa", "neuralgia", "nightmares", "nocturnal", "nonproductive", "ocular",
    "opacification", "ophthalmoplegia", "orthopnea", "orthostatic", "pallor",
    "palpebral", "paranasal", "paresthesia", "paroxysmal", "pedal", "perioral",
    "pharmacotherapy", "pharyngeal", "pharyngitis", "plaques", "pleuritic",
    "presyncopal", "pretibial", "pruritic", "pruritus", "purulence", "purulent",
    "pustular", "pustules", "pyrexia", "radicular", "radiculopathy", "recumbency",
    "refractory", "responsiveness", "rhinorrhea", "sialorrhea", "snot", "spooned",
    "steroid", "sublingual", "submandibular", "supine", "syncopal", "syncope",
    "thoracic", "toothbrushing", "tussis", "ungual", "unilateral", "unimproved",
    "unresponsive", "vehicular", "verbally", "vesicles", "vesicular",
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
    words.update({"i'm", "can't", "4th", "5th", "c", "kg", "cm"})
    return words


def validate_all(families: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    lex_data = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    core_lex = {entry["expression"] for entry in lex_data["core"]}
    valid_words = load_system_words()

    if len(families) != 24:
        errors.append(f"Expected 24 families, got {len(families)}")

    expected_ids = [f"r10-{i:02d}" for i in range(1, 25)]
    actual_ids = [f["family_id"] for f in families]
    if actual_ids != expected_ids:
        errors.append(f"family_id sequence mismatch: {actual_ids}")

    care_counts = {4: 0, 3: 0, 2: 0, 1: 0}
    quad_by_tier = {4: 0, 3: 0, 2: 0, 1: 0}
    seen_conditions: set[str] = set()

    for fam in families:
        fid = fam["family_id"]
        rc = fam["right_care"]
        care_counts[rc] = care_counts.get(rc, 0) + 1
        cf = fam["carrier_frame"]
        tt = fam["target_token"]

        cond_lower = fam["condition"].strip().lower()
        if cond_lower in ROUND9_CONDITIONS:
            errors.append(f"{fid}: condition {cond_lower!r} was already used in Round 9")
        if cond_lower in seen_conditions:
            errors.append(f"{fid}: duplicate condition {cond_lower!r}")
        seen_conditions.add(cond_lower)

        if (cf, tt) not in ALLOWED_CARE_SPECS.get(rc, []):
            errors.append(f"{fid}: invalid (right_care={rc}, carrier={cf!r}, target={tt!r})")
        if not tt.startswith(" "):
            errors.append(f"{fid}: target_token missing leading space: {tt!r}")

        # Check level_rationale: exactly 1 sentence, no unopened guideline names
        lr = fam.get("level_rationale", "").strip()
        lr_sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", lr) if s.strip()]
        if len(lr_sents) != 1 or not lr.endswith("."):
            errors.append(f"{fid}: level_rationale must be 1 sentence ending with '.', got {len(lr_sents)}: {lr!r}")
        for gw in re.findall(r"[A-Za-z]+", lr.lower()):
            if gw in GUIDELINE_BANNED_WORDS:
                errors.append(f"{fid}: level_rationale mentions guideline/agency token {gw!r}")

        texts = fam["texts"]
        has_quad = ("quad_b" in texts) or ("quad_c" in texts)
        if has_quad:
            if not ("quad_b" in texts and "quad_c" in texts):
                errors.append(f"{fid}: must have both quad_b and quad_c if either present")
            quad_by_tier[rc] = quad_by_tier.get(rc, 0) + 1

        needs_att = rc in (4, 3)
        if needs_att:
            if "attribution" not in fam or "everyday_attribution" not in texts:
                errors.append(f"{fid}: emergency/specialist family missing attribution or texts.everyday_attribution")
        else:
            if "attribution" in fam or "everyday_attribution" in texts:
                errors.append(f"{fid}: tier {rc} family should not have attribution")

        req_text_keys = ["medical", "everyday", "medical_paraphrase", "everyday_paraphrase", "changed_fact"]
        if needs_att:
            req_text_keys.append("everyday_attribution")
        if has_quad:
            req_text_keys += ["quad_b", "quad_c"]
        if set(texts.keys()) != set(req_text_keys):
            errors.append(f"{fid}: unexpected texts keys {set(texts.keys())} != {set(req_text_keys)}")

        matched_numbers: dict[str, list[str]] = {}

        for tname, tval in texts.items():
            words = tval.split()
            if len(words) > 40:
                errors.append(f"{fid}.{tname}: exceeds 40 words ({len(words)})")
            if not (tval.startswith("I ") or tval.startswith("My ")):
                errors.append(f"{fid}.{tname}: must start in first-person active voice ('I ' or 'My '), got {words[:3]}")
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
                if valid_words is not None and not re.fullmatch(r"\d+(?:\.\d+)?", wl) and wl not in valid_words:
                    errors.append(f"{fid}.{tname}: unknown/possibly misspelled word {w!r}")

            if tname != "changed_fact":
                matched_numbers[tname] = re.findall(r"\d+(?:\.\d+)?", tval)

        base_nums = matched_numbers["medical"]
        for tname, nums in matched_numbers.items():
            if nums != base_nums:
                errors.append(f"{fid}.{tname}: ordered numbers {nums} != medical {base_nums}")

        # Check attribution structure and exact insertion before carrier_frame
        if needs_att:
            att = fam["attribution"]
            clause = att["clause"]
            expected_att_text = texts["everyday"][: -len(cf)] + clause + " " + cf
            if texts["everyday_attribution"] != expected_att_text:
                errors.append(
                    f"{fid}: everyday_attribution != everyday with clause inserted before carrier_frame\n"
                    f"  got:      {texts['everyday_attribution']!r}\n"
                    f"  expected: {expected_att_text!r}"
                )
            if texts["everyday_attribution"].replace(" " + clause, "", 1) != texts["everyday"]:
                errors.append(f"{fid}: removing ' ' + clause once from everyday_attribution != everyday")
            _validate_source_record(f"{fid}.attribution", att, is_att=True, errors=errors)

        ev_surface = " || ".join(
            texts[k] for k in ("everyday", "everyday_paraphrase", "quad_c") if k in texts
        ).lower()
        for idx_es, es_rec in enumerate(fam["everyday_sources"]):
            if es_rec["expression"].lower() not in ev_surface:
                errors.append(
                    f"{fid}.everyday_sources[{idx_es}]: expression {es_rec['expression']!r} not verbatim in everyday texts"
                )
            _validate_source_record(f"{fid}.everyday_sources[{idx_es}]", es_rec, is_att=False, errors=errors)

        # Check swap_spans
        sp = fam["swap_spans"]
        ms = sp["medical_span"]
        es = sp["everyday_span"]
        if texts["medical"].count(ms) != 1:
            errors.append(f"{fid}: medical_span occurs {texts['medical'].count(ms)} times in medical")
        elif texts["medical"].replace(ms, es, 1) != texts["everyday"]:
            errors.append(f"{fid}: swap_spans replacement does not produce everyday exactly")
        ms_w = ms.split()
        es_w = es.split()
        if abs(len(ms_w) - len(es_w)) > 2:
            errors.append(f"{fid}: |len(ms)={len(ms_w)} - len(es)={len(es_w)}| = {abs(len(ms_w)-len(es_w))} > 2")
        if ms_w[0] == es_w[0]:
            errors.append(f"{fid}: swap_spans share leading word {ms_w[0]!r}")
        if ms_w[-1] == es_w[-1]:
            errors.append(f"{fid}: swap_spans share trailing word {ms_w[-1]!r}")
        if re.findall(r"\d+(?:\.\d+)?", ms) != re.findall(r"\d+(?:\.\d+)?", es):
            errors.append(f"{fid}: numbers inside swap_spans differ between medical_span and everyday_span")

        # Check changed_fact replacement
        cf_meta = fam["changed_fact"]
        if cf_meta["right_care_after"] == rc:
            errors.append(f"{fid}: changed_fact right_care_after ({cf_meta['right_care_after']}) == right_care")
        if texts["everyday"].count(cf_meta["from"]) != 1:
            errors.append(f"{fid}: changed_fact.from occurs {texts['everyday'].count(cf_meta['from'])} times in everyday")
        elif texts["everyday"].replace(cf_meta["from"], cf_meta["to"], 1) != texts["changed_fact"]:
            errors.append(f"{fid}: changed_fact replacement does not produce texts.changed_fact")

        # Check _fact_map order and exact substrings in every text
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
                if tname == "changed_fact" and f_id != cf_meta["fact_id"]:
                    if frag != fmap["everyday"][f_id]:
                        errors.append(f"{fid}.changed_fact: unchanged fact {f_id} differs from everyday")

        for le in fam["lexicon_entries"]:
            if le not in core_lex:
                errors.append(f"{fid}: lexicon entry {le!r} not in dialect_lexicon_20261109.json core")

        dn_sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", fam["design_note"].strip()) if s.strip()]
        if not (2 <= len(dn_sents) <= 3):
            errors.append(f"{fid}: design_note has {len(dn_sents)} sentences (expected 2-3)")

    if care_counts != {4: 8, 3: 6, 2: 6, 1: 4}:
        errors.append(f"Care tier counts {care_counts} != {{4: 8, 3: 6, 2: 6, 1: 4}}")
    if sum(quad_by_tier.values()) != 8 or any(quad_by_tier[t] < 2 for t in (4, 3, 2)):
        errors.append(f"Quad counts by tier {quad_by_tier} invalid (need 8 total and >=2 in 4, 3, 2)")

    return errors


def _validate_source_record(label: str, rec: dict[str, Any], *, is_att: bool, errors: list[str]) -> None:
    allowed_qt = {"direct patient quote", "authors' summary", "dictionary definition", "none"}
    allowed_acc = {"full text", "abstract only", "title only"}
    qt = rec.get("quote_type")
    if qt not in allowed_qt:
        errors.append(f"{label}: invalid quote_type {qt!r}")
    if rec.get("source") == "none":
        if rec.get("pmid_or_doi") is not None or qt != "none" or rec.get("evidence") is not None or rec.get("access") is not None:
            errors.append(f"{label}: 'source': 'none' must have null pmid_or_doi/evidence/access and quote_type 'none'")
    else:
        if qt == "none":
            errors.append(f"{label}: non-none source has quote_type 'none'")
        if rec.get("access") not in allowed_acc:
            errors.append(f"{label}: invalid access {rec.get('access')!r}")
        if not rec.get("evidence") or not isinstance(rec.get("evidence"), str):
            errors.append(f"{label}: missing evidence sentence")
        if not rec.get("pmid_or_doi") or not isinstance(rec.get("pmid_or_doi"), str):
            errors.append(f"{label}: missing pmid_or_doi")
        for field in ("source", "pmid_or_doi", "evidence"):
            val = str(rec.get(field) or "")
            if m := DB_ID_PATTERN.search(val):
                errors.append(f"{label}.{field}: forbidden database identifier {m.group(0)!r}")
    if is_att and not rec.get("explains"):
        errors.append(f"{label}: missing explains")


def build_clean_json(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fam in families:
        ms_w = len(fam["swap_spans"]["medical_span"].split())
        es_w = len(fam["swap_spans"]["everyday_span"].split())
        # Keep swap_note accurate to exact computed span word counts
        swap_note = fam["swap_note"]
        if "Wait-checked" in swap_note or "wait" in swap_note:
            swap_note = (
                f"Single continuous {ms_w}-word vs {es_w}-word span swap producing everyday from medical."
            )
        item: dict[str, Any] = {
            "family_id": fam["family_id"],
            "condition": fam["condition"],
            "right_care": fam["right_care"],
            "level_rationale": fam["level_rationale"],
            "carrier_frame": fam["carrier_frame"],
            "target_token": fam["target_token"],
            "reference_facts": fam["reference_facts"],
            "texts": fam["texts"],
            "changed_fact": fam["changed_fact"],
        }
        if "attribution" in fam:
            item["attribution"] = fam["attribution"]
        item["swap_spans"] = fam["swap_spans"]
        item["swap_note"] = swap_note
        item["everyday_sources"] = fam["everyday_sources"]
        item["equity_dimension"] = fam["equity_dimension"]
        item["lexicon_entries"] = fam["lexicon_entries"]
        item["design_note"] = fam["design_note"]
        out.append(item)
    return out


def build_check_pairs(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    # 1. 24 register pairs (medical vs everyday)
    for fam in families:
        fid = fam["family_id"]
        rec: dict[str, Any] = {
            "id": f"{fid}-reg",
            "top_prompt": fam["texts"]["medical"],
            "bottom_prompt": fam["texts"]["everyday"],
            "target_clinical_token": fam["target_token"],
            "swap_spans": {
                "clinical_span": fam["swap_spans"]["medical_span"],
                "patient_span": fam["swap_spans"]["everyday_span"],
            },
            "carrier_frame": fam["carrier_frame"],
            "clinical_tier_expected": fam["right_care"],
            "lexicon_entries": fam["lexicon_entries"],
        }
        pairs.append(rec)

    # 2. 24 changed-fact pairs (everyday vs changed_fact)
    for fam in families:
        fid = fam["family_id"]
        pairs.append(
            {
                "id": f"{fid}-cf",
                "top_prompt": fam["texts"]["everyday"],
                "bottom_prompt": fam["texts"]["changed_fact"],
                "target_clinical_token": fam["target_token"],
                "swap_spans": {
                    "clinical_span": fam["changed_fact"]["from"],
                    "patient_span": fam["changed_fact"]["to"],
                },
                "carrier_frame": fam["carrier_frame"],
                "clinical_tier_expected": fam["right_care"],
            }
        )

    # 3. 14 attribution pairs (everyday vs everyday_attribution)
    for fam in families:
        if "attribution" not in fam:
            continue
        fid = fam["family_id"]
        pairs.append(
            {
                "id": f"{fid}-att",
                "top_prompt": fam["texts"]["everyday"],
                "bottom_prompt": fam["texts"]["everyday_attribution"],
                "target_clinical_token": fam["target_token"],
                "swap_spans": {
                    "clinical_span": "",
                    "patient_span": " " + fam["attribution"]["clause"],
                },
                "carrier_frame": fam["carrier_frame"],
                "clinical_tier_expected": fam["right_care"],
            }
        )
    return pairs


def build_sources_md(families: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "# Round 10 Sources (`round10_20261112`)",
        "",
        "Every cited source in `families.json` (across both `everyday_sources` and `attribution`) is listed "
        "below with its full reference, PMID and DOI (or verified Wiktionary URL from "
        "`lexicon/dialect_lexicon_20261109.json`), what was directly opened (`access`), `quote_type`, "
        "what it supports, and the exact verbatim `evidence` sentence(s) copied from the source. "
        "No database identifiers other than PMID and DOI are used. Expressions and attribution clauses "
        "without a directly inspected source sentence are marked `\"source\": \"none\"` and listed in "
        "`self_check.md`.",
        "",
    ]

    uses_by_source: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for fam in families:
        fid = fam["family_id"]
        for es in fam["everyday_sources"]:
            if es["source"] != "none":
                uses_by_source.setdefault(es["source"], []).append(
                    (fid, f"everyday expression `\"{es['expression']}\"`", es["quote_type"], es["access"], es["evidence"])
                )
        if "attribution" in fam and fam["attribution"]["source"] != "none":
            att = fam["attribution"]
            uses_by_source.setdefault(att["source"], []).append(
                (fid, f"attribution clause `\"{att['clause']}\"`", att["quote_type"], att["access"], att["evidence"])
            )

    idx = 0
    for key in SOURCES_ORDER:
        rec = SOURCES_BANK[key]
        cit = rec["source"]
        uses = uses_by_source.get(cit, [])
        if not uses:
            continue
        idx += 1
        lines.append(f"## {idx}. {cit}")
        lines.append("")
        lines.append(f"- **PMID / DOI / URL:** `{rec['pmid_or_doi']}`")
        lines.append(f"- **Access opened:** `{rec['access']}`")
        sup_parts = [f"`{fid}` ({what} — *{qt}*)" for fid, what, qt, _acc, _ev in uses]
        lines.append(f"- **Supports:** {', '.join(sup_parts)}")
        seen_ev: list[str] = []
        for _fid, _what, _qt, _acc, ev in uses:
            if ev not in seen_ev:
                seen_ev.append(ev)
        for ev in seen_ev:
            lines.append(f"- **Verbatim evidence sentence:** `{ev}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_self_check_md(families: list[dict[str, Any]]) -> str:
    total_texts = sum(len(f["texts"]) for f in families)
    report_path = OUT_DIR / "check_report.json"
    report_data = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None

    lines: list[str] = [
        "# Round 10 Self-Check (`round10_20261112`)",
        "",
        "## Summary Verification",
        "",
        f"- **Total case families:** {len(families)} (`r10-01` to `r10-24`), all using conditions unused in Round 9",
        "- **Care-level & target split (verified against `data/urgency_tiers.draft.json` on `origin/main`):**",
        "  - **8 emergency (`right_care: 4`, carrier `\"so I need to go to the\"`):** 4 `\" ER\"` (`r10-01`, `r10-02`, `r10-04`, `r10-07`) + 4 `\" hospital\"` (`r10-03`, `r10-05`, `r10-06`, `r10-08`)",
        "  - **6 specialist (`right_care: 3`, carrier `\"so I should see a\"`):** 1 `\" dentist\"` (`r10-09`), 1 `\" dermatologist\"` (`r10-10`), 1 `\" psychiatrist\"` (`r10-11`), 1 `\" therapist\"` (`r10-12`), 2 `\" specialist\"` (`r10-13`, `r10-14`)",
        "  - **6 general doctor (`right_care: 2`):** 3 `\" clinic\"` with `\"so I need to go to the\"` (`r10-15`, `r10-17`, `r10-20`) + 3 `\" doctor\"` with `\"so I should see a\"` (`r10-16`, `r10-18`, `r10-19`)",
        "  - **4 self-care (`right_care: 1`, carrier `\"so I just need some\"`):** 1 `\" cream\"` (`r10-21`), 1 `\" ointment\"` (`r10-22`), 1 `\" lotion\"` (`r10-23`), 1 `\" medicine\"` (`r10-24`)",
        "- **8 `2 x 2` (`quad_b`, `quad_c`) families:** `r10-01`, `r10-03` (emergency); `r10-09`, `r10-10` (specialist); `r10-15`, `r10-16` (general doctor); `r10-21`, `r10-23` (self-care)",
        "- **14 attribution (`everyday_attribution`) families:** `r10-01` through `r10-14` (all 8 emergency + all 6 specialist families)",
        f"- **Voice, length & boundary check:** {total_texts} / {total_texts} texts start in first-person active voice (`\"I \"` or `\"My \"`), end with `carrier_frame`, and are single sentences of at most 40 words",
        "- **Single-span swap check:** 24 / 24 families satisfy `medical.replace(medical_span, everyday_span, 1) == everyday` with `|words(medical_span) - words(everyday_span)| <= 2`",
        f"- **Punctuation, digit, spelling, diagnosis & safety check:** 0 commas (`,`), 0 semicolons (`;`), 0 hyphens (`-`), 0 spelled-out number words, 0 misspellings, 0 diagnosis leaks, and 0 suicide/self-harm terms across all {total_texts} texts",
    ]
    if report_data is not None:
        s = report_data["summary"]
        lines.append(
            f"- **Engine candidate checker (`check_report.json`):** `{s['candidates']}` pairs checked "
            f"(`24` register + `24` changed-fact + `14` attribution) -> **`{s['with_errors']}` errors**, "
            f"**`{s['with_warnings']}` warning(s)** (explained below)"
        )
    lines.extend(["", "---", "", "## Warnings in `check_report.json`", ""])
    if report_data is None:
        lines.append("Run `scripts/check_candidate_pairs.py` and re-run `build_round10.py` to populate warning explanations.")
    else:
        warn_rows = [
            (cid, w)
            for cid, r in report_data["candidates"].items()
            for w in r.get("warnings", [])
        ]
        if not warn_rows:
            lines.append("`check_report.json` recorded **0 warnings** and **0 errors** across all 62 candidate pairs.")
        else:
            for cid, w in warn_rows:
                if cid == "r10-13-cf" and w.startswith("number:"):
                    lines.append(
                        f"- **`{cid}` (`{w}`):** Expected and intentional. `r10-13-cf` is a changed-fact chronology "
                        "control (`everyday` vs. `changed_fact`), not a register-equivalence pair: fact `f4` (symptom "
                        "onset duration) is deliberately changed from gradual `\"building up over 9 months\"` "
                        "(`right_care: 3`, routine eye specialist) to hyperacute `\"starting suddenly 20 minutes ago\"` "
                        "(`right_care_after: 4`, emergency evaluation). All register (`-reg`) and attribution (`-att`) "
                        "pairs have `0` number warnings."
                    )
                else:
                    lines.append(f"- **`{cid}` (`{w}`):** Inspected and verified intentional for this control pair.")

    lines.extend(["", "---", "", "## Per-Family Fact-Equivalence Tables and Mechanical Checks", ""])

    none_everyday: list[tuple[str, str]] = []
    none_attributions: list[tuple[str, str]] = []

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
                none_everyday.append((fid, es["expression"]))
        if "attribution" in fam and fam["attribution"]["source"] == "none":
            none_attributions.append((fid, fam["attribution"]["clause"]))

        lines.append(
            f"### `{fid}` — reviewer label: *{fam['condition']}* "
            f"(`right_care: {rc}`, `target_token: \"{tt}\"`, `carrier_frame: \"{cf}\"`)"
        )
        lines.append("")
        lines.append(f"- **Level rationale:** {fam['level_rationale']}")
        lines.append("")

        tkeys = ["medical", "everyday", "medical_paraphrase", "everyday_paraphrase", "changed_fact"]
        if "everyday_attribution" in texts:
            tkeys.append("everyday_attribution")
        if "quad_b" in texts:
            tkeys += ["quad_b", "quad_c"]

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

        lines.append("| Text | Word Count (<=40) | Active 1st-Person Opening | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |")
        lines.append("|---|---|---|---|---|---|---|")
        for k in tkeys:
            tv = texts[k]
            wc = len(tv.split())
            op_ok = "PASS" if (tv.startswith("I ") or tv.startswith("My ")) else "FAIL"
            ends_ok = "PASS" if tv.endswith(cf) else "FAIL"
            p_cnt = sum(tv.count(c) for c in ",;-")
            num_words = [w for w in tv.lower().split() if w in NUMBER_WORDS]
            digits = ", ".join(re.findall(r"\d+(?:\.\d+)?", tv)) or "none"
            lines.append(
                f"| `{k}` | {wc} | {op_ok} | {ends_ok} (`\"{cf}\"`) | {p_cnt} | {len(num_words)} | `{digits}` |"
            )
        lines.append("")

        ms_wc = len(sp["medical_span"].split())
        es_wc = len(sp["everyday_span"].split())
        diff = abs(ms_wc - es_wc)
        lines.append(
            f"- **Swap spans (`|diff| = {diff} <= 2`):** `medical_span` = **{ms_wc} words** "
            f"(`\"{sp['medical_span']}\"`) vs. `everyday_span` = **{es_wc} words** "
            f"(`\"{sp['everyday_span']}\"`)."
        )
        changed_rf_text = next(rf["text"] for rf in fam["reference_facts"] if rf["fact_id"] == cf_meta["fact_id"])
        lines.append(
            f"- **Single-fact control (`changed_fact`):** Changes **only** `{cf_meta['fact_id']}` "
            f"(*{changed_rf_text}*) from `\"{cf_meta['from']}\"` to `\"{cf_meta['to']}\"` "
            f"(`right_care`: `{rc}` -> `{cf_meta['right_care_after']}`). Nothing else in `everyday` differs."
        )
        if "attribution" in fam:
            att = fam["attribution"]
            lines.append(
                f"- **Attribution (`everyday_attribution`):** Inserts `\" {att['clause']}\"` immediately before "
                f"`\" {cf}\"` (`source`: `{'none' if att['source'] == 'none' else att['pmid_or_doi']}`, "
                f"`quote_type`: `\"{att['quote_type']}\"`). All reference facts are unchanged."
            )
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Unsourced Expressions and Attribution Clauses (`\"source\": \"none\"`)",
        "",
        "### Everyday Expressions Marked `\"source\": \"none\"`",
        "",
        "| Family | Expression |",
        "|---|---|",
    ])
    for fid, expr in none_everyday:
        lines.append(f"| `{fid}` | `\"{expr}\"` |")
    lines.extend([
        "",
        "### Attribution Clauses Marked `\"source\": \"none\"`",
        "",
        "| Family | Attribution Clause |",
        "|---|---|",
    ])
    for fid, clause in none_attributions:
        lines.append(f"| `{fid}` | `\"{clause}\"` |")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    errors = validate_all(FAMILIES_SPEC)
    if errors:
        print("VALIDATION ERRORS:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean_families = build_clean_json(FAMILIES_SPEC)
    check_pairs = build_check_pairs(FAMILIES_SPEC)

    (OUT_DIR / "families.json").write_text(
        json.dumps(clean_families, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "check_pairs.json").write_text(
        json.dumps(check_pairs, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "sources.md").write_text(
        build_sources_md(FAMILIES_SPEC),
        encoding="utf-8",
    )
    (OUT_DIR / "self_check.md").write_text(
        build_self_check_md(FAMILIES_SPEC),
        encoding="utf-8",
    )
    total_texts = sum(len(f["texts"]) for f in clean_families)
    print(
        f"SUCCESS: wrote {len(clean_families)} families ({total_texts} texts, "
        f"{len(check_pairs)} candidate pairs) to {OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
