# Stimulus quality codebook v0.1 (draft, 2026-10-01)

Decision rules for judging a generated clinical/patient stimulus pair, drawn from the owner's blind review of the 40-pair sample of run `pilot_real_20260930`. Rules R1-R7 restate the owner's notes and lesson; R8 is inferred from the pattern of keep answers. Open questions Q1-Q4 need the owner's ruling before the next protocol is frozen.

## Baseline from the first review

- Kept as is: 18/40 (45%, 95% CI 31-60%)
- Both sentences read naturally: 21/40 (52%, 95% CI 38-67%)
- Patient phrase sounds real: 19/40 (48%, 95% CI 33-62%)
- Agreement with the checker on "same thing?": 23/40 (57%, 95% CI 42-71%); kappa -0.04 (chance level)
- Every kept pair had both sentences natural: 18/18 (100%, 95% CI 82-100%); pairs with both sentences natural and a real patient phrase were kept 16/16 (100%, 95% CI 81-100%)

The checker judges only whether the two phrases name the same thing. The keep decisions follow sentence quality and patient realism, which no automated step judges yet.

## Rules

**R1 (sentence).** One-for-one swap: the template is grammatical with either phrase in the blank without changing any other word (article, verb, preposition, number). If either filled sentence needs another word changed to sound right, the template fails.
Basis: r001 note: the ideal stimulus is a one-for-one swap where the grammar does not need to change; lesson.

- **r001** `tenesmus` / `that feeling like I still need to go` in "I keep having ___ even after using the bathroom, so I'm going to see": same yes, real real, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: I have tenesmus, instead of keep having. In this instance the grammar is incorrect for the patient thing. The ideal similuli is a one for one swap where the grammar does not need to change.


**R2 (sentence).** Both sentences sound like a person talking: first person or a relative speaking, active voice, conversational, with correct grammar. Clinical-note prose fails.
Basis: r015 note: proper grammar, stream of consciousness, active voice; r019, r027, r032 notes; lesson.

- **r015** `hematochezia` / `blood on the toilet paper` in "This morning I noticed ___, so I think I should call": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the grammar for the clinical one is not a natural flowing sentence, again these things should be proper grammar but stream of conscious and active voice.

- **r019** `paresthesia in my hands` / `pins and needles in my hands` in "Lately I get ___ at night, so I think I should see a": same yes, real textbook, sentence both, keep edit; checker yes

  > Your note, verbatim: Again think about the grammar being right for the clinical phrase

- **r032** `presyncopal` / `woozy` in "When I stand up too fast I get ___, so I sit down and": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the tense and context for the clinical one feels a little odd


**R3 (clinical_right).** The clinical phrase is the term a clinician would use for this situation, at a clinician's level of detail. A technical word where clinicians also say the plain word is jargon for its own sake and fails.
Basis: r030 note: jargon used for its own sake; r031 note: add specificity to the clinical version; lesson: the clinical word is often forced into a sentence in a way a doctor would not use it.

- **r030** `oral cavity` / `mouth` in "I've got painful sores all over my ___, so I'm going to try some": same yes, real real, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: feels like using clinical jargon just to use jargon in this case

- **r031** `hematemesis` / `blood in his throw-up` in "This morning he had ___, so his wife drove him straight to the": same yes, real textbook, sentence neither, keep edit; checker yes

  > Your note, verbatim: maybe add specificity to the clinical version


**R4 (keep).** The scenario is clinically plausible. Start from a real clinical situation, then write how a patient would describe it; a scenario a clinician would not recognise fails.
Basis: r006 note: draw on real clinical cases, then work back to how a patient would describe them.

- **r006** `mitral valve` / `heart valve` in "My ___ is leaking a little, so every year I have to": same unclear, real unlikely, sentence patient_only, keep drop; checker no

  > Your note, verbatim: This does not really seem like a plausible clinical scenario. Again think about generation by drawing on clinical cases that are in the real world then reverse engineer that to ways tha ta patient might inaccurately describe it.


**R5 (patient_real).** The patient phrase is how patients talk: everyday words, slang, household names or a vague description. The tidy plain-language phrasing of a health leaflet counts as textbook, not real.
Basis: r012 note: slang for the patient side is beneficial; r013 note: something more colloquial; r026 note.

- **r012** `pyridostigmine` / `Mestinon` in "When her eyelids start drooping in the evening, she takes another ___ and within half an hour": same unclear, real unlikely, sentence clinical_only, keep drop; checker yes

  > Your note, verbatim: I feel like in these scenarios using things like slang for the patients is beneficial. Source from those areas of lexicon if possible

- **r013** `left ventricle` / `main pumping chamber` in "The echo showed my ___ is weaker than it should be, so I need to": same yes, real textbook, sentence clinical_only, keep edit; checker yes

  > Your note, verbatim: maybe something like left side of heart, or something more colloquial.

- **r026** `myocardium` / `heart muscle` in "The doctor said my ___ was damaged by the attack, so now I need to": same yes, real textbook, sentence clinical_only, keep edit; checker yes

  > Your note, verbatim: I feel like patients are generally more vague, so maybe in cases when someone would say heart muscle you can just say the more general thing as well as an opton

- **r029** `nauseated` / `queasy` in "I feel ___ every morning, so I think I should try": same yes, real real, sentence both, keep keep; checker yes

**R6 (precision).** A patient phrase vaguer than the clinical term is wanted, not a defect, when patients really talk that way; record it as vaguer so precision can be analysed.
Basis: r003 note: show what happens when patients are imprecise; r026 note; r008 note: various levels of precision.

- **r003** `femoral artery` / `artery in my groin` in "For the catheter procedure they will go in through the ___, so afterward I have to": same yes, real real, sentence both, keep keep; checker yes

  > Your note, verbatim: maybe even doing this by saying "blood vessel" or just "vessel" instead of artery for the patient version that way you can also show what happens when patients are being imprecise.

- **r022** `ACE inhibitor` / `pressure medicine` in "My ___ gives me a dry cough at night, so I asked the": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: More like this for common medicines, stressing a few different phrases that are common in clinical lexicon but have a ton of ways patients might refer to them is interesting to me

- **r008** `sigmoid colon` / `lower bowel` in "The scan showed a problem in his ___, so he needs to": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: In these scenarios if you could show various levels of precision around what the "problem" is that could be cool


**R7 (design).** Give some clinical terms more than one patient phrasing (for example the usual everyday phrase and a vaguer or slangier one), so one clinical term meets several patient versions.
Basis: r011 note; r022 note: common clinical terms that patients refer to in many different ways.

- **r011** `vertigo` / `the spins` in "Every time I roll over in bed I get ___, so I need to see a": same yes, real textbook, sentence both, keep keep; checker yes

  > Your note, verbatim: in these scenarios maybe having the clinical phrase be met with multiple different patient phrases

- **r022** `ACE inhibitor` / `pressure medicine` in "My ___ gives me a dry cough at night, so I asked the": same yes, real real, sentence both, keep keep; checker no

  > Your note, verbatim: More like this for common medicines, stressing a few different phrases that are common in clinical lexicon but have a ton of ways patients might refer to them is interesting to me


**R8 (keep).** Keep a pair only when both sentences read naturally (R1, R2) and the patient phrase sounds real (R5). Derived from the pattern of your keep answers, not stated in a note: confirm or change it.
Basis: computed: every kept pair had both sentences natural (sentence_both_given_keep); see baseline.

## Open questions for the owner

**Q1. Does a brand name count as the patient phrase?** Same and keep for a household brand (r023); can't tell and drop for two brand-for-generic pairs (r002, r012).

- **r023** `lactase enzyme tablet` / `Lactaid pill` in "Before eating ice cream I take a ___ so that I": same yes, real real, sentence both, keep keep; checker yes
- **r002** `loperamide` / `Imodium` in "Before the long bus ride I took some ___ so I": same unclear, real textbook, sentence both, keep drop; checker yes

  > Your note, verbatim: This is a good example of the word swap but it feels like a weird pairing. Maybe swap with a different medicine

- **r012** `pyridostigmine` / `Mestinon` in "When her eyelids start drooping in the evening, she takes another ___ and within half an hour": same unclear, real unlikely, sentence clinical_only, keep drop; checker yes

  > Your note, verbatim: I feel like in these scenarios using things like slang for the patients is beneficial. Source from those areas of lexicon if possible


**Q2. When the patient phrase is vaguer than the clinical term, is it the same thing?** Same for r008, r009, r010, r022, r024; can't tell for r006, r025, r040.

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

**Q3. Two everyday names for the same anatomy: same or can't tell?** Same for r017; can't tell for r018 (same clinical term, a different everyday phrase).

- **r017** `plantar surface of my feet` / `bottoms of my feet` in "The burning on the ___ keeps me awake at night, so I asked about": same yes, real unlikely, sentence neither, keep drop; checker yes

  > Your note, verbatim: Both non-specific and somewhat different meanings here

- **r018** `plantar surface of the foot` / `sole of the foot` in "There is a burning feeling on the ___ every night, so she should": same unclear, real textbook, sentence neither, keep drop; checker yes

**Q4. Does "can't tell" mean only "I can't decide whether they name the same thing"?** 11 of your answers were can't tell; the checker said same for 10 of them, and several of their notes are about grammar or realism rather than meaning (r015). If can't tell also carries "this pair is off", agreement with the checker cannot be read as a measure of the checker. Proposed: answer the first question on meaning alone and put every other problem in the later questions.

- **r015** `hematochezia` / `blood on the toilet paper` in "This morning I noticed ___, so I think I should call": same unclear, real textbook, sentence patient_only, keep edit; checker yes

  > Your note, verbatim: the grammar for the clinical one is not a natural flowing sentence, again these things should be proper grammar but stream of conscious and active voice.

- **r028** `right upper quadrant` / `upper right side of my belly` in "The pain sits in the ___ and gets worse after fatty food, so I should": same unclear, real textbook, sentence neither, keep edit; checker yes
- **r034** `occipital region` / `back of the head` in "The headache starts in the ___ and then spreads forward, so I should": same unclear, real textbook, sentence both, keep edit; checker yes
- **r036** `epigastrium` / `pit of my stomach` in "I get a burning pain in the ___ after meals, so I've started taking": same unclear, real unlikely, sentence neither, keep drop; checker yes

## Questions for a clinician

**C1.** Migraine with aura is a named diagnosis in the International Classification of Headache Disorders (ICHD-3, 1.2). The review marks it as not a clinical classification and the pair as different (r007). Is "a bad headache with flashing lights" a patient's name for it?

**C2.** Is "woozy" a patient's word for presyncope, or a different complaint (r032)?

## Lesson recorded on the review page

> One of the primary lessons I had from this review is that I think that having clinical grammar that is proper and then having a patient scenario that can be proper grammar too but with a plausible swap for a colloquial language are really the situations we are looking for. Often times the clinical word is forced into a sentence that is not how a doctor would describe it and often creates a mismatch with the patient. If you can create an active and conversational tone for both, but with good grammar, and word swaps that'd be ideal for steering.
