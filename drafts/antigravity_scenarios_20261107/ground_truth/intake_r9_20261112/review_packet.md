# Review packet: batch r9_20261110

Source: draft/antigravity-scenarios-20261107@d4b27148:drafts/antigravity_scenarios_20261107/round9_20261110/families.json (SHA-256 `d5e347fd46c48343bf6b8dbbca89461b4261a69247d2747893929b1c283f67f2`).

Design rules: `data/experiments/intake_design.v1.json` (`6f033e45e641`). Status of those rules: draft, 2026-11-12: proposed by the batch-intake change; not agreed. The owner agrees it by a commit that changes this line.

What has and has not been reviewed:

- **Software validation: passed** (0 errors, 5 warnings). These are structural checks by this command. It says nothing about clinical content or patient language.
- **Owner's read:** 15 kept, 1 stale. This is the owner's keep or exclude decision on a named version of the texts. It is not a clinician's review.
- **Domain review:** 16 domain review pending. A family is reviewed only when a clinician and a patient-language reviewer have both recorded their items; nothing in this packet does that.

No model output appears in this packet.

Measured endpoint, when measured: the full-vocabulary probability of the first token of the family's declared target word at the position after the carrier phrase. It is not triage accuracy, the quality of an answer, evidence that a model understands a wording.

- Care tiers are not compared with each other: families at different tiers use different carrier phrases and target words, so their endpoints are probabilities of different tokens in different contexts.
- Strata are not pooled: a register contrast, a patient-explanation contrast and a syntax crossing are different manipulations.

## r9-01

Care level 4 · ends on "so I need to go to the" + "ER" · split discovery · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: cardiogenic syncope

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Occurred 2 times today
- `f2` Sudden rapid heartbeat
- `f3` Tight or sinking sensation in the chest
- `f4` Followed immediately by brief loss of consciousness

| Wording | Text |
|---|---|
| medical | 2 times today I experienced paroxysmal rapid palpitations accompanied by acute precordial chest tightness followed by transient loss of consciousness so I need to go to the |
| everyday | 2 times today I got a sudden racing heartbeat along with my heart sinking in my chest right before briefly blacking out so I need to go to the |
| medical_paraphrase | On 2 occasions today I developed abrupt rapid palpitations with substernal chest tightness resulting in brief loss of consciousness so I need to go to the |
| everyday_paraphrase | I had 2 episodes today where my heart raced suddenly with a sinking heart in my chest right before a brief blackout so I need to go to the |
| changed_fact | 2 times today I got a sudden racing heartbeat along with my heart sinking in my chest that passed quickly sitting still with no dizziness or fainting so I need to go to the |
| quad_b | 2 times today I got paroxysmal rapid palpitations along with acute precordial chest tightness right before transient loss of consciousness so I need to go to the |
| quad_c | 2 times today I experienced a sudden racing heartbeat accompanied by my heart sinking in my chest followed by briefly blacking out so I need to go to the |

Changed fact `f4`: "right before briefly blacking out" became "that passed quickly sitting still with no dizziness or fainting"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| a sudden racing heartbeat | no source |   |  |
| my heart raced suddenly | no source |   |  |
| my heart sinking in my chest | authors' summary | Krause IB (1989). Sinking heart: a Punjabi communication of distress. Social Science & Med PMID: 2756440; DOI: 10.1016/0277-9536(89)90202-5 | not given |
| a sinking heart in my chest | authors' summary | Krause IB (1989). Sinking heart: a Punjabi communication of distress. Social Science & Med PMID: 2756440; DOI: 10.1016/0277-9536(89)90202-5 | not given |
| briefly blacking out | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'bla https://en.wiktionary.org/wiki/blackout | not given |
| a brief blackout | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'bla https://en.wiktionary.org/wiki/blackout | not given |

Software findings: none.

## r9-02

Care level 4 · ends on "so I need to go to the" + "hospital" · split validation · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: transient ischemic attack

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Patient is 74 years old
- `f2` Sudden episode began 45 minutes ago
- `f3` Left facial weakness and slurred speech
- `f4` Episode lasted 10 minutes

| Wording | Text |
|---|---|
| medical | My mother is 74 years old and 45 minutes ago she experienced an acute focal neurologic episode characterized by unilateral left facial paresis and dysarthria lasting 10 minutes so I need to go to the |
| everyday | My mother is 74 years old and 45 minutes ago she had a funny turn where the left side of her face drooped and speech slurred for 10 minutes so I need to go to the |
| medical_paraphrase | At age 74 my mother developed a sudden neurologic event 45 minutes ago presenting with left facial motor weakness and dysarthric speech over 10 minutes so I need to go to the |
| everyday_paraphrase | My 74 year old mother had a funny turn 45 minutes ago when her left face drooped and her words came out slurred for 10 minutes so I need to go to the |
| changed_fact | My mother is 74 years old and 45 minutes ago she had a funny turn where she felt mildly lightheaded right after standing up quickly for 10 minutes so I need to go to the |

Changed fact `f3`: "where the left side of her face drooped and speech slurred" became "where she felt mildly lightheaded right after standing up quickly"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| a funny turn | authors' summary | Blythe R, Kularatna S, White N, Graves N, Clark K, Middleton H, Grimley R (2019). Fits, fa PMID: 31297515; DOI: 10.1093/ageing/afz086 | not given |
| the left side of her face drooped and speech slurred | authors' summary | Mellor RM, Bailey S, Sheppard J, Carr P, Quinn T, Boyal A, Sandler D, Sims DG, Mant J, Gre PMID: 25455907; DOI: 10.1016/j.annemergmed.2014.10.018 | not given |

Software findings: none.

## r9-03

Care level 4 · ends on "so I need to go to the" + "hospital" · split fresh_test · register stratum `register`

Label for reviewers only, in no text: preeclampsia with severe features

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Currently at 33 weeks of pregnancy
- `f2` Symptoms present for the past 3 hours
- `f3` Mild swelling of both ankles
- `f4` Severe persistent headache with dark spots in vision

| Wording | Text |
|---|---|
| medical | At 33 weeks of pregnancy for the past 3 hours I have had mild dependent bilateral ankle edema accompanied by severe unrelenting cephalalgia and dark visual scotomata so I need to go to the |
| everyday | At 33 weeks of pregnancy for the past 3 hours I have had mild swelling in both ankles with a bad constant headache and dark spots in my vision so I need to go to the |
| medical_paraphrase | Now at 33 weeks gestation over the last 3 hours I developed mild edema of both ankles together with persistent severe cephalalgia and dark scotomata in my visual field so I need to go to the |
| everyday_paraphrase | I am 33 weeks pregnant and for 3 hours both of my ankles have been mildly puffy with a terrible nonstop headache and dark spots before my eyes so I need to go to the |
| changed_fact | At 33 weeks of pregnancy for the past 3 hours I have had mild swelling in both ankles after standing with mild back ache and no headache or blurry vision so I need to go to the |

Changed fact `f4`: "with a bad constant headache and dark spots in my vision" became "after standing with mild back ache and no headache or blurry vision"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| swelling in both ankles | authors' summary | Carter W, Bick D, Mackintosh N, Sandall J (2021). Maternal help seeking about early warnin PMID: 33780789; DOI: 10.1016/j.midw.2021.102992 | not given |
| both of my ankles have been mildly puffy | no source |   |  |
| a bad constant headache | authors' summary | Carter W, Bick D, Mackintosh N, Sandall J (2021). Maternal help seeking about early warnin PMID: 33780789; DOI: 10.1016/j.midw.2021.102992 | not given |
| dark spots in my vision | authors' summary | Carter W, Bick D, Mackintosh N, Sandall J (2021). Maternal help seeking about early warnin PMID: 33780789; DOI: 10.1016/j.midw.2021.102992 | not given |

Software findings: none.

## r9-04

Care level 4 · ends on "so I need to go to the" + "ER" · split discovery · register stratum `register`

Label for reviewers only, in no text: severe acute bronchiolitis

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Infant is 5 months old
- `f2` 2 days of nasal mucus and cough
- `f3` Slightly reduced bottle feeding
- `f4` Labored breathing tonight with chest skin pulling between ribs

| Wording | Text |
|---|---|
| medical | My baby is 5 months old with 2 days of rhinorrhea and cough plus mildly decreased oral intake and tonight developed labored dyspnea with intercostal retractions so I need to go to the |
| everyday | My baby is 5 months old with 2 days of extra mucus and cough plus smaller bottle feeds and tonight has hard breathing with ribs sucking in so I need to go to the |
| medical_paraphrase | At 5 months of age following 2 days of nasal discharge and cough with modestly reduced bottle intake my infant developed respiratory distress and intercostal retractions tonight so I need to go to the |
| everyday_paraphrase | My 5 month old baby has had 2 days of runny mucus and a cough taking less milk and tonight she has trouble breathing with skin pulling around her ribs so I need to go to the |
| changed_fact | My baby is 5 months old with 2 days of extra mucus and cough plus smaller bottle feeds and tonight breathes easily with wet diapers and low fever so I need to go to the |

Changed fact `f4`: "and tonight has hard breathing with ribs sucking in" became "and tonight breathes easily with wet diapers and low fever"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| extra mucus | no source |   |  |
| runny mucus | no source |   |  |
| smaller bottle feeds | no source |   |  |
| taking less milk | no source |   |  |
| hard breathing | authors' summary | Campbell A, Hartling L, Louie-Poon S, Scott SD (2020). Parent Experiences Caring for a Chi PMID: 33457588; DOI: 10.1177/2374373520924526 | not given |
| trouble breathing | authors' summary | Campbell A, Hartling L, Louie-Poon S, Scott SD (2020). Parent Experiences Caring for a Chi PMID: 33457588; DOI: 10.1177/2374373520924526 | not given |
| ribs sucking in | no source |   |  |
| skin pulling around her ribs | no source |   |  |

Software findings: none.

## r9-05

Care level 4 · ends on "so I need to go to the" + "ER" · split discovery · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: severe acute asthma exacerbation

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Symptoms ongoing for the past 20 minutes
- `f2` Acute shortness of breath
- `f3` Audible chest wheezing
- `f4` Unable to speak full sentences despite 2 rescue inhaler puffs

| Wording | Text |
|---|---|
| medical | For the past 20 minutes I have become acutely dyspneic accompanied by audible expiratory wheezing with inability to complete sentences despite 2 bronchodilator puffs so I need to go to the |
| everyday | For the past 20 minutes I started feeling short winded with tight whistling breathing and broken sentences even after 2 inhaler puffs so I need to go to the |
| medical_paraphrase | Over the last 20 minutes I developed severe dyspnea and expiratory wheezes with fragmented speech refractory to 2 inhaled bronchodilator actuations so I need to go to the |
| everyday_paraphrase | Over the last 20 minutes I can't catch my breath with whistling in my chest and cannot finish a sentence even after 2 puffs of my inhaler so I need to go to the |
| changed_fact | For the past 20 minutes I started feeling short winded with tight whistling breathing that eased right away after 2 inhaler puffs with normal speech so I need to go to the |
| quad_b | For the past 20 minutes I started feeling acutely dyspneic with audible expiratory wheezing and inability to complete sentences even after 2 bronchodilator puffs so I need to go to the |
| quad_c | For the past 20 minutes I have become short winded accompanied by tight whistling breathing with broken sentences despite 2 inhaler puffs so I need to go to the |

Changed fact `f4`: "and broken sentences even after 2 inhaler puffs" became "that eased right away after 2 inhaler puffs with normal speech"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| short winded | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'sho https://en.wiktionary.org/wiki/short-winded | not given |
| can't catch my breath | authors' summary | Hardy P, Pappalardo AA (2025). "I can't breathe, I can't catch my breath:" the impact of s PMID: 39382247; DOI: 10.1080/02770903.2024.2414351 | not given |
| tight whistling breathing | no source |   |  |
| whistling in my chest | no source |   |  |
| broken sentences even after 2 inhaler puffs | no source |   |  |
| cannot finish a sentence even after 2 puffs of my inhaler | no source |   |  |

Software findings: none.

## r9-06

Care level 4 · ends on "so I need to go to the" + "hospital" · split discovery · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: generalized tonic clonic seizure

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Occurred today after 2 brief episodes earlier this month
- `f2` Happened while standing in a warm room
- `f3` Preceded by sudden dizziness
- `f4` Collapsed unconscious with 3 minutes of generalized convulsions

| Wording | Text |
|---|---|
| medical | Today after 2 brief episodes this month while standing in a warm room I developed acute presyncopal lightheadedness followed by loss of consciousness and 3 minutes of generalized convulsions so I need to go to the |
| everyday | Today after 2 brief episodes this month while standing in a warm room I got a sudden dizzy spell and then fell out having fits for 3 minutes so I need to go to the |
| medical_paraphrase | Following 2 transient episodes earlier this month today in a warm room I experienced sudden presyncopal lightheadedness progressing to unconsciousness and generalized convulsions lasting 3 minutes so I need to go to the |
| everyday_paraphrase | After 2 short episodes this month today standing in a warm room I had a dizzy spell before falling out and having fits for 3 minutes so I need to go to the |
| changed_fact | Today after 2 brief episodes this month while standing in a warm room I got a sudden dizzy spell but sat down and recovered in 1 minute without fainting so I need to go to the |

Changed fact `f4`: "and then fell out having fits for 3 minutes" became "but sat down and recovered in 1 minute without fainting"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| a sudden dizzy spell | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'spe https://en.wiktionary.org/wiki/spell | not given |
| a dizzy spell | dictionary definition | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'spe https://en.wiktionary.org/wiki/spell | not given |
| fell out | lexicon entry ('fell out / falling out') | dialect_lexicon_20261109.json, core entry 'fell out / falling out' (Wiktionary entry 'fall https://en.wiktionary.org/wiki/fall_out | not given |
| falling out | authors' summary | Mas C (2022). "Falling-Out" in Miami and the History of Culture in American Medicine. Bull PMID: 35370146; DOI: 10.1353/bhm.2022.0003 | not given |
| having fits | authors' summary | Nwani PO, Nwosu MC, Enwereji KO, Asomugha AL, Arinzechi EO, Ogunniyi AO (2013). Epilepsy t PMID: 23425044; DOI: 10.1111/ane.12096 | not given |

Software findings: 
- warning r9-06-chg: number: the everyday span drops ['3']
- warning r9-06-chg: number: the everyday span adds ['1']

## r9-07

Care level 4 · ends on "so I need to go to the" + "hospital" · split validation · register stratum `register`

Label for reviewers only, in no text: pediatric diabetic ketoacidosis

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Child is 9 years old
- `f2` 1 week of excessive thirst
- `f3` 1 week of frequent urination
- `f4` Persistent vomiting and marked drowsiness today

| Wording | Text |
|---|---|
| medical | My son is 9 years old and after 1 week of polydipsia and polyuria he developed intractable emesis and marked somnolence today so I need to go to the |
| everyday | My son is 9 years old and after 1 week of extreme thirst and constant toilet trips he started nonstop vomiting and drowsiness today so I need to go to the |
| medical_paraphrase | At age 9 following 1 week of excessive polydipsia with polyuria my son presented with persistent emesis and pronounced lethargy today so I need to go to the |
| everyday_paraphrase | My 9 year old son for 1 week has had extreme thirst and frequent trips to the toilet and cannot stop throwing up while acting drowsy today so I need to go to the |
| changed_fact | My son is 9 years old and after 1 week of extreme thirst and constant toilet trips he stays alert eating meals with no vomiting today so I need to go to the |

Changed fact `f4`: "he started nonstop vomiting and drowsiness" became "he stays alert eating meals with no vomiting"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| extreme thirst | authors' summary | Rankin D, Harden J, Waugh N, Noyes K, Barnard KD, Stephen J, Robertson KJ, Bath L, Roberts PMID: 24552497; DOI: 10.1111/pedi.12124 | not given |
| constant toilet trips | authors' summary | Rankin D, Harden J, Waugh N, Noyes K, Barnard KD, Stephen J, Robertson KJ, Bath L, Roberts PMID: 24552497; DOI: 10.1111/pedi.12124 | not given |
| frequent trips to the toilet | authors' summary | Rankin D, Harden J, Waugh N, Noyes K, Barnard KD, Stephen J, Robertson KJ, Bath L, Roberts PMID: 24552497; DOI: 10.1111/pedi.12124 | not given |
| nonstop vomiting and drowsiness | no source |   |  |
| cannot stop throwing up while acting drowsy | no source |   |  |

Software findings: none.

## r9-08

Care level 4 · ends on "so I need to go to the" + "ER" · split fresh_test · register stratum `register`

Label for reviewers only, in no text: food induced anaphylaxis

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 2 hours after eating shellfish
- `f2` Itchy raised hives across both arms
- `f3` Throat swelling with labored breathing

| Wording | Text |
|---|---|
| medical | 2 hours after eating shellfish I developed generalized pruritic urticaria across both upper extremities accompanied by acute oropharyngeal angioedema and labored dyspnea so I need to go to the |
| everyday | 2 hours after eating shellfish I was itching and breaking out in hives on both arms and my throat swelled up with trouble breathing so I need to go to the |
| medical_paraphrase | Following shellfish ingestion 2 hours ago I presented with pruritic urticarial wheals on both arms plus pharyngeal angioedema and acute respiratory difficulty so I need to go to the |
| everyday_paraphrase | After eating shellfish 2 hours ago I started itching and breaking out in hives over both arms while my throat swelled up with trouble breathing so I need to go to the |
| changed_fact | 2 hours after eating shellfish I was itching and breaking out in hives on both arms with normal breathing and no lip or throat swelling so I need to go to the |

Changed fact `f3`: "and my throat swelled up with trouble breathing" became "with normal breathing and no lip or throat swelling"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| itching and breaking out in hives | direct patient quote | Oehrlein EM, Schoch SC, Escontrias OA, Carver M, Eftekhari S, Marvel J, Pashos CL, Pistine PMID: 40486694; DOI: 10.1016/j.jacig.2025.100482 | not given |
| my throat swelled up | direct patient quote | Oehrlein EM, Schoch SC, Escontrias OA, Carver M, Eftekhari S, Marvel J, Pashos CL, Pistine PMID: 40486694; DOI: 10.1016/j.jacig.2025.100482 | not given |
| trouble breathing | authors' summary | Oehrlein EM, Schoch SC, Escontrias OA, Carver M, Eftekhari S, Marvel J, Pashos CL, Pistine PMID: 40486694; DOI: 10.1016/j.jacig.2025.100482 | not given |

Software findings: none.

## r9-09

Care level 3 · ends on "so I should see a" + "dentist" · split validation · register stratum `register`

Label for reviewers only, in no text: symptomatic irreversible pulpitis

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Symptoms present for 4 days
- `f2` Throbbing pain localized to 1 lower back tooth
- `f3` Triggered by hot and cold liquids
- `f4` Absence of facial swelling fever or difficulty swallowing

| Wording | Text |
|---|---|
| medical | For 4 days I have experienced pulsatile odontalgia in 1 mandibular molar provoked by hot and cold thermal stimuli in the absence of facial edema pyrexia or dysphagia so I should see a |
| everyday | For 4 days I keep getting throbbing pain in 1 bottom back tooth whenever I have hot and cold drinks but I have no facial swelling fever or trouble swallowing so I should see a |
| medical_paraphrase | Over 4 days I developed pulsatile mandibular molar odontalgia in 1 tooth elicited by hot and cold liquids without facial edema pyrexia or dysphagia so I should see a |
| everyday_paraphrase | Across the past 4 days 1 lower back tooth has had an intense throbbing ache with hot and cold drinks and no swollen face fever or swallowing trouble so I should see a |
| changed_fact | For 4 days I keep getting throbbing pain in 1 bottom back tooth whenever I have hot and cold drinks and tonight jaw swelling started with high fever and trouble swallowing so I should see a |
| quad_b | For 4 days I keep getting pulsatile odontalgia in 1 mandibular molar whenever I have hot and cold thermal stimuli but I have no facial edema pyrexia or dysphagia so I should see a |
| quad_c | For 4 days I have experienced throbbing pain in 1 bottom back tooth provoked by hot and cold drinks in the absence of facial swelling fever or trouble swallowing so I should see a |

Changed fact `f4`: "but I have no facial swelling fever or trouble swallowing" became "and tonight jaw swelling started with high fever and trouble swallowing"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| throbbing pain | authors' summary | Cohen LA, Harris SL, Bonito AJ, Manski RJ, Cornelius LJ (2007). Coping with toothache pain PMID: 17436976; DOI: 10.1111/j.1752-7325.2007.00005.x | not given |
| an intense throbbing ache | authors' summary | Cohen LA, Harris SL, Bonito AJ, Manski RJ, Cornelius LJ (2007). Coping with toothache pain PMID: 17436976; DOI: 10.1111/j.1752-7325.2007.00005.x | not given |
| 1 bottom back tooth | no source |   |  |
| 1 lower back tooth | no source |   |  |
| hot and cold drinks | no source |   |  |
| no facial swelling fever or trouble swallowing | no source |   |  |
| no swollen face fever or swallowing trouble | no source |   |  |

Software findings: none.

## r9-10

Care level 3 · ends on "so I should see a" + "dermatologist" · split fresh_test · register stratum `register`

Label for reviewers only, in no text: cutaneous melanoma

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Patient is 68 years old
- `f2` Dark flat skin lesion on the upper back
- `f3` Enlarged with irregular borders over 3 months
- `f4` Absence of fever or surrounding skin redness

| Wording | Text |
|---|---|
| medical | At age 68 I have observed a pigmented macular nevus on my posterior trunk exhibiting irregular border expansion over 3 months in the absence of pyrexia or surrounding erythema so I should see a |
| everyday | At age 68 I saw a dark flat mole on my upper back that got wider jagged edges over 3 months and I have no fever or spreading redness so I should see a |
| medical_paraphrase | Now 68 years old I noted a flat pigmented nevus over my upper posterior trunk showing progressive border irregularity across 3 months without pyrexia or perilesional erythema so I should see a |
| everyday_paraphrase | I am 68 years old and noticed a flat dark mole on my upper back growing jagged uneven edges over the past 3 months without fever or red skin around it so I should see a |
| changed_fact | At age 68 I saw a dark flat mole on my upper back rubbed sore by my shirt for 2 weeks without changing shape and I have no fever or spreading redness so I should see a |
| quad_b | At age 68 I saw a pigmented macular nevus on my posterior trunk that got irregular border expansion over 3 months and I have no pyrexia or surrounding erythema so I should see a |
| quad_c | At age 68 I have observed a dark flat mole on my upper back exhibiting wider jagged edges over 3 months in the absence of fever or spreading redness so I should see a |

Changed fact `f3`: "that got wider jagged edges over 3 months" became "rubbed sore by my shirt for 2 weeks without changing shape"; right care after the change: level 2.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| a dark flat mole | authors' summary | Walter FM, Birt L, Cavers D, Scott S, Emery J, Burrows N, Cavanagh G, MacKie R, Weller D,  PMID: 25052174; DOI: 10.1136/bmjopen-2014-005566 | not given |
| jagged edges | authors' summary (quoting participant phrase 'jagged edges') | Walter FM, Birt L, Cavers D, Scott S, Emery J, Burrows N, Cavanagh G, MacKie R, Weller D,  PMID: 25052174; DOI: 10.1136/bmjopen-2014-005566 | not given |
| no fever or spreading redness | no source |   |  |

Software findings: 
- warning r9-10-chg: number: the everyday span drops ['3']
- warning r9-10-chg: number: the everyday span adds ['2']

## r9-11

Care level 3 · ends on "so I should see a" + "psychiatrist" · split discovery · register stratum `register`

Label for reviewers only, in no text: panic disorder with agoraphobia

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 4 months of episodes 3 times weekly lasting 15 minutes
- `f2` Sudden racing heartbeat and trembling
- `f3` Acute fear of losing control
- `f4` Public transit avoidance without chest pain or fainting

| Wording | Text |
|---|---|
| medical | For 4 months 3 times weekly I have had 15 minute paroxysms of palpitations and tremor with fear of losing control causing transit avoidance without thoracic pain or syncope so I should see a |
| everyday | For 4 months 3 times weekly I have had 15 minute waves of racing heart and trembling with fear of losing control keeping me off buses without chest pain or fainting so I should see a |
| medical_paraphrase | Across 4 months at a frequency of 3 episodes per week I experience 15 minute surges of autonomic palpitations and tremor with fear of losing control and transit avoidance without thoracic pain or syncope so I should see a |
| everyday_paraphrase | Over 4 months 3 times a week I get 15 minute rushes of a pounding heart and shaking with fear of losing control so I avoid buses despite no chest pain or fainting so I should see a |
| changed_fact | For 4 months 3 times weekly I have had 15 minute waves of racing heart and trembling with fear of losing control and right now I have crushing chest pain and fainted so I should see a |

Changed fact `f4`: "keeping me off buses without chest pain or fainting" became "and right now I have crushing chest pain and fainted"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| racing heart | authors' summary | Baker HJ, Hollywood A, Waite P (2022). Adolescents' lived experience of panic disorder: an PMID: 35668509; DOI: 10.1186/s40359-022-00849-x | not given |
| trembling | no source |   |  |
| a pounding heart and shaking | no source |   |  |
| fear of losing control | authors' summary | Baker HJ, Hollywood A, Waite P (2022). Adolescents' lived experience of panic disorder: an PMID: 35668509; DOI: 10.1186/s40359-022-00849-x | not given |
| keeping me off buses | no source |   |  |
| avoid buses | no source |   |  |
| without chest pain or fainting | no source |   |  |

Software findings: none.

## r9-12

Care level 3 · ends on "so I should see a" + "specialist" · split discovery · register stratum `register`

Label for reviewers only, in no text: early rheumatoid arthritis

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Patient is 66 years old with 8 weeks of symptoms
- `f2` Symmetric swelling and pain in knuckles of both hands
- `f3` Morning joint stiffness lasting 90 minutes
- `f4` Absence of injury fever or single hot red joint

| Wording | Text |
|---|---|
| medical | At age 66 for 8 weeks I have had symmetric metacarpophalangeal joint edema and arthralgia in both hands with 90 minute morning stiffness without trauma pyrexia or monoarticular erythema so I should see a |
| everyday | At age 66 for 8 weeks I have had swollen painful knuckles on both hands that stay stiff 90 minutes every morning without injury fever or a hot red joint so I should see a |
| medical_paraphrase | Now 66 years old over 8 weeks I developed symmetric edema and arthralgia across the metacarpophalangeal joints of both hands with 90 minutes of morning stiffness and no trauma pyrexia or focal erythema so I should see a |
| everyday_paraphrase | I am 66 years old and for 8 weeks the knuckles on both hands have been swollen and sore taking 90 minutes each morning to loosen up with no injury fever or hot red skin so I should see a |
| changed_fact | At age 66 for 8 weeks I have had swollen painful knuckles on both hands that stay stiff 90 minutes every morning and today my right wrist turned hot red and immobile with fever so I should see a |

Changed fact `f4`: "without injury fever or a hot red joint" became "and today my right wrist turned hot red and immobile with fever"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| swollen painful knuckles on both hands | authors' summary | Stack RJ, van Tuyl LHD, Sloots M, van de Stadt LA, Hoogland W, Maat B, Mallen CD, Tiwana R PMID: 24729397; DOI: 10.1093/rheumatology/keu159 | not given |
| stiff | authors' summary | Stack RJ, van Tuyl LHD, Sloots M, van de Stadt LA, Hoogland W, Maat B, Mallen CD, Tiwana R PMID: 24729397; DOI: 10.1093/rheumatology/keu159 | not given |
| loosen up | authors' summary | Stack RJ, van Tuyl LHD, Sloots M, van de Stadt LA, Hoogland W, Maat B, Mallen CD, Tiwana R PMID: 24729397; DOI: 10.1093/rheumatology/keu159 | not given |
| without injury fever or a hot red joint | no source |   |  |

Software findings: none.

## r9-13

Care level 2 · ends on "so I need to go to the" + "clinic" · split discovery · register stratum `register`

Label for reviewers only, in no text: uncomplicated acute cystitis

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Symptoms present for 2 days
- `f2` Burning pain during urination
- `f3` Frequent small volume urination
- `f4` Absence of flank or back pain
- `f5` Absence of fever and vomiting

| Wording | Text |
|---|---|
| medical | For 2 days I have experienced dysuria accompanied by urinary frequency in small volumes in the absence of flank tenderness or pyrexia with emesis so I need to go to the |
| everyday | For 2 days I keep getting burning when I pee and peeing tiny amounts often but I have no back pain or fever with vomiting so I need to go to the |
| medical_paraphrase | Over the past 2 days I developed acute dysuria and frequent small volume voiding without costovertebral angle pain or febrile emesis so I need to go to the |
| everyday_paraphrase | Over the past 2 days it has been stinging and burning when I pee with frequent tiny trips to the bathroom and no pain in my back or fever with throwing up so I need to go to the |
| changed_fact | For 2 days I keep getting burning when I pee and peeing tiny amounts often but I have no back pain yet today I got high fever shaking chills and nonstop vomiting so I need to go to the |
| quad_b | For 2 days I keep getting dysuria and urinary frequency in small volumes but I have no flank tenderness or pyrexia with emesis so I need to go to the |
| quad_c | For 2 days I have experienced burning when I pee accompanied by peeing tiny amounts often in the absence of back pain or fever with vomiting so I need to go to the |

Changed fact `f5`: "or fever with vomiting" became "yet today I got high fever shaking chills and nonstop vomiting"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| burning when I pee | authors' summary | Leydon GM, Turner S, Smith H, Little P, UTIS team (2010). Women's views about management a PMID: 20139217; DOI: 10.1136/bmj.c279 | not given |
| stinging and burning when I pee | authors' summary | Leydon GM, Turner S, Smith H, Little P, UTIS team (2010). Women's views about management a PMID: 20139217; DOI: 10.1136/bmj.c279 | not given |
| peeing tiny amounts often | no source |   |  |
| no back pain or fever with vomiting | no source |   |  |

Software findings: none.

## r9-14

Care level 2 · ends on "so I should see a" + "doctor" · split validation · register stratum `register`

Label for reviewers only, in no text: uncomplicated acute otitis media

Status: software passed · owner read: stale (the texts or the care level changed after this read; the decision is not carried over) · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Child is 4 years old with 2 days of symptoms
- `f2` Right ear pain and ear pulling
- `f3` Fever of 38 degrees Celsius
- `f4` Alert and drinking fluids well without swelling behind the ear

| Wording | Text |
|---|---|
| medical | My 4 year old daughter has had 2 days of right otalgia and auricular tugging accompanied by 38 Celsius pyrexia while maintaining normal alertness oral intake and no postauricular edema so I should see a |
| everyday | My 4 year old daughter has had 2 days of right ear pain and ear pulling plus 38 Celsius fever but still has good energy normal drinking and no swelling behind it so I should see a |
| medical_paraphrase | My 4 year old daughter has experienced 2 days of unilateral right otalgia auricular tugging and 38 Celsius pyrexia while remaining alert hydrated and free of postauricular swelling so I should see a |
| everyday_paraphrase | My 4 year old daughter has spent 2 days pulling her right ear with earache and a 38 Celsius fever while staying playful drinking well without swelling behind her ear so I should see a |
| changed_fact | My 4 year old daughter has had 2 days of right ear pain and ear pulling plus 38 Celsius fever and today became drowsy with stiff neck and red swelling behind it so I should see a |
| quad_b | My 4 year old daughter has had 2 days of right otalgia and auricular tugging plus 38 Celsius pyrexia but still has normal alertness oral intake and no postauricular edema so I should see a |
| quad_c | My 4 year old daughter has had 2 days of right ear pain and ear pulling accompanied by 38 Celsius fever while maintaining good energy normal drinking and no swelling behind it so I should see a |

Changed fact `f4`: "but still has good energy normal drinking and no swelling behind it" became "and today became drowsy with stiff neck and red swelling behind it"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| ear pulling | authors' summary (with direct parent quote 'she was pulling her ears') | Lee MC, Kavalieratos D, Alberty A, Groff D, Haralam MA, Shaikh N (2022). Parents' experien PMID: 35606702; DOI: 10.1186/s12875-022-01737-4 | not given |
| pulling her right ear | authors' summary (with direct parent quote 'she was pulling her ears') | Lee MC, Kavalieratos D, Alberty A, Groff D, Haralam MA, Shaikh N (2022). Parents' experien PMID: 35606702; DOI: 10.1186/s12875-022-01737-4 | not given |
| right ear pain | no source |   |  |
| earache | no source |   |  |
| good energy normal drinking and no swelling behind it | no source |   |  |
| staying playful drinking well without swelling behind her ear | no source |   |  |

Software findings: none.

## r9-15

Care level 2 · ends on "so I should see a" + "doctor" · split discovery · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: persistent uncomplicated acute gastroenteritis

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 6 days of symptoms following a recent trip
- `f2` Frequent nonbloody watery diarrhea
- `f3` Mild abdominal cramping
- `f4` Keeping fluids down with normal urination and no dizziness on standing

| Wording | Text |
|---|---|
| medical | For 6 days after a trip I have had frequent nonbloody watery diarrhea with mild abdominal cramping while tolerating oral hydration maintaining normal diuresis without orthostatic lightheadedness so I should see a |
| everyday | For 6 days after a trip I have had frequent watery loose motions with no blood and mild belly cramps while keeping drinks down peeing normally without dizziness standing so I should see a |
| medical_paraphrase | Since returning from travel 6 days ago I have experienced persistent watery diarrhea without hematochezia and mild abdominal cramps while retaining oral fluids with normal urine output and no postural dizziness so I should see a |
| everyday_paraphrase | Since a trip 6 days ago I keep having watery loose motions without blood and mild stomach cramps while holding fluids down passing urine normally and feeling steady on my feet so I should see a |
| changed_fact | For 6 days after a trip I have had frequent watery loose motions with no blood and mild belly cramps and today cannot keep water down stopped peeing and nearly faint standing so I should see a |

Changed fact `f4`: "while keeping drinks down peeing normally without dizziness standing" became "and today cannot keep water down stopped peeing and nearly faint standing"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| loose motions | authors' summary | Bitar Z, Abdelraouf HM, Maig RA, Maadarani O, Bitar ZZ, Dashti H (2024). Exploring Hypogly PMID: 39686534; DOI: 10.12659/AJCR.946133 | not given |
| mild belly cramps | no source |   |  |
| mild stomach cramps | no source |   |  |
| keeping drinks down peeing normally without dizziness standing | no source |   |  |
| holding fluids down passing urine normally and feeling steady on my feet | no source |   |  |

Software findings: none.

## r9-16

Care level 2 · ends on "so I need to go to the" + "clinic" · split fresh_test · register stratum `register`

Label for reviewers only, in no text: uncomplicated gastroesophageal reflux in pregnancy

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` At 24 weeks of pregnancy with 2 weeks of symptoms
- `f2` Burning chest sensation after meals with sour acid in the throat
- `f3` Worse when lying flat
- `f4` Absence of swallowing difficulty bloody vomit headache or blurred vision

| Wording | Text |
|---|---|
| medical | At 24 weeks of pregnancy for 2 weeks I have had postprandial retrosternal burning discomfort and acidic pharyngeal regurgitation during recumbency in the absence of dysphagia hematemesis cephalalgia or visual disturbance so I need to go to the |
| everyday | At 24 weeks of pregnancy for 2 weeks I have had burning in my chest after meals and throat acid lying flat with no swallowing pain bloody vomit headache or blurry vision so I need to go to the |
| medical_paraphrase | Now at 24 weeks gestation over 2 weeks I experience postprandial substernal burning with sour pharyngeal acid worse when supine and without dysphagia hematemesis cephalalgia or visual disturbance so I need to go to the |
| everyday_paraphrase | At 24 weeks pregnant over 2 weeks burning rises in my chest after eating with sour throat acid lying down and no swallowing pain blood headache or blurry sight so I need to go to the |
| changed_fact | At 24 weeks of pregnancy for 2 weeks I have had burning in my chest after meals and throat acid lying flat and 1 hour ago vomited red blood and felt faint so I need to go to the |

Changed fact `f4`: "with no swallowing pain bloody vomit headache or blurry vision" became "and 1 hour ago vomited red blood and felt faint"; right care after the change: level 4.

| Everyday expression | Declared support | Source | Evidence sentence |
|---|---|---|---|
| burning in my chest after meals | authors' summary | Jones R, Ballard K (2008). Healthcare seeking in gastro-oesophageal reflux disease: a qual PMID: 18334869; DOI: 10.1097/MEG.0b013e3282f2a5bd | not given |
| burning rises in my chest after eating | authors' summary | Jones R, Ballard K (2008). Healthcare seeking in gastro-oesophageal reflux disease: a qual PMID: 18334869; DOI: 10.1097/MEG.0b013e3282f2a5bd | not given |
| throat acid | authors' summary | Jones R, Ballard K (2008). Healthcare seeking in gastro-oesophageal reflux disease: a qual PMID: 18334869; DOI: 10.1097/MEG.0b013e3282f2a5bd | not given |
| sour throat acid | authors' summary | Jones R, Ballard K (2008). Healthcare seeking in gastro-oesophageal reflux disease: a qual PMID: 18334869; DOI: 10.1097/MEG.0b013e3282f2a5bd | not given |
| lying flat | no source |   |  |
| lying down | no source |   |  |
| no swallowing pain bloody vomit headache or blurry vision | no source |   |  |
| no swallowing pain blood headache or blurry sight | no source |   |  |

Software findings: 
- warning r9-16-chg: number: the everyday span adds ['1']
