# Round 5 Self-Check (`round5_20261108`)

## 1. Automated Verification Summary

- **18 comma rewrites (`rewritten.json`):** Rewrites all 18 excluded pairs from `pairs_noted_for_commas` in `ground_truth/gt_scale_20261108.json` (`sc-025`, `sc-027`, `sc-029`, `sc-031`, `sc-033`, `sc-035`, `sc-039`, `sc-040`, `sc-042`, `sc-043`, `sc-044`, `sc-047`, `sc-048`, `sc-049`, `sc-050`, `sc-052`, `sc-053`, `sc-054`), leaving `sc-051` untouched as instructed. Each entry includes `rewrites` naming the original ID.
- **30 new pairs (`candidates.json`):** `r5-001` through `r5-030`, extending the Round 3 pairs that downgraded in `ground_truth/gt_measured_20261108.json`.
- **Comma, semicolon, and hyphen check (`48 / 48` pairs):** Every `top_prompt` and `bottom_prompt` across both `rewritten.json` (18 pairs) and `candidates.json` (30 pairs) has **0 commas**, **0 semicolons**, and **0 hyphens**.
- **Single-contrast swap & carrier-frame reconstruction (`48 / 48` pairs):** Every pair's `bottom_prompt` reconstructs exactly from `top_prompt` via its single span swap, minimizing prefix insertion (`r5-030`), or ordered misspellings (`sc-039`..`sc-054`), and both sides end with the exact `carrier_frame`.
- **Dose-group alignment in `rewritten.json`:** Each rewritten 1-misspelling and 3-misspelling pair (`sc-039`/`sc-049`, `sc-040`/`sc-050`, `sc-042`/`sc-052`, `sc-043`/`sc-053`, `sc-044`/`sc-054`) shares an identical 0-comma `top_prompt`.
- **Holdout seal check (`scripts/tierb_split.py`):** `0 / 48` pairs trigger `tierb_split.sealed_pair` or `tierb_split.is_holdout` on either `top_prompt` or `bottom_prompt`.
- **Similarity check against 1,774 published scenarios (`patientwords/data/simulated_scenarios.json`):** Maximum word-level Jaccard similarity across all 48 pairs (96 prompts) is **`0.375`** (`sc-047:top` vs `pub-786-clin`), well below `0.70`.
- **Similarity check of 30 new candidates against Round 3 (`candidates_v3.json`) and Scale Round (`candidates_v2.json`):** Maximum Jaccard similarity is **`0.522`** (`r5-020:top` vs `sc-025-top`).
- **Internal deduplication check among 30 new candidates:** Maximum pairwise Jaccard similarity is **`0.448`** (`r5-001` vs `r5-021`).

## 2. Comma Count, Swap Reconstruction, and Fact-Parity Table: `rewritten.json` (18 Pairs)

| ID (`rewrites`) | Family | Top Commas | Bottom Commas | Hyphens | Swap Type | Shared Facts (Both Sentences) |
|---|---|---:|---:|---:|---|---|
| `sc-025` (`sc-025`) | `dialect_non_native` | 0 | 0 | 0 | single-span swap | Cirrhosis context today; Progressive ascites / growing water swelling in belly; Scleral icterus / yellow eyes; Asterixis / flapping hands |
| `sc-027` (`sc-027`) | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | Post-splenectomy context; Sudden fever of 102.4 Fahrenheit; Rigors / shaking chills; Orthostatic dizziness / dizziness when standing |
| `sc-029` (`sc-029`) | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | Age and mechanism: age 81 after a fall; Groin pain; Inability to walk; Shortened externally rotated leg |
| `sc-031` (`sc-031`) | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | Prosthetic heart valve context; Fever; Rigors / shaking chills; Tender fingertip nodules/bumps (Osler nodes) |
| `sc-033` (`sc-033`) | `medication_safety` | 0 | 0 | 0 | single-span swap | Stopped daily clonidine; Blood pressure 210 over 126; Severe cephalalgia / headache; Diaphoresis / cold sweats |
| `sc-035` (`sc-035`) | `medication_safety` | 0 | 0 | 0 | single-span swap | Two weeks after starting lamotrigine; Fever; Painful oral mucosal erosions / raw mouth sores; Blistering skin detachment / peeling skin blisters |
| `sc-039` (`sc-039`) | `misspelled_everyday` | 0 | 0 | 0 | 1 misspelling (shivering -> shiverring) | High fever context; Violent shivering (1-word everyday spelling contrast: shivering vs shiverring); Flank kidney aching; Nonstop vomiting |
| `sc-040` (`sc-040`) | `misspelled_everyday` | 0 | 0 | 0 | 1 misspelling (itching -> itchhing) | Trigger: five minutes after a bee sting; Full-body itching (1-word everyday spelling contrast: itching vs itchhing); Throat choking; Severe dizziness |
| `sc-042` (`sc-042`) | `misspelled_everyday` | 0 | 0 | 0 | 1 misspelling (sweating -> sweatting) | High fever onset today; Drenching cold sweating (1-word everyday spelling contrast: sweating vs sweatting); Uncontrollable shaking; Blood-streaked coughing |
| `sc-043` (`sc-043`) | `misspelled_everyday` | 0 | 0 | 0 | 1 misspelling (coughing -> coughhing) | Onset tonight with high fever; Barking coughing (1-word everyday spelling contrast: coughing vs coughhing); Throat choking; Inflamed throat with drooling |
| `sc-044` (`sc-044`) | `misspelled_everyday` | 0 | 0 | 0 | 1 misspelling (hearing -> hearring) | Ear infection and fever context; Muffled hearing (1-word everyday spelling contrast: hearing vs hearring); Painful bulging behind ear; Violent shaking |
| `sc-047` (`sc-047`) | `misspelled_multiple` | 0 | 0 | 0 | 3 misspellings in order | Early pregnancy onset today; Heavy vaginal bleeding (misspelled 'bleedding' on bottom); Lower belly aching (misspelled 'acheing' on bottom); Severe dizziness (misspelled 'dizzyness' on bottom) |
| `sc-048` (`sc-048`) | `misspelled_multiple` | 0 | 0 | 0 | 3 misspellings in order | Onset since midnight; Repeated dark vomiting (misspelled 'vomitting' on bottom); Crampy stomach pain (misspelled 'stomache' on bottom); Heavy rectal bleeding (misspelled 'bleedding' on bottom) |
| `sc-049` (`sc-049`) | `misspelled_multiple` | 0 | 0 | 0 | 3 misspellings in order | High fever context; Violent shivering (misspelled 'shiverring' on bottom); Flank kidney aching (misspelled 'acheing' on bottom); Nonstop vomiting (misspelled 'vomitting' on bottom) |
| `sc-050` (`sc-050`) | `misspelled_multiple` | 0 | 0 | 0 | 3 misspellings in order | Trigger: five minutes after a bee sting; Full-body itching (misspelled 'itchhing' on bottom); Throat choking (misspelled 'chokeing' on bottom); Severe dizziness (misspelled 'dizzyness' on bottom) |
| `sc-052` (`sc-052`) | `misspelled_multiple` | 0 | 0 | 0 | 3 misspellings in order | High fever onset today; Drenching cold sweating (misspelled 'sweatting' on bottom); Uncontrollable shaking (misspelled 'shakeing' on bottom); Blood-streaked coughing (misspelled 'coughhing' on bottom) |
| `sc-053` (`sc-053`) | `misspelled_multiple` | 0 | 0 | 0 | 3 misspellings in order | Onset tonight with high fever; Barking coughing (misspelled 'coughhing' on bottom); Throat choking (misspelled 'chokeing' on bottom); Inflamed throat with drooling (misspelled 'inflammed' on bottom) |
| `sc-054` (`sc-054`) | `misspelled_multiple` | 0 | 0 | 0 | 3 misspellings in order | Ear infection and fever context; Muffled hearing (misspelled 'hearring' on bottom); Painful bulging behind ear (misspelled 'bulgeing' on bottom); Violent shaking (misspelled 'shakeing' on bottom) |

## 3. Comma Count, Swap Reconstruction, and Fact-Parity Table: `candidates.json` (30 New Pairs)

| ID | Extends | Family | Top Commas | Bottom Commas | Hyphens | Swap Type | Shared Facts (Both Sentences) |
|---|---|---|---:|---:|---:|---|---|
| `r5-001` | `ag-003` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | Onset 1 hour ago in right foot; Acute rest pain / sudden pain sitting still; Pallor / pale cold toes; Absent pedal pulses / no pulse |
| `r5-002` | `ag-003` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | Onset 1 hour ago; Pressure / paint sprayer punctured / poked index / pointer finger; Digit / finger is pale / white; Cold and numb |
| `r5-003` | `ag-014` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | Onset this evening; Severe unilateral ocular pain / bad pain in one eye; Blurred vision / blurry sight; Rainbow halos / rainbow rings around lights |
| `r5-004` | `ag-014` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | Skin boil and fever context; Severe thoracic spine tenderness / bad middle back soreness; Bilateral lower extremity paraparesis / both legs giving out when standing |
| `r5-005` | `ag-001` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | After a 12 hour flight; Calf swelling; Sudden dyspnea / short breath; Brief syncope / passing out briefly |
| `r5-006` | `ag-006` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | Infected lower molar context; Bilateral submandibular swelling / swelling under both sides of jaw; Trismus / locked jaw; Drooling |
| `r5-007` | `ag-007` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | Onset this hour; Paroxysmal / nonstop coughing; Cup of bright red hemoptysis / blood from lungs; Resting dyspnea / short breath sitting still |
| `r5-008` | `ag-013` | `red_flag_everyday` | 0 | 0 | 0 | single-span swap | After lifting a heavy box; Tense irreducible inguinoscrotal bulge / hard lump by one of my balls that will not push back in; Bilious emesis / green vomit |
| `r5-009` | `ag-065` | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | 6 year old son today; Ventriculoperitoneal shunt / brain fluid tube; Projectile emesis / vomiting across the room; Extreme somnolence / cannot stay awake at all |
| `r5-010` | `ag-065` | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | 4 days after giving birth; Severe occipital headache / bad headache in back of head; Scotomata / dark spots in sight; Blood pressure 176 over 114 |
| `r5-011` | `ag-067` | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | 1 hour after hitting head on a cabinet; Congenital coagulopathy / blood clotting disorder; Progressive cephalalgia / worsening headache; Emesis / throwing up |
| `r5-012` | `ag-067` | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | Missed hemodialysis / kidney dialysis for 4 days; Ascending lower extremity weakness / weakness creeping up both legs; Bradycardia / slow pulse of 38 beats a minute |
| `r5-013` | `ag-070` | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | 9 month old son this morning; Episodic colicky abdominal pain with knees drawn up / spells of belly pain where he pulls his knees up; Currant jelly hematochezia / dark red jelly poop |
| `r5-014` | `ag-070` | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | Spinal cord injury context; Blocked bladder catheter / tube; Pounding headache; Profuse facial diaphoresis / heavy face sweating; Blood pressure 204 over 118 |
| `r5-015` | `ag-071` | `context_raises_urgency` | 0 | 0 | 0 | single-span swap | Age 78; Atrial fibrillation / irregular heartbeat; Sudden severe diffuse periumbilical pain / bad pain all around belly button; Forceful emesis / hard throwing up |
| `r5-016` | `ag-057` | `dialect_non_native` | 0 | 0 | 0 | single-span swap | Sudden onset today on the phone; Expressive aphasia / words coming out wrong; Right homonymous hemianopia / lost sight on right side of both eyes |
| `r5-017` | `ag-057` | `dialect_non_native` | 0 | 0 | 0 | single-span swap | Brother this morning; 10 minute generalized convulsion / 10 minutes of whole body shaking; Urinary incontinence / wet himself; Persistent stupor / still cannot wake up |
| `r5-018` | `ag-052` | `dialect_non_native` | 0 | 0 | 0 | single-span swap | Type 1 diabetes context today; Kussmaul respirations / deep gasping breath; Fruity halitosis / sweet fruit smell on breath; Intractable emesis / nonstop throwing up |
| `r5-019` | `ag-052` | `dialect_non_native` | 0 | 0 | 0 | single-span swap | Standing in kitchen; Abrupt syncope without prodrome / fell out cold with no warning; Pulse of 32 beats a minute |
| `r5-020` | `ag-055` | `dialect_non_native` | 0 | 0 | 0 | single-span swap | Gallstones context today; Right hypochondriac pain / pain under right ribs; Scleral icterus / yellow eyes; Shaking chills |
| `r5-021` | `ag-029` | `metaphor_idiom` | 0 | 0 | 0 | single-span swap | Onset 1 hour ago; Pulsatile abdominal mass / heartbeat thumping in belly; Tearing lumbar pain / pain ripping into lower back; Presyncope / near fainting |
| `r5-022` | `ag-029` | `metaphor_idiom` | 0 | 0 | 0 | single-span swap | Pericarditis / heart sac inflammation context; Severe orthopnea / feeling of suffocating when lying flat; Jugular venous distension / bulging neck veins; Muffled heart sounds / distant heartbeat |
| `r5-023` | `ag-034` | `metaphor_idiom` | 0 | 0 | 0 | single-span swap | Several episodes this week; Epigastric rising aura / rollercoaster drop feeling in stomach; Olfactory hallucinations / phantom burnt rubber smells; Brief staring spells |
| `r5-024` | `ag-041` | `literacy_spelling` | 0 | 0 | 0 | 1 misspelling (tongue -> tounge) | Minutes after eating peanut sauce; Swollen tongue (misspelled tounge on bottom); Nonstop vomiting; Trouble breathing |
| `r5-025` | `ag-043` | `literacy_spelling` | 0 | 0 | 0 | 1 misspelling (inflamed -> inflammed) | Onset this week in left eye; Optic nerve inflamed (misspelled inflammed on bottom); Washed out red color vision; Dizziness |
| `r5-026` | `ag-048` | `literacy_spelling` | 0 | 0 | 0 | 1 misspelling (stomach -> stomache) | Onset 1 hour ago; Sudden rigid stomach pain (misspelled stomache on bottom); Dark rectal bleeding; Severe dizziness |
| `r5-027` | `ag-083` | `medication_safety` | 0 | 0 | 0 | single-span swap | 3 weeks after starting methimazole / thyroid pill; 103 Fahrenheit fever; Rigors / shaking chills; Exudative pharyngitis / white pus on throat |
| `r5-028` | `ag-083` | `medication_safety` | 0 | 0 | 0 | single-span swap | Taking warfarin / blood thinner with sulfamethoxazole trimethoprim / bladder antibiotic; Gross hematuria / dark red blood in pee; Flank pain / side pain; Orthostatic presyncope / near fainting when standing |
| `r5-029` | `ag-076` | `medication_safety` | 0 | 0 | 0 | single-span swap | Doubled furosemide / water pill while taking digoxin / heart pill; Xanthopsia / yellow rings in sight; Emesis / throwing up; Pulse of 36 beats a minute |
| `r5-030` | `ag-018` | `minimizing_hedged` | 0 | 0 | 0 | hedge prefix ("It's probably nothing but ") | Exertional onset while walking up stairs today; Blacked out for 20 seconds; Woke up on the landing |

## 4. Everyday Misspelling Citations (`literacy_spelling` in `candidates.json`)

- `r5-024`: `'tongue'` -> `'tounge'` (OAC CHV `data/chv/CHV_concepts_terms_flatfile_20110204.tsv` `CUI=C0040408`, `term_id=0000033827`; also verified in Wikipedia machine-readable common misspellings list line 4016).
- `r5-025`: `'inflamed'` -> `'inflammed'` (OAC CHV `CUI=C0021368`, `term_id=0000024600`; listed in `gt_measured_20261108.json` `observed_everyday_misspellings_in_repo`).
- `r5-026`: `'stomach'` -> `'stomache'` (OAC CHV `CUI=C0038351`, `term_id=0000033821`; also verified in Wikipedia machine-readable common misspellings list line 3708).
