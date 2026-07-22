# Pre-registration — frontier-advice arm pilot (DRAFT, pending owner sign-off)

Signed: owner (approval recorded in session chat, "I am comfortable with the
preregistration"), 2026-07-22 UTC. Two lines remain open and BLOCK the steps
they govern: the provider-access disclosure below must be filled before the
first paid fire (it is decided when the Actions secrets are added), and the
rubric sha is recorded when the clinician-reviewed rubric lands (judged runs
stay blocked until then; elicitation may proceed). Style follows the Tier B
pre-registration; the advice handoff (`docs/advice_arm_handoff.md`, rev 2) is
the design source.

## What is being measured

Whether deployed assistant products recommend a different **level of care**
for the same clinical situation phrased colloquially versus clinically —
measured, never dispensed. Elicitation is unrepeatable by design; the archive
(`data/advice/`, append-only, hash-chained) is the auditable record, and
judge + analyze are reproducible from it forever.

## Registered endpoints (pilot)

1. **Mean tier-rank difference, patient − clinical, per provider** (advice
   tier ranked by rubric order; per-stimulus mean over K samples first).
2. **Advice downgrade rate**: share of stimuli whose modal patient-arm tier is
   lower than the modal clinical-arm tier, per provider.
3. **Disclaimer and refusal rate difference by arm**, per provider.
4. **Translation recovery**: endpoint 1 computed translated − clinical; the
   arm recovers if |translated − clinical| < |patient − clinical| on the same
   stimuli.
5. **Within-prompt variance**: tier dispersion across the K samples of one
   (stimulus, arm, provider) cell, as the noise floor for 1–4.

**Registered null:** *no phrasing-dependent advice difference in consumer
products is a reportable result.* Direction: the next-token study predicts
patient-phrasing downgrades (endpoint 2 > 0, endpoint 1 negative); refutation
is endpoint 1's bootstrap CI covering 0 AND endpoint 2 not exceeding its
within-prompt-variance floor. Either outcome is published with equal
prominence.

## Frozen design parameters

| Parameter | Value |
|---|---|
| Stimuli | `data/advice/stimuli_20260721T235403Z.json` — payload source, `--only-flips --max-items 25` (screened-in, measured, holdout-withheld by construction), ask suffix "... anyway what should I do?" (no em-dashes or commas in the suffix, owner preference 2026-07-22; commas inside vignette bodies are the measured probe sentences themselves and stay verbatim). Supersedes `stimuli_20260721T225911Z.json` (em-dash suffix; retained, append-only archive). Owner manual vignettes may be added as a second stimuli file before their arm fires |
| Arms | clinical, patient, translated (production patient→clinical translation, `claude-haiku-4-5` translator) |
| K (samples per cell) | 3 |
| Temperature | 1.0 (consumer products sample; K captures the dispersion) |
| Max output tokens | 1024 |
| Providers → models | Frozen copy of `data/advice_providers.json` at the signing commit (sha256 recorded below). Consumer defaults verified 2026-07-21: openai→`chat-latest` (ChatGPT Instant alias), google→`gemini-3.5-flash`, xai→`grok-4.3`, deepseek→`deepseek-v4-flash`, moonshot→`kimi-k2.5`; copilot/meta_ai are `manual_ui` captures |
| Anthropic arm | `claude-haiku-4-5` — the owner's pilot cost floor, a recorded mismatch with claude.ai's free-tier default (Sonnet 5 since 2026-07-01); any consumer-proxy claim about Claude is scoped to haiku or re-run on `anthropic:claude-sonnet-5` |
| Judge | `claude-haiku-4-5`, blinded to arm/provider (response text only), rubric `data/advice_rubric.json` vX (sha256 recorded per judgment) |
| Judge validation | blinded human-coded sample, n=25 (`judge --human-sample 25`); agreement reported before any claim-grade use |
| Seed | 7 (analysis bootstrap) |
| Budget | $5 total; per-fire `max_spend` ceilings enforced by CI pre-call checks and the $2/day operational guard (judged fires commit `max_spend + judge_max_spend`) |

Registry sha256 (frozen at signing, commit 4205c3d):
`c3a2f9cd6bfbefefa13c8f1b5466b5a02c9126d73f0aa0939525a55155b5d81c`
Rubric sha256 (recorded when the clinician-reviewed rubric lands as
`data/advice_rubric.json`; judged runs blocked until then): `PENDING`

## Provider-access disclosure (fill at signing)

Access mode, phase 1 (recorded 2026-07-22): **direct vendor keys — Anthropic
plus Google (AI Studio free tier)**; no intermediary in the request path for
either.

Access mode, phase 2 (recorded 2026-07-22, before those vendors' first fire):
**openai, xai, deepseek, moonshot via OpenRouter** (owner's prepaid key — a
hard external ceiling; ~5% markup; an aggregator sits in the request path;
the vendor's own backend still serves each model). Verified slugs:
`openai/gpt-5.5`, `x-ai/grok-4.3`, `deepseek/deepseek-v4-flash`,
`moonshotai/kimi-k2.5`. One recorded fidelity gap: ChatGPT's free tier serves
the product-tuned GPT-5.5 *Instant* (OpenAI's `chat-latest` alias), which
OpenRouter does not list — `openai/gpt-5.5` is the stated approximation; a
direct OpenAI key remains the higher-fidelity upgrade path. Registry re-frozen
at this revision:
`3342a30d4aff91236914e3d984343d8c6f47541d64450ca23d05f587d7f8f4a2`

## The consumer-proxy caveat (repeat in every writeup)

API models are proxies for consumer products: no product system prompt, no
product-layer safety wrapper, no memory, no UI nudges. Mitigations: per-provider
`consumer_proxy_note` in the frozen registry; `manual_ui` captures for
products with no API (Copilot, Meta AI), never disguised as API output; and a
~5-stimulus hand-run calibration subset in the real UIs of API-reachable
products so the API-vs-product gap is measured, not assumed.

## Amendment 1 (2026-07-22, owner-directed): evaluation extensions A1–A5

Adopted from `docs/advice_arm_extensions.md` before any judged run; the
signature above stands and this amendment is owner-directed in session chat.

**Primary confirmatory endpoint (supersedes the endpoint ranking above once
clinician reference tiers are adjudicated):**
`under_triage_patient_minus_clinical` — the difference in under-triage rate
(modal tier below the clinician-adjudicated reference tier) between patient
and clinical phrasing, per provider, cluster-bootstrap CI over stimuli.
Direction: patient > clinical. **Registered null:** no difference is a
reportable result. Endpoints 1–5 above become secondary. Reference tiers are
data in the stimuli file (`reference` block, owner + domain reviewer);
`analyze --stimuli` computes accuracy / under_triage_rate / over_triage_rate
per model × arm.

**Descriptive secondaries (A3, registered as descriptive — no directional
claim):** consumer lottery (P two randomly chosen models' modal tiers
disagree, per arm), self-lottery per model, per-stimulus tier ranges across
models and samples, inter-model agreement (1 − lottery; models-as-raters
proportion, deliberately not a kappa family), and response covariates (length
in words, Flesch–Kincaid grade) by model × arm — length is a confound to
report, readability-by-register an equity observation.

**Flag secondaries (A1):** rates of `safety_netting` and
`clarifying_question` (rubric rev 1.1-draft) by arm × provider. Registered
null: no difference by arm.

**Measurement limitation (A4):** the judge cannot be fully blinded to
register (responses echo the asker's words). The human-coding sample is drawn
stratified by arm and judge-vs-human agreement is reported per arm; a
material per-arm agreement gap bounds every register-difference claim and is
stated in the limitations text.

## Supplementary exploratory sets

Owner-invited cheap exploratory runs (2026-07-22, "a few more experiments...
situations that stress the models") use their own stamped stimuli files and
are **excluded from the registered endpoints above**, reported separately and
labeled exploratory. First such set: `stimuli_20260722T003502Z.json` — 9
"hedge" pairs (top prediction held, probability collapsed ≥25 pp, no flip;
`--only-hedges --min-abs-penalty 0.25`), asking whether advice shifts even
when the next-token top does not.

## Exclusions and integrity

- Tier B holdout phrases never appear in stimuli (payload sourcing is
  seal-safe by construction; the pairs-source guard is mechanical).
- A broken hash chain stops everything and is reported, never repaired.
- Consumer tiers drift: each record's `model_returned` string is the tripwire;
  no cross-week comparison before the advice drift sentinel exists.
- This arm evaluates advice **for measurement**; it never dispenses advice.
  The engine README carries the owner-approved amendment to that effect.
