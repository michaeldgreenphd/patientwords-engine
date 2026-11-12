# Review packet: batch r10_20261112

Source: draft/antigravity-scenarios-20261107@c75a8e757:drafts/antigravity_scenarios_20261107/round10_20261112/families.json (SHA-256 `21b742255ef341ac68d6e2797a472931f96d239f656c848884edf398724a6ebb`).

Design rules: `data/experiments/intake_design.v1.json` (`6f033e45e641`). Status of those rules: draft, 2026-11-12: proposed by the batch-intake change; not agreed. The owner agrees it by a commit that changes this line.

What has and has not been reviewed:

- **Software validation: passed** (0 errors, 2 warnings). These are structural checks by this command. It says nothing about clinical content or patient language.
- **Owner's read:** 24 not read. This is the owner's keep or exclude decision on a named version of the texts. It is not a clinician's review.
- **Domain review:** 24 domain review pending. A family is reviewed only when a clinician and a patient-language reviewer have both recorded their items; nothing in this packet does that.

No model output appears in this packet.

Measured endpoint, when measured: the full-vocabulary probability of the first token of the family's declared target word at the position after the carrier phrase. It is not triage accuracy, the quality of an answer, evidence that a model understands a wording.

- Care tiers are not compared with each other: families at different tiers use different carrier phrases and target words, so their endpoints are probabilities of different tokens in different contexts.
- Strata are not pooled: a register contrast, a patient-explanation contrast and a syntax crossing are different manipulations.

## r10-01

Care level 4 · ends on "so I need to go to the" + "ER" · split unassigned · register stratum `register`

Label for reviewers only, in no text: cauda equina syndrome

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Lifted a heavy box 4 days ago
- `f2` Low back pain radiating down the left leg
- `f3` Numbness in the left toes
- `f4` Unable to urinate today

| Wording | Text |
|---|---|
| medical | I lifted a heavy box 4 days ago and developed left lumbar radiculopathy accompanied by left pedal paresthesia and urinary retention today so I need to go to the |
| everyday | I lifted a heavy box 4 days ago and got low back pain down my left leg with numb toes and cannot pee today so I need to go to the |
| medical_paraphrase | I lifted a heavy crate 4 days ago and experienced left lower limb radicular back pain with left toe paresthesia and acute urinary retention today so I need to go to the |
| everyday_paraphrase | I picked up a heavy box 4 days ago and got low back pain running down my left leg with numbness of my left toes and cannot pee today so I need to go to the |
| changed_fact | I lifted a heavy box 4 days ago and got low back pain down my left leg with numb toes and can pee normally today so I need to go to the |
| everyday_attribution | I lifted a heavy box 4 days ago and got low back pain down my left leg with numb toes and cannot pee today and I think I pulled a muscle so I need to go to the |
| quad_b | I lifted a heavy box 4 days ago and got left lumbar radiculopathy with left pedal paresthesia and urinary retention today so I need to go to the |
| quad_c | I lifted a heavy box 4 days ago and developed low back pain down my left leg accompanied by numb toes and inability to pee today so I need to go to the |

Changed fact `f4`: "and cannot pee today" became "and can pee normally today"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think I pulled a muscle"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| low back pain | authors' summary | Kumar N, Patralekh MK, Jacob RV, Kumar S, Gowda MB (2026). Adolescent Cauda Equina Seconda PMID: 42597798; DOI: 10.13107/jocr.2026.v16.i08.7832 | A 13-year-old male child presented to us in the emergency department with complaints of low back pain, weakness, and urinary incontinence following lifting of a heavy weight 25 days back. |
| numbness of my left toes | authors' summary | Wang S, Shang J (2026). Cauda equina cavernous malformation with nerve fascicle involvemen PMID: 42991049; DOI: 10.3389/fsurg.2026.2004471 | A 51-year-old woman was admitted with a four-year history of low back discomfort, numbness of the right fourth and fifth toes, and bowel and urinary urgency. |
| down my left leg | no source |   |  |
| numb toes | no source |   |  |
| cannot pee | no source |   |  |

Software findings: none.

## r10-02

Care level 4 · ends on "so I need to go to the" + "ER" · split unassigned · register stratum `register`

Label for reviewers only, in no text: acute febrile pharyngitis with drooling and dysphagia

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 3 days of sore throat and swollen neck glands
- `f2` Fever of 39 C
- `f3` Unable to swallow saliva and drooling today

| Wording | Text |
|---|---|
| medical | I have had 3 days of pharyngitis and cervical lymphadenopathy with a 39 C fever and developed aphagia for saliva with sialorrhea today so I need to go to the |
| everyday | I have had 3 days of a sore throat and swollen glands with a 39 C fever and cannot swallow spit with drooling today so I need to go to the |
| medical_paraphrase | I experienced 3 days of pharyngeal pain and tender cervical lymphadenopathy with a 39 C pyrexia and inability to swallow secretions with sialorrhea today so I need to go to the |
| everyday_paraphrase | I had 3 days of throat pain and swollen neck glands with a 39 C fever and started drooling because I cannot swallow spit today so I need to go to the |
| changed_fact | I have had 3 days of a sore throat and swollen glands with a 39 C fever and swallow liquids easily without drooling today so I need to go to the |
| everyday_attribution | I have had 3 days of a sore throat and swollen glands with a 39 C fever and cannot swallow spit with drooling today and I think it is a throat virus so I need to go to the |

Changed fact `f3`: "and cannot swallow spit with drooling today" became "and swallow liquids easily without drooling today"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think it is a throat virus"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| sore throat | authors' summary | Jaunay LB, Ivanoff AS, Philippot C, Triby E, Pelaccia T (2026). How Patients' Inquiry Shap PMID: 42900758; DOI: 10.1111/jep.70653 | And that's going to give a sort of tonsillitis, sore throat, swollen glands, significant fatigue and a bit of a lingering fever. |
| swollen glands | authors' summary | Jaunay LB, Ivanoff AS, Philippot C, Triby E, Pelaccia T (2026). How Patients' Inquiry Shap PMID: 42900758; DOI: 10.1111/jep.70653 | And that's going to give a sort of tonsillitis, sore throat, swollen glands, significant fatigue and a bit of a lingering fever. |
| drooling | authors' summary | Torretta S, De Lucia G, Cavalera S, Cavaleri L, Battilocchi L (2026). Early recognition of PMID: 42923267; DOI: 10.3389/fped.2026.1980308 | Consequently, progressive dysphagia, drooling, muffled voice, inspiratory stridor, increasing respiratory effort, and inability to maintain adequate oral intake should be regarded as clinically significant warning signs rather than expected manifestations of uncomplicated viral pharyngotonsillitis (3–5). |
| cannot swallow spit | no source |   |  |

Software findings: none.

## r10-03

Care level 4 · ends on "so I need to go to the" + "hospital" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: spreading lower limb skin infection with syncope

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Patient is 68 years old
- `f2` 3 days of expanding warm red swelling on the right calf
- `f3` Fever of 39 C
- `f4` Fainted upon standing today

| Wording | Text |
|---|---|
| medical | I am 68 with 3 days of expanding warm right calf erythema and edema accompanied by a 39 C fever followed by orthostatic syncope standing today so I need to go to the |
| everyday | I am 68 with 3 days of spreading hot red right calf swelling with a 39 C fever and then fell out standing today so I need to go to the |
| medical_paraphrase | I am 68 years old with 3 days of progressive right calf erythema warmth and edema plus a 39 C pyrexia complicated by syncope on standing today so I need to go to the |
| everyday_paraphrase | I am 68 years old with 3 days of hot red swelling spreading on my right calf and a 39 C fever before falling out standing today so I need to go to the |
| changed_fact | I am 68 with 3 days of spreading hot red right calf swelling with a 39 C fever without fainting when standing today so I need to go to the |
| everyday_attribution | I am 68 with 3 days of spreading hot red right calf swelling with a 39 C fever and then fell out standing today and I think it is a bug bite so I need to go to the |
| quad_b | I am 68 with 3 days of expanding warm right calf erythema and edema with a 39 C fever and then orthostatic syncope standing today so I need to go to the |
| quad_c | I am 68 with 3 days of spreading hot red right calf swelling accompanied by a 39 C fever followed by falling out standing today so I need to go to the |

Changed fact `f4`: "and then fell out standing today" became "without fainting when standing today"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think it is a bug bite"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| fell out | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'fal https://en.wiktionary.org/wiki/fall_out | # {{lb|en|dialect|intransitive}} To [[pass out]]. |
| falling out | authors' summary | Mas C (2022). "Falling-Out" in Miami and the History of Culture in American Medicine. Bull PMID: 35370146; DOI: 10.1353/bhm.2022.0003 | In the 1970s, after playing a leading role in the organization of medical anthropology, Hazel Weidman uncovered a condition that Miami residents called "falling-out." |
| spreading hot red right calf swelling | no source |   |  |

Software findings: none.

## r10-04

Care level 4 · ends on "so I need to go to the" + "ER" · split unassigned · register stratum `register`

Label for reviewers only, in no text: pediatric febrile lower respiratory infection with cyanosis

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Child is 5 years old
- `f2` 4 days of wet productive cough and 39 C fever
- `f3` Chest pain on coughing
- `f4` Lips turned blue today

| Wording | Text |
|---|---|
| medical | My 5 year old daughter has 4 days of productive cough and 39 C fever with pleuritic chest pain and labial cyanosis today so I need to go to the |
| everyday | My 5 year old daughter has 4 days of wet cough and 39 C fever with chest pain coughing and her lips turned blue today so I need to go to the |
| medical_paraphrase | My 5 year old child developed 4 days of productive tussis and 39 C pyrexia accompanied by pleuritic chest pain and perioral cyanosis today so I need to go to the |
| everyday_paraphrase | My 5 year old girl spent 4 days with wet cough and 39 C fever plus chest pain when coughing and her lips turned blue today so I need to go to the |
| changed_fact | My 5 year old daughter has 4 days of wet cough and 39 C fever with chest pain coughing and her lips stayed pink today so I need to go to the |
| everyday_attribution | My 5 year old daughter has 4 days of wet cough and 39 C fever with chest pain coughing and her lips turned blue today and I think it is a common cold so I need to go to the |

Changed fact `f4`: "and her lips turned blue today" became "and her lips stayed pink today"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think it is a common cold"; source: Nantanda R, Najjingo I, Kjaergaard J, Reventlow S, Ndekezi D, Ssemata AS, Østergaard MS (2026). Childhood asthma in Uganda: experiences of healthcare providers and caregivers in diagnosis and management. A FRESH AIR qualitative study. NPJ Primary Care Respiratory Medicine. (authors' summary).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| wet cough | authors' summary | Nantanda R, Najjingo I, Kjaergaard J, Reventlow S, Ndekezi D, Ssemata AS, Østergaard MS (2 PMID: 41714660; DOI: 10.1038/s41533-026-00493-7 | The episodes often started as a runny nose and an irritating dry or wet cough, mainly at night, associated with a sound in the chest and difficulty in breathing. |
| her lips turned blue | direct patient quote | Liu F, Ling Y, Fan X, Cheng X, Chen Z, Zhu J (2026). Safety risk identification and family PMID: 42957182; DOI: 10.1136/bmjpo-2026-005022 | One mother said: “Once our child seemed to be breathing with effort and their lips turned a bit blue. |
| chest pain coughing | no source |   |  |
| chest pain when coughing | no source |   |  |

Software findings: none.

## r10-05

Care level 4 · ends on "so I need to go to the" + "hospital" · split unassigned · register stratum `register`

Label for reviewers only, in no text: acute upper gastrointestinal bleeding

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Taking daily ibuprofen for 3 weeks
- `f2` 4 days of burning upper abdominal pain
- `f3` Passed black tarry stools 2 times today

| Wording | Text |
|---|---|
| medical | I took daily ibuprofen for 3 weeks and developed 4 days of burning epigastric pain and passed melenic stools 2 times today so I need to go to the |
| everyday | I took daily ibuprofen for 3 weeks and got 4 days of burning upper stomach pain and passed black tarry stools 2 times today so I need to go to the |
| medical_paraphrase | I used daily oral ibuprofen over 3 weeks and experienced 4 days of burning epigastric discomfort plus melena 2 times today so I need to go to the |
| everyday_paraphrase | I took ibuprofen every day for 3 weeks and had 4 days of burning high stomach pain and black tarry stools 2 times today so I need to go to the |
| changed_fact | I took daily ibuprofen for 3 weeks and got 4 days of burning upper stomach pain and passed normal brown stools 2 times today so I need to go to the |
| everyday_attribution | I took daily ibuprofen for 3 weeks and got 4 days of burning upper stomach pain and passed black tarry stools 2 times today and I think it is just indigestion so I need to go to the |

Changed fact `f3`: "and passed black tarry stools 2 times today" became "and passed normal brown stools 2 times today"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think it is just indigestion"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| black tarry stools | authors' summary | Abbas A, Jaradat M, Kmail H, Nairat S, Haj R, Jallad F, Qudaih O, Amro J, Diab B, Nazzal M PMID: 42427814; DOI: 10.1002/ccr3.73138 | A 28‐year‐old female, previously in her usual state of good health, presented with a three‐day history of black, tarry stools. |
| burning upper stomach pain | no source |   |  |
| burning high stomach pain | no source |   |  |

Software findings: none.

## r10-06

Care level 4 · ends on "so I need to go to the" + "hospital" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: acute febrile respiratory illness with resting dyspnea in pregnancy

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Currently 31 weeks pregnant
- `f2` 3 days of dry cough and 39 C fever
- `f3` Severe difficulty getting air at rest tonight

| Wording | Text |
|---|---|
| medical | I am 31 weeks pregnant with 3 days of nonproductive cough and a 39 C fever plus resting air hunger and dyspnea tonight so I need to go to the |
| everyday | I am 31 weeks pregnant with 3 days of a dry cough and a 39 C fever and I'm smothering at rest tonight so I need to go to the |
| medical_paraphrase | I am at 31 weeks gestation with 3 days of dry tussis and a 39 C pyrexia complicated by resting dyspnea and air hunger tonight so I need to go to the |
| everyday_paraphrase | I am 31 weeks into pregnancy with 3 days of a dry cough and a 39 C fever and feel like I am smothering sitting still tonight so I need to go to the |
| changed_fact | I am 31 weeks pregnant with 3 days of a dry cough and a 39 C fever and breathe easily at rest tonight so I need to go to the |
| everyday_attribution | I am 31 weeks pregnant with 3 days of a dry cough and a 39 C fever and I'm smothering at rest tonight and I think I just have a cold so I need to go to the |

Changed fact `f3`: "and I'm smothering at rest tonight" became "and breathe easily at rest tonight"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think I just have a cold"; source: Jiao M, Wang W, Chen C, Zhang X, Zhao X (2025). Treatment Inertia Among Elderly Patients with Chronic Heart Failure: A Qualitative Study. Patient Preference and Adherence. (direct patient quote).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| dry cough | authors' summary | Nantanda R, Najjingo I, Kjaergaard J, Reventlow S, Ndekezi D, Ssemata AS, Østergaard MS (2 PMID: 41714660; DOI: 10.1038/s41533-026-00493-7 | The episodes often started as a runny nose and an irritating dry or wet cough, mainly at night, associated with a sound in the chest and difficulty in breathing. |
| I'm smothering | authors' summary | Ferguson ON, Mitchell RA, Schaeffer MR, Ramsook AH, Dhillon SS, Dominelli PB, Molgat-Seon  PMID: 36469484; DOI: 10.1249/MSS.0000000000003074 | There were significant increases in the sensory quality of "smothering/air hunger" ( P = 0.01) and the emotional response of "anxiousness" ( P = 0.04) in the FM condition. |
| smothering | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'smo https://en.wiktionary.org/wiki/smother | # {{lb|en|intransitive}} To [[breathe]] with great difficulty by reason of smoke, dust, close covering or wrapping, or the like. |

Software findings: none.

## r10-07

Care level 4 · ends on "so I need to go to the" + "ER" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: acute decompensated fluid overload with orthopnea

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Patient is 67 years old
- `f2` 2 weeks of swelling in both ankles and 4 kg weight gain
- `f3` Acute severe shortness of breath when lying flat tonight

| Wording | Text |
|---|---|
| medical | I am 67 with 2 weeks of bilateral ankle edema and 4 kg weight gain and developed acute orthopnea and resting supine dyspnea tonight so I need to go to the |
| everyday | I am 67 with 2 weeks of swollen ankles and 4 kg weight gain and got short winded and can't catch my breath lying flat tonight so I need to go to the |
| medical_paraphrase | I am 67 years old with 2 weeks of dependent bilateral pedal edema plus 4 kg weight gain and acute orthopnea on recumbency tonight so I need to go to the |
| everyday_paraphrase | I am 67 years old with 2 weeks of swelling in both ankles and 4 kg weight gain and I am short winded and can't catch my breath lying flat tonight so I need to go to the |
| changed_fact | I am 67 with 2 weeks of swollen ankles and 4 kg weight gain and breathe comfortably when lying flat tonight so I need to go to the |
| everyday_attribution | I am 67 with 2 weeks of swollen ankles and 4 kg weight gain and got short winded and can't catch my breath lying flat tonight and I think I am just tired so I need to go to the |

Changed fact `f3`: "and got short winded and can't catch my breath lying flat tonight" became "and breathe comfortably when lying flat tonight"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think I am just tired"; source: Jiao M, Wang W, Chen C, Zhang X, Zhao X (2025). Treatment Inertia Among Elderly Patients with Chronic Heart Failure: A Qualitative Study. Patient Preference and Adherence. (direct patient quote).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| weight gain | authors' summary | Opasrattanakon S, Jaraeprapal U, Punsawad C (2026). Self-care management in patients with  PMID: 41839957; DOI: 10.1038/s41598-026-44071-w | Bodily sensations enable patients to recognize symptom changes early, supporting timely detection and effective HF management, such as shortness of breath, leg swelling, weight gain, orthopnea, and chest pain. |
| short winded | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'sho https://en.wiktionary.org/wiki/short-winded | # [[out of breath|Out of breath]], [[gasp]]ing for [[air]]; [[breathing]] [[rapidly]], or given to [[become|becoming]] [[short of breath]]. |
| can't catch my breath | authors' summary | Hardy P, Pappalardo AA (2025). "I can't breathe, I can't catch my breath:" the impact of s PMID: 39382247; DOI: 10.1080/02770903.2024.2414351 | "I can't breathe, I can't catch my breath:" the impact of school staff storytelling on asthma management. |
| swollen ankles | no source |   |  |
| swelling in both ankles | no source |   |  |

Software findings: none.

## r10-08

Care level 4 · ends on "so I need to go to the" + "hospital" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: acute febrile dermatomal vesicular rash with confusion

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Father is 73 years old
- `f2` 3 days of painful clustered blisters on the left chest
- `f3` Fever of 39 C
- `f4` New confusion and disorientation today

| Wording | Text |
|---|---|
| medical | My 73 year old father has 3 days of unilateral left thoracic neuralgia and clustered vesicles with a 39 C fever plus acute disorientation today so I need to go to the |
| everyday | My 73 year old father has 3 days of a misery in his left chest and clustered blisters with a 39 C fever plus confusion today so I need to go to the |
| medical_paraphrase | My 73 year old dad developed 3 days of left dermatomal chest pain and grouped vesicular lesions with a 39 C pyrexia and acute confusion today so I need to go to the |
| everyday_paraphrase | My 73 year old dad had 3 days of a misery in the left side of his chest and clusters of blisters with a 39 C fever and got confused today so I need to go to the |
| changed_fact | My 73 year old father has 3 days of a misery in his left chest and clustered blisters with a 39 C fever while staying clear headed today so I need to go to the |
| everyday_attribution | My 73 year old father has 3 days of a misery in his left chest and clustered blisters with a 39 C fever plus confusion today and I think it is heat rash so I need to go to the |

Changed fact `f4`: "plus confusion today" became "while staying clear headed today"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think it is heat rash"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| a misery in his left chest | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'mis https://en.wiktionary.org/wiki/misery | # {{lb|en|US|and|UK|dialects}} A [[bodily]] [[ache]] or [[pain]]. |
| clusters of blisters | authors' summary | Yamada R, Fuchigami T, Moriuchi Y (2026). A Pediatric Case of Urinary Retention Caused by  PMID: 42591554; DOI: 10.7759/cureus.112547 | (a) Clusters of blisters observed on the upper and right sides of the intergluteal cleft; (b) The bladder capacity before catheterization was 808 mL, and no obvious irregularities, wall thickening, or neoplastic lesions were observed. |
| clustered blisters | no source |   |  |
| confusion | no source |   |  |

Software findings: none.

## r10-09

Care level 3 · ends on "so I should see a" + "dentist" · split unassigned · register stratum `register`

Label for reviewers only, in no text: chronic gum disease with tooth mobility

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 2 months of gum bleeding when brushing teeth
- `f2` Receding gums and 1 loose lower front tooth
- `f3` No swelling under the jaw or tongue

| Wording | Text |
|---|---|
| medical | I have had 2 months of gingival bleeding on toothbrushing accompanied by gingival recession and 1 mobile mandibular anterior incisor without submandibular or sublingual edema so I should see a |
| everyday | I have had 2 months of gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth without jaw or tongue swelling so I should see a |
| medical_paraphrase | I experienced 2 months of gingival bleeding during toothbrushing with gingival recession and 1 mobile mandibular central incisor in the absence of submandibular or sublingual edema so I should see a |
| everyday_paraphrase | I had 2 months of bleeding gums when brushing my teeth along with gums pulling back and 1 loose lower front tooth without jaw or tongue swelling so I should see a |
| changed_fact | I have had 2 months of gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth with fast spreading firm jaw and tongue swelling so I should see a |
| everyday_attribution | I have had 2 months of gum bleeding brushing my teeth with receding gums and 1 loose lower front tooth without jaw or tongue swelling and I think it is just ageing so I should see a |
| quad_b | I have had 2 months of gingival bleeding on toothbrushing with gingival recession and 1 mobile mandibular anterior incisor without submandibular or sublingual edema so I should see a |
| quad_c | I have had 2 months of gum bleeding brushing my teeth accompanied by receding gums and 1 loose lower front tooth without jaw or tongue swelling so I should see a |

Changed fact `f3`: "without jaw or tongue swelling" became "with fast spreading firm jaw and tongue swelling"; right care after the change: level 4.

Patient explanation (adds a belief, analysed apart from register): "and I think it is just ageing"; source: Velpula KP, Jacob E (2025). The stories of the ageing population in Luton, United Kingdom on their experience of periodontal diseases healthcare. Frontiers in Public Health. (authors' summary).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| bleeding gums when brushing my teeth | authors' summary | Falcón-Flores JA, Jiménez-Corona ME, Rangel-Nieto IG, Vazquez-Duran M, Jiménez-Corona A (2 PMID: 41517925; DOI: 10.1002/cre2.70274 | (2) In the past year, have you had bleeding gums when brushing your teeth? |
| gum bleeding | authors' summary | Velpula KP, Jacob E (2025). The stories of the ageing population in Luton, United Kingdom  PMID: 41890769; DOI: 10.3389/fpubh.2025.1710973 | Participants exhibited low levels of awareness of the fact that periodontal disease is a preventable condition and tended to attribute such symptoms as gum bleeding or sensitivity to ageing. |
| receding gums | no source |   |  |
| 1 loose lower front tooth | no source |   |  |
| without jaw or tongue swelling | no source |   |  |

Software findings: none.

## r10-10

Care level 3 · ends on "so I should see a" + "dermatologist" · split unassigned · register stratum `register`

Label for reviewers only, in no text: chronic scaly plaque eruption refractory to topical therapy

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 4 months of thick red scaly plaques on both elbows
- `f2` Fingernail pitting unimproved after prescribed clinic cream
- `f3` No raw skin sloughing elsewhere

| Wording | Text |
|---|---|
| medical | I have had 4 months of erythematous plaques with silvery scales on both elbows and ungual pitting refractory to prescribed topical cream without epidermal detachment today so I should see a |
| everyday | I have had 4 months of red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream without raw skin sloughing today so I should see a |
| medical_paraphrase | I experienced 4 months of thick erythematous elbow plaques with silvery desquamation and nail pitting unresponsive to clinic topical therapy without epidermal sloughing today so I should see a |
| everyday_paraphrase | I had 4 months of thick red patches shedding flakes on both elbows with tiny nail pits after prescribed clinic cream failed without raw skin sloughing today so I should see a |
| changed_fact | I have had 4 months of red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream with raw skin sloughing across my chest today so I should see a |
| everyday_attribution | I have had 4 months of red patches with silvery scales on both elbows and nail pits unimproved by prescribed cream without raw skin sloughing today and I think it is dry skin so I should see a |
| quad_b | I have had 4 months of erythematous plaques with silvery scales on both elbows and ungual pitting unimproved by prescribed topical cream without epidermal detachment today so I should see a |
| quad_c | I have had 4 months of red patches with silvery scales on both elbows and nail pits refractory to prescribed cream without raw skin sloughing today so I should see a |

Changed fact `f3`: "without raw skin sloughing today" became "with raw skin sloughing across my chest today"; right care after the change: level 4.

Patient explanation (adds a belief, analysed apart from register): "and I think it is dry skin"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| red patches | authors' summary | Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and co PMID: 41544022; DOI: 10.1371/journal.pone.0329066 | Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin. |
| silvery scales | authors' summary | Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and co PMID: 41544022; DOI: 10.1371/journal.pone.0329066 | Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin. |
| shedding flakes | authors' summary | Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and co PMID: 41544022; DOI: 10.1371/journal.pone.0329066 | One respondent shared that she felt burdened because her skin kept shedding flakes onto the office carpet. |
| nail pits | no source |   |  |
| without raw skin sloughing today | no source |   |  |

Software findings: none.

## r10-11

Care level 3 · ends on "so I should see a" + "psychiatrist" · split unassigned · register stratum `register`

Label for reviewers only, in no text: treatment refractory persistent low mood syndrome

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 26 year old brother has 4 months of daily low mood sleep disruption and fatigue
- `f2` Unimproved after 2 prescribed clinic medication trials
- `f3` Speaking and responding normally today

| Wording | Text |
|---|---|
| medical | My 26 year old brother has 4 months of persistent dysphoria insomnia and fatigue refractory to 2 primary care pharmacotherapy trials while remaining verbally responsive today so I should see a |
| everyday | My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue unimproved after 2 prescribed clinic pills while speaking normally today so I should see a |
| medical_paraphrase | My 26 year old brother experienced 4 months of pervasive dysphoric mood sleep disturbance and fatigue unresponsive to 2 clinic medication trials with intact verbal responsiveness today so I should see a |
| everyday_paraphrase | My 26 year old brother spent 4 months with low mood disrupted sleep and tiredness that failed 2 prescribed doctor pills while talking normally today so I should see a |
| changed_fact | My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue unimproved after 2 prescribed clinic pills and became mute and unresponsive today so I should see a |
| everyday_attribution | My 26 year old brother has 4 months of daily low mood sleep disruption and fatigue unimproved after 2 prescribed clinic pills while speaking normally today and I think it is work stress so I should see a |

Changed fact `f3`: "while speaking normally today" became "and became mute and unresponsive today"; right care after the change: level 4.

Patient explanation (adds a belief, analysed apart from register): "and I think it is work stress"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| sleep disruption and fatigue | authors' summary | Boonkrong P, Khunboonjun K, Shakya S, Yang J, Vitoonmetha N, Chatchumni M (2026). A mixed- PMID: 42959322; DOI: 10.3389/frcha.2026.1907727 | At the same time, some participants described upward comparison, difficulty disengaging at night, sleep disruption, fatigue, and impaired concentration. |
| tiredness | authors' summary | Boonkrong P, Khunboonjun K, Shakya S, Yang J, Vitoonmetha N, Chatchumni M (2026). A mixed- PMID: 42959322; DOI: 10.3389/frcha.2026.1907727 | Nighttime use was a more consistent concern among heavier users: late scrolling delayed sleep and was followed by tiredness, irritability, mental fog, or reduced concentration the next day. |
| daily low mood | no source |   |  |
| unimproved after 2 prescribed clinic pills | no source |   |  |
| while speaking normally today | no source |   |  |

Software findings: none.

## r10-12

Care level 3 · ends on "so I should see a" + "therapist" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: chronic post collision trauma intrusion and avoidance syndrome

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Motor vehicle collision 3 months ago
- `f2` Nightly nightmares and daytime flashbacks
- `f3` Driving avoidance and exaggerated startle
- `f4` No loss of consciousness

| Wording | Text |
|---|---|
| medical | I survived a motor vehicle collision 3 months ago and have nightly trauma nightmares intrusive flashbacks driving avoidance and hypervigilance without syncope so I should see a |
| everyday | I survived a car crash 3 months ago and have nightly nightmares daytime flashbacks avoidance of driving and jumpiness without blacking out so I should see a |
| medical_paraphrase | I was in a vehicular collision 3 months ago and experience recurrent trauma nightmares daytime intrusions driving avoidance and exaggerated startle without loss of consciousness so I should see a |
| everyday_paraphrase | I was in a car accident 3 months ago and get nightmares flashbacks avoidance of reminders in traffic and startle easily with no blackouts so I should see a |
| changed_fact | I survived a car crash 3 months ago and have nightly nightmares daytime flashbacks avoidance of driving and jumpiness and just blacked out on the floor so I should see a |
| everyday_attribution | I survived a car crash 3 months ago and have nightly nightmares daytime flashbacks avoidance of driving and jumpiness without blacking out and I think it will pass alone so I should see a |

Changed fact `f4`: "without blacking out" became "and just blacked out on the floor"; right care after the change: level 4.

Patient explanation (adds a belief, analysed apart from register): "and I think it will pass alone"; source: none (none).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| nightmares | authors' summary | Dixon TAM, Hole K, Johnson L, Nutbeam T (2026). Trapped and traumatised: a scoping review  PMID: 41612474; DOI: 10.1186/s13049-026-01558-9 | Other symptoms described following MVC-entrapment included nightmares, avoidance of reminders, heightened physiological arousal, and ongoing anxiety; in some cases meeting criteria for ASD or PTSD, as explored below. |
| flashbacks | authors' summary | Melkevik O, Roberts N, Folke S (2026). Self-reported versus clinician-evaluated symptom as PMID: 41853968; DOI: 10.1080/20008066.2026.2635917 | The ITQ consists of six items measuring the three PTSD symptom clusters: re-experiencing symptoms (RE; flashbacks or nightmares), avoidance symptoms (AV; avoidance of internal or external reminders of the event), and sense of current threat (TH; hypervigilance or exaggerated startle response). |
| avoidance of reminders | authors' summary | Dixon TAM, Hole K, Johnson L, Nutbeam T (2026). Trapped and traumatised: a scoping review  PMID: 41612474; DOI: 10.1186/s13049-026-01558-9 | Other symptoms described following MVC-entrapment included nightmares, avoidance of reminders, heightened physiological arousal, and ongoing anxiety; in some cases meeting criteria for ASD or PTSD, as explored below. |
| blacking out | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'bla https://en.wiktionary.org/wiki/blackout | # A [[temporary]] [[loss]] of [[consciousness]]. |
| car crash | no source |   |  |
| jumpiness | no source |   |  |

Software findings: none.

## r10-13

Care level 3 · ends on "so I should see a" + "specialist" · split unassigned · register stratum `register`

Label for reviewers only, in no text: gradual bilateral lens clouding with night glare

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Patient is 71 years old
- `f2` Painless cloudy vision in both eyes
- `f3` Glare and halos around night headlights
- `f4` Developed gradually over 9 months

| Wording | Text |
|---|---|
| medical | I am 71 and have painless bilateral visual clouding with nocturnal headlight glare and halos developing gradually over 9 months so I should see a |
| everyday | I am 71 and have painless cloudy vision in both eyes with night headlight glare and halos building up over 9 months so I should see a |
| medical_paraphrase | I am 71 years old with painless bilateral visual opacification plus nocturnal glare and halos around headlights progressing slowly across 9 months so I should see a |
| everyday_paraphrase | I am 71 years old with painless cloudy sight in both eyes and bright glare and halos from night headlights getting worse over 9 months so I should see a |
| changed_fact | I am 71 and have painless cloudy vision in both eyes with night headlight glare and halos starting suddenly 20 minutes ago so I should see a |
| everyday_attribution | I am 71 and have painless cloudy vision in both eyes with night headlight glare and halos building up over 9 months and I think it is part of getting older so I should see a |

Changed fact `f4`: "building up over 9 months" became "starting suddenly 20 minutes ago"; right care after the change: level 4.

Patient explanation (adds a belief, analysed apart from register): "and I think it is part of getting older"; source: Coklar-Okutkan I, Harvey S, Doyle J, Teixeira F, Dinsmore J (2026). Illness Identity and Its Influence on Self-Management in Older Adults With Multimorbidity: A Hybrid Thematic Analysis. Qualitative Health Research. (authors' summary).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| glare and halos | authors' summary | Zavodni Z (2026). Visual Outcomes and Patient Satisfaction With a New Trifocal, Toric Intr PMID: 42471984; DOI: 10.1155/joph/9983329 | Although 25% (n = 6) of patients reported glare or halos “Most of the time” (n = 5) or “Always” (n = 1), 50% (n = 12) of patients reported that they were bothered by glare and halos either “Rarely” or “Never.” |
| cloudy vision in both eyes | no source |   |  |
| building up over 9 months | no source |   |  |

Software findings: 
- warning r10-13-chg: number: the everyday span drops ['9']
- warning r10-13-chg: number: the everyday span adds ['20']

## r10-14

Care level 3 · ends on "so I should see a" + "specialist" · split unassigned · register stratum `register`

Label for reviewers only, in no text: treatment refractory heavy menstrual bleeding

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 6 months of heavy menstrual periods lasting 9 days with large blood clots
- `f2` Unimproved on prescribed clinic hormone pills
- `f3` No fainting today

| Wording | Text |
|---|---|
| medical | I have had 6 months of menorrhagia lasting 9 days with large clots refractory to prescribed hormonal pills without orthostatic syncope today so I should see a |
| everyday | I have had 6 months of heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills without fainting today so I should see a |
| medical_paraphrase | I experienced 6 months of 9 day menorrhagia with large blood clots unresponsive to clinic hormonal therapy and no syncope today so I should see a |
| everyday_paraphrase | I spent 6 months having heavy periods for 9 days with large clots that failed prescribed clinic hormone pills without fainting today so I should see a |
| changed_fact | I have had 6 months of heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills and fainted standing up today so I should see a |
| everyday_attribution | I have had 6 months of heavy periods lasting 9 days with big clots unimproved on prescribed hormone pills without fainting today and I think heavy periods are normal for me so I should see a |

Changed fact `f3`: "without fainting today" became "and fainted standing up today"; right care after the change: level 4.

Patient explanation (adds a belief, analysed apart from register): "and I think heavy periods are normal for me"; source: Taree NA, Rich R, Zhu N, Khalife R, Wu CM, Sun HWL (2026). Barriers and facilitators for management of iron-deficiency anemia in reproductive-aged women: perspectives of health care professionals in Alberta, Canada. CMAJ. (authors' summary).

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| heavy periods | direct patient quote | Drejza M, Nicholson LS, Paquette G, Chawla M, Vale CL, Rogozińska E, Moss N, Hutchinson-Pa PMID: 42324234; DOI: 10.1111/1471-0528.70290 | Several participants described diagnosed mental health conditions, with one reporting, ‘I have been diagnosed with PTSD due to my heavy periods, hemorrhages and endometriosis. |
| big clots | no source |   |  |
| without fainting today | no source |   |  |

Software findings: none.

## r10-15

Care level 2 · ends on "so I need to go to the" + "clinic" · split unassigned · register stratum `register`

Label for reviewers only, in no text: persistent purulent facial sinus infection

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 12 days of worsening pain and pressure around the sinuses
- `f2` Thick green nasal discharge and 39 C fever
- `f3` No double vision today

| Wording | Text |
|---|---|
| medical | I have had 12 days of worsening maxillary sinus pain and pressure accompanied by purulent green rhinorrhea and a 39 C fever without diplopia today so I need to go to the |
| everyday | I have had 12 days of worsening pain and pressure around the sinuses with thick green nose mucus and a 39 C fever without double vision today so I need to go to the |
| medical_paraphrase | I experienced 12 days of progressive paranasal sinus pain and pressure with purulent green nasal discharge and a 39 C pyrexia in the absence of diplopia today so I need to go to the |
| everyday_paraphrase | I spent 12 days with worsening pain and pressure around my sinuses plus thick green snot and a 39 C fever and no double vision today so I need to go to the |
| changed_fact | I have had 12 days of worsening pain and pressure around the sinuses with thick green nose mucus and a 39 C fever and new double vision today so I need to go to the |
| quad_b | I have had 12 days of worsening maxillary sinus pain and pressure with purulent green rhinorrhea and a 39 C fever without diplopia today so I need to go to the |
| quad_c | I have had 12 days of worsening pain and pressure around the sinuses accompanied by thick green nose mucus and a 39 C fever without double vision today so I need to go to the |

Changed fact `f3`: "without double vision today" became "and new double vision today"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| pain and pressure around the sinuses | authors' summary | Coles T, Mkumba LS, Wright L, Godley FA, Collins TA, Jang DW (2025). Development of the Si PMID: 41196482; DOI: 10.1186/s41687-025-00956-4 | Many patients present with chronic or recurrent pain or pressure around the sinuses, often leading to a diagnosis of chronic rhinosinusitis (CRS). |
| thick green nose mucus | no source |   |  |
| thick green snot | no source |   |  |
| without double vision today | no source |   |  |

Software findings: none.

## r10-16

Care level 2 · ends on "so I should see a" + "doctor" · split unassigned · register stratum `register`

Label for reviewers only, in no text: subacute fatigue cold intolerance and weight gain syndrome

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 3 months of daily fatigue feeling cold and 6 kg weight gain
- `f2` Dry skin and hard infrequent stools
- `f3` Fully alert and oriented today

| Wording | Text |
|---|---|
| medical | I have had 3 months of persistent fatigue cold intolerance and a 6 kg weight gain accompanied by cutaneous dryness and constipation with intact mental alertness today so I should see a |
| everyday | I have had 3 months of daily tiredness feeling cold and a 6 kg weight gain with dry skin and hard infrequent stools while staying fully alert today so I should see a |
| medical_paraphrase | I experienced 3 months of daily fatigue cold intolerance and a 6 kg weight gain plus cutaneous dryness and constipation while remaining alert and oriented today so I should see a |
| everyday_paraphrase | I spent 3 months feeling tired and cold every day with a 6 kg weight gain plus dry skin and constipation while staying clear headed today so I should see a |
| changed_fact | I have had 3 months of daily tiredness feeling cold and a 6 kg weight gain with dry skin and hard infrequent stools and became confused and barely awake today so I should see a |
| quad_b | I have had 3 months of persistent fatigue cold intolerance and a 6 kg weight gain with cutaneous dryness and constipation while staying mentally alert today so I should see a |
| quad_c | I have had 3 months of daily tiredness feeling cold and a 6 kg weight gain accompanied by dry skin and hard infrequent stools with full alertness today so I should see a |

Changed fact `f3`: "while staying fully alert today" became "and became confused and barely awake today"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| weight gain | authors' summary | Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic Ma PMID: 42800981; DOI: 10.7759/cureus.115269 | Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being. |
| dry skin | authors' summary | Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic Ma PMID: 42800981; DOI: 10.7759/cureus.115269 | Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being. |
| constipation | authors' summary | Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic Ma PMID: 42800981; DOI: 10.7759/cureus.115269 | Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being. |
| daily tiredness feeling cold | no source |   |  |
| hard infrequent stools | no source |   |  |

Software findings: none.

## r10-17

Care level 2 · ends on "so I need to go to the" + "clinic" · split unassigned · register stratum `register`

Label for reviewers only, in no text: pediatric acute purulent ocular discharge

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Son is 3 years old
- `f2` 2 days of red eyes and thick yellow pus sticking eyelids shut on waking
- `f3` Moving both eyes normally today

| Wording | Text |
|---|---|
| medical | My 3 year old son has 2 days of bilateral bulbar erythema and purulent ocular discharge matting his eyelids on waking with intact extraocular motility today so I need to go to the |
| everyday | My 3 year old son has 2 days of red eyes and thick yellow pus gluing his eyelids shut on waking while moving both eyes easily today so I need to go to the |
| medical_paraphrase | My 3 year old boy developed 2 days of bilateral ocular erythema and mucopurulent discharge crusting his eyelids shut each morning with full extraocular movements today so I need to go to the |
| everyday_paraphrase | My 3 year old boy had 2 days of red eyes with yellow eye pus sticking his eyelids together on waking and moves both eyes normally today so I need to go to the |
| changed_fact | My 3 year old son has 2 days of red eyes and thick yellow pus gluing his eyelids shut on waking and cannot move his right eye today so I need to go to the |

Changed fact `f3`: "while moving both eyes easily today" became "and cannot move his right eye today"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| red eyes | authors' summary | Muse YH, Hassan MA, Ali M, Muse AH, Nadarajah S (2026). A pediatric case of measles with g PMID: 42437059; DOI: 10.1016/j.idcr.2026.e02657 | A 4.5-year-old girl from an urban area presented with fever, vomiting, diarrhea, red eyes, and poor oral intake. |
| thick yellow pus gluing his eyelids shut on waking | no source |   |  |
| while moving both eyes easily today | no source |   |  |

Software findings: none.

## r10-18

Care level 2 · ends on "so I should see a" + "doctor" · split unassigned · register stratum `register`

Label for reviewers only, in no text: inhaled corticosteroid associated oral white mucosal plaques

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Started a daily steroid inhaler 2 weeks ago
- `f2` 5 days of sore white patches on the tongue and inner cheeks leaving red spots when wiped
- `f3` Swallowing liquids easily today

| Wording | Text |
|---|---|
| medical | I started a daily corticosteroid inhaler 2 weeks ago and have 5 days of sore white plaques on my tongue and buccal mucosa with erythematous bases when scraped and intact liquid swallowing today so I should see a |
| everyday | I started a daily steroid inhaler 2 weeks ago and have 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped while swallowing liquids easily today so I should see a |
| medical_paraphrase | I began daily inhaled corticosteroids 2 weeks ago and developed 5 days of painful white oral plaques over my tongue and buccal mucosa leaving erythematous mucosa on scraping with normal liquid intake today so I should see a |
| everyday_paraphrase | I began using a daily steroid inhaler 2 weeks ago and got 5 days of sore white patches on my tongue and inside my cheeks that wipe off red while drinking liquids easily today so I should see a |
| changed_fact | I started a daily steroid inhaler 2 weeks ago and have 5 days of sore white patches on my tongue and inner cheeks leaving red spots when wiped and cannot swallow water today so I should see a |

Changed fact `f3`: "while swallowing liquids easily today" became "and cannot swallow water today"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| sore white patches on my tongue and inner cheeks | no source |   |  |
| leaving red spots when wiped | no source |   |  |
| while swallowing liquids easily today | no source |   |  |

Software findings: none.

## r10-19

Care level 2 · ends on "so I should see a" + "doctor" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: expanding annular rash after tick bite

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 11 year old son had a tick bite on his calf 8 days ago
- `f2` Expanding 7 cm red ring rash and 38 C fever
- `f3` No fainting episodes

| Wording | Text |
|---|---|
| medical | My 11 year old son had a calf tick bite 8 days ago and developed an expanding 7 cm annular erythematous rash and a 38 C fever without syncope so I should see a |
| everyday | My 11 year old son had a calf tick bite 8 days ago and got a spreading 7 cm red ring rash and a 38 C fever without fainting spells so I should see a |
| medical_paraphrase | My 11 year old boy sustained a calf tick bite 8 days ago and has an expanding 7 cm annular erythema and a 38 C pyrexia without syncopal episodes so I should see a |
| everyday_paraphrase | My 11 year old boy got a calf tick bite 8 days ago and has a growing 7 cm red bullseye rash and a 38 C fever with no fainting spells so I should see a |
| changed_fact | My 11 year old son had a calf tick bite 8 days ago and got a spreading 7 cm red ring rash and a 38 C fever and a fainting spell today so I should see a |

Changed fact `f3`: "without fainting spells" became "and a fainting spell today"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| tick bite | authors' summary | Bogovič P, Jaklič M, Ogrinc K, Maraspin V, Rojko T, Nahtigal-Klevišar M, Ružić-Sabljić E,  PMID: 42783436; DOI: 10.3390/medsci14050563 | EM was defined as an expanding erythematous skin lesion, with or without central clearing, that developed days to a few weeks after a tick bite or exposure to ticks in an LB-endemic area and had a maximum diameter of ≥5 cm. |
| fainting spells | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'spe https://en.wiktionary.org/wiki/spell | # {{lb|en|colloquial|US}} A period of illness, or sudden interval of bad spirits, disease etc. {{defdate|from 19th c.}} |
| spreading 7 cm red ring rash | no source |   |  |

Software findings: none.

## r10-20

Care level 2 · ends on "so I need to go to the" + "clinic" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: subacute exertional dyspnea conjunctival pallor and koilonychia

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 6 weeks of tiredness and lightheadedness climbing 1 flight of stairs
- `f2` Pale inner eyelids and brittle spoon shaped nails
- `f3` Comfortable normal breathing at rest

| Wording | Text |
|---|---|
| medical | I have had 6 weeks of exertional fatigue and lightheadedness climbing 1 flight of stairs accompanied by conjunctival pallor and koilonychia with comfortable resting respiration today so I need to go to the |
| everyday | I have had 6 weeks of tiredness and feeling giddy climbing 1 flight of stairs with pale inner eyelids and spooned nails but easy resting breathing today so I need to go to the |
| medical_paraphrase | I experienced 6 weeks of exertional fatigue and presyncopal dizziness on 1 flight of stairs accompanied by palpebral conjunctival pallor and brittle spoon nails with normal resting breathing today so I need to go to the |
| everyday_paraphrase | I spent 6 weeks getting tired with giddiness climbing 1 flight of stairs plus pale lower eyelids and brittle scooped nails while breathing easily at rest today so I need to go to the |
| changed_fact | I have had 6 weeks of tiredness and feeling giddy climbing 1 flight of stairs with pale inner eyelids and spooned nails and am gasping for air at rest today so I need to go to the |

Changed fact `f3`: "but easy resting breathing today" became "and am gasping for air at rest today"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| giddiness | authors' summary | Rana T, Kaeley N, Tejpal P, Yadav S, Mudi D (2025). Pulmonary Embolism Presenting as Recur PMID: 41573451; DOI: 10.7759/cureus.99743 | We describe a 41-year-old previously healthy man who presented with recurrent episodes of syncope, giddiness, and transient blurring of vision over five days. |
| feeling giddy | no source |   |  |
| pale inner eyelids | no source |   |  |
| spooned nails | no source |   |  |

Software findings: none.

## r10-21

Care level 1 · ends on "so I just need some" + "cream" · split unassigned · register stratum `new_carrier` (flags: new_carrier)

Label for reviewers only, in no text: mild uncomplicated toe web scaling

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 5 days of mild itchy peeling skin between the 4th and 5th left toes after gym showers
- `f2` No pus

| Wording | Text |
|---|---|
| medical | I have had 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers without purulent exudate so I just need some |
| everyday | I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers with no yellow pus so I just need some |
| medical_paraphrase | I developed 5 days of mild pruritic scaling and peeling in the 4th and 5th left interdigital toe web after gym showers without purulence so I just need some |
| everyday_paraphrase | I got 5 days of mild itchy flaking skin between my 4th and 5th left toes after gym showers and no pus at all so I just need some |
| changed_fact | I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers oozing thick yellow pus so I just need some |
| quad_b | I have had 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers with no purulent exudate so I just need some |
| quad_c | I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers without yellow pus so I just need some |

Changed fact `f2`: "with no yellow pus" became "oozing thick yellow pus"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| peeling | authors' summary | Kutlu O, Cetinkaya PO, Yavuz G, Khachemoune A (2025). Turkish Bath-Associated Infectious D PMID: 41700199; DOI: 10.14744/SEMB.2025.54782 | Tinea pedis manifests as either interdigital erythema with scaling, peeling, and maceration—especially between the fourth and fifth toes—hyperkeratotic thick scaly erythematous plaques on the soles, heels, and sides of the feet, or vesiculobullous intensely pruritic vesicles/bullae on an erythematous base. |
| itchy peeling skin between my 4th and 5th left toes | no source |   |  |
| with no yellow pus | no source |   |  |

Software findings: none.

## r10-22

Care level 1 · ends on "so I just need some" + "ointment" · split unassigned · register stratum `new_carrier` (flags: new_carrier)

Label for reviewers only, in no text: mild uncomplicated infant diaper area redness

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 8 month old son has 1 day of mild pink redness in the diaper area
- `f2` No pus blisters

| Wording | Text |
|---|---|
| medical | My 8 month old son has 1 day of mild macular erythema in his diaper area without pustular lesions so I just need some |
| everyday | My 8 month old son has 1 day of mild pink skin redness in his diaper area with no pus blisters so I just need some |
| medical_paraphrase | My 8 month old infant developed 1 day of mild superficial diaper area erythema in the absence of pustules so I just need some |
| everyday_paraphrase | My 8 month old baby boy got 1 day of mild pink redness in his diaper area without any pus bumps so I just need some |
| changed_fact | My 8 month old son has 1 day of mild pink skin redness in his diaper area covered in yellow pus blisters so I just need some |

Changed fact `f2`: "with no pus blisters" became "covered in yellow pus blisters"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| diaper area | authors' summary | Alkhamis ZZ, Bhagchandani M, Idris M, Bhyat Y, Alsani SM, Pasha AI, Ali AHA, Ali Eledresi  PMID: 41769510; DOI: 10.7759/cureus.102379 | Diaper dermatitis (DD) is a broad term used to describe the acute inflammatory skin response caused by irritation from urine, feces, moisture, or friction in the diaper area of infants and children. |
| pink skin redness | no source |   |  |
| with no pus blisters | no source |   |  |

Software findings: none.

## r10-23

Care level 1 · ends on "so I just need some" + "lotion" · split unassigned · register stratum `new_carrier` (flags: new_carrier)

Label for reviewers only, in no text: mild winter lower leg skin dryness

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 7 days of mild dry flaky itchy skin on both shins in cold winter air
- `f2` No pus bumps

| Wording | Text |
|---|---|
| medical | I have had 7 days of mild cutaneous dryness fine desquamation and pruritus on both shins in winter weather without pustules so I just need some |
| everyday | I have had 7 days of mild dry skin flakiness and itching on both shins in winter weather with no pus bumps so I just need some |
| medical_paraphrase | I developed 7 days of mild bilateral pretibial cutaneous dryness scaling and pruritus in cold winter air without pustular lesions so I just need some |
| everyday_paraphrase | I got 7 days of mild dry flaky itchy skin on both shins in cold winter weather without any pus bumps so I just need some |
| changed_fact | I have had 7 days of mild dry skin flakiness and itching on both shins in winter weather with painful yellow pus bumps so I just need some |
| quad_b | I have had 7 days of mild cutaneous dryness fine desquamation and pruritus on both shins in winter weather with no pustules so I just need some |
| quad_c | I have had 7 days of mild dry skin flakiness and itching on both shins in winter weather without pus bumps so I just need some |

Changed fact `f2`: "with no pus bumps" became "with painful yellow pus bumps"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| dry skin | authors' summary | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | Dry skin, marked by flakiness and a rough texture, is a key contributor to various skin issues, primarily caused by a compromised skin barrier that results in moisture loss [23]. |
| flakiness | authors' summary | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | Dry skin, marked by flakiness and a rough texture, is a key contributor to various skin issues, primarily caused by a compromised skin barrier that results in moisture loss [23]. |
| itching | authors' summary | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | Xerosis, marked by a compromised skin barrier and disrupted lipid metabolism, leads to dryness, scaling, and itching. |
| shins | authors' summary | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | Xerosis predominantly manifests on the lower extremities, particularly the shins and calves, where the density of sebaceous glands is minimal and transepidermal water loss is pronounced [3]. |
| with no pus bumps | no source |   |  |

Software findings: none.

## r10-24

Care level 1 · ends on "so I just need some" + "medicine" · split unassigned · register stratum `new_carrier` (flags: new_carrier)

Label for reviewers only, in no text: mild seasonal pollen sneezing and watery eyes

Status: software passed · owner read: not_read · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 3 days of sneezing and clear runny nose outdoors in spring pollen
- `f2` Mildly itchy watery eyes
- `f3` Easy normal breathing

| Wording | Text |
|---|---|
| medical | I have had 3 days of paroxysmal sneezing and clear aqueous rhinorrhea outdoors in spring pollen with mild ocular pruritus and epiphora and eupnea today so I just need some |
| everyday | I have had 3 days of sneezing and a clear running nose outdoors in spring pollen with mildly itchy watery eyes and easy breathing today so I just need some |
| medical_paraphrase | I developed 3 days of sneezing and clear watery rhinorrhea around spring pollen accompanied by mild bilateral ocular pruritus and tearing with normal respiration today so I just need some |
| everyday_paraphrase | I got 3 days of sneezing when my nose starts running outdoors in spring pollen with mildly itchy and watery eyes and comfortable breathing today so I just need some |
| changed_fact | I have had 3 days of sneezing and a clear running nose outdoors in spring pollen with mildly itchy watery eyes and cannot catch my breath sitting still today so I just need some |

Changed fact `f3`: "and easy breathing today" became "and cannot catch my breath sitting still today"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| my nose starts running | direct patient quote | Opadokun A, Mikhail E, Chong LX, Suphioğlu C, Gokhale M, Azizoğlu S (2026). The Impact of  PMID: 42796056; DOI: 10.3390/jcm15187284 | Pollen emerged as a widely recognised trigger, particularly during spring: “When the wind picks up in spring, I can feel it instantly; my nose starts running, and I can’t stop sneezing” (P9). |
| sneezing | direct patient quote | Opadokun A, Mikhail E, Chong LX, Suphioğlu C, Gokhale M, Azizoğlu S (2026). The Impact of  PMID: 42796056; DOI: 10.3390/jcm15187284 | Pollen emerged as a widely recognised trigger, particularly during spring: “When the wind picks up in spring, I can feel it instantly; my nose starts running, and I can’t stop sneezing” (P9). |
| itchy and watery eyes | authors' summary | Opadokun A, Mikhail E, Chong LX, Suphioğlu C, Gokhale M, Azizoğlu S (2026). The Impact of  PMID: 42796056; DOI: 10.3390/jcm15187284 | Participants reported a wide range of symptoms including nasal congestion, sneezing, itchy and watery eyes, headaches and fatigue. |
| and easy breathing today | no source |   |  |

Software findings: none.
