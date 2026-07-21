# Frontier-advice arm — handoff (2026-07-21, rev 2: multi-provider consumer-tier)

Standalone handoff for the session integrating the new **advice evaluation arm**.
It assumes the 2026-07-21 audit handoff (`docs/audit_2026-07-21.md`, Appendix B
queue) has been worked. Everything below landed on branch
`claude/patientwords-audit-reflection-alwovz`; code complete and tested (suite
green at 303, ruff clean), **not wired into the firing path** — the steps below
do that, in order, with owner sign-off where marked.

Owner decisions recorded 2026-07-21 (design constraints, not suggestions):

- **Pilot budget: $5 for the whole experiment**, Anthropic side on haiku.
- **No Claude-only scale run** — Claude's guardrails make single-vendor scale
  uninformative; the question is cross-vendor.
- **Target vendors:** Claude, OpenAI, Gemini, Grok, Copilot, DeepSeek (main
  consumer products); optionally Kimi, Llama/Meta AI. (Thinking Machines has no
  consumer chat product/API as of 2026-07 — re-check at integration.)
- **Consumer-tier default:** each provider defaults to the model its FREE /
  default consumer tier serves — the experiment measures what the average
  consumer gets — while remaining overridable per run (`provider:model`).

## What this arm is

The next-token study measures probabilities. This arm measures the **advice**
deployed assistant products give for the same clinical situation phrased two
ways. Three run modes: (1) stimuli from situations the study already validated
(published payload — screened-in, measured, holdout-withheld by construction);
(2) owner-authored manual vignettes; (3) a translated arm that runs the
production patient→clinical translation before elicitation, testing whether
translation recovers the *advice*.

Elicitation is unrepeatable by nature, so the design is **auditable, not
reproducible**: append-only JSONL, one record per call with full request, full
raw response, the exact model version string the provider returned, UTC
timestamps, latency, per-call cost, engine sha, and a per-record sha256 chain
whose head lands in the cost sidecar in the same commit as the data (public
repo ⇒ third-party timestamps). Judge and analyze are fully reproducible from
the archive forever.

## The consumer-proxy caveat (state it in every writeup)

API models are **proxies** for consumer products: no product system prompt, no
product-layer safety wrapper, no memory, no UI nudges. Two mitigations are built
in: (a) the registry records a `consumer_proxy_note` per provider documenting
the mapping and its fidelity; (b) products with **no public consumer API**
(Microsoft Copilot, Meta AI) are captured by hand in the real product UI and
imported via `import-manual-responses` — same audit chain, provenance
`capture.method=manual_ui`, never disguised as API output. Recommended: also
hand-run a ~5-stimulus calibration subset in the real UIs of the API-reachable
products, so the API-vs-product gap is measured rather than assumed.

## What exists on this branch

| Path | What |
|---|---|
| `scripts/advice_eval.py` | `build-stimuli` / `elicit` (multi-provider) / `import-manual-responses` / `judge` / `analyze` / `verify-chain` |
| `data/advice_providers.example.json` | provider registry skeleton: per vendor base_url, key_env, consumer_default (**every default is a VERIFY placeholder**), pricing, proxy note; `manual_ui` entries for Copilot/Meta AI |
| `.github/workflows/advice_evaluation.yml` | CI workflow (dispatch + push-path trigger; per-branch concurrency; provider secrets passed through) |
| `data/advice_rubric.example.json` | rubric skeleton — **needs domain review** |
| `data/advice/README.md` | archive schema + audit-chain contract |
| `tests/test_advice_eval.py` | 21 offline tests incl. spec resolution, compat-client path, registry pricing, manual-import chain/judging, holdout guard, tamper/ceiling/resume |

Deliberately absent: `.github/trigger/advice-eval.json` (first sanctioned fire
creates it — NEVER create by hand; it fires a paid workflow on any push
including merges), `fire_trigger.py` registration (step 2),
`data/advice_rubric.json` and `data/advice_providers.json` (only reviewed
copies carry those names).

## Integration steps (in order)

### 1. Land the code
Bring the six paths above onto the working branch/main per the current branch
strategy. No trigger files are touched — merging cannot fire anything.

### 2. Register the trigger in `scripts/fire_trigger.py`
Three edits (then extend `tests/test_fire_trigger.py` key-set/paid coverage;
cite `advice_evaluation.yml` + date in the KNOWN_KEYS comment per convention):

```python
# in TRIGGERS, after "archive-renders":
    "advice-eval",

# PAID_TRIGGERS — elicit AND judge spend Anthropic/provider tokens:
PAID_TRIGGERS = frozenset({"scenario-generation", "model-evaluation", "advice-eval"})

# in KNOWN_KEYS (verified against advice_evaluation.yml `defaults` dict, 2026-07-21):
    "advice-eval": frozenset({
        "stimuli_file", "models", "arms", "samples", "temperature", "max_tokens",
        "translator_model", "max_spend", "judge", "judge_model", "judge_max_spend",
        "rubric", "offset", "limit", "commit_outputs",
    }),
```

The budget guard counts `max_spend`; `judge_max_spend` is a second ceiling it
does not see — keep the sum inside the day's headroom, or extend the guard to
sum both keys (cleaner; add a regression test).

Accounting gap to close in the same session: `ledger_update.py` scans only
`data/simulated/*.report.json`, so advice-arm sidecars
(`data/advice/*.report.json`) will not fold into `spend.today` /
`spend.lifetime` — meaning landed advice spend is invisible to the $2/day
guard once the fire resolves. Extend the ledger's scan globs to include
`data/advice/*.report.json` (both `responses_*` and `judgments_*` sidecars
carry `cost_usd`), with a regression test.

### 3. Provider registry + secrets (consumer-tier defaults)
Copy `data/advice_providers.example.json` → `data/advice_providers.json` and
**verify every `consumer_default` and pricing entry against the vendors'
current free-tier docs** — they are deliberately placeholders (consumer tiers
drift; the registry is data so corrections are config fixes, and the archive
records the exact resolved model per call regardless). Note the Anthropic
entry's recorded tension: claude.ai's free tier is sonnet-class, but the pilot
runs haiku as the owner's cost floor — whichever is used, record the choice in
the pre-registration. Then add the Actions secrets for the vendors in scope:
`OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY`,
`MOONSHOT_API_KEY`, and/or a single prepaid `OPENROUTER_API_KEY` (one key, hard
external ceiling, covers Llama-family too). Missing secrets fail only the spec
that needs them, with a clear message. Model spec syntax everywhere:
`provider` (consumer default) · `provider:model` (override) · bare id
(Anthropic). Copilot / Meta AI are `manual_ui` — API elicitation refuses them
and points at `import-manual-responses`; they need no key at all.

**Option B — one key instead of five (recommended for the pilot):** route all
non-Anthropic vendors through OpenRouter. Add a single prepaid
`OPENROUTER_API_KEY` secret (the prepaid balance is a hard external ceiling on
top of the script's), then edit the registry so each vendor entry keeps its own
name (analysis still groups by vendor — the record's `provider` field comes
from the registry key) but points at the aggregator:

```json
"openai": {"api": "openai-compat", "base_url": "https://openrouter.ai/api/v1",
           "key_env": "OPENROUTER_API_KEY",
           "consumer_default": "openai/VERIFY-free-tier-model", ...}
```

Trade-offs, recorded honestly: proprietary models are served by the vendor's
own backend via OpenRouter's routing, but an intermediary sits in the request
path (~5% markup, its own response metadata) — note it in the pre-registration.
Direct keys remain the higher-fidelity option per vendor; Gemini's direct API
key (AI Studio) has a free tier that covers pilot volumes, so a mixed setup
(direct Gemini + Anthropic, OpenRouter for the rest) is also reasonable.

### 4. Rubric domain review (owner + domain reviewer — blocks judged runs)
Copy `data/advice_rubric.example.json` → `data/advice_rubric.json` after
review. Judgments record the rubric sha, so revisions never contaminate earlier
codings. Un-judged elicitation may proceed before review; claim-grade output
may not.

### 5. Pre-register before the first paid fire (owner sign-off)
`docs/preregistration_advice.md`, Tier B style: endpoints (mean tier-rank
difference patient−clinical per provider; advice downgrade rate;
disclaimer/refusal rate difference by arm; translation recovery; within-prompt
variance), direction + refutation criteria (**register the null**: no
phrasing-dependent advice difference in consumer products is a reportable
result), the provider→model map actually used (frozen registry copy), K,
temperature, stimulus source and n, rubric version, judge model, seed. Also:
the engine README's "nothing here generates or evaluates medical advice" line
needs an owner-approved amendment ("…evaluates assistant advice for
measurement; never dispenses it") — owner prose, redline it.

### 6. Build and review stimuli ($0, local)
```bash
python scripts/advice_eval.py build-stimuli --source payload --only-flips --max-items 25
python scripts/advice_eval.py build-stimuli --source manual --manual-in my_situations.json
```
Review the assembled messages by eye (payload vignettes are probe prompts
finished with a fixed ask suffix, identical on both sides — the minimal pair
holds; manual mode is where polished vignettes come from). Commit the stimuli
file — the workflow reads it from the repo.

### 7. Pilot fire — the $5 cross-provider experiment
Fire per provider group (or one fire listing several specs; chunk with
`offset`/`limit` under queue discipline). Example first fire:

```bash
python scripts/fire_trigger.py fire --trigger advice-eval --params '{
  "stimuli_file": "data/advice/stimuli_<STAMP>.json",
  "models": "anthropic:claude-haiku-4-5 openai google deepseek",
  "arms": "clinical,patient,translated",
  "samples": "3", "max_spend": "1.50",
  "judge": "false",
  "commit_outputs": "true",
  "_note": "advice arm pilot 1/2 — consumer defaults, elicit only, rubric pending"
}'
```
A second fire adds `xai moonshot` (dearer tiers) and, once the rubric clears
review, a judge-only re-fire (`"judge":"true"` — elicit resumes and skips
everything archived). This first fire **creates** the trigger file; thereafter
the merge/copy danger rule covers it like the other six. After landing:
harvest, `resolve`, then `verify-chain` locally. Copilot/Meta AI: hand-capture
in the real UIs and `import-manual-responses` (validated, chained, $0).

**$5 pilot arithmetic** (25 stimuli × 3 arms × K=3 = 225 advice calls per
provider, ~200 in / ~500 out tokens per call): haiku ≈ $0.55; mini/flash-class
consumer defaults ≈ $0.15–0.45 each; DeepSeek ≈ $0.15; Grok-class ≈ $1.20 —
five API vendors ≈ **$2.50–3.00**, plus a haiku judge pass over ~1,200
responses ≈ **$1.10**, translations ≈ $0.05. Total ≈ **$3.70–4.20, inside $5.**
The script's pre-call check reserves the worst case, so a ceiling of $X
guarantees spend < $X per fire; the paid-trigger guard counts each fire against
the $2/day ceiling — two fires of $1.50 + a $1.00 judge fire fit a two-day
window without touching the ceiling.

### 8. After the pilot
Validate the judge against a blinded human-coded sample
(`judge --human-sample 25`; report agreement); run `analyze`; write the pilot
note. Only then decide any scale-up — and per the owner: scale means **more
vendors/stimuli at cheap consumer tiers**, not a Claude-only scale run. When
the arm becomes routine, add the advice drift sentinel (small pinned weekly
probe per provider) before making cross-week comparisons — consumer tiers
change silently; every record's `model_returned` string is the tripwire.

## Guardrails (absolute)

- Fire ONLY via `scripts/fire_trigger.py`; never touch `.github/trigger/` by
  hand; never `--force-evict`/`--override-budget`; chain, never stack.
- `data/advice/` is append-only and hash-chained; `elicit` and
  `import-manual-responses` refuse a broken chain; tampering is reported to the
  owner, never repaired in place.
- Never quote or paraphrase Tier B holdout phrases anywhere; payload-sourced
  stimuli are seal-safe by construction, the pairs-source guard is mechanical,
  chat replies and reports are on you.
- Judge stays blinded (response text only). Manual-UI records are never
  disguised as API output. No medical vocabulary in Python — stimuli, tiers,
  judge wording, and the provider map are data.
- Both repos public: no secrets, ever; keys exist only as Actions secrets.
- This arm evaluates advice for measurement; it never dispenses advice, and
  published framing must say so (owner-approved prose).
