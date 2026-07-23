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

Access mode change (recorded 2026-07-22, before the affected fires):
google's direct AI Studio free tier proved daily-quota-capped — run 1b and
the first hedge run died on sustained 429s despite 10 s pacing and transient
retries. Per the owner's conditional pre-approval (session chat 2026-07-22),
the google arm's REMAINDER routes via OpenRouter
(`openrouter:google/gemini-3.5-flash`, vendor-served, ~5% markup, aggregator
in the request path). Records carry the exact spec they were elicited under;
the direct-path records stand unchanged; cells re-elicited under the new spec
are additional records, never replacements. Analysis joins google's two
access paths by `model_returned`.

Metering amendment (recorded 2026-07-22, after runs 1c and hedge-resume):
the registry's aggregator catch-all `default_pricing` (5, 30 USD/Mtok, sized
for GPT-tier slugs) metered the rerouted `openrouter:google/gemini-3.5-flash`
calls at ~12x the flash-tier rate, so both runs hit their `max_spend`
ceilings early (11 and 7 gemini records landed before truncation). The
archives stand as written — the per-record `cost_usd` values for those
records carry the inflated metering rate, the token counts are the measured
truth, and real cost is recomputable from them. The registry now carries a
per-model rate for the slug ([0.35, 2.75] USD/Mtok = vendor list + markup +
margin; regression test `test_registry_prices_rerouted_gemini_slug`).
Registry re-frozen at this revision:
`84acef3606cb8afa10cabe5a0c72cc772a5838a8111a47f297e8cf6f7ae59fee`

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

## Amendment 2 (2026-07-22, owner-directed): provisional machine coding

Owner direction (session chat 2026-07-22): before the clinician-reviewed
rubric lands, a PROVISIONAL machine coding pass may run so the site's figures
can show placeholder grades. Terms, all binding:

- Judge `claude-haiku-4-5`, blinded exactly as registered (response text
  only), against the committed draft rubric `data/advice_rubric.draft.json`
  (version 1.1-draft; sha256 recorded per judgment as always).
- Every surface showing these codings labels them machine-coded and
  provisional pending clinician review; the rubric version string carries
  `-draft` and the site derives the label from it mechanically.
- Provisional codings are EXCLUDED from every registered endpoint and any
  claim-grade use. The registered gate stands: no claim-grade judged use
  before the clinician-reviewed rubric and the blinded human-coded agreement
  sample.
- When the clinician-reviewed rubric lands, the judge re-runs under it and
  the new judgments supersede the provisional ones everywhere they are
  published. Clinician re-grades of individual items enter through the same
  judgments path. Provisional judgment files are retained append-only for
  audit; nothing is rewritten.
- Reproducibility: each judgment record carries the judge model, the rubric
  sha256 it was coded under, and the sha256 of the exact response text coded.

## Amendment 3 (2026-07-23, owner-directed): build forensics + vendor reproduction packs

**Build capture (additive; the hash chain is unaffected).** From 2026-07-23
forward every elicitation record also carries `request_id` and `api_version`
from the provider's response headers and a first-class `build_fingerprint`
lifted from the body (system_fingerprint class), so any single call can be
correlated in the vendor's own logs. Records from before this date — the
1,238-call registered pilot included — carry body-level version strings
(`model_returned`, full raw body) but no request ids; the new fields apply
from the next elicitation forward and the n=100 scale run will carry them in
full.

**Alias vs snapshot (recorded measurement decision).** Each provider's
registered target remains the CONSUMER DEFAULT — a rolling alias wherever
that is what the vendor's free tier serves — because the study measures the
product consumers get, not a frozen build. The served build is pinned per
record (`model_returned` + `build_fingerprint` + `request_id`) rather than by
freezing the request id. Switching any arm to a dated snapshot id is an
access-mode change, recorded here before the affected fire. These fields join
the weekly advice drift sentinel when it exists: same pinned probes, any
change in served build between weeks is flagged.

**Vendor reproduction packs and sequencing (binding).** Per-vendor
reproduction packs (`advice_eval.py repro-pack`) assemble, from the public
archive alone: the claims and caveats, every record involving that vendor's
model with full request/response forensics, the chain-verification command
and expected head, the versioned rubric and that vendor's judgments, and the
exact seeded analyze command. Rules: (1) a pack goes to the affected vendor
BEFORE any public per-model comparison is published; (2) any public
per-model claim cites the pack version it is reproducible from, and that
version must be FRESH at publication time per `repro-pack --check`; (3) a
sent pack is never rebuilt in place — state changes produce a superseding
version in `ops/disclosure_log.jsonl` (append-only, public, no
vendor-private contact details), and a STALE pack with a recorded send is a
digest-level escalation until an updated pack is owed and sent.

## Supplementary exploratory sets

Owner-invited cheap exploratory runs (2026-07-22, "a few more experiments...
situations that stress the models") use their own stamped stimuli files and
are **excluded from the registered endpoints above**, reported separately and
labeled exploratory. First such set: `stimuli_20260722T003502Z.json` — 9
"hedge" pairs (top prediction held, probability collapsed ≥25 pp, no flip;
`--only-hedges --min-abs-penalty 0.25`), asking whether advice shifts even
when the next-token top does not.

Second set (built 2026-07-22, not yet fired):
`stimuli_20260722T112140Z.json` — the same 25 registered flip pairs with each
probe sentence **completed by its own pair's intended word**
(`--complete-with-target`; suffix "Anyway what should I do?", ellipsis
dropped, wording otherwise identical). Motivation: the registered stimuli
trail off mid-sentence by construction (they are the measured next-token
probes), and pilot responses show models reacting to the truncation itself;
this set measures that artifact by differing from the registered set only in
the target word being present. Two items (`pairs_20260706T201750Z#1`, `#10`)
whose intended word "sleeping" is not a complete noun carry the
owner-approved completion "sleeping pill" (`--complete-override`, session
chat 2026-07-22; recorded per item as `completion_override`). Supersedes
`stimuli_20260722T111215Z.json` (same build minus the overrides; retained,
append-only archive, never fired).

## Exclusions and integrity

- Tier B holdout phrases never appear in stimuli (payload sourcing is
  seal-safe by construction; the pairs-source guard is mechanical).
- A broken hash chain stops everything and is reported, never repaired.
- Consumer tiers drift: each record's `model_returned` string is the tripwire;
  no cross-week comparison before the advice drift sentinel exists.
- This arm evaluates advice **for measurement**; it never dispenses advice.
  The engine README carries the owner-approved amendment to that effect.
