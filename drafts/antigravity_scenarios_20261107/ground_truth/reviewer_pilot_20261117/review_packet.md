# Review packet: batch r10_reviewer_pilot8

Source: draft/antigravity-scenarios-20261107: 8 families of round10_20261112_rev1/families.json, drawn with seed 20261117, 2 per care level (SHA-256 `92cffb6791da338bb8da97067973130d632f068fcc67da66ee94879e0961d410`).

Design rules: `data/experiments/intake_design.v1.json` (`bc93653f26ed`). Status of those rules: draft, 2026-11-13: the items listed under decisions are as the owner decided on 2026-11-13; every other rule is proposed by the batch-intake change and not agreed. The owner agrees the rest by a commit that changes this line.

What has and has not been reviewed:

- **Software validation: passed** (0 errors, 0 warnings). These are structural checks by this command. It says nothing about clinical content or patient language.
- **Owner's read:** 8 kept. This is the owner's keep or exclude decision on a named version of the texts. It is not a clinician's review. It is recorded and shown in every output, and it does not gate confirmatory eligibility (decisions, 2026-11-13)
- **Domain review:** 8 domain review pending. A family is reviewed only when a clinician and a patient-language reviewer have both recorded their items; nothing in this packet does that.
- **Known concerns:** 9 open, 0 closed. A concern is closed only by its own recorded disposition. The owner keeping a family does not close it, and a review does not close it.
- **Sources:** 1 not checked, 17 record and sentence found. A check shows that the cited record exists and contains the evidence sentence. It does not show that patients in the family's population use the expression.

No model output appears in this packet.

Measured endpoint, when measured: the full-vocabulary probability of the first token of the family's declared target word at the position after the carrier phrase. It is not triage accuracy, the quality of an answer, evidence that a model understands a wording.

- Care tiers are not compared with each other: families at different tiers use different carrier phrases and target words, so their endpoints are probabilities of different tokens in different contexts.
- Strata are not pooled: a register contrast, a patient-explanation contrast and a syntax crossing are different manipulations.

## r10-01

Care level 4 · ends on "so I need to go to the" + "ER" · split unassigned · register stratum `register`

Label for reviewers only, in no text: cauda equina syndrome

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` Lifted a heavy box 4 days ago
- `f2` Low back pain radiating down the left leg
- `f3` Numbness in the left toes
- `f4` Unable to urinate today

| Wording | Text |
|---|---|
| medical | I lifted a heavy box 4 days ago and developed left lumbosacral radiculopathy accompanied by left toe paresthesia and acute urinary retention today so I need to go to the |
| everyday | I lifted a heavy box 4 days ago and got low back pain down my left leg with numb left toes and cannot pee today so I need to go to the |
| medical_paraphrase | I lifted a heavy crate 4 days ago and experienced left lower limb radicular back pain with paresthesia of my left toes and acute urinary retention today so I need to go to the |
| everyday_paraphrase | I picked up a heavy box 4 days ago and got low back pain running down my left leg with numbness of my left toes and cannot pee today so I need to go to the |
| changed_fact | I lifted a heavy box 4 days ago and got low back pain down my left leg with numb left toes and can pee normally today so I need to go to the |
| everyday_attribution | I lifted a heavy box 4 days ago and got low back pain down my left leg with numb left toes and cannot pee today and I think I pulled a muscle so I need to go to the |
| quad_b | I lifted a heavy box 4 days ago and got left lumbosacral radiculopathy with left toe paresthesia and acute urinary retention today so I need to go to the |
| quad_c | I lifted a heavy box 4 days ago and developed low back pain down my left leg accompanied by numb left toes and inability to pee today so I need to go to the |

Changed fact `f4`: "and cannot pee today" became "and can pee normally today"; right care after the change: level 2.

Patient explanation (adds a belief, analysed apart from register): "and I think I pulled a muscle"; source: none (none).

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| low back pain | authors' summary | record and sentence found | Kumar N, Patralekh MK, Jacob RV, Kumar S, Gowda MB (2026). Adolescent Cauda Equina Seconda PMID: 42597798; DOI: 10.13107/jocr.2026.v16.i08.7832 | A 13-year-old male child presented to us in the emergency department with complaints of low back pain, weakness, and urinary incontinence following lifting of a heavy weight 25 days back. |
| numbness of my left toes | authors' summary | record and sentence found | Wang S, Shang J (2026). Cauda equina cavernous malformation with nerve fascicle involvemen PMID: 42991049; DOI: 10.3389/fsurg.2026.2004471 | A 51-year-old woman was admitted with a four-year history of low back discomfort, numbness of the right fourth and fifth toes, and bowel and urinary urgency. ... Over subsequent years, urgency and right toe numbness increased, and occasional numbness developed in the left fourth and fifth toes. |
| down my left leg | no source |  |   |  |
| numb left toes | no source |  |   |  |
| cannot pee | no source |  |   |  |

Known concerns: 1 open, 0 closed.
- `r10-01-c1` **open** · fact parity · applies to reg · In the first version the everyday wording said 'numb toes' where the fact and the medical wording say the left toes. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: revised pending reread: Changed by the author's second version (9a495c763): every everyday text now says 'numb left toes'. Open until a person confirms it.

Software findings: none.

## r10-03

Care level 4 · ends on "so I need to go to the" + "hospital" · split unassigned · register stratum `register_with_dialect` (flags: dialect)

Label for reviewers only, in no text: spreading lower limb skin infection with syncope

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

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

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| fell out | dictionary definition | not checked | Wiktionary contributors (verified 2026-11-09 in dialect_lexicon_20261109.json). Entry 'fal https://en.wiktionary.org/wiki/fall_out | # {{lb|en|dialect|intransitive}} To [[pass out]]. |
| falling out | authors' summary | record and sentence found | Mas C (2022). "Falling-Out" in Miami and the History of Culture in American Medicine. Bull PMID: 35370146; DOI: 10.1353/bhm.2022.0003 | In the 1970s, after playing a leading role in the organization of medical anthropology, Hazel Weidman uncovered a condition that Miami residents called "falling-out." |
| spreading hot red right calf swelling | no source |  |   |  |

Known concerns: 1 open, 0 closed.
- `r10-03-c1` **open** · control level disputed · applies to chg · The control (age 68, 3 days of spreading hot red calf swelling, 39 C fever, no fainting) is labelled a general doctor; that is arguably still urgent. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending clinical review: Left pending clinical review at the owner's instruction of 2026-11-12. It does not invalidate the register pair.

Software findings: none.

## r10-10

Care level 3 · ends on "so I should see a" + "dermatologist" · split unassigned · register stratum `register`

Label for reviewers only, in no text: chronic scaly plaque eruption refractory to topical therapy

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 4 months of red scaly plaques or patches on both elbows
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

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| red patches | authors' summary | record and sentence found | Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and co PMID: 41544022; DOI: 10.1371/journal.pone.0329066 | Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin. |
| silvery scales | authors' summary | record and sentence found | Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and co PMID: 41544022; DOI: 10.1371/journal.pone.0329066 | Psoriasis is a chronic autoimmune skin condition characterized by the rapid growth of skin cells, leading to thick, silvery scales and itchy, dry, and red patches on the skin. |
| shedding flakes | authors' summary | record and sentence found | Che Awanis CJ, Norhayati MN, Mat Yudin Z (2026). Beyond the skin: Lived experiences and co PMID: 41544022; DOI: 10.1371/journal.pone.0329066 | One respondent shared that she felt burdened because her skin kept shedding flakes onto the office carpet. |
| nail pits | no source |  |   |  |
| without raw skin sloughing today | no source |  |   |  |

Known concerns: 2 open, 0 closed.
- `r10-10-c1` **open** · stated negative · applies to reg · The texts state a negative ('without raw skin sloughing today') that a patient would rarely volunteer. It is kept: it is the fact the control changes. Reviewer's reading of how plausible it is in a patient's mouth: unlikely. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending patient language review: Retained at the owner's instruction of 2026-11-12: the negative carries information and is not deleted. Whether a patient would say it is for the patient-language reviewer.
- `r10-10-c2` **open** · control adds fact · applies to chg · The control changes fact f3 and gives the sloughing a place ('across my chest') that the fact does not name. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending clinical review: Not revised.

Software findings: none.

## r10-14

Care level 3 · ends on "so I should see a" + "specialist" · split unassigned · register stratum `register`

Label for reviewers only, in no text: treatment refractory heavy menstrual bleeding

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

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

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| heavy periods | direct patient quote | record and sentence found | Drejza M, Nicholson LS, Paquette G, Chawla M, Vale CL, Rogozińska E, Moss N, Hutchinson-Pa PMID: 42324234; DOI: 10.1111/1471-0528.70290 | Several participants described diagnosed mental health conditions, with one reporting, ‘I have been diagnosed with PTSD due to my heavy periods, hemorrhages and endometriosis. This followed with crippling anxiety’ (P79). |
| big clots | no source |  |   |  |
| without fainting today | no source |  |   |  |
| and I think heavy periods are normal for me | authors' summary | record and sentence found | Taree NA, Rich R, Zhu N, Khalife R, Wu CM, Sun HWL (2026). Barriers and facilitators for m PMID: 42971550; DOI: 10.1503/cmaj.252102 | They reported that misogyny, lack of knowledge of normal versus abnormal menses, and the normalization of female suffering deter care-seeking and delay diagnosis (Table 3). |

Known concerns: 1 open, 0 closed.
- `r10-14-c1` **open** · stated negative · applies to reg · The texts state a negative ('without fainting today') that a patient would rarely volunteer. It is kept: it is the fact the control changes. Reviewer's reading of how plausible it is in a patient's mouth: possible. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending patient language review: Retained at the owner's instruction of 2026-11-12: the negative carries information and is not deleted. Whether a patient would say it is for the patient-language reviewer.

Software findings: none.

## r10-16

Care level 2 · ends on "so I should see a" + "doctor" · split unassigned · register stratum `register`

Label for reviewers only, in no text: subacute fatigue cold intolerance and weight gain syndrome

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 3 months of daily fatigue and feeling cold with a 6 kg weight gain
- `f2` Dry skin and hard infrequent stools
- `f3` Fully alert and oriented today

| Wording | Text |
|---|---|
| medical | I have had 3 months of persistent fatigue and cold intolerance with a 6 kg weight gain accompanied by cutaneous dryness and constipation with intact mental alertness today so I should see a |
| everyday | I have had 3 months of daily tiredness and feeling cold with a 6 kg weight gain plus dry skin and hard infrequent stools while staying fully alert today so I should see a |
| medical_paraphrase | I experienced 3 months of daily fatigue and cold intolerance with a 6 kg weight gain plus cutaneous dryness and constipation while remaining alert and oriented today so I should see a |
| everyday_paraphrase | I spent 3 months feeling tired and cold every day with a 6 kg weight gain plus dry skin and constipation while staying clear headed today so I should see a |
| changed_fact | I have had 3 months of daily tiredness and feeling cold with a 6 kg weight gain plus dry skin and hard infrequent stools and became confused and barely awake today so I should see a |
| quad_b | I have had 3 months of persistent fatigue and cold intolerance with a 6 kg weight gain plus cutaneous dryness and constipation while staying mentally alert today so I should see a |
| quad_c | I have had 3 months of daily tiredness and feeling cold with a 6 kg weight gain accompanied by dry skin and hard infrequent stools with full alertness today so I should see a |

Changed fact `f3`: "while staying fully alert today" became "and became confused and barely awake today"; right care after the change: level 4.

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| weight gain | authors' summary | record and sentence found | Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic Ma PMID: 42800981; DOI: 10.7759/cureus.115269 | Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being. |
| dry skin | authors' summary | record and sentence found | Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic Ma PMID: 42800981; DOI: 10.7759/cureus.115269 | Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being. |
| constipation | authors' summary | record and sentence found | Lathiya PN, Patel PJ, Mangukiya R, Goti HS, Parmar VJ, Kulkarni AP (2026). Homoeopathic Ma PMID: 42800981; DOI: 10.7759/cureus.115269 | Its clinical presentation ranges from minimal or non-specific symptoms to overt disease associated with fatigue, cold intolerance, weight gain, constipation, dry skin, hair changes, menstrual disturbance, cognitive complaints, and impaired functional well-being. |
| daily tiredness and feeling cold | no source |  |   |  |
| hard infrequent stools | no source |  |   |  |

Known concerns: 1 open, 0 closed.
- `r10-16-c1` **open** · stated negative · applies to reg · The texts state a negative ('while staying fully alert today') that a patient would rarely volunteer. It is kept: it is the fact the control changes. Reviewer's reading of how plausible it is in a patient's mouth: unlikely. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending patient language review: Retained at the owner's instruction of 2026-11-12: the negative carries information and is not deleted. Whether a patient would say it is for the patient-language reviewer.

Software findings: none.

## r10-17

Care level 2 · ends on "so I need to go to the" + "clinic" · split unassigned · register stratum `register`

Label for reviewers only, in no text: pediatric acute purulent ocular discharge

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

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

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| red eyes | authors' summary | record and sentence found | Muse YH, Hassan MA, Ali M, Muse AH, Nadarajah S (2026). A pediatric case of measles with g PMID: 42437059; DOI: 10.1016/j.idcr.2026.e02657 | A 4.5-year-old girl from an urban area presented with fever, vomiting, diarrhea, red eyes, and poor oral intake. |
| thick yellow pus gluing his eyelids shut on waking | no source |  |   |  |
| while moving both eyes easily today | no source |  |   |  |

Known concerns: 1 open, 0 closed.
- `r10-17-c1` **open** · stated negative · applies to reg · The texts state a negative ('while moving both eyes easily today') that a patient would rarely volunteer. It is kept: it is the fact the control changes. Reviewer's reading of how plausible it is in a patient's mouth: unlikely. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending patient language review: Retained at the owner's instruction of 2026-11-12: the negative carries information and is not deleted. Whether a patient would say it is for the patient-language reviewer.

Software findings: none.

## r10-21

Care level 1 · ends on "so I just need some" + "cream" · split unassigned · register stratum `new_carrier` (flags: new_carrier)

Label for reviewers only, in no text: mild uncomplicated toe web scaling

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 5 days of mild itchy peeling skin between the 4th and 5th left toes after gym showers
- `f2` No pus

| Wording | Text |
|---|---|
| medical | I have had 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers without purulent exudate so I just need some |
| everyday | I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers with no pus so I just need some |
| medical_paraphrase | I developed 5 days of mild pruritic scaling and peeling in the 4th and 5th left interdigital toe web after gym showers without purulence so I just need some |
| everyday_paraphrase | I got 5 days of mild itchy flaking skin between my 4th and 5th left toes after gym showers and no pus at all so I just need some |
| changed_fact | I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers oozing thick yellow pus so I just need some |
| quad_b | I have had 5 days of mild pruritic interdigital desquamation between my 4th and 5th left toes after gym showers with no purulent exudate so I just need some |
| quad_c | I have had 5 days of mild itchy peeling skin between my 4th and 5th left toes after gym showers without pus so I just need some |

Changed fact `f2`: "with no pus" became "oozing thick yellow pus"; right care after the change: level 2.

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| peeling | authors' summary | record and sentence found | Kutlu O, Cetinkaya PO, Yavuz G, Khachemoune A (2025). Turkish Bath-Associated Infectious D PMID: 41700199; DOI: 10.14744/SEMB.2025.54782 | Tinea pedis manifests as either interdigital erythema with scaling, peeling, and maceration—especially between the fourth and fifth toes—hyperkeratotic thick scaly erythematous plaques on the soles, heels, and sides of the feet, or vesiculobullous intensely pruritic vesicles/bullae on an erythematous base. |
| itchy peeling skin between my 4th and 5th left toes | no source |  |   |  |
| with no pus | no source |  |   |  |

Known concerns: 1 open, 0 closed.
- `r10-21-c1` **open** · stated negative · applies to reg · The texts state a negative ('with no pus') that a patient would rarely volunteer. It is kept: it is the fact the control changes. Reviewer's reading of how plausible it is in a patient's mouth: plausible. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending patient language review: Retained at the owner's instruction of 2026-11-12: the negative carries information and is not deleted. Whether a patient would say it is for the patient-language reviewer.

Software findings: none.

## r10-23

Care level 1 · ends on "so I just need some" + "lotion" · split unassigned · register stratum `new_carrier` (flags: new_carrier)

Label for reviewers only, in no text: mild winter lower leg skin dryness

Status: software passed · owner read: kept · clinician: not_reviewed · patient language: not_reviewed · overall: **domain_review_pending**

Reference facts:

- `f1` 7 days of mild dry flaky itchy skin on both shins in cold winter air
- `f2` No pus bumps

| Wording | Text |
|---|---|
| medical | I have had 7 days of mild cutaneous dryness with fine desquamation and pruritus on both shins in winter weather without pustules so I just need some |
| everyday | I have had 7 days of mild dry skin with flakiness and itching on both shins in winter weather with no pus bumps so I just need some |
| medical_paraphrase | I developed 7 days of mild bilateral pretibial cutaneous dryness with scaling and pruritus in cold winter air without pustular lesions so I just need some |
| everyday_paraphrase | I got 7 days of mild dry flaky itchy skin on both shins in cold winter weather without any pus bumps so I just need some |
| changed_fact | I have had 7 days of mild dry skin with flakiness and itching on both shins in winter weather with painful yellow pus bumps so I just need some |
| quad_b | I have had 7 days of mild cutaneous dryness with fine desquamation and pruritus on both shins in winter weather with no pustules so I just need some |
| quad_c | I have had 7 days of mild dry skin with flakiness and itching on both shins in winter weather without pus bumps so I just need some |

Changed fact `f2`: "with no pus bumps" became "with painful yellow pus bumps"; right care after the change: level 2.

| Everyday expression | Declared support | Citation check | Source | Evidence sentence |
|---|---|---|---|---|
| dry skin | authors' summary | record and sentence found | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | This multi‐omics insight provides a foundation for the targeted management of dry skin. |
| flakiness | authors' summary | record and sentence found | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | Dry skin, marked by flakiness and a rough texture, is a key contributor to various skin issues, primarily caused by a compromised skin barrier that results in moisture loss [23]. |
| itching | authors' summary | record and sentence found | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | Xerosis, marked by a compromised skin barrier and disrupted lipid metabolism, leads to dryness, scaling, and itching. |
| shins | authors' summary | record and sentence found | Wang J, Cheng L, Zhang J, Qin Y, Fu Q, Bai X, Qi F, Wu F, Yang J, Pan Y (2026). Comprehens PMID: 41622615; DOI: 10.1111/jocd.70711 | Xerosis predominantly manifests on the lower extremities, particularly the shins and calves, where the density of sebaceous glands is minimal and transepidermal water loss is pronounced [3]. |
| with no pus bumps | no source |  |   |  |

Known concerns: 1 open, 0 closed.
- `r10-23-c1` **open** · stated negative · applies to reg · The texts state a negative ('with no pus bumps') that a patient would rarely volunteer. It is kept: it is the fact the control changes. Reviewer's reading of how plausible it is in a patient's mouth: plausible. (raised by Claude review session (a model's reading; not a clinician's or a patient-language reviewer's), 2026-11-12). Disposition: pending patient language review: Retained at the owner's instruction of 2026-11-12: the negative carries information and is not deleted. Whether a patient would say it is for the patient-language reviewer.

Software findings: none.
