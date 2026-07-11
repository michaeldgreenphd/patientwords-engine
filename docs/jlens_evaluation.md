# Jacobian-lens evaluation — fit with this study

Owner request 2026-07-11: evaluate Anthropic's new Jacobian lens ("J-lens") for
tasteful incorporation into the translation element and circuit communication,
with credit and links to the authors. This is the evaluation; implementation is
gated behind the checks in section 6.

## 1. What it is (verified 2026-07-11)

**Paper:** Gurnee, Sofroniew, Pearce, Piotrowski, Kauvar, Chen, Soligo, Bogdan,
Ong, Wang, Thompson, Abrahams, Kantamneni, Ameisen, Batson & Lindsey,
"Verbalizable Representations Form a Global Workspace in Language Models,"
Transformer Circuits Thread, 2026-07-06.
https://transformer-circuits.pub/2026/workspace/index.html

**Code:** https://github.com/anthropics/jacobian-lens — Apache-2.0 reference
implementation (`jlens`), explicitly "not maintained and not accepting
contributions." **Hosted demo:** https://www.neuronpedia.org/jlens (currently
Qwen3.6-27B). **Pre-fitted lens weights:** HF repo `neuronpedia/jacobian-lens`
(confirmed: Qwen3.5-4B, n=1000 wikitext; gemma files reported by secondary
sources, unverified — see J0).

Verification notes: transformer-circuits.pub, anthropic.com, neuronpedia.org and
huggingface.co are all blocked at this sandbox's egress proxy. Paper content was
read through a complete translation mirrored on GitHub
(`alchaincyf/global-workspace-paper-zh`); repo facts come from
`anthropics/jacobian-lens` directly (README + walkthrough.ipynb). Anything that
matters scientifically must be re-verified against the original from a CI runner
(open egress) before we cite it on the site.

**Method.** For each layer l, precompute once per model a d×d matrix
`J_l = E[∂h_final,t' / ∂h_l,t]` — the input-output Jacobian averaged over source
positions t, subsequent positions t' ≥ t, and ~1000 pretraining-like prompts.
The lens readout at any (layer, position) is
`lens(h) = softmax(W_U · norm(J_l h))`: transport the residual vector into the
final-layer basis, decode with the model's own unembedding, get a ranked vocab
list — "what this activation is disposed to make the model say." Inference cost
after fitting is one matmul per layer. Fitting is the expensive offline step;
the repo supports chunked fitting over disjoint prompt slices plus
`JacobianLens.merge()`, and states ~100 prompts already gives a usable lens.

**Versus what we already do.** Authors' own comparison: logit lens assumes every
layer shares the output coordinate system and becomes uninterpretable early;
tuned lens is fit to match the output distribution and "front-runs" to the
answer instead of exposing intermediate computation; the J-lens uses causal
Jacobians for the basis transport, so earlier layers stay readable. Note their
headline experiments are on Claude models (Sonnet 4.5, validated on Haiku 4.5 /
Opus 4.5 / 4.6); the open-source release demos on Qwen because those weights are
public.

**Authors' stated limitations** (all relevant to how we would use it):
single-token concepts only; treats the workspace as a flat bag of concepts (no
binding/relations); some cells resist interpretation; early-layer emptiness may
be a lens artifact; the workspace components never exceed ~10% of activation
variance. And the readout is correlational — a lens, not an intervention.

## 2. Why it fits this study

**(a) The translation element — the scientific fit.** Our mitigation question
is: when colloquial phrasing loses the clinical answer, is the concept absent or
suppressed? The paper contains a directly analogous experiment (their §6.2
thought suppression): concepts a model demonstrably represents internally
without verbalizing are visible in the lens readout. Applied here, per pair and
per phrasing, we read the lens rank/log-prob of the clinical target token at
every layer:

- **Absence:** the target never becomes readable at any depth under colloquial
  phrasing → translation supplies signal the model did not derive.
- **Suppression:** the target becomes readable mid-network, then loses to a
  colloquial continuation late → the model "had" the answer and the phrasing
  taxed the readout; translation recovers something already computed.

Distinguishing these is exactly the mechanistic story the translated third
panel currently lacks. Their biggest limitation (single-token concepts) does
not bite: our endpoint is literally the next-token probability of a target
token. And it complements rather than duplicates B1: activation patching says
*layer L carries causally sufficient signal*; the lens says *at layer L the
stream already reads out the target*. Causal claim stays with patching; the
lens adds the cheap depth-resolved readout. This also strictly dominates H2
(logit-lens depth profiles) — same figure, better-founded transport; H2 should
become the J-lens version if J1 passes.

**(b) Circuit communication.** A two-column exemplar figure — clinical vs.
colloquial phrasing, depth on one axis, the clinical answer's lens rank
forming through the layers — is the most legible "watch the answer form"
visual available, far more intuitive for the public-health audience than
feature graphs. It rhymes with the Step 4 layer track already on the site.
Rendered by us to the site's Tufte/palette standard (never their d3 CDN
pages — site hard rule: no CDN, no external imports).

## 3. Constraints and risks

| Constraint | Assessment |
|---|---|
| $0 compute rule | Holds. Fitting is offline CPU work in CI; chunked `fit()` + `merge()` maps 1:1 onto our offset-chunk + part_NN pattern. Apply step is one matmul per layer on top of forwards `logits_eval.py` already does. |
| Model mismatch | Released lenses are Qwen3.5-4B / Qwen3.6-27B — neither is in our matrix. Either (i) a gemma/our-qwen lens exists in the HF repo (verify, J0), or (ii) we fit our own on gemma-2-2b (flagship, the only traced model — strongest synergy). Do NOT add a new model to the matrix mid-study just to reuse a lens. |
| CPU feasibility | Unknown. Paper fit on GPU (1000×128 tokens). ~100-prompt fit on a free runner within 6h chunks is plausible but unproven → J1 smoke gate before anything else is promised. |
| W5 supply chain | `anthropics/jacobian-lens` is an official-org repo, Apache-2.0 → pin a commit SHA. Pre-fitted weights are `.pt` (pickle): if used, `torch.load(weights_only=True)` + pinned HF revision, same tripwire-test treatment as model loaders. Fitting our own lens from scratch avoids third-party weights entirely and is the default. |
| Tier B integrity | Lens readouts are a new exploratory measurement. Exploration split only; the sealed holdout is untouched. Any confirmatory absence-vs-suppression claim needs its own pre-registered endpoints on future batches — J2 output is exploratory by construction. |
| Queue discipline | J-runs ride idle slots only; the nightly Tier B cycle keeps priority; one-running + one-pending as always. Needs either a `jlens-fit.json` trigger (fire_trigger.py must learn the key) or a mode flag on the logits workflow — decide at J1. |
| Framing | Paper is 5 days old, not peer-reviewed, and press coverage runs to consciousness talk. We cite the method, not the metaphysics: no "global workspace" or J-space framing on the site; the lens is "a layer-by-layer readout" and labeled correlational. Voice guardrails apply to all site text. |

## 4. Credit pattern (when anything ships)

Methods endnote + acknowledgments footer, research-notebook register:

> Layer-by-layer readouts use the Jacobian lens (Gurnee et al., Transformer
> Circuits, 2026), computed with the authors' reference implementation
> (github.com/anthropics/jacobian-lens, Apache-2.0). The lens is a readout,
> not an intervention; causal claims in this study rest on activation
> patching.

Link the paper, the repo, and the Neuronpedia demo. Figure captions name the
technique. Exact author list re-verified from the original page via CI before
publication.

## 5. What it does not give us

No feature-level tags (that stays Neuronpedia transcoders, gemma-2-2b only);
no causal evidence (stays B1 patching); no multi-token concept readout; no
hosted API we can call today (the Neuronpedia demo is interactive-only as far
as verifiable from here — re-check from CI, J0).

## 5b. Update 2026-07-11 pm: hosted endpoint found — fitting unnecessary

Owner surfaced the Neuronpedia launch blog: 13 models served (Gemma, Llama,
GPT-OSS, Qwen families) at neuronpedia.org/[modelId]/jlens, plus a "swap"
steering capability. Reading the open-source webapp confirmed a programmatic
endpoint: **POST /api/lens/prompt** (modelId, prompt, type
["JACOBIAN_LENS","LOGIT_LENS"], topN 1-8, numCompletionTokens, stream,
steerTokens/steerLayers/steerStrength/swapToken). Non-streaming returns
{meta, tokens, done} with per-position readouts. This retires the local-fit
plan (J1) for any served model: same $0 hosted pattern as our tracing, same
NEURONPEDIA_API_KEY, no third-party .pt weights, no CPU Jacobians. The
served-model list is deployment config (not in the code), so the overlap
with our matrix is discovered empirically: `scripts/jlens_readout.py`
records supported=false per model via `jlens_readout.yml` probe fires.
Known from their HF lens repo: qwen3-1.7b (in our matrix) has a fitted lens.
Response token schema is undocumented — first probe runs use --save-raw and
a defensive parser (parse_status per pair), then the parser gets pinned
against the real artifact.

**Probe results (run 1, 2026-07-11 14:24-14:49 UTC, batch-6 pairs 1-2):**
SERVED: **gemma-2-2b** and **gemma-2-2b-it** (probe supported=true, raw
committed, schema pinned: tokens[i].results = [{type, top_tokens: [[top-8
strings] per layer]}], layers from meta.layers_by_type; gemma-2-2b exposes
layers 0-25). NOT served (persistent HTTP 500 through the retry ladder —
the same unserved-model signature the graph endpoint shows): gemma-2-9b,
gemma-3-4b-it, qwen3-4b, qwen3-1.7b, llama-3.2-3b, olmo-2-1b,
biomistral-7b. The qwen3-1.7b 500 despite fitted weights on HF suggests the
inference host is not deployed yet; re-probe as Neuronpedia expands.
First real profiles (pair 1, target readable rank-1 by layer 19 clinical,
delayed 2 layers under patient phrasing; pair 2, concept readable
layers 19-24 under clinical then lost at the output layer, never readable
under patient phrasing) already exhibit the depth classes the design
anticipated. Multi-wordpiece targets match by prefix (MIN_PREFIX_CHARS=4),
mirroring the behavioral path's first-wordpiece measurement.

## 6. Gated plan (no fires yet; critic queue owns sequencing)

- **J0 verify (free, next CI touch):** from a runner with open egress — list
  `neuronpedia/jacobian-lens` HF files (gemma lens? our qwen variants?); pull
  the original paper page (authors, citation format, anything the translation
  garbled); check whether Neuronpedia exposes a jlens API endpoint. Pin
  repo SHA + HF revision in docs/model_matrix.md.
- **J1 smoke fit ($0, idle slot):** fit a ~100-prompt lens for gemma-2-2b
  (or apply a verified pre-fitted lens if J0 finds a matching one), chunked,
  wall-time measured. Gate: fits within CI limits with time to spare.
- **J2 readout script:** `scripts/jlens_readout.py` — both phrasings per pair,
  lens rank/log-prob of the clinical target across layers, join key
  (batch, index, model), exploration split only, vocabulary from data files
  as always. Output schema documented before the run.
- **J3 exemplar figure + methods note:** one pair, two columns, site standard,
  credit per §4. Candidate deck artifact for 07-17 ONLY if J1/J2 have landed —
  not promised.
- **J4 (if J2 shows the absence/suppression split):** design doc + fresh
  pre-registered endpoints on future batches; supersedes H2.

**Recommendation:** proceed J0 → J1 in idle queue slots after the nightly
Tier B cycle. The scientific upside (mechanism behind the translation panel)
and the communication upside (the most legible depth figure we could show)
are both real; every risk above has a cheap gate in front of it.
