---
title: "PatientWords — site text for manual editing"
date: "2026-07-17"
output: html_document
---

**Instructions.**
Edit the site text in place, block by block.
Each block is preceded by an HTML comment id (`<!-- id: <page>.bNNN -->`) that maps it back to its page and position — keep the comments and do not reorder blocks.
To delete text, delete the block body but keep its id comment.
Dynamic table/chart text is generated at runtime by page JS from the data files and is not included here.
Site navigation and footers are excluded; the provenance & acknowledgments footer content is protected.

# PatientWords — clinical vs. patient language in medical AI circuits — `index.html`

> ⚑ meta description: Attribution-graph comparisons of clinical vs. colloquial patient language in gemma-2-2b, built on Neuronpedia and circuit-tracer.

<!-- id: index.b001 -->
Research bulletin · mechanistic interpretability of medical language · gemma-2-2b

<!-- id: index.b002 -->
## Patients don’t speak like doctors. Small open models change their next-word predictions when the wording does.

<!-- id: index.b003 -->
We trace how gemma-2-2b reads clinical terms versus the everyday words patients use. Wording can change the model's top next word in addition to its confidence, and rewriting the sentence in clinical terms restores it in 8 of the 20 hardest cases. Try the live case below.

<!-- id: index.b004 -->
Every figure is a live render: columns are the prompt’s words in order; height is depth in the model; the predicted next word sits at the top. Nodes (the dots) are features — size is contribution, color is category. Curves are paths of influence; the spread at the top shows the competing next-word continuations ranked by probability. Hover any node for its identity and mass.

<!-- id: index.b005 -->
“When the dust kicks up my asthma flares, so at work I keep a spare ___”

<!-- id: index.b006 -->
live measurements, scenario 85 · open the full trace · browse all scenarios

<!-- id: index.b007 -->
clinical / recovery off-target (the patient-language direction) structural / context language penalty

<!-- id: index.b008 -->
## Four comparison engines

<!-- id: index.b009 -->
*caption:* live trace

<!-- id: index.b010 -->
Fig. 1 · wording: one-word swap

<!-- id: index.b011 -->
### Swap the word

<!-- id: index.b012 -->
One phrase swapped — “asthma flares” vs. “chest gets all tight” — as two stacked graphs. The numbers are in the demo above; the trace shows where the probability goes.

<!-- id: index.b013 -->
live trace: gemma-2-2b · gemma scope transcoders hosted circuit-tracer via Neuronpedia · traced July 7, 2026 · scenario 85 of the simulated series

<!-- id: index.b014 -->
*caption:* live render · simulated scenario

<!-- id: index.b015 -->
Fig. 2 · wording: grammar × lexicon

<!-- id: index.b016 -->
### Swap the grammar

<!-- id: index.b017 -->
A 2×2 grid crossing wording (patient vs. medical) with grammar (standard vs. nonstandard). From our analysis, changing the grammar alone shifts +11–13% toward the everyday continuation, even when the medical word stays (Box B).

<!-- id: index.b018 -->
traced model: gemma-2-2b · gemma scope transcoders hosted circuit-tracer via Neuronpedia

<!-- id: index.b019 -->
*caption:* Fig. 3 · dialect · live specimen Same medical situation. Different framing. Different prediction.

<!-- id: index.b020 -->
traced model: gemma-2-2b · gemma scope transcoders 45 graphs · 5 baselines + 40 framings · from the dialect framings batch of July 8, 2026

<!-- id: index.b021 -->
*caption:* live trace

<!-- id: index.b022 -->
Fig. 4 · translation recovery

<!-- id: index.b023 -->
### Translation

<!-- id: index.b024 -->
An LLM rewrites the patient sentence into clinical terms, and the rewrite is evaluated. The clinical features and the target probability often both come back.

<!-- id: index.b025 -->
live trace: gemma-2-2b · gemma scope transcoders hosted circuit-tracer via Neuronpedia · traced July 7, 2026 · phrase 17 of the reviewed downgrade set (predictions that fell to a lower care tier)

<!-- id: index.b026 -->
## Simulated scenarios

<!-- id: index.b027 -->
*caption:* live renders · simulated data

<!-- id: index.b028 -->
Sim series · generated pairs · simulated data

<!-- id: index.b029 -->
### Simulated Scenarios

<!-- id: index.b030 -->
Claude writes new patient-vs-clinical pairs in the hand-built dataset’s format — one term swapped per pair — and automatic validators accept or reject each. Accepted pairs are traced on gemma-2-2b and published with the generator’s rationale and cost. Kept separate from the hand-measured set.

<!-- id: index.b031 -->
traced model: gemma-2-2b · gemma scope transcoders simulated data · generating model and cost in the per-batch sidecar

<!-- id: index.b032 -->
## Safety view — urgency of the predicted actiontiers owner-reviewed v1 · domain review pending

<!-- id: index.b033 -->
Not every flip is equal: the model hedges (top answer holds, loses probability) or redirects; a redirect down the care ladder is a downgrade. Definitions and the five-tier ladder live in methods step 4. These are next-word probabilities in small open models on LLM-written test sentences, not clinical outcomes; scope and caveats are on the methods page.

<!-- id: index.b034 -->
when a wording change moves the top answer across care tiers, the move is mostly down · red arrows: answers landing on a lower tier · grey: a higher one · phrase-deduped counts per model · LLM-authored stimuli

<!-- id: index.b035 -->
Per-model statistics with multiple-comparison correction: the interim table on the Technical page.

<!-- id: index.b036 -->
## Phrase dataset

<!-- id: index.b037 -->
measured on: gemma-2-2b · gemma scope transcoders → observed next token · p = observed next-token probability · via the neuronpedia circuit tracer

<!-- id: index.b038 -->
*fold:* The five pairs with the largest observed effect, from the hand-built set.

<!-- id: index.b039 -->
Hand-measured on gemma-2-2b (Gemma Scope transcoders) via the Neuronpedia circuit tracer; next-token probabilities as observed at measurement time.

<!-- id: index.b040 -->
preview: observed-token flips and biggest probability gaps first · full dataset (all pairs) →

<!-- id: index.b041 -->
## Model evaluations

<!-- id: index.b042 -->
One set of AIs writes the test, another takes it, and translating patient words into clinician language loses information. The full audit lives on the methods page; the measured models compare on the Technical page.

<!-- id: index.b043 -->
Figs. 1–4, the simulated scenarios, and the phrase-dataset measurements are live gemma-2-2b traces.

<!-- id: index.b044 -->
SIMULATED DATA: the sentence pairs measured across this site are written by an LLM and checked automatically. The scenarios are simulated; the testing is real. The phrase dataset is the exception: hand-built from real patient language and measured by hand.

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Start Here — PatientWords — `start-here/index.html`

> ⚑ meta description: A plain-language introduction: doctors interpret many ways of saying the same thing; a language model can answer each one differently. What we trace and measure.

<!-- id: start-here.b001 -->
Start here · the whole idea in five minutes

<!-- id: start-here.b002 -->
## People say the same thing many ways. What does a machine "hear"?

<!-- id: start-here.b003 -->
What happens inside a language model when the same medical question is asked in patient words instead of clinical words.

<!-- id: start-here.b004 -->
1 · A doctor converges

<!-- id: start-here.b005 -->
## Three phrasings, one interpretation

<!-- id: start-here.b006 -->
Patients rarely use words that appear in medical textbooks. A clinician understands multiple different framings, recognizes the same stomach problem, and reaches the same recommendation.

<!-- id: start-here.b007 -->
interpretation absorbs the wording

<!-- id: start-here.b008 -->
2 · The model diverges

<!-- id: start-here.b009 -->
## Same three phrasings, three different answers

<!-- id: start-here.b010 -->
We gave a language model the same sentences and read off its most likely next word. Under the clinical phrasing, the top next word is the medical answer. Under the casual framings, it is a food word, even in the one that uses the clinical term.

<!-- id: start-here.b011 -->
the wording chooses the answer — measured on gemma-2-2b · see the traces: stomach’s on fire · dyspepsia ladder

<!-- id: start-here.b012 -->
3 · Try it

<!-- id: start-here.b013 -->
## Watch one word change the answer

<!-- id: start-here.b014 -->
A language model works by guessing the next word. Flip the phrasing and watch its guesses reshuffle.

<!-- id: start-here.b015 -->
“When the dust kicks up my asthma flares, so at work I keep a spare ___”

<!-- id: start-here.b016 -->
real measurements: open scenario 85’s full trace · browse all scenarios

<!-- id: start-here.b017 -->
4 · What we measure

<!-- id: start-here.b018 -->
## Two numbers per sentence pair

<!-- id: start-here.b019 -->
How far the right answer's probability falls when the wording turns casual, and whether the top answer changes. When it changes to a word lower on the care ladder, like "inhaler" becoming "shirt" in step 3, we count a downgrade.

<!-- id: start-here.b020 -->
5 · Look inside

<!-- id: start-here.b021 -->
## Circuit tracing photographs the reasoning

<!-- id: start-here.b022 -->
A trace is not a later stage: it is a look inside the guess you watched in step 3. Inside the model, small units called "features" switch on as it reads. Some respond to medical ideas; others to everyday ones. A circuit trace records which features fired and how strongly each fed the predicted next word. Clinical wording lights the medical features; patient wording lights the everyday ones. A person chatting with a model never sees any of this: the trace is a diagnostic that researchers compute from the model's internals after it answers.

<!-- id: start-here.b023 -->
larger node = stronger influence · faint = barely fired · the real traces of the matching acid-reflux pair fire 732 and 787 features and share 465; the sketch draws the strongest few

<!-- id: start-here.b024 -->
Most figures elsewhere on PatientWords are real circuit traces like this sketch.

<!-- id: start-here.b025 -->
6 · The patch

<!-- id: start-here.b026 -->
## A translation layer, for now

<!-- id: start-here.b027 -->
Put a translator between the patient and the model: it rewrites the sentence into clinical wording before the model answers.

<!-- id: start-here.b028 -->
A patch, not a permanent solution: translation fixed 8 of the 20 hardest cases, left 7 unchanged, and three times made things worse. See the live translation traces.

<!-- id: start-here.b029 -->
7 · The lasting fix

<!-- id: start-here.b030 -->
## Measure, mend, maintain: a cycle, not a patch

<!-- id: start-here.b031 -->
No single fix closes this gap. Language evolves; dialects, slang, and communities change, and a test built once goes stale. The method has to be a loop: measure, mend, maintain, repeat.

<!-- id: start-here.b032 -->
### Measure

<!-- id: start-here.b033 -->
- Pair each clinical phrasing with its patient phrasing. Count how often the answer drops in urgency.

<!-- id: start-here.b034 -->
- nowsimulated phrases, pre-registered, a tenth sealed for checking.

<!-- id: start-here.b035 -->
- nextreal patient language, clinician-checked, community-validated dialects.

<!-- id: start-here.b036 -->
### Mend

<!-- id: start-here.b037 -->
- Fortify the model: put a line of medical context in front of the question. One sentence of explicit medical context roughly halves the penalty measured under casual framing.

<!-- id: start-here.b038 -->
- Train on patient language: include the way people actually speak in the training data. Models learn idioms, misspellings, and dialects the way clinicians do.

<!-- id: start-here.b039 -->
- Translate only behind a regression check: re-test every rewrite, because rewrites can lose clinical content.

<!-- id: start-here.b040 -->
### Maintain

<!-- id: start-here.b041 -->
- Re-run the audit on a schedule.

<!-- id: start-here.b042 -->
- Refresh the phrase sets and urgency tiers with clinician and community review.

<!-- id: start-here.b043 -->
- Stress-test the edges with supplementary sets. A small emergency-scenario set (7 pairs) is generated and being measured; further emergency rounds are paused. Kept outside the pre-registered run.

<!-- id: start-here.b044 -->
- nextMore edge sets: alarm-sounding wording, misspellings.

<!-- id: start-here.b045 -->
- Watch the circuit for drift as models update.

<!-- id: start-here.b046 -->
### Two kinds of loss, two kinds of fix

<!-- id: start-here.b047 -->
A layer-by-layer readout shows where the answer is lost: some answers form and drop out at the last step, some never form at all. The running census, pair by pair, lives on the Technical page; the methods page shows the causal check.

<!-- id: start-here.b048 -->
SIMULATED DATA: the sentence pairs measured across this site are written by an LLM and checked automatically. The scenarios are simulated; the testing is real. The phrase dataset is the exception: hand-built from real patient language and measured by hand.

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Methods — PatientWords — `methods.html`

> ⚑ meta description: How PatientWords works: gemma-2-2b with Gemma Scope transcoders, circuit-tracer attribution graphs via Neuronpedia, feature tagging, and the comparison engines.

<!-- id: methods.b001 -->
Methods · how the pipeline works

<!-- id: methods.b002 -->
## From a sentence to a circuit, in six steps.

<!-- id: methods.b003 -->
Every figure starts as two (or four) plain sentences, one in clinician wording and one in patient wording, and ends as an interactive map of the computation gemma-2-2b performs on it.

<!-- id: methods.b004 -->
Step 1 · Model & features

<!-- id: methods.b005 -->
## A prism splits the model’s activity into readable features

<!-- id: methods.b006 -->
The study’s subject is gemma-2-2b, a small open language model (Google DeepMind, released July 2024). Watched directly, its inner workings are millions of undifferentiated numbers: white light. Google DeepMind’s Gemma Scope transcoders act as a prism. They split that light into distinct, readable colors called features. Each feature fires for one recognizable thing: mental-health treatment, first-person symptom talk, the grammar of a quoted sentence. Once the light is split, we can see which parts of the model’s thinking a sentence switches on.

<!-- id: methods.b007 -->
Step 2 · Attribution

<!-- id: methods.b008 -->
## Tracing which features pushed the model to its next word

<!-- id: methods.b009 -->
For each sentence we run circuit-tracer through Neuronpedia to build an attribution graph: a map of which features, at which depth and position in the sentence, pushed the model toward its next word. Each connection carries a weight: the influence one feature’s firing had on another’s, and on the word the model chose. The technical term for that weight is attribution mass.

<!-- id: methods.b010 -->
The instrument repeats itself, within the record we have. — phrase pairs were traced two or more times on different days: the pairs that happened to be re-traced, not a designed sample. At the precision the files record (three decimals), every repeat reproduced identical probabilities (largest spread —), identical top-five lists (— pairs), and, under the same graph settings, identical clinical-mass shares. The top word never changed (— pairs). Different graph settings do change the feature-level numbers; that is parameter sensitivity, not noise. Zero repeat variation was observed through July 14, 2026. On July 15 the daily sentinel recorded its first movement: probabilities shifted by at most 0.027 across the three sentinel pairs, and every top word held (sentinel series). Source: the repeatability measurements file on GitHub.

<!-- id: methods.b011 -->
Step 3 · Tagging

<!-- id: methods.b012 -->
## Every feature gets sorted: clinical, off-target, or structural

<!-- id: methods.b013 -->
Each feature is tagged by what it responds to, read from its machine-written description and from the kinds of text that make it fire:

<!-- id: methods.b014 -->
- Clinical: features in the medical computation we want: depression, therapy, diagnosis, treatment.

<!-- id: methods.b015 -->
- Off-target: features dragged in by colloquial wording: idiom, mood-as-weather metaphors, the music sense of “the blues.” These are the mechanism of the language penalty.

<!-- id: methods.b016 -->
- Structural: scaffolding features for syntax, position, and punctuation that appear in every trace and carry no medical content.

<!-- id: methods.b017 -->
The three-way split makes two graphs comparable: when the wording turns colloquial, the clinical share of the circuit falls and the off-target share rises.

<!-- id: methods.b018 -->
Step 4 · Comparison

<!-- id: methods.b019 -->
## Four views put the two phrasings side by side

<!-- id: methods.b020 -->
The tagged graphs feed four comparison views:

<!-- id: methods.b021 -->
- Wording: the word swap 2panel · Fig. 1 Two stacked traces of the same sentence, differing only in “depression” vs. “the blues.”

<!-- id: methods.b022 -->
- Wording: the grammar swap 4quadrant · Fig. 2 A 2×2 grid crossing the medical keyword with the surrounding frame, separating the vocabulary effect from the grammar effect.

<!-- id: methods.b023 -->
- Dialect Differences dialect · Fig. 3 The clinical term is held fixed while the surrounding syntax is re-traced across dialect and register variants.

<!-- id: methods.b024 -->
- Translation translation · Fig. 4 An LLM rewrites the patient sentence in clinical terms, and the rewrite is traced to show the circuit and prediction recover together.

<!-- id: methods.b025 -->
Every render is a single self-contained HTML file.

<!-- id: methods.b026 -->
Whatever the view, each comparison ends one of three ways. The model hedges: the clinical answer stays on top but loses probability. It redirects: the top answer changes. Or it downgrades: the redirect lands on a lower tier of care. A worked case: “Grandma’s been constipated for a week, so before dinner she took a” continues with laxative. Rephrase it as “all bunged up” and the top word becomes nap (30%, against the laxative’s 26% under clinical wording). The predicted word changed, not just its probability. Tiers follow the owner-reviewed v1 vocabulary (domain review pending), listed below with measured example words.

<!-- id: methods.b027 -->
*fold:* The five care tiers, with measured example words at each rung.

<!-- id: methods.b028 -->
care-urgency tiers, owner-reviewed v1 · domain review pending · predicted words with no urgency information are excluded · a redirect that lands on a lower tier is a downgrade

<!-- id: methods.b029 -->
## Reading the layers

<!-- id: methods.b030 -->
The circuit view names which features fire. The Jacobian lens reads what the model would say if forced to answer at each of its 26 layers: ranked words, one list per layer. Two questions per pair: where does the clinical answer become readable, and does it survive to the output.

<!-- id: methods.b031 -->
The pair below asks for a word after “so I might need to take a”. Under the clinical wording the answer is readable from layer 10 and reaches first place by layer 19. Under the everyday wording it appears 9 layers later, never rises past second place, and is gone at the output, where “take a break” wins. The causal check: copy the clinical run’s internal state into the everyday run one layer at a time and re-measure. The early layers return nothing; the deep layers return most of the probability. Those layers carry the difference.

<!-- id: methods.b032 -->
One downgrade-set pair, one layer axis. Top lanes: the lens readout; darker cells rank the clinical answer higher in that layer’s top 8; a faint dot means not readable. Bottom lane: the answer’s probability when the everyday run is patched with the clinical state at that single layer, best position per layer, against the two measured levels.

<!-- id: methods.b033 -->
Layer readouts use the Jacobian lens (Gurnee et al., Transformer Circuits, 2026), applied through Neuronpedia’s hosted deployment of the authors’ reference implementation (anthropics/jacobian-lens, Apache-2.0). The lens is a readout, not an intervention; causal evidence comes from the activation-patching check above and the steering experiments. The readout is exploratory and reported for one model.

<!-- id: methods.b034 -->
Step 5 · Generation & its audit

<!-- id: methods.b035 -->
## One set of AIs writes the test; a different set takes it

<!-- id: methods.b036 -->
The pipeline keeps a strict separation of church and state. Anthropic’s Claude models do exactly two jobs. They write the test questions (the phrase pairs; each batch’s record names the exact model, for the main run currently claude-haiku-4-5, Anthropic, released October 2025) and they translate patient wording into clinical wording for the Translation figure. A different set of models takes the test: the open-weights gemma, qwen, llama, and olmo families on every other page. The test-writers never take the test, and the test-takers never write their own questions.

<!-- id: methods.b037 -->
Because the test-writer is itself an AI, it gets audited. The audit asks a Claude model to pull the clinical concepts out of a sentence twice: once from the patient’s own words, once after translating those words into clinical language. The finding is plain: the models read patient wording perfectly, but translating patient words into clinical words destroys information. The losses appear at the translation step, not before it.

<!-- id: methods.b038 -->
*fold:* The audit numbers, model by model: extraction accuracy from the patient’s own words versus after translation, with each run’s cost.

<!-- id: methods.b039 -->
orange slope = clinical content lost in translation · grey = no loss

<!-- id: methods.b040 -->
That is the same regression the engine flags automatically, and the reason the Translation fix can’t be assumed safe without checking its output. The item set is small; read the percentages as the direction of the effect, not a ranking of models.

<!-- id: methods.b041 -->
## What translation fixes

<!-- id: methods.b042 -->
The depth readout splits the penalty into two failure kinds. When the answer never forms, translation supplies the clinical wording up front. When the answer forms and is lost, translation recovers work the model already did. The running census, set by set, lives on the Technical page.

<!-- id: methods.b043 -->
The loop for a deployed system: read the layers to see which kind dominates, mend with translation, verify with patching, re-measure as language drifts.

<!-- id: methods.b044 -->
Step 6 · Accumulation

<!-- id: methods.b045 -->
## Confidence grows as the data accumulates

<!-- id: methods.b046 -->
Each model's average language penalty starts uncertain and narrows as hundreds of phrase pairs accumulate. One honesty rule: a random tenth of new phrases is locked away untouched, and since July 14 also withheld from this site's data files, so conclusions can be checked once, at the end, against data no interim analysis has seen. The accumulation figure, one panel per model with its data table, moved to the cross-model section of the Technical page (2026-07-14, owner decision); the interim cross-model statistics live there too.

<!-- id: methods.b047 -->
Limitations

<!-- id: methods.b048 -->
## What this evidence does and does not show

<!-- id: methods.b049 -->
This project measures one narrow thing: how the probability of a single next word changes when clinical wording is replaced by patient wording. That is a probe of model behavior, not a clinical outcome. A lower probability for “antacid” isn’t a measure of harm; it’s a sign the model treats the two phrasings differently.

<!-- id: methods.b050 -->
- One small model carries the circuit evidence. Every graph here comes from gemma-2-2b, chosen because its transcoders are public. The behavioral checks on the other seven models measure next-word probabilities only, no circuits. None of this shows how larger systems behave. The one medically tuned model measured, medgemma-4b-it (4B parameters, next-word behavior only), still shows a below-zero penalty: −3.4 pp, 95% CI [−6.9, −0.2], on 119 phrases. That reading is exploratory; the model is a post-registration addition, and its interval crosses zero under the stricter simultaneous correction.

<!-- id: methods.b051 -->
- Attribution graphs are an interpretive tool. They reconstruct the model’s computation through features and prune heavily; error nodes absorb what’s missed.

<!-- id: methods.b052 -->
- Feature labels are machine-generated. The clinical / off-target categories come from keyword-matching auto-interp descriptions. Both steps can be wrong, and a mislabeled feature shifts the clinical-mass numbers.

<!-- id: methods.b053 -->
- Measurements are a point in time. The probabilities were observed on specific dates against a hosted service. The 52 pairs re-traced so far reproduce exactly at the recorded three-decimal precision (see step 2), but that is the set that happened to be repeated, not a guarantee. Future drift would come from service changes; a daily three-pair sentinel re-trace watches for that.

<!-- id: methods.b054 -->
- Translation can fail. The fix in the Translation figure is itself an LLM step. The engine flags regressions — cases where the rewrite made the target word less likely.

<!-- id: methods.b055 -->
- The stimuli are constructed. Most phrase pairs were written by a language model and checked automatically, not collected from patients. They are stress tests, not a sample of real clinical conversations.

<!-- id: methods.b056 -->
Nothing here is medical advice, and no part of this pipeline is a deployed clinical tool. The claim is narrower: on the models measured, the same situation phrased in patient words is measurably less likely to reach the clinical answer than in clinical terms — and the circuit view shows where that difference arises.

<!-- id: methods.b057 -->
Two kinds of provenance appear in the gallery. Figs. 1–4 and the simulated scenarios use prompts written by an LLM and checked automatically: the scenarios are simulated, but the testing is real. The phrase dataset is the other kind: hand-built from real patient language and measured by hand.

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Technical · PatientWords: watching answers form, layer by layer — `technical/index.html`

> ⚑ meta description: The Jacobian lens in plain language, what it lets us ask about how a language model fails on patient phrasing, and a data dive: formation depth, capture versus hijack, and where each repair applies.

<!-- id: technical.b001 -->
Technical · the Jacobian lens · exploratory depth analytics

<!-- id: technical.b002 -->
## Watching an answer form, layer by layer.

<!-- id: technical.b003 -->
A new instrument reads the model's forming answer at every depth. This page explains it, shows what it lets us ask, and opens the first data.

<!-- id: technical.b004 -->
Part 1 · The instrument, in plain language

<!-- id: technical.b005 -->
## A film strip of the model making up its mind

<!-- id: technical.b006 -->
A language model reads a sentence in layers, a few dozen stacked processing steps. The final layer produces the answer everyone sees. The Jacobian lens reads the layers in between: at each one, it asks "if the model had to answer right now, what would it say?" The result is a film strip of the answer forming. An answer can appear early and hold, appear and be pushed out, or never appear at all.

<!-- id: technical.b007 -->
The lens does not change the model. Like a circuit trace, it is a diagnostic that researchers compute; a person chatting with the model never sees it. Where a circuit trace shows which internal features fired, the lens shows when in depth the answer existed. The two instruments answer different questions about the same failure.

<!-- id: technical.b008 -->
Part 2 · What it lets us ask

<!-- id: technical.b009 -->
## Not just whether it fails. How.

<!-- id: technical.b010 -->
The rest of this site measures the end: the final answer and its probability. The lens opens the middle. Three questions become askable.

<!-- id: technical.b011 -->
### Did the right answer ever exist inside the model?

<!-- id: technical.b012 -->
If patient wording merely weakens the answer, it should still form at some depth. If the wording redirects the computation entirely, the answer should never appear. These are different failures with different repairs.

<!-- id: technical.b013 -->
### When the model gets it wrong, was the answer captured or hijacked?

<!-- id: technical.b014 -->
Two failure shapes: in a capture, the everyday reading owns the trajectory from the start and the clinical answer never enters the window. In a hijack, the clinical answer forms at depth and is pushed out near the end. Two counting rules, adopted July 14: the split is only scored on pairs whose clinical side is lens-readable (pairs where neither wording ever reads out are their own class), and formation requires two consecutive readable layers, so a one-layer blip does not count. Part 3 counts all of it.

<!-- id: technical.b015 -->
### Which repair applies where?

<!-- id: technical.b016 -->
Each tested fix acts at a depth. Translation supplies the clinical wording before the model starts, so it can act even when the answer never forms. Steering amplifies an existing circuit, so it should work best when something formed and was lost. The lens turns "try every fix" into "read the failure, pick the fix". The second amendment, adopted July 14, registers one directional test on batches generated after adoption: translation recovering more where the answer formed and was lost than where it never formed. The fourth amendment, adopted July 17, registers the steering-by-class test on post-adoption batches.

<!-- id: technical.b017 -->
Part 3 · Data dive

<!-- id: technical.b018 -->
## First readings, exploratory

<!-- id: technical.b019 -->
loading the lens readouts

<!-- id: technical.b020 -->
### Where answers form

<!-- id: technical.b021 -->
When the clinical answer forms at all, it forms late, and patient wording barely moves that depth. The difference between the wordings is not timing. It is existence.

<!-- id: technical.b022 -->
### Capture versus hijack

<!-- id: technical.b023 -->
### The census, set by set

<!-- id: technical.b024 -->
Every measured set, one row of squares per outcome class, one square per pair. New sets join as the nightly cycle measures them. The reviewed downgrade set holds the pairs whose predicted action fell to a lower tier of care.

<!-- id: technical.b025 -->
hover a square for its clinical target · the generated sets live in the scenario gallery; the reviewed downgrade set is separate

<!-- id: technical.b026 -->
*fold:* Every pair: depth class and care-urgency tiers regained by translation, where measured (owner-reviewed v1 tiers, domain review pending)

<!-- id: technical.b027 -->
*fold:* The switch, close up: six rule-selected pairs, sentence by sentence

<!-- id: technical.b028 -->
Selection rule: every lost-late pair, strongest clinical hold first, capped at four, plus the two never-formed pairs whose clinical wording holds best at the output. All sentences are generated stress-test stimuli.

<!-- id: technical.b029 -->
### Read the failure, pick the fix

<!-- id: technical.b030 -->
Translation recovery is already measurable by failure depth. The steering column fills when the per-pair steering verdicts are joined to the lens classes.

<!-- id: technical.b031 -->
care-urgency tiers regained per pair (owner-reviewed v1 tiers, domain review pending) · translation column from the joined translated panels · steering column queued: per-pair steering verdicts against the same lens classes

<!-- id: technical.b032 -->
### Does tuning move the depth?

<!-- id: technical.b033 -->
### Queued next

<!-- id: technical.b034 -->
- nextThe three translation arms through the lens: does real translation restore early formation while the placebo paraphrase leaves depth unchanged?

<!-- id: technical.b035 -->
- nextThe context prefix through the lens: does one sentence of clinical context make the answer form earlier, or only boost it late?

<!-- id: technical.b036 -->
- nextMisspelling stress set: does a real observed misspelling delay formation or prevent it?

<!-- id: technical.b037 -->
- nextA lens reading in the daily drift sentinel, watching the internals for service change, not just the outputs (fires daily since July 14; every day-over-day lens comparison so far reads out identical).

<!-- id: technical.b038 -->
- nextThe same depth profiles under the plain logit lens: a robustness arm for the formation story.

<!-- id: technical.b039 -->
Part 4 · Across models

<!-- id: technical.b040 -->
## Eight models, one measurement.

<!-- id: technical.b041 -->
The lens results above come from one model. The behavioral finding they explain generalizes: the same two-phrasing probe, run on eight measured open-weights models across four model families, with the probability of the clinical next word measured under both wordings. These are interim numbers from the exploration split. They use the plain generated scenario batches only; steered, screened, and re-traced rows sit in a labeled sensitivity analysis inside the statistics file. Phrase counts differ by model; the table lists each. Every count uses a phrase once per model. Four models were named in the pre-registration; the other four are later additions, marked exploratory below, and the asymmetry tests are corrected for multiple comparisons within each of those two groups. One tenth of newly collected phrases is sealed for the confirmatory endpoint and withheld from this site's data files. The models here are the measured subjects; the stimuli they read are written by Claude models and audited on the methods page.

<!-- id: technical.b042 -->
### The penalty, model by model

<!-- id: technical.b043 -->
Mean language penalty: the percentage points of next-word probability the clinical answer loses when the wording turns colloquial. The thick band is each model's own 95% interval; the hairline is the stricter simultaneous interval, sized for reading all eight at once.

<!-- id: technical.b044 -->
*fold:* How confidence accumulated: each model's estimate, batch by batch (moved from methods, formerly Fig. 5)

<!-- id: technical.b045 -->
Each panel follows one model as it reads more phrase pairs. The red line is the average language penalty; the band around it starts wide and narrows as hundreds of phrases accumulate. The four post-registration additions have read about 120 phrases so far, so their bands stay wider. Early points in any panel are unstable by construction; read where each band ends, not the path it took.

<!-- id: technical.b046 -->
Mean language penalty per model as measurement accumulates, batch by batch. Shaded band: bootstrap 95% confidence interval (seed 7, phrase-deduped, Tier B exploration split only). Grey hairline: zero penalty. Drawn at load time from the convergence data file on GitHub.

<!-- id: technical.b047 -->
*fold:* Data table (every point)

<!-- id: technical.b048 -->
### When the answer changes, it goes down the care ladder

<!-- id: technical.b049 -->
Among phrases where the top prediction changes under patient wording, downgrades outnumber upgrades on every model. Asterisks mark asymmetry that survives multiple-comparison correction within the model's registration family; hover a row for the exact value.

<!-- id: technical.b050 -->
filled red = downgrades · hollow = upgrades · * significant after correction (q < 0.05)

<!-- id: technical.b051 -->
*fold:* The interim table: every model with its maker, release month, registration, evidence kind, and exact statistics

<!-- id: technical.b052 -->
table scrolls sideways →

<!-- id: technical.b053 -->
Statistical methods

<!-- id: technical.b054 -->
- Population: plain generated scenario batches only; steered, screened, imported, and re-traced rows are reported as a labeled sensitivity analysis in the statistics file.

<!-- id: technical.b055 -->
- One record per (model, clinical phrase); re-traces collapse by majority vote.

<!-- id: technical.b056 -->
- Penalty intervals: phrase-level bootstrap after dedupe, percentile 95%, seed 7; the file also carries simultaneous (Bonferroni) intervals and batch- and topic-clustered sensitivity intervals.

<!-- id: technical.b057 -->
- Downgrade rates: Clopper–Pearson exact 95%.

<!-- id: technical.b058 -->
- Asymmetry: exact two-sided sign tests, Benjamini–Hochberg corrected within registration family; the merged eight-model correction stays in the file for comparison.

<!-- id: technical.b059 -->
- Registration: four models pre-registered, four post-registration exploratory; departures are recorded in the divergence log in the engine repository.

<!-- id: technical.b060 -->
- Confirmatory holdout: one tenth of Tier B phrases, withheld from this site's data files until the registered endpoint runs.

<!-- id: technical.b061 -->
- Circuit evidence: gemma-2-2b only; the rest behavioral, fixed open weights, a point in time.

<!-- id: technical.b062 -->
- Care-urgency tiers: owner-reviewed v1, domain review pending.

<!-- id: technical.b063 -->
- Source: the per-model statistics file on GitHub.

<!-- id: technical.b064 -->
*fold:* Where the penalty concentrates: per-specialty, exploratory

<!-- id: technical.b065 -->
table scrolls sideways →

<!-- id: technical.b066 -->
gemma-2-2b · exploratory: phrase-deduped, no correction for testing many specialties at once, cells under 10 phrases suppressed · grouping follows the draft specialty taxonomy (owner review pending) · hypothesis-generating only, not a pre-registered endpoint

<!-- id: technical.b067 -->
Method credit pending data load.

<!-- id: technical.b068 -->
Everything in the lens sections (Parts 1 to 3) is exploratory: the pairs are the ones with landed lens readouts, not a designed sample, and all of it predates the second amendment (adopted July 14), which pre-registers the confirmatory depth endpoints on batches generated after adoption. Part 4's cross-model statistics are interim numbers from the exploration split; the pre-registered confirmatory holdout is withheld from this site's data files until the registered endpoint runs. Ranks are within the lens's top-8 readout; "never formed" means never entered that readable window for two consecutive layers (one-layer blips do not count, rule adopted July 14).

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Simulated scenarios — PatientWords — `simulated-scenarios/index.html`

> ⚑ meta description: Claude-generated patient-vs-clinical stress scenarios, programmatically validated and traced live on gemma-2-2b, kept apart from the hand-measured dataset.

<!-- id: simulated-scenarios.b001 -->
Simulated series · generated stress pairs · live renders · simulated data

<!-- id: simulated-scenarios.b002 -->
## Simulated scenarios

<!-- id: simulated-scenarios.b003 -->
Stress scenarios authored by an LLM, validated, traced live on gemma-2-2b, and kept apart from the hand-measured set.

<!-- id: simulated-scenarios.b004 -->
*fold:* View generation methodology

<!-- id: simulated-scenarios.b005 -->
This section adds simulated scenarios to the hand-measured dataset. Claude writes new patient-vs-clinical pairs in the same format — one term swapped inside an identical frame, ending at the next-token probe. Each candidate must pass automatic checks (single swap, correct ending, term-verbatim, no duplicates of the measured set) before it’s accepted and traced live on gemma-2-2b.

<!-- id: simulated-scenarios.b006 -->
Each scenario shows the two phrasings, the traced probabilities with the language penalty, and the generator’s reason the swap should matter. The 25 largest-effect scenarios (prediction flips first, then largest penalty) include a full circuit comparison; every scenario’s measurements are downloadable below.

<!-- id: simulated-scenarios.b007 -->
In the table, the model hedges (top answer holds, loses probability) or redirects; the urgency column marks a redirect down the care ladder as a downgrade. Full definitions and the tier ladder: methods step 4.

<!-- id: simulated-scenarios.b008 -->
traced model: gemma-2-2b · gemma scope transcoders → prob = target-token probability read from the live trace · penalty = patient − clinical

<!-- id: simulated-scenarios.b009 -->
## Key example

<!-- id: simulated-scenarios.b010 -->
## When the advice itself changes

<!-- id: simulated-scenarios.b011 -->
Some redirects go further — the top answer lands on a different object altogether. These are the swaps to watch: the wording changes what’s offered. Tier labels follow the owner-reviewed v1 vocabulary (domain review pending).

<!-- id: simulated-scenarios.b012 -->
click a Sim number to jump to its full trace · glyph: ● clinical → ○ patient target probability on a shared 0–1 axis (dashed = patient below the traced spread) · * intended target fell below the traced spread; measurement anchored on the clinical top prediction · screened-out rows kept their clinical trace but failed the measurement screen (open a Sim page for details)

<!-- id: simulated-scenarios.b013 -->
*fold:* The key example, full size

<!-- id: simulated-scenarios.b014 -->
SIMULATED DATA · these phrasings were written by an LLM (see the strip above) and passed the generator's automatic validators; they are not statements from patients and contain no real personal or clinical data. The traces are live gemma-2-2b runs via the Neuronpedia circuit tracer.

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Wording differences — PatientWords — `wording-differences/index.html`

> ⚑ meta description: Two experiments on gemma-2-2b: swap a single word (clinical term vs. patient idiom), or hold the words and change only the grammar. Both move the next-word prediction.

<!-- id: wording-differences.b001 -->
Figs. 1–2 · one-word swap + grammar × lexicon · live renders · simulated scenarios

<!-- id: wording-differences.b002 -->
## Wording differences

<!-- id: wording-differences.b003 -->
Swap one word, or only the grammar around it; either moves the prediction.

<!-- id: wording-differences.b004 -->
## Swap the word · Fig. 1

<!-- id: wording-differences.b005 -->
A single phrase swapped — “asthma flares” vs. “chest gets all tight” — as two stacked traces. Clinical wording gives inhaler at 69%; the patient wording drops it to 4%, and the top guess becomes “shirt”.

<!-- id: wording-differences.b006 -->
live trace: gemma-2-2b · gemma scope transcoders hosted circuit-tracer via Neuronpedia · traced July 7, 2026 · scenario 85 of the simulated series · next-token probabilities read directly from the trace · “asthma flares” vs. “chest gets all tight”, target “ inhaler”

<!-- id: wording-differences.b007 -->
Live trace: clinical wording reaches “ inhaler” at 69%; the patient phrasing top word is “ shirt”, with inhaler at 4% (scenario 85). Two panels on one scale — clinical above, patient below: green clinical features stack over the swapped word and feed the continuation; the idiom replaces them and the probability falls.

<!-- id: wording-differences.b008 -->
## Swap the grammar · Fig. 2

<!-- id: wording-differences.b009 -->
A 2×2 crossing wording (medical vs. patient, columns) with grammar (standard vs. nonstandard, rows). The live-traced item is a simulated palpitations case ending “driving him to the __”. Changing only the grammar adds +10–13% to “hospital”; changing only the words removes 10–13%.

<!-- id: wording-differences.b010 -->
traced model: gemma-2-2b · gemma scope transcoders hosted circuit-tracer via Neuronpedia · traced July 15, 2026

<!-- id: wording-differences.b011 -->
rows show the grammar, columns show the phrasing. The traced item: A “My father says his heart has been experiencing palpitations again, so we are driving him to the __” · C the same frame with “fluttering and skipping” · B “My father say his heart been experiencing palpitations again, so we driving him to the __” · D the nonstandard frame with “fluttering and skipping”.

<!-- id: wording-differences.b012 -->
### The full matrix: all four cells at once

<!-- id: wording-differences.b013 -->
The matrix is scaled to fit the page; click any quadrant to expand it full screen. Each box traces one cell’s prompt.

<!-- id: wording-differences.b014 -->
*fold:* More views: one swap at a time

<!-- id: wording-differences.b015 -->
### The four edges, one swap at a time

<!-- id: wording-differences.b016 -->
Each comparison isolates ONE cell swap. Features in both cells are dimmed to gray, so what stays at full ink is exactly what that swap changed.

<!-- id: wording-differences.b017 -->
Register shift, standard row · A → C (“experiencing palpitations” → “fluttering and skipping”) · Δ −10% on “hospital”

<!-- id: wording-differences.b018 -->
Register shift, nonstandard row · B → D · Δ −13%

<!-- id: wording-differences.b019 -->
Variety shift, medical column · A → B (“says … has been … we are” → “say … been … we”) · Δ +13%

<!-- id: wording-differences.b020 -->
Variety shift, patient column · C → D · Δ +10%

<!-- id: wording-differences.b021 -->
SIMULATED DATA · the phrasings here (scenario 85 and the four palpitations cells) were written by an LLM and passed the engine's automatic validators; they are not patient statements and contain no real personal or clinical data. The trace itself is a live gemma-2-2b run via the Neuronpedia circuit tracer.

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Dialect differences — PatientWords — `dialect-differences/index.html`

> ⚑ meta description: Clinical terms held fixed while each sentence is re-traced across dialect and register framings in gemma-2-2b; a minority of framings move the model's top prediction.

<!-- id: dialect-differences.b001 -->
Fig. 3 · dialect & register sweep · live render · traced July 16 and 17, 2026

<!-- id: dialect-differences.b002 -->
## Dialect differences

<!-- id: dialect-differences.b003 -->
The clinical term held fixed while the surrounding sentence shifts across eight LLM-approximated dialect and register framings per term.

<!-- id: dialect-differences.b004 -->
The clinical term stays fixed while the sentence around it is re-traced across dialect and register variants, so any shift comes from framing. The framings are Claude-written approximations: each column label is the instruction given to the generating model, not a recording of how any community speaks, and no speaker of any variety reviewed them. The sweep below holds a set of clinical terms fixed, one per row, and re-traces each across several framings; the matrix reports the exact counts. A minority of framings move the top word.

<!-- id: dialect-differences.b005 -->
model: gemma-2-2b · features: Gemma Scope transcoders (16k) · graphs: 180 (20 baselines + 160 framings) held fixed: clinical terms from the hand-measured dataset · framings: dialect + register variants per term framings authored by claude-sonnet-5 ($0.413, 160 accepted / 5 rejected) · traced via Neuronpedia

<!-- id: dialect-differences.b006 -->
Change in p(target), by term and framing

<!-- id: dialect-differences.b007 -->
Each cell is one traced sentence (n=1): the change in p(target) when that framing replaces standard English. Column labels are the instructions given to the generating LLM, not community samples. A red ● marks a framing that also flips the model’s top prediction away from the baseline target; hover a cell for the new top prediction. Rows whose target is a function word (“my”, “the”) are tagged and their flips sit outside the headline count. Click any row to open that term’s standalone render.

<!-- id: dialect-differences.b008 -->
Featured term

<!-- id: dialect-differences.b009 -->
Bars share a fixed 0–100% probability scale; the thin ink tick marks the standard-English baseline. Rows sorted by p, baseline first.

<!-- id: dialect-differences.b010 -->
*fold:* View the dialect-invariant clinical features

<!-- id: dialect-differences.b011 -->
The featured term’s strongest baseline clinical features, ranked by normalized attribution mass. “Survives” counts the framings whose trace still contains the feature; features surviving every framing are the dialect-invariant core. Computed from the committed renders, no re-tracing.

<!-- id: dialect-differences.b012 -->
*fold:* View the full framing trace (all panels)

<!-- id: dialect-differences.b013 -->
How to read it: the standard-English baseline first, then one panel per framing. Columns are the prompt’s words; height is model depth; the predicted next word sits at the top. The clinical term appears in every panel while the sentence around it changes, so differences in the stacks above it are the framing effect.

<!-- id: dialect-differences.b014 -->
*fold:* The register ladder: one clinical term held fixed while the sentence slides from formal to casual

<!-- id: dialect-differences.b015 -->
live trace (dose-response ladder): gemma-2-2b · gemma scope transcoders hosted circuit-tracer via Neuronpedia · traced July 8, 2026 · “dyspepsia” held verbatim across five register rungs · next-token probabilities read directly from the trace

<!-- id: dialect-differences.b016 -->
Live trace: a baseline plus five rungs from formal clinical wording to casual speech, the clinical term unchanged throughout. The top word is “ antacid” at 32% (rung 1) and 11% (rung 2), then “ apple” from the mixed rung on.

<!-- id: dialect-differences.b017 -->
Wording style alone moves the target less than swapping the term. In the ladder above, “dyspepsia” is held fixed while the sentence slides from clinical to casual, and the top word degrades from antacid (32%, then 11%) to apple. But across ten baselines traced the same way, the mean target probability stays flat across the rungs (27%–34%).

<!-- id: dialect-differences.b018 -->
The graphs above are live gemma-2-2b traces. The dialect framings were written by an LLM to hold the clinical term fixed while changing the surrounding words. Treat them as probes: an LLM’s version of a dialect is an approximation and may miss how a community actually speaks.

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Translation — PatientWords — `translation/index.html`

> ⚑ meta description: An LLM translates the patient sentence into standard terminology and the raw output is traced natively. On the reviewed hardest set, translation restores the clinical continuation in 8 of 20 cases; a placebo paraphrase recovers a quarter of the probability. Live gemma-2-2b traces.

<!-- id: translation.b001 -->
Fig. 4 · translation recovery · live trace · traced July 7, 2026 · re-traced July 9, 2026

<!-- id: translation.b002 -->
## Translation

<!-- id: translation.b003 -->
Translating the patient sentence back into clinical terms restores the prediction in 8 of the 20 hardest cases.

<!-- id: translation.b004 -->
The mitigation: an LLM rewrites the patient sentence in standard terms, and that rewrite is traced directly. In the cases translation fixes, the clinical features reappear and the target probability recovers; in 7 of the 20 it changes nothing, and 3 rewrites made the prediction worse.

<!-- id: translation.b005 -->
Translation matters most when it changes the predicted next word, not just its probability. In the reviewed downgrade set, “Grandma’s been all bunged up for a week, so before dinner she took a” continues with nap (30%); rewritten in clinical terms, the top word becomes lax(ative), above the original clinical phrasing (26%): 45% in the July 7 study trace, 41% on the July 9 re-trace shown below. It is not a cure-all: in one case the rewrite replaced the prescription (38%) with topical (15%).

<!-- id: translation.b006 -->
## Where the patch holds, and where it does not

<!-- id: translation.b007 -->
every classifiable case from the live mitigation trace · top token per panel

<!-- id: translation.b008 -->
The control that makes the case: on 14 pairs measured under both arms, the real clinical rewrite recovered a mean +1.9 points of target probability against +0.5 for a placebo paraphrase that keeps the casual register. The terminology does the work, not the rewriting.

<!-- id: translation.b009 -->
## At scale

<!-- id: translation.b010 -->
## What the depth readout adds

<!-- id: translation.b011 -->
A layer-by-layer readout splits the penalty into two failure kinds: answers that form and are lost late, which translation recovers, and answers that never form, which translation supplies. The running numbers, class by class, live in the data section of the Technical page.

<!-- id: translation.b012 -->
*fold:* View the live three-panel trace (clinical / patient / translated)

<!-- id: translation.b013 -->
live trace: gemma-2-2b · gemma scope transcoders hosted circuit-tracer via Neuronpedia · re-traced July 9, 2026 · phrase 17 of the reviewed downgrade set (predictions that fell to a lower care tier), three panels (clinical / patient / LLM-translated)

<!-- id: translation.b014 -->
Live trace: under patient wording the top word is “ nap” (30%); after rewriting to clinical wording it’s “ lax(ative)” (41%) — above the original clinical phrasing (26%).

<!-- id: translation.b015 -->
*fold:* Causal faithfulness & titration metrics (gemma-2-2b)

<!-- id: translation.b016 -->
### Dose–response: recovery by steering strength

<!-- id: translation.b017 -->
Boost the top-5 clinical features while the model reads the patient wording; recovery = the clinical target appears in the steered output. Recovery holds near ceiling from strength 2.5 through 10 (4/5, 5/5, 4/5) and falls off at 20, where the output sometimes breaks down.

<!-- id: translation.b018 -->
### Faithfulness: does attribution rank predict effect?

<!-- id: translation.b019 -->
same strength, different features: top-5 by attribution mass vs ranks 6–10. Control: 5 random features at strength 10 recovered 0/5 — the effect is the clinical circuit, not steering itself.

<!-- id: translation.b020 -->
The traces here are live gemma-2-2b runs.

<!-- id: translation.b021 -->
SIMULATED DATA: the sentence pairs measured across this site are written by an LLM and checked automatically. The scenarios are simulated; the testing is real. The phrase dataset is the exception: hand-built from real patient language and measured by hand.

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*

# Phrase dataset — PatientWords — `phrase-dataset/index.html`

> ⚑ meta description: The hand-built, hand-measured clinical/patient sentence pairs: observed next tokens, probabilities, and links to their Neuronpedia circuit traces.

<!-- id: phrase-dataset.b001 -->
Hand-measured · the study's ground truth (will be updated with patient language)

<!-- id: phrase-dataset.b002 -->
## Phrase dataset

<!-- id: phrase-dataset.b003 -->
Every hand-built sentence pair.

<!-- id: phrase-dataset.b004 -->
Each pair was built by hand and measured on gemma-2-2b via the Neuronpedia circuit tracer; the table records the observed next token, its probability, and, where captured, a link to the live trace. The simulated scenarios extend this set by machine.

<!-- id: phrase-dataset.b005 -->
The starkest case in the set illustrates a change in the recommended clinical advice. “Since her urinary tract was completely blocked up, they had to urgently call a” continues with uro(logist) at 20%; phrase it as “her water was completely blocked up” and the model calls a plumber — at 68%. The patient language changed what was recommended. (Pair 16 below.)

<!-- id: phrase-dataset.b006 -->
## All pairs

<!-- id: phrase-dataset.b007 -->
measured on: gemma-2-2b · gemma scope transcoders → observed next token · p = observed next-token probability · via the neuronpedia circuit tracer

<!-- id: phrase-dataset.b008 -->
Next-token probabilities as observed at measurement time.

<!-- id: phrase-dataset.b009 -->
prompts shown verbatim, including intentional misspellings

*Not extracted: text this page's JS generates at runtime from data files (tables, counts, chart labels).*
