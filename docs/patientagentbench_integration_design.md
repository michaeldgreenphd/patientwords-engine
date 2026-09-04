# PatientAgentBench × PatientWords — integration design (draft, 2026-08-03)

Exploratory design note. Nothing here is registered, fired, or published. It exists to
decide whether an integration is worth a pre-registration amendment.

## The other instrument

**PatientAgentBench** (Vatanparvar et al., Amazon Health AI, arXiv:2607.25485v1, 28 Jul
2026; code at `amazon-science/PatientAgentBench`, CC-BY-NC-4.0). It wraps a foundation
model in an agent with a sandboxed set of healthcare tools and has it converse with a
*simulated patient agent* over multi-turn, task-oriented dialogue. Every conversation is
scored 1–5 by an LLM-as-a-Jury against 102 clinician-grounded criteria across six
dimensions: clinical safety, triage quality, workflow accuracy, task completion, clinical
helpfulness, conversational quality. Licensed clinicians annotated a shared subset:
**79–93% adjacent agreement** between jury and expert raters, on par with or exceeding
clinician inter-rater agreement. Reported: 10 models across 4 families, 1,200 scenarios
each.

What ships in the repo: the seed distribution (79 conditions, 4 task categories, 24
subtasks), the scenario generator, the sandbox, the dual-agent runner, the six rubric
prompts, and a **20-scenario sample**. The full 1,200 are generated on demand — a
deliberate contamination-resistance property. **No conversations ship.**

## Why this is a two-way fit

### What PatientWords fills for PatientAgentBench

Their headline sensitivity result is that **patient personality is the strongest
performance driver across all benchmark attributes** — larger than scenario complexity,
severity, demographics, or task category. On triage quality (their most discriminating
dimension, 32%–88% pass rates), GPT-5.5 shows a 0.79-point spread across personas.

But the persona system cannot say *which* part of "how the patient talks" is responsible.
`user_agent/personalities.py` defines seven traits × three levels, then bundles them into
six fixed presets; `get_personality_prompt()` accepts only a preset name. The traits
covary, and the only contrast that touches health literacy runs backwards:

| preset     | health_literacy | cooperation | clarity | urgency | communication | triage (GPT-OSS-120B) |
|------------|-----------------|-------------|---------|---------|---------------|-----------------------|
| confused   | **low**         | high        | low     | low     | medium        | **3.15**              |
| skeptical  | **high**        | low         | high    | medium  | low           | **2.52**              |
| cooperative| high            | high        | high    | medium  | medium        | —                     |

The low-literacy persona scored *better* than the high-literacy one, and the paper
attributes the degradation to patients "who provide minimal clinical information and
resist guidance" — i.e. clarity and cooperation. Only one preset carries
`health_literacy: low`, and it also carries `clarity: low` and `urgency: low`, both
independent clinical reasons to de-escalate. The register effect is not identified.

PatientWords' entire method is the missing manipulation: hold the clinical situation
identical, swap exactly one contiguous span, validate the swap programmatically, measure.
The two study arms map onto their two register traits — the wording study varies medical
terminology (`health_literacy` axis); the dialect study holds the term fixed and varies
surrounding syntax (`communication` axis, whose trait text names casual phrasing and
"minor typos").

Secondary contribution: their clinician annotators flagged that simulated patients
"occasionally used clinical jargon (e.g. 'crisis level symptoms') rather than lay
language" — a documented fidelity gap in the patient simulator, in exactly the domain
where PatientWords holds a validated phrase corpus.

### What PatientAgentBench fills for PatientWords

1. **A clinician-validated urgency rubric.** Care-urgency tiers are currently
   owner-reviewed v1, domain review pending — a caveat on every urgency claim the site
   publishes. Their triage rubric is a 1–5 anchored scale (1 = "Dangerous triage —
   self-care for emergency symptoms, missed urgent signs") co-developed with licensed
   clinicians and validated at 79–93% agreement.
2. **Multi-turn.** The advice arm is single-turn (50 scenarios × 8 models × 3 attempts).
   The obvious reviewer question — does the gap survive a conversation where the agent can
   ask a clarifying question — is directly measurable here.
3. **Comorbidity and polypharmacy structure.** See the coverage diff below.
4. **A harness-vs-model result to compare against.** Their context-engineering case study
   raised triage +0.59 without changing the base model, several times the effect of
   switching Sonnet→Opus. If wording gaps are similarly harness-fixable, that is a
   deployable safety finding.

## Coverage diff (computed 2026-08-03)

Their 79 seed conditions against the 282 free-text topics in the published
`simulated_scenarios.json`. The matcher is lexical token overlap and **over-reports gaps**
— it misses synonym pairs (their "Heart palpitations" vs our "cardiac palpitations", their
"Sinus infection" vs our "rhinosinusitis"). Treat 37 as an upper bound.

- ~42 of 79 conditions fall inside the existing topic space.
- ≤37 do not.
- **25 of the 79 are comorbid or polypharmacy combinations** — e.g. "COPD with heart
  failure", "Atrial fibrillation on warfarin with new NSAID need", "Elderly polypharmacy
  with heart failure, COPD, diabetes, and arthritis".

The robust finding is structural, not lexical. The two corpora carve clinical space
differently: PatientWords topics are **symptom- and system-oriented** single conditions;
PatientAgentBench conditions are **named diagnoses and comorbidity clusters**. The
comorbid category is absent from PatientWords by construction — every stress pair is a
single-condition frame — and the paper reports that complicated cases are exactly where
agent tiers diverge (frontier agents improve on them; weaker agents degrade).

## Proposed integration, in cost order

### Tier 0 — free, no API calls
Read the 20-scenario sample and the seed. Use their condition list as a **topic seed** for
the existing generator: the comorbid combinations and named acute presentations become
topics for PatientWords-authored stress pairs. Buys externally-derived clinical coverage
with no licensing entanglement on generated text and no spend. Does not buy independent
*phrasing*.

### Tier 1 — the decomposition experiment (the case for doing this at all)
Fork-side change: a function accepting an arbitrary `Dict[str, str]` of trait→level and
formatting it from the existing `TRAIT_DEFINITIONS`. Roughly ten lines; the data structure
is already factored, only the public API is preset-locked.

Then a single-factor sweep: hold vignette, patient record, and six traits fixed; vary
`health_literacy` across low/medium/high; read the triage-quality delta. Repeat
independently for `communication`. This is the identification analysis their own paper
could not run, on their stimuli, against their clinician-validated rubric.

Design notes: needs a scenario set held constant across arms (generate once, reuse);
per-arm n and model count drive the whole cost; report as a paired analysis, since arms
share the scenario.

### Tier 2 — harvested stimuli
Conversations generated in Tier 1 emit first-person patient utterances for identical
clinical situations, paired by construction across literacy levels. Harvest patient turns,
convert to next-token probe frames, and trace on gemma-2-2b — the only route by which this
benchmark reaches the interpretability core.

Caveat that must be stated in any writeup: probe construction remains ours, so this yields
**independent phrasing with our probe framing**, not independent stimuli. And the default
config runs the patient agent on Bedrock Claude models (`claude-sonnet-5-bedrock`,
`claude-opus-4-8`); generating patient turns with Claude reintroduces the provenance
limitation the exercise is meant to escape. Running the patient agent on a non-Claude
family is what makes the harvest genuinely independent.

## Blockers to resolve before any of this is registered

- **Cost.** Their scale is 1,200 scenarios per model. The operational ceiling is $2/day,
  enforced by `fire_trigger.py`. Tier 1 needs an explicit per-arm budget before a single
  fire; Tier 2 multiplies it.
- **License.** Data and code are CC-BY-NC-4.0. Site data ships under `DATA_LICENSE.md`,
  code under MIT. Any derived artifact entering the public repos inherits attribution and
  NonCommercial terms. Decide the boundary before anything derived lands.
- **Pre-registration.** Tier 1 changes what is measured and with which instrument. It is
  an amendment (the fifth) or an explicitly labeled exploratory arm — not a silent
  addition to a running Tier B. Adopting an external rubric *after* seeing that it agrees
  better than ours would be instrument shopping; the posture has to be fixed in advance.
- **Seal.** Any new phrase entering the site must pass `seal_check.py --site
  ../patientwords`. External conditions are unlikely to collide with the sealed Tier B
  holdout, but the check is mandatory, not optional.
- **Evaluator stack.** Their patient is an LLM and their jury is an LLM; ours are too.
  Their clinician validation mitigates this and is stronger than what we have, but the
  combined stack must be disclosed plainly rather than treating the benchmark as ground
  truth.

## What this does not do

It does not extend the circuit or Jacobian-lens work directly. Attribution graphs cannot
be traced through a multi-turn tool-using conversation. Tier 2 is the only path from this
benchmark to the interpretability core, and it arrives by way of harvested sentences, not
by tracing anything the benchmark itself runs.

## Open questions

1. Does trait independence survive prompt-level interaction? Setting `health_literacy:
   low` in isolation may produce an incoherent persona the simulator partly ignores.
   Test on a handful of conversations before committing to a sweep.
2. Does their triage rubric's 1–5 scale map monotonically onto the five-tier care ladder,
   or do the anchors cross? A mapping study on the existing reviewed downgrade set is
   cheap and answers it.
3. Can the patient agent run on a non-Bedrock, non-Claude model without harness changes?
   Determines whether Tier 2 provenance is achievable at all.
