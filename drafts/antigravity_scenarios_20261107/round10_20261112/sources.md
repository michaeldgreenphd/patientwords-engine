# Round 10 Sources (`round10_20261112`)

Every cited source in `families.json` (across both `everyday_sources` and `attribution`) is listed below with its `title`, `PMID` and `DOI` (or verified Wiktionary URL), `inspected_url`, what was directly opened (`access`: `full text` or `abstract only` — zero title-only sources), exact section/paragraph/sense `location`, `quote_type` (`"direct patient quote"`, `"authors' summary"`, or `"dictionary definition"`), exact verbatim `evidence`, and explicit `adaptation` separating the verbatim source text from how it was adapted into first-person scenario stimulus wording. No database identifiers other than `PMID` and `DOI` are used anywhere. Expressions and attribution clauses without a directly inspected source sentence are marked `"source": "none"` and catalogued in `self_check.md`.

## Scope and Provenance Disclaimers

- **Dictionary / Wiktionary lexical-sense scope:** Wiktionary and dictionary entries attest lexical senses and grammatical definitions only and do **NOT** establish demographic, regional-frequency, or community usage.
- **Synthetic test stimuli (not real patient records):** Source-inspired synthetic scenarios in `families.json` are test stimuli constructed for language-model evaluation, **NOT** real patient records; verbatim source excerpts (`evidence`) are recorded separately from first-person scenario adaptations (`adaptation`).

## 1. Kumar N, Patralekh MK, Jacob RV, Kumar S, Gowda MB (2026). Adolescent Cauda Equina Secondary to Traumatic Lumbar Disc Herniation: A Rare Case Report with Review of Literature. Journal of Orthopaedic Case Reports.

- **Title:** Adolescent Cauda Equina Secondary to Traumatic Lumbar Disc Herniation: A Rare Case Report with Review of Literature.
- **PMID / DOI / URL:** `PMID: 42597798; DOI: 10.13107/jocr.2026.v16.i08.7832`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42597798/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-01` (everyday expression `"low back pain"` — *authors' summary*)
    - **Location:** `Abstract — Case Report, para 1; Case Report, para 1`
    - **Verbatim `evidence`:** `A 13-year-old male child presented to us in the emergency department with complaints of low back pain, weakness, and urinary incontinence following lifting of a heavy weight 25 days back.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 2. Wang S, Shang J (2026). Cauda equina cavernous malformation with nerve fascicle involvement and chronic bowel and urinary urgency: a case report. Frontiers in Surgery.

- **Title:** Cauda equina cavernous malformation with nerve fascicle involvement and chronic bowel and urinary urgency: a case report.
- **PMID / DOI / URL:** `PMID: 42991049; DOI: 10.3389/fsurg.2026.2004471`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42991049/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-01` (everyday expression `"numbness of my left toes"` — *authors' summary*)
    - **Location:** `Case description, para 1 (and Abstract — Case Description, para 1)`
    - **Verbatim `evidence`:** `A 51-year-old woman was admitted with a four-year history of low back discomfort, numbness of the right fourth and fifth toes, and bowel and urinary urgency. ... Over subsequent years, urgency and right toe numbness increased, and occasional numbness developed in the left fourth and fifth toes.`
    - **Scenario `adaptation`:** `Synthesized first-person 'numbness of my left toes' from clinician third-person prose ('numbness of the right fourth and fifth toes' and 'occasional numbness developed in the left fourth and fifth toes').`

## 3. Jaunay LB, Ivanoff AS, Philippot C, Triby E, Pelaccia T (2026). How Patients' Inquiry Shapes Meaning in Primary Care Consultations: A Qualitative Study Using Own-Point-of-View Video-Stimulated Recall. Journal of Evaluation in Clinical Practice.

- **Title:** How Patients' Inquiry Shapes Meaning in Primary Care Consultations: A Qualitative Study Using Own-Point-of-View Video-Stimulated Recall.
- **PMID / DOI / URL:** `PMID: 42900758; DOI: 10.1111/jep.70653`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42900758/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-02` (everyday expression `"sore throat"` — *direct patient quote*)
    - **Location:** `Results — The Experience Prior to the Consultation — Identifying Problems as Disruptions in Usual Experience, para 3 (blockquote 3, P8)`
    - **Verbatim `evidence`:** `In fact, I really felt fatigue, the beginning of a sore throat, and my body, I could hardly control it anymore […] I spent really 48 h without sleeping… I was sweating a lot because the fever was going up, it was going down. (P8: Zoe, 18, student; acute febrile illness)`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-02` (everyday expression `"swollen glands"` — *authors' summary*)
    - **Location:** `Results — The Experience During the Consultation — Deciphering the Physician's Reasoning, para 4 (blockquote 5, GP consultation transcript)`
    - **Verbatim `evidence`:** `GP [consultation record]: Someone who has swollen glands, a persistent fever and is 18 years old, sometimes it's mononucleosis. It's a virus, you often catch it in adolescence. We drink from the same glass as someone… And that's going to give a sort of tonsillitis, sore throat, swollen glands, significant fatigue and a bit of a lingering fever.`
    - **Scenario `adaptation`:** `Spoken lay explanation by the general practitioner during a recorded consultation rather than patient speech; classified as 'authors' summary'.`

## 4. Torretta S, De Lucia G, Cavalera S, Cavaleri L, Battilocchi L (2026). Early recognition of life-threatening otolaryngologic complications in pediatric epstein-barr virus infectious mononucleosis: a systematic review and meta-analysis. Frontiers in Pediatrics.

- **Title:** Early recognition of life-threatening otolaryngologic complications in pediatric epstein-barr virus infectious mononucleosis: a systematic review and meta-analysis.
- **PMID / DOI / URL:** `PMID: 42923267; DOI: 10.3389/fped.2026.1980308`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42923267/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-02` (everyday expression `"drooling"` — *authors' summary*)
    - **Location:** `Introduction, para 2`
    - **Verbatim `evidence`:** `Consequently, progressive dysphagia, drooling, muffled voice, inspiratory stridor, increasing respiratory effort, and inability to maintain adequate oral intake should be regarded as clinically significant warning signs rather than expected manifestations of uncomplicated viral pharyngotonsillitis (3–5).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 5. Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'fall out'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'fall out'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/fall_out`
- **Inspected URL:** `https://en.wiktionary.org/wiki/fall_out`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-03` (everyday expression `"fell out"` — *dictionary definition*)
    - **Location:** `English — Verb, sense 5`
    - **Verbatim `evidence`:** `# {{lb|en|dialect|intransitive}} To [[pass out]].`
    - **Scenario `adaptation`:** `Past-tense inflection ('fell out') of verb lemma 'fall out'; Wiktionary entry attests lexical sense only and does not establish demographic or community usage.`

## 6. Mas C (2022). "Falling-Out" in Miami and the History of Culture in American Medicine. Bulletin of the History of Medicine.

- **Title:** "Falling-Out" in Miami and the History of Culture in American Medicine.
- **PMID / DOI / URL:** `PMID: 35370146; DOI: 10.1353/bhm.2022.0003`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/35370146/`
- **Access opened:** `abstract only`
- **Supported Round 10 items:**
  - `r10-03` (everyday expression `"falling out"` — *authors' summary*)
    - **Location:** `Abstract, para 1`
    - **Verbatim `evidence`:** `In the 1970s, after playing a leading role in the organization of medical anthropology, Hazel Weidman uncovered a condition that Miami residents called "falling-out."`
    - **Scenario `adaptation`:** `Omitted hyphen from verbatim 'falling-out' to satisfy single-sentence unpunctuated stimulus constraints.`

## 7. Nantanda R, Najjingo I, Kjaergaard J, Reventlow S, Ndekezi D, Ssemata AS, Østergaard MS (2026). Childhood asthma in Uganda: experiences of healthcare providers and caregivers in diagnosis and management. A FRESH AIR qualitative study. NPJ Primary Care Respiratory Medicine.

- **Title:** Childhood asthma in Uganda: experiences of healthcare providers and caregivers in diagnosis and management. A FRESH AIR qualitative study.
- **PMID / DOI / URL:** `PMID: 41714660; DOI: 10.1038/s41533-026-00493-7`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41714660/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-04` (everyday expression `"wet cough"` — *authors' summary*)
    - **Location:** `Results — Symptoms and triggers, para 1`
    - **Verbatim `evidence`:** `The episodes often started as a runny nose and an irritating dry or wet cough, mainly at night, associated with a sound in the chest and difficulty in breathing.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-04` (attribution clause `"and I think it is a common cold"` — *authors' summary*)
    - **Location:** `Results — Symptoms and triggers, para 1 & para 4`
    - **Verbatim `evidence`:** `Common triggers for the respiratory symptoms were cold weather and a common cold. ... According to HCWs, the most common triggers and causes of respiratory symptoms, as described by CGs, were cold weather, common colds, dust, overcrowding in homes, exposure to tobacco smoke, poor ventilation, malnutrition, and witchcraft.`
    - **Scenario `adaptation`:** `Framed authors' summary of caregiver-described respiratory triggers/causes ('a common cold' / 'common colds') into a first-person caregiver belief clause ('and I think it is a common cold').`
  - `r10-06` (everyday expression `"dry cough"` — *direct patient quote*)
    - **Location:** `Results — Diagnoses, blockquote 2 (CG 4)`
    - **Verbatim `evidence`:** `Initially they used to say that he had malaria, and it was causing the dry cough until he developed difficulty in breathing, and they diagnosed asthma at four years old (CG 4, Female).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 8. Liu F, Ling Y, Fan X, Cheng X, Chen Z, Zhu J (2026). Safety risk identification and family empowerment needs in home oxygen therapy for preterm infants with bronchopulmonary dysplasia: a qualitative study. BMJ Paediatrics Open.

- **Title:** Safety risk identification and family empowerment needs in home oxygen therapy for preterm infants with bronchopulmonary dysplasia: a qualitative study.
- **PMID / DOI / URL:** `PMID: 42957182; DOI: 10.1136/bmjpo-2026-005022`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42957182/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-04` (everyday expression `"her lips turned blue"` — *direct patient quote*)
    - **Location:** `Results — Gaps in caregiver preparedness and professional support for home oxygen care — Confusion regarding equipment maintenance and emergency management procedures, para 1 (C2)`
    - **Verbatim `evidence`:** `One mother said: “Once our child seemed to be breathing with effort and their lips turned a bit blue. We rushed them to the local maternity hospital, but the A&E said they didn’t handle neonatal emergencies and we'd have to queue. We had no choice but to drive to another hospital.” (C2)`
    - **Scenario `adaptation`:** `Adapted from verbatim mother quote 'their lips turned a bit blue' (C2) by replacing 'their' with 'her' and omitting hedge 'a bit' so severity matches 'acute labial cyanosis'.`

## 9. Abbas A, Jaradat M, Kmail H, Nairat S, Haj R, Jallad F, Qudaih O, Amro J, Diab B, Nazzal M (2026). An Unusual Cause of Melena: Adjacent Sigmoid Tubular Adenomas With Moderate Dysplasia-A Case Report. Clinical Case Reports.

- **Title:** An Unusual Cause of Melena: Adjacent Sigmoid Tubular Adenomas With Moderate Dysplasia-A Case Report.
- **PMID / DOI / URL:** `PMID: 42427814; DOI: 10.1002/ccr3.73138`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42427814/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-05` (everyday expression `"black tarry stools"` — *authors' summary*)
    - **Location:** `Case History/Examination — Chief Complaint (CC): Melena for 3 Days, para 1`
    - **Verbatim `evidence`:** `A 28‐year‐old female, previously in her usual state of good health, presented with a three‐day history of black, tarry stools.`
    - **Scenario `adaptation`:** `Omitted comma from 'black, tarry stools' to satisfy unpunctuated stimulus constraints (Discussion, para 2 of the same article also uses unpunctuated 'black tarry appearance').`

## 10. Banzett RBB, Sheridan AR, Baker KM, Lansing RW, Stevens JP (2020). 'Scared to death' dyspnoea from the hospitalised patient's perspective. BMJ Open Respiratory Research.

- **Title:** 'Scared to death' dyspnoea from the hospitalised patient's perspective.
- **PMID / DOI / URL:** `PMID: 32169831; DOI: 10.1136/bmjresp-2019-000493`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/32169831/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-06` (everyday expression `"not getting the air in"` — *direct patient quote*)
    - **Location:** `Results — Emotion related to dyspnoea, para 1 (1VC14)`
    - **Verbatim `evidence`:** `‘Breathing discomfort gets to a point where it feels like I can’t take another breath, feels very stressful and anxious’ (1VC-19); ‘Panicking, couldn’t get any air in. Scared the shit out of me’ (1VC-40); ‘scary, not getting the air in’ (1VC14).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-07` (everyday expression `"it feels like I can't take another breath"` — *direct patient quote*)
    - **Location:** `Results — Emotion related to dyspnoea, para 1 (1VC-19)`
    - **Verbatim `evidence`:** `‘Breathing discomfort gets to a point where it feels like I can’t take another breath, feels very stressful and anxious’ (1VC-19); ‘Panicking, couldn’t get any air in. Scared the shit out of me’ (1VC-40); ‘scary, not getting the air in’ (1VC14).`
    - **Scenario `adaptation`:** `Normalized curly apostrophe ('can’t' -> "can't") from verbatim hospitalised patient quote 'it feels like I can’t take another breath' (1VC-19).`

## 11. Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'smother'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'smother'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/smother`
- **Inspected URL:** `https://en.wiktionary.org/wiki/smother`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-06` (everyday expression `"smothering"` — *dictionary definition*)
    - **Location:** `English — Etymology 1, Verb, sense 7`
    - **Verbatim `evidence`:** `# {{lb|en|intransitive}} To [[breathe]] with great difficulty by reason of smoke, dust, close covering or wrapping, or the like.`
    - **Scenario `adaptation`:** `Present-participle inflection ('smothering') of verb lemma 'smother'; Wiktionary entry attests lexical sense only and does not establish demographic or community usage.`

## 12. Ferguson ON, Mitchell RA, Schaeffer MR, Ramsook AH, Dhillon SS, Dominelli PB, Molgat-Seon Y, Guenette JA (2023). Effects of Face Masks on the Multiple Dimensions and Neurophysiological Mechanisms of Exertional Dyspnea. Medicine and Science in Sports and Exercise.

- **Title:** Effects of Face Masks on the Multiple Dimensions and Neurophysiological Mechanisms of Exertional Dyspnea.
- **PMID / DOI / URL:** `PMID: 36469484; DOI: 10.1249/MSS.0000000000003074`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/36469484/`
- **Access opened:** `abstract only`
- **Supported Round 10 items:**
  - `r10-06` (everyday expression `"smothering"` — *authors' summary*)
    - **Location:** `Abstract — Results, para 1`
    - **Verbatim `evidence`:** `There were significant increases in the sensory quality of "smothering/air hunger" ( P = 0.01) and the emotional response of "anxiousness" ( P = 0.04) in the FM condition.`
    - **Scenario `adaptation`:** `Used 'smothering' inside first-person progressive clause ('I'm smothering at rest' / 'feel like I am smothering') adapted from descriptor label 'smothering/air hunger' in abstract.`

## 13. Jiao M, Wang W, Chen C, Zhang X, Zhao X (2025). Treatment Inertia Among Elderly Patients with Chronic Heart Failure: A Qualitative Study. Patient Preference and Adherence.

- **Title:** Treatment Inertia Among Elderly Patients with Chronic Heart Failure: A Qualitative Study.
- **PMID / DOI / URL:** `PMID: 41393075; DOI: 10.2147/PPA.S560907`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41393075/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-06` (attribution clause `"and I think I just have a cold"` — *direct patient quote*)
    - **Location:** `Results — Theme 1: Deficient Capability — Insufficient Symptom Perception, blockquote 2 (A12); Results — Table 4`
    - **Verbatim `evidence`:** `I initially thought I just had a cold and was feeling breathless, so I took cold medicine for a while, but it didn’t improve anything. When I couldn’t bear it anymore, I came to the hospital for a check-up. [A12]`
    - **Scenario `adaptation`:** `Shifted retrospective past-tense patient quote ('I initially thought I just had a cold' [A12]) into present-tense first-person attribution ('and I think I just have a cold').`
  - `r10-07` (everyday expression `"can't catch my breath"` — *direct patient quote*)
    - **Location:** `Results — Theme 1: Deficient Capability — Insufficient Symptom Perception, blockquote 3 (A14)`
    - **Verbatim `evidence`:** `At first, I couldn’t catch my breath, and even slight movements made me gasp for air. I thought I was just tired, so I rested for a while, but I still felt chest tightness and shortness of breath. I didn’t consider it to be related to heart disease at all. [A14]`
    - **Scenario `adaptation`:** `Shifted retrospective past-tense heart-failure patient quote ('couldn’t catch my breath' [A14]) to present-tense ASCII apostrophe ("can't catch my breath").`
  - `r10-07` (attribution clause `"and I think I am just tired"` — *direct patient quote*)
    - **Location:** `Results — Theme 1: Deficient Capability — Insufficient Symptom Perception, blockquote 3 (A14)`
    - **Verbatim `evidence`:** `At first, I couldn’t catch my breath, and even slight movements made me gasp for air. I thought I was just tired, so I rested for a while, but I still felt chest tightness and shortness of breath. I didn’t consider it to be related to heart disease at all. [A14]`
    - **Scenario `adaptation`:** `Shifted retrospective past-tense patient quote ('I thought I was just tired' [A14]) into present-tense first-person attribution ('and I think I am just tired').`

## 14. Opasrattanakon S, Jaraeprapal U, Punsawad C (2026). Self-care management in patients with heart failure in Nakhon Si Thammarat Province, Thailand: a descriptive qualitative study. Scientific Reports.

- **Title:** Self-care management in patients with heart failure in Nakhon Si Thammarat Province, Thailand: a descriptive qualitative study.
- **PMID / DOI / URL:** `PMID: 41839957; DOI: 10.1038/s41598-026-44071-w`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41839957/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-07` (everyday expression `"weight gain"` — *authors' summary*)
    - **Location:** `Results — Section 2.1 Physical sensations influence symptom monitoring and help guide self-management strategies, para 1`
    - **Verbatim `evidence`:** `Bodily sensations enable patients to recognize symptom changes early, supporting timely detection and effective HF management, such as shortness of breath, leg swelling, weight gain, orthopnea, and chest pain.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 15. Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'short-winded'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'short-winded'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/short-winded`
- **Inspected URL:** `https://en.wiktionary.org/wiki/short-winded`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-07` (everyday expression `"short winded"` — *dictionary definition*)
    - **Location:** `English — Adjective, sense 1`
    - **Verbatim `evidence`:** `# [[out of breath|Out of breath]], [[gasp]]ing for [[air]]; [[breathing]] [[rapidly]], or given to [[become|becoming]] [[short of breath]].`
    - **Scenario `adaptation`:** `Omitted hyphen from headword 'short-winded' to satisfy unpunctuated stimulus constraints; Wiktionary entry attests lexical sense only and does not establish demographic or community usage.`

## 16. Yamada R, Fuchigami T, Moriuchi Y (2026). A Pediatric Case of Urinary Retention Caused by Shingles on the Buttocks. Cureus.

- **Title:** A Pediatric Case of Urinary Retention Caused by Shingles on the Buttocks.
- **PMID / DOI / URL:** `PMID: 42591554; DOI: 10.7759/cureus.112547`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42591554/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-08` (everyday expression `"clusters of blisters"` — *authors' summary*)
    - **Location:** `Case presentation — Figure 1 caption`
    - **Verbatim `evidence`:** `(a) Clusters of blisters observed on the upper and right sides of the intergluteal cleft; (b) The bladder capacity before catheterization was 808 mL, and no obvious irregularities, wall thickening, or neoplastic lesions were observed.`
    - **Scenario `adaptation`:** `Lowercased caption-initial 'Clusters of blisters'.`

## 17. Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'misery'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'misery'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/misery`
- **Inspected URL:** `https://en.wiktionary.org/wiki/misery`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-08` (everyday expression `"a misery in his left chest"` — *dictionary definition*)
    - **Location:** `English — Noun, sense 2`
    - **Verbatim `evidence`:** `# {{lb|en|US|and|UK|dialects}} A [[bodily]] [[ache]] or [[pain]].`
    - **Scenario `adaptation`:** `Embedded dialect noun lemma 'misery' (bodily ache or pain) into caregiver phrase 'a misery in his left chest'; Wiktionary entry attests lexical sense only and does not establish demographic or community usage.`

## 18. Falcón-Flores JA, Jiménez-Corona ME, Rangel-Nieto IG, Vazquez-Duran M, Jiménez-Corona A (2026). Exploratory Evaluation of Self-Reported Periodontitis Among Adult Population From Comitán Chiapas, Mexico. Clinical and Experimental Dental Research.

- **Title:** Exploratory Evaluation of Self-Reported Periodontitis Among Adult Population From Comitán Chiapas, Mexico.
- **PMID / DOI / URL:** `PMID: 41517925; DOI: 10.1002/cre2.70274`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41517925/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-09` (everyday expression `"bleeding gums when brushing my teeth"` — *authors' summary*)
    - **Location:** `Materials and Methods — Periodontal Status by Self-Report, para 1 (item 2)`
    - **Verbatim `evidence`:** `(2) In the past year, have you had bleeding gums when brushing your teeth?`
    - **Scenario `adaptation`:** `Shifted second-person questionnaire item ('bleeding gums when brushing your teeth') to first-person ('bleeding gums when brushing my teeth').`

## 19. Velpula KP, Jacob E (2025). The stories of the ageing population in Luton, United Kingdom on their experience of periodontal diseases healthcare. Frontiers in Public Health.

- **Title:** The stories of the ageing population in Luton, United Kingdom on their experience of periodontal diseases healthcare.
- **PMID / DOI / URL:** `PMID: 41890769; DOI: 10.3389/fpubh.2025.1710973`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41890769/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-09` (everyday expression `"gum bleeding"` — *authors' summary*)
    - **Location:** `Results — Key findings — Limited awareness, para 1; Results — Table 3`
    - **Verbatim `evidence`:** `Participants exhibited low levels of awareness of the fact that periodontal disease is a preventable condition and tended to attribute such symptoms as gum bleeding or sensitivity to ageing.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-09` (attribution clause `"and I think it is just ageing"` — *authors' summary*)
    - **Location:** `Results — Key findings — Limited awareness, para 1`
    - **Verbatim `evidence`:** `Participants exhibited low levels of awareness of the fact that periodontal disease is a preventable condition and tended to attribute such symptoms as gum bleeding or sensitivity to ageing.`
    - **Scenario `adaptation`:** `Framed authors' thematic summary ('tended to attribute such symptoms as gum bleeding or sensitivity to ageing') into first-person belief clause ('and I think it is just ageing').`

## 20. Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and coping strategies of psoriasis patients in Malaysia. PLoS One.

- **Title:** Beyond the skin: Lived experiences and coping strategies of psoriasis patients in Malaysia.
- **PMID / DOI / URL:** `PMID: 41544022; DOI: 10.1371/journal.pone.0329066`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41544022/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-10` (everyday expression `"red patches"` — *authors' summary*)
    - **Location:** `Introduction, para 1`
    - **Verbatim `evidence`:** `Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-10` (everyday expression `"silvery scales"` — *authors' summary*)
    - **Location:** `Introduction, para 1`
    - **Verbatim `evidence`:** `Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-10` (everyday expression `"shedding flakes"` — *authors' summary*)
    - **Location:** `Results — Burden to others, para 2 (A14)`
    - **Verbatim `evidence`:** `One respondent shared that she felt burdened because her skin kept shedding flakes onto the office carpet.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 21. Boonkrong P, Khunboonjun K, Shakya S, Yang J, Vitoonmetha N, Chatchumni M (2026). A mixed-methods study of depressive-symptom severity among Thai university students and the underestimated role of social media. Frontiers in Child and Adolescent Psychiatry.

- **Title:** A mixed-methods study of depressive-symptom severity among Thai university students and the underestimated role of social media.
- **PMID / DOI / URL:** `PMID: 42959322; DOI: 10.3389/frcha.2026.1907727`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42959322/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-11` (everyday expression `"sleep disruption"` — *authors' summary*)
    - **Location:** `4 Results — 4.5 Qualitative subset findings, para 5`
    - **Verbatim `evidence`:** `At the same time, some participants described upward comparison, difficulty disengaging at night, sleep disruption, fatigue, and impaired concentration.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-11` (everyday expression `"fatigue"` — *authors' summary*)
    - **Location:** `4 Results — 4.5 Qualitative subset findings, para 5`
    - **Verbatim `evidence`:** `At the same time, some participants described upward comparison, difficulty disengaging at night, sleep disruption, fatigue, and impaired concentration.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-11` (everyday expression `"tiredness"` — *authors' summary*)
    - **Location:** `4 Results — 4.5 Qualitative subset findings, para 3`
    - **Verbatim `evidence`:** `Nighttime use was a more consistent concern among heavier users: late scrolling delayed sleep and was followed by tiredness, irritability, mental fog, or reduced concentration the next day.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 22. Melkevik O, Roberts N, Folke S (2026). Self-reported versus clinician-evaluated symptom assessment and diagnosis of ICD-11 PTSD and CPTSD: a comparison between the International Trauma Interview and the International Trauma Questionnaire. European Journal of Psychotraumatology.

- **Title:** Self-reported versus clinician-evaluated symptom assessment and diagnosis of ICD-11 PTSD and CPTSD: a comparison between the International Trauma Interview and the International Trauma Questionnaire.
- **PMID / DOI / URL:** `PMID: 41853968; DOI: 10.1080/20008066.2026.2635917`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41853968/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-12` (everyday expression `"flashbacks"` — *authors' summary*)
    - **Location:** `Method — Measures — The International Trauma Questionnaire, para 1 (also Table 2)`
    - **Verbatim `evidence`:** `The ITQ consists of six items measuring the three PTSD symptom clusters: re-experiencing symptoms (RE; flashbacks or nightmares), avoidance symptoms (AV; avoidance of internal or external reminders of the event), and sense of current threat (TH; hypervigilance or exaggerated startle response).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 23. Dixon TAM, Hole K, Johnson L, Nutbeam T (2026). Trapped and traumatised: a scoping review of the psychological sequelae of entrapment following motor vehicle collision. Scandinavian Journal of Trauma, Resuscitation and Emergency Medicine.

- **Title:** Trapped and traumatised: a scoping review of the psychological sequelae of entrapment following motor vehicle collision.
- **PMID / DOI / URL:** `PMID: 41612474; DOI: 10.1186/s13049-026-01558-9`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41612474/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-12` (everyday expression `"nightmares"` — *authors' summary*)
    - **Location:** `Results — Casualties’ experience of MVC-entrapment, para 1`
    - **Verbatim `evidence`:** `Other symptoms described following MVC-entrapment included nightmares, avoidance of reminders, heightened physiological arousal, and ongoing anxiety; in some cases meeting criteria for ASD or PTSD, as explored below.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-12` (everyday expression `"avoidance of reminders"` — *authors' summary*)
    - **Location:** `Results — Casualties’ experience of MVC-entrapment, para 1`
    - **Verbatim `evidence`:** `Other symptoms described following MVC-entrapment included nightmares, avoidance of reminders, heightened physiological arousal, and ongoing anxiety; in some cases meeting criteria for ASD or PTSD, as explored below.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 24. Wiktionary contributors (verified 2026-11-12). Entry 'black out'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'black out'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/black_out`
- **Inspected URL:** `https://en.wiktionary.org/wiki/black_out`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-12` (everyday expression `"blacking out"` — *dictionary definition*)
    - **Location:** `English — Verb, sense 3`
    - **Verbatim `evidence`:** `# {{lb|en|intransitive|idiomatic}} To [[lose]] [[consciousness]]; to suffer a [[blackout]].`
    - **Scenario `adaptation`:** `Present-participle inflection ('blacking out'; also past-tense 'blacked out' in changed_fact) of phrasal verb lemma 'black out'; Wiktionary entry attests lexical sense only and does not establish demographic or community usage.`

## 25. Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'blackout'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'blackout'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/blackout`
- **Inspected URL:** `https://en.wiktionary.org/wiki/blackout`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-12` (everyday expression `"blackouts"` — *dictionary definition*)
    - **Location:** `English — Noun, sense 1`
    - **Verbatim `evidence`:** `# A [[temporary]] [[loss]] of [[consciousness]].`
    - **Scenario `adaptation`:** `Plural inflection ('blackouts') of noun lemma 'blackout'; Wiktionary entry attests lexical sense only and does not establish demographic or community usage.`

## 26. Zavodni Z (2026). Visual Outcomes and Patient Satisfaction With a New Trifocal, Toric Intraocular Lens. Journal of Ophthalmology.

- **Title:** Visual Outcomes and Patient Satisfaction With a New Trifocal, Toric Intraocular Lens.
- **PMID / DOI / URL:** `PMID: 42471984; DOI: 10.1155/joph/9983329`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42471984/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-13` (everyday expression `"glare and halos"` — *authors' summary*)
    - **Location:** `3. Results, para 5; 4. Discussion, para 3`
    - **Verbatim `evidence`:** `Although 25% (n = 6) of patients reported glare or halos “Most of the time” (n = 5) or “Always” (n = 1), 50% (n = 12) of patients reported that they were bothered by glare and halos either “Rarely” or “Never.”`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 27. Coklar-Okutkan I, Harvey S, Doyle J, Teixeira F, Dinsmore J (2026). Illness Identity and Its Influence on Self-Management in Older Adults With Multimorbidity: A Hybrid Thematic Analysis. Qualitative Health Research.

- **Title:** Illness Identity and Its Influence on Self-Management in Older Adults With Multimorbidity: A Hybrid Thematic Analysis.
- **PMID / DOI / URL:** `PMID: 42549522; DOI: 10.1177/10497323261470629`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42549522/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-13` (attribution clause `"and I think it is part of getting older"` — *authors' summary*)
    - **Location:** `Results — Theme 5: Intersection of Illness Identity and Ageing — Subtheme 5.2: Perceiving Ageing and Chronic Conditions as Part of the Life Course, para 3`
    - **Verbatim `evidence`:** `Instead, decline is seen as an expected part of getting older rather than a break in life, so new limits can be taken on without threatening the person’s sense of who they are.`
    - **Scenario `adaptation`:** `Framed verbatim phrase 'part of getting older' from authors' thematic prose into a first-person belief clause ('and I think it is part of getting older').`

## 28. Drejza M, Nicholson LS, Paquette G, Chawla M, Vale CL, Rogozińska E, Moss N, Hutchinson-Pascal N, Al Wattar BH (2026). The Impact of Heavy Menstrual Bleeding on Quality of Life: A Mixed-Methods Survey Study. BJOG.

- **Title:** The Impact of Heavy Menstrual Bleeding on Quality of Life: A Mixed-Methods Survey Study.
- **PMID / DOI / URL:** `PMID: 42324234; DOI: 10.1111/1471-0528.70290`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42324234/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-14` (everyday expression `"heavy periods"` — *direct patient quote*)
    - **Location:** `3. Results — 3.4. Influence on Different Aspects of Health — 3.4.2. Mental Health, para 1 (P79)`
    - **Verbatim `evidence`:** `Several participants described diagnosed mental health conditions, with one reporting, ‘I have been diagnosed with PTSD due to my heavy periods, hemorrhages and endometriosis. This followed with crippling anxiety’ (P79).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 29. Taree NA, Rich R, Zhu N, Khalife R, Wu CM, Sun HWL (2026). Barriers and facilitators for management of iron-deficiency anemia in reproductive-aged women: perspectives of health care professionals in Alberta, Canada. CMAJ.

- **Title:** Barriers and facilitators for management of iron-deficiency anemia in reproductive-aged women: perspectives of health care professionals in Alberta, Canada.
- **PMID / DOI / URL:** `PMID: 42971550; DOI: 10.1503/cmaj.252102`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42971550/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-14` (attribution clause `"and I think heavy periods are normal for me"` — *authors' summary*)
    - **Location:** `Results — Patient-centred care — Sexism and normalization of suffering, para 1`
    - **Verbatim `evidence`:** `They reported that misogyny, lack of knowledge of normal versus abnormal menses, and the normalization of female suffering deter care-seeking and delay diagnosis (Table 3).`
    - **Scenario `adaptation`:** `Synthesized first-person patient belief clause ('and I think heavy periods are normal for me') from authors' summary of interviewed health care professionals' observations on 'lack of knowledge of normal versus abnormal menses, and the normalization of female suffering'.`

## 30. Coles T, Mkumba LS, Wright L, Godley FA, Collins TA, Jang DW (2025). Development of the Sinus Headache Screener to identify patients with non-rhinogenic facial pain compared with chronic rhinosinusitis in rhinology clinics. Journal of Patient-Reported Outcomes.

- **Title:** Development of the Sinus Headache Screener to identify patients with non-rhinogenic facial pain compared with chronic rhinosinusitis in rhinology clinics.
- **PMID / DOI / URL:** `PMID: 41196482; DOI: 10.1186/s41687-025-00956-4`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41196482/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-15` (everyday expression `"pain and pressure around the sinuses"` — *authors' summary*)
    - **Location:** `Introduction, para 1`
    - **Verbatim `evidence`:** `Many patients present with chronic or recurrent pain or pressure around the sinuses, often leading to a diagnosis of chronic rhinosinusitis (CRS).`
    - **Scenario `adaptation`:** `Changed 'pain or pressure around the sinuses' in source text to 'pain and pressure around the sinuses' ('or' -> 'and').`

## 31. Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic Management of Hypothyroidism: A Narrative Review of Reported Clinical Experience, Individualised Prescribing, and Research Gaps. Cureus.

- **Title:** Homoeopathic Management of Hypothyroidism: A Narrative Review of Reported Clinical Experience, Individualised Prescribing, and Research Gaps.
- **PMID / DOI / URL:** `PMID: 42800981; DOI: 10.7759/cureus.115269`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42800981/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-16` (everyday expression `"weight gain"` — *authors' summary*)
    - **Location:** `Introduction and background, para 1; Review, para 8`
    - **Verbatim `evidence`:** `Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-16` (everyday expression `"dry skin"` — *authors' summary*)
    - **Location:** `Introduction and background, para 1; Review, para 8`
    - **Verbatim `evidence`:** `Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-16` (everyday expression `"constipation"` — *authors' summary*)
    - **Location:** `Introduction and background, para 1; Review, para 8`
    - **Verbatim `evidence`:** `Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 32. Muse YH, Hassan MA, Ali M, Muse AH, Nadarajah S (2026). A pediatric case of measles with gastrointestinal complications in an urban hospital setting: A clinical and public health perspective. IDCases.

- **Title:** A pediatric case of measles with gastrointestinal complications in an urban hospital setting: A clinical and public health perspective.
- **PMID / DOI / URL:** `PMID: 42437059; DOI: 10.1016/j.idcr.2026.e02657`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42437059/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-17` (everyday expression `"red eyes"` — *authors' summary*)
    - **Location:** `Abstract — Case Presentation, para 1; Assessment and diagnosis, para 1`
    - **Verbatim `evidence`:** `A 4.5-year-old girl from an urban area presented with fever, vomiting, diarrhea, red eyes, and poor oral intake.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 33. Bogovič P, Jaklič M, Ogrinc K, Maraspin V, Rojko T, Nahtigal-Klevišar M, Ružić-Sabljić E, Wormser GP, Strle F (2026). Dynamics of Borrelial Antibodies in European Lyme Borreliosis Patients with Erythema Migrans. Medical Sciences.

- **Title:** Dynamics of Borrelial Antibodies in European Lyme Borreliosis Patients with Erythema Migrans.
- **PMID / DOI / URL:** `PMID: 42783436; DOI: 10.3390/medsci14050563`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42783436/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-19` (everyday expression `"tick bite"` — *authors' summary*)
    - **Location:** `2. Materials and Methods — 2.1. Definition of EM, para 1`
    - **Verbatim `evidence`:** `EM was defined as an expanding erythematous skin lesion, with or without central clearing, that developed days to a few weeks after a tick bite or exposure to ticks in an LB-endemic area and had a maximum diameter of ≥5 cm.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 34. Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'spell'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'spell'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/spell`
- **Inspected URL:** `https://en.wiktionary.org/wiki/spell`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-19` (everyday expression `"fainting spells"` — *dictionary definition*)
    - **Location:** `English — Etymology 3, Noun, sense 5`
    - **Verbatim `evidence`:** `# {{lb|en|colloquial|US}} A period of illness, or sudden interval of bad spirits, disease etc. {{defdate|from 19th c.}}`
    - **Scenario `adaptation`:** `Plural 'spells' of noun lemma 'spell' combined with modifier 'fainting' ('fainting spells' / 'fainting spell'); Wiktionary entry attests lexical sense only and does not establish demographic or community usage.`

## 35. Rana T, Kaeley N, Tejpal P, Yadav S, Mudi D (2025). Pulmonary Embolism Presenting as Recurrent Syncope and Visual Disturbances in a Patient With Protein C Deficiency: An Atypical Emergency Department Presentation. Cureus.

- **Title:** Pulmonary Embolism Presenting as Recurrent Syncope and Visual Disturbances in a Patient With Protein C Deficiency: An Atypical Emergency Department Presentation.
- **PMID / DOI / URL:** `PMID: 41573451; DOI: 10.7759/cureus.99743`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41573451/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-20` (everyday expression `"giddiness"` — *authors' summary*)
    - **Location:** `Abstract, para 1; Case presentation, para 1`
    - **Verbatim `evidence`:** `We describe a 41-year-old previously healthy man who presented with recurrent episodes of syncope, giddiness, and transient blurring of vision over five days.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 36. Kutlu O, Cetinkaya PO, Yavuz G, Khachemoune A (2025). Turkish Bath-Associated Infectious Dermatoses: A Comprehensive Review of Risk Factors, Clinical Manifestations, and Preventive Measures. Sisli Etfal Hastanesi Tip Bulteni.

- **Title:** Turkish Bath-Associated Infectious Dermatoses: A Comprehensive Review of Risk Factors, Clinical Manifestations, and Preventive Measures.
- **PMID / DOI / URL:** `PMID: 41700199; DOI: 10.14744/SEMB.2025.54782`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41700199/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-21` (everyday expression `"peeling"` — *authors' summary*)
    - **Location:** `Fungal Infections, para 1`
    - **Verbatim `evidence`:** `Tinea pedis manifests as either interdigital erythema with scaling, peeling, and maceration—especially between the fourth and fifth toes—hyperkeratotic thick scaly erythematous plaques on the soles, heels, and sides of the feet, or vesiculobullous intensely pruritic vesicles/bullae on an erythematous base.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 37. Alkhamis ZZ, Bhagchandani M, Idris M, Bhyat Y, Alsani SM, Pasha AI, Ali AHA, Ali Eledresi D, Mahdi AA, Almohamedhusain FR (2026). Clinical Effectiveness of Barrier Preparations in the Management of Diaper Dermatitis: A Systematic Review and Meta-Analysis. Cureus.

- **Title:** Clinical Effectiveness of Barrier Preparations in the Management of Diaper Dermatitis: A Systematic Review and Meta-Analysis.
- **PMID / DOI / URL:** `PMID: 41769510; DOI: 10.7759/cureus.102379`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41769510/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-22` (everyday expression `"diaper area"` — *authors' summary*)
    - **Location:** `Introduction and background, para 1`
    - **Verbatim `evidence`:** `Diaper dermatitis (DD) is a broad term used to describe the acute inflammatory skin response caused by irritation from urine, feces, moisture, or friction in the diaper area of infants and children.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 38. Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehensive Evaluation of Body Lotion in Alleviating Xerosis: A Multi-Omics Approach to Lipid Metabolism and Microbial Community Modulation. Journal of Cosmetic Dermatology.

- **Title:** Comprehensive Evaluation of Body Lotion in Alleviating Xerosis: A Multi-Omics Approach to Lipid Metabolism and Microbial Community Modulation.
- **PMID / DOI / URL:** `PMID: 41622615; DOI: 10.1111/jocd.70711`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41622615/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-23` (everyday expression `"dry skin"` — *authors' summary*)
    - **Location:** `Abstract — Conclusion, para 1; Introduction, para 3`
    - **Verbatim `evidence`:** `This multi‐omics insight provides a foundation for the targeted management of dry skin.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-23` (everyday expression `"flakiness"` — *authors' summary*)
    - **Location:** `Discussion, para 1`
    - **Verbatim `evidence`:** `Dry skin, marked by flakiness and a rough texture, is a key contributor to various skin issues, primarily caused by a compromised skin barrier that results in moisture loss [23].`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-23` (everyday expression `"itching"` — *authors' summary*)
    - **Location:** `Abstract — Background, para 1`
    - **Verbatim `evidence`:** `Xerosis, marked by a compromised skin barrier and disrupted lipid metabolism, leads to dryness, scaling, and itching.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-23` (everyday expression `"shins"` — *authors' summary*)
    - **Location:** `Introduction, para 1`
    - **Verbatim `evidence`:** `Xerosis predominantly manifests on the lower extremities, particularly the shins and calves, where the density of sebaceous glands is minimal and transepidermal water loss is pronounced [3].`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 39. Opadokun A, Mikhail E, Chong LX, Suphioğlu C, Gokhale M, Azizoğlu S (2026). The Impact of Allergic Rhinitis on Australian Adults in an Urban Setting: A Qualitative Exploration. Journal of Clinical Medicine.

- **Title:** The Impact of Allergic Rhinitis on Australian Adults in an Urban Setting: A Qualitative Exploration.
- **PMID / DOI / URL:** `PMID: 42796056; DOI: 10.3390/jcm15187284`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/42796056/`
- **Access opened:** `full text`
- **Supported Round 10 items:**
  - `r10-24` (everyday expression `"my nose starts running"` — *direct patient quote*)
    - **Location:** `3. Results — 3.2. Themes — 3.2.2. Theme 2: Environmental Exposures and Seasonal Changes Strongly Influence the Experience of Allergic Rhinitis Patients — Main Triggers, para 1 (P9)`
    - **Verbatim `evidence`:** `Pollen emerged as a widely recognised trigger, particularly during spring: “When the wind picks up in spring, I can feel it instantly; my nose starts running, and I can’t stop sneezing” (P9).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-24` (everyday expression `"sneezing"` — *direct patient quote*)
    - **Location:** `3. Results — 3.2. Themes — 3.2.2. Theme 2: Environmental Exposures and Seasonal Changes Strongly Influence the Experience of Allergic Rhinitis Patients — Main Triggers, para 1 (P9)`
    - **Verbatim `evidence`:** `Pollen emerged as a widely recognised trigger, particularly during spring: “When the wind picks up in spring, I can feel it instantly; my nose starts running, and I can’t stop sneezing” (P9).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r10-24` (everyday expression `"itchy and watery eyes"` — *authors' summary*)
    - **Location:** `3. Results — 3.2. Themes — 3.2.1. Theme 1: Allergic Rhinitis Is Shaped by Onset, Family History and Comorbidities — Symptom Patterns, para 1`
    - **Verbatim `evidence`:** `Participants reported a wide range of symptoms including nasal congestion, sneezing, itchy and watery eyes, headaches and fatigue.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

---

## Verified Research Leads Retained for Future Rounds

The three qualitative full-text leads below were directly opened and audited during Round 10 verification (`PMID` and `DOI` only; zero `PMC` or other database IDs). Two verbatim breathlessness quotes from **Banzett et al. (2020)** (`1VC14` and `1VC-19`) were integrated into `r10-06` and `r10-07` above; all remaining verified excerpts from **Pattenden et al. (2002)**, **Banzett et al. (2020)**, and **Berman et al. (2017)** are preserved below for future rounds rather than borrowed across clinically mismatched conditions.

### Lead A — Pattenden et al. (2002): Pattenden J, Watt I, Lewin RJP, Stanford N (2002). Decision making processes in people with symptoms of acute myocardial infarction: qualitative study. BMJ.

- **Title:** Decision making processes in people with symptoms of acute myocardial infarction: qualitative study.
- **PMID / DOI:** `PMID: 11976241; DOI: 10.1136/bmj.324.7344.1006`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/11976241/`
- **Access opened:** `full text`
- **Round 10 fit & retention rationale:** Full text verified; no Round 9 overlap (Round 9 r9-01 was cardiogenic syncope, not acute myocardial infarction). Retained for future rounds rather than cross-citing onto r10-05 (NSAID-associated melena) or replacing an emergency family, because multi-cue acute ischemic chest pain at rest still warrants emergency care when any single symptom cue (such as diaphoresis) is flipped, whereas r10-05 provides an unambiguous single-fact stool-color boundary (4 -> 2). Full-text negative check: does not contain 'muscle strain' or 'tiredness'/'tired'.
- **Verified excerpts retained:**
  - **Theme / phrase:** `indigestion / mild pain and breathlessness / normalising or minimising of symptoms` (*authors' summary*)
    - **Location:** `Results — Appraisal of symptoms, para 1`
    - **Exact `original_excerpt`:** `Instead of being “crushing chest pain,” many heart attacks were reported to have had a slow onset with only mild pain and breathlessness. Many participants were confused by the fact that their symptoms were similar to angina or indigestion; many had experienced prodromal symptoms in the previous few days, which led to a normalising or minimising of symptoms`
  - **Theme / phrase:** `heartburn or indigestion / heartburny thing / slight chest pain` (*direct patient quote*)
    - **Location:** `Results — Box 2 (Appraisal of symptoms), Patient 14`
    - **Exact `original_excerpt`:** `…and I had a slight chest pain. I didn't think too much of it because actually I had eaten some chips and I thought these chips had stuck in my chest, and you know, often when you get that sort of heartburny thing. … I thought this can't be heartburn or indigestion or something, as those are the first things you think of obviously.`
  - **Theme / phrase:** `pain or breathlessness became unbearable` (*authors' summary*)
    - **Location:** `Results — Perceived risk of acute myocardial infarction, para 1`
    - **Exact `original_excerpt`:** `Many of those who did not perceive themselves to be at risk reported taking longer to appraise symptoms and acted only when the pain or breathlessness became unbearable.`
  - **Theme / phrase:** `severe pain in left arm and left side` (*authors' summary*)
    - **Location:** `Results — Box 3 (Perceived risk), Patient 11`
    - **Exact `original_excerpt`:** `Had severe pain in left arm and left side. Previous heart attack had involved central chest pain. He didn't think it could be another one.`
  - **Theme / phrase:** `right across my chest / thought it was flatulence` (*direct patient quote*)
    - **Location:** `Results — Box 4 (Previous experience), Patient 16`
    - **Exact `original_excerpt`:** `It was right across my chest. You see the last time I had a heart attack I was full of . . . well I thought it was flatulence. I was trying to, burp you might say, almost continuously and this pain was nothing like that in that respect and that's why I thought, well, it's not a heart attack.`
  - **Theme / phrase:** `might just go away` (*direct patient quote*)
    - **Location:** `Results — Psychological factors and emotional response, para 1 & Box 5, Patient 21`
    - **Exact `original_excerpt`:** `perhaps if I pretend it is not a heart attack, it might just go away`

### Lead B — Banzett et al. (2020) [Additional Unused Excerpts]: Banzett RBB, Sheridan AR, Baker KM, Lansing RW, Stevens JP (2020). 'Scared to death' dyspnoea from the hospitalised patient's perspective. BMJ Open Respiratory Research.

- **Title:** 'Scared to death' dyspnoea from the hospitalised patient's perspective.
- **PMID / DOI:** `PMID: 32169831; DOI: 10.1136/bmjresp-2019-000493`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/32169831/`
- **Access opened:** `full text`
- **Round 10 fit & retention rationale:** Participant quotes 1VC14 ('not getting the air in') and 1VC-19 ('feels like I can’t take another breath') were integrated into r10-06 and r10-07 (replacing title-only Hardy 2025 alongside full-text Jiao 2025 A14). Remaining verified full-text quotes below are retained for future rounds. Full-text negative check: does not contain 'smothering' or 'can't catch my breath'.
- **Verified excerpts retained:**
  - **Theme / phrase:** `air hunger / Wish I had more air / Not being able to get air` (*direct patient quote*)
    - **Location:** `Results — Sensory experience of dyspnoea, para 1 (1VC-22, 1VC-38, 1VC-79)`
    - **Exact `original_excerpt`:** `‘Wish I had more air’ (1VC-22); ‘Not being able to get air is the worst thing that could ever happen to you. Air is everything’ (1VC-38); ‘Didn’t feel like I was getting air, but I was’ (1VC-79).`
  - **Theme / phrase:** `couldn't get any air in` (*direct patient quote*)
    - **Location:** `Results — Emotion related to dyspnoea, para 1 (1VC-40)`
    - **Exact `original_excerpt`:** `‘Panicking, couldn’t get any air in. Scared the shit out of me’ (1VC-40)`
  - **Theme / phrase:** `you have to stay very still to get enough air (dyspnoea at rest)` (*direct patient quote*)
    - **Location:** `Results — Precipitating events and managing dyspnoea, para 1 (1VC-8)`
    - **Exact `original_excerpt`:** `‘It's that you have to stay very still to get enough air’ (1VC-8).`
  - **Theme / phrase:** `Can't breathe because I am coughing a lot` (*direct patient quote*)
    - **Location:** `Results — Symptoms that exacerbated dyspnoea, para 1 (1VC-153)`
    - **Exact `original_excerpt`:** `‘Can’t breathe because I am coughing a lot’ (1VC-153).`

### Lead C — Berman et al. (2017): Berman N, Jones MM, De Coster DA (2017). 'Just like a normal pain', what do people with diabetes mellitus experience when having a myocardial infarction: a qualitative study recruited from UK hospitals. BMJ Open.

- **Title:** 'Just like a normal pain', what do people with diabetes mellitus experience when having a myocardial infarction: a qualitative study recruited from UK hospitals.
- **PMID / DOI:** `PMID: 28918410; DOI: 10.1136/bmjopen-2016-015736`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/28918410/`
- **Access opened:** `full text`
- **Round 10 fit & retention rationale:** Full text verified; no pediatric DKA overlap with Round 9 r9-07 (Berman 2017 studies UK adults aged 40-90 with diabetes experiencing acute myocardial infarction). Retained for future adult diabetes or acute coronary families rather than borrowing across unrelated Round 10 conditions.
- **Verified excerpts retained:**
  - **Theme / phrase:** `tight chest / started sweating / I can't breathe / I'm short of breath` (*direct patient quote*)
    - **Location:** `Results — Symptoms — Typical versus atypical presentations, para 4 (P11), para 9 (P14), para 10 (P35)`
    - **Exact `original_excerpt`:** `…like a tight chest just really tight, like someone is squeezing it inside…but then I went really pale and started sweating… (P11) / I can’t breathe… (P14) / Like somebody’s pushing me…and I’m short of breath and then it was getting worse and it start burning. (P35)`
  - **Theme / phrase:** `lethargy / I was just so weak` (*direct patient quote*)
    - **Location:** `Results — Symptoms — Atypical pain, para 10 & para 11 (P10)`
    - **Exact `original_excerpt`:** `It’s just the sheer um lethargy really, I just couldn’t do anything…I was just so weak. (P10)`
  - **Theme / phrase:** `mistook it for being indigestion / put it down to nerves or exercise` (*direct patient quote*)
    - **Location:** `Results — Attribution and consequences — Attributing symptoms to comorbidities, para 1 & para 2 (P31)`
    - **Exact `original_excerpt`:** `when you feel bloated and gassy and it’s similar to that sort of pain. That’s why I mistook it for being indigestion…. I put it down to nerves or exercise… (P31)`
  - **Theme / phrase:** `symptoms attributed to asthma, muscular aches, panic attacks, stress, and diabetes` (*authors' summary*)
    - **Location:** `Results — Attribution and consequences — Attributing symptoms to comorbidities, para 4`
    - **Exact `original_excerpt`:** `During evolving MI, patients were often dynamic in their interpretation of symptoms, and symptoms were attributed to other causes that included asthma, muscular aches, panic attacks, stress and, importantly in this group, their DM.`
  - **Theme / phrase:** `dizzy, tired / dizzy turns attributed to diabetes` (*direct patient quote*)
    - **Location:** `Results — Attribution and consequences — Ascribing symptoms to DM, para 3 (P17) & para 5 (P3)`
    - **Exact `original_excerpt`:** `Well dizzy, tired, again I’m dizzy all the time with diabetes, you get that, that’s part and parcel of being diabetic. (P17) / Not fainting, but you know dizzy turns, because I do get these dizzy turns. You see, this is all in with the diabetes you see. (P3)`
  - **Theme / phrase:** `initially thought it was low blood sugar / might be a hypo` (*direct patient quote*)
    - **Location:** `Results — Attribution and consequences — Ascribing symptoms to hypoglycaemia, para 2 (P2) & para 3 (P11)`
    - **Exact `original_excerpt`:** `because I am diabetic, right, um, I thought, initially I thought it was um low blood sugar. (P2.) / …I thought that it might be a hypo at the time. (P11)`
