# Round 11 Final Report (`round11_20261114`)

**Status notice:** All 144 Round 11 case families across `batch_01` to `batch_06` are **drafts awaiting an owner's read, a clinician's review, and a patient-language review**. Automated software checks (`G1`–`G3`) and model-based internal audits (`G4`–`G8`) check structural rules, source-record text matching, and authoring constraints only; they do not establish clinical triage ground truth or spontaneous patient-speech authenticity.

## 1. Families Planned, Passed, and Dropped

### 1.1 Run totals and per-batch totals

- **Planned slots (`plan.json`):** `144` across 6 batches of 24 (`r11-001` to `r11-144`), plus `36` pre-planned reserve slots (`6` per batch, `0` used).
- **Passed internal gates `G1`–`G8`:** `144` (`24` per batch; `360` candidate pairs in `check_pairs.json`, `60` per batch).
- **Dropped:** `0` overall (`0` in every batch).
- **Returned once during pre-assembly `G4`–`G8` auditing and revised before batch assembly:** `32` families (`r11-001, r11-009, r11-025, r11-026, r11-027, r11-028, r11-029, r11-030, r11-044, r11-047, r11-048, r11-052, r11-055, r11-056, r11-061, r11-065, r11-088, r11-092, r11-096, r11-111, r11-112, r11-113, r11-116, r11-118, r11-121, r11-124, r11-125, r11-126, r11-128, r11-129, r11-130, r11-141`).
- **Post-push corrections logged in `revisions.json`:** `11` families in `batch_01` (`r11-001`, `r11-004`, `r11-005`, `r11-006`, `r11-008`, `r11-009`, `r11-010`, `r11-012`, `r11-015`, `r11-016`, `r11-024`), committed in `7fc15b68` per `reviewer_notes.md` (`9632c0a0`) and accepted in `fece726a`. Batches `02`, `03`, and `04` were reviewed and accepted in `reviewer_notes.md` (`8ac69414`, `cd962a7a`, `94e7eed1`) with no text or source corrections; batches `05` and `06` await review.

| Batch | Commit(s) | Planned | Passed `G1`–`G8` | Dropped | Plain register | Dialect | Self-care | L4 (emergency) | L3 (specialist) | L2 (general doctor) | L1 (self-care) | `G2` errors / `-cf` warning pairs (total warnings) | `G3` intake status / errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `batch_01` | `fa68f2e4` (revisions in `7fc15b68`, concern follow-ups in `33fae7da`) | 24 | 24 | 0 | 18 | 4 | 2 | 8 | 7 | 7 | 2 | `0` / `3` (`3`) | `intake` / `0` |
| `batch_02` | `33fae7da` (concern follow-ups in `70861405`) | 24 | 24 | 0 | 18 | 4 | 2 | 7 | 7 | 8 | 2 | `0` / `6` (`9`) | `intake` / `0` |
| `batch_03` | `70861405` | 24 | 24 | 0 | 18 | 4 | 2 | 8 | 7 | 7 | 2 | `0` / `10` (`16`) | `intake` / `0` |
| `batch_04` | `275753b3` | 24 | 24 | 0 | 18 | 4 | 2 | 7 | 7 | 8 | 2 | `0` / `12` (`19`) | `intake` / `0` |
| `batch_05` | `773ab633` | 24 | 24 | 0 | 18 | 4 | 2 | 8 | 7 | 7 | 2 | `0` / `14` (`25`) | `intake` / `0` |
| `batch_06` | `c5c7d240` | 24 | 24 | 0 | 18 | 4 | 2 | 7 | 7 | 8 | 2 | `0` / `11` (`19`) | `intake` / `0` |
| **Total** | — | **144** | **144** | **0** | **108** | **24** | **12** | **45** | **42** | **45** | **12** | `0` / `56` (`91`) | `intake` / `0` |

### 1.2 Group × care-level matrix (planned vs passed vs dropped)

| Group | Care level (`right_care`) | Planned | Passed `G1`–`G8` | Dropped | Notes |
|---|---:|---:|---:|---:|---|
| `plain_register` | `4` (emergency) | 36 | 36 | 0 | 6 per batch; all carry `everyday_attribution`, 12 (`2`/batch) carry `quad_b` + `quad_c` |
| `plain_register` | `3` (specialist) | 36 | 36 | 0 | 6 per batch; all carry `everyday_attribution`, 12 (`2`/batch) carry `quad_b` + `quad_c` |
| `plain_register` | `2` (general doctor) | 36 | 36 | 0 | 6 per batch; 12 (`2`/batch) carry `quad_b` + `quad_c` |
| `dialect` | `4` (emergency) | 9 | 9 | 0 | `2` in `batch_01`, `03`, `05`; `1` in `batch_02`, `04`, `06` |
| `dialect` | `3` (specialist) | 6 | 6 | 0 | `1` per batch across `batch_01`–`batch_06` |
| `dialect` | `2` (general doctor) | 9 | 9 | 0 | `1` in `batch_01`, `03`, `05`; `2` in `batch_02`, `04`, `06` |
| `self_care` | `1` (self-care) | 12 | 12 | 0 | `2` per batch; all controls escalate to level `2` or `3` |
| **Total** | **All (`4, 3, 2, 1`)** | **144** | **144** | **0** | `360` candidate pairs total (`60`/batch) |

## 2. Drops by Gate and Pre-Assembly Return Summary

- **Drops by gate (`G1`–`G8`):** `0` families were dropped at any gate in any batch (`G1: 0, G2: 0, G3: 0, G4: 0, G5: 0, G6: 0, G7: 0, G8: 0`). Every family returned by an auditor during internal review resolved the cited defect on its single permitted return (`SPEC.md` section 6) and subsequently passed a fresh re-audit across all five auditor gates (`G4`–`G8`).
- **Single-return internal catches before batch assembly (`32` families total):**
  - `batch_01` (`2` families): `r11-001` (`G7` citation replacement), `r11-009` (`G4`/`G5` parity and wording).
  - `batch_02` (`9` families): `r11-025`..`r11-030` (`G6`/`G8` Rule A stranded emergency facts in `f1`–`f3` on de-escalated L4 controls), `r11-044` (`G5` pre-stacked symptom adjectives on `'a funny turn'`), `r11-047` and `r11-048` (`G5`/`G7` wording and Rule B evidence).
  - `batch_03` (`5` families): `r11-052` (`G5` Rule C `'my right back'`), `r11-055` (`G4` bare `'digits'` + added control laterality), `r11-056` (`G4` compounded detachment + aspiration in control), `r11-061` (`G7` Rule B clinical morphology sentence), `r11-065` (`G5` Rule C noun stack `'morning arm cuff blood pressure readings'`).
  - `batch_04` (`3` families): `r11-088` (`G7` Rule B study eligibility definition on PMID `17521401`), `r11-092` (`G5` `changed_fact` timeframe collision on `'have had'`), `r11-096` (`G5` Rule C `'my front thighs'`).
  - `batch_05` (`5` families): `r11-111` (`G4` unstated `'across her chest'` in control + `G5` homograph `'12 minute'`), `r11-112` (`G4` extra `'progressive'` in medical variants), `r11-113` (`G4`+`G6` added `'across my cheeks'`/`'hot tea'` stranding `'cool bedroom'`), `r11-116` (`G4` `'breakroom thermometer'` referent ambiguity + `G6` Rule D `'98 F'` overlap with `r11-099`), `r11-118` (`G5` pre-stacked adjectives `'a shaky sweaty funny turn'`).
  - `batch_06` (`8` families): `r11-121` and `r11-125` (`G5` Rule C bare participial splice after predicate age), `r11-124` (`G5` Rule C `'a fast steel sliver'`), `r11-126` (`G7` Rule B + Trend 1 `'knitting together'` X-ray follow-up sentence), `r11-128` (`G5` Rule C `quad_c` `'showing swelling up'`), `r11-129` (`G5` Rule C `'for 5 months ... brings'`), `r11-130` (`G5` Rule C `'rolled stuck upward'`), `r11-141` (`G4` `'across my chest'` widening unilateral `'right side of my chest'`).

## 3. Source Coverage and `same` Source-Fit Share

Across all 144 families, there are `391` `everyday_sources` rows and `72` `attribution` rows (`463` sourceable rows total). Of these, `138` rows carry a verified opened PubMed/PMC/DOI or allowed dictionary citation (`122/391` = `31.2%` of `everyday_sources`, `16/72` = `22.2%` of `attribution` clauses), and `95/138` = **`0.6884` (`68.8%`)** of cited rows match the family's population/condition (`same`), with `43` (`31.2%`) `adjacent` and `0` `different`. Every batch met the `>= 0.50` `same` share target (`SPEC.md` section 8 Gate G7). Following `reviewer_notes.md` `'After batch 04'` Trend 1, cited `everyday_sources` coverage rose from `19.3%` in `batch_04` and `28.3%` in `batch_05` to `44.6%` (`25/56`) in `batch_06`.

| Batch | `everyday_sources` cited / total (%) | `attribution` cited / total (%) | Total cited rows (`source_fit.json`) | `same` | `adjacent` | `different` | `same` share |
|---|---|---|---|---:|---:|---:|---:|
| `batch_01` | `34 / 82` (`41.5%`) | `3 / 12` (`25.0%`) | `37` | 34 | 3 | 0 | `0.9189` (`91.9%`) |
| `batch_02` | `18 / 75` (`24.0%`) | `3 / 12` (`25.0%`) | `21` | 14 | 7 | 0 | `0.6667` (`66.7%`) |
| `batch_03` | `19 / 68` (`27.9%`) | `2 / 12` (`16.7%`) | `21` | 11 | 10 | 0 | `0.5238` (`52.4%`) |
| `batch_04` | `11 / 57` (`19.3%`) | `3 / 12` (`25.0%`) | `14` | 9 | 5 | 0 | `0.6429` (`64.3%`) |
| `batch_05` | `15 / 53` (`28.3%`) | `3 / 12` (`25.0%`) | `18` | 11 | 7 | 0 | `0.6111` (`61.1%`) |
| `batch_06` | `25 / 56` (`44.6%`) | `2 / 12` (`16.7%`) | `27` | 16 | 11 | 0 | `0.5926` (`59.3%`) |
| **Run total** | **`122 / 391` (`31.2%`)** | **`16 / 72` (`22.2%`)** | **`138`** | **95** | **43** | **0** | **`0.6884` (`68.8%`)** |

## 4. Unsourced Expressions (`"source": "none"`)

In accordance with `SPEC.md` section 7 and `reviewer_notes.md` Rule B (*'When only such a sentence exists, the row is `"source": "none"`. An unsourced row is acceptable'*), `325` rows across the run (`269` `everyday_sources` rows and `56` `attribution` rows) are marked `"source": "none"`. Full per-batch inventory:

### 4.1 `batch_01` (`57` unsourced rows: `48` everyday, `9` attribution)

- `r11-001`: `"crushing pressure behind my breastbone"`, `"high blood pressure medicine"`, `"medicine for high blood pressure"`, `"a dry cough"`, `"and I think it is heartburn"` [attr]
- `r11-002`: `"glasses for nearsightedness"`, `"yellow discharge"`, `"and I think it is eyestrain"` [attr]
- `r11-003`: `"7 weeks pregnant"`, `"burning when I pee"`, `"and I think it is trapped gas"` [attr]
- `r11-004`: `"a hard workout"`, `"mild skin chafing in his right groin"`, `"and I think he pulled a groin muscle"` [attr]
- `r11-005`: `"farsighted"`, `"mild eyestrain"`, `"and I think it is allergies"` [attr]
- `r11-006`: `"birth control pills"`, `"coughing up yellow phlegm"`, `"and I think it is from dry air"` [attr]
- `r11-007`: `"wore a right wrist splint at night"`, `"gets a faint strap mark"`
- `r11-008`: `"trouble breathing"`, `"and I think it is just teething"` [attr]
- `r11-009`: `"prescribed antibiotics by mouth"`, `"mild dry skin"`, `"and I think it is poor hygiene"` [attr]
- `r11-010`: `"nonstop fast talking"`, `"started throwing furniture at me"`
- `r11-011`: `"worry about surface germs"`, `"carry hand sanitizer"`
- `r11-012`: `"fading hearing in my left ear"`, `"painful swelling behind my left ear"`, `"and I think it is from getting older"` [attr]
- `r11-013`: `"the right side of my face started drooping"`
- `r11-014`: `"a 40 C fever"`
- `r11-015`: `"skin sores around his mouth"`, `"a 40 C fever"`
- `r11-016`: `"over the counter vaginal antifungal cream"`, `"severe lower belly pain"`
- `r11-017`: `"right foot arch tightness"`, `"my right foot turning blue"`
- `r11-018`: `"tender red bump on my right upper eyelid edge"`, `"crusts on my right eyelashes"`, `"started seeing double"`
- `r11-019`: `"forehead headaches"`, `"headaches in my forehead"`, `"had trouble concentrating"`
- `r11-020`: `"got confused about where he is"`, `"became confused about where he is"`, `"lost his appetite"`
- `r11-021`: `"seizure medicines"`
- `r11-022`: `"double vision"`
- `r11-023`: `"dry peeling skin"`, `"dry flaking skin"`, `"oozing thick yellow pus"`
- `r11-024`: `"throw up repeatedly"`

### 4.2 `batch_02` (`66` unsourced rows: `57` everyday, `9` attribution)

- `r11-025`: `"sharp severe pain in my right lower belly"`, `"a big meal"`, `"mild bloating in my lower belly"`, `"and I think it is indigestion"` [attr]
- `r11-026`: `"a sudden stiff neck"`, `"a 39 C fever"`, `"white pus on my tonsils"`, `"and I think it is the flu"` [attr]
- `r11-027`: `"my left foot suddenly turned cold"`, `"left calf cramps when walking"`, `"those cramps eased with rest"`, `"and I think it is cold air"` [attr]
- `r11-028`: `"poop with dark red bloody mucus"`, `"started daycare"`, `"poop with tiny white moving worms"`, `"and I think it is a stomach bug"` [attr]
- `r11-029`: `"soaked 3 pads with heavy vaginal bleeding in 1 hour"`, `"gave birth 2 weeks ago"`, `"clumpy white vaginal discharge"`, `"and I think my period came back"` [attr]
- `r11-030`: `"fast spreading hard swelling under my jaw"`, `"cracked a lower molar"`, `"a sharp rough edge on that tooth"`, `"and I think it is a swollen gland"` [attr]
- `r11-031`: `"a routine eye test at the optometrist"`, `"and I think it is eye strain"` [attr]
- `r11-032`: `"stuck on the left side of my tongue"`, `"that is gushing bright red blood"`
- `r11-033`: `"a painful thick raised scar growing past the piercing hole"`, `"a tiny flat healed scar at"`, `"and I think friction caused it"` [attr]
- `r11-034`: `"now have a resting heart rate of 180 beats a minute"`
- `r11-035`: `"brief mild moments of missing her during my daily life"`, `"and I think it is from living alone"` [attr]
- `r11-036`: `"have taken ibuprofen during my periods"`, `"only get mild cramps"`
- `r11-037`: `"felt tired"`, `"peeing often"`, `"started gasping for breath"`
- `r11-038`: `"soaks my work papers"`, `"leaves them slightly damp"`
- `r11-039`: `"ring shaped red patch"`, `"its edge is scaly"`, `"a 40 C fever"`
- `r11-040`: `"my left ear has felt plugged"`, `"painful swelling behind that ear"`
- `r11-041`: `"rolled my right ankle inward"`, `"mildly swollen"`, `"my right foot is turning blue"`
- `r11-042`: `"bulging twisted veins"`, `"dull aching in those veins"`, `"blood spurting from a leg vein"`
- `r11-043`: `"between my shoulder blades"`, `"mild muscle soreness"`
- `r11-044`: `"where my head spins"`, `"feel mildly unsteady walking"`, `"keep falling to the floor"`
- `r11-045`: `"blood pressure pill"`
- `r11-046`: `"standing still"`, `"resting pulse"`
- `r11-047`: `"friction blister"`, `"filled with clear fluid"`, `"draining cloudy yellow pus"`
- `r11-048`: `"small red bumps"`, `"feel mildly itchy"`, `"are oozing yellow pus"`

### 4.3 `batch_03` (`59` unsourced rows: `49` everyday, `10` attribution)

- `r11-049`: `"started hydroxyurea pills"`, `"had mild nausea after my morning pill for 5 days"`, `"and I think it is acid reflux"` [attr]
- `r11-050`: `"fast spreading dark purple spots on her legs that stay dark when pressed"`, `"a mild sore throat"`, `"started sneezing with a mild clear runny nose"`
- `r11-051`: `"suddenly turned hard and severely painful"`, `"stays soft and flattens right back in whenever I lie down"`, `"and I think it is trapped gas"` [attr]
- `r11-052`: `"peed out gritty sand"`, `"My lower back and right side ached"`, `"and I think I pulled my back"` [attr]
- `r11-053`: `"got sudden severe shortness of breath sitting still"`, `"row on a college crew team"`, `"keep getting mild shortness of breath during hard sprints this month"`, `"and I think it is seasonal allergies"` [attr]
- `r11-054`: `"34 weeks pregnant"`, `"noticed new pink stretch marks across my lower belly this week"`, `"and I think it is my mucus plug"` [attr]
- `r11-055`: `"my finger skin got tight and shiny"`, `"and I think it's poor circulation"` [attr]
- `r11-056`: `"scrapes the left side of my tongue when I chew"`, `"sliced a deep heavily bleeding gash into the left side of my tongue when I chewed"`, `"and I think I bit something hard"` [attr]
- `r11-057`: `"got a widening smooth bald patch on my crown"`, `"noticed mild dry white flaking on my scalp"`, `"and I think it's stress"` [attr]
- `r11-058`: `"feel driven to check my baby's breathing 30 times"`, `"calmly check my baby's breathing once before bed"`, `"and I think it's new mom nerves"` [attr]
- `r11-059`: `"I feel brief mild pressure for 5 seconds during the exam"`, `"and I think I'm just too tense"` [attr]
- `r11-060`: `"passed large maroon blood clots into the toilet 4 times this hour"`
- `r11-061`: `"coin shaped red patches"`, `"stayed dry and itchy"`, `"cleared up completely after"`
- `r11-062`: `"trouble starting to pee"`, `"wake 4 times a night to pee"`, `"have a painful full bladder passing only drops for 14 hours"`
- `r11-063`: `"red scratch marks around her bottom"`, `"painful dark red tissue bulging from her bottom"`
- `r11-064`: `"thin gray vaginal discharge"`, `"light clear stretchy vaginal discharge"`
- `r11-065`: `"checked my blood pressure with an arm cuff"`, `"stays around 154 over 96"`, `"118 over 74"`
- `r11-066`: `"a tickle in my throat"`, `"my tongue swelled up fast"`
- `r11-067`: `"mild stitch pulling when swallowing"`
- `r11-068`: `"felt briefly lightheaded for 5 seconds"`
- `r11-070`: `"cloudy foul smelling pee"`, `"mild queasiness"`, `"vomiting every sip of water for 10 hours"`
- `r11-071`: `"red bump"`, `"itches mildly"`, `"throbs with sharp pain"`
- `r11-072`: `"hard dry stools"`, `"mild lower belly bloating"`, `"stools streaked with dark red blood"`

### 4.4 `batch_04` (`55` unsourced rows: `46` everyday, `9` attribution)

- `r11-073`: `"a dull headache across my forehead"`, `"running a portable gas generator inside the closed garage"`, `"staring at spreadsheets on my laptop"`, `"and I think it's dehydration"` [attr]
- `r11-074`: `"got strong lye drain cleaner splashed into my right eye"`, `"clean lukewarm faucet water"`, `"and I think trapped air made it splash"` [attr]
- `r11-075`: `"been peeing a lot"`, `"and I think it's her diet"` [attr]
- `r11-076`: `"brief aches under my right ribs"`, `"the whites of my eyes turned yellow"`, `"had 3 of those 20 minute aches this week"`
- `r11-077`: `"got a deep gash on my right shin with bone sticking out"`, `"got a shallow 2 cm road scrape on my right shin"`, `"and I think that piece is gravel"` [attr]
- `r11-078`: `"a loud harsh squeak on every breath in while resting"`, `"a mild watery runny nose"`, `"gave 3 brief dry coughs after lying down"`, `"and I think it's bedroom dust"` [attr]
- `r11-079`: `"recurring painful draining tunnels under my armpit skin"`, `"got brief mild razor sting on my armpit skin"`, `"and I think they're ingrown hairs"` [attr]
- `r11-080`: `"my jaw joint locked rigid wide open when I opened my mouth wide"`
- `r11-081`: `"slow shuffling steps"`, `"both my legs suddenly went limp under me when walking"`, `"and I think it's old age"` [attr]
- `r11-082`: `"make myself throw up my meal right after"`, `"I threw up a bowlful of fresh red blood right after eating"`, `"and I think it's college stress"` [attr]
- `r11-083`: `"intense fear of speaking in front of coworkers makes me skip every meeting"`, `"I feel brief mild butterflies right before speaking in front of coworkers"`, `"and I think I'm just shy"` [attr]
- `r11-084`: `"for 2 months"`
- `r11-085`: `"on the outer side of my right elbow"`, `"felt slight soreness on the outer side of my right elbow for 10 minutes after gripping tools yesterday"`
- `r11-086`: `"tore a hangnail beside my right index fingernail"`, `"a painful swollen pocket of white pus"`, `"clean smooth healed skin"`
- `r11-087`: `"scalp itching behind both ears"`, `"tiny white specks stuck to his hair strands"`, `"hot boggy swelling across his scalp"`
- `r11-088`: `"on toilet paper"`, `"heavy bright red blood has been pouring from my rectum for 20 minutes"`
- `r11-089`: `"felt queasy and thrown up"`, `"keeping daytime meals and water down"`, `"have retched up bile 18 times since midnight"`
- `r11-090`: `"the nails on both big toes have been thick and yellow"`, `"their tips are crumbly"`, `"red streaks started spreading up from those big toes"`
- `r11-093`: `"mild belly bloating"`
- `r11-095`: `"fine white flakes"`, `"raw weeping open sores"`
- `r11-096`: `"sore muscles in the front of my thighs"`, `"feel mildly stiff when walking"`, `"make me limp on every step"`

### 4.5 `batch_05` (`47` unsourced rows: `38` everyday, `9` attribution)

- `r11-097`: `"blood pressure pills"`, `"she has forgotten scheduled appointment dates more often over 9 months"`, `"and I think it's from waking up early"` [attr]
- `r11-098`: `"every swallow of my own spit comes straight back up"`, `"I have had mild hiccups off and on"`, `"and I think I chewed too fast"` [attr]
- `r11-099`: `"aching and swelling in my right knee"`, `"my thermometer read"`, `"and I think it's from gardening"` [attr]
- `r11-100`: `"thrown up 6 times"`, `"have gained 12 pounds around my waist over 4 months"`, `"and I think it's something I ate last night"` [attr]
- `r11-101`: `"unable to pee at all"`, `"noticed my pee stream has been slower than usual"`, `"and I think it's hot weather"` [attr]
- `r11-102`: `"feel mild itching along the dry healing scar over that collarbone"`, `"and I think it's indigestion"` [attr]
- `r11-103`: `"a slight even sun tan"`, `"and I think it's sun damage"` [attr]
- `r11-104`: `"painful raw sore on the roof of my mouth"`, `"it lodged stuck across the back of my throat"`, `"and I think my gums shrank"` [attr]
- `r11-105`: `"192"`
- `r11-106`: `"glanced at my nose in the mirror for 2 minutes each morning before heading to work"`, `"and I think it's vanity"` [attr]
- `r11-107`: `"on the past 2 nights"`
- `r11-108`: `"monthly period"`, `"29 days ago"`
- `r11-109`: `"a sore throat and tender swollen neck glands"`, `"feels worn out every afternoon"`, `"started making a harsh squeaking sound on every breath in today"`
- `r11-110`: `"along the thumb side of my right wrist"`, `"felt a quick twinge along the thumb side of my right wrist that faded right away when picking up my baby once"`
- `r11-111`: `"dimpled bumps"`, `"the skin around them turned red and itchy"`, `"large sheets of tender red skin started peeling off around those bumps today"`
- `r11-112`: `"behind my breastbone at every dinner"`, `"a hurried bite of steamed rice paused behind my breastbone for 3 seconds once last month"`
- `r11-113`: `"woken up 4 times every night for 3 months soaked"`, `"woke up feeling mildly warm from a single hot flush 2 weeks ago"`
- `r11-114`: `"took it off yesterday"`, `"an itchy red patch of oozing blisters"`, `"saw a light clasp dent on my left wrist that smoothed out in 15 minutes"`
- `r11-119`: `"shallow 1 cm paper cut on the side of my right index finger"`, `"feels mildly sore when I press it"`, `"warm and swollen with bright red skin around it"`
- `r11-120`: `"woken up wide awake"`

### 4.6 `batch_06` (`41` unsourced rows: `31` everyday, `10` attribution)

- `r11-121`: `"sudden severe pain all across my belly"`, `"and I think it's spoiled soup"` [attr]
- `r11-122`: `"swallowed a mouthful of lye liquid drain cleaner"`, `"canola cooking oil"`, `"and I think the cap was loose"` [attr]
- `r11-123`: `"his right eye started bulging forward"`, `"his right eye watered mildly when he sneezed"`, `"and I think a bug bit him"` [attr]
- `r11-124`: `"got a fast moving steel sliver stuck in my right eye"`, `"felt mild dryness in my right eye at quitting time"`, `"and I think it's surface dust"` [attr]
- `r11-125`: `"and I think it's from too much coffee"` [attr]
- `r11-126`: `"pain in my right forearm straightening my fingers"`, `"and I think it's knitting together"` [attr]
- `r11-127`: `"firm scarred bumps joining together on the back of my neck"`, `"got 2 tiny superficial pimples on the back of my neck"`
- `r11-128`: `"that swelling ballooned rock hard pushing my tongue upward"`, `"and I think it's a toothache"` [attr]
- `r11-129`: `"both feet went completely numb and paralyzed at rest"`, `"and I think it's aging"` [attr]
- `r11-130`: `"throat clearing noises"`, `"both my eyes rolled up and got stuck in a painful spasm"`
- `r11-131`: `"intense fear of needles makes me walk out of the lab"`, `"I feel brief mild nervousness and look away calmly"`, `"and I think I'm just squeamish"` [attr]
- `r11-132`: `"dull ache"`, `"that testicle suddenly pulled up high with agonizing pain"`, `"and I think it's muscle strain"` [attr]
- `r11-133`: `"got 1 oval pink patch on my chest"`, `"that chest patch shrank to a barely visible pale mark today"`
- `r11-134`: `"ached mildly in my palm for 5 minutes yesterday"`
- `r11-135`: `"had 1 tiny flat pink dot on his palm this morning that faded by noon"`
- `r11-136`: `"pinching my nose"`, `"had 1 brief nosebleed from my right nostril that stopped within 1 minute of pinching my nose"`
- `r11-137`: `"a bald scalp"`, `"had mild warmth on my scalp yesterday evening that subsided overnight"`
- `r11-138`: `"woken from sleep 3 nights a week"`, `"woke from sleep 1 time 3 weeks ago with a 20 second cramp in both calves"`
- `r11-142`: `"belly bloating"`
- `r11-143`: `"large fluid blisters wrapping 15 cm around it"`
- `r11-144`: `"a mild dull forehead ache"`

## 5. Stated Negatives and Justifications

- **Run total:** `0` stated negatives across all 144 families (`0` in `batch_01`, `0` in `batch_02`, `0` in `batch_03`, `0` in `batch_04`, `0` in `batch_05`, `0` in `batch_06`; ceiling `<= 3` per batch in `SPEC.md` section 5.3).
- **Justifications:** None required, because every `changed_fact` control across all six batches was constructed around a positive checkable fact (a measured value, onset, duration, count, severity, or same-site symptom property) rather than a volunteered symptom absence.

## 6. Stop Rules (`SPEC.md` Section 9)

| Stop rule (`SPEC.md` §9) | Triggered? | Record |
|---|---|---|
| **1.** A batch ends with fewer than 16 families passing all gates | **No** | Every batch (`batch_01`–`batch_06`) passed `24 / 24` families. |
| **2.** More than 6 families of a batch are dropped at the same gate | **No** | `0` families were dropped at any gate in any batch. |
| **3.** `@sources` finds a nonexistent citation or missing evidence sentence in a family that already passed `G7` | **No** | Every cited PubMed/PMC/DOI and allowed dictionary record existed and contained its verbatim evidence sentence. *(Note: in `batch_01`, independent owner review flagged 5 rows whose real sentences did not demonstrate patient speech in use, prompting `reviewer_notes.md` Rule B and commit `7fc15b68` before `batch_02`.)* |
| **4.** Any agent opens a path listed under Hard Limit 2 | **No** | Zero outcome, `trace_out/`, `pilot/`, `data/pab/`, `pairs_*.json`, `agscen_*`, `gt_measured_*`, `analysis.md`, `round5`–`round8`, holdout/sealed, or `../patientwords` paths were opened by any agent. |
| **5.** `batch_06` is pushed | **Yes** | Triggered upon pushing `batch_06` (`c5c7d240`), ending the run and initiating this report. |

## 7. Uncertainties and Open Items for Human Review

Across `batch_01` to `batch_06`, `69` open non-blocking concerns (`35` `pending_clinical_review`, `34` `pending_patient_language_review`) plus `3` `withdrawn` concerns (`batch_01` `r11-004-c1`, `r11-004-c2`, `r11-005-c1`, superseded by `7fc15b68`) are recorded in `batch_NN/concerns_selfreported.json`:

1. **Clinical triage boundary calls (`35` open `pending_clinical_review` concerns across `batch_01`–`batch_06`):**
   - **Level 4 emergency vs same-day clinic/doctor/specialist (`control_level_disputed` and `level_disputed`):** Several presentations and escalated controls sit near real-world triage thresholds where an emergency department vs an urgent same-day outpatient/specialist visit is a clinician's call — e.g., acute mastoid-area post-auricular pain/swelling (`r11-012`, `r11-040`), acute severe pelvic/abdominal pain after cream (`r11-016`), high fever with spreading rash or focal cellulitis (`r11-006`, `r11-015`, `r11-039`, `r11-087`), deep hand/oral/cutaneous infections (`r11-049`, `r11-055`, `r11-056`, `r11-067`), acute locked jaw (`r11-080`), diabetic/vascular foot changes (`r11-090`), acute stridor/skin-peeling/fainting/varicocele/neurological controls and specialist-vs-GP boundaries (`r11-060`, `r11-063`, `r11-076`, `r11-084`, `r11-093`, `r11-096`, `r11-100`, `r11-101`, `r11-105`, `r11-108`, `r11-112`, `r11-114`, `r11-116`, `r11-121`, `r11-125`, `r11-129`, `r11-132`, `r11-135`, `r11-137`, `r11-144`).
   - **De-escalated controls on chronic medications (`r11-100`, `r11-121`, `r11-125`):** In older or steroid/diltiazem/lithium-treated patients, mild symptoms after de-escalation are labeled `right_care_after: 1` or `2`; clinicians should confirm whether background medication history warrants routine clinic contact (`2`) vs home observation (`1`).
2. **Spontaneous patient-language naturalness (`34` open `pending_patient_language_review` concerns):**
   - Unsourced everyday expressions (`269` `everyday_sources` rows and `56` `attribution` rows, listed in Section 4) and `adjacent`-fit cited rows (`43` rows adapted across age, speaker role, or neighbouring condition) rely on author and `@language` judgment rather than direct quotes from the exact target demographic.
   - Early-batch wording items flagged in `reviewer_notes.md` Rule C (`r11-002` `'blocking the field of view'`, `r11-017` `'with right foot arch tightness'`, `r11-018` `'ciliary crusting'`) were left unedited per `reviewer_notes.md` (*'These are not corrections. They are logged for the patient-language reviewer'*) and await human language review.
   - Single-sentence unpunctuated carrier-frame constraints (`<= 40` words, no commas/semicolons/hyphens) occasionally require `"and"` coordination where spoken transcripts would pause with commas or sentence breaks.

## 8. What Was Verified vs What Was Assumed

### 8.1 Verified deterministically or against primary records

- **Gate `G1` (`tools/assemble_batch.py` + `tools/validate_family.py`):** Exact Round 10 JSON key structure, batch composition (`18` plain + `4` dialect + `2` self-care per batch), `<= 40`-word single-sentence limit, no commas/semicolons/hyphens, digits for numbers, first-person active openings, exact single-stretch `swap_spans` replacement (`medical.replace(medical_span, everyday_span, 1) == everyday`, word-count delta `<= 2`), exact single-stretch `changed_fact` replacement (`everyday.replace(from, to, 1) == changed_fact`), single inserted `attribution` clause, dialect `core` lexicon retention in `everyday_paraphrase` and absence from plain/self-care families, target-token urgency tier equality against `origin/main` `data/urgency_tiers.draft.json` (`tier` values only), cross-batch `changed_fact.to` uniqueness (`Rule D` on `batch_03`–`batch_06`), and deterministic byte-identical rebuild SHA-256 hashes.
- **Gate `G2` (`scripts/check_candidate_pairs.py`):** `0` errors across all `360` pairs (`60` per batch); all `91` warnings across `56` pairs occur solely on `-cf` (`changed_fact`) pairs that intentionally alter numeric values, counts, or durations.
- **Gate `G3` (`python -m scripts.experiments.cli intake --no-write` on `../pw-main`):** `status: "intake"` and `0` software errors on every batch (`r11_b01`..`r11_b06`), cross-checked cumulatively against `round9_20261110`, `round10_20261112_rev1`, and all preceding Round 11 batches, plus `--concerns` verification on every `batch_NN/concerns_selfreported.json`.
- **Gate `G7` (`@sources`):** Every one of the `138` cited rows across `batch_01`–`batch_06` was opened on PubMed/PMC/DOI or an allowed dictionary (`Wiktionary`, `Merriam-Webster`) with title, identifier, access level, verbatim single-sentence evidence, and Rule B wording-in-use checked.
- **Repository & outcome-blind boundaries:** `git status` / `git log` confirm writes occurred exclusively inside `drafts/antigravity_scenarios_20261107/round11_20261114/`, `SPEC.md` and `reviewer_notes.md` remained unedited by agents, no study models/tokenizers or paid workflows were invoked, and no Hard Limit 2 path was opened.

### 8.2 Assumed (not verifiable without human review or full print archives)

- **Clinical triage labels (`right_care` and `right_care_after`):** Assigned by authors and checked by `@level` and `@adversary` (language models), not by a licensed clinician.
- **Naturalness of unsourced and adapted expressions:** Unsourced expressions (`325` rows) and `adjacent`-population cited expressions (`43` rows) are assumed to sound natural for each family's described speaker pending patient-language review.
- **Abstract-only / non-PMC full-text boundaries:** Where a PubMed citation was verified from `"abstract only"` (`access: "abstract only"`), we verified the exact sentence in the PubMed abstract record without assuming unseen full-text context; for `r11-001` (`PMID 11976241`), where PMC returned no XML body text in independent review, only the remaining verified row was retained after `7fc15b68`.

## 9. Where the Run Stalled or Needed Extra Steps, and What Change to `SPEC.md` Would Have Prevented It

1. **Cross-system `changed_fact` swaps in `batch_01` (`8` post-push revisions in `7fc15b68`) and repeated stock control phrases across `batch_01`–`batch_02` (`Rule D`):**
   - *What happened:* `SPEC.md` section 5.3 permitted changing *'one present symptom against a different present symptom'*, which led `plan.json` and `batch_01` authors to swap a symptom to an unrelated organ system (`8` families in `batch_01`) and reuse stock L4 phrases (`'40 C fever'`, `'painful swelling behind ... ear'`, `'turning blue'`, `'yellow pus'`) across multiple slots.
   - *Preventive `SPEC.md` change:* Incorporate `reviewer_notes.md` **Rule A** and **Rule D** directly into `SPEC.md` sections 4 and 5.5: require `changed_fact` to stay inside the same clinical case (preferring measured-value or same-symptom property changes where every unchanged fact still makes sense when read aloud), and forbid repeating `changed_fact.to` wording or stock escalation phrases across the round.
2. **Citations mentioning a phrase without showing patient wording in use (`5` source revisions in `batch_01`) and mid-run dip in cited everyday share (`19.3%` in `batch_04`):**
   - *What happened:* `SPEC.md` section 7 required copying an exact sentence from an opened source, which allowed sentences reporting that patients *rejected* a phrase/belief or clinical study definitions (`batch_01`), and once Rule B excluded weak sentences, authors increasingly defaulted to `"source": "none"` through `batch_04` before `"After batch 04"` Trend 1 restored active qualitative literature search (`44.6%` cited `everyday_sources` in `batch_06`).
   - *Preventive `SPEC.md` change:* Add `reviewer_notes.md` **Rule B** plus Trend 1's search-before-`none` expectation directly to `SPEC.md` section 7 (require evidence sentences to show patients/carers using the wording/belief in that sense, and instruct authors/`@sources` to search qualitative symptom-description studies before marking an expression `none`).
3. **Concern withdrawal semantics and `@level` clinical-judgment concern threshold (`2` follow-up commits in `33fae7da` and `70861405`):**
   - *What happened:* `SPEC.md` section 10 listed only open concern statuses (`pending_clinical_review | pending_patient_language_review | open`) and forbade closing concerns, leaving ambiguous how to handle concerns rendered moot by a revision (`3` records in `batch_01`) and how consistently `@level` should log non-blocking concerns on borderline L4-vs-same-day-doctor controls (`batch_02`).
   - *Preventive `SPEC.md` change:* Document the `withdrawn` disposition (`status: "withdrawn"`, matching `by`/`by_kind` to `raised_by`/`raised_by_kind` with an explanatory note; never delete a concern record) in `SPEC.md` section 10, and state in Gate `G6` that `@level` must log a non-blocking concern whenever emergency care vs same-day outpatient care is a clinical judgment call.
4. **Sandbox approval pauses on `../pw-main` / `.venv`, transient 5-auditor `503` bursts, and owner checkpoints:**
   - *What happened:* The owner intentionally paused after `batch_01`, `batch_02`, and `batch_03` for incremental calibration via `reviewer_notes.md`. During unattended execution of `batch_04`–`batch_06`, each batch still paused on host permission prompts for `.venv/bin/python` (outside standard sandbox) and `git add`/`commit`/`push`, one macOS update/sleep interrupted in-flight workers during `batch_06` (cleanly recovered from `ledger.json` and disk files), and firing 5 `gemini-4-carbon-high` workers simultaneously triggered a transient HTTP `503` capacity error on two auditors in `batch_06` (resolved by staggering 2–3 Carbon auditors per sub-wave).
   - *Preventive `SPEC.md` change:* Note in `SPEC.md` section 9 that auditor dispatches may be staggered in pairs (`2`–`3` concurrent workers on the same high-tier model) to avoid capacity spikes, and list `.venv/bin/python` + `../pw-main` as pre-whitelisted local paths when running inside a sandboxed agent environment.
