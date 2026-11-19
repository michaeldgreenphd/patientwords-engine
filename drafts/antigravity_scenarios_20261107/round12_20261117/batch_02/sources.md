# Round 12 Batch 02 Sources (`round12_20261117/batch_02`)

Every cited source in `families.json` (across both `everyday_sources` and `attribution`) is listed below with its `title`, `PMID` and `DOI` (or verified dictionary entry URL), `inspected_url`, what was directly opened (`access`: `full text` or `abstract only` — zero title-only sources), exact section/paragraph/sense `location`, `quote_type` (`"direct patient quote"`, `"authors' summary"`, or `"dictionary definition"`), exact verbatim `evidence`, and explicit `adaptation` separating the verbatim source text from how it was adapted into first-person scenario stimulus wording. No database identifiers other than `PMID` and `DOI` are used anywhere. Expressions and attribution clauses without a directly inspected Rule-B-compliant source sentence are marked `"source": "none"`.

## Scope and Provenance Disclaimers

- **Dictionary lexical-sense scope:** Dictionary entries cited in this batch (Wiktionary, Cambridge) attest lexical senses and grammatical definitions only and do **NOT** by themselves establish contemporary demographic or community frequency unless accompanied by a population source.
- **Synthetic test stimuli (not real patient records):** Source-inspired synthetic scenarios in `families.json` are test stimuli constructed for language-model evaluation, **NOT** real patient records; verbatim source excerpts (`evidence`) are recorded separately from first-person scenario adaptations (`adaptation`).

## 1. Hubsch A, Cashmore SJ, Mallick R, Gibbons B (2025). Experiences of Immunoglobulin Therapy for Those with a Confirmed Diagnosis of Chronic Inflammatory Demyelinating Polyneuropathy: A Mixed-Methods Study with a Qualitative Patient Perspective Focus. Patient Preference and Adherence.

- **Title:** Experiences of Immunoglobulin Therapy for Those with a Confirmed Diagnosis of Chronic Inflammatory Demyelinating Polyneuropathy: A Mixed-Methods Study with a Qualitative Patient Perspective Focus.
- **PMID / DOI / URL:** `PMID: 41409888; DOI: 10.2147/PPA.S543188`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41409888/`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-025` (everyday expression `"weakness in my legs"` — *direct patient quote*)
    - **Location:** `Results — Qualitative Patient Perspective (patient quote on lower-limb weakness)`
    - **Verbatim `evidence`:** `And because of the weakness in my legs during that first summer [after diagnosis], it almost stopped me from going out.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 2. Lei D, Li X, Bian W, Wan J, Wang L, Su J (2025). Exploring Symptom Experience and Management Strategies Among Patients with Corneal Ulcers Based on Symptom Management Theory: A Qualitative Study. Patient Preference and Adherence.

- **Title:** Exploring Symptom Experience and Management Strategies Among Patients with Corneal Ulcers Based on Symptom Management Theory: A Qualitative Study.
- **PMID / DOI / URL:** `PMID: 40395651; DOI: 10.2147/PPA.S515296`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/40395651/`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-031` (everyday expression `"hit my left eye"` — *direct patient quote*)
    - **Location:** `Results — Ignoring Symptoms (Participant P2 quote)`
    - **Verbatim `evidence`:** `A tree branch hit my eye when I was doing farmwork, and my eye bled a little when I was injured.`
    - **Scenario `adaptation`:** `Adds unilateral 'left' modifier to verbatim patient ocular-impact phrase 'hit my eye'.`
  - `r12-031` (everyday expression `"watering"` — *direct patient quote*)
    - **Location:** `Results — Some Diagnosis and Treatment Activities Were Also Painful (Participant P15 quote)`
    - **Verbatim `evidence`:** `As soon as I open my eyes and see light, my eyes start watering.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r12-031` (attribution clause `"and I think it is a skin cut"` — *direct patient quote*)
    - **Location:** `Results — Ignoring Symptoms (Participant P2 quote)`
    - **Verbatim `evidence`:** `I thought it was like a skincut, which would be fine after a few days, and I continued working.`
    - **Scenario `adaptation`:** `Recasts eye-trauma patient Participant P2's causal minimization of traumatic ocular bleeding ('I thought it was like a skincut') into the two-word standard-spelling uncontracted present-tense belief clause 'and I think it is a skin cut', omitting the course expectation.`

## 3. Alzayer H, Alabbad E, Alnasrallah B, Alqawain A, Aljishi M (2026). Lived Experiences of Patients With Sickle Cell Disease and Kidney Failure: Insights From a Qualitative Study. Journal of Patient Experience.

- **Title:** Lived Experiences of Patients With Sickle Cell Disease and Kidney Failure: Insights From a Qualitative Study.
- **PMID / DOI / URL:** `PMID: 41958640; DOI: 10.1177/23743735261439469`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/41958640/`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-032` (everyday expression `"dialysis 3 days a week"` — *direct patient quote*)
    - **Location:** `Results — Subtheme: Dual Burden of SCD and KF (Participant P1 quote)`
    - **Verbatim `evidence`:** `Now I also have to deal with dialysis three days a week.`
    - **Scenario `adaptation`:** `Digit normalization ('three' -> '3') per SPEC.md section 4 ('Numbers as digits') of the hemodialysis patient's verbatim schedule phrase 'dialysis three days a week'.`
  - `r12-032` (everyday expression `"tired"` — *direct patient quote*)
    - **Location:** `Results — Subtheme: Compound Impact of KF and SCD on Physical Strength (Participant P3 quote)`
    - **Verbatim `evidence`:** `It was something painful (starting dialysis) because my condition was very, very miserable, and I was extremely, extremely tired.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 4. Wiktionary

- **Title:** cuticle
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/cuticle`
- **Inspected URL:** `https://en.wiktionary.org/wiki/cuticle`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-033` (everyday expression `"cuticle"` — *dictionary definition*)
    - **Location:** `English — Noun, sense 2`
    - **Verbatim `evidence`:** `The strip of hardened skin at the base and sides of a fingernail or toenail.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 5. Wiktionary

- **Title:** pimple
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/pimple`
- **Inspected URL:** `https://en.wiktionary.org/wiki/pimple`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-034` (everyday expression `"pimple"` — *dictionary definition*)
    - **Location:** `English — Noun, sense 1`
    - **Verbatim `evidence`:** `(dermatology) An inflamed (raised and colored) spot on the surface of the skin that is usually painful and fills with pus.`
    - **Scenario `adaptation`:** `Everyday term 'pimple' applied to a small pus-draining bump on the outer gum.`

## 6. Wiktionary

- **Title:** spotting
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/spotting`
- **Inspected URL:** `https://en.wiktionary.org/wiki/spotting`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-035` (everyday expression `"spotting"` — *dictionary definition*)
    - **Location:** `English — Noun, sense 3`
    - **Verbatim `evidence`:** `Vaginal spotting, the discharge of blood from the vagina at a time outside of one's usual menses.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 7. Wu J, Guo X, D J, Peng J, Hu X, Li Y, Wu Y (2024). Psychological experience of patients with postpartum depression: A qualitative meta-synthesis. PLoS One.

- **Title:** Psychological experience of patients with postpartum depression: A qualitative meta-synthesis
- **PMID / DOI / URL:** `PMID: 39504322; DOI: 10.1371/journal.pone.0312996`
- **Inspected URL:** `https://doi.org/10.1371/journal.pone.0312996`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-036` (everyday expression `"cried"` — *direct patient quote*)
    - **Location:** `Results — Negative psychological experiences`
    - **Verbatim `evidence`:** `I don't know why, I just want to cry.`
    - **Scenario `adaptation`:** `Past-participle verb form 'cried' adapted from postpartum depression participant quote 'want to cry'.`

## 8. Wiktionary

- **Title:** grimace
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/grimace`
- **Inspected URL:** `https://en.wiktionary.org/wiki/grimace`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-037` (everyday expression `"grimacing"` — *dictionary definition*)
    - **Location:** `English — Verb, sense 1`
    - **Verbatim `evidence`:** `(intransitive) To make grimaces; to distort one's face; to make faces.`
    - **Scenario `adaptation`:** `Gerund form 'grimacing' adapted from verb entry 'grimace'.`

## 9. Wiktionary

- **Title:** clot
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/clot`
- **Inspected URL:** `https://en.wiktionary.org/wiki/clot`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-038` (everyday expression `"clots"` — *dictionary definition*)
    - **Location:** `English — Noun, sense 1`
    - **Verbatim `evidence`:** `A thrombus, solidified mass of blood.`
    - **Scenario `adaptation`:** `Plural form 'clots' adapted from noun entry 'clot'.`

## 10. Steenrod AW, Smyth EN, Bush EN, Chang ALS, Arron ST, Helfrich YR, et al. (2015). A Qualitative Comparison of Symptoms and Impact of Varying Stages of Basal Cell Carcinoma. Dermatol Ther (Heidelb).

- **Title:** A Qualitative Comparison of Symptoms and Impact of Varying Stages of Basal Cell Carcinoma
- **PMID / DOI / URL:** `PMID: 26324194; DOI: 10.1007/s13555-015-0081-6`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/26324194/`
- **Access opened:** `abstract only`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-039` (everyday expression `"sore"` — *authors' summary*)
    - **Location:** `Abstract — Results`
    - **Verbatim `evidence`:** `Both groups reported similar symptoms, with the most common being red lesions or open sores that failed to heal (41%, N = 14) and cancer-related stress (41%, N = 14).`
    - **Scenario `adaptation`:** `Singular form 'sore' adapted from patient-reported basal cell carcinoma symptom 'open sores'.`

## 11. Wiktionary

- **Title:** scab
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/scab`
- **Inspected URL:** `https://en.wiktionary.org/wiki/scab`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-039` (everyday expression `"scabbed"` — *dictionary definition*)
    - **Location:** `English — Noun, sense 1`
    - **Verbatim `evidence`:** `An incrustation over a sore, wound, vesicle, or pustule, formed during healing.`
    - **Scenario `adaptation`:** `Participial adjective 'scabbed' adapted from noun entry 'scab'.`

## 12. Jackson K, Parthan A, Lauher-Charest M, Broderick L, Law N, Barnett C (2023). Understanding the Symptom Burden and Impact of Myasthenia Gravis from the Patient's Perspective: A Qualitative Study. Neurol Ther.

- **Title:** Understanding the Symptom Burden and Impact of Myasthenia Gravis from the Patient's Perspective: A Qualitative Study
- **PMID / DOI / URL:** `PMID: 36322146; DOI: 10.1007/s40120-022-00408-x`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/36322146/`
- **Access opened:** `abstract only`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-040` (everyday expression `"eyelid drooping"` — *authors' summary*)
    - **Location:** `Abstract — Results`
    - **Verbatim `evidence`:** `The most frequently reported symptoms were eyelid drooping (93%), physical fatigue (89%), symptoms affecting the legs (82%), difficulty breathing (82%), and difficulty holding head up (82%).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*
  - `r12-040` (everyday expression `"double vision"` — *authors' summary*)
    - **Location:** `Abstract — Results`
    - **Verbatim `evidence`:** `Participants' most bothersome symptoms were blurry/double vision (43%), breathing difficulties (36%), all-over fatigue (36%), and swallowing problems (29%).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 13. Hircock C, Lin XW, Lansang RP, Thoma A (2024). A Systematic Review of Qualitative Research in Hand Surgery. Hand.

- **Title:** A Systematic Review of Qualitative Research in Hand Surgery
- **PMID / DOI / URL:** `PMID: 38265010; DOI: 10.1177/15589447231225271`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/38265010/`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-041` (everyday expression `"bend my wrist"` — *direct patient quote*)
    - **Location:** `Results`
    - **Verbatim `evidence`:** `In general, I can't bend my wrist, I'll start getting an increase in pain, and that affects a lot of the daily things I do.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 14. McCarrier KP, Bull S, Fleming S, Simacek K, Wicks P, Cella D, Pierson R (2016). Concept Elicitation Within Patient-Powered Research Networks: A Feasibility Study in Chronic Lymphocytic Leukemia. Value in Health.

- **Title:** Concept Elicitation Within Patient-Powered Research Networks: A Feasibility Study in Chronic Lymphocytic Leukemia
- **PMID / DOI / URL:** `PMID: 26797235; DOI: 10.1016/j.jval.2015.10.013`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/26797235/`
- **Access opened:** `abstract only`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-043` (everyday expression `"night sweats"` — *authors' summary*)
    - **Location:** `Abstract - Results`
    - **Verbatim `evidence`:** `These concepts were followed by night sweats (38%), swollen lymph nodes (32%), and frequent infections (28%).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 15. Klassen AF, Rae C, O'Malley M, Breitkopf T, Algu L, Mansouri J, Brown CR, Wang Y, Lipner SR (2023). Development and Validation of a Patient-Reported Outcome Measure for Fingernail and Toenail Conditions: The NAIL-Q. Clinical, Cosmetic and Investigational Dermatology.

- **Title:** Development and Validation of a Patient-Reported Outcome Measure for Fingernail and Toenail Conditions: The NAIL-Q
- **PMID / DOI / URL:** `PMID: 37915422; DOI: 10.2147/CCID.S429120`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/37915422/`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-044` (everyday expression `"swollen"` — *direct patient quote*)
    - **Location:** `Results - Phase 1: Qualitative Study`
    - **Verbatim `evidence`:** `I will get an ingrown nail on my finger, and it swells up.`
    - **Scenario `adaptation`:** `Inflected verbatim patient interview phrase 'swells up' describing periungual ingrown-nail swelling to adjectival 'swollen'.`

## 16. Wiktionary contributors (verified 2026-11-19). Entry 'wet the bed'. Wiktionary, The Free Dictionary.

- **Title:** Entry 'wet the bed'
- **PMID / DOI / URL:** `https://en.wiktionary.org/wiki/wet_the_bed`
- **Inspected URL:** `https://en.wiktionary.org/wiki/wet_the_bed`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-045` (everyday expression `"wet the bed"` — *dictionary definition*)
    - **Location:** `English - Verb, sense 1`
    - **Verbatim `evidence`:** `To urinate in one's bed (during sleep).`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 17. Knight AW, Hasan I, Tam CWM, Qummouh R, Shehata A (2025). A qualitative study of the influence of childcare on high antibiotic use in a multicultural, lower socioeconomic community. BMC Public Health.

- **Title:** A qualitative study of the influence of childcare on high antibiotic use in a multicultural, lower socioeconomic community
- **PMID / DOI / URL:** `PMID: 40349003; DOI: 10.1186/s12889-025-22725-0`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/40349003/`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-046` (everyday expression `"yellow green"` — *direct patient quote*)
    - **Location:** `Results`
    - **Verbatim `evidence`:** `The fever is up and down, up and down, and runny nose turns green or yellow.`
    - **Scenario `adaptation`:** `Adapted verbatim childcare parent quote 'green or yellow' describing a child's colored nasal discharge to unhyphenated 'yellow green'.`

## 18. Cambridge Dictionary (verified 2026-11-19). Entry 'gnawing'. Cambridge University Press.

- **Title:** Entry 'gnawing'
- **PMID / DOI / URL:** `https://dictionary.cambridge.org/dictionary/english/gnawing`
- **Inspected URL:** `https://dictionary.cambridge.org/dictionary/english/gnawing`
- **Access opened:** `full text`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-047` (everyday expression `"gnawing"` — *dictionary definition*)
    - **Location:** `adjective`
    - **Verbatim `evidence`:** `continuously uncomfortable, worrying, or painful`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

## 19. Kocaata Z, Currie B, Beck E, Zaiser E, Cutts K, Barnes N, Meszaros K (2024). A Qualitative Concept Elicitation Study to Understand Patient-Reported Symptoms and Impacts of Neisseria gonorrhoeae Infections in the United States. Sexually Transmitted Diseases.

- **Title:** A Qualitative Concept Elicitation Study to Understand Patient-Reported Symptoms and Impacts of Neisseria gonorrhoeae Infections in the United States
- **PMID / DOI / URL:** `PMID: 38395028; DOI: 10.1097/OLQ.0000000000001958`
- **Inspected URL:** `https://pubmed.ncbi.nlm.nih.gov/38395028/`
- **Access opened:** `abstract only`
- **Supported Round 12 (`batch_02`) items:**
  - `r12-048` (everyday expression `"discharge"` — *authors' summary*)
    - **Location:** `Abstract - Results`
    - **Verbatim `evidence`:** `The most frequently reported symptoms were vaginal discharge (n = 11 of 12), dysuria (n = 10 of 12), and abdominal/vaginal pain (n = 9 of 12) for symptomatic WSM; dysuria (n = 5 of 6) and penile discharge (n = 4 of 6) for symptomatic MSW; and throat, testicular, or rectal pain (n = 4 of 6) for symptomatic MSM.`
    - **Scenario `adaptation`:** `null` *(exact case-sensitive verbatim substring in `evidence`)*

---

## Unsourced Expressions and Attribution Clauses (`"source": "none"`)

| Family | Kind | Phrase |
|---|---|---|
| `r12-025` | everyday expression | `"felt mild tiredness in my legs for 1 hour the day that diarrhea ended"` |
| `r12-025` | attribution clause | `"and I think it is dehydration"` |
| `r12-026` | everyday expression | `"after giving birth"` |
| `r12-026` | everyday expression | `"my blood pressure on my home arm cuff is 178 over 114 at rest"` |
| `r12-026` | attribution clause | `"and I think it is stress"` |
| `r12-027` | everyday expression | `"all around my right hand and fingers making big tight blisters"` |
| `r12-027` | everyday expression | `"got 1 tiny pink drop mark on my right hand from warm soup that stopped stinging in 1 minute"` |
| `r12-027` | attribution clause | `"and I think they are superficial"` |
| `r12-028` | everyday expression | `"felt warm to the touch"` |
| `r12-028` | everyday expression | `"a temperature of 39 degrees Celsius in his bottom"` |
| `r12-028` | attribution clause | `"and I think it is his blanket"` |
| `r12-029` | everyday expression | `"saliva started pouring nonstop from my mouth"` |
| `r12-029` | everyday expression | `"my mouth felt mildly dry for 10 minutes this afternoon"` |
| `r12-029` | attribution clause | `"and I think it is the heat"` |
| `r12-030` | everyday expression | `"got suddenly confused about where he is and what year it is"` |
| `r12-030` | everyday expression | `"forgot 1 grocery item off our list once"` |
| `r12-030` | attribution clause | `"and I think he is overtired"` |
| `r12-032` | attribution clause | `"and I think it is low iron"` |
| `r12-033` | everyday expression | `"a lengthwise brown black stripe has widened to 5 mm"` |
| `r12-033` | everyday expression | `"a tiny 1 mm white speck has grown halfway out toward the tip over 5 weeks"` |
| `r12-033` | attribution clause | `"and I think I pinched it"` |
| `r12-034` | everyday expression | `"draining pus has kept coming back over 3 weeks"` |
| `r12-034` | everyday expression | `"I felt mild tenderness for 5 minutes yesterday evening"` |
| `r12-034` | attribution clause | `"and I think food scratched it"` |
| `r12-035` | everyday expression | `"have felt mild outer vaginal dryness for 2 days"` |
| `r12-035` | attribution clause | `"and I think it is late hormones"` |
| `r12-036` | everyday expression | `"felt emotionally numb"` |
| `r12-036` | everyday expression | `"felt mildly teary for 10 minutes 1 afternoon last week"` |
| `r12-036` | attribution clause | `"and I think it is tiredness"` |
| `r12-037` | everyday expression | `"gotten stuck on words"` |
| `r12-037` | everyday expression | `"repeated 1 short word 2 times once yesterday"` |
| `r12-037` | attribution clause | `"and I think he talks fast"` |
| `r12-038` | everyday expression | `"passed dark red pee"` |
| `r12-038` | everyday expression | `"1 time yesterday morning my first pee looked medium yellow"` |
| `r12-038` | attribution clause | `"and I think it is beets"` |
| `r12-039` | everyday expression | `"I have had mild dry skin flaking for 2 days"` |
| `r12-039` | attribution clause | `"and I think glasses rubbed it"` |
| `r12-040` | everyday expression | `"1 day last week my upper eyelids felt mildly heavy for 15 minutes"` |
| `r12-040` | attribution clause | `"and I think it is eye strain"` |
| `r12-041` | everyday expression | `"a smooth firm 1 cm lump on the back of my right wrist"` |
| `r12-041` | everyday expression | `"yesterday I felt mild stiffness on the back of my right wrist for 10 minutes right after carrying trays"` |
| `r12-042` | everyday expression | `"bit the back of my right hand and left 2 deep tooth puncture marks"` |
| `r12-042` | everyday expression | `"mild redness and soreness right around them"` |
| `r12-042` | everyday expression | `"yesterday its claw left a tiny 3 mm shallow surface scratch on the back of my right hand that felt mildly tender for 1 minute"` |
| `r12-043` | everyday expression | `"lost 5 kg without trying"` |
| `r12-043` | everyday expression | `"tonight I have a 104 F fever with violent shaking chills and cannot stand up"` |
| `r12-044` | everyday expression | `"side edge of his right big toenail has dug into painful red"` |
| `r12-044` | everyday expression | `"skin oozing a little clear fluid"` |
| `r12-044` | everyday expression | `"felt mild pressure on the tip of his right big toe for 15 minutes yesterday afternoon"` |
| `r12-045` | everyday expression | `"learned to stay dry all night at age 5"` |
| `r12-045` | everyday expression | `"woke up 1 time last Saturday night and walked to the bathroom to pee"` |
| `r12-046` | everyday expression | `"smelly thick"` |
| `r12-046` | everyday expression | `"mucus coming out of only her right nostril"` |
| `r12-046` | everyday expression | `"has had a little thin watery mucus from both nostrils for 1 day"` |
| `r12-047` | everyday expression | `"hunger ache in my upper middle stomach that eases briefly with crackers or milk"` |
| `r12-047` | everyday expression | `"1 evening last week my upper middle stomach rumbled mildly with hunger right before dinner"` |
| `r12-048` | everyday expression | `"thick yellow"` |
| `r12-048` | everyday expression | `"from my penis staining my underwear"` |
| `r12-048` | everyday expression | `"burning when I pee"` |
| `r12-048` | everyday expression | `"today tight swelling trapped my foreskin behind the head of my penis turning the tip dark purple"` |
