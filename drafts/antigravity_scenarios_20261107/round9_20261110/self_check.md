# Round 9 Self-Check (`round9_20261110`)

## Summary Verification

- **Total case families:** 16 (`r9-01` to `r9-16`)
- **Care-level split:** 8 emergency (`right_care: 4`, 4 `" ER"` + 4 `" hospital"`), 4 specialist (`right_care: 3`, 1 each of `" dentist"`, `" dermatologist"`, `" psychiatrist"`, `" specialist"`), 4 general doctor (`right_care: 2`, 2 `" clinic"` + 2 `" doctor"`)
- **2 x 2 (`quad_b`, `quad_c`) families:** 6 (`r9-01`, `r9-05`, `r9-09`, `r9-10`, `r9-13`, `r9-14`)
- **Carrier-phrase & length check:** 92 / 92 texts end with their family's `carrier_frame` and are single sentences of at most 40 words
- **Single-span swap check:** 16 / 16 families satisfy `medical.replace(medical_span, everyday_span, 1) == everyday` with `|words(medical_span) - words(everyday_span)| <= 2`
- **Punctuation, digit, spelling & diagnosis check:** 0 commas (`,`), 0 semicolons (`;`), 0 hyphens (`-`), all numbers written as digits (`0` spelled-out number words), 0 misspellings, 0 condition/diagnosis leaks, and 0 self-harm terms across all 92 texts

---

## Per-Family Fact-Equivalence Tables and Mechanical Checks

### `r9-01` — reviewer label: *cardiogenic syncope* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | Occurred 2 times today | 2 times today | 2 times today | On 2 occasions today | 2 episodes today | 2 times today | 2 times today | 2 times today |
| `f2` | Sudden rapid heartbeat | paroxysmal rapid palpitations | a sudden racing heartbeat | abrupt rapid palpitations | my heart raced suddenly | a sudden racing heartbeat | paroxysmal rapid palpitations | a sudden racing heartbeat |
| `f3` | Tight or sinking sensation in the chest | acute precordial chest tightness | my heart sinking in my chest | substernal chest tightness | a sinking heart in my chest | my heart sinking in my chest | acute precordial chest tightness | my heart sinking in my chest |
| `f4` | Followed immediately by brief loss of consciousness | followed by transient loss of consciousness | right before briefly blacking out | resulting in brief loss of consciousness | right before a brief blackout | **CHANGED (`->2`):** that passed quickly sitting still with no dizziness or fainting | right before transient loss of consciousness | followed by briefly blacking out |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 27 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `everyday` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `medical_paraphrase` | 26 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `everyday_paraphrase` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `changed_fact` | 34 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `quad_b` | 27 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `quad_c` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **16 words** (`"experienced paroxysmal rapid palpitations accompanied by acute precordial chest tightness followed by transient loss of consciousness"`) vs. `everyday_span` = **18 words** (`"got a sudden racing heartbeat along with my heart sinking in my chest right before briefly blacking out"`).
- **Changed-fact check:** `f4` changed from `"right before briefly blacking out"` to `"that passed quickly sitting still with no dizziness or fainting"` (`right_care`: `4` -> `2`).

### `r9-02` — reviewer label: *transient ischemic attack* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Patient is 74 years old | My mother is 74 years old | My mother is 74 years old | At age 74 my mother | My 74 year old mother | My mother is 74 years old |
| `f2` | Sudden episode began 45 minutes ago | 45 minutes ago she experienced an acute focal neurologic episode | 45 minutes ago she had a funny turn | developed a sudden neurologic event 45 minutes ago | had a funny turn 45 minutes ago | 45 minutes ago she had a funny turn |
| `f3` | Left facial weakness and slurred speech | unilateral left facial paresis and dysarthria | where the left side of her face drooped and speech slurred | left facial motor weakness and dysarthric speech | her left face drooped and her words came out slurred | **CHANGED (`->2`):** where she felt mildly lightheaded right after standing up quickly |
| `f4` | Episode lasted 10 minutes | lasting 10 minutes | for 10 minutes | over 10 minutes | for 10 minutes | for 10 minutes |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 35 | PASS (`"so I need to go to the"`) | 0 | 0 | `74, 45, 10` |
| `everyday` | 36 | PASS (`"so I need to go to the"`) | 0 | 0 | `74, 45, 10` |
| `medical_paraphrase` | 32 | PASS (`"so I need to go to the"`) | 0 | 0 | `74, 45, 10` |
| `everyday_paraphrase` | 33 | PASS (`"so I need to go to the"`) | 0 | 0 | `74, 45, 10` |
| `changed_fact` | 35 | PASS (`"so I need to go to the"`) | 0 | 0 | `74, 45, 10` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **15 words** (`"experienced an acute focal neurologic episode characterized by unilateral left facial paresis and dysarthria lasting"`) vs. `everyday_span` = **16 words** (`"had a funny turn where the left side of her face drooped and speech slurred for"`).
- **Changed-fact check:** `f3` changed from `"where the left side of her face drooped and speech slurred"` to `"where she felt mildly lightheaded right after standing up quickly"` (`right_care`: `4` -> `2`).

### `r9-03` — reviewer label: *preeclampsia with severe features* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Currently at 33 weeks of pregnancy | At 33 weeks of pregnancy | At 33 weeks of pregnancy | Now at 33 weeks gestation | I am 33 weeks pregnant | At 33 weeks of pregnancy |
| `f2` | Symptoms present for the past 3 hours | for the past 3 hours | for the past 3 hours | over the last 3 hours | for 3 hours | for the past 3 hours |
| `f3` | Mild swelling of both ankles | mild dependent bilateral ankle edema | mild swelling in both ankles | mild edema of both ankles | both of my ankles have been mildly puffy | mild swelling in both ankles |
| `f4` | Severe persistent headache with dark spots in vision | severe unrelenting cephalalgia and dark visual scotomata | with a bad constant headache and dark spots in my vision | persistent severe cephalalgia and dark scotomata in my visual field | a terrible nonstop headache and dark spots before my eyes | **CHANGED (`->2`):** after standing with mild back ache and no headache or blurry vision |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 34 | PASS (`"so I need to go to the"`) | 0 | 0 | `33, 3` |
| `everyday` | 36 | PASS (`"so I need to go to the"`) | 0 | 0 | `33, 3` |
| `medical_paraphrase` | 36 | PASS (`"so I need to go to the"`) | 0 | 0 | `33, 3` |
| `everyday_paraphrase` | 35 | PASS (`"so I need to go to the"`) | 0 | 0 | `33, 3` |
| `changed_fact` | 37 | PASS (`"so I need to go to the"`) | 0 | 0 | `33, 3` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **13 words** (`"dependent bilateral ankle edema accompanied by severe unrelenting cephalalgia and dark visual scotomata"`) vs. `everyday_span` = **15 words** (`"swelling in both ankles with a bad constant headache and dark spots in my vision"`).
- **Changed-fact check:** `f4` changed from `"with a bad constant headache and dark spots in my vision"` to `"after standing with mild back ache and no headache or blurry vision"` (`right_care`: `4` -> `2`).

### `r9-04` — reviewer label: *severe acute bronchiolitis* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Infant is 5 months old | My baby is 5 months old | My baby is 5 months old | At 5 months of age | My 5 month old baby | My baby is 5 months old |
| `f2` | 2 days of nasal mucus and cough | 2 days of rhinorrhea and cough | 2 days of extra mucus and cough | 2 days of nasal discharge and cough | 2 days of runny mucus and a cough | 2 days of extra mucus and cough |
| `f3` | Slightly reduced bottle feeding | mildly decreased oral intake | smaller bottle feeds | modestly reduced bottle intake | taking less milk | smaller bottle feeds |
| `f4` | Labored breathing tonight with chest skin pulling between ribs | and tonight developed labored dyspnea with intercostal retractions | and tonight has hard breathing with ribs sucking in | developed respiratory distress and intercostal retractions tonight | tonight she has trouble breathing with skin pulling around her ribs | **CHANGED (`->2`):** and tonight breathes easily with wet diapers and low fever |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 33 | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 2` |
| `everyday` | 34 | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 2` |
| `medical_paraphrase` | 34 | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 2` |
| `everyday_paraphrase` | 37 | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 2` |
| `changed_fact` | 35 | PASS (`"so I need to go to the"`) | 0 | 0 | `5, 2` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **16 words** (`"rhinorrhea and cough plus mildly decreased oral intake and tonight developed labored dyspnea with intercostal retractions"`) vs. `everyday_span` = **17 words** (`"extra mucus and cough plus smaller bottle feeds and tonight has hard breathing with ribs sucking in"`).
- **Changed-fact check:** `f4` changed from `"and tonight has hard breathing with ribs sucking in"` to `"and tonight breathes easily with wet diapers and low fever"` (`right_care`: `4` -> `2`).

### `r9-05` — reviewer label: *severe acute asthma exacerbation* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | Symptoms ongoing for the past 20 minutes | For the past 20 minutes | For the past 20 minutes | Over the last 20 minutes | Over the last 20 minutes | For the past 20 minutes | For the past 20 minutes | For the past 20 minutes |
| `f2` | Acute shortness of breath | acutely dyspneic | short winded | severe dyspnea | can't catch my breath | short winded | acutely dyspneic | short winded |
| `f3` | Audible chest wheezing | audible expiratory wheezing | tight whistling breathing | expiratory wheezes | whistling in my chest | tight whistling breathing | audible expiratory wheezing | tight whistling breathing |
| `f4` | Unable to speak full sentences despite 2 rescue inhaler puffs | inability to complete sentences despite 2 bronchodilator puffs | and broken sentences even after 2 inhaler puffs | fragmented speech refractory to 2 inhaled bronchodilator actuations | cannot finish a sentence even after 2 puffs of my inhaler | **CHANGED (`->2`):** that eased right away after 2 inhaler puffs with normal speech | inability to complete sentences even after 2 bronchodilator puffs | broken sentences despite 2 inhaler puffs |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 31 | PASS (`"so I need to go to the"`) | 0 | 0 | `20, 2` |
| `everyday` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `20, 2` |
| `medical_paraphrase` | 28 | PASS (`"so I need to go to the"`) | 0 | 0 | `20, 2` |
| `everyday_paraphrase` | 34 | PASS (`"so I need to go to the"`) | 0 | 0 | `20, 2` |
| `changed_fact` | 32 | PASS (`"so I need to go to the"`) | 0 | 0 | `20, 2` |
| `quad_b` | 31 | PASS (`"so I need to go to the"`) | 0 | 0 | `20, 2` |
| `quad_c` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `20, 2` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **17 words** (`"have become acutely dyspneic accompanied by audible expiratory wheezing with inability to complete sentences despite 2 bronchodilator"`) vs. `everyday_span` = **15 words** (`"started feeling short winded with tight whistling breathing and broken sentences even after 2 inhaler"`).
- **Changed-fact check:** `f4` changed from `"and broken sentences even after 2 inhaler puffs"` to `"that eased right away after 2 inhaler puffs with normal speech"` (`right_care`: `4` -> `2`).

### `r9-06` — reviewer label: *generalized tonic clonic seizure* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Occurred today after 2 brief episodes earlier this month | Today after 2 brief episodes this month | Today after 2 brief episodes this month | Following 2 transient episodes earlier this month today | After 2 short episodes this month today | Today after 2 brief episodes this month |
| `f2` | Happened while standing in a warm room | while standing in a warm room | while standing in a warm room | in a warm room | standing in a warm room | while standing in a warm room |
| `f3` | Preceded by sudden dizziness | acute presyncopal lightheadedness | a sudden dizzy spell | sudden presyncopal lightheadedness | a dizzy spell | a sudden dizzy spell |
| `f4` | Collapsed unconscious with 3 minutes of generalized convulsions | followed by loss of consciousness and 3 minutes of generalized convulsions | and then fell out having fits for 3 minutes | progressing to unconsciousness and generalized convulsions lasting 3 minutes | before falling out and having fits for 3 minutes | **CHANGED (`->2`):** but sat down and recovered in 1 minute without fainting |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 36 | PASS (`"so I need to go to the"`) | 0 | 0 | `2, 3` |
| `everyday` | 35 | PASS (`"so I need to go to the"`) | 0 | 0 | `2, 3` |
| `medical_paraphrase` | 33 | PASS (`"so I need to go to the"`) | 0 | 0 | `2, 3` |
| `everyday_paraphrase` | 33 | PASS (`"so I need to go to the"`) | 0 | 0 | `2, 3` |
| `changed_fact` | 36 | PASS (`"so I need to go to the"`) | 0 | 0 | `2, 1` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **15 words** (`"developed acute presyncopal lightheadedness followed by loss of consciousness and 3 minutes of generalized convulsions"`) vs. `everyday_span` = **14 words** (`"got a sudden dizzy spell and then fell out having fits for 3 minutes"`).
- **Changed-fact check:** `f4` changed from `"and then fell out having fits for 3 minutes"` to `"but sat down and recovered in 1 minute without fainting"` (`right_care`: `4` -> `2`).

### `r9-07` — reviewer label: *pediatric diabetic ketoacidosis* (`right_care: 4`, `target_token: " hospital"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Child is 9 years old | My son is 9 years old | My son is 9 years old | At age 9 | My 9 year old son | My son is 9 years old |
| `f2` | 1 week of excessive thirst | 1 week of polydipsia | 1 week of extreme thirst | 1 week of excessive polydipsia | for 1 week has had extreme thirst | 1 week of extreme thirst |
| `f3` | 1 week of frequent urination | and polyuria | and constant toilet trips | with polyuria | and frequent trips to the toilet | and constant toilet trips |
| `f4` | Persistent vomiting and marked drowsiness today | he developed intractable emesis and marked somnolence today | he started nonstop vomiting and drowsiness today | presented with persistent emesis and pronounced lethargy today | cannot stop throwing up while acting drowsy today | **CHANGED (`->2`):** he stays alert eating meals with no vomiting today |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `9, 1` |
| `everyday` | 31 | PASS (`"so I need to go to the"`) | 0 | 0 | `9, 1` |
| `medical_paraphrase` | 28 | PASS (`"so I need to go to the"`) | 0 | 0 | `9, 1` |
| `everyday_paraphrase` | 34 | PASS (`"so I need to go to the"`) | 0 | 0 | `9, 1` |
| `changed_fact` | 33 | PASS (`"so I need to go to the"`) | 0 | 0 | `9, 1` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **10 words** (`"polydipsia and polyuria he developed intractable emesis and marked somnolence"`) vs. `everyday_span` = **12 words** (`"extreme thirst and constant toilet trips he started nonstop vomiting and drowsiness"`).
- **Changed-fact check:** `f4` changed from `"he started nonstop vomiting and drowsiness"` to `"he stays alert eating meals with no vomiting"` (`right_care`: `4` -> `2`).

### `r9-08` — reviewer label: *food induced anaphylaxis* (`right_care: 4`, `target_token: " ER"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | 2 hours after eating shellfish | 2 hours after eating shellfish | 2 hours after eating shellfish | Following shellfish ingestion 2 hours ago | After eating shellfish 2 hours ago | 2 hours after eating shellfish |
| `f2` | Itchy raised hives across both arms | generalized pruritic urticaria across both upper extremities | itching and breaking out in hives on both arms | pruritic urticarial wheals on both arms | itching and breaking out in hives over both arms | itching and breaking out in hives on both arms |
| `f3` | Throat swelling with labored breathing | acute oropharyngeal angioedema and labored dyspnea | and my throat swelled up with trouble breathing | pharyngeal angioedema and acute respiratory difficulty | my throat swelled up with trouble breathing | **CHANGED (`->2`):** with normal breathing and no lip or throat swelling |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `everyday` | 31 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `medical_paraphrase` | 29 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `everyday_paraphrase` | 32 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `changed_fact` | 32 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **16 words** (`"developed generalized pruritic urticaria across both upper extremities accompanied by acute oropharyngeal angioedema and labored dyspnea"`) vs. `everyday_span` = **18 words** (`"was itching and breaking out in hives on both arms and my throat swelled up with trouble breathing"`).
- **Changed-fact check:** `f3` changed from `"and my throat swelled up with trouble breathing"` to `"with normal breathing and no lip or throat swelling"` (`right_care`: `4` -> `2`).

### `r9-09` — reviewer label: *symptomatic irreversible pulpitis* (`right_care: 3`, `target_token: " dentist"`, `carrier_frame: "so I should see a"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | Symptoms present for 4 days | For 4 days | For 4 days | Over 4 days | Across the past 4 days | For 4 days | For 4 days | For 4 days |
| `f2` | Throbbing pain localized to 1 lower back tooth | pulsatile odontalgia in 1 mandibular molar | throbbing pain in 1 bottom back tooth | pulsatile mandibular molar odontalgia in 1 tooth | 1 lower back tooth has had an intense throbbing ache | throbbing pain in 1 bottom back tooth | pulsatile odontalgia in 1 mandibular molar | throbbing pain in 1 bottom back tooth |
| `f3` | Triggered by hot and cold liquids | provoked by hot and cold thermal stimuli | whenever I have hot and cold drinks | elicited by hot and cold liquids | with hot and cold drinks | whenever I have hot and cold drinks | whenever I have hot and cold thermal stimuli | provoked by hot and cold drinks |
| `f4` | Absence of facial swelling fever or difficulty swallowing | in the absence of facial edema pyrexia or dysphagia | but I have no facial swelling fever or trouble swallowing | without facial edema pyrexia or dysphagia | and no swollen face fever or swallowing trouble | **CHANGED (`->4`):** and tonight jaw swelling started with high fever and trouble swallowing | but I have no facial edema pyrexia or dysphagia | in the absence of facial swelling fever or trouble swallowing |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 33 | PASS (`"so I should see a"`) | 0 | 0 | `4, 1` |
| `everyday` | 35 | PASS (`"so I should see a"`) | 0 | 0 | `4, 1` |
| `medical_paraphrase` | 29 | PASS (`"so I should see a"`) | 0 | 0 | `4, 1` |
| `everyday_paraphrase` | 33 | PASS (`"so I should see a"`) | 0 | 0 | `4, 1` |
| `changed_fact` | 36 | PASS (`"so I should see a"`) | 0 | 0 | `4, 1` |
| `quad_b` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `4, 1` |
| `quad_c` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `4, 1` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **24 words** (`"have experienced pulsatile odontalgia in 1 mandibular molar provoked by hot and cold thermal stimuli in the absence of facial edema pyrexia or dysphagia"`) vs. `everyday_span` = **26 words** (`"keep getting throbbing pain in 1 bottom back tooth whenever I have hot and cold drinks but I have no facial swelling fever or trouble swallowing"`).
- **Changed-fact check:** `f4` changed from `"but I have no facial swelling fever or trouble swallowing"` to `"and tonight jaw swelling started with high fever and trouble swallowing"` (`right_care`: `3` -> `4`).

### `r9-10` — reviewer label: *cutaneous melanoma* (`right_care: 3`, `target_token: " dermatologist"`, `carrier_frame: "so I should see a"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | Patient is 68 years old | At age 68 | At age 68 | Now 68 years old | I am 68 years old | At age 68 | At age 68 | At age 68 |
| `f2` | Dark flat skin lesion on the upper back | a pigmented macular nevus on my posterior trunk | a dark flat mole on my upper back | a flat pigmented nevus over my upper posterior trunk | a flat dark mole on my upper back | a dark flat mole on my upper back | a pigmented macular nevus on my posterior trunk | a dark flat mole on my upper back |
| `f3` | Enlarged with irregular borders over 3 months | exhibiting irregular border expansion over 3 months | that got wider jagged edges over 3 months | showing progressive border irregularity across 3 months | growing jagged uneven edges over the past 3 months | **CHANGED (`->2`):** rubbed sore by my shirt for 2 weeks without changing shape | that got irregular border expansion over 3 months | exhibiting wider jagged edges over 3 months |
| `f4` | Absence of fever or surrounding skin redness | in the absence of pyrexia or surrounding erythema | and I have no fever or spreading redness | without pyrexia or perilesional erythema | without fever or red skin around it | and I have no fever or spreading redness | and I have no pyrexia or surrounding erythema | in the absence of fever or spreading redness |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `68, 3` |
| `everyday` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `68, 3` |
| `medical_paraphrase` | 32 | PASS (`"so I should see a"`) | 0 | 0 | `68, 3` |
| `everyday_paraphrase` | 36 | PASS (`"so I should see a"`) | 0 | 0 | `68, 3` |
| `changed_fact` | 37 | PASS (`"so I should see a"`) | 0 | 0 | `68, 2` |
| `quad_b` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `68, 3` |
| `quad_c` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `68, 3` |

- **Swap spans (`|diff| = 0 <= 2`):** `medical_span` = **25 words** (`"have observed a pigmented macular nevus on my posterior trunk exhibiting irregular border expansion over 3 months in the absence of pyrexia or surrounding erythema"`) vs. `everyday_span` = **25 words** (`"saw a dark flat mole on my upper back that got wider jagged edges over 3 months and I have no fever or spreading redness"`).
- **Changed-fact check:** `f3` changed from `"that got wider jagged edges over 3 months"` to `"rubbed sore by my shirt for 2 weeks without changing shape"` (`right_care`: `3` -> `2`).

### `r9-11` — reviewer label: *panic disorder with agoraphobia* (`right_care: 3`, `target_token: " psychiatrist"`, `carrier_frame: "so I should see a"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | 4 months of episodes 3 times weekly lasting 15 minutes | For 4 months 3 times weekly I have had 15 minute | For 4 months 3 times weekly I have had 15 minute | Across 4 months at a frequency of 3 episodes per week I experience 15 minute | Over 4 months 3 times a week I get 15 minute | For 4 months 3 times weekly I have had 15 minute |
| `f2` | Sudden racing heartbeat and trembling | paroxysms of palpitations and tremor | waves of racing heart and trembling | surges of autonomic palpitations and tremor | rushes of a pounding heart and shaking | waves of racing heart and trembling |
| `f3` | Acute fear of losing control | with fear of losing control | with fear of losing control | with fear of losing control | with fear of losing control | with fear of losing control |
| `f4` | Public transit avoidance without chest pain or fainting | causing transit avoidance without thoracic pain or syncope | keeping me off buses without chest pain or fainting | and transit avoidance without thoracic pain or syncope | so I avoid buses despite no chest pain or fainting | **CHANGED (`->4`):** and right now I have crushing chest pain and fainted |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `4, 3, 15` |
| `everyday` | 36 | PASS (`"so I should see a"`) | 0 | 0 | `4, 3, 15` |
| `medical_paraphrase` | 39 | PASS (`"so I should see a"`) | 0 | 0 | `4, 3, 15` |
| `everyday_paraphrase` | 38 | PASS (`"so I should see a"`) | 0 | 0 | `4, 3, 15` |
| `changed_fact` | 37 | PASS (`"so I should see a"`) | 0 | 0 | `4, 3, 15` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **18 words** (`"paroxysms of palpitations and tremor with fear of losing control causing transit avoidance without thoracic pain or syncope"`) vs. `everyday_span` = **20 words** (`"waves of racing heart and trembling with fear of losing control keeping me off buses without chest pain or fainting"`).
- **Changed-fact check:** `f4` changed from `"keeping me off buses without chest pain or fainting"` to `"and right now I have crushing chest pain and fainted"` (`right_care`: `3` -> `4`).

### `r9-12` — reviewer label: *early rheumatoid arthritis* (`right_care: 3`, `target_token: " specialist"`, `carrier_frame: "so I should see a"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | Patient is 66 years old with 8 weeks of symptoms | At age 66 for 8 weeks | At age 66 for 8 weeks | Now 66 years old over 8 weeks | I am 66 years old and for 8 weeks | At age 66 for 8 weeks |
| `f2` | Symmetric swelling and pain in knuckles of both hands | symmetric metacarpophalangeal joint edema and arthralgia in both hands | swollen painful knuckles on both hands | symmetric edema and arthralgia across the metacarpophalangeal joints of both hands | the knuckles on both hands have been swollen and sore | swollen painful knuckles on both hands |
| `f3` | Morning joint stiffness lasting 90 minutes | with 90 minute morning stiffness | that stay stiff 90 minutes every morning | with 90 minutes of morning stiffness | taking 90 minutes each morning to loosen up | that stay stiff 90 minutes every morning |
| `f4` | Absence of injury fever or single hot red joint | without trauma pyrexia or monoarticular erythema | without injury fever or a hot red joint | and no trauma pyrexia or focal erythema | with no injury fever or hot red skin | **CHANGED (`->4`):** and today my right wrist turned hot red and immobile with fever |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `66, 8, 90` |
| `everyday` | 35 | PASS (`"so I should see a"`) | 0 | 0 | `66, 8, 90` |
| `medical_paraphrase` | 38 | PASS (`"so I should see a"`) | 0 | 0 | `66, 8, 90` |
| `everyday_paraphrase` | 40 | PASS (`"so I should see a"`) | 0 | 0 | `66, 8, 90` |
| `changed_fact` | 39 | PASS (`"so I should see a"`) | 0 | 0 | `66, 8, 90` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **20 words** (`"symmetric metacarpophalangeal joint edema and arthralgia in both hands with 90 minute morning stiffness without trauma pyrexia or monoarticular erythema"`) vs. `everyday_span` = **21 words** (`"swollen painful knuckles on both hands that stay stiff 90 minutes every morning without injury fever or a hot red joint"`).
- **Changed-fact check:** `f4` changed from `"without injury fever or a hot red joint"` to `"and today my right wrist turned hot red and immobile with fever"` (`right_care`: `3` -> `4`).

### `r9-13` — reviewer label: *uncomplicated acute cystitis* (`right_care: 2`, `target_token: " clinic"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | Symptoms present for 2 days | For 2 days | For 2 days | Over the past 2 days | Over the past 2 days | For 2 days | For 2 days | For 2 days |
| `f2` | Burning pain during urination | dysuria | burning when I pee | acute dysuria | stinging and burning when I pee | burning when I pee | dysuria | burning when I pee |
| `f3` | Frequent small volume urination | urinary frequency in small volumes | peeing tiny amounts often | frequent small volume voiding | frequent tiny trips to the bathroom | peeing tiny amounts often | urinary frequency in small volumes | peeing tiny amounts often |
| `f4` | Absence of flank or back pain | in the absence of flank tenderness | no back pain | without costovertebral angle pain | no pain in my back | no back pain | no flank tenderness | in the absence of back pain |
| `f5` | Absence of fever and vomiting | or pyrexia with emesis | or fever with vomiting | or febrile emesis | or fever with throwing up | **CHANGED (`->4`):** yet today I got high fever shaking chills and nonstop vomiting | or pyrexia with emesis | or fever with vomiting |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 31 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `everyday` | 32 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `medical_paraphrase` | 28 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `everyday_paraphrase` | 39 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `changed_fact` | 39 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `quad_b` | 30 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |
| `quad_c` | 33 | PASS (`"so I need to go to the"`) | 0 | 0 | `2` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **20 words** (`"have experienced dysuria accompanied by urinary frequency in small volumes in the absence of flank tenderness or pyrexia with emesis"`) vs. `everyday_span` = **21 words** (`"keep getting burning when I pee and peeing tiny amounts often but I have no back pain or fever with vomiting"`).
- **Changed-fact check:** `f5` changed from `"or fever with vomiting"` to `"yet today I got high fever shaking chills and nonstop vomiting"` (`right_care`: `2` -> `4`).

### `r9-14` — reviewer label: *uncomplicated acute otitis media* (`right_care: 2`, `target_token: " doctor"`, `carrier_frame: "so I should see a"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` | `quad_b` | `quad_c` |
|---|---|---|---|---|---|---|---|---|
| `f1` | Child is 4 years old with 2 days of symptoms | At age 4 for 2 days | At age 4 for 2 days | My 4 year old daughter has presented for 2 days | My 4 year old daughter for 2 days | At age 4 for 2 days | At age 4 for 2 days | At age 4 for 2 days |
| `f2` | Right ear pain and ear pulling | right otalgia and auricular tugging | right ear pain and ear pulling | unilateral right otalgia auricular tugging | pulling her right ear with earache | right ear pain and ear pulling | right otalgia and auricular tugging | right ear pain and ear pulling |
| `f3` | Fever of 38 degrees Celsius | 38 Celsius pyrexia | 38 Celsius fever | and 38 Celsius pyrexia | and a 38 Celsius fever | 38 Celsius fever | 38 Celsius pyrexia | 38 Celsius fever |
| `f4` | Alert and drinking fluids well without swelling behind the ear | while maintaining normal alertness oral intake and no postauricular edema | but still has good energy normal drinking and no swelling behind it | while remaining alert hydrated and free of postauricular swelling | while staying playful drinking well without swelling behind her ear | **CHANGED (`->4`):** and today became drowsy with stiff neck and red swelling behind it | but still has normal alertness oral intake and no postauricular edema | while maintaining good energy normal drinking and no swelling behind it |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 35 | PASS (`"so I should see a"`) | 0 | 0 | `4, 2, 38` |
| `everyday` | 37 | PASS (`"so I should see a"`) | 0 | 0 | `4, 2, 38` |
| `medical_paraphrase` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `4, 2, 38` |
| `everyday_paraphrase` | 36 | PASS (`"so I should see a"`) | 0 | 0 | `4, 2, 38` |
| `changed_fact` | 37 | PASS (`"so I should see a"`) | 0 | 0 | `4, 2, 38` |
| `quad_b` | 35 | PASS (`"so I should see a"`) | 0 | 0 | `4, 2, 38` |
| `quad_c` | 37 | PASS (`"so I should see a"`) | 0 | 0 | `4, 2, 38` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **22 words** (`"has exhibited right otalgia and auricular tugging accompanied by 38 Celsius pyrexia while maintaining normal alertness oral intake and no postauricular edema"`) vs. `everyday_span` = **24 words** (`"kept having right ear pain and ear pulling plus 38 Celsius fever but still has good energy normal drinking and no swelling behind it"`).
- **Changed-fact check:** `f4` changed from `"but still has good energy normal drinking and no swelling behind it"` to `"and today became drowsy with stiff neck and red swelling behind it"` (`right_care`: `2` -> `4`).

### `r9-15` — reviewer label: *persistent uncomplicated acute gastroenteritis* (`right_care: 2`, `target_token: " doctor"`, `carrier_frame: "so I should see a"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | 6 days of symptoms following a recent trip | For 6 days after a trip | For 6 days after a trip | Since returning from travel 6 days ago | Since a trip 6 days ago | For 6 days after a trip |
| `f2` | Frequent nonbloody watery diarrhea | frequent nonbloody watery diarrhea | frequent watery loose motions with no blood | persistent watery diarrhea without hematochezia | watery loose motions without blood | frequent watery loose motions with no blood |
| `f3` | Mild abdominal cramping | with mild abdominal cramping | and mild belly cramps | and mild abdominal cramps | and mild stomach cramps | and mild belly cramps |
| `f4` | Keeping fluids down with normal urination and no dizziness on standing | while tolerating oral hydration maintaining normal diuresis without orthostatic lightheadedness | while keeping drinks down peeing normally without dizziness standing | while retaining oral fluids with normal urine output and no postural dizziness | while holding fluids down passing urine normally and feeling steady on my feet | **CHANGED (`->4`):** and today cannot keep water down stopped peeing and nearly faint standing |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 32 | PASS (`"so I should see a"`) | 0 | 0 | `6` |
| `everyday` | 34 | PASS (`"so I should see a"`) | 0 | 0 | `6` |
| `medical_paraphrase` | 36 | PASS (`"so I should see a"`) | 0 | 0 | `6` |
| `everyday_paraphrase` | 36 | PASS (`"so I should see a"`) | 0 | 0 | `6` |
| `changed_fact` | 37 | PASS (`"so I should see a"`) | 0 | 0 | `6` |

- **Swap spans (`|diff| = 2 <= 2`):** `medical_span` = **17 words** (`"nonbloody watery diarrhea with mild abdominal cramping while tolerating oral hydration maintaining normal diuresis without orthostatic lightheadedness"`) vs. `everyday_span` = **19 words** (`"watery loose motions with no blood and mild belly cramps while keeping drinks down peeing normally without dizziness standing"`).
- **Changed-fact check:** `f4` changed from `"while keeping drinks down peeing normally without dizziness standing"` to `"and today cannot keep water down stopped peeing and nearly faint standing"` (`right_care`: `2` -> `4`).

### `r9-16` — reviewer label: *uncomplicated gastroesophageal reflux in pregnancy* (`right_care: 2`, `target_token: " clinic"`, `carrier_frame: "so I need to go to the"`)

| Fact | Reference Fact | `medical` | `everyday` | `medical_paraphrase` | `everyday_paraphrase` | `changed_fact` |
|---|---|---|---|---|---|---|
| `f1` | At 24 weeks of pregnancy with 2 weeks of symptoms | At 24 weeks of pregnancy for 2 weeks | At 24 weeks of pregnancy for 2 weeks | Now at 24 weeks gestation over 2 weeks | At 24 weeks pregnant over 2 weeks | At 24 weeks of pregnancy for 2 weeks |
| `f2` | Burning chest sensation after meals with sour acid in the throat | postprandial retrosternal burning discomfort and acidic pharyngeal regurgitation | burning in my chest after meals and throat acid | postprandial substernal burning with sour pharyngeal acid | burning rises in my chest after eating with sour throat acid | burning in my chest after meals and throat acid |
| `f3` | Worse when lying flat | during recumbency | lying flat | worse when supine | lying down | lying flat |
| `f4` | Absence of swallowing difficulty bloody vomit headache or blurred vision | in the absence of dysphagia hematemesis cephalalgia or visual disturbance | with no swallowing pain bloody vomit headache or blurry vision | and without dysphagia hematemesis cephalalgia or visual disturbance | and no swallowing pain blood headache or blurry sight | **CHANGED (`->4`):** and 1 hour ago vomited red blood and felt faint |

| Text | Word Count (<=40) | Ends with `carrier_frame` | `,` / `;` / `-` Count | Spelled-Out Numbers | Digits Present |
|---|---|---|---|---|---|
| `medical` | 38 | PASS (`"so I need to go to the"`) | 0 | 0 | `24, 2` |
| `everyday` | 39 | PASS (`"so I need to go to the"`) | 0 | 0 | `24, 2` |
| `medical_paraphrase` | 35 | PASS (`"so I need to go to the"`) | 0 | 0 | `24, 2` |
| `everyday_paraphrase` | 36 | PASS (`"so I need to go to the"`) | 0 | 0 | `24, 2` |
| `changed_fact` | 39 | PASS (`"so I need to go to the"`) | 0 | 0 | `24, 2, 1` |

- **Swap spans (`|diff| = 1 <= 2`):** `medical_span` = **20 words** (`"postprandial retrosternal burning discomfort and acidic pharyngeal regurgitation during recumbency in the absence of dysphagia hematemesis cephalalgia or visual disturbance"`) vs. `everyday_span` = **21 words** (`"burning in my chest after meals and throat acid lying flat with no swallowing pain bloody vomit headache or blurry vision"`).
- **Changed-fact check:** `f4` changed from `"with no swallowing pain bloody vomit headache or blurry vision"` to `"and 1 hour ago vomited red blood and felt faint"` (`right_care`: `2` -> `4`).

---

## Expressions Marked `"source": "none"`

The following everyday expressions had no directly verified verbatim quote or specific symptom summary in the inspected literature and are therefore marked `"source": "none"` rather than citing an unverified paper:

| Family | Expression Marked `"source": "none"` |
|---|---|
| `r9-01` | `"a sudden racing heartbeat"` |
| `r9-01` | `"my heart raced suddenly"` |
| `r9-03` | `"both of my ankles have been mildly puffy"` |
| `r9-04` | `"runny mucus"` |
| `r9-04` | `"smaller bottle feeds"` |
| `r9-04` | `"taking less milk"` |
| `r9-04` | `"ribs sucking in"` |
| `r9-04` | `"skin pulling around her ribs"` |
| `r9-05` | `"tight whistling breathing"` |
| `r9-05` | `"whistling in my chest"` |
| `r9-05` | `"broken sentences even after 2 inhaler puffs"` |
| `r9-05` | `"cannot finish a sentence even after 2 puffs of my inhaler"` |
| `r9-07` | `"nonstop vomiting and drowsiness"` |
| `r9-07` | `"cannot stop throwing up while acting drowsy"` |
| `r9-09` | `"1 bottom back tooth"` |
| `r9-09` | `"1 lower back tooth"` |
| `r9-09` | `"hot and cold drinks"` |
| `r9-09` | `"no facial swelling fever or trouble swallowing"` |
| `r9-09` | `"no swollen face fever or swallowing trouble"` |
| `r9-10` | `"no fever or spreading redness"` |
| `r9-11` | `"a pounding heart and shaking"` |
| `r9-11` | `"without chest pain or fainting"` |
| `r9-12` | `"without injury fever or a hot red joint"` |
| `r9-13` | `"peeing tiny amounts often"` |
| `r9-13` | `"no back pain or fever with vomiting"` |
| `r9-14` | `"right ear pain"` |
| `r9-14` | `"earache"` |
| `r9-14` | `"good energy normal drinking and no swelling behind it"` |
| `r9-14` | `"staying playful drinking well without swelling behind her ear"` |
| `r9-15` | `"mild belly cramps"` |
| `r9-15` | `"mild stomach cramps"` |
| `r9-15` | `"keeping drinks down peeing normally without dizziness standing"` |
| `r9-15` | `"holding fluids down passing urine normally and feeling steady on my feet"` |
| `r9-16` | `"lying flat"` |
| `r9-16` | `"lying down"` |
| `r9-16` | `"no swallowing pain bloody vomit headache or blurry vision"` |
| `r9-16` | `"no swallowing pain blood headache or blurry sight"` |
