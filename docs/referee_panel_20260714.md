# Referee panel synthesis, 2026-07-14

**Provenance.** Five adversarial referee personas (clinical informaticist, mech-interp
researcher, methods/reproducibility referee, sociolinguist, statistician) reviewed the
published site and engine artifacts on 2026-07-14, on the owner's instruction. Every
MAJOR premise was independently fact-checked against the repos
(`ops/referee/report_*.json`, `ops/referee/verdicts_*.json`): of 25 MAJOR findings,
15 were CONFIRMED, 10 PARTLY confirmed, 0 WRONG. Context from the same day's
independent replication (`ops/replication/comparison_20260714.md`): the published
per-model statistics reproduce (6 of 8 models exact, 2 explained by documented
population choices, 0 divergent; 120/120 raw-layer spot checks matched). The pipeline's
arithmetic is sound. Everything below is about design and presentation.

## Executive summary

The numbers are right and reproducible; the claims wrapped around them are not yet
earned. Three findings would each draw a reject at review: interim, sequentially
inspected statistics branded "claim-grade" with post-registration models rendered
indistinguishably from the pre-registered four; a "sealed" holdout whose per-pair
outcomes are published nightly and which cannot deliver its registered precision; and a
front door that converts a next-token probe on undeployed base models into "advice" and
"recommendation" claims the methods page itself disclaims. The instrument-grade
problems (urgency vocabulary, feature tagger, lens window, dialect labels) are all
fixable with scoped work. Nothing found requires retracting a number; nearly everything
requires rescoping a sentence.

## MAJOR findings

### Confirmed

**1. Claim-grade branding on interim, sequentially inspected numbers, with
post-registration models pooled in.** (clinical, methods, statistician) The prereg
fixed four primary models; the divergence log labels llama-3.2-3b, olmo-2-1b,
gemma-2-2b-it, and medgemma-4b-it "secondary/exploratory". The site's Part 4 table
renders all eight identically, the endnote calls them "the claim-grade interim
numbers", and the word "divergence" appears on no site page. The numbers are
recomputed nightly with no alpha-spending, batch size was doubled mid-collection in
view of results ("go 100"), and the convergence fold commits the sequential-testing
error explicitly: "by 155 it could not [be chance]" declares significance at a
data-chosen look (uncorrected sign p about 0.0007 across 21 plotted looks) while the
penalty CI at that very look still crossed zero ([-6.6, +0.5] pp). "Settled below
zero" is also wrong for the four added models: their n is frozen at 119-122 across all
14 plotted points; one estimate is re-plotted under a fold titled "How confidence
accumulated". **Fix:** reserve "claim-grade" for the sealed holdout analysis; relabel
Part 4 "interim, exploration split"; tag the four additions "exploratory, added
post-registration" and link the divergence log; rewrite the 36/155 sentence
descriptively; say "measured once at about 120 phrases" for the frozen models.

**2. "Every band sits below zero" is a joint claim over eight marginal, non-independent
95% CIs, corrected nowhere, resting on a post-hoc BH family.** (statistician) Only the
sign tests are multiplicity-adjusted; the headline penalty claim is simultaneous over
eight marginal intervals. The weakest, medgemma-4b-it, ends 0.2 pp below zero; any
simultaneity adjustment pushes it across. The dumbbell prose asserts direction "on
every model" when two of eight asymmetries fail the correction (gemma-2-2b-it q=0.289,
medgemma q=0.075). The BH family itself is data-dependent: registered when the family
was four models, published over all eight, and the rigor script's docstring still
describes four tests. **Fix:** publish simultaneous intervals behind any every-model
sentence and soften it if medgemma fails; run BH over the pre-registered four as the
confirmatory family with the additions in a separate exploratory block; update the
docstring.

**3. The medgemma claim is the rhetorically strongest sentence on the methods page and
rests on the weakest evidence.** (clinical, methods, statistician) methods.html states
flatly that the one medically tuned model "still shows a below-zero penalty". The
verified numbers: an exploratory 07-13 probe outside the prereg, n=119, point estimate
-3.4 pp, CI95 [-6.8, -0.2] pp with the upper bound 0.2 pp from zero, downgrade
asymmetry non-significant after correction (q=0.075). The claim could flip on a shift
of a quarter of its CI width. This is the row every clinical reader checks first.
**Fix:** rewrite with qualifiers (point estimate, interval nearly touching zero, n,
exploratory status) or hold it for the sealed-holdout analysis.

**4. The sealed holdout cannot deliver its registered precision, and its per-pair
outcomes are published nightly.** (statistician; corroborated by the replication) Two
verified problems. Power: the prereg's own calculation needs about 1,000 usable pairs
for plus-or-minus 2 pp on the downgrade rate; the 10% holdout yields roughly 160 pairs
at full target (worse at current accrual, 600 accepted), giving a Clopper-Pearson
half-width near plus-or-minus 9 pp, and Amendment 1 never states holdout-only versus
pooled analysis. Sealing: `urgency_shift.py --publish` writes holdout rows to the
public site and `export_frontend_simulated.py` has no `tierb_split` handling; the
checker counted 193 holdout rows in public `urgency_shift.json` and 47 holdout
scenarios with full measurements in `simulated_scenarios.json`, against site copy
reading "sealed in advance and never touched". The replication adds a second leak: 5
sealed-holdout phrases re-enter the published statistics through split-less re-run
batches because the exclusion is row-tag-keyed, not phrase-keyed (zero effect at
reported precision today, a latent hole as re-runs accumulate). **Fix:** amend the
analysis plan now (confirmatory dataset, reconciliation rule, honest 8-10 pp
precision); withhold holdout rows from published payloads or change the site language
to "excluded from published aggregates; individual measurements are public"; make the
holdout exclusion phrase-keyed.

**5. The stimulus generator was selected partly for penalty magnitude, and the
registered guard was never executed.** (methods) The prereg records that haiku was
chosen over opus on validator yield (76% v 60%), screen-in rate (55% v 48%), and
"penalty magnitude on screened-in pairs": the test-writer was selected on the
dependent variable, and Tier B haiku pairs now dominate every displayed estimate
(about 680 v 132 Tier A phrases on gemma-2-2b). The prereg's own remedy, generator as
a fixed effect in pooled models, appears nowhere in `model_stats.json` or either stats
script; no site page discloses the selection criterion. **Fix:** publish the
generator-stratified analysis (Tier A v Tier B mean penalty per model) next to the
forest plot; disclose the selection criterion in methods and limitations; add the
hand-built set's penalty as a benchmark row.

**6. Next-token story completion is framed as the model's "recommendation", "advice",
and "predicted action", the reading the study's own limitations disclaim.** (clinical,
mech-interp) Verified verbatim: the H1 "Medical AI must be ready to interpret them",
"competing recommendations ranked by probability", "Safety view: urgency of the
predicted action", "The advice changed, not just its probability", "changes toward
less help", "Translation matters most when it changes the advice". The limitations
correctly say the opposite ("a probe of model behavior, not a clinical outcome"), and
the engine's scope statement says nothing here evaluates medical advice. The stimuli
are third-person narrative completions on an undeployed 2B base model. Checker
correction folded in: the og and meta descriptions do scope to gemma-2-2b; only the
H1 and twitter description lack model scoping. **Fix:** replace
recommendation/advice/help vocabulary with predicted-continuation language in the
named spots; scope the H1 and twitter description; surface one sentence of the
limitations scoping in the home safety view, in the same visual unit as the downgrade
counts.

**7. The urgency-tier vocabulary is token-level, ambiguity-dominated, and
self-contradictory, including in the emergency tier.** (clinical) Verified: tiers
attach to bare lowercased tokens; "blood" is tier 2 while its own note says it is not
a care action, and methods.html renders it as a measured example of generalist care;
tier 4 holds five tokens of which "ed" and "ers" are still review-flagged; "sleep"
(tier 1 as sleep aid) decides three downgrade calls; 129 tokens remain
confidence=review; 61% of flips (968 of 1587) are discarded as uninformative, so the
downgrade asymmetry rests on the 39% the owner could label, with single unresolved
tokens gating 23 ("new") and 12 ("blood") classifications. **Fix:** score tiers on the
multi-token continuations the logits backend already records; correct "blood" and drop
"ed"/"ers" from tier 4 pending review; publish a sensitivity analysis excluding all
review-flagged tokens next to the headline counts.

**8. The clinical_mass construct has zero reported validation and a circular category
definition, and unmatched features default into the load-bearing category.**
(mech-interp) Every green-versus-dark story rests on keyword-matching of
machine-written feature descriptions. No validation artifact exists in either repo: no
human-audited sample, no agreement statistics, no keyword-sensitivity analysis. The
checker found the problem is stronger than charged: `feature_tagger.py` sets
`DEFAULT_CATEGORY = CATEGORY_OFF_TARGET`, so unmatched non-structural features fall
into the category defined as "the mechanism of the language penalty", a definition
that presupposes the conclusion. The project already documents that untagged models
produce clinical_mass near 0.0 as an artifact, with no analogous analysis for tagged
numbers. **Fix:** validation appendix (blind two-rater sample of about 100 features,
agreement, precision/recall, keyword-ablation range for the headline deltas); change
or disclose the default-category behavior; rewrite the off-target definition
descriptively and let the mass-shift result carry the mechanism claim.

**9. Lens window: the capture/hijack taxonomy attributes to wording what is mostly
instrument blindness, and "never formed" overstates what a top-8 readout can
support.** (mech-interp; count correction CONFIRMED exactly, the companion
never-formed finding PARTLY) Verified: 34 of 56 "captures" have the clinical answer
unreadable under both wordings (20 of those 34 were screened out below 0.02, so the
lens not seeing them is expected), leaving 22 wording-attributable captures versus 14
hijacks, not the 56 v 14 the page narrates. No persistence criterion exists: a
single-layer blip at the top-8 boundary counts as formation (the showcased hijack
exemplar is rank 7, gone, rank 8, rank 5, gone). Checker corrections on the
never-formed side: the claimed 24% miss rate on measurable answers is unsupported
(only 7 of the 40 never-formed clinical readings passed the 0.02 screen, so the
screen-passed never-formed rate is 7/90, about 8%), and window-qualified language does
appear in the body, not only the endnote. The strong existence prose ("It is
existence", "not readable at any layer") still overreaches a rank-censored
instrument. **Fix:** restrict capture/hijack classification to pairs whose clinical
side is lens-readable and report the 34 both-null pairs as a separate unreadable
class; add a persistence rule before "formed" is assigned; republish 22 v 14 and
rewrite the body text to top-8-window language; add a window-size sensitivity
(top-4/8/16) to `jlens_insights.json`.

**10. The "cluster bootstrap" is an iid bootstrap over phrase means, and the majority
vote mixes estimands.** (statistician) `cluster_bootstrap_ci()` resamples values that
are already one-per-cluster phrase means; every cluster is a singleton. The label buys
credibility against exactly one threat (verbatim re-traces) that the deterministic
tracer makes nearly information-free, while the design's real clustering (LLM
generation in 50-100-pair batches from eight standing topics, seed-pair anchoring,
near-duplicates under an exact-string dedupe key) is unmodeled. The vote also collapses
rows differing on the patient side (paraphrase variants the prereg assigns to a
separate analysis, plus steered re-traces) into one label. **Fix:** report batch-level
and topic-level bootstraps as sensitivity intervals plus a near-duplicate diagnostic;
restrict the vote to rows sharing the full (clinical, patient) pair; rename the method
"phrase-level bootstrap after dedupe".

**11. Flagship per-pair numbers breach the prereg's paraphrase-noise rule, and the
front-page case is an undisclosed extreme-tail pick.** (methods) The prereg fixes "no
per-pair claim is reported without its paraphrase-noise caveat"; the study's own
control (innocuous rewording moves single-pair probabilities by mean absolute delta
0.064) is rendered on zero pages. The inhaler demo (-65 pp) is about 19 times the
population mean (-3.5 pp) and was surfaced by the exporter's consequence ranking,
disclosed only on the scenarios page, with no adjacent base-rate anchor on the front
page. Checker nuance: the rule postdates the Tier A flagship cases, so the letter of
the breach is arguable; the site-wide absence of any per-pair noise caveat is factual.
**Fix:** surface `paraphrase_robustness` into a fetched data file and render a
one-line caveat beside each per-pair headline; caption the demo as the largest
measured effect against the stated mean.

**12. Dialect variety labeling: the share card asserts the authenticity the endnote
disclaims, and named varieties rest on one unvalidated LLM sentence per cell.**
(sociolinguist, three CONFIRMED findings merged) The og description claims "the way
different communities actually speak" while the approximation caveat sits in muted
footer type; the homepage specimen names "dialect" as the cause with no authorship
disclosure in the same visual unit. Each (term x framing) cell is a single
Claude-written sentence, validated only for term fixity, never dialectal accuracy. The
"Caribbean English" column mixes Jamaican Creole basilect with Trinidadian mesolect
and acrolect; "ESL" is not a variety and its probes stereotype one L1 group. The 2x2
labels "prestige form" versus nameless "nonstandard morphosyntax" quietly test
AAVE-associated features (unstressed "been", "I'ma") as generic bad grammar, against a
"Standard English" baseline row that is itself colloquial; the homepage generalizes a
single traced insomnia item as "From our analysis, changing the grammar alone shifts
+11-13%", with a companion register delta below the noise floor. **Fix:** rewrite the
og/twitter descriptions to "LLM-approximated framings"; relabel matrix columns as
generator instructions with n=1 per cell stated; split or drop the Caribbean column;
rename or cut ESL; relabel the baseline row and the 2x2 cells descriptively, naming
the features actually tested; scope the homepage grammar claim to the one traced case.
Gate any return of community names on the already-promised validation.

### Partly confirmed (checker corrections folded in)

**13. The care ladder counts appropriate referral behavior as a safety downgrade, and
the downgrade-versus-upgrade null is directional by construction.** (clinical, PARTLY:
numerators confirmed, denominators corrected) Corrected numbers: 114 of 315 downgrade
rows (36.2%) are tier 3 to tier 2 moves, the largest transition class; on gemma-2-2b,
47 of 137. The provenance exemplar makes it concrete: patient wording yields "doctor"
at 68%, a guideline-concordant primary-care pathway, scored as a downgrade against
"dermatologist" at 54%. No clinical framework is cited for the tier ordering, and the
50/50 null is loaded: clinical prompts anchor targets at tiers 1-3 (577 of 654
informative flips; tier 4 in only 5), so flips have more room below than above.
**Fix:** publish the tier-transition matrix next to every downgrade count; split "left
the care domain" (to tier 0) from "moved within professional care" (3 to 2), or
collapse tiers 2-3 pending clinician review; state that the null is directional by
construction; retitle the claim "moves out of the care vocabulary" until domain review.

**14. Row-population scope: the per-model statistics pool non-observational and
outcome-selected rows, and the compared populations are incommensurable.**
(statistician, PARTLY; replication context) Core confirmed: `analyze()` filters only
by model and holdout tag. gemma-2-2b's published population (n_rows 1027) includes
steered boostgrid rows, the outcome-selected reviewed downgrade set, the hand-built
imported pairs the site promises are "kept separate", repeatability and drift
re-traces, and translation re-runs, with steered rows voting in phrase flip labels.
Corrections: gemma-3-4b-it also pools 19 outcome-selected downgrade rows (only the two
qwen models are pairs_*-only, which extends the contamination); n_rows is 1027, not
1020; "measured once" is literally exact only for medgemma among the frozen-n models.
The replication independently confirmed the population is batch-inclusive and that the
headline is robust to dropping steered/QC rows (-3.5 pp either way; 54/13 v 55/13
downgrades), so this is a hygiene and disclosure problem, not a results problem.
**Fix:** restrict the confirmatory table to observational pairs_* rows (copy
`convergence_tracker.py`'s scope filter into `paired_stats_rigor.py`), report the
all-rows version as sensitivity, document the population in the file metadata, and put
the steered/QC inclusion question to the owner.

**15. Translation: "restores it" outruns an uncontrolled n=14 on a downgrade-selected
set, but the placebo arm already exists and supports specificity; the 45% to 41%
"re-trace" is a mislabeled paraphrase comparison.** (mech-interp, methods, PARTLY,
three findings merged) Confirmed: the classified evidence is 18 cases (8 recovered, 3
unrecovered, 3 worsened, 4 already ok; 8 of 14 classifiable, 57%) under a universal
present-tense subtitle; "restores the circuit" is quantified nowhere; the depth-router
story is contradicted by flat by-class recovery (lost-late 0.157, never-formed 0.163,
retained 0.13, the last a noise floor, and never-formed above lost-late, opposite the
draft amendment's prediction); the methods audit line about translation destroying
information never appears on the translation page. Checker corrections: "no control
arm" is wrong at the artifact level; the placebo-paraphrase arm ran 2026-07-11, its 26
rows are in the site's own `urgency_shift.json` (mean recovery 0.028-0.033 versus
0.080-0.122 for real translation, so about two thirds of the benefit is
vocabulary-specific), and it is analyzed in the engine's draft synthesis; it is simply
rendered on no page. And the July 7 versus July 9 discrepancy does not falsify "zero
repeat variation": the July 9 run traced a different translated sentence ("Grandmother
has been" 0.453 v "Grandma has been" 0.409) while the clinical panel reproduced
exactly; the mislabel is calling it "re-trace jitter" when it is a paraphrase
comparison, and the methods repeatability claim is silently scoped to panels
`retrace_consistency.py` actually compares. **Fix:** publish the landed placebo result
on the translation page and rewrite the subtitle to the measured rate including the
worsened cases; delete "restores the circuit" until circuit-level recovery is
quantified; relabel July 9 as a paraphrase comparison and scope the repeatability
claim; run the queued lens analysis before any depth-routing language returns, with
the retained-class 0.13 displayed as the noise benchmark.

**16. The LLM-authorship disclosure is missing from the pages where conclusions
form.** (clinical, PARTLY) Correction folded in: the home page does disclose synthetic
stimuli, but inside the Simulated Scenarios gallery card, not in the hero demo, the
figure captions, or the safety view; start-here and translation genuinely contain no
stimulus-authorship statement, and start-here frames the material as patient speech.
**Fix:** add the existing SIMULATED DATA endnote verbatim to index, start-here, and
translation; place "LLM-authored stimuli" in the safety-view and start-here step-4
captions, in the same visual unit as the downgrade counts.

**17. All circuit and causal claims rest on one 2B base model, and the steering
titration is computed on pairs pre-selected for steering success.** (mech-interp,
PARTLY) Confirmed core: every graph, tag, lens readout, patch, and steering result is
gemma-2-2b; the titration cells (4/5, 5/5, 4/5) are measured on the 5 boost-recovered
cases out of 20, so near-ceiling recovery is built in, and the translation page
presents them without the selection rule (the 5/20 base rate is disclosed only on the
scenarios page). Corrections: the og/meta descriptions do scope to gemma-2-2b (only
the H1 and twitter description lack it), and the rank arm is n=4 measured (3/4; one
call failed server-side), not n=5. The informative contrasts are the placebo (0/5) and
rank arms. **Fix:** add the selection rule to the titration caption; re-run the
dose-response on a fresh, unselected downgrade sample before keeping "the effect is
the clinical circuit" language; state the one-model circuit scope wherever circuit
claims appear.

**18. Dialect measurement validity: some cells sit inside the paraphrase-noise floor,
the benchmark is surfaced nowhere, and most matrix cells measure syntax, not care
content.** (sociolinguist, PARTLY, two findings merged) Corrections first: "most cells
are within noise" is wrong (16 of 38 measured cells are at or below 0.064; median
absolute delta 0.082), and function-word rows supply only 2 of 10 flips, though they
are 24 of 40 cells (60%). What stands: the 0.064 benchmark appears on no page, so
readers cannot tell noise-scale cells from signal; the featured "flips" run toward
more clinical answers ("pill", "medication" against baseline "break") while borrowing
the penalty-red flip grammar; wordform variants (medication to "meds") count as flips;
and 3 of 5 rows target function words ("my", "the"), so p("the") after a rewritten
verb frame is read as a dialect effect on medical interpretation. The "postprandial"
baseline is not well-formed clinical English. **Fix:** print the noise benchmark in
the matrix caption; color flips by direction relative to the clinical target; tag or
exclude function-word rows from headline counts; footnote wordform-variant flips;
retire or regenerate the postprandial row.

## MINOR findings

- Translation outcomes are stated three inconsistent ways (provenance summary 8/7/5 of
  20; all.cases 8/3/3/4 of 18; start-here's 8/7/3 matches neither); reconcile to one
  record and cite it everywhere.
- Phrase-dataset provenance conflicts: the methods endnote says hand-built from real
  patient language, the dataset page and start-here say patient language is still to
  come; determine which is true and align all three.
- Part 4 never reconciles the byte-identical hosted -it lens readouts with the -it CPU
  row above it; one sentence naming the backend difference resolves the aliasing
  question and would replace an information-free figure.
- Target screening conditions on the clinical side of the differenced quantity with no
  published sensitivity; run the threshold sweep (0/0.01/0.02/0.05) on the free logits
  backend.
- No version anchor: `model_stats.json` and `urgency_shift.json` carry no timestamp or
  commit; stale hard-coded text (52 v 68 re-traces); three unreconciled gemma-2-2b n's
  on one page; and the convergence series includes the emergency batches that
  provenance marks outside the pre-registered run (checker-confirmed).
- The register-ladder null (flat 27-34% across 10 baselines) is hidden in a collapsed
  fold while start-here teaches "the wording chooses the answer" from the single
  staircase the data file itself calls unrepresentative.
- The claim-grade table renders q = 0 (impossible for an exact sign test; 5-decimal
  rounding), sidedness is unstated (it is two-sided), and the rigor script's docstring
  still describes a four-test BH family while n_tests is 8.

## Fix before any preprint

Ordered by leverage. Tags: (a) engine/analysis, (b) site wording, (c) new
measurements or controls, (d) owner or outside experts.

1. (a) Rescope the confirmatory population in `paired_stats_rigor.py`: observational
   pairs_* rows only (copy the `convergence_tracker.py` filter), all-rows version as
   a labeled sensitivity, generator/tier stratification per the prereg, holdout
   exclusion phrase-keyed (replication recommendation), majority vote restricted to
   full (clinical, patient) pairs.
2. (a) Fix the inference layer: confirmatory BH over the pre-registered four with the
   additions in an exploratory block; simultaneous intervals behind any every-model
   sentence; batch- and topic-level bootstraps plus a near-duplicate diagnostic;
   exact unrounded p-values; corrected docstring and honest CI-method label.
3. (b) Relabel Part 4 "interim, exploration split"; tag post-registration models and
   link the divergence log; rewrite the convergence fold (drop the 36/155 sentence,
   stop saying frozen-n models "settled"); rewrite the medgemma sentence with n, CI,
   and exploratory status.
4. (a,b) Holdout: amend the analysis plan now (holdout-only versus pooled, honest
   8-10 pp achievable precision, reconciliation rule); withhold holdout rows from
   published payloads or change "sealed, never touched" to "excluded from published
   aggregates; individual measurements are public".
5. (b) Reframe the front door: replace recommendation/advice/help vocabulary with
   predicted-continuation language; scope the H1 and twitter description to the
   measured models; put one sentence of the limitations scoping in the home safety
   view; add the SIMULATED DATA endnote to index, start-here, and translation, with
   "LLM-authored stimuli" in the safety-view caption.
6. (b,c) Translation: publish the landed placebo arm beside the recovery claim;
   rewrite "restores it" to the measured 8-of-14 rate with the worsened cases; delete
   "restores the circuit"; relabel July 9 as a paraphrase comparison and scope the
   repeatability claim to what `retrace_consistency.py` compares; reconcile the two
   provenance translation records.
7. (a) Lens: add a persistence rule; restrict capture/hijack to clinical-readable
   pairs and republish 22 v 14 with the 34 both-null pairs as an unreadable class;
   rewrite existence prose to top-8-window language; add window-size sensitivity to
   `jlens_insights.json`.
8. (c) Feature-tagger validation appendix: blind two-rater sample of about 100
   features with agreement and precision/recall; keyword-ablation range for the
   headline clinical-share deltas; change or disclose the off-target default
   category; rewrite the off-target definition descriptively.
9. (a) Urgency instrument: score tiers on the recorded multi-token continuations;
   correct "blood"; drop "ed"/"ers" from tier 4 pending review; publish the
   tier-transition matrix and a review-token-excluded sensitivity next to every
   downgrade count; state that the asymmetry null is directional by construction.
10. (b) Surface the paraphrase-noise benchmark (0.064) as a fetched data field with a
    one-line caveat beside every per-pair headline and in the dialect matrix caption;
    caption the front-page demo as the largest measured effect against the -3.5 pp
    mean.
11. (b) Dialect relabeling: og/twitter descriptions to "LLM-approximated framings";
    matrix columns as generator instructions with per-cell n=1 stated; split or drop
    the Caribbean column; rename or cut ESL; relabel the baseline row and 2x2 cells,
    naming the AAVE-associated features actually tested; tag function-word-target
    rows and exclude them from headline flip counts; scope the homepage grammar claim
    to the one traced case.
12. (c) New measurements, zero or near-zero cost: steering titration on a fresh
    unselected downgrade sample; re-run the failed rank-arm call; screening-threshold
    sweep on the logits backend; a translation panel on the hand-built set.
13. (a) Version anchors: emit generated_utc plus engine commit into exported data
    files and render as-of stamps under the forest plot and table; reconcile the
    three gemma-2-2b n's; fix stale fallback text; label or exclude the emergency
    batches from prereg-facing series.
14. (d) Owner and outside experts: clinician review of the tier vocabulary and ladder
    ordering (the checklist exists); community or linguist validation before variety
    names return to the dialect matrix; owner decisions on steered/QC rows in
    observational statistics and on the emergency batches; resolve the "real patient
    language" provenance statement.
