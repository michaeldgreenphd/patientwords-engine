# Kimi K3 (Moonshot) — can it join the next-token experiment?

Opened 2026-07-28 at owner request. Status: **NOT ACTIONABLE TONIGHT.** Nothing
fired. This records the feasibility check so the decision is not re-litigated.

## The model is real

Kimi K3, Moonshot AI, announced 2026-07-16: Mixture-of-Experts, **2.8T total
parameters**, 896 experts, 16 active per token, 1M context. Open weights
released 2026-07-27. Available on OpenRouter as `moonshotai/kimi-k3`.

## Why it cannot enter the next-token arm as that arm is currently built

The next-token experiment has exactly two backends, and K3 fits neither.

**1. Neuronpedia hosted circuit tracing — NO.** `MODEL_REGISTRY` lists four
models and only `gemma-2-2b` actually produces hosted graphs (the others 400/500
server-side, verified 2026-07-07). Neuronpedia serves small open models that have
transcoder feature sets; a 2.8T MoE is not and will not be among them. Without a
transcoder source set there is no `clinical_mass` either — the tagging that makes
this arm mechanistic rather than merely behavioural.

**2. CPU logits-eval — NO, by a wide margin.** `scripts/logits_eval.py` loads
weights with `AutoModelForCausalLM` and runs `torch` inference on a GitHub
Actions runner (CPU, ~7GB RAM, no GPU). Every model it has ever run is 1B-8B:
olmo-2-1b, qwen3-1.7b, llama-3.2-3b, gemma-2-2b, gemma-3-4b-it, medgemma-4b-it,
meditron3-8b, apertus-8b-meditronfo. K3 is roughly 350x the largest of those.
This is not a tuning problem.

## The only viable route, and its open question

K3 is reachable by **API** (OpenRouter), the same path the advice arm already
uses for `moonshotai/kimi-k2.5`. Measuring next-token behaviour that way needs a
new backend — call it `api-logits` — that requests `logprobs` and emits the
existing `batch_summary` schema so downstream merges unchanged (the same trick
`logits_eval.py` plays with `backend: "logits"`, `source_set: null`).

**Blocking unknown: does OpenRouter return logprobs for this model?** Not
established. A sampled K3 response shows a `logprobs` field present but null.
Many hosted chat endpoints accept the parameter and return nothing. This must be
settled by one cheap probe call from CI (where the key lives) BEFORE any design
work. If logprobs are unavailable, the route is closed and there is nothing to
build.

**Second constraint: cost.** The whole next-token arm is $0 today (Neuronpedia
tracing and CPU inference are free). An API-logits backend makes it paid and puts
it under the $2/day ceiling.

**Third, and the reason to think twice:** an API-logits model yields only the
output distribution — no attribution graphs, no clinical mass, no layer-depth
readout. That is a strictly weaker measurement than what this arm exists to
produce, and it sits closer to the advice arm than to the tracing arm.

## Recommendation

**K3 belongs in the ADVICE arm, not the next-token arm.** That arm already
reaches Moonshot through OpenRouter, already measures frontier API models, and
already has K2.5 in it — adding K3 is a registry entry plus a paid run rather
than a new backend. Two things make it an owner decision, not a default:
- the advice arm is **frozen at n=25** pending clinician review of the draft tier
  rubric (prereg Amendment 2), so adding a 9th model is a design change;
- it is paid, against the $2/day ceiling, and K3's rate is not yet in
  `data/advice_providers.json`.

A K2.5 -> K3 comparison within one vendor would also be genuinely interesting on
its own terms: same lab, one generation apart, same stimuli.

## If the owner wants the next-token route anyway

Ordered, cheapest first:
1. One $0-ish probe fire from CI: call `moonshotai/kimi-k3` with `logprobs` set
   and record whether values come back. Settles the whole question.
2. Only if that succeeds: build `api-logits`, emitting `batch_summary` with
   `backend: "api-logits"`, `source_set: null`. Downstream consumers already null
   clinical-mass for null-source-set models, so the frontend needs no change.
3. Register pricing and add a spend guard before any batch run.

## Why nothing was fired tonight

The circuit-trace lane is mid-backfill with 48 pairs left and both slots
occupied; a new model would compete for the same queue that finally has momentum.
Nothing here is urgent and all of it is cheaper to do after the backfill lands.
