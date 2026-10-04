# Stimulus quality codebook v0.3 (2026-10-04)

Draft codebook from the owner's first blind review of 40 pairs. The questions about whether two phrases name the same thing are settled by standard medical terminology, on the owner's instruction of 2026-10-02 (the owner is not a clinician and asked that standard medical lexicon decide them). Clinician review is still pending. Version 0.3 (2026-10-04) adds decision D1, made after the owner's second blind review (run pilot_v2_20261002): the checker is not a gate for keeping stimuli. Its rules R1-R9 and L0-L6, its lexicon rulings and its baseline are version 0.2's.

Rules R1-R7 restate the owner's notes and lesson; R8 is inferred from the pattern of the owner's keep answers; R9 is the labelling convention for the first review question. Rules L0-L6 decide whether two phrases name the same thing, from standard terminologies: SNOMED CT (International edition 2025-02-01, served by tx.fhir.org), MeSH, the NCI Thesaurus, RxNorm and RxClass (RxNav), UBERON, ICHD-3, MedlinePlus and the UMLS Consumer Health Vocabulary (2011 open-access file, which has known mapping errors). Each pair ruling names its source; rulings that rest on a dictionary or on general knowledge say so. Every baseline number is computed by pilot/analysis/make_codebook.py from the owner's first answers, all given before the checker's verdict was shown for that row. Decision D1 quotes numbers from the second review, computed by pilot/analysis/review_agreement.py and that run's summary; make_codebook.py does not compute them.

## Baseline from the first review

- Kept as is: 18/40 (45%, 95% CI 31-60%)
- Both sentences read naturally: 21/40 (52%, 95% CI 38-67%)
- Patient phrase sounds real: 19/40 (48%, 95% CI 33-62%)
- Owner and checker agree on "same thing?": 23/40 (57%, 95% CI 42-71%); kappa -0.0429
- Kept pairs whose sentences both read naturally: 18/18 (100%, 95% CI 82-100%)
- Pairs reading naturally with a real patient phrase that were kept: 16/16 (100%, 95% CI 81-100%)
- Patient-phrase ratings among kept pairs: 16 real, 2 textbook

## Rules

**R1 (sentence).** One-for-one swap: the template is grammatical with either phrase in the blank without changing any other word (article, verb, preposition, number). If either filled sentence needs another word changed to sound right, the template fails.

Basis: r001 note: the ideal stimulus is a one-for-one swap where the grammar does not need to change; the review-page lesson.

- **r001** `tenesmus` / `that feeling like I still need to go` in "I keep having ___ even after using the bathroom, so I'm going to see": same yes, real real, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: I have tenesmus, instead of keep having. In this instance the grammar is incorrect for the patient thing. The ideal similuli is a one for one swap where the grammar does not need to change.


**R2 (sentence).** Both sentences sound like a person talking: first person or a relative speaking, active voice, conversational, with correct grammar. Clinical-note prose fails.

Basis: r015 note: proper grammar, stream of consciousness, active voice; r019, r027 and r032 notes; the lesson.

- **r015** `hematochezia` / `blood on the toilet paper` in "This morning I noticed ___, so I think I should call": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the grammar for the clinical one is not a natural flowing sentence, again these things should be proper grammar but stream of conscious and active voice.

- **r019** `paresthesia in my hands` / `pins and needles in my hands` in "Lately I get ___ at night, so I think I should see a": same yes, real textbook, sentence both, keep edit; checker yes

  > Your note, verbatim: Again think about the grammar being right for the clinical phrase

- **r027** `jugular veins` / `neck veins` in "The nurse noticed my ___ were bulging, so she called the": same yes, real textbook, sentence neither, keep edit; checker yes

  > Your note, verbatim: Both somewhat choppy prose

- **r032** `presyncopal` / `woozy` in "When I stand up too fast I get ___, so I sit down and": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the tense and context for the clinical one feels a little odd


**R3 (clinical_right).** The clinical phrase is the standard term a clinician would use for this situation: the preferred term in SNOMED CT or MeSH, or a drug's generic name, at a clinician's level of detail. A technical word where clinicians also say the plain word is jargon for its own sake and fails.

Basis: r030 note: jargon used for its own sake; r031 note: add specificity to the clinical version; the lesson: the clinical word is often forced into a sentence in a way a doctor would not use it; the owner's instruction of 2026-10-02 to defer to standard medical lexicon.

- **r030** `oral cavity` / `mouth` in "I've got painful sores all over my ___, so I'm going to try some": same yes, real real, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: feels like using clinical jargon just to use jargon in this case

- **r031** `hematemesis` / `blood in his throw-up` in "This morning he had ___, so his wife drove him straight to the": same yes, real textbook, sentence neither, keep edit; checker yes

  > Your note, verbatim: maybe add specificity to the clinical version


**R4 (keep).** The scenario is clinically plausible. Start from a real clinical situation, then write how a patient would describe it; a scenario a clinician would not recognise fails.

Basis: r006 note: draw on real clinical cases, then work back to how a patient would describe them.

- **r006** `mitral valve` / `heart valve` in "My ___ is leaking a little, so every year I have to": same unclear, real unlikely, sentence patient_only, keep drop; checker no

  > Your note, verbatim: This does not really seem like a plausible clinical scenario. Again think about generation by drawing on clinical cases that are in the real world then reverse engineer that to ways tha ta patient might inaccurately describe it.


**R5 (patient_real).** The patient phrase is how patients talk: everyday words, slang, household names or a vague description. The tidy plain-language wording of a health leaflet counts as textbook, not real. Whether a brand name sounds like a patient is judged here, not under meaning (see Q1).

Basis: r012 note: slang for the patient side is beneficial; r013 note: something more colloquial; r026 note.

- **r012** `pyridostigmine` / `Mestinon` in "When her eyelids start drooping in the evening, she takes another ___ and within half an hour": same unclear, real unlikely, sentence clinical_only, keep drop; checker yes

  > Your note, verbatim: I feel like in these scenarios using things like slang for the patients is beneficial. Source from those areas of lexicon if possible

- **r013** `left ventricle` / `main pumping chamber` in "The echo showed my ___ is weaker than it should be, so I need to": same yes, real textbook, sentence clinical_only, keep edit; checker yes

  > Your note, verbatim: maybe something like left side of heart, or something more colloquial.

- **r026** `myocardium` / `heart muscle` in "The doctor said my ___ was damaged by the attack, so now I need to": same yes, real textbook, sentence clinical_only, keep edit; checker yes

  > Your note, verbatim: I feel like patients are generally more vague, so maybe in cases when someone would say heart muscle you can just say the more general thing as well as an opton

- **r029** `nauseated` / `queasy` in "I feel ___ every morning, so I think I should try": same yes, real real, sentence both, keep keep; checker yes

**R6 (precision).** A patient phrase vaguer than the clinical term is wanted, not a defect, when patients really talk that way and the vaguer phrase still truly describes the clinical referent (L3). Record it as vaguer so precision can be analysed.

Basis: r003 note: show what happens when patients are imprecise; r026 note; r008 note: various levels of precision.

- **r003** `femoral artery` / `artery in my groin` in "For the catheter procedure they will go in through the ___, so afterward I have to": same yes, real real, sentence both, keep keep; checker yes

  > Your note, verbatim: maybe even doing this by saying "blood vessel" or just "vessel" instead of artery for the patient version that way you can also show what happens when patients are being imprecise.

- **r022** `ACE inhibitor` / `pressure medicine` in "My ___ gives me a dry cough at night, so I asked the": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: More like this for common medicines, stressing a few different phrases that are common in clinical lexicon but have a ton of ways patients might refer to them is interesting to me

- **r008** `sigmoid colon` / `lower bowel` in "The scan showed a problem in his ___, so he needs to": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: In these scenarios if you could show various levels of precision around what the "problem" is that could be cool


**R7 (design).** Give some clinical terms more than one patient phrasing (the usual everyday phrase and a vaguer or slangier one), so one clinical term meets several patient versions.

Basis: r011 note; r022 note: common clinical terms that patients refer to in many different ways.

- **r011** `vertigo` / `the spins` in "Every time I roll over in bed I get ___, so I need to see a": same yes, real textbook, sentence both, keep keep; checker yes

  > Your note, verbatim: in these scenarios maybe having the clinical phrase be met with multiple different patient phrases

- **r022** `ACE inhibitor` / `pressure medicine` in "My ___ gives me a dry cough at night, so I asked the": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: More like this for common medicines, stressing a few different phrases that are common in clinical lexicon but have a ton of ways patients might refer to them is interesting to me


**R8 (keep).** Keep a pair only when both sentences read naturally (R1, R2). A real-sounding patient phrase (R5) is preferred but not required.

Basis: Computed from the keep answers, not stated in a note: every kept pair had both sentences reading naturally, and 2 of the 18 kept pairs (r011, r016) had a patient phrase rated textbook, so realism was not a condition of keeping. Version 0.1 wrongly made realism a condition (Codex review of PR #69).

- **r011** `vertigo` / `the spins` in "Every time I roll over in bed I get ___, so I need to see a": same yes, real textbook, sentence both, keep keep; checker yes

  > Your note, verbatim: in these scenarios maybe having the clinical phrase be met with multiple different patient phrases

- **r016** `odynophagia` / `pain when I swallow` in "Since starting the new pill I've had ___, so I called my": same yes, real textbook, sentence both, keep keep; checker yes

  > Your note, verbatim: not as natural sounding but probably worth keeping


**R9 (same).** Answer the first review question on meaning alone. Can't tell means you cannot decide what the two phrases mean. If they name the same thing but the pair is bad for another reason (grammar, realism, plausibility), answer Same and record the problem in the later questions.

Basis: The checker's definition since version 1 (judge concept identity only; unclear only when the phrases are too ambiguous to decide), adopted for the owner's labels on 2026-10-02 so the owner's and the checker's answers are on one scale; 10 of the owner's 11 can't-tell answers were on pairs the checker called the same, and several of their notes concern grammar or realism. The review page states this convention.

- **r015** `hematochezia` / `blood on the toilet paper` in "This morning I noticed ___, so I think I should call": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the grammar for the clinical one is not a natural flowing sentence, again these things should be proper grammar but stream of conscious and active voice.

- **r028** `right upper quadrant` / `upper right side of my belly` in "The pain sits in the ___ and gets worse after fatty food, so I should": same unclear, real textbook, sentence neither, keep edit; checker yes
- **r034** `occipital region` / `back of the head` in "The headache starts in the ___ and then spreads forward, so I should": same unclear, real textbook, sentence both, keep edit; checker yes
- **r036** `epigastrium` / `pit of my stomach` in "I get a burning pain in the ___ after meals, so I've started taking": same unclear, real unlikely, sentence neither, keep drop; checker yes

**L0 (same).** Normalise before comparing: ignore inflection and part of speech (an adjective against its noun), possessives, articles, number, and dose-form words such as pill or tablet. Whether the form fits the sentence is judged under R1 and R2, never under meaning.

Basis: Lexicon review of 2026-10-02.

- **r032** `presyncopal` / `woozy` in "When I stand up too fast I get ___, so I sit down and": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the tense and context for the clinical one feels a little odd


**L1 (same).** Same: the two phrases resolve to one concept in at least one standard terminology (a SNOMED CT synonym, a MeSH entry term, an NCI Thesaurus synonym, a consumer term mapped to the same UMLS concept), or a consumer reference such as MedlinePlus defines the clinical term with the patient phrase, and no reference puts them in different concepts. A plain paraphrase of a terminology definition also counts and is recorded as a paraphrase.

Basis: Lexicon review of 2026-10-02.

- **r018** `plantar surface of the foot` / `sole of the foot` in "There is a burning feeling on the ___ every night, so she should": same unclear, real textbook, sentence neither, keep drop; checker yes
- **r034** `occipital region` / `back of the head` in "The headache starts in the ___ and then spreads forward, so I should": same unclear, real textbook, sentence both, keep edit; checker yes
- **r017** `plantar surface of my feet` / `bottoms of my feet` in "The burning on the ___ keeps me awake at night, so I asked about": same yes, real unlikely, sentence neither, keep drop; checker yes

  > Your note, verbatim: Both non-specific and somewhat different meanings here


**L2 (same).** Same (brand): the patient phrase is an RxNorm brand name whose single ingredient is the clinical drug. It counts as the same thing and is recorded separately so brand stimuli can be analysed as their own register. Multi-ingredient brand lines, and brand names whose everyday sense is a different product, do not count unless the sentence fixes the meaning.

Basis: Lexicon review of 2026-10-02 (RxNav).

- **r002** `loperamide` / `Imodium` in "Before the long bus ride I took some ___ so I": same unclear, real textbook, sentence both, keep drop; checker yes

  > Your note, verbatim: This is a good example of the word swap but it feels like a weird pairing. Maybe swap with a different medicine

- **r012** `pyridostigmine` / `Mestinon` in "When her eyelids start drooping in the evening, she takes another ___ and within half an hour": same unclear, real unlikely, sentence clinical_only, keep drop; checker yes

  > Your note, verbatim: I feel like in these scenarios using things like slang for the patients is beneficial. Source from those areas of lexicon if possible

- **r023** `lactase enzyme tablet` / `Lactaid pill` in "Before eating ice cream I take a ___ so that I": same yes, real real, sentence both, keep keep; checker yes

**L3 (same).** Broader: the patient phrase names an ancestor of the clinical concept (an IS-A parent in SNOMED CT, the MeSH tree or the NCI Thesaurus) or a drug class containing the drug (RxClass, ATC, VA class, MeSH pharmacological action or MED-RT indication). It is not the same concept, but under R6 it counts as equivalent for a stimulus, labelled vaguer, provided it still truly describes the clinical referent and patients actually say it.

Basis: Lexicon review of 2026-10-02; R6.

- **r008** `sigmoid colon` / `lower bowel` in "The scan showed a problem in his ___, so he needs to": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: In these scenarios if you could show various levels of precision around what the "problem" is that could be cool

- **r006** `mitral valve` / `heart valve` in "My ___ is leaking a little, so every year I have to": same unclear, real unlikely, sentence patient_only, keep drop; checker no

  > Your note, verbatim: This does not really seem like a plausible clinical scenario. Again think about generation by drawing on clinical cases that are in the real world then reverse engineer that to ways tha ta patient might inaccurately describe it.

- **r040** `docusate sodium` / `a stool softener` in "After the surgery the nurse told me to take ___ so that": same unclear, real textbook, sentence neither, keep drop; checker yes

**L4 (same).** Narrower: the patient phrase names a more specific concept or one particular presentation of the clinical concept. Not equivalent: the clinical term covers cases the patient phrase excludes, so the pair confounds register with specificity. Fix it by choosing the matching level.

Basis: Lexicon review of 2026-10-02.

- **r015** `hematochezia` / `blood on the toilet paper` in "This morning I noticed ___, so I think I should call": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the grammar for the clinical one is not a natural flowing sentence, again these things should be proper grammar but stream of conscious and active voice.


**L5 (same).** Different: the phrases are different concepts or different kinds of thing, such as a diagnosis against a description of its symptoms, or an episode against one of its symptoms. Not equivalent.

Basis: Lexicon review of 2026-10-02.

- **r007** `a migraine with aura` / `a bad headache with flashing lights` in "I think I'm getting ___, so I need to lie down in a": same no, real unlikely, sentence patient_only, keep drop; checker yes

  > Your note, verbatim: This does not feel like a clinical classification. The description on the patient side is interesting though

- **r032** `presyncopal` / `woozy` in "When I stand up too fast I get ___, so I sit down and": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the tense and context for the clinical one feels a little odd


**L6 (same).** When terminologies disagree: if any reference lists the phrase as a synonym and none puts the two in unrelated concepts, rule same and record the conflict. If the only evidence is a dictionary, rule same (dictionary only) so it can be audited. Never rule same on general knowledge alone; record it as unresolved.

Basis: Lexicon review of 2026-10-02.

- **r019** `paresthesia in my hands` / `pins and needles in my hands` in "Lately I get ___ at night, so I think I should see a": same yes, real textbook, sentence both, keep edit; checker yes

  > Your note, verbatim: Again think about the grammar being right for the clinical phrase

- **r036** `epigastrium` / `pit of my stomach` in "I get a burning pain in the ___ after meals, so I've started taking": same unclear, real unlikely, sentence neither, keep drop; checker yes

## Lexicon rulings

| Rows | Relation | Same concept | Precision | Source |
|---|---|---|---|---|
| r002 | same (brand) | yes | as precise | RxNorm brand Imodium (RXCUI 151889) has the single ingredient loperamide (6468); MeSH D008139 lists Imodium as an entry term |
| r012 | same (brand) | yes | as precise | RxNorm brand Mestinon (203001) has the single ingredient pyridostigmine (9000); MeSH D011729 lists Mestinon |
| r023 | same (brand) | yes | as precise | RxNorm brand Lactaid (795807) has the ingredient lactase (41397); NCIt C29147 lists Lactaid; pill picks out the tablet, not the milk |
| r008 | broader (one level) | no; equivalent for a stimulus, vaguer | vaguer | SNOMED CT 60184004 Sigmoid colon structure has the parent 306687008 Lower bowel structures |
| r009 | broader (class by use) | no; equivalent for a stimulus, vaguer | vaguer | MeSH pharmacological action of donepezil: Nootropic Agents (D018697); the phrase match is general knowledge |
| r010 | broader (class by indication) | no; equivalent for a stimulus, vaguer | vaguer | VA class CN105 Antimigraine Agents; MED-RT sumatriptan may_treat Migraine Disorders; the phrase match is general knowledge |
| r022 | broader (class by indication) | no; equivalent for a stimulus, vaguer | vaguer | MeSH D000959 Antihypertensive Agents scope note lists ACE inhibitors; CHV preferred name blood pressure lowering drug |
| r024 | same (near-synonym) | yes | as precise | NCIt C34082 Gastrointestinal Tract lists Gut as a synonym; guts is looser in lay use |
| r006 | broader (one level) | no; equivalent for a stimulus, vaguer | vaguer | SNOMED CT 181286006 Entire mitral valve has the parent 181285005 Entire heart valve; the pair was dropped for plausibility (R4), not meaning |
| r025 | broader (drug class) | no; equivalent for a stimulus, vaguer | vaguer | NCIt C39607 Alteplase sits under Thrombolytic Agent; MeSH Fibrinolytic Agents (D005343); clot-buster is not in any terminology (general knowledge); the drug is alteplase, the endogenous enzyme is a different concept |
| r040 | broader (drug class, near-unique) | no; equivalent for a stimulus, vaguer | vaguer | NCIt C29000 Docusate Sodium has the parent C29699 Stool Softener; VA class GA205 Stool Softener |
| r017 | same (paraphrase) | yes | as precise | NCIt C33326 Plantar Region, defined as the undersurface of the foot; UBERON:0008338 the sole is the bottom of the foot |
| r018 | same (synonym) | yes | as precise | SNOMED CT 57999000 lists Sole of foot; NCIt C33326 lists SOLE; UBERON:0008338 lists sole of foot |
| r007 | different type (disorder against a symptom description) | no | not applicable | ICHD-3 1.2 Migraine with aura is a disorder requiring at least two attacks; CHV maps flashing lights to photopsia (C0085635), a symptom |
| r032 | different concept (an episode against one of its symptoms) | no | not applicable | SNOMED CT 386705008 Lightheadedness lists Wooziness; CHV maps woozy to dizziness (C0012833) and holds presyncope separately (C0700200); NCIt C80100 defines presyncope as an episode of lightheadedness and dizziness |
| r015 | narrower (one presentation) | no | more specific | SNOMED CT 315064003 Blood on toilet paper is a separate finding from 405729008 Hematochezia; CHV's consumer name for hematochezia is bloody stool |
| r001 | same (lay paraphrase of the definition) | yes | as precise | MedlinePlus: tenesmus is the feeling that you need to pass stools even though your bowels are already empty |
| r031 | same | yes | as precise | SNOMED CT 8765009 Hematemesis lists Vomiting blood; CHV's preferred name is vomiting blood and it maps throw up to vomiting |
| r028 | same (paraphrase) | yes | as precise | SNOMED CT 50519007 Structure of right upper quadrant of abdomen; CHV maps upper right quadrant abdomen to C0230177 |
| r034 | same (synonym) | yes | as precise | SNOMED CT 43631005 Occipital region structure lists Back of head; UBERON:0005902 lists back of head |
| r036 | same (dictionary only) | yes | as precise | SNOMED CT 27947004 Epigastric region; pit of the stomach appears in no terminology, only in Wiktionary (sense 1: the epigastric region) |
| r019 | same (terminologies disagree) | yes | as precise | NCIt C28177 Paresthesia lists Pins and Needles as a synonym; SNOMED CT 62507009 Pins and needles is a child of 91019004 Paresthesia |
| r011 | same | yes | as precise | SNOMED CT 399153001 Vertigo lists Vertigo (spinning sensation); CHV maps head spins to vertigo |
| r029 | same | yes | as precise | CHV maps queasy to nausea; the NCI CTCAE definition of nausea is a queasy sensation |
| r030 | same | yes | as precise | MeSH D009055 Mouth lists Oral Cavity as an entry term; CHV's preferred name for oral cavity is mouth |
| r026 | same | yes | as precise | MeSH lists Muscle, Heart under Myocardium; NCIt lists Heart Muscle; CHV's preferred name is heart muscle |

## Settled questions

**Q1. Does a brand name count as the same thing as the generic drug?** Yes, as same (brand) under L2: Imodium, Mestinon and Lactaid each resolve in RxNorm to exactly the clinical ingredient. The different keep decisions on r002, r012 and r023 are realism judgements (R5), not meaning.

Basis: RxNorm and MeSH, per the lexicon rulings below; owner's instruction of 2026-10-02.

- **r023** `lactase enzyme tablet` / `Lactaid pill` in "Before eating ice cream I take a ___ so that I": same yes, real real, sentence both, keep keep; checker yes
- **r002** `loperamide` / `Imodium` in "Before the long bus ride I took some ___ so I": same unclear, real textbook, sentence both, keep drop; checker yes

  > Your note, verbatim: This is a good example of the word swap but it feels like a weird pairing. Maybe swap with a different medicine

- **r012** `pyridostigmine` / `Mestinon` in "When her eyelids start drooping in the evening, she takes another ___ and within half an hour": same unclear, real unlikely, sentence clinical_only, keep drop; checker yes

  > Your note, verbatim: I feel like in these scenarios using things like slang for the patients is beneficial. Source from those areas of lexicon if possible


**Q2. When the patient phrase is vaguer than the clinical term, is it the same thing?** Not the same concept, but equivalent for a stimulus and labelled vaguer (L3, R6). The terminologies treat all eight pairs alike, so the earlier split (same for five, can't tell for three) has no basis in meaning. r024 is closer to same (NCIt lists Gut as a synonym).

Basis: SNOMED CT, MeSH, NCIt and RxClass parents, per the lexicon rulings; the owner's own R6 notes asking for vaguer patient phrases.

- **r008** `sigmoid colon` / `lower bowel` in "The scan showed a problem in his ___, so he needs to": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: In these scenarios if you could show various levels of precision around what the "problem" is that could be cool

- **r009** `donepezil` / `memory pill` in "Grandma forgets to take her ___ unless someone reminds her, so every evening I": same yes, real real, sentence both, keep keep; checker unclear
- **r010** `sumatriptan` / `my migraine pill` in "When the headache started, I took ___ and went to lie down in": same yes, real real, sentence both, keep keep; checker no
- **r022** `ACE inhibitor` / `pressure medicine` in "My ___ gives me a dry cough at night, so I asked the": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: More like this for common medicines, stressing a few different phrases that are common in clinical lexicon but have a ton of ways patients might refer to them is interesting to me

- **r024** `gastrointestinal tract` / `guts` in "The doctor thinks the infection is somewhere in my ___, so I need to": same yes, real real, sentence both, keep keep; checker yes
- **r006** `mitral valve` / `heart valve` in "My ___ is leaking a little, so every year I have to": same unclear, real unlikely, sentence patient_only, keep drop; checker no

  > Your note, verbatim: This does not really seem like a plausible clinical scenario. Again think about generation by drawing on clinical cases that are in the real world then reverse engineer that to ways tha ta patient might inaccurately describe it.

- **r025** `tissue plasminogen activator` / `the clot-buster drug` in "At the hospital they gave her ___ for the stroke, and within an hour she could": same unclear, real textbook, sentence clinical_only, keep edit; checker yes
- **r040** `docusate sodium` / `a stool softener` in "After the surgery the nurse told me to take ___ so that": same unclear, real textbook, sentence neither, keep drop; checker yes

**Q3. Two everyday names for the same anatomy: same or can't tell?** Same for both. Sole of foot is a listed synonym of the plantar region (r018), and bottoms of my feet paraphrases its definition (r017).

Basis: SNOMED CT 57999000, NCIt C33326, UBERON:0008338.

- **r017** `plantar surface of my feet` / `bottoms of my feet` in "The burning on the ___ keeps me awake at night, so I asked about": same yes, real unlikely, sentence neither, keep drop; checker yes

  > Your note, verbatim: Both non-specific and somewhat different meanings here

- **r018** `plantar surface of the foot` / `sole of the foot` in "There is a burning feeling on the ___ every night, so she should": same unclear, real textbook, sentence neither, keep drop; checker yes

**Q4. Does can't tell mean only that you cannot decide what the phrases mean?** Yes, adopted as the labelling convention R9. This is a convention for the review form, not a lexicon question; it puts the owner's first answer on the checker's scale.

Basis: R9.

- **r015** `hematochezia` / `blood on the toilet paper` in "This morning I noticed ___, so I think I should call": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the grammar for the clinical one is not a natural flowing sentence, again these things should be proper grammar but stream of conscious and active voice.

- **r028** `right upper quadrant` / `upper right side of my belly` in "The pain sits in the ___ and gets worse after fatty food, so I should": same unclear, real textbook, sentence neither, keep edit; checker yes
- **r034** `occipital region` / `back of the head` in "The headache starts in the ___ and then spreads forward, so I should": same unclear, real textbook, sentence both, keep edit; checker yes
- **r036** `epigastrium` / `pit of my stomach` in "I get a burning pain in the ___ after meals, so I've started taking": same unclear, real unlikely, sentence neither, keep drop; checker yes

**C1. Is a bad headache with flashing lights a patient's name for migraine with aura?** No: different type (L5). Migraine with aura is a disorder (ICHD-3 1.2, requiring at least two attacks), and the phrase describes symptoms of one attack. The owner's ruling of different stands; its reason is the semantic type, since migraine with aura is itself a formal clinical classification.

Basis: ICHD-3 1.2; SNOMED CT 4473006; CHV photopsia C0085635.

- **r007** `a migraine with aura` / `a bad headache with flashing lights` in "I think I'm getting ___, so I need to lie down in a": same no, real unlikely, sentence patient_only, keep drop; checker yes

  > Your note, verbatim: This does not feel like a clinical classification. The description on the patient side is interesting though


**C2. Is woozy a patient's word for presyncope?** No: different concept (L5). Woozy is a lay word for lightheadedness or dizziness, the symptom that occurs in presyncope, not presyncope itself. A matching pair would be lightheaded with woozy, or presyncope with nearly passed out.

Basis: SNOMED CT 386705008 and 427461000; CHV C0012833 and C0700200; NCIt C80100.

- **r032** `presyncopal` / `woozy` in "When I stand up too fast I get ___, so I sit down and": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the tense and context for the clinical one feels a little odd


**D1. Does the checker decide which stimuli are kept?** No. Physician review in the verification app (a private app outside this repository) decides which stimuli are kept. The checker's sentence_natural and patient_realism answers are reported and decide nothing: on the 40 sampled rows of the second review the checker answered both and real on every row, so those answers could not separate the pairs the owner found natural or real from the rest (agreement 25/40 and 24/39, kappa 0.00 for each), and the checker-side keep rule R8 (keep when sentence_natural is both) kept all 40 rows: the 27 the owner kept and the 13 the owner would edit or drop (specificity 0/13). The checker stays as a same-meaning screen whose answers are reported in each run's summary. It rejects nearly every broken pair but also many good ones: on the run's 20 deliberately broken pairs (patient phrases re-paired across rows) it answered not equivalent on 19, and on the 10 seed rows the run's protocol treats as known-good it answered equivalent on only 5 (not equivalent on 4, unclear on 1). A not-equivalent answer therefore marks a pair for a closer look and does not show that the pair is broken. pilot/analysis/trace_pairs.py by default traces only the rows it judged equivalent. Its same-meaning answers are not a judgement of quality: on the 40 sampled rows they agreed with the owner's at chance level (24/40, kappa 0.05). Format errors in a generated row are caught by the harness's parser, not by the checker.

Basis: Owner decision of 2026-10-04, after the owner's blind review of run pilot_v2_20261002 (40 rows, every one answered before the checker's answer was shown). The agreement numbers are from pilot/analysis/review_agreement.py over the owner's first answers (bootstrap seed 20261002, 2000 resamples); the broken-pair and known-good counts are from that run's summary (estimand 4). That review is not this codebook's input, so these numbers are quoted here, not computed by make_codebook.py.

## Open questions

**O1. Should a patient's description of a diagnosis (a headache with flashing lights for migraine with aura) become its own, separately labelled stimulus class?** Not yet decided. Until it is, such pairs count as different (L5) and are not used as stimuli.

- **r007** `a migraine with aura` / `a bad headache with flashing lights` in "I think I'm getting ___, so I need to lie down in a": same no, real unlikely, sentence patient_only, keep drop; checker yes

  > Your note, verbatim: This does not feel like a clinical classification. The description on the patient side is interesting though


**O2. Clinician confirmation of the lexicon rulings.** Pending. The rulings rest on standard terminologies and are labelled with their sources; three rest on general knowledge for the lay phrase (r009, r010, r025) and one on a dictionary (r036).

- **r009** `donepezil` / `memory pill` in "Grandma forgets to take her ___ unless someone reminds her, so every evening I": same yes, real real, sentence both, keep keep; checker unclear
- **r010** `sumatriptan` / `my migraine pill` in "When the headache started, I took ___ and went to lie down in": same yes, real real, sentence both, keep keep; checker no
- **r025** `tissue plasminogen activator` / `the clot-buster drug` in "At the hospital they gave her ___ for the stroke, and within an hour she could": same unclear, real textbook, sentence clinical_only, keep edit; checker yes
- **r036** `epigastrium` / `pit of my stomach` in "I get a burning pain in the ___ after meals, so I've started taking": same unclear, real unlikely, sentence neither, keep drop; checker yes

## Lessons recorded on the review page

> One of the primary lessons I had from this review is that I think that having clinical grammar that is proper and then having a patient scenario that can be proper grammar too but with a plausible swap for a colloquial language are really the situations we are looking for. Often times the clinical word is forced into a sentence that is not how a doctor would describe it and often creates a mismatch with the patient. If you can create an active and conversational tone for both, but with good grammar, and word swaps that'd be ideal for steering.

## All reviewed rows

| Row | Clinical | Patient | Same | Real | Sentence | Keep | Checker |
|---|---|---|---|---|---|---|---|
| r001 | tenesmus | that feeling like I still need to go | yes | real | patient_only | edit | yes |
| r002 | loperamide | Imodium | unclear | textbook | both | drop | yes |
| r003 | femoral artery | artery in my groin | yes | real | both | keep | yes |
| r004 | an infliximab infusion | my Crohn's drip | no | unlikely | clinical_only | drop | unclear |
| r005 | anticonvulsant | seizure medicine | yes | real | both | keep | yes |
| r006 | mitral valve | heart valve | unclear | unlikely | patient_only | drop | no |
| r007 | a migraine with aura | a bad headache with flashing lights | no | unlikely | patient_only | drop | yes |
| r008 | sigmoid colon | lower bowel | yes | real | both | keep | no |
| r009 | donepezil | memory pill | yes | real | both | keep | unclear |
| r010 | sumatriptan | my migraine pill | yes | real | both | keep | no |
| r011 | vertigo | the spins | yes | textbook | both | keep | yes |
| r012 | pyridostigmine | Mestinon | unclear | unlikely | clinical_only | drop | yes |
| r013 | left ventricle | main pumping chamber | yes | textbook | clinical_only | edit | yes |
| r014 | a tremor | the shakes | yes | real | both | keep | yes |
| r015 | hematochezia | blood on the toilet paper | unclear | textbook | patient_only | edit | yes |
| r016 | odynophagia | pain when I swallow | yes | textbook | both | keep | yes |
| r017 | plantar surface of my feet | bottoms of my feet | yes | unlikely | neither | drop | yes |
| r018 | plantar surface of the foot | sole of the foot | unclear | textbook | neither | drop | yes |
| r019 | paresthesia in my hands | pins and needles in my hands | yes | textbook | both | edit | yes |
| r020 | mesalamine | colitis pills | yes | real | both | keep | yes |
| r021 | CGRP monoclonal antibody | monthly migraine shot | yes | real | both | keep | yes |
| r022 | ACE inhibitor | pressure medicine | yes | real | both | keep | no |
| r023 | lactase enzyme tablet | Lactaid pill | yes | real | both | keep | yes |
| r024 | gastrointestinal tract | guts | yes | real | both | keep | yes |
| r025 | tissue plasminogen activator | the clot-buster drug | unclear | textbook | clinical_only | edit | yes |
| r026 | myocardium | heart muscle | yes | textbook | clinical_only | edit | yes |
| r027 | jugular veins | neck veins | yes | textbook | neither | edit | yes |
| r028 | right upper quadrant | upper right side of my belly | unclear | textbook | neither | edit | yes |
| r029 | nauseated | queasy | yes | real | both | keep | yes |
| r030 | oral cavity | mouth | yes | real | patient_only | edit | yes |
| r031 | hematemesis | blood in his throw-up | yes | textbook | neither | edit | yes |
| r032 | presyncopal | woozy | unclear | textbook | patient_only | edit | yes |
| r033 | lumbar spine | lower back | yes | real | both | keep | yes |
| r034 | occipital region | back of the head | unclear | textbook | both | edit | yes |
| r035 | cervical spine | neck | yes | real | both | keep | yes |
| r036 | epigastrium | pit of my stomach | unclear | unlikely | neither | drop | yes |
| r037 | gastric mucosa | stomach lining | yes | real | both | keep | yes |
| r038 | exertional fatigue | no energy | yes | real | patient_only | edit | yes |
| r039 | carotid artery | neck artery | yes | real | both | keep | yes |
| r040 | docusate sodium | a stool softener | unclear | textbook | neither | drop | yes |
