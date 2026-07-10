# Fable week plan — owner-approved 2026-07-09 (FABLE PLAN paste)

Owner decisions: A1 nightly · A2 approve · A3 approve · A4 keep ops light ·
B1–B4 all approved (B4 both) · C1 Llama-3.2-3B add · C2 Phi skip ·
C3 OLMo-2 add · C4 medical-tuned 7B add.
Owner note: Fable runs through **Tuesday 2026-07-14**, then heavy batches
downshift (agents pinned to Opus 4.8 via per-agent model override) unless
Fable access increases. Ops Routine stays on the light path throughout (A4).

## A · Autonomous streams (this session)

- **A1 Nightly research-critic (Fable), ~05:00 UTC daily:** read everything
  landed that day (Tier B batches, traces, stats), re-run
  `paired_stats_rigor.py`, evaluate like a hostile reviewer, design/queue the
  next experiments, write suggestions into `ops/dashboard.json`
  (`verdicts`/`findings_delta`/`decisions_pending`) + a dated report in
  `docs/critic/` so the 13:00 UTC digest carries them. Re-chains itself +24h.
- **A2 Verify-before-commit:** every autonomous batch ends with adversarial
  reviewer agents over the diff before I commit. (Standing policy.)
- **A3 Weekly synthesis deep-refresh:** Monday — full DRAFT rewrite of
  `docs/findings_synthesis.md` against all accumulated data, delivered as
  `docs/findings_synthesis_DRAFT_<date>.md` for the owner's voice. Never
  auto-published over the released doc.
- **A4:** daily ops Routine stays on the default light model.

## B · Interpretability experiments (all $0 compute)

- **B1 Activation patching in CI:** wire the hooking dependency
  (transformer-lens) into a CPU workflow; run the (layer × position)
  recovery grid on the downgrade set; extend batch_summary with the
  documented recovery-map schema (`docs/activation_patching_design.md`).
- **B2 gemma-2-9b universality:** probe Neuronpedia tracer support; CPU
  logits regardless. Gemma Scope exists at 9B.
- **B3 gemma-2-2b-it contrast:** same base ± instruction tuning; one logits
  run on the unified set.
- **B4 both:** cross-pair feature transfer + steering-vector vs SAE-feature
  comparison; designs then hosted-API execution ($0), small-n pre-registered.

## C · Behavioral matrix additions ($0 CPU logits)

| add | HF id | gate? |
|---|---|---|
| Llama-3.2-3B | `meta-llama/Llama-3.2-3B` | Meta license form (free) |
| OLMo-2-1B | `allenai/OLMo-2-0425-1B` | none |
| BioMistral-7B (medical-tuned) | `BioMistral/BioMistral-7B` | none (Apache-2.0) |
| gemma-2-2b-it (B3) | `google/gemma-2-2b-it` | Gemma license (likely already accepted) |
| gemma-2-9b (B2) | `google/gemma-2-9b` | Gemma license (likely already accepted) |

Rollout: probe each model with a tiny logits run first; only models that
401 as gated get surfaced to the owner as a decision item with exact
click-path instructions. **Hugging Face cost truth:** license acceptance and
weight downloads are free; no card exists on the account to charge; HF bills
only optional subscriptions/hosted endpoints, which this pipeline never uses;
CI compute is GitHub's free public-repo runners. Charge risk: none.

## Schedule anchors

- Tonight 01:00 UTC: Tier B go/no-go (unchanged).
- Friday 08:00 UTC: pre-flight handoff (unchanged).
- Daily 05:00 UTC: A1 critic · 13:00 UTC: ops digest.
- Monday: A3 synthesis draft.
- **Tuesday 2026-07-14 end-of-day: downshift** — batch agents pinned to
  Opus 4.8 (per-agent override; the session model itself is owner-controlled).

## H · Headroom streams (owner-approved 2026-07-09 evening; H6 pending)

Execution order (nightly critic works through this queue; verify-before-
commit applies to all):
1. **H1 claim-integrity CI** — engine workflow that recomputes every
   published number from committed artifacts on push and fails on drift;
   includes a deployed-site health job (fetch the live Pages URL + data
   files from the CI runner, assert 200 + parseable + spot values).
2. **H3 circuit-drift monitor** — extend the critic cycle: compare each new
   Tier B trace's named-feature composition/overlap vs the established set
   (docs/analyses_20260708.json baseline); digest flags composition shifts.
3. **H2 logit-lens depth profiles** — rides the patching CI dependency;
   layer-by-layer target trajectory clinical vs patient on the downgrade
   set; produces the companion figure to the patching heatmap.
4. **H4 feature atlas** — data-driven catalog page (label, category,
   frequency, mean layer, Neuronpedia link) from the analyses bundle;
   no owner prose needed.
5. **H5 reproducibility kit** — one-command rebuild script, dataset card,
   schema docs, CITATION.cff, fresh collaborator exports.
6. H6 preprint skeleton — HELD pending owner.

## W · Gaps closed 2026-07-09 evening

- W1 watchdog: the fresh-session Routine now verifies the orchestrator's
  artifacts are fresh and flags a stalled wake chain in the digest.
- W2 deployed-site health: folded into H1 (CI runners have open egress;
  the sandbox proxy may block github.io locally).
- W3 prereg Amendment 1: 10% confirmatory holdout by deterministic hash +
  seed provenance, committed BEFORE Tier B batch 1 (start_utc null at
  amendment commit).
- W4 STOP protocol: digest footer tells the owner one word here freezes
  all automation (this session deletes every trigger on "STOP").
- W5 model supply-chain (owner request 2026-07-09 night): safetensors-only
  + trust_remote_code=False enforced with a tripwire test; official-org-only
  registry; ephemeral-runner execution; revision pinning after each model's
  first probe (critic fills the table in docs/model_matrix.md). Owner's
  morning digest is the once-daily touchpoint — new ideas surface there,
  not as extra pings.

## P · Presentation & provenance queue (owner request 2026-07-10, in-flight)

Owner asked what the new findings justify adding for (1) interpretability,
(2) practical explanation, (3) communicating the study's timing to readers.
Data artifacts only — site text/HTML stays the owner's lane.

- **P1 convergence tracker** (`scripts/convergence_tracker.py`): per-model
  cumulative penalty CI + downgrade/upgrade counts batch-by-batch (ordered
  by batch stamp, exploration split only, seed 7). Writes
  `data/convergence.json` + site copy. Re-run each critic cycle. The
  gemma-3 n.s.→significant arc (11v4 p=0.12 @133 → 22v5 q=0.002 @240) is
  the worked example a reader should be able to see.
- **P2 study timeline** (`scripts/study_timeline.py`): reconstruct the
  study from committed artifacts — batch sidecars (run_timestamp, model,
  accepted, cost), trace-part commit times, prereg/amendment commit dates,
  tierb.start_utc — into `data/timeline.json` + site copy, plus a
  methods-endnote DRAFT in docs/ for the owner's voice. Honest answer to
  "how long did this take": days, with receipts; generation < $10 total;
  tracing/inference $0 public CI.
- **P3 recovery-map aggregation** (after B1 grid runs land): per-layer
  recovery profile + term-site vs elsewhere recovery share across the
  downgrade set. The claim it can earn: the penalty is carried by the
  wording-swap site, at named layers — the second causal leg beside
  steering. Feeds a future heatmap figure (H2 logit-lens companion).
- Owner-lane suggestion (parked): one-line methods stamp "measured <range>,
  N pairs, $X API credits, all runs public" sourced from timeline.json.

STATUS 2026-07-10 pm: P1+P2 BUILT and live (owner delegated the site
placements same day: Fig. 5 convergence small-multiples on methods.html,
timeline strip on simulated-scenarios; both runtime-drawn from data files,
browser-verified, fallback-safe). Critic: re-run both generators each cycle
for freshness; P3 activates when the first grid batch lands.

## New-model incorporation checklist (owner request 2026-07-10 pm)

When llama-3.2-3b, biomistral-7b (medical-tuned), olmo-2-1b, or the gemma
variants land logits for the unified stems, the chain is automatic EXCEPT
two manual steps the critic owns:
1. Re-run the exporter with the extended model list so models_meta + the
   simulated-page selector include them:
   `--models gemma-2-2b,gemma-3-4b-it,qwen3-4b,qwen3-1.7b,llama-3.2-3b,olmo-2-1b,biomistral-7b,gemma-2-2b-it,gemma-2-9b`
   (a model's trace dir is used only where present).
2. Verify the comparison page (model-evaluations/) renders the new rows
   (forest, dumbbells, evidence table pick up d.models automatically;
   labels come from models_meta) and republish site data.
Everything else already flows: collector reads any trace_out/<stem>__<model>
dir; rigor computes per_model for all models present; model_stats.json site
copy carries them; convergence_tracker appends new models automatically
(PREFERRED_ORDER first, then alphabetical).

## Friday 2026-07-17 AM: full site-text outline for the owner

Owner hand-edits prose after vacation. Wake armed for 12:45 UTC Fri 07-17:
regenerate the site-text extraction from the LIVE pages (this week added
methods Steps 5-6, the comparison page, timeline strip, Fig. 5 captions),
emit it as MARKDOWN with stable block ids (owner edits and returns it as
markdown; apply block-by-block like the 07-09 Rmd round), SendUserFile +
flag in that morning's digest.

ADDED 07-10 pm (owner): the same Friday wake also delivers the ANTHROPIC
MEETING DECK (ops/decks/meeting_deck_20260717.html): 5 artifact cards
(plumber hook, asymmetry dumbbells, steering table, convergence figure,
translation-audit slopegraph) + a talking-points card (person-centered
inversion, disparity-gradient bridge, dialect framework + validation
roadmap, limits to preempt), fresh Tier B numbers only.
Wake: trig_01RH47ogfzk48SoLR4SpAVdz (replaces trig_01CsrvJeckBXFwfvq7yjBAUc).
